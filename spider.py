# -*- encoding: utf-8 -*-

"""
Author: Hmily
GitHub:https://github.com/ihmily
Date: 2023-07-15 23:15:00
Update: 2024-01-29 18:57:12
Copyright (c) 2023 by Hmily, All Rights Reserved.
Function: Get live stream data.
"""

import hashlib
import time
import urllib.parse
from typing import Union, Dict, Any
import requests
import re
import json
import execjs
import urllib.request
from utils import trace_error_decorator

no_proxy_handler = urllib.request.ProxyHandler({})
opener = urllib.request.build_opener(no_proxy_handler)


@trace_error_decorator
def get_douyin_stream_data(url: str, cookies: Union[str, None] = None) -> Dict[str, Any]:
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/115.0',
        'Accept-Language': 'zh-CN,zh;q=0.8,zh-TW;q=0.7,zh-HK;q=0.5,en-US;q=0.3,en;q=0.2',
        'Referer': 'https://live.douyin.com/',
        'Cookie': 'ttwid=1%7CB1qls3GdnZhUov9o2NxOMxxYS2ff6OSvEWbv0ytbES4%7C1680522049%7C280d802d6d478e3e78d0c807f7c487e7ffec0ae4e5fdd6a0fe74c3c6af149511; my_rd=1; passport_csrf_token=3ab34460fa656183fccfb904b16ff742; passport_csrf_token_default=3ab34460fa656183fccfb904b16ff742; d_ticket=9f562383ac0547d0b561904513229d76c9c21; n_mh=hvnJEQ4Q5eiH74-84kTFUyv4VK8xtSrpRZG1AhCeFNI; store-region=cn-fj; store-region-src=uid; LOGIN_STATUS=1; __security_server_data_status=1; FORCE_LOGIN=%7B%22videoConsumedRemainSeconds%22%3A180%7D; pwa2=%223%7C0%7C3%7C0%22; download_guide=%223%2F20230729%2F0%22; volume_info=%7B%22isUserMute%22%3Afalse%2C%22isMute%22%3Afalse%2C%22volume%22%3A0.6%7D; strategyABtestKey=%221690824679.923%22; stream_recommend_feed_params=%22%7B%5C%22cookie_enabled%5C%22%3Atrue%2C%5C%22screen_width%5C%22%3A1536%2C%5C%22screen_height%5C%22%3A864%2C%5C%22browser_online%5C%22%3Atrue%2C%5C%22cpu_core_num%5C%22%3A8%2C%5C%22device_memory%5C%22%3A8%2C%5C%22downlink%5C%22%3A10%2C%5C%22effective_type%5C%22%3A%5C%224g%5C%22%2C%5C%22round_trip_time%5C%22%3A150%7D%22; VIDEO_FILTER_MEMO_SELECT=%7B%22expireTime%22%3A1691443863751%2C%22type%22%3Anull%7D; home_can_add_dy_2_desktop=%221%22; __live_version__=%221.1.1.2169%22; device_web_cpu_core=8; device_web_memory_size=8; xgplayer_user_id=346045893336; csrf_session_id=2e00356b5cd8544d17a0e66484946f28; odin_tt=724eb4dd23bc6ffaed9a1571ac4c757ef597768a70c75fef695b95845b7ffcd8b1524278c2ac31c2587996d058e03414595f0a4e856c53bd0d5e5f56dc6d82e24004dc77773e6b83ced6f80f1bb70627; __ac_nonce=064caded4009deafd8b89; __ac_signature=_02B4Z6wo00f01HLUuwwAAIDBh6tRkVLvBQBy9L-AAHiHf7; ttcid=2e9619ebbb8449eaa3d5a42d8ce88ec835; webcast_leading_last_show_time=1691016922379; webcast_leading_total_show_times=1; webcast_local_quality=sd; live_can_add_dy_2_desktop=%221%22; msToken=1JDHnVPw_9yTvzIrwb7cQj8dCMNOoesXbA_IooV8cezcOdpe4pzusZE7NB7tZn9TBXPr0ylxmv-KMs5rqbNUBHP4P7VBFUu0ZAht_BEylqrLpzgt3y5ne_38hXDOX8o=; msToken=jV_yeN1IQKUd9PlNtpL7k5vthGKcHo0dEh_QPUQhr8G3cuYv-Jbb4NnIxGDmhVOkZOCSihNpA2kvYtHiTW25XNNX_yrsv5FN8O6zm3qmCIXcEe0LywLn7oBO2gITEeg=; tt_scid=mYfqpfbDjqXrIGJuQ7q-DlQJfUSG51qG.KUdzztuGP83OjuVLXnQHjsz-BRHRJu4e986'
    }
    if cookies:
        headers['Cookie'] = cookies

    try:
        # 使用更底层的urllib内置库，防止开启代理时导致的抖音录制SSL 443报错
        req = urllib.request.Request(url, headers=headers)
        response = opener.open(req, timeout=15)
        html_str = response.read().decode('utf-8')
        match_json_str = re.search(r'(\{\\"state\\":.*?)]\\n"]\)', html_str)
        if not match_json_str:
            match_json_str = re.search(r'(\{\\"common\\":.*?)]\\n"]\)</script><div hidden', html_str)
        json_str = match_json_str.group(1)
        cleaned_string = json_str.replace('\\', '').replace(r'u0026', r'&')
        room_store = re.search('"roomStore":(.*?),"linkmicStore"', cleaned_string, re.S).group(1)
        anchor_name = re.search('"nickname":"(.*?)","avatar_thumb', room_store, re.S).group(1)
        room_store = room_store.split(',"has_commerce_goods"')[0] + '}}}'
        json_data = json.loads(room_store)['roomInfo']['room']
        json_data['anchor_name'] = anchor_name
        return json_data

    except Exception as e:
        print(f'失败地址：{url} 准备切换解析方法{e}')
        web_rid = re.match('https://live.douyin.com/(\d+)', url).group(1)
        headers['Cookie'] = 'sessionid=73d300f837f261eaa8ffc69d50162700'
        url2 = f'https://live.douyin.com/webcast/room/web/enter/?aid=6383&app_name=douyin_web&live_id=1&web_rid={web_rid}'
        req = urllib.request.Request(url2, headers=headers)
        response = opener.open(req, timeout=15)
        json_str = response.read().decode('utf-8')
        json_data = json.loads(json_str)['data']
        room_data = json_data['data'][0]
        room_data['anchor_name'] = json_data['user']['nickname']
        return room_data


@trace_error_decorator
def get_tiktok_stream_data(url: str, proxy_addr: Union[str, None] = None, cookies: Union[str, None] = None) -> Dict[
                        str, Any]:
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36 Edg/114.0.1823.79',
        'Cookie': 'ttwid=1%7CM-rF193sJugKuNz2RGNt-rh6pAAR9IMceUSzlDnPCNI%7C1683274418%7Cf726d4947f2fc37fecc7aeb0cdaee52892244d04efde6f8a8edd2bb168263269; tiktok_webapp_theme=light; tt_chain_token=VWkygAWDlm1cFg/k8whmOg==; passport_csrf_token=6e422c5a7991f8cec7033a8082921510; passport_csrf_token_default=6e422c5a7991f8cec7033a8082921510; d_ticket=f8c267d4af4523c97be1ccb355e9991e2ae06; odin_tt=320b5f386cdc23f347be018e588873db7f7aea4ea5d1813681c3fbc018ea025dde957b94f74146dbc0e3612426b865ccb95ec8abe4ee36cca65f15dbffec0deff7b0e69e8ea536d46e0f82a4fc37d211; cmpl_token=AgQQAPNSF-RO0rT04baWtZ0T_jUjl4fVP4PZYM2QPw; uid_tt=319b558dbba684bb1557206c92089cd113a875526a89aee30595925d804b81c7; uid_tt_ss=319b558dbba684bb1557206c92089cd113a875526a89aee30595925d804b81c7; sid_tt=ad5e736f4bedb2f6d42ccd849e706b1d; sessionid=ad5e736f4bedb2f6d42ccd849e706b1d; sessionid_ss=ad5e736f4bedb2f6d42ccd849e706b1d; store-idc=useast5; store-country-code=us; store-country-code-src=uid; tt-target-idc=useast5; tt-target-idc-sign=qXNk0bb1pDQ0FbCNF120Pl9WWMLZg9Edv5PkfyCbS4lIk5ieW5tfLP7XWROnN0mEaSlc5hg6Oji1pF-yz_3ZXnUiNMrA9wNMPvI6D9IFKKVmq555aQzwPIGHv0aQC5dNRgKo5Z5LBkgxUMWEojTKclq2_L8lBciw0IGdhFm_XyVJtbqbBKKgybGDLzK8ZyxF4Jl_cYRXaDlshZjc38JdS6wruDueRSHe7YvNbjxCnApEFUv-OwJANSPU_4rvcqpVhq3JI2VCCfw-cs_4MFIPCDOKisk5EhAo2JlHh3VF7_CLuv80FXg_7ZqQ2pJeMOog294rqxwbbQhl3ATvjQV_JsWyUsMd9zwqecpylrPvtySI2u1qfoggx1owLrrUynee1R48QlanLQnTNW_z1WpmZBgVJqgEGLwFoVOmRzJuFFNj8vIqdjM2nDSdWqX8_wX3wplohkzkPSFPfZgjzGnQX28krhgTytLt7BXYty5dpfGtsdb11WOFHM6MZ9R9uLVB; sid_guard=ad5e736f4bedb2f6d42ccd849e706b1d%7C1690990657%7C15525213%7CMon%2C+29-Jan-2024+08%3A11%3A10+GMT; sid_ucp_v1=1.0.0-KGM3YzgwYjZhODgyYWI1NjIwNTA0NjBmOWUxMGRhMjIzYTI2YjMxNDUKGAiqiJ30keKD5WQQwfCppgYYsws4AkDsBxAEGgd1c2Vhc3Q1IiBhZDVlNzM2ZjRiZWRiMmY2ZDQyY2NkODQ5ZTcwNmIxZA; ssid_ucp_v1=1.0.0-KGM3YzgwYjZhODgyYWI1NjIwNTA0NjBmOWUxMGRhMjIzYTI2YjMxNDUKGAiqiJ30keKD5WQQwfCppgYYsws4AkDsBxAEGgd1c2Vhc3Q1IiBhZDVlNzM2ZjRiZWRiMmY2ZDQyY2NkODQ5ZTcwNmIxZA; tt_csrf_token=dD0EIH8q-pe3qDQsCyyD1jLN6KizJDRjOEyk; __tea_cache_tokens_1988={%22_type_%22:%22default%22%2C%22user_unique_id%22:%227229608516049831425%22%2C%22timestamp%22:1683274422659}; ttwid=1%7CM-rF193sJugKuNz2RGNt-rh6pAAR9IMceUSzlDnPCNI%7C1694002151%7Cd89b77afc809b1a610661a9d1c2784d80ebef9efdd166f06de0d28e27f7e4efe; msToken=KfJAVZ7r9D_QVeQlYAUZzDFbc1Yx-nZz6GF33eOxgd8KlqvTg1lF9bMXW7gFV-qW4MCgUwnBIhbiwU9kdaSpgHJCk-PABsHCtTO5J3qC4oCTsrXQ1_E0XtbqiE4OVLZ_jdF1EYWgKNPT2SnwGkQ=; msToken=KfJAVZ7r9D_QVeQlYAUZzDFbc1Yx-nZz6GF33eOxgd8KlqvTg1lF9bMXW7gFV-qW4MCgUwnBIhbiwU9kdaSpgHJCk-PABsHCtTO5J3qC4oCTsrXQ1_E0XtbqiE4OVLZ_jdF1EYWgKNPT2SnwGkQ='
    }
    if cookies:
        headers['Cookie'] = cookies

    if proxy_addr:

        proxies = {
            'http': proxy_addr,
            'https': proxy_addr
        }

        html = requests.get(url, headers=headers, proxies=proxies, timeout=15)
        html_str = html.text

    else:

        req = urllib.request.Request(url, headers=headers)
        response = urllib.request.urlopen(req, timeout=15)
        html_str = response.read().decode('utf-8')
    json_str = re.findall(
        '<script id="SIGI_STATE" type="application/json">(.*?)</script><script id="SIGI_RETRY" type="application/json">',
        html_str)[0]
    json_data = json.loads(json_str)
    return json_data


@trace_error_decorator
def get_kuaishou_stream_data(url: str, cookies: Union[str, None] = None) -> Dict[str, Any]:
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/115.0',
        'Accept-Language': 'zh-CN,zh;q=0.8,zh-TW;q=0.7,zh-HK;q=0.5,en-US;q=0.3,en;q=0.2',
    }
    if cookies:
        headers['Cookie'] = cookies
    try:
        req = urllib.request.Request(url, headers=headers)
        response = urllib.request.urlopen(req, timeout=15)
        html_str = response.read().decode('utf-8')
    except Exception as e:
        print(f"Failed to fetch data from {url}.{e}")
        return {"type": 1, "is_live": False}

    try:
        json_str = re.search('<script>window.__INITIAL_STATE__=(.*?);\(function\(\)\{var s;', html_str).group(1)
        play_list = re.findall('(\{"liveStream".*?),"gameInfo', json_str)[0] + "}"
        play_list = json.loads(play_list)
    except (AttributeError, IndexError, json.JSONDecodeError) as e:
        print(f"Failed to parse JSON data from {url}. Error: {e}")
        return {"type": 1, "is_live": False}

    result = {"type": 2, "is_live": False}

    if 'errorType' in play_list or 'liveStream' not in play_list:
        error_msg = play_list.get('errorType', {}).get('title', '') + play_list.get('errorType', {}).get('content', '')
        print(f'失败地址：{url} 错误信息: {error_msg}')
        print('提示信息：请打开快手直播页面正常随机进入一个直播间，即可解除频繁访问限制')
        return result

    if not play_list.get('liveStream'):
        print("IP banned. Please change device or network.")
        return result

    anchor_name = play_list['author'].get('name', '')
    result.update({"anchor_name": anchor_name})

    if play_list['liveStream'].get("playUrls"):
        play_url_list = play_list['liveStream']['playUrls'][0]['adaptationSet']['representation']
        result.update({"flv_url_list": play_url_list, "is_live": True})

    return result


@trace_error_decorator
def get_kuaishou_stream_data2(url: str, cookies: Union[str, None] = None) -> Dict[str, Any]:
    headers = {
        'User-Agent': 'Mozilla/5.0 (Linux; Android 11; SAMSUNG SM-G973U) AppleWebKit/537.36 (KHTML, like Gecko) SamsungBrowser/14.2 Chrome/87.0.4280.141 Mobile Safari/537.36',
        'Accept-Language': 'zh-CN,zh;q=0.8,zh-TW;q=0.7,zh-HK;q=0.5,en-US;q=0.3,en;q=0.2',
        'Referer': "https://www.kuaishou.com/short-video/3x224rwabjmuc9y?fid=1712760877&cc=share_copylink&followRefer=151&shareMethod=TOKEN&docId=9&kpn=KUAISHOU&subBiz=BROWSE_SLIDE_PHOTO&photoId=3x224rwabjmuc9y&shareId=17144298796566&shareToken=X-6FTMeYTsY97qYL&shareResourceType=PHOTO_OTHER&userId=3xtnuitaz2982eg&shareType=1&et=1_i/2000048330179867715_h3052&shareMode=APP&originShareId=17144298796566&appType=21&shareObjectId=5230086626478274600&shareUrlOpened=0&timestamp=1663833792288&utm_source=app_share&utm_medium=app_share&utm_campaign=app_share&location=app_share",
        'content-type': 'application/json',
        'Cookie': 'did=web_e988652e11b545469633396abe85a89f; didv=1796004001000',
    }
    if cookies:
        headers['Cookie'] = cookies
    try:
        eid = url.split('/u/')[1].strip()
        data = {"source": 5, "eid": eid, "shareMethod": "card", "clientType": "WEB_OUTSIDE_SHARE_H5"}
        data_encoded = json.dumps(data).encode('utf-8')
        app_api = 'https://livev.m.chenzhongtech.com/rest/k/live/byUser?kpn=GAME_ZONE&captchaToken='
        req = urllib.request.Request(app_api, headers=headers, data=data_encoded)
        response = urllib.request.urlopen(req)
        json_str = response.read().decode('utf-8')
        json_data = json.loads(json_str)

        live_stream = json_data['liveStream']
        anchor_name = live_stream['user']['user_name']
        result = {
            "type": 2,
            "anchor_name": anchor_name,
            "is_live": False,
        }
        live_status = live_stream['living']
        if live_status:
            result['is_live'] = True
            backup_m3u8_url = live_stream['hlsPlayUrl']
            backup_flv_url = live_stream['playUrls'][0]['url']
            if 'multiResolutionHlsPlayUrls' in live_stream:
                m3u8_url_list = live_stream['multiResolutionHlsPlayUrls'][0]['urls']
                result['m3u8_url_list'] = m3u8_url_list
            if 'multiResolutionPlayUrls' in live_stream:
                flv_url_list = live_stream['multiResolutionPlayUrls'][0]['urls']
                result['flv_url_list'] = flv_url_list
            result['backup'] = {'m3u8_url': backup_m3u8_url, 'flv_url': backup_flv_url}
        if result['anchor_name']:
            return result
    except Exception:
        print(f'失败地址：{url} 准备切换为备用方案重新解析 ')
    return get_kuaishou_stream_data(url, cookies=cookies)


@trace_error_decorator
def get_huya_stream_data(url: str, cookies: Union[str, None] = None) -> Dict[str, Any]:
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/115.0',
        'Accept-Language': 'zh-CN,zh;q=0.8,zh-TW;q=0.7,zh-HK;q=0.5,en-US;q=0.3,en;q=0.2',
        'Cookie': 'huya_ua=webh5&0.0.1&websocket; SoundValue=0.50; alphaValue=0.80; isInLiveRoom=true; game_did=-GcWYDglXNu2ZzqqTr4X-L4PSTclU2iheFm; Hm_lvt_51700b6c722f5bb4cf39906a596ea41f=1691210433,1691477318; udb_deviceid=w_610934293339279360; __yamid_tt1=0.5879880896254449; __yamid_new=C9EFFE0C63A00001A7A94510B5E718A6; guid=0a70d5e7b1d2cd644301d168d268de7b; guid=0a70d5e7b1d2cd644301d168d268de7b; udb_cred=CnDN6T9nhzPKEPgJieRfkuh2PcVTTfwhGVayc7q49srtD2angI9ShGfVHENqGqcGVvyssMbG1spibOt1mjsa57ZsNwEJ1sYVRedE_rsSN30WBp783NmwViE2I-Zh1yPV1MD6NRQURwYmyAUA5YOaY8iT; udb_passdata=3'
    }
    if cookies:
        headers['Cookie'] = cookies

    req = urllib.request.Request(url, headers=headers)
    response = opener.open(req, timeout=15)
    html_str = response.read().decode('utf-8')
    json_str = re.findall('stream: (\{"data".*?),"iWebDefaultBitRate"', html_str)[0]
    json_data = json.loads(json_str + '}')
    return json_data


def md5(data):
    return hashlib.md5(data.encode('utf-8')).hexdigest()


def get_token_js(rid: str, did: str) -> Union[list, Dict[str, Any]]:
    """
    通过PC网页端的接口获取完整直播源。
    :param did:
    :param rid:
    :param cdn: 主线路ws-h5、备用线路tct-h5
    :param rate: 1流畅；2高清；3超清；4蓝光4M；0蓝光8M或10M
    """
    url = f'https://www.douyu.com/{rid}'
    response = opener.open(url, timeout=15)
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
    params = js.call('sign', rid, did, t10)
    params_list = re.findall('=(.*?)(?=&|$)', params)
    return params_list


@trace_error_decorator
def get_douyu_info_data(url: str) -> Dict[str, Any]:
    match_rid = re.search('rid=(.*?)&', url)
    if match_rid:
        rid = match_rid.group(1)
    else:
        rid = re.search('douyu.com/(.*?)(?=\?|$)', url).group(1)
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/115.0',
    }
    url2 = f'https://m.douyu.com/{rid}'
    req = urllib.request.Request(url2, headers=headers)
    response = opener.open(req, timeout=15)

    html_str = response.read().decode('utf-8')
    json_str = re.search('<script id="vike_pageContext" type="application/json">(.*?)</script>',
                         html_str).group(1)
    json_data = json.loads(json_str)
    return json_data


@trace_error_decorator
def get_douyu_stream_data(rid: str, rate: str = '-1', cookies: Union[str, None] = None) -> Dict[str, Any]:
    did = '10000000000000000000000000003306'
    params_list = get_token_js(rid, did)

    headers = {
        'User-Agent': 'Mozilla/5.0 (Linux; Android 11; SAMSUNG SM-G973U) AppleWebKit/537.36 (KHTML, like Gecko) SamsungBrowser/14.2 Chrome/87.0.4280.141 Mobile Safari/537.36',
        'Referer': 'https://m.douyu.com/3125893?rid=3125893&dyshid=0-96003918aa5365bc6dcb4933000316p1&dyshci=181',
        'Cookie': 'dy_did=413b835d2ae00270f0c69f6400031601; acf_did=413b835d2ae00270f0c69f6400031601; Hm_lvt_e99aee90ec1b2106afe7ec3b199020a7=1692068308,1694003758; m_did=96003918aa5365bc6dcb4933000316p1; dy_teen_mode=%7B%22uid%22%3A%22472647365%22%2C%22status%22%3A0%2C%22birthday%22%3A%22%22%2C%22password%22%3A%22%22%7D; PHPSESSID=td59qi2fu2gepngb8mlehbeme3; acf_auth=94fc9s%2FeNj%2BKlpU%2Br8tZC3Jo9sZ0wz9ClcHQ1akL2Nhb6ZyCmfjVWSlR3LFFPuePWHRAMo0dt9vPSCoezkFPOeNy4mYcdVOM1a8CbW0ZAee4ipyNB%2Bflr58; dy_auth=bec5yzM8bUFYe%2FnVAjmUAljyrsX%2FcwRW%2FyMHaoArYb5qi8FS9tWR%2B96iCzSnmAryLOjB3Qbeu%2BBD42clnI7CR9vNAo9mva5HyyL41HGsbksx1tEYFOEwxSI; wan_auth37wan=5fd69ed5b27fGM%2FGoswWwDo%2BL%2FRMtnEa4Ix9a%2FsH26qF0sR4iddKMqfnPIhgfHZUqkAk%2FA1d8TX%2B6F7SNp7l6buIxAVf3t9YxmSso8bvHY0%2Fa6RUiv8; acf_uid=472647365; acf_username=472647365; acf_nickname=%E7%94%A8%E6%88%B776576662; acf_own_room=0; acf_groupid=1; acf_phonestatus=1; acf_avatar=https%3A%2F%2Fapic.douyucdn.cn%2Fupload%2Favatar%2Fdefault%2F24_; acf_ct=0; acf_ltkid=25305099; acf_biz=1; acf_stk=90754f8ed18f0c24; Hm_lpvt_e99aee90ec1b2106afe7ec3b199020a7=1694003778'
    }
    if cookies:
        headers['Cookie'] = cookies

    data = {
        'v': params_list[0],
        'did': params_list[1],
        'tt': params_list[2],
        'sign': params_list[3],  # 10分钟有效期
        'ver': '22011191',
        'rid': rid,
        'rate': rate,  # 0蓝光、3超清、2高清、-1默认
    }
    # 将数据转换为 URL 编码的字节格式
    data = urllib.parse.urlencode(data).encode('utf-8')
    app_api = 'https://m.douyu.com/hgapi/livenc/room/getStreamUrl'
    req = urllib.request.Request(app_api, data=data, headers=headers)
    response = opener.open(req, timeout=15)
    json_str = response.read().decode('utf-8')
    json_data = json.loads(json_str)
    return json_data


@trace_error_decorator
def get_yy_stream_data(url: str, cookies: Union[str, None] = None) -> Dict[str, Any]:
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/115.0',
        'Accept-Language': 'zh-CN,zh;q=0.8,zh-TW;q=0.7,zh-HK;q=0.5,en-US;q=0.3,en;q=0.2',
        'Referer': 'https://www.yy.com/',
        'Cookie': 'hd_newui=0.2103068903976506; hdjs_session_id=0.4929014850884579; hdjs_session_time=1694004002636; hiido_ui=0.923076230899782'
    }
    if cookies:
        headers['Cookie'] = cookies

    req = urllib.request.Request(url, headers=headers)
    response = opener.open(req, timeout=15)
    html_str = response.read().decode('utf-8')
    anchor_name = re.search('nick: "(.*?)",\n\s+logo', html_str).group(1)
    cid = re.search('sid : "(.*?)",\n\s+ssid', html_str, re.S).group(1)

    data = '{"head":{"seq":1701869217590,"appidstr":"0","bidstr":"121","cidstr":"' + cid + '","sidstr":"' + cid + '","uid64":0,"client_type":108,"client_ver":"5.17.0","stream_sys_ver":1,"app":"yylive_web","playersdk_ver":"5.17.0","thundersdk_ver":"0","streamsdk_ver":"5.17.0"},"client_attribute":{"client":"web","model":"web0","cpu":"","graphics_card":"","os":"chrome","osversion":"0","vsdk_version":"","app_identify":"","app_version":"","business":"","width":"1920","height":"1080","scale":"","client_type":8,"h265":0},"avp_parameter":{"version":1,"client_type":8,"service_type":0,"imsi":0,"send_time":1701869217,"line_seq":-1,"gear":4,"ssl":1,"stream_format":0}}'
    data_bytes = data.encode('utf-8')
    url2 = f'https://stream-manager.yy.com/v3/channel/streams?uid=0&cid={cid}&sid={cid}&appid=0&sequence=1701869217590&encode=json'
    req = urllib.request.Request(url2, data=data_bytes, headers=headers)
    response = opener.open(req, timeout=15)
    json_str = response.read().decode('utf-8')
    json_data = json.loads(json_str)
    json_data['anchor_name'] = anchor_name
    return json_data


@trace_error_decorator
def get_bilibili_stream_data(url: str, cookies: Union[str, None] = None) -> Dict[str, Any]:
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/115.0',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
        'Referer': 'https://live.bilibili.com/?spm_id_from=333.1296.0.0',
        'Cookie': "buvid3=13436C33-39B8-C4D5-C5C6-3F31B85716A131745infoc; b_nut=1680525931; CURRENT_FNVAL=4048; _uuid=B10E775DC-168D-CA47-E1B8-CEF7C52FA84234052infoc; buvid_fp=a2f7f8f3977824b52ec75cf23e5b6754; CURRENT_PID=70fa2680-d21d-11ed-ba58-9979ebfa5794; rpdid=|(JYYJ|uuYm)0J'uY)|lklmRJ; buvid4=C29E3582-5740-8FF3-AFD1-98B345DDAF5393968-022082019-Vk7oLekZ8O%2FtgWtFEu98GQ%3D%3D; DedeUserID=623475372; DedeUserID__ckMd5=db79fcea5a8315aa; i-wanna-go-back=-1; b_ut=5; FEED_LIVE_VERSION=V8; header_theme_version=CLOSE; home_feed_column=5; browser_resolution=1483-722; SESSDATA=122468fe%2C1707184844%2C2c98c%2A827Ts7uT3NZIxeOzop88h3EdmSUIG9NhWF9VkiidKIkTgJkTbh5WcONjTKuaOwfeR9t6uUZAAASAA; bili_jct=b8479df41520c402eb0a1a7f37a26de8; bp_video_offset_623475372=827303476826472609; PVID=1; LIVE_BUVID=AUTO5816940041629512; GIFT_BLOCK_COOKIE=GIFT_BLOCK_COOKIE"
    }
    if cookies:
        headers['Cookie'] = cookies
    try:
        req = urllib.request.Request(url, headers=headers)
        response = opener.open(req, timeout=15)
        html_str = response.read().decode('utf-8')
        json_str = re.search('<script>window.__NEPTUNE_IS_MY_WAIFU__=(.*?)</script><script>', html_str, re.S).group(1)
        json_data = json.loads(json_str)
        return json_data
    except Exception:
        return {"anchor_name": '', "is_live": False}


@trace_error_decorator
def get_xhs_stream_url(url: str, cookies: Union[str, None] = None) -> Dict[str, Any]:
    headers = {
        'User-Agent': 'Mozilla/5.0 (Linux; Android 11; SAMSUNG SM-G973U) AppleWebKit/537.36 (KHTML, like Gecko) SamsungBrowser/14.2 Chrome/87.0.4280.141 Mobile Safari/537.36',
        'Accept': 'application/json, text/plain, */*',
        'Accept-Language': 'zh-CN,zh;q=0.8,zh-TW;q=0.7,zh-HK;q=0.5,en-US;q=0.3,en;q=0.2',
        'Referer': 'https://www.xiaohongshu.com/hina/livestream/568979931846654360',
    }
    if cookies:
        headers['Cookie'] = cookies

    room_id = url.split('?')[0].rsplit('/', maxsplit=1)[1]
    appuid = re.search('appuid=(.*?)&', url).group(1)
    app_api = f'https://www.xiaohongshu.com/api/sns/red/live/app/v1/ecology/outside/share_info?room_id={room_id}'
    req = urllib.request.Request(app_api, headers=headers)
    response = opener.open(req, timeout=15)
    json_str = response.read().decode('utf-8')
    json_data = json.loads(json_str)
    anchor_name = json_data['data']['host_info']['nickname']
    live_status = json_data['data']['room']['status']
    result = {
        "anchor_name": anchor_name,
        "is_live": False,
    }

    # 这个判断不准确，无论是否在直播都为0
    if live_status == 0:
        flv_url = f'http://live-play.xhscdn.com/live/{room_id}.flv?uid={appuid}'
        result['flv_url'] = flv_url
        result['is_live'] = True
        result['record_url'] = flv_url
    return result


@trace_error_decorator
def get_bigo_stream_url(url: str, cookies: Union[str, None] = None) -> Dict[str, Any]:
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/119.0',
        'Accept-Language': 'zh-CN,zh;q=0.8,zh-TW;q=0.7,zh-HK;q=0.5,en-US;q=0.3,en;q=0.2',
        'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
        'Referer': 'https://www.bigo.tv/',
    }
    if cookies:
        headers['Cookie'] = cookies

    room_id = re.search('www.bigo.tv/cn/(\w+)', url).group(1)
    data = {'siteId': room_id}  # roomId
    url2 = 'https://ta.bigo.tv/official_website/studio/getInternalStudioInfo'
    data = urllib.parse.urlencode(data).encode('utf-8')
    req = urllib.request.Request(url2, data=data, headers=headers)
    response = opener.open(req, timeout=15)
    json_str = response.read().decode('utf-8')
    json_data = json.loads(json_str)
    anchor_name = json_data['data']['nick_name']
    live_status = json_data['data']['alive']
    result = {
        "anchor_name": anchor_name,
        "is_live": False,
    }

    if live_status == 1:
        m3u8_url = json_data['data']['hls_src']
        result['m3u8_url'] = m3u8_url
        result['is_live'] = True
        result['record_url'] = m3u8_url
    elif result['anchor_name'] == '':
        req = urllib.request.Request(url, headers=headers)
        response = opener.open(req, timeout=15)
        html_str = response.read().decode('utf-8')
        result['anchor_name'] = re.search('<title>(.*?)</title>', html_str, re.S).group(1)

    return result


@trace_error_decorator
def get_blued_stream_url(url: str, cookies: Union[str, None] = None) -> Dict[str, Any]:
    headers = {
        'User-Agent': 'Mozilla/5.0 (Linux; Android 11; SAMSUNG SM-G973U) AppleWebKit/537.36 (KHTML, like Gecko) SamsungBrowser/14.2 Chrome/87.0.4280.141 Mobile Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
        'Accept-Language': 'zh-CN,zh;q=0.8,zh-TW;q=0.7,zh-HK;q=0.5,en-US;q=0.3,en;q=0.2',
    }
    if cookies:
        headers['Cookie'] = cookies

    req = urllib.request.Request(url, headers=headers)
    response = opener.open(req, timeout=15)
    html_str = response.read().decode('utf-8')
    json_str = re.search('decodeURIComponent\(\"(.*?)\"\)\),window\.Promise', html_str, re.S).group(1)
    json_str = urllib.parse.unquote(json_str)
    json_data = json.loads(json_str)
    anchor_name = json_data['userInfo']['name']
    live_status = json_data['userInfo']['onLive']
    result = {
        "anchor_name": anchor_name,
        "is_live": False,
    }

    if live_status:
        m3u8_url = "http:" + json_data['liveInfo']['liveUrl']
        result['m3u8_url'] = m3u8_url
        result['is_live'] = True
        result['record_url'] = m3u8_url
    return result


def get_afreecatv_cdn_url(broad_no: str, proxy_addr: Union[str, None] = None, cookies: Union[str, None] = None) -> Dict[
                        str, Any]:
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/119.0',
        'Accept-Language': 'zh-CN,zh;q=0.8,zh-TW;q=0.7,zh-HK;q=0.5,en-US;q=0.3,en;q=0.2',
        'Referer': 'https://play.afreecatv.com/oul282/249469582',
        'Content-Type': 'application/x-www-form-urlencoded',
    }
    if cookies:
        headers['Cookie'] = cookies

    params = {
        'return_type': 'gcp_cdn',
        'use_cors': 'false',
        'cors_origin_url': 'play.afreecatv.com',
        'broad_key': f'{broad_no}-common-master-hls',
        'time': '8361.086329376785',
    }

    url2 = 'http://livestream-manager.afreecatv.com/broad_stream_assign.html?' + urllib.parse.urlencode(params)

    if proxy_addr:

        proxies = {
            'http': proxy_addr,
            'https': proxy_addr
        }

        response = requests.get(url2, headers=headers, proxies=proxies, timeout=15)
        json_data = response.json()

    else:

        req = urllib.request.Request(url2, headers=headers)
        response = urllib.request.urlopen(req, timeout=15)
        json_str = response.read().decode('utf-8')
        json_data = json.loads(json_str)

    return json_data


@trace_error_decorator
def get_afreecatv_stream_url(url: str, proxy_addr: Union[str, None] = None, cookies: Union[str, None] = None) -> Dict[
                            str, Any]:
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/119.0',
        'Accept-Language': 'zh-CN,zh;q=0.8,zh-TW;q=0.7,zh-HK;q=0.5,en-US;q=0.3,en;q=0.2',
        'Referer': 'https://m.afreecatv.com/',
        'Content-Type': 'application/x-www-form-urlencoded',
    }
    if cookies:
        headers['Cookie'] = cookies

    split_url = url.split('/')
    bj_id = split_url[3] if len(split_url) < 6 else split_url[5]

    data = {
        'bj_id': bj_id,
        'broad_no': '',
        'agent': 'web',
        'confirm_adult': 'true',
        'player_type': 'webm',
        'mode': 'live',
    }

    url2 = 'http://api.m.afreecatv.com/broad/a/watch'
    if proxy_addr:
        proxies = {
            'http': proxy_addr,
            'https': proxy_addr
        }
        response = requests.post(url2, data=data, headers=headers, proxies=proxies, timeout=15)
        json_data = response.json()

    else:

        data = urllib.parse.urlencode(data).encode('utf-8')
        req = urllib.request.Request(url2, data=data, headers=headers)
        response = urllib.request.urlopen(req, timeout=15)
        json_str = response.read().decode('utf-8')
        json_data = json.loads(json_str)

    anchor_name = json_data['data']['user_nick']
    if not anchor_name:
        if json_data['data']['code'] == -3004:
            print("AfreecaTV直播获取失败:", json_data['data']['message'])
        elif json_data['data']['code'] == -3002:
            print("AfreecaTV直播获取失败:", json_data['data']['message'])
    result = {
        "anchor_name": '' if anchor_name is None else anchor_name,
        "is_live": False,
    }

    if json_data['result'] == 1:
        broad_no = json_data['data']['broad_no']
        hls_authentication_key = json_data['data']['hls_authentication_key']
        view_url = get_afreecatv_cdn_url(broad_no, proxy_addr=proxy_addr)['view_url']
        m3u8_url = view_url + '?aid=' + hls_authentication_key
        result['m3u8_url'] = m3u8_url
        result['is_live'] = True
        result['record_url'] = m3u8_url
    return result


# @trace_error_decorator
def get_netease_stream_data(url: str, cookies: Union[str, None] = None) -> Dict[str, Any]:
    headers = {
        'accept': 'application/json, text/plain, */*',
        'accept-language': 'zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6',
        'referer': 'https://cc.163.com/',
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36 Edg/114.0.1823.58',
    }
    if cookies:
        headers['Cookie'] = cookies
    url = url + '/' if url[-1] != '/' else url
    req = urllib.request.Request(url, headers=headers)
    response = opener.open(req, timeout=15)
    html_str = response.read().decode('utf-8')
    json_str = re.search('<script id="__NEXT_DATA__" .* crossorigin="anonymous">(.*?)</script></body>', html_str,
                         re.S).group(1)
    json_data = json.loads(json_str)
    room_data = json_data['props']['pageProps']['roomInfoInitData']
    live_data = room_data['live']
    result = {"is_live": False}
    if 'quickplay' not in live_data:
        result["anchor_name"] = room_data['nickname']
    else:
        result["anchor_name"] = live_data['nickname']
        result["stream_list"] = live_data['quickplay']
        result["is_live"] = True
    return result


@trace_error_decorator
def get_qiandurebo_stream_data(url: str, cookies: Union[str, None] = None) -> Dict[str, Any]:
    headers = {
        'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
        'accept-language': 'zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6',
        'referer': 'https://qiandurebo.com/web/index.php',
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36 Edg/114.0.1823.58',
    }
    if cookies:
        headers['Cookie'] = cookies

    req = urllib.request.Request(url, headers=headers)
    response = opener.open(req, timeout=15)
    html_str = response.read().decode('utf-8')
    data = re.search('var user = (.*?)\r\n\s+user\.play_url', html_str, re.S).group(1)
    anchor_name = re.findall('"zb_nickname": "(.*?)",\r\n', data)

    result = {"anchor": "", "is_live": False}
    if len(anchor_name) > 0:
        result['anchor_name'] = anchor_name[0]
        play_url = re.findall('"play_url": "(.*?)",\r\n', data)

        if len(play_url) > 0:
            result['anchor_name'] = anchor_name[0]
            result['flv_url'] = play_url[0]
            result['is_live'] = True
            result['record_url'] = play_url[0]
    return result


@trace_error_decorator
def get_pandatv_stream_data(url: str, proxy_addr: Union[str, None] = None, cookies: Union[str, None] = None) -> Dict[
                            str, Any]:
    headers = {
        'referer': 'https://www.pandalive.co.kr/',
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36 Edg/114.0.1823.58',
    }
    if cookies:
        headers['Cookie'] = cookies

    user_id = url.split('?')[0].rsplit('/', maxsplit=1)[1]
    url2 = 'https://api.pandalive.co.kr/v1/live/play'
    data = {
        'userId': user_id,
        'info': 'media fanGrade',
    }
    data2 = {
        'action': 'watch',
        'userId': user_id,
        'password': '',
        'shareLinkType': '',
    }

    result = {"anchor_name": "", "is_live": False}
    if proxy_addr:
        proxies = {
            'http': proxy_addr,
            'https': proxy_addr
        }

        response = requests.post('https://api.pandalive.co.kr/v1/member/bj',
                                 headers=headers, proxies=proxies, data=data)
        json_data = response.json()
        anchor_name = json_data['bjInfo']['nick']
        result['anchor_name'] = anchor_name
        live_status = 'media' in json_data
        if live_status:
            response = requests.post(url2, data=data2, headers=headers, proxies=proxies, timeout=15)
            json_data = response.json()

    else:

        data = urllib.parse.urlencode(data).encode('utf-8')
        req = urllib.request.Request('https://api.pandalive.co.kr/v1/member/bj', data=data, headers=headers)
        response = urllib.request.urlopen(req, timeout=20)
        json_str = response.read().decode('utf-8')
        json_data = json.loads(json_str)
        anchor_name = json_data['bjInfo']['nick']
        result['anchor_name'] = anchor_name
        live_status = 'media' in json_data
        if live_status:
            data2 = urllib.parse.urlencode(data2).encode('utf-8')
            req = urllib.request.Request(url2, data=data2, headers=headers)
            response = urllib.request.urlopen(req, timeout=20)
            json_str = response.read().decode('utf-8')
            json_data = json.loads(json_str)

    if live_status:
        play_url = json_data['PlayList']['hls'][0]['url']
        result['m3u8_url'] = play_url
        result['is_live'] = True
        result['record_url'] = play_url
    return result


@trace_error_decorator
def get_maoerfm_stream_url(url: str, cookies: Union[str, None] = None) -> Dict[str, Any]:
    headers = {
        'accept': 'application/json, text/plain, */*',
        'accept-language': 'zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6',
        'referer': 'https://fm.missevan.com/live/868895007',
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) '
                      'Chrome/114.0.0.0 Safari/537.36 Edg/114.0.1823.58',
    }
    if cookies:
        headers['Cookie'] = cookies

    room_id = url.split('?')[0].rsplit('/', maxsplit=1)[1]
    url2 = f'https://fm.missevan.com/api/v2/live/{room_id}'
    req = urllib.request.Request(url2, headers=headers)
    response = opener.open(req, timeout=15)
    json_str = response.read().decode('utf-8')
    json_data = json.loads(json_str)

    anchor_name = json_data['info']['creator']['username']
    live_status = False
    if 'room' in json_data['info']:
        live_status = json_data['info']['room']['status']['broadcasting']
    result = {
        "anchor_name": anchor_name,
        "is_live": live_status,
    }

    if live_status:
        stream_list = json_data['info']['room']['channel']
        m3u8_url = stream_list['hls_pull_url']
        flv_url = stream_list['flv_pull_url']
        result['m3u8_url'] = m3u8_url
        result['flv_url'] = flv_url
        result['is_live'] = True
        result['record_url'] = m3u8_url
    return result


if __name__ == '__main__':
    # 尽量用自己的cookie，以避免默认的不可用导致无法获取数据
    # 以下示例链接不保证时效性，请自行查看链接是否能正常访问

    room_url = "https://live.douyin.com/745964462470"  # 抖音直播
    # room_url = "https://www.tiktok.com/@pearlgaga88/live"  # Tiktok直播
    # room_url = "https://live.kuaishou.com/u/yall1102"  # 快手直播
    # room_url = 'https://www.huya.com/116'  # 虎牙直播
    # room_url = 'https://www.douyu.com/topic/wzDBLS6?rid=4921614&dyshid='  # 斗鱼直播
    # room_url = 'https://www.douyu.com/3637778?dyshid'
    # room_url = 'https://www.yy.com/22490906/22490906'  # YY直播
    # room_url = 'https://live.bilibili.com/21593109'  # b站直播
    # 小红书直播
    # room_url = 'https://www.xiaohongshu.com/hina/livestream/568980065082002402?appuid=5f3f478a00000000010005b3&apptime='
    # room_url = 'https://www.bigo.tv/cn/716418802'  # bigo直播
    # room_url = 'https://app.blued.cn/live?id=Mp6G2R'  # blued直播
    # room_url = 'https://play.afreecatv.com/sw7love'  # afreecatv直播
    # room_url = 'https://m.afreecatv.com/#/player/hl6260'  # afreecatv直播
    # room_url = 'https://cc.163.com/583946984'  # 网易cc直播
    # room_url = 'https://qiandurebo.com/web/video.php?roomnumber=33333'  # 千度热播
    # room_url = 'https://www.pandalive.co.kr/live/play/bara0109'  # pandaTV
    # room_url = 'https://fm.missevan.com/live/868895007'  # 猫耳FM直播

    print(get_douyin_stream_data(room_url))
    # print(get_tiktok_stream_data(url,proxy_addr=''))
    # print(get_kuaishou_stream_data(room_url))
    # print(get_huya_stream_data(room_url))
    # print(get_douyu_info_data(room_url))
    # print(get_douyu_stream_data("4921614",rate='-1'))
    # print(get_yy_stream_data(room_url))
    # print(get_bilibili_stream_data(room_url))
    # print(get_xhs_stream_url(room_url))
    # print(get_bigo_stream_url(room_url))
    # print(get_blued_stream_url(room_url))
    # print(get_afreecatv_stream_url(room_url, proxy_addr=''))
    # print(get_netease_stream_data(room_url))
    # print(get_qiandurebo_stream_data(room_url))
    # print(get_pandatv_stream_data(room_url, proxy_addr=''))
    # print(get_maoerfm_stream_url(room_url))
