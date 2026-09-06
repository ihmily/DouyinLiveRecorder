# 弹幕模块基类与数据结构（对标 dart simple_live_core 的 LiveDanmaku / LiveMessage）。
#
# 本模块定义各平台弹幕实现的公共契约与传输数据结构：
# - DanmakuMessageType：弹幕消息类型枚举（聊天/礼物/在线人数/醒目留言）
# - DanmakuMessage：单条弹幕的数据载体（类型、用户名、内容、颜色、时间戳等）
# - DanmakuBase：抽象基类，各平台子类实现 start/stop/heartbeat/decode_message，
#   并通过 on_message / on_close / on_ready 回调把事件上抛给采集器。

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Optional


# 弹幕消息类型枚举：取值为字符串（chat/gift/online/superChat），供消息过滤与分发判断使用。
class DanmakuMessageType(Enum):
    # 弹幕消息类型，对标 dart LiveMessageType。

    CHAT = "chat"
    GIFT = "gift"
    ONLINE = "online"
    SUPER_CHAT = "superChat"


# 单条弹幕消息数据类：字段含消息类型 type、用户名 user_name、正文 message、
# 平台原始数据 data、显示颜色 color 与相对时间戳 timestamp_ms（由采集器注入）。
@dataclass
class DanmakuMessage:
    # 单条弹幕消息，对标 dart LiveMessage。
    #
    #    timestamp_ms 由 DanmakuCollector 在收到时注入（time.monotonic 基准的相对秒），
    #    平台实现不写该字段。

    type: DanmakuMessageType
    user_name: str
    message: str
    data: Any = None
    color: str = "#FFFFFF"
    timestamp_ms: float = 0.0


# 平台弹幕客户端抽象基类：统一连接生命周期与回调协议，子类需实现四个抽象方法。
class DanmakuBase(ABC):
    # 弹幕基类，对标 dart LiveDanmaku。
    #
    #    每个平台实现 start / stop / heartbeat / decode_message 四个方法。
    #    收到可分发的弹幕时调 self._on_message(DanmakuMessage(...))。

    heartbeat_interval: float = 45.0  # 秒，各平台子类覆盖

    # 初始化基类：保存收到弹幕 on_message、连接关闭 on_close、连接就绪 on_ready 三个回调，
    # 并把停止标记 _stopped 置为 False；无返回值。
    def __init__(
        self,
        on_message: Optional[Callable[[DanmakuMessage], None]] = None,
        on_close: Optional[Callable[[str], None]] = None,
        on_ready: Optional[Callable[[], None]] = None,
    ) -> None:
        self._on_message = on_message
        self._on_close = on_close
        self._on_ready = on_ready
        self._stopped = False

    # 抽象方法：用平台启动参数 args（room_id / token 等）建立连接并持续接收弹幕，无返回值。
    @abstractmethod
    async def start(self, args: Any) -> None:
        # 建立连接并开始接收弹幕。args 为该平台的启动参数（room_id / token 等）。
        pass

    # 抽象方法：停止接收弹幕并关闭底层连接，无入参无返回值。
    @abstractmethod
    async def stop(self) -> None:
        # 停止接收并关闭连接。
        pass

    # 抽象方法：向服务端发送一次平台约定的心跳包，由 WsClient 按 heartbeat_interval 定时调用。
    @abstractmethod
    async def heartbeat(self) -> None:
        # 发送一次心跳。由 WsClient 按时调用。
        pass

    # 抽象方法：解析一帧原始数据 data（bytes 或 str），解析结果经 _on_message 回调上抛，无返回值。
    @abstractmethod
    def decode_message(self, data: bytes | str) -> None:
        # 解析一帧原始数据，解析出的弹幕通过 self._on_message 回调上抛。
        pass

    # 供子类调用的分发入口：若已注册 on_message 回调则把 msg 交给上层（采集器），无返回值。
    def _emit(self, msg: DanmakuMessage) -> None:
        if self._on_message:
            self._on_message(msg)
