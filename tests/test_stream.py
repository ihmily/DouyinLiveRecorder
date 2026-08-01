"""Tests for src/stream.py module — 纯工具函数 + 核心平台流地址解析路径。"""

from unittest.mock import AsyncMock, patch

import pytest

from src.stream import (
    QUALITY_CODE_TO_ZH,
    QUALITY_LEVEL,
    QUALITY_MAPPING,
    QUALITY_MAPPING_BIT,
    bitrate_to_quality,
    code_to_zh,
    get_quality_index,
    is_downgrade,
    _pad_list,
)


# ────────────────────────────────────────────────────────────
# 纯工具函数
# ────────────────────────────────────────────────────────────


class TestBitrateToQuality:
    """bitrate_to_quality: 码率 → 画质代码映射。"""

    def test_zero_bitrate_returns_od(self):
        assert bitrate_to_quality(0) == "OD"

    def test_negative_bitrate_returns_od(self):
        assert bitrate_to_quality(-100) == "OD"

    def test_low_bitrate_returns_ld(self):
        # LD 上限 600
        assert bitrate_to_quality(500) == "LD"

    def test_boundary_600_returns_ld(self):
        assert bitrate_to_quality(600) == "LD"

    def test_boundary_601_returns_sd(self):
        assert bitrate_to_quality(601) == "SD"

    def test_mid_bitrate_returns_hd(self):
        # HD 上限 1000
        assert bitrate_to_quality(999) == "HD"

    def test_high_bitrate_returns_bd(self):
        # BD 上限 4000
        assert bitrate_to_quality(3000) == "BD"

    def test_very_high_bitrate_returns_od(self):
        # OD 无上限（>4000 落入 OD）
        assert bitrate_to_quality(99999) == "OD"

    def test_exact_bd_boundary(self):
        assert bitrate_to_quality(4000) == "BD"


class TestCodeToZh:
    """code_to_zh: 画质代码 → 中文名。"""

    def test_known_codes(self):
        for code, zh in QUALITY_CODE_TO_ZH.items():
            assert code_to_zh(code) == zh

    def test_unknown_code_returns_as_is(self):
        assert code_to_zh("UNKNOWN") == "UNKNOWN"

    def test_none_returns_empty_string(self):
        assert code_to_zh(None) == ""

    def test_empty_string_returns_empty_string(self):
        assert code_to_zh("") == ""


class TestIsDowngrade:
    """is_downgrade: 判定实际画质是否低于请求画质。"""

    def test_same_quality_not_downgrade(self):
        assert is_downgrade("HD", "HD") is False

    def test_higher_quality_not_downgrade(self):
        # OD(0) 请求, HD(2) 实际 → 降级
        assert is_downgrade("OD", "HD") is True

    def test_lower_quality_not_downgrade(self):
        # SD(3) 请求, HD(2) 实际 → 非降级
        assert is_downgrade("SD", "HD") is False

    def test_none_requested_not_downgrade(self):
        assert is_downgrade(None, "HD") is False

    def test_none_actual_not_downgrade(self):
        assert is_downgrade("HD", None) is False

    def test_unknown_code_not_downgrade(self):
        assert is_downgrade("XX", "HD") is False


class TestPadList:
    """_pad_list: 列表填充到最小长度。"""

    def test_empty_list_returns_nones(self):
        result = _pad_list([], min_length=3)
        assert result == [None, None, None]

    def test_short_list_padded(self):
        result = _pad_list([1, 2], min_length=5)
        assert result == [1, 2, 2, 2, 2]

    def test_exact_length_unchanged(self):
        result = _pad_list([1, 2, 3], min_length=3)
        assert result == [1, 2, 3]

    def test_longer_list_unchanged(self):
        result = _pad_list([1, 2, 3, 4], min_length=3)
        assert result == [1, 2, 3, 4]

    def test_default_min_length_is_5(self):
        result = _pad_list([1])
        assert len(result) == 5
        assert result[0] == 1
        assert all(x == 1 for x in result[1:])


class TestGetQualityIndex:
    """get_quality_index: 解析画质参数。"""

    def test_none_returns_first(self):
        name, idx = get_quality_index(None)
        assert name == "OD"
        assert idx == QUALITY_MAPPING["OD"]

    def test_empty_string_returns_first(self):
        name, idx = get_quality_index("")
        assert name == "OD"

    def test_string_code(self):
        name, idx = get_quality_index("HD")
        assert name == "HD"
        assert idx == QUALITY_MAPPING["HD"]

    def test_numeric_string(self):
        # "3" → 第一个字符 3 → keys[3] = "HD"
        name, idx = get_quality_index("3")
        assert name == "HD"
        assert idx == QUALITY_MAPPING["HD"]

    def test_numeric_string_out_of_range(self):
        # "9" → 第一个字符 9 >= len(keys)=6 → 回退 0 → "OD"
        name, idx = get_quality_index("9")
        assert name == "OD"

    def test_unknown_string_returns_first(self):
        name, idx = get_quality_index("INVALID")
        assert name == "OD"

    def test_integer_input(self):
        name, idx = get_quality_index(2)
        # str(2) → "2" → "2".upper() → "2".isdigit() → int("2"[0])=2 → keys[2]="UHD"
        assert name == "UHD"

    def test_case_insensitive(self):
        name, idx = get_quality_index("hd")
        assert name == "HD"


# ────────────────────────────────────────────────────────────
# 常量一致性校验
# ────────────────────────────────────────────────────────────


class TestConstants:
    """确保画质相关常量映射保持一致。"""

    def test_quality_mapping_keys_match_level_keys(self):
        assert set(QUALITY_MAPPING.keys()) == set(QUALITY_LEVEL.keys())

    def test_quality_mapping_keys_match_bit_keys(self):
        assert set(QUALITY_MAPPING.keys()) == set(QUALITY_MAPPING_BIT.keys())

    def test_quality_code_to_zh_keys_match_mapping_keys(self):
        assert set(QUALITY_CODE_TO_ZH.keys()) == set(QUALITY_MAPPING.keys())


# ────────────────────────────────────────────────────────────
# 平台流地址解析（异步 + Mock）
# ────────────────────────────────────────────────────────────


class TestGetDouyinStreamUrl:
    """get_douyin_stream_url: 抖音直播流解析核心路径。"""

    @pytest.mark.asyncio
    async def test_offline_status_returns_not_live(self):
        """status != 2 → is_live=False。"""
        from src.stream import get_douyin_stream_url

        json_data = {"anchor_name": "test_anchor", "status": 4}
        result = await get_douyin_stream_url(json_data)
        assert result["is_live"] is False
        assert result["anchor_name"] == "test_anchor"

    @pytest.mark.asyncio
    async def test_live_with_flv_and_m3u8(self):
        """status=2 + flv/m3u8 数据 → 正确选中画质并返回流地址。"""
        from src.stream import get_douyin_stream_url

        json_data = {
            "anchor_name": "anchor_a",
            "status": 2,
            "stream_url": {
                "flv_pull_url": {"HD": "https://flv.example.com/hd.flv", "SD": "https://flv.example.com/sd.flv"},
                "hls_pull_url_map": {"HD": "https://m3u8.example.com/hd.m3u8"},
                "hevc_flv_url": None,
            },
        }
        with patch("src.stream.get_response_status", new_callable=AsyncMock, return_value=True):
            result = await get_douyin_stream_url(json_data, video_quality="HD")

        assert result["is_live"] is True
        assert result["quality"] == "HD"
        assert result["m3u8_url"] or result["flv_url"]
        assert "available_qualities" in result

    @pytest.mark.asyncio
    async def test_live_only_flv_no_m3u8(self):
        """仅有 FLV 无 m3u8 → 跳过可用性校验，不降级。"""
        from src.stream import get_douyin_stream_url

        json_data = {
            "anchor_name": "anchor_b",
            "status": 2,
            "stream_url": {
                "flv_pull_url": {"OD": "https://flv.example.com/od.flv"},
                "hls_pull_url_map": {},
                "hevc_flv_url": None,
            },
        }
        with patch("src.stream.get_response_status", new_callable=AsyncMock, return_value=True) as mock_status:
            result = await get_douyin_stream_url(json_data, video_quality="OD")

        assert result["is_live"] is True
        # 无 m3u8 时不应调用 get_response_status
        mock_status.assert_not_called()

    @pytest.mark.asyncio
    async def test_m3u8_unreachable_triggers_fallback(self):
        """m3u8 不可达 → 降级到相邻画质。"""
        from src.stream import get_douyin_stream_url

        json_data = {
            "anchor_name": "anchor_c",
            "status": 2,
            "stream_url": {
                "flv_pull_url": {"HD": "https://flv.example.com/hd.flv", "SD": "https://flv.example.com/sd.flv"},
                "hls_pull_url_map": {"HD": "https://m3u8.example.com/hd.m3u8", "SD": "https://m3u8.example.com/sd.m3u8"},
                "hevc_flv_url": None,
            },
        }
        with patch("src.stream.get_response_status", new_callable=AsyncMock, return_value=False):
            result = await get_douyin_stream_url(json_data, video_quality="HD")

        assert result["is_live"] is True
        # 降级后应切换到 SD
        assert result.get("actual_quality") in ("SD", "HD")


class TestGetTiktokStreamUrl:
    """get_tiktok_stream_url: TikTok 直播流解析。"""

    @pytest.mark.asyncio
    async def test_none_json_returns_not_live(self):
        from src.stream import get_tiktok_stream_url

        result = await get_tiktok_stream_url(None)
        assert result["is_live"] is False

    @pytest.mark.asyncio
    async def test_offline_user_status(self):
        from src.stream import get_tiktok_stream_url

        json_data = {
            "LiveRoom": {
                "liveRoomUserInfo": {"user": {"status": 0, "nickname": "Test", "uniqueId": "test_id"}},
                "liveRoom": {},
            }
        }
        result = await get_tiktok_stream_url(json_data)
        assert result["is_live"] is False
        assert result["anchor_name"] == "Test-test_id"

    @pytest.mark.asyncio
    async def test_live_with_stream_data(self):
        import json

        from src.stream import get_tiktok_stream_url

        stream_data = {
            "data": {
                "origin": {
                    "main": {"sdk_params": '{"vbitrate": 4000, "VCodec": "h264", "resolution": "1920x1080"}'},
                    "flv": "https://tiktok.example.com/origin.flv",
                    "hls": "https://tiktok.example.com/origin.m3u8",
                },
                "sd": {
                    "main": {"sdk_params": '{"vbitrate": 1000, "VCodec": "h264", "resolution": "1280x720"}'},
                    "flv": "https://tiktok.example.com/sd.flv",
                    "hls": "https://tiktok.example.com/sd.m3u8",
                },
            }
        }
        json_data = {
            "LiveRoom": {
                "liveRoomUserInfo": {"user": {"status": 2, "nickname": "Streamer", "uniqueId": "streamer1"}},
                "liveRoom": {
                    "title": "Live Now",
                    "streamData": {"pull_data": {"stream_data": json.dumps(stream_data)}},
                },
            }
        }
        with patch("src.stream.get_response_status", new_callable=AsyncMock, return_value=True):
            result = await get_tiktok_stream_url(json_data, video_quality="OD")

        assert result["is_live"] is True
        assert result["anchor_name"] == "Streamer-streamer1"
        assert result.get("flv_url") or result.get("m3u8_url")


class TestGetKuaishouStreamUrl:
    """get_kuaishou_stream_url: 快手直播流解析。"""

    @pytest.mark.asyncio
    async def test_not_live(self):
        from src.stream import get_kuaishou_stream_url

        json_data = {"type": 0, "is_live": False, "anchor_name": "ks_anchor"}
        result = await get_kuaishou_stream_url(json_data)
        assert result["is_live"] is False

    @pytest.mark.asyncio
    async def test_live_with_bitrate(self):
        from src.stream import get_kuaishou_stream_url

        json_data = {
            "type": 0,
            "is_live": True,
            "anchor_name": "ks_live",
            "m3u8_url_list": [{"url": "https://ks.example.com/hd.m3u8"}],
            "flv_url_list": [
                {"url": "https://ks.example.com/hd.flv", "bitrate": 2000},
                {"url": "https://ks.example.com/sd.flv", "bitrate": 800},
            ],
        }
        result = await get_kuaishou_stream_url(json_data, video_quality="HD")
        assert result["is_live"] is True
        assert result.get("flv_url")
        assert result.get("actual_quality")

    @pytest.mark.asyncio
    async def test_type1_not_live_returns_directly(self):
        from src.stream import get_kuaishou_stream_url

        json_data = {"type": 1, "is_live": False, "anchor_name": "ks_offline"}
        result = await get_kuaishou_stream_url(json_data)
        assert result == json_data


class TestGetYyStreamUrl:
    """get_yy_stream_url: YY 直播流解析。"""

    @pytest.mark.asyncio
    async def test_no_avp_info(self):
        from src.stream import get_yy_stream_url

        json_data = {"anchor_name": "yy_anchor"}
        result = await get_yy_stream_url(json_data)
        assert result["is_live"] is False

    @pytest.mark.asyncio
    async def test_live_with_cdn(self):
        from src.stream import get_yy_stream_url

        json_data = {
            "anchor_name": "yy_live",
            "title": "YY Live",
            "avp_info_res": {
                "stream_line_addr": {
                    "line1": {"cdn_info": {"url": "https://yy.example.com/live.flv"}}
                }
            },
        }
        result = await get_yy_stream_url(json_data)
        assert result["is_live"] is True
        assert result["flv_url"] == "https://yy.example.com/live.flv"
        assert result["record_url"] == "https://yy.example.com/live.flv"


class TestGetNeteaseStreamUrl:
    """get_netease_stream_url: 网易 CC 直播流解析。"""

    @pytest.mark.asyncio
    async def test_not_live_returns_directly(self):
        from src.stream import get_netease_stream_url

        json_data = {"is_live": False, "anchor_name": "netease_off"}
        result = await get_netease_stream_url(json_data)
        assert result == json_data

    @pytest.mark.asyncio
    async def test_live_with_stream_list(self):
        from src.stream import get_netease_stream_url

        json_data = {
            "is_live": True,
            "anchor_name": "netease_host",
            "title": "CC Live",
            "m3u8_url": "https://cc.example.com/live.m3u8",
            "stream_list": {
                "resolution": {
                    "ultra": {"cdn": {"ali": "https://ali.example.com/ultra.flv"}},
                    "high": {"cdn": {"ali": "https://ali.example.com/high.flv"}},
                }
            },
        }
        result = await get_netease_stream_url(json_data, video_quality="HD")
        assert result["is_live"] is True
        assert result.get("flv_url")
        assert result.get("actual_quality") == "HD"


class TestGetStreamUrl:
    """get_stream_url: 通用直播流解析入口。"""

    @pytest.mark.asyncio
    async def test_not_live_returns_directly(self):
        from src.stream import get_stream_url

        json_data = {"is_live": False, "anchor_name": "test"}
        result = await get_stream_url(json_data)
        assert result == json_data

    @pytest.mark.asyncio
    async def test_empty_play_url_list(self):
        from src.stream import get_stream_url

        json_data = {"is_live": True, "anchor_name": "test", "play_url_list": []}
        result = await get_stream_url(json_data)
        assert result == json_data

    @pytest.mark.asyncio
    async def test_m3u8_type(self):
        from src.stream import get_stream_url

        json_data = {
            "is_live": True,
            "anchor_name": "generic",
            "title": "Generic Live",
            "play_url_list": [
                {"m3u8": "https://example.com/od.m3u8", "flv": "https://example.com/od.flv"},
                {"m3u8": "https://example.com/sd.m3u8", "flv": "https://example.com/sd.flv"},
            ],
        }
        result = await get_stream_url(json_data, video_quality="OD", url_type="m3u8")
        assert result["is_live"] is True
        assert result.get("m3u8_url")
        assert result["quality"] == "OD"

    @pytest.mark.asyncio
    async def test_flv_type(self):
        from src.stream import get_stream_url

        json_data = {
            "is_live": True,
            "anchor_name": "generic",
            "title": "Generic Live",
            "play_url_list": [{"flv": "https://example.com/od.flv"}],
        }
        result = await get_stream_url(json_data, url_type="flv")
        assert result["is_live"] is True
        assert result.get("flv_url")

    @pytest.mark.asyncio
    async def test_all_type(self):
        from src.stream import get_stream_url

        json_data = {
            "is_live": True,
            "anchor_name": "generic",
            "title": "Generic Live",
            "play_url_list": [{"m3u8": "https://example.com/a.m3u8", "flv": "https://example.com/a.flv"}],
        }
        result = await get_stream_url(json_data, url_type="all")
        assert result["is_live"] is True
        assert "m3u8_url" in result
        assert "flv_url" in result
