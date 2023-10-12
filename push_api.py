"""
Author: Hmily
Github:https://github.com/ihmily
Date: 2023-09-03 19:18:36
Copyright (c) 2023 by Hmily, All Rights Reserved.
"""

import json, time
import urllib.request
from webhook_msg_api import FeiShuWebhookMsgeAPI

class PushAPI(object):
    def __init__(self,
                 live_status_push = None,
                 dingtalk_api_url = None,
                 dingtalk_phone_num = None,
                 xizhi_api_url = None,
                 feishu_webhook_url = None,
                 feishu_webhook_secret = None
                 ):
        self.live_status_push = live_status_push
        self.dingtalk_api_url = dingtalk_api_url
        self.dingtalk_phone_num = dingtalk_phone_num
        self.xizhi_api_url = xizhi_api_url

        self.feishu_api = FeiShuWebhookMsgeAPI(webhook=feishu_webhook_url, secrect=feishu_webhook_secret)

        self.no_proxy_handler = urllib.request.ProxyHandler({})
        self.opener = urllib.request.build_opener(self.no_proxy_handler)
        self.headers = {'Content-Type': 'application/json'}

    def notify_live_start(self, live_name, live_url):
        content = f"[开始录制]{live_name}({live_url}) 正在直播中 {time.strftime('%Y-%m-%d %H:%M:%S')}"
        self.nofity(content)

    def notify_live_end(self, live_name, live_url):
        content = f"[录制完毕]{live_name}({live_url}) 直播结束 {time.strftime('%Y-%m-%d %H:%M:%S')}"
        self.nofity(content)

    def nofity(self, content):
        if self.live_status_push != '':
            if '飞书' in self.live_status_push:
                self.feishu_api.send_text_msg(content)
            if '微信' in self.live_status_push:
                self.xizhi(content)
            if '钉钉' in self.live_status_push:
                self.dingtalk(content, self.dingtalk_phone_num)

    def dingtalk(self, content, phone_number=''):
        json_data = {
            'msgtype': 'text',
            'text': { 'content': content },
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
        req = urllib.request.Request(self.dingtalk_api_url, data=data, headers=self.headers)
        response = self.opener.open(req, timeout=10)
        html_str = response.read().decode('utf-8')
        # print(html_str)
        return html_str

    def xizhi(self, content):
        json_data = { 'title': '直播间状态更新', 'content': content }
        data = json.dumps(json_data).encode('utf-8')
        req = urllib.request.Request(self.xizhi_api_url, data=data, headers=self.headers)
        response = self.opener.open(req, timeout=10)
        html_str = response.read().decode('utf-8')
        # print(html_str)
        return html_str
