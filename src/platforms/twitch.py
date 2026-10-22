# Twitch 弹幕实现，移植自 dart simple_live_core 的 twitch_danmaku.dart。
#
# 协议：wss://irc-ws.chat.twitch.tv 纯 IRC 文本，匿名登录，PING/PONG 心跳。
# args：{"channel": "房间名", "proxy": "http://127.0.0.1:7890"} 或直接房间名字符串。
# 代理：Twitch 需海外网络，优先用 main 传入的 proxy（录制所用 proxy_address），否则跟随系统代理
# （urllib getproxies，与录制 abroad 路径一致），无代理则直连。

from __future__ import annotations

import random
import re
import urllib.request
from typing import Any, Union

from src.base import DanmakuBase, DanmakuMessage, DanmakuMessageType
from src.utils import handle_proxy_addr
from src.ws_client import WsClient

SERVER_URL = "wss://irc-ws.chat.twitch.tv"

_PRIVMSG_RE = re.compile(r"PRIVMSG [^:]+:(.+)")
_NAME_RE = re.compile(r"display-name=([^;]+);")
_COLOR_RE = re.compile(r"color=#([a-zA-Z0-9]{6});")


# Twitch 弹幕客户端：基于 IRC over WebSocket 匿名进房并解析 PRIVMSG 聊天消息。
class TwitchDanmaku(DanmakuBase):
    heartbeat_interval = 40.0  # IRC 侧无服务端心跳，靠本端按时发 PONG 保活

    # 记录频道名与 WS 客户端占位；真正建连在 start()。
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._channel: str = ""
        self._ws: WsClient | None = None
        self._line_buf = ""  # MI-21：跨帧半行缓冲（见 decode_message）

    # 启动监听：解析频道名 → 确定代理 → 建立 WebSocket 长连接；无频道名时回调 on_close 并返回。
    async def start(self, args: Any) -> None:
        proxy = None
        if isinstance(args, dict):
            self._channel = str(args.get("channel", ""))
            proxy = args.get("proxy")
        else:
            self._channel = str(args)
        self._channel = self._channel.lstrip("#").strip()
        if not self._channel:
            if self._on_close:
                self._on_close("缺少 channel")
            return

        proxy_addr = handle_proxy_addr(proxy)
        if not proxy_addr:
            for _scheme in ("https", "http"):
                _p = urllib.request.getproxies().get(_scheme)
                if _p:
                    proxy_addr = handle_proxy_addr(_p)
                    break

        self._ws = WsClient(
            url=SERVER_URL,
            heartbeat_interval=self.heartbeat_interval,
            on_message=self.decode_message,
            on_ready=self._on_ws_ready,
            on_heartbeat=self.heartbeat,
            on_close=self._on_close,
            on_reconnect=self._on_reconnect,
            proxy=proxy_addr,
        )
        await self._ws.connect()

    # WebSocket 连接就绪回调：向上层抛 on_ready，随后立即发送 IRC 登录/进房指令。
    def _on_ws_ready(self) -> None:
        if self._on_ready:
            self._on_ready()
        self._join_room()

    # 发送 IRC 匿名登录与进房序列（CAP/PASS/NICK/USER/JOIN），无返回值。
    def _join_room(self) -> None:
        if self._ws is None:
            return
        # justinfan+随机数字是 Twitch 官方约定的匿名只读昵称，配合固定口令 SCHMOOPIIE 可免登录收弹幕
        user = f"justinfan{1000 + random.randint(0, 99999 - 1000)}"
        for line in (
            "CAP REQ :twitch.tv/tags twitch.tv/commands twitch.tv/membership",
            "PASS SCHMOOPIIE",
            f"NICK {user}",
            f"USER {user} 8 * :{user}",
            f"JOIN #{self._channel}",
        ):
            self._ws.send_nowait(line)

    # 心跳：主动发送 IRC PONG 保活（由 WsClient 按 heartbeat_interval 定时调用）。
    async def heartbeat(self) -> None:
        if self._ws is not None:
            await self._ws.send("PONG :tmi.twitch.tv")

    # 停止监听：置停止标记并关闭 WebSocket 连接。
    async def stop(self) -> None:
        self._stopped = True
        if self._ws is not None:
            await self._ws.close()

    # 解析服务端下行文本（bytes 或 str）：逐行处理，收到 PING 立刻回 PONG，
    # 匹配到 PRIVMSG 则提取昵称/内容/颜色并 _emit 一条 CHAT 弹幕。无返回值。
    def decode_message(self, data: Union[bytes, str]) -> None:
        if isinstance(data, bytes):
            text = data.decode("utf-8", errors="ignore")
        else:
            text = data

        # MI-21：按行缓冲，跨帧的半行要拼回下帧再解析——WebSocket 的边界是**消息**而非行，
        # 高流量频道下服务端会把一条 IRC 消息切成两帧；逐帧独立 split 会把前后半行当独立行，
        # 正则双双失配 → 弹幕静默丢失（且无日志）。
        text = self._line_buf + text
        _parts = text.split("\n")
        self._line_buf = _parts.pop()  # 末段可能不完整，留到下帧
        for line in _parts:
            line = line.strip("\r")
            if line.startswith("PING"):
                if self._ws is not None:
                    self._ws.send_nowait(line.replace("PING", "PONG", 1))
            content_match = _PRIVMSG_RE.search(line)
            name_match = _NAME_RE.search(line)
            color_match = _COLOR_RE.search(line)
            # color 是可选标签：观众未设置颜色时下发 "color=;"（无 hex 值）。故只要求 PRIVMSG +
            # display-name 命中——要求三标签全中会让未设颜色观众的整条弹幕被静默丢弃。
            if content_match and name_match:
                color = "#FFFFFF"
                color_int = 0
                if color_match:
                    try:
                        color_int = int(color_match.group(1), 16)
                        color = f"#{color_match.group(1)}"
                    except ValueError:
                        color = "#FFFFFF"
                        color_int = 0
                # 纯黑(0x000000)在深色弹幕背景上不可见，统一回退为白色
                if color_int == 0:
                    color = "#FFFFFF"
                self._emit(
                    DanmakuMessage(
                        type=DanmakuMessageType.CHAT,
                        user_name=name_match.group(1),
                        message=content_match.group(1),
                        color=color,
                    )
                )
