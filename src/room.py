# -*- encoding: utf-8 -*-

# Author: Hmily
# GitHub:https://github.com/ihmily
# Date: 2023-07-17 23:52:05
# Update: 2025-02-04 04:57:00
# Copyright (c) 2023 by Hmily, All Rights Reserved.
import re
import urllib.parse
import execjs
import httpx
from . import JS_SCRIPT_PATH, utils


class UnsupportedUrlError(Exception):
    # 不支持的 URL 格式异常
    pass


HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Linux; Android 11; SAMSUNG SM-G973U) AppleWebKit/537.36 (KHTML, like Gecko) '
                  'SamsungBrowser/14.2 Chrome/87.0.4280.141 Mobile Safari/537.36',
    'Accept-Language': 'zh-CN,zh;q=0.8,zh-TW;q=0.7,zh-HK;q=0.5,en-US;q=0.3,en;q=0.2',
    # 移除原硬编码的 s_v_web_id 访客校验 Cookie
    # 该字段为抖音访客校验 ID，原值为硬编码过期凭据，访问页面时服务器会重新下发
    'Cookie': ''
}

# 缓存自动获取的抖音 ttwid，避免每次请求都重新获取
_cached_ttwid: str = ""


async def _ensure_douyin_ttwid(proxy_addr: str | None = None) -> str:
    # 自动访问抖音主页获取 ttwid，替代硬编码过期凭据
    # 注意：room.py 被 spider.py 导入，此处不能反向导入 spider._ensure_ttwid，需本地实现
    global _cached_ttwid
    if _cached_ttwid:
        return _cached_ttwid
    try:
        proxy_addr = utils.handle_proxy_addr(proxy_addr)
        async with httpx.AsyncClient(proxy=proxy_addr, timeout=10) as client:
            response = await client.get(
                'https://live.douyin.com/',
                headers={'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                                       '(KHTML, like Gecko) Chrome/116.0.0.0 Safari/537.36'},
                follow_redirects=True
            )
            cookies = response.cookies
            ttwid = cookies.get('ttwid', '')
            if ttwid:
                _cached_ttwid = f"ttwid={ttwid}"
    except Exception:
        pass
    return _cached_ttwid


# X-bogus算法
async def get_xbogus(url: str, headers: dict | None = None) -> str:
    if not headers or 'user-agent' not in (k.lower() for k in headers):
        headers = HEADERS
    query = urllib.parse.urlparse(url).query
    # headers 键大小写不敏感，回退到 HEADERS 的真实 UA（此前默认值误写为字面量 "user-agent"）
    user_agent = next((v for k, v in headers.items() if k.lower() == 'user-agent'), HEADERS['User-Agent'])
    with open(f'{JS_SCRIPT_PATH}/x-bogus.js', encoding='utf-8') as f:
        xbogus_js = f.read()
    xbogus = execjs.compile(xbogus_js).call('sign', query, user_agent)
    return xbogus


# 获取房间ID和用户secID
async def get_sec_user_id(url: str, proxy_addr: str | None = None, headers: dict | None = None) -> tuple | None:
    if not headers or all(k.lower() not in ['user-agent', 'cookie'] for k in headers):
        headers = HEADERS

    try:
        proxy_addr = utils.handle_proxy_addr(proxy_addr)
        async with httpx.AsyncClient(proxy=proxy_addr, timeout=15) as client:
            response = await client.get(url, headers=headers, follow_redirects=True)
            redirect_url = response.url
            if 'reflow/' in str(redirect_url):
                match = re.search(r'sec_user_id=([\w_\-]+)&', str(redirect_url))
                if match:
                    sec_user_id = match.group(1)
                    room_id = str(redirect_url).split('?')[0].rsplit('/', maxsplit=1)[1]
                    return room_id, sec_user_id
                else:
                    raise RuntimeError("Could not find sec_user_id in the URL.")
            else:
                raise UnsupportedUrlError("The redirect URL does not contain 'reflow/'.")
    except UnsupportedUrlError as e:
        raise e
    except Exception as e:
        raise RuntimeError(f"An error occurred: {e}")


# 获取抖音号
async def get_unique_id(url: str, proxy_addr: str | None = None, headers: dict | None = None) -> str | None:
    if not headers or all(k.lower() not in ['user-agent', 'cookie'] for k in headers):
        headers = HEADERS

    try:
        proxy_addr = utils.handle_proxy_addr(proxy_addr)
        async with httpx.AsyncClient(proxy=proxy_addr, timeout=15) as client:
            response = await client.get(url, headers=headers, follow_redirects=True)
            redirect_url = str(response.url)
            if 'reflow/' in redirect_url:
                raise UnsupportedUrlError("Unsupported URL")
            sec_user_id = redirect_url.split('?')[0].rsplit('/', maxsplit=1)[1]
            # 动态获取 ttwid，替代原硬编码的过期 ttwid/__ac_nonce/__ac_signature
            ttwid_cookie = await _ensure_douyin_ttwid(proxy_addr)
            if ttwid_cookie:
                headers['Cookie'] = ttwid_cookie
            user_page_response = await client.get(f'https://www.iesdouyin.com/share/user/{sec_user_id}',
                                                headers=headers, follow_redirects=True)
            matches = re.findall(r'unique_id":"(.*?)","verification_type', user_page_response.text)
            if matches:
                unique_id = matches[-1]
                return unique_id
            else:
                raise RuntimeError("Could not find unique_id in the response.")
    except UnsupportedUrlError as e:
        raise e
    except Exception as e:
        raise RuntimeError(f"An error occurred: {e}")


# 获取直播间webID
async def get_live_room_id(room_id: str, sec_user_id: str, proxy_addr: str | None = None, params: dict | None = None,
                           headers: dict | None = None) -> str:
    if not headers or all(k.lower() not in ['user-agent', 'cookie'] for k in headers):
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

    api = f'https://webcast.amemv.com/webcast/room/reflow/info/?{urllib.parse.urlencode(params)}'
    xbogus = await get_xbogus(api)
    api = api + "&X-Bogus=" + xbogus

    try:
        proxy_addr = utils.handle_proxy_addr(proxy_addr)
        async with httpx.AsyncClient(proxy=proxy_addr,
                                     timeout=15) as client:
            response = await client.get(api, headers=headers)
            response.raise_for_status()
            json_data = response.json()
            return json_data['data']['room']['owner']['web_rid']
    except httpx.HTTPStatusError as e:
        print(f"HTTP status error occurred: {e.response.status_code}")
        raise
    except Exception as e:
        print(f"An exception occurred during get_live_room_id: {e}")
        raise


if __name__ == '__main__':
    import asyncio
    room_url = "https://v.douyin.com/iQLgKSj/"
    result = asyncio.run(get_sec_user_id(room_url))
    if result is not None:
        _room_id, sec_uid = result
        web_rid = asyncio.run(get_live_room_id(_room_id, sec_uid))
        print("return web_rid:", web_rid)
