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
    # 移动端 UA（Android 14 + Chrome 141，与 stream_select.MOBILE_UA 一致；X-Bogus 签名以
    # 请求头中的同一 UA 计算，UA 与签名必须自洽，更新字符串安全）
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


# 2026-10-21 M-43：调用方头的合并必须以 HEADERS 为**基底逐键补齐**，不得整组替换。
# 旧判据 `if not headers or all(k.lower() not in ["user-agent", "cookie"] for k in headers)`
# 的语义是「UA 与 Cookie 里只要出现任意一个，就完全不补默认头」——于是只带 Cookie 的调用方
# 拿不到移动端 UA（抖音接口对 UA 敏感，见 DESKTOP_UA 注释与「已知坑」抖音风控条目），
# 只带 UA 的调用方拿不到 Cookie 位；两处都是「配置了一半就当成没配置」。
# 空值默认（HEADERS["Cookie"] = ""）刻意不注入：访问页面时服务器会重新下发该 Cookie，
# 主动发出一个空的 Cookie 头等于改变请求指纹，与整组替换前「不带该头」的行为不等价。
def _merge_default_headers(headers: dict[str, str] | None) -> dict[str, str]:
    merged: dict[str, str] = dict(headers) if headers else {}
    present = {k.lower() for k in merged}
    for name, value in HEADERS.items():
        if not value or name.lower() in present:
            continue
        merged[name] = value
    return merged


# 2026-10-21 M-43：把单个键值对（形如 ttwid=<value>）合并进已有 Cookie 串。
# 旧写法 `headers["Cookie"] = ttwid_cookie` 会**整串覆盖**调用方 Cookie——用户在配置里填的
# 登录态（sessionid / passport_csrf_token 等）被一次 ttwid 自动获取抹掉，表现为「填了 Cookie
# 却仍按游客态解析」。同名键在原位置替换、其余键原样保留；Cookie 键名按 HTTP 惯例大小写不敏感。
def _merge_cookie_pair(cookie: str, pair: str) -> str:
    key = pair.split("=", 1)[0].strip().lower()
    parts = [p.strip() for p in (cookie or "").split(";") if p.strip()]
    merged: list[str] = []
    replaced = False
    for part in parts:
        if part.split("=", 1)[0].strip().lower() == key:
            # 同名键只保留一份：命中处换成新值，后续重复的同名键一并丢弃（重复 Cookie 键本就非法）
            if not replaced:
                merged.append(pair)
                replaced = True
            continue
        merged.append(part)
    if not replaced:
        merged.append(pair)
    return "; ".join(merged)


# 2026-10-21 M-58④：出站前的目标闸门（只拦「发出去」这一步，不改响应读取形态）。
# url 来自用户配置 / Web 面板 / 短链落地页，属外部可控输入；旧代码除 httpx 自带的形态校验外
# 没有任何 scheme / host / 内网判定，写成 http://127.0.0.1:6379/ 或
# http://169.254.169.254/latest/meta-data/ 会被照常 GET（且 follow_redirects=True 逐跳跟随），
# 于是「内网端口是否开放 / 云元数据是否存在」变成一个稳定的观测口（与 AGENTS「重定向逐跳复检
# 只有两个合法接线点」同源：判定一律复用 async_http 那一份，不在此另写内网名单）。
# 刻意**不**顺手把响应读取改成流式：新增出站读取点必须同批登记 tests/test_outbound_read_caps.py
# 的 (文件, 函数) 台账（该文件不在本次改动范围），故本次只做前置闸门，读取上限维持既有形态。
def _outbound_target_reason(url: str, proxy_addr: str | None) -> str | None:
    from .async_http import internal_stream_target_reason

    # 函数内 import：src.async_http 经 .web_config 取内网判据，模块级引入会把这条边加进
    # 本模块的初始化顺序（room 由 spider 导入，spider 又与 stream_select/main 互为依赖）。
    if not utils.is_safe_http_url(url):
        return "协议不在白名单或缺少主机名"
    parsed = urllib.parse.urlparse(url)
    if parsed.username or parsed.password:
        # userinfo 形态会把凭据同时写进 URL 与出站请求（httpx 会按 basic auth 带出去），
        # 而本仓的凭据只应来自 Cookie/配置，不接受地址内嵌。
        return "URL 含 userinfo"
    return internal_stream_target_reason(url, utils.handle_proxy_addr(proxy_addr))


async def _ensure_douyin_ttwid(proxy_addr: str | None = None) -> str:
    # 委托给共享 ttwid.py 模块（带 threading.Lock 跨线程去重），
    # 解决多线程并发时重复拉取 ttwid 触发风控的问题。
    # [2026-10-30 L-03] 本模块的 _cached_ttwid 镜像变量已删除：全仓无任何读取点（ttwid.py 自己的
    # 同名镜像才是真缓存），「兼容旧引用」的原注释为失实陈述。
    result = await _shared_get_ttwid(proxy_addr)
    return result


# 为 url 的 query 计算 X-Bogus 签名（node 执行 src/javascript/x-bogus.js）
async def get_xbogus(url: str, headers: dict[str, str] | None = None) -> str:
    if not headers or "user-agent" not in (k.lower() for k in headers):
        headers = HEADERS
    query = urllib.parse.urlparse(url).query
    # UA 必须与签名计算所用的一致（headers 键大小写不敏感）
    user_agent = next((v for k, v in headers.items() if k.lower() == "user-agent"), HEADERS["User-Agent"])
    # 原为同步读文件 + execjs.compile().call()（起 node 子进程阻塞等 stdout），而本函数被抖音
    # 解析链路高频调用 → 冻结事件循环且每次重复编译。改 utils.run_js_async：阻塞段丢线程池，
    # 编译产物按 (路径, mtime) 缓存。
    xbogus = cast(str, await utils.run_js_async(f"{JS_SCRIPT_PATH}/x-bogus.js", "sign", query, user_agent))
    return xbogus


# 获取房间ID和用户secID
async def get_sec_user_id(
    url: str, proxy_addr: str | None = None, headers: dict[str, str] | None = None
) -> tuple[str, str] | None:
    # 2026-10-21 M-43：逐键合并取代整组替换（判据与理由见 _merge_default_headers）。
    # 本函数只读头、不写头，故无需再 dict() 复制。
    headers = _merge_default_headers(headers)
    # 2026-10-21 M-58④：出站前闸门，命中即拒、绝不发包。出口复用本模块既有的
    # UnsupportedUrlError（spider.py 的 get_douyin_app_stream_data 已有对应 except 分支）。
    target_reason = _outbound_target_reason(url, proxy_addr)
    if target_reason is not None:
        raise UnsupportedUrlError(f"URL target rejected: {utils.mask_credentials(url)} - {target_reason}")

    try:
        proxy_addr = utils.handle_proxy_addr(proxy_addr)
        # 必须传 verify=http_config.ssl_verify：原先未传、httpx 默认恒校验，用户在 config.ini
        # 关闭证书校验后，抖音解析链路（sec_user_id / unique_id / web_rid）仍会因证书问题失败
        # M-04（2026-10-30）：直建点必须挂与 async_http._build_client 同一逐跳复检钩子——
        # follow_redirects=True 下「公网短链 → 302 → 内网/元数据」的跳转落点原本不被复检。
        # 函数内 import：与上方 _outbound_target_reason 同理由（本模块不做 async_http 模块级依赖）。
        from .async_http import _build_hop_guard

        async with httpx.AsyncClient(
            proxy=proxy_addr,
            timeout=15,
            verify=http_config.ssl_verify,
            event_hooks={"response": [_build_hop_guard(proxy_addr)]},
        ) as client:
            response = await client.get(url, headers=headers, follow_redirects=True)
            redirect_url = response.url
            if "reflow/" in str(redirect_url):
                # 参数值后用前瞻断言 (?=&|#|$)：若要求其后必须紧跟 `&`，sec_user_id 位于
                # query 末尾（无后继参数）时匹配失败，该房间每轮永久失败。
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
        # e 的 str 内嵌完整 URL（InvalidURL/TooManyRedirects 等可能带 token 参数），
        # 包装前过码——异常文本会进入 logs（多份轮转保留）。
        raise RuntimeError(f"An error occurred: {utils.mask_credentials(str(e))}") from e


def is_user_homepage_url(url: str) -> bool:
    # 判断 URL 是否为「网页端主播主页」（www.douyin.com/user/<sec_uid>）。这类链接的
    # sec_user_id 直接写在路径里，且不会重定向到 reflow 直播间页，可跳过跟随重定向的探测请求；
    # v.douyin.com 短链无法从形态判断指向主页还是直播间，不属于此类。
    return bool(re.search(r"douyin\.com/user/[\w\-]+", url))


def extract_sec_user_id(redirect_url: str) -> str:
    # 从主页链接中提取 sec_user_id（形如 MS4wLjABAAAA...）。兼容三种形态：
    #   1. https://www.douyin.com/user/MS4w...            （网页端主页）
    #   2. https://www.iesdouyin.com/share/user/MS4w...?  （v.douyin.com 短链重定向后）
    #   3. 任意形态但带 sec_uid=MS4w... 查询参数
    # 不用 rsplit("/") 取最后一段：遇到尾斜杠会取到空串。
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


# 进程级 sec_user_id -> 抖音号缓存
# 抖音号（unique_id/short_id）几乎不变，而 get_unique_id 在每个 room 的轮询循环里都会被调用
# （默认每 120s 一次）。不缓存则每次轮询都要请求 iesdouyin 接口并拉取 ttwid。
# per-loop 的 asyncio.Lock 无法跨房间/跨 asyncio 循环协调，故用 threading.Lock。
# 30 分钟过期：在「消除重复请求」与「账号信息变更后自愈」之间取平衡（进程可能连续运行数天）。
_SEC_UID_UNIQUE_CACHE: dict[str, tuple[str, float]] = {}
_SEC_UID_CACHE_LOCK = threading.Lock()
_SEC_UID_CACHE_TTL = 30 * 60
# 缓存条数上限（M-36b）：sec_user_id 是外部可控输入（主页链接 / 短链落地页 / 用户自填地址），
# 一个进程连续运行数天时会不断有新 sec_uid 进来；旧实现只在读取时「跳过」过期条目却从不删除，
# dict 只增不减 → 内存无界增长。到达上限时按**写入序**逐出最旧一条（不是访问序 LRU：
# 命中路径不重排字典，代价是多留几条仍在使用但尚未过期的条目，远小于无界）。
_SEC_UID_CACHE_MAX_ENTRIES = 512


def _get_cached_unique_id(sec_user_id: str) -> str | None:
    now = time.monotonic()
    with _SEC_UID_CACHE_LOCK:
        entry = _SEC_UID_UNIQUE_CACHE.get(sec_user_id)
        if entry is None:
            return None
        unique_id, recorded_at = entry
        if (now - recorded_at) < _SEC_UID_CACHE_TTL:
            return unique_id
        # 2026-10-21 M-36b：过期即删。旧写法只 return None、条目留在表里等下次覆盖，
        # 而一个 sec_uid 往往只出现一次（换主播就不再回来）——于是过期条目永远无人回收。
        _SEC_UID_UNIQUE_CACHE.pop(sec_user_id, None)
    return None


def _set_cached_unique_id(sec_user_id: str, unique_id: str) -> None:
    with _SEC_UID_CACHE_LOCK:
        _SEC_UID_UNIQUE_CACHE[sec_user_id] = (unique_id, time.monotonic())
        while len(_SEC_UID_UNIQUE_CACHE) > _SEC_UID_CACHE_MAX_ENTRIES:
            oldest = next(iter(_SEC_UID_UNIQUE_CACHE), None)
            if oldest is None:
                break
            _SEC_UID_UNIQUE_CACHE.pop(oldest, None)


async def get_unique_id(url: str, proxy_addr: str | None = None, headers: dict[str, str] | None = None) -> str | None:
    # 将「主播主页链接」解析为抖音号（unique_id），供上层拼接 live.douyin.com/<抖音号> 录制。
    #
    # iesdouyin 的 share/user 页已改为 JS 混淆的反爬壳页（响应体内不再含 unique_id），
    # 故优先调用 JSON 接口，HTML 正则仅作兜底。
    # 2026-10-21 M-43：逐键合并（见 _merge_default_headers）——只带 Cookie 的调用方此前拿不到
    # 默认 UA，只带 UA 的调用方拿不到 Cookie 位，两种「半配置」都被当成「不配置」。
    headers = _merge_default_headers(headers)
    # 复制一份：下方会写入 Cookie，直接改会污染模块级共享的 HEADERS（多线程下互相干扰）
    headers = dict(headers)
    # 2026-10-21 M-58④：出站前闸门（同 get_sec_user_id，判据见 _outbound_target_reason）。
    # 本函数的 url 同样来自用户配置/短链落地页，必须发之前就拒。
    target_reason = _outbound_target_reason(url, proxy_addr)
    if target_reason is not None:
        raise UnsupportedUrlError(f"URL target rejected: {utils.mask_credentials(url)} - {target_reason}")

    try:
        proxy_addr = utils.handle_proxy_addr(proxy_addr)
        # M-04（2026-10-30）：逐跳复检钩子与 get_sec_user_id 同批接线（理由见彼处注释）；
        # follow_redirects=True 的跳转落点必须逐跳复检。
        from .async_http import _build_hop_guard

        async with httpx.AsyncClient(
            proxy=proxy_addr,
            timeout=15,
            verify=http_config.ssl_verify,
            event_hooks={"response": [_build_hop_guard(proxy_addr)]},
        ) as client:
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
            # 命中缓存即省一次 iesdouyin 请求
            cached_unique_id = _get_cached_unique_id(sec_user_id)
            if cached_unique_id is not None:
                return cached_unique_id
            # 动态获取 ttwid，替代原硬编码的过期 ttwid/__ac_nonce/__ac_signature
            ttwid_cookie = await _ensure_douyin_ttwid(proxy_addr)
            if ttwid_cookie:
                # 2026-10-21 M-43：只替换 Cookie 串里的 ttwid 这一对，其余键（用户手填的登录态）
                # 原样保留。旧写法整串覆盖 = 每次自动取访客 ID 都把登录 Cookie 抹掉。
                cookie_key = next((k for k in headers if k.lower() == "cookie"), "Cookie")
                headers[cookie_key] = _merge_cookie_pair(headers.get(cookie_key, ""), ttwid_cookie)

            # 主路径：JSON 接口直接返回 unique_id。该接口对 User-Agent 敏感——用模块级
            # HEADERS 的移动端 UA 会被风控返回 HTTP 200 + 空 body（len=0），必须用桌面端 Chrome UA。
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
                # 用 debug 而非 warning：这是每轮都会走的兜底降级路径，warning 会淹掉真线索
                # （同 spider.py）。记录类型与脱敏 URL，避免根因（证书 / 代理 / DNS / 风控
                # 200+空 body / JSON 改版）完全没落盘。
                logger.debug(
                    i18n.tr(
                        "抖音 unique_id 接口失败（转 HTML 兜底）: {type_name}: {e} - {masked_url}",
                        type_name=type(e).__name__,
                        # 2026-10-21 M-41：本行原样记 e 时，同一模板里 masked_url 已过码、异常文本却没过——
                        # httpx/urllib 的异常 str() 必然内嵌完整请求 URL（含 sec_uid、代理 userinfo、
                        # 可能的 cookie 相关参数），而 logs/ 按大小轮转保留多份 = 凭据长期落盘。
                        # msgid 保持不变（四目录与 web/app.js 五处同源，本文件不收录词条）。
                        e=utils.mask_credentials(str(e)),
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


# get_live_room_id 已删除：全仓无生产调用点（web_rid 由 spider.get_douyin_stream_url 的
# webcast/room/web/enter 接口直接返回），且键缺失分支与 -> str 注解矛盾。

if __name__ == "__main__":
    import asyncio

    room_url = "https://v.douyin.com/iQLgKSj/"
    result = asyncio.run(get_sec_user_id(room_url))
    if result is not None:
        _room_id, sec_uid = result
        print("return sec_user_id:", sec_uid)
