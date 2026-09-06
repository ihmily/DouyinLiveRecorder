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

    # 丢弃 query 可避免同一主播不同房间参数（分享/回放）被当不同 key 各拉一次风控凭据
    # 归一化键丢弃 query 与尾斜杠：同路径不同 query 的房间须共享一条缓存，避免重复拉风控凭据
    def test_strips_query_and_trailing_slash(self) -> None:
        # 丢弃 query 可避免同一主播不同房间参数（分享/回放）被当不同 key 各拉一次风控凭据
        # 归一化键丢弃 query 与尾斜杠：同路径不同 query 的房间须共享一条缓存，避免重复拉取风控凭据
        assert _make_key("https://live.example.com/path/?a=1&b=2", None) == "https://live.example.com/path|"

    # 代理地址须纳入键：同房间走代理 vs 直连拿到的是不同风控凭据，须分别缓存而非共享
    def test_includes_proxy_addr(self) -> None:
        proxy = "http://127.0.0.1:8080"
        assert _make_key("https://live.example.com/", proxy) == f"https://live.example.com|{proxy}"

    def test_proxy_and_direct_are_distinct(self) -> None:
        # 直连与代理网络路径不同，抖音按环境下发不同风控 cookie，混用会触发二次验证
        # 键级隔离，防止代理用户的 cookie 泄漏给直连用户（反之亦然）
        direct = _make_key("https://live.example.com/", None)
        proxied = _make_key("https://live.example.com/", "http://127.0.0.1:8080")
        assert direct != proxied


# 统一读取入口 fetch_cookies：首次拉取写入、命中复用、TTL 失效、失败/空值不缓存。
# 并发维度（同循环 reentrant、跨线程）是 singleflight 去重与跨循环交付的关键回归点。
class TestFetchCookies:
    # 统一读取入口。

    # 首次拉取即写入并返回；并通过断言 fetcher 透传参数，锁定与 ttwid/spider 调用方一致的调用约定
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
        # 默认超时 10s 透传给 async_req：网络拉取 cookie 的普遍超时预算，过短易误判风控、过长拖慢首帧
        assert kwargs["timeout"] == 10
        # 默认禁用 HTTP/2：旧版 curl_cffi 在部分平台对 HTTP/2 支持不稳，须与调用方约定保持一致
        assert kwargs["http2"] is False

    # 命中缓存后不应再次调用 fetcher（calls==1），守护 singleflight"只拉一次"核心不变量
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

        # int/float 不转 str 会拼出 'a=1 ' 等非法头，导致下游请求被拒

    # 非字符串 cookie 值须强制为 str：下游拼 Cookie 头要求 str，int/float 不得泄漏
    async def test_values_are_str_coerced(self) -> None:
        async def fake_fetcher(**kwargs: Any) -> dict[str, Any]:
            return {"a": 1, "b": 1.5}  # type: ignore[return-value]

        result = await fetch_cookies("https://live.example.com/", fetcher=fake_fetcher)
        assert result == {"a": "1", "b": "1.5"}

    # async_req(return_cookies=True) 另一成功形态 (其他数据, cookie_dict)：须正确解包出 cookie 字典
    async def test_tuple_result_compat(self) -> None:
        # async_req(return_cookies=True) 的另一种成功返回形态 (其他数据, cookie_dict)
        # 兼容旧版 async_req 的 (ok, cookie_dict) 双元素返回：须解包第二元素，回归早期结构
        async def fake_fetcher(**kwargs: Any) -> tuple[bool, dict[str, Any]]:
            return (True, {"k": "v"})

        result = await fetch_cookies("https://live.example.com/", fetcher=fake_fetcher)
        assert result == {"k": "v"}

    # ttl=0 即「每次都过期」：连续两次 fetch 各拉一次（calls==2），验证 TTL 真正生效
    # 而非被命中短路，防止默认 TTL 把临时失败也长期缓存
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

    # 代理与直连虽访问同房间，但键不同 → 各 fetch 一次（calls==[None, proxy]），
    # 验证代理地址正确透传 fetcher 且两类用户互不串用 cookie
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

    # fetcher 首调抛错须返回空字典且不固化缓存，下次访问重新拉取（calls==2），
    # 避免失败凭据被永久复用或把异常误判为「未直播」
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

    # 空字典视为「未拿到任何风控凭据」，与异常同等待遇：不缓存、下次重试（calls==2），
    # 而非把空结果当作有效命中导致后续一直拿到空 cookie
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

            # 须打在模块全局引用上：fetch_cookies 经 cc.async_req 调用，patch import 名无效

        # patch cc.async_req 而非 import 级名：fetch_cookies 通过模块全局引用 cc.async_req，必须打在模块属性上
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
        barrier = threading.Barrier(4)  # 4 个线程模拟 4 个 room 线程并发首帧；Barrier 同步起跑以放大竞态窗口
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

    # 任何未预热 key 的同步查询必须返回 None，且不得触发网络（与 fetch 路径解耦）
    def test_miss_returns_none(self) -> None:
        assert get_cached("https://live.example.com/") is None

    # 预热后同步查询直接返回已缓存 cookie，不触发任何网络（与 fetch 路径解耦）
    async def test_hit_returns_cookies(self) -> None:
        async def fake_fetcher(**kwargs: Any) -> dict[str, Any]:
            return {"ttwid": "abc"}

        await fetch_cookies("https://live.douyin.com/", fetcher=fake_fetcher)
        assert get_cached("https://live.douyin.com/") == {"ttwid": "abc"}

    # 手动把 expire_ts 回拨到 DEFAULT_TTL 之前：即便缓存字典里有条目，过期也必须判 miss，
    # 守护 TTL 失效语义（而非只检查「有没有条目」）
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
        # 缓存键含代理地址：直连查询代理写入的条目必须 miss，避免串用不同环境的 cookie
        assert get_cached("https://live.example.com/", proxy_addr="http://127.0.0.1:8080") is None


class TestGetCookieStr:
    # 拼接字符串便捷封装。

    # 多键值须按 'k=v' 用分号+空格拼接（标准 Cookie 头格式），供下游直接塞进请求头
    async def test_joins_entries(self) -> None:
        async def fake_fetcher(**kwargs: Any) -> dict[str, Any]:
            return {"a": "1", "b": "2"}

        result = await get_cookie_str("https://live.example.com/", fetcher=fake_fetcher)
        assert result == "a=1; b=2"

    # 无 cookie 时返回空字符串而非 '=' 之类畸形串，避免下游拼出无效 Cookie 头
    async def test_empty_when_no_cookies(self) -> None:
        async def fake_fetcher(**kwargs: Any) -> dict[str, Any]:
            return {}

        result = await get_cookie_str("https://live.example.com/", fetcher=fake_fetcher)
        assert result == ""


# 失效入口：按 key 精准失效单条，或按无参清空整份缓存。
# 守护"精准失效不误伤其它房间"与"无参清空"两条语义。
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

    # 失效 a 不影响 b：守护「精准失效不误伤」语义，避免一键清空式的退化
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

    # 失效从未拉取过的 key 必须安全无操作、不抛异常（轮询线程可能在写入前调用）
    async def test_missing_key_no_error(self) -> None:
        invalidate("https://never-fetched.example.com/")


# 整份缓存清空入口：清空后所有 key 均 miss，语义与 invalidate() 无参对齐。
# 常用于测试 fixture 复位，避免用例间缓存状态泄漏。
class TestClear:
    # clear 后进程级缓存字典清空且所有 key miss：常用 fixture 复位，防用例间状态泄漏
    async def test_clears_all_entries(self) -> None:
        async def fake_fetcher(**kwargs: Any) -> dict[str, Any]:
            return {"a": "1"}

        await fetch_cookies("https://a.example.com/", fetcher=fake_fetcher)
        await fetch_cookies("https://b.example.com/", fetcher=fake_fetcher)
        clear()
        assert cc._cookie_cache == {}
        assert get_cached("https://a.example.com/") is None
