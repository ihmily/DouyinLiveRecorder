# -*- encoding: utf-8 -*-
# 统一 cookie 缓存模块
#
# 背景：原先各平台各自维护一份「从该网址动态获取的访客 cookie」缓存并各自请求网址
# （如 src/ttwid.py 的抖音 ttwid、src/spider.py 的快手 did）。在「每个 room 独立线程 +
# 独立 asyncio.run 循环」的并发模型下，同网址会被多个房间重复请求，触发平台风控
# （返回 HTTP 200 但空响应体），表现为解析静默失败。
#
# 本模块把「按网址动态获取 cookie」的缓存统一到进程内唯一一份存储：
#   - fetch_cookies(url, proxy, ...) : 统一读取入口——命中缓存直接返回；未命中则加锁只
#                                     拉取一次，其余并发调用等待复用同一份结果。
#   - get_cached(url, proxy)        : 同步只读查询（不触发网络请求），供其他模块复用。
#   - get_cookie_str(url, proxy, ...) : 同上但返回拼接好的 "k=v; k=v" 字符串。
#   - invalidate(url, proxy) / clear() : 失效与清空，供调试或强制刷新。
#
# ── 存储结构 ──
#   _cookie_cache: dict[str, tuple[dict[str, str], float]]
#       key   = _make_key(url, proxy)        # 归一化网址 + 代理地址
#       value = (cookie_dict, expire_ts)     # 原始 cookie 字典 + 写入时刻(monotonic)
#   缓存的是「网址下发的原始访客 cookie 字典」，不做平台特定的字段裁剪，
#   由各调用方按自己的需要提取（如 ttwid 取 "ttwid"，快手取 "did"/"didv"）。
#
# ── 失效策略 ──
#   - TTL 失效：每个条目带写入时间戳，超过 ttl 秒后视为失效，下次访问重新拉取。
#     DEFAULT_TTL = 30 * 60（30 分钟），与 src/room.py 的 sec_uid 缓存保持一致，
#     在「消除重复请求」与「cookie 失效后自愈」之间取得平衡（录制进程可能连续运行数天）。
#   - 失败不缓存：拉取异常或返回空字典时一律不写入缓存，下次访问会重试，
#     避免把「瞬时失败」固化成长期空值。
#   - 并发去重（singleflight）：threading.Lock 只保护「缓存字典 + 在途登记表」的同步
#     读写，绝不在锁内 await——RLock 跨 await 持有时，同事件循环内的并发协程属于同一
#     线程、全部可重入该锁，互斥完全失效（多个协程会并发请求同一网址，恰恰是要消除
#     的风控触发源）。每个房间线程各自 asyncio.run() 独立循环：抢到拉取权的协程负责
#     拉取，等待者（同循环或跨循环）登记 future 复用同一份结果，跨循环交付经
#     loop.call_soon_threadsafe 回写（future 非线程安全，禁止跨线程直接 set_result）。
#
# ── 跨模块调用方式 ──
#   from .cookie_cache import fetch_cookies, get_cached, get_cookie_str
#   1) 动态获取并复用：cookies = await fetch_cookies("https://live.douyin.com/", proxy_addr=proxy)
#   2) 仅复用不拉取：   cached  = get_cached("https://live.douyin.com/", proxy_addr=proxy)
#   3) 取拼接字符串：   s      = await get_cookie_str("https://live.kuaishou.com/", proxy_addr=proxy)
#   同网址的任意模块（抖音 ttwid、快手 did 等）共用同一份缓存，绝不会对同一网址重复发起请求。
# pyright: reportImplicitStringConcatenation=none, reportUnknownArgumentType=none, reportUnknownMemberType=none, reportUnknownVariableType=none
import asyncio
import threading
import time
from typing import Any, Callable, Optional

from .async_http import async_req
from .logger import logger

OptionalStr = str | None

# 进程级唯一 cookie 缓存：key -> (cookie_dict, expire_ts)
_cookie_cache: dict[str, tuple[dict[str, str], float]] = {}
# 在途拉取登记表：key 在表中即表示某协程正在拉取该网址；value 为等待结果的
# (等待者所在事件循环, 等待者 future) 列表，拉取完成后逐个交付
_inflight: dict[str, list[tuple[asyncio.AbstractEventLoop, asyncio.Future[dict[str, str]]]]] = {}
# 去重锁：只保护 _cookie_cache 与 _inflight 的同步读写（临界区内绝无 await）
_cache_lock = threading.Lock()
# 等待其它线程在途拉取的超时余量（秒）：拉取线程若异常死亡（如 asyncio.run 被硬杀），
# 等待者按 timeout + 余量 超时返回空结果，避免永久挂起
_INFLIGHT_WAIT_MARGIN = 5.0

# 默认失效时间：30 分钟。允许调用方按需覆盖（如更长生命周期的凭据）。
DEFAULT_TTL = 30 * 60


def _make_key(url: str, proxy_addr: OptionalStr) -> str:
    # 以「归一化网址 + 代理」为 key。
    # 访客 cookie 由域名下发，与查询参数/尾斜杠无关，故去掉 ? 与尾随 /。
    # 代理不同（直连 vs 走代理）下发的 cookie 可能不同，故纳入 key 区分。
    normalized = url.split("?")[0].rstrip("/")
    return f"{normalized}|{proxy_addr or ''}"


def _get_cached_entry(key: str) -> tuple[dict[str, str], float] | None:
    # 在锁内读取，避免并发下的字典视图不一致
    with _cache_lock:
        return _cookie_cache.get(key)


def get_cached(url: str, proxy_addr: OptionalStr = None) -> dict[str, str] | None:
    # 同步只读查询：命中且未过期返回 cookie 字典，否则返回 None（不触发网络请求）。
    # 供其他模块在不发起请求的前提下复用已缓存的同网址 cookie。
    entry = _get_cached_entry(_make_key(url, proxy_addr))
    if entry is None:
        return None
    cookies, expire_ts = entry
    if (time.monotonic() - expire_ts) >= DEFAULT_TTL:
        return None
    return cookies


def _deliver(
    waiter_loop: asyncio.AbstractEventLoop, fut: asyncio.Future[dict[str, str]], cookies: dict[str, str]
) -> None:
    # 把拉取结果交付给等待者（须在拉取方协程内调用）：
    # - 等待者与拉取方同循环：本函数正运行于该循环线程，直接 set_result 安全；
    # - 跨循环：future 非线程安全，必须经 call_soon_threadsafe 调度到等待者
    #   自己的循环线程执行；其循环已关闭时结果无处交付（等待方的超时兜底）。
    def _set() -> None:
        if not fut.done():
            fut.set_result(cookies)

    if waiter_loop is asyncio.get_running_loop():
        _set()
        return
    try:
        waiter_loop.call_soon_threadsafe(_set)
    except RuntimeError:
        # 等待者所在循环已关闭：丢弃结果，其 wait_for 超时兜底
        pass


async def fetch_cookies(
    url: str,
    proxy_addr: OptionalStr = None,
    *,
    headers: Optional[dict[str, str]] = None,
    timeout: int = 10,
    http2: bool = False,
    ttl: int = DEFAULT_TTL,
    fetcher: Callable[..., Any] | None = None,
) -> dict[str, str]:
    # 统一读取入口：命中缓存直接返回；未命中则加锁只拉取一次，并发调用复用同一结果。
    # 返回该网址下发的原始访客 cookie 字典（调用方按需提取字段）。
    #
    # fetcher: 实际发起 HTTP 请求的可调用对象，默认使用本模块的 async_req。调用方应传入
    # 自身命名空间下的 async_req（如 ttwid/spider 模块导入的 async_req），以便单测中对
    # "src.<mod>.async_req" 打桩仍能拦截（各模块导入的是同一函数对象，但分属不同命名空间，
    # 对模块命名空间打桩不影响本模块默认引用）。签名需兼容
    # (url, *, proxy_addr, headers, return_cookies, timeout, http2) -> dict。
    key = _make_key(url, proxy_addr)
    now = time.monotonic()
    do_fetch: Callable[..., Any] = fetcher if callable(fetcher) else async_req

    # 快速路径（无锁）：绝大多数调用命中此处
    entry = _get_cached_entry(key)
    if entry is not None and (now - entry[1]) < ttl:
        return entry[0]

    # 未命中：锁内二次检查缓存（锁内绝无 await）。key 已在途则登记为等待者复用
    # 同一份结果；否则本协程登记为拉取者，负责拉取一次
    loop = asyncio.get_running_loop()
    waiter: asyncio.Future[dict[str, str]] | None = None
    with _cache_lock:
        entry = _cookie_cache.get(key)
        if entry is not None and (time.monotonic() - entry[1]) < ttl:
            return entry[0]
        if key in _inflight:
            waiter = loop.create_future()
            _inflight[key].append((loop, waiter))
        else:
            _inflight[key] = []  # 占位：本协程即拉取者，列表留给后续等待者登记
    if waiter is not None:
        try:
            return await asyncio.wait_for(waiter, timeout + _INFLIGHT_WAIT_MARGIN)
        except TimeoutError:
            # 拉取者所在线程异常退出（循环被硬杀等极端场景）：超时返回空结果，
            # 失败不缓存，下次访问重新走拉取
            logger.warning(f"等待其它线程的 cookie 拉取超时，返回空结果: {key}")
            return {}

    # 本协程为拉取者：异常/空结果同样要交付等待者（失败语义与单协程路径一致）
    try:
        try:
            result = await do_fetch(
                url=url,
                proxy_addr=proxy_addr,
                headers=headers,
                return_cookies=True,
                timeout=timeout,
                http2=http2,
            )
        except Exception as e:
            # 失败不缓存，下次访问会重试；带类型+URL 便于排查（Windows 下 e 的 str 可能为空）
            logger.warning(f"动态获取 cookie 失败: {url} - {type(e).__name__}: {e}")
            cookies = {}
        else:
            # async_req(return_cookies=True, include_cookies=False) 成功返回 dict，异常返回 {}
            if isinstance(result, dict):
                cookies = {k: str(v) for k, v in result.items()}
            elif isinstance(result, tuple) and len(result) == 2 and isinstance(result[1], dict):
                cookies = {k: str(v) for k, v in result[1].items()}
            else:
                cookies = {}
    except BaseException:
        # 本协程被取消（房间停止/进程退出）：立即摘除登记并给等待者交付空结果，
        # 避免其它线程的等待者一直等到超时
        with _cache_lock:
            pending = _inflight.pop(key, [])
        for waiter_loop, waiter_fut in pending:
            _deliver(waiter_loop, waiter_fut, {})
        raise
    # 仅缓存非空结果，空结果视为失败不固化，允许重试
    if cookies:
        with _cache_lock:
            _cookie_cache[key] = (cookies, time.monotonic())
        logger.debug(f"动态获取 cookie 成功并缓存: {key}")
    with _cache_lock:
        pending = _inflight.pop(key, [])
    for waiter_loop, waiter_fut in pending:
        _deliver(waiter_loop, waiter_fut, cookies)
    return cookies


async def get_cookie_str(
    url: str,
    proxy_addr: OptionalStr = None,
    *,
    headers: Optional[dict[str, str]] = None,
    timeout: int = 10,
    http2: bool = False,
    ttl: int = DEFAULT_TTL,
    fetcher: Callable[..., Any] | None = None,
) -> str:
    # 便捷封装：返回拼接好的 "k=v; k=v" 字符串；无 cookie 时返回空串。
    cookies = await fetch_cookies(
        url, proxy_addr, headers=headers, timeout=timeout, http2=http2, ttl=ttl, fetcher=fetcher
    )
    return "; ".join(f"{k}={v}" for k, v in cookies.items())


def invalidate(url: str | None = None, proxy_addr: OptionalStr = None) -> None:
    # 失效指定网址（或整份）缓存。url 为 None 时清空全部。
    with _cache_lock:
        if url is None:
            _cookie_cache.clear()
            return
        _cookie_cache.pop(_make_key(url, proxy_addr), None)


def clear() -> None:
    # 清空全部 cookie 缓存（调试/测试用）
    with _cache_lock:
        _cookie_cache.clear()
