# -*- coding: utf-8 -*-
import os
import shlex
import signal
import subprocess
import sys
import time
from typing import cast

from loguru import logger

import i18n
import main
from msg_push import bark, dingtalk, ntfy, pushplus, send_email, tg_bot, xizhi
from src import utils
from src.video_postprocess import get_startup_info

# 通知与录制状态钩子（独立模块）
#
# 负责：多渠道直播状态推送（push_message）、录后自定义脚本执行（run_script）、线程安全的
# 错误/成功计数（record_error / record_success）、按错误率动态调整并发（现委托
# ConcurrencyScheduler 的自适应调速循环）、清理单个直播间的录制状态（clear_record_info）、
# 房间线程退出时从运行列表移除该房间（remove_room_from_running）。
#
# 这些函数读写的都是 main 的配置与运行时全局变量（推送渠道、录制状态集合、错误率窗口、
# 并发信号量），故通过 `import main` 在运行时惰性读写：状态在 main 与各模块间实时共享，
# 同时避免循环导入与 `python main.py` 直接运行时的 __main__ 二次执行。


# 按配置的推送渠道（微信/钉钉/邮箱/TG/BARK/NTFY/PUSHPLUS）分发直播状态消息：
# record_name 房间显示名、live_url 直播间地址（部分渠道作跳转链接）、content 推送正文。
def push_message(record_name: str, live_url: str, content: str) -> None:
    # 兜底标题是推送文案（提取盲区③），过 tr 先查表后插值才能被目录命中
    msg_title = main.push_message_title.strip() or i18n.tr("直播间状态更新通知")
    push_functions = {
        "微信": lambda: xizhi(main.xizhi_api_url, msg_title, content),
        "钉钉": lambda: dingtalk(main.dingtalk_api_url, content, main.dingtalk_phone_num, main.dingtalk_is_atall),
        "邮箱": lambda: send_email(
            main.email_host,
            main.login_email,
            main.email_password,
            main.sender_email,
            main.sender_name,
            main.to_email,
            msg_title,
            content,
            main.smtp_port,
            main.open_smtp_ssl,
        ),
        "TG": lambda: tg_bot(main.tg_chat_id, main.tg_token, content),
        "BARK": lambda: bark(
            main.bark_msg_api, title=msg_title, content=content, level=main.bark_msg_level, sound=main.bark_msg_ring
        ),
        "NTFY": lambda: ntfy(
            main.ntfy_api,
            title=msg_title,
            content=content,
            tags=main.ntfy_tags,
            action_url=live_url,
            email=main.ntfy_email,
        ),
        "PUSHPLUS": lambda: pushplus(main.pushplus_token, msg_title, content),
    }

    for platform, func in push_functions.items():
        if platform in main.live_status_push.upper():
            try:
                result = func()  # type: ignore[no-untyped-call]
                result_dict = cast(dict[str, list[str | int]], result)
                logger.info(
                    i18n.tr(
                        "提示信息：已经将[{record_name}]直播状态消息推送至你的{platform}, 成功{success_count}, 失败{error_count}",
                        record_name=record_name,
                        platform=platform,
                        success_count=len(result_dict["success"]),
                        error_count=len(result_dict["error"]),
                    )
                )
            except Exception as e:
                # {e} 必须过 mask_credentials：推送渠道的 API URL 本身就是凭据载体（息知
                # https://xizhi.qq.com/<key>、Bark https://api.day.app/<key>/…、TG
                # .../bot<token>/sendMessage），而 urllib/requests 异常的 str() 常规把完整 URL
                # 连同 path 拼进消息——直传等于把密钥明文写进 logs/ 并按轮转保留多份。
                # f-string 直传 print_colored 也扫不到提取器（盲区①），故先查表后插值。
                main.color_obj.print_colored(
                    i18n.tr("直播消息推送到{platform}失败: {e}", platform=platform, e=utils.mask_credentials(str(e))),
                    main.color_obj.RED,
                )


# 录后自定义脚本执行超时（秒）：脚本由用户提供，若其挂起（等输入 / 死循环 / 网络阻塞），
# 无超时的 communicate() 会一直占用调用线程。超时后终止子进程并记日志，不让第三方脚本拖住
# 录制主流程。默认给足 5 分钟以兼容耗时较长的上传 / 转码类脚本；模块级常量便于测试注入。
_SCRIPT_TIMEOUT_SECONDS = 300.0

# 超时**之后**回收管道读取的时限（秒）。第二次 communicate() 若不带超时：脚本只要起过孙进程
# （rclone / curl / 数据库客户端这类上传脚本的常态），孙进程就继承管道写端，只 kill 直接子进程
# 永远读不到 EOF ⇒ 录后钩子线程被永久挂住（本机 Windows 实测：孙进程 sleep 60 时，kill 掉直接
# 子进程后 communicate 仍取不到输出）。宁可丢一段输出也不许无界阻塞。
_SCRIPT_REAP_TIMEOUT_SECONDS = 10.0

# taskkill 自身的时限（秒）：进程树很大或权限不足时，不得让「回收进程树」变成第二个挂起点。
_TREE_KILL_TIMEOUT_SECONDS = 5.0

# 进程树回收的平台判定，做成模块级常量而不是就地读 os.name/sys.platform：用例可
# monkeypatch.setattr(notify, "_KILL_TREE_VIA_TASKKILL", True) 让 Windows 分支在 Linux CI 上真实执行。
_KILL_TREE_VIA_TASKKILL = os.name == "nt"


# 把 TimeoutExpired 里「已经读到的部分输出」收口成 bytes：communicate() 超时抛的异常带 stdout/stderr
# 字段，text 模式下是 str、一条都没读到时是 None，两种都不许流到下游 .decode()（会抛 AttributeError）。
def _partial_output_bytes(value: object) -> bytes:
    return value if isinstance(value, bytes) else b""


# POSIX 进程组回收：脚本以 start_new_session=True 启动 ⇒ 自成会话，进程组 ID == 子进程 PID，
# killpg 一次收掉脚本 + 它起的全部孙进程（只 kill 直接子进程会留下握着管道写端的孙进程）。
# os.killpg/os.getpgid 与 signal.SIGKILL 是 POSIX-only 符号（typeshed 在 win32 下不导出），必须用
# sys.platform **字面量**门控，本地 mypy（win32）与 `mypy --platform linux` 才能双跑干净。
# 门控方向写反静态检查发现不了，由 tests/test_notify_script_guard.py::
# test_platform_gate_direction_is_locked_in_source 断言「早返回行在 killpg 行之前且比较的是
# == "win32"」锁住；win32 下本函数什么都不做，由 _kill_process_tree 的 finally 兜底。
def _kill_posix_process_group(pid: int) -> None:
    if sys.platform == "win32":
        return
    os.killpg(os.getpgid(pid), signal.SIGKILL)


# 超时后回收**整棵进程树**：任何失败一律退化到只杀直接子进程，绝不向调用方抛出——run_script
# 对外的成败语义由脚本进程自己决定，不由回收路径决定。masked_command 已由调用方预先脱敏。
def _kill_process_tree(process: subprocess.Popen[bytes], masked_command: str) -> None:
    try:
        if _KILL_TREE_VIA_TASKKILL:
            # Windows：taskkill /T（递归子树）/F（强制）。一律 argv 列表调用，禁止 shell=True——
            # 参数是用户脚本命令行，交给 cmd 解释等于推倒 run_script「不用 shell」的前提。
            # 输出不参与判定，capture_output 后按字节原样丢弃、**不做解码**（中文 Windows 上
            # taskkill 按 GBK 码页回显本地化消息）。
            subprocess.run(
                ["taskkill", "/T", "/F", "/PID", str(process.pid)],
                capture_output=True,
                timeout=_TREE_KILL_TIMEOUT_SECONDS,
                check=False,
            )
        else:
            _kill_posix_process_group(process.pid)
    except Exception as e:
        # 典型形态：子进程已自行退出（ProcessLookupError）、Linux CI 上被强制走 Windows 分支
        # 时压根没有 taskkill（FileNotFoundError）、taskkill 自身超时。留痕但不改写结果——
        # 下面 finally 仍会 kill 直接子进程。
        # msgid 复用既有的「执行自定义脚本失败」条目：新增模板要同批改四份 i18n 目录并重编 .mo，
        # 不在本文件权限内；异常类型与脱敏文本照旧走实参。
        logger.warning(
            i18n.tr(
                "执行自定义脚本失败: {command} - {type_name}: {e}",
                command=masked_command,
                type_name=type(e).__name__,
                e=utils.mask_credentials(str(e)),
            )
        )
    finally:
        try:
            process.kill()
        except OSError:
            # 进程已经自行退出（ProcessLookupError 是 OSError 子类）正是期望结果，无需上报
            pass


# 把「已脱敏的命令原文」拆成 argv 并起脚本进程；返回 Popen[bytes]（管道按字节读，解码在调用侧
# 统一做，见 run_script 里 errors="replace" 的取舍）。独立成函数而不是在 run_script 里分叉两次
# Popen 调用：两平台形态各写一遍字面调用比 `**dict` 拼装更稳（后者会让 mypy 丢掉 Popen[bytes]
# 的推断，也让替身用例的 kwargs 断言依赖拼装顺序）。
def _spawn_script(args: list[str]) -> subprocess.Popen[bytes]:
    if _KILL_TREE_VIA_TASKKILL:
        # Windows：不传 start_new_session——它在 CPython 的 Windows 侧是 unused_start_new_session
        # （文档明确 POSIX only），传了零收益，却把「会话 detach」这个 POSIX 语义塞进 Windows 的
        # 进程创建参数（本机实测过一次偶发 OSError [WinError 50] 不支持该请求，与第三方
        # CreateProcess 钩子/沙箱层有关）；Windows 的进程树回收一律走 taskkill /T。
        return subprocess.Popen(
            args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, startupinfo=get_startup_info(main.os_type)
        )
    # POSIX：让脚本自成会话/进程组 ⇒ _kill_posix_process_group 的 killpg 能一次收掉整棵树
    # （孙进程继承着 stdout 管道的写端，只 kill 直接子进程时第二次 communicate 读不到 EOF）。
    return subprocess.Popen(
        args,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
        startupinfo=get_startup_info(main.os_type),
    )


# 执行用户自定义的录后脚本命令（shlex 拆分，不用 shell），打印其 stdout/stderr。
def run_script(command: str) -> None:
    # 不用 shell=True（避免命令注入），交给 shlex.split 拆分。三点取舍：
    # - 保留 posix=True（默认）以正确解析含引号的命令（如 "python -c \"...\""）；posix=False 会把外层
    #   双引号当字面字符（实测 shlex.split('python -c \"print()\"', posix=False) →
    #   ['python', '-c', '"print()"']），让 -c 收到带引号的整段而破坏行为。
    # - 已知限制：Windows 反斜杠路径（"C:\\path\\to.exe"）被 POSIX 规则当转义符拆分，要求用户改用
    #   正斜杠（"C:/path/to.exe"）或 PowerShell 原生语法；彻底修复需重写拆分器。
    # - stdout/stderr 以 errors="replace" 解码：Windows 脚本常输出 GBK 字节（如 PowerShell 中文），
    #   严格 utf-8 会抛 UnicodeDecodeError 被 except 兜底误报成「命令解析失败」。
    #
    # 日志脱敏：command 里常内嵌凭据（rclone 的 remote token、curl 的 Authorization 头、数据库
    # 口令），而 logs/ 下的日志按 rotation 保留多份 ⇒ 原文入日志＝凭据长期落盘。故所有会进日志的
    # command / 异常文本一律过 utils.mask_credentials，只在落日志时脱敏，实际执行的 args 仍用原文。
    # 脚本自身的 stdout/stderr 仍原样 print（那是用户脚本的输出，脱敏会破坏上传/转码日志可读性）；
    # 结构性治本（loguru patcher 统一过码）已在 src/utils.py::mask_credentials 注释里列为另案待办。
    masked_command = utils.mask_credentials(command)
    try:
        args = shlex.split(command)
        process = _spawn_script(args)
        try:
            stdout, stderr = process.communicate(timeout=_SCRIPT_TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired:
            # 脚本挂起：先收整棵进程树（孙进程会握着管道写端，只 kill 直接子进程读不到 EOF），
            # 再带**有限超时**地回收管道，避免读取线程残留导致调用方永久阻塞。
            _kill_process_tree(process, masked_command)
            try:
                stdout, stderr = process.communicate(timeout=_SCRIPT_REAP_TIMEOUT_SECONDS)
            except subprocess.TimeoutExpired as e:
                # 依然读不到 EOF（顽固孙进程 / 进程处于不可中断睡眠）⇒ 放弃读取，只取异常里已读到
                # 的部分；未读的管道随 Popen 对象由解释器的子进程清理收尾，绝不再无限阻塞录后线程。
                stdout, stderr = _partial_output_bytes(e.stdout), _partial_output_bytes(e.stderr)
                logger.warning(
                    i18n.tr(
                        "执行自定义脚本失败: {command} - {type_name}: {e}",
                        command=masked_command,
                        type_name=type(e).__name__,
                        e=utils.mask_credentials(str(e)),
                    )
                )
            logger.error(
                i18n.tr(
                    "执行自定义脚本超时（{_SCRIPT_TIMEOUT_SECONDS} 秒），已终止: {command}",
                    _SCRIPT_TIMEOUT_SECONDS=_SCRIPT_TIMEOUT_SECONDS,
                    command=masked_command,
                )
            )
        stdout_decoded = stdout.decode("utf-8", errors="replace")
        stderr_decoded = stderr.decode("utf-8", errors="replace")
        if stdout_decoded.strip():
            print(stdout_decoded)
        if stderr_decoded.strip():
            print(stderr_decoded)
    except PermissionError as e:
        logger.error(
            i18n.tr(
                "执行自定义脚本失败（无执行权限）: {command} - {type_name}: {e}",
                command=masked_command,
                type_name=type(e).__name__,
                e=utils.mask_credentials(str(e)),
            )
        )
        logger.error("脚本无执行权限!, 若是Linux环境, 请先执行:chmod +x your_script.sh 授予脚本可执行权限")
    except OSError as e:
        logger.error(
            i18n.tr(
                "执行自定义脚本失败: {command} - {type_name}: {e}",
                command=masked_command,
                type_name=type(e).__name__,
                e=utils.mask_credentials(str(e)),
            )
        )
        logger.error("Please add `#!/bin/bash` at the beginning of your bash script file.")
    except ValueError as e:
        logger.error(
            i18n.tr(
                "脚本命令解析失败: {command} - {type_name}: {e}",
                command=masked_command,
                type_name=type(e).__name__,
                e=utils.mask_credentials(str(e)),
            )
        )


# 线程安全记录一次错误：累计计数 error_count 加一，并向错误率窗口追加样本 1。
def record_error(key: str | None = None) -> None:
    # 滑动窗口 deque maxlen 自动裁剪；同时上报调度器（按 key 驱动熔断与全局背压）。
    # key 为可选（直播间 host），缺省时仅维护全局错误窗口（保持无参调用以兼容既有调用方与测试）。
    with main.max_request_lock:
        main.error_count += 1
        main.error_window.append(1)
    # 直接访问模块级声明属性（AGENTS.md 禁止三参 getattr：返回 Any 使类型检查静默失效）
    scheduler = main.scheduler
    if scheduler is not None:
        scheduler.record_failure(key)


# 线程安全记录一次成功的检测周期：向错误率窗口追加样本 0。
def record_success(key: str | None = None) -> None:
    # 与 record_error 的 1 混合采样，使 error_window 反映真实错误率（此前只记 1 导致错误率恒为
    # 1.0，并发只能降不能升）；同时上报调度器。保持无参调用以兼容既有调用方与测试。
    with main.max_request_lock:
        main.error_window.append(0)
    # 直接访问模块级声明属性（同 record_error：AGENTS「禁止三参 getattr」条）
    scheduler = main.scheduler
    if scheduler is not None:
        scheduler.record_success(key)


# 守护线程主体：委托给并发调度器的自适应调速循环（自适应全局容量 + per-key 熔断）；死循环不返回。
def adjust_max_request() -> None:
    # 并发调速完全由 ConcurrencyScheduler.adjust_loop 负责；保留函数名以兼容 main 的守护线程启动
    # 调用；调度器就绪前先等待。
    while main.scheduler is None:
        time.sleep(1)
    main.scheduler.adjust_loop()


# 清理 record_name 的录制状态；若 record_url 已被注释则从运行列表移除并把监控计数减一。
def clear_record_info(record_name: str, record_url: str) -> None:
    with main.record_state_lock:
        main.recording.discard(record_name)
        # 清理录制时间记录，防止长期运行内存无界增长
        main.recording_time_list.pop(record_name, None)
        if record_url in main.url_comments and record_url in main.running_list:
            main.running_list.remove(record_url)
            main.monitoring -= 1
            main.color_obj.print_colored(
                i18n.tr("[{record_name}]已经从录制列表中移除\n", record_name=record_name), main.color_obj.YELLOW
            )


# 房间线程退出时从运行列表移除 record_url 并把监控计数减一（幂等：已被 clear_record_info 移除
# 时为无操作）。
# 不按 exit_recording 分流的原因：该标志在磁盘满暂停（main.py 磁盘限制块）时同样置位，若据此跳过
# 清理，暂停期退出的线程会让 URL 永久残留在 running_list，空间恢复后主循环的「not in running_list」
# 拉起条件恒假、所有房间不再被拉起。真进程退出路径（safe_exit）上多跑一次无害，故一律在
# record_state_lock 内幂等执行。
def remove_room_from_running(record_url: str) -> None:
    # 兜底清理：覆盖「停止录制」（recording_enabled=False）、磁盘满暂停与线程意外退出路径——
    # 线程退出后运行列表若残留该 URL，主循环会误判「仍在运行」而不再重新拉起，
    # 重新开始录制后该房间将永久失联
    if not record_url:
        return
    with main.record_state_lock:
        if record_url in main.running_list:
            main.running_list.remove(record_url)
            main.monitoring -= 1
