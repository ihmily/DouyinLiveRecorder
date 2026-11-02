# src/async_http.py 回归用例：客户端缓存/复用、缓存键的循环维度、有界响应读取与核心请求路径。

import asyncio
import gzip
import threading
from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

import src.async_http as async_http
from src import web_config
from src.async_http import (
    _client_cache,
    _client_cache_lock,
    _close_all_clients,
    _get_client,
    async_req,
    close_all_clients_sync,
    get_response_status,
)

# get_response_status 按「本机解析结果」判定直连目标是否落在内网，判定链最终走 web_config._resolve_host_ips
# （该函数即**为用例留的 DNS seam**，见 tests/test_web_config.py）。本文件全部探针用例都必须与该 seam 隔离：
# 否则无外网/无 DNS 的 CI 与开发机上「example.com 可达」类用例随机转红、且把真实解析结果当被测行为断言；默认桩值是公网 IP（= 放行）。
_PUBLIC_IP = "93.184.216.34"


@pytest.fixture(autouse=True)
def _stub_dns_as_public(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(web_config, "_resolve_host_ips", lambda host: [_PUBLIC_IP])


# ────────────────────────────────────────────────────────────
# _get_client: 客户端缓存与复用
# ────────────────────────────────────────────────────────────


class TestGetClient:
    # _get_client: 按 (proxy, verify, http2, 事件循环) 维度复用 AsyncClient（循环维度见下方缓存键用例）。

    @pytest.mark.asyncio
    async def test_creates_new_client(self) -> None:
        # 首次调用创建新 AsyncClient 并缓存：守住「首次填充」不变量，避免每次请求重建连接池（复用实测省约 15.9ms/次）。
        _client_cache.clear()
        try:
            client = await _get_client(None, 10, True, False)
            assert isinstance(client, httpx.AsyncClient)
            assert not client.is_closed
            assert len(_client_cache) == 1
        finally:
            await _close_all_clients()

    @pytest.mark.asyncio
    async def test_reuses_cached_client(self) -> None:
        # 相同参数复用同一 client 实例。
        _client_cache.clear()
        try:
            c1 = await _get_client(None, 10, True, False)
            c2 = await _get_client(None, 20, True, False)  # timeout 不同但 key 不含 timeout
            assert c1 is c2
        finally:
            await _close_all_clients()

    @pytest.mark.asyncio
    async def test_different_proxy_creates_different_client(self) -> None:
        # 不同 proxy 创建不同 client：proxy 是缓存 key 的一维，换代理须隔离独立连接（cookie/鉴权不串房间）。
        _client_cache.clear()
        try:
            c1 = await _get_client(None, 10, True, False)
            c2 = await _get_client("http://proxy:8080", 10, True, False)
            assert c1 is not c2
            assert len(_client_cache) == 2
        finally:
            await _close_all_clients()

    @pytest.mark.asyncio
    async def test_closed_client_replaced(self) -> None:
        # 缓存的 client 已关闭时必须重建，否则后续请求在死连接上挂死、拖垮整轮。
        _client_cache.clear()
        try:
            c1 = await _get_client(None, 10, True, False)
            await c1.aclose()
            assert c1.is_closed
            c2 = await _get_client(None, 10, True, False)
            assert c2 is not c1
            assert not c2.is_closed
        finally:
            await _close_all_clients()


class TestClientCacheLock:
    # _client_cache 由 threading 锁保护（临界区无 await）。[历史注] 曾用「模块级单槽 asyncio.Lock 随循环
    # 重建」：线程 A 会拿到线程 B 循环绑定的锁并 await，触发 'bound to a different event loop'。

    def test_cache_lock_is_reentrant_threading_lock(self) -> None:
        # 锁必须是**可重入**的 threading.RLock（既非 asyncio.Lock 也非普通 threading.Lock）：main.py 的
        # safe_exit（SIGINT/SIGTERM，跑在主线程）会调 close_all_clients_sync() 取同一把锁，而主线程自身
        # 可能正持它跑 _get_client 的同步临界区（warmup / 启动期探测的 asyncio.run）；非重入锁下信号恰好
        # 落在临界区内即同线程自死锁，表现为「Ctrl+C 后既不退出也不报错」。
        assert isinstance(_client_cache_lock, type(threading.RLock()))
        assert not isinstance(_client_cache_lock, type(threading.Lock()))

    def test_cache_lock_is_reentrant_in_practice(self) -> None:
        # 行为级守卫（只看能否重入，不看类型）：外层持有时内层非阻塞 acquire 必须成功，换成 threading.Lock
        # 即返回 False → 用例红且**不会挂死**（刻意 blocking=False，防锁被改回非重入时整个 pytest 卡在这里）。
        with _client_cache_lock:
            assert _client_cache_lock.acquire(blocking=False) is True
            _client_cache_lock.release()

    def test_concurrent_get_client_across_loops_no_error(self) -> None:
        errors: list[Exception] = []

        def run() -> None:
            try:
                client = asyncio.run(_get_client(None, 10, True, False))
                assert client is not None
            except Exception as e:  # pragma: no cover - 仅收集异常
                errors.append(e)

        # 8 个线程各跑独立事件循环（asyncio.run 创建并绑定各自 loop），刻意制造循环多样性以复现「模块级单槽
        # 锁跨循环」竞态；8 与 15s 仅为压测规模/收尾余量，非精确不变量；errors == [] 即无跨循环/跨线程异常。
        threads = [threading.Thread(target=run) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=15)
        assert errors == []
        # join 带超时**返回**不代表线程已退出：挂死形态下 errors 仍空、用例假绿（与 tests/test_async_http_lock.py
        # 同口径）。必须逐线程断言 is_alive 为 False，才钉住「8 线程全部跑完」。
        for t in threads:
            assert not t.is_alive(), "join 超时后线程仍存活：被测逻辑挂死，不得判绿"
        with _client_cache_lock:
            _client_cache.clear()


# ────────────────────────────────────────────────────────────
# 缓存键的事件循环维度（不同循环不得互相逐出存活客户端）
# ────────────────────────────────────────────────────────────


class TestClientCacheLoopDimension:
    # 每房间一线程、每轮一个 asyncio.run() 循环：不同循环必须各自持有条目。

    def test_foreign_loop_does_not_evict_live_client(self) -> None:
        # 现状锁：两个循环各得一支客户端，且 A 的条目在 B 取完之后仍在缓存里。
        # [历史注] 旧 key 不含循环 → 循环 B 会把循环 A **正在使用**的条目 pop 掉自建。
        _client_cache.clear()
        loop_a = asyncio.new_event_loop()
        loop_b = asyncio.new_event_loop()
        client_a: httpx.AsyncClient | None = None
        client_b: httpx.AsyncClient | None = None
        try:
            client_a = loop_a.run_until_complete(_get_client(None, 10, True, False))
            client_b = loop_b.run_until_complete(_get_client(None, 10, True, False))
            assert client_a is not client_b
            entries_a = [(k, v) for k, v in _client_cache.items() if k[3] is loop_a]
            assert len(entries_a) == 1
            assert entries_a[0][1][0] is client_a
            assert not client_a.is_closed
            # 同一循环内重复获取必须复用同一实例（每请求重做 TCP+TLS 的形态已消失）
            again = loop_a.run_until_complete(_get_client(None, 10, True, False))
            assert again is client_a
        finally:
            with _client_cache_lock:
                _client_cache.clear()
            if client_a is not None:
                loop_a.run_until_complete(client_a.aclose())
            if client_b is not None:
                loop_b.run_until_complete(client_b.aclose())
            loop_a.close()
            loop_b.close()

    def test_room_threads_each_keep_their_own_entry(self) -> None:
        # 多线程形态（贴近生产：每房间一个线程 + 各自独立的循环）并发取同一 key：
        # 每个线程拿到的客户端互不相同，且全部仍留在缓存里（无人被别的房间逐出）。
        _client_cache.clear()
        n_threads = 4
        started = threading.Barrier(n_threads + 1)
        keep_alive = threading.Event()
        seen: list[tuple[httpx.AsyncClient, asyncio.AbstractEventLoop]] = []
        seen_lock = threading.Lock()
        errors: list[BaseException] = []

        def worker() -> None:
            loop = asyncio.new_event_loop()
            try:
                client = loop.run_until_complete(_get_client(None, 10, True, False))
                with seen_lock:
                    seen.append((client, loop))
                _ = started.wait(timeout=15)
                # 循环保持存活（不 close）直到主线程断言完毕——复现「房间仍在录制」
                _ = keep_alive.wait(timeout=15)
            except BaseException as e:  # pragma: no cover
                errors.append(e)
                _ = started.wait(timeout=15)
            finally:
                asyncio.set_event_loop(None)
                loop.close()

        threads = [threading.Thread(target=worker) for _ in range(n_threads)]
        for t in threads:
            t.start()
        try:
            _ = started.wait(timeout=15)
            assert errors == []
            assert len(seen) == n_threads
            assert len({id(c) for c, _ in seen}) == n_threads, "不同房间被分配了同一支客户端"
            with _client_cache_lock:
                # 值是三元 (client, loop, owner_thread)：owner 只在 _close_all_clients 里起作用（atexit/信号
                # 钩子只能安全关闭本线程建的那份连接池）。本条只核对「存活客户端仍在缓存里」，owner 不参与
                # 判定，但解包形状必须与 src.async_http._CacheValue 同步（按二元解包会直接 ValueError）。
                cached_clients = {id(client) for client, _loop, _owner in _client_cache.values()}
            for client, _loop in seen:
                assert id(client) in cached_clients, "存活客户端被其它循环逐出（MID-21 回归）"
                assert not client.is_closed
        finally:
            keep_alive.set()
            for t in threads:
                t.join(timeout=20)
            with _client_cache_lock:
                _client_cache.clear()
            # 同 TestClientCacheLock 的 join/is_alive 口径：keep_alive 置位后房间线程理应各自 wait 返回、
            # close 自己的循环并结束；这条 is_alive 是唯一能看出「线程挂死」的地方（缺失即假绿 + 非守护线程拖住退出）。
            alive = [t.name for t in threads if t.is_alive()]
            assert not alive, f"keep_alive 置位后房间线程仍未退出（疑似挂死）：{alive}"

    def test_sweep_drops_references_but_never_closes_cross_loop(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # 超阈值触发清扫时：已关闭循环的条目只丢引用，**绝不**为其创建 aclose 协程
        # （跨循环不关闭是硬约束，本条是它的静态守卫）。
        from src.async_http import _CACHE_SWEEP_THRESHOLD

        _client_cache.clear()
        dead_clients = []
        for _ in range(_CACHE_SWEEP_THRESHOLD + 1):
            loop = asyncio.new_event_loop()
            mock = MagicMock(spec=httpx.AsyncClient)
            mock.is_closed = False
            mock.aclose = AsyncMock()
            _client_cache[("dead", True, False, loop)] = (mock, loop, threading.current_thread())
            dead_clients.append(mock)
            loop.close()
        current = asyncio.new_event_loop()
        new_client: httpx.AsyncClient | None = None
        try:
            new_client = current.run_until_complete(_get_client(None, 10, True, False))
        finally:
            with _client_cache_lock:
                remaining = dict(_client_cache)
                _client_cache.clear()
            if new_client is not None:
                current.run_until_complete(new_client.aclose())
            current.close()
        assert [k for k in remaining if k[0] == "dead"] == [], "已关闭循环的条目未被清扫"
        for mock in dead_clients:
            mock.aclose.assert_not_called()


# ────────────────────────────────────────────────────────────
# 登录 / 取 Cookie 类调用与共享客户端隔离（cookie jar 不跨房间串号）
# ────────────────────────────────────────────────────────────


class TestStatefulCallIsolation:
    # return_cookies=True 的 4 个调用点全是登录/取 token，绝不能复用带持久 jar 的共享客户端。

    @pytest.mark.asyncio
    async def test_stateful_request_does_not_touch_shared_client(self) -> None:
        _client_cache.clear()
        shared = MagicMock(spec=httpx.AsyncClient)
        shared.is_closed = False
        shared.cookies = MagicMock()
        own = AsyncMock()
        resp = MagicMock()
        resp.cookies.items.return_value = [("sid", "B-account")]
        own.get.return_value = resp
        released: list[object] = []

        async def _fake_release(client: object) -> None:
            released.append(client)

        get_calls: list[tuple[object, ...]] = []
        real_get_client = async_http._get_client

        async def _spy_get_client(*args: object, **kwargs: object) -> httpx.AsyncClient:
            get_calls.append(args)
            return await real_get_client(*args, **kwargs)  # type: ignore[arg-type]

        with (
            patch("src.async_http._get_client", side_effect=_spy_get_client),
            patch("src.async_http._build_client", return_value=own),
            patch("src.async_http._release_client", side_effect=_fake_release),
            patch("src.async_http.utils.handle_proxy_addr", return_value=None),
        ):
            _client_cache[("", True, False, asyncio.get_running_loop())] = (
                shared,
                asyncio.get_running_loop(),
                threading.current_thread(),
            )
            result = await async_req("https://example.com", return_cookies=True)

        assert result == {"sid": "B-account"}
        assert get_calls == [], "登录/取 Cookie 调用仍走了缓存客户端（cookie jar 会跨账号累积）"
        assert released == [own], "独占客户端未被关闭，连接池泄漏"

    @pytest.mark.asyncio
    async def test_plain_request_still_uses_shared_client(self) -> None:
        # 反向断言：普通文本请求仍复用缓存客户端（否则缓存复用的收益被误伤成每次自建）
        _client_cache.clear()
        loop = asyncio.get_running_loop()
        shared = AsyncMock()
        shared.is_closed = False
        resp = MagicMock()
        resp.text = "body"
        shared.get.return_value = resp
        _client_cache[("", True, True, loop)] = (shared, loop, threading.current_thread())
        with (
            patch("src.async_http.utils.handle_proxy_addr", return_value=None),
            patch("src.async_http._build_client") as build_spy,
        ):
            result = await async_req("https://example.com")
        assert result == "body"
        build_spy.assert_not_called()
        shared.get.assert_called_once()


# ────────────────────────────────────────────────────────────
# 探针按平台取拉流侧 SSL 策略
# ────────────────────────────────────────────────────────────


class TestGetResponseStatusSslPolicy:
    # get_response_status 的入参是**流地址**，verify 必须与 ffmpeg / stream_select 同源。

    @pytest.mark.asyncio
    async def test_platform_override_reaches_the_probe(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from src import http_config

        monkeypatch.setattr(http_config, "stream_ssl_verify", True)
        monkeypatch.setattr(http_config, "ssl_verify_platform_overrides", {"虎牙直播": False})
        mock_client = AsyncMock()
        head = MagicMock()
        head.status_code = 200
        mock_client.head.return_value = head
        with patch("src.async_http._get_client", new_callable=AsyncMock, return_value=mock_client) as get_spy:
            assert await get_response_status("https://example.com/a.m3u8", platform="虎牙直播") is True
        # 第 3 个位置参数即 verify：命中「禁用SSL证书验证的平台」→ False（与 ffmpeg -tls_verify 一致）
        assert get_spy.await_args is not None
        assert get_spy.await_args.args[2] is False

    @pytest.mark.asyncio
    async def test_platform_without_override_follows_stream_policy(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from src import http_config

        monkeypatch.setattr(http_config, "stream_ssl_verify", True)
        monkeypatch.setattr(http_config, "ssl_verify_platform_overrides", {})
        mock_client = AsyncMock()
        head = MagicMock()
        head.status_code = 200
        mock_client.head.return_value = head
        with patch("src.async_http._get_client", new_callable=AsyncMock, return_value=mock_client) as get_spy:
            assert await get_response_status("https://example.com/a.m3u8", platform="抖音直播") is True
        assert get_spy.await_args is not None
        assert get_spy.await_args.args[2] is True

    @pytest.mark.asyncio
    async def test_https_recording_mode_exempts_stream_side(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # 「是否启用https录制」开启 → 拉流侧全局豁免校验（stream_ssl_verify=False）：探针不得再按
        # 控制面的 True 去校验证书，否则校验假红、画质被误降
        from src import http_config

        monkeypatch.setattr(http_config, "stream_ssl_verify", False)
        monkeypatch.setattr(http_config, "ssl_verify", True)
        monkeypatch.setattr(http_config, "ssl_verify_platform_overrides", {})
        mock_client = AsyncMock()
        head = MagicMock()
        head.status_code = 200
        mock_client.head.return_value = head
        with patch("src.async_http._get_client", new_callable=AsyncMock, return_value=mock_client) as get_spy:
            assert await get_response_status("https://example.com/a.m3u8", platform="虎牙直播") is True
        assert get_spy.await_args is not None
        assert get_spy.await_args.args[2] is False

    @pytest.mark.asyncio
    async def test_explicit_verify_still_wins(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # verify 显式传值时单次覆盖语义保持不变（平台策略只填默认值）
        from src import http_config

        monkeypatch.setattr(http_config, "stream_ssl_verify", False)
        mock_client = AsyncMock()
        head = MagicMock()
        head.status_code = 200
        mock_client.head.return_value = head
        with patch("src.async_http._get_client", new_callable=AsyncMock, return_value=mock_client) as get_spy:
            assert await get_response_status("https://example.com/a.m3u8", verify=True, platform="虎牙直播") is True
        assert get_spy.await_args is not None
        assert get_spy.await_args.args[2] is True

    @pytest.mark.asyncio
    async def test_legacy_proxy_addr_keyword_still_accepted(self) -> None:
        # 迁移期兼容：src/stream.py 现有调用用 proxy_addr= 关键字，不得因签名改造而炸
        mock_client = AsyncMock()
        head = MagicMock()
        head.status_code = 200
        mock_client.head.return_value = head
        with (
            patch("src.async_http._get_client", new_callable=AsyncMock, return_value=mock_client),
            patch("src.async_http.utils.handle_proxy_addr", return_value="http://127.0.0.1:7890") as hp,
        ):
            assert await get_response_status(url="https://example.com/a.m3u8", proxy_addr="127.0.0.1:7890") is True
        # handle_proxy_addr 是同步调用 → 用 call_args（await_args 只适用于被 await 的替身）
        assert hp.call_args is not None
        assert hp.call_args.args[0] == "127.0.0.1:7890"

    @pytest.mark.asyncio
    async def test_proxy_keyword_reaches_client(self) -> None:
        mock_client = AsyncMock()
        head = MagicMock()
        head.status_code = 200
        mock_client.head.return_value = head
        with (
            patch("src.async_http._get_client", new_callable=AsyncMock, return_value=mock_client) as get_spy,
            patch("src.async_http.utils.handle_proxy_addr", return_value="http://127.0.0.1:7890"),
        ):
            assert await get_response_status("https://example.com", proxy="http://127.0.0.1:7890") is True
        assert get_spy.await_args is not None
        assert get_spy.await_args.args[0] == "http://127.0.0.1:7890"


# ────────────────────────────────────────────────────────────
# _close_all_clients / close_all_clients_sync
# ────────────────────────────────────────────────────────────


class TestCloseAllClients:
    # _close_all_clients: 释放所有缓存客户端。

    @pytest.mark.asyncio
    async def test_close_all(self) -> None:
        # 关闭所有缓存的 client，缓存清空。
        _client_cache.clear()
        c1 = await _get_client(None, 10, True, False)
        c2 = await _get_client("http://proxy:8080", 10, True, False)
        assert not c1.is_closed
        assert not c2.is_closed

        await _close_all_clients()
        assert c1.is_closed
        assert c2.is_closed
        assert len(_client_cache) == 0

    @pytest.mark.asyncio
    async def test_close_empty_cache(self) -> None:
        # 空缓存关闭路径须幂等，防无房间时 shutdown 崩溃。
        _client_cache.clear()
        await _close_all_clients()
        assert len(_client_cache) == 0


class TestCloseAllClientsSync:
    # close_all_clients_sync: 同步安全清理。

    def test_empty_cache_no_error(self) -> None:
        # 同步清理空缓存须安全返回（不抛异常），供信号处理/atexit 兜底调用。
        _client_cache.clear()
        close_all_clients_sync()  # 不应抛异常

    def test_clears_cache_when_populated(self) -> None:
        # 非空缓存不论是否在 loop 内都应清空，避免旧 client 泄漏被误复用。
        _client_cache.clear()
        mock_client = MagicMock(spec=httpx.AsyncClient)
        mock_client.is_closed = False
        # 缓存键已含事件循环维度（4 元组），替身键须同步
        _client_cache[("test", True, False, MagicMock(spec=asyncio.AbstractEventLoop))] = (
            mock_client,
            MagicMock(),
            threading.current_thread(),
        )
        assert len(_client_cache) == 1
        close_all_clients_sync()
        assert len(_client_cache) == 0


# ────────────────────────────────────────────────────────────
# async_req: 核心请求函数
# ────────────────────────────────────────────────────────────


class TestAsyncReq:
    # async_req：GET/POST 请求 + 异常回退。
    # Mock 策略：每个用例都 patch 掉 _get_client（避免构造真实 httpx.AsyncClient / 触网）与 utils.handle_proxy_addr
    # （隔离代理地址解析，避免读真实配置或做 DNS），从而只验证 async_req 自身的请求分派与异常回退分支。

    @pytest.mark.asyncio
    async def test_get_request_returns_text(self) -> None:
        # GET 是主路径：锁住分派与响应体透传，确保异常分支不吞文本。
        mock_response = MagicMock()
        mock_response.text = "response body"
        mock_response.url = "https://example.com"
        mock_response.cookies = MagicMock()
        mock_response.cookies.items.return_value = []

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response

        with (
            patch("src.async_http._get_client", new_callable=AsyncMock, return_value=mock_client),
            patch("src.async_http.utils.handle_proxy_addr", return_value=None),
        ):
            result = await async_req("https://example.com")

        assert result == "response body"
        mock_client.get.assert_called_once()

    @pytest.mark.asyncio
    async def test_post_with_dict_data(self) -> None:
        # POST dict 数据使用 data= 参数。
        mock_response = MagicMock()
        mock_response.text = '{"ok": true}'

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response

        with (
            patch("src.async_http._get_client", new_callable=AsyncMock, return_value=mock_client),
            patch("src.async_http.utils.handle_proxy_addr", return_value=None),
        ):
            result = await async_req("https://api.example.com", data={"key": "value"})

        assert result == '{"ok": true}'
        # 必须校验实际传入的关键字：只断言「被调用过」时，data=/json=/content=
        # 三者写反的回归测不出来（本用例注释声称的就是「用 data= 传 dict」）。
        mock_client.post.assert_called_once()
        assert mock_client.post.call_args.kwargs["data"] == {"key": "value"}
        assert mock_client.post.call_args.kwargs["json"] is None

    @pytest.mark.asyncio
    async def test_post_with_string_data(self) -> None:
        # POST 字符串数据使用 content= 参数。
        mock_response = MagicMock()
        mock_response.text = "ok"

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response

        with (
            patch("src.async_http._get_client", new_callable=AsyncMock, return_value=mock_client),
            patch("src.async_http.utils.handle_proxy_addr", return_value=None),
        ):
            result = await async_req("https://api.example.com", data="raw body")

        assert result == "ok"
        # 字符串体必须走 content= 而非 data=（httpx 语义不同：data= 会被当作表单编码）
        mock_client.post.assert_called_once()
        assert mock_client.post.call_args.kwargs["content"] == "raw body"

    @pytest.mark.asyncio
    async def test_post_with_bytes_data(self) -> None:
        # POST bytes 数据使用 content= 参数。
        mock_response = MagicMock()
        mock_response.text = "ok"

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response

        with (
            patch("src.async_http._get_client", new_callable=AsyncMock, return_value=mock_client),
            patch("src.async_http.utils.handle_proxy_addr", return_value=None),
        ):
            result = await async_req("https://api.example.com", data=b"binary data")

        assert result == "ok"

    @pytest.mark.asyncio
    async def test_redirect_url_returns_url(self) -> None:
        # redirect_url 模式须返回最终 URL（而非文本），供上层跟随跳转拿真地址。
        mock_response = MagicMock()
        mock_response.url = "https://redirected.example.com/final"

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response

        with (
            patch("src.async_http._get_client", new_callable=AsyncMock, return_value=mock_client),
            patch("src.async_http.utils.handle_proxy_addr", return_value=None),
        ):
            result = await async_req("https://example.com", redirect_url=True)

        assert result == "https://redirected.example.com/final"

    @pytest.mark.asyncio
    async def test_return_cookies_returns_cookies(self) -> None:
        # return_cookies 须把 cookie jar 转 dict，供登录态向下游透传。
        # 登录/取 Cookie 调用不走缓存客户端，故此处 patch _build_client 而非 _get_client（见 TestStatefulCallIsolation）。
        mock_response = MagicMock()
        mock_response.text = "ok"
        mock_cookies = MagicMock()
        mock_cookies.items.return_value = [("session", "abc123"), ("token", "xyz")]
        mock_response.cookies = mock_cookies

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response

        with (
            patch("src.async_http._build_client", return_value=mock_client),
            patch("src.async_http.utils.handle_proxy_addr", return_value=None),
        ):
            result = await async_req("https://example.com", return_cookies=True)

        assert result == {"session": "abc123", "token": "xyz"}
        mock_client.get.assert_called_once()

    @pytest.mark.asyncio
    async def test_return_cookies_with_include_cookies(self) -> None:
        # return_cookies=True + include_cookies=True 返回 (text, cookies) 元组。
        mock_response = MagicMock()
        mock_response.text = "page content"
        mock_cookies = MagicMock()
        mock_cookies.items.return_value = [("sid", "val")]
        mock_response.cookies = mock_cookies

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response

        with (
            patch("src.async_http._build_client", return_value=mock_client),
            patch("src.async_http.utils.handle_proxy_addr", return_value=None),
        ):
            result = await async_req("https://example.com", return_cookies=True, include_cookies=True)

        assert result == ("page content", {"sid": "val"})

    @pytest.mark.asyncio
    async def test_exception_returns_empty_string(self) -> None:
        # 请求异常时返回空字符串。
        mock_client = AsyncMock()
        mock_client.get.side_effect = httpx.ConnectError("connection refused")

        with (
            patch("src.async_http._get_client", new_callable=AsyncMock, return_value=mock_client),
            patch("src.async_http.utils.handle_proxy_addr", return_value=None),
        ):
            result = await async_req("https://example.com")

        assert result == ""

    @pytest.mark.asyncio
    async def test_exception_redirect_returns_empty_string(self) -> None:
        # redirect 模式异常同样降级空串，与文本模式失败语义一致（统一兜底）。
        mock_client = AsyncMock()
        mock_client.get.side_effect = httpx.TimeoutException("timeout")

        with (
            patch("src.async_http._get_client", new_callable=AsyncMock, return_value=mock_client),
            patch("src.async_http.utils.handle_proxy_addr", return_value=None),
        ):
            result = await async_req("https://example.com", redirect_url=True)

        assert result == ""

    @pytest.mark.asyncio
    async def test_exception_cookies_returns_empty_dict(self) -> None:
        # return_cookies 模式异常返回空字典；该分支客户端由 _build_client 独占创建，替身须打在同一个口上（否则触网）。
        mock_client = AsyncMock()
        mock_client.get.side_effect = Exception("network error")

        with (
            patch("src.async_http._build_client", return_value=mock_client),
            patch("src.async_http.utils.handle_proxy_addr", return_value=None),
        ):
            result = await async_req("https://example.com", return_cookies=True)

        assert result == {}

    @pytest.mark.asyncio
    async def test_verify_defaults_to_config(self) -> None:
        # verify=None 时使用 config.ssl_verify 默认值。
        mock_response = MagicMock()
        mock_response.text = "ok"

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response

        with (
            patch("src.async_http._get_client", new_callable=AsyncMock, return_value=mock_client) as mock_get,
            patch("src.async_http.utils.handle_proxy_addr", return_value=None),
            patch("src.async_http.config.ssl_verify", False),
        ):
            await async_req("https://example.com")
            # 调用参数 (proxy=None, timeout=20, verify=False, http2=True)：20 是 async_req 未显式传入时的兜底超时，
            # False 来自 patch 的 config.ssl_verify，True 为 http2 默认开关；本用例守「verify 缺省回落配置」。
            mock_get.assert_called_once_with(None, 20, False, True)


# ────────────────────────────────────────────────────────────
# get_response_status: URL 可达性检测
# ────────────────────────────────────────────────────────────


class TestGetResponseStatus:
    # get_response_status: URL 可达性检测。

    @pytest.mark.asyncio
    async def test_status_200_returns_true(self) -> None:
        # HEAD 200 即可达，是 URL 校验主路径（不浪费一次 GET）。
        mock_response = MagicMock()
        mock_response.status_code = 200

        mock_client = AsyncMock()
        mock_client.head.return_value = mock_response

        with (
            patch("src.async_http._get_client", new_callable=AsyncMock, return_value=mock_client),
            patch("src.async_http.utils.handle_proxy_addr", return_value=None),
        ):
            result = await get_response_status("https://example.com/stream.m3u8")

        assert result is True

    @pytest.mark.asyncio
    async def test_status_404_returns_false(self) -> None:
        # HEAD 404 即不可达：快速定罪，不误放死链。
        mock_response = MagicMock()
        mock_response.status_code = 404

        mock_client = AsyncMock()
        mock_client.head.return_value = mock_response

        with (
            patch("src.async_http._get_client", new_callable=AsyncMock, return_value=mock_client),
            patch("src.async_http.utils.handle_proxy_addr", return_value=None),
        ):
            result = await get_response_status("https://example.com/notfound")

        assert result is False

    @pytest.mark.asyncio
    async def test_m3u8_head_405_fallback_to_get(self) -> None:
        # m3u8 URL HEAD 405 → 降级 Range GET 探测：复刻斗鱼 hw CDN 禁用 HEAD 的实测形态，
        # 须走 Range GET 才能拿到真地址。
        head_response = MagicMock()
        head_response.status_code = 405

        get_response = MagicMock()
        get_response.status_code = 206

        mock_client = AsyncMock()
        mock_client.head.return_value = head_response
        mock_client.get.return_value = get_response

        with (
            patch("src.async_http._get_client", new_callable=AsyncMock, return_value=mock_client),
            patch("src.async_http.utils.handle_proxy_addr", return_value=None),
        ):
            result = await get_response_status("https://cdn.example.com/live.m3u8")

        assert result is True
        # 只 assert_called_once() 锁不住本用例要保的契约：降级探针必须带 `Range: bytes=0-0`，删掉该头会退化成
        # 整文件下载（对 CDN 是流量事故）而旧断言照样绿，故显式断言请求参数而不只数调用次数。
        mock_client.get.assert_called_once()
        probe_kwargs = mock_client.get.call_args.kwargs
        assert (
            probe_kwargs.get("headers", {}).get("Range") == "bytes=0-0"
        ), f"降级探针必须带 Range: bytes=0-0，实际 headers={probe_kwargs.get('headers')!r}"

    @pytest.mark.asyncio
    async def test_m3u8_head_403_get_also_fails(self) -> None:
        # HEAD 403 且 Range GET 仍失败 → 真不可达，防误判可用而放行死链。
        head_response = MagicMock()
        head_response.status_code = 403

        get_response = MagicMock()
        get_response.status_code = 403

        mock_client = AsyncMock()
        mock_client.head.return_value = head_response
        mock_client.get.return_value = get_response

        with (
            patch("src.async_http._get_client", new_callable=AsyncMock, return_value=mock_client),
            patch("src.async_http.utils.handle_proxy_addr", return_value=None),
        ):
            result = await get_response_status("https://cdn.example.com/live.m3u8")

        assert result is False

    @pytest.mark.asyncio
    async def test_exception_returns_false(self) -> None:
        # 请求异常 → False（判定为不可达）。
        mock_client = AsyncMock()
        mock_client.head.side_effect = httpx.ConnectError("refused")

        with (
            patch("src.async_http._get_client", new_callable=AsyncMock, return_value=mock_client),
            patch("src.async_http.utils.handle_proxy_addr", return_value=None),
        ):
            result = await get_response_status("https://example.com")

        assert result is False

    @pytest.mark.asyncio
    async def test_non_m3u8_403_returns_false_directly(self) -> None:
        # 非 m3u8 URL 返回 403 → 直接 False，不做 Range GET 探测。
        mock_response = MagicMock()
        mock_response.status_code = 403

        mock_client = AsyncMock()
        mock_client.head.return_value = mock_response

        with (
            patch("src.async_http._get_client", new_callable=AsyncMock, return_value=mock_client),
            patch("src.async_http.utils.handle_proxy_addr", return_value=None),
        ):
            result = await get_response_status("https://example.com/api")

        assert result is False
        mock_client.get.assert_not_called()


# ────────────────────────────────────────────────────────────
# async 出站响应体读取上限（压缩炸弹 / 超大响应防线）
# ────────────────────────────────────────────────────────────


class _ChunkedStream(httpx.AsyncByteStream):
    # 替身传输层：按块吐原始字节，模拟「响应体尚未物化」的真流形态（httpx 的 aiter_raw 迭代 response.stream）。
    # 刻意不用预装载 Response——MockTransport 默认回的 Response 构造期就带 _content，钩子会按「已装载」直接放行，
    # 上限逻辑根本不执行（假绿面）。必须继承 AsyncByteStream：AsyncClient._send_single_request 对 stream 有
    # isinstance 断言，异步生成器形态的 __aiter__ 与 httpx 基类签名同构。
    def __init__(self, chunks: list[bytes]) -> None:
        self._chunks = chunks
        self.yielded = 0

    async def __aiter__(self) -> AsyncIterator[bytes]:
        for chunk in self._chunks:
            self.yielded += 1
            yield chunk


def _stream_response(
    chunks: list[bytes],
    *,
    headers: dict[str, str] | None = None,
    status_code: int = 200,
    url: str = "https://example.com/api",
) -> tuple[httpx.Response, _ChunkedStream]:
    stream = _ChunkedStream(chunks)
    response = httpx.Response(status_code, headers=headers, stream=stream, request=httpx.Request("GET", url))
    return response, stream


class TestBoundedResponseRead:
    # _bounded_response_read：读上限、回填语义、超限失败形态（出站上限的核心不变量）。

    @pytest.mark.asyncio
    async def test_plain_body_over_cap_raises_value_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # 未压缩：decoded == raw，按 _MAX_RESPONSE_BYTES 定罪；超限必须是 ValueError（落 async_req
        # 既有通用 except 的空值契约），不是截断返回。
        monkeypatch.setattr(async_http, "_MAX_RESPONSE_BYTES", 64)
        response, stream = _stream_response([b"a" * 40, b"a" * 40])
        with pytest.raises(ValueError, match="响应体"):
            await async_http._bounded_response_read(response)
        # 超限判定必须在「读入超过上限的那一块」当场生效：第三块根本不该被拉取
        assert stream.yielded == 2

    @pytest.mark.asyncio
    async def test_within_cap_loads_body_for_public_readers(self) -> None:
        # 未超限：物化 + 回填后 .content/.text 走公开读径且与既有契约一致（async_req 的
        # response.text、get_response_status 的 status 判定都不许感知到「半途流」）。
        response, _stream = _stream_response([b'{"a": 1}', b" tail"])
        await async_http._bounded_response_read(response)
        assert response.content == b'{"a": 1} tail'
        assert response.text == '{"a": 1} tail'

    @pytest.mark.asyncio
    async def test_gzip_bomb_over_decompressed_cap_rejected(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # 解压炸弹（本防线的攻击主体）：压缩体很小、解压产出超限——只限压缩体挡不住，必须按
        # _MAX_DECOMPRESSED_BYTES 在解码产出侧当场拒绝。
        monkeypatch.setattr(async_http, "_MAX_DECOMPRESSED_BYTES", 64)
        compressed = gzip.compress(b"a" * 4096)
        assert len(compressed) < 64, "构造失效：压缩体本身已超上限，会走成压缩侧定罪"
        response, _stream = _stream_response([compressed], headers={"content-encoding": "gzip"})
        with pytest.raises(ValueError, match="解压后响应体"):
            await async_http._bounded_response_read(response)

    @pytest.mark.asyncio
    async def test_gzip_body_within_cap_is_decoded_by_httpx_pipeline(self) -> None:
        # 反向锁（防「上限误杀正常 gzip 大 JSON」与「回填绕过解码管线导致 text 是密文」）：
        # 未超限的 gzip 响应必须经 httpx 自带解码器还原成明文，并由 .text 直读。
        compressed = gzip.compress(b"hello gzip")
        response, _stream = _stream_response([compressed], headers={"content-encoding": "gzip"})
        await async_http._bounded_response_read(response)
        assert response.text == "hello gzip"

    @pytest.mark.asyncio
    async def test_redirect_hop_body_is_bounded_like_any_other_hop(self) -> None:
        # 现状锁：3xx 跳与其它跳同一条有界读取——必须真的读，且读到上限后立刻判失败。
        # [历史注] 旧契约「3xx 中间跳一律不读」（stream.yielded == 0）已证伪：钩子返回后、跟随重定向前，httpx
        # 仍会对该跳执行一次**无上限且自动解压**的 aread()，「302 + 超大 gzip 正文」因此绕过上限（实测峰值 405MB）。
        response, stream = _stream_response(
            [b"redirect body"], status_code=302, headers={"location": "https://next.example.com/x"}
        )
        await async_http._bounded_response_read(response)
        assert stream.yielded == 1
        assert response.content == b"redirect body"

    @pytest.mark.asyncio
    async def test_redirect_hop_body_over_cap_is_rejected(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # 攻击形态：超大 3xx 正文不得因为「这是中间跳」而被跳过上限检查
        monkeypatch.setattr(async_http, "_MAX_RESPONSE_BYTES", 8)
        response, _stream = _stream_response(
            [b"x" * 64], status_code=302, headers={"location": "https://next.example.com/x"}
        )
        with pytest.raises(ValueError, match="响应体"):
            await async_http._bounded_response_read(response)

    @pytest.mark.asyncio
    async def test_preloaded_response_is_left_untouched(self) -> None:
        # 构造期已装载（content= 形态 / 替身客户端）的响应没有流可限：原样放行，
        # 这条早退让既有按 MagicMock 响应打桩的用例不被波及。
        response = httpx.Response(200, content=b"preloaded", request=httpx.Request("GET", "https://example.com"))
        await async_http._bounded_response_read(response)
        assert response.content == b"preloaded"

    @pytest.mark.asyncio
    async def test_caps_match_the_sync_side_baseline(self) -> None:
        # 「与 sync_http 同一口径」的同值锁：两个上限各存一份（不 import），任一侧抬数、另一侧不同批抬即红
        # （两份事实源漂移正是本仓反复点名的缺口形态，注释承诺必须有机检兜底）。
        from src import sync_http

        assert async_http._MAX_RESPONSE_BYTES == sync_http._MAX_RESPONSE_BYTES
        assert async_http._MAX_DECOMPRESSED_BYTES == sync_http._MAX_DECOMPRESSED_BYTES


class TestAsyncReqCapEndToEnd:
    # 全链路锁：上限必须经**真实** _build_client 挂的 response 钩子生效在 async_req 主路径上。
    # 本类只把最底层 transport 换成 MockTransport（wp_b_netguard 同法），钩子与被测读取链全走
    # 真实代码；把 _get_client 整个打桩就验不到「钩子真的接线」这半条不变量。

    @pytest.mark.asyncio
    async def test_async_req_oversized_stream_body_fails_with_empty_contract(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(async_http, "_MAX_RESPONSE_BYTES", 64)
        client = async_http._build_client(None, 10, True, False)
        client._mounts = {}  # 与 wp_b_netguard 同法：让每一跳都落到 MockTransport 上
        client._transport = httpx.MockTransport(
            lambda request: httpx.Response(200, stream=_ChunkedStream([b"a" * 40, b"a" * 40]))
        )

        async def _provide(*args: Any, **kwargs: Any) -> httpx.AsyncClient:
            return client

        monkeypatch.setattr(async_http, "_get_client", _provide)
        monkeypatch.setattr(async_http.utils, "handle_proxy_addr", lambda x: None)
        try:
            # 超限 = 既有失败语义（空串），不得穿透 ValueError、不得返回半截响应
            assert await async_req("https://example.com/api") == ""
        finally:
            await client.aclose()

    @pytest.mark.asyncio
    async def test_async_req_normal_body_flows_through_the_hook(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # 反向锁：经钩子物化 + 回填的正常小响应，async_req 的文本契约逐字不变（若回填形态与
        # httpx 的「已装载」判定脱钩，这里会拿到空串/ResponseNotRead）。
        client = async_http._build_client(None, 10, True, False)
        client._mounts = {}
        client._transport = httpx.MockTransport(
            lambda request: httpx.Response(200, stream=_ChunkedStream([b"part1", b"part2"]))
        )

        async def _provide(*args: Any, **kwargs: Any) -> httpx.AsyncClient:
            return client

        monkeypatch.setattr(async_http, "_get_client", _provide)
        monkeypatch.setattr(async_http.utils, "handle_proxy_addr", lambda x: None)
        try:
            assert await async_req("https://example.com/api") == "part1part2"
        finally:
            await client.aclose()

    @pytest.mark.asyncio
    async def test_stateful_login_client_is_capped_too(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # return_cookies=True 走 _build_client 的独占分支：同一支工厂 → 同一道上限；漏了这条
        # 就等于「登录/取 cookie 路径的响应体无人设防」。
        monkeypatch.setattr(async_http, "_MAX_RESPONSE_BYTES", 64)
        monkeypatch.setattr(async_http.utils, "handle_proxy_addr", lambda x: None)
        seen: list[httpx.AsyncClient] = []
        real_build = async_http._build_client

        def _build(proxy_addr: str | None, timeout: int, verify: bool, http2: bool) -> httpx.AsyncClient:
            client = real_build(proxy_addr, timeout, verify, http2)
            client._mounts = {}
            client._transport = httpx.MockTransport(
                lambda request: httpx.Response(200, stream=_ChunkedStream([b"b" * 40, b"b" * 40]))
            )
            seen.append(client)
            return client

        monkeypatch.setattr(async_http, "_build_client", _build)
        # include_cookies=True 的失败契约是 ("", {})：超限必须落回这个形状而不是抛穿
        assert await async_req("https://example.com/login", return_cookies=True, include_cookies=True) == ("", {})
        for client in seen:
            await client.aclose()
