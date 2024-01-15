# -*- coding: utf-8 -*-

"""
Author: Hmily
GitHub: https://github.com/ihmily
Date: 2023-09-03 19:18:36
Update: 2024-01-16 02:31:36
Copyright (c) 2023 by Hmily, All Rights Reserved.
"""

from typing import Dict, Any, Optional
import json
import urllib.request
from utils import trace_error_decorator

no_proxy_handler = urllib.request.ProxyHandler({})
opener = urllib.request.build_opener(no_proxy_handler)
headers: Dict[str, str] = {'Content-Type': 'application/json'}


@trace_error_decorator
def dingtalk(url: str, content: str, phone_number: Optional[str] = '') -> Dict[str, Any]:
    json_data = {
        'msgtype': 'text',
        'text': {
            'content': '直播间状态更新：\n' + content,
        },
        "at": {
            "atMobiles": [
                phone_number  # 添加这个手机号，可以被@通知（必须要在群里）
            ],
        },
    }
    data = json.dumps(json_data).encode('utf-8')
    req = urllib.request.Request(url, data=data, headers=headers)
    response = opener.open(req, timeout=10)
    json_str = response.read().decode('utf-8')
    json_data = json.loads(json_str)
    return json_data


@trace_error_decorator
def xizhi(url: str, content: str) -> Dict[str, Any]:
    json_data = {
        'title': '直播间状态更新',
        'content': content
    }
    data = json.dumps(json_data).encode('utf-8')
    req = urllib.request.Request(url, data=data, headers=headers)
    response = opener.open(req, timeout=10)
    json_str = response.read().decode('utf-8')
    json_data = json.loads(json_str)
    return json_data


@trace_error_decorator
def tg_bot(chat_id: int, token: str, content: str) -> Dict[str, Any]:
    json_data = {
        "chat_id": chat_id,
        'text': content
    }
    url = f'https://api.telegram.org/bot{token}/sendMessage'
    data = json.dumps(json_data).encode('utf-8')
    req = urllib.request.Request(url, data=data, headers=headers)
    response = urllib.request.urlopen(req, timeout=15)
    json_str = response.read().decode('utf-8')
    json_data = json.loads(json_str)
    return json_data


if __name__ == '__main__':
    content = '张三 开播了！'  # 推送内容

    # 钉钉推送通知
    webhook_api = ''  # 替换成自己Webhook链接,参考文档：https://open.dingtalk.com/document/robots/custom-robot-access
    phone_number = ''  # 被@用户的手机号码
    # dingtalk(webhook_api, content, phone_number)

    # 微信推送通知
    xizhi_api = 'https://xizhi.qqoq.net/XZa5a4a224987c88ab828acbcc0aa4c853.send'  # 替换成自己的单点推送接口,获取地址：https://xz.qqoq.net/#/admin/one
    # xizhi(xizhi_api, content)

    # telegram推送通知
    token = ''  # tg搜索"BotFather"获取的token值
    chat_id = 000000  # tg搜索"userinfobot"获取的chat_id值，即可发送推送消息给你自己，如果下面的是群组id则发送到群
    # tg_bot(chat_id, token, content)
