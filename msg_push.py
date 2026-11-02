#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import base64
import http.client
import json
import smtplib
import ssl
import urllib.error
import urllib.request
from email.header import Header
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from http.client import HTTPMessage
from typing import IO, cast

from loguru import logger

import i18n

# 消息推送模块：钉钉 / 微信(Server酱、息知) / Telegram / Bark / ntfy / PushPlus 推送及 SMTP 邮件。
# 各推送函数接收地址与内容，返回 {"success": [...], "error": [...]}；单地址失败只计入 error，
# 不影响同批其它地址（旁路通知不阻断录制）。


# 不走系统代理：本地或自建推送不应被代理干扰
no_proxy_handler: urllib.request.ProxyHandler = urllib.request.ProxyHandler({})
# 重定向最大跳数：urllib 默认最多 10 跳且不做安全复核，这里显式收紧并在每跳重跑准入校验。
_PUSH_MAX_REDIRECTS = 5


# 逐跳复核的重定向处理器。
# 原实现把裸 HTTPRedirectHandler 放进白名单：`_checked_push_url` 只在**发起请求前**跑一次，
# 落地地址既不复核内网也不复核协议。推送地址来自 config.ini（Web 面板可写全部配置），攻击者把自己的
# 服务器设为推送地址、再 302 到 http://169.254.169.254/latest/meta-data/，就绕过了「拒绝内部目标」，
# 而 ntfy/钉钉/Bark 分支会把重定向后的响应体写进 logs/streamget.log（300KB 轮转、求助时常整包上传）
# ——构成**带回显**的 SSRF，云元数据凭据可借此泄露。
# 覆写 redirect_request 在**下一跳连接发出之前**重跑同一判据（_checked_push_url）。
# 命中抛 _PushHopRejected（URLError 子类，对齐 src/sync_http.py 的同族处理）：不直接用 ValueError，
# 是因为 urllib 的 HTTPErrorProcessor 会把 handler 抛出的异常原样上抛，而调用方对「网络类失败」
# 的既有分类是按 urllib.error 家族做的——用同一家族可让它与「目标不可达」走同一条放弃路径，
# 各渠道既有的 `except Exception` 收敛成「本条推送失败」，不影响其它渠道（旁路通知不阻断录制）。
class _PushHopRejected(urllib.error.URLError):
    def __init__(self, url: str, reason: str) -> None:
        super().__init__(reason)
        self.hop_url = url
        self.reject_reason = reason


class _PushHopGuardRedirectHandler(urllib.request.HTTPRedirectHandler):
    max_redirections = _PUSH_MAX_REDIRECTS

    def redirect_request(
        self,
        req: urllib.request.Request,
        fp: IO[bytes],
        code: int,
        msg: str,
        headers: HTTPMessage,
        newurl: str,
    ) -> urllib.request.Request | None:
        try:
            _checked_push_url(newurl)
        except ValueError as e:
            raise _PushHopRejected(newurl, str(e)) from e
        return super().redirect_request(req, fp, code, msg, headers, newurl)


# opener 按**协议白名单手工组装**，不能用 build_opener——后者是「默认 handler
# 集合 + 指定 ProxyHandler」，默认集合含 FileHandler / FTPHandler / DataHandler；而推送地址来自
# config.ini，Web 面板可写全部配置，写成 file:///C:/Users/x/.ssh/id_rsa 就能让本模块读本地文件，
# 读到的内容随后经 ntfy 分支的 error 键原样进日志（logs/ 按轮转保留多份，求助时常整包上传）。
# 白名单形态与 scripts/douyin_live_recorder_standalone.py 的 _build_opener 同源：只注册 http/https
# 所需处理器，file/ftp/data 三类协议入口彻底不存在。
_PUSH_HTTP_HANDLERS: tuple[type[urllib.request.BaseHandler], ...] = (
    urllib.request.UnknownHandler,
    urllib.request.HTTPHandler,
    urllib.request.HTTPDefaultErrorHandler,
    _PushHopGuardRedirectHandler,
    urllib.request.HTTPErrorProcessor,
)


def _build_push_opener() -> urllib.request.OpenerDirector:
    built = urllib.request.OpenerDirector()
    built.add_handler(no_proxy_handler)
    for klass in _PUSH_HTTP_HANDLERS:
        built.add_handler(klass())
    built.add_handler(urllib.request.HTTPSHandler())
    return built


opener: urllib.request.OpenerDirector = _build_push_opener()
headers: dict[str, str] = {"Content-Type": "application/json"}


# 推送地址准入校验：只放行 http/https，并拒绝「内部用途名字」。
# 不拒绝回环与 RFC1918：自建 ntfy / Bark 反代跑在局域网或本机是**合规配置**，拦掉会把真实用户的
# 推送打哑。真正有攻击面的是「非 HTTP 协议」（能读本地文件）与「云元数据 / 内部 DNS 名」（把推送
# 变成内网探测）两类，故走 web_config._host_internal_reason 的 allow_local_targets 形态（放行私网、
# 仍拦 metadata/*.internal）。校验失败抛 ValueError，由各渠道既有的 `except Exception` 收敛成
# 「本条推送失败」，不影响同批其它地址。
def _checked_push_url(url: str) -> str:
    from urllib.parse import urlsplit

    from src.web_config import _host_internal_reason

    parts = urlsplit(url.strip())
    if parts.scheme.lower() not in ("http", "https"):
        raise ValueError(i18n.tr("推送地址协议不受支持（仅允许 http/https）: {scheme}", scheme=parts.scheme or "-"))
    host = parts.hostname or ""
    if not host:
        raise ValueError(i18n.tr("推送地址缺少主机名"))
    reason = _host_internal_reason(host, allow_local_targets=True)
    if reason is not None:
        raise ValueError(i18n.tr("推送地址指向内部目标，已拒绝: {reason}", reason=reason))
    return url


# 脱敏密钥：保留前后各 2 位，其余以 * 遮挡，防日志泄露
def _mask_secret(secret: str) -> str:
    if not secret:
        return ""
    # 短密钥（<=6）整体遮蔽而非保留首尾：首尾保留后仅遮 1-2 位等同明文，无脱敏意义。
    if len(secret) <= 6:
        return "****"
    return f"{secret[:2]}{'*' * (len(secret) - 4)}{secret[-2:]}"


# 脱敏推送地址：丢弃 query 与疑似密钥路径段，仅供日志展示、不影响实际请求。
# mask_last_segment=True：把「路径最后一段即凭据」的渠道（Bark / Server酱 / 息知 / ntfy）无条件遮蔽
# 末段。：旧实现靠 hostname.endswith("day.app") 白名单命中 Bark 的 8 位短密钥，自建 / 反代
# Bark（https://bark.example.com/<8字符key>）因此整串明文进 logs/streamget.log（300KB 轮转、保留
# 多份、求助时通常整包上传），拿到即可向用户手机无限推送——主机名从来不是判据，密钥的位置才是，
# 故改由调用方按渠道声明。ntfy 的 https://ntfy.sh/<topic> 同样「末段即频道
# 口令」（拿到 topic 即可匿名订阅、也能抢先发假消息），三处失败日志曾漏传该参数，已补齐；
# 钉钉/TG/PushPlus 的凭据在 query 或 token 字段、末段非凭据，保持不传（本函数本就丢弃 query）。
def _mask_url(url: str, *, mask_last_segment: bool = False) -> str:
    try:
        from urllib.parse import urlsplit, urlunsplit

        parts = urlsplit(url)
        segs = [s for s in parts.path.split("/") if s]
        masked_segs: list[str] = []
        for idx, seg in enumerate(segs):
            if seg.startswith("bot") and len(seg) > 4:
                masked_segs.append("bot****")  # Telegram token
            elif seg.endswith(".send") or seg.lower() in ("key", "sendmessage"):
                masked_segs.append("****")
            elif idx == len(segs) - 1 and mask_last_segment:
                # Bark / Server酱 / 息知：密钥恒为最后一段，与主机名无关
                masked_segs.append("****")
            elif len(seg) > 12 and "sendmessage" not in seg.lower():
                masked_segs.append("****")  # 疑似长密钥（Server酱/Bark 末段）
            else:
                masked_segs.append(seg)
        masked_path = "/" + "/".join(masked_segs) if masked_segs else ""
        # netloc 里的 userinfo（https://user:pass@host，自托管反代常见的 basic-auth 形态）必须剥离：
        # [历史注] 原实现原样带出，口令曾因此明文进轮转日志。
        netloc = parts.netloc
        if "@" in netloc:
            netloc = "***@" + netloc.rsplit("@", 1)[1]
        # 丢弃 query（access_token 等敏感参数）
        return urlunsplit((parts.scheme, netloc, masked_path, "", ""))
    except Exception:
        return _mask_secret(url)


# 2026-10-21：响应体派生文本在写日志前必须截断 + 脱敏。
# 重定向让推送请求落到内网（云元数据等）时，响应体原文会经 errmsg/msg/message/error 字段进
# logs/streamget.log（300KB 轮转、求助时常整包上传）——这正是「带回显的 SSRF」。除逐跳拦截外，
# 输出侧再兜一层：截断到固定长度（避免整份响应把日志刷爆）并按同一口径抹凭据。
_PUSH_RESP_TEXT_LIMIT = 300


def _sanitize_resp_text(value: object) -> str:
    text = value if isinstance(value, str) else str(value)
    if len(text) > _PUSH_RESP_TEXT_LIMIT:
        text = text[:_PUSH_RESP_TEXT_LIMIT] + "…"
    from src.utils import mask_credentials

    return mask_credentials(text)


# 异常文本进轮转日志前的统一出口：出站失败时 str(e) 常带完整推送
# URL，自托管 bark/ntfy 的口令就在路径末段，而 logs 按大小轮转保留多份 = 凭据长期落盘。
# 类型名由各日志模板的 {type_name} 单独承载，此处不重复拼接；截断复用同一上限避免超长 URL 刷屏。
def _mask_exc_text(exc: BaseException) -> str:
    return _sanitize_resp_text(str(exc))


# 钉钉群机器人推送文本消息，支持 @手机号/全体，返回成功与失败地址列表
def dingtalk(url: str, content: str, number: str | None = None, is_atall: bool = False) -> dict[str, list[str | int]]:
    success: list[str | int] = []
    error: list[str | int] = []
    api_list = url.replace("，", ",").split(",") if url.strip() else []
    # 支持多 webhook 逗号分隔批量推送；单条异常被下方 try 单独捕获，不影响其余地址（旁路通知不阻断录制）。
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
            _ = _checked_push_url(api)
            data = json.dumps(json_data).encode("utf-8")
            req = urllib.request.Request(api, data=data, headers=headers)
            with cast(http.client.HTTPResponse, opener.open(req, timeout=10)) as response:
                json_str = response.read().decode("utf-8")
            resp_data: dict[str, object] = cast(dict[str, object], json.loads(json_str))
            # 钉钉以响应体 errcode==0 判成功；非 0 即业务失败（如 IP 未加白），必须显式计入 error。
            # 区别于 Server酱/Bark/PushPlus 的 code==200 判定，勿混用字段。
            if resp_data.get("errcode") == 0:
                success.append(api)
            else:
                error.append(api)
                logger.warning(
                    i18n.tr(
                        "钉钉推送失败, 推送地址：{masked_api}, {errmsg}",
                        masked_api=_mask_url(api),
                        errmsg=_sanitize_resp_text(resp_data.get("errmsg", i18n.tr("未知错误"))),
                    )
                )
        except Exception as e:
            error.append(api)
            # 本仓硬约定「异常日志必带 type_name」——Windows 下 socket.timeout /
            # TimeoutError 的 str() 是空串、urllib 包装后只剩 '<urlopen error >'，只写 {e} 会让
            # 「DNS 失败 / TLS 校验失败 / 超时」三种故障打成同一行空白尾巴。
            logger.warning(
                i18n.tr(
                    "钉钉推送失败, 推送地址：{masked_api}, 错误信息: {type_name}: {e}",
                    masked_api=_mask_url(api),
                    type_name=type(e).__name__,
                    e=_mask_exc_text(e),
                )
            )
    return {"success": success, "error": error}


# 通过 Server酱/微信 推送消息（url 为推送地址，title/content 为内容）。
def xizhi(url: str, title: str, content: str) -> dict[str, list[str | int]]:
    success: list[str | int] = []
    error: list[str | int] = []
    api_list = url.replace("，", ",").split(",") if url.strip() else []
    # 支持多推送地址逗号分隔批量发送；单条异常被下方 try 单独捕获，不影响其余地址。
    for api in api_list:
        json_data = {"title": title, "content": content}
        try:
            _ = _checked_push_url(api)
            data = json.dumps(json_data).encode("utf-8")
            req = urllib.request.Request(api, data=data, headers=headers)
            with cast(http.client.HTTPResponse, opener.open(req, timeout=10)) as response:
                json_str = response.read().decode("utf-8")
            resp_data: dict[str, object] = cast(dict[str, object], json.loads(json_str))
            # Server酱/息知以响应体 code==200 标识成功（非 HTTP 状态码、也非 errcode）；
            # 误用 errcode 字段会漏判，需与钉钉区分。
            if resp_data.get("code") == 200:
                success.append(api)
            else:
                error.append(api)
                logger.warning(
                    i18n.tr(
                        "微信推送失败, 推送地址：{masked_api}, 失败信息：{msg}",
                        masked_api=_mask_url(api, mask_last_segment=True),
                        msg=_sanitize_resp_text(resp_data.get("msg", i18n.tr("未知错误"))),
                    )
                )
        except Exception as e:
            error.append(api)
            logger.warning(
                i18n.tr(
                    "微信推送失败, 推送地址：{masked_api}, 错误信息: {type_name}: {e}",
                    masked_api=_mask_url(api, mask_last_segment=True),
                    type_name=type(e).__name__,
                    e=_mask_exc_text(e),
                )
            )
    return {"success": success, "error": error}


# SMTP 头注入防护（与 src/web_config._reject_newline 同款语义）
# 邮件头以 \r\n 分隔：任何进入 From/To/Subject 的外部数据（title 部分来自主播名等
# 平台返回内容，攻击者可控）含换行即可伪造任意邮件头（如 Bcc 批量投递、伪造 From
# 绕过 SPF 显示）。email.header.Header 会编码非 ASCII 但**不会**剥离 CRLF，故必须
# 在组装前显式拒绝。
def _reject_smtp_newline(kind: str, value: str) -> None:
    if value and ("\n" in value or "\r" in value):
        # 异常文本经 push 失败分支打印到控制台：模板过 tr 先查表后插值（kind 已在调用点翻好）
        raise ValueError(i18n.tr("{kind} 含换行符，禁止用于邮件头", kind=kind))


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
    receivers = to_email.replace("，", ",").split(",") if to_email.strip() else []
    smtp_obj: smtplib.SMTP | smtplib.SMTP_SSL | None = None

    # 两条 TLS 路径共用同一个**校验证书**的 context。
    # 病史：原实现 `SMTP_SSL(host, port, timeout=10)` 与 `starttls()` 都不传 context，二者均回落
    # `ssl._create_stdlib_context()`——而它**就是** `_create_unverified_context`（本机 CPython 3.14
    # 实测 verify_mode=0 / check_hostname=False）：中间人呈递任意自签证书即可解密整段会话、拿到
    # login_email / email_pass（授权码等同口令）；`open_ssl=True` 是默认值，465 默认分支同样不设防。
    # 两条路径必须传同一个 ctx（「只改一条即出现口径分叉」）。确需放行自签证书应走显式配置项
    # 并 logger.warning，本轮不加该开关，避免引入未经决策的放宽入口。
    # 复核判据：tests/test_regression_utils.py::TestSmtpBothPathsVerifyCertificates
    # （断言 SSL 与 starttls 两分支各自收到 verify_mode == ssl.CERT_REQUIRED 的 context 且为同一对象）。
    ctx = ssl.create_default_context()

    try:
        # CRLF 注入校验前置。放行则攻击者可用含换行的主播名
        # 伪造 Bcc/Reply-To 等邮件头；拒绝并记 warning 比静默发送伪造邮件安全。
        # kind 标签在调用点过 tr（盲区③推送文案，提取器扫不到裸字面量实参位）
        _reject_smtp_newline(i18n.tr("邮件标题"), title)
        _reject_smtp_newline(i18n.tr("发件人地址"), sender_email)
        _reject_smtp_newline(i18n.tr("发件人名称"), sender_name)
        for rcpt in receivers:
            _reject_smtp_newline(i18n.tr("收件人地址"), rcpt)

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
            smtp_obj = smtplib.SMTP_SSL(email_host, port, timeout=10, context=ctx)
        else:
            try:
                port = int(smtp_port) if smtp_port else 25
            except ValueError:
                port = 25
            smtp_obj = smtplib.SMTP(email_host, port, timeout=10)
            # 非 SSL 分支原先直接 login，授权码在**明文链路**上传输（等同邮箱口令，可被公共
            # Wi-Fi / 透明代理嗅探）。这里先尝试 STARTTLS 升级，服务器不支持时明确告警而非静默明文登录。
            # starttls 必须显式传 context=ctx，否则回落不校验证书的 context，升级成
            # 「已加密但未认证」的链路。
            try:
                _ = smtp_obj.ehlo()
                _ = smtp_obj.starttls(context=ctx)
                _ = smtp_obj.ehlo()
            except smtplib.SMTPException as e:
                logger.warning(
                    i18n.tr(
                        "SMTP 服务器不支持 STARTTLS，本次将以明文发送邮箱授权码（存在被窃听风险，"
                        "建议在配置中改为启用 SSL 加密）: {type_name}",
                        type_name=type(e).__name__,
                    )
                )
        assert smtp_obj is not None
        _ = smtp_obj.login(login_email, email_pass)
        _ = smtp_obj.sendmail(sender_email, receivers, message.as_string())
        return {"success": receivers, "error": []}
    except ValueError as e:
        # 换行注入被拒：与 SMTPException 分开记，便于区分「配置被污染/攻击」与「网络故障」
        logger.warning(i18n.tr("邮件推送被拒绝（疑似头注入）: {e}", e=e))
        return {"success": [], "error": receivers}
    except smtplib.SMTPException as e:
        logger.warning(
            i18n.tr(
                "邮件推送失败, 推送邮箱：{to_email}, 错误信息: {type_name}: {e}",
                to_email=to_email,
                type_name=type(e).__name__,
                e=_mask_exc_text(e),
            )
        )
        return {"success": [], "error": receivers}
    except Exception as e:
        logger.warning(
            i18n.tr(
                "邮件推送失败, 推送邮箱：{to_email}, 错误信息: {type_name}: {e}",
                to_email=to_email,
                type_name=type(e).__name__,
                e=_mask_exc_text(e),
            )
        )
        return {"success": [], "error": receivers}
    # 无论成功失败都主动 quit() 关闭 SMTP 会话，避免连接悬挂；quit 失败忽略（连接本就要丢弃）。
    # 原先只吞 smtplib.SMTPException，但 quit() 走 docmd("QUIT") 等 221
    # 响应、socket 带 timeout=10，服务端不回 221 时抛 socket.timeout（= TimeoutError，是 **OSError**
    # 子类而**不是** SMTPException）。在 finally 里穿出会**替换掉** try 块已算好的成功返回值：邮件其实
    # 已发出，上层 push_message 却拿到未捕获异常、重试逻辑据此重发（用户表现为重复收到同一封开播通知）。
    # ECONNRESET / EBADF 等其它 OSError 同理只是「会话没优雅关闭」，不得改变已得出的结论。
    # 复核判据：tests/test_regression_utils.py::test_send_email_quit_timeout_does_not_replace_result
    finally:
        if smtp_obj:
            try:
                _ = smtp_obj.quit()
            except smtplib.SMTPException, OSError:
                pass


# Telegram Bot 推送文本消息，返回成功与失败聊天ID列表
def tg_bot(chat_id: str | int, token: str, content: str) -> dict[str, list[str | int]]:
    # url 在 try 外预绑定，避免构造 json_data 异常时 except 块引用未绑定变量触发 NameError
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        # 2026-10-21：即使本函数拼的是硬编码的官方地址，也必须过同一道首跳校验——
        # 「所有出站 URL 统一过检」是不变量，留一处例外就给后来者留了「此处不必检查」的错误示例。
        _ = _checked_push_url(url)
        json_data = {"chat_id": chat_id, "text": content}
        data = json.dumps(json_data).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=headers)
        with cast(http.client.HTTPResponse, opener.open(req, timeout=15)) as response:
            json_str = response.read().decode("utf-8")
        resp_data: dict[str, object] = cast(dict[str, object], json.loads(json_str))
        # Telegram 即便 HTTP 2xx 也可能业务失败（ok=false + description），须以 ok 字段判定、不能只看状态码。
        if resp_data.get("ok") is True:
            return {"success": [str(chat_id)], "error": []}
        # description 由服务端响应体派生，经重定向落到内网（云元数据等）
        # 时它就是回显内容，必须与其余分支一样过 _sanitize_resp_text（截断 + 脱敏）再入日志。
        error_detail = _sanitize_resp_text(resp_data.get("description", i18n.tr("未知错误")))
        logger.warning(
            i18n.tr(
                "tg推送失败, 聊天ID：{chat_id}, 推送地址：{masked_url}, 失败信息:{error_detail}",
                chat_id=chat_id,
                masked_url=_mask_url(url),
                error_detail=error_detail,
            )
        )
        return {"success": [], "error": [str(chat_id)]}
    except Exception as e:
        logger.warning(
            i18n.tr(
                "tg推送失败, 聊天ID：{chat_id}, 推送地址：{masked_url}, 错误信息: {type_name}: {e}",
                chat_id=chat_id,
                masked_url=_mask_url(url),
                type_name=type(e).__name__,
                e=_mask_exc_text(e),
            )
        )
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
            _ = _checked_push_url(_api)
            data = json.dumps(json_data).encode("utf-8")
            req = urllib.request.Request(_api, data=data, headers=headers)
            with cast(http.client.HTTPResponse, opener.open(req, timeout=10)) as response:
                json_str = response.read().decode("utf-8")
            resp_data: dict[str, object] = cast(dict[str, object], json.loads(json_str))
            # Bark 以响应体 code==200 判成功（与 Server酱/息知/PushPlus 一致，区别于钉钉 errcode）。
            if resp_data.get("code") == 200:
                success.append(_api)
            else:
                error.append(_api)
                logger.warning(
                    i18n.tr(
                        "Bark推送失败, 推送地址：{masked_api}, 失败信息：{message}",
                        masked_api=_mask_url(_api, mask_last_segment=True),
                        message=_sanitize_resp_text(resp_data.get("message", i18n.tr("未知错误"))),
                    )
                )
        except Exception as e:
            error.append(_api)
            logger.warning(
                i18n.tr(
                    "Bark推送失败, 推送地址：{masked_api}, 错误信息: {type_name}: {e}",
                    masked_api=_mask_url(_api, mask_last_segment=True),
                    type_name=type(e).__name__,
                    e=_mask_exc_text(e),
                )
            )
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
    success: list[str | int] = []
    error: list[str | int] = []
    api_list = api.replace("，", ",").split(",") if api.strip() else []
    # 支持多 ntfy 地址逗号分隔批量推送；单条异常被下方 try/except 单独捕获，不影响其余地址。
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

            # ensure_ascii=False 保留中文原文，否则 ntfy 收到 \uXXXX 转义会显示成乱码/编码体；
            # 推文/标题含中文时必须如此。
            _ = _checked_push_url(server)
            data = json.dumps(json_data, ensure_ascii=False).encode("utf-8")
            req = urllib.request.Request(server, data=data, headers=headers)
            with cast(http.client.HTTPResponse, opener.open(req, timeout=10)) as response:
                json_str = response.read().decode("utf-8")
            resp_data: dict[str, object] = cast(dict[str, object], json.loads(json_str))
            # ntfy 成功响应无 "error" 字段，失败才带 error；与上面的 code==200 风格不同，
            # 必须按"无 error 即成功"判定，否则会把成功误判为失败。
            if "error" not in resp_data:
                success.append(_api)
            else:
                error.append(_api)
                logger.warning(
                    i18n.tr(
                        "ntfy推送失败, 推送地址：{masked_api}, 失败信息：{error}",
                        masked_api=_mask_url(_api, mask_last_segment=True),
                        error=_sanitize_resp_text(resp_data["error"]),
                    )
                )
        except urllib.error.HTTPError as e:
            error.append(_api)
            try:
                error_msg = e.read().decode("utf-8")
                error_detail = cast(dict[str, object], json.loads(error_msg)).get("error", str(e))
            except Exception:
                error_detail = str(e)
            finally:
                e.close()
            logger.warning(
                i18n.tr(
                    "ntfy推送失败, 推送地址：{masked_api}, 错误信息:{error_detail}",
                    masked_api=_mask_url(_api, mask_last_segment=True),
                    # HTTPError 的响应体是攻击者可控的回显，与上面
                    # resp_data["error"] 那条同口径，写日志前一律截断 + 脱敏。
                    error_detail=_sanitize_resp_text(error_detail),
                )
            )
        except Exception as e:
            error.append(_api)
            logger.warning(
                i18n.tr(
                    "ntfy推送失败, 推送地址：{masked_api}, 错误信息: {type_name}: {e}",
                    masked_api=_mask_url(_api, mask_last_segment=True),
                    type_name=type(e).__name__,
                    e=_mask_exc_text(e),
                )
            )
    return {"success": success, "error": error}


# PushPlus 推送（token+title+content），返回成功与失败 token 列表
def pushplus(token: str, title: str, content: str) -> dict[str, list[str | int]]:
    success: list[str | int] = []
    error: list[str | int] = []
    token_list = token.replace("，", ",").split(",") if token.strip() else []

    # 支持多 token 逗号分隔批量推送；单条异常被下方 try 单独捕获，不影响其余 token。
    for _token in token_list:
        json_data = {"token": _token, "title": title, "content": content}

        try:
            url = "https://www.pushplus.plus/send"
            # 同 tg_bot——硬编码地址也过首跳校验，维持「所有出站 URL 统一过检」的不变量。
            _ = _checked_push_url(url)
            data = json.dumps(json_data).encode("utf-8")
            req = urllib.request.Request(url, data=data, headers=headers)
            with cast(http.client.HTTPResponse, opener.open(req, timeout=10)) as response:
                json_str = response.read().decode("utf-8")
            resp_data: dict[str, object] = cast(dict[str, object], json.loads(json_str))

            # PushPlus 以响应体 code==200 判定成功（与 Server酱/Bark 一致）。
            if resp_data.get("code") == 200:
                success.append(_token)
            else:
                error.append(_token)
                logger.warning(
                    i18n.tr(
                        "PushPlus推送失败, Token：{masked_token}, 失败信息：{msg}",
                        masked_token=_mask_secret(_token),
                        msg=_sanitize_resp_text(resp_data.get("msg", i18n.tr("未知错误"))),
                    )
                )
        except Exception as e:
            error.append(_token)
            logger.warning(
                i18n.tr(
                    "PushPlus推送失败, Token：{masked_token}, 错误信息: {type_name}: {e}",
                    masked_token=_mask_secret(_token),
                    type_name=type(e).__name__,
                    e=_mask_exc_text(e),
                )
            )

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

    # [历史注] 本调用原先未注释，而本文件 `if __name__` 块是手工
    # 调试入口、其余渠道（钉钉/邮件/TG/Bark 等）全部已注释——直接 `python msg_push.py` 会向公网
    # ntfy.sh 主题发出真实推送（主题名可被任何人订阅），属误操作外泄。注释掉，与其余渠道保持一致。
    # _ = ntfy(
    #     api="https://ntfy.sh/xxxxx",
    #     title="直播推送",
    #     content="xxx已开播",
    # )

    _ = ntfy  # 保留引用，避免 lint 将 ntfy 判为未使用导入/定义

    pushplus_token = ""
    # pushplus(pushplus_token, send_title, send_content)
