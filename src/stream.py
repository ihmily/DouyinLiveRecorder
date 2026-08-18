#!/usr/bin/env python3
# -*- encoding: utf-8 -*-
# 直播流地址获取模块 - 从各平台解析获取直播流地址，支持多种画质选择

# Author: Hmily
# GitHub: https://github.com/ihmily
# Date: 2023-07-15 23:15:00
# Update: 2025-02-06 02:28:00
# Copyright (c) 2023-2025 by Hmily, All Rights Reserved.
# Function: Get live stream data.

import json
import re
import urllib.parse
from typing import TypedDict, TypeVar, cast

from .async_http import get_response_status
from .spider import get_bilibili_stream_data, get_douyu_stream_data
from .utils import trace_error_decorator

_PadT = TypeVar("_PadT")


# ---- 各平台 json_data 结构类型（仅用于静态类型检查，运行时完全透明）----
class DouyinStreamUrl(TypedDict, total=False):
    anchor_name: str | None
    status: int
    stream_url: "DouyinStreamInner"


class DouyinStreamInner(TypedDict, total=False):
    flv_pull_url: dict[str, str]
    hls_pull_url_map: dict[str, str]
    hevc_flv_url: str


class TiktokStreamUrl(TypedDict, total=False):
    LiveRoom: "TiktokLiveRoom"


class TiktokLiveRoom(TypedDict, total=False):
    liveRoomUserInfo: "TiktokUserInfo"
    liveRoom: "TiktokLiveDetail"
    title: str


class TiktokUserInfo(TypedDict, total=False):
    user: "TiktokUser"


class TiktokUser(TypedDict, total=False):
    status: int
    nickname: str
    uniqueId: str


class TiktokLiveDetail(TypedDict, total=False):
    title: str
    streamData: "TiktokStreamDataOuter"


class TiktokStreamDataOuter(TypedDict, total=False):
    pull_data: "TiktokPullData"


class TiktokPullData(TypedDict, total=False):
    stream_data: str


class KuaishouM3u8Item(TypedDict, total=False):
    url: str


class KuaishouFlvItem(TypedDict, total=False):
    url: str
    bitrate: int


class KuaishouStreamUrl(TypedDict, total=False):
    type: int
    is_live: bool
    anchor_name: str
    m3u8_url_list: list[KuaishouM3u8Item]
    flv_url_list: list[KuaishouFlvItem]


class HuyaStreamUrl(TypedDict, total=False):
    data: list["HuyaDataItem"]


class HuyaDataItem(TypedDict, total=False):
    gameLiveInfo: "HuyaGameLiveInfo"
    gameStreamInfoList: list["HuyaStreamInfo"]


class HuyaGameLiveInfo(TypedDict, total=False):
    introduction: str
    nick: str


class HuyaStreamInfo(TypedDict, total=False):
    sCdnType: str
    sFlvUrl: str
    sStreamName: str
    sFlvUrlSuffix: str
    sHlsUrl: str
    sHlsUrlSuffix: str
    sFlvAntiCode: str
    sHlsAntiCode: str


class DouyuStreamUrl(TypedDict, total=False):
    is_live: bool
    anchor_name: str | None
    room_id: str | int


class DouyuFlvData(TypedDict, total=False):
    rtmp_url: str
    rtmp_live: str
    rate: int | str


class YyStreamUrl(TypedDict, total=False):
    anchor_name: str
    title: str
    avp_info_res: "YyAvpInfoRes"


class YyAvpInfoRes(TypedDict, total=False):
    stream_line_addr: dict[str, "YyCdnInfo"]


class YyCdnInfo(TypedDict, total=False):
    cdn_info: "YyCdnDetail"


class YyCdnDetail(TypedDict, total=False):
    url: str


class BilibiliStreamUrl(TypedDict, total=False):
    anchor_name: str
    live_status: int
    title: str
    room_url: str


class BilibiliPlayData(TypedDict, total=False):
    current_qn: int | str
    accept_qn: list[int]
    url: str


class NeteaseStreamUrl(TypedDict, total=False):
    is_live: bool
    anchor_name: str
    title: str
    m3u8_url: str
    stream_list: "NeteaseStreamList"


class NeteaseStreamList(TypedDict, total=False):
    resolution: dict[str, "NeteaseResolution"]


class NeteaseResolution(TypedDict, total=False):
    cdn: dict[str, str]


class GenericStreamUrl(TypedDict, total=False):
    is_live: bool
    anchor_name: str
    title: str
    m3u8_url: str
    flv_url: str
    play_url_list: list[dict[str, str]]


class StreamQuality(TypedDict, total=False):
    url: str
    vbitrate: int
    resolution: tuple[int, int]


class TiktokSdkParams(TypedDict, total=False):
    vbitrate: int
    VCodec: str
    resolution: str


# 画质 -> 排序后列表中的位置（索引）。必须与 get_douyin_stream_url 中 _sort_quality_items 的
# order 字典保持一致（ORIGIN/OD=0, BD=1, UHD=2, HD=3, SD=4, LD=5），否则按名称选画质会错位。
QUALITY_MAPPING = {"OD": 0, "BD": 1, "UHD": 2, "HD": 3, "SD": 4, "LD": 5}
QUALITY_MAPPING_BIT = {"OD": 99999, "BD": 4000, "UHD": 2000, "HD": 1000, "SD": 800, "LD": 600}

# 画质等级值（数值越大画质越低），用于降级判定
QUALITY_LEVEL = {"OD": 0, "BD": 0, "UHD": 1, "HD": 2, "SD": 3, "LD": 4}

# 画质代码 → 中文名（对齐 main.py get_quality_code 的反向）
QUALITY_CODE_TO_ZH = {"OD": "原画", "BD": "蓝光", "UHD": "超清", "HD": "高清", "SD": "标清", "LD": "流畅"}

# 网易CC 画质名 → 统一代码
NETEASE_QUALITY_MAP = {"blueray": "OD", "ultra": "UHD", "high": "HD", "standard": "SD"}


def bitrate_to_quality(bitrate: int) -> str:
    # 根据码率反查画质代码。返回码率上限 >= 给定值的最高档；0/未知回退 OD。
    if not bitrate or bitrate <= 0:
        return "OD"
    # 从低到高找第一个能容纳该码率的档位（LD<SD<HD<UHD<BD<OD）
    for code in ("LD", "SD", "HD", "UHD", "BD", "OD"):
        if bitrate <= QUALITY_MAPPING_BIT[code]:
            return code
    return "OD"


def code_to_zh(code: str | None) -> str:
    # 画质代码转中文；未知代码原样返回。
    if not code:
        return code or ""
    return QUALITY_CODE_TO_ZH.get(code, code)


def is_downgrade(requested: str | None, actual: str | None) -> bool:
    # 判定是否降级：actual 画质等级值 > requested 等级值。None 不告警。
    if not requested or not actual:
        return False
    req_level = QUALITY_LEVEL.get(requested)
    act_level = QUALITY_LEVEL.get(actual)
    if req_level is None or act_level is None:
        return False
    return act_level > req_level


def _pad_list(url_list: list[_PadT], min_length: int = 5) -> list[_PadT] | list[None]:
    # 将列表填充到指定最小长度
    # 空列表无法以"最后一个元素"填充，返回 None 列表避免调用方索引越界
    if not url_list:
        return [None] * min_length
    while len(url_list) < min_length:
        url_list.append(url_list[-1])
    return url_list


def get_quality_index(quality: str | int | None) -> tuple[str, int]:
    # 解析画质参数，返回画质名称和索引
    if not quality:
        return list(QUALITY_MAPPING.items())[0]

    quality_str = str(quality).upper()
    if quality_str.isdigit():
        quality_int = int(quality_str[0])
        keys = list(QUALITY_MAPPING.keys())
        if quality_int >= len(keys):
            quality_int = 0
        quality_str = keys[quality_int]
    if quality_str not in QUALITY_MAPPING:
        quality_str = list(QUALITY_MAPPING.keys())[0]
    return quality_str, QUALITY_MAPPING[quality_str]


@trace_error_decorator
async def get_douyin_stream_url(
    json_data: dict[str, object], video_quality: str | None = None, proxy_addr: str | None = None
) -> dict[str, object]:
    # 获取抖音直播流URL
    d = cast(DouyinStreamUrl, cast(object, json_data))
    anchor_name = d.get("anchor_name")
    result: dict[str, object] = {"anchor_name": anchor_name, "is_live": False}
    status = d.get("status", 4)

    if status == 2:
        stream_url = d.get("stream_url") or {}
        flv_pull_url: dict[str, str] = stream_url.get("flv_pull_url") or {}
        m3u8_pull_url: dict[str, str] = stream_url.get("hls_pull_url_map") or {}
        hevc_flv_url = stream_url.get("hevc_flv_url")

        # 保留画质标签：将 dict items 按画质等级降序（OD>BD>UHD>HD>SD>LD）排序
        def _sort_quality_items(dd: dict[str, str]) -> list[tuple[str, str]]:
            order = {"ORIGIN": 0, "OD": 0, "BD": 1, "UHD": 2, "HD": 3, "SD": 4, "LD": 5}
            return sorted(dd.items(), key=lambda kv: order.get(kv[0].upper(), 99))

        flv_pairs = _sort_quality_items(flv_pull_url)
        m3u8_pairs = _sort_quality_items(m3u8_pull_url)

        # 可用画质档位（统一为代码：ORIGIN→OD）
        def _norm_code(name: str) -> str:
            return "OD" if name.upper() in ("ORIGIN",) else name.upper()

        available_qualities = (
            [_norm_code(k) for k, _ in flv_pairs] if flv_pairs else [_norm_code(k) for k, _ in m3u8_pairs]
        )

        video_quality, quality_index = get_quality_index(video_quality)
        # 显式截断而非 _pad_list 静默填充
        flv_idx = min(quality_index, len(flv_pairs) - 1) if flv_pairs else 0
        m3u8_idx = min(quality_index, len(m3u8_pairs) - 1) if m3u8_pairs else 0
        flv_quality_name, flv_url = flv_pairs[flv_idx] if flv_pairs else ("", "")
        m3u8_quality_name, m3u8_url = m3u8_pairs[m3u8_idx] if m3u8_pairs else ("", "")
        actual_quality = _norm_code(flv_quality_name or m3u8_quality_name)

        m3u8_codec = urllib.parse.parse_qs(urllib.parse.urlparse(m3u8_url or "").query).get("codec", [""])[0]
        m3u8_is_hevc = "h265" in m3u8_codec.lower() or "hevc" in m3u8_codec.lower()
        use_hevc_flv = quality_index == 0 and bool(hevc_flv_url) and not m3u8_is_hevc
        if use_hevc_flv and hevc_flv_url:
            flv_url = hevc_flv_url
        if m3u8_url:
            ok = await get_response_status(url=m3u8_url, proxy_addr=proxy_addr)
        else:
            # 仅有 FLV 源：跳过对空 URL 的可用性校验，避免误判失败并错误降级画质
            ok = True
        if not ok:
            index = flv_idx + 1 if flv_idx < len(flv_pairs) - 1 else max(flv_idx - 1, 0)
            if m3u8_pairs:
                m3u8_quality_name, m3u8_url = m3u8_pairs[index]
            if not use_hevc_flv and flv_pairs:
                flv_quality_name, flv_url = flv_pairs[index]
            actual_quality = _norm_code(flv_quality_name or m3u8_quality_name)
        result |= {
            "is_live": True,
            "quality": video_quality,
            "actual_quality": actual_quality,
            "available_qualities": available_qualities,
            "m3u8_url": m3u8_url,
            "flv_url": flv_url,
            "record_url": m3u8_url or flv_url,
        }
    return result


@trace_error_decorator
async def get_tiktok_stream_url(
    json_data: dict[str, object] | None, video_quality: str | None = None, proxy_addr: str | None = None
) -> dict[str, object]:
    # 获取TikTok直播流URL
    if not json_data:
        return {"anchor_name": None, "is_live": False}

    def get_video_quality_url(stream: dict[str, object], q_key: str) -> list[StreamQuality]:
        # 从流列表中按画质索引选择 URL
        play_list: list[StreamQuality] = []
        for key in stream:
            url_info = cast(dict[str, object], stream[key])
            main_info = cast(dict[str, object], url_info.get("main") or {})
            sdk_params_raw = main_info.get("sdk_params")
            sdk_params: TiktokSdkParams = {}
            if isinstance(sdk_params_raw, str):
                sdk_params = cast(TiktokSdkParams, json.loads(sdk_params_raw))
            vbitrate = int(sdk_params.get("vbitrate", 0))
            v_codec = sdk_params.get("VCodec", "")

            play_url = ""
            url_value = cast(str, url_info.get(q_key) or "")
            if url_value:
                if url_value.endswith(".flv") or url_value.endswith(".m3u8"):
                    play_url = url_value + "?codec=" + v_codec
                else:
                    play_url = url_value + "&codec=" + v_codec

            resolution = sdk_params.get("resolution", "")
            if vbitrate != 0 and resolution:
                width, height = map(int, resolution.split("x"))
                play_list.append({"url": play_url, "vbitrate": vbitrate, "resolution": (width, height)})

        play_list.sort(
            key=lambda x: (-x.get("vbitrate", 0), -x.get("resolution", (0, 0))[0], -x.get("resolution", (0, 0))[1])
        )
        return play_list

    t = cast(TiktokStreamUrl, cast(object, json_data))
    live_room = t.get("LiveRoom") or {}
    user_info = live_room.get("liveRoomUserInfo") or {}
    user = user_info.get("user") or {}
    anchor_name = f"{user.get('nickname', '')}-{user.get('uniqueId', '')}"
    status = user.get("status", 4)

    result: dict[str, object] = {"anchor_name": anchor_name, "is_live": False}

    if status == 2:
        live_detail = live_room.get("liveRoom") or {}
        stream_data_outer = live_detail.get("streamData") or {}
        pull_data = stream_data_outer.get("pull_data") or {}
        stream_data_raw = pull_data.get("stream_data", "")
        parsed: dict[str, object] = cast(dict[str, object], json.loads(stream_data_raw)) if stream_data_raw else {}
        stream_data = cast(dict[str, object], parsed.get("data", {}) if parsed else {})
        flv_url_list = get_video_quality_url(stream_data, "flv")
        m3u8_url_list = get_video_quality_url(stream_data, "hls")

        if not flv_url_list and not m3u8_url_list:
            return result

        _ = _pad_list(flv_url_list)
        _ = _pad_list(m3u8_url_list)
        video_quality, quality_index = get_quality_index(video_quality)
        quality_index = min(quality_index, len(flv_url_list) - 1) if flv_url_list else 0
        m3u8_quality_index = min(quality_index, len(m3u8_url_list) - 1) if m3u8_url_list else 0
        flv_dict: StreamQuality | dict[str, str] = flv_url_list[quality_index] if flv_url_list else {"url": ""}
        m3u8_dict: StreamQuality | dict[str, str] = m3u8_url_list[m3u8_quality_index] if m3u8_url_list else {"url": ""}

        check_url = cast(str, m3u8_dict.get("url") or flv_dict.get("url"))
        if not check_url:
            ok = False
        else:
            ok = await get_response_status(url=check_url, proxy_addr=proxy_addr, http2=False)

        if not ok:
            fallback_index = quality_index + 1 if quality_index < 4 else max(quality_index - 1, 0)
            if flv_url_list:
                fallback_index = min(fallback_index, len(flv_url_list) - 1)
                flv_dict = flv_url_list[fallback_index]
            if m3u8_url_list:
                m3u8_fallback = min(fallback_index, len(m3u8_url_list) - 1)
                m3u8_dict = m3u8_url_list[m3u8_fallback]

        flv_url = flv_dict.get("url", "")
        m3u8_url = m3u8_dict.get("url", "")
        # 实际选中项的 vbitrate → 画质代码
        actual_quality = bitrate_to_quality(int(flv_dict.get("vbitrate", 0))) if flv_dict else video_quality
        available_qualities = (
            [bitrate_to_quality(x.get("vbitrate", 0)) for x in flv_url_list if x] if flv_url_list else None
        )
        result |= {
            "is_live": True,
            "title": (live_room.get("liveRoom") or {}).get("title", ""),
            "quality": video_quality,
            "actual_quality": actual_quality,
            "available_qualities": available_qualities,
            "m3u8_url": m3u8_url,
            "flv_url": m3u8_url or flv_url,
            "record_url": m3u8_url or flv_url,
        }
    return result


@trace_error_decorator
async def get_kuaishou_stream_url(json_data: dict[str, object], video_quality: str | None = None) -> dict[str, object]:
    # 获取快手直播流URL
    k = cast(KuaishouStreamUrl, cast(object, json_data))
    if k.get("type") == 1 and not k.get("is_live"):
        return json_data
    live_status = k.get("is_live", False)

    result: dict[str, object] = {"type": 2, "anchor_name": k.get("anchor_name", ""), "is_live": live_status}

    if live_status:
        _, quality_index = get_quality_index(video_quality)
        actual_quality: str | None = None
        available_qualities: list[str] | None = None
        m3u8_list = k.get("m3u8_url_list")
        if m3u8_list:
            m3u8_url_list = m3u8_list[::-1]
            idx = min(quality_index, len(m3u8_url_list) - 1)
            result["m3u8_url"] = m3u8_url_list[idx].get("url", "")

        flv_list = k.get("flv_url_list")
        if flv_list:
            if "bitrate" in flv_list[0]:
                flv_sorted = sorted(flv_list, key=lambda x: x.get("bitrate", 0), reverse=True)
                quality_str = video_quality.upper() if video_quality else "OD"
                if quality_str.isdigit():
                    bit_items = list(QUALITY_MAPPING_BIT.items())
                    q_idx = min(int(quality_str[0]), len(bit_items) - 1)
                    video_quality, quality_index_bitrate_value = bit_items[q_idx]
                else:
                    quality_index_bitrate_value = QUALITY_MAPPING_BIT.get(quality_str, 99999)
                    video_quality = quality_str
                sel_index = next(
                    (i for i, x in enumerate(flv_sorted) if x.get("bitrate", 0) <= quality_index_bitrate_value), None
                )
                if sel_index is None:
                    sel_index = len(flv_sorted) - 1
                selected = flv_sorted[sel_index]
                actual_quality = bitrate_to_quality(selected.get("bitrate", 0))
                available_qualities = [bitrate_to_quality(x.get("bitrate", 0)) for x in flv_sorted]
                result["flv_url"] = selected.get("url", "")
                result["record_url"] = selected.get("url", "")
            else:
                flv_rev = flv_list[::-1]
                idx = min(quality_index, len(flv_rev) - 1)
                flv_url = flv_rev[idx].get("url", "")
                result["flv_url"] = flv_url
                result["record_url"] = flv_url
        result["quality"] = video_quality
        result["actual_quality"] = actual_quality
        result["available_qualities"] = available_qualities
    return result


@trace_error_decorator
async def get_huya_stream_url(json_data: dict[str, object], video_quality: str | None = None) -> dict[str, object]:
    # 获取虎牙直播流URL
    h = cast(HuyaStreamUrl, cast(object, json_data))
    data_list: list[HuyaDataItem] = h.get("data") or []
    if not data_list:
        return {"anchor_name": "", "is_live": False}
    item0 = data_list[0]
    game_live_info = item0.get("gameLiveInfo") or {}
    live_title = game_live_info.get("introduction", "")
    stream_info_list = item0.get("gameStreamInfoList") or []
    anchor_name = game_live_info.get("nick", "")

    result: dict[str, object] = {"anchor_name": anchor_name, "is_live": False}
    if not stream_info_list:
        return result

    # 画质 ratio 解析（与历史行为一致）：从首个候选的 sFlvAntiCode 中解析 exsphd 档位表，
    # 按 video_quality 选择对应 ratio；无 exsphd 时不附加 ratio（保持原始防盗链参数原样）。
    first_anti = stream_info_list[0].get("sFlvAntiCode") or ""
    quality_list = first_anti.split("&exsphd=")
    actual_quality = video_quality  # OD/BD 默认即请求值
    available_qualities: list[str] | None = None
    ratio_val: str = ""
    if len(quality_list) > 1 and video_quality not in ["OD", "BD"]:
        pattern = r"(?<=264_)\d+"
        qlist = cast(list[str], re.findall(pattern, quality_list[1]))[::-1]
        if qlist:
            # 不再 _pad_list；按实际可用档位构造 options
            labels = ["UHD", "HD", "SD", "LD"]
            video_quality_options = dict(zip(labels, qlist))
            available_qualities = ["OD", "BD"] + list(video_quality_options.keys())
            if video_quality in video_quality_options:
                ratio_val = video_quality_options[video_quality]
                actual_quality = video_quality
            else:
                # 请求档位不在可用列表：降级到最近的更低档，若无更低档则取最低可用档
                req_level = QUALITY_LEVEL.get(video_quality or "", 4)
                lower = [
                    (level, ratio)
                    for level, ratio in video_quality_options.items()
                    if QUALITY_LEVEL.get(level, 0) >= req_level
                ]
                if lower:
                    actual_quality, ratio_val = lower[0]
                else:
                    # 取最低可用档（列表最后一个）
                    actual_quality, ratio_val = list(video_quality_options.items())[-1]

    # CDN 候选排序：实测 HLS 可靠承载线路为 HS（AL/TX 常因该房间未启用该线路返回 403，
    # 且三条线路共享完全相同的防盗链参数——AL/TX 的 403 非请求问题、而是线路未承载推流，
    # 随时可能切换）。故枚举全部 CDN 候选交给 select_source_url 逐条按可达性校验，
    # 首位优先 HS 以最大化「首试即中」。线路可用性动态变化，必须每轮现拉现校验、不得长期缓存。
    cdn_priority = ["HS", "HW", "TX", "AL"]

    def _rank(cdn: object) -> int:
        try:
            return cdn_priority.index(str(cdn))
        except ValueError:
            return len(cdn_priority)

    candidates: list[dict[str, str]] = []
    for cdn in sorted(stream_info_list, key=lambda c: _rank(c.get("sCdnType"))):
        s_cdn = cdn.get("sCdnType", "") or ""
        s_stream_name = cdn.get("sStreamName", "")
        s_flv_url = cdn.get("sFlvUrl", "")
        s_flv_suffix = cdn.get("sFlvUrlSuffix", "")
        s_flv_anti = cdn.get("sFlvAntiCode") or ""
        s_hls_url = cdn.get("sHlsUrl", "")
        s_hls_suffix = cdn.get("sHlsUrlSuffix", "")
        s_hls_anti = cdn.get("sHlsAntiCode") or ""
        if not s_stream_name or not s_flv_anti:
            continue
        # 直接使用房间页内嵌防盗链参数（与端到端校验报告一致：HS 经 GET 校验 200 正常拉流），
        # 不重建 anti_code（避免引入未被验证的签名算法）。统一降为 http：实测 https 返回 403、
        # 仅 http 可用（含 HLS/FLV），与校验探针共用此 scheme 防止「校验 http 可用、录制 https 被拒」。
        flv_url = f"{str(s_flv_url).replace('https://', 'http://')}/{s_stream_name}.{s_flv_suffix}?{s_flv_anti}"
        if ratio_val:
            flv_url = flv_url + "&ratio=" + str(ratio_val)
        hls_url = ""
        if s_hls_anti and s_hls_url and s_hls_suffix:
            hls_url = f"{str(s_hls_url).replace('https://', 'http://')}/{s_stream_name}.{s_hls_suffix}?{s_hls_anti}"
            if ratio_val:
                hls_url = hls_url + "&ratio=" + str(ratio_val)
        if hls_url or flv_url:
            candidates.append({"cdn_type": s_cdn, "m3u8_url": hls_url, "flv_url": flv_url})

    if not candidates:
        return result

    # 主源取排序后首位候选；全部候选注入 m3u8_url_list/flv_url_list 供 select_source_url
    # 逐条按可达性校验、首条可达即选用（动态规避离线 CDN 线路）。record_url 与所选 flv 同源。
    primary = candidates[0]
    m3u8_url_list = [c["m3u8_url"] for c in candidates if c["m3u8_url"]]
    flv_url_list = [c["flv_url"] for c in candidates if c["flv_url"]]
    record_url = primary["flv_url"] or primary["m3u8_url"]
    result |= {
        "is_live": True,
        "title": live_title,
        "quality": video_quality,
        "actual_quality": actual_quality,
        "available_qualities": available_qualities,
        "m3u8_url": primary["m3u8_url"],
        "m3u8_url_list": m3u8_url_list,
        "flv_url": primary["flv_url"],
        "flv_url_list": flv_url_list,
        "record_url": record_url,
    }
    return result


@trace_error_decorator
async def get_douyu_stream_url(
    json_data: dict[str, object], video_quality: str | None = None, cookies: str = "", proxy_addr: str | None = None
) -> dict[str, object]:
    # 获取斗鱼直播流URL
    dy = cast(DouyuStreamUrl, cast(object, json_data))
    if not dy.get("is_live"):
        return {"anchor_name": dy.get("anchor_name"), "is_live": False}

    video_quality_options = {"OD": "0", "BD": "0", "UHD": "3", "HD": "2", "SD": "1", "LD": "1"}
    # 反向映射：rate 值 → 画质代码（多对一取最高档）
    rate_to_code = {"0": "OD", "3": "UHD", "2": "HD", "1": "SD"}

    rid = str(dy.get("room_id", ""))
    rate = video_quality_options.get(video_quality or "", "0")
    flv_data = await get_douyu_stream_data(rid, rate, cookies=cookies, proxy_addr=proxy_addr)
    flv_data_inner = cast(DouyuFlvData, flv_data.get("data") or {})
    rtmp_url = flv_data_inner.get("rtmp_url", "")
    rtmp_live = flv_data_inner.get("rtmp_live", "")
    # 平台实际下发的 rate
    actual_rate = str(flv_data_inner.get("rate", ""))
    actual_quality = rate_to_code.get(actual_rate, video_quality)

    result: dict[str, object] = {
        "anchor_name": dy.get("anchor_name"),
        "is_live": True,
        "quality": video_quality,
        "actual_quality": actual_quality,
    }
    if rtmp_live:
        flv_url = f"{rtmp_url}/{rtmp_live}"
        result |= {"flv_url": flv_url, "record_url": flv_url}
        # 斗鱼 wsAuth token 对 FLV/HLS 通用：路径 .flv 换 .m3u8 即同 token 的 HLS 播放列表
        # （实测 hw CDN 200 + application/vnd.apple.mpegurl，且 token 存活远超 75 秒）。
        # 游客态 FLV 长连接常被 CDN 约 70 秒掐断（反复分段），HLS 逐段拉取不维持长连接、
        # 天然免疫；select_source_url 会在启用 HLS 采集时优先校验并选用 m3u8，不可达时
        # 自动回退 FLV，故此处无条件附带该候选。
        path, _, query = flv_url.partition("?")
        if path.endswith(".flv"):
            result["m3u8_url"] = f"{path[:-4]}.m3u8" + (f"?{query}" if query else "")
    return result


@trace_error_decorator
async def get_yy_stream_url(json_data: dict[str, object]) -> dict[str, object]:
    # 获取YY直播流URL
    y = cast(YyStreamUrl, cast(object, json_data))
    anchor_name = y.get("anchor_name", "")
    result: dict[str, object] = {"anchor_name": anchor_name, "is_live": False}
    avp = y.get("avp_info_res")
    if avp:
        stream_line_addr = avp.get("stream_line_addr") or {}
        if not stream_line_addr:
            return result
        cdn_info = list(stream_line_addr.values())[0]
        cdn_detail = cdn_info.get("cdn_info") or {}
        flv_url = cdn_detail.get("url", "")
        result |= {
            "is_live": True,
            "title": y.get("title", ""),
            "quality": "OD",
            "flv_url": flv_url,
            "record_url": flv_url,
        }
    return result


@trace_error_decorator
async def get_bilibili_stream_url(
    json_data: dict[str, object], video_quality: str | None = None, proxy_addr: str | None = None, cookies: str = ""
) -> dict[str, object]:
    # 获取B站直播流URL
    b = cast(BilibiliStreamUrl, cast(object, json_data))
    anchor_name = b.get("anchor_name", "")
    if not b.get("live_status"):
        return {"anchor_name": anchor_name, "is_live": False}

    room_url = b.get("room_url", "")
    video_quality_options = {"OD": "10000", "BD": "400", "UHD": "250", "HD": "150", "SD": "80", "LD": "80"}

    select_quality = video_quality_options.get((video_quality or "OD").upper(), "10000")
    play_url_data = await get_bilibili_stream_data(
        room_url, qn=select_quality, platform="web", proxy_addr=proxy_addr, cookies=cookies
    )
    if not play_url_data:
        return {"anchor_name": anchor_name, "is_live": False}
    pd = cast(BilibiliPlayData, cast(object, play_url_data))
    # qn → 画质代码 反向映射
    qn_to_code = {v: k for k, v in video_quality_options.items()}
    actual_quality = qn_to_code.get(str(pd.get("current_qn", "")), video_quality)
    accept_qn = pd.get("accept_qn") or []
    available_qualities = [qn_to_code.get(str(q), str(q)) for q in accept_qn] or None
    return {
        "anchor_name": anchor_name,
        "is_live": True,
        "title": b.get("title", ""),
        "quality": video_quality,
        "actual_quality": actual_quality,
        "available_qualities": available_qualities,
        "record_url": pd.get("url", ""),
    }


@trace_error_decorator
async def get_netease_stream_url(json_data: dict[str, object], video_quality: str | None = None) -> dict[str, object]:
    # 获取网易CC直播流URL
    n = cast(NeteaseStreamUrl, cast(object, json_data))
    if not n.get("is_live"):
        return json_data

    m3u8_url = n.get("m3u8_url", "")
    flv_url: str | None = None
    actual_quality: str | None = None
    available_qualities: list[str] | None = None
    stream_list_data = n.get("stream_list")
    if stream_list_data:
        stream_list = stream_list_data.get("resolution") or {}
        order = ["blueray", "ultra", "high", "standard"]
        sorted_keys = [key for key in order if key in stream_list]
        if not sorted_keys:
            return json_data
        video_quality, quality_index = get_quality_index(video_quality)
        # 显式截断，记录实际选中的画质名
        idx = min(quality_index, len(sorted_keys) - 1)
        selected_quality = sorted_keys[idx]
        actual_quality = NETEASE_QUALITY_MAP.get(selected_quality, video_quality)
        available_qualities = [NETEASE_QUALITY_MAP.get(k, k.upper()) for k in sorted_keys]
        flv_url_list = stream_list[selected_quality].get("cdn") or {}
        selected_cdn = list(flv_url_list.keys())[0]
        flv_url = flv_url_list[selected_cdn]

    return {
        "is_live": True,
        "anchor_name": n.get("anchor_name", ""),
        "title": n.get("title", ""),
        "quality": video_quality,
        "actual_quality": actual_quality,
        "available_qualities": available_qualities,
        "m3u8_url": m3u8_url,
        "flv_url": flv_url,
        "record_url": flv_url or m3u8_url,
    }


async def get_stream_url(
    json_data: dict[str, object],
    video_quality: str | None = None,
    url_type: str = "m3u8",
    spec: bool = False,
    hls_extra_key: str | int | None = None,
    flv_extra_key: str | int | None = None,
) -> dict[str, object]:
    # 通用直播流URL获取函数
    g = cast(GenericStreamUrl, cast(object, json_data))
    if not g.get("is_live"):
        return json_data

    play_url_list: list[dict[str, str]] = g.get("play_url_list") or []
    if not play_url_list:
        return json_data
    _ = _pad_list(play_url_list)

    video_quality, selected_quality = get_quality_index(video_quality)
    data: dict[str, object] = {"anchor_name": g.get("anchor_name", ""), "is_live": True}

    def get_url(key: str | int | None) -> object:
        # 从直播流响应中提取流地址
        play_url = play_url_list[selected_quality]
        return play_url[cast(str, key)] if key else play_url

    if url_type == "all":
        m3u8_url = get_url(hls_extra_key)
        flv_url = get_url(flv_extra_key)
        data |= {
            "m3u8_url": g.get("m3u8_url", "") if spec else m3u8_url,
            "flv_url": g.get("flv_url", "") if spec else flv_url,
            "record_url": m3u8_url,
        }
    elif url_type == "m3u8":
        m3u8_url = get_url(hls_extra_key)
        data |= {"m3u8_url": g.get("m3u8_url", "") if spec else m3u8_url, "record_url": m3u8_url}
    else:
        flv_url = get_url(flv_extra_key)
        data |= {"flv_url": flv_url, "record_url": flv_url}
    data["title"] = g.get("title", "")
    data["quality"] = video_quality
    return data
