# -*- encoding: utf-8 -*-

"""
Author: Hmily
Github:https://github.com/ihmily
Date: 2023-07-15 23:15:00
Update: 2023-08-07 06:41:09
Copyright (c) 2023 by Hmily, All Rights Reserved.
Function: Get live stream data.
"""
import hashlib
import time
import urllib
import urllib.parse
import requests
import re
import json
# pip install PyExecJS
import execjs


# 直接选择从网页HTML中获取直播间数据
def get_douyin_stream_data(url, cookies):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/115.0',
        'Accept-Language': 'zh-CN,zh;q=0.8,zh-TW;q=0.7,zh-HK;q=0.5,en-US;q=0.3,en;q=0.2',
        'Referer': 'https://live.douyin.com/',
        'Cookie': cookies
    }

    # response = requests.get(url, headers=headers)
    # html_str = response.text
    # 使用更底层的urllib内置库，防止开启代理时导致的抖音录制SSL 443报错
    request = urllib.request.Request(url, headers=headers)
    response = urllib.request.urlopen(request, timeout=10)
    html_str = response.read().decode('utf-8')
    quote_json_str = re.search('<script id="RENDER_DATA" type="application\/json">(.*?)<\/script><script type=',
                               html_str).group(1)
    unquote_json_str = urllib.parse.unquote(quote_json_str)
    json_data = json.loads(unquote_json_str)
    return json_data


def get_tiktok_stream_data(url, proxy_addr):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36 Edg/114.0.1823.79'
    }

    if proxy_addr != '':
        # 设置代理
        proxies = {
            'http': proxy_addr,
            'https': proxy_addr
        }

        html = requests.get(url, headers=headers, proxies=proxies)
        html_str = html.text

    else:
        request = urllib.request.Request(url, headers=headers)
        response = urllib.request.urlopen(request, timeout=10)
        html_str = response.read().decode('utf-8')

    json_str = re.findall(
        '<script id="SIGI_STATE" type="application/json">(.*?)<\/script><script id="SIGI_RETRY" type="application\/json">',
        html_str)[0]
    # print(json_str)
    json_data = json.loads(json_str)

    return json_data


def get_kuaishou_stream_data(url):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/115.0',
        'Accept-Language': 'zh-CN,zh;q=0.8,zh-TW;q=0.7,zh-HK;q=0.5,en-US;q=0.3,en;q=0.2',
    }

    request = urllib.request.Request(url, headers=headers)
    response = urllib.request.urlopen(request, timeout=10)
    html_str = response.read().decode('utf-8')
    json_str = re.findall('__INITIAL_STATE__=(.*?);\(function', html_str)[0]
    # print(json_str)
    json_data = json.loads(json_str)
    return json_data

def get_huya_stream_data(url):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/115.0',
        'Accept-Language': 'zh-CN,zh;q=0.8,zh-TW;q=0.7,zh-HK;q=0.5,en-US;q=0.3,en;q=0.2',
    }

    request = urllib.request.Request(url, headers=headers)
    response = urllib.request.urlopen(request, timeout=10)
    html_str = response.read().decode('utf-8')
    json_str = re.findall('stream: (\{"data".*?),"iWebDefaultBitRate"', html_str)[0]
    json_data = json.loads(json_str + '}')
    return json_data

def md5(data):
    return hashlib.md5(data.encode('utf-8')).hexdigest()

def get_token_js(rid,did,cdn='ws-h5', rate="0"):
    """
    通过PC网页端的接口获取完整直播源。
    :param cdn: 主线路ws-h5、备用线路tct-h5
    :param rate: 1流畅；2高清；3超清；4蓝光4M；0蓝光8M或10M
    """
    response = urllib.request.urlopen(f'https://www.douyu.com/{rid}', timeout=10)
    html_str = response.read().decode('utf-8')
    result = re.search(r'(vdwdae325w_64we[\s\S]*function ub98484234[\s\S]*?)function', html_str).group(1)
    func_ub9 = re.sub(r'eval.*?;}', 'strc;}', result)
    js = execjs.compile(func_ub9)
    res = js.call('ub98484234')

    t10 = str(int(time.time()))
    v = re.search(r'v=(\d+)', res).group(1)
    rb = md5(rid + did + t10 + v)

    func_sign = re.sub(r'return rt;}\);?', 'return rt;}', res)
    func_sign = func_sign.replace('(function (', 'function sign(')
    func_sign = func_sign.replace('CryptoJS.MD5(cb).toString()', '"' + rb + '"')

    js = execjs.compile(func_sign)
    params = js.call('sign',  rid,  did,  t10)
    # print(params)
    params_list=re.findall('=(.*?)(?=&|$)',params)
    return params_list


def get_douyu_info_data(url):

    match_rid = re.search('rid=(.*?)&', url)
    if match_rid:
        rid = match_rid.group(1)
    else:
        rid = re.search('douyu.com/(.*?)\?dyshid', url).group(1)
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/115.0',
    }
    url=f'https://m.douyu.com/{rid}'
    request = urllib.request.Request(url, headers=headers)
    response = urllib.request.urlopen(request, timeout=10)
    html_str = response.read().decode('utf-8')
    json_str = re.search('ssr_pageContext" type="application\/json">(.*?)<\/script>', html_str).group(1)
    # print(json_str)
    json_data=json.loads(json_str)
    return json_data

def get_douyu_stream_data(rid,rate='-1'):

    did = '10000000000000000000000000003306'
    params_list=get_token_js(rid, did, cdn='ws-h5', rate=rate)


    headers = {
        'User-Agent': 'Mozilla/5.0 (Linux; Android 11; SAMSUNG SM-G973U) AppleWebKit/537.36 (KHTML, like Gecko) SamsungBrowser/14.2 Chrome/87.0.4280.141 Mobile Safari/537.36',
        'Referer': 'https://m.douyu.com/3125893?rid=3125893&dyshid=0-96003918aa5365bc6dcb4933000316p1&dyshci=181',
    }
    data = {
        'v': params_list[0],
        'did': params_list[1],
        'tt': params_list[2],
        'sign': params_list[3],  # 10分钟过期
        'ver': '22011191',
        'rid': rid,
        'rate': rate,  # 0蓝光、3超清、2高清、-1默认
    }
    # 将数据转换为 URL 编码的字节格式
    data = urllib.parse.urlencode(data).encode('utf-8')
    app_api='https://m.douyu.com/hgapi/livenc/room/getStreamUrl'
    request = urllib.request.Request(app_api, data=data, headers=headers)
    response = urllib.request.urlopen(request, timeout=10)
    json_str = response.read().decode('utf-8')
    json_data = json.loads(json_str)
    return json_data


if __name__ == '__main__':
    # 抖音直播间页面的cookie
    Cookie = 'ttwid=1%7CB1qls3GdnZhUov9o2NxOMxxYS2ff6OSvEWbv0ytbES4%7C1680522049%7C280d802d6d478e3e78d0c807f7c487e7ffec0ae4e5fdd6a0fe74c3c6af149511; my_rd=1; passport_csrf_token=3ab34460fa656183fccfb904b16ff742; passport_csrf_token_default=3ab34460fa656183fccfb904b16ff742; d_ticket=9f562383ac0547d0b561904513229d76c9c21; n_mh=hvnJEQ4Q5eiH74-84kTFUyv4VK8xtSrpRZG1AhCeFNI; store-region=cn-fj; store-region-src=uid; LOGIN_STATUS=1; __security_server_data_status=1; FORCE_LOGIN=%7B%22videoConsumedRemainSeconds%22%3A180%7D; pwa2=%223%7C0%7C3%7C0%22; download_guide=%223%2F20230729%2F0%22; volume_info=%7B%22isUserMute%22%3Afalse%2C%22isMute%22%3Afalse%2C%22volume%22%3A0.6%7D; strategyABtestKey=%221690824679.923%22; stream_recommend_feed_params=%22%7B%5C%22cookie_enabled%5C%22%3Atrue%2C%5C%22screen_width%5C%22%3A1536%2C%5C%22screen_height%5C%22%3A864%2C%5C%22browser_online%5C%22%3Atrue%2C%5C%22cpu_core_num%5C%22%3A8%2C%5C%22device_memory%5C%22%3A8%2C%5C%22downlink%5C%22%3A10%2C%5C%22effective_type%5C%22%3A%5C%224g%5C%22%2C%5C%22round_trip_time%5C%22%3A150%7D%22; VIDEO_FILTER_MEMO_SELECT=%7B%22expireTime%22%3A1691443863751%2C%22type%22%3Anull%7D; home_can_add_dy_2_desktop=%221%22; __live_version__=%221.1.1.2169%22; device_web_cpu_core=8; device_web_memory_size=8; xgplayer_user_id=346045893336; csrf_session_id=2e00356b5cd8544d17a0e66484946f28; odin_tt=724eb4dd23bc6ffaed9a1571ac4c757ef597768a70c75fef695b95845b7ffcd8b1524278c2ac31c2587996d058e03414595f0a4e856c53bd0d5e5f56dc6d82e24004dc77773e6b83ced6f80f1bb70627; __ac_nonce=064caded4009deafd8b89; __ac_signature=_02B4Z6wo00f01HLUuwwAAIDBh6tRkVLvBQBy9L-AAHiHf7; ttcid=2e9619ebbb8449eaa3d5a42d8ce88ec835; webcast_leading_last_show_time=1691016922379; webcast_leading_total_show_times=1; webcast_local_quality=sd; live_can_add_dy_2_desktop=%221%22; msToken=1JDHnVPw_9yTvzIrwb7cQj8dCMNOoesXbA_IooV8cezcOdpe4pzusZE7NB7tZn9TBXPr0ylxmv-KMs5rqbNUBHP4P7VBFUu0ZAht_BEylqrLpzgt3y5ne_38hXDOX8o=; msToken=jV_yeN1IQKUd9PlNtpL7k5vthGKcHo0dEh_QPUQhr8G3cuYv-Jbb4NnIxGDmhVOkZOCSihNpA2kvYtHiTW25XNNX_yrsv5FN8O6zm3qmCIXcEe0LywLn7oBO2gITEeg=; tt_scid=mYfqpfbDjqXrIGJuQ7q-DlQJfUSG51qG.KUdzztuGP83OjuVLXnQHjsz-BRHRJu4e986'
    # url = "https://live.douyin.com/745964462470"  # 抖音直播
    # url = "https://www.tiktok.com/@pearlgaga88/live"  # Tiktok直播
    # url = "https://live.kuaishou.com/u/yall1102"  # 快手直播
    # url = 'https://www.huya.com/116'  # 虎牙直播
    url = 'https://www.douyu.com/topic/wzDBLS6?rid=4921614&dyshid='  # 斗鱼直播
    url = 'https://www.douyu.com/3637778?dyshid='

    # print(get_douyin_stream_data(url,Cookie))
    # print(get_tiktok_stream_data(url,''))
    # print(get_kuaishou_stream_data(url))
    # print(get_huya_stream_data(url))
    print(get_douyu_info_data(url))
    print(get_douyu_stream_data("4921614",rate='-1'))
