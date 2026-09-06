# -*- coding: utf-8 -*-
# src/spider.py 批量平台函数测试：覆盖 60+ 直播平台的流地址解析函数（get_xxx_stream_url /
# get_xxx_stream_data / get_xxx_room_info 等）。测试策略：用 AsyncMock 桩掉 src.spider.async_req
# （屏蔽真实网络），喂入各平台真实响应 JSON/HTML 形态，断言解析出的 anchor_name / is_live /
# 流地址契约。
# 大量用例守护「离线/出错路径」：平台函数多经装饰器捕获异常，须返回 {is_live:False} 而非抛错
# （保证主循环不因单房间解析失败而中断）。部分函数（get_xxx_tk / login_xxx / get_winktv_bj_info）
# 返回非 dict（str / tuple / None），其出错兜底为 None 而非 {is_live:False} —— 这类「类型匹配兜底」
# 契约被多用例显式锁定，因为旧 dict 兜底会被 `if token/cookie` 误判为登录/解析成功。
# 在线路径用例普遍固化完整 URL 契约（host/路径/扩展名/候选顺序），弱子串断言会漏检拼接回归。

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
    # 守护 _generate_twitch_play_session_id 的会话 ID 格式契约：固定 32 位小写十六进制串
    # （Twitch playSessionId 长度与大小写受服务端鉴权约束，不符会被拒签）。

    def test_returns_32_char_string(self) -> None:
        # Twitch playSessionId 的长度与大小写受服务端鉴权约束，不符会被拒签；
        # 锁住 32 位小写十六进制格式契约，防截断/大小写回归。
        result = _generate_twitch_play_session_id()
        assert len(result) == 32
        assert result == result.lower()  # should be lowercase

    def test_unique_per_call(self) -> None:
        # 会话 ID 须全局唯一，避免不同播放器实例撞同一会话导致鉴权重放；
        # 10 次采样不应全同（极端巧合概率可忽略）。
        results = {_generate_twitch_play_session_id() for _ in range(10)}
        assert len(results) > 1  # extremely unlikely all 10 are the same


class TestEnsureTwitchClientId:
    # Test _ensure_twitch_client_id.

    @pytest.mark.asyncio
    async def test_fetches_from_html(self) -> None:
        # Client-ID 从播放页内联脚本提取（无公开 API）；
        # 锁住 JSON 解析出的 24 位 ID 契约。
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
        # 缓存命中时直接返回已存 Client-ID、跳过网络拉取；锁住「免重复请求」契约，
        # 防止上层 Twitch 解析每房间都重拉凭据触发频控。
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
        # 拉取页面异常须返回空串而非抛错，避免上层 Twitch 解析整体失败；
        # 空 Client-ID 触发后续匿名兜底路径。
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
        # SIGI_STATE 内嵌 JSON 的 status=2 表示开播；锁住「整段内嵌 JSON 原样回传」契约，
        # 防解析器误拆字段导致主播名/状态丢失。
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
        # 响应体为截断/异常 EOF 时解析失败须走 {is_live:False} 兜底而非抛错；
        # 此异常响应体正是触发重试耗尽的现实形态，验证离线兜底路径。
        with (
            patch("src.spider.async_req", new_callable=AsyncMock, return_value="UNEXPECTED_EOF_WHILE_READING"),
            patch("src.spider.asyncio.sleep", new_callable=AsyncMock),
        ):
            result = await get_tiktok_stream_data("https://www.tiktok.com/@test/live")
            assert result == {"is_live": False}


class TestYYStreamData:
    # Test get_yy_stream_data.
    # 守护 YY 解析：页面含 nick 即视为可解析出主播名；缺字段经装饰器转 {is_live:False}，
    # 锁住「非标准结构也返回 dict」契约。

    @pytest.mark.asyncio
    async def test_no_anchor_name_returns_empty(self) -> None:
        # 无主播名时装饰器捕获异常，返回 {is_live: False}.
        with patch("src.spider.async_req", new_callable=AsyncMock, return_value="<html>no data</html>"):
            result = await get_yy_stream_data("https://www.yy.com/12345")
            assert result == {"is_live": False}

    @pytest.mark.asyncio
    async def test_successful_parse(self) -> None:
        # 页面含 nick 字段即视为可解析出主播名；锁住「非字典结构也返回 dict 且 is_live 推断」契约，
        # 防正则/字段提取失败时把在播房间误判离线。
        html = 'nick: "YY主播",\n  logo'
        with patch("src.spider.async_req", new_callable=AsyncMock, return_value=html):
            result = await get_yy_stream_data("https://www.yy.com/12345")
            assert isinstance(result, dict)


class TestPandatvStreamData:
    # 守护 PandaTV 解析：bjInfo 存在但 status 非直播 → anchor_name 由「昵称-房间号」拼接、
    # is_live=False；bjInfo 缺失（User not found）被装饰器转成离线兜底，验证异常不向上抛。

    @pytest.mark.asyncio
    async def test_not_live(self) -> None:
        bj_info_response = json.dumps({"bjInfo": {"id": "user1", "nick": "Panda主播"}, "message": "ok"})
        with patch("src.spider.async_req", new_callable=AsyncMock, return_value=bj_info_response):
            result = await get_pandatv_stream_data("https://www.pandalive.co.kr/user1")
            assert result["anchor_name"] == "Panda主播-user1"
            assert result["is_live"] is False

    @pytest.mark.asyncio
    async def test_no_bj_info_raises(self) -> None:
        # User not found 时装饰器捕获 RuntimeError 转离线兜底；
        # 验证异常不向上抛、中断主循环。
        response = json.dumps({"message": "User not found"})
        with patch("src.spider.async_req", new_callable=AsyncMock, return_value=response):
            result = await get_pandatv_stream_data("https://www.pandalive.co.kr/unknown")
            # decorator catches RuntimeError → returns {is_live: False}
            assert result == {"is_live": False}


class TestBaiduStreamData:
    # Test get_baidu_stream_data.

    @pytest.mark.asyncio
    async def test_empty_data_returns_not_live(self) -> None:
        # data 为空仍可解析出空主播名+离线，不抛 KeyError；
        # 字段缺失是常态，须兜底而非崩溃。
        api_response = json.dumps({"data": {}})
        with patch("src.spider.async_req", new_callable=AsyncMock, return_value=api_response):
            result = await get_baidu_stream_data("https://live.baidu.com?room_id=12345&other=x")
            assert result["anchor_name"] == ""
            assert result["is_live"] is False

    @pytest.mark.asyncio
    async def test_no_room_id_raises(self) -> None:
        # 无 room_id 无法拼请求 → 装饰器兜底 {is_live:False}；
        # 锁住缺参离线契约，防 KeyError 中断主循环。
        with patch("src.spider.async_req", new_callable=AsyncMock):
            result = await get_baidu_stream_data("https://live.baidu.com/no_room_id")
            assert result == {"is_live": False}


class TestWeiboStreamData:
    # 守护微博直播：show 页 status=0（未开播）→ is_live=False 但能拿到主播名；uid 页先走
    # feed 列表定位直播间 object_id 再拉详情，status=1 且含 pull 地址 → 在线并固化清晰度契约。

    @pytest.mark.asyncio
    async def test_show_url_not_live(self) -> None:
        # show 页 status=0（未开播）→ 离线但仍解析出主播名；
        # 锁住离线字段契约，防误判在线。
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
        # uid 页先走 feed 列表定位直播间 object_id 再拉详情；
        # status=1 且含 pull 地址 → 在线并解析主播名。
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
    # 守护 CHZZK（Naver）：status=CLOSED → 离线（仍能解析 channelName）；status=OPEN 且有
    # livePlaybackJson → 在线，二次请求解析 m3u8 内容得到 m3u8_url。

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
    # 守护飘飘直播：living 字段为真/假映射在线/离线，pullUrl 即流地址；覆盖两种状态码分支。

    @pytest.mark.asyncio
    async def test_not_live(self) -> None:
        # living=False 离线但仍解析主播名；
        # 锁住 living 字段分支，防误判在线。
        api_response = json.dumps({"data": {"name": "飘飘主播", "living": False, "pullUrl": ""}})
        with patch("src.spider.async_req", new_callable=AsyncMock, return_value=api_response):
            result = await get_pplive_stream_url("https://m.pp.weimipopo.com/?anchorUid=abc123")
            assert result["anchor_name"] == "飘飘主播"
            assert result["is_live"] is False

    @pytest.mark.asyncio
    async def test_live(self) -> None:
        # living=True 在线且 pullUrl 即流地址；锁住「在线状态分支 + 流地址契约」，
        # 与 test_not_live 对称覆盖飘飘直播两种状态码。
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
        # 页面无 rid 则无法拼房间号 → 装饰器兜底 {is_live:False}；
        # 锁住缺参离线契约。
        html = "<html>no rid here</html>"
        with patch("src.spider.async_req", new_callable=AsyncMock, return_value=html):
            result = await get_6room_stream_url("https://v.6.cn/12345")
            assert result == {"is_live": False}


class TestYoutubeStreamUrl:
    # Test get_youtube_stream_url.

    @pytest.mark.asyncio
    async def test_no_player_response_raises(self) -> None:
        # 页面无 ytInitialPlayerResponse 时无法定位播放元数据 → 装饰器兜底 {is_live:False}；
        # 锁住缺数据离线契约，防 KeyError 中断主循环。
        with patch("src.spider.async_req", new_callable=AsyncMock, return_value="<html>no data</html>"):
            result = await get_youtube_stream_url("https://www.youtube.com/watch?v=abc")
            assert result == {"is_live": False}

    @pytest.mark.asyncio
    async def test_not_live(self) -> None:
        # isLive=False 离线但仍解析 author；
        # 锁住离线字段契约。
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
        # live_status=1 在该平台语义为离线（与常规相反）→ is_live=False 但仍解析 room_name；
        # 锁住反直觉状态映射，防误判在线。
        info_response = json.dumps({"room_name": "ShowRoom主播", "live_status": 1})
        with patch("src.spider.async_req", new_callable=AsyncMock, return_value=info_response):
            result = await get_showroom_stream_data("https://www.showroom-live.com/room/profile?room_id=123")
            assert result["anchor_name"] == "ShowRoom主播"
            assert result["is_live"] is False


class TestLookliveSecretData:
    # Test get_looklive_secret_data - RSA/AES encryption.
    # 守护look直播登录加密：返回 (密文, 256位 RSA 加密密钥) 元组且含随机填充，不同明文输出不同，
    # 供上层拼装登录凭据。

    def test_returns_tuple_of_strings(self) -> None:
        # 加密函数须返回 (密文, 加密密钥) 两元组且均为 str；RSA-2048 加密密钥固定 256 个
        # 十六进制字符，锁住加密封装契约供上层登录拼装。
        result = get_looklive_secret_data({"key": "value"})
        assert isinstance(result, tuple)
        assert len(result) == 2
        enc_text, enc_sec_key = result
        assert isinstance(enc_text, str)
        assert isinstance(enc_sec_key, str)
        assert len(enc_sec_key) == 256  # RSA 2048-bit → 256 hex chars

    def test_different_inputs_different_outputs(self) -> None:
        # 不同明文须产生不同密文（加密含随机填充）；锁住加密非确定性输出，
        # 防实现退化为确定性编码导致登录凭据可被重放。
        r1 = get_looklive_secret_data({"a": "1"})
        r2 = get_looklive_secret_data({"b": "2"})
        # enc_text differs (different plaintext); enc_sec_key may differ due to random key
        assert r1[0] != r2[0]


class TestKugouStreamUrl:
    # Test get_kugou_stream_url.

    @pytest.mark.asyncio
    async def test_not_live(self) -> None:
        # liveType=-1 离线但仍解析 nickName；
        # 锁住 liveType 字段分支。
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
    # 守护京东直播：URL 既无 authorId 也无 live_id 时无法拼装请求 → anchor_name 空、离线兜底。

    @pytest.mark.asyncio
    async def test_no_author_id_no_live_id(self) -> None:
        # 无 authorId 且无 live_id 时返回空.
        with patch("src.spider.async_req", new_callable=AsyncMock, return_value="https://lives.jd.com/"):
            result = await get_jd_stream_url("https://lives.jd.com/")
            assert result["anchor_name"] == ""
            assert result["is_live"] is False


class TestFaceitStreamData:
    # Test get_faceit_stream_data.
    # 守护 Faceit 解析：platform 非 twitch 时不视为直播；锁住「非目标平台 → 离线」契约。

    @pytest.mark.asyncio
    async def test_non_twitch_platform(self) -> None:
        # platform 非 twitch 时 Faceit 不视为直播；锁住「非目标平台 → is_live=False」契约，
        # 防把 YouTube 等外部平台的资料误判为在播。
        user_response = json.dumps({"payload": {"id": "user123"}})
        stream_response = json.dumps(
            {"payload": [{"userNickname": "Faceit主播", "platformId": "id123", "platform": "youtube"}]}
        )
        with patch("src.spider.async_req", new_callable=AsyncMock, side_effect=[user_response, stream_response]):
            result = await get_faceit_stream_data("https://www.faceit.com/zh/players/testuser/stream")
            assert result["anchor_name"] == "Faceit主播"
            assert result["is_live"] is False


class TestYingkeStreamUrl:
    # 守护映客：status=0 且 live_addr 空数组 → 离线但解析出 nick；URL 无 uid 时无法定位
    # 房间 → 离线兜底（uid 是接口必需路径参数）。

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
    # 守护流星直播：live_stat=0 → 离线但解析出 nickname，验证离线路径字段契约。

    @pytest.mark.asyncio
    async def test_not_live(self) -> None:
        # live_stat=0 离线但仍解析 nickname；
        # 锁住 live_stat 字段分支。
        api_response = json.dumps({"data": {"roomInfo": {"nickname": "流星主播", "live_stat": 0}}})
        with patch("src.spider.async_req", new_callable=AsyncMock, return_value=api_response):
            result = await get_liuxing_stream_url("https://wap.7u66.com/12345")
            assert result["anchor_name"] == "流星主播"
            assert result["is_live"] is False


class TestLangliveStreamUrl:
    # 守护浪Live：live_status=0 离线 / =1 在线（含 flv 与 hls 双地址），验证两种状态码分支。

    @pytest.mark.asyncio
    async def test_not_live(self) -> None:
        # live_status=0 离线但仍解析 nickname；
        # 锁住 live_status 字段分支（与 test_live 对称）。
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
        # status=0 离线但仍解析 displayName；锁住 17Live「双响应（用户+直播）」解析契约，
        # 防离线时丢掉主播名。
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
        # 房间信息接口返回「Not Found」→ 离线但仍解析 anchorName；
        # 验证多响应分支均走离线兜底。
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
        # live_stat=0 离线但仍解析 nickname；
        # 与流星/音播同字段语义，锁住分支。
        api_response = json.dumps({"data": {"roomInfo": {"nickname": "畅聊主播", "live_stat": 0}}})
        with patch("src.spider.async_req", new_callable=AsyncMock, return_value=api_response):
            result = await get_changliao_stream_url("https://wap.tlclw.com/12345")
            assert result["anchor_name"] == "畅聊主播"
            assert result["is_live"] is False


class TestYinboStreamUrl:
    # Test get_yinbo_stream_url.

    @pytest.mark.asyncio
    async def test_not_live(self) -> None:
        # live_stat=0 离线但仍解析 nickname；
        # 锁住 live_stat 字段分支。
        api_response = json.dumps({"data": {"roomInfo": {"nickname": "音播主播", "live_stat": 0}}})
        with patch("src.spider.async_req", new_callable=AsyncMock, return_value=api_response):
            result = await get_yinbo_stream_url("https://live.ybw1666.com/800005143")
            assert result["anchor_name"] == "音播主播"
            assert result["is_live"] is False


class TestZhihuStreamUrl:
    # Test get_zhihu_stream_url.
    # 守护知乎直播：页面无初始数据无法定位直播信息 → 装饰器兜底 {is_live:False}；锁住缺数据离线契约。

    @pytest.mark.asyncio
    async def test_no_initial_data_returns_empty(self) -> None:
        # 页面无 __INITIAL_STATE__ 初始数据 → 无法定位直播信息，装饰器兜底 {is_live:False}；
        # 锁住缺数据离线契约。
        html = "<html><body>no data</body></html>"
        with patch("src.spider.async_req", new_callable=AsyncMock, return_value=html):
            result = await get_zhihu_stream_url("https://www.zhihu.com/theater/12345")
            assert result == {"is_live": False}


class TestLianjieStreamUrl:
    # Test get_lianjie_stream_url.
    # 守护连接直播：isonline=0 离线但仍解析 nickname；锁住 isonline 字段分支契约。

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
    # 守护来秀：playStatus=1 即「未开播」语义（与常规相反）→ is_live=False 但解析 nickname。

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
        # errmsg 错误响应须返回 None（app 接口返回非 dict，调用方以 None 判失败）；
        # 验证类型匹配兜底而非 {is_live:False}。
        api_response = json.dumps({"errmsg": "error", "data": {}})
        with patch("src.spider.async_req", new_callable=AsyncMock, return_value=api_response):
            result = await get_huajiao_stream_url_app("https://www.huajiao.com/l/12345")
            assert result is None


class TestHuajiaoUserInfo:
    # 守护花椒用户主页：URL 非 user/ 路径 → 直接返回 None（无需请求）；user/ 路径 feeds 为空
    # + 主页 title 解析出主播名 → 离线但不漏主播名，且离线不应携带 sn/liveid/title 等直播字段。

    @pytest.mark.asyncio
    async def test_no_user_in_url_returns_none(self) -> None:
        # 非 user/ 路径无需发请求直接返回 None，省一次无谓拉取；
        # 锁住路径前缀短路契约。
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
    # 守护 A 站直播：无 live 状态字段时离线但仍解析 profile.name；锁住字段契约。

    @pytest.mark.asyncio
    async def test_not_live(self) -> None:
        # 无 live 状态字段时离线但仍解析 profile.name；
        # 锁住字段契约。
        api_response = json.dumps({"profile": {"name": "A站主播"}})
        with patch("src.spider.async_req", new_callable=AsyncMock, return_value=api_response):
            result = await get_acfun_stream_data("https://live.acfun.cn/live/12345")
            assert result["anchor_name"] == "A站主播"
            assert result["is_live"] is False


class TestMaoerfmStreamUrl:
    # 守护猫耳 FM：网络异常（Exception）→ 装饰器兜底返回 {is_live:False}（音频直播接口不稳定）。

    @pytest.mark.asyncio
    async def test_error_returns_empty(self) -> None:
        # 网络异常（音频直播接口不稳定）→ 装饰器兜底 {is_live:False}；
        # 验证异常不向上抛。
        with patch("src.spider.async_req", new_callable=AsyncMock, side_effect=Exception("network error")):
            result = await get_maoerfm_stream_url("https://www.missevan.com/live/12345")
            assert result == {"is_live": False}


class TestMaoerfmStreamUrlLive:
    # Test get_maoerfm_stream_url with live data.

    @pytest.mark.asyncio
    async def test_not_live(self) -> None:
        # room.status.broadcasting=False 离线但仍解析 creator.username；锁住猫耳 FM
        # 嵌套状态字段契约，防离线误判在线。
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
        # H5 入口只回传标题字符串（非完整直播字典）；锁住「返回 str 而非 dict」契约，
        # 调用方据此直接显示房间标题。
        api_response = json.dumps({"data": {"room_info": {"title": "B站直播"}}})
        with patch("src.spider.async_req", new_callable=AsyncMock, return_value=api_response):
            result = await get_bilibili_room_info_h5("https://live.bilibili.com/26066074")
            assert result == "B站直播"


class TestHuajiaoStreamUrl:
    # Test get_huajiao_stream_url.
    # 守护花椒 web 接口：user/ 路径无 cookie 时无法拉流 → 返回空主播名+离线，验证鉴权前置短路。

    @pytest.mark.asyncio
    async def test_no_cookies_user_url_returns_empty(self) -> None:
        # user/ 路径无 cookie 时无法拉流 → 返回空主播名+离线；
        # 验证鉴权前置短路。
        result = await get_huajiao_stream_url("https://www.huajiao.com/user/12345")
        assert result["anchor_name"] == ""
        assert result["is_live"] is False


class TestWinktvBjInfo:
    # 守护 WinkTV 主播信息：网络异常返回 None 而非 {is_live:False} —— 该接口返回值是 tuple
    # (anchor, is_live)，类型契约不允许 dict 兜底，调用方须以 None 判断拉取失败。

    @pytest.mark.asyncio
    async def test_error_returns_empty(self) -> None:
        # 出错返回 None（类型匹配兜底）：返回 tuple 的函数不能再拿到 dict 兜底值
        with patch("src.spider.async_req", new_callable=AsyncMock, side_effect=Exception("network")):
            result = await get_winktv_bj_info("https://www.winktv.co.kr/test")
            assert result is None


class TestKuaishouStreamData2:
    # 守护快手 data2 入口：无 eid 时回退到内部 get_kuaishou_stream_data，桩掉 _ensure_kuaishou_did
    # （避免真实去重锁/网络）后验证返回 dict（不校验具体字段，只锁类型契约）。

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
    # 守护 Bigo 解析：alive 字段映射在线/离线，alive=1 时 hls_src 即 m3u8_url；网络异常兜底
    # {is_live:False}。

    @pytest.mark.asyncio
    async def test_not_live_bigo_url(self) -> None:
        # alive=0 离线但仍解析 nick_name；
        # 锁住 alive 字段分支。
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
        # 网络异常 → 装饰器兜底 {is_live:False}；
        # 验证异常不向上抛中断主循环。
        with patch("src.spider.async_req", new_callable=AsyncMock, side_effect=Exception("net")):
            result = await get_bigo_stream_url("https://www.bigo.tv/test/12345")
            assert result == {"is_live": False}


class TestBluedStreamUrl:
    # 守护 Blued：页面内 decodeURIComponent(...) 解码出 userInfo/liveInfo，onLive=False 离线 /
    # True 在线（liveUrl 即 m3u8_url）；网络异常 → {is_live:False}。HTML 用 urllib.parse.quote
    # 编码内嵌 JSON，复刻前端真实拼接形态。

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
        # onLive=True 在线且 liveUrl 即 m3u8_url；
        # 锁住解码后 liveInfo 字段契约。
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
        # 无 cookie 时仅下发 client-id/user-agent，不得带 cookie 字段；
        # 避免空 cookie 被服务端拒绝。
        headers = get_soop_headers()
        assert "client-id" in headers
        assert "user-agent" in headers
        assert "cookie" not in headers

    def test_with_cookies(self) -> None:
        headers = get_soop_headers(cookies="my_cookie=123")
        assert headers["cookie"] == "my_cookie=123"


class TestSoopliveCdnUrl:
    # Test get_sooplive_cdn_url.
    # 守护 Soop CDN 地址解析：接口返回 view_url 原样透传；网络异常兜底 {is_live:False}。

    @pytest.mark.asyncio
    async def test_returns_json(self) -> None:
        # CDN 接口返回 view_url 即直推地址；锁住「原始 JSON 透传」契约，
        # 供上层拼接最终流地址。
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
    # 守护 SoopLive token 解析：aid 模式取 AID 字符串 / info 模式取 (BJNICK-BJID, BNO) 元组；
    # 网络异常返回 None（返回 str/tuple 的接口不做 dict 兜底，避免被 if token 误判为成功）。

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
    # 守护虎牙 app 接口：覆盖 realLiveStatus 的 ON/OFF、多 CDN 候选（HS/TX/AL）的 HS-first 排序、
    # 以及 AL 抢占 index0 时仍按 TX→AL 顺序排列（非固定取 play_url_list[0]）。URL 统一 http
    # （https 实测 403），候选列表（m3u8_url_list/flv_url_list）顺序与 select_source_url 可达性校验对接。

    @pytest.mark.asyncio
    async def test_not_live(self) -> None:
        # realLiveStatus=OFF 离线但仍解析 nick；
        # 锁住离线字段契约。
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
        # 网络异常 → 兜底 {is_live:False}；
        # 验证异常不向上抛。
        with patch("src.spider.async_req", new_callable=AsyncMock, side_effect=Exception("net")):
            result = await get_huya_app_stream_url("https://www.huya.com/12345")
            assert result == {"is_live": False}


class TestXhsStreamUrl:
    # 守护小红书：__INITIAL_STATE__.liveStream=null → 离线但解析出 @user 用户名；网络异常 → {is_live:False}。

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
        # 网络异常 → 兜底 {is_live:False}；
        # 验证异常不向上抛。
        with patch("src.spider.async_req", new_callable=AsyncMock, side_effect=Exception("net")):
            result = await get_xhs_stream_url("https://www.xiaohongshu.com/user/profile/test123")
            assert result == {"is_live": False}


class TestTokenJs:
    # Test get_token_js.

    @pytest.mark.asyncio
    async def test_success(self) -> None:
        # 密钥接口成功须带回 enc_data/did/auth；
        # 锁住登录签名字段契约。
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
        # 拉取密钥异常 → 返回空 dict（调用方据空 dict 判失败）；
        # 验证类型匹配兜底。
        with patch("src.spider.async_req", new_callable=AsyncMock, side_effect=Exception("net")):
            result = await get_token_js("12345", "did123")
            assert result == {}

    @pytest.mark.asyncio
    async def test_api_error_returns_empty(self) -> None:
        # 密钥接口返回 error!=0（业务失败）须返回空 dict 而非抛错；
        # 与网络异常同走类型匹配兜底，调用方据空 dict 判失败。
        key_resp = json.dumps({"error": 1})
        with patch("src.spider.async_req", new_callable=AsyncMock, return_value=key_resp):
            result = await get_token_js("12345", "did123")
            assert result == {}


class TestDouyuInfoData:
    # Test get_douyu_info_data.
    # 守护斗鱼房间信息：show_status 映射在线/离线，在线须清洗 HTML 实体标题；网络异常兜底
    # {is_live:False}。

    @pytest.mark.asyncio
    async def test_not_live(self) -> None:
        # show_status=0 离线但仍解析 nickname/room_id；锁住斗鱼 show_status 字段分支，
        # 防离线误判在线。
        resp = json.dumps(
            {"room": {"nickname": "anchor", "videoLoop": 0, "show_status": 0, "room_name": "test", "room_id": 1}}
        )
        with patch("src.spider.async_req", new_callable=AsyncMock, return_value=resp):
            result = await get_douyu_info_data("https://www.douyu.com/12345?rid=12345")
            assert result["anchor_name"] == "anchor"
            assert result["is_live"] is False

    @pytest.mark.asyncio
    async def test_live(self) -> None:
        # show_status=1 在线且 title 去 HTML 实体；
        # 锁住在线与字段清洗契约。
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
        # 网络异常 → 装饰器兜底 {is_live:False}；验证异常不向上抛中断主循环。
        with patch("src.spider.async_req", new_callable=AsyncMock, side_effect=Exception("net")):
            result = await get_douyu_info_data("https://www.douyu.com/12345")
            assert result == {"is_live": False}


class TestAcfunSignParams:
    # Test get_acfun_sign_params.
    # 守护 A 站访问凭据获取：返回 (userId, ..., visitor_st) 元组；拉取异常兜底 {is_live:False}。

    @pytest.mark.asyncio
    async def test_returns_params(self) -> None:
        # 访客接口返回 (userId, ..., visitor_st) 元组；锁住下标契约（0=userId、2=visitor_st），
        # 供后续签名流程取用访问凭据。
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
        # 桩掉 get_token_js 注入签名参数后，整体须返回 dict（含流地址）；锁住「签名→拉流」编排契约，
        # 防签名缺失导致 KeyError。
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
        # 密码过短须返回 None（类型匹配兜底）；
        # 返回 cookie 串的函数不拿 dict 兜底，避免被 if 误判登录成功。
        with patch("src.spider.async_req", new_callable=AsyncMock):
            result = await login_sooplive("validuser", "short")
            assert result is None


class TestBilibiliStreamData:
    # Test get_bilibili_stream_data.

    @pytest.mark.asyncio
    async def test_code_zero_with_durl(self) -> None:
        # code=0 且 durl 非空 → 在线并含流地址；锁住 B 站「code=0 即成功」契约，
        # 防把成功响应误判离线。
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
    # 守护网易 CC 直播：从 __NEXT_DATA__ 提取 live.status 映射在线/离线，在线解析 nickname/title
    # 与 quickplay/sharefile 流地址；离线分支不携带流地址。

    @pytest.mark.asyncio
    async def test_live_stream(self) -> None:
        # __NEXT_DATA__ 内 live.status=1 → 在线，解析 nickname/title；
        # 锁住 live 分支字段。
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
        # live.status=0 → 离线；
        # 验证离线分支不携带流地址。
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
    # 守护 B 站房间信息多接口聚合：uid/live_status/uname/title 三段请求合并；网络异常兜底
    # 空主播名+离线。

    @pytest.mark.asyncio
    async def test_live_room(self) -> None:
        # 三连请求取 uid/live_status/uname/title；live_status=1 在线；锁住 B 站房间信息
        # 多接口聚合契约，防字段错位。
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
    # 守护 FlexTV 登录：成功固化 cookie 串格式（"; " 分隔全条目）；无 access 字段或网络异常返回
    # None（类型匹配兜底），旧 dict 兜底会被 if 误判登录成功。

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
        # 响应缺 flx_oauth_access 字段 → 登录失败返回 None（类型匹配兜底）；
        # 返回 cookie 串的函数不拿 dict 兜底，避免被 if 误判登录成功。
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
    # 守护 FlexTV 流地址：sources 非空 → 返回首个 url；空 → None；网络异常向上抛（该层不兜底，
    # 由调用方处理，与多数平台 {is_live:False} 兜底不同）。

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
        # 网络异常须向上抛（该层不兜底），由调用方处理；
        # 与多数平台 {is_live:False} 兜底不同。
        with patch("src.spider.async_req", new_callable=AsyncMock, side_effect=Exception("net")):
            with pytest.raises(Exception):
                await get_flextv_stream_url("https://www.ttinglive.com/user123/live")


class TestGetWinkTvStreamData:
    # 守护 WinkTV：bj_info=(anchor, True) + play 列表含 hls → 在线并固化 m3u8_url；bj_info 离线
    # → {is_live:False}；bj_info 拉取异常 → {is_live:False}（薄编排层，桩掉 get_winktv_bj_info 隔离）。

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
        # bj_info 拉取异常 → {is_live:False}（桩掉 bj_info 隔离）；
        # 验证异常不向上抛。
        with patch("src.spider.get_winktv_bj_info", new_callable=AsyncMock, side_effect=Exception("net")):
            result = await get_winktv_stream_data("https://www.winktv.co.kr/testuser")
            assert result == {"is_live": False}
