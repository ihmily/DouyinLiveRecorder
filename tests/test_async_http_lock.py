# src/async_http.py 批次5修复的回归用例：客户端缓存锁的跨线程安全。
# 全程使用 mock 客户端（不创建真实 httpx.AsyncClient），测试确定且无网络/环境依赖。

import asyncio
import threading
from unittest.mock import patch

from src import async_http as ah


class FakeAsyncClient:
    # httpx.AsyncClient 的最小替身（_get_client 只用 is_closed / aclose）。
    # 不建真实客户端：真实 AsyncClient 绑定事件循环与连接池，并发用例下会引入网络/时序
    # 不确定性，而本文件只关心「缓存与锁」，假对象即可确定性复现。
    def __init__(self, **kwargs: object) -> None:
        self.kwargs = kwargs
        self.closed = False

    @property
    def is_closed(self) -> bool:
        return self.closed

    async def aclose(self) -> None:
        self.closed = True


class TestClientCacheConcurrency:
    # _client_cache 由 threading.Lock 保护（临界区无 await）：多房间「独立线程 + 独立事件
    # 循环」并发获取客户端不应抛异常（原实现存在跨循环锁竞态）。

    def setup_method(self) -> None:
        # 每个用例前清空客户端缓存（模块级全局状态）：跨用例残留会掩盖「新建/复用/淘汰」
        # 的判定（上一例留下的客户端会被误判为本轮复用）。清理持同一把锁，避免与后台线程争用。
        with ah._client_cache_lock:
            ah._client_cache.clear()

    def teardown_method(self) -> None:
        # 与 setup 对称的收尾清理。本文件塞进模块级缓存的全是 FakeAsyncClient，
        # 只在 setup 清会让最后一例（及中途失败者）的条目跨文件滞留整个会话，后续按
        # 「缓存里是什么类型」推断的其它文件可能被这类替身污染。同样持锁清理。
        with ah._client_cache_lock:
            ah._client_cache.clear()

    # 8 个线程各自 asyncio.run（8 个独立事件循环）并发取客户端，不得抛异常。
    # 这是生产并发模型的复现：每直播间一线程、各自 asyncio.run。旧实现用模块级
    # asyncio.Lock 单例，锁惰性绑定到首个事件循环，后续循环 await 时抛
    # 「bound to a different event loop」，异常被 async_req 的 except 吞成空串，
    # 最终误判为平台风控并级联失败；改按当前循环缓存 threading.Lock 后此路径应无异常。
    # 不再过滤 RuntimeWarning：跨循环一律不创建 aclose 协程后，
    # 本用例不应产生任何 "coroutine ... was never awaited" 告警，保留过滤会掩盖回归。
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
        # join(timeout=15) **返回**不等于线程已退出——被测逻辑挂死时
        # join 超时静默返回、errors 仍空，本用例照绿（线程永不退出正是本文件要防的跨循环锁死
        # 形态）。必须逐线程断言 is_alive 为 False，才钉住「8 线程全部跑完」。
        for t in threads:
            assert not t.is_alive(), "join 超时后线程仍存活：被测逻辑挂死，不得判绿"

    # 同一事件循环内两次取客户端应命中缓存（连接复用的前提）；返回不同实例等于每次请求
    # 新建连接池，长连接与 TLS 握手开销成倍放大。
    def test_same_loop_reuses_client(self) -> None:
        async def get_twice() -> tuple:
            a = await ah._get_client(proxy_addr=None, timeout=10, verify=True, http2=False)
            b = await ah._get_client(proxy_addr=None, timeout=10, verify=True, http2=False)
            return a, b

        with patch("httpx.AsyncClient", new=FakeAsyncClient):
            a, b = asyncio.run(get_twice())
        assert a is b  # 同一循环内复用连接池

    # 换事件循环后必须换客户端：旧客户端绑定旧循环，跨循环复用必然报错；旧客户端不在此
    # await 关闭（会触发跨循环 await），交由 GC 回收，故只断言实例不同。两次 asyncio.run
    # 之间旧循环已结束，这正是「不能缓存跨循环客户端」的原因。
    def test_loop_change_replaces_client_and_closes_old(self) -> None:
        with patch("httpx.AsyncClient", new=FakeAsyncClient):
            first = asyncio.run(ah._get_client(proxy_addr=None, timeout=10, verify=True, http2=False))
            second = asyncio.run(ah._get_client(proxy_addr=None, timeout=10, verify=True, http2=False))
        assert first is not second
        # 旧循环已关闭，旧客户端交由 GC（不跨循环 await）
        assert second is not None

    # 旧循环仍在其他线程运行时，换循环取客户端也绝不创建 aclose 协程。
    # 旧实现在此场景用 run_coroutine_threadsafe 在旧循环上安排关闭，但旧循环可能正处于
    # 收尾阶段（is_running 为真却随时停止），任务可能永不执行，GC 时报
    # "aclose was never awaited"/"Task was destroyed"（flaky）。断言旧客户端未被关闭，
    # 即锁定「跨循环一律不调度关闭、交由 GC 兜底」语义。
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
            # 审查 7.11（与该同口径）：stop() 已投递、join 也已返回，但「join
            # 返回」不等于「run_forever 退出」——循环没停下来时 thread_a 会一直活着，本用例仍
            # 假绿并留下一个在跑的循环。断言放在 loop_a.close() 之后：判红时资源已回收，
            # 不会因这条断言再漏关一个循环。
            assert not thread_a.is_alive(), "loop_a.stop() 后 thread_a 仍未退出：run_forever 没停，不得判绿"

    # 旧循环已停止但未关闭（asyncio.run 收尾窗口：run_until_complete 已返回、close() 尚未
    # 执行）时同样不创建 aclose 协程——排入停止循环的回调永不执行，协程从未被 await，
    # GC 时报 "aclose was never awaited"（曾致 1~2 个 flaky 告警）。此路径交由 GC 兜底，
    # 断言旧客户端未被关闭即锁定「跳过调度」语义。
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

    # 不同连接参数（此处为 proxy）必须映射到不同缓存键：共用缓存会让代理配置不同的两个
    # 房间互相借错连接池，表现为「配了代理却不生效」或「直连请求被代理污染」，且难以复现。
    def test_different_params_use_different_cache_keys(self) -> None:
        async def get_two() -> tuple:
            a = await ah._get_client(proxy_addr=None, timeout=10, verify=True, http2=False)
            b = await ah._get_client(proxy_addr="http://p:1", timeout=10, verify=True, http2=False)
            return a, b

        with patch("httpx.AsyncClient", new=FakeAsyncClient):
            a, b = asyncio.run(get_two())
        assert a is not b
