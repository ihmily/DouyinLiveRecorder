# src/cookie_cache.py 单元测试：key 归一化、命中/未命中、TTL 失效、失败不缓存、跨线程并发
# 去重、字符串拼接、失效/清空，以及与 ttwid/spider 约定一致的 fetcher 透传。
#
# 另覆盖三组不变量（改回旧形态即应转红）：
#   失败日志的异常文本必须过 mask_credentials（凭据不随轮转日志长期落盘）；
#   在途登记表只回收「拉取者所在循环已关闭」的孤儿登记，且须唤醒其等待者、不得摘掉
#         仍活着的登记、不得让迟到的拉取者抢走接管者的登记位；
#   条目寿命由写入方按自己的 ttl 折成失效时刻，两个读取方（get_cached / fetch_cookies
#         与 singleflight）一律按记录的失效时刻判定。
#
# 另有两组 src/room.py 的同族不变量（同样改回旧形态即应转红）：
#   sec_user_id → 抖音号缓存：过期条目必须**见到即删**且有容量上限（key 外部可控且通常
#          只出现一次，只「不返回」不删除就是无界增长）；
#   默认头按**键**合并（UA/Cookie 任一存在不再让另一项也不补），自动取到的 ttwid 只替换
#          Cookie 串里的同名键、不得整串覆盖登录态；配套的**接线点**锁见文末该段。

import ast
import asyncio
import io
import threading
import time
import types
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from loguru import logger

import src.cookie_cache as cc
import src.room as room_module
from src.cookie_cache import DEFAULT_TTL, _make_key, clear, fetch_cookies, get_cached, get_cookie_str, invalidate
from src.room import HEADERS, _get_cached_unique_id, _merge_cookie_pair, _merge_default_headers, _set_cached_unique_id

# 真实形态的失败异常文本：查询串挂 token、代理地址挂 user:pass，两类都在 utils.mask_credentials 覆盖内（写用例前逐条实测）。
# 断言口径是「密钥字符串确实从日志里消失」而非「调用过 mask_credentials」——后者在删掉生产那次调用后照样全绿（AGENTS 关键约定 #11）。
_SECRET_TOKEN = "AbcDef0123456789TOKENVALUE"
_SECRET_PROXY_PASS = "Sup3rPr0xyPassw0rd"
_SECRET_URL = f"https://push.example.com/api?token={_SECRET_TOKEN} via pusher:{_SECRET_PROXY_PASS}@proxy.internal:8080"


@pytest.fixture(autouse=True)
def _clean_cache() -> Iterator[None]:
    # 每个测试前后清空进程级缓存，避免用例间相互污染。
    clear()
    yield
    clear()


@pytest.fixture
def log_capture() -> Iterator[io.StringIO]:
    # 内存 sink 直接接管 loguru：本仓不把 loguru 桥接到 stdlib logging，caplog 抓不到。
    buf = io.StringIO()
    sink_id = logger.add(buf, format="{level} {message}", level="DEBUG")
    try:
        yield buf
    finally:
        try:
            logger.remove(sink_id)
        except ValueError:
            pass


@pytest.fixture
def fake_clock(monkeypatch: pytest.MonkeyPatch) -> Iterator[list[float]]:
    # TTL 用例需把时钟推过条目寿命，但绝不允许真 sleep（整包跑既慢又不稳）。按 AGENTS「进程级 stdlib
    # 替身走被测模块命名空间 shim」：真 time 模块本体一字节不动，同会话其它用例与 loguru 的取时不受牵连。
    holder = [1000.0]
    shim = types.SimpleNamespace(**vars(time))
    shim.monotonic = lambda: holder[0]
    monkeypatch.setattr(cc, "time", shim)
    yield holder


def _dead_loop() -> asyncio.AbstractEventLoop:
    # 造一个「拉取者所在线程已被硬杀」的循环对象：is_closed() 为真，
    # 这是该里孤儿登记唯一的可证明判据。
    loop = asyncio.new_event_loop()
    loop.close()
    return loop


class TestMakeKey:
    # 缓存键的归一化规则。

    def test_strips_query_and_trailing_slash(self) -> None:
        # 丢弃 query 与尾斜杠：同路径不同房间参数（分享/回放）须共享一条缓存，否则同一主播被当成不同 key 各拉一次风控凭据。
        assert _make_key("https://live.example.com/path/?a=1&b=2", None) == "https://live.example.com/path|"

    # 代理地址须纳入键：同房间走代理与直连拿到的是不同风控凭据，必须分别缓存
    def test_includes_proxy_addr(self) -> None:
        proxy = "http://127.0.0.1:8080"
        assert _make_key("https://live.example.com/", proxy) == f"https://live.example.com|{proxy}"

    def test_proxy_and_direct_are_distinct(self) -> None:
        # 混用会触发二次验证，故直连与代理的键必须不相等；键级隔离也防止两侧 cookie 互相泄漏。
        direct = _make_key("https://live.example.com/", None)
        proxied = _make_key("https://live.example.com/", "http://127.0.0.1:8080")
        assert direct != proxied


# 统一读取入口 fetch_cookies：首次拉取写入、命中复用、TTL 失效、失败/空值不缓存。
# 并发维度（同循环 reentrant、跨线程）是 singleflight 去重与跨循环交付的关键回归点。
class TestFetchCookies:
    async def test_first_fetch_caches_and_returns(self) -> None:
        # 首次拉取即写入；同时锁住 fetcher 透传参数（与 ttwid/spider 的调用约定一致）。
        calls: list[dict[str, Any]] = []

        async def fake_fetcher(**kwargs: Any) -> dict[str, Any]:
            calls.append(kwargs)
            return {"ttwid": "abc", "passport": "yes"}

        result = await fetch_cookies("https://live.example.com/", fetcher=fake_fetcher)
        assert result == {"ttwid": "abc", "passport": "yes"}
        assert len(calls) == 1
        kwargs = calls[0]
        assert kwargs["url"] == "https://live.example.com/"
        assert kwargs["return_cookies"] is True
        # 10s 是网络拉 cookie 的普遍超时预算：过短易误判风控，过长拖慢首帧
        assert kwargs["timeout"] == 10
        # 默认禁用 HTTP/2：旧版 curl_cffi 在部分平台对 HTTP/2 支持不稳，须与调用方约定一致
        assert kwargs["http2"] is False

    # 命中缓存后不得再次调用 fetcher（calls==1）：守护 singleflight「只拉一次」核心不变量
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

    # 非字符串 cookie 值须强制为 str：下游拼 Cookie 头要求 str，int/float 不得泄漏
    async def test_values_are_str_coerced(self) -> None:
        async def fake_fetcher(**kwargs: Any) -> dict[str, Any]:
            return {"a": 1, "b": 1.5}  # type: ignore[return-value]

        result = await fetch_cookies("https://live.example.com/", fetcher=fake_fetcher)
        assert result == {"a": "1", "b": "1.5"}

    # async_req(return_cookies=True) 的另一种成功形态 (其他数据, cookie_dict)：须解包第二个元素
    async def test_tuple_result_compat(self) -> None:
        async def fake_fetcher(**kwargs: Any) -> tuple[bool, dict[str, Any]]:
            return (True, {"k": "v"})

        result = await fetch_cookies("https://live.example.com/", fetcher=fake_fetcher)
        assert result == {"k": "v"}

    # ttl=0 即「每次都过期」：连续两次 fetch 各拉一次（calls==2），证明 TTL 判定生效而非被命中短路。
    async def test_ttl_zero_refetches_every_time(self) -> None:
        calls = 0

        async def fake_fetcher(**kwargs: Any) -> dict[str, Any]:
            nonlocal calls
            calls += 1
            return {"a": "1"}

        await fetch_cookies("https://live.example.com/", ttl=0, fetcher=fake_fetcher)
        await fetch_cookies("https://live.example.com/", ttl=0, fetcher=fake_fetcher)
        assert calls == 2

    # 每条 entry 记下自己的失效时刻，两个读取方都只认这条时刻：短 ttl 写入的条目
    # 不得被读取侧的 DEFAULT_TTL 续命，长 ttl 写入的也不得被更小的 ttl 提前判死。
    async def test_recorded_ttl_governs_both_readers(self, fake_clock: list[float]) -> None:
        calls = 0

        async def fake_fetcher(**kwargs: Any) -> dict[str, Any]:
            nonlocal calls
            calls += 1
            return {"a": "1"}

        # 短寿命凭据：以 ttl=60 写入，越过 60 秒后 get_cached 必须判 miss
        await fetch_cookies("https://short.example.com/", ttl=60, fetcher=fake_fetcher)
        fake_clock[0] += 61
        assert get_cached("https://short.example.com/") is None, "写入侧的短 ttl 被读取侧的 DEFAULT_TTL 覆盖"

        # 长寿命凭据：以 ttl=DEFAULT_TTL+600 写入，越过 DEFAULT_TTL 后 get_cached 仍须命中，
        # 而 fetch_cookies 带着**更小**的 ttl 去读也不得因此提前重新拉取（读取方无权续命也无权判死）
        await fetch_cookies("https://long.example.com/", ttl=DEFAULT_TTL + 600, fetcher=fake_fetcher)
        fake_clock[0] += DEFAULT_TTL + 1
        assert get_cached("https://long.example.com/") == {"a": "1"}, "长寿命条目被 get_cached 按 30 分钟判死"
        assert await fetch_cookies("https://long.example.com/", ttl=30, fetcher=fake_fetcher) == {"a": "1"}
        assert calls == 2, "读取方传的 ttl 不该决定条目寿命（多拉一次就是一次风控触发）"
        # 越过条目自己记录的寿命（DEFAULT_TTL+600）后才失效
        fake_clock[0] += 600
        assert get_cached("https://long.example.com/") is None
        assert await fetch_cookies("https://long.example.com/", fetcher=fake_fetcher) == {"a": "1"}
        assert calls == 3

    # singleflight 层与 cookie 层同口径：读取方传的 ttl 不改变命中判定。
    async def test_singleflight_recorded_ttl_governs_readers(self, fake_clock: list[float]) -> None:
        calls = 0

        async def _factory() -> str:
            nonlocal calls
            calls += 1
            return "v"

        assert await cc.singleflight("k-ttl", factory=_factory, ttl=60, timeout=2) == "v"
        fake_clock[0] += 61
        # 条目自己的 60 秒已过：即使调用方传更大的 ttl 也必须重新拉取
        assert await cc.singleflight("k-ttl", factory=_factory, ttl=DEFAULT_TTL, timeout=2) == "v"
        assert calls == 2, "singleflight 侧仍按调用方 ttl 判新鲜（短寿命凭据被续命）"
        # 反向：条目按 DEFAULT_TTL+600 写入后（第 3 次拉取），调用方传更小的 ttl 不得再拉一次
        assert await cc.singleflight("k-long", factory=_factory, ttl=DEFAULT_TTL + 600, timeout=2) == "v"
        assert calls == 3
        fake_clock[0] += DEFAULT_TTL + 1
        assert await cc.singleflight("k-long", factory=_factory, ttl=30, timeout=2) == "v"
        assert calls == 3, "读取方传的 ttl 不该决定条目寿命"

    # 代理与直连虽访问同房间，但键不同 → 各 fetch 一次（calls==[None, proxy]）：代理地址须正确透传 fetcher 且不串用 cookie
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

    # fetcher 首调抛错须返回空字典且不固化缓存，下次访问重新拉取（calls==2）：避免失败凭据被永久复用或把异常误判为「未直播」
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
        second = await fetch_cookies("https://live.example.com/", fetcher=fake_fetcher)
        assert second == {"ok": "1"}
        assert calls == 2

    # 空字典视为「未拿到任何风控凭据」，与异常同等待遇：不缓存、下次重试（calls==2），而非当作有效命中导致后续一直拿到空 cookie
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

        # patch cc.async_req 而非 import 级名：fetch_cookies 走模块全局引用 cc.async_req，必须打在模块属性上
        monkeypatch.setattr(cc, "async_req", fake_async_req)
        result = await fetch_cookies("https://live.example.com/")
        assert result == {"ttwid": "from_async_req"}
        assert seen["url"] == "https://live.example.com/"

    async def test_same_loop_reentrant_no_deadlock(self) -> None:
        # 同事件循环内并发 gather：既不死锁、结果一致，也应只拉取一次（singleflight）。
        # [历史注] 旧 RLock 跨 await 持有时，同循环协程全部可重入、互斥失效并并发拉取同一网址——
        # 正是本模块要消除的风控触发源。
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
        # barrier.wait()/join() 都必须带超时：本用例是「被测代码死锁就整轮挂死」的形态（单条卡住会拖垮整个
        # pytest 会话与 CI job，日志里还看不出是谁），并把「线程是否真退出」写成断言——死锁当场判红而非无声等待。
        _JOIN_TIMEOUT_SECONDS = 15.0

        async def fake_fetcher(**kwargs: Any) -> dict[str, Any]:
            nonlocal call_count
            with call_lock:
                call_count += 1
            await asyncio.sleep(0.01)
            return {"did": "shared"}

        def worker() -> None:
            barrier.wait(timeout=_JOIN_TIMEOUT_SECONDS)

            async def _run() -> dict[str, Any]:
                return await fetch_cookies("https://live.kuaishou.com/", fetcher=fake_fetcher)

            results.append(asyncio.run(_run()))

        threads = [threading.Thread(target=worker) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=_JOIN_TIMEOUT_SECONDS)
        alive = [t.name for t in threads if t.is_alive()]
        assert not alive, f"线程未在 {_JOIN_TIMEOUT_SECONDS}s 内退出（疑似死锁）：{alive}"

        assert call_count == 1
        assert all(r == {"did": "shared"} for r in results)


class TestGetCached:
    # 同步只读查询：命中就返回值、未命中/过期就 None，任何情况都不触发网络（与 fetch 路径解耦）。

    def test_miss_returns_none(self) -> None:
        assert get_cached("https://live.example.com/") is None

    async def test_hit_returns_cookies(self) -> None:
        async def fake_fetcher(**kwargs: Any) -> dict[str, Any]:
            return {"ttwid": "abc"}

        await fetch_cookies("https://live.douyin.com/", fetcher=fake_fetcher)
        assert get_cached("https://live.douyin.com/") == {"ttwid": "abc"}

    # 手动把 expire_ts 回拨到 DEFAULT_TTL 之前：缓存里有条目也须判 miss，守 TTL 失效语义而非「有没有条目」
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


# 失效入口：按 key 精准失效单条，或按无参清空整份缓存（「不误伤其它房间」是本组的语义本体）。
class TestInvalidate:
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

    # 失效 a 不影响 b：防止退化成一键清空式。
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


# 整份缓存清空入口：clear 后所有 key miss，语义与 invalidate() 无参对齐；也是本文件 fixture 的复位手段。
class TestClear:
    async def test_clears_all_entries(self) -> None:
        async def fake_fetcher(**kwargs: Any) -> dict[str, Any]:
            return {"a": "1"}

        await fetch_cookies("https://a.example.com/", fetcher=fake_fetcher)
        await fetch_cookies("https://b.example.com/", fetcher=fake_fetcher)
        clear()
        assert cc._cookie_cache == {}
        assert get_cached("https://a.example.com/") is None


# ── 通用 singleflight 必须与 fetch_cookies 一样做世代比对 ──────────────
# fetch_cookies 早已补「写回前比对 _cache_generation」；singleflight 缺这半条时，拉取期间被
# invalidate_generic()/clear() 作废的结果仍被无条件回填，「凭据被平台拒绝 → 失效」只能等 30 分钟
# TTL 自然过期，自愈链断在半路。
class TestSingleflightGeneration:
    async def test_invalidate_during_inflight_fetch_is_not_resurrected(self) -> None:
        gate = asyncio.Event()
        calls = 0

        async def _factory() -> str:
            nonlocal calls
            calls += 1
            await gate.wait()
            return "rejected-value"

        task = asyncio.create_task(cc.singleflight("bili_buvid3|", factory=_factory, timeout=2))
        # 等拉取者真正进入 factory（即已登记在途、尚未回填）
        for _ in range(200):
            if "bili_buvid3|" in cc._generic_inflight and calls == 1:
                break
            await asyncio.sleep(0.01)
        assert calls == 1

        # 关键交错：拉取者还在路上，失效已经发生
        cc.invalidate_generic("bili_buvid3|")
        gate.set()
        assert await task == "rejected-value"
        assert "rejected-value" not in [v for v, _ts in cc._generic_cache.values()], "被作废的凭据又被回填"

        # 再取一次必须走新拉取，而不是命中那份被拒的值（第二调用的是另一个 factory）
        cc.invalidate_generic("bili_buvid3|")
        second = await cc.singleflight("bili_buvid3|", factory=_make_counting_factory(), timeout=2)
        assert second == "fresh-value"
        assert calls == 1  # 故 calls 仍为 1：第一次的 factory 没被再执行

    # 未被作废时结果照常缓存（不得把缓存写没，否则去重意义全无）
    async def test_normal_fetch_still_cached(self) -> None:
        calls = 0

        async def _factory() -> str:
            nonlocal calls
            calls += 1
            return "v"

        assert await cc.singleflight("k-cached", factory=_factory, timeout=2) == "v"
        assert await cc.singleflight("k-cached", factory=_factory, timeout=2) == "v"
        assert calls == 1
        assert cc._generic_cache["k-cached"][0] == "v"


def _make_counting_factory() -> Any:
    async def _factory() -> str:
        return "fresh-value"

    return _factory


# ── ：失败日志的异常文本必须脱敏 ────────────────────────────────────────────
# factory 内部走 async_req/sync_req，异常文本常内嵌带签名/鉴权查询串的完整 URL 与代理凭据，
# 而 logs/ 按 rotation 保留多份 ⇒ 原文入日志等于凭据长期落盘（fetch_cookies 侧早已脱敏）。
class TestFailureLogMasksCredentials:
    async def test_singleflight_failure_log_masks_exception_text(self, log_capture: io.StringIO) -> None:
        async def _boom() -> str:
            raise ConnectionError(_SECRET_URL)

        assert await cc.singleflight("mask_probe|", factory=_boom, timeout=2) is None
        text = log_capture.getvalue()
        # 「值确实消失」而非「调用过 mask_credentials」；同时要求脱敏痕迹与异常类型都在，
        # 前者防「整行被抹空也算通过」，后者防「脱敏顺手把归因信息一起删掉」。
        assert _SECRET_TOKEN not in text, "签名/token 参数随异常文本落进轮转日志"
        assert _SECRET_PROXY_PASS not in text, "代理口令随异常文本落进轮转日志"
        assert "***" in text
        assert "ConnectionError" in text
        assert "凭据拉取失败" in text

    # fetch_cookies 一侧本已正确，此处一并钉住，防两侧再漂移
    async def test_fetch_cookies_failure_log_masks_exception_text(self, log_capture: io.StringIO) -> None:
        async def _boom(**kwargs: Any) -> dict[str, Any]:
            raise ConnectionError(_SECRET_URL)

        assert await fetch_cookies("https://mask.example.com/", fetcher=_boom) == {}
        text = log_capture.getvalue()
        assert _SECRET_TOKEN not in text and _SECRET_PROXY_PASS not in text
        assert "***" in text and "ConnectionError" in text

    # 行为锁挡不住「新加一条漏抹」（新日志点没人写用例就无人核对），故再钉一条 AST 结构锁：
    # 本模块每个 logger.<level>(i18n.tr(模板, **kw)) 里，实参名为 e / err / url / masked_url 的表达式必须含
    # mask_credentials(...)；type(e).__name__ 不含凭据，放行。易踩点：① 关键字实参挂在内层 i18n.tr(...) 而非
    # logger 调用上，只遍历 logger 节点会恒为空、锁恒真；② 须同时断言受检点位数，否则模板一改即空集通过。
    def test_every_credential_bearing_log_arg_is_masked(self) -> None:
        import ast
        from pathlib import Path

        tree = ast.parse(Path(cc.__file__).read_text(encoding="utf-8"))
        offenders: list[str] = []
        inspected = 0
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
                continue
            if node.func.attr not in {"warning", "error", "debug", "info"}:
                continue
            if not node.args:
                continue
            template_call = node.args[0]
            if not (isinstance(template_call, ast.Call) and isinstance(template_call.func, ast.Attribute)):
                continue
            if template_call.func.attr != "tr":
                continue
            for kw in template_call.keywords:
                if kw.arg not in {"e", "err", "url", "masked_url"}:
                    continue
                inspected += 1
                src = ast.unparse(kw.value)
                if "mask_credentials" in src or "__name__" in src:
                    continue
                offenders.append(f"line {kw.lineno or node.lineno}: {kw.arg}={src}")
        # 现存量受检点位（实测）：fetch_cookies 与 singleflight 各一处 e= 加一处 url=，
        # 两处超时告警的 masked_key 不计入本集合；下限取 3 留一点余量，上限不钉（新增日志点应当更多）
        assert inspected >= 3, f"受检点位只剩 {inspected} 个：日志模板形态可能已变更，本锁已失效"
        assert not offenders, "以下日志实参未经 utils.mask_credentials 脱敏：\n" + "\n".join(offenders)


# ── ：在途登记表的孤儿回收 ─────────────────────────────────────────────────
# 口径：只回收 owner 循环已关闭的登记（活拉取者一律不动，否则会连带丢掉它的等待者并让同 key 并发
# 重发请求），并唤醒被回收登记的等待者，令其立刻拿空结果而不是白等。
# [历史注] 线程被硬杀后登记既无人交付也无人摘除，旧 invalidate()/clear() 只清结果字典 → 该 key 从此
# 每次走「等待 timeout+余量 → 空结果」，永不自愈。
class TestInflightOrphanReclaim:
    async def test_clear_reclaims_dead_registration_and_wakes_waiters(self) -> None:
        loop = asyncio.get_running_loop()
        key = _make_key("https://orphan.example.com/", None)
        waiter = loop.create_future()
        with cc._cache_lock:
            cc._inflight[key] = cc._Inflight(owner_loop=_dead_loop(), waiters=[(loop, waiter)])
        clear()
        with cc._cache_lock:
            assert key not in cc._inflight, "clear() 没回收已失主的在途登记"
        # 等待者被就地唤醒并拿到空结果（等价于它本会走到的超时结局，只是不再白等）
        assert await asyncio.wait_for(waiter, timeout=5) == {}

    async def test_invalidate_reclaims_dead_generic_registration(self) -> None:
        loop = asyncio.get_running_loop()
        key = "kuaishou_did|orphan"
        waiter: asyncio.Future[Any] = loop.create_future()
        waiter2: asyncio.Future[Any] = loop.create_future()
        with cc._cache_lock:
            cc._generic_inflight[key] = cc._Inflight(owner_loop=_dead_loop(), waiters=[(loop, waiter), (loop, waiter2)])
        cc.invalidate_generic(key)
        with cc._cache_lock:
            assert key not in cc._generic_inflight, "invalidate_generic() 没回收已失主的在途登记"
        assert await asyncio.wait_for(waiter, timeout=5) is None
        assert await asyncio.wait_for(waiter2, timeout=5) is None

    async def test_dead_registration_self_heals_on_next_fetch(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # 不等任何人调用 invalidate/clear：下一次取用就自愈——否则「恒走等待超时→空结果」
        monkeypatch.setattr(cc, "_INFLIGHT_WAIT_MARGIN", 0.05)
        key = _make_key("https://orphan2.example.com/", None)
        with cc._cache_lock:
            cc._inflight[key] = cc._Inflight(owner_loop=_dead_loop(), waiters=[])
        calls = 0

        async def fake_fetcher(**kwargs: Any) -> dict[str, Any]:
            nonlocal calls
            calls += 1
            return {"did": "fresh"}

        got = await fetch_cookies("https://orphan2.example.com/", timeout=0, fetcher=fake_fetcher)
        assert calls == 1, "死登记没被接管：调用方挂在了一个永不交付的拉取上"
        assert got == {"did": "fresh"}

    async def test_takeover_also_wakes_waiters_of_the_dead_registration(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # 接管时不能只顾自己：挂在死登记上的等待者原本要各自等满 timeout+余量，必须就地交付空结果
        monkeypatch.setattr(cc, "_INFLIGHT_WAIT_MARGIN", 30.0)
        loop = asyncio.get_running_loop()
        key = _make_key("https://orphan3.example.com/", None)
        stranded_waiter: asyncio.Future[Any] = loop.create_future()
        with cc._cache_lock:
            cc._inflight[key] = cc._Inflight(owner_loop=_dead_loop(), waiters=[(loop, stranded_waiter)])
        calls = 0

        async def fake_fetcher(**kwargs: Any) -> dict[str, Any]:
            nonlocal calls
            calls += 1
            return {"did": "fresh"}

        async def _probe() -> None:
            assert await asyncio.wait_for(stranded_waiter, timeout=5) == {}

        probe = asyncio.create_task(_probe())
        got = await fetch_cookies("https://orphan3.example.com/", timeout=1, fetcher=fake_fetcher)
        await asyncio.wait_for(probe, timeout=5)
        assert got == {"did": "fresh"} and calls == 1

    async def test_waking_waiters_of_a_closed_loop_does_not_raise(self) -> None:
        # 等待者自己的循环也关了（其线程同批死亡）：唤醒必须静默丢弃，
        # 不得让 clear()/invalidate() 这个同步入口抛 RuntimeError——那会把「清理缓存」
        # 打成「调用方崩」，而 invalidate_ttwid 正是平台拒绝路径上调用的。
        loop = asyncio.get_running_loop()
        key = _make_key("https://orphan4.example.com/", None)
        with cc._cache_lock:
            cc._inflight[key] = cc._Inflight(owner_loop=_dead_loop(), waiters=[(_dead_loop(), loop.create_future())])
        clear()  # 不得抛
        with cc._cache_lock:
            assert key not in cc._inflight

    async def test_clear_keeps_registration_of_a_live_fetcher(self) -> None:
        gate = asyncio.Event()

        async def fake_fetcher(**kwargs: Any) -> dict[str, Any]:
            await gate.wait()
            return {"did": "shared"}

        key = _make_key("https://live.example.com/", None)
        fetcher_task = asyncio.create_task(fetch_cookies("https://live.example.com/", fetcher=fake_fetcher))
        for _ in range(200):
            if key in cc._inflight:
                break
            await asyncio.sleep(0.01)
        assert key in cc._inflight, "拉取者没登记在途（用例前提不成立）"
        waiter_task = asyncio.create_task(fetch_cookies("https://live.example.com/", fetcher=fake_fetcher))
        for _ in range(200):
            if len(cc._inflight[key].waiters) == 1:
                break
            await asyncio.sleep(0.01)

        clear()
        with cc._cache_lock:
            assert key in cc._inflight, "clear() 误摘仍活着的拉取者登记"

        gate.set()
        value = {"did": "shared"}
        assert await asyncio.wait_for(fetcher_task, timeout=5) == value
        # 等待者仍由活着的拉取者交付本次值（既有口径：世代比对只挡回填缓存）
        assert await asyncio.wait_for(waiter_task, timeout=5) == value
        with cc._cache_lock:
            assert key not in cc._inflight, "拉取者收尾没归还登记位"

    async def test_late_finisher_does_not_steal_takeover_registration(self) -> None:
        # 收尾只归还自己那一格：手工换掉登记位，验证迟到的拉取者不摘走接管者的登记。
        # [历史注] 原实现 pop(key) 不认归属，会在重新占位的窗口里连带摘掉新登记、让新等待者无人交付。
        gate = asyncio.Event()
        mine_key = _make_key("https://steal.example.com/", None)

        async def fake_fetcher(**kwargs: Any) -> dict[str, Any]:
            await gate.wait()
            return {"did": "late"}

        fetcher_task = asyncio.create_task(fetch_cookies("https://steal.example.com/", fetcher=fake_fetcher))
        for _ in range(200):
            if mine_key in cc._inflight:
                break
            await asyncio.sleep(0.01)
        takeover = cc._Inflight(owner_loop=asyncio.get_running_loop())
        takeover_waiter: asyncio.Future[Any] = asyncio.get_running_loop().create_future()
        takeover.waiters.append((asyncio.get_running_loop(), takeover_waiter))
        with cc._cache_lock:
            cc._inflight[mine_key] = takeover  # 模拟本登记被回收、同 key 已由他人占位
        gate.set()
        await asyncio.wait_for(fetcher_task, timeout=5)
        with cc._cache_lock:
            assert cc._inflight.get(mine_key) is takeover, "迟到的拉取者摘走了接管者的登记位"
        cc._inflight.pop(mine_key, None)


# ────────────────────────────────────────────────────────────
# src/room.py 的 sec_user_id → 抖音号进程级缓存
# 与上面 cookie 缓存同族（同为「进程级、TTL、外部可控 key」的映射），故用例并档在此。
# ────────────────────────────────────────────────────────────


@pytest.fixture
def _clean_sec_uid_cache() -> Iterator[None]:
    # 该缓存是模块级 dict，按文件/用例共享；不清会把上一条用例的条目留给下一条（R9 同族污染）。
    room_module._SEC_UID_UNIQUE_CACHE.clear()
    yield
    room_module._SEC_UID_UNIQUE_CACHE.clear()


@pytest.mark.usefixtures("_clean_sec_uid_cache")
class TestSecUidUniqueCacheBound:
    def test_expired_entry_is_popped_on_sight(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # 过期条目必须见到即删：sec_user_id 属外部可控且**只出现一次**的 key（换主播就不再回来）。
        # [历史注] 旧实现读取时只「不返回」过期条目、从不删除 → 过期条目永远无人回收，24×7 长跑下 dict 只增不减。
        holder = [1000.0]
        shim = types.SimpleNamespace(**vars(time))
        shim.monotonic = lambda: holder[0]
        # 进程级 stdlib 替身走被测模块命名空间的 shim（AGENTS：os/time 本体一字节不动）
        monkeypatch.setattr(room_module, "time", shim)

        _set_cached_unique_id("secA", "uidA")
        assert _get_cached_unique_id("secA") == "uidA"

        holder[0] += room_module._SEC_UID_CACHE_TTL + 1.0
        assert _get_cached_unique_id("secA") is None
        assert "secA" not in room_module._SEC_UID_UNIQUE_CACHE, "过期条目没被删除：无界增长的成因"

    def test_fresh_entry_survives_the_pop_path(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # 反向保证：不得把「过期即删」写成「一律删」（那会让缓存彻底失效、每轮都打 iesdouyin 接口）。
        assert _get_cached_unique_id("secB") is None
        _set_cached_unique_id("secB", "uidB")
        assert _get_cached_unique_id("secB") == "uidB"
        assert "secB" in room_module._SEC_UID_UNIQUE_CACHE

    def test_cache_size_is_bounded(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(room_module, "_SEC_UID_CACHE_MAX_ENTRIES", 8)
        for i in range(30):
            _set_cached_unique_id(f"sec{i}", f"uid{i}")
        assert len(room_module._SEC_UID_UNIQUE_CACHE) == 8
        assert "sec0" not in room_module._SEC_UID_UNIQUE_CACHE
        assert _get_cached_unique_id("sec29") == "uid29"


# ────────────────────────────────────────────────────────────
# src/room.py 的默认头合并与 Cookie 键级合并
# ────────────────────────────────────────────────────────────


class TestRoomHeaderMerge:
    def test_cookie_only_caller_still_gets_default_user_agent(self) -> None:
        # 旧判据「UA/Cookie 任一存在就完全不补默认头」：只填 Cookie 的调用方拿不到移动端 UA，
        # 而抖音接口对 UA 敏感（见 DESKTOP_UA 注释与「已知坑」抖音风控条目）→ 200 + 空 body。
        merged = _merge_default_headers({"Cookie": "sessionid=ABC"})
        assert merged["Cookie"] == "sessionid=ABC"
        assert merged["User-Agent"] == HEADERS["User-Agent"]

    def test_user_agent_only_caller_is_not_given_an_empty_cookie(self) -> None:
        # 空值默认刻意不注入：HEADERS["Cookie"] = "" 是「让服务器重新下发」的占位，
        # 主动发出空 Cookie 头会改变请求指纹，与旧行为「不带该头」不等价。
        merged = _merge_default_headers({"User-Agent": "MyUA"})
        assert merged["User-Agent"] == "MyUA"
        assert "Cookie" not in merged

    def test_lowercase_caller_key_does_not_duplicate_the_header(self) -> None:
        # HTTP 头名大小写不敏感：合并后同时挂 user-agent 与 User-Agent 会让 httpx 发两个值。
        merged = _merge_default_headers({"user-agent": "MyUA"})
        assert [k for k in merged if k.lower() == "user-agent"] == ["user-agent"]

    def test_merge_does_not_mutate_shared_headers(self) -> None:
        # 多线程共享 HEADERS（模块级），合并必须产出新 dict（旧代码靠调用点 dict() 复制防污染）。
        before = dict(HEADERS)
        merged = _merge_default_headers({"Cookie": "x=1"})
        merged["Cookie"] = "changed"
        assert HEADERS == before


class TestRoomCookiePairMerge:
    def test_ttwid_replaces_only_its_own_pair(self) -> None:
        # 本体：ttwid 只替换 Cookie 串里的同名键。[历史注] 旧写法 `headers["Cookie"] = ttwid_cookie` 整串覆盖，
        # 把用户填的登录态一起抹掉。
        merged = _merge_cookie_pair("sessionid=ABC; ttwid=OLD; sid_guard=G", "ttwid=NEW")
        assert merged == "sessionid=ABC; ttwid=NEW; sid_guard=G"
        assert "OLD" not in merged

    def test_pair_is_appended_when_absent(self) -> None:
        assert _merge_cookie_pair("sessionid=ABC", "ttwid=NEW") == "sessionid=ABC; ttwid=NEW"
        assert _merge_cookie_pair("", "ttwid=NEW") == "ttwid=NEW"

    def test_existing_pair_name_is_matched_case_insensitively(self) -> None:
        assert _merge_cookie_pair("TTWID=OLD; a=1", "ttwid=NEW") == "ttwid=NEW; a=1"

    def test_duplicate_pairs_collapse_to_one(self) -> None:
        assert _merge_cookie_pair("ttwid=ONE; ttwid=TWO", "ttwid=NEW") == "ttwid=NEW"


# ────────────────────────────────────────────────────────────
# 接线点锁：调用点必须真的走这两个 helper
#
# helper 单测只能证明函数本身对，证明不了调用点用到了它：把 get_unique_id 里那行改回
# `headers[cookie_key] = ttwid_cookie`（整串覆盖）、或从 get_sec_user_id / get_unique_id 删掉
# `_merge_default_headers(...)`，helper 用例**一条都不会红**——函数还在也对，只是没人调（AGENTS
# 「安全边界不得再用文本锁 / 测试不得自实现被测逻辑」点名的假绿形态）。故这里按 AST 判「调用点是否
# 存在、写的值是不是 helper 的返回值」，判据取「谁被调用、赋的是什么」，不取变量名或某句文案。
# ────────────────────────────────────────────────────────────


def _room_tree() -> Any:
    source = (Path(__file__).resolve().parent.parent / "src" / "room.py").read_text(encoding="utf-8")
    return ast.parse(source)


def _room_func(name: str) -> Any:
    for node in _room_tree().body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    raise AssertionError(f"src/room.py 不再定义 {name}()：M-43 的接线点判据已失效，需同步改本锁")


def _called_names(node: Any) -> set[str]:
    found: set[str] = set()
    for sub in ast.walk(node):
        if isinstance(sub, ast.Call):
            if isinstance(sub.func, ast.Name):
                found.add(sub.func.id)
            elif isinstance(sub.func, ast.Attribute):
                found.add(sub.func.attr)
    return found


def _headers_subscript_assigns(fn: Any) -> list[Any]:
    out: list[Any] = []
    for sub in ast.walk(fn):
        if isinstance(sub, ast.Assign) and any(
            isinstance(t, ast.Subscript) and isinstance(t.value, ast.Name) and t.value.id == "headers"
            for t in sub.targets
        ):
            out.append(sub)
    return out


def test_ttwid_write_back_goes_through_the_pair_merger() -> None:
    assigns = _headers_subscript_assigns(_room_func("get_unique_id"))
    assert len(assigns) == 1, f"get_unique_id 内对 headers[..] 的写入应为 1 处（Cookie 位），实测 {len(assigns)} 处"
    value = assigns[0].value
    assert isinstance(value, ast.Call), (
        f"Cookie 位被赋成非 helper 调用的形态（第 {getattr(value, 'lineno', 0)} 行）："
        f"整串覆盖会抹掉用户填的登录态 Cookie（M-43）"
    )
    assert (
        isinstance(value.func, ast.Name) and value.func.id == "_merge_cookie_pair"
    ), "Cookie 位必须经 _merge_cookie_pair 只替换 ttwid 这一对（M-43 接线点）"
    assert len(value.args) == 2, "_merge_cookie_pair 需要「原 Cookie 串 + 新键值对」两个实参"


def test_default_header_merge_is_applied_at_both_readers() -> None:
    for name in ("get_sec_user_id", "get_unique_id"):
        assert "_merge_default_headers" in _called_names(
            _room_func(name)
        ), f"{name}() 不再调用 _merge_default_headers：M-43 退回到「任一默认头存在就不补另一个」"


def test_unique_id_headers_are_copied_before_writing_cookie() -> None:
    # HEADERS 是模块级共享字典（多线程），写入 Cookie 前必须 dict() 复制一份，
    # 否则一次自动取 ttwid 会把凭据永久写进全局默认头。
    fn = _room_func("get_unique_id")
    assert "_merge_default_headers" in _called_names(fn) and "dict" in _called_names(
        fn
    ), "get_unique_id() 缺少对合并结果的 dict() 复制：会污染模块级 HEADERS（M-43 附带防线）"
