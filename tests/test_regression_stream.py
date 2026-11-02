# -*- coding: utf-8 -*-
# 2026-09-22 审查报告 / 组 A（src/stream.py + src/stream_select.py）修复的回归锁。
#
# 每条用例都对应报告里的一个编号，判据是「失效形态本身」而不是调用形状：
#   SEV-2201  play_url_list 元素为裸 URL 串时不得抛 AttributeError，也不得被装饰器兜成
#             {"is_live": False}（8+ 平台每轮漏录）；
#   MID-2227  抖音/TikTok 的 HLS 可用性探针必须带 UA（与 stream_select 同源）；
#   MID-2228  虎牙无 exsphd 且请求 HD/SD/LD 时必须进档位裁决（旧实现两分支都进不去）；
#   MID-2229  抖音真实画质键 FULL_HD1/HD1/SD1/SD2 必须能排序、能回采、能告警降级；
#   MID-2230  B站蓝光子档位（BD30/BD20/BD8/BD4）必须先折叠再选 qn，不得落到默认原画；
#   MID-2231  播放列表正文派生的第二跳地址：跨域剥 Cookie、内网/畸形目标不发请求。
#
# 全部离线：网络探针用 AsyncMock 桩掉，HTTP 客户端用记录型假对象替换。

from collections.abc import Iterator
from typing import Literal, cast
from unittest.mock import AsyncMock, patch

import pytest

import main  # noqa: F401  先完整初始化 main，打破 stream_select<->main 的循环导入（同 test_stream_select.py）
from src import stream as stream_mod
from src import stream_select as ss
from src.stream import (
    _probe_headers,
    get_bilibili_stream_url,
    get_douyin_stream_url,
    get_huya_stream_url,
    get_stream_url,
    get_tiktok_stream_url,
    is_downgrade,
)
from src.stream_select import MOBILE_UA, get_record_user_agent

# ────────────────────────────────────────────────────────────
# SEV-2201：play_url_list 元素类型契约（list[str] 与 list[dict] 并存）
# ────────────────────────────────────────────────────────────


class TestPlayUrlListStrContract:
    # 写入侧（src/spider.py 9 处同型产出）给的是按画质排序后的**裸 URL 串**，
    # 读取侧原实现无条件 `.get()` → AttributeError → 被装饰器兜成 {"is_live": False}。

    @pytest.mark.asyncio
    async def test_str_element_returns_url_not_offline(self) -> None:
        json_data = {"is_live": True, "anchor_name": "soop", "title": "T", "play_url_list": ["https://x/a.m3u8"]}
        result = await get_stream_url(json_data, video_quality="OD", url_type="m3u8")
        # 修复前：{"is_live": False}（AttributeError 被吞）——下面两行同时变红
        assert result["is_live"] is True
        assert result["m3u8_url"] == "https://x/a.m3u8"
        assert result["record_url"] == "https://x/a.m3u8"

    @pytest.mark.asyncio
    async def test_str_element_flv_type(self) -> None:
        json_data = {"is_live": True, "anchor_name": "panda", "play_url_list": ["https://x/a.flv"]}
        result = await get_stream_url(json_data, video_quality="OD", url_type="flv")
        assert result["flv_url"] == "https://x/a.flv"
        assert result["record_url"] == "https://x/a.flv"

    @pytest.mark.asyncio
    async def test_str_element_all_type(self) -> None:
        json_data = {"is_live": True, "anchor_name": "wink", "play_url_list": ["https://x/a.m3u8"]}
        result = await get_stream_url(json_data, url_type="all")
        assert result["m3u8_url"] == "https://x/a.m3u8"
        assert result["flv_url"] == "https://x/a.m3u8"
        assert result["record_url"] == "https://x/a.m3u8"

    @pytest.mark.asyncio
    async def test_empty_str_element_stays_empty(self) -> None:
        # 空串按既有语义原样返回（不得被当成缺字段而抛错，也不得编造地址）
        json_data = {"is_live": True, "anchor_name": "x", "play_url_list": [""]}
        result = await get_stream_url(json_data, url_type="m3u8")
        assert result["is_live"] is True
        assert result["m3u8_url"] == ""

    @pytest.mark.asyncio
    async def test_low_quality_index_padded_with_last_str(self) -> None:
        # LD（索引 5）在 2 元素列表上经 _pad_list 以末元素补齐后取值
        json_data = {"is_live": True, "anchor_name": "x", "play_url_list": ["https://x/hd.m3u8", "https://x/sd.m3u8"]}
        result = await get_stream_url(json_data, video_quality="LD", url_type="m3u8")
        assert result["m3u8_url"] == "https://x/sd.m3u8"

    @pytest.mark.asyncio
    async def test_dict_element_still_probed_in_order(self) -> None:
        # 对照：字典形态（既有契约）不得被 str 分支改变取值顺序
        json_data = {
            "is_live": True,
            "anchor_name": "x",
            "play_url_list": [
                {"play_url": "https://x/p.m3u8", "m3u8_url": "https://x/h.m3u8"},
                {"flv_url": "https://x/only.flv"},
            ],
        }
        result = await get_stream_url(json_data, video_quality="OD", url_type="m3u8")
        assert result["record_url"] == "https://x/p.m3u8"
        result = await get_stream_url(json_data, video_quality="HD", url_type="flv")
        assert result["flv_url"] == "https://x/only.flv"

    @pytest.mark.asyncio
    async def test_mixed_list_does_not_raise(self) -> None:
        # 混合形态（同一份列表里既有 str 又有 dict）：逐元素判型，不得整轮兜成未开播
        json_data = {
            "is_live": True,
            "anchor_name": "x",
            "play_url_list": ["https://x/a.m3u8", {"url": "https://x/b.m3u8"}],
        }
        first = await get_stream_url(json_data, video_quality="OD", url_type="m3u8")
        second = await get_stream_url(json_data, video_quality="UHD", url_type="m3u8")
        assert first["m3u8_url"] == "https://x/a.m3u8"
        assert second["m3u8_url"] == "https://x/b.m3u8"


# ────────────────────────────────────────────────────────────
# MID-2227：抖音/TikTok 的 HLS 探针必须带 UA
# ────────────────────────────────────────────────────────────


class TestProbeCarriesUserAgent:
    @pytest.mark.asyncio
    async def test_douyin_probe_headers(self) -> None:
        json_data = {
            "anchor_name": "a",
            "status": 2,
            "stream_url": {
                "flv_pull_url": {"FULL_HD1": "https://f/a.flv"},
                "hls_pull_url_map": {"FULL_HD1": "https://m/a.m3u8"},
                "hevc_flv_url": None,
            },
        }
        with patch("src.stream.get_response_status", new_callable=AsyncMock, return_value=True) as mock_status:
            await get_douyin_stream_url(json_data, video_quality="OD")
        assert mock_status.await_args is not None
        headers = cast(dict[str, str], mock_status.await_args.kwargs.get("headers") or {})
        # 判据：出网 UA 不得是 httpx 默认指纹，且与 stream_select 同源
        assert headers.get("User-Agent") in (get_record_user_agent("抖音直播"), MOBILE_UA)
        assert "python-httpx" not in headers.get("User-Agent", "")

    @pytest.mark.asyncio
    async def test_tiktok_probe_headers(self) -> None:
        import json as _json

        stream_data = {
            "data": {
                "origin": {
                    "main": {"sdk_params": '{"vbitrate": 4000, "VCodec": "h264", "resolution": "1920x1080"}'},
                    "flv": "https://t/origin.flv",
                    "hls": "https://t/origin.m3u8",
                }
            }
        }
        json_data = {
            "LiveRoom": {
                "liveRoomUserInfo": {"user": {"status": 2, "nickname": "N", "uniqueId": "u"}},
                "liveRoom": {"title": "T", "streamData": {"pull_data": {"stream_data": _json.dumps(stream_data)}}},
            }
        }
        with patch("src.stream.get_response_status", new_callable=AsyncMock, return_value=True) as mock_status:
            await get_tiktok_stream_url(cast(dict[str, object], json_data), video_quality="OD")
        assert mock_status.await_args is not None
        headers = cast(dict[str, str], mock_status.await_args.kwargs.get("headers") or {})
        assert headers.get("User-Agent") in (get_record_user_agent("TikTok直播"), MOBILE_UA)
        assert "python-httpx" not in headers.get("User-Agent", "")

    def test_probe_headers_matches_stream_select_source(self) -> None:
        # UA 唯一事实源：不得在 stream.py 里再抄一份字面量
        assert _probe_headers("虎牙直播") == {"User-Agent": get_record_user_agent("虎牙直播")}
        assert _probe_headers("抖音直播") == {"User-Agent": MOBILE_UA}


# ────────────────────────────────────────────────────────────
# MID-2228：虎牙「无 exsphd + 请求 HD/SD/LD」的档位裁决缺口
# ────────────────────────────────────────────────────────────


class TestHuyaTierGapWithoutExsphd:
    @staticmethod
    def _json(bit_rate: int | None = None) -> dict[str, object]:
        # sFlvAntiCode 不含 &exsphd=（quality_list 长度为 1）——旧实现的缺口形态
        anti = "wsSecret=hs&wsTime=6a&ctype=huya_live&fs=bgct"
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
    async def test_hd_without_exsphd_is_decided_by_bitrate(self) -> None:
        # 缺口形态：无 exsphd、房间 bitRate=30000、请求 HD(1000)。旧实现两个分支都进不去 → 不挂
        # ratio（=原画）而 actual_quality 仍是 HD → is_downgrade 恒 False → 面板显示「高清」、产物是原画。
        with patch("src.stream.logger.warning") as warn:
            result = await get_huya_stream_url(cast(dict[str, object], self._json(30000)), video_quality="HD")
        assert str(result["flv_url"]).endswith("&ratio=500")  # 1000 无档 → 就近降到 500
        assert result["actual_quality"] == "LD"
        assert is_downgrade("HD", cast(str, result["actual_quality"])) is True
        assert any("不可用" in str(c.args[0]) for c in warn.call_args_list)

    @pytest.mark.asyncio
    async def test_uhd_without_exsphd_lands_on_uhd(self) -> None:
        result = await get_huya_stream_url(cast(dict[str, object], self._json(30000)), video_quality="UHD")
        assert str(result["flv_url"]).endswith("&ratio=2000")
        assert result["actual_quality"] == "UHD"
        assert is_downgrade("UHD", cast(str, result["actual_quality"])) is False

    @pytest.mark.asyncio
    async def test_no_exsphd_no_bitrate_falls_back_to_od_with_warning(self) -> None:
        # 两者皆缺：不附加 ratio，但必须把 actual_quality 显式写成 OD（旧实现留着请求档）
        with patch("src.stream.logger.warning") as warn:
            result = await get_huya_stream_url(cast(dict[str, object], self._json()), video_quality="SD")
        assert "ratio=" not in str(result["flv_url"])
        assert result["actual_quality"] == "OD"
        assert any("按原画拉流" in str(c.args[0]) for c in warn.call_args_list)


# ────────────────────────────────────────────────────────────
# MID-2229：抖音真实画质键 FULL_HD1/HD1/SD1/SD2
# ────────────────────────────────────────────────────────────


class TestDouyinRealQualityKeys:
    @staticmethod
    def _json(flv: dict[str, str], m3u8: dict[str, str] | None = None) -> dict[str, object]:
        return {
            "anchor_name": "a",
            "status": 2,
            "stream_url": {
                "flv_pull_url": flv,
                "hls_pull_url_map": m3u8 or {},
                "hevc_flv_url": None,
            },
        }

    @pytest.mark.asyncio
    async def test_real_keys_are_sorted_by_tier_not_by_response_order(self) -> None:
        # 故意打乱接口返回顺序：排序必须按档位（BD>HD>SD>LD），不是按 dict 插入序
        flv = {
            "SD2": "https://f/sd2.flv",
            "FULL_HD1": "https://f/fhd.flv",
            "HD1": "https://f/hd1.flv",
            "SD1": "https://f/sd1.flv",
        }
        with patch("src.stream.get_response_status", new_callable=AsyncMock, return_value=True):
            result = await get_douyin_stream_url(cast(dict[str, object], self._json(flv)), video_quality="OD")
        assert result["available_qualities"] == ["BD", "HD", "SD", "LD"]
        assert result["flv_url"] == "https://f/fhd.flv"
        assert result["actual_quality"] == "BD"

    @pytest.mark.asyncio
    async def test_real_quality_readback_enables_downgrade_alarm(self) -> None:
        # 旧实现：actual_quality 是 "FULL_HD1" 这类真实键，QUALITY_LEVEL 查不到 →
        # is_downgrade 恒 False → 抖音画质降级永不告警。
        flv = {"FULL_HD1": "https://f/fhd.flv", "SD1": "https://f/sd1.flv"}
        with patch("src.stream.get_response_status", new_callable=AsyncMock, return_value=True):
            result = await get_douyin_stream_url(cast(dict[str, object], self._json(flv)), video_quality="BD")
        assert result["actual_quality"] == "SD"
        assert is_downgrade("BD", cast(str, result["actual_quality"])) is True

    @pytest.mark.asyncio
    async def test_unknown_key_warns_and_keeps_name(self) -> None:
        # 未知键：留痕 + 原样上抛（order 默认 99 = 按最低档对待），不得伪造档位名
        from src.stream import DOUYIN_KEY_TO_CODE

        assert "FULL_HD1" in DOUYIN_KEY_TO_CODE and DOUYIN_KEY_TO_CODE["FULL_HD1"] == "BD"
        with (
            patch("src.stream.get_response_status", new_callable=AsyncMock, return_value=True),
            patch("src.stream.logger.warning") as warn,
        ):
            result = await get_douyin_stream_url(
                cast(dict[str, object], self._json({"MYSTERY": "https://f/x.flv"})), video_quality="OD"
            )
        assert result["actual_quality"] == "MYSTERY"
        assert any("未知画质键" in str(c.args[0]) for c in warn.call_args_list)


# ────────────────────────────────────────────────────────────
# MID-2230：B站蓝光子档位必须先折叠再选 qn
# ────────────────────────────────────────────────────────────


class TestBilibiliSubTierFolding:
    @staticmethod
    async def _resolve(video_quality: str, current_qn: int = 400) -> tuple[dict[str, object], AsyncMock]:
        json_data = {"anchor_name": "bili", "live_status": 1, "title": "T", "room_url": "https://live.bilibili.com/1"}
        play = {"current_qn": current_qn, "accept_qn": [current_qn], "url": "https://bilivideo/x.m3u8"}
        with patch("src.stream.get_bilibili_stream_data", new_callable=AsyncMock, return_value=play) as mock_data:
            result = await get_bilibili_stream_url(cast(dict[str, object], json_data), video_quality=video_quality)
        return result, mock_data

    @pytest.mark.asyncio
    async def test_bd4_folds_to_bd_qn(self) -> None:
        # 旧实现：video_quality_options.get("BD4", "10000") → 请求原画（比用户选的更高），
        # 而 is_downgrade("BD4","OD") 为 False → 既不按请求录也不告警。
        result, mock_data = await self._resolve("BD4")
        assert mock_data.await_args is not None
        assert mock_data.await_args.kwargs.get("qn") == "400"
        assert result["actual_quality"] == "BD"

    @pytest.mark.asyncio
    @pytest.mark.parametrize("code", ["BD30", "BD20", "BD8"])
    async def test_all_sub_tiers_fold_to_bd_qn(self, code: str) -> None:
        _result, mock_data = await self._resolve(code)
        assert mock_data.await_args is not None
        assert mock_data.await_args.kwargs.get("qn") == "400"

    @pytest.mark.asyncio
    async def test_unknown_code_warns(self) -> None:
        _result, mock_data = await self._resolve("NOPE")
        assert mock_data.await_args is not None
        assert mock_data.await_args.kwargs.get("qn") == "10000"
        # 告警由 logger.warning 发出（此处只锁 qn 回退到默认原画这一既有兜底语义）


# ────────────────────────────────────────────────────────────
# MID-2231：正文派生的第二跳地址（Cookie 外泄 / 内网 SSRF）
# ────────────────────────────────────────────────────────────


class _Resp:
    def __init__(self, status_code: int, text: str = "") -> None:
        self.status_code = status_code
        self.text = text
        self.headers: dict[str, str] = {}
        # L-11：探针读正文改走 _bounded_probe_get 的流式形态，故桩要能当流式响应用
        # （上下文协议 + iter_bytes + encoding）。刻意整段一次交出、不在桩里重实现「读满上限即断」。
        self.encoding = "utf-8"

    def __enter__(self) -> _Resp:
        return self

    def __exit__(self, *_args: object) -> Literal[False]:
        return False

    def iter_bytes(self, _chunk_size: int | None = None) -> Iterator[bytes]:
        yield (self.text or "").encode("utf-8")


class _RecordingClient:
    # 记录每一次 GET 的 (url, headers)，按 URL 返回预置正文
    def __init__(self, bodies: dict[str, str], default_status: int = 200) -> None:
        self.bodies = bodies
        self.default_status = default_status
        self.calls: list[tuple[str, dict[str, str]]] = []

    def get(self, url: str, headers: dict[str, str] | None = None, follow_redirects: bool = True) -> _Resp:
        self.calls.append((url, dict(headers or {})))
        return _Resp(self.default_status, self.bodies.get(url, ""))

    def stream(
        self,
        method: str,
        url: str,
        headers: dict[str, str] | None = None,
        follow_redirects: bool = True,
    ) -> _Resp:
        # L-11：生产的探针读取统一走 client.stream(...)，本方法把既有 get 的语义原样暴露成
        # 流式形态——同一份正文、同一个 calls 记录，因此「哪些地址被请求过」的断言逐字不变。
        assert method == "GET", method
        return self.get(url, headers=headers, follow_redirects=follow_redirects)

    def headers_for(self, fragment: str) -> dict[str, str] | None:
        for url, headers in self.calls:
            if fragment in url:
                return headers
        return None


_PLAYLIST = "https://cdn.example.com/live/a.m3u8"
_HEADERS = {"cookie": "SESS=secret", "User-Agent": "ua", "referer": "https://example.com/"}


class TestDerivedHopScope:
    def test_same_host_and_registrable_domain(self) -> None:
        assert ss._is_same_probe_scope(_PLAYLIST, "https://cdn.example.com/live/b.m3u8") is True
        assert ss._is_same_probe_scope(_PLAYLIST, "https://edge.example.com/live/b.m3u8") is True

    def test_different_registrable_domain(self) -> None:
        assert ss._is_same_probe_scope(_PLAYLIST, "https://evil.example.net/x.m3u8") is False
        # 双段主机名不得因「末两段相同」的近似判断被误判为同域
        assert ss._is_same_probe_scope("https://example.com/a.m3u8", "https://evil.com/b.m3u8") is False

    def test_derived_hop_allowlist(self) -> None:
        assert ss._is_derived_hop_allowed("https://cdn.example.com/a.ts") is True
        assert ss._is_derived_hop_allowed("file:///etc/passwd") is False
        assert ss._is_derived_hop_allowed("http://169.254.169.254/latest/meta-data/") is False
        assert ss._is_derived_hop_allowed("http://127.0.0.1:8080/x.m3u8") is False
        assert ss._is_derived_hop_allowed("http://192.168.1.9/x.m3u8") is False

    def test_cross_domain_variant_is_probed_without_cookie(self) -> None:
        # 变体地址由正文派生（urljoin 对绝对 URL 整体丢弃 base）→ 跨注册域，Cookie 必须剥掉
        variant = "https://evil.example.net/steal.m3u8"
        client = _RecordingClient(
            {
                _PLAYLIST: f"#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=1000\n{variant}\n",
                variant: "#EXTM3U\n#EXTINF:4.0,\nhttps://cdn.example.com/seg.ts\n",
            }
        )
        with (
            patch.object(ss, "_PROBE_MIN_HOST_INTERVAL", 0),
            patch.object(ss, "_PROBE_THROTTLE_JITTER", 0),
        ):
            assert ss._probe_hls_segment(cast(object, client), _PLAYLIST, _HEADERS) is True  # type: ignore[arg-type]
        sent = client.headers_for("evil.example.net")
        assert sent is not None
        assert "cookie" not in {k.lower() for k in sent}
        # User-Agent / Referer 与本轮其它探针保持一致（只剥凭据，不改指纹）
        assert sent.get("User-Agent") == "ua"
        # 同域的分片请求保留 Cookie（分片与列表同域是常态）
        seg_headers = client.headers_for("seg.ts")
        assert seg_headers is not None and seg_headers.get("cookie") == "SESS=secret"

    def test_cross_domain_segment_is_probed_without_cookie(self) -> None:
        # 斗鱼 hw 形态（列表与分片跨注册域）：探测照旧执行（分片 404 仍须判假绿），
        # 只是这一跳不再携带登录态
        client = _RecordingClient({_PLAYLIST: "#EXTM3U\n#EXTINF:4.0,\nhttps://f19c.livehwc4.com/live/x.ts\n"})
        with (
            patch.object(ss, "_PROBE_MIN_HOST_INTERVAL", 0),
            patch.object(ss, "_PROBE_THROTTLE_JITTER", 0),
        ):
            assert ss._probe_hls_segment(cast(object, client), _PLAYLIST, _HEADERS, platform="斗鱼直播") is True  # type: ignore[arg-type]
        sent = client.headers_for("livehwc4.com")
        assert sent is not None
        assert "cookie" not in {k.lower() for k in sent}
        assert sent.get("Range") == "bytes=0-0"

    def test_internal_target_is_not_requested(self) -> None:
        # 内网/本机目标：一个请求都不发。[历史注] SR-01 修复前此处断言 True——
        # 安全拒绝分支错误沿用「保守维持列表可达」，内网地址经播放列表正文交给 ffmpeg -i。
        client = _RecordingClient(
            {_PLAYLIST: "#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=1000\nhttp://127.0.0.1:8080/x.m3u8\n"}
        )
        with patch("src.stream_select.logger.warning") as warn:
            # S-04：安全拒绝改抛内部控制流异常（原先 return False）——
            # False 与「分片 404 不可达」不可区分，会被调用方的 last_resort / 同址复用翻回可达。
            with pytest.raises(ss._DerivedHopRejected):
                _ = ss._probe_hls_segment(cast(object, client), _PLAYLIST, _HEADERS)  # type: ignore[arg-type]
        assert [url for url, _ in client.calls] == [_PLAYLIST]
        assert any("形态不合规" in str(c.args[0]) for c in warn.call_args_list)

    def test_non_recordable_variant_is_not_requested(self) -> None:
        # 形态不合规变体（file://）：同 SR-01 判据，候选判失败而非维持可达
        client = _RecordingClient({_PLAYLIST: "#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=1000\nfile:///etc/passwd\n"})
        with patch("src.stream_select.logger.warning"):
            # S-04：同 test_internal_target_is_not_requested，改判内部控制流异常
            with pytest.raises(ss._DerivedHopRejected):
                _ = ss._probe_hls_segment(cast(object, client), _PLAYLIST, _HEADERS)  # type: ignore[arg-type]
        assert [url for url, _ in client.calls] == [_PLAYLIST]

    def test_internal_segment_target_rejects_candidate(self) -> None:
        # SR-01 行为锁：变体合法但媒体分片行携带内网地址——分片派生跳的安全拒绝
        # 必须判候选失败，否则被劫持播放列表把 http://127.0.0.1:6379/ 形态目标经 -i 交给 ffmpeg。
        # 对照：修复前该形态维持可达，逐跳钩子拦不住（正文请求不走客户端钩子）。
        client = _RecordingClient({_PLAYLIST: "#EXTM3U\n#EXTINF:4.0,\nhttp://127.0.0.1:6379/seg.ts\n"})
        with patch("src.stream_select.logger.warning") as warn:
            # S-04：改判内部控制流异常（详见 tests/test_stream_select.py 的同名锁）
            with pytest.raises(ss._DerivedHopRejected):
                _ = ss._probe_hls_segment(cast(object, client), _PLAYLIST, _HEADERS)  # type: ignore[arg-type]
        assert [url for url, _ in client.calls] == [_PLAYLIST]
        assert any("形态不合规" in str(c.args[0]) for c in warn.call_args_list)


# ────────────────────────────────────────────────────────────
# 变异验证辅助：str 分支存在性（临时删掉该分支时本条变红）
# ────────────────────────────────────────────────────────────


def test_str_branch_is_present_in_get_url_source() -> None:
    # 判据（可复核）：src/stream.py 的 get_url 内必须有 `isinstance(play_url, str)` 分支。
    # 变异验证：临时删掉该分支 → SEV-2201 的 6 条用例整体变红（AttributeError 被装饰器吞）。
    import inspect

    source = inspect.getsource(stream_mod.get_stream_url)
    assert "isinstance(play_url, str)" in source
