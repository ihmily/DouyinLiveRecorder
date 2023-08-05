# -*- encoding: utf-8 -*-

"""
Author: Hmily
Github:https://github.com/ihmily
Date: 2023-07-15 23:15:00
Update: 2023-08-05 23:37:00
Copyright (c) 2023 by Hmily, All Rights Reserved.
Function: Get live stream data.
"""
import urllib
import urllib.parse
import requests
import re
import json


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


if __name__ == '__main__':
    # 抖音直播间页面的cookie
    Cookie = 'ttwid=1%7CB1qls3GdnZhUov9o2NxOMxxYS2ff6OSvEWbv0ytbES4%7C1680522049%7C280d802d6d478e3e78d0c807f7c487e7ffec0ae4e5fdd6a0fe74c3c6af149511; my_rd=1; passport_csrf_token=3ab34460fa656183fccfb904b16ff742; passport_csrf_token_default=3ab34460fa656183fccfb904b16ff742; d_ticket=9f562383ac0547d0b561904513229d76c9c21; n_mh=hvnJEQ4Q5eiH74-84kTFUyv4VK8xtSrpRZG1AhCeFNI; store-region=cn-fj; store-region-src=uid; LOGIN_STATUS=1; __security_server_data_status=1; FORCE_LOGIN=%7B%22videoConsumedRemainSeconds%22%3A180%7D; pwa2=%223%7C0%7C3%7C0%22; download_guide=%223%2F20230729%2F0%22; volume_info=%7B%22isUserMute%22%3Afalse%2C%22isMute%22%3Afalse%2C%22volume%22%3A0.6%7D; strategyABtestKey=%221690824679.923%22; stream_recommend_feed_params=%22%7B%5C%22cookie_enabled%5C%22%3Atrue%2C%5C%22screen_width%5C%22%3A1536%2C%5C%22screen_height%5C%22%3A864%2C%5C%22browser_online%5C%22%3Atrue%2C%5C%22cpu_core_num%5C%22%3A8%2C%5C%22device_memory%5C%22%3A8%2C%5C%22downlink%5C%22%3A10%2C%5C%22effective_type%5C%22%3A%5C%224g%5C%22%2C%5C%22round_trip_time%5C%22%3A150%7D%22; VIDEO_FILTER_MEMO_SELECT=%7B%22expireTime%22%3A1691443863751%2C%22type%22%3Anull%7D; home_can_add_dy_2_desktop=%221%22; __live_version__=%221.1.1.2169%22; device_web_cpu_core=8; device_web_memory_size=8; xgplayer_user_id=346045893336; csrf_session_id=2e00356b5cd8544d17a0e66484946f28; odin_tt=724eb4dd23bc6ffaed9a1571ac4c757ef597768a70c75fef695b95845b7ffcd8b1524278c2ac31c2587996d058e03414595f0a4e856c53bd0d5e5f56dc6d82e24004dc77773e6b83ced6f80f1bb70627; __ac_nonce=064caded4009deafd8b89; __ac_signature=_02B4Z6wo00f01HLUuwwAAIDBh6tRkVLvBQBy9L-AAHiHf7; ttcid=2e9619ebbb8449eaa3d5a42d8ce88ec835; webcast_leading_last_show_time=1691016922379; webcast_leading_total_show_times=1; webcast_local_quality=sd; live_can_add_dy_2_desktop=%221%22; msToken=1JDHnVPw_9yTvzIrwb7cQj8dCMNOoesXbA_IooV8cezcOdpe4pzusZE7NB7tZn9TBXPr0ylxmv-KMs5rqbNUBHP4P7VBFUu0ZAht_BEylqrLpzgt3y5ne_38hXDOX8o=; msToken=jV_yeN1IQKUd9PlNtpL7k5vthGKcHo0dEh_QPUQhr8G3cuYv-Jbb4NnIxGDmhVOkZOCSihNpA2kvYtHiTW25XNNX_yrsv5FN8O6zm3qmCIXcEe0LywLn7oBO2gITEeg=; tt_scid=mYfqpfbDjqXrIGJuQ7q-DlQJfUSG51qG.KUdzztuGP83OjuVLXnQHjsz-BRHRJu4e986'
    url = "https://live.douyin.com/745964462470"  # 抖音直播
    # url = "https://www.tiktok.com/@pearlgaga88/live"  # Tiktok 直播
    # url = "https://live.kuaishou.com/u/yall1102"  # 快手直播
    url = 'https://www.huya.com/116'
    # print(get_douyin_stream_data(url,Cookie))
    # print(get_tiktok_stream_data(url,''))
    # print(get_kuaishou_stream_data(url))
    print(get_huya_stream_data(url))
