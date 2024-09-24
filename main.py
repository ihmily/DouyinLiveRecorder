# -*- encoding: utf-8 -*-

"""
Author: Hmily
GitHub: https://github.com/ihmily
Date: 2023-07-17 23:52:05
Update: 2024-09-25 02:10:00
Copyright (c) 2023-2024 by Hmily, All Rights Reserved.
Function: Record live stream video.
"""

import os
import sys
import subprocess
import signal
import threading
import time
import datetime
import json
import re
import shutil
import random
import base64
import hashlib
import urllib.parse
import urllib.request
from urllib.error import URLError, HTTPError
from typing import Any, Union, Dict
import configparser

from spider import (
    get_douyin_stream_data,
    get_douyin_app_stream_data,
    get_tiktok_stream_data,
    get_kuaishou_stream_data,
    get_huya_stream_data,
    get_douyu_info_data,
    get_douyu_stream_data,
    get_yy_stream_data,
    get_bilibili_stream_data,
    get_bilibili_room_info,
    get_xhs_stream_url,
    get_bigo_stream_url,
    get_blued_stream_url,
    get_afreecatv_stream_data,
    get_netease_stream_data,
    get_qiandurebo_stream_data,
    get_pandatv_stream_data,
    get_maoerfm_stream_url,
    get_winktv_stream_data,
    get_flextv_stream_data,
    get_looklive_stream_url,
    get_popkontv_stream_url,
    get_twitcasting_stream_url,
    get_baidu_stream_data,
    get_weibo_stream_data,
    get_kugou_stream_url,
    get_twitchtv_stream_data,
    get_liveme_stream_url,
    get_huajiao_stream_url,
    get_liuxing_stream_url,
    get_showroom_stream_data,
    get_acfun_stream_data,
    get_huya_app_stream_url,
    get_shiguang_stream_url,
    get_yinbo_stream_url,
    get_yingke_stream_url,
    get_zhihu_stream_url
)

from utils import (
    logger, check_md5,
    trace_error_decorator, get_file_paths
)
from msg_push import dingtalk, xizhi, tg_bot, email_message, bark

version = "v3.0.7"
platforms = ("\n国内站点：抖音|快手|虎牙|斗鱼|YY|B站|小红书|bigo|blued|网易CC|千度热播|猫耳FM|Look|TwitCasting|百度|微博|"
             "酷狗|LiveMe|花椒|流星|Acfun|时光|映客|音播|知乎"
             "\n海外站点：TikTok|AfreecaTV|PandaTV|WinkTV|FlexTV|PopkonTV|TwitchTV|ShowRoom")

recording = set()
not_recording = set()
warning_count = 0
max_request = 0
pre_max_request = 0
monitoring = 0
running_list = []
url_tuples_list = []
url_comments = []
text_no_repeat_url = []
create_var = locals()
first_start = True
need_update_line_list = []
first_run = True
not_record_list = []
start_display_time = datetime.datetime.now()
global_proxy = False
recording_time_list = {}
script_path = os.path.split(os.path.realpath(sys.argv[0]))[0]
config_file = f'{script_path}/config/config.ini'
url_config_file = f'{script_path}/config/URL_config.ini'
backup_dir = f'{script_path}/backup_config'
text_encoding = 'utf-8-sig'
rstr = r"[\/\\\:\*\?\"\<\>\|&.。,， ]"
ffmpeg_path = f"{script_path}/ffmpeg.exe"
default_path = f'{script_path}/downloads'
os.makedirs(default_path, exist_ok=True)
file_update_lock = threading.Lock()


def signal_handler(_signal, _frame):
    sys.exit(0)


signal.signal(signal.SIGTERM, signal_handler)


def display_info():
    global start_display_time
    time.sleep(5)
    while True:
        try:
            time.sleep(5)
            if os.name == 'nt':
                os.system("cls")
            elif os.name == 'posix':
                os.system("clear")
            print(f"\r共监测{monitoring}个直播中", end=" | ")
            print(f"同一时间访问网络的线程数: {max_request}", end=" | ")
            if len(video_save_path) > 0:
                if not os.path.exists(video_save_path):
                    print("配置文件里,直播保存路径并不存在,请重新输入一个正确的路径.或留空表示当前目录,按回车退出")
                    input("程序结束")
                    sys.exit(0)

            print(f"是否开启代理录制: {'是' if use_proxy else '否'}", end=" | ")
            if split_video_by_time:
                print(f"录制分段开启: {split_time}秒", end=" | ")
            print(f"是否生成时间文件: {'是' if create_time_file else '否'}", end=" | ")
            print(f"录制视频质量为: {video_record_quality}", end=" | ")
            print(f"录制视频格式为: {video_save_type}", end=" | ")
            print(f"目前瞬时错误数为: {warning_count}", end=" | ")
            format_now_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
            print(f"当前时间: {format_now_time}")

            if len(recording) == 0 and len(not_recording) == 0:
                time.sleep(5)
                print(f"\r没有正在录制的直播 {format_now_time[-8:]}", end="")
                print("")
                continue
            else:
                now_time = datetime.datetime.now()
                if len(recording) > 0:
                    print("x" * 60)
                    no_repeat_recording = list(set(recording))
                    print(f"正在录制{len(no_repeat_recording)}个直播: ")
                    for recording_live in no_repeat_recording:
                        rt, qa = recording_time_list[recording_live]
                        have_record_time = now_time - rt
                        print(f"{recording_live}[{qa}] 正在录制中 {str(have_record_time).split('.')[0]}")

                    # print('\n本软件已运行：'+str(now_time - start_display_time).split('.')[0])
                    print("x" * 60)
                else:
                    start_display_time = now_time
        except Exception as e:
            logger.error(f"错误信息: {e} 发生错误的行数: {e.__traceback__.tb_lineno}")


def update_file(file_path: str, old_str: str, new_str: str, start_str: str = None):
    if old_str == new_str and start_str is None:
        return
    with file_update_lock:
        file_data = ""
        with open(file_path, "r", encoding=text_encoding) as f:
            try:
                for text_line in f:
                    if old_str in text_line:
                        text_line = text_line.replace(old_str, new_str)
                        if start_str:
                            text_line = f'{start_str}{text_line}'
                    file_data += text_line
            except RuntimeError as e:
                logger.error(f"错误信息: {e} 发生错误的行数: {e.__traceback__.tb_lineno}")
                if ini_URL_content:
                    with open(file_path, "w", encoding=text_encoding) as f2:
                        f2.write(ini_URL_content)
        if file_data:
            with open(file_path, "w", encoding=text_encoding) as f:
                f.write(file_data)


def delete_line(file_path: str, del_line: str):
    with file_update_lock:
        with open(file_path, 'r+', encoding=text_encoding) as f:
            lines = f.readlines()
            f.seek(0)
            f.truncate()
            for txt_line in lines:
                if del_line not in txt_line:
                    f.write(txt_line)


def converts_mp4(address: str):
    if ts_to_mp4:
        _output = subprocess.check_output([
            "ffmpeg", "-i", address,
            "-c:v", "copy",
            "-c:a", "copy",
            "-f", "mp4", address.split('.')[0] + ".mp4",
        ], stderr=subprocess.STDOUT)
        if delete_origin_file:
            time.sleep(1)
            if os.path.exists(address):
                os.remove(address)


def converts_m4a(address: str):
    if ts_to_m4a:
        _output = subprocess.check_output([
            "ffmpeg", "-i", address,
            "-n", "-vn",
            "-c:a", "aac", "-bsf:a", "aac_adtstoasc", "-ab", "320k",
            address.split('.')[0] + ".m4a",
        ], stderr=subprocess.STDOUT)
        if delete_origin_file:
            time.sleep(1)
            if os.path.exists(address):
                os.remove(address)


def create_ass_file(file_gruop: list):
    anchor_name = file_gruop[0]
    ass_filename = file_gruop[1]
    index_time = -1
    finish = 0
    today = datetime.datetime.now()
    re_datatime = today.strftime('%Y-%m-%d %H:%M:%S')

    while True:
        index_time += 1
        txt = str(index_time) + "\n" + transform_int_to_time(index_time) + ',000 --> ' + transform_int_to_time(
            index_time + 1) + ',000' + "\n" + str(re_datatime) + "\n"

        with open(ass_filename + ".ass", 'a', encoding=text_encoding) as f:
            f.write(txt)

        if anchor_name not in recording:
            finish += 1
            offset = datetime.timedelta(seconds=1)
            re_datatime = (today + offset).strftime('%Y-%m-%d %H:%M:%S')
            today = today + offset
        else:
            time.sleep(1)
            today = datetime.datetime.now()
            re_datatime = today.strftime('%Y-%m-%d %H:%M:%S')

        if finish > 15:
            break


def change_max_connect():
    global max_request
    global warning_count
    global pre_max_request
    preset = max_request
    start_time = time.time()
    pre_max_request = max_request

    while True:
        time.sleep(5)
        if 10 <= warning_count <= 20:
            if preset > 5:
                max_request = 5
            else:
                max_request //= 2
                if max_request > 0:
                    max_request = preset
                else:
                    preset = 1
            time.sleep(5)

        elif 20 < warning_count:
            max_request = 1
            time.sleep(10)

        elif warning_count < 10 and time.time() - start_time > 60:
            max_request = preset
            start_time = time.time()

        warning_count = 0
        if pre_max_request != max_request:
            pre_max_request = max_request
            print("同一时间访问网络的线程数动态改为", max_request)


@trace_error_decorator
def get_douyin_stream_url(json_data: dict, video_quality: str) -> Dict[str, Any]:
    anchor_name = json_data.get('anchor_name', None)

    result = {
        "anchor_name": anchor_name,
        "is_live": False,
    }

    status = json_data.get("status", 4)  # 直播状态 2 是正在直播、4 是未开播

    if status == 2:
        stream_url = json_data['stream_url']
        flv_url_dict = stream_url['flv_pull_url']
        flv_url_list = list(flv_url_dict.values())
        m3u8_url_dict = stream_url['hls_pull_url_map']
        m3u8_url_list = list(m3u8_url_dict.values())

        while len(flv_url_list) < 5:
            flv_url_list.append(flv_url_list[-1])
            m3u8_url_list.append(m3u8_url_list[-1])

        video_qualities = {"原画": 0, "蓝光": 0, "超清": 1, "高清": 2, "标清": 3, "流畅": 4}
        quality_index = video_qualities.get(video_quality)
        m3u8_url = m3u8_url_list[quality_index]
        flv_url = flv_url_list[quality_index]
        result['m3u8_url'] = m3u8_url
        result['flv_url'] = flv_url
        result['is_live'] = True
        result['record_url'] = m3u8_url
    return result


@trace_error_decorator
def get_tiktok_stream_url(json_data: dict, video_quality: str) -> Dict[str, Any]:
    if not json_data:
        return {"anchor_name": None, "is_live": False}

    def get_video_quality_url(stream, q_key) -> list[dict[str, int | Any]]:
        play_list = []
        for key in stream:
            url_info = stream[key]['main']
            play_url = url_info[q_key]
            sdk_params = url_info['sdk_params']
            sdk_params = json.loads(sdk_params)
            vbitrate = int(sdk_params['vbitrate'])
            resolution = sdk_params['resolution']
            if vbitrate != 0 and resolution:
                width, height = map(int, resolution.split('x'))
                play_list.append({'url': play_url, 'vbitrate': vbitrate, 'resolution': (width, height)})

        play_list.sort(key=lambda x: x['vbitrate'], reverse=True)
        play_list.sort(key=lambda x: (-x['vbitrate'], -x['resolution'][0], -x['resolution'][1]))
        return play_list

    live_room = json_data['LiveRoom']['liveRoomUserInfo']
    user = live_room['user']
    anchor_name = f"{user['nickname']}-{user['uniqueId']}"
    status = user.get("status", 4)

    result = {
        "anchor_name": anchor_name,
        "is_live": False,
    }

    if status == 2:
        stream_data = live_room['liveRoom']['streamData']['pull_data']['stream_data']
        stream_data = json.loads(stream_data).get('data', {})
        flv_url_list = get_video_quality_url(stream_data, 'flv')
        m3u8_url_list = get_video_quality_url(stream_data, 'hls')

        while len(flv_url_list) < 5:
            flv_url_list.append(flv_url_list[-1])
        while len(m3u8_url_list) < 5:
            m3u8_url_list.append(m3u8_url_list[-1])
        video_qualities = {"原画": 0, "蓝光": 0, "超清": 1, "高清": 2, "标清": 3, '流畅': 4}
        quality_index = video_qualities.get(video_quality)
        result['flv_url'] = flv_url_list[quality_index]['url']
        result['m3u8_url'] = m3u8_url_list[quality_index]['url']
        result['is_live'] = True
        result['record_url'] = flv_url_list[quality_index]['url'].replace("https://", "http://")
    return result


@trace_error_decorator
def get_kuaishou_stream_url(json_data: dict, video_quality: str) -> Dict[str, Any]:
    if json_data['type'] == 1 and not json_data["is_live"]:
        return json_data
    live_status = json_data['is_live']

    result = {
        "type": 2,
        "anchor_name": json_data['anchor_name'],
        "is_live": live_status,
    }

    if live_status:
        quality_mapping = {'原画': 0, '蓝光': 0, '超清': 1, '高清': 2, '标清': 3, '流畅': 4}

        if video_quality in quality_mapping:

            quality_index = quality_mapping[video_quality]
            if 'm3u8_url_list' in json_data:
                m3u8_url_list = json_data['m3u8_url_list'][::-1]
                while len(m3u8_url_list) < 5:
                    m3u8_url_list.append(m3u8_url_list[-1])
                m3u8_url = m3u8_url_list[quality_index]['url']
                result['m3u8_url'] = m3u8_url

            if 'flv_url_list' in json_data:
                flv_url_list = json_data['flv_url_list'][::-1]
                while len(flv_url_list) < 5:
                    flv_url_list.append(flv_url_list[-1])
                flv_url = flv_url_list[quality_index]['url']
                result['flv_url'] = flv_url
                result['record_url'] = flv_url

            result['is_live'] = True
    return result


@trace_error_decorator
def get_huya_stream_url(json_data: dict, video_quality: str) -> Dict[str, Any]:
    game_live_info = json_data['data'][0]['gameLiveInfo']
    stream_info_list = json_data['data'][0]['gameStreamInfoList']
    anchor_name = game_live_info.get('nick', '')

    result = {
        "anchor_name": anchor_name,
        "is_live": False,
    }

    if stream_info_list:
        select_cdn = stream_info_list[0]
        flv_url = select_cdn.get('sFlvUrl')
        stream_name = select_cdn.get('sStreamName')
        flv_url_suffix = select_cdn.get('sFlvUrlSuffix')
        hls_url = select_cdn.get('sHlsUrl')
        hls_url_suffix = select_cdn.get('sHlsUrlSuffix')
        flv_anti_code = select_cdn.get('sFlvAntiCode')

        def get_anti_code(old_anti_code: str) -> str:

            # js地址：https://hd.huya.com/cdn_libs/mobile/hysdk-m-202402211431.js

            params_t = 100
            sdk_version = 2403051612

            # sdk_id是13位数毫秒级时间戳
            t13 = int(time.time()) * 1000
            sdk_sid = t13

            # 计算uuid和uid参数值
            init_uuid = (int(t13 % 10 ** 10 * 1000) + int(1000 * random.random())) % 4294967295  # 直接初始化
            uid = random.randint(1400000000000, 1400009999999)  # 经过测试uid也可以使用init_uuid代替
            seq_id = uid + sdk_sid  # 移动端请求的直播流地址中包含seqId参数

            # 计算ws_time参数值(16进制) 可以是当前毫秒时间戳，当然也可以直接使用url_query['wsTime'][0]
            # 原始最大误差不得慢240000毫秒
            target_unix_time = (t13 + 110624) // 1000
            ws_time = hex(target_unix_time)[2:].lower()

            # fm参数值是经过url编码然后base64编码得到的，解码结果类似 DWq8BcJ3h6DJt6TY_$0_$1_$2_$3
            # 具体细节在上面js中查看，大概在32657行代码开始，有base64混淆代码请自行替换
            url_query = urllib.parse.parse_qs(old_anti_code)
            ws_secret_pf = base64.b64decode(urllib.parse.unquote(url_query['fm'][0]).encode()).decode().split("_")[0]
            ws_secret_hash = hashlib.md5(f'{seq_id}|{url_query["ctype"][0]}|{params_t}'.encode()).hexdigest()
            ws_secret = f'{ws_secret_pf}_{uid}_{stream_name}_{ws_secret_hash}_{ws_time}'
            ws_secret_md5 = hashlib.md5(ws_secret.encode()).hexdigest()

            anti_code = (
                f'wsSecret={ws_secret_md5}&wsTime={ws_time}&seqid={seq_id}&ctype={url_query["ctype"][0]}&ver=1'
                f'&fs={url_query["fs"][0]}&uuid={init_uuid}&u={uid}&t={params_t}&sv={sdk_version}'
                f'&sdk_sid={sdk_sid}&codec=264'
            )
            return anti_code

        new_anti_code = get_anti_code(flv_anti_code)
        flv_url = f'{flv_url}/{stream_name}.{flv_url_suffix}?{new_anti_code}&ratio='
        m3u8_url = f'{hls_url}/{stream_name}.{hls_url_suffix}?{new_anti_code}&ratio='

        quality_list = flv_anti_code.split('&exsphd=')
        if len(quality_list) > 1 and video_quality not in ["原画", "蓝光"]:
            pattern = r"(?<=264_)\d+"
            quality_list = [x for x in re.findall(pattern, quality_list[1])][::-1]
            while len(quality_list) < 5:
                quality_list.append(quality_list[-1])

            video_quality_options = {
                "超清": quality_list[0],
                "高清": quality_list[1],
                "标清": quality_list[2],
                "流畅": quality_list[3]
            }

            if video_quality not in video_quality_options:
                raise ValueError(
                    f"Invalid video quality. Available options are: {', '.join(video_quality_options.keys())}")

            flv_url = flv_url + str(video_quality_options[video_quality])
            m3u8_url = m3u8_url + str(video_quality_options[video_quality])

        result['flv_url'] = flv_url
        result['m3u8_url'] = m3u8_url
        result['is_live'] = True
        result['record_url'] = flv_url
    return result


@trace_error_decorator
def get_douyu_stream_url(json_data: dict, cookies: str, video_quality: str, proxy_address: str) -> Dict[str, Any]:
    if not json_data["is_live"]:
        return json_data

    video_quality_options = {
        "原画": '0',
        "蓝光": '0',
        "超清": '3',
        "高清": '2',
        "标清": '1',
        "流畅": '1'
    }

    rid = str(json_data["room_id"])
    json_data.pop("room_id", None)
    rate = video_quality_options.get(video_quality, '0')
    flv_data = get_douyu_stream_data(rid, rate, cookies=cookies, proxy_addr=proxy_address)
    rtmp_url = flv_data['data'].get('rtmp_url', None)
    rtmp_live = flv_data['data'].get('rtmp_live', None)
    if rtmp_live:
        flv_url = f'{rtmp_url}/{rtmp_live}'
        json_data['flv_url'] = flv_url
        json_data['record_url'] = flv_url
    return json_data


@trace_error_decorator
def get_yy_stream_url(json_data: dict) -> Dict[str, Any]:
    anchor_name = json_data.get('anchor_name', '')
    result = {
        "anchor_name": anchor_name,
        "is_live": False,
    }
    if 'avp_info_res' in json_data:
        stream_line_addr = json_data['avp_info_res']['stream_line_addr']
        cdn_info = list(stream_line_addr.values())[0]
        flv_url = cdn_info['cdn_info']['url']
        result['flv_url'] = flv_url
        result['is_live'] = True
        result['record_url'] = flv_url
    return result


@trace_error_decorator
def get_bilibili_stream_url(json_data: dict, video_quality: str) -> Dict[str, Any]:
    anchor_name = json_data["anchor_name"]
    if not json_data["live_status"]:
        return {
            "anchor_name": anchor_name,
            "is_live": False
        }

    room_url = json_data['room_url']

    video_quality_options = {
        "原画": '10000',
        "蓝光": '400',
        "超清": '250',
        "高清": '150',
        "标清": '80',
        "流畅": '80'
    }

    select_quality = video_quality_options[video_quality]
    play_url = get_bilibili_stream_data(room_url, qn=select_quality, platform='web', proxy_addr=proxy_addr,
                                        cookies=bili_cookie)
    return {
        'anchor_name': json_data['anchor_name'],
        'is_live': True,
        'record_url': play_url
    }


@trace_error_decorator
def get_netease_stream_url(json_data: dict, video_quality: str) -> Dict[str, Any]:
    if not json_data['is_live']:
        return json_data
    stream_list = json_data['stream_list']['resolution']
    order = ['blueray', 'ultra', 'high', 'standard']
    sorted_keys = [key for key in order if key in stream_list]
    while len(sorted_keys) < 5:
        sorted_keys.append(sorted_keys[-1])
    quality_list = {'原画': 0, '蓝光': 0, '超清': 1, '高清': 2, '标清': 3, '流畅': 4}
    selected_quality = sorted_keys[quality_list[video_quality]]
    flv_url_list = stream_list[selected_quality]['cdn']
    selected_cdn = list(flv_url_list.keys())[0]
    flv_url = flv_url_list[selected_cdn]
    return {
        "is_live": True,
        "anchor_name": json_data['anchor_name'],
        "flv_url": flv_url,
        "record_url": flv_url
    }


def get_stream_url(json_data: dict, video_quality: str, url_type: str = 'm3u8', spec: bool = False,
                   extra_key: Union[str, int] = None) -> Dict[str, Any]:
    if not json_data['is_live']:
        return json_data

    play_url_list = json_data['play_url_list']
    quality_list = {'原画': 0, '蓝光': 0, '超清': 1, '高清': 2, '标清': 3, '流畅': 4}
    while len(play_url_list) < 5:
        play_url_list.append(play_url_list[-1])

    selected_quality = quality_list[video_quality]
    data = {
        "anchor_name": json_data['anchor_name'],
        "is_live": True
    }
    if url_type == 'm3u8':
        m3u8_url = play_url_list[selected_quality][extra_key] if extra_key else play_url_list[selected_quality]
        data["m3u8_url"] = json_data['m3u8_url'] if spec else m3u8_url
        data["record_url"] = m3u8_url
    else:
        flv = play_url_list[selected_quality][extra_key] if extra_key else play_url_list[selected_quality]
        data["flv_url"] = flv
        data["record_url"] = flv

    return data


def push_message(content: str) -> Union[str, list]:
    push_pts = []
    if '微信' in live_status_push:
        push_pts.append('微信')
        xizhi(xizhi_api_url, content)
    if '钉钉' in live_status_push:
        push_pts.append('钉钉')
        dingtalk(dingtalk_api_url, content, dingtalk_phone_num)
    if '邮箱' in live_status_push:
        push_pts.append('邮箱')
        email_message(mail_host, mail_password, from_email, to_email, "直播间状态更新通知", content)
    if 'TG' in live_status_push.upper():
        push_pts.append('TG')
        tg_bot(tg_chat_id, tg_token, content)
    if 'BARK' in live_status_push.upper():
        push_pts.append('BARK')
        bark(bark_msg_api, title="直播录制通知", content=content, level=bark_msg_level, sound=bark_msg_ring)
    push_pts = '、'.join(push_pts) if len(push_pts) > 0 else []
    return push_pts


def clear_record_info(record_name, anchor_name, record_url):
    if record_name in recording:
        recording.remove(record_name)
    if anchor_name in not_recording:
        not_recording.add(anchor_name)
    if record_url in url_comments and record_url in running_list:
        print(f"[{record_name}]从录制列表中清除")
        running_list.remove(record_url)


def check_subprocess(record_name: str, anchor_name: str, record_url: str, ffmpeg_command: list):
    process = subprocess.Popen(
        ffmpeg_command, stderr=subprocess.STDOUT, text=True, stdout=subprocess.PIPE, stdin=subprocess.PIPE
    )

    # 检查进程是否结束
    while process.poll() is None:
        if record_url in url_comments:
            print(f"[{record_name}]录制时已被注释,本条线程将会退出")
            clear_record_info(record_name, anchor_name, record_url)
            process.terminate()
            process.wait()
            return True
        time.sleep(1)

    return_code = process.returncode
    if return_code == 0:
        print(f"[{record_name}]录制成功完成")
    else:
        print(f"[{record_name}]录制退出,返回码: {return_code}")
    return return_code == 0


def start_record(url_data: tuple, count_variable: int = -1):
    global warning_count
    global video_save_path
    start_pushed = False

    while True:
        try:
            record_finished = False
            record_finished_2 = False
            run_once = False
            is_long_url = False
            no_error = True
            new_record_url = ''
            count_time = time.time()
            retry = 0
            record_quality, record_url, anchor_name = url_data
            proxy_address = proxy_addr

            if proxy_addr:
                proxy_address = None
                for platform in enable_proxy_platform_list:
                    if platform and platform.strip() in url:
                        proxy_address = proxy_addr
                        break

            if not proxy_address:
                if extra_enable_proxy_platform_list:
                    for pt in extra_enable_proxy_platform_list:
                        if pt and pt.strip() in url:
                            proxy_address = proxy_addr_bak if proxy_addr_bak else None

            # print(f'\r代理地址:{proxy_address}')
            # print(f'\r全局代理:{global_proxy}')
            print(f"\r运行新线程,传入地址 {record_url}")
            while True:
                try:
                    port_info = []
                    if record_url.find("douyin.com/") > -1:
                        platform = '抖音直播'
                        with semaphore:
                            if 'live.douyin.com' in record_url:
                                json_data = get_douyin_stream_data(
                                    url=record_url,
                                    proxy_addr=proxy_address,
                                    cookies=dy_cookie)
                            else:
                                json_data = get_douyin_app_stream_data(
                                    url=record_url,
                                    proxy_addr=proxy_address,
                                    cookies=dy_cookie)
                            port_info = get_douyin_stream_url(json_data, record_quality)

                    elif record_url.find("https://www.tiktok.com/") > -1:
                        platform = 'TikTok直播'
                        with semaphore:
                            if global_proxy or proxy_address:
                                json_data = get_tiktok_stream_data(
                                    url=record_url,
                                    proxy_addr=proxy_address,
                                    cookies=tiktok_cookie)
                                port_info = get_tiktok_stream_url(json_data, record_quality)
                            else:
                                logger.error(f"错误信息: 网络异常，请检查网络是否能正常访问TikTok平台")

                    elif record_url.find("https://live.kuaishou.com/") > -1:
                        platform = '快手直播'
                        with semaphore:
                            json_data = get_kuaishou_stream_data(
                                url=record_url,
                                proxy_addr=proxy_address,
                                cookies=ks_cookie)
                            port_info = get_kuaishou_stream_url(json_data, record_quality)

                    elif record_url.find("https://www.huya.com/") > -1:
                        platform = '虎牙直播'
                        with semaphore:
                            if record_quality not in ['原画', '蓝光', '超清']:
                                json_data = get_huya_stream_data(
                                    url=record_url,
                                    proxy_addr=proxy_address,
                                    cookies=hy_cookie)
                                port_info = get_huya_stream_url(json_data, record_quality)
                            else:
                                port_info = get_huya_app_stream_url(
                                    url=record_url,
                                    proxy_addr=proxy_address,
                                    cookies=hy_cookie
                                )

                    elif record_url.find("https://www.douyu.com/") > -1:
                        platform = '斗鱼直播'
                        with semaphore:
                            json_data = get_douyu_info_data(
                                url=record_url, proxy_addr=proxy_address, cookies=douyu_cookie)
                            port_info = get_douyu_stream_url(
                                json_data, proxy_address=proxy_address, cookies=douyu_cookie,
                                video_quality=record_quality
                            )

                    elif record_url.find("https://www.yy.com/") > -1:
                        platform = 'YY直播'
                        with semaphore:
                            json_data = get_yy_stream_data(
                                url=record_url, proxy_addr=proxy_address, cookies=yy_cookie)
                            port_info = get_yy_stream_url(json_data)

                    elif record_url.find("https://live.bilibili.com/") > -1:
                        platform = 'B站直播'
                        with semaphore:
                            json_data = get_bilibili_room_info(
                                url=record_url, proxy_addr=proxy_address, cookies=bili_cookie)
                            port_info = get_bilibili_stream_url(json_data, record_quality)

                    elif record_url.find("https://www.redelight.cn/") > -1 or \
                            record_url.find("https://www.xiaohongshu.com/") > -1 or \
                            record_url.find("http://xhslink.com/") > -1:
                        platform = '小红书直播'
                        if retry > 0:
                            delete_line(url_config_file, record_url)
                            if record_url in running_list:
                                running_list.remove(record_url)
                                not_record_list.append(record_url)
                                logger.info(f'{record_url} 小红书直播已结束，停止录制')
                                return
                        with semaphore:
                            port_info = get_xhs_stream_url(url=record_url, proxy_addr=proxy_address, cookies=xhs_cookie)
                            retry += 1

                    elif record_url.find("https://www.bigo.tv/") > -1 or record_url.find("slink.bigovideo.tv/") > -1:
                        platform = 'Bigo直播'
                        with semaphore:
                            port_info = get_bigo_stream_url(record_url, proxy_addr=proxy_address, cookies=bigo_cookie)

                    elif record_url.find("https://app.blued.cn/") > -1:
                        platform = 'Blued直播'
                        with semaphore:
                            port_info = get_blued_stream_url(record_url, proxy_addr=proxy_address, cookies=blued_cookie)

                    elif record_url.find("afreecatv.com/") > -1:
                        platform = 'AfreecaTV'
                        with semaphore:
                            if global_proxy or proxy_address:
                                json_data = get_afreecatv_stream_data(
                                    url=record_url, proxy_addr=proxy_address,
                                    cookies=afreecatv_cookie,
                                    username=afreecatv_username,
                                    password=afreecatv_password
                                )
                                port_info = get_stream_url(json_data, record_quality, spec=True)
                            else:
                                logger.error(f"错误信息: 网络异常，请检查本网络是否能正常访问AfreecaTV平台")

                    elif record_url.find("cc.163.com/") > -1:
                        platform = '网易CC直播'
                        with semaphore:
                            json_data = get_netease_stream_data(url=record_url, cookies=netease_cookie)
                            port_info = get_netease_stream_url(json_data, record_quality)

                    elif record_url.find("qiandurebo.com/") > -1:
                        platform = '千度热播'
                        with semaphore:
                            port_info = get_qiandurebo_stream_data(
                                url=record_url, proxy_addr=proxy_address, cookies=qiandurebo_cookie)

                    elif record_url.find("www.pandalive.co.kr/") > -1:
                        platform = 'PandaTV'
                        with semaphore:
                            if global_proxy or proxy_address:
                                json_data = get_pandatv_stream_data(
                                    url=record_url,
                                    proxy_addr=proxy_address,
                                    cookies=pandatv_cookie
                                )
                                port_info = get_stream_url(json_data, record_quality, spec=True)
                            else:
                                logger.error(f"错误信息: 网络异常，请检查本网络是否能正常访问PandaTV直播平台")

                    elif record_url.find("fm.missevan.com/") > -1:
                        platform = '猫耳FM直播'
                        with semaphore:
                            port_info = get_maoerfm_stream_url(
                                url=record_url, proxy_addr=proxy_address, cookies=maoerfm_cookie)

                    elif record_url.find("www.winktv.co.kr/") > -1:
                        platform = 'WinkTV'
                        with semaphore:
                            if global_proxy or proxy_address:
                                json_data = get_winktv_stream_data(
                                    url=record_url,
                                    proxy_addr=proxy_address,
                                    cookies=winktv_cookie)
                                port_info = get_stream_url(json_data, record_quality, spec=True)
                            else:
                                logger.error(f"错误信息: 网络异常，请检查本网络是否能正常访问WinkTV直播平台")

                    elif record_url.find("www.flextv.co.kr/") > -1:
                        platform = 'FlexTV'
                        with semaphore:
                            if global_proxy or proxy_address:
                                json_data = get_flextv_stream_data(
                                    url=record_url,
                                    proxy_addr=proxy_address,
                                    cookies=flextv_cookie,
                                    username=flextv_username,
                                    password=flextv_password
                                )
                                port_info = get_stream_url(json_data, record_quality, spec=True)
                            else:
                                logger.error(f"错误信息: 网络异常，请检查本网络是否能正常访问FlexTV直播平台")

                    elif record_url.find("look.163.com/") > -1:
                        platform = 'Look直播'
                        with semaphore:
                            port_info = get_looklive_stream_url(
                                url=record_url, proxy_addr=proxy_address, cookies=look_cookie
                            )

                    elif record_url.find("www.popkontv.com/") > -1:
                        platform = 'PopkonTV'
                        with semaphore:
                            if global_proxy or proxy_address:
                                port_info = get_popkontv_stream_url(
                                    url=record_url,
                                    proxy_addr=proxy_address,
                                    access_token=popkontv_access_token,
                                    username=popkontv_username,
                                    password=popkontv_password,
                                    partner_code=popkontv_partner_code
                                )
                            else:
                                logger.error(f"错误信息: 网络异常，请检查本网络是否能正常访问PopkonTV直播平台")

                    elif record_url.find("twitcasting.tv/") > -1:
                        platform = 'TwitCasting'
                        with semaphore:
                            port_info = get_twitcasting_stream_url(
                                url=record_url,
                                proxy_addr=proxy_address,
                                cookies=twitcasting_cookie,
                                account_type=twitcasting_account_type,
                                username=twitcasting_username,
                                password=twitcasting_password
                            )

                    elif record_url.find("live.baidu.com/") > -1:
                        platform = '百度直播'
                        with semaphore:
                            json_data = get_baidu_stream_data(
                                url=record_url,
                                proxy_addr=proxy_address,
                                cookies=baidu_cookie)
                            port_info = get_stream_url(json_data, record_quality)

                    elif record_url.find("weibo.com/") > -1:
                        platform = '微博直播'
                        with semaphore:
                            json_data = get_weibo_stream_data(
                                url=record_url, proxy_addr=proxy_address, cookies=weibo_cookie)
                            port_info = get_stream_url(json_data, record_quality, extra_key='m3u8_url')

                    elif record_url.find("kugou.com/") > -1:
                        platform = '酷狗直播'
                        with semaphore:
                            port_info = get_kugou_stream_url(
                                url=record_url, proxy_addr=proxy_address, cookies=kugou_cookie)

                    elif record_url.find("www.twitch.tv/") > -1:
                        platform = 'TwitchTV'
                        with semaphore:
                            if global_proxy or proxy_address:
                                json_data = get_twitchtv_stream_data(
                                    url=record_url,
                                    proxy_addr=proxy_address,
                                    cookies=twitch_cookie
                                )
                                port_info = get_stream_url(json_data, record_quality, spec=True)
                            else:
                                logger.error(f"错误信息: 网络异常，请检查本网络是否能正常访问TwitchTV直播平台")

                    elif record_url.find("www.liveme.com/") > -1:
                        platform = 'LiveMe'
                        with semaphore:
                            port_info = get_liveme_stream_url(
                                url=record_url, proxy_addr=proxy_address, cookies=liveme_cookie)

                    elif record_url.find("www.huajiao.com/") > -1:
                        platform = '花椒直播'
                        with semaphore:
                            port_info = get_huajiao_stream_url(
                                url=record_url, proxy_addr=proxy_address, cookies=huajiao_cookie)

                    elif record_url.find("7u66.com/") > -1:
                        platform = '流星直播'
                        with semaphore:
                            port_info = get_liuxing_stream_url(
                                url=record_url, proxy_addr=proxy_address, cookies=liuxing_cookie)

                    elif record_url.find("showroom-live.com/") > -1:
                        platform = 'ShowRoom'
                        with semaphore:
                            json_data = get_showroom_stream_data(
                                url=record_url, proxy_addr=proxy_address, cookies=showroom_cookie)
                            port_info = get_stream_url(json_data, record_quality, spec=True)

                    elif record_url.find("live.acfun.cn/") > -1 or record_url.find("m.acfun.cn/") > -1:
                        platform = 'Acfun'
                        with semaphore:
                            json_data = get_acfun_stream_data(
                                url=record_url, proxy_addr=proxy_address, cookies=acfun_cookie)
                            port_info = get_stream_url(json_data, record_quality, url_type='flv', extra_key='url')

                    elif record_url.find("rengzu.com/") > -1:
                        platform = '时光直播'
                        with semaphore:
                            port_info = get_shiguang_stream_url(
                                url=record_url, proxy_addr=proxy_address, cookies=shiguang_cookie)

                    elif record_url.find("ybw1666.com/") > -1:
                        platform = '音播直播'
                        with semaphore:
                            port_info = get_yinbo_stream_url(
                                url=record_url, proxy_addr=proxy_address, cookies=yinbo_cookie)

                    elif record_url.find("www.inke.cn/") > -1:
                        platform = '映客直播'
                        with semaphore:
                            port_info = get_yingke_stream_url(
                                url=record_url, proxy_addr=proxy_address, cookies=yingke_cookie)

                    elif record_url.find("www.zhihu.com/") > -1:
                        platform = '知乎直播'
                        with semaphore:
                            port_info = get_zhihu_stream_url(
                                url=record_url, proxy_addr=proxy_address, cookies=zhihu_cookie)

                    else:
                        logger.error(f'{record_url} 未知直播地址')
                        return

                    if anchor_name:
                        # 第一次从config中读取，带有'主播:'，去除'主播:'
                        # 之后的线程循环，已经是处理后的结果，不需要去处理
                        if '主播:' in anchor_name:
                            anchor_split: list = anchor_name.split('主播:')
                            if len(anchor_split) > 1 and anchor_split[1].strip():
                                anchor_name = anchor_split[1].strip()
                            else:
                                anchor_name = port_info.get("anchor_name", '')
                    else:
                        anchor_name = port_info.get("anchor_name", '')

                    if not port_info.get("anchor_name", ''):
                        print(f'序号{count_variable} 网址内容获取失败,进行重试中...获取失败的地址是:{url_data}')
                        warning_count += 1
                    else:
                        anchor_name = re.sub(rstr, "_", anchor_name)
                        record_name = f'序号{count_variable} {anchor_name}'

                        # print(f"正在录制中!!!!: {anchor_name} {record_url} {url_comments}")
                        if record_url in url_comments:
                            print(f"[{anchor_name}]已被注释,本条线程将会退出")
                            return

                        if anchor_name in recording:
                            print(f"新增的地址: {anchor_name} 已经存在,本条线程将会退出")
                            need_update_line_list.append(f'{record_url}|#{record_url}')
                            return

                        if url_data[-1] == "" and run_once is False:
                            if is_long_url:
                                need_update_line_list.append(
                                    f'{record_url}|{new_record_url},主播: {anchor_name.strip()}')
                            else:
                                need_update_line_list.append(f'{record_url}|{record_url},主播: {anchor_name.strip()}')
                            run_once = True

                        push_at = datetime.datetime.today().strftime('%Y-%m-%d %H:%M:%S')
                        if port_info['is_live'] is False:
                            print(f"\r{record_name} 等待直播... ")

                            if start_pushed:
                                if over_show_push:
                                    push_content = f"直播间状态更新：[直播间名称] 直播已结束！时间：[时间]"
                                    if over_push_message_text:
                                        push_content = over_push_message_text

                                    push_content = (push_content.replace('[直播间名称]', record_name).
                                                    replace('[时间]', push_at))
                                    push_pts = push_message(push_content.replace(r'\n', '\n'))
                                    if push_pts:
                                        print(f'提示信息：已经将[{record_name}]直播状态消息推送至你的{push_pts}')
                                start_pushed = False
                        else:
                            content = f"\r{record_name} 正在直播中..."
                            print(content)

                            if live_status_push and not start_pushed:
                                if begin_show_push:
                                    push_content = f"直播间状态更新：[直播间名称] 正在直播中，时间：[时间]"
                                    if begin_push_message_text:
                                        push_content = begin_push_message_text

                                    push_content = (push_content.replace('[直播间名称]', record_name).
                                                    replace('[时间]', push_at))
                                    push_pts = push_message(push_content.replace(r'\n', '\n'))
                                    if push_pts:
                                        print(f'提示信息：已经将[{record_name}]直播状态消息推送至你的{push_pts}')
                                start_pushed = True

                            if disable_record:
                                time.sleep(push_check_seconds)
                                continue

                            real_url = port_info.get('record_url', None)
                            full_path = f'{default_path}/{platform}'
                            if len(real_url) > 0:
                                now = datetime.datetime.today().strftime("%Y-%m-%d_%H-%M-%S")

                                try:
                                    if len(video_save_path) > 0:
                                        if video_save_path[-1] not in ["/", "\\"]:
                                            video_save_path = video_save_path + "/"
                                        full_path = f'{video_save_path}{platform}'

                                    full_path = full_path.replace("\\", '/')
                                    if folder_by_author:
                                        full_path = f'{full_path}/{anchor_name}'
                                    if folder_by_time:
                                        full_path = f'{full_path}/{now[:10]}'
                                    if not os.path.exists(full_path):
                                        os.makedirs(full_path)
                                except Exception as e:
                                    logger.error(f"错误信息: {e} 发生错误的行数: {e.__traceback__.tb_lineno}")

                                user_agent = ("Mozilla/5.0 (Linux; Android 11; SAMSUNG SM-G973U) AppleWebKit/537.36 ("
                                              "KHTML, like Gecko) SamsungBrowser/14.2 Chrome/87.0.4280.141 Mobile "
                                              "Safari/537.36")

                                rw_timeout = "15000000"
                                analyzeduration = "20000000"
                                probesize = "10000000"
                                bufsize = "8000k"
                                max_muxing_queue_size = "1024"
                                for pt_host in overseas_platform_host:
                                    if pt_host in record_url:
                                        rw_timeout = "50000000"
                                        analyzeduration = "40000000"
                                        probesize = "20000000"
                                        bufsize = "15000k"
                                        max_muxing_queue_size = "2048"
                                        break

                                ffmpeg_command = [
                                    'ffmpeg', "-y",
                                    "-v", "verbose",
                                    "-rw_timeout", rw_timeout,
                                    "-loglevel", "error",
                                    "-hide_banner",
                                    "-user_agent", user_agent,
                                    "-protocol_whitelist", "rtmp,crypto,file,http,https,tcp,tls,udp,rtp",
                                    "-thread_queue_size", "1024",
                                    "-analyzeduration", analyzeduration,
                                    "-probesize", probesize,
                                    "-fflags", "+discardcorrupt",
                                    "-i", real_url,
                                    "-bufsize", bufsize,
                                    "-sn", "-dn",
                                    "-reconnect_delay_max", "60",
                                    "-reconnect_streamed", "-reconnect_at_eof",
                                    "-max_muxing_queue_size", max_muxing_queue_size,
                                    "-correct_ts_overflow", "1",
                                ]

                                add_headers_list = ['PandaTV', '千度热播', 'WinkTV']
                                if platform in add_headers_list:
                                    if platform == 'PandaTV':
                                        headers = 'origin:https://www.pandalive.co.kr'
                                    elif platform == 'WinkTV':
                                        headers = 'origin:https://www.winktv.co.kr'
                                    else:
                                        headers = 'referer:https://qiandurebo.com'
                                    ffmpeg_command.insert(11, "-headers")
                                    ffmpeg_command.insert(12, headers)

                                # 添加代理参数
                                if proxy_address:
                                    ffmpeg_command.insert(1, "-http_proxy")
                                    ffmpeg_command.insert(2, proxy_address)

                                recording.add(record_name)
                                start_record_time = datetime.datetime.now()
                                recording_time_list[record_name] = [start_record_time, record_quality]
                                rec_info = f"\r{anchor_name} 录制视频中: {full_path}"
                                filename_short = full_path + '/' + anchor_name + '_' + now
                                if show_url:
                                    re_plat = ['WinkTV', 'PandaTV', 'ShowRoom']
                                    if platform in re_plat:
                                        logger.info(f"{platform} | {anchor_name} | 直播源地址: {port_info['m3u8_url']}")
                                    else:
                                        logger.info(
                                            f"{platform} | {anchor_name} | 直播源地址: {port_info['record_url']}")

                                if video_save_type == "FLV":
                                    filename = anchor_name + '_' + now + '.flv'
                                    print(f'{rec_info}/{filename}')

                                    if create_time_file:
                                        filename_group = [anchor_name, filename_short]
                                        create_var[str(filename_short)] = threading.Thread(target=create_ass_file,
                                                                                           args=(filename_group,))
                                        create_var[str(filename_short)].daemon = True
                                        create_var[str(filename_short)].start()

                                    try:
                                        flv_url = port_info.get('flv_url', None)
                                        if flv_url:
                                            _filepath, _ = urllib.request.urlretrieve(real_url,
                                                                                      f'{full_path}/{filename}')
                                            record_finished = True
                                    except Exception as e:
                                        logger.error(f"错误信息: {e} 发生错误的行数: {e.__traceback__.tb_lineno}")
                                        warning_count += 1
                                        no_error = False

                                elif video_save_type == "MKV":
                                    filename = anchor_name + '_' + now + ".mkv"
                                    print(f'{rec_info}/{filename}')
                                    save_file_path = full_path + '/' + filename

                                    try:
                                        if split_video_by_time:
                                            now = time.strftime("%Y-%m-%d_%H-%M-%S", time.localtime())
                                            save_file_path = f"{full_path}/{anchor_name}_{now}_%03d.mkv"
                                            command = [
                                                "-flags", "global_header",
                                                "-c:v", "copy",
                                                "-c:a", "aac",
                                                "-map", "0",
                                                "-f", "segment",
                                                "-segment_time", split_time,
                                                "-segment_format", "matroska",
                                                "-reset_timestamps", "1",
                                                save_file_path,
                                            ]

                                        else:
                                            if create_time_file:
                                                filename_group = [anchor_name, filename_short]
                                                create_var[str(filename_short)] = threading.Thread(
                                                    target=create_ass_file,
                                                    args=(filename_group,))
                                                create_var[str(filename_short)].daemon = True
                                                create_var[str(filename_short)].start()

                                            command = [
                                                "-flags", "global_header",
                                                "-map", "0",
                                                "-c:v", "copy",
                                                "-c:a", "copy",
                                                "-f", "matroska",
                                                "{path}".format(path=save_file_path),
                                            ]
                                        ffmpeg_command.extend(command)

                                        comment_end = check_subprocess(
                                            record_name,
                                            anchor_name,
                                            record_url,
                                            ffmpeg_command
                                        )
                                        if comment_end:
                                            return

                                    except subprocess.CalledProcessError as e:
                                        logger.error(f"错误信息: {e} 发生错误的行数: {e.__traceback__.tb_lineno}")
                                        warning_count += 1
                                        no_error = False

                                elif video_save_type == "MP4":
                                    filename = anchor_name + '_' + now + ".mp4"
                                    print(f'{rec_info}/{filename}')
                                    save_file_path = full_path + '/' + filename

                                    try:
                                        if split_video_by_time:
                                            now = time.strftime("%Y-%m-%d_%H-%M-%S", time.localtime())
                                            save_file_path = f"{full_path}/{anchor_name}_{now}_%03d.mp4"
                                            command = [
                                                "-c:v", "copy",
                                                "-c:a", "aac",
                                                "-map", "0",
                                                "-f", "segment",
                                                "-segment_time", split_time,
                                                "-segment_format", "mp4",
                                                "-reset_timestamps", "1",
                                                "-movflags", "+frag_keyframe+empty_moov",
                                                save_file_path,
                                            ]

                                        else:
                                            if create_time_file:
                                                filename_group = [anchor_name, filename_short]
                                                create_var[str(filename_short)] = threading.Thread(
                                                    target=create_ass_file,
                                                    args=(filename_group,))
                                                create_var[str(filename_short)].daemon = True
                                                create_var[str(filename_short)].start()

                                            command = [
                                                "-map", "0",
                                                "-c:v", "copy",
                                                "-c:a", "copy",
                                                "-f", "mp4",
                                                "{path}".format(path=save_file_path),
                                            ]

                                        ffmpeg_command.extend(command)
                                        comment_end = check_subprocess(
                                            record_name,
                                            anchor_name,
                                            record_url,
                                            ffmpeg_command
                                        )
                                        if comment_end:
                                            return

                                    except subprocess.CalledProcessError as e:
                                        logger.error(f"错误信息: {e} 发生错误的行数: {e.__traceback__.tb_lineno}")
                                        warning_count += 1
                                        no_error = False

                                elif video_save_type == "MKV音频":
                                    try:
                                        if split_video_by_time:
                                            now = time.strftime("%Y-%m-%d_%H-%M-%S", time.localtime())
                                            filename = anchor_name + '_' + now + ".mkv"
                                            print(f'{rec_info}/{filename}')

                                            if ts_to_mp3:
                                                save_path_name = f"{full_path}/{anchor_name}_{now}_%03d.mp3"
                                            else:
                                                save_path_name = f"{full_path}/{anchor_name}_{now}_%03d.mkv"

                                            command = [
                                                "-map", "0:a",
                                                "-c:a", 'copy',
                                                "-f", "segment",
                                                "-segment_time", split_time,
                                                "-segment_format", 'mpegts',
                                                "-reset_timestamps", "1",
                                                save_path_name,
                                            ]
                                            ffmpeg_command.extend(command)
                                            comment_end = check_subprocess(
                                                record_name,
                                                anchor_name,
                                                record_url,
                                                ffmpeg_command
                                            )
                                            if comment_end:
                                                threading.Thread(target=converts_m4a, args=(save_path_name,)).start()
                                                return

                                        else:
                                            filename = anchor_name + '_' + now + ".mkv"
                                            print(f'{rec_info}/{filename}')
                                            save_file_path = full_path + '/' + filename

                                            command = [
                                                "-map", "0:a",
                                                "-c:a", "copy",
                                                "-f", "segment",
                                                "-segment_time", split_time,
                                                "-segment_format", "matroska",
                                                "-reset_timestamps", "1",
                                                save_file_path,
                                            ]

                                            ffmpeg_command.extend(command)
                                            comment_end = check_subprocess(
                                                record_name,
                                                anchor_name,
                                                record_url,
                                                ffmpeg_command,
                                            )
                                            if comment_end:
                                                threading.Thread(target=converts_m4a, args=(save_file_path,)).start()
                                                return

                                    except subprocess.CalledProcessError as e:
                                        logger.error(f"错误信息: {e} 发生错误的行数: {e.__traceback__.tb_lineno}")
                                        warning_count += 1
                                        no_error = False

                                elif video_save_type == "TS音频":
                                    try:
                                        if split_video_by_time:
                                            now = time.strftime("%Y-%m-%d_%H-%M-%S", time.localtime())
                                            filename = anchor_name + '_' + now + ".ts"
                                            print(f'{rec_info}/{filename}')

                                            if ts_to_mp3:
                                                save_path_name = f"{full_path}/{anchor_name}_{now}_%03d.mp3"
                                            else:
                                                save_path_name = f"{full_path}/{anchor_name}_{now}_%03d.ts"

                                            command = [
                                                "-map", "0:a",
                                                "-c:a", 'copy',
                                                "-f", "segment",
                                                "-segment_time", split_time,
                                                "-segment_format", 'mpegts',
                                                "-reset_timestamps", "1",
                                                save_path_name,
                                            ]
                                            ffmpeg_command.extend(command)
                                            comment_end = check_subprocess(
                                                record_name,
                                                anchor_name,
                                                record_url,
                                                ffmpeg_command,
                                            )
                                            if comment_end:
                                                threading.Thread(target=converts_m4a, args=(save_path_name,)).start()
                                                return

                                        else:
                                            filename = anchor_name + '_' + now + ".ts"
                                            print(f'{rec_info}/{filename}')
                                            save_file_path = full_path + '/' + filename

                                            command = [
                                                "-map", "0:a",
                                                "-c:a", "copy",
                                                "-f", "mpegts",
                                                "{path}".format(path=save_file_path),
                                            ]

                                            ffmpeg_command.extend(command)
                                            comment_end = check_subprocess(
                                                record_name,
                                                anchor_name,
                                                record_url,
                                                ffmpeg_command,
                                            )
                                            if comment_end:
                                                threading.Thread(target=converts_m4a, args=(save_file_path,)).start()
                                                return

                                    except subprocess.CalledProcessError as e:
                                        logger.error(f"错误信息: {e} 发生错误的行数: {e.__traceback__.tb_lineno}")
                                        warning_count += 1
                                        no_error = False

                                else:
                                    if split_video_by_time:
                                        now = time.strftime("%Y-%m-%d_%H-%M-%S", time.localtime())
                                        filename = anchor_name + '_' + now + ".ts"
                                        print(f'{rec_info}/{filename}')

                                        try:
                                            save_path_name = f"{full_path}/{anchor_name}_{now}_%03d.ts"
                                            command = [
                                                "-c:v", "copy",
                                                "-c:a", "copy",
                                                "-map", "0",
                                                "-f", "segment",
                                                "-segment_time", split_time,
                                                "-segment_format", 'mpegts',
                                                "-reset_timestamps", "1",
                                                save_path_name,
                                            ]

                                            ffmpeg_command.extend(command)
                                            comment_end = check_subprocess(
                                                record_name,
                                                anchor_name,
                                                record_url,
                                                ffmpeg_command,
                                            )
                                            if comment_end:
                                                if ts_to_mp4:
                                                    file_paths = get_file_paths(os.path.dirname(save_path_name))
                                                    prefix = os.path.basename(save_path_name).rsplit('_', maxsplit=1)[0]
                                                    for path in file_paths:
                                                        if prefix in path:
                                                            threading.Thread(target=converts_mp4, args=(path,)).start()
                                                return

                                        except subprocess.CalledProcessError as e:
                                            logger.error(
                                                f"错误信息: {e} 发生错误的行数: {e.__traceback__.tb_lineno}")
                                            warning_count += 1
                                            no_error = False

                                    else:
                                        filename = anchor_name + '_' + now + ".ts"
                                        print(f'{rec_info}/{filename}')
                                        save_file_path = full_path + '/' + filename

                                        if create_time_file:
                                            filename_group = [anchor_name, filename_short]
                                            create_var[str(filename_short)] = threading.Thread(target=create_ass_file,
                                                                                               args=(filename_group,))
                                            create_var[str(filename_short)].daemon = True
                                            create_var[str(filename_short)].start()

                                        try:
                                            command = [
                                                "-c:v", "copy",
                                                "-c:a", "copy",
                                                "-map", "0",
                                                "-f", "mpegts",
                                                "{path}".format(path=save_file_path),
                                            ]

                                            ffmpeg_command.extend(command)
                                            comment_end = check_subprocess(
                                                record_name,
                                                anchor_name,
                                                record_url,
                                                ffmpeg_command
                                            )
                                            if comment_end:
                                                threading.Thread(target=converts_mp4, args=(save_file_path,)).start()
                                                return

                                        except subprocess.CalledProcessError as e:
                                            logger.error(f"错误信息: {e} 发生错误的行数: {e.__traceback__.tb_lineno}")
                                            warning_count += 1
                                            no_error = False

                                record_finished_2 = True
                                count_time = time.time()

                            if record_finished_2:
                                clear_record_info(record_name, anchor_name, record_url)

                                if no_error:
                                    print(f"\n{anchor_name} {time.strftime('%Y-%m-%d %H:%M:%S')} 直播录制完成\n")
                                else:
                                    print(
                                        f"\n{anchor_name} {time.strftime('%Y-%m-%d %H:%M:%S')} 直播录制出错,请检查网络\n")

                                record_finished_2 = False

                except Exception as e:
                    logger.error(f"错误信息: {e} 发生错误的行数: {e.__traceback__.tb_lineno}")
                    warning_count += 1

                num = random.randint(-5, 5) + delay_default
                if num < 0:
                    num = 0
                x = num

                if warning_count > 20:
                    x = x + 60
                    print("瞬时错误太多,延迟加60秒")

                # 这里是.如果录制结束后,循环时间会暂时变成30s后检测一遍. 这样一定程度上防止主播卡顿造成少录
                # 当30秒过后检测一遍后. 会回归正常设置的循环秒数
                if record_finished:
                    count_time_end = time.time() - count_time
                    if count_time_end < 60:
                        x = 30
                    record_finished = False

                else:
                    x = num

                # 这里是正常循环
                while x:
                    x = x - 1
                    if loop_time:
                        print(f'\r{anchor_name}循环等待{x}秒 ', end="")
                    time.sleep(1)
                if loop_time:
                    print('\r检测直播间中...', end="")
        except Exception as e:
            logger.error(f"错误信息: {e} 发生错误的行数: {e.__traceback__.tb_lineno}")
            warning_count += 1
            time.sleep(2)


def backup_file(file_path: str, backup_dir_path: str):
    try:
        if not os.path.exists(backup_dir_path):
            os.makedirs(backup_dir_path)

        timestamp = datetime.datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
        backup_file_name = os.path.basename(file_path) + '_' + timestamp

        backup_file_path = os.path.join(backup_dir_path, backup_file_name).replace("\\", "/")
        shutil.copy2(file_path, backup_file_path)
        # print(f'\r已备份配置文件 {file_path} 到 {backup_file_path}')

        files = os.listdir(backup_dir_path)
        url_files = [f for f in files if f.startswith(os.path.basename(url_config_file))]
        config_files = [f for f in files if f.startswith(os.path.basename(config_file))]

        url_files.sort(key=lambda x: os.path.getmtime(os.path.join(backup_dir_path, x)))
        config_files.sort(key=lambda x: os.path.getmtime(os.path.join(backup_dir_path, x)))

        while len(url_files) > 6:
            oldest_file = url_files[0]
            os.remove(os.path.join(backup_dir_path, oldest_file))
            url_files = url_files[1:]

        while len(config_files) > 6:
            oldest_file = config_files[0]
            os.remove(os.path.join(backup_dir_path, oldest_file))
            config_files = config_files[1:]

    except Exception as e:
        logger.error(f'\r备份配置文件 {file_path} 失败：{str(e)}')


def backup_file_start():
    config_md5 = ''
    url_config_md5 = ''

    while True:
        try:
            if os.path.exists(config_file):
                new_config_md5 = check_md5(config_file)
                if new_config_md5 != config_md5:
                    backup_file(config_file, backup_dir)
                    config_md5 = new_config_md5

            if os.path.exists(url_config_file):
                new_url_config_md5 = check_md5(url_config_file)
                if new_url_config_md5 != url_config_md5:
                    backup_file(url_config_file, backup_dir)
                    url_config_md5 = new_url_config_md5
            time.sleep(600)
        except Exception as e:
            logger.error(f'执行脚本异常：{str(e)}')


# --------------------------检查是否存在ffmpeg-------------------------------------
def check_ffmpeg_existence():
    dev_null = open(os.devnull, 'wb')
    try:
        subprocess.run(['ffmpeg', '--help'], stdout=dev_null, stderr=dev_null, check=True)
    except subprocess.CalledProcessError as e:
        logger.error(e)
        return False
    except FileNotFoundError:
        ffmpeg_file_check = subprocess.getoutput(ffmpeg_path)
        if ffmpeg_file_check.find("run") > -1 and os.path.isfile(ffmpeg_path):
            os.environ['PATH'] += os.pathsep + os.path.dirname(os.path.abspath(ffmpeg_path))
            # print(f"已将ffmpeg路径添加到环境变量：{ffmpeg_path}")
            return True
        else:
            logger.error("检测到ffmpeg不存在,请将ffmpeg.exe放到同目录,或者设置为环境变量,没有ffmpeg将无法录制")
            sys.exit(0)
    finally:
        dev_null.close()
    return True


if not check_ffmpeg_existence():
    logger.error("ffmpeg检查失败，程序将退出。")
    sys.exit(1)

# --------------------------初始化程序-------------------------------------
print("-----------------------------------------------------")
print("|                DouyinLiveRecorder                 |")
print("-----------------------------------------------------")

print(f"版本号: {version}")
print(f"GitHub: https://github.com/ihmily/DouyinLiveRecorder")
print(f'支持平台: {platforms}')
print('.....................................................')

os.makedirs(os.path.dirname(config_file), exist_ok=True)
t3 = threading.Thread(target=backup_file_start, args=(), daemon=True)
t3.start()


def read_config_value(config_parser: configparser.RawConfigParser, section: str, option: str, default_value: Any) \
        -> Union[str, int, bool]:
    try:

        config_parser.read(config_file, encoding=text_encoding)
        if '录制设置' not in config_parser.sections():
            config_parser.add_section('录制设置')
        if '推送配置' not in config_parser.sections():
            config_parser.add_section('推送配置')
        if 'Cookie' not in config_parser.sections():
            config_parser.add_section('Cookie')
        if 'Authorization' not in config_parser.sections():
            config_parser.add_section('Authorization')
        if '账号密码' not in config_parser.sections():
            config_parser.add_section('账号密码')
        return config_parser.get(section, option)
    except (configparser.NoSectionError, configparser.NoOptionError):
        config_parser.set(section, option, str(default_value))
        with open(config_file, 'w', encoding=text_encoding) as f:
            config_parser.write(f)
        return default_value


options = {"是": True, "否": False}

config = configparser.RawConfigParser()
skip_proxy_check = options.get(read_config_value(config, '录制设置', '是否跳过代理检测（是/否）', "否"), False)

try:
    if skip_proxy_check:
        global_proxy = True
    else:
        print('系统代理检测中，请耐心等待...')
        response_g = urllib.request.urlopen("https://www.google.com/", timeout=15)
        global_proxy = True
        print('\r全局/规则网络代理已开启√')
except HTTPError as err:
    print(f"HTTP error occurred: {err.code} - {err.reason}")
except URLError as err:
    # print("URLError:", err.reason)
    print('INFO：未检测到全局/规则网络代理，请检查代理配置（若无需录制海外直播请忽略此条提示）')
except Exception as err:
    print("An unexpected error occurred:", err)

while True:

    try:
        if not os.path.isfile(config_file):
            with open(config_file, 'w', encoding=text_encoding) as file:
                pass

        ini_URL_content = ''
        if os.path.isfile(url_config_file):
            with open(url_config_file, 'r', encoding=text_encoding) as file:
                ini_URL_content = file.read().strip()

        if not ini_URL_content.strip():
            input_url = input('请输入要录制的主播直播间网址（尽量使用PC网页端的直播间地址）:\n')
            with open(url_config_file, 'w', encoding=text_encoding) as file:
                file.write(input_url)
    except OSError as err:
        logger.error(f"发生 I/O 错误: {err}")

    video_save_path = read_config_value(config, '录制设置', '直播保存路径（不填则默认）', "")
    folder_by_author = options.get(read_config_value(config, '录制设置', '保存文件夹是否以作者区分', "是"), False)
    folder_by_time = options.get(read_config_value(config, '录制设置', '保存文件夹是否以时间区分', "否"), False)
    video_save_type = read_config_value(config, '录制设置', '视频保存格式ts|mkv|flv|mp4|ts音频|mkv音频', "ts")
    video_record_quality = read_config_value(config, '录制设置', '原画|超清|高清|标清|流畅', "原画")
    use_proxy = options.get(read_config_value(config, '录制设置', '是否使用代理ip（是/否）', "是"), False)
    proxy_addr_bak = read_config_value(config, '录制设置', '代理地址', "")
    proxy_addr = None if not use_proxy else proxy_addr_bak
    max_request = int(read_config_value(config, '录制设置', '同一时间访问网络的线程数', 3))
    semaphore = threading.Semaphore(max_request)
    delay_default = int(read_config_value(config, '录制设置', '循环时间(秒)', 120))
    local_delay_default = int(read_config_value(config, '录制设置', '排队读取网址时间(秒)', 0))
    loop_time = options.get(read_config_value(config, '录制设置', '是否显示循环秒数', "否"), False)
    show_url = options.get(read_config_value(config, '录制设置', '是否显示直播源地址', "否"), False)
    split_video_by_time = options.get(read_config_value(config, '录制设置', '分段录制是否开启', "否"), False)
    split_time = str(read_config_value(config, '录制设置', '视频分段时间(秒)', 1800))
    ts_to_mp4 = options.get(read_config_value(config, '录制设置', 'ts录制完成后自动转为mp4格式', "否"),
                            False)
    ts_to_m4a = options.get(read_config_value(config, '录制设置', 'ts录制完成后自动增加生成m4a格式', "否"),
                            False)
    ts_to_mp3 = options.get(read_config_value(config, '录制设置', '音频录制完成后自动转为mp3格式', "否"),
                            False)
    delete_origin_file = options.get(read_config_value(config, '录制设置', '追加格式后删除原文件', "否"), False)
    create_time_file = options.get(read_config_value(config, '录制设置', '生成时间文件', "否"), False)
    enable_proxy_platform = read_config_value(
        config, '录制设置', '使用代理录制的平台（逗号分隔）',
        'tiktok, afreecatv, pandalive, winktv, flextv, popkontv, twitch, showroom')
    enable_proxy_platform_list = enable_proxy_platform.replace('，', ',').split(',') if enable_proxy_platform else None
    extra_enable_proxy = read_config_value(config, '录制设置', '额外使用代理录制的平台（逗号分隔）', '')
    extra_enable_proxy_platform_list = extra_enable_proxy.replace('，', ',').split(',') if extra_enable_proxy else None
    live_status_push = read_config_value(config, '推送配置', '直播状态通知(可选微信|钉钉|tg|邮箱|bark或者都填)', "")
    dingtalk_api_url = read_config_value(config, '推送配置', '钉钉推送接口链接', "")
    xizhi_api_url = read_config_value(config, '推送配置', '微信推送接口链接', "")
    bark_msg_api = read_config_value(config, '推送配置', 'bark推送接口链接', "")
    bark_msg_level = read_config_value(config, '推送配置', 'bark推送中断级别', "active")
    bark_msg_ring = read_config_value(config, '推送配置', 'bark推送铃声', "bell")
    dingtalk_phone_num = read_config_value(config, '推送配置', '钉钉通知@对象(填手机号)', "")
    tg_token = read_config_value(config, '推送配置', 'tgapi令牌', "")
    tg_chat_id = read_config_value(config, '推送配置', 'tg聊天id(个人或者群组id)', "")
    mail_host = read_config_value(config, '推送配置', 'SMTP邮件服务器', "")
    from_email = read_config_value(config, '推送配置', '发件人邮箱', "")
    mail_password = read_config_value(config, '推送配置', '发件人密码(授权码)', "")
    to_email = read_config_value(config, '推送配置', '收件人邮箱', "")
    begin_push_message_text = read_config_value(config, '推送配置', '自定义开播推送内容', "")
    over_push_message_text = read_config_value(config, '推送配置', '自定义关播推送内容', "")
    disable_record = options.get(read_config_value(config, '推送配置', '只推送通知不录制（是/否）', "否"), False)
    push_check_seconds = int(read_config_value(config, '推送配置', '直播推送检测频率（秒）', 1800))
    begin_show_push = options.get(read_config_value(config, '推送配置', '开播推送开启（是/否）', "是"), True)
    over_show_push = options.get(read_config_value(config, '推送配置', '关播推送开启（是/否）', "否"), False)
    afreecatv_username = read_config_value(config, '账号密码', 'afreecatv账号', '')
    afreecatv_password = read_config_value(config, '账号密码', 'afreecatv密码', '')
    flextv_username = read_config_value(config, '账号密码', 'flextv账号', '')
    flextv_password = read_config_value(config, '账号密码', 'flextv密码', '')
    popkontv_username = read_config_value(config, '账号密码', 'popkontv账号', '')
    popkontv_partner_code = read_config_value(config, '账号密码', 'partner_code', 'P-00001')
    popkontv_password = read_config_value(config, '账号密码', 'popkontv密码', '')
    twitcasting_account_type = read_config_value(config, '账号密码', 'twitcasting账号类型', 'normal')
    twitcasting_username = read_config_value(config, '账号密码', 'twitcasting账号', '')
    twitcasting_password = read_config_value(config, '账号密码', 'twitcasting密码', '')
    popkontv_access_token = read_config_value(config, 'Authorization', 'popkontv_token', '')
    dy_cookie = read_config_value(config, 'Cookie', '抖音cookie(录制抖音必须要有)', '')
    ks_cookie = read_config_value(config, 'Cookie', '快手cookie', '')
    tiktok_cookie = read_config_value(config, 'Cookie', 'tiktok_cookie', '')
    hy_cookie = read_config_value(config, 'Cookie', '虎牙cookie', '')
    douyu_cookie = read_config_value(config, 'Cookie', '斗鱼cookie', '')
    yy_cookie = read_config_value(config, 'Cookie', 'yy_cookie', '')
    bili_cookie = read_config_value(config, 'Cookie', 'B站cookie', '')
    xhs_cookie = read_config_value(config, 'Cookie', '小红书cookie', '')
    bigo_cookie = read_config_value(config, 'Cookie', 'bigo_cookie', '')
    blued_cookie = read_config_value(config, 'Cookie', 'blued_cookie', '')
    afreecatv_cookie = read_config_value(config, 'Cookie', 'afreecatv_cookie', '')
    netease_cookie = read_config_value(config, 'Cookie', 'netease_cookie', '')
    qiandurebo_cookie = read_config_value(config, 'Cookie', '千度热播_cookie', '')
    pandatv_cookie = read_config_value(config, 'Cookie', 'pandatv_cookie', '')
    maoerfm_cookie = read_config_value(config, 'Cookie', '猫耳fm_cookie', '')
    winktv_cookie = read_config_value(config, 'Cookie', 'winktv_cookie', '')
    flextv_cookie = read_config_value(config, 'Cookie', 'flextv_cookie', '')
    look_cookie = read_config_value(config, 'Cookie', 'look_cookie', '')
    twitcasting_cookie = read_config_value(config, 'Cookie', 'twitcasting_cookie', '')
    baidu_cookie = read_config_value(config, 'Cookie', 'baidu_cookie', '')
    weibo_cookie = read_config_value(config, 'Cookie', 'weibo_cookie', '')
    kugou_cookie = read_config_value(config, 'Cookie', 'kugou_cookie', '')
    twitch_cookie = read_config_value(config, 'Cookie', 'twitch_cookie', '')
    liveme_cookie = read_config_value(config, 'Cookie', 'liveme_cookie', '')
    huajiao_cookie = read_config_value(config, 'Cookie', 'huajiao_cookie', '')
    liuxing_cookie = read_config_value(config, 'Cookie', 'liuxing_cookie', '')
    showroom_cookie = read_config_value(config, 'Cookie', 'showroom_cookie', '')
    acfun_cookie = read_config_value(config, 'Cookie', 'acfun_cookie', '')
    shiguang_cookie = read_config_value(config, 'Cookie', 'shiguang_cookie', '')
    yinbo_cookie = read_config_value(config, 'Cookie', 'yinbo_cookie', '')
    yingke_cookie = read_config_value(config, 'Cookie', 'yingke_cookie', '')
    zhihu_cookie = read_config_value(config, 'Cookie', 'zhihu_cookie', '')

    video_save_type_list = ["FLV", "MKV", "TS", "MP4", "TS音频", "MKV音频"]
    if video_save_type and video_save_type.upper() in video_save_type_list:
        video_save_type = video_save_type.upper()
    else:
        video_save_type = "TS"


    def transform_int_to_time(seconds: int) -> str:
        m, s = divmod(seconds, 60)
        h, m = divmod(m, 60)
        return f"{h}:{m:02d}:{s:02d}"


    def contains_url(string: str) -> bool:
        pattern = (r"(http:\/\/www\.|https:\/\/www\.|http:\/\/|https:\/\/)?[a-zA-Z0-9][a-zA-Z0-9\-]+(\.["
                   r"a-zA-Z0-9\-]+)*\.[a-zA-Z]{2,10}(:[0-9]{1,5})?(\/.*)?$")
        return re.search(pattern, string) is not None


    try:
        url_comments = []
        with (open(url_config_file, "r", encoding=text_encoding, errors='ignore') as file):
            for line in file:
                line = line.strip()
                if len(line) < 20:
                    continue

                is_comment_line = line.startswith("#")
                if is_comment_line:
                    line = line[1:]

                if re.search('[,，]', line):
                    split_line = re.split('[,，]', line)
                else:
                    split_line = [line, '']

                if len(split_line) == 1:
                    url = split_line[0]
                    quality, name = [video_record_quality, '']
                elif len(split_line) == 2:
                    if contains_url(split_line[0]):
                        quality = video_record_quality
                        url, name = split_line
                    else:
                        quality, url = split_line
                        name = ''
                else:
                    quality, url, name = split_line

                if quality not in ["原画", "蓝光", "超清", "高清", "标清", "流畅"]:
                    quality = '原画'

                if ('http://' not in url) and ('https://' not in url):
                    url = 'https://' + url

                url_host = url.split('/')[2]
                platform_host = [
                    'live.douyin.com',
                    'v.douyin.com',
                    'live.kuaishou.com',
                    'www.huya.com',
                    'www.douyu.com',
                    'www.yy.com',
                    'live.bilibili.com',
                    'www.redelight.cn',
                    'www.xiaohongshu.com',
                    'xhslink.com',
                    'www.bigo.tv',
                    'slink.bigovideo.tv',
                    'app.blued.cn',
                    'cc.163.com',
                    'qiandurebo.com',
                    'fm.missevan.com',
                    'look.163.com',
                    'twitcasting.tv',
                    'live.baidu.com',
                    'weibo.com',
                    'fanxing.kugou.com',
                    'fanxing2.kugou.com',
                    'mfanxing.kugou.com',
                    'www.liveme.com',
                    'www.huajiao.com',
                    'www.7u66.com',
                    'wap.7u66.com',
                    'live.acfun.cn',
                    'm.acfun.cn',
                    'www.rengzu.com',
                    'wap.rengzu.com',
                    'www.ybw1666.com',
                    'wap.ybw1666.com',
                    'www.inke.cn',
                    'www.zhihu.com'
                ]
                overseas_platform_host = [
                    'www.tiktok.com',
                    'play.afreecatv.com',
                    'm.afreecatv.com',
                    'www.pandalive.co.kr',
                    'www.winktv.co.kr',
                    'www.flextv.co.kr',
                    'www.popkontv.com',
                    'www.twitch.tv',
                    'www.showroom-live.com'
                ]

                platform_host.extend(overseas_platform_host)
                clean_url_host_list = [
                    "live.douyin.com",
                    "live.bilibili.com",
                    "www.huajiao.com",
                    "www.zhihu.com",
                    "www.xiaohongshu.com",
                    "www.redelight.cn",
                    "www.huya.com"
                ]
                if url_host in platform_host:
                    if url_host in clean_url_host_list:
                        update_file(url_config_file, url, url.split('?')[0])
                        url = url.split('?')[0]

                    new_line = (quality, url, name)
                    if is_comment_line:
                        url_comments.append(url)
                    else:
                        url_tuples_list.append(new_line)
                else:
                    print(f"\r{url} 未知链接.此条跳过")
                    update_file(url_config_file, url, url, start_str='#')

        while len(need_update_line_list):
            a = need_update_line_list.pop()
            replace_words = a.split('|')
            if replace_words[0] != replace_words[1]:
                if replace_words[1].startswith("#"):
                    start_with = '#'
                    new_word = replace_words[1][1:]
                else:
                    start_with = None
                    new_word = replace_words[1]
                update_file(url_config_file, replace_words[0], new_word, start_str=start_with)

        text_no_repeat_url = list(set(url_tuples_list))

        if len(text_no_repeat_url) > 0:
            for url_tuple in text_no_repeat_url:
                monitoring = len(running_list)

                if url_tuple[1] in not_record_list:
                    continue

                if url_tuple[1] not in running_list:

                    if not first_start:
                        print(f"\r新增链接: {url_tuple[1]}")
                    monitoring += 1
                    args = [url_tuple, monitoring]
                    create_var['thread' + str(monitoring)] = threading.Thread(target=start_record, args=args)
                    create_var['thread' + str(monitoring)].daemon = True
                    create_var['thread' + str(monitoring)].start()
                    running_list.append(url_tuple[1])
                    time.sleep(local_delay_default)
        url_tuples_list = []
        first_start = False

    except Exception as err:
        logger.error(f"错误信息: {err} 发生错误的行数: {err.__traceback__.tb_lineno}")

    if first_run:
        t = threading.Thread(target=display_info, args=(), daemon=True)
        t.start()
        t2 = threading.Thread(target=change_max_connect, args=(), daemon=True)
        t2.start()

        first_run = False

    time.sleep(3)
