#!/usr/bin/env python3
# -*- encoding: utf-8 -*-
# 直播流地址获取模块 - 从各平台解析获取直播流地址，支持多种画质选择

# Author: Hmily
# GitHub: https://github.com/ihmily
# Date: 2023-07-15 23:15:00
# Update: 2025-02-06 02:28:00
# Copyright (c) 2023-2025 by Hmily, All Rights Reserved.
# Function: Get live stream data.

import base64
import hashlib
import json
import time
import random
import re
import urllib.parse
from .utils import trace_error_decorator
from .spider import (
    get_douyu_stream_data, get_bilibili_stream_data
)
from .http_clients.async_http import get_response_status

QUALITY_MAPPING = {"OD": 0, "BD": 0, "UHD": 1, "HD": 2, "SD": 3, "LD": 4}
QUALITY_MAPPING_BIT = {'OD': 99999, 'BD': 4000, 'UHD': 2000, 'HD': 1000, 'SD': 800, 'LD': 600}


def _pad_list(url_list: list, min_length: int = 5) -> list:
    # 将列表填充到指定最小长度
    if not url_list:
        return url_list
    while len(url_list) < min_length:
        url_list.append(url_list[-1])
    return url_list


def get_quality_index(quality) -> tuple:
    # 解析画质参数，返回画质名称和索引
    if not quality:
        return list(QUALITY_MAPPING.items())[0]

    quality_str = str(quality).upper()
    if quality_str.isdigit():
        quality_int = int(quality_str[0])
        keys = list(QUALITY_MAPPING.keys())
        if quality_int >= len(keys):
            quality_int = 0
        quality_str = keys[quality_int]
    if quality_str not in QUALITY_MAPPING:
        quality_str = list(QUALITY_MAPPING.keys())[0]
    return quality_str, QUALITY_MAPPING[quality_str]


@trace_error_decorator
async def get_douyin_stream_url(json_data: dict, video_quality: str | None = None, proxy_addr: str | None = None) -> dict:
    # 获取抖音直播流URL
    anchor_name = json_data.get('anchor_name')
    result = {"anchor_name": anchor_name, "is_live": False}
    status = json_data.get("status", 4)

    if status == 2:
        stream_url = json_data['stream_url']
        flv_url_dict = stream_url['flv_pull_url']
        flv_url_list: list = list(flv_url_dict.values())
        m3u8_url_dict = stream_url['hls_pull_url_map']
        m3u8_url_list: list = list(m3u8_url_dict.values())

        _pad_list(flv_url_list)
        _pad_list(m3u8_url_list)

        video_quality, quality_index = get_quality_index(video_quality)
        m3u8_url = m3u8_url_list[quality_index]
        flv_url = flv_url_list[quality_index]
        hevc_flv_url = stream_url.get('hevc_flv_url')
        # 原画优先 HEVC：若 ORIGIN m3u8 已是 HEVC 则直接用；否则用 HTML 提取的 HEVC FLV
        m3u8_codec = urllib.parse.parse_qs(urllib.parse.urlparse(m3u8_url).query).get('codec', [''])[0]
        m3u8_is_hevc = 'h265' in m3u8_codec.lower() or 'hevc' in m3u8_codec.lower()
        use_hevc_flv = quality_index == 0 and bool(hevc_flv_url) and not m3u8_is_hevc
        if use_hevc_flv:
            flv_url = hevc_flv_url
        ok = await get_response_status(url=m3u8_url, proxy_addr=proxy_addr)
        if not ok:
            index = quality_index + 1 if quality_index < 4 else quality_index - 1
            m3u8_url = m3u8_url_list[index]
            if not use_hevc_flv:
                flv_url = flv_url_list[index]
        result |= {
            'is_live': True,
            'title': json_data['title'],
            'quality': video_quality,
            'm3u8_url': m3u8_url,
            'flv_url': flv_url,
            'record_url': flv_url if use_hevc_flv else (m3u8_url or flv_url),
        }
    return result


@trace_error_decorator
async def get_tiktok_stream_url(json_data: dict | None, video_quality: str | None = None, proxy_addr: str | None = None) -> dict:
    # 获取TikTok直播流URL
    if not json_data:
        return {"anchor_name": None, "is_live": False}

    def get_video_quality_url(stream, q_key) -> list:
        # 从流列表中按画质索引选择 URL
        play_list = []
        for key in stream:
            url_info = stream[key]['main']
            sdk_params = url_info['sdk_params']
            sdk_params = json.loads(sdk_params)
            vbitrate = int(sdk_params['vbitrate'])
            v_codec = sdk_params.get('VCodec', '')

            play_url = ''
            if url_info.get(q_key):
                if url_info[q_key].endswith(".flv") or url_info[q_key].endswith(".m3u8"):
                    play_url = url_info[q_key] + '?codec=' + v_codec
                else:
                    play_url = url_info[q_key] + '&codec=' + v_codec

            resolution = sdk_params['resolution']
            if vbitrate != 0 and resolution:
                width, height = map(int, resolution.split('x'))
                play_list.append({'url': play_url, 'vbitrate': vbitrate, 'resolution': (width, height)})

        play_list.sort(key=lambda x: (-x['vbitrate'], -x['resolution'][0], -x['resolution'][1]))
        return play_list

    live_room = json_data['LiveRoom']['liveRoomUserInfo']
    user = live_room['user']
    anchor_name = f"{user['nickname']}-{user['uniqueId']}"
    status = user.get("status", 4)

    result = {"anchor_name": anchor_name, "is_live": False}

    if status == 2:
        stream_data = live_room['liveRoom']['streamData']['pull_data']['stream_data']
        stream_data = json.loads(stream_data).get('data', {})
        flv_url_list = get_video_quality_url(stream_data, 'flv')
        m3u8_url_list = get_video_quality_url(stream_data, 'hls')

        if not flv_url_list and not m3u8_url_list:
            return result

        _pad_list(flv_url_list)
        _pad_list(m3u8_url_list)
        video_quality, quality_index = get_quality_index(video_quality)
        quality_index = min(quality_index, len(flv_url_list) - 1) if flv_url_list else 0
        m3u8_quality_index = min(quality_index, len(m3u8_url_list) - 1) if m3u8_url_list else 0
        flv_dict: dict = flv_url_list[quality_index] if flv_url_list else {'url': ''}
        m3u8_dict: dict = m3u8_url_list[m3u8_quality_index] if m3u8_url_list else {'url': ''}

        check_url = m3u8_dict.get('url') or flv_dict.get('url')
        if not check_url:
            ok = False
        else:
            ok = await get_response_status(url=check_url, proxy_addr=proxy_addr, http2=False)

        if not ok:
            fallback_index = quality_index + 1 if quality_index < 4 else max(quality_index - 1, 0)
            if flv_url_list:
                fallback_index = min(fallback_index, len(flv_url_list) - 1)
                flv_dict = flv_url_list[fallback_index]
            if m3u8_url_list:
                m3u8_fallback = min(fallback_index, len(m3u8_url_list) - 1)
                m3u8_dict = m3u8_url_list[m3u8_fallback]

        flv_url = flv_dict.get('url', '')
        m3u8_url = m3u8_dict.get('url', '')
        result |= {
            'is_live': True,
            'title': live_room['liveRoom']['title'],
            'quality': video_quality,
            'm3u8_url': m3u8_url,
            'flv_url': flv_url,
            'record_url': m3u8_url or flv_url,
        }
    return result


@trace_error_decorator
async def get_kuaishou_stream_url(json_data: dict, video_quality: str | None = None) -> dict:
    # 获取快手直播流URL
    if json_data['type'] == 1 and not json_data["is_live"]:
        return json_data
    live_status = json_data['is_live']

    result = {"type": 2, "anchor_name": json_data['anchor_name'], "is_live": live_status}

    if live_status:
        quality, quality_index = get_quality_index(video_quality)
        if 'm3u8_url_list' in json_data:
            m3u8_url_list = json_data['m3u8_url_list'][::-1]
            _pad_list(m3u8_url_list)
            m3u8_url = m3u8_url_list[quality_index]['url']
            result['m3u8_url'] = m3u8_url

        if 'flv_url_list' in json_data:
            if 'bitrate' in json_data['flv_url_list'][0]:
                flv_url_list = json_data['flv_url_list']
                flv_url_list = sorted(flv_url_list, key=lambda x: x['bitrate'], reverse=True)
                quality_str = video_quality.upper() if video_quality else 'OD'
                if quality_str.isdigit():
                    bit_items = list(QUALITY_MAPPING_BIT.items())
                    q_idx = min(int(quality_str[0]), len(bit_items) - 1)
                    video_quality, quality_index_bitrate_value = bit_items[q_idx]
                else:
                    quality_index_bitrate_value = QUALITY_MAPPING_BIT.get(quality_str, 99999)
                    video_quality = quality_str
                quality_index = next(
                    (i for i, x in enumerate(flv_url_list) if x['bitrate'] <= quality_index_bitrate_value), None)
                if quality_index is None:
                    quality_index = len(flv_url_list) - 1
                flv_url = flv_url_list[quality_index]['url']
                result['flv_url'] = flv_url
                result['record_url'] = flv_url
            else:
                flv_url_list = json_data['flv_url_list'][::-1]
                _pad_list(flv_url_list)
                flv_url = flv_url_list[quality_index]['url']
                result |= {'flv_url': flv_url, 'record_url': flv_url}
        result['is_live'] = True
        result['quality'] = quality
    return result


@trace_error_decorator
async def get_huya_stream_url(json_data: dict, video_quality: str | None = None) -> dict:
    # 获取虎牙直播流URL
    game_live_info = json_data['data'][0]['gameLiveInfo']
    live_title = game_live_info['introduction']
    stream_info_list = json_data['data'][0]['gameStreamInfoList']
    anchor_name = game_live_info.get('nick', '')

    result = {"anchor_name": anchor_name, "is_live": False}

    if stream_info_list:
        select_cdn = stream_info_list[0]
        flv_url = select_cdn.get('sFlvUrl')
        stream_name = select_cdn.get('sStreamName')
        flv_url_suffix = select_cdn.get('sFlvUrlSuffix')
        hls_url = select_cdn.get('sHlsUrl')
        hls_url_suffix = select_cdn.get('sHlsUrlSuffix')
        flv_anti_code = select_cdn.get('sFlvAntiCode') or ''

        if not flv_anti_code:
            return result

        def get_anti_code(old_anti_code: str) -> str:
            # 解析虎牙 flv_anti_code 参数为字典
            params_t = 100
            sdk_version = 2403051612
            t13 = int(time.time()) * 1000
            sdk_sid = t13
            init_uuid = (t13 % 10 ** 10 * 1000 + int(1000 * random.random())) % 4294967295
            uid = random.randint(1400000000000, 1400009999999)
            seq_id = uid + sdk_sid
            target_unix_time = (t13 + 110624) // 1000
            ws_time = f"{target_unix_time:x}".lower()
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
        if len(quality_list) > 1 and video_quality not in ["OD", "BD"]:
            pattern = r"(?<=264_)\d+"
            quality_list = list(re.findall(pattern, quality_list[1]))[::-1]
            _pad_list(quality_list)

            video_quality_options = {
                "UHD": quality_list[0],
                "HD": quality_list[1],
                "SD": quality_list[2],
                "LD": quality_list[3]
            }

            if video_quality not in video_quality_options:
                raise ValueError(
                    f"Invalid video quality. Available options are: {', '.join(video_quality_options.keys())}")

            flv_url = flv_url + str(video_quality_options[video_quality])
            m3u8_url = m3u8_url + str(video_quality_options[video_quality])

        result |= {
            'is_live': True,
            'title': live_title,
            'quality': video_quality,
            'm3u8_url': m3u8_url,
            'flv_url': flv_url,
            'record_url': flv_url or m3u8_url
        }
    return result


@trace_error_decorator
async def get_douyu_stream_url(json_data: dict, video_quality: str | None = None, cookies: str = '',
                               proxy_addr: str | None = None) -> dict:
    # 获取斗鱼直播流URL
    if not json_data["is_live"]:
        return {"anchor_name": json_data.get("anchor_name"), "is_live": False}

    video_quality_options = {"OD": '0', "BD": '0', "UHD": '3', "HD": '2', "SD": '1', "LD": '1'}

    rid = str(json_data["room_id"])
    rate = video_quality_options.get(video_quality or '', '0')
    flv_data = await get_douyu_stream_data(rid, rate, cookies=cookies, proxy_addr=proxy_addr)
    rtmp_url = flv_data['data'].get('rtmp_url')
    rtmp_live = flv_data['data'].get('rtmp_live')

    result = {"anchor_name": json_data.get('anchor_name'), "is_live": True, "quality": video_quality}
    if rtmp_live:
        flv_url = f'{rtmp_url}/{rtmp_live}'
        result |= {'flv_url': flv_url, 'record_url': flv_url}
    return result


@trace_error_decorator
async def get_yy_stream_url(json_data: dict) -> dict:
    # 获取YY直播流URL
    anchor_name = json_data.get('anchor_name', '')
    result = {"anchor_name": anchor_name, "is_live": False}
    if 'avp_info_res' in json_data:
        stream_line_addr = json_data['avp_info_res']['stream_line_addr']
        cdn_info = list(stream_line_addr.values())[0]
        flv_url = cdn_info['cdn_info']['url']
        result |= {'is_live': True, 'title': json_data['title'], 'quality': 'OD', 'flv_url': flv_url, 'record_url': flv_url}
    return result


@trace_error_decorator
async def get_bilibili_stream_url(json_data: dict, video_quality: str | None = None,
                                  proxy_addr: str | None = None, cookies: str = '') -> dict:
    # 获取B站直播流URL
    anchor_name = json_data["anchor_name"]
    if not json_data["live_status"]:
        return {"anchor_name": anchor_name, "is_live": False}

    room_url = json_data['room_url']
    video_quality_options = {"OD": '10000', "BD": '400', "UHD": '250', "HD": '150', "SD": '80', "LD": '80'}

    select_quality = video_quality_options.get((video_quality or 'OD').upper(), '10000')
    play_url = await get_bilibili_stream_data(
        room_url, qn=select_quality, platform='web', proxy_addr=proxy_addr, cookies=cookies)
    if not play_url:
        return {"anchor_name": anchor_name, "is_live": False}
    return {'anchor_name': json_data['anchor_name'], 'is_live': True, 'title': json_data['title'], 'quality': video_quality, 'record_url': play_url}


@trace_error_decorator
async def get_netease_stream_url(json_data: dict, video_quality: str | None = None) -> dict:
    # 获取网易CC直播流URL
    if not json_data['is_live']:
        return json_data

    m3u8_url = json_data['m3u8_url']
    flv_url = None
    if json_data.get('stream_list'):
        stream_list = json_data['stream_list']['resolution']
        order = ['blueray', 'ultra', 'high', 'standard']
        sorted_keys = [key for key in order if key in stream_list]
        if not sorted_keys:
            return json_data
        _pad_list(sorted_keys)
        video_quality, quality_index = get_quality_index(video_quality)
        selected_quality = sorted_keys[quality_index]
        flv_url_list = stream_list[selected_quality]['cdn']
        selected_cdn = list(flv_url_list.keys())[0]
        flv_url = flv_url_list[selected_cdn]

    return {
        "is_live": True, "anchor_name": json_data['anchor_name'], "title": json_data['title'],
        'quality': video_quality, "m3u8_url": m3u8_url, "flv_url": flv_url, "record_url": flv_url or m3u8_url
    }


async def get_stream_url(json_data: dict, video_quality: str | None = None, url_type: str = 'm3u8', spec: bool = False,
                         hls_extra_key: str | int | None = None, flv_extra_key: str | int | None = None) -> dict:
    # 通用直播流URL获取函数
    if not json_data['is_live']:
        return json_data

    play_url_list = json_data.get('play_url_list', [])
    if not play_url_list:
        return json_data
    _pad_list(play_url_list)

    video_quality, selected_quality = get_quality_index(video_quality)
    data = {"anchor_name": json_data['anchor_name'], "is_live": True}

    def get_url(key):
        # 从直播流响应中提取流地址
        play_url = play_url_list[selected_quality]
        return play_url[key] if key else play_url

    if url_type == 'all':
        m3u8_url = get_url(hls_extra_key)
        flv_url = get_url(flv_extra_key)
        data |= {"m3u8_url": json_data['m3u8_url'] if spec else m3u8_url, "flv_url": json_data['flv_url'] if spec else flv_url, "record_url": m3u8_url}
    elif url_type == 'm3u8':
        m3u8_url = get_url(hls_extra_key)
        data |= {"m3u8_url": json_data['m3u8_url'] if spec else m3u8_url, "record_url": m3u8_url}
    else:
        flv_url = get_url(flv_extra_key)
        data |= {"flv_url": flv_url, "record_url": flv_url}
    data['title'] = json_data.get('title')
    data['quality'] = video_quality
    return data
