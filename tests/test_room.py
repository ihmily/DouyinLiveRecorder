# Tests for src/room.py module.

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from src.room import HEADERS, UnsupportedUrlError


class TestUnsupportedUrlError:
    # Test UnsupportedUrlError exception.

    def test_exception_creation(self) -> None:
        # Test exception can be created and raised.
        with pytest.raises(UnsupportedUrlError) as exc_info:
            raise UnsupportedUrlError("Test error message")
        assert "Test error message" in str(exc_info.value)

    def test_exception_is_exception(self) -> None:
        # Test UnsupportedUrlError is an Exception subclass.
        assert issubclass(UnsupportedUrlError, Exception)

    def test_exception_can_be_caught_as_exception(self) -> None:
        # Test exception can be caught as Exception.
        try:
            raise UnsupportedUrlError("test")
        except Exception as e:
            assert isinstance(e, UnsupportedUrlError)


class TestHeaders:
    # Test HEADERS constant.

    def test_headers_is_dict(self) -> None:
        # Test HEADERS is a dictionary.
        assert isinstance(HEADERS, dict)

    def test_headers_has_user_agent(self) -> None:
        # Test HEADERS contains User-Agent.
        assert "User-Agent" in HEADERS
        assert len(HEADERS["User-Agent"]) > 0

    def test_headers_has_accept_language(self) -> None:
        # Test HEADERS contains Accept-Language.
        assert "Accept-Language" in HEADERS
        assert "zh-CN" in HEADERS["Accept-Language"]

    def test_headers_has_cookie(self) -> None:
        # Test HEADERS contains Cookie key.
        assert "Cookie" in HEADERS


class TestGetSecUserId:
    # Test get_sec_user_id function.

    @pytest.mark.asyncio
    async def test_function_exists(self) -> None:
        # Test function is importable.
        from src.room import get_sec_user_id

        assert callable(get_sec_user_id)

    @pytest.mark.asyncio
    async def test_function_is_async(self) -> None:
        # Test function is async.
        import inspect

        from src.room import get_sec_user_id

        assert inspect.iscoroutinefunction(get_sec_user_id)

    @pytest.mark.asyncio
    async def test_normal_extraction(self) -> None:
        # 正常路径：重定向 URL 包含 reflow/ 和 sec_user_id 参数，正确提取 room_id 和 sec_user_id。
        from src.room import get_sec_user_id

        redirect_url = "https://live.douyin.com/reflow/7318293442?sec_user_id=MS4wLjABAAAA_test_sec&aid=6383"
        mock_response = MagicMock()
        mock_response.url = redirect_url

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("src.room.httpx.AsyncClient", return_value=mock_client):
            result = await get_sec_user_id("https://v.douyin.com/iQLgKSj/")

        assert result is not None
        room_id, sec_user_id = result
        assert room_id == "7318293442"
        assert sec_user_id == "MS4wLjABAAAA_test_sec"

    @pytest.mark.asyncio
    async def test_unsupported_url_raises(self) -> None:
        # 异常路径：重定向 URL 不包含 reflow/，抛出 UnsupportedUrlError。
        from src.room import get_sec_user_id

        mock_response = MagicMock()
        mock_response.url = "https://www.douyin.com/user/some_user"

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("src.room.httpx.AsyncClient", return_value=mock_client):
            with pytest.raises(UnsupportedUrlError):
                await get_sec_user_id("https://v.douyin.com/invalid/")


class TestGetUniqueId:
    # Test get_unique_id function.

    @pytest.mark.asyncio
    async def test_function_exists(self) -> None:
        # Test function is importable.
        from src.room import get_unique_id

        assert callable(get_unique_id)

    @pytest.mark.asyncio
    async def test_function_is_async(self) -> None:
        # Test function is async.
        import inspect

        from src.room import get_unique_id

        assert inspect.iscoroutinefunction(get_unique_id)

    @pytest.mark.asyncio
    async def test_normal_extraction(self) -> None:
        # 兜底路径：JSON 接口不可用时，仍能从用户分享页 HTML 中提取 unique_id。
        from src.room import get_unique_id

        # 第一次请求：重定向到用户主页（不含 reflow/）
        first_response = MagicMock()
        first_response.url = "https://www.douyin.com/user/MS4wLjABAAAA_sec123"

        # 第二次请求：JSON 用户信息接口——模拟被风控返回空响应体，json() 抛错
        api_response = MagicMock()
        api_response.json.side_effect = ValueError("Expecting value: line 1 column 1 (char 0)")

        # 第三次请求：用户分享页，HTML 中包含 unique_id
        second_response = MagicMock()
        second_response.text = '{"unique_id":"douyin_test_99","verification_type":1}'

        mock_client = AsyncMock()
        mock_client.get.side_effect = [first_response, api_response, second_response]
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("src.room.httpx.AsyncClient", return_value=mock_client),
            patch("src.room._ensure_douyin_ttwid", new_callable=AsyncMock, return_value="ttwid=fake"),
        ):
            result = await get_unique_id("https://v.douyin.com/iQLgKSj/")

        assert result == "douyin_test_99"

    @pytest.mark.asyncio
    async def test_reflow_url_raises_unsupported(self) -> None:
        # 异常路径：重定向 URL 包含 reflow/，抛出 UnsupportedUrlError。
        from src.room import get_unique_id

        mock_response = MagicMock()
        mock_response.url = "https://live.douyin.com/reflow/123456?sec_user_id=abc&aid=6383"

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("src.room.httpx.AsyncClient", return_value=mock_client):
            with pytest.raises(UnsupportedUrlError):
                await get_unique_id("https://v.douyin.com/iQLgKSj/")


class TestGetLiveRoomId:
    # Test get_live_room_id function.

    @pytest.mark.asyncio
    async def test_function_exists(self) -> None:
        # Test function is importable.
        from src.room import get_live_room_id

        assert callable(get_live_room_id)

    @pytest.mark.asyncio
    async def test_function_is_async(self) -> None:
        # Test function is async.
        import inspect

        from src.room import get_live_room_id

        assert inspect.iscoroutinefunction(get_live_room_id)

    @pytest.mark.asyncio
    async def test_normal_extraction(self) -> None:
        # 正常路径：API 返回 JSON，正确提取 web_rid。
        from src.room import get_live_room_id

        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {"data": {"room": {"owner": {"web_rid": "web_rid_78901"}}}}

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("src.room.httpx.AsyncClient", return_value=mock_client),
            patch("src.room.get_xbogus", new_callable=AsyncMock, return_value="fake_xbogus"),
        ):
            result = await get_live_room_id("7318293442", "MS4wLjABAAAA_sec123")

        assert result == "web_rid_78901"

    @pytest.mark.asyncio
    async def test_http_error_raises(self) -> None:
        # 异常路径：API 返回 HTTP 错误状态码，抛出 HTTPStatusError。
        from src.room import get_live_room_id

        mock_request = httpx.Request("GET", "https://webcast.amemv.com/webcast/room/reflow/info/")
        mock_response = MagicMock()
        mock_response.status_code = 403
        mock_response.request = mock_request
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Forbidden", request=mock_request, response=mock_response
        )

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("src.room.httpx.AsyncClient", return_value=mock_client),
            patch("src.room.get_xbogus", new_callable=AsyncMock, return_value="fake_xbogus"),
        ):
            with pytest.raises(httpx.HTTPStatusError):
                await get_live_room_id("7318293442", "MS4wLjABAAAA_sec123")


class TestGetXbogus:
    # Test get_xbogus function.

    @pytest.mark.asyncio
    async def test_function_exists(self) -> None:
        # Test function is importable.
        from src.room import get_xbogus

        assert callable(get_xbogus)

    @pytest.mark.asyncio
    async def test_function_is_async(self) -> None:
        # Test function is async.
        import inspect

        from src.room import get_xbogus

        assert inspect.iscoroutinefunction(get_xbogus)
