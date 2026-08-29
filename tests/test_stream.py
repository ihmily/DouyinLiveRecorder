# Tests for src/stream.py module — 纯工具函数 + 核心平台流地址解析路径。

from typing import TypedDict, cast
from unittest.mock import AsyncMock, patch

import pytest

from src.stream import (
    BD_SUB_TIERS,
    QUALITY_CODE_TO_ZH,
    QUALITY_LEVEL,
    QUALITY_MAPPING,
    QUALITY_MAPPING_BIT,
    HuyaStreamUrl,
    TiktokStreamUrl,
    YyStreamUrl,
    _pad_list,
    bitrate_to_quality,
    code_to_zh,
    get_quality_index,
    is_downgrade,
)


# 测试侧收窄：get_*_stream_url 返回类型声明为 dict[str, object]（不变类型），
# 访问返回的异构字段时需按 MEMORY cast 模式收窄到具体结构。
class HuyaResult(TypedDict):
    is_live: bool
    m3u8_url: str
    m3u8_url_list: list[str]
    flv_url_list: list[str]


# ────────────────────────────────────────────────────────────
# 纯工具函数
# ────────────────────────────────────────────────────────────


class TestBitrateToQuality:
    # bitrate_to_quality: 码率 → 画质代码映射。

    def test_zero_bitrate_returns_od(self) -> None:
        assert bitrate_to_quality(0) == "OD"

    def test_negative_bitrate_returns_od(self) -> None:
        assert bitrate_to_quality(-100) == "OD"

    def test_low_bitrate_returns_ld(self) -> None:
        # LD 上限 600
        assert bitrate_to_quality(500) == "LD"

    def test_boundary_600_returns_ld(self) -> None:
        assert bitrate_to_quality(600) == "LD"

    def test_boundary_601_returns_sd(self) -> None:
        assert bitrate_to_quality(601) == "SD"

    def test_mid_bitrate_returns_hd(self) -> None:
        # HD 上限 1000
        assert bitrate_to_quality(999) == "HD"

    def test_high_bitrate_returns_bd(self) -> None:
        # BD 上限 4000
        assert bitrate_to_quality(3000) == "BD"

    def test_very_high_bitrate_returns_od(self) -> None:
        # OD 无上限（>4000 落入 OD）
        assert bitrate_to_quality(99999) == "OD"

    def test_exact_bd_boundary(self) -> None:
        assert bitrate_to_quality(4000) == "BD"


class TestCodeToZh:
    # code_to_zh: 画质代码 → 中文名。

    def test_known_codes(self) -> None:
        for code, zh in QUALITY_CODE_TO_ZH.items():
            assert code_to_zh(code) == zh

    def test_unknown_code_returns_as_is(self) -> None:
        assert code_to_zh("UNKNOWN") == "UNKNOWN"

    def test_none_returns_empty_string(self) -> None:
        assert code_to_zh(None) == ""

    def test_empty_string_returns_empty_string(self) -> None:
        assert code_to_zh("") == ""


class TestIsDowngrade:
    # is_downgrade: 判定实际画质是否低于请求画质。

    def test_same_quality_not_downgrade(self) -> None:
        assert is_downgrade("HD", "HD") is False

    def test_higher_quality_not_downgrade(self) -> None:
        # OD(0) 请求, HD(2) 实际 → 降级
        assert is_downgrade("OD", "HD") is True

    def test_lower_quality_not_downgrade(self) -> None:
        # SD(3) 请求, HD(2) 实际 → 非降级
        assert is_downgrade("SD", "HD") is False

    def test_none_requested_not_downgrade(self) -> None:
        assert is_downgrade(None, "HD") is False

    def test_none_actual_not_downgrade(self) -> None:
        assert is_downgrade("HD", None) is False

    def test_unknown_code_not_downgrade(self) -> None:
        assert is_downgrade("XX", "HD") is False


class TestPadList:
    # _pad_list: 列表填充到最小长度。

    def test_empty_list_returns_nones(self) -> None:
        result = _pad_list([], min_length=3)
        assert result == [None, None, None]

    def test_short_list_padded(self) -> None:
        result = _pad_list([1, 2], min_length=5)
        assert result == [1, 2, 2, 2, 2]

    def test_exact_length_unchanged(self) -> None:
        result = _pad_list([1, 2, 3], min_length=3)
        assert result == [1, 2, 3]

    def test_longer_list_unchanged(self) -> None:
        result = _pad_list([1, 2, 3, 4], min_length=3)
        assert result == [1, 2, 3, 4]

    def test_default_min_length_is_5(self) -> None:
        result = _pad_list([1])
        assert len(result) == 5
        assert result[0] == 1
        assert all(x == 1 for x in result[1:])


class TestGetQualityIndex:
    # get_quality_index: 解析画质参数。

    def test_none_returns_first(self) -> None:
        name, idx = get_quality_index(None)
        assert name == "OD"
        assert idx == QUALITY_MAPPING["OD"]

    def test_empty_string_returns_first(self) -> None:
        name, idx = get_quality_index("")
        assert name == "OD"

    def test_string_code(self) -> None:
        name, idx = get_quality_index("HD")
        assert name == "HD"
        assert idx == QUALITY_MAPPING["HD"]

    def test_numeric_string(self) -> None:
        # "3" → 第一个字符 3 → keys[3] = "HD"
        name, idx = get_quality_index("3")
        assert name == "HD"
        assert idx == QUALITY_MAPPING["HD"]

    def test_numeric_string_out_of_range(self) -> None:
        # "9" → 第一个字符 9 >= len(keys)=6 → 回退 0 → "OD"
        name, idx = get_quality_index("9")
        assert name == "OD"

    def test_unknown_string_returns_first(self) -> None:
        name, idx = get_quality_index("INVALID")
        assert name == "OD"

    def test_integer_input(self) -> None:
        name, idx = get_quality_index(2)
        # str(2) → "2" → "2".upper() → "2".isdigit() → int("2"[0])=2 → keys[2]="UHD"
        assert name == "UHD"

    def test_case_insensitive(self) -> None:
        name, idx = get_quality_index("hd")
        assert name == "HD"


# ────────────────────────────────────────────────────────────
# 常量一致性校验
# ────────────────────────────────────────────────────────────


class TestConstants:
    # 确保画质相关常量映射保持一致。

    def test_quality_mapping_keys_match_level_keys(self) -> None:
        # QUALITY_LEVEL 是 QUALITY_MAPPING 的超集：额外含蓝光细粒度子档位（BD30/BD20/BD8/BD4）
        assert set(QUALITY_MAPPING.keys()) <= set(QUALITY_LEVEL.keys())
        assert set(BD_SUB_TIERS) == set(QUALITY_LEVEL.keys()) - set(QUALITY_MAPPING.keys())

    def test_quality_mapping_keys_match_bit_keys(self) -> None:
        # QUALITY_MAPPING_BIT 是 QUALITY_MAPPING 的超集：额外含蓝光细粒度子档位
        assert set(QUALITY_MAPPING.keys()) <= set(QUALITY_MAPPING_BIT.keys())
        assert set(BD_SUB_TIERS) == set(QUALITY_MAPPING_BIT.keys()) - set(QUALITY_MAPPING.keys())

    def test_quality_code_to_zh_keys_match_mapping_keys(self) -> None:
        # QUALITY_CODE_TO_ZH 是 QUALITY_MAPPING 的超集：额外含蓝光细粒度子档位中文名
        assert set(QUALITY_MAPPING.keys()) <= set(QUALITY_CODE_TO_ZH.keys())
        assert set(BD_SUB_TIERS) == set(QUALITY_CODE_TO_ZH.keys()) - set(QUALITY_MAPPING.keys())

    def test_bd_sub_tier_level_order(self) -> None:
        # 蓝光子档位等级序：OD/BD(0) > BD30 > BD20 > BD8 > BD4 > UHD > HD > SD > LD
        # （数值越大画质越低；is_downgrade 按 actual > requested 判定）
        levels = [QUALITY_LEVEL[c] for c in ("OD", "BD", "BD30", "BD20", "BD8", "BD4", "UHD", "HD", "SD", "LD")]
        assert levels == sorted(levels)
        assert is_downgrade("BD8", "BD4") is True
        assert is_downgrade("BD8", "BD30") is False
        assert is_downgrade("BD4", "UHD") is True
        assert is_downgrade("UHD", "BD4") is False


# ────────────────────────────────────────────────────────────
# 平台流地址解析（异步 + Mock）
# ────────────────────────────────────────────────────────────


class TestGetDouyinStreamUrl:
    # get_douyin_stream_url: 抖音直播流解析核心路径。

    @pytest.mark.asyncio
    async def test_offline_status_returns_not_live(self) -> None:
        # status != 2 → is_live=False，且离线分支必须短路、不得触发网络可用性校验。
        from src.stream import get_douyin_stream_url

        json_data = {"anchor_name": "test_anchor", "status": 4}
        # 离线分支不应调用 get_response_status；mock 并断言未调用，防止回归。
        with patch("src.stream.get_response_status", new_callable=AsyncMock) as mock_status:
            result = await get_douyin_stream_url(json_data)
            # 边界覆盖：status 键缺失时，d.get("status", 4) 默认判为离线，同样短路。
            result_default = await get_douyin_stream_url({"anchor_name": "test_anchor"})
        assert result["is_live"] is False
        assert result["anchor_name"] == "test_anchor"
        # 离线结果不含流地址相关键，锁定离线契约。
        assert "flv_url" not in result and "m3u8_url" not in result
        # 缺省离线边界：无 status 键也应判离线且不触发网络校验。
        assert result_default["is_live"] is False
        assert "flv_url" not in result_default and "m3u8_url" not in result_default
        mock_status.assert_not_called()

    @pytest.mark.asyncio
    async def test_live_with_flv_and_m3u8(self) -> None:
        # status=2 + flv/m3u8 数据 → 正确选中画质并返回流地址。
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
        # 固化选中结果契约（弱断言仅检查真值/键存在，会漏检选错画质或空 URL 回归）。
        # HD 请求的 flv 索引被截断到 SD，m3u8 索引截断到 HD，故实际质量回落为 SD。
        assert result["flv_url"] == "https://flv.example.com/sd.flv"
        assert result["m3u8_url"] == "https://m3u8.example.com/hd.m3u8"
        assert result["actual_quality"] == "SD"
        assert result["available_qualities"] == ["HD", "SD"]
        assert result["record_url"] == result["m3u8_url"]

    @pytest.mark.asyncio
    async def test_live_only_flv_no_m3u8(self) -> None:
        # 仅有 FLV 无 m3u8 → 跳过可用性校验，不降级。
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
        # 不降级：请求的 OD 画质应被原样保留，且正确选中 OD 的 FLV 地址
        assert result["quality"] == "OD"
        assert result["actual_quality"] == "OD"
        assert result["flv_url"] == "https://flv.example.com/od.flv"
        # FLV-only 路径无 m3u8，record_url 应回退为选中的 FLV 地址（与有 m3u8 用例的 record_url 契约一致）。
        assert result["record_url"] == "https://flv.example.com/od.flv"
        assert result["available_qualities"] == ["OD"]

    @pytest.mark.asyncio
    async def test_m3u8_unreachable_triggers_fallback(self) -> None:
        # m3u8 不可达 → 降级到相邻画质。
        from src.stream import get_douyin_stream_url

        json_data = {
            "anchor_name": "anchor_c",
            "status": 2,
            "stream_url": {
                "flv_pull_url": {"HD": "https://flv.example.com/hd.flv", "SD": "https://flv.example.com/sd.flv"},
                "hls_pull_url_map": {
                    "HD": "https://m3u8.example.com/hd.m3u8",
                    "SD": "https://m3u8.example.com/sd.m3u8",
                },
                "hevc_flv_url": None,
            },
        }
        with patch("src.stream.get_response_status", new_callable=AsyncMock, return_value=False):
            result = await get_douyin_stream_url(json_data, video_quality="HD")

        assert result["is_live"] is True
        # 降级后应切换到 SD
        assert result.get("actual_quality") in ("SD", "HD")


class TestGetHuyaStreamUrl:
    # get_huya_stream_url: 虎牙 web 路径 HLS 解析。枚举全部 CDN 候选（不再固定取 index0），
    # HS-first 排序，使用房间页内嵌防盗链参数、统一 http（https 实测 403），
    # 全部候选注入 m3u8_url_list/flv_url_list 供 select_source_url 按可达性校验选用。

    @staticmethod
    def _json(ordered_cdn_types: list[str]) -> dict[str, object]:
        # 复刻 room 179966 房间页 gameStreamInfoList 结构（含 sCdnType/sStreamName/各 URL/反链参数）
        base = {
            "AL": (
                "http://al.hls.huya.com/src",
                "http://al.flv.huya.com/src",
                "wsSecret=al&wsTime=6a&ctype=huya_live&fs=bgct",
            ),
            "TX": (
                "http://tx.hls.huya.com/src",
                "http://tx.flv.huya.com/src",
                "wsSecret=tx&wsTime=6a&ctype=huya_live&fs=bgct",
            ),
            "HS": (
                "http://hs.hls.huya.com/src",
                "http://hs.flv.huya.com/src",
                "wsSecret=hs&wsTime=6a&ctype=huya_live&fs=bgct",
            ),
        }
        stream_list = []
        for cdn in ordered_cdn_types:
            hls, flv, anti = base[cdn]
            stream_list.append(
                {
                    "sCdnType": cdn,
                    "sStreamName": "STREAMNAME",
                    "sFlvUrl": flv,
                    "sFlvUrlSuffix": "flv",
                    "sFlvAntiCode": anti,
                    "sHlsUrl": hls,
                    "sHlsUrlSuffix": "m3u8",
                    "sHlsAntiCode": anti,
                }
            )
        return {
            "data": [{"gameLiveInfo": {"nick": "anchor", "introduction": "title"}, "gameStreamInfoList": stream_list}]
        }

    @pytest.mark.asyncio
    async def test_enumerates_all_cdn_candidates_hs_first(self) -> None:
        # room 179966 实测：gameStreamInfoList 顺序为 [AL, X, HS]（AL 为 index0 且离线）。
        # 修复前固定取 index0=AL 导致 HLS 整轮不可达；修复后枚举全部候选、HS 排首位选中。
        from src.stream import get_huya_stream_url

        json_data = self._json(["AL", "TX", "HS"])
        result = cast("HuyaResult", await get_huya_stream_url(cast(dict[str, object], json_data)))
        assert result["is_live"] is True
        # 主源为 HS（不再因 AL 在 index0 而选到离线 AL）
        assert (
            result["m3u8_url"]
            == "http://hs.hls.huya.com/src/STREAMNAME.m3u8?wsSecret=hs&wsTime=6a&ctype=huya_live&fs=bgct"
        )
        # 候选列表按 HS→TX→AL（HS-first）
        assert result["m3u8_url_list"] == [
            "http://hs.hls.huya.com/src/STREAMNAME.m3u8?wsSecret=hs&wsTime=6a&ctype=huya_live&fs=bgct",
            "http://tx.hls.huya.com/src/STREAMNAME.m3u8?wsSecret=tx&wsTime=6a&ctype=huya_live&fs=bgct",
            "http://al.hls.huya.com/src/STREAMNAME.m3u8?wsSecret=al&wsTime=6a&ctype=huya_live&fs=bgct",
        ]
        # 全部为 http（无 https 化），且三条 FLV 候选齐全
        assert all(u.startswith("http://") for u in result["m3u8_url_list"] + result["flv_url_list"])
        assert len(result["flv_url_list"]) == 3

    @pytest.mark.asyncio
    async def test_https_in_input_downgraded_to_http(self) -> None:
        # 房间页若返回 https 形式的 CDN URL，必须降为 http（https 实测 403）
        from src.stream import get_huya_stream_url

        json_data = {
            "data": [
                {
                    "gameLiveInfo": {"nick": "anchor", "introduction": "title"},
                    "gameStreamInfoList": [
                        {
                            "sCdnType": "HS",
                            "sStreamName": "STREAMNAME",
                            "sFlvUrl": "https://hs.flv.huya.com/src",
                            "sFlvUrlSuffix": "flv",
                            "sFlvAntiCode": "wsSecret=hs&wsTime=6a&ctype=huya_live&fs=bgct",
                            "sHlsUrl": "https://hs.hls.huya.com/src",
                            "sHlsUrlSuffix": "m3u8",
                            "sHlsAntiCode": "wsSecret=hs&wsTime=6a&ctype=huya_live&fs=bgct",
                        }
                    ],
                }
            ]
        }
        result = cast("HuyaResult", await get_huya_stream_url(cast(dict[str, object], json_data)))
        assert result["m3u8_url"].startswith("http://")
        assert result["m3u8_url_list"][0].startswith("http://")

    @pytest.mark.asyncio
    async def test_empty_game_stream_info_list_returns_not_live(self) -> None:
        from src.stream import get_huya_stream_url

        json_data = {"data": [{"gameLiveInfo": {"nick": "anchor"}, "gameStreamInfoList": []}]}
        result = cast("HuyaResult", await get_huya_stream_url(cast(dict[str, object], json_data)))
        assert result["is_live"] is False


class TestGetDouyuStreamUrl:
    # get_douyu_stream_url: 斗鱼流解析 + FLV→m3u8 同 token HLS 候选。

    @pytest.mark.asyncio
    async def test_offline_returns_not_live(self) -> None:
        from src.stream import get_douyu_stream_url

        result = await get_douyu_stream_url({"anchor_name": "dy_off", "is_live": False})
        assert result["is_live"] is False
        assert "flv_url" not in result and "m3u8_url" not in result

    @pytest.mark.asyncio
    async def test_flv_url_carries_m3u8_candidate(self) -> None:
        # 同 token 的 .flv → .m3u8 改写：查询串原样保留，FLV/record_url 不受影响。
        from src.stream import get_douyu_stream_url

        json_data = {"anchor_name": "dy_live", "is_live": True, "room_id": 100}
        flv_data = {
            "data": {
                "rtmp_url": "https://hw1a.douyucdn2.cn/live",
                "rtmp_live": "100rPCLP.flv?wsAuth=abc&token=t",
                "rate": 0,
            }
        }
        with patch("src.stream.get_douyu_stream_data", new_callable=AsyncMock, return_value=flv_data):
            result = await get_douyu_stream_url(json_data, video_quality="OD")
        assert result["is_live"] is True
        assert result["flv_url"] == "https://hw1a.douyucdn2.cn/live/100rPCLP.flv?wsAuth=abc&token=t"
        assert result["record_url"] == result["flv_url"]
        assert result["m3u8_url"] == "https://hw1a.douyucdn2.cn/live/100rPCLP.m3u8?wsAuth=abc&token=t"

    @pytest.mark.asyncio
    async def test_flv_without_query_keeps_clean_m3u8(self) -> None:
        # 无查询串的 FLV 改写后不得残留悬空 "?"
        from src.stream import get_douyu_stream_url

        json_data = {"anchor_name": "dy_live", "is_live": True, "room_id": 999}
        flv_data = {"data": {"rtmp_url": "https://x.douyucdn2.cn/live", "rtmp_live": "999x.flv", "rate": 0}}
        with patch("src.stream.get_douyu_stream_data", new_callable=AsyncMock, return_value=flv_data):
            result = await get_douyu_stream_url(json_data)
        assert result["m3u8_url"] == "https://x.douyucdn2.cn/live/999x.m3u8"

    @pytest.mark.asyncio
    async def test_non_flv_rtmp_live_has_no_m3u8(self) -> None:
        # rtmp_live 非 .flv 后缀（如 h265 流）不改写，避免伪造不可用的 m3u8 候选
        from src.stream import get_douyu_stream_url

        json_data = {"anchor_name": "dy_h265", "is_live": True, "room_id": 888}
        flv_data = {"data": {"rtmp_url": "https://x.douyucdn2.cn/live", "rtmp_live": "888x.xsls?wsAuth=abc", "rate": 0}}
        with patch("src.stream.get_douyu_stream_data", new_callable=AsyncMock, return_value=flv_data):
            result = await get_douyu_stream_url(json_data)
        assert result["flv_url"] == "https://x.douyucdn2.cn/live/888x.xsls?wsAuth=abc"
        assert "m3u8_url" not in result

    @pytest.mark.asyncio
    async def test_empty_rtmp_live_returns_no_urls(self) -> None:
        # rtmp_live 为空（风控/边界）：is_live=True 但无流地址，交由 select_source_url 告警
        from src.stream import get_douyu_stream_url

        json_data = {"anchor_name": "dy_edge", "is_live": True, "room_id": 777}
        flv_data = {"data": {"rtmp_url": "", "rtmp_live": "", "rate": 0}}
        with patch("src.stream.get_douyu_stream_data", new_callable=AsyncMock, return_value=flv_data):
            result = await get_douyu_stream_url(json_data)
        assert result["is_live"] is True
        assert "flv_url" not in result and "m3u8_url" not in result


class TestGetTiktokStreamUrl:
    # get_tiktok_stream_url: TikTok 直播流解析。

    @pytest.mark.asyncio
    async def test_none_json_returns_not_live(self) -> None:
        from src.stream import get_tiktok_stream_url

        result = await get_tiktok_stream_url(None)
        assert result["is_live"] is False

    @pytest.mark.asyncio
    async def test_offline_user_status(self) -> None:
        from src.stream import get_tiktok_stream_url

        json_data = {
            "LiveRoom": {
                "liveRoomUserInfo": {"user": {"status": 0, "nickname": "Test", "uniqueId": "test_id"}},
                "liveRoom": {},
            }
        }
        result = await get_tiktok_stream_url(cast(dict[str, object], json_data))
        assert result["is_live"] is False
        assert result["anchor_name"] == "Test-test_id"
        # 离线不应携带直播相关字段，防止误判为直播（与抖音离线用例契约一致）。
        assert (
            "flv_url" not in result
            and "m3u8_url" not in result
            and "record_url" not in result
            and "quality" not in result
        )

    @pytest.mark.asyncio
    async def test_live_with_stream_data(self) -> None:
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
            result = await get_tiktok_stream_url(cast(dict[str, object], json_data), video_quality="OD")

        assert result["is_live"] is True
        assert result["anchor_name"] == "Streamer-streamer1"
        assert result["title"] == "Live Now"
        # 固化选中结果契约（弱断言仅检查真值，会漏检选错画质或空 URL 回归）。
        # OD 请求索引截断到末档 → 选中最高码率 origin（BD），flv_url 回退为 m3u8。
        assert result["m3u8_url"] == "https://tiktok.example.com/origin.m3u8?codec=h264"
        assert result["flv_url"] == "https://tiktok.example.com/origin.m3u8?codec=h264"
        assert result["actual_quality"] == "BD"
        assert result["record_url"] == result["m3u8_url"]


class TestGetKuaishouStreamUrl:
    # get_kuaishou_stream_url: 快手直播流解析。

    @pytest.mark.asyncio
    async def test_not_live(self) -> None:
        from src.stream import get_kuaishou_stream_url

        json_data = {"type": 0, "is_live": False, "anchor_name": "ks_anchor"}
        result = await get_kuaishou_stream_url(json_data)
        assert result["is_live"] is False

    @pytest.mark.asyncio
    async def test_live_with_bitrate(self) -> None:
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
    async def test_type1_not_live_returns_directly(self) -> None:
        from src.stream import get_kuaishou_stream_url

        json_data = {"type": 1, "is_live": False, "anchor_name": "ks_offline"}
        result = await get_kuaishou_stream_url(json_data)
        assert result == json_data


class TestGetYyStreamUrl:
    # get_yy_stream_url: YY 直播流解析。

    @pytest.mark.asyncio
    async def test_no_avp_info(self) -> None:
        from src.stream import get_yy_stream_url

        json_data = {"anchor_name": "yy_anchor"}
        result = await get_yy_stream_url(cast(dict[str, object], json_data))
        assert result["is_live"] is False

    @pytest.mark.asyncio
    async def test_live_with_cdn(self) -> None:
        from src.stream import get_yy_stream_url

        json_data = {
            "anchor_name": "yy_live",
            "title": "YY Live",
            "avp_info_res": {"stream_line_addr": {"line1": {"cdn_info": {"url": "https://yy.example.com/live.flv"}}}},
        }
        result = await get_yy_stream_url(cast(dict[str, object], json_data))
        assert result["is_live"] is True
        assert result["flv_url"] == "https://yy.example.com/live.flv"
        assert result["record_url"] == "https://yy.example.com/live.flv"


class TestGetNeteaseStreamUrl:
    # get_netease_stream_url: 网易 CC 直播流解析。

    @pytest.mark.asyncio
    async def test_not_live_returns_directly(self) -> None:
        from src.stream import get_netease_stream_url

        json_data = {"is_live": False, "anchor_name": "netease_off"}
        result = await get_netease_stream_url(json_data)
        # 非直播时函数短路直接返回原始 dict（同一对象），不构造新结果。
        # 用同一性断言锁定「原样返回」契约，杜绝返回被篡改副本或注入空字段的回归。
        assert result is json_data

    @pytest.mark.asyncio
    async def test_live_with_stream_list(self) -> None:
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
        # 固化选中结果契约（弱断言仅检查真值/键存在，会漏检选错画质或空 URL 回归）。
        # HD 请求映射到 high 分辨率 CDN，flv_url 锁定为 high.flv；record_url 与 flv_url 一致。
        assert result["flv_url"] == "https://ali.example.com/high.flv"
        assert result["record_url"] == result["flv_url"]
        assert result["m3u8_url"] == "https://cc.example.com/live.m3u8"
        assert result["actual_quality"] == "HD"
        assert result["available_qualities"] == ["UHD", "HD"]


class TestGetStreamUrl:
    # get_stream_url: 通用直播流解析入口。

    @pytest.mark.asyncio
    async def test_not_live_returns_directly(self) -> None:
        from src.stream import get_stream_url

        json_data = {"is_live": False, "anchor_name": "test"}
        result = await get_stream_url(json_data)
        # 非直播时函数短路直接返回原始 dict（同一对象），不构造新结果。
        # 用同一性断言锁定「原样返回」契约，杜绝返回被篡改副本或注入空字段的回归。
        assert result is json_data

    @pytest.mark.asyncio
    async def test_empty_play_url_list(self) -> None:
        from src.stream import get_stream_url

        json_data = {"is_live": True, "anchor_name": "test", "play_url_list": []}
        result = await get_stream_url(json_data)
        # 空 play_url_list 时函数短路直接返回原始 dict（同一对象），不构造新结果。
        # 用同一性断言锁定「原样返回」契约，杜绝返回被篡改副本或注入空字段的回归。
        assert result is json_data

    @pytest.mark.asyncio
    async def test_m3u8_type(self) -> None:
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
        # url_type="m3u8" 且未传 hls_extra_key 时，m3u8_url 取整个 play_url_list[0] 字典（OD 选中索引 0）。
        # 精确锁定选中值与 record_url 契约，杜绝「真值/键存在」的假绿断言漏检空值/错选回归。
        assert result["m3u8_url"] == {"m3u8": "https://example.com/od.m3u8", "flv": "https://example.com/od.flv"}
        assert result["record_url"] == result["m3u8_url"]
        assert result["quality"] == "OD"

    @pytest.mark.asyncio
    async def test_flv_type(self) -> None:
        from src.stream import get_stream_url

        json_data = {
            "is_live": True,
            "anchor_name": "generic",
            "title": "Generic Live",
            "play_url_list": [{"flv": "https://example.com/od.flv"}],
        }
        result = await get_stream_url(json_data, url_type="flv")
        assert result["is_live"] is True
        # url_type="flv" 且未传 flv_extra_key 时，flv_url 取整个 play_url_list[0] 字典。
        # 精确锁定选中值与 record_url 契约，杜绝「真值/键存在」的假绿断言漏检空值/错选回归。
        assert result["flv_url"] == {"flv": "https://example.com/od.flv"}
        assert result["record_url"] == result["flv_url"]

    @pytest.mark.asyncio
    async def test_all_type(self) -> None:
        from src.stream import get_stream_url

        json_data = {
            "is_live": True,
            "anchor_name": "generic",
            "title": "Generic Live",
            "play_url_list": [{"m3u8": "https://example.com/a.m3u8", "flv": "https://example.com/a.flv"}],
        }
        result = await get_stream_url(json_data, url_type="all")
        assert result["is_live"] is True
        # url_type="all" 且未传 hls_extra_key/flv_extra_key 时，m3u8_url/flv_url 取整个 play_url_list[0] 字典。
        # 精确锁定选中值与 record_url 契约，杜绝「键存在即可」的假绿断言漏检空值/错选回归。
        assert result["m3u8_url"] == {"m3u8": "https://example.com/a.m3u8", "flv": "https://example.com/a.flv"}
        assert result["flv_url"] == {"m3u8": "https://example.com/a.m3u8", "flv": "https://example.com/a.flv"}
        assert result["record_url"] == result["m3u8_url"]
