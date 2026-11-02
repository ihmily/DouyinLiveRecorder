# src/spider.py 回归测试：抖音（Web/APP）流地址解析路径，及各平台解析函数与容错归一化入口的行为契约。

import ast
import asyncio
import json
import pathlib
import time
import types
from typing import Any, cast
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from src import spider as sp
from src.spider import get_douyin_app_stream_data  # noqa: E402
from src.spider import (
    _extract_room_data_from_html,
    _get_str_response,
    _loads_dict,
    _safe_extract_id,
    extract_douyin_hevc_flv_url,
    extract_kuaishou_eid,
    get_acfun_stream_data,
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
    # _get_str_response：归一化 async_req 返回值（str / (body, headers) 元组 / None → 一律取字符串）。
    # 真实请求可能返回纯文本，也可能返回 (响应体, 响应头) 元组（主流程靠元组透传 cookie）；
    # 下游一律按字符串处理，故须统一抽取首元素。

    def test_str_input(self) -> None:
        # 已是字符串：原样返回，不二次包装
        assert _get_str_response("hello") == "hello"

    def test_tuple_input(self) -> None:
        # 元组形态 (body, headers)：解包只取首元素（纯响应体），丢弃头部
        assert _get_str_response(("body", {"cookie": "x"})) == "body"

    def test_none_input(self) -> None:
        # 网络异常时 async_req 可能返回 None：须归一化为 "" 而非让下游 str() 崩
        assert _get_str_response(None) == ""

    def test_empty_tuple(self) -> None:
        # 空元组解包保护：缺省为 ""，避免 IndexError 冒泡到录制主流程
        assert _get_str_response(()) == ""


class TestLoadsDict:
    # _loads_dict：容错 JSON 解析，失败或非 dict 一律回 {}。
    # 下游普遍依赖「解析失败 => {}」不变量来跳过脏数据，而非区分"无数据"与"解析异常"。

    def test_valid_json(self) -> None:
        # 标准 JSON 对象原样解析
        result = _loads_dict('{"key": "value"}')
        assert result == {"key": "value"}

    def test_empty_string(self) -> None:
        # 空响应体（非 JSON）返回 {}：调用方据此判断"无房间数据"继续回退
        assert _loads_dict("") == {}

    def test_non_dict_json(self) -> None:
        # 顶层非 dict（如列表）按失败处理：防止下游 result.get 误把列表当映射而取到 None
        assert _loads_dict("[1,2,3]") == {}

    def test_invalid_json(self) -> None:
        # 非法 JSON（WAF 拦截页 / 302 落地 HTML / 截断 JSON）返回 {} 而非上抛：外围
        # @trace_error_decorator 会把抛出的异常吞成 {"is_live": False}，与 {} 的最终表现一致、
        # 却丢掉一切日志线索。[历史注] 旧用例断言「必须抛 JSONDecodeError」，锁的正是导致
        # 「明明在播却持续漏录」的错误前提。
        assert _loads_dict("not json") == {}
        assert _loads_dict("<html><body>403</body></html>") == {}
        assert _loads_dict('{"a": 1') == {}


class TestExtractDouyinHevcFlvUrl:
    # extract_douyin_hevc_flv_url：从 HTML 提取 HEVC FLV 流地址。

    def test_normal_extraction(self) -> None:
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

    def test_skips_audio_only(self) -> None:
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

    def test_no_match_returns_none(self) -> None:
        # 异常路径：HTML中无匹配流地址，返回None。
        html = "<html><body>no stream here</body></html>"
        assert extract_douyin_hevc_flv_url(html) is None

    def test_empty_html(self) -> None:
        assert extract_douyin_hevc_flv_url("") is None


class TestGetDouyinWebStreamData:
    # get_douyin_web_stream_data：抖音网页端 API 获取直播数据。

    @pytest.mark.asyncio
    async def test_normal_api_response(self) -> None:
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
        # 抖音 web API 的 room.status 字段：2=直播中、4=未开播（见 test_custom_cookies_used）。
        # async_req 的 side_effect 顺序即 fetch 顺序：[API 响应, HEVC HTML（第二次请求）]，本例两调都命中。
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
    async def test_api_empty_response_fallback_html(self) -> None:
        # API 两次返回空响应 → 走 HTML 回退分支（回退是否命中正则不锁，见函数末尾断言）。
        html_with_data = (
            '{"state":1}\\"roomStore\\":{\\"roomInfo\\":{\\"room\\":{\\"status\\":2,'
            '\\"title\\":\\"测试\\",\\"stream_url\\":{\\"hls_pull_url_map\\":{},\\"flv_pull_url\\":{}}}},'
            '\\"has_commerce_goods\\"'
        )
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
    async def test_api_error_returns_empty_anchor(self) -> None:
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
    async def test_custom_cookies_used(self) -> None:
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
    # get_douyin_app_stream_data：抖音 APP 端接口获取直播数据。

    @pytest.mark.asyncio
    async def test_live_douyin_url_delegates_to_web(self) -> None:
        # 正常路径：live.douyin.com 链接直接委托给 get_douyin_web_stream_data。
        expected = {"status": 2, "anchor_name": "主播", "stream_url": {}}

        with patch("src.spider.get_douyin_web_stream_data", new_callable=AsyncMock, return_value=expected) as mock_web:
            result = await get_douyin_app_stream_data("https://live.douyin.com/7318293442")

        mock_web.assert_called_once_with("https://live.douyin.com/7318293442", None, None)
        assert result == expected

    @pytest.mark.asyncio
    async def test_short_url_normal_resolution(self) -> None:
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
    async def test_error_returns_empty_anchor(self) -> None:
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
    # _extract_room_data_from_html：HTML 回退解析房间数据。

    def test_empty_html(self) -> None:
        # 异常路径：空HTML返回空字典。
        assert _extract_room_data_from_html("") == {}

    def test_no_match_returns_empty(self) -> None:
        # 异常路径：HTML中无匹配模式返回空字典。
        assert _extract_room_data_from_html("<html><body>nothing</body></html>") == {}


class TestSafeExtractId:
    # _safe_extract_id：从 URL 安全提取路径 ID。

    def test_basic_url(self) -> None:
        assert _safe_extract_id("https://example.com/path/12345") == "12345"

    def test_url_with_query(self) -> None:
        assert _safe_extract_id("https://example.com/path/12345?foo=bar") == "12345"

    def test_url_with_trailing_slash(self) -> None:
        assert _safe_extract_id("https://example.com/path/12345/") == "12345"

    def test_no_path_id(self) -> None:
        # "https://example.com/" → rsplit → ["https:", "example.com"] → 返回 "example.com"
        assert _safe_extract_id("https://example.com/") == "example.com"

    def test_root_url(self) -> None:
        assert _safe_extract_id("https://example.com") == "example.com"

    def test_default_value(self) -> None:
        # 仅当路径中无 "/" 时才返回 default
        assert _safe_extract_id("https://example.com", default="fallback") == "example.com"
        assert _safe_extract_id("single_segment", default="fallback") == "fallback"


class TestGetParams:
    # get_params：从 URL 提取指定查询参数。

    def test_existing_param(self) -> None:
        assert get_params("https://example.com?foo=bar&baz=qux", "foo") == "bar"

    def test_missing_param(self) -> None:
        assert get_params("https://example.com?foo=bar", "missing") is None

    def test_no_query_string(self) -> None:
        assert get_params("https://example.com/path", "foo") is None

    def test_multiple_values_returns_first(self) -> None:
        assert get_params("https://example.com?a=1&a=2", "a") == "1"


class TestMd5:
    # md5：计算签名用的 MD5 摘要。

    # 断言钉死标准 MD5 摘要值（快手/抖音请求体签名参数用它），防止算法被误改。

    def test_known_hash(self) -> None:
        # 经典向量 MD5("hello")：跨实现一致，作为回归锚点
        assert md5("hello") == "5d41402abc4b2a76b9719d911017c592"

    def test_empty_string(self) -> None:
        # 空串摘要是与输入无关的定值，验证边界不影响下游拼接
        assert md5("") == "d41d8cd98f00b204e9800998ecf8427e"

    def test_deterministic(self) -> None:
        # 同一输入必须产出同一摘要（幂等），否则签名每次都变会被服务端拒
        assert md5("test") == md5("test")


class TestGetPlayUrlList:
    # get_play_url_list：解析 M3U8 播放列表。

    @pytest.mark.asyncio
    async def test_https_urls(self) -> None:
        # 提取以 https:// 开头的 URL.
        m3u8_content = "#EXTM3U\nhttps://cdn.example.com/stream1.m3u8\nhttps://cdn.example.com/stream2.m3u8"
        with patch("src.spider.async_req", new_callable=AsyncMock, return_value=m3u8_content):
            result = await get_play_url_list("https://example.com/master.m3u8")
            assert len(result) == 2
            assert "stream1.m3u8" in result[0]

    @pytest.mark.asyncio
    async def test_relative_m3u8_urls(self) -> None:
        # 提取相对路径 m3u8.
        m3u8_content = "#EXTM3U\nstream1.m3u8\nstream2.m3u8"
        with patch("src.spider.async_req", new_callable=AsyncMock, return_value=m3u8_content):
            result = await get_play_url_list("https://example.com/master.m3u8")
            assert len(result) == 2

    @pytest.mark.asyncio
    async def test_empty_response(self) -> None:
        with patch("src.spider.async_req", new_callable=AsyncMock, return_value=""):
            result = await get_play_url_list("https://example.com/master.m3u8")
            assert result == []

    @pytest.mark.asyncio
    async def test_non_string_response(self) -> None:
        with patch("src.spider.async_req", new_callable=AsyncMock, return_value={"error": "bad"}):
            result = await get_play_url_list("https://example.com/master.m3u8")
            assert result == []

    @pytest.mark.asyncio
    async def test_bandwidth_sorting(self) -> None:
        # 按带宽降序排序.
        m3u8_content = (
            "#EXTINF:10\n#EXT-X-BANDWIDTH=1000000\nhttps://cdn.example.com/low.m3u8\n"
            "#EXTINF:10\n#EXT-X-BANDWIDTH=5000000\nhttps://cdn.example.com/high.m3u8"
        )
        with patch("src.spider.async_req", new_callable=AsyncMock, return_value=m3u8_content):
            result = await get_play_url_list("https://example.com/master.m3u8")
            assert len(result) == 2
            assert "high" in result[0]

    @pytest.mark.asyncio
    async def test_mixed_absolute_and_relative_keeps_all_qualities(self) -> None:
        # 混合清单里绝对行与相对行同权、全部收齐，且相对行一律 urljoin 绝对化
        # （不得留无 host 的裸相对路径给 ffmpeg）。
        # [历史注] 该续修回归锁：旧判据只要出现 ≥1 条绝对行就丢掉全部相对 .m3u8 行，
        # 上层回退单地址（用户侧「画质下拉只有一项」）。
        m3u8_content = (
            "#EXTM3U\n"
            "#EXT-X-STREAM-INF:BANDWIDTH=1000000\n"
            "https://cdn.example.com/abs.m3u8\n"
            "#EXT-X-STREAM-INF:BANDWIDTH=3000000\n"
            "relative/hd.m3u8\n"
            "#EXT-X-STREAM-INF:BANDWIDTH=5000000\n"
            "/abs-path/uhd.m3u8\n"
            "#EXT-X-ENDLIST"
        )
        with patch("src.spider.async_req", new_callable=AsyncMock, return_value=m3u8_content):
            result = await get_play_url_list("https://origin.example.com/live/master.m3u8")
        assert len(result) == 3
        assert "https://cdn.example.com/abs.m3u8" in result
        assert "https://origin.example.com/live/relative/hd.m3u8" in result
        assert "https://origin.example.com/abs-path/uhd.m3u8" in result

    @pytest.mark.asyncio
    async def test_relative_m3u8_with_query_token_survives_mixed(self) -> None:
        # 混合清单中的带查询串相对行（x.m3u8?token=）既不被丢弃、又保留 query：判据用
        # urlparse().path.endswith(".m3u8")（token 落 query，不影响 path 命中），urljoin 后 token 仍在。
        # [历史注] 该续修回归锁：退回旧的 endswith("m3u8") 字面判据会把该整行丢掉。
        m3u8_content = "#EXTM3U\nhttps://cdn.example.com/abs.m3u8\nseg/x.m3u8?token=abc123\n"
        with patch("src.spider.async_req", new_callable=AsyncMock, return_value=m3u8_content):
            result = await get_play_url_list("https://origin.example.com/live/master.m3u8")
        assert len(result) == 2
        assert "https://origin.example.com/live/seg/x.m3u8?token=abc123" in result

    @pytest.mark.asyncio
    async def test_media_playlist_ts_segments_not_mistaken_for_qualities(self) -> None:
        # 反向见证：主循环新增的相对分支只收 .m3u8 行，必须把分段媒体清单里的裸 .ts 行挡在门外，
        # 否则一个分片会被当成「一档画质」——这条若变红说明相对分支被放宽成「收任意非 # 行」。
        m3u8_content = "#EXTM3U\n#EXT-X-TARGETDURATION:10\n#EXTINF:10,\nseg0.ts\n#EXT-X-ENDLIST\n"
        with patch("src.spider.async_req", new_callable=AsyncMock, return_value=m3u8_content):
            result = await get_play_url_list("https://origin.example.com/live/media.m3u8")
        assert result == []


class TestKuaishouStreamData:
    # get_kuaishou_stream_data：快手直播数据解析。

    @pytest.mark.asyncio
    async def test_network_error_returns_not_live(self) -> None:
        # 网络异常返回 is_live=False.
        with patch("src.spider.async_req", new_callable=AsyncMock, side_effect=Exception("network error")):
            result = await get_kuaishou_stream_data("https://live.kuaishou.com/u/testuser")
            assert result["is_live"] is False

    @pytest.mark.asyncio
    async def test_no_initial_state_returns_not_live(self) -> None:
        # 无 __INITIAL_STATE__ 返回 is_live=False.
        with patch("src.spider.async_req", new_callable=AsyncMock, return_value="<html>no data</html>"):
            result = await get_kuaishou_stream_data("https://live.kuaishou.com/u/testuser")
            assert result["is_live"] is False


class TestHuyaStreamData:
    # get_huya_stream_data：虎牙直播数据解析。

    @pytest.mark.asyncio
    async def test_no_stream_data_returns_empty(self) -> None:
        # 无流数据时装饰器捕获异常，返回空字典。
        with patch("src.spider.async_req", new_callable=AsyncMock, return_value="<html>no stream</html>"):
            result = await get_huya_stream_data("https://www.huya.com/12345")
            assert result == {"is_live": False}

    @pytest.mark.asyncio
    async def test_successful_parse(self) -> None:
        # 正常解析虎牙流数据.
        html = 'stream: {"data":{"gameStreamInfoList":[]}},"iWebDefaultBitRate"'
        with patch("src.spider.async_req", new_callable=AsyncMock, return_value=html):
            result = await get_huya_stream_data("https://www.huya.com/12345")
            assert isinstance(result, dict)


class TestDouyuInfoData:
    # get_douyu_info_data：斗鱼直播间信息解析。

    @pytest.mark.asyncio
    async def test_rid_from_url(self) -> None:
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
    async def test_not_live(self) -> None:
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
    # get_netease_stream_data：网易 CC 直播数据解析。

    @pytest.mark.asyncio
    async def test_no_next_data_returns_empty(self) -> None:
        # 无 __NEXT_DATA__ 时装饰器捕获异常，返回空字典。
        with patch("src.spider.async_req", new_callable=AsyncMock, return_value="<html>no data</html>"):
            result = await get_netease_stream_data("https://cc.163.com/12345")
            assert result == {"is_live": False}

    @pytest.mark.asyncio
    async def test_live_status(self) -> None:
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
    # get_qiandurebo_stream_data：千度热播直播数据解析。

    @pytest.mark.asyncio
    async def test_no_user_data(self) -> None:
        # 无用户数据返回空.
        with patch("src.spider.async_req", new_callable=AsyncMock, return_value="<html>no user</html>"):
            result = await get_qiandurebo_stream_data("https://qiandurebo.com/web/index.php?room=123")
            assert result["is_live"] is False

    @pytest.mark.asyncio
    async def test_live_stream(self) -> None:
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
    # get_bilibili_room_info：B 站直播间信息解析。

    @pytest.mark.asyncio
    async def test_error_returns_empty(self) -> None:
        # 异常返回空 anchor_name.
        with patch("src.spider.async_req", new_callable=AsyncMock, side_effect=Exception("network")):
            result = await get_bilibili_room_info("https://live.bilibili.com/26066074")
            assert result["anchor_name"] == ""
            assert result["live_status"] is False

    @pytest.mark.asyncio
    async def test_successful_parse(self) -> None:
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
    # get_bilibili_stream_data：B 站直播流数据解析。

    @pytest.mark.asyncio
    async def test_play_url_success(self) -> None:
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
            # 精确钉死返回的 gotcha CDN 地址，验证优先选择逻辑而非含糊子串匹配。
            assert result["url"] == "https://d1--cn-gotcha01.bilivideo.com/live/test.flv"

    @pytest.mark.asyncio
    async def test_play_url_empty_durl_fallback(self) -> None:
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
    async def test_empty_durl_list_returns_none(self) -> None:
        # 空 durl 列表返回 None.
        resp = json.dumps({"code": 0, "data": {"durl": []}})
        room_info = json.dumps({"data": {"live_status": 0, "playurl_info": {"playurl": {"stream": []}}}})
        with patch("src.spider.async_req", new_callable=AsyncMock, side_effect=[resp, room_info]):
            result = await get_bilibili_stream_data("https://live.bilibili.com/26066074")
            assert result is None

    @pytest.mark.asyncio
    async def test_url_info_null_host_extra_degrades_to_empty_string(self) -> None:
        # M-03：url_info[0] 的 host/extra 显式 null（风控降级响应形态）时不得以
        # TypeError 被装饰器吞成「未开播」——.get(key, "") 只挡缺键不挡 null。改走 _dig_str 后
        # null 回空串、拼接继续，拼出的残缺地址由选源阶段形态闸判掉，而不是整轮静默归因未开播。
        # 首响应给非 0 code：getRoomPlayInfo 回退只在 playUrl code!=0 时触发（code==0 且 durl
        # 空是「无可用清晰度」直返 None 的既有语义）。
        play_url_resp = json.dumps({"code": -352, "message": "risk"})
        room_info_resp = json.dumps(
            {
                "data": {
                    "live_status": 1,
                    "playurl_info": {
                        "playurl": {
                            "stream": [
                                {
                                    "format": [
                                        {
                                            "codec": [
                                                {
                                                    "current_qn": 250,
                                                    "base_url": "/live_250.m3u8",
                                                    "url_info": [{"host": None, "extra": "?expires=1"}],
                                                }
                                            ]
                                        }
                                    ]
                                }
                            ]
                        }
                    },
                }
            }
        )
        with patch("src.spider.async_req", new_callable=AsyncMock, side_effect=[play_url_resp, room_info_resp]):
            result = await get_bilibili_stream_data("https://live.bilibili.com/26066074")
            assert result is not None
            assert result["url"] == "/live_250.m3u8?expires=1"


class TestAcFunTolerantSortKey:
    # get_acfun_stream_data：representation 档位排序的容错锁。

    @pytest.mark.asyncio
    async def test_missing_bitrate_element_sorts_last_instead_of_silencing_room(self) -> None:
        # M-02：representation 任一元素缺 bitrate（风控降级响应形态）时，排序键
        # 不得让已确认开播的取流整轮被 trace_error_decorator 吞成 {"is_live": False}——
        # 取不到按 0 排到最后（与 B站 _qn_sort_key 同判据），只影响该元素排序。
        inner = {
            "liveAdaptiveManifest": [
                {
                    # adaptationSet 是 dict（representation 直接挂在其下）——_dig 链为
                    # liveAdaptiveManifest[0].adaptationSet.representation
                    "adaptationSet": {
                        "representation": [
                            {"url": "https://pull.acfun.example/flv_low.flv"},
                            {"url": "https://pull.acfun.example/flv_high.flv", "bitrate": 8000},
                        ]
                    },
                }
            ]
        }
        user_resp = json.dumps({"profile": {"name": "AcFun主播", "liveId": 123}})
        play_resp = json.dumps({"data": {"caption": "标题", "videoPlayRes": json.dumps(inner)}})
        with (
            patch("src.spider.async_req", new_callable=AsyncMock, side_effect=[user_resp, play_resp]),
            patch("src.spider.get_acfun_sign_params", new_callable=AsyncMock, return_value=("1", "did", "st")),
        ):
            result = await get_acfun_stream_data("https://live.acfun.cn/live/17912421")
        assert result["is_live"] is True
        urls = [item["url"] for item in cast("list[dict[str, object]]", result["play_url_list"])]
        assert urls[-1] == "https://pull.acfun.example/flv_low.flv"


# ─── src/spider.py 安全收口回归锁 ────────────────────────────────────────────
# 覆盖 docs/worklog/CODE_REVIEW_2026-09-29_2.md 的 / / / / ；
# （Shopee 落地页域族白名单 + 凭据收口 + api_host 闸）单独落在 tests/test_shopee_landing_guard.py。
# 共同约定：一律 monkeypatch.setattr（自动还原、进程内不留桩），替身只打**网络层**与
# 被委托的凭据拉取；脱敏判据、出口一致性、异常类型匹配、anchor_name 类型契约全部走真实代码，
# 否则就是「测试里重新实现被测逻辑」的假绿（AGENTS「测试不得自实现被测逻辑」条）。


def _unwrap(func: object) -> Any:
    # 取 trace_error_decorator 装饰前的原函数（装饰器经 functools.wraps 保留 __wrapped__）。
    # 断言「异常消息原文」必须走这条路——被装饰后异常会被吞成 {"is_live": False}，
    # 消息内容（本组用例的被测对象）根本看不到。
    return cast(Any, getattr(func, "__wrapped__"))


class _LogSpy:
    # sp.logger 替身：按级别收集文本。刻意不重做级别分档/格式化逻辑，
    # 否则「该不该落 warning」这一被测语义就被测试自己实现了。

    def __init__(self) -> None:
        self.msgs: list[tuple[str, str]] = []

    def _record(self, level: str, message: object) -> None:
        self.msgs.append((level, str(message)))

    def debug(self, message: object, *args: object, **kwargs: object) -> None:
        self._record("debug", message)

    def info(self, message: object, *args: object, **kwargs: object) -> None:
        self._record("info", message)

    def success(self, message: object, *args: object, **kwargs: object) -> None:
        self._record("success", message)

    def warning(self, message: object, *args: object, **kwargs: object) -> None:
        self._record("warning", message)

    def error(self, message: object, *args: object, **kwargs: object) -> None:
        self._record("error", message)

    def exception(self, message: object, *args: object, **kwargs: object) -> None:
        # 抖音最外层兜底走 logger.exception 留栈，替身必须同形实现——
        # 只加方法、不重做级别分档（语义仍是被测方决定的）。
        self._record("exception", message)

    def critical(self, message: object, *args: object, **kwargs: object) -> None:
        self._record("critical", message)

    def texts(self, level: str | None = None) -> list[str]:
        if level is None:
            return [text for _lv, text in self.msgs]
        return [text for lv, text in self.msgs if lv == level]


class TestM3RoomPasswordNotInErrorPaths:
    # 私有房密码挂在 ?pwd= 上（pwd 在 utils._SECRET_KEYS 表内），而
    # @trace_error_decorator 落日志时对异常原文零脱敏（见 utils._make_trace_error_guard），
    # 受限房每轮都会把明文密码写进轮转日志。判据是「值确实消失」，不是「调用了脱敏函数」。

    @pytest.mark.asyncio
    async def test_pandatv_needadult_raises_with_masked_room_password(self, monkeypatch: pytest.MonkeyPatch) -> None:
        bodies = [
            '{"bjInfo": {"id": "1", "nick": "N"}, "media": {"title": "在播"}}',
            '{"errorData": {"code": "needAdult"}, "message": "adult only"}',
        ]
        seen: list[str] = []

        async def fake_req(*args: object, **kwargs: object) -> str:
            url = str(kwargs.get("url") or (args[0] if args else ""))
            seen.append(url)
            return bodies[len(seen) - 1]

        monkeypatch.setattr(sp, "async_req", fake_req)
        raw = _unwrap(sp.get_pandatv_stream_data)
        with pytest.raises(RuntimeError) as excinfo:
            await raw("https://www.pandalive.co.kr/play/abc123?pwd=ROOM-SECRET-PW")

        message = str(excinfo.value)
        assert "ROOM-SECRET-PW" not in message, f"房间密码原文进了异常消息: {message}"
        assert "pwd=***" in message, message
        # 文案结构保持不变（调用方与既有断言按原样匹配这句话）
        assert "The live room requires login and is only accessible to adults" in message

    @pytest.mark.asyncio
    async def test_winktv_needadult_raises_with_masked_room_password(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # bj 信息用替身（同文件既有做法），聚焦本函数的 raise 现场
        monkeypatch.setattr(sp, "get_winktv_bj_info", AsyncMock(return_value=("主播-1", True)))
        monkeypatch.setattr(sp, "async_req", AsyncMock(return_value='{"errorData": {"code": "needAdult"}}'))
        raw = _unwrap(sp.get_winktv_stream_data)
        with pytest.raises(RuntimeError) as excinfo:
            await raw("https://www.winktv.co.kr/play/xyz?pwd=ROOM-SECRET-PW")

        message = str(excinfo.value)
        assert "ROOM-SECRET-PW" not in message, f"房间密码原文进了异常消息: {message}"
        assert "pwd=***" in message, message
        assert "The live stream is only accessible to logged-in adults" in message

    @pytest.mark.asyncio
    async def test_twitcasting_malformed_url_masks_query_credentials(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(sp, "async_req", AsyncMock(return_value=""))
        raw = _unwrap(sp.get_twitcasting_stream_url)
        with pytest.raises(RuntimeError) as excinfo:
            await raw("https://twitcasting.tv//?token=RAW-TOKEN")
        assert "RAW-TOKEN" not in str(excinfo.value), str(excinfo.value)
        assert "token=***" in str(excinfo.value)

    @pytest.mark.asyncio
    async def test_weibo_malformed_url_masks_query_credentials(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(sp, "async_req", AsyncMock(return_value=""))
        raw = _unwrap(sp.get_weibo_stream_data)
        with pytest.raises(RuntimeError) as excinfo:
            await raw("https://weibo.com/x?cookie=RAW-COOKIE")
        assert "RAW-COOKIE" not in str(excinfo.value), str(excinfo.value)
        assert "cookie=***" in str(excinfo.value)

    @pytest.mark.asyncio
    async def test_douyin_web_api_failure_logs_masked_url(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # 抖音两处 raise（web/enter 的 inner_list 为空）走的是「异常文本进 logger.error」这条路。
        body = '{"status_code": 0, "data": {"data": [], "user": {"nickname": "N"}}}'
        logger = _LogSpy()
        monkeypatch.setattr(sp, "async_req", AsyncMock(return_value=body))
        monkeypatch.setattr(sp, "logger", logger)

        result = await sp.get_douyin_web_stream_data("https://live.douyin.com/745964462470?ttwid=RAW-TTWID")

        assert result.get("anchor_name") == ""
        joined = "".join(logger.texts())
        assert joined, "抖音兜底路径必须留下归因日志"
        assert "RAW-TTWID" not in joined, f"原始凭据进了日志: {joined}"
        assert "ttwid=***" in joined, joined

    def test_no_unmasked_url_left_in_any_raise(self) -> None:
        # 文件级安全不变量（防「改一处漏 N 处」）：raise 的 f-string 里插值任何 *url* 变量，
        # 都必须包在 mask_credentials(...) 之内。新增平台解析把原始房间地址拼进异常消息即变红。
        source = pathlib.Path(sp.__file__).read_text(encoding="utf-8")
        offenders: list[str] = []
        for node in ast.walk(ast.parse(source)):
            if not isinstance(node, ast.Raise):
                continue
            for sub in ast.walk(node):
                if not isinstance(sub, ast.JoinedStr):
                    continue
                for part in sub.values:
                    if not isinstance(part, ast.FormattedValue):
                        continue
                    names = {n.id for n in ast.walk(part.value) if isinstance(n, ast.Name)}
                    attrs = {
                        c.func.attr
                        for c in ast.walk(part.value)
                        if isinstance(c, ast.Call) and isinstance(c.func, ast.Attribute)
                    }
                    raw = sorted(n for n in names if "url" in n.lower())
                    if raw and "mask_credentials" not in attrs:
                        offenders.append(f"line {node.lineno}: {raw}")
        assert offenders == [], "异常消息里拼了未脱敏的 URL: " + "; ".join(offenders)


class TestM4PopkontvLoginErrorMasking:
    # login_popkontv 是全文件唯一**绕过 async_req** 的生产 httpx 请求，
    # 因此拿不到 async_http 那条「异常文本一律过 mask_credentials」的现成防线。
    # httpx/urllib3 的代理异常原文里内嵌含 user:pass@ 的代理 URL。

    @pytest.mark.asyncio
    async def test_proxy_credentials_masked_and_type_name_present(self, monkeypatch: pytest.MonkeyPatch) -> None:
        boom = httpx.ConnectError("Cannot connect to proxy http://proxyuser:SECRETPW@proxy.internal:3128")

        class _BoomClient:
            def __init__(self, *args: object, **kwargs: object) -> None:
                pass

            async def __aenter__(self) -> object:
                return self

            async def __aexit__(self, *exc_info: object) -> bool:
                return False

            async def post(self, *args: object, **kwargs: object) -> object:
                raise boom

        # 替身装进 spider 命名空间（不改 httpx 模块本体，见 AGENTS「patch stdlib/三方模块本体」条）：
        # vars(httpx) 浅拷贝保留 HTTPStatusError 等异常类，except 子句照常可用。
        shim = types.SimpleNamespace(**{k: v for k, v in vars(httpx).items() if not k.startswith("__")})
        shim.AsyncClient = _BoomClient
        logger = _LogSpy()
        monkeypatch.setattr(sp, "httpx", cast(Any, shim))
        monkeypatch.setattr(sp, "logger", logger)

        # 走 __wrapped__ 原函数：login_popkontv 是 _or_none 装饰，异常会被吞成 None，
        # 那样就断言不到「异常仍向上抛」这半边契约（脱敏的是日志，抛出语义必须保持）。
        raw = _unwrap(sp.login_popkontv)
        with pytest.raises(httpx.ConnectError):
            await raw("u", "p", proxy_addr="http://proxyuser:SECRETPW@proxy.internal:3128")

        joined = "".join(logger.texts())
        assert joined, "登录异常必须落日志"
        assert "SECRETPW" not in joined, f"代理口令原文进了日志: {joined}"
        assert "***@" in joined, joined
        # AGENTS「异常日志必须带异常类型与上下文」：Windows 下超时类异常的 str(e) 可能是空串
        assert "ConnectError" in joined, joined


class TestM12ProxyCredentialMaskedInPlatformErrorLogs:
    # 续修：get_flextv_stream_data / login_twitcasting 的 except 分支把 str(e) 直接拼进
    # logger.error，而 httpx/urllib 的连接·代理异常原文内嵌含 user:pass@ 的代理 URL，logger.error
    # 直落轮转日志（logs/ 多份＝凭据长期落盘）。判据同 TestM3RoomPasswordNotInErrorPaths：值确实消失。
    # 两处刻意保留原字符串拼接形态与原 msgid 文本，故脱敏后仍能在日志里看到整句话。
    # [2026-10-29 更正] 两处拼接已迁移 i18n.tr 常量模板（模板文本未变，conftest 恒等钉定下断言不受影响）。

    _PROXY_BOOM_MSG = "Cannot connect to proxy http://proxyuser:SECRETPW@proxy.internal:3128"

    @pytest.mark.asyncio
    async def test_flextv_stream_error_masks_proxy_password(self, monkeypatch: pytest.MonkeyPatch) -> None:
        logger = _LogSpy()
        monkeypatch.setattr(sp, "async_req", AsyncMock(side_effect=httpx.ConnectError(self._PROXY_BOOM_MSG)))
        monkeypatch.setattr(sp, "logger", logger)

        # 内部 except 捕获后返回 result（is_live=False）、不外抛 → 走真实（已装饰）调用路径即可。
        result = await sp.get_flextv_stream_data("https://www.ttinglive.com/somechannel/live")
        assert result["is_live"] is False, result

        joined = "".join(logger.texts())
        assert "Failed to retrieve data from FlexTV live room" in joined, joined
        assert "SECRETPW" not in joined, f"代理口令原文进了日志: {joined}"
        assert "proxyuser" not in joined, f"代理用户名原文进了日志: {joined}"
        assert "***@proxy.internal:3128" in joined, joined

    @pytest.mark.asyncio
    async def test_twitcasting_login_error_masks_proxy_password(self, monkeypatch: pytest.MonkeyPatch) -> None:
        logger = _LogSpy()
        calls: list[int] = []

        async def fake_req(*args: object, **kwargs: object) -> object:
            calls.append(1)
            if len(calls) == 1:
                # 首页返回含 cs_session_id 的表单，令登录链路走到第二次（真正会抛）请求。
                return '<input type="hidden" name="cs_session_id" value="SID">'
            raise httpx.ConnectError(self._PROXY_BOOM_MSG)

        monkeypatch.setattr(sp, "async_req", fake_req)
        monkeypatch.setattr(sp, "logger", logger)

        # 第二次请求的异常被内部 except 捕获、脱敏后落日志、返回 None（_or_none 装饰器不触发）。
        result = await sp.login_twitcasting("twitter", "user", "pass")
        assert result is None, result
        assert len(calls) == 2, calls

        joined = "".join(logger.texts())
        assert "TwitCasting login error" in joined, joined
        assert "SECRETPW" not in joined, f"代理口令原文进了日志: {joined}"
        assert "proxyuser" not in joined, f"代理用户名原文进了日志: {joined}"
        assert "***@proxy.internal:3128" in joined, joined


class TestM8ProxyScopedCredentialCaches:
    # 进程级凭据快路须同判 proxy——只判「非空 + TTL」时，代理 A 取到的设备标识会在有效期内
    # 被代理 B 的房间复用（同 src/ttwid.py 已修形态）。

    def test_kuaishou_did_fast_path_requires_same_proxy(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(sp, "_cached_kuaishou_did", "did=A")
        monkeypatch.setattr(sp, "_cached_kuaishou_did_ts", time.monotonic())
        monkeypatch.setattr(sp, "_cached_kuaishou_did_proxy", "http://a:8080")

        assert sp._take_cached_kuaishou_did("http://a:8080") == "did=A"
        assert sp._take_cached_kuaishou_did("http://b:8080") == ""
        assert sp._take_cached_kuaishou_did(None) == ""

    def test_kuaishou_did_fast_path_keeps_ttl_semantics(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # 两条既有语义不得被本轮改动带走：陈旧即弃、外部注入（ts==0）按有效。
        monkeypatch.setattr(sp, "_cached_kuaishou_did", "did=A")
        monkeypatch.setattr(sp, "_cached_kuaishou_did_proxy", "")
        monkeypatch.setattr(sp, "_cached_kuaishou_did_ts", time.monotonic() - 4000.0)
        assert sp._take_cached_kuaishou_did(None) == ""
        monkeypatch.setattr(sp, "_cached_kuaishou_did_ts", 0.0)
        assert sp._take_cached_kuaishou_did(None) == "did=A"

    @pytest.mark.asyncio
    async def test_kuaishou_did_refetched_for_other_proxy(self, monkeypatch: pytest.MonkeyPatch) -> None:
        used: list[object] = []

        async def fake_fetch_cookies(**kwargs: object) -> dict[str, str]:
            used.append(kwargs.get("proxy_addr"))
            return {"did": "B", "didv": ""}

        monkeypatch.setattr(sp, "_cached_kuaishou_did", "did=A")
        monkeypatch.setattr(sp, "_cached_kuaishou_did_ts", time.monotonic())
        monkeypatch.setattr(sp, "_cached_kuaishou_did_proxy", "http://a:8080")
        monkeypatch.setattr(sp, "_cache_fetch_cookies", fake_fetch_cookies)

        got = await sp._ensure_kuaishou_did("http://b:8080")

        assert got == "did=B", got
        assert used == ["http://b:8080"], used

    @pytest.mark.asyncio
    async def test_kuaishou_did_failure_does_not_leak_other_proxy_value(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # 失败分支是第二条泄漏路径：本轮没取到新值时只能回空串，不得把全局（属别出口）的值直接递出去。
        async def dead_fetch(**kwargs: object) -> dict[str, str]:
            return {}

        monkeypatch.setattr(sp, "_cached_kuaishou_did", "did=A")
        monkeypatch.setattr(sp, "_cached_kuaishou_did_ts", time.monotonic())
        monkeypatch.setattr(sp, "_cached_kuaishou_did_proxy", "http://a:8080")
        monkeypatch.setattr(sp, "_cache_fetch_cookies", dead_fetch)

        assert await sp._ensure_kuaishou_did("http://b:8080") == ""

    def test_bili_buvid_fast_path_requires_same_proxy(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(sp, "_bili_buvid_cached", "BUVID-A")
        monkeypatch.setattr(sp, "_bili_buvid_cached_proxy", "http://a:8080")

        assert sp._take_cached_bili_buvid("http://a:8080") == "BUVID-A"
        assert sp._take_cached_bili_buvid("http://b:8080") == ""
        assert sp._take_cached_bili_buvid(None) == ""

    @pytest.mark.asyncio
    async def test_bili_buvid_refetched_for_other_proxy(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # 走真实 get_bilibili_danmaku_info：代理 B 的房间必须重新取 buvid，而不是拿代理 A 的
        # 设备标识进房（B站弹幕服务器按 AUTH 判设备标识，串用即软拒绝、弹幕静默收不到）。
        nav_resp = (
            '{"code":0,"data":{"wbi_img":{"img_url":"https://i0.hdslb.com/bfs/wbi/'
            "1234567890abcdef1234567890abcdef.png"
            '","sub_url":"https://i0.hdslb.com/bfs/wbi/'
            "fedcba0987654321fedcba0987654321.png"
            '"}}}'
        )
        danmu_resp = (
            '{"code":0,"data":{"token":"TOKEN123","host_list":'
            '[{"host":"broadcastlv.chat.bilibili.com","port":2243,"ws_port":2244,"wss_port":443}]}}'
        )
        spi_hits: list[object] = []

        async def fake_req(*args: object, **kwargs: object) -> str:
            url = str(kwargs.get("url") or (args[0] if args else ""))
            if "finger/spi" in url:
                spi_hits.append(kwargs.get("proxy_addr"))
                return '{"code":0,"data":{"b_3":"BUVID-B"}}'
            if "room_init" in url:
                return '{"code":0,"data":{"room_id":763679,"uid":12345}}'
            if "/nav" in url:
                return nav_resp
            if "getDanmuInfo" in url:
                return danmu_resp
            return ""

        monkeypatch.setattr(sp, "_bili_buvid_cached", "BUVID-A")
        monkeypatch.setattr(sp, "_bili_buvid_cached_proxy", "http://a:8080")
        monkeypatch.setattr(sp, "async_req", fake_req)

        info = await sp.get_bilibili_danmaku_info("https://live.bilibili.com/462", proxy_addr="http://b:8080")

        assert info is not None
        assert info["buvid"] == "BUVID-B", info
        assert spi_hits == ["http://b:8080"], spi_hits


class TestM9AnchorNameNeverNone:
    # dict.get("nickname")/.get("nick")/.get("name","") 只挡「键缺失」，平台显式返回 null
    # 时得到 None 入结果 dict，下游 clean_name(None) 当场 AttributeError（stream_select.py），
    # 整轮解析被兜成「获取失败」。文件内新代码统一 _dig_str，这几处是漏网点。

    @pytest.mark.asyncio
    async def test_douyin_web_null_nickname_yields_empty_string(self, monkeypatch: pytest.MonkeyPatch) -> None:
        body = '{"status_code": 0, "data": {"data": [{"status": 4, "room_id": 1}], "user": {"nickname": null}}}'
        monkeypatch.setattr(sp, "async_req", AsyncMock(return_value=body))
        monkeypatch.setattr(sp, "logger", _LogSpy())

        result = await sp.get_douyin_web_stream_data("https://live.douyin.com/745964462470", cookies="c=1")

        assert result.get("anchor_name") == "", result
        assert isinstance(result.get("anchor_name"), str)

    @pytest.mark.asyncio
    async def test_kuaishou_web_null_author_name_yields_empty_string(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # 快手把状态塞在 window.__INITIAL_STATE__ 内联串里：第一个正则要求内联串后面紧跟
        # `;(function(){var s;`，第二个正则在**捕获到的内联串内部**再按 `,"gameInfo"` 截断
        # （页面把整段状态截到这里），截出的片段补 1 个右花括号后才是 play_list。
        inline = '{"liveStream": {"hls": "http://p/1.m3u8"}, "author": {"name": null},"gameInfo": {}}'
        html = f"<html><script>window.__INITIAL_STATE__={inline};(function(){{var s;</script></html>"
        monkeypatch.setattr(sp, "async_req", AsyncMock(return_value=html))
        monkeypatch.setattr(sp, "logger", _LogSpy())

        result = await sp.get_kuaishou_stream_data("https://live.kuaishou.com/u/testuser", cookies="c=1")

        assert result.get("anchor_name") == "", result
        assert isinstance(result.get("anchor_name"), str)

    @pytest.mark.asyncio
    async def test_huya_app_null_nick_yields_empty_string(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # 房间号必须是纯数字尾段（字母号会先进反查分支、非数字直接早抛，见上文）。
        body = '{"data": {"profileInfo": {"nick": null}, "realLiveStatus": "OFF"}}'
        monkeypatch.setattr(sp, "async_req", AsyncMock(return_value=body))
        monkeypatch.setattr(sp, "logger", _LogSpy())

        result = await sp.get_huya_app_stream_url("https://www.huya.com/6030242", cookies="c=1")

        assert result.get("anchor_name") == "", result
        assert isinstance(result.get("anchor_name"), str)

    @pytest.mark.asyncio
    async def test_netease_null_sharefile_yields_empty_string(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # is_live 已置真、m3u8_url 却是 None 时，上游 `n.get("m3u8_url", "")` 仍拿到 None
        # （键在、值为 null，缺省不生效），record_url 跟着变 None。
        next_data = {
            "props": {
                "pageProps": {
                    "roomInfoInitData": {
                        "live": {
                            "status": 1,
                            "nickname": "网易主播",
                            "title": "测试直播",
                            "quickplay": None,
                            "sharefile": None,
                        },
                        "nickname": "网易主播",
                    }
                }
            }
        }
        html = (
            '<script id="__NEXT_DATA__" type="application/json" crossorigin="anonymous">'
            + json.dumps(next_data)
            + "</script></body>"
        )
        monkeypatch.setattr(sp, "async_req", AsyncMock(return_value=html))
        monkeypatch.setattr(sp, "logger", _LogSpy())

        result = await sp.get_netease_stream_data("https://cc.163.com/12345", cookies="c=1")

        assert result["is_live"] is True
        assert result["m3u8_url"] == "", result


class TestTwitCastingParseFailureLoginFallback:
    # （src/spider.py 的 except AttributeError, ValueError 分支；类名被该处注释引用）：
    # get_data 在四个正则任一未命中时**显式** raise ValueError("Failed to parse page data")，
    # 受限房的登录回退须一并接住 ValueError——只接 AttributeError 时「解析失败→登录重试」是死分支，
    # 页面改版/成人房一律判未开播、登录态永远用不上。用例走「首次 ValueError → 登录 → 二次成功」
    # 证明捕获真被走到：把 ValueError 从 except 删掉即变红（装饰器会吞成 {"is_live": False}，login 一次也不调）。

    _GOOD_HTML = (
        # 四个正则的共同现场（模式串见 src/spider.py::get_twitcasting_stream_url 的 get_data）：
        # <title> 段要求 `主播名 (@账号)  的直播 - Twit`（括号 + 两个空格），
        # twitter:title 与 data-is-onlive 之后都必须紧跟**换行 + 空白**再接下一个属性。
        "<html><head><title>主播 (@tcuser)  的直播 - Twit</title>\n"
        '<meta name="twitter:title" content="直播标题">\n'
        '      <meta name="x" content="y">\n'
        '      <div data-is-onlive="false"\n'
        '      data-view-mode="live">\n'
        '      <div data-movie-id="998877" data-audience-id="1">\n'
        "</div></head></html>"
    )

    @pytest.mark.asyncio
    async def test_value_error_triggers_login_and_retry(self, monkeypatch: pytest.MonkeyPatch) -> None:
        sent: list[dict[str, Any]] = []

        async def fake_req(*args: object, **kwargs: object) -> str:
            # kwargs 的值类型是 object（打桩签名与生产 async_req 的宽签名对齐），此处要进
            # dict[str, str] 的 sent 列表，必须显式 cast 收窄——不收窄则 mypy 在 warn_return_any
            # 之外还会报 dict(object) 无匹配重载，而 Any 会顺带关掉整条属性链的检查。
            headers = cast(dict[str, str], kwargs.get("headers") or {})
            sent.append({"url": str(kwargs.get("url") or (args[0] if args else "")), "headers": dict(headers)})
            # 第一页受限（正则全失配 → ValueError），登录后的第二页才解析得出
            return "" if len(sent) == 1 else self._GOOD_HTML

        login = AsyncMock(return_value="TC_COOKIE=1")
        monkeypatch.setattr(sp, "async_req", fake_req)
        monkeypatch.setattr(sp, "login_twitcasting", login)
        monkeypatch.setattr(sp, "logger", _LogSpy())

        result = await sp.get_twitcasting_stream_url("https://twitcasting.tv/tcuser")

        assert login.await_count == 1, f"解析失败后未触发登录回退: {result}"
        assert len(sent) == 2, sent
        assert sent[1]["headers"].get("Cookie") == "TC_COOKIE=1", sent
        assert result["anchor_name"] == "主播-tcuser-998877", result

    @pytest.mark.asyncio
    async def test_login_failure_still_raises_runtime_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # 回退分支的另一半：登录拿不到 cookie 时仍按既有语义抛 RuntimeError（不得静默判未开播）。
        async def fake_req(*args: object, **kwargs: object) -> str:
            return ""

        monkeypatch.setattr(sp, "async_req", fake_req)
        monkeypatch.setattr(sp, "login_twitcasting", AsyncMock(return_value=None))
        monkeypatch.setattr(sp, "logger", _LogSpy())

        raw = _unwrap(sp.get_twitcasting_stream_url)
        with pytest.raises(RuntimeError):
            await raw("https://twitcasting.tv/tcuser")


class TestL09KuaishouEidExtraction:
    # eid 必须取 urlsplit 后的「/u/ 路径段」（与 extract_douyu_room_id 同口径）——query/fragment
    # 不得进 eid，否则 byUser 只回「房间不存在」这类误导性结果、且 anchor_name 为空会再走一遍网页路径。
    # [历史注] 旧实现 `url.split("/u/")[1].strip()` 取的是 /u/ 之后的整串。

    @pytest.mark.parametrize(
        ("url", "expected"),
        [
            ("https://live.kuaishou.com/u/3gxyh7gnanb7fdh", "3gxyh7gnanb7fdh"),
            # 分享链接最常见的形态：query 不得进 eid
            ("https://live.kuaishou.com/u/3gxyh7gnanb7fdh?from=live&shareToken=ST.foo", "3gxyh7gnanb7fdh"),
            # 尾斜杠 / fragment 同样不得留下（斗鱼同型事故：房间号带尾斜杠 → 接口拿不到 room）
            ("https://live.kuaishou.com/u/3gxyh7gnanb7fdh/", "3gxyh7gnanb7fdh"),
            ("https://live.kuaishou.com/u/3gxyh7gnanb7fdh#comment", "3gxyh7gnanb7fdh"),
            # 无 scheme 形态（用户手填常见）：补 https:// 后首段仍是 u，而不是主机名
            ("live.kuaishou.com/u/3gxyh7gnanb7fdh?from=wc", "3gxyh7gnanb7fdh"),
            # 形态不合规一律空串（调用方据此报错并回退网页路径），不得把主机名/空段当 eid
            ("https://live.kuaishou.com/profile/abc", ""),
            ("https://live.kuaishou.com/u/", ""),
            ("https://live.kuaishou.com/u", ""),
            ("http://[oops/u/1", ""),
        ],
    )
    def test_eid_is_the_path_segment_after_u(self, url: str, expected: str) -> None:
        assert extract_kuaishou_eid(url) == expected

    @pytest.mark.asyncio
    async def test_share_link_sends_clean_eid_to_backup_api(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # 行为锁（不是只钉 helper）：真正发往 byUser 接口的 data["eid"] 必须是干净那一段。
        # 整串 split 的旧形态在这里会得到 "3gxyh7gnanb7fdh?from=live&shareToken=x" → 本条转红。
        sent: list[dict[str, object]] = []

        async def fake_req(*args: object, **kwargs: object) -> str:
            sent.append({"url": str(kwargs.get("url") or (args[0] if args else "")), "data": kwargs.get("data")})
            return '{"code":0,"data":{"liveStream":{}}}'

        monkeypatch.setattr(sp, "async_req", fake_req)
        monkeypatch.setattr(sp, "_ensure_kuaishou_did", AsyncMock(return_value="did=abc"))
        fallback = AsyncMock(return_value={"is_live": False})
        monkeypatch.setattr(sp, "get_kuaishou_stream_data", fallback)

        result = await sp.get_kuaishou_stream_data2(
            "https://live.kuaishou.com/u/3gxyh7gnanb7fdh?from=live&shareToken=x"
        )

        assert len(sent) == 1, sent
        data = cast(dict[str, object], sent[0]["data"])
        assert data["eid"] == "3gxyh7gnanb7fdh", data
        # liveStream 里没有 user → anchor_name 为空 → 按既有语义回退网页路径解析一次
        assert fallback.await_count == 1, result


class TestL08BiliBuvidNeverLoggedInClear:
    # B 站 buvid3 是设备级标识、弹幕 AUTH 的凭据成分，而 logs/ 按大小轮转保留多份
    # （AGENTS「凭据不入轮转日志」红线），故 _fetch_buvid 的两条 debug（cookie 提取、首页 Set-Cookie
    # 兜底）只留归因形态。判据按 AGENTS 关键约定 #11：「值确实消失」，不是「调用了 mask_credentials」；
    # 同时反向钉住「凭据照旧按原值取用」——只改日志形态，进房/AUTH 的语义一律不许动。

    _COOKIE_BUVID = "XYAA11223344556677889900AABBCCDD35187infoc"
    _HOME_BUVID = "BBBB00001111222233334444555566667777infoc"

    @staticmethod
    def _fake_req(spi_body: str) -> Any:
        # 只造 room_init / nav / spi / getDanmuInfo 四条响应体，不做任何 buvid 判定
        # （判定与被测的日志形态都在真实 get_bilibili_danmaku_info 里跑）
        nav_resp = (
            '{"code":0,"data":{"wbi_img":{"img_url":"https://i0.hdslb.com/bfs/wbi/'
            "1234567890abcdef1234567890abcdef.png"
            '","sub_url":"https://i0.hdslb.com/bfs/wbi/'
            "fedcba0987654321fedcba0987654321.png"
            '"}}}'
        )
        danmu_resp = (
            '{"code":0,"data":{"token":"TOKEN123","host_list":'
            '[{"host":"broadcastlv.chat.bilibili.com","port":2243,"ws_port":2244,"wss_port":443}]}}'
        )

        async def fake_req(*args: object, **kwargs: object) -> str:
            url = str(kwargs.get("url") or (args[0] if args else ""))
            if "finger/spi" in url:
                return spi_body
            if "room_init" in url:
                return '{"code":0,"data":{"room_id":763679,"uid":12345}}'
            if "/nav" in url:
                return nav_resp
            if "getDanmuInfo" in url:
                return danmu_resp
            return ""

        return fake_req

    @pytest.fixture(autouse=True)
    def _empty_buvid_cache(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # 进程级设备标识缓存跨用例存活会让获取链整段短路（快路命中即不打任何日志），
        # 于是三条断言全部空转。逐用例清成「未缓存」再跑。
        monkeypatch.setattr(sp, "_bili_buvid_cached", "")
        monkeypatch.setattr(sp, "_bili_buvid_cached_proxy", "")
        monkeypatch.setattr(sp, "_bili_buvid_is_fallback", False)

    def test_log_form_keeps_attribution_without_the_value(self) -> None:
        # 归因面必须留下（「是哪一枚、多长」是排查 AUTH 被软拒绝、出口串用的唯一线索），
        # 但除 4 位前缀外的主体不得出现在日志形态里。
        form = sp._buvid_log_form(self._COOKIE_BUVID)
        assert form == "XYAA len=42", form
        assert self._COOKIE_BUVID[4:] not in form
        assert sp._buvid_log_form("") == ""

    @pytest.mark.asyncio
    async def test_cookie_buvid_debug_line_has_no_plaintext(self, monkeypatch: pytest.MonkeyPatch) -> None:
        spy = _LogSpy()
        monkeypatch.setattr(sp, "logger", spy)
        monkeypatch.setattr(sp, "async_req", self._fake_req('{"code":0,"data":{"b_3":"SHOULD-NOT-BE-USED"}}'))

        info = await sp.get_bilibili_danmaku_info(
            "https://live.bilibili.com/462", cookies=f"buvid3={self._COOKIE_BUVID};SESSDATA=rawsess"
        )

        assert info is not None and info["buvid"] == self._COOKIE_BUVID, info
        joined = "".join(spy.texts())
        assert self._COOKIE_BUVID not in joined, f"cookie 里的 buvid3 整值仍进日志: {joined}"
        assert "rawsess" not in joined, f"整串 Cookie 仍进日志: {joined}"
        assert "XYAA len=42" in joined, f"脱敏把归因面一起抹掉了: {joined}"

    @pytest.mark.asyncio
    async def test_home_set_cookie_buvid_debug_line_has_no_plaintext(self, monkeypatch: pytest.MonkeyPatch) -> None:
        secret = self._HOME_BUVID

        async def _no_sleep(_delay: float) -> None:
            return None

        # 打桩口径（AGENTS「替身禁止裸赋值共享模块属性」）：asyncio 是全进程唯一的 stdlib 模块本体，
        # 直接把 asyncio.sleep 换成 no-op 会波及同窗口内其它协程/后台线程 → 浅拷贝成 shim 只覆盖
        # sleep 一个属性，再挂到被测模块的命名空间。
        shim = types.SimpleNamespace(**vars(asyncio))
        shim.sleep = _no_sleep
        monkeypatch.setattr(sp, "asyncio", shim)

        async def fake_home_cookies(*args: object, **kwargs: object) -> dict[str, str]:
            return {"buvid3": secret}

        monkeypatch.setattr(sp, "_cache_fetch_cookies", fake_home_cookies)
        spy = _LogSpy()
        monkeypatch.setattr(sp, "logger", spy)
        # spi 两跳皆空（风控 200+空 body 的主形态）→ 落到首页 Set-Cookie 兜底那条 debug
        monkeypatch.setattr(sp, "async_req", self._fake_req('{"code":0,"data":{}}'))

        info = await sp.get_bilibili_danmaku_info("https://live.bilibili.com/462")

        assert info is not None and info["buvid"] == secret, info
        joined = "".join(spy.texts())
        assert secret not in joined, f"首页 Set-Cookie 取到的 buvid3 整值仍进日志: {joined}"
        assert "BBBB len=41" in joined, f"兜底来源的归因面被一起抹掉了: {joined}"
