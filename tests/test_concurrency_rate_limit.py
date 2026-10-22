# -*- encoding: utf-8 -*-
# 并发专项：对**生产代码**的「跨线程去重」与「同 host 探针限流」做真实断言。
#
# 教训（2026-09-10 审查）：早期版本在测试内自行实现锁 / 凭证缓存 / 限流器再断言自己，
# 把 src/ 的实现整个删掉仍全绿（典型假绿）。现改为直接驱动真实入口：
#   - src.ttwid.get_ttwid()               并发去重（多线程各自 asyncio.run，复刻房间线程模型）
#   - src.stream_select._throttle_probe() 同 host 探针最小间隔节流（真实限流器）
#
# 判据必须是「删掉生产实现就会失败」，因此这里只打桩网络层（_fetch_ttwid）与时间常量，
# 去重与节流逻辑本身一律走真实代码。
import asyncio
import threading
import time
from typing import Any

import pytest

import main  # noqa: F401  先完整初始化 main，打破 stream_select<->main 的循环导入
import src.stream_select as stream_select
import src.ttwid as ttwid_module


# 清空 ttwid 进程级缓存，并屏蔽 config.ini 的预置值：否则开发者本地填过 ttwid 时
# get_ttwid 会短路走配置分支，本用例的并发去重路径根本不被执行。
@pytest.fixture()
def _isolated_ttwid(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ttwid_module, "_cached_ttwid", "")
    monkeypatch.setattr(ttwid_module, "_read_config_ttwid", lambda: "")


# 重置探针节流状态，并把最小间隔压到极小、抖动置 0（模块注释明确允许测试调整这两个常量），
# 使用例既不牺牲断言强度又把耗时控制在毫秒级。
@pytest.fixture()
def _fast_probe_throttle(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(stream_select, "_PROBE_MIN_HOST_INTERVAL", 0.05)
    monkeypatch.setattr(stream_select, "_PROBE_THROTTLE_JITTER", 0.0)
    monkeypatch.setattr(stream_select, "_probe_last_seen", {})


class TestTtwidConcurrentDedup:
    # get_ttwid 的跨线程去重：并发调用只允许一次真实拉取，其余复用同一缓存值。

    def test_concurrent_threads_fetch_once(self, monkeypatch: pytest.MonkeyPatch, _isolated_ttwid: None) -> None:
        fetch_calls: list[int] = []

        async def fake_fetch(proxy_addr: Any = None) -> str:
            fetch_calls.append(1)
            # 让出控制权放大并发窗口：若去重失效，等待者会各自进入这里
            await asyncio.sleep(0.05)
            ttwid_module._cached_ttwid = "ttwid=shared"
            return ttwid_module._cached_ttwid

        monkeypatch.setattr(ttwid_module, "_fetch_ttwid", fake_fetch)

        results: list[str] = []
        errors: list[BaseException] = []
        collect_lock = threading.Lock()

        def worker() -> None:
            try:
                value = asyncio.run(ttwid_module.get_ttwid())
            except BaseException as e:  # 收集后在主线程统一断言，避免线程内断言丢失
                with collect_lock:
                    errors.append(e)
                return
            with collect_lock:
                results.append(value)

        threads = [threading.Thread(target=worker) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=15)
        # LT-03：join(timeout=15) **返回**不等于线程已退出——去重逻辑挂死时 join 只是超时静默返回，
        # errors 仍为空、fetch_calls 仍为 1，本用例照样判绿。必须逐线程确认 is_alive 为 False，
        # 才真正钉住「8 线程全部跑完」（口径同 tests/test_async_http_lock.py 的 LT-01）。
        for t in threads:
            assert not t.is_alive(), "join 超时后线程仍存活：跨线程去重逻辑挂死，不得判绿"

        assert not errors, f"并发调用抛出异常: {errors}"
        assert len(fetch_calls) == 1, f"并发去重失效: _fetch_ttwid 被调用 {len(fetch_calls)} 次（期望 1）"
        assert results == ["ttwid=shared"] * 8

    def test_failed_owner_does_not_stampede(self, monkeypatch: pytest.MonkeyPatch, _isolated_ttwid: None) -> None:
        # owner 拉取失败时，等待者必须**串行**接管重试。原实现在锁外直接 _fetch_ttwid，
        # 多个等待者会同时发起请求——正是 ttwid 模块要消除的「重复请求触发风控」。
        fetch_calls: list[int] = []
        inflight = 0
        concurrent_peak = 0
        guard = threading.Lock()

        async def failing_fetch(proxy_addr: Any = None) -> str:
            nonlocal inflight, concurrent_peak
            with guard:
                inflight += 1
                concurrent_peak = max(concurrent_peak, inflight)
                fetch_calls.append(1)
            await asyncio.sleep(0.03)
            with guard:
                inflight -= 1
            return ""

        monkeypatch.setattr(ttwid_module, "_fetch_ttwid", failing_fetch)

        def worker() -> None:
            asyncio.run(ttwid_module.get_ttwid())

        threads = [threading.Thread(target=worker) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=15)
        # LT-03：同上——「串行接管」判据（concurrent_peak == 1）对「线程根本没退出」完全隐形：
        # 等待者全挂死时峰值同样只记到 1。逐线程断言 is_alive 已为 False，才钉住「5 线程全部跑完」。
        for t in threads:
            assert not t.is_alive(), "join 超时后线程仍存活：等待者接管链挂死，不得判绿"

        assert fetch_calls, "owner 失败后等待者未接管重试，用例前提不成立"
        assert concurrent_peak == 1, f"拉取出现并发（峰值 {concurrent_peak}），等待者应串行接管"


class TestProbeThrottle:
    # _throttle_probe 是探针层真实限流器：同 host 强制最小间隔，不同 host 互不影响。

    def test_same_host_enforces_min_interval(self, _fast_probe_throttle: None) -> None:
        url = "https://cdn.example.com/live/stream.m3u8"
        start = time.monotonic()
        stream_select._throttle_probe(url)
        stream_select._throttle_probe(url)
        elapsed = time.monotonic() - start
        # 首次不等待，第二次须补足最小间隔（jitter 已置 0，故期望 ≈ 0.05s）
        assert elapsed >= 0.05, f"同 host 探针未节流：两次共耗时 {elapsed:.4f}s"

    def test_different_hosts_do_not_throttle_each_other(self, _fast_probe_throttle: None) -> None:
        start = time.monotonic()
        stream_select._throttle_probe("https://a.example.com/x.m3u8")
        stream_select._throttle_probe("https://b.example.com/y.m3u8")
        elapsed = time.monotonic() - start
        assert elapsed < 0.05, f"不同 host 不应互相节流：实测耗时 {elapsed:.4f}s"

    def test_empty_host_returns_immediately(self, _fast_probe_throttle: None) -> None:
        # 无效 URL 取不到 netloc：须直接返回，不得进入节流等待
        start = time.monotonic()
        stream_select._throttle_probe("not-a-url")
        stream_select._throttle_probe("not-a-url")
        elapsed = time.monotonic() - start
        assert elapsed < 0.05, f"空 host 不应节流：实测耗时 {elapsed:.4f}s"
