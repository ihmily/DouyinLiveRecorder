# -*- encoding: utf-8 -*-

# 抖音直播录制工具 - 爬虫模块
#
# 平台爬虫核心：负责 60+ 直播平台的房间信息解析与真实流地址提取。
# 分层（自顶向下）：
#   - 通用工具与凭据缓存：_safe_extract_id / _get_str_response / _loads_dict /
#     _ensure_ttwid / _ensure_kuaishou_did / _ensure_twitch_client_id /
#     get_bilibili_danmaku_info 的 buvid 链——均为「首次获取、进程内缓存、
#     跨线程锁去重」，避免每轮重复请求触发平台风控。
#   - 各平台解析函数：get_<platform>_stream_data / _stream_url，逐一对应一个平台；
#     输入直播间 URL，输出统一结构 {anchor_name, is_live, m3u8_url/flv_url/
#     record_url/play_url_list, ...}。函数名即平台分发表（main.py 按平台名反射调用）。
#   - 签名/加密：抖音 web/enter + HTML 回退（get_douyin_web_stream_data 内）、
#     B站 WBI（_sign_wbi + _MIXIN_KEY_ENC_TAB）、斗鱼 websec 签名（get_token_js）、
#     网易/PopkonTV AES-RSA（get_looklive_secret_data）、LiveMe/嗨秀/咪咕的 JS 签名
#     （execjs 调用 javascript/ 下脚本）。
# 与仓库其它模块的关系：
#   - main.py：按平台名分发调用本模块函数并驱动监控主循环，不直接解析平台接口。
#   - stream_select.py：本模块只负责「取地址」；地址可达性校验与候选排序由
#     select_source_url / _validate_stream_url 负责（含探针退避、同 host 节流、HLS/FLV 优先级）。
#   - stream.py：消费本模块返回的地址，启动 ffmpeg 录制。
#   - platforms/：另有若干平台的独立解析；本文件覆盖主流 60+ 平台。
#   - javascript/（JS_SCRIPT_PATH）：liveme.js / haixiu.js / migu.js 等签名脚本，
#     由 execjs（优先）或 PyExecJS 调用；node 调用失败统一转 ProgramError 交上层处理。
# 设计取舍与坑位：
#   - 全部解析函数为 async，统一经 async_req（src/async_http）发请求，便于代理/超时/
#     重试集中管理；不要在此直接 import httpx 发同步请求（弹幕等少数路径除外）。
#   - 平台接口极易风控：空响应体（200+空 body）、-352、-3001/-3002/-3004 等错误码多为
#     风控或登录态缺失，函数内已尽量带「重试一次再定罪」与回退，调用方需透传 cookies/proxy。
#   - 本文件使用 Python 3.14 的 PEP 758 异常语法 `except A, B:`（不带括号），这是语法特性
#     而非笔误，严禁改成 `except (A, B):`，否则会被误判为需要回溯兼容并破坏 3.14 语义。
#   - 严格类型检查（pyright）在此对动态 JSON 放宽，见下列 report* 指令。

# 爬虫模块大量解析动态 JSON（json.loads 返回 Any、嵌套异构结构），
# 严格模式下的 reportUnknown* 等规则在此类代码上只会产生噪声，
# 故对本文件放宽相关检查，仅保留其余基础类型检查。
# pyright: reportUnknownVariableType=none, reportUnknownParameterType=none, reportUnknownArgumentType=none, reportUnknownMemberType=none, reportUnknownLambdaType=none, reportMissingTypeArgument=none, reportMissingParameterType=none, reportIndexIssue=none, reportOperatorIssue=none, reportImplicitStringConcatenation=none, reportUnnecessaryIsInstance=none, reportUnusedCallResult=none, reportArgumentType=none, reportReturnType=none

import asyncio
import hashlib
import json
import random
import re
import subprocess
import threading
import time
import urllib.parse
import uuid
from operator import itemgetter
from typing import cast

import httpx

# 优先使用 exejs（PyExecJS 的活跃维护继任者），未安装时回退到 PyExecJS
try:
    import exejs as execjs

    ProgramError = execjs.ExejsProgramError
except ImportError:
    import execjs  # type: ignore[no-redef]
    from execjs import ProgramError  # type: ignore[no-redef]

from . import JS_SCRIPT_PATH, http_config, utils
from .async_http import async_req
from .cookie_cache import fetch_cookies as _cache_fetch_cookies
from .logger import logger, script_path
from .room import UnsupportedUrlError, get_sec_user_id, get_unique_id, is_user_homepage_url
from .ttwid import get_ttwid as _shared_get_ttwid
from .utils import generate_random_string, trace_error_decorator, trace_error_decorator_or_none

OptionalStr = str | None
OptionalDict = dict[str, str] | None
# 花椒接口返回的异构 dict（含 is_live 布尔值），值类型需覆盖 str | bool
OptionalStreamDict = dict[str, str | bool] | None

# 缓存自动获取的 ttwid，避免重复请求主页（已委托给共享 ttwid.py 模块，保留变量兼容旧引用）
_cached_ttwid: str = ""

# 模块级预编译正则：原先在解析函数内每次调用都 re.compile（m3u8 带宽提取、抖音 HEVC FLV
# 提取），平台解析每房间每轮多次触发。预编译后省去重复编译，匹配语义不变。
_BANDWIDTH_PATTERN = re.compile(r"BANDWIDTH=(\d+)")
_DOUYIN_HEVC_FLV_PATTERN = re.compile(r'(https?://[^\s"\']*stream-\d{10,}(?!_[a-z0-9]+)\.flv(?:[^"\']|\\u0026)+)')


def _safe_extract_id(url: str, default: str = "") -> str:
    # 从 URL 中安全提取路径 ID（避免 rsplit 越界）
    # 无 "/" 的非法 URL 返回 default（约定为 ""），调用方据此识别房间标识缺失、转主页解析兜底，
    # 故 default 必须可区分「未取到」与「取到空串」两种语义。
    path = url.split("?")[0].rstrip("/")
    parts = path.rsplit("/", maxsplit=1)
    return parts[1] if len(parts) > 1 else default


async def _ensure_ttwid(proxy_addr: OptionalStr = None) -> str:
    # 委托给共享 ttwid.py 模块（带 threading.Lock 跨线程去重），
    # 解决多线程并发时重复拉取 ttwid 触发风控的问题
    global _cached_ttwid
    result = await _shared_get_ttwid(proxy_addr)
    _cached_ttwid = result  # 同步本地缓存，兼容可能的外部引用
    return result


# 各平台自动获取凭据的缓存，避免每次请求都重新获取
_cached_kuaishou_did: str = ""
_cached_twitch_client_id: str = ""
# 凭据获取的互斥锁 + 二次检查：多房间线程并发首轮请求时只拉取一次，
# 避免重复打平台接口（触发风控）与凭据互相覆盖
_kuaishou_did_lock = threading.Lock()
_twitch_client_id_lock = threading.Lock()


async def _ensure_kuaishou_did(proxy_addr: OptionalStr = None) -> str:
    # 自动获取快手访客 did/didv（访问快手直播主页时服务器下发），替代硬编码过期凭据。
    # 改经统一 cookie 缓存（src/cookie_cache.fetch_cookies）从快手主页动态获取，
    # 同网址下的其他模块直接复用，避免重复请求触发风控。
    global _cached_kuaishou_did
    if _cached_kuaishou_did:
        return _cached_kuaishou_did
    with _kuaishou_did_lock:
        if _cached_kuaishou_did:
            return _cached_kuaishou_did
        try:
            cookies_dict = await _cache_fetch_cookies(
                url="https://live.kuaishou.com/",
                proxy_addr=proxy_addr,
                headers={
                    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36"
                },
                timeout=10,
                fetcher=async_req,  # 传入本模块 async_req，使单测对 src.spider.async_req 打桩仍生效
            )
            if isinstance(cookies_dict, dict):
                did = cookies_dict.get("did", "")
                didv = cookies_dict.get("didv", "")
                if did:
                    _cached_kuaishou_did = f"did={did}; didv={didv}" if didv else f"did={did}"
                    logger.debug("自动获取快手 did 成功")
        except Exception as e:
            logger.warning(f"自动获取快手 did 失败: {e}")
    return _cached_kuaishou_did


async def _ensure_twitch_client_id(proxy_addr: OptionalStr = None) -> str:
    # 从 Twitch 主页动态提取 Web 端公开 Client-Id（替代硬编码值，避免后续变更失效）
    # 该 Client-Id 是 Twitch 网页客户端使用的公共标识，非用户私人凭据，
    # 但仍改为动态提取以避免 Twitch 更换后导致功能失效
    global _cached_twitch_client_id
    if _cached_twitch_client_id:
        return _cached_twitch_client_id
    with _twitch_client_id_lock:
        if _cached_twitch_client_id:
            return _cached_twitch_client_id
        fallback_ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:148.0) Gecko/20100101 Firefox/148.0"
        try:
            html = await async_req(
                url="https://www.twitch.tv/",
                proxy_addr=proxy_addr,
                headers={"User-Agent": fallback_ua, "Accept-Language": "en-US"},
                timeout=10,
            )
            html = _get_str_response(html)
            # Twitch 主页 HTML 中通过 "Client-ID" 字符串内嵌公开客户端标识
            match = re.search(r'"Client-ID"\s*[:=]\s*"([a-z0-9]{20,})"', html)
            if match:
                _cached_twitch_client_id = match.group(1)
                logger.debug("自动获取 Twitch Client-Id 成功")
        except Exception as e:
            logger.warning(f"自动获取 Twitch Client-Id 失败: {e}")
    return _cached_twitch_client_id


def _generate_twitch_play_session_id() -> str:
    # 动态生成 Twitch 播放会话 ID（替代硬编码的过期会话 ID）
    # 原硬编码值为固定 32 位十六进制字符串，实际应为每次会话独立生成
    return generate_random_string(32).lower()


def _get_str_response(resp: object) -> str:
    # 安全地将 async_req 的响应转换为字符串格式
    # async_req 成功返回 str、失败/异常返回 (str, status) 元组或 None；统一收敛为 str，
    # 失败返回 ""，使下游 _loads_dict 与「空响应即风控」判据无需区分响应类型。
    if isinstance(resp, str):
        return resp
    elif isinstance(resp, tuple) and len(resp) > 0 and isinstance(resp[0], str):
        return resp[0]
    return ""


def _loads_dict(text: object) -> dict[str, object]:
    # 将 async_req 文本响应安全解析为 dict[str, object]，消除 json.loads 的 Any 传播
    # 空串/非 JSON/非 dict 一律回 {} 而非 None，保证调用方始终能 .get() 而不必先判空，
    # 否则上游取 stream_url/origin 时会因 None 触发 AttributeError 崩主循环。
    s = _get_str_response(text)
    if not s:
        return {}
    parsed = cast(object, json.loads(s))
    return parsed if isinstance(parsed, dict) else {}


def get_params(url: str, params: str) -> OptionalStr:
    # 从URL中提取指定参数的值
    # 参数缺失时返回 None（而非空串），调用方常靠 None 区分「未提供」与「值为空」，
    # 若改返回 "" 会与「参数为空字符串」语义混淆、导致直播类型/房间号误判。
    parsed_url = urllib.parse.urlparse(url)
    query_params = urllib.parse.parse_qs(parsed_url.query)

    if params in query_params:
        return query_params[params][0]
    return None


def extract_douyin_hevc_flv_url(html: str) -> OptionalStr:
    # 从抖音页面 HTML 中提取 HEVC/H265 FLV 流地址
    # 跳过 only_audio=1 的纯音频 FLV（无画面不可录）；整页未匹配到有效视频流时返回 None，
    # 调用方据此保留 ORIGIN 的 hls/flv 而不注入 hevc_flv_url，避免把音频流当视频源录制。
    for match in _DOUYIN_HEVC_FLV_PATTERN.findall(html):
        clean_url = match.replace("\\u0026", "&").rstrip("\\").strip()
        parsed = urllib.parse.urlparse(clean_url)
        query = urllib.parse.parse_qs(parsed.query)
        if query.get("only_audio", ["0"])[0] == "1":
            continue
        # 必须补 codec=h265 标记：下游 _is_h265() 与 main.py 的 h265 兜底判定只认 URL 上的
        # codec 查询参数（对齐本文件给 ORIGIN 线路拼 &codec=<VCodec> 的既有做法），缺失会让
        # HEVC 源伪装成普通 FLV 通过全部检查、直接进 -c copy。已带该参数时原样返回，避免重复拼接。
        if query.get("codec"):
            return cast(str, clean_url)
        separator = "&" if parsed.query else "?"
        return cast(str, f"{clean_url}{separator}codec=h265")
    return None


async def get_play_url_list(
    m3u8: str, proxy: OptionalStr = None, header: OptionalDict = None, abroad: bool = False
) -> list[str]:
    # 获取M3U8播放列表中的所有清晰度URL并按带宽排序
    # 响应非字符串（请求失败/被风控）直接回 []，调用方据此判定无多清晰度源、回退单地址；
    # 仅当带宽标记数量与 URL 数量一致才按带宽降序，否则保留 m3u8 原始顺序，避免错位映射选错画质。
    resp = await async_req(url=m3u8, proxy_addr=proxy, headers=header, abroad=abroad)
    if not isinstance(resp, str):
        return []
    play_url_list: list[str] = []
    for i in resp.split("\n"):
        if i.startswith("https://"):
            play_url_list.append(i.strip())
    if not play_url_list:
        for i in resp.split("\n"):
            if i.strip().endswith("m3u8"):
                play_url_list.append(i.strip())
    bandwidth_pattern = _BANDWIDTH_PATTERN
    bandwidth_list = cast(list[str], bandwidth_pattern.findall(resp))
    if bandwidth_list and len(bandwidth_list) == len(play_url_list):
        url_to_bandwidth = {url: int(bandwidth) for bandwidth, url in zip(bandwidth_list, play_url_list)}
        play_url_list = sorted(play_url_list, key=lambda url: url_to_bandwidth[url], reverse=True)
    return play_url_list


def _extract_room_data_from_html(html_str: str) -> dict[str, object]:
    # 从抖音直播间HTML页面提取房间数据（作为API失败时的回退方案）
    # 这是 web/enter 接口彻底失败后的兜底：HTML 内联了状态 JSON，但其结构随页面改版极不稳定，
    # 一旦正则失配就落到末尾 except 返回 {}，上游会据此判定「未开播/房间不存在」而反复重试。
    if not html_str:
        return {}
    try:
        # 两种正则分别匹配不同版本的页面内联根结构（state / common），无第三个兜底；
        # 正则强依赖抖音页面模板，任一处字段改名即整体失效、静默返回 {}。
        match_json_str = re.search(r'(\{\\"state\\":.*?)]\\n"]\)', html_str)
        if not match_json_str:
            match_json_str = re.search(r'(\{\\"common\\":.*?)]\\n"]\)</script><div hidden', html_str)
        if not match_json_str:
            return {}
        json_str = match_json_str.group(1)
        # 内联 JSON 是双重转义字符串：先去掉一层反斜杠还原引号，再把 u0026 还原为
        # &（URL 参数分隔符），否则后续按 JSON 解析与按 & 拆参数都会失败。
        cleaned_string = json_str.replace("\\", "").replace(r"u0026", r"&")
        room_store_match = re.search('"roomStore":(.*?),"linkmicStore"', cleaned_string, re.DOTALL)
        if not room_store_match:
            return {}
        room_store = room_store_match.group(1)
        anchor_name_match = re.search('"nickname":"(.*?)","avatar_thumb', room_store, re.DOTALL)
        anchor_name = anchor_name_match.group(1) if anchor_name_match else ""
        # 截到 "has_commerce_goods" 字段前再用固定 3 个右花括号收尾：内联 JSON 被页面截断，
        # 用固定标记切断后再手动补齐括号平衡结构；若结构层级变化会导致解析抛错而落到 except。
        room_store = room_store.split(',"has_commerce_goods"')[0] + "}}}"
        room_info = cast(dict[str, object], _loads_dict(room_store).get("roomInfo") or {})
        json_data = cast(dict[str, object], room_info.get("room") or {})
        json_data["anchor_name"] = anchor_name
        # status==4 表示非开播态（回放/下播）；此处提前返回不含 stream_url 的结果，
        # 上游据此判定未开播，不再尝试取流。
        if json_data.get("status") == 4:
            return json_data
        stream_url_field = cast(dict[str, object], json_data.get("stream_url") or {})
        stream_orientation = stream_url_field.get("stream_orientation")
        origin_url_list: dict[str, object] | None = None
        # 同一页面存在多段内联脚本（横屏/竖屏各一段），按 stream_orientation 选对应段；
        # findall 取不到时回退到整页清洗串里抠 "origin":{"main":... 片段（第二兜底）。
        match_json_str2 = cast(list[str], re.findall(r'"(\{\\"common\\":.*?)"]\)</script><script nonce=', html_str))
        if match_json_str2:
            if stream_orientation == 1:
                json_str2 = match_json_str2[0]
            else:
                json_str2 = match_json_str2[1] if len(match_json_str2) > 1 else match_json_str2[0]
            json_data2 = _loads_dict(
                json_str2.replace("\\", "").replace('"{', "{").replace('}"', "}").replace("u0026", "&")
            )
            data2 = cast(dict[str, object], json_data2.get("data") or {})
            if "origin" in data2:
                origin_url_list = cast(dict[str, object], cast(dict[str, object], data2["origin"]).get("main") or {})
        else:
            html_str_clean = html_str.replace("\\", "").replace("u0026", "&")
            match_json_str3 = re.search('"origin":\\{"main":(.*?),"dash"', html_str_clean, re.DOTALL)
            if match_json_str3:
                # 这里只补 1 个右花括号：该片段在 "dash" 前被切断，结构比上面更浅一层。
                origin_url_list = _loads_dict(match_json_str3.group(1) + "}")
        if origin_url_list:
            sdk_params_field = cast(dict[str, object], origin_url_list.get("sdk_params") or {})
            vcodec = sdk_params_field.get("VCodec")
            origin_hls_codec = vcodec if isinstance(vcodec, str) else ""
            hls_v = origin_url_list.get("hls", "")
            flv_v = origin_url_list.get("flv", "")
            hls_s = hls_v if isinstance(hls_v, str) else ""
            flv_s = flv_v if isinstance(flv_v, str) else ""
            # 把 VCodec 拼进地址的 &codec= 查询参数，供后续 h265 判定与 ffmpeg 选流使用；
            # 再把 ORIGIN 线路合并到已有的 hls_pull_url_map / flv_pull_url 之前，优先于其它线路。
            origin_m3u8 = {"ORIGIN": hls_s + "&codec=" + origin_hls_codec}
            origin_flv = {"ORIGIN": flv_s + "&codec=" + origin_hls_codec}
            hls_pull_url_map = cast(dict[str, object], stream_url_field.get("hls_pull_url_map") or {})
            flv_pull_url = cast(dict[str, object], stream_url_field.get("flv_pull_url") or {})
            stream_url_field["hls_pull_url_map"] = {**origin_m3u8, **hls_pull_url_map}
            stream_url_field["flv_pull_url"] = {**origin_flv, **flv_pull_url}
            hevc_flv_url = extract_douyin_hevc_flv_url(html_str)
            if hevc_flv_url:
                stream_url_field["hevc_flv_url"] = hevc_flv_url
        return json_data
    # 整段兜底逻辑用裸 except 吞掉一切异常并回 {}：失败原因（页面改版/网络/解析错误）全部丢失，
    # 上游只能看到空结果、按「未开播」处理，无法区分「真离线」与「解析挂了」。
    except Exception:
        return {}


async def get_douyin_web_stream_data(
    url: str, proxy_addr: OptionalStr = None, cookies: OptionalStr = None
) -> dict[str, object]:
    # 通过抖音网页端API获取直播数据
    # 注意：cookie 需由调用方通过 cookies 参数传入有效值，硬编码的过期 cookie 必然触发风控
    chrome_ua = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36"
    )
    headers = {
        "cookie": "",
        "referer": url,
        "user-agent": chrome_ua,
        "accept": "application/json, text/plain, */*",
        "accept-language": "zh-CN,zh;q=0.8,zh-TW;q=0.7,zh-HK;q=0.5,en-US;q=0.3,en;q=0.2",
        "sec-ch-ua": '"Google Chrome";v="141", "Chromium";v="141", "Not_A Brand";v="8"',
        "sec-ch-ua-platform": '"Windows"',
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin",
        "x-requested-with": "XMLHttpRequest",
    }
    if cookies:
        headers["cookie"] = cookies
    else:
        # 未传入 cookie 时退化到游客态：用 _ensure_ttwid 取一个仅含 ttwid 的设备访客标识。
        # 仅 ttwid 也能拉到流，但风控率显著高于带登录 cookie，故调用方应优先传真实 cookie。
        headers["cookie"] = await _ensure_ttwid(proxy_addr)

    try:
        # web_rid 取 URL 末段即可，无需额外解析请求：web/enter 同时接受数字房间号
        # （745964462470）与抖音号（yall1102），且传入抖音号不会发生重定向
        # （数字 id 才可能被 30x 跳转），故直接取末段即可。
        web_rid = url.split("?")[0].rstrip("/").split("live.douyin.com/")[-1]
        params = {
            "aid": "6383",
            "app_name": "douyin_web",
            "live_id": "1",
            "device_platform": "web",
            "language": "zh-CN",
            "browser_language": "zh-CN",
            "browser_platform": "Win32",
            "browser_name": "Chrome",
            "browser_version": "141.0.0.0",
            "web_rid": web_rid,
            # msToken 此处留空：web/enter 端点不强制校验 msToken（app 端点才强依赖），
            # 留空可避免引入需额外签名的参数；风控主要看 ttwid/cookie 而非 msToken。
            "msToken": "",
        }

        api = f"https://live.douyin.com/webcast/room/web/enter/?{urllib.parse.urlencode(params)}"

        async def _try_web_api() -> dict[str, object]:
            # 单次 web/enter API 尝试；失败（空响应 / 非 0 状态码）抛异常，由外层决定是否重试或回退。
            json_str = _get_str_response(await async_req(url=api, proxy_addr=proxy_addr, headers=headers))
            # 抖音风控时不返回 4xx，而是 200 + 空响应体，故不能只靠状态码判断成败，
            # 必须显式判空再抛「疑似风控」，交外层决定重试或回退 HTML。
            if not json_str:
                raise Exception("empty response from API (possible risk control)")
            parsed = _loads_dict(json_str)
            status_code = parsed.get("status_code")
            if status_code is not None and int(cast(str, status_code)) != 0:
                status_msg = parsed.get("status_msg", "unknown error")
                raise Exception(f"API returned status_code={status_code}, msg={status_msg}")
            json_data = cast(dict[str, object], parsed.get("data") or {})
            inner_list = json_data.get("data")
            if not inner_list:
                raise Exception(f"{url} VR live is not supported or room not found")
            room_data = cast(dict[str, object], cast(list[object], inner_list)[0])
            user_info = cast(dict[str, object], json_data.get("user") or {})
            room_data["anchor_name"] = user_info.get("nickname")
            return room_data

        room_data: dict[str, object] | None = None
        api_error: Exception | None = None
        # 抖音 web/enter 接口偶发返回 10002 等软拒绝（多为瞬时风控），先静默重试一次，
        # 成功则直接返回、跳过 HTML 回退（省去一次约 1MB 的兜底 HTML 抓取）；
        # 两次都失败才记 WARNING 并回退 HTML 抓取。
        for attempt in range(2):
            try:
                room_data = await _try_web_api()
                break
            except Exception as e:
                api_error = e
                if attempt == 0:
                    await asyncio.sleep(0.5)  # 给瞬时风控一个缓冲窗口
                    continue
                logger.warning(f"Douyin web API failed: {api_error}, falling back to HTML scraping")
                try:
                    html_str = _get_str_response(await async_req(url=url, proxy_addr=proxy_addr, headers=headers))
                    room_data = _extract_room_data_from_html(html_str)
                    if not room_data:
                        raise Exception(f"HTML scraping also failed after API error: {api_error}")
                    logger.debug("HTML scraping fallback succeeded")
                except Exception as e2:
                    raise Exception(f"Douyin web data fetch error (API: {api_error}) (HTML fallback: {e2}).")
        if room_data is None:
            raise Exception(f"Douyin web data fetch error: {api_error}")

        # status==2 才是真正开播；其它值（如 4）视为未开播，跳过取流、返回无 stream 的 room_data。
        if room_data.get("status") == 2:
            if "stream_url" not in room_data:
                raise RuntimeError(
                    "The live streaming type or gameplay is not supported on the computer side yet, please use the "
                    "app to share the link for recording."
                )
            stream_url = cast(dict[str, object], room_data["stream_url"])
            # web/enter 的响应里不含 HEVC 的 flv 地址，只能再从直播间 HTML 内联数据里抠，
            # 故即便 API 已给流，仍要再抓一次页面专门取 hevc_flv_url。
            html_str = _get_str_response(await async_req(url=url, proxy_addr=proxy_addr, headers=headers))
            hevc_flv_url = extract_douyin_hevc_flv_url(html_str)
            live_core_sdk_data = cast(dict[str, object], stream_url.get("live_core_sdk_data") or {})
            pull_datas = cast(dict[str, object], stream_url.get("pull_datas") or {})
            if live_core_sdk_data:
                json_str = ""
                if pull_datas:
                    # 遍历 pull_datas 各线路，优先挑出 HEVC(h265) 候选；拿不到再退回第一条有效候选。
                    # 用 "origin" 是否在解析后的 data 中存在作为该线路有效的判据；单条解析失败（PEP 758 多异常）
                    # 仅跳过该条、不中断整体遍历。
                    hevc_candidate = ""
                    first_candidate = ""
                    for value in pull_datas.values():
                        value_dict = cast(dict[str, object], value) if isinstance(value, dict) else {}
                        candidate_raw = value_dict.get("stream_data") or ""
                        candidate = candidate_raw if isinstance(candidate_raw, str) else ""
                        if not candidate:
                            continue
                        try:
                            cand_data = cast(dict[str, object], _loads_dict(candidate).get("data") or {})
                        except json.JSONDecodeError, TypeError:
                            continue
                        if "origin" not in cand_data:
                            continue
                        if not first_candidate:
                            first_candidate = candidate
                        try:
                            cand_main = cast(dict[str, object], cast(dict[str, object], cand_data["origin"])["main"])
                            cand_sdk_raw = cand_main.get("sdk_params", "{}")
                            codec_val = _loads_dict(cand_sdk_raw if isinstance(cand_sdk_raw, str) else "{}").get(
                                "VCodec", ""
                            )
                            codec = codec_val if isinstance(codec_val, str) else ""
                        except json.JSONDecodeError, KeyError, TypeError:
                            codec = ""
                        if "h265" in codec.lower() or "hevc" in codec.lower():
                            hevc_candidate = candidate
                            break
                    json_str = hevc_candidate or first_candidate
                elif "pull_data" in live_core_sdk_data:
                    pull_data = live_core_sdk_data["pull_data"]
                    if isinstance(pull_data, dict):
                        sd = cast(dict[str, object], pull_data).get("stream_data", "")
                        json_str = sd if isinstance(sd, str) else ""
                    else:
                        json_str = ""
                if json_str:
                    parsed_data = cast(dict[str, object], _loads_dict(json_str).get("data") or {})
                    if "origin" in parsed_data:
                        origin_url_list = cast(
                            dict[str, object], cast(dict[str, object], parsed_data["origin"])["main"]
                        )
                        sdk_raw = origin_url_list.get("sdk_params", "")
                        sdk_params = _loads_dict(sdk_raw if isinstance(sdk_raw, str) else "")
                        vcodec = sdk_params.get("VCodec")
                        origin_hls_codec = vcodec if isinstance(vcodec, str) else ""

                        hls_v = origin_url_list.get("hls", "")
                        flv_v = origin_url_list.get("flv", "")
                        hls_s = hls_v if isinstance(hls_v, str) else ""
                        flv_s = flv_v if isinstance(flv_v, str) else ""
                        origin_m3u8 = {"ORIGIN": hls_s + "&codec=" + origin_hls_codec}
                        origin_flv = {"ORIGIN": flv_s + "&codec=" + origin_hls_codec}
                        hls_pull_url_map = cast(dict[str, object], stream_url.get("hls_pull_url_map") or {})
                        flv_pull_url = cast(dict[str, object], stream_url.get("flv_pull_url") or {})
                        stream_url["hls_pull_url_map"] = {**origin_m3u8, **hls_pull_url_map}
                        stream_url["flv_pull_url"] = {**origin_flv, **flv_pull_url}
                    if hevc_flv_url:
                        stream_url["hevc_flv_url"] = hevc_flv_url
    # 任何解析异常都吞掉并回 {"anchor_name": ""}：不让单房间解析崩溃主循环，
    # 但副作用是「解析失败」与「未开播」被上游同样视作「需重试的不可录」，可能空转。
    except Exception as e:
        tb_lineno = e.__traceback__.tb_lineno if e.__traceback__ else 0
        logger.error(f"Error message: {e} Error line: {tb_lineno}")
        room_data = cast(dict[str, object], {"anchor_name": ""})
    return room_data


@trace_error_decorator
async def get_douyin_app_stream_data(
    url: str, proxy_addr: OptionalStr = None, cookies: OptionalStr = None
) -> dict[str, object]:
    # 通过抖音APP端接口获取直播数据（备用方案）
    # 注意：cookie 需由调用方通过 cookies 参数传入有效值，硬编码的过期 cookie 必然触发风控
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
        + "Chrome/141.0.0.0 Safari/537.36 Edg/141.0.0.0",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-CN,zh;q=0.8,zh-TW;q=0.7,zh-HK;q=0.5,en-US;q=0.3,en;q=0.2",
        "Referer": url,
        "Cookie": "",
    }
    if cookies:
        headers["Cookie"] = cookies
    else:
        headers["Cookie"] = await _ensure_ttwid(proxy_addr)

    async def get_app_data(room_id: str, sec_uid: str) -> dict[str, object]:
        app_params = {
            # verifyFp 留空：app reflow 接口不强制校验指纹，留空省去一次签名计算。
            "verifyFp": "",
            "type_id": "0",
            "live_id": "1",
            "room_id": room_id,
            "sec_user_id": sec_uid,
            # version_code / app_id 是模拟抖音 APP 客户端的固定标识，必须与接口预期一致，
            # 否则返回 status_code 非零（风控/参数错误）；不要随意改版本号。
            "version_code": "141.0.0.0",
            "app_id": "1128",
        }
        # 走 amemv.com 的 reflow/info 端点（APP 侧直播间接口），与 web/enter 不同源、参数体系也不同。
        api2 = f"https://webcast.amemv.com/webcast/room/reflow/info/?{urllib.parse.urlencode(app_params)}"
        try:
            json_str2 = _get_str_response(await async_req(url=api2, proxy_addr=proxy_addr, headers=headers))
            # 与 web 端一致：抖音风控返回 200+空 body 而非 4xx，必须显式判空再定罪。
            if not json_str2:
                raise Exception("empty response from API (possible risk control)")
            parsed2 = _loads_dict(json_str2)
            status_code2 = parsed2.get("status_code")
            if status_code2 is not None and int(cast(str, status_code2)) != 0:
                status_msg2 = parsed2.get("status_msg", "unknown error")
                raise Exception(f"API returned status_code={status_code2}, msg={status_msg2}")
            json_data2 = cast(dict[str, object], parsed2.get("data") or {})
            room_field = json_data2.get("room")
            if not room_field:
                raise Exception(f"{url} VR live is not supported or room not found")
            room_data2 = cast(dict[str, object], room_field)
            owner = cast(dict[str, object], room_data2.get("owner") or {})
            room_data2["anchor_name"] = owner.get("nickname")
            return room_data2
        except Exception as e:
            raise Exception(f"Douyin app data fetch error, because {e}.")

    async def resolve_from_homepage() -> dict[str, object]:
        # 主播主页链接：先解析出抖音号，再按直播间地址取流。
        # 这里直调 get_douyin_web_stream_data（网页端 API 优先、内置 HTML 兜底），
        # 而非旧版 HTML 优先抓取路径（需下载约 1MB 页面且正则易随改版失效），可省去一次大流量请求。
        # 注意必须透传 proxy_addr / cookies，否则代理与 Cookie 配置会在此路径静默丢失。
        unique_id = await get_unique_id(url, proxy_addr=proxy_addr)
        return await get_douyin_web_stream_data(f"https://live.douyin.com/{unique_id}", proxy_addr, cookies)

    try:
        web_rid = url.split("?")[0].split("live.douyin.com/")
        if len(web_rid) > 1:
            return await get_douyin_web_stream_data(url, proxy_addr, cookies)
        elif is_user_homepage_url(url):
            # 网页端主页链接（www.douyin.com/user/<sec_uid>）不会重定向到 reflow 直播间页，
            # 调 get_sec_user_id 必然抛 UnsupportedUrlError 且白下载一次主页 HTML，直接跳过。
            return await resolve_from_homepage()
        else:
            try:
                data = await get_sec_user_id(url, proxy_addr=proxy_addr)
                if data is None:
                    raise RuntimeError("Failed to get sec_user_id")
                _room_id, _sec_uid = data
                room_data = await get_app_data(_room_id, _sec_uid)
            except UnsupportedUrlError:
                return await resolve_from_homepage()

        if room_data.get("status") == 2:
            if "stream_url" not in room_data:
                raise RuntimeError(
                    "The live streaming type or gameplay is not supported on the computer side yet, please use the "
                    + "app to share the link for recording."
                )
            stream_url = cast(dict[str, object], room_data["stream_url"])
            live_core_sdk_data = cast(dict[str, object], stream_url.get("live_core_sdk_data") or {})
            pull_datas = cast(dict[str, object], stream_url.get("pull_datas") or {})
            if live_core_sdk_data:
                if pull_datas:
                    key = list(pull_datas.keys())[0]
                    first_pull = cast(dict[str, object], pull_datas[key])
                    sd0 = first_pull.get("stream_data", "")
                    json_str = sd0 if isinstance(sd0, str) else ""
                else:
                    pull_data = live_core_sdk_data.get("pull_data", {})
                    if isinstance(pull_data, dict):
                        sd0 = cast(dict[str, object], pull_data).get("stream_data", "")
                        json_str = sd0 if isinstance(sd0, str) else ""
                    else:
                        json_str = ""
                if json_str:
                    parsed_data = cast(dict[str, object], _loads_dict(json_str).get("data") or {})
                    if "origin" in parsed_data:
                        pull_data2 = cast(dict[str, object], live_core_sdk_data.get("pull_data") or {})
                        stream_data_raw = pull_data2.get("stream_data", "")
                        stream_data = stream_data_raw if isinstance(stream_data_raw, str) else ""
                        if stream_data:
                            try:
                                sd_data = cast(dict[str, object], _loads_dict(stream_data).get("data") or {})
                                sd_origin = cast(dict[str, object], sd_data.get("origin") or {})
                                origin_data = cast(dict[str, object], sd_origin.get("main") or {})
                            except json.JSONDecodeError, TypeError:
                                origin_data = {}
                            sdk_params_raw = origin_data.get("sdk_params", "{}")
                            sdk_params = _loads_dict(sdk_params_raw if isinstance(sdk_params_raw, str) else "{}")
                            vcodec = sdk_params.get("VCodec")
                            origin_hls_codec = vcodec if isinstance(vcodec, str) else ""

                            origin_url_list = origin_data
                            hls_v = origin_url_list.get("hls")
                            flv_v = origin_url_list.get("flv")
                            if hls_v and flv_v:
                                hls_s = hls_v if isinstance(hls_v, str) else ""
                                flv_s = flv_v if isinstance(flv_v, str) else ""
                                origin_m3u8 = {"ORIGIN": hls_s + "&codec=" + origin_hls_codec}
                                origin_flv = {"ORIGIN": flv_s + "&codec=" + origin_hls_codec}
                                hls_pull_url_map = cast(dict[str, object], stream_url.get("hls_pull_url_map") or {})
                                flv_pull_url = cast(dict[str, object], stream_url.get("flv_pull_url") or {})
                                stream_url["hls_pull_url_map"] = {**origin_m3u8, **hls_pull_url_map}
                                stream_url["flv_pull_url"] = {**origin_flv, **flv_pull_url}
    # 任何解析异常都吞掉并回 {"anchor_name": ""}：不让单房间解析崩溃主循环，
    # 但副作用是「解析失败」与「未开播」被上游同样视作「需重试的不可录」，可能空转。
    except Exception as e:
        tb_lineno = e.__traceback__.tb_lineno if e.__traceback__ else 0
        logger.error(f"Error message: {e} Error line: {tb_lineno}")
        room_data = cast(dict[str, object], {"anchor_name": ""})
    return room_data


@trace_error_decorator
async def get_tiktok_stream_data(
    url: str, proxy_addr: OptionalStr = None, cookies: OptionalStr = None
) -> dict[str, object] | None:
    # 获取 TikTok 直播数据。TikTok 的房间状态写在 <script id="SIGI_STATE"> 的 SIGI_STATE 里，
    # 必须整页 HTML 抓回再正则抠 JSON，不能用接口直取。下面默认内置一个游客 cookie，
    # 仅用于绕过「未登录即拦截」，有 cookies 参数时以传入为准。
    headers = {
        "referer": "https://www.tiktok.com/",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
        + "Chrome/141.0.0.0 Safari/537.36",
        "cookie": cookies
        or "1%7Cz7FKki38aKyy7i-BC9rEDwcrVvjcLcFEL6QIeqldoy4%7C1761302831%7C6c1461e9f1f980cbe0404c5190"
        + "5177d5d53bbd822e1bf66128887d942c9c3e2f",
    }

    # 最多重试 3 次：TikTok 偶发返回半截 HTML（含 UNEXPECTED_EOF_WHILE_READING 截断标记），
    # 这种脏响应解析必失败，所以先 sleep 1s 再重试，而不是立即报错终止。
    for _ in range(3):
        html_str = _get_str_response(
            await async_req(url=url, proxy_addr=proxy_addr, headers=headers, abroad=True, http2=False)
        )
        await asyncio.sleep(1)  # 异步休眠，避免阻塞事件循环
        # 命中「该节点地区已停止运营 TikTok」公告页：属于代理节点地域被墙，必须抛错让用户换节点，
        # 而不是当成「未开播」静默放过。
        if "We regret to inform you that we have discontinued operating TikTok" in html_str:
            msg = re.search("<p>\n\\s+(We regret to inform you that we have discontinu.*?)\\.\n\\s+</p>", html_str)
            raise ConnectionError(
                "Your proxy node's regional network is blocked from accessing TikTok; please switch to a node in "
                + f"another region to access. {msg.group(1) if msg else ''}"
            )
        # 只有「不含 EOF 截断标记」的整页才尝试解析；截断页直接走下一次重试。
        if "UNEXPECTED_EOF_WHILE_READING" not in html_str:
            try:
                json_str_matches = cast(
                    list[str],
                    re.findall('<script id="SIGI_STATE" type="application/json">(.*?)</script>', html_str, re.DOTALL),
                )
                if not json_str_matches:
                    raise ConnectionError("Please check if your network can access the TikTok website normally")
                json_str = json_str_matches[0]
            except Exception:
                raise ConnectionError("Please check if your network can access the TikTok website normally")
            return _loads_dict(json_str)

    raise ConnectionError(
        "Failed to retrieve TikTok data after 3 retries, please check if your network can access "
        + "the TikTok website normally"
    )


@trace_error_decorator
async def get_kuaishou_stream_data(
    url: str, proxy_addr: OptionalStr = None, cookies: OptionalStr = None
) -> dict[str, object]:
    # 获取快手直播数据
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:148.0) Gecko/20100101 Firefox/148.0",
        "Accept-Language": "zh-CN,zh;q=0.8,zh-TW;q=0.7,zh-HK;q=0.5,en-US;q=0.3,en;q=0.2",
    }
    if cookies:
        headers["Cookie"] = cookies
    # 该路径无重试：抓取 HTML 一旦抛异常（网络抖动/超时）就直接按「未开播」返回，
    # 不会区分「真离线」与「临时拉取失败」，主循环下一轮会再试。
    try:
        html_str = _get_str_response(await async_req(url=url, proxy_addr=proxy_addr, headers=headers))
    except Exception as e:
        # 用 print 而非 logger：抓取失败必须始终暴露到控制台（即使 logger 被静默/重定向），
        # 否则网络抖动会被静默吞掉、房间永久按「未开播」空转。直接回未开播，主循环下轮重试。
        print(f"Failed to fetch data from {url}.{e}")
        return {"type": 1, "is_live": False}

    try:
        # 快手把房间状态塞进页面 __INITIAL_STATE__ 全局变量，正则抠出后还要补一个右花括号收尾
        # （内联 JSON 被截断在 "gameInfo" 前）。__INITIAL_STATE__ 缺失即视为页面结构变化/被风控。
        json_str_match = re.search("<script>window.__INITIAL_STATE__=(.*?);\\(function\\(\\)\\{var s;", html_str)
        if not json_str_match:
            raise ValueError("Failed to find __INITIAL_STATE__")
        json_str = json_str_match.group(1)
        play_list_matches = cast(list[str], re.findall('(\\{"liveStream".*?),"gameInfo', json_str))
        if not play_list_matches:
            raise ValueError("Failed to find liveStream")
        # 内联串在 "gameInfo" 前被截断，补 1 个右花括号平衡结构。
        play_list = _loads_dict(play_list_matches[0] + "}")
    except (AttributeError, IndexError, json.JSONDecodeError) as e:
        # 只捕获「结构解析」类异常（页面改版/字段缺失/JSON 坏），按未开播返回；
        # 其它异常（如超时已由上层兜住）不在此吞掉，避免把非解析错误也误判成未开播而静默丢失根因。
        print(f"Failed to parse JSON data from {url}. Error: {e}")
        return {"type": 1, "is_live": False}

    result: dict[str, object] = {"type": 2, "is_live": False}

    # errorType 字段存在、或 liveStream 缺失，通常代表账号/地域受限（封禁/风控），
    # 此时 play_list 不含真实流信息，直接按「未开播」返回而非抛错。
    if "errorType" in play_list or "liveStream" not in play_list:
        error_type = cast(dict[str, object], play_list.get("errorType") or {})
        title = error_type.get("title", "")
        content = error_type.get("content", "")
        error_msg = (title if isinstance(title, str) else "") + (content if isinstance(content, str) else "")
        print(f"Failed URL: {url} Error message: {error_msg}")
        return result

    live_stream = cast(dict[str, object], play_list.get("liveStream") or {})
    # liveStream 为空也意味着 IP 被封（非开播态），打印提示后按未开播返回。
    if not live_stream:
        print("IP banned. Please change device or network.")
        return result

    author = cast(dict[str, object], play_list.get("author") or {})
    anchor_name = author.get("name", "")
    result.update({"anchor_name": anchor_name})

    play_urls_obj = live_stream.get("playUrls")
    if play_urls_obj:
        play_url_list: object
        # 新接口 playUrls 为分 codec 的字典（h264 支路为主），无 adaptationSet 说明字段缺失，
        # 按未开播返回；下方 else 是 2024-11-28 起已失效的旧 list 结构（保留作兜底，基本不会命中）。
        if isinstance(play_urls_obj, dict) and "h264" in play_urls_obj:
            h264 = cast(dict[str, object], cast(dict[str, object], play_urls_obj)["h264"])
            if "adaptationSet" not in h264:
                return result
            adaptation = cast(dict[str, object], h264["adaptationSet"])
            play_url_list = adaptation.get("representation")
        else:
            # TODO: Old version which not working at 20241128, could be removed if not working confirmed
            play_urls_list = cast(list[object], play_urls_obj) if isinstance(play_urls_obj, list) else []
            if not play_urls_list:
                return result
            first_item = cast(dict[str, object], play_urls_list[0])
            adaptation2 = cast(dict[str, object], first_item.get("adaptationSet") or {})
            play_url_list = adaptation2.get("representation", [])
        result.update({"flv_url_list": play_url_list, "is_live": True})

    return result


@trace_error_decorator
async def get_kuaishou_stream_data2(
    url: str, proxy_addr: OptionalStr = None, cookies: OptionalStr = None
) -> dict[str, object] | None:
    # 获取快手直播流数据（备用接口）
    headers = {
        "User-Agent": "ios/7.830 (ios 17.0; ; iPhone 15 (A2846/A3089/A3090/A3092))",
        "Accept-Language": "zh-CN,zh;q=0.8,zh-TW;q=0.7,zh-HK;q=0.5,en-US;q=0.3,en;q=0.2",
        # 仅保留直播间 Referer，移除原硬编码分享链接（含过期 shareToken/userId/photoId）
        "Referer": "https://live.kuaishou.com/",
        "content-type": "application/json",
    }
    if cookies:
        headers["Cookie"] = cookies
    else:
        # 未配置 cookie 时自动获取快手访客 did，避免硬编码过期凭据
        headers["Cookie"] = await _ensure_kuaishou_did(proxy_addr)
    try:
        # 快手 URL 形如 https://live.kuaishou.com/u/xxxx，提取 u/ 后的部分作为 eid
        if "/u/" in url:
            eid = url.split("/u/")[1].strip()
        else:
            raise ValueError("Failed to extract eid from kuaishou URL")
        data: dict[str, object] = {"source": 5, "eid": eid, "shareMethod": "card", "clientType": "WEB_OUTSIDE_SHARE_H5"}
        # 走的不是快手官方域名，而是 chenzhongtech 的第三方聚合接口（kpn=GAME_ZONE 为固定包名标识），
        # captchaToken 留空——该接口对游客基本不校验验证码，留空即可；带错 token 反而会被拒。
        app_api = "https://livev.m.chenzhongtech.com/rest/k/live/byUser?kpn=GAME_ZONE&captchaToken="
        json_str = _get_str_response(await async_req(url=app_api, proxy_addr=proxy_addr, headers=headers, data=data))
        json_data = _loads_dict(json_str)
        live_stream = cast(dict[str, object], json_data.get("liveStream") or {})
        user = cast(dict[str, object], live_stream.get("user") or {})
        anchor_name = user.get("user_name")
        result: dict[str, object] = {
            "type": 2,
            "anchor_name": anchor_name,
            "is_live": False,
        }
        # app 端用 living 布尔字段判定开播（非 status 数字），与 web 端语义不同；
        # 仅 living 为真才组装 m3u8/flv 多分辨率候选与 backup 地址。
        live_status = live_stream.get("living")
        if live_status:
            result["is_live"] = True
            backup_m3u8_url = live_stream.get("hlsPlayUrl")
            play_urls = cast(list[object], live_stream.get("playUrls") or [])
            first_play = cast(dict[str, object], play_urls[0]) if play_urls else {}
            backup_flv_url = first_play.get("url", "")
            multi_hls = cast(list[object], live_stream.get("multiResolutionHlsPlayUrls") or [])
            if multi_hls:
                first_hls = cast(dict[str, object], multi_hls[0])
                result["m3u8_url_list"] = first_hls.get("urls", [])
            multi_play = cast(list[object], live_stream.get("multiResolutionPlayUrls") or [])
            if multi_play:
                first_mp = cast(dict[str, object], multi_play[0])
                result["flv_url_list"] = first_mp.get("urls", [])
            result["backup"] = {"m3u8_url": backup_m3u8_url, "flv_url": backup_flv_url}
        # anchor_name 非空才返回本函数结果；为空说明直播间不存在/被风控，
        # 落到下方 except 兜底、统一回退 get_kuaishou_stream_data 再试一次。
        if result["anchor_name"]:
            return result
    # 兜底回退：本函数解析抛异常、或成功解析但 anchor_name 为空（房间不存在/被风控）时，
    # 都转去走 get_kuaishou_stream_data（网页 __INITIAL_STATE__ 路径）再试一次；
    # 注意即使本路径已拿到流地址，只要 anchor_name 为空也会触发这次回退，可能重复解析。
    except Exception as e:
        print(f"{e}, Failed URL: {url}, preparing to switch to a backup plan for re-parsing.")
    return await get_kuaishou_stream_data(url, cookies=cookies, proxy_addr=proxy_addr)


@trace_error_decorator
async def get_huya_stream_data(
    url: str, proxy_addr: OptionalStr = None, cookies: OptionalStr = None
) -> dict[str, object]:
    # 获取虎牙直播数据
    # 依赖页面内联 `stream:` 对象；正则未命中即抛 ValueError，由装饰器/调用方回退到
    # 微信小程序接口 get_huya_app_stream_url，本函数不自行处理「未开播」语义。
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:148.0) Gecko/20100101 Firefox/148.0",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.8,zh-TW;q=0.7,zh-HK;q=0.5,en-US;q=0.3,en;q=0.2",
        # 移除原硬编码的长串过期 Cookie（含大量 session/token，多数为访客统计字段）
        # 未配置 cookie 时不发送 Cookie 头，让虎牙服务器在响应中重新下发访客 cookie
    }
    if cookies:
        headers["Cookie"] = cookies

    html_str = _get_str_response(await async_req(url=url, proxy_addr=proxy_addr, headers=headers))
    # 直播间页内联了 stream: {...} 对象，正则抠出后补一个右花括号收尾（截断在 iWebDefaultBitRate 前）。
    # 该内联结构随页面改版会变，缺失即抛错、交由上层回退到小程序接口（get_huya_app_stream_url）。
    json_str_matches = cast(list[str], re.findall('stream: (\\{"data".*?),"iWebDefaultBitRate"', html_str))
    if not json_str_matches:
        raise ValueError("Failed to find stream data")
    json_str = json_str_matches[0]
    return _loads_dict(json_str + "}")


@trace_error_decorator
async def get_huya_app_stream_url(
    url: str, proxy_addr: OptionalStr = None, cookies: OptionalStr = None
) -> dict[str, object]:
    # 通过虎牙微信小程序API获取直播流地址
    headers = {
        "User-Agent": "ios/7.830 (ios 17.0; ; iPhone 15 (A2846/A3089/A3090/A3092))",
        "xweb_xhr": "1",
        "referer": "https://servicewechat.com/wx74767bf0b684f7d3/301/page-frame.html",
        "accept-language": "zh-CN,zh;q=0.9",
    }

    if cookies:
        headers["Cookie"] = cookies
    # 微信小程序接口按纯数字 roomid 取流；URL 里可能是字母房间号（短链/主播号），
    # 需先抓页面用 ProfileRoom 正则反查出数字 roomid，否则直接报错要求用户换数字链接。
    room_id = url.split("?")[0].rsplit("/", maxsplit=1)[-1]

    if any(char.isalpha() for char in room_id):
        html_str = _get_str_response(await async_req(url, proxy_addr=proxy_addr, headers=headers))
        room_id_match = re.search('ProfileRoom":(.*?),"sPrivateHost', html_str)
        if room_id_match:
            room_id = room_id_match.group(1)
        else:
            raise Exception('Please use "https://www.huya.com/+room_number" for recording')

    # mp.huya.com 小程序接口参数：m=Live/do=profileRoom 固定；showSecret=1 要求返回防盗链参数。
    params = {
        "m": "Live",
        "do": "profileRoom",
        "roomid": room_id,
        "showSecret": "1",
    }
    wx_app_api = f"https://mp.huya.com/cache.php?{urllib.parse.urlencode(params)}"
    json_str = _get_str_response(await async_req(url=wx_app_api, proxy_addr=proxy_addr, headers=headers))
    json_data = _loads_dict(json_str)
    data_field = cast(dict[str, object], json_data.get("data") or {})
    profile_info = cast(dict[str, object], data_field.get("profileInfo") or {})
    anchor_name = profile_info.get("nick")
    live_status = data_field.get("realLiveStatus")
    live_data = cast(dict[str, object], data_field.get("liveData") or {})
    live_title = live_data.get("introduction")
    # 小程序接口用字符串 "ON" 表示开播，与 web 端数字状态码不同；非 ON 直接按未开播返回。
    if live_status != "ON":
        return {"anchor_name": anchor_name, "is_live": False}
    else:
        stream_field = cast(dict[str, object], data_field.get("stream") or {})
        base_steam_info_list = cast(list[object], stream_field.get("baseSteamInfoList") or [])
        play_url_list: list[dict[str, object]] = []
        for i_obj in base_steam_info_list:
            i = cast(dict[str, object], i_obj)
            cdn_type = i.get("sCdnType")
            stream_name = i.get("sStreamName")
            flv_anti_code = i.get("sFlvAntiCode")
            s_flv_url = i.get("sFlvUrl")
            s_hls_url = i.get("sHlsUrl")
            hls_anti_code = i.get("sHlsAntiCode")
            if not (stream_name and flv_anti_code):
                continue

            # 直接使用小程序接口返回的原始防盗链参数（sHlsAntiCode/sFlvAntiCode），
            # 统一降为 http（实测 https 返回 403、仅 http 可用），并对所有 CDN 一致地做
            # 反爬参数替换（tars_mp→huya_webh5, bhct→bgct，缺失时幂等无副作用）。
            # suffix 显式区分 HLS(.m3u8)/FLV(.flv)，不可依据 host 推断（HLS/FLV host 路径同为 /src）。
            def _normalize(base: object, anti: object, suffix: str) -> str:
                if not (isinstance(base, str) and isinstance(anti, str) and base and anti):
                    return ""
                url = f"{base}/{stream_name}.{suffix}?{anti}"
                url = url.replace("https://", "http://")
                return url.replace("&ctype=tars_mp", "&ctype=huya_webh5").replace("&fs=bhct", "&fs=bgct")

            m3u8_url = _normalize(s_hls_url, hls_anti_code, "m3u8")
            flv_url = _normalize(s_flv_url, flv_anti_code, "flv")
            play_url_list.append({"cdn_type": cdn_type, "m3u8_url": m3u8_url, "flv_url": flv_url})

        if not play_url_list:
            return {"anchor_name": anchor_name, "is_live": True}

        # 候选排序：实测 HLS 可靠承载线路为 HS（AL/TX 常因该房间未启用该线路返回 403，
        # 且各线路共享完全相同的防盗链参数——403 非请求问题、而是线路未承载推流，随时可能切换）。
        # 故枚举全部候选交给 select_source_url 逐条按可达性校验，首位优先 HS 以最大化「首试即中」；
        # 不再固定取 index0（AL 抢占时徒增无谓探针）或固定 TX 优先（TX 同样会离线）。
        cdn_priority = ["HS", "HW", "TX", "AL"]

        def _rank(item: dict[str, object]) -> int:
            try:
                return cdn_priority.index(str(item.get("cdn_type")))
            except ValueError:
                return len(cdn_priority)

        ordered = sorted(play_url_list, key=_rank)
        selected_item = ordered[0]

        selected_cdn_type = selected_item.get("cdn_type")
        selected_m3u8 = selected_item.get("m3u8_url")
        selected_flv = selected_item.get("flv_url")
        selected_m3u8_url: str | None = selected_m3u8 if isinstance(selected_m3u8, str) else None
        selected_flv_url: str | None = selected_flv if isinstance(selected_flv, str) else None

        # record_url: 与所选 flv 同源，始终保持 http（https 实测 403）。
        record_url: str | None
        if selected_flv_url:
            record_url = selected_flv_url
        else:
            record_url = None

        # 弹幕所需三元组:yyid 取自 profileInfo;lChannelId/lSubChannelId 优先取 data 顶层
        # chTopId/subChId(部分响应含), 否则回退到 baseSteamInfoList[0](直播路径下必非空)。
        # 供 main.py 在 OD/BD/UHD 分支直接组装 ayyuid/topSid/subSid, 与 web 路径字段一致。
        first_steam_info = cast(dict[str, object], base_steam_info_list[0] if base_steam_info_list else {})
        yyid = profile_info.get("yyid")
        l_channel_id = data_field.get("chTopId") or first_steam_info.get("lChannelId")
        l_sub_channel_id = data_field.get("subChId") or first_steam_info.get("lSubChannelId")

        # 全部候选注入 m3u8_url_list/flv_url_list，供 select_source_url 逐条按可达性校验、
        # 首条可达即选用（动态规避离线 CDN 线路）。候选顺序已按 HS 优先排序。
        m3u8_url_list = [c.get("m3u8_url") for c in ordered if isinstance(c.get("m3u8_url"), str) and c.get("m3u8_url")]
        flv_url_list = [c.get("flv_url") for c in ordered if isinstance(c.get("flv_url"), str) and c.get("flv_url")]

        return {
            "anchor_name": anchor_name,
            "is_live": True,
            "m3u8_url": selected_m3u8_url,
            "m3u8_url_list": m3u8_url_list,
            "flv_url": selected_flv_url,
            "flv_url_list": flv_url_list,
            "record_url": record_url,
            "title": live_title,
            "yyid": yyid,
            "lChannelId": l_channel_id,
            "lSubChannelId": l_sub_channel_id,
        }


def md5(data: str) -> str:
    # 计算字符串的MD5哈希值
    # 入参为 str 故先 utf-8 编码（斗鱼 websec 的 enc_key/key 均为字符串）；被 get_token_js
    # 的签名迭代循环反复调用，是斗鱼 anti-bot 签名的核心一步，不可替换为其它哈希。
    return hashlib.md5(data.encode("utf-8")).hexdigest()


async def get_token_js(rid: str, did: str, proxy_addr: OptionalStr = None) -> dict[str, object]:
    # 获取斗鱼API请求签名参数
    # 签名失败（接口异常/风控/error!=0）时返回 {}，调用方 get_douyu_stream_data 据此判断并中断，
    # 而非拿空签名去请求必败的 play 接口（空签名会得到无意义响应而非明确报错）。
    try:
        key_url = f"https://www.douyu.com/wgapi/livenc/liveweb/websec/getEncryption?did={did}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
            + "Chrome/141.0.0.0 Safari/537.36",
            "Referer": f"https://www.douyu.com/{rid}",
        }
        json_str = _get_str_response(await async_req(url=key_url, proxy_addr=proxy_addr, headers=headers))
        key_data = _loads_dict(json_str)
        if key_data.get("error") != 0:
            return {}
        enc_key = cast(dict[str, object], key_data.get("data") or {})
        ts = int(time.time())
        rand_str_v = enc_key.get("rand_str")
        auth = rand_str_v if isinstance(rand_str_v, str) else ""
        key_v = enc_key.get("key")
        key = key_v if isinstance(key_v, str) else ""
        enc_time_v = enc_key.get("enc_time", 0)
        enc_time = enc_time_v if isinstance(enc_time_v, int) else 0
        # is_special==1 表示该房间走特殊签名分支，无需拼接 rid+ts 的待签串；
        # 普通房间则把 rid+ts 作为待签内容参与 md5 链，漏拼会导致 auth 校验失败被拒。
        sign_str = "" if enc_key.get("is_special") == 1 else f"{rid}{ts}"
        for _ in range(enc_time):
            auth = md5(auth + key)
        auth = md5(auth + key + sign_str)
        return {"enc_data": enc_key.get("enc_data"), "did": did, "ts": ts, "auth": auth}
    except Exception as e:
        print(f"Get douyu sign params error: {e}")
        return {}


@trace_error_decorator
async def get_douyu_info_data(
    url: str, proxy_addr: OptionalStr = None, cookies: OptionalStr = None
) -> dict[str, object]:
    # 获取斗鱼直播间基本信息
    headers = {
        "User-Agent": "ios/7.830 (ios 17.0; ; iPhone 15 (A2846/A3089/A3090/A3092))",
        "Referer": "https://m.douyu.com/3125893?rid=3125893&dyshid=0-96003918aa5365bc6dcb4933000316p1&dyshci=181",
        # 移除原硬编码的斗鱼登录态 Cookie（含 acf_auth/dy_auth/acf_uid 等用户登录凭据）
        # 未配置 cookie 时不发送 Cookie 头，斗鱼服务器会下发访客 cookie 用于公开直播间访问
    }
    if cookies:
        headers["Cookie"] = cookies

    # 斗鱼 URL 形态不一：带 rid= 查询参数的直链可直接取到房间号；
    # 否则从路径末段抠字母号，再抓移动端 vike_pageContext 还原成真正的数字 rid
    # （web 端 betard 接口只认数字 rid，字母号/分享短链必须先解析），否则取流必失败。
    match_rid = re.search("rid=(.*?)(?=&|$)", url)
    if match_rid:
        rid = match_rid.group(1)
    else:
        rid_match = re.search("douyu.com/(.*?)(?=\\?|$)", url)
        if not rid_match:
            raise ValueError("Failed to find rid in url")
        rid = rid_match.group(1)
        html_str = await async_req(url=f"https://m.douyu.com/{rid}", proxy_addr=proxy_addr, headers=headers)
        html_str = _get_str_response(html_str)
        json_str_matches = re.findall('<script id="vike_pageContext" type="application/json">(.*?)</script>', html_str)
        if not json_str_matches:
            raise ValueError("Failed to find vike_pageContext")
        json_str = json_str_matches[0]
        json_data = json.loads(json_str)
        rid = json_data["pageProps"]["room"]["roomInfo"]["roomInfo"]["rid"]

    # 抓 vike_pageContext 时用 ios UA（移动端页面模板），真正取房间信息切回桌面 Firefox UA：
    # betard 接口按桌面端返回结构解析，UA 不对会拿到不同的页面骨架导致字段取不到。
    headers["User-Agent"] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:148.0) Gecko/20100101 Firefox/148.0"
    url2 = f"https://www.douyu.com/betard/{rid}"
    json_str = await async_req(url=url2, proxy_addr=proxy_addr, headers=headers)
    json_str = _get_str_response(json_str)
    json_data = json.loads(json_str)
    result: dict[str, object] = {"anchor_name": json_data["room"]["nickname"], "is_live": False}
    # 斗鱼「show_status==1 且 videoLoop==0」才视为真开播：videoLoop!=0 多为轮播/回放，
    # 不应被当作直播录制（否则录到循环播放的录像）。
    if json_data["room"]["videoLoop"] == 0 and json_data["room"]["show_status"] == 1:
        result["title"] = json_data["room"]["room_name"].replace("&nbsp;", "")
        result["is_live"] = True
        result["room_id"] = json_data["room"]["room_id"]
    return result


@trace_error_decorator
async def get_douyu_stream_data(
    rid: str, rate: str = "-1", proxy_addr: OptionalStr = None, cookies: OptionalStr = None
) -> dict[str, object]:
    # 获取斗鱼直播间流地址
    # did 是固定的游客设备标识（非登录态），斗鱼 websec 签名依赖它；签名失败（sign_params 为空）
    # 时返回 {error:-1,...} 让调用方显式中断，而非静默 None（None 会被误判为「未开播」空转）。
    # 直接透传接口原始 json（含 code/msg），由调用方按 code 决定重试或回退。
    # 斗鱼对游客态的 websec 签名要求一个固定写死的 did（非真实设备号，来自抓包）；
    # 服务端对游客宽容、不校验 duid 真伪，用固定值即可正常签名，改了反而可能触发风控。
    did = "10000000000000000000000000003306"
    sign_params = await get_token_js(rid, did, proxy_addr=proxy_addr)
    if not sign_params:
        return {"error": -1, "msg": "Failed to get sign params", "data": {}}
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/141.0.0.0 Safari/537.36",
        "Referer": f"https://www.douyu.com/{rid}",
        "Content-Type": "application/x-www-form-urlencoded",
    }
    if cookies:
        headers["Cookie"] = cookies

    post_data = (
        f"enc_data={sign_params['enc_data']}"
        f"&tt={sign_params['ts']}"
        f"&did={sign_params['did']}"
        f"&auth={sign_params['auth']}"
        f"&cdn=&rate={rate}&hevc=0&fa=0&ive=0"
    )
    app_api = f"https://www.douyu.com/lapi/live/getH5PlayV1/{rid}"
    json_str = await async_req(url=app_api, proxy_addr=proxy_addr, headers=headers, data=post_data)
    json_str = _get_str_response(json_str)
    json_data = json.loads(json_str)
    return cast(dict[str, object], json_data)


@trace_error_decorator
async def get_yy_stream_data(
    url: str, proxy_addr: OptionalStr = None, cookies: OptionalStr = None
) -> dict[str, object]:
    # 获取 YY 直播流数据
    # 解析链路：先抓主播页抠昵称 + cid，再用写死的 stream-manager 模板请求拿流（游客 uid=0 即可）；
    # 返回 is_live + flv/m3u8；昵称/cid 抠不到直接抛 ValueError，由装饰器上层按「未开播」兜底重试。
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36 Edg/141.0.0.0",
        "Accept-Language": "zh-CN,zh;q=0.8,zh-TW;q=0.7,zh-HK;q=0.5,en-US;q=0.3,en;q=0.2",
        "Referer": "https://www.yy.com/",
        # 移除原硬编码的 YY 访客统计 Cookie（hd_newui/hdjs_session_id 等均为临时统计字段）
        # 未配置 cookie 时不发送 Cookie 头，YY 服务器会在响应中重新下发访客 cookie
    }
    if cookies:
        headers["Cookie"] = cookies

    html_str = await async_req(url=url, proxy_addr=proxy_addr, headers=headers)
    html_str = _get_str_response(html_str)
    anchor_name_match = re.search('nick: "(.*?)",\n\\s+logo', html_str)
    if not anchor_name_match:
        raise ValueError("Failed to find anchor name")
    anchor_name = anchor_name_match.group(1)
    cid_match = re.search('sid : "(.*?)",\n\\s+ssid', html_str, re.DOTALL)
    if not cid_match:
        raise ValueError("Failed to find cid")
    cid = cid_match.group(1)

    # 下面这份 JSON 是抓包得到的真实 stream-manager 请求模板：head.seq / client_ver 等是
    # 固定写死的历史值，服务端对游客（uid64=0）宽容、不校验这些字段真伪；client_type=108
    # 标识 web 端。改动这些值需重新抓包，否则可能拿不到流。
    data = (
        '{"head":{"seq":1701869217590,"appidstr":"0","bidstr":"121","cidstr":"'
        + cid
        + '","sidstr":"'
        + cid
        + '","uid64":0,"client_type":108,"client_ver":"5.17.0","stream_sys_ver":1,"app":"yylive_web","playersdk_ver":"5.17.0","thundersdk_ver":"0","streamsdk_ver":"5.17.0"},"client_attribute":{"client":"web","model":"web0","cpu":"","graphics_card":"","os":"chrome","osversion":"0","vsdk_version":"","app_identify":"","app_version":"","business":"","width":"1920","height":"1080","scale":"","client_type":8,"h265":0},"avp_parameter":{"version":1,"client_type":8,"service_type":0,"imsi":0,"send_time":1701869217,"line_seq":-1,"gear":4,"ssl":1,"stream_format":0}}'
    )
    data_bytes = data.encode("utf-8")
    params = {"uid": "0", "cid": cid, "sid": cid, "appid": "0", "sequence": "1701869217590", "encode": "json"}
    url2 = f"https://stream-manager.yy.com/v3/channel/streams?{urllib.parse.urlencode(params)}"
    json_str = await async_req(url=url2, data=data_bytes, proxy_addr=proxy_addr, headers=headers)
    json_str = _get_str_response(json_str)
    json_data = json.loads(json_str)
    # stream-manager 响应只含流地址、不含主播名（昵称来自前面页面正则抠取），
    # 手动把 anchor_name 塞进返回结构，供下游统一按 key 取用。
    json_data["anchor_name"] = anchor_name

    # 第二次请求单独取房间标题（detail 接口），sequence 改用实时时间戳；两次请求串起
    # 主播名（来自页面）+ 流地址（来自 stream-manager）+ 标题（来自 detail）。
    params = {
        "uid": "",
        "sid": cid,
        "ssid": cid,
        "_": int(time.time() * 1000),
    }
    detail_api = f"https://www.yy.com/live/detail?{urllib.parse.urlencode(params)}"
    json_str2 = await async_req(detail_api, proxy_addr=proxy_addr, headers=headers)
    json_str2 = _get_str_response(json_str2)
    json_data2 = json.loads(json_str2)
    json_data["title"] = json_data2["data"]["roomName"]
    return cast(dict[str, object], json_data)


@trace_error_decorator_or_none
async def get_bilibili_room_info_h5(url: str, proxy_addr: OptionalStr = None, cookies: OptionalStr = None) -> str:
    # 获取 B站直播间 H5 接口信息
    # 失败时返回 ""（而非 None）：调用方以 `title = ... or ""` 兜底，None 会破坏该兜底并
    # 使 get_bilibili_room_info 跨接口拼装标题时 TypeError。
    headers = {
        "user-agent": "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/141.0.0.0 Mobile Safari/537.36",
        "accept-language": "zh-CN,zh;q=0.8,zh-TW;q=0.7,zh-HK;q=0.5,en-US;q=0.3,en;q=0.2",
        "cookie": "",
        "origin": "https://live.bilibili.com",
        "referer": "https://live.bilibili.com/26066074",
    }
    # 调用方透传 cookie 时优先采用；否则走游客态/自动获取凭据（各平台未登录态取流能力不一，部分更易被风控）
    if cookies:
        headers["cookie"] = cookies

    room_id = _safe_extract_id(url)
    api = f"https://api.live.bilibili.com/xlive/web-room/v1/index/getH5InfoByRoom?room_id={room_id}"
    json_str = await async_req(api, proxy_addr=proxy_addr, headers=headers)
    json_str = _get_str_response(json_str)
    room_info = json.loads(json_str)
    title = room_info["data"]["room_info"].get("title") if room_info.get("data") else ""
    return title


@trace_error_decorator
async def get_bilibili_room_info(
    url: str, proxy_addr: OptionalStr = None, cookies: OptionalStr = None
) -> dict[str, object]:
    # 获取 B站直播间信息（含主播名）
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:148.0) Gecko/20100101 Firefox/148.0",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.8,zh-TW;q=0.7,zh-HK;q=0.5,en-US;q=0.3,en;q=0.2",
    }
    # 调用方透传 cookie 时优先采用；否则走游客态/自动获取凭据（各平台未登录态取流能力不一，部分更易被风控）
    if cookies:
        headers["Cookie"] = cookies

    try:
        room_id = _safe_extract_id(url)
        json_str = await async_req(
            f"https://api.live.bilibili.com/room/v1/Room/room_init?id={room_id}", proxy_addr=proxy_addr, headers=headers
        )
        json_str = _get_str_response(json_str)
        room_info = json.loads(json_str)
        uid = room_info["data"]["uid"]
        live_status = True if room_info["data"]["live_status"] == 1 else False

        api = f"https://api.live.bilibili.com/live_user/v1/Master/info?uid={uid}"
        json_str2 = await async_req(url=api, proxy_addr=proxy_addr, headers=headers)
        json_str2 = _get_str_response(json_str2)
        anchor_info = json.loads(json_str2)
        anchor_name = anchor_info["data"]["info"]["uname"]

        title = await get_bilibili_room_info_h5(url, proxy_addr, cookies)
        return {"anchor_name": anchor_name, "live_status": live_status, "room_url": url, "title": title}
    except Exception as e:
        # 房间信息抓取失败（房间不存在/风控/网络）一律静默返回空名+未开播，交由主循环下轮重试，
        # 不中断整体监控；anchor_name 用 "" 保证下游拼接标题时不会因 None 而 TypeError。
        print(e)
        return {"anchor_name": "", "live_status": False, "room_url": url}


@trace_error_decorator
async def get_bilibili_stream_data(
    url: str, qn: str = "10000", platform: str = "web", proxy_addr: OptionalStr = None, cookies: OptionalStr = None
) -> dict[str, object] | None:
    # 获取 B站直播流数据（多清晰度），返回 {url, current_qn, accept_qn}
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:148.0) Gecko/20100101 Firefox/148.0",
        "Accept-Language": "zh-CN,zh;q=0.8,zh-TW;q=0.7,zh-HK;q=0.5,en-US;q=0.3,en;q=0.2",
        "origin": "https://live.bilibili.com",
        "referer": "https://live.bilibili.com/26066074",
    }
    # 调用方透传 cookie 时优先采用；否则走游客态/自动获取凭据（各平台未登录态取流能力不一，部分更易被风控）
    if cookies:
        headers["Cookie"] = cookies

    room_id = _safe_extract_id(url)
    params = {"cid": room_id, "qn": qn, "platform": platform}
    play_api = f"https://api.live.bilibili.com/room/v1/Room/playUrl?{urllib.parse.urlencode(params)}"
    json_str = await async_req(play_api, proxy_addr=proxy_addr, headers=headers)
    json_str = _get_str_response(json_str)
    json_data = json.loads(json_str)
    # B站 get_play_url 仅 code==0 返回有效 durl，否则无源
    if json_data and json_data["code"] == 0:
        durl_list = json_data["data"].get("durl", [])
        # durl 为空即无可用清晰度，返回 None
        if not durl_list:
            return None
        # playUrl 接口无 qn 元信息，current_qn 取请求值，accept_qn 未知
        target_url = None
        # 优先挑含 "d1--cn-gotcha" 子串的 CDN 地址（B站某可用线路 host 特征），
        # 没有命中再退回列表末位；是经验性的线路优选，非官方保证。
        for i in durl_list:
            # 跳过 d1--cn-gotcha 这类中转/防盗链节点，优先选真实 CDN
            if "d1--cn-gotcha" in i.get("url", ""):
                target_url = i["url"]
                break
        if not target_url:
            target_url = durl_list[-1].get("url")
        return {"url": target_url, "current_qn": qn, "accept_qn": [qn]}
    else:
        # 旧 playUrl 返回非 0（多为 -352/-412 风控或参数被拒）时，回退到 v2 getRoomPlayInfo
        # 接口：它返回更完整的清晰度/编码列表，是 B站当前的取流主路径。
        params = {
            "room_id": room_id,
            "protocol": "0,1",
            "format": "0,1,2",
            "codec": "0,1,2",
            "qn": qn,
            "platform": "web",
            "ptype": "8",
            "dolby": "5",
            "panorama": "1",
            "hdr_type": "0,1",
        }
        api = f"https://api.live.bilibili.com/xlive/web-room/v2/index/getRoomPlayInfo?{urllib.parse.urlencode(params)}"
        json_str = await async_req(api, proxy_addr=proxy_addr, headers=headers)
        json_str = _get_str_response(json_str)
        json_data = json.loads(json_str)
        # live_status==0 表示未开播（1 为开播），此时 playurl_info 不存在，按未开播返回 None。
        if json_data["data"]["live_status"] == 0:
            print("The anchor did not start broadcasting.")
            # stream_list 字段缺失即无可用流，返回 None
            return None
        playurl_info = json_data["data"]["playurl_info"]
        stream_list = playurl_info["playurl"].get("stream", [])
        # format_list 字段缺失即无可用流，返回 None
        if not stream_list:
            return None
        format_list = stream_list[0].get("format", [])
        # stream_data_list 字段缺失即无可用流，返回 None
        if not format_list:
            return None
        stream_data_list = format_list[0].get("codec", [])
        # stream_data_list 为空即无可用流，返回 None
        if not stream_data_list:
            return None
        sorted_stream_list: list[dict[str, object]] = sorted(
            stream_data_list, key=itemgetter("current_qn"), reverse=True
        )
        # qn 字符串到「选择下标」的映射：10000=原画、400=蓝光、250=超清、150=高清、80=流畅。
        # 用 min(映射值, qn_count-1) 防止请求的清晰度超出实际可用档位导致下标越界，
        # 请求档位不存在时回退到最高可用清晰度。
        video_quality_options = {"10000": 0, "400": 1, "250": 2, "150": 3, "80": 4}
        qn_count = len(sorted_stream_list)
        select_stream_index = min(video_quality_options.get(qn, 0), qn_count - 1)
        stream_data: dict[str, object] = sorted_stream_list[select_stream_index]
        base_url = cast(str, stream_data["base_url"])
        url_info = stream_data.get("url_info", [])
        # url_info 字段缺失即无可用流，返回 None
        if not url_info:
            return None
        url_info_list = cast(list[dict[str, object]], url_info)
        host = cast(str, url_info_list[0].get("host", ""))
        extra = cast(str, url_info_list[0].get("extra", ""))
        m3u8_url = host + base_url + extra
        current_qn = str(stream_data.get("current_qn", qn))
        accept_qn = [str(s.get("current_qn")) for s in sorted_stream_list]
        # 最终解析出 m3u8 才返回，否则返回 None
        return {"url": m3u8_url, "current_qn": current_qn, "accept_qn": accept_qn}


# B站 wbi 签名混排表（官方固定 64 位置换，用于将 img_key+sub_key 截取为 32 位 mixinKey）
_MIXIN_KEY_ENC_TAB = [
    46,
    47,
    18,
    2,
    53,
    8,
    23,
    32,
    15,
    50,
    10,
    31,
    58,
    3,
    45,
    35,
    27,
    43,
    5,
    49,
    33,
    9,
    42,
    19,
    29,
    28,
    14,
    39,
    12,
    38,
    41,
    13,
    37,
    48,
    7,
    16,
    24,
    55,
    40,
    61,
    26,
    17,
    6,
    60,
    21,
    57,
    59,
    62,
    11,
    36,
    20,
    51,
    54,
    25,
    1,
    34,
    56,
    30,
    4,
    22,
    44,
    52,
    63,
    0,
]


def _get_mixin_key(orig: str) -> str:
    # 按官方混排表从 img_key+sub_key 截取 32 位 mixinKey
    return "".join(orig[i] for i in _MIXIN_KEY_ENC_TAB)[:32]


def _sign_wbi(params: dict[str, str], img_key: str, sub_key: str) -> dict[str, str]:
    # 生成 w_rid 签名：拼接 img_key+sub_key -> mixinKey -> 追加参数并 md5
    mixin_key = _get_mixin_key(img_key + sub_key)
    params["wts"] = str(int(time.time()))
    query = urllib.parse.urlencode(sorted(params.items()))
    params["w_rid"] = hashlib.md5((query + mixin_key).encode("utf-8")).hexdigest()
    return params


# B站 buvid 缓存：设备级标识（非房间级），进程内首次获取/生成后全局复用，
# 避免每个监测周期重复请求 spi 反复触发 B站风控（200+空 body，越取越失败的循环）
_bili_buvid_lock = threading.Lock()
_bili_buvid_cached = ""
# 当前缓存值是否为「生成的随机 UUID 兜底」（非服务器注册的真实设备标识）。
# 弹幕服务器对未注册 buvid 的 AUTH 会软拒绝；客户端收到拒绝后经
# invalidate_bili_buvid_cache() 清除缓存，下一轮监测重新走真实获取链。
_bili_buvid_is_fallback = False


def invalidate_bili_buvid_cache() -> None:
    # 使进程内 buvid 缓存失效（不清 cookie_cache 的首页 Set-Cookie TTL 缓存——那里存的
    # 是真实注册标识，可继续复用）。触发方为弹幕 AUTH 被拒：兜底 UUID 被服务器拒绝后
    # 不可复用，必须重新获取；真实 buvid 被拒时重取亦无副作用。
    global _bili_buvid_cached, _bili_buvid_is_fallback
    with _bili_buvid_lock:
        _bili_buvid_cached = ""
        _bili_buvid_is_fallback = False


async def get_bilibili_danmaku_info(
    url: str, proxy_addr: OptionalStr = None, cookies: OptionalStr = None
) -> dict[str, object] | None:
    # 获取 B站弹幕连接参数（token/server_host/host_list/room_id/uid/buvid），供 BilibiliDanmaku 进房。
    # 必须带 wbi 签名，否则 getDanmuInfo 返回 -352 风控。短号房间需先 room_init 转为真实 room_id。
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:148.0) Gecko/20100101 Firefox/148.0",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-CN,zh;q=0.8,zh-TW;q=0.7,zh-HK;q=0.5,en-US;q=0.3,en;q=0.2",
        "origin": "https://live.bilibili.com",
        "referer": "https://live.bilibili.com",
    }
    # 调用方透传 cookie 时优先采用；否则走游客态/自动获取凭据（各平台未登录态取流能力不一，部分更易被风控）
    if cookies:
        headers["Cookie"] = cookies

    room_id = _safe_extract_id(url)

    # 1) room_init 取真实 room_id 与 uid（短号房间 URL 的 path id 可能是短号，需转换）
    real_room_id = room_id
    uid = 0
    try:
        init_str = await async_req(
            f"https://api.live.bilibili.com/room/v1/Room/room_init?id={room_id}",
            proxy_addr=proxy_addr,
            headers=headers,
        )
        init_data = _loads_dict(_get_str_response(init_str))
        init_room: dict[str, object] = {}
        if isinstance(init_data, dict):
            d = init_data.get("data")
            if isinstance(d, dict):
                init_room = d
        real_room_id = str(init_room.get("room_id") or room_id)
        _uid = init_room.get("uid")
        uid = int(_uid) if isinstance(_uid, int) else 0
    except Exception as e:
        logger.warning(f"[B站直播]room_init 失败: {type(e).__name__}: {e}")

    # 2) nav 取 wbi_img（img_key/sub_key）
    img_key = ""
    sub_key = ""
    try:
        nav_str = await async_req(
            "https://api.bilibili.com/x/web-interface/nav", proxy_addr=proxy_addr, headers=headers
        )
        nav_data = _loads_dict(_get_str_response(nav_str))
        nav_wbi: dict[str, object] = {}
        if isinstance(nav_data, dict):
            w = nav_data.get("data")
            if isinstance(w, dict):
                nw = w.get("wbi_img")
                if isinstance(nw, dict):
                    nav_wbi = nw
        img_url = str(nav_wbi.get("img_url", ""))
        sub_url = str(nav_wbi.get("sub_url", ""))
        img_key = img_url.rsplit("/", 1)[-1].split(".")[0]
        sub_key = sub_url.rsplit("/", 1)[-1].split(".")[0]
    except Exception as e:
        logger.warning(f"[B站直播]nav(wbi) 获取失败: {type(e).__name__}: {e}")

    # 3) buvid 获取链（匿名弹幕进房也需要 buvid 字段），按「真实注册标识优先」排序：
    #    a. 进程缓存   —— 设备级标识，长期有效；
    #    b. 登录 cookie —— cookie 带 buvid3= 时提取（服务器注册过的最可靠来源）；
    #    c. spi 接口   —— 官方端点 /x/frontend/finger/spi（注意结尾 i，拼写错误会 200+空 body）。
    #                     偶发风控返回空响应体（200+空 body）→ _loads_dict 得 {}，重试一次再定罪；
    #    d. 首页 Set-Cookie —— GET https://www.bilibili.com/ 响应头下发真实注册 buvid3
    #                     （与 spi 不同域名，spi 被风控时通常仍可用；经 cookie_cache 复用）；
    #    e. 随机 UUID 兜底 —— 未注册标识，弹幕服务器 AUTH 会软拒绝；仅保进房包非空，
    #                     被拒后由 invalidate_bili_buvid_cache() 清除，下一轮重新获取。
    # 进房包带空 buvid 会被弹幕服务器硬断连（"no close frame received or sent"），故必须非空。
    # 锁覆盖取值全程：并发首次调用只打一次 spi/首页；兜底 UUID 同样缓存但标记 is_fallback。
    global _bili_buvid_cached, _bili_buvid_is_fallback
    with _bili_buvid_lock:
        buvid = _bili_buvid_cached
        if not buvid and cookies:
            _m = re.search(r"buvid3=([^;\s]+)", str(cookies))
            if _m and _m.group(1).strip():
                buvid = _m.group(1).strip()
                logger.debug(f"[B站直播]使用 cookie 中的 buvid3: {buvid}")
        if not buvid:
            for _attempt in range(2):
                try:
                    spi_str = await async_req(
                        "https://api.bilibili.com/x/frontend/finger/spi", proxy_addr=proxy_addr, headers=headers
                    )
                    spi_data = _loads_dict(_get_str_response(spi_str))
                    spi_d: dict[str, object] = {}
                    if isinstance(spi_data, dict):
                        s = spi_data.get("data")
                        if isinstance(s, dict):
                            spi_d = s
                    buvid = str(spi_d.get("b_3") or spi_d.get("buvid") or "")
                    if buvid:
                        break
                except Exception as e:
                    if _attempt == 0:
                        logger.debug(f"[B站直播]buvid 获取失败(将重试): {type(e).__name__}: {e}")
                    else:
                        logger.warning(f"[B站直播]buvid 获取失败: {type(e).__name__}: {e}")
        if not buvid:
            # spi 两跳仍空（风控）：改走首页 Set-Cookie（真实注册标识，cookie_cache 内置
            # TTL 缓存与并发去重；UA 需浏览器态——headers 已是 Firefox UA）
            try:
                home_cookies = await _cache_fetch_cookies(
                    "https://www.bilibili.com/", proxy_addr=proxy_addr, headers=headers, fetcher=async_req
                )
                buvid = str(home_cookies.get("buvid3", "")).strip()
                if buvid:
                    logger.debug(f"[B站直播]spi 失败，从首页 Set-Cookie 获取 buvid3: {buvid}")
            except Exception as e:
                logger.debug(f"[B站直播]首页 Set-Cookie 获取 buvid3 失败: {type(e).__name__}: {e}")
        if not buvid:
            buvid = str(uuid.uuid4())
            _bili_buvid_is_fallback = True
            logger.debug(f"[B站直播]spi/首页均无 buvid，使用生成兜底 buvid3（未注册，AUTH 可能被拒）: {buvid}")
        else:
            _bili_buvid_is_fallback = False
        _bili_buvid_cached = buvid

    # 4) getDanmuInfo（wbi 签名）；无 wbi 则跳过签名，由调用方 -352 风控日志体现
    danmu_params: dict[str, str] = {"id": real_room_id, "type": "0", "web_location": "444.8"}
    if img_key and sub_key:
        try:
            _sign_wbi(danmu_params, img_key, sub_key)
        except Exception as e:
            logger.warning(f"[B站直播]wbi 签名失败: {type(e).__name__}: {e}")
    try:
        danmu_str = await async_req(
            f"https://api.live.bilibili.com/xlive/web-room/v1/index/getDanmuInfo?"
            f"{urllib.parse.urlencode(danmu_params)}",
            proxy_addr=proxy_addr,
            headers=headers,
        )
        danmu_data = _loads_dict(_get_str_response(danmu_str))
        danmu: dict[str, object] = {}
        if isinstance(danmu_data, dict):
            dd = danmu_data.get("data")
            if isinstance(dd, dict):
                danmu = dd
        if not danmu:
            logger.warning("[B站直播]getDanmuInfo 返回空（可能 -352 风控，检查 wbi 签名/cookie）")
            return None
        token = str(danmu.get("token", ""))
        host_list_raw = danmu.get("host_list")
        host_list: list[str] = []
        if isinstance(host_list_raw, list):
            host_list = [str(h.get("host", "")) for h in host_list_raw if isinstance(h, dict) and h.get("host")]
        if not host_list:
            logger.warning("[B站直播]getDanmuInfo 无可用 host")
            return None
        server_host = host_list[0]
    except Exception as e:
        logger.warning(f"[B站直播]getDanmuInfo 失败: {type(e).__name__}: {e}")
        return None

    return {
        "room_id": int(real_room_id) if str(real_room_id).isdigit() else real_room_id,
        "uid": uid,
        "token": token,
        "server_host": server_host,
        "host_list": host_list,
        "buvid": buvid,
        "cookie": cookies or "",
    }


@trace_error_decorator
async def get_xhs_stream_url(
    url: str, proxy_addr: OptionalStr = None, cookies: OptionalStr = None
) -> dict[str, object]:
    # 获取小红书直播流地址
    # 解析链路：xhslink 短链先解重定向 → 抠 host_id/user_id → __INITIAL_STATE__（undefined 替换 null 后解析）；
    # 返回 is_live + flv/m3u8 + record_url；标题含「回放」视为非实时不取流；未开播仍回抠到的 anchor_name。
    headers = {
        "User-Agent": "ios/7.830 (ios 17.0; ; iPhone 15 (A2846/A3089/A3090/A3092))",
        # xy-common-params 是 XHS 固定内置的「平台+会话」头，sid 是一段写死的 session 串，
        # app 端接口以此头鉴权，缺省会被拒；不要随意改写该值。
        "xy-common-params": "platform=iOS&sid=session.1722166379345546829388",
        "referer": "https://app.xhs.cn/",
    }
    # 调用方透传 cookie 时优先采用；否则走游客态/自动获取凭据（各平台未登录态取流能力不一，部分更易被风控）
    if cookies:
        headers["Cookie"] = cookies

    # xhslink.com 是分享短链，需先解析出真实落地页 URL 再继续（redirect_url=True 取最终地址）。
    if "xhslink.com" in url:
        url_result = await async_req(url, proxy_addr=proxy_addr, headers=headers, redirect_url=True)
        if isinstance(url_result, str):
            url = url_result

    host_id = get_params(url, "host_id")
    user_id_match = re.search("/user/profile/(.*?)(?=/|\\?|$)", url)
    user_id = user_id_match.group(1) if user_id_match else host_id
    result: dict[str, object] = {"anchor_name": "", "is_live": False}
    html_str = await async_req(url, proxy_addr=proxy_addr, headers=headers)
    html_str = _get_str_response(html_str)
    # 内联 __INITIAL_STATE__ 里混有 JS 的 undefined（非法 JSON 字面量），先替换为 null 再解析。
    match_data = re.search("<script>window.__INITIAL_STATE__=(.*?)</script>", html_str)

    if match_data:
        json_str = match_data.group(1).replace("undefined", "null")
        json_data = json.loads(json_str)

        if json_data.get("liveStream"):
            stream_data = json_data["liveStream"]
            # liveStatus=="success" 才是开播；标题含「回放」视为非实时直播，跳过取流。
            if stream_data.get("liveStatus") == "success":
                room_info = stream_data["roomData"]["roomInfo"]
                title = room_info.get("roomTitle")
                if title and "回放" not in title:
                    live_link = room_info["deeplink"]
                    anchor_name = get_params(live_link, "host_nickname")
                    flv_url = get_params(live_link, "flvUrl")
                    if not flv_url:
                        raise RuntimeError("Failed to get flvUrl")
                    room_id_match = re.search(r"live/([^./?]+)", flv_url)
                    if not room_id_match:
                        raise RuntimeError("Failed to extract room_id from flvUrl")
                    room_id = room_id_match.group(1)
                    # 不用 deeplink 里的签名 flvUrl（易过期），改用稳定的 CDN host 按 room_id 重建，
                    # 实测该 host 直拼 room_id 即可持续拉流；m3u8 由 flv 替换后缀得到。
                    flv_url = f"http://live-source-play.xhscdn.com/live/{room_id}.flv"
                    m3u8_url = flv_url.replace(".flv", ".m3u8")
                    result |= {
                        "anchor_name": anchor_name,
                        "is_live": True,
                        "title": title,
                        "flv_url": flv_url,
                        "m3u8_url": m3u8_url,
                        "record_url": flv_url,
                    }
                    return result

    # 内联状态未命中直播（未开播/分享页无 liveStream）时，退到用户主页仅补全 anchor_name，
    # 不影响录制判定（is_live 保持 False）；http 直链里抠不到昵称则留空返回。
    profile_url = f"https://www.xiaohongshu.com/user/profile/{user_id}"
    html_str = await async_req(profile_url, proxy_addr=proxy_addr, headers=headers)
    html_str = _get_str_response(html_str)
    anchor_name_match = re.search("<title>@(.*?) 的个人主页</title>", html_str)
    if anchor_name_match:
        result["anchor_name"] = anchor_name_match.group(1)

    return result


@trace_error_decorator
async def get_bigo_stream_url(
    url: str, proxy_addr: OptionalStr = None, cookies: OptionalStr = None
) -> dict[str, object]:
    # 获取 bigo 直播流地址
    # 解析链路：非 bigo.tv 域名先从 og:web:url 取真实地址再抠 &h=room_id；getInternalStudioInfo 对游客开放；
    # alive==1 取 hls_src（同时作 m3u8 与 record_url，仅 HLS 一路）；未开播且昵称空才回抓房间页补名。
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:148.0) Gecko/20100101 Firefox/148.0",
        "Accept-Language": "zh-CN,zh;q=0.8,zh-TW;q=0.7,zh-HK;q=0.5,en-US;q=0.3,en;q=0.2",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "Referer": "https://www.bigo.tv/",
    }
    # 调用方透传 cookie 时优先采用；否则走游客态/自动获取凭据（各平台未登录态取流能力不一，部分更易被风控）
    if cookies:
        headers["Cookie"] = cookies

    # 非 bigo.tv 域名（分享/第三方落地页）要先从 og meta 的 web:url 取真实地址，
    # 再从 &h= 截出 room_id；bigo.tv 直链则直接取 &h= 或路径末段作为 room_id。
    if "bigo.tv" not in url:
        html_str = await async_req(url, proxy_addr=proxy_addr, headers=headers)
        html_str = _get_str_response(html_str)
        web_url_match = re.search(
            '<meta data-n-head="ssr" data-hid="al:web:url" property="al:web:url" content="(.*?)">', html_str
        )
        if not web_url_match:
            raise ValueError("Failed to find web url")
        web_url = web_url_match.group(1)
        room_id = web_url.split("&amp;h=")[-1]
    else:
        if "&h=" in url:
            room_id = url.split("&h=")[-1]
        else:
            room_id = url.split("?")[0].rsplit("/", maxsplit=1)[-1]

    # 以 siteId 键提交 room_id 到内部接口拿直播间信息；该接口对游客开放，不强制登录。
    data = {"siteId": room_id}  # roomId
    url2 = "https://ta.bigo.tv/official_website/studio/getInternalStudioInfo"
    json_str = await async_req(url=url2, proxy_addr=proxy_addr, headers=headers, data=data)
    json_str = _get_str_response(json_str)
    json_data = json.loads(json_str)
    anchor_name = json_data["data"]["nick_name"]
    live_status = json_data["data"]["alive"]
    result: dict[str, object] = {"anchor_name": anchor_name, "is_live": False}

    # alive==1 才是开播；hls_src 同时作为 m3u8 与 record_url（bigo 仅 HLS 一路）。
    if live_status == 1:
        live_title = json_data["data"]["roomTopic"]
        m3u8_url = json_data["data"]["hls_src"]
        result["m3u8_url"] = m3u8_url
        result["record_url"] = m3u8_url
        result |= {"title": live_title, "is_live": True, "m3u8_url": m3u8_url, "record_url": m3u8_url}
    # 未开播且接口没返回昵称时，退回抓房间页从 <title>/og:title 抠主播名（仅补全信息，不影响录制判定）。
    elif result["anchor_name"] == "":
        html_str = await async_req(
            url=f'https://www.bigo.tv/{url.split("/")[3]}/{room_id}', proxy_addr=proxy_addr, headers=headers
        )
        html_str = _get_str_response(html_str)
        match_anchor_name = re.search("<title>欢迎来到(.*?)的直播间</title>", html_str, re.DOTALL)
        if match_anchor_name:
            anchor_name = match_anchor_name.group(1)
        else:
            match_anchor_name = re.search(
                '<meta data-n-head="ssr" data-hid="og:title" property="og:title" ' 'content="(.*?) - BIGO LIVE">',
                html_str,
                re.DOTALL,
            )
            anchor_name = match_anchor_name.group(1) if match_anchor_name else ""
        result["anchor_name"] = anchor_name

    return result


@trace_error_decorator
async def get_blued_stream_url(
    url: str, proxy_addr: OptionalStr = None, cookies: OptionalStr = None
) -> dict[str, object]:
    # 获取 blued 直播流地址
    # 页面内联串经 decodeURIComponent 还原（URL 编码的 JSON）；onLive 为真才含 liveInfo，
    # 故 liveUrl 同时作为 m3u8 与 record_url（blued 仅单路 HLS），未开播时不取流。
    headers = {
        "User-Agent": "ios/7.830 (ios 17.0; ; iPhone 15 (A2846/A3089/A3090/A3092))",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.8,zh-TW;q=0.7,zh-HK;q=0.5,en-US;q=0.3,en;q=0.2",
    }
    # 调用方透传 cookie 时优先采用；否则走游客态/自动获取凭据（各平台未登录态取流能力不一，部分更易被风控）
    if cookies:
        headers["Cookie"] = cookies

    html_str = await async_req(url=url, proxy_addr=proxy_addr, headers=headers)
    html_str = _get_str_response(html_str)
    json_str_match = re.search('decodeURIComponent\\("(.*?)"\\)\\),window\\.Promise', html_str, re.DOTALL)
    if not json_str_match:
        raise ValueError("Failed to find json string")
    json_str = json_str_match.group(1)
    json_str = urllib.parse.unquote(json_str)
    json_data = json.loads(json_str)
    anchor_name = json_data["userInfo"]["name"]
    live_status = json_data["userInfo"]["onLive"]
    result: dict[str, object] = {"anchor_name": anchor_name, "is_live": False}

    if live_status:
        m3u8_url = json_data["liveInfo"]["liveUrl"]
        result |= {"is_live": True, "m3u8_url": m3u8_url, "record_url": m3u8_url}
    return result


@trace_error_decorator_or_none
async def login_sooplive(username: str, password: str, proxy_addr: OptionalStr = None) -> OptionalStr:
    # SOOP(原AfreecaTV) 平台登录获取认证 Cookie
    # 返回 cookie 字符串（OptionalStr）或抛错；账号/密码长度不足直接抛 RuntimeError，
    # 不发起请求（避免无意义的登录尝试）；后续 get_sooplive_stream_data 用该 cookie 鉴权。
    if len(username) < 6 or len(password) < 10:
        raise RuntimeError(
            "sooplive login failed! Please enter the correct account and password for the sooplive "
            "platform in the config.ini file."
        )

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:148.0) Gecko/20100101 Firefox/148.0",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "Origin": "https://play.sooplive.co.kr",
        "Referer": "https://play.sooplive.co.kr/superbsw123/277837074",
    }

    data = {
        "szWork": "login",
        "szType": "json",
        "szUid": username,
        "szPassword": password,
        "isSaveId": "true",
        "isSavePw": "true",
        "isSaveJoin": "true",
        "isLoginRetain": "Y",
    }

    url = "https://login.sooplive.co.kr/app/LoginAction.php"

    try:
        cookie_result = await async_req(
            url, proxy_addr=proxy_addr, headers=headers, data=data, return_cookies=True, timeout=20
        )
        if isinstance(cookie_result, dict):
            cookie_dict = cookie_result
        elif isinstance(cookie_result, tuple) and len(cookie_result) == 2 and isinstance(cookie_result[1], dict):
            cookie_dict = cookie_result[1]
        else:
            raise RuntimeError("Failed to get cookies from login response")
        cookie_str = "; ".join([f"{k}={v}" for k, v in cookie_dict.items()])
        return cookie_str
    except Exception as e:
        print(f"An error occurred during login: {e}")
        raise Exception(
            "sooplive login failed, please check if the account password in the configuration file is correct."
        )


@trace_error_decorator
async def get_sooplive_cdn_url(
    broad_no: str, proxy_addr: OptionalStr = None, cookies: OptionalStr = None
) -> dict[str, object]:
    # 获取 SOOP(原AfreecaTV) 平台 CDN 流地址
    # 返回接口原始 json（含 CDN 候选列表），由调用方解析；abroad=True 不可省——
    # 该分配接口走境外域名 livestream-manager.sooplive.co.kr，不走代理会直连超时。
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:148.0) Gecko/20100101 Firefox/148.0",
        "Accept-Language": "zh-CN,zh;q=0.8,zh-TW;q=0.7,zh-HK;q=0.5,en-US;q=0.3,en;q=0.2",
        "Origin": "https://play.sooplive.co.kr",
        "Referer": "https://play.sooplive.co.kr/oul282/249469582",
        "Content-Type": "application/x-www-form-urlencoded",
    }
    # 调用方透传 cookie 时优先采用；否则走游客态/自动获取凭据（各平台未登录态取流能力不一，部分更易被风控）
    if cookies:
        headers["Cookie"] = cookies

    params = {
        "return_type": "gcp_cdn",
        "use_cors": "false",
        "cors_origin_url": "play.sooplive.co.kr",
        # broad_key 用 "{broad_no}-common-master-hls" 固定后缀指定主线路 HLS；
        # time 是写死的时间戳（服务端不校验其真伪，仅作为防重放字段占位），改不动即可。
        "broad_key": f"{broad_no}-common-master-hls",
        "time": "8361.086329376785",
    }

    # abroad=True：SOOP CDN 分配接口走境外域名，必须走与解析阶段相同的代理，否则直连超时。
    url2 = "http://livestream-manager.sooplive.co.kr/broad_stream_assign.html?" + urllib.parse.urlencode(params)
    json_str = await async_req(url=url2, proxy_addr=proxy_addr, headers=headers, abroad=True)
    json_str = _get_str_response(json_str)
    json_data = json.loads(json_str)

    return cast(dict[str, object], json_data)


@trace_error_decorator_or_none
async def get_sooplive_tk(
    url: str, rtype: str, proxy_addr: OptionalStr = None, cookies: OptionalStr = None
) -> str | tuple[str, str]:
    # 获取 SOOP(原AfreecaTV) 平台临时访问 token
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:148.0) Gecko/20100101 Firefox/148.0",
        "Origin": "https://play.sooplive.co.kr",
        "Referer": "https://play.sooplive.co.kr/secretx/250989857",
        "Content-Type": "application/x-www-form-urlencoded",
    }

    # 调用方透传 cookie 时优先采用；否则走游客态/自动获取凭据（各平台未登录态取流能力不一，部分更易被风控）
    if cookies:
        headers["Cookie"] = cookies

    split_url = url.split("/")
    # SOOP 房间 URL 两种形态：短链/分享链（段数<6，如 /{bj}/...）取 [3]；完整 play 链接
    # （段数≥6，如 /play/sooplive/.../{bj}/...）取 [5]。取错段会得到非 bjid、tk 接口直接 404。
    bj_id = split_url[3] if len(split_url) < 6 else split_url[5]
    room_password = get_params(url, "pwd")
    if not room_password:
        room_password = ""
    data = {
        "bid": bj_id,
        "bno": "",
        "type": rtype,
        "pwd": room_password,
        "player_type": "html5",
        "stream_type": "common",
        "quality": "master",
        "mode": "landing",
        "from_api": "0",
        "is_revive": "false",
    }

    url2 = f"https://live.sooplive.co.kr/afreeca/player_live_api.php?bjid={bj_id}"
    json_str = await async_req(url=url2, proxy_addr=proxy_addr, headers=headers, data=data, abroad=True)
    json_str = _get_str_response(json_str)
    json_data = json.loads(json_str)

    if rtype == "aid":
        token = json_data["CHANNEL"]["AID"]
        return cast(str, token)
    else:
        bj_name = json_data["CHANNEL"]["BJNICK"]
        bj_id = json_data["CHANNEL"]["BJID"]
        return f"{bj_name}-{bj_id}", cast(str, json_data["CHANNEL"]["BNO"])


def get_soop_headers(cookies: OptionalStr = None) -> dict[str, str]:
    # 构造 SOOP(原AfreecaTV) 平台请求头
    # client-id 每次调用随机生成（抗重放/会话隔离）；返回的字典供 _get_soop_*_global 复用同一套头，
    # 保证频道/流信息两次请求头一致，否则 SOOP 可能按不一致 client-id 拒绝。
    headers = {
        "client-id": str(uuid.uuid4()),
        "user-agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 18_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, "
        "like Gecko) Version/18.5 Mobile/15E148 Safari/604.1 Edg/141.0.0.0",
    }
    # 调用方透传 cookie 时优先采用；否则走游客态/自动获取凭据（各平台未登录态取流能力不一，部分更易被风控）
    if cookies:
        headers["cookie"] = cookies
    return headers


async def _get_soop_channel_info_global(bj_id: str, proxy_addr: OptionalStr = None, cookies: OptionalStr = None) -> str:
    # 获取 SOOP(原AfreecaTV) 频道信息（内部通用方法）
    # 返回 "nickname-channelId" 复合串作为房间 key：频道号 bj_id 非稳定房间标识，
    # 用昵称+频道号唯一化，避免不同主播复用同一 bj_id 时录制串台。
    headers = get_soop_headers(cookies)
    api = "https://api.sooplive.com/v2/channel/info/" + str(bj_id)
    json_str = await async_req(api, proxy_addr=proxy_addr, headers=headers)
    json_str = _get_str_response(json_str)
    json_data = json.loads(json_str)
    nickname = json_data["data"]["streamerChannelInfo"]["nickname"]
    channelId = json_data["data"]["streamerChannelInfo"]["channelId"]
    anchor_name = f"{nickname}-{channelId}"
    return anchor_name


async def _get_soop_stream_info_global(
    bj_id: str, proxy_addr: OptionalStr = None, cookies: OptionalStr = None
) -> tuple[bool, str]:
    # 获取 SOOP(原AfreecaTV) 直播流信息（内部通用方法）
    # 返回 (isStream, title)；isStream 为真即开播，直接驱动 get_sooplive_stream_data 的 is_live 判定，
    # 标题用于录制文件名；接口对游客开放、无需登录 cookie。
    headers = get_soop_headers(cookies)
    api = "https://api.sooplive.com/v2/stream/info/" + str(bj_id)
    json_str = await async_req(api, proxy_addr=proxy_addr, headers=headers)
    json_str = _get_str_response(json_str)
    json_data = json.loads(json_str)
    status = json_data["data"]["isStream"]
    title = json_data["data"]["title"]
    return status, title


async def _fetch_web_stream_data_global(
    url: str, proxy_addr: OptionalStr = None, cookies: OptionalStr = None
) -> dict[str, object]:
    # 抓取 Web 端直播流数据（内部通用方法）
    split_url = url.split("/")
    bj_id = split_url[3] if len(split_url) < 6 else split_url[5]
    anchor_name = await _get_soop_channel_info_global(bj_id, proxy_addr=proxy_addr, cookies=cookies)
    result: dict[str, object] = {"anchor_name": anchor_name or "", "is_live": False, "live_url": url}
    status, title = await _get_soop_stream_info_global(bj_id, proxy_addr=proxy_addr, cookies=cookies)
    if not status:
        return result
    else:

        async def _get_url_list(m3u8: str) -> list[str]:
            # 从直播流数据中提取 URL 列表（内部方法）
            # m3u8 内相对路径（非 # 开头）需拼回 url_prefix（域名前三段），否则 ffmpeg 取到相对地址无法拉流；
            # 未匹配到带宽的 URL 排序时置 0 兜底，避免 KeyError 导致整轮取流失败。
            headers = {
                "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/141.0.0.0 Safari/537.36 Edg/141.0.0.0",
            }
            if cookies:
                headers["cookie"] = cookies
            resp = await async_req(url=m3u8, proxy_addr=proxy_addr, headers=headers)
            resp = _get_str_response(resp)
            play_url_list = []
            url_prefix = "/".join(m3u8.split("/")[0:3])
            for i in resp.split("\n"):
                if not i.startswith("#") and i.strip():
                    play_url_list.append(url_prefix + i.strip())
            bandwidth_pattern = _BANDWIDTH_PATTERN
            bandwidth_list = bandwidth_pattern.findall(resp)
            url_to_bandwidth = {purl: int(bandwidth) for bandwidth, purl in zip(bandwidth_list, play_url_list)}
            # 未匹配到带宽的 URL 置 0，避免排序时 KeyError
            play_url_list = sorted(play_url_list, key=lambda purl: url_to_bandwidth.get(purl, 0), reverse=True)
            return play_url_list

        m3u8_url = "https://global-media.sooplive.com/live/" + bj_id + "/master.m3u8"
        result |= {
            "is_live": True,
            "title": title,
            "m3u8_url": m3u8_url,
            "play_url_list": await _get_url_list(m3u8_url),
        }
    return result


@trace_error_decorator
async def get_sooplive_stream_data(
    url: str,
    proxy_addr: OptionalStr = None,
    cookies: OptionalStr = None,
    username: OptionalStr = None,
    password: OptionalStr = None,
) -> dict[str, object]:
    # 获取 SOOP(原AfreecaTV) 平台直播流数据
    # 解析链路：先 _get_soop_channel_info_global 拿 bj_id，再 _get_soop_stream_info_global 取流；
    # 返回 is_live + m3u8；账号受限/未开播统一走 get_sooplive_cdn_url 兜底，失败抛错由装饰器重试。
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:148.0) Gecko/20100101 Firefox/148.0",
        "Accept-Language": "zh-CN,zh;q=0.8,zh-TW;q=0.7,zh-HK;q=0.5,en-US;q=0.3,en;q=0.2",
        "Referer": "https://m.sooplive.co.kr/",
        "Content-Type": "application/x-www-form-urlencoded",
    }
    # 调用方透传 cookie 时优先采用；否则走游客态/自动获取凭据（各平台未登录态取流能力不一，部分更易被风控）
    if cookies:
        headers["Cookie"] = cookies

    if "sooplive.com" in url:
        return await _fetch_web_stream_data_global(url, proxy_addr, cookies)

    split_url = url.split("/")
    bj_id = split_url[3] if len(split_url) < 6 else split_url[5]

    data = {
        "bj_id": bj_id,
        "broad_no": "",
        "agent": "web",
        "confirm_adult": "true",
        "player_type": "webm",
        "mode": "live",
    }

    url2 = "http://api.m.sooplive.co.kr/broad/a/watch"

    json_str = await async_req(url=url2, proxy_addr=proxy_addr, headers=headers, data=data, abroad=True)
    json_str = _get_str_response(json_str)
    json_data = json.loads(json_str)

    # 公开直播间接口才会在 data 里带 user_nick；bj_id 后缀用于唯一标识房间
    # （不同主播可能复用同一 bj_id 段，加昵称前缀避免录制串台）。无 user_nick 视为
    # 受限/未公开房间，anchor_name 留空走下方登录或报错分支。
    if "user_nick" in json_data["data"]:
        anchor_name = json_data["data"]["user_nick"]
        if "bj_id" in json_data["data"]:
            anchor_name = f"{anchor_name}-{json_data['data']['bj_id']}"
    else:
        anchor_name = ""

    result: dict[str, object] = {"anchor_name": anchor_name or "", "is_live": False}

    async def get_url_list(m3u8: str) -> list[str]:
        # 解析直播流响应并返回 URL 列表
        resp = await async_req(url=m3u8, proxy_addr=proxy_addr, headers=headers, abroad=True)
        resp = _get_str_response(resp)
        play_url_list = []
        url_prefix = m3u8.rsplit("/", maxsplit=1)[0] + "/"
        for i in resp.split("\n"):
            if i.startswith("auth_playlist"):
                play_url_list.append(url_prefix + i.strip())
        bandwidth_pattern = _BANDWIDTH_PATTERN
        bandwidth_list = bandwidth_pattern.findall(resp)
        url_to_bandwidth = {purl: int(bandwidth) for bandwidth, purl in zip(bandwidth_list, play_url_list)}
        play_url_list = sorted(play_url_list, key=lambda purl: url_to_bandwidth[purl], reverse=True)
        return play_url_list

    # anchor_name 为空说明接口未返回公开直播间信息（成人房/未登录/房间异常），需按 data.code
    # 进入登录或报错分支；guest 仅能拿公开房，下面各 code 是 SOOP 网关的状态语义。
    if not anchor_name:

        async def handle_login() -> OptionalStr:
            # 处理平台登录认证
            cookie = await login_sooplive(cast(str, username), cast(str, password), proxy_addr=proxy_addr)
            if cookie and "AuthTicket=" in cookie:
                print("sooplive platform login successful! Starting to fetch live streaming data...")
                return cookie
            return None

        async def fetch_data(cookie: str, _result: dict[str, object]) -> dict[str, object]:
            # 抓取直播数据
            aid_token = await get_sooplive_tk(url, rtype="aid", proxy_addr=proxy_addr, cookies=cookie)
            _info = await get_sooplive_tk(url, rtype="info", proxy_addr=proxy_addr, cookies=cookie)
            if isinstance(_info, tuple) and len(_info) == 2:
                _anchor_name, _broad_no = _info
            else:
                raise RuntimeError("Failed to get sooplive info")
            _view_url_data = await get_sooplive_cdn_url(_broad_no, proxy_addr=proxy_addr)
            _view_url = cast(str, _view_url_data.get("view_url", ""))
            _m3u8_url = _view_url + "?aid=" + cast(str, aid_token)
            _result |= {
                "anchor_name": _anchor_name,
                "is_live": True,
                "m3u8_url": _m3u8_url,
                "play_url_list": await get_url_list(_m3u8_url),
                "new_cookies": cookie,
            }
            return _result

        # SOOP 网关错误码：-3001 直播刚结束；-3002 成人房需 19+ 登录；-3004 需登录态 cookie；
        # -6001 房间地址错误。-3002/-3004 都触发登录流程（-3004 优先复用已传入 cookie，避免重复登录）。
        if json_data["data"]["code"] == -3001:
            print("sooplive live stream failed to retrieve, the live stream just ended.")
            return result

        elif json_data["data"]["code"] == -3002:
            print("sooplive live stream retrieval failed, the live needs 19+, you are not logged in.")
            print(
                "Attempting to log in to the sooplive live streaming platform with your account and password, "
                "please ensure it is configured."
            )
            new_cookie = await handle_login()
            if new_cookie and len(new_cookie) > 0:
                return await fetch_data(new_cookie, result)
            raise RuntimeError("sooplive login failed, please check if the account and password are correct")

        elif json_data["data"]["code"] == -3004:
            if cookies and len(cookies) > 0:
                return await fetch_data(cookies, result)
            else:
                raise RuntimeError("sooplive login failed, please check if the account and password are correct")
        elif json_data["data"]["code"] == -6001:
            print("error message：Please check if the input sooplive live room address " "is correct.")
            return result
    # result==1 且已有 anchor_name：公开可观看的直播间。hls_authentication_key 即 CDN 的 aid 票据，
    # 必须作为 ?aid= 拼到 m3u8 地址后，缺失该票据 CDN 会直接 403（同样的票据也用于登录态的 AID）。
    if json_data["result"] == 1 and anchor_name:
        broad_no = json_data["data"]["broad_no"]
        hls_authentication_key = json_data["data"]["hls_authentication_key"]
        view_url_data = await get_sooplive_cdn_url(cast(str, broad_no), proxy_addr=proxy_addr)
        view_url = cast(str, view_url_data.get("view_url", ""))
        m3u8_url = view_url + "?aid=" + cast(str, hls_authentication_key)
        result |= {"is_live": True, "m3u8_url": m3u8_url, "play_url_list": await get_url_list(m3u8_url)}
    # 仅在未通过登录获取新 cookie 时置 None，避免覆盖 fetch_data 中设置的 cookie
    result.setdefault("new_cookies", None)
    return result


@trace_error_decorator
async def get_netease_stream_data(
    url: str, proxy_addr: OptionalStr = None, cookies: OptionalStr = None
) -> dict[str, object]:
    # 获取网易 CC 直播流数据
    # 解析链路：抓 __NEXT_DATA__ 内联 JSON → roomInfoInitData；status==1 才取流；
    # 返回 is_live + m3u8 + stream_list（quickplay 清晰度列表）；sharefile/quickplay 缺失按无源不报错。
    headers = {
        "accept": "application/json, text/plain, */*",
        "accept-language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
        "referer": "https://cc.163.com/",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:148.0) Gecko/20100101 Firefox/148.0",
    }
    # 调用方透传 cookie 时优先采用；否则走游客态/自动获取凭据（各平台未登录态取流能力不一，部分更易被风控）
    if cookies:
        headers["Cookie"] = cookies
    # 规整 URL 结尾斜杠，保证后续正则/接口参数拼接稳定
    url = url + "/" if url[-1] != "/" else url

    html_str = await async_req(url=url, proxy_addr=proxy_addr, headers=headers)
    html_str = _get_str_response(html_str)
    json_str_match = re.search(
        '<script id="__NEXT_DATA__" .* crossorigin="anonymous">(.*?)</script></body>', html_str, re.DOTALL
    )
    # __NEXT_DATA__ 缺失即页面结构变化，显式报错而非后续 KeyError
    if not json_str_match:
        raise ValueError("Failed to find __NEXT_DATA__")
    json_str = json_str_match.group(1)
    json_data = json.loads(json_str)
    room_data = json_data["props"]["pageProps"]["roomInfoInitData"]
    live_data = room_data["live"]
    result: dict[str, object] = {"is_live": False}
    # 网易 CC 用 status==1 表示开播（0/2 为未播/轮播），只有开播才取流；
    # sharefile 即 m3u8 地址、quickplay 为清晰度列表，缺失时上游按无源处理、不报错。
    live_status = live_data.get("status") == 1
    result["anchor_name"] = live_data.get("nickname", room_data.get("nickname"))
    if live_status:
        result |= {
            "is_live": True,
            "title": live_data["title"],
            "stream_list": live_data.get("quickplay"),
            "m3u8_url": live_data.get("sharefile"),
        }
    return result


@trace_error_decorator
async def get_qiandurebo_stream_data(
    url: str, proxy_addr: OptionalStr = None, cookies: OptionalStr = None
) -> dict[str, object]:
    # 获取千度热播直播流数据
    # 解析链路：抓页面 var user 内联串 → 抠 zb_nickname/play_url；含「未开播占位提示」即视为未开播；
    # 返回 is_live + flv + record_url；play_url 缺失直接回未开播，不抛错（装饰器按未开播空转重试）。
    headers = {
        "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8,"
        "application/signed-exchange;v=b3;q=0.7",
        "accept-language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
        "referer": "https://qiandurebo.com/web/index.php",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:148.0) Gecko/20100101 Firefox/148.0",
    }
    # 调用方透传 cookie 时优先采用；否则走游客态/自动获取凭据（各平台未登录态取流能力不一，部分更易被风控）
    if cookies:
        headers["Cookie"] = cookies

    html_str = await async_req(url=url, proxy_addr=proxy_addr, headers=headers)
    html_str = _get_str_response(html_str)
    data_match = re.search("var user = (.*?)\r\n\\s+user\\.play_url", html_str, re.DOTALL)
    if not data_match:
        return {"anchor_name": "", "is_live": False}
    data = data_match.group(1)
    anchor_name = re.findall('"zb_nickname": "(.*?)",\r\n', data)

    result: dict[str, object] = {"anchor_name": "", "is_live": False}
    if len(anchor_name) > 0:
        result["anchor_name"] = anchor_name[0]
        play_url = re.findall('"play_url": "(.*?)",\r\n', data)

        # 离线/被封房间页会渲染 `common-text-center" style="display:block` 的占位提示，
        # 此串存在即视为未开播，避免把占位页里抽到的空 play_url 当成有效流录制。
        if len(play_url) > 0 and 'common-text-center" style="display:block' not in html_str:
            result |= {
                "anchor_name": anchor_name[0],
                "is_live": True,
                "flv_url": play_url[0],
                "record_url": play_url[0],
            }
    return result


@trace_error_decorator
async def get_pandatv_stream_data(
    url: str, proxy_addr: OptionalStr = None, cookies: OptionalStr = None
) -> dict[str, object]:
    # 获取 PandaTV 直播流数据
    # 解析链路：member/bj 拿主播信息 + media 是否在播字段 → 在播才请求 live/play 拿 HLS；
    # 返回 is_live + m3u8 + play_url_list；errorData.needAdult 表示成人房需登录 cookie，其它 code 原样抛错。
    headers = {
        "origin": "https://www.pandalive.co.kr",
        "referer": "https://www.pandalive.co.kr/",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:148.0) Gecko/20100101 Firefox/148.0",
    }
    # 调用方透传 cookie 时优先采用；否则走游客态/自动获取凭据（各平台未登录态取流能力不一，部分更易被风控）
    if cookies:
        headers["Cookie"] = cookies

    user_id = _safe_extract_id(url)
    url2 = "https://api.pandalive.co.kr/v1/live/play"
    data = {
        "userId": user_id,
        "info": "media fanGrade",
    }
    room_password = get_params(url, "pwd")
    if not room_password:
        room_password = ""
    data2 = {
        "action": "watch",
        "userId": user_id,
        "password": room_password,
        "shareLinkType": "",
    }

    result: dict[str, object] = {"anchor_name": "", "is_live": False}
    json_str = await async_req(
        "https://api.pandalive.co.kr/v1/member/bj", proxy_addr=proxy_addr, headers=headers, data=data, abroad=True
    )
    json_str = _get_str_response(json_str)
    json_data = json.loads(json_str)
    if "bjInfo" not in json_data:
        raise RuntimeError(json_data.get("message", "Unknown error"))
    anchor_id = json_data["bjInfo"]["id"]
    anchor_name = f"{json_data['bjInfo']['nick']}-{anchor_id}"
    result["anchor_name"] = anchor_name
    # PandaTV 用 "media" 字段是否存在来表示是否在播：有 media 才是开播态，否则只是离线主播页。
    live_status = "media" in json_data

    if live_status:
        json_str = await async_req(url2, proxy_addr=proxy_addr, headers=headers, data=data2, abroad=True)
        json_str = _get_str_response(json_str)
        json_data = json.loads(json_str)
        # errorData 出现表示观看受限：needAdult 是成人房需登录态 cookie；其它 code 原样抛出。
        if "errorData" in json_data:
            if json_data["errorData"]["code"] == "needAdult":
                raise RuntimeError(
                    f"{url} The live room requires login and is only accessible to adults. Please "
                    f"correctly fill in the login cookie in the configuration file."
                )
            else:
                raise RuntimeError(json_data["errorData"]["code"], json_data["message"])
        play_url = json_data["PlayList"]["hls"][0]["url"]
        play_url_list = await get_play_url_list(m3u8=play_url, proxy=proxy_addr, header=headers, abroad=True)
        result |= {"is_live": True, "m3u8_url": play_url, "play_url_list": play_url_list}
    return result


@trace_error_decorator
async def get_maoerfm_stream_url(
    url: str, proxy_addr: OptionalStr = None, cookies: OptionalStr = None
) -> dict[str, object]:
    # 获取猫耳 FM 直播流地址
    # 解析链路：api/v2/live/{room_id} 直取；room 字段存在且 broadcasting 为真才取流；
    # 返回 is_live + m3u8 + flv + record_url；无 room 字段按未开播返回，不抛错。
    headers = {
        "accept": "application/json, text/plain, */*",
        "accept-language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
        "referer": "https://fm.missevan.com/live/868895007",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:148.0) Gecko/20100101 Firefox/148.0",
    }
    # 调用方透传 cookie 时优先采用；否则走游客态/自动获取凭据（各平台未登录态取流能力不一，部分更易被风控）
    if cookies:
        headers["Cookie"] = cookies

    room_id = _safe_extract_id(url)
    url2 = f"https://fm.missevan.com/api/v2/live/{room_id}"

    json_str = await async_req(url=url2, proxy_addr=proxy_addr, headers=headers)
    json_str = _get_str_response(json_str)
    json_data = json.loads(json_str)

    anchor_name = json_data["info"]["creator"]["username"]
    live_status = False
    # room 字段缺失表示离线主播页（无 broadcasting 标记），live_status 保持 False
    if "room" in json_data["info"]:
        live_status = json_data["info"]["room"]["status"]["broadcasting"]

    result: dict[str, object] = {"anchor_name": anchor_name, "is_live": live_status}
    if live_status:
        stream_list = json_data["info"]["room"]["channel"]
        m3u8_url = stream_list["hls_pull_url"]
        flv_url = stream_list["flv_pull_url"]
        title = json_data["info"]["room"]["name"]
        result |= {"is_live": True, "title": title, "m3u8_url": m3u8_url, "flv_url": flv_url, "record_url": flv_url}
    return result


@trace_error_decorator_or_none
async def get_winktv_bj_info(
    url: str, proxy_addr: OptionalStr = None, cookies: OptionalStr = None
) -> tuple[str, object]:
    # 获取 WinkTV 主播信息
    # 返回 (anchor_name, live_status) 二元组供 get_winktv_stream_data 复用，避免重复抓 bj 接口；
    # live_status 由响应是否含 "media" 字段判定（有 media 才在播），anchor_id 取自 bjInfo
    # 用于后续 watch 接口鉴权，缺它会被服务端按「未授权观看」拒绝。
    headers = {
        "accept": "application/json, text/plain, */*",
        "accept-language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
        "content-type": "application/x-www-form-urlencoded",
        "referer": "https://www.winktv.co.kr/",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:148.0) Gecko/20100101 Firefox/148.0",
    }
    # 调用方透传 cookie 时优先采用；否则走游客态/自动获取凭据（各平台未登录态取流能力不一，部分更易被风控）
    if cookies:
        headers["Cookie"] = cookies
    user_id = url.split("?")[0].rsplit("/", maxsplit=1)[-1]
    data = {
        "userId": user_id,
        "info": "media",
    }

    info_api = "https://api.winktv.co.kr/v1/member/bj"
    json_str = await async_req(url=info_api, proxy_addr=proxy_addr, headers=headers, data=data, abroad=True)
    json_str = _get_str_response(json_str)
    json_data = json.loads(json_str)
    live_status = "media" in json_data
    anchor_id = json_data["bjInfo"]["id"]
    anchor_name = f"{json_data['bjInfo']['nick']}-{anchor_id}"
    return anchor_name, live_status


@trace_error_decorator
async def get_winktv_stream_data(
    url: str, proxy_addr: OptionalStr = None, cookies: OptionalStr = None
) -> dict[str, object]:
    # 获取 WinkTV 直播流数据
    # 解析链路：get_winktv_bj_info 拿 (anchor_name, live_status) → 在播才请求 play/cdn 拿 HLS；
    # 返回 is_live + m3u8 + play_url_list；live_status 由响应是否含 media 字段判定，无 media 即离线。
    headers = {
        "accept": "application/json, text/plain, */*",
        "accept-language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
        "content-type": "application/x-www-form-urlencoded",
        "referer": "https://www.winktv.co.kr",
        "origin": "https://www.winktv.co.kr",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:148.0) Gecko/20100101 Firefox/148.0",
    }
    # 调用方透传 cookie 时优先采用；否则走游客态/自动获取凭据（各平台未登录态取流能力不一，部分更易被风控）
    if cookies:
        headers["Cookie"] = cookies
    user_id = url.split("?")[0].rsplit("/", maxsplit=1)[-1]
    room_password = get_params(url, "pwd")
    if not room_password:
        room_password = ""
    data = {
        "action": "watch",
        "userId": user_id,
        "password": room_password,
        "shareLinkType": "",
    }

    anchor_name, live_status = await get_winktv_bj_info(url=url, proxy_addr=proxy_addr, cookies=cookies)
    result: dict[str, object] = {"anchor_name": anchor_name, "is_live": live_status}
    if live_status:
        play_api = "https://api.winktv.co.kr/v1/live/play"
        json_str = await async_req(url=play_api, proxy_addr=proxy_addr, headers=headers, data=data, abroad=True)
        json_str = _get_str_response(json_str)
        # WinkTV 被封禁时不在 HTTP 层返回 403，而是把 "403: Forbidden" 作为响应体字符串返回，
        # 故必须做文本包含判断，而非只看状态码；命中即说明该出口 IP 已被拉黑。
        if "403: Forbidden" in json_str:
            raise ConnectionError(f"Your network has been banned from accessing WinkTV ({json_str})")
        json_data = json.loads(json_str)
        if "errorData" in json_data:
            if json_data["errorData"]["code"] == "needAdult":
                raise RuntimeError(
                    f"{url} The live stream is only accessible to logged-in adults. Please ensure that "
                    f"the cookie is correctly filled in the configuration file after logging in."
                )
            else:
                raise RuntimeError(json_data["errorData"]["code"], json_data["message"])
        m3u8_url = json_data["PlayList"]["hls"][0]["url"]
        play_url_list = await get_play_url_list(m3u8=m3u8_url, proxy=proxy_addr, header=headers, abroad=True)
        result["m3u8_url"] = m3u8_url
        result["play_url_list"] = play_url_list
    return result


@trace_error_decorator_or_none
async def login_flextv(username: str, password: str, proxy_addr: OptionalStr = None) -> OptionalStr:
    # TTingLive(原Flextv) 平台登录认证
    # 返回 cookie 字符串（OptionalStr）或 None；signin 接口对游客态也会下发游客 cookie，
    # 故即使未传账号密码也能拿到可用的访客凭证，无需强制登录。
    headers = {
        "accept": "application/json, text/plain, */*",
        "accept-language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
        "content-type": "application/json;charset=UTF-8",
        "referer": "https://www.ttinglive.com/",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:148.0) Gecko/20100101 Firefox/148.0",
    }

    data = {
        "loginId": username,
        "password": password,
        "loginKeep": True,
        "saveId": True,
        "device": "PCWEB",
    }

    url = "https://www.ttinglive.com/v2/api/auth/signin"

    try:
        print("Logging into FlexTV platform...")
        cookie_result = await async_req(
            url, proxy_addr=proxy_addr, headers=headers, json_data=data, return_cookies=True, timeout=20
        )

        # async_req 返回 cookies 的形状随版本变化（dict 或 (resp,dict) 元组），统一收敛为 cookie_dict
        if isinstance(cookie_result, dict):
            cookie_dict = cookie_result
        elif isinstance(cookie_result, tuple) and len(cookie_result) == 2 and isinstance(cookie_result[1], dict):
            cookie_dict = cookie_result[1]
        else:
            cookie_dict = {}

        if cookie_dict and "flx_oauth_access" in cookie_dict:
            cookie_str = "; ".join([f"{k}={v}" for k, v in cookie_dict.items()])
            return cookie_str
        else:
            print("Please check if the FlexTV account and password in the configuration file are correct.")
            return None

    except Exception as e:
        print(f"FlexTV login request exception: {e}")
        raise Exception(
            "FlexTV login failed, please check if the account and password in the configuration file are correct."
        )


async def get_flextv_stream_url(url: str, proxy_addr: OptionalStr = None, cookies: OptionalStr = None) -> str | None:
    # 获取 TTingLive(原Flextv) 直播流地址
    # 返回 str|None（None 表示未开播/无源），调用方 get_flextv_stream_data 据此决定是否置 is_live；
    # 内部 fetch_data 把响应体里的 "HTTP Error 400: Bad Request" 文本当作代理被封信号——
    # flextv 不在 HTTP 层返回 400，而是把错误塞进 body 字符串，需做文本包含判断。
    async def fetch_data(cookie: OptionalStr = None) -> dict[str, object]:
        # 抓取 TTingLive(原Flextv) 直播数据
        headers = {
            "accept": "application/json, text/plain, */*",
            "accept-language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
            "referer": "https://www.ttinglive.com/",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:148.0) Gecko/20100101 Firefox/148.0",
        }
        user_id = url.split("/live")[0].rsplit("/", maxsplit=1)[-1]
        # 调用方透传 cookie 时优先采用；否则走游客态/自动获取凭据（各平台未登录态取流能力不一，部分更易被风控）
        if cookie:
            headers["Cookie"] = cookie
        play_api = f"https://www.ttinglive.com/api/channels/{user_id}/stream?option=all"
        json_str = await async_req(play_api, proxy_addr=proxy_addr, headers=headers, abroad=True)
        json_str = _get_str_response(json_str)
        if "HTTP Error 400: Bad Request" in json_str:
            raise ConnectionError(
                "Failed to retrieve FlexTV live streaming data, please switch to a different proxy and try again."
            )
        return cast(dict[str, object], json.loads(json_str))

    json_data = await fetch_data(cookies)
    sources = json_data.get("sources")
    # sources 为空/非列表即无可用清晰度的流，返回 None 由调用方按未开播处理
    if sources and isinstance(sources, list) and len(sources) > 0:
        first_source = sources[0]
        if isinstance(first_source, dict):
            play_url = cast(str, first_source.get("url", ""))
            return play_url
    return None


@trace_error_decorator
async def get_flextv_stream_data(
    url: str,
    proxy_addr: OptionalStr = None,
    cookies: OptionalStr = None,
    username: OptionalStr = None,
    password: OptionalStr = None,
) -> dict[str, object]:
    # 获取 TTingLive(原Flextv) 直播流数据
    # 解析链路：未登录走游客头直接请求 live/play，登录态经 login_flextv 拿 token 再请求；
    # 返回 is_live + m3u8 + play_url_list；token 失效由调用方头部透传刷新，无流按未开播返回。
    headers = {
        "accept": "application/json, text/plain, */*",
        "accept-language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
        "referer": "https://www.ttinglive.com/",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:148.0) Gecko/20100101 Firefox/148.0",
    }
    # 调用方透传 cookie 时优先采用；否则走游客态/自动获取凭据（各平台未登录态取流能力不一，部分更易被风控）
    if cookies:
        headers["Cookie"] = cookies
    # user_id 取 URL 中 "/live" 之前最后一段（主播主页路径），是 flextv 频道路由标识。
    user_id = url.split("/live")[0].rsplit("/", maxsplit=1)[-1]
    result: dict[str, object] = {"anchor_name": "", "is_live": False}
    new_cookies = None
    try:
        url2 = f"https://www.ttinglive.com/channels/{user_id}/live"
        html_str = await async_req(url2, proxy_addr=proxy_addr, headers=headers, abroad=True)
        html_str = _get_str_response(html_str)
        json_str_match = re.search('<script id="__NEXT_DATA__" type=".*">(.*?)</script>', html_str)
        if not json_str_match:
            raise ValueError("Failed to find __NEXT_DATA__")
        json_str = json_str_match.group(1)
        json_data = json.loads(json_str)
        channel_data = json_data["props"]["pageProps"]["channel"]
        # 成人/登录限定房：频道页 message 含韩文「로그인후 이용이 가능합니다.」(需登录)，
        # 此时必须走登录流程换 cookie，否则拿不到流；下方触发 login_flextv 重试整页抓取。
        login_need = "message" in channel_data and "로그인후 이용이 가능합니다." in channel_data.get("message")
        if login_need:
            print(
                "FlexTV live stream retrieval failed [not logged in]: 19+ live streams are only available for "
                "logged-in adults."
            )
            print(
                "Attempting to log in to the FlexTV live streaming platform, please ensure your account and "
                "password are correctly filled in the configuration file."
            )
            if not username or not password or len(username) < 6 or len(password) < 8:
                raise RuntimeError(
                    "TTingLive(原Flextv)登录失败！请在config.ini配置文件中填写正确的TTingLive(原Flextv)平台的账号和密码"
                )
            new_cookies = await login_flextv(username, password, proxy_addr=proxy_addr)
            if new_cookies:
                print("Logged into FlexTV platform successfully! Starting to fetch live streaming data...")
            else:
                raise RuntimeError("TTingLive(原Flextv) login failed")
            cookies = new_cookies if new_cookies else cookies
            if cookies:
                headers["Cookie"] = cookies
            html_str = await async_req(url2, proxy_addr=proxy_addr, headers=headers, abroad=True)
            html_str = _get_str_response(html_str)
            json_str_match = re.search('<script id="__NEXT_DATA__" type=".*">(.*?)</script>', html_str)
            if not json_str_match:
                raise ValueError("Failed to find __NEXT_DATA__")
            json_str = json_str_match.group(1)
            json_data = json.loads(json_str)
            channel_data = json_data["props"]["pageProps"]["channel"]

        # 频道页若带 message 字段说明是未开播/受限占位页，无 message 才是真实在播频道。
        live_status = "message" not in channel_data
        if live_status:
            anchor_id = channel_data["owner"]["loginId"]
            anchor_name = f"{channel_data['owner']['nickname']}-{anchor_id}"
            result["anchor_name"] = anchor_name
            play_url = await get_flextv_stream_url(url=url, proxy_addr=proxy_addr, cookies=cookies)
            if play_url:
                result["is_live"] = True
                if ".m3u8" in play_url:
                    play_url_list = await get_play_url_list(
                        m3u8=play_url, proxy=proxy_addr, header=headers, abroad=True
                    )
                    if play_url_list:
                        result["m3u8_url"] = play_url
                        result["play_url_list"] = play_url_list
                else:
                    result["flv_url"] = play_url
                    result["record_url"] = play_url
        else:
            url2 = f"https://www.ttinglive.com/channels/{user_id}"
            html_str = await async_req(url2, proxy_addr=proxy_addr, headers=headers, abroad=True)
            html_str = _get_str_response(html_str)
            anchor_name_match = re.search('<meta name="twitter:title" content="(.*?)의', html_str)
            if anchor_name_match:
                anchor_name = anchor_name_match.group(1)
                result["anchor_name"] = anchor_name
    except Exception as e:
        print("Failed to retrieve data from FlexTV live room", e)
    result["new_cookies"] = new_cookies
    return result


def get_looklive_secret_data(text: str | dict[str, str]) -> tuple[str, str]:
    # 本算法参考项目：https://github.com/785415581/MusicBox/blob/b8f716d43d/doc/analysis/analyze_captured_data.md

    # 以下 modulus/nonce/public_key 是网易 weapi 接口的固定加密常量（与网易云音乐同一套 RSA/AES 方案），
    # 由服务端硬编码，不可随意更改——改了服务端也无法解密 params，表现为 200+空/报错。
    modulus = (
        "00e0b509f6259df8642dbc35662901477df22677ec152b5ff68ace615bb7b725152b3ab17a876aea8a5aa76d2e417629ec4ee"
        "341f56135fccf695280104e0312ecbda92557c93870114af6c9d05c4f7f0c3685b7a46bee255932575cce10b424d813cfe487"
        "5d3e82047b97ddef52741d546b8e289dc6935b3ece0462db0a22b8e7"
    )
    nonce = b"0CoJUm6Qyw8W8jud"
    public_key = "010001"
    import base64
    import binascii
    import secrets

    from Crypto.Cipher import AES
    from Crypto.Util.Padding import pad

    def create_secret_key(size: int) -> bytes:
        # 生成网易 weapi/Look 直播方案用的随机 sec_key（每请求独立生成，无状态、不缓存）
        charset = "1234567890abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ!@#$%^&*()_+-=[]{}|;:,.<>?"
        return "".join(secrets.choice(charset) for _ in range(size)).encode("utf-8")

    def aes_encrypt(_text: str | bytes, _sec_key: str | bytes) -> bytes:
        # 网易 weapi 标准 AES-128-CBC：密钥取前 16 字节、IV 固定为 "0102030405060708"（服务端约定，
        # 不可改），明文先 PKCS7 填充再加密；外层对 nonce、内层对随机 sec_key 做两次加密。
        if isinstance(_text, str):
            _text = _text.encode("utf-8")
        if isinstance(_sec_key, str):
            _sec_key = _sec_key.encode("utf-8")
        _sec_key = _sec_key[:16]  # AES-128 固定 16 字节密钥
        iv = bytes("0102030405060708", "utf-8")
        encryptor = AES.new(_sec_key, AES.MODE_CBC, iv)
        padded_text = pad(_text, AES.block_size)
        ciphertext = encryptor.encrypt(padded_text)
        encoded_ciphertext = base64.b64encode(ciphertext)
        return encoded_ciphertext

    def rsa_encrypt(_text: str | bytes, pub_key: str, mod: str) -> str:
        # 网易 weapi 的 RSA：明文先反转字节序再以固定公钥(pub_key="010001")对 modulus 取幂，
        # 结果补零到 256 位十六进制——这是网易云音乐同款逆向参数 encSecKey 的生成方式。
        if isinstance(_text, str):
            _text = _text.encode("utf-8")
        text_reversed = _text[::-1]
        text_int = int(binascii.hexlify(text_reversed), 16)
        encrypted_int = pow(text_int, int(pub_key, 16), int(mod, 16))
        return format(encrypted_int, "x").zfill(256)

    sec_key = create_secret_key(16)
    enc_text = aes_encrypt(aes_encrypt(json.dumps(text), nonce), sec_key)
    enc_sec_key = rsa_encrypt(sec_key, public_key, modulus)
    return enc_text.decode(), enc_sec_key


async def get_looklive_stream_url(
    url: str, proxy_addr: OptionalStr = None, cookies: OptionalStr = None
) -> dict[str, object]:
    # 通过PC网页端的接口获取完整直播源，只有params和encSecKey这两个加密请求参数。

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:148.0) Gecko/20100101 Firefox/148.0",
        "Accept": "application/json, text/javascript",
        "Accept-Language": "zh-CN,zh;q=0.8,zh-TW;q=0.7,zh-HK;q=0.5,en-US;q=0.3,en;q=0.2",
        "Content-Type": "application/x-www-form-urlencoded",
        "Referer": "https://look.163.com/",
    }

    # 调用方透传 cookie 时优先采用；否则走游客态/自动获取凭据（各平台未登录态取流能力不一，部分更易被风控）
    if cookies:
        headers["Cookie"] = cookies

    room_id_match = re.search("live\\?id=(.*?)&", url)
    if not room_id_match:
        raise ValueError("Failed to find room id in url")
    room_id = room_id_match.group(1)
    # 接口只接受 params/encSecKey 两个加密字段（网易 weapi 方案）：先用随机 sec_key 对明文做
    # 两次 AES-CBC，再用固定公钥 RSA 加密 sec_key 得到 encSecKey，服务端反向解密。明文缺失 room_id 即失败。
    params, secretkey = get_looklive_secret_data({"liveRoomNo": room_id})
    request_data = {"params": params, "encSecKey": secretkey}
    api = "https://api.look.163.com/weapi/livestream/room/get/v3"
    json_str = await async_req(api, proxy_addr=proxy_addr, headers=headers, data=request_data)
    json_str = _get_str_response(json_str)
    json_data = json.loads(json_str)
    anchor_name = json_data["data"]["anchor"]["nickName"]
    live_status = json_data["data"]["liveStatus"]
    result: dict[str, object] = {"anchor_name": anchor_name, "is_live": False}
    # liveStatus==1 为开播；liveType==1 是纯音频直播（无视频流，无法录视频，仅提示不报错）。
    if live_status == 1:
        result["is_live"] = True
        # liveType==1 是纯音频直播：无视频流可录，仅提示不取 play_url
        if json_data["data"]["roomInfo"]["liveType"] == 1:
            print("Look live currently only supports audio live streaming, not video live streaming!")
        else:
            play_url_list = json_data["data"]["roomInfo"]["liveUrl"]
            live_title = json_data["data"]["roomInfo"]["title"]
            result |= {
                "title": live_title,
                "flv_url": play_url_list["httpPullUrl"],
                "m3u8_url": play_url_list["hlsPullUrl"],
                "record_url": play_url_list["hlsPullUrl"],
            }
    return result


@trace_error_decorator
async def login_popkontv(
    username: str, password: str, proxy_addr: OptionalStr = None, code: OptionalStr = "P-00001"
) -> tuple[str, str]:
    # PopkonTV 平台登录认证
    headers = {
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
        # 应用级固定 API 凭据（非用户私人凭据），嵌入于 PopkonTV 客户端，无法从主页动态获取
        "Authorization": "Basic FpAhe6mh8Qtz116OENBmRddbYVirNKasktdXQiuHfm88zRaFydTsFy63tzkdZY0u",
        "Content-Type": "application/json",
        "Origin": "https://www.popkontv.com",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:148.0) Gecko/20100101 Firefox/148.0",
    }

    data = {
        "partnerCode": code,
        "signId": username,
        "signPwd": password,
    }

    url = "https://www.popkontv.com/api/proxy/member/v1/login"

    try:
        proxy_addr = utils.handle_proxy_addr(proxy_addr)
        async with httpx.AsyncClient(proxy=proxy_addr, timeout=20, verify=http_config.ssl_verify) as client:
            response = await client.post(url, json=data, headers=headers)
            response.raise_for_status()

            json_data = response.json()
            login_status_code = json_data.get("statusCd")

            # 登录网关状态：E4010 账号/密码错误；S2000 成功（返回 token 与 partnerCode 两件套）；
            # 其余按未知错误抛出。token 是后续所有播放接口的 Bearer 凭据，partnerCode 随账号绑定。
            if login_status_code == "E4010":
                raise Exception("popkontv login failed, please reconfigure the correct login account or password!")
            elif login_status_code == "S2000":
                token = json_data["data"].get("token")
                partner_code = json_data["data"].get("partnerCode")
                return token, partner_code
            else:
                raise Exception(f"popkontv login failed, {json_data.get('statusMsg', 'unknown error')}")
    except httpx.HTTPStatusError as e:
        print(f"HTTP status error occurred during login: {e.response.status_code}")
        raise
    except Exception as e:
        print(f"An exception occurred during popkontv login: {e}")
        raise


@trace_error_decorator
async def get_popkontv_stream_data(
    url: str,
    proxy_addr: OptionalStr = None,
    cookies: OptionalStr = None,
    username: OptionalStr = None,
    code: OptionalStr = "P-00001",
) -> tuple[str, list[object] | None]:
    # 获取 PopkonTV 直播流数据
    # 解析链路：broadcast/search/all 按 anchor_id 找 mcSignId → 必要时从 notices 抠昵称补 partnerCode；
    # 返回 (anchor_name, room_info|None)；room_info 为 None 表示未开播，交由 get_popkontv_stream_url 判否。
    headers = {
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
        "Content-Type": "application/json",
        "Origin": "https://www.popkontv.com",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:148.0) Gecko/20100101 Firefox/148.0",
    }
    # 调用方透传 cookie 时优先采用；否则走游客态/自动获取凭据（各平台未登录态取流能力不一，部分更易被风控）
    if cookies:
        headers["Cookie"] = cookies
    if "mcid" in url:
        anchor_id_match = re.search("mcid=(.*?)&", url)
    else:
        anchor_id_match = re.search("castId=(.*?)(?=&|$)", url)
    if not anchor_id_match:
        raise ValueError("Failed to find anchor id in url")
    anchor_id = anchor_id_match.group(1)

    data = {
        "partnerCode": code,
        "searchKeyword": anchor_id,
        "signId": username,
    }

    api = "https://www.popkontv.com/api/proxy/broadcast/v1/search/all"
    json_str = await async_req(api, proxy_addr=proxy_addr, headers=headers, json_data=data, abroad=True)
    json_str = _get_str_response(json_str)
    json_data = json.loads(json_str)

    partner_code: str | None = ""
    anchor_name = "Unknown"
    for item in json_data["data"]["broadCastList"]:
        if item["mcSignId"] == anchor_id:
            mc_name = item["nickName"]
            anchor_name = f"{mc_name}-{anchor_id}"
            partner_code = cast(str | None, item["mcPartnerCode"]) if item else None
            break

    # 搜索接口没带出 partnerCode 时，从 URL 抠或退回默认 code，并补抓 notices 页拿昵称
    if not partner_code:
        # 搜索接口未带出 partnerCode 时，优先从 URL 抠（mcPartnerCode/partnerCode），都没有则用默认 code；
        # 再抓 notices 页用正则抠出 mcNickName 补全主播名（搜索结果里没昵称时的兜底）。
        if "mcPartnerCode" in url:
            regex_result = re.search("mcPartnerCode=(P-\\d+)", url)
        else:
            regex_result = re.search("partnerCode=(P-\\d+)", url)
        partner_code = regex_result.group(1) if regex_result else code
        notices_url = f"https://www.popkontv.com/channel/notices?mcid={anchor_id}&mcPartnerCode={partner_code}"
        notices_response = await async_req(notices_url, proxy_addr=proxy_addr, headers=headers, abroad=True)
        notices_response = _get_str_response(notices_response)
        mc_name_match = re.search(r'"mcNickName":"([^"]+)"', notices_response)
        mc_name = mc_name_match.group(1) if mc_name_match else "Unknown"
        anchor_name = f"{anchor_id}-{mc_name}"

    live_url = f"https://www.popkontv.com/live/view?castId={anchor_id}&partnerCode={partner_code}"
    html_str2 = await async_req(live_url, proxy_addr=proxy_addr, headers=headers, abroad=True)
    html_str2 = _get_str_response(html_str2)
    json_str2_match = re.search('<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', html_str2)
    if not json_str2_match:
        return anchor_name, None
    json_str2 = json_str2_match.group(1)
    json_data2 = json.loads(json_str2)
    if "mcData" in json_data2["props"]["pageProps"]:
        room_data = json_data2["props"]["pageProps"]["mcData"]["data"]
        is_private = room_data["mc_isPrivate"]
        cast_start_date_code = room_data["mc_castStartDate"]
        mc_sign_id = room_data["mc_signId"]
        cast_type = room_data["castType"]
        return anchor_name, [cast_start_date_code, partner_code, mc_sign_id, cast_type, is_private]
    else:
        return anchor_name, None


@trace_error_decorator
async def get_popkontv_stream_url(
    url: str,
    proxy_addr: OptionalStr = None,
    access_token: OptionalStr = None,
    username: OptionalStr = None,
    password: OptionalStr = None,
    partner_code: OptionalStr = "P-00001",
) -> dict[str, object]:
    # 获取 PopkonTV 直播流地址
    # 解析链路：复用 get_popkontv_stream_data 的 room_info → castwatchonoffguest 拿 HLS；
    # token 失效(E5000/400)自动登录刷新（新 token 长度须 640）；返回 is_live + m3u8 + new_token。
    headers = {
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
        "ClientKey": "Client FpAhe6mh8Qtz116OENBmRddbYVirNKasktdXQiuHfm88zRaFydTsFy63tzkdZY0u",
        "Content-Type": "application/json",
        "Origin": "https://www.popkontv.com",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:148.0) Gecko/20100101 Firefox/148.0",
    }

    # 调用方透传 Bearer token 时优先采用；否则复用游客态，token 失效由下方分支触发登录刷新
    if access_token:
        headers["Authorization"] = f"Bearer {access_token}"

    anchor_name, room_info = await get_popkontv_stream_data(
        url, proxy_addr=proxy_addr, code=partner_code, username=username
    )
    result: dict[str, object] = {"anchor_name": anchor_name, "is_live": False}
    new_token = None
    if room_info:
        cast_start_date_code, cast_partner_code, mc_sign_id, cast_type, is_private = room_info
        result["is_live"] = True
        room_password = get_params(url, "pwd")
        # 私有房间且未配密码：必须带 pwd 才能取流，否则抛错提示配置密码
        if int(cast(str, is_private)) != 0 and not room_password:
            raise RuntimeError(
                f"Failed to retrieve live room data because {anchor_name}'s room is a private room. "
                f"Please configure the room password and try again."
            )

        current_partner_code = partner_code  # 跟踪当前有效的 partner_code，登录刷新后更新

        async def fetch_data(header: dict[str, str] | None = None, code: OptionalStr = None) -> str:
            # 抓取 PopkonTV 直播数据
            data = {
                "androidStore": 0,
                "castCode": f"{mc_sign_id}-{cast_start_date_code}",
                "castPartnerCode": cast_partner_code,
                "castSignId": mc_sign_id,
                "castType": cast_type,
                "commandType": 0,
                "exePath": 5,
                "isSecret": is_private,
                "partnerCode": code,
                "password": room_password,
                "signId": username,
                "version": "4.6.2",
            }
            play_api = "https://www.popkontv.com/api/proxy/broadcast/v1/castwatchonoffguest"
            resp = await async_req(play_api, proxy_addr=proxy_addr, json_data=data, headers=header, abroad=True)
            return _get_str_response(resp)

        json_str = await fetch_data(headers, current_partner_code)
        json_str = _get_str_response(json_str)

        # token 失效/不存在：接口返回 HTTP 400 或 body 内 statusCd E5000，均表示 Bearer 凭据过期，
        # 触发登录刷新（新 token 长度必须为 640，否则视为登录失败）。登录后复用新 partnerCode 重试。
        if "HTTP Error 400" in json_str or 'statusCd":"E5000' in json_str:
            print(
                "Failed to retrieve popkontv live stream [token does not exist or has expired]: Please log in to "
                "watch."
            )
            print(
                "Attempting to log in to the popkontv live streaming platform, please ensure your account "
                "and password are correctly filled in the configuration file."
            )
            if not username or not password or len(username) < 4 or len(password) < 10:
                raise RuntimeError(
                    "popkontv login failed! Please enter the correct account and password for the "
                    "popkontv platform in the config.ini file."
                )
            print("Logging into popkontv platform...")
            new_access_token, new_partner_code = await login_popkontv(
                username=username, password=password, proxy_addr=proxy_addr, code=current_partner_code
            )
            # 新 token 长度固定 640 字节是登录接口的真实返回特征，偏离即说明登录未真正成功。
            # 新 token 长度固定 640 是登录接口真实返回特征，偏离即说明登录未真正成功
            if new_access_token and len(new_access_token) == 640:
                print("Logged into popkontv platform successfully! Starting to fetch live streaming data...")
                headers["Authorization"] = f"Bearer {new_access_token}"
                new_token = f"Bearer {new_access_token}"
                current_partner_code = new_partner_code
                json_str = await fetch_data(headers, current_partner_code)
                json_str = _get_str_response(json_str)
            else:
                raise RuntimeError("popkontv login failed, please check if the account and password are correct")
        json_data = json.loads(json_str)
        status_msg = json_data["statusMsg"]
        # L000A：未实名/未手机验证会员，服务端拒绝提供流；L0000：成功拿到 HLS；L0001：首请求需二次确认。
        if json_data["statusCd"] == "L000A":
            print("Failed to retrieve live stream source,", status_msg)
            raise RuntimeError(
                "You are an unverified member. After logging into the popkontv official website, "
                "please verify your mobile phone at the bottom of the 'My Page' > 'Edit My "
                "Information' to use the service."
            )
        elif json_data["statusCd"] == "L0001":
            cast_start_date_code_int = int(cast(str, cast_start_date_code)) - 1
            # 对同参数再请求一次（首请求偶发需二次确认才返回真实 HLS）。注意：上面算出的
            # cast_start_date_code_int（原值减 1）实际并未传入本次重试（fetch_data 闭包仍用原值），
            # 若该减 1 才是正确值，则此处重试可能仍失败——属潜在的时效/边界坑位。
            json_str = await fetch_data(headers, current_partner_code)
            json_str = _get_str_response(json_str)
            json_data = json.loads(json_str)
            m3u8_url = json_data["data"]["castHlsUrl"]
            result |= {"m3u8_url": m3u8_url, "record_url": m3u8_url}
        elif json_data["statusCd"] == "L0000":
            m3u8_url = json_data["data"]["castHlsUrl"]
            result |= {"m3u8_url": m3u8_url, "record_url": m3u8_url}
        else:
            raise RuntimeError("Failed to retrieve live stream source,", status_msg)
    result["new_token"] = new_token
    return result


@trace_error_decorator
async def login_twitcasting(
    account_type: str, username: str, password: str, proxy_addr: OptionalStr = None, cookies: OptionalStr = None
) -> OptionalStr:
    # TwitCasting 平台登录认证
    headers = {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
        "Content-Type": "application/x-www-form-urlencoded",
        "Referer": "https://twitcasting.tv/indexcaslogin.php?redir=%2Findexloginwindow.php%3Fnext%3D%252F&keep=1",
        # 移除原硬编码的 TwitCasting 访客统计 Cookie（hl/did/_ga 等均为临时统计字段）
        # 登录流程由 cs_session_id 驱动，不依赖此 Cookie；未配置时不发送 Cookie 头
        "User-Agent": "ios/7.830 (ios 17.0; ; iPhone 15 (A2846/A3089/A3090/A3092))",
    }

    if cookies:
        headers["Cookie"] = cookies

    if account_type == "twitter":
        login_url = "https://twitcasting.tv/indexpasswordlogin.php"
        login_api = "https://twitcasting.tv/indexpasswordlogin.php?redir=/indexloginwindow.php?next=%2F&keep=1"
    else:
        login_url = "https://twitcasting.tv/indexcaslogin.php?redir=%2F&keep=1"
        login_api = "https://twitcasting.tv/indexcaslogin.php?redir=/indexloginwindow.php?next=%2F&keep=1"

    html_str = await async_req(login_url, proxy_addr=proxy_addr, headers=headers)
    html_str = _get_str_response(html_str)
    cs_session_id_match = re.search('<input type="hidden" name="cs_session_id" value="(.*?)">', html_str)
    if not cs_session_id_match:
        raise ValueError("Failed to find cs_session_id")
    cs_session_id = cs_session_id_match.group(1)

    data = {
        "username": username,
        "password": password,
        "action": "login",
        "cs_session_id": cs_session_id,
    }
    try:
        cookie_result = await async_req(
            login_api, proxy_addr=proxy_addr, headers=headers, data=data, return_cookies=True, timeout=20
        )
        if isinstance(cookie_result, dict):
            cookie_dict = cookie_result
        elif isinstance(cookie_result, tuple) and len(cookie_result) == 2 and isinstance(cookie_result[1], dict):
            cookie_dict = cookie_result[1]
        else:
            cookie_dict = {}

        if "tc_ss" in cookie_dict:
            cookie = utils.dict_to_cookie_str(cookie_dict)
            return cookie
    except Exception as e:
        print("TwitCasting login error,", e)
    return None


@trace_error_decorator
async def get_twitcasting_stream_url(
    url: str,
    proxy_addr: OptionalStr = None,
    cookies: OptionalStr = None,
    account_type: OptionalStr = None,
    username: OptionalStr = None,
    password: OptionalStr = None,
) -> dict[str, object]:
    # 获取 TwitCasting 直播流地址
    # 解析链路：畸形 URL 显式报错 → 必要时 login_twitcasting 拿 cookie → get_data 抠 title/status/movie_id；
    # data-is-onlive="true" 才取流；返回 is_live + play_url_list（高>中>低排序），未开播不取流。
    headers = {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
        "Referer": "https://twitcasting.tv/?ch0",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:148.0) Gecko/20100101 Firefox/148.0",
    }

    parts = url.split("?")[0].split("/")
    # 畸形 URL（无主播 ID 段）：显式报错而非 IndexError
    if len(parts) < 4 or not parts[3].strip():
        # 畸形 URL（无主播 ID 段）：显式报错而非 IndexError
        raise RuntimeError(f"无法从链接中解析 TwitCasting 主播 ID: {url}")
    anchor_id = parts[3]
    # 调用方透传 cookie 时优先采用；否则走游客态/自动获取凭据（各平台未登录态取流能力不一，部分更易被风控）
    if cookies:
        headers["Cookie"] = cookies

    async def get_data(header: dict[str, str]) -> tuple[str, str, str]:
        # 获取 TwitCasting 直播数据
        html_str = await async_req(url, proxy_addr=proxy_addr, headers=header)
        html_str = _get_str_response(html_str)
        anchor = re.search("<title>(.*?) \\(@(.*?)\\)  的直播 - Twit", html_str)
        title = re.search('<meta name="twitter:title" content="(.*?)">\n\\s+<meta', html_str)
        status = re.search('data-is-onlive="(.*?)"\n\\s+data-view-mode', html_str)
        movie_id = re.search('data-movie-id="(.*?)" data-audience-id', html_str)
        if not anchor or not title or not status or not movie_id:
            raise ValueError("Failed to parse page data")
        return f"{anchor.group(1).strip()}-{anchor.group(2)}-{movie_id.group(1)}", status.group(1), title.group(1)

    result: dict[str, object] = {"anchor_name": "", "is_live": False}
    new_cookie = None
    anchor_name = ""
    live_status = ""
    live_title = ""
    try:
        to_login = get_params(url, "login")
        if to_login == "true":
            print("Attempting to log in to TwitCasting...")
            new_cookie = await login_twitcasting(
                account_type=cast(str, account_type),
                username=cast(str, username),
                password=cast(str, password),
                proxy_addr=proxy_addr,
                cookies=cookies,
            )
            if not new_cookie:
                raise RuntimeError(
                    "TwitCasting login failed, please check if the account password in the "
                    "configuration file is correct"
                )
            print("TwitCasting login successful! Starting to fetch data...")
            headers["Cookie"] = new_cookie
        anchor_name, live_status, live_title = await get_data(headers)
    # 解析阶段抛 AttributeError（页面结构变化/受限，正则 group 落在 None 上）即视为需登录，
    # 这里统一回落到登录流程再抓一次；登录失败则向上抛 RuntimeError。
    except AttributeError:
        print("Failed to retrieve TwitCasting data, attempting to log in...")
        new_cookie = await login_twitcasting(
            account_type=cast(str, account_type),
            username=cast(str, username),
            password=cast(str, password),
            proxy_addr=proxy_addr,
            cookies=cookies,
        )
        if not new_cookie:
            raise RuntimeError(
                "TwitCasting login failed, please check if the account and password in the "
                "configuration file are correct"
            )
        print("TwitCasting login successful! Starting to fetch data...")
        headers["Cookie"] = new_cookie
        anchor_name, live_status, live_title = await get_data(headers)

    result["anchor_name"] = anchor_name
    # data-is-onlive="true" 才是开播；否则（含未登录受限）按未开播返回，不取流。
    if live_status == "true":
        url_streamserver = f"https://twitcasting.tv/streamserver.php?target={anchor_id}&mode=client&player=pc_web"
        stream_data = await async_req(url_streamserver, proxy_addr=proxy_addr, headers=headers)
        stream_data = _get_str_response(stream_data)
        json_data = json.loads(stream_data)
        # tc-hls/streams 缺失即无可用 HLS，报错提示检查链接
        if not json_data.get("tc-hls") or not json_data["tc-hls"].get("streams"):
            raise RuntimeError("No m3u8_url,please check the url")

        stream_dict = json_data["tc-hls"]["streams"]
        quality_order = {"high": 0, "medium": 1, "low": 2}
        # 按 高>中>低 顺序排序画质候选，未识别的画质 key 放到最后（quality_order.get 默认 99），
        # 避免服务端新增档位时 KeyError 导致整段解析失败。
        sorted_streams = sorted(stream_dict.items(), key=lambda item: quality_order.get(item[0], 99))
        play_url_list = [url for _, url in sorted_streams]
        result |= {"title": live_title, "is_live": True, "play_url_list": play_url_list}
    result["new_cookies"] = new_cookie
    return result


@trace_error_decorator
async def get_baidu_stream_data(
    url: str, proxy_addr: OptionalStr = None, cookies: OptionalStr = None
) -> dict[str, object]:
    # 获取百度直播流数据
    # 解析链路：随机 h5- uid 游客标识 → searchbox 接口 → data 取 status/url_clarity_list；
    # status=="0" 才取流，flv 转 m3u8 拼固定 CDN；返回 is_live + play_url_list，data 缺失直接回未开播。
    headers = {
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
        "Connection": "keep-alive",
        "Referer": "https://live.baidu.com/",
        "User-Agent": "ios/7.830 (ios 17.0; ; iPhone 15 (A2846/A3089/A3090/A3092))",
    }
    if cookies:
        headers["Cookie"] = cookies

    # 从一组写死的 h5- 设备/访客 uid 里随机挑一个作为匿名标识：百度接口对游客态要求带该 uid，
    # 但不校验其真实归属，随机复用即可；硬编码是为避免每轮请求都生成新设备被风控。
    uid = random.choice(
        [
            "h5-683e85bdf741bf2492586f7ca39bf465",
            "h5-c7c6dc14064a136be4215b452fab9eea",
            "h5-4581281f80bb8968bd9a9dfba6050d3a",
        ]
    )
    room_id_match = re.search("room_id=(.*?)&", url)
    if not room_id_match:
        raise ValueError("Failed to find room_id in url")
    room_id = room_id_match.group(1)
    params = {
        "cmd": "371",
        "action": "star",
        "service": "bdbox",
        "osname": "baiduboxapp",
        "data": '{"data":{"room_id":"' + room_id + '","device_id":"h5-683e85bdf741bf2492586f7ca39bf465",'
        '"source_type":0,"osname":"baiduboxapp"},"replay_slice":0,'
        '"nid":"","schemeParams":{"src_pre":"pc","src_suf":"other",'
        '"bd_vid":"","share_uid":"","share_cuk":"","share_ecid":"",'
        '"zb_tag":"","shareTaskInfo":"{\\"room_id\\":\\"9175031377\\"}",'
        '"share_from":"","ext_params":"","nid":""}}',
        "ua": "360_740_ANDROID_0",
        "bd_vid": "",
        "uid": uid,
        "_": str(int(time.time() * 1000)),
    }
    app_api = f"https://mbd.baidu.com/searchbox?{urllib.parse.urlencode(params)}"
    json_str = await async_req(url=app_api, proxy_addr=proxy_addr, headers=headers)
    json_str = _get_str_response(json_str)
    json_data = json.loads(json_str)
    data_dict = json_data.get("data", {})
    if not data_dict:
        return {"anchor_name": "", "is_live": False}
    key = list(data_dict.keys())[0]
    data = data_dict[key]
    anchor_name = data["host"]["name"]
    result: dict[str, object] = {"anchor_name": anchor_name, "is_live": False}
    if data["status"] == "0":
        result["is_live"] = True
        live_title = data["video"]["title"]
        play_url_list = data["video"]["url_clarity_list"]
        # 百度直播只下发 flv 地址，但本机只支持录制 m3u8，故把 flv 地址的「扩展名+host」剥掉、
        # 换成固定 hls CDN 前缀拼回 .m3u8，得到可拉流的 HLS 地址。
        url_list = []
        prefix = "https://hls.liveshow.bdstatic.com/live/"
        if play_url_list:
            # 结构一：url_clarity_list 直接给每档位的 flv 串，剥 .flv 与 host 取流 id 重拼为 m3u8
            for i in play_url_list:
                flv = i.get("urls", {}).get("flv", "")
                flv_id = flv.rsplit(".", maxsplit=1)[0].rsplit("/", maxsplit=1)
                url_list.append(prefix + (flv_id[1] if len(flv_id) > 1 else "") + ".m3u8")
        else:
            # 结构二：url_list 嵌套 urls[0].hls（带查询参数），同样剥查询+host 取流 id
            play_url_list = data["video"]["url_list"]
            for i in play_url_list:
                urls = i.get("urls", [])
                hls = urls[0].get("hls", "") if urls else ""
                hls_id = hls.rsplit("?", maxsplit=1)[0].rsplit("/", maxsplit=1)
                url_list.append(prefix + (hls_id[1] if len(hls_id) > 1 else ""))

        if url_list:
            result |= {"is_live": True, "title": live_title, "play_url_list": url_list}
    return result


@trace_error_decorator
async def get_weibo_stream_data(
    url: str, proxy_addr: OptionalStr = None, cookies: OptionalStr = None
) -> dict[str, object]:
    # 获取微博直播流数据
    # 解析链路：show/<id> 直链或 /u/<uid> 主页列表找 live object → anchor/live_id → pc/anchor/live；
    # status==1 取流；返回 is_live + play_url_list（两组候选，含去画质后缀回退可用源）。
    headers = {
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
        # 移除原硬编码的微博登录态 Cookie（含 XSRF-TOKEN/SUB/SUBP/WBPSESS 等用户登录凭据）
        # 未配置 cookie 时不发送 Cookie 头；公开直播间信息无需登录态
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:148.0) Gecko/20100101 Firefox/148.0",
        "Referer": "https://weibo.com/u/5885340893",
    }
    if cookies:
        headers["Cookie"] = cookies

    room_id = ""
    # 两条入口：show/<id> 直链可直接拿到 room_id；/u/<uid> 主页需先拉微博列表，
    # 在 list 里找 object_type=="live" 的那条取 object_id 作为 room_id（无直播时 room_id 留空→不取流）。
    if "show/" in url:
        room_id = url.split("?")[0].split("show/")[1]
    else:
        parts = url.split("?")[0].rsplit("/u/", maxsplit=1)
        # 畸形 URL（无 /u/ 用户段）：显式报错而非 IndexError
        if len(parts) < 2 or not parts[1].strip():
            # 畸形 URL（无 /u/ 用户段）：显式报错而非 IndexError
            raise RuntimeError(f"无法从链接中解析微博用户 ID: {url}")
        uid = parts[1]
        web_api = f"https://weibo.com/ajax/statuses/mymblog?uid={uid}&page=1&feature=0"
        json_str = await async_req(web_api, proxy_addr=proxy_addr, headers=headers)
        json_str = _get_str_response(json_str)
        json_data = json.loads(json_str)
        for i in json_data["data"]["list"]:
            if "page_info" in i and i["page_info"]["object_type"] == "live":
                room_id = i["page_info"]["object_id"]
                break

    result: dict[str, object] = {"anchor_name": "", "is_live": False}
    if room_id:
        app_api = f"https://weibo.com/l/pc/anchor/live?live_id={room_id}"
        # app_api = f'https://weibo.com/l/!/2/wblive/room/show_pc_live.json?live_id={room_id}'
        json_str = await async_req(url=app_api, proxy_addr=proxy_addr, headers=headers)
        json_str = _get_str_response(json_str)
        json_data = json.loads(json_str)
        anchor_name = json_data["data"]["user_info"]["name"]
        result["anchor_name"] = anchor_name
        live_status = json_data["data"]["item"]["status"]
        if live_status == 1:
            result["is_live"] = True
            live_title = json_data["data"]["item"]["desc"]
            play_url_list = json_data["data"]["item"]["stream_info"]["pull"]
            m3u8_url = play_url_list["live_origin_hls_url"]
            flv_url = play_url_list["live_origin_flv_url"]
            result["title"] = live_title
            # 第二组候选把地址里的画质后缀（"_原画"/"_蓝光"等）去掉，回退到默认清晰度，
            # 当原始清晰度档位在 CDN 上不可用时仍有可用源；两组都进 play_url_list 由上层按可达性校验。
            result["play_url_list"] = [
                {"m3u8_url": m3u8_url, "flv_url": flv_url},
                {"m3u8_url": m3u8_url.split("_")[0] + ".m3u8", "flv_url": flv_url.split("_")[0] + ".flv"},
            ]
    return result


@trace_error_decorator
async def get_kugou_stream_url(
    url: str, proxy_addr: OptionalStr = None, cookies: OptionalStr = None
) -> dict[str, object]:
    # 获取酷狗繁星直播流地址
    # 解析链路：getEnterRoomInfo 拿昵称 + liveType → liveType!=-1 才请求 mutiline/streamaddr 拿 flv；
    # 返回 is_live + flv + record_url；音乐频道房间不支持录制会抛 RuntimeError。
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:148.0) Gecko/20100101 Firefox/148.0",
        "Accept": "application/json",
        "Accept-Language": "zh-CN,zh;q=0.8,zh-TW;q=0.7,zh-HK;q=0.5,en-US;q=0.3,en;q=0.2",
        "Referer": "https://fanxing2.kugou.com/",
    }
    # 调用方透传 cookie 时优先采用；否则走游客态/自动获取凭据（各平台未登录态取流能力不一，部分更易被风控）
    if cookies:
        headers["Cookie"] = cookies

    # 两条入口：URL 直带 roomId 直接抠，否则从路径末段取主播房间号
    if "roomId" in url:
        room_id_match = re.search("roomId=(\\d+)", url)
        if not room_id_match:
            raise ValueError("Failed to find roomId in url")
        room_id = room_id_match.group(1)
    else:
        room_id = _safe_extract_id(url)

    app_api = f"https://service2.fanxing.kugou.com/roomcen/room/web/cdn/getEnterRoomInfo?roomId={room_id}"
    json_str = await async_req(url=app_api, proxy_addr=proxy_addr, headers=headers)
    json_str = _get_str_response(json_str)
    json_data = json.loads(json_str)
    anchor_name = json_data["data"]["normalRoomInfo"]["nickName"]
    result: dict[str, object] = {"anchor_name": anchor_name, "is_live": False}
    # 音乐频道房间不支持录制，显式抛错提示换房间
    if not anchor_name:
        raise RuntimeError(
            "Music channel live rooms are not supported for recording, please switch to a different live room."
        )
    live_status = json_data["data"]["liveType"]
    # 酷狗用 liveType==-1 表示未开播，其它值（0/1 等）视为在播；注意这里是「!= -1」而非 == 1。
    # 酷狗 liveType==-1 表示未开播，其它值（0/1 等）视为在播（注意是 != -1 而非 == 1）
    if live_status != -1:
        params = {
            "std_rid": room_id,
            "std_plat": "7",
            "std_kid": "0",
            "streamType": "1-2-4-5-8",
            "ua": "fx-flash",
            "targetLiveTypes": "1-5-6",
            "version": "1000",
            "supportEncryptMode": "1",
            "appid": "1010",
            "_": str(int(time.time() * 1000)),
        }
        api = f"https://fx1.service.kugou.com/video/pc/live/pull/mutiline/streamaddr?{urllib.parse.urlencode(params)}"
        json_str2 = await async_req(api, proxy_addr=proxy_addr, headers=headers)
        json_str2 = _get_str_response(json_str2)
        json_data2 = json.loads(json_str2)
        stream_data = json_data2["data"]["lines"]
        if stream_data:
            flv_url = stream_data[-1]["streamProfiles"][0]["httpsFlv"][0]
            result |= {"is_live": True, "flv_url": flv_url, "record_url": flv_url}
    return result


async def get_twitchtv_room_info(
    url: str, token: str, proxy_addr: OptionalStr = None, cookies: OptionalStr = None
) -> tuple[str, bool]:
    # 获取 Twitch 直播间信息
    # 动态获取 Twitch Web 端公开 Client-Id，替代原硬编码值
    client_id = await _ensure_twitch_client_id(proxy_addr)
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:148.0) Gecko/20100101 Firefox/148.0",
        "Accept-Language": "zh-CN",
        "Referer": "https://www.twitch.tv/",
        "Client-Id": client_id,
        "Client-Integrity": token,
        "Content-Type": "text/plain;charset=UTF-8",
    }
    # 调用方透传 cookie 时优先采用；否则走游客态/自动获取凭据（各平台未登录态取流能力不一，部分更易被风控）
    if cookies:
        headers["Cookie"] = cookies
    uid = url.split("?")[0].rsplit("/", maxsplit=1)[-1]

    data = [
        {
            "operationName": "ChannelShell",
            "variables": {"login": uid},
            "extensions": {
                "persistedQuery": {
                    "version": 1,
                    "sha256Hash": "580ab410bcd0c1ad194224957ae2241e5d252b2c5173d8e0cce9d32d5bb14efe",
                }
            },
        },
    ]

    json_str = await async_req(
        "https://gql.twitch.tv/gql", proxy_addr=proxy_addr, headers=headers, json_data=data, abroad=True
    )
    json_str = _get_str_response(json_str)
    json_data = json.loads(json_str)
    # Twitch GQL 返回异常（非预期数组）即视为拿用户数据失败
    if not json_data or not isinstance(json_data, list):
        raise RuntimeError("Failed to retrieve Twitch user data")
    user_data = json_data[0]["data"]["userOrError"]
    login_name = user_data["login"]
    nickname = f"{user_data['displayName']}-{login_name}"
    # Twitch 用 userOrError.stream 字段是否存在来判定开播（有 stream 对象即在播），
    # 返回 (nickname, status) 元组供 get_twitchtv_stream_data 复用作 is_live。
    status = True if user_data["stream"] else False
    return nickname, status


@trace_error_decorator
async def get_twitchtv_stream_data(
    url: str, proxy_addr: OptionalStr = None, cookies: OptionalStr = None
) -> dict[str, object]:
    # 获取 Twitch 直播流数据
    # 动态获取 Twitch Web 端公开 Client-Id，替代原硬编码值
    client_id = await _ensure_twitch_client_id(proxy_addr)
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:148.0) Gecko/20100101 Firefox/148.0",
        "Accept-Language": "en-US",
        "Referer": "https://www.twitch.tv/",
        "Client-ID": client_id,
        "device-id": generate_random_string(16).lower(),
    }

    # 调用方透传 cookie 时优先采用；否则走游客态/自动获取凭据（各平台未登录态取流能力不一，部分更易被风控）
    if cookies:
        headers["Cookie"] = cookies
    uid = url.split("?")[0].rsplit("/", maxsplit=1)[-1]

    # Twitch 走 GraphQL persisted query：用固定 sha256Hash 指代一条预注册查询，省去传整段 query 文本；
    # Client-Id 必须动态获取（硬编码值会随前端版本过期导致 401），device-id 用随机串每次新建。
    data = {
        "operationName": "PlaybackAccessToken_Template",
        "query": "query PlaybackAccessToken_Template($login: String!, $isLive: Boolean!, $vodID: ID!, "
        "$isVod: Boolean!, $playerType: String!) {  streamPlaybackAccessToken(channelName: $login, "
        'params: {platform: "web", playerBackend: "mediaplayer", playerType: $playerType}) @include(if: '
        "$isLive) {    value    signature   authorization { isForbidden forbiddenReasonCode }   __typename  "
        '}  videoPlaybackAccessToken(id: $vodID, params: {platform: "web", playerBackend: "mediaplayer", '
        "playerType: $playerType}) @include(if: $isVod) {    value    signature   __typename  }}",
        "variables": {"isLive": True, "login": uid, "isVod": False, "vodID": "", "playerType": "site"},
    }

    json_str = await async_req(
        "https://gql.twitch.tv/gql", proxy_addr=proxy_addr, headers=headers, json_data=data, abroad=True
    )
    json_str = _get_str_response(json_str)
    json_data = json.loads(json_str)
    # token(value) 与 signature 是拿到 HLS master 地址的必需票据，缺一则 usher 接口返回 403/签名无效。
    token = json_data["data"]["streamPlaybackAccessToken"]["value"]
    sign = json_data["data"]["streamPlaybackAccessToken"]["signature"]

    anchor_name, live_status = await get_twitchtv_room_info(
        url=url, token=token, proxy_addr=proxy_addr, cookies=cookies
    )
    result: dict[str, object] = {"anchor_name": anchor_name, "is_live": live_status}
    if live_status:
        # 动态生成播放会话 ID，替代原硬编码的两个过期会话 ID
        play_session_id = _generate_twitch_play_session_id()
        params = {
            # acmb="e30=" 是 base64 后的空 JSON 对象（{}），为 usher 接口的约定占位参数，不要改成其它值。
            "acmb": "e30=",
            "allow_source": "true",
            "browser_family": "firefox",
            "browser_version": "124.0",
            "cdm": "wv",
            "fast_bread": "true",
            "os_name": "Windows",
            "os_version": "NT%2010.0",
            # p="3553732" 是写死的客户端标识；play_session_id 改为每轮动态生成（原硬编码值已过期）。
            "p": "3553732",
            "platform": "web",
            "play_session_id": play_session_id,
            "player_backend": "mediaplayer",
            "player_version": "1.28.0-rc.1",
            "playlist_include_framerate": "true",
            "reassignments_supported": "true",
            # sig/token 来自上一步 GQL，拼到 query 串作为 URL 签名，缺失 usher 直接拒签。
            "sig": sign,
            "token": token,
            "transcode_mode": "cbr_v1",
        }
        access_key = urllib.parse.urlencode(params)
        m3u8_url = f"https://usher.ttvnw.net/api/channel/hls/{uid}.m3u8?{access_key}"
        play_url_list = await get_play_url_list(m3u8=m3u8_url, proxy=proxy_addr, header=headers, abroad=True)
        result |= {"m3u8_url": m3u8_url, "play_url_list": play_url_list}
    return result


@trace_error_decorator
async def get_liveme_stream_url(
    url: str, proxy_addr: OptionalStr = None, cookies: OptionalStr = None
) -> dict[str, object]:
    # 获取 LiveMe 直播流地址
    # 解析链路：og:url 取 room_id → liveme.js 生成 lm-s-sign → queryinfosimple；
    # status=="0"(字符串) 取流；返回 is_live + m3u8 + flv + record_url；缺 room_id 回原 URL 继续。
    headers = {
        "origin": "https://www.liveme.com",
        "referer": "https://www.liveme.com",
        "user-agent": "ios/7.830 (ios 17.0; ; iPhone 15 (A2846/A3089/A3090/A3092))",
    }
    # 调用方透传 cookie 时优先采用；否则走游客态/自动获取凭据（各平台未登录态取流能力不一，部分更易被风控）
    if cookies:
        headers["Cookie"] = cookies

    # 分享短链/主播主页 URL 不含 index.html，需先抓页面从 og:url 还原成带 room_id 的真实直播页地址；
    # 已是 index.html 直链则直接从中抠 room_id，无需额外页面请求。
    # 分享短链/主页不含 index.html，需先抓页从 og:url 还原带 room_id 的真实直播页
    if "index.html" not in url:
        html_str = await async_req(url, proxy_addr=proxy_addr, headers=headers, abroad=True)
        html_str = _get_str_response(html_str)
        match_url = re.search('<meta property="og:url" content="(.*?)">', html_str)
        if match_url:
            url = match_url.group(1)

    room_id = url.split("/index.html")[0].rsplit("/", maxsplit=1)[-1]
    with open(f"{JS_SCRIPT_PATH}/liveme.js", encoding="utf-8") as f:
        liveme_js = f.read()
    sign_data = execjs.compile(liveme_js).call("sign", room_id, f"{JS_SCRIPT_PATH}/crypto-js.min.js")
    lm_s_sign = sign_data.pop("lm_s_sign")
    tongdun_black_box = sign_data.pop("tongdun_black_box")
    platform = sign_data.pop("os")
    headers["lm-s-sign"] = lm_s_sign

    params = {
        "alias": "liveme",
        "tongdun_black_box": tongdun_black_box,
        "os": platform,
    }

    api = f"https://live.liveme.com/live/queryinfosimple?{urllib.parse.urlencode(params)}"
    json_str = await async_req(api, data=sign_data, proxy_addr=proxy_addr, headers=headers, abroad=True)
    json_str = _get_str_response(json_str)
    json_data = json.loads(json_str)
    stream_data = json_data["data"]["video_info"]
    anchor_name = stream_data["uname"]
    live_status = stream_data["status"]
    result: dict[str, object] = {"anchor_name": anchor_name, "is_live": False}
    # LiveMe 用字符串 "0" 表示在播（注意是字符串而非数字），"1" 等表示离线/其它状态。
    # LiveMe 用字符串 "0" 表示在播（注意是字符串而非数字）
    if live_status == "0":
        m3u8_url = stream_data["hlsvideosource"]
        flv_url = stream_data["videosource"]
        result |= {"is_live": True, "m3u8_url": m3u8_url, "flv_url": flv_url, "record_url": m3u8_url or flv_url}
    return result


async def get_huajiao_sn(
    url: str, cookies: OptionalStr = None, proxy_addr: OptionalStr = None
) -> tuple[str, str, str, str] | None:
    # 获取花椒直播流 SN 参数
    headers = {
        "accept-language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
        "referer": "https://www.huajiao.com/",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:148.0) Gecko/20100101 Firefox/148.0",
    }

    # 调用方透传 cookie 时优先采用；否则走游客态/自动获取凭据（各平台未登录态取流能力不一，部分更易被风控）
    if cookies:
        headers["Cookie"] = cookies

    live_id = _safe_extract_id(url)
    api = f"https://www.huajiao.com/l/{live_id}"
    try:
        html_str = await async_req(url=api, proxy_addr=proxy_addr, headers=headers)
        html_str = _get_str_response(html_str)
        json_str_match = re.search("var feed = (.*?});", html_str)
        if not json_str_match:
            raise ValueError("Failed to find feed data")
        json_str = json_str_match.group(1)
        json_data = json.loads(json_str)
        sn = json_data["feed"]["sn"]
        uid = json_data["author"]["uid"]
        nickname = json_data["author"]["nickname"]
        live_id = _safe_extract_id(url)
        return nickname, sn, uid, live_id
    except Exception:
        # 花椒直播间地址不固定（短链会失效），解析失败时直接把该 URL 在配置文件里注释掉（加 # 前缀），
        # 避免主循环反复重试无效地址；这是少数会写回配置文件的分支，副作用需留意。
        utils.replace_url(f"{script_path}/config/URL_config.ini", old=url, new="#" + url)
        raise RuntimeError(
            "Failed to retrieve live room data, the Huajiao live room address is not fixed, please use "
            "the anchor's homepage address for recording."
        )


async def get_huajiao_user_info(
    url: str, cookies: OptionalStr = None, proxy_addr: OptionalStr = None
) -> OptionalStreamDict:
    # 获取花椒主播用户信息
    headers = {
        "accept-language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
        "referer": "https://www.huajiao.com/",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:148.0) Gecko/20100101 Firefox/148.0",
    }

    # 调用方透传 cookie 时优先采用；否则走游客态/自动获取凭据（各平台未登录态取流能力不一，部分更易被风控）
    if cookies:
        headers["Cookie"] = cookies

    # 花椒 user/ 主页入口：按 uid 查主播 feeds 找在播 live；否则走短链重定向兜底
    if "user" in url:
        uid = url.split("?")[0].split("user/")[1]
        params = {
            "uid": uid,
            "fmt": "json",
            "_": str(int(time.time() * 1000)),
        }

        api = f"https://webh.huajiao.com/User/getUserFeeds?{urllib.parse.urlencode(params)}"
        json_str = await async_req(url=api, proxy_addr=proxy_addr, headers=headers)
        json_str = _get_str_response(json_str)
        json_data = json.loads(json_str)

        html_str = await async_req(url=f"https://www.huajiao.com/user/{uid}", proxy_addr=proxy_addr, headers=headers)
        html_str = _get_str_response(html_str)
        anchor_name_match = re.search("<title>(.*?)的主页.*</title>", html_str)
        anchor_name = anchor_name_match.group(1) if anchor_name_match else ""
        feeds = json_data.get("data", {}).get("feeds", [])
        if json_data.get("data") and feeds and "sn" in feeds[0].get("feed", {}):
            feed = feeds[0]["feed"]
            return {
                "anchor_name": anchor_name,
                "title": feed["title"],
                "is_live": True,
                "sn": feed["sn"],
                "liveid": feed["relateid"],
                "uid": uid,
            }
        else:
            return {"anchor_name": anchor_name, "is_live": False}
    return None


async def get_huajiao_stream_url_app(
    url: str, proxy_addr: OptionalStr = None, cookies: OptionalStr = None
) -> OptionalStreamDict:
    # 获取花椒 App 端直播流地址
    # errmsg 非空或 creatime 缺失即视为地址失效（返回 None，触发上层 get_huajiao_stream_url 回退主页地址）；
    # 返回的 dict 恒带 is_live=True（能取到即表示在播），sn/liveid/uid 供后续 substream 签名接口拼参。
    headers = {
        "User-Agent": "living/9.4.0 (com.huajiao.seeding; build:2410231746; iOS 17.0.0) Alamofire/9.4.0",
        "accept-language": "zh-Hans-US;q=1.0",
        "sdk_version": "1",
    }
    # 调用方透传 cookie 时优先采用；否则走游客态/自动获取凭据（各平台未登录态取流能力不一，部分更易被风控）
    if cookies:
        headers["Cookie"] = cookies
    room_id = _safe_extract_id(url)
    api = f"https://live.huajiao.com/feed/getFeedInfo?relateid={room_id}"
    json_str = await async_req(api, proxy_addr=proxy_addr, headers=headers)
    json_str = _get_str_response(json_str)
    json_data = json.loads(json_str)

    # errmsg 非空或 creatime 缺失即地址失效，返回 None 触发上层回退主页地址
    if json_data["errmsg"] or not json_data["data"].get("creatime"):
        print(
            "Failed to retrieve live room data, the Huajiao live room address is not fixed, please manually change "
            "the address for recording."
        )
        return None
    data = json_data["data"]
    return {
        "anchor_name": data["author"]["nickname"],
        "title": data["feed"]["title"],
        "is_live": True,
        "sn": data["feed"]["sn"],
        "liveid": data["feed"]["relateid"],
        "uid": data["author"]["uid"],
    }


@trace_error_decorator
async def get_huajiao_stream_url(
    url: str, proxy_addr: OptionalStr = None, cookies: OptionalStr = None
) -> dict[str, object]:
    # 获取花椒直播流地址
    # 解析链路：user/ 主页或短链重定向 → get_huajiao_user_info / get_huajiao_stream_url_app 拿 sn；
    # 再 substream 接口取 h264_url；返回 is_live + flv + record_url；地址失效会回退主页地址。
    headers = {
        "accept-language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
        "referer": "https://www.huajiao.com/",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:148.0) Gecko/20100101 Firefox/148.0",
    }
    # 调用方透传 cookie 时优先采用；否则走游客态/自动获取凭据（各平台未登录态取流能力不一，部分更易被风控）
    if cookies:
        headers["Cookie"] = cookies

    result: dict[str, object] = {"anchor_name": "", "is_live": False}

    # 花椒两条入口：user/ 主页需 cookie 取信息，否则短链重定向解析
    if "user/" in url:
        if not cookies:
            return result
        room_data = await get_huajiao_user_info(url, cookies, proxy_addr)
    else:
        url_result = await async_req(url, proxy_addr=proxy_addr, headers=headers, redirect_url=True)
        if isinstance(url_result, str):
            url = url_result
        else:
            url = "https://www.huajiao.com"

        # 重定向落到花椒首页说明短链失效，提示换主页地址按未开播返回
        if url.rstrip("/") == "https://www.huajiao.com":
            print(
                "Failed to retrieve live room data, the Huajiao live room address is not fixed, please manually change "
                "the address for recording."
            )
            return result
        room_data = await get_huajiao_stream_url_app(url, proxy_addr, cookies)

    if room_data:
        result["anchor_name"] = room_data.pop("anchor_name")
        live_status = room_data.pop("is_live")

        if live_status:
            result["title"] = room_data.pop("title")
            params = {"time": int(time.time() * 1000), "version": "1.0.0", **room_data, "encode": "h265"}

            api = f"https://live.huajiao.com/live/substream?{urllib.parse.urlencode(params)}"
            json_str = await async_req(url=api, proxy_addr=proxy_addr, headers=headers)
            json_str = _get_str_response(json_str)
            json_data = json.loads(json_str)
            result |= {
                "is_live": True,
                "flv_url": json_data["data"]["h264_url"],
                "record_url": json_data["data"]["h264_url"],
            }
    return result


@trace_error_decorator
async def get_liuxing_stream_url(
    url: str, proxy_addr: OptionalStr = None, cookies: OptionalStr = None
) -> dict[str, object]:
    # 获取流星直播流地址
    # live_stat==1 为开播（0 为未播）；flv_url 直拼固定 CDN host txpull1.5see.com/{idx}/{liveId}.flv，
    # 该平台仅单路 FLV、无 HLS 候选，故同一地址同时作 record_url。
    headers = {
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
        "Referer": "https://wap.7u66.com/198189?promoters=0",
        "User-Agent": "ios/7.830 (ios 17.0; ; iPhone 15 (A2846/A3089/A3090/A3092))",
    }
    # 调用方透传 cookie 时优先采用；否则走游客态/自动获取凭据（各平台未登录态取流能力不一，部分更易被风控）
    if cookies:
        headers["Cookie"] = cookies

    room_id = _safe_extract_id(url)
    params = {"promoters": "0", "roomidx": room_id, "currentUrl": f"https://www.7u66.com/{room_id}?promoters=0"}
    api = f"https://wap.7u66.com/api/ui/room/v1.0.0/live.ashx?{urllib.parse.urlencode(params)}"
    json_str = await async_req(url=api, proxy_addr=proxy_addr, headers=headers)
    json_str = _get_str_response(json_str)
    json_data = json.loads(json_str)
    room_info = json_data["data"]["roomInfo"]
    anchor_name = room_info["nickname"]
    live_status = room_info["live_stat"]
    result: dict[str, object] = {"anchor_name": anchor_name, "is_live": False}
    if live_status == 1:
        idx = room_info["idx"]
        live_id = room_info["liveId1"]
        flv_url = f"https://txpull1.5see.com/live/{idx}/{live_id}.flv"
        result |= {"is_live": True, "flv_url": flv_url, "record_url": flv_url}
    return result


@trace_error_decorator
async def get_showroom_stream_data(
    url: str, proxy_addr: OptionalStr = None, cookies: OptionalStr = None
) -> dict[str, object]:
    # 获取 ShowRoom 直播流数据
    # 解析链路：/room/profile 或主页抠 room_id → live_info → live_status==2 才请求 streaming_url；
    # 返回 is_live + m3u8 + play_url_list（CDN 实测降级 http）；未开播不取流。
    headers = {
        "accept-language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:148.0) Gecko/20100101 Firefox/148.0",
    }
    # 调用方透传 cookie 时优先采用；否则走游客态/自动获取凭据（各平台未登录态取流能力不一，部分更易被风控）
    if cookies:
        headers["Cookie"] = cookies

    # ShowRoom 两条入口：profile 直链抠 room_id，否则抓主页找 profile 链接
    if "/room/profile" in url:
        room_id = url.split("room_id=")[-1]
    else:
        html_str = await async_req(url, proxy_addr=proxy_addr, headers=headers, abroad=True)
        html_str = _get_str_response(html_str)
        room_id_match = re.search('href="/room/profile\\?room_id=(.*?)"', html_str)
        if not room_id_match:
            raise ValueError("Failed to find room_id")
        room_id = room_id_match.group(1)
    info_api = f"https://www.showroom-live.com/api/live/live_info?room_id={room_id}"
    json_str = await async_req(info_api, proxy_addr=proxy_addr, headers=headers, abroad=True)
    json_str = _get_str_response(json_str)
    json_data = json.loads(json_str)
    anchor_name = json_data["room_name"]
    result: dict[str, object] = {"anchor_name": anchor_name, "is_live": False}
    live_status = json_data["live_status"]
    # ShowRoom 用 live_status==2 表示开播（1 为离线/准备中），与多数平台的 1 不一致。
    if live_status == 2:
        result["is_live"] = True
        web_api = f"https://www.showroom-live.com/api/live/streaming_url?room_id={room_id}&abr_available=1"
        json_str = await async_req(web_api, proxy_addr=proxy_addr, headers=headers, abroad=True)
        json_str = _get_str_response(json_str)
        if json_str:
            json_data = json.loads(json_str)
            streaming_url_list = json_data["streaming_url_list"]

            for i in streaming_url_list:
                if i["type"] == "hls_all":
                    m3u8_url = i["url"]
                    result["m3u8_url"] = m3u8_url
                    if m3u8_url:
                        m3u8_url_list = await get_play_url_list(m3u8_url, proxy=proxy_addr, header=headers, abroad=True)
                        if m3u8_url_list:
                            result["play_url_list"] = [
                                f"{m3u8_url.rsplit('/', maxsplit=1)[0]}/{i}" for i in m3u8_url_list
                            ]
                        else:
                            result["play_url_list"] = [m3u8_url]
                        _play_url_list = cast(list[str], result["play_url_list"])
                        # ShowRoom CDN 实测 https 拉流不稳定，统一降级为 http（与 huya/popkontv 同思路）。
                        result["play_url_list"] = [i.replace("https://", "http://") for i in _play_url_list]
                        break
    return result


@trace_error_decorator
async def get_acfun_sign_params(
    proxy_addr: OptionalStr = None, cookies: OptionalStr = None
) -> tuple[object, str, object]:
    # 计算 Acfun 请求签名参数
    # 返回 (user_id, did, visitor_st) 游客三件套，是 startPlay 签名必需票据；
    # did 每次随机生成（web_ 前缀是 AcFun 游客设备标识），visitor_st 为登录接口下发的临时令牌，
    # 缺失会致 startPlay 返回 401（风控）。
    did = f"web_{utils.generate_random_string(16)}"
    headers = {
        "referer": "https://live.acfun.cn/",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:148.0) Gecko/20100101 Firefox/148.0",
        "cookie": f"_did={did};",
    }
    # 调用方透传 cookie 时优先采用；否则走游客态/自动获取凭据（各平台未登录态取流能力不一，部分更易被风控）
    if cookies:
        headers["Cookie"] = cookies
    data = {
        "sid": "acfun.api.visitor",
    }
    api = "https://id.app.acfun.cn/rest/app/visitor/login"
    json_str = await async_req(api, data=data, proxy_addr=proxy_addr, headers=headers)
    json_str = _get_str_response(json_str)
    json_data = json.loads(json_str)
    user_id = json_data["userId"]
    visitor_st = json_data["acfun.api.visitor_st"]
    return user_id, did, visitor_st


@trace_error_decorator
async def get_acfun_stream_data(
    url: str, proxy_addr: OptionalStr = None, cookies: OptionalStr = None
) -> dict[str, object]:
    # 获取 Acfun 直播流数据
    # 解析链路：userInfo 拿 nickname + liveId → get_acfun_sign_params 游客三件套 → startPlay 取 FLV；
    # 返回 is_live + play_url_list（按码率排序）+ title；liveId 缺失（"liveId" not in profile）按未开播。
    headers = {
        "referer": "https://live.acfun.cn/live/17912421",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:148.0) Gecko/20100101 Firefox/148.0",
    }
    # 调用方透传 cookie 时优先采用；否则走游客态/自动获取凭据（各平台未登录态取流能力不一，部分更易被风控）
    if cookies:
        headers["Cookie"] = cookies

    author_id = _safe_extract_id(url)
    user_info_api = f"https://live.acfun.cn/rest/pc-direct/user/userInfo?userId={author_id}"
    json_str = await async_req(user_info_api, proxy_addr=proxy_addr, headers=headers)
    json_str = _get_str_response(json_str)
    json_data = json.loads(json_str)
    anchor_name = json_data["profile"]["name"]
    # AcFun 用 profile 是否含 liveId 判定开播（有 liveId 才在播）
    status = "liveId" in json_data["profile"]
    result: dict[str, object] = {"anchor_name": anchor_name, "is_live": False}
    if status:
        result["is_live"] = True
        user_id, did, visitor_st = await get_acfun_sign_params(proxy_addr=proxy_addr, cookies=cookies)
        params = {
            "subBiz": "mainApp",
            "kpn": "ACFUN_APP",
            "kpf": "PC_WEB",
            "userId": user_id,
            "did": did,
            "acfun.api.visitor_st": visitor_st,
        }

        data = {
            "authorId": author_id,
            "pullStreamType": "FLV",
        }
        play_api = f"https://api.kuaishouzt.com/rest/zt/live/web/startPlay?{urllib.parse.urlencode(params)}"
        json_str = await async_req(play_api, data=data, proxy_addr=proxy_addr, headers=headers)
        json_str = _get_str_response(json_str)
        json_data = json.loads(json_str)
        live_title = json_data["data"]["caption"]
        videoPlayRes = json_data["data"]["videoPlayRes"]
        play_url_list = json.loads(videoPlayRes)["liveAdaptiveManifest"][0]["adaptationSet"]["representation"]
        play_url_list = sorted(play_url_list, key=itemgetter("bitrate"), reverse=True)
        result |= {"play_url_list": play_url_list, "title": live_title}
    return result


@trace_error_decorator
async def get_changliao_stream_url(
    url: str, proxy_addr: OptionalStr = None, cookies: OptionalStr = None
) -> dict[str, object]:
    # 获取畅聊直播流地址
    # 解析链路：live.ashx 拿 nickname + live_stat → get_live_domain 从页面 config 抠 flv/hls 域名拼 liveID；
    # live_stat==1 取流；返回 is_live + m3u8 + flv + record_url；拉流域名随部署变化不写死。
    headers = {
        "User-Agent": "ios/7.830 (ios 17.0; ; iPhone 15 (A2846/A3089/A3090/A3092))",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-CN,zh;q=0.8,zh-TW;q=0.7,zh-HK;q=0.5,en-US;q=0.3,en;q=0.2",
        "Referer": "https://wap.tlclw.com/phone/15777?promoters=0",
    }
    # 调用方透传 cookie 时优先采用；否则走游客态/自动获取凭据（各平台未登录态取流能力不一，部分更易被风控）
    if cookies:
        headers["Cookie"] = cookies

    room_id = url.split("?")[0].rsplit("/", maxsplit=1)[-1]
    params = {
        "roomidx": room_id,
        "currentUrl": f"https://wap.tlclw.com/{room_id}",
    }
    play_api = f"https://wap.tlclw.com/api/ui/room/v1.0.0/live.ashx?{urllib.parse.urlencode(params)}"
    json_str = await async_req(play_api, proxy_addr=proxy_addr, headers=headers)
    json_str = _get_str_response(json_str)
    json_data = json.loads(json_str)
    anchor_name = json_data["data"]["roomInfo"]["nickname"]
    live_status = json_data["data"]["roomInfo"]["live_stat"]

    async def get_live_domain(page_url: str) -> tuple[str, str]:
        # 拉流域名不能写死：该平台 CDN 域名随部署变化，必须从直播间页内 var config 里抠
        # domainpullstream_flv / domainpullstream_hls，再用 liveID 拼出最终地址。
        # 注意：原注释写「映客」是复制粘贴遗留，此处实际服务于畅聊，域名取自当前房间页。
        html_str = await async_req(page_url, proxy_addr=proxy_addr, headers=headers)
        html_str = _get_str_response(html_str)
        config_json_match = re.findall("var config = (.*?)config.webskins", html_str, re.DOTALL)
        if not config_json_match:
            raise ValueError("Failed to find config data")
        config_json_str = config_json_match[0].rsplit(";", maxsplit=1)[0].strip()
        config_json_data = json.loads(config_json_str)
        stream_flv_domain = config_json_data["domainpullstream_flv"]
        stream_hls_domain = config_json_data["domainpullstream_hls"]
        return stream_flv_domain, stream_hls_domain

    result: dict[str, object] = {"anchor_name": anchor_name, "is_live": False}
    if live_status == 1:
        flv_domain, hls_domain = await get_live_domain(url)
        live_id = json_data["data"]["roomInfo"]["liveID"]
        flv_url = f"{flv_domain}/{live_id}.flv"
        m3u8_url = f"{hls_domain}/{live_id}.m3u8"
        result |= {"is_live": True, "m3u8_url": m3u8_url, "flv_url": flv_url, "record_url": flv_url}
    return result


@trace_error_decorator
async def get_yingke_stream_url(
    url: str, proxy_addr: OptionalStr = None, cookies: OptionalStr = None
) -> dict[str, object]:
    # 获取映客直播流地址
    # 解析链路：url 抠 uid+id → live_share_pc → status==1 取 hls_stream_addr/stream_addr；
    # 返回 is_live + m3u8 + flv + record_url；缺 uid/id 抛 ValueError 交由装饰器重试。
    headers = {
        "Referer": "https://www.inke.cn/",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:148.0) Gecko/20100101 Firefox/148.0",
    }
    # 调用方透传 cookie 时优先采用；否则走游客态/自动获取凭据（各平台未登录态取流能力不一，部分更易被风控）
    if cookies:
        headers["Cookie"] = cookies

    parsed_url = urllib.parse.urlparse(url)
    query_params = urllib.parse.parse_qs(parsed_url.query)
    uid = query_params.get("uid", [""])[0]
    live_id = query_params.get("id", [""])[0]
    # URL 缺 uid/id 无法定位映客房间，显式报错交由装饰器重试
    if not uid or not live_id:
        raise ValueError("Failed to extract uid or live_id from inke URL")
    params = {
        "uid": uid,
        "id": live_id,
        "_t": str(int(time.time())),
    }

    api = f"https://webapi.busi.inke.cn/web/live_share_pc?{urllib.parse.urlencode(params)}"
    json_str = await async_req(api, proxy_addr=proxy_addr, headers=headers)
    json_str = _get_str_response(json_str)
    json_data = json.loads(json_str)
    anchor_name = json_data["data"]["media_info"]["nick"]
    live_status = json_data["data"]["status"]

    result: dict[str, object] = {"anchor_name": anchor_name, "is_live": False}
    if live_status == 1:
        m3u8_url = json_data["data"]["live_addr"][0]["hls_stream_addr"]
        flv_url = json_data["data"]["live_addr"][0]["stream_addr"]
        result |= {"is_live": True, "m3u8_url": m3u8_url, "flv_url": flv_url, "record_url": m3u8_url}
    return result


@trace_error_decorator
async def get_yinbo_stream_url(
    url: str, proxy_addr: OptionalStr = None, cookies: OptionalStr = None
) -> dict[str, object]:
    # 获取音播直播流地址
    # 解析链路：live.ashx 拿 nickname + live_stat → get_live_domain 抠域名拼 liveID；
    # live_stat==1 取流；返回 is_live + m3u8 + flv + record_url；拉流域名不写死（随部署变化）。
    headers = {
        "User-Agent": "ios/7.830 (ios 17.0; ; iPhone 15 (A2846/A3089/A3090/A3092))",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-CN,zh;q=0.8,zh-TW;q=0.7,zh-HK;q=0.5,en-US;q=0.3,en;q=0.2",
        "Referer": "https://live.ybw1666.com/800005143?promoters=0",
    }
    # 调用方透传 cookie 时优先采用；否则走游客态/自动获取凭据（各平台未登录态取流能力不一，部分更易被风控）
    if cookies:
        headers["Cookie"] = cookies

    room_id = url.split("?")[0].rsplit("/", maxsplit=1)[-1]
    params = {
        "roomidx": room_id,
        "currentUrl": f"https://wap.ybw1666.com/{room_id}",
    }
    play_api = f"https://wap.ybw1666.com/api/ui/room/v1.0.0/live.ashx?{urllib.parse.urlencode(params)}"
    json_str = await async_req(play_api, proxy_addr=proxy_addr, headers=headers)
    json_str = _get_str_response(json_str)
    json_data = json.loads(json_str)
    room_data = json_data["data"]["roomInfo"]
    anchor_name = room_data["nickname"]
    live_status = room_data["live_stat"]

    async def get_live_domain(page_url: str) -> tuple[str, str]:
        # 拉流域名不能写死：从当前房间页内 var config 抠出 flv/hls 拉流域名再拼 liveID。
        # 原注释「知乎」为复制粘贴遗留，此处服务于音播（ybw1666.com）。
        html_str = await async_req(page_url, proxy_addr=proxy_addr, headers=headers)
        html_str = _get_str_response(html_str)
        config_json_match = re.findall("var config = (.*?)config.webskins", html_str, re.DOTALL)
        if not config_json_match:
            raise ValueError("Failed to find config data")
        config_json_str = config_json_match[0].rsplit(";", maxsplit=1)[0].strip()
        config_json_data = json.loads(config_json_str)
        stream_flv_domain = config_json_data["domainpullstream_flv"]
        stream_hls_domain = config_json_data["domainpullstream_hls"]
        return stream_flv_domain, stream_hls_domain

    result: dict[str, object] = {"anchor_name": anchor_name, "is_live": False}
    if live_status == 1:
        flv_domain, hls_domain = await get_live_domain(url)
        live_id = room_data["liveID"]
        flv_url = f"{flv_domain}/{live_id}.flv"
        m3u8_url = f"{hls_domain}/{live_id}.m3u8"
        result |= {"is_live": True, "m3u8_url": m3u8_url, "flv_url": flv_url, "record_url": flv_url}
    return result


@trace_error_decorator
async def get_zhihu_stream_url(
    url: str, proxy_addr: OptionalStr = None, cookies: OptionalStr = None
) -> dict[str, object]:
    # 获取知乎直播流地址
    # 解析链路：people/<id> 主页 profile 拿 theater_url → 直播页 js-initialData 抠 playInfo；
    # status==1 取流；返回 is_live + m3u8 + flv + record_url；无在映剧场直接回未开播。
    headers = {
        "accept-language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:148.0) Gecko/20100101 Firefox/148.0",
    }
    # 调用方透传 cookie 时优先采用；否则走游客态/自动获取凭据（各平台未登录态取流能力不一，部分更易被风控）
    if cookies:
        headers["Cookie"] = cookies

    # 知乎主播主页（people/<id>）不直接是直播间：先查 profile 拿到 living_theater 的 theater_url，
    # 再跳到该直播页解析；若没有在映剧场说明未开播，提前返回避免无谓的页面请求。
    if "people/" in url:
        user_id = url.split("people/")[1]
        api = f"https://api.zhihu.com/people/{user_id}/profile?profile_new_version="
        json_str = await async_req(api, proxy_addr=proxy_addr, headers=headers)
        json_str = _get_str_response(json_str)
        json_data = json.loads(json_str)
        drama = json_data.get("drama") or {}
        living_theater = drama.get("living_theater") or {}
        # 未开播（无 drama/无在映剧场）直接返回，不再发起后续页面请求
        # 无在映剧场即未开播，提前返回避免无谓页面请求
        if not living_theater.get("theater_url"):
            return {"anchor_name": "", "is_live": False}
        live_page_url = living_theater["theater_url"]
    else:
        live_page_url = url

    web_id = live_page_url.split("?")[0].rsplit("/", maxsplit=1)[-1]
    html_str = await async_req(live_page_url, proxy_addr=proxy_addr, headers=headers)
    html_str = _get_str_response(html_str)
    json_str2_match = re.findall('<script id="js-initialData" type="text/json">(.*?)</script>', html_str)
    if not json_str2_match:
        raise ValueError("Failed to find initialData")
    json_str2 = json_str2_match[0]
    json_data2 = json.loads(json_str2)
    live_data = json_data2["initialState"]["theater"]["theaters"][web_id]
    anchor_name = live_data["actor"]["name"]
    live_status = live_data["drama"]["status"]
    result: dict[str, object] = {"anchor_name": anchor_name, "is_live": False}
    if live_status == 1:
        live_title = live_data["theme"]
        play_url = live_data["drama"]["playInfo"]
        result |= {
            "is_live": True,
            "title": live_title,
            "m3u8_url": play_url["hlsUrl"],
            "flv_url": play_url["playUrl"],
            "record_url": play_url["hlsUrl"],
        }
    return result


@trace_error_decorator
async def get_chzzk_stream_data(
    url: str, proxy_addr: OptionalStr = None, cookies: OptionalStr = None
) -> dict[str, object]:
    # 获取 CHZZK 直播流数据
    # live_status=="OPEN" 字符串表示开播（非数字 1）；play_data 由 livePlaybackJson 解析、
    # media[0].path 为 master m3u8，再经 get_play_url_list 拆出多清晰度候选。
    headers = {
        "accept": "application/json, text/plain, */*",
        "accept-language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
        "origin": "https://chzzk.naver.com",
        "referer": "https://chzzk.naver.com/live/458f6ec20b034f49e0fc6d03921646d2",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:148.0) Gecko/20100101 Firefox/148.0",
    }
    # 调用方透传 cookie 时优先采用；否则走游客态/自动获取凭据（各平台未登录态取流能力不一，部分更易被风控）
    if cookies:
        headers["Cookie"] = cookies

    room_id = url.split("?")[0].rsplit("/", maxsplit=1)[-1]
    play_api = f"https://api.chzzk.naver.com/service/v3/channels/{room_id}/live-detail"
    json_str = await async_req(play_api, proxy_addr=proxy_addr, headers=headers, abroad=True)
    json_str = _get_str_response(json_str)
    json_data = json.loads(json_str)
    live_data = json_data["content"]
    anchor_name = live_data["channel"]["channelName"]
    live_status = live_data["status"]

    result: dict[str, object] = {"anchor_name": anchor_name, "is_live": False}
    # CHZZK 用字符串 "OPEN" 表示开播（非数字 1）
    if live_status == "OPEN":
        play_data = json.loads(live_data["livePlaybackJson"])
        m3u8_url = play_data["media"][0]["path"]
        m3u8_url_list = await get_play_url_list(m3u8_url, proxy=proxy_addr, header=headers, abroad=True)
        prefix = m3u8_url.split("?")[0].rsplit("/", maxsplit=1)[0]
        m3u8_url_list = [prefix + "/" + i for i in m3u8_url_list]
        result |= {"is_live": True, "m3u8_url": m3u8_url, "play_url_list": m3u8_url_list}
    return result


@trace_error_decorator
async def get_haixiu_stream_url(
    url: str, proxy_addr: OptionalStr = None, cookies: OptionalStr = None
) -> dict[str, object]:
    # 获取嗨秀直播流地址（含签名）
    headers = {
        "origin": "https://www.haixiutv.com",
        "referer": "https://www.haixiutv.com/",
        "user-agent": "ios/7.830 (ios 17.0; ; iPhone 15 (A2846/A3089/A3090/A3092))",
    }
    # 调用方透传 cookie 时优先采用；否则走游客态/自动获取凭据（各平台未登录态取流能力不一，部分更易被风控）
    if cookies:
        headers["Cookie"] = cookies

    room_id = url.split("?")[0].rsplit("/", maxsplit=1)[-1]
    # access_token 是两段写死的「双重 URL 编码」凭据（嗨秀/嗨嗨两套各一个），调用前再 unquote 两次还原。
    # 该 token 长期有效、与账号无关，是接口鉴权的关键；改动会导致 401。lehaitv 走另一域名与 origin。
    # 嗨秀/嗨嗨两套域名各对应一个写死双重编码 token，按域名选择
    if "haixiutv" in url:
        access_token = "pLXSC%252FXJ0asc1I21tVL5FYZhNJn2Zg6d7m94umCnpgL%252BuVm31GQvyw%253D%253D"
    else:
        access_token = "s7FUbTJ%252BjILrR7kicJUg8qr025ZVjd07DAnUQd8c7g%252Fo4OH9pdSX6w%253D%253D"

    params = {"accessToken": access_token, "tku": "3000006", "c": "10138100100000", "_st1": int(time.time() * 1000)}
    with open(f"{JS_SCRIPT_PATH}/haixiu.js", encoding="utf-8") as f:
        haixiu_js = f.read()
    # 用 haixiu.js 对参数做签名得到 _ajaxData1（前端 crypto-js 逻辑迁移到 node 执行）。
    ajax_data = execjs.compile(haixiu_js).call("sign", params, f"{JS_SCRIPT_PATH}/crypto-js.min.js")

    params["accessToken"] = urllib.parse.unquote(urllib.parse.unquote(access_token))
    params["_ajaxData1"] = ajax_data
    params["_"] = int(time.time() * 1000)

    if "haixiutv" in url:
        api = f"https://service.haixiutv.com/v2/room/{room_id}/media/advanceInfoRoom?{urllib.parse.urlencode(params)}"
    else:
        headers["origin"] = "https://www.lehaitv.com"
        headers["referer"] = "https://www.lehaitv.com"
        api = f"https://service.lehaitv.com/v2/room/{room_id}/media/advanceInfoRoom?{urllib.parse.urlencode(params)}"

    json_str = await async_req(api, proxy_addr=proxy_addr, headers=headers, abroad=True)
    json_str = _get_str_response(json_str)
    json_data = json.loads(json_str)

    stream_data = json_data["data"]
    anchor_name = stream_data["nickname"]
    live_status = stream_data["live_status"]
    result: dict[str, object] = {"anchor_name": anchor_name, "is_live": False}
    # 嗨秀 live_status==1 为开播
    if live_status == 1:
        flv_url = stream_data["media_url_web"]
        result |= {"is_live": True, "flv_url": flv_url, "record_url": flv_url}
    return result


@trace_error_decorator
async def get_vvxqiu_stream_url(
    url: str, proxy_addr: OptionalStr = None, cookies: OptionalStr = None
) -> dict[str, object]:
    # 获取 VV 星球直播流地址
    # 解析链路：get_params 拿 roomId → 两处接口补昵称 → 固定 CDN 模板 m3u8 探测；
    # 响应非空且不含 Not Found 才判开播；返回 is_live + m3u8 + record_url；无 roomId 不探测。
    headers = {
        "User-Agent": "ios/7.830 (ios 17.0; ; iPhone 15 (A2846/A3089/A3090/A3092))",
        "Access-Control-Request-Method": "GET",
        "Origin": "https://h5webcdn-pro.vvxqiu.com",
        "Referer": "https://h5webcdn-pro.vvxqiu.com/",
    }

    # 调用方透传 cookie 时优先采用；否则走游客态/自动获取凭据（各平台未登录态取流能力不一，部分更易被风控）
    if cookies:
        headers["Cookie"] = cookies

    room_id = get_params(url, "roomId")
    api_1 = f"https://h5p.vvxqiu.com/activity-center/fanclub/activity/captain/banner?roomId={room_id}&product=vvstar"
    json_str = await async_req(api_1, proxy_addr=proxy_addr, headers=headers)
    json_str = _get_str_response(json_str)
    json_data = json.loads(json_str)
    anchor_name = json_data["data"]["anchorName"]
    # 第一个 banner 接口对匿名/未登录用户可能不返回昵称，用第二个活动 banner 接口兜底补 memberName；
    # 仍取不到则留空（不影响取流判定，仅标题/昵称缺失）。
    # 首接口匿名用户可能不返回昵称，用第二个 banner 接口补 memberName
    if not anchor_name:
        params = {
            "sessionId": "",
            "userId": "",
            "product": "vvstar",
            "tickToken": "",
            "roomId": room_id,
        }
        json_str = await async_req(
            f"https://h5p.vvxqiu.com/activity-center/halloween2023/banner?{urllib.parse.urlencode(params)}",
            proxy_addr=proxy_addr,
            headers=headers,
        )
        json_str = _get_str_response(json_str)
        json_data = json.loads(json_str)
        anchor_name = json_data["data"]["memberVO"]["memberName"]

    result: dict[str, object] = {"anchor_name": anchor_name, "is_live": False}
    # 房间号缺失时不再探测 m3u8（拼不出有效地址，请求必然无意义）
    # 房间号缺失不再探测 m3u8（拼不出有效地址）
    if not room_id:
        return result
    # 地址是固定 CDN 模板：1400442770 写死前缀 + room_id + room_id[2:] 后缀（取除前两位外的部分），
    # 整条地址由平台约定拼接，缺失/错拼任何一段都只会拿到 "Not Found"。
    m3u8_url = f"https://liveplay-pro.wasaixiu.com/live/1400442770_{room_id}_{room_id[2:]}_single.m3u8"
    resp = await async_req(m3u8_url, proxy_addr=proxy_addr, headers=headers)
    resp = _get_str_response(resp)
    # 空响应也判未直播：此前空串不含 "Not Found" 会误判为开播，故需同时判非空且不含 Not Found。
    # 空响应或含 Not Found 均判未直播（空串不含 Not Found 会误判为开播）
    if resp and "Not Found" not in resp:
        result |= {"is_live": True, "m3u8_url": m3u8_url, "record_url": m3u8_url}
    return result


@trace_error_decorator
async def get_17live_stream_url(
    url: str, proxy_addr: OptionalStr = None, cookies: OptionalStr = None
) -> dict[str, object]:
    # 获取 17Live 直播流地址
    # status==2 为开播（1 为离线），flv 取自 rtmpURLs[0].urlHighQuality；
    # 未取到 status 或 status!=2 时回 is_live=False（默认），不抛错、交由主循环下轮重试。
    headers = {
        "origin": "https://17.live",
        "referer": "https://17.live/",
        "user-agent": "ios/7.830 (ios 17.0; ; iPhone 15 (A2846/A3089/A3090/A3092))",
    }

    # 调用方透传 cookie 时优先采用；否则走游客态/自动获取凭据（各平台未登录态取流能力不一，部分更易被风控）
    if cookies:
        headers["Cookie"] = cookies

    room_id = url.split("?")[0].rsplit("/", maxsplit=1)[-1]
    api_1 = f"https://wap-api.17app.co/api/v1/user/room/{room_id}"
    json_str = await async_req(api_1, proxy_addr=proxy_addr, headers=headers)
    json_str = _get_str_response(json_str)
    json_data = json.loads(json_str)
    anchor_name = json_data["displayName"]
    result: dict[str, object] = {"anchor_name": anchor_name, "is_live": False}
    # 第一个 user/room 接口只给主播名，需再请求 viewers/alive 接口、用 room_id 作为 liveStreamID
    # 换取开播状态与拉流地址；该平台把开播判定与取流分两步，缺一不可。
    json_data = {
        "liveStreamID": room_id,
    }
    api_1 = f"https://wap-api.17app.co/api/v1/lives/{room_id}/viewers/alive"
    json_str = await async_req(api_1, json_data=json_data, proxy_addr=proxy_addr, headers=headers)
    json_str = _get_str_response(json_str)
    json_data = json.loads(json_str)
    live_status = json_data.get("status")
    # 17Live status==2 为开播（1 为离线）
    if live_status and live_status == 2:
        flv_url = json_data["pullURLsInfo"]["rtmpURLs"][0]["urlHighQuality"]
        result |= {"is_live": True, "flv_url": flv_url, "record_url": flv_url}
    return result


@trace_error_decorator
async def get_langlive_stream_url(
    url: str, proxy_addr: OptionalStr = None, cookies: OptionalStr = None
) -> dict[str, object]:
    # 获取浪 Live 直播流地址
    # live_status==1 为开播；flv_url 与 m3u8_url 同源（liveurl/liveurl_hls），该平台 HLS 可用，
    # 故 m3u8 也作为 record_url 候选交给上层按可达性校验，而非只用 FLV。
    headers = {
        "origin": "https://www.lang.live",
        "referer": "https://www.lang.live/",
        "user-agent": "ios/7.830 (ios 17.0; ; iPhone 15 (A2846/A3089/A3090/A3092))",
    }

    # 调用方透传 cookie 时优先采用；否则走游客态/自动获取凭据（各平台未登录态取流能力不一，部分更易被风控）
    if cookies:
        headers["Cookie"] = cookies

    room_id = url.split("?")[0].rsplit("/", maxsplit=1)[-1]
    api_1 = f"https://api.lang.live/langweb/v1/room/liveinfo?room_id={room_id}"
    json_str = await async_req(api_1, proxy_addr=proxy_addr, headers=headers, abroad=True)
    json_str = _get_str_response(json_str)
    json_data = json.loads(json_str)
    live_info = json_data["data"]["live_info"]
    anchor_name = live_info["nickname"]
    live_status = live_info["live_status"]
    result: dict[str, object] = {"anchor_name": anchor_name, "is_live": False}
    # 浪 Live live_status==1 为开播
    if live_status == 1:
        flv_url = json_data["data"]["live_info"]["liveurl"]
        m3u8_url = json_data["data"]["live_info"]["liveurl_hls"]
        result |= {"is_live": True, "m3u8_url": m3u8_url, "flv_url": flv_url, "record_url": m3u8_url}
    return result


@trace_error_decorator
async def get_pplive_stream_url(
    url: str, proxy_addr: OptionalStr = None, cookies: OptionalStr = None
) -> dict[str, object]:
    # 获取飘飘直播流地址
    # living 字段为真即在播；pullUrl 同时作 m3u8 与 record_url（单路 HLS）；
    # catshow 子域走独立 api 域名（api.catshow168.com）并切换 Origin/Referer，否则用默认 pp 域名。
    headers = {
        "Content-Type": "application/json",
        "Origin": "https://m.pp.weimipopo.com",
        "Referer": "https://m.pp.weimipopo.com/",
        "User-Agent": "ios/7.830 (ios 17.0; ; iPhone 15 (A2846/A3089/A3090/A3092))",
    }

    # 调用方透传 cookie 时优先采用；否则走游客态/自动获取凭据（各平台未登录态取流能力不一，部分更易被风控）
    if cookies:
        headers["Cookie"] = cookies

    room_id = get_params(url, "anchorUid")
    req_body = {
        "inviteUuid": "",
        "anchorUuid": room_id,
    }

    # catshow 子域走独立 api 域名并切换 Origin/Referer，否则用默认 pp 域名
    if "catshow" in url:
        api = "https://api.catshow168.com/live/preview"
        headers["Origin"] = "https://h.catshow168.com"
        headers["Referer"] = "https://h.catshow168.com"
    else:
        api = "https://api.pp.weimipopo.com/live/preview"
    json_str = await async_req(api, json_data=req_body, proxy_addr=proxy_addr, headers=headers)
    json_str = _get_str_response(json_str)
    json_data = json.loads(json_str)
    live_info = json_data["data"]
    anchor_name = live_info["name"]
    live_status = live_info["living"]
    result: dict[str, object] = {"anchor_name": anchor_name, "is_live": False}
    # 飘飘 living 字段为真即在播
    if live_status:
        m3u8_url = live_info["pullUrl"]
        result |= {"is_live": True, "m3u8_url": m3u8_url, "record_url": m3u8_url}
    return result


@trace_error_decorator
async def get_6room_stream_url(
    url: str, proxy_addr: OptionalStr = None, cookies: OptionalStr = None
) -> dict[str, object]:
    # 获取六间房直播流地址
    # 解析链路：v.6.cn 抠 rid → coop/mobile inroom → flvtitle 非空取流；
    # 返回 is_live + flv + record_url；无 rid 抛 ValueError，由装饰器按未开播重试。
    headers = {
        "accept-language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
        "referer": "https://ios.6.cn/?ver=8.0.3&build=4",
        "user-agent": "ios/7.830 (ios 17.0; ; iPhone 15 (A2846/A3089/A3090/A3092))",
    }

    # 调用方透传 cookie 时优先采用；否则走游客态/自动获取凭据（各平台未登录态取流能力不一，部分更易被风控）
    if cookies:
        headers["Cookie"] = cookies

    room_id = _safe_extract_id(url)
    html_str = await async_req(f"https://v.6.cn/{room_id}", proxy_addr=proxy_addr, headers=headers)
    html_str = _get_str_response(html_str)
    room_id_match = re.search("rid: '(.*?)',\n\\s+roomid", html_str)
    # 页面 rid 缺失即结构变化，显式报错交由装饰器按未开播重试
    if not room_id_match:
        raise ValueError("Failed to find room_id")
    room_id = room_id_match.group(1)
    data = {
        "av": "3.1",
        "encpass": "",
        "logiuid": "",
        "project": "v6iphone",
        "rate": "1",
        "rid": "",
        "ruid": room_id,
    }
    api = "https://v.6.cn/coop/mobile/index.php?padapi=coop-mobile-inroom.php"
    json_str = await async_req(api, data=data, proxy_addr=proxy_addr, headers=headers)
    json_str = _get_str_response(json_str)
    json_data = json.loads(json_str)
    flv_title = json_data["content"]["liveinfo"]["flvtitle"]
    anchor_name = json_data["content"]["roominfo"]["alias"]
    result: dict[str, object] = {"anchor_name": anchor_name, "is_live": False}
    # flvtitle 非空才是有效在播房间，否则判未直播
    if flv_title:
        flv_url = f"https://wlive.6rooms.com/httpflv/{flv_title}.flv"
        result |= {"is_live": True, "flv_url": flv_url, "record_url": flv_url}
    return result


@trace_error_decorator
async def get_shopee_stream_url(
    url: str, proxy_addr: OptionalStr = None, cookies: OptionalStr = None
) -> dict[str, object]:
    # 获取 Shopee 直播流地址
    # 解析链路：重定向/uid 定 host_suffix → ongoing_live 或 session 接口拿 play_url；
    # status==1 且链接判定在播才取流；返回 is_live + flv + record_url；畸形 URL 直接回未开播。
    headers = {
        "accept": "application/json, text/plain, */*",
        "accept-language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
        "referer": "https://live.shopee.sg/share?from=live&session=802458&share_user_id=",
        "user-agent": "ios/7.830 (ios 17.0; ; iPhone 15 (A2846/A3089/A3090/A3092))",
    }

    # 调用方透传 cookie 时优先采用；否则走游客态/自动获取凭据（各平台未登录态取流能力不一，部分更易被风控）
    if cookies:
        headers["Cookie"] = cookies

    result: dict[str, object] = {"anchor_name": "", "is_live": False}
    is_living = False

    # 非直链且非店铺主页：先解析重定向拿到真实 host/会话
    if "live.shopee" not in url and "uid" not in url:
        url_result = await async_req(url, proxy_addr=proxy_addr, headers=headers, redirect_url=True, abroad=True)
        # 重定向失败（空响应）时保留原 URL 继续解析，避免后续 split 越界
        if isinstance(url_result, str) and url_result:
            url = url_result

    # 畸形 URL（无 host）直接判未直播，不再抛 IndexError
    # 畸形 URL（无 host）：判未直播，避免后续 split 越界
    if "://" not in url or len(url.split("/")) < 3 or not url.split("/")[2]:
        return result

    # 直链用完整 TLD 后缀定位 host；含 uid 的是店铺主页（未必在播）
    if "live.shopee" in url:
        host_suffix = url.split("/")[2].rsplit(".", maxsplit=1)[1]
        # 含 uid 的是店铺主页分享链接（未必在播），不含 uid 的 live.shopee 直链（仅带 session）才视为在播态。
        is_living = get_params(url, "uid") is None
    else:
        # 完整 TLD 后缀：shopee.co.id → "co.id"（只取首段会拼出 live.shopee.shopee 这种无效域名）
        host_suffix = url.split("/")[2].split(".", maxsplit=1)[-1]

    uid = get_params(url, "uid")
    api_host = f"https://live.shopee.{host_suffix}"
    session_id = get_params(url, "session")
    if uid:
        json_str = await async_req(
            f"{api_host}/api/v1/shop_page/live/ongoing?uid={uid}", proxy_addr=proxy_addr, headers=headers, abroad=True
        )
        json_str = _get_str_response(json_str)
        json_data = json.loads(json_str)
        # 店铺有在进行直播才取 session，否则查回放列表兜底
        if json_data["data"]["ongoing_live"]:
            session_id = json_data["data"]["ongoing_live"]["session_id"]
            is_living = True
        else:
            json_str = await async_req(
                f"{api_host}/api/v1/shop_page/live/replay_list?offset=0&limit=1&uid={uid}",
                proxy_addr=proxy_addr,
                headers=headers,
                abroad=True,
            )
            json_str = _get_str_response(json_str)
            json_data = json.loads(json_str)
            # 仅回放无在播：补主播名后按未直播返回
            if json_data["data"]["replay"]:
                result["anchor_name"] = json_data["data"]["replay"][0]["nick_name"]
                return result

    json_str = await async_req(
        f"{api_host}/api/v1/session/{session_id}", proxy_addr=proxy_addr, headers=headers, abroad=True
    )
    json_str = _get_str_response(json_str)
    json_data = json.loads(json_str)
    # session 接口无 data 即拉取失败，提示换地址按未开播返回
    if not json_data.get("data"):
        print("Fetch shopee live data failed, please update the address of the live broadcast room and try again.")
        return result
    uid = json_data["data"]["session"]["uid"]
    anchor_name = json_data["data"]["session"]["nickname"]
    live_status = json_data["data"]["session"]["status"]
    result["anchor_name"] = anchor_name
    result["uid"] = f"uid={uid}&session={session_id}"
    # 必须「接口报 status==1 且 链接判定为在播(is_living)」同时满足才取流；只有 session 而无 uid 的
    # 直链才置 is_living，避免把店铺主页的离线回放误判为直播。
    # 必须接口报在播 且 链接判定为在播同时满足，避免把离线回放误判为直播
    if live_status == 1 and is_living:
        flv_url = json_data["data"]["session"]["play_url"]
        title = json_data["data"]["session"]["title"]
        result |= {"is_live": True, "title": title, "flv_url": flv_url, "record_url": flv_url}
    return result


@trace_error_decorator
async def get_youtube_stream_url(
    url: str, proxy_addr: OptionalStr = None, cookies: OptionalStr = None
) -> dict[str, object]:
    # 获取 YouTube 直播流地址
    # 解析链路：页面 ytInitialPlayerResponse 抠 videoDetails；无 videoDetails（未登录）回未开播；
    # isLive 真取 hlsManifestUrl；返回 is_live + m3u8 + play_url_list；需配置 cookie 才能取流。
    headers = {
        "accept-language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:148.0) Gecko/20100101 Firefox/148.0",
    }

    # 调用方透传 cookie 时优先采用；否则走游客态/自动获取凭据（各平台未登录态取流能力不一，部分更易被风控）
    if cookies:
        headers["Cookie"] = cookies

    html_str = await async_req(url, proxy_addr=proxy_addr, headers=headers, abroad=True)
    html_str = _get_str_response(html_str)
    json_str_match = re.search("var ytInitialPlayerResponse = (.*?);var meta = document\\.createElement", html_str)
    # ytInitialPlayerResponse 缺失即登录态/页面结构异常，显式报错
    if not json_str_match:
        raise ValueError("Failed to find ytInitialPlayerResponse")
    json_str = json_str_match.group(1)
    json_data = json.loads(json_str)
    result: dict[str, object] = {"anchor_name": "", "is_live": False}
    # 无 videoDetails 说明未登录/无播放数据，提示配置 cookie 按未开播返回
    if "videoDetails" not in json_data:
        print("Error: Please log in to YouTube on your device's webpage and configure cookies in the config.ini")
        return result
    result["anchor_name"] = json_data["videoDetails"]["author"]
    live_status = json_data["videoDetails"].get("isLive")
    # isLive 为真才取 HLS 清单
    if live_status:
        live_title = json_data["videoDetails"]["title"]
        m3u8_url = json_data["streamingData"]["hlsManifestUrl"]
        play_url_list = await get_play_url_list(m3u8_url, proxy=proxy_addr, header=headers, abroad=True)
        result |= {"is_live": True, "title": live_title, "m3u8_url": m3u8_url, "play_url_list": play_url_list}
    return result


@trace_error_decorator
async def get_taobao_stream_url(
    url: str, proxy_addr: OptionalStr = None, cookies: OptionalStr = None
) -> dict[str, object]:
    # 获取淘宝直播流地址
    # 解析链路：get_params 拿 liveId（或重定向解 id）→ mtop 两轮 _m_h5_tk 签名 → livedetail；
    # streamStatus=="1" 取 liveUrlList（按画质排序）；返回 is_live + play_url_list；挤爆提示需换 cookie。
    headers = {
        "Referer": "https://huodong.m.taobao.com/",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:148.0) Gecko/20100101 Firefox/148.0",
        "Cookie": "",
    }

    # 调用方透传 cookie 时优先采用；否则走游客态/自动获取凭据（各平台未登录态取流能力不一，部分更易被风控）
    if cookies:
        headers["Cookie"] = cookies

    live_id = get_params(url, "liveId")
    # URL 无 liveId：先抓页面找重定向解 id
    if not live_id:
        html_str = await async_req(url, proxy_addr=proxy_addr, headers=headers)
        html_str = _get_str_response(html_str)
        redirect_url_match = re.findall("var url = '(.*?)';", html_str)
        if not redirect_url_match:
            raise ValueError("Failed to find redirect_url")
        redirect_url = redirect_url_match[0]
        live_id = get_params(redirect_url, "id")

    # 重定向后仍解不出 liveId：显式报错
    if not live_id:
        raise ValueError("Failed to find live_id")

    params = {
        "jsv": "2.7.0",
        "appKey": "12574478",
        "t": "1733104933120",
        "sign": "",
        "AntiFlood": "true",
        "AntiCreep": "true",
        "api": "mtop.mediaplatform.live.livedetail",
        "v": "4.0",
        "preventFallback": "true",
        "type": "jsonp",
        "dataType": "jsonp",
        "callback": "mtopjsonp1",
        "data": '{"liveId":"' + live_id + '","creatorId":null}',
    }

    # 淘宝 mtop 接口需要 _m_h5_tk 签名：首次请求不带该 cookie 时，响应会下发新的 _m_h5_tk/_m_h5_tk_enc，
    # 第二轮用其算 MD5 签名（pre_sign_str = token&t&appKey&data）再请求；两轮都拿不到 SUCCESS 即放弃。
    for _ in range(2):
        t13 = int(time.time() * 1000)
        params["t"] = str(t13)

        # 带 _m_h5_tk 时才做 MD5 签名；否则首轮裸请求换回新 token
        if "_m_h5_tk" in headers.get("Cookie", ""):
            app_key = "12574478"
            cookie_str = headers.get("Cookie", "")
            _m_h5_tk_match = re.findall("_m_h5_tk=(.*?);", cookie_str)
            if _m_h5_tk_match:
                _m_h5_tk = _m_h5_tk_match[0]
                pre_sign_str = f'{_m_h5_tk.split("_")[0]}&{t13}&{app_key}&' + params["data"]
                sign = hashlib.md5(pre_sign_str.encode("utf-8")).hexdigest()
                params["sign"] = sign
        api = f"https://h5api.m.taobao.com/h5/mtop.mediaplatform.live.livedetail/4.0/?{urllib.parse.urlencode(params)}"
        result_tuple = await async_req(
            url=api, proxy_addr=proxy_addr, headers=headers, timeout=20, return_cookies=True, include_cookies=True
        )
        # return_cookies 返回 (jsonp, cookie) 元组，需拆出 cookie 用于下一轮签名
        if isinstance(result_tuple, tuple) and len(result_tuple) == 2:
            jsonp_str, new_cookie = result_tuple
        else:
            jsonp_str = str(result_tuple) if result_tuple else ""
            new_cookie = {}
        json_data = utils.jsonp_to_json(jsonp_str)
        # ret 字段存在才进入解析；否则走循环重试换 token
        if json_data and "ret" in json_data:
            ret_value = json_data["ret"]
            # ret 为字符串数组，首元素含状态码文案（如被挤爆/SUCCESS）
            if isinstance(ret_value, list) and len(ret_value) > 0:
                # 淘宝高并发/风控会返回「被挤爆」提示，是 cookie 失效或会话被限流的明确信号，
                # 必须换有效 cookie 才能继续，否则后续请求依旧拿不到 SUCCESS。
                if "哎哟喂,被挤爆啦,请稍后重试" in str(ret_value[0]):
                    raise RuntimeError(f"Please change your taobao cookie: {ret_value}")

                ret_msg = ret_value
                if ret_msg == ["SUCCESS::调用成功"]:
                    anchor_name = cast(str, cast(dict[str, object], json_data["data"])["broadCaster"])
                    result: dict[str, object] = {"anchor_name": anchor_name, "is_live": False}
                    live_status_data = cast(dict[str, object], json_data["data"])
                    live_status = live_status_data.get("streamStatus")

                    def get_sort_key(item: dict[str, object]) -> int:
                        # 按画质优先级给清晰度排序（lld<ld<md<hd<ud），取最高可用清晰度放首位；
                        # 原注释误写为「京东」，此处实际服务于淘宝 liveUrlList。
                        definition_priority = {"lld": 0, "ld": 1, "md": 2, "hd": 3, "ud": 4}
                        def_value = item.get("definition") or item.get("newDefinition")
                        priority = definition_priority.get(str(def_value), -1)
                        return int(priority)

                    # 淘宝 streamStatus=="1" 为开播
                    if live_status == "1":
                        live_title = live_status_data.get("title")
                        play_url_list = cast(list[dict[str, object]], live_status_data.get("liveUrlList", []))
                        play_url_list = sorted(play_url_list, key=get_sort_key, reverse=True)
                        result |= {
                            "is_live": True,
                            "title": live_title,
                            "play_url_list": play_url_list,
                            "live_id": live_id,
                        }

                    # 仅在成功分支返回 result；否则落入循环重试（ret 非空但非 SUCCESS）
                    return result
            else:
                # 两轮都拿不到新 token cookie：登录式刷新失败，提示更新 cookie
                if "_m_h5_tk" not in new_cookie or "_m_h5_tk_enc" not in new_cookie:
                    raise RuntimeError(
                        "Try to update cookie failed, please update the cookies in the configuration file"
                    )
                new_cookie_str = utils.dict_to_cookie_str(new_cookie)
                headers["Cookie"] = new_cookie_str
                # 淘宝的 _m_h5_tk 是会话级票据，会过期；这里把刷新到的新 cookie 直接回写到 config.ini
                # 的 taobao_cookie，避免每轮都重新走登录式刷新。属少数会写回配置的分支。
                utils.update_config(f"{script_path}/config/config.ini", "Cookie", "taobao_cookie", new_cookie_str)
    # 如果循环结束还没有返回，返回默认结果
    return {"anchor_name": "", "is_live": False}


@trace_error_decorator
async def get_jd_stream_url(url: str, proxy_addr: OptionalStr = None, cookies: OptionalStr = None) -> dict[str, object]:
    # 获取京东直播流数据：先解析跳转/主播页定位 liveId，再经 api.m.jd.com 取播放地址（flv/hls）
    # 返回 is_live + m3u8 + flv + record_url + title；status==1 才取流，标题仅在 author_id 路径补取；
    # 跳转/主播页解析失败时回未开播，不抛错（装饰器按未开播空转重试）。
    headers = {
        "User-Agent": "ios/7.830 (ios 17.0; ; iPhone 15 (A2846/A3089/A3090/A3092))",
        "origin": "https://lives.jd.com",
        "referer": "https://lives.jd.com/",
        "x-referer-page": "https://lives.jd.com/",
    }

    # 调用方透传 cookie 时优先采用；否则走游客态/自动获取凭据（各平台未登录态取流能力不一，部分更易被风控）
    if cookies:
        headers["Cookie"] = cookies

    redirect_url_result = await async_req(url, proxy_addr=proxy_addr, headers=headers, redirect_url=True)
    # 重定向返回字符串才采用，否则保留原 URL 继续解析
    if isinstance(redirect_url_result, str):
        redirect_url = redirect_url_result
    else:
        redirect_url = url

    # 京东入口有两种形态：带 authorId 的是主播主页（需查 talent 接口拿主播名并跳转到直播间 id）；
    # 不带的是直播间直链（从 #/<liveId>?origin 抠 id）。两条路径最终都归一到 liveId 取播放地址。
    author_id = get_params(redirect_url, "authorId")
    result: dict[str, object] = {"anchor_name": "", "is_live": False}
    live_id_str: str = ""
    # 无 authorId 即直播间直链：从 #/<liveId> 抠 id；否则走主播主页接口
    if not author_id:
        live_id_match = re.search("#/(.*?)\\?origin", redirect_url)
        if not live_id_match:
            return result
        live_id_str = live_id_match.group(1)
        result["anchor_name"] = f"jd_{live_id_str}"
    else:
        data = {
            "functionId": "talent_head_findTalentMsg",
            "appid": "dr_detail",
            "body": '{"authorId":"' + author_id + '","monitorSource":"1","userId":""}',
        }
        info_api = "https://api.m.jd.com/talent_head_findTalentMsg"
        json_str = await async_req(info_api, data=data, proxy_addr=proxy_addr, headers=headers)
        json_str = _get_str_response(json_str)
        json_data = json.loads(json_str)
        anchor_name = json_data["result"]["talentName"]
        result["anchor_name"] = anchor_name
        # 主播页无在播跳转信息：未开播，直接回未开播
        if "livingRoomJump" not in json_data["result"]:
            return result
        live_id_str = cast(str, json_data["result"]["livingRoomJump"]["params"]["id"])
    params = {"body": '{"liveId": "' + live_id_str + '"}', "functionId": "getImmediatePlayToM", "appid": "h5-live"}

    api = f"https://api.m.jd.com/client.action?{urllib.parse.urlencode(params)}"
    # backup_api: https://api.m.jd.com/api
    json_str = await async_req(api, proxy_addr=proxy_addr, headers=headers)
    json_str = _get_str_response(json_str)
    json_data = json.loads(json_str)
    live_status = json_data["data"]["status"]
    # 京东 status==1 为开播
    if live_status == 1:
        # 仅 authorId 入口才需补查标题（直链入口标题缺省）
        if author_id:
            data = {
                "functionId": "jdTalentContentList",
                "appid": "dr_detail",
                "body": '{"authorId":"' + author_id + '","type":1,"userId":"","page":1,"offset":"-1",'
                '"monitorSource":"1","pageSize":1}',
            }
            json_str2 = await async_req(
                "https://api.m.jd.com/jdTalentContentList", data=data, proxy_addr=proxy_addr, headers=headers
            )
            json_str2 = _get_str_response(json_str2)
            json_data2 = json.loads(json_str2)
            result["title"] = json_data2["result"]["content"][0]["title"]

        flv_url = json_data["data"]["videoUrl"]
        m3u8_url = json_data["data"]["h5VideoUrl"]
        result |= {"is_live": True, "m3u8_url": m3u8_url, "flv_url": flv_url, "record_url": m3u8_url}
    return result


@trace_error_decorator
async def get_faceit_stream_data(
    url: str, proxy_addr: OptionalStr = None, cookies: OptionalStr = None
) -> dict[str, object]:
    # 获取 Faceit 直播流数据
    # 解析链路：nicknames 拿 user_id → streamings 拿 platform；platform==twitch 委托 get_twitchtv_stream_data
    # （透传代理/cookie，否则登录态丢失）；否则回未开播；返回 is_live + 平台流地址。
    headers = {
        "Referer": "https://www.faceit.com/zh/players/qpjzz/stream",
        "faceit-referer": "web-next",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:148.0) Gecko/20100101 Firefox/148.0",
    }

    # 调用方透传 cookie 时优先采用；否则走游客态/自动获取凭据（各平台未登录态取流能力不一，部分更易被风控）
    if cookies:
        headers["Cookie"] = cookies
    nickname = re.findall("/players/(.*?)/stream", url)[0]
    api = f"https://www.faceit.com/api/users/v1/nicknames/{nickname}"
    json_str = await async_req(api, proxy_addr=proxy_addr, headers=headers)
    json_str = _get_str_response(json_str)
    json_data = json.loads(json_str)
    user_id = json_data["payload"]["id"]
    api2 = f"https://www.faceit.com/api/stream/v1/streamings?userId={user_id}"
    json_str2 = await async_req(api2, proxy_addr=proxy_addr, headers=headers)
    json_str2 = _get_str_response(json_str2)
    json_data2 = json.loads(json_str2)
    platform_info = json_data2["payload"][0]
    anchor_name = platform_info.get("userNickname")
    anchor_id = platform_info.get("platformId")
    platform = platform_info.get("platform")
    # Faceit 委托 Twitch 解析并透传代理/cookie，否则无流按未开播
    if platform == "twitch":
        # 委托 Twitch 解析：透传代理与 cookies，否则登录态/代理全部丢失
        result = await get_twitchtv_stream_data(f"https://www.twitch.tv/{anchor_id}", proxy_addr, cookies)
        result["anchor_name"] = anchor_name
    else:
        result = {"anchor_name": anchor_name, "is_live": False}
    return result


@trace_error_decorator
async def get_migu_stream_url(
    url: str, proxy_addr: OptionalStr = None, cookies: OptionalStr = None
) -> dict[str, object]:
    # 获取咪咕直播流地址
    # 解析链路：basic-data 拿 pId → playurl 接口拿 source_url → migu.js 签名算 ddCalcu；
    # currentLive=="1" 取流；m3u8 经重定向、flv 直用；返回 is_live + m3u8/flv + record_url。
    headers = {
        "origin": "https://www.miguvideo.com",
        "referer": "https://www.miguvideo.com/",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/141.0.0.0 Safari/537.36 Edg/141.0.0.0",
        "appCode": "miguvideo_default_www",
        "appId": "miguvideo",
        "channel": "H5",
    }

    # 调用方透传 cookie 时优先采用；否则走游客态/自动获取凭据（各平台未登录态取流能力不一，部分更易被风控）
    if cookies:
        headers["Cookie"] = cookies

    web_id = url.split("?")[0].rsplit("/")[-1]
    # 先从 basic-data 静态缓存拿到 pId（真实房间号）；该接口对游客开放、无需登录 cookie。
    api = f"https://vms-sc.miguvideo.com/vms-match/v6/staticcache/basic/basic-data/{web_id}/miguvideo"
    json_str = await async_req(api, proxy_addr=proxy_addr, headers=headers)
    json_str = _get_str_response(json_str)
    json_data = json.loads(json_str)

    anchor_name = json_data["body"].get("title") or ""
    detail_title = json_data["body"].get("detailPageTitle") or ""
    live_title = f"{anchor_name}-{detail_title}" if detail_title else anchor_name
    room_id = json_data["body"].get("pId")

    result: dict[str, object] = {"anchor_name": anchor_name, "is_live": False}
    # basic-data 没拿到 pId：房间不存在/失效，按未开播返回
    if not room_id:
        return result

    params = {
        "contId": room_id,
        # rateType=3 为原画；clientId 每次请求用随机 uuid（无状态、不缓存）；chip/channelId 为固定渠道标识。
        "rateType": "3",
        "clientId": str(uuid.uuid4()),
        "timestamp": int(time.time() * 1000),
        "flvEnable": "true",
        "xh265": "false",
        "chip": "mgwww",
        "channelId": "",
    }

    api = f"https://webapi.miguvideo.com/gateway/playurl/v3/play/playurl?{urllib.parse.urlencode(params)}"
    json_str = await async_req(api, proxy_addr=proxy_addr, headers=headers)
    json_str = _get_str_response(json_str)
    json_data = json.loads(json_str)
    # currentLive 是字符串 "1" 表示在播，其它值（含 "0"/空）视为未开播直接返回。
    live_status = json_data["body"]["content"]["currentLive"]
    # 咪咕 currentLive 为字符串 "1" 才在播，其它值（含 "0"/空）判未开播
    if live_status != "1":
        return result
    else:
        result["title"] = live_title
        # source_url 是未签名的播放地址，必须经 migu.js 算出 ddCalcu/sv 签名参数后才可用，
        # 裸地址直接拉会 403；下面 _get_dd_calcu 返回的才是带签名的可拉流地址。
        source_url = json_data["body"]["urlInfo"]["url"]

        async def _get_dd_calcu(url: str) -> str:
            # 咪咕签名算法（内部方法）：node 失败/超时统一转为 ProgramError，
            # 由上层装饰器按平台错误处理，不向调用方泄漏 CalledProcessError。
            # migu.js（2026-08 重写版）输出带 ddCalcu/sv 参数的完整地址：
            # 加密因子与 sv 版本号由脚本端从官网接口获取（失败回退播放器内置
            # 默认因子），此处不再拼接固定 sv=10010（该值已过期）。
            try:
                result = subprocess.run(
                    ["node", f"{JS_SCRIPT_PATH}/migu.js", url],
                    capture_output=True,
                    text=True,
                    check=True,
                    timeout=30,
                )
                return result.stdout.strip()
            except subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError:
                raise ProgramError("Failed to execute JS code. Please check if the Node.js environment")

        real_source_url = await _get_dd_calcu(source_url)
        # 签名后的地址可能已是 m3u8（走重定向拿到最终清单）也可能是 flv 直链，按后缀分流处理；
        # m3u8 需再发一次请求取重定向后的真实清单，flv 直链可直接作为录制源。
        # 签名后地址按后缀分流：m3u8 需再取重定向清单，flv 直链可直接录制
        if ".m3u8" in real_source_url:
            m3u8_url = await async_req(real_source_url, proxy_addr=proxy_addr, headers=headers, redirect_url=True)
            m3u8_url = _get_str_response(m3u8_url)
            # 重定向失败（空响应）判未直播，避免把空串当流地址返回
            # 重定向失败（空响应）判未直播，避免把空串当流地址
            if not m3u8_url:
                return result
            result["m3u8_url"] = m3u8_url
            result["record_url"] = m3u8_url
        else:
            result["flv_url"] = real_source_url
            result["record_url"] = real_source_url
        result["is_live"] = True
    return result


@trace_error_decorator
async def get_lianjie_stream_url(
    url: str, proxy_addr: OptionalStr = None, cookies: OptionalStr = None
) -> dict[str, object]:
    # 获取连接直播流地址
    # 解析链路：roomNumber 直取 getRoomInfo → isonline==1 取 videoUrl；非 webrtc:// 拼不出可录地址按未开播；
    # 返回 is_live + m3u8 + flv + record_url；webrtc 转 https 后替换后缀得 flv/m3u8。
    headers = {
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/141.0.0.0 Safari/537.36 Edg/141.0.0.0",
        "accept-language": "zh-CN,zh;q=0.8,zh-TW;q=0.7,zh-HK;q=0.5,en-US;q=0.3,en;q=0.2",
    }

    # 调用方透传 cookie 时优先采用；否则走游客态/自动获取凭据（各平台未登录态取流能力不一，部分更易被风控）
    if cookies:
        headers["cookie"] = cookies

    room_id = url.split("?")[0].rsplit("lailianjie.com/", maxsplit=1)[-1]
    play_api = f"https://api.lailianjie.com/ApiServices/service/live/getRoomInfo?&_$t=&_sign=&roomNumber={room_id}"
    json_str = await async_req(play_api, proxy_addr=proxy_addr, headers=headers)
    json_str = _get_str_response(json_str)
    json_data = json.loads(json_str)

    room_data = json_data["data"]
    anchor_name = room_data["nickname"]
    live_status = room_data["isonline"]

    result: dict[str, object] = {"anchor_name": anchor_name, "is_live": False}
    if live_status == 1:
        title = room_data["defaultRoomTitle"]
        webrtc_url = room_data["videoUrl"]
        # videoUrl 非 webrtc:// 格式时无法拼出可录制的 https 地址，判未直播而非 IndexError
        # videoUrl 非 webrtc:// 时无法拼出可录 https 地址，判未直播
        if not str(webrtc_url).startswith("webrtc://"):
            return result
        https_url = "https://" + webrtc_url.split("webrtc://")[1]
        flv_url = https_url.replace("?", ".flv?")
        m3u8_url = https_url.replace("?", ".m3u8?")
        result |= {"is_live": True, "title": title, "m3u8_url": m3u8_url, "flv_url": flv_url, "record_url": flv_url}
    return result


@trace_error_decorator
async def get_laixiu_stream_url(
    url: str, proxy_addr: OptionalStr = None, cookies: OptionalStr = None
) -> dict[str, object]:
    # 获取来秀直播流地址
    # 解析链路：calculate_sign(md5 盐 u) 游客头 → getShareLiveVideo 拿 playUrl；
    # playStatus==0(注意是 0 而非 1) 取流；返回 is_live + flv + record_url；room_data 缺失 KeyError 由装饰器兜底。
    def generate_uuid(ua_type: str) -> str:
        # 生成 UUID（来秀签名用）
        if ua_type == "mobile":
            return str(uuid.uuid4())
        return str(uuid.uuid4()).replace("-", "")

    def calculate_sign(ua_type: str = "pc") -> dict[str, int | str]:
        # 计算来秀请求签名：md5("web" + 随机imei + 时间戳 + 固定盐u)。
        # u 是该 App 写死的签名盐（服务端硬编码），改了服务端无法校验；imei 每次随机即可。
        a = int(time.time() * 1000)
        s = generate_uuid(ua_type)
        u = "kk792f28d6ff1f34ec702c08626d454b39pro"

        input_str = f"web{s}{a}{u}"
        md5_hash = hashlib.md5(input_str.encode("utf-8")).hexdigest()

        return {"timestamp": a, "imei": s, "requestId": md5_hash, "inputString": input_str}

    sign_data = calculate_sign(ua_type="pc")
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/141.0.0.0 Safari/537.36 Edg/141.0.0.0",
        "mobileModel": "web",
        "timestamp": str(sign_data["timestamp"]),
        "loginType": "2",
        "versionCode": "10003",
        "imei": str(sign_data["imei"]),
        "requestId": str(sign_data["requestId"]),
        "channel": "9",
        "version": "1.0.0",
        "os": "web",
        "platform": "WEB",
        "Origin": "https://www.imkktv.com",
        "Referer": "https://www.imkktv.com/",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
    }

    # 调用方透传 cookie 时优先采用；否则走游客态/自动获取凭据（各平台未登录态取流能力不一，部分更易被风控）
    if cookies:
        headers["cookie"] = cookies

    pattern = r"(?:roomId|anchorId)=(.*?)(?=&|$)"
    match = re.search(pattern, url)
    room_id = match.group(1) if match else ""
    play_api = f"https://api.imkktv.com/liveroom/getShareLiveVideo?roomId={room_id}"
    json_str = await async_req(play_api, proxy_addr=proxy_addr, headers=headers)
    json_str = _get_str_response(json_str)
    json_data = json.loads(json_str)

    room_data = json_data["data"]
    anchor_name = room_data["nickname"]
    # 来秀用 playStatus==0 表示在播（注意是 0 而非 1，与其它平台相反），非 0 视为未开播。
    live_status = room_data["playStatus"] == 0

    result: dict[str, object] = {"anchor_name": anchor_name, "is_live": False}
    # 来秀在播才取 playUrl
    if live_status:
        flv_url = room_data["playUrl"]
        result |= {"is_live": True, "flv_url": flv_url, "record_url": flv_url}
    return result


@trace_error_decorator
async def get_picarto_stream_url(
    url: str, proxy_addr: OptionalStr = None, cookies: OptionalStr = None
) -> dict[str, object]:
    # 获取 Picarto 直播流地址
    # channel.online 布尔直接驱动 is_live；m3u8 由固定 edge host + anchor_name 拼出
    # （golive+{name}），非接口返回，依赖 anchor_name 稳定，拼错会得到无效地址。
    headers = {
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/141.0.0.0 Safari/537.36 Edg/141.0.0.0",
        "accept-language": "zh-CN,zh;q=0.8,zh-TW;q=0.7,zh-HK;q=0.5,en-US;q=0.3,en;q=0.2",
    }

    # 调用方透传 cookie 时优先采用；否则走游客态/自动获取凭据（各平台未登录态取流能力不一，部分更易被风控）
    if cookies:
        headers["cookie"] = cookies

    anchor_id = url.split("?")[0].rsplit("/", maxsplit=1)[-1]
    api = f"https://ptvintern.picarto.tv/api/channel/detail/{anchor_id}"

    json_str = await async_req(api, proxy_addr=proxy_addr, headers=headers)
    json_str = _get_str_response(json_str)
    json_data = json.loads(json_str)

    anchor_name = json_data["channel"]["name"]
    live_status = json_data["channel"]["online"]

    result: dict[str, object] = {"anchor_name": anchor_name, "is_live": live_status}
    # Picarto channel.online 布尔直接驱动 is_live
    if live_status:
        title = json_data["channel"]["title"]
        m3u8_url = f"https://1-edge1-us-newyork.picarto.tv/stream/hls/golive+{anchor_name}/index.m3u8"
        result |= {"is_live": True, "title": title, "m3u8_url": m3u8_url, "record_url": m3u8_url}
    return result
