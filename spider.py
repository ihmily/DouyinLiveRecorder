# -*- encoding: utf-8 -*-

"""
Author: Hmily
Github:https://github.com/ihmily
Date: 2023-07-15 23:15:00
Update: 2023-09-14 00:27:55
Copyright (c) 2023 by Hmily, All Rights Reserved.
Function: Get live stream data.
"""

import hashlib
import time
import urllib.parse
import requests
import re
import json
# pip install PyExecJS
import execjs
import urllib.request

no_proxy_handler = urllib.request.ProxyHandler({})
opener = urllib.request.build_opener(no_proxy_handler)


# 直接选择从网页HTML中获取直播间数据
def get_douyin_stream_data(url, cookies=''):
    cookie = 'ttwid=1%7CB1qls3GdnZhUov9o2NxOMxxYS2ff6OSvEWbv0ytbES4%7C1680522049%7C280d802d6d478e3e78d0c807f7c487e7ffec0ae4e5fdd6a0fe74c3c6af149511; my_rd=1; passport_csrf_token=3ab34460fa656183fccfb904b16ff742; passport_csrf_token_default=3ab34460fa656183fccfb904b16ff742; d_ticket=9f562383ac0547d0b561904513229d76c9c21; n_mh=hvnJEQ4Q5eiH74-84kTFUyv4VK8xtSrpRZG1AhCeFNI; store-region=cn-fj; store-region-src=uid; LOGIN_STATUS=1; __security_server_data_status=1; FORCE_LOGIN=%7B%22videoConsumedRemainSeconds%22%3A180%7D; pwa2=%223%7C0%7C3%7C0%22; download_guide=%223%2F20230729%2F0%22; volume_info=%7B%22isUserMute%22%3Afalse%2C%22isMute%22%3Afalse%2C%22volume%22%3A0.6%7D; strategyABtestKey=%221690824679.923%22; stream_recommend_feed_params=%22%7B%5C%22cookie_enabled%5C%22%3Atrue%2C%5C%22screen_width%5C%22%3A1536%2C%5C%22screen_height%5C%22%3A864%2C%5C%22browser_online%5C%22%3Atrue%2C%5C%22cpu_core_num%5C%22%3A8%2C%5C%22device_memory%5C%22%3A8%2C%5C%22downlink%5C%22%3A10%2C%5C%22effective_type%5C%22%3A%5C%224g%5C%22%2C%5C%22round_trip_time%5C%22%3A150%7D%22; VIDEO_FILTER_MEMO_SELECT=%7B%22expireTime%22%3A1691443863751%2C%22type%22%3Anull%7D; home_can_add_dy_2_desktop=%221%22; __live_version__=%221.1.1.2169%22; device_web_cpu_core=8; device_web_memory_size=8; xgplayer_user_id=346045893336; csrf_session_id=2e00356b5cd8544d17a0e66484946f28; odin_tt=724eb4dd23bc6ffaed9a1571ac4c757ef597768a70c75fef695b95845b7ffcd8b1524278c2ac31c2587996d058e03414595f0a4e856c53bd0d5e5f56dc6d82e24004dc77773e6b83ced6f80f1bb70627; __ac_nonce=064caded4009deafd8b89; __ac_signature=_02B4Z6wo00f01HLUuwwAAIDBh6tRkVLvBQBy9L-AAHiHf7; ttcid=2e9619ebbb8449eaa3d5a42d8ce88ec835; webcast_leading_last_show_time=1691016922379; webcast_leading_total_show_times=1; webcast_local_quality=sd; live_can_add_dy_2_desktop=%221%22; msToken=1JDHnVPw_9yTvzIrwb7cQj8dCMNOoesXbA_IooV8cezcOdpe4pzusZE7NB7tZn9TBXPr0ylxmv-KMs5rqbNUBHP4P7VBFUu0ZAht_BEylqrLpzgt3y5ne_38hXDOX8o=; msToken=jV_yeN1IQKUd9PlNtpL7k5vthGKcHo0dEh_QPUQhr8G3cuYv-Jbb4NnIxGDmhVOkZOCSihNpA2kvYtHiTW25XNNX_yrsv5FN8O6zm3qmCIXcEe0LywLn7oBO2gITEeg=; tt_scid=mYfqpfbDjqXrIGJuQ7q-DlQJfUSG51qG.KUdzztuGP83OjuVLXnQHjsz-BRHRJu4e986'
    if cookies != '':
        cookie = cookies
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/115.0',
        'Accept-Language': 'zh-CN,zh;q=0.8,zh-TW;q=0.7,zh-HK;q=0.5,en-US;q=0.3,en;q=0.2',
        'Referer': 'https://live.douyin.com/',
        'Cookie': cookie
    }

    # response = requests.get(url, headers=headers)
    # html_str = response.text
    # 使用更底层的urllib内置库，防止开启代理时导致的抖音录制SSL 443报错
    req = urllib.request.Request(url, headers=headers)
    response = opener.open(req, timeout=15)
    html_str = response.read().decode('utf-8')
    match_json_str = re.search(r'(\{\\\"state\\\"\:.*?)\]\\n\"\]\)', html_str)
    if not match_json_str:
        match_json_str = re.search(r'(\{\\\"common\\\"\:.*?)\]\\n\"\]\)\<\/script\>\<div hidden',html_str)
    json_str = match_json_str.group(1)
    cleaned_string = re.sub('bdp_log=(.*?)&bdpsum=', '', json_str.replace('\\', '')).replace(r'u0026', r'&')
    cleaned_string = cleaned_string.replace('"[', '[').replace(']"', ']').replace('"{', '{').replace('}"', '}')
    room_store = re.search('"roomStore":(.*?),"linkmicStore"', cleaned_string, re.S).group(1)
    json_data = json.loads(room_store)
    return json_data


def get_tiktok_stream_data(url, proxy_addr, cookies=''):
    cookie = 'ttwid=1%7CM-rF193sJugKuNz2RGNt-rh6pAAR9IMceUSzlDnPCNI%7C1683274418%7Cf726d4947f2fc37fecc7aeb0cdaee52892244d04efde6f8a8edd2bb168263269; tiktok_webapp_theme=light; tt_chain_token=VWkygAWDlm1cFg/k8whmOg==; passport_csrf_token=6e422c5a7991f8cec7033a8082921510; passport_csrf_token_default=6e422c5a7991f8cec7033a8082921510; d_ticket=f8c267d4af4523c97be1ccb355e9991e2ae06; odin_tt=320b5f386cdc23f347be018e588873db7f7aea4ea5d1813681c3fbc018ea025dde957b94f74146dbc0e3612426b865ccb95ec8abe4ee36cca65f15dbffec0deff7b0e69e8ea536d46e0f82a4fc37d211; cmpl_token=AgQQAPNSF-RO0rT04baWtZ0T_jUjl4fVP4PZYM2QPw; uid_tt=319b558dbba684bb1557206c92089cd113a875526a89aee30595925d804b81c7; uid_tt_ss=319b558dbba684bb1557206c92089cd113a875526a89aee30595925d804b81c7; sid_tt=ad5e736f4bedb2f6d42ccd849e706b1d; sessionid=ad5e736f4bedb2f6d42ccd849e706b1d; sessionid_ss=ad5e736f4bedb2f6d42ccd849e706b1d; store-idc=useast5; store-country-code=us; store-country-code-src=uid; tt-target-idc=useast5; tt-target-idc-sign=qXNk0bb1pDQ0FbCNF120Pl9WWMLZg9Edv5PkfyCbS4lIk5ieW5tfLP7XWROnN0mEaSlc5hg6Oji1pF-yz_3ZXnUiNMrA9wNMPvI6D9IFKKVmq555aQzwPIGHv0aQC5dNRgKo5Z5LBkgxUMWEojTKclq2_L8lBciw0IGdhFm_XyVJtbqbBKKgybGDLzK8ZyxF4Jl_cYRXaDlshZjc38JdS6wruDueRSHe7YvNbjxCnApEFUv-OwJANSPU_4rvcqpVhq3JI2VCCfw-cs_4MFIPCDOKisk5EhAo2JlHh3VF7_CLuv80FXg_7ZqQ2pJeMOog294rqxwbbQhl3ATvjQV_JsWyUsMd9zwqecpylrPvtySI2u1qfoggx1owLrrUynee1R48QlanLQnTNW_z1WpmZBgVJqgEGLwFoVOmRzJuFFNj8vIqdjM2nDSdWqX8_wX3wplohkzkPSFPfZgjzGnQX28krhgTytLt7BXYty5dpfGtsdb11WOFHM6MZ9R9uLVB; sid_guard=ad5e736f4bedb2f6d42ccd849e706b1d%7C1690990657%7C15525213%7CMon%2C+29-Jan-2024+08%3A11%3A10+GMT; sid_ucp_v1=1.0.0-KGM3YzgwYjZhODgyYWI1NjIwNTA0NjBmOWUxMGRhMjIzYTI2YjMxNDUKGAiqiJ30keKD5WQQwfCppgYYsws4AkDsBxAEGgd1c2Vhc3Q1IiBhZDVlNzM2ZjRiZWRiMmY2ZDQyY2NkODQ5ZTcwNmIxZA; ssid_ucp_v1=1.0.0-KGM3YzgwYjZhODgyYWI1NjIwNTA0NjBmOWUxMGRhMjIzYTI2YjMxNDUKGAiqiJ30keKD5WQQwfCppgYYsws4AkDsBxAEGgd1c2Vhc3Q1IiBhZDVlNzM2ZjRiZWRiMmY2ZDQyY2NkODQ5ZTcwNmIxZA; tt_csrf_token=dD0EIH8q-pe3qDQsCyyD1jLN6KizJDRjOEyk; __tea_cache_tokens_1988={%22_type_%22:%22default%22%2C%22user_unique_id%22:%227229608516049831425%22%2C%22timestamp%22:1683274422659}; ttwid=1%7CM-rF193sJugKuNz2RGNt-rh6pAAR9IMceUSzlDnPCNI%7C1694002151%7Cd89b77afc809b1a610661a9d1c2784d80ebef9efdd166f06de0d28e27f7e4efe; msToken=KfJAVZ7r9D_QVeQlYAUZzDFbc1Yx-nZz6GF33eOxgd8KlqvTg1lF9bMXW7gFV-qW4MCgUwnBIhbiwU9kdaSpgHJCk-PABsHCtTO5J3qC4oCTsrXQ1_E0XtbqiE4OVLZ_jdF1EYWgKNPT2SnwGkQ=; msToken=KfJAVZ7r9D_QVeQlYAUZzDFbc1Yx-nZz6GF33eOxgd8KlqvTg1lF9bMXW7gFV-qW4MCgUwnBIhbiwU9kdaSpgHJCk-PABsHCtTO5J3qC4oCTsrXQ1_E0XtbqiE4OVLZ_jdF1EYWgKNPT2SnwGkQ='
    if cookies != '':
        cookie = cookies
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36 Edg/114.0.1823.79',
        'Cookie': cookie
    }

    if proxy_addr != '':
        # 设置代理
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
        '<script id="SIGI_STATE" type="application/json">(.*?)<\/script><script id="SIGI_RETRY" type="application\/json">',
        html_str)[0]
    # print(json_str)
    json_data = json.loads(json_str)
    return json_data


def get_kuaishou_stream_data(url, cookies=''):
    cookie = 'did=web_7a4e65ac197566d457bc452ee5ade7d0; clientid=3; did=web_7a4e65ac197566d457bc452ee5ade7d0; client_key=65890b29; kpn=GAME_ZONE; kuaishou.live.bfb1s=3e261140b0cf7444a0ba411c6f227d88'
    if cookies != '':
        cookie = cookies
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/115.0',
        'Accept-Language': 'zh-CN,zh;q=0.8,zh-TW;q=0.7,zh-HK;q=0.5,en-US;q=0.3,en;q=0.2',
        'Cookie': cookie
    }

    req = urllib.request.Request(url, headers=headers)
    response = opener.open(req, timeout=15)
    html_str = response.read().decode('utf-8')
    json_str = re.findall('__INITIAL_STATE__=(.*?);\(function', html_str)[0]
    json_data = json.loads(json_str)
    return json_data


def get_huya_stream_data(url, cookies=''):
    cookie = 'huya_ua=webh5&0.0.1&websocket; SoundValue=0.50; alphaValue=0.80; isInLiveRoom=true; game_did=-GcWYDglXNu2ZzqqTr4X-L4PSTclU2iheFm; Hm_lvt_51700b6c722f5bb4cf39906a596ea41f=1691210433,1691477318; udb_deviceid=w_610934293339279360; __yamid_tt1=0.5879880896254449; __yamid_new=C9EFFE0C63A00001A7A94510B5E718A6; guid=0a70d5e7b1d2cd644301d168d268de7b; guid=0a70d5e7b1d2cd644301d168d268de7b; udb_cred=CnDN6T9nhzPKEPgJieRfkuh2PcVTTfwhGVayc7q49srtD2angI9ShGfVHENqGqcGVvyssMbG1spibOt1mjsa57ZsNwEJ1sYVRedE_rsSN30WBp783NmwViE2I-Zh1yPV1MD6NRQURwYmyAUA5YOaY8iT; udb_passdata=3'
    if cookies != '':
        cookie = cookies
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/115.0',
        'Accept-Language': 'zh-CN,zh;q=0.8,zh-TW;q=0.7,zh-HK;q=0.5,en-US;q=0.3,en;q=0.2',
        'Cookie': cookie
    }

    req = urllib.request.Request(url, headers=headers)
    response = opener.open(req, timeout=15)
    html_str = response.read().decode('utf-8')
    json_str = re.findall('stream: (\{"data".*?),"iWebDefaultBitRate"', html_str)[0]
    json_data = json.loads(json_str + '}')
    return json_data


def md5(data):
    return hashlib.md5(data.encode('utf-8')).hexdigest()


def get_token_js(rid, did):
    """
    通过PC网页端的接口获取完整直播源。
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
    # print(params)
    params_list = re.findall('=(.*?)(?=&|$)', params)
    return params_list


def get_douyu_info_data(url):
    match_rid = re.search('rid=(.*?)&', url)
    if match_rid:
        rid = match_rid.group(1)
    else:
        rid = re.search('douyu.com/(.*?)(?=\?|$)', url).group(1)
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/115.0',
    }
    url = f'https://m.douyu.com/{rid}'
    req = urllib.request.Request(url, headers=headers)
    response = opener.open(req, timeout=15)

    html_str = response.read().decode('utf-8')
    json_str = re.search('ssr_pageContext" type="application\/json">(.*?)<\/script>', html_str).group(1)
    # print(json_str)
    json_data = json.loads(json_str)
    return json_data


def get_douyu_stream_data(rid, rate='-1', cookies=''):
    did = '10000000000000000000000000003306'
    params_list = get_token_js(rid, did)

    cookie = 'dy_did=413b835d2ae00270f0c69f6400031601; acf_did=413b835d2ae00270f0c69f6400031601; Hm_lvt_e99aee90ec1b2106afe7ec3b199020a7=1692068308,1694003758; m_did=96003918aa5365bc6dcb4933000316p1; dy_teen_mode=%7B%22uid%22%3A%22472647365%22%2C%22status%22%3A0%2C%22birthday%22%3A%22%22%2C%22password%22%3A%22%22%7D; PHPSESSID=td59qi2fu2gepngb8mlehbeme3; acf_auth=94fc9s%2FeNj%2BKlpU%2Br8tZC3Jo9sZ0wz9ClcHQ1akL2Nhb6ZyCmfjVWSlR3LFFPuePWHRAMo0dt9vPSCoezkFPOeNy4mYcdVOM1a8CbW0ZAee4ipyNB%2Bflr58; dy_auth=bec5yzM8bUFYe%2FnVAjmUAljyrsX%2FcwRW%2FyMHaoArYb5qi8FS9tWR%2B96iCzSnmAryLOjB3Qbeu%2BBD42clnI7CR9vNAo9mva5HyyL41HGsbksx1tEYFOEwxSI; wan_auth37wan=5fd69ed5b27fGM%2FGoswWwDo%2BL%2FRMtnEa4Ix9a%2FsH26qF0sR4iddKMqfnPIhgfHZUqkAk%2FA1d8TX%2B6F7SNp7l6buIxAVf3t9YxmSso8bvHY0%2Fa6RUiv8; acf_uid=472647365; acf_username=472647365; acf_nickname=%E7%94%A8%E6%88%B776576662; acf_own_room=0; acf_groupid=1; acf_phonestatus=1; acf_avatar=https%3A%2F%2Fapic.douyucdn.cn%2Fupload%2Favatar%2Fdefault%2F24_; acf_ct=0; acf_ltkid=25305099; acf_biz=1; acf_stk=90754f8ed18f0c24; Hm_lpvt_e99aee90ec1b2106afe7ec3b199020a7=1694003778'
    if cookies != '':
        cookie = cookies
    headers = {
        'User-Agent': 'Mozilla/5.0 (Linux; Android 11; SAMSUNG SM-G973U) AppleWebKit/537.36 (KHTML, like Gecko) SamsungBrowser/14.2 Chrome/87.0.4280.141 Mobile Safari/537.36',
        'Referer': 'https://m.douyu.com/3125893?rid=3125893&dyshid=0-96003918aa5365bc6dcb4933000316p1&dyshci=181',
        'Cookie': cookie
    }
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


def get_yy_stream_data(url, cookies=''):
    cid = re.search('yy.com/(.*?)/', url).group(1)

    cookie = 'hd_newui=0.2103068903976506; hdjs_session_id=0.4929014850884579; hdjs_session_time=1694004002636; hiido_ui=0.923076230899782'
    if cookies != '':
        cookie = cookies
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/115.0',
        'Accept-Language': 'zh-CN,zh;q=0.8,zh-TW;q=0.7,zh-HK;q=0.5,en-US;q=0.3,en;q=0.2',
        'Referer': 'https://www.yy.com/',
        'Cookie': cookie
    }
    req = urllib.request.Request(url, headers=headers)
    response = opener.open(req, timeout=15)
    html_str = response.read().decode('utf-8')
    live_info = re.search('<div class="w-liveplayer-head__content">(.*)<i class="follow-i">', html_str, re.S).group(1)
    anchor_name = re.search('<h2>(.*?)</h2>', live_info).group(1)

    data = '{"head":{"seq":1691766627723,"appidstr":"0","bidstr":"121","cidstr":"' + cid + '","sidstr":"' + cid + '","uid64":0,"client_type":108,"client_ver":"5.14.13","stream_sys_ver":1,"app":"yylive_web","playersdk_ver":"5.14.13","thundersdk_ver":"0","streamsdk_ver":"5.14.13"},"client_attribute":{"client":"web","model":"","cpu":"","graphics_card":"","os":"chrome","osversion":"0","vsdk_version":"","app_identify":"","app_version":"","business":"","width":"1536","height":"864","scale":"","client_type":8,"h265":0},"avp_parameter":{"version":1,"client_type":8,"service_type":0,"imsi":0,"send_time":1691766627,"line_seq":-1,"gear":4,"ssl":1,"stream_format":0}}'
    data_bytes = data.encode('utf-8')
    url2 = f'https://stream-manager.yy.com/v3/channel/streams?uid=0&cid={cid}&sid={cid}&appid=0&sequence=1691766112069&encode=json'
    req = urllib.request.Request(url2, data=data_bytes, headers=headers)
    response = opener.open(req, timeout=15)
    json_str = response.read().decode('utf-8')
    json_data = json.loads(json_str)
    json_data['anchor_name'] = anchor_name
    return json_data


def get_bilibili_stream_data(url, cookies=''):
    cookie = "buvid3=13436C33-39B8-C4D5-C5C6-3F31B85716A131745infoc; b_nut=1680525931; CURRENT_FNVAL=4048; _uuid=B10E775DC-168D-CA47-E1B8-CEF7C52FA84234052infoc; buvid_fp=a2f7f8f3977824b52ec75cf23e5b6754; CURRENT_PID=70fa2680-d21d-11ed-ba58-9979ebfa5794; rpdid=|(JYYJ|uuYm)0J'uY)|lklmRJ; buvid4=C29E3582-5740-8FF3-AFD1-98B345DDAF5393968-022082019-Vk7oLekZ8O%2FtgWtFEu98GQ%3D%3D; DedeUserID=623475372; DedeUserID__ckMd5=db79fcea5a8315aa; i-wanna-go-back=-1; b_ut=5; FEED_LIVE_VERSION=V8; header_theme_version=CLOSE; home_feed_column=5; browser_resolution=1483-722; SESSDATA=122468fe%2C1707184844%2C2c98c%2A827Ts7uT3NZIxeOzop88h3EdmSUIG9NhWF9VkiidKIkTgJkTbh5WcONjTKuaOwfeR9t6uUZAAASAA; bili_jct=b8479df41520c402eb0a1a7f37a26de8; bp_video_offset_623475372=827303476826472609; PVID=1; LIVE_BUVID=AUTO5816940041629512; GIFT_BLOCK_COOKIE=GIFT_BLOCK_COOKIE"
    if cookies != '':
        cookie = cookies
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/115.0',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
        'Referer': 'https://live.bilibili.com/?spm_id_from=333.1296.0.0',
        'Cookie': cookie
    }
    req = urllib.request.Request(url, headers=headers)
    response = opener.open(req, timeout=15)
    html_str = response.read().decode('utf-8')
    json_str = re.search('<script>window.__NEPTUNE_IS_MY_WAIFU__=(.*?)</script><script>', html_str, re.S).group(1)
    json_data = json.loads(json_str)
    return json_data


if __name__ == '__main__':
    # 尽量用自己的cookie，以避免默认的不可用导致无法获取数据
    dy_cookie = ''
    ks_cookie = ''
    url = "https://live.douyin.com/745964462470"  # 抖音直播
    # url = "https://www.tiktok.com/@pearlgaga88/live"  # Tiktok直播
    # url = "https://live.kuaishou.com/u/yall1102"  # 快手直播
    # url = 'https://www.huya.com/116'  # 虎牙直播
    # url = 'https://www.douyu.com/topic/wzDBLS6?rid=4921614&dyshid='  # 斗鱼直播
    # url = 'https://www.douyu.com/3637778?dyshid'
    # url = 'https://www.yy.com/22490906/22490906'  # YY直播
    # url = 'https://live.bilibili.com/21593109'  # b站直播


    print(get_douyin_stream_data(url, dy_cookie))
    # print(get_tiktok_stream_data(url,'http://127.0.0.1:7890'))
    # print(get_kuaishou_stream_data(url,ks_cookie))
    # print(get_huya_stream_data(url))
    # print(get_douyu_info_data(url))
    # print(get_douyu_stream_data("4921614",rate='-1'))
    # print(get_yy_stream_data(url))
    # print(get_bilibili_stream_data(url))



