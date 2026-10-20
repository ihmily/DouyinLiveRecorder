# -*- coding: utf-8 -*-
# 弹幕监控：tail 录制子进程写的边车 JSONL（logs/danmaku_monitor.jsonl）。
#
# 为什么是一条 tail 线程而不是 QFileSystemWatcher：JSONL 由录制进程持续 open 追加写入，
# 而 watcher 只在 close/rename 时给 signal，内容增长收不到事件，因此只能轮询 + 偏移。
#
# 并发约定：rooms / msgs 两个缓冲在 tail 线程与主线程间共享，一律在 _lock 下读写。
# _stop_event 与线程一一绑定——共享 Event 被 clear() 会让旧线程永不退出、计数随重启翻倍
# （MID-2250），故每次 start 都**新建** Event 并随参数交给该线程。
from __future__ import annotations

import json
import os
import threading
import time
from collections import deque
from typing import Any, Callable

from .shared import as_float, as_int

# 近期消息环形缓冲上限（tail 线程追加，主线程渲染）
_MAX_MESSAGES: int = 300
# 首读仅回看末尾 64KB，避免重放历史会话
_FIRST_READ_WINDOW: int = 64 * 1024
# tail 线程自身异常的限频留痕窗口（秒）
_WARN_INTERVAL_SECONDS: float = 30.0


class DanmakuMonitor:
    def __init__(self, jsonl_path: str, log: Callable[[str, str], None]) -> None:
        self._path = jsonl_path
        self._log = log
        self._lock = threading.Lock()
        self._rooms: dict[str, dict[str, Any]] = {}
        self._msgs: deque[dict[str, Any]] = deque(maxlen=_MAX_MESSAGES)
        self._stats_dirty = True
        self._stream_dirty = True
        self._thread: threading.Thread | None = None
        self._stop_event: threading.Event | None = None

    # ─── 主线程侧读接口 ───

    def rooms_snapshot(self) -> dict[str, dict[str, Any]]:
        with self._lock:
            return {name: dict(info) for name, info in self._rooms.items()}

    def messages_snapshot(self) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._msgs)

    def consume_stats_dirty(self) -> bool:
        with self._lock:
            dirty = self._stats_dirty
            self._stats_dirty = False
        return dirty

    def consume_stream_dirty(self) -> bool:
        with self._lock:
            dirty = self._stream_dirty
            self._stream_dirty = False
        return dirty

    def clear(self) -> None:
        with self._lock:
            self._rooms.clear()
            self._msgs.clear()
            self._stats_dirty = True
            self._stream_dirty = True

    # ─── 生命周期 ───

    def start(self) -> None:
        self.stop()
        stale = self._thread
        if stale is not None and stale.is_alive():
            # MID-2250：上一轮 join 超时被保留下来的线程仍在收尾时不等它（不为收尾阻塞界面），
            # 其停止标志已 set，最多再睡完一轮即自行退出；这里留一条 warn 供排查计数虚增。
            self._log("上一条弹幕监控 tail 线程尚未退出（其停止标志已置位、会自行结束），本轮另起新线程", "warn")
        self.clear()
        stop_event = threading.Event()
        self._stop_event = stop_event
        self._thread = threading.Thread(target=self._tail_loop, args=(stop_event,), name="danmaku-tail", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        stop_event = self._stop_event
        if stop_event is not None:
            stop_event.set()
        thread = self._thread
        if thread is not None and thread is not threading.current_thread() and thread.is_alive():
            # WD-21：join 超时压到 0.2s。旧 tkinter 版的 2s 会让每次收尾冻结窗口约 2 秒。
            thread.join(timeout=0.2)
            if thread.is_alive():
                # 收尾未完成：**保留**线程引用与它的停止标志，让下一轮启动前重查。
                return
        self._thread = None
        self._stop_event = None

    # ─── tail 线程主体 ───

    def _tail_loop(self, stop_event: threading.Event) -> None:
        offset = 0
        partial = ""
        first_open = True
        last_warn_at = 0.0
        while not stop_event.is_set():
            try:
                if not os.path.exists(self._path):
                    time.sleep(0.5)
                    continue
                size = os.path.getsize(self._path)
                if size < offset:
                    # 文件被轮转（变短）：从头重读
                    offset = 0
                    partial = ""
                if size == offset:
                    time.sleep(0.3)
                    continue
                with open(self._path, "rb") as f:
                    if first_open:
                        # 二进制模式 + tell 偏移：文本模式的 tell 是不透明 cookie，
                        # 不能与文件字节数比较（一度是「大文件永远读不到」的根因）。
                        if size > _FIRST_READ_WINDOW:
                            f.seek(size - _FIRST_READ_WINDOW)
                            f.readline()  # 丢弃半个行首，对齐到下一行
                        offset = f.tell()
                        first_open = False
                        if size == offset:
                            continue
                    f.seek(offset)
                    chunk = f.read()
                    offset += len(chunk)
                partial += chunk.decode("utf-8", errors="replace")
                lines = partial.split("\n")
                partial = lines.pop()
                bad_events = 0
                bad_detail = ""
                for line in lines:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        event = json.loads(line)
                    except ValueError, TypeError:
                        continue
                    if not isinstance(event, dict):
                        continue
                    # 防护必须落在**每条事件**上：一条脏事件冒泡到最外层 except 时，offset 已推进
                    # 过整个 chunk，同批后续完好事件会全部丢失且零日志（M-17）。
                    try:
                        self._dispatch(event)
                    except Exception as e:
                        bad_events += 1
                        if not bad_detail:
                            # Windows 下 socket.timeout 的 str() 是空串，故必须带类型名。
                            bad_detail = f"{type(e).__name__}: {e}"
                if bad_events:
                    self._log(
                        f"弹幕事件处理失败 {bad_events} 条已跳过（同批其余事件不受影响）: {bad_detail}",
                        "warn",
                    )
            except OSError:
                # 日志被归档改名 / 句柄未就绪（MID-2250 已知良性路径）：等一轮再试，不刷屏。
                time.sleep(1.0)
            except Exception as e:
                # 完全静默会让「弹幕监控长期不更新」查无线索；限频 30s 留痕后继续循环，
                # 不 break（本线程的退出信号只有 stop_event，M-17）。
                now = time.time()
                if now - last_warn_at >= _WARN_INTERVAL_SECONDS:
                    last_warn_at = now
                    self._log(f"弹幕 tail 线程本轮异常（下轮继续）: {type(e).__name__}: {e}", "warn")
                time.sleep(1.0)

    # 分发一条 JSONL 事件到线程安全缓冲（tail 线程调用）。
    # 数值字段一律经 as_float/as_int：本函数读的是外部可控的边车 JSONL，
    # 且 tail 首读会回放旧文件末尾 64KB 的历史脏记录，null/字符串都可达。
    def _dispatch(self, event: dict[str, Any]) -> None:
        ev = str(event.get("ev", ""))
        room = str(event.get("room", ""))
        with self._lock:
            if ev == "conn":
                state = str(event.get("state", ""))
                if state == "started":
                    self._rooms[room] = {
                        "platform": str(event.get("platform", "—")),
                        "connected": False,
                        "started_at": as_float(event.get("ts")),
                        "msg_total": 0,
                        "msg_rate": 0,
                        "gift_total": 0,
                        "online": 0,
                    }
                elif state == "stopped":
                    # 房间已停止监控（URL 被移除 / 注释）：从监控表移除，不再显示旧数据
                    self._rooms.pop(room, None)
                else:
                    info = self._rooms.get(room)
                    if info is not None:
                        info["connected"] = state == "ready"
                self._stats_dirty = True
            elif ev == "msg":
                self._msgs.append(event)
                self._stream_dirty = True
            elif ev == "stats":
                info = self._rooms.setdefault(
                    room,
                    {
                        "platform": str(event.get("platform", "—")),
                        "connected": False,
                        "started_at": 0.0,
                        "msg_total": 0,
                        "msg_rate": 0,
                        "gift_total": 0,
                        "online": 0,
                    },
                )
                # stats 事件是统计的权威来源，四个计数直接覆盖（而不是累加）；
                # platform 允许被后续事件修正——它在 conn.started 时可能还是占位值。
                info["platform"] = str(event.get("platform", info.get("platform", "—")))
                info["connected"] = bool(event.get("connected", False))
                info["msg_total"] = as_int(event.get("msg_total", info.get("msg_total", 0)))
                info["msg_rate"] = as_int(event.get("msg_rate", info.get("msg_rate", 0)))
                info["gift_total"] = as_int(event.get("gift_total", info.get("gift_total", 0)))
                info["online"] = as_int(event.get("online", info.get("online", 0)))
                self._stats_dirty = True
