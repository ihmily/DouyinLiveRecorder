# DanmakuCollector 生命周期回归（CODE_REVIEW_2026-09-20 的 / / ，及）。
#
# 全部离线：平台弹幕客户端用桩替代，不触网、不起真实 WS。
#
# 覆盖的不变量：
#   ① ：stop() 不得在「_loop 已发布、尚未 run_until_complete」的窗口丢停止信号；
#   ② ：SRT sentinel 一律非阻塞投递，队列满时由写线程自检退出，
#      且 sentinel 失败绝不阻断 srt.close()（否则录制并发槽在 try 内路径上永久泄漏）；
#   ③ ：停 loop 前先 cancel danmaku.start() 任务并让取消传播，
#      使平台 start() 的 finally 清理链真的跑完；
#   ④ ：start() 非原子——任一步抛错（实测可达形态 RuntimeError: can't start new thread）
#      后不得留在「半启动」状态；stop() 里两处 join 绝不能因为「线程从未成功 start()」就抛错、
#      跳过末尾的 self._srt.close()（SRT 句柄泄漏，Windows 上该 .srt 在 GC 前无法改名，会打挂改名逻辑）。
#
# 另附该写线程侧：get() 带超时 + _srt_stop 自检，队列空时能自行退出。
#
# CODE_REVIEW_2026-10-21 追加两条不变量（改回旧形态即应转红）：
#   ⑤ 该采集线程 join 超时后必须复查 is_alive() 并留 warning——join(timeout) 超时是静默返回，
#           旧写法不复查，卡死的线程（连同事件循环与监控房间条目）在日志里完全隐形；
#           同时钉住「新增判定不得改变 srt.close() 的调用顺序」（该槽位泄漏契约）。
#   ⑥ 该平台类**构造期**与回调注入阶段的异常不得逃出守护线程：必须落一条脱敏 warning
#           并把房间上报为已关闭，否则面板停在「采集中」、监控条目永不上报关闭。

import asyncio
import io
import json
import queue
import threading
import time
import types
from collections.abc import Iterator
from pathlib import Path
from typing import Any, cast

import pytest
from loguru import logger

import src.collector as collector_module
from src.collector import DanmakuCollector
from src.danmaku_monitor import DanmakuMonitorHub


# 构造期即阻塞的弹幕客户端替身：模拟 _run 发布 self._loop 之后、进入 run_until_complete
# 之前那段「正在实例化平台 SDK」的窗口（真实形态为数毫秒到数百毫秒）。
class _SlowConstructDanmaku:
    _entered: threading.Event = threading.Event()
    _release: threading.Event = threading.Event()
    start_called = False

    def __init__(self, **kwargs: Any) -> None:
        type(self)._entered.set()
        assert type(self)._release.wait(timeout=10), "测试未在 10s 内放行构造函数"

    async def start(self, args: Any) -> None:
        type(self).start_called = True
        await asyncio.sleep(60)

    async def stop(self) -> None:
        return None

    async def heartbeat(self) -> None:
        return None

    def decode_message(self, data: Any) -> None:
        return None


# start() 内含 finally 清理链、且常驻不自行退出的弹幕客户端替身（该用）。
class _FinallyChainDanmaku:
    finally_ran = threading.Event()

    def __init__(self, **kwargs: Any) -> None:
        return None

    async def start(self, args: Any) -> None:
        try:
            await asyncio.sleep(60)
        finally:
            # 平台 start() 里的清理链（关连接、失效缓存等）——只有取消真正送达才会执行
            type(self).finally_ran.set()

    async def stop(self) -> None:
        return None

    async def heartbeat(self) -> None:
        return None

    def decode_message(self, data: Any) -> None:
        return None


# 只做监控、不落 SRT 的采集器（本文件多数用例只关心线程生命周期）。
def _monitor_only(tmp_path: Path, danmaku_cls: Any, monitor: DanmakuMonitorHub) -> DanmakuCollector:
    return DanmakuCollector(
        danmaku_cls=cast(Any, danmaku_cls),
        danmaku_args={},
        base_filename=str(tmp_path / "video"),
        segment_seconds=None,
        room_name="房间A",
        platform_name="抖音直播",
        write_srt=False,
        monitor=monitor,
    )


def test_stop_signal_not_dropped_during_client_construction(tmp_path: Path) -> None:
    # 主用例：复现「loop 已发布但未 running」的丢信号窗口。
    # 旧实现在此刻 is_running() 为 False → 整段 call_soon_threadsafe 被跳过 → 信号永久丢失
    # → join(8) 超时、采集线程与监控房间条目全部滞留。
    _SlowConstructDanmaku.start_called = False
    _SlowConstructDanmaku._entered.clear()
    _SlowConstructDanmaku._release.clear()
    collector = _monitor_only(tmp_path, _SlowConstructDanmaku, DanmakuMonitorHub(log_path=None))
    collector.start()
    assert _SlowConstructDanmaku._entered.wait(3), "采集线程未进入客户端构造阶段"
    loop = collector._loop
    assert loop is not None
    # 窗口成立的前提：loop 已发布但尚未开始运行（旧实现正是在这里丢掉信号）
    assert not loop.is_running()

    # stop() 的有界等待期间放行构造，模拟真实的「构造完成 → 即将进入 run_until_complete」
    timer = threading.Timer(0.1, _SlowConstructDanmaku._release.set)
    timer.start()
    started = time.monotonic()
    try:
        collector.stop(timeout=3.0)
    finally:
        _SlowConstructDanmaku._release.set()
        timer.join(timeout=2)

    thread = collector._thread
    assert thread is not None and not thread.is_alive(), "采集线程未退出：停止信号被丢弃"
    # 二次复查兜底：信号已在建连前送达，绝不该再进入 danmaku.start()
    assert _SlowConstructDanmaku.start_called is False
    assert time.monotonic() - started < 3.0


class _LateRunningLoop:
    # 只在若干毫秒后才「进入 running」的假 loop，用于单测 stop() 的有界等待半段。
    def __init__(self, delay: float) -> None:
        self._deadline = time.monotonic() + delay
        self.scheduled = 0

    def is_running(self) -> bool:
        return time.monotonic() >= self._deadline

    def is_closed(self) -> bool:
        return False

    def call_soon_threadsafe(self, callback: Any, *args: Any) -> None:
        self.scheduled += 1


def test_stop_waits_bounded_for_loop_before_scheduling(tmp_path: Path) -> None:
    # 投递侧：loop 稍后才 running 时，stop() 必须等到那一刻再投递，
    # 而不是「此刻不在跑就永久放弃」。
    collector = _monitor_only(tmp_path, _FinallyChainDanmaku, DanmakuMonitorHub(log_path=None))
    loop = _LateRunningLoop(0.15)
    collector._started = True
    cast(Any, collector)._loop = loop
    collector._thread = None

    collector.stop(timeout=1.0)

    assert loop.scheduled == 1, "loop 进入 running 后仍未收到停止投递"


def test_monitor_hub_and_writer_thread_survive_full_queue(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # 队列满 + 写线程卡在 flush 时，stop() 必须**照常返回**并把 srt.close() 走到，
    # 否则录制线程挂死在 try 内路径上、_rec_sem 的槽位永不归还。
    monkeypatch.setattr(collector_module, "_SRT_QUEUE_MAXSIZE", 1)
    collector = DanmakuCollector(
        danmaku_cls=cast(Any, _FinallyChainDanmaku),
        danmaku_args={},
        base_filename=str(tmp_path / "video"),
        segment_seconds=None,
        monitor=DanmakuMonitorHub(log_path=None),
    )
    closed: list[int] = []
    srt = collector._srt
    assert srt is not None
    real_close = srt.close

    def _spy_close() -> None:
        closed.append(1)
        real_close()

    cast(Any, srt).close = _spy_close

    # 手工进入「已启动 + 写线程卡死」形态：真实场景里写线程卡在阻塞 flush() 上，
    # 队列被填满，此时 sentinel 无处可去——旧实现的阻塞 put 就挂死在这里。
    class _NeverExit:
        # 写线程替身：join 到期仍「存活」。
        # ident 必须给出非 None（ stop() 侧改用 `ident is None` 判定
        # 「该线程可 join」，替身不实现它就会 AttributeError；真实形态里写线程已 start 成功，
        # 只是卡在阻塞 flush() 上，故 ident 早已就绪）。
        ident = 1

        def join(self, timeout: float | None = None) -> None:
            return None

        def is_alive(self) -> bool:
            return True

    collector._started = True
    collector._thread = None
    collector._srt_queue.put(("u", "m", 0.0))
    collector._srt_writer = cast(Any, _NeverExit())

    started = time.monotonic()
    collector.stop(timeout=1.0)
    elapsed = time.monotonic() - started

    assert elapsed < 5.0, f"stop() 疑似被阻塞的 sentinel 挂住: {elapsed:.1f}s"
    assert collector._srt_stop.is_set(), "队列满时未置 _srt_stop，写线程无从自检退出"
    assert closed == [1], "sentinel 失败阻断了 srt.close()"


def test_srt_writer_loop_self_exits_on_stop_event(tmp_path: Path) -> None:
    # 写线程侧：sentinel 没投进来时，队列为空 + _srt_stop 置位即自行退出。
    # 旧实现的 get() 无超时、也不看任何事件，此场景下永不返回（线程与句柄双泄漏）。
    collector = DanmakuCollector(
        danmaku_cls=cast(Any, _FinallyChainDanmaku),
        danmaku_args={},
        base_filename=str(tmp_path / "video"),
        segment_seconds=None,
        monitor=DanmakuMonitorHub(log_path=None),
    )
    collector._srt_stop.set()
    writer = threading.Thread(target=collector._srt_writer_loop, daemon=True)
    writer.start()
    writer.join(timeout=3.0)
    assert not writer.is_alive(), "写线程未在 _srt_stop 置位后自检退出"


def test_srt_writer_drains_pending_items_before_exit(tmp_path: Path) -> None:
    # 反向保证：_srt_stop 置位但队列里还有弹幕时，必须**先消费完**再退出（不得多丢一条）。
    collector = DanmakuCollector(
        danmaku_cls=cast(Any, _FinallyChainDanmaku),
        danmaku_args={},
        base_filename=str(tmp_path / "video"),
        segment_seconds=None,
        monitor=DanmakuMonitorHub(log_path=None),
    )
    srt = collector._srt
    assert srt is not None
    srt.start(now=0.0)
    written: list[tuple[str, str]] = []
    collector._srt_queue.put(("u1", "m1", 0.1))
    collector._srt_queue.put(("u2", "m2", 0.2))
    collector._srt_stop.set()

    def _slow_write(user_name: str, message: str, now: float | None = None) -> None:
        # 写第一条的过程中置停止事件（真实形态：stop() 与写线程并发）
        collector._srt_stop.set()
        written.append((user_name, message))

    cast(Any, srt).write = _slow_write
    writer = threading.Thread(target=collector._srt_writer_loop, daemon=True)
    writer.start()
    writer.join(timeout=3.0)

    assert not writer.is_alive()
    assert written == [("u1", "m1"), ("u2", "m2")], "队列未排空就退出，丢掉了已入队的弹幕"


def test_shutdown_cancels_start_task_and_runs_finally_chain(tmp_path: Path) -> None:
    # _shutdown 直接 loop.stop() 会让 danmaku.start() 的任务以 pending 态被
    # 销毁（stderr 刷「Task was destroyed but it is pending」），且平台 start() 的
    # finally 清理链永不执行。现在必须先 cancel + 让出一轮，再停 loop。
    _FinallyChainDanmaku.finally_ran.clear()
    collector = _monitor_only(tmp_path, _FinallyChainDanmaku, DanmakuMonitorHub(log_path=None))
    collector.start()
    deadline = time.monotonic() + 3.0
    while time.monotonic() < deadline:
        loop = collector._loop
        if loop is not None and loop.is_running():
            break
        time.sleep(0.02)
    assert collector._loop is not None and collector._loop.is_running()

    collector.stop(timeout=3.0)

    assert _FinallyChainDanmaku.finally_ran.wait(2.0), "start() 的 finally 清理链未执行（任务被硬切）"
    thread = collector._thread
    assert thread is not None and not thread.is_alive()


def test_reverse_order_handshake_still_holds(tmp_path: Path) -> None:
    # 反向序握手回归锁（本仓硬约定，改任何一侧都会丢信号）：
    # stop() 先 set(_stop_event) 再读 _loop；_run 先发布 _loop 再检查 _stop_event。
    # 本用例固定「stop 早于采集线程建好 loop」这一交错：信号必须由 _run 侧接住。
    _SlowConstructDanmaku.start_called = False
    _SlowConstructDanmaku._entered.clear()
    # 预先置位：_run 一发布 loop 就看到停止信号，直接跳过建连
    collector = _monitor_only(tmp_path, _SlowConstructDanmaku, DanmakuMonitorHub(log_path=None))
    collector._stop_event.set()
    collector._started = True
    collector._thread = threading.Thread(target=collector._run, name="danmaku_probe", daemon=True)
    collector._thread.start()
    collector._thread.join(timeout=3.0)

    assert not collector._thread.is_alive()
    assert _SlowConstructDanmaku.start_called is False
    assert collector._loop is None
    # 队列仍在但已无消费者：sentinel 走非阻塞路径，不影响收尾
    assert isinstance(collector._srt_queue, queue.Queue)


@pytest.mark.parametrize("as_stop_arg", [True, False])
def test_stop_is_idempotent(tmp_path: Path, as_stop_arg: bool) -> None:
    # stop() 幂等：提前中断与 ffmpeg 正常退出两条路径都会触发，重复调用不得二次投递/二次关文件
    collector = _monitor_only(tmp_path, _FinallyChainDanmaku, DanmakuMonitorHub(log_path=None))
    collector.start()
    collector.stop(timeout=2.0)
    if as_stop_arg:
        collector.stop(timeout=2.0)
    assert collector._stop_called is True


# ---------------------------------------------------------------------------
# start() 半启动回滚 + stop() 的 join 不得阻断 srt.close()
# ---------------------------------------------------------------------------


def _make_thread_start_fail(monkeypatch: pytest.MonkeyPatch, victim_prefix: str, created: list) -> None:
    # 让名字以 victim_prefix 开头的线程 start() 抛 RuntimeError("can't start new thread")
    # ——80+ 房间 + 线程数触顶时的现实形态，其余线程照常起。
    # 绝不 patch stdlib 模块本体（会波及同进程 harness 守护线程），只把 collector 命名空间里的
    # 全局名 threading 换成浅拷贝替身。基类直接写 threading.Thread：本函数只替换
    # collector_module.threading，从不替换本测试模块的全局 threading，故这里取到的必是 stdlib 真身
    # （不先存 `real_thread = threading.Thread` 再当基类，是因为 mypy 禁止变量作基类）。
    class _NoStartThread(threading.Thread):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            super().__init__(*args, **kwargs)
            created.append(self)

        def start(self, *args: Any, **kwargs: Any) -> None:
            if self.name.startswith(victim_prefix):
                raise RuntimeError("can't start new thread")
            super().start(*args, **kwargs)

    shim = types.SimpleNamespace(**vars(collector_module.threading))
    shim.Thread = _NoStartThread
    monkeypatch.setattr(collector_module, "threading", shim)


def _srt_collector(tmp_path: Path) -> DanmakuCollector:
    return DanmakuCollector(
        danmaku_cls=cast(Any, _FinallyChainDanmaku),
        danmaku_args={},
        base_filename=str(tmp_path / "video"),
        segment_seconds=None,
        room_name="房间A",
        platform_name="B站直播",
        monitor=DanmakuMonitorHub(log_path=None),
    )


@pytest.mark.parametrize("victim_prefix", ["srt_writer", "danmaku"])
def test_start_rolls_back_when_a_thread_cannot_start(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, victim_prefix: str
) -> None:
    # 旧实现：start() 里没有 try（只有 self._srt.start() 有），RuntimeError 直接冒出——
    # 调用方 main.py 的 except 分支随即把 danmaku_collector 置 None，半启动对象连同
    # 已打开的 SRT 句柄、已空转的写线程一起失去引用，永不再被 close/join。
    created: list = []
    _make_thread_start_fail(monkeypatch, victim_prefix, created)
    collector = _srt_collector(tmp_path)
    srt = collector._srt
    assert srt is not None

    collector.start()  # 不得抛：本类承诺「弹幕失败不影响录像」

    assert collector._started is False, "start() 失败后仍留在半启动状态（stop() 会去 join 空线程）"
    assert collector._srt_writer is None
    assert collector._thread is None
    fp = srt._fp
    assert fp is not None, "前置条件：SRT 第 0 片应已在 start() 中被创建"
    # 已经起成功的线程（victim='danmaku' 时的写线程）不得被引用一起丢掉：
    # 它会在 get(timeout=0.5) 上空转到进程结束
    for thread in created:
        if thread.ident is not None:
            assert not thread.is_alive(), f"回滚丢下了空转线程 {thread.name}"

    collector.stop(timeout=2.0)
    collector.stop(timeout=2.0)  # 幂等
    assert fp.closed is True, "SRT 句柄未被关闭（Windows 上该文件在 GC 前无法改名）"


def test_stop_joins_only_started_threads(tmp_path: Path) -> None:
    # stop() 侧的独立锁：直接构造「持有从未 start() 的 Thread 引用」的形态。
    # 旧实现的两处 join 都会先抛 RuntimeError: cannot join thread before it is started，
    # 该异常从 stop() 逃出去就跳过末尾的 self._srt.close()。
    collector = _srt_collector(tmp_path)
    srt = collector._srt
    assert srt is not None
    srt.start()
    fp = srt._fp
    assert fp is not None

    collector._started = True
    collector._stop_called = False
    collector._thread = threading.Thread(target=lambda: None)
    collector._srt_writer = threading.Thread(target=collector._srt_writer_loop)

    collector.stop(timeout=1.0)

    assert fp.closed is True, "join 抛错跳过了 srt.close()"
    assert collector._stop_called is True


@pytest.fixture
def log_capture() -> Iterator[io.StringIO]:
    # 内存 sink 直接接管 loguru：本仓不把 loguru 桥接到 stdlib logging，caplog 抓不到
    # （与 tests/test_cookie_cache.py 的 log_capture 同一手法）。
    buf = io.StringIO()
    sink_id = logger.add(buf, format="{level} {message}", level="DEBUG")
    try:
        yield buf
    finally:
        try:
            logger.remove(sink_id)
        except ValueError:
            pass


class _AliveForeverThread:
    # 「join 到期仍存活」的线程替身：ident 必须给出非 None（_join_thread 以 ident is None
    # 判「可 join」），is_alive 恒真模拟卡在平台 SDK 里的采集线程。
    ident = 1

    def join(self, timeout: float | None = None) -> None:
        return None

    def is_alive(self) -> bool:
        return True


def test_stop_warns_when_capture_thread_outlives_join(tmp_path: Path, log_capture: io.StringIO) -> None:
    # join(timeout) 超时是**静默返回**，旧写法不复查存活就继续收尾，卡死的采集线程
    # （事件循环 + WS 连接 + 监控房间条目全部滞留）在日志里一条线索都不留。
    collector = _srt_collector(tmp_path)
    srt = collector._srt
    assert srt is not None
    srt.start()
    fp = srt._fp
    assert fp is not None

    collector._started = True
    collector._stop_called = False
    collector._thread = cast(Any, _AliveForeverThread())

    collector.stop(timeout=1.0)

    text = log_capture.getvalue()
    assert "停止流程收尾异常" in text, text
    assert "still alive after join(timeout=1.0s)" in text, text
    # 契约的另一半：新增的存活判定**不得**改变 srt.close() 的到达（录制并发槽泄漏防线）
    assert fp.closed is True, "采集线程未退出时跳过了 srt.close()：录制并发槽会永久泄漏"


class _RaisingConstructDanmaku:
    # 平台 SDK 在构造期即抛（缺依赖 / 参数校验失败 / 风控页解析异常都是这种形态）。
    # 异常文本内嵌带 token 的地址——既是该「异常不得逃出守护线程」触发器，
    # 也是该脱敏判据样本（断言口径是「密钥字符串确实从日志里消失」）。
    def __init__(self, **kwargs: Any) -> None:
        raise RuntimeError("connect failed https://ws.example/live?token=SECRETTOKEN40")

    async def start(self, args: Any) -> None:
        return None

    async def stop(self) -> None:
        return None

    async def heartbeat(self) -> None:
        return None

    def decode_message(self, data: Any) -> None:
        return None


def test_run_reports_closed_and_masks_when_construction_raises(tmp_path: Path, log_capture: io.StringIO) -> None:
    # 构造期异常此前裸奔在 _run 的 finally 之外——线程带 traceback 消失（无控制台进程里
    # 连 traceback 都没有），而监控枢纽条目仍停在 started，面板显示「采集中」直到录制结束。
    hub = DanmakuMonitorHub(log_path=str(tmp_path / "dm.jsonl"))
    collector = DanmakuCollector(
        danmaku_cls=cast(Any, _RaisingConstructDanmaku),
        danmaku_args={},
        base_filename=str(tmp_path / "video"),
        segment_seconds=None,
        room_name="房间A",
        platform_name="抖音直播",
        write_srt=False,
        monitor=hub,
    )
    collector.start()
    thread = collector._thread
    assert thread is not None
    thread.join(timeout=5)
    assert not thread.is_alive(), "构造期异常后采集线程未在 5s 内退出：不得判绿"
    assert collector._loop is None, "_run 的收尾 finally 未执行（事件循环引用未清）"

    hub.flush()
    events = [json.loads(line) for line in (tmp_path / "dm.jsonl").read_text(encoding="utf-8").splitlines()]
    closed = [
        ev for ev in events if ev.get("ev") == "conn" and ev.get("state") == "closed" and ev.get("room") == "房间A"
    ]
    assert closed, f"构造失败未把房间上报为已关闭：{events}"

    text = log_capture.getvalue()
    assert "SECRETTOKEN40" not in text, "异常文本未过 mask_credentials：凭据随轮转日志长期落盘"
    assert "RuntimeError" in text, text


def test_room_closed_reported_once_across_stop_and_on_close(tmp_path: Path) -> None:
    # hub.room_closed 在枢纽侧不去重（每次写一条新 seq 的 conn/closed 事件），
    # 而 stop() 与 _on_close 在「正常停止」时序里都会触发——双投让面板 closed 计数虚增。
    # 首投生效语义：哪种时序先到，哪种 reason 被保留，第二条一律吞掉。
    hub = DanmakuMonitorHub(log_path=str(tmp_path / "dm_a.jsonl"))
    collector = _monitor_only(tmp_path, _FinallyChainDanmaku, hub)
    collector.start()
    collector.stop(timeout=5)
    # 真实时序：stop() 引发 WS 关闭，_on_close 随后到达——不得再投第二条。
    collector._on_close("连接已关闭")
    hub.flush()
    events = [json.loads(line) for line in (tmp_path / "dm_a.jsonl").read_text(encoding="utf-8").splitlines()]
    closed = [
        ev for ev in events if ev.get("ev") == "conn" and ev.get("state") == "closed" and ev.get("room") == "房间A"
    ]
    assert len(closed) == 1, f"主动停止时序下 room_closed 双投未去重: {closed}"

    # 反向时序：意外掉线先触发 _on_close（真实关闭原因），随后的 stop() 收尾不再补投。
    hub_b = DanmakuMonitorHub(log_path=str(tmp_path / "dm_b.jsonl"))
    collector_b = _monitor_only(tmp_path, _FinallyChainDanmaku, hub_b)
    collector_b.start()
    collector_b._on_close("连接已关闭")
    collector_b.stop(timeout=5)
    hub_b.flush()
    events_b = [json.loads(line) for line in (tmp_path / "dm_b.jsonl").read_text(encoding="utf-8").splitlines()]
    closed_b = [
        ev for ev in events_b if ev.get("ev") == "conn" and ev.get("state") == "closed" and ev.get("room") == "房间A"
    ]
    assert len(closed_b) == 1, f"意外掉线时序下 room_closed 双投未去重: {closed_b}"
    assert closed_b[0].get("reason") == "连接已关闭", f"首投 reason 被后续路径覆盖: {closed_b}"
