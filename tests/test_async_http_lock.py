# Tests for src/async_http.py 批次5修复 - 客户端缓存锁跨线程安全回归测试.
# 使用 mock 客户端（不创建真实 httpx.AsyncClient），保证测试确定性且无网络/环境依赖.

import asyncio
import threading
from unittest.mock import patch

from src import async_http as ah


class FakeAsyncClient:
    # 模拟 httpx.AsyncClient 的最小接口（_get_client 仅使用 is_closed / aclose）
    # 之所以不创建真实客户端：真实 AsyncClient 会绑定事件循环与连接池，并发用例下
    # 会引入网络/时序不确定性，而本文件只关心「缓存与锁」的行为，用假对象即可确定性复现。
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
        # 每个用例前清空客户端缓存：缓存是模块级全局状态，若跨用例残留会掩盖
        # 「新建/复用/淘汰」的判定逻辑（例如上一个用例留下的客户端会被误判为本轮复用）。
        # 清理本身也要持同一把锁，避免与后台线程争用。
        with ah._client_cache_lock:
            ah._client_cache.clear()

    # 守护行为：8 个线程各自 asyncio.run（即 8 个独立事件循环）并发取客户端，不应抛异常。
    # 这是本项目真实并发模型的复现——每个直播间一个线程、各自 asyncio.run，
    # 旧实现用模块级 asyncio.Lock 单例，锁会惰性绑定到首个事件循环，后续循环 await 时
    # 抛「bound to a different event loop」，且该异常被 async_req 的 except 吞掉返回空串，
    # 最终被误判成平台风控并级联失败。改为按当前循环缓存 threading.Lock 后此路径应无异常。
    # 不再过滤 RuntimeWarning（2026-09-04 修复）：跨循环一律不创建 aclose 协程后，
    # 本用例不应产生任何 "coroutine ... was never awaited" 告警；保留过滤会掩盖回归。
    def test_concurrent_threads_no_cross_loop_error(self) -> None:
        errors: list[Exception] = []

        # 注意在线程内收集异常而非抛出：子线程异常不会传播到 pytest，
        # 若直接断言会假绿，故统一 append 后在主线程断言列表为空。
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

    # 守护行为：同一事件循环内两次取客户端应命中缓存（连接复用的前提）。
    # 若此处返回不同实例，意味着每次请求都新建连接池，长连接与 TLS 握手开销将成倍放大。
    def test_same_loop_reuses_client(self) -> None:
        async def get_twice() -> tuple:
            a = await ah._get_client(proxy_addr=None, timeout=10, verify=True, http2=False)
            b = await ah._get_client(proxy_addr=None, timeout=10, verify=True, http2=False)
            return a, b

        with patch("httpx.AsyncClient", new=FakeAsyncClient):
            a, b = asyncio.run(get_twice())
        assert a is b  # 同一循环内复用连接池

    # 守护行为：换事件循环后必须换客户端。旧客户端绑定旧循环，跨循环复用必然报错；
    # 而旧客户端不在此处 await 关闭（会触发跨循环 await），交由 GC 回收，故只断言实例不同。
    # 两次 asyncio.run 之间旧循环已结束，这正是「不能缓存跨循环客户端」的原因。
    def test_loop_change_replaces_client_and_closes_old(self) -> None:
        with patch("httpx.AsyncClient", new=FakeAsyncClient):
            first = asyncio.run(ah._get_client(proxy_addr=None, timeout=10, verify=True, http2=False))
            second = asyncio.run(ah._get_client(proxy_addr=None, timeout=10, verify=True, http2=False))
        assert first is not second
        # 旧循环已关闭，旧客户端交由 GC（不跨循环 await）
        assert second is not None

    # 守护行为：旧循环仍在其他线程运行时，换循环取客户端也绝不创建 aclose 协程。
    # 回归背景：旧实现在此场景用 run_coroutine_threadsafe 在旧循环上安排关闭，
    # 但旧循环可能正处于收尾阶段（is_running 为真却随时停止），安排的任务可能
    # 永不执行，GC 时报 "aclose was never awaited"/"Task was destroyed"（flaky）。
    # 断言旧客户端未被关闭即锁定「跨循环一律不调度关闭、交由 GC 兜底」语义。
    def test_cross_loop_running_old_loop_skips_close(self) -> None:
        loop_a = asyncio.new_event_loop()
        thread_a = threading.Thread(target=loop_a.run_forever, daemon=True)
        thread_a.start()
        try:
            with patch("httpx.AsyncClient", new=FakeAsyncClient):
                # 在后台循环 A 上创建并缓存客户端
                first = asyncio.run_coroutine_threadsafe(
                    ah._get_client(proxy_addr=None, timeout=10, verify=True, http2=False), loop_a
                ).result(timeout=15)
                # 主线程换循环 B 取客户端：淘汰缓存但不在循环 A 上安排 aclose
                second = asyncio.run(ah._get_client(proxy_addr=None, timeout=10, verify=True, http2=False))
                assert first is not second
                assert not first.is_closed
        finally:
            loop_a.call_soon_threadsafe(loop_a.stop)
            thread_a.join(timeout=15)
            loop_a.close()

    # 守护行为：旧循环已停止但未关闭（asyncio.run 收尾窗口的形态：run_until_complete
    # 已返回、close() 尚未执行）时，同样不创建 aclose 协程——排入停止循环的回调永不执行，
    # 协程从未被 await，GC 时报 "aclose was never awaited"（曾致 1~2 个 flaky 告警）。
    # 此路径交由 GC 兜底，断言旧客户端未被关闭即锁定「跳过调度」语义。
    def test_cross_loop_stopped_old_loop_skips_close(self) -> None:
        loop_a = asyncio.new_event_loop()
        try:
            with patch("httpx.AsyncClient", new=FakeAsyncClient):
                # 循环 A 上创建客户端后循环即停止（不 close，复现收尾窗口形态）
                first = loop_a.run_until_complete(ah._get_client(proxy_addr=None, timeout=10, verify=True, http2=False))
                assert not loop_a.is_running() and not loop_a.is_closed()
                # 换循环 B 取客户端：淘汰缓存但不在停止的循环上调度 aclose
                second = asyncio.run(ah._get_client(proxy_addr=None, timeout=10, verify=True, http2=False))
                assert first is not second
                assert not first.is_closed
        finally:
            loop_a.close()

    # 守护行为：不同的连接参数（此处为 proxy）必须映射到不同缓存键。
    # 若共用缓存，代理配置不同的两个房间会互相借用到错误的连接池，
    # 表现为「明明配了代理却不生效」或「直连请求被代理污染」，且难以复现。
    def test_different_params_use_different_cache_keys(self) -> None:
        async def get_two() -> tuple:
            a = await ah._get_client(proxy_addr=None, timeout=10, verify=True, http2=False)
            b = await ah._get_client(proxy_addr="http://p:1", timeout=10, verify=True, http2=False)
            return a, b

        with patch("httpx.AsyncClient", new=FakeAsyncClient):
            a, b = asyncio.run(get_two())
        assert a is not b
