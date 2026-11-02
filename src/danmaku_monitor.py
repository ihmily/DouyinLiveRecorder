# -*- coding: utf-8 -*-
# 弹幕监控枢纽：进程级单例，汇总各直播间弹幕采集器上报的实时事件。
# 两类消费方：Web API（与录制引擎同进程，直接读内存快照：统计 + 增量消息游标）；
# GUI（子进程跑录制引擎，tail 边车文件 logs/danmaku_monitor.jsonl）。
#
# 设计约束：
# - 所有公开方法异常全吞、只记 debug 日志——弹幕监控是旁路功能，任何失败都绝不允许影响录制主流程；
# - 「统计精确、流式采样」：计数器（累计弹幕/礼物/速率桶）对每条消息都累加，但消息展示流（内存环形
#   缓冲与 JSONL）按每房间每秒采样上限输出，超出部分折叠为下一事件上的 dropped 计数，保证高频房间下
#   UI 与文件体积有界；GIFT / SUPER_CHAT / 连接事件为低频事件，不参与采样。
from __future__ import annotations

import json
import os
import queue
import threading
import time
from collections import deque
from typing import Any, Optional, TextIO

import i18n
from src.logger import logger, script_path

# 消息展示流采样上限（条/秒/房间）：仅约束展示流，统计计数不受影响
_STREAM_SAMPLE_PER_SEC = 10
# 内存侧近期消息环形缓冲条数（全局，供 Web 增量拉取）
_RECENT_BUFFER_SIZE = 500
# 单次 snapshot 返回的最大消息条数（超出取最新并标记 truncated）
_MAX_MESSAGES_PER_RESPONSE = 200
# JSONL 边车文件轮转阈值（字节）：超过后轮转为 .1 备份（仅保留一代）
_ROTATE_BYTES = 5 * 1024 * 1024
# stats 事件写入间隔（秒）：房间静默时 GUI 统计行也能周期性刷新
_STATS_INTERVAL = 5.0
# 弹幕速率窗口：10 秒一桶 × 6 桶 = 60 秒，窗口内计数之和即 条/分
_RATE_WINDOW_SEC = 60.0

# 边车落盘队列上限。80 房间 × 10 条/秒采样 ≈ 800 行/秒，每行约 150 字节，2 万条缓冲
# 可吸收约 25 秒的极端慢盘抖动；超出即计数丢弃（丢弃必须可观测），与 collector 侧 SRT 队列同口径。
_SIDECAR_QUEUE_MAXSIZE = 20000
# 等待落盘队列排空的上限（秒）。close_file() 由日志归档在改名前调用——Windows 下句柄未关的文件
# rename 必抛 PermissionError，故必须等真正写完；超时只告警降级（慢盘/网络盘掉线时归档跳过该文件），
# 绝不无限阻塞停止流程。
_SIDECAR_DRAIN_SECONDS = 5.0

# 边车轮转失败的退避周期（秒）：`.1` 备份被第三方进程占用 / 目标跨卷时 os.replace 必失败，
# 而失败后仍以追加模式重开、fh.tell() 依旧 >= _ROTATE_BYTES，于是**此后每一条**事件都会重走一遍
# 必败的 close → replace → open（最后写入循环与每秒采样叠加下即每秒数百次）。现按路径记一个退避窗口：
# 期内直接跳过轮转、照常追加。两条边界：① 这不是「把轮转关掉」——标记带过期时间，到期即回收并重试；
# ② 与归档链路无关——close_file() 的归档语义（排空 + 关句柄）逐字不变。
_ROTATE_RETRY_BACKOFF_SECONDS = 300.0


# ── 轮转退避记忆（按路径）──────────────────────────────────
_rotate_backoff_until: dict[str, float] = {}
_rotate_backoff_lock = threading.Lock()


# 该路径是否处于轮转退避期内；顺带回收已到期条目，避免字典随历史路径数无界增长。
def _rotate_in_backoff(path: str) -> bool:
    with _rotate_backoff_lock:
        until = _rotate_backoff_until.get(path)
        if until is None:
            return False
        if time.monotonic() >= until:
            _rotate_backoff_until.pop(path, None)
            return False
        return True


# 记一次轮转失败：置退避标记 + 留一条 warning（带异常类型与原文，用来区分「.1 被占用」与「跨卷」）。
# 限频不需要额外计数：退避期内根本不会再走到 replace，故两条 warning 间至少相隔一个退避周期。
# msgid 复用四目录既有的「[弹幕监控]{where} 处理失败(忽略)」模板（where=rotate 是标识符、不翻译）。
def _note_rotate_failure(path: str, err: OSError) -> None:
    with _rotate_backoff_lock:
        _rotate_backoff_until[path] = time.monotonic() + _ROTATE_RETRY_BACKOFF_SECONDS
    logger.warning(
        i18n.tr(
            "[弹幕监控]{where} 处理失败(忽略): {type_name}: {e}",
            where="rotate",
            type_name=type(err).__name__,
            e=err,
        )
    )


# ── JSONL 边车落盘（进程级单写线程）──────────────────
#
# room_message() 跑在**各房间自己的事件循环线程**上，旧实现在全局 _lock 内 open/write/flush：10 条/秒
# 每房间、80 房间即最高 800 次带 flush 的串行落盘/秒，任一次 flush 被慢盘/网络盘/杀毒扫描拖住 →
# 全房间 ws 收包与心跳协程一起停摆（协议层 ping 超时 → 断连 → 重连风暴），Web 的 snapshot() 也抢同
# 一把锁——与 collector「SRT 写盘必须挪到独立线程否则阻塞 ws_recv」同因。现锁内只剩统计 + payload 构造，
# 磁盘 IO 交下面这支守护线程（有界队列 + 丢弃计数）；句柄只被写线程读写，故 _files 无需加锁。
# close_file() = 入队一条 close 指令 + 等待队列排空（改名前必须关句柄，关闭后惰性重开）。
# 归档另有「抑制窗口」——suspend_writes()/resume_writes() 之间的 line 指令（含置位前就已
# 入队的）一律丢弃、不落句柄，改名窗口内不会再有人持有该文件；close_file() 本身语义不变。


# 把一行 JSON 追加到边车文件并按需轮转（保留一代 .1 备份）。独立成模块级函数是**给测试留的注入口**：
# 回归锁把它换成慢速写，以此证明「写盘期间不持有 hub._lock」。写失败静默重置该路径句柄，
# 下一条事件重新打开；轮转失败另按路径记退避窗口（见 _note_rotate_failure）。
def _append_sidecar_line(files: dict[str, TextIO], path: str, line: str) -> None:
    fh: Optional[TextIO] = None
    try:
        fh = files.get(path)
        if fh is None:
            fh = files[path] = open(path, "a", encoding="utf-8")
        # 轮转判定用当前句柄的真实大小，避免长期运行下误差累积；退避期内跳过轮转但**照常追加**，
        # 既不丢监控流也不把轮转永久关掉。
        if fh.tell() >= _ROTATE_BYTES and not _rotate_in_backoff(path):
            fh.close()
            files.pop(path, None)
            try:
                os.replace(path, path + ".1")
            except OSError as e:
                # 吞没即正确：轮转失败（.1 被占用 / 跨卷）只是没有备份，随后仍以追加模式继续写，
                # 绝不因一次改名失败丢掉整段监控流；另补退避标记 + warning。
                _note_rotate_failure(path, e)
            # 成功一侧不另设「清除标记」分支：能走到这里就说明 _rotate_in_backoff 已把过期条目弹出
            # （未过期根本进不来），字典此刻对本路径本就是空的，写清除等于留一条永不为真的死分支。
            fh = files[path] = open(path, "a", encoding="utf-8")
        fh.write(line + "\n")
        fh.flush()
    except Exception as e:
        # 与本模块「异常全吞但必须留痕」的约定一致：写失败记 debug（弹幕边车是旁路功能，绝不影响录制
        # 主流程，但不允许静默丢数据无迹可查）；msgid 复用目录既有条目。
        logger.debug(i18n.tr("弹幕边车文件写入失败: {type_name}: {e}", type_name=type(e).__name__, e=e))
        # 句柄可能已损坏：关闭置空，下一条事件重新打开
        try:
            if fh is not None:
                fh.close()
        except Exception:
            # 吞没即正确：句柄已处于不可用状态，关闭再失败也无从恢复
            pass
        files.pop(path, None)


# 关闭某路径的边车句柄（日志归档改名前调用）。
def _close_sidecar_handle(files: dict[str, TextIO], path: str) -> None:
    fh = files.pop(path, None)
    if fh is None:
        return
    try:
        fh.flush()
        fh.close()
    except Exception as e:
        logger.debug(i18n.tr("[弹幕监控]关闭边车文件异常(忽略): {type_name}: {e}", type_name=type(e).__name__, e=e))


# 边车单写线程：串行消费「追加一行 / 关闭句柄」两类指令，队列有界、满即计数丢弃。
class _SidecarWriter:
    # 指令载体为 (op, path, line)；op ∈ {"line", "close"}
    def __init__(self, maxsize: int = _SIDECAR_QUEUE_MAXSIZE) -> None:
        self._queue: "queue.Queue[tuple[str, str, str]]" = queue.Queue(maxsize=maxsize)
        self._files: dict[str, TextIO] = {}
        self._thread: Optional[threading.Thread] = None
        self._start_lock = threading.Lock()
        self._dropped = 0
        # 「未处理完的指令数」+ 条件变量：实现带超时的 join（queue.Queue.join() 无超时，
        # 而 close_file() 必须等待落盘完成后才能改名，见 _SIDECAR_DRAIN_SECONDS 的说明）
        self._cond = threading.Condition()
        self._outstanding = 0
        # 归档窗口抑制的路径集合。命中即「丢弃 line 指令、绝不重开句柄」，由独立小锁保护
        # （写线程每条指令读一次，成本可忽略）；_suppressed 是抑制期按路径的丢弃计数。
        self._suspended: set[str] = set()
        self._suspend_lock = threading.Lock()
        self._suppressed: dict[str, int] = {}

    # 进入归档窗口：置位该路径的抑制标记。置位后「已在队列中排队的 line 指令」与「此后新入队的
    # line 指令」都会被丢弃（见 submit 与 _loop 两处判定）。只置位、不关句柄——关闭与排空由调用方
    # 复用 close_file() 完成。丢弃计数按「本窗口」计：跨窗口累计会让第二个窗口一条都不报
    # （抑制是每轮停止录制都会进入的短窗口，不是进程级状态）。
    def suspend(self, path: str) -> None:
        with self._suspend_lock:
            self._suspended.add(path)
            self._suppressed.pop(path, None)

    # 退出归档窗口：解除抑制，下一条事件经写线程的惰性重开逻辑继续落盘。
    def resume(self, path: str) -> None:
        with self._suspend_lock:
            self._suspended.discard(path)
            self._suppressed.pop(path, None)

    # 该路径当前是否处于抑制期（供观测/断言）。
    def is_suspended(self, path: str) -> bool:
        with self._suspend_lock:
            return path in self._suspended

    # 入队一条指令；队列满时记丢弃计数并返回 False（调用方不得被阻塞）。
    def submit(self, op: str, path: str, line: str = "") -> bool:
        if op == "line" and self.is_suspended(path):
            # 抑制期内连队列都不进：否则 drain 返回后这些残留指令仍会把文件重新打开，
            # 正好是该失效形态（丢弃计数留痕，边车是旁路数据可接受）
            with self._suspend_lock:
                suppressed = self._suppressed.get(path, 0) + 1
                self._suppressed[path] = suppressed
            if suppressed == 1 or suppressed % 1000 == 0:
                logger.debug(i18n.tr("[弹幕监控]归档窗口内丢弃 {count} 条边车事件", count=suppressed))
            return False
        self._ensure_thread()
        with self._cond:
            try:
                self._queue.put_nowait((op, path, line))
            except queue.Full:
                self._dropped += 1
                if self._dropped == 1 or self._dropped % 1000 == 0:
                    logger.warning(i18n.tr("[弹幕监控]边车写入队列已满，累计丢弃 {count} 条事件", count=self._dropped))
                return False
            # 计数与入队必须在同一临界区：否则写线程可能先完成处理并递减，
            # 把 _outstanding 打成负数，drain() 从此永远等不到 0。
            self._outstanding += 1
        return True

    # 等待已入队的指令全部处理完（带超时）；返回是否排空。
    def drain(self, timeout: float = _SIDECAR_DRAIN_SECONDS) -> bool:
        with self._cond:
            return self._cond.wait_for(lambda: self._outstanding == 0, timeout)

    # 当前是否仍持有某路径的打开句柄（仅供观测/断言，不做 IO）。
    def open_handle(self, path: str) -> Optional[TextIO]:
        return self._files.get(path)

    # 惰性起线程；守护线程随进程结束回收，故无需显式 stop（drain 已覆盖需要落盘的时机）
    def _ensure_thread(self) -> None:
        with self._start_lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._thread = threading.Thread(target=self._loop, name="danmaku-monitor-sidecar", daemon=True)
            self._thread.start()

    # 写线程主体：任何单条指令异常都不得让线程退出（否则监控流永久静默断档）。
    def _loop(self) -> None:
        while True:
            op, path, line = self._queue.get()
            try:
                if op == "close":
                    _close_sidecar_handle(self._files, path)
                elif self.is_suspended(path):
                    # 抑制标记置位**之前**就已入队的 line 指令也必须丢弃——「close 之后不再重开句柄」
                    # 只能由这一处的显式判定保证，绝不能指望队列/调度时序（残留指令会经惰性重开
                    # 重新持有句柄）。计数与日志已在 submit() 侧完成，这里不重复留痕。
                    pass
                else:
                    _append_sidecar_line(self._files, path, line)
            except Exception as e:
                # 吞没即正确：两条指令函数各自已容错，这里只兜「替换实现/未知故障」，
                # 边车是旁路数据，任何失败都不允许杀死写线程本身。
                logger.debug(
                    i18n.tr(
                        "[弹幕监控]{where} 处理失败(忽略): {type_name}: {e}",
                        where="sidecar",
                        type_name=type(e).__name__,
                        e=e,
                    )
                )
            finally:
                with self._cond:
                    self._outstanding -= 1
                    self._cond.notify_all()


# 进程级唯一写线程（供所有 hub 实例共用，含测试里注入的临时路径 hub）
_sidecar: Optional[_SidecarWriter] = None
_sidecar_lock = threading.Lock()


def _get_sidecar() -> _SidecarWriter:
    global _sidecar
    with _sidecar_lock:
        if _sidecar is None:
            _sidecar = _SidecarWriter()
        return _sidecar


# 弹幕监控枢纽：线程安全地聚合各房间弹幕事件，维护统计与展示流。
class DanmakuMonitorHub:
    # 初始化枢纽。log_path 为 JSONL 边车文件路径，None 表示禁用文件输出
    # （仅供测试/无 GUI 消费方场景）；目录不可写时自动降级为禁用。
    def __init__(self, log_path: Optional[str] = None) -> None:
        self._lock = threading.Lock()
        # 磁盘句柄不再由本实例持有，改由进程级 _SidecarWriter 独占（见其注释）。
        # 原 self._file / self._file_lock 一并移交；_file 保留同名只读属性以兼容既有断言。
        self._log_path: Optional[str] = self._prepare_log_path(log_path)
        # 房间状态表：{room: {platform/connected/started_at/msg_total/gift_total/
        # online/msg_rate/last_msg_at + 采样与速率桶等内部字段（_ 前缀）}}
        self._rooms: dict[str, dict[str, Any]] = {}
        # 近期消息环形缓冲（含 seq，供 Web 增量拉取过滤）
        self._recent: deque[dict[str, Any]] = deque(maxlen=_RECENT_BUFFER_SIZE)
        self._seq = 0
        self._stats_thread: Optional[threading.Thread] = None
        self._stats_stop = threading.Event()

    # 本枢纽边车路径当前是否仍有打开句柄（写线程独占，这里只读它的登记表）。
    # 保留同名只读属性是为兼容既有断言（tests/test_log_archive.py 的 close_file → 惰性重开用例）。
    # **会先等待已入队指令落盘**：句柄是写线程异步打开的，不排空则观测结果不确定。
    # 仅供观测/测试，生产链路不读它，也不做任何 IO。
    @property
    def _file(self) -> Optional[TextIO]:
        if not self._log_path:
            return None
        _get_sidecar().drain()
        return _get_sidecar().open_handle(self._log_path)

    # 等待本枢纽已入队的边车指令全部落盘（带超时）；返回是否排空。
    # 写盘已在独立线程异步进行，同步读 JSONL 的调用方需先 flush 才能看到全部内容。
    def flush(self, timeout: float = _SIDECAR_DRAIN_SECONDS) -> bool:
        return _get_sidecar().drain(timeout)

    # ── 公开事件接口（全部容错，异常不影响录制） ──────────────

    # 房间开始采集（collector.start）：重置该房间统计并写 conn/started 事件。
    def room_started(self, room: str, platform: str) -> None:
        try:
            with self._lock:
                self._rooms[room] = self._default_state(platform)
                seq = self._next_seq()
                self._write_line(
                    {
                        "ev": "conn",
                        "seq": seq,
                        "room": room,
                        "platform": platform,
                        "state": "started",
                        "ts": time.time(),
                    }
                )
                self._ensure_stats_thread()
        except Exception as e:
            logger.debug(
                i18n.tr(
                    "[弹幕监控]{where} 处理失败(忽略): {type_name}: {e}",
                    where="room_started",
                    type_name=type(e).__name__,
                    e=e,
                )
            )

    # 弹幕连接就绪（collector.on_ready）：置连接状态并写 conn/ready 事件。
    def room_connected(self, room: str) -> None:
        try:
            with self._lock:
                state = self._rooms.get(room)
                if state is not None:
                    state["connected"] = True
                self._write_line(
                    {
                        "ev": "conn",
                        "seq": self._next_seq(),
                        "room": room,
                        "state": "ready",
                        "ts": time.time(),
                    }
                )
        except Exception as e:
            logger.debug(
                i18n.tr(
                    "[弹幕监控]{where} 处理失败(忽略): {type_name}: {e}",
                    where="room_connected",
                    type_name=type(e).__name__,
                    e=e,
                )
            )

    # 弹幕连接关闭（collector.on_close / stop）：清除连接状态并写 conn/closed 事件。
    def room_closed(self, room: str, reason: str = "") -> None:
        try:
            with self._lock:
                state = self._rooms.get(room)
                if state is not None:
                    state["connected"] = False
                self._write_line(
                    {
                        "ev": "conn",
                        "seq": self._next_seq(),
                        "room": room,
                        "state": "closed",
                        "reason": reason,
                        "ts": time.time(),
                    }
                )
        except Exception as e:
            logger.debug(
                i18n.tr(
                    "[弹幕监控]{where} 处理失败(忽略): {type_name}: {e}",
                    where="room_closed",
                    type_name=type(e).__name__,
                    e=e,
                )
            )

    # 房间停止监控（main.py 的录制线程在 outer try 的 finally 里调用，覆盖录制态/轮询态/解析失败态）：
    # 从房间表移除条目并写 conn/stopped 事件——窗口层 DanmakuMonitor 见 state=="stopped" 即 pop
    # 房间行，Web 快照随房间表自动消失；同房间重新录制时由 room_started 重新登记。
    # 条目必须删除：URL 被移除/注释后房间线程已退出，旧实现却让监控页一直残留失效直播间及其旧数据。
    def room_stopped(self, room: str, reason: Optional[str] = None) -> None:
        # 2026-10-02：默认文案改函数内 i18n.tr（原默认参数在 import 期求值一次，
        # 语言热切换后不更新；缺省 None + 函数内取值保证每次调用按当前语言解析）
        if reason is None:
            reason = i18n.tr("房间已停止监控")
        try:
            with self._lock:
                if self._rooms.pop(room, None) is None:
                    return  # 未注册过的房间不打事件
                self._write_line(
                    {
                        "ev": "conn",
                        "seq": self._next_seq(),
                        "room": room,
                        "state": "stopped",
                        "reason": reason,
                        "ts": time.time(),
                    }
                )
        except Exception as e:
            logger.debug(
                i18n.tr(
                    "[弹幕监控]{where} 处理失败(忽略): {type_name}: {e}",
                    where="room_stopped",
                    type_name=type(e).__name__,
                    e=e,
                )
            )

    # 收到一条弹幕消息（collector.on_message 转发，msg_type 取 DanmakuMessageType.value）。
    # chat 累计并按采样写入展示流；gift/superChat 计入礼物数且不采样直接入流；online 仅更新在线人数。
    # data 为可选的原始数值载荷（各平台把在线人数放在 DanmakuMessage.data，而 message 为空串）。
    def room_message(self, room: str, msg_type: str, user: str, text: str, data: Any = None) -> None:
        try:
            with self._lock:
                # 用 get 而非 setdefault：setdefault 的默认值实参会**先求值**——即使房间已存在，
                # 每条弹幕仍会白建一个 dict+deque 并多次调用 time。高刷新直播间下是热路径上的纯浪费。
                state = self._rooms.get(room)
                if state is None:
                    state = self._default_state("未知")
                    self._rooms[room] = state
                now = time.time()
                state["last_msg_at"] = now
                if msg_type == "chat":
                    state["msg_total"] = int(state["msg_total"]) + 1
                    self._bump_rate(state, now)
                    if self._allow_stream_sample(state):
                        self._emit_message(room, "chat", user, text)
                elif msg_type in ("gift", "superChat"):
                    state["gift_total"] = int(state["gift_total"]) + 1
                    # 礼物/SC 为低频高价值事件，不采样
                    self._emit_message(room, msg_type, user, text)
                elif msg_type == "online":
                    # WD-20：优先取平台放置在线人数的 data 字段；text 仅作字符串兜底
                    if isinstance(data, (int, float)):
                        state["online"] = int(data)
                    elif data is not None and str(data).strip().isdigit():
                        state["online"] = int(str(data).strip())
                    else:
                        state["online"] = self._parse_online(text, int(state["online"]))
                # ④：弹幕能到达即说明「该房间仍在被监控」，这里一并兜底拉起 stats 线程。
                # 只靠 room_started 会漏两种形态：stats 线程异常退出后房间表非空、以及未经
                # room_started 隐式注册的房间（上面的 get→建条目分支）——二者都会让 GUI 的
                # msg_rate/online 永久冻结且无任何线索。判活只是 is_alive() 一次属性读。
                self._ensure_stats_thread()
        except Exception as e:
            logger.debug(
                i18n.tr(
                    "[弹幕监控]{where} 处理失败(忽略): {type_name}: {e}",
                    where="room_message",
                    type_name=type(e).__name__,
                    e=e,
                )
            )

    # 生成监控快照：rooms 为各房间统计（含人读时间），messages 为 seq 大于
    # since 的近期消息（最多 _MAX_MESSAGES_PER_RESPONSE 条，超出置 truncated），
    # last_seq 为当前游标。供 Web API 直接 JSON 序列化返回。
    def snapshot(self, since: int = 0) -> dict[str, Any]:
        try:
            with self._lock:
                now = time.time()
                rooms: list[dict[str, Any]] = []
                for name, state in self._rooms.items():
                    # 顺带在快照时重算速率（按时间窗剪枝桶，静默房间速率自然衰减）
                    state["msg_rate"] = self._rate_of(state, now)
                    rooms.append(
                        {
                            "name": name,
                            "platform": state["platform"],
                            "connected": bool(state["connected"]),
                            "started_at": time.strftime(
                                "%Y-%m-%d %H:%M:%S", time.localtime(float(state["started_at"]))
                            ),
                            "msg_total": int(state["msg_total"]),
                            "msg_rate": int(state["msg_rate"]),
                            "gift_total": int(state["gift_total"]),
                            "online": int(state["online"]),
                        }
                    )
                messages = [m for m in self._recent if int(m["seq"]) > since]
                truncated = False
                if len(messages) > _MAX_MESSAGES_PER_RESPONSE:
                    messages = messages[-_MAX_MESSAGES_PER_RESPONSE:]
                    truncated = True
                return {
                    "rooms": rooms,
                    "messages": messages,
                    "last_seq": self._seq,
                    "truncated": truncated,
                }
        except Exception as e:
            logger.debug(
                i18n.tr(
                    "[弹幕监控]{where} 处理失败(忽略): {type_name}: {e}",
                    where="snapshot",
                    type_name=type(e).__name__,
                    e=e,
                )
            )
            return {"rooms": [], "messages": [], "last_seq": since, "truncated": False}

    # ── 内部实现（调用方须已持有 self._lock） ────────────────

    # 构造新房间的初始状态字典。
    @staticmethod
    def _default_state(platform: str) -> dict[str, Any]:
        return {
            "platform": platform,
            "connected": False,
            "started_at": time.time(),
            "msg_total": 0,
            "gift_total": 0,
            "online": 0,
            "msg_rate": 0,
            "last_msg_at": 0.0,
            # 速率桶：(bucket_start, count)，10 秒一桶，最多 6 桶
            "_buckets": deque(maxlen=6),
            # 展示流采样窗口（monotonic 基准）
            "_sample_win_start": time.monotonic(),
            "_sample_win_count": 0,
            # 被采样折叠掉的消息数（折入下一条已发出事件）
            "_dropped": 0,
        }

    # 分配下一个单调递增游标（须持 self._lock 调用）。
    def _next_seq(self) -> int:
        self._seq += 1
        return self._seq

    # 往当前时间窗的速率桶中计数一条（须持 self._lock 调用）。
    @staticmethod
    def _bump_rate(state: dict[str, Any], now: float) -> None:
        buckets: deque[tuple[float, int]] = state["_buckets"]
        bucket_start = int(now // 10) * 10
        if buckets and buckets[-1][0] == bucket_start:
            buckets[-1] = (bucket_start, buckets[-1][1] + 1)
        else:
            buckets.append((bucket_start, 1))

    # 计算近 60 秒窗口内的弹幕速率（条/分）：剪枝过期桶后求和（须持 self._lock 调用）。
    @staticmethod
    def _rate_of(state: dict[str, Any], now: float) -> int:
        buckets: deque[tuple[float, int]] = state["_buckets"]
        while buckets and buckets[0][0] < now - _RATE_WINDOW_SEC:
            buckets.popleft()
        return sum(count for _start, count in buckets)

    # 展示流采样判定：每房间每秒最多 _STREAM_SAMPLE_PER_SEC 条，超出折叠计数（须持 self._lock 调用）。
    @staticmethod
    def _allow_stream_sample(state: dict[str, Any]) -> bool:
        now_mono = time.monotonic()
        if now_mono - float(state["_sample_win_start"]) >= 1.0:
            state["_sample_win_start"] = now_mono
            state["_sample_win_count"] = 0
        if int(state["_sample_win_count"]) < _STREAM_SAMPLE_PER_SEC:
            state["_sample_win_count"] = int(state["_sample_win_count"]) + 1
            return True
        state["_dropped"] = int(state["_dropped"]) + 1
        return False

    # 将一条消息写入展示流（内存缓冲 + JSONL），折入被采样折叠的条数（须持 self._lock 调用）。
    def _emit_message(self, room: str, msg_type: str, user: str, text: str) -> None:
        payload: dict[str, Any] = {
            "ev": "msg",
            "seq": self._next_seq(),
            "room": room,
            "type": msg_type,
            "user": user,
            "text": text,
            "ts": time.time(),
        }
        dropped = int(self._rooms[room]["_dropped"]) if room in self._rooms else 0
        if dropped > 0:
            payload["dropped"] = dropped
            self._rooms[room]["_dropped"] = 0
        self._recent.append(dict(payload))
        self._write_line(payload)

    # 解析在线人数文本：优先整体转 int；否则按 K/M/万/亿 单位换算（如 "1.2万" → 12000）；
    # 再失败则抽取其中的数字；仍失败保持原值。
    # 不能只剔除非数字字符："1.2万" 会得到 12 而不是 12000（数字少三个量级、小数点也被丢弃）。
    @staticmethod
    def _parse_online(text: str, current: int) -> int:
        t = text.strip()
        if not t:
            return current
        try:
            return int(t)
        except ValueError:
            # 单位换算：万=1e4，亿=1e8（中英文单位都覆盖）
            unit = 1
            if "亿" in t or "億" in t:
                unit = 100000000
            elif "万" in t or "萬" in t:
                unit = 10000
            elif t.upper().endswith("K"):
                unit = 1000
            elif t.upper().endswith("M"):
                unit = 1000000
            body = t.replace("亿", "").replace("億", "").replace("万", "").replace("萬", "")
            body = body.rstrip("KkMm")
            # 只保留数字与小数点，供 float 解析
            cleaned = "".join(ch for ch in body if ch.isdigit() or ch == ".")
            if cleaned:
                try:
                    return int(float(cleaned) * unit)
                except ValueError:
                    pass
            digits = "".join(ch for ch in t if ch.isdigit())
            return int(digits) if digits else current

    # 确保周期 stats 线程在运行（房间全部移除后线程自行退出，须持 self._lock 调用）。
    # 两处调用点（room_started 与 room_message）都必需：房间表非空而线程已死时，只靠 room_started
    # 拉不起新线程，stats 线程一旦停摆 GUI 的 msg_rate/online 就永久冻结。判活用 is_alive()，
    # 线程退出时在 _stats_loop 的 finally 里自注销 self._stats_thread，两者配套才能真的重启。
    def _ensure_stats_thread(self) -> None:
        t = self._stats_thread
        if t is not None and t.is_alive():
            return
        self._stats_stop.clear()
        self._stats_thread = threading.Thread(target=self._stats_loop, name="danmaku-monitor-stats", daemon=True)
        self._stats_thread.start()

    # stats 线程主体：每 _STATS_INTERVAL 秒为全部房间写一条 stats 事件；
    # 无房间时退出，待下次 room_started / room_message 再拉起。
    def _stats_loop(self) -> None:
        thread = threading.current_thread()
        # 只有「房间表为空 → break」这条正常出口允许在注销后立即复活；异常/stop 出口一律
        # 维持「等下一次事件再拉起」，否则一崩就重建会自旋（见 finally 内的说明）。
        revive_on_deregister = False
        try:
            while not self._stats_stop.wait(_STATS_INTERVAL):
                try:
                    with self._lock:
                        if not self._rooms:
                            revive_on_deregister = True
                            break
                        now = time.time()
                        for room, state in self._rooms.items():
                            state["msg_rate"] = self._rate_of(state, now)
                            self._write_line(
                                {
                                    "ev": "stats",
                                    "room": room,
                                    "platform": state["platform"],
                                    "connected": bool(state["connected"]),
                                    "msg_total": int(state["msg_total"]),
                                    "msg_rate": int(state["msg_rate"]),
                                    "gift_total": int(state["gift_total"]),
                                    "online": int(state["online"]),
                                    "ts": now,
                                }
                            )
                except Exception as e:
                    # 吞没即正确：内层异常只丢掉本轮统计，不足以让整条监控链路永久静默
                    logger.debug(
                        i18n.tr(
                            "[弹幕监控]{where} 处理失败(忽略): {type_name}: {e}",
                            where="stats_loop",
                            type_name=type(e).__name__,
                            e=e,
                        )
                    )
        except Exception as e:
            # 能走到这里说明异常发生在 while 条件/锁之外，线程就此退出。不外抛也不重抛：本线程是
            # 守护线程，未捕获异常只会向（GUI/无控制台进程里未必存在的）stderr 打一段无人认领的
            # Traceback，而「已退出」这一事实由下面的 finally 自注销 + 本条 warning 完整交代。
            logger.warning(
                i18n.tr(
                    "[弹幕监控]{where} 线程异常退出，将在下一条弹幕事件时重新拉起: {type_name}: {e}",
                    where="stats",
                    type_name=type(e).__name__,
                    e=e,
                )
            )
        finally:
            # ④：无论正常 break、异常退出还是被 stop 置位退出，都要在持锁状态下比对身份后
            # 清掉 self._stats_thread。缺这一步时 _ensure_stats_thread 的 is_alive() 永远读到那支
            # 已死线程，重启链路整体失效。身份比对不可省：本线程可能已被更新的一轮
            # _ensure_stats_thread 换掉，无条件置 None 会误清正在运行的新线程引用。
            # self._lock 是普通 Lock（非重入），故必须在 while 的 with 块之外再取一次。
            try:
                with self._lock:
                    if self._stats_thread is thread:
                        self._stats_thread = None
                        # 2026-10-21 ：break（房间表当时为空）与这里之间存在窗口——期间新登记的
                        # 房间调 _ensure_stats_thread() 时本线程**仍 is_alive()**，于是判定为
                        # 「已有线程在跑」而不新建；本线程随后把引用清成 None 并退出，结果该房间
                        # 永久拿不到周期 stats（GUI 的 msg_rate/online 冻结，直到下一条弹幕或
                        # 下一次 room_started 才有机会重启）。注销后必须在**仍持锁**时复检房间表：
                        # 非空即原子拉起替代线程（同锁内完成，故不会与并发登记交错出第二支线程）。
                        # 复活只对 break 路径成立：异常退出时立即重建会变成「崩溃→重建→再崩」的
                        # 自旋（实测 1s 内可打满几十条 warning），且与本函数上方「异常退出待下一条
                        # 弹幕事件再拉起」的既有契约冲突，故由 revive_on_deregister 区分两种出口。
                        if revive_on_deregister and self._rooms:
                            self._ensure_stats_thread()
            except Exception as e:
                # 吞没即正确：自注销失败最坏退回到修复前的行为，绝不让收尾再抛一次
                logger.debug(
                    i18n.tr(
                        "[弹幕监控]{where} 处理失败(忽略): {type_name}: {e}",
                        where="stats_cleanup",
                        type_name=type(e).__name__,
                        e=e,
                    )
                )

    # ── JSONL 边车文件 ─────────────────────────────────────

    # 准备日志文件路径：创建父目录，失败则禁用文件输出并返回 None。
    @staticmethod
    def _prepare_log_path(log_path: Optional[str]) -> Optional[str]:
        if not log_path:
            return None
        try:
            # 2026-10-21 ：裸文件名（如 "danmaku_monitor.jsonl"，无目录段）时
            # os.path.dirname() 返回空串，os.makedirs("") 抛 FileNotFoundError 落进下面的
            # except 被当成「目录不可写」→ 边车输出**静默禁用**，GUI/Web 的 tail 链路整体失效。
            # 空父目录本就等价于「当前目录」，无需创建，直接放行。
            parent = os.path.dirname(log_path)
            if parent:
                os.makedirs(parent, exist_ok=True)
            return log_path
        except Exception as e:
            logger.debug(i18n.tr("[弹幕监控]日志目录创建失败，禁用文件输出: {e}", e=e))
            return None

    # 把一行 JSON 事件**入队**交给进程级写线程落盘（调用方持 self._lock 时只做序列化 +
    # O(1) 入队，绝不碰磁盘）。真正的追加与轮转见 _append_sidecar_line；队列满时计数丢弃，
    # 绝不阻塞调用方（调用方是各房间的事件循环线程）。
    def _write_line(self, payload: dict[str, Any]) -> None:
        if not self._log_path:
            return
        try:
            _get_sidecar().submit("line", self._log_path, json.dumps(payload, ensure_ascii=False))
        except Exception as e:
            # 留痕但不外抛：本函数由 room_* 在持锁路径上调用，抛出会让整条事件被丢弃
            # 且调用方（采集器回调）看到异常——与「监控绝不影响录制」的约定冲突。
            logger.debug(i18n.tr("弹幕边车文件写入失败: {type_name}: {e}", type_name=type(e).__name__, e=e))

    # flush 并关闭 JSONL 边车文件句柄（停止录制归档流程在改名前调用）。
    # 后写盘在独立线程，故「关闭」= 入队一条 close 指令 + 等待队列排空，顺序与旧实现一致：
    # 改名前句柄必已关闭，且已 accept 的事件不会丢。排空超时时抛 TimeoutError 由下面的容错记日志
    # ——归档侧会因句柄未关而跳过该文件的改名，绝不中断停止流程。关闭后下一条事件经写线程的
    # 惰性重开自动重建句柄。
    def close_file(self) -> None:
        try:
            path = self._log_path
            if not path:
                return
            writer = _get_sidecar()
            # 2026-10-02：submit 返回 False（队列满被丢弃）必须与 drain 超时同语义
            # 处理——静默丢弃 close 指令会让句柄未关而本函数「成功」返回，随后的归档改名
            # 必抛 PermissionError 且无法归因。外层容错会记日志（归档侧跳过该文件）。
            if not writer.submit("close", path):
                raise TimeoutError("sidecar close command dropped (queue full)")
            if not writer.drain(_SIDECAR_DRAIN_SECONDS):
                raise TimeoutError(f"sidecar drain exceeded {_SIDECAR_DRAIN_SECONDS}s")
        except Exception as e:
            # 吞没即正确：close_file 处于「停止录制 → 日志归档」链路的最前端，
            # 这里的外抛会让整批运行日志都不再归档；句柄最坏随进程退出回收。
            logger.debug(i18n.tr("[弹幕监控]关闭边车文件异常(忽略): {type_name}: {e}", type_name=type(e).__name__, e=e))

    # 进入「停止录制 → 日志归档改名」窗口：先置位抑制标记，再复用 close_file() 的
    # 「入队 close + 等待排空」。差别就在那一步置位——旧实现只关一次，之后延迟/已排队事件仍经写线程
    # 惰性重开重持 logs/danmaku_monitor.jsonl 句柄，而归档改名与 close 无同步点、delay_default 最长
    # 120s 仍在推事件，于是 Windows 下「句柄未关的文件 rename 必抛 PermissionError」几乎必然发生，
    # 该文件基本永不归档。现由显式窗口决定是否丢弃（抑制期事件一律丢是刻意取舍——边车只是旁路展示
    # 数据、录制收尾日志的完整归档优先，丢弃量经 logger.debug 留痕）。调用方必须在窗口结束后调 resume_writes()。
    def suspend_writes(self) -> None:
        try:
            path = self._log_path
            if not path:
                return
            _get_sidecar().suspend(path)
            self.close_file()
        except Exception as e:
            # 吞没即正确：与 close_file() 同一条链路，绝不允许中断停止录制流程
            logger.debug(i18n.tr("[弹幕监控]关闭边车文件异常(忽略): {type_name}: {e}", type_name=type(e).__name__, e=e))

    # 退出归档窗口：解除抑制，下一条事件经惰性重开继续落盘（幂等，可重复调用）。
    def resume_writes(self) -> None:
        try:
            path = self._log_path
            if not path:
                return
            _get_sidecar().resume(path)
        except Exception as e:
            logger.debug(i18n.tr("[弹幕监控]关闭边车文件异常(忽略): {type_name}: {e}", type_name=type(e).__name__, e=e))

    # 当前是否处于归档抑制期（供观测/断言）。
    def writes_suspended(self) -> bool:
        path = self._log_path
        if not path:
            return False
        return _get_sidecar().is_suspended(path)


_hub: Optional[DanmakuMonitorHub] = None
_hub_lock = threading.Lock()


# 获取进程级弹幕监控枢纽单例：首次调用时以默认路径
# <script_path>/logs/danmaku_monitor.jsonl 创建。
def get_hub() -> DanmakuMonitorHub:
    global _hub
    with _hub_lock:
        if _hub is None:
            _hub = DanmakuMonitorHub(log_path=os.path.join(script_path, "logs", "danmaku_monitor.jsonl"))
        return _hub


# 关闭弹幕监控边车文件句柄（停止录制归档流程调用，归档改名前必须先关句柄——
# Windows 下句柄未关的文件 rename 会抛 PermissionError）。枢纽单例未初始化时为 no-op，
# 刻意不经 get_hub() 触发初始化：未启用监控的进程不应凭空创建枢纽实例。
def close_monitor_file() -> None:
    hub = _hub
    if hub is not None:
        hub.close_file()


# 归档窗口的进入/退出（src/log_archive.py 成对调用，改名结束一律要退出）；枢纽未初始化时为 no-op、
# 刻意不经 get_hub() 触发初始化，理由同 close_monitor_file。
def suspend_monitor_writes() -> None:
    hub = _hub
    if hub is not None:
        hub.suspend_writes()


def resume_monitor_writes() -> None:
    hub = _hub
    if hub is not None:
        hub.resume_writes()
