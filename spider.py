# -*- encoding: utf-8 -*-

"""
Author: Hmily
Github:https://github.com/ihmily
Date: 2023-07-15 23:15:00
Update: 2023-08-03 08:06:43
Copyright (c) 2023 by Hmily, All Rights Reserved.
Function: Get douyin and titok live stream.
"""
import urllib
import urllib.parse
import requests
import re
import json

# 直接选择从网页HTML中获取直播间数据
def get_douyin_stream_data(url,cookies):

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/115.0',
        'Accept-Language': 'zh-CN,zh;q=0.8,zh-TW;q=0.7,zh-HK;q=0.5,en-US;q=0.3,en;q=0.2',
        'Referer': 'https://live.douyin.com/',
        # 'Cookie':'ttwid=1^%^7CIkooT8SJQrpeYtHlSALuhz9BdcHpaaf9tHQRKHuDaYE^%^7C1687785070^%^7C6690250483b63b6482128174d0f93bd879614d76f1b6e03ca52e032cf7fbaafd; passport_csrf_token=52bece134ac246c81163cc93b72f86a6; passport_csrf_token_default=52bece134ac246c81163cc93b72f86a6; d_ticket=2b9e3eb3626216c0122f0d980f867deb7b414; odin_tt=36dcfa4bd95b1edf0e6445dc9584a7371b4b90a2a8c390292b9be44af8161e06d10e34e6e575bf43c45c0a5871229533; passport_assist_user=CjxqZLHwcDmhxMjoh8u0-Jz4Zmhcq9VzKQqpAjK3P9Ve87i4njjbsai_u6NAI6MebG4KH4QXtbfNRbRFWRgaSAo8oBvHC_eXhqSGSo1uWPz4KBGu9uo-UdwM-5ynbDuDQRybofj0pQlPexcYmVoryiYqpC7yMdKO4rSVclgNEJbxtA0Yia_WVCIBA78Lg84^%^3D; n_mh=hvnJEQ4Q5eiH74-84kTFUyv4VK8xtSrpRZG1AhCeFNI; passport_auth_status=a74f300f376940d65914eb148d55ca96^%^2C9ca487aea255972120d502f736c5dd7b; passport_auth_status_ss=a74f300f376940d65914eb148d55ca96^%^2C9ca487aea255972120d502f736c5dd7b; sso_auth_status=52ecac30d95890cc7896c880366aa21a; sso_auth_status_ss=52ecac30d95890cc7896c880366aa21a; sso_uid_tt=a71f659bc416b890eb13929ee82a4340; sso_uid_tt_ss=a71f659bc416b890eb13929ee82a4340; toutiao_sso_user=da6c1f563492114cf1ad2dac7617e3f4; toutiao_sso_user_ss=da6c1f563492114cf1ad2dac7617e3f4; sid_ucp_sso_v1=1.0.0-KDNhOTk2NzYzZjkzMGZkZDdlNDU4ODE3YjczNGE3MGExYTBhOGQ0OGIKHQjRpfzk8AEQn6LmpAYY7zEgDDCRxffLBTgCQPEHGgJsZiIgZGE2YzFmNTYzNDkyMTE0Y2YxYWQyZGFjNzYxN2UzZjQ; ssid_ucp_sso_v1=1.0.0-KDNhOTk2NzYzZjkzMGZkZDdlNDU4ODE3YjczNGE3MGExYTBhOGQ0OGIKHQjRpfzk8AEQn6LmpAYY7zEgDDCRxffLBTgCQPEHGgJsZiIgZGE2YzFmNTYzNDkyMTE0Y2YxYWQyZGFjNzYxN2UzZjQ; sid_guard=219f9f2d8838724307589f32debd7d62^%^7C1687785774^%^7C5183988^%^7CFri^%^2C+25-Aug-2023+13^%^3A22^%^3A42+GMT; uid_tt=9f33ebaf781ad75909d6d4edb0b46b86; uid_tt_ss=9f33ebaf781ad75909d6d4edb0b46b86; sid_tt=219f9f2d8838724307589f32debd7d62; sessionid=219f9f2d8838724307589f32debd7d62; sessionid_ss=219f9f2d8838724307589f32debd7d62; sid_ucp_v1=1.0.0-KGZkMzE1MGRhMTZiOTI4M2ZkOTkzMjIwNjQ5NmJhMjhjMzlhZmFmMGYKGQjRpfzk8AEQrqLmpAYY7zEgDDgCQPEHSAQaAmxmIiAyMTlmOWYyZDg4Mzg3MjQzMDc1ODlmMzJkZWJkN2Q2Mg; ssid_ucp_v1=1.0.0-KGZkMzE1MGRhMTZiOTI4M2ZkOTkzMjIwNjQ5NmJhMjhjMzlhZmFmMGYKGQjRpfzk8AEQrqLmpAYY7zEgDDgCQPEHSAQaAmxmIiAyMTlmOWYyZDg4Mzg3MjQzMDc1ODlmMzJkZWJkN2Q2Mg; LOGIN_STATUS=1; store-region=cn-fj; store-region-src=uid; __security_server_data_status=1; __live_version__=^%^221.1.1.1250^%^22; live_can_add_dy_2_desktop=^%^220^%^22; xgplayer_user_id=528819598596; publish_badge_show_info=^%^220^%^2C0^%^2C0^%^2C1689195658062^%^22; msToken=OqErXe8WFLs1OjcJCNX2pNWTvnMSJIKjUXQRa74H4uQo8Ea5hpI8L3zlpK2eq5GUyrHcnTbQ-Kw4UgEntfb9dXu4Ijfowp_LSMxN6AISaoDf-OZCFv2IFS1P4UY2DHYG; ttcid=b8ea42abb1954fd2a913086620d2447f25; download_guide=^%^223^%^2F20230713^%^2F0^%^22; home_can_add_dy_2_desktop=^%^220^%^22; strategyABtestKey=^%^221689299939.836^%^22; FOLLOW_LIVE_POINT_INFO=^%^22MS4wLjABAAAAf6aekfyBsc4u8jMkeYbgnkFa0ksIWKWpGOywuyHXyo4^%^2F1689350400000^%^2F0^%^2F1689299940112^%^2F0^%^22; VIDEO_FILTER_MEMO_SELECT=^%^7B^%^22expireTime^%^22^%^3A1689904741009^%^2C^%^22type^%^22^%^3Anull^%^7D; device_web_cpu_core=8; device_web_memory_size=-1; webcast_local_quality=origin; csrf_session_id=ce1e9bc7ba69feec32889636027ce79a; passport_fe_beating_status=false; webcast_leading_last_show_time=1689300023141; webcast_leading_total_show_times=1; tt_scid=PgQO8z6aK2zeofuxFGselkNp2kSbPFCuPmOMwU9ih.SXbBp8iA7l2EiqrurdBuMWf204; msToken=T5-gdGi61ytJtas2VgUQAogURSJT2pQDWT5E_TPGT9paO9OtCuHOGAl72YAxHhrkKJdNhx6O1JgGn0uzdkfHw_a_MWJS-OJlgroduiLAcJzzSCmib6GfWqIgWT8m2qA3; __ac_nonce=064b0be450072f85a1215; __ac_signature=_02B4Z6wo00f01eL3lWgAAIDA.rQr1mcyUx3ixpHAABwPwM4wuxfDlht-h5js2proCQ84O246NPRhh7I6Pv0tJwHeCCotGZpibWazzH51O7kDcl18lUJy6o8VYLGIG..jFlP-zEpspGjM6AZO34; __ac_referer=https://live.douyin.com/',
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


def get_tiktok_stream_data(url,proxy_addr):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36 Edg/114.0.1823.79'
    }

    if proxy_addr !='':
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


if __name__ == '__main__':
    Cookie='ttwid=1%7CB1qls3GdnZhUov9o2NxOMxxYS2ff6OSvEWbv0ytbES4%7C1680522049%7C280d802d6d478e3e78d0c807f7c487e7ffec0ae4e5fdd6a0fe74c3c6af149511; my_rd=1; passport_csrf_token=3ab34460fa656183fccfb904b16ff742; passport_csrf_token_default=3ab34460fa656183fccfb904b16ff742; d_ticket=9f562383ac0547d0b561904513229d76c9c21; n_mh=hvnJEQ4Q5eiH74-84kTFUyv4VK8xtSrpRZG1AhCeFNI; store-region=cn-fj; store-region-src=uid; LOGIN_STATUS=1; __security_server_data_status=1; FORCE_LOGIN=%7B%22videoConsumedRemainSeconds%22%3A180%7D; pwa2=%223%7C0%7C3%7C0%22; download_guide=%223%2F20230729%2F0%22; volume_info=%7B%22isUserMute%22%3Afalse%2C%22isMute%22%3Afalse%2C%22volume%22%3A0.6%7D; strategyABtestKey=%221690824679.923%22; stream_recommend_feed_params=%22%7B%5C%22cookie_enabled%5C%22%3Atrue%2C%5C%22screen_width%5C%22%3A1536%2C%5C%22screen_height%5C%22%3A864%2C%5C%22browser_online%5C%22%3Atrue%2C%5C%22cpu_core_num%5C%22%3A8%2C%5C%22device_memory%5C%22%3A8%2C%5C%22downlink%5C%22%3A10%2C%5C%22effective_type%5C%22%3A%5C%224g%5C%22%2C%5C%22round_trip_time%5C%22%3A150%7D%22; VIDEO_FILTER_MEMO_SELECT=%7B%22expireTime%22%3A1691443863751%2C%22type%22%3Anull%7D; home_can_add_dy_2_desktop=%221%22; __live_version__=%221.1.1.2169%22; device_web_cpu_core=8; device_web_memory_size=8; xgplayer_user_id=346045893336; csrf_session_id=2e00356b5cd8544d17a0e66484946f28; odin_tt=724eb4dd23bc6ffaed9a1571ac4c757ef597768a70c75fef695b95845b7ffcd8b1524278c2ac31c2587996d058e03414595f0a4e856c53bd0d5e5f56dc6d82e24004dc77773e6b83ced6f80f1bb70627; __ac_nonce=064caded4009deafd8b89; __ac_signature=_02B4Z6wo00f01HLUuwwAAIDBh6tRkVLvBQBy9L-AAHiHf7; ttcid=2e9619ebbb8449eaa3d5a42d8ce88ec835; webcast_leading_last_show_time=1691016922379; webcast_leading_total_show_times=1; webcast_local_quality=sd; live_can_add_dy_2_desktop=%221%22; msToken=1JDHnVPw_9yTvzIrwb7cQj8dCMNOoesXbA_IooV8cezcOdpe4pzusZE7NB7tZn9TBXPr0ylxmv-KMs5rqbNUBHP4P7VBFUu0ZAht_BEylqrLpzgt3y5ne_38hXDOX8o=; msToken=jV_yeN1IQKUd9PlNtpL7k5vthGKcHo0dEh_QPUQhr8G3cuYv-Jbb4NnIxGDmhVOkZOCSihNpA2kvYtHiTW25XNNX_yrsv5FN8O6zm3qmCIXcEe0LywLn7oBO2gITEeg=; tt_scid=mYfqpfbDjqXrIGJuQ7q-DlQJfUSG51qG.KUdzztuGP83OjuVLXnQHjsz-BRHRJu4e986'
    url="https://live.douyin.com/803023607352"  # douyin live
    url="https://live.douyin.com/745964462470"  # douyin live
    # url = "https://www.tiktok.com/@pearlgaga88/live"  # tiktok live
    print(get_douyin_stream_data(url,Cookie))
    # print(get_tiktok_stream_data(url,''))