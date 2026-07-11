#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 消息推送模块 - 支持多种消息推送渠道用于直播状态通知

import json
import base64
import http.client
import urllib.request
import urllib.error
import smtplib
from email.header import Header
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import src.logger  # trigger loguru config side effects
from loguru import logger

# 配置 HTTP 客户端（不使用代理，防止本地推送被代理干扰）
no_proxy_handler: urllib.request.ProxyHandler = urllib.request.ProxyHandler({})
opener: urllib.request.OpenerDirector = urllib.request.build_opener(no_proxy_handler)
headers: dict[str, str] = {'Content-Type': 'application/json'}


def dingtalk(url: str, content: str, number: str | None = None, is_atall: bool = False) -> dict[str, list[str | int]]:
    # 钉钉群机器人推送
    success = []
    error = []
    api_list = url.replace('，', ',').split(',') if url.strip() else []
    for api in api_list:
        json_data = {
            'msgtype': 'text',
            'text': {'content': content},
            "at": {"atMobiles": [number], "isAtAll": is_atall},
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
    # 微信推送（Server酱/WeChat）
    success = []
    error = []
    api_list = url.replace('，', ',').split(',') if url.strip() else []
    for api in api_list:
        json_data = {'title': title, 'content': content}
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
    # 邮件推送（SMTP协议）
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
    # Telegram Bot 推送
    try:
        json_data = {"chat_id": chat_id, 'text': content}
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
    # Bark 推送（iOS 通知）
    success = []
    error = []
    api_list = api.replace('，', ',').split(',') if api.strip() else []
    for _api in api_list:
        json_data = {
            "title": title, "body": content, "level": level, "badge": badge, "autoCopy": auto_copy,
            "sound": sound, "icon": icon, "group": group, "isArchive": is_archive, "url": url
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
    # NTFY 推送（跨平台通知服务）
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
            "topic": topic, "title": title, "message": content, "tags": tags, "priority": priority,
            "attach": attach, "filename": filename, "click": click, "actions": actions,
            "markdown": False, "icon": icon, "delay": delay, "email": email, "call": call
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
    # PushPlus 推送
    success = []
    error = []
    token_list = token.replace('，', ',').split(',') if token.strip() else []

    for _token in token_list:
        json_data = {'token': _token, 'title': title, 'content': content}

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
