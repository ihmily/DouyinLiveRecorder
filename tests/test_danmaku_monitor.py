# 弹幕监控测试（离线，不依赖网络 / 真实弹幕 WS）。覆盖：
# 1. DanmakuMonitorHub：统计精确性（不受采样影响）、展示流采样折叠、礼物/在线处理、
#    seq 增量游标、连接状态生命周期、JSONL 合法性与轮转；
# 2. DanmakuCollector 双模式：write_srt=False 不落 SRT、全类型消息上报、连接状态上报；
# 3. get_danmaku_collector 工厂透传 room_name / write_srt；
# 4. Web API /api/danmaku 端点返回枢纽快照；
# 5. GUI 弹幕监控（无头）的行为锁已随 tkinter legacy GUI 退役迁至
#    tests/test_gui_qt_units.py（DanmakuMonitor 的事件分发、tail 轮转与停止语义）。

import asyncio
import json
import threading
import time
from pathlib import Path
from typing import Any, cast

import pytest

import src.danmaku_monitor as dm
from src.base import DanmakuBase, DanmakuMessage, DanmakuMessageType
from src.collector import DanmakuCollector
from src.danmaku_monitor import DanmakuMonitorHub


# 可长期阻塞的弹幕客户端替身：start() 长睡眠模拟常驻连接，collector 经 loop.stop() 中断
# （run_until_complete 抛 RuntimeError 被 _run 捕获），从而可无网络验证采集线程生命周期。
class _BlockingDanmaku(DanmakuBase):
    async def start(self, args: Any) -> None:
        await asyncio.sleep(3600)

    async def stop(self) -> None:
        pass

    async def heartbeat(self) -> None:
        pass

    def decode_message(self, data: Any) -> None:
        pass


def _feed_chat(hub: DanmakuMonitorHub, room: str, count: int, prefix: str = "m") -> None:
    # 快速灌入 count 条聊天弹幕（同一采样秒窗口内）。
    # 不 sleep 保证全部落在同一秒，便于验证展示流采样上限（而非速率口径）。
    for i in range(count):
        hub.room_message(room, "chat", f"用户{i}", f"{prefix}{i}")


# ─── Hub：统计与采样 ───────────────────────────────────────


def test_msg_total_exact_while_stream_sampled(tmp_path: Path) -> None:
    # 统计精确、流式采样：25 条同秒弹幕 → msg_total=25（精确），展示流仅保留 10 条（每秒采样上限）。
    hub = DanmakuMonitorHub(log_path=str(tmp_path / "dm.jsonl"))
    hub.room_started("房间A", "抖音直播")
    _feed_chat(hub, "房间A", 25)

    snap = hub.snapshot(0)
    room = next(r for r in snap["rooms"] if r["name"] == "房间A")
    assert room["msg_total"] == 25
    assert len(snap["messages"]) == 10


def test_rate_counts_all_messages_in_window(tmp_path: Path) -> None:
    # 速率口径：60 秒窗口内全部计数（30 条快速弹幕 → 30 条/分），不受展示流采样影响。
    hub = DanmakuMonitorHub(log_path=str(tmp_path / "dm.jsonl"))
    hub.room_started("房间A", "抖音直播")
    _feed_chat(hub, "房间A", 30)

    snap = hub.snapshot(0)
    room = next(r for r in snap["rooms"] if r["name"] == "房间A")
    assert room["msg_rate"] == 30


def test_gift_counted_and_not_sampled(tmp_path: Path) -> None:
    # 礼物为低频高价值事件：不参与采样，全部进入展示流并计入 gift_total。
    hub = DanmakuMonitorHub(log_path=str(tmp_path / "dm.jsonl"))
    hub.room_started("房间A", "B站直播")
    for i in range(15):
        hub.room_message("房间A", "gift", f"老板{i}", "送出 小心心×1")

    snap = hub.snapshot(0)
    room = next(r for r in snap["rooms"] if r["name"] == "房间A")
    assert room["gift_total"] == 15
    # 礼物全进展示流（不采样），且类型保持 gift（未被混入 chat 采样折叠）。
    assert len(snap["messages"]) == 15
    assert all(m["type"] == "gift" for m in snap["messages"])


def test_online_updates_state_not_stream(tmp_path: Path) -> None:
    # 在线人数仅更新房间状态，不进入展示流（避免高频数字刷屏）。
    hub = DanmakuMonitorHub(log_path=str(tmp_path / "dm.jsonl"))
    hub.room_started("房间A", "抖音直播")
    hub.room_message("房间A", "online", "", "1234")

    snap = hub.snapshot(0)
    room = next(r for r in snap["rooms"] if r["name"] == "房间A")
    assert room["online"] == 1234
    assert snap["messages"] == []


def test_seq_cursor_incremental(tmp_path: Path) -> None:
    # seq 增量游标：snapshot(since=last_seq) 只返回新消息，不丢不重。
    hub = DanmakuMonitorHub(log_path=str(tmp_path / "dm.jsonl"))
    hub.room_started("房间A", "抖音直播")
    _feed_chat(hub, "房间A", 5)
    first = hub.snapshot(0)
    assert first["last_seq"] > 0

    _feed_chat(hub, "房间A", 3, prefix="n")
    second = hub.snapshot(int(first["last_seq"]))
    assert len(second["messages"]) == 3
    assert all(str(m["text"]).startswith("n") for m in second["messages"])


def test_conn_lifecycle_and_restart_resets(tmp_path: Path) -> None:
    # 连接状态生命周期：started→未连接，ready→已连接，closed→断开；
    # 房间重新 started 时计数清零。
    hub = DanmakuMonitorHub(log_path=str(tmp_path / "dm.jsonl"))
    hub.room_started("房间A", "斗鱼直播")

    def _room() -> dict[str, Any]:
        return next(r for r in hub.snapshot(0)["rooms"] if r["name"] == "房间A")  # type: ignore[return-value]

    assert _room()["connected"] is False
    hub.room_connected("房间A")
    assert _room()["connected"] is True
    _feed_chat(hub, "房间A", 3)
    hub.room_closed("房间A", "重连耗尽")
    assert _room()["connected"] is False
    assert _room()["msg_total"] == 3

    hub.room_started("房间A", "斗鱼直播")
    assert _room()["msg_total"] == 0


def test_room_stopped_removes_room_and_logs_event(tmp_path: Path) -> None:
    # 房间停止监控（URL 移除/注释、录制线程退出）：条目从快照移除、JSONL 记录 stopped 事件
    # （GUI 据此删行）；未注册房间为无操作——否则监控页会一直残留已失效直播间及其旧数据。
    hub = DanmakuMonitorHub(log_path=str(tmp_path / "dm.jsonl"))
    hub.room_started("房间A", "虎牙直播")
    _feed_chat(hub, "房间A", 3)
    hub.room_stopped("房间A")

    snap = hub.snapshot(0)
    assert all(r["name"] != "房间A" for r in snap["rooms"])
    hub.flush()  # 落盘已挪到独立写线程，读文件前须先等队列排空
    lines = (tmp_path / "dm.jsonl").read_text(encoding="utf-8").splitlines()
    assert any(json.loads(line).get("state") == "stopped" for line in lines)

    # 未注册房间：无操作不抛异常、不写事件
    before = len(lines)
    hub.room_stopped("不存在的房间")
    hub.flush()
    assert len((tmp_path / "dm.jsonl").read_text(encoding="utf-8").splitlines()) == before


def test_jsonl_lines_valid_and_rotation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # JSONL 每行均为合法 JSON；把轮转阈值压到 512 字节并灌 30 条长消息，超过后应产生 .1 备份。
    monkeypatch.setattr(dm, "_ROTATE_BYTES", 512)
    hub = DanmakuMonitorHub(log_path=str(tmp_path / "dm.jsonl"))
    hub.room_started("房间A", "抖音直播")
    for i in range(30):
        hub.room_message("房间A", "chat", f"用户{i}", f"消息内容{i}" * 5)

    log_file = tmp_path / "dm.jsonl"
    hub.flush()  # 轮转发生在写线程里，断言前先等队列排空
    assert log_file.exists()
    content = log_file.read_text(encoding="utf-8")
    for line in content.splitlines():
        assert json.loads(line)  # 每行可解析
    # 超阈值后原文件重命名为 .1 备份，新文件继续写入（轮转不丢历史）。
    assert (tmp_path / "dm.jsonl.1").exists()


def test_sidecar_write_does_not_hold_hub_lock(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # 主用例：磁盘 IO 不得发生在 hub._lock 内。旧实现 open/write/flush 全在锁里，
    # 一次被慢盘拖住的 flush 会让所有房间的 ws 收包/心跳协程一起停摆（协议层 ping 超时 →
    # 断连风暴），snapshot() 也抢同一把锁。做法：把真实写函数换成一直不返回的慢版本，再从另一线程抢锁。
    started = threading.Event()
    release = threading.Event()

    def _slow_append(files: dict, path: str, line: str) -> None:
        started.set()
        assert release.wait(timeout=10), "测试未在 10s 内放行慢写入"

    monkeypatch.setattr(dm, "_append_sidecar_line", _slow_append)
    hub = DanmakuMonitorHub(log_path=str(tmp_path / "dm.jsonl"))
    hub.room_started("房间A", "抖音直播")
    assert started.wait(3), "写线程未执行到落盘函数"

    try:
        # 落盘卡住期间：① hub 自己的锁必须立即可得（其他房间不被串住）
        assert hub._lock.acquire(timeout=0.5), "边车写盘期间仍持有 hub._lock"
        hub._lock.release()
        # ② 事件循环侧的投递本身不被阻塞（room_message 只做统计 + 入队）
        t0 = time.monotonic()
        for i in range(200):
            hub.room_message("房间A", "chat", f"u{i}", f"m{i}")
        assert time.monotonic() - t0 < 0.5, "room_message 被慢盘拖住"
        # ③ snapshot() 也不被拖住（旧实现与写盘争同一把锁）
        t0 = time.monotonic()
        snap = hub.snapshot(0)
        assert time.monotonic() - t0 < 0.5
        assert snap["rooms"]
    finally:
        release.set()

    hub.flush()
    hub.close_file()


def test_close_file_waits_for_pending_writes_before_closing(tmp_path: Path) -> None:
    # close_file() 处于「停止录制 → 日志归档改名」链路上：Windows 下句柄未关的文件 rename 必抛
    # PermissionError，故必须等已入队事件真正落盘后再关；该把写盘挪进独立线程后，
    # 「已 accept 的事件一条都不能丢」只能靠这次排空保证。
    hub = DanmakuMonitorHub(log_path=str(tmp_path / "dm.jsonl"))
    log_file = tmp_path / "dm.jsonl"
    hub.room_started("房间A", "抖音直播")
    hub._stats_stop.set()  # 停掉周期 stats 线程：否则它可能在断言窗口内多写若干行
    _feed_chat(hub, "房间A", 30)
    hub.close_file()

    assert hub._file is None
    lines = log_file.read_text(encoding="utf-8").splitlines()
    # 1 条 conn/started + 展示流里的每一条（chat 按每秒采样，故与 snapshot 同口径）
    assert len(lines) == 1 + len(hub.snapshot(0)["messages"])

    # 关闭后惰性重开：下一条事件仍能落盘，且不会把上一条冲掉
    hub.room_message("房间A", "gift", "老板", "火箭×1")
    hub.close_file()
    after = log_file.read_text(encoding="utf-8").splitlines()
    assert len(after) == len(lines) + 1
    assert json.loads(after[-1])["type"] == "gift"


def test_hub_swallows_errors_without_raising() -> None:
    # 容错约束：监控枢纽任何异常都不得外抛（弹窗/录制流程不受影响）。
    hub = DanmakuMonitorHub(log_path=None)
    # 不存在的房间直接 close / 非法 online 文本等边界输入
    hub.room_closed("不存在的房间", "test")
    hub.room_message("不存在的房间", "online", "", "不是数字")
    hub.snapshot(-1)
    assert hub.snapshot(0)["last_seq"] >= 0


# ─── Collector：双模式与上报 ───────────────────────────────


def test_monitor_only_mode_writes_no_srt(tmp_path: Path) -> None:
    # 仅监控模式：write_srt=False 时不创建任何 SRT 文件，弹幕仍上报枢纽。
    hub = DanmakuMonitorHub(log_path=None)
    collector = DanmakuCollector(
        danmaku_cls=_BlockingDanmaku,
        danmaku_args={},
        base_filename=str(tmp_path / "video"),
        segment_seconds=None,
        room_name="房间A",
        platform_name="抖音直播",
        write_srt=False,
        monitor=hub,
    )
    collector.start()
    collector._on_message(DanmakuMessage(type=DanmakuMessageType.CHAT, user_name="用户", message="你好"))
    collector.stop(timeout=3)

    assert not list(tmp_path.glob("*.srt"))
    room = next(r for r in hub.snapshot(0)["rooms"] if r["name"] == "房间A")
    # 一条 chat 上报成功；采集线程未走到 on_ready，连接状态保持未连接。
    assert room["msg_total"] == 1
    assert room["connected"] is False


def test_collector_forwards_all_types_and_lifecycle(tmp_path: Path) -> None:
    # 全类型上报与连接状态上报：CHAT/GIFT/ONLINE 都到达枢纽；
    # start→started、_on_ready→connected、stop→closed。
    hub = DanmakuMonitorHub(log_path=None)
    collector = DanmakuCollector(
        danmaku_cls=_BlockingDanmaku,
        danmaku_args={},
        base_filename=str(tmp_path / "video"),
        segment_seconds=None,
        room_name="房间B",
        platform_name="B站直播",
        write_srt=False,
        monitor=hub,
    )
    collector.start()

    # 等待采集线程创建弹幕客户端并把 started 事件送达枢纽
    deadline = time.monotonic() + 3.0
    while time.monotonic() < deadline:
        if collector._danmaku is not None and any(r["name"] == "房间B" for r in hub.snapshot(0)["rooms"]):
            break
        time.sleep(0.02)
    rooms = hub.snapshot(0)["rooms"]
    room = next(r for r in rooms if r["name"] == "房间B")
    assert room["platform"] == "B站直播"

    danmaku = collector._danmaku
    assert danmaku is not None and danmaku._on_ready is not None
    danmaku._on_ready()
    assert next(r for r in hub.snapshot(0)["rooms"] if r["name"] == "房间B")["connected"] is True

    collector._on_message(DanmakuMessage(type=DanmakuMessageType.CHAT, user_name="u1", message="聊天"))
    collector._on_message(DanmakuMessage(type=DanmakuMessageType.GIFT, user_name="u2", message="送出 火箭×1"))
    collector._on_message(DanmakuMessage(type=DanmakuMessageType.ONLINE, user_name="", message="4321"))
    snap = hub.snapshot(0)
    room = next(r for r in snap["rooms"] if r["name"] == "房间B")
    assert room["msg_total"] == 1
    assert room["gift_total"] == 1
    assert room["online"] == 4321
    assert collector.message_count == 1  # SRT 口径仍只计 CHAT

    collector.stop(timeout=3)
    # stop 后采集线程退出，连接状态应回落为未连接（closed 事件已上报枢纽）。
    room = next(r for r in hub.snapshot(0)["rooms"] if r["name"] == "房间B")
    assert room["connected"] is False


def test_factory_passthrough_room_name_and_write_srt(tmp_path: Path) -> None:
    # 工厂透传：write_srt=False 采集器不创建 SrtWriter；平台不支持返回 None。
    from src import get_danmaku_collector

    collector = get_danmaku_collector(
        platform="抖音直播",
        danmaku_args={"room_id": "1"},
        base_filename=str(tmp_path / "v"),
        room_name="房间C",
        write_srt=False,
    )
    assert collector is not None
    assert collector._srt is None
    assert collector._room_name == "房间C"
    assert collector._platform_name == "抖音直播"

    # 平台不支持时工厂返回 None（不创建 SrtWriter/采集器），录制流程跳过弹幕。
    # 写入 None 分支：验证工厂对未知平台的安全降级，不抛异常。
    assert get_danmaku_collector(platform="不支持的平台", danmaku_args={}, base_filename=str(tmp_path / "v")) is None


def test_hub_thread_safety_under_concurrent_feed(tmp_path: Path) -> None:
    # 并发灌入（模拟多房间采集线程同时上报）不丢计数、不抛异常。
    hub = DanmakuMonitorHub(log_path=str(tmp_path / "dm.jsonl"))

    # 4 个房间各灌 50 条（并发写同一 hub）：验证无锁竞争丢计数、最终每房间 msg_total=50。
    def _worker(room: str) -> None:
        hub.room_started(room, "虎牙直播")
        for i in range(50):
            hub.room_message(room, "chat", f"u{i}", f"m{i}")

    threads = [threading.Thread(target=_worker, args=(f"房间{i}",)) for i in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        # 审查 7.11：裸 join() 在 hub 内部锁互锁时会把整轮 pytest 挂死（本用例
        # 正是「四线程并发灌同一 hub」的形态）。带上限把挂死变成判红，再用 is_alive 收口——
        # join 超时静默返回时下面的 snapshot 断言仍可能全绿，那是假绿。
        t.join(timeout=10)
    alive = [t.name for t in threads if t.is_alive()]
    assert not alive, f"并发灌入线程未在 10s 内退出（疑似 hub 锁竞争死锁）：{alive}"

    snap = hub.snapshot(0)
    assert len(snap["rooms"]) == 4
    # 每房间 50 条全部计入，无并发丢数（deque/锁正确）。
    for room in snap["rooms"]:
        assert room["msg_total"] == 50


# ─── Web API 端点 ─────────────────────────────────────────


def test_api_danmaku_endpoint_returns_hub_snapshot(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # /api/danmaku 返回注入枢纽的快照（认证关闭的本地配置）。
    from starlette.testclient import TestClient

    from src import web_api as wa

    hub = DanmakuMonitorHub(log_path=None)
    monkeypatch.setattr(dm, "get_hub", lambda: hub)

    cfg = tmp_path / "config.ini"
    cfg.write_text(
        "[Web]\nweb_host = 127.0.0.1\nweb_port = 8000\nweb_auth_enable = false\nweb_password = \n",
        encoding="utf-8-sig",
    )
    downloads = tmp_path / "downloads"
    downloads.mkdir()
    logs = tmp_path / "logs"
    logs.mkdir()
    app = wa.create_app(
        config_file=str(cfg),
        url_config_file=str(tmp_path / "URL_config.ini"),
        downloads_root=str(downloads),
        logs_dir=str(logs),
    )
    client = TestClient(app)
    try:
        hub.room_started("房间A", "抖音直播")
        hub.room_message("房间A", "chat", "用户", "你好世界")

        resp = client.get("/api/danmaku?since=0")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["rooms"][0]["name"] == "房间A"
        assert data["rooms"][0]["platform"] == "抖音直播"
        assert any(m["text"] == "你好世界" for m in data["messages"])
        assert data["last_seq"] > 0
    finally:
        client.close()


# ───（CODE_REVIEW_2026-10-21）：stats 线程复活窗口与裸文件名边车路径 ───


class _GapGate:
    # 一次性闸门：把「即将退出的 stats 线程」停在 finally 取锁的那一步，从而**确定性地**复现
    # break → finally 之间的窗口（该是竞态，没有外部可观测时序，只能在此注入停顿）。
    # 必须只停在**第二次**取锁：第一次是 while 体内的 `with self._lock`（它判完空表才 break），
    # 停在第一次的话房间登记会落进循环体、线程根本不退出（等于测了另一条路径）。
    # 只做「停 + 放行」，不重写任何被测逻辑（AGENTS「测试不得自实现被测逻辑」）。
    def __init__(self) -> None:
        self.acquisitions = 0
        self.reached = threading.Event()
        self.proceed = threading.Event()

    def __enter__(self) -> "_GapGate":
        self.acquisitions += 1
        if self.acquisitions >= 2:
            self.reached.set()
            assert self.proceed.wait(timeout=10.0), "测试未在 10s 内放行收尾线程"
        return self

    def __exit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None:
        return None


def test_stats_thread_restarts_for_room_registered_in_teardown_gap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # 房间在 break（当时房间表为空）与 finally 注销引用之间登记时，_ensure_stats_thread
    # 看到的是**仍 is_alive()** 的那支将死线程 → 不新建；随后它将 self._stats_thread 置 None 并退出，
    # 该房间从此**永久**拿不到周期 stats（GUI 的 msg_rate/online 冻结，直到下一条弹幕或下次开房才有机会）。
    monkeypatch.setattr(dm, "_STATS_INTERVAL", 0.02)
    hub = DanmakuMonitorHub(log_path=str(tmp_path / "dm.jsonl"))
    gate = _GapGate()
    real_lock = hub._lock
    # 先把锁换成闸门：stats 线程 break 后就会停在 finally 的 `with self._lock` 处
    hub._lock = cast(Any, gate)
    dying = threading.Thread(target=hub._stats_loop, name="stats-dying", daemon=True)
    hub._stats_thread = dying
    dying.start()
    assert gate.reached.wait(3.0), "stats 线程未到达 finally：窗口未复现"

    # 窗口内登记房间（换回真锁才能调用公开接口；将死线程此刻仍停在闸门外）
    hub._lock = real_lock
    hub.room_started("房间A", "抖音直播")
    assert hub._stats_thread is dying, "登记时旧线程已注销：本用例没有命中要复现的窗口"

    gate.proceed.set()
    dying.join(timeout=3.0)
    assert not dying.is_alive(), "将死线程未在 3s 内退出：不得判绿"

    replacement = hub._stats_thread
    assert replacement is not None and replacement is not dying, "注销后未复检房间表：新房间永远没有周期统计"

    deadline = time.monotonic() + 5.0
    stats_events: list[dict[str, Any]] = []
    while time.monotonic() < deadline and not stats_events:
        hub.flush()
        if (tmp_path / "dm.jsonl").exists():
            stats_events = [
                ev
                for ev in (json.loads(ln) for ln in (tmp_path / "dm.jsonl").read_text(encoding="utf-8").splitlines())
                if ev.get("ev") == "stats" and ev.get("room") == "房间A"
            ]
        time.sleep(0.05)
    assert stats_events, "替代线程没有为该房间写出周期统计"

    # 收尾：先摘房间（否则按修复语义线程会一直复活），再置停止位并 join 替代线程
    hub.room_stopped("房间A")
    hub._stats_stop.set()
    replacement.join(timeout=3.0)
    assert not replacement.is_alive(), "替代线程未在 3s 内退出：守护线程会残留到进程结束"


def test_prepare_log_path_keeps_file_output_for_bare_filename(tmp_path: Path) -> None:
    # os.makedirs(os.path.dirname(log_path)) 在裸文件名（无目录段）下 dirname 返回空串，
    # makedirs("") 抛 FileNotFoundError 被下面的 except 吞掉 → 边车输出**静默禁用**，
    # GUI/Web 的 tail 链路整体失效（用户只看到「监控页永远空白」）。
    assert DanmakuMonitorHub._prepare_log_path("danmaku_monitor.jsonl") == "danmaku_monitor.jsonl"
    # 反向保证：父目录确实会被创建（不得把 guard 写成「一律不建目录」）
    nested = tmp_path / "sub" / "dm.jsonl"
    assert DanmakuMonitorHub._prepare_log_path(str(nested)) == str(nested)
    assert (tmp_path / "sub").is_dir()
    # 第三向：真正不可创建的父目录仍走「禁用文件输出」出口——guard 不得把 except 路径一并废掉
    blocker = tmp_path / "afile"
    blocker.write_text("x", encoding="utf-8")
    assert DanmakuMonitorHub._prepare_log_path(str(blocker / "sub" / "dm.jsonl")) is None
