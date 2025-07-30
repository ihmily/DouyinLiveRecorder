# -*- coding: utf-8 -*-

"""
Author: Hmily
GitHub: https://github.com/ihmily
Date: 2023-09-03 19:18:36
Update: 2025-01-23 17:16:12
Copyright (c) 2023-2024 by Hmily, All Rights Reserved.
"""
from typing import Dict, Any
import json
import base64
import urllib.request
import urllib.error
import smtplib
from email.header import Header
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

no_proxy_handler = urllib.request.ProxyHandler({})
opener = urllib.request.build_opener(no_proxy_handler)
headers: Dict[str, str] = {'Content-Type': 'application/json'}


def dingtalk(url: str, content: str, number: str = None, is_atall: bool = False) -> Dict[str, Any]:
    success = []
    error = []
    api_list = url.replace('，', ',').split(',') if url.strip() else []
    for api in api_list:
        json_data = {
            'msgtype': 'text',
            'text': {
                'content': content,
            },
            "at": {
                "atMobiles": [
                    number
                ],
                "isAtAll": is_atall
            },
        }
        try:
            data = json.dumps(json_data).encode('utf-8')
            req = urllib.request.Request(api, data=data, headers=headers)
            response = opener.open(req, timeout=10)
            json_str = response.read().decode('utf-8')
            json_data = json.loads(json_str)
            if json_data['errcode'] == 0:
                success.append(api)
            else:
                error.append(api)
                print(f'钉钉推送失败, 推送地址：{api}, {json_data["errmsg"]}')
        except Exception as e:
            error.append(api)
            print(f'钉钉推送失败, 推送地址：{api}, 错误信息:{e}')
    return {"success": success, "error": error}


def xizhi(url: str, title: str, content: str) -> Dict[str, Any]:
    success = []
    error = []
    api_list = url.replace('，', ',').split(',') if url.strip() else []
    for api in api_list:
        json_data = {
            'title': title,
            'content': content
        }
        try:
            data = json.dumps(json_data).encode('utf-8')
            req = urllib.request.Request(api, data=data, headers=headers)
            response = opener.open(req, timeout=10)
            json_str = response.read().decode('utf-8')
            json_data = json.loads(json_str)
            if json_data['code'] == 200:
                success.append(api)
            else:
                error.append(api)
                print(f'微信推送失败, 推送地址：{api}, 失败信息：{json_data["msg"]}')
        except Exception as e:
            error.append(api)
            print(f'微信推送失败, 推送地址：{api}, 错误信息:{e}')
    return {"success": success, "error": error}


def send_email(email_host: str, login_email: str, email_pass: str, sender_email: str, sender_name: str,
               to_email: str, title: str, content: str, smtp_port: str = None, open_ssl: bool = True) -> Dict[str, Any]:
    receivers = to_email.replace('，', ',').split(',') if to_email.strip() else []

    try:
        message = MIMEMultipart()
        send_name = base64.b64encode(sender_name.encode("utf-8")).decode()
        message['From'] = f'=?UTF-8?B?{send_name}?= <{sender_email}>'
        message['Subject'] = Header(title, 'utf-8')
        if len(receivers) == 1:
            message['To'] = receivers[0]

        t_apart = MIMEText(content, 'plain', 'utf-8')
        message.attach(t_apart)

        if open_ssl:
            smtp_port = int(smtp_port) or 465
            smtp_obj = smtplib.SMTP_SSL(email_host, smtp_port)
        else:
            smtp_port = int(smtp_port) or 25
            smtp_obj = smtplib.SMTP(email_host, smtp_port)
        smtp_obj.login(login_email, email_pass)
        smtp_obj.sendmail(sender_email, receivers, message.as_string())
        return {"success": receivers, "error": []}
    except smtplib.SMTPException as e:
        print(f'邮件推送失败, 推送邮箱：{to_email}, 错误信息:{e}')
        return {"success": [], "error": receivers}


def tg_bot(chat_id: int, token: str, content: str) -> Dict[str, Any]:
    try:
        json_data = {
            "chat_id": chat_id,
            'text': content
        }
        url = f'https://api.telegram.org/bot{token}/sendMessage'
        data = json.dumps(json_data).encode('utf-8')
        req = urllib.request.Request(url, data=data, headers=headers)
        response = urllib.request.urlopen(req, timeout=15)
        json_str = response.read().decode('utf-8')
        _json_data = json.loads(json_str)
        return {"success": [1], "error": []}
    except Exception as e:
        print(f'tg推送失败, 聊天ID：{chat_id}, 错误信息:{e}')
        return {"success": [], "error": [1]}


def bark(api: str, title: str = "message", content: str = 'test', level: str = "active",
         badge: int = 1, auto_copy: int = 1, sound: str = "", icon: str = "", group: str = "",
         is_archive: int = 1, url: str = "") -> Dict[str, Any]:
    success = []
    error = []
    api_list = api.replace('，', ',').split(',') if api.strip() else []
    for _api in api_list:
        json_data = {
            "title": title,
            "body": content,
            "level": level,
            "badge": badge,
            "autoCopy": auto_copy,
            "sound": sound,
            "icon": icon,
            "group": group,
            "isArchive": is_archive,
            "url": url
        }
        try:
            data = json.dumps(json_data).encode('utf-8')
            req = urllib.request.Request(_api, data=data, headers=headers)
            response = opener.open(req, timeout=10)
            json_str = response.read().decode("utf-8")
            json_data = json.loads(json_str)
            if json_data['code'] == 200:
                success.append(_api)
            else:
                error.append(_api)
                print(f'Bark推送失败, 推送地址：{_api}, 失败信息：{json_data["message"]}')
        except Exception as e:
            error.append(api)
            print(f'Bark推送失败, 推送地址：{_api}, 错误信息:{e}')
    return {"success": success, "error": error}


def ntfy(api: str, title: str = "message", content: str = 'test', tags: str = 'tada', priority: int = 3,
         action_url: str = "", attach: str = "", filename: str = "", click: str = "", icon: str = "",
         delay: str = "", email: str = "", call: str = "") -> Dict[str, Any]:
    success = []
    error = []
    api_list = api.replace('，', ',').split(',') if api.strip() else []
    tags = tags.replace('，', ',').split(',') if tags else ['partying_face']
    actions = [{"action": "view", "label": "view live", "url": action_url}] if action_url else []
    for _api in api_list:
        server, topic = _api.rsplit('/', maxsplit=1)
        json_data = {
            "topic": topic,
            "title": title,
            "message": content,
            "tags": tags,
            "priority": priority,
            "attach": attach,
            "filename": filename,
            "click": click,
            "actions": actions,
            "markdown": False,
            "icon": icon,
            "delay": delay,
            "email": email,
            "call": call
        }

        try:
            data = json.dumps(json_data, ensure_ascii=False).encode('utf-8')
            req = urllib.request.Request(server, data=data, headers=headers)
            response = opener.open(req, timeout=10)
            json_str = response.read().decode("utf-8")
            json_data = json.loads(json_str)
            if "error" not in json_data:
                success.append(_api)
            else:
                error.append(_api)
                print(f'ntfy推送失败, 推送地址：{_api}, 失败信息：{json_data["error"]}')
        except urllib.error.HTTPError as e:
            error.append(_api)
            error_msg = e.read().decode("utf-8")
            print(f'ntfy推送失败, 推送地址：{_api}, 错误信息:{json.loads(error_msg)["error"]}')
        except Exception as e:
            error.append(api)
            print(f'ntfy推送失败, 推送地址：{_api}, 错误信息:{e}')
    return {"success": success, "error": error}


def pushplus(token: str, title: str, content: str) -> Dict[str, Any]:
    """
    PushPlus推送通知
    API文档: https://www.pushplus.plus/doc/
    """
    success = []
    error = []
    token_list = token.replace('，', ',').split(',') if token.strip() else []
    
    for _token in token_list:
        json_data = {
            'token': _token,
            'title': title,
            'content': content
        }
        
        try:
            url = 'https://www.pushplus.plus/send'
            data = json.dumps(json_data).encode('utf-8')
            req = urllib.request.Request(url, data=data, headers=headers)
            response = opener.open(req, timeout=10)
            json_str = response.read().decode('utf-8')
            json_data = json.loads(json_str)
            
            if json_data.get('code') == 200:
                success.append(_token)
            else:
                error.append(_token)
                print(f'PushPlus推送失败, Token：{_token}, 失败信息：{json_data.get("msg", "未知错误")}')
        except Exception as e:
            error.append(_token)
            print(f'PushPlus推送失败, Token：{_token}, 错误信息:{e}')
    
    return {"success": success, "error": error}


if __name__ == '__main__':
    send_title = '直播通知'  # 标题
    send_content = '张三 开播了！'  # 推送内容

    # 钉钉推送通知
    webhook_api = ''  # 替换成自己Webhook链接,参考文档：https://open.dingtalk.com/document/robots/custom-robot-access
    phone_number = ''  # 被@用户的手机号码
    is_atall = ''  # 是否@全体
    # dingtalk(webhook_api, send_content, phone_number)

    # 微信推送通知
    # 替换成自己的单点推送接口,获取地址：https://xz.qqoq.net/#/admin/one
    # 当然也可以使用其他平台API 如server酱 使用方法一样
    xizhi_api = 'https://xizhi.qqoq.net/xxxxxxxxx.send'
    # xizhi(xizhi_api, send_content)

    # telegram推送通知
    tg_token = ''  # tg搜索"BotFather"获取的token值
    tg_chat_id = 000000  # tg搜索"userinfobot"获取的chat_id值，即可发送推送消息给你自己，如果下面的是群组id则发送到群
    # tg_bot(tg_chat_id, tg_token, send_content)

    # email_message(
    #     email_host="smtp.qq.com",
    #     login_email="",
    #     email_pass="",
    #     sender_email="",
    #     sender_name="",
    #     to_email="",
    #     title="",
    #     content="",
    # )

    bark_url = 'https://xxx.xxx.com/key/'
    # bark(bark_url, send_title, send_content)

    ntfy(
        api="https://ntfy.sh/xxxxx",
        title="直播推送",
        content="xxx已开播",
    )

    # PushPlus推送通知
    pushplus_token = ''  # 替换成自己的PushPlus Token，获取地址：https://www.pushplus.plus/
    # pushplus(pushplus_token, send_title, send_content)
