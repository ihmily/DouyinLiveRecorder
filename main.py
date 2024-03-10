# -*- encoding: utf-8 -*-

"""
Author: Hmily
GitHub: https://github.com/ihmily
Date: 2023-07-17 23:52:05
Update: 2024-03-11 00:42:11
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
from typing import Any, Union
import configparser

from spider import (
    get_douyin_stream_data,
    get_tiktok_stream_data,
    get_kuaishou_stream_data,
    get_huya_stream_data,
    get_douyu_info_data,
    get_douyu_stream_data,
    get_yy_stream_data,
    get_bilibili_stream_data,
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
    get_twitcasting_stream_url
)

from web_rid import (
    get_live_room_id,
    get_sec_user_id
)
from utils import (
    logger, check_md5,
    trace_error_decorator
)
from msg_push import dingtalk, xizhi, tg_bot

version = "v3.0.2"
platforms = "\n国内站点：抖音|快手|虎牙|斗鱼|YY|B站|小红书|bigo直播|blued直播|网易CC|千度热播|猫耳FM|Look直播|TwitCasting" \
            "\n海外站点：TikTok|AfreecaTV|PandaTV|WinkTV|FlexTV|PopkonTV"

# --------------------------全局变量-------------------------------------
recording = set()
unrecording = set()
warning_count = 0
max_request = 0
monitoring = 0
runing_list = []
url_tuples_list = []
text_no_repeat_url = []
create_var = locals()
first_start = True
name_list = []
first_run = True
live_list = []
not_record_list = []
start_display_time = datetime.datetime.now()
global_proxy = False
recording_time_list = {}
config_file = './config/config.ini'
url_config_file = './config/URL_config.ini'
backup_dir = './backup_config'
encoding = 'utf-8-sig'
rstr = r"[\/\\\:\*\?\"\<\>\|&.。,，]"
ffmpeg_path = "ffmpeg"  # ffmpeg文件路径
default_path = os.getcwd() + '/downloads'
os.makedirs(default_path, exist_ok=True)


# --------------------------用到的函数-------------------------------------
def signal_handler(_signal, _frame):
    sys.exit(0)


signal.signal(signal.SIGTERM, signal_handler)


def display_info():
    # TODO: 显示当前录制配置信息
    global start_display_time
    global recording_time_list
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

            if len(recording) == 0 and len(unrecording) == 0:
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
                        print(f"{recording_live}[{qa}] 正在录制中 " + str(have_record_time).split('.')[0])

                    # print('\n本软件已运行：'+str(now_time - start_display_time).split('.')[0])
                    print("x" * 60)
                else:
                    start_display_time = now_time
        except Exception as e:
            logger.warning(f"错误信息: {e} 发生错误的行数: {e.__traceback__.tb_lineno}")


def update_file(file_path: str, old_str: str, new_str: str, start_str: str = None):
    # TODO: 更新文件操作
    file_data = ""
    with open(file_path, "r", encoding="utf-8-sig") as f:
        for text_line in f:
            if old_str in text_line:
                text_line = text_line.replace(old_str, new_str)
                if start_str:
                    text_line = f'{start_str}{text_line}'

            file_data += text_line
    with open(file_path, "w", encoding="utf-8-sig") as f:
        f.write(file_data)


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


def create_ass_file(filegruop: list):
    # TODO:  录制时生成ass格式的字幕文件
    anchor_name = filegruop[0]
    ass_filename = filegruop[1]
    index_time = -1
    finish = 0
    today = datetime.datetime.now()
    re_datatime = today.strftime('%Y-%m-%d %H:%M:%S')

    while True:
        index_time += 1
        txt = str(index_time) + "\n" + transform_int_to_time(index_time) + ',000 --> ' + transform_int_to_time(
            index_time + 1) + ',000' + "\n" + str(re_datatime) + "\n"

        with open(ass_filename + ".ass", 'a', encoding='utf8') as f:
            f.write(txt)

        if anchor_name not in recording:
            finish += 1
            offset = datetime.timedelta(seconds=1)
            # 获取修改后的时间并格式化
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
    # 动态控制连接次数
    preset = max_request
    # 记录当前时间
    start_time = time.time()

    while True:
        time.sleep(5)
        if 10 <= warning_count <= 20:
            if preset > 5:
                max_request = 5
            else:
                max_request //= 2  # 将max_request除以2（向下取整）
                if max_request > 0:  # 如果得到的结果大于0，则直接取该结果
                    max_request = preset
                else:  # 否则将其设置为1
                    preset = 1

            print("同一时间访问网络的线程数动态改为", max_request)
            warning_count = 0
            time.sleep(5)

        elif 20 < warning_count:
            max_request = 1
            print("同一时间访问网络的线程数动态改为", max_request)
            warning_count = 0
            time.sleep(10)

        elif warning_count < 10 and time.time() - start_time > 60:
            max_request = preset
            warning_count = 0
            start_time = time.time()
            print("同一时间访问网络的线程数动态改为", max_request)


@trace_error_decorator
def get_douyin_stream_url(json_data: dict, video_quality: str) -> dict:
    # TODO: 获取抖音直播源地址

    anchor_name = json_data.get('anchor_name', None)

    result = {
        "anchor_name": anchor_name,
        "is_live": False,
    }

    status = json_data.get("status", 4)  # 直播状态 2 是正在直播、4 是未开播

    if status == 2:
        stream_url = json_data['stream_url']
        flv_url_list = stream_url['flv_pull_url']
        m3u8_url_list = stream_url['hls_pull_url_map']

        # video_qualities = {
        #     "原画": "FULL_HD1",
        #     "蓝光": "FULL_HD1",
        #     "超清": "HD1",
        #     "高清": "SD1",
        #     "标清": "SD2",
        # }

        quality_list: list = list(m3u8_url_list.keys())
        while len(quality_list) < 4:
            quality_list.append(quality_list[-1])
        video_qualities = {"原画": 0, "蓝光": 0, "超清": 1, "高清": 2, "标清": 3}
        quality_index = video_qualities.get(video_quality)
        quality_key = quality_list[quality_index]
        m3u8_url = m3u8_url_list.get(quality_key)
        flv_url = flv_url_list.get(quality_key)

        result['m3u8_url'] = m3u8_url
        result['flv_url'] = flv_url
        result['is_live'] = True
        result['record_url'] = m3u8_url  # 使用 m3u8 链接进行录制
    return result


@trace_error_decorator
def get_tiktok_stream_url(json_data: dict, video_quality: str) -> dict:
    # TODO: 获取tiktok直播源地址
    if not json_data:
        return {"anchor_name": None, "is_live": False}

    def get_video_quality_url(stream, q_key):
        return {
            'hls': re.sub("https", "http", stream[q_key]['main']['hls']),
            'flv': re.sub("https", "http", stream[q_key]['main']['flv']),
        }

    live_room = json_data['LiveRoom']['liveRoomUserInfo']
    user = live_room['user']
    anchor_name = f"{user['nickname']}-{user['uniqueId']}"
    status = user.get("status", 4)

    result = {
        "anchor_name": anchor_name,
        "is_live": False,
    }

    if status == 2:
        stream_data = live_room.get('liveRoom', {}).get('streamData', {}).get('pull_data', {}).get('stream_data', '{}')
        stream_data = json.loads(stream_data).get('data', {})

        quality_list: list = list(stream_data.keys())  # ["origin","uhd","sd","ld"]
        while len(quality_list) < 4:
            quality_list.append(quality_list[-1])
        video_qualities = {"原画": 0, "蓝光": 0, "超清": 1, "高清": 2, "标清": 3}
        quality_index = video_qualities.get(video_quality)
        quality_key = quality_list[quality_index]
        video_quality_urls = get_video_quality_url(stream_data, quality_key)
        result['flv_url'] = video_quality_urls['flv']
        result['m3u8_url'] = video_quality_urls['hls']
        result['is_live'] = True
        result['record_url'] = result['flv_url'] if result['flv_url'] else result['m3u8_url']
        result['record_url'] = re.sub("only_audio=1", "only_audio=0", result['record_url'])
    return result


@trace_error_decorator
def get_kuaishou_stream_url(json_data: dict, video_quality: str) -> dict:
    # TODO: 获取快手直播源地址

    if json_data['type'] == 1 and not json_data["is_live"]:
        return json_data
    live_status = json_data['is_live']

    result = {
        "type": 2,
        "anchor_name": json_data['anchor_name'],
        "is_live": live_status,
    }

    if live_status:
        quality_mapping = {'原画': 0, '蓝光': 0, '超清': 1, '高清': 2, '标清': 3}

        if video_quality in quality_mapping:

            quality_index = quality_mapping[video_quality]
            if 'm3u8_url_list' in json_data:
                m3u8_url_list = json_data['m3u8_url_list'][::-1]
                while len(m3u8_url_list) < 4:
                    m3u8_url_list.append(m3u8_url_list[-1])
                m3u8_url = m3u8_url_list[quality_index]['url']
                result['m3u8_url'] = m3u8_url

            if 'flv_url_list' in json_data:
                flv_url_list = json_data['flv_url_list'][::-1]
                while len(flv_url_list) < 4:
                    flv_url_list.append(flv_url_list[-1])
                flv_url = flv_url_list[quality_index]['url']
                result['flv_url'] = flv_url
                result['record_url'] = flv_url

            result['is_live'] = True
    return result


@trace_error_decorator
def get_huya_stream_url(json_data: dict, video_quality: str) -> dict:
    # TODO: 获取虎牙直播源地址

    game_live_info = json_data.get('data', [])[0].get('gameLiveInfo', {})
    stream_info_list = json_data.get('data', [])[0].get('gameStreamInfoList', [])
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

        def get_anti_code(old_anti_code):

            # js地址：https://hd.huya.com/cdn_libs/mobile/hysdk-m-202402211431.js

            params_t = 100
            sdk_version = 2403051612

            # sdk_id是13位数毫秒级时间戳
            t13 = int(time.time()) * 1000
            sdk_sid = t13

            # 计算uuid和uid参数值
            init_uuid = (int(t13 % 10**10 * 1000) + int(1000 * random.random())) % 4294967295  # 直接初始化
            uid = random.randint(1400000000000, 1400009999999)  # 经过测试uid也可以使用init_uuid代替
            seq_id = uid + sdk_sid  # 移动端请求的直播流地址中包含seqId参数

            # 计算ws_time参数值(16进制) 可以是当前毫秒时间戳，当然也可以直接使用url_query['wsTime'][0]
            # 原始最大误差不得慢240000毫秒
            target_unix_time = (t13+110624) // 1000
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
        if len(quality_list) > 1:
            pattern = r"(?<=264_)\d+"
            quality_list = [x for x in re.findall(pattern, quality_list[1])][::-1]
            while len(quality_list) < 4:
                quality_list.append(quality_list[-1])

            video_quality_options = {
                "原画": quality_list[0],
                "蓝光": quality_list[0],
                "超清": quality_list[1],
                "高清": quality_list[2],
                "标清": quality_list[3]
            }

            if video_quality not in video_quality_options:
                raise ValueError(
                    f"Invalid video quality. Available options are: {', '.join(video_quality_options.keys())}")

            flv_url = flv_url + str(video_quality_options[video_quality])
            m3u8_url = m3u8_url + str(video_quality_options[video_quality])

        result['flv_url'] = flv_url
        result['m3u8_url'] = m3u8_url
        result['is_live'] = True
        result['record_url'] = flv_url  # m3u8经常会出现断流
    return result


@trace_error_decorator
def get_douyu_stream_url(json_data: dict, cookies: str, video_quality: str, proxy_address: str) -> dict:
    # TODO: 获取斗鱼直播源地址
    video_quality_options = {
        "原画": '0',
        "蓝光": '0',
        "超清": '3',
        "高清": '2',
        "标清": '1'
    }

    room_info = json_data.get('pageContext', json_data)['pageProps']['room']['roomInfo']['roomInfo']
    anchor_name = room_info.get('nickname', '')
    status = room_info.get('isLive', False)
    result = {
        "anchor_name": anchor_name,
        "is_live": False,
    }
    # 如果status值为1，则正在直播
    # 这边有个bug，就是如果是直播回放，状态也是在直播 待优化
    if status == 1:
        rid = str(room_info['rid'])
        rate = video_quality_options.get(video_quality, '0')  # 默认为原画
        flv_data = get_douyu_stream_data(rid, rate, cookies=cookies, proxy_addr=proxy_address)
        flv_url = flv_data['data'].get('url', None)
        if flv_url:
            result['flv_url'] = flv_url
            result['is_live'] = True
            result['record_url'] = flv_url
    return result


@trace_error_decorator
def get_yy_stream_url(json_data: dict) -> dict:
    # TODO: 获取YY直播源地址
    anchor_name = json_data.get('anchor_name', '')
    result = {
        "anchor_name": anchor_name,
        "is_live": False,
    }
    if 'avp_info_res' in json_data:
        stream_line_addr = json_data['avp_info_res']['stream_line_addr']
        # 获取最后一个键的值
        cdn_info = list(stream_line_addr.values())[0]
        flv_url = cdn_info['cdn_info']['url']  # 清晰度暂时默认高清
        result['flv_url'] = flv_url
        result['is_live'] = True
        result['record_url'] = flv_url
    return result


@trace_error_decorator
def get_bilibili_stream_url(json_data: dict, video_quality: str) -> dict:
    # TODO: 获取B站直播源地址
    if "is_live" in json_data and not json_data['anchor_name']:
        return json_data

    anchor_name = json_data.get('roomInfoRes', {}).get('data', {}).get('anchor_info', {}).get('base_info', {}).get(
        'uname', '')
    playurl_info = json_data['roomInitRes']['data']['playurl_info']
    result = {
        "anchor_name": anchor_name,
        "is_live": False,
    }
    if playurl_info:
        def get_url(m, n):
            format_list = ['.flv', '.m3u8']
            # 字典中的键就是qn，其中qn=30000为杜比 20000为4K 10000为原画 400蓝光 250超清 150高清，qn=0是默认画质
            quality_list = {'10000': '', '400': '_4000', '250': '_2500', '150': '_1500'}

            stream_data = playurl_info['playurl']['stream'][m]['format'][0]['codec'][0]
            accept_qn_list = stream_data['accept_qn']
            while len(accept_qn_list) < 4:
                accept_qn_list.append(accept_qn_list[-1])
            base_url = stream_data['base_url']
            current_qn = stream_data['current_qn']
            host = stream_data['url_info'][0]['host']
            extra = stream_data['url_info'][0]['extra']
            url_type = format_list[m]
            qn = str(accept_qn_list[n])
            select_quality = quality_list[qn]

            if current_qn != 10000:
                base_url = re.sub(r'_(\d+)' + f'(?={url_type}\\?)', select_quality, base_url)

            extra = re.sub('&qn=0', f'&qn={qn}', extra)
            return host + base_url + extra

        if video_quality == "原画" or video_quality == "蓝光":
            flv_url = get_url(0, 0)
            m3u8_url = get_url(1, 0)
        elif video_quality == "超清":
            flv_url = get_url(0, 1)
            m3u8_url = get_url(1, 1)
        elif video_quality == "高清":
            flv_url = get_url(0, 2)
            m3u8_url = get_url(1, 2)
        elif video_quality == "标清":
            flv_url = get_url(0, 3)
            m3u8_url = get_url(1, 3)
        else:
            flv_url = get_url(0, 0)
            m3u8_url = get_url(1, 0)

        result['flv_url'] = flv_url
        result['m3u8_url'] = m3u8_url
        result['is_live'] = True
        result['record_url'] = m3u8_url  # B站使用m3u8链接进行录制
    return result


@trace_error_decorator
def get_afreecatv_stream_url(json_data: dict, video_quality: str) -> dict:
    if not json_data['is_live']:
        return json_data

    play_url_list = json_data['play_url_list']
    quality_list = {'原画': 0, '蓝光': 0, '超清': 1, '高清': 2, '标清': 3}
    while len(play_url_list) < 4:
        play_url_list.append(play_url_list[-1])

    selected_quality = quality_list[video_quality]
    m3u8_url = play_url_list[selected_quality]

    return {
        "anchor_name": json_data['anchor_name'],
        "is_live": True,
        "m3u8_url": json_data['m3u8_url'],
        "record_url": m3u8_url
    }


@trace_error_decorator
def get_netease_stream_url(json_data: dict, video_quality: str) -> dict:
    if not json_data['is_live']:
        return json_data
    stream_list = json_data['stream_list']['resolution']
    order = ['blueray', 'ultra', 'high', 'standard']
    sorted_keys = [key for key in order if key in stream_list]
    while len(sorted_keys) < 4:
        sorted_keys.append(sorted_keys[-1])
    quality_list = {'原画': 0, '蓝光': 0, '超清': 1, '高清': 2, '标清': 3}
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


@trace_error_decorator
def get_pandatv_stream_url(json_data: dict, video_quality: str) -> dict:
    if not json_data['is_live']:
        return json_data

    play_url_list = json_data['play_url_list']
    quality_list = {'原画': 0, '蓝光': 0, '超清': 1, '高清': 2, '标清': 3}
    while len(play_url_list) < 4:
        play_url_list.append(play_url_list[-1])

    selected_quality = quality_list[video_quality]
    m3u8_url = play_url_list[selected_quality]

    return {
        "anchor_name": json_data['anchor_name'],
        "is_live": True,
        "m3u8_url": json_data['m3u8_url'],
        "record_url": m3u8_url
    }


@trace_error_decorator
def get_winktv_stream_url(json_data: dict, video_quality: str) -> dict:
    if not json_data['is_live']:
        return json_data

    play_url_list = json_data['play_url_list']
    quality_list = {'原画': 0, '蓝光': 0, '超清': 1, '高清': 2, '标清': 3}
    while len(play_url_list) < 4:
        play_url_list.append(play_url_list[-1])

    selected_quality = quality_list[video_quality]
    m3u8_url = play_url_list[selected_quality]

    return {
        "anchor_name": json_data['anchor_name'],
        "is_live": True,
        "m3u8_url": json_data['m3u8_url'],
        "record_url": m3u8_url
    }


@trace_error_decorator
def get_flextv_stream_url(json_data: dict, video_quality: str) -> dict:
    if not json_data['is_live']:
        return json_data

    play_url_list = json_data['play_url_list']
    quality_list = {'原画': 0, '蓝光': 0, '超清': 1, '高清': 2, '标清': 3}
    while len(play_url_list) < 4:
        play_url_list.append(play_url_list[-1])

    selected_quality = quality_list[video_quality]
    m3u8_url = play_url_list[selected_quality]

    return {
        "anchor_name": json_data['anchor_name'],
        "is_live": True,
        "m3u8_url": json_data['m3u8_url'],
        "record_url": m3u8_url
    }


def push_message(content: str):
    push_pts = []
    if '微信' in live_status_push:
        push_pts.append('微信')
        xizhi(xizhi_api_url, content)
    if '钉钉' in live_status_push:
        push_pts.append('钉钉')
        dingtalk(dingtalk_api_url, content, dingtalk_phone_num)
    if 'TG' in live_status_push or 'tg' in live_status_push:
        push_pts.append('TG')
        tg_bot(tg_chat_id, tg_token, content)
    push_pts = '、'.join(push_pts) if len(push_pts) > 0 else ''
    return push_pts


def start_record(url_data: tuple, count_variable: int = -1):
    global warning_count
    global video_save_path
    global live_list
    global not_record_list
    global recording_time_list
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
            print(f"\r运行新线程,传入地址 {record_url}")
            while True:
                try:
                    port_info = []
                    if record_url.find("https://live.douyin.com/") > -1:
                        platform = '抖音直播'
                        # 判断如果是浏览器长链接
                        with semaphore:
                            json_data = get_douyin_stream_data(
                                url=record_url,
                                proxy_addr=proxy_address,
                                cookies=dy_cookie)
                            port_info = get_douyin_stream_url(json_data, record_quality)
                    elif record_url.find("https://v.douyin.com/") > -1:
                        platform = '抖音直播'
                        # 判断如果是app分享链接
                        is_long_url = True
                        room_id, sec_user_id = get_sec_user_id(url=record_url, proxy_addr=proxy_address)
                        web_rid = get_live_room_id(room_id, sec_user_id, proxy_addr=proxy_address)
                        if len(web_rid) == 0:
                            print('web_rid 获取失败，若多次失败请联系作者修复或者使用浏览器打开后的长链接')
                        new_record_url = "https://live.douyin.com/" + str(web_rid)
                        not_record_list.append(new_record_url)
                        with semaphore:
                            json_data = get_douyin_stream_data(
                                url=new_record_url,
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
                                logger.warning(f"错误信息: 网络异常，请检查网络是否能正常访问TikTok平台")

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
                            json_data = get_huya_stream_data(
                                url=record_url,
                                proxy_addr=proxy_address,
                                cookies=hy_cookie)
                            port_info = get_huya_stream_url(json_data, record_quality)

                    elif record_url.find("https://www.douyu.com/") > -1:
                        platform = '斗鱼直播'
                        with semaphore:
                            json_data = get_douyu_info_data(url=record_url, proxy_addr=proxy_address)
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
                            json_data = get_bilibili_stream_data(
                                url=record_url, proxy_addr=proxy_address, cookies=bili_cookie)
                            port_info = get_bilibili_stream_url(json_data, record_quality)

                    elif record_url.find("https://www.redelight.cn/") > -1 or \
                            record_url.find("https://www.xiaohongshu.com/") > -1:
                        platform = '小红书直播'
                        if retry > 0:
                            time.sleep(7200)
                            retry = 0
                        with semaphore:
                            port_info = get_xhs_stream_url(url=record_url, proxy_addr=proxy_address, cookies=xhs_cookie)
                            retry += 1

                    elif record_url.find("https://www.bigo.tv/") > -1:
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
                                port_info = get_afreecatv_stream_url(json_data, record_quality)
                            else:
                                logger.warning(f"错误信息: 网络异常，请检查本网络是否能正常访问AfreecaTV平台")

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
                                port_info = get_pandatv_stream_url(json_data, record_quality)
                            else:
                                logger.warning(f"错误信息: 网络异常，请检查本网络是否能正常访问PandaTV直播平台")

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
                                port_info = get_winktv_stream_url(json_data, record_quality)
                            else:
                                logger.warning(f"错误信息: 网络异常，请检查本网络是否能正常访问WinkTV直播平台")

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
                                port_info = get_flextv_stream_url(json_data, record_quality)
                            else:
                                logger.warning(f"错误信息: 网络异常，请检查本网络是否能正常访问FlexTV直播平台")

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
                                logger.warning(f"错误信息: 网络异常，请检查本网络是否能正常访问PopkonTV直播平台")

                    elif record_url.find("twitcasting.tv/") > -1:
                        platform = 'TwitCasting'
                        with semaphore:
                            port_info = get_twitcasting_stream_url(
                                url=record_url,
                                proxy_addr=proxy_address,
                                cookies=twitcasting_cookie,
                                username=twitcasting_username,
                                password=twitcasting_password
                            )

                    else:
                        logger.warning(f'{record_url} 未知直播地址')
                        return

                    if anchor_name:
                        anchor_split: list = anchor_name.split('主播:')
                        if len(anchor_split) > 1 and anchor_split[1].strip():
                            anchor_name = anchor_split[1].strip()
                        else:
                            anchor_name = port_info.get("anchor_name", '')
                    else:
                        anchor_name = port_info.get("anchor_name", '')

                    if anchor_name == '':
                        print(f'序号{count_variable} 网址内容获取失败,进行重试中...获取失败的地址是:{url_data}')
                        warning_count += 1
                    else:
                        anchor_name = re.sub(rstr, "_", anchor_name)  # 过滤不能作为文件名的字符，替换为下划线
                        record_name = f'序号{count_variable} {anchor_name}'

                        if anchor_name in recording:
                            print(f"新增的地址: {anchor_name} 已经存在,本条线程将会退出")
                            name_list.append(f'{record_url}|#{record_url}')
                            return

                        if url_data[-1] == "" and run_once is False:
                            if is_long_url:
                                name_list.append(f'{record_url}|{new_record_url},主播: {anchor_name.strip()}')
                            else:
                                name_list.append(f'{record_url}|{record_url},主播: {anchor_name.strip()}')
                            run_once = True

                        if port_info['is_live'] is False:
                            print(f"\r{record_name} 等待直播... ")

                            if start_pushed:
                                content = f"{record_name} 直播已结束！"
                                push_pts = push_message(content)
                                if push_pts:
                                    print(f'提示信息：已经将[{record_name}]直播状态消息推送至你的{push_pts}')
                                    start_pushed = False
                        else:
                            content = f"\r{record_name} 正在直播中..."
                            print(content)

                            # 推送通知
                            if live_status_push and not start_pushed:
                                push_pts = push_message(f"{content.split('...')[0]}，时间：{datetime.datetime.today()}")
                                if push_pts:
                                    print(f'提示信息：已经将[{record_name}]直播状态消息推送至你的{push_pts}')
                                    start_pushed = True

                            if disable_record:
                                time.sleep(push_check_seconds)
                                continue

                            real_url = port_info['record_url']
                            full_path = f'{default_path}/{platform}/{anchor_name}'
                            if len(real_url) > 0:
                                live_list.append(anchor_name)
                                now = datetime.datetime.today().strftime("%Y-%m-%d_%H-%M-%S")

                                try:
                                    if len(video_save_path) > 0:
                                        if video_save_path[-1] not in ["/", "\\"]:
                                            video_save_path = video_save_path + "/"
                                        full_path = f'{video_save_path}{platform}/{anchor_name}'

                                    full_path = full_path.replace("\\", '/')

                                    if not os.path.exists(full_path):
                                        os.makedirs(full_path)
                                except Exception as e:
                                    logger.warning(f"错误信息: {e} 发生错误的行数: {e.__traceback__.tb_lineno}")

                                if not os.path.exists(full_path):
                                    logger.warning(
                                        "错误信息: 保存路径不存在,不能生成录制.请避免把本程序放在c盘,桌面,下载文件夹,qq默认传输目录.请重新检查设置")

                                user_agent = ("Mozilla/5.0 (Linux; Android 11; SAMSUNG SM-G973U) AppleWebKit/537.36 ("
                                              "KHTML, like Gecko) SamsungBrowser/14.2 Chrome/87.0.4280.141 Mobile "
                                              "Safari/537.36")

                                analyzeduration = "20000000"
                                probesize = "10000000"
                                bufsize = "8000k"
                                max_muxing_queue_size = "1024"
                                for pt_host in overseas_platform_host:
                                    if pt_host in record_url:
                                        analyzeduration = "40000000"
                                        probesize = "20000000"
                                        bufsize = "15000k"
                                        max_muxing_queue_size = "2048"
                                        break

                                ffmpeg_command = [
                                    ffmpeg_path, "-y",
                                    "-v", "verbose",
                                    "-rw_timeout", "30000000",
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

                                # 添加代理参数
                                if proxy_address:
                                    ffmpeg_command.insert(1, "-http_proxy")
                                    ffmpeg_command.insert(2, proxy_address)

                                recording.add(record_name)
                                start_record_time = datetime.datetime.now()
                                recording_time_list[record_name] = [start_record_time, record_quality]
                                rec_info = f"\r{anchor_name} 录制视频中: {full_path}"
                                filename_short = full_path + '/' + anchor_name + '_' + now

                                if video_save_type == "FLV":
                                    filename = anchor_name + '_' + now + '.flv'
                                    print(f'{rec_info}/{filename}')

                                    if create_time_file:
                                        filename_gruop = [anchor_name, filename_short]
                                        create_var[str(filename_short)] = threading.Thread(target=create_ass_file,
                                                                                           args=(filename_gruop,))
                                        create_var[str(filename_short)].daemon = True
                                        create_var[str(filename_short)].start()

                                    try:
                                        flv_url = port_info.get('flv_url', None)
                                        if flv_url:
                                            _filepath, _ = urllib.request.urlretrieve(real_url,
                                                                                      full_path + '/' + filename)

                                        else:
                                            raise Exception('该直播无flv直播流，请切换视频保存类型')

                                    except Exception as e:
                                        logger.warning(f"错误信息: {e} 发生错误的行数: {e.__traceback__.tb_lineno}")
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
                                                filename_gruop = [anchor_name, filename_short]
                                                create_var[str(filename_short)] = threading.Thread(
                                                    target=create_ass_file,
                                                    args=(filename_gruop,))
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

                                        _output = subprocess.check_output(ffmpeg_command, stderr=subprocess.STDOUT)

                                    except subprocess.CalledProcessError as e:
                                        logger.warning(f"错误信息: {e} 发生错误的行数: {e.__traceback__.tb_lineno}")
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
                                                save_file_path,
                                            ]
                                        else:
                                            if create_time_file:
                                                filename_gruop = [anchor_name, filename_short]
                                                create_var[str(filename_short)] = threading.Thread(
                                                    target=create_ass_file,
                                                    args=(filename_gruop,))
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
                                        _output = subprocess.check_output(ffmpeg_command, stderr=subprocess.STDOUT)

                                    except subprocess.CalledProcessError as e:
                                        logger.warning(f"错误信息: {e} 发生错误的行数: {e.__traceback__.tb_lineno}")
                                        warning_count += 1
                                        no_error = False

                                elif video_save_type == "MKV音频":
                                    filename = anchor_name + '_' + now + ".mkv"
                                    print(f'{rec_info}/{filename}')
                                    save_file_path = full_path + '/' + filename

                                    try:
                                        command = [
                                            "-map", "0:a",
                                            "-c:a", "copy",
                                            "-f", "matroska",
                                            "{path}".format(path=save_file_path),
                                        ]
                                        ffmpeg_command.extend(command)
                                        _output = subprocess.check_output(ffmpeg_command, stderr=subprocess.STDOUT)

                                        if ts_to_m4a:
                                            threading.Thread(target=converts_m4a, args=(save_file_path,)).start()
                                    except subprocess.CalledProcessError as e:
                                        logger.warning(f"错误信息: {e} 发生错误的行数: {e.__traceback__.tb_lineno}")
                                        warning_count += 1
                                        no_error = False

                                elif video_save_type == "TS音频":
                                    filename = anchor_name + '_' + now + ".ts"
                                    print(f'{rec_info}/{filename}')
                                    save_file_path = full_path + '/' + filename

                                    try:
                                        command = [
                                            "-map", "0:a",
                                            "-c:a", "copy",
                                            "-f", "mpegts",
                                            "{path}".format(path=save_file_path),
                                        ]
                                        ffmpeg_command.extend(command)
                                        _output = subprocess.check_output(ffmpeg_command, stderr=subprocess.STDOUT)

                                        if ts_to_m4a:
                                            threading.Thread(target=converts_m4a, args=(save_file_path,)).start()
                                    except subprocess.CalledProcessError as e:
                                        logger.warning(f"错误信息: {e} 发生错误的行数: {e.__traceback__.tb_lineno}")
                                        warning_count += 1
                                        no_error = False

                                else:
                                    if split_video_by_time:
                                        now = time.strftime("%Y-%m-%d_%H-%M-%S", time.localtime())
                                        filename = anchor_name + '_' + now + ".ts"
                                        print(f'{rec_info}/{filename}')

                                        try:
                                            if ts_to_mp4:
                                                save_path_name = f"{full_path}/{anchor_name}_{now}_%03d.mp4"
                                                audio_code = 'aac'
                                                segment_format = 'mp4'
                                            else:
                                                save_path_name = f"{full_path}/{anchor_name}_{now}_%03d.ts"
                                                audio_code = 'copy'
                                                segment_format = 'mpegts'

                                            command = [
                                                "-c:v", "copy",
                                                "-c:a", audio_code,
                                                "-map", "0",
                                                "-f", "segment",
                                                "-segment_time", split_time,
                                                "-segment_format", segment_format,
                                                "-reset_timestamps", "1",
                                                save_path_name,
                                            ]

                                            ffmpeg_command.extend(command)
                                            _output = subprocess.check_output(ffmpeg_command,
                                                                              stderr=subprocess.STDOUT)

                                        except subprocess.CalledProcessError as e:
                                            logger.warning(
                                                f"错误信息: {e} 发生错误的行数: {e.__traceback__.tb_lineno}")
                                            warning_count += 1
                                            no_error = False

                                    else:
                                        filename = anchor_name + '_' + now + ".ts"

                                        print(f'{rec_info}/{filename}')
                                        save_file_path = full_path + '/' + filename

                                        if create_time_file:
                                            filename_gruop = [anchor_name, filename_short]
                                            create_var[str(filename_short)] = threading.Thread(target=create_ass_file,
                                                                                               args=(filename_gruop,))
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
                                            _output = subprocess.check_output(ffmpeg_command, stderr=subprocess.STDOUT)

                                            if ts_to_mp4:
                                                threading.Thread(target=converts_mp4, args=(save_file_path,)).start()
                                            if ts_to_m4a:
                                                threading.Thread(target=converts_m4a, args=(save_file_path,)).start()

                                        except subprocess.CalledProcessError as e:
                                            logger.warning(f"错误信息: {e} 发生错误的行数: {e.__traceback__.tb_lineno}")
                                            warning_count += 1
                                            no_error = False

                                record_finished = True
                                record_finished_2 = True
                                count_time = time.time()

                            if record_finished_2:
                                if record_name in recording:
                                    recording.remove(record_name)
                                if anchor_name in unrecording:
                                    unrecording.add(anchor_name)

                                if no_error:
                                    print(f"\n{anchor_name} {time.strftime('%Y-%m-%d %H:%M:%S')} 直播录制完成\n")
                                else:
                                    print(
                                        f"\n{anchor_name} {time.strftime('%Y-%m-%d %H:%M:%S')} 直播录制出错,请检查网络\n")

                                record_finished_2 = False

                                # 推送通知
                                content = f"{record_name} 直播已结束"
                                if not live_status_push:
                                    if '微信' in live_status_push:
                                        xizhi(xizhi_api_url, content)
                                    if '钉钉' in live_status_push:
                                        dingtalk(dingtalk_api_url, content, dingtalk_phone_num)
                                    if 'TG' in live_status_push:
                                        tg_bot(tg_chat_id, tg_token, content)

                except Exception as e:
                    logger.warning(f"错误信息: {e} 发生错误的行数: {e.__traceback__.tb_lineno}")
                    warning_count += 1

                num = random.randint(-5, 5) + delay_default  # 生成-5到5的随机数，加上delay_default
                if num < 0:  # 如果得到的结果小于0，则将其设置为0
                    num = 0
                x = num

                # 如果出错太多,就加秒数
                if warning_count > 100:
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
            logger.warning(f"错误信息: {e} 发生错误的行数: {e.__traceback__.tb_lineno}")
            warning_count += 1
            time.sleep(2)


def backup_file(file_path: str, backup_dir_path: str):
    """
    备份配置文件到备份目录，分别保留最新 5 个文件
    """
    try:
        if not os.path.exists(backup_dir_path):
            os.makedirs(backup_dir_path)

        timestamp = datetime.datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
        backup_file_name = os.path.basename(file_path) + '_' + timestamp

        backup_file_path = os.path.join(backup_dir_path, backup_file_name).replace("\\", "/")
        shutil.copy2(file_path, backup_file_path)
        print(f'\r已备份配置文件 {file_path} 到 {backup_file_path}')

        # 删除多余的备份文件
        files = os.listdir(backup_dir_path)
        url_files = [f for f in files if f.startswith('URL_config.ini')]
        config_files = [f for f in files if f.startswith('config.ini')]

        url_files.sort(key=lambda x: os.path.getmtime(os.path.join(backup_dir_path, x)))
        config_files.sort(key=lambda x: os.path.getmtime(os.path.join(backup_dir_path, x)))

        while len(url_files) > 5:
            oldest_file = url_files[0]
            os.remove(os.path.join(backup_dir_path, oldest_file))
            # print(f'\r已删除最旧的 URL_config.ini 备份文件 {oldest_file}')
            url_files = url_files[1:]

        while len(config_files) > 5:
            oldest_file = config_files[0]
            os.remove(os.path.join(backup_dir_path, oldest_file))
            # print(f'\r已删除最旧的 config.ini 备份文件 {oldest_file}')
            config_files = config_files[1:]

    except Exception as e:
        print(f'\r备份配置文件 {file_path} 失败：{str(e)}')


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
            time.sleep(600)  # 每10分钟检测一次文件是否有修改
        except Exception as e:
            print(f'执行脚本异常：{str(e)}')


# --------------------------检测是否存在ffmpeg-------------------------------------
ffmepg_file_check = subprocess.getoutput("ffmpeg")
if ffmepg_file_check.find("run") > -1:
    # print("ffmpeg存在")
    pass
else:
    input("重要提示:\n\r检测到ffmpeg不存在,请将ffmpeg.exe放到同目录,或者设置为环境变量,没有ffmpeg将无法录制")
    sys.exit(0)

# --------------------------初始化程序-------------------------------------
print("-----------------------------------------------------")
print("|                DouyinLiveRecorder                 |")
print("-----------------------------------------------------")

print(f"版本号: {version}")
print(f"GitHub: https://github.com/ihmily/DouyinLiveRecorder")
print(f'支持平台: {platforms}')
print('.....................................................')

if not os.path.exists('./config'):
    os.makedirs('./config')

# 备份配置
t3 = threading.Thread(target=backup_file_start, args=(), daemon=True)
t3.start()


try:
    # 录制国外平台时，如果开启了电脑全局/规则代理，可以正常录制，但强烈建议还是配置一下代理地址，否则非常不稳定
    # 检测电脑是否开启了全局/规则代理（如果身处国外请忽略）
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


def read_config_value(config_parser: configparser.RawConfigParser, section: str, option: str, default_value: Any) -> (
        Union)[str, int, bool]:
    try:

        config_parser.read(config_file, encoding=encoding)
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
        with open(config_file, 'w', encoding=encoding) as f:
            config_parser.write(f)
        return default_value


options = {"是": True, "否": False}

while True:
    # 循环读取配置
    config = configparser.RawConfigParser()

    try:
        with open(config_file, 'r', encoding=encoding) as file:
            config.read_file(file)
    except IOError:
        with open(config_file, 'w', encoding=encoding) as file:
            pass

    if os.path.isfile(url_config_file):
        with open(url_config_file, 'r', encoding=encoding) as file:
            ini_content = file.read()
    else:
        ini_content = ""

    if len(ini_content) == 0:
        input_url = input('请输入要录制的主播直播间网址（尽量使用PC网页端的直播间地址）:\n')
        with open(url_config_file, 'a+', encoding=encoding) as file:
            file.write(input_url)

    video_save_path = read_config_value(config, '录制设置', '直播保存路径（不填则默认）', "")
    video_save_type = read_config_value(config, '录制设置', '视频保存格式ts|mkv|flv|mp4|ts音频|mkv音频', "ts")
    video_record_quality = read_config_value(config, '录制设置', '原画|超清|高清|标清', "原画")
    use_proxy = options.get(read_config_value(config, '录制设置', '是否使用代理ip（是/否）', "是"), False)
    proxy_addr_bak = read_config_value(config, '录制设置', '代理地址', "")
    proxy_addr = None if not use_proxy else proxy_addr_bak
    max_request = int(read_config_value(config, '录制设置', '同一时间访问网络的线程数', 3))
    semaphore = threading.Semaphore(max_request)
    delay_default = int(read_config_value(config, '录制设置', '循环时间(秒)', 120))
    local_delay_default = int(read_config_value(config, '录制设置', '排队读取网址时间(秒)', 0))
    loop_time = options.get(read_config_value(config, '录制设置', '是否显示循环秒数', "否"), False)
    split_video_by_time = options.get(read_config_value(config, '录制设置', '分段录制是否开启', "否"), False)
    split_time = str(read_config_value(config, '录制设置', '视频分段时间(秒)', 1800))
    ts_to_mp4 = options.get(read_config_value(config, '录制设置', 'ts录制完成后自动转为mp4格式', "否"),
                            False)
    ts_to_m4a = options.get(read_config_value(config, '录制设置', 'ts录制完成后自动增加生成m4a格式', "否"),
                            False)
    delete_origin_file = options.get(read_config_value(config, '录制设置', '追加格式后删除原文件', "否"), False)
    create_time_file = options.get(read_config_value(config, '录制设置', '生成时间文件', "否"), False)
    enable_proxy_platform = read_config_value(config, '录制设置', '使用代理录制的平台（逗号分隔）',
                                              'tiktok, afreecatv, pandalive, winktv, flextv, popkontv')
    enable_proxy_platform_list = enable_proxy_platform.replace('，', ',').split(',') if enable_proxy_platform else None
    extra_enable_proxy = read_config_value(config, '录制设置', '额外使用代理录制的平台（逗号分隔）', '')
    extra_enable_proxy_platform_list = extra_enable_proxy.replace('，', ',').split(',') if extra_enable_proxy else None
    live_status_push = read_config_value(config, '推送配置', '直播状态通知(可选微信|钉钉|tg或者都填)', "")
    dingtalk_api_url = read_config_value(config, '推送配置', '钉钉推送接口链接', "")
    xizhi_api_url = read_config_value(config, '推送配置', '微信推送接口链接', "")
    dingtalk_phone_num = read_config_value(config, '推送配置', '钉钉通知@对象(填手机号)', "")
    tg_token = read_config_value(config, '推送配置', 'tgapi令牌', "")
    tg_chat_id = read_config_value(config, '推送配置', 'tg聊天id(个人或者群组id)', "")
    disable_record = options.get(read_config_value(config, '推送配置', '只推送通知不录制（是/否）', "否"), False)
    push_check_seconds = int(read_config_value(config, '推送配置', '直播推送检测频率（秒）', 1800))
    afreecatv_username = read_config_value(config, '账号密码', 'afreecatv账号', '')
    afreecatv_password = read_config_value(config, '账号密码', 'afreecatv密码', '')
    flextv_username = read_config_value(config, '账号密码', 'flextv账号', '')
    flextv_password = read_config_value(config, '账号密码', 'flextv密码', '')
    popkontv_username = read_config_value(config, '账号密码', 'popkontv账号', '')
    popkontv_partner_code = read_config_value(config, '账号密码', 'partner_code', 'P-00001')
    popkontv_password = read_config_value(config, '账号密码', 'popkontv密码', '')
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

    if len(video_save_type) > 0:
        if video_save_type.upper().lower() == "FLV".lower():
            video_save_type = "FLV"
        elif video_save_type.upper().lower() == "MKV".lower():
            video_save_type = "MKV"
        elif video_save_type.upper().lower() == "TS".lower():
            video_save_type = "TS"
        elif video_save_type.upper().lower() == "MP4".lower():
            video_save_type = "MP4"
        elif video_save_type.upper().lower() == "TS音频".lower():
            video_save_type = "TS音频"
        elif video_save_type.upper().lower() == "MKV音频".lower():
            video_save_type = "MKV音频"
        else:
            video_save_type = "TS"
            print("直播视频保存格式设置有问题,这次录制重置为默认的TS格式")
    else:
        video_save_type = "TS"
        print("直播视频保存为TS格式")


    def transform_int_to_time(seconds: int) -> str:
        m, s = divmod(seconds, 60)
        h, m = divmod(m, 60)
        return f"{h}:{m:02d}:{s:02d}"


    def contains_url(string: str) -> bool:
        pattern = (r"(http:\/\/www\.|https:\/\/www\.|http:\/\/|https:\/\/)?[a-zA-Z0-9][a-zA-Z0-9\-]+(\.["
                   r"a-zA-Z0-9\-]+)*\.[a-zA-Z]{2,10}(:[0-9]{1,5})?(\/.*)?$")
        return re.search(pattern, string) is not None


    # 读取URL_config.ini文件
    try:
        with open(url_config_file, "r", encoding=encoding, errors='ignore') as file:
            for line in file:
                line = line.strip()
                if line.startswith("#") or len(line) < 20:
                    continue

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

                if quality not in ["原画", "蓝光", "超清", "高清", "标清"]:
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
                    'www.bigo.tv',
                    'app.blued.cn',
                    'cc.163.com',
                    'qiandurebo.com',
                    'fm.missevan.com',
                    'look.163.com',
                    'twitcasting.tv',
                ]
                overseas_platform_host = [
                    'www.tiktok.com',
                    'play.afreecatv.com',
                    'm.afreecatv.com',
                    'www.pandalive.co.kr',
                    'www.winktv.co.kr',
                    'www.flextv.co.kr',
                    'www.popkontv.com'
                ]

                platform_host.extend(overseas_platform_host)
                if url_host in platform_host:
                    if url_host in ['live.douyin.com', 'live.bilibili.com']:
                        update_file(url_config_file, url, url.split('?')[0])
                        url = url.split('?')[0]

                    new_line = (quality, url, name)
                    url_tuples_list.append(new_line)
                else:
                    print(f"\r{url} 未知链接.此条跳过")
                    update_file(url_config_file, url, url, start_str='#')

        while len(name_list):
            a = name_list.pop()
            replace_words = a.split('|')
            if replace_words[0] != replace_words[1]:
                if replace_words[1].startswith("#"):
                    start_with = '#'
                    new_word = replace_words[1][1:]
                else:
                    start_with = None
                    new_word = replace_words[1]
                update_file(url_config_file, replace_words[0], new_word, start_str=start_with)

        if len(url_tuples_list) > 0:
            text_no_repeat_url = list(set(url_tuples_list))

        if len(text_no_repeat_url) > 0:
            for url_tuple in text_no_repeat_url:
                if url_tuple[1] in not_record_list:
                    continue

                if url_tuple[1] not in runing_list:
                    if not first_start:
                        print(f"\r新增链接: {url_tuple[1]}")
                    monitoring += 1
                    args = [url_tuple, monitoring]
                    # TODO: 执行开始录制的操作
                    create_var['thread' + str(monitoring)] = threading.Thread(target=start_record, args=args)
                    create_var['thread' + str(monitoring)].daemon = True
                    create_var['thread' + str(monitoring)].start()
                    runing_list.append(url_tuple[1])
                    time.sleep(local_delay_default)
        url_tuples_list = []
        first_start = False

    except Exception as err:
        logger.warning(f"错误信息: {err} 发生错误的行数: {err.__traceback__.tb_lineno}")

    if first_run:
        t = threading.Thread(target=display_info, args=(), daemon=True)
        t.start()
        t2 = threading.Thread(target=change_max_connect, args=(), daemon=True)
        t2.start()

        first_run = False

    time.sleep(3)
