# 弹幕采集器：将异步弹幕客户端包装为可被同步录制流程调用的线程化采集器。
#
# 职责：
# - 在独立线程里跑 asyncio event loop，驱动平台 DanmakuBase 客户端
# - 收到 DanmakuMessage 后记录时间戳，推给 SrtWriter 写盘（write_srt=False 时跳过）
# - 将全部类型消息与连接状态上报弹幕监控枢纽（DanmakuMonitorHub），供 GUI/Web 监控
# - 对外提供同步的 start() / stop()，与 ffmpeg 子进程同起同停
#
# 为何独立线程：main.py 录制主循环是同步线程，弹幕 WS 需常驻连接不能阻塞录制，
# 因此单独起线程跑自己的 asyncio loop。

from __future__ import annotations

import asyncio
import threading
import time
from typing import Any, Optional, Type, cast

from src.base import DanmakuBase, DanmakuMessage, DanmakuMessageType
from src.danmaku_monitor import DanmakuMonitorHub
from src.logger import logger
from src.srt_writer import SrtWriter


# 弹幕采集器：在独立守护线程的 asyncio loop 中驱动某平台弹幕客户端，
# 把收到的聊天弹幕写入 SrtWriter，并把全部消息上报监控枢纽；
# 对外只暴露同步的 start() / stop() 与 message_count。
class DanmakuCollector:
    # 初始化采集器：danmaku_cls 为平台弹幕类，danmaku_args 为其启动参数，
    # base_filename 为 SRT 文件名前缀，segment_seconds 为分片时长，only_fans 为仅粉丝弹幕开关；
    # room_name / platform_name 为监控枢纽中的房间与平台显示名；
    # write_srt=False 表示仅监控不落 SRT 文件（弹幕监控开、弹幕录制关的模式）；
    # monitor 可注入测试用枢纽，缺省惰性取进程级单例 get_hub()。
    def __init__(
        self,
        danmaku_cls: Type[DanmakuBase],
        danmaku_args: Any,
        base_filename: str,
        segment_seconds: Optional[float] = 1800.0,
        only_fans: bool = True,
        room_name: Optional[str] = None,
        platform_name: Optional[str] = None,
        write_srt: bool = True,
        monitor: Optional[DanmakuMonitorHub] = None,
    ) -> None:
        self._danmaku_cls = danmaku_cls
        self._danmaku_args = danmaku_args
        # 仅监控模式（write_srt=False）不创建 SrtWriter、不落任何 SRT 文件
        self._srt: Optional[SrtWriter] = (
            SrtWriter(base_filename=base_filename, segment_seconds=segment_seconds) if write_srt else None
        )
        self._only_fans = only_fans
        # 监控显示名：房间名缺省用弹幕类名，平台名缺省同样回退类名
        # （getattr 兜底：测试替身可能是无 __name__ 的 Mock）
        _cls_name = str(getattr(self._danmaku_cls, "__name__", "danmaku"))
        self._room_name = room_name or _cls_name
        self._platform_name = platform_name or _cls_name
        self._monitor: Optional[DanmakuMonitorHub] = monitor

        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._danmaku: Optional[DanmakuBase] = None
        self._stop_event = threading.Event()
        self._started = False
        self._stop_called = False  # stop() 防重入标记：提前中断与尾收兜底可能重复触发
        self._msg_count = 0

    # 惰性解析监控枢纽：未显式注入时取进程级单例（失败静默返回 None，监控缺位不影响录制）。
    def _monitor_hub(self) -> Optional[DanmakuMonitorHub]:
        if self._monitor is None:
            try:
                from src.danmaku_monitor import get_hub

                self._monitor = get_hub()
            except Exception:
                return None
        return self._monitor

    # 启动采集：锚定 SRT 时间轴并拉起后台守护线程，重复调用无效；无返回值且不抛异常。
    def start(self) -> None:
        # 启动采集线程（非阻塞）。失败仅记录，不抛异常以免影响录像。
        if self._started:
            return
        self._started = True
        # 弹幕时间轴锚定到启动时刻(≈ffmpeg 录像起点)并立即创建 SRT 文件:
        # 否则以首条弹幕为 T0,弹幕与视频时间轴错位(视频已录 N 秒 SRT 才创建)。
        if self._srt is not None:
            try:
                self._srt.start()
            except Exception as e:
                logger.warning(f"[弹幕采集]SRT 初始化失败(继续尝试写弹幕): {e}")
        # 上报监控枢纽：房间采集开始（重置该房间统计）
        hub = self._monitor_hub()
        if hub is not None:
            hub.room_started(self._room_name, self._platform_name)
        self._thread = threading.Thread(target=self._run, name=f"danmaku_{self._danmaku_cls.__name__}", daemon=True)
        self._thread.start()

    # 停止采集：置停止标记、跨线程调度关闭弹幕连接，最多等待 timeout 秒回收线程，最后关闭 SRT 文件。
    # 幂等：重复调用直接返回（录制提前中断与 ffmpeg 正常退出两条路径都可能触发 stop）。
    def stop(self, timeout: float = 8.0) -> None:
        # 停止采集并 flush SRT。
        if self._stop_called:
            return
        self._stop_called = True
        # 上报监控枢纽：房间采集结束（连接状态置离线）
        hub = self._monitor_hub()
        if hub is not None:
            hub.room_closed(self._room_name, "采集停止")
        if not self._started:
            # 未启动也要尝试关 SRT（空文件）
            if self._srt is not None:
                self._srt.close()
            return
        self._stop_event.set()
        loop = self._loop
        if loop is not None and loop.is_running():
            try:
                loop.call_soon_threadsafe(self._schedule_stop)
            except Exception:
                pass
        if self._thread is not None:
            self._thread.join(timeout=timeout)
        if self._srt is not None:
            self._srt.close()

    # 在采集线程的 loop 中执行：投递一个关闭协程用于停止弹幕客户端并停掉 loop，无返回值。
    def _schedule_stop(self) -> None:
        # 内部协程：先 await 弹幕客户端 stop()（异常忽略），再停止事件循环。
        async def _shutdown() -> None:
            if self._danmaku is not None:
                try:
                    await self._danmaku.stop()
                except Exception:
                    pass
            if self._loop is not None:
                self._loop.stop()

        if self._loop is not None:
            asyncio.ensure_future(_shutdown())

    # 采集线程主体：新建并绑定事件循环，实例化平台弹幕类（注入三个回调、透传 only_fans），
    # 阻塞运行 danmaku.start() 直到连接结束或被停止；退出前关闭 loop 并打印收到条数，无返回值。
    def _run(self) -> None:
        # DEBUG 状态噪音,已按要求注释:
        # logger.debug(f"[弹幕采集]{self._danmaku_cls.__name__} 采集线程已启动")
        loop = asyncio.new_event_loop()
        self._loop = loop
        asyncio.set_event_loop(loop)
        try:
            danmaku = self._danmaku_cls(
                on_message=self._on_message,
                on_close=self._on_close,
                on_ready=self._on_ready,
            )
            # 透传 only_fans（斗鱼等支持的平台）
            if hasattr(danmaku, "_only_fans"):
                cast(Any, danmaku)._only_fans = self._only_fans
            self._danmaku = danmaku
            try:
                # start() 内部会阻塞直到连接关闭或 stop() 被调用（stop 经 call_soon_threadsafe 关闭 ws）
                loop.run_until_complete(danmaku.start(self._danmaku_args))
            except (asyncio.CancelledError, RuntimeError):
                pass
            except Exception as e:
                logger.warning(f"[弹幕采集]{self._danmaku_cls.__name__} 运行异常,不影响录制: {e}")
        finally:
            logger.debug(f"[弹幕采集]{self._danmaku_cls.__name__} 采集线程已退出,共收到 {self._msg_count} 条消息")
            try:
                loop.close()
            except Exception:
                pass
            self._loop = None

    # ---- 回调（在采集线程的 loop 中调用）----
    # 收到弹幕回调：全部类型转发监控枢纽；SRT 仅记录 CHAT 且用户名或内容非空的消息，
    # 计数后按当前 monotonic 时间写入 SRT。
    def _on_message(self, msg: DanmakuMessage) -> None:
        # 监控侧不过滤消息类型（聊天/礼物/在线人数/SC 全部上报，由枢纽分别处理）
        hub = self._monitor_hub()
        if hub is not None:
            hub.room_message(self._room_name, msg.type.value, msg.user_name, msg.message)
        if msg.type != DanmakuMessageType.CHAT:
            return  # SRT 当前只录普通弹幕
        if not msg.user_name and not msg.message:
            return
        self._msg_count += 1
        # DEBUG 状态噪音(每条弹幕都给一条),已按要求注释:
        # if self._msg_count == 1:
        #     logger.debug(f"[弹幕采集]{self._danmaku_cls.__name__} 收到第一条弹幕: {msg.user_name}: {msg.message}")
        now = time.monotonic()
        # 在工作线程直接写 SRT（SrtWriter 内部已加锁）；仅监控模式无 SrtWriter
        if self._srt is not None:
            self._srt.write(msg.user_name, msg.message, now=now)

    # 连接就绪回调：上报监控枢纽并输出一条 debug 日志，无返回值。
    def _on_ready(self) -> None:
        hub = self._monitor_hub()
        if hub is not None:
            hub.room_connected(self._room_name)
        logger.debug(f"[弹幕采集]{self._danmaku_cls.__name__} 连接就绪,开始接收弹幕")

    # 连接关闭回调：上报监控枢纽，并把关闭原因 reason 记入 debug 日志，无返回值。
    def _on_close(self, reason: str) -> None:
        hub = self._monitor_hub()
        if hub is not None:
            hub.room_closed(self._room_name, reason)
        logger.debug(f"[弹幕采集]{self._danmaku_cls.__name__} 连接关闭: {reason}")

    # 只读属性：返回本次采集已写入的弹幕条数（int）。
    @property
    def message_count(self) -> int:
        return self._msg_count
