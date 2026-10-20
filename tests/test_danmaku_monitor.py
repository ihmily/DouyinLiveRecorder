# 弹幕监控测试（离线，不依赖网络 / 真实弹幕 WS）。覆盖：
# 1. DanmakuMonitorHub：统计精确性（不受采样影响）、展示流采样折叠、礼物/在线处理、
#    seq 增量游标、连接状态生命周期、JSONL 合法性与轮转；
# 2. DanmakuCollector 双模式：write_srt=False 不落 SRT、全类型消息上报、连接状态上报；
# 3. get_danmaku_collector 工厂透传 room_name / write_srt；
# 4. Web API /api/danmaku 端点返回枢纽快照；
# 5. GUI 弹幕监控（无头）：JSONL 事件分发到线程安全状态、边车文件 tail（含轮转回绕）。
#    M-24：tail 用例的停止信号必须发给**传入线程的那只 Event** 并断言线程已退出；
#    M-31②：gui 在**用例内**导入，配套 autouse fixture 成对还原 DLR_GUI_PARENT。

import asyncio
import json
import threading
import time
from collections import deque
from pathlib import Path
from typing import Any

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
    hub.flush()  # MID-25：落盘已挪到独立写线程，读文件前须先等队列排空
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
    hub.flush()  # MID-25：轮转发生在写线程里，断言前先等队列排空
    assert log_file.exists()
    content = log_file.read_text(encoding="utf-8")
    for line in content.splitlines():
        assert json.loads(line)  # 每行可解析
    # 超阈值后原文件重命名为 .1 备份，新文件继续写入（轮转不丢历史）。
    assert (tmp_path / "dm.jsonl.1").exists()


def test_sidecar_write_does_not_hold_hub_lock(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # MID-25 主用例：磁盘 IO 不得发生在 hub._lock 内。旧实现 open/write/flush 全在锁里，
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
    # PermissionError，故必须等已入队事件真正落盘后再关；MID-25 把写盘挪进独立线程后，
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
        # 审查 7.11（2026-10-18）：裸 join() 在 hub 内部锁互锁时会把整轮 pytest 挂死（本用例
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


# ─── GUI 弹幕监控（无头，不创建 Tk 窗口） ───────────────────


# M-31②（2026-09-29 审查）：本文件此前在模块级 `gui = pytest.importorskip("gui")`，于是收集期就
# 把 DLR_GUI_PARENT=1 注进整个会话（gui.py 在 import 期写入该变量），与「不在 pytest 进程 import
# gui」的既定约定冲突。现改为用例内经 _load_gui() 取模块，并由下面的 autouse fixture 成对还原。
# 残余风险（如实记录，不得当作已彻底解决）：① sys.modules 里的 gui 不会随用例结束消失，后续用例
# 再 import 仍是命中缓存（不再重复写 env，无二次污染）；② src/logger.py 的「GUI 父进程」判定只在
# 导入期读一次该变量，本文件模块级 import 早于任何用例内的 gui 导入，故 logger 落定的仍是「非 GUI
# 父进程」；若某个会话让别的文件先 import gui，靠下游用例各自的 monkeypatch.delenv 兜住。
def _load_gui() -> Any:
    return pytest.importorskip("gui", reason="gui 导入失败时跳过 GUI 无头测试（阶段5 起 gui 已不依赖 customtkinter)")


@pytest.fixture(autouse=True)
def _isolate_gui_parent_env_marker(monkeypatch: pytest.MonkeyPatch) -> None:
    # 进入用例前抹掉标记，退出时由 monkeypatch 恢复进入时的原值 —— 一律用
    # monkeypatch.setenv/delenv，禁止 patch.dict(os.environ)（harness 注入的 MCP 配置
    # 整体快照超 32767 上限，写回即抛 ValueError；见 AGENTS「环境变量一律用 monkeypatch」）。
    import src.logger as logger_mod

    monkeypatch.delenv(logger_mod.GUI_PARENT_ENV, raising=False)


# 构造仅含弹幕监控状态字段的 LiveRecorderGUI 桩实例（object.__new__ 跳过 Tk 初始化），
# 供 _danmaku_dispatch / _danmaku_tail_loop 无头驱动。
def _make_gui_stub(app_root: Path, gui: Any) -> Any:
    stub = object.__new__(gui.LiveRecorderGUI)
    stub._danmaku_lock = threading.Lock()
    stub._danmaku_rooms = {}
    stub._danmaku_msgs = deque(maxlen=300)  # 300 与生产端展示流环形缓冲上限一致，保证 tail 截断行为可比
    stub._danmaku_stats_dirty = False
    stub._danmaku_stream_dirty = False
    stub._danmaku_tail_stop = threading.Event()
    # M-17 的留痕走 self._log（tail 线程只写队列、不触碰 Tk），桩把它收成列表即可断言。
    stub._log_lines = []
    stub._log = lambda message, level="info": stub._log_lines.append((message, level))
    stub._CHAIN_WARN_INTERVAL_SECONDS = 0.0
    stub.app_root = str(app_root)
    return stub


def test_gui_dispatch_maps_events_to_state() -> None:
    # JSONL 事件 → GUI 状态映射：conn 建房/连接、msg 入流、stats 为统计权威来源。
    import tempfile

    gui = _load_gui()
    with tempfile.TemporaryDirectory() as tmp:
        stub = _make_gui_stub(Path(tmp), gui)
        # conn 事件建房（started）：房间进入监控表但尚未连接。
        gui.LiveRecorderGUI._danmaku_dispatch(
            stub, {"ev": "conn", "room": "房间A", "platform": "抖音直播", "state": "started", "ts": 1700000000.0}
        )
        gui.LiveRecorderGUI._danmaku_dispatch(stub, {"ev": "conn", "room": "房间A", "state": "ready"})
        assert stub._danmaku_rooms["房间A"]["connected"] is True

        gui.LiveRecorderGUI._danmaku_dispatch(
            stub, {"ev": "msg", "seq": 1, "room": "房间A", "type": "chat", "user": "u", "text": "hi", "ts": 1.0}
        )
        assert len(stub._danmaku_msgs) == 1
        assert stub._danmaku_stream_dirty is True
        # stats 事件为统计权威来源：覆盖 msg_total/msg_rate/online，并置 stats_dirty 触发刷新。
        gui.LiveRecorderGUI._danmaku_dispatch(
            stub,
            {
                "ev": "stats",
                "room": "房间A",
                "platform": "抖音直播",
                "connected": True,
                "msg_total": 99,
                "msg_rate": 12,
                "gift_total": 3,
                "online": 800,
            },
        )
        info = stub._danmaku_rooms["房间A"]
        assert info["msg_total"] == 99 and info["msg_rate"] == 12 and info["online"] == 800
        assert stub._danmaku_stats_dirty is True

        gui.LiveRecorderGUI._danmaku_dispatch(stub, {"ev": "conn", "room": "房间A", "state": "closed", "reason": "r"})
        assert stub._danmaku_rooms["房间A"]["connected"] is False


def test_gui_dispatch_stopped_removes_room() -> None:
    # stopped 事件（房间线程退出：URL 被移除/注释）→ GUI 从监控表移除房间行，
    # 不再显示已失效直播间及其旧弹幕数据
    import tempfile

    gui = _load_gui()
    with tempfile.TemporaryDirectory() as tmp:
        stub = _make_gui_stub(Path(tmp), gui)
        gui.LiveRecorderGUI._danmaku_dispatch(
            stub, {"ev": "conn", "room": "房间A", "platform": "虎牙直播", "state": "started", "ts": 1.0}
        )
        assert "房间A" in stub._danmaku_rooms
        gui.LiveRecorderGUI._danmaku_dispatch(stub, {"ev": "conn", "room": "房间A", "state": "stopped"})
        assert "房间A" not in stub._danmaku_rooms
        # 移除房间后置 stats_dirty，触发 GUI 监控表重绘（清掉已失效直播间行）。
        assert stub._danmaku_stats_dirty is True


def test_gui_tail_reads_jsonl_and_handles_rotation(tmp_path: Any) -> None:
    # tail 集成：写事件文件 → tail 线程读取入状态；文件变小（轮转回绕）时从头重读不崩溃；
    # 以及 M-24：对**传入的那只 Event** set 之后，线程必须真的退出。
    import os

    gui = _load_gui()
    logs = tmp_path / "logs"
    logs.mkdir()
    log_file = logs / "danmaku_monitor.jsonl"

    # _write 以追加模式写事件行，模拟监控枢纽的 JSONL 落盘（tail 线程随后读取）。
    def _write(lines: list[str]) -> None:
        with open(log_file, "a", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")

    _write(
        [
            json.dumps({"ev": "conn", "room": "房间A", "platform": "B站直播", "state": "started", "ts": 1.0}),
            json.dumps({"ev": "conn", "room": "房间A", "state": "ready"}),
            json.dumps({"ev": "msg", "seq": 1, "room": "房间A", "type": "chat", "user": "u", "text": "m1", "ts": 1.0}),
        ]
    )

    stub = _make_gui_stub(tmp_path, gui)
    # MID-2250 连带修正：_danmaku_tail_loop 的退出标志是**逐次创建的局部 Event 形参**（原读
    # 共享的 self._danmaku_tail_stop，会被新一轮 clear() 抹掉退出信号 → 线程永不退出），故必须
    # 作为第二个实参传入。M-24（严重假绿）：这只 Event 必须落到**局部变量**并在末尾 set 它——
    # 旧写法 set 的是 stub._danmaku_tail_stop（生产签名根本不读），join 必然等满又缺 is_alive 断言，
    # 「轮转后能停」从未被验证过。
    stop = threading.Event()
    t = threading.Thread(target=gui.LiveRecorderGUI._danmaku_tail_loop, args=(stub, stop), daemon=True)
    t.start()

    # 等待 tail 线程读取 JSONL 并分发：房间A 进入监控表、消息入展示流（带锁读取避免竞态）。
    deadline = time.monotonic() + 3.0
    while time.monotonic() < deadline:
        with stub._danmaku_lock:
            if len(stub._danmaku_msgs) >= 1 and "房间A" in stub._danmaku_rooms:
                break
        time.sleep(0.05)
    with stub._danmaku_lock:
        assert stub._danmaku_rooms["房间A"]["connected"] is True
        assert len(stub._danmaku_msgs) == 1

    # 模拟轮转：截断文件后写入新事件（size < offset 触发从头重读）
    with open(log_file, "w", encoding="utf-8") as f:
        f.write(
            json.dumps({"ev": "conn", "room": "房间B", "platform": "斗鱼直播", "state": "started", "ts": 2.0}) + "\n"
        )
    deadline = time.monotonic() + 3.0
    while time.monotonic() < deadline:
        with stub._danmaku_lock:
            if "房间B" in stub._danmaku_rooms:
                break
        time.sleep(0.05)

    # 轮转回绕后被 tail 正确读取到房间B；停止 tail 线程并断言房间B 入表。
    with stub._danmaku_lock:
        assert "房间B" in stub._danmaku_rooms, "轮转回绕后 tail 未读到房间B"
    assert os.path.exists(log_file)

    # M-24 的本体：set **传入线程的那只** Event，线程必须在预算内自行退出。
    stop.set()
    t.join(timeout=3.0)
    assert not t.is_alive(), "tail 线程未响应传入的 stop_event 退出（守护线程会残留到进程结束）"
