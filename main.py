# -*- encoding: utf-8 -*-

"""
Author: Hmily
GitHub: https://github.com/ihmily
Date: 2023-07-17 23:52:05
Update: 2023-12-10 05:13:20
Copyright (c) 2023 by Hmily, All Rights Reserved.
Function: Record live stream video.
"""

import random
import os
import sys
import urllib.parse
import urllib.request
import configparser
import subprocess
import threading
import logging
import datetime
import time
import json
import re
import shutil
from spider import (
    get_douyin_stream_data,
    get_tiktok_stream_data,
    get_kuaishou_stream_data,
    get_kuaishou_stream_data2,
    get_huya_stream_data,
    get_douyu_info_data,
    get_douyu_stream_data,
    get_yy_stream_data,
    get_bilibili_stream_data,
    get_xhs_stream_url,
    get_bigo_stream_url,
    get_blued_stream_url,
    get_afreecatv_stream_url
)

from web_rid import (
    get_live_room_id,
    get_sec_user_id
)
from utils import (
    logger, check_md5,
    trace_error_decorator
)
from msg_push import dingtalk, xizhi

version = "v2.0.6"
platforms = "抖音|Tiktok|快手|虎牙|斗鱼|YY|B站|小红书|bigo直播|blued直播|AfreecaTV"
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
rstr = r"[\/\\\:\*\?\"\<\>\|&u]"
ffmpeg_path = "ffmpeg"  # ffmpeg文件路径
default_path = os.getcwd()


# --------------------------用到的函数-------------------------------------

def display_info():
    # TODO: 显示当前录制配置信息
    global start_display_time
    global recording_time_list
    time.sleep(5)
    while True:
        try:
            time.sleep(5)
            os.system("cls")
            print(f"\r共监测{monitoring}个直播中", end=" | ")
            print(f"同一时间访问网络的线程数: {max_request}", end=" | ")
            if len(video_save_path) > 0:
                if not os.path.exists(video_save_path):
                    print("配置文件里,直播保存路径并不存在,请重新输入一个正确的路径.或留空表示当前目录,按回车退出")
                    input("程序结束")
                    sys.exit(0)

            print(f"是否开启代理录制: {'是' if use_proxy else '否'}", end=" | ")
            if split_video_by_size:
                print(f"TS录制分段开启，录制分段大小为 {split_size} M", end=" | ")
            print(f"是否生成时间文件: {'是' if create_time_file else '否'}", end=" | ")
            print(f"录制视频质量为: {video_quality}", end=" | ")
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
                        have_record_time = now_time - recording_time_list[recording_live]
                        print(f"{recording_live} 正在录制中 " + str(have_record_time).split('.')[0])

                    # print('\n本软件已运行：'+str(now_time - start_display_time).split('.')[0])
                    print("x" * 60)
                else:
                    start_display_time = now_time
        except Exception as e:
            print(f"错误信息:{e}\r\n发生错误的行数: {e.__traceback__.tb_lineno}")
            logger.warning(f"错误信息: {e} 发生错误的行数: {e.__traceback__.tb_lineno}")


def update_file(file, old_str, new_str):
    # TODO: 更新文件操作
    file_data = ""
    with open(file, "r", encoding="utf-8-sig") as f:
        for text_line in f:
            if old_str in text_line:
                text_line = text_line.replace(old_str, new_str)
            file_data += text_line
    with open(file, "w", encoding="utf-8-sig") as f:
        f.write(file_data)


def converts_mp4(address):
    if tsconvert_to_mp4:
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


def converts_m4a(address):
    if tsconvert_to_m4a:
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


def create_ass_file(filegruop):
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
def get_douyin_stream_url(json_data):
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

        quality_list = list(m3u8_url_list.keys())
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
def get_tiktok_stream_url(json_data):
    # TODO: 获取tiktok直播源地址

    def get_video_quality_url(stream_data, quality_key):
        return {
            'hls': re.sub("https", "http", stream_data[quality_key]['main']['hls']),
            'flv': re.sub("https", "http", stream_data[quality_key]['main']['flv']),
        }

    live_room = json_data['LiveRoom']['liveRoomUserInfo']
    user = live_room['user']
    anchor_name = user['nickname']
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
def get_kuaishou_stream_url(json_data):
    # TODO: 获取快手直播源地址

    if json_data['type'] == 1:
        return json_data
    live_status = json_data['is_live']

    result = {
        "type": 2,
        "anchor_name": json_data['anchor_name'],
        "is_live": live_status,
    }

    if live_status:
        quality_mapping = {'原画': 0, '蓝光': 0, '超清': 1, '高清': 2, '标清': 3, }

        if video_quality in quality_mapping:

            quality_index = quality_mapping[video_quality]
            if 'm3u8_url_list' in json_data:
                m3u8_url_list = json_data['m3u8_url_list'][::-1]
                while len(m3u8_url_list) < 4:
                    m3u8_url_list.append(m3u8_url_list[-1])
                m3u8_url = m3u8_url_list[quality_index]['url']
            else:
                m3u8_url = json_data['backup']['m3u8_url']
            if 'flv_url_list' in json_data:
                flv_url_list = json_data['flv_url_list'][::-1]
                while len(flv_url_list) < 4:
                    flv_url_list.append(flv_url_list[-1])
                flv_url = flv_url_list[quality_index]['url']
            else:
                flv_url = json_data['backup']['flv_url']

            result['flv_url'] = flv_url
            result['m3u8_url'] = m3u8_url
            result['is_live'] = True
            result['record_url'] = flv_url if flv_url else m3u8_url
    return result


@trace_error_decorator
def get_huya_stream_url(json_data):
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

        flv_url = f'{flv_url}/{stream_name}.{flv_url_suffix}?{flv_anti_code}&ratio='
        m3u8_url = f'{hls_url}/{stream_name}.{hls_url_suffix}?{flv_anti_code}&ratio='

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
        result['record_url'] = flv_url  # 虎牙使用flv视频流录制

    return result


@trace_error_decorator
def get_douyu_stream_url(json_data, cookies):
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
    # 这边有个bug，就是如果是直播回放，状态也是在直播 待修复
    if status == 1:
        rid = str(room_info['rid'])
        rate = video_quality_options.get(video_quality, '0')  # 默认为原画
        flv_data = get_douyu_stream_data(rid, rate, cookies)
        flv_url = flv_data['data'].get('url', None)
        if flv_url:
            result['flv_url'] = flv_url
            result['is_live'] = True
            result['record_url'] = flv_url  # 斗鱼目前只能使用flv视频流录制
    return result


@trace_error_decorator
def get_yy_stream_url(json_data):
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
def get_bilibili_stream_url(json_data):
    # TODO: 获取B站直播源地址

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
            host = stream_data['url_info'][0]['host']
            extra = stream_data['url_info'][0]['extra']
            url_type = format_list[m]
            qn = str(accept_qn_list[n])
            quality = quality_list[qn]
            base_url = re.sub(r'_(\d+)' + f'(?={url_type}\?)', quality, base_url)
            extra = re.sub('&qn=0', f'&qn={qn}', extra)
            url = host + base_url + extra
            return url

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


def start_record(url_tuple, count_variable=-1):
    global warning_count
    global video_save_path
    global live_list
    global not_record_list
    global recording_time_list

    while True:
        try:
            record_finished = False
            record_finished_2 = False
            run_once = False
            is_long_url = False
            no_error = True
            new_record_url = ''
            count_time = time.time()
            record_url = url_tuple[0]
            anchor_name = url_tuple[1]
            print(f"\r运行新线程,传入地址 {record_url}")

            while True:
                try:
                    port_info = []
                    if record_url.find("https://live.douyin.com/") > -1:
                        # 判断如果是浏览器长链接
                        with semaphore:
                            # 使用semaphore来控制同时访问资源的线程数量
                            json_data = get_douyin_stream_data(record_url, dy_cookie)
                            port_info = get_douyin_stream_url(json_data)
                    elif record_url.find("https://v.douyin.com/") > -1:
                        # 判断如果是app分享链接
                        is_long_url = True
                        room_id, sec_user_id = get_sec_user_id(record_url)
                        web_rid = get_live_room_id(room_id, sec_user_id)
                        if len(web_rid) == 0:
                            print('web_rid 获取失败，若多次失败请联系作者修复或者使用浏览器打开后的长链接')
                        new_record_url = "https://live.douyin.com/" + str(web_rid)
                        not_record_list.append(new_record_url)
                        with semaphore:
                            json_data = get_douyin_stream_data(new_record_url, dy_cookie)
                            port_info = get_douyin_stream_url(json_data)

                    elif record_url.find("https://www.tiktok.com/") > -1:
                        with semaphore:
                            if use_proxy:
                                if global_proxy or proxy_addr != '':
                                    json_data = get_tiktok_stream_data(record_url, proxy_addr, tiktok_cookie)
                                    port_info = get_tiktok_stream_url(json_data)

                    elif record_url.find("https://live.kuaishou.com/") > -1:
                        with semaphore:
                            json_data = get_kuaishou_stream_data(record_url, ks_cookie)
                            port_info = get_kuaishou_stream_url(json_data)

                    elif record_url.find("https://www.huya.com/") > -1:
                        with semaphore:
                            json_data = get_huya_stream_data(record_url, hy_cookie)
                            port_info = get_huya_stream_url(json_data)

                    elif record_url.find("https://www.douyu.com/") > -1:
                        with semaphore:
                            json_data = get_douyu_info_data(record_url)
                            port_info = get_douyu_stream_url(json_data, douyu_cookie)

                    elif record_url.find("https://www.yy.com/") > -1:
                        with semaphore:
                            json_data = get_yy_stream_data(record_url, yy_cookie)
                            port_info = get_yy_stream_url(json_data)

                    elif record_url.find("https://live.bilibili.com/") > -1:
                        with semaphore:
                            json_data = get_bilibili_stream_data(record_url, bili_cookie)
                            port_info = get_bilibili_stream_url(json_data)

                    elif record_url.find("https://www.xiaohongshu.com/") > -1:
                        with semaphore:
                            port_info = get_xhs_stream_url(record_url, xhs_cookie)

                    elif record_url.find("https://www.bigo.tv/") > -1:
                        with semaphore:
                            port_info = get_bigo_stream_url(record_url, bigo_cookie)

                    elif record_url.find("https://app.blued.cn/") > -1:
                        with semaphore:
                            port_info = get_blued_stream_url(record_url, blued_cookie)

                    elif record_url.find("afreecatv.com/") > -1:
                        with semaphore:
                            port_info = get_afreecatv_stream_url(record_url, afreecatv_cookie)

                    anchor_name: str = port_info.get("anchor_name", '')

                    if not anchor_name:
                        print(f'序号{count_variable} 网址内容获取失败,进行重试中...获取失败的地址是:{url_tuple}')
                        warning_count += 1
                    else:
                        anchor_name = re.sub(rstr, "_", anchor_name)  # 过滤不能作为文件名的字符，替换为下划线
                        record_name = f'序号{count_variable} {anchor_name}'

                        if anchor_name in recording:
                            print(f"新增的地址: {anchor_name} 已经存在,本条线程将会退出")
                            name_list.append(f'{record_url}|#{record_url}')
                            return

                        if url_tuple[1] == "" and run_once is False:
                            if is_long_url:
                                name_list.append(f'{record_url}|{new_record_url},主播: {anchor_name.strip()}')
                            else:
                                name_list.append(f'{record_url}|{record_url},主播: {anchor_name.strip()}')
                            run_once = True

                        if port_info['is_live'] is False:
                            print(f"{record_name} 等待直播... ")
                        else:
                            content = f"{record_name} 正在直播中..."
                            print(content)

                            # 推送通知
                            if live_status_push:
                                if '微信' in live_status_push:
                                    xizhi(xizhi_api_url, content)
                                if '钉钉' in live_status_push:
                                    dingtalk(dingtalk_api_url, content, dingtalk_phone_num)

                            real_url = port_info['record_url']
                            full_path = f'{default_path}/{anchor_name}'
                            if real_url != "":
                                live_list.append(anchor_name)
                                now = time.strftime("%Y-%m-%d_%H-%M-%S", time.localtime(time.time()))
                                try:
                                    if len(video_save_path) > 0:
                                        if video_save_path[-1] != "/":
                                            video_save_path = video_save_path + "/"
                                        full_path = f'{video_save_path}/{anchor_name}'
                                        if not os.path.exists(full_path):
                                            os.makedirs(full_path)
                                    else:
                                        full_path = './' + anchor_name
                                        if not os.path.exists(anchor_name):
                                            os.makedirs(full_path)

                                except Exception as e:
                                    print(f"路径错误信息: {e} 发生错误的行数: {e.__traceback__.tb_lineno}")
                                    logger.warning(f"错误信息: {e} 发生错误的行数: {e.__traceback__.tb_lineno}")

                                if not os.path.exists(full_path):
                                    print(
                                        "保存路径不存在,不能生成录制.请避免把本程序放在c盘,桌面,下载文件夹,qq默认传输目录.请重新检查设置")
                                    logger.warning(
                                        "错误信息: 保存路径不存在,不能生成录制.请避免把本程序放在c盘,桌面,下载文件夹,qq默认传输目录.请重新检查设置")

                                user_agent = ("Mozilla/5.0 (Linux; Android 11; SAMSUNG SM-G973U) AppleWebKit/537.36 ("
                                              "KHTML, like Gecko) SamsungBrowser/14.2 Chrome/87.0.4280.141 Mobile "
                                              "Safari/537.36")
                                ffmpeg_command = [
                                    ffmpeg_path, "-y",
                                    "-v", "verbose",
                                    "-rw_timeout", "15000000",  # 15s
                                    "-loglevel", "error",
                                    "-hide_banner",
                                    "-user_agent", user_agent,
                                    "-protocol_whitelist", "rtmp,crypto,file,http,https,tcp,tls,udp,rtp",
                                    "-thread_queue_size", "1024",
                                    "-analyzeduration", "2147483647",
                                    "-probesize", "2147483647",
                                    "-fflags", "+discardcorrupt",
                                    "-i", real_url,
                                    "-bufsize", "5000k",
                                    "-sn", "-dn",
                                    "-reconnect_delay_max", "30",
                                    "-reconnect_streamed", "-reconnect_at_eof",
                                    "-c:a", "copy",
                                    "-max_muxing_queue_size", "64",
                                    "-correct_ts_overflow", "1",
                                ]

                                # 添加代理参数
                                need_proxy_url = ['tiktok','afreecatv']
                                for i in need_proxy_url:
                                    if i in real_url:
                                        if use_proxy and proxy_addr != '':
                                            # os.environ["http_proxy"] = proxy_addr
                                            ffmpeg_command.insert(1, "-http_proxy")
                                            ffmpeg_command.insert(2, proxy_addr)
                                            break

                                recording.add(record_name)
                                start_record_time = datetime.datetime.now()
                                recording_time_list[record_name] = start_record_time
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
                                        print(f"\r{time.strftime('%Y-%m-%d %H:%M:%S')}  {anchor_name} 未开播")
                                        logger.warning(f"错误信息: {e} 发生错误的行数: {e.__traceback__.tb_lineno}")
                                        warning_count += 1
                                        no_error = False

                                elif video_save_type == "MKV":
                                    filename = anchor_name + '_' + now + ".mkv"
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
                                            "-map", "0",
                                            "-c:v", "copy",  # 直接用copy的话体积特别大.
                                            "-f", "matroska",
                                            "{path}".format(path=save_file_path),
                                        ]
                                        ffmpeg_command.extend(command)

                                        _output = subprocess.check_output(ffmpeg_command, stderr=subprocess.STDOUT)

                                    except subprocess.CalledProcessError as e:
                                        # logging.warning(str(e.output))
                                        print(f"{e.output} 发生错误的行数: {e.__traceback__.tb_lineno}")
                                        logger.warning(f"错误信息: {e} 发生错误的行数: {e.__traceback__.tb_lineno}")
                                        warning_count += 1
                                        no_error = False

                                elif video_save_type == "MP4":
                                    filename = anchor_name + '_' + now + ".mp4"
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
                                            "-map", "0",
                                            "-c:v", "copy",  # 直接用copy的话体积特别大.
                                            "-f", "mp4",
                                            "{path}".format(path=save_file_path),
                                        ]
                                        ffmpeg_command.extend(command)
                                        _output = subprocess.check_output(ffmpeg_command, stderr=subprocess.STDOUT)

                                        # 取消http_proxy环境变量设置
                                        # if proxy_addr:
                                        #     del os.environ["http_proxy"]

                                    except subprocess.CalledProcessError as e:
                                        # logging.warning(str(e.output))
                                        print(f"{e.output} 发生错误的行数: {e.__traceback__.tb_lineno}")
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
                                            "-f", "matroska",
                                            "{path}".format(path=save_file_path),
                                        ]
                                        ffmpeg_command.extend(command)
                                        _output = subprocess.check_output(ffmpeg_command, stderr=subprocess.STDOUT)

                                        if tsconvert_to_m4a:
                                            threading.Thread(target=converts_m4a, args=(file,)).start()
                                    except subprocess.CalledProcessError as e:
                                        # logging.warning(str(e.output))
                                        print(f"{e.output} 发生错误的行数: {e.__traceback__.tb_lineno}")
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
                                            "-f", "mpegts",
                                            "{path}".format(path=save_file_path),
                                        ]
                                        ffmpeg_command.extend(command)
                                        _output = subprocess.check_output(ffmpeg_command, stderr=subprocess.STDOUT)

                                        if tsconvert_to_m4a:
                                            threading.Thread(target=converts_m4a, args=(file,)).start()
                                    except subprocess.CalledProcessError as e:
                                        # logging.warning(str(e.output))
                                        print(f"{e.output} 发生错误的行数: {e.__traceback__.tb_lineno}")
                                        logger.warning(f"错误信息: {e} 发生错误的行数: {e.__traceback__.tb_lineno}")
                                        warning_count += 1
                                        no_error = False



                                else:

                                    if split_video_by_size:  # 这里默认是启用/不启用视频分割功能
                                        while True:
                                            now = time.strftime("%Y-%m-%d_%H-%M-%S", time.localtime(time.time()))
                                            filename = anchor_name + '_' + now + ".ts"
                                            print(f'{rec_info}/{filename}')
                                            save_file_path = full_path + '/' + filename

                                            if create_time_file:
                                                filename_gruop = [anchor_name, filename_short]
                                                create_var[str(filename_short)] = threading.Thread(
                                                    target=create_ass_file,
                                                    args=(filename_gruop,))
                                                create_var[str(filename_short)].daemon = True
                                                create_var[str(filename_short)].start()

                                            try:
                                                command = [
                                                    "-c:v", "copy",
                                                    "-map", "0",
                                                    "-f", "mpegts",
                                                    "-fs", str(split_byte_sizes),
                                                    "{path}".format(path=save_file_path),
                                                ]

                                                ffmpeg_command.extend(command)
                                                _output = subprocess.check_output(ffmpeg_command,
                                                                                  stderr=subprocess.STDOUT)

                                                if tsconvert_to_mp4:
                                                    threading.Thread(target=converts_mp4, args=(file,)).start()
                                                if tsconvert_to_m4a:
                                                    threading.Thread(target=converts_m4a, args=(file,)).start()

                                            except subprocess.CalledProcessError as e:
                                                logging.warning(str(e.output))
                                                logger.warning(
                                                    f"错误信息: {e} 发生错误的行数: {e.__traceback__.tb_lineno}")
                                                warning_count += 1
                                                no_error = False
                                                break

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
                                                "-map", "0",
                                                "-f", "mpegts",
                                                "{path}".format(path=save_file_path),
                                            ]

                                            ffmpeg_command.extend(command)
                                            _output = subprocess.check_output(ffmpeg_command, stderr=subprocess.STDOUT)

                                            if tsconvert_to_mp4:
                                                threading.Thread(target=converts_mp4, args=(file,)).start()
                                            if tsconvert_to_m4a:
                                                threading.Thread(target=converts_m4a, args=(file,)).start()

                                        except subprocess.CalledProcessError as e:
                                            # logging.warning(str(e.output))
                                            print(f"{e.output} 发生错误的行数: {e.__traceback__.tb_lineno}")
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
                                    print(f"\n{anchor_name} {time.strftime('%Y-%m-%d %H:%M:%S')} 直播录制出错,请检查网络\n")

                                record_finished_2 = False

                                # 推送通知
                                content = f"{record_name} 直播已结束"
                                if live_status_push:
                                    if '微信' in live_status_push:
                                        xizhi(xizhi_api_url, content)
                                    if '钉钉' in live_status_push:
                                        dingtalk(dingtalk_api_url, content, dingtalk_phone_num)

                except Exception as e:
                    print(f"错误信息:{e}\r\n读取的地址为: {record_url} 发生错误的行数: {e.__traceback__.tb_lineno}")
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
            print(f"错误信息:{e}\r\n发生错误的行数: {e.__traceback__.tb_lineno}")
            logger.warning(f"错误信息: {e} 发生错误的行数: {e.__traceback__.tb_lineno}")
            print(f"线程崩溃2秒后重试.错误信息: {e} 发生错误的行数: {e.__traceback__.tb_lineno}")
            warning_count += 1
            time.sleep(2)


def backup_file(file_path, backup_dir):
    """
    备份配置文件到备份目录，分别保留最新 10 个文件
    """
    try:
        if not os.path.exists(backup_dir):
            os.makedirs(backup_dir)

        timestamp = datetime.datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
        backup_file_name = os.path.basename(file_path) + '_' + timestamp

        backup_file_path = os.path.join(backup_dir, backup_file_name)
        shutil.copy2(file_path, backup_file_path)
        print(f'\r已备份配置文件 {file_path} 到 {backup_file_path}')

        # 删除多余的备份文件
        files = os.listdir(backup_dir)
        url_files = [f for f in files if f.startswith('URL_config.ini')]
        config_files = [f for f in files if f.startswith('config.ini')]

        url_files.sort(key=lambda x: os.path.getmtime(os.path.join(backup_dir, x)))
        config_files.sort(key=lambda x: os.path.getmtime(os.path.join(backup_dir, x)))

        while len(url_files) > 5:
            oldest_file = url_files[0]
            os.remove(os.path.join(backup_dir, oldest_file))
            # print(f'\r已删除最旧的 URL_config.ini 备份文件 {oldest_file}')
            url_files = url_files[1:]

        while len(config_files) > 5:
            oldest_file = config_files[0]
            os.remove(os.path.join(backup_dir, oldest_file))
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
            time.sleep(60)  # 每1分钟检测一次文件是否有修改
        except Exception as e:
            print(f'执行脚本异常：{str(e)}')


# --------------------------检测是否存在ffmpeg-------------------------------------
ffmepg_file_check = subprocess.getoutput("ffmpeg")
if ffmepg_file_check.find("run") > -1:
    # print("ffmpeg存在")
    pass
else:
    print("重要提示:")
    input("检测到ffmpeg不存在,请将ffmpeg.exe放到同目录,或者设置为环境变量,没有ffmpeg将无法录制")
    sys.exit(0)

# --------------------------初始化程序-------------------------------------
print("-----------------------------------------------------")
print("|                DouyinLiveRecorder                 |")
print("-----------------------------------------------------")

print(f"版本号：{version}")
print("Github：https://github.com/ihmily/DouyinLiveRecorder")
print(f'支持平台：{platforms}')
print('.....................................................')

if not os.path.exists('./config'):
    os.makedirs('./config')

# 备份配置
t3 = threading.Thread(target=backup_file_start, args=(), daemon=True)
t3.start()

# 录制tiktok时，如果开启了电脑全局/规则代理，可以不用再在配置文件中填写代理地址
# 但强烈建议还是配置一下代理地址，否则非常不稳定
try:
    # 检测电脑是否开启了全局/规则代理
    print('系统代理检测中，请耐心等待...')
    response_g = urllib.request.urlopen("https://www.google.com/", timeout=15)
    global_proxy = True
    print('系统代理已开启√ 注意：配置文件中的代理设置也要开启才会生效哦！')

except Exception as e:
    print('INFO：未检测到全局/规则网络代理，请检查代理配置（若无需录制Tiktok直播请忽略此条提示）')


def read_config_value(config, section, option, default_value):
    try:
        config.read(config_file, encoding=encoding)
        if '录制设置' not in config.sections():
            config.add_section('录制设置')
        if '推送配置' not in config.sections():
            config.add_section('推送配置')
        if 'Cookie' not in config.sections():
            config.add_section('Cookie')
        return config.get(section, option)
    except (configparser.NoSectionError, configparser.NoOptionError):
        config.set(section, option, str(default_value))
        with open(config_file, 'w', encoding=encoding) as f:
            config.write(f)
        return default_value


options = {"是": True, "否": False}

while True:
    # 循环读取配置
    config = configparser.RawConfigParser()

    try:
        with open(config_file, 'r', encoding=encoding) as f:
            config.read_file(f)
    except IOError:
        with open(config_file, 'w', encoding=encoding) as f:
            pass

    if os.path.isfile(url_config_file):
        with open(url_config_file, 'r', encoding=encoding) as f:
            ini_content = f.read()
    else:
        ini_content = ""

    if len(ini_content) == 0:
        input_url = input('请输入要录制的主播直播间网址（尽量使用PC网页端的直播间地址）:\n')
        with open(url_config_file, 'a+', encoding=encoding) as f:
            f.write(input_url)

    video_save_path = read_config_value(config, '录制设置', '直播保存路径（不填则默认）', "")
    video_save_type = read_config_value(config, '录制设置', '视频保存格式TS|MKV|FLV|MP4|TS音频|MKV音频', "mp4")
    video_quality = read_config_value(config, '录制设置', '原画|超清|高清|标清', "原画")
    use_proxy = options.get(read_config_value(config, '录制设置', '是否使用代理ip（是/否）', "是"), False)
    proxy_addr = read_config_value(config, '录制设置', '代理地址', "")
    max_request = int(read_config_value(config, '录制设置', '同一时间访问网络的线程数', 3))
    semaphore = threading.Semaphore(max_request)
    delay_default = int(read_config_value(config, '录制设置', '循环时间(秒)', 60))
    local_delay_default = int(read_config_value(config, '录制设置', '排队读取网址时间(秒)', 0))
    loop_time = options.get(read_config_value(config, '录制设置', '是否显示循环秒数', "否"), False)
    split_video_by_size = options.get(read_config_value(config, '录制设置', 'TS格式分段录制是否开启', "否"), False)
    split_size = int(read_config_value(config, '录制设置', '视频分段大小(兆)', '1000'))
    tsconvert_to_mp4 = options.get(read_config_value(config, '录制设置', 'TS录制完成后自动增加生成MP4格式', "否"),
                                   False)
    tsconvert_to_m4a = options.get(read_config_value(config, '录制设置', 'TS录制完成后自动增加生成m4a格式', "否"),
                                   False)
    delete_origin_file = options.get(read_config_value(config, '录制设置', '追加格式后删除原文件', "否"), False)
    create_time_file = options.get(read_config_value(config, '录制设置', '生成时间文件', "否"), False)
    live_status_push = read_config_value(config, '推送配置', '直播状态通知(可选微信|钉钉或者两个都填)', "")
    dingtalk_api_url = read_config_value(config, '推送配置', '钉钉推送接口链接', "")
    xizhi_api_url = read_config_value(config, '推送配置', '微信推送接口链接', "")
    dingtalk_phone_num = read_config_value(config, '推送配置', '钉钉通知@对象(填手机号)', "")
    dy_cookie = read_config_value(config, 'Cookie', '抖音cookie(录制抖音必须要有)', '')
    ks_cookie = read_config_value(config, 'Cookie', '快手cookie', '')
    tiktok_cookie = read_config_value(config, 'Cookie', 'Tiktok_cookie', '')
    hy_cookie = read_config_value(config, 'Cookie', '虎牙cookie', '')
    douyu_cookie = read_config_value(config, 'Cookie', '斗鱼cookie', '')
    yy_cookie = read_config_value(config, 'Cookie', 'YY_cookie', '')
    bili_cookie = read_config_value(config, 'Cookie', 'B站cookie', '')
    xhs_cookie = read_config_value(config, 'Cookie', '小红书cookie', '')
    bigo_cookie = read_config_value(config, 'Cookie', 'bigo_cookie', '')
    blued_cookie = read_config_value(config, 'Cookie', 'blued_cookie', '')
    afreecatv_cookie = read_config_value(config, 'Cookie', 'afreecatv_cookie', '')

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

    # 这里是控制TS分段大小
    if split_size < 5:
        split_size = 5  # 分段大小最低不能小于5m
    split_byte_sizes = split_size * 1024 * 1024  # 分割视频大小,转换为字节


    def transform_int_to_time(seconds):
        m, s = divmod(seconds, 60)
        h, m = divmod(m, 60)
        return f"{h}:{m:02d}:{s:02d}"


    # 读取url_config.ini文件
    try:
        with open(url_config_file, "r", encoding=encoding) as file:
            for line in file:
                line = line.strip()
                if line.startswith("#") or len(line) < 20:
                    continue

                if re.search('[,，]', line):
                    split_line = re.split('[,，]', line)
                else:
                    split_line = [line, '']
                url = split_line[0]

                if ('http://' not in url) and ('https://' not in url):
                    url = 'https://' + url

                url_host = url.split('/')[2]
                host_list = [
                    'live.douyin.com',
                    'v.douyin.com',
                    'www.tiktok.com',
                    'live.kuaishou.com',
                    'www.huya.com',
                    'www.douyu.com',
                    'www.yy.com',
                    'live.bilibili.com',
                    'www.xiaohongshu.com',
                    'www.bigo.tv',
                    'app.blued.cn',
                    'play.afreecatv.com',
                    'm.afreecatv.com'
                ]
                if url_host in host_list:
                    new_line = (url, split_line[1])
                    url_tuples_list.append(new_line)
                else:
                    print(f"{url} 未知链接.此条跳过")

        while len(name_list):
            a = name_list.pop()
            replace_words = a.split('|')
            if replace_words[0] != replace_words[1]:
                update_file(url_config_file, replace_words[0], replace_words[1])

        if len(url_tuples_list) > 0:
            text_no_repeat_url = list(set(url_tuples_list))
        if len(text_no_repeat_url) > 0:
            for url_tuple in text_no_repeat_url:
                if url_tuple[0] in not_record_list:
                    continue

                if url_tuple[0] not in runing_list:
                    if not first_start:
                        print(f"新增链接: {url_tuple[0]}")
                    monitoring += 1
                    args = [url_tuple, monitoring]
                    # TODO: 执行开始录制的操作
                    create_var['thread' + str(monitoring)] = threading.Thread(target=start_record, args=args)
                    create_var['thread' + str(monitoring)].daemon = True
                    create_var['thread' + str(monitoring)].start()
                    runing_list.append(url_tuple[0])
                    time.sleep(local_delay_default)
        url_tuples_list = []
        first_start = False

    except Exception as e:
        print(f"错误信息:{e}\r\n发生错误的行数: {e.__traceback__.tb_lineno}")
        logger.warning(f"错误信息: {e} 发生错误的行数: {e.__traceback__.tb_lineno}")

    if first_run:
        t = threading.Thread(target=display_info, args=(), daemon=True)
        t.start()
        t2 = threading.Thread(target=change_max_connect, args=(), daemon=True)
        t2.start()

        first_run = False

    time.sleep(3)