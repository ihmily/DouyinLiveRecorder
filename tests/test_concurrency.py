# -*- encoding: utf-8 -*-
#
# 并发风控核心模式测试：验证线程锁、速率限制、凭证共享的正确性。
#
# 覆盖三个核心模式（与 src 的真实实现一一对应）：
# 1. 线程安全凭证管理  -> src/ttwid.py 的 get_ttwid()（跨线程 + 跨事件循环去重）
# 2. 速率限制          -> src/stream_select.py 的 _douyin_rate_limit()（最小间隔 + 串行化）
# 3. 凭证共享          -> src/cookie_cache.py 的 singleflight()（同 key 只拉一次、多模块复用）
#
# 口径：早期形态是「在测试里重写一份锁 / 限流器 / 凭证缓存，再断言这份
# 自实现」，把 src/ 的对应实现整个删掉仍然全绿（典型假绿）。现在三处用例一律**直接驱动真实入口**，
# 只允许打桩网络层与时间常量：
#   - test_lock_prevents_duplicate_fetch   驱动 src.ttwid.get_ttwid（桩 _fetch_ttwid）
#   - TestRateLimit                        驱动 src.stream_select._douyin_rate_limit
#                                          （桩 stream_select 命名空间里的 time + main 的两个常量）
#   - test_shared_credential_single_source 驱动 src.cookie_cache.singleflight（真去重实现）
# 判据仍是「删掉生产实现就会失败」：去掉 with main.douyin_rate_lock / 去掉 singleflight 的
# 二次检查，本文件的相应用例会红（见各条注释里的失效推演）。
#
# 与 tests/test_concurrency_rate_limit.py 的分工：那个文件锁「ttwid owner 失败不惊群」
# 与「探针节流」；本文件锁「抖音请求限流的串行化与最小间隔」与「跨循环凭据去重」，不重复。
import asyncio
import threading
import time
import types
from typing import Any

import pytest

import main  # noqa: F401  先完整初始化 main，打破 stream_select<->main 的循环导入
import src.cookie_cache as cookie_cache
import src.stream_select as stream_select
import src.ttwid as ttwid_module

_plain_lock_type = type(threading.Lock())
_rlock_type = type(threading.RLock())


@pytest.fixture()
def _isolated_ttwid(monkeypatch: pytest.MonkeyPatch) -> None:
    # 清空 ttwid 进程级缓存，并屏蔽 config.ini 的预置值：开发者本地填过 ttwid 时
    # get_ttwid 会短路走配置分支，本用例要驱动的是「自动拉取 + 去重」那条路。
    monkeypatch.setattr(ttwid_module, "_cached_ttwid", "")
    monkeypatch.setattr(ttwid_module, "_read_config_ttwid", lambda: "")


class _FakeClock:
    # 假时钟：sleep 不真睡，只把时钟往前拨——这正是「按差值补足间隔」的可观测效果。
    # gate 让「拨钟 + 记录」原子化，使并发用例仍能读出真实的串行化结果。
    def __init__(self) -> None:
        self.now = 1_000.0
        self.sleeps: list[float] = []
        self.gate = threading.Lock()

    def time(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        with self.gate:
            self.now += seconds
            self.sleeps.append(seconds)


@pytest.fixture()
def _fake_douyin_clock(monkeypatch: pytest.MonkeyPatch) -> _FakeClock:
    # 只桩「时间常量」：用一只假时钟驱动真实限流逻辑，用例耗时保持毫秒级。
    # 写法的坑（AGENTS.md「测试编写强制约定」）：绝不允许
    # monkeypatch.setattr(stream_select.time, "sleep", ...)——stream_select.time 是 stdlib
    # time 模块本体，改它波及全进程（loguru enqueue 线程、harness 守护线程），
    # 且被 tests/test_test_hygiene.py 的 R1 直接判红。必须浅拷贝成替身后替换模块全局引用。
    fake = _FakeClock()
    shim = types.SimpleNamespace(**vars(time))
    shim.time = fake.time
    shim.sleep = fake.sleep
    monkeypatch.setattr(stream_select, "time", shim)
    # 生产默认最小间隔 3s；用例把它压到 0.5s 让断言仍是有意义的量（不是「恰好等于 0」）。
    monkeypatch.setattr(main, "douyin_min_interval", 0.5, raising=False)
    monkeypatch.setattr(main, "douyin_last_request_time", 0.0, raising=False)
    return fake


class TestThreadSafeCredential:
    # 线程安全的凭证管理：真实入口 src/ttwid.get_ttwid()

    def test_lock_prevents_duplicate_fetch(self, monkeypatch: pytest.MonkeyPatch, _isolated_ttwid: None) -> None:
        # 10 个「房间线程」（各自 asyncio.run，复刻本项目的并发模型）并发取 ttwid，
        # 真实拉取只允许发生一次；把 src/cookie_cache/singleflight 的去重删掉即回归为多次拉取。
        fetch_calls = 0
        call_guard = threading.Lock()

        async def fake_fetch(proxy_addr: Any = None) -> str:
            nonlocal fetch_calls
            with call_guard:
                fetch_calls += 1
            await asyncio.sleep(0.05)  # 拉长在途窗口，让「无去重」必然被并发命中
            return "ttwid=from-network"

        monkeypatch.setattr(ttwid_module, "_fetch_ttwid", fake_fetch)

        results: list[str] = []
        errors: list[BaseException] = []
        collect = threading.Lock()

        def worker() -> None:
            try:
                value = asyncio.run(ttwid_module.get_ttwid())
            except BaseException as e:  # 线程内断言会丢失，统一收集后在主线程判定
                with collect:
                    errors.append(e)
                return
            with collect:
                results.append(value)

        threads = [threading.Thread(target=worker) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=20)
        # join(timeout=20) **返回**不等于线程已退出——去重链挂死时 join 超时静默返回，
        # 本用例只能靠「结果条数」间接兜住；逐线程断言 is_alive 为 False 才钉住「10 线程全部跑完」。
        for t in threads:
            assert not t.is_alive(), "join 超时后线程仍存活：跨线程去重链挂死，不得判绿"

        assert not errors, f"并发取凭据抛出异常: {errors}"
        assert len(results) == 10, "有线程没拿到结果：去重等待者被饿死或超时"
        assert results == ["ttwid=from-network"] * 10, f"各线程拿到不同凭据: {set(results)}"
        assert fetch_calls == 1, f"凭据被重复拉取 {fetch_calls} 次（期望 1）：跨线程去重失效"

        # 二次调用必须命中缓存（「多模块复用同一份缓存」的另一半：room.py / spider.py 后续轮次）
        assert asyncio.run(ttwid_module.get_ttwid()) == "ttwid=from-network"
        assert fetch_calls == 1, "缓存命中却再次拉取：TTL/全局缓存判定被改坏"

    def test_production_locks_are_threading_primitives(self) -> None:
        # 跨事件循环去重的锁必须是 threading 原语，**不得**是模块级 asyncio.Lock 单例
        # （AGENTS.md「锁的强制约定」：模块级 asyncio.Lock 会惰性绑定首个 await 它的循环，
        #  第二个房间线程的新循环里 await 即抛 "bound to a different event loop"）。
        # 本条取代旧版的「拿一个本地新建锁断言它有 acquire/release」——那与生产代码无关。
        assert not isinstance(ttwid_module._ttwid_lock, asyncio.Lock), "ttwid 去重锁退化成 asyncio.Lock 单例"
        assert isinstance(
            ttwid_module._ttwid_lock, _rlock_type
        ), "ttwid 锁跨 await 持有，必须是 RLock（普通 Lock 下同线程重入即自旋死锁）"
        assert not isinstance(stream_select._probe_throttle_lock, asyncio.Lock)
        assert isinstance(stream_select._probe_throttle_lock, _plain_lock_type), "探针节流锁必须是跨线程原语"
        assert isinstance(main.douyin_rate_lock, _plain_lock_type), "抖音限流锁必须是跨线程原语"


class TestRateLimit:
    # 速率限制：真实入口 src/stream_select._douyin_rate_limit()

    def test_rate_limit_enforces_min_interval(self, _fake_douyin_clock: _FakeClock) -> None:
        # 三次连续调用：每次都必须把「上一次请求时刻」推进到当前时刻，
        # 且相邻两次的间隔 >= 最小间隔。把 `if elapsed < min_interval: sleep(...)` 删掉
        # 或把 douyin_last_request_time 的推进删掉，本条立刻红（间隔变 0 / 不推进）。
        stamps: list[float] = []
        for _ in range(3):
            stream_select._douyin_rate_limit()
            stamps.append(float(main.douyin_last_request_time))

        assert len(stamps) == 3
        assert stamps == sorted(stamps), f"请求时刻倒退: {stamps}"
        for prev, nxt in zip(stamps, stamps[1:]):
            assert nxt - prev >= main.douyin_min_interval, f"两次抖音请求间隔 {nxt - prev} < {main.douyin_min_interval}"
        assert _fake_douyin_clock.sleeps, "限流器一次都没 sleep：等于没限速"
        assert all(seconds > 0 for seconds in _fake_douyin_clock.sleeps), _fake_douyin_clock.sleeps

    def test_rate_limit_serializes_concurrent_calls(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # 5 个房间线程**同时**进入限流器（Barrier 保证真并发，否则线程启动开销就把它们自然错开，
        # 「没有锁」与「有锁」的观测结果相同）。真实 douyin_rate_lock 让「读间隔 → 补睡 → 记时刻」
        # 成为临界区：相邻请求必然相差至少一个最小间隔。刻意用**真实时钟**：假时钟的 sleep 自带
        # 互斥，会把无锁形态也「救」成串行；代价是每条用例真等 ~0.05s×N。
        monkeypatch.setattr(main, "douyin_min_interval", 0.05, raising=False)
        monkeypatch.setattr(main, "douyin_last_request_time", time.time(), raising=False)

        stamps: list[float] = []
        stamp_guard = threading.Lock()
        barrier = threading.Barrier(5)

        def worker() -> None:
            barrier.wait(timeout=20)
            stream_select._douyin_rate_limit()
            with stamp_guard:
                stamps.append(float(main.douyin_last_request_time))

        threads = [threading.Thread(target=worker) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=20)
        # join 超时返回时线程可能还卡在 douyin_rate_lock 里，`len(stamps) == 5` 只是间接
        # 证据；逐线程断言已退出才挡住「死锁但判绿」。
        for t in threads:
            assert not t.is_alive(), "join 超时后线程仍存活：限流临界区死锁，不得判绿"

        assert len(stamps) == 5, f"有线程未走完限流临界区: {stamps}"
        ordered = sorted(stamps)
        gaps = [b - a for a, b in zip(ordered, ordered[1:])]
        assert all(gap >= main.douyin_min_interval * 0.9 for gap in gaps), (
            f"并发调用未被串行化（相邻请求间隔 {[round(g, 4) for g in gaps]} < {main.douyin_min_interval}）："
            "限流的 with main.douyin_rate_lock 被移除或改名"
        )


class TestCredentialSharing:
    # 凭证共享：真实入口 src/cookie_cache.singleflight()（room.py / spider.py / ttwid.py 共用）

    def test_shared_credential_single_source(self) -> None:
        # 多个模块（这里用 5 个「房间线程 + 各自事件循环」代表）并发取同一 key 的凭据：
        # 真实现只执行一次 factory，其余等待者经跨循环交付复用同一结果。
        # 把 singleflight 的「同 key 在途即挂等待者」分支删掉 → 每个调用方各自拉取，本条红。
        key = "unit_test_shared_credential"
        cookie_cache.invalidate_generic(key)
        factory_calls = 0
        call_guard = threading.Lock()

        async def factory() -> dict[str, str]:
            nonlocal factory_calls
            with call_guard:
                factory_calls += 1
            await asyncio.sleep(0.05)
            return {"did": "abc", "didv": "def"}

        values: list[Any] = []
        value_guard = threading.Lock()

        def consumer() -> None:
            async def runner() -> Any:
                return await cookie_cache.singleflight(key=key, factory=factory, timeout=5)

            value = asyncio.run(runner())
            with value_guard:
                values.append(value)

        threads = [threading.Thread(target=consumer) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=20)
        # singleflight 的跨循环交付若挂住，等待者线程永不退出，而 join(timeout=20) 只是
        # 超时返回、不报错——逐线程断言已退出，否则「死锁」会以「值不齐」的间接形态出现。
        for t in threads:
            assert not t.is_alive(), "join 超时后线程仍存活：singleflight 临界区死锁，不得判绿"

        assert len(values) == 5, f"有消费者没拿到凭据: {values}"
        assert all(v == {"did": "abc", "didv": "def"} for v in values), f"各模块拿到的凭据不一致: {values}"
        assert factory_calls == 1, f"统一缓存被绕过：factory 执行了 {factory_calls} 次"

        # 复用同一份缓存的第二个消费者：不得再触发拉取（这就是「多模块复用」的语义）
        async def second_consumer() -> Any:
            return await cookie_cache.singleflight(key=key, factory=factory, timeout=5)

        assert asyncio.run(second_consumer()) == {"did": "abc", "didv": "def"}
        assert factory_calls == 1, "TTL 内二次调用仍重新拉取：共享缓存没有生效"
        cookie_cache.invalidate_generic(key)

    def test_ttwid_module_pattern(self) -> None:
        # 验证实际 ttwid.py 模块的缓存模式
        from src.ttwid import _cached_ttwid, _ttwid_lock

        # 锁为 threading.RLock：跨线程去重的同时允许同线程重入，
        # 避免锁跨越 await 时同事件循环并发协程自旋死锁
        assert isinstance(_cached_ttwid, str)
        assert isinstance(_ttwid_lock, _rlock_type)
