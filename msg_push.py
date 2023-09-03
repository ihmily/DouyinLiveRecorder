"""
Author: Hmily
Github:https://github.com/ihmily
Date: 2023-09-03 19:18:36
Copyright (c) 2023 by Hmily, All Rights Reserved.
"""

import json
import urllib.request

no_proxy_handler = urllib.request.ProxyHandler({})
opener = urllib.request.build_opener(no_proxy_handler)
headers = {
    'Content-Type': 'application/json',
}


def dingtalk(url, content, phone_number=''):
    json_data = {
        'msgtype': 'text',
        'text': {
            'content': '直播间状态更新：\n' + content,
        },
        "at": {
            "atMobiles": [
                phone_number  # 添加这个手机号，可以被@通知（必须要在群里）
            ],
            # "atUserIds": [
            #     "user123"
            # ],
            # "isAtAll": False
        },
    }
    data = json.dumps(json_data).encode('utf-8')
    req = urllib.request.Request(url, data=data, headers=headers)
    response = opener.open(req, timeout=10)
    html_str = response.read().decode('utf-8')
    # print(html_str)
    return html_str


def xizhi(url, content):
    json_data = {
        'title': '直播间状态更新',
        'content': content
    }
    data = json.dumps(json_data).encode('utf-8')
    req = urllib.request.Request(url, data=data, headers=headers)
    response = opener.open(req, timeout=10)
    html_str = response.read().decode('utf-8')
    # print(html_str)
    return html_str


if __name__ == '__main__':
    content = '张三 开播了！'  # 推送内容
    phone_number = ''  # 被@用户的手机号码
    # 替换成自己Webhook链接,参考文档：https://open.dingtalk.com/document/robots/custom-robot-access
    webhook_api = ''
    # dingtalk(webhook_api,content,phone_number)

    # 替换成自己的单点推送接口,获取地址：https://xz.qqoq.net/#/admin/one
    xizhi_api = ''
    # xizhi(xizhi_api,content)
