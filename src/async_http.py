# -*- coding: utf-8 -*-
# 异步 HTTP 客户端模块 - 提供高效的异步 HTTP 请求功能

import asyncio
import threading
from collections.abc import Mapping, Sequence
from typing import cast

import httpx

from . import http_config as config
from . import utils
from .logger import logger

OptionalStr = str | None
OptionalDict = dict[str, str] | None

# 全局连接池配置，提高 HTTP 请求性能
_httpx_limits = httpx.Limits(max_connections=100, max_keepalive_connections=20)

# 复用 Client 以真正发挥 keepalive 连接池作用
# AsyncClient 必须在事件循环内创建并使用，进程退出时需 aclose() 释放连接池
# 值为 (client, 创建时的事件循环)，用于检测 asyncio.run() 导致的循环变更
_client_cache: dict[tuple[str, bool, bool], tuple[httpx.AsyncClient, asyncio.AbstractEventLoop]] = {}
# 保护 _client_cache 的跨线程锁：多房间「独立线程+独立事件循环」并发取客户端时
# 序列化 check-then-act 竞态。临界区内只做同步 dict 操作、绝不含 await。
_client_cache_lock = threading.Lock()


async def _get_client(
    proxy_addr: OptionalStr,
    timeout: int,
    verify: bool,
    http2: bool,
) -> httpx.AsyncClient:
    # 按 (代理, verify, http2) 维度复用 AsyncClient
    # timeout 在每次请求时单独传入，避免不同调用方覆盖彼此的超时
    key = (proxy_addr or "", verify, http2)
    current_loop = asyncio.get_running_loop()
    with _client_cache_lock:
        cached = _client_cache.get(key)
    if cached is not None:
        client, client_loop = cached
        # client 未关闭且事件循环未变更时直接复用
        if not client.is_closed and client_loop is current_loop:
            return client
        # 缓存的 client 已失效（已关闭或事件循环变更）：先释放旧连接池，避免泄漏
        stale = False
        with _client_cache_lock:
            # 二次检查：可能已被并发线程替换，替换成功者负责旧 client 的释放
            if _client_cache.get(key) is cached:
                _client_cache.pop(key, None)
                stale = True
        if stale and not client.is_closed:
            if client_loop is current_loop:
                try:
                    await client.aclose()
                except Exception as e:
                    logger.debug(f"关闭失效 AsyncClient 失败: {e}")
            elif not client_loop.is_closed():
                # 跨事件循环：在其创建循环上安排 aclose，避免在其创建循环外操作 transport
                try:
                    _ = asyncio.run_coroutine_threadsafe(client.aclose(), client_loop)
                except Exception as e:
                    logger.debug(f"跨循环关闭 AsyncClient 失败: {e}")
    client = httpx.AsyncClient(
        proxy=proxy_addr,
        timeout=timeout,
        verify=verify,
        http2=http2,
        limits=_httpx_limits,
    )
    with _client_cache_lock:
        _client_cache[key] = (client, current_loop)
    return client


async def _close_all_clients() -> None:
    # 进程退出时释放所有复用的 AsyncClient，避免连接池泄漏
    with _client_cache_lock:
        clients = list(_client_cache.values())
        _client_cache.clear()
    for client, _ in clients:
        try:
            if not client.is_closed:
                await client.aclose()
        except Exception as e:
            logger.debug(e)


def close_all_clients_sync() -> None:
    # 同步安全清理（供 atexit / 信号处理器调用）：
    # 若当前线程有可用事件循环，则在其上驱动 _close_all_clients；
    # 否则清空缓存交由 GC 兜底（httpx.AsyncClient 析构会尝试关闭底层传输）
    with _client_cache_lock:
        if not _client_cache:
            return
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            raise RuntimeError("loop closed")
        if loop.is_running():
            # 信号/atexit 钩子在事件循环线程中触发时无法再 run_until_complete，
            # 仅清理缓存引用，让循环关闭时由 AsyncClient.__del__ 兜底关闭
            with _client_cache_lock:
                _client_cache.clear()
            return
        loop.run_until_complete(_close_all_clients())
    except Exception as e:
        logger.debug(f"close_all_clients_sync 回退到引用清理: {e}")
        with _client_cache_lock:
            _client_cache.clear()


async def async_req(
    url: str,
    proxy_addr: OptionalStr = None,
    headers: OptionalDict = None,
    data: Mapping[str, object] | str | bytes | bytearray | memoryview | None = None,
    json_data: Mapping[str, object] | Sequence[object] | None = None,
    timeout: int = 20,
    redirect_url: bool = False,
    return_cookies: bool = False,
    include_cookies: bool = False,
    abroad: bool = False,
    content_encoding: str = "utf-8",
    verify: bool | None = None,
    http2: bool = True,
) -> str | dict[str, str] | tuple[str, dict[str, str]]:
    # 异步 HTTP 请求函数，支持 GET/POST、代理、Cookie 等功能
    # abroad / content_encoding 仅为与 sync_req 保持签名兼容，异步实现无需显式使用
    _ = (abroad, content_encoding)
    if headers is None:
        headers = {}
    # 未显式指定时使用全局 SSL 验证开关
    if verify is None:
        verify = config.ssl_verify
    try:
        # 处理代理地址
        proxy_addr = utils.handle_proxy_addr(proxy_addr)
        client = await _get_client(proxy_addr, timeout, verify, http2)
        if data or json_data:
            if isinstance(data, (bytes, bytearray, memoryview)):
                # 将 bytearray/memoryview 转换为 bytes（已是 bytes 时直接使用，避免无谓拷贝）
                content_data = data if isinstance(data, bytes) else bytes(data)
                response = await client.post(
                    url, content=content_data, json=json_data, headers=headers, timeout=timeout
                )
            elif isinstance(data, str):
                response = await client.post(url, content=data, json=json_data, headers=headers, timeout=timeout)
            else:
                # data 是 dict 或 None
                response = await client.post(url, data=data, json=json_data, headers=headers, timeout=timeout)
        else:
            # GET 请求
            response = await client.get(url, headers=headers, follow_redirects=True, timeout=timeout)

        # 根据参数返回不同结果（必须在 try 块内访问 response，异常时 response 未定义）
        if redirect_url:
            # 返回重定向后的 URL
            return str(response.url)
        elif return_cookies:
            # 返回 Cookie
            cookies_dict = {name: value for name, value in response.cookies.items()}
            return (response.text, cookies_dict) if include_cookies else cookies_dict
        else:
            # 返回响应文本
            resp_str = response.text
    except Exception as e:
        # 异常时按调用方期望的返回契约回退，避免类型冲突：
        #   redirect_url -> 空字符串（调用方据此判定未取到 URL）
        #   return_cookies -> 空 dict / ("", {})（调用方据此判定登录/取 cookie 失败）
        #   默认文本 -> 空字符串（调用方解析失败进入各自异常分支）
        logger.debug(e)
        if redirect_url:
            return ""
        elif return_cookies:
            return ("", cast(dict[str, str], {})) if include_cookies else cast(dict[str, str], {})
        else:
            return ""

    return resp_str


async def get_response_status(
    url: str,
    proxy_addr: OptionalStr = None,
    headers: OptionalDict = None,
    timeout: int = 10,
    abroad: bool = False,
    verify: bool | None = None,
    http2: bool = False,
) -> bool:
    # 检查 URL 响应状态，确认是否可访问
    # 未显式指定时使用全局 SSL 验证开关
    _ = abroad
    if verify is None:
        verify = config.ssl_verify
    try:
        proxy_addr = utils.handle_proxy_addr(proxy_addr)
        client = await _get_client(proxy_addr, timeout, verify, http2)
        response = await client.head(url, headers=headers, follow_redirects=True, timeout=timeout)
        if response.status_code == 200:
            return True
        # 部分 CDN（如抖音 m3u8）对 HEAD 返回非 200（含 403/404），但 GET 可正常拉流。
        # 对 m3u8 源额外做一次 Range GET 轻量可达性探测，避免误判不可达而降级画质。
        # 注意：仅覆盖 400/401/403/405 会漏掉 404（部分 CDN 对 HEAD 一律回 404），
        # 因此 HEAD 非 2xx 的 m3u8 源一律进入探测。
        if ".m3u8" in url and response.status_code != 200:
            probe = await client.get(
                url, headers={**(headers or {}), "Range": "bytes=0-0"}, follow_redirects=True, timeout=timeout
            )
            if probe.status_code in (200, 206):
                return True
            logger.debug(
                f"get_response_status 校验未通过: {url} - HEAD={response.status_code}, "
                f"Range-GET={probe.status_code}, content-type={probe.headers.get('content-type', '')}"
            )
            return False
        logger.debug(
            f"get_response_status 校验未通过: {url} - status_code={response.status_code}, "
            f"content-type={response.headers.get('content-type', '')}"
        )
        return False
    except Exception as e:
        # 注意：Windows 下 socket.timeout 的 str() 为空，仅打印 {e} 会得到空白日志，
        # 必须带上 URL 与异常类型，否则无法定位是超时、连接被拒还是证书问题。
        logger.debug(f"get_response_status 校验失败（判定为不可达）: {url} - {type(e).__name__}: {e}")
    return False
