# 弹幕采集器：把异步弹幕客户端包装成可被同步录制流程调用的线程化采集器。
#
# - 在独立线程里跑 asyncio event loop，驱动平台 DanmakuBase 客户端；
# - 收到 DanmakuMessage 后记时间戳，推给 SrtWriter 写盘（write_srt=False 时跳过）；
# - 全部类型消息与连接状态上报弹幕监控枢纽（DanmakuMonitorHub），供 GUI/Web 监控；
# - 对外只暴露同步的 start() / stop()，与 ffmpeg 子进程同起同停。
#
# 为何独立线程：main.py 录制主循环是同步线程，弹幕 WS 需常驻连接不能阻塞录制。

from __future__ import annotations

import asyncio
import queue
import threading
import time
from typing import Any, Optional, Type, cast

import i18n
from src import utils
from src.base import DanmakuBase, DanmakuMessage, DanmakuMessageType, spawn_danmaku_task
from src.danmaku_monitor import DanmakuMonitorHub
from src.logger import logger
from src.srt_writer import SrtWriter

# SRT 待写队列上限：10000 条对高热度直播间（数十条/秒 + 慢盘）足以吸收数分钟抖动；
# 超出即计数丢弃并聚合告警，保证内存有界而不是静默增长到 OOM。
# 内存界真正成立靠 _DANMAKU_TEXT_LIMIT 的单条截断：极端消息曾可放大到「条数上限 × 8MiB 帧」。
_SRT_QUEUE_MAXSIZE = 10000
# SRT 写盘连续失败时的告警间隔（秒）：逐条告警会在磁盘满时刷屏并放大 IO，改按时间窗聚合。
_SRT_WARN_INTERVAL = 60.0
# 单条弹幕文本（user_name/message）的统一截断上限（字符）：上游只限单帧解压 8MiB，一条批量帧
# 可解析出大量大文本消息，而 SRT 队列/边车队列/监控流都只按条数封顶——「按条数封顶」的内存界
# 在超大消息面前名不副实。在公共入口 _on_message 截断，SRT 与监控流共用同一口径；2000 字符远超
# 现实弹幕长度，不影响正常内容。
_DANMAKU_TEXT_LIMIT = 2000

# 弹幕客户端 stop() 的等待上限（秒）：SDK 因半开连接挂住时若无限等待，
# 关闭协程里的 loop.stop() 永不执行，采集线程永久驻留（join 超时后线程与 SRT 句柄双泄漏）。
_SHUTDOWN_TIMEOUT_SECONDS = 5.0

# stop() 等待「已发布但尚未 running」的 loop 进入 running 的上限（秒）。
# 该窗口位于 _run 发布 self._loop 之后、进入 run_until_complete 之前（正在构造平台弹幕客户端：
# 实例化 SDK / 拼装参数），实测毫秒级。轮询只为把停止信号投递进去，超上限仍未 running 时
# 由 _run 的二次复查兜底，故取值偏小即可。
_LOOP_RUNNING_WAIT_SECONDS = 0.5
# 轮询步长（秒）：0.02 × 25 = 上面的 0.5s 上限。正常路径 loop 早已 running，首次判断即通过、
# 不产生任何 sleep，故不会拖慢 stop()。
_LOOP_RUNNING_POLL_INTERVAL = 0.02
# stop() 等待 SRT 写线程退出的上限（秒）
_SRT_WRITER_JOIN_SECONDS = 3.0
# SRT 写线程 get() 的阻塞步长（秒）：把「阻塞在空队列上」变成有限等待，
# 队列满导致 sentinel 投不进去时，写线程仍能靠 _srt_stop 自检退出。
_SRT_QUEUE_POLL_SECONDS = 0.5
# 收尾异常的两种观测值（作日志实参、非文案，故不进 i18n 目录）
_SRT_SHUTDOWN_QUEUE_FULL = "queue-full"
_SRT_SHUTDOWN_JOIN_TIMEOUT = "join-timeout"


# 单房间采集器：同步 start() / stop() 入口，另有只读的 message_count。
class DanmakuCollector:
    # 仅记非显然语义：write_srt=False 表示只监控、不落 SRT 文件（弹幕监控开、录制关）；monitor 可
    # 注入测试用枢纽，缺省惰性取进程级单例 get_hub()；only_fans=None 表示不覆盖平台类默认值。
    def __init__(
        self,
        danmaku_cls: Type[DanmakuBase],
        danmaku_args: Any,
        base_filename: str,
        segment_seconds: Optional[float] = 1800.0,
        # 默认 None 而非 True——True 会经下方「hasattr → 覆盖实例属性」压掉平台类自己的刻意默认
        # （斗鱼为 False），使该修复在真实调用链上完全失效（普通弹幕被静默丢弃且无日志）。
        only_fans: Optional[bool] = None,
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
        # 监控显示名：房间名 / 平台名缺省时都回退弹幕类名。类名经 getattr 兜底并缓存到
        # self._cls_name——Mock 型测试替身可能没有 __name__，行内重复访问会在 start() 与日志处
        # 抛 AttributeError，而 start() 明确承诺不抛异常。
        _cls_name = str(getattr(self._danmaku_cls, "__name__", "danmaku"))
        self._room_name = room_name or _cls_name
        self._platform_name = platform_name or _cls_name
        self._cls_name = _cls_name
        self._monitor: Optional[DanmakuMonitorHub] = monitor

        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._danmaku: Optional[DanmakuBase] = None
        self._stop_event = threading.Event()
        self._started = False
        self._stop_called = False  # stop() 防重入标记：提前中断与尾收兜底可能重复触发
        # hub.room_closed 首投生效标记：stop() / _on_close / _run 异常兜底 / _rollback_start 四条
        # 路径都会上报「房间已关闭」，正常停止与意外掉线各有一对会先后触发；枢纽侧不去重（每次都
        # 写一条新 seq 的 conn/closed 事件），双投会让面板 closed 计数虚增。首次生效的语义在两种
        # 时序下都保留更准确的 reason：用户主动停 → stop() 先投（「采集停止」）；意外掉线 →
        # _on_close 先投（真实关闭原因），随后路径的补报才是冗余侧。
        self._room_closed_reported = False
        self._msg_count = 0
        # danmaku.start() 的任务引用：run_until_complete(协程) 会把协程包成任务却不留引用，
        # _shutdown 想取消也拿不到 → 只能 loop.stop() 硬切（stderr 刷「Task was destroyed but
        # it is pending」，且平台 start() 的 finally 清理链永不执行）。故 _run 显式建任务并留存。
        self._start_task: "Optional[asyncio.Task[None]]" = None
        self._shutdown_task: "Optional[asyncio.Task[None]]" = None
        # SRT 写入与弹幕接收解耦：_on_message 跑在 asyncio 事件循环上，若同步调 srt.write 会阻塞
        # ws_recv → 心跳掉线 / 对端断连误判。故把 (user, msg, now) 推入队列，由独立守护线程取出写盘。
        # 队列必须有界 + 满即计数丢弃：慢盘 / 网络盘 / 杀毒扫描 / 磁盘满时「写盘极快」的假设不成立，
        # 无界堆积会直致 OOM。
        # sentinel = None 通知消费者退出；stop() 在 srt.close() 之前先发 sentinel 并 join 线程，
        # 确保「队列清空 → srt.close 兜底刷尾」的顺序。
        self._srt_queue: "queue.Queue[Optional[tuple[str, str, float]]]" = queue.Queue(maxsize=_SRT_QUEUE_MAXSIZE)
        self._srt_dropped = 0  # 因队列满被丢弃的弹幕条数（丢弃必须可观测，见下）
        self._srt_writer: Optional[threading.Thread] = None
        # sentinel 投不进去（队列被慢盘填满）时的替代退出通道——写线程的
        # get(timeout=_SRT_QUEUE_POLL_SECONDS) 在队列排空后检查它，自检退出。
        # 与 _stop_event 分开是刻意的：_stop_event 参与「stop() ↔ _run」的反向序握手，
        # 复用同一事件会让两条保证互相耦合、日后改一处即悄悄破坏另一处。
        self._srt_stop = threading.Event()

    # 惰性解析监控枢纽：未显式注入时取进程级单例（失败静默返回 None，监控缺位不影响录制）。
    def _monitor_hub(self) -> Optional[DanmakuMonitorHub]:
        if self._monitor is None:
            try:
                from src.danmaku_monitor import get_hub

                self._monitor = get_hub()
            except Exception:
                # 吞没即正确：监控枢纽是旁路功能（导入失败 / 目录不可写 / 单例构造异常），
                # 返回 None 即「本采集器不上报监控」，录制与 SRT 落盘照常进行。
                # 重抛会让承诺「不影响录像」的 start()/回调变成异常源。
                return None
        return self._monitor

    # 启动采集：锚定 SRT 时间轴并拉起后台守护线程，重复调用无效；不抛异常（失败只记日志）。
    def start(self) -> None:
        if self._started:
            return
        self._started = True
        # 弹幕时间轴锚定到启动时刻(≈ffmpeg 录像起点)并立即创建 SRT 文件:
        # 否则以首条弹幕为 T0,弹幕与视频时间轴错位(视频已录 N 秒 SRT 才创建)。
        if self._srt is not None:
            try:
                self._srt.start()
            except Exception as e:
                # SRT 初始化失败的异常文本同样内嵌 base_filename 路径（可含主播名）与 OSError 的
                # strerror，进轮转日志前一律过码。
                logger.warning(
                    i18n.tr(
                        "[弹幕采集]SRT 初始化失败(继续尝试写弹幕): {e}",
                        e=utils.mask_credentials(str(e)),
                    )
                )
            # 启动 SRT 写盘守护线程：把 (user, msg, now) 从队列取出再写盘，保证 _on_message
            # 在事件循环里只做 O(1) 入队、不阻塞 ws 接收。线程**先建后 start、start 成功才留引用**：
            # 赋值紧跟 .start() 时，一旦 start 抛（实测可达形态 RuntimeError: can't start new
            # thread），_srt_writer 就持有一个永不可 join 的线程对象，stop() 的 join 直接抛错并
            # 跳过末尾的 srt.close()。
            # [历史注] 旧写法正是赋值紧跟 .start()。
            try:
                writer = threading.Thread(
                    target=self._srt_writer_loop, name=f"srt_writer_{self._cls_name}", daemon=True
                )
                writer.start()
                self._srt_writer = writer
            except Exception as e:
                logger.warning(
                    i18n.tr(
                        "[弹幕采集]{cls_name} SRT 写线程启动失败,放弃本次弹幕采集: {type_name}: {e}",
                        cls_name=self._cls_name,
                        type_name=type(e).__name__,
                        e=e,
                    )
                )
                # 此时还没走到 hub.room_started()，故 room_registered=False（不给枢纽投无主事件）
                self._rollback_start(room_registered=False)
                return
        # 上报监控枢纽：房间采集开始（重置该房间统计）
        hub = self._monitor_hub()
        if hub is not None:
            hub.room_started(self._room_name, self._platform_name)
        try:
            worker = threading.Thread(target=self._run, name=f"danmaku_{self._cls_name}", daemon=True)
            worker.start()
            self._thread = worker
        except Exception as e:
            # 采集线程起不来时整条弹幕链路都不存在：回滚并让枢纽看到房间已结束，
            # 否则监控页会留一个「已登记、永不上报」的条目。
            logger.warning(
                i18n.tr(
                    "[弹幕采集]{cls_name} 采集线程启动失败,放弃本次弹幕采集: {type_name}: {e}",
                    cls_name=self._cls_name,
                    type_name=type(e).__name__,
                    e=e,
                )
            )
            self._rollback_start(room_registered=True, close_reason="采集线程启动失败")
            return

    # start() 的回滚出口：「不抛异常」不等于「可以留在半启动状态」——_started 若仍为 True，随后的
    # stop() 会去 join 一个从未成功 start() 的线程并抛 RuntimeError: cannot join thread before it
    # is started；该异常逃出 stop() 就跳过末尾的 self._srt.close()，SrtWriter 句柄泄漏（Windows 上
    # 该 .srt 在 GC 前无法改名，会连带打挂 rename_anchor_directory）。
    # 故这里把 _started 归 False 并摘掉线程引用，让 stop() 走「未启动」早退分支、照常关干净 SRT。
    # room_registered 指明枢纽里是否已登记本房间：已登记才补一条 closed 事件。
    def _rollback_start(self, room_registered: bool, close_reason: str = "") -> None:
        # 先回收**已经起成功**的 SRT 写线程（采集线程启动失败时正是这种形态）：只把 self._srt_writer
        # 置 None 等于丢掉一个活的守护线程及其引用，它会在 get(timeout=_SRT_QUEUE_POLL_SECONDS) 上
        # 空转到进程结束。此刻队列必空、sentinel 基本都能投进；投不进（极窄竞态）就退到 _srt_stop
        # 自检通道——两条都是 _srt_writer_loop 已有的退出契约，不新造机制。
        writer = self._srt_writer
        if writer is not None:
            try:
                self._srt_queue.put_nowait(None)
            except queue.Full:
                self._srt_stop.set()
            self._join_thread(writer, _SRT_WRITER_JOIN_SECONDS)
        self._srt_writer = None
        self._thread = None
        self._started = False
        if room_registered:
            hub = self._monitor_hub()
            # 首投生效：启动失败回滚后随后的 stop() 不再重复投「采集停止」。
            if hub is not None and not self._room_closed_reported:
                hub.room_closed(self._room_name, close_reason)
                self._room_closed_reported = True

    # join 一个「从未成功 start()」的 Thread 会先抛 RuntimeError: cannot join thread before it is
    # started，而本类两处 join 都排在 self._srt.close() 之前——异常一逃就跳过收尾。
    # Thread.ident 只在 start() 成功后被赋值，是「可 join」的跨版本稳定判据；仍包一层 try 是因为
    # stop() 明确承诺不影响录像收尾，任何线程回收竞态都不该让它变成异常源。
    @staticmethod
    def _join_thread(thread: threading.Thread, timeout: float) -> None:
        if thread.ident is None:
            return
        try:
            thread.join(timeout=timeout)
        except RuntimeError as e:
            logger.debug(
                i18n.tr(
                    "[弹幕采集]{where} 异常(忽略): {type_name}: {e}",
                    where="thread.join",
                    type_name=type(e).__name__,
                    e=e,
                )
            )

    # 停止采集：置停止标记、跨线程调度关闭弹幕连接，最多等待 timeout 秒回收线程，最后关闭 SRT 文件。
    # 幂等：重复调用直接返回（录制提前中断与 ffmpeg 正常退出两条路径都可能触发 stop）。
    def stop(self, timeout: float = 8.0) -> None:
        if self._stop_called:
            return
        self._stop_called = True
        # 上报监控枢纽：房间采集结束（连接状态置离线）。首投生效：随后的 _on_close 是重复侧。
        # [2026-10-31 L-11] 加 _started 门：从未 start 过的采集器没有已注册的房间，
        # 上报 closed 会让面板出现一条「从未上线就离线」的无主事件（与本文件上方
        # 「只上报已注册房间」的自述相悖）。
        hub = self._monitor_hub()
        if hub is not None and not self._room_closed_reported and self._started:
            # reason 文案经 i18n——面板非中文语言下混入简中
            hub.room_closed(self._room_name, i18n.tr("采集停止"))
            self._room_closed_reported = True
        if not self._started:
            # 未启动也要尝试关 SRT（空文件）
            if self._srt is not None:
                self._srt.close()
            return
        self._stop_event.set()
        # 反向序握手第 1 半（顺序不可调整）：stop() 先 set(_stop_event)、**再**读 self._loop；对应的
        # 另一半见 _run()（先发布 self._loop、再检查 _stop_event）。两个相反顺序保证信号必被一方接收，
        # 缺任一半都会丢信号。
        loop = self._loop
        if loop is not None:
            # 「未 running 且未 closed」时有界轮询等其 running 再投递；反向序握手不参与此判定。
            # [历史注] 旧实现额外要求 loop.is_running()，「_run 已发布 _loop、尚未进入
            # run_until_complete」（正在构造平台弹幕客户端）这段毫秒级窗口里整段
            # call_soon_threadsafe 被跳过 → 停止信号永久丢失 → join 超时，采集线程 + SrtWriter
            # 句柄 + 监控房间条目（room_stopped 只在线程退出才发）全部滞留。
            deadline = time.monotonic() + _LOOP_RUNNING_WAIT_SECONDS
            while not loop.is_running() and not loop.is_closed():
                if time.monotonic() >= deadline:
                    break
                time.sleep(_LOOP_RUNNING_POLL_INTERVAL)
            if loop.is_running():
                try:
                    loop.call_soon_threadsafe(self._schedule_stop)
                except Exception as e:
                    # 投递失败（循环恰在此刻被关闭等）：不重抛——采集线程侧的二次复查与
                    # 下面的 join 超时是兜底，抛出去会让承诺「不影响录像」的 stop() 变成异常源。
                    logger.debug(
                        i18n.tr(
                            "[弹幕采集]{where} 异常(忽略): {type_name}: {e}",
                            where="call_soon_threadsafe",
                            type_name=type(e).__name__,
                            e=e,
                        )
                    )
        if self._thread is not None:
            self._join_thread(self._thread, timeout)
            # join 带 timeout 时超时是静默返回，必须复查存活：否则卡死的采集线程（连同它的事件
            # 循环、平台 WS 连接与监控枢纽里的房间条目）无人知晓，用户侧只有「弹幕不再更新」、
            # 日志里一条线索都没有。与 SRT 写线程侧的 is_alive 判据同构。
            # 判定必须放在 _join_thread 之后、srt.close() 之前：本方法不改写 _srt.close() 的调用
            # 顺序（sentinel 失败也必须走到 close，否则录制并发槽永久泄漏，由
            # tests/test_collector.py::test_monitor_hub_and_writer_thread_survive_full_queue 钉住）。
            if self._thread.is_alive():
                detail = f"{self._cls_name} capture thread still alive after join(timeout={timeout}s)"
                logger.warning(
                    i18n.tr(
                        "停止流程收尾异常: {type_name}: {err}",
                        type_name="ThreadStillAlive",
                        err=utils.mask_credentials(detail),
                    )
                )
        # SRT 写线程收尾：sentinel 通知消费者排空队列后退出，join 超时降级为「未排空也关文件」，
        # 避免 srt.close() 之前还有未刷盘的弹幕丢失（保留 flush-on-close 的兜底）。
        if self._srt_writer is not None and self._srt is not None:
            # 必须非阻塞投递 sentinel：队列有界，而写线程可能正卡在 srt.write() 的阻塞 flush() 上
            # （网络盘掉线 / USB 拔除 / 磁盘满），队列满 + 消费者永不再取 ⇒ 阻塞 put 永不返回，stop()
            # 挂死在录制线程里；main.py 的两条 try 内调用路径此时还在 finally: _rec_sem.release() 之前，
            # 于是**永久泄漏一个录制并发槽**，累积到上限后所有后续录制饿死（SrtWriter.close() 早已为
            # 同一场景设 _CLOSE_LOCK_TIMEOUT）。
            # 故：投不进就置 _srt_stop 让写线程自检退出；只 join 有限时间；sentinel 失败绝不阻断
            # 后面的 srt.close()。
            # [历史注] 旧实现用阻塞 put(None)，正是上述形态。
            reason: Optional[str] = None
            try:
                self._srt_queue.put_nowait(None)
            except queue.Full:
                self._srt_stop.set()
                reason = _SRT_SHUTDOWN_QUEUE_FULL
            self._join_thread(self._srt_writer, _SRT_WRITER_JOIN_SECONDS)
            if reason is None and self._srt_writer.is_alive():
                reason = _SRT_SHUTDOWN_JOIN_TIMEOUT
            if reason is not None:
                logger.warning(
                    i18n.tr(
                        "[弹幕采集]SRT 写线程收尾未完成（{reason}），尾部弹幕可能未落盘",
                        reason=reason,
                    )
                )
        if self._srt is not None:
            self._srt.close()

    # 在采集线程的 loop 中执行：投递一个关闭协程用于停止弹幕客户端并停掉 loop，无返回值。
    def _schedule_stop(self) -> None:
        # 内部协程：先 await 弹幕客户端 stop()（异常记日志），再取消 danmaku.start() 任务、
        # 让取消传播，最后停止事件循环。
        async def _shutdown() -> None:
            if self._danmaku is not None:
                try:
                    # 限时（超时值与理由见 _SHUTDOWN_TIMEOUT_SECONDS）；
                    # asyncio.TimeoutError 在 3.11+ 即内置 TimeoutError，故只捕后者。
                    await asyncio.wait_for(self._danmaku.stop(), timeout=_SHUTDOWN_TIMEOUT_SECONDS)
                except TimeoutError:
                    logger.warning(
                        i18n.tr("[弹幕采集]{cls_name} stop() 超时,强制停止事件循环", cls_name=self._cls_name)
                    )
                except Exception as e:
                    # 弹幕客户端关闭失败不影响收尾：下方仍要取消 start() 任务并停 loop，
                    # 否则采集线程永不退出（重抛等于把「停止录制」变成线程级异常源）。
                    logger.debug(
                        i18n.tr(
                            "[弹幕采集]{where} 异常(忽略): {type_name}: {e}",
                            where="danmaku.stop",
                            type_name=type(e).__name__,
                            # 平台 WS 关闭异常的文本同样带连接 URL 与鉴权参数，与 base.py 的
                            # _log_task_exception 同口径。
                            e=utils.mask_credentials(str(e)),
                        )
                    )
            # 不能直接 loop.stop()：danmaku.start() 的任务此刻多半仍 pending，run_until_complete
            # 被掐断后 loop.close() 触发 Task.__del__，向 stderr 刷「Task was destroyed but it is
            # pending」（多房间同时停止录制时集中刷屏），且平台 start() 里 finally 的清理链
            # （连接副作用、buvid/看门狗等）永不执行。故先取消任务、让出一轮把取消送达，再停 loop。
            task = self._start_task
            if task is not None and not task.done():
                task.cancel()
                # 让出一个调度轮：cancel() 只是投递 CancelledError，必须回到事件循环
                # 才会真正送达并跑完 finally 链。
                await asyncio.sleep(0)
            if self._loop is not None:
                self._loop.stop()

        if self._loop is not None:
            # 与 base.spawn_danmaku_task 同源：裸 ensure_future 的关闭协程异常只会在被 GC 时打一行
            # stderr。持引用 + 完成回调落盘异常；本任务通常随 loop.stop() 结束，不会被丢弃。
            self._shutdown_task = spawn_danmaku_task(_shutdown())

    # 采集线程主体：新建并绑定事件循环，实例化平台弹幕类（注入三个回调、透传 only_fans），
    # 阻塞运行 danmaku.start() 直到连接结束或被停止；退出前关闭 loop，无返回值。
    def _run(self) -> None:
        # DEBUG 状态噪音,已按要求注释:
        # logger.debug(f"[弹幕采集]{self._danmaku_cls.__name__} 采集线程已启动")
        loop = asyncio.new_event_loop()
        self._loop = loop
        asyncio.set_event_loop(loop)
        # 与 stop() 的握手：stop() 先 set(_stop_event) 再读 self._loop，而本线程先发布 self._loop
        # 再检查 _stop_event——两个相反的顺序保证信号必被一方接收。若此处已置位（stop() 在采集线程
        # 建好 loop 之前就到达），直接退出不再拉起连接，否则 _loop 仍为 None 时 stop() 的
        # call_soon_threadsafe 会被整段跳过，信号永久丢失。
        if self._stop_event.is_set():
            logger.debug(
                i18n.tr(
                    "[弹幕采集]{cls_name} 启动前已收到停止信号,跳过连接",
                    cls_name=self._cls_name,
                )
            )
            try:
                loop.close()
            except Exception:
                # 吞没即正确：该 loop 从未运行过，close() 失败（极少数平台/权限形态）也已无
                # 可恢复动作；此处抛错会让采集线程带异常退出，反而丢掉下方的退出统计日志。
                pass
            self._loop = None
            return
        try:
            danmaku = self._danmaku_cls(
                on_message=self._on_message,
                on_close=self._on_close,
                on_ready=self._on_ready,
            )
            # 透传 only_fans（斗鱼等支持的平台）。仅在调用方显式指定时才覆盖，否则保留平台类
            # 自己的默认值（斗鱼为 False = 不过滤普通弹幕，见上文）。
            if self._only_fans is not None and hasattr(danmaku, "_only_fans"):
                cast(Any, danmaku)._only_fans = self._only_fans
            self._danmaku = danmaku
            # 二次复查（不破坏反向序握手）：stop() 的「有界等待 is_running」与本行是同一窗口的两半。
            # 本行保证「置位后绝不进入 run_until_complete」，于是该窗口要么由轮询投递、要么在这里
            # 直接跳过建连——两条路径都收敛，不存在丢信号的第三种交错。
            if self._stop_event.is_set():
                logger.debug(
                    i18n.tr(
                        "[弹幕采集]{cls_name} 启动前已收到停止信号,跳过连接",
                        cls_name=self._cls_name,
                    )
                )
                return
            # 显式建任务而非把协程交给 run_until_complete —— _shutdown 需要拿到这个任务的引用
            # 来 cancel()（见 _schedule_stop）。
            self._start_task = loop.create_task(danmaku.start(self._danmaku_args))
            try:
                # start() 内部会阻塞直到连接关闭或 stop() 被调用（stop 经 call_soon_threadsafe 关闭 ws）
                loop.run_until_complete(self._start_task)
            except asyncio.CancelledError:
                # 吞没即正确：任务被 _shutdown 取消正是「正常停止」的形态，
                # 重抛会把停止动作误报成采集失败。
                pass
            except RuntimeError as e:
                # 按任务是否真被取消区分，不能把 RuntimeError 一并吞掉：平台 danmaku.start() 内部
                # 冒出的真 RuntimeError（参数错误、回调抛错等）会被静默归为「正常停止」。被取消
                # （_shutdown 路径）吞掉；非取消态的补 warning 留线索。
                if self._start_task is not None and self._start_task.cancelled():
                    pass
                else:
                    # {e} 位一律传脱敏后的字符串（异常对象由 loguru 就地 str()，平台 SDK 的异常文本
                    # 常内嵌带 token 的 ws/流地址）。msgid 不变。
                    logger.warning(
                        i18n.tr(
                            "[弹幕采集]{cls_name} 运行异常,不影响录制: {e}",
                            cls_name=self._cls_name,
                            e=utils.mask_credentials(str(e)),
                        )
                    )
            except Exception as e:
                # 同上：msgid 保持不变。
                logger.warning(
                    i18n.tr(
                        "[弹幕采集]{cls_name} 运行异常,不影响录制: {e}",
                        cls_name=self._cls_name,
                        e=utils.mask_credentials(str(e)),
                    )
                )
        except Exception as e:
            # 平台类**构造期**与回调注入（下方 only_fans 透传）此前裸奔在
            # finally 之外——只有 danmaku.start() 那一段受保护，构造一抛就逃出守护线程：
            # 线程带 traceback 消失（无控制台进程里连 traceback 都没有），而监控枢纽条目仍停在
            # started、面板显示「采集中」直到录制结束。这里补外层 except：记脱敏异常 + 主动把
            # 房间上报为已关闭，收尾仍交给原有 finally（loop.close() 与 _loop 置空的位置不动）。
            # 重复 closed 事件会让面板计数虚增：stop() 入口与 _on_close 也会上报，全路径统一由
            # _room_closed_reported 首投生效标记去重，此处补报只发生在「线程自己出错」这条路径。
            logger.warning(
                i18n.tr(
                    "[弹幕采集]{cls_name} 运行异常,不影响录制: {e}",
                    cls_name=self._cls_name,
                    e=utils.mask_credentials(f"{type(e).__name__}: {e}"),
                )
            )
            if not self._room_closed_reported:
                hub = self._monitor_hub()
                if hub is not None:
                    hub.room_closed(self._room_name, i18n.tr("采集停止"))
                    self._room_closed_reported = True
        finally:
            logger.debug(
                i18n.tr(
                    "[弹幕采集]{cls_name} 采集线程已退出,共收到 {msg_count} 条消息",
                    cls_name=self._cls_name,
                    msg_count=self._msg_count,
                )
            )
            # 兜底：_shutdown 的 wait_for 超时分支会在取消 start() 任务前就走到 loop.stop()；
            # 此时任务仍 pending，直接 loop.close() 就会由 Task.__del__ 刷「Task was destroyed but it is
            # pending」且平台 finally 链不执行。故关循环前用**有界**的排水循环把取消送达（上限 0.5s，
            # 异常一律吞）。
            pending = self._start_task
            if pending is not None and not pending.done():
                pending.cancel()
                drain_deadline = time.monotonic() + _LOOP_RUNNING_WAIT_SECONDS
                try:
                    while not pending.done() and time.monotonic() < drain_deadline:
                        loop.run_until_complete(asyncio.sleep(0.01))
                except Exception:
                    # 吞没即正确：收尾阶段的取消失败已无可恢复动作，继续关循环即可
                    pass
            try:
                loop.close()
            except Exception:
                # 吞没即正确：loop 可能已被 _shutdown 路径关闭；重复关闭抛错不影响线程退出
                pass
            self._loop = None
            self._start_task = None

    # SRT 写盘线程主体：阻塞从 self._srt_queue 取 (user, msg, now) 并调 srt.write；收到 sentinel
    # (None) 后退出循环。now 来自事件循环侧（采集时刻），保证时间轴不被写线程调度延迟影响。
    # srt.write 失败（磁盘满/文件被删）仅记 warning 不退出，与「弹幕失败不影响录制」契约一致。
    def _srt_writer_loop(self) -> None:
        srt = self._srt
        if srt is None:
            return
        # WD-03：失败告警按时间窗聚合。原实现每条弹幕一条 warning，磁盘满/文件被删时
        # 高热度房间会刷屏并进一步放大 IO 压力，反而掩盖问题。
        _last_warn_at = 0.0
        _fail_since_warn = 0
        while True:
            # get() 改为带超时的有限等待，并在队列为空时检查 _srt_stop。
            # sentinel 仍是主退出通道（保证「先清空队列再关文件」的顺序不变）；_srt_stop 只在
            # sentinel 因队列满投不进来时生效，且**只在队列已空时**检查——队列里还有弹幕就继续
            # 消费，不多丢一条。
            try:
                item = self._srt_queue.get(timeout=_SRT_QUEUE_POLL_SECONDS)
            except queue.Empty:
                if self._srt_stop.is_set():
                    return
                continue
            if item is None:
                return

            user_name, message, now = item
            try:
                srt.write(user_name, message, now=now)
            except Exception as e:
                _fail_since_warn += 1
                _now = time.monotonic()
                if _now - _last_warn_at >= _SRT_WARN_INTERVAL:
                    logger.warning(
                        i18n.tr(
                            "[弹幕采集]SRT 写入失败(继续采集): {type_name}: {e}（本窗口累计失败 {count} 条）",
                            type_name=type(e).__name__,
                            e=e,
                            count=_fail_since_warn,
                        )
                    )
                    _last_warn_at = _now
                    _fail_since_warn = 0

    # 收到弹幕回调：全部类型转发监控枢纽；SRT 仅记录 CHAT 且用户名或内容非空的消息。
    def _on_message(self, msg: DanmakuMessage) -> None:
        # 入队/上报前统一截断（口径见 _DANMAKU_TEXT_LIMIT 注释）；SRT 与监控流共用。
        user_name = msg.user_name[:_DANMAKU_TEXT_LIMIT]
        message = msg.message[:_DANMAKU_TEXT_LIMIT]
        # 监控侧不过滤消息类型（聊天/礼物/在线人数/SC 全部上报，由枢纽分别处理）
        hub = self._monitor_hub()
        if hub is not None:
            # WD-20 修复：在线人数由各平台放在 msg.data（B站/虎牙的 ONLINE 消息 message 为空串），
            # 原实现只透传 message，导致枢纽侧 _parse_online("") 恒返回 0——「在线人数」列永远显示
            # 0 且无任何日志线索。这里把 data 一并透传。
            hub.room_message(self._room_name, msg.type.value, user_name, message, data=msg.data)
        if msg.type != DanmakuMessageType.CHAT:
            return  # SRT 当前只录普通弹幕
        if not user_name and not message:
            return
        self._msg_count += 1
        # DEBUG 状态噪音(每条弹幕都给一条),已按要求注释:
        # if self._msg_count == 1:
        #     logger.debug(f"[弹幕采集]{self._danmaku_cls.__name__} 收到第一条弹幕: {msg.user_name}: {msg.message}")
        now = time.monotonic()
        # 仅监控模式无 SrtWriter、无写线程，_srt_queue 也不消费——写线程只在 _srt is not None 时
        # 启动，故入队条件必须与之一致。
        if self._srt is not None:
            # WD-02：非阻塞入队。队列满说明写盘已明显落后于接收速率（慢盘/磁盘满），此时丢弃最新的
            # 弹幕并计数——保持内存有界，且丢弃量在下一批告警里可观测。用 put_nowait 而非 put：
            # 本函数跑在事件循环线程上，阻塞入队会卡住 ws_recv。
            try:
                self._srt_queue.put_nowait((user_name, message, now))
            except queue.Full:
                self._srt_dropped += 1
                if self._srt_dropped == 1 or self._srt_dropped % 1000 == 0:
                    logger.warning(
                        i18n.tr(
                            "[弹幕采集]SRT 写入队列已满，正在丢弃弹幕（累计 {count} 条）——请检查磁盘空间与写入性能",
                            count=self._srt_dropped,
                        )
                    )

    # 连接就绪/关闭回调：上报监控枢纽并记一条 debug 日志。
    def _on_ready(self) -> None:
        hub = self._monitor_hub()
        if hub is not None:
            hub.room_connected(self._room_name)
        logger.debug(
            i18n.tr(
                "[弹幕采集]{cls_name} 连接就绪,开始接收弹幕",
                cls_name=self._cls_name,
            )
        )

    # 连接关闭回调：上报监控枢纽，并把关闭原因记入 debug 日志。
    def _on_close(self, reason: str) -> None:
        # 最后一道闸：上游 src/ws_client.py 已约定「交给回调的文案必须已脱敏」，
        # 但 on_close 是全平台弹幕客户端的公共出口（B栈的 start()/spider 侧、Twitch 的 SDK 异常分支
        # 都直接调它），只要一处把裸 str(e) 传进来，代理凭据就会同时落进 logs/（轮转保留多份 = 长期
        # 落盘）和监控枢纽 → Web/GUI 面板。这里再兜一道，mask_credentials 对已脱敏文案幂等。
        reason = utils.mask_credentials(reason)
        hub = self._monitor_hub()
        # 首投生效：意外掉线时本回调先于 stop() 触发，真实关闭原因由这里带上；
        # 主动停止时 stop() 已先投「采集停止」，本回调即重复侧，不再补第二条 closed 事件。
        if hub is not None and not self._room_closed_reported:
            hub.room_closed(self._room_name, reason)
            self._room_closed_reported = True
        logger.debug(
            i18n.tr(
                "[弹幕采集]{cls_name} 连接关闭: {reason}",
                cls_name=self._cls_name,
                reason=reason,
            )
        )

    # 只读属性：本次采集已写入的弹幕条数。
    @property
    def message_count(self) -> int:
        return self._msg_count
