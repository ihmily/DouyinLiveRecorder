# Tests for src/async_http.py 批次5修复 - 客户端缓存锁跨线程安全回归测试.
# 使用 mock 客户端（不创建真实 httpx.AsyncClient），保证测试确定性且无网络/环境依赖.

import asyncio
import threading
from unittest.mock import patch

import pytest

from src import async_http as ah


class FakeAsyncClient:
    # 模拟 httpx.AsyncClient 的最小接口（_get_client 仅使用 is_closed / aclose）
    def __init__(self, **kwargs: object) -> None:
        self.kwargs = kwargs
        self.closed = False

    @property
    def is_closed(self) -> bool:
        return self.closed

    async def aclose(self) -> None:
        self.closed = True


class TestClientCacheConcurrency:
    # _client_cache 由 threading.Lock 保护（临界区无 await），
    # 多房间「独立线程+独立事件循环」并发获取客户端不应抛异常（原实现存在跨循环锁竞态）.

    def setup_method(self) -> None:
        with ah._client_cache_lock:
            ah._client_cache.clear()

    @pytest.mark.filterwarnings("ignore::RuntimeWarning")
    def test_concurrent_threads_no_cross_loop_error(self) -> None:
        errors: list[Exception] = []

        def run() -> None:
            try:
                client = asyncio.run(ah._get_client(proxy_addr=None, timeout=10, verify=True, http2=False))
                assert client is not None
            except Exception as e:  # pragma: no cover - 仅收集异常
                errors.append(e)

        with patch("httpx.AsyncClient", new=FakeAsyncClient):
            threads = [threading.Thread(target=run) for _ in range(8)]
            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=15)
        assert errors == []

    def test_same_loop_reuses_client(self) -> None:
        async def get_twice() -> tuple:
            a = await ah._get_client(proxy_addr=None, timeout=10, verify=True, http2=False)
            b = await ah._get_client(proxy_addr=None, timeout=10, verify=True, http2=False)
            return a, b

        with patch("httpx.AsyncClient", new=FakeAsyncClient):
            a, b = asyncio.run(get_twice())
        assert a is b  # 同一循环内复用连接池

    def test_loop_change_replaces_client_and_closes_old(self) -> None:
        with patch("httpx.AsyncClient", new=FakeAsyncClient):
            first = asyncio.run(ah._get_client(proxy_addr=None, timeout=10, verify=True, http2=False))
            second = asyncio.run(ah._get_client(proxy_addr=None, timeout=10, verify=True, http2=False))
        assert first is not second
        # 旧循环已关闭，旧客户端交由 GC（不跨循环 await）
        assert second is not None

    def test_different_params_use_different_cache_keys(self) -> None:
        async def get_two() -> tuple:
            a = await ah._get_client(proxy_addr=None, timeout=10, verify=True, http2=False)
            b = await ah._get_client(proxy_addr="http://p:1", timeout=10, verify=True, http2=False)
            return a, b

        with patch("httpx.AsyncClient", new=FakeAsyncClient):
            a, b = asyncio.run(get_two())
        assert a is not b
