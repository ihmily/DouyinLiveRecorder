# -*- coding: utf-8 -*-
# 异步 HTTP 客户端模块 - 提供高效的异步 HTTP 请求功能

import asyncio
import httpx
from typing import Dict, Any, Tuple
from . import config
from .. import utils
from ..logger import logger

OptionalStr = str | None
OptionalDict = Dict[str, Any] | None

# 全局连接池配置，提高 HTTP 请求性能
_httpx_limits = httpx.Limits(max_connections=100, max_keepalive_connections=20)

# 复用 Client 以真正发挥 keepalive 连接池作用
# AsyncClient 必须在事件循环内创建并使用，进程退出时需 aclose() 释放连接池
_client_cache: Dict[Tuple[str, bool, bool], httpx.AsyncClient] = {}


async def _get_client(
        proxy_addr: OptionalStr,
        timeout: int,
        verify: bool,
        http2: bool,
) -> httpx.AsyncClient:
    # 按 (代理, verify, http2) 维度复用 AsyncClient
    # timeout 在每次请求时单独传入，避免不同调用方覆盖彼此的超时
    key = (proxy_addr or "", verify, http2)
    client = _client_cache.get(key)
    if client is None or client.is_closed:
        client = httpx.AsyncClient(
            proxy=proxy_addr,
            timeout=timeout,
            verify=verify,
            http2=http2,
            limits=_httpx_limits,
        )
        _client_cache[key] = client
    return client


async def _close_all_clients() -> None:
    # 进程退出时释放所有复用的 AsyncClient，避免连接池泄漏
    for client in list(_client_cache.values()):
        try:
            if not client.is_closed:
                await client.aclose()
        except Exception as e:
            logger.debug(e)
    _client_cache.clear()


def close_all_clients_sync() -> None:
    # 同步安全清理（供 atexit / 信号处理器调用）：
    # 若当前线程有可用事件循环，则在其上驱动 _close_all_clients；
    # 否则清空缓存交由 GC 兜底（httpx.AsyncClient 析构会尝试关闭底层传输）
    if not _client_cache:
        return
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            raise RuntimeError("loop closed")
        if loop.is_running():
            # 信号/atexit 钩子在事件循环线程中触发时无法再 run_until_complete，
            # 仅清理缓存引用，让循环关闭时由 AsyncClient.__del__ 兜底关闭
            _client_cache.clear()
            return
        loop.run_until_complete(_close_all_clients())
    except Exception as e:
        logger.debug(f"close_all_clients_sync 回退到引用清理: {e}")
        _client_cache.clear()


async def async_req(
        url: str,
        proxy_addr: OptionalStr = None,
        headers: OptionalDict = None,
        data: dict | str | bytes | None = None,
        json_data: dict | list | None = None,
        timeout: int = 20,
        redirect_url: bool = False,
        return_cookies: bool = False,
        include_cookies: bool = False,
        abroad: bool = False,
        content_encoding: str = 'utf-8',
        verify: bool | None = None,
        http2: bool = True
) -> str | dict | tuple:
    # 异步 HTTP 请求函数，支持 GET/POST、代理、Cookie 等功能
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
                response = await client.post(url, content=content_data, json=json_data, headers=headers, timeout=timeout)
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
            resp_str = ""
        elif return_cookies:
            resp_str = ("", {}) if include_cookies else {}
        else:
            resp_str = ""

    return resp_str


async def get_response_status(url: str, proxy_addr: OptionalStr = None, headers: OptionalDict = None,
                              timeout: int = 10, abroad: bool = False, verify: bool | None = None, http2=False) -> bool:
    # 检查 URL 响应状态，确认是否可访问
    # 未显式指定时使用全局 SSL 验证开关
    if verify is None:
        verify = config.ssl_verify
    try:
        proxy_addr = utils.handle_proxy_addr(proxy_addr)
        client = await _get_client(proxy_addr, timeout, verify, http2)
        response = await client.head(url, headers=headers, follow_redirects=True, timeout=timeout)
        return response.status_code == 200
    except Exception as e:
        logger.debug(e)
    return False
