# -*- coding: utf-8 -*-
# 同步 HTTP 客户端模块 - 提供同步 HTTP 请求功能

import atexit
import gzip
import http.client
import json
import ssl
import threading
import urllib.error
import urllib.parse
import urllib.request
import weakref
from collections.abc import Mapping, Sequence
from typing import TypeAlias, cast

import requests

# JSON 可序列化类型别名：对齐 requests._types.JsonType 的结构（该别名在较新版 requests 中
# 定义于 TYPE_CHECKING 块内、运行时不可导入，故本地显式重定义，同时满足运行时注解求值
# 与 requests.post(json=...) 的参数类型校验两端）。
JsonType: TypeAlias = None | bool | int | float | str | Sequence["JsonType"] | Mapping[str, "JsonType"]

from . import http_config as config
from .logger import logger

# 禁用代理的处理器（本地请求不使用代理）
no_proxy_handler = urllib.request.ProxyHandler({})

# SSL 上下文配置（禁用证书验证）
ssl_context = ssl.create_default_context()
ssl_context.check_hostname = False
ssl_context.verify_mode = ssl.CERT_NONE

# 预构建 opener：禁用代理 + 禁用证书验证（ssl_verify=False 时使用）
_opener_insecure = urllib.request.build_opener(no_proxy_handler, urllib.request.HTTPSHandler(context=ssl_context))
# 预构建 opener：仅禁用代理，保留默认证书验证（ssl_verify=True 时使用）
_opener_secure = urllib.request.build_opener(no_proxy_handler)


def _get_opener() -> urllib.request.OpenerDirector:
    # 按全局 SSL 验证开关选择本地请求 opener
    return _opener_secure if config.ssl_verify else _opener_insecure


_thread_local = threading.local()
# 进程内全部线程 Session 的弱引用登记：线程销毁后条目自动回收，不阻止 GC；
# 进程退出时（atexit）据此统一优雅关闭仍存活的连接池（80+ 房间长跑场景）
_all_sessions: "weakref.WeakSet[requests.Session]" = weakref.WeakSet()
_all_sessions_lock = threading.Lock()


def _session() -> requests.Session:
    # 线程内复用的 requests.Session。requests 的模块级 get/post 每次都会新建一个
    # Session 并在退出时销毁，底层 urllib3 连接池随之丢弃——每次请求都要重新建立
    # TCP（HTTPS 还要重新握手），实测单次约 11.9ms vs 复用的 1.5ms、200 次请求产生
    # 200 条连接 vs 1 条。本函数是 sync_req 的必经路径（125 处调用点，位于平台解析
    # 主链路），80+ 房间并发时收益显著。
    # Session 本身不是线程安全的，故用 thread-local 每线程一份：既避免跨线程共享，
    # 又能让同一房间线程（长期存活）持续复用同一连接池。
    session: requests.Session | None = getattr(_thread_local, "session", None)
    if session is None:
        session = requests.Session()
        _thread_local.session = session
        with _all_sessions_lock:
            _all_sessions.add(session)
    return session


def close_session() -> None:
    # 关闭当前线程的 Session 并释放其连接池（房间线程退出路径可显式调用）。
    # 关闭后下次 _session() 会重建，不影响后续请求
    session: requests.Session | None = getattr(_thread_local, "session", None)
    if session is not None:
        _thread_local.session = None
        try:
            session.close()
        except Exception:
            pass


def close_all_sessions() -> None:
    # 进程退出时统一关闭所有线程（含主线程）的 Session 连接池，由 atexit 调用；
    # WeakSet 快照迭代受 _IterationGuard 保护，期间条目被 GC 移除也安全
    with _all_sessions_lock:
        sessions = list(_all_sessions)
        _all_sessions.clear()
    for session in sessions:
        try:
            session.close()
        except Exception:
            pass


atexit.register(close_all_sessions)


OptionalStr = str | None
OptionalDict = dict[str, str] | None


def sync_req(
    url: str,
    proxy_addr: OptionalStr = None,
    headers: OptionalDict = None,
    data: Mapping[str, object] | str | bytes | None = None,
    json_data: JsonType = None,
    timeout: int = 20,
    redirect_url: bool = False,
    abroad: bool = False,
    content_encoding: str = "utf-8",
) -> str:
    # 同步 HTTP 请求函数，支持 GET/POST、代理、重定向、gzip 解压等功能
    if headers is None:
        headers = {}
    resp_str = ""
    try:
        if proxy_addr:
            # 使用代理的请求
            proxies = {"http": proxy_addr, "https": proxy_addr}
            if data or json_data:
                # POST 请求（带代理）
                response = _session().post(
                    url,
                    data=data,
                    json=json_data,
                    headers=headers,
                    proxies=proxies,
                    timeout=timeout,
                    verify=config.ssl_verify,
                )
            else:
                # GET 请求（带代理）
                response = _session().get(
                    url, headers=headers, proxies=proxies, timeout=timeout, verify=config.ssl_verify
                )
            if redirect_url:
                return response.url
            resp_str = response.text
        else:
            # 不使用代理的请求
            # 处理请求数据编码
            if data and not isinstance(data, bytes):
                if isinstance(data, dict):
                    # dict 类型转换为 URL 编码
                    data = urllib.parse.urlencode(data).encode(content_encoding)
                else:
                    # 其他类型转换为字符串再编码
                    data = str(data).encode(content_encoding)
            if json_data and isinstance(json_data, (dict, list)):
                # JSON 数据编码
                data = json.dumps(json_data).encode(content_encoding)

            # 创建请求对象
            req = urllib.request.Request(url, data=cast("bytes | None", data), headers=headers)

            try:
                if abroad:
                    # 海外请求：仅在全局禁用证书验证时使用 CERT_NONE 上下文
                    _resp = cast(
                        http.client.HTTPResponse,
                        urllib.request.urlopen(
                            req, timeout=timeout, context=None if config.ssl_verify else ssl_context
                        ),
                    )
                else:
                    # 本地请求（使用按全局配置选择的 opener）
                    _resp = cast(http.client.HTTPResponse, _get_opener().open(req, timeout=timeout))
                try:
                    if redirect_url:
                        return _resp.url

                    # 处理响应编码和 gzip 解压
                    resp_encoding = _resp.headers.get("Content-Encoding")
                    if resp_encoding == "gzip":
                        # gzip 解压
                        resp_bytes = gzip.decompress(_resp.read())
                        resp_str = resp_bytes.decode(content_encoding)
                    else:
                        # 普通解码
                        resp_str = _resp.read().decode(content_encoding)
                finally:
                    _resp.close()

            except urllib.error.HTTPError as e:
                # HTTP 错误处理
                try:
                    if e.code == 400:
                        resp_str = e.read().decode(content_encoding)
                    else:
                        raise
                finally:
                    e.close()
            except urllib.error.URLError as e:
                # URL 错误记录日志
                logger.warning(f"URL Error: {e}")
                raise
            except Exception as e:
                # 其他错误记录日志
                logger.error(f"An error occurred: {e}")
                raise

    except Exception as e:
        # 请求失败统一记录并返回空串：错误文本伪装成响应体会被上游误当有效数据解析
        logger.error(f"sync_req 请求失败: {type(e).__name__}: {e}")
        resp_str = ""

    return resp_str
