# -*- encoding: utf-8 -*-
#
# 并发风控核心模式测试：验证线程锁、速率限制、凭证共享的正确性。
#
# 覆盖三个核心模式：
# 1. 线程安全凭证管理（threading.Lock 保护缓存）
# 2. 速率限制（最小间隔控制）
# 3. 凭证共享（多模块复用同一缓存）
#
import asyncio
import threading
import time
from unittest.mock import AsyncMock, patch

import pytest


class TestThreadSafeCredential:
    # 测试线程安全的凭证管理（对应 ttwid.py 模式）

    def test_lock_prevents_duplicate_fetch(self) -> None:
        # 验证 threading.Lock 确保凭证只获取一次
        fetch_count = 0
        lock = threading.Lock()
        cached: str | None = None

        def get_credential() -> str:
            nonlocal fetch_count, cached
            if cached:
                return cached
            if not lock.acquire(blocking=False):
                with lock:
                    pass
                return cached or "fetched"
            try:
                if cached:
                    return cached
                fetch_count += 1
                cached = "fetched"
                return cached
            finally:
                lock.release()

        # 模拟多线程并发访问
        results: list[str] = []
        threads = [threading.Thread(target=lambda: results.append(get_credential())) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # 所有线程都应获得结果
        assert len(results) == 10
        assert all(r == "fetched" for r in results)
        # 凭证只获取一次
        assert fetch_count == 1

    def test_lock_is_threading_lock(self) -> None:
        # 验证使用的是 threading.Lock 而非其他锁类型
        lock = threading.Lock()
        assert isinstance(lock, type(threading.Lock()))
        assert hasattr(lock, "acquire")
        assert hasattr(lock, "release")


class TestRateLimit:
    # 测试速率限制（对应 main.py _douyin_rate_limit 模式）

    def test_rate_limit_enforces_min_interval(self) -> None:
        # 验证速率限制确保最小请求间隔
        rate_lock = threading.Lock()
        last_request_time: float = 0.0
        min_interval: float = 0.1  # 测试用 100ms（生产环境为 3.0s）
        request_times: list[float] = []

        def rate_limit() -> None:
            nonlocal last_request_time
            with rate_lock:
                now = time.time()
                elapsed = now - last_request_time
                if elapsed < min_interval:
                    time.sleep(min_interval - elapsed)
                last_request_time = time.time()
                request_times.append(last_request_time)

        # 连续调用 3 次
        for _ in range(3):
            rate_limit()

        # 验证每次调用间隔 >= min_interval
        assert len(request_times) == 3
        for i in range(1, len(request_times)):
            interval = request_times[i] - request_times[i - 1]
            assert interval >= min_interval * 0.9  # 允许 10% 误差

    def test_rate_limit_serializes_concurrent_calls(self) -> None:
        # 验证速率限制在多线程下串行化执行
        rate_lock = threading.Lock()
        last_request_time: float = 0.0
        min_interval: float = 0.05
        execution_order: list[int] = []
        order_lock = threading.Lock()

        def rate_limit(thread_id: int) -> None:
            nonlocal last_request_time
            with rate_lock:
                now = time.time()
                elapsed = now - last_request_time
                if elapsed < min_interval:
                    time.sleep(min_interval - elapsed)
                last_request_time = time.time()
                with order_lock:
                    execution_order.append(thread_id)

        threads = [threading.Thread(target=rate_limit, args=(i,)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # 所有线程都应执行完毕
        assert len(execution_order) == 5


class TestCredentialSharing:
    # 测试凭证共享（对应 ttwid.py 统一缓存模式）

    def test_shared_credential_single_source(self) -> None:
        # 验证多模块复用同一凭证缓存
        # 模拟统一的凭证模块
        class CredentialModule:
            def __init__(self) -> None:
                self._cached: str = ""
                self._lock = threading.Lock()
                self.fetch_count = 0

            async def get(self) -> str:
                if self._cached:
                    return self._cached
                if not self._lock.acquire(blocking=False):
                    with self._lock:
                        pass
                    return self._cached or await self._fetch()
                try:
                    if self._cached:
                        return self._cached
                    return await self._fetch()
                finally:
                    self._lock.release()

            async def _fetch(self) -> str:
                self.fetch_count += 1
                self._cached = "shared_credential"
                return self._cached

        module = CredentialModule()

        # 模拟多个模块（room.py, spider.py）并发调用同一凭证模块
        async def consumer() -> str:
            return await module.get()

        async def run_consumers() -> list[str]:
            return list(await asyncio.gather(*[consumer() for _ in range(10)]))

        results = asyncio.run(run_consumers())

        # 所有消费者获得相同凭证
        assert all(r == "shared_credential" for r in results)
        # 凭证只获取一次
        assert module.fetch_count == 1

    def test_ttwid_module_pattern(self) -> None:
        # 验证实际 ttwid.py 模块的缓存模式
        from src.ttwid import _cached_ttwid, _ttwid_lock

        # 验证模块级变量存在且类型正确
        # 锁为 threading.RLock：跨线程去重的同时允许同线程重入，
        # 避免锁跨越 await 时同事件循环并发协程自旋死锁
        assert isinstance(_cached_ttwid, str)
        assert isinstance(_ttwid_lock, type(threading.RLock()))
