# 抖音弹幕实现，移植自 dart simple_live_core 的 douyin_danmaku.dart。
#
# 协议：WebSocket `wss://webcast100-ws-web-lq.douyin.com/webcast/im/push/v2/`，
# Protobuf PushFrame 帧 + gzip 压缩的 Response：进房与 10s 心跳都发 PushFrame{payloadType='hb'}；
# 推送侧 gzip 解压 payload → Response，needAck 时回 ack 帧；
# WebcastChatMessage → 弹幕(CHAT)，WebcastRoomUserSeqMessage → 在线人数(ONLINE)。
# 签名：XBogus（src/platforms/_xbogus.py 纯 Python 实现，与 dart getSignature 一致）。
# Cookie：握手必须携带有效 cookie（至少 ttwid），否则服务端回 HTTP 200 拒绝；优先用 main 传入的
# 录制 cookie，为空时经 src.ttwid.get_ttwid() 动态获取（进程级共享缓存，config.ini [Cookie]
# ttwid 优先，其次自动拉取抖音主页）。
# 凭据自愈（MID-33）：握手被 HTTP 200 拒绝即判定本轮 ttwid 已作废 → invalidate_ttwid() 清进程级
# 缓存，下一轮重新获取，而不是等 cookie_cache 的 TTL（默认 30 分钟）自然过期；与 B站
# _reject_auth() → invalidate_bili_buvid_cache() 同形。解析侧（src/room.py / src/spider.py）的
# 「HTTP 200 + 空响应体」判定无 invalidate_ttwid() 调用点，故本模块的接线只覆盖弹幕链路。

from __future__ import annotations

import re
import time
import urllib.parse
from typing import Any, Union, cast

import i18n
from src.base import DanmakuBase, DanmakuMessage, DanmakuMessageType
from src.logger import logger
from src.platforms._xbogus import danmaku_signature
from src.proto import douyin_pb2
from src.ttwid import get_ttwid, invalidate_ttwid

# MI-01：解压上限与解压助手统一取自 ws_client，避免各平台各写一个魔数
from src.ws_client import _MAX_DECOMPRESSED_BYTES, WsClient, decompress_limited

SERVER_URL = "wss://webcast100-ws-web-lq.douyin.com/webcast/im/push/v2/"

# 抖音对「失效 ttwid」的拒绝形态是 **HTTP 200 但不升级协议**（不返回 4xx）。websockets 对此抛
# InvalidStatus，str() 形如 "server rejected WebSocket connection: HTTP 200"（代理侧为
# "proxy rejected connection: HTTP …"）。WsClient 只把 str(e) 透传给 on_close/on_reconnect
# （拿不到异常对象），故只能按状态码文本识别，且**只认 200**：4xx/5xx 与网络类异常（超时/DNS/
# TLS/连接被拒）都不是「凭据被作废」的信号，误判会让每次断网都多打一次抖音主页接口，而重复拉
# ttwid 本身就是风控触发源（并发去重见 src/room.py 的锁注释）。
_HTTP_200_REFUSAL_PATTERN = re.compile(r"(?:http|status(?:\s+code)?)[^\d]{0,4}\b200\b", re.IGNORECASE)


# 判定一条 WsClient 回调文案是否为「握手被服务端以 HTTP 200 拒绝」。
def _is_http200_handshake_refusal(detail: str) -> bool:
    return bool(_HTTP_200_REFUSAL_PATTERN.search(detail or ""))


# 抖音弹幕 WS 默认 UA（query 的 browser_version 与请求头同源此常量，两处必须自洽）；
# 版本过旧会被风控按指纹识别，2026-08 起统一 Chrome/141。
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36 Edg/141.0.0.0"
)

METHOD_CHAT = "WebcastChatMessage"
METHOD_ONLINE = "WebcastRoomUserSeqMessage"


# 构造抖音心跳/进房帧 PushFrame{payloadType='hb'}，返回序列化 bytes。
def _make_hb_frame() -> bytes:
    frame = douyin_pb2.PushFrame()
    frame.payloadType = "hb"
    return cast(bytes, frame.SerializeToString())


# 抖音弹幕客户端：Protobuf PushFrame 收发、心跳与 ack 确认。
class DouyinDanmaku(DanmakuBase):
    heartbeat_interval = 10.0  # 与 dart heartbeatTime 一致

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._args: dict = {}
        self._ws: WsClient | None = None
        # _ttwid_in_use：本轮 cookie 是否来自 get_ttwid()。只有这支凭据被拒才需作废进程级缓存——
        # 用户自填的录制 cookie 不走该缓存，作废它既无效又会让下一轮白拉一次主页接口。
        self._ttwid_in_use = False
        # _ttwid_revoked：一次会话内只作废一次（重连最多 5 次，同一拒绝文案无需重复清缓存）。
        self._ttwid_revoked = False

    # 启动：构造带 XBogus 签名与 cookie 的 WS URL，建立连接；缺 room_id 回调 on_close。
    async def start(self, args: Any) -> None:
        self._args = args if isinstance(args, dict) else {}
        room_id = str(self._args.get("room_id") or "")
        user_id = str(self._args.get("user_id") or "")
        # 未配置录制 cookie 时动态获取 ttwid：本协程跑在采集线程的事件循环里可直接 await；
        # get_ttwid 是进程级缓存，多房间并发只实际拉取一次。
        cookie = str(self._args.get("cookie") or "").strip()
        self._ttwid_in_use = False
        self._ttwid_revoked = False
        if not cookie:
            try:
                cookie = await get_ttwid()
            except Exception as e:
                logger.warning(
                    i18n.tr("[抖音弹幕]动态获取 ttwid 失败: {type_name}: {e}", type_name=type(e).__name__, e=e)
                )
                cookie = ""
            if not cookie:
                logger.warning("[抖音弹幕]无可用 cookie/ttwid，WS 握手可能被服务端拒绝")
            else:
                # 标记「本轮用的是动态 ttwid」：随后握手被 HTTP 200 拒时据此作废缓存（MID-33）
                self._ttwid_in_use = True
        if not room_id:
            if self._on_close:
                self._on_close("缺少 room_id")
            return

        ts = int(time.time() * 1000)
        params = [
            ("app_name", "douyin_web"),
            ("version_code", "180800"),
            ("webcast_sdk_version", "1.0.14-beta.0"),
            ("update_version_code", "1.0.14-beta.0"),
            ("compress", "gzip"),
            ("cursor", f"h-1_t-{ts}_r-1_d-1_u-1"),
            ("host", "https://live.douyin.com"),
            ("aid", "6383"),
            ("live_id", "1"),
            ("did_rule", "3"),
            ("debug", "false"),
            ("maxCacheMessageNumber", "20"),
            ("endpoint", "live_pc"),
            ("support_wrds", "1"),
            ("im_path", "/webcast/im/fetch/"),
            ("user_unique_id", user_id),
            ("device_platform", "web"),
            ("cookie_enabled", "true"),
            ("screen_width", "1920"),
            ("screen_height", "1080"),
            ("browser_language", "zh-CN"),
            ("browser_platform", "Win32"),
            ("browser_name", "Mozilla"),
            ("browser_version", DEFAULT_USER_AGENT.replace("Mozilla/", "")),
            ("browser_online", "true"),
            ("tz_name", "Asia/Shanghai"),
            ("identity", "audience"),
            ("room_id", room_id),
            ("heartbeatDuration", "0"),
        ]
        query = urllib.parse.urlencode(params)
        sign = danmaku_signature(room_id, user_id)
        # signature **不做** URL 编码：上游 dart（douyin_danmaku.dart 的 "$uri&signature=$sign"）
        # 是直接拼接、不 encodeComponent。XBogus 字符表含 `+` / `/`，按 form-urlencoded 语义 `+` 会
        # 变成空格，但握手侧实测不按该语义解码（否则约四成含 `+` 的签名会系统性失败，且社区实现
        # simple_live_core / f2 / DouyinLiveWebFetcher 均沿用未编码形态）。出现「签名无效」告警时
        # 先抓包对照上游实际字节，不得凭静态审查直接加 quote()——那会成为全网唯一异类指纹。
        url = f"{SERVER_URL}?{query}&signature={sign}"
        backup_url = url.replace("webcast100-ws-web-lq", "webcast100-ws-web-lf")

        self._ws = WsClient(
            url=url,
            backup_url=backup_url,
            heartbeat_interval=self.heartbeat_interval,
            headers={
                "User-Agent": DEFAULT_USER_AGENT,
                "Cookie": cookie,
                "Origin": "https://live.douyin.com",
            },
            on_message=self.decode_message,
            on_ready=self._on_ws_ready,
            on_heartbeat=self.heartbeat,
            on_close=self._handle_close,
            on_reconnect=self._on_reconnect,
        )
        await self._ws.connect()

    # 连接关闭上报：先做 ttwid 作废判定，再把「房间已关闭」事件原样上抛给采集器。
    def _handle_close(self, reason: str) -> None:
        self._note_ttwid_refusal(reason)
        if self._on_close:
            self._on_close(reason)

    # 断线重连（基类回调，只记 debug、不上报关闭）：重连次数与退避节奏不变，只在每次失败时
    # 顺手判一次 HTTP 200 拒绝——命中即作废缓存，使**下一轮** start() 取到新 ttwid，而不是在本轮
    # 剩余重连里继续用同一支废凭据。
    def _on_reconnect(self, reason: str) -> None:
        self._note_ttwid_refusal(reason)
        super()._on_reconnect(reason)

    # MID-33 接线点：HTTP 200 拒绝握手 = 本轮 ttwid 已被平台作废。三层进程级缓存由
    # invalidate_ttwid 一并作废，下一轮重新获取，不等 cookie_cache 的 30 分钟 TTL——那是
    # 「抖音解析长期 200 + 空 body」的自愈断点。刻意不打日志：可观测性由下一轮「自动获取抖音
    # ttwid 成功」的 debug 承担（新增文案需四处目录同步）。
    def _note_ttwid_refusal(self, reason: str) -> None:
        if not self._ttwid_in_use or self._ttwid_revoked:
            return
        if _is_http200_handshake_refusal(reason):
            self._ttwid_revoked = True
            invalidate_ttwid()

    # WS 就绪回调：触发 on_ready 并按 dart joinRoom 的做法发送进房 hb 帧。
    def _on_ws_ready(self) -> None:
        if self._on_ready:
            self._on_ready()
        self._send_nowait(_make_hb_frame())

    # 非阻塞发送字节数据（仅在 WS 已建立时发送）。
    def _send_nowait(self, data: bytes) -> None:
        if self._ws is not None:
            self._ws.send_nowait(data)

    async def heartbeat(self) -> None:
        self._send_nowait(_make_hb_frame())

    async def stop(self) -> None:
        self._stopped = True
        if self._ws is not None:
            await self._ws.close()

    # 解析 PushFrame：gzip 解压 payload 为 Response，分发弹幕/在线消息并回 ack。
    def decode_message(self, data: Union[bytes, str]) -> None:
        if isinstance(data, str):
            return
        try:
            frame = douyin_pb2.PushFrame()
            frame.ParseFromString(data)
            # MI-01：解压必须限长。gzip 压缩比可达 1000:1，几百 KB 的帧就能展开成 GB 级对象，
            # 服务端异常或链路被篡改时可打爆本进程并连带影响录制主流程。
            payload = decompress_limited(frame.payload, _MAX_DECOMPRESSED_BYTES)
            resp = douyin_pb2.Response()
            resp.ParseFromString(payload)

            if resp.needAck:
                self._send_ack(frame.logId)

            for msg in resp.messagesList:
                method = msg.method
                if method == METHOD_CHAT:
                    self._decode_chat(msg.payload)
                elif method == METHOD_ONLINE:
                    pass  # 在线人数不进 SRT
        except Exception as e:
            # 无效包丢弃不影响录像，但须留异常类型+帧头 hex 线索，避免「0 弹幕零线索」
            logger.debug(
                i18n.tr(
                    "[抖音弹幕]帧解析异常: {type_name} head={head}", type_name=type(e).__name__, head=data[:16].hex()
                )
            )

    # 解析 ChatMessage 的 payload，提取昵称与内容并 emit 弹幕。
    def _decode_chat(self, payload: bytes) -> None:
        try:
            chat = douyin_pb2.ChatMessage()
            chat.ParseFromString(payload)
            content = chat.content or ""
            nick = (chat.user.nickName or "") if chat.HasField("user") else ""
            if not content or not nick:
                return
            self._emit(
                DanmakuMessage(
                    type=DanmakuMessageType.CHAT,
                    user_name=nick,
                    message=content,
                    color="#FFFFFF",
                )
            )
        except Exception as e:
            # 单条消息解码失败不影响后续，但须留线索（protobuf 字段变更时排障依赖此日志）
            logger.debug(
                i18n.tr(
                    "[抖音弹幕]弹幕解析异常: {type_name} payload={payload}",
                    type_name=type(e).__name__,
                    payload=payload[:16].hex(),
                )
            )

    # 对需要确认的帧发送 ack（payloadType='ack' + logId）。
    def _send_ack(self, log_id: int) -> None:
        frame = douyin_pb2.PushFrame()
        frame.payloadType = "ack"
        frame.logId = log_id
        self._send_nowait(frame.SerializeToString())
