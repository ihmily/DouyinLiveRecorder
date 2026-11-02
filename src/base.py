# 弹幕模块基类与数据结构（对标 dart simple_live_core 的 LiveDanmaku / LiveMessage）。
# 定义各平台弹幕实现的公共契约：消息类型枚举、单条消息载体、客户端抽象基类
# （子类实现 start/stop/heartbeat/decode_message，经 on_message / on_close / on_ready 上抛事件）。

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Any, Awaitable, Callable, Optional

import i18n


# 消息类型枚举：取值为字符串（chat/gift/online/superChat），供过滤与分发判断使用。
class DanmakuMessageType(Enum):
    CHAT = "chat"
    GIFT = "gift"
    ONLINE = "online"
    SUPER_CHAT = "superChat"


# 单条弹幕消息载体（对标 dart LiveMessage）：data 是平台原始数据（如在线人数），color 是显示颜色。
# 消息不带时间戳：SRT 时间轴由采集侧在收到时单独取 monotonic，不依赖本类。
# [历史注] 原 timestamp_ms 字段全仓无写入无读取，已删除。
@dataclass
class DanmakuMessage:
    type: DanmakuMessageType
    user_name: str
    message: str
    data: Any = None
    color: str = "#FFFFFF"


# 后台弹幕协程的统一异常落盘：裸 asyncio.ensure_future 的异常只在任务被 GC 时以
# "Task exception was never retrieved" 打到 stderr，进房协程抛异常（如 room_id 非数字、
# 发送失败）会完全无日志地静默死亡；故各平台后台协程一律经 spawn_danmaku_task 起，
# 由完成回调捕获并落盘。
def _log_task_exception(task: "asyncio.Task[None]") -> None:
    if task.cancelled():
        return
    exc = task.exception()
    if exc is not None:
        from src import utils
        from src.logger import logger

        # 异常必须先 str() 再过 mask_credentials：后台弹幕协程抛出的多是 httpx/websockets 异常，
        # 其 str() 内嵌完整请求 URL（带 token/签名/代理 userinfo），而 logs/ 按大小轮转保留多份
        # = 凭据长期落盘。与 async_http / collector 同口径。
        # msgid 保持不变（四语目录 + web/app.js 五处同源，本文件不动目录）。
        # [历史注] 旧写法把异常**对象**直接塞进 {exc}，由 loguru 就地 str()，绕过了脱敏。
        logger.warning(
            i18n.tr(
                "[弹幕]后台协程异常: {type_name}: {exc}",
                type_name=type(exc).__name__,
                exc=utils.mask_credentials(str(exc)),
            )
        )


def spawn_danmaku_task(coro: Awaitable[None]) -> "asyncio.Task[None]":
    task = asyncio.ensure_future(coro)
    task.add_done_callback(_log_task_exception)
    return task


# 平台弹幕客户端抽象基类：统一连接生命周期与回调协议；子类收到可分发的弹幕时经
# self._emit(DanmakuMessage(...)) 上抛，而不是直接调 _on_message。
class DanmakuBase(ABC):
    heartbeat_interval: float = 45.0  # 秒，各平台子类覆盖

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

    # 重连是**中间态**（max_reconnect 次数内会自动恢复），不能复用 on_close——后者的语义是
    # 「房间已关闭」、会调监控枢纽 room_closed()，把重连当关闭上报会在面板留下假事件
    # （几秒后重连成功又活过来）。故独立成本回调：只记 debug 日志，不上报关闭。
    def _on_reconnect(self, reason: str) -> None:
        from src.logger import logger

        logger.debug(i18n.tr("[{cls}]弹幕连接断开，正在重连: {reason}", cls=type(self).__name__, reason=reason))

    # 抽象方法：用平台启动参数 args（room_id / token 等）建连并持续接收，直到被 stop 或连接结束。
    @abstractmethod
    async def start(self, args: Any) -> None:
        pass

    # 抽象方法：停止接收并关闭底层连接。
    @abstractmethod
    async def stop(self) -> None:
        pass

    # 抽象方法：发一次平台约定的心跳包，由 WsClient 按 heartbeat_interval 定时调用。
    @abstractmethod
    async def heartbeat(self) -> None:
        pass

    # 抽象方法：解析一帧原始数据（bytes 或 str），结果经 _emit 上抛。
    @abstractmethod
    def decode_message(self, data: bytes | str) -> None:
        pass

    # 唯一上抛出口：判空只此一处，回调缺省时静默丢弃。
    def _emit(self, msg: DanmakuMessage) -> None:
        if self._on_message:
            self._on_message(msg)
