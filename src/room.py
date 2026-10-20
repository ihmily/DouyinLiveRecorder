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
from typing import cast

import httpx

import i18n
from src.logger import logger

from . import JS_SCRIPT_PATH, http_config, utils
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
    # [历史注] 原硬编码的 s_v_web_id（抖音访客校验 ID）系过期凭据，已移除；
    # 访问页面时服务器会重新下发该 Cookie，留空即可。
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


# 为 url 的 query 计算 X-Bogus 签名（node 执行 src/javascript/x-bogus.js）
async def get_xbogus(url: str, headers: dict[str, str] | None = None) -> str:
    if not headers or "user-agent" not in (k.lower() for k in headers):
        headers = HEADERS
    query = urllib.parse.urlparse(url).query
    # UA 必须与签名计算所用的一致（headers 键大小写不敏感）；此前默认值误写成字面量 "user-agent"
    user_agent = next((v for k, v in headers.items() if k.lower() == "user-agent"), HEADERS["User-Agent"])
    # 2026-09-12 审查 6.3：原为同步读文件 + execjs.compile().call()（起 node 子进程阻塞等
    # stdout），本 async 函数被抖音解析链路高频调用 → 同步阻塞会冻结调用方整个事件循环且每次
    # 重复 compile。改 utils.run_js_async：阻塞段丢线程池，编译产物按 (路径, mtime) 缓存。
    xbogus = cast(str, await utils.run_js_async(f"{JS_SCRIPT_PATH}/x-bogus.js", "sign", query, user_agent))
    return xbogus


# 获取房间ID和用户secID
async def get_sec_user_id(
    url: str, proxy_addr: str | None = None, headers: dict[str, str] | None = None
) -> tuple[str, str] | None:
    if not headers or all(k.lower() not in ["user-agent", "cookie"] for k in headers):
        headers = HEADERS

    try:
        proxy_addr = utils.handle_proxy_addr(proxy_addr)
        # 2026-09-12 审查 6.3：补 verify=http_config.ssl_verify（控制面开关）。原先三处
        # AsyncClient 均未传该参数、httpx 默认恒校验——用户在 config.ini 关闭证书校验后，
        # 抖音解析链路（sec_user_id / unique_id / web_rid）仍会因证书问题失败，开关形同不一致
        async with httpx.AsyncClient(proxy=proxy_addr, timeout=15, verify=http_config.ssl_verify) as client:
            response = await client.get(url, headers=headers, follow_redirects=True)
            redirect_url = response.url
            if "reflow/" in str(redirect_url):
                # L-11（2026-10-02）：参数值后改为前瞻断言 (?=&|#|$)——原要求紧随 `&`，
                # sec_user_id 位于 query 末尾（无后继参数）时匹配失败，该房每轮永久失败；
                # 与同文件 rid=/mcid= 的既有写法一致。
                match = re.search(r"sec_user_id=([\w_\-]+)(?=&|#|$)", str(redirect_url))
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
        # L-07（2026-10-02）：e 的 str 内嵌完整 URL（InvalidURL/TooManyRedirects 等可能带
        # token 参数），包装前过码——异常文本会进入上层日志（logs 轮转保留多份）
        raise RuntimeError(f"An error occurred: {utils.mask_credentials(str(e))}") from e


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
        async with httpx.AsyncClient(proxy=proxy_addr, timeout=15, verify=http_config.ssl_verify) as client:
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
            # 命中 _SEC_UID_UNIQUE_CACHE 即省一次 iesdouyin 请求（表头注释说明为何可缓存）
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
            except Exception as e:
                # MID-2246（2026-09-23）：原为 `except Exception: pass` 零日志。主路径（iesdouyin
                # JSON 接口）失败后走 HTML 兜底（AGENTS 记载「已是 JS 反爬壳页、正则通常失效」），
                # 用户只看到上层「网址内容获取失败」而根因（证书 / 代理 / DNS / 风控 200+空 body /
                # JSON 改版）没落盘，违反 AGENTS「异常日志须带类型与上下文、禁止静默吞异常」。用
                # debug 而非 warning：这是每轮都走的有兜底降级路径，warning 会淹掉真线索（同 spider.py）。
                logger.debug(
                    i18n.tr(
                        "抖音 unique_id 接口失败（转 HTML 兜底）: {type_name}: {e} - {masked_url}",
                        type_name=type(e).__name__,
                        e=e,
                        masked_url=utils.mask_credentials(api),
                    )
                )

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
        # L-07：同 get_sec_user_id——异常文本过码后再包装
        raise RuntimeError(f"An error occurred: {utils.mask_credentials(str(e))}") from e


# L-13（2026-10-02）：get_live_room_id 已删除——全仓无生产调用点（web_rid 由
# spider.get_douyin_stream_url 的 webcast/room/web/enter 接口直接返回），且其键缺失
# 分支 cast(str, owner.get("web_rid")) 实际返回 None、与 -> str 注解矛盾。

if __name__ == "__main__":
    import asyncio

    room_url = "https://v.douyin.com/iQLgKSj/"
    result = asyncio.run(get_sec_user_id(room_url))
    if result is not None:
        _room_id, sec_uid = result
        print("return sec_user_id:", sec_uid)
