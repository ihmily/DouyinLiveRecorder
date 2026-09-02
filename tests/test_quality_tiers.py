# -*- coding: utf-8 -*-
# 虎牙/斗鱼清晰度档位专项测试：细粒度蓝光档位枚举、选档拉流、不可用降级与错误提示。
#
# 实测依据（2026-08-29）：
# - 虎牙 huya.com/chuhe（bitRate=30000）：ratio 即码率上限 kbps——
#   0=原画(2560x1440@60) / 30000=蓝光30M(1080p60) / 20000=蓝光20M(1080p60)
#   / 8000=蓝光8M(1080p60) / 4000=蓝光4M(1080p30) / 2000=超清(720p30) / 500=流畅(450p24)。
# - 斗鱼 douyu.com/3168536：rate 0=原画 / 8200=蓝光8M / 4000=蓝光4M(下发 rate=4)
#   / 3=超清 / 2=高清 / 1=流畅；服务端对不存在档位自动就近钳制（8200→4）。

from typing import cast
from unittest.mock import AsyncMock, patch

import pytest

import main  # noqa: F401  先完整初始化 main，打破 stream_select<->main 的循环导入
from src.stream import get_douyu_stream_url, get_huya_stream_url, get_quality_index
from src.stream_select import get_quality_code

# ────────────────────────────────────────────────────────────
# 中文名 → 代码映射
# ────────────────────────────────────────────────────────────


class TestGetQualityCodeSubTiers:
    # get_quality_code: 蓝光细粒度档位中文名 → 代码。

    @pytest.mark.parametrize(
        ("zh", "code"),
        [("蓝光4M", "BD4"), ("蓝光8M", "BD8"), ("蓝光20M", "BD20"), ("蓝光30M", "BD30")],
    )
    def test_sub_tier_names(self, zh: str, code: str) -> None:
        assert get_quality_code(zh) == code

    def test_legacy_names_unchanged(self) -> None:
        assert get_quality_code("原画") == "OD"
        assert get_quality_code("蓝光") == "BD"
        assert get_quality_code("超清") == "UHD"
        assert get_quality_code("流畅") == "LD"

    def test_unknown_falls_back_to_od(self) -> None:
        assert get_quality_code("蓝光16M") == "OD"


class TestGetQualityIndexSubTiers:
    # get_quality_index: 蓝光子档位折叠到 BD 槽位（通用索引平台退化为「蓝光」）。

    @pytest.mark.parametrize("code", ["BD4", "BD8", "BD20", "BD30"])
    def test_sub_tiers_fold_to_bd(self, code: str) -> None:
        from src.stream import QUALITY_MAPPING

        name, idx = get_quality_index(code)
        assert name == "BD"
        assert idx == QUALITY_MAPPING["BD"]

    def test_numeric_semantics_unchanged(self) -> None:
        # 数字输入 0-5 的语义不受子档位键影响（"3" → HD）
        name, _ = get_quality_index("3")
        assert name == "HD"


# ────────────────────────────────────────────────────────────
# 虎牙：细粒度档位选档与降级
# ────────────────────────────────────────────────────────────


def _huya_json(
    bit_rate: int = 0,
    exsphd: str | None = None,
    cdn_type: str = "HS",
) -> dict[str, object]:
    # 构造 get_huya_stream_url 输入：单 CDN、可选 bitRate 与 exsphd 档位表
    anti = "wsSecret=hs&wsTime=6a&ctype=huya_live&fs=bgct"
    if exsphd is not None:
        anti += f"&exsphd={exsphd}"
    game_live_info: dict[str, object] = {"nick": "anchor", "introduction": "title"}
    if bit_rate:
        game_live_info["bitRate"] = bit_rate
    return {
        "data": [
            {
                "gameLiveInfo": game_live_info,
                "gameStreamInfoList": [
                    {
                        "sCdnType": cdn_type,
                        "sStreamName": "STREAMNAME",
                        "sFlvUrl": "http://hs.flv.huya.com/src",
                        "sFlvUrlSuffix": "flv",
                        "sFlvAntiCode": anti,
                        "sHlsUrl": "http://hs.hls.huya.com/src",
                        "sHlsUrlSuffix": "m3u8",
                        "sHlsAntiCode": anti,
                    }
                ],
            }
        ]
    }


class TestHuyaSubTiers:
    # get_huya_stream_url: 蓝光细粒度档位（ratio 即码率上限 kbps）。

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("code", "ratio"),
        [("BD30", "30000"), ("BD20", "20000"), ("BD8", "8000"), ("BD4", "4000")],
    )
    async def test_available_tier_appends_ratio(self, code: str, ratio: str) -> None:
        # bitRate=30000 的房间四档全可用：URL 追加 &ratio=<码率>，actual 即请求档
        result = await get_huya_stream_url(_huya_json(bit_rate=30000), video_quality=code)
        assert result["is_live"] is True
        assert str(result["flv_url"]).endswith(f"&ratio={ratio}")
        assert str(result["m3u8_url"]).endswith(f"&ratio={ratio}")
        assert result["quality"] == code
        assert result["actual_quality"] == code
        # 可用档位枚举含全部蓝光子档位
        assert result["available_qualities"] == ["OD", "BD30", "BD20", "BD8", "BD4", "UHD", "LD"]

    @pytest.mark.asyncio
    async def test_unavailable_tier_degrades_to_nearest_lower(self) -> None:
        # bitRate=8000 的房间请求蓝光30M：降级到蓝光8M(ratio=8000)
        result = await get_huya_stream_url(_huya_json(bit_rate=8000), video_quality="BD30")
        assert str(result["flv_url"]).endswith("&ratio=8000")
        assert result["quality"] == "BD30"
        assert result["actual_quality"] == "BD8"

    @pytest.mark.asyncio
    async def test_exsphd_table_drives_degradation(self) -> None:
        # exsphd 档位表优先：房间仅 0/500/2000 时请求蓝光4M → 降级超清(ratio=2000)
        result = await get_huya_stream_url(
            _huya_json(bit_rate=2000, exsphd="264_0 264_500 264_2000"), video_quality="BD4"
        )
        assert str(result["flv_url"]).endswith("&ratio=2000")
        assert result["actual_quality"] == "UHD"

    @pytest.mark.asyncio
    async def test_low_capacity_room_degrades_to_lowest_available(self) -> None:
        # bitRate=2000 的小码率房间请求蓝光30M：一路降级到超清(ratio=2000)
        result = await get_huya_stream_url(_huya_json(bit_rate=2000), video_quality="BD30")
        assert str(result["flv_url"]).endswith("&ratio=2000")
        assert result["quality"] == "BD30"
        assert result["actual_quality"] == "UHD"

    @pytest.mark.asyncio
    async def test_no_lower_tier_falls_back_to_origin(self) -> None:
        # exsphd 只列出高于请求档的档位（无更低档可用）：不附加 ratio，按原画拉流
        result = await get_huya_stream_url(_huya_json(exsphd="264_0 264_8000"), video_quality="BD4")
        assert "ratio=" not in str(result["flv_url"])
        assert result["actual_quality"] == "OD"

    @pytest.mark.asyncio
    async def test_unknown_capacity_requests_directly(self) -> None:
        # bitRate 缺失且无 exsphd：不做本地降级判断，直接按请求档拉流（交由服务端决定）
        result = await get_huya_stream_url(_huya_json(), video_quality="BD8")
        assert str(result["flv_url"]).endswith("&ratio=8000")
        assert result["actual_quality"] == "BD8"

    @pytest.mark.asyncio
    async def test_od_request_unchanged(self) -> None:
        # 原画请求不附加 ratio（保持原始防盗链参数），actual=OD
        result = await get_huya_stream_url(_huya_json(bit_rate=30000), video_quality="OD")
        assert "ratio=" not in str(result["flv_url"])
        assert result["actual_quality"] == "OD"

    @pytest.mark.asyncio
    async def test_legacy_uhd_via_exsphd_labels(self) -> None:
        # 旧档位（UHD/HD/SD/LD）继续走 exsphd 标签映射，行为不变
        result = await get_huya_stream_url(_huya_json(exsphd="264_0 264_500 264_2000 264_8000"), video_quality="UHD")
        # qlist 降序 [8000, 2000, 500, 0] → UHD=8000
        assert str(result["flv_url"]).endswith("&ratio=8000")
        assert result["actual_quality"] == "UHD"


# ────────────────────────────────────────────────────────────
# 斗鱼：rate 选档、服务端钳制回采与被限制降级
# ────────────────────────────────────────────────────────────


def _douyu_flv(rate: int, suffix: str = "") -> dict[str, object]:
    # 构造 get_douyu_stream_data 成功响应
    return {
        "error": 0,
        "data": {
            "rtmp_url": "https://hw.douyucdn2.cn/live",
            "rtmp_live": f"100x{suffix}.flv?wsAuth=abc&token=t",
            "rate": rate,
        },
    }


class TestDouyuSubTiers:
    # get_douyu_stream_url: 细粒度蓝光档位 + 降级回退。

    @pytest.mark.asyncio
    async def test_bd4_request_rate_and_readback(self) -> None:
        # 蓝光4M：请求 rate=4000，服务端下发 rate=4 → actual=BD4
        json_data = {"anchor_name": "dy", "is_live": True, "room_id": 100}
        with patch("src.stream.get_douyu_stream_data", new_callable=AsyncMock) as mock:
            mock.return_value = _douyu_flv(rate=4, suffix="_4000")
            result = await get_douyu_stream_url(cast(dict[str, object], json_data), video_quality="BD4")
        mock.assert_awaited_once()
        # await_args 类型为 _Call | None（mock 未被 await 时为 None）：mypy 无法从
        # assert_awaited_once 收窄，需显式判空；兼作运行时的明确失败点
        assert mock.await_args is not None
        assert mock.await_args.args[1] == "4000"
        assert result["quality"] == "BD4"
        assert result["actual_quality"] == "BD4"
        assert "_4000.flv" in str(result["flv_url"])

    @pytest.mark.asyncio
    async def test_bd8_clamped_by_server(self) -> None:
        # 房间无蓝光8M：请求 rate=8200，服务端钳制下发 rate=4 → actual=BD4（触发降级告警链路）
        json_data = {"anchor_name": "dy", "is_live": True, "room_id": 100}
        with patch("src.stream.get_douyu_stream_data", new_callable=AsyncMock) as mock:
            mock.return_value = _douyu_flv(rate=4, suffix="_4000")
            result = await get_douyu_stream_url(cast(dict[str, object], json_data), video_quality="BD8")
        assert mock.await_args is not None
        assert mock.await_args.args[1] == "8200"
        assert result["quality"] == "BD8"
        assert result["actual_quality"] == "BD4"

    @pytest.mark.asyncio
    async def test_bd30_20_fold_to_bd8(self) -> None:
        # 斗鱼无蓝光30M/20M：按蓝光8M(rate=8200)请求
        json_data = {"anchor_name": "dy", "is_live": True, "room_id": 100}
        with patch("src.stream.get_douyu_stream_data", new_callable=AsyncMock) as mock:
            mock.return_value = _douyu_flv(rate=8200)
            result = await get_douyu_stream_url(cast(dict[str, object], json_data), video_quality="BD30")
        assert mock.await_args is not None
        assert mock.await_args.args[1] == "8200"
        assert result["actual_quality"] == "BD8"

    @pytest.mark.asyncio
    async def test_od_success_single_call(self) -> None:
        # 原画可用：单次请求 rate=0，下发 rate=0 → actual=OD
        json_data = {"anchor_name": "dy", "is_live": True, "room_id": 100}
        with patch("src.stream.get_douyu_stream_data", new_callable=AsyncMock) as mock:
            mock.return_value = _douyu_flv(rate=0)
            result = await get_douyu_stream_url(cast(dict[str, object], json_data), video_quality="OD")
        mock.assert_awaited_once()
        assert mock.await_args is not None
        assert mock.await_args.args[1] == "0"
        assert result["actual_quality"] == "OD"

    @pytest.mark.asyncio
    async def test_od_restricted_degrades_and_retries(self) -> None:
        # 原画被限制（游客态 error 响应）：降级链 0 → 8200 → 4000，第三个成功
        json_data = {"anchor_name": "dy", "is_live": True, "room_id": 100}
        error_resp: dict[str, object] = {"error": 20105, "msg": "请登录后观看", "data": {}}
        with patch("src.stream.get_douyu_stream_data", new_callable=AsyncMock) as mock:
            mock.side_effect = [error_resp, error_resp, _douyu_flv(rate=4, suffix="_4000")]
            result = await get_douyu_stream_url(cast(dict[str, object], json_data), video_quality="OD")
        assert mock.await_count == 3
        assert [c.args[1] for c in mock.await_args_list] == ["0", "8200", "4000"]
        assert result["actual_quality"] == "BD4"
        assert str(result["flv_url"]).startswith("https://hw.douyucdn2.cn/live/")

    @pytest.mark.asyncio
    async def test_all_rates_failed_returns_no_urls(self) -> None:
        # 全部档位失败：保持 is_live=True 但无流地址的既有契约（交由上层告警重试）
        json_data = {"anchor_name": "dy", "is_live": True, "room_id": 100}
        error_resp: dict[str, object] = {"error": 500, "msg": "server error", "data": {}}
        with patch("src.stream.get_douyu_stream_data", new_callable=AsyncMock, return_value=error_resp):
            result = await get_douyu_stream_url(cast(dict[str, object], json_data), video_quality="BD4")
        assert result["is_live"] is True
        assert "flv_url" not in result and "m3u8_url" not in result

    @pytest.mark.asyncio
    async def test_legacy_od_rate_mapping_unchanged(self) -> None:
        # 旧档位语义不变：超清 → rate=3 → actual=UHD
        json_data = {"anchor_name": "dy", "is_live": True, "room_id": 100}
        with patch("src.stream.get_douyu_stream_data", new_callable=AsyncMock) as mock:
            mock.return_value = _douyu_flv(rate=3, suffix="_2000")
            result = await get_douyu_stream_url(cast(dict[str, object], json_data), video_quality="UHD")
        assert mock.await_args is not None
        assert mock.await_args.args[1] == "3"
        assert result["actual_quality"] == "UHD"
