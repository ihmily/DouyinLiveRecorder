# Tests for src/async_http.py module — 客户端管理 + 核心请求路径。

import asyncio
import threading
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from src.async_http import (
    _client_cache,
    _client_cache_lock,
    _close_all_clients,
    _get_client,
    async_req,
    close_all_clients_sync,
    get_response_status,
)

# ────────────────────────────────────────────────────────────
# _get_client: 客户端缓存与复用
# ────────────────────────────────────────────────────────────


class TestGetClient:
    # _get_client: 按 (proxy, verify, http2) 维度复用 AsyncClient。

    @pytest.mark.asyncio
    async def test_creates_new_client(self) -> None:
        # 首次调用创建新 AsyncClient 并缓存。
        # 守护「首次缓存填充」不变量，避免每次请求重建连接池（复用实测省约 15.9ms/次）。
        _client_cache.clear()
        try:
            client = await _get_client(None, 10, True, False)
            assert isinstance(client, httpx.AsyncClient)
            assert not client.is_closed
            # 缓存中应有记录
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
        # 不同 proxy 参数创建不同 client。
        # proxy 是缓存 key 一维，换代理须隔离独立连接（cookie/鉴权不串房间）。
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
        # 缓存的 client 已关闭时创建新的。
        # 已关闭的 client 必须重建，否则后续请求在死连接上挂死、拖垮整轮。
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
    # 批次5重构：_client_cache 由普通 threading.Lock 保护（临界区无 await），
    # 避免原「模块级单槽 asyncio.Lock 随循环重建」的跨线程竞态——
    # 线程 A 可能拿到线程 B 循环绑定的锁并 await，触发 'bound to a different event loop'。

    def test_cache_lock_is_threading_lock(self) -> None:
        # 缓存锁必须是普通 threading.Lock 而非模块级单槽 asyncio.Lock；
        # 临界区无 await，避免跨线程/跨循环 await 触发 'bound to a different event loop'。
        assert isinstance(_client_cache_lock, type(threading.Lock()))

    def test_concurrent_get_client_across_loops_no_error(self) -> None:
        # 多线程各用独立事件循环并发获取客户端：不应抛跨循环/跨线程异常
        # 8 线程各跑独立 loop 刻意制造循环多样性，复现原模块级单槽锁跨循环竞态。
        errors: list[Exception] = []

        def run() -> None:
            try:
                client = asyncio.run(_get_client(None, 10, True, False))
                assert client is not None
            except Exception as e:  # pragma: no cover - 仅收集异常
                errors.append(e)

        # 8 个线程各跑独立事件循环（asyncio.run 创建并绑定各自 loop），刻意制造循环多样性
        # 以复现「模块级单槽锁跨循环」竞态；8 与 15s 仅为压测规模/收尾余量，非精确不变量。
        # 断言 errors == []：无跨循环/跨线程异常，验证 threading.Lock 重构化解了原竞态。
        threads = [threading.Thread(target=run) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=15)
        assert errors == []
        with _client_cache_lock:
            _client_cache.clear()


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
        # 空缓存调用不报错。
        # 空缓存关闭路径须幂等，防无房间时 shutdown 崩溃。
        _client_cache.clear()
        await _close_all_clients()
        assert len(_client_cache) == 0


class TestCloseAllClientsSync:
    # close_all_clients_sync: 同步安全清理。

    def test_empty_cache_no_error(self) -> None:
        # 空缓存时直接返回，不报错。
        # 同步清理空缓存须安全返回，供信号处理/atexit 兜底调用。
        _client_cache.clear()
        close_all_clients_sync()  # 不应抛异常

    def test_clears_cache_when_populated(self) -> None:
        # 缓存非空时，调用后缓存被清空（无论是否在事件循环内）。
        # 非空缓存不论是否在 loop 内都应清空，避免旧 client 泄漏被误复用。
        _client_cache.clear()
        mock_client = MagicMock(spec=httpx.AsyncClient)
        mock_client.is_closed = False
        _client_cache[("test", True, False)] = (mock_client, MagicMock())
        assert len(_client_cache) == 1
        close_all_clients_sync()
        assert len(_client_cache) == 0


# ────────────────────────────────────────────────────────────
# async_req: 核心请求函数
# ────────────────────────────────────────────────────────────


class TestAsyncReq:
    # async_req: GET/POST 请求 + 异常回退。
    # Mock 策略：每个用例都 patch 掉 _get_client（避免构造真实 httpx.AsyncClient / 触网）
    # 与 utils.handle_proxy_addr（隔离代理地址解析，避免读真实配置或做 DNS），从而只验证
    # async_req 自身的请求分派与异常回退分支。

    @pytest.mark.asyncio
    async def test_get_request_returns_text(self) -> None:
        # GET 请求返回响应文本。
        # GET 是主路径，锁住分派与响应体透传，确保异常分支不吞文本。
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
        mock_client.post.assert_called_once()

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
        # redirect_url=True 返回重定向后 URL。
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
        # return_cookies=True 返回 cookie 字典。
        # return_cookies 须把 cookie jar 转 dict，供登录态向下游透传。
        mock_response = MagicMock()
        mock_response.text = "ok"
        mock_cookies = MagicMock()
        mock_cookies.items.return_value = [("session", "abc123"), ("token", "xyz")]
        mock_response.cookies = mock_cookies

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response

        with (
            patch("src.async_http._get_client", new_callable=AsyncMock, return_value=mock_client),
            patch("src.async_http.utils.handle_proxy_addr", return_value=None),
        ):
            result = await async_req("https://example.com", return_cookies=True)

        assert result == {"session": "abc123", "token": "xyz"}

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
            patch("src.async_http._get_client", new_callable=AsyncMock, return_value=mock_client),
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
        # redirect_url 模式异常返回空字符串。
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
        # return_cookies 模式异常返回空字典。
        mock_client = AsyncMock()
        mock_client.get.side_effect = Exception("network error")

        with (
            patch("src.async_http._get_client", new_callable=AsyncMock, return_value=mock_client),
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
            # 调用参数 (proxy=None, timeout=20, verify=False, http2=True)：
            # 20 是请求默认超时（async_req 未显式传入时的兜底值），
            # False 来自 patch 的 config.ssl_verify，True 为 http2 默认开关。
            # 此用例守护「verify 缺省回落配置」而非硬编码 True/False。
            mock_get.assert_called_once_with(None, 20, False, True)


# ────────────────────────────────────────────────────────────
# get_response_status: URL 可达性检测
# ────────────────────────────────────────────────────────────


class TestGetResponseStatus:
    # get_response_status: URL 可达性检测。

    @pytest.mark.asyncio
    async def test_status_200_returns_true(self) -> None:
        # HEAD 返回 200 → True。
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
        # HEAD 返回 404 → False。
        # HEAD 404 即不可达，快速定罪不误放死链。
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
        # m3u8 URL HEAD 返回 405 → 降级 Range GET 探测。
        # 复刻斗鱼 hw CDN 禁用 HEAD（405）实测，须降级 Range GET 才能拿到真地址。
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
        mock_client.get.assert_called_once()

    @pytest.mark.asyncio
    async def test_m3u8_head_403_get_also_fails(self) -> None:
        # m3u8 URL HEAD 403 + Range GET 也失败 → False。
        # HEAD 403 且 Range GET 仍失败 → 真不可达，防误判可用放行死链。
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
