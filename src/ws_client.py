# 异步 WebSocket 客户端封装（对标 dart simple_live_core 的 WebScoketUtils）。
#
# 提供心跳定时与断线重连（最多 max_reconnect 次，间隔 reconnect_interval 秒，指数退避 + 抖动）。
# 所有平台弹幕共用此客户端。
#
# 约定：**交给 on_close / on_reconnect 回调的文案必须已脱敏**。这两条回调是把
# 异常文本送出去的唯一出口，消费端（src/collector.py 的 _on_close）会把 reason 原样写进
# loguru 文件 sink（logs/ 按 300KB 轮转保留多份 = 长期落盘）与弹幕监控枢纽（进而显示到
# Web/GUI 面板）。websockets 的 InvalidProxy 文本自带代理原串（含 user:pass@host），故所有
# 出口一律先过 utils.mask_credentials；新增回调参数同样适用，不得把裸 str(e) 传出去。

from __future__ import annotations

import asyncio
import inspect
import random
import ssl
import time
from typing import Awaitable, Callable, Optional, Union, cast

import websockets

import i18n

from . import utils
from .base import spawn_danmaku_task
from .logger import logger

# 单次连接内"毒消息"（处理抛异常的帧）的最大逐条记日志条数：
# 超出后只记一次汇总，避免同型异常把日志刷满、掩盖其它真实问题。
_POISON_LOG_LIMIT = 5

# send_nowait 在途任务堆积上限。心跳/进房/ack 均为秒级小帧，正常在途 < 5；
# 上限只在 _send_lock 被 WD-04 的 5s 超时长期占住时触顶——触顶即丢弃并告警，而不是让
# 任务数随断连时长无界增长（旧实现裸 ensure_future，既无引用也无上限）。
_MAX_PENDING_SENDS = 64

# WD-04：协议层 ping 参数。各平台自带应用级心跳（只发不收），无法感知 TCP 半开；
# 依赖库的 ping/pong 才能在断网、NAT 老化、对端静默时主动断开并触发重连。
# 间隔取 20s（远小于各平台心跳周期），超时 20s——两次未收到 pong 即判定连接已死。
_PING_INTERVAL = 20.0
_PING_TIMEOUT = 20.0
# WD-04 修复：单帧大小上限。各平台弹幕帧实测在 KB 量级，8MiB 已是极宽松的上界，
# 用于替代原 max_size=None（配合帧内 gzip/zlib/brotli 解压构成内存放大面）。
_MAX_FRAME_BYTES = 8 * 1024 * 1024
# WD-04：send() 单次发送超时（秒）。半开连接上 send 会一直缓冲而不报错，
# 无超时会让 _send_lock 永久不释放，此后每次心跳都堆积一个等待任务。
_SEND_TIMEOUT = 5.0

# 重连退避倍数的上限：base * 2^(n-1) 封顶于此倍数。
_BACKOFF_MAX_MULTIPLIER = 16

# 判定「这条连接已真健康到可把重连计数归零」所需的最短存活秒数 = 2 × reconnect_interval。
# 一次「握手成功即被服务端关掉」的抖动存活时长远小于一个重连周期，若连这个长度都没活过就归零，
# max_reconnect 永不耗尽；取 2 倍是给「连上后正常收了几秒弹幕再断」留余量。
_HEALTHY_CONNECTION_FACTOR = 2
# 同上的下限（秒）：reconnect_interval 被压得很小（测试/激进配置）时，若健康窗口也跟着缩到
# 毫秒级，任何一次慢断开都会白白归零计数，等于回到「连上即重置」的老问题。
_MIN_HEALTHY_CONNECTION_SECONDS = 1.0


# 重连退避时长：base * 2^(n-1) 封顶 16 倍，并叠加 0~30% 随机抖动。
# 固定间隔会让多个房间在平台抖动时同一秒齐刷刷重连（thundering herd），
# 放大被风控概率；抖动把重连时刻打散。
def _backoff_delay(base: float, attempt: int) -> float:
    multiplier: int = min(2 ** max(attempt - 1, 0), _BACKOFF_MAX_MULTIPLIER)
    jitter: float = 1.0 + random.random() * 0.3
    return float(base * multiplier * jitter)


# 弹幕帧解压后的输出上限（字节）：8MiB 与 _MAX_FRAME_BYTES 同量级。
_MAX_DECOMPRESSED_BYTES = 8 * 1024 * 1024


# 带输出上限的 gzip/deflate 解压（MI-01）：裸 gzip.decompress 对高压缩比输入（可达 1000:1）会把
# 几百 KB 的帧展开成 GB 级对象，服务端异常或链路被篡改时可打爆本进程（同进程还跑着录制主流程）。
# 此处用 decompressobj 分块解压并在超限时抛错，把内存放大面收敛为可捕获异常。
def decompress_limited(data: bytes, limit: int = _MAX_DECOMPRESSED_BYTES, wbits: int = 31) -> bytes:
    import zlib

    obj = zlib.decompressobj(wbits)
    out = obj.decompress(data, limit + 1)
    if len(out) > limit:
        raise ValueError(f"decompressed payload exceeds limit ({limit} bytes)")
    # 处理流尾残留（未超限时正常返回）
    tail = obj.flush()
    if len(out) + len(tail) > limit:
        raise ValueError(f"decompressed payload exceeds limit ({limit} bytes)")
    return out + tail


# 带输出上限的 brotli 解压（MI-01）：brotli 的 Python 绑定没有 max_output_size 参数，
# 故改用 Decompressor 分块喂入并在累计输出超限时抛错。注意这只是**事后检测**：单块输出会
# 先物化再检查，消费侧最多少付一块的瞬时内存，不与 decompress_limited（zlib 在 C 层硬截断）
# 的真上限同强度；根治需换支持输出上限的绑定，超出本层职责。
def decompress_brotli_limited(data: bytes, limit: int = _MAX_DECOMPRESSED_BYTES, chunk: int = 4096) -> bytes:
    import brotli

    obj = brotli.Decompressor()
    out = bytearray()
    for i in range(0, len(data), chunk):
        out += obj.process(data[i : i + chunk])
        if len(out) > limit:
            raise ValueError(f"decompressed payload exceeds limit ({limit} bytes)")
    if not obj.is_finished():
        raise ValueError("brotli stream is incomplete")
    return bytes(out)


# 根据 url 生成默认 SSL 上下文：wss:// 返回放宽到 @SECLEVEL=1 的 SSLContext，ws:// 返回 None。
def _default_ssl_context(url: str) -> Optional[ssl.SSLContext]:
    # 某些直播平台的弹幕服务（如斗鱼 danmuproxy:8506）用旧 RSA 密钥交换套件，
    # OpenSSL 3.x 在默认 SECLEVEL 之上会拒绝握手，故 wss 降级兼容。
    if not url.startswith("wss://"):
        return None
    ctx = ssl.create_default_context()
    try:
        ctx.set_ciphers("DEFAULT:@SECLEVEL=1")
    except ssl.SSLError:
        pass  # 某些构建不支持该字符串，退回默认
    return ctx


# 判断连接是否仍可用于发送（该第二道防线）：websockets 的协议对象带 `state`，
# 连接关闭后即便引用未清空也不会是 OPEN。桩对象/旧版本没有 state 时返回 True（乐观放行），
# 保持既有打桩用例的行为不变。形参用 object 注解：本函数只经 getattr 取 state，而
# `websockets.WebSocketClientProtocol` 在不同版本下是否导出并不一致。
def _conn_is_open(ws: object) -> bool:
    state = getattr(ws, "state", None)
    if state is None:
        return True
    return str(getattr(state, "name", state)).upper() == "OPEN"


# 各平台弹幕共用的异步 WebSocket 客户端：负责连接、收包分发、定时心跳、断线重连与主动关闭。
class WsClient:
    # 初始化客户端：url/backup_url 为主备地址，各 on_* 为回调，heartbeat_interval /
    # max_reconnect / reconnect_interval / connect_timeout 控制心跳与重连策略，
    # headers/proxy/ssl_context 为连接参数（ssl_context 未传时按 url 自动生成）；不发起连接。
    def __init__(
        self,
        url: str,
        on_message: Callable[[Union[bytes, str]], None],
        on_ready: Optional[Callable[[], None]] = None,
        on_heartbeat: Optional[Callable[[], Union[None, Awaitable[None]]]] = None,
        on_close: Optional[Callable[[str], None]] = None,
        on_reconnect: Optional[Callable[[str], None]] = None,
        heartbeat_interval: float = 45.0,
        headers: Optional[dict] = None,
        backup_url: Optional[str] = None,
        max_reconnect: int = 5,
        reconnect_interval: float = 5.0,
        connect_timeout: float = 10.0,
        ssl_context: Optional[ssl.SSLContext] = None,
        proxy: Optional[str] = None,
    ) -> None:
        self._url = url
        self._backup_url = backup_url
        self._on_message = on_message
        self._on_ready = on_ready
        self._on_heartbeat = on_heartbeat
        self._on_close = on_close
        self._on_reconnect = on_reconnect
        self.heartbeat_interval = heartbeat_interval
        self._headers = headers
        self.max_reconnect = max_reconnect
        self.reconnect_interval = reconnect_interval
        self.connect_timeout = connect_timeout
        # 代理：默认 None = 直连，**不得改成跟随系统代理**（AGENTS「弹幕 WS 连接必须显式
        # proxy=None」是已记录的回归坑）——跟随系统代理后 B站/斗鱼会报
        # `connecting through a SOCKS proxy requires python-socks` 且连接即断。
        # 只有 Twitch 等海外平台在调用点显式传入自己的代理。
        self._proxy = proxy
        # 默认 wss 用宽松 SECLEVEL=1 context；可被 ssl_context 覆盖
        self._ssl_context = ssl_context if ssl_context is not None else _default_ssl_context(url)

        self._ws: Optional["websockets.WebSocketClientProtocol"] = None  # type: ignore[name-defined]
        self._stopped = False
        self._reconnect_count = 0
        # 连接存活多久才算「健康」、可重置重连计数（见 _HEALTHY_CONNECTION_FACTOR）
        self._healthy_lifetime_seconds = max(
            _MIN_HEALTHY_CONNECTION_SECONDS, reconnect_interval * _HEALTHY_CONNECTION_FACTOR
        )
        # on_close 是「房间已结束」的配对信号（collector 侧发 hub.room_closed），
        # 一个客户端生命周期内只该发一次；fail() 与 connect() 的耗尽分支可能先后触达，
        # 用该标记保证不会把同一房间的关闭事件重复投给监控枢纽。
        self._close_reported = False
        self._send_lock = asyncio.Lock()
        # send_nowait 派出的后台发送任务需持强引用（asyncio 只弱引用任务），
        # 否则「入队即被 GC」属文档化的丢失风险；done_callback 里回收，集合有界。
        self._pending: "set[asyncio.Task[None]]" = set()

    # 主协程：连接（重连时改用备用地址）→ 触发 on_ready 并起心跳任务 → 逐帧回调 on_message；
    # 异常或正常断开时按 max_reconnect / reconnect_interval 重连，耗尽则回调 on_close 后返回。
    async def connect(self) -> None:
        while not self._stopped:
            url = self._url
            # 重连时切换备用地址（如有）
            if self._reconnect_count > 0 and self._backup_url:
                url = self._backup_url
            # 本次连接内的「毒消息」计数（每次成功建连重置：换地址/重连后重新计数，
            # 避免一次历史风暴永久压制后续真实告警的日志可见性）
            _poison_count = 0
            # 本轮连接的「健康度」观测点——握手成功的时刻 / 是否收到过应用层帧，
            # 两者共同决定退出本轮时要不要把 _reconnect_count 归零（见 _reset_count_if_healthy）。
            _connected_at: Optional[float] = None
            _got_frame = False
            try:
                async with websockets.connect(
                    url,
                    additional_headers=self._headers,
                    open_timeout=self.connect_timeout,
                    # WD-04：原为 ping_interval=None（完全关闭协议层 ping）。各平台的应用级心跳
                    # 只做**发送**，感知不到 TCP 半开（断网 / NAT 老化 / 对端静默）——连接被判为
                    # 「正常」、永不进重连，表现为断网恢复后弹幕永久 0 条而监控仍显示「已连接」。
                    # 协议层 ping/pong 才能主动断开并触发重连（取值理由见 _PING_INTERVAL）。
                    ping_interval=_PING_INTERVAL,
                    ping_timeout=_PING_TIMEOUT,
                    # WD-04/E-07：原为 None（取消 1MiB 默认帧限制），单帧可任意大，帧内还有
                    # gzip/zlib/brotli 无上限解压，构成内存放大面。设合理上限。
                    max_size=_MAX_FRAME_BYTES,
                    ssl=self._ssl_context,
                    proxy=self._proxy,  # None=直连(B站/虎牙等);Twitch 等海外平台可传显式代理
                ) as ws:
                    self._ws = ws
                    # 握手成功不等于会话健康——房间结束、被踢、鉴权软拒绝、uid 用错
                    # 的 1006 硬断连都属「连上即断」，若连上就归零，则每轮从 1 加起、下一轮又
                    # 归零：max_reconnect 永不耗尽，文件头声明的「耗尽则回调 on_close」契约失效
                    # （监控页以为还在连），且每轮握手 + 进房包构成对平台的持续连击。
                    # 故只记录时刻，由 _reset_count_if_healthy 在两条重连出口处判定是否真健康。
                    _connected_at = time.monotonic()
                    if self._on_ready:
                        self._on_ready()
                    hb_task = asyncio.create_task(self._heartbeat_loop())
                    try:
                        async for data in ws:
                            if self._stopped:
                                break
                            # 收到首个应用层帧 = 这条连接确实推过数据，算健康
                            _got_frame = True
                            # 单条「毒消息」隔离：若让 _on_message 的异常冒泡到外层 except，将触发
                            # 整条连接重建；而恒定解析失败的帧（平台协议变体、畸形帧）在重连后会被
                            # 服务端重放——无限重连风暴（max_reconnect 快速耗尽、日志被刷满）。
                            # 故只丢该帧并记日志、连接保持，与各平台 decode_message 内部的 debug 兜底
                            # 构成两级防御。
                            try:
                                self._on_message(data)
                            except Exception as e:
                                _poison_count += 1
                                if _poison_count <= _POISON_LOG_LIMIT:
                                    logger.warning(
                                        i18n.tr(
                                            "弹幕消息处理异常（已丢弃该帧，连接保持）: {type_name}: {e}",
                                            type_name=type(e).__name__,
                                            e=e,
                                        )
                                    )
                                elif _poison_count == _POISON_LOG_LIMIT + 1:
                                    # 超限后降级为不再逐条记，避免日志被同型异常刷满
                                    logger.warning(
                                        i18n.tr(
                                            "弹幕消息处理异常持续出现，后续同类异常不再逐条记录（累计 {count} 条）",
                                            count=_poison_count,
                                        )
                                    )
                                continue
                    finally:
                        hb_task.cancel()
                        try:
                            await hb_task
                        except asyncio.CancelledError:
                            # hb_task 按预期被取消（回收心跳任务）属正常路径，吞掉即可；若系本协程
                            # 自身被取消（hb_task 并未处于 cancelled 态），不得吞掉取消信号，原样上抛
                            # 交由外层统一退出。
                            if not hb_task.cancelled():
                                raise
                        except Exception:
                            # 吞没即正确：这里是「回收心跳任务」的收尾，回收失败不应掩盖真正的
                            # 连接异常（CancelledError 非继承 Exception，已在上面显式放行）
                            pass
            except asyncio.CancelledError:
                # 三条出口都要在这里摘引用，且必须**在退避 sleep 之前**。把清理挂在
                # 外层 finally 不行——finally 要等 except 子句整个执行完才跑，而退避 sleep 就在
                # except 里，悬挂窗口原样存在。窗口内 `self._ws` 仍指向上一条**已关闭**连接，
                # 而 send()/send_nowait() 只判 `is None`，进房包与心跳全打在死连接上、异常被
                # 吞成一条 debug，表现为「重连成功却再也不推弹幕」且无任何线索。回归锁：
                # tests/test_ws_client.py::test_ws_reference_cleared_before_reconnect_backoff
                # （观察点放在 on_reconnect，恰在 sleep 之前）。关闭动作由 `async with` 负责。
                self._ws = None
                break
            except Exception as e:
                self._ws = None
                if self._stopped:
                    break
                # 异常文本可能自带代理原串（websockets 的 InvalidProxy 形如
                # "http://user:pass@127.0.0.1:10808 isn't a valid proxy: ..."），而 reason 会被
                # collector 原样写进轮转日志与监控枢纽 → 交出前先脱敏（约定见文件头）。
                _reason = utils.mask_credentials(str(e))
                self._reset_count_if_healthy(_connected_at, _got_frame)
                self._reconnect_count += 1
                if self._reconnect_count <= self.max_reconnect:
                    if self._on_reconnect:
                        self._on_reconnect(_reason)
                    # WD-05：指数退避 + 抖动（原为固定 reconnect_interval）
                    await asyncio.sleep(_backoff_delay(self.reconnect_interval, self._reconnect_count))
                    continue
                # 重连耗尽
                self._report_close(i18n.tr("重连超过最大次数，与服务器断开连接: {reason}", reason=_reason))
                break
            else:
                # 正常关闭（onDone）但未 stop，尝试重连
                self._ws = None
                if self._stopped:
                    break
                self._reset_count_if_healthy(_connected_at, _got_frame)
                self._reconnect_count += 1
                if self._reconnect_count <= self.max_reconnect:
                    if self._on_reconnect:
                        # reason 文案经 i18n——面板非中文语言下不得混入简中
                        self._on_reconnect(i18n.tr("连接已关闭，正在尝试重连"))
                    # WD-05：同上，指数退避 + 抖动
                    await asyncio.sleep(_backoff_delay(self.reconnect_interval, self._reconnect_count))
                    continue
                self._report_close(i18n.tr("重连超过最大次数，与服务器断开连接"))
                break

    # 本轮连接若「已证明健康」则把重连计数归零（在 ++ 之前调用，故归零后本轮计 1）。
    # 判据二选一：① 本轮收到过至少一个应用层帧；② 从握手成功算起存活时长 >
    # _healthy_lifetime_seconds。都不成立即视为「握手成功即被断开」，计数继续累计直到
    # max_reconnect 耗尽、由 _report_close 上报 on_close。connected_at 为 None 表示本轮
    # 根本没连上（纯连接失败），同样不重置——旧实现把「连上」当「健康」，才让该出口永不可达。
    def _reset_count_if_healthy(self, connected_at: Optional[float], got_frame: bool) -> None:
        if got_frame:
            self._reconnect_count = 0
            return
        if connected_at is not None and (time.monotonic() - connected_at) > self._healthy_lifetime_seconds:
            self._reconnect_count = 0

    # on_close 的唯一出口（一个客户端生命周期内只发一次）：connect() 的耗尽分支
    # 与 fail() 可能先后触达，而消费端（collector._on_close → hub.room_closed）把它当作「房间
    # 已结束」的配对信号，重复投递会让监控枢纽多出一条无主的 closed 事件。
    # reason 在此再过一道掩码，与文件头约定一致。
    def _report_close(self, reason: str) -> None:
        if self._close_reported:
            return
        self._close_reported = True
        if self._on_close:
            self._on_close(utils.mask_credentials(reason))

    # 异步发送一帧数据 data（bytes 或 str）：未连接/连接已关闭则直接返回，发送加锁串行化，
    # 异常记日志后忽略，无返回值。
    async def send(self, data: Union[bytes, str]) -> None:
        ws = self._ws
        if ws is None:
            return
        # 第二道防线：`_ws` 非 None 不代表可写（对端刚关、connect() 尚未回到循环顶）。
        # 判活后再发送，避免把帧写进已关闭的协议对象里换一条被吞掉的 debug 日志。
        if not _conn_is_open(ws):
            return
        async with self._send_lock:
            try:
                # WD-04：加超时。半开连接上 await send 会一直缓冲而不抛异常，无超时会让
                # _send_lock 永久不释放，此后每次心跳/ack/进房都派一个新任务堆在锁上（任务数
                # 与内存无上限增长），而心跳实际再也发不出去。
                await asyncio.wait_for(ws.send(data), timeout=_SEND_TIMEOUT)
            except asyncio.TimeoutError:
                # 超时说明连接已不可用：主动关闭以触发重连，而不是继续在死连接上堆积
                logger.warning(i18n.tr("弹幕发送超时（{seconds}s），判定连接已失效并触发重连", seconds=_SEND_TIMEOUT))
                try:
                    await ws.close()
                except Exception:
                    # 吞没即正确：关不上也要 return——外层 connect() 的 async for 会因连接不可用
                    # 而抛错并进入重连；在此重抛只会把「发送超时」升级成「收包协程异常」，反而
                    # 更晚恢复。
                    pass
                return
            except Exception as e:
                # 不重抛是刻意的（原为裸 except: pass，发送失败完全无声，表现为「进房包发了
                # 但永远收不到弹幕」且无线索）：send 多由 on_ready 等同步回调经 send_nowait
                # 触发，重抛会打断收包主循环，故至少留一条 debug。
                logger.debug(i18n.tr("弹幕数据发送失败（已忽略）: {type_name}: {e}", type_name=type(e).__name__, e=e))

    # 同步版发送：把 send(data) 作为任务丢进事件循环，立即返回不等待结果（供 on_ready 等同步回调使用）。
    def send_nowait(self, data: Union[bytes, str]) -> None:
        ws = self._ws
        if ws is None or not _conn_is_open(ws):
            return
        # 不用裸 `asyncio.ensure_future(self.send(data))`——任务只被 asyncio 弱引用，
        # 可能在回调前被 GC，异常无人取走（详见 src/base.py 同名注释），而这里恰是全项目最核心
        # 的进房/心跳发送口。现由 spawn_danmaku_task（完成回调里落盘异常）+ self._pending 持强
        # 引用（done_callback 里 discard 回收）；在途上界由 _MAX_PENDING_SENDS 兜住。
        if len(self._pending) >= _MAX_PENDING_SENDS:
            logger.warning(i18n.tr("弹幕发送后台任务堆积超过 {count} 个，本次发送已丢弃", count=_MAX_PENDING_SENDS))
            return
        task = spawn_danmaku_task(self.send(data))
        self._pending.add(task)
        task.add_done_callback(self._pending.discard)

    # 心跳循环任务：每隔 heartbeat_interval 秒调 on_heartbeat（同步或协程均支持），已停止或
    # 连接为空时退出。单次心跳加 asyncio.wait_for 兜底——心跳回调若因网络阻塞永久挂起，后续
    # 心跳将永远无法被调度。timeout 取 heartbeat_interval + 1s 缓冲：心跳正常 1 秒内必返回，
    # 超时即视为本轮失败（关连接让外层 connect 走重连）。
    async def _heartbeat_loop(self) -> None:
        _HEARTBEAT_TIMEOUT_SECONDS = max(1.0, self.heartbeat_interval + 1.0)
        while not self._stopped:
            await asyncio.sleep(self.heartbeat_interval)
            if self._stopped or self._ws is None:
                break
            if self._on_heartbeat:
                try:
                    result = self._on_heartbeat()
                    if inspect.isawaitable(result):
                        # 协程型心跳加 wait_for 兜底：超时即关连接、退出心跳循环，让外层 connect
                        # 走重连；非协程型（同步回调）原样调用、不加超时——同步回调阻塞本协程属
                        # 「调用方违反契约」，此处无法挽救。
                        try:
                            await asyncio.wait_for(cast(Awaitable[None], result), timeout=_HEARTBEAT_TIMEOUT_SECONDS)
                        except TimeoutError:
                            # 统一用项目 logger + i18n.tr，格式说明符按约定在调用方先
                            # 求值。不得换回「别名 logger + f-string」：f-string 在查目录前完成
                            # 插值，文案永远无法翻译；而 i18n 门禁（tests/test_i18n_migration.py）
                            # 的判据是 `node.func.value.id == "logger"`，别名形态对它完全隐形。
                            logger.warning(
                                i18n.tr(
                                    "[ws_client] 心跳回调超时 ({seconds}s),关闭连接以触发重连",
                                    seconds=f"{_HEARTBEAT_TIMEOUT_SECONDS:.0f}",
                                )
                            )
                            try:
                                if self._ws is not None:
                                    await self._ws.close()
                            except Exception:
                                # 吞没即正确：关不上也要 break 出心跳循环让外层 connect() 走重连；
                                # 重抛只会把「心跳超时」升级为「心跳协程异常退出」，连接反而更晚回收。
                                pass
                            break
                except Exception:
                    # 吞没即正确：单次心跳失败（构造包异常、发送被拒）不该终止心跳循环——
                    # 连接还活着，下一轮心跳或协议层 ping 超时会正常把故障暴露出来。
                    pass

    # 主动关闭：置停止标记（阻止后续重连与心跳）并关闭底层连接，异常忽略，无返回值。
    async def close(self) -> None:
        self._stopped = True
        if self._ws is not None:
            try:
                await self._ws.close()
            except Exception:
                # 吞没即正确：close() 是「调用方要求停止」的收尾动作，连接可能已被对端关掉
                # （重复 close 抛 ConnectionClosed 属正常），重抛会让录制线程看到一条与停止
                # 无关的异常。
                pass

    # 显式「失败出口」——与 close() 一样终止重连与心跳，但**仍然**回调 on_close(reason)。
    # 为什么不能复用 close()：close() 语义是「调用方主动停止」，connect() 里两条
    # `if self._stopped: break` 出口都不触发 _on_close。B站的 _reject_auth（AUTH_REPLY 非 0
    # 的软拒绝、8 秒看门狗超时）走的正是 close()，于是 collector 侧与 room_connected 配对的
    # hub.room_closed() 永不发出，Web 弹幕监控页把该房间永久停在「已连接 / 0 条」。
    # reason 由调用方给出可读文案；本方法负责脱敏后经 _report_close 投递（约定见文件头）。
    async def fail(self, reason: str = "") -> None:
        self._stopped = True
        if self._ws is not None:
            try:
                await self._ws.close()
            except Exception:
                # 吞没即正确：同 close()——对端可能已关，重复 close 抛 ConnectionClosed 属正常，
                # 重抛只会把「判定连接不可用」升级成调用方（同步回调）的异常源。
                pass
        self._report_close(reason)
