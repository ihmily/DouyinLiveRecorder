# Tests for src/spider.py - batch platform function tests for coverage improvement.

import json
import urllib.parse
from typing import cast
from unittest.mock import AsyncMock, patch

import pytest

from src.spider import (
    _ensure_twitch_client_id,
    _generate_twitch_play_session_id,
    get_6room_stream_url,
    get_17live_stream_url,
    get_acfun_sign_params,
    get_acfun_stream_data,
    get_baidu_stream_data,
    get_bigo_stream_url,
    get_bilibili_room_info,
    get_bilibili_room_info_h5,
    get_bilibili_stream_data,
    get_blued_stream_url,
    get_changliao_stream_url,
    get_chzzk_stream_data,
    get_douyu_info_data,
    get_douyu_stream_data,
    get_faceit_stream_data,
    get_flextv_stream_url,
    get_huajiao_stream_url,
    get_huajiao_stream_url_app,
    get_huajiao_user_info,
    get_huya_app_stream_url,
    get_jd_stream_url,
    get_kuaishou_stream_data2,
    get_kugou_stream_url,
    get_laixiu_stream_url,
    get_langlive_stream_url,
    get_lianjie_stream_url,
    get_liuxing_stream_url,
    get_looklive_secret_data,
    get_maoerfm_stream_url,
    get_netease_stream_data,
    get_pandatv_stream_data,
    get_picarto_stream_url,
    get_pplive_stream_url,
    get_showroom_stream_data,
    get_soop_headers,
    get_sooplive_cdn_url,
    get_sooplive_stream_data,
    get_sooplive_tk,
    get_tiktok_stream_data,
    get_token_js,
    get_vvxqiu_stream_url,
    get_weibo_stream_data,
    get_winktv_bj_info,
    get_winktv_stream_data,
    get_xhs_stream_url,
    get_yinbo_stream_url,
    get_yingke_stream_url,
    get_youtube_stream_url,
    get_yy_stream_data,
    get_zhihu_stream_url,
    login_flextv,
    login_sooplive,
)


class TestGenerateTwitchPlaySessionId:
    # Test _generate_twitch_play_session_id.

    def test_returns_32_char_string(self) -> None:
        result = _generate_twitch_play_session_id()
        assert len(result) == 32
        assert result == result.lower()  # should be lowercase

    def test_unique_per_call(self) -> None:
        results = {_generate_twitch_play_session_id() for _ in range(10)}
        assert len(results) > 1  # extremely unlikely all 10 are the same


class TestEnsureTwitchClientId:
    # Test _ensure_twitch_client_id.

    @pytest.mark.asyncio
    async def test_fetches_from_html(self) -> None:
        html = '<script>var config = {"Client-ID": "abcdef12345678901234567890ab"};</script>'
        with (
            patch("src.spider.async_req", new_callable=AsyncMock, return_value=html),
            patch("src.spider._cached_twitch_client_id", ""),
        ):
            import src.spider as spider_mod

            old = spider_mod._cached_twitch_client_id
            spider_mod._cached_twitch_client_id = ""
            try:
                result = await _ensure_twitch_client_id()
                assert result == "abcdef12345678901234567890ab"
            finally:
                spider_mod._cached_twitch_client_id = old

    @pytest.mark.asyncio
    async def test_returns_cached(self) -> None:
        import src.spider as spider_mod

        old = spider_mod._cached_twitch_client_id
        spider_mod._cached_twitch_client_id = "cached_id_value_12345678"
        try:
            result = await _ensure_twitch_client_id()
            assert result == "cached_id_value_12345678"
        finally:
            spider_mod._cached_twitch_client_id = old

    @pytest.mark.asyncio
    async def test_network_error_returns_empty(self) -> None:
        import src.spider as spider_mod

        old = spider_mod._cached_twitch_client_id
        spider_mod._cached_twitch_client_id = ""
        try:
            with patch("src.spider.async_req", new_callable=AsyncMock, side_effect=Exception("timeout")):
                result = await _ensure_twitch_client_id()
                assert result == ""
        finally:
            spider_mod._cached_twitch_client_id = old


class TestTiktokStreamData:
    # Test get_tiktok_stream_data.

    @pytest.mark.asyncio
    async def test_successful_parse(self) -> None:
        html = '<script id="SIGI_STATE" type="application/json">{"room":{"status":2}}</script>'
        with (
            patch("src.spider.async_req", new_callable=AsyncMock, return_value=html),
            patch("src.spider.asyncio.sleep", new_callable=AsyncMock),
        ):
            result = await get_tiktok_stream_data("https://www.tiktok.com/@test/live")
            assert result == {"room": {"status": 2}}

    @pytest.mark.asyncio
    async def test_discontinued_returns_empty(self) -> None:
        html = "<p>\nWe regret to inform you that we have discontinued operating TikTok in this region.\n</p>"
        with (
            patch("src.spider.async_req", new_callable=AsyncMock, return_value=html),
            patch("src.spider.asyncio.sleep", new_callable=AsyncMock),
        ):
            result = await get_tiktok_stream_data("https://www.tiktok.com/@test/live")
            assert result == {"is_live": False}

    @pytest.mark.asyncio
    async def test_retry_exhaustion(self) -> None:
        with (
            patch("src.spider.async_req", new_callable=AsyncMock, return_value="UNEXPECTED_EOF_WHILE_READING"),
            patch("src.spider.asyncio.sleep", new_callable=AsyncMock),
        ):
            result = await get_tiktok_stream_data("https://www.tiktok.com/@test/live")
            assert result == {"is_live": False}


class TestYYStreamData:
    # Test get_yy_stream_data.

    @pytest.mark.asyncio
    async def test_no_anchor_name_returns_empty(self) -> None:
        # 无主播名时装饰器捕获异常，返回 {is_live: False}.
        with patch("src.spider.async_req", new_callable=AsyncMock, return_value="<html>no data</html>"):
            result = await get_yy_stream_data("https://www.yy.com/12345")
            assert result == {"is_live": False}

    @pytest.mark.asyncio
    async def test_successful_parse(self) -> None:
        html = 'nick: "YY主播",\n  logo'
        with patch("src.spider.async_req", new_callable=AsyncMock, return_value=html):
            result = await get_yy_stream_data("https://www.yy.com/12345")
            assert isinstance(result, dict)


class TestPandatvStreamData:
    # Test get_pandatv_stream_data.

    @pytest.mark.asyncio
    async def test_not_live(self) -> None:
        bj_info_response = json.dumps({"bjInfo": {"id": "user1", "nick": "Panda主播"}, "message": "ok"})
        with patch("src.spider.async_req", new_callable=AsyncMock, return_value=bj_info_response):
            result = await get_pandatv_stream_data("https://www.pandalive.co.kr/user1")
            assert result["anchor_name"] == "Panda主播-user1"
            assert result["is_live"] is False

    @pytest.mark.asyncio
    async def test_no_bj_info_raises(self) -> None:
        response = json.dumps({"message": "User not found"})
        with patch("src.spider.async_req", new_callable=AsyncMock, return_value=response):
            result = await get_pandatv_stream_data("https://www.pandalive.co.kr/unknown")
            # decorator catches RuntimeError → returns {is_live: False}
            assert result == {"is_live": False}


class TestBaiduStreamData:
    # Test get_baidu_stream_data.

    @pytest.mark.asyncio
    async def test_empty_data_returns_not_live(self) -> None:
        api_response = json.dumps({"data": {}})
        with patch("src.spider.async_req", new_callable=AsyncMock, return_value=api_response):
            result = await get_baidu_stream_data("https://live.baidu.com?room_id=12345&other=x")
            assert result["anchor_name"] == ""
            assert result["is_live"] is False

    @pytest.mark.asyncio
    async def test_no_room_id_raises(self) -> None:
        with patch("src.spider.async_req", new_callable=AsyncMock):
            result = await get_baidu_stream_data("https://live.baidu.com/no_room_id")
            assert result == {"is_live": False}


class TestWeiboStreamData:
    # Test get_weibo_stream_data.

    @pytest.mark.asyncio
    async def test_show_url_not_live(self) -> None:
        live_response = json.dumps(
            {
                "data": {
                    "user_info": {"name": "微博主播"},
                    "item": {"status": 0, "desc": "", "stream_info": {"pull": {}}},
                }
            }
        )
        with patch("src.spider.async_req", new_callable=AsyncMock, return_value=live_response):
            result = await get_weibo_stream_data("https://weibo.com/l/show/12345")
            assert result["anchor_name"] == "微博主播"
            assert result["is_live"] is False

    @pytest.mark.asyncio
    async def test_uid_url_finds_room(self) -> None:
        feed_response = json.dumps(
            {
                "data": {
                    "list": [
                        {"page_info": {"object_type": "live", "object_id": "room999"}},
                    ]
                }
            }
        )
        live_response = json.dumps(
            {
                "data": {
                    "user_info": {"name": "主播"},
                    "item": {
                        "status": 1,
                        "desc": "直播中",
                        "stream_info": {
                            "pull": {
                                "live_origin_hls_url": "https://hdl.weibo.com/live.m3u8",
                                "live_origin_flv_url": "https://hdl.weibo.com/live.flv",
                            }
                        },
                    },
                }
            }
        )
        with patch("src.spider.async_req", new_callable=AsyncMock, side_effect=[feed_response, live_response]):
            result = await get_weibo_stream_data("https://weibo.com/u/5885340893")
            assert result["is_live"] is True
            assert result["anchor_name"] == "主播"


class TestChzzkStreamData:
    # Test get_chzzk_stream_data.

    @pytest.mark.asyncio
    async def test_not_live(self) -> None:
        api_response = json.dumps(
            {
                "content": {
                    "channel": {"channelName": "CHZZK主播"},
                    "status": "CLOSED",
                    "livePlaybackJson": None,
                }
            }
        )
        with patch("src.spider.async_req", new_callable=AsyncMock, return_value=api_response):
            result = await get_chzzk_stream_data("https://chzzk.naver.com/live/abc123")
            assert result["anchor_name"] == "CHZZK主播"
            assert result["is_live"] is False

    @pytest.mark.asyncio
    async def test_live_status(self) -> None:
        playback_json = json.dumps({"media": [{"path": "https://live.chzzk.com/master.m3u8"}]})
        api_response = json.dumps(
            {
                "content": {
                    "channel": {"channelName": "主播"},
                    "status": "OPEN",
                    "livePlaybackJson": playback_json,
                }
            }
        )
        m3u8_content = "#EXTM3U\nhttps://live.chzzk.com/stream1.m3u8"
        with (patch("src.spider.async_req", new_callable=AsyncMock, side_effect=[api_response, m3u8_content]),):
            result = await get_chzzk_stream_data("https://chzzk.naver.com/live/abc123")
            assert result["is_live"] is True
            assert "m3u8_url" in result


class TestPpliveStreamUrl:
    # Test get_pplive_stream_url.

    @pytest.mark.asyncio
    async def test_not_live(self) -> None:
        api_response = json.dumps({"data": {"name": "飘飘主播", "living": False, "pullUrl": ""}})
        with patch("src.spider.async_req", new_callable=AsyncMock, return_value=api_response):
            result = await get_pplive_stream_url("https://m.pp.weimipopo.com/?anchorUid=abc123")
            assert result["anchor_name"] == "飘飘主播"
            assert result["is_live"] is False

    @pytest.mark.asyncio
    async def test_live(self) -> None:
        api_response = json.dumps(
            {"data": {"name": "主播", "living": True, "pullUrl": "https://pull.example.com/live.m3u8"}}
        )
        with patch("src.spider.async_req", new_callable=AsyncMock, return_value=api_response):
            result = await get_pplive_stream_url("https://m.pp.weimipopo.com/?anchorUid=abc123")
            assert result["is_live"] is True
            assert result["m3u8_url"] == "https://pull.example.com/live.m3u8"


class Test6roomStreamUrl:
    # Test get_6room_stream_url.

    @pytest.mark.asyncio
    async def test_live(self) -> None:
        html = "rid: '12345',\n  roomid"
        api_response = json.dumps(
            {
                "content": {
                    "liveinfo": {"flvtitle": "live_12345"},
                    "roominfo": {"alias": "六间房主播"},
                }
            }
        )
        with patch("src.spider.async_req", new_callable=AsyncMock, side_effect=[html, api_response]):
            result = await get_6room_stream_url("https://v.6.cn/12345")
            assert result["anchor_name"] == "六间房主播"
            assert result["is_live"] is True
            # 固化 6room 流地址完整契约，防止 host/路径/扩展名回归（弱子串断言会漏检）。
            assert result["flv_url"] == "https://wlive.6rooms.com/httpflv/live_12345.flv"
            assert result["record_url"] == result["flv_url"]

    @pytest.mark.asyncio
    async def test_no_room_id_raises(self) -> None:
        html = "<html>no rid here</html>"
        with patch("src.spider.async_req", new_callable=AsyncMock, return_value=html):
            result = await get_6room_stream_url("https://v.6.cn/12345")
            assert result == {"is_live": False}


class TestYoutubeStreamUrl:
    # Test get_youtube_stream_url.

    @pytest.mark.asyncio
    async def test_no_player_response_raises(self) -> None:
        with patch("src.spider.async_req", new_callable=AsyncMock, return_value="<html>no data</html>"):
            result = await get_youtube_stream_url("https://www.youtube.com/watch?v=abc")
            assert result == {"is_live": False}

    @pytest.mark.asyncio
    async def test_not_live(self) -> None:
        player_response = json.dumps(
            {
                "videoDetails": {"author": "YT主播", "isLive": False, "title": "test"},
            }
        )
        html = f"var ytInitialPlayerResponse = {player_response};var meta = document.createElement"
        with patch("src.spider.async_req", new_callable=AsyncMock, return_value=html):
            result = await get_youtube_stream_url("https://www.youtube.com/watch?v=abc")
            assert result["anchor_name"] == "YT主播"
            assert result["is_live"] is False


class TestShowroomStreamData:
    # Test get_showroom_stream_data.

    @pytest.mark.asyncio
    async def test_not_live(self) -> None:
        info_response = json.dumps({"room_name": "ShowRoom主播", "live_status": 1})
        with patch("src.spider.async_req", new_callable=AsyncMock, return_value=info_response):
            result = await get_showroom_stream_data("https://www.showroom-live.com/room/profile?room_id=123")
            assert result["anchor_name"] == "ShowRoom主播"
            assert result["is_live"] is False


class TestLookliveSecretData:
    # Test get_looklive_secret_data - RSA/AES encryption.

    def test_returns_tuple_of_strings(self) -> None:
        result = get_looklive_secret_data({"key": "value"})
        assert isinstance(result, tuple)
        assert len(result) == 2
        enc_text, enc_sec_key = result
        assert isinstance(enc_text, str)
        assert isinstance(enc_sec_key, str)
        assert len(enc_sec_key) == 256  # RSA 2048-bit → 256 hex chars

    def test_different_inputs_different_outputs(self) -> None:
        r1 = get_looklive_secret_data({"a": "1"})
        r2 = get_looklive_secret_data({"b": "2"})
        # enc_text differs (different plaintext); enc_sec_key may differ due to random key
        assert r1[0] != r2[0]


class TestKugouStreamUrl:
    # Test get_kugou_stream_url.

    @pytest.mark.asyncio
    async def test_not_live(self) -> None:
        room_info = json.dumps(
            {
                "data": {
                    "normalRoomInfo": {"nickName": "酷狗主播"},
                    "liveType": -1,
                }
            }
        )
        with patch("src.spider.async_req", new_callable=AsyncMock, return_value=room_info):
            result = await get_kugou_stream_url("https://fanxing2.kugou.com/12345?roomId=12345")
            assert result["anchor_name"] == "酷狗主播"
            assert result["is_live"] is False


class TestJdStreamUrl:
    # Test get_jd_stream_url.

    @pytest.mark.asyncio
    async def test_no_author_id_no_live_id(self) -> None:
        # 无 authorId 且无 live_id 时返回空.
        with patch("src.spider.async_req", new_callable=AsyncMock, return_value="https://lives.jd.com/"):
            result = await get_jd_stream_url("https://lives.jd.com/")
            assert result["anchor_name"] == ""
            assert result["is_live"] is False


class TestFaceitStreamData:
    # Test get_faceit_stream_data.

    @pytest.mark.asyncio
    async def test_non_twitch_platform(self) -> None:
        user_response = json.dumps({"payload": {"id": "user123"}})
        stream_response = json.dumps(
            {"payload": [{"userNickname": "Faceit主播", "platformId": "id123", "platform": "youtube"}]}
        )
        with patch("src.spider.async_req", new_callable=AsyncMock, side_effect=[user_response, stream_response]):
            result = await get_faceit_stream_data("https://www.faceit.com/zh/players/testuser/stream")
            assert result["anchor_name"] == "Faceit主播"
            assert result["is_live"] is False


class TestYingkeStreamUrl:
    # Test get_yingke_stream_url.

    @pytest.mark.asyncio
    async def test_not_live(self) -> None:
        api_response = json.dumps(
            {
                "data": {
                    "media_info": {"nick": "映客主播"},
                    "status": 0,
                    "live_addr": [],
                }
            }
        )
        with patch("src.spider.async_req", new_callable=AsyncMock, return_value=api_response):
            result = await get_yingke_stream_url("https://www.inke.cn/live.html?uid=abc&id=123")
            assert result["anchor_name"] == "映客主播"
            assert result["is_live"] is False

    @pytest.mark.asyncio
    async def test_no_uid_raises(self) -> None:
        with patch("src.spider.async_req", new_callable=AsyncMock):
            result = await get_yingke_stream_url("https://www.inke.cn/live.html")
            assert result == {"is_live": False}


class TestLiuxingStreamUrl:
    # Test get_liuxing_stream_url.

    @pytest.mark.asyncio
    async def test_not_live(self) -> None:
        api_response = json.dumps({"data": {"roomInfo": {"nickname": "流星主播", "live_stat": 0}}})
        with patch("src.spider.async_req", new_callable=AsyncMock, return_value=api_response):
            result = await get_liuxing_stream_url("https://wap.7u66.com/12345")
            assert result["anchor_name"] == "流星主播"
            assert result["is_live"] is False


class TestLangliveStreamUrl:
    # Test get_langlive_stream_url.

    @pytest.mark.asyncio
    async def test_not_live(self) -> None:
        api_response = json.dumps({"data": {"live_info": {"nickname": "浪Live主播", "live_status": 0}}})
        with patch("src.spider.async_req", new_callable=AsyncMock, return_value=api_response):
            result = await get_langlive_stream_url("https://www.lang.live/room/12345")
            assert result["anchor_name"] == "浪Live主播"
            assert result["is_live"] is False

    @pytest.mark.asyncio
    async def test_live(self) -> None:
        api_response = json.dumps(
            {
                "data": {
                    "live_info": {
                        "nickname": "主播",
                        "live_status": 1,
                        "liveurl": "http://cdn.lang.live/flv",
                        "liveurl_hls": "http://cdn.lang.live/hls",
                    }
                }
            }
        )
        with patch("src.spider.async_req", new_callable=AsyncMock, return_value=api_response):
            result = await get_langlive_stream_url("https://www.lang.live/room/12345")
            assert result["is_live"] is True


class Test17LiveStreamUrl:
    # Test get_17live_stream_url.

    @pytest.mark.asyncio
    async def test_not_live(self) -> None:
        user_response = json.dumps({"displayName": "17主播"})
        live_response = json.dumps({"status": 0, "pullURLsInfo": {}})
        with patch("src.spider.async_req", new_callable=AsyncMock, side_effect=[user_response, live_response]):
            result = await get_17live_stream_url("https://17.live/live/12345")
            assert result["anchor_name"] == "17主播"
            assert result["is_live"] is False


class TestVvxqiuStreamUrl:
    # Test get_vvxqiu_stream_url.

    @pytest.mark.asyncio
    async def test_not_live(self) -> None:
        api_response = json.dumps({"data": {"anchorName": "VV主播"}})
        with patch("src.spider.async_req", new_callable=AsyncMock, side_effect=[api_response, "Not Found"]):
            result = await get_vvxqiu_stream_url("https://h5.vvxqiu.com/?roomId=12345")
            assert result["anchor_name"] == "VV主播"
            assert result["is_live"] is False


class TestPicartoStreamUrl:
    # Test get_picarto_stream_url.

    @pytest.mark.asyncio
    async def test_not_live(self) -> None:
        api_response = json.dumps({"channel": {"name": "PicartoArtist", "online": False, "title": ""}})
        with patch("src.spider.async_req", new_callable=AsyncMock, return_value=api_response):
            result = await get_picarto_stream_url("https://picarto.tv/PicartoArtist")
            assert result["anchor_name"] == "PicartoArtist"
            assert result["is_live"] is False

    @pytest.mark.asyncio
    async def test_live(self) -> None:
        api_response = json.dumps({"channel": {"name": "Artist", "online": True, "title": "Drawing"}})
        with patch("src.spider.async_req", new_callable=AsyncMock, return_value=api_response):
            result = await get_picarto_stream_url("https://picarto.tv/Artist")
            assert result["is_live"] is True
            assert "m3u8_url" in result


class TestChangliaoStreamUrl:
    # Test get_changliao_stream_url.

    @pytest.mark.asyncio
    async def test_not_live(self) -> None:
        api_response = json.dumps({"data": {"roomInfo": {"nickname": "畅聊主播", "live_stat": 0}}})
        with patch("src.spider.async_req", new_callable=AsyncMock, return_value=api_response):
            result = await get_changliao_stream_url("https://wap.tlclw.com/12345")
            assert result["anchor_name"] == "畅聊主播"
            assert result["is_live"] is False


class TestYinboStreamUrl:
    # Test get_yinbo_stream_url.

    @pytest.mark.asyncio
    async def test_not_live(self) -> None:
        api_response = json.dumps({"data": {"roomInfo": {"nickname": "音播主播", "live_stat": 0}}})
        with patch("src.spider.async_req", new_callable=AsyncMock, return_value=api_response):
            result = await get_yinbo_stream_url("https://live.ybw1666.com/800005143")
            assert result["anchor_name"] == "音播主播"
            assert result["is_live"] is False


class TestZhihuStreamUrl:
    # Test get_zhihu_stream_url.

    @pytest.mark.asyncio
    async def test_no_initial_data_returns_empty(self) -> None:
        html = "<html><body>no data</body></html>"
        with patch("src.spider.async_req", new_callable=AsyncMock, return_value=html):
            result = await get_zhihu_stream_url("https://www.zhihu.com/theater/12345")
            assert result == {"is_live": False}


class TestLianjieStreamUrl:
    # Test get_lianjie_stream_url.

    @pytest.mark.asyncio
    async def test_not_live(self) -> None:
        api_response = json.dumps(
            {"data": {"nickname": "连接主播", "isonline": 0, "defaultRoomTitle": "", "videoUrl": ""}}
        )
        with patch("src.spider.async_req", new_callable=AsyncMock, return_value=api_response):
            result = await get_lianjie_stream_url("https://www.lailianjie.com/room/12345")
            assert result["anchor_name"] == "连接主播"
            assert result["is_live"] is False


class TestLaixiuStreamUrl:
    # Test get_laixiu_stream_url.

    @pytest.mark.asyncio
    async def test_not_live(self) -> None:
        api_response = json.dumps({"data": {"nickname": "来秀主播", "playStatus": 1}})
        with patch("src.spider.async_req", new_callable=AsyncMock, return_value=api_response):
            result = await get_laixiu_stream_url("https://www.imkktv.com/?roomId=12345")
            assert result["anchor_name"] == "来秀主播"
            assert result["is_live"] is False


class TestHuajiaoStreamUrlApp:
    # Test get_huajiao_stream_url_app.

    @pytest.mark.asyncio
    async def test_error_returns_none(self) -> None:
        api_response = json.dumps({"errmsg": "error", "data": {}})
        with patch("src.spider.async_req", new_callable=AsyncMock, return_value=api_response):
            result = await get_huajiao_stream_url_app("https://www.huajiao.com/l/12345")
            assert result is None


class TestHuajiaoUserInfo:
    # Test get_huajiao_user_info.

    @pytest.mark.asyncio
    async def test_no_user_in_url_returns_none(self) -> None:
        result = await get_huajiao_user_info("https://www.huajiao.com/other/12345")
        assert result is None

    @pytest.mark.asyncio
    async def test_not_live(self) -> None:
        feeds_response = json.dumps({"data": {"feeds": []}})
        html = "<title>主播的主页.*</title>"
        with patch("src.spider.async_req", new_callable=AsyncMock, side_effect=[feeds_response, html]):
            result = await get_huajiao_user_info("https://www.huajiao.com/user/12345")
            assert result is not None
            assert result["is_live"] is False
            # 离线仍需从主页 <title> 解析出主播名，锁死 HTML 标题解析契约。
            assert result["anchor_name"] == "主播"
            # 离线不应携带直播相关字段（sn/liveid/title），防止误判为直播。
            assert "sn" not in result and "liveid" not in result and "title" not in result


class TestAcfunStreamData:
    # Test get_acfun_stream_data.

    @pytest.mark.asyncio
    async def test_not_live(self) -> None:
        api_response = json.dumps({"profile": {"name": "A站主播"}})
        with patch("src.spider.async_req", new_callable=AsyncMock, return_value=api_response):
            result = await get_acfun_stream_data("https://live.acfun.cn/live/12345")
            assert result["anchor_name"] == "A站主播"
            assert result["is_live"] is False


class TestMaoerfmStreamUrl:
    # Test get_maoerfm_stream_url.

    @pytest.mark.asyncio
    async def test_error_returns_empty(self) -> None:
        with patch("src.spider.async_req", new_callable=AsyncMock, side_effect=Exception("network error")):
            result = await get_maoerfm_stream_url("https://www.missevan.com/live/12345")
            assert result == {"is_live": False}


class TestMaoerfmStreamUrlLive:
    # Test get_maoerfm_stream_url with live data.

    @pytest.mark.asyncio
    async def test_not_live(self) -> None:
        api_response = json.dumps(
            {
                "info": {
                    "creator": {"username": "猫耳主播"},
                    "room": {"status": {"broadcasting": False}},
                }
            }
        )
        with patch("src.spider.async_req", new_callable=AsyncMock, return_value=api_response):
            result = await get_maoerfm_stream_url("https://www.missevan.com/live/12345")
            assert result["anchor_name"] == "猫耳主播"
            assert result["is_live"] is False


class TestBilibiliRoomInfoH5:
    # Test get_bilibili_room_info_h5.

    @pytest.mark.asyncio
    async def test_returns_title(self) -> None:
        api_response = json.dumps({"data": {"room_info": {"title": "B站直播"}}})
        with patch("src.spider.async_req", new_callable=AsyncMock, return_value=api_response):
            result = await get_bilibili_room_info_h5("https://live.bilibili.com/26066074")
            assert result == "B站直播"


class TestHuajiaoStreamUrl:
    # Test get_huajiao_stream_url.

    @pytest.mark.asyncio
    async def test_no_cookies_user_url_returns_empty(self) -> None:
        result = await get_huajiao_stream_url("https://www.huajiao.com/user/12345")
        assert result["anchor_name"] == ""
        assert result["is_live"] is False


class TestWinktvBjInfo:
    # Test get_winktv_bj_info.

    @pytest.mark.asyncio
    async def test_error_returns_empty(self) -> None:
        # 出错返回 None（类型匹配兜底）：返回 tuple 的函数不能再拿到 dict 兜底值
        with patch("src.spider.async_req", new_callable=AsyncMock, side_effect=Exception("network")):
            result = await get_winktv_bj_info("https://www.winktv.co.kr/test")
            assert result is None


class TestKuaishouStreamData2:
    # Test get_kuaishou_stream_data2.

    @pytest.mark.asyncio
    async def test_no_eid_falls_back(self) -> None:
        fallback = json.dumps({"is_live": False})
        with (
            patch("src.spider.async_req", new_callable=AsyncMock, return_value=fallback),
            patch("src.spider._ensure_kuaishou_did", new_callable=AsyncMock, return_value="did=abc"),
            patch("src.spider.get_kuaishou_stream_data", new_callable=AsyncMock, return_value={"is_live": False}),
        ):
            result = await get_kuaishou_stream_data2("https://live.kuaishou.com/u/testuser")
            assert isinstance(result, dict)


class TestBigoStreamUrl:
    # Test get_bigo_stream_url.

    @pytest.mark.asyncio
    async def test_not_live_bigo_url(self) -> None:
        resp1 = json.dumps({"data": {"nick_name": "test_anchor", "alive": 0, "roomTopic": "", "hls_src": ""}})
        with patch("src.spider.async_req", new_callable=AsyncMock, return_value=resp1):
            result = await get_bigo_stream_url("https://www.bigo.tv/test/12345")
            assert result["anchor_name"] == "test_anchor"
            assert result["is_live"] is False

    @pytest.mark.asyncio
    async def test_live_bigo_url(self) -> None:
        resp1 = json.dumps(
            {
                "data": {
                    "nick_name": "anchor",
                    "alive": 1,
                    "roomTopic": "title",
                    "hls_src": "https://example.com/live.m3u8",
                }
            }
        )
        with patch("src.spider.async_req", new_callable=AsyncMock, return_value=resp1):
            result = await get_bigo_stream_url("https://www.bigo.tv/test/12345")
            assert result["is_live"] is True
            assert result["m3u8_url"] == "https://example.com/live.m3u8"

    @pytest.mark.asyncio
    async def test_error_returns_false(self) -> None:
        with patch("src.spider.async_req", new_callable=AsyncMock, side_effect=Exception("net")):
            result = await get_bigo_stream_url("https://www.bigo.tv/test/12345")
            assert result == {"is_live": False}


class TestBluedStreamUrl:
    # Test get_blued_stream_url.

    @pytest.mark.asyncio
    async def test_not_live(self) -> None:
        inner_json = json.dumps({"userInfo": {"name": "anchor", "onLive": False}, "liveInfo": {}})
        encoded = urllib.parse.quote(inner_json)
        html = f'decodeURIComponent("{encoded}")),window.Promise'
        with patch("src.spider.async_req", new_callable=AsyncMock, return_value=html):
            result = await get_blued_stream_url("https://www.blued.test/test")
            assert result["anchor_name"] == "anchor"
            assert result["is_live"] is False

    @pytest.mark.asyncio
    async def test_live(self) -> None:
        inner_json = json.dumps(
            {"userInfo": {"name": "anchor", "onLive": True}, "liveInfo": {"liveUrl": "https://example.com/live.m3u8"}}
        )
        encoded = urllib.parse.quote(inner_json)
        html = f'decodeURIComponent("{encoded}")),window.Promise'
        with patch("src.spider.async_req", new_callable=AsyncMock, return_value=html):
            result = await get_blued_stream_url("https://www.blued.test/test")
            assert result["is_live"] is True
            assert result["m3u8_url"] == "https://example.com/live.m3u8"

    @pytest.mark.asyncio
    async def test_error_returns_false(self) -> None:
        with patch("src.spider.async_req", new_callable=AsyncMock, side_effect=Exception("net")):
            result = await get_blued_stream_url("https://www.blued.test/test")
            assert result == {"is_live": False}


class TestSoopHeaders:
    # Test get_soop_headers.

    def test_without_cookies(self) -> None:
        headers = get_soop_headers()
        assert "client-id" in headers
        assert "user-agent" in headers
        assert "cookie" not in headers

    def test_with_cookies(self) -> None:
        headers = get_soop_headers(cookies="my_cookie=123")
        assert headers["cookie"] == "my_cookie=123"


class TestSoopliveCdnUrl:
    # Test get_sooplive_cdn_url.

    @pytest.mark.asyncio
    async def test_returns_json(self) -> None:
        resp = json.dumps({"view_url": "http://cdn.example.com/live"})
        with patch("src.spider.async_req", new_callable=AsyncMock, return_value=resp):
            result = await get_sooplive_cdn_url("12345")
            assert result["view_url"] == "http://cdn.example.com/live"

    @pytest.mark.asyncio
    async def test_error_returns_false(self) -> None:
        with patch("src.spider.async_req", new_callable=AsyncMock, side_effect=Exception("net")):
            result = await get_sooplive_cdn_url("12345")
            assert result == {"is_live": False}


class TestSoopliveTk:
    # Test get_sooplive_tk.

    @pytest.mark.asyncio
    async def test_aid_mode(self) -> None:
        resp = json.dumps({"CHANNEL": {"AID": "test_token_123"}})
        with patch("src.spider.async_req", new_callable=AsyncMock, return_value=resp):
            result = await get_sooplive_tk("https://play.sooplive.co.kr/testbj/123", rtype="aid")
            assert result == "test_token_123"

    @pytest.mark.asyncio
    async def test_info_mode(self) -> None:
        resp = json.dumps({"CHANNEL": {"BJNICK": "anchor", "BJID": "testbj", "BNO": "456"}})
        with patch("src.spider.async_req", new_callable=AsyncMock, return_value=resp):
            result = await get_sooplive_tk("https://play.sooplive.co.kr/testbj/123", rtype="info")
            assert result == ("anchor-testbj", "456")

    @pytest.mark.asyncio
    async def test_error_returns_false(self) -> None:
        # 出错返回 None（类型匹配兜底）：返回 str/tuple 的函数不能再拿到 dict 兜底值
        with patch("src.spider.async_req", new_callable=AsyncMock, side_effect=Exception("net")):
            result = await get_sooplive_tk("https://play.sooplive.co.kr/testbj/123", rtype="live")
            assert result is None


class TestHuyaAppStreamUrl:
    # Test get_huya_app_stream_url.

    @pytest.mark.asyncio
    async def test_not_live(self) -> None:
        resp = json.dumps(
            {"data": {"profileInfo": {"nick": "anchor"}, "realLiveStatus": "OFF", "liveData": {}, "stream": {}}}
        )
        with patch("src.spider.async_req", new_callable=AsyncMock, return_value=resp):
            result = await get_huya_app_stream_url("https://www.huya.com/12345")
            assert result["anchor_name"] == "anchor"
            assert result["is_live"] is False

    @pytest.mark.asyncio
    async def test_live_with_streams(self) -> None:
        resp = json.dumps(
            {
                "data": {
                    "profileInfo": {"nick": "anchor"},
                    "realLiveStatus": "ON",
                    "liveData": {"introduction": "test title"},
                    "stream": {
                        "baseSteamInfoList": [
                            {
                                "sCdnType": "TX",
                                "sStreamName": "stream1",
                                "sFlvUrl": "http://flv.example.com",
                                "sFlvAntiCode": "auth=1",
                                "sHlsUrl": "http://hls.example.com",
                                "sHlsAntiCode": "auth=2",
                            }
                        ]
                    },
                }
            }
        )
        with patch("src.spider.async_req", new_callable=AsyncMock, return_value=resp):
            result = await get_huya_app_stream_url("https://www.huya.com/12345")
            assert result["is_live"] is True
            assert result["title"] == "test title"
            assert "m3u8_url" in result
            assert "flv_url" in result

    @pytest.mark.asyncio
    async def test_priority_prefers_tx_over_al_at_index0(self) -> None:
        # AL 抢占 index 0 时, 候选仍应按 HS-first 优先级排序, TX 排在 AL 前,
        # 而非固定取 play_url_list[0](AL)。所有候选注入 m3u8_url_list/flv_url_list,
        # 由 select_source_url 按可达性校验选用。URL 统一为 http（https 实测 403）。
        resp = json.dumps(
            {
                "data": {
                    "profileInfo": {"nick": "anchor"},
                    "realLiveStatus": "ON",
                    "liveData": {"introduction": "test title"},
                    "stream": {
                        "baseSteamInfoList": [
                            {
                                "sCdnType": "AL",
                                "sStreamName": "alstream",
                                "sFlvUrl": "http://al.flv.example.com",
                                "sFlvAntiCode": "auth=al",
                                "sHlsUrl": "http://al.hls.example.com",
                                "sHlsAntiCode": "auth=al",
                            },
                            {
                                "sCdnType": "TX",
                                "sStreamName": "txstream",
                                "sFlvUrl": "http://tx.flv.example.com",
                                "sFlvAntiCode": "codec=flv&ctype=tars_mp&fs=bhct",
                                "sHlsUrl": "http://tx.hls.example.com",
                                "sHlsAntiCode": "auth=tx",
                            },
                        ]
                    },
                }
            }
        )
        with patch("src.spider.async_req", new_callable=AsyncMock, return_value=resp):
            result = await get_huya_app_stream_url("https://www.huya.com/12345")
            assert result["is_live"] is True
            # 三项均来自 TX（TX 优先于 AL，且非 index0 的 AL），scheme 为 http
            assert result["m3u8_url"] == "http://tx.hls.example.com/txstream.m3u8?auth=tx"
            assert result["flv_url"] == "http://tx.flv.example.com/txstream.flv?codec=flv&ctype=huya_webh5&fs=bgct"
            assert result["record_url"] == "http://tx.flv.example.com/txstream.flv?codec=flv&ctype=huya_webh5&fs=bgct"
            assert "alstream" not in cast(str, result["m3u8_url"])
            assert "alstream" not in cast(str, result["flv_url"])
            # 候选列表按 TX→AL 顺序注入（HS-first 排序下 TX 在 AL 前）
            assert result["m3u8_url_list"] == [
                "http://tx.hls.example.com/txstream.m3u8?auth=tx",
                "http://al.hls.example.com/alstream.m3u8?auth=al",
            ]
            assert result["flv_url_list"] == [
                "http://tx.flv.example.com/txstream.flv?codec=flv&ctype=huya_webh5&fs=bgct",
                "http://al.flv.example.com/alstream.flv?auth=al",
            ]

    @pytest.mark.asyncio
    async def test_hs_cdn_selected_first_when_present(self) -> None:
        # 含 HS 候选时按 HS-first 排序, 主源与候选列表首位均为 HS（实测 HS 为 HLS 可靠承载线路）。
        resp = json.dumps(
            {
                "data": {
                    "profileInfo": {"nick": "anchor"},
                    "realLiveStatus": "ON",
                    "liveData": {"introduction": "test title"},
                    "stream": {
                        "baseSteamInfoList": [
                            {
                                "sCdnType": "AL",
                                "sStreamName": "alstream",
                                "sFlvUrl": "http://al.flv.example.com",
                                "sFlvAntiCode": "auth=al",
                                "sHlsUrl": "http://al.hls.example.com",
                                "sHlsAntiCode": "auth=al",
                            },
                            {
                                "sCdnType": "HS",
                                "sStreamName": "hsstream",
                                "sFlvUrl": "http://hs.flv.example.com",
                                "sFlvAntiCode": "auth=hs",
                                "sHlsUrl": "http://hs.hls.example.com",
                                "sHlsAntiCode": "auth=hs",
                            },
                            {
                                "sCdnType": "TX",
                                "sStreamName": "txstream",
                                "sFlvUrl": "http://tx.flv.example.com",
                                "sFlvAntiCode": "auth=tx",
                                "sHlsUrl": "http://tx.hls.example.com",
                                "sHlsAntiCode": "auth=tx",
                            },
                        ]
                    },
                }
            }
        )
        with patch("src.spider.async_req", new_callable=AsyncMock, return_value=resp):
            result = await get_huya_app_stream_url("https://www.huya.com/12345")
            assert result["is_live"] is True
            # 主源取 HS
            assert result["m3u8_url"] == "http://hs.hls.example.com/hsstream.m3u8?auth=hs"
            # 候选列表按 HS→TX→AL 顺序（HS-first）
            assert result["m3u8_url_list"] == [
                "http://hs.hls.example.com/hsstream.m3u8?auth=hs",
                "http://tx.hls.example.com/txstream.m3u8?auth=tx",
                "http://al.hls.example.com/alstream.m3u8?auth=al",
            ]
            # 无 https 化：所有 URL 均保持 http
            m3u8_list = cast(list[str], result["m3u8_url_list"])
            flv_list = cast(list[str], result["flv_url_list"])
            assert all(u.startswith("http://") for u in m3u8_list + flv_list)

    @pytest.mark.asyncio
    async def test_al_used_as_last_resort_when_only_cdn(self) -> None:
        # 仅 AL 可用时(末位兜底)仍应正常选源, 不出现空地址; scheme 保持 http。
        resp = json.dumps(
            {
                "data": {
                    "profileInfo": {"nick": "anchor"},
                    "realLiveStatus": "ON",
                    "liveData": {"introduction": "test title"},
                    "stream": {
                        "baseSteamInfoList": [
                            {
                                "sCdnType": "AL",
                                "sStreamName": "alstream",
                                "sFlvUrl": "http://al.flv.example.com",
                                "sFlvAntiCode": "auth=al",
                                "sHlsUrl": "http://al.hls.example.com",
                                "sHlsAntiCode": "auth=al",
                            }
                        ]
                    },
                }
            }
        )
        with patch("src.spider.async_req", new_callable=AsyncMock, return_value=resp):
            result = await get_huya_app_stream_url("https://www.huya.com/12345")
            assert result["is_live"] is True
            assert result["m3u8_url"] == "http://al.hls.example.com/alstream.m3u8?auth=al"
            assert result["flv_url"] == "http://al.flv.example.com/alstream.flv?auth=al"
            # 仅 AL 时 record_url 与 flv 同源且保持 http（不强制 https 化）
            assert result["record_url"] == "http://al.flv.example.com/alstream.flv?auth=al"

    @pytest.mark.asyncio
    async def test_error_returns_false(self) -> None:
        with patch("src.spider.async_req", new_callable=AsyncMock, side_effect=Exception("net")):
            result = await get_huya_app_stream_url("https://www.huya.com/12345")
            assert result == {"is_live": False}


class TestXhsStreamUrl:
    # Test get_xhs_stream_url.

    @pytest.mark.asyncio
    async def test_not_live_no_match(self) -> None:
        html1 = '<script>window.__INITIAL_STATE__={"liveStream":null}</script>'
        html2 = "<title>@testuser 的个人主页</title>"
        with patch("src.spider.async_req", new_callable=AsyncMock, side_effect=[html1, html2]):
            result = await get_xhs_stream_url("https://www.xiaohongshu.com/user/profile/test123")
            assert result["anchor_name"] == "testuser"
            assert result["is_live"] is False

    @pytest.mark.asyncio
    async def test_error_returns_false(self) -> None:
        with patch("src.spider.async_req", new_callable=AsyncMock, side_effect=Exception("net")):
            result = await get_xhs_stream_url("https://www.xiaohongshu.com/user/profile/test123")
            assert result == {"is_live": False}


class TestTokenJs:
    # Test get_token_js.

    @pytest.mark.asyncio
    async def test_success(self) -> None:
        key_resp = json.dumps(
            {"error": 0, "data": {"rand_str": "abc", "key": "k", "enc_time": 1, "enc_data": "enc123", "is_special": 0}}
        )
        with patch("src.spider.async_req", new_callable=AsyncMock, return_value=key_resp):
            result = await get_token_js("12345", "did123")
            assert "enc_data" in result
            assert result["did"] == "did123"
            assert "auth" in result

    @pytest.mark.asyncio
    async def test_error_returns_empty(self) -> None:
        with patch("src.spider.async_req", new_callable=AsyncMock, side_effect=Exception("net")):
            result = await get_token_js("12345", "did123")
            assert result == {}

    @pytest.mark.asyncio
    async def test_api_error_returns_empty(self) -> None:
        key_resp = json.dumps({"error": 1})
        with patch("src.spider.async_req", new_callable=AsyncMock, return_value=key_resp):
            result = await get_token_js("12345", "did123")
            assert result == {}


class TestDouyuInfoData:
    # Test get_douyu_info_data.

    @pytest.mark.asyncio
    async def test_not_live(self) -> None:
        resp = json.dumps(
            {"room": {"nickname": "anchor", "videoLoop": 0, "show_status": 0, "room_name": "test", "room_id": 1}}
        )
        with patch("src.spider.async_req", new_callable=AsyncMock, return_value=resp):
            result = await get_douyu_info_data("https://www.douyu.com/12345?rid=12345")
            assert result["anchor_name"] == "anchor"
            assert result["is_live"] is False

    @pytest.mark.asyncio
    async def test_live(self) -> None:
        resp = json.dumps(
            {
                "room": {
                    "nickname": "anchor",
                    "videoLoop": 0,
                    "show_status": 1,
                    "room_name": "test&nbsp;live",
                    "room_id": 123,
                }
            }
        )
        with patch("src.spider.async_req", new_callable=AsyncMock, return_value=resp):
            result = await get_douyu_info_data("https://www.douyu.com/12345?rid=12345")
            assert result["is_live"] is True
            assert result["title"] == "testlive"
            assert result["room_id"] == 123

    @pytest.mark.asyncio
    async def test_error_returns_false(self) -> None:
        with patch("src.spider.async_req", new_callable=AsyncMock, side_effect=Exception("net")):
            result = await get_douyu_info_data("https://www.douyu.com/12345")
            assert result == {"is_live": False}


class TestAcfunSignParams:
    # Test get_acfun_sign_params.

    @pytest.mark.asyncio
    async def test_returns_params(self) -> None:
        resp = json.dumps({"userId": 12345, "acfun.api.visitor_st": "st123"})
        with patch("src.spider.async_req", new_callable=AsyncMock, return_value=resp):
            result = await get_acfun_sign_params()
            assert result[0] == 12345
            assert result[2] == "st123"

    @pytest.mark.asyncio
    async def test_error_returns_false(self) -> None:
        with patch("src.spider.async_req", new_callable=AsyncMock, side_effect=Exception("net")):
            result = await get_acfun_sign_params()
            assert result == {"is_live": False}


class TestDouyuStreamData:
    # Test get_douyu_stream_data.

    @pytest.mark.asyncio
    async def test_success(self) -> None:
        sign_params = {"enc_data": "enc", "did": "did123", "ts": 1000, "auth": "auth123"}
        stream_resp = json.dumps({"error": 0, "data": {"url": "http://stream.example.com"}})
        with (
            patch("src.spider.get_token_js", new_callable=AsyncMock, return_value=sign_params),
            patch("src.spider.async_req", new_callable=AsyncMock, return_value=stream_resp),
        ):
            result = await get_douyu_stream_data("12345")
            assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_no_sign_params(self) -> None:
        with patch("src.spider.get_token_js", new_callable=AsyncMock, return_value={}):
            result = await get_douyu_stream_data("12345")
            assert result["error"] == -1


class TestSoopliveStreamData:
    # Test get_sooplive_stream_data.

    @pytest.mark.asyncio
    async def test_error_returns_false(self) -> None:
        with patch("src.spider.async_req", new_callable=AsyncMock, side_effect=Exception("net")):
            result = await get_sooplive_stream_data("https://play.sooplive.co.kr/testbj/123")
            assert result == {"is_live": False}


class TestLoginSooplive:
    # Test login_sooplive.

    @pytest.mark.asyncio
    async def test_short_username_raises(self) -> None:
        # 出错返回 None（类型匹配兜底）：返回 cookie 字符串的函数不能再拿到 dict 兜底值
        with patch("src.spider.async_req", new_callable=AsyncMock):
            result = await login_sooplive("short", "longpassword1")
            assert result is None

    @pytest.mark.asyncio
    async def test_short_password_raises(self) -> None:
        with patch("src.spider.async_req", new_callable=AsyncMock):
            result = await login_sooplive("validuser", "short")
            assert result is None


class TestBilibiliStreamData:
    # Test get_bilibili_stream_data.

    @pytest.mark.asyncio
    async def test_code_zero_with_durl(self) -> None:
        resp = json.dumps({"code": 0, "data": {"durl": [{"url": "http://live.example.com/stream?d1--cn-gotcha=1"}]}})
        with patch("src.spider.async_req", new_callable=AsyncMock, return_value=resp):
            result = await get_bilibili_stream_data("https://live.bilibili.com/12345")
            assert result is not None
            assert "url" in result

    @pytest.mark.asyncio
    async def test_code_zero_empty_durl(self) -> None:
        resp = json.dumps({"code": 0, "data": {"durl": []}})
        with patch("src.spider.async_req", new_callable=AsyncMock, return_value=resp):
            result = await get_bilibili_stream_data("https://live.bilibili.com/12345")
            assert result is None

    @pytest.mark.asyncio
    async def test_code_nonzero_not_live(self) -> None:
        resp1 = json.dumps({"code": -1, "data": {}})
        resp2 = json.dumps({"data": {"live_status": 0, "playurl_info": {"playurl": {"stream": []}}}})
        with patch("src.spider.async_req", new_callable=AsyncMock, side_effect=[resp1, resp2]):
            result = await get_bilibili_stream_data("https://live.bilibili.com/12345")
            assert result is None

    @pytest.mark.asyncio
    async def test_error_returns_false(self) -> None:
        with patch("src.spider.async_req", new_callable=AsyncMock, side_effect=Exception("net")):
            result = await get_bilibili_stream_data("https://live.bilibili.com/12345")
            assert result == {"is_live": False}

    @pytest.mark.asyncio
    async def test_fallback_with_streams(self) -> None:
        resp1 = json.dumps({"code": -1, "data": {}})
        resp2 = json.dumps(
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
                                                    "base_url": "/live/123.m3u8",
                                                    "current_qn": 10000,
                                                    "url_info": [
                                                        {"host": "http://cdn.example.com", "extra": "?wsSecret=abc"}
                                                    ],
                                                },
                                                {
                                                    "base_url": "/live/456.m3u8",
                                                    "current_qn": 400,
                                                    "url_info": [
                                                        {"host": "http://cdn.example.com", "extra": "?wsSecret=def"}
                                                    ],
                                                },
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
        with patch("src.spider.async_req", new_callable=AsyncMock, side_effect=[resp1, resp2]):
            result = await get_bilibili_stream_data("https://live.bilibili.com/12345")
            assert result is not None
            assert "url" in result
            assert result["current_qn"] == "10000"
            # 固化清晰度集合与降序契约（弱长度断言会漏检质量值映射回归）。
            assert result["accept_qn"] == ["10000", "400"]


class TestNeteaseStreamDataLive:
    # Test get_netease_stream_data live path.

    @pytest.mark.asyncio
    async def test_live_stream(self) -> None:
        inner_json = json.dumps(
            {
                "props": {
                    "pageProps": {
                        "roomInfoInitData": {
                            "nickname": "anchor",
                            "live": {
                                "status": 1,
                                "nickname": "anchor",
                                "title": "test live",
                                "quickplay": [{"url": "http://live.m3u8"}],
                                "sharefile": "http://share.m3u8",
                            },
                        }
                    }
                }
            }
        )
        html = (
            f'<script id="__NEXT_DATA__" type="application/json" crossorigin="anonymous">{inner_json}</script></body>'
        )
        with patch("src.spider.async_req", new_callable=AsyncMock, return_value=html):
            result = await get_netease_stream_data("https://cc.163.com/12345")
            assert result["is_live"] is True
            assert result["anchor_name"] == "anchor"
            assert result["title"] == "test live"

    @pytest.mark.asyncio
    async def test_not_live(self) -> None:
        inner_json = json.dumps(
            {
                "props": {
                    "pageProps": {
                        "roomInfoInitData": {"nickname": "anchor", "live": {"status": 0, "nickname": "anchor"}}
                    }
                }
            }
        )
        html = (
            f'<script id="__NEXT_DATA__" type="application/json" crossorigin="anonymous">{inner_json}</script></body>'
        )
        with patch("src.spider.async_req", new_callable=AsyncMock, return_value=html):
            result = await get_netease_stream_data("https://cc.163.com/12345")
            assert result["is_live"] is False


class TestBilibiliRoomInfo:
    # Test get_bilibili_room_info.

    @pytest.mark.asyncio
    async def test_live_room(self) -> None:
        resp1 = json.dumps({"data": {"uid": 123, "live_status": 1}})
        resp2 = json.dumps({"data": {"info": {"uname": "anchor_name"}}})
        resp3 = json.dumps({"data": {"room_info": {"title": "test title"}}})
        with patch("src.spider.async_req", new_callable=AsyncMock, side_effect=[resp1, resp2, resp3]):
            result = await get_bilibili_room_info("https://live.bilibili.com/12345")
            assert result["anchor_name"] == "anchor_name"
            assert result["live_status"] is True
            assert result["title"] == "test title"

    @pytest.mark.asyncio
    async def test_error_returns_default(self) -> None:
        with patch("src.spider.async_req", new_callable=AsyncMock, side_effect=Exception("net")):
            result = await get_bilibili_room_info("https://live.bilibili.com/12345")
            assert result["anchor_name"] == ""
            assert result["live_status"] is False


class TestLoginFlexTv:
    # Test login_flextv.

    @pytest.mark.asyncio
    async def test_success_returns_cookie_str(self) -> None:
        cookie_dict = {"flx_oauth_access": "abc123", "other": "val"}
        with patch("src.spider.async_req", new_callable=AsyncMock, return_value=cookie_dict):
            result = await login_flextv("user123", "pass123")
            # 固化 cookie 串完整格式：分隔符 "; " + 全部条目（弱子串断言会漏检分隔符/漏项回归）。
            assert result == "flx_oauth_access=abc123; other=val"

    @pytest.mark.asyncio
    async def test_success_tuple_format(self) -> None:
        cookie_dict = {"flx_oauth_access": "tok", "x": "y"}
        with patch("src.spider.async_req", new_callable=AsyncMock, return_value=("ignored", cookie_dict)):
            result = await login_flextv("user", "pass")
            # 固化 cookie 串完整格式：分隔符 "; " + 全部条目（弱子串断言会漏检分隔符/漏项回归）。
            assert result == "flx_oauth_access=tok; x=y"

    @pytest.mark.asyncio
    async def test_no_access_token_returns_none(self) -> None:
        with patch("src.spider.async_req", new_callable=AsyncMock, return_value={"other": "val"}):
            result = await login_flextv("user", "pass")
            assert result is None

    @pytest.mark.asyncio
    async def test_error_returns_false(self) -> None:
        # 出错返回 None（类型匹配兜底）：旧 dict 兜底会被 if new_cookies 误判为登录成功
        with patch("src.spider.async_req", new_callable=AsyncMock, side_effect=Exception("net")):
            result = await login_flextv("user", "pass")
            assert result is None


class TestGetFlexTvStreamUrl:
    # Test get_flextv_stream_url.

    @pytest.mark.asyncio
    async def test_returns_play_url(self) -> None:
        resp = json.dumps({"sources": [{"url": "http://live.m3u8"}]})
        with patch("src.spider.async_req", new_callable=AsyncMock, return_value=resp):
            result = await get_flextv_stream_url("https://www.ttinglive.com/user123/live")
            assert result == "http://live.m3u8"

    @pytest.mark.asyncio
    async def test_no_sources_returns_none(self) -> None:
        resp = json.dumps({"sources": []})
        with patch("src.spider.async_req", new_callable=AsyncMock, return_value=resp):
            result = await get_flextv_stream_url("https://www.ttinglive.com/user123/live")
            assert result is None

    @pytest.mark.asyncio
    async def test_error_raises(self) -> None:
        with patch("src.spider.async_req", new_callable=AsyncMock, side_effect=Exception("net")):
            with pytest.raises(Exception):
                await get_flextv_stream_url("https://www.ttinglive.com/user123/live")


class TestGetWinkTvStreamData:
    # Test get_winktv_stream_data.

    @pytest.mark.asyncio
    async def test_live_stream(self) -> None:
        bj_resp = ("wink_anchor", True)
        play_resp = json.dumps({"PlayList": {"hls": [{"url": "http://wink.m3u8"}]}})
        m3u8_content = "#EXTM3U\n#EXTINF:2,auth_playlist0.ts\nhttp://cdn/auth_playlist0.ts"
        with (
            patch("src.spider.get_winktv_bj_info", new_callable=AsyncMock, return_value=bj_resp),
            patch("src.spider.async_req", new_callable=AsyncMock, side_effect=[play_resp, m3u8_content]),
        ):
            result = await get_winktv_stream_data("https://www.winktv.co.kr/testuser")
            assert result["is_live"] is True
            assert result["anchor_name"] == "wink_anchor"
            assert result["m3u8_url"] == "http://wink.m3u8"

    @pytest.mark.asyncio
    async def test_not_live(self) -> None:
        bj_resp = ("wink_anchor", False)
        with patch("src.spider.get_winktv_bj_info", new_callable=AsyncMock, return_value=bj_resp):
            result = await get_winktv_stream_data("https://www.winktv.co.kr/testuser")
            assert result["is_live"] is False

    @pytest.mark.asyncio
    async def test_error_returns_false(self) -> None:
        with patch("src.spider.get_winktv_bj_info", new_callable=AsyncMock, side_effect=Exception("net")):
            result = await get_winktv_stream_data("https://www.winktv.co.kr/testuser")
            assert result == {"is_live": False}
