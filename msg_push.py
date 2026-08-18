#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 消息推送模块 - 支持多种消息推送渠道用于直播状态通知
# 提供钉钉/微信(Server酱)/Telegram/Bark/ntfy/PushPlus 推送及 SMTP 邮件发送，
# 各推送函数接收地址与内容，返回 {"success": [...], "error": [...]}。

import base64
import http.client
import json
import smtplib
import urllib.error
import urllib.request
from email.header import Header
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import cast

from loguru import logger

# 配置 HTTP 客户端（不使用代理，防止本地推送被代理干扰）
no_proxy_handler: urllib.request.ProxyHandler = urllib.request.ProxyHandler({})
opener: urllib.request.OpenerDirector = urllib.request.build_opener(no_proxy_handler)
headers: dict[str, str] = {"Content-Type": "application/json"}


# 脱敏密钥：保留前后各 2 位，其余以 * 遮挡，防日志泄露
def _mask_secret(secret: str) -> str:
    # 脱敏：仅保留前后各 2 位用于排查，其余以 * 遮挡，避免凭证泄露到日志。
    if not secret:
        return ""
    if len(secret) <= 6:
        # 短密钥（如测试 token）遮蔽 1-2 位形同虚设，整体遮蔽
        return "****"
    return f"{secret[:2]}{'*' * (len(secret) - 4)}{secret[-2:]}"


# 脱敏推送地址：隐藏 query 与疑似密钥路径段，仅供日志展示
def _mask_url(url: str) -> str:
    # 脱敏推送地址：隐藏 query 中的 token 与疑似密钥的路径段，避免凭证泄露到日志。
    # 仅用于日志展示，不影响实际请求。
    try:
        from urllib.parse import urlsplit, urlunsplit

        parts = urlsplit(url)
        segs = [s for s in parts.path.split("/") if s]
        masked_segs: list[str] = []
        for seg in segs:
            if seg.startswith("bot") and len(seg) > 4:
                masked_segs.append("bot****")  # Telegram token
            elif seg.endswith(".send") or seg.lower() in ("key", "sendmessage"):
                masked_segs.append("****")
            elif len(seg) > 12 and "sendmessage" not in seg.lower():
                masked_segs.append("****")  # 疑似长密钥（Server酱/Bark 末段）
            elif parts.hostname and parts.hostname.endswith("day.app"):
                masked_segs.append("****")  # Bark key（8 位短密钥，原规则漏遮蔽）
            else:
                masked_segs.append(seg)
        masked_path = "/" + "/".join(masked_segs) if masked_segs else ""
        # 丢弃 query（access_token 等敏感参数）
        return urlunsplit((parts.scheme, parts.netloc, masked_path, "", ""))
    except Exception:
        return _mask_secret(url)


# 钉钉群机器人推送文本消息，支持 @手机号/全体，返回成功与失败地址列表
# 钉钉群机器人推送文本消息，支持 @手机号/全体，返回成功与失败地址列表
def dingtalk(url: str, content: str, number: str | None = None, is_atall: bool = False) -> dict[str, list[str | int]]:
    # 钉钉群机器人推送
    success: list[str | int] = []
    error: list[str | int] = []
    api_list = url.replace("，", ",").split(",") if url.strip() else []
    for api in api_list:
        at_payload: dict[str, object] = {"isAtAll": is_atall}
        if number:
            # 未填手机号时不传 atMobiles，避免序列化为 [null] 被钉钉判非法
            at_payload["atMobiles"] = [number]
        json_data = {
            "msgtype": "text",
            "text": {"content": content},
            "at": at_payload,
        }
        try:
            data = json.dumps(json_data).encode("utf-8")
            req = urllib.request.Request(api, data=data, headers=headers)
            with cast(http.client.HTTPResponse, opener.open(req, timeout=10)) as response:
                json_str = response.read().decode("utf-8")
            resp_data: dict[str, object] = cast(dict[str, object], json.loads(json_str))
            if resp_data.get("errcode") == 0:
                success.append(api)
            else:
                error.append(api)
                logger.warning(f'钉钉推送失败, 推送地址：{_mask_url(api)}, {resp_data.get("errmsg", "未知错误")}')
        except Exception as e:
            error.append(api)
            logger.warning(f"钉钉推送失败, 推送地址：{_mask_url(api)}, 错误信息:{e}")
    return {"success": success, "error": error}


# 通过 Server酱/微信 推送消息（url 为推送地址，title/content 为内容）。
def xizhi(url: str, title: str, content: str) -> dict[str, list[str | int]]:
    # 微信推送（Server酱/WeChat）
    success: list[str | int] = []
    error: list[str | int] = []
    api_list = url.replace("，", ",").split(",") if url.strip() else []
    for api in api_list:
        json_data = {"title": title, "content": content}
        try:
            data = json.dumps(json_data).encode("utf-8")
            req = urllib.request.Request(api, data=data, headers=headers)
            with cast(http.client.HTTPResponse, opener.open(req, timeout=10)) as response:
                json_str = response.read().decode("utf-8")
            resp_data: dict[str, object] = cast(dict[str, object], json.loads(json_str))
            if resp_data.get("code") == 200:
                success.append(api)
            else:
                error.append(api)
                logger.warning(
                    f'微信推送失败, 推送地址：{_mask_url(api)}, 失败信息：{resp_data.get("msg", "未知错误")}'
                )
        except Exception as e:
            error.append(api)
            logger.warning(f"微信推送失败, 推送地址：{_mask_url(api)}, 错误信息:{e}")
    return {"success": success, "error": error}


# 通过 SMTP 发送邮件（支持 SSL/非SSL），返回成功与失败收件人列表
def send_email(
    email_host: str,
    login_email: str,
    email_pass: str,
    sender_email: str,
    sender_name: str,
    to_email: str,
    title: str,
    content: str,
    smtp_port: str | None = None,
    open_ssl: bool = True,
) -> dict[str, list[str]]:
    # 邮件推送（SMTP协议）
    receivers = to_email.replace("，", ",").split(",") if to_email.strip() else []
    smtp_obj: smtplib.SMTP | smtplib.SMTP_SSL | None = None

    try:
        message = MIMEMultipart()
        send_name = base64.b64encode(sender_name.encode("utf-8")).decode()
        message["From"] = f"=?UTF-8?B?{send_name}?= <{sender_email}>"
        message["Subject"] = str(Header(title, "utf-8"))
        if len(receivers) == 1:
            message["To"] = receivers[0]

        t_apart = MIMEText(content, "plain", "utf-8")
        message.attach(t_apart)

        if open_ssl:
            try:
                port = int(smtp_port) if smtp_port else 465
            except ValueError:
                port = 465
            smtp_obj = smtplib.SMTP_SSL(email_host, port, timeout=10)
        else:
            try:
                port = int(smtp_port) if smtp_port else 25
            except ValueError:
                port = 25
            smtp_obj = smtplib.SMTP(email_host, port, timeout=10)
        assert smtp_obj is not None
        _ = smtp_obj.login(login_email, email_pass)
        _ = smtp_obj.sendmail(sender_email, receivers, message.as_string())
        return {"success": receivers, "error": []}
    except smtplib.SMTPException as e:
        logger.warning(f"邮件推送失败, 推送邮箱：{to_email}, 错误信息:{e}")
        return {"success": [], "error": receivers}
    except Exception as e:
        logger.warning(f"邮件推送失败, 推送邮箱：{to_email}, 错误信息:{e}")
        return {"success": [], "error": receivers}
    finally:
        if smtp_obj:
            try:
                _ = smtp_obj.quit()
            except smtplib.SMTPException:
                pass


# Telegram Bot 推送文本消息，返回成功与失败聊天ID列表
def tg_bot(chat_id: str | int, token: str, content: str) -> dict[str, list[str | int]]:
    # Telegram Bot 推送
    # url 在 try 外预绑定，避免构造 json_data 异常时 except 块引用未绑定变量触发 NameError
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        json_data = {"chat_id": chat_id, "text": content}
        data = json.dumps(json_data).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=headers)
        with cast(http.client.HTTPResponse, opener.open(req, timeout=15)) as response:
            json_str = response.read().decode("utf-8")
        resp_data: dict[str, object] = cast(dict[str, object], json.loads(json_str))
        # Telegram 即使返回 2xx，业务失败也会返回 {"ok": false, "description": "..."}
        if resp_data.get("ok") is True:
            return {"success": [str(chat_id)], "error": []}
        error_detail = resp_data.get("description", "未知错误")
        logger.warning(f"tg推送失败, 聊天ID：{chat_id}, 推送地址：{_mask_url(url)}, 失败信息:{error_detail}")
        return {"success": [], "error": [str(chat_id)]}
    except Exception as e:
        logger.warning(f"tg推送失败, 聊天ID：{chat_id}, 推送地址：{_mask_url(url)}, 错误信息:{e}")
        return {"success": [], "error": [str(chat_id)]}


# Bark（iOS）推送通知，返回成功与失败地址列表
def bark(
    api: str,
    title: str = "message",
    content: str = "test",
    level: str = "active",
    badge: int = 1,
    auto_copy: int = 1,
    sound: str = "",
    icon: str = "",
    group: str = "",
    is_archive: int = 1,
    url: str = "",
) -> dict[str, list[str | int]]:
    # Bark 推送（iOS 通知）
    success: list[str | int] = []
    error: list[str | int] = []
    api_list = api.replace("，", ",").split(",") if api.strip() else []
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
            "url": url,
        }
        try:
            data = json.dumps(json_data).encode("utf-8")
            req = urllib.request.Request(_api, data=data, headers=headers)
            with cast(http.client.HTTPResponse, opener.open(req, timeout=10)) as response:
                json_str = response.read().decode("utf-8")
            resp_data: dict[str, object] = cast(dict[str, object], json.loads(json_str))
            if resp_data.get("code") == 200:
                success.append(_api)
            else:
                error.append(_api)
                logger.warning(
                    f'Bark推送失败, 推送地址：{_mask_url(_api)}, 失败信息：{resp_data.get("message", "未知错误")}'
                )
        except Exception as e:
            error.append(_api)
            logger.warning(f"Bark推送失败, 推送地址：{_mask_url(_api)}, 错误信息:{e}")
    return {"success": success, "error": error}


# ntfy 跨平台推送通知（支持 tags/优先级/附件等），返回成功与失败列表
def ntfy(
    api: str,
    title: str = "message",
    content: str = "test",
    tags: str | list[str] = "tada",
    priority: int = 3,
    action_url: str = "",
    attach: str = "",
    filename: str = "",
    click: str = "",
    icon: str = "",
    delay: str = "",
    email: str = "",
    call: str = "",
) -> dict[str, list[str | int]]:
    # NTFY 推送（跨平台通知服务）
    success: list[str | int] = []
    error: list[str | int] = []
    api_list = api.replace("，", ",").split(",") if api.strip() else []
    if isinstance(tags, str):
        tags = tags.replace("，", ",").split(",") if tags else ["partying_face"]
    elif not tags:
        tags = ["partying_face"]
    actions = [{"action": "view", "label": "view live", "url": action_url}] if action_url else []
    for _api in api_list:
        # rsplit 在地址不含 '/' 时会抛 ValueError，需放入 try 块内优雅降级
        try:
            server, topic = _api.rsplit("/", maxsplit=1)
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
                "call": call,
            }

            data = json.dumps(json_data, ensure_ascii=False).encode("utf-8")
            req = urllib.request.Request(server, data=data, headers=headers)
            with cast(http.client.HTTPResponse, opener.open(req, timeout=10)) as response:
                json_str = response.read().decode("utf-8")
            resp_data: dict[str, object] = cast(dict[str, object], json.loads(json_str))
            if "error" not in resp_data:
                success.append(_api)
            else:
                error.append(_api)
                logger.warning(f'ntfy推送失败, 推送地址：{_mask_url(_api)}, 失败信息：{resp_data["error"]}')
        except urllib.error.HTTPError as e:
            error.append(_api)
            try:
                error_msg = e.read().decode("utf-8")
                error_detail = cast(dict[str, object], json.loads(error_msg)).get("error", str(e))
            except Exception:
                error_detail = str(e)
            finally:
                e.close()
            logger.warning(f"ntfy推送失败, 推送地址：{_mask_url(_api)}, 错误信息:{error_detail}")
        except Exception as e:
            error.append(_api)
            logger.warning(f"ntfy推送失败, 推送地址：{_mask_url(_api)}, 错误信息:{e}")
    return {"success": success, "error": error}


# PushPlus 推送（token+title+content），返回成功与失败 token 列表
def pushplus(token: str, title: str, content: str) -> dict[str, list[str | int]]:
    # PushPlus 推送
    success: list[str | int] = []
    error: list[str | int] = []
    token_list = token.replace("，", ",").split(",") if token.strip() else []

    for _token in token_list:
        json_data = {"token": _token, "title": title, "content": content}

        try:
            url = "https://www.pushplus.plus/send"
            data = json.dumps(json_data).encode("utf-8")
            req = urllib.request.Request(url, data=data, headers=headers)
            with cast(http.client.HTTPResponse, opener.open(req, timeout=10)) as response:
                json_str = response.read().decode("utf-8")
            resp_data: dict[str, object] = cast(dict[str, object], json.loads(json_str))

            if resp_data.get("code") == 200:
                success.append(_token)
            else:
                error.append(_token)
                logger.warning(
                    f'PushPlus推送失败, Token：{_mask_secret(_token)}, 失败信息：{resp_data.get("msg", "未知错误")}'
                )
        except Exception as e:
            error.append(_token)
            logger.warning(f"PushPlus推送失败, Token：{_mask_secret(_token)}, 错误信息:{e}")

    return {"success": success, "error": error}


if __name__ == "__main__":
    send_title = "直播通知"
    send_content = "张三 开播了！"

    webhook_api = ""
    phone_number = ""
    is_atall = ""
    # dingtalk(webhook_api, send_content, phone_number)

    xizhi_api = "https://xizhi.qqoq.net/xxxxxxxxx.send"
    # xizhi(xizhi_api, send_content)

    tg_token = ""
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

    bark_url = "https://xxx.xxx.com/key/"
    # bark(bark_url, send_title, send_content)

    _ = ntfy(
        api="https://ntfy.sh/xxxxx",
        title="直播推送",
        content="xxx已开播",
    )

    pushplus_token = ""
    # pushplus(pushplus_token, send_title, send_content)
