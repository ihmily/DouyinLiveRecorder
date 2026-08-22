# 异步 WebSocket 客户端封装（对标 dart simple_live_core 的 WebScoketUtils）。
#
# 提供心跳定时、断线重连（最多 max_reconnect 次，间隔 reconnect_interval 秒）。
# 所有平台弹幕共用此客户端。

from __future__ import annotations

import asyncio
import inspect
import ssl
from typing import Awaitable, Callable, Optional, Union

import websockets


# 根据 url 生成默认 SSL 上下文：wss:// 返回放宽到 @SECLEVEL=1 的 SSLContext 以兼容老套件，ws:// 返回 None。
def _default_ssl_context(url: str) -> Optional[ssl.SSLContext]:
    # 为 wss 连接构造宽松 SSL context。
    #
    #    某些直播平台弹幕服务（如斗鱼 danmuproxy:8506）使用旧 RSA 密钥交换套件，
    #    OpenSSL 3.x 默认 SECLEVEL=1 之上会拒绝握手。降级到 @SECLEVEL=1 以兼容。
    #    ws:// 连接返回 None。
    if not url.startswith("wss://"):
        return None
    ctx = ssl.create_default_context()
    try:
        ctx.set_ciphers("DEFAULT:@SECLEVEL=1")
    except ssl.SSLError:
        pass  # 某些构建不支持该字符串，退回默认
    return ctx


# 各平台弹幕共用的异步 WebSocket 客户端：负责连接、收包分发、定时心跳、断线重连与主动关闭。
class WsClient:
    # 初始化客户端：url/backup_url 为主备地址，on_message/on_ready/on_heartbeat/on_close/on_reconnect 为回调，
    # heartbeat_interval、max_reconnect、reconnect_interval、connect_timeout 控制心跳与重连策略，
    # headers/proxy/ssl_context 为连接参数（ssl_context 未传时按 url 自动生成）；仅保存配置，不发起连接。
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
        # 显式代理(如 Twitch 等海外平台)。None=直连,其余平台行为不变。
        self._proxy = proxy
        # 默认 wss 用宽松 SECLEVEL=1 context；可被 ssl_context 覆盖
        self._ssl_context = ssl_context if ssl_context is not None else _default_ssl_context(url)

        self._ws: Optional["websockets.WebSocketClientProtocol"] = None  # type: ignore[name-defined]
        self._stopped = False
        self._reconnect_count = 0
        self._send_lock = asyncio.Lock()

    # 主协程：连接（重连时改用备用地址）→ 触发 on_ready 并起心跳任务 → 逐帧回调 on_message；
    # 异常或正常断开时按 max_reconnect / reconnect_interval 重连，耗尽则回调 on_close 后返回。
    async def connect(self) -> None:
        # 建立连接并循环收消息，断线后按策略重连。整个生命周期阻塞到 stop 或重连耗尽。
        while not self._stopped:
            url = self._url
            # 重连时切换备用地址（如有）
            if self._reconnect_count > 0 and self._backup_url:
                url = self._backup_url
            try:
                async with websockets.connect(
                    url,
                    additional_headers=self._headers,
                    open_timeout=self.connect_timeout,
                    ping_interval=None,  # 各平台自带心跳，关闭库默认 ping
                    max_size=None,
                    ssl=self._ssl_context,
                    proxy=self._proxy,  # None=直连(B站/虎牙等);Twitch 等海外平台可传显式代理
                ) as ws:
                    self._ws = ws
                    self._reconnect_count = 0  # 连上即重置
                    if self._on_ready:
                        self._on_ready()
                    hb_task = asyncio.create_task(self._heartbeat_loop())
                    try:
                        async for data in ws:
                            if self._stopped:
                                break
                            self._on_message(data)
                    finally:
                        hb_task.cancel()
                        try:
                            await hb_task
                        except asyncio.CancelledError, Exception:
                            pass
            except asyncio.CancelledError:
                break
            except Exception as e:
                if self._stopped:
                    break
                self._reconnect_count += 1
                if self._reconnect_count <= self.max_reconnect:
                    if self._on_reconnect:
                        self._on_reconnect(str(e))
                    await asyncio.sleep(self.reconnect_interval)
                    continue
                # 重连耗尽
                if self._on_close:
                    self._on_close(f"重连超过最大次数，与服务器断开连接: {e}")
                break
            else:
                # 正常关闭（onDone）但未 stop，尝试重连
                if self._stopped:
                    break
                self._reconnect_count += 1
                if self._reconnect_count <= self.max_reconnect:
                    if self._on_reconnect:
                        self._on_reconnect("连接已关闭，正在尝试重连")
                    await asyncio.sleep(self.reconnect_interval)
                    continue
                if self._on_close:
                    self._on_close("重连超过最大次数，与服务器断开连接")
                break

            if self._ws is not None:
                try:
                    await self._ws.close()
                except Exception:
                    pass
                self._ws = None

    # 异步发送一帧数据 data（bytes 或 str）：未连接则直接返回，发送加锁串行化且异常忽略，无返回值。
    async def send(self, data: Union[bytes, str]) -> None:
        if self._ws is None:
            return
        async with self._send_lock:
            try:
                await self._ws.send(data)
            except Exception:
                pass

    # 同步版发送：把 send(data) 作为任务丢进事件循环，立即返回不等待结果（供 on_ready 等同步回调使用）。
    def send_nowait(self, data: Union[bytes, str]) -> None:
        # 同步回调（on_ready 等）中调用的非阻塞发送。
        if self._ws is None:
            return
        asyncio.ensure_future(self.send(data))

    # 心跳循环任务：每隔 heartbeat_interval 秒调用 on_heartbeat（同步或协程均支持），
    # 已停止或连接为空时退出；单次心跳异常忽略以免中断循环。
    async def _heartbeat_loop(self) -> None:
        while not self._stopped:
            await asyncio.sleep(self.heartbeat_interval)
            if self._stopped or self._ws is None:
                break
            if self._on_heartbeat:
                try:
                    result = self._on_heartbeat()
                    if inspect.isawaitable(result):
                        await result
                except Exception:
                    pass

    # 主动关闭：置停止标记（阻止后续重连与心跳）并关闭底层连接，异常忽略，无返回值。
    async def close(self) -> None:
        self._stopped = True
        if self._ws is not None:
            try:
                await self._ws.close()
            except Exception:
                pass
