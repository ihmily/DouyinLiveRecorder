# -*- coding: utf-8 -*-
# 弹幕监控枢纽：进程级单例，汇总各直播间弹幕采集器上报的实时事件，
# 为两类消费方提供数据：
# - Web API（与录制引擎同进程）：直接读内存快照（统计 + 增量消息游标）；
# - GUI（以子进程方式运行录制引擎）：tail 边车文件 logs/danmaku_monitor.jsonl。
#
# 设计约束：
# - 所有公开方法异常全吞、只记 debug 日志——弹幕监控是旁路功能，
#   任何失败都绝不允许影响录制主流程；
# - 「统计精确、流式采样」：计数器（累计弹幕/礼物/速率桶）对每条消息都累加，
#   但消息展示流（内存环形缓冲与 JSONL 文件）按每房间每秒采样上限输出，
#   超出部分折叠为下一事件上的 dropped 计数，保证高频房间下 UI 与文件体积有界；
#   GIFT / SUPER_CHAT / 连接事件为低频事件，不参与采样。
from __future__ import annotations

import json
import os
import threading
import time
from collections import deque
from typing import Any, Optional, TextIO

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


# 弹幕监控枢纽：线程安全地聚合各房间弹幕事件，维护统计与展示流。
class DanmakuMonitorHub:
    # 初始化枢纽。log_path 为 JSONL 边车文件路径，None 表示禁用文件输出
    # （仅供测试/无 GUI 消费方场景）；目录不可写时自动降级为禁用。
    def __init__(self, log_path: Optional[str] = None) -> None:
        self._lock = threading.Lock()
        self._file_lock = threading.Lock()
        self._log_path: Optional[str] = self._prepare_log_path(log_path)
        self._file: Optional[TextIO] = None
        # 房间状态表：{room: {platform/connected/started_at/msg_total/gift_total/
        # online/msg_rate/last_msg_at + 采样与速率桶等内部字段（_ 前缀）}}
        self._rooms: dict[str, dict[str, Any]] = {}
        # 近期消息环形缓冲（含 seq，供 Web 增量拉取过滤）
        self._recent: deque[dict[str, Any]] = deque(maxlen=_RECENT_BUFFER_SIZE)
        self._seq = 0
        self._stats_thread: Optional[threading.Thread] = None
        self._stats_stop = threading.Event()

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
            logger.debug(f"[弹幕监控]room_started 处理失败(忽略): {e}")

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
            logger.debug(f"[弹幕监控]room_connected 处理失败(忽略): {e}")

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
            logger.debug(f"[弹幕监控]room_closed 处理失败(忽略): {e}")

    # 房间停止监控（房间录制线程退出：URL 被注释/移除）：从房间表移除条目并写
    # conn/stopped 事件（GUI 据此移除房间行，Web 快照随房间表自动消失）。
    # 此前房间条目永不删除，URL 移除后监控页会一直残留已失效直播间及其旧弹幕数据。
    def room_stopped(self, room: str, reason: str = "房间已停止监控") -> None:
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
            logger.debug(f"[弹幕监控]room_stopped 处理失败(忽略): {e}")

    # 收到一条弹幕消息（collector.on_message 转发，msg_type 取 DanmakuMessageType.value）。
    # chat 累计并按采样写入展示流；gift/superChat 计入礼物数且不采样直接入流；
    # online 仅更新房间在线人数（不入展示流）。
    def room_message(self, room: str, msg_type: str, user: str, text: str) -> None:
        try:
            with self._lock:
                state = self._rooms.setdefault(room, self._default_state("未知"))
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
                    state["online"] = self._parse_online(text, int(state["online"]))
        except Exception as e:
            logger.debug(f"[弹幕监控]room_message 处理失败(忽略): {e}")

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
            logger.debug(f"[弹幕监控]snapshot 处理失败(忽略): {e}")
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

    # 解析在线人数文本：优先整体转 int，失败则抽取其中的数字（如 "1.2万" 取 12），
    # 再失败则保持原值。
    @staticmethod
    def _parse_online(text: str, current: int) -> int:
        t = text.strip()
        if not t:
            return current
        try:
            return int(t)
        except ValueError:
            digits = "".join(ch for ch in t if ch.isdigit())
            return int(digits) if digits else current

    # 确保周期 stats 线程在运行（房间全部移除后线程自行退出，须持 self._lock 调用）。
    def _ensure_stats_thread(self) -> None:
        t = self._stats_thread
        if t is not None and t.is_alive():
            return
        self._stats_stop.clear()
        self._stats_thread = threading.Thread(target=self._stats_loop, name="danmaku-monitor-stats", daemon=True)
        self._stats_thread.start()

    # stats 线程主体：每 _STATS_INTERVAL 秒为全部房间写一条 stats 事件；
    # 无房间时退出，待下次 room_started 再拉起。
    def _stats_loop(self) -> None:
        while not self._stats_stop.wait(_STATS_INTERVAL):
            try:
                with self._lock:
                    if not self._rooms:
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
                logger.debug(f"[弹幕监控]stats 循环异常(忽略): {e}")

    # ── JSONL 边车文件 ─────────────────────────────────────

    # 准备日志文件路径：创建父目录，失败则禁用文件输出并返回 None。
    @staticmethod
    def _prepare_log_path(log_path: Optional[str]) -> Optional[str]:
        if not log_path:
            return None
        try:
            os.makedirs(os.path.dirname(log_path), exist_ok=True)
            return log_path
        except Exception as e:
            logger.debug(f"[弹幕监控]日志目录创建失败，禁用文件输出: {e}")
            return None

    # 追加一行 JSON 事件到边车文件；超过轮转阈值时先轮转（保留一代 .1 备份）。
    # 写失败时静默重置句柄，下一条再尝试重开（不影响任何调用方）。
    def _write_line(self, payload: dict[str, Any]) -> None:
        if not self._log_path:
            return
        try:
            line = json.dumps(payload, ensure_ascii=False)
            with self._file_lock:
                if self._file is None:
                    self._file = open(self._log_path, "a", encoding="utf-8")
                # 轮转判定用当前句柄的真实大小，避免长期运行下误差累积
                if self._file.tell() >= _ROTATE_BYTES:
                    self._file.close()
                    backup = self._log_path + ".1"
                    try:
                        os.replace(self._log_path, backup)
                    except OSError:
                        pass
                    self._file = open(self._log_path, "a", encoding="utf-8")
                self._file.write(line + "\n")
                self._file.flush()
        except Exception:
            # 句柄可能已损坏：关闭置空，下一条事件重新打开
            try:
                if self._file is not None:
                    self._file.close()
            except Exception:
                pass
            self._file = None


# 进程级单例访问：首次调用时以默认路径 <script_path>/logs/danmaku_monitor.jsonl 创建。
_hub: Optional[DanmakuMonitorHub] = None
_hub_lock = threading.Lock()


# 获取进程级弹幕监控枢纽单例。
def get_hub() -> DanmakuMonitorHub:
    global _hub
    with _hub_lock:
        if _hub is None:
            _hub = DanmakuMonitorHub(log_path=os.path.join(script_path, "logs", "danmaku_monitor.jsonl"))
        return _hub
