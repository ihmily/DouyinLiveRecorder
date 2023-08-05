# -*- encoding: utf-8 -*-

"""
Author: Hmily
Github:https://github.com/ihmily
Date: 2023-07-17 23:52:05
Update: 2023-08-05 23:47:30
Copyright (c) 2023 by Hmily, All Rights Reserved.
"""
import json
import urllib.parse
# import execjs  # pip install PyExecJS
import requests

headers = {
        'User-Agent': 'Mozilla/5.0 (Linux; Android 11; SAMSUNG SM-G973U) AppleWebKit/537.36 (KHTML, like Gecko) SamsungBrowser/14.2 Chrome/87.0.4280.141 Mobile Safari/537.36',
        'Accept-Language': 'zh-CN,zh;q=0.8,zh-TW;q=0.7,zh-HK;q=0.5,en-US;q=0.3,en;q=0.2',
        'Cookie': 's_v_web_id=verify_lk07kv74_QZYCUApD_xhiB_405x_Ax51_GYO9bUIyZQVf'
    }


# X-bogus算法
# def get_xbogus(url) -> str:
#     query = urllib.parse.urlparse(url).query
#     xbogus = execjs.compile(open('./x-bogus.js').read()).call('sign', query, headers["User-Agent"])
#     # print(xbogus)
#     return xbogus

# X-Bogus.js在我的服务器上用node.js运行了，这里直接调用就好
def get_xbogus2(url) -> str:
    query = urllib.parse.urlparse(url).query
    url = "http://43.138.133.177:8890/xbogus"
    data = {"url":query,"ua":headers["User-Agent"]}
    response = requests.get(url,params=data)
    xbogus =response.json()["result"]
    # print(f'生成的X-Bogus签名为: {xbogus}')
    return xbogus


# 获取房间ID和用户secID
def get_sec_user_id(url):
    # response=requests.get(url)
    response = urllib.request.urlopen(url)
    redirect_url = response.url
    sec_user_id=redirect_url.split('sec_user_id=')[1].rsplit('&ecom_share')[0]
    room_id=redirect_url.split('?')[0].rsplit('/',maxsplit=1)[1]
    return room_id,sec_user_id


# 获取直播间webID
def get_live_room_id(room_id,sec_user_id):
    url= f'https://webcast.amemv.com/webcast/room/reflow/info/?verifyFp=verify_lk07kv74_QZYCUApD_xhiB_405x_Ax51_GYO9bUIyZQVf&type_id=0&live_id=1&room_id={room_id}&sec_user_id={sec_user_id}&app_id=1128&msToken=wrqzbEaTlsxt52-vxyZo_mIoL0RjNi1ZdDe7gzEGMUTVh_HvmbLLkQrA_1HKVOa2C6gkxb6IiY6TY2z8enAkPEwGq--gM-me3Yudck2ailla5Q4osnYIHxd9dI4WtQ=='
    xbogus = get_xbogus2(url)  # 获取X-Bogus算法
    url = url + "&X-Bogus=" + xbogus
    # response = requests.get(url,headers=headers)
    # json_data=response.json()
    # 通通改成用urlib库，防止同时录制Tiktok直播时，代理影响requests请求出错
    request = urllib.request.Request(url, headers=headers)
    response = urllib.request.urlopen(request, timeout=10)
    html_str = response.read().decode('utf-8')
    json_data = json.loads(html_str)
    web_rid=json_data['data']['room']['owner']['web_rid']
    return web_rid


if __name__ == '__main__':
    url="https://v.douyin.com/iQLgKSj/"
    # url="https://v.douyin.com/iQFeBnt/"
    room_id,sec_user_id = get_sec_user_id(url)
    web_rid=get_live_room_id(room_id,sec_user_id)
    print(web_rid)

