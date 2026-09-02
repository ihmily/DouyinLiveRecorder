# Tests for src/cookie_cache.py - 统一 cookie 缓存模块的单元测试。
# 覆盖：key 归一化、命中/未命中、TTL 失效、失败不缓存、跨线程并发去重、
#       字符串拼接、失效/清空，以及与调用方（ttwid/spider）约定一致的 fetcher 透传。

import asyncio
import threading
import time
from collections.abc import Iterator
from typing import Any

import pytest

import src.cookie_cache as cc
from src.cookie_cache import (
    DEFAULT_TTL,
    _make_key,
    clear,
    fetch_cookies,
    get_cached,
    get_cookie_str,
    invalidate,
)


@pytest.fixture(autouse=True)
def _clean_cache() -> Iterator[None]:
    # 每个测试前后清空进程级缓存，避免用例间相互污染。
    clear()
    yield
    clear()


class TestMakeKey:
    # 缓存键的归一化规则。

    def test_strips_query_and_trailing_slash(self) -> None:
        assert _make_key("https://live.example.com/path/?a=1&b=2", None) == "https://live.example.com/path|"

    def test_includes_proxy_addr(self) -> None:
        proxy = "http://127.0.0.1:8080"
        assert _make_key("https://live.example.com/", proxy) == f"https://live.example.com|{proxy}"

    def test_proxy_and_direct_are_distinct(self) -> None:
        direct = _make_key("https://live.example.com/", None)
        proxied = _make_key("https://live.example.com/", "http://127.0.0.1:8080")
        assert direct != proxied


class TestFetchCookies:
    # 统一读取入口。

    async def test_first_fetch_caches_and_returns(self) -> None:
        calls: list[dict[str, Any]] = []

        async def fake_fetcher(**kwargs: Any) -> dict[str, Any]:
            calls.append(kwargs)
            return {"ttwid": "abc", "passport": "yes"}

        result = await fetch_cookies("https://live.example.com/", fetcher=fake_fetcher)
        assert result == {"ttwid": "abc", "passport": "yes"}
        assert len(calls) == 1
        # 透传约定参数（与 ttwid/spider 的调用方式一致）
        kwargs = calls[0]
        assert kwargs["url"] == "https://live.example.com/"
        assert kwargs["return_cookies"] is True
        assert kwargs["timeout"] == 10
        assert kwargs["http2"] is False

    async def test_cache_hit_does_not_refetch(self) -> None:
        calls = 0

        async def fake_fetcher(**kwargs: Any) -> dict[str, Any]:
            nonlocal calls
            calls += 1
            return {"did": "d1", "didv": "d2"}

        first = await fetch_cookies("https://live.kuaishou.com/", fetcher=fake_fetcher)
        second = await fetch_cookies("https://live.kuaishou.com/", fetcher=fake_fetcher)
        assert first == second == {"did": "d1", "didv": "d2"}
        assert calls == 1

    async def test_values_are_str_coerced(self) -> None:
        async def fake_fetcher(**kwargs: Any) -> dict[str, Any]:
            return {"a": 1, "b": 1.5}  # type: ignore[return-value]

        result = await fetch_cookies("https://live.example.com/", fetcher=fake_fetcher)
        assert result == {"a": "1", "b": "1.5"}

    async def test_tuple_result_compat(self) -> None:
        # async_req(return_cookies=True) 的另一种成功返回形态 (其他数据, cookie_dict)
        async def fake_fetcher(**kwargs: Any) -> tuple[bool, dict[str, Any]]:
            return (True, {"k": "v"})

        result = await fetch_cookies("https://live.example.com/", fetcher=fake_fetcher)
        assert result == {"k": "v"}

    async def test_ttl_zero_refetches_every_time(self) -> None:
        calls = 0

        async def fake_fetcher(**kwargs: Any) -> dict[str, Any]:
            nonlocal calls
            calls += 1
            return {"a": "1"}

        await fetch_cookies("https://live.example.com/", ttl=0, fetcher=fake_fetcher)
        await fetch_cookies("https://live.example.com/", ttl=0, fetcher=fake_fetcher)
        assert calls == 2

    async def test_ttl_param_overrides_default_lifetime(self) -> None:
        # 缓存条目的 expire_ts 早于 DEFAULT_TTL，但晚于本次传入的 ttl=3600，
        # 此时 fetch_cookies 仍应命中（get_cached 用 DEFAULT_TTL 则判为过期）。
        async def fake_fetcher(**kwargs: Any) -> dict[str, Any]:
            return {"a": "1"}

        await fetch_cookies("https://live.example.com/", fetcher=fake_fetcher)
        with cc._cache_lock:
            _, _expire = cc._cookie_cache[_make_key("https://live.example.com/", None)]
            cc._cookie_cache[_make_key("https://live.example.com/", None)] = (
                {"a": "1"},
                _expire - (DEFAULT_TTL + 100),
            )
        stale = get_cached("https://live.example.com/")
        assert stale is None
        hit = await fetch_cookies("https://live.example.com/", ttl=DEFAULT_TTL + 1000, fetcher=fake_fetcher)
        assert hit == {"a": "1"}

    async def test_different_proxy_is_separate_entry(self) -> None:
        calls: list[Any] = []
        proxy = "http://127.0.0.1:8080"

        async def fake_fetcher(**kwargs: Any) -> dict[str, Any]:
            calls.append(kwargs.get("proxy_addr"))
            return {"did": "value"}

        direct = await fetch_cookies("https://live.kuaishou.com/", fetcher=fake_fetcher)
        proxied = await fetch_cookies("https://live.kuaishou.com/", proxy_addr=proxy, fetcher=fake_fetcher)
        assert direct == proxied == {"did": "value"}
        assert calls == [None, proxy]

    async def test_exception_returns_empty_and_not_cached(self) -> None:
        calls = 0

        async def fake_fetcher(**kwargs: Any) -> dict[str, Any]:
            nonlocal calls
            calls += 1
            if calls == 1:
                raise ConnectionError("boom")
            return {"ok": "1"}

        first = await fetch_cookies("https://live.example.com/", fetcher=fake_fetcher)
        assert first == {}
        # 失败未固化为缓存：下一次访问会重新拉取
        second = await fetch_cookies("https://live.example.com/", fetcher=fake_fetcher)
        assert second == {"ok": "1"}
        assert calls == 2

    async def test_empty_dict_not_cached(self) -> None:
        calls = 0

        async def fake_fetcher(**kwargs: Any) -> dict[str, Any]:
            nonlocal calls
            calls += 1
            return {} if calls == 1 else {"a": "1"}

        first = await fetch_cookies("https://live.example.com/", fetcher=fake_fetcher)
        assert first == {}
        second = await fetch_cookies("https://live.example.com/", fetcher=fake_fetcher)
        assert second == {"a": "1"}
        assert calls == 2

    async def test_default_fetcher_is_async_req(self, monkeypatch: pytest.MonkeyPatch) -> None:
        seen: dict[str, Any] = {}

        async def fake_async_req(
            url: str, *, proxy_addr: str | None = None, headers: Any = None, **kwargs: Any
        ) -> dict[str, Any]:
            seen["url"] = url
            return {"ttwid": "from_async_req"}

        monkeypatch.setattr(cc, "async_req", fake_async_req)
        result = await fetch_cookies("https://live.example.com/")
        assert result == {"ttwid": "from_async_req"}
        assert seen["url"] == "https://live.example.com/"

    async def test_same_loop_reentrant_no_deadlock(self) -> None:
        # 同事件循环内并发 gather：既不死锁、结果一致，也应只拉取一次（singleflight）。
        # 旧实现的 RLock 跨 await 持有时同循环协程全部可重入、互斥失效，会并发拉取
        # 同一网址——正是本模块要消除的风控触发源。
        calls = 0

        async def fake_fetcher(**kwargs: Any) -> dict[str, Any]:
            nonlocal calls
            calls += 1
            await asyncio.sleep(0.01)
            return {"a": "1"}

        results = await asyncio.gather(
            *(fetch_cookies("https://live.example.com/", fetcher=fake_fetcher) for _ in range(5))
        )
        assert all(r == {"a": "1"} for r in results)
        assert calls == 1

    def test_cross_thread_concurrent_fetch_once(self) -> None:
        # 真实并发模型：多个 room 线程各自独立 asyncio.run 循环，经在途登记表 +
        # call_soon_threadsafe 跨循环交付，同一网址只应被拉取一次，其余线程复用结果。
        call_count = 0
        call_lock = threading.Lock()
        barrier = threading.Barrier(4)
        results: list[dict[str, Any]] = []

        async def fake_fetcher(**kwargs: Any) -> dict[str, Any]:
            nonlocal call_count
            with call_lock:
                call_count += 1
            await asyncio.sleep(0.01)
            return {"did": "shared"}

        def worker() -> None:
            barrier.wait()

            async def _run() -> dict[str, Any]:
                return await fetch_cookies("https://live.kuaishou.com/", fetcher=fake_fetcher)

            results.append(asyncio.run(_run()))

        threads = [threading.Thread(target=worker) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert call_count == 1
        assert all(r == {"did": "shared"} for r in results)


class TestGetCached:
    # 同步只读查询（不触发网络请求）。

    def test_miss_returns_none(self) -> None:
        assert get_cached("https://live.example.com/") is None

    async def test_hit_returns_cookies(self) -> None:
        async def fake_fetcher(**kwargs: Any) -> dict[str, Any]:
            return {"ttwid": "abc"}

        await fetch_cookies("https://live.douyin.com/", fetcher=fake_fetcher)
        assert get_cached("https://live.douyin.com/") == {"ttwid": "abc"}

    async def test_expired_returns_none(self) -> None:
        async def fake_fetcher(**kwargs: Any) -> dict[str, Any]:
            return {"a": "1"}

        await fetch_cookies("https://live.example.com/", fetcher=fake_fetcher)
        key = _make_key("https://live.example.com/", None)
        with cc._cache_lock:
            cc._cookie_cache[key] = ({"a": "1"}, time.monotonic() - DEFAULT_TTL - 1)
        assert get_cached("https://live.example.com/") is None

    async def test_proxy_mismatch_is_miss(self) -> None:
        async def fake_fetcher(**kwargs: Any) -> dict[str, Any]:
            return {"a": "1"}

        await fetch_cookies("https://live.example.com/", fetcher=fake_fetcher)
        assert get_cached("https://live.example.com/", proxy_addr="http://127.0.0.1:8080") is None


class TestGetCookieStr:
    # 拼接字符串便捷封装。

    async def test_joins_entries(self) -> None:
        async def fake_fetcher(**kwargs: Any) -> dict[str, Any]:
            return {"a": "1", "b": "2"}

        result = await get_cookie_str("https://live.example.com/", fetcher=fake_fetcher)
        assert result == "a=1; b=2"

    async def test_empty_when_no_cookies(self) -> None:
        async def fake_fetcher(**kwargs: Any) -> dict[str, Any]:
            return {}

        result = await get_cookie_str("https://live.example.com/", fetcher=fake_fetcher)
        assert result == ""


class TestInvalidate:
    # 失效指定条目或整份缓存。

    async def test_removes_single_entry(self) -> None:
        calls = 0

        async def fake_fetcher(**kwargs: Any) -> dict[str, Any]:
            nonlocal calls
            calls += 1
            return {"a": "1"}

        await fetch_cookies("https://live.example.com/", fetcher=fake_fetcher)
        invalidate("https://live.example.com/")
        assert get_cached("https://live.example.com/") is None
        await fetch_cookies("https://live.example.com/", fetcher=fake_fetcher)
        assert calls == 2

    async def test_other_entries_kept(self) -> None:
        async def fake_fetcher(**kwargs: Any) -> dict[str, Any]:
            return {"a": "1"}

        await fetch_cookies("https://a.example.com/", fetcher=fake_fetcher)
        await fetch_cookies("https://b.example.com/", fetcher=fake_fetcher)
        invalidate("https://a.example.com/")
        assert get_cached("https://a.example.com/") is None
        assert get_cached("https://b.example.com/") == {"a": "1"}

    async def test_none_clears_all(self) -> None:
        async def fake_fetcher(**kwargs: Any) -> dict[str, Any]:
            return {"a": "1"}

        await fetch_cookies("https://a.example.com/", fetcher=fake_fetcher)
        await fetch_cookies("https://b.example.com/", fetcher=fake_fetcher)
        invalidate()
        assert get_cached("https://a.example.com/") is None
        assert get_cached("https://b.example.com/") is None

    async def test_missing_key_no_error(self) -> None:
        invalidate("https://never-fetched.example.com/")


class TestClear:
    async def test_clears_all_entries(self) -> None:
        async def fake_fetcher(**kwargs: Any) -> dict[str, Any]:
            return {"a": "1"}

        await fetch_cookies("https://a.example.com/", fetcher=fake_fetcher)
        await fetch_cookies("https://b.example.com/", fetcher=fake_fetcher)
        clear()
        assert cc._cookie_cache == {}
        assert get_cached("https://a.example.com/") is None
