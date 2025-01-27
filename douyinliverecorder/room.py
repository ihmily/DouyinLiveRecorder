# -*- encoding: utf-8 -*-

"""
Author: Hmily
GitHub:https://github.com/ihmily
Date: 2023-07-17 23:52:05
Update: 2025-01-27 22:08:00
Copyright (c) 2023 by Hmily, All Rights Reserved.
"""
import json
import re
import urllib.parse
import execjs
import httpx
import urllib.request
from . import JS_SCRIPT_PATH
from .utils import handle_proxy_addr

no_proxy_handler = urllib.request.ProxyHandler({})
opener = urllib.request.build_opener(no_proxy_handler)

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Linux; Android 11; SAMSUNG SM-G973U) AppleWebKit/537.36 (KHTML, like Gecko) '
                  'SamsungBrowser/14.2 Chrome/87.0.4280.141 Mobile Safari/537.36',
    'Accept-Language': 'zh-CN,zh;q=0.8,zh-TW;q=0.7,zh-HK;q=0.5,en-US;q=0.3,en;q=0.2',
    'Cookie': 's_v_web_id=verify_lk07kv74_QZYCUApD_xhiB_405x_Ax51_GYO9bUIyZQVf'
}

HEADERS_PC = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.5845.97 '
                  'Safari/537.36 Core/1.116.438.400 QQBrowser/13.0.6070.400',
    'Cookie': 'sessionid=7494ae59ae06784454373ce25761e864; __ac_nonce=0670497840077ee4c9eb2; '
              '__ac_signature=_02B4Z6wo00f012DZczQAAIDCJJBb3EjnINdg-XeAAL8-db;  '
              's_v_web_id=verify_m1ztgtjj_vuHnMLZD_iwZ9_4YO4_BdN1_7wLP3pyqXsf2; ',
    }


# X-bogus算法
def get_xbogus(url: str, headers: dict | None = None) -> str:
    if not headers or 'user-agent' not in (k.lower() for k in headers):
        headers = HEADERS
    query = urllib.parse.urlparse(url).query
    xbogus = execjs.compile(open(f'{JS_SCRIPT_PATH}/x-bogus.js').read()).call('sign', query, headers.get("User-Agent", "user-agent"))
    return xbogus


# 获取房间ID和用户secID
async def get_sec_user_id(url: str, proxy_addr: str | None = None, headers: dict | None = None) -> tuple | None:
    # 如果没有提供headers或者headers中不包含user-agent和cookie，则使用默认headers
    if not headers or all(k.lower() not in ['user-agent', 'cookie'] for k in headers):
        headers = HEADERS

    try:
        proxy_addr = handle_proxy_addr(proxy_addr)
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
                    print("Could not find sec_user_id in the URL.")
            else:
                print("The redirect URL does not contain 'reflow/'.")
    except Exception as e:
        print(f"An error occurred: {e}")

    return None


# 获取抖音号
async def get_unique_id(url: str, proxy_addr: str | None = None, headers: dict | None = None) -> str | None:
    # 如果没有提供headers或者headers中不包含user-agent和cookie，则使用默认headers
    if not headers or all(k.lower() not in ['user-agent', 'cookie'] for k in headers):
        headers = HEADERS_PC

    try:
        proxy_addr = handle_proxy_addr(proxy_addr)
        async with httpx.AsyncClient(proxy=proxy_addr, timeout=15) as client:
            # 第一次请求，获取重定向后的URL以提取sec_user_id
            response = await client.get(url, headers=headers, follow_redirects=True)
            redirect_url = str(response.url)
            sec_user_id = redirect_url.split('?')[0].rsplit('/', maxsplit=1)[1]

            # 第二次请求，获取用户页面内容来提取unique_id
            user_page_response = await client.get(f'https://www.douyin.com/user/{sec_user_id}', headers=headers)

            # 使用正则表达式查找unique_id
            matches = re.findall(r'undefined\\"},\\"uniqueId\\":\\"(.*?)\\",\\"customVerify', user_page_response.text)
            if matches:
                unique_id = matches[-1]
                return unique_id
            else:
                print("Could not find unique_id in the response.")
                return None
    except Exception as e:
        print(f"An error occurred: {e}")
        return None


# 获取直播间webID
async def get_live_room_id(room_id: str, sec_user_id: str, proxy_addr: str | None = None,
                     params: dict | None = None, headers: dict | None = None) -> str:
    # 如果没有提供headers或者headers中不包含user-agent和cookie，则使用默认headers
    if not headers or all(k.lower() not in ['user-agent', 'cookie'] for k in headers):
        headers = HEADERS

    # 设置默认参数
    if not params:
        params = {
            "verifyFp": "verify_lk07kv74_QZYCUApD_xhiB_405x_Ax51_GYO9bUIyZQVf",
            "type_id": "0",
            "live_id": "1",
            "room_id": room_id,
            "sec_user_id": sec_user_id,
            "app_id": "1128",
            "msToken": "wrqzbEaTlsxt52-vxyZo_mIoL0RjNi1ZdDe7gzEGMUTVh_HvmbLLkQrA_1HKVOa2C6gkxb6IiY6TY2z8enAkPEwGq--gM"
                       "-me3Yudck2ailla5Q4osnYIHxd9dI4WtQ==",
        }

    # 构建API URL并添加X-Bogus签名
    api = f'https://webcast.amemv.com/webcast/room/reflow/info/?{urllib.parse.urlencode(params)}'
    xbogus = get_xbogus(api)
    api = api + "&X-Bogus=" + xbogus

    try:
        proxy_addr = handle_proxy_addr(proxy_addr)
        async with httpx.AsyncClient(proxy=proxy_addr,
                                     timeout=15) as client:
            response = await client.get(api, headers=headers)
            response.raise_for_status()  # 检查HTTP响应状态码是否表示成功

            json_data = response.json()
            web_rid = json_data['data']['room']['owner']['web_rid']
            return web_rid
    except httpx.HTTPStatusError as e:
        print(f"HTTP status error occurred: {e.response.status_code}")
        raise
    except Exception as e:
        print(f"An exception occurred during get_live_room_id: {e}")
        raise


if __name__ == '__main__':
    room_url = "https://v.douyin.com/iQLgKSj/"
    _room_id, sec_uid = get_sec_user_id(room_url)
    web_rid = get_live_room_id(_room_id, sec_uid)
    print("return web_rid:", web_rid)