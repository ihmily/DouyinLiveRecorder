# -*- encoding: utf-8 -*-

# 抖音直播录制工具 - 爬虫模块

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
from .logger import logger, script_path
from .room import UnsupportedUrlError, get_sec_user_id, get_unique_id, is_user_homepage_url
from .ttwid import get_ttwid as _shared_get_ttwid
from .utils import generate_random_string, trace_error_decorator

OptionalStr = str | None
OptionalDict = dict[str, str] | None
# 花椒接口返回的异构 dict（含 is_live 布尔值），值类型需覆盖 str | bool
OptionalStreamDict = dict[str, str | bool] | None

# 缓存自动获取的 ttwid，避免重复请求主页（已委托给共享 ttwid.py 模块，保留变量兼容旧引用）
_cached_ttwid: str = ""


def _safe_extract_id(url: str, default: str = "") -> str:
    # 从 URL 中安全提取路径 ID（避免 rsplit 越界）
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


async def _ensure_kuaishou_did(proxy_addr: OptionalStr = None) -> str:
    # 自动获取快手访客 did/didv（访问快手直播主页时服务器下发），替代硬编码过期凭据
    global _cached_kuaishou_did
    if _cached_kuaishou_did:
        return _cached_kuaishou_did
    try:
        cookies_dict = await async_req(
            url="https://live.kuaishou.com/",
            proxy_addr=proxy_addr,
            headers={
                "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
            },
            return_cookies=True,
            timeout=10,
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
    fallback_ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0"
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
    if isinstance(resp, str):
        return resp
    elif isinstance(resp, tuple) and len(resp) > 0 and isinstance(resp[0], str):
        return resp[0]
    return ""


def _loads_dict(text: object) -> dict[str, object]:
    # 将 async_req 文本响应安全解析为 dict[str, object]，消除 json.loads 的 Any 传播
    s = _get_str_response(text)
    if not s:
        return {}
    parsed = cast(object, json.loads(s))
    return parsed if isinstance(parsed, dict) else {}


def get_params(url: str, params: str) -> OptionalStr:
    # 从URL中提取指定参数的值
    parsed_url = urllib.parse.urlparse(url)
    query_params = urllib.parse.parse_qs(parsed_url.query)

    if params in query_params:
        return query_params[params][0]
    return None


def extract_douyin_hevc_flv_url(html: str) -> OptionalStr:
    # 从抖音页面 HTML 中提取 HEVC/H265 FLV 流地址
    pattern = re.compile(r'(https?://[^\s"\']*stream-\d{10,}(?!_[a-z0-9]+)\.flv(?:[^"\']|\\u0026)+)')
    for match in pattern.findall(html):
        clean_url = match.replace("\\u0026", "&").rstrip("\\").strip()
        query = urllib.parse.parse_qs(urllib.parse.urlparse(clean_url).query)
        if query.get("only_audio", ["0"])[0] == "1":
            continue
        return cast(str, clean_url)
    return None


async def get_play_url_list(
    m3u8: str, proxy: OptionalStr = None, header: OptionalDict = None, abroad: bool = False
) -> list[str]:
    # 获取M3U8播放列表中的所有清晰度URL并按带宽排序
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
    bandwidth_pattern = re.compile(r"BANDWIDTH=(\d+)")
    bandwidth_list = cast(list[str], bandwidth_pattern.findall(resp))
    if bandwidth_list and len(bandwidth_list) == len(play_url_list):
        url_to_bandwidth = {url: int(bandwidth) for bandwidth, url in zip(bandwidth_list, play_url_list)}
        play_url_list = sorted(play_url_list, key=lambda url: url_to_bandwidth[url], reverse=True)
    return play_url_list


def _extract_room_data_from_html(html_str: str) -> dict[str, object]:
    # 从抖音直播间HTML页面提取房间数据（作为API失败时的回退方案）
    if not html_str:
        return {}
    try:
        match_json_str = re.search(r'(\{\\"state\\":.*?)]\\n"]\)', html_str)
        if not match_json_str:
            match_json_str = re.search(r'(\{\\"common\\":.*?)]\\n"]\)</script><div hidden', html_str)
        if not match_json_str:
            return {}
        json_str = match_json_str.group(1)
        cleaned_string = json_str.replace("\\", "").replace(r"u0026", r"&")
        room_store_match = re.search('"roomStore":(.*?),"linkmicStore"', cleaned_string, re.DOTALL)
        if not room_store_match:
            return {}
        room_store = room_store_match.group(1)
        anchor_name_match = re.search('"nickname":"(.*?)","avatar_thumb', room_store, re.DOTALL)
        anchor_name = anchor_name_match.group(1) if anchor_name_match else ""
        room_store = room_store.split(',"has_commerce_goods"')[0] + "}}}"
        room_info = cast(dict[str, object], _loads_dict(room_store).get("roomInfo") or {})
        json_data = cast(dict[str, object], room_info.get("room") or {})
        json_data["anchor_name"] = anchor_name
        if json_data.get("status") == 4:
            return json_data
        stream_url_field = cast(dict[str, object], json_data.get("stream_url") or {})
        stream_orientation = stream_url_field.get("stream_orientation")
        origin_url_list: dict[str, object] | None = None
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
                origin_url_list = _loads_dict(match_json_str3.group(1) + "}")
        if origin_url_list:
            sdk_params_field = cast(dict[str, object], origin_url_list.get("sdk_params") or {})
            vcodec = sdk_params_field.get("VCodec")
            origin_hls_codec = vcodec if isinstance(vcodec, str) else ""
            hls_v = origin_url_list.get("hls", "")
            flv_v = origin_url_list.get("flv", "")
            hls_s = hls_v if isinstance(hls_v, str) else ""
            flv_s = flv_v if isinstance(flv_v, str) else ""
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
        headers["cookie"] = await _ensure_ttwid(proxy_addr)

    try:
        # web_rid 取 URL 末段即可：web/enter 接口同时接受数字房间号（745964462470）
        # 与抖音号（yall1102），后者不会发生重定向，无需额外解析请求。
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
            "msToken": "",
        }

        api = f"https://live.douyin.com/webcast/room/web/enter/?{urllib.parse.urlencode(params)}"

        async def _try_web_api() -> dict[str, object]:
            # 单次 web/enter API 尝试；失败（空响应 / 非 0 状态码）抛异常，由外层决定是否重试或回退。
            json_str = _get_str_response(await async_req(url=api, proxy_addr=proxy_addr, headers=headers))
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

        if room_data.get("status") == 2:
            if "stream_url" not in room_data:
                raise RuntimeError(
                    "The live streaming type or gameplay is not supported on the computer side yet, please use the "
                    "app to share the link for recording."
                )
            stream_url = cast(dict[str, object], room_data["stream_url"])
            html_str = _get_str_response(await async_req(url=url, proxy_addr=proxy_addr, headers=headers))
            hevc_flv_url = extract_douyin_hevc_flv_url(html_str)
            live_core_sdk_data = cast(dict[str, object], stream_url.get("live_core_sdk_data") or {})
            pull_datas = cast(dict[str, object], stream_url.get("pull_datas") or {})
            if live_core_sdk_data:
                json_str = ""
                if pull_datas:
                    # 遍历 pull_datas 选取包含 origin 的条目，优先 HEVC
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
                        except (json.JSONDecodeError, TypeError):
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
                        except (json.JSONDecodeError, KeyError, TypeError):
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
            "verifyFp": "",
            "type_id": "0",
            "live_id": "1",
            "room_id": room_id,
            "sec_user_id": sec_uid,
            "version_code": "141.0.0.0",
            "app_id": "1128",
        }
        api2 = f"https://webcast.amemv.com/webcast/room/reflow/info/?{urllib.parse.urlencode(app_params)}"
        try:
            json_str2 = _get_str_response(await async_req(url=api2, proxy_addr=proxy_addr, headers=headers))
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
                            except (json.JSONDecodeError, TypeError):
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
    except Exception as e:
        tb_lineno = e.__traceback__.tb_lineno if e.__traceback__ else 0
        logger.error(f"Error message: {e} Error line: {tb_lineno}")
        room_data = cast(dict[str, object], {"anchor_name": ""})
    return room_data


@trace_error_decorator
async def get_tiktok_stream_data(
    url: str, proxy_addr: OptionalStr = None, cookies: OptionalStr = None
) -> dict[str, object] | None:
    # 获取TikTok直播数据
    headers = {
        "referer": "https://www.tiktok.com/",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
        + "Chrome/141.0.0.0 Safari/537.36",
        "cookie": cookies
        or "1%7Cz7FKki38aKyy7i-BC9rEDwcrVvjcLcFEL6QIeqldoy4%7C1761302831%7C6c1461e9f1f980cbe0404c5190"
        + "5177d5d53bbd822e1bf66128887d942c9c3e2f",
    }

    for _ in range(3):
        html_str = _get_str_response(
            await async_req(url=url, proxy_addr=proxy_addr, headers=headers, abroad=True, http2=False)
        )
        await asyncio.sleep(1)  # 异步休眠，避免阻塞事件循环
        if "We regret to inform you that we have discontinued operating TikTok" in html_str:
            msg = re.search("<p>\n\\s+(We regret to inform you that we have discontinu.*?)\\.\n\\s+</p>", html_str)
            raise ConnectionError(
                "Your proxy node's regional network is blocked from accessing TikTok; please switch to a node in "
                + f"another region to access. {msg.group(1) if msg else ''}"
            )
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
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/115.0",
        "Accept-Language": "zh-CN,zh;q=0.8,zh-TW;q=0.7,zh-HK;q=0.5,en-US;q=0.3,en;q=0.2",
    }
    if cookies:
        headers["Cookie"] = cookies
    try:
        html_str = _get_str_response(await async_req(url=url, proxy_addr=proxy_addr, headers=headers))
    except Exception as e:
        print(f"Failed to fetch data from {url}.{e}")
        return {"type": 1, "is_live": False}

    try:
        json_str_match = re.search("<script>window.__INITIAL_STATE__=(.*?);\\(function\\(\\)\\{var s;", html_str)
        if not json_str_match:
            raise ValueError("Failed to find __INITIAL_STATE__")
        json_str = json_str_match.group(1)
        play_list_matches = cast(list[str], re.findall('(\\{"liveStream".*?),"gameInfo', json_str))
        if not play_list_matches:
            raise ValueError("Failed to find liveStream")
        play_list = _loads_dict(play_list_matches[0] + "}")
    except (AttributeError, IndexError, json.JSONDecodeError) as e:
        print(f"Failed to parse JSON data from {url}. Error: {e}")
        return {"type": 1, "is_live": False}

    result: dict[str, object] = {"type": 2, "is_live": False}

    if "errorType" in play_list or "liveStream" not in play_list:
        error_type = cast(dict[str, object], play_list.get("errorType") or {})
        title = error_type.get("title", "")
        content = error_type.get("content", "")
        error_msg = (title if isinstance(title, str) else "") + (content if isinstance(content, str) else "")
        print(f"Failed URL: {url} Error message: {error_msg}")
        return result

    live_stream = cast(dict[str, object], play_list.get("liveStream") or {})
    if not live_stream:
        print("IP banned. Please change device or network.")
        return result

    author = cast(dict[str, object], play_list.get("author") or {})
    anchor_name = author.get("name", "")
    result.update({"anchor_name": anchor_name})

    play_urls_obj = live_stream.get("playUrls")
    if play_urls_obj:
        play_url_list: object
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
        if result["anchor_name"]:
            return result
    except Exception as e:
        print(f"{e}, Failed URL: {url}, preparing to switch to a backup plan for re-parsing.")
    return await get_kuaishou_stream_data(url, cookies=cookies, proxy_addr=proxy_addr)


@trace_error_decorator
async def get_huya_stream_data(
    url: str, proxy_addr: OptionalStr = None, cookies: OptionalStr = None
) -> dict[str, object]:
    # 获取虎牙直播数据
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.8,zh-TW;q=0.7,zh-HK;q=0.5,en-US;q=0.3,en;q=0.2",
        # 移除原硬编码的长串过期 Cookie（含大量 session/token，多数为访客统计字段）
        # 未配置 cookie 时不发送 Cookie 头，让虎牙服务器在响应中重新下发访客 cookie
    }
    if cookies:
        headers["Cookie"] = cookies

    html_str = _get_str_response(await async_req(url=url, proxy_addr=proxy_addr, headers=headers))
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
    room_id = url.split("?")[0].rsplit("/", maxsplit=1)[-1]

    if any(char.isalpha() for char in room_id):
        html_str = _get_str_response(await async_req(url, proxy_addr=proxy_addr, headers=headers))
        room_id_match = re.search('ProfileRoom":(.*?),"sPrivateHost', html_str)
        if room_id_match:
            room_id = room_id_match.group(1)
        else:
            raise Exception('Please use "https://www.huya.com/+room_number" for recording')

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
            s_flv_url = i.get("sFlvUrl")
            flv_anti_code = i.get("sFlvAntiCode")
            s_hls_url = i.get("sHlsUrl")
            hls_anti_code = i.get("sHlsAntiCode")
            m3u8_url = f"{s_hls_url}/{stream_name}.m3u8?{hls_anti_code}"
            flv_url = f"{s_flv_url}/{stream_name}.flv?{flv_anti_code}"
            play_url_list.append(
                {
                    "cdn_type": cdn_type,
                    "m3u8_url": m3u8_url,
                    "flv_url": flv_url,
                }
            )
        # print(json.dumps(play_url_list, indent=4, ensure_ascii=False))
        # flv_url = 'https://' + play_url_list[0]['flv_url'].split('://')[1]
        # record_url = flv_url

        # 设定优先级，优先选择 TX,2025/03/14时AL不可用
        priority_order = ["TX", "HW", "HS", "AL"]

        # 查找优先的 flv_url
        selected_flv_url: str | None = None
        selected_cdn_type = None

        for cdn in priority_order:
            for item in play_url_list:
                if item["cdn_type"] == cdn:
                    item_flv = item["flv_url"]
                    selected_flv_url = item_flv if isinstance(item_flv, str) else None
                    selected_cdn_type = cdn
                    break
            if selected_flv_url:
                break

        # 处理 flv_url，确保使用 https
        record_url: str | None
        if selected_flv_url:
            flv_url = "https://" + selected_flv_url.split("://")[1]

            # 如果选择的是 TX，执行额外的字符串替换
            if selected_cdn_type == "TX":
                flv_url = flv_url.replace("&ctype=tars_mp", "&ctype=huya_webh5").replace("&fs=bhct", "&fs=bgct")

            record_url = flv_url
        else:
            record_url = None

        return {
            "anchor_name": anchor_name,
            "is_live": True,
            "m3u8_url": play_url_list[0]["m3u8_url"],
            "flv_url": play_url_list[0]["flv_url"],
            "record_url": record_url,
            "title": live_title,
        }


def md5(data: str) -> str:
    # 计算字符串的MD5哈希值
    return hashlib.md5(data.encode("utf-8")).hexdigest()


async def get_token_js(rid: str, did: str, proxy_addr: OptionalStr = None) -> dict[str, object]:
    # 获取斗鱼API请求签名参数
    try:
        key_url = f"https://www.douyu.com/wgapi/livenc/liveweb/websec/getEncryption?did={did}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
            + "Chrome/120.0.0.0 Safari/537.36",
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

    headers["User-Agent"] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0"
    url2 = f"https://www.douyu.com/betard/{rid}"
    json_str = await async_req(url=url2, proxy_addr=proxy_addr, headers=headers)
    json_str = _get_str_response(json_str)
    json_data = json.loads(json_str)
    result: dict[str, object] = {"anchor_name": json_data["room"]["nickname"], "is_live": False}
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
    did = "10000000000000000000000000003306"
    sign_params = await get_token_js(rid, did, proxy_addr=proxy_addr)
    if not sign_params:
        return {"error": -1, "msg": "Failed to get sign params", "data": {}}
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36",
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
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36 Edg/121.0.0.0",
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
    json_data["anchor_name"] = anchor_name

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


@trace_error_decorator
async def get_bilibili_room_info_h5(url: str, proxy_addr: OptionalStr = None, cookies: OptionalStr = None) -> str:
    # 获取 B站直播间 H5 接口信息
    headers = {
        "user-agent": "Mozilla/5.0 (Linux; Android 11; SAMSUNG SM-G973U) AppleWebKit/537.36 (KHTML, like Gecko) "
        "SamsungBrowser/14.2 Chrome/87.0.4280.141 Mobile Safari/537.36",
        "accept-language": "zh-CN,zh;q=0.8,zh-TW;q=0.7,zh-HK;q=0.5,en-US;q=0.3,en;q=0.2",
        "cookie": "",
        "origin": "https://live.bilibili.com",
        "referer": "https://live.bilibili.com/26066074",
    }
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
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:127.0) Gecko/20100101 Firefox/127.0",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.8,zh-TW;q=0.7,zh-HK;q=0.5,en-US;q=0.3,en;q=0.2",
    }
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
        print(e)
        return {"anchor_name": "", "live_status": False, "room_url": url}


@trace_error_decorator
async def get_bilibili_stream_data(
    url: str, qn: str = "10000", platform: str = "web", proxy_addr: OptionalStr = None, cookies: OptionalStr = None
) -> dict[str, object] | None:
    # 获取 B站直播流数据（多清晰度），返回 {url, current_qn, accept_qn}
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:127.0) Gecko/20100101 Firefox/127.0",
        "Accept-Language": "zh-CN,zh;q=0.8,zh-TW;q=0.7,zh-HK;q=0.5,en-US;q=0.3,en;q=0.2",
        "origin": "https://live.bilibili.com",
        "referer": "https://live.bilibili.com/26066074",
    }
    if cookies:
        headers["Cookie"] = cookies

    room_id = _safe_extract_id(url)
    params = {"cid": room_id, "qn": qn, "platform": platform}
    play_api = f"https://api.live.bilibili.com/room/v1/Room/playUrl?{urllib.parse.urlencode(params)}"
    json_str = await async_req(play_api, proxy_addr=proxy_addr, headers=headers)
    json_str = _get_str_response(json_str)
    json_data = json.loads(json_str)
    if json_data and json_data["code"] == 0:
        durl_list = json_data["data"].get("durl", [])
        if not durl_list:
            return None
        # playUrl 接口无 qn 元信息，current_qn 取请求值，accept_qn 未知
        target_url = None
        for i in durl_list:
            if "d1--cn-gotcha" in i.get("url", ""):
                target_url = i["url"]
                break
        if not target_url:
            target_url = durl_list[-1].get("url")
        return {"url": target_url, "current_qn": qn, "accept_qn": [qn]}
    else:
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
        if json_data["data"]["live_status"] == 0:
            print("The anchor did not start broadcasting.")
            return None
        playurl_info = json_data["data"]["playurl_info"]
        stream_list = playurl_info["playurl"].get("stream", [])
        if not stream_list:
            return None
        format_list = stream_list[0].get("format", [])
        if not format_list:
            return None
        stream_data_list = format_list[0].get("codec", [])
        if not stream_data_list:
            return None
        sorted_stream_list: list[dict[str, object]] = sorted(
            stream_data_list, key=itemgetter("current_qn"), reverse=True
        )
        video_quality_options = {"10000": 0, "400": 1, "250": 2, "150": 3, "80": 4}
        qn_count = len(sorted_stream_list)
        select_stream_index = min(video_quality_options.get(qn, 0), qn_count - 1)
        stream_data: dict[str, object] = sorted_stream_list[select_stream_index]
        base_url = cast(str, stream_data["base_url"])
        url_info = stream_data.get("url_info", [])
        if not url_info:
            return None
        url_info_list = cast(list[dict[str, object]], url_info)
        host = cast(str, url_info_list[0].get("host", ""))
        extra = cast(str, url_info_list[0].get("extra", ""))
        m3u8_url = host + base_url + extra
        current_qn = str(stream_data.get("current_qn", qn))
        accept_qn = [str(s.get("current_qn")) for s in sorted_stream_list]
        return {"url": m3u8_url, "current_qn": current_qn, "accept_qn": accept_qn}


@trace_error_decorator
async def get_xhs_stream_url(
    url: str, proxy_addr: OptionalStr = None, cookies: OptionalStr = None
) -> dict[str, object]:
    # 获取小红书直播流地址
    headers = {
        "User-Agent": "ios/7.830 (ios 17.0; ; iPhone 15 (A2846/A3089/A3090/A3092))",
        "xy-common-params": "platform=iOS&sid=session.1722166379345546829388",
        "referer": "https://app.xhs.cn/",
    }
    if cookies:
        headers["Cookie"] = cookies

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
    match_data = re.search("<script>window.__INITIAL_STATE__=(.*?)</script>", html_str)

    if match_data:
        json_str = match_data.group(1).replace("undefined", "null")
        json_data = json.loads(json_str)

        if json_data.get("liveStream"):
            stream_data = json_data["liveStream"]
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
    # 获取 Bigo 直播流地址
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/119.0",
        "Accept-Language": "zh-CN,zh;q=0.8,zh-TW;q=0.7,zh-HK;q=0.5,en-US;q=0.3,en;q=0.2",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "Referer": "https://www.bigo.tv/",
    }
    if cookies:
        headers["Cookie"] = cookies

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

    data = {"siteId": room_id}  # roomId
    url2 = "https://ta.bigo.tv/official_website/studio/getInternalStudioInfo"
    json_str = await async_req(url=url2, proxy_addr=proxy_addr, headers=headers, data=data)
    json_str = _get_str_response(json_str)
    json_data = json.loads(json_str)
    anchor_name = json_data["data"]["nick_name"]
    live_status = json_data["data"]["alive"]
    result: dict[str, object] = {"anchor_name": anchor_name, "is_live": False}

    if live_status == 1:
        live_title = json_data["data"]["roomTopic"]
        m3u8_url = json_data["data"]["hls_src"]
        result["m3u8_url"] = m3u8_url
        result["record_url"] = m3u8_url
        result |= {"title": live_title, "is_live": True, "m3u8_url": m3u8_url, "record_url": m3u8_url}
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
    # 获取 Blued 直播流地址
    headers = {
        "User-Agent": "ios/7.830 (ios 17.0; ; iPhone 15 (A2846/A3089/A3090/A3092))",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.8,zh-TW;q=0.7,zh-HK;q=0.5,en-US;q=0.3,en;q=0.2",
    }
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


@trace_error_decorator
async def login_sooplive(username: str, password: str, proxy_addr: OptionalStr = None) -> OptionalStr:
    # SOOP 平台登录获取认证 Cookie
    if len(username) < 6 or len(password) < 10:
        raise RuntimeError(
            "sooplive login failed! Please enter the correct account and password for the sooplive "
            "platform in the config.ini file."
        )

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) Gecko/20100101 Firefox/122.0",
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
    # 获取 SOOP 平台 CDN 流地址
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/119.0",
        "Accept-Language": "zh-CN,zh;q=0.8,zh-TW;q=0.7,zh-HK;q=0.5,en-US;q=0.3,en;q=0.2",
        "Origin": "https://play.sooplive.co.kr",
        "Referer": "https://play.sooplive.co.kr/oul282/249469582",
        "Content-Type": "application/x-www-form-urlencoded",
    }
    if cookies:
        headers["Cookie"] = cookies

    params = {
        "return_type": "gcp_cdn",
        "use_cors": "false",
        "cors_origin_url": "play.sooplive.co.kr",
        "broad_key": f"{broad_no}-common-master-hls",
        "time": "8361.086329376785",
    }

    url2 = "http://livestream-manager.sooplive.co.kr/broad_stream_assign.html?" + urllib.parse.urlencode(params)
    json_str = await async_req(url=url2, proxy_addr=proxy_addr, headers=headers, abroad=True)
    json_str = _get_str_response(json_str)
    json_data = json.loads(json_str)

    return cast(dict[str, object], json_data)


@trace_error_decorator
async def get_sooplive_tk(
    url: str, rtype: str, proxy_addr: OptionalStr = None, cookies: OptionalStr = None
) -> str | tuple[str, str]:
    # 获取 SOOP 平台临时访问 token
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) Gecko/20100101 Firefox/122.0",
        "Origin": "https://play.sooplive.co.kr",
        "Referer": "https://play.sooplive.co.kr/secretx/250989857",
        "Content-Type": "application/x-www-form-urlencoded",
    }

    if cookies:
        headers["Cookie"] = cookies

    split_url = url.split("/")
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
    # 构造 SOOP 平台请求头
    headers = {
        "client-id": str(uuid.uuid4()),
        "user-agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 18_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, "
        "like Gecko) Version/18.5 Mobile/15E148 Safari/604.1 Edg/141.0.0.0",
    }
    if cookies:
        headers["cookie"] = cookies
    return headers


async def _get_soop_channel_info_global(bj_id: str, proxy_addr: OptionalStr = None, cookies: OptionalStr = None) -> str:
    # 获取 SOOP 频道信息（内部通用方法）
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
    # 获取 SOOP 直播流信息（内部通用方法）
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
            bandwidth_pattern = re.compile(r"BANDWIDTH=(\d+)")
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
    # 获取 SOOP 平台直播流数据
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/119.0",
        "Accept-Language": "zh-CN,zh;q=0.8,zh-TW;q=0.7,zh-HK;q=0.5,en-US;q=0.3,en;q=0.2",
        "Referer": "https://m.sooplive.co.kr/",
        "Content-Type": "application/x-www-form-urlencoded",
    }
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
        bandwidth_pattern = re.compile(r"BANDWIDTH=(\d+)")
        bandwidth_list = bandwidth_pattern.findall(resp)
        url_to_bandwidth = {purl: int(bandwidth) for bandwidth, purl in zip(bandwidth_list, play_url_list)}
        play_url_list = sorted(play_url_list, key=lambda purl: url_to_bandwidth[purl], reverse=True)
        return play_url_list

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
    headers = {
        "accept": "application/json, text/plain, */*",
        "accept-language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
        "referer": "https://cc.163.com/",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0",
    }
    if cookies:
        headers["Cookie"] = cookies
    url = url + "/" if url[-1] != "/" else url

    html_str = await async_req(url=url, proxy_addr=proxy_addr, headers=headers)
    html_str = _get_str_response(html_str)
    json_str_match = re.search(
        '<script id="__NEXT_DATA__" .* crossorigin="anonymous">(.*?)</script></body>', html_str, re.DOTALL
    )
    if not json_str_match:
        raise ValueError("Failed to find __NEXT_DATA__")
    json_str = json_str_match.group(1)
    json_data = json.loads(json_str)
    room_data = json_data["props"]["pageProps"]["roomInfoInitData"]
    live_data = room_data["live"]
    result: dict[str, object] = {"is_live": False}
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
    headers = {
        "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8,"
        "application/signed-exchange;v=b3;q=0.7",
        "accept-language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
        "referer": "https://qiandurebo.com/web/index.php",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0",
    }
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
    headers = {
        "origin": "https://www.pandalive.co.kr",
        "referer": "https://www.pandalive.co.kr/",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0",
    }
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
    live_status = "media" in json_data

    if live_status:
        json_str = await async_req(url2, proxy_addr=proxy_addr, headers=headers, data=data2, abroad=True)
        json_str = _get_str_response(json_str)
        json_data = json.loads(json_str)
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
    headers = {
        "accept": "application/json, text/plain, */*",
        "accept-language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
        "referer": "https://fm.missevan.com/live/868895007",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0",
    }
    if cookies:
        headers["Cookie"] = cookies

    room_id = _safe_extract_id(url)
    url2 = f"https://fm.missevan.com/api/v2/live/{room_id}"

    json_str = await async_req(url=url2, proxy_addr=proxy_addr, headers=headers)
    json_str = _get_str_response(json_str)
    json_data = json.loads(json_str)

    anchor_name = json_data["info"]["creator"]["username"]
    live_status = False
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


@trace_error_decorator
async def get_winktv_bj_info(
    url: str, proxy_addr: OptionalStr = None, cookies: OptionalStr = None
) -> tuple[str, object]:
    # 获取 WinkTV 主播信息
    headers = {
        "accept": "application/json, text/plain, */*",
        "accept-language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
        "content-type": "application/x-www-form-urlencoded",
        "referer": "https://www.winktv.co.kr/",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0",
    }
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
    headers = {
        "accept": "application/json, text/plain, */*",
        "accept-language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
        "content-type": "application/x-www-form-urlencoded",
        "referer": "https://www.winktv.co.kr",
        "origin": "https://www.winktv.co.kr",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0",
    }
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


@trace_error_decorator
async def login_flextv(username: str, password: str, proxy_addr: OptionalStr = None) -> OptionalStr:
    # FlexTV 平台登录认证
    headers = {
        "accept": "application/json, text/plain, */*",
        "accept-language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
        "content-type": "application/json;charset=UTF-8",
        "referer": "https://www.ttinglive.com/",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0",
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
    # 获取 FlexTV 直播流地址
    async def fetch_data(cookie: OptionalStr = None) -> dict[str, object]:
        # 抓取 FlexTV 直播数据
        headers = {
            "accept": "application/json, text/plain, */*",
            "accept-language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
            "referer": "https://www.ttinglive.com/",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0",
        }
        user_id = url.split("/live")[0].rsplit("/", maxsplit=1)[-1]
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
    # 获取 FlexTV 直播流数据
    headers = {
        "accept": "application/json, text/plain, */*",
        "accept-language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
        "referer": "https://www.ttinglive.com/",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0",
    }
    if cookies:
        headers["Cookie"] = cookies
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
                raise RuntimeError("FlexTV登录失败！请在config.ini配置文件中填写正确的FlexTV平台的账号和密码")
            new_cookies = await login_flextv(username, password, proxy_addr=proxy_addr)
            if new_cookies:
                print("Logged into FlexTV platform successfully! Starting to fetch live streaming data...")
            else:
                raise RuntimeError("FlexTV login failed")
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
        # 生成 PopkonTV 加密密钥
        charset = "1234567890abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ!@#$%^&*()_+-=[]{}|;:,.<>?"
        return "".join(secrets.choice(charset) for _ in range(size)).encode("utf-8")

    def aes_encrypt(_text: str | bytes, _sec_key: str | bytes) -> bytes:
        # AES 加密数据
        if isinstance(_text, str):
            _text = _text.encode("utf-8")
        if isinstance(_sec_key, str):
            _sec_key = _sec_key.encode("utf-8")
        _sec_key = _sec_key[:16]  # 16 (AES-128), 24 (AES-192), or 32 (AES-256) bytes
        iv = bytes("0102030405060708", "utf-8")
        encryptor = AES.new(_sec_key, AES.MODE_CBC, iv)
        padded_text = pad(_text, AES.block_size)
        ciphertext = encryptor.encrypt(padded_text)
        encoded_ciphertext = base64.b64encode(ciphertext)
        return encoded_ciphertext

    def rsa_encrypt(_text: str | bytes, pub_key: str, mod: str) -> str:
        # RSA 加密数据（公钥加密）
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
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) Gecko/20100101 Firefox/122.0",
        "Accept": "application/json, text/javascript",
        "Accept-Language": "zh-CN,zh;q=0.8,zh-TW;q=0.7,zh-HK;q=0.5,en-US;q=0.3,en;q=0.2",
        "Content-Type": "application/x-www-form-urlencoded",
        "Referer": "https://look.163.com/",
    }

    if cookies:
        headers["Cookie"] = cookies

    room_id_match = re.search("live\\?id=(.*?)&", url)
    if not room_id_match:
        raise ValueError("Failed to find room id in url")
    room_id = room_id_match.group(1)
    params, secretkey = get_looklive_secret_data({"liveRoomNo": room_id})
    request_data = {"params": params, "encSecKey": secretkey}
    api = "https://api.look.163.com/weapi/livestream/room/get/v3"
    json_str = await async_req(api, proxy_addr=proxy_addr, headers=headers, data=request_data)
    json_str = _get_str_response(json_str)
    json_data = json.loads(json_str)
    anchor_name = json_data["data"]["anchor"]["nickName"]
    live_status = json_data["data"]["liveStatus"]
    result: dict[str, object] = {"anchor_name": anchor_name, "is_live": False}
    if live_status == 1:
        result["is_live"] = True
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
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0",
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
) -> tuple[str, list[object] | None] | dict[str, object]:
    # 获取 PopkonTV 直播流数据
    headers = {
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
        "Content-Type": "application/json",
        "Origin": "https://www.popkontv.com",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0",
    }
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

    if not partner_code:
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
    headers = {
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
        "ClientKey": "Client FpAhe6mh8Qtz116OENBmRddbYVirNKasktdXQiuHfm88zRaFydTsFy63tzkdZY0u",
        "Content-Type": "application/json",
        "Origin": "https://www.popkontv.com",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0",
    }

    if access_token:
        headers["Authorization"] = f"Bearer {access_token}"

    anchor_name, room_info = await get_popkontv_stream_data(
        url, proxy_addr=proxy_addr, code=partner_code, username=username
    )
    result: dict[str, object] = {"anchor_name": anchor_name, "is_live": False}
    new_token = None
    if room_info:
        cast_start_date_code, cast_partner_code, mc_sign_id, cast_type, is_private = room_info  # type: ignore[str-unpack]
        result["is_live"] = True
        room_password = get_params(url, "pwd")
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
        if json_data["statusCd"] == "L000A":
            print("Failed to retrieve live stream source,", status_msg)
            raise RuntimeError(
                "You are an unverified member. After logging into the popkontv official website, "
                "please verify your mobile phone at the bottom of the 'My Page' > 'Edit My "
                "Information' to use the service."
            )
        elif json_data["statusCd"] == "L0001":
            cast_start_date_code_int = int(cast(str, cast_start_date_code)) - 1
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
    headers = {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
        "Referer": "https://twitcasting.tv/?ch0",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0",
    }

    anchor_id = url.split("/")[3]
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
    if live_status == "true":
        url_streamserver = f"https://twitcasting.tv/streamserver.php?target={anchor_id}&mode=client&player=pc_web"
        stream_data = await async_req(url_streamserver, proxy_addr=proxy_addr, headers=headers)
        stream_data = _get_str_response(stream_data)
        json_data = json.loads(stream_data)
        if not json_data.get("tc-hls") or not json_data["tc-hls"].get("streams"):
            raise RuntimeError("No m3u8_url,please check the url")

        stream_dict = json_data["tc-hls"]["streams"]
        quality_order = {"high": 0, "medium": 1, "low": 2}
        # 未识别的画质 key 放到最后，避免 KeyError
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
    headers = {
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
        "Connection": "keep-alive",
        "Referer": "https://live.baidu.com/",
        "User-Agent": "ios/7.830 (ios 17.0; ; iPhone 15 (A2846/A3089/A3090/A3092))",
    }
    if cookies:
        headers["Cookie"] = cookies

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
        url_list = []
        prefix = "https://hls.liveshow.bdstatic.com/live/"
        if play_url_list:
            for i in play_url_list:
                flv = i.get("urls", {}).get("flv", "")
                flv_id = flv.rsplit(".", maxsplit=1)[0].rsplit("/", maxsplit=1)
                url_list.append(prefix + (flv_id[1] if len(flv_id) > 1 else "") + ".m3u8")
        else:
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
    headers = {
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
        # 移除原硬编码的微博登录态 Cookie（含 XSRF-TOKEN/SUB/SUBP/WBPSESS 等用户登录凭据）
        # 未配置 cookie 时不发送 Cookie 头；公开直播间信息无需登录态
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0",
        "Referer": "https://weibo.com/u/5885340893",
    }
    if cookies:
        headers["Cookie"] = cookies

    room_id = ""
    if "show/" in url:
        room_id = url.split("?")[0].split("show/")[1]
    else:
        uid = url.split("?")[0].rsplit("/u/", maxsplit=1)[1]
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
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0",
        "Accept": "application/json",
        "Accept-Language": "zh-CN,zh;q=0.8,zh-TW;q=0.7,zh-HK;q=0.5,en-US;q=0.3,en;q=0.2",
        "Referer": "https://fanxing2.kugou.com/",
    }
    if cookies:
        headers["Cookie"] = cookies

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
    if not anchor_name:
        raise RuntimeError(
            "Music channel live rooms are not supported for recording, please switch to a different live room."
        )
    live_status = json_data["data"]["liveType"]
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
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0",
        "Accept-Language": "zh-CN",
        "Referer": "https://www.twitch.tv/",
        "Client-Id": client_id,
        "Client-Integrity": token,
        "Content-Type": "text/plain;charset=UTF-8",
    }
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
    if not json_data or not isinstance(json_data, list):
        raise RuntimeError("Failed to retrieve Twitch user data")
    user_data = json_data[0]["data"]["userOrError"]
    login_name = user_data["login"]
    nickname = f"{user_data['displayName']}-{login_name}"
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
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/115.0",
        "Accept-Language": "en-US",
        "Referer": "https://www.twitch.tv/",
        "Client-ID": client_id,
        "device-id": generate_random_string(16).lower(),
    }

    if cookies:
        headers["Cookie"] = cookies
    uid = url.split("?")[0].rsplit("/", maxsplit=1)[-1]

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
            "acmb": "e30=",
            "allow_source": "true",
            "browser_family": "firefox",
            "browser_version": "124.0",
            "cdm": "wv",
            "fast_bread": "true",
            "os_name": "Windows",
            "os_version": "NT%2010.0",
            "p": "3553732",
            "platform": "web",
            "play_session_id": play_session_id,
            "player_backend": "mediaplayer",
            "player_version": "1.28.0-rc.1",
            "playlist_include_framerate": "true",
            "reassignments_supported": "true",
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
    headers = {
        "origin": "https://www.liveme.com",
        "referer": "https://www.liveme.com",
        "user-agent": "ios/7.830 (ios 17.0; ; iPhone 15 (A2846/A3089/A3090/A3092))",
    }
    if cookies:
        headers["Cookie"] = cookies

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
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/115.0",
    }

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
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/115.0",
    }

    if cookies:
        headers["Cookie"] = cookies

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
    headers = {
        "User-Agent": "living/9.4.0 (com.huajiao.seeding; build:2410231746; iOS 17.0.0) Alamofire/9.4.0",
        "accept-language": "zh-Hans-US;q=1.0",
        "sdk_version": "1",
    }
    if cookies:
        headers["Cookie"] = cookies
    room_id = _safe_extract_id(url)
    api = f"https://live.huajiao.com/feed/getFeedInfo?relateid={room_id}"
    json_str = await async_req(api, proxy_addr=proxy_addr, headers=headers)
    json_str = _get_str_response(json_str)
    json_data = json.loads(json_str)

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
    headers = {
        "accept-language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
        "referer": "https://www.huajiao.com/",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/115.0",
    }
    if cookies:
        headers["Cookie"] = cookies

    result: dict[str, object] = {"anchor_name": "", "is_live": False}

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
    headers = {
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
        "Referer": "https://wap.7u66.com/198189?promoters=0",
        "User-Agent": "ios/7.830 (ios 17.0; ; iPhone 15 (A2846/A3089/A3090/A3092))",
    }
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
    headers = {
        "accept-language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/115.0",
    }
    if cookies:
        headers["Cookie"] = cookies

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
                        result["play_url_list"] = [i.replace("https://", "http://") for i in _play_url_list]
                        break
    return result


@trace_error_decorator
async def get_acfun_sign_params(
    proxy_addr: OptionalStr = None, cookies: OptionalStr = None
) -> tuple[object, str, object]:
    # 计算 Acfun 请求签名参数
    did = f"web_{utils.generate_random_string(16)}"
    headers = {
        "referer": "https://live.acfun.cn/",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/115.0",
        "cookie": f"_did={did};",
    }
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
    headers = {
        "referer": "https://live.acfun.cn/live/17912421",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/115.0",
    }
    if cookies:
        headers["Cookie"] = cookies

    author_id = _safe_extract_id(url)
    user_info_api = f"https://live.acfun.cn/rest/pc-direct/user/userInfo?userId={author_id}"
    json_str = await async_req(user_info_api, proxy_addr=proxy_addr, headers=headers)
    json_str = _get_str_response(json_str)
    json_data = json.loads(json_str)
    anchor_name = json_data["profile"]["name"]
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
    headers = {
        "User-Agent": "ios/7.830 (ios 17.0; ; iPhone 15 (A2846/A3089/A3090/A3092))",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-CN,zh;q=0.8,zh-TW;q=0.7,zh-HK;q=0.5,en-US;q=0.3,en;q=0.2",
        "Referer": "https://wap.tlclw.com/phone/15777?promoters=0",
    }
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
        # 获取映客直播域名
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
    headers = {
        "Referer": "https://www.inke.cn/",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/115.0",
    }
    if cookies:
        headers["Cookie"] = cookies

    parsed_url = urllib.parse.urlparse(url)
    query_params = urllib.parse.parse_qs(parsed_url.query)
    uid = query_params.get("uid", [""])[0]
    live_id = query_params.get("id", [""])[0]
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
    headers = {
        "User-Agent": "ios/7.830 (ios 17.0; ; iPhone 15 (A2846/A3089/A3090/A3092))",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-CN,zh;q=0.8,zh-TW;q=0.7,zh-HK;q=0.5,en-US;q=0.3,en;q=0.2",
        "Referer": "https://live.ybw1666.com/800005143?promoters=0",
    }
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
        # 获取知乎直播域名
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
    headers = {
        "accept-language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/115.0",
    }
    if cookies:
        headers["Cookie"] = cookies

    if "people/" in url:
        user_id = url.split("people/")[1]
        api = f"https://api.zhihu.com/people/{user_id}/profile?profile_new_version="
        json_str = await async_req(api, proxy_addr=proxy_addr, headers=headers)
        json_str = _get_str_response(json_str)
        json_data = json.loads(json_str)
        live_page_url = json_data["drama"]["living_theater"]["theater_url"]
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
    headers = {
        "accept": "application/json, text/plain, */*",
        "accept-language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
        "origin": "https://chzzk.naver.com",
        "referer": "https://chzzk.naver.com/live/458f6ec20b034f49e0fc6d03921646d2",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/115.0",
    }
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
    if cookies:
        headers["Cookie"] = cookies

    room_id = url.split("?")[0].rsplit("/", maxsplit=1)[-1]
    if "haixiutv" in url:
        access_token = "pLXSC%252FXJ0asc1I21tVL5FYZhNJn2Zg6d7m94umCnpgL%252BuVm31GQvyw%253D%253D"
    else:
        access_token = "s7FUbTJ%252BjILrR7kicJUg8qr025ZVjd07DAnUQd8c7g%252Fo4OH9pdSX6w%253D%253D"

    params = {"accessToken": access_token, "tku": "3000006", "c": "10138100100000", "_st1": int(time.time() * 1000)}
    with open(f"{JS_SCRIPT_PATH}/haixiu.js", encoding="utf-8") as f:
        haixiu_js = f.read()
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
    if live_status == 1:
        flv_url = stream_data["media_url_web"]
        result |= {"is_live": True, "flv_url": flv_url, "record_url": flv_url}
    return result


@trace_error_decorator
async def get_vvxqiu_stream_url(
    url: str, proxy_addr: OptionalStr = None, cookies: OptionalStr = None
) -> dict[str, object]:
    # 获取 VV 星球直播流地址
    headers = {
        "User-Agent": "ios/7.830 (ios 17.0; ; iPhone 15 (A2846/A3089/A3090/A3092))",
        "Access-Control-Request-Method": "GET",
        "Origin": "https://h5webcdn-pro.vvxqiu.com",
        "Referer": "https://h5webcdn-pro.vvxqiu.com/",
    }

    if cookies:
        headers["Cookie"] = cookies

    room_id = get_params(url, "roomId")
    api_1 = f"https://h5p.vvxqiu.com/activity-center/fanclub/activity/captain/banner?roomId={room_id}&product=vvstar"
    json_str = await async_req(api_1, proxy_addr=proxy_addr, headers=headers)
    json_str = _get_str_response(json_str)
    json_data = json.loads(json_str)
    anchor_name = json_data["data"]["anchorName"]
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
    if room_id:
        m3u8_url = f"https://liveplay-pro.wasaixiu.com/live/1400442770_{room_id}_{room_id[2:]}_single.m3u8"
    else:
        m3u8_url = ""
    resp = await async_req(m3u8_url, proxy_addr=proxy_addr, headers=headers)
    resp = _get_str_response(resp)
    if "Not Found" not in resp:
        result |= {"is_live": True, "m3u8_url": m3u8_url, "record_url": m3u8_url}
    return result


@trace_error_decorator
async def get_17live_stream_url(
    url: str, proxy_addr: OptionalStr = None, cookies: OptionalStr = None
) -> dict[str, object]:
    # 获取 17Live 直播流地址
    headers = {
        "origin": "https://17.live",
        "referer": "https://17.live/",
        "user-agent": "ios/7.830 (ios 17.0; ; iPhone 15 (A2846/A3089/A3090/A3092))",
    }

    if cookies:
        headers["Cookie"] = cookies

    room_id = url.split("?")[0].rsplit("/", maxsplit=1)[-1]
    api_1 = f"https://wap-api.17app.co/api/v1/user/room/{room_id}"
    json_str = await async_req(api_1, proxy_addr=proxy_addr, headers=headers)
    json_str = _get_str_response(json_str)
    json_data = json.loads(json_str)
    anchor_name = json_data["displayName"]
    result: dict[str, object] = {"anchor_name": anchor_name, "is_live": False}
    json_data = {
        "liveStreamID": room_id,
    }
    api_1 = f"https://wap-api.17app.co/api/v1/lives/{room_id}/viewers/alive"
    json_str = await async_req(api_1, json_data=json_data, proxy_addr=proxy_addr, headers=headers)
    json_str = _get_str_response(json_str)
    json_data = json.loads(json_str)
    live_status = json_data.get("status")
    if live_status and live_status == 2:
        flv_url = json_data["pullURLsInfo"]["rtmpURLs"][0]["urlHighQuality"]
        result |= {"is_live": True, "flv_url": flv_url, "record_url": flv_url}
    return result


@trace_error_decorator
async def get_langlive_stream_url(
    url: str, proxy_addr: OptionalStr = None, cookies: OptionalStr = None
) -> dict[str, object]:
    # 获取浪 Live 直播流地址
    headers = {
        "origin": "https://www.lang.live",
        "referer": "https://www.lang.live/",
        "user-agent": "ios/7.830 (ios 17.0; ; iPhone 15 (A2846/A3089/A3090/A3092))",
    }

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
    headers = {
        "Content-Type": "application/json",
        "Origin": "https://m.pp.weimipopo.com",
        "Referer": "https://m.pp.weimipopo.com/",
        "User-Agent": "ios/7.830 (ios 17.0; ; iPhone 15 (A2846/A3089/A3090/A3092))",
    }

    if cookies:
        headers["Cookie"] = cookies

    room_id = get_params(url, "anchorUid")
    json_data = {
        "inviteUuid": "",
        "anchorUuid": room_id,
    }

    if "catshow" in url:
        api = "https://api.catshow168.com/live/preview"
        headers["Origin"] = "https://h.catshow168.com"
        headers["Referer"] = "https://h.catshow168.com"
    else:
        api = "https://api.pp.weimipopo.com/live/preview"
    json_str = await async_req(api, json_data=json_data, proxy_addr=proxy_addr, headers=headers)
    json_str = _get_str_response(json_str)
    json_data = json.loads(json_str)
    live_info = json_data["data"]
    anchor_name = live_info["name"]
    live_status = live_info["living"]
    result: dict[str, object] = {"anchor_name": anchor_name, "is_live": False}
    if live_status:
        m3u8_url = live_info["pullUrl"]
        result |= {"is_live": True, "m3u8_url": m3u8_url, "record_url": m3u8_url}
    return result


@trace_error_decorator
async def get_6room_stream_url(
    url: str, proxy_addr: OptionalStr = None, cookies: OptionalStr = None
) -> dict[str, object]:
    # 获取六间房直播流地址
    headers = {
        "accept-language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
        "referer": "https://ios.6.cn/?ver=8.0.3&build=4",
        "user-agent": "ios/7.830 (ios 17.0; ; iPhone 15 (A2846/A3089/A3090/A3092))",
    }

    if cookies:
        headers["Cookie"] = cookies

    room_id = _safe_extract_id(url)
    html_str = await async_req(f"https://v.6.cn/{room_id}", proxy_addr=proxy_addr, headers=headers)
    html_str = _get_str_response(html_str)
    room_id_match = re.search("rid: '(.*?)',\n\\s+roomid", html_str)
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
    if flv_title:
        flv_url = f"https://wlive.6rooms.com/httpflv/{flv_title}.flv"
        result |= {"is_live": True, "flv_url": flv_url, "record_url": flv_url}
    return result


@trace_error_decorator
async def get_shopee_stream_url(
    url: str, proxy_addr: OptionalStr = None, cookies: OptionalStr = None
) -> dict[str, object]:
    # 获取 Shopee 直播流地址
    headers = {
        "accept": "application/json, text/plain, */*",
        "accept-language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
        "referer": "https://live.shopee.sg/share?from=live&session=802458&share_user_id=",
        "user-agent": "ios/7.830 (ios 17.0; ; iPhone 15 (A2846/A3089/A3090/A3092))",
    }

    if cookies:
        headers["Cookie"] = cookies

    result: dict[str, object] = {"anchor_name": "", "is_live": False}
    is_living = False

    if "live.shopee" not in url and "uid" not in url:
        url_result = await async_req(url, proxy_addr=proxy_addr, headers=headers, redirect_url=True, abroad=True)
        if isinstance(url_result, str):
            url = url_result

    if "live.shopee" in url:
        host_suffix = url.split("/")[2].rsplit(".", maxsplit=1)[1]
        is_living = get_params(url, "uid") is None
    else:
        host_suffix = url.split("/")[2].split(".", maxsplit=1)[0]

    uid = get_params(url, "uid")
    api_host = f"https://live.shopee.{host_suffix}"
    session_id = get_params(url, "session")
    if uid:
        json_str = await async_req(
            f"{api_host}/api/v1/shop_page/live/ongoing?uid={uid}", proxy_addr=proxy_addr, headers=headers, abroad=True
        )
        json_str = _get_str_response(json_str)
        json_data = json.loads(json_str)
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
            if json_data["data"]["replay"]:
                result["anchor_name"] = json_data["data"]["replay"][0]["nick_name"]
                return result

    json_str = await async_req(
        f"{api_host}/api/v1/session/{session_id}", proxy_addr=proxy_addr, headers=headers, abroad=True
    )
    json_str = _get_str_response(json_str)
    json_data = json.loads(json_str)
    if not json_data.get("data"):
        print("Fetch shopee live data failed, please update the address of the live broadcast room and try again.")
        return result
    uid = json_data["data"]["session"]["uid"]
    anchor_name = json_data["data"]["session"]["nickname"]
    live_status = json_data["data"]["session"]["status"]
    result["anchor_name"] = anchor_name
    result["uid"] = f"uid={uid}&session={session_id}"
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
    headers = {
        "accept-language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/115.0",
    }

    if cookies:
        headers["Cookie"] = cookies

    html_str = await async_req(url, proxy_addr=proxy_addr, headers=headers, abroad=True)
    html_str = _get_str_response(html_str)
    json_str_match = re.search("var ytInitialPlayerResponse = (.*?);var meta = document\\.createElement", html_str)
    if not json_str_match:
        raise ValueError("Failed to find ytInitialPlayerResponse")
    json_str = json_str_match.group(1)
    json_data = json.loads(json_str)
    result: dict[str, object] = {"anchor_name": "", "is_live": False}
    if "videoDetails" not in json_data:
        print("Error: Please log in to YouTube on your device's webpage and configure cookies in the config.ini")
        return result
    result["anchor_name"] = json_data["videoDetails"]["author"]
    live_status = json_data["videoDetails"].get("isLive")
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
    headers = {
        "Referer": "https://huodong.m.taobao.com/",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/115.0",
        "Cookie": "",
    }

    if cookies:
        headers["Cookie"] = cookies

    live_id = get_params(url, "liveId")
    if not live_id:
        html_str = await async_req(url, proxy_addr=proxy_addr, headers=headers)
        html_str = _get_str_response(html_str)
        redirect_url_match = re.findall("var url = '(.*?)';", html_str)
        if not redirect_url_match:
            raise ValueError("Failed to find redirect_url")
        redirect_url = redirect_url_match[0]
        live_id = get_params(redirect_url, "id")

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

    for _ in range(2):
        t13 = int(time.time() * 1000)
        params["t"] = str(t13)

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
        if isinstance(result_tuple, tuple) and len(result_tuple) == 2:
            jsonp_str, new_cookie = result_tuple
        else:
            jsonp_str = str(result_tuple) if result_tuple else ""
            new_cookie = {}
        json_data = utils.jsonp_to_json(jsonp_str)
        if json_data and "ret" in json_data:
            ret_value = json_data["ret"]
            if isinstance(ret_value, list) and len(ret_value) > 0:
                if "哎哟喂,被挤爆啦,请稍后重试" in str(ret_value[0]):
                    raise RuntimeError(f"Please change your taobao cookie: {ret_value}")

                ret_msg = ret_value
                if ret_msg == ["SUCCESS::调用成功"]:
                    anchor_name = cast(str, cast(dict[str, object], json_data["data"])["broadCaster"])
                    result: dict[str, object] = {"anchor_name": anchor_name, "is_live": False}
                    live_status_data = cast(dict[str, object], json_data["data"])
                    live_status = live_status_data.get("streamStatus")

                    def get_sort_key(item: dict[str, object]) -> int:
                        # 京东直播流排序键函数
                        definition_priority = {"lld": 0, "ld": 1, "md": 2, "hd": 3, "ud": 4}
                        def_value = item.get("definition") or item.get("newDefinition")
                        priority = definition_priority.get(str(def_value), -1)
                        return int(priority)

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

                return result
            else:
                if "_m_h5_tk" not in new_cookie or "_m_h5_tk_enc" not in new_cookie:
                    raise RuntimeError(
                        "Try to update cookie failed, please update the cookies in the configuration file"
                    )
                new_cookie_str = utils.dict_to_cookie_str(new_cookie)
                headers["Cookie"] = new_cookie_str
                utils.update_config(f"{script_path}/config/config.ini", "Cookie", "taobao_cookie", new_cookie_str)
    # 如果循环结束还没有返回，返回默认结果
    return {"anchor_name": "", "is_live": False}


@trace_error_decorator
async def get_jd_stream_url(url: str, proxy_addr: OptionalStr = None, cookies: OptionalStr = None) -> dict[str, object]:
    headers = {
        "User-Agent": "ios/7.830 (ios 17.0; ; iPhone 15 (A2846/A3089/A3090/A3092))",
        "origin": "https://lives.jd.com",
        "referer": "https://lives.jd.com/",
        "x-referer-page": "https://lives.jd.com/",
    }

    if cookies:
        headers["Cookie"] = cookies

    redirect_url_result = await async_req(url, proxy_addr=proxy_addr, headers=headers, redirect_url=True)
    if isinstance(redirect_url_result, str):
        redirect_url = redirect_url_result
    else:
        redirect_url = url

    author_id = get_params(redirect_url, "authorId")
    result: dict[str, object] = {"anchor_name": "", "is_live": False}
    live_id_str: str = ""
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
    if live_status == 1:
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
    headers = {
        "Referer": "https://www.faceit.com/zh/players/qpjzz/stream",
        "faceit-referer": "web-next",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/115.0",
    }

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
    if platform == "twitch":
        result = await get_twitchtv_stream_data(f"https://www.twitch.tv/{anchor_id}")
        result["anchor_name"] = anchor_name
    else:
        result = {"anchor_name": anchor_name, "is_live": False}
    return result


@trace_error_decorator
async def get_migu_stream_url(
    url: str, proxy_addr: OptionalStr = None, cookies: OptionalStr = None
) -> dict[str, object]:
    # 获取咪咕直播流地址
    headers = {
        "origin": "https://www.miguvideo.com",
        "referer": "https://www.miguvideo.com/",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/121.0.0.0 Safari/537.36 Edg/121.0.0.0",
        "appCode": "miguvideo_default_www",
        "appId": "miguvideo",
        "channel": "H5",
    }

    if cookies:
        headers["Cookie"] = cookies

    web_id = url.split("?")[0].rsplit("/")[-1]
    api = f"https://vms-sc.miguvideo.com/vms-match/v6/staticcache/basic/basic-data/{web_id}/miguvideo"
    json_str = await async_req(api, proxy_addr=proxy_addr, headers=headers)
    json_str = _get_str_response(json_str)
    json_data = json.loads(json_str)

    anchor_name = json_data["body"]["title"]
    live_title = json_data["body"].get("title") + "-" + json_data["body"].get("detailPageTitle", "")
    room_id = json_data["body"].get("pId")

    result: dict[str, object] = {"anchor_name": anchor_name, "is_live": False}
    if not room_id:
        return result

    params = {
        "contId": room_id,
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
    live_status = json_data["body"]["content"]["currentLive"]
    if live_status != "1":
        return result
    else:
        result["title"] = live_title
        source_url = json_data["body"]["urlInfo"]["url"]

        async def _get_dd_calcu(url: str) -> str:
            # 来秀签名算法（内部方法）
            try:
                result = subprocess.run(
                    ["node", f"{JS_SCRIPT_PATH}/migu.js", url], capture_output=True, text=True, check=True
                )
                return result.stdout.strip()
            except ProgramError:
                raise ProgramError("Failed to execute JS code. Please check if the Node.js environment")

        ddCalcu = await _get_dd_calcu(source_url)
        real_source_url = f"{source_url}&ddCalcu={ddCalcu}&sv=10010"
        if ".m3u8" in real_source_url:
            m3u8_url = await async_req(real_source_url, proxy_addr=proxy_addr, headers=headers, redirect_url=True)
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
    headers = {
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/121.0.0.0 Safari/537.36 Edg/121.0.0.0",
        "accept-language": "zh-CN,zh;q=0.8,zh-TW;q=0.7,zh-HK;q=0.5,en-US;q=0.3,en;q=0.2",
    }

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
    def generate_uuid(ua_type: str) -> str:
        # 生成 UUID（来秀签名用）
        if ua_type == "mobile":
            return str(uuid.uuid4())
        return str(uuid.uuid4()).replace("-", "")

    def calculate_sign(ua_type: str = "pc") -> dict[str, int | str]:
        # 计算来秀请求签名
        a = int(time.time() * 1000)
        s = generate_uuid(ua_type)
        u = "kk792f28d6ff1f34ec702c08626d454b39pro"

        input_str = f"web{s}{a}{u}"
        md5_hash = hashlib.md5(input_str.encode("utf-8")).hexdigest()

        return {"timestamp": a, "imei": s, "requestId": md5_hash, "inputString": input_str}

    sign_data = calculate_sign(ua_type="pc")
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/138.0.0.0 Safari/537.36 Edg/138.0.0.0",
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
    live_status = room_data["playStatus"] == 0

    result: dict[str, object] = {"anchor_name": anchor_name, "is_live": False}
    if live_status:
        flv_url = room_data["playUrl"]
        result |= {"is_live": True, "flv_url": flv_url, "record_url": flv_url}
    return result


@trace_error_decorator
async def get_picarto_stream_url(
    url: str, proxy_addr: OptionalStr = None, cookies: OptionalStr = None
) -> dict[str, object]:
    # 获取 Picarto 直播流地址
    headers = {
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/121.0.0.0 Safari/537.36 Edg/121.0.0.0",
        "accept-language": "zh-CN,zh;q=0.8,zh-TW;q=0.7,zh-HK;q=0.5,en-US;q=0.3,en;q=0.2",
    }

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
    if live_status:
        title = json_data["channel"]["title"]
        m3u8_url = f"https://1-edge1-us-newyork.picarto.tv/stream/hls/golive+{anchor_name}/index.m3u8"
        result |= {"is_live": True, "title": title, "m3u8_url": m3u8_url, "record_url": m3u8_url}
    return result
