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
#   - 并发去重：threading.RLock 双检查。每个 room 各自 asyncio.run() 独立循环并发执行，
#     per-loop 的 asyncio.Lock 无法跨循环协调，故用 threading 锁；
#     锁需跨 await 持有，同事件循环并发协程重入不会自旋死锁，故必须用 RLock（见 src/ttwid.py）。
#
# ── 跨模块调用方式 ──
#   from .cookie_cache import fetch_cookies, get_cached, get_cookie_str
#   1) 动态获取并复用：cookies = await fetch_cookies("https://live.douyin.com/", proxy_addr=proxy)
#   2) 仅复用不拉取：   cached  = get_cached("https://live.douyin.com/", proxy_addr=proxy)
#   3) 取拼接字符串：   s      = await get_cookie_str("https://live.kuaishou.com/", proxy_addr=proxy)
#   同网址的任意模块（抖音 ttwid、快手 did 等）共用同一份缓存，绝不会对同一网址重复发起请求。
# pyright: reportImplicitStringConcatenation=none, reportUnknownArgumentType=none, reportUnknownMemberType=none, reportUnknownVariableType=none
import threading
import time
from typing import Any, Callable, Optional

from .async_http import async_req
from .logger import logger

OptionalStr = str | None

# 进程级唯一 cookie 缓存：key -> (cookie_dict, expire_ts)
_cookie_cache: dict[str, tuple[dict[str, str], float]] = {}
# 跨线程/跨循环去重锁（RLock：锁跨越 await 持有，同线程重入安全）
_cache_lock = threading.RLock()

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

    # 未命中：加锁二次检查，抢到锁的协程负责拉取，其余等待其完成
    with _cache_lock:
        entry = _cookie_cache.get(key)
        if entry is not None and (now - entry[1]) < ttl:
            return entry[0]
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
            return {}
        # async_req(return_cookies=True, include_cookies=False) 成功返回 dict，异常返回 {}
        if isinstance(result, dict):
            cookies = {k: str(v) for k, v in result.items()}
        elif isinstance(result, tuple) and len(result) == 2 and isinstance(result[1], dict):
            cookies = {k: str(v) for k, v in result[1].items()}
        else:
            cookies = {}
        # 仅缓存非空结果，空结果视为失败不固化，允许重试
        if cookies:
            _cookie_cache[key] = (cookies, time.monotonic())
            logger.debug(f"动态获取 cookie 成功并缓存: {key}")
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
