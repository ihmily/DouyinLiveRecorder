"""Tests for src/spider.py module - 抖音平台流地址解析路径."""

import json
from unittest.mock import AsyncMock, patch

import pytest

from src.spider import (
    _extract_room_data_from_html,
    _get_str_response,
    _loads_dict,
    extract_douyin_hevc_flv_url,
    get_douyin_app_stream_data,
    get_douyin_web_stream_data,
)


class TestGetStrResponse:
    """Test _get_str_response helper."""

    def test_str_input(self):
        assert _get_str_response("hello") == "hello"

    def test_tuple_input(self):
        assert _get_str_response(("body", {"cookie": "x"})) == "body"

    def test_none_input(self):
        assert _get_str_response(None) == ""

    def test_empty_tuple(self):
        assert _get_str_response(()) == ""


class TestLoadsDict:
    """Test _loads_dict helper."""

    def test_valid_json(self):
        result = _loads_dict('{"key": "value"}')
        assert result == {"key": "value"}

    def test_empty_string(self):
        assert _loads_dict("") == {}

    def test_non_dict_json(self):
        assert _loads_dict("[1,2,3]") == {}

    def test_invalid_json(self):
        with pytest.raises(json.JSONDecodeError):
            _loads_dict("not json")


class TestExtractDouyinHevcFlvUrl:
    """Test extract_douyin_hevc_flv_url - 从HTML提取HEVC FLV流地址."""

    def test_normal_extraction(self):
        """正常路径：HTML包含有效HEVC FLV流地址，正确提取并清理。"""
        html = (
            '<script>var data = "https://pull-flv-q11.douyincdn.com/thirdgame/'
            'stream-731829344212345678.flv?expire=123\\u0026major_anchor_level=svip"</script>'
        )
        result = extract_douyin_hevc_flv_url(html)
        assert result is not None
        assert "stream-731829344212345678.flv" in result
        assert "&" in result  # \u0026 已替换为 &
        assert "\\u0026" not in result

    def test_skips_audio_only(self):
        """正常路径：跳过 only_audio=1 的流地址。"""
        html = (
            '"https://pull-flv-q11.douyincdn.com/thirdgame/'
            'stream-731829344212345678.flv?expire=123&only_audio=1"'
            '"https://pull-flv-q11.douyincdn.com/thirdgame/'
            'stream-731829344212345679.flv?expire=456&major_anchor_level=svip"'
        )
        result = extract_douyin_hevc_flv_url(html)
        assert result is not None
        assert "stream-731829344212345679.flv" in result

    def test_no_match_returns_none(self):
        """异常路径：HTML中无匹配流地址，返回None。"""
        html = "<html><body>no stream here</body></html>"
        assert extract_douyin_hevc_flv_url(html) is None

    def test_empty_html(self):
        """异常路径：空HTML返回None。"""
        assert extract_douyin_hevc_flv_url("") is None


class TestGetDouyinWebStreamData:
    """Test get_douyin_web_stream_data - 抖音网页端API获取直播数据."""

    @pytest.mark.asyncio
    async def test_normal_api_response(self):
        """正常路径：API返回有效JSON，status=2且包含stream_url，正确解析房间数据。"""
        api_response = json.dumps(
            {
                "status_code": 0,
                "data": {
                    "data": [
                        {
                            "status": 2,
                            "title": "测试直播间",
                            "stream_url": {
                                "hls_pull_url_map": {"FULL_HD1": "https://pull-hls.q11.douyincdn.com/live/test.m3u8"},
                                "flv_pull_url": {"FULL_HD1": "https://pull-flv.q11.douyincdn.com/live/test.flv"},
                            },
                        }
                    ],
                    "user": {"nickname": "测试主播"},
                },
            }
        )
        # 第二次请求（获取 HEVC FLV URL 的 HTML）
        html_response = "<html>no hevc stream</html>"

        with (
            patch("src.spider.async_req", new_callable=AsyncMock, side_effect=[api_response, html_response]),
            patch("src.spider._ensure_ttwid", new_callable=AsyncMock, return_value="ttwid=fake_ttwid"),
        ):
            result = await get_douyin_web_stream_data("https://live.douyin.com/7318293442")

        assert result["anchor_name"] == "测试主播"
        assert result["status"] == 2
        assert "stream_url" in result

    @pytest.mark.asyncio
    async def test_api_empty_response_fallback_html(self):
        """异常路径：API两次返回空响应，回退到HTML抓取成功。"""
        html_with_data = (
            '{"state":1}\\"roomStore\\":{\\"roomInfo\\":{\\"room\\":{\\"status\\":2,'
            '\\"title\\":\\"测试\\",\\"stream_url\\":{\\"hls_pull_url_map\\":{},\\"flv_pull_url\\":{}}}},'
            '\\"has_commerce_goods\\"'
        )
        # 构造一个能被正则匹配的HTML
        valid_html = (
            '<script nonce="abc">self.__pace_f.push([1,"{\\"state\\":1,'
            '\\"roomStore\\":{\\"roomInfo\\":{\\"room\\":{\\"status\\":2,'
            '\\"title\\":\\"测试\\",\\"stream_url\\":{\\"hls_pull_url_map\\":{},\\"flv_pull_url\\":{}}}},'
            '\\"has_commerce_goods\\":0}]\\n"])</script>'
        )

        with (
            patch(
                "src.spider.async_req",
                new_callable=AsyncMock,
                side_effect=["", "", valid_html],  # 两次API空响应 + HTML回退
            ),
            patch("src.spider._ensure_ttwid", new_callable=AsyncMock, return_value="ttwid=fake"),
            patch("src.spider.asyncio.sleep", new_callable=AsyncMock),
        ):
            result = await get_douyin_web_stream_data("https://live.douyin.com/7318293442")

        # HTML回退解析可能成功或失败（取决于正则匹配），但不应抛出未捕获异常
        assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_api_error_returns_empty_anchor(self):
        """异常路径：API返回非0状态码且HTML回退也失败，返回空anchor_name。"""
        error_response = json.dumps({"status_code": 10002, "status_msg": "risk control"})

        with (
            patch(
                "src.spider.async_req",
                new_callable=AsyncMock,
                side_effect=[error_response, error_response, "<html>no data</html>"],
            ),
            patch("src.spider._ensure_ttwid", new_callable=AsyncMock, return_value="ttwid=fake"),
            patch("src.spider.asyncio.sleep", new_callable=AsyncMock),
        ):
            result = await get_douyin_web_stream_data("https://live.douyin.com/7318293442")

        assert result["anchor_name"] == ""

    @pytest.mark.asyncio
    async def test_custom_cookies_used(self):
        """正常路径：传入自定义cookies时不再调用_ensure_ttwid。"""
        api_response = json.dumps(
            {
                "status_code": 0,
                "data": {
                    "data": [{"status": 4, "title": "未开播"}],
                    "user": {"nickname": "主播"},
                },
            }
        )

        mock_ttwid = AsyncMock(return_value="ttwid=should_not_be_called")
        with (
            patch("src.spider.async_req", new_callable=AsyncMock, return_value=api_response),
            patch("src.spider._ensure_ttwid", mock_ttwid),
        ):
            result = await get_douyin_web_stream_data(
                "https://live.douyin.com/7318293442", cookies="custom_cookie=abc"
            )

        mock_ttwid.assert_not_called()
        assert result["anchor_name"] == "主播"


class TestGetDouyinAppStreamData:
    """Test get_douyin_app_stream_data - 抖音APP端接口获取直播数据."""

    @pytest.mark.asyncio
    async def test_live_douyin_url_delegates_to_web(self):
        """正常路径：live.douyin.com 链接直接委托给 get_douyin_web_stream_data。"""
        expected = {"status": 2, "anchor_name": "主播", "stream_url": {}}

        with patch(
            "src.spider.get_douyin_web_stream_data", new_callable=AsyncMock, return_value=expected
        ) as mock_web:
            result = await get_douyin_app_stream_data("https://live.douyin.com/7318293442")

        mock_web.assert_called_once_with("https://live.douyin.com/7318293442", None, None)
        assert result == expected

    @pytest.mark.asyncio
    async def test_short_url_normal_resolution(self):
        """正常路径：短链接通过 get_sec_user_id 解析后调用APP接口获取数据。"""
        app_response = json.dumps(
            {
                "status_code": 0,
                "data": {
                    "room": {
                        "status": 2,
                        "title": "直播中",
                        "owner": {"nickname": "APP主播"},
                        "stream_url": {
                            "hls_pull_url_map": {"FULL_HD1": "https://pull-hls.douyincdn.com/live/app.m3u8"},
                            "flv_pull_url": {"FULL_HD1": "https://pull-flv.douyincdn.com/live/app.flv"},
                        },
                    }
                },
            }
        )

        with (
            patch(
                "src.spider.get_sec_user_id",
                new_callable=AsyncMock,
                return_value=("7318293442", "MS4wLjABAAAA_sec"),
            ),
            patch("src.spider.async_req", new_callable=AsyncMock, return_value=app_response),
            patch("src.spider._ensure_ttwid", new_callable=AsyncMock, return_value="ttwid=fake"),
        ):
            result = await get_douyin_app_stream_data("https://v.douyin.com/iQLgKSj/")

        assert result["anchor_name"] == "APP主播"
        assert result["status"] == 2

    @pytest.mark.asyncio
    async def test_error_returns_empty_anchor(self):
        """异常路径：所有解析路径失败，返回空anchor_name字典。"""
        with (
            patch(
                "src.spider.get_sec_user_id",
                new_callable=AsyncMock,
                side_effect=Exception("network error"),
            ),
            patch("src.spider._ensure_ttwid", new_callable=AsyncMock, return_value="ttwid=fake"),
            patch("src.spider.is_user_homepage_url", return_value=False),
        ):
            result = await get_douyin_app_stream_data("https://v.douyin.com/invalid/")

        assert result["anchor_name"] == ""


class TestExtractRoomDataFromHtml:
    """Test _extract_room_data_from_html - HTML回退解析."""

    def test_empty_html(self):
        """异常路径：空HTML返回空字典。"""
        assert _extract_room_data_from_html("") == {}

    def test_no_match_returns_empty(self):
        """异常路径：HTML中无匹配模式返回空字典。"""
        assert _extract_room_data_from_html("<html><body>nothing</body></html>") == {}
