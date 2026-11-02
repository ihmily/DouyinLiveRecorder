# -*- encoding: utf-8 -*-
# 抖音 ttwid 共享缓存模块
#
# 为什么集中成进程级唯一缓存：spider.py 与 room.py 原先各自缓存、各自请求抖音主页，
# 在「每个 room 独立线程 + 独立 asyncio.run 循环」下重复拉取，并放大 ReadError 重试噪声。
#
# 对外入口：
#   - get_ttwid()        : 统一读取（懒加载，并发只真正拉取一次）；
#   - warmup_ttwid()     : 启动期同步预热，后续调用直接命中；
#   - invalidate_ttwid() : 凭据被抖音拒绝时失效，三层缓存一并作废。
#
# 去重必须用 threading 锁而非 asyncio 锁：每 room 各自 asyncio.run() 循环彼此独立，
# per-loop 的 asyncio.Lock 无法跨循环协调（绑定首个循环后其余循环直接 RuntimeError）。
# pyright: reportUnreachable=none, reportImplicitStringConcatenation=none, reportUnusedCallResult=none
import asyncio
import configparser
import os
import sys
import threading
import time

import i18n

from .async_http import async_req
from .cookie_cache import DEFAULT_TTL as _CACHE_TTL_SECONDS
from .cookie_cache import fetch_cookies as _cache_fetch_cookies
from .cookie_cache import invalidate as _cache_invalidate_cookies
from .cookie_cache import invalidate_generic as _cache_invalidate_generic
from .cookie_cache import singleflight as _cache_singleflight
from .logger import logger

OptionalStr = str | None

# ttwid 的来源网址：cookie 缓存按「归一化网址 + 代理」为键，失效时需复用同一网址。
_DOUYIN_HOME_URL = "https://live.douyin.com/"


def _app_root() -> str:
    # 返回应用程序根目录，与 logger.py 同口径，用于独立定位 config.ini：
    # 源码运行取主脚本目录；冻结运行（PyInstaller）取 exe 同级目录（_internal 的父目录）。
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.realpath(sys.executable))
    return os.path.split(os.path.realpath(sys.argv[0]))[0]


# 进程级唯一缓存
_cached_ttwid: str = ""
# 获取时刻，供 TTL 判定：语义由「非空即永久返回」改为「按 TTL 判陈旧」，否则抖音
# 作废 ttwid（风控常见形态）后本进程永不重取，表现为长期「HTTP 200 + 空响应体」。
# TTL 取 cookie_cache.DEFAULT_TTL，与承载它的 singleflight 层同口径，避免两层各自过期而抖动。
_cached_ttwid_at: float = 0.0
# 上面的模块全局只是「最近一次成功写入值」的镜像（供 warmup 观测与既有用例读取），不参与
# 快路判定；真正的缓存按出口分列，键 `proxy_addr or ""`（与 singleflight key 的代理维度同写
# 法，空串=直连）。为什么必须分列：抖音 ttwid 与出口 IP 强相关，跨出口复用表现为
# 间歇「HTTP 200 + 空响应体」，且作废链会连带清掉别的出口的正常值、下一轮再抢占回来，来回抖动。
_cached_ttwid_by_proxy: dict[str, tuple[str, float]] = {}
# 本进程用过的 (singleflight key, 代理) 组合：invalidate_ttwid() 据此把下两层缓存一并
# 作废（key 含代理维度，不记录就找不到要清的那条）。
_ttwid_scopes: "set[tuple[str, OptionalStr]]" = set()
# 跨线程去重锁。网络拉取已移出临界区，本模块不再 acquire（去重由 cookie_cache.singleflight 承担）；
# 保留它是因为 tests/test_concurrency.py::test_ttwid_module_pattern 断言了其类型，**改类型即让该用例变红**。
# 必须是可重入 RLock 而非 threading.Lock：一旦被重新接线成「跨越 await 持有」，同循环的第二个协程
# 会自旋死锁（持锁协程永不恢复），RLock 把同线程重入退化为一次幂等重复拉取；也不得退回模块级
# asyncio.Lock 单例（绑定首个 await 它的循环，每房间独立循环下 RuntimeError）。
_ttwid_lock = threading.RLock()

# 配置文件中的 ttwid 键名（位于 [Cookie] 段），用户手动填写时优先于自动获取
_CONFIG_TTWID_KEY = "ttwid"
_CONFIG_SECTION = "Cookie"

# 缓存生命周期：与 cookie_cache 的默认 TTL 同值（30 分钟）。
_TTWID_TTL_SECONDS: float = float(_CACHE_TTL_SECONDS)


def _proxy_slot(proxy_addr: OptionalStr) -> str:
    # 缓存分列键：与 singleflight key 里的代理维度同一写法（None/空串都归到「直连」桶）。
    return proxy_addr or ""


def _cache_ttwid(value: str, proxy_addr: OptionalStr = None) -> str:
    # 写入按出口分列的真实缓存，并同步「最近写入值」镜像（仅供观测，理由见 _cached_ttwid_by_proxy）。
    # 值与获取时刻必须在同一入口成对设置，漏一处即退化成「永久有效」。
    global _cached_ttwid, _cached_ttwid_at
    now = time.monotonic()
    _cached_ttwid_by_proxy[_proxy_slot(proxy_addr)] = (value, now)
    _cached_ttwid = value
    _cached_ttwid_at = now
    return value


def _take_cached_ttwid(proxy_addr: OptionalStr) -> str:
    # 读取本出口的缓存值；陈旧则删除条目并返回空串（TTL 按出口各算各的）。
    #
    # 第一道 `_cached_ttwid` 判空是「整体失效开关」而非遗留的跨出口复用路径：分桶缓存没有公开的
    # clear-by-bucket 入口，外部（tests/conftest.py 逐用例重置、排障时手工置空）只会写 `_cached_ttwid = ""`；
    # 镜像为空即禁用快路，外部重置才真的生效，否则上一个用例的值会串进下一个用例。写侧唯一入口
    # _cache_ttwid() 恒为「镜像 + 分桶」成对写，故镜像非空 ⟺ 至少一个桶有值。
    if not _cached_ttwid:
        return ""
    slot = _cached_ttwid_by_proxy.get(_proxy_slot(proxy_addr))
    if not slot:
        return ""
    value, fetched_at = slot
    if (time.monotonic() - fetched_at) >= _TTWID_TTL_SECONDS:
        # 陈旧值先删再往下走，否则本层会永久短路 cookie_cache 的 30 分钟自愈。
        _cached_ttwid_by_proxy.pop(_proxy_slot(proxy_addr), None)
        return ""
    return value


def _read_config_ttwid() -> str:
    # 从 config.ini 的 [Cookie] 段读取用户手填的 ttwid，为空或缺失返回 ""。
    # 与 logger.py 一致：RawConfigParser + utf-8-sig 独立读取，不依赖 main.py 的执行顺序。
    try:
        parser = configparser.RawConfigParser()
        _ = parser.read(f"{_app_root()}/config/config.ini", encoding="utf-8-sig")
        raw = parser.get(_CONFIG_SECTION, _CONFIG_TTWID_KEY).strip()
    except configparser.NoSectionError, configparser.NoOptionError, configparser.Error:
        return ""
    except Exception:
        # 吞没即正确：手填覆盖值读不到时回落到自动获取，绝不能让录制链路在此抛错；
        # 配置损坏由 main.py 启动期读取负责报告，此处重复告警只会刷屏。
        return ""
    if not raw:
        return ""
    # 归一化：确保形如 ttwid=<value>
    return raw if raw.lower().startswith("ttwid=") else f"ttwid={raw}"


async def _fetch_ttwid(proxy_addr: OptionalStr = None) -> str:
    # 实际拉取并写入缓存，失败返回空字符串。
    # 经统一 cookie 缓存（src/cookie_cache.fetch_cookies）从抖音主页获取，同网址下的弹幕、
    # url 解析等模块直接复用，避免重复请求触发风控。
    try:
        cookies_dict = await _cache_fetch_cookies(
            url=_DOUYIN_HOME_URL,
            proxy_addr=proxy_addr,
            headers={
                "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36"
            },
            timeout=10,
            http2=False,  # 抖音对 HTTP/2 支持不稳定，常触发 ReadError('')，降级到 HTTP/1.1
            fetcher=async_req,  # 传入本模块 async_req，使单测对 src.ttwid.async_req 打桩仍生效
        )
        if isinstance(cookies_dict, dict) and cookies_dict.get("ttwid"):
            logger.debug("自动获取抖音 ttwid 成功")
            return _cache_ttwid(f"ttwid={cookies_dict['ttwid']}", proxy_addr)
    except Exception as e:
        # Windows 下 socket.timeout / httpx 超时族的 str() 可能为空串，必须带上
        # 类型名，否则只打 {e} 会得到一行空白告警，无法区分超时/DNS/证书/依赖缺失。
        logger.warning(i18n.tr("自动获取抖音 ttwid 失败: {type_name}: {e}", type_name=type(e).__name__, e=e))
    # 失败时不得回落到 `_cached_ttwid` 镜像：那等于把别的出口的值当本出口的值。
    # 返回空串，由调用方按未开播/风控处理。
    return ""


async def get_ttwid(proxy_addr: OptionalStr = None) -> str:
    # 统一读取入口。优先级：本出口缓存 > 配置文件手填 > 自动从抖音主页获取。
    # 未命中时只真正拉取一次，其余并发调用等待复用同一结果。
    #
    # 不用 `_ttwid_lock` 跨越 await：每房间独立线程 + 独立事件循环，持锁协程 await 网络（最坏
    # 10s + 重试）期间其它房间线程会在 acquire() 上同步阻塞整个事件循环，冷启动全串行卡顿；
    # 且等待者拿到锁后 owner 已失败时还会各自重发。现由 cookie_cache.singleflight 承担：临界区
    # 只做字典读写，网络在锁外，等待者经 future 复用结果（跨循环经 call_soon_threadsafe 交付）。
    # 快路按「本次调用的出口」取缓存，陈旧即丢弃并继续往下走（ + ）。
    cached = _take_cached_ttwid(proxy_addr)
    if cached:
        return cached

    # 配置优先：用户手填 ttwid 属本地确定值，不进 singleflight（无网络、无竞争必要）
    cfg = _read_config_ttwid()
    if cfg:
        _cache_ttwid(cfg, proxy_addr)
        logger.debug("使用配置文件中的 ttwid")
        # 返回 cfg 而非全局镜像：并发下镜像可能已被其它出口改写，返回它即违反「不得把别的
        # 出口的值当本出口的值」。
        return cfg

    async def _fetch() -> str:
        return await _fetch_ttwid(proxy_addr)

    key = f"douyin_ttwid|{proxy_addr or ''}"
    # 记下 (key, 代理)：invalidate_ttwid() 需要它才能定位到承载本值的那条下层缓存
    _ttwid_scopes.add((key, proxy_addr))
    got = await _cache_singleflight(key=key, factory=_fetch, timeout=10)
    if isinstance(got, str) and got:
        _cache_ttwid(got, proxy_addr)
    # 只返回本出口的值：成功时 _fetch_ttwid 已按 proxy_addr 写入，失败时为空串。
    return _take_cached_ttwid(proxy_addr)


# 显式作废进程内的 ttwid（与 spider.invalidate_bili_buvid_cache 同形）：抖音侧拒绝该凭据
# （HTTP 200 + 空 body 的风控形态、弹幕鉴权失败）时由调用方触发，下一轮 get_ttwid 重新获取，
# 不必等 TTL 自然过期。三层缓存（模块全局 / generic singleflight / 同网址 cookie 缓存）必须
# 一并清：只清上层会立刻被下层同一份旧值回填，形成「失效只生效一半」。
def invalidate_ttwid(proxy_addr: OptionalStr = None) -> None:
    # 无日志的纯清缓存动作：失效的可观测性由下一轮「自动获取抖音 ttwid 成功」的 debug 承担，
    # 避免新增无占位符的日志条目。
    global _cached_ttwid, _cached_ttwid_at
    _cached_ttwid = ""
    _cached_ttwid_at = 0.0
    # 分桶缓存必须跟镜像一起清，否则快路仍会命中已被平台拒绝的值。刻意整体清空而非只清
    # proxy_addr 桶：同一进程各桶的值很可能来自同一次主页请求（cookie_cache 会跨出口复用
    # set-cookie），逐桶保留仍会留下被拒值；代价只是各出口下一轮重拉一次，属低频路径。
    _cached_ttwid_by_proxy.clear()
    scopes = set(_ttwid_scopes)
    if proxy_addr is not None:
        scopes.add((f"douyin_ttwid|{proxy_addr or ''}", proxy_addr or None))
    for key, scope_proxy in scopes:
        _cache_invalidate_generic(key)
        _cache_invalidate_cookies(_DOUYIN_HOME_URL, scope_proxy)


def warmup_ttwid(proxy_addr: OptionalStr = None) -> None:
    # 启动期同步预热：拉取一次写入缓存，后续调用直接命中。
    # 必须在无运行中事件循环的同步上下文调用（如 main() 的启动阶段）。
    try:
        asyncio.run(get_ttwid(proxy_addr))
    except Exception as e:
        # 同 _fetch_ttwid：异常文本可能为空串，缺类型名会让「预热失败」成为无法归因的空行。
        logger.warning(i18n.tr("启动时预热 ttwid 失败: {type_name}: {e}", type_name=type(e).__name__, e=e))
