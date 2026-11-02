# -*- coding: utf-8 -*-
# DanmakuCollector 内部 SRT 写盘线程解耦回归。
#
# 旧实现：_on_message 在事件循环里同步调 srt.write，文件 I/O（Windows 上偶发的杀软索引、
# 句柄释放）会阻塞 ws_recv → 心跳超时、对端误判断连。新实现：_on_message 只做 O(1) 入队，
# 独立守护线程消费队列并落盘。
#
# 守护：① 写线程存在且 daemon=True；② stop() 顺序为「sentinel → join 写线程 → srt.close」
# （与「srt.close 兜底刷尾」一致）；③ 端到端 start → 推送 → stop 后 SRT 落盘且内容正确；
# ④ 仅监控模式（write_srt=False）不创建写线程与队列写入。

import time
from pathlib import Path
from typing import Any, cast

import pytest

from src.base import DanmakuMessage, DanmakuMessageType
from src.collector import DanmakuCollector
from src.danmaku_monitor import DanmakuMonitorHub
from src.srt_writer import SrtWriter


class _FakeDanmaku:
    # 空实现的弹幕客户端：start 直接挂起直到外部 close；stop 立即返回。
    def __init__(self, **kwargs: Any) -> None:
        pass

    async def start(self, args: Any) -> None:
        # 用 asyncio.sleep 挂起，让采集线程长期驻留以验证写线程独立工作
        import asyncio

        await asyncio.sleep(60)

    async def stop(self) -> None:
        return None

    def decode_message(self, data: Any) -> None:
        return None

    async def heartbeat(self) -> None:
        return None


def test_srt_writer_thread_created_and_daemon(tmp_path: Path) -> None:
    # write_srt=True 时应创建 SRT 写盘守护线程，名字含类名前缀便于排查
    collector = DanmakuCollector(
        danmaku_cls=cast(Any, _FakeDanmaku),
        danmaku_args={},
        base_filename=str(tmp_path / "video"),
        segment_seconds=None,
    )
    collector.start()
    try:
        # 写线程已启动
        assert collector._srt_writer is not None
        assert collector._srt_writer.is_alive()
        assert collector._srt_writer.daemon is True
        assert collector._srt_writer.name.startswith("srt_writer_")
    finally:
        collector.stop(timeout=2.0)
    # stop 后写线程已退出
    assert collector._srt_writer is not None
    assert not collector._srt_writer.is_alive()


def test_srt_not_written_when_write_srt_false(tmp_path: Path) -> None:
    # 仅监控模式（write_srt=False）：不创建 SrtWriter、不创建写线程、不入队 SRT
    collector = DanmakuCollector(
        danmaku_cls=cast(Any, _FakeDanmaku),
        danmaku_args={},
        base_filename=str(tmp_path / "video"),
        segment_seconds=None,
        write_srt=False,
    )
    collector.start()
    try:
        assert collector._srt is None
        assert collector._srt_writer is None
        # 推消息：应不抛、不入队（_srt is None 分支短路）
        collector._on_message(DanmakuMessage(type=DanmakuMessageType.CHAT, user_name="u", message="m"))
    finally:
        collector.stop(timeout=2.0)


def test_stop_drains_queue_and_writes_srt(tmp_path: Path) -> None:
    # 端到端：start → 推 N 条弹幕 → stop → SRT 文件被正确写入 N 条字幕块
    base = str(tmp_path / "live")
    collector = DanmakuCollector(
        danmaku_cls=cast(Any, _FakeDanmaku),
        danmaku_args={},
        base_filename=base,
        segment_seconds=None,
    )
    collector.start()
    # 给写线程一点启动时间（start 已拉起线程，这里只是保险）
    time.sleep(0.05)
    for i in range(5):
        collector._on_message(DanmakuMessage(type=DanmakuMessageType.CHAT, user_name=f"用户{i}", message=f"弹幕{i}"))
    collector.stop(timeout=2.0)
    # 验证 SRT 文件落盘：5 条字幕块，每块 4 行（序号/时间/文本/空行）
    srt_path = base + ".srt"
    content = Path(srt_path).read_text(encoding="utf-8")
    assert content.count("-->") == 5
    for i in range(5):
        assert f"用户{i}: 弹幕{i}" in content


def test_stop_calls_srt_close_exactly_once(tmp_path: Path) -> None:
    # 守护：srt.close() 在 stop() 中只调一次（写线程 join 后才关 srt），
    # 防止重复关闭抛 ValueError（I/O on closed file）
    collector = DanmakuCollector(
        danmaku_cls=cast(Any, _FakeDanmaku),
        danmaku_args={},
        base_filename=str(tmp_path / "x"),
        segment_seconds=None,
    )
    srt = collector._srt
    assert srt is not None
    close_spy = []
    real_close = srt.close

    def spy_close() -> None:
        close_spy.append(1)
        real_close()

    srt.close = spy_close  # type: ignore[method-assign]
    collector.start()
    time.sleep(0.05)
    collector.stop(timeout=2.0)
    assert len(close_spy) == 1


def test_on_message_does_not_block_event_loop(tmp_path: Path) -> None:
    # 关键回归：_on_message 本身应在亚毫秒内返回（仅 O(1) 入队），不再被 srt.write 的文件 I/O
    # 阻塞。模拟慢速 srt.write：写线程卡住 200ms 时，_on_message 仍须在 10ms 内返回。
    collector = DanmakuCollector(
        danmaku_cls=cast(Any, _FakeDanmaku),
        danmaku_args={},
        base_filename=str(tmp_path / "slow"),
        segment_seconds=None,
    )
    collector.start()
    time.sleep(0.05)
    # 替换 _srt.write 为慢速版（200ms）：写线程消费时被卡住，但入队不应受它影响
    srt = collector._srt
    assert srt is not None

    def slow_write(user: str, msg: str, now: Any = None) -> None:
        time.sleep(0.2)
        # 仍用原 write 落盘，200ms 只是人为放大写线程的阻塞窗口
        cast(Any, SrtWriter.write)(srt, user, msg, now=now)

    # mypy 报 assignment（写实例属性）、basedpyright 报 method-assign，两种码都要压制
    srt.write = slow_write  # type: ignore[assignment, method-assign]
    t0 = time.monotonic()
    for i in range(10):
        collector._on_message(DanmakuMessage(type=DanmakuMessageType.CHAT, user_name=f"u{i}", message=f"m{i}"))
    elapsed = time.monotonic() - t0
    # 10 次入队总耗时应远低于 10 * 200ms = 2000ms（若 10 次均 < 50ms 则说明入队与写盘解耦）
    assert elapsed < 0.5, f"_on_message 入队疑似被写盘阻塞: {elapsed * 1000:.0f}ms"
    collector.stop(timeout=5.0)
