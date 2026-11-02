#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import io
import os
import re
import sys
import threading
from datetime import datetime, timedelta
from typing import TextIO

import i18n
from src.config_bool import parse_config_bool  # 唯一布尔入口；config_bool 零依赖，不会与本模块的依赖链成环
from src.danmaku_monitor import close_monitor_file, resume_monitor_writes, suspend_monitor_writes
from src.logger import GUI_PARENT_ENV, add_file_sinks, logger, rebind_console_sink, remove_file_sinks, script_path

# 运行日志归档模块：停止录制流程（手动停止 / 异常或中断退出）统一调用的收尾步骤，
# 将四个运行时日志按「原文件名_YYYYMMDD_HHMMSS.扩展名」改名归档（目标已存在时追加 _N 序号）：
# - logs/streamget.log          loguru DEBUG 文件 sink（录制进程）
# - logs/PlayURL.log            loguru INFO 文件 sink（录制进程）
# - logs/danmaku_monitor.jsonl  弹幕监控枢纽自管的边车文件
# - logs/web_console.log        web.py 后台模式重定向的 sys.stdout/sys.stderr
#
# Windows 下句柄未关闭的文件 rename 会抛 PermissionError（WinError 32），故改名前先 flush 并关闭
# 对应句柄：loguru 文件 sink 经 logger.remove()（先 flush enqueue 队列再关文件）、边车文件经
# DanmakuMonitorHub.close_file()、web_console 经流对象自身 flush+close()。
# 归档全程不抛异常：单文件失败（如句柄被第三方进程占用）仅告警跳过，绝不中断停止录制流程；
# 归档后日志链路立即恢复（loguru 重新 add 即创建全新同名文件）。
#
# 三条已知失败形态（细则见对应函数注释）：弹幕边车改名期间必须套「归档窗口抑制」
# （suspend_monitor_writes / resume_monitor_writes），否则延迟事件会把句柄抢回来、改名必抛
# PermissionError；web_console 改名后重开失败时回退 os.devnull 并置 pending 标记；web_console
# 改名前先由 _ConsoleBridge 接管 sys.stdout/sys.stderr，关旧句柄与改名全程标准流都指向可写对象。
#
# 归档之后还有一步裁剪：见 _prune_archives 的保留策略与三条硬约束——
# 每个基名只留最新若干份、且删除文件名时间戳已超龄的份，排序取文件名里的 %Y%m%d_%H%M%S 而非 mtime。


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

# web_console.log 句柄重建失败的一次性标记：置位 = 改名后重开失败、sys.stdout/sys.stderr 正落在
# os.devnull 黑洞上。devnull 的 name 不匹配 _streams_bound_to() 的判定，下一轮归档会认为「没有绑定
# 本文件的标准流」从而永不重开，一次失败即把整个进程剩余生命周期的控制台输出丢进黑洞；故必须显式
# 记这一位，_archive_web_console 每轮开头/结尾各再试一次，重开成功即清零。只在 _archive_lock 内读写。
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


# 归档窗口内的 sys.stdout/sys.stderr 替身。旧实现是「flush+close 指向 web_console.log 的旧句柄
# → os.rename → 重建句柄」，而 sys.stdout/sys.stderr 在整个改名+重建期间**仍指向那个已关闭对象**，
# 其它线程（Web 请求线程的 print、录后脚本输出、loguru 的错误回显）在这段窗口里 print() 即抛
# ValueError: I/O operation on closed file；Windows 慢盘/杀软扫描会把窗口从微秒放大到秒级。
# 「先建新句柄接管标准流、再关旧流并改名」在本平台走不通：改名要求该路径上**一个句柄都不剩**——
# 2026-10-18 本机实测，同进程还持有 web_console.log 的追加句柄时 os.rename 直接 PermissionError
# [WinError 32]，关掉后才成功（这正是本模块「先关后改」存在的理由，见文件头注释）。新句柄只能等
# 改名之后再建，故改为「替身接管标准流 → 关旧句柄 → 改名 → 建真实新句柄，再把窗口期内容并入」。
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


# 第一步：用替身接管标准流，并把 loguru 控制台 sink 一并改绑到它。
# 控制台 sink 也要跟着换，是因为它在 add() 时绑定的就是那个旧句柄对象（loguru 不随 sys.stderr
# 被替换而改道，见 src/logger.py::rebind_console_sink 的说明）；不改绑则窗口期内每条记录都往
# 已关闭句柄写，被 loguru 的 catch 兜成一串「Logging error in Loguru Handler」噪声。
# remove() 会先把 enqueue 队列刷进旧句柄再关闭 worker，此刻旧句柄尚未关闭，不会丢行。
def _install_console_bridge() -> _ConsoleBridge:
    bridge = _ConsoleBridge()
    sys.stdout = bridge
    sys.stderr = bridge
    rebind_console_sink()
    return bridge


# 收尾：把替身期间缓存的输出并入新句柄。这些行本该落在被归档的那份文件里，与其丢弃不如追加到
# 全新同名文件的开头——对调用方而言归档链路依然「一条都没少」。仅在标准流已交回真实句柄
# （_rebind_web_console 之后）时调用；`is not bridge` 守卫兜住「连 os.devnull 都打不开、标准流仍留在
# 替身上」的绝境分支，必须在 take() **之前**判掉，否则会把唯一可写的兜底对象掏空。
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
        # 这里绝不能只告警后 return。_archive_web_console 在改名前已经把指向该文件的原句柄
        # flush+close 掉，而 sys.stdout/sys.stderr 仍指向那个**已关闭对象**，于是本进程剩余生命周期
        # 的每一次 print() 都抛 ValueError: I/O operation on closed file（表现为「点一次停止录制之后
        # 随机崩、Web 面板日志从此不再更新」）。回退到 os.devnull 保证标准流一定可写，控制台 sink
        # 照常重建（写丢弃但不抛），同时置位 pending，由下一轮归档继续尝试把链路接回真实文件。
        # [历史注] 上段「标准流仍指向已关闭对象」是旧顺序（先关句柄→改名→重建）下的事实；现在
        # 改名前先用 _ConsoleBridge 接管了标准流，本回退兜的是「重开失败后标准流无处可去」这一半。
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
# 改名后立即重建句柄，后续输出写往全新同名文件，避免线程向已关闭句柄写入；文件存在但未绑定
# 标准流（历史遗留）时仅改名、绝不劫持当前 stdout。接管顺序：替身接管标准流 → 关旧句柄 → 改名 →
# 真实新句柄接管 + 并入窗口期缓存；「改名前必须先把该路径上的句柄一个不剩地关掉」这条平台约束没变。
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
        # 先用替身接管标准流（含 loguru 控制台 sink），**之后**才允许关旧句柄——旧顺序（先关后改名、
        # 改名后才重建）让 sys.stdout/stderr 在整个改名+重建期间指向已关闭对象。无绑定句柄的遗留
        # 文件（bound 为空）不需要也不允许接管：那条路径绝不劫持当前 stdout。
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


# 归档保留策略。为什么必须清理：「停止录制」在 7×24 循环监测下每天会发生数十次（面板停止、
# GUI 停止、atexit 退出各触发一轮），logs/ 里每个基名下的 _YYYYMMDD_HHMMSS 归档此前只改名、
# 从不删除，磁盘占用完全由「启停次数」决定。
# 两条判据取并集删除：数量上限（每个基名各算各的）与时间上限。
_ARCHIVE_MAX_KEEP = 50
_ARCHIVE_MAX_AGE_DAYS = 14
# 归档名中段形态：YYYYMMDD_HHMMSS（可带 _N 冲突序号，见 _archive_target）。
# 排序一律用**文件名里的时间戳**而不是 mtime：mtime 会被「拷贝日志取证」「杀软扫描」
# 「同步工具保留时间戳」改写成与生成顺序相反的形态，按 mtime 保留最新 N 份会删掉真正最新的归档。
# 时间戳定宽 %Y%m%d_%H%M%S，故字典序即时间序，比较无需逐文件 strptime。
_ARCHIVE_TS_RE = re.compile(r"^(?P<ts>\d{8}_\d{6})(?:_(?P<seq>\d+))?$")


# 由「本轮归档时刻」算出保留窗口下界的时间戳字符串（定宽，可直接与归档名里的 ts 比大小）。
def _archive_cutoff_ts(now: datetime) -> str:
    return (now - timedelta(days=_ARCHIVE_MAX_AGE_DAYS)).strftime("%Y%m%d_%H%M%S")


# 裁剪 logs_dir 内每个基名的历史归档：删除「排在最新 _ARCHIVE_MAX_KEEP 份之外」或
# 「文件名时间戳早于 cutoff_ts」的份。硬约束三条：
# ① 只认 _ARCHIVE_TS_RE 能解析的名字，故活动日志本体（无时间戳的 streamget.log 等）与用户
#    自己放进 logs/ 的同名前缀文件一律不碰；
# ② 必须在**所有关句柄步骤之后**调用（见 archive_runtime_logs 内的接线注释）——Windows 下
#    仍被持有的文件 os.remove 直接抛 PermissionError(WinError 32)，那只会把「无界增长」换成
#    「一半删不掉 + 一堆告警」；
# ③ 任何失败（单个删除、整个目录列举、意外的解析问题）一律留痕后继续，绝不向调用方抛异常。
# 两处刻意不做：
# · 不打「本轮删了 N 份」的成功日志——本轮约束是不新增 i18n msgid，现有四目录里没有语义正确的
#   清理文案；待办：新增「运行日志归档已清理超量历史文件: {count} 份」并同步四目录 + 重编 .mo 后
#   再补这条。删除失败仍可经下方 warning 归因。
# · 不给 web_console.log 加**写入侧**轮转——该文件被 web.py 与本模块当作一只普通文件流消费
#   （_streams_bound_to() 按 sys.stdout/sys.stderr 的 .name 认句柄，换流对象即认不出；loguru 的
#   rotation= 又不支持流对象 sink，换成路径型 sink 会让 print 与 loguru 各持一只句柄、改名必抛），
#   详见 web.py 注释；它的单轮体量由 web.py 的启动侧上限 _WEB_CONSOLE_MAX_BYTES 兜住，
#   本函数只负责它归档之后的历史份数。
def _prune_archives(logs_dir: str, cutoff_ts: str) -> None:
    try:
        try:
            names = os.listdir(logs_dir)
        except OSError as e:
            # 目录本身读不出（权限/被删）：本轮不清理即可，归档改名结果不受影响
            logger.debug(i18n.tr("运行日志归档失败(忽略): {type_name}: {e}", type_name=type(e).__name__, e=e))
            return
        for base_name in ARCHIVE_LOG_NAMES:
            stem, ext = os.path.splitext(base_name)
            prefix = f"{stem}_"
            archives: list[tuple[str, int, str]] = []
            for file_name in names:
                if not file_name.startswith(prefix) or not file_name.endswith(ext):
                    continue
                middle = file_name[len(prefix) : len(file_name) - len(ext)]
                matched = _ARCHIVE_TS_RE.match(middle)
                if matched is None:
                    continue
                archives.append(
                    (matched.group("ts"), int(matched.group("seq") or 0), os.path.join(logs_dir, file_name))
                )
            # 新→旧：同刻的 _N 冲突序号越大越新（_archive_target 的追加顺序）
            archives.sort(key=lambda item: (item[0], item[1]), reverse=True)
            for rank, (ts, _seq, path) in enumerate(archives):
                if rank < _ARCHIVE_MAX_KEEP and ts >= cutoff_ts:
                    continue
                try:
                    os.remove(path)
                except OSError as e:
                    # 复用既有「归档失败(跳过)」文案：删除失败同样属于「这一步没做成、流程继续」
                    logger.warning(
                        i18n.tr(
                            "日志归档失败(跳过): {name} - {type_name}: {e}",
                            name=os.path.basename(path),
                            type_name=type(e).__name__,
                            e=e,
                        )
                    )
    except Exception as e:
        # 清理是旁路收尾，任何意外（含替身/桩造成的属性缺失）都不得影响归档本身
        logger.debug(i18n.tr("运行日志归档失败(忽略): {type_name}: {e}", type_name=type(e).__name__, e=e))


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
            # 两处布尔判定走 parse_config_bool（口径同 src/logger.py）：手写 `in ("1","true","yes")`
            # / `== "1"` 认不出 on/TRUE 等取值——开发者用 DOUYIN_DISABLE_LOG_ARCHIVE=on 关闭归档时，
            # pytest 退出仍会改名工作副本里的真实日志；DLR_GUI_PARENT=TRUE 时 GUI 进程照样参与归档。
            # 缺省（env 未设）仍为 False——两条守卫的默认行为逐字不变。
            if parse_config_bool(os.environ.get(_DISABLE_ENV), False):
                return []
            if parse_config_bool(os.environ.get(GUI_PARENT_ENV), False):
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

            # 弹幕监控边车文件：进入归档窗口——先置位抑制标记再关句柄，窗口内「已入队」与「新到达」
            # 的事件一律丢弃、不重开句柄。旧实现只 close 一次，之后任何一条延迟事件（最长 120s 仍在推）
            # 都会经写线程的惰性重开重新持有该文件，Windows 下改名必抛 PermissionError。
            suspend_monitor_writes()
            try:
                close_monitor_file()
                _rename_one(os.path.join(logs_dir, "danmaku_monitor.jsonl"), ts, archived)
            finally:
                # 改名成功或失败都要退出窗口：抑制只是为了争取一个「无人持有句柄」的改名窗口，
                # 留在抑制态会让 GUI 监控页与 Web 弹幕面板永久停更。
                resume_monitor_writes()

            # 超量历史归档的裁剪。接线位置是硬约束——必须在上面**全部**关句柄步骤
            # （remove_file_sinks / 边车 close_monitor_file / web_console 的 flush+close）之后、
            # 且早于 add_file_sinks() 重新开句柄之前：此刻 logs/ 内本进程一个句柄都不持有，
            # os.remove 才不会因为 WinError 32 失败。清理失败只留痕，不影响本轮归档结果。
            _prune_archives(logs_dir, _archive_cutoff_ts(datetime.now()))

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
