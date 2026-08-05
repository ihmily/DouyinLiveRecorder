# Tests for src/async_http.py module — 客户端管理 + 核心请求路径。

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from src.async_http import (
    _client_cache,
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
    async def test_creates_new_client(self):
        # 首次调用创建新 AsyncClient 并缓存。
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
    async def test_reuses_cached_client(self):
        # 相同参数复用同一 client 实例。
        _client_cache.clear()
        try:
            c1 = await _get_client(None, 10, True, False)
            c2 = await _get_client(None, 20, True, False)  # timeout 不同但 key 不含 timeout
            assert c1 is c2
        finally:
            await _close_all_clients()

    @pytest.mark.asyncio
    async def test_different_proxy_creates_different_client(self):
        # 不同 proxy 参数创建不同 client。
        _client_cache.clear()
        try:
            c1 = await _get_client(None, 10, True, False)
            c2 = await _get_client("http://proxy:8080", 10, True, False)
            assert c1 is not c2
            assert len(_client_cache) == 2
        finally:
            await _close_all_clients()

    @pytest.mark.asyncio
    async def test_closed_client_replaced(self):
        # 缓存的 client 已关闭时创建新的。
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


# ────────────────────────────────────────────────────────────
# _close_all_clients / close_all_clients_sync
# ────────────────────────────────────────────────────────────


class TestCloseAllClients:
    # _close_all_clients: 释放所有缓存客户端。

    @pytest.mark.asyncio
    async def test_close_all(self):
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
    async def test_close_empty_cache(self):
        # 空缓存调用不报错。
        _client_cache.clear()
        await _close_all_clients()
        assert len(_client_cache) == 0


class TestCloseAllClientsSync:
    # close_all_clients_sync: 同步安全清理。

    def test_empty_cache_no_error(self):
        # 空缓存时直接返回，不报错。
        _client_cache.clear()
        close_all_clients_sync()  # 不应抛异常

    def test_clears_cache_when_populated(self):
        # 缓存非空时，调用后缓存被清空（无论是否在事件循环内）。
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

    @pytest.mark.asyncio
    async def test_get_request_returns_text(self):
        # GET 请求返回响应文本。
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
    async def test_post_with_dict_data(self):
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
    async def test_post_with_string_data(self):
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
    async def test_post_with_bytes_data(self):
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
    async def test_redirect_url_returns_url(self):
        # redirect_url=True 返回重定向后 URL。
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
    async def test_return_cookies_returns_cookies(self):
        # return_cookies=True 返回 cookie 字典。
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
    async def test_return_cookies_with_include_cookies(self):
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
    async def test_exception_returns_empty_string(self):
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
    async def test_exception_redirect_returns_empty_string(self):
        # redirect_url 模式异常返回空字符串。
        mock_client = AsyncMock()
        mock_client.get.side_effect = httpx.TimeoutException("timeout")

        with (
            patch("src.async_http._get_client", new_callable=AsyncMock, return_value=mock_client),
            patch("src.async_http.utils.handle_proxy_addr", return_value=None),
        ):
            result = await async_req("https://example.com", redirect_url=True)

        assert result == ""

    @pytest.mark.asyncio
    async def test_exception_cookies_returns_empty_dict(self):
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
    async def test_verify_defaults_to_config(self):
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
            # _get_client 被调用时 verify 参数应为 config.ssl_verify 的值
            mock_get.assert_called_once_with(None, 20, False, True)


# ────────────────────────────────────────────────────────────
# get_response_status: URL 可达性检测
# ────────────────────────────────────────────────────────────


class TestGetResponseStatus:
    # get_response_status: URL 可达性检测。

    @pytest.mark.asyncio
    async def test_status_200_returns_true(self):
        # HEAD 返回 200 → True。
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
    async def test_status_404_returns_false(self):
        # HEAD 返回 404 → False。
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
    async def test_m3u8_head_405_fallback_to_get(self):
        # m3u8 URL HEAD 返回 405 → 降级 Range GET 探测。
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
    async def test_m3u8_head_403_get_also_fails(self):
        # m3u8 URL HEAD 403 + Range GET 也失败 → False。
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
    async def test_exception_returns_false(self):
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
    async def test_non_m3u8_403_returns_false_directly(self):
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
