# -*- encoding: utf-8 -*-

# Author: Hmily
# GitHub:https://github.com/ihmily
# Date: 2023-07-17 23:52:05
# Update: 2025-02-04 04:57:00
# Copyright (c) 2023 by Hmily, All Rights Reserved.
import re
import threading
import time
import urllib.parse

# 优先使用 exejs（PyExecJS 的活跃维护继任者），未安装时回退到 PyExecJS
try:
    import exejs as execjs
except ImportError:
    import execjs  # type: ignore[no-redef]

from typing import cast

import httpx

from . import JS_SCRIPT_PATH, utils
from .ttwid import get_ttwid as _shared_get_ttwid


class UnsupportedUrlError(Exception):
    # 不支持的 URL 格式异常
    pass


HEADERS = {
    # 移动端 UA（2026-08 统一升级为 Android 14 + Chrome 141，与 stream_select.MOBILE_UA
    # 一致；X-Bogus 签名以请求头中的同一 UA 计算，UA 与签名自洽，更新字符串安全）
    "User-Agent": "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) "
    + "Chrome/141.0.0.0 Mobile Safari/537.36",
    "Accept-Language": "zh-CN,zh;q=0.8,zh-TW;q=0.7,zh-HK;q=0.5,en-US;q=0.3,en;q=0.2",
    # 移除原硬编码的 s_v_web_id 访客校验 Cookie
    # 该字段为抖音访客校验 ID，原值为硬编码过期凭据，访问页面时服务器会重新下发
    "Cookie": "",
}

# 桌面端 Chrome UA：部分抖音接口（如 iesdouyin 用户信息接口）在旧版移动端 UA 下
# 会被风控静默拦截（返回 HTTP 200 但响应体为空），需改用桌面端 UA 请求。
DESKTOP_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 " "(KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36"
)

# 缓存自动获取的抖音 ttwid（已委托给共享 ttwid.py 模块，保留变量兼容旧引用）
_cached_ttwid: str = ""


async def _ensure_douyin_ttwid(proxy_addr: str | None = None) -> str:
    # 委托给共享 ttwid.py 模块（带 threading.Lock 跨线程去重），
    # 解决多线程并发时重复拉取 ttwid 触发风控的问题
    global _cached_ttwid
    result = await _shared_get_ttwid(proxy_addr)
    _cached_ttwid = result  # 同步本地缓存
    return result


# X-bogus算法
async def get_xbogus(url: str, headers: dict[str, str] | None = None) -> str:
    if not headers or "user-agent" not in (k.lower() for k in headers):
        headers = HEADERS
    query = urllib.parse.urlparse(url).query
    # headers 键大小写不敏感，回退到 HEADERS 的真实 UA（此前默认值误写为字面量 "user-agent"）
    user_agent = next((v for k, v in headers.items() if k.lower() == "user-agent"), HEADERS["User-Agent"])
    with open(f"{JS_SCRIPT_PATH}/x-bogus.js", encoding="utf-8") as f:
        xbogus_js = f.read()
    xbogus = cast(str, execjs.compile(xbogus_js).call("sign", query, user_agent))
    return xbogus


# 获取房间ID和用户secID
async def get_sec_user_id(
    url: str, proxy_addr: str | None = None, headers: dict[str, str] | None = None
) -> tuple[str, str] | None:
    if not headers or all(k.lower() not in ["user-agent", "cookie"] for k in headers):
        headers = HEADERS

    try:
        proxy_addr = utils.handle_proxy_addr(proxy_addr)
        async with httpx.AsyncClient(proxy=proxy_addr, timeout=15) as client:
            response = await client.get(url, headers=headers, follow_redirects=True)
            redirect_url = response.url
            if "reflow/" in str(redirect_url):
                match = re.search(r"sec_user_id=([\w_\-]+)&", str(redirect_url))
                if match:
                    sec_user_id = match.group(1)
                    room_id = str(redirect_url).split("?")[0].rsplit("/", maxsplit=1)[1]
                    return room_id, sec_user_id
                else:
                    raise RuntimeError("Could not find sec_user_id in the URL.")
            else:
                raise UnsupportedUrlError("The redirect URL does not contain 'reflow/'.")
    except UnsupportedUrlError as e:
        raise e
    except Exception as e:
        raise RuntimeError(f"An error occurred: {e}")


def is_user_homepage_url(url: str) -> bool:
    # 判断 URL 是否为「网页端主播主页」形态（www.douyin.com/user/<sec_uid>）。
    # 这类链接的 sec_user_id 直接写在路径里，且不会重定向到 reflow 直播间页，
    # 因此可跳过跟随重定向的探测请求。
    # 注意：v.douyin.com 短链无法从形态判断指向主页还是直播间，不属于此类。
    return bool(re.search(r"douyin\.com/user/[\w\-]+", url))


def extract_sec_user_id(redirect_url: str) -> str:
    # 从主页链接中提取 sec_user_id（形如 MS4wLjABAAAA...）。
    # 兼容三种形态：
    #   1. https://www.douyin.com/user/MS4w...            （网页端主页）
    #   2. https://www.iesdouyin.com/share/user/MS4w...?  （v.douyin.com 短链重定向后）
    #   3. 任意形态但带 sec_uid=MS4w... 查询参数
    # 原实现用 rsplit("/") 取最后一段，遇到尾斜杠会取到空串，故改为显式匹配。
    query_match = re.search(r"[?&]sec_uid=([\w\-]+)", redirect_url)
    if query_match:
        return query_match.group(1)
    path = redirect_url.split("?")[0].rstrip("/")
    path_match = re.search(r"/(?:user|share/user)/([\w\-]+)$", path)
    if path_match:
        return path_match.group(1)
    # 兜底：取最后一个非空路径段
    segments = [seg for seg in path.split("/") if seg]
    return segments[-1] if segments else ""


# 进程级 sec_user_id -> 抖音号 缓存
# 抖音号（unique_id/short_id）几乎不会变化，但 get_unique_id 在每个 room 的轮询循环里都会被调用
# （默认每 120s 一次）。若不缓存，每次轮询都要请求 iesdouyin 接口并拉取 ttwid。
# 与 ttwid.py 同理：per-loop 的 asyncio.Lock 无法跨房间/跨 asyncio 循环协调，故用 threading.Lock。
# 设 30 分钟过期：在「消除重复请求」与「账号信息变更后自愈」之间取得平衡（录制进程可能连续运行数天）。
_SEC_UID_UNIQUE_CACHE: dict[str, tuple[str, float]] = {}
_SEC_UID_CACHE_LOCK = threading.Lock()
_SEC_UID_CACHE_TTL = 30 * 60


def _get_cached_unique_id(sec_user_id: str) -> str | None:
    now = time.monotonic()
    with _SEC_UID_CACHE_LOCK:
        entry = _SEC_UID_UNIQUE_CACHE.get(sec_user_id)
        if entry is not None and (now - entry[1]) < _SEC_UID_CACHE_TTL:
            return entry[0]
    return None


def _set_cached_unique_id(sec_user_id: str, unique_id: str) -> None:
    with _SEC_UID_CACHE_LOCK:
        _SEC_UID_UNIQUE_CACHE[sec_user_id] = (unique_id, time.monotonic())


# 获取抖音号
async def get_unique_id(url: str, proxy_addr: str | None = None, headers: dict[str, str] | None = None) -> str | None:
    # 将「主播主页链接」解析为抖音号（unique_id），供上层拼接 live.douyin.com/<抖音号> 录制。
    #
    # 实现说明：原方案抓取 https://www.iesdouyin.com/share/user/<sec_uid> 的 HTML 再正则提取
    # unique_id，但该页面已改为 JS 混淆的反爬壳页（响应体内不再包含任何 unique_id 字段），
    # 导致所有主页类链接解析必然失败。现改为优先调用 JSON 接口，HTML 正则降级为兜底。
    if not headers or all(k.lower() not in ["user-agent", "cookie"] for k in headers):
        headers = HEADERS
    # 复制一份：下方会写入 Cookie，直接改会污染模块级共享的 HEADERS（多线程下互相干扰）
    headers = dict(headers)

    try:
        proxy_addr = utils.handle_proxy_addr(proxy_addr)
        async with httpx.AsyncClient(proxy=proxy_addr, timeout=15) as client:
            # 快速路径：网页端主页链接的 sec_user_id 已在路径中，无需发请求跟随重定向，
            # 可省去一次约 70KB 的主页 HTML 下载。
            sec_user_id = extract_sec_user_id(url) if is_user_homepage_url(url) else ""
            if not sec_user_id:
                # v.douyin.com 短链等形态必须跟随重定向才能拿到主页地址
                response = await client.get(url, headers=headers, follow_redirects=True)
                redirect_url = str(response.url)
                if "reflow/" in redirect_url:
                    raise UnsupportedUrlError("Unsupported URL")
                sec_user_id = extract_sec_user_id(redirect_url)
                if not sec_user_id:
                    raise RuntimeError(f"Could not extract sec_user_id from {redirect_url}")
            # 进程级缓存：sec_user_id -> 抖音号 映射几乎不变，但每个 room 轮询都会重解析
            # （默认每 120s 一次），命中缓存可省去一次 iesdouyin 接口请求及其 ttwid 依赖。
            cached_unique_id = _get_cached_unique_id(sec_user_id)
            if cached_unique_id is not None:
                return cached_unique_id
            # 动态获取 ttwid，替代原硬编码的过期 ttwid/__ac_nonce/__ac_signature
            ttwid_cookie = await _ensure_douyin_ttwid(proxy_addr)
            if ttwid_cookie:
                headers["Cookie"] = ttwid_cookie

            # 主路径：JSON 接口直接返回 unique_id
            # 注意：该接口对 User-Agent 敏感——沿用模块级 HEADERS 的旧版移动端 UA 时，
            # 抖音风控会返回 HTTP 200 但响应体为空（len=0），必须使用桌面端 Chrome UA。
            api_headers = {**headers, "User-Agent": DESKTOP_UA, "Referer": "https://www.douyin.com/"}
            api = f"https://www.iesdouyin.com/web/api/v2/user/info/?sec_uid={sec_user_id}"
            try:
                api_response = await client.get(api, headers=api_headers, follow_redirects=True)
                user_info = cast(dict[str, object], cast(dict[str, object], api_response.json()).get("user_info") or {})
                unique_id_value = user_info.get("unique_id")
                if isinstance(unique_id_value, str) and unique_id_value:
                    _set_cached_unique_id(sec_user_id, unique_id_value)
                    return unique_id_value
                # 部分账号未设置抖音号，unique_id 为空，此时退回 short_id
                short_id_value = user_info.get("short_id")
                if isinstance(short_id_value, str) and short_id_value and short_id_value != "0":
                    _set_cached_unique_id(sec_user_id, short_id_value)
                    return short_id_value
            except Exception:
                pass  # 接口异常时继续走 HTML 兜底

            # 兜底路径：分享页 HTML 正则（页面改版后通常已失效，保留以防接口下线）
            user_page_response = await client.get(
                f"https://www.iesdouyin.com/share/user/{sec_user_id}", headers=headers, follow_redirects=True
            )
            matches = re.findall(r'unique_id":"(.*?)","verification_type', user_page_response.text)
            if matches:
                unique_id = cast(str, matches[-1])
                _set_cached_unique_id(sec_user_id, unique_id)
                return unique_id
            else:
                raise RuntimeError(f"Could not resolve unique_id for sec_user_id={sec_user_id}")
    except UnsupportedUrlError as e:
        raise e
    except Exception as e:
        raise RuntimeError(f"An error occurred: {e}")


# 获取直播间webID
async def get_live_room_id(
    room_id: str,
    sec_user_id: str,
    proxy_addr: str | None = None,
    params: dict[str, str] | None = None,
    headers: dict[str, str] | None = None,
) -> str:
    if not headers or all(k.lower() not in ["user-agent", "cookie"] for k in headers):
        headers = HEADERS

    if not params:
        # 移除原硬编码的 verifyFp 和 msToken 过期凭据
        # verifyFp（访客指纹）和 msToken（请求令牌）原为硬编码过期值，
        # 留空时由抖音服务器在响应中重新下发，避免凭据失效导致功能异常
        params = {
            "verifyFp": "",
            "type_id": "0",
            "live_id": "1",
            "room_id": room_id,
            "sec_user_id": sec_user_id,
            "app_id": "1128",
            "msToken": "",
        }

    api = f"https://webcast.amemv.com/webcast/room/reflow/info/?{urllib.parse.urlencode(params)}"
    xbogus = await get_xbogus(api)
    api = api + "&X-Bogus=" + xbogus

    try:
        proxy_addr = utils.handle_proxy_addr(proxy_addr)
        async with httpx.AsyncClient(proxy=proxy_addr, timeout=15) as client:
            response = await client.get(api, headers=headers)
            _ = response.raise_for_status()
            json_data = cast(dict[str, object], response.json())
            data = cast(dict[str, object], json_data.get("data", {}))
            room = cast(dict[str, object], data.get("room", {}))
            owner = cast(dict[str, object], room.get("owner", {}))
            return cast(str, owner.get("web_rid"))
    except httpx.HTTPStatusError as e:
        print(f"HTTP status error occurred: {e.response.status_code}")
        raise
    except Exception as e:
        print(f"An exception occurred during get_live_room_id: {e}")
        raise


if __name__ == "__main__":
    import asyncio

    room_url = "https://v.douyin.com/iQLgKSj/"
    result = asyncio.run(get_sec_user_id(room_url))
    if result is not None:
        _room_id, sec_uid = result
        web_rid = asyncio.run(get_live_room_id(_room_id, sec_uid))
        print("return web_rid:", web_rid)
