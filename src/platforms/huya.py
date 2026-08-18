# 虎牙弹幕实现，移植自 dart simple_live_core 的 huya_danmaku.dart。
#
# 协议：WebSocket wss://cdnws.api.huya.com + Tars 编码（本地极简实现，见 _tars.py）。
# - 加入房间：WSCmd{iCmdType=1, iCmdData=WSRegisterReq{ayyuid,true,"","",topSid,subSid,0,0}}
# - 心跳：硬编码字节（与 dart 一致）
# - 推送：WSCmd.iCmdType==7 时取 iCmdData 解析 HYPushMessage：
#  uri=1400 弹幕(HYMessage)，uri=8006 在线人数

from __future__ import annotations

import asyncio
import base64
from typing import Any, Union

from src.base import DanmakuBase, DanmakuMessage, DanmakuMessageType
from src.platforms._tars import TarsInputStream, TarsOutputStream
from src.ws_client import WsClient

SERVER_URL = "wss://cdnws.api.huya.com"

# 与 dart 相同的硬编码心跳包
HEARTBEAT_DATA = base64.b64decode("ABQdAAwsNgBM")

# 弹幕消息 uri
URI_CHAT = 1400
URI_ONLINE = 8006


# 虎牙弹幕客户端：Tars 编码进房数据、心跳与推送消息解析。
class HuyaDanmaku(DanmakuBase):
    heartbeat_interval = 60.0  # 60s

    # 初始化：调用父类并重置内部状态（参数、WS 连接）。
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._args: dict = {}
        self._ws: WsClient | None = None

    # 启动：解析 ayyuid/topSid 等参数，建立虎牙 WS 连接；缺失则回调 on_close。
    async def start(self, args: Any) -> None:
        self._args = args if isinstance(args, dict) else {}
        if not self._args.get("ayyuid") or not self._args.get("topSid"):
            if self._on_close:
                self._on_close("缺少 ayyuid/topSid")
            return

        self._ws = WsClient(
            url=SERVER_URL,
            heartbeat_interval=self.heartbeat_interval,
            on_message=self.decode_message,
            on_ready=self._on_ws_ready,
            on_heartbeat=self.heartbeat,
            on_close=self._on_close,
            on_reconnect=self._on_close,
        )
        await self._ws.connect()

    # WS 就绪回调：触发 on_ready 并异步发送进房数据。
    def _on_ws_ready(self) -> None:
        if self._on_ready:
            self._on_ready()
        asyncio.ensure_future(self._join_room())

    # 异步发送进房数据（WSRegisterReq）加入直播间。
    async def _join_room(self) -> None:
        if self._ws is None:
            return
        await self._ws.send(self._make_join_data())

    # 构造 Tars 编码的进房数据字节串（WSCmd iCmdType=1），返回 bytes。
    def _make_join_data(self) -> bytes:
        # 与 dart getJoinData(ayyuid, topSid, topSid) 完全一致:
        # 注意 tag5(tid/sid) 也填 topSid,而非 lSubChannelId(subSid 不参与 join)
        oos = TarsOutputStream()
        oos.write_int(int(self._args.get("ayyuid") or 0), 0)
        oos.write_bool(True, 1)
        oos.write_string("", 2)
        oos.write_string("", 3)
        oos.write_int(int(self._args.get("topSid") or 0), 4)
        oos.write_int(int(self._args.get("topSid") or 0), 5)
        oos.write_int(0, 6)
        oos.write_int(0, 7)

        wscmd = TarsOutputStream()
        wscmd.write_int(1, 0)
        wscmd.write_bytes(oos.to_bytes(), 1)
        return wscmd.to_bytes()

    # 发送硬编码心跳字节包维持连接。
    async def heartbeat(self) -> None:
        if self._ws is not None:
            await self._ws.send(HEARTBEAT_DATA)

    # 停止：置停止标志并关闭 WebSocket 连接。
    async def stop(self) -> None:
        self._stopped = True
        if self._ws is not None:
            await self._ws.close()

    # 解析 Tars 帧：识别 cmdType==7 的消息推送并解码 HYPushMessage。
    def decode_message(self, data: Union[bytes, str]) -> None:
        if isinstance(data, str):
            return
        try:
            stream = TarsInputStream(data)
            cmd_type = stream.read_int(0)
            if cmd_type != 7:
                return  # 非消息推送（如注册回应），忽略
            push_data = stream.read_bytes(1)
            self._decode_push_message(push_data)
        except Exception:
            pass  # 无效包丢弃，不影响录像

    # 解析推送消息：按 uri 分发弹幕(1400)/在线人数(8006)。
    def _decode_push_message(self, data: bytes) -> None:
        stream = TarsInputStream(data)
        uri = stream.read_int(1)
        msg = stream.read_bytes(2)

        if uri == URI_CHAT:
            self._decode_chat(msg)
        elif uri == URI_ONLINE:
            # dart: online = stream.read(online, 0) → 直接读 tag0
            s = TarsInputStream(msg)
            online = s.read_int(0)
            self._emit(
                DanmakuMessage(
                    type=DanmakuMessageType.ONLINE,
                    user_name="",
                    message="",
                    data=online,
                    color="#FFFFFF",
                )
            )

    # 解析 HYMessage 弹幕：提取发送者昵称、内容与颜色并 emit。
    def _decode_chat(self, msg: bytes) -> None:
        # msg 即 HYMessage 平铺字段(tag0=userInfo 结构体, tag3=内容, tag6=bulletFormat),
        # 与 dart HYMessage.readFrom 一致;不要再包一层 read_struct(0, ...)。
        stream = TarsInputStream(msg)

        # 从 userInfo 结构体解析出发送者昵称，返回 {nick_name}。
        def parse_sender(inner: "TarsInputStream") -> dict:
            nick = inner.read_string(2)
            inner.finish_struct()
            return {"nick_name": nick}

        sender = stream.read_struct(0, parse_sender) or {"nick_name": ""}
        content = stream.read_string(3)
        # bulletFormat(tag6) 里的 iFontColor
        font_color = 0

        # 从 bulletFormat 结构体解析出弹幕字体颜色(int)。
        def parse_format(f: "TarsInputStream") -> None:
            nonlocal font_color
            font_color = f.read_int(0)
            f.finish_struct()

        stream.read_struct(6, parse_format)

        color = "#FFFFFF" if font_color <= 0 else f"#{font_color:06X}"
        self._emit(
            DanmakuMessage(
                type=DanmakuMessageType.CHAT,
                user_name=sender["nick_name"],
                message=content,
                color=color,
            )
        )
