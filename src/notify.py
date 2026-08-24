# -*- coding: utf-8 -*-
# 通知与录制状态钩子（独立模块）
#
# 负责：
# - 多渠道直播状态推送（push_message）
# - 录后自定义脚本执行（run_script）
# - 线程安全的错误/成功计数（record_error / record_success）
# - 按错误率动态调整并发线程数（adjust_max_request）
# - 清理单个直播间的录制状态（clear_record_info）
#
# 这些函数需要读取/写入 main 的大量配置与运行时全局变量
# （推送渠道配置、录制状态集合、错误率窗口、并发信号量等），
# 通过 `import main` 在运行时惰性读写，保证状态在 main 与各模块间实时共享，
# 同时避免循环导入与 `python main.py` 直接运行时的 __main__ 二次执行。

import shlex
import subprocess
import time
from typing import cast

from loguru import logger

import main
from msg_push import bark, dingtalk, ntfy, pushplus, send_email, tg_bot, xizhi
from src.video_postprocess import get_startup_info


# 按配置的推送渠道（微信/钉钉/邮箱/TG/BARK/NTFY/PUSHPLUS）分发直播状态消息：
# record_name 房间显示名、live_url 直播间地址（部分渠道作跳转链接）、content 推送正文；无返回值
def push_message(record_name: str, live_url: str, content: str) -> None:
    # 触发消息推送（多渠道分发）
    msg_title = main.push_message_title.strip() or "直播间状态更新通知"
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
                    f'提示信息：已经将[{record_name}]直播状态消息推送至你的{platform}, 成功{len(result_dict["success"])}, 失败{len(result_dict["error"])}'
                )
            except Exception as e:
                main.color_obj.print_colored(f"直播消息推送到{platform}失败: {e}", main.color_obj.RED)


# 执行用户自定义的录后脚本命令 command（shlex 拆分，不用 shell），打印其 stdout/stderr；无返回值
def run_script(command: str) -> None:
    # 执行自定义脚本命令
    # 使用 shlex.split 安全解析命令字符串，避免 shell=True 命令注入
    try:
        args = shlex.split(command)
        process = subprocess.Popen(
            args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, startupinfo=get_startup_info(main.os_type)
        )
        stdout, stderr = process.communicate()
        stdout_decoded = stdout.decode("utf-8")
        stderr_decoded = stderr.decode("utf-8")
        if stdout_decoded.strip():
            print(stdout_decoded)
        if stderr_decoded.strip():
            print(stderr_decoded)
    except PermissionError as e:
        logger.error(e)
        logger.error("脚本无执行权限!, 若是Linux环境, 请先执行:chmod +x your_script.sh 授予脚本可执行权限")
    except OSError as e:
        logger.error(e)
        logger.error("Please add `#!/bin/bash` at the beginning of your bash script file.")
    except ValueError as e:
        logger.error(f"脚本命令解析失败: {e}")


# 线程安全记录一次错误：累计计数 error_count 加一，并向错误率窗口追加样本 1；无入参无返回值
def record_error(key: str | None = None) -> None:
    # 线程安全地记录一次错误：递增计数并追加 1 到滑动窗口（deque maxlen 自动裁剪）；
    # 同时上报给并发调度器（按 key 驱动熔断与全局背压）。key 为可选（直播间 host），
    # 缺省时仅维护全局错误窗口（保持无参调用以兼容既有调用方与测试）。
    with main.max_request_lock:
        main.error_count += 1
        main.error_window.append(1)
    scheduler = getattr(main, "scheduler", None)
    if scheduler is not None:
        scheduler.record_failure(key)


# 线程安全记录一次成功的检测周期：向错误率窗口追加样本 0；无入参无返回值
def record_success(key: str | None = None) -> None:
    # 线程安全地记录一次成功完成的检测周期（追加 0），与 record_error 的 1 混合采样，
    # 使 error_window 反映真实错误率（此前只记 1 导致错误率恒为 1.0，并发只能降不能升）；
    # 同时上报给并发调度器。保持无参调用以兼容既有调用方与测试。
    with main.max_request_lock:
        main.error_window.append(0)
    scheduler = getattr(main, "scheduler", None)
    if scheduler is not None:
        scheduler.record_success(key)


# 守护线程主体：委托给并发调度器的自适应调速循环；无入参，死循环不返回
def adjust_max_request() -> None:
    # 并发调速改为由 ConcurrencyScheduler.adjust_loop 负责：自适应全局容量 + per-key 熔断。
    # 保留函数名以兼容 main 的守护线程启动调用；调度器就绪前先等待。
    while main.scheduler is None:
        time.sleep(1)
    main.scheduler.adjust_loop()


# 清理 record_name 的录制状态；若 record_url 已被注释则从运行列表移除并把监控计数减一；无返回值
def clear_record_info(record_name: str, record_url: str) -> None:
    # 清理录制状态信息
    with main.record_state_lock:
        main.recording.discard(record_name)
        # 清理录制时间记录，防止长期运行内存无界增长
        main.recording_time_list.pop(record_name, None)
        if record_url in main.url_comments and record_url in main.running_list:
            main.running_list.remove(record_url)
            main.monitoring -= 1
            main.color_obj.print_colored(f"[{record_name}]已经从录制列表中移除\n", main.color_obj.YELLOW)
