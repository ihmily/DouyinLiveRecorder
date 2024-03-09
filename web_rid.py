# -*- encoding: utf-8 -*-

"""
Author: Hmily
Github:https://github.com/ihmily
Date: 2023-07-17 23:52:05
Update: 2024-03-06 23:35:00
Copyright (c) 2023 by Hmily, All Rights Reserved.
"""
import json
import re
import urllib.parse
from typing import Union
import execjs  # pip install PyExecJS
import requests
import urllib.request

no_proxy_handler = urllib.request.ProxyHandler({})
opener = urllib.request.build_opener(no_proxy_handler)

headers = {
    'User-Agent': 'Mozilla/5.0 (Linux; Android 11; SAMSUNG SM-G973U) AppleWebKit/537.36 (KHTML, like Gecko) SamsungBrowser/14.2 Chrome/87.0.4280.141 Mobile Safari/537.36',
    'Accept-Language': 'zh-CN,zh;q=0.8,zh-TW;q=0.7,zh-HK;q=0.5,en-US;q=0.3,en;q=0.2',
    'Cookie': 's_v_web_id=verify_lk07kv74_QZYCUApD_xhiB_405x_Ax51_GYO9bUIyZQVf'
}


# X-bogus算法
def get_xbogus(url: str) -> str:
    query = urllib.parse.urlparse(url).query
    xbogus = execjs.compile(open('./x-bogus.js').read()).call('sign', query, headers["User-Agent"])
    # print(xbogus)
    return xbogus


# 获取房间ID和用户secID
def get_sec_user_id(url: str, proxy_addr: Union[str, None] = None):
    if proxy_addr:
        proxies = {
            'http': proxy_addr,
            'https': proxy_addr
        }
        response = requests.get(url, headers=headers, proxies=proxies, timeout=15)
    else:
        response = opener.open(url, timeout=15)
    redirect_url = response.url
    sec_user_id = re.search(r'sec_user_id=([\w\d_\-]+)&', redirect_url).group(1)
    room_id = redirect_url.split('?')[0].rsplit('/', maxsplit=1)[1]
    return room_id, sec_user_id


# 获取直播间webID
def get_live_room_id(room_id: str, sec_user_id: str, proxy_addr: Union[str, None] = None) -> str:
    url = f'https://webcast.amemv.com/webcast/room/reflow/info/?verifyFp=verify_lk07kv74_QZYCUApD_xhiB_405x_Ax51_GYO9bUIyZQVf&type_id=0&live_id=1&room_id={room_id}&sec_user_id={sec_user_id}&app_id=1128&msToken=wrqzbEaTlsxt52-vxyZo_mIoL0RjNi1ZdDe7gzEGMUTVh_HvmbLLkQrA_1HKVOa2C6gkxb6IiY6TY2z8enAkPEwGq--gM-me3Yudck2ailla5Q4osnYIHxd9dI4WtQ=='
    xbogus = get_xbogus(url)  # 获取X-Bogus算法
    url = url + "&X-Bogus=" + xbogus

    if proxy_addr:
        proxies = {
            'http': proxy_addr,
            'https': proxy_addr
        }
        response = requests.get(url, headers=headers, proxies=proxies, timeout=15)
        json_str = response.text
    else:
        req = urllib.request.Request(url, headers=headers)
        response = opener.open(req, timeout=15)
        json_str = response.read().decode('utf-8')
    json_data = json.loads(json_str)
    return json_data['data']['room']['owner']['web_rid']


if __name__ == '__main__':
    url = "https://v.douyin.com/iQLgKSj/"
    # url="https://v.douyin.com/iQFeBnt/"
    # url="https://v.douyin.com/iehvKttp/"
    room_id, sec_user_id = get_sec_user_id(url)
    web_rid = get_live_room_id(room_id, sec_user_id)
    print(web_rid)
