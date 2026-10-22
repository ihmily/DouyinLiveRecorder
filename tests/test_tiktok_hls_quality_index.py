# M-11 回归锁（2026-09-29 审查）：TikTok 选档时 FLV 与 HLS 两个列表必须各自基于「用户请求档」的
# 原始索引独立钳制，不得把被 FLV 长度钳过的索引再喂给 HLS。
#
# 被测生产实现：src/stream.py::get_tiktok_stream_url 的 flv_quality_index / m3u8_quality_index
# 两行（主选档）与探针失败后的 fallback_base 回退段；对照实现是同文件上方抖音分支的
# flv_idx / m3u8_idx 两行。
#
# 失效形态（修复前）：
#   quality_index = min(quality_index, len(flv_url_list) - 1) if flv_url_list else 0
#   m3u8_quality_index = min(quality_index, len(m3u8_url_list) - 1) if m3u8_url_list else 0
# HLS-only 房间（get_video_quality_url 对只下发 hls 的条目仍会产出 {"url": ""} 的 FLV 项、
# 随后被过滤成空列表）里 quality_index 被无条件归零 → 用户选任何档位都拉码率最高的首档；
# actual_quality 回采到高档后 main.py 的降级告警恒不触发（高档不属于「降级」，见下方
# TestDowngradeWarningConvention），于是「选流畅实拉原画」完全静默、白烧带宽。
#
# 打桩边界：只替换网络层探针 src.stream.get_response_status（真实实现要打真机 CDN）；
# 档位排序、_pad_list 补齐、空地址过滤、索引钳制与 bitrate_to_quality 回采全部走生产代码。
# 变异验证：把上述两行改回原式后，本文件 HLS-only 选档、不等长独立钳制、回退基准三组用例立即变红。

import json
from typing import Any, cast
from unittest.mock import AsyncMock, patch

import pytest

# 先完整初始化 main，打破 stream_select<->main 的循环导入（同 tests/test_quality_tiers.py 口径）：
# src/stream.py::_probe_headers 就地延迟导入 src.stream_select，而 stream_select 顶层又 `import main`；
# 单文件跑本用例时若不先把 main 装好，延迟导入拿到的是半初始化的 stream_select →
# ImportError 被 trace_error_decorator 吞成「未开播」，断言会表现为 is_live=False 的假因。
import main  # noqa: F401
from src.stream import bitrate_to_quality, get_tiktok_stream_url, is_downgrade

_HOST = "https://tiktok.example.com"

# 档位标签 → 码率：取值必须让 bitrate_to_quality 反查回同名档位，否则下面的参数化断言自证失效。
# 9000→OD 4000→BD 2000→UHD 1000→HD 800→SD 600→LD（容量序见 src/stream.py::bitrate_to_quality）
_TIERS: tuple[tuple[str, int], ...] = (
    ("od", 9000),
    ("bd", 4000),
    ("uhd", 2000),
    ("hd", 1000),
    ("sd", 800),
    ("ld", 600),
)


def _entry(tag: str, bitrate: int, *, flv: bool = True, hls: bool = True) -> dict[str, Any]:
    # 构造一路 TikTok stream 条目：sdk_params 是 JSON 字符串（生产解析走 json.loads），
    # resolution 随行递增以保证排序结果与 _TIERS 的顺序一致（排序键首先是 -vbitrate）。
    idx = next(i for i, (name, _b) in enumerate(_TIERS) if name == tag)
    node: dict[str, Any] = {
        "main": {
            "sdk_params": json.dumps({"vbitrate": bitrate, "VCodec": "h264", "resolution": f"{1280 + idx}x{720 + idx}"})
        }
    }
    if flv:
        node["flv"] = f"{_HOST}/{tag}.flv"
    if hls:
        node["hls"] = f"{_HOST}/{tag}.m3u8"
    return node


def _payload(data: dict[str, Any]) -> dict[str, object]:
    return {
        "LiveRoom": {
            "liveRoomUserInfo": {"user": {"status": 2, "nickname": "Streamer", "uniqueId": "streamer1"}},
            "liveRoom": {
                "title": "Live Now",
                "streamData": {"pull_data": {"stream_data": json.dumps({"data": data})}},
            },
        }
    }


def _streams(tags: list[str], *, flv: bool, hls: bool) -> dict[str, Any]:
    return {tag: _entry(tag, bitrate, flv=flv, hls=hls) for tag, bitrate in _TIERS if tag in tags}


class TestHlsOnlyQualityIndex:
    # 失效面①：HLS-only 房间（FLV 侧过滤后为空）此前恒取首档。

    @pytest.mark.parametrize(
        "requested,expected_tag,expected_code",
        [
            ("OD", "od", "OD"),
            ("BD", "bd", "BD"),
            ("UHD", "uhd", "UHD"),
            ("HD", "hd", "HD"),
            ("SD", "sd", "SD"),
            ("LD", "ld", "LD"),
        ],
    )
    async def test_hls_only_room_uses_requested_index(
        self, requested: str, expected_tag: str, expected_code: str
    ) -> None:
        # 六个 HLS 档位齐全的房间：请求哪一档就必须拉哪一档（修复前一律落 od = 9000kbps）。
        payload = _payload(_streams([t for t, _b in _TIERS], flv=False, hls=True))
        with patch("src.stream.get_response_status", new_callable=AsyncMock, return_value=True):
            result = await get_tiktok_stream_url(cast(dict[str, object], payload), video_quality=requested)

        assert result["is_live"] is True
        assert result["quality"] == requested
        assert str(result["m3u8_url"]).startswith(f"{_HOST}/{expected_tag}.m3u8")
        # MID-15：FLV 通道为空就诚实地空，不得用 m3u8 顶替。
        assert result["flv_url"] == ""
        assert result["record_url"] == result["m3u8_url"]
        # actual_quality 由**选中项**的 vbitrate 回采（MID-16），与请求档一致时不该有任何降级暗示。
        assert result["actual_quality"] == expected_code
        assert bitrate_to_quality(600) == "LD"

    async def test_hls_only_low_tier_does_not_burn_highest_bitrate(self) -> None:
        # 单独固化 M-11 的带宽后果：请求「流畅」时实拉的 HLS 必须是最低码率那一路。
        payload = _payload(_streams([t for t, _b in _TIERS], flv=False, hls=True))
        with patch("src.stream.get_response_status", new_callable=AsyncMock, return_value=True) as probe:
            result = await get_tiktok_stream_url(cast(dict[str, object], payload), video_quality="LD")

        assert str(result["m3u8_url"]).startswith(f"{_HOST}/ld.m3u8")
        # 探针校验的正是被选中的那一档（不是首档）——两处必须同源，否则校验与实际拉流脱节。
        assert probe.await_args is not None
        assert str(probe.await_args.kwargs["url"]).startswith(f"{_HOST}/ld.m3u8")
        assert probe.await_args.kwargs.get("platform") == "TikTok直播"

    async def test_hls_only_single_tier_clamps_to_that_tier(self) -> None:
        # 边界：HLS 只有一路时，任何请求档都钳到该唯一档（索引 min(请求, len-1) = 0）。
        payload = _payload(_streams(["sd"], flv=False, hls=True))
        for requested in ("OD", "BD", "UHD", "HD", "SD", "LD"):
            with patch("src.stream.get_response_status", new_callable=AsyncMock, return_value=True):
                result = await get_tiktok_stream_url(cast(dict[str, object], payload), video_quality=requested)
            assert str(result["m3u8_url"]).startswith(f"{_HOST}/sd.m3u8"), requested
            assert result["actual_quality"] == "SD", requested


class TestIndependentClampWhenLengthsDiffer:
    # 失效面②：两侧过滤后长度不等时，HLS 不得被 FLV 的长度二次截断。

    async def test_flv_shorter_than_hls_clamps_independently(self) -> None:
        # 6 路 HLS、仅中间 3 路带 FLV（TikTok 真实形态：部分档位不下发 FLV）。
        # 请求 LD(5)：FLV 侧钳到自身末档 hd.flv，HLS 侧必须仍是 ld.m3u8。
        # 修复前 quality_index 先被钳成 2，HLS 也随之落到 uhd.m3u8（高档）。
        data = {tag: _entry(tag, bitrate, flv=(tag in ("bd", "uhd", "hd")), hls=True) for tag, bitrate in _TIERS}
        with patch("src.stream.get_response_status", new_callable=AsyncMock, return_value=True):
            result = await get_tiktok_stream_url(cast(dict[str, object], _payload(data)), video_quality="LD")

        assert str(result["m3u8_url"]).startswith(f"{_HOST}/ld.m3u8")
        assert str(result["flv_url"]).startswith(f"{_HOST}/hd.flv")
        # 选中项含 FLV 时 actual_quality 按 FLV 的码率回采（MID-15/16 既有口径，本用例只固化不回改）。
        assert result["actual_quality"] == "HD"

    async def test_flv_only_room_clamps_to_requested_index(self) -> None:
        # FLV-only（HLS 侧过滤后为空）：m3u8 通道为空、FLV 按请求档取，且不受 HLS 长度影响。
        data = {tag: _entry(tag, bitrate, flv=True, hls=False) for tag, bitrate in _TIERS}
        with patch("src.stream.get_response_status", new_callable=AsyncMock, return_value=True):
            result = await get_tiktok_stream_url(cast(dict[str, object], _payload(data)), video_quality="LD")

        assert result["m3u8_url"] == ""
        assert str(result["flv_url"]).startswith(f"{_HOST}/ld.flv")
        assert result["record_url"] == result["flv_url"]
        assert result["available_qualities"] is not None


class TestEmptyListsBoundary:
    # 两个列表皆空的边界不得抛异常（原实现靠 {"url": ""} 兜底，MID-16 的形态必须保持）。

    async def test_no_url_at_all_returns_empty_candidates(self) -> None:
        # 条目有 vbitrate/resolution（因此原始列表非空、过不了上方 len==0 的早退），
        # 但 flv/hls 一路都没有 → 过滤后两侧皆空，只能给出空地址交由上层判无候选。
        data = {tag: _entry(tag, bitrate, flv=False, hls=False) for tag, bitrate in _TIERS}
        with patch("src.stream.get_response_status", new_callable=AsyncMock, return_value=True) as probe:
            result = await get_tiktok_stream_url(cast(dict[str, object], _payload(data)), video_quality="LD")

        assert result["is_live"] is True
        assert result["flv_url"] == ""
        assert result["m3u8_url"] == ""
        assert result["record_url"] == ""
        # 空地址不得去打探针（check_url 为空即判不可达，避免一次无意义的 CDN 请求）。
        assert probe.await_count == 0

    async def test_no_bitrate_entries_return_not_live(self) -> None:
        # get_video_quality_url 对 vbitrate==0 或无 resolution 的条目一律不收录 → 原始列表即空 →
        # 早退 is_live=False（不得为无流房间伪造 is_live=True 误导调度器）。
        data = {"only_meta": {"main": {"sdk_params": json.dumps({"vbitrate": 0})}, "hls": f"{_HOST}/x.m3u8"}}
        with patch("src.stream.get_response_status", new_callable=AsyncMock, return_value=True):
            result = await get_tiktok_stream_url(cast(dict[str, object], _payload(data)), video_quality="LD")
        assert result["is_live"] is False


class TestFallbackBaseIsRawIndex:
    # 探针不可达时的回退同样不得复用「被 FLV 钳过」的下标。

    async def test_probe_failure_steps_from_requested_index(self) -> None:
        data = {tag: _entry(tag, bitrate, flv=(tag in ("bd", "uhd", "hd")), hls=True) for tag, bitrate in _TIERS}
        with patch("src.stream.get_response_status", new_callable=AsyncMock, return_value=False):
            result = await get_tiktok_stream_url(cast(dict[str, object], _payload(data)), video_quality="LD")

        # 请求 LD(5) → 回退基准 fallback_base = max(5-1, 0) = 4 → HLS 取 sd（索引 4）。
        # 修复前基准取自被 FLV 钳过的索引 2 → 回退成 uhd/hd 一侧的高档。
        assert str(result["m3u8_url"]).startswith(f"{_HOST}/sd.m3u8")
        assert str(result["flv_url"]).startswith(f"{_HOST}/hd.flv")

    async def test_probe_failure_hls_only_room_stays_on_low_tier(self) -> None:
        data = {tag: _entry(tag, bitrate, flv=False, hls=True) for tag, bitrate in _TIERS}
        with patch("src.stream.get_response_status", new_callable=AsyncMock, return_value=False):
            result = await get_tiktok_stream_url(cast(dict[str, object], _payload(data)), video_quality="LD")

        assert str(result["m3u8_url"]).startswith(f"{_HOST}/sd.m3u8")
        assert result["flv_url"] == ""
        assert result["actual_quality"] == "SD"


class TestDowngradeWarningConvention:
    # M-11 要求的「降级告警口径」核对：main.py 的告警闸门只在 actual 比 requested **低**时触发。
    # TikTok 的钳制（min 到更短列表的末位）只会取到**更高**档，因此按既有口径保持静默是设计如此，
    # 不是缺陷；缺陷在于修复前把「档位明明存在」也钳成了首档（上方用例已锁）。

    @pytest.mark.parametrize(
        "requested,actual,warns",
        [
            ("LD", "OD", False),  # 修复前 HLS-only 房间的真实形态：选流畅实拉原画 → 高档，静默
            ("LD", "SD", False),  # 钳到更高一档同样静默（既有口径）
            ("OD", "LD", True),  # 反向：请求原画实拉流畅才是告警的目标形态
            ("BD", "BD", False),  # 修复后请求档存在即命中：actual == requested，无告警
        ],
    )
    def test_is_downgrade_matrix(self, requested: str, actual: str, warns: bool) -> None:
        assert is_downgrade(requested, actual) is warns
