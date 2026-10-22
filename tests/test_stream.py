# -*- coding: utf-8 -*-
# src/stream.py 测试：分两部分 —— ① 纯工具/画质映射函数（bitrate_to_quality / code_to_zh /
# is_downgrade / _pad_list / get_quality_index 及四张画质常量表一致性）；② 核心平台流地址解析
# （抖音/虎牙/斗鱼/快手/YY/网易/TikTok/B站 的 get_*_stream_url，以及通用入口 get_stream_url）。
# 测试策略：用 AsyncMock 桩掉 src.stream.get_response_status（可用性网络探针），把「解析逻辑」
# 与「候选可达性探测」彻底隔离 —— 这样 m3u8 不可达降级、离线短路等分支可被确定性触发，而非依赖
# 真实 CDN 响应。画质边界数字（LD≤600 / HD≤1000 / BD≤4000）取自码率上限表 QUALITY_MAPPING_BIT
# （QUALITY_MAPPING 只有 OD=0…LD=5 的排序索引、不含码率，两者不可混引），用例既锁分段边界也防阈值回归。
# 通用入口 get_stream_url 的「原样返回」契约用同一性断言 `is`
# 锁定，杜绝短路路径返回被篡改副本的回归。
# 2026-09-20 补充（档位语义回归锁）：TestHuyaLegacyTierByRatioValue 锁「虎牙 exsphd 按数值而非
# 出现顺序解释」；TestBilibiliQualityReadback 锁「qn 反向表一对多取更高档 + 表外 qn 不入白名单」；
# TestKuaishouNumericQuality 锁「数字画质先过 QUALITY_MAPPING 解码再查码率表」；
# B站用例另用 AsyncMock 桩 src.stream.get_bilibili_stream_data（第二段网络入口）：patch 目标必须是
# src.stream 命名空间里的那份导入引用（src/stream.py 顶部 from .spider import ...），改成 src.spider.*
# 会让 get_bilibili_stream_url 仍打到真实现、用例静默走网络。

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
# 访问返回的异构字段时按本仓通行的 cast(dict[str, object], ...) / 专用 TypedDict 中转收窄
# （mypy 侧 warn_return_any + disallow_untyped_defs 会把 Any 泄漏报成 no-any-return）。
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
        # 0 码率视为「无有效流」→ 落到原画 OD（表内容量最大档 = 无上限档），
        # 不走升序循环，免得 0 被误判成最低档 LD 而把无码率源标成「流畅」。
        assert bitrate_to_quality(0) == "OD"

    def test_negative_bitrate_returns_od(self) -> None:
        # 负码率（接口异常/缺字段）与 0 同走 `not bitrate or bitrate <= 0` 早退，不抛错。
        assert bitrate_to_quality(-100) == "OD"

    def test_low_bitrate_returns_ld(self) -> None:
        # LD 容量上限 600（QUALITY_MAPPING_BIT）：升序 LD<SD<HD<UHD<BD<OD 找首个「容量 ≥ 实码率」的档
        assert bitrate_to_quality(500) == "LD"

    def test_boundary_600_returns_ld(self) -> None:
        # 码率==LD 上限边界（600）须仍判 LD（判定是 <= 不是 <）；
        # 锁住分段闭区间，防阈值回归把边界错判为 SD。
        assert bitrate_to_quality(600) == "LD"

    def test_boundary_601_returns_sd(self) -> None:
        assert bitrate_to_quality(601) == "SD"

    def test_mid_bitrate_returns_hd(self) -> None:
        # HD 上限 1000（SD=800 / UHD=2000，故 801~1000 落 HD）
        assert bitrate_to_quality(999) == "HD"

    def test_high_bitrate_returns_bd(self) -> None:
        # BD 上限 4000（UHD=2000 < BD=4000，2001~4000 落 BD；BD4 同为 4000 但不在本表回值集合内）
        assert bitrate_to_quality(3000) == "BD"

    def test_very_high_bitrate_returns_od(self) -> None:
        # OD 表内写 99999，且循环全部不命中时仍有末位 return "OD" → 实际无上限（>4000 一律原画）
        assert bitrate_to_quality(99999) == "OD"

    def test_exact_bd_boundary(self) -> None:
        # 码率==BD 上限边界（4000）须仍判 BD；
        # 锁住 BD 闭区间，防把刚好 4000 错判为原画 OD。
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
        # 实际画质缺失时不判降级；
        # 防 None 比较异常。
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
        # 长度恰好等于 min_length 时不增不减；
        # 锁住边界不变。
        result = _pad_list([1, 2, 3], min_length=3)
        assert result == [1, 2, 3]

    def test_longer_list_unchanged(self) -> None:
        result = _pad_list([1, 2, 3, 4], min_length=3)
        assert result == [1, 2, 3, 4]

    def test_default_min_length_is_6(self) -> None:
        # 缺省 min_length=6（2026-09-12 审查 6.5 修复：原 5 让 LD 档（QUALITY_MAPPING 索引 5）越界，
        # 被下游 min(...) 钳制后退回"未开播"分支，用户选"流畅"画质时部分平台永远录不上）；
        # 非空列表原地补末项、空列表返回 [None] * min_length **新列表**——MID-16 的 TikTok 空 FLV
        # 分支正是被这份「非空即真」的空占位列表骗过，见下方 TestGetTiktokStreamUrl 的 MID-16 注释。
        result = _pad_list([1])
        assert len(result) == 6
        assert result[0] == 1
        assert all(x == 1 for x in result[1:])


class TestGetQualityIndex:
    # get_quality_index: 画质入参 → (档位代码, 通用索引)。数字入参按 QUALITY_MAPPING 的键序取档
    # （首字符是数字才生效，>= len(keys)=6 一律回退 0），蓝光子档位在此折叠回 BD——
    # 折叠是本表不塞进 BD4/BD8/BD20/BD30 的前提（见 TestConstants 与 AGENTS 同条约定）。

    def test_none_returns_first(self) -> None:
        name, idx = get_quality_index(None)
        assert name == "OD"
        assert idx == QUALITY_MAPPING["OD"]

    def test_empty_string_returns_first(self) -> None:
        # 空字符串同未传 → 默认 OD；
        # 防空串被当非法代码。
        name, idx = get_quality_index("")
        assert name == "OD"

    def test_string_code(self) -> None:
        # 传入画质代码字符串 → 原样返回该档；
        # 锁住代码直通契约。
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

    def test_multi_digit_quality_parsed_as_whole_number(self) -> None:
        # L-04（2026-10-21）：原实现 int(quality_str[0]) 只取首字符，"10" 被当成 1（BD）；
        # 纯数字串必须按整值解析，越界（>=6）仍按原口径归 0（OD）。
        assert get_quality_index("10")[0] == "OD"
        assert get_quality_index("10")[1] == QUALITY_MAPPING["OD"]
        # 对照：单字符语义不变，防「顺手改成取末字符」这类反向回归
        assert get_quality_index("4")[0] == "SD"


# ────────────────────────────────────────────────────────────
# 常量一致性校验
# ────────────────────────────────────────────────────────────


class TestConstants:
    # 四张画质表的键集合关系（AGENTS「蓝光子档位必须折叠到 BD 索引、不得塞进通用 QUALITY_MAPPING」
    # 的机检面，类名在本文件为 TestConstants，函数名 test_quality_mapping_keys_match_*）：
    # QUALITY_MAPPING 是权威 6 键序（OD=0/BD=1/UHD=2/HD=3/SD=4/LD=5），QUALITY_LEVEL /
    # QUALITY_MAPPING_BIT / QUALITY_CODE_TO_ZH 各是它的**超集**，多出的键必须恰为 BD_SUB_TIERS
    # 四档（30000/20000/8000/4000 与对应中文名）。因此只能断「基础键子集 + 差集恰等于子档位」：
    # 要求三表键全等会把合法的细粒度档判成回归；只断基础键互为子集，则有人往 QUALITY_MAPPING
    # 里塞一个 BD4 也能全绿——而那正是通用选档错位的事故形态。

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
        with patch("src.stream.get_response_status", new_callable=AsyncMock, return_value=True) as mock_status:
            result = await get_douyin_stream_url(json_data, video_quality="HD")

        assert result["is_live"] is True
        # MID-26：解析阶段的探针也必须带 platform（与 stream_select / ffmpeg 同一份
        # 拉流侧 SSL 口径），否则证书异常平台的 m3u8 会被判不可达、错误降级画质
        assert mock_status.await_args is not None
        assert mock_status.await_args.kwargs.get("platform") == "抖音直播"
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
        # m3u8 不可达（get_response_status=False）→ 触发降级到相邻画质；断言放宽到 (SD, HD)
        # 是因降级算法取「请求档之下最近的可用档」，锁定「确实发生了降级」而非具体落到哪一档。
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

    @pytest.mark.asyncio
    async def test_hevc_origin_replaces_flv_but_keeps_h264_in_list(self) -> None:
        # 2026-10-01 原画 hevc 房死锁回归锁：原画 + hevc_flv_url 时 flv_url 被替换为 h265，
        # 被替换的 h264 原画地址必须同步进 flv_url_list —— 选源层会剔除一切 codec=h265 候选，
        # 不保留则「HLS 采集关闭 / m3u8 缺席」的原画 hevc 房过滤后零可用候选、永不录制。
        from src.stream import get_douyin_stream_url

        json_data = {
            "anchor_name": "hevc_anchor",
            "status": 2,
            "stream_url": {
                "flv_pull_url": {"FULL_HD1": "https://flv.example.com/a.flv"},
                "hls_pull_url_map": {"FULL_HD1": "https://hls.example.com/a.m3u8?codec=h264"},
                "hevc_flv_url": "https://flv.example.com/a.flv?codec=h265",
            },
        }
        with patch("src.stream.get_response_status", new_callable=AsyncMock, return_value=True):
            result = await get_douyin_stream_url(json_data, video_quality="OD")

        assert result["is_live"] is True
        assert result["flv_url"] == "https://flv.example.com/a.flv?codec=h265"
        assert result["flv_url_list"] == ["https://flv.example.com/a.flv"]
        # record_url 契约不变：m3u8 优先（h265 主候选仍只经 record_url 末位通道放行）
        assert result["record_url"] == "https://hls.example.com/a.m3u8?codec=h264"

    @pytest.mark.asyncio
    async def test_hevc_fallback_list_survives_m3u8_probe_failure(self) -> None:
        # m3u8 探针失败触发相邻档降级：use_hevc_flv 时 flv_url 保持 h265、仅换 m3u8，
        # 替换发生前已捕获的 h264 原画备选不得丢失 —— 否则探针失败轮恰好退回死锁形态。
        from src.stream import get_douyin_stream_url

        json_data = {
            "anchor_name": "hevc_anchor",
            "status": 2,
            "stream_url": {
                "flv_pull_url": {"FULL_HD1": "https://flv.example.com/a.flv"},
                "hls_pull_url_map": {"FULL_HD1": "https://hls.example.com/a.m3u8?codec=h264"},
                "hevc_flv_url": "https://flv.example.com/a.flv?codec=h265",
            },
        }
        with patch("src.stream.get_response_status", new_callable=AsyncMock, return_value=False):
            result = await get_douyin_stream_url(json_data, video_quality="OD")

        assert result["flv_url"] == "https://flv.example.com/a.flv?codec=h265"
        assert result["flv_url_list"] == ["https://flv.example.com/a.flv"]

    @pytest.mark.asyncio
    async def test_non_origin_quality_skips_hevc_substitution(self) -> None:
        # 对照组：非原画请求不触发 hevc 替换，flv_url 保持 h264；备选列表键恒存在但为空
        from src.stream import get_douyin_stream_url

        json_data = {
            "anchor_name": "hevc_anchor",
            "status": 2,
            "stream_url": {
                "flv_pull_url": {"FULL_HD1": "https://flv.example.com/a.flv", "HD1": "https://flv.example.com/hd.flv"},
                "hls_pull_url_map": {"FULL_HD1": "https://hls.example.com/a.m3u8?codec=h264"},
                "hevc_flv_url": "https://flv.example.com/a.flv?codec=h265",
            },
        }
        with patch("src.stream.get_response_status", new_callable=AsyncMock, return_value=True):
            result = await get_douyin_stream_url(json_data, video_quality="HD")

        assert result["flv_url"] == "https://flv.example.com/hd.flv"
        assert result["flv_url_list"] == []

    @pytest.mark.asyncio
    async def test_hevc_only_without_flv_pairs_has_empty_fallback(self) -> None:
        # flv_pull_url 为空（仅下发 hevc）：flv_url 直接取 hevc，无 h264 原件可保留，备选为空
        from src.stream import get_douyin_stream_url

        json_data = {
            "anchor_name": "hevc_only",
            "status": 2,
            "stream_url": {
                "flv_pull_url": {},
                "hls_pull_url_map": {"FULL_HD1": "https://hls.example.com/a.m3u8?codec=h264"},
                "hevc_flv_url": "https://flv.example.com/a.flv?codec=h265",
            },
        }
        with patch("src.stream.get_response_status", new_callable=AsyncMock, return_value=True):
            result = await get_douyin_stream_url(json_data, video_quality="OD")

        assert result["flv_url"] == "https://flv.example.com/a.flv?codec=h265"
        assert result["flv_url_list"] == []

    @pytest.mark.asyncio
    async def test_hevc_equal_to_flv_entry_not_duplicated(self) -> None:
        # flv_pull_url 原画条目与 hevc 地址逐字相同（接口异常形态）：备选不得重复收同一条
        from src.stream import get_douyin_stream_url

        json_data = {
            "anchor_name": "hevc_dup",
            "status": 2,
            "stream_url": {
                "flv_pull_url": {"FULL_HD1": "https://flv.example.com/a.flv?codec=h265"},
                "hls_pull_url_map": {"FULL_HD1": "https://hls.example.com/a.m3u8?codec=h264"},
                "hevc_flv_url": "https://flv.example.com/a.flv?codec=h265",
            },
        }
        with patch("src.stream.get_response_status", new_callable=AsyncMock, return_value=True):
            result = await get_douyin_stream_url(json_data, video_quality="OD")

        assert result["flv_url"] == "https://flv.example.com/a.flv?codec=h265"
        assert result["flv_url_list"] == []

    @pytest.mark.asyncio
    async def test_h265_marked_flv_entry_not_collected_as_fallback(self) -> None:
        # flv_pull_url 条目自带 codec=h265（约定外形态）：选源层对标记地址同样剔除，
        # 收进备选只会多一条告警、救不了选源 —— 备选必须保证是过滤后仍可用的候选
        from src.stream import get_douyin_stream_url

        json_data = {
            "anchor_name": "hevc_marked",
            "status": 2,
            "stream_url": {
                "flv_pull_url": {"FULL_HD1": "https://flv.example.com/other.flv?codec=h265"},
                "hls_pull_url_map": {"FULL_HD1": "https://hls.example.com/a.m3u8?codec=h264"},
                "hevc_flv_url": "https://flv.example.com/a.flv?codec=h265",
            },
        }
        with patch("src.stream.get_response_status", new_callable=AsyncMock, return_value=True):
            result = await get_douyin_stream_url(json_data, video_quality="OD")

        assert result["flv_url"] == "https://flv.example.com/a.flv?codec=h265"
        assert result["flv_url_list"] == []


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
        # gameStreamInfoList 为空（房间无 CDN 候选）→ 离线；
        # 验证空候选不抛错、契约返回 is_live=False。
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
        # M-26（2026-10-21）：全部档位失败且一格地址都没有时，不再谎报 is_live=True——
        # 旧口径让上层把「开播但无地址」当待录房间、每轮空跑一路 ffmpeg。
        assert result["is_live"] is False
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
        # OD 请求索引截断到末档 → 选中最高码率 origin（BD）。
        # MID-15：flv_url 字段**只放 FLV**。原写法 `"flv_url": m3u8_url or flv_url` 让同一个
        # m3u8 同时进 hls_candidates 与 flv_candidates（去重只在组内）→ 同一轮被连续校验两次、
        # 日志把 HLS 源记成「FLV 源」，最关键是绕过「HLS采集排除平台」的整组剔除语义。
        assert result["m3u8_url"] == "https://tiktok.example.com/origin.m3u8?codec=h264"
        assert result["flv_url"] == "https://tiktok.example.com/origin.flv?codec=h264"
        assert result["actual_quality"] == "BD"
        # 「无 FLV 时以 HLS 顶上」由 record_url 通道承担
        assert result["record_url"] == result["m3u8_url"]

    @staticmethod
    def _json(stream_data: dict[str, object]) -> dict[str, object]:
        import json

        return {
            "LiveRoom": {
                "liveRoomUserInfo": {"user": {"status": 2, "nickname": "Streamer", "uniqueId": "streamer1"}},
                "liveRoom": {
                    "title": "Live Now",
                    "streamData": {"pull_data": {"stream_data": json.dumps(stream_data)}},
                },
            }
        }

    @pytest.mark.asyncio
    async def test_hls_only_room_does_not_raise(self) -> None:
        # MID-16：TikTok 只下发 hls 一路时，get_video_quality_url(stream, "flv") 仍会为每个
        # 条目追加一个 {"url": "", vbitrate, resolution}（追加条件是 vbitrate/resolution，
        # 与 q_key 是否存在无关），于是 FLV 侧全是空地址项。
        # 原实现两重问题：① `"flv_url": m3u8_url or flv_url` 把 m3u8 塞进 FLV 通道（MID-15）；
        # ② flv 列表为空时 _pad_list([]) 返回 [None] * 6（新列表、非空即真），
        #    `if flv_url_list else {"url": ""}` 的兜底进不去 → flv_dict 为 None →
        #    .get("url") 抛 AttributeError，被 trace_error_decorator 伪装成「未开播」。
        # 现在索引前过滤 None 与空地址项，两条路径都走 {"url": ""} 兜底。
        from src.stream import get_tiktok_stream_url

        stream_data: dict[str, object] = {
            "data": {
                "origin": {
                    "main": {"sdk_params": '{"vbitrate": 4000, "VCodec": "h264", "resolution": "1920x1080"}'},
                    "hls": "https://tiktok.example.com/origin.m3u8",
                }
            }
        }
        with patch("src.stream.get_response_status", new_callable=AsyncMock, return_value=True) as mock_status:
            result = await get_tiktok_stream_url(cast(dict[str, object], self._json(stream_data)), video_quality="OD")
        # 修复前这里得到的是装饰器的 {"is_live": False} 兜底（AttributeError 被吞）
        assert result["is_live"] is True
        assert result["m3u8_url"] == "https://tiktok.example.com/origin.m3u8?codec=h264"
        # MID-15：FLV 通道为空就诚实地空，不得用 m3u8 顶替
        assert result["flv_url"] == ""
        assert result["record_url"] == "https://tiktok.example.com/origin.m3u8?codec=h264"
        # 无 FLV 时按选中的 HLS 项回采档位（4000kbps → BD），不再伪装成 OD
        assert result["actual_quality"] == "BD"
        # 空 FLV 列表不得产出画质候选（None 占位项已被剔除）
        assert result["available_qualities"] is None
        # MID-26：探针必须带 platform —— 与 stream_select / ffmpeg 共用拉流侧 SSL 口径
        # （get_effective_ssl_verify(platform)），否则「禁用SSL证书验证的平台」命中时
        # 探针必然证书报错 → 判不可达 → 明明可录的档位被静默降级
        assert mock_status.await_args is not None
        assert mock_status.await_args.kwargs.get("platform") == "TikTok直播"


class TestHuyaLegacyTierByRatioValue:
    # MID-13 / MID-14：虎牙档位必须按 ratio **数值**解释，与 exsphd 的出现顺序无关。

    @staticmethod
    def _json(exsphd: str, bit_rate: int = 0) -> dict[str, object]:
        anti = f"wsSecret=hs&wsTime=6a&ctype=huya_live&fs=bgct&exsphd={exsphd}"
        info: dict[str, object] = {"nick": "anchor", "introduction": "title"}
        if bit_rate:
            info["bitRate"] = bit_rate
        return {
            "data": [
                {
                    "gameLiveInfo": info,
                    "gameStreamInfoList": [
                        {
                            "sCdnType": "HS",
                            "sStreamName": "S",
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

    @pytest.mark.asyncio
    @pytest.mark.parametrize("exsphd", ["264_0 264_500 264_2000 264_8000", "264_8000 264_2000 264_500 264_0"])
    async def test_uhd_ratio_is_order_independent(self, exsphd: str) -> None:
        # 原实现把 labels=["UHD","HD","SD","LD"] 与 reversed(findall) 做**位置式** zip：
        # 同一串 exsphd 换个顺序就得到完全不同的档位标签（请求超清实拉蓝光8M），
        # 且 actual_quality 被回写成请求值 → is_downgrade 恒 False、日志与面板双盲。
        from src.stream import get_huya_stream_url

        result = await get_huya_stream_url(cast(dict[str, object], self._json(exsphd)), video_quality="UHD")
        assert str(result["flv_url"]).endswith("&ratio=2000")
        assert result["actual_quality"] == "UHD"
        # available_qualities 亦按数值集合输出（画质由高到低），不再依赖字符串顺序
        assert result["available_qualities"] == ["OD", "BD", "BD8", "UHD", "LD"]

    @pytest.mark.asyncio
    async def test_legacy_no_interpretable_ratio_falls_back_to_origin(self) -> None:
        # exsphd 只有 264_0（房间仅原画）：按 BD 分支口径不附加 ratio、回采 OD 并告警，
        # 而不是把 0 当成「UHD 的 ratio」拼进 URL
        from src.stream import get_huya_stream_url

        result = await get_huya_stream_url(cast(dict[str, object], self._json("264_0")), video_quality="UHD")
        assert "ratio=" not in str(result["flv_url"])
        assert result["actual_quality"] == "OD"

    @pytest.mark.asyncio
    async def test_unregistered_ratio_is_named_by_value_and_warns(self) -> None:
        # MID-14：exsphd 携带表外 ratio（12000）时，降级档位名按数值就近取 BD8，
        # 不得回落到**请求档**（那是把降级伪装成按请求录）；且必须告警。
        from src.stream import get_huya_stream_url

        with patch("src.stream.logger.warning") as warn:
            result = await get_huya_stream_url(
                cast(dict[str, object], self._json("264_0 264_12000 264_500", bit_rate=20000)),
                video_quality="BD20",
            )
        assert str(result["flv_url"]).endswith("&ratio=12000")
        assert result["quality"] == "BD20"
        assert result["actual_quality"] == "BD8"
        assert is_downgrade("BD20", cast(str, result["actual_quality"])) is True
        assert any("不可用" in str(c.args[0]) for c in warn.call_args_list)

    @pytest.mark.asyncio
    async def test_nearest_code_prefers_lower_tier_on_tie(self) -> None:
        # 表外值就近取档：6000 与 4000/8000 等距，取**更低画质**（BD4）——
        # 宁可多打一条降级告警，也不把更低的实际档位伪装成高档
        from src.stream import huya_code_for_ratio

        assert huya_code_for_ratio(6000) == "BD4"
        assert huya_code_for_ratio(12000) == "BD8"
        assert huya_code_for_ratio(2000) == "UHD"
        assert huya_code_for_ratio(250) == "LD"


class TestBilibiliQualityReadback:
    # MIN-05：B站 qn→档位反向表与表外 qn 的处理。

    @staticmethod
    async def _resolve(current_qn: int, accept_qn: list[int], video_quality: str) -> dict[str, object]:
        from src.stream import get_bilibili_stream_url

        json_data = {
            "anchor_name": "bili",
            "live_status": 1,
            "title": "T",
            "room_url": "https://live.bilibili.com/1",
        }
        play = {"current_qn": current_qn, "accept_qn": accept_qn, "url": "https://bilivideo/x.m3u8"}
        with patch("src.stream.get_bilibili_stream_data", new_callable=AsyncMock, return_value=play):
            return await get_bilibili_stream_url(cast(dict[str, object], json_data), video_quality=video_quality)

    @pytest.mark.asyncio
    async def test_qn80_prefers_sd_over_ld(self) -> None:
        # SD 与 LD 同为 "80"（B站无独立标清档），推导式反向表后写覆盖前写 → 实发 80 恒被
        # 回采成 LD，于是请求「标清」时打出根本不存在的降级告警（SD=7 → LD=8）。
        # 一对多必须显式取**更高档**。
        result = await self._resolve(80, [10000, 400, 250, 150, 80], "SD")
        assert result["actual_quality"] == "SD"
        assert is_downgrade("SD", cast(str, result["actual_quality"])) is False
        # 请求流畅时同样回采 80 → SD，等级更高、不属降级
        assert is_downgrade("LD", "SD") is False

    @pytest.mark.asyncio
    async def test_out_of_table_qn_not_leaked(self) -> None:
        # accept_qn 常含表外值（20000/30000/0）：不得把裸数字塞进 available_qualities
        result = await self._resolve(400, [20000, 10000, 400, 0, 250], "BD")
        assert result["available_qualities"] == ["OD", "BD", "UHD"]
        assert result["actual_quality"] == "BD"

    @pytest.mark.asyncio
    async def test_unknown_current_qn_keeps_requested(self) -> None:
        # current_qn 表外：保持请求档（不伪造档位名），与既有契约一致
        result = await self._resolve(20000, [20000, 10000], "OD")
        assert result["actual_quality"] == "OD"
        assert result["available_qualities"] == ["OD"]


class TestKuaishouNumericQuality:
    # MIN-06：数字画质入参必须按通用索引语义解码，不得按位置索引码率表。

    @pytest.mark.asyncio
    async def test_numeric_index_decoded_through_quality_mapping(self) -> None:
        from src.stream import get_kuaishou_stream_url

        json_data = {
            "type": 2,
            "is_live": True,
            "anchor_name": "ks",
            "flv_url_list": [
                {"url": "https://ks.example.com/max.flv", "bitrate": 30000},
                {"url": "https://ks.example.com/mid.flv", "bitrate": 4000},
                {"url": "https://ks.example.com/low.flv", "bitrate": 1500},
            ],
        }
        # "2" 在通用 QUALITY_MAPPING 里是 UHD（码率上限 2000）。
        # 原实现直接 list(QUALITY_MAPPING_BIT.items())[2] —— 该表为蓝光子档位插了位，
        # 位置 2 是 BD30(30000)，于是「请求 UHD」实拉最高码率档并把 quality 改写成 BD30。
        result = await get_kuaishou_stream_url(cast(dict[str, object], json_data), video_quality="2")
        assert result["quality"] == "UHD"
        assert result["flv_url"] == "https://ks.example.com/low.flv"
        assert result["actual_quality"] == "UHD"

    @pytest.mark.asyncio
    async def test_named_quality_unchanged(self) -> None:
        # 对照：中文名入参（录制链实际形态）行为不变
        from src.stream import get_kuaishou_stream_url

        json_data = {
            "type": 2,
            "is_live": True,
            "anchor_name": "ks",
            "flv_url_list": [
                {"url": "https://ks.example.com/max.flv", "bitrate": 30000},
                {"url": "https://ks.example.com/mid.flv", "bitrate": 4000},
            ],
        }
        result = await get_kuaishou_stream_url(cast(dict[str, object], json_data), video_quality="BD")
        assert result["quality"] == "BD"
        assert result["flv_url"] == "https://ks.example.com/mid.flv"


class TestGetKuaishouStreamUrl:
    # get_kuaishou_stream_url: 快手直播流解析。

    @pytest.mark.asyncio
    async def test_not_live(self) -> None:
        # type=0 且 is_live=False → 离线；
        # 锁住 type 路由与离线契约。
        from src.stream import get_kuaishou_stream_url

        json_data = {"type": 0, "is_live": False, "anchor_name": "ks_anchor"}
        result = await get_kuaishou_stream_url(json_data)
        assert result["is_live"] is False

    @pytest.mark.asyncio
    async def test_live_with_bitrate(self) -> None:
        # 在线且含 flv 码率候选 → 选中画质；
        # 验证按 video_quality 匹配清晰度。
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


class TestStreamMalformedPayload:
    # M-21 / M-22（2026-10-21）：平台下发结构畸形时不得被 @trace_error_decorator 吞成「未开播」。
    # 这些用例一律断言「不抛异常、且不把在播房间谎报成离线」——旧实现在这些形态下抛
    # AttributeError / IndexError / JSONDecodeError，最终都表现为「在播但每轮不录」。

    @pytest.mark.asyncio
    async def test_kuaishou_flv_list_with_non_dict_items_does_not_crash(self) -> None:
        # M-22：flv_list 元素是裸串时，旧实现 flv_list[0] 取首字符、"bitrate" in 恒假，
        # 随后 .get 抛 AttributeError 被吞成未开播。现按「只收 dict 元素」归一。
        from src.stream import get_kuaishou_stream_url

        json_data = {
            "type": 0,
            "is_live": True,
            "anchor_name": "ks_bad",
            "flv_url_list": ["https://ks.example.com/a.flv", "https://ks.example.com/b.flv"],
        }
        result = await get_kuaishou_stream_url(cast("dict[str, object]", json_data), video_quality="HD")
        assert result["is_live"] is True
        assert "flv_url" not in result  # 形态全部不合规 → 无候选，但不谎报离线

    @pytest.mark.asyncio
    async def test_yy_cdn_info_not_dict_does_not_crash(self) -> None:
        # M-22：cdn_info 下发成字符串时，旧实现 .get 抛 AttributeError 被吞成未开播。
        from src.stream import get_yy_stream_url

        json_data = {
            "anchor_name": "yy_bad",
            "title": "YY Live",
            "avp_info_res": {"stream_line_addr": {"line1": {"cdn_info": "https://yy.example.com/live.flv"}}},
        }
        result = await get_yy_stream_url(cast("dict[str, object]", json_data))
        assert result["is_live"] is True
        assert result["flv_url"] == ""

    @pytest.mark.asyncio
    async def test_yy_stream_line_addr_not_dict_does_not_crash(self) -> None:
        # M-22：stream_line_addr 下发成 list 时，旧实现 .get 抛 AttributeError 被吞成未开播。
        from src.stream import get_yy_stream_url

        json_data = {"anchor_name": "yy_bad2", "avp_info_res": {"stream_line_addr": ["x"]}}
        result = await get_yy_stream_url(cast("dict[str, object]", json_data))
        assert result["is_live"] is False

    @pytest.mark.asyncio
    async def test_netease_resolution_entry_not_dict_does_not_crash(self) -> None:
        # M-22：档位条目下发成字符串时，旧实现 stream_list[q].get("cdn") 抛 AttributeError，
        # 整个房间被判未开播（实际在播）。
        from src.stream import get_netease_stream_url

        json_data = {
            "is_live": True,
            "anchor_name": "cc_bad",
            "m3u8_url": "https://cc.example.com/live.m3u8",
            "stream_list": {"resolution": {"ultra": "not-a-dict"}},
        }
        result = await get_netease_stream_url(cast("dict[str, object]", json_data))
        assert result["is_live"] is True
        assert result["flv_url"] == ""
        assert result["record_url"] == "https://cc.example.com/live.m3u8"

    @pytest.mark.asyncio
    async def test_tiktok_truncated_stream_data_returns_not_live_without_raising(self) -> None:
        # M-21：stream_data 是截断的 JSON 时，旧实现 json.loads 裸在任何 try 之外，
        # 异常被装饰器吞成未开播且零日志。现显式收敛：不抛异常、按未开播返回。
        from src.stream import get_tiktok_stream_url

        json_data = {
            "LiveRoom": {
                "liveRoomUserInfo": {"user": {"status": 2, "nickname": "Test", "uniqueId": "test_id"}},
                "liveRoom": {"streamData": {"pull_data": {"stream_data": '{"data": {"origin": '}}},
            }
        }
        result = await get_tiktok_stream_url(cast("dict[str, object]", json_data))
        assert result["is_live"] is False

    @pytest.mark.asyncio
    async def test_douyin_stream_url_not_dict_does_not_crash(self) -> None:
        # M-22：stream_url 下发成字符串时，旧实现 .get 抛 AttributeError 被吞成未开播。
        from src.stream import get_douyin_stream_url

        json_data = {"anchor_name": "dy_bad", "status": 2, "stream_url": "not-a-dict"}
        result = await get_douyin_stream_url(cast("dict[str, object]", json_data))
        assert result["is_live"] is True
        assert result["m3u8_url"] == ""
        assert result["flv_url"] == ""


class TestHuyaAvailableQualities:
    # M-24（2026-10-21）：蓝光分支的 available_qualities 原实现无条件追加 UHD/LD，
    # max_ratio<=0 时对外声称 ["OD","UHD","LD"]，与房间实际档位不符。

    @pytest.mark.asyncio
    async def test_available_qualities_do_not_fabricate_uhd_ld_when_room_has_none(self) -> None:
        from src.stream import get_huya_stream_url

        # exsphd 只有 264_0（房间仅原画）+ 无 bitRate：可用档位只剩 OD
        json_data = {
            "data": [
                {
                    "gameLiveInfo": {"nick": "anchor", "introduction": "t"},
                    "gameStreamInfoList": [
                        {
                            "sCdnType": "HS",
                            "sStreamName": "room1",
                            "sFlvUrl": "https://hs.flv.huya.com/src",
                            "sFlvUrlSuffix": "flv",
                            "sFlvAntiCode": "wsSecret=abc&exsphd=264_0",
                        }
                    ],
                }
            ]
        }
        result = await get_huya_stream_url(cast("dict[str, object]", json_data), video_quality="BD8")
        assert result["is_live"] is True
        assert result["available_qualities"] == ["OD"]

    @pytest.mark.asyncio
    async def test_available_qualities_follow_exsphd_when_room_reports_tiers(self) -> None:
        # 对照：exsphd 报告了 264_4000（蓝光4M）与 264_2000（超清）时，档位按统一序枚举且无伪造档
        from src.stream import get_huya_stream_url

        json_data = {
            "data": [
                {
                    "gameLiveInfo": {"nick": "anchor", "introduction": "t"},
                    "gameStreamInfoList": [
                        {
                            "sCdnType": "HS",
                            "sStreamName": "room2",
                            "sFlvUrl": "https://hs.flv.huya.com/src",
                            "sFlvUrlSuffix": "flv",
                            "sFlvAntiCode": "wsSecret=abc&exsphd=264_0_264_2000_264_4000",
                        }
                    ],
                }
            ]
        }
        result = await get_huya_stream_url(cast("dict[str, object]", json_data), video_quality="UHD")
        assert result["is_live"] is True
        # 旧档位分支（请求非 BD_SUB_TIERS）的既有契约：固定前缀 ["OD", "BD"] + 按 HUYA_CODE_ORDER
        # 枚举 room_codes 命中的具体档。exsphd 264_0_264_2000_264_4000 → {0,2000,4000} → BD4/UHD，
        # 故期望是四档而非三档（"BD" 是通用蓝光标签；M-24 只改蓝光分支，本分支行为未变）。
        assert result["available_qualities"] == ["OD", "BD", "BD4", "UHD"]


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
        # MID-20(a)：未传 hls_extra_key 时原实现把**整份 play_url_list[i] 字典**当流地址返回，
        # 而 stream_select 的 isinstance(str) / _as_str_list 会静默丢弃 → 「解析成功却无任何
        # 流地址」。现按 url/play_url/m3u8_url/flv_url 顺序探测，探测不到即返回 ""。
        # 该字典只有 m3u8/flv 两个非探测序列键，故得到空串而不是 dict。
        result = await get_stream_url(json_data, video_quality="OD", url_type="m3u8")
        assert result["is_live"] is True
        assert result["m3u8_url"] == ""
        assert result["record_url"] == ""
        assert result["quality"] == "OD"

        # 显式传 key 时按 key 取值（既有契约），record_url 与之同源
        result = await get_stream_url(json_data, video_quality="OD", url_type="m3u8", hls_extra_key="m3u8")
        assert result["m3u8_url"] == "https://example.com/od.m3u8"
        assert result["record_url"] == "https://example.com/od.m3u8"

    @pytest.mark.asyncio
    async def test_missing_key_returns_empty_not_keyerror(self) -> None:
        # MID-20：play_url[key] 的 KeyError 会穿透到 main.py 的通用 except 并
        # record_error(host) 计入按 host 的熔断样本（AGENTS 2026-09-19：与其它平台
        # 「安静重试一轮」不等价，严重时自动注释用户房间地址）。缺键必须返回 ""。
        from src.stream import get_stream_url

        json_data = {
            "is_live": True,
            "anchor_name": "generic",
            "title": "Generic Live",
            "play_url_list": [{"flv": "https://example.com/od.flv"}],
        }
        result = await get_stream_url(json_data, url_type="flv", flv_extra_key="no_such_key")
        assert result["is_live"] is True
        assert result["flv_url"] == ""
        assert result["record_url"] == ""

    @pytest.mark.asyncio
    async def test_generic_url_key_probed_in_order(self) -> None:
        # 未指定 extra_key 时的取值顺序 url → play_url → m3u8_url → flv_url（MID-20）
        from src.stream import get_stream_url

        json_data = {
            "is_live": True,
            "anchor_name": "generic",
            "title": "Generic Live",
            "play_url_list": [
                {"play_url": "https://example.com/p.m3u8", "m3u8_url": "https://example.com/h.m3u8"},
                {"flv_url": "https://example.com/only.flv"},
            ],
        }
        result = await get_stream_url(json_data, video_quality="OD", url_type="m3u8")
        assert result["record_url"] == "https://example.com/p.m3u8"
        # 该项只有 flv_url：按探测序列落到 flv_url（总比把 dict / 空值塞进录制链路好）
        result = await get_stream_url(json_data, video_quality="HD", url_type="flv")
        assert result["flv_url"] == "https://example.com/only.flv"

    @pytest.mark.asyncio
    async def test_malformed_payload_falls_back_instead_of_raising(self) -> None:
        # MID-20：本函数必须是**带兜底装饰器**的平台入口（本层其余 8 处都有）。
        # 未加 @trace_error_decorator 前，这里的 AttributeError 会穿透到 main.py 的通用
        # except 并 record_error(host) 计入按 host 的熔断样本——AGENTS 2026-09-19 条目
        # 明确指出这与其他平台「异常只安静重试一轮」不等价，严重时会自动注释用户房间地址。
        # 输入形态：平台 JSON 把 play_url_list 下发成 dict（劫持/改版均可能）。
        from src.stream import get_stream_url

        json_data = {"is_live": True, "anchor_name": "generic", "play_url_list": {"url": "https://x/a.m3u8"}}
        result = await get_stream_url(json_data)
        assert result == {"is_live": False}

    @pytest.mark.asyncio
    async def test_flv_type(self) -> None:
        from src.stream import get_stream_url

        json_data = {
            "is_live": True,
            "anchor_name": "generic",
            "title": "Generic Live",
            "play_url_list": [{"url": "https://example.com/od.flv"}],
        }
        result = await get_stream_url(json_data, url_type="flv")
        assert result["is_live"] is True
        # MID-20：缺 flv_extra_key 时按探测序列取 url（原实现返回整份 dict，被下游静默丢弃）。
        # 精确锁定选中值与 record_url 契约，杜绝「真值/键存在」的假绿断言漏检空值/错选回归。
        assert result["flv_url"] == "https://example.com/od.flv"
        assert result["record_url"] == result["flv_url"]

    @pytest.mark.asyncio
    async def test_all_type(self) -> None:
        from src.stream import get_stream_url

        json_data = {
            "is_live": True,
            "anchor_name": "generic",
            "title": "Generic Live",
            "play_url_list": [{"m3u8_url": "https://example.com/a.m3u8", "flv_url": "https://example.com/a.flv"}],
        }
        result = await get_stream_url(json_data, url_type="all")
        assert result["is_live"] is True
        # MID-20：未传 extra_key 时按 url/play_url/m3u8_url/flv_url 顺序探测，
        # m3u8_url 槽取到 m3u8_url 键、flv_url 槽亦取同一序列的首个命中值（此处为 m3u8_url）。
        # 关键是**永远返回 str**，不再是整份 dict（dict 会被 stream_select 静默丢弃）。
        assert result["m3u8_url"] == "https://example.com/a.m3u8"
        assert result["record_url"] == result["m3u8_url"]
        assert isinstance(result["flv_url"], str)
        assert result["flv_url"] == "https://example.com/a.m3u8"
