#!/usr/bin/env python3
# -*- encoding: utf-8 -*-
import json
import re
from typing import TypedDict, TypeVar, cast

from loguru import logger

import i18n

from .async_http import get_response_status
from .spider import get_bilibili_stream_data, get_douyu_stream_data
from .utils import trace_error_decorator

# 直播流地址获取模块：从各平台解析结果中取流地址、选画质，支持多档位与就近降级。
#
# 职责：把各平台 spider 解析出的 json_data 归一化为统一结构
#   {is_live, anchor_name, title, quality, actual_quality, available_qualities,
#    m3u8_url, flv_url, record_url, m3u8_url_list, flv_url_list}，供上层录制与
#    流地址校验（src.stream_select.select_source_url）消费。
# 核心机制：
#   - 画质档位映射（QUALITY_MAPPING / QUALITY_MAPPING_BIT / QUALITY_LEVEL）与平台专属
#     档位表（HUYA_FIXED_TIERS / DOUYU_RATE_BY_CODE）把中文画质名转为各平台请求参数；
#   - 各平台按统一画质索引选档，不可用档位就近降级（is_downgrade 判定告警）；
#   - 虎牙/斗鱼细粒度蓝光档位走各自专属表，不污染通用 0-5 数字索引语义。
# 与其它模块的关系：本模块只「取地址 + 选画质降级」，不做可达性校验与 ffmpeg 拉流；
#   地址可用性由 stream_select.select_source_url 逐候选校验、首条可达即选用。
# 设计取舍：所有 get_*_stream_url 缺字段即按「未开播」返回 is_live=False，保持上游
#   json_data 透传，避免对离线房间伪造 is_live=True 误导调度器。

# Author: Hmily
# GitHub: https://github.com/ihmily
# Copyright (c) 2023-2025 by Hmily, All Rights Reserved.
# Function: Get live stream data.


# 通用列表填充辅助的类型变量：_pad_list 把任意元素类型的列表填充到指定最小长度
_PadT = TypeVar("_PadT")


# ---- 各平台 json_data 结构类型（仅用于静态类型检查，运行时完全透明）----
# 抖音解析结果结构：status=2 表示直播中，stream_url 内含 flv/hls 拉流映射
class DouyinStreamUrl(TypedDict, total=False):
    anchor_name: str | None
    status: int
    stream_url: "DouyinStreamInner"


class DouyinStreamInner(TypedDict, total=False):
    flv_pull_url: dict[str, str]
    hls_pull_url_map: dict[str, str]
    hevc_flv_url: str


# TikTok 解析结果顶层：LiveRoom 包裹直播间与用户态
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


# 快手 m3u8 候选项：单条 url
class KuaishouM3u8Item(TypedDict, total=False):
    url: str


class KuaishouFlvItem(TypedDict, total=False):
    url: str
    bitrate: int


# 快手解析结果：type(1未开播/2开播)、m3u8_url_list / flv_url_list 候选
class KuaishouStreamUrl(TypedDict, total=False):
    type: int
    is_live: bool
    anchor_name: str
    m3u8_url_list: list[KuaishouM3u8Item]
    flv_url_list: list[KuaishouFlvItem]


# 虎牙解析结果：data 列表，每项含房间信息与多 CDN 线路
class HuyaStreamUrl(TypedDict, total=False):
    data: list["HuyaDataItem"]


class HuyaDataItem(TypedDict, total=False):
    gameLiveInfo: "HuyaGameLiveInfo"
    gameStreamInfoList: list["HuyaStreamInfo"]


class HuyaGameLiveInfo(TypedDict, total=False):
    introduction: str
    nick: str
    # 房间最高码率(kbps)，画质 ratio 推导的上限来源；API 实测为数值，
    # 异常形态（如字符串）由取用处 try/except 兜底为 0
    bitRate: int


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


# B站解析结果：live_status(1=直播中)、anchor_name、title、room_url
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
    # 元素有两种契约（裸 URL 串 / 画质→地址字典），依据与处置见 _PLAY_URL_KEY_ORDER 注释
    play_url_list: list[str | dict[str, str]]


# 排序用画质项：url + vbitrate（码率）+ resolution（宽高元组）
class StreamQuality(TypedDict, total=False):
    url: str
    vbitrate: int
    resolution: tuple[int, int]


# TikTok 单路 sdk_params：vbitrate / VCodec（编码）/ resolution（宽x高）
class TiktokSdkParams(TypedDict, total=False):
    vbitrate: int
    VCodec: str
    resolution: str


# 画质 → 排序后列表中的位置（索引），全仓选档的唯一权威序（OD=0, BD=1, UHD=2, HD=3,
# SD=4, LD=5）。按名称选画质靠它定位，改本表顺序即整体错位。
# 蓝光子档位（BD30/BD20/BD8/BD4）不得塞进本表：那会撑开「数字输入 0-5」的语义、让通用
# 选档错位；它们由 get_quality_index 折叠到 BD 槽位，虎牙/斗鱼走各自专属档位表。
QUALITY_MAPPING = {"OD": 0, "BD": 1, "UHD": 2, "HD": 3, "SD": 4, "LD": 5}
QUALITY_MAPPING_BIT = {
    "OD": 99999,
    "BD": 4000,
    "BD30": 30000,
    "BD20": 20000,
    "BD8": 8000,
    "BD4": 4000,
    "UHD": 2000,
    "HD": 1000,
    "SD": 800,
    "LD": 600,
}

# 画质等级值（数值越大画质越低），用于降级判定。
# 蓝光子档位按码率上限插入等级序：OD/BD(0) > BD30(1) > BD20(2) > BD8(3) > BD4(4) > UHD(5) > HD(6) > SD(7) > LD(8)。
# （BD 与 OD 同级：两者在虎牙/斗鱼侧均不加 ratio/rate，即按原画拉流。）
QUALITY_LEVEL = {"OD": 0, "BD": 0, "BD30": 1, "BD20": 2, "BD8": 3, "BD4": 4, "UHD": 5, "HD": 6, "SD": 7, "LD": 8}

# 画质代码 → 中文名（对齐 main.py get_quality_code 的反向）
QUALITY_CODE_TO_ZH = {
    "OD": "原画",
    "BD": "蓝光",
    "BD30": "蓝光30M",
    "BD20": "蓝光20M",
    "BD8": "蓝光8M",
    "BD4": "蓝光4M",
    "UHD": "超清",
    "HD": "高清",
    "SD": "标清",
    "LD": "流畅",
}

# 蓝光子档位代码集合（虎牙/斗鱼细粒度档位）
BD_SUB_TIERS = frozenset({"BD30", "BD20", "BD8", "BD4"})

# 网易CC 画质名 → 统一代码
NETEASE_QUALITY_MAP = {"blueray": "OD", "ultra": "UHD", "high": "HD", "standard": "SD"}

# 抖音接口下发的画质键 → 统一画质代码。flv_pull_url / hls_pull_url_map 实测键为
# ORIGIN/FULL_HD1/HD1/SD1/SD2（app 端另有 ORIGIN 一路，见 src/spider.py 同名合并），
# 不是 OD/BD/UHD/... 这套内部代码。不折叠时其余键进不了 order 表（全落默认 99），
# 回采的 actual_quality 又查不到 QUALITY_LEVEL → is_downgrade 恒 False，降级完全静默。
DOUYIN_KEY_TO_CODE: dict[str, str] = {
    "ORIGIN": "OD",
    "FULL_HD1": "BD",
    "HD1": "HD",
    "SD1": "SD",
    "SD2": "LD",
}

# get_stream_url 未指定 extra_key 时的取值探测顺序。play_url_list 元素有两种契约：
# 「画质 → 地址」字典（键名各平台不统一）与「按画质排序的裸 URL 串」（spider.py 9 处同型写入）。
# 缺 key 时若把整份字典当地址返回，下游按 str 判型会静默丢弃；这里按「通用名 → 容器专属名」
# 探测、全落空返回 ""，让「无地址」显式成立而非塞 dict 进录制链路。
_PLAY_URL_KEY_ORDER: tuple[str, ...] = ("url", "play_url", "m3u8_url", "flv_url")

# ── 虎牙画质档位 ─────────────────────────────────────────────
# 虎牙细粒度档位：ratio 参数即该档位的码率上限（kbps）。2026-08-29 在 huya.com/chuhe
# （bitRate=30000）实测 ffmpeg 3 秒采样：ratio=0 原画 2560x1440@60；30000 蓝光30M
# 1080p60；20000 蓝光20M；8000 蓝光8M；4000 蓝光4M 1080p30；2000 超清 720p30；
# 500 流畅 800x450@24。各 CDN 线路共享同一防盗链参数，ratio 直接拼在 FLV/HLS URL 的
# query 上，流地址路径不变。
HUYA_FIXED_TIERS: tuple[tuple[str, int], ...] = (("BD30", 30000), ("BD20", 20000), ("BD8", 8000), ("BD4", 4000))
# ratio(字符串) → 画质代码：选中/降级后回采实际档位用。
# 必须登记表外可能值（1000/250）：未命中会把 actual_quality 回写成请求档，
# 把「URL 挂着更低 ratio、面板显示按请求录」的降级彻底伪装掉。
HUYA_RATIO_TO_CODE = {
    "30000": "BD30",
    "20000": "BD20",
    "8000": "BD8",
    "4000": "BD4",
    "2000": "UHD",
    "1000": "HD",
    "500": "LD",
    "250": "LD",
}
# 画质代码 → 虎牙 ratio（码率上限 kbps）：HUYA_RATIO_TO_CODE 的正向表，两个档位分支
# （蓝光子档位 / 旧档位）都以数值为唯一语义，不依赖 exsphd 的出现顺序。
# SD 无独立实测档，取 HD(1000) 与 LD(500) 之间的 800（对齐 QUALITY_MAPPING_BIT），
# 由就近取值逻辑落到房间实际存在的档。
HUYA_RATIO_BY_CODE: dict[str, int] = {
    "BD30": 30000,
    "BD20": 20000,
    "BD8": 8000,
    "BD4": 4000,
    "UHD": 2000,
    "HD": 1000,
    "SD": 800,
    "LD": 500,
}
# 档位输出序（画质由高到低，OD/BD 除外）：available_qualities 按此顺序枚举，
# 保证同一档位集合的输出顺序与 exsphd 的字符串顺序无关。
HUYA_CODE_ORDER: tuple[str, ...] = ("BD30", "BD20", "BD8", "BD4", "UHD", "HD", "SD", "LD")


def huya_code_for_ratio(ratio: int) -> str:
    # 按数值给虎牙 ratio 贴档位标签：精确命中表内值直接返回；表外值（12000/6000 等
    # exsphd 可能携带的档）取绝对距离最近的档；距离相同时偏向更低画质（QUALITY_LEVEL 更大
    # 的一侧）——宁可多打一条降级告警，也不把更低的实际档位伪装成高档。
    # 返回 "" 表示完全无法命名（调用方按请求档兜底）。
    exact = HUYA_RATIO_TO_CODE.get(str(ratio))
    if exact:
        return exact
    best_code = ""
    best_key: tuple[int, int] | None = None
    for code, tier_ratio in HUYA_RATIO_BY_CODE.items():
        # 第二项取负等级：min 比较下让「更低画质」在同距离时胜出
        key = (abs(tier_ratio - ratio), -QUALITY_LEVEL[code])
        if best_key is None or key < best_key:
            best_key, best_code = key, code
    return best_code


# ── 斗鱼画质档位 ─────────────────────────────────────────────
# 斗鱼 rate 语义（2026-08-29 在 3168536 房间实测）：0=原画 1080p60；8200=蓝光8M（房间
# 无此档时服务端钳制到 4/蓝光4M）；4000=蓝光4M 1080p30；3=超清 720p30；2=高清 540p25；
# 1=流畅（无档位时钳制到 2）。服务端自带「就近钳制」：请求不存在的档位不报错，而是
# 下发更低档，rate 字段回采真实档位。
DOUYU_RATE_BY_CODE = {
    "OD": "0",
    "BD": "0",
    "BD30": "8200",
    "BD20": "8200",
    "BD8": "8200",
    "BD4": "4000",
    "UHD": "3",
    "HD": "2",
    "SD": "1",
    "LD": "1",
}
# 斗鱼下发 rate（字符串）→ 画质代码：回采实际档位用
DOUYU_RATE_TO_CODE = {
    "0": "OD",
    "1": "SD",
    "2": "HD",
    "3": "UHD",
    "4": "BD4",
    "8200": "BD8",
    "4000": "BD4",
    "2000": "UHD",
}
# 斗鱼降级链：各请求 rate 失败（原画需登录等被限制场景）时依次回退的更低 rate。
# 斗鱼 rates 按画质从高到低的全序（用于构造「严格低于请求档」的回退序列）。
DOUYU_RATE_DESC = ("8200", "4000", "3", "2", "1")


def bitrate_to_quality(bitrate: int) -> str:
    # 根据码率反查画质代码：返回码率上限 >= 给定值的最高档；0/未知回退 OD。
    # 按 LD→OD 升序查找，首个「容量 >= 实码率」的档即能容纳该码率的最低档，
    # 避免把低码率源误标成高画质。
    if not bitrate or bitrate <= 0:
        return "OD"
    for code in ("LD", "SD", "HD", "UHD", "BD", "OD"):
        if bitrate <= QUALITY_MAPPING_BIT[code]:
            return code
    return "OD"


def code_to_zh(code: str | None) -> str:
    # 画质代码转中文；未知代码原样返回。
    # 原样返回而非兜底默认，避免把解析异常（如 None/空串）伪装成有效画质名。
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


def _pad_list(url_list: list[_PadT], min_length: int = 6) -> list[_PadT] | list[None]:
    # 填充到指定最小长度。空列表返回新列表（无法以末元素填充，填 None 防调用方越界），
    # 非空则原地补齐后返回自身；调用方一律以返回值赋回原变量，不依赖「原地修改」副作用。
    # 默认 6 而非 5：LD 在 QUALITY_MAPPING 索引为 5，恰返回 5 档时 url_list[5] 会越界，
    # 用户选「流畅」时部分平台永远录不上；6 档下 min(quality_index, len-1) 仍生效。
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
        # 原写 int(quality_str[0])，只取首字符——"10" 被当成 1（BD）录成蓝光。
        # 纯数字串按整值解析，越界（>=6）仍按原口径归 0（OD）。上限钳在 9：调用方可能递来
        # 任意长度的数字串（配置/接口下发），int() 对超长串在 3.14 有位数上限、抛 ValueError 反而
        # 穿透房间线程；先按前两位取足够区分「越界」的判据即可。
        quality_int = int(quality_str) if len(quality_str) <= 9 else 0
        keys = list(QUALITY_MAPPING.keys())
        if quality_int >= len(keys):
            quality_int = 0
        quality_str = keys[quality_int]
    # 蓝光子档位不参与通用索引：折叠到 BD 槽位（抖音/TikTok 等按索引选档的平台
    # 请求 蓝光4M/8M/20M/30M 时退化为「蓝光」档，保持其余档位索引语义不变）
    if quality_str in BD_SUB_TIERS:
        quality_str = "BD"
    if quality_str not in QUALITY_MAPPING:
        quality_str = list(QUALITY_MAPPING.keys())[0]
    return quality_str, QUALITY_MAPPING[quality_str]


def _probe_headers(platform: str) -> dict[str, str]:
    # 本模块两处 HLS 探针（抖音 / TikTok）的请求头：headers=None 会让出网 UA 落到 httpx 默认值，
    # 而 stream_select._validate_stream_url 与 ffmpeg 录制都显式补 UA——同一条流三种指纹，探针被
    # CDN 风控误判的概率显著高于录制侧（表现为「判不可达 → 相邻档降级」而 ffmpeg 其实录得上）。
    # UA 唯一事实源在 stream_select，此处只转发。
    # 就地延迟导入而非模块级：src.stream_select 顶层 import main、main 又 import 本模块，模块级
    # 导入会在 python main.py（__main__ 之外二次执行 main）下形成环，实测抛 ImportError。
    from .stream_select import MOBILE_UA, get_record_user_agent

    return {"User-Agent": get_record_user_agent(platform) or MOBILE_UA}


@trace_error_decorator
async def get_douyin_stream_url(
    json_data: dict[str, object], video_quality: str | None = None, proxy_addr: str | None = None
) -> dict[str, object]:
    # 抖音：status==2 才算开播；flv/hls 两张档位表按 QUALITY_MAPPING 索引选档，不可达时单步降级
    d = cast(DouyinStreamUrl, cast(object, json_data))
    anchor_name = d.get("anchor_name")
    result: dict[str, object] = {"anchor_name": anchor_name, "is_live": False}
    status = d.get("status", 4)
    # 抖音 status 约定：2=直播中；其余值（含默认 4=未开播/轮播）一律按非 live 处理。
    # 不能把"未开播"误判为 live，否则会带着空地址进入录制流程、空跑一路 ffmpeg。

    if status == 2:
        # stream_url 及各档位表都是平台下发的结构，`or {}` 只兜住「缺失/None」，
        # 兜不住「下发成字符串/list」——那种形态下 .get 抛 AttributeError，被装饰器吞成「未开播」，
        # 在播房间从此静默不录。逐层 isinstance 归一，异常形态一律按空表处理（等价于「无档位」）。
        stream_url = d.get("stream_url")
        if not isinstance(stream_url, dict):
            stream_url = {}
        raw_flv = stream_url.get("flv_pull_url")
        flv_pull_url: dict[str, str] = raw_flv if isinstance(raw_flv, dict) else {}
        raw_m3u8 = stream_url.get("hls_pull_url_map")
        m3u8_pull_url: dict[str, str] = raw_m3u8 if isinstance(raw_m3u8, dict) else {}
        hevc_flv_url = stream_url.get("hevc_flv_url")

        # 保留画质标签：将 dict items 按画质等级降序（OD>BD>UHD>HD>SD>LD）排序
        def _sort_quality_items(dd: dict[str, str]) -> list[tuple[str, str]]:
            # order 由统一代码表推导，不写字面量字典：字面量版认不出抖音真实键
            # （FULL_HD1/HD1/SD1/SD2），全落默认 99，sorted 稳定 ⇒ 排序结果 = 接口返回顺序。
            order = {name: QUALITY_MAPPING.get(code, 99) for name, code in DOUYIN_KEY_TO_CODE.items()}
            order.update(QUALITY_MAPPING)
            return sorted(dd.items(), key=lambda kv: order.get(kv[0].upper(), 99))

        flv_pairs = _sort_quality_items(flv_pull_url)
        m3u8_pairs = _sort_quality_items(m3u8_pull_url)

        # 可用画质档位（统一为代码：ORIGIN→OD，FULL_HD1/HD1/SD1/SD2 → BD/HD/SD/LD）
        def _norm_code(name: str) -> str:
            key = name.upper()
            code = DOUYIN_KEY_TO_CODE.get(key)
            if code:
                return code
            # 未知键：既不进 order 表也进不了 QUALITY_LEVEL（is_downgrade 会静默返回 False）。
            # 本接口不下发码率/分辨率，无法按码率反查档位；回退口径为「原样上抛 + 排在最末」
            # （order 默认 99 = 按最低档对待），宁可少选也不把未知档当高档，并留痕以便补表。
            if key and key not in QUALITY_LEVEL:
                logger.warning(
                    i18n.tr(
                        "[抖音直播] 未知画质键 {name}，无法映射为统一画质代码（按最低档参与排序与降级判定）",
                        name=name,
                    )
                )
            return key

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

        # h265 判定不再在此另写一份。原实现用 `"h265" in codec or "hevc" in codec`
        # 做子串包含，选源侧 _is_h265 只认 codec 全等 h265——同一条流两处口径不一致，HEVC/H265 地址在
        # 选源侧不被剔除、仍被交付 ffmpeg 直拷。现在三处共用 stream_select._is_h265（函数内 import，
        # 理由同 _probe_headers 上方的循环导入说明）。
        from .stream_select import _is_h265

        m3u8_is_hevc = bool(m3u8_url) and _is_h265(m3u8_url)
        # 仅原画请求(quality_index==0)且存在 hevc 备用地址、且 m3u8 非 h265 时启用 hevc flv；
        # 否则仍走通用 h264 源，避免把编码不兼容的源当成可录地址。
        flv_url_list: list[str] = []
        use_hevc_flv = quality_index == 0 and bool(hevc_flv_url) and not m3u8_is_hevc
        if use_hevc_flv and hevc_flv_url:
            # 被替换的 h264 原画地址必须存入 flv_url_list：选源层会剔除一切 codec=h265 候选，
            # 不保留则「HLS 采集关闭 / m3u8 缺席」的原画 hevc 房过滤后零可用候选，每轮
            # 「本轮无可用源」永不录制。select_source_url 会把 flv_url_list 追加在主候选之后：
            # HLS 开启时仍 m3u8 优先，HLS 关闭/不可达时落到这条 h264 FLV。
            # flv_pull_url 条目若自带 codec=h265 标记同样会被选源层剔除，不收进备选徒增告警。
            # 函数内 import：stream_select 顶层 import main 会循环导入，惯例同 _probe_headers。
            # _is_h265 已提到上方与本分支共用（同一处 import），此处不再重复导入。
            if flv_url and flv_url != hevc_flv_url and not _is_h265(flv_url):
                flv_url_list.append(flv_url)
            flv_url = hevc_flv_url
        if m3u8_url:
            # 探针必须与 stream_select / ffmpeg 用同一份拉流侧 SSL 口径
            # （get_effective_ssl_verify(platform)），否则用户关闭证书校验后探针必然报错 →
            # 判不可达 → 明明可录的档位被静默降级。platform 取 main.py 分派处的同名平台标识。
            ok = await get_response_status(
                url=m3u8_url, proxy=proxy_addr, platform="抖音直播", headers=_probe_headers("抖音直播")
            )
        else:
            # 仅有 FLV 源：跳过对空 URL 的可用性校验，避免误判失败并错误降级画质
            ok = True
        if not ok:
            # m3u8 不可达时向相邻档降级：还有更高档就升一档，否则降到前一档；仅做单步回退，
            # 避免跨档跳过可用画质。flv_pairs 可能比 m3u8_pairs 长（部分档位仅在 flv 侧存在），
            # 两侧各自钳制到自己的长度，避免 IndexError 被上游吞成「未开播」而漏录。
            if flv_pairs:
                index = flv_idx + 1 if flv_idx < len(flv_pairs) - 1 else max(flv_idx - 1, 0)
            else:
                index = m3u8_idx
            if m3u8_pairs:
                m3u8_index = min(index, len(m3u8_pairs) - 1)
                m3u8_quality_name, m3u8_url = m3u8_pairs[m3u8_index]
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
            "flv_url_list": flv_url_list,
            "record_url": m3u8_url or flv_url,
        }
    return result


@trace_error_decorator
async def get_tiktok_stream_url(
    json_data: dict[str, object] | None, video_quality: str | None = None, proxy_addr: str | None = None
) -> dict[str, object]:
    # TikTok：status==2 才算开播；档位按 sdk_params 的 vbitrate/分辨率排序后取索引，不可达时相邻档降级
    if not json_data:
        return {"anchor_name": None, "is_live": False}

    def get_video_quality_url(stream: dict[str, object], q_key: str) -> list[StreamQuality]:
        # 从流列表中按画质索引选择 URL
        play_list: list[StreamQuality] = []
        for key in stream:
            # 单条脏数据不得穿透整个候选构建：sdk_params 的 json.loads / resolution 的
            # split("x") 都会抛（上游 JSON 被截断或字段改版），一条坏条目会让装饰器把整个
            # TikTok 房间吞成未开播。
            try:
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
                    # 区分 URL 是否自带 query：带 .flv/.m3u8 后缀通常无 query 用 ? 拼接 codec；
                    # 其余（已含 query 的地址）用 & 追加，避免破坏原查询串。
                    if url_value.endswith(".flv") or url_value.endswith(".m3u8"):
                        play_url = url_value + "?codec=" + v_codec
                    else:
                        play_url = url_value + "&codec=" + v_codec

                resolution = sdk_params.get("resolution", "")
                if vbitrate != 0 and resolution:
                    width, height = map(int, resolution.split("x"))
                    play_list.append({"url": play_url, "vbitrate": vbitrate, "resolution": (width, height)})
            except (ValueError, TypeError) as e:
                logger.debug(
                    i18n.tr(
                        "TikTok 流条目解析异常，跳过该条目: {key} - {type_name}: {e}",
                        key=str(key),
                        type_name=type(e).__name__,
                        e=e,
                    )
                )
                continue

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
        # 本函数对每条流条目都做了逐条防御（见 get_video_quality_url 的
        # except，注释写明「一条坏条目不得让整个房间吞成未开播」），而这一句却裸在 try 之外：
        # 上游 stream_data 被截断时 json.loads 抛错、被 @trace_error_decorator 吞成「未开播」，
        # 整房静默不录，与逐条防御的设计意图自相矛盾。取不到正文就按「无档位可用」走下方既有
        # 的 `not flv and not m3u8 → return result` 出口，并留一条 warning 供排障。
        parsed: dict[str, object] = {}
        if isinstance(stream_data_raw, str) and stream_data_raw:
            try:
                parsed = cast(dict[str, object], json.loads(stream_data_raw))
            except (ValueError, TypeError, json.JSONDecodeError) as e:
                logger.warning(
                    i18n.tr(
                        "TikTok stream_data 解析失败，本轮按未开播处理: {type_name}: {e}",
                        type_name=type(e).__name__,
                        e=e,
                    )
                )
                return result
        stream_data = cast(dict[str, object], parsed.get("data", {}) if parsed else {})
        flv_url_list = get_video_quality_url(stream_data, "flv")
        m3u8_url_list = get_video_quality_url(stream_data, "hls")

        if not flv_url_list and not m3u8_url_list:
            return result

        # 先 _pad_list（默认 6，空列表填 6 个 None）防御下面 [quality_index] 越界；pad 不改
        # 档位语义，实际档位由随后的 min 截断决定。必须显式接收返回值：空列表分支返回新列表，
        # 丢弃返回值会让填充失效。
        flv_url_list = cast(list[StreamQuality], _pad_list(flv_url_list))
        m3u8_url_list = cast(list[StreamQuality], _pad_list(m3u8_url_list))
        # pad 出的 [None] * 6 让「列表非空」恒真，`.get("url")` 会因 None 直接 AttributeError
        # 并被装饰器伪装成「未开播」。索引前同时剔除 None 占位项与无 url 的项——后者是线上
        # 真实形态：只下发 hls 路时 flv 侧是一串 {"url": "", ...}，不过滤会带空地址进候选池。
        flv_url_list = [x for x in flv_url_list if x and x.get("url")]
        m3u8_url_list = [x for x in m3u8_url_list if x and x.get("url")]
        video_quality, quality_index = get_quality_index(video_quality)
        # quality_index 保留用户请求档原始值，FLV 与 HLS 各自基于原始索引独立钳制（与抖音
        # 分支的 flv_idx / m3u8_idx 同口径）。若把 FLV 钳制后的值再喂给 HLS：① HLS-only 房间
        # 索引被无条件归零，选任何档都拉最高码率，回采到高档后降级判定恒假，白烧带宽；
        # ② 两侧长度不等时 HLS 被 FLV 长度二次截断，请求低档实拉高档。
        # 回退分支同样以原始索引为基准（fallback_base），避免同一污染在回退路径复现。
        flv_quality_index = min(quality_index, len(flv_url_list) - 1) if flv_url_list else 0
        m3u8_quality_index = min(quality_index, len(m3u8_url_list) - 1) if m3u8_url_list else 0
        flv_dict: StreamQuality | dict[str, str] = flv_url_list[flv_quality_index] if flv_url_list else {"url": ""}
        m3u8_dict: StreamQuality | dict[str, str] = m3u8_url_list[m3u8_quality_index] if m3u8_url_list else {"url": ""}

        check_url = cast(str, m3u8_dict.get("url") or flv_dict.get("url"))
        if not check_url:
            ok = False
        else:
            # SSL 口径与 platform 取值依据同抖音分支（本模块两处探针必须一致）
            ok = await get_response_status(
                url=check_url,
                proxy=proxy_addr,
                http2=False,
                platform="TikTok直播",
                headers=_probe_headers("TikTok直播"),
            )

        if not ok:
            # 回退基准取自原始请求档（fallback_base），两侧各自按自己的长度钳制，
            # 不得再把 FLV 钳过的下标当作 HLS 的基准。
            fallback_base = quality_index + 1 if quality_index < 4 else max(quality_index - 1, 0)
            if flv_url_list:
                flv_dict = flv_url_list[min(fallback_base, len(flv_url_list) - 1)]
            if m3u8_url_list:
                m3u8_dict = m3u8_url_list[min(fallback_base, len(m3u8_url_list) - 1)]

        flv_url = cast(str, flv_dict.get("url", ""))
        m3u8_url = cast(str, m3u8_dict.get("url", ""))
        # 实际选中项的 vbitrate → 画质代码：只有 FLV 时才用 FLV 的码率，FLV 缺失（仅 HLS
        # 源）时以选中的 HLS 项为准——否则 bitrate 恒 0 会把它标成 OD。
        _selected = flv_dict if flv_url else m3u8_dict
        actual_quality = bitrate_to_quality(int(cast(int, _selected.get("vbitrate", 0)) or 0))
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
            # flv_url 字段只放 FLV：若写成 m3u8_url or flv_url，同一个 m3u8 会同时出现在两路
            # 候选，被连续校验两次、以 is_hls=False 身份打假「HLS 失败回退 FLV」；更关键的是
            # 命中「HLS 采集排除平台」/关闭 HLS 采集时，该 m3u8 仍留在 FLV 组被探测选用，与
            # 「HLS 探针一次都不发」的硬语义冲突。「无 FLV 时以 HLS 顶上」由 record_url 承担。
            "flv_url": flv_url,
            "record_url": m3u8_url or flv_url,
        }
    return result


@trace_error_decorator
async def get_kuaishou_stream_url(json_data: dict[str, object], video_quality: str | None = None) -> dict[str, object]:
    # 快手：type==1 且 is_live 为假时原样回传、交由上层判离线；FLV 带 bitrate 字段时按码率表选档
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
        # 同 flv_list，只收 dict 元素；非 list（dumps 过的字符串等）按无候选处理。
        if isinstance(m3u8_list, list):
            m3u8_list = [x for x in m3u8_list if isinstance(x, dict)]
        else:
            m3u8_list = []
        if m3u8_list:
            m3u8_url_list = m3u8_list[::-1]
            idx = min(quality_index, len(m3u8_url_list) - 1)
            result["m3u8_url"] = m3u8_url_list[idx].get("url", "")

        flv_list = k.get("flv_url_list")
        # 平台下发形态不可控——`flv_list` 可能是 dumps 过的字符串、元素也可能是
        # 裸串，那么 `flv_list[0]` 取到的是首字符、`"bitrate" in` 恒假，随后 `.get` 抛 AttributeError
        # 被装饰器吞成「未开播」。先按「只收 dict 元素」归一，非 dict 形态一律按「无候选」跳过。
        if isinstance(flv_list, list):
            flv_list = [x for x in flv_list if isinstance(x, dict)]
        else:
            flv_list = []
        if flv_list:
            # 两种 FLV 候选形态：带 bitrate 字段的按码率排序选档；否则按画质索引从反序列表拣选。
            if "bitrate" in flv_list[0]:
                flv_sorted = sorted(flv_list, key=lambda x: x.get("bitrate", 0), reverse=True)
                quality_str = video_quality.upper() if video_quality else "OD"
                if quality_str.isdigit():
                    # 数字画质必须先按通用索引语义（OD=0,BD=1,UHD=2,HD=3,SD=4,LD=5）解成档位
                    # 代码，再查码率表。QUALITY_MAPPING_BIT 为蓝光子档位插了位，直接按位置索引
                    # 会让同一数字在两表指向不同档（"2" 通用表是 UHD、码率表是 BD30），
                    # 「请求 UHD」实拉最高码率档。
                    code, _ = get_quality_index(quality_str)
                    video_quality = code
                    quality_index_bitrate_value = QUALITY_MAPPING_BIT.get(code, 99999)
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
    # 虎牙：按 ratio（码率上限 kbps）选档，并枚举全部 CDN 线路交给 select_source_url 逐条校验
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

    # 画质 ratio 解析：ratio 即码率上限(kbps)，拼在 FLV/HLS URL 的 query 上选档。
    # 可用档位来源（按优先级）：① sFlvAntiCode 中的 exsphd 档位表（房间实际可拉取的
    # ratio 集合）；② gameLiveInfo.bitRate（房间最高码率）。两者都缺失时不附加 ratio
    # （保持原始防盗链参数原样，即按原画拉流）。
    first_anti = stream_info_list[0].get("sFlvAntiCode") or ""
    quality_list = first_anti.split("&exsphd=")
    bit_rate = game_live_info.get("bitRate") or 0
    try:
        max_ratio = int(bit_rate)
    except TypeError, ValueError:
        max_ratio = 0
    # exsphd 档位表（可能含 264_0/264_500 等，转 int 集合）
    exsphd_ratios: set[int] = set()
    if len(quality_list) > 1:
        for v in cast(list[str], re.findall(r"(?<=264_)\d+", quality_list[1])):
            r = int(v)
            if r > 0:
                exsphd_ratios.add(r)
        if exsphd_ratios:
            max_ratio = max(max_ratio, max(exsphd_ratios))

    actual_quality = video_quality  # OD/BD 默认即请求值
    available_qualities: list[str] | None = None
    ratio_val: str = ""
    # 本轮可用于裁决的 ratio 集合：exsphd 优先，缺失时由 bitRate 推导，两者皆缺为空集
    available_ratios: set[int] = set()

    if video_quality in BD_SUB_TIERS:
        # 细粒度蓝光档位（蓝光30M/20M/8M/4M）：请求固定 ratio，不可用时就近向下降级
        target_ratio = dict(HUYA_FIXED_TIERS)[video_quality]
        # available_ratios 的取值优先级见本函数开头；两者皆缺（max_ratio<=0）时不做本地降级
        # 判断，直接按请求值拉流，交由服务端决定
        if exsphd_ratios:
            available_ratios = exsphd_ratios
        elif max_ratio > 0:
            available_ratios = {r for r in (30000, 20000, 8000, 4000, 2000, 500) if r <= max_ratio}
        else:
            available_ratios = set()
        if not available_ratios or target_ratio in available_ratios:
            ratio_val = str(target_ratio)
            actual_quality = video_quality
        elif any(r < target_ratio for r in available_ratios):
            # 就近向下降级：取可用集合中 < target 的最大 ratio
            chosen = max(r for r in available_ratios if r < target_ratio)
            ratio_val = str(chosen)
            # 档位命名与「能否精确回采」解耦：chosen != target 就告警，表外 ratio 也按
            # 数值就近命名，不回落请求档（那会把降级伪装成按请求录）。
            actual_quality = huya_code_for_ratio(chosen) or video_quality
            logger.warning(
                i18n.tr(
                    "[虎牙直播] 请求档位 {video_quality}(ratio={target_ratio}) 不可用(房间最高码率={max_ratio})，降级为 {actual_quality}(ratio={chosen})",
                    video_quality=code_to_zh(video_quality),
                    target_ratio=target_ratio,
                    max_ratio=max_ratio,
                    actual_quality=code_to_zh(actual_quality),
                    chosen=chosen,
                )
            )
        else:
            # 无任何更低档可用：不附加 ratio 按原画拉流
            actual_quality = "OD"
            logger.warning(
                i18n.tr(
                    "[虎牙直播] 请求档位 {video_quality}(ratio={target_ratio}) 不可用(房间最高码率={max_ratio}，无更低档位)，按原画拉流",
                    video_quality=code_to_zh(video_quality),
                    target_ratio=target_ratio,
                    max_ratio=max_ratio,
                )
            )
        # 按统一档位序输出可用档位（信息展示用）
        # 原实现无条件追加 ["UHD", "LD"]，exsphd 仅含 264_0、max_ratio<=0 的房间
        # 对外声称 ["OD","UHD","LD"]——档位与房间实际可拉取集合不符。现与旧档位分支同一口径：按
        # available_ratios 经 huya_code_for_ratio 贴档位名再按 HUYA_CODE_ORDER 枚举；BD 子档位仍按
        # HUYA_FIXED_TIERS 的「≤ 房间最高码率」口径枚举（子档位不在 exsphd 的 264_ 族里）。
        room_codes = {huya_code_for_ratio(r) for r in available_ratios} - {""}
        bd_tiers = [c for c, r in HUYA_FIXED_TIERS if max_ratio > 0 and r <= max_ratio]
        available_qualities = ["OD"] + bd_tiers + [c for c in HUYA_CODE_ORDER if c in room_codes and c not in bd_tiers]
    elif video_quality and video_quality not in ["OD", "BD"]:
        # ---- 旧档位（超清/高清/标清/流畅）：exsphd 是集合，不是有序序列 ----
        # 原实现把 labels 与 reversed(findall(264_\d+)) 做位置式 zip、不看数值语义，而蓝光
        # 分支把同一串 exsphd 当集合查表。同一字符串两种互斥解释：exsphd 降序或含额外档时方向
        # 整体反转，请求「超清」实拉「蓝光8M」，且 actual_quality 回写成请求值 → 告警静默。
        # 现按数值定位目标档、不可用时就近降级，与 BD 分支同一口径、同一份表。
        # 原条件还挂着 len(quality_list) > 1，房间不带 exsphd 时它恒假、而上一分支只认蓝光子
        # 档位，于是请求 HD/SD/LD 时两个分支都进不去：ratio 为空、actual 仍是请求档、零告警。
        # 现与蓝光分支共用同一条裁决链（exsphd 优先 → bitRate 推导 → 皆缺才不附加 ratio 并告警）。
        if exsphd_ratios:
            available_ratios = exsphd_ratios
        elif max_ratio > 0:
            available_ratios = {r for r in (30000, 20000, 8000, 4000, 2000, 500) if r <= max_ratio}
        target_ratio = HUYA_RATIO_BY_CODE.get(video_quality or "", 0)
        room_codes = {huya_code_for_ratio(r) for r in available_ratios} - {""}
        available_qualities = ["OD", "BD"] + [c for c in HUYA_CODE_ORDER if c in room_codes]
        if not available_ratios or target_ratio <= 0:
            # exsphd 只有 264_0（房间仅原画）/ 请求档无对应 ratio：
            # 按 BD 分支口径不附加 ratio，交由服务端按原画下发，并显式告警说明本地无法裁决
            ratio_val = ""
            actual_quality = "OD"
            logger.warning(
                i18n.tr(
                    "[虎牙直播] 请求档位 {video_quality}(ratio={target_ratio}) 不可用(房间最高码率={max_ratio}，无更低档位)，按原画拉流",
                    video_quality=code_to_zh(video_quality),
                    target_ratio=target_ratio,
                    max_ratio=max_ratio,
                )
            )
        elif target_ratio in available_ratios:
            ratio_val = str(target_ratio)
            actual_quality = video_quality
        else:
            lower = [r for r in available_ratios if r < target_ratio]
            # 无更低档时取集合中最低的一档（最接近请求值），按数值取 min，不依赖出现顺序。
            chosen = max(lower) if lower else min(available_ratios)
            ratio_val = str(chosen)
            actual_quality = huya_code_for_ratio(chosen) or video_quality
            logger.warning(
                i18n.tr(
                    "[虎牙直播] 请求档位 {video_quality}(ratio={target_ratio}) 不可用(房间最高码率={max_ratio})，降级为 {actual_quality}(ratio={chosen})",
                    video_quality=code_to_zh(video_quality),
                    target_ratio=target_ratio,
                    max_ratio=max_ratio,
                    actual_quality=code_to_zh(actual_quality),
                    chosen=chosen,
                )
            )

    # CDN 候选排序：实测 HLS 可靠承载线路为 HS（AL/TX 常因该房间未启用该线路返回 403，
    # 三条线路共享完全相同的防盗链参数——403 是线路未承载推流，随时可能切换）。故枚举全部
    # CDN 候选交给 select_source_url 逐条按可达性校验，首位优先 HS 以最大化「首试即中」；
    # 线路可用性动态变化，必须每轮现拉现校验、不得长期缓存。
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
        # 直接使用房间页内嵌防盗链参数，不重建 anti_code（避免引入未被验证的签名算法）。
        # 统一降为 http：实测 https 返回 403、仅 http 可用（含 HLS/FLV），与校验探针共用
        # 此 scheme，防止「校验 http 可用、录制 https 被拒」。
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
    # 斗鱼：按 DOUYU_RATE_BY_CODE 请求 rate；档位被服务端拒绝/钳制时本地最多回退 2 档重试
    dy = cast(DouyuStreamUrl, cast(object, json_data))
    if not dy.get("is_live"):
        return {"anchor_name": dy.get("anchor_name"), "is_live": False}

    rid = str(dy.get("room_id", ""))
    requested_code = video_quality or "OD"
    rate = DOUYU_RATE_BY_CODE.get(requested_code, "0")
    # 蓝光30M/20M 斗鱼无对应档位：按最高蓝光档（蓝光8M）请求
    if requested_code in ("BD30", "BD20") and rate == "8200":
        logger.info("[斗鱼直播] 斗鱼无蓝光30M/20M档位，按蓝光8M(rate=8200)请求")

    # 降级链：请求档位被限制（如游客态请求原画被拒）时，依次回退更低档位重试（最多 2 次）
    flv_data: dict[str, object] = {}
    flv_data_inner: DouyuFlvData = {}
    # 全序（高→低）：原画(0) → 蓝光8M(8200) → 蓝光4M(4000) → 超清(3) → 高清(2) → 流畅(1)
    order = ["0", *DOUYU_RATE_DESC]
    if rate in order:
        pos = order.index(rate)
        attempt_rates = order[pos : pos + 3]  # 请求档 + 最多 2 个更低档
    else:
        attempt_rates = [rate]
    for idx, attempt in enumerate(attempt_rates):
        flv_data = await get_douyu_stream_data(rid, attempt, cookies=cookies, proxy_addr=proxy_addr)
        err_code = flv_data.get("error", 0)
        flv_data_inner = cast(DouyuFlvData, flv_data.get("data") or {})
        if not err_code and flv_data_inner.get("rtmp_live"):
            if idx > 0:
                actual_code = DOUYU_RATE_TO_CODE.get(attempt, requested_code)
                logger.warning(
                    i18n.tr(
                        "[斗鱼直播] 请求档位 {requested_code}(rate={rate}) 失败，降级为 {actual_code}(rate={attempt}) 拉流成功",
                        requested_code=code_to_zh(requested_code),
                        rate=rate,
                        actual_code=code_to_zh(actual_code),
                        attempt=attempt,
                    )
                )
            break
        err_msg = flv_data.get("msg", "")
        # 可选的 msg 片段按约定在调用方预求值为 err_detail 实参（无 msg 时为空串，输出与旧
        # 实现逐字节一致），模板本身保持常量串：首参若是 ast.BinOp，i18n 门禁看不见、翻译会在
        # 查目录前完成插值。
        err_detail = f", msg={err_msg}" if err_msg else ""
        if idx + 1 < len(attempt_rates):
            logger.warning(
                i18n.tr(
                    "[斗鱼直播] rate={attempt} 拉流失败(error={err_code}{err_detail})，尝试更低档位 rate={next_rate}",
                    attempt=attempt,
                    err_code=err_code,
                    err_detail=err_detail,
                    next_rate=attempt_rates[idx + 1],
                )
            )
        else:
            logger.warning(
                i18n.tr(
                    "[斗鱼直播] rate={attempt} 拉流失败(error={err_code}{err_detail})，已无更低档位",
                    attempt=attempt,
                    err_code=err_code,
                    err_detail=err_detail,
                )
            )
    else:
        # 全部尝试失败：返回 is_live=True 但无流地址（保持既有契约，交由上层告警重试）
        logger.error(
            i18n.tr("[斗鱼直播] 全部档位拉流失败(尝试={attempt_rates})，本轮无可用流地址", attempt_rates=attempt_rates)
        )
        # 本轮**一格地址都没有**时不再谎报开播。上一条告警保留（它是唯一给出
        # 「尝试过哪些 rate」的线索），但 is_live 必须为 False：旧口径下上层把「开播但无地址」当待录
        # 房间，每轮空跑一路 ffmpeg，而 select_source_url 侧只会得到「解析结果无任何流地址」。
        # 与模块头「缺字段即按未开播返回」的既定取舍同向（不伪造 is_live=True 误导调度器）。
        return {"anchor_name": dy.get("anchor_name"), "is_live": False}

    rtmp_url = flv_data_inner.get("rtmp_url", "")
    rtmp_live = flv_data_inner.get("rtmp_live", "")
    # 平台实际下发的 rate（服务端会把不存在的档位就近钳制到更低档，如 8200→4）
    actual_rate = str(flv_data_inner.get("rate", ""))
    actual_quality = DOUYU_RATE_TO_CODE.get(actual_rate, requested_code)

    result: dict[str, object] = {
        "anchor_name": dy.get("anchor_name"),
        "is_live": True,
        "quality": requested_code,
        "actual_quality": actual_quality,
    }
    if rtmp_live:
        flv_url = f"{rtmp_url}/{rtmp_live}"
        result |= {"flv_url": flv_url, "record_url": flv_url}
        # 斗鱼 wsAuth token 对 FLV/HLS 通用：路径 .flv 换 .m3u8 即同 token 的 HLS 播放列表。
        # 游客态 FLV 长连接常被 CDN 约 70 秒掐断（反复分段），HLS 逐段拉取天然免疫；
        # select_source_url 启用 HLS 采集时优先校验并选用 m3u8，不可达时回退 FLV。
        path, _, query = flv_url.partition("?")
        if path.endswith(".flv"):
            result["m3u8_url"] = f"{path[:-4]}.m3u8" + (f"?{query}" if query else "")
    return result


@trace_error_decorator
async def get_yy_stream_url(json_data: dict[str, object]) -> dict[str, object]:
    # YY：avp_info_res.stream_line_addr 只取首条 CDN 线路，未做多线路回退
    y = cast(YyStreamUrl, cast(object, json_data))
    anchor_name = y.get("anchor_name", "")
    result: dict[str, object] = {"anchor_name": anchor_name, "is_live": False}
    avp = y.get("avp_info_res")
    if avp:
        # avp_info_res / stream_line_addr / cdn_info 全是平台下发结构，`or {}` 只兜住
        # 缺失与 None。下发成字符串或 list 时 .get 抛 AttributeError、list(...)[0] 抛 IndexError，
        # 都被装饰器吞成「未开播」。逐层 isinstance 归一，并保留「取首条线路」的既有语义。
        if not isinstance(avp, dict):
            return result
        raw_line = avp.get("stream_line_addr")
        # cast 而非直接赋：TypedDict 下 avp.get(...) 带具体值类型，dict 不变式下不能赋给 dict[str, object]。
        stream_line_addr: dict[str, object] = cast(dict[str, object], raw_line) if isinstance(raw_line, dict) else {}
        if not stream_line_addr:
            return result
        # 仅取首条 CDN 线路、未做多线路回退（YY 单线路可用性假设）；首路失败即无备选。
        # 空映射由上方 not stream_line_addr 早退，此处不会空下标。
        cdn_info = next(iter(stream_line_addr.values()))
        cdn_detail: dict[str, object] = cdn_info if isinstance(cdn_info, dict) else {}
        raw_cdn_info = cdn_detail.get("cdn_info")
        cdn_meta: dict[str, object] = raw_cdn_info if isinstance(raw_cdn_info, dict) else {}
        flv_url = cdn_meta.get("url", "")
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
    # B站：画质名经 video_quality_options 换成 qn 数值请求，再用下发的 current_qn 回采实际档位
    b = cast(BilibiliStreamUrl, cast(object, json_data))
    anchor_name = b.get("anchor_name", "")
    if not b.get("live_status"):
        return {"anchor_name": anchor_name, "is_live": False}

    room_url = b.get("room_url", "")
    video_quality_options = {"OD": "10000", "BD": "400", "UHD": "250", "HD": "150", "SD": "80", "LD": "80"}

    # record_quality 可取蓝光子档位（BD30/BD20/BD8/BD4），这四档不在
    # video_quality_options 里，直接 .get 会落到默认「原画 10000」——比用户选的档更高，
    # 且 is_downgrade("BD4","OD") 为 False，既不按请求录也不告警。选档前先经
    # get_quality_index 折叠子档位（全仓唯一的折叠入口）。
    requested_code = (video_quality or "OD").upper()
    select_code, _ = get_quality_index(requested_code)
    if requested_code not in QUALITY_LEVEL and not requested_code.isdigit():
        logger.warning(
            i18n.tr(
                "[B站直播] 未知画质代码 {video_quality}，按 {select_code} 请求流地址",
                video_quality=video_quality,
                select_code=select_code,
            )
        )

    select_quality = video_quality_options.get(select_code, "10000")
    play_url_data = await get_bilibili_stream_data(
        room_url, qn=select_quality, platform="web", proxy_addr=proxy_addr, cookies=cookies
    )
    if not play_url_data:
        return {"anchor_name": anchor_name, "is_live": False}
    pd = cast(BilibiliPlayData, cast(object, play_url_data))
    # qn → 画质代码反向映射必须显式构造：video_quality_options 里 SD 与 LD 同为 "80"，
    # 推导式 {v: k ...} 后写覆盖前写，实发 qn=80 恒被回采成 LD，用户请求「标清」时会打出
    # 一条不存在的降级告警。一对多时取更高档（SD 优先于 LD），宁可少报也不虚构降级。
    qn_to_code: dict[str, str] = {}
    for code, qn_value in video_quality_options.items():
        known = qn_to_code.get(qn_value)
        if known is None or QUALITY_LEVEL[code] < QUALITY_LEVEL[known]:
            qn_to_code[qn_value] = code
    actual_quality = qn_to_code.get(str(pd.get("current_qn", "")), video_quality)
    accept_qn = pd.get("accept_qn") or []
    # accept_qn 常含本表未登记的值（20000/30000/0 等 4K/帧率档），裸数字经 code_to_zh 只会
    # 原样透出，会打穿 available_qualities 的白名单口径，故只保留能映射到档位代码的项。
    available_qualities = [qn_to_code[str(q)] for q in accept_qn if str(q) in qn_to_code] or None
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
    # 网易CC：stream_list.resolution 按 order 表选档，CDN 只取首个 key（无连通性校验/多 CDN 回退）
    n = cast(NeteaseStreamUrl, cast(object, json_data))
    if not n.get("is_live"):
        return json_data

    m3u8_url = n.get("m3u8_url", "")
    flv_url: str | None = None
    actual_quality: str | None = None
    available_qualities: list[str] | None = None
    stream_list_data = n.get("stream_list")
    if stream_list_data:
        # stream_list / resolution 由平台下发，`or {}` 兜不住「下发成字符串」；
        # 那种形态下 .get 抛 AttributeError 被装饰器吞成「未开播」。逐层 isinstance 归一。
        if not isinstance(stream_list_data, dict):
            return json_data
        raw_resolution = stream_list_data.get("resolution")
        # cast 理由同 get_yy_stream_url：TypedDict 的具体值类型与目标注解在不变式下不可直赋。
        stream_list: dict[str, dict[str, dict[str, str]]] = (
            cast(dict[str, dict[str, dict[str, str]]], raw_resolution) if isinstance(raw_resolution, dict) else {}
        )
        order = ["blueray", "ultra", "high", "standard"]
        sorted_keys = [key for key in order if key in stream_list]
        # 该房间 stream_list 不含任何已知画质键：保持透传上游，不伪造 is_live，交由上层判离线。
        if not sorted_keys:
            return json_data
        video_quality, quality_index = get_quality_index(video_quality)
        # 显式截断，记录实际选中的画质名
        idx = min(quality_index, len(sorted_keys) - 1)
        selected_quality = sorted_keys[idx]
        actual_quality = NETEASE_QUALITY_MAP.get(selected_quality, video_quality)
        available_qualities = [NETEASE_QUALITY_MAP.get(k, k.upper()) for k in sorted_keys]
        raw_entry = stream_list[selected_quality]
        # 档位条目本身也可能是非 dict 形态（平台改版/被截断），
        # `stream_list[selected_quality].get("cdn")` 会抛 AttributeError 被吞成「未开播」。
        # cast 理由同 get_yy_stream_url：档位条目的静态类型是具体 dict，直赋违反 dict 不变式。
        entry: dict[str, object] = cast(dict[str, object], raw_entry) if isinstance(raw_entry, dict) else {}
        raw_cdn = entry.get("cdn")
        flv_url_list: dict[str, str] = raw_cdn if isinstance(raw_cdn, dict) else {}
        # 网易 CDN 取首个 key，未做连通性校验/多 CDN 回退；首路失败会直接影响该画质录制可用性。
        # cdn 映射为空 dict 时 list(keys())[0] 会抛 IndexError、被装饰器吞成未开播；
        # 改为 next(iter(...), None)，空映射时跳过 flv 选择、回退 m3u8（record_url 跟随）。
        selected_cdn = next(iter(flv_url_list), None)
        flv_url = flv_url_list[selected_cdn] if selected_cdn is not None else ""

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


@trace_error_decorator
async def get_stream_url(
    json_data: dict[str, object],
    video_quality: str | None = None,
    url_type: str = "m3u8",
    spec: bool = False,
    hls_extra_key: str | int | None = None,
    flv_extra_key: str | int | None = None,
) -> dict[str, object]:
    # 通用平台入口：play_url_list 按 QUALITY_MAPPING 索引取档，元素两种契约的处置见 get_url。
    # 与其它平台入口一样由 trace_error_decorator 兜底；不得移除该装饰器——否则 KeyError 会
    # 穿透到 main.py 的通用 except 并计入按 host 的熔断样本，与其它 50+ 平台语义不等价。
    g = cast(GenericStreamUrl, cast(object, json_data))
    if not g.get("is_live"):
        return json_data

    play_url_list: list[str | dict[str, str]] = g.get("play_url_list") or []
    if not play_url_list:
        return json_data
    # MI-02：显式接收返回值（原 `_ = _pad_list(...)` 丢弃了空列表分支的填充结果）
    play_url_list = cast(list[str | dict[str, str]], _pad_list(play_url_list))

    video_quality, selected_quality = get_quality_index(video_quality)
    data: dict[str, object] = {"anchor_name": g.get("anchor_name", ""), "is_live": True}

    def get_url(key: str | int | None) -> str:
        # 从 play_url_list 提取流地址；元素有「裸 URL 串」与「画质→地址字典」两种契约。
        # 字典项：缺 key 时不能把整份 dict 当地址返回（下游按 str 判型会静默丢弃，表现为
        # 「解析成功却无任何流地址」）；按 _PLAY_URL_KEY_ORDER 顺序探测、取不到返回 ""，
        # 显式传 key 时用 .get(key, "")——平台字典缺该键是常态，不该抛 KeyError。
        # 裸串：本身就是地址（无子键可选），原样返回；空串照旧，不改下游「无地址」的语义。
        play_url = play_url_list[selected_quality]
        if isinstance(play_url, str):
            return play_url
        if key:
            return str(play_url.get(cast(str, key), "") or "")
        for probe_key in _PLAY_URL_KEY_ORDER:
            value = play_url.get(probe_key, "")
            if value:
                return str(value)
        return ""

    if url_type == "all":
        # spec=True 时优先返回平台原始 m3u8_url/flv_url（未经验证），避免 get_url 解析覆盖掉
        # 已知可用地址；非 spec 则用 play_url_list 解析出的地址。
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
