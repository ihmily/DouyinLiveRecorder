#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
消息推送模块

支持多种消息推送渠道，用于直播状态通知：
- 钉钉群机器人
- 微信（Server酱/WeChat）
- 邮件 (SMTP)
- Telegram Bot
- Bark (iOS)
- NTFY (通知服务)
- PushPlus (推送加)

每个推送函数返回格式：{"success": [...], "error": [...]}

Author: Hmily
GitHub: https://github.com/ihmily
Date: 2023-09-03 19:18:36
Update: 2025-01-23 17:16:12
Copyright (c) 2023-2024 by Hmily, All Rights Reserved.
"""
import json
import base64
import http.client
import urllib.request
import urllib.error
import smtplib
from email.header import Header
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import src.logger  # pyright: ignore[reportUnusedImport]  # trigger loguru config side effects
from loguru import logger

# 配置 HTTP 客户端（不使用代理，防止本地推送被代理干扰
no_proxy_handler = urllib.request.ProxyHandler({})
opener = urllib.request.build_opener(no_proxy_handler)
headers: dict[str, str] = {'Content-Type': 'application/json'}


def dingtalk(url: str, content: str, number: str | None = None, is_atall: bool = False) -> dict[str, list[str | int]]:
    """钉钉群机器人推送
    
    参数:
        url: 钉钉机器人 Webhook 地址（支持多个，用逗号或中文逗号分隔
        content: 推送消息内容
        number: 要 @ 的手机号（可选
        is_atall: 是否 @ 所有人
        
    返回:
        dict: {"success": [...成功地址...], "error": [...失败地址...]}
    """
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
            response: http.client.HTTPResponse = opener.open(req, timeout=10)
            json_str = response.read().decode('utf-8')
            json_data = json.loads(json_str)
            if json_data['errcode'] == 0:
                success.append(api)
            else:
                error.append(api)
                logger.warning(f'钉钉推送失败, 推送地址：{api}, {json_data["errmsg"]}')
        except Exception as e:
            error.append(api)
            logger.warning(f'钉钉推送失败, 推送地址：{api}, 错误信息:{e}')
    return {"success": success, "error": error}


def xizhi(url: str, title: str, content: str) -> dict[str, list[str | int]]:
    """微信推送（Server酱/WeChat）
    
    参数:
        url: Server酱 API 地址（支持多个
        title: 消息标题
        content: 消息内容
        
    返回:
        dict: {"success": [...成功地址...], "error": [...失败地址...]}
    """
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
                logger.warning(f'微信推送失败, 推送地址：{api}, 失败信息：{json_data["msg"]}')
        except Exception as e:
            error.append(api)
            logger.warning(f'微信推送失败, 推送地址：{api}, 错误信息:{e}')
    return {"success": success, "error": error}


def send_email(email_host: str, login_email: str, email_pass: str, sender_email: str, sender_name: str,
               to_email: str, title: str, content: str, smtp_port: str | None = None,
               open_ssl: bool = True) -> dict[str, list[str]]:
    """邮件推送（SMTP协议）
    
    参数:
        email_host: SMTP 服务器地址
        login_email: 登录邮箱
        email_pass: 邮箱密码/授权码
        sender_email: 发件人邮箱
        sender_name: 发件人名称
        to_email: 收件人邮箱（支持多个
        title: 邮件标题
        content: 邮件内容
        smtp_port: SMTP 端口（可选，SSL默认465，非SSL默认25
        open_ssl: 是否使用 SSL/TLS
        
    返回:
        dict: {"success": [...成功邮箱...], "error": [...失败邮箱...]}
    """
    receivers = to_email.replace('，', ',').split(',') if to_email.strip() else []
    smtp_obj = None

    try:
        message = MIMEMultipart()
        send_name = base64.b64encode(sender_name.encode("utf-8")).decode()
        message['From'] = f'=?UTF-8?B?{send_name}?= <{sender_email}>'
        message['Subject'] = str(Header(title, 'utf-8'))
        if len(receivers) == 1:
            message['To'] = receivers[0]

        t_apart = MIMEText(content, 'plain', 'utf-8')
        message.attach(t_apart)

        if open_ssl:
            port = int(smtp_port) if smtp_port else 465
            smtp_obj = smtplib.SMTP_SSL(email_host, port)
        else:
            port = int(smtp_port) if smtp_port else 25
            smtp_obj = smtplib.SMTP(email_host, port)
        smtp_obj.login(login_email, email_pass)
        smtp_obj.sendmail(sender_email, receivers, message.as_string())
        return {"success": receivers, "error": []}
    except smtplib.SMTPException as e:
        logger.warning(f'邮件推送失败, 推送邮箱：{to_email}, 错误信息:{e}')
        return {"success": [], "error": receivers}
    except Exception as e:
        logger.warning(f'邮件推送失败, 推送邮箱：{to_email}, 错误信息:{e}')
        return {"success": [], "error": receivers}
    finally:
        if smtp_obj:
            try:
                smtp_obj.quit()
            except smtplib.SMTPException:
                pass


def tg_bot(chat_id: int, token: str, content: str) -> dict[str, list[str | int]]:
    """Telegram Bot 推送
    
    参数:
        chat_id: Telegram 聊天/群组 ID
        token: Bot Token
        content: 推送内容
        
    返回:
        dict: {"success": [1] 或 [], "error": [] 或 [1]}
    """
    try:
        json_data = {
            "chat_id": chat_id,
            'text': content
        }
        url = f'https://api.telegram.org/bot{token}/sendMessage'
        data = json.dumps(json_data).encode('utf-8')
        req = urllib.request.Request(url, data=data, headers=headers)
        response = opener.open(req, timeout=15)
        json_str = response.read().decode('utf-8')
        json.loads(json_str)
        return {"success": [1], "error": []}
    except Exception as e:
        logger.warning(f'tg推送失败, 聊天ID：{chat_id}, 错误信息:{e}')
        return {"success": [], "error": [1]}


def bark(api: str, title: str = "message", content: str = 'test', level: str = "active",
         badge: int = 1, auto_copy: int = 1, sound: str = "", icon: str = "", group: str = "",
         is_archive: int = 1, url: str = "") -> dict[str, list[str | int]]:
    """Bark 推送（iOS 通知
    
    参数:
        api: Bark API 地址（格式：https://your.bark.server/key/
        title: 消息标题
        content: 消息内容
        level: 通知级别（active/timeout/passive
        badge: 应用角标数字
        auto_copy: 是否自动复制内容
        sound: 通知声音
        icon: 图标 URL
        group: 消息分组
        is_archive: 是否自动归档
        url: 点击通知跳转的 URL
        
    返回:
        dict: {"success": [...成功地址...], "error": [...失败地址...]}
    """
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
                logger.warning(f'Bark推送失败, 推送地址：{_api}, 失败信息：{json_data["message"]}')
        except Exception as e:
            error.append(_api)
            logger.warning(f'Bark推送失败, 推送地址：{_api}, 错误信息:{e}')
    return {"success": success, "error": error}


def ntfy(api: str, title: str = "message", content: str = 'test', tags: str | list[str] = 'tada', priority: int = 3,
         action_url: str = "", attach: str = "", filename: str = "", click: str = "", icon: str = "",
         delay: str = "", email: str = "", call: str = "") -> dict[str, list[str | int]]:
    """NTFY 推送（跨平台通知服务
    
    参数:
        api: NTFY API 地址（格式：https://ntfy.sh/your-topic
        title: 消息标题
        content: 消息内容
        tags: 标签/表情（支持多个
        priority: 优先级（1-5，5最高
        action_url: 点击通知跳转的 URL
        attach: 附件 URL
        filename: 附件文件名
        click: 点击 URL
        icon: 图标 URL
        delay: 延迟发送（如 30s, 10m
        email: 邮件通知
        call: 电话通知
        
    返回:
        dict: {"success": [...成功地址...], "error": [...失败地址...]}
    """
    success = []
    error = []
    api_list = api.replace('，', ',').split(',') if api.strip() else []
    if isinstance(tags, str):
        tags = tags.replace('，', ',').split(',') if tags else ['partying_face']
    elif not tags:
        tags = ['partying_face']
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
                logger.warning(f'ntfy推送失败, 推送地址：{_api}, 失败信息：{json_data["error"]}')
        except urllib.error.HTTPError as e:
            error.append(_api)
            try:
                error_msg = e.read().decode("utf-8")
                error_detail = json.loads(error_msg).get("error", str(e))
            except Exception:
                error_detail = str(e)
            logger.warning(f'ntfy推送失败, 推送地址：{_api}, 错误信息:{error_detail}')
        except Exception as e:
            error.append(_api)
            logger.warning(f'ntfy推送失败, 推送地址：{_api}, 错误信息:{e}')
    return {"success": success, "error": error}


def pushplus(token: str, title: str, content: str) -> dict[str, list[str | int]]:
    """PushPlus 推送（推送加
    
    参数:
        token: PushPlus Token（支持多个
        title: 消息标题
        content: 消息内容
        
    返回:
        dict: {"success": [...成功Token...], "error": [...失败Token...]}
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
                logger.warning(f'PushPlus推送失败, Token：{_token}, 失败信息：{json_data.get("msg", "未知错误")}')
        except Exception as e:
            error.append(_token)
            logger.warning(f'PushPlus推送失败, Token：{_token}, 错误信息:{e}')

    return {"success": success, "error": error}


if __name__ == '__main__':
    send_title = '直播通知'
    send_content = '张三 开播了！'

    webhook_api = ''
    phone_number = ''
    is_atall = ''
    # dingtalk(webhook_api, send_content, phone_number)

    xizhi_api = 'https://xizhi.qqoq.net/xxxxxxxxx.send'
    # xizhi(xizhi_api, send_content)

    tg_token = ''
    tg_chat_id = 000000
    # tg_bot(tg_chat_id, tg_token, send_content)

    # send_email(
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

    pushplus_token = ''
    # pushplus(pushplus_token, send_title, send_content)
