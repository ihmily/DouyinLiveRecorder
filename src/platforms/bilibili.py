# B站弹幕实现，移植自 dart simple_live_core 的 bilibili_danmaku.dart。
#
# 协议：WebSocket wss://{serverHost}/sub，大头序 16B 帧头
# [包长4][头长2=16][protover2][op4][seq4]。
# protover=2 需 zlib 解压，=3 需 brotli 解压（依赖 brotli 包）。

from __future__ import annotations

import asyncio
import json
import re
import struct
import zlib
from typing import Any, Union

import brotli
from loguru import logger

from src.base import DanmakuBase, DanmakuMessage, DanmakuMessageType
from src.ws_client import WsClient

HEADER_LEN = 16


# B站弹幕客户端：封装 WebSocket 连接、进房、心跳与消息解密。
class BilibiliDanmaku(DanmakuBase):
    heartbeat_interval = 60.0  # 60s

    # 初始化：调用父类并重置内部状态（参数、WS 连接、进房标志）。
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._args: dict = {}
        self._ws: WsClient | None = None
        self._session_ok = False
        self._auth_ok = False

    # 启动：解析房间/服务器参数，逐个尝试 host 建立 WebSocket 连接，失败则回调 on_close。
    async def start(self, args: Any) -> None:
        self._args = args if isinstance(args, dict) else {}
        server_host = self._args.get("server_host", "")
        room_id = self._args.get("room_id")
        if not server_host or not room_id:
            if self._on_close:
                self._on_close("缺少 server_host/room_id")
            return

        hosts = [str(h) for h in (self._args.get("host_list") or []) if h]
        if server_host and server_host not in hosts:
            hosts.insert(0, server_host)
        if not hosts:
            if self._on_close:
                self._on_close("无可用弹幕服务器")
            self._session_ok = False
            return

        # 逐个尝试 getDanmuInfo 返回的 host，全部连不上才放弃（单 host 固定会卡死）
        cookie = self._args.get("cookie", "")
        for idx, host in enumerate(hosts):
            if self._stopped:
                return
            backup = hosts[idx + 1] if idx + 1 < len(hosts) else None
            self._ws = WsClient(
                url=f"wss://{host}/sub",
                backup_url=f"wss://{backup}/sub" if backup else None,
                heartbeat_interval=self.heartbeat_interval,
                on_message=self.decode_message,
                on_ready=self._on_ws_ready,
                on_heartbeat=self.heartbeat,
                on_close=self._on_close,
                on_reconnect=self._on_close,
                headers={"cookie": cookie} if cookie else None,
                max_reconnect=2,
                reconnect_interval=3.0,
                connect_timeout=8.0,
            )
            await self._ws.connect()
            if self._session_ok or self._stopped:
                break

    # WS 就绪回调：置进房成功标志、触发 on_ready 并异步发送进房包。
    def _on_ws_ready(self) -> None:
        self._session_ok = True
        if self._on_ready:
            self._on_ready()
        asyncio.ensure_future(self._join_room())

    # 异步发送进房请求（uid/roomid/token 等），加入指定直播间。
    async def _join_room(self) -> None:
        if self._ws is None:
            return
        # 与 dart 一致：uid/buvid 匿名亦可，token 必须。
        # uid 必须是观众自身 uid（匿名=0），不能传房间主的 uid（get_bilibili_danmaku_info
        # 返回的 uid 是主播 uid）：真机对照探针证实 uid=主播uid 时弹幕服务器在 AUTH 后
        # 立刻硬断连（1006 / "no close frame"），uid=0 则正常收到 AUTH_REPLY 与弹幕。
        # 登录态 cookie（SESSDATA）携带 DedeUserID 时取其作为观众 uid。
        _m = re.search(r"DedeUserID=(\d+)", str(self._args.get("cookie") or ""))
        viewer_uid = int(_m.group(1)) if _m else 0
        join_body = json.dumps(
            {
                "uid": viewer_uid,
                "roomid": int(self._args.get("room_id", 0)),
                "protover": 3,
                "buvid": self._args.get("buvid", ""),
                "platform": "web",
                "type": 2,
                "key": str(self._args.get("token", "")),
            },
            separators=(",", ":"),
        )
        await self._ws.send(self._encode(join_body, action=7))

    # 进房认证超时（秒）：AUTH 发出后该时长内未收到 code=0 回应视为被拒/异常
    _AUTH_TIMEOUT = 8.0

    # 认证看门狗：进房包发出后限时未收到 AUTH_REPLY(code=0) 则按被拒处理。
    # 部分拒绝形态下服务器不回 AUTH_REPLY（连接保持、静默不推弹幕），与 code!=0 的
    # 软拒绝表现一致，靠看门狗兜底断开，避免"连接就绪"却 0 弹幕且无任何日志。
    # ws 为发送进房包时的连接实例：若期间已切换到下一 host，本次看门狗作废。
    async def _auth_watchdog(self, ws: WsClient) -> None:
        await asyncio.sleep(self._AUTH_TIMEOUT)
        if self._stopped or self._auth_ok:
            return
        if self._ws is not ws:
            return  # 会话已切换 host，旧看门狗作废
        logger.warning(f"[B站弹幕]进房认证 {self._AUTH_TIMEOUT:.0f} 秒无回应，按被拒处理主动断开")
        self._reject_auth()

    # 认证被拒统一处理：置停止标志、关闭连接，并使 spider 侧 buvid 缓存失效——
    # 兜底随机 UUID 被服务器拒绝后不可复用，失效后下一轮监测重新走真实获取链
    # （cookie/spi/首页 Set-Cookie）。真实 buvid 被拒时重取亦无副作用。
    def _reject_auth(self) -> None:
        self._stopped = True
        if self._ws is not None:
            asyncio.ensure_future(self._ws.close())
        try:
            from src import spider  # 懒加载：避免 platforms <-> spider 循环导入

            spider.invalidate_bili_buvid_cache()
        except Exception:
            pass

    # 发送心跳包（action=2），维持 WebSocket 长连接。
    async def heartbeat(self) -> None:
        if self._ws is not None:
            await self._ws.send(self._encode("", action=2))

    # 停止：置停止标志并关闭 WebSocket 连接。
    async def stop(self) -> None:
        self._stopped = True
        if self._ws is not None:
            await self._ws.close()

    # 将文本按 B站 16 字节大头序帧头封装为发送字节串，返回 bytes。
    @staticmethod
    def _encode(msg: str, action: int) -> bytes:
        data = msg.encode("utf-8")
        return struct.pack(">IHHII", len(data) + HEADER_LEN, HEADER_LEN, 0, action, 1) + data

    # 解析收到的字节流（处理粘包），逐帧解码并分发弹幕/在线消息。
    def decode_message(self, data: Union[bytes, str]) -> None:
        if isinstance(data, str):
            return
        # 粘包循环：一帧最少 16 字节头
        offset = 0
        n = len(data)
        while offset + HEADER_LEN <= n:
            packet_len = struct.unpack_from(">I", data, offset)[0]
            if packet_len < HEADER_LEN or offset + packet_len > n:
                break
            try:
                self._decode_packet(data[offset : offset + packet_len])
            except Exception:
                pass  # 单帧解析失败不影响后续/录像
            offset += packet_len

    # 解码单帧：按 protover 解压，解析心跳回应/弹幕消息并 emit。
    def _decode_packet(self, frame: bytes) -> None:
        if len(frame) < HEADER_LEN:
            return
        proto_ver = struct.unpack_from(">H", frame, 6)[0]
        operation = struct.unpack_from(">I", frame, 8)[0]
        body = frame[HEADER_LEN:]

        if operation == 3:
            # 心跳回应：4B 人气值
            if len(body) >= 4:
                online = struct.unpack_from(">I", body, 0)[0]
                self._emit(
                    DanmakuMessage(
                        type=DanmakuMessageType.ONLINE,
                        user_name="",
                        message="",
                        data=online,
                        color="#FFFFFF",
                    )
                )
            return

        if operation == 8:
            # 进房包（AUTH）回应：code==0 才会推送弹幕。非 0 时弹幕服务器软拒绝——连接保持
            # 不断开也不推弹幕，此前完全无感知（表现为"连接就绪"但 0 弹幕）。显式校验并
            # 主动断开（_reject_auth 同时使 buvid 缓存失效，下一轮重新获取），等待下一轮
            # 监测重新取参数进房。
            try:
                reply = json.loads(body.decode("utf-8", errors="ignore") or "{}")
            except Exception:
                reply = {}
            code = reply.get("code", -1) if isinstance(reply, dict) else -1
            if code == 0:
                self._auth_ok = True  # 解除认证看门狗
                logger.debug("[B站弹幕]进房认证成功（AUTH_REPLY code=0）")
            else:
                logger.warning(f"[B站弹幕]进房认证失败（AUTH_REPLY code={code}），主动断开: {reply}")
                self._reject_auth()
            return
        if operation != 5:
            return  # 其他操作码忽略

        try:
            if proto_ver == 2:
                payload = zlib.decompress(body)
            elif proto_ver == 3:
                payload = brotli.decompress(body)
            else:
                payload = body
        except Exception:
            return  # 解压失败丢弃

        # 解压后的包内多条 JSON 以控制字符（\x00-\x1f）分隔（与 dart split [\x00-\x1f] 一致），
        # 使用 splitlines 会把整包当一行导致 json.loads 失败，这里按控制字符切分
        for item in re.split(r"[\x00-\x1f]+", payload.decode("utf-8", errors="ignore")):
            item = item.strip()
            if len(item) > 2 and item.startswith("{"):
                try:
                    self._parse_message(json.loads(item))
                except Exception:
                    pass

    # 解析单条 JSON 弹幕消息（弹幕/SC），提取内容、用户、颜色并 emit。
    def _parse_message(self, obj: dict) -> None:
        cmd = str(obj.get("cmd", ""))
        if "DANMU_MSG" in cmd:
            info = obj.get("info")
            if isinstance(info, list) and len(info) > 2:
                message = str(info[1])
                color_int = 0
                # info[0][3] 为弹幕颜色十进制
                try:
                    if isinstance(info[0], list) and len(info[0]) > 3:
                        color_int = int(info[0][3])
                except TypeError, ValueError:
                    color_int = 0
                user_info = info[2]
                if isinstance(user_info, list) and len(user_info) > 1:
                    self._emit(
                        DanmakuMessage(
                            type=DanmakuMessageType.CHAT,
                            user_name=str(user_info[1]),
                            message=message,
                            color=f"#{color_int:06X}" if color_int else "#FFFFFF",
                        )
                    )
        elif cmd == "SUPER_CHAT_MESSAGE":
            data = obj.get("data")
            if data:
                self._emit(
                    DanmakuMessage(
                        type=DanmakuMessageType.SUPER_CHAT,
                        user_name=str(data.get("user_info", {}).get("uname", "")),
                        message=str(data.get("message", "")),
                        data=data,
                        color="#FFFFFF",
                    )
                )
