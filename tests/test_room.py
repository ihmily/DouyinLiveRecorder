# src/room.py 回归测试：URL 解析、请求签名入口与共享请求头 HEADERS。

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from src.room import HEADERS, UnsupportedUrlError


# 守卫 get_sec_user_id / get_unique_id 在 URL 非法时抛出的专用异常类型。
# 验证其可被正常构造、是 Exception 子类、可作为 Exception 被捕获。
class TestUnsupportedUrlError:

    # 异常须可被构造并携带消息内容，供上层据此识别"不支持的 URL"
    def test_exception_creation(self) -> None:
        with pytest.raises(UnsupportedUrlError) as exc_info:
            raise UnsupportedUrlError("Test error message")
        assert "Test error message" in str(exc_info.value)

    # 必须是 Exception 的子类，才能被通用异常处理路径识别
    def test_exception_is_exception(self) -> None:
        assert issubclass(UnsupportedUrlError, Exception)

    def test_exception_can_be_caught_as_exception(self) -> None:
        # 须能被通用 Exception 捕获，保证上层统一异常处理不漏接
        try:
            raise UnsupportedUrlError("test")
        except Exception as e:
            assert isinstance(e, UnsupportedUrlError)


class TestHeaders:
    # 守卫共享请求头常量 HEADERS 的关键字段，缺失会被平台识别为异常客户端

    def test_headers_is_dict(self) -> None:
        # HEADERS 须为 dict，供 httpx 直接展开为请求头
        assert isinstance(HEADERS, dict)

    def test_headers_has_user_agent(self) -> None:
        # 须带 User-Agent，缺失会被多数平台识别为脚本客户端
        assert "User-Agent" in HEADERS
        assert len(HEADERS["User-Agent"]) > 0

    def test_headers_has_accept_language(self) -> None:
        # 必须带 zh-CN 语言以匹配区域风控与页面，缺失会被识别为异常客户端
        assert "Accept-Language" in HEADERS
        assert "zh-CN" in HEADERS["Accept-Language"]

    def test_headers_has_cookie(self) -> None:
        # 预置 Cookie 头是绕过部分平台无 Cookie 即 401/403 风控的前提
        assert "Cookie" in HEADERS


class TestGetSecUserId:
    # 守卫 get_sec_user_id：从 reflow 重定向 URL 解析 room_id 与 sec_user_id

    @pytest.mark.asyncio
    # 守卫函数可导入且可调用，防止重命名/删除导致调用方崩溃
    async def test_function_exists(self) -> None:
        from src.room import get_sec_user_id

        assert callable(get_sec_user_id)

    @pytest.mark.asyncio
    # 须为协程函数，调用方以 await 调用
    async def test_function_is_async(self) -> None:
        import inspect

        from src.room import get_sec_user_id

        assert inspect.iscoroutinefunction(get_sec_user_id)

    @pytest.mark.asyncio
    # 正常路径：reflow URL 含 sec_user_id，正确提取 room_id 与 sec_user_id
    async def test_normal_extraction(self) -> None:
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
        # reflow 路径段即 room_id，query 中的 sec_user_id 即用户唯一标识，二者须正确提取
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
    # 守卫 get_unique_id：解析用户 unique_id（JSON 接口被风控时回退分享页 HTML）

    @pytest.mark.asyncio
    # 守卫函数可导入且可调用，防止重命名/删除导致调用方崩溃
    async def test_function_exists(self) -> None:
        from src.room import get_unique_id

        assert callable(get_unique_id)

    @pytest.mark.asyncio
    # 守卫其为协程函数，确保调用方以 await 调用
    async def test_function_is_async(self) -> None:
        import inspect

        from src.room import get_unique_id

        assert inspect.iscoroutinefunction(get_unique_id)

    @pytest.mark.asyncio
    # 兜底路径：JSON 接口被风控后仍能从分享页 HTML 提取 unique_id
    async def test_normal_extraction(self) -> None:
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


# [历史注] 原 TestGetLiveRoomId 类（4 用例）随 get_live_room_id 一并删除
# ——该函数全仓无生产调用点且键缺失分支返回值与注解矛盾，生产代码已移除。


# get_xbogus 是抖音请求签名入口；守卫函数存在性与协程形态，供调用方 await。
class TestGetXbogus:

    @pytest.mark.asyncio
    # 守卫函数可导入且可调用，防止重命名/删除导致调用方崩溃
    async def test_function_exists(self) -> None:
        from src.room import get_xbogus

        assert callable(get_xbogus)

    @pytest.mark.asyncio
    # 守卫其为协程函数，确保调用方以 await 调用
    async def test_function_is_async(self) -> None:
        import inspect

        from src.room import get_xbogus

        assert inspect.iscoroutinefunction(get_xbogus)
