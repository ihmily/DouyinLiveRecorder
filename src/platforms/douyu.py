# 斗鱼弹幕实现，移植自 dart simple_live_core 的 douyu_danmaku.dart。
#
# 协议：WebSocket wss://danmuproxy.douyu.com:8506 + STT 自定义文本协议。
# 二进制帧（小端）：[总长4][总长4][packType=689 2B][enc=0 1B][res=0 1B][body UTF-8][0x00 1B]

from __future__ import annotations

import struct
from typing import Any

import i18n
from src.base import DanmakuBase, DanmakuMessage, DanmakuMessageType, spawn_danmaku_task
from src.logger import logger
from src.ws_client import WsClient

SERVER_URL = "wss://danmuproxy.douyu.com:8506"
CLIENT_SEND_TO_SERVER = 689

# 斗鱼弹幕颜色 col -> #RRGGBB
_DOUYU_COLORS = {
    1: "#FF0000",
    2: "#1E87F0",
    3: "#7AC84B",
    4: "#FF7F00",
    5: "#9B39F4",
    6: "#FF69B4",
}


# 斗鱼弹幕客户端：STT 自定义文本协议、进房、心跳与消息解析。
class DouyuDanmaku(DanmakuBase):
    heartbeat_interval = 45.0

    # 初始化：记录是否只显示粉丝弹幕，重置房间号与 WS 连接。
    # only_fans 默认 False（2026-09-12 审查 C-3）：dart 上游无任何粉丝过滤，移植时引入
    # True 默认值导致普通观众弹幕（通常占绝大多数）被静默丢弃，且 main 调用链无开关可关。
    def __init__(self, *args: Any, only_fans: bool = False, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._only_fans = only_fans  # 是否只显示粉丝弹幕（True 时过滤 if!='1' 的消息，默认不过滤）
        self._room_id: str = ""
        self._ws: WsClient | None = None

    # 启动：解析 room_id（字典或字符串），建立斗鱼 WS 连接；缺失则回调 on_close。
    async def start(self, args: Any) -> None:
        # args 可为 {"room_id": "xxx"} 或直接 room_id 字符串
        if isinstance(args, dict):
            self._room_id = str(args.get("room_id", ""))
        else:
            self._room_id = str(args)
        if not self._room_id:
            if self._on_close:
                self._on_close("缺少 room_id")
            return

        self._ws = WsClient(
            url=SERVER_URL,
            heartbeat_interval=self.heartbeat_interval,
            on_message=self.decode_message,
            on_ready=self._on_ws_ready,
            on_heartbeat=self.heartbeat,
            on_close=self._on_close,
            on_reconnect=self._on_reconnect,
        )
        await self._ws.connect()

    # WS 就绪回调：触发 on_ready 并异步发送登录/进房请求。
    def _on_ws_ready(self) -> None:
        if self._on_ready:
            self._on_ready()
        # ready 后异步登录进房（spawn_danmaku_task 兜底异常落盘，防止静默死亡）
        spawn_danmaku_task(self._join_room())

    # 异步发送 loginreq 与 joingroup 请求，登录并加入房间。
    async def _join_room(self) -> None:
        if self._ws is None:
            return
        await self._ws.send(self._serialize(f"type@=loginreq/roomid@={self._room_id}/"))
        await self._ws.send(self._serialize(f"type@=joingroup/rid@={self._room_id}/gid@=-9999/"))

    # 发送 mrkl 心跳包维持连接。
    async def heartbeat(self) -> None:
        if self._ws is not None:
            await self._ws.send(self._serialize("type@=mrkl/"))

    # 停止：置停止标志并关闭 WebSocket 连接。
    async def stop(self) -> None:
        self._stopped = True
        if self._ws is not None:
            await self._ws.close()

    # 将 STT 文本按斗鱼二进制帧结构（小端）封装为发送字节串，返回 bytes。
    @staticmethod
    def _serialize(body: str) -> bytes:
        # 帧结构（小端）：[total 4][total 4][packType 2][enc 1][res 1][body utf8][0x00 1]
        # total 字段值 = 4+4+body+1（dart serializeDouyu 原样照抄，斗鱼协议如此定义，非帧总字节数）
        body_b = body.encode("utf-8")
        total = 4 + 4 + len(body_b) + 1
        return struct.pack("<II", total, total) + struct.pack("<HBB", CLIENT_SEND_TO_SERVER, 0, 0) + body_b + b"\x00"

    # 解析二进制帧（处理粘包），反序列化为 STT 对象并分发消息。
    def decode_message(self, data: bytes | str) -> None:
        if isinstance(data, str):
            return  # 斗鱼是二进制帧
        # 处理粘包：可能一次收到多帧
        offset = 0
        n = len(data)
        while offset + 12 <= n:
            full_len = struct.unpack_from("<I", data, offset)[0]
            # 斗鱼长度域值 = 帧总字节数 - 4（不含首个长度域自身，见 _serialize 的 total 定义）。
            # 截断判断与帧推进均须按「整帧 = full_len + 4 字节」计算——2026-09-12 审查 C-2：
            # 原来只按 full_len 推进，粘包时第二帧起点错位 4 字节，长度域读出垃圾值后
            # 触发截断 break，第二帧起全部静默丢失（高热度直播间消息密集时必然粘包）。
            if full_len <= 0 or offset + full_len + 4 > n:
                break
            try:
                body_len = full_len - 9  # dart: bodyLength = fullMsgLength - 9
                if body_len < 0:
                    offset += full_len + 4
                    continue
                # 帧头结构：[full_len 4][full_len 4][packType 2][enc 1][res 1] = 12 字节，之后是 body 与尾0
                body_start = offset + 12
                body_end = body_start + body_len
                if body_end > n:
                    break
                body = data[body_start:body_end]
                stt = body.decode("utf-8", errors="ignore")
                obj = self._stt_to_obj(stt)
                self._dispatch(obj)
            except Exception as e:
                # 平台改版/异常帧时的唯一线索：异常类型 + 帧头 16 字节 hex，避免「0 弹幕零线索」
                logger.debug(
                    i18n.tr(
                        "[斗鱼弹幕]帧解析异常: {type_name} head={head}",
                        type_name=type(e).__name__,
                        head=data[offset : offset + 16].hex(),
                    )
                )
            offset += full_len + 4  # 下一帧起点：整帧长度 = full_len + 4（首个长度域自身不计入长度域值）

    # 递归解析 STT 文本协议为 dict/list（处理 @= / @A= 与转义），返回解析结果。
    @staticmethod
    def _stt_to_obj(s: str) -> Any:
        if "//" in s:
            return [DouyuDanmaku._stt_to_obj(x) for x in s.split("//") if x]
        if "@=" in s:
            result: dict = {}
            for field in s.split("/"):
                if not field:
                    continue
                k, sep, v = field.partition("@=")
                if not sep:
                    continue
                result[k] = DouyuDanmaku._stt_to_obj(DouyuDanmaku._unescape(v))
            return result
        if "@A=" in s:
            return DouyuDanmaku._stt_to_obj(DouyuDanmaku._unescape(s))
        return DouyuDanmaku._unescape(s)

    # 反转义 STT 特殊字符（@S→/，@A→@），返回还原后的字符串。
    @staticmethod
    def _unescape(s: str) -> str:
        return s.replace("@S", "/").replace("@A", "@")

    # 按 type 分发 STT 消息，处理普通弹幕（chatmsg）并 emit。
    def _dispatch(self, obj: Any) -> None:
        items = obj if isinstance(obj, list) else [obj]
        for it in items:
            if not isinstance(it, dict):
                continue
            t = it.get("type")
            if t == "chatmsg":
                fans = str(it.get("if", "0"))
                if self._only_fans and fans != "1":
                    continue
                col = 0
                try:
                    col = int(it.get("col", 0))
                except TypeError, ValueError:
                    col = 0
                self._emit(
                    DanmakuMessage(
                        type=DanmakuMessageType.CHAT,
                        user_name=str(it.get("nn", "")),
                        message=str(it.get("txt", "")),
                        color=_DOUYU_COLORS.get(col, "#FFFFFF"),
                    )
                )
            # superChat(comm_chatmsg/voice_trlt) 与 uenter 暂不处理，SRT 只录普通弹幕
