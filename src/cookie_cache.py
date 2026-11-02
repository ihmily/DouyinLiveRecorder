# -*- encoding: utf-8 -*-
# 统一 cookie 缓存模块
#
# 背景：原先各平台各自维护一份「从该网址动态获取的访客 cookie」缓存并各自请求（如 src/ttwid.py 的
# 抖音 ttwid、src/spider.py 的快手 did）。在「每个 room 独立线程 + 独立 asyncio.run 循环」的并发模型下，
# 同网址会被多个房间重复请求，触发平台风控（返回 HTTP 200 但空响应体），表现为解析静默失败。
# 故把「按网址动态获取 cookie」的缓存统一到进程内唯一一份存储：
#   - fetch_cookies(url, proxy, ...) : 统一读取入口——命中缓存直接返回；未命中则加锁只
#                                     拉取一次，其余并发调用等待复用同一份结果。
#   - get_cached(url, proxy)        : 同步只读查询（不触发网络请求），供其他模块复用。
#   - get_cookie_str(url, proxy, ...) : 同上但返回拼接好的 "k=v; k=v" 字符串。
#   - invalidate(url, proxy) / clear() : 失效与清空，供调试或强制刷新。
#
# ── 存储结构 ──
#   _cookie_cache: dict[str, tuple[dict[str, str], float]]，key = _make_key(url, proxy)
#   （归一化网址 + 代理地址），value = (原始 cookie 字典, 失效时刻 monotonic)。
#   存的是网址下发的原始访客 cookie 字典，不做平台特定裁剪，由调用方按需取字段
#   （如 ttwid 取 "ttwid"，快手取 "did"/"didv"）。
#   失效时刻在写入时由该次 ttl 折算，所有读取方只判 now < 失效时刻（L-07）——早期存的是写入时刻、
#   由各读取方拿自己手上的 ttl 去减，同一条目会因读取方不同而有不同寿命。
#
# ── 失效策略 ──
#   - TTL：DEFAULT_TTL = 30 * 60，与 src/room.py 的 sec_uid 缓存保持一致（录制进程可能连续运行
#     数天），调用方可按需覆盖；到点即失效、下次访问重新拉取。
#   - 失败不缓存：拉取异常或返回空字典时一律不写入，下次访问会重试，避免把「瞬时失败」固化成长期空值。
#   - 世代号（MI-12）：invalidate() / clear() / invalidate_generic() 递增 _cache_generation，在途拉取者
#     写回前比对，期间发生过失效就丢弃本次结果——否则失效后立即 fetch_cookies() 若命中在途登记，又会
#     拿到那份**已被判定过期**的 cookie，自愈链要直到 TTL（默认 30 分钟）自然过期为止。
#   - 在途登记的孤儿回收（L-06）：登记项记下「拉取者所在事件循环」，失效与新抢到拉取权的协程都**只摘
#     owner 循环已关闭**的登记（拉取线程被硬杀 / 拉取任务被丢弃——它永远无人交付，实测会让同 key 之后
#     每次调用都白等一轮 timeout+余量再拿空结果），并就地以空结果唤醒挂在它上面的等待者。拉取者仍
#     活着的登记一律不得摘：那等于把它的等待者判空，还会让同 key 并发重发一次请求。「失效后旧值不得
#     复活」由上面的世代号负责，与本条分工不同、不可互相替代。
#   - 并发去重（singleflight）：threading.Lock 只保护「缓存字典 + 在途登记表」的同步读写，绝不在锁内
#     await——锁跨 await 时，同循环的并发协程属同一线程、全部可重入该锁，互斥完全失效（那正是要消除
#     的风控触发源）。抢到拉取权的协程负责拉取，等待者（同循环或跨循环）登记 future 复用同一份结果；
#     跨循环交付经 loop.call_soon_threadsafe 回写（future 非线程安全，禁止跨线程直接 set_result）。
#
# ── 跨模块调用方式 ──
#   from .cookie_cache import fetch_cookies, get_cached, get_cookie_str
#   1) 动态获取并复用：cookies = await fetch_cookies("https://live.douyin.com/", proxy_addr=proxy)
#   2) 仅复用不拉取：   cached  = get_cached("https://live.douyin.com/", proxy_addr=proxy)
#   3) 取拼接字符串：   s       = await get_cookie_str("https://live.kuaishou.com/", proxy_addr=proxy)
# pyright: reportImplicitStringConcatenation=none, reportUnknownArgumentType=none, reportUnknownMemberType=none, reportUnknownVariableType=none
import asyncio
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

import i18n

from . import utils
from .async_http import async_req
from .logger import logger

OptionalStr = str | None
# 等待者条目：(等待者所在事件循环, 等待者 future)。future 的值类型两份登记表不同
# （cookie 侧是 dict[str, str]、通用侧是任意对象），统一放宽为 Any 以便共用回收/唤醒助手。
_Waiter = tuple[asyncio.AbstractEventLoop, asyncio.Future[Any]]

# 进程级唯一 cookie 缓存：key -> (cookie_dict, 失效时刻 monotonic)
_cookie_cache: dict[str, tuple[dict[str, str], float]] = {}


# 一次在途拉取的登记项。
#   owner_loop：抢到拉取权的协程所在的事件循环——判「拉取者还在不在」的唯一凭据
#     （拉取线程被硬杀 / 任务被丢弃时必为 is_closed()，可据此安全回收，绝不误伤仍活着的拉取者）。
#   waiters：挂在这次拉取上的等待者，拉取结束时逐个交付。
@dataclass
class _Inflight:
    owner_loop: asyncio.AbstractEventLoop
    waiters: list[_Waiter] = field(default_factory=list)


# 在途拉取登记表：key 在表中即表示某协程正在拉取该网址
_inflight: dict[str, _Inflight] = {}
# 去重锁：只保护 _cookie_cache 与 _inflight 的同步读写（临界区内绝无 await）
_cache_lock = threading.Lock()

# MI-12：缓存世代号，invalidate() / clear() / invalidate_generic() 递增它，在途拉取者写回前
# 比对，世代变了就丢弃本次结果（避免「刚失效就被在途请求回填」）。
# fetch_cookies 与 singleflight 两层共用同一个计数器，语义必须保持一致。
_cache_generation = 0
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


def _is_orphan(rec: _Inflight) -> bool:
    # 拉取者所在事件循环已关闭 ⇒ 这次拉取永远不会有人交付，登记是孤儿（L-06）。
    # is_closed() 只读一个标志位，跨线程调用安全；按等待时长判死会误伤「活着但慢」的拉取者。
    return rec.owner_loop.is_closed()


def _wake_waiters(pending: list[_Waiter], value: Any) -> None:
    # 从**同步**上下文唤醒等待者：invalidate()/clear() 常在无运行循环的线程里被调用
    # （ttwid.invalidate_ttwid 的拒绝链、tests/conftest 的逐用例清理），不能复用 _deliver——
    # 它第一行就 asyncio.get_running_loop()，无运行循环时会抛 RuntimeError。
    # 一律走 call_soon_threadsafe（同循环线程调用同样合法）；等待者循环已关闭时抛 RuntimeError，
    # 那个 future 再没人读，丢弃即可。
    for waiter_loop, waiter_fut in pending:
        _wake_one(waiter_loop, waiter_fut, value)


def _wake_one(waiter_loop: asyncio.AbstractEventLoop, waiter_fut: asyncio.Future[Any], value: Any) -> None:
    # 单独成函数而非在循环里造闭包：闭包必须按「本次等待者」绑定，写成循环内引用循环变量
    # 会晚绑定成最后一个等待者。
    def _set() -> None:
        if not waiter_fut.done():
            waiter_fut.set_result(value)

    try:
        waiter_loop.call_soon_threadsafe(_set)
    except RuntimeError:
        pass


def _reap_orphans_locked(registry: dict[str, _Inflight], only_key: OptionalStr) -> list[_Waiter]:
    # 必须在持有 _cache_lock 时调用（只做字典读写，无 await）。
    # 摘除孤儿登记并返回挂在上面的等待者，交调用方在**锁外**唤醒。
    # only_key 为 None 表示整表（clear/无参 invalidate 的语义），否则只处理这一个 key。
    stranded: list[_Waiter] = []
    for key in (list(registry) if only_key is None else [only_key]):
        rec = registry.get(key)
        if rec is not None and _is_orphan(rec):
            registry.pop(key, None)
            stranded.extend(rec.waiters)
    return stranded


def _release_inflight(registry: dict[str, _Inflight], key: str, mine: _Inflight) -> list[_Waiter]:
    # 拉取者收尾：归还登记位，并返回本次需要交付的等待者。
    # **只摘自己那一格**（按 _Inflight 对象身份判定）：无条件 pop(key) 在「invalidate() 已把本格
    # 摘走、同 key 又已由新的拉取者占位」的交错下会连带摘掉别人的登记位——那份拉取还在路上，
    # 它的等待者就再没人交付，只能等满 timeout 拿空结果。
    # 返回的始终是自己的 waiters：即使登记位已被回收，挂在自己这次拉取上的等待者仍应拿到结果。
    with _cache_lock:
        if registry.get(key) is mine:
            registry.pop(key, None)
        return list(mine.waiters)


def get_cached(url: str, proxy_addr: OptionalStr = None) -> dict[str, str] | None:
    # 同步只读查询：命中且未过期返回 cookie 字典，否则返回 None（不触发网络请求）。
    # 判过期只认条目里记下的失效时刻，不硬编码 DEFAULT_TTL——否则写入方用自定义 ttl 时，
    # 两个读取方会对同一条目给出相反结论（L-07）。
    entry = _get_cached_entry(_make_key(url, proxy_addr))
    if entry is None:
        return None
    cookies, expire_ts = entry
    if time.monotonic() >= expire_ts:
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
    # fetcher：实际发起 HTTP 请求的可调用对象，默认用本模块的 async_req。**调用方应传入自身
    # 命名空间下的 async_req**（如 ttwid / spider 模块导入的那一个），否则单测对
    # "src.<mod>.async_req" 打的桩拦不住这里的请求——各模块导入的是同一函数对象，但分属不同
    # 命名空间。这是一条测试设计契约，不是可选优化。签名需兼容
    # (url, *, proxy_addr, headers, return_cookies, timeout, http2) -> dict。
    #
    # ttl：只决定「本次写入的条目能活多久」，写入时折成绝对失效时刻存进条目；两个读取方一律与该
    # 时刻比对（L-07）。故「想强制重新拉取」只能走 invalidate()，不能靠传更小的 ttl。
    key = _make_key(url, proxy_addr)
    now = time.monotonic()
    do_fetch: Callable[..., Any] = fetcher if callable(fetcher) else async_req

    # 快速路径（无锁）：绝大多数调用命中此处
    entry = _get_cached_entry(key)
    if entry is not None and now < entry[1]:
        return entry[0]

    # 未命中：锁内二次检查缓存（锁内绝无 await）。key 已在途则登记为等待者复用同一份结果，
    # 否则本协程登记为拉取者
    loop = asyncio.get_running_loop()
    waiter: asyncio.Future[dict[str, str]] | None = None
    # 本次拉取独占的登记项；_Inflight 对象的身份就是「这条登记归我」的凭证（见收尾的摘除守卫）
    mine = _Inflight(owner_loop=loop)
    stranded: list[_Waiter] = []
    with _cache_lock:
        entry = _cookie_cache.get(key)
        if entry is not None and time.monotonic() < entry[1]:
            return entry[0]
        rec = _inflight.get(key)
        if rec is not None and _is_orphan(rec):
            # L-06：拉取者所在的循环已经关了 ⇒ 它永远不会有人交付。挂在它上面的等待者只能白等
            # 一轮 timeout，而这条死登记还会把同 key 之后每一次调用都拖进同一个结局
            # （实测：孤儿登记令 fetch_cookies 恒返回 {}，直到进程重启）。就地摘掉并接管。
            _inflight.pop(key, None)
            stranded = rec.waiters
            rec = None
        if rec is not None:
            waiter = loop.create_future()
            rec.waiters.append((loop, waiter))
        else:
            _inflight[key] = mine  # 占位：本协程即拉取者，登记项留给后续等待者挂入
    if stranded:
        _wake_waiters(stranded, {})
    if waiter is not None:
        try:
            return await asyncio.wait_for(waiter, timeout + _INFLIGHT_WAIT_MARGIN)
        except TimeoutError:
            # 拉取者所在线程异常退出（循环被硬杀等极端场景）：超时返回空结果，
            # 失败不缓存，下次访问重新走拉取
            logger.warning(
                i18n.tr(
                    "等待其它线程的 cookie 拉取超时，返回空结果: {masked_key}",
                    masked_key=utils.mask_credentials(key),
                )
            )
            return {}

    # 本协程为拉取者：异常/空结果同样要交付等待者（失败语义与单协程路径一致）
    with _cache_lock:
        _gen_before = _cache_generation
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
            # 失败不缓存、下次重试；带类型 + URL 便于排查（Windows 下 e 的 str() 可能为空）。
            # WD-01：异常文本常内嵌完整请求 URL（含签名/鉴权查询串），必须一并脱敏
            logger.warning(
                i18n.tr(
                    "动态获取 cookie 失败: {url} - {type_name}: {e}",
                    url=utils.mask_credentials(url),
                    type_name=type(e).__name__,
                    e=utils.mask_credentials(str(e)),
                )
            )
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
        pending = _release_inflight(_inflight, key, mine)
        for waiter_loop, waiter_fut in pending:
            _deliver(waiter_loop, waiter_fut, {})
        raise
    # 仅缓存非空结果（空结果视为失败、不固化，下次可重试）；写回前比对世代号（MI-12），
    # 期间被 invalidate()/clear() 失效过就丢弃本次结果
    if cookies:
        with _cache_lock:
            if _gen_before == _cache_generation:
                # L-07：把本次 ttl 折成绝对失效时刻存进条目，读取方不再各自拿 ttl 去减
                _cookie_cache[key] = (cookies, time.monotonic() + ttl)
        logger.debug(
            i18n.tr(
                "动态获取 cookie 成功并缓存: {masked_key}",
                masked_key=utils.mask_credentials(key),
            )
        )
    pending = _release_inflight(_inflight, key, mine)
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


# 通用 singleflight 缓存（H-2）：与 fetch_cookies 同范式，但缓存值是任意对象而非 cookie dict，
# 供「一次性拉取、长期复用」的凭据类数据（Twitch Client-Id、B站 buvid3、快手 did、抖音 ttwid）复用。
# 这些拉取点原先在「threading.Lock 临界区内 await 网络请求」：本项目每房间一线程一循环，锁内 await
# 期间房间 B 执行到 with 会同步阻塞其整个事件循环线程；B站处为不可重入锁，同循环两协程并发进入即
# 互等死锁。本实现把「临界区只做字典读写、网络请求移到锁外」固化成公共实现。
_generic_cache: dict[str, tuple[Any, float]] = {}
_generic_inflight: dict[str, _Inflight] = {}


def _deliver_generic(waiter_loop: asyncio.AbstractEventLoop, fut: asyncio.Future[Any], value: Any) -> None:
    # 与 _deliver 同语义，仅类型放宽为 Any（见 _deliver 的跨循环交付说明）
    def _set() -> None:
        if not fut.done():
            fut.set_result(value)

    if waiter_loop is asyncio.get_running_loop():
        _set()
        return
    try:
        waiter_loop.call_soon_threadsafe(_set)
    except RuntimeError:
        pass


async def singleflight(
    key: str,
    factory: Callable[[], Any],
    *,
    ttl: float = DEFAULT_TTL,
    timeout: float = 10.0,
    cache_falsy: bool = False,
) -> Any:
    # 通用 singleflight：同 key 的并发调用只执行一次 factory，其余等待复用同一结果。
    #
    # - key：缓存键（调用方自行保证不同用途不碰撞，建议带前缀，如 "twitch_client_id|proxy"）
    # - factory：无参协程工厂（Callable[[], Awaitable[Any]]）；被调用于锁外，故可安全 await
    # - ttl：缓存秒数，写入时折成条目的绝对失效时刻，读取一律按该时刻判过期（L-07，与
    #   fetch_cookies / get_cached 同口径）；cache_falsy=False（默认）时空结果不缓存（视为失败，下次重试）
    # - timeout：等待其它协程在途拉取的超时（秒），超时返回 None 而非永久挂起
    #
    # 返回值语义：命中缓存返回缓存值；本协程为拉取者返回 factory 结果；
    # 等待者返回拉取者结果（拉取者异常/取消时返回 None）。
    now = time.monotonic()

    # 快速路径（MI-13：纳入 _cache_lock）。原实现无锁读，与 invalidate_generic / clear 的持锁写
    # 不互斥，而本模块其余所有字典访问都在锁内。临界区只有一次 dict.get、无 await。
    with _cache_lock:
        entry = _generic_cache.get(key)
        if entry is not None and now < entry[1]:
            return entry[0]

    loop = asyncio.get_running_loop()
    waiter: asyncio.Future[Any] | None = None
    mine = _Inflight(owner_loop=loop)
    stranded: list[_Waiter] = []
    with _cache_lock:
        entry = _generic_cache.get(key)
        if entry is not None and time.monotonic() < entry[1]:
            return entry[0]
        rec = _generic_inflight.get(key)
        if rec is not None and _is_orphan(rec):
            # L-06：同 fetch_cookies——拉取者所在的循环已关闭 ⇒ 这条登记永远无人交付，
            # 摘掉并接管，别把同 key 之后的每次调用都拖成「等待超时→None」。
            _generic_inflight.pop(key, None)
            stranded = rec.waiters
            rec = None
        if rec is not None:
            waiter = loop.create_future()
            rec.waiters.append((loop, waiter))
        else:
            _generic_inflight[key] = mine

    if stranded:
        _wake_waiters(stranded, None)

    if waiter is not None:
        try:
            return await asyncio.wait_for(waiter, timeout + _INFLIGHT_WAIT_MARGIN)
        except TimeoutError:
            logger.warning(
                i18n.tr(
                    "等待其它线程的凭据拉取超时，返回空结果: {masked_key}",
                    masked_key=utils.mask_credentials(key),
                )
            )
            return None

    # 本协程为拉取者：锁外执行 factory（临界区内绝无 await），写回前比对世代号——与 fetch_cookies
    # 共用同一个 _cache_generation，两层必须同口径：否则「凭据被平台拒绝 → invalidate_generic(key)」
    # 与「同 key 在途拉取」并发时，已被判定作废的那份结果（如 B 站软拒绝的随机 UUID buvid3）会在
    # 拉取结束后重新固化进缓存、直到 TTL 自然过期，自愈链在 singleflight 侧断开（MID-40）。
    with _cache_lock:
        _gen_before = _cache_generation
    try:
        try:
            value = await factory()
        except Exception as e:
            # 异常文本常内嵌带签名/鉴权查询串的完整 URL（factory 里就是 async_req/sync_req），
            # 与 fetch_cookies 同口径一律过 mask_credentials——logs/ 按 rotation 保留多份，
            # 原文入日志等于凭据长期落盘。{type_name} 保持不脱敏（Windows 下 str(e) 可能为空，
            # 缺类型名就只剩一条空白告警，无法归因）。
            logger.warning(
                i18n.tr(
                    "凭据拉取失败: {masked_key} - {type_name}: {e}",
                    masked_key=utils.mask_credentials(key),
                    type_name=type(e).__name__,
                    e=utils.mask_credentials(str(e)),
                )
            )
            value = None
    except BaseException:
        # 本协程被取消：摘除登记并给等待者交付 None，避免其空等超时
        pending = _release_inflight(_generic_inflight, key, mine)
        for waiter_loop, waiter_fut in pending:
            _deliver_generic(waiter_loop, waiter_fut, None)
        raise

    if value or cache_falsy:
        with _cache_lock:
            # 世代变更（期间被 invalidate_generic / clear / invalidate 作废）则丢弃本次结果、
            # 不回填缓存——与 fetch_cookies 的 MI-12 口径一致（那里同样静默丢弃，等待者仍拿
            # 到本次值，但下一轮会重新拉取，从而让「被拒凭据」不被固化 30 分钟）。
            if _gen_before == _cache_generation:
                # L-07：ttl 在写入时折成绝对失效时刻（与 cookie 侧同口径）
                _generic_cache[key] = (value, time.monotonic() + ttl)
    pending = _release_inflight(_generic_inflight, key, mine)
    for waiter_loop, waiter_fut in pending:
        _deliver_generic(waiter_loop, waiter_fut, value)
    return value


def invalidate_generic(key: str | None = None) -> None:
    # 失效通用缓存（key 为 None 时清空全部）。供调试或凭据失效后强制刷新。
    global _cache_generation
    with _cache_lock:
        _cache_generation += 1
        # L-06：与 cookie 侧同形——只回收「拉取者所在循环已关闭」的登记，并在锁外把挂在上面的
        # 等待者立即唤醒（交付 None，等价于它们本会走到的超时结局，只是不再白等）。
        stranded = _reap_orphans_locked(_generic_inflight, key)
        if key is None:
            _generic_cache.clear()
        else:
            _generic_cache.pop(key, None)
    _wake_waiters(stranded, None)


def invalidate(url: str | None = None, proxy_addr: OptionalStr = None) -> None:
    # 失效指定网址（或整份）缓存。url 为 None 时清空全部。
    global _cache_generation
    with _cache_lock:
        # MI-12：递增世代，令在途拉取者放弃回填
        _cache_generation += 1
        # L-06：同步清理在途登记表。原先只清结果字典，于是拉取线程被硬杀留下的孤儿 key 永不自愈
        # （实测：该 key 之后每次 fetch_cookies 都白等 timeout 再拿 {}），而「主动作废凭据」正是
        # 唯一的重置入口。仍活着的拉取者的登记一律不动——摘它会连带丢掉它已挂上的等待者，
        # 并让同 key 并发重发请求。世代比对（MI-12）管「旧值不得复活」，本条管「登记者的存在性」。
        if url is None:
            stranded = _reap_orphans_locked(_inflight, None)
            _cookie_cache.clear()
        else:
            ck = _make_key(url, proxy_addr)
            stranded = _reap_orphans_locked(_inflight, ck)
            _cookie_cache.pop(ck, None)
    _wake_waiters(stranded, {})


def clear() -> None:
    # 清空全部缓存（调试/测试用）：cookie 缓存与通用 singleflight 缓存一并清。
    # 只清 cookie 侧会让单测间残留上一条用例的凭据（如 ttwid=fetched），下一条用例命中旧缓存
    # 而非本次打桩值——表现为「测试莫名失败且只在整包运行时出现」。
    global _cache_generation
    with _cache_lock:
        _cache_generation += 1
        # L-06：两张在途登记表一并回收（同样只回收已失主的登记）。tests/conftest 的
        # autouse _clean_credential_caches 每条用例前后都调本函数，孤儿登记若不清掉，
        # 上一条用例留下的死 key 会让下一条用例的 fetch 直接退化成「超时→空结果」。
        stranded_cookie = _reap_orphans_locked(_inflight, None)
        stranded_generic = _reap_orphans_locked(_generic_inflight, None)
        _cookie_cache.clear()
        _generic_cache.clear()
    _wake_waiters(stranded_cookie, {})
    _wake_waiters(stranded_generic, None)
