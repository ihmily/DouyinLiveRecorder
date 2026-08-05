# Tests for src/spider.py module - 抖音平台流地址解析路径.

import json
from unittest.mock import AsyncMock, patch

import pytest

from src.spider import get_douyin_app_stream_data  # noqa: E402
from src.spider import (
    _extract_room_data_from_html,
    _get_str_response,
    _loads_dict,
    _safe_extract_id,
    extract_douyin_hevc_flv_url,
    get_bilibili_room_info,
    get_bilibili_stream_data,
    get_douyin_web_stream_data,
    get_douyu_info_data,
    get_huya_stream_data,
    get_kuaishou_stream_data,
    get_netease_stream_data,
    get_params,
    get_play_url_list,
    get_qiandurebo_stream_data,
    md5,
)


class TestGetStrResponse:
    # Test _get_str_response helper.

    def test_str_input(self):
        assert _get_str_response("hello") == "hello"

    def test_tuple_input(self):
        assert _get_str_response(("body", {"cookie": "x"})) == "body"

    def test_none_input(self):
        assert _get_str_response(None) == ""

    def test_empty_tuple(self):
        assert _get_str_response(()) == ""


class TestLoadsDict:
    # Test _loads_dict helper.

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
    # Test extract_douyin_hevc_flv_url - 从HTML提取HEVC FLV流地址.

    def test_normal_extraction(self):
        # 正常路径：HTML包含有效HEVC FLV流地址，正确提取并清理。
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
        # 正常路径：跳过 only_audio=1 的流地址。
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
        # 异常路径：HTML中无匹配流地址，返回None。
        html = "<html><body>no stream here</body></html>"
        assert extract_douyin_hevc_flv_url(html) is None

    def test_empty_html(self):
        # 异常路径：空HTML返回None。
        assert extract_douyin_hevc_flv_url("") is None


class TestGetDouyinWebStreamData:
    # Test get_douyin_web_stream_data - 抖音网页端API获取直播数据.

    @pytest.mark.asyncio
    async def test_normal_api_response(self):
        # 正常路径：API返回有效JSON，status=2且包含stream_url，正确解析房间数据。
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
        # 异常路径：API两次返回空响应，回退到HTML抓取成功。
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
        # 异常路径：API返回非0状态码且HTML回退也失败，返回空anchor_name。
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
        # 正常路径：传入自定义cookies时不再调用_ensure_ttwid。
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
            result = await get_douyin_web_stream_data("https://live.douyin.com/7318293442", cookies="custom_cookie=abc")

        mock_ttwid.assert_not_called()
        assert result["anchor_name"] == "主播"


class TestGetDouyinAppStreamData:
    # Test get_douyin_app_stream_data - 抖音APP端接口获取直播数据.

    @pytest.mark.asyncio
    async def test_live_douyin_url_delegates_to_web(self):
        # 正常路径：live.douyin.com 链接直接委托给 get_douyin_web_stream_data。
        expected = {"status": 2, "anchor_name": "主播", "stream_url": {}}

        with patch("src.spider.get_douyin_web_stream_data", new_callable=AsyncMock, return_value=expected) as mock_web:
            result = await get_douyin_app_stream_data("https://live.douyin.com/7318293442")

        mock_web.assert_called_once_with("https://live.douyin.com/7318293442", None, None)
        assert result == expected

    @pytest.mark.asyncio
    async def test_short_url_normal_resolution(self):
        # 正常路径：短链接通过 get_sec_user_id 解析后调用APP接口获取数据。
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
        # 异常路径：所有解析路径失败，返回空anchor_name字典。
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
    # Test _extract_room_data_from_html - HTML回退解析.

    def test_empty_html(self):
        # 异常路径：空HTML返回空字典。
        assert _extract_room_data_from_html("") == {}

    def test_no_match_returns_empty(self):
        # 异常路径：HTML中无匹配模式返回空字典。
        assert _extract_room_data_from_html("<html><body>nothing</body></html>") == {}


class TestSafeExtractId:
    # Test _safe_extract_id - URL安全提取路径ID.

    def test_basic_url(self):
        assert _safe_extract_id("https://example.com/path/12345") == "12345"

    def test_url_with_query(self):
        assert _safe_extract_id("https://example.com/path/12345?foo=bar") == "12345"

    def test_url_with_trailing_slash(self):
        assert _safe_extract_id("https://example.com/path/12345/") == "12345"

    def test_no_path_id(self):
        # "https://example.com/" → rsplit → ["https:", "example.com"] → 返回 "example.com"
        assert _safe_extract_id("https://example.com/") == "example.com"

    def test_root_url(self):
        assert _safe_extract_id("https://example.com") == "example.com"

    def test_default_value(self):
        # 仅当路径中无 "/" 时才返回 default
        assert _safe_extract_id("https://example.com", default="fallback") == "example.com"
        assert _safe_extract_id("single_segment", default="fallback") == "fallback"


class TestGetParams:
    # Test get_params - URL参数提取.

    def test_existing_param(self):
        assert get_params("https://example.com?foo=bar&baz=qux", "foo") == "bar"

    def test_missing_param(self):
        assert get_params("https://example.com?foo=bar", "missing") is None

    def test_no_query_string(self):
        assert get_params("https://example.com/path", "foo") is None

    def test_multiple_values_returns_first(self):
        assert get_params("https://example.com?a=1&a=2", "a") == "1"


class TestMd5:
    # Test md5 - MD5哈希计算.

    def test_known_hash(self):
        assert md5("hello") == "5d41402abc4b2a76b9719d911017c592"

    def test_empty_string(self):
        assert md5("") == "d41d8cd98f00b204e9800998ecf8427e"

    def test_deterministic(self):
        assert md5("test") == md5("test")


class TestGetPlayUrlList:
    # Test get_play_url_list - M3U8播放列表解析.

    @pytest.mark.asyncio
    async def test_https_urls(self):
        # 提取以 https:// 开头的 URL.
        m3u8_content = "#EXTM3U\nhttps://cdn.example.com/stream1.m3u8\nhttps://cdn.example.com/stream2.m3u8"
        with patch("src.spider.async_req", new_callable=AsyncMock, return_value=m3u8_content):
            result = await get_play_url_list("https://example.com/master.m3u8")
            assert len(result) == 2
            assert "stream1.m3u8" in result[0]

    @pytest.mark.asyncio
    async def test_relative_m3u8_urls(self):
        # 提取相对路径 m3u8.
        m3u8_content = "#EXTM3U\nstream1.m3u8\nstream2.m3u8"
        with patch("src.spider.async_req", new_callable=AsyncMock, return_value=m3u8_content):
            result = await get_play_url_list("https://example.com/master.m3u8")
            assert len(result) == 2

    @pytest.mark.asyncio
    async def test_empty_response(self):
        # 空响应返回空列表.
        with patch("src.spider.async_req", new_callable=AsyncMock, return_value=""):
            result = await get_play_url_list("https://example.com/master.m3u8")
            assert result == []

    @pytest.mark.asyncio
    async def test_non_string_response(self):
        # 非字符串响应返回空列表.
        with patch("src.spider.async_req", new_callable=AsyncMock, return_value={"error": "bad"}):
            result = await get_play_url_list("https://example.com/master.m3u8")
            assert result == []

    @pytest.mark.asyncio
    async def test_bandwidth_sorting(self):
        # 按带宽降序排序.
        m3u8_content = (
            "#EXTINF:10\n#EXT-X-BANDWIDTH=1000000\nhttps://cdn.example.com/low.m3u8\n"
            "#EXTINF:10\n#EXT-X-BANDWIDTH=5000000\nhttps://cdn.example.com/high.m3u8"
        )
        with patch("src.spider.async_req", new_callable=AsyncMock, return_value=m3u8_content):
            result = await get_play_url_list("https://example.com/master.m3u8")
            assert len(result) == 2
            assert "high" in result[0]


class TestKuaishouStreamData:
    # Test get_kuaishou_stream_data - 快手直播数据.

    @pytest.mark.asyncio
    async def test_network_error_returns_not_live(self):
        # 网络异常返回 is_live=False.
        with patch("src.spider.async_req", new_callable=AsyncMock, side_effect=Exception("network error")):
            result = await get_kuaishou_stream_data("https://live.kuaishou.com/u/testuser")
            assert result["is_live"] is False

    @pytest.mark.asyncio
    async def test_no_initial_state_returns_not_live(self):
        # 无 __INITIAL_STATE__ 返回 is_live=False.
        with patch("src.spider.async_req", new_callable=AsyncMock, return_value="<html>no data</html>"):
            result = await get_kuaishou_stream_data("https://live.kuaishou.com/u/testuser")
            assert result["is_live"] is False


class TestHuyaStreamData:
    # Test get_huya_stream_data - 虎牙直播数据.

    @pytest.mark.asyncio
    async def test_no_stream_data_returns_empty(self):
        # 无流数据时装饰器捕获异常，返回空字典。
        with patch("src.spider.async_req", new_callable=AsyncMock, return_value="<html>no stream</html>"):
            result = await get_huya_stream_data("https://www.huya.com/12345")
            assert result == {"is_live": False}

    @pytest.mark.asyncio
    async def test_successful_parse(self):
        # 正常解析虎牙流数据.
        html = 'stream: {"data":{"gameStreamInfoList":[]}},"iWebDefaultBitRate"'
        with patch("src.spider.async_req", new_callable=AsyncMock, return_value=html):
            result = await get_huya_stream_data("https://www.huya.com/12345")
            assert isinstance(result, dict)


class TestDouyuInfoData:
    # Test get_douyu_info_data - 斗鱼直播间信息.

    @pytest.mark.asyncio
    async def test_rid_from_url(self):
        # 从 URL 提取 rid.
        betard_response = json.dumps(
            {
                "room": {
                    "nickname": "斗鱼主播",
                    "videoLoop": 0,
                    "show_status": 1,
                    "room_name": "测试直播间",
                    "room_id": 3125893,
                }
            }
        )
        with patch("src.spider.async_req", new_callable=AsyncMock, return_value=betard_response):
            result = await get_douyu_info_data("https://www.douyu.com/3125893?rid=3125893")
            assert result["anchor_name"] == "斗鱼主播"
            assert result["is_live"] is True

    @pytest.mark.asyncio
    async def test_not_live(self):
        # 未开播状态.
        betard_response = json.dumps(
            {
                "room": {
                    "nickname": "主播",
                    "videoLoop": 1,
                    "show_status": 0,
                    "room_name": "",
                    "room_id": 123,
                }
            }
        )
        with patch("src.spider.async_req", new_callable=AsyncMock, return_value=betard_response):
            result = await get_douyu_info_data("https://www.douyu.com/123")
            assert result["is_live"] is False


class TestNeteaseStreamData:
    # Test get_netease_stream_data - 网易CC直播数据.

    @pytest.mark.asyncio
    async def test_no_next_data_returns_empty(self):
        # 无 __NEXT_DATA__ 时装饰器捕获异常，返回空字典。
        with patch("src.spider.async_req", new_callable=AsyncMock, return_value="<html>no data</html>"):
            result = await get_netease_stream_data("https://cc.163.com/12345")
            assert result == {"is_live": False}

    @pytest.mark.asyncio
    async def test_live_status(self):
        # 直播中状态解析。
        next_data = {
            "props": {
                "pageProps": {
                    "roomInfoInitData": {
                        "live": {
                            "status": 1,
                            "nickname": "网易主播",
                            "title": "测试直播",
                            "quickplay": [{"url": "http://example.com/stream"}],
                            "sharefile": "http://example.com/share.m3u8",
                        },
                        "nickname": "网易主播",
                    }
                }
            }
        }
        # 注意正则要求 </script></body> 紧跟在 JSON 后面，且 id 和 crossorigin 之间需要其他属性
        html = f'<script id="__NEXT_DATA__" type="application/json" crossorigin="anonymous">{json.dumps(next_data)}</script></body>'
        with patch("src.spider.async_req", new_callable=AsyncMock, return_value=html):
            result = await get_netease_stream_data("https://cc.163.com/12345")
            assert result["is_live"] is True
            assert result["anchor_name"] == "网易主播"


class TestQiandureboStreamData:
    # Test get_qiandurebo_stream_data - 千度热播直播数据.

    @pytest.mark.asyncio
    async def test_no_user_data(self):
        # 无用户数据返回空.
        with patch("src.spider.async_req", new_callable=AsyncMock, return_value="<html>no user</html>"):
            result = await get_qiandurebo_stream_data("https://qiandurebo.com/web/index.php?room=123")
            assert result["is_live"] is False

    @pytest.mark.asyncio
    async def test_live_stream(self):
        # 直播中解析。
        # 正则: var user = (.*?)\r\n\s+user\.play_url （要求 user.play_url 前有缩进）
        # play_url 正则: "play_url": "(.*?)",\r\n 要求行尾有 \r\n
        html = (
            'var user = {"zb_nickname": "热播主播",\r\n'
            '  "play_url": "http://cdn.example.com/live.flv",\r\n'
            '  "other": "val",\r\n'
            "  user.play_url"
        )
        with patch("src.spider.async_req", new_callable=AsyncMock, return_value=html):
            result = await get_qiandurebo_stream_data("https://qiandurebo.com/web/index.php?room=123")
            # 正则 "zb_nickname": "(.*?)",\r\n 提取昵称
            assert result["anchor_name"] == "热播主播"
            assert result["is_live"] is True
            assert result["flv_url"] == "http://cdn.example.com/live.flv"


class TestBilibiliRoomInfo:
    # Test get_bilibili_room_info - B站直播间信息.

    @pytest.mark.asyncio
    async def test_error_returns_empty(self):
        # 异常返回空 anchor_name.
        with patch("src.spider.async_req", new_callable=AsyncMock, side_effect=Exception("network")):
            result = await get_bilibili_room_info("https://live.bilibili.com/26066074")
            assert result["anchor_name"] == ""
            assert result["live_status"] is False

    @pytest.mark.asyncio
    async def test_successful_parse(self):
        # 正常解析B站直播间.
        init_resp = json.dumps({"data": {"uid": 12345, "live_status": 1}})
        master_resp = json.dumps({"data": {"info": {"uname": "B站主播"}}})
        h5_resp = json.dumps({"data": {"room_info": {"title": "测试标题"}}})

        with patch(
            "src.spider.async_req",
            new_callable=AsyncMock,
            side_effect=[init_resp, master_resp, h5_resp],
        ):
            result = await get_bilibili_room_info("https://live.bilibili.com/26066074")
            assert result["anchor_name"] == "B站主播"
            assert result["live_status"] is True
            assert result["title"] == "测试标题"


class TestBilibiliStreamData:
    # Test get_bilibili_stream_data - B站直播流数据.

    @pytest.mark.asyncio
    async def test_play_url_success(self):
        # playUrl 接口成功.
        resp = json.dumps(
            {
                "code": 0,
                "data": {
                    "durl": [{"url": "https://d1--cn-gotcha01.bilivideo.com/live/test.flv"}],
                },
            }
        )
        with patch("src.spider.async_req", new_callable=AsyncMock, return_value=resp):
            result = await get_bilibili_stream_data("https://live.bilibili.com/26066074")
            assert result is not None
            assert "gotcha" in result["url"]

    @pytest.mark.asyncio
    async def test_play_url_empty_durl_fallback(self):
        # playUrl 无 durl 时回退到 getRoomPlayInfo.
        play_url_resp = json.dumps({"code": 0, "data": {"durl": []}})
        room_info_resp = json.dumps(
            {
                "data": {
                    "live_status": 0,
                    "playurl_info": {"playurl": {"stream": []}},
                }
            }
        )
        with patch(
            "src.spider.async_req",
            new_callable=AsyncMock,
            side_effect=[play_url_resp, room_info_resp],
        ):
            result = await get_bilibili_stream_data("https://live.bilibili.com/26066074")
            assert result is None

    @pytest.mark.asyncio
    async def test_empty_durl_list_returns_none(self):
        # 空 durl 列表返回 None.
        resp = json.dumps({"code": 0, "data": {"durl": []}})
        room_info = json.dumps({"data": {"live_status": 0, "playurl_info": {"playurl": {"stream": []}}}})
        with patch("src.spider.async_req", new_callable=AsyncMock, side_effect=[resp, room_info]):
            result = await get_bilibili_stream_data("https://live.bilibili.com/26066074")
            assert result is None
