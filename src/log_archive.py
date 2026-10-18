#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import io
import os
import sys
import threading
from datetime import datetime
from typing import TextIO

import i18n
from src.danmaku_monitor import close_monitor_file, resume_monitor_writes, suspend_monitor_writes
from src.logger import (
    GUI_PARENT_ENV,
    add_file_sinks,
    logger,
    rebind_console_sink,
    remove_file_sinks,
    script_path,
)

# 运行日志归档模块：停止录制流程（手动停止 / 异常或中断退出）统一调用的收尾步骤，
# 将四个运行时日志按「原文件名_YYYYMMDD_HHMMSS.扩展名」改名归档（目标已存在时追加 _N 序号）：
# - logs/streamget.log          loguru DEBUG 文件 sink（录制进程）
# - logs/PlayURL.log            loguru INFO 文件 sink（录制进程）
# - logs/danmaku_monitor.jsonl  弹幕监控枢纽自管的边车文件
# - logs/web_console.log        web.py 后台模式重定向的 sys.stdout/sys.stderr
#
# Windows 下句柄未关闭的文件 rename 会抛 PermissionError（WinError 32），故改名前先
# flush 并关闭对应句柄：loguru 文件 sink 经 logger.remove()（先 flush enqueue 队列再关文件）、
# 边车文件经 DanmakuMonitorHub.close_file()、web_console 经流对象自身 flush+close()。
# 归档全程不抛异常：单文件失败（如句柄被第三方进程占用）仅告警跳过，绝不中断停止录制流程；
# 归档后日志链路立即恢复（loguru 重新 add 即创建全新同名文件），不影响现有日志写入逻辑。
#
# 三条已知失败形态（各自的细则见对应函数注释；前两条 2026-09-22 补，第三条 2026-10-18 补）：
# - MID-2243：弹幕边车改名期间套一层「归档窗口抑制」（suspend_monitor_writes /
#   resume_monitor_writes），否则延迟事件会把句柄抢回来、改名必然抛 PermissionError；
# - MID-2258：web_console 改名后重开失败时回退到 os.devnull 并置 pending 标记，
#   既不能让 print() 往已关闭对象上写，也要保证下一轮归档会把链路接回真实文件。
# - M-09（2026-10-18）：web_console 改名前先由 _ConsoleBridge 接管 sys.stdout/sys.stderr，
#   关旧句柄与改名全程标准流都指向一个可写对象——旧顺序下「窗口期内其它线程 print() 即抛
#   ValueError」的中间态被整体消掉，窗口期的行缓存后并入新文件（判据与实测见 _ConsoleBridge）。


# 参与归档的运行日志文件名（logs 目录下固定 ASCII 名，不含空格与非法字符）
ARCHIVE_LOG_NAMES: tuple[str, str, str, str] = (
    "streamget.log",
    "PlayURL.log",
    "danmaku_monitor.jsonl",
    "web_console.log",
)

# 归档禁用开关：测试进程（tests/conftest.py 设置）会导入 main 并注册归档 atexit，
# 但 pytest 退出并非「停止录制」事件，不得改名开发者工作副本里的真实日志。
_DISABLE_ENV = "DOUYIN_DISABLE_LOG_ARCHIVE"

# 归档串行锁：Web 面板停止与进程退出（atexit）可能并发触发，避免同一文件被重复处理
_archive_lock = threading.Lock()

# web_console.log 句柄重建失败的一次性标记（MID-2258）：置位 = 改名后重开失败、sys.stdout/sys.stderr
# 正落在 os.devnull 黑洞上。必须显式记这一位而非「等下次自然恢复」——devnull 的 name 不匹配
# _streams_bound_to() 的判定，下一轮归档会认为「没有绑定本文件的标准流」从而永不重开，一次失败即把
# 整个进程剩余生命周期的控制台输出丢进黑洞。有本标记后 _archive_web_console 每轮开头/结尾各再试一次，
# 重开成功即清零；只在 _archive_lock 内读写，无需额外同步。
_web_console_rebind_pending = False


# 生成归档目标路径：原名_YYYYMMDD_HHMMSS.扩展名；目标已存在时依次追加 _1/_2 序号避免覆盖。
def _archive_target(src_path: str, ts: str) -> str:
    dir_name, file_name = os.path.split(src_path)
    stem, ext = os.path.splitext(file_name)
    candidate = os.path.join(dir_name, f"{stem}_{ts}{ext}")
    seq = 1
    while os.path.exists(candidate):
        candidate = os.path.join(dir_name, f"{stem}_{ts}_{seq}{ext}")
        seq += 1
    return candidate


# 收集 sys.stdout/sys.stderr 中指向指定文件的活动句柄（web.py 后台模式两者为同一对象，去重）。
def _streams_bound_to(path: str) -> list[TextIO]:
    bound: list[TextIO] = []
    for stream in (sys.stdout, sys.stderr):
        if stream is None or any(stream is existing for existing in bound):
            continue
        name = getattr(stream, "name", None)
        if isinstance(name, str) and os.path.abspath(name) == os.path.abspath(path):
            bound.append(stream)
    return bound


# 归档窗口内标准流替身的缓冲上限（字符数）。窗口正常只有毫秒级、几十行，设上限只为
# 「改名被杀软扫描/慢盘拖成秒级且各线程持续输出」的极端形态兜底：超限后丢弃新写入
# （宁可丢几行控制台输出，也不无界吃内存），已缓存部分照常并入新文件。
_BRIDGE_BUFFER_LIMIT = 65536


# 归档窗口内的 sys.stdout/sys.stderr 替身（M-09，2026-10-18）。
# 为什么需要它：旧实现是「flush+close 指向 web_console.log 的旧句柄 → os.rename → 重建句柄」，
# 而 sys.stdout/sys.stderr 在整个改名+重建期间**仍指向那个已关闭对象**，其它线程（Web 请求线程
# 的 print、录后脚本输出、loguru 的错误回显）在这段窗口里 print() 即抛
# ValueError: I/O operation on closed file；Windows 慢盘/杀软扫描会把窗口从微秒放大到秒级。
# 审查建议的「先建新句柄接管标准流、再关旧流并改名」在本平台走不通：改名要求该路径上
# **一个句柄都不剩**——2026-10-18 本机实测，同进程还持有 web_console.log 的追加句柄时
# os.rename 直接 PermissionError [WinError 32]，关掉后才成功（这正是本模块「先关后改」存在的理由，
# 见文件头注释）。新句柄只能等改名之后再建。
# 故改为「先用替身接管标准流 → 关旧句柄 → 改名 → 建真实新句柄，再把窗口期内容并入」：
# 窗口内标准流始终指向一个可写对象，print() 不抛，落进来的行也不丢（缓存到上限）。
class _ConsoleBridge(io.TextIOBase):
    def __init__(self) -> None:
        super().__init__()
        self._chunks: list[str] = []
        self._size = 0
        self._dropped = 0
        self._buf_lock = threading.Lock()

    # 替身不对应任何文件路径，且该 name 必须与 logs/web_console.log 不同：
    # _streams_bound_to() 按 abspath 比对 sys.stdout/sys.stderr，给出一个「像文件名」的 name
    # 会让下一轮归档把这个内存对象当成绑定本文件的活动句柄去 flush+close。
    @property
    def name(self) -> str:
        return "<dlr-log-archive-bridge>"

    # 必须显式覆写：io.TextIOBase 的 writable() 默认返回 False，
    # 而消费方（web.py 的 print 路径、第三方库）会先问一句 writable 再写。
    def writable(self) -> bool:
        return True

    # 恒 False：替身不是终端。src/logger.py 的 _console_colorize() 走同样的 isatty 口径，
    # 若这里返回 True，归档窗口内的日志会带 ANSI 转义序列被缓存进新文件。
    def isatty(self) -> bool:
        return False

    def write(self, text: str) -> int:
        # 返回值一律是 len(text)：报短会被 print()/loguru 当成写失败再抛一次，
        # 而「不抛」正是本替身存在的唯一目的
        with self._buf_lock:
            if self._size < _BRIDGE_BUFFER_LIMIT:
                self._chunks.append(text)
                self._size += len(text)
            else:
                self._dropped += 1
        return len(text)

    def flush(self) -> None:
        # 内存对象无系统缓冲可刷；print(flush=True) 与 src/recorder_status.py 的
        # sys.stdout.flush() 都会走到这里，必须是 no-op 而不是抛错
        return None

    # 取出窗口期内缓存的全部输出（取出即清空）。只应在标准流已交回真实句柄后调用。
    def take(self) -> str:
        with self._buf_lock:
            content = "".join(self._chunks)
            self._chunks.clear()
            self._size = 0
        return content


# 第一步（M-09）：用替身接管标准流，并把 loguru 控制台 sink 一并改绑到它。
# 控制台 sink 也要跟着换，是因为它在 add() 时绑定的就是那个旧句柄对象（loguru 不随
# sys.stderr 被替换而改道，见 src/logger.py::rebind_console_sink 的说明）；不改绑则窗口期内
# 每条记录都往已关闭句柄写，被 loguru 的 catch 兜成一串「Logging error in Loguru Handler」噪声。
# remove() 会先把 enqueue 队列刷进旧句柄再关闭 worker，此刻旧句柄尚未关闭，不会丢行。
def _install_console_bridge() -> _ConsoleBridge:
    bridge = _ConsoleBridge()
    sys.stdout = bridge
    sys.stderr = bridge
    rebind_console_sink()
    return bridge


# 收尾（M-09）：把替身期间缓存的输出并入新句柄。这些行本该落在被归档的那份文件里，
# 与其丢弃不如追加到全新同名文件的开头——对调用方而言归档链路依然「一条都没少」。
# 仅在标准流已交回真实句柄（_rebind_web_console 之后）时调用；此时 bridge 不再是 sys.stdout，
# 那个 `is not bridge` 守卫用来兜住「连 os.devnull 都打不开、标准流仍留在替身上」的绝境分支：
# 守卫必须在 take() **之前**判掉，否则会把唯一可写的兜底对象掏空。
def _merge_bridge_output(bridge: _ConsoleBridge | None) -> None:
    if bridge is None:
        return
    stream = sys.stdout
    if stream is None or stream is bridge:
        return
    try:
        content = bridge.take()
        if content:
            stream.write(content)
    except Exception:
        # 吞没即正确：这一步只是补写窗口期缓存，失败（磁盘满等）意味着新句柄本身也已不可写，
        # 那件事由 _rebind_web_console 与本模块的归档告警交代，这里不重复留痕也不外抛
        pass


# 重建 web_console.log 句柄并重新接管 sys.stdout/sys.stderr 与 loguru 控制台 sink
# （与 web.py::_enter_background_mode 同参数：追加写 + 行缓冲，保证后台日志实时落盘）。
def _rebind_web_console(path: str) -> None:
    global _web_console_rebind_pending
    try:
        stream = open(path, "a", encoding="utf-8", buffering=1)
        _web_console_rebind_pending = False
    except OSError as e:
        logger.warning(i18n.tr("重建 web_console.log 句柄失败: {type_name}: {e}", type_name=type(e).__name__, e=e))
        # MID-2258：这里绝不能只告警后 return。_archive_web_console 在改名前已经把指向该
        # 文件的原句柄 flush+close 掉，而 sys.stdout/sys.stderr 仍指向那个**已关闭对象**，
        # 于是本进程剩余生命周期的每一次 print() 都抛 ValueError: I/O operation on closed
        # file（表现为「点一次停止录制之后随机崩、Web 面板日志从此不再更新」）。
        # 回退到 os.devnull 保证标准流一定可写，控制台 sink 照常重建（写丢弃但不抛），
        # 同时置位 pending，由下一轮归档继续尝试把链路接回真实文件。
        # [历史注 M-09，2026-10-18] 上段「标准流仍指向已关闭对象」是旧顺序（先关句柄→改名→重建）
        # 下的事实；现在改名前先用 _ConsoleBridge 接管了标准流，该形态不再无条件成立，本回退兜的是
        # 「重开失败后标准流无处可去」这一半——不回退就会把内存替身永久留在 sys.stdout 上。
        _web_console_rebind_pending = True
        try:
            stream = open(os.devnull, "w", encoding="utf-8")
        except OSError as e2:
            # 连 os.devnull 都打不开只可能是 fd/句柄耗尽这类进程级绝境，此时任何回退手段
            # 同样会失败。留一条 error 线索并保留当前标准流，不再叠加第二次异常。
            logger.error(i18n.tr("回退到 os.devnull 也失败: {type_name}: {e}", type_name=type(e2).__name__, e=e2))
            return
    sys.stdout = stream
    sys.stderr = stream
    rebind_console_sink()


# 归档 web_console.log（仅 Web 后台模式下被重定向为 sys.stdout/sys.stderr、且为同一对象）。
# 改名后立即重建句柄，后续输出写往全新同名文件，避免线程向已关闭句柄写入；
# 文件存在但未绑定标准流（历史遗留）时仅改名、绝不劫持当前 stdout。
# M-09 接管顺序（2026-10-18）：替身接管标准流 → 关旧句柄 → 改名 → 真实新句柄接管 + 并入窗口期缓存；
# 「改名前必须先把该路径上的句柄一个不剩地关掉」这条平台约束没变，变的是关句柄前标准流去了哪里。
def _archive_web_console(logs_dir: str, ts: str, archived: list[str]) -> None:
    path = os.path.join(logs_dir, "web_console.log")
    if _web_console_rebind_pending and not os.path.isfile(path):
        # 上一轮重开失败（标准流还写在 devnull 黑洞上）且此刻原文件也不存在：
        # 本轮只负责把链路接回来，不产生归档条目——刚 open 出来的空文件不该被改名。
        _rebind_web_console(path)
        return
    if not os.path.isfile(path):
        return
    bound = _streams_bound_to(path)
    bridge: _ConsoleBridge | None = None
    if bound:
        # M-09：先用替身接管标准流（含 loguru 控制台 sink），**之后**才允许关旧句柄——
        # 旧顺序（先关后改名、改名后才重建）让 sys.stdout/stderr 在整个改名+重建期间指向已关闭对象。
        # 无绑定句柄的遗留文件（bound 为空）不需要也不允许接管：那条路径绝不劫持当前 stdout。
        bridge = _install_console_bridge()
    for stream in bound:
        try:
            stream.flush()
            stream.close()
        except Exception as e:
            logger.debug(i18n.tr("关闭 web_console 句柄异常(忽略): {type_name}: {e}", type_name=type(e).__name__, e=e))
    try:
        target = _archive_target(path, ts)
        os.rename(path, target)
        archived.append(target)
    except OSError as e:
        # 改名失败（句柄被第三方进程占用等）：跳过归档，并重建原路径句柄保证输出链路不断
        logger.warning(
            i18n.tr("日志归档失败(跳过): web_console.log - {type_name}: {e}", type_name=type(e).__name__, e=e)
        )
        if bound or _web_console_rebind_pending:
            _rebind_web_console(path)
            _merge_bridge_output(bridge)
        return
    if bound or _web_console_rebind_pending:
        # 除「标准流确实被我们关过」外，额外允许 pending 分支：上一轮重开失败时标准流落在
        # devnull 上、_streams_bound_to 匹配不到本文件，此处若不重建就成了永久黑洞。
        _rebind_web_console(path)
        _merge_bridge_output(bridge)


# 单文件归档：文件不存在则跳过；改名失败仅告警（Windows 下句柄被第三方进程占用时会发生），
# 绝不向调用方抛异常——归档是停止录制流程的旁路收尾步骤。
def _rename_one(path: str, ts: str, archived: list[str]) -> None:
    name = os.path.basename(path)
    try:
        if not os.path.isfile(path):
            return
        target = _archive_target(path, ts)
        os.rename(path, target)
        archived.append(target)
        logger.debug(i18n.tr("日志已归档: {name} -> {target}", name=name, target=os.path.basename(target)))
    except OSError as e:
        logger.warning(
            i18n.tr("日志归档失败(跳过): {name} - {type_name}: {e}", name=name, type_name=type(e).__name__, e=e)
        )


# 停止录制流程的日志归档入口：flush/关闭四个运行日志的句柄后，按停止操作发生时刻的
# 本机时间戳逐个改名。reopen_streams=True（Web 面板停止等进程继续运行场景）时在改名后
# 重建 loguru 文件 sink，日志写入立即恢复到全新同名文件；False（atexit 等进程退出场景，
# 由调用方显式传参）仅关闭+改名，下次启动时经导入期注册自然重建。
# 返回成功归档的新路径列表（仅供日志/测试观察，流程不依赖返回值）；本函数绝不抛异常。
def archive_runtime_logs(*, reopen_streams: bool = True) -> list[str]:
    try:
        with _archive_lock:
            # 测试进程禁用（见 _DISABLE_ENV 注释）；GUI 父进程不持有录制日志句柄，
            # 也绝不能改名录制子进程正在写的日志文件
            if os.environ.get(_DISABLE_ENV, "").strip().lower() in ("1", "true", "yes"):
                return []
            if os.environ.get(GUI_PARENT_ENV) == "1":
                return []
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            logs_dir = os.path.join(script_path, "logs")
            archived: list[str] = []

            # web_console.log 最先处理：其句柄是 sys.stdout/sys.stderr，改名后须立即重建，
            # 使归档过程自身后续的日志输出有正常去处
            _archive_web_console(logs_dir, ts, archived)

            # loguru 文件 sink：remove() 先 flush enqueue 队列并关闭句柄（幂等），再改名
            remove_file_sinks()
            _rename_one(os.path.join(logs_dir, "streamget.log"), ts, archived)
            _rename_one(os.path.join(logs_dir, "PlayURL.log"), ts, archived)

            # 弹幕监控边车文件：进入归档窗口（MID-2243）——先置位抑制标记再关句柄，
            # 窗口内「已入队」与「新到达」的事件一律丢弃、不重开句柄。旧实现只 close 一次，
            # 之后任何一条延迟事件（delay_default 最长 120s 仍在推）都会经写线程的惰性重开
            # 重新持有该文件，Windows 下改名必抛 PermissionError，于是这个文件基本永不归档。
            suspend_monitor_writes()
            try:
                close_monitor_file()
                _rename_one(os.path.join(logs_dir, "danmaku_monitor.jsonl"), ts, archived)
            finally:
                # 改名成功或失败都要退出窗口：抑制只是为了争取一个「无人持有句柄」的改名窗口，
                # 留在抑制态会让 GUI 监控页与 Web 弹幕面板永久停更。
                resume_monitor_writes()

            if reopen_streams:
                # 进程继续运行：重新注册文件 sink，loguru add() 即创建全新同名文件
                add_file_sinks()

            if archived:
                logger.info(
                    i18n.tr("运行日志已归档: {archived}", archived="、".join(os.path.basename(p) for p in archived))
                )
            return archived
    except Exception as e:
        # 归档失败绝不允许影响停止录制本身：任何意外仅告警并返回空列表
        try:
            logger.warning(i18n.tr("运行日志归档失败(忽略): {type_name}: {e}", type_name=type(e).__name__, e=e))
        except Exception:
            pass
        return []
