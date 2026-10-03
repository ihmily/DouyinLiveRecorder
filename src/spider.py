# -*- encoding: utf-8 -*-
import asyncio
import hashlib
import json
import os
import random
import re
import threading
import time
import urllib.parse
import uuid
from operator import itemgetter
from typing import Optional, cast

import httpx

import i18n

# 抖音直播录制工具 - 爬虫模块
#
# 平台爬虫核心：负责 60+ 直播平台的房间信息解析与真实流地址提取。
# 分层（自顶向下）：
#   - 通用工具与凭据缓存：_safe_extract_id / _get_str_response / _loads_dict /
#     _ensure_ttwid / _ensure_kuaishou_did / _ensure_twitch_client_id /
#     get_bilibili_danmaku_info 的 buvid 链——均为「首次获取、进程内缓存、
#     跨线程锁去重」，避免每轮重复请求触发平台风控。
#   - 各平台解析函数：get_<platform>_stream_data / _stream_url，逐一对应一个平台；
#     输入直播间 URL，输出统一结构 {anchor_name, is_live, m3u8_url/flv_url/
#     record_url/play_url_list, ...}。函数名即平台分发表（main.py 按平台名反射调用）。
#   - 签名/加密：抖音 web/enter + HTML 回退（get_douyin_web_stream_data 内）、
#     B站 WBI（_sign_wbi + _MIXIN_KEY_ENC_TAB）、斗鱼 websec 签名（get_token_js）、
#     网易/PopkonTV AES-RSA（get_looklive_secret_data）、LiveMe/嗨秀/咪咕的 JS 签名
#     （execjs 调用 javascript/ 下脚本）。
# 与仓库其它模块的关系：
#   - main.py：按平台名分发调用本模块函数并驱动监控主循环，不直接解析平台接口。
#   - stream_select.py：本模块只负责「取地址」；地址可达性校验与候选排序由
#     select_source_url / _validate_stream_url 负责（含探针退避、同 host 节流、HLS/FLV 优先级）。
#   - stream.py：消费本模块返回的地址，启动 ffmpeg 录制。
#   - platforms/：另有若干平台的独立解析；本文件覆盖主流 60+ 平台。
#   - javascript/（JS_SCRIPT_PATH）：liveme.js / haixiu.js / migu.js 等签名脚本，
#     由 execjs（优先）或 PyExecJS 调用；node 调用失败统一转 ProgramError 交上层处理。
# 设计取舍与坑位：
#   - 全部解析函数为 async，统一经 async_req（src/async_http）发请求，便于代理/超时/
#     重试集中管理；不要在此直接 import httpx 发同步请求（弹幕等少数路径除外）。
#   - 平台接口极易风控：空响应体（200+空 body）、-352、-3001/-3002/-3004 等错误码多为
#     风控或登录态缺失，函数内已尽量带「重试一次再定罪」与回退，调用方需透传 cookies/proxy。
#   - 本文件使用 Python 3.14 的 PEP 758 异常语法 `except A, B:`（不带括号），这是语法特性
#     而非笔误；两种写法 black 均接受，本项目统一写无括号（约定见 AGENTS.md「代码风格」章节）。
#     唯一例外：需要 as 绑定时必须回退为加括号写法——无括号写法配 as 是语法错误。
#     [历史注] 旧版本条称「加括号会破坏 3.14 语义、即违反 black 门禁」，2026-09-17 实测推翻。
#   - 严格类型检查（pyright）在此对动态 JSON 放宽，见下列 report* 指令。

# 爬虫模块大量解析动态 JSON（json.loads 返回 Any、嵌套异构结构），
# 严格模式下的 reportUnknown* 等规则在此类代码上只会产生噪声，
# 故对本文件放宽相关检查，仅保留其余基础类型检查。
# pyright: reportUnknownVariableType=none, reportUnknownParameterType=none, reportUnknownArgumentType=none, reportUnknownMemberType=none, reportUnknownLambdaType=none, reportMissingTypeArgument=none, reportMissingParameterType=none, reportIndexIssue=none, reportOperatorIssue=none, reportImplicitStringConcatenation=none, reportUnnecessaryIsInstance=none, reportUnusedCallResult=none, reportArgumentType=none, reportReturnType=none


# 优先使用 exejs（PyExecJS 的活跃维护继任者），未安装时回退到 PyExecJS
try:
    import exejs as execjs

    ProgramError = execjs.ExejsProgramError
except ImportError:
    import execjs  # type: ignore[no-redef]
    from execjs import ProgramError  # type: ignore[no-redef]

from . import JS_SCRIPT_PATH, http_config, utils, web_config
from .async_http import async_req
from .config_bool import parse_config_bool
from .cookie_cache import DEFAULT_TTL as _CREDENTIAL_TTL
from .cookie_cache import fetch_cookies as _cache_fetch_cookies
from .cookie_cache import invalidate_generic as _cache_invalidate_generic
from .cookie_cache import singleflight as _cache_singleflight
from .logger import logger, script_path
from .room import UnsupportedUrlError, get_sec_user_id, get_unique_id, is_user_homepage_url
from .ttwid import get_ttwid as _shared_get_ttwid
from .utils import generate_random_string, trace_error_decorator, trace_error_decorator_or_none

OptionalStr = str | None
OptionalDict = dict[str, str] | None
# 花椒接口返回的异构 dict（含 is_live 布尔值），值类型需覆盖 str | bool
OptionalStreamDict = dict[str, str | bool] | None

# 缓存自动获取的 ttwid，避免重复请求主页（已委托给共享 ttwid.py 模块，保留变量兼容旧引用）
_cached_ttwid: str = ""

# 模块级预编译正则：原先在解析函数内每次调用都 re.compile（m3u8 带宽提取、抖音 HEVC FLV
# 提取），平台解析每房间每轮多次触发。预编译后省去重复编译，匹配语义不变。
_BANDWIDTH_PATTERN = re.compile(r"BANDWIDTH=(\d+)")
_DOUYIN_HEVC_FLV_PATTERN = re.compile(r'(https?://[^\s"\']*stream-\d{10,}(?!_[a-z0-9]+)\.flv(?:[^"\']|\\u0026)+)')

# WD-17：PopkonTV 应用级固定 API 凭据（非用户私人凭据，嵌入于其客户端、无法从主页动态获取）。
# 原先同一串 64 字符凭据以 `Basic` 与 `Client` 两种前缀**分别写死在两个函数里**，
# 任一处更新都会漏掉另一处（本仓已多次出现此类「改一处漏 N 处」），
# 表现为「登录 OK 但取流 401」或反之。收敛为单一常量供两处引用。
# 轮换方式：与 _read_haixiu_token_override 同理支持环境变量覆盖，无需改代码即可替换。
_POPKONTV_APP_CREDENTIAL = "FpAhe6mh8Qtz116OENBmRddbYVirNKasktdXQiuHfm88zRaFydTsFy63tzkdZY0u"


def _popkontv_credential() -> str:
    # 读取 PopkonTV 应用凭据：优先环境变量覆盖（平台轮换时无需改代码），否则用内置缺省值
    return os.environ.get("POPKONTV_APP_CREDENTIAL", "").strip() or _POPKONTV_APP_CREDENTIAL


# MI-16：Shopee 站点后缀解析的唯一实现。
# 取「去掉首段后的完整 TLD」：live.shopee.co.id → "co.id"（rsplit 取最后一段会得到
# "id"，拼出 live.shopee.id 这样的无效域名）。解析异常时回退 "com"（Shopee 主站）。
# SEV-06 修复（2026-09-20）：原实现漏了「先剥 live. 首段」这一步——对真实路由形态
# live.shopee.sg，split(".", 1)[-1] 得到 "shopee.sg"，拼出 https://live.shopee.shopee.sg
# 这样的非法 host，请求必失败 → 装饰器兜成未开播，即所有可路由的 Shopee 链接永久解析失败。
# 唯一不命中的输入（shopee.co.id/live 无 live. 前缀）恰好不被 main.py 的 "live.shopee" 分发命中。
# S-1（2026-09-29，见 docs/worklog/CODE_REVIEW_2026-09-29_2.md）：改为基于 urlparse().hostname 取 host。
# 原 `url.split("/")[2]` 拿的是**整个 authority**（userinfo + host + 端口），于是
# https://live.shopee.sg@127.0.0.1/ 切出来的「host」长得像白名单，而 httpx 真正连的是 127.0.0.1；
# hostname 属性按 RFC 语义剥掉 userinfo 与端口，与 _shopee_is_allowed_host 取的是**同一个** host——
# 两道判据必须看同一个取值，否则会出现「校验 A 主机、连接 B 主机」的错位（这是本项漏洞的根形态）。
def _shopee_host_suffix(url: str) -> str:
    try:
        host = (urllib.parse.urlparse(url).hostname or "").lower()
    except ValueError:
        # 畸形 authority（如 http://[::1 这类非法 IPv6 字面量）：与旧实现的 IndexError 分支同口径回 "com"
        return "com"
    if not host:
        return "com"
    # 剥掉 live. 子域首段后再取 shopee 之后的完整后缀（co.id / com.my / sg 均正确）
    host = re.sub(r"^live\.", "", host)
    parts = host.split(".", maxsplit=1)
    return parts[-1] if len(parts) > 1 and parts[-1] else "com"


# S-1（2026-09-29）：镜像同文件小红书 SEV-2214（见 _XHS_ALLOWED_HOST_SUFFIXES / _xhs_is_allowed_host）
# 的定稿实现。Shopee 短链（.shp.ee 等）解出的落地页由**响应**决定，而后续三次请求
# （ongoing / replay_list / session）都复用同一份含 Cookie 的 headers（调用方经 [Cookie] shopee_cookie
# 透传登录态）。此前对落地页零 host 校验 → 一条恶意分享链接即可把用户 Shopee Cookie 递送到任意
# http(s) host，并把 api_host 指向内网/回环/云元数据（SSRF）。
# 白名单取 Shopee 各官方站点的**可注册域**（含两段式 TLD）+ 官方短链宿主 shp.ee：
# 必须逐段枚举，不能写成「含 .shopee. 即放行」——live.shopee.evil.com 是 evil.com 的子域，
# 攻击者握有其 DNS，字面看着像官方域但连接目标完全由他控制。
# 新增市场时在此追加一条即可（追加后 host_suffix 的取值才会被第三道闸放行）。
_SHOPEE_ALLOWED_HOST_SUFFIXES = (
    "shopee.sg",
    "shopee.com",
    "shopee.co.id",
    "shopee.com.my",
    "shopee.com.ph",
    "shopee.co.th",
    "shopee.vn",
    "shopee.com.br",
    "shopee.mx",
    "shopee.cl",
    "shopee.tw",
    "shopee.fr",
    "shopee.es",
    "shopee.pl",
    "shp.ee",
)


def _shopee_is_allowed_host(url: str) -> bool:
    # 落地页/接口 host 是否落在 Shopee 域族内。用「精确等于或 . 后缀」判定，防 evil-shopee.sg /
    # shopee.sg.evil.com 这类后缀伪装（裸 endswith 会把 notshopee.sg 也放行）——与小红书同判据。
    # 额外显式拒绝 userinfo（netloc 含 @）：urlparse 把 https://live.shopee.sg@127.0.0.1/ 的
    # hostname 解成 @ **之后**的 127.0.0.1，真实连接目标是回环而非白名单域，故「hostname 看着像
    # 官方域」在这种输入上不成立，必须整条拒掉。
    try:
        parsed = urllib.parse.urlparse(url)
    except ValueError:
        return False
    if "@" in parsed.netloc:
        return False
    host = (parsed.hostname or "").lower()
    if not host:
        return False
    return any(host == suffix or host.endswith("." + suffix) for suffix in _SHOPEE_ALLOWED_HOST_SUFFIXES)


def _safe_extract_id(url: str, default: str = "") -> str:
    # 从 URL 中安全提取路径 ID（避免 rsplit 越界）
    # 无 "/" 的非法 URL 返回 default（约定为 ""），调用方据此识别房间标识缺失、转主页解析兜底，
    # 故 default 必须可区分「未取到」与「取到空串」两种语义。
    path = url.split("?")[0].rstrip("/")
    parts = path.rsplit("/", maxsplit=1)
    return parts[1] if len(parts) > 1 else default


async def _ensure_ttwid(proxy_addr: OptionalStr = None) -> str:
    # 委托给共享 ttwid.py 模块（带 threading.Lock 跨线程去重），
    # 解决多线程并发时重复拉取 ttwid 触发风控的问题
    global _cached_ttwid
    result = await _shared_get_ttwid(proxy_addr)
    _cached_ttwid = result  # 同步本地缓存，兼容可能的外部引用
    return result


# 各平台自动获取凭据的缓存，避免每次请求都重新获取
# MID-33 修复（2026-09-20）：以下两组「模块全局非空即永久返回」的凭据缓存补充了
# 写入时间戳与 TTL 判定（对齐 cookie_cache.DEFAULT_TTL 与 src/room.py 的 sec_uid 缓存——
# 后者是全仓唯一按 TTL 判定的正确实现）。原实现对平台侧作废凭据（快手风控重置 did、
# Twitch 轮换 Client-Id）永不重试，直到进程重启；现按 TTL 过期后重取，并提供
# invalidate_* 钩子供「凭据被平台拒绝」时主动失效（镜像 invalidate_bili_buvid_cache）。
# ts==0.0 且值非空仅可能来自测试/外部直接注入全局（生产写入点恒与 ts 同点赋值），
# 此时按有效处理、与旧行为一致。
_cached_kuaishou_did: str = ""
_cached_kuaishou_did_ts: float = 0.0
# 记录当前缓存值产生时使用的代理上下文：generic singleflight 键含 proxy，
# 失效钩子需据此清对正确的通用缓存键
_cached_kuaishou_did_proxy: str = ""
_cached_twitch_client_id: str = ""
_cached_twitch_client_id_ts: float = 0.0
_cached_twitch_client_id_proxy: str = ""
# 凭据获取的互斥锁 + 二次检查：多房间线程并发首轮请求时只拉取一次，
# 避免重复打平台接口（触发风控）与凭据互相覆盖
_kuaishou_did_lock = threading.Lock()
_twitch_client_id_lock = threading.Lock()

# Twitch Web 端统一 UA（MID-50b）：主页 Client-Id 提取、GQL、usher 三处请求共用一份，
# 与 AGENTS「UA 双端一字不差 / 全库统一基准（Firefox/148）」一致。browser_version 由同一
# 常量派生——usher 查询参数原先写死 124.0 与 UA 的 148 自相矛盾（风控按不一致指纹识别）。
_TWITCH_WEB_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:148.0) Gecko/20100101 Firefox/148.0"
_TWITCH_BROWSER_VERSION = _TWITCH_WEB_UA.split("rv:", 1)[-1].split(")", 1)[0]  # -> "148.0"


def invalidate_kuaishou_did_cache(proxy_addr: OptionalStr = None) -> None:
    # 使进程内快手 did 缓存失效（MID-33）：平台侧作废 did 时由调用方主动失效，
    # 同时清 cookie_cache 通用缓存中本凭据的 singleflight 键（TTL 30 分钟，
    # 只清模块全局会被通用缓存继续喂回同一份被拒值——与 bili buvid 同型问题）。
    global _cached_kuaishou_did, _cached_kuaishou_did_ts, _cached_kuaishou_did_proxy
    with _kuaishou_did_lock:
        _cached_kuaishou_did = ""
        _cached_kuaishou_did_ts = 0.0
        recorded = _cached_kuaishou_did_proxy
        _cached_kuaishou_did_proxy = ""
    keys = {recorded}
    if proxy_addr is not None:
        keys.add(proxy_addr or "")
    for k in keys:
        _cache_invalidate_generic(f"kuaishou_did|{k}")


def invalidate_twitch_client_id_cache(proxy_addr: OptionalStr = None) -> None:
    # 使进程内 Twitch Client-Id 缓存失效（MID-33，同 invalidate_kuaishou_did_cache 口径）
    global _cached_twitch_client_id, _cached_twitch_client_id_ts, _cached_twitch_client_id_proxy
    with _twitch_client_id_lock:
        _cached_twitch_client_id = ""
        _cached_twitch_client_id_ts = 0.0
        recorded = _cached_twitch_client_id_proxy
        _cached_twitch_client_id_proxy = ""
    keys = {recorded}
    if proxy_addr is not None:
        keys.add(proxy_addr or "")
    for k in keys:
        _cache_invalidate_generic(f"twitch_client_id|{k}")


def _take_cached_kuaishou_did(proxy_addr: OptionalStr) -> str:
    # M-8（2026-09-29）：快路必须判「出口(proxy)一致性」，参照 src/ttwid.py 的 MIN-2220 已修形态。
    # 下层 singleflight 键 f"kuaishou_did|{proxy or ''}" 与写入侧的 _cached_kuaishou_did_proxy 都带
    # 代理维度，唯独原来的模块全局快路只看「非空 + TTL」→ 代理 A 取到的 did 在 TTL 内被代理 B 的
    # 房间直接复用。快手的 did 与出口 IP 绑定，串用表现为间歇「200 + 空 body」风控，且
    # invalidate 链会连带清掉另一个出口本来正常的值、下一轮又重新抢占，整条链路来回抖动。
    # 不匹配时只回空串、**不清全局**——那份值对它自己的出口仍然有效。
    # ts==0.0 且值非空仍按有效处理（与 MID-33 的既有口径一致：只可能来自测试/外部直接注入全局）。
    if not _cached_kuaishou_did:
        return ""
    if _cached_kuaishou_did_proxy != (proxy_addr or ""):
        return ""
    if _cached_kuaishou_did_ts and (time.monotonic() - _cached_kuaishou_did_ts) >= _CREDENTIAL_TTL:
        return ""
    return _cached_kuaishou_did


async def _ensure_kuaishou_did(proxy_addr: OptionalStr = None) -> str:
    # 自动获取快手访客 did/didv（访问快手直播主页时服务器下发），替代硬编码过期凭据。
    # 改经统一 cookie 缓存（src/cookie_cache.fetch_cookies）从快手主页动态获取，
    # 同网址下的其他模块直接复用，避免重复请求触发风控。
    #
    # 2026-09-12 审查 H-2：原实现为「with _kuaishou_did_lock: 内 await _cache_fetch_cookies」，
    # 属锁内 await 反模式——本项目每房间独立线程 + 独立事件循环，持锁协程等待网络期间
    # 其它房间线程执行到 with 会同步阻塞整个事件循环（多房间冷启动全部串行卡顿）。
    # 改为经 cookie_cache.singleflight 统一去重：临界区内仅做字典读写，网络拉取在锁外，
    # 等待者经 future 复用同一份结果（跨循环经 call_soon_threadsafe 交付）。
    global _cached_kuaishou_did, _cached_kuaishou_did_ts, _cached_kuaishou_did_proxy
    # M-8（2026-09-29）：快路判据收进 _take_cached_kuaishou_did（含出口一致性），理由见该函数注释。
    cached_did = _take_cached_kuaishou_did(proxy_addr)
    if cached_did:
        return cached_did

    async def _fetch() -> str:
        cookies_dict = await _cache_fetch_cookies(
            url="https://live.kuaishou.com/",
            proxy_addr=proxy_addr,
            headers={
                "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36"
            },
            timeout=10,
            fetcher=async_req,  # 传入本模块 async_req，使单测对 src.spider.async_req 打桩仍生效
        )
        if not isinstance(cookies_dict, dict):
            return ""
        did = cookies_dict.get("did", "")
        didv = cookies_dict.get("didv", "")
        if not did:
            return ""
        logger.debug("自动获取快手 did 成功")
        return f"did={did}; didv={didv}" if didv else f"did={did}"

    got = await _cache_singleflight(key=f"kuaishou_did|{proxy_addr or ''}", factory=_fetch, timeout=10)
    if isinstance(got, str) and got:
        # M-04（2026-10-02）：「值/ts/proxy 记录」三元组必须整组在锁内写——两个不同代理的
        # singleflight 桶并发返回时，锁外交错写会产生「值与出口记录错配」（proxy=A 的房间
        # 拿到 proxy=B 拉取的 did，跨出口串用即复活 M-8 描述的风控症状）。临界区零 await。
        with _kuaishou_did_lock:
            _cached_kuaishou_did = got
            _cached_kuaishou_did_ts = time.monotonic()
            _cached_kuaishou_did_proxy = proxy_addr or ""
        return got
    # M-8（2026-09-29）本轮没拿到新值的两条出口。全局留着的是**别的出口**的 did 时，既不能把它
    # 递给本次调用（那正是快路漏判 proxy 的那条泄漏路径，失败分支同样要走一遍），也不能清掉它
    # （对它自己的出口仍有效）。
    if _cached_kuaishou_did and _cached_kuaishou_did_proxy != (proxy_addr or ""):
        return ""
    if _cached_kuaishou_did and (time.monotonic() - _cached_kuaishou_did_ts) >= _CREDENTIAL_TTL:
        # TTL 已过期且本轮重取失败：旧值不再返回（原行为是永久返回旧值），回空串交调用方下轮重试
        # 代理记录随值一并清空，保持「值非空 ⟺ 出口记录有效」这一对写入/清空同点的不变量。
        _cached_kuaishou_did = ""
        _cached_kuaishou_did_ts = 0.0
        _cached_kuaishou_did_proxy = ""
    return _cached_kuaishou_did


async def _ensure_twitch_client_id(proxy_addr: OptionalStr = None) -> str:
    # 从 Twitch 主页动态提取 Web 端公开 Client-Id（替代硬编码值，避免 Twitch 更换后功能失效）。
    # 它是网页客户端使用的公共标识、非用户私人凭据。
    #
    # 2026-09-12 审查 H-2：同 _ensure_kuaishou_did，原为锁内 await 反模式，
    # 改经 cookie_cache.singleflight 去重（锁内零 await）
    global _cached_twitch_client_id, _cached_twitch_client_id_ts, _cached_twitch_client_id_proxy
    # L-12（2026-10-02）：快路补出口(proxy)一致性比对，对齐快手 did / B站 buvid 的
    # _take_cached_* 口径。Client-Id 非出口绑定凭据，错配的实际影响有限，但保持三处
    # 凭据缓存同一判定形态，避免未来新凭据复制快路写法时把「漏判 proxy」一起带上。
    if (
        _cached_twitch_client_id
        and _cached_twitch_client_id_proxy == (proxy_addr or "")
        and (not _cached_twitch_client_id_ts or (time.monotonic() - _cached_twitch_client_id_ts) < _CREDENTIAL_TTL)
    ):
        return _cached_twitch_client_id

    async def _fetch() -> str:
        html = await async_req(
            url="https://www.twitch.tv/",
            proxy_addr=proxy_addr,
            headers={"User-Agent": _TWITCH_WEB_UA, "Accept-Language": "en-US"},
            timeout=10,
        )
        html = _get_str_response(html)
        # Twitch 主页 HTML 中通过 "Client-ID" 字符串内嵌公开客户端标识
        match = re.search(r'"Client-ID"\s*[:=]\s*"([a-z0-9]{20,})"', html)
        if not match:
            return ""
        logger.debug("自动获取 Twitch Client-Id 成功")
        return match.group(1)

    got = await _cache_singleflight(key=f"twitch_client_id|{proxy_addr or ''}", factory=_fetch, timeout=10)
    if isinstance(got, str) and got:
        # M-04（2026-10-02）：三元组整组锁内写，理由同 _ensure_kuaishou_did
        with _twitch_client_id_lock:
            _cached_twitch_client_id = got
            _cached_twitch_client_id_ts = time.monotonic()
            _cached_twitch_client_id_proxy = proxy_addr or ""
    elif _cached_twitch_client_id and (time.monotonic() - _cached_twitch_client_id_ts) >= _CREDENTIAL_TTL:
        # TTL 过期且重取失败：不再返回过期旧值（同 _ensure_kuaishou_did 口径）
        with _twitch_client_id_lock:
            _cached_twitch_client_id = ""
            _cached_twitch_client_id_ts = 0.0
    return _cached_twitch_client_id


def _generate_twitch_play_session_id() -> str:
    # 动态生成 Twitch 播放会话 ID（替代硬编码的过期会话 ID）
    # 原硬编码值为固定 32 位十六进制字符串，实际应为每次会话独立生成
    return generate_random_string(32).lower()


def _get_str_response(resp: object) -> str:
    # 安全地将 async_req 的响应转换为字符串格式
    # async_req 成功返回 str、失败/异常返回 (str, status) 元组或 None；统一收敛为 str，
    # 失败返回 ""，使下游 _loads_dict 与「空响应即风控」判据无需区分响应类型。
    if isinstance(resp, str):
        return resp
    elif isinstance(resp, tuple) and len(resp) > 0 and isinstance(resp[0], str):
        return resp[0]
    return ""


def _loads_dict(text: object) -> dict[str, object]:
    # 将 async_req 文本响应安全解析为 dict[str, object]，消除 json.loads 的 Any 传播
    # 空串/非 JSON/非 dict 一律回 {} 而非 None，保证调用方始终能 .get() 而不必先判空，
    # 否则上游取 stream_url/origin 时会因 None 触发 AttributeError 崩主循环。
    #
    # CR-12 修复：原实现用裸 json.loads(s)，只挡住了空串——平台在风控/改版时返回
    # HTML（WAF 拦截页、302 落地页、Cloudflare 挑战页、被截断的 JSON）会抛
    # JSONDecodeError，与「非 JSON 一律回 {}」的注释承诺相反。该函数在本文件有上百处
    # 调用，任一处抛错都会被 @trace_error_decorator 吞成 {"is_live": False}，
    # 表现为「明明在播却持续漏录」且日志看不出原因。改走异常安全版 _safe_loads。
    s = _get_str_response(text)
    if not s:
        return {}
    return _safe_loads(s) or {}


def _safe_loads(text: str) -> Optional[dict[str, object]]:
    # 异常安全的 json.loads：捕获 JSONDecodeError 并记录 warning 后回 None。
    # 用于替换 spider.py 中大量裸 json.loads(json_str) 调用，平台接口轻微变更
    # （如返回 HTML 错误页或截断）不至于把整个解析链路拉崩。仅解析失败时记日志，
    # 解析成功但非 dict 的非合法值仍由调用方按业务判空处理。
    try:
        parsed = cast(object, json.loads(text))
    except json.JSONDecodeError as e:
        logger.warning(i18n.tr("JSON 解析失败(已忽略): {type_name}: {e}", type_name=type(e).__name__, e=e))
        return None
    return parsed if isinstance(parsed, dict) else None


def _dig(data: object, *keys: str | int) -> object:
    # MID-48（2026-09-21 国内平台批次）：深层链式索引 `json_data["a"]["b"][0]["c"]` 的安全下钻版。
    # 旧写法在接口改版 / 返回 WAF 页 / 房间不存在时抛 KeyError·TypeError·IndexError，三种成因
    # 一律被 @trace_error_decorator 吞成 {"is_live": False}，与「主播真未开播」完全不可区分
    # （用户侧只见持续的「网址内容获取失败」）。本函数任一环缺失或类型不符即回 None，
    # 由调用方显式判空后决定「按未开播返回」还是「留线索后再抛错」。
    # 返回值仍是 object：字符串字段走 _dig_str，需要继续下钻就继续用 _dig。
    current: object = data
    for key in keys:
        if isinstance(key, int):
            if not isinstance(current, list) or not -len(current) <= key < len(current):
                return None
            current = current[key]
        elif isinstance(current, dict) and key in current:
            current = current[key]
        else:
            return None
    return current


def _dig_str(data: object, *keys: str | int) -> str:
    # _dig 的字符串专用版：非 str（缺失 / null / 数字 / dict）一律回 ""。
    # 主播名与标题会流到 main.py 的 clean_name()（只接受 str，见 MID-43 同类坑），
    # 直接返回 object 会让下游 AttributeError 并把该轮记成熔断成功样本。
    value = _dig(data, *keys)
    return value if isinstance(value, str) else ""


def _dig_list(data: object, *keys: str | int) -> list[object]:
    # _dig 的列表专用版：非 list 一律回 []，使调用方 for 循环恒安全。
    # 「键缺失」与「空数组」在此不区分——需要归因时先判 _dig(data, *keys) is None。
    value = _dig(data, *keys)
    return cast(list[object], value) if isinstance(value, list) else []


def _warn_api_abnormal(json_str: str, api_name: str, field: str, data: dict[str, object]) -> None:
    # MID-48：把「接口响应不符合预期」的成因分开落日志，替代原先「静默 KeyError → 未开播」。
    # ① 空响应：async_req 失败/被风控时归一为 ""（见 _get_str_response 注释）→ 网络或风控信号；
    # ② 非空但缺字段：可能是真「房间不存在/未开通」，也可能是接口改版；其中 WAF/HTML 形态
    #    在 _loads_dict→_safe_loads 处已额外留过一条「JSON 解析失败」告警，两条相邻即可判定
    #    是拦截页而非业务空数据。
    # 另把接口自身的 code/message 原样带出——多数平台用它区分「房间不存在」，这是离线环境下
    # 唯一能进一步归因的信息（具体取值需真机核对）。
    if not json_str:
        logger.warning(i18n.tr("{api} 返回空响应（风控或网络失败）", api=api_name))
        return
    # 各平台错误信封的键名不一（B站/猫耳用 code、AcFun/快手系用 errorCode/resultCode、
    # 京东用 code 字符串），逐个试到第一个非 None 为止。
    code: object = None
    for key in ("code", "status", "errorCode", "resultCode"):
        code = _dig(data, key)
        if code is not None:
            break
    msg: object = None
    for key in ("message", "msg", "errorMsg"):
        msg = _dig(data, key)
        if msg:
            break
    logger.warning(
        i18n.tr(
            "{api} 响应缺少 {field} 字段（房间不存在/未开通 或 接口改版/风控页）: code={code} msg={msg}",
            api=api_name,
            field=field,
            code=code if code is not None else "",
            msg=msg if msg is not None else "",
        )
    )


def _is_safe_http_url(url: str) -> bool:
    # 平台 URL 白名单校验：仅放行 http(s)，另允许 webcal/ws(s) 等平台专用协议
    # （弹幕 wsclient 仍需 ws://）。防用户在 URL_config.ini 写入 file:// / gopher:// /
    # ftp:// 造成 SSRF——本项目虽无直接 fetch 面，但 stream_select 校验与后续解析链路
    # 都会按 URL 触发请求，收紧 scheme 边界是最低成本的防御。
    #
    # 本函数是 src/utils.is_safe_http_url 的薄封装，spider.py 内已无生产调用点、仅为兼容 tests/ 保留；
    # 新代码直接用 utils.is_safe_http_url，别因这里有同名函数就以为 spider 仍在它上面做 URL 校验。
    # [历史注] MI-15（2026-09-12 审查 6.3）把实现上移到 utils：原定义在此处时，更底层的
    # async_http / sync_http 无法反向 import spider（循环依赖），校验退化成纸面防御，上移后才接入请求入口。
    return utils.is_safe_http_url(url)


def get_params(url: str, params: str) -> OptionalStr:
    # 从URL中提取指定参数的值
    # 参数缺失时返回 None（而非空串），调用方常靠 None 区分「未提供」与「值为空」，
    # 若改返回 "" 会与「参数为空字符串」语义混淆、导致直播类型/房间号误判。
    parsed_url = urllib.parse.urlparse(url)
    query_params = urllib.parse.parse_qs(parsed_url.query)

    if params in query_params:
        return query_params[params][0]
    return None


def extract_douyin_hevc_flv_url(html: str) -> OptionalStr:
    # 从抖音页面 HTML 中提取 HEVC/H265 FLV 流地址
    # 跳过 only_audio=1 的纯音频 FLV（无画面不可录）；整页未匹配到有效视频流时返回 None，
    # 调用方据此保留 ORIGIN 的 hls/flv 而不注入 hevc_flv_url，避免把音频流当视频源录制。
    for match in _DOUYIN_HEVC_FLV_PATTERN.findall(html):
        clean_url = match.replace("\\u0026", "&").rstrip("\\").strip()
        parsed = urllib.parse.urlparse(clean_url)
        query = urllib.parse.parse_qs(parsed.query)
        if query.get("only_audio", ["0"])[0] == "1":
            continue
        # 必须补 codec=h265 标记：下游 _is_h265() 与 main.py 的 h265 兜底判定只认 URL 上的
        # codec 查询参数（对齐本文件给 ORIGIN 线路拼 &codec=<VCodec> 的既有做法），缺失会让
        # HEVC 源伪装成普通 FLV 通过全部检查、直接进 -c copy。已带该参数时原样返回，避免重复拼接。
        if query.get("codec"):
            return cast(str, clean_url)
        separator = "&" if parsed.query else "?"
        return cast(str, f"{clean_url}{separator}codec=h265")
    return None


async def get_play_url_list(
    m3u8: str, proxy: OptionalStr = None, header: OptionalDict = None, abroad: bool = False
) -> list[str]:
    # 获取M3U8播放列表中的所有清晰度URL并按带宽排序
    # 响应非字符串（请求失败/被风控）直接回 []，调用方据此判定无多清晰度源、回退单地址；
    # 仅当带宽标记数量与 URL 数量一致才按带宽降序，否则保留 m3u8 原始顺序，避免错位映射选错画质。
    # **返回值可能混合绝对与相对地址**（2026-09-12 审查放宽：http(s):// 绝对行原样收，
    # `//host/path` 按清单自身协议补全，其余以 .m3u8 结尾的行按相对收）。
    # 因此调用方**不得**再假定「全是相对路径」而做前缀字符串拼接——那会把绝对条目拼成
    # `https://host/path/https://cdn/x.m3u8` 这种坏候选（MID-2222 在 ShowRoom/CHZZK 的实际形态）。
    # 需要统一成绝对地址的调用方一律用 urllib.parse.urljoin(m3u8, line)（见 SOOP 的写法），
    # 它对相对/绝对/带参三形态都正确。
    resp = await async_req(url=m3u8, proxy_addr=proxy, headers=header, abroad=abroad)
    if not isinstance(resp, str):
        return []
    play_url_list: list[str] = []
    # 2026-09-12 审查（低危）：此前只认 "https://" 前缀，部分自建/内网 HLS 源与个别
    # CDN 用 http:// 或协议相对写法会被整条跳过 → 多清晰度列表为空、上层回退单地址
    # （用户侧表现为「画质下拉只有一项」）。三形态的具体收法见本函数头部注释。
    _m3u8_scheme = urllib.parse.urlparse(m3u8).scheme or "https"
    for i in resp.split("\n"):
        line = i.strip()
        if line.startswith(("https://", "http://")):
            play_url_list.append(line)
        elif line.startswith("//"):
            play_url_list.append(f"{_m3u8_scheme}:{line}")
    if not play_url_list:
        for i in resp.split("\n"):
            if i.strip().endswith("m3u8"):
                play_url_list.append(i.strip())
    bandwidth_pattern = _BANDWIDTH_PATTERN
    bandwidth_list = cast(list[str], bandwidth_pattern.findall(resp))
    if bandwidth_list and len(bandwidth_list) == len(play_url_list):
        url_to_bandwidth = {url: int(bandwidth) for bandwidth, url in zip(bandwidth_list, play_url_list)}
        play_url_list = sorted(play_url_list, key=lambda url: url_to_bandwidth[url], reverse=True)
    return play_url_list


def _extract_room_data_from_html(html_str: str) -> dict[str, object]:
    # 从抖音直播间HTML页面提取房间数据（作为API失败时的回退方案）
    # 这是 web/enter 接口彻底失败后的兜底：HTML 内联了状态 JSON，但其结构随页面改版极不稳定，
    # 正则失配即直接返回 {}、结构层级变化才落到末尾 except 返回 {}，两条路径在上游都表现为
    # 「未开播/房间不存在」并反复重试。
    if not html_str:
        return {}
    try:
        # 两种正则分别匹配不同版本的页面内联根结构（state / common），无第三个兜底；
        # 正则强依赖抖音页面模板，任一处字段改名即整体失效、静默返回 {}。
        match_json_str = re.search(r'(\{\\"state\\":.*?)]\\n"]\)', html_str)
        if not match_json_str:
            match_json_str = re.search(r'(\{\\"common\\":.*?)]\\n"]\)</script><div hidden', html_str)
        if not match_json_str:
            return {}
        json_str = match_json_str.group(1)
        # 内联 JSON 是双重转义字符串：先去掉一层反斜杠还原引号，再把 u0026 还原为
        # &（URL 参数分隔符），否则后续按 JSON 解析与按 & 拆参数都会失败。
        cleaned_string = json_str.replace("\\", "").replace(r"u0026", r"&")
        room_store_match = re.search('"roomStore":(.*?),"linkmicStore"', cleaned_string, re.DOTALL)
        if not room_store_match:
            return {}
        room_store = room_store_match.group(1)
        anchor_name_match = re.search('"nickname":"(.*?)","avatar_thumb', room_store, re.DOTALL)
        anchor_name = anchor_name_match.group(1) if anchor_name_match else ""
        # 截到 "has_commerce_goods" 字段前再用固定 3 个右花括号收尾：内联 JSON 被页面截断，
        # 用固定标记切断后再手动补齐括号平衡结构；若结构层级变化会导致解析抛错而落到 except。
        room_store = room_store.split(',"has_commerce_goods"')[0] + "}}}"
        room_info = cast(dict[str, object], _loads_dict(room_store).get("roomInfo") or {})
        json_data = cast(dict[str, object], room_info.get("room") or {})
        json_data["anchor_name"] = anchor_name
        # status==4 表示非开播态（回放/下播）；此处提前返回不含 stream_url 的结果，
        # 上游据此判定未开播，不再尝试取流。
        if json_data.get("status") == 4:
            return json_data
        stream_url_field = cast(dict[str, object], json_data.get("stream_url") or {})
        stream_orientation = stream_url_field.get("stream_orientation")
        origin_url_list: dict[str, object] | None = None
        # 同一页面存在多段内联脚本（横屏/竖屏各一段），按 stream_orientation 选对应段；
        # findall 取不到时回退到整页清洗串里抠 "origin":{"main":... 片段（第二兜底）。
        match_json_str2 = cast(list[str], re.findall(r'"(\{\\"common\\":.*?)"]\)</script><script nonce=', html_str))
        if match_json_str2:
            if stream_orientation == 1:
                json_str2 = match_json_str2[0]
            else:
                json_str2 = match_json_str2[1] if len(match_json_str2) > 1 else match_json_str2[0]
            json_data2 = _loads_dict(
                json_str2.replace("\\", "").replace('"{', "{").replace('}"', "}").replace("u0026", "&")
            )
            data2 = cast(dict[str, object], json_data2.get("data") or {})
            if "origin" in data2:
                origin_url_list = cast(dict[str, object], cast(dict[str, object], data2["origin"]).get("main") or {})
        else:
            html_str_clean = html_str.replace("\\", "").replace("u0026", "&")
            match_json_str3 = re.search('"origin":\\{"main":(.*?),"dash"', html_str_clean, re.DOTALL)
            if match_json_str3:
                # 这里只补 1 个右花括号：该片段在 "dash" 前被切断，结构比上面更浅一层。
                origin_url_list = _loads_dict(match_json_str3.group(1) + "}")
        if origin_url_list:
            sdk_params_field = cast(dict[str, object], origin_url_list.get("sdk_params") or {})
            vcodec = sdk_params_field.get("VCodec")
            origin_hls_codec = vcodec if isinstance(vcodec, str) else ""
            hls_v = origin_url_list.get("hls", "")
            flv_v = origin_url_list.get("flv", "")
            hls_s = hls_v if isinstance(hls_v, str) else ""
            flv_s = flv_v if isinstance(flv_v, str) else ""
            # 把 VCodec 拼进地址的 &codec= 查询参数，供后续 h265 判定与 ffmpeg 选流使用；
            # 再把 ORIGIN 线路合并到已有的 hls_pull_url_map / flv_pull_url 之前，优先于其它线路。
            origin_m3u8 = {"ORIGIN": hls_s + "&codec=" + origin_hls_codec}
            origin_flv = {"ORIGIN": flv_s + "&codec=" + origin_hls_codec}
            hls_pull_url_map = cast(dict[str, object], stream_url_field.get("hls_pull_url_map") or {})
            flv_pull_url = cast(dict[str, object], stream_url_field.get("flv_pull_url") or {})
            stream_url_field["hls_pull_url_map"] = {**origin_m3u8, **hls_pull_url_map}
            stream_url_field["flv_pull_url"] = {**origin_flv, **flv_pull_url}
            hevc_flv_url = extract_douyin_hevc_flv_url(html_str)
            if hevc_flv_url:
                stream_url_field["hevc_flv_url"] = hevc_flv_url
        return json_data
    # 整段兜底逻辑捕获一切异常并回 {}，上游只能看到空结果、按「未开播」处理。
    # [历史注] L-10（2026-10-02）前为裸 except 零日志，失败原因（页面改版/网络/解析错误）
    # 全部丢失、无法区分「真离线」与「解析挂了」；现补 debug 留痕（见下方分支注释）。
    except Exception as e:
        # L-10（2026-10-02）：补 debug 日志——原裸 except 回 {} 使意外 TypeError/KeyError 零痕迹，
        # 与「真离线」不可区分。本路径是「页面结构改版/网络异常」的兜底，每轮重试都会走，
        # 用 debug 避免告警噪音（与同文件 MID-2246 口径一致）。
        logger.debug(
            i18n.tr(
                "抖音房间页 __INITIAL_STATE__ 解析异常（按未开播处理）: {type_name}: {e}",
                type_name=type(e).__name__,
                e=e,
            )
        )
        return {}


async def get_douyin_web_stream_data(
    url: str, proxy_addr: OptionalStr = None, cookies: OptionalStr = None
) -> dict[str, object]:
    # 通过抖音网页端API获取直播数据
    # 注意：cookie 需由调用方通过 cookies 参数传入有效值，硬编码的过期 cookie 必然触发风控
    chrome_ua = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36"
    )
    headers = {
        "cookie": "",
        "referer": url,
        "user-agent": chrome_ua,
        "accept": "application/json, text/plain, */*",
        "accept-language": "zh-CN,zh;q=0.8,zh-TW;q=0.7,zh-HK;q=0.5,en-US;q=0.3,en;q=0.2",
        "sec-ch-ua": '"Google Chrome";v="141", "Chromium";v="141", "Not_A Brand";v="8"',
        "sec-ch-ua-platform": '"Windows"',
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin",
        "x-requested-with": "XMLHttpRequest",
    }
    if cookies:
        headers["cookie"] = cookies
    else:
        # 未传入 cookie 时退化到游客态：用 _ensure_ttwid 取一个仅含 ttwid 的设备访客标识。
        # 仅 ttwid 也能拉到流，但风控率显著高于带登录 cookie，故调用方应优先传真实 cookie。
        headers["cookie"] = await _ensure_ttwid(proxy_addr)

    try:
        # web_rid 取 URL 末段即可，无需额外解析请求：web/enter 同时接受数字房间号
        # （745964462470）与抖音号（yall1102），且传入抖音号不会发生重定向
        # （数字 id 才可能被 30x 跳转），故直接取末段即可。
        web_rid = url.split("?")[0].rstrip("/").split("live.douyin.com/")[-1]
        params = {
            "aid": "6383",
            "app_name": "douyin_web",
            "live_id": "1",
            "device_platform": "web",
            "language": "zh-CN",
            "browser_language": "zh-CN",
            "browser_platform": "Win32",
            "browser_name": "Chrome",
            "browser_version": "141.0.0.0",
            "web_rid": web_rid,
            # msToken 此处留空：web/enter 端点不强制校验 msToken（app 端点才强依赖），
            # 留空可避免引入需额外签名的参数；风控主要看 ttwid/cookie 而非 msToken。
            "msToken": "",
        }

        api = f"https://live.douyin.com/webcast/room/web/enter/?{urllib.parse.urlencode(params)}"

        async def _try_web_api() -> dict[str, object]:
            # 单次 web/enter API 尝试；失败（空响应 / 非 0 状态码）抛异常，由外层决定是否重试或回退。
            json_str = _get_str_response(await async_req(url=api, proxy_addr=proxy_addr, headers=headers))
            # 抖音风控时不返回 4xx，而是 200 + 空响应体，故不能只靠状态码判断成败，
            # 必须显式判空再抛「疑似风控」，交外层决定重试或回退 HTML。
            if not json_str:
                raise Exception("empty response from API (possible risk control)")
            parsed = _loads_dict(json_str)
            status_code = parsed.get("status_code")
            if status_code is not None and int(cast(str, status_code)) != 0:
                status_msg = parsed.get("status_msg", "unknown error")
                raise Exception(f"API returned status_code={status_code}, msg={status_msg}")
            json_data = cast(dict[str, object], parsed.get("data") or {})
            inner_list = json_data.get("data")
            if not inner_list:
                # M-3（2026-09-29）：进 raise 的 URL 一律先过 utils.mask_credentials。
                # @trace_error_decorator 落日志时对异常原文不做任何脱敏，而调用方透传的房间地址
                # 可能挂着 token/ttwid/cookie 类查询参数（pwd/session 均在 utils._SECRET_KEYS 表内），
                # 明文抛出即等于把凭据写进 logs/streamget.log（300 KB 轮转保留多份 = 长期落盘）。
                raise Exception(f"{utils.mask_credentials(url)} VR live is not supported or room not found")
            room_data = cast(dict[str, object], cast(list[object], inner_list)[0])
            user_info = cast(dict[str, object], json_data.get("user") or {})
            # M-9（2026-09-29）：.get("nickname") 只挡「键缺失」，抖音显式返回 "nickname": null
            # （游客态被风控/主页态房间）时取到 None 并写进结果 dict；下游 clean_name(None) 当场
            # AttributeError（src/stream_select.py 的 clean_name 首行 input_text.strip()），整轮解析
            # 被兜成「获取失败」且该轮已按成功样本上报熔断统计。文件内新代码统一走 _dig_str。
            room_data["anchor_name"] = _dig_str(user_info, "nickname")
            return room_data

        room_data: dict[str, object] | None = None
        api_error: Exception | None = None
        # MIN-2202 修复（2026-09-22）：兜底抓到的 HTML 提到循环外复用——原先兜底成功后又在下方
        # 对**同一 url** 再发一次请求只为取 hevc_flv_url，而被风控（200+空 body）是每个抖音房间的
        # 常态，等于每轮多下载约 1MB 页面（正是下方重试注释想「省去」的开销）；两次抓取之间页面还可能
        # 变化，导致 ORIGIN 与 hevc 地址来自不同快照。仅在其为空（未走兜底、或兜底抓取失败）时才再抓一次。
        html_str = ""
        # 抖音 web/enter 接口偶发返回 10002 等软拒绝（多为瞬时风控），先静默重试一次，
        # 成功则直接返回、跳过 HTML 回退（省去一次约 1MB 的兜底 HTML 抓取）；
        # 两次都失败才记 WARNING 并回退 HTML 抓取。
        for attempt in range(2):
            try:
                room_data = await _try_web_api()
                break
            except Exception as e:
                api_error = e
                if attempt == 0:
                    await asyncio.sleep(0.5)  # 给瞬时风控一个缓冲窗口
                    continue
                logger.warning(
                    i18n.tr("Douyin web API failed: {api_error}, falling back to HTML scraping", api_error=api_error)
                )
                try:
                    html_str = _get_str_response(await async_req(url=url, proxy_addr=proxy_addr, headers=headers))
                    room_data = _extract_room_data_from_html(html_str)
                    if not room_data:
                        raise Exception(f"HTML scraping also failed after API error: {api_error}")
                    logger.debug("HTML scraping fallback succeeded")
                except Exception as e2:
                    raise Exception(f"Douyin web data fetch error (API: {api_error}) (HTML fallback: {e2}).")
        if room_data is None:
            raise Exception(f"Douyin web data fetch error: {api_error}")

        # status==2 才是真正开播；其它值（如 4）视为未开播，跳过取流、返回无 stream 的 room_data。
        if room_data.get("status") == 2:
            if "stream_url" not in room_data:
                raise RuntimeError(
                    "The live streaming type or gameplay is not supported on the computer side yet, please use the "
                    "app to share the link for recording."
                )
            stream_url = cast(dict[str, object], room_data["stream_url"])
            # web/enter 的响应里不含 HEVC 的 flv 地址，只能再从直播间 HTML 内联数据里抠。
            # MIN-2202：复用上面兜底抓到的同一份快照，仅在其为空时才另抓一次（理由见循环外那条注释）。
            if not html_str:
                html_str = _get_str_response(await async_req(url=url, proxy_addr=proxy_addr, headers=headers))
            hevc_flv_url = extract_douyin_hevc_flv_url(html_str)
            live_core_sdk_data = cast(dict[str, object], stream_url.get("live_core_sdk_data") or {})
            pull_datas = cast(dict[str, object], stream_url.get("pull_datas") or {})
            if live_core_sdk_data:
                json_str = ""
                if pull_datas:
                    # 遍历 pull_datas 各线路，优先挑出 HEVC(h265) 候选；拿不到再退回第一条有效候选。
                    # 用 "origin" 是否在解析后的 data 中存在作为该线路有效的判据；单条解析失败（PEP 758 多异常）
                    # 仅跳过该条、不中断整体遍历。
                    hevc_candidate = ""
                    first_candidate = ""
                    for value in pull_datas.values():
                        value_dict = cast(dict[str, object], value) if isinstance(value, dict) else {}
                        candidate_raw = value_dict.get("stream_data") or ""
                        candidate = candidate_raw if isinstance(candidate_raw, str) else ""
                        if not candidate:
                            continue
                        try:
                            cand_data = cast(dict[str, object], _loads_dict(candidate).get("data") or {})
                        except json.JSONDecodeError, TypeError:
                            continue
                        if "origin" not in cand_data:
                            continue
                        if not first_candidate:
                            first_candidate = candidate
                        try:
                            cand_main = cast(dict[str, object], cast(dict[str, object], cand_data["origin"])["main"])
                            cand_sdk_raw = cand_main.get("sdk_params", "{}")
                            codec_val = _loads_dict(cand_sdk_raw if isinstance(cand_sdk_raw, str) else "{}").get(
                                "VCodec", ""
                            )
                            codec = codec_val if isinstance(codec_val, str) else ""
                        except json.JSONDecodeError, KeyError, TypeError:
                            codec = ""
                        if "h265" in codec.lower() or "hevc" in codec.lower():
                            hevc_candidate = candidate
                            break
                    json_str = hevc_candidate or first_candidate
                elif "pull_data" in live_core_sdk_data:
                    pull_data = live_core_sdk_data["pull_data"]
                    if isinstance(pull_data, dict):
                        sd = cast(dict[str, object], pull_data).get("stream_data", "")
                        json_str = sd if isinstance(sd, str) else ""
                    else:
                        json_str = ""
                if json_str:
                    parsed_data = cast(dict[str, object], _loads_dict(json_str).get("data") or {})
                    if "origin" in parsed_data:
                        # MID-2214（2026-09-23）：原为 `cast(dict, cast(dict, parsed_data["origin"])["main"])`
                        # 双层裸下标。抖音 pull_data 的 origin 已出现 full/sdk 等变体，「有 origin 但无
                        # main」是真实形态，KeyError 会被最外层 except 吞成 {"anchor_name": ""}，
                        # 把**已经解析好的 room_data（含主播名与全部流地址）**整体作废 → 该房间
                        # 此后每轮固定「网址内容获取失败」、永久不录。
                        # 与同文件姊妹实现 get_douyin_app_stream_data 同写法（.get("main") or {}），
                        # 并在取不到时**整体跳过** ORIGIN 注入：不能只把 origin_url_list 置空，
                        # 否则下面的 {**origin_m3u8, **hls_pull_url_map} 会注入
                        # `ORIGIN: "&codec="` 这类坏条目，让选源逻辑多试一次必失败的候选。
                        origin_url_list = cast(
                            dict[str, object], cast(dict[str, object], parsed_data["origin"]).get("main") or {}
                        )
                        if origin_url_list:
                            sdk_raw = origin_url_list.get("sdk_params", "")
                            sdk_params = _loads_dict(sdk_raw if isinstance(sdk_raw, str) else "")
                            vcodec = sdk_params.get("VCodec")
                            origin_hls_codec = vcodec if isinstance(vcodec, str) else ""

                            hls_v = origin_url_list.get("hls", "")
                            flv_v = origin_url_list.get("flv", "")
                            hls_s = hls_v if isinstance(hls_v, str) else ""
                            flv_s = flv_v if isinstance(flv_v, str) else ""
                            origin_m3u8 = {"ORIGIN": hls_s + "&codec=" + origin_hls_codec}
                            origin_flv = {"ORIGIN": flv_s + "&codec=" + origin_hls_codec}
                            hls_pull_url_map = cast(dict[str, object], stream_url.get("hls_pull_url_map") or {})
                            flv_pull_url = cast(dict[str, object], stream_url.get("flv_pull_url") or {})
                            stream_url["hls_pull_url_map"] = {**origin_m3u8, **hls_pull_url_map}
                            stream_url["flv_pull_url"] = {**origin_flv, **flv_pull_url}
                    if hevc_flv_url:
                        stream_url["hevc_flv_url"] = hevc_flv_url
    # 任何解析异常都吞掉并回 {"anchor_name": ""}：不让单房间解析崩溃主循环，
    # 但副作用是「解析失败」与「未开播」被上游同样视作「需重试的不可录」，可能空转。
    except Exception as e:
        tb_lineno = e.__traceback__.tb_lineno if e.__traceback__ else 0
        logger.error(i18n.tr("Error message: {e} Error line: {tb_lineno}", e=e, tb_lineno=tb_lineno))
        room_data = cast(dict[str, object], {"anchor_name": ""})
    return room_data


@trace_error_decorator
async def get_douyin_app_stream_data(
    url: str, proxy_addr: OptionalStr = None, cookies: OptionalStr = None
) -> dict[str, object]:
    # 通过抖音APP端接口获取直播数据（备用方案）
    # 注意：cookie 需由调用方通过 cookies 参数传入有效值，硬编码的过期 cookie 必然触发风控
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
        + "Chrome/141.0.0.0 Safari/537.36 Edg/141.0.0.0",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-CN,zh;q=0.8,zh-TW;q=0.7,zh-HK;q=0.5,en-US;q=0.3,en;q=0.2",
        "Referer": url,
        "Cookie": "",
    }
    if cookies:
        headers["Cookie"] = cookies
    else:
        headers["Cookie"] = await _ensure_ttwid(proxy_addr)

    async def get_app_data(room_id: str, sec_uid: str) -> dict[str, object]:
        app_params = {
            # verifyFp 留空：app reflow 接口不强制校验指纹，留空省去一次签名计算。
            "verifyFp": "",
            "type_id": "0",
            "live_id": "1",
            "room_id": room_id,
            "sec_user_id": sec_uid,
            # version_code / app_id 是模拟抖音 APP 客户端的固定标识，必须与接口预期一致，
            # 否则返回 status_code 非零（风控/参数错误）；不要随意改版本号。
            "version_code": "141.0.0.0",
            "app_id": "1128",
        }
        # 走 amemv.com 的 reflow/info 端点（APP 侧直播间接口），与 web/enter 不同源、参数体系也不同。
        api2 = f"https://webcast.amemv.com/webcast/room/reflow/info/?{urllib.parse.urlencode(app_params)}"
        try:
            json_str2 = _get_str_response(await async_req(url=api2, proxy_addr=proxy_addr, headers=headers))
            # 与 web 端一致：抖音风控返回 200+空 body 而非 4xx，必须显式判空再定罪。
            if not json_str2:
                raise Exception("empty response from API (possible risk control)")
            parsed2 = _loads_dict(json_str2)
            status_code2 = parsed2.get("status_code")
            if status_code2 is not None and int(cast(str, status_code2)) != 0:
                status_msg2 = parsed2.get("status_msg", "unknown error")
                raise Exception(f"API returned status_code={status_code2}, msg={status_msg2}")
            json_data2 = cast(dict[str, object], parsed2.get("data") or {})
            room_field = json_data2.get("room")
            if not room_field:
                # M-3（2026-09-29）：同 get_douyin_web_stream_data 内同名判据（见该处注释全文）——
                # APP 端这条路径同样把调用方 URL 拼进了异常消息，脱敏后才允许上抛。
                raise Exception(f"{utils.mask_credentials(url)} VR live is not supported or room not found")
            room_data2 = cast(dict[str, object], room_field)
            owner = cast(dict[str, object], room_data2.get("owner") or {})
            # M-9（2026-09-29）：同 web 端 _try_web_api 的判据（见该处注释）——null 昵称一律回 ""。
            room_data2["anchor_name"] = _dig_str(owner, "nickname")
            return room_data2
        except Exception as e:
            raise Exception(f"Douyin app data fetch error, because {e}.")

    async def resolve_from_homepage() -> dict[str, object]:
        # 主播主页链接：先解析出抖音号，再按直播间地址取流。
        # 这里直调 get_douyin_web_stream_data（网页端 API 优先、内置 HTML 兜底），
        # 而非旧版 HTML 优先抓取路径（需下载约 1MB 页面且正则易随改版失效），可省去一次大流量请求。
        # 注意必须透传 proxy_addr / cookies，否则代理与 Cookie 配置会在此路径静默丢失。
        unique_id = await get_unique_id(url, proxy_addr=proxy_addr)
        return await get_douyin_web_stream_data(f"https://live.douyin.com/{unique_id}", proxy_addr, cookies)

    try:
        web_rid = url.split("?")[0].split("live.douyin.com/")
        if len(web_rid) > 1:
            return await get_douyin_web_stream_data(url, proxy_addr, cookies)
        elif is_user_homepage_url(url):
            # 网页端主页链接（www.douyin.com/user/<sec_uid>）不会重定向到 reflow 直播间页，
            # 调 get_sec_user_id 必然抛 UnsupportedUrlError 且白下载一次主页 HTML，直接跳过。
            return await resolve_from_homepage()
        else:
            try:
                data = await get_sec_user_id(url, proxy_addr=proxy_addr)
                if data is None:
                    raise RuntimeError("Failed to get sec_user_id")
                _room_id, _sec_uid = data
                room_data = await get_app_data(_room_id, _sec_uid)
            except UnsupportedUrlError:
                return await resolve_from_homepage()

        if room_data.get("status") == 2:
            if "stream_url" not in room_data:
                raise RuntimeError(
                    "The live streaming type or gameplay is not supported on the computer side yet, please use the "
                    + "app to share the link for recording."
                )
            stream_url = cast(dict[str, object], room_data["stream_url"])
            live_core_sdk_data = cast(dict[str, object], stream_url.get("live_core_sdk_data") or {})
            pull_datas = cast(dict[str, object], stream_url.get("pull_datas") or {})
            if live_core_sdk_data:
                if pull_datas:
                    key = list(pull_datas.keys())[0]
                    first_pull = cast(dict[str, object], pull_datas[key])
                    sd0 = first_pull.get("stream_data", "")
                    json_str = sd0 if isinstance(sd0, str) else ""
                else:
                    pull_data = live_core_sdk_data.get("pull_data", {})
                    if isinstance(pull_data, dict):
                        sd0 = cast(dict[str, object], pull_data).get("stream_data", "")
                        json_str = sd0 if isinstance(sd0, str) else ""
                    else:
                        json_str = ""
                if json_str:
                    parsed_data = cast(dict[str, object], _loads_dict(json_str).get("data") or {})
                    if "origin" in parsed_data:
                        # MID-41 修复（2026-09-20）：ORIGIN 候选与 codec 原先取**第二次解析**的
                        # live_core_sdk_data.pull_data.stream_data，与刚解析出的 json_str 候选无关——
                        # 现代 app 响应只有 pull_datas 而无 pull_data → stream_data 为空 → 整段注入被
                        # 跳过、原画（ORIGIN）候选丢失；两者都在时又会把 pull_data 的 VCodec 标到
                        # pull_datas 的地址上（codec 标注错位 → _is_h265 判错 → -c copy 不安全）。
                        # 现与同文件姊妹实现 get_douyin_web_stream_data 对齐：直接用
                        # parsed_data["origin"]["main"]，删除冗余的二次解析。
                        origin_url_list = cast(
                            dict[str, object], cast(dict[str, object], parsed_data["origin"]).get("main") or {}
                        )
                        sdk_raw = origin_url_list.get("sdk_params", "")
                        sdk_params = _loads_dict(sdk_raw if isinstance(sdk_raw, str) else "")
                        vcodec = sdk_params.get("VCodec")
                        origin_hls_codec = vcodec if isinstance(vcodec, str) else ""

                        hls_v = origin_url_list.get("hls", "")
                        flv_v = origin_url_list.get("flv", "")
                        hls_s = hls_v if isinstance(hls_v, str) else ""
                        flv_s = flv_v if isinstance(flv_v, str) else ""
                        # 把 VCodec 拼进地址的 &codec= 查询参数，供后续 h265 判定与 ffmpeg 选流使用；
                        # ORIGIN 线路合并到已有线路之前、优先于其它线路（与 web 端实现同语义）。
                        origin_m3u8 = {"ORIGIN": hls_s + "&codec=" + origin_hls_codec}
                        origin_flv = {"ORIGIN": flv_s + "&codec=" + origin_hls_codec}
                        hls_pull_url_map = cast(dict[str, object], stream_url.get("hls_pull_url_map") or {})
                        flv_pull_url = cast(dict[str, object], stream_url.get("flv_pull_url") or {})
                        stream_url["hls_pull_url_map"] = {**origin_m3u8, **hls_pull_url_map}
                        stream_url["flv_pull_url"] = {**origin_flv, **flv_pull_url}
    # 任何解析异常都吞掉并回 {"anchor_name": ""}：不让单房间解析崩溃主循环，
    # 但副作用是「解析失败」与「未开播」被上游同样视作「需重试的不可录」，可能空转。
    except Exception as e:
        tb_lineno = e.__traceback__.tb_lineno if e.__traceback__ else 0
        logger.error(i18n.tr("Error message: {e} Error line: {tb_lineno}", e=e, tb_lineno=tb_lineno))
        room_data = cast(dict[str, object], {"anchor_name": ""})
    return room_data


# 内置 TikTok 游客 cookie（MID-46：提为常量，供「是否用了内置缺省」判定与失败告警复用）。
# 第三段 epoch 1761302831 解为 2025-10-24——该值会随时间过期，未配置覆盖的默认安装
# 拿到的就是过期凭据，解析必失败且被装饰器伪装成「未开播」，故失败路径有专属告警。
_TIKTOK_BUILTIN_GUEST_COOKIE = (
    "1%7Cz7FKki38aKyy7i-BC9rEDwcrVvjcLcFEL6QIeqldoy4%7C1761302831%7C6c1461e9f1f980cbe0404c5190"
    "5177d5d53bbd822e1bf66128887d942c9c3e2f"
)


def _read_tiktok_guest_cookie() -> str:
    # TikTok 游客 cookie 的外部覆盖值：优先环境变量，其次 config.ini 的 [Cookie] 段，
    # 最后回落内置缺省值（F-10：参照 _read_haixiu_token_override 的覆盖模式）。
    # 背景：内置游客 cookie 仅用于绕过「未登录即拦截」，已随公开仓库分发、会随时间失效；
    # 提供覆盖入口后，凭据轮换无需改代码重新发布。
    # 注意：本函数必须定义在 get_tiktok_stream_data 的 @trace_error_decorator **之前**，
    # 否则会把该装饰器劫持到自己头上（首次提交即踩过，表现为 TikTok 测试的
    # ConnectionError 不再被装饰器转译成 {"is_live": False} 兜底）。
    override = os.environ.get("TIKTOK_GUEST_COOKIE", "").strip()
    if override:
        return override
    try:
        cfg_value = utils.read_ini_value(f"{script_path}/config/config.ini", "Cookie", "tiktok_guest_cookie")
    except Exception:
        cfg_value = None
    if cfg_value and cfg_value.strip():
        return cfg_value.strip()
    return _TIKTOK_BUILTIN_GUEST_COOKIE


@trace_error_decorator
async def get_tiktok_stream_data(
    url: str, proxy_addr: OptionalStr = None, cookies: OptionalStr = None
) -> dict[str, object] | None:
    # 获取 TikTok 直播数据。TikTok 的房间状态写在 <script id="SIGI_STATE"> 的 SIGI_STATE 里，
    # 必须整页 HTML 抓回再正则抠 JSON，不能用接口直取。下面默认内置一个游客 cookie，
    # 仅用于绕过「未登录即拦截」，有 cookies 参数时以传入为准。
    guest_cookie = cookies or _read_tiktok_guest_cookie()
    # MID-46（2026-09-20）：内置游客 cookie 已过期（epoch 1761302831 ≈ 2025-10-24）时，
    # 未配置覆盖的默认安装拿到的是过期凭据，解析失败被装饰器伪装成「未开播」、
    # 没有任何指向性提示。解析失败且本轮用的正是内置缺省时，先落一条可动作告警再抛错。
    using_builtin_guest = guest_cookie == _TIKTOK_BUILTIN_GUEST_COOKIE

    def _warn_if_builtin_guest() -> None:
        if using_builtin_guest:
            logger.warning(
                i18n.tr(
                    "TikTok 解析失败，且本次使用的是内置游客 cookie（可能已过期）；"
                    "请在 config.ini 的 [Cookie] tiktok_guest_cookie 配置有效访客 cookie（或设置环境变量 TIKTOK_GUEST_COOKIE）"
                )
            )

    headers = {
        "referer": "https://www.tiktok.com/",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
        + "Chrome/141.0.0.0 Safari/537.36",
        # F-10：调用方 cookies > 环境变量/config 覆盖 > 内置缺省（见 _read_tiktok_guest_cookie）
        "cookie": guest_cookie,
    }

    # 最多重试 3 次：TikTok 偶发返回半截 HTML（含 UNEXPECTED_EOF_WHILE_READING 截断标记），
    # 这种脏响应解析必失败，所以先 sleep 1s 再重试，而不是立即报错终止。
    for _ in range(3):
        html_str = _get_str_response(
            await async_req(url=url, proxy_addr=proxy_addr, headers=headers, abroad=True, http2=False)
        )
        await asyncio.sleep(1)  # 异步休眠，避免阻塞事件循环
        # 命中「该节点地区已停止运营 TikTok」公告页：属于代理节点地域被墙，必须抛错让用户换节点，
        # 而不是当成「未开播」静默放过。
        if "We regret to inform you that we have discontinued operating TikTok" in html_str:
            msg = re.search("<p>\n\\s+(We regret to inform you that we have discontinu.*?)\\.\n\\s+</p>", html_str)
            raise ConnectionError(
                "Your proxy node's regional network is blocked from accessing TikTok; please switch to a node in "
                + f"another region to access. {msg.group(1) if msg else ''}"
            )
        # 只有「不含 EOF 截断标记」的整页才尝试解析；截断页直接走下一次重试。
        if "UNEXPECTED_EOF_WHILE_READING" not in html_str:
            try:
                json_str_matches = cast(
                    list[str],
                    re.findall('<script id="SIGI_STATE" type="application/json">(.*?)</script>', html_str, re.DOTALL),
                )
                if not json_str_matches:
                    raise ConnectionError("Please check if your network can access the TikTok website normally")
                json_str = json_str_matches[0]
            except Exception:
                _warn_if_builtin_guest()
                raise ConnectionError("Please check if your network can access the TikTok website normally")
            return _loads_dict(json_str)

    _warn_if_builtin_guest()
    raise ConnectionError(
        "Failed to retrieve TikTok data after 3 retries, please check if your network can access "
        + "the TikTok website normally"
    )


@trace_error_decorator
async def get_kuaishou_stream_data(
    url: str, proxy_addr: OptionalStr = None, cookies: OptionalStr = None
) -> dict[str, object]:
    # 获取快手直播数据
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:148.0) Gecko/20100101 Firefox/148.0",
        "Accept-Language": "zh-CN,zh;q=0.8,zh-TW;q=0.7,zh-HK;q=0.5,en-US;q=0.3,en;q=0.2",
    }
    if cookies:
        headers["Cookie"] = cookies
    # 该路径无重试：抓取 HTML 一旦拿不到内容就直接按「未开播」返回，主循环下一轮会再试。
    # MID-2217（2026-09-23）：原先这里包着 try/except Exception，但 async_req 已在内部
    # 吞尽传输层异常并返回 ""（见 src/async_http.py 的 async_req 尾部 except，且只在
    # debug 级留一行），该 except 分支**永不可达**；而注释声称「用 print 而非 logger」，
    # 与代码（logger.error）相反。于是网络抖动的真实走向是 html_str="" → 正则失配 →
    # ValueError → 被下一层捕获并打印「Failed to parse JSON data」，把**网络成因**归因成
    # **解析成因**，真正的抓取线索永不出现。现删死分支，改为对空响应显式归因。
    html_str = _get_str_response(await async_req(url=url, proxy_addr=proxy_addr, headers=headers))
    if not html_str:
        logger.error(
            i18n.tr(
                "Failed to fetch data from {masked_url}: {type_name}",
                masked_url=utils.mask_credentials(url),
                type_name="EmptyResponse",
            )
        )
        return {"type": 1, "is_live": False}

    try:
        # 快手把房间状态塞进页面 __INITIAL_STATE__ 全局变量，正则抠出后还要补一个右花括号收尾
        # （内联 JSON 被截断在 "gameInfo" 前）。__INITIAL_STATE__ 缺失即视为页面结构变化/被风控。
        json_str_match = re.search("<script>window.__INITIAL_STATE__=(.*?);\\(function\\(\\)\\{var s;", html_str)
        if not json_str_match:
            raise ValueError("Failed to find __INITIAL_STATE__")
        json_str = json_str_match.group(1)
        play_list_matches = cast(list[str], re.findall('(\\{"liveStream".*?),"gameInfo', json_str))
        if not play_list_matches:
            raise ValueError("Failed to find liveStream")
        # 内联串在 "gameInfo" 前被截断，补 1 个右花括号平衡结构。
        play_list = _loads_dict(play_list_matches[0] + "}")
    except (AttributeError, IndexError, json.JSONDecodeError) as e:
        # 只捕获「结构解析」类异常（页面改版/字段缺失/JSON 坏），按未开播返回；
        # 其它异常（如超时已由上层兜住）不在此吞掉，避免把非解析错误也误判成未开播而静默丢失根因。
        logger.error(i18n.tr("Failed to parse JSON data from {url}. Error: {e}", url=utils.mask_credentials(url), e=e))
        return {"type": 1, "is_live": False}

    result: dict[str, object] = {"type": 2, "is_live": False}

    # errorType 字段存在、或 liveStream 缺失，通常代表账号/地域受限（封禁/风控），
    # 此时 play_list 不含真实流信息，直接按「未开播」返回而非抛错。
    if "errorType" in play_list or "liveStream" not in play_list:
        error_type = cast(dict[str, object], play_list.get("errorType") or {})
        title = error_type.get("title", "")
        content = error_type.get("content", "")
        error_msg = (title if isinstance(title, str) else "") + (content if isinstance(content, str) else "")
        logger.error(
            i18n.tr(
                "Failed URL: {url} Error message: {error_msg}", url=utils.mask_credentials(url), error_msg=error_msg
            )
        )
        return result

    live_stream = cast(dict[str, object], play_list.get("liveStream") or {})
    # liveStream 为空也意味着 IP 被封（非开播态），打印提示后按未开播返回。
    if not live_stream:
        logger.error("IP banned. Please change device or network.")
        return result

    author = cast(dict[str, object], play_list.get("author") or {})
    # M-9（2026-09-29）：.get("name", "") 的缺省只在「键不存在」时生效，快手网页端显式下发
    # "author": {"name": null} 时结果仍是 None，并向下游 clean_name() 蔓延。
    anchor_name = _dig_str(author, "name")
    result.update({"anchor_name": anchor_name})

    play_urls_obj = live_stream.get("playUrls")
    if play_urls_obj:
        play_url_list: object
        # 新接口 playUrls 为分 codec 的字典。SEV-2204 修复（2026-09-22）：原实现只认 "h264" 一个键，
        # 两种真实形态会**完全静默**地漏录：
        #   ① HEVC-only 房间的 playUrls 只含 "h265"（本仓其它平台明确支持 h265 选流）→ 落入
        #      下面那条 2024-11-28 起已失效的 list 死分支 → play_url_list 恒 [] → is_live 保持 False；
        #   ② "h264": null（键在值为空，快手常见降级形态）→ `"adaptationSet" not in None` 抛 TypeError
        #      → 被 @trace_error_decorator 吞成未开播。
        # 现按 codec 优先级遍历 play_urls_obj 中**实际存在**的键（h264 优先、缺失取 h265），
        # 每个候选都先做 isinstance 判空再取 adaptationSet。
        if isinstance(play_urls_obj, dict):
            play_urls_dict = cast(dict[str, object], play_urls_obj)
            play_url_list = []
            for codec_key in ("h264", "h265"):
                codec_block = play_urls_dict.get(codec_key)
                if not isinstance(codec_block, dict):
                    continue
                adaptation = cast(dict[str, object], codec_block.get("adaptationSet") or {})
                if not isinstance(adaptation, dict):
                    continue
                # 显式补 `or []`：与下方旧 list 分支口径一致，避免 representation 缺失时把 None
                # 与 is_live=True 一起返回（flv_url_list=None 会让上层遍历候选时炸掉）。
                play_url_list = adaptation.get("representation") or []
                if play_url_list:
                    break
            if not play_url_list:
                # 已判有 liveStream/playUrls 却拿不到任何候选（键改名/结构改版/风控降级）：
                # 按无源返回并留线索，不再静默当成「未开播」。
                _warn_api_abnormal(json.dumps(play_urls_dict, ensure_ascii=False), "快手 playUrls", codec_key, {})
                return result
        else:
            # TODO: Old version which not working at 20241128, could be removed if not working confirmed
            play_urls_list = cast(list[object], play_urls_obj) if isinstance(play_urls_obj, list) else []
            if not play_urls_list:
                return result
            first_item = cast(dict[str, object], play_urls_list[0])
            adaptation2 = cast(dict[str, object], first_item.get("adaptationSet") or {})
            play_url_list = adaptation2.get("representation", [])
        result.update({"flv_url_list": play_url_list, "is_live": True})

    return result


@trace_error_decorator
async def get_kuaishou_stream_data2(
    url: str, proxy_addr: OptionalStr = None, cookies: OptionalStr = None
) -> dict[str, object] | None:
    # 获取快手直播流数据（备用接口）
    headers = {
        "User-Agent": "ios/7.830 (ios 17.0; ; iPhone 15 (A2846/A3089/A3090/A3092))",
        "Accept-Language": "zh-CN,zh;q=0.8,zh-TW;q=0.7,zh-HK;q=0.5,en-US;q=0.3,en;q=0.2",
        # 仅保留直播间 Referer，移除原硬编码分享链接（含过期 shareToken/userId/photoId）
        "Referer": "https://live.kuaishou.com/",
        "content-type": "application/json",
    }
    if cookies:
        headers["Cookie"] = cookies
    else:
        # 未配置 cookie 时自动获取快手访客 did，避免硬编码过期凭据
        headers["Cookie"] = await _ensure_kuaishou_did(proxy_addr)
    try:
        # 快手 URL 形如 https://live.kuaishou.com/u/xxxx，提取 u/ 后的部分作为 eid
        if "/u/" in url:
            eid = url.split("/u/")[1].strip()
        else:
            raise ValueError("Failed to extract eid from kuaishou URL")
        data: dict[str, object] = {"source": 5, "eid": eid, "shareMethod": "card", "clientType": "WEB_OUTSIDE_SHARE_H5"}
        # 走的不是快手官方域名，而是 chenzhongtech 的第三方聚合接口（kpn=GAME_ZONE 为固定包名标识），
        # captchaToken 留空——该接口对游客基本不校验验证码，留空即可；带错 token 反而会被拒。
        app_api = "https://livev.m.chenzhongtech.com/rest/k/live/byUser?kpn=GAME_ZONE&captchaToken="
        json_str = _get_str_response(await async_req(url=app_api, proxy_addr=proxy_addr, headers=headers, data=data))
        json_data = _loads_dict(json_str)
        live_stream = cast(dict[str, object], json_data.get("liveStream") or {})
        user = cast(dict[str, object], live_stream.get("user") or {})
        anchor_name = user.get("user_name")
        result: dict[str, object] = {
            "type": 2,
            "anchor_name": anchor_name,
            "is_live": False,
        }
        # app 端用 living 布尔字段判定开播（非 status 数字），与 web 端语义不同；
        # 仅 living 为真才组装 m3u8/flv 多分辨率候选与 backup 地址。
        live_status = live_stream.get("living")
        if live_status:
            result["is_live"] = True
            backup_m3u8_url = live_stream.get("hlsPlayUrl")
            play_urls = cast(list[object], live_stream.get("playUrls") or [])
            first_play = cast(dict[str, object], play_urls[0]) if play_urls else {}
            backup_flv_url = first_play.get("url", "")
            multi_hls = cast(list[object], live_stream.get("multiResolutionHlsPlayUrls") or [])
            if multi_hls:
                first_hls = cast(dict[str, object], multi_hls[0])
                result["m3u8_url_list"] = first_hls.get("urls", [])
            multi_play = cast(list[object], live_stream.get("multiResolutionPlayUrls") or [])
            if multi_play:
                first_mp = cast(dict[str, object], multi_play[0])
                result["flv_url_list"] = first_mp.get("urls", [])
            result["backup"] = {"m3u8_url": backup_m3u8_url, "flv_url": backup_flv_url}
        # anchor_name 非空才返回本函数结果；为空说明直播间不存在/被风控，
        # 落到下方 except 兜底、统一回退 get_kuaishou_stream_data 再试一次。
        if result["anchor_name"]:
            return result
    # 兜底回退：本函数解析抛异常、或成功解析但 anchor_name 为空（房间不存在/被风控）时，
    # 都转去走 get_kuaishou_stream_data（网页 __INITIAL_STATE__ 路径）再试一次；
    # 注意即使本路径已拿到流地址，只要 anchor_name 为空也会触发这次回退，可能重复解析。
    except Exception as e:
        logger.error(
            i18n.tr(
                "{e}, Failed URL: {url}, preparing to switch to a backup plan for re-parsing.",
                e=e,
                url=utils.mask_credentials(url),
            )
        )
    return await get_kuaishou_stream_data(url, cookies=cookies, proxy_addr=proxy_addr)


@trace_error_decorator
async def get_huya_stream_data(
    url: str, proxy_addr: OptionalStr = None, cookies: OptionalStr = None
) -> dict[str, object]:
    # 获取虎牙直播数据
    # 依赖页面内联 `stream:` 对象；正则未命中即抛 ValueError，由装饰器/调用方回退到
    # 微信小程序接口 get_huya_app_stream_url，本函数不自行处理「未开播」语义。
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:148.0) Gecko/20100101 Firefox/148.0",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.8,zh-TW;q=0.7,zh-HK;q=0.5,en-US;q=0.3,en;q=0.2",
        # 移除原硬编码的长串过期 Cookie（含大量 session/token，多数为访客统计字段）
        # 未配置 cookie 时不发送 Cookie 头，让虎牙服务器在响应中重新下发访客 cookie
    }
    if cookies:
        headers["Cookie"] = cookies

    html_str = _get_str_response(await async_req(url=url, proxy_addr=proxy_addr, headers=headers))
    # 直播间页内联了 stream: {...} 对象，正则抠出后补一个右花括号收尾（截断在 iWebDefaultBitRate 前）。
    # 该内联结构随页面改版会变，缺失即抛错、交由上层回退到小程序接口（get_huya_app_stream_url）。
    json_str_matches = cast(list[str], re.findall('stream: (\\{"data".*?),"iWebDefaultBitRate"', html_str))
    if not json_str_matches:
        raise ValueError("Failed to find stream data")
    json_str = json_str_matches[0]
    return _loads_dict(json_str + "}")


@trace_error_decorator
async def get_huya_app_stream_url(
    url: str, proxy_addr: OptionalStr = None, cookies: OptionalStr = None
) -> dict[str, object]:
    # 通过虎牙微信小程序API获取直播流地址
    headers = {
        "User-Agent": "ios/7.830 (ios 17.0; ; iPhone 15 (A2846/A3089/A3090/A3092))",
        "xweb_xhr": "1",
        "referer": "https://servicewechat.com/wx74767bf0b684f7d3/301/page-frame.html",
        "accept-language": "zh-CN,zh;q=0.9",
    }

    if cookies:
        headers["Cookie"] = cookies
    # 微信小程序接口按纯数字 roomid 取流；URL 里可能是字母房间号（短链/主播号），
    # 需先抓页面用 ProfileRoom 正则反查出数字 roomid，否则直接报错要求用户换数字链接。
    # rstrip("/") 不可省：URL 以 / 结尾时 rsplit 得到空串，非数字空串会一路拼进
    # roomid= 参数、白发一次必败请求（MIN-2201）。
    room_id = url.split("?")[0].rstrip("/").rsplit("/", maxsplit=1)[-1]

    if any(char.isalpha() for char in room_id):
        # MIN-2201（2026-09-23）：正则与孪生副本 scripts/douyin_live_recorder_standalone.py 的
        # _HUYA_PROFILE_ROOM_RE **逐字一致**（以键名的起始引号作锚点，避免命中页面里其他
        # 同名子串）。此前主实现缺该锚点，是「副本比主实现更严」的反向漂移。
        html_str = _get_str_response(await async_req(url, proxy_addr=proxy_addr, headers=headers))
        room_id_match = re.search('"ProfileRoom":(.*?),"sPrivateHost', html_str)
        if room_id_match:
            # 页面内联 JSON 的 "ProfileRoom" 有数字（:6030242）与字符串（:"6030242"）两种形态，
            # 非贪婪捕获对后者会把引号一并收进来 → 原先直接拼出 roomid=%226030242%22，
            # 接口恒返回空房间、所有字母号虎牙房间静默按未开播。剥引号后一律走 isdigit 判定。
            room_id = room_id_match.group(1).strip().strip('"')
    # 非数字（含「URL 尾斜杠 → 空串」「页面改版 → 正则未命中」两条路径）一律早抛，
    # 绝不把坏 roomid 发出去。回归锁 tests/test_regression_2026_09_22_spider.py::TestHuyaLetterRoomId。
    if not room_id.isdigit():
        raise Exception('Please use "https://www.huya.com/+room_number" for recording')

    # mp.huya.com 小程序接口参数：m=Live/do=profileRoom 固定；showSecret=1 要求返回防盗链参数。
    params = {
        "m": "Live",
        "do": "profileRoom",
        "roomid": room_id,
        "showSecret": "1",
    }
    wx_app_api = f"https://mp.huya.com/cache.php?{urllib.parse.urlencode(params)}"
    json_str = _get_str_response(await async_req(url=wx_app_api, proxy_addr=proxy_addr, headers=headers))
    json_data = _loads_dict(json_str)
    data_field = cast(dict[str, object], json_data.get("data") or {})
    profile_info = cast(dict[str, object], data_field.get("profileInfo") or {})
    # M-9（2026-09-29）：虎牙小程序接口对被封禁/注销房间返回 "nick": null，
    # 裸 .get 取到 None 会随 {"anchor_name": None} 一路传到 clean_name()（同抖音 web 端判据）。
    anchor_name = _dig_str(profile_info, "nick")
    live_status = data_field.get("realLiveStatus")
    live_data = cast(dict[str, object], data_field.get("liveData") or {})
    live_title = live_data.get("introduction")
    # 小程序接口用字符串 "ON" 表示开播，与 web 端数字状态码不同；非 ON 直接按未开播返回。
    if live_status != "ON":
        return {"anchor_name": anchor_name, "is_live": False}
    else:
        stream_field = cast(dict[str, object], data_field.get("stream") or {})
        base_steam_info_list = cast(list[object], stream_field.get("baseSteamInfoList") or [])
        play_url_list: list[dict[str, object]] = []
        for i_obj in base_steam_info_list:
            i = cast(dict[str, object], i_obj)
            cdn_type = i.get("sCdnType")
            stream_name = i.get("sStreamName")
            flv_anti_code = i.get("sFlvAntiCode")
            s_flv_url = i.get("sFlvUrl")
            s_hls_url = i.get("sHlsUrl")
            hls_anti_code = i.get("sHlsAntiCode")
            # MIN-2202（2026-09-23）：整条 entry 的有效性只由 sStreamName 裁决。
            # 旧判据 `not (stream_name and flv_anti_code)` 用 **FLV 票据** 的有无去裁决整条
            # 候选，而 HLS 地址只依赖 sHlsUrl + sHlsAntiCode —— 房间只下发 HLS 票据（或该
            # CDN 线路本就不承载 FLV）时连 HLS 候选都被砍掉，全部线路如此即落到
            # 「在播但零候选」，与「虎牙 FLV-first + HLS 回退」的设计意图相悖。
            if not stream_name:
                continue

            # 直接使用小程序接口返回的原始防盗链参数（sHlsAntiCode/sFlvAntiCode），
            # 统一降为 http（实测 https 返回 403、仅 http 可用），并对所有 CDN 一致地做
            # 反爬参数替换（tars_mp→huya_webh5, bhct→bgct，缺失时幂等无副作用）。
            # suffix 显式区分 HLS(.m3u8)/FLV(.flv)，不可依据 host 推断（HLS/FLV host 路径同为 /src）。
            def _normalize(base: object, anti: object, suffix: str) -> str:
                if not (isinstance(base, str) and isinstance(anti, str) and base and anti):
                    return ""
                url = f"{base}/{stream_name}.{suffix}?{anti}"
                url = url.replace("https://", "http://")
                return url.replace("&ctype=tars_mp", "&ctype=huya_webh5").replace("&fs=bhct", "&fs=bgct")

            m3u8_url = _normalize(s_hls_url, hls_anti_code, "m3u8")
            flv_url = _normalize(s_flv_url, flv_anti_code, "flv")
            # 两路地址按各自票据的非空性分别产出（_normalize 缺一即回 ""），但**整条候选**
            # 至少要有一路可用才入列：否则 play_url_list 非空而 m3u8_url_list/flv_url_list
            # 全空，会返回「is_live=True 且无任何线路」的坏结果（原实现靠 FLV 票据判据顺带
            # 挡住了这种 entry，去掉该判据后必须在此补回，见 MIN-2202 注释）。
            if m3u8_url or flv_url:
                play_url_list.append({"cdn_type": cdn_type, "m3u8_url": m3u8_url, "flv_url": flv_url})

        if not play_url_list:
            return {"anchor_name": anchor_name, "is_live": True}

        # 候选排序：实测 HLS 可靠承载线路为 HS（AL/TX 常因该房间未启用该线路返回 403，
        # 且各线路共享完全相同的防盗链参数——403 非请求问题、而是线路未承载推流，随时可能切换）。
        # 故枚举全部候选交给 select_source_url 逐条按可达性校验，首位优先 HS 以最大化「首试即中」；
        # 不再固定取 index0（AL 抢占时徒增无谓探针）或固定 TX 优先（TX 同样会离线）。
        cdn_priority = ["HS", "HW", "TX", "AL"]

        def _rank(item: dict[str, object]) -> int:
            try:
                return cdn_priority.index(str(item.get("cdn_type")))
            except ValueError:
                return len(cdn_priority)

        ordered = sorted(play_url_list, key=_rank)
        selected_item = ordered[0]

        selected_cdn_type = selected_item.get("cdn_type")
        selected_m3u8 = selected_item.get("m3u8_url")
        selected_flv = selected_item.get("flv_url")
        selected_m3u8_url: str | None = selected_m3u8 if isinstance(selected_m3u8, str) else None
        selected_flv_url: str | None = selected_flv if isinstance(selected_flv, str) else None

        # record_url: 与所选 flv 同源，始终保持 http（https 实测 403）。
        record_url: str | None
        if selected_flv_url:
            record_url = selected_flv_url
        else:
            record_url = None

        # 弹幕所需三元组:yyid 取自 profileInfo;lChannelId/lSubChannelId 优先取 data 顶层
        # chTopId/subChId(部分响应含), 否则回退到 baseSteamInfoList[0](直播路径下必非空)。
        # 供 main.py 在 OD/BD/UHD 分支直接组装 ayyuid/topSid/subSid, 与 web 路径字段一致。
        first_steam_info = cast(dict[str, object], base_steam_info_list[0] if base_steam_info_list else {})
        yyid = profile_info.get("yyid")
        l_channel_id = data_field.get("chTopId") or first_steam_info.get("lChannelId")
        l_sub_channel_id = data_field.get("subChId") or first_steam_info.get("lSubChannelId")

        # 全部候选注入 m3u8_url_list/flv_url_list，供 select_source_url 逐条按可达性校验、
        # 首条可达即选用（动态规避离线 CDN 线路）。候选顺序已按 HS 优先排序。
        m3u8_url_list = [c.get("m3u8_url") for c in ordered if isinstance(c.get("m3u8_url"), str) and c.get("m3u8_url")]
        flv_url_list = [c.get("flv_url") for c in ordered if isinstance(c.get("flv_url"), str) and c.get("flv_url")]

        return {
            "anchor_name": anchor_name,
            "is_live": True,
            "m3u8_url": selected_m3u8_url,
            "m3u8_url_list": m3u8_url_list,
            "flv_url": selected_flv_url,
            "flv_url_list": flv_url_list,
            "record_url": record_url,
            "title": live_title,
            "yyid": yyid,
            "lChannelId": l_channel_id,
            "lSubChannelId": l_sub_channel_id,
        }


def md5(data: str) -> str:
    # 计算字符串的MD5哈希值
    # 入参为 str 故先 utf-8 编码（斗鱼 websec 的 enc_key/key 均为字符串）；被 get_token_js
    # 的签名迭代循环反复调用，是斗鱼 anti-bot 签名的核心一步，不可替换为其它哈希。
    return hashlib.md5(data.encode("utf-8")).hexdigest()


async def get_token_js(rid: str, did: str, proxy_addr: OptionalStr = None) -> dict[str, object]:
    # 获取斗鱼API请求签名参数
    # 签名失败（接口异常/风控/error!=0）时返回 {}，调用方 get_douyu_stream_data 据此判断并中断，
    # 而非拿空签名去请求必败的 play 接口（空签名会得到无意义响应而非明确报错）。
    try:
        key_url = f"https://www.douyu.com/wgapi/livenc/liveweb/websec/getEncryption?did={did}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
            + "Chrome/141.0.0.0 Safari/537.36",
            "Referer": f"https://www.douyu.com/{rid}",
        }
        json_str = _get_str_response(await async_req(url=key_url, proxy_addr=proxy_addr, headers=headers))
        key_data = _loads_dict(json_str)
        if key_data.get("error") != 0:
            return {}
        enc_key = cast(dict[str, object], key_data.get("data") or {})
        ts = int(time.time())
        # MID-2215 修复（2026-09-22）：原实现「非预期类型即取空串/0」，三字段任一异常都**零日志**降级：
        #   - rand_str/key 缺失/非 str → 空串，产物 auth 恒被拒，调用方却只见「无流」；
        #   - enc_time 若以字符串 "2" 下发 → isinstance(int) 为假 → 退化为 0 次迭代，同样必被拒。
        # 现 int(...) 容错解析 + min(..., 32) 上界：enc_time 是**响应驱动**的，异常大数值会在房间
        # 事件循环里跑无上限 md5 链，阻塞同循环的弹幕协程。
        # 三字段任一缺失即 warning 并 return {}（get_douyu_stream_data 已对 enc_data 这么做，另三个此前漏了）。
        rand_str_v = enc_key.get("rand_str")
        key_v = enc_key.get("key")
        if not isinstance(rand_str_v, str) or not rand_str_v or not isinstance(key_v, str) or not key_v:
            logger.warning(
                i18n.tr("斗鱼 websec 签名参数不完整: rand_str/key 缺失或类型异常，本轮跳过取流"),
            )
            return {}
        auth = rand_str_v
        key = key_v
        # MIN-2204 后半（2026-09-23）：enc_time 缺失/非数值**不得**再静默退化成 0 次迭代——
        # 0 次迭代产出的 auth 必被服务端拒，调用方只见「无流」，与 rand_str/key 同属
        # 「签名参数不完整」，须走同一条 warning + return {}（兑现上方注释的承诺）。
        # 原实现取 `enc_key.get("enc_time", 0)` 并以 `enc_time = 0` 兜住异常，两形态均零日志。
        # 容错解析保留：字符串 "2" 必须被当成 2（而非退化为 0 次迭代），故先 str() 再 int()。
        try:
            enc_time = int(str(enc_key.get("enc_time")))
        except TypeError, ValueError:
            logger.warning(
                i18n.tr("斗鱼 websec 签名参数不完整: enc_time 缺失或非数值，本轮跳过取流"),
            )
            return {}
        # 响应驱动的迭代次数必须夹上界：异常大数值会跑无上限 md5 链，阻塞本房间事件循环。
        enc_time = min(max(enc_time, 0), 32)
        # is_special==1 表示该房间走特殊签名分支，无需拼接 rid+ts 的待签串；
        # 普通房间则把 rid+ts 作为待签内容参与 md5 链，漏拼会导致 auth 校验失败被拒。
        sign_str = "" if enc_key.get("is_special") == 1 else f"{rid}{ts}"
        for _ in range(enc_time):
            auth = md5(auth + key)
        auth = md5(auth + key + sign_str)
        return {"enc_data": enc_key.get("enc_data"), "did": did, "ts": ts, "auth": auth}
    except Exception as e:
        logger.error(i18n.tr("Get douyu sign params error: {e}", e=e))
        return {}


# 斗鱼房间号提取：两种来源（?rid= 查询参数 / 路径首段）与一处归一。
# 旧实现是两处整串正则，各有一个边界洞：
#   ① `rid=(.*?)(?=&|$)` 未锚定参数边界 —— ?xyzrid=123 这类参数会被误命中成房间号；
#   ② `douyu.com/(.*?)(?=\?|$)` 把尾斜杠与后续路径段一起带进房间号（/8751648/ → "8751648/"、
#      /topic/x → "topic/x"），于是 betard 请求拿不到 room，用户只看到「房间不存在」这类误导。
# 换 urlsplit 后 scheme / 尾斜杠 / query / fragment 都在解析层剥掉，http 与 https、
# www.douyu.com 与 m.douyu.com 走同一口径（移动端链接接入即依赖此点）。
def extract_douyu_rid_param(url: str) -> str:
    # 取 ?rid= / &rid= 参数值（参数边界锚定）；无该参数或值为空时返回空串，由调用方决定后续
    match = re.search(r"[?&]rid=([^&#]*)", url)
    return match.group(1) if match else ""


def extract_douyu_room_id(url: str) -> str:
    # 取斗鱼链接**路径首个非空段**作为房间号候选（可能是字母号，还原成数字 rid 由调用方负责）。
    # 无 scheme 时按准入侧同一规则补 `https://`——否则 urlsplit 会把 "m.douyu.com/8751648"
    # 整串当成 path，首个非空段取到的是主机名而非房间号。
    # 房间号候选来自用户手填，链接可带 token 类查询参数，故入错误消息前先脱敏。
    masked_url = utils.mask_credentials(url)
    try:
        path = urllib.parse.urlsplit(url if "://" in url else f"https://{url}").path
    except ValueError as e:
        raise ValueError(i18n.tr("斗鱼链接无法解析房间号: {masked_url}", masked_url=masked_url)) from e
    segments = [seg for seg in path.split("/") if seg]
    if not segments:
        raise ValueError(i18n.tr("斗鱼链接缺少房间号: {masked_url}", masked_url=masked_url))
    return segments[0]


@trace_error_decorator
async def get_douyu_info_data(
    url: str, proxy_addr: OptionalStr = None, cookies: OptionalStr = None
) -> dict[str, object]:
    # 获取斗鱼直播间基本信息
    headers = {
        "User-Agent": "ios/7.830 (ios 17.0; ; iPhone 15 (A2846/A3089/A3090/A3092))",
        "Referer": "https://m.douyu.com/3125893?rid=3125893&dyshid=0-96003918aa5365bc6dcb4933000316p1&dyshci=181",
        # 移除原硬编码的斗鱼登录态 Cookie（含 acf_auth/dy_auth/acf_uid 等用户登录凭据）
        # 未配置 cookie 时不发送 Cookie 头，斗鱼服务器会下发访客 cookie 用于公开直播间访问
    }
    if cookies:
        headers["Cookie"] = cookies

    # 斗鱼 URL 形态不一：带 rid= 查询参数的直链可直接取到房间号；
    # 否则从路径首段抠房间号（可能是字母号），再抓移动端 vike_pageContext 还原成真正的数字 rid
    # （web 端 betard 接口只认数字 rid，字母号/分享短链必须先解析），否则取流必失败。
    query_rid = extract_douyu_rid_param(url)
    if query_rid.isdigit():
        rid = query_rid
    else:
        # rid 参数不是数字（?rid=abc 这类畸形直链）时**不认它**：旧实现会拿它直拼 betard，
        # 必然失败且没有任何提示。此时回落到路径首段，仍拿不到才报「缺少房间号」。
        # 路径形态一律抓移动端页面还原（含已是纯数字的情形——按维护者口径保持现状，
        # 不做「数字即跳过抓取」的快路径，www 与 m 两侧行为因此完全一致）。
        rid_candidate = extract_douyu_room_id(url)
        html_str = await async_req(url=f"https://m.douyu.com/{rid_candidate}", proxy_addr=proxy_addr, headers=headers)
        html_str = _get_str_response(html_str)
        json_str_matches = re.findall('<script id="vike_pageContext" type="application/json">(.*?)</script>', html_str)
        if not json_str_matches:
            raise ValueError("Failed to find vike_pageContext")
        json_str = json_str_matches[0]
        # MID-48（2026-09-20）：vike_pageContext 与 betard 两处裸 json.loads + 深层链式索引改为
        # _loads_dict + .get——平台返回 HTML 拦截页/截断 JSON 时不再抛 JSONDecodeError/KeyError
        # 被装饰器整体吞成「未开播」，而是留明确线索。
        json_data = _loads_dict(json_str)
        page_props = cast(dict[str, object], json_data.get("pageProps") or {})
        room_wrap = cast(dict[str, object], page_props.get("room") or {})
        room_info = cast(dict[str, object], room_wrap.get("roomInfo") or {})
        inner_room = cast(dict[str, object], room_info.get("roomInfo") or {})
        if inner_room.get("rid") is None:
            raise ValueError("Failed to find rid in vike_pageContext (WAF page? truncated JSON?)")
        rid = str(inner_room["rid"])
        # betard / getH5PlayV1 两个接口只认数字 rid：还原产物非数字时直拼 URL 只会拿到
        # 「响应缺少 room 字段」这类误导性结果，故在还原出口就判掉并给出明确原因。
        if not rid.isdigit():
            raise ValueError(
                i18n.tr("斗鱼房间号还原结果非数字: candidate={candidate} rid={rid}", candidate=rid_candidate, rid=rid)
            )

    # 抓 vike_pageContext 时用 ios UA（移动端页面模板），真正取房间信息切回桌面 Firefox UA：
    # betard 接口按桌面端返回结构解析，UA 不对会拿到不同的页面骨架导致字段取不到。
    headers["User-Agent"] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:148.0) Gecko/20100101 Firefox/148.0"
    url2 = f"https://www.douyu.com/betard/{rid}"
    json_str = await async_req(url=url2, proxy_addr=proxy_addr, headers=headers)
    json_str = _get_str_response(json_str)
    json_data = _loads_dict(json_str)
    room = cast(dict[str, object], json_data.get("room") or {})
    if not room:
        # MID-48：区分两种成因落日志——「空响应」是风控/网络信号（async_req 失败已归一为 ""），
        # 「非空但缺 room」是房间不存在/接口改版/WAF 页。原实现两者都抛 KeyError 被装饰器
        # 静默吞成 {"is_live": False}，日志上完全不可分辨（用户只见持续「网址内容获取失败」）。
        #
        # MID-2214（2026-09-22）：原写法用字符串**拼接**做首参（"Douyu betard abnormal for rid=" + str(rid)
        # + ": " + reason）——全仓唯一一条拼接式形参日志，既进不了 zh_CN.po 也进不了四语目录
        # （提取器与测试判据都只看 JoinedStr 子树）。改为 i18n.tr 模板 + 具名参数。
        reason = (
            i18n.tr("空响应（风控或网络失败）")
            if not json_str
            else i18n.tr("响应缺少 room 字段（房间不存在 / 接口改版 / WAF 页）")
        )
        logger.warning(i18n.tr("斗鱼 betard 响应异常: rid={rid} reason={reason}", rid=rid, reason=reason))
        raise ValueError("douyu betard response has no room info: " + reason)
    nickname_v = room.get("nickname")
    result: dict[str, object] = {"anchor_name": nickname_v if isinstance(nickname_v, str) else "", "is_live": False}
    # 斗鱼「show_status==1 且 videoLoop==0」才视为真开播：videoLoop!=0 多为轮播/回放，
    # 不应被当作直播录制（否则录到循环播放的录像）。
    if room.get("videoLoop") == 0 and room.get("show_status") == 1:
        room_name_v = room.get("room_name")
        result["title"] = room_name_v.replace("&nbsp;", "") if isinstance(room_name_v, str) else ""
        result["is_live"] = True
        result["room_id"] = room.get("room_id")
    return result


@trace_error_decorator
async def get_douyu_stream_data(
    rid: str, rate: str = "-1", proxy_addr: OptionalStr = None, cookies: OptionalStr = None
) -> dict[str, object]:
    # 获取斗鱼直播间流地址
    # did 是写死的游客设备标识（来自抓包、非真实设备号，也非登录态）：斗鱼服务端对游客宽容、
    # 不校验其真伪，用固定值即可正常签名，改了反而可能触发风控；斗鱼的 websec 签名依赖它。
    # 签名失败（sign_params 为空）时返回 {error:-1,...} 让调用方显式中断，而非静默返回 None
    # （None 会被误判为「未开播」空转）。本函数直接透传接口原始 json（含 code/msg），
    # 由调用方按 code 决定重试或回退。
    did = "10000000000000000000000000003306"
    sign_params = await get_token_js(rid, did, proxy_addr=proxy_addr)
    if not sign_params:
        return {"error": -1, "msg": "Failed to get sign params", "data": {}}
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/141.0.0.0 Safari/537.36",
        "Referer": f"https://www.douyu.com/{rid}",
        "Content-Type": "application/x-www-form-urlencoded",
    }
    if cookies:
        headers["Cookie"] = cookies

    # MID-49 修复（2026-09-20）：原实现把 enc_data 等值手工拼接进 f-string 表单体——
    # enc_data 是 base64 序列化产物，其中的 & / = / + / % 会直接破坏表单字段结构
    # （服务端解析到的 enc_data 被截断）；且接口 error==0 但缺 enc_data 时，body 会
    # 变成字面量 enc_data=None，斗鱼返回接口错误、被上层伪装成「无流」。
    # 改为传 dict 交给 async_http 的 data=dict 分支（httpx 统一 urlencode 编码），
    # enc_data 缺失时直接返回 {} 走调用方（stream.get_douyu_stream_url）的取流失败告警分支。
    enc_data_raw = sign_params.get("enc_data")
    if not isinstance(enc_data_raw, str) or not enc_data_raw:
        logger.warning("Douyu websec sign params incomplete: enc_data missing, skip getH5PlayV1 this round")
        return {}
    post_data = {
        "enc_data": enc_data_raw,
        "tt": str(sign_params["ts"]),
        "did": str(sign_params["did"]),
        "auth": str(sign_params["auth"]),
        "cdn": "",
        "rate": rate,
        "hevc": "0",
        "fa": "0",
        "ive": "0",
    }
    app_api = f"https://www.douyu.com/lapi/live/getH5PlayV1/{rid}"
    json_str = await async_req(url=app_api, proxy_addr=proxy_addr, headers=headers, data=post_data)
    json_str = _get_str_response(json_str)
    return _loads_dict(json_str)


@trace_error_decorator
async def get_yy_stream_data(
    url: str, proxy_addr: OptionalStr = None, cookies: OptionalStr = None
) -> dict[str, object]:
    # 获取 YY 直播流数据
    # 解析链路：先抓主播页抠昵称 + cid，再用写死的 stream-manager 模板请求拿流（游客 uid=0 即可）；
    # 返回 is_live + flv/m3u8；昵称/cid 抠不到直接抛 ValueError，由装饰器上层按「未开播」兜底重试。
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36 Edg/141.0.0.0",
        "Accept-Language": "zh-CN,zh;q=0.8,zh-TW;q=0.7,zh-HK;q=0.5,en-US;q=0.3,en;q=0.2",
        "Referer": "https://www.yy.com/",
        # 移除原硬编码的 YY 访客统计 Cookie（hd_newui/hdjs_session_id 等均为临时统计字段）
        # 未配置 cookie 时不发送 Cookie 头，YY 服务器会在响应中重新下发访客 cookie
    }
    if cookies:
        headers["Cookie"] = cookies

    html_str = await async_req(url=url, proxy_addr=proxy_addr, headers=headers)
    html_str = _get_str_response(html_str)
    anchor_name_match = re.search('nick: "(.*?)",\n\\s+logo', html_str)
    if not anchor_name_match:
        raise ValueError("Failed to find anchor name")
    anchor_name = anchor_name_match.group(1)
    cid_match = re.search('sid : "(.*?)",\n\\s+ssid', html_str, re.DOTALL)
    if not cid_match:
        raise ValueError("Failed to find cid")
    cid = cid_match.group(1)

    # 下面这份 JSON 是抓包得到的真实 stream-manager 请求模板：head.seq / client_ver 等是
    # 固定写死的历史值，服务端对游客（uid64=0）宽容、不校验这些字段真伪；client_type=108
    # 标识 web 端。改动这些值需重新抓包，否则可能拿不到流。
    data = (
        '{"head":{"seq":1701869217590,"appidstr":"0","bidstr":"121","cidstr":"'
        + cid
        + '","sidstr":"'
        + cid
        + '","uid64":0,"client_type":108,"client_ver":"5.17.0","stream_sys_ver":1,"app":"yylive_web","playersdk_ver":"5.17.0","thundersdk_ver":"0","streamsdk_ver":"5.17.0"},"client_attribute":{"client":"web","model":"web0","cpu":"","graphics_card":"","os":"chrome","osversion":"0","vsdk_version":"","app_identify":"","app_version":"","business":"","width":"1920","height":"1080","scale":"","client_type":8,"h265":0},"avp_parameter":{"version":1,"client_type":8,"service_type":0,"imsi":0,"send_time":1701869217,"line_seq":-1,"gear":4,"ssl":1,"stream_format":0}}'
    )
    data_bytes = data.encode("utf-8")
    params = {"uid": "0", "cid": cid, "sid": cid, "appid": "0", "sequence": "1701869217590", "encode": "json"}
    url2 = f"https://stream-manager.yy.com/v3/channel/streams?{urllib.parse.urlencode(params)}"
    json_str = await async_req(url=url2, data=data_bytes, proxy_addr=proxy_addr, headers=headers)
    json_str = _get_str_response(json_str)
    # MID-48（2026-09-21）：裸 json.loads → _loads_dict。WAF/HTML 页此前抛 JSONDecodeError
    # 被装饰器吞成 {"is_live": False}，与「主播未开播」不可区分（YY 未开播时响应正常、
    # 只是不含 avp_info_res，由 stream.get_yy_stream_url 判离线）。故只在「整个响应解析不出
    # 对象」时告警，avp_info_res 缺失本身是正常离线形态、不刷日志。
    json_data = _loads_dict(json_str)
    if not json_data:
        _warn_api_abnormal(json_str, "YY stream-manager", "avp_info_res", json_data)
        # MID-2215（2026-09-23）评审项**未按建议改动**，留此说明避免下次重复排查：
        # 建议形态是「空响应分支显式返回 {"type": 1, "is_live": False}（不带 anchor_name）」，
        # 让 main.py 走 `not port_info["anchor_name"]` 的 record_error 分支。但
        # ① 该契约已被 tests/test_spider_hardening.py::TestYyHardening.check_offline
        #    锁死（「昵称来自第一段页面正则，异常响应不得把它一起吞掉」，断言 abnormal
        #    用例的 anchor_name == 页面昵称），去掉即变红；
        # ② 语义上也站不住：anchor_name 来自**主播页**（host 即 record_url 的 www.yy.com），
        #    本轮该 host 的请求是成功的；失败的是 stream-manager.yy.com **另一个 host**，
        #    而 PlatformBreaker 的键是 record_url 的 host（main.start_record 的 record_host），
        #    把失败记到 www.yy.com 反而会在「主播页正常、只是取流接口被限」时误熔断整站房间。
        # 结论：保持返回带 anchor_name 的未开播结构（与既有锁一致）。
    # stream-manager 响应只含流地址、不含主播名（昵称来自前面页面正则抠取），
    # 手动把 anchor_name 塞进返回结构，供下游统一按 key 取用。
    json_data["anchor_name"] = anchor_name

    # 第二次请求单独取房间标题（detail 接口），sequence 改用实时时间戳；两次请求串起
    # 主播名（来自页面）+ 流地址（来自 stream-manager）+ 标题（来自 detail）。
    params = {
        "uid": "",
        "sid": cid,
        "ssid": cid,
        "_": int(time.time() * 1000),
    }
    # MI-18 修复：标题接口是**独立的第二次请求**且只用于装饰文件名，原实现却没做任何判空——
    # detail 接口返回错误页/空 body 时 json.loads 抛 JSONDecodeError，返回体无 data.roomName
    # 时抛 KeyError/TypeError，两者都会被外层 @trace_error_decorator 降级为
    # {"is_live": False}，把前面 stream-manager 已经成功取到的流地址一并作废：
    # YY 直播间在 detail 接口抖动时「在播却漏录」，而标题本不值得让整路录制失败。
    detail_api = f"https://www.yy.com/live/detail?{urllib.parse.urlencode(params)}"
    try:
        json_str2 = await async_req(detail_api, proxy_addr=proxy_addr, headers=headers)
        json_str2 = _get_str_response(json_str2)
        json_data2 = _loads_dict(json_str2)
        _detail_data = json_data2.get("data")
        if isinstance(_detail_data, dict):
            json_data["title"] = _detail_data.get("roomName") or json_data.get("title", "")
    except Exception as e:
        # 标题拿不到不影响取流：留一条 warning 便于定位，然后用空标题继续返回
        logger.warning(i18n.tr("YY 标题补取失败（不影响取流）: {type_name}", type_name=type(e).__name__))
        json_data["title"] = json_data.get("title", "")
    return cast(dict[str, object], json_data)


@trace_error_decorator_or_none
async def get_bilibili_room_info_h5(url: str, proxy_addr: OptionalStr = None, cookies: OptionalStr = None) -> str:
    # 获取 B站直播间 H5 接口信息
    # 失败时返回 ""（而非 None）：调用方以 `title = ... or ""` 兜底，None 会破坏该兜底并
    # 使 get_bilibili_room_info 跨接口拼装标题时 TypeError。
    headers = {
        "user-agent": "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/141.0.0.0 Mobile Safari/537.36",
        "accept-language": "zh-CN,zh;q=0.8,zh-TW;q=0.7,zh-HK;q=0.5,en-US;q=0.3,en;q=0.2",
        "cookie": "",
        "origin": "https://live.bilibili.com",
        "referer": "https://live.bilibili.com/26066074",
    }
    # 调用方透传 cookie 时优先采用；否则走游客态/自动获取凭据（各平台未登录态取流能力不一，部分更易被风控）
    if cookies:
        headers["cookie"] = cookies

    room_id = _safe_extract_id(url)
    api = f"https://api.live.bilibili.com/xlive/web-room/v1/index/getH5InfoByRoom?room_id={room_id}"
    json_str = await async_req(api, proxy_addr=proxy_addr, headers=headers)
    json_str = _get_str_response(json_str)
    # MID-48：`room_info["data"]["room_info"]` 在接口返回 HTML/截断 JSON 时抛 JSONDecodeError、
    # 在 data 为 null 时抛 TypeError，两者都被本函数的 _or_none 装饰器变成 None，
    # 与「房间无标题」不可区分。改为 _loads_dict + .get 链：取不到即空串（上层 `or ""` 兜底），
    # data 整体缺失（风控信封 / 解析失败）时留一条区分性告警。
    room_info = _loads_dict(json_str)
    if _dig(room_info, "data") is None:
        _warn_api_abnormal(json_str, "B站 getH5InfoByRoom", "data.room_info.title", room_info)
    return _dig_str(room_info, "data", "room_info", "title")


@trace_error_decorator
async def get_bilibili_room_info(
    url: str, proxy_addr: OptionalStr = None, cookies: OptionalStr = None
) -> dict[str, object]:
    # 获取 B站直播间信息（含主播名）
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:148.0) Gecko/20100101 Firefox/148.0",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.8,zh-TW;q=0.7,zh-HK;q=0.5,en-US;q=0.3,en;q=0.2",
    }
    # 调用方透传 cookie 时优先采用；否则走游客态/自动获取凭据（各平台未登录态取流能力不一，部分更易被风控）
    if cookies:
        headers["Cookie"] = cookies

    try:
        room_id = _safe_extract_id(url)
        json_str = await async_req(
            f"https://api.live.bilibili.com/room/v1/Room/room_init?id={room_id}", proxy_addr=proxy_addr, headers=headers
        )
        json_str = _get_str_response(json_str)
        # MID-48（2026-09-21）：room_init / master/info 两处裸 json.loads + 四级链式索引改为
        # _loads_dict + _dig。B站对不存在/未开通的房间回 code!=0 且不含 data，此前与
        # 「接口改版 / WAF 页」同样抛 KeyError → 落到下方那条笼统告警，用户无从分辨。
        room_info = _loads_dict(json_str)
        uid = _dig(room_info, "data", "uid")
        if uid is None:
            _warn_api_abnormal(json_str, "B站 room_init", "data.uid", room_info)
            return {"anchor_name": "", "live_status": False, "room_url": url}
        live_status = _dig(room_info, "data", "live_status") == 1

        api = f"https://api.live.bilibili.com/live_user/v1/Master/info?uid={uid}"
        json_str2 = await async_req(url=api, proxy_addr=proxy_addr, headers=headers)
        json_str2 = _get_str_response(json_str2)
        anchor_info = _loads_dict(json_str2)
        anchor_name = _dig_str(anchor_info, "data", "info", "uname")
        if not anchor_name:
            _warn_api_abnormal(json_str2, "B站 master/info", "data.info.uname", anchor_info)
            return {"anchor_name": "", "live_status": False, "room_url": url}

        # L-08（2026-10-02）：补 `or ""` 兜底（对齐函数头注释的契约）——兜底装饰器
        # trace_error_decorator_or_none 失败时返回 None，无兜底时 None 会作为 title 入 dict，
        # get_bilibili_room_info 跨接口拼装标题时 TypeError。
        title = await get_bilibili_room_info_h5(url, proxy_addr, cookies) or ""
        return {"anchor_name": anchor_name, "live_status": live_status, "room_url": url, "title": title}
    except Exception as e:
        # 房间信息抓取失败（房间不存在/风控/网络）一律返回空名+未开播，交由主循环下轮重试，
        # 不中断整体监控；anchor_name 用 "" 保证下游拼接标题时不会因 None 而 TypeError。
        # WD-19 修复：原用 logger.info 只记异常对象——级别低于 warning，常规日志级别下
        # 这条**唯一线索**会被直接过滤掉；且不带 URL 与异常类型，无法区分 cookie 失效、
        # -352 风控、房间真不存在还是网络问题，与同文件其它错误路径的口径也不一致。
        # MID-2219（2026-09-23）：url 必须过脱敏——用户可粘贴带 token 查询参数的地址，
        # 而该行走 logger 文件 sink（300 KB 轮转保留多份 = 凭据长期落盘）。同文件其余
        # url= 实参（快手两条解析路径等）早已这么脱敏，此处曾是唯一漏网的一个。
        logger.warning(
            i18n.tr(
                "B站房间信息获取失败（下轮重试）: url={url} - {type_name}: {e}",
                url=utils.mask_credentials(url),
                type_name=type(e).__name__,
                e=e,
            )
        )
        return {"anchor_name": "", "live_status": False, "room_url": url}


@trace_error_decorator
async def get_bilibili_stream_data(
    url: str, qn: str = "10000", platform: str = "web", proxy_addr: OptionalStr = None, cookies: OptionalStr = None
) -> dict[str, object] | None:
    # 获取 B站直播流数据（多清晰度），返回 {url, current_qn, accept_qn}
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:148.0) Gecko/20100101 Firefox/148.0",
        "Accept-Language": "zh-CN,zh;q=0.8,zh-TW;q=0.7,zh-HK;q=0.5,en-US;q=0.3,en;q=0.2",
        "origin": "https://live.bilibili.com",
        "referer": "https://live.bilibili.com/26066074",
    }
    # 调用方透传 cookie 时优先采用；否则走游客态/自动获取凭据（各平台未登录态取流能力不一，部分更易被风控）
    if cookies:
        headers["Cookie"] = cookies

    room_id = _safe_extract_id(url)
    params = {"cid": room_id, "qn": qn, "platform": platform}
    play_api = f"https://api.live.bilibili.com/room/v1/Room/playUrl?{urllib.parse.urlencode(params)}"
    json_str = await async_req(play_api, proxy_addr=proxy_addr, headers=headers)
    json_str = _get_str_response(json_str)
    # MID-48（2026-09-20）：旧 playUrl 分支裸 json.loads + 深索引改为 _loads_dict + .get。
    # 该接口被风控时常返回 WAF 页/空 body，原实现在此处抛 JSONDecodeError/KeyError 被装饰器
    # 直接吞掉，**绕过了下方 getRoomPlayInfo 回退与其「-352 一眼可见」告警路径**；
    # 解析失败回 {} 后 code 判定自然落入 else 分支，补救链恢复可用。
    json_data = _loads_dict(json_str)
    # B站 get_play_url 仅 code==0 返回有效 durl，否则无源
    if json_data.get("code") == 0:
        play_data = cast(dict[str, object], json_data.get("data") or {})
        durl_list = cast(list[dict[str, object]], play_data.get("durl", []))
        # durl 为空即无可用清晰度，返回 None
        if not durl_list:
            return None
        # playUrl 接口无 qn 元信息，current_qn 取请求值，accept_qn 未知
        target_url = None
        # 优先挑含 "d1--cn-gotcha" 子串的 CDN 地址（B站某可用线路 host 特征），
        # 没有命中再退回列表末位；是经验性的线路优选，非官方保证。
        # [历史注] 2026-09-20 删掉了相邻一条把优选方向说反（「跳过 gotcha、优先真实 CDN」）的注释。
        for i in durl_list:
            # durl_list 经 _loads_dict 解析后值为 object，子串匹配前统一转 str
            # （URL 恒为字符串；None 转成 "None" 也不会命中 gotcha 子串，无副作用）。
            if "d1--cn-gotcha" in str(i.get("url", "")):
                target_url = i["url"]
                break
        if not target_url:
            target_url = durl_list[-1].get("url")
        return {"url": target_url, "current_qn": qn, "accept_qn": [qn]}
    else:
        # 旧 playUrl 返回非 0（多为 -352/-412 风控或参数被拒）时，回退到 v2 getRoomPlayInfo
        # 接口：它返回更完整的清晰度/编码列表，是 B站当前的取流主路径。
        params = {
            "room_id": room_id,
            "protocol": "0,1",
            "format": "0,1,2",
            "codec": "0,1,2",
            "qn": qn,
            "platform": "web",
            "ptype": "8",
            "dolby": "5",
            "panorama": "1",
            "hdr_type": "0,1",
        }
        api = f"https://api.live.bilibili.com/xlive/web-room/v2/index/getRoomPlayInfo?{urllib.parse.urlencode(params)}"
        json_str = await async_req(api, proxy_addr=proxy_addr, headers=headers)
        json_str = _get_str_response(json_str)
        json_data = _loads_dict(json_str)
        # WD-19 修复：先判 code，再判 data 是否为空。
        # B 站在 -352（风控 / wbi 签名失效）时返回 {"code": -352, "data": null}，
        # 此时 json_data["data"] 为 None、None["live_status"] 直接抛 TypeError，
        # 被装饰器吞成 {"is_live": False}，日志丢失 -352 这一关键判据，
        # 排障时极易误判成「主播没开播」（本文件其余字段都做了判空，唯独顶层 data 没做）。
        # MID-2216（2026-09-23）：原判据 `not in (0, None)` 把 None 划进「正常」侧，而 None
        # 恰恰是「空 body / 响应不是 JSON（WAF 壳页）」经 _loads_dict 归一后的形态——
        # 最需要线索的那一类落到 data_obj={} → live_status!=0 → stream_list=[] → 整轮零日志，
        # 与「主播没开播」完全不可区分（正是 WD-19 要消灭的形态）。现拆开两种语义：
        # 整体为空 → 归因告警；带非 0 code → 原样告警。
        if not json_data:
            _warn_api_abnormal(json_str, "B站 getRoomPlayInfo", "code + data", json_data)
            return None
        if json_data.get("code") is not None and json_data.get("code") != 0:
            logger.warning(
                i18n.tr("B站接口返回异常 code={code}（疑似风控/签名失效），本轮跳过", code=json_data.get("code"))
            )
            return None
        data_obj = json_data.get("data") or {}
        if not isinstance(data_obj, dict):
            return None
        # live_status==0 表示未开播（1 为开播），此时 playurl_info 不存在，按未开播返回 None。
        if data_obj.get("live_status") == 0:
            logger.info("The anchor did not start broadcasting.")
            return None
        playurl_info = data_obj.get("playurl_info") or {}
        if not isinstance(playurl_info, dict):
            return None
        # WD-19：playurl 同样可能缺失（风控/未开播竞态），改为 get 链式取值
        _playurl = playurl_info.get("playurl") or {}
        stream_list = _playurl.get("stream", []) if isinstance(_playurl, dict) else []
        # stream_list 字段缺失即无可用流，返回 None
        if not stream_list:
            return None
        format_list = stream_list[0].get("format", [])
        # format_list 字段缺失即无可用流，返回 None
        if not format_list:
            return None
        stream_data_list = format_list[0].get("codec", [])
        # stream_data_list 为空即无可用流，返回 None
        if not stream_data_list:
            return None
        sorted_stream_list: list[dict[str, object]] = sorted(
            stream_data_list, key=itemgetter("current_qn"), reverse=True
        )
        # qn 字符串到「选择下标」的映射：10000=原画、400=蓝光、250=超清、150=高清、80=流畅。
        # MIN-2201 修复（2026-09-22）：原注释写「回退到**最高**可用清晰度」，但 min(映射值, qn_count-1)
        # 的实际语义是**就近向下取档**——sorted_stream_list 已按 current_qn 降序，映射下标越大档位越低，
        # 请求档位不在可用集合时 min 取到的是 qn_count-1，即**最低**可用档（房间只有 [10000,80] 时请求
        # 蓝光 400 → 取下标 1 → 80 流畅），与注释相反且无降级告警（虎牙/斗鱼分支都有，B站没有）。
        # 现保持「就近向下」的既有行为不变（避免改动线上已习惯的选档结果），仅改正注释并在
        # 实际落入的档位与请求档位不一致时落一条 WARNING，与 get_huya_stream_url 的降级告警口径对齐。
        video_quality_options = {"10000": 0, "400": 1, "250": 2, "150": 3, "80": 4}
        qn_count = len(sorted_stream_list)
        requested_index = video_quality_options.get(qn, 0)
        select_stream_index = min(requested_index, qn_count - 1)
        if select_stream_index != requested_index:
            logger.warning(
                i18n.tr(
                    "B站请求清晰度 {qn} 不可用，就近降级到 {actual_qn}",
                    qn=qn,
                    actual_qn=sorted_stream_list[select_stream_index].get("current_qn", ""),
                )
            )
        stream_data: dict[str, object] = sorted_stream_list[select_stream_index]
        base_url = cast(str, stream_data["base_url"])
        url_info = stream_data.get("url_info", [])
        # url_info 字段缺失即无可用流，返回 None
        if not url_info:
            return None
        url_info_list = cast(list[dict[str, object]], url_info)
        host = cast(str, url_info_list[0].get("host", ""))
        extra = cast(str, url_info_list[0].get("extra", ""))
        m3u8_url = host + base_url + extra
        current_qn = str(stream_data.get("current_qn", qn))
        accept_qn = [str(s.get("current_qn")) for s in sorted_stream_list]
        # 最终解析出 m3u8 才返回，否则返回 None
        return {"url": m3u8_url, "current_qn": current_qn, "accept_qn": accept_qn}


# B站 wbi 签名混排表（官方固定 64 位置换，用于将 img_key+sub_key 截取为 32 位 mixinKey）
_MIXIN_KEY_ENC_TAB = [
    46,
    47,
    18,
    2,
    53,
    8,
    23,
    32,
    15,
    50,
    10,
    31,
    58,
    3,
    45,
    35,
    27,
    43,
    5,
    49,
    33,
    9,
    42,
    19,
    29,
    28,
    14,
    39,
    12,
    38,
    41,
    13,
    37,
    48,
    7,
    16,
    24,
    55,
    40,
    61,
    26,
    17,
    6,
    60,
    21,
    57,
    59,
    62,
    11,
    36,
    20,
    51,
    54,
    25,
    1,
    34,
    56,
    30,
    4,
    22,
    44,
    52,
    63,
    0,
]


def _get_mixin_key(orig: str) -> str:
    # 按官方混排表从 img_key+sub_key 截取 32 位 mixinKey
    return "".join(orig[i] for i in _MIXIN_KEY_ENC_TAB)[:32]


def _sign_wbi(params: dict[str, str], img_key: str, sub_key: str) -> dict[str, str]:
    # 生成 w_rid 签名：拼接 img_key+sub_key -> mixinKey -> 追加参数并 md5
    #
    # 2026-09-12 审查（低危）：原实现直接改写调用方传入的 params（就地插入 wts/w_rid）。
    # 调用方多处复用同一个字典做「签名前的原始参数」与「签名后的请求参数」，副作用会
    # 让前者被污染——典型后果是重试/多分支共享同一 dict 时 wts 未刷新导致签名过期失败，
    # 且这类问题表现为偶发、难复现。改为对副本操作后返回新 dict；同时用 pop 显式剔除
    # 已存在的 w_rid，避免旧签名残留参与本次计算（原实现无此处理）。
    signed = dict(params)
    signed.pop("w_rid", None)
    mixin_key = _get_mixin_key(img_key + sub_key)
    signed["wts"] = str(int(time.time()))
    query = urllib.parse.urlencode(sorted(signed.items()))
    signed["w_rid"] = hashlib.md5((query + mixin_key).encode("utf-8")).hexdigest()
    return signed


# B站 buvid 缓存：设备级标识（非房间级），进程内首次获取/生成后全局复用，
# 避免每个监测周期重复请求 spi 反复触发 B站风控（200+空 body，越取越失败的循环）
_bili_buvid_lock = threading.Lock()
_bili_buvid_cached = ""
# 当前缓存值是否为「生成的随机 UUID 兜底」（非服务器注册的真实设备标识）。
# 弹幕服务器对未注册 buvid 的 AUTH 会软拒绝；客户端收到拒绝后经
# invalidate_bili_buvid_cache() 清除缓存，下一轮监测重新走真实获取链。
_bili_buvid_is_fallback = False
# MID-40：记录当前缓存值产生时使用的代理上下文——通用 singleflight 键含 proxy，
# 失效时须按同一形态清对键（调用方未显式传参时也能清掉刚缓存被拒的那份）。
_bili_buvid_cached_proxy = ""


def _take_cached_bili_buvid(proxy_addr: OptionalStr) -> str:
    # M-8（2026-09-29）：buvid 的进程级快路同样必须判「出口(proxy)一致性」，判据与理由见
    # _take_cached_kuaishou_did（同一 bug 的第二处：下层 singleflight 键 f"bili_buvid3|{proxy}"
    # 与写入侧 _bili_buvid_cached_proxy 都带代理维度，唯独快路只看非空）。
    # 串用的后果比 did 更隐蔽：B站弹幕服务器按 AUTH 判定设备标识，代理 B 的房间拿着代理 A
    # 注册的 buvid3 进房 → AUTH 被软拒绝（弹幕静默收不到，视频照常录），而日志上看不到出口差异。
    # 与 did 不同，这份全局本来就没有 TTL 判定（设备级标识长期有效是既有语义），本轮只补出口维度、
    # 不顺手加 TTL——那会改变「真实 buvid 一旦拿到即永久复用」的既有行为与 MID-40 的失效链。
    if not _bili_buvid_cached:
        return ""
    if _bili_buvid_cached_proxy != (proxy_addr or ""):
        return ""
    return _bili_buvid_cached


def invalidate_bili_buvid_cache(proxy_addr: OptionalStr = None) -> None:
    # 使进程内 buvid 缓存失效（不清 cookie_cache 的首页 Set-Cookie TTL 缓存——那里存的
    # 是真实注册标识，可继续复用）。触发方为弹幕 AUTH 被拒：兜底 UUID 被服务器拒绝后
    # 不可复用，必须重新获取；真实 buvid 被拒时重取亦无副作用。
    # MID-40 修复（2026-09-20）：只清模块全局是**半条自愈链**——承载它的
    # cookie_cache.singleflight 通用缓存（键 f"bili_buvid3|{proxy}"、TTL 30 分钟）里
    # 仍留着被拒值，下一轮全局为空 → singleflight 命中 → 又被喂回同一份被拒 UUID，
    # 循环到 TTL 自然过期。故必须同时 invalidate_generic 该键；proxy 以形参透传，
    # 未传时按缓存写入时记录的代理清（覆盖 platforms/bilibili.py 的无参调用点）。
    global _bili_buvid_cached, _bili_buvid_is_fallback, _bili_buvid_cached_proxy
    with _bili_buvid_lock:
        _bili_buvid_cached = ""
        _bili_buvid_is_fallback = False
        recorded_proxy = _bili_buvid_cached_proxy
        _bili_buvid_cached_proxy = ""
    keys = {recorded_proxy}
    if proxy_addr is not None:
        keys.add(proxy_addr or "")
    for k in keys:
        _cache_invalidate_generic(f"bili_buvid3|{k}")


async def get_bilibili_danmaku_info(
    url: str, proxy_addr: OptionalStr = None, cookies: OptionalStr = None
) -> dict[str, object] | None:
    # 获取 B站弹幕连接参数（token/server_host/host_list/room_id/uid/buvid），供 BilibiliDanmaku 进房。
    # 必须带 wbi 签名，否则 getDanmuInfo 返回 -352 风控。短号房间需先 room_init 转为真实 room_id。
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:148.0) Gecko/20100101 Firefox/148.0",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-CN,zh;q=0.8,zh-TW;q=0.7,zh-HK;q=0.5,en-US;q=0.3,en;q=0.2",
        "origin": "https://live.bilibili.com",
        "referer": "https://live.bilibili.com",
    }
    # 调用方透传 cookie 时优先采用；否则走游客态/自动获取凭据（各平台未登录态取流能力不一，部分更易被风控）
    if cookies:
        headers["Cookie"] = cookies

    room_id = _safe_extract_id(url)

    # 1) room_init 取真实 room_id 与 uid（短号房间 URL 的 path id 可能是短号，需转换）
    real_room_id = room_id
    uid = 0
    init_api = f"https://api.live.bilibili.com/room/v1/Room/room_init?id={room_id}"
    # MID-2217（2026-09-23，同型第二处）：原先这三步包在 try/except Exception 里并打
    # 「room_init 失败」告警，但 async_req 吞尽传输层异常回 ""、_loads_dict 解析失败回 {}，
    # 中间每一步都不抛错 → 该告警**永不触发**。room_init 被风控时 real_room_id 静默沿用
    # URL 里的短号、uid 静默为 0（短号房间的弹幕连接因此建不起来），却没有任何线索指向这一步。
    # 现删死分支，改为对结果显式判空并按 MID-48 的统一口径归因（空响应 vs 缺字段带 code/msg）。
    init_str = _get_str_response(await async_req(init_api, proxy_addr=proxy_addr, headers=headers))
    init_data = _loads_dict(init_str)
    init_room: dict[str, object] = {}
    if isinstance(init_data, dict):
        d = init_data.get("data")
        if isinstance(d, dict):
            init_room = d
    if not init_room:
        _warn_api_abnormal(init_str, "B站 room_init", "data.room_id + data.uid", init_data)
    real_room_id = str(init_room.get("room_id") or room_id)
    _uid = init_room.get("uid")
    uid = int(_uid) if isinstance(_uid, int) else 0
    # 2) nav 取 wbi_img（img_key/sub_key）
    img_key = ""
    sub_key = ""
    try:
        nav_str = await async_req(
            "https://api.bilibili.com/x/web-interface/nav", proxy_addr=proxy_addr, headers=headers
        )
        nav_data = _loads_dict(_get_str_response(nav_str))
        nav_wbi: dict[str, object] = {}
        if isinstance(nav_data, dict):
            w = nav_data.get("data")
            if isinstance(w, dict):
                nw = w.get("wbi_img")
                if isinstance(nw, dict):
                    nav_wbi = nw
        img_url = str(nav_wbi.get("img_url", ""))
        sub_url = str(nav_wbi.get("sub_url", ""))
        img_key = img_url.rsplit("/", 1)[-1].split(".")[0]
        sub_key = sub_url.rsplit("/", 1)[-1].split(".")[0]
    except Exception as e:
        logger.warning(i18n.tr("[B站直播]nav(wbi) 获取失败: {type_name}: {e}", type_name=type(e).__name__, e=e))

    # 3) buvid 获取链（匿名弹幕进房也需要 buvid 字段），按「真实注册标识优先」排序：
    #    a. 进程缓存   —— 设备级标识，长期有效；
    #    b. 登录 cookie —— cookie 带 buvid3= 时提取（服务器注册过的最可靠来源）；
    #    c. spi 接口   —— 官方端点 /x/frontend/finger/spi（注意结尾 i，拼写错误会 200+空 body）。
    #                     偶发风控返回空响应体（200+空 body）→ _loads_dict 得 {}，重试一次再定罪；
    #    d. 首页 Set-Cookie —— GET https://www.bilibili.com/ 响应头下发真实注册 buvid3
    #                     （与 spi 不同域名，spi 被风控时通常仍可用；经 cookie_cache 复用）；
    #    e. 随机 UUID 兜底 —— 未注册标识，弹幕服务器 AUTH 会软拒绝；仅保进房包非空，
    #                     被拒后由 invalidate_bili_buvid_cache() 清除，下一轮重新获取。
    # 进房包带空 buvid 会被弹幕服务器硬断连（"no close frame received or sent"），故必须非空。
    #
    # 2026-09-12 审查 H-2：原实现为「with _bili_buvid_lock: 内含 3 处 await」——
    # 该锁是不可重入 threading.Lock，本项目「每房间独立线程 + 独立事件循环」下：
    #   ① 持锁协程 await 网络（最坏 30s+ 重试）期间，其它房间线程执行到 with 会
    #      同步阻塞其整个事件循环（多房间并发冷启动全部串行卡顿）；
    #   ② 同一事件循环内两个协程并发进入即互等，构成死锁。
    # 改为 cookie_cache.singleflight 去重：临界区仅做字典读写，网络请求全在锁外。
    # 兜底 UUID 仍缓存（is_fallback 标记），与原语义一致。
    global _bili_buvid_cached, _bili_buvid_is_fallback, _bili_buvid_cached_proxy

    async def _fetch_buvid() -> str:
        # 单条获取链（不含进程缓存层，由 singleflight 负责去重与缓存）
        # M-8（2026-09-29）：这里读全局也必须按出口取值。本函数跑在 singleflight 的 factory 里，
        # 返回值会被写进 **本次调用所用 proxy** 对应的那条桶（key=f"bili_buvid3|{proxy}"）——
        # 若这里直接取别出口的全局值，就等于把「A 的 buvid」固化进「B 的桶」，
        # 之后即便快路修好了，下层缓存仍在持续喂回串用值（比快路更难自愈）。
        b = _take_cached_bili_buvid(proxy_addr)
        if not b and cookies:
            _m = re.search(r"buvid3=([^;\s]+)", str(cookies))
            if _m and _m.group(1).strip():
                b = _m.group(1).strip()
                logger.debug(i18n.tr("[B站直播]使用 cookie 中的 buvid3: {buvid}", buvid=b))
        if not b:
            # MIN-2203 修复（2026-09-22）：原实现两次请求**零间隔**连击同一路径（对 CDN 探针有
            # _throttle_probe，对 spi 没有）；且 on-exception 的 except 分支在风控主形态下**永不执行**
            # ——「200+空 body」时 async_req 与 _loads_dict 都不抛，只是 b 仍为空，于是真正需要告警的
            # 「两跳皆空」反而无任何日志。现：空结果与异常两条路径都在重试前插入 0.5~1.0s 抖动退避
            # （与 stream_select._recheck_delay 同思路：固定节奏是风控指纹，抖动打散节奏），
            # 并在「两跳皆空」时落一条 warning 取代原先永不执行的 except。
            for _attempt in range(2):
                try:
                    spi_str = await async_req(
                        "https://api.bilibili.com/x/frontend/finger/spi", proxy_addr=proxy_addr, headers=headers
                    )
                    spi_data = _loads_dict(_get_str_response(spi_str))
                    spi_d: dict[str, object] = {}
                    if isinstance(spi_data, dict):
                        s = spi_data.get("data")
                        if isinstance(s, dict):
                            spi_d = s
                    b = str(spi_d.get("b_3") or spi_d.get("buvid") or "")
                    if b:
                        break
                    if _attempt == 0:
                        # 空响应（多为风控 200+空 body）：抖动退避后再试一次，避免零间隔连击
                        await asyncio.sleep(0.5 + random.random() * 0.5)
                    else:
                        logger.warning(
                            i18n.tr("[B站直播]spi 两跳均未返回 buvid（疑似风控 200+空 body），改走首页 Set-Cookie 兜底")
                        )
                except Exception as e:
                    if _attempt == 0:
                        logger.debug(
                            i18n.tr(
                                "[B站直播]buvid 获取失败(将重试): {type_name}: {e}", type_name=type(e).__name__, e=e
                            )
                        )
                        await asyncio.sleep(0.5 + random.random() * 0.5)
                    else:
                        logger.warning(
                            i18n.tr("[B站直播]buvid 获取失败: {type_name}: {e}", type_name=type(e).__name__, e=e)
                        )
        if not b:
            # spi 两跳仍空（风控）：改走首页 Set-Cookie（真实注册标识，cookie_cache 内置
            # TTL 缓存与并发去重；UA 需浏览器态——headers 已是 Firefox UA）
            try:
                home_cookies = await _cache_fetch_cookies(
                    "https://www.bilibili.com/", proxy_addr=proxy_addr, headers=headers, fetcher=async_req
                )
                b = str(home_cookies.get("buvid3", "")).strip()
                if b:
                    logger.debug(i18n.tr("[B站直播]spi 失败，从首页 Set-Cookie 获取 buvid3: {buvid}", buvid=b))
            except Exception as e:
                logger.debug(
                    i18n.tr(
                        "[B站直播]首页 Set-Cookie 获取 buvid3 失败: {type_name}: {e}", type_name=type(e).__name__, e=e
                    )
                )
        return b

    # M-8（2026-09-29）：快路按出口取值（不匹配即下沉到按 proxy 分桶的 singleflight）。
    # 锁类型、加锁位置与 global 声明一律不动——本函数临界区零 await，去重仍由 singleflight 承担。
    buvid = _take_cached_bili_buvid(proxy_addr)
    if not buvid:
        # 兜底 UUID 也须走 singleflight：否则并发下每个协程各自生成不同 UUID，
        # 后写覆盖先写，_bili_buvid_cached 抖动。
        # factory 返回 (buvid, is_fallback) 元组：判据随结果一起缓存，避免调用方
        # 再用「值是否形似 UUID」这类启发式反推（真实 buvid3 也可能长得像 UUID）
        async def _fetch_with_fallback() -> tuple[str, bool]:
            b = await _fetch_buvid()
            if b:
                return b, False
            b = str(uuid.uuid4())
            logger.debug(
                i18n.tr("[B站直播]spi/首页均无 buvid，使用生成兜底 buvid3（未注册，AUTH 可能被拒）: {buvid}", buvid=b)
            )
            return b, True

        got = await _cache_singleflight(
            key=f"bili_buvid3|{proxy_addr or ''}",
            factory=_fetch_with_fallback,
            timeout=10,
            cache_falsy=True,  # 兜底 UUID 恒非空；置 True 仅为防御 factory 返回空串
        )
        if isinstance(got, tuple) and len(got) == 2 and isinstance(got[0], str) and got[0]:
            buvid, _bili_buvid_is_fallback = got[0], bool(got[1])
        else:
            # 等待超时/拉取异常：退化为本地兜底，不写缓存（下轮重试）
            buvid = str(uuid.uuid4())
            _bili_buvid_is_fallback = True
    # M-04（2026-10-02）：缓存值与代理上下文必须整组在锁内写（与 invalidate 钩子的持锁清空
    # 对称），否则并发 singleflight 返回交错时可产生「值与出口记录错配」。
    with _bili_buvid_lock:
        _bili_buvid_cached = buvid
        # MID-40：随缓存值记录其代理上下文，供无参失效钩子清对 generic 键（见 invalidate_bili_buvid_cache）
        _bili_buvid_cached_proxy = proxy_addr or ""

    # 4) getDanmuInfo（wbi 签名）；无 wbi 则跳过签名，由调用方 -352 风控日志体现
    danmu_params: dict[str, str] = {"id": real_room_id, "type": "0", "web_location": "444.8"}
    if img_key and sub_key:
        try:
            # _sign_wbi 返回签名后的**新** dict（不就地修改入参，详见其注释）
            danmu_params = _sign_wbi(danmu_params, img_key, sub_key)
        except Exception as e:
            logger.warning(i18n.tr("[B站直播]wbi 签名失败: {type_name}: {e}", type_name=type(e).__name__, e=e))
    try:
        danmu_str = await async_req(
            f"https://api.live.bilibili.com/xlive/web-room/v1/index/getDanmuInfo?"
            f"{urllib.parse.urlencode(danmu_params)}",
            proxy_addr=proxy_addr,
            headers=headers,
        )
        danmu_data = _loads_dict(_get_str_response(danmu_str))
        danmu: dict[str, object] = {}
        if isinstance(danmu_data, dict):
            dd = danmu_data.get("data")
            if isinstance(dd, dict):
                danmu = dd
        if not danmu:
            logger.warning("[B站直播]getDanmuInfo 返回空（可能 -352 风控，检查 wbi 签名/cookie）")
            return None
        token = str(danmu.get("token", ""))
        host_list_raw = danmu.get("host_list")
        host_list: list[str] = []
        if isinstance(host_list_raw, list):
            host_list = [str(h.get("host", "")) for h in host_list_raw if isinstance(h, dict) and h.get("host")]
        if not host_list:
            logger.warning("[B站直播]getDanmuInfo 无可用 host")
            return None
        server_host = host_list[0]
    except Exception as e:
        logger.warning(i18n.tr("[B站直播]getDanmuInfo 失败: {type_name}: {e}", type_name=type(e).__name__, e=e))
        return None

    return {
        "room_id": int(real_room_id) if str(real_room_id).isdigit() else real_room_id,
        "uid": uid,
        "token": token,
        "server_host": server_host,
        "host_list": host_list,
        "buvid": buvid,
        "cookie": cookies or "",
    }


_XHS_BUILTIN_SESSION_SID = "session.1722166379345546829388"

# SEV-2214（2026-09-22）：xhslink 短链解出的落地页 URL 由**响应**决定，而后续请求会带上
# 用户 Cookie 与 xy-common-params（含会话 sid）。若不校验落地页 host，一条恶意 xhslink
# 链接即可把登录凭据递送到任意 http(s) host:port（凭据外泄 + 内网 SSRF）。
# 白名单取 XHS 实际会用到的三个域族：主站/短链/CDN。命中即带凭据，否则剥凭据再请求。
_XHS_ALLOWED_HOST_SUFFIXES = ("xiaohongshu.com", "xhslink.com", "xhscdn.com")


def _xhs_is_allowed_host(url: str) -> bool:
    # 落地页 host 是否落在 XHS 域族内。用「精确等于或 . 后缀」判定，防 evil-xiaohongshu.com
    # 这类后缀伪装（endswith 裸判定会把 notxiaohongshu.com 也放行）。
    host = (urllib.parse.urlparse(url).hostname or "").lower()
    if not host:
        return False
    return any(host == suffix or host.endswith("." + suffix) for suffix in _XHS_ALLOWED_HOST_SUFFIXES)


class XhsUrlError(ValueError):
    # code 是稳定的机器可读分类；消息只描述类别，不回显可能携带凭据的原始 URL/path。
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


# 主机的**精确**白名单（不做域族后缀匹配）：本函数输出会进配置回写与后续取流请求，
# 放宽成后缀匹配会把 evil-xiaohongshu.com 这类伪装域写进用户的配置文件。
# 注意与 _XHS_ALLOWED_HOST_SUFFIXES 分工不同：那边管「响应给出的落地页能不能带凭据」，
# 这边管「用户填的链接长什么样」，前者必须能容纳 CDN 子域，后者只认官网与短链两个主机。
_XHS_MAIN_HOST = "www.xiaohongshu.com"
_XHS_SHORT_HOST = "xhslink.com"
# 分享参数白名单，**顺序即重建顺序**：host_id 承担主页兜底、xsec_token/xsec_source 是页面
# 鉴权参数；timestamp/share_source/share_id 只用于分享溯源统计，带上会让同一房间的规范
# 地址每次都不同，配置回写后逐轮漂移（PROPOSAL_2026-10-04 已批准边界）。
_XHS_QUERY_KEYS = ("host_id", "xsec_token", "xsec_source")
# 四类受支持路径：标准直播 / 动态段直播（分享页带一段随机前缀）/ 短链 / 作者主页。
# 房间号一律取路径末段且必须全数字；动态段只认一段——真机出现更多段时先存脱敏样例再扩
# 规则，不提前放宽（同 PROPOSAL「假设与回滚」）。
_XHS_LIVE_PATH_RE = re.compile(r"^/livestream/([0-9]+)/?$")
_XHS_LIVE_DYNAMIC_PATH_RE = re.compile(r"^/livestream/[A-Za-z0-9_-]+/([0-9]+)/?$")
_XHS_SHORT_PATH_RE = re.compile(r"^/o/[A-Za-z0-9_-]+/?$")
_XHS_PROFILE_PATH_RE = re.compile(r"^/user/profile/([A-Za-z0-9_-]+)/?$")


def parse_xhs_live_url(url: str) -> dict[str, str]:
    # 小红书链接的统一解析入口（**纯函数**：不发请求、不读配置、不写全局），把标准直播链接、
    # 动态段直播链接、xhslink 短链、作者主页四类地址归一到
    # {kind, normalized_url, room_id, user_id}，让分派、配置归一化与取流共用同一份判据。
    # 判定顺序刻意「先验 scheme/host/port/userinfo，再看路径」：非法域一律挡在路径解析之前，
    # 免得 https://evil.com/livestream/... 这类伪装地址先被当成合法直播间。
    raw = (url or "").strip()
    if not raw:
        raise XhsUrlError("format", "小红书链接为空")
    try:
        parsed = urllib.parse.urlparse(raw)
        # .hostname 对畸形 IPv6 字面量、.port 对非数字端口都会抛 ValueError
        host = parsed.hostname or ""
        port = parsed.port
    except ValueError as e:
        raise XhsUrlError("format", "小红书链接格式非法") from e
    scheme = parsed.scheme.lower()
    if scheme not in ("http", "https"):
        raise XhsUrlError("scheme", "小红书链接协议不受支持（只接受 http/https）")
    if parsed.username is not None or parsed.password is not None:
        # userinfo 既不是用户手填形态，也常是「@ 之后才是真 host」的伪装载体
        raise XhsUrlError("userinfo", "小红书链接不允许携带用户信息（userinfo）")
    if port is not None and port != (443 if scheme == "https" else 80):
        raise XhsUrlError("port", "小红书链接不允许指定非默认端口")
    host = host.lower()
    if host not in (_XHS_MAIN_HOST, _XHS_SHORT_HOST):
        raise XhsUrlError("host", f"小红书链接域名不受支持: {host or '空'}")

    # 规范化：scheme 统一 https（XHS 只在 https 下发 xsec_token），尾斜杠去掉，
    # query 只留白名单三项并按固定顺序重建，fragment 直接丢弃。
    path = parsed.path or "/"
    kept = urllib.parse.parse_qs(parsed.query, keep_blank_values=False)
    pairs = [(key, kept[key][0]) for key in _XHS_QUERY_KEYS if kept.get(key)]
    normalized_url = f"https://{host}{path.rstrip('/')}"
    if pairs:
        normalized_url += "?" + urllib.parse.urlencode(pairs)

    if host == _XHS_SHORT_HOST:
        if not _XHS_SHORT_PATH_RE.match(path):
            raise XhsUrlError("short_path", "小红书短链路径必须是 /o/<短码>")
        # 短码本身不含房间号，room_id 只能等解重定向后从落地页再解析一次
        return {"kind": "short", "normalized_url": normalized_url, "room_id": "", "user_id": ""}
    profile_match = _XHS_PROFILE_PATH_RE.match(path)
    if profile_match:
        return {
            "kind": "profile",
            "normalized_url": normalized_url,
            "room_id": "",
            "user_id": profile_match.group(1),
        }
    dynamic_match = _XHS_LIVE_DYNAMIC_PATH_RE.match(path)
    if dynamic_match:
        room_id = dynamic_match.group(1)
    else:
        live_match = _XHS_LIVE_PATH_RE.match(path)
        if not live_match:
            if path == "/livestream" or path.startswith("/livestream/"):
                raise XhsUrlError("room_id", "小红书直播链接的房间 ID 缺失或非数字")
            raise XhsUrlError("non_live_path", "小红书链接不是直播间或作者主页地址")
        room_id = live_match.group(1)
    return {
        "kind": "live",
        # 动态段保持原样：删掉它之后页面未必还能打开，故不折叠成标准路径
        "normalized_url": normalized_url,
        "room_id": room_id,
        # 沿用既有兜底口径：直播链接没走 /user/profile/ 时拿 host_id 当 user_id
        "user_id": dict(pairs).get("host_id", ""),
    }


def _read_xhs_sid() -> str:
    # XHS 会话 sid 的外部覆盖值（MID-50a）：优先环境变量 XHS_SESSION_SID，其次
    # config.ini 的 [Cookie] xhs_session_sid，最后回落内置缺省。
    # 背景：内置 sid 前 10 位为 epoch（1722166379 ≈ 2024-07-28，约两年前的会话串），
    # 与本仓对 TikTok 游客 cookie（F-10）、嗨秀 accessToken（CR-12）同型的「写死外部会话」
    # 形态——原先唯独此处没有覆盖入口，一旦 XHS 校验 sid 时效，平台侧坏掉只能等发版改代码。
    # MID-2218（2026-09-23）：该键此前**从未登记**进 config.ini / README 模板，而
    # utils.read_ini_value 对「节在键不在」刻意发 warning（MI-19：凭据键缺失是用户求助时的
    # 关键线索）→ 每个小红书房间每 ~120s 刷一条「Key [xhs_session_sid] does not exist」，
    # 正踩 AGENTS「正常轮次刻意保持静默」。键已补进 [Cookie] 节与两份 README 模板。
    override = os.environ.get("XHS_SESSION_SID", "").strip()
    if override:
        return override
    try:
        cfg_value = utils.read_ini_value(f"{script_path}/config/config.ini", "Cookie", "xhs_session_sid")
    except Exception:
        cfg_value = None
    if cfg_value and cfg_value.strip():
        return cfg_value.strip()
    return _XHS_BUILTIN_SESSION_SID


@trace_error_decorator
async def get_xhs_stream_url(
    url: str, proxy_addr: OptionalStr = None, cookies: OptionalStr = None
) -> dict[str, object]:
    # 获取小红书直播流地址
    # 解析链路：xhslink 短链先解重定向 → 抠 host_id/user_id → __INITIAL_STATE__（undefined 替换 null 后解析）；
    # 返回 is_live + flv/m3u8 + record_url；标题含「回放」视为非实时不取流；未开播仍回抠到的 anchor_name。
    # M-03（2026-10-02）：入口先做域族白名单校验（对齐 _shopee_is_allowed_host 的 S-1 判据，
    # 与下方 SEV-2214 落地页校验同源）——本函数 headers 内嵌 xy-common-params（含会话 sid）
    # 与用户 Cookie，分发侧按 host 收紧（main._match_host）之外的防御纵深：必须在任何请求
    # 发出前确认目标是官方域，而不是等第一个带凭据请求已经出去了再补救。
    if not _xhs_is_allowed_host(url):
        logger.warning(
            i18n.tr(
                "小红书直播间地址不在白名单域内，拒绝解析（不发送任何带凭据请求）: {url}",
                url=utils.mask_credentials(url),
            )
        )
        return {"anchor_name": "", "is_live": False}
    sid_value = _read_xhs_sid()
    # MID-2218（2026-09-23）：镜像 TikTok 的 _warn_if_builtin_guest（见 get_tiktok_stream_data）。
    # MID-50a 只补了 sid 覆盖入口、没补「用了内置缺省且本轮失败」的告警，于是 sid 被平台判失效
    # 时用户只看到与「主播没开播」无法区分的静默失败，线索指不到凭据上（内置值年代见 _read_xhs_sid）。
    using_builtin_sid = sid_value == _XHS_BUILTIN_SESSION_SID

    def _warn_if_builtin_sid() -> None:
        if using_builtin_sid:
            logger.warning(
                i18n.tr(
                    "小红书解析失败，且本次使用的是内置会话 sid（可能已过期）；"
                    "请在 config.ini 的 [Cookie] xhs_session_sid 配置有效 sid（或设置环境变量 XHS_SESSION_SID）"
                )
            )

    headers = {
        "User-Agent": "ios/7.830 (ios 17.0; ; iPhone 15 (A2846/A3089/A3090/A3092))",
        # xy-common-params 是 XHS 固定内置的「平台+会话」头，app 端接口以此头鉴权，缺省会被拒。
        # sid 现走 env → config.ini → 内置缺省三级覆盖（见 _read_xhs_sid）。
        "xy-common-params": "platform=iOS&sid=" + sid_value,
        "referer": "https://app.xhs.cn/",
    }
    # 调用方透传 cookie 时优先采用；否则走游客态/自动获取凭据（各平台未登录态取流能力不一，部分更易被风控）
    if cookies:
        headers["Cookie"] = cookies

    # xhslink.com 是分享短链，需先解析出真实落地页 URL 再继续（redirect_url=True 取最终地址）。
    if "xhslink.com" in url:
        url_result = await async_req(url, proxy_addr=proxy_addr, headers=headers, redirect_url=True)
        if isinstance(url_result, str):
            # SEV-2214（2026-09-22）：落地页由**响应**决定，其后无 host 判定就用同一份 headers 再请求，
            # 等于把用户 Cookie 与会话 sid 递送给任意 http(s) host:port。两道闸：
            #   ① 落地页 host 必须落在 XHS 域族白名单内（_xhs_is_allowed_host）；
            #   ② 落地页不得解析到内网/回环/云元数据（复用仓内既有判定 web_config._host_internal_reason，
            #      不自造——它已覆盖 inet_aton 缩写 IP、CGNAT、metadata 域名等绕过形态）。
            # 任一条不满足即丢弃跳转结果、保留原始 xhslink url（原请求是用户自己填的合法短链宿主，
            # 不会把凭据送往响应指定的目标），并对该落地页剥离 Cookie / xy-common-params。
            _landing = url_result
            if _xhs_is_allowed_host(_landing):
                try:
                    # DNS 判定；web_config._host_internal_reason 解析失败（NXDOMAIN）也返回拒绝理由。
                    _landing_host = (urllib.parse.urlparse(_landing).hostname or "").lower()
                    _internal_reason = (
                        web_config._host_internal_reason(_landing_host) if _landing_host else "缺少主机名"
                    )
                except Exception as e:
                    _internal_reason = f"内网判定异常: {type(e).__name__}"
                if _internal_reason is None:
                    url = _landing
                else:
                    logger.warning(
                        i18n.tr(
                            "小红书短链落地页不可信，已忽略跳转: {url} ({reason})",
                            url=utils.mask_credentials(_landing),
                            reason=_internal_reason,
                        )
                    )
            else:
                logger.warning(
                    i18n.tr(
                        "小红书短链跳转到非白名单主机，已忽略跳转: {url}",
                        url=utils.mask_credentials(_landing),
                    )
                )

    host_id = get_params(url, "host_id")
    user_id_match = re.search("/user/profile/(.*?)(?=/|\\?|$)", url)
    user_id = user_id_match.group(1) if user_id_match else host_id
    result: dict[str, object] = {"anchor_name": "", "is_live": False}
    # 走到这里 url 已保证落在 XHS 白名单域内（原始短链宿主或可信落地页），故带凭据安全。
    html_str = await async_req(url, proxy_addr=proxy_addr, headers=headers)
    html_str = _get_str_response(html_str)
    # 内联 __INITIAL_STATE__ 里混有 JS 的 undefined（非法 JSON 字面量），先替换为 null 再解析。
    match_data = re.search("<script>window.__INITIAL_STATE__=(.*?)</script>", html_str)

    if match_data:
        json_str = match_data.group(1).replace("undefined", "null")
        # MID-48：__INITIAL_STATE__ 被截断（页面尺寸限制 / CDN 半截响应）时裸 json.loads 抛
        # JSONDecodeError → 装饰器 → 连下方「补主播名」的兜底路径都走不到。改为解析失败即
        # 落到 profile 兜底补 anchor_name，is_live 保持 False；并留一条区分性告警。
        json_data = _loads_dict(json_str)
        if not json_data:
            _warn_api_abnormal(json_str, "小红书 __INITIAL_STATE__", "liveStream", json_data)

        if _dig(json_data, "liveStream"):
            stream_data = _dig(json_data, "liveStream")
            # liveStatus=="success" 才是开播；标题含「回放」视为非实时直播，跳过取流。
            if _dig(stream_data, "liveStatus") == "success":
                room_info = _dig(stream_data, "roomData", "roomInfo")
                if not isinstance(room_info, dict):
                    _warn_api_abnormal(json_str, "小红书 __INITIAL_STATE__", "roomData.roomInfo", json_data)
                    return result
                title = _dig_str(room_info, "roomTitle")
                if title and "回放" not in title:
                    live_link = _dig_str(room_info, "deeplink")
                    anchor_name = get_params(live_link, "host_nickname")
                    flv_url = get_params(live_link, "flvUrl")
                    if not flv_url:
                        raise RuntimeError("Failed to get flvUrl")
                    room_id_match = re.search(r"live/([^./?]+)", flv_url)
                    if not room_id_match:
                        raise RuntimeError("Failed to extract room_id from flvUrl")
                    room_id = room_id_match.group(1)
                    # 不用 deeplink 里的签名 flvUrl（易过期），改用稳定的 CDN host 按 room_id 重建，
                    # 实测该 host 直拼 room_id 即可持续拉流；m3u8 由 flv 替换后缀得到。
                    flv_url = f"http://live-source-play.xhscdn.com/live/{room_id}.flv"
                    m3u8_url = flv_url.replace(".flv", ".m3u8")
                    result |= {
                        "anchor_name": anchor_name,
                        "is_live": True,
                        "title": title,
                        "flv_url": flv_url,
                        "m3u8_url": m3u8_url,
                        "record_url": flv_url,
                    }
                    return result
    else:
        # MID-2218：内联状态**整段**缺失 = 页面本身不合预期（风控壳页 / sid 被拒 / 页面改版）；
        # 离线房间的页面照样带 __INITIAL_STATE__（只是不含 liveStream），不会落到这里，
        # 故不违反「未开播等正常轮次刻意保持静默」。空响应走 MID-48 的统一归因，
        # 拿到页面却无内联状态时才补「内置 sid 可能过期」这条可动作提示。
        _warn_api_abnormal(html_str, "小红书 房间页", "__INITIAL_STATE__", {})
        if html_str:
            _warn_if_builtin_sid()

    # 内联状态未命中直播（未开播/分享页无 liveStream）时，退到用户主页仅补全 anchor_name，
    # 不影响录制判定（is_live 保持 False）；http 直链里抠不到昵称则留空返回。
    profile_url = f"https://www.xiaohongshu.com/user/profile/{user_id}"
    html_str = await async_req(profile_url, proxy_addr=proxy_addr, headers=headers)
    html_str = _get_str_response(html_str)
    anchor_name_match = re.search("<title>@(.*?) 的个人主页</title>", html_str)
    if anchor_name_match:
        result["anchor_name"] = anchor_name_match.group(1)

    return result


@trace_error_decorator
async def get_bigo_stream_url(
    url: str, proxy_addr: OptionalStr = None, cookies: OptionalStr = None
) -> dict[str, object]:
    # 获取 bigo 直播流地址
    # 解析链路：非 bigo.tv 域名先从 og:web:url 取真实地址再抠 &h=room_id；getInternalStudioInfo 对游客开放；
    # alive==1 取 hls_src（同时作 m3u8 与 record_url，仅 HLS 一路）；未开播且昵称空才回抓房间页补名。
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:148.0) Gecko/20100101 Firefox/148.0",
        "Accept-Language": "zh-CN,zh;q=0.8,zh-TW;q=0.7,zh-HK;q=0.5,en-US;q=0.3,en;q=0.2",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "Referer": "https://www.bigo.tv/",
    }
    # 调用方透传 cookie 时优先采用；否则走游客态/自动获取凭据（各平台未登录态取流能力不一，部分更易被风控）
    if cookies:
        headers["Cookie"] = cookies

    # 非 bigo.tv 域名（分享/第三方落地页）要先从 og meta 的 web:url 取真实地址，
    # 再从 &h= 截出 room_id；bigo.tv 直链则直接取 &h= 或路径末段作为 room_id。
    if "bigo.tv" not in url:
        html_str = await async_req(url, proxy_addr=proxy_addr, headers=headers)
        html_str = _get_str_response(html_str)
        web_url_match = re.search(
            '<meta data-n-head="ssr" data-hid="al:web:url" property="al:web:url" content="(.*?)">', html_str
        )
        if not web_url_match:
            raise ValueError("Failed to find web url")
        web_url = web_url_match.group(1)
        room_id = web_url.split("&amp;h=")[-1]
    else:
        if "&h=" in url:
            room_id = url.split("&h=")[-1]
        else:
            room_id = url.split("?")[0].rsplit("/", maxsplit=1)[-1]

    # 以 siteId 键提交 room_id 到内部接口拿直播间信息；该接口对游客开放，不强制登录。
    data = {"siteId": room_id}  # roomId
    url2 = "https://ta.bigo.tv/official_website/studio/getInternalStudioInfo"
    json_str = await async_req(url=url2, proxy_addr=proxy_addr, headers=headers, data=data)
    json_str = _get_str_response(json_str)
    # MID-48（2026-09-21 海外批次）：该接口对风控/拦截页返回 HTML，裸 json.loads 抛 JSONDecodeError
    # 后与「房间不存在」一起被装饰器吞成「未开播」，日志无任何区分线索。改为安全下钻 + 区分性告警。
    json_data = _loads_dict(json_str)
    studio_info = cast(dict[str, object], _dig(json_data, "data") or {})
    if _dig(studio_info, "alive") is None:
        _warn_api_abnormal(json_str, "Bigo getInternalStudioInfo", "data.alive", json_data)
        return {"anchor_name": _dig_str(studio_info, "nick_name"), "is_live": False}
    anchor_name = _dig_str(studio_info, "nick_name")
    live_status = _dig(studio_info, "alive")
    result: dict[str, object] = {"anchor_name": anchor_name, "is_live": False}

    # alive==1 才是开播；hls_src 同时作为 m3u8 与 record_url（bigo 仅 HLS 一路）。
    if live_status == 1:
        m3u8_url = _dig_str(studio_info, "hls_src")
        if not m3u8_url:
            # 已判开播却无流地址（改版/风控降级）：与「未开播」区分，按无源返回而非崩
            _warn_api_abnormal(json_str, "Bigo getInternalStudioInfo", "data.hls_src", json_data)
            return result
        live_title = _dig_str(studio_info, "roomTopic")
        result["m3u8_url"] = m3u8_url
        result["record_url"] = m3u8_url
        result |= {"title": live_title, "is_live": True, "m3u8_url": m3u8_url, "record_url": m3u8_url}
    # 未开播且接口没返回昵称时，退回抓房间页从 <title>/og:title 抠主播名（仅补全信息，不影响录制判定）。
    elif result["anchor_name"] == "":
        html_str = await async_req(
            url=f'https://www.bigo.tv/{url.split("/")[3]}/{room_id}', proxy_addr=proxy_addr, headers=headers
        )
        html_str = _get_str_response(html_str)
        match_anchor_name = re.search("<title>欢迎来到(.*?)的直播间</title>", html_str, re.DOTALL)
        if match_anchor_name:
            anchor_name = match_anchor_name.group(1)
        else:
            match_anchor_name = re.search(
                '<meta data-n-head="ssr" data-hid="og:title" property="og:title" ' 'content="(.*?) - BIGO LIVE">',
                html_str,
                re.DOTALL,
            )
            anchor_name = match_anchor_name.group(1) if match_anchor_name else ""
        result["anchor_name"] = anchor_name

    return result


@trace_error_decorator
async def get_blued_stream_url(
    url: str, proxy_addr: OptionalStr = None, cookies: OptionalStr = None
) -> dict[str, object]:
    # 获取 blued 直播流地址
    # 页面内联串经 decodeURIComponent 还原（URL 编码的 JSON）；onLive 为真才含 liveInfo，
    # 故 liveUrl 同时作为 m3u8 与 record_url（blued 仅单路 HLS），未开播时不取流。
    headers = {
        "User-Agent": "ios/7.830 (ios 17.0; ; iPhone 15 (A2846/A3089/A3090/A3092))",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.8,zh-TW;q=0.7,zh-HK;q=0.5,en-US;q=0.3,en;q=0.2",
    }
    # 调用方透传 cookie 时优先采用；否则走游客态/自动获取凭据（各平台未登录态取流能力不一，部分更易被风控）
    if cookies:
        headers["Cookie"] = cookies

    html_str = await async_req(url=url, proxy_addr=proxy_addr, headers=headers)
    html_str = _get_str_response(html_str)
    json_str_match = re.search('decodeURIComponent\\("(.*?)"\\)\\),window\\.Promise', html_str, re.DOTALL)
    if not json_str_match:
        raise ValueError("Failed to find json string")
    json_str = json_str_match.group(1)
    json_str = urllib.parse.unquote(json_str)
    # MID-48：页面内联串经 unquote 后同样可能是 WAF 页 / 截断产物，裸 json.loads + 二级链式
    # 索引失败时被装饰器伪装成「未开播」。改为 _loads_dict + _dig，并在结构确实不合预期时
    # 落一条区分性告警（HTML 形态另有 _safe_loads 那条「JSON 解析失败」相邻可比对）。
    json_data = _loads_dict(json_str)
    if _dig(json_data, "userInfo") is None:
        _warn_api_abnormal(json_str, "blued 页面内联数据", "userInfo", json_data)
        return {"anchor_name": "", "is_live": False}
    anchor_name = _dig_str(json_data, "userInfo", "name")
    live_status = _dig(json_data, "userInfo", "onLive")
    result: dict[str, object] = {"anchor_name": anchor_name, "is_live": False}

    if live_status:
        m3u8_url = _dig_str(json_data, "liveInfo", "liveUrl")
        if not m3u8_url:
            # onLive 为真却取不到 liveUrl：多为接口改版或风控降级，不是「未开播」
            _warn_api_abnormal(json_str, "blued 页面内联数据", "liveInfo.liveUrl", json_data)
            return result
        result |= {"is_live": True, "m3u8_url": m3u8_url, "record_url": m3u8_url}
    return result


# SOOP 房间链接里 bj_id 前面的路径前缀段（形如 /play/<bj>、/channel/<bj>、/live/<bj>）。
_SOOP_BJ_LEAD_SEGMENTS = ("play", "channel", "live")


def _soop_bj_id_from_url(url: str) -> str:
    # 从 SOOP 房间链接取主播 bj_id。MIN-2210（2026-09-23）：此前 get_sooplive_tk /
    # _fetch_web_stream_data_global / get_sooplive_stream_data 三处各自复制了同一条
    # 「按 '/' 切段后 len<6 取 [3]、否则取 [5]」的**段数**启发式——它对
    # https://www.sooplive.co.kr/play/<bj>（切成 5 段）命中 <6 分支、取到字面量 "play"，
    # 于是拼出 .../live/play/master.m3u8，该形态**永久**解析失败；且改一处必漏另两处。
    # 现按 urlparse 的 path 段做**语义**判定：首段是路径前缀（play/channel/live）时取其后
    # 一段，否则首段即 bj_id；尾斜杠与空段一并被过滤，不再影响下标。
    # 畸形 URL（无 path）返回空串，由调用方沿用既有的「取不到即按未开播返回」分支，不抛错。
    segments = [seg for seg in urllib.parse.urlparse(url).path.split("/") if seg]
    if not segments:
        return ""
    if segments[0].lower() in _SOOP_BJ_LEAD_SEGMENTS and len(segments) > 1:
        return segments[1]
    return segments[0]


@trace_error_decorator_or_none
async def login_sooplive(username: str, password: str, proxy_addr: OptionalStr = None) -> OptionalStr:
    # SOOP(原AfreecaTV) 平台登录获取认证 Cookie
    # 返回 cookie 字符串（OptionalStr）或抛错；账号/密码长度不足直接抛 RuntimeError，
    # 不发起请求（避免无意义的登录尝试）；后续 get_sooplive_stream_data 用该 cookie 鉴权。
    if len(username) < 6 or len(password) < 10:
        raise RuntimeError(
            "sooplive login failed! Please enter the correct account and password for the sooplive "
            "platform in the config.ini file."
        )

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:148.0) Gecko/20100101 Firefox/148.0",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "Origin": "https://play.sooplive.co.kr",
        "Referer": "https://play.sooplive.co.kr/superbsw123/277837074",
    }

    data = {
        "szWork": "login",
        "szType": "json",
        "szUid": username,
        "szPassword": password,
        "isSaveId": "true",
        "isSavePw": "true",
        "isSaveJoin": "true",
        "isLoginRetain": "Y",
    }

    url = "https://login.sooplive.co.kr/app/LoginAction.php"

    try:
        cookie_result = await async_req(
            url, proxy_addr=proxy_addr, headers=headers, data=data, return_cookies=True, timeout=20
        )
        if isinstance(cookie_result, dict):
            cookie_dict = cookie_result
        elif isinstance(cookie_result, tuple) and len(cookie_result) == 2 and isinstance(cookie_result[1], dict):
            cookie_dict = cookie_result[1]
        else:
            raise RuntimeError("Failed to get cookies from login response")
        cookie_str = "; ".join([f"{k}={v}" for k, v in cookie_dict.items()])
        return cookie_str
    except Exception as e:
        logger.error(i18n.tr("An error occurred during login: {e}", e=e))
        raise Exception(
            "sooplive login failed, please check if the account password in the configuration file is correct."
        )


@trace_error_decorator
async def get_sooplive_cdn_url(
    broad_no: str, proxy_addr: OptionalStr = None, cookies: OptionalStr = None
) -> dict[str, object]:
    # 获取 SOOP(原AfreecaTV) 平台 CDN 流地址
    # 返回接口原始 json（含 CDN 候选列表），由调用方解析。
    # 境外能否连通完全由 **proxy_addr** 决定：async_http.async_req 内 `_ = (abroad, content_encoding)`，
    # abroad 只是与 sync_req 的签名兼容位、异步实现不读它。保留 abroad=True 只为与同步侧调用形态
    # 一致，删它零行为变化；删 proxy_addr 才会真的直连超时——排障盯 proxy_addr，别盯 abroad。
    # [历史注] 2026-09-23 MIN-2216 推翻了本段旧说法「abroad=True 不可省，不走代理会直连超时」。
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:148.0) Gecko/20100101 Firefox/148.0",
        "Accept-Language": "zh-CN,zh;q=0.8,zh-TW;q=0.7,zh-HK;q=0.5,en-US;q=0.3,en;q=0.2",
        "Origin": "https://play.sooplive.co.kr",
        "Referer": "https://play.sooplive.co.kr/oul282/249469582",
        "Content-Type": "application/x-www-form-urlencoded",
    }
    # 调用方透传 cookie 时优先采用；否则走游客态/自动获取凭据（各平台未登录态取流能力不一，部分更易被风控）
    if cookies:
        headers["Cookie"] = cookies

    params = {
        "return_type": "gcp_cdn",
        "use_cors": "false",
        "cors_origin_url": "play.sooplive.co.kr",
        # broad_key 用 "{broad_no}-common-master-hls" 固定后缀指定主线路 HLS；
        # time 是写死的时间戳（服务端不校验其真伪，仅作为防重放字段占位），改不动即可。
        "broad_key": f"{broad_no}-common-master-hls",
        "time": "8361.086329376785",
    }

    # 境外域名必须带 proxy_addr 才走代理（abroad 不生效，见本函数头部 MIN-2216 说明）。
    url2 = "http://livestream-manager.sooplive.co.kr/broad_stream_assign.html?" + urllib.parse.urlencode(params)
    json_str = await async_req(url=url2, proxy_addr=proxy_addr, headers=headers, abroad=True)
    json_str = _get_str_response(json_str)
    # MID-48（2026-09-21 海外批次）：该境外分配接口常返回 HTML 拦截页/截断体，裸 json.loads 抛错后
    # 与「线路不存在」同样被上层装饰器吞成「未开播」。改为 _loads_dict + 缺字段归因。
    json_data = _loads_dict(json_str)
    if _dig(json_data, "view_url") is None:
        _warn_api_abnormal(json_str, "SOOP broad_stream_assign", "view_url", json_data)
    return json_data


@trace_error_decorator_or_none
async def get_sooplive_tk(
    url: str, rtype: str, proxy_addr: OptionalStr = None, cookies: OptionalStr = None
) -> str | tuple[str, str]:
    # 获取 SOOP(原AfreecaTV) 平台临时访问 token
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:148.0) Gecko/20100101 Firefox/148.0",
        "Origin": "https://play.sooplive.co.kr",
        "Referer": "https://play.sooplive.co.kr/secretx/250989857",
        "Content-Type": "application/x-www-form-urlencoded",
    }

    # 调用方透传 cookie 时优先采用；否则走游客态/自动获取凭据（各平台未登录态取流能力不一，部分更易被风控）
    if cookies:
        headers["Cookie"] = cookies

    # bj_id 一律经 _soop_bj_id_from_url 判定（取错段会得到非 bjid、tk 接口直接 404）。
    bj_id = _soop_bj_id_from_url(url)
    room_password = get_params(url, "pwd")
    if not room_password:
        room_password = ""
    data = {
        "bid": bj_id,
        "bno": "",
        "type": rtype,
        "pwd": room_password,
        "player_type": "html5",
        "stream_type": "common",
        "quality": "master",
        "mode": "landing",
        "from_api": "0",
        "is_revive": "false",
    }

    url2 = f"https://live.sooplive.co.kr/afreeca/player_live_api.php?bjid={bj_id}"
    json_str = await async_req(url=url2, proxy_addr=proxy_addr, headers=headers, data=data, abroad=True)
    json_str = _get_str_response(json_str)
    # MID-48（2026-09-21 海外批次）：CHANNEL 缺失既可能是「房间不存在」也可能是风控壳页。
    # 本函数取回的是 AID/BNO 票据，归因日志只带接口的 code/message，**绝不打印票据值**。
    json_data = _loads_dict(json_str)
    channel_info = cast(dict[str, object], _dig(json_data, "CHANNEL") or {})
    needed_keys = ("AID",) if rtype == "aid" else ("BJNICK", "BJID", "BNO")
    if any(_dig(channel_info, key) is None for key in needed_keys):
        _warn_api_abnormal(json_str, "SOOP player_live_api", "CHANNEL." + "/".join(needed_keys), json_data)
        raise RuntimeError("Failed to get sooplive CHANNEL data")

    if rtype == "aid":
        token = _dig(channel_info, "AID")
        return cast(str, token)
    else:
        bj_name = _dig(channel_info, "BJNICK")
        # 不复用上面的 bj_id（那是从 URL 段里抠的 str，此处是接口回包里的对象）
        bj_id_value = _dig(channel_info, "BJID")
        return f"{bj_name}-{bj_id_value}", cast(str, _dig(channel_info, "BNO"))


def get_soop_headers(cookies: OptionalStr = None) -> dict[str, str]:
    # 构造 SOOP(原AfreecaTV) 平台请求头
    # client-id 每次调用随机生成（抗重放/会话隔离）；返回的字典供 _get_soop_*_global 复用同一套头，
    # 保证频道/流信息两次请求头一致，否则 SOOP 可能按不一致 client-id 拒绝。
    headers = {
        "client-id": str(uuid.uuid4()),
        "user-agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 18_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, "
        "like Gecko) Version/18.5 Mobile/15E148 Safari/604.1 Edg/141.0.0.0",
    }
    # 调用方透传 cookie 时优先采用；否则走游客态/自动获取凭据（各平台未登录态取流能力不一，部分更易被风控）
    if cookies:
        headers["cookie"] = cookies
    return headers


async def _get_soop_channel_info_global(bj_id: str, proxy_addr: OptionalStr = None, cookies: OptionalStr = None) -> str:
    # 获取 SOOP(原AfreecaTV) 频道信息（内部通用方法）
    # 返回 "nickname-channelId" 复合串作为房间 key：频道号 bj_id 非稳定房间标识，
    # 用昵称+频道号唯一化，避免不同主播复用同一 bj_id 时录制串台。
    headers = get_soop_headers(cookies)
    api = "https://api.sooplive.com/v2/channel/info/" + str(bj_id)
    json_str = await async_req(api, proxy_addr=proxy_addr, headers=headers)
    json_str = _get_str_response(json_str)
    # MID-48（2026-09-21 海外批次）：v2/channel/info 对不存在/已注销频道返回不含 streamerChannelInfo
    # 的信封（或被风控换成 HTML），原四级链式索引抛错后被上层装饰器吞成「未开播」。此处降级为
    # 空昵称（调用点 `anchor_name or ""` 已容忍），并留一条区分性告警。
    json_data = _loads_dict(json_str)
    channel_info = _dig(json_data, "data", "streamerChannelInfo")
    if _dig(channel_info, "nickname") is None or _dig(channel_info, "channelId") is None:
        _warn_api_abnormal(json_str, "SOOP channel/info", "data.streamerChannelInfo", json_data)
        return ""
    nickname = _dig(channel_info, "nickname")
    channelId = _dig(channel_info, "channelId")
    anchor_name = f"{nickname}-{channelId}"
    return anchor_name


async def _get_soop_stream_info_global(
    bj_id: str, proxy_addr: OptionalStr = None, cookies: OptionalStr = None
) -> tuple[bool, str]:
    # 获取 SOOP(原AfreecaTV) 直播流信息（内部通用方法）
    # 返回 (isStream, title)；isStream 为真即开播，直接驱动 get_sooplive_stream_data 的 is_live 判定，
    # 标题用于录制文件名；接口对游客开放、无需登录 cookie。
    headers = get_soop_headers(cookies)
    api = "https://api.sooplive.com/v2/stream/info/" + str(bj_id)
    json_str = await async_req(api, proxy_addr=proxy_addr, headers=headers)
    json_str = _get_str_response(json_str)
    # MID-48（2026-09-21 海外批次）：本函数返回 (status, title) 二元组且调用点直接解包，
    # 因此结构异常时必须回「未开播 + 空标题」而不是 None（解包 None 会抛 TypeError 并被
    # 上层装饰器伪装成未开播、彻底丢失成因）。isStream 缺失即响应不合预期，落告警。
    json_data = _loads_dict(json_str)
    stream_info = _dig(json_data, "data")
    status = _dig(stream_info, "isStream")
    if status is None:
        _warn_api_abnormal(json_str, "SOOP stream/info", "data.isStream", json_data)
        return False, ""
    return cast(bool, status), _dig_str(stream_info, "title")


async def _fetch_web_stream_data_global(
    url: str, proxy_addr: OptionalStr = None, cookies: OptionalStr = None
) -> dict[str, object]:
    # 抓取 Web 端直播流数据（内部通用方法）
    # bj_id 判定见 _soop_bj_id_from_url（MIN-2210：三处共用同一实现，不得再各自复制段数启发式）
    bj_id = _soop_bj_id_from_url(url)
    anchor_name = await _get_soop_channel_info_global(bj_id, proxy_addr=proxy_addr, cookies=cookies)
    result: dict[str, object] = {"anchor_name": anchor_name or "", "is_live": False, "live_url": url}
    status, title = await _get_soop_stream_info_global(bj_id, proxy_addr=proxy_addr, cookies=cookies)
    if not status:
        return result
    else:

        async def _get_url_list(m3u8: str) -> list[str]:
            # 从直播流数据中提取 URL 列表（内部方法）
            # m3u8 内相对路径（非 # 开头）行须按清单自身地址解析为绝对地址，否则 ffmpeg 取到
            # 相对地址无法拉流；未匹配到带宽的 URL 排序时置 0 兜底，避免 KeyError 导致整轮取流失败。
            headers = {
                "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/141.0.0.0 Safari/537.36 Edg/141.0.0.0",
            }
            if cookies:
                headers["cookie"] = cookies
            resp = await async_req(url=m3u8, proxy_addr=proxy_addr, headers=headers)
            resp = _get_str_response(resp)
            play_url_list = []
            # MID-47 修复（2026-09-20）：原实现 url_prefix = "/".join(m3u8.split("/")[0:3]) 缺尾斜杠，
            # 相对行 "1080/index.m3u8" 被拼成 https://global-media.sooplive.com1080/index.m3u8，
            # 且该损坏串会经 play_url_list 成为 record_url（main→stream.get_stream_url spec=True）；
            # 绝对地址行又会被前缀污染。改用 urljoin 对相对/绝对/带参三形态一律正确，
            # 语义与同文件韩国侧姊妹实现（rsplit 目录前缀 + 拼接）对齐且更稳健。
            for i in resp.split("\n"):
                line = i.strip()
                if not line.startswith("#") and line:
                    play_url_list.append(urllib.parse.urljoin(m3u8, line))
            bandwidth_pattern = _BANDWIDTH_PATTERN
            bandwidth_list = bandwidth_pattern.findall(resp)
            url_to_bandwidth = {purl: int(bandwidth) for bandwidth, purl in zip(bandwidth_list, play_url_list)}
            play_url_list = sorted(play_url_list, key=lambda purl: url_to_bandwidth.get(purl, 0), reverse=True)
            return play_url_list

        m3u8_url = "https://global-media.sooplive.com/live/" + bj_id + "/master.m3u8"
        result |= {
            "is_live": True,
            "title": title,
            "m3u8_url": m3u8_url,
            "play_url_list": await _get_url_list(m3u8_url),
        }
    return result


@trace_error_decorator
async def get_sooplive_stream_data(
    url: str,
    proxy_addr: OptionalStr = None,
    cookies: OptionalStr = None,
    username: OptionalStr = None,
    password: OptionalStr = None,
) -> dict[str, object]:
    # 获取 SOOP(原AfreecaTV) 平台直播流数据
    # 解析链路：sooplive.com 域名先转 _fetch_web_stream_data_global（全球区走 channel/stream 两个接口）；
    # 韩国区经 api.m.sooplive.co.kr/broad/a/watch 一次拿 user_nick / broad_no / hls_authentication_key，
    # 公开房直接拼 m3u8；无昵称时按 data.code 分流（-3002/-3004 走登录 + get_sooplive_tk 取 AID 票据，
    # -3001 刚下播、-6001 地址错误按未开播返回）。两条路径最终都经 get_sooplive_cdn_url 取 view_url。
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:148.0) Gecko/20100101 Firefox/148.0",
        "Accept-Language": "zh-CN,zh;q=0.8,zh-TW;q=0.7,zh-HK;q=0.5,en-US;q=0.3,en;q=0.2",
        "Referer": "https://m.sooplive.co.kr/",
        "Content-Type": "application/x-www-form-urlencoded",
    }
    # 调用方透传 cookie 时优先采用；否则走游客态/自动获取凭据（各平台未登录态取流能力不一，部分更易被风控）
    if cookies:
        headers["Cookie"] = cookies

    if "sooplive.com" in url:
        return await _fetch_web_stream_data_global(url, proxy_addr, cookies)

    # bj_id 判定见 _soop_bj_id_from_url（MIN-2210：三处共用同一实现，不得再各自复制段数启发式）
    bj_id = _soop_bj_id_from_url(url)

    data = {
        "bj_id": bj_id,
        "broad_no": "",
        "agent": "web",
        "confirm_adult": "true",
        "player_type": "webm",
        "mode": "live",
    }

    url2 = "http://api.m.sooplive.co.kr/broad/a/watch"

    json_str = await async_req(url=url2, proxy_addr=proxy_addr, headers=headers, data=data, abroad=True)
    json_str = _get_str_response(json_str)
    # MID-48（2026-09-21 海外批次）：broad/a/watch 对受限房/风控返回不含 data 的信封或 HTML，
    # 原 `json_data["data"]`（下面还按 data.code 分支）抛错后被装饰器吞成「未开播」，
    # 与「直播刚结束」「房间地址错误」等既有可诊断形态混成同一条。改为安全下钻。
    json_data = _loads_dict(json_str)
    watch_data = cast(dict[str, object], _dig(json_data, "data") or {})

    # 公开直播间接口才会在 data 里带 user_nick；bj_id 后缀用于唯一标识房间
    # （不同主播可能复用同一 bj_id 段，加昵称前缀避免录制串台）。无 user_nick 视为
    # 受限/未公开房间，anchor_name 留空走下方登录或报错分支。
    if _dig(watch_data, "user_nick") is not None:
        anchor_name = _dig_str(watch_data, "user_nick")
        bj_id_value = _dig(watch_data, "bj_id")
        if bj_id_value is not None:
            anchor_name = f"{anchor_name}-{bj_id_value}"
    else:
        anchor_name = ""

    result: dict[str, object] = {"anchor_name": anchor_name or "", "is_live": False}

    async def get_url_list(m3u8: str) -> list[str]:
        # 解析直播流响应并返回 URL 列表
        resp = await async_req(url=m3u8, proxy_addr=proxy_addr, headers=headers, abroad=True)
        resp = _get_str_response(resp)
        play_url_list = []
        url_prefix = m3u8.rsplit("/", maxsplit=1)[0] + "/"
        for i in resp.split("\n"):
            if i.startswith("auth_playlist"):
                play_url_list.append(url_prefix + i.strip())
        bandwidth_pattern = _BANDWIDTH_PATTERN
        bandwidth_list = bandwidth_pattern.findall(resp)
        url_to_bandwidth = {purl: int(bandwidth) for bandwidth, purl in zip(bandwidth_list, play_url_list)}
        # 2026-09-12 审查 6.3：原为 url_to_bandwidth[purl] 无兜底。zip 会在
        # bandwidth_list 与 play_url_list 较短的一侧截断，两者长度不一致时（部分
        # 清晰度行缺 BANDWIDTH 或格式变体）尾部 URL 不在字典里 → KeyError，
        # 被外层 trace_error_decorator 吞成"未开播"，表现为明明在播却漏录。
        # 本文件另一处 get_play_url_list 用的是「数量一致才按带宽排序」的长度守卫，
        # 与此处是两种等效的不抛错写法：取 0 兜底让缺带宽的 URL 排到末尾、链路不失败。
        play_url_list = sorted(play_url_list, key=lambda purl: url_to_bandwidth.get(purl, 0), reverse=True)
        return play_url_list

    # anchor_name 为空说明接口未返回公开直播间信息（成人房/未登录/房间异常），需按 data.code
    # 进入登录或报错分支；guest 仅能拿公开房，下面各 code 是 SOOP 网关的状态语义。
    if not anchor_name:

        async def handle_login() -> OptionalStr:
            # 处理平台登录认证
            cookie = await login_sooplive(cast(str, username), cast(str, password), proxy_addr=proxy_addr)
            if cookie and "AuthTicket=" in cookie:
                logger.info("sooplive platform login successful! Starting to fetch live streaming data...")
                return cookie
            return None

        async def fetch_data(cookie: str, _result: dict[str, object]) -> dict[str, object]:
            # 抓取直播数据
            aid_token = await get_sooplive_tk(url, rtype="aid", proxy_addr=proxy_addr, cookies=cookie)
            _info = await get_sooplive_tk(url, rtype="info", proxy_addr=proxy_addr, cookies=cookie)
            # MID-2210（2026-09-23）：get_sooplive_tk 挂的是 trace_error_decorator_or_none，
            # 票据失败时返回 **None**，而 `cast(str, aid_token)` 只骗过类型检查、不做运行时转换，
            # 于是下面 `"?aid=" + None` 抛 TypeError → 被最外层 @trace_error_decorator 吞成
            # 「未开播」，把已经拿到的主播名/线路号连同那条真正的归因日志一起冲掉
            # （游客路径与 _info 都判了空，此处口径原本不一致）。
            # 现与两处对齐：判空即按未开播返回 _result（anchor_name 为空 → main 记失败样本），
            # 且**移到 CDN 分配请求之前**——拿不到 aid 时 view_url 也用不上，别白烧一次请求。
            # 归因由 get_sooplive_tk 的 _warn_api_abnormal 与装饰器 guard 各自落过，此处不重复刷。
            if not isinstance(aid_token, str) or not aid_token:
                return _result
            if not (isinstance(_info, tuple) and len(_info) == 2):
                return _result
            _anchor_name, _broad_no = _info
            _view_url_data = await get_sooplive_cdn_url(_broad_no, proxy_addr=proxy_addr)
            _view_url = cast(str, _view_url_data.get("view_url", ""))
            _m3u8_url = _view_url + "?aid=" + aid_token
            _result |= {
                "anchor_name": _anchor_name,
                "is_live": True,
                "m3u8_url": _m3u8_url,
                "play_url_list": await get_url_list(_m3u8_url),
                "new_cookies": cookie,
            }
            return _result

        # SOOP 网关错误码：-3001 直播刚结束；-3002 成人房需 19+ 登录；-3004 需登录态 cookie；
        # -6001 房间地址错误。-3002/-3004 都触发登录流程，区别只在 -3004 先复用调用方透传的
        # cookie（避免每轮重复登录），票据仍被拒时才用账号密码登录一次并重试（MID-2211）。
        soop_code = _dig(watch_data, "code")
        if soop_code is None:
            # 无 user_nick 又无网关 code：既不是已知「刚结束/需登录/地址错误」任一形态，
            # 只能是响应整体不合预期（风控壳页 / 接口改版），落线索后按未开播返回。
            _warn_api_abnormal(json_str, "SOOP broad/a watch", "data.code", json_data)
            return result

        if soop_code == -3001:
            logger.error("sooplive live stream failed to retrieve, the live stream just ended.")
            return result

        elif soop_code == -3002:
            logger.error("sooplive live stream retrieval failed, the live needs 19+, you are not logged in.")
            logger.warning(
                "Attempting to log in to the sooplive live streaming platform with your account and password, "
                "please ensure it is configured."
            )
            new_cookie = await handle_login()
            if new_cookie and len(new_cookie) > 0:
                return await fetch_data(new_cookie, result)
            raise RuntimeError("sooplive login failed, please check if the account and password are correct")

        elif soop_code == -3004:
            # MID-2211（2026-09-23）：原实现只复用调用方透传的 cookie，票据被拒时每轮拿同一份
            # 坏 cookie 反复失败，配置里的 [账号密码] sooplive账号/密码 **永不被使用**，
            # 用户只能手工删项。现与 -3002 的语义收敛：先复用（避免每轮重复登录触发风控），
            # 复用后 fetch_data 仍取不到票据（回未开播）才登录一次并重试。
            # fetch_data 原地改写并返回同一个 _result，失败时 is_live 仍为 False，可直接作判据。
            if cookies:
                reused = await fetch_data(cast(str, cookies), result)
                if reused.get("is_live"):
                    return reused
                logger.warning(
                    "The playback ticket of the cookie you provided was rejected, retrying with the "
                    "sooplive account and password in the configuration file."
                )
            new_cookie = await handle_login()
            if new_cookie and len(new_cookie) > 0:
                return await fetch_data(new_cookie, result)
            raise RuntimeError("sooplive login failed, please check if the account and password are correct")
        elif soop_code == -6001:
            logger.error("error message：Please check if the input sooplive live room address " "is correct.")
            return result
    # result==1 且已有 anchor_name：公开可观看的直播间。hls_authentication_key 即 CDN 的 aid 票据，
    # 必须作为 ?aid= 拼到 m3u8 地址后，缺失该票据 CDN 会直接 403（同样的票据也用于登录态的 AID）。
    if _dig(json_data, "result") == 1 and anchor_name:
        broad_no = _dig(watch_data, "broad_no")
        hls_authentication_key = _dig(watch_data, "hls_authentication_key")
        if broad_no is None or hls_authentication_key is None:
            # 已判开播却拿不到线路号或 CDN 票据（接口改版 / 风控降级）：与「未开播」区分。
            # 归因只带 code/message，票据值绝不入日志。
            _warn_api_abnormal(json_str, "SOOP broad/a watch", "data.broad_no + hls_authentication_key", json_data)
        else:
            view_url_data = await get_sooplive_cdn_url(cast(str, broad_no), proxy_addr=proxy_addr)
            view_url = cast(str, view_url_data.get("view_url", ""))
            m3u8_url = view_url + "?aid=" + cast(str, hls_authentication_key)
            result |= {"is_live": True, "m3u8_url": m3u8_url, "play_url_list": await get_url_list(m3u8_url)}
    # 仅在未通过登录获取新 cookie 时置 None，避免覆盖 fetch_data 中设置的 cookie
    result.setdefault("new_cookies", None)
    return result


@trace_error_decorator
async def get_netease_stream_data(
    url: str, proxy_addr: OptionalStr = None, cookies: OptionalStr = None
) -> dict[str, object]:
    # 获取网易 CC 直播流数据
    # 解析链路：抓 __NEXT_DATA__ 内联 JSON → roomInfoInitData；status==1 才取流；
    # 返回 is_live + m3u8 + stream_list（quickplay 清晰度列表）；sharefile/quickplay 缺失按无源不报错。
    headers = {
        "accept": "application/json, text/plain, */*",
        "accept-language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
        "referer": "https://cc.163.com/",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:148.0) Gecko/20100101 Firefox/148.0",
    }
    # 调用方透传 cookie 时优先采用；否则走游客态/自动获取凭据（各平台未登录态取流能力不一，部分更易被风控）
    if cookies:
        headers["Cookie"] = cookies
    # 规整 URL 结尾斜杠，保证后续正则/接口参数拼接稳定
    url = url + "/" if url[-1] != "/" else url

    html_str = await async_req(url=url, proxy_addr=proxy_addr, headers=headers)
    html_str = _get_str_response(html_str)
    json_str_match = re.search(
        '<script id="__NEXT_DATA__" .* crossorigin="anonymous">(.*?)</script></body>', html_str, re.DOTALL
    )
    # __NEXT_DATA__ 缺失即页面结构变化，显式报错而非后续 KeyError
    if not json_str_match:
        raise ValueError("Failed to find __NEXT_DATA__")
    json_str = json_str_match.group(1)
    # MID-48：__NEXT_DATA__ 命中但内容被截断 / 换成风控壳页时，裸 json.loads 与随后
    # ["props"]["pageProps"]["roomInfoInitData"]["live"] 的四级索引都会抛错并被装饰器
    # 吞成 {"is_live": False}——连「房间存在但未开播」都读不出来。改为安全下钻 + 显式归因。
    json_data = _loads_dict(json_str)
    room_data = _dig(json_data, "props", "pageProps", "roomInfoInitData")
    live_data = _dig(room_data, "live")
    if not isinstance(live_data, dict):
        _warn_api_abnormal(json_str, "网易CC __NEXT_DATA__", "roomInfoInitData.live", json_data)
        return {"anchor_name": _dig_str(room_data, "nickname"), "is_live": False}
    live_data = cast(dict[str, object], live_data)
    result: dict[str, object] = {"is_live": False}
    # 网易 CC 用 status==1 表示开播（0/2 为未播/轮播），只有开播才取流；
    # sharefile 即 m3u8 地址、quickplay 为清晰度列表，缺失时上游按无源处理、不报错。
    live_status = live_data.get("status") == 1
    # 原写法 live_data.get("nickname", room_data.get("nickname")) 在 nickname 显式为 null 时
    # 会把 None 交给下游 clean_name()（MID-43 同类），改为 _dig_str 后一律回 str。
    result["anchor_name"] = _dig_str(live_data, "nickname") or _dig_str(room_data, "nickname")
    if live_status:
        # M-9（2026-09-29）同型收口：sharefile 显式为 null 时 .get 取到 None，而本分支已把
        # is_live 置真 → 下游 stream.py 的 `n.get("m3u8_url", "")` 拿到的还是 None（键存在、
        # 值为 null，缺省不生效），record_url 跟着变 None。_dig_str 一律回 str，与「无源」
        # 的既有判定（falsy 即不取流）口径一致。
        # quickplay 保持原样：它是**字典**（按画质键索引，见 src/stream.py 的网易CC 分支），
        # 不是字符串字段，缺失时上游 `if stream_list_data:` 已按 falsy 安全处理。
        result |= {
            "is_live": True,
            "title": _dig_str(live_data, "title"),
            "stream_list": live_data.get("quickplay"),
            "m3u8_url": _dig_str(live_data, "sharefile"),
        }
    return result


@trace_error_decorator
async def get_qiandurebo_stream_data(
    url: str, proxy_addr: OptionalStr = None, cookies: OptionalStr = None
) -> dict[str, object]:
    # 获取千度热播直播流数据
    # 解析链路：抓页面 var user 内联串 → 抠 zb_nickname/play_url；含「未开播占位提示」即视为未开播；
    # 返回 is_live + flv + record_url；play_url 缺失直接回未开播，不抛错（装饰器按未开播空转重试）。
    headers = {
        "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8,"
        "application/signed-exchange;v=b3;q=0.7",
        "accept-language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
        "referer": "https://qiandurebo.com/web/index.php",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:148.0) Gecko/20100101 Firefox/148.0",
    }
    # 调用方透传 cookie 时优先采用；否则走游客态/自动获取凭据（各平台未登录态取流能力不一，部分更易被风控）
    if cookies:
        headers["Cookie"] = cookies

    html_str = await async_req(url=url, proxy_addr=proxy_addr, headers=headers)
    html_str = _get_str_response(html_str)
    data_match = re.search("var user = (.*?)\r\n\\s+user\\.play_url", html_str, re.DOTALL)
    if not data_match:
        return {"anchor_name": "", "is_live": False}
    data = data_match.group(1)
    anchor_name = re.findall('"zb_nickname": "(.*?)",\r\n', data)

    result: dict[str, object] = {"anchor_name": "", "is_live": False}
    if len(anchor_name) > 0:
        result["anchor_name"] = anchor_name[0]
        play_url = re.findall('"play_url": "(.*?)",\r\n', data)

        # 离线/被封房间页会渲染 `common-text-center" style="display:block` 的占位提示，
        # 此串存在即视为未开播，避免把占位页里抽到的空 play_url 当成有效流录制。
        if len(play_url) > 0 and 'common-text-center" style="display:block' not in html_str:
            result |= {
                "anchor_name": anchor_name[0],
                "is_live": True,
                "flv_url": play_url[0],
                "record_url": play_url[0],
            }
    return result


@trace_error_decorator
async def get_pandatv_stream_data(
    url: str, proxy_addr: OptionalStr = None, cookies: OptionalStr = None
) -> dict[str, object]:
    # 获取 PandaTV 直播流数据
    # 解析链路：member/bj 拿主播信息 + media 是否在播字段 → 在播才请求 live/play 拿 HLS；
    # 返回 is_live + m3u8 + play_url_list；errorData.needAdult 表示成人房需登录 cookie，其它 code 原样抛错。
    headers = {
        "origin": "https://www.pandalive.co.kr",
        "referer": "https://www.pandalive.co.kr/",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:148.0) Gecko/20100101 Firefox/148.0",
    }
    # 调用方透传 cookie 时优先采用；否则走游客态/自动获取凭据（各平台未登录态取流能力不一，部分更易被风控）
    if cookies:
        headers["Cookie"] = cookies

    user_id = _safe_extract_id(url)
    url2 = "https://api.pandalive.co.kr/v1/live/play"
    data = {
        "userId": user_id,
        "info": "media fanGrade",
    }
    room_password = get_params(url, "pwd")
    if not room_password:
        room_password = ""
    data2 = {
        "action": "watch",
        "userId": user_id,
        "password": room_password,
        "shareLinkType": "",
    }

    result: dict[str, object] = {"anchor_name": "", "is_live": False}
    json_str = await async_req(
        "https://api.pandalive.co.kr/v1/member/bj", proxy_addr=proxy_addr, headers=headers, data=data, abroad=True
    )
    json_str = _get_str_response(json_str)
    # MID-48（2026-09-21 海外批次）：member/bj 对「用户不存在」回合法 JSON + message，对风控回
    # HTML/空体——两者此前都变成「未开播」。bjInfo 缺失仍按既有语义抛错（上层装饰器 → 离线，
    # 且既有测试锁定 {"is_live": False} 契约），只在响应整体解析不出对象时补一条区分性告警。
    json_data = _loads_dict(json_str)
    bj_info = _dig(json_data, "bjInfo")
    if bj_info is None:
        _warn_api_abnormal(json_str, "PandaTV member/bj", "bjInfo", json_data)
        raise RuntimeError(cast(str, json_data.get("message", "Unknown error")))
    anchor_id = _dig(bj_info, "id")
    anchor_nick = _dig(bj_info, "nick")
    anchor_name = f"{anchor_nick}-{anchor_id}"
    result["anchor_name"] = anchor_name
    # PandaTV 用 "media" 字段是否存在来表示是否在播：有 media 才是开播态，否则只是离线主播页。
    live_status = "media" in json_data

    if live_status:
        json_str = await async_req(url2, proxy_addr=proxy_addr, headers=headers, data=data2, abroad=True)
        json_str = _get_str_response(json_str)
        json_data = _loads_dict(json_str)
        # errorData 出现表示观看受限：needAdult 是成人房需登录态 cookie；其它 code 原样抛出。
        error_data = _dig(json_data, "errorData")
        if error_data is not None:
            error_code = _dig(error_data, "code")
            if error_code == "needAdult":
                # M-3（2026-09-29，本项主案发现场）：私有/成人房的房间密码就挂在 url 的
                # ?pwd= 上（pwd 在 utils._SECRET_KEYS 表内），而 @trace_error_decorator 落日志时
                # 对异常原文零脱敏 → 受限房每轮把明文密码写进 logs/streamget.log（轮转保留多份）。
                # 只脱敏、不改文案结构与抛出语义（调用方与既有断言均按原样匹配这条消息）。
                raise RuntimeError(
                    f"{utils.mask_credentials(url)} "
                    f"The live room requires login and is only accessible to adults. Please "
                    f"correctly fill in the login cookie in the configuration file."
                )
            else:
                raise RuntimeError(cast(object, error_code), _dig(json_data, "message"))
        play_url = _dig_str(json_data, "PlayList", "hls", 0, "url")
        if not play_url:
            # 已判在播却取不到 HLS（改版 / 风控降级）：与「未开播」区分，按无源返回
            _warn_api_abnormal(json_str, "PandaTV live/play", "PlayList.hls[0].url", json_data)
            return result
        play_url_list = await get_play_url_list(m3u8=play_url, proxy=proxy_addr, header=headers, abroad=True)
        result |= {"is_live": True, "m3u8_url": play_url, "play_url_list": play_url_list}
    return result


@trace_error_decorator
async def get_maoerfm_stream_url(
    url: str, proxy_addr: OptionalStr = None, cookies: OptionalStr = None
) -> dict[str, object]:
    # 获取猫耳 FM 直播流地址
    # 解析链路：api/v2/live/{room_id} 直取；room 字段存在且 broadcasting 为真才取流；
    # 返回 is_live + m3u8 + flv + record_url；无 room 字段按未开播返回，不抛错。
    headers = {
        "accept": "application/json, text/plain, */*",
        "accept-language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
        "referer": "https://fm.missevan.com/live/868895007",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:148.0) Gecko/20100101 Firefox/148.0",
    }
    # 调用方透传 cookie 时优先采用；否则走游客态/自动获取凭据（各平台未登录态取流能力不一，部分更易被风控）
    if cookies:
        headers["Cookie"] = cookies

    room_id = _safe_extract_id(url)
    url2 = f"https://fm.missevan.com/api/v2/live/{room_id}"

    json_str = await async_req(url=url2, proxy_addr=proxy_addr, headers=headers)
    json_str = _get_str_response(json_str)
    # MID-48：猫耳的错误信封是 {code, msg}（不含 info），房间不存在/已下线与接口改版此前
    # 都表现为 `json_data["info"]` 的 KeyError → 装饰器 → 「未开播」，日志零线索。
    json_data = _loads_dict(json_str)
    if _dig(json_data, "info") is None:
        _warn_api_abnormal(json_str, "猫耳FM api/v2/live", "info", json_data)
        return {"anchor_name": "", "is_live": False}
    info = _dig(json_data, "info")
    anchor_name = _dig_str(info, "creator", "username")
    if not anchor_name:
        _warn_api_abnormal(json_str, "猫耳FM api/v2/live", "info.creator.username", json_data)
    live_status: object = False
    # room 字段缺失表示离线主播页（无 broadcasting 标记），live_status 保持 False。
    # 原写法先判 `"room" in info` 再四级下钻，room 显式为 null 时抛 TypeError；改为 or {}
    # 收敛后统一按 falsy 走离线分支。
    room = cast(dict[str, object], _dig(info, "room") or {})
    if room:
        live_status = _dig(room, "status", "broadcasting")

    result: dict[str, object] = {"anchor_name": anchor_name, "is_live": live_status}
    if live_status:
        m3u8_url = _dig_str(room, "channel", "hls_pull_url")
        flv_url = _dig_str(room, "channel", "flv_pull_url")
        title = _dig_str(room, "name")
        if not flv_url and not m3u8_url:
            # broadcasting 为真却没有任何拉流地址：接口改版/风控降级，不是「未开播」
            _warn_api_abnormal(json_str, "猫耳FM api/v2/live", "room.channel", json_data)
            return {"anchor_name": anchor_name, "is_live": False}
        result |= {"is_live": True, "title": title, "m3u8_url": m3u8_url, "flv_url": flv_url, "record_url": flv_url}
    return result


@trace_error_decorator_or_none
async def get_winktv_bj_info(
    url: str, proxy_addr: OptionalStr = None, cookies: OptionalStr = None
) -> tuple[str, object]:
    # 获取 WinkTV 主播信息
    # 返回 (anchor_name, live_status) 二元组供 get_winktv_stream_data 复用，避免重复抓 bj 接口；
    # live_status 由响应是否含 "media" 字段判定（有 media 才在播），anchor_id 取自 bjInfo
    # 用于后续 watch 接口鉴权，缺它会被服务端按「未授权观看」拒绝。
    headers = {
        "accept": "application/json, text/plain, */*",
        "accept-language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
        "content-type": "application/x-www-form-urlencoded",
        "referer": "https://www.winktv.co.kr/",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:148.0) Gecko/20100101 Firefox/148.0",
    }
    # 调用方透传 cookie 时优先采用；否则走游客态/自动获取凭据（各平台未登录态取流能力不一，部分更易被风控）
    if cookies:
        headers["Cookie"] = cookies
    user_id = url.split("?")[0].rsplit("/", maxsplit=1)[-1]
    data = {
        "userId": user_id,
        "info": "media",
    }

    info_api = "https://api.winktv.co.kr/v1/member/bj"
    json_str = await async_req(url=info_api, proxy_addr=proxy_addr, headers=headers, data=data, abroad=True)
    json_str = _get_str_response(json_str)
    # MID-48（2026-09-21 海外批次）：与 PandaTV 同族接口，风控壳页/截断体此前抛 JSONDecodeError，
    # 被 _or_none 装饰器吞成 None，调用点只看到「拿不到主播信息」。补区分性告警后再交装饰器兜底。
    json_data = _loads_dict(json_str)
    live_status = "media" in json_data
    bj_info = _dig(json_data, "bjInfo")
    if bj_info is None:
        _warn_api_abnormal(json_str, "WinkTV member/bj", "bjInfo", json_data)
        raise RuntimeError(cast(str, json_data.get("message", "Unknown error")))
    anchor_id = _dig(bj_info, "id")
    anchor_nick = _dig(bj_info, "nick")
    anchor_name = f"{anchor_nick}-{anchor_id}"
    return anchor_name, live_status


@trace_error_decorator
async def get_winktv_stream_data(
    url: str, proxy_addr: OptionalStr = None, cookies: OptionalStr = None
) -> dict[str, object]:
    # 获取 WinkTV 直播流数据
    # 解析链路：get_winktv_bj_info 拿 (anchor_name, live_status) → 在播才请求 play/cdn 拿 HLS；
    # 返回 is_live + m3u8 + play_url_list；live_status 由响应是否含 media 字段判定，无 media 即离线。
    headers = {
        "accept": "application/json, text/plain, */*",
        "accept-language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
        "content-type": "application/x-www-form-urlencoded",
        "referer": "https://www.winktv.co.kr",
        "origin": "https://www.winktv.co.kr",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:148.0) Gecko/20100101 Firefox/148.0",
    }
    # 调用方透传 cookie 时优先采用；否则走游客态/自动获取凭据（各平台未登录态取流能力不一，部分更易被风控）
    if cookies:
        headers["Cookie"] = cookies
    user_id = url.split("?")[0].rsplit("/", maxsplit=1)[-1]
    room_password = get_params(url, "pwd")
    if not room_password:
        room_password = ""
    data = {
        "action": "watch",
        "userId": user_id,
        "password": room_password,
        "shareLinkType": "",
    }

    # MID-44（2026-09-20，CR-12 契约）：get_winktv_bj_info 是 _or_none 装饰（visitor 接口
    # 风控/HTML 拦截页时返回 None），必须显式判空后再解包——原实现直接解包 None 抛
    # TypeError，被本函数自己的装饰器二次吞掉，与「真未开播」不可区分且 anchor_name 永不回传。
    # 同仓 get_popkontv_stream_data / get_acfun_sign_params 均已按此口径修过，此处为漏改点。
    bj_info = await get_winktv_bj_info(url=url, proxy_addr=proxy_addr, cookies=cookies)
    if not bj_info:
        return {"anchor_name": "", "is_live": False}
    anchor_name, live_status = bj_info
    result: dict[str, object] = {"anchor_name": anchor_name, "is_live": live_status}
    if live_status:
        play_api = "https://api.winktv.co.kr/v1/live/play"
        json_str = await async_req(url=play_api, proxy_addr=proxy_addr, headers=headers, data=data, abroad=True)
        json_str = _get_str_response(json_str)
        # WinkTV 被封禁时不在 HTTP 层返回 403，而是把 "403: Forbidden" 作为响应体字符串返回，
        # 故必须做文本包含判断，而非只看状态码；命中即说明该出口 IP 已被拉黑。
        if "403: Forbidden" in json_str:
            raise ConnectionError(f"Your network has been banned from accessing WinkTV ({json_str})")
        json_data = _loads_dict(json_str)
        # MID-48（2026-09-21 海外批次）：与 PandaTV live/play 同族实现，加固口径保持一致
        # （详见 get_pandatv_stream_data 内 MID-48 注释）。
        error_data = _dig(json_data, "errorData")
        if error_data is not None:
            error_code = _dig(error_data, "code")
            if error_code == "needAdult":
                # M-3（2026-09-29）：与 PandaTV 同族实现（见 get_pandatv_stream_data 内的说明）——
                # WinkTV 的受限房地址同样可能带 ?pwd=，异常消息里的 URL 必须先脱敏。
                raise RuntimeError(
                    f"{utils.mask_credentials(url)} "
                    f"The live stream is only accessible to logged-in adults. Please ensure that "
                    f"the cookie is correctly filled in the configuration file after logging in."
                )
            else:
                raise RuntimeError(cast(object, error_code), _dig(json_data, "message"))
        m3u8_url = _dig_str(json_data, "PlayList", "hls", 0, "url")
        if not m3u8_url:
            # 已判在播却取不到 HLS（改版 / 风控降级）：改按无源返回并留线索，
            # 不再让 KeyError 被装饰器伪装成「未开播」而丢掉主播名。
            _warn_api_abnormal(json_str, "WinkTV live/play", "PlayList.hls[0].url", json_data)
            result["is_live"] = False
            return result
        play_url_list = await get_play_url_list(m3u8=m3u8_url, proxy=proxy_addr, header=headers, abroad=True)
        result["m3u8_url"] = m3u8_url
        result["play_url_list"] = play_url_list
    return result


@trace_error_decorator_or_none
async def login_flextv(username: str, password: str, proxy_addr: OptionalStr = None) -> OptionalStr:
    # TTingLive(原Flextv) 平台登录认证
    # 返回 cookie 字符串（OptionalStr）或 None；signin 接口对游客态也会下发游客 cookie，
    # 故即使未传账号密码也能拿到可用的访客凭证，无需强制登录。
    headers = {
        "accept": "application/json, text/plain, */*",
        "accept-language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
        "content-type": "application/json;charset=UTF-8",
        "referer": "https://www.ttinglive.com/",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:148.0) Gecko/20100101 Firefox/148.0",
    }

    data = {
        "loginId": username,
        "password": password,
        "loginKeep": True,
        "saveId": True,
        "device": "PCWEB",
    }

    url = "https://www.ttinglive.com/v2/api/auth/signin"

    try:
        logger.info("Logging into FlexTV platform...")
        cookie_result = await async_req(
            url, proxy_addr=proxy_addr, headers=headers, json_data=data, return_cookies=True, timeout=20
        )

        # async_req 返回 cookies 的形状随版本变化（dict 或 (resp,dict) 元组），统一收敛为 cookie_dict
        if isinstance(cookie_result, dict):
            cookie_dict = cookie_result
        elif isinstance(cookie_result, tuple) and len(cookie_result) == 2 and isinstance(cookie_result[1], dict):
            cookie_dict = cookie_result[1]
        else:
            cookie_dict = {}

        if cookie_dict and "flx_oauth_access" in cookie_dict:
            cookie_str = "; ".join([f"{k}={v}" for k, v in cookie_dict.items()])
            return cookie_str
        else:
            logger.warning("Please check if the FlexTV account and password in the configuration file are correct.")
            return None

    except Exception as e:
        logger.error(i18n.tr("FlexTV login request exception: {e}", e=e))
        raise Exception(
            "FlexTV login failed, please check if the account and password in the configuration file are correct."
        )


async def get_flextv_stream_url(url: str, proxy_addr: OptionalStr = None, cookies: OptionalStr = None) -> str | None:
    # 获取 TTingLive(原Flextv) 直播流地址
    # 返回 str|None（None 表示未开播/无源），调用方 get_flextv_stream_data 据此决定是否置 is_live；
    # 内部 fetch_data 把响应体里的 "HTTP Error 400: Bad Request" 文本当作代理被封信号——
    # flextv 不在 HTTP 层返回 400，而是把错误塞进 body 字符串，需做文本包含判断。
    async def fetch_data(cookie: OptionalStr = None) -> dict[str, object]:
        # 抓取 TTingLive(原Flextv) 直播数据
        headers = {
            "accept": "application/json, text/plain, */*",
            "accept-language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
            "referer": "https://www.ttinglive.com/",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:148.0) Gecko/20100101 Firefox/148.0",
        }
        user_id = url.split("/live")[0].rsplit("/", maxsplit=1)[-1]
        # 调用方透传 cookie 时优先采用；否则走游客态/自动获取凭据（各平台未登录态取流能力不一，部分更易被风控）
        if cookie:
            headers["Cookie"] = cookie
        play_api = f"https://www.ttinglive.com/api/channels/{user_id}/stream?option=all"
        json_str = await async_req(play_api, proxy_addr=proxy_addr, headers=headers, abroad=True)
        json_str = _get_str_response(json_str)
        if "HTTP Error 400: Bad Request" in json_str:
            raise ConnectionError(
                "Failed to retrieve FlexTV live streaming data, please switch to a different proxy and try again."
            )
        # MID-48（2026-09-21 海外批次）：streams 接口对风控返回 HTML 时裸 json.loads 抛错，
        # 会被上层 get_flextv_stream_data 的宽 except 记成「拉取失败」而看不出成因；
        # 改走 _loads_dict，sources 整个键缺失（风控壳页 / 改版）才留线索——
        # {"sources": []} 是「频道存在但未开播」的常态，不得刷告警。
        json_data = _loads_dict(json_str)
        if _dig(json_data, "sources") is None:
            _warn_api_abnormal(json_str, "TTingLive channels/stream", "sources", json_data)
        return json_data

    json_data = await fetch_data(cookies)
    sources = json_data.get("sources")
    # sources 为空/非列表即无可用清晰度的流，返回 None 由调用方按未开播处理
    if sources and isinstance(sources, list) and len(sources) > 0:
        first_source = sources[0]
        if isinstance(first_source, dict):
            play_url = cast(str, first_source.get("url", ""))
            return play_url
    return None


@trace_error_decorator
async def get_flextv_stream_data(
    url: str,
    proxy_addr: OptionalStr = None,
    cookies: OptionalStr = None,
    username: OptionalStr = None,
    password: OptionalStr = None,
) -> dict[str, object]:
    # 获取 TTingLive(原Flextv) 直播流数据
    # 解析链路：未登录走游客头直接请求 live/play，登录态经 login_flextv 拿 token 再请求；
    # 返回 is_live + m3u8 + play_url_list；token 失效由调用方头部透传刷新，无流按未开播返回。
    headers = {
        "accept": "application/json, text/plain, */*",
        "accept-language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
        "referer": "https://www.ttinglive.com/",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:148.0) Gecko/20100101 Firefox/148.0",
    }
    # 调用方透传 cookie 时优先采用；否则走游客态/自动获取凭据（各平台未登录态取流能力不一，部分更易被风控）
    if cookies:
        headers["Cookie"] = cookies
    # user_id 取 URL 中 "/live" 之前最后一段（主播主页路径），是 flextv 频道路由标识。
    user_id = url.split("/live")[0].rsplit("/", maxsplit=1)[-1]
    result: dict[str, object] = {"anchor_name": "", "is_live": False}
    new_cookies = None
    try:
        url2 = f"https://www.ttinglive.com/channels/{user_id}/live"
        html_str = await async_req(url2, proxy_addr=proxy_addr, headers=headers, abroad=True)
        html_str = _get_str_response(html_str)
        json_str_match = re.search('<script id="__NEXT_DATA__" type=".*">(.*?)</script>', html_str)
        if not json_str_match:
            raise ValueError("Failed to find __NEXT_DATA__")
        json_str = json_str_match.group(1)
        # MID-48（2026-09-21 海外批次）：__NEXT_DATA__ 命中但内容被截断/换成风控壳页时，
        # 裸 json.loads 与随后的四级链式索引都抛错，被本函数的宽 except 记成一句「拉取失败」。
        # 改为安全下钻：结构不合预期时落区分性告警（异常仍按既有路径收敛，不外逸）。
        json_data = _loads_dict(json_str)
        channel_data = _dig(json_data, "props", "pageProps", "channel")
        if not isinstance(channel_data, dict):
            _warn_api_abnormal(json_str, "TTingLive channel 页(__NEXT_DATA__)", "props.pageProps.channel", json_data)
            raise ValueError("Failed to get FlexTV channel data")
        # 成人/登录限定房：频道页 message 含韩文「로그인후 이용이 가능합니다.」(需登录)，
        # 此时必须走登录流程换 cookie，否则拿不到流；下方触发 login_flextv 重试整页抓取。
        login_need = "로그인후 이용이 가능합니다." in _dig_str(channel_data, "message")
        if login_need:
            logger.error(
                "FlexTV live stream retrieval failed [not logged in]: 19+ live streams are only available for "
                "logged-in adults."
            )
            logger.warning(
                "Attempting to log in to the FlexTV live streaming platform, please ensure your account and "
                "password are correctly filled in the configuration file."
            )
            if not username or not password or len(username) < 6 or len(password) < 8:
                raise RuntimeError(
                    "TTingLive(原Flextv)登录失败！请在config.ini配置文件中填写正确的TTingLive(原Flextv)平台的账号和密码"
                )
            new_cookies = await login_flextv(username, password, proxy_addr=proxy_addr)
            if new_cookies:
                logger.info("Logged into FlexTV platform successfully! Starting to fetch live streaming data...")
            else:
                raise RuntimeError("TTingLive(原Flextv) login failed")
            cookies = new_cookies if new_cookies else cookies
            if cookies:
                headers["Cookie"] = cookies
            html_str = await async_req(url2, proxy_addr=proxy_addr, headers=headers, abroad=True)
            html_str = _get_str_response(html_str)
            json_str_match = re.search('<script id="__NEXT_DATA__" type=".*">(.*?)</script>', html_str)
            if not json_str_match:
                raise ValueError("Failed to find __NEXT_DATA__")
            json_str = json_str_match.group(1)
            json_data = _loads_dict(json_str)
            channel_data = _dig(json_data, "props", "pageProps", "channel")
            if not isinstance(channel_data, dict):
                # 登录后的二次抓取仍拿不到频道对象：多为登录态失效/风控，与首抓同样归因
                _warn_api_abnormal(
                    json_str, "TTingLive channel 页(__NEXT_DATA__)", "props.pageProps.channel", json_data
                )
                raise ValueError("Failed to get FlexTV channel data")

        # 频道页若带 message 字段说明是未开播/受限占位页，无 message 才是真实在播频道。
        live_status = _dig(channel_data, "message") is None
        if live_status:
            anchor_id = _dig(channel_data, "owner", "loginId")
            if anchor_id is None:
                # 已判在播却无 owner：接口改版/风控降级，与「未开播」区分
                _warn_api_abnormal(
                    json_str, "TTingLive channel 页(__NEXT_DATA__)", "props.pageProps.channel.owner", json_data
                )
                raise ValueError("Failed to get FlexTV owner data")
            anchor_nick = _dig(channel_data, "owner", "nickname")
            anchor_name = f"{anchor_nick}-{anchor_id}"
            result["anchor_name"] = anchor_name
            play_url = await get_flextv_stream_url(url=url, proxy_addr=proxy_addr, cookies=cookies)
            if play_url:
                result["is_live"] = True
                if ".m3u8" in play_url:
                    play_url_list = await get_play_url_list(
                        m3u8=play_url, proxy=proxy_addr, header=headers, abroad=True
                    )
                    if play_url_list:
                        result["m3u8_url"] = play_url
                        result["play_url_list"] = play_url_list
                else:
                    result["flv_url"] = play_url
                    result["record_url"] = play_url
        else:
            url2 = f"https://www.ttinglive.com/channels/{user_id}"
            html_str = await async_req(url2, proxy_addr=proxy_addr, headers=headers, abroad=True)
            html_str = _get_str_response(html_str)
            anchor_name_match = re.search('<meta name="twitter:title" content="(.*?)의', html_str)
            if anchor_name_match:
                anchor_name = anchor_name_match.group(1)
                result["anchor_name"] = anchor_name
    except Exception as e:
        # F-11：print → logger（多参数改用字符串拼接，不用 f-string——f-string 会被
        # i18n 扫描器判为「应改用 i18n.tr」）
        logger.error("Failed to retrieve data from FlexTV live room " + str(e))
    result["new_cookies"] = new_cookies
    return result


def get_looklive_secret_data(text: str | dict[str, str]) -> tuple[str, str]:
    # 本算法参考项目：https://github.com/785415581/MusicBox/blob/b8f716d43d/doc/analysis/analyze_captured_data.md

    # 以下 modulus/nonce/public_key 是网易 weapi 接口的固定加密常量（与网易云音乐同一套 RSA/AES 方案），
    # 由服务端硬编码，不可随意更改——改了服务端也无法解密 params，表现为 200+空/报错。
    modulus = (
        "00e0b509f6259df8642dbc35662901477df22677ec152b5ff68ace615bb7b725152b3ab17a876aea8a5aa76d2e417629ec4ee"
        "341f56135fccf695280104e0312ecbda92557c93870114af6c9d05c4f7f0c3685b7a46bee255932575cce10b424d813cfe487"
        "5d3e82047b97ddef52741d546b8e289dc6935b3ece0462db0a22b8e7"
    )
    nonce = b"0CoJUm6Qyw8W8jud"
    public_key = "010001"
    import base64
    import binascii
    import secrets

    from Crypto.Cipher import AES
    from Crypto.Util.Padding import pad

    def create_secret_key(size: int) -> bytes:
        # 生成网易 weapi/Look 直播方案用的随机 sec_key（每请求独立生成，无状态、不缓存）
        charset = "1234567890abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ!@#$%^&*()_+-=[]{}|;:,.<>?"
        return "".join(secrets.choice(charset) for _ in range(size)).encode("utf-8")

    def aes_encrypt(_text: str | bytes, _sec_key: str | bytes) -> bytes:
        # 网易 weapi 标准 AES-128-CBC：密钥取前 16 字节、IV 固定为 "0102030405060708"（服务端约定，
        # 不可改），明文先 PKCS7 填充再加密；外层对 nonce、内层对随机 sec_key 做两次加密。
        if isinstance(_text, str):
            _text = _text.encode("utf-8")
        if isinstance(_sec_key, str):
            _sec_key = _sec_key.encode("utf-8")
        _sec_key = _sec_key[:16]  # AES-128 固定 16 字节密钥
        iv = bytes("0102030405060708", "utf-8")
        encryptor = AES.new(_sec_key, AES.MODE_CBC, iv)
        padded_text = pad(_text, AES.block_size)
        ciphertext = encryptor.encrypt(padded_text)
        encoded_ciphertext = base64.b64encode(ciphertext)
        return encoded_ciphertext

    def rsa_encrypt(_text: str | bytes, pub_key: str, mod: str) -> str:
        # 网易 weapi 的 RSA：明文先反转字节序再以固定公钥(pub_key="010001")对 modulus 取幂，
        # 结果补零到 256 位十六进制——这是网易云音乐同款逆向参数 encSecKey 的生成方式。
        if isinstance(_text, str):
            _text = _text.encode("utf-8")
        text_reversed = _text[::-1]
        text_int = int(binascii.hexlify(text_reversed), 16)
        encrypted_int = pow(text_int, int(pub_key, 16), int(mod, 16))
        return format(encrypted_int, "x").zfill(256)

    sec_key = create_secret_key(16)
    enc_text = aes_encrypt(aes_encrypt(json.dumps(text), nonce), sec_key)
    enc_sec_key = rsa_encrypt(sec_key, public_key, modulus)
    return enc_text.decode(), enc_sec_key


# CR-12 修复：与其余 50+ 平台入口保持一致，补兜底装饰器。缺失时该平台的任意异常
# （含下方 room_id 正则失配）都会穿透到 main.py 计入 host 熔断失败样本。
@trace_error_decorator
async def get_looklive_stream_url(
    url: str, proxy_addr: OptionalStr = None, cookies: OptionalStr = None
) -> dict[str, object]:
    # 获取网易 Look 直播流地址（PC 网页端接口，签名细节见下方 get_looklive_secret_data 调用处）

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:148.0) Gecko/20100101 Firefox/148.0",
        "Accept": "application/json, text/javascript",
        "Accept-Language": "zh-CN,zh;q=0.8,zh-TW;q=0.7,zh-HK;q=0.5,en-US;q=0.3,en;q=0.2",
        "Content-Type": "application/x-www-form-urlencoded",
        "Referer": "https://look.163.com/",
    }

    # 调用方透传 cookie 时优先采用；否则走游客态/自动获取凭据（各平台未登录态取流能力不一，部分更易被风控）
    if cookies:
        headers["Cookie"] = cookies

    # MI-17 修复：原正则尾部写死 `&`，以 id 结尾的分享链接
    # （https://look.163.com/live?id=32108888，无后续参数）必然匹配失败 →
    # ValueError → 该直播间永久解析失败。改为字符类终止，覆盖 & ? # 与串尾。
    room_id_match = re.search(r"live\?id=([^&?#]+)", url)
    if not room_id_match:
        raise ValueError("Failed to find room id in url")
    room_id = room_id_match.group(1)
    # 接口只接受 params/encSecKey 两个加密字段（网易 weapi 方案）：先用随机 sec_key 对明文做
    # 两次 AES-CBC，再用固定公钥 RSA 加密 sec_key 得到 encSecKey，服务端反向解密。明文缺失 room_id 即失败。
    params, secretkey = get_looklive_secret_data({"liveRoomNo": room_id})
    request_data = {"params": params, "encSecKey": secretkey}
    api = "https://api.look.163.com/weapi/livestream/room/get/v3"
    json_str = await async_req(api, proxy_addr=proxy_addr, headers=headers, data=request_data)
    json_str = _get_str_response(json_str)
    # MID-48（2026-09-21 海外批次）：weapi 接口对风控/参数失效返回 HTML 或不含 data 的信封，
    # 原 `["data"]["anchor"]["nickName"]` 三级索引抛错后被装饰器伪装成「未开播」。
    json_data = _loads_dict(json_str)
    room_block = cast(dict[str, object], _dig(json_data, "data") or {})
    if _dig(room_block, "liveStatus") is None:
        _warn_api_abnormal(json_str, "Look 房间接口 room/get/v3", "data.liveStatus", json_data)
        return {"anchor_name": _dig_str(room_block, "anchor", "nickName"), "is_live": False}
    anchor_name = _dig_str(room_block, "anchor", "nickName")
    live_status = _dig(room_block, "liveStatus")
    result: dict[str, object] = {"anchor_name": anchor_name, "is_live": False}
    # liveStatus==1 为开播；liveType==1 是纯音频直播（无视频流，无法录视频，仅提示不报错）。
    if live_status == 1:
        result["is_live"] = True
        room_info = cast(dict[str, object], _dig(room_block, "roomInfo") or {})
        # liveType==1 是纯音频直播：无视频流可录，仅提示不取 play_url
        if _dig(room_info, "liveType") == 1:
            logger.info("Look live currently only supports audio live streaming, not video live streaming!")
        else:
            play_url_list = cast(dict[str, object], _dig(room_info, "liveUrl") or {})
            live_title = _dig_str(room_info, "title")
            flv_url = _dig_str(play_url_list, "httpPullUrl")
            m3u8_url = _dig_str(play_url_list, "hlsPullUrl")
            # MID-2212（2026-09-22）：原 `if not flv_url or not m3u8_url` 把「FLV 与 HLS 同时存在」
            # 当开播必要条件，与上层 stream_select 的「hls/flv/record_url 三通道各自可空、按可用性
            # 回退」设计相反——只下发单路的房间每轮被判未开播，且「未开播」轮次刻意静默，用户与
            # 日志都无线索。改为两路皆空才判无源，否则只写实际拿到的那一路。
            if not flv_url and not m3u8_url:
                # 已判开播却两路皆无（改版 / 风控降级）：按无源返回并留线索
                _warn_api_abnormal(json_str, "Look 房间接口 room/get/v3", "data.roomInfo.liveUrl", json_data)
                result["is_live"] = False
                return result
            result |= {
                "title": live_title,
                "flv_url": flv_url,
                "m3u8_url": m3u8_url,
            }
            # MID-2212：record_url 恒取可用的一路（HLS 优先、退 FLV），与上方判据同向放宽。
            result["record_url"] = m3u8_url or flv_url
    return result


# SEV-07 修复（2026-09-20，CR-12 契约收口）：本函数返回二元组 (token, partnerCode)，
# 原先挂 trace_error_decorator（失败值 {"is_live": False}）——调用点 `new_access_token,
# new_partner_code = await login_popkontv(...)` 解包 dict 抛 ValueError，被调用方自己的
# 装饰器二次吞掉，函数内三条路径（E4010 / HTTPStatusError / 网络异常）raise 的
# 「账号密码错误」这一用户可自助修复的提示彻底丢失。改用 _or_none：失败回 None，
# 原始异常信息由装饰器 guard 落 error 日志，调用点显式判空后再解包。
@trace_error_decorator_or_none
async def login_popkontv(
    username: str, password: str, proxy_addr: OptionalStr = None, code: OptionalStr = "P-00001"
) -> tuple[str, str]:
    # PopkonTV 平台登录认证
    headers = {
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
        # 应用级固定 API 凭据（非用户私人凭据），嵌入于 PopkonTV 客户端，无法从主页动态获取
        "Authorization": "Basic " + _popkontv_credential(),
        "Content-Type": "application/json",
        "Origin": "https://www.popkontv.com",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:148.0) Gecko/20100101 Firefox/148.0",
    }

    data = {
        "partnerCode": code,
        "signId": username,
        "signPwd": password,
    }

    url = "https://www.popkontv.com/api/proxy/member/v1/login"

    try:
        proxy_addr = utils.handle_proxy_addr(proxy_addr)
        async with httpx.AsyncClient(proxy=proxy_addr, timeout=20, verify=http_config.ssl_verify) as client:
            response = await client.post(url, json=data, headers=headers)
            response.raise_for_status()

            json_data = response.json()
            login_status_code = json_data.get("statusCd")

            # 登录网关状态：E4010 账号/密码错误；S2000 成功（返回 token 与 partnerCode 两件套）；
            # 其余按未知错误抛出。token 是后续所有播放接口的 Bearer 凭据，partnerCode 随账号绑定。
            if login_status_code == "E4010":
                raise Exception("popkontv login failed, please reconfigure the correct login account or password!")
            elif login_status_code == "S2000":
                token = json_data["data"].get("token")
                partner_code = json_data["data"].get("partnerCode")
                return token, partner_code
            else:
                raise Exception(f"popkontv login failed, {json_data.get('statusMsg', 'unknown error')}")
    except httpx.HTTPStatusError as e:
        logger.error(
            i18n.tr("HTTP status error occurred during login: {status_code}", status_code=e.response.status_code)
        )
        raise
    except Exception as e:
        # M-4（2026-09-29）：本函数是全文件唯一**绕过 async_req** 的生产 httpx 请求，因此拿不到
        # async_http 那条「异常文本一律过 mask_credentials」的现成防线（见 async_req 的失败分支）。
        # httpx/urllib3 的连接与代理异常原文里会内嵌**含 user:pass@ 的代理 URL**（本仓 [Proxy] 配置
        # 允许 http://user:pass@host:port 写法），而 logger.error 直接落 logs（轮转保留多份 = 凭据长期落盘）。
        # 同时按 AGENTS「异常日志必须带异常类型与上下文」补 type_name：Windows 下超时类异常的 str(e)
        # 可能是空串，裸 {e} 会打出一条空白行、无法归因。
        logger.error(
            i18n.tr(
                "An exception occurred during popkontv login: {type_name}: {e}",
                type_name=type(e).__name__,
                e=utils.mask_credentials(str(e)),
            )
        )
        raise


# CR-12 修复：本函数返回二元组，失败时必须回 None 而不是 {"is_live": False}——
# 后者会让下方 `anchor_name, room_info = await get_popkontv_stream_data(...)` 抛
# ValueError，该错误又被调用方自己的装饰器二次吞没，根因彻底丢失。
@trace_error_decorator_or_none
async def get_popkontv_stream_data(
    url: str,
    proxy_addr: OptionalStr = None,
    cookies: OptionalStr = None,
    username: OptionalStr = None,
    code: OptionalStr = "P-00001",
) -> tuple[str, list[object] | None]:
    # 获取 PopkonTV 直播流数据
    # 解析链路：broadcast/search/all 按 anchor_id 找 mcSignId → 必要时从 notices 抠昵称补 partnerCode；
    # 返回 (anchor_name, room_info|None)；room_info 为 None 表示未开播，交由 get_popkontv_stream_url 判否。
    headers = {
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
        "Content-Type": "application/json",
        "Origin": "https://www.popkontv.com",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:148.0) Gecko/20100101 Firefox/148.0",
    }
    # 调用方透传 cookie 时优先采用；否则走游客态/自动获取凭据（各平台未登录态取流能力不一，部分更易被风控）
    if cookies:
        headers["Cookie"] = cookies
    if "mcid" in url:
        # MID-45（2026-09-20，MI-17 收口）：原正则 "mcid=(.*?)&" 要求参数后必有 &，
        # 形如 https://www.popkontv.com/channel/notices?mcid=XXXX 的分享链接（参数位于串尾）
        # 恒匹配失败 → ValueError → 装饰器伪装未开播、永久解析失败。
        #  lookahead 兼收 & / # / 串尾三形态，与同文件 rid= / castId= 已修写法一致。
        anchor_id_match = re.search("mcid=(.*?)(?=&|#|$)", url)
    else:
        anchor_id_match = re.search("castId=(.*?)(?=&|$)", url)
    if not anchor_id_match:
        raise ValueError("Failed to find anchor id in url")
    anchor_id = anchor_id_match.group(1)

    data = {
        "partnerCode": code,
        "searchKeyword": anchor_id,
        "signId": username,
    }

    api = "https://www.popkontv.com/api/proxy/broadcast/v1/search/all"
    json_str = await async_req(api, proxy_addr=proxy_addr, headers=headers, json_data=data, abroad=True)
    json_str = _get_str_response(json_str)
    # MID-48（2026-09-21 海外批次）：search/all 对不存在的 castId 返回不含 data 的信封（或被
    # 风控换成 HTML），原 `["data"]["broadCastList"]` + 循环内三重索引任一抛错都被 _or_none
    # 装饰器吞成 None，调用点只报「未开播」。改为安全下钻 + 缺字段归因（仍按既有语义返回 None 契约）。
    json_data = _loads_dict(json_str)
    search_data = _dig(json_data, "data")
    if search_data is None:
        _warn_api_abnormal(json_str, "PopkonTV search/all", "data.broadCastList", json_data)
        raise RuntimeError("Failed to retrieve popkontv broadcast list")

    partner_code: str | None = ""
    anchor_name = "Unknown"
    for item in _dig_list(search_data, "broadCastList"):
        if _dig(item, "mcSignId") == anchor_id:
            mc_name = _dig(item, "nickName")
            anchor_name = f"{mc_name}-{anchor_id}"
            partner_code = cast(str | None, _dig(item, "mcPartnerCode")) if item else None
            break

    if not partner_code:
        # 搜索接口未带出 partnerCode 时，优先从 URL 抠（mcPartnerCode/partnerCode），都没有则用默认 code；
        # 再抓 notices 页用正则抠出 mcNickName 补全主播名（搜索结果里没昵称时的兜底）。
        if "mcPartnerCode" in url:
            regex_result = re.search("mcPartnerCode=(P-\\d+)", url)
        else:
            regex_result = re.search("partnerCode=(P-\\d+)", url)
        partner_code = regex_result.group(1) if regex_result else code
        notices_url = f"https://www.popkontv.com/channel/notices?mcid={anchor_id}&mcPartnerCode={partner_code}"
        notices_response = await async_req(notices_url, proxy_addr=proxy_addr, headers=headers, abroad=True)
        notices_response = _get_str_response(notices_response)
        mc_name_match = re.search(r'"mcNickName":"([^"]+)"', notices_response)
        mc_name = mc_name_match.group(1) if mc_name_match else "Unknown"
        anchor_name = f"{anchor_id}-{mc_name}"

    live_url = f"https://www.popkontv.com/live/view?castId={anchor_id}&partnerCode={partner_code}"
    html_str2 = await async_req(live_url, proxy_addr=proxy_addr, headers=headers, abroad=True)
    html_str2 = _get_str_response(html_str2)
    json_str2_match = re.search('<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', html_str2)
    if not json_str2_match:
        return anchor_name, None
    json_str2 = json_str2_match.group(1)
    # MID-48（2026-09-21 海外批次）：view 页的 __NEXT_DATA__ 命中但内容被截断/换成风控壳页时，
    # 裸 json.loads 与后续四级链式索引抛错，与「房间存在但未开播」（无 mcData）混成同一条。
    # 未开播形态（pageProps 里没有 mcData）保持既有静默返回。
    json_data2 = _loads_dict(json_str2)
    page_props = _dig(json_data2, "props", "pageProps")
    if page_props is None:
        _warn_api_abnormal(json_str2, "PopkonTV live/view(__NEXT_DATA__)", "props.pageProps", json_data2)
        raise RuntimeError("Failed to retrieve popkontv live view page data")
    if _dig(page_props, "mcData") is None:
        return anchor_name, None
    room_data = _dig(page_props, "mcData", "data")
    room_keys = ("mc_isPrivate", "mc_castStartDate", "mc_signId", "castType")
    if not isinstance(room_data, dict) or any(_dig(room_data, key) is None for key in room_keys):
        # mcData 在但四个开播字段任一缺失/为 null：原实现同样在此抛 KeyError/ValueError 被
        # _or_none 吞成 None，只是没有线索；补一条区分性告警后维持同一返回契约。
        _warn_api_abnormal(json_str2, "PopkonTV live/view(__NEXT_DATA__)", "props.pageProps.mcData.data", json_data2)
        raise RuntimeError("Failed to retrieve popkontv room data")
    is_private = _dig(room_data, "mc_isPrivate")
    cast_start_date_code = _dig(room_data, "mc_castStartDate")
    mc_sign_id = _dig(room_data, "mc_signId")
    cast_type = _dig(room_data, "castType")
    return anchor_name, [cast_start_date_code, partner_code, mc_sign_id, cast_type, is_private]


@trace_error_decorator
async def get_popkontv_stream_url(
    url: str,
    proxy_addr: OptionalStr = None,
    access_token: OptionalStr = None,
    username: OptionalStr = None,
    password: OptionalStr = None,
    partner_code: OptionalStr = "P-00001",
) -> dict[str, object]:
    # 获取 PopkonTV 直播流地址
    # 解析链路：复用 get_popkontv_stream_data 的 room_info → castwatchonoffguest 拿 HLS；
    # token 失效(E5000/400)自动登录刷新（新 token 长度须 640）；返回 is_live + m3u8 + new_token。
    # new_token 契约（SEV-N02 修复，2026-09-21）：**裸 token，不含 "Bearer "**——main.py 把它原样
    # 写入 config.ini 的 [Authorization] popkontv_token，读回后经下方 access_token 归一再补前缀。
    headers = {
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
        "ClientKey": "Client " + _popkontv_credential(),
        "Content-Type": "application/json",
        "Origin": "https://www.popkontv.com",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:148.0) Gecko/20100101 Firefox/148.0",
    }

    # 调用方透传 Bearer token 时优先采用；否则复用游客态，token 失效由下方分支触发登录刷新
    # SEV-N02 修复（2026-09-21，CODE_REVIEW_2026-09-21）：入参先归一成**裸 token**再补前缀。
    # 存量用户的 [Authorization] popkontv_token 已被旧实现写坏成自带 "Bearer "（旧实现把带前缀的
    # 串整体落盘，这里又拼一次 → 实际发出 "Bearer Bearer <token>"，服务端必回 400 / E5000）。
    # 读取侧剥前缀，让这批配置无需用户手工修改即可自愈。
    if access_token:
        _bare_access_token = access_token.strip().removeprefix("Bearer ").strip()
        headers["Authorization"] = f"Bearer {_bare_access_token}"

    # CR-12：装饰失败返回 None，显式判空后再解包，避免拿到 dict 触发 ValueError
    popkon_data = await get_popkontv_stream_data(url, proxy_addr=proxy_addr, code=partner_code, username=username)
    if not popkon_data:
        return {"anchor_name": "", "is_live": False}
    anchor_name, room_info = popkon_data
    result: dict[str, object] = {"anchor_name": anchor_name, "is_live": False}
    new_token = None
    if room_info:
        cast_start_date_code, cast_partner_code, mc_sign_id, cast_type, is_private = room_info
        result["is_live"] = True
        room_password = get_params(url, "pwd")
        # 私有房间且未配密码：必须带 pwd 才能取流，否则抛错提示配置密码
        # M-05（2026-10-02）：判定不再依赖字段的具体 JSON 类型——原 `int(cast(str, is_private))`
        # 在 API 以 JSON 布尔下发 mc_isPrivate 时抛 ValueError（int("True") 非法），被兜底装饰器
        # 吞成 {"is_live": False}，开播房间恒判未开播。
        # [历史注] 同日首版改成裸真值 `if is_private`，实测证伪：字符串 "0" 的 bool() 为 True，
        # 下发 "0" 的公开房间会被误判成私有并整轮报错。现走全仓统一布尔口径 parse_config_bool
        # （bool 短路 / int 非零 / "0"·"false"·"否" 等 token 归一）；无法识别的取值按「非私有」
        # 放行取流，宁可让后续取流环节自然失败，也不误挡公开房间。
        # 回归锁：tests/test_spider_platforms.py::TestPopkontvIsPrivateParsing（三形态矩阵）。
        if parse_config_bool(cast("str | bool | int | None", is_private), False) and not room_password:
            raise RuntimeError(
                f"Failed to retrieve live room data because {anchor_name}'s room is a private room. "
                f"Please configure the room password and try again."
            )

        current_partner_code = partner_code  # 跟踪当前有效的 partner_code，登录刷新后更新

        async def fetch_data(header: dict[str, str] | None = None, code: OptionalStr = None) -> str:
            # 抓取 PopkonTV 直播数据
            data = {
                "androidStore": 0,
                "castCode": f"{mc_sign_id}-{cast_start_date_code}",
                "castPartnerCode": cast_partner_code,
                "castSignId": mc_sign_id,
                "castType": cast_type,
                "commandType": 0,
                "exePath": 5,
                "isSecret": is_private,
                "partnerCode": code,
                "password": room_password,
                "signId": username,
                "version": "4.6.2",
            }
            play_api = "https://www.popkontv.com/api/proxy/broadcast/v1/castwatchonoffguest"
            resp = await async_req(play_api, proxy_addr=proxy_addr, json_data=data, headers=header, abroad=True)
            return _get_str_response(resp)

        json_str = await fetch_data(headers, current_partner_code)
        json_str = _get_str_response(json_str)

        # token 失效/不存在：接口返回 HTTP 400 或 body 内 statusCd E5000，均表示 Bearer 凭据过期，
        # 触发登录刷新（新 token 长度必须为 640，否则视为登录失败）。登录后复用新 partnerCode 重试。
        if "HTTP Error 400" in json_str or 'statusCd":"E5000' in json_str:
            logger.error(
                "Failed to retrieve popkontv live stream [token does not exist or has expired]: Please log in to "
                "watch."
            )
            logger.warning(
                "Attempting to log in to the popkontv live streaming platform, please ensure your account "
                "and password are correctly filled in the configuration file."
            )
            if not username or not password or len(username) < 4 or len(password) < 10:
                raise RuntimeError(
                    "popkontv login failed! Please enter the correct account and password for the "
                    "popkontv platform in the config.ini file."
                )
            logger.info("Logging into popkontv platform...")
            # SEV-07：login_popkontv 现为 _or_none（登录失败/异常回 None，账号密码错误原文
            # 已由装饰器 guard 落 error 日志）。CR-12 契约——判空后再解包。
            login_result = await login_popkontv(
                username=username, password=password, proxy_addr=proxy_addr, code=current_partner_code
            )
            if not login_result:
                raise RuntimeError("popkontv login failed, please check if the account and password are correct")
            new_access_token, new_partner_code = login_result
            # 新 token 长度固定 640 字节是登录接口的真实返回特征，偏离即说明登录未真正成功。
            if new_access_token and len(new_access_token) == 640:
                logger.info("Logged into popkontv platform successfully! Starting to fetch live streaming data...")
                headers["Authorization"] = f"Bearer {new_access_token}"
                # SEV-N02 修复（2026-09-21，CODE_REVIEW_2026-09-21）：落盘值改为**裸 token**，
                # "Bearer " 前缀只存在于请求头。旧实现在此处把带前缀的串一并回传，main.py 原样写入
                # config.ini 的 [Authorization] popkontv_token，下一轮读回后又拼一次前缀，
                # 双前缀凭据必被拒 → 每个检测轮次（默认 120s）都重跑一次明文账号密码登录
                # （自建客户端 + 配置写回 + 触发备份线程），len==640 的长度校验形同虚设。
                new_token = new_access_token
                current_partner_code = new_partner_code
                json_str = await fetch_data(headers, current_partner_code)
                json_str = _get_str_response(json_str)
            else:
                raise RuntimeError("popkontv login failed, please check if the account and password are correct")
        # MID-48（2026-09-21 海外批次）：castwatchonoffguest 被风控换成 HTML、或返回不含 statusCd
        # 的信封时，原 `["statusMsg"]` + `["statusCd"]` 索引抛错后被装饰器伪装成「未开播」，与既有
        # 可诊断的 L000A / 未知状态码分支混成同一条。补一条「响应结构不合预期」告警后再交装饰器兜底。
        json_data = _loads_dict(json_str)
        status_cd = _dig_str(json_data, "statusCd")
        status_msg = _dig_str(json_data, "statusMsg")
        if not status_cd:
            _warn_api_abnormal(json_str, "PopkonTV castwatchonoffguest", "statusCd", json_data)
            raise RuntimeError("Failed to retrieve live stream source, no statusCd in response")
        # L000A：未实名/未手机验证会员，服务端拒绝提供流；L0000：成功拿到 HLS；L0001：首请求需二次确认。
        if status_cd == "L000A":
            # F-11：print → logger（多参数用字符串拼接，避免 f-string 触发 i18n 门禁）
            logger.error("Failed to retrieve live stream source, " + str(status_msg))
            raise RuntimeError(
                "You are an unverified member. After logging into the popkontv official website, "
                "please verify your mobile phone at the bottom of the 'My Page' > 'Edit My "
                "Information' to use the service."
            )
        elif status_cd == "L0001":
            # 对同参数再请求一次（首请求偶发需二次确认才返回真实 HLS）。
            # [历史注] M-05 清理（2026-10-02）：原此处计算的 cast_start_date_code_int（原值减 1）
            # 从未传入重试（fetch_data 闭包仍用原值），属死代码已删；若减 1 才是正确值，
            # 则此处重试可能仍失败——属潜在的时效/边界坑位。
            json_str = await fetch_data(headers, current_partner_code)
            json_str = _get_str_response(json_str)
            json_data = _loads_dict(json_str)
            m3u8_url = _dig_str(json_data, "data", "castHlsUrl")
            if not m3u8_url:
                _warn_api_abnormal(json_str, "PopkonTV castwatchonoffguest", "data.castHlsUrl", json_data)
                raise RuntimeError("Failed to retrieve live stream source, no castHlsUrl in response")
            result |= {"m3u8_url": m3u8_url, "record_url": m3u8_url}
        elif status_cd == "L0000":
            m3u8_url = _dig_str(json_data, "data", "castHlsUrl")
            if not m3u8_url:
                _warn_api_abnormal(json_str, "PopkonTV castwatchonoffguest", "data.castHlsUrl", json_data)
                raise RuntimeError("Failed to retrieve live stream source, no castHlsUrl in response")
            result |= {"m3u8_url": m3u8_url, "record_url": m3u8_url}
        else:
            raise RuntimeError("Failed to retrieve live stream source,", status_msg)
    result["new_token"] = new_token
    return result


# SEV-07 修复（2026-09-20，CR-12 契约收口）：本函数返回 OptionalStr（cookie 串或 None），
# 原先挂 trace_error_decorator——cs_session_id 抠取与首次抓页都在内层 try 之外，抛错即被
# 转成 {"is_live": False}；调用点判空写的是 `if not new_cookie: raise ...`，**dict 恒为真**，
# 于是把 dict 赋给 headers["Cookie"] 交给 httpx → TypeError → 又被外层装饰器吞 →
# 需登录房间在风控/改版时表现为静默「未开播」。改用 _or_none 后失败回 None，
# 调用点判空 + isinstance str 断言双保险。
@trace_error_decorator_or_none
async def login_twitcasting(
    account_type: str, username: str, password: str, proxy_addr: OptionalStr = None, cookies: OptionalStr = None
) -> OptionalStr:
    # TwitCasting 平台登录认证
    headers = {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
        "Content-Type": "application/x-www-form-urlencoded",
        "Referer": "https://twitcasting.tv/indexcaslogin.php?redir=%2Findexloginwindow.php%3Fnext%3D%252F&keep=1",
        # 移除原硬编码的 TwitCasting 访客统计 Cookie（hl/did/_ga 等均为临时统计字段）
        # 登录流程由 cs_session_id 驱动，不依赖此 Cookie；未配置时不发送 Cookie 头
        "User-Agent": "ios/7.830 (ios 17.0; ; iPhone 15 (A2846/A3089/A3090/A3092))",
    }

    if cookies:
        headers["Cookie"] = cookies

    if account_type == "twitter":
        login_url = "https://twitcasting.tv/indexpasswordlogin.php"
        login_api = "https://twitcasting.tv/indexpasswordlogin.php?redir=/indexloginwindow.php?next=%2F&keep=1"
    else:
        login_url = "https://twitcasting.tv/indexcaslogin.php?redir=%2F&keep=1"
        login_api = "https://twitcasting.tv/indexcaslogin.php?redir=/indexloginwindow.php?next=%2F&keep=1"

    html_str = await async_req(login_url, proxy_addr=proxy_addr, headers=headers)
    html_str = _get_str_response(html_str)
    cs_session_id_match = re.search('<input type="hidden" name="cs_session_id" value="(.*?)">', html_str)
    if not cs_session_id_match:
        raise ValueError("Failed to find cs_session_id")
    cs_session_id = cs_session_id_match.group(1)

    data = {
        "username": username,
        "password": password,
        "action": "login",
        "cs_session_id": cs_session_id,
    }
    try:
        cookie_result = await async_req(
            login_api, proxy_addr=proxy_addr, headers=headers, data=data, return_cookies=True, timeout=20
        )
        if isinstance(cookie_result, dict):
            cookie_dict = cookie_result
        elif isinstance(cookie_result, tuple) and len(cookie_result) == 2 and isinstance(cookie_result[1], dict):
            cookie_dict = cookie_result[1]
        else:
            cookie_dict = {}

        if "tc_ss" in cookie_dict:
            cookie = utils.dict_to_cookie_str(cookie_dict)
            return cookie
    except Exception as e:
        # F-11：print → logger（多参数用字符串拼接，避免 f-string 触发 i18n 门禁）
        logger.error("TwitCasting login error, " + str(e))
    return None


@trace_error_decorator
async def get_twitcasting_stream_url(
    url: str,
    proxy_addr: OptionalStr = None,
    cookies: OptionalStr = None,
    account_type: OptionalStr = None,
    username: OptionalStr = None,
    password: OptionalStr = None,
) -> dict[str, object]:
    # 获取 TwitCasting 直播流地址
    # 解析链路：畸形 URL 显式报错 → 必要时 login_twitcasting 拿 cookie → get_data 抠 title/status/movie_id；
    # data-is-onlive="true" 才取流；返回 is_live + play_url_list（高>中>低排序），未开播不取流。
    headers = {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
        "Referer": "https://twitcasting.tv/?ch0",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:148.0) Gecko/20100101 Firefox/148.0",
    }

    parts = url.split("?")[0].split("/")
    # 畸形 URL（无主播 ID 段）：显式报错而非 IndexError
    if len(parts) < 4 or not parts[3].strip():
        # M-3（2026-09-29）：异常消息里的 URL 先过脱敏（同 PandaTV/WinkTV 口径）
        raise RuntimeError(f"无法从链接中解析 TwitCasting 主播 ID: {utils.mask_credentials(url)}")
    anchor_id = parts[3]
    # 调用方透传 cookie 时优先采用；否则走游客态/自动获取凭据（各平台未登录态取流能力不一，部分更易被风控）
    if cookies:
        headers["Cookie"] = cookies

    async def get_data(header: dict[str, str]) -> tuple[str, str, str]:
        # 获取 TwitCasting 直播数据
        html_str = await async_req(url, proxy_addr=proxy_addr, headers=header)
        html_str = _get_str_response(html_str)
        anchor = re.search("<title>(.*?) \\(@(.*?)\\)  的直播 - Twit", html_str)
        title = re.search('<meta name="twitter:title" content="(.*?)">\n\\s+<meta', html_str)
        status = re.search('data-is-onlive="(.*?)"\n\\s+data-view-mode', html_str)
        movie_id = re.search('data-movie-id="(.*?)" data-audience-id', html_str)
        if not anchor or not title or not status or not movie_id:
            raise ValueError("Failed to parse page data")
        return f"{anchor.group(1).strip()}-{anchor.group(2)}-{movie_id.group(1)}", status.group(1), title.group(1)

    result: dict[str, object] = {"anchor_name": "", "is_live": False}
    new_cookie = None
    anchor_name = ""
    live_status = ""
    live_title = ""
    try:
        to_login = get_params(url, "login")
        if to_login == "true":
            logger.info("Attempting to log in to TwitCasting...")
            new_cookie = await login_twitcasting(
                account_type=cast(str, account_type),
                username=cast(str, username),
                password=cast(str, password),
                proxy_addr=proxy_addr,
                cookies=cookies,
            )
            # SEV-07：判空 + isinstance str 双保险——装饰器契约为 OptionalStr，
            # 非字符串（含旧 dict 形态）绝不允许写进 Cookie 头（httpx 会 TypeError）。
            if not isinstance(new_cookie, str) or not new_cookie:
                raise RuntimeError(
                    "TwitCasting login failed, please check if the account password in the "
                    "configuration file is correct"
                )
            logger.info("TwitCasting login successful! Starting to fetch data...")
            headers["Cookie"] = new_cookie
        anchor_name, live_status, live_title = await get_data(headers)
    # 解析阶段抛 AttributeError（页面结构变化/受限，正则 group 落在 None 上）即视为需登录，
    # 这里统一回落到登录流程再抓一次；登录失败则向上抛 RuntimeError。
    # M-10（2026-09-29）：同一分支还必须接住 ValueError。get_data 在四个正则任一未命中时
    # **显式** `raise ValueError("Failed to parse page data")`——这才是受限房/改版的主形态，
    # 而 AttributeError 只在「正则命中了但 group 取不到」这类少境里出现。原实现只 catch
    # AttributeError，于是注释承诺的「解析失败 → 登录重试」在这条最常见路径上是**死分支**：
    # 受限房直接判未开播，登录态永远用不上。PEP 758 无括号写法（本分支不绑定异常对象）。
    # 回归锁：tests/test_spider.py::TestTwitCastingParseFailureLoginFallback
    except AttributeError, ValueError:
        logger.error("Failed to retrieve TwitCasting data, attempting to log in...")
        new_cookie = await login_twitcasting(
            account_type=cast(str, account_type),
            username=cast(str, username),
            password=cast(str, password),
            proxy_addr=proxy_addr,
            cookies=cookies,
        )
        # SEV-07：同上——判空 + isinstance str 断言后才允许写 Cookie 头
        if not isinstance(new_cookie, str) or not new_cookie:
            raise RuntimeError(
                "TwitCasting login failed, please check if the account and password in the "
                "configuration file are correct"
            )
        logger.info("TwitCasting login successful! Starting to fetch data...")
        headers["Cookie"] = new_cookie
        anchor_name, live_status, live_title = await get_data(headers)

    result["anchor_name"] = anchor_name
    # data-is-onlive="true" 才是开播；否则（含未登录受限）按未开播返回，不取流。
    if live_status == "true":
        url_streamserver = f"https://twitcasting.tv/streamserver.php?target={anchor_id}&mode=client&player=pc_web"
        stream_data = await async_req(url_streamserver, proxy_addr=proxy_addr, headers=headers)
        stream_data = _get_str_response(stream_data)
        # MID-48（2026-09-21 海外批次）：streamserver 接口被风控时返回 HTML，裸 json.loads 抛错后
        # 与「页面判定在播但已无 HLS」混成同一条（后者才是既有的 RuntimeError 语义）。
        # 只在整体解析不出对象时补告警，避免给「刚下播」这种常态刷噪声。
        json_data = _loads_dict(stream_data)
        stream_dict = _dig(json_data, "tc-hls", "streams")
        if not json_data:
            _warn_api_abnormal(stream_data, "TwitCasting streamserver", "tc-hls.streams", json_data)
        # tc-hls/streams 缺失即无可用 HLS，报错提示检查链接
        if not stream_dict:
            raise RuntimeError("No m3u8_url,please check the url")

        streams = cast(dict[str, object], stream_dict)
        quality_order = {"high": 0, "medium": 1, "low": 2}
        # 按 高>中>低 顺序排序画质候选，未识别的画质 key 放到最后（quality_order.get 默认 99），
        # 避免服务端新增档位时 KeyError 导致整段解析失败。
        sorted_streams = sorted(streams.items(), key=lambda item: quality_order.get(item[0], 99))
        play_url_list = [url for _, url in sorted_streams]
        result |= {"title": live_title, "is_live": True, "play_url_list": play_url_list}
    result["new_cookies"] = new_cookie
    return result


@trace_error_decorator
async def get_baidu_stream_data(
    url: str, proxy_addr: OptionalStr = None, cookies: OptionalStr = None
) -> dict[str, object]:
    # 获取百度直播流数据
    # 解析链路：随机 h5- uid 游客标识 → searchbox 接口 → data 取 status/url_clarity_list；
    # status=="0" 才取流，flv 转 m3u8 拼固定 CDN；返回 is_live + play_url_list，data 缺失直接回未开播。
    headers = {
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
        "Connection": "keep-alive",
        "Referer": "https://live.baidu.com/",
        "User-Agent": "ios/7.830 (ios 17.0; ; iPhone 15 (A2846/A3089/A3090/A3092))",
    }
    if cookies:
        headers["Cookie"] = cookies

    # 从一组写死的 h5- 设备/访客 uid 里随机挑一个作为匿名标识：百度接口对游客态要求带该 uid，
    # 但不校验其真实归属，随机复用即可；硬编码是为避免每轮请求都生成新设备被风控。
    uid = random.choice(
        [
            "h5-683e85bdf741bf2492586f7ca39bf465",
            "h5-c7c6dc14064a136be4215b452fab9eea",
            "h5-4581281f80bb8968bd9a9dfba6050d3a",
        ]
    )
    # MID-45（2026-09-20，MI-17 收口）：原正则 "room_id=(.*?)&" 要求参数后必有 &，
    # https://live.baidu.com/m/media/pclive/pchome/live.html?room_id=9175031377 这类
    # 参数位于串尾的分享链接恒匹配失败 → ValueError → 永久「未开播」。
    # lookahead 兼收 & / # / 串尾，与同文件 rid= / castId= 已修写法一致。
    room_id_match = re.search("room_id=(.*?)(?=&|#|$)", url)
    if not room_id_match:
        raise ValueError("Failed to find room_id in url")
    room_id = room_id_match.group(1)
    params = {
        "cmd": "371",
        "action": "star",
        "service": "bdbox",
        "osname": "baiduboxapp",
        "data": '{"data":{"room_id":"' + room_id + '","device_id":"h5-683e85bdf741bf2492586f7ca39bf465",'
        '"source_type":0,"osname":"baiduboxapp"},"replay_slice":0,'
        '"nid":"","schemeParams":{"src_pre":"pc","src_suf":"other",'
        '"bd_vid":"","share_uid":"","share_cuk":"","share_ecid":"",'
        '"zb_tag":"","shareTaskInfo":"{\\"room_id\\":\\"9175031377\\"}",'
        '"share_from":"","ext_params":"","nid":""}}',
        "ua": "360_740_ANDROID_0",
        "bd_vid": "",
        "uid": uid,
        "_": str(int(time.time() * 1000)),
    }
    app_api = f"https://mbd.baidu.com/searchbox?{urllib.parse.urlencode(params)}"
    json_str = await async_req(url=app_api, proxy_addr=proxy_addr, headers=headers)
    json_str = _get_str_response(json_str)
    json_data = _loads_dict(json_str)
    data_dict = cast(dict[str, object], json_data.get("data") or {})
    if not data_dict:
        # MID-48：data 缺失既可能是「房间不存在/未开播」也可能是风控换成信封/HTML。
        # 二者都值得留线索（用户侧只会看到「网址内容获取失败」），故不区分 json_str 是否为空，
        # 由 _warn_api_abnormal 内部按「空响应 / 缺字段」两种成因分别落日志。
        _warn_api_abnormal(json_str, "百度 searchbox cmd=371", "data", json_data)
        return {"anchor_name": "", "is_live": False}
    # MIN-2222 修复（2026-09-22）：原取 `list(data_dict.keys())[0]`（**首个键**）——该接口的 data 以
    # room_id 为键（见 tests/test_spider_hardening.py 的百度用例），响应里若混入其它键，dict 顺序一变就取错。
    # 先按稳定键名 room_id 取；取不到再退回「首个 dict 值」并显式做类型过滤（防取到非 dict 值）。
    # 该接口 data 结构为 {"<room_id>": {...}}，room_id 即本次请求所用的房间号，是唯一稳定标识。
    data: object = None
    room_key = _dig(data_dict, room_id)
    if isinstance(room_key, dict):
        data = room_key
    else:
        for _v in data_dict.values():
            if isinstance(_v, dict):
                data = _v
                break
    anchor_name = _dig_str(data, "host", "name")
    result: dict[str, object] = {"anchor_name": anchor_name, "is_live": False}
    if _dig(data, "status") == "0":
        result["is_live"] = True
        live_title = _dig_str(data, "video", "title")
        play_url_list = _dig_list(data, "video", "url_clarity_list")
        # 百度直播只下发 flv 地址，但本机只支持录制 m3u8，故把 flv 地址的「扩展名+host」剥掉、
        # 换成固定 hls CDN 前缀拼回 .m3u8，得到可拉流的 HLS 地址。
        url_list = []
        prefix = "https://hls.liveshow.bdstatic.com/live/"
        if play_url_list:
            # 结构一：url_clarity_list 直接给每档位的 flv 串，剥 .flv 与 host 取流 id 重拼为 m3u8
            for i in play_url_list:
                flv = _dig_str(i, "urls", "flv")
                flv_id = flv.rsplit(".", maxsplit=1)[0].rsplit("/", maxsplit=1)
                url_list.append(prefix + (flv_id[1] if len(flv_id) > 1 else "") + ".m3u8")
        else:
            # 结构二：url_list 嵌套 urls[0].hls（带查询参数），同样剥查询+host 取流 id
            play_url_list = _dig_list(data, "video", "url_list")
            for i in play_url_list:
                urls = _dig_list(i, "urls")
                hls = _dig_str(urls[0], "hls") if urls else ""
                hls_id = hls.rsplit("?", maxsplit=1)[0].rsplit("/", maxsplit=1)
                url_list.append(prefix + (hls_id[1] if len(hls_id) > 1 else ""))

        if url_list:
            result |= {"is_live": True, "title": live_title, "play_url_list": url_list}
        else:
            # status=="0" 却在两种清单结构里都拿不到地址：接口改版/风控降级，不是「未开播」
            _warn_api_abnormal(json_str, "百度 searchbox cmd=371", "video.url_clarity_list", json_data)
            result["is_live"] = False
    return result


@trace_error_decorator
async def get_weibo_stream_data(
    url: str, proxy_addr: OptionalStr = None, cookies: OptionalStr = None
) -> dict[str, object]:
    # 获取微博直播流数据
    # 解析链路：show/<id> 直链或 /u/<uid> 主页列表找 live object → anchor/live_id → pc/anchor/live；
    # status==1 取流；返回 is_live + play_url_list（两组候选，含去画质后缀回退可用源）。
    headers = {
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
        # 移除原硬编码的微博登录态 Cookie（含 XSRF-TOKEN/SUB/SUBP/WBPSESS 等用户登录凭据）
        # 未配置 cookie 时不发送 Cookie 头；公开直播间信息无需登录态
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:148.0) Gecko/20100101 Firefox/148.0",
        "Referer": "https://weibo.com/u/5885340893",
    }
    if cookies:
        headers["Cookie"] = cookies

    room_id = ""
    # 两条入口：show/<id> 直链可直接拿到 room_id；/u/<uid> 主页需先拉微博列表，
    # 在 list 里找 object_type=="live" 的那条取 object_id 作为 room_id（无直播时 room_id 留空→不取流）。
    if "show/" in url:
        room_id = url.split("?")[0].split("show/")[1]
    else:
        parts = url.split("?")[0].rsplit("/u/", maxsplit=1)
        # 畸形 URL（无 /u/ 用户段）：显式报错而非 IndexError
        if len(parts) < 2 or not parts[1].strip():
            # M-3（2026-09-29）：异常消息里的 URL 先过脱敏（同 TwitCasting 口径）
            raise RuntimeError(f"无法从链接中解析微博用户 ID: {utils.mask_credentials(url)}")
        uid = parts[1]
        web_api = f"https://weibo.com/ajax/statuses/mymblog?uid={uid}&page=1&feature=0"
        json_str = await async_req(web_api, proxy_addr=proxy_addr, headers=headers)
        json_str = _get_str_response(json_str)
        # MID-48（2026-09-21）：微博列表接口被风控时会返回 HTML 或 {"error": ...} 信封，
        # 原 json.loads + ["data"]["list"] 任一失败都抛错 → 装饰器 → 「未开播」。列表为空按
        # 「该用户无直播」静默返回（正常离线形态、不刷日志），仅响应解析不出对象时归因。
        json_data = _loads_dict(json_str)
        if not json_data:
            _warn_api_abnormal(json_str, "微博 mymblog", "data.list", json_data)
        for i in _dig_list(json_data, "data", "list"):
            if _dig(i, "page_info", "object_type") == "live":
                room_id = _dig_str(i, "page_info", "object_id")
                break

    result: dict[str, object] = {"anchor_name": "", "is_live": False}
    if room_id:
        app_api = f"https://weibo.com/l/pc/anchor/live?live_id={room_id}"
        # app_api = f'https://weibo.com/l/!/2/wblive/room/show_pc_live.json?live_id={room_id}'
        json_str = await async_req(url=app_api, proxy_addr=proxy_addr, headers=headers)
        json_str = _get_str_response(json_str)
        json_data = _loads_dict(json_str)
        if _dig(json_data, "data", "user_info") is None or _dig(json_data, "data", "item") is None:
            # 房间不存在/已被封时接口只回 {error/code} 信封、无 data.user_info；此前与
            # 「接口改版」同样表现为 data["user_info"]["name"] 的 KeyError → 装饰器 → 未开播。
            _warn_api_abnormal(json_str, "微博 pc/anchor/live", "data.user_info / data.item", json_data)
            return result
        anchor_name = _dig_str(json_data, "data", "user_info", "name")
        result["anchor_name"] = anchor_name
        live_status = _dig(json_data, "data", "item", "status")
        if live_status == 1:
            result["is_live"] = True
            live_title = _dig_str(json_data, "data", "item", "desc")
            play_url_list = _dig(json_data, "data", "item", "stream_info", "pull")
            m3u8_url = _dig_str(play_url_list, "live_origin_hls_url")
            flv_url = _dig_str(play_url_list, "live_origin_flv_url")
            # MID-2212（2026-09-22）：原 `if not m3u8_url or not flv_url` 把「FLV 与 HLS 同时存在」
            # 当开播必要条件，与上层 stream_select 的「hls/flv/record_url 三通道各自可空、按可用性
            # 回退」设计相反——只下发单路的房间每轮被判未开播（「未开播」轮次刻意静默，用户与日志
            # 都无线索），且归因文案还写「风控降级或字段改名」把方向带偏。改为两路皆空才判无源。
            if not m3u8_url and not flv_url:
                # status 已报在播却两路皆无：接口改版/风控降级，不是「未开播」
                _warn_api_abnormal(json_str, "微博 pc/anchor/live", "item.stream_info.pull", json_data)
                result["is_live"] = False
                return result
            result["title"] = live_title
            # 第二组候选把地址里的画质后缀（"_原画"/"_蓝光"等）去掉，回退到默认清晰度，
            # 当原始清晰度档位在 CDN 上不可用时仍有可用源；两组都进 play_url_list 由上层按可达性校验。
            # 单路缺失（MID-2212）时该路候选留空串，由上层按「三通道各自可空」的口径跳过。
            result["play_url_list"] = [
                {"m3u8_url": m3u8_url, "flv_url": flv_url},
                {
                    "m3u8_url": m3u8_url.split("_")[0] + ".m3u8" if m3u8_url else "",
                    "flv_url": flv_url.split("_")[0] + ".flv" if flv_url else "",
                },
            ]
            # 单路缺失时补 record_url 兜底（HLS 优先、退 FLV）：上层 stream_select 以 m3u8/hls 为主
            # 通道，纯 FLV 房间（无 HLS）必须借 record_url 才能取到流；两路齐备或纯 HLS 时不加，
            # 保持既有返回结构不变（避免给已有上游路径平添一条结构差异）。
            if not m3u8_url:
                result["record_url"] = flv_url
    return result


@trace_error_decorator
async def get_kugou_stream_url(
    url: str, proxy_addr: OptionalStr = None, cookies: OptionalStr = None
) -> dict[str, object]:
    # 获取酷狗繁星直播流地址
    # 解析链路：getEnterRoomInfo 拿昵称 + liveType → liveType!=-1 才请求 mutiline/streamaddr 拿 flv；
    # 返回 is_live + flv + record_url；音乐频道房间不支持录制会抛 RuntimeError。
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:148.0) Gecko/20100101 Firefox/148.0",
        "Accept": "application/json",
        "Accept-Language": "zh-CN,zh;q=0.8,zh-TW;q=0.7,zh-HK;q=0.5,en-US;q=0.3,en;q=0.2",
        "Referer": "https://fanxing2.kugou.com/",
    }
    # 调用方透传 cookie 时优先采用；否则走游客态/自动获取凭据（各平台未登录态取流能力不一，部分更易被风控）
    if cookies:
        headers["Cookie"] = cookies

    # 两条入口：URL 直带 roomId 直接抠，否则从路径末段取主播房间号
    if "roomId" in url:
        room_id_match = re.search("roomId=(\\d+)", url)
        if not room_id_match:
            raise ValueError("Failed to find roomId in url")
        room_id = room_id_match.group(1)
    else:
        room_id = _safe_extract_id(url)

    app_api = f"https://service2.fanxing.kugou.com/roomcen/room/web/cdn/getEnterRoomInfo?roomId={room_id}"
    json_str = await async_req(url=app_api, proxy_addr=proxy_addr, headers=headers)
    json_str = _get_str_response(json_str)
    # MID-48：getEnterRoomInfo 对不存在房间/风控返回不含 data.normalRoomInfo 的 JSON 或 HTML。
    # 此处不能简单把「取不到昵称」并入下方那条音乐频道 RuntimeError——那会把接口异常
    # 说成「请换房间」，用户按提示换地址也解决不了。先判响应结构、再判业务空值。
    json_data = _loads_dict(json_str)
    if _dig(json_data, "data", "normalRoomInfo") is None:
        _warn_api_abnormal(json_str, "酷狗 getEnterRoomInfo", "data.normalRoomInfo", json_data)
        return {"anchor_name": "", "is_live": False}
    anchor_name = _dig_str(json_data, "data", "normalRoomInfo", "nickName")
    result: dict[str, object] = {"anchor_name": anchor_name, "is_live": False}
    # 音乐频道房间不支持录制，显式抛错提示换房间
    if not anchor_name:
        raise RuntimeError(
            "Music channel live rooms are not supported for recording, please switch to a different live room."
        )
    live_status = _dig(json_data, "data", "liveType")
    if live_status is None:
        # liveType 缺失不能按「!= -1」当作在播（会把改版误判为开播并白跑第二次请求）
        _warn_api_abnormal(json_str, "酷狗 getEnterRoomInfo", "data.liveType", json_data)
        return result
    # 酷狗用 liveType==-1 表示未开播，其它值（0/1 等）视为在播（注意是「!= -1」而非 == 1）
    if live_status != -1:
        params = {
            "std_rid": room_id,
            "std_plat": "7",
            "std_kid": "0",
            "streamType": "1-2-4-5-8",
            "ua": "fx-flash",
            "targetLiveTypes": "1-5-6",
            "version": "1000",
            "supportEncryptMode": "1",
            "appid": "1010",
            "_": str(int(time.time() * 1000)),
        }
        api = f"https://fx1.service.kugou.com/video/pc/live/pull/mutiline/streamaddr?{urllib.parse.urlencode(params)}"
        json_str2 = await async_req(api, proxy_addr=proxy_addr, headers=headers)
        json_str2 = _get_str_response(json_str2)
        json_data2 = _loads_dict(json_str2)
        if _dig(json_data2, "data") is None:
            # 已判在播却拿不到 data（含 lines）：签名/接口异常，与「lines 为空」的普通离线形态区分
            _warn_api_abnormal(json_str2, "酷狗 mutiline/streamaddr", "data.lines", json_data2)
            return result
        stream_data = _dig_list(json_data2, "data", "lines")
        if stream_data:
            flv_url = _dig_str(stream_data[-1], "streamProfiles", 0, "httpsFlv", 0)
            if not flv_url:
                _warn_api_abnormal(
                    json_str2, "酷狗 mutiline/streamaddr", "lines[-1].streamProfiles[0].httpsFlv[0]", json_data2
                )
                return result
            result |= {"is_live": True, "flv_url": flv_url, "record_url": flv_url}
    return result


async def get_twitchtv_room_info(
    url: str, token: str, proxy_addr: OptionalStr = None, cookies: OptionalStr = None
) -> tuple[str, bool]:
    # 获取 Twitch 直播间信息
    # 动态获取 Twitch Web 端公开 Client-Id，替代原硬编码值
    client_id = await _ensure_twitch_client_id(proxy_addr)
    # MID-48（2026-09-20）：Client-Id 拉取失败（Twitch 改版/风控）时原先照发 `Client-Id: ""`，
    # 制造「必然失败但无日志」的组合——GQL 401 后错误数组穿过守卫再 KeyError，
    # 最终被上层装饰器伪装成「未开播」。现在缺凭据直接显式失败并告警（MID-33 的 TTL 重取
    # 保证下一轮会再试，而不是进程内永久拿同一个空值）。
    if not client_id:
        logger.warning("Twitch Client-Id unavailable (homepage extraction failed), skip GQL request this round")
        raise RuntimeError("Failed to obtain Twitch Client-Id")
    headers = {
        "User-Agent": _TWITCH_WEB_UA,
        "Accept-Language": "zh-CN",
        "Referer": "https://www.twitch.tv/",
        "Client-Id": client_id,
        "Client-Integrity": token,
        "Content-Type": "text/plain;charset=UTF-8",
    }
    # 调用方透传 cookie 时优先采用；否则走游客态/自动获取凭据（各平台未登录态取流能力不一，部分更易被风控）
    if cookies:
        headers["Cookie"] = cookies
    uid = url.split("?")[0].rsplit("/", maxsplit=1)[-1]

    data = [
        {
            "operationName": "ChannelShell",
            "variables": {"login": uid},
            "extensions": {
                "persistedQuery": {
                    "version": 1,
                    "sha256Hash": "580ab410bcd0c1ad194224957ae2241e5d252b2c5173d8e0cce9d32d5bb14efe",
                }
            },
        },
    ]

    json_str = await async_req(
        "https://gql.twitch.tv/gql", proxy_addr=proxy_addr, headers=headers, json_data=data, abroad=True
    )
    json_str = _get_str_response(json_str)
    # MID-48（2026-09-20）：GQL 批量查询响应是 **list**（_loads_dict 只收 dict，不适用），
    # 保留 json.loads 但判掉 JSONDecodeError；并处理此前穿过守卫的非空 errors 数组——
    # 原实现 `json_data[0]["data"]["userOrError"]` 对 errors 响应直接 KeyError，
    # 被上层装饰器吞成「未开播」，真实原因（GQL 拒绝/凭据问题）在日志里彻底丢失。
    try:
        json_data = cast(object, json.loads(json_str))
    except json.JSONDecodeError as e:
        logger.warning("Twitch GQL response is not valid JSON (WAF page? truncated?): " + type(e).__name__)
        raise RuntimeError("Failed to parse Twitch GQL response") from e
    # Twitch GQL 返回异常（非预期数组）即视为拿用户数据失败
    if not json_data or not isinstance(json_data, list) or not isinstance(json_data[0], dict):
        raise RuntimeError("Failed to retrieve Twitch user data")
    first_item = cast(dict[str, object], json_data[0])
    gql_errors = first_item.get("errors")
    if gql_errors:
        logger.warning("Twitch GQL returned errors for ChannelShell: " + str(gql_errors)[:300])
        raise RuntimeError("Twitch GQL errors: see log")
    user_data = cast(dict[str, object], cast(dict[str, object], first_item.get("data") or {}).get("userOrError") or {})
    login_name = user_data.get("login", "")
    nickname = f"{user_data.get('displayName', '')}-{login_name}"
    # Twitch 用 userOrError.stream 字段是否存在来判定开播（有 stream 对象即在播），
    # 返回 (nickname, status) 元组供 get_twitchtv_stream_data 复用作 is_live。
    status = True if user_data.get("stream") else False
    return nickname, status


@trace_error_decorator
async def get_twitchtv_stream_data(
    url: str, proxy_addr: OptionalStr = None, cookies: OptionalStr = None
) -> dict[str, object]:
    # 获取 Twitch 直播流数据
    # 动态获取 Twitch Web 端公开 Client-Id，替代原硬编码值
    client_id = await _ensure_twitch_client_id(proxy_addr)
    # MID-48（2026-09-20）：同 get_twitchtv_room_info——空 Client-Id 不再照发，显式失败交上层
    # 下一轮重试（MID-33 TTL 到期后 _ensure_twitch_client_id 会自动重取）。
    if not client_id:
        logger.warning("Twitch Client-Id unavailable (homepage extraction failed), skip GQL request this round")
        raise RuntimeError("Failed to obtain Twitch Client-Id")
    headers = {
        "User-Agent": _TWITCH_WEB_UA,
        "Accept-Language": "en-US",
        "Referer": "https://www.twitch.tv/",
        "Client-ID": client_id,
        "device-id": generate_random_string(16).lower(),
    }

    # 调用方透传 cookie 时优先采用；否则走游客态/自动获取凭据（各平台未登录态取流能力不一，部分更易被风控）
    if cookies:
        headers["Cookie"] = cookies
    uid = url.split("?")[0].rsplit("/", maxsplit=1)[-1]

    # Twitch 走 GraphQL persisted query：用固定 sha256Hash 指代一条预注册查询，省去传整段 query 文本；
    # Client-Id 必须动态获取（硬编码值会随前端版本过期导致 401），device-id 用随机串每次新建。
    data = {
        "operationName": "PlaybackAccessToken_Template",
        "query": "query PlaybackAccessToken_Template($login: String!, $isLive: Boolean!, $vodID: ID!, "
        "$isVod: Boolean!, $playerType: String!) {  streamPlaybackAccessToken(channelName: $login, "
        'params: {platform: "web", playerBackend: "mediaplayer", playerType: $playerType}) @include(if: '
        "$isLive) {    value    signature   authorization { isForbidden forbiddenReasonCode }   __typename  "
        '}  videoPlaybackAccessToken(id: $vodID, params: {platform: "web", playerBackend: "mediaplayer", '
        "playerType: $playerType}) @include(if: $isVod) {    value    signature   __typename  }}",
        "variables": {"isLive": True, "login": uid, "isVod": False, "vodID": "", "playerType": "site"},
    }

    json_str = await async_req(
        "https://gql.twitch.tv/gql", proxy_addr=proxy_addr, headers=headers, json_data=data, abroad=True
    )
    json_str = _get_str_response(json_str)
    # MID-48（2026-09-20）：裸 json.loads + 深层链式索引 → _loads_dict + .get 链并显式判票据。
    # 非 JSON 响应（WAF 页/空 body）与 errors 数组此前直接 KeyError，被装饰器吞成「未开播」。
    json_data = _loads_dict(json_str)
    if json_data.get("errors"):
        logger.warning("Twitch GQL returned errors for PlaybackAccessToken: " + str(json_data["errors"])[:300])
        raise RuntimeError("Twitch GQL errors: see log")
    _pb_data = cast(dict[str, object], json_data.get("data") or {})
    _access = cast(dict[str, object], _pb_data.get("streamPlaybackAccessToken") or {})
    # token(value) 与 signature 是拿到 HLS master 地址的必需票据，缺一则 usher 接口返回 403/签名无效。
    token = _access.get("value")
    sign = _access.get("signature")
    if not isinstance(token, str) or not token or not isinstance(sign, str) or not sign:
        raise RuntimeError("Twitch PlaybackAccessToken missing value/signature (risk control or expired token)")

    anchor_name, live_status = await get_twitchtv_room_info(
        url=url, token=token, proxy_addr=proxy_addr, cookies=cookies
    )
    result: dict[str, object] = {"anchor_name": anchor_name, "is_live": live_status}
    if live_status:
        # 动态生成播放会话 ID，替代原硬编码的两个过期会话 ID
        play_session_id = _generate_twitch_play_session_id()
        params = {
            # acmb="e30=" 是 base64 后的空 JSON 对象（{}），为 usher 接口的约定占位参数，不要改成其它值。
            "acmb": "e30=",
            "allow_source": "true",
            "browser_family": "firefox",
            # MID-50b（2026-09-20）：browser_version 原先写死 124.0，与同一请求 UA 的
            # rv:148.0 自相矛盾（UA 与派生参数必须同源，见 AGENTS「UA 双端一字不差」条目，
            # 版本不一致是风控按指纹识别的特征之一）。现由 _TWITCH_WEB_UA 同一常量派生。
            "browser_version": _TWITCH_BROWSER_VERSION,
            "cdm": "wv",
            "fast_bread": "true",
            "os_name": "Windows",
            # MID-50b：原值写成预百分号编码的 "NT%2010.0"，再经 urlencode 二次编码成
            # NT%252010.0。编码交给 urlencode 统一处理，这里存原文。
            "os_version": "NT 10.0",
            # p="3553732" 是写死的客户端标识；play_session_id 改为每轮动态生成（原硬编码值已过期）。
            "p": "3553732",
            "platform": "web",
            "play_session_id": play_session_id,
            "player_backend": "mediaplayer",
            "player_version": "1.28.0-rc.1",
            "playlist_include_framerate": "true",
            "reassignments_supported": "true",
            # sig/token 来自上一步 GQL，拼到 query 串作为 URL 签名，缺失 usher 直接拒签。
            "sig": sign,
            "token": token,
            "transcode_mode": "cbr_v1",
        }
        # quote_via=quote：urlencode 默认 quote_plus 会把空格编成 '+'，与本接口历史线上
        # 形态（NT%2010.0）不一致；显式用 percent-encoding 保持 %20。
        access_key = urllib.parse.urlencode(params, quote_via=urllib.parse.quote)
        m3u8_url = f"https://usher.ttvnw.net/api/channel/hls/{uid}.m3u8?{access_key}"
        play_url_list = await get_play_url_list(m3u8=m3u8_url, proxy=proxy_addr, header=headers, abroad=True)
        result |= {"m3u8_url": m3u8_url, "play_url_list": play_url_list}
    return result


@trace_error_decorator
async def get_liveme_stream_url(
    url: str, proxy_addr: OptionalStr = None, cookies: OptionalStr = None
) -> dict[str, object]:
    # 获取 LiveMe 直播流地址
    # 解析链路：og:url 取 room_id → liveme.js 生成 lm-s-sign → queryinfosimple；
    # status=="0"(字符串) 取流；返回 is_live + m3u8 + flv + record_url；缺 room_id 回原 URL 继续。
    headers = {
        "origin": "https://www.liveme.com",
        "referer": "https://www.liveme.com",
        "user-agent": "ios/7.830 (ios 17.0; ; iPhone 15 (A2846/A3089/A3090/A3092))",
    }
    # 调用方透传 cookie 时优先采用；否则走游客态/自动获取凭据（各平台未登录态取流能力不一，部分更易被风控）
    if cookies:
        headers["Cookie"] = cookies

    # 分享短链/主播主页 URL 不含 index.html，需先抓页面从 og:url 还原成带 room_id 的真实直播页地址；
    # 已是 index.html 直链则直接从中抠 room_id，无需额外页面请求。
    if "index.html" not in url:
        html_str = await async_req(url, proxy_addr=proxy_addr, headers=headers, abroad=True)
        html_str = _get_str_response(html_str)
        match_url = re.search('<meta property="og:url" content="(.*?)">', html_str)
        if match_url:
            url = match_url.group(1)

    room_id = url.split("/index.html")[0].rsplit("/", maxsplit=1)[-1]
    # 2026-09-12 审查 6.3：原为同步读文件 + execjs.compile().call()（内部起 node
    # 子进程并阻塞），在 async 协程内会冻结本房间的整个事件循环；且每次调用都
    # 重复读文件 + compile。改 utils.run_js_async（to_thread + 按路径缓存编译产物）
    sign_data = cast(
        dict[str, object],
        await utils.run_js_async(f"{JS_SCRIPT_PATH}/liveme.js", "sign", room_id, f"{JS_SCRIPT_PATH}/crypto-js.min.js"),
    )
    lm_s_sign = str(sign_data.pop("lm_s_sign"))
    tongdun_black_box = sign_data.pop("tongdun_black_box")
    platform = sign_data.pop("os")
    headers["lm-s-sign"] = lm_s_sign

    params = {
        "alias": "liveme",
        "tongdun_black_box": tongdun_black_box,
        "os": platform,
    }

    api = f"https://live.liveme.com/live/queryinfosimple?{urllib.parse.urlencode(params)}"
    json_str = await async_req(api, data=sign_data, proxy_addr=proxy_addr, headers=headers, abroad=True)
    json_str = _get_str_response(json_str)
    # MID-48（2026-09-21 海外批次）：queryinfosimple 对签名失效/风控返回不含 data.video_info 的
    # 信封或 HTML，原三级索引抛错被装饰器伪装成「未开播」。改为安全下钻 + 区分性告警。
    json_data = _loads_dict(json_str)
    stream_data = cast(dict[str, object], _dig(json_data, "data", "video_info") or {})
    if _dig(stream_data, "status") is None:
        _warn_api_abnormal(json_str, "LiveMe queryinfosimple", "data.video_info.status", json_data)
        return {"anchor_name": _dig_str(stream_data, "uname"), "is_live": False}
    anchor_name = _dig_str(stream_data, "uname")
    live_status = _dig(stream_data, "status")
    result: dict[str, object] = {"anchor_name": anchor_name, "is_live": False}
    # LiveMe 用字符串 "0" 表示在播（注意是字符串而非数字），"1" 等表示离线/其它状态。
    if live_status == "0":
        m3u8_url = _dig_str(stream_data, "hlsvideosource")
        flv_url = _dig_str(stream_data, "videosource")
        if not m3u8_url and not flv_url:
            # 已判在播却两路地址皆空（改版 / 风控降级）：按无源返回并留线索
            _warn_api_abnormal(json_str, "LiveMe queryinfosimple", "data.video_info.videosource", json_data)
            return result
        result |= {"is_live": True, "m3u8_url": m3u8_url, "flv_url": flv_url, "record_url": m3u8_url or flv_url}
    return result


async def get_huajiao_sn(
    url: str, cookies: OptionalStr = None, proxy_addr: OptionalStr = None
) -> tuple[str, str, str, str] | None:
    # 获取花椒直播流 SN 参数
    headers = {
        "accept-language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
        "referer": "https://www.huajiao.com/",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:148.0) Gecko/20100101 Firefox/148.0",
    }

    # 调用方透传 cookie 时优先采用；否则走游客态/自动获取凭据（各平台未登录态取流能力不一，部分更易被风控）
    if cookies:
        headers["Cookie"] = cookies

    live_id = _safe_extract_id(url)
    api = f"https://www.huajiao.com/l/{live_id}"
    # MID-2223（2026-09-23）处置②（改判据，不删函数）：原「瞬时网络故障」判据是
    # `isinstance(e, (httpx.HTTPError, httpx.TimeoutException, OSError, asyncio.TimeoutError))`，
    # 但 async_req 已在内部吞尽传输层异常并返回 ""（见 src/async_http.py 的 async_req 尾部
    # except）——断网/DNS/超时到此处既不是异常、也不带任何状态，该判据**恒假**
    # （元组里 TimeoutException ⊂ HTTPError，第二判别项还冗余），2026-09-12 审查 6.3 那轮加固因此无效。
    # 本函数是 spider.py 唯一会 `utils.replace_url` 改写 URL_config.ini（把用户房间加 `#`
    # 注释掉、重启不恢复）的分支，判据恒假等于「断网一次即永久注释掉用户房间」。
    # 现把判据前移到**响应契约层**：空响应 = 网络/风控不确定态 → 一律不写回；
    # 只有确实取到页面而内容表明地址失效（无 feed 数据 / 字段缺失 / JSON 坏）才写回注释。
    # 不选处置①（删除函数）的原因：本函数登记在 tests/test_spider_hardening.py 的
    # OVERSEAS_MIGRATED_FUNCTIONS（MID-48 加固清单），删名须同改该文件；写回语义本身也仍有价值。
    html_str = _get_str_response(await async_req(url=api, proxy_addr=proxy_addr, headers=headers))
    if not html_str:
        logger.warning(
            i18n.tr(
                "[花椒直播]房间页返回空响应（网络失败或风控），未改动配置文件: {masked_url}",
                masked_url=utils.mask_credentials(api),
            )
        )
        raise RuntimeError(
            "Failed to retrieve live room data, the Huajiao live room address is not fixed, please use "
            "the anchor's homepage address for recording."
        )
    try:
        json_str_match = re.search("var feed = (.*?});", html_str)
        if not json_str_match:
            raise ValueError("Failed to find feed data")
        json_str = json_str_match.group(1)
        # MID-48（2026-09-21 海外批次）：`var feed = ` 命中的片段可能被风控换成 JS 壳页/截断，
        # 裸 json.loads 与三级索引抛错会走进「非瞬时异常 → 注释掉用户配置里的 URL」分支，
        # 与「确认地址失效」不可区分。先归因再抛错，保留既有写回语义（本函数是唯一写回配置的分支）。
        json_data = _loads_dict(json_str)
        sn = _dig(json_data, "feed", "sn")
        uid = _dig(json_data, "author", "uid")
        nickname = _dig(json_data, "author", "nickname")
        if sn is None or uid is None or nickname is None:
            _warn_api_abnormal(json_str, "花椒 房间页 var feed", "feed.sn + author.uid", json_data)
            raise KeyError("Missing feed/author data in huajiao page")
        live_id = _safe_extract_id(url)
        return cast(str, nickname), cast(str, sn), cast(str, uid), live_id
    except (ValueError, KeyError) as e:
        # 花椒直播间地址不固定（短链会失效），确认失效时把该 URL 在配置文件里注释掉（加 # 前缀），
        # 避免主循环反复重试无效地址；这是少数会写回配置文件的分支，副作用需留意。
        #
        # 分类按「异常来源」：请求已移出本 try，能进这里的只有上面两处**主动抛出**的
        # ValueError（页面无 feed 数据）与 KeyError（feed/author 字段缺失），即真正的
        # 「内容确认失效」；其余未预期异常走下面那条不写回的分支，避免把用户房间无端注释掉
        # （2026-09-12 审查 6.3 原用 isinstance 按异常类型分类、判据恒假，详见函数头 MID-2223）。
        logger.warning(
            i18n.tr(
                "[花椒直播]房间页确认无有效直播数据，已注释该房间: {type_name}: {e}",
                type_name=type(e).__name__,
                e=e,
            )
        )
        utils.replace_url(f"{script_path}/config/URL_config.ini", old=url, new="#" + url)
        raise RuntimeError(
            "Failed to retrieve live room data, the Huajiao live room address is not fixed, please use "
            "the anchor's homepage address for recording."
        ) from e
    except Exception as e:
        # MID-2223：兜底分支刻意**不写回**配置文件——到这里说明出现了未预期的内部错误
        # （不是「房间地址失效」的证据），宁可让主循环下轮重试，也不能改写用户配置。
        logger.warning(
            i18n.tr(
                "[花椒直播]解析异常（非内容失效，未改动配置文件）: {type_name}: {e}",
                type_name=type(e).__name__,
                e=e,
            )
        )
        raise RuntimeError(
            "Failed to retrieve live room data, the Huajiao live room address is not fixed, please use "
            "the anchor's homepage address for recording."
        ) from e


async def get_huajiao_user_info(
    url: str, cookies: OptionalStr = None, proxy_addr: OptionalStr = None
) -> OptionalStreamDict:
    # 获取花椒主播用户信息
    headers = {
        "accept-language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
        "referer": "https://www.huajiao.com/",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:148.0) Gecko/20100101 Firefox/148.0",
    }

    # 调用方透传 cookie 时优先采用；否则走游客态/自动获取凭据（各平台未登录态取流能力不一，部分更易被风控）
    if cookies:
        headers["Cookie"] = cookies

    # 花椒 user/ 主页入口：按 uid 查主播 feeds 找在播 live；否则走短链重定向兜底
    if "user" in url:
        uid = url.split("?")[0].split("user/")[1]
        params = {
            "uid": uid,
            "fmt": "json",
            "_": str(int(time.time() * 1000)),
        }

        api = f"https://webh.huajiao.com/User/getUserFeeds?{urllib.parse.urlencode(params)}"
        json_str = await async_req(url=api, proxy_addr=proxy_addr, headers=headers)
        json_str = _get_str_response(json_str)
        # MID-48（2026-09-21 海外批次）：getUserFeeds 对风控返回 HTML 时裸 json.loads 抛错，
        # 本函数无装饰器、异常会一路穿透到 get_huajiao_stream_url。改为解析不出对象时留线索，
        # 并按「未开播」返回（feeds 为空是既有静默离线形态，不得刷告警）。
        json_data = _loads_dict(json_str)
        feeds = _dig_list(json_data, "data", "feeds")
        if _dig(json_data, "data") is None:
            _warn_api_abnormal(json_str, "花椒 getUserFeeds", "data.feeds", json_data)

        html_str = await async_req(url=f"https://www.huajiao.com/user/{uid}", proxy_addr=proxy_addr, headers=headers)
        html_str = _get_str_response(html_str)
        anchor_name_match = re.search("<title>(.*?)的主页.*</title>", html_str)
        anchor_name = anchor_name_match.group(1) if anchor_name_match else ""
        first_feed = _dig(feeds, 0) if feeds else None
        if feeds and _dig(first_feed, "feed", "sn") is not None:
            feed = cast(dict[str, object], _dig(first_feed, "feed") or {})
            # OptionalStreamDict 的值域是 str|bool：这里刻意用 cast 而不是 _dig_str——
            # 花椒的 relateid/uid 可能是数字，下游只做 urlencode(str())，转成 "" 会直接取不到流。
            return {
                "anchor_name": anchor_name,
                "title": cast(str, _dig(feed, "title")),
                "is_live": True,
                "sn": cast(str, _dig(feed, "sn")),
                "liveid": cast(str, _dig(feed, "relateid")),
                "uid": uid,
            }
        else:
            return {"anchor_name": anchor_name, "is_live": False}
    return None


async def get_huajiao_stream_url_app(
    url: str, proxy_addr: OptionalStr = None, cookies: OptionalStr = None
) -> OptionalStreamDict:
    # 获取花椒 App 端直播流地址
    # errmsg 非空或 creatime 缺失即视为地址失效（返回 None，触发上层 get_huajiao_stream_url 回退主页地址）；
    # 返回的 dict 恒带 is_live=True（能取到即表示在播），sn/liveid/uid 供后续 substream 签名接口拼参。
    headers = {
        "User-Agent": "living/9.4.0 (com.huajiao.seeding; build:2410231746; iOS 17.0.0) Alamofire/9.4.0",
        "accept-language": "zh-Hans-US;q=1.0",
        "sdk_version": "1",
    }
    # 调用方透传 cookie 时优先采用；否则走游客态/自动获取凭据（各平台未登录态取流能力不一，部分更易被风控）
    if cookies:
        headers["Cookie"] = cookies
    room_id = _safe_extract_id(url)
    api = f"https://live.huajiao.com/feed/getFeedInfo?relateid={room_id}"
    json_str = await async_req(api, proxy_addr=proxy_addr, headers=headers)
    json_str = _get_str_response(json_str)
    # MID-48（2026-09-21 海外批次）：getFeedInfo 被风控换成 HTML 时裸 json.loads 抛错，与
    # 「errmsg 非空 = 地址失效」这条既有语义混在一起（后者会提示用户换主页地址）。
    # 先区分「响应整体解析不出对象」，再走原有的地址失效判定。
    json_data = _loads_dict(json_str)
    if _dig(json_data, "errmsg") is None or _dig(json_data, "data") is None:
        _warn_api_abnormal(json_str, "花椒 getFeedInfo", "errmsg + data.creatime", json_data)
        return None

    if _dig(json_data, "errmsg") or not _dig(json_data, "data", "creatime"):
        logger.error(
            "Failed to retrieve live room data, the Huajiao live room address is not fixed, please manually change "
            "the address for recording."
        )
        return None
    data = cast(dict[str, object], _dig(json_data, "data") or {})
    if _dig(data, "feed", "sn") is None or _dig(data, "author", "nickname") is None:
        # creatime 在但 feed.sn / author.nickname 缺 = 接口改版或风控降级（原实现此处 KeyError
        # 穿透到上层装饰器）；回 None 让上层按未开播重试，并留下成因线索
        _warn_api_abnormal(json_str, "花椒 getFeedInfo", "data.feed.sn + data.author.nickname", json_data)
        return None
    return {
        "anchor_name": _dig_str(data, "author", "nickname"),
        # 同 get_huajiao_user_info：用 cast 保留数字原值（下游只 urlencode），不得改成 _dig_str
        "title": cast(str, _dig(data, "feed", "title")),
        "is_live": True,
        "sn": cast(str, _dig(data, "feed", "sn")),
        "liveid": cast(str, _dig(data, "feed", "relateid")),
        "uid": cast(str, _dig(data, "author", "uid")),
    }


@trace_error_decorator
async def get_huajiao_stream_url(
    url: str, proxy_addr: OptionalStr = None, cookies: OptionalStr = None
) -> dict[str, object]:
    # 获取花椒直播流地址
    # 解析链路：user/ 主页或短链重定向 → get_huajiao_user_info / get_huajiao_stream_url_app 拿 sn；
    # 再 substream 接口取 h264_url；返回 is_live + flv + record_url；地址失效会回退主页地址。
    headers = {
        "accept-language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
        "referer": "https://www.huajiao.com/",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:148.0) Gecko/20100101 Firefox/148.0",
    }
    # 调用方透传 cookie 时优先采用；否则走游客态/自动获取凭据（各平台未登录态取流能力不一，部分更易被风控）
    if cookies:
        headers["Cookie"] = cookies

    result: dict[str, object] = {"anchor_name": "", "is_live": False}

    # 花椒两条入口：user/ 主页需 cookie 取信息，否则短链重定向解析
    if "user/" in url:
        if not cookies:
            return result
        room_data = await get_huajiao_user_info(url, cookies, proxy_addr)
    else:
        url_result = await async_req(url, proxy_addr=proxy_addr, headers=headers, redirect_url=True)
        # MID-2225（2026-09-23）：async_req(redirect_url=True) 的契约是「成功回 str(response.url)、
        # 失败回 ""」（见 src/async_http.py 的异常兜底分支），而空串同样是 str →
        # 原判据 `isinstance(url_result, str)` 恒真、else 分支**永不执行**：网络抖动后 url 被
        # 覆盖成空串，于是下面那条「落到首页 = 短链失效」的判定不成立，转而拿空 relateid
        # 去请求 substream 接口，最终把「断网」与「短链真失效」压成同一条静默未开播。
        # 现补判空串（对齐本文件已判空串的 Shopee 侧写法），并让 else 成为真正的失败回退：
        # 拿不到落地页时按「本轮无响应」返回未开播交由下轮重试，**不**再冒充首页去触发
        # 「地址不固定，请改为主页地址」那条误导提示。
        if isinstance(url_result, str) and url_result:
            url = url_result
        else:
            logger.warning(
                i18n.tr(
                    "[花椒直播]短链重定向无响应（网络失败或风控），本轮按未开播重试: {masked_url}",
                    masked_url=utils.mask_credentials(url),
                )
            )
            return result

        # 重定向落到花椒首页说明短链失效，提示换主页地址按未开播返回
        if url.rstrip("/") == "https://www.huajiao.com":
            logger.error(
                "Failed to retrieve live room data, the Huajiao live room address is not fixed, please manually change "
                "the address for recording."
            )
            return result
        room_data = await get_huajiao_stream_url_app(url, proxy_addr, cookies)

    if room_data:
        result["anchor_name"] = room_data.pop("anchor_name")
        live_status = room_data.pop("is_live")

        if live_status:
            result["title"] = room_data.pop("title")
            # MID-42 修复（2026-09-20）：原先请求 encode=h265 却消费 h264_url——请求参数与
            # 消费字段的编码器错配，两种后果都不利：① 服务端按 encode 只填匹配字段 →
            # KeyError → 装饰器伪装未开播（花椒整平台静默不可录）；② 服务端把 HEVC 地址
            # 塞进 h264_url 返回 → 地址上没有 codec=h265 标记，而 stream_select._is_h265()
            # 只认 URL 查询参数（AGENTS 硬约定）→ HEVC 被当 H.264 直接 -c copy 进容器、
            # 静默损坏产物。取「请求 h264 + 消费 h264_url」的自洽形态（改动最小，
            # 且不依赖未实测的 h265_url 字段可用性）。
            params = {"time": int(time.time() * 1000), "version": "1.0.0", **room_data, "encode": "h264"}

            api = f"https://live.huajiao.com/live/substream?{urllib.parse.urlencode(params)}"
            json_str = await async_req(url=api, proxy_addr=proxy_addr, headers=headers)
            json_str = _get_str_response(json_str)
            # MID-42 后半：json_data["data"] 深索引改为判空取值（WAF 页/截断响应回 {} 不再抛错）
            json_data = _loads_dict(json_str)
            _sub_data = json_data.get("data")
            h264_v = _sub_data.get("h264_url") if isinstance(_sub_data, dict) else None
            if isinstance(h264_v, str) and h264_v:
                result |= {
                    "is_live": True,
                    "flv_url": h264_v,
                    "record_url": h264_v,
                }
            else:
                # 语义与旧 KeyError 被装饰器吞掉后的最终表现一致（按未开播返回、下轮重试），
                # 但现在留下一条明确线索，不再与「真未开播」混淆。
                logger.warning("Huajiao substream response has no h264_url (API changed or risk control)")
    return result


@trace_error_decorator
async def get_liuxing_stream_url(
    url: str, proxy_addr: OptionalStr = None, cookies: OptionalStr = None
) -> dict[str, object]:
    # 获取流星直播流地址
    # live_stat==1 为开播（0 为未播）；flv_url 直拼固定 CDN host txpull1.5see.com/{idx}/{liveId}.flv，
    # 该平台仅单路 FLV、无 HLS 候选，故同一地址同时作 record_url。
    headers = {
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
        "Referer": "https://wap.7u66.com/198189?promoters=0",
        "User-Agent": "ios/7.830 (ios 17.0; ; iPhone 15 (A2846/A3089/A3090/A3092))",
    }
    # 调用方透传 cookie 时优先采用；否则走游客态/自动获取凭据（各平台未登录态取流能力不一，部分更易被风控）
    if cookies:
        headers["Cookie"] = cookies

    room_id = _safe_extract_id(url)
    params = {"promoters": "0", "roomidx": room_id, "currentUrl": f"https://www.7u66.com/{room_id}?promoters=0"}
    api = f"https://wap.7u66.com/api/ui/room/v1.0.0/live.ashx?{urllib.parse.urlencode(params)}"
    json_str = await async_req(url=api, proxy_addr=proxy_addr, headers=headers)
    json_str = _get_str_response(json_str)
    # MID-48（2026-09-21 海外批次）：与畅聊/音播同一套 live.ashx 接口，对不存在的 roomidx 返回
    # 不含 data.roomInfo 的信封（或经风控回 HTML）。加固口径保持一致（见 get_changliao_stream_url）。
    json_data = _loads_dict(json_str)
    room_info = cast(dict[str, object], _dig(json_data, "data", "roomInfo") or {})
    if _dig(room_info, "live_stat") is None:
        _warn_api_abnormal(json_str, "流星 live.ashx", "data.roomInfo.live_stat", json_data)
        return {"anchor_name": _dig_str(room_info, "nickname"), "is_live": False}
    anchor_name = _dig_str(room_info, "nickname")
    live_status = _dig(room_info, "live_stat")
    result: dict[str, object] = {"anchor_name": anchor_name, "is_live": False}
    if live_status == 1:
        # idx / liveId1 在真实响应里可能是数字，f-string 直接插值即可；刻意不用 _dig_str
        # （那会把 int 变成空串、拼出坏地址）。
        idx = _dig(room_info, "idx")
        live_id = _dig(room_info, "liveId1")
        if idx is None or live_id is None:
            # 已判开播却拼不出流地址（改版/风控降级）：按无源返回并留线索
            _warn_api_abnormal(json_str, "流星 live.ashx", "data.roomInfo.idx + liveId1", json_data)
            return result
        flv_url = f"https://txpull1.5see.com/live/{idx}/{live_id}.flv"
        result |= {"is_live": True, "flv_url": flv_url, "record_url": flv_url}
    return result


@trace_error_decorator
async def get_showroom_stream_data(
    url: str, proxy_addr: OptionalStr = None, cookies: OptionalStr = None
) -> dict[str, object]:
    # 获取 ShowRoom 直播流数据
    # 解析链路：/room/profile 或主页抠 room_id → live_info → live_status==2 才请求 streaming_url；
    # 返回 is_live + m3u8 + play_url_list（CDN 实测降级 http）；未开播不取流。
    headers = {
        "accept-language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:148.0) Gecko/20100101 Firefox/148.0",
    }
    # 调用方透传 cookie 时优先采用；否则走游客态/自动获取凭据（各平台未登录态取流能力不一，部分更易被风控）
    if cookies:
        headers["Cookie"] = cookies

    # ShowRoom 两条入口：profile 直链抠 room_id，否则抓主页找 profile 链接
    if "/room/profile" in url:
        room_id = url.split("room_id=")[-1]
    else:
        html_str = await async_req(url, proxy_addr=proxy_addr, headers=headers, abroad=True)
        html_str = _get_str_response(html_str)
        room_id_match = re.search('href="/room/profile\\?room_id=(.*?)"', html_str)
        if not room_id_match:
            raise ValueError("Failed to find room_id")
        room_id = room_id_match.group(1)
    info_api = f"https://www.showroom-live.com/api/live/live_info?room_id={room_id}"
    json_str = await async_req(info_api, proxy_addr=proxy_addr, headers=headers, abroad=True)
    json_str = _get_str_response(json_str)
    json_data = _loads_dict(json_str)
    # MID-48（2026-09-21）：live_info 对不存在的 room_id 返回不含 room_name/live_status 的
    # JSON（或经 CDN 回 HTML 挑战页），原两处裸 json.loads + 链式索引一律抛错 → 装饰器 →
    # 「未开播」。改为安全下钻，结构异常时留区分性告警。
    if _dig(json_data, "live_status") is None:
        _warn_api_abnormal(json_str, "ShowRoom live_info", "live_status", json_data)
        return {"anchor_name": _dig_str(json_data, "room_name"), "is_live": False}
    anchor_name = _dig_str(json_data, "room_name")
    result: dict[str, object] = {"anchor_name": anchor_name, "is_live": False}
    live_status = _dig(json_data, "live_status")
    # ShowRoom 用 live_status==2 表示开播（1 为离线/准备中），与多数平台的 1 不一致。
    if live_status == 2:
        result["is_live"] = True
        web_api = f"https://www.showroom-live.com/api/live/streaming_url?room_id={room_id}&abr_available=1"
        json_str = await async_req(web_api, proxy_addr=proxy_addr, headers=headers, abroad=True)
        json_str = _get_str_response(json_str)
        if json_str:
            json_data = _loads_dict(json_str)
            streaming_url_list = _dig_list(json_data, "streaming_url_list")
            if not streaming_url_list:
                # 已判开播却拿不到任何线路：接口改版/风控降级，与「未开播」区分开
                _warn_api_abnormal(json_str, "ShowRoom streaming_url", "streaming_url_list", json_data)
                result["is_live"] = False
                return result

            for i in streaming_url_list:
                if _dig(i, "type") == "hls_all":
                    m3u8_url = _dig_str(i, "url")
                    # MIN-2215（2026-09-23）：m3u8_url 赋值必须在 `if m3u8_url:` **之内**。
                    # 原实现先无条件写 result["m3u8_url"] = m3u8_url，而 is_live 早在
                    # live_status==2 处已置 True → 命中 hls_all 但 url 为空时返回
                    # {is_live: True, m3u8_url: ""}（既无 play_url_list 也无 record_url），
                    # 与同批「已判开播却拿不到任何线路 → 归因 + is_live=False」自相矛盾，
                    # 且空地址会进选源、每轮白烧探针。
                    if m3u8_url:
                        result["m3u8_url"] = m3u8_url
                        m3u8_url_list = await get_play_url_list(m3u8_url, proxy=proxy_addr, header=headers, abroad=True)
                        if m3u8_url_list:
                            # MID-2222（2026-09-23）：原为 `f"{m3u8_url.rsplit('/',1)[0]}/{i}"` 前缀拼接，
                            # 假定清单行全是相对路径；而 get_play_url_list 已放宽为**可返回绝对地址**
                            # （ShowRoom 的部分线路确实直接下发 https://cdn/...m3u8），
                            # 于是绝对条目被拼成 `https://host/path/https://cdn/x.m3u8` 坏候选，
                            # 多清晰度列表整体报废（画质下拉只剩一项 / 选档后校验必失败）。
                            # urljoin 对相对/绝对/带参三形态一律正确，与 SOOP 的写法一致。
                            result["play_url_list"] = [urllib.parse.urljoin(m3u8_url, i) for i in m3u8_url_list]
                        else:
                            result["play_url_list"] = [m3u8_url]
                        _play_url_list = cast(list[str], result["play_url_list"])
                        # ShowRoom CDN 实测 https 拉流不稳定，统一降级为 http（与 huya/popkontv 同思路）。
                        result["play_url_list"] = [i.replace("https://", "http://") for i in _play_url_list]
                        break
            else:
                # MIN-2215（2026-09-23）：循环走完仍未 break = 列表里没有 hls_all、或其 url 全为空。
                # 上一段告警只覆盖「streaming_url_list 整体为空」，这一形态同样属
                # 「已判开播却拿不到任何线路」，必须复用同一条归因告警并把 is_live 收回 False，
                # 否则返回 {is_live: True} 空壳、每轮白烧探针。
                _warn_api_abnormal(json_str, "ShowRoom streaming_url", "streaming_url_list", json_data)
                result["is_live"] = False
    return result


# CR-12 修复：返回三元组，失败须回 None（同 get_popkontv_stream_data）。旧装饰器回 dict，
# 调用方元组解包抛 ValueError 后再被吞，AcFun 整条链路会静默失效且日志看不到
# visitor/login 失败原因。
@trace_error_decorator_or_none
async def get_acfun_sign_params(
    proxy_addr: OptionalStr = None, cookies: OptionalStr = None
) -> tuple[object, str, object]:
    # 计算 Acfun 请求签名参数
    # 返回 (user_id, did, visitor_st) 游客三件套，是 startPlay 签名必需票据；
    # did 每次随机生成（web_ 前缀是 AcFun 游客设备标识），visitor_st 为登录接口下发的临时令牌，
    # 缺失会致 startPlay 返回 401（风控）。
    did = f"web_{utils.generate_random_string(16)}"
    # MID-2221（2026-09-23）：Cookie 头必须是**单键**。原先同一字典里并存小写 "cookie"
    # （游客 _did）与大写 "Cookie"（调用方透传）两个键，httpx 的 Headers 不做大小写去重
    # （该组已用 httpx.Client().build_request(...).headers.raw 实测请求里出现两条 Cookie 头），
    # 而 RFC 6265 §5.4 规定 UA 不得发送多个 Cookie 头、取首个还是合并由各边缘节点自决
    # → 注释承诺的「调用方透传 cookie 时优先采用」并不成立，用户配置的 acfun_cookie
    # 可能被整体丢弃，部分 WAF 还会因重复 Cookie 直接回 400。
    # 本文件其余下发小写 cookie 头处（抖音 web / tiktok / B站 h5 / get_soop_headers）都是单键，唯此处混用。
    cookie_header = f"_did={did};"
    # 调用方透传 cookie 时优先采用；否则走游客态/自动获取凭据（各平台未登录态取流能力不一，部分更易被风控）
    if cookies:
        cookie_header = f"_did={did}; {cookies}"
    headers = {
        "referer": "https://live.acfun.cn/",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:148.0) Gecko/20100101 Firefox/148.0",
        "Cookie": cookie_header,
    }
    data = {
        "sid": "acfun.api.visitor",
    }
    api = "https://id.app.acfun.cn/rest/app/visitor/login"
    json_str = await async_req(api, data=data, proxy_addr=proxy_addr, headers=headers)
    json_str = _get_str_response(json_str)
    # MID-48（2026-09-21 海外批次）：visitor/login 被风控时返回 HTML，裸 json.loads 抛错后被
    # _or_none 吞成 None，调用点只看到「拿不到签名三件套」。userId 是数字（既有测试锁定），
    # 故一律用 _dig 保留原类型；visitor_st 是票据值，**绝不写进日志**。
    json_data = _loads_dict(json_str)
    user_id = _dig(json_data, "userId")
    visitor_st = _dig(json_data, "acfun.api.visitor_st")
    if user_id is None or visitor_st is None:
        _warn_api_abnormal(json_str, "AcFun visitor/login", "userId + acfun.api.visitor_st", json_data)
        raise RuntimeError("Failed to get AcFun visitor sign params")
    return user_id, did, visitor_st


@trace_error_decorator
async def get_acfun_stream_data(
    url: str, proxy_addr: OptionalStr = None, cookies: OptionalStr = None
) -> dict[str, object]:
    # 获取 Acfun 直播流数据
    # 解析链路：userInfo 拿 nickname + liveId → get_acfun_sign_params 游客三件套 → startPlay 取 FLV；
    # 返回 is_live + play_url_list（按码率排序）+ title；liveId 缺失（"liveId" not in profile）按未开播。
    headers = {
        "referer": "https://live.acfun.cn/live/17912421",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:148.0) Gecko/20100101 Firefox/148.0",
    }
    # 调用方透传 cookie 时优先采用；否则走游客态/自动获取凭据（各平台未登录态取流能力不一，部分更易被风控）
    if cookies:
        headers["Cookie"] = cookies

    author_id = _safe_extract_id(url)
    user_info_api = f"https://live.acfun.cn/rest/pc-direct/user/userInfo?userId={author_id}"
    json_str = await async_req(user_info_api, proxy_addr=proxy_addr, headers=headers)
    json_str = _get_str_response(json_str)
    # MID-48：userInfo 被风控时返回不含 profile 的 JSON/HTML，原 `["profile"]["name"]` 抛
    # KeyError → 装饰器 → 「未开播」，与「主播未开播（profile 有但无 liveId）」不可区分。
    json_data = _loads_dict(json_str)
    profile = cast(dict[str, object], _dig(json_data, "profile") or {})
    if not profile:
        _warn_api_abnormal(json_str, "AcFun userInfo", "profile", json_data)
        return {"anchor_name": "", "is_live": False}
    anchor_name = _dig_str(profile, "name")
    # AcFun 用 profile 是否含 liveId 判定开播（有 liveId 才在播）
    status = "liveId" in profile
    result: dict[str, object] = {"anchor_name": anchor_name, "is_live": False}
    if status:
        result["is_live"] = True
        # CR-12：装饰失败返回 None，显式判空后再解包
        _sign_params = await get_acfun_sign_params(proxy_addr=proxy_addr, cookies=cookies)
        if not _sign_params:
            logger.warning("Acfun 游客签名参数获取失败，跳过本轮取流（visitor/login 未拿到三件套）")
            result["is_live"] = False
            return result
        user_id, did, visitor_st = _sign_params
        params = {
            "subBiz": "mainApp",
            "kpn": "ACFUN_APP",
            "kpf": "PC_WEB",
            "userId": user_id,
            "did": did,
            "acfun.api.visitor_st": visitor_st,
        }

        data = {
            "authorId": author_id,
            "pullStreamType": "FLV",
        }
        play_api = f"https://api.kuaishouzt.com/rest/zt/live/web/startPlay?{urllib.parse.urlencode(params)}"
        json_str = await async_req(play_api, data=data, proxy_addr=proxy_addr, headers=headers)
        json_str = _get_str_response(json_str)
        json_data = _loads_dict(json_str)
        if _dig(json_data, "data") is None:
            # startPlay 对游客凭据失效/风控回 {resultCode, message} 而无 data：
            # 此前 `["data"]["caption"]` 抛 KeyError，被装饰器伪装成「未开播」
            _warn_api_abnormal(json_str, "AcFun startPlay", "data", json_data)
            result["is_live"] = False
            return result
        live_title = _dig_str(json_data, "data", "caption")
        video_play_res = _dig(json_data, "data", "videoPlayRes")
        # videoPlayRes 是「JSON 串套在 JSON 字段里」的二重编码，内层同样可能被截断；
        # 原实现内层再用裸 json.loads 后接四级索引，任一环失败整轮录制作废。
        if not isinstance(video_play_res, str):
            _warn_api_abnormal(json_str, "AcFun startPlay", "data.videoPlayRes", json_data)
            result["is_live"] = False
            return result
        res_data = _loads_dict(video_play_res)
        # 元素须保持 dict 类型：下游按 itemgetter("bitrate") 排序、stream.py 按键取地址，
        # _dig_list 只能给出 list[object]，故在此显式收窄（原实现的 Any 隐含了同一前提）。
        play_url_list = cast(
            list[dict[str, object]], _dig_list(res_data, "liveAdaptiveManifest", 0, "adaptationSet", "representation")
        )
        if not play_url_list:
            _warn_api_abnormal(
                video_play_res,
                "AcFun startPlay(videoPlayRes)",
                "liveAdaptiveManifest[0].adaptationSet.representation",
                res_data,
            )
            result["is_live"] = False
            return result
        play_url_list = sorted(play_url_list, key=itemgetter("bitrate"), reverse=True)
        result |= {"play_url_list": play_url_list, "title": live_title}
    return result


@trace_error_decorator
async def get_changliao_stream_url(
    url: str, proxy_addr: OptionalStr = None, cookies: OptionalStr = None
) -> dict[str, object]:
    # 获取畅聊直播流地址
    # 解析链路：live.ashx 拿 nickname + live_stat → get_live_domain 从页面 config 抠 flv/hls 域名拼 liveID；
    # live_stat==1 取流；返回 is_live + m3u8 + flv + record_url；拉流域名随部署变化不写死。
    headers = {
        "User-Agent": "ios/7.830 (ios 17.0; ; iPhone 15 (A2846/A3089/A3090/A3092))",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-CN,zh;q=0.8,zh-TW;q=0.7,zh-HK;q=0.5,en-US;q=0.3,en;q=0.2",
        "Referer": "https://wap.tlclw.com/phone/15777?promoters=0",
    }
    # 调用方透传 cookie 时优先采用；否则走游客态/自动获取凭据（各平台未登录态取流能力不一，部分更易被风控）
    if cookies:
        headers["Cookie"] = cookies

    room_id = url.split("?")[0].rsplit("/", maxsplit=1)[-1]
    params = {
        "roomidx": room_id,
        "currentUrl": f"https://wap.tlclw.com/{room_id}",
    }
    play_api = f"https://wap.tlclw.com/api/ui/room/v1.0.0/live.ashx?{urllib.parse.urlencode(params)}"
    json_str = await async_req(play_api, proxy_addr=proxy_addr, headers=headers)
    json_str = _get_str_response(json_str)
    # MID-48（2026-09-21）：live.ashx 对不存在的 roomidx 返回不含 data.roomInfo 的信封
    # （或经风控返回 HTML），原 `["data"]["roomInfo"]["nickname"]` 三级索引抛 KeyError
    # → 装饰器 → 「未开播」，与「房间存在但未开播」完全一样。畅聊/音播同接口同实现。
    json_data = _loads_dict(json_str)
    room_info = cast(dict[str, object], _dig(json_data, "data", "roomInfo") or {})
    if not room_info:
        _warn_api_abnormal(json_str, "畅聊 live.ashx", "data.roomInfo", json_data)
        return {"anchor_name": "", "is_live": False}
    anchor_name = _dig_str(room_info, "nickname")
    live_status = _dig(room_info, "live_stat")

    async def get_live_domain(page_url: str) -> tuple[str, str]:
        # 拉流域名不能写死：该平台 CDN 域名随部署变化，必须从直播间页内 var config 里抠
        # domainpullstream_flv / domainpullstream_hls，再用 liveID 拼出最终地址。
        # 注意：原注释写「映客」是复制粘贴遗留，此处实际服务于畅聊，域名取自当前房间页。
        html_str = await async_req(page_url, proxy_addr=proxy_addr, headers=headers)
        html_str = _get_str_response(html_str)
        config_json_match = re.findall("var config = (.*?)config.webskins", html_str, re.DOTALL)
        if not config_json_match:
            raise ValueError("Failed to find config data")
        config_json_str = config_json_match[0].rsplit(";", maxsplit=1)[0].strip()
        # var config 命中的片段可能是 JS 对象字面量或被截断（改版），裸 json.loads 抛错
        # 会把「已确认开播」的一路取流作废；改为回空串 + 归因，由调用方按无源处理。
        config_json_data = _loads_dict(config_json_str)
        stream_flv_domain = _dig_str(config_json_data, "domainpullstream_flv")
        stream_hls_domain = _dig_str(config_json_data, "domainpullstream_hls")
        if not stream_flv_domain or not stream_hls_domain:
            _warn_api_abnormal(
                config_json_str, "畅聊 房间页 var config", "domainpullstream_flv / _hls", config_json_data
            )
        return stream_flv_domain, stream_hls_domain

    result: dict[str, object] = {"anchor_name": anchor_name, "is_live": False}
    if live_status == 1:
        flv_domain, hls_domain = await get_live_domain(url)
        if not flv_domain or not hls_domain:
            return result
        # SEV-2205 修复（2026-09-22）：原用 _dig_str 取 liveID —— 该接口族的 roomInfo 数值字段在
        # 真实响应里是**数字**（见 tests/test_spider_hardening.py 流星用例的同源记录），_dig_str 会把
        # int 变成空串，拼出 "https://<domain>/.flv" 这种只有域名的坏地址；且 liveID 缺失时同样返回 ""。
        # 两种形态下仍无条件置 is_live=True 并交出坏地址 → 两路候选校验全失败 → real_url 为空，
        # 每轮多烧请求且永远录不上。对齐孪生实现 get_liuxing_stream_url 的口径：改用 _dig + 显式判空。
        live_id = _dig(room_info, "liveID")
        if live_id is None:
            # 已判开播却拼不出流地址（改版/风控降级）：按无源返回并留线索
            _warn_api_abnormal(json_str, "畅聊 live.ashx", "data.roomInfo.liveID", json_data)
            return result
        flv_url = f"{flv_domain}/{str(live_id)}.flv"
        m3u8_url = f"{hls_domain}/{str(live_id)}.m3u8"
        result |= {"is_live": True, "m3u8_url": m3u8_url, "flv_url": flv_url, "record_url": flv_url}
    return result


@trace_error_decorator
async def get_yingke_stream_url(
    url: str, proxy_addr: OptionalStr = None, cookies: OptionalStr = None
) -> dict[str, object]:
    # 获取映客直播流地址
    # 解析链路：url 抠 uid+id → live_share_pc → status==1 取 hls_stream_addr/stream_addr；
    # 返回 is_live + m3u8 + flv + record_url；缺 uid/id 抛 ValueError 交由装饰器重试。
    headers = {
        "Referer": "https://www.inke.cn/",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:148.0) Gecko/20100101 Firefox/148.0",
    }
    # 调用方透传 cookie 时优先采用；否则走游客态/自动获取凭据（各平台未登录态取流能力不一，部分更易被风控）
    if cookies:
        headers["Cookie"] = cookies

    parsed_url = urllib.parse.urlparse(url)
    query_params = urllib.parse.parse_qs(parsed_url.query)
    uid = query_params.get("uid", [""])[0]
    live_id = query_params.get("id", [""])[0]
    if not uid or not live_id:
        raise ValueError("Failed to extract uid or live_id from inke URL")
    params = {
        "uid": uid,
        "id": live_id,
        "_t": str(int(time.time())),
    }

    api = f"https://webapi.busi.inke.cn/web/live_share_pc?{urllib.parse.urlencode(params)}"
    json_str = await async_req(api, proxy_addr=proxy_addr, headers=headers)
    json_str = _get_str_response(json_str)
    # MID-48（2026-09-21 海外批次）：live_share_pc 对失效/风控房间返回不含 data.status 的信封或
    # HTML，原 `["data"]["media_info"]["nick"]` + `["live_addr"][0]` 索引抛错被装饰器伪装成「未开播」。
    json_data = _loads_dict(json_str)
    live_data = cast(dict[str, object], _dig(json_data, "data") or {})
    if _dig(live_data, "status") is None:
        _warn_api_abnormal(json_str, "映客 live_share_pc", "data.status", json_data)
        return {"anchor_name": _dig_str(live_data, "media_info", "nick"), "is_live": False}
    anchor_name = _dig_str(live_data, "media_info", "nick")
    live_status = _dig(live_data, "status")

    result: dict[str, object] = {"anchor_name": anchor_name, "is_live": False}
    if live_status == 1:
        first_addr = _dig(live_data, "live_addr", 0)
        m3u8_url = _dig_str(first_addr, "hls_stream_addr")
        flv_url = _dig_str(first_addr, "stream_addr")
        if not m3u8_url or not flv_url:
            # 已判开播但地址列表为空/字段改名：与「未开播」区分，按无源返回
            _warn_api_abnormal(json_str, "映客 live_share_pc", "data.live_addr[0].hls_stream_addr", json_data)
            return result
        result |= {"is_live": True, "m3u8_url": m3u8_url, "flv_url": flv_url, "record_url": m3u8_url}
    return result


@trace_error_decorator
async def get_yinbo_stream_url(
    url: str, proxy_addr: OptionalStr = None, cookies: OptionalStr = None
) -> dict[str, object]:
    # 获取音播直播流地址
    # 解析链路：live.ashx 拿 nickname + live_stat → get_live_domain 抠域名拼 liveID；
    # live_stat==1 取流；返回 is_live + m3u8 + flv + record_url；拉流域名不写死（随部署变化）。
    headers = {
        "User-Agent": "ios/7.830 (ios 17.0; ; iPhone 15 (A2846/A3089/A3090/A3092))",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-CN,zh;q=0.8,zh-TW;q=0.7,zh-HK;q=0.5,en-US;q=0.3,en;q=0.2",
        "Referer": "https://live.ybw1666.com/800005143?promoters=0",
    }
    # 调用方透传 cookie 时优先采用；否则走游客态/自动获取凭据（各平台未登录态取流能力不一，部分更易被风控）
    if cookies:
        headers["Cookie"] = cookies

    room_id = url.split("?")[0].rsplit("/", maxsplit=1)[-1]
    params = {
        "roomidx": room_id,
        "currentUrl": f"https://wap.ybw1666.com/{room_id}",
    }
    play_api = f"https://wap.ybw1666.com/api/ui/room/v1.0.0/live.ashx?{urllib.parse.urlencode(params)}"
    json_str = await async_req(play_api, proxy_addr=proxy_addr, headers=headers)
    json_str = _get_str_response(json_str)
    # MID-48：与畅聊同一套 live.ashx / var config 实现，加固口径也保持一致
    # （详见 get_changliao_stream_url 内 MID-48 注释）。
    json_data = _loads_dict(json_str)
    room_data = cast(dict[str, object], _dig(json_data, "data", "roomInfo") or {})
    if not room_data:
        _warn_api_abnormal(json_str, "音播 live.ashx", "data.roomInfo", json_data)
        return {"anchor_name": "", "is_live": False}
    anchor_name = _dig_str(room_data, "nickname")
    live_status = _dig(room_data, "live_stat")

    async def get_live_domain(page_url: str) -> tuple[str, str]:
        # 拉流域名不能写死：从当前房间页内 var config 抠出 flv/hls 拉流域名再拼 liveID。
        # 原注释「知乎」为复制粘贴遗留，此处服务于音播（ybw1666.com）。
        html_str = await async_req(page_url, proxy_addr=proxy_addr, headers=headers)
        html_str = _get_str_response(html_str)
        config_json_match = re.findall("var config = (.*?)config.webskins", html_str, re.DOTALL)
        if not config_json_match:
            raise ValueError("Failed to find config data")
        config_json_str = config_json_match[0].rsplit(";", maxsplit=1)[0].strip()
        config_json_data = _loads_dict(config_json_str)
        stream_flv_domain = _dig_str(config_json_data, "domainpullstream_flv")
        stream_hls_domain = _dig_str(config_json_data, "domainpullstream_hls")
        if not stream_flv_domain or not stream_hls_domain:
            _warn_api_abnormal(
                config_json_str, "音播 房间页 var config", "domainpullstream_flv / _hls", config_json_data
            )
        return stream_flv_domain, stream_hls_domain

    result: dict[str, object] = {"anchor_name": anchor_name, "is_live": False}
    if live_status == 1:
        flv_domain, hls_domain = await get_live_domain(url)
        if not flv_domain or not hls_domain:
            return result
        # SEV-2205 修复（2026-09-22）：与畅聊逐字同形的问题与修法——见 get_changliao_stream_url
        # 内同编号注释（_dig_str 把 int liveID 变空串 / 缺失时仍置 is_live=True 交出坏地址）。
        live_id = _dig(room_data, "liveID")
        if live_id is None:
            _warn_api_abnormal(json_str, "音播 live.ashx", "data.roomInfo.liveID", json_data)
            return result
        flv_url = f"{flv_domain}/{str(live_id)}.flv"
        m3u8_url = f"{hls_domain}/{str(live_id)}.m3u8"
        result |= {"is_live": True, "m3u8_url": m3u8_url, "flv_url": flv_url, "record_url": flv_url}
    return result


@trace_error_decorator
async def get_zhihu_stream_url(
    url: str, proxy_addr: OptionalStr = None, cookies: OptionalStr = None
) -> dict[str, object]:
    # 获取知乎直播流地址
    # 解析链路：people/<id> 主页 profile 拿 theater_url → 直播页 js-initialData 抠 playInfo；
    # status==1 取流；返回 is_live + m3u8 + flv + record_url；无在映剧场直接回未开播。
    headers = {
        "accept-language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:148.0) Gecko/20100101 Firefox/148.0",
    }
    # 调用方透传 cookie 时优先采用；否则走游客态/自动获取凭据（各平台未登录态取流能力不一，部分更易被风控）
    if cookies:
        headers["Cookie"] = cookies

    # 知乎主播主页（people/<id>）不直接是直播间：先查 profile 拿到 living_theater 的 theater_url，
    # 再跳到该直播页解析；若没有在映剧场说明未开播，提前返回避免无谓的页面请求。
    if "people/" in url:
        # MID-2224（2026-09-23）：原为裸 `url.split("people/")[1]`，既不剥 query 也不剥子路径。
        # 知乎分享链普遍带 ?ivt=...，另有 /people/<id>/activities 形态 → 抠出的 user_id 变成
        # "xxx?ivt=abc" / "xxx/activities"，拼出 query 落在 path 之前的坏接口
        # （https://api.zhihu.com/people/xxx?ivt=abc/profile?...），接口必回错误；而下方归因
        # 会说成「缺 drama.living_theater」，把排障方向带偏成「接口改版」。
        # 本文件其余取 id 处一律先 split("?")[0] 或走 _safe_extract_id，此处对齐。
        user_id = url.split("?")[0].split("people/")[1].split("/")[0]
        if not user_id:
            # 取不到主播 id 时显式抛错（与同文件其它「URL 形态不合预期」处一致），
            # 不能拿空串去拼 /people//profile —— 那会请求到一个与目标无关的接口路径。
            raise ValueError("Failed to find zhihu user id")
        api = f"https://api.zhihu.com/people/{user_id}/profile?profile_new_version="
        json_str = await async_req(api, proxy_addr=proxy_addr, headers=headers)
        json_str = _get_str_response(json_str)
        # MID-48：profile 接口被风控时返回 HTML/空 body，裸 json.loads 抛 JSONDecodeError；
        # 原 drama/living_theater 已用 .get 但前一步仍会崩。解析不出对象时归因后按未开播返回。
        json_data = _loads_dict(json_str)
        if not json_data:
            _warn_api_abnormal(json_str, "知乎 people/profile", "drama.living_theater.theater_url", json_data)
            return {"anchor_name": "", "is_live": False}
        drama = _dig(json_data, "drama") or {}
        living_theater = _dig(drama, "living_theater") or {}
        # 无在映剧场即未开播，提前返回避免无谓的直播页请求
        theater_url = _dig_str(living_theater, "theater_url")
        if not theater_url:
            return {"anchor_name": "", "is_live": False}
        live_page_url = theater_url
    else:
        live_page_url = url

    web_id = live_page_url.split("?")[0].rsplit("/", maxsplit=1)[-1]
    html_str = await async_req(live_page_url, proxy_addr=proxy_addr, headers=headers)
    html_str = _get_str_response(html_str)
    json_str2_match = re.findall('<script id="js-initialData" type="text/json">(.*?)</script>', html_str)
    if not json_str2_match:
        raise ValueError("Failed to find initialData")
    json_str2 = json_str2_match[0]
    # MID-48：js-initialData 命中但内容被截断/改版时，裸 json.loads 与随后
    # ["initialState"]["theater"]["theaters"][web_id] 的四级索引（最后一级是动态键）都会抛错，
    # 被装饰器伪装成「未开播」。theaters 以 web_id 为键 → 房间不存在即键缺失，
    # 与接口改版此前完全无法分辨。
    json_data2 = _loads_dict(json_str2)
    live_data = _dig(json_data2, "initialState", "theater", "theaters", web_id)
    if not isinstance(live_data, dict):
        _warn_api_abnormal(json_str2, "知乎 js-initialData", f"initialState.theater.theaters[{web_id}]", json_data2)
        return {"anchor_name": "", "is_live": False}
    anchor_name = _dig_str(live_data, "actor", "name")
    live_status = _dig(live_data, "drama", "status")
    result: dict[str, object] = {"anchor_name": anchor_name, "is_live": False}
    if live_status == 1:
        live_title = _dig_str(live_data, "theme")
        play_url = _dig(live_data, "drama", "playInfo")
        hls_url = _dig_str(play_url, "hlsUrl")
        if not hls_url:
            # status 已报在播却无 hlsUrl：字段改名/风控降级，不是「未开播」
            _warn_api_abnormal(json_str2, "知乎 js-initialData", "drama.playInfo.hlsUrl", json_data2)
            return result
        result |= {
            "is_live": True,
            "title": live_title,
            "m3u8_url": hls_url,
            "flv_url": _dig_str(play_url, "playUrl"),
            "record_url": hls_url,
        }
    return result


@trace_error_decorator
async def get_chzzk_stream_data(
    url: str, proxy_addr: OptionalStr = None, cookies: OptionalStr = None
) -> dict[str, object]:
    # 获取 CHZZK 直播流数据
    # live_status=="OPEN" 字符串表示开播（非数字 1）；play_data 由 livePlaybackJson 解析、
    # media[0].path 为 master m3u8，再经 get_play_url_list 拆出多清晰度候选。
    headers = {
        "accept": "application/json, text/plain, */*",
        "accept-language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
        "origin": "https://chzzk.naver.com",
        "referer": "https://chzzk.naver.com/live/458f6ec20b034f49e0fc6d03921646d2",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:148.0) Gecko/20100101 Firefox/148.0",
    }
    # 调用方透传 cookie 时优先采用；否则走游客态/自动获取凭据（各平台未登录态取流能力不一，部分更易被风控）
    if cookies:
        headers["Cookie"] = cookies

    room_id = url.split("?")[0].rsplit("/", maxsplit=1)[-1]
    play_api = f"https://api.chzzk.naver.com/service/v3/channels/{room_id}/live-detail"
    json_str = await async_req(play_api, proxy_addr=proxy_addr, headers=headers, abroad=True)
    json_str = _get_str_response(json_str)
    # MID-48（2026-09-21）：live-detail 对不存在频道返回不含 content 的信封（Naver CDN 也可能
    # 回 HTML），原 `json_data["content"]["channel"]["channelName"]` 抛 KeyError → 装饰器 →
    # 「未开播」，与「频道存在但未开播（status!=OPEN）」完全同形。
    json_data = _loads_dict(json_str)
    live_data = cast(dict[str, object], _dig(json_data, "content") or {})
    if not live_data:
        _warn_api_abnormal(json_str, "CHZZK live-detail", "content", json_data)
        return {"anchor_name": "", "is_live": False}
    anchor_name = _dig_str(live_data, "channel", "channelName")
    live_status = _dig(live_data, "status")

    result: dict[str, object] = {"anchor_name": anchor_name, "is_live": False}
    # CHZZK 用字符串 "OPEN" 表示开播（非数字 1）
    if live_status == "OPEN":
        # livePlaybackJson 又是「JSON 串套在 JSON 字段里」的二重编码，内层同样可能截断
        raw_playback = _dig_str(live_data, "livePlaybackJson")
        if not raw_playback:
            _warn_api_abnormal(json_str, "CHZZK live-detail", "content.livePlaybackJson", json_data)
            return result
        play_data = _loads_dict(raw_playback)
        m3u8_url = _dig_str(play_data, "media", 0, "path")
        if not m3u8_url:
            _warn_api_abnormal(raw_playback, "CHZZK livePlaybackJson", "media[0].path", play_data)
            return result
        m3u8_url_list = await get_play_url_list(m3u8_url, proxy=proxy_addr, header=headers, abroad=True)
        # MID-2222（2026-09-23）：同 ShowRoom——清单行可能是绝对地址，前缀拼接会产出
        # `https://host/path/https://cdn/x.m3u8` 坏候选。原先连 query 一起当目录前缀
        # （`split("?")[0]` 只用于去签名），改用 urljoin 后三形态一律正确。
        prefix = m3u8_url.split("?")[0].rsplit("/", maxsplit=1)[0]
        m3u8_url_list = [urllib.parse.urljoin(prefix + "/", i) for i in m3u8_url_list]
        result |= {"is_live": True, "m3u8_url": m3u8_url, "play_url_list": m3u8_url_list}
    return result


# CR-12 修复（本仓「注释插在装饰器与 def 之间」事故的原点）：Python 允许 @decorator 与 def 之间
# 夹注释行，且装饰器仍绑到紧随其后的那个 def——原先正是如此，兜底装饰器绑到了本同步函数
# （返回 str，与「异常回 {"is_live": False}」的契约冲突），而它下方看起来被装饰的
# get_haixiu_stream_url 反而裸奔，异常会穿透到 main.py 计入 host 熔断样本、存在房间地址被自动
# 注释掉的风险。本函数体已自带 try/except，无需装饰器；说明性注释一律写在装饰器**上方**。
# 读取嗨秀/嗨嗨接口 accessToken 的外部覆盖值：优先环境变量，其次 config.ini 的 [Cookie] 段。
# 背景：内置 token 为「双重 URL 编码」的长期凭据，已随公开仓库分发；提供覆盖入口，
# 使平台轮换或凭据失效时无需改代码即可替换（正式换发仍需维护者更新内置缺省值）。
def _read_haixiu_token_override(is_haixiu: bool) -> str:
    env_key = "HAIXIU_ACCESS_TOKEN" if is_haixiu else "HAIHAI_ACCESS_TOKEN"
    cfg_key = "haixiu_access_token" if is_haixiu else "haihai_access_token"
    override = os.environ.get(env_key, "").strip()
    if override:
        return override
    try:
        # F-16：`read_ini_value`（按文件路径读取、不写回），勿与 config_io 的
        # `read_config_value(parser, section, option, default)` 混淆
        cfg_value = utils.read_ini_value(f"{script_path}/config/config.ini", "Cookie", cfg_key)
    except Exception:
        return ""
    return (cfg_value or "").strip()


# CR-12 修复：兜底装饰器回归到平台入口本身（原错配到了上方的 _read_haixiu_token_override）
@trace_error_decorator
async def get_haixiu_stream_url(
    url: str, proxy_addr: OptionalStr = None, cookies: OptionalStr = None
) -> dict[str, object]:
    # 获取嗨秀直播流地址（含签名）
    headers = {
        "origin": "https://www.haixiutv.com",
        "referer": "https://www.haixiutv.com/",
        "user-agent": "ios/7.830 (ios 17.0; ; iPhone 15 (A2846/A3089/A3090/A3092))",
    }
    # 调用方透传 cookie 时优先采用；否则走游客态/自动获取凭据（各平台未登录态取流能力不一，部分更易被风控）
    if cookies:
        headers["Cookie"] = cookies

    room_id = url.split("?")[0].rsplit("/", maxsplit=1)[-1]
    # accessToken 是两段写死的「双重 URL 编码」凭据（嗨秀/嗨嗨两套域名各一个，按域名选择），
    # 发请求前经 params 组装处 unquote 两次还原；该 token 长期有效、与账号无关，是接口鉴权的关键，
    # 改动会导致 401。lehaitv 走另一域名与 origin。
    # 先取外部覆盖（env / config.ini），未配置时才回退内置值以保持既有行为不变。
    _is_haixiu = "haixiutv" in url
    access_token = _read_haixiu_token_override(_is_haixiu)
    if not access_token:
        if _is_haixiu:
            access_token = "pLXSC%252FXJ0asc1I21tVL5FYZhNJn2Zg6d7m94umCnpgL%252BuVm31GQvyw%253D%253D"
        else:
            access_token = "s7FUbTJ%252BjILrR7kicJUg8qr025ZVjd07DAnUQd8c7g%252Fo4OH9pdSX6w%253D%253D"

    params = {"accessToken": access_token, "tku": "3000006", "c": "10138100100000", "_st1": int(time.time() * 1000)}
    # 用 haixiu.js 对参数做签名得到 _ajaxData1（前端 crypto-js 逻辑迁移到 node 执行）。
    # 2026-09-12 审查 6.3：同 LiveMe，改 utils.run_js_async（to_thread + 编译缓存）
    ajax_data = cast(
        str,
        await utils.run_js_async(f"{JS_SCRIPT_PATH}/haixiu.js", "sign", params, f"{JS_SCRIPT_PATH}/crypto-js.min.js"),
    )

    params["accessToken"] = urllib.parse.unquote(urllib.parse.unquote(access_token))
    params["_ajaxData1"] = ajax_data
    params["_"] = int(time.time() * 1000)

    if "haixiutv" in url:
        api = f"https://service.haixiutv.com/v2/room/{room_id}/media/advanceInfoRoom?{urllib.parse.urlencode(params)}"
    else:
        headers["origin"] = "https://www.lehaitv.com"
        headers["referer"] = "https://www.lehaitv.com"
        api = f"https://service.lehaitv.com/v2/room/{room_id}/media/advanceInfoRoom?{urllib.parse.urlencode(params)}"

    json_str = await async_req(api, proxy_addr=proxy_addr, headers=headers, abroad=True)
    json_str = _get_str_response(json_str)
    # MID-48（2026-09-21 海外批次）：advanceInfoRoom 对签名过期/风控返回不含 data 的信封或 HTML，
    # 原 `["data"]["nickname"]` 链式索引抛错被装饰器伪装成「未开播」。注意 accessToken/_ajaxData1
    # 是凭据，本函数任何日志都不得带出它们的值。
    json_data = _loads_dict(json_str)
    stream_data = cast(dict[str, object], _dig(json_data, "data") or {})
    if _dig(stream_data, "live_status") is None:
        _warn_api_abnormal(json_str, "嗨秀 advanceInfoRoom", "data.live_status", json_data)
        return {"anchor_name": _dig_str(stream_data, "nickname"), "is_live": False}
    anchor_name = _dig_str(stream_data, "nickname")
    live_status = _dig(stream_data, "live_status")
    result: dict[str, object] = {"anchor_name": anchor_name, "is_live": False}
    # 嗨秀 live_status==1 为开播
    if live_status == 1:
        flv_url = _dig_str(stream_data, "media_url_web")
        if not flv_url:
            _warn_api_abnormal(json_str, "嗨秀 advanceInfoRoom", "data.media_url_web", json_data)
            return result
        result |= {"is_live": True, "flv_url": flv_url, "record_url": flv_url}
    return result


@trace_error_decorator
async def get_vvxqiu_stream_url(
    url: str, proxy_addr: OptionalStr = None, cookies: OptionalStr = None
) -> dict[str, object]:
    # 获取 VV 星球直播流地址
    # 解析链路：get_params 拿 roomId → 两处接口补昵称 → 固定 CDN 模板 m3u8 探测；
    # 响应非空且不含 Not Found 才判开播；返回 is_live + m3u8 + record_url；无 roomId 不探测。
    headers = {
        "User-Agent": "ios/7.830 (ios 17.0; ; iPhone 15 (A2846/A3089/A3090/A3092))",
        "Access-Control-Request-Method": "GET",
        "Origin": "https://h5webcdn-pro.vvxqiu.com",
        "Referer": "https://h5webcdn-pro.vvxqiu.com/",
    }

    # 调用方透传 cookie 时优先采用；否则走游客态/自动获取凭据（各平台未登录态取流能力不一，部分更易被风控）
    if cookies:
        headers["Cookie"] = cookies

    room_id = get_params(url, "roomId")
    api_1 = f"https://h5p.vvxqiu.com/activity-center/fanclub/activity/captain/banner?roomId={room_id}&product=vvstar"
    json_str = await async_req(api_1, proxy_addr=proxy_addr, headers=headers)
    json_str = _get_str_response(json_str)
    # MID-48：banner 接口对游客可能不含 data（而非「无昵称」），原 `["data"]["anchorName"]`
    # 抛 KeyError 会让整轮取流作废（含后面的 m3u8 探测）；这里降级为「昵称留空、继续探测」，
    # 只在响应整体解析不出对象时留线索——取流判定本就不依赖昵称。
    json_data = _loads_dict(json_str)
    if _dig(json_data, "data") is None:
        _warn_api_abnormal(json_str, "VV星球 captain/banner", "data.anchorName", json_data)
    anchor_name = _dig_str(json_data, "data", "anchorName")
    # 第一个 banner 接口对匿名/未登录用户可能不返回昵称，用第二个活动 banner 接口兜底补 memberName；
    # 仍取不到则留空（不影响取流判定，仅标题/昵称缺失）。
    if not anchor_name:
        params = {
            "sessionId": "",
            "userId": "",
            "product": "vvstar",
            "tickToken": "",
            "roomId": room_id,
        }
        json_str = await async_req(
            f"https://h5p.vvxqiu.com/activity-center/halloween2023/banner?{urllib.parse.urlencode(params)}",
            proxy_addr=proxy_addr,
            headers=headers,
        )
        json_str = _get_str_response(json_str)
        json_data = _loads_dict(json_str)
        anchor_name = _dig_str(json_data, "data", "memberVO", "memberName")

    result: dict[str, object] = {"anchor_name": anchor_name, "is_live": False}
    # 房间号缺失时不再探测 m3u8（拼不出有效地址，请求必然无意义）
    if not room_id:
        return result
    # 地址是固定 CDN 模板：1400442770 写死前缀 + room_id + room_id[2:] 后缀（取除前两位外的部分），
    # 整条地址由平台约定拼接，缺失/错拼任何一段都只会拿到 "Not Found"。
    m3u8_url = f"https://liveplay-pro.wasaixiu.com/live/1400442770_{room_id}_{room_id[2:]}_single.m3u8"
    resp = await async_req(m3u8_url, proxy_addr=proxy_addr, headers=headers)
    resp = _get_str_response(resp)
    # 空响应也判未直播：此前空串不含 "Not Found" 会误判为开播，故需同时判非空且不含 Not Found。
    if resp and "Not Found" not in resp:
        result |= {"is_live": True, "m3u8_url": m3u8_url, "record_url": m3u8_url}
    return result


@trace_error_decorator
async def get_17live_stream_url(
    url: str, proxy_addr: OptionalStr = None, cookies: OptionalStr = None
) -> dict[str, object]:
    # 获取 17Live 直播流地址
    # status==2 为开播（1 为离线），flv 取自 rtmpURLs[0].urlHighQuality；
    # 未取到 status 或 status!=2 时回 is_live=False（默认），不抛错、交由主循环下轮重试。
    headers = {
        "origin": "https://17.live",
        "referer": "https://17.live/",
        "user-agent": "ios/7.830 (ios 17.0; ; iPhone 15 (A2846/A3089/A3090/A3092))",
    }

    # 调用方透传 cookie 时优先采用；否则走游客态/自动获取凭据（各平台未登录态取流能力不一，部分更易被风控）
    if cookies:
        headers["Cookie"] = cookies

    room_id = url.split("?")[0].rsplit("/", maxsplit=1)[-1]
    api_1 = f"https://wap-api.17app.co/api/v1/user/room/{room_id}"
    json_str = await async_req(api_1, proxy_addr=proxy_addr, headers=headers)
    json_str = _get_str_response(json_str)
    # MID-48：user/room 接口对不存在的主页返回不含 displayName 的信封/HTML，
    # 原 `json_data["displayName"]` 抛 KeyError → 装饰器 → 连后面的 alive 接口都不再请求。
    # 昵称缺失不影响开播判定（由 alive 接口给），故降级为留空继续。
    json_data = _loads_dict(json_str)
    if _dig(json_data, "displayName") is None:
        _warn_api_abnormal(json_str, "17Live user/room", "displayName", json_data)
    anchor_name = _dig_str(json_data, "displayName")
    result: dict[str, object] = {"anchor_name": anchor_name, "is_live": False}
    # 第一个 user/room 接口只给主播名，需再请求 viewers/alive 接口、用 room_id 作为 liveStreamID
    # 换取开播状态与拉流地址；该平台把开播判定与取流分两步，缺一不可。
    # 注意：alive 的请求体与上一个接口的响应都叫 json_data，改名 request_payload 以免
    # 与 _loads_dict 的 dict[str, object] 推断冲突（mypy 会因 dict[str, str] 不变性报错）。
    request_payload: dict[str, str] = {
        "liveStreamID": room_id,
    }
    api_1 = f"https://wap-api.17app.co/api/v1/lives/{room_id}/viewers/alive"
    json_str = await async_req(api_1, json_data=request_payload, proxy_addr=proxy_addr, headers=headers)
    json_str = _get_str_response(json_str)
    json_data = _loads_dict(json_str)
    live_status = _dig(json_data, "status")
    # 17Live status==2 为开播（1 为离线）
    if live_status and live_status == 2:
        flv_url = _dig_str(json_data, "pullURLsInfo", "rtmpURLs", 0, "urlHighQuality")
        if not flv_url:
            # 已报在播却无拉流地址：风控降级/字段改名，不是「未开播」
            _warn_api_abnormal(json_str, "17Live viewers/alive", "pullURLsInfo.rtmpURLs[0].urlHighQuality", json_data)
            return result
        result |= {"is_live": True, "flv_url": flv_url, "record_url": flv_url}
    return result


@trace_error_decorator
async def get_langlive_stream_url(
    url: str, proxy_addr: OptionalStr = None, cookies: OptionalStr = None
) -> dict[str, object]:
    # 获取浪 Live 直播流地址
    # live_status==1 为开播；flv_url 与 m3u8_url 同源（liveurl/liveurl_hls），该平台 HLS 可用，
    # 故 m3u8 也作为 record_url 候选交给上层按可达性校验，而非只用 FLV。
    headers = {
        "origin": "https://www.lang.live",
        "referer": "https://www.lang.live/",
        "user-agent": "ios/7.830 (ios 17.0; ; iPhone 15 (A2846/A3089/A3090/A3092))",
    }

    # 调用方透传 cookie 时优先采用；否则走游客态/自动获取凭据（各平台未登录态取流能力不一，部分更易被风控）
    if cookies:
        headers["Cookie"] = cookies

    room_id = url.split("?")[0].rsplit("/", maxsplit=1)[-1]
    api_1 = f"https://api.lang.live/langweb/v1/room/liveinfo?room_id={room_id}"
    json_str = await async_req(api_1, proxy_addr=proxy_addr, headers=headers, abroad=True)
    json_str = _get_str_response(json_str)
    # MID-48（2026-09-21 海外批次）：liveinfo 对不存在房间返回不含 data.live_info 的信封（或 HTML），
    # 原三级索引抛错被装饰器伪装成「未开播」。
    json_data = _loads_dict(json_str)
    live_info = cast(dict[str, object], _dig(json_data, "data", "live_info") or {})
    if _dig(live_info, "live_status") is None:
        _warn_api_abnormal(json_str, "浪Live room/liveinfo", "data.live_info.live_status", json_data)
        return {"anchor_name": _dig_str(live_info, "nickname"), "is_live": False}
    anchor_name = _dig_str(live_info, "nickname")
    live_status = _dig(live_info, "live_status")
    result: dict[str, object] = {"anchor_name": anchor_name, "is_live": False}
    # 浪 Live live_status==1 为开播
    if live_status == 1:
        flv_url = _dig_str(live_info, "liveurl")
        m3u8_url = _dig_str(live_info, "liveurl_hls")
        if not flv_url or not m3u8_url:
            # 已判开播却拿不到两路地址（改版/风控降级）：按无源返回并留线索
            _warn_api_abnormal(json_str, "浪Live room/liveinfo", "data.live_info.liveurl", json_data)
            return result
        result |= {"is_live": True, "m3u8_url": m3u8_url, "flv_url": flv_url, "record_url": m3u8_url}
    return result


@trace_error_decorator
async def get_pplive_stream_url(
    url: str, proxy_addr: OptionalStr = None, cookies: OptionalStr = None
) -> dict[str, object]:
    # 获取飘飘直播流地址
    # living 字段为真即在播；pullUrl 同时作 m3u8 与 record_url（单路 HLS）；
    # catshow 子域走独立 api 域名（api.catshow168.com）并切换 Origin/Referer，否则用默认 pp 域名。
    headers = {
        "Content-Type": "application/json",
        "Origin": "https://m.pp.weimipopo.com",
        "Referer": "https://m.pp.weimipopo.com/",
        "User-Agent": "ios/7.830 (ios 17.0; ; iPhone 15 (A2846/A3089/A3090/A3092))",
    }

    # 调用方透传 cookie 时优先采用；否则走游客态/自动获取凭据（各平台未登录态取流能力不一，部分更易被风控）
    if cookies:
        headers["Cookie"] = cookies

    room_id = get_params(url, "anchorUid")
    req_body = {
        "inviteUuid": "",
        "anchorUuid": room_id,
    }

    # catshow 子域走独立 api 域名并切换 Origin/Referer，否则用默认 pp 域名
    if "catshow" in url:
        api = "https://api.catshow168.com/live/preview"
        headers["Origin"] = "https://h.catshow168.com"
        headers["Referer"] = "https://h.catshow168.com"
    else:
        api = "https://api.pp.weimipopo.com/live/preview"
    json_str = await async_req(api, json_data=req_body, proxy_addr=proxy_addr, headers=headers)
    json_str = _get_str_response(json_str)
    # MID-48（2026-09-21 海外批次）：live/preview 对不存在的 anchorUuid 返回不含 data 的信封（或
    # 风控 HTML），原 `["data"]["name"]` 链式索引抛错被装饰器伪装成「未开播」。
    json_data = _loads_dict(json_str)
    live_info = cast(dict[str, object], _dig(json_data, "data") or {})
    if _dig(live_info, "living") is None:
        _warn_api_abnormal(json_str, "飘飘 live/preview", "data.living", json_data)
        return {"anchor_name": _dig_str(live_info, "name"), "is_live": False}
    anchor_name = _dig_str(live_info, "name")
    live_status = _dig(live_info, "living")
    result: dict[str, object] = {"anchor_name": anchor_name, "is_live": False}
    # 飘飘 living 字段为真即在播
    if live_status:
        m3u8_url = _dig_str(live_info, "pullUrl")
        if not m3u8_url:
            # 已判在播却无 pullUrl（改版/风控降级）：按无源返回并留线索
            _warn_api_abnormal(json_str, "飘飘 live/preview", "data.pullUrl", json_data)
            return result
        result |= {"is_live": True, "m3u8_url": m3u8_url, "record_url": m3u8_url}
    return result


@trace_error_decorator
async def get_6room_stream_url(
    url: str, proxy_addr: OptionalStr = None, cookies: OptionalStr = None
) -> dict[str, object]:
    # 获取六间房直播流地址
    # 解析链路：v.6.cn 抠 rid → coop/mobile inroom → flvtitle 非空取流；
    # 返回 is_live + flv + record_url；无 rid 抛 ValueError，由装饰器按未开播重试。
    headers = {
        "accept-language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
        "referer": "https://ios.6.cn/?ver=8.0.3&build=4",
        "user-agent": "ios/7.830 (ios 17.0; ; iPhone 15 (A2846/A3089/A3090/A3092))",
    }

    # 调用方透传 cookie 时优先采用；否则走游客态/自动获取凭据（各平台未登录态取流能力不一，部分更易被风控）
    if cookies:
        headers["Cookie"] = cookies

    room_id = _safe_extract_id(url)
    html_str = await async_req(f"https://v.6.cn/{room_id}", proxy_addr=proxy_addr, headers=headers)
    html_str = _get_str_response(html_str)
    room_id_match = re.search("rid: '(.*?)',\n\\s+roomid", html_str)
    # 页面 rid 缺失即结构变化，显式报错交由装饰器按未开播重试
    if not room_id_match:
        raise ValueError("Failed to find room_id")
    room_id = room_id_match.group(1)
    data = {
        "av": "3.1",
        "encpass": "",
        "logiuid": "",
        "project": "v6iphone",
        "rate": "1",
        "rid": "",
        "ruid": room_id,
    }
    api = "https://v.6.cn/coop/mobile/index.php?padapi=coop-mobile-inroom.php"
    json_str = await async_req(api, data=data, proxy_addr=proxy_addr, headers=headers)
    json_str = _get_str_response(json_str)
    # MID-48（2026-09-21 海外批次）：inroom 接口对加密房间/风控返回不含 content.liveinfo 的响应
    # （或 HTML），原三级索引抛错被装饰器伪装成「未开播」，与「房间存在但未开播」（flvtitle 为空）
    # 混成一条。后者保持既有静默语义。
    json_data = _loads_dict(json_str)
    liveinfo = cast(dict[str, object], _dig(json_data, "content", "liveinfo") or {})
    if _dig(liveinfo, "flvtitle") is None:
        _warn_api_abnormal(json_str, "六间房 coop-mobile-inroom", "content.liveinfo.flvtitle", json_data)
        return {"anchor_name": _dig_str(json_data, "content", "roominfo", "alias"), "is_live": False}
    flv_title = _dig_str(liveinfo, "flvtitle")
    anchor_name = _dig_str(json_data, "content", "roominfo", "alias")
    result: dict[str, object] = {"anchor_name": anchor_name, "is_live": False}
    # flvtitle 非空才是有效在播房间，否则判未直播
    if flv_title:
        flv_url = f"https://wlive.6rooms.com/httpflv/{flv_title}.flv"
        result |= {"is_live": True, "flv_url": flv_url, "record_url": flv_url}
    return result


@trace_error_decorator
async def get_shopee_stream_url(
    url: str, proxy_addr: OptionalStr = None, cookies: OptionalStr = None
) -> dict[str, object]:
    # 获取 Shopee 直播流地址
    # 解析链路：重定向/uid 定 host_suffix → ongoing_live 或 session 接口拿 play_url；
    # status==1 且链接判定在播才取流；返回 is_live + flv + record_url；畸形 URL 直接回未开播。
    headers = {
        "accept": "application/json, text/plain, */*",
        "accept-language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
        "referer": "https://live.shopee.sg/share?from=live&session=802458&share_user_id=",
        "user-agent": "ios/7.830 (ios 17.0; ; iPhone 15 (A2846/A3089/A3090/A3092))",
    }

    # 调用方透传 cookie 时优先采用；否则走游客态/自动获取凭据（各平台未登录态取流能力不一，部分更易被风控）
    if cookies:
        headers["Cookie"] = cookies

    result: dict[str, object] = {"anchor_name": "", "is_live": False}
    is_living = False

    # 非直链且非店铺主页：先解析重定向拿到真实 host/会话
    # S-1（2026-09-29，镜像同文件小红书 SEV-2214 的两道闸 + 剥凭据口径）：落地页由**响应**决定，
    # 而下方三处请求都复用含 Cookie 的 headers，故跳转结果必须过两道闸才允许替换 url：
    #   ① 落地页 host 必须落在 Shopee 域族白名单内（_shopee_is_allowed_host，含 userinfo 拒绝）；
    #   ② 落地页不得解析到内网/回环/云元数据/CGNAT/缩写 IP（复用仓内既有判定
    #      web_config._host_internal_reason，不自造——它已覆盖 inet_aton 缩写 IP、
    #      metadata 域名等绕过形态）。
    # 任一条不满足即丢弃跳转结果、保留原始用户填写的 url（原请求是用户自己填的合法短链宿主，
    # 不会把凭据送往响应指定的目标），并置 landing_untrusted 让后续请求一律剥离 Cookie。
    landing_untrusted = False
    if "live.shopee" not in url and "uid" not in url:
        url_result = await async_req(url, proxy_addr=proxy_addr, headers=headers, redirect_url=True, abroad=True)
        # 重定向失败（空响应）时保留原 URL 继续解析，避免后续 split 越界
        if isinstance(url_result, str) and url_result:
            _landing = url_result
            if _shopee_is_allowed_host(_landing):
                try:
                    # DNS 判定；web_config._host_internal_reason 解析失败（NXDOMAIN）也返回拒绝理由。
                    _landing_host = (urllib.parse.urlparse(_landing).hostname or "").lower()
                    _internal_reason = (
                        web_config._host_internal_reason(_landing_host) if _landing_host else "缺少主机名"
                    )
                except Exception as e:
                    _internal_reason = f"内网判定异常: {type(e).__name__}"
                if _internal_reason is None:
                    url = _landing
                else:
                    landing_untrusted = True
                    logger.warning(
                        i18n.tr(
                            "Shopee 短链落地页不可信，已忽略跳转: {url} ({reason})",
                            url=utils.mask_credentials(_landing),
                            reason=_internal_reason,
                        )
                    )
            else:
                landing_untrusted = True
                logger.warning(
                    i18n.tr(
                        "Shopee 短链跳转到非白名单主机，已忽略跳转: {url}",
                        url=utils.mask_credentials(_landing),
                    )
                )

    if landing_untrusted:
        # 凭据外送防线第二层：跳转被判不可信后，本轮所有后续请求（含按原 url 拼出的 api_host）
        # 都不再携带调用方 Cookie。不可信判定说明「响应会把请求引向攻击者指定的主机」这一事实
        # 已经成立，不能因为「丢弃了这次跳转」就当作凭据安全。
        headers.pop("Cookie", None)

    # 畸形 URL（无 host）：判未直播早退，避免后续 split 越界抛 IndexError
    if "://" not in url or len(url.split("/")) < 3 or not url.split("/")[2]:
        return result

    # 直链用完整 TLD 后缀定位 host；含 uid 的是店铺主页（未必在播）。
    # MI-16 修复：两分支原先后缀算法不一致（live.shopee 分支只取最后一段，
    # 对 live.shopee.co.id 得到 "id" → 无效域名），同一站点两种链接表现互反而极难归因；
    # 现统一走 _shopee_host_suffix 一个实现（其算法沿革见该函数注释）。
    host_suffix = _shopee_host_suffix(url)
    if "live.shopee" in url:
        # 含 uid 的是店铺主页分享链接（未必在播），不含 uid 的 live.shopee 直链（仅带 session）才视为在播态。
        is_living = get_params(url, "uid") is None

    uid = get_params(url, "uid")
    api_host = f"https://live.shopee.{host_suffix}"
    # S-1 的第三道闸（也是最后一道）：校验对象是**构造结果**而不是输入。前两道闸只看落地页输入，
    # 而 host_suffix 是从 host 上切下来的任意片段——它被投毒成 "evil.com" 时，拼出的
    # api_host=https://live.shopee.evil.com 是 evil.com 的子域（攻击者握有 DNS），
    # 前两闸按字面看着像官方域、放行照样外发凭据。放在**任何带凭据请求发出之前**，
    # 不过即按未开播早退并告警；不回退到其它 host——Shopee 只有 live.shopee.<官方站点后缀>
    # 一个接口宿主，拼不出合法宿主就说明这条链接本身不可路由。
    if not _shopee_is_allowed_host(api_host):
        logger.warning(
            i18n.tr(
                "Shopee 接口域名不在白名单内，本轮按未开播返回: {host}",
                host=utils.mask_credentials(api_host),
            )
        )
        return result
    session_id = get_params(url, "session")
    if uid:
        # uid/session 取自 URL 查询串或接口响应，直接拼进请求行会让 "a&b=x" 这类值变成**新增查询参数**
        # （参数走私）；按仓内既有做法（urllib.parse.urlencode/quote）做 percent 编码后再拼。
        json_str = await async_req(
            f"{api_host}/api/v1/shop_page/live/ongoing?uid={urllib.parse.quote(uid, safe='')}",
            proxy_addr=proxy_addr,
            headers=headers,
            abroad=True,
        )
        json_str = _get_str_response(json_str)
        # MID-48（2026-09-21）：三个 shopee 接口都会在校验失败时返回不含 data 的信封
        # （或经 CDN 回 HTML），原 `json_data["data"]["..."]` 抛 KeyError → 装饰器 → 「未开播」，
        # 用户侧与「店铺没开播」完全同形。改为逐级判空 + 区分性告警。
        json_data = _loads_dict(json_str)
        if _dig(json_data, "data") is None:
            _warn_api_abnormal(json_str, "Shopee shop_page/live/ongoing", "data", json_data)
            return result
        # 店铺有在进行直播才取 session，否则查回放列表兜底
        if _dig(json_data, "data", "ongoing_live"):
            session_id = _dig_str(json_data, "data", "ongoing_live", "session_id")
            if not session_id:
                _warn_api_abnormal(json_str, "Shopee shop_page/live/ongoing", "data.ongoing_live.session_id", json_data)
                return result
            is_living = True
        else:
            json_str = await async_req(
                f"{api_host}/api/v1/shop_page/live/replay_list?offset=0&limit=1&uid={urllib.parse.quote(uid, safe='')}",
                proxy_addr=proxy_addr,
                headers=headers,
                abroad=True,
            )
            json_str = _get_str_response(json_str)
            json_data = _loads_dict(json_str)
            if _dig(json_data, "data") is None:
                _warn_api_abnormal(json_str, "Shopee replay_list", "data.replay", json_data)
                return result
            # 仅回放无在播：补主播名后按未直播返回
            replays = _dig_list(json_data, "data", "replay")
            if replays:
                result["anchor_name"] = _dig_str(replays[0], "nick_name")
                return result

    # MIN-2211（2026-09-23）：走到这里仍没有 session_id，说明链接既无 ?session= 参数、
    # 也没走 uid→ongoing_live 分支拿到会话。原实现照发 /api/v1/session/None：白发一次请求，
    # 然后每轮（默认 120 秒）输出一条 **ERROR** 叫用户「更换房间地址」——可地址没问题，
    # 只是没开播，正踩 AGENTS「未开播属正常轮次、刻意保持静默，否则真线索会被淹掉」的口径。
    if not session_id:
        logger.debug(i18n.tr("Shopee 房间链接未带 session 且无进行中的直播，本轮按未开播返回"))
        return result

    # session_id 落在**路径段**上（不是查询串），同样须做 percent 编码：未编码时
    # "../x"、"?a=b"、"#frag" 这类值能改写请求的行与查询串（S-1 同批收口，仓内既有做法同上）。
    json_str = await async_req(
        f"{api_host}/api/v1/session/{urllib.parse.quote(session_id, safe='')}",
        proxy_addr=proxy_addr,
        headers=headers,
        abroad=True,
    )
    json_str = _get_str_response(json_str)
    json_data = _loads_dict(json_str)
    # session 接口无 data 即拉取失败，提示换地址按未开播返回
    if not json_data.get("data"):
        if not json_data:
            _warn_api_abnormal(json_str, "Shopee session", "data.session", json_data)
        else:
            # 只有「确实拉到了会话信封、但里面没有 data」才是地址失效级别的错误；
            # 空响应/风控 HTML 已在上一分支留过区分性告警，不再重复刷 ERROR（MIN-2211）。
            logger.error(
                "Fetch shopee live data failed, please update the address of the live broadcast room and try again."
            )
        return result
    if _dig(json_data, "data", "session") is None:
        # data 在但 session 不在：接口改版/风控降级，与「data 缺失」的拉取失败不同因
        _warn_api_abnormal(json_str, "Shopee session", "data.session", json_data)
        return result
    session = _dig(json_data, "data", "session")
    # session 里的 uid 与 URL 上的 uid 同名但来源不同；换个局部名以免 mypy 把
    # `str | None`（get_params 的返回类型）与 object 混赋，且下游只用到这一次。
    session_uid = _dig(session, "uid")
    anchor_name = _dig_str(session, "nickname")
    live_status = _dig(session, "status")
    result["anchor_name"] = anchor_name
    result["uid"] = f"uid={session_uid}&session={session_id}"
    # 必须「接口报 status==1 且 链接判定为在播(is_living)」同时满足才取流：is_living 只在
    # 无 uid 的 live.shopee 直链、或 uid→ongoing_live 确实查到在播时才为真，避免把店铺主页的离线回放误判为直播。
    if live_status == 1 and is_living:
        flv_url = _dig_str(session, "play_url")
        if not flv_url:
            _warn_api_abnormal(json_str, "Shopee session", "data.session.play_url", json_data)
            return result
        title = _dig_str(session, "title")
        result |= {"is_live": True, "title": title, "flv_url": flv_url, "record_url": flv_url}
    return result


@trace_error_decorator
async def get_youtube_stream_url(
    url: str, proxy_addr: OptionalStr = None, cookies: OptionalStr = None
) -> dict[str, object]:
    # 获取 YouTube 直播流地址
    # 解析链路：页面 ytInitialPlayerResponse 抠 videoDetails；无 videoDetails（未登录）回未开播；
    # isLive 真取 hlsManifestUrl；返回 is_live + m3u8 + play_url_list；需配置 cookie 才能取流。
    headers = {
        "accept-language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:148.0) Gecko/20100101 Firefox/148.0",
    }

    # 调用方透传 cookie 时优先采用；否则走游客态/自动获取凭据（各平台未登录态取流能力不一，部分更易被风控）
    if cookies:
        headers["Cookie"] = cookies

    html_str = await async_req(url, proxy_addr=proxy_addr, headers=headers, abroad=True)
    html_str = _get_str_response(html_str)
    json_str_match = re.search("var ytInitialPlayerResponse = (.*?);var meta = document\\.createElement", html_str)
    # ytInitialPlayerResponse 缺失即登录态/页面结构异常，显式报错
    if not json_str_match:
        raise ValueError("Failed to find ytInitialPlayerResponse")
    json_str = json_str_match.group(1)
    # MID-48（2026-09-21 海外批次）：ytInitialPlayerResponse 命中的片段被截断/换成风控壳页时，
    # 裸 json.loads 抛错与「未登录无 videoDetails」（既有 error 提示 + 未开播）混成一条。
    json_data = _loads_dict(json_str)
    result: dict[str, object] = {"anchor_name": "", "is_live": False}
    video_details = _dig(json_data, "videoDetails")
    # 无 videoDetails 说明未登录/无播放数据，提示配置 cookie 按未开播返回
    if video_details is None:
        if not json_data:
            # 内联片段解析不出对象 = 风控壳页/截断，与「未登录」区分开（后者保留既有那条 error 提示）
            _warn_api_abnormal(json_str, "YouTube ytInitialPlayerResponse", "videoDetails", json_data)
        logger.error("Error: Please log in to YouTube on your device's webpage and configure cookies in the config.ini")
        return result
    result["anchor_name"] = _dig_str(video_details, "author")
    live_status = _dig(video_details, "isLive")
    # isLive 为真才取 HLS 清单
    if live_status:
        live_title = _dig_str(video_details, "title")
        m3u8_url = _dig_str(json_data, "streamingData", "hlsManifestUrl")
        if not m3u8_url:
            # 已判在播却无清单地址（改版/风控降级）：按无源返回并留线索
            _warn_api_abnormal(json_str, "YouTube ytInitialPlayerResponse", "streamingData.hlsManifestUrl", json_data)
            return result
        play_url_list = await get_play_url_list(m3u8_url, proxy=proxy_addr, header=headers, abroad=True)
        result |= {"is_live": True, "title": live_title, "m3u8_url": m3u8_url, "play_url_list": play_url_list}
    return result


# SEV-N04 修复（2026-09-21，CODE_REVIEW_2026-09-21）：淘宝 mtop 的两张 H5 签名票据键。
# 只有这两键允许被响应下发的 Set-Cookie 覆盖，用户 cookie 的其余部分（unb / _tb_token_ /
# cookie2 等登录态）必须原样保留——见 get_taobao_stream_url 的合并分支。
_TAOBAO_TICKET_KEYS = ("_m_h5_tk", "_m_h5_tk_enc")


def _cookie_str_to_dict(cookie_str: str) -> dict[str, str]:
    # Cookie 头串 → dict，即 utils.dict_to_cookie_str 的逆向。
    # 为什么写在本模块而不是 utils：仓内此前只有正向函数（grep 全仓确认无 cookie_str→dict 实现），
    # 且目前只被淘宝票据合并这一条链路需要。
    # 边界：只在「;」处分段，段内按**首个**「=」切分——base64 / URL 编码的 cookie 值常含「=」
    # （_m_h5_tk 形如 <32位hex>_<13位毫秒>，部分站点的值带 padding），再切会把值截断成空串。
    # 无「=」的残段（末尾多余分号、用户手工截断配置）直接丢弃：解析不出来的内容不该被写回配置文件。
    parsed: dict[str, str] = {}
    for segment in cookie_str.split(";"):
        name, sep, value = segment.strip().partition("=")
        if sep and name:
            parsed[name] = value.strip()
    return parsed


@trace_error_decorator
async def get_taobao_stream_url(
    url: str, proxy_addr: OptionalStr = None, cookies: OptionalStr = None
) -> dict[str, object]:
    # 获取淘宝直播流地址
    # 解析链路：get_params 拿 liveId（或重定向解 id）→ mtop 两轮 _m_h5_tk 签名 → livedetail；
    # streamStatus=="1" 取 liveUrlList（按画质排序）；返回 is_live + play_url_list；挤爆提示需换 cookie。
    headers = {
        "Referer": "https://huodong.m.taobao.com/",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:148.0) Gecko/20100101 Firefox/148.0",
        "Cookie": "",
    }

    # 调用方透传 cookie 时优先采用；否则走游客态/自动获取凭据（各平台未登录态取流能力不一，部分更易被风控）
    if cookies:
        headers["Cookie"] = cookies

    live_id = get_params(url, "liveId")
    # URL 无 liveId：先抓页面找重定向解 id
    if not live_id:
        html_str = await async_req(url, proxy_addr=proxy_addr, headers=headers)
        html_str = _get_str_response(html_str)
        redirect_url_match = re.findall("var url = '(.*?)';", html_str)
        if not redirect_url_match:
            raise ValueError("Failed to find redirect_url")
        redirect_url = redirect_url_match[0]
        live_id = get_params(redirect_url, "id")

    # 重定向后仍解不出 liveId：显式报错
    if not live_id:
        raise ValueError("Failed to find live_id")

    params = {
        "jsv": "2.7.0",
        "appKey": "12574478",
        "t": "1733104933120",
        "sign": "",
        "AntiFlood": "true",
        "AntiCreep": "true",
        "api": "mtop.mediaplatform.live.livedetail",
        "v": "4.0",
        "preventFallback": "true",
        "type": "jsonp",
        "dataType": "jsonp",
        "callback": "mtopjsonp1",
        "data": '{"liveId":"' + live_id + '","creatorId":null}',
    }

    # 淘宝 mtop 接口需要 _m_h5_tk 签名：首次请求不带该 cookie 时，响应会下发新的 _m_h5_tk/_m_h5_tk_enc，
    # 第二轮用其算 MD5 签名（pre_sign_str = token&t&appKey&data）再请求；两轮都拿不到 SUCCESS 即放弃。
    for _ in range(2):
        t13 = int(time.time() * 1000)
        params["t"] = str(t13)

        # 带 _m_h5_tk 时才做 MD5 签名；否则首轮裸请求换回新 token
        if "_m_h5_tk" in headers.get("Cookie", ""):
            app_key = "12574478"
            cookie_str = headers.get("Cookie", "")
            # MID-2220（2026-09-23）：原用 `re.findall("_m_h5_tk=(.*?);", cookie_str)` 提取票据，
            # 依赖**尾随分隔符**；而写回用的 utils.dict_to_cookie_str 是 `"; ".join(...)`、不追加
            # 尾随 `;`，浏览器复制的 cookie 也常把该键放在末位 → `in` 判真、findall 却命中 0，
            # sign 保持空值 → mtop 必拒；合并回写后仍是末位，于是**两轮都签不上**，收尾的
            # `_m_h5_tk not in Cookie` 又为真 → 连 cookie 过期提示都不出的静默未开播。
            # 现统一走 _cookie_str_to_dict（只在「;」分段、段内按首个「=」切，值里的 `=` 与末位
            # 无分隔符都不受影响）；取不到票据即视为无票据，落回既有「裸请求换票」分支。
            _m_h5_tk = _cookie_str_to_dict(cookie_str).get("_m_h5_tk", "")
            if _m_h5_tk:
                pre_sign_str = f'{_m_h5_tk.split("_")[0]}&{t13}&{app_key}&' + params["data"]
                sign = hashlib.md5(pre_sign_str.encode("utf-8")).hexdigest()
                params["sign"] = sign
        api = f"https://h5api.m.taobao.com/h5/mtop.mediaplatform.live.livedetail/4.0/?{urllib.parse.urlencode(params)}"
        result_tuple = await async_req(
            url=api, proxy_addr=proxy_addr, headers=headers, timeout=20, return_cookies=True, include_cookies=True
        )
        # return_cookies 返回 (jsonp, cookie) 元组，需拆出 cookie 用于下一轮签名
        if isinstance(result_tuple, tuple) and len(result_tuple) == 2:
            jsonp_str, new_cookie = result_tuple
        else:
            jsonp_str = str(result_tuple) if result_tuple else ""
            new_cookie = {}
        try:
            json_data = utils.jsonp_to_json(jsonp_str)
        except Exception as e:
            # WD-18：jsonp_to_json 在响应不是 JSONP（风控页/HTML 错误页/被截断）时直接 raise，
            # 会把整个「换 token 再试一轮」的补救循环一起掀掉——第二轮根本不会发生。
            # 这里降级为「本轮无数据」，让循环按既有语义继续。
            logger.warning(i18n.tr("淘宝响应不是合法 JSONP，本轮重试: {type_name}", type_name=type(e).__name__))
            json_data = {}

        # WD-18 修复：把「应用刷新到的票据」提到 ret 判定**之外**无条件执行。原实现把
        # headers["Cookie"] = new_cookie_str 放在与 isinstance(ret_value, list) 配对的 else 分支里，
        # 而 mtop 在 token 缺失/过期时返回的仍是**非空 ret 数组**（如 ["FAIL_SYS_TOKEN_EMPTY::令牌为空"]），
        # 那个 else 永远走不到 → 刷新到的票据被丢弃、第二轮 Cookie 与首轮完全相同且 sign 仍为空，
        # 必然复现首轮失败：cookie 未自带有效 _m_h5_tk 时淘宝 100% 取流失败，且失败被静默降级成
        # 「未开播」、用户看不到任何 token 过期提示。
        # [历史注] 2026-09-21 SEV-N04 证伪了本节旧表述「应用刷新到的 cookie」：
        # async_req(return_cookies=True) 返回的只是响应的 Set-Cookie（src/async_http.py 的
        # response.cookies，不含请求侧 cookie），整体应用会连带抹掉用户登录态——故意图保留、
        # 作用范围收窄到下面两张票据键。
        if new_cookie and "_m_h5_tk" in new_cookie:
            # SEV-N04 修复（2026-09-21，CODE_REVIEW_2026-09-21）：**合并**而非替换。
            # 旧实现 `headers["Cookie"] = utils.dict_to_cookie_str(new_cookie)` 把整条 Cookie 头
            # 换成「只剩响应票据」的串，并在下一行把这一份持久化写回 config.ini 的
            # [Cookie] taobao_cookie——用户配置的登录态（unb / _tb_token_ / cookie2 等）在任意一次
            # token 轮换后被静默销毁且重启也回不来，需登录的淘宝房间此后恒为游客态失败。
            # 响应里除两张票据外的 Set-Cookie 一律不入请求头也不入配置（服务端可控，
            # 不该被持久化成用户凭据）。
            merged_cookie = _cookie_str_to_dict(headers.get("Cookie", ""))
            for _ticket_key in _TAOBAO_TICKET_KEYS:
                if _ticket_key in new_cookie:
                    merged_cookie[_ticket_key] = new_cookie[_ticket_key]
            new_cookie_str = utils.dict_to_cookie_str(merged_cookie)
            headers["Cookie"] = new_cookie_str
            # WD-16：回写会话票据，避免每轮都重新走登录式刷新。两处收紧：
            # ① 持 main.file_update_lock（与主循环热加载读/其它写入方互斥，防半写）；
            # ② 仅在值确实变化时才写，减少无谓的整份 config.ini 重写与备份触发。
            # [2026-09-21 SEV-N04 修订] ② 的旧实现拿「响应票据串」与「配置里的完整 cookie」比较，
            # 两者形态必然不同 → 条件恒真、每轮都重写整份 config.ini 并触发备份线程，
            # 「仅在值确实变化时才写」实际从未生效。现比较的是**合并后的完整串**。
            try:
                import main as _main

                _cfg_path = f"{script_path}/config/config.ini"
                _old_cookie = utils.read_ini_value(_cfg_path, "Cookie", "taobao_cookie")
                if _old_cookie != new_cookie_str:
                    with _main.file_update_lock:
                        utils.update_config(_cfg_path, "Cookie", "taobao_cookie", new_cookie_str)
                    # SEV-N04：成功回写须可观测（旧实现只在 except 里留一条 debug，
                    # 「用户 cookie 被改动」在常规日志级别下完全不可见，与 MID-37
                    # 「敏感项不得被静默覆盖」的口径冲突）。只落节名/键名，**值一律不落日志**
                    # （cookie 即凭据，logs/ 会轮转保留多份）；update_config 自身的失败路径
                    # 已各自 warning，故走到这里即写入已完成。
                    logger.info(
                        i18n.tr(
                            "The value of {key} under [{section}] in the configuration file has been updated.",
                            key="taobao_cookie",
                            section="Cookie",
                        )
                    )
            except (ImportError, OSError) as e:
                logger.debug(i18n.tr("淘宝 cookie 回写配置失败（已忽略）: {type_name}", type_name=type(e).__name__))

        # ret 字段存在才进入解析；否则走循环重试换 token
        if json_data and "ret" in json_data:
            ret_value = json_data["ret"]
            # ret 为字符串数组，首元素含状态码文案（如被挤爆/SUCCESS）
            if isinstance(ret_value, list) and len(ret_value) > 0:
                # 淘宝高并发/风控会返回「被挤爆」提示，是 cookie 失效或会话被限流的明确信号，
                # 必须换有效 cookie 才能继续，否则后续请求依旧拿不到 SUCCESS。
                if "哎哟喂,被挤爆啦,请稍后重试" in str(ret_value[0]):
                    raise RuntimeError(f"Please change your taobao cookie: {ret_value}")

                ret_msg = ret_value
                # MIN-2214（2026-09-23）：两处收口。
                # ① 状态比较原为 `ret_msg == ["SUCCESS::调用成功"]` 全等——淘宝把该文案改成
                #    任何后缀（历史上 mtop 的 :: 后文案随版本变过）就会整体判成「非 SUCCESS」，
                #    表现为持续的「拿不到流」且日志无痕；改判前缀即可。
                # ② `json_data["data"]` 是本文件 MID-48 口径的最后一处裸链式索引：SUCCESS
                #    信封偶发不带 data（网关降级）时抛 KeyError，被装饰器吞成「未开播」。
                if str(ret_msg[0]).startswith("SUCCESS"):
                    live_status_obj = _dig(json_data, "data")
                    if not isinstance(live_status_obj, dict):
                        # 已判 SUCCESS 却拿不到 data 对象：接口改版/网关降级，留线索后按未开播
                        # 返回。此处不能返回下方才构造的 result（该分支尚未执行到），故显式构造
                        # 与函数收尾一致的未开播契约。
                        _warn_api_abnormal(jsonp_str, "淘宝 mtop livedetail", "data", json_data)
                        return {"anchor_name": "", "is_live": False}
                    live_status_data = cast(dict[str, object], live_status_obj)
                    # MID-43 修复（2026-09-20）：mtop livedetail 的 data.broadCaster 是**对象**
                    # （accountName/nick/headPic…），原实现 `cast(str, ...["broadCaster"])` 只
                    # 能压掉 mypy 的 no-any-return，运行时仍是 dict → main.py 的
                    # clean_name(dict).strip() 抛 AttributeError；且 record_success(record_host)
                    # 在 clean_name **之前**已上报，熔断统计把这轮故障记成成功样本。
                    # 现取具体字符串字段，非 str 结果回退 ""（宁可主播名为空也不产出错类型）。
                    broadcaster = live_status_data.get("broadCaster")
                    if isinstance(broadcaster, dict):
                        bc_name = broadcaster.get("accountName") or broadcaster.get("nick")
                        anchor_name = bc_name if isinstance(bc_name, str) else ""
                    else:
                        anchor_name = broadcaster if isinstance(broadcaster, str) else ""
                    result: dict[str, object] = {"anchor_name": anchor_name, "is_live": False}
                    live_status = live_status_data.get("streamStatus")

                    def get_sort_key(item: dict[str, object]) -> int:
                        # 按画质优先级给清晰度排序（lld<ld<md<hd<ud），取最高可用清晰度放首位；
                        # 原注释误写为「京东」，此处实际服务于淘宝 liveUrlList。
                        definition_priority = {"lld": 0, "ld": 1, "md": 2, "hd": 3, "ud": 4}
                        def_value = item.get("definition") or item.get("newDefinition")
                        priority = definition_priority.get(str(def_value), -1)
                        return int(priority)

                    # 淘宝 streamStatus=="1" 为开播
                    if live_status == "1":
                        live_title = live_status_data.get("title")
                        play_url_list = cast(list[dict[str, object]], live_status_data.get("liveUrlList", []))
                        play_url_list = sorted(play_url_list, key=get_sort_key, reverse=True)
                        result |= {
                            "is_live": True,
                            "title": live_title,
                            "play_url_list": play_url_list,
                            "live_id": live_id,
                        }

                    # 仅在成功分支返回 result；否则落入循环重试（ret 非空但非 SUCCESS）
                    return result
            else:
                # ret 存在但不是非空数组（空数组/非列表）：本轮无有效结果，交由循环重试。
                # 原实现在这里做「刷新失败即抛错」，但 token 过期时 ret 恰恰是非空数组、
                # 根本走不到该分支（见上方 WD-18 说明）；刷新失败的判定已移到循环外的收尾处。
                logger.debug("淘宝 mtop 返回的 ret 为空/非数组，本轮无结果")
    # 如果循环结束还没有返回，返回默认结果
    # WD-18：两轮耗尽仍未拿到 SUCCESS。区分两种语义——
    #   ① cookie 里始终没有可用 _m_h5_tk（登录式刷新也没成功）：这是**需要用户干预**的
    #      确定性错误，必须抛出提示更新 cookie，而不是与「主播未开播」混为同一个静默结果；
    #   ② 已拿到 token 但仍非 SUCCESS：多为瞬时风控/限流，按未开播返回交由下轮重试。
    # MID-2220（2026-09-23）：判定改用解析后的**键集合**而非子串包含——`_m_h5_tk` 是
    # `_m_h5_tk_enc` 的子串，只带 enc 键的 cookie 会被子串判据误认为「已有票据」，
    # 于是这条本应抛给用户的「请更新 cookie」提示恰好在该形态下不出（与签名侧同源）。
    if "_m_h5_tk" not in _cookie_str_to_dict(headers.get("Cookie", "")):
        raise RuntimeError("Try to update cookie failed, please update the cookies in the configuration file")
    return {"anchor_name": "", "is_live": False}


@trace_error_decorator
async def get_jd_stream_url(url: str, proxy_addr: OptionalStr = None, cookies: OptionalStr = None) -> dict[str, object]:
    # 获取京东直播流数据：先解析跳转/主播页定位 liveId，再经 api.m.jd.com 取播放地址（flv/hls）
    # 返回 is_live + m3u8 + flv + record_url + title；status==1 才取流，标题仅在 author_id 路径补取；
    # 跳转/主播页解析失败时回未开播，不抛错（装饰器按未开播空转重试）。
    headers = {
        "User-Agent": "ios/7.830 (ios 17.0; ; iPhone 15 (A2846/A3089/A3090/A3092))",
        "origin": "https://lives.jd.com",
        "referer": "https://lives.jd.com/",
        "x-referer-page": "https://lives.jd.com/",
    }

    # 调用方透传 cookie 时优先采用；否则走游客态/自动获取凭据（各平台未登录态取流能力不一，部分更易被风控）
    if cookies:
        headers["Cookie"] = cookies

    redirect_url_result = await async_req(url, proxy_addr=proxy_addr, headers=headers, redirect_url=True)
    # MID-2225（2026-09-23）：原注释写「重定向返回字符串才采用，否则保留原 URL 继续解析」，
    # 与代码相反——async_req(redirect_url=True) 失败时回的是**空串**，空串同样是 str，
    # 于是 else（保留原 URL）永不执行，原 URL 被空串覆盖 → 后续 authorId / `#/<id>?origin`
    # 两处正则必然失配 → 静默按未开播返回，用户填的主播页地址根本没被解析过。
    # 现补判空串，让 else 成为注释所述的真实回退。
    if isinstance(redirect_url_result, str) and redirect_url_result:
        redirect_url = redirect_url_result
    else:
        redirect_url = url

    # 京东入口有两种形态：带 authorId 的是主播主页（需查 talent 接口拿主播名并跳转到直播间 id）；
    # 不带的是直播间直链（从 #/<liveId>?origin 抠 id）。两条路径最终都归一到 liveId 取播放地址。
    author_id = get_params(redirect_url, "authorId")
    result: dict[str, object] = {"anchor_name": "", "is_live": False}
    live_id_str: str = ""
    # 无 authorId 即直播间直链：从 #/<liveId> 抠 id；否则走主播主页接口
    if not author_id:
        live_id_match = re.search("#/(.*?)\\?origin", redirect_url)
        if not live_id_match:
            return result
        live_id_str = live_id_match.group(1)
        result["anchor_name"] = f"jd_{live_id_str}"
    else:
        data = {
            "functionId": "talent_head_findTalentMsg",
            "appid": "dr_detail",
            "body": '{"authorId":"' + author_id + '","monitorSource":"1","userId":""}',
        }
        info_api = "https://api.m.jd.com/talent_head_findTalentMsg"
        json_str = await async_req(info_api, data=data, proxy_addr=proxy_addr, headers=headers)
        json_str = _get_str_response(json_str)
        # MID-48：京东 mtop 风格接口对风控/参数失效返回不含 result 的信封，原
        # `json_data["result"]["talentName"]` 与后面 `["livingRoomJump"]["params"]["id"]`
        # 任一环抛错都被装饰器伪装成「未开播」。
        json_data = _loads_dict(json_str)
        jd_result = cast(dict[str, object], _dig(json_data, "result") or {})
        if not jd_result:
            _warn_api_abnormal(json_str, "京东 talent_head_findTalentMsg", "result", json_data)
            return result
        anchor_name = _dig_str(jd_result, "talentName")
        result["anchor_name"] = anchor_name
        # 主播页无在播跳转信息：未开播，直接回未开播
        if "livingRoomJump" not in jd_result:
            return result
        live_id_str = _dig_str(jd_result, "livingRoomJump", "params", "id")
        if not live_id_str:
            # livingRoomJump 在、params.id 不在：字段改名（原实现此处 KeyError）
            _warn_api_abnormal(json_str, "京东 talent_head_findTalentMsg", "result.livingRoomJump.params.id", json_data)
            return result
    params = {"body": '{"liveId": "' + live_id_str + '"}', "functionId": "getImmediatePlayToM", "appid": "h5-live"}

    api = f"https://api.m.jd.com/client.action?{urllib.parse.urlencode(params)}"
    # backup_api: https://api.m.jd.com/api
    json_str = await async_req(api, proxy_addr=proxy_addr, headers=headers)
    json_str = _get_str_response(json_str)
    json_data = _loads_dict(json_str)
    if _dig(json_data, "data") is None:
        _warn_api_abnormal(json_str, "京东 getImmediatePlayToM", "data", json_data)
        return result
    live_status = _dig(json_data, "data", "status")
    # 京东 status==1 为开播
    if live_status == 1:
        # 仅 authorId 入口才需补查标题（直链入口标题缺省）
        if author_id:
            data = {
                "functionId": "jdTalentContentList",
                "appid": "dr_detail",
                "body": '{"authorId":"' + author_id + '","type":1,"userId":"","page":1,"offset":"-1",'
                '"monitorSource":"1","pageSize":1}',
            }
            json_str2 = await async_req(
                "https://api.m.jd.com/jdTalentContentList", data=data, proxy_addr=proxy_addr, headers=headers
            )
            json_str2 = _get_str_response(json_str2)
            json_data2 = _loads_dict(json_str2)
            contents = _dig_list(json_data2, "result", "content")
            if contents:
                result["title"] = _dig_str(contents[0], "title")
            else:
                # 标题只用于文件名，不值得让已确认开播的一路取流作废（与 YY 标题补取同口径）
                _warn_api_abnormal(json_str2, "京东 jdTalentContentList", "result.content[0].title", json_data2)

        flv_url = _dig_str(json_data, "data", "videoUrl")
        m3u8_url = _dig_str(json_data, "data", "h5VideoUrl")
        if not flv_url or not m3u8_url:
            # status 已报开播却无地址：风控降级/字段改名，不是「未开播」
            _warn_api_abnormal(json_str, "京东 getImmediatePlayToM", "data.videoUrl / data.h5VideoUrl", json_data)
            return result
        result |= {"is_live": True, "m3u8_url": m3u8_url, "flv_url": flv_url, "record_url": m3u8_url}
    return result


@trace_error_decorator
async def get_faceit_stream_data(
    url: str, proxy_addr: OptionalStr = None, cookies: OptionalStr = None
) -> dict[str, object]:
    # 获取 Faceit 直播流数据
    # 解析链路：nicknames 拿 user_id → streamings 拿 platform；platform==twitch 委托 get_twitchtv_stream_data
    # （透传代理/cookie，否则登录态丢失）；否则回未开播；返回 is_live + 平台流地址。
    headers = {
        "Referer": "https://www.faceit.com/zh/players/qpjzz/stream",
        "faceit-referer": "web-next",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:148.0) Gecko/20100101 Firefox/148.0",
    }

    # 调用方透传 cookie 时优先采用；否则走游客态/自动获取凭据（各平台未登录态取流能力不一，部分更易被风控）
    if cookies:
        headers["Cookie"] = cookies
    # MIN-2213（2026-09-23）：原为裸 `re.findall(...)[0]`——用户粘贴不带 /stream 的玩家
    # 资料页（https://www.faceit.com/zh/players/xxx）时抛 IndexError，日志只剩一行
    # "IndexError … in get_faceit_stream_data"，读不出「换链接形态」这个可执行结论。
    # 与本文件其余「正则未命中即 raise ValueError("Failed to find …")」的写法统一口径。
    nickname_matches = re.findall("/players/(.*?)/stream", url)
    if not nickname_matches:
        raise ValueError("Failed to find faceit nickname in url")
    nickname = nickname_matches[0]
    api = f"https://www.faceit.com/api/users/v1/nicknames/{nickname}"
    json_str = await async_req(api, proxy_addr=proxy_addr, headers=headers)
    json_str = _get_str_response(json_str)
    # MID-48（2026-09-21 海外批次）：nicknames 接口对不存在的用户名返回不含 payload.id 的信封
    # （或风控 HTML），原二级索引抛错被装饰器伪装成「未开播」。
    json_data = _loads_dict(json_str)
    user_id = _dig(json_data, "payload", "id")
    if user_id is None:
        _warn_api_abnormal(json_str, "Faceit users/nicknames", "payload.id", json_data)
        raise RuntimeError("Failed to retrieve Faceit user id")
    api2 = f"https://www.faceit.com/api/stream/v1/streamings?userId={user_id}"
    json_str2 = await async_req(api2, proxy_addr=proxy_addr, headers=headers)
    json_str2 = _get_str_response(json_str2)
    json_data2 = _loads_dict(json_str2)
    # payload 为空数组是「该用户没有直播」的既有静默形态，不得刷告警
    platform_info = _dig(json_data2, "payload", 0)
    if platform_info is None:
        if _dig(json_data2, "payload") is None:
            _warn_api_abnormal(json_str2, "Faceit stream/streamings", "payload", json_data2)
        return {"anchor_name": "", "is_live": False}
    anchor_name = _dig_str(platform_info, "userNickname")
    anchor_id = _dig_str(platform_info, "platformId")
    platform = _dig_str(platform_info, "platform")
    if platform == "twitch":
        # 委托 Twitch 解析：必须透传代理与 cookies，否则登录态/代理在这一跳全部丢失
        result = await get_twitchtv_stream_data(f"https://www.twitch.tv/{anchor_id}", proxy_addr, cookies)
        result["anchor_name"] = anchor_name
    else:
        result = {"anchor_name": anchor_name, "is_live": False}
    return result


@trace_error_decorator
async def get_migu_stream_url(
    url: str, proxy_addr: OptionalStr = None, cookies: OptionalStr = None
) -> dict[str, object]:
    # 获取咪咕直播流地址
    # 解析链路：basic-data 拿 pId → playurl 接口拿 source_url → migu.js 签名算 ddCalcu；
    # currentLive=="1" 取流；m3u8 经重定向、flv 直用；返回 is_live + m3u8/flv + record_url。
    headers = {
        "origin": "https://www.miguvideo.com",
        "referer": "https://www.miguvideo.com/",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/141.0.0.0 Safari/537.36 Edg/141.0.0.0",
        "appCode": "miguvideo_default_www",
        "appId": "miguvideo",
        "channel": "H5",
    }

    # 调用方透传 cookie 时优先采用；否则走游客态/自动获取凭据（各平台未登录态取流能力不一，部分更易被风控）
    if cookies:
        headers["Cookie"] = cookies

    web_id = url.split("?")[0].rsplit("/")[-1]
    # 先从 basic-data 静态缓存拿到 pId（真实房间号）；该接口对游客开放、无需登录 cookie。
    api = f"https://vms-sc.miguvideo.com/vms-match/v6/staticcache/basic/basic-data/{web_id}/miguvideo"
    json_str = await async_req(api, proxy_addr=proxy_addr, headers=headers)
    json_str = _get_str_response(json_str)
    # MID-48（2026-09-21）：basic-data 对不存在的 web_id 返回不含 body 的信封（或被风控换成
    # HTML），原 `json_data["body"]` 抛 KeyError → 装饰器 → 「未开播」。body 缺失归因后仍按
    # 未开播返回（pId 缺失本身是既有的「房间不存在/失效」静默路径，不刷日志）。
    json_data = _loads_dict(json_str)
    body = cast(dict[str, object], _dig(json_data, "body") or {})
    if not body:
        _warn_api_abnormal(json_str, "咪咕 basic-data", "body", json_data)
    anchor_name = _dig_str(body, "title")
    detail_title = _dig_str(body, "detailPageTitle")
    live_title = f"{anchor_name}-{detail_title}" if detail_title else anchor_name
    room_id = _dig(body, "pId")

    result: dict[str, object] = {"anchor_name": anchor_name, "is_live": False}
    # basic-data 没拿到 pId：房间不存在/失效，按未开播返回
    if not room_id:
        return result

    params = {
        "contId": room_id,
        # rateType=3 为原画；clientId 每次请求用随机 uuid（无状态、不缓存）；chip/channelId 为固定渠道标识。
        "rateType": "3",
        "clientId": str(uuid.uuid4()),
        "timestamp": int(time.time() * 1000),
        "flvEnable": "true",
        "xh265": "false",
        "chip": "mgwww",
        "channelId": "",
    }

    api = f"https://webapi.miguvideo.com/gateway/playurl/v3/play/playurl?{urllib.parse.urlencode(params)}"
    json_str = await async_req(api, proxy_addr=proxy_addr, headers=headers)
    json_str = _get_str_response(json_str)
    json_data = _loads_dict(json_str)
    # currentLive 是字符串 "1" 表示在播，其它值（含 "0"/空）视为未开播直接返回。
    if _dig(json_data, "body", "content") is None:
        # body/content 缺失是「接口改版或风控」（房间存在且已确认要取流），与 currentLive
        # 为 "0" 的正常未开播形态不同因，必须区分——否则与下方 urlInfo 缺失一起都表现为
        # 「未开播」，用户只会看到持续的「网址内容获取失败」。
        _warn_api_abnormal(json_str, "咪咕 playurl", "body.content.currentLive", json_data)
        return result
    live_status = _dig(json_data, "body", "content", "currentLive")
    # 咪咕 currentLive 为字符串 "1" 才在播，其它值（含 "0"/空）判未开播
    if live_status != "1":
        return result
    else:
        result["title"] = live_title
        # source_url 是未签名的播放地址，必须经 migu.js 算出 ddCalcu/sv 签名参数后才可用，
        # 裸地址直接拉会 403；下面 _get_dd_calcu 返回的才是带签名的可拉流地址。
        source_url = _dig_str(json_data, "body", "urlInfo", "url")
        if not source_url:
            _warn_api_abnormal(json_str, "咪咕 playurl", "body.urlInfo.url", json_data)
            return result

        async def _get_dd_calcu(url: str) -> str:
            # 咪咕签名算法（内部方法）：node 失败/超时统一转为 ProgramError，
            # 由上层装饰器按平台错误处理，不向调用方泄漏 CalledProcessError。
            # migu.js（2026-08 重写版）输出带 ddCalcu/sv 参数的完整地址：
            # 加密因子与 sv 版本号由脚本端从官网接口获取（失败回退播放器内置
            # 默认因子），此处不再拼接固定 sv=10010（该值已过期）。
            try:
                # 2026-09-12 审查 6.3：原为同步 subprocess.run（timeout=30），
                # 在 async 协程内会冻结本房间的整个事件循环最长 30 秒（该房间
                # 其它协程全部停摆）。改 utils.run_node_script_async（to_thread）
                signed = await utils.run_node_script_async(f"{JS_SCRIPT_PATH}/migu.js", url, timeout=30)
                return signed
            except Exception:
                # 咪咕签名失败/超时统一转 ProgramError，由上层装饰器按平台错误处理，
                # 不向调用方泄漏 CalledProcessError。to_thread 内抛出的异常会被
                # 原样传播（asyncio.to_thread 不包装异常类型），故此处宽泛捕获。
                raise ProgramError("Failed to execute JS code. Please check if the Node.js environment")

        real_source_url = await _get_dd_calcu(source_url)
        # 签名后地址按后缀分流：m3u8 需再发一次请求取重定向后的真实清单，flv 直链可直接作为录制源。
        if ".m3u8" in real_source_url:
            m3u8_url = await async_req(real_source_url, proxy_addr=proxy_addr, headers=headers, redirect_url=True)
            m3u8_url = _get_str_response(m3u8_url)
            # 重定向失败（空响应）判未直播，避免把空串当流地址返回
            if not m3u8_url:
                return result
            result["m3u8_url"] = m3u8_url
            result["record_url"] = m3u8_url
        else:
            result["flv_url"] = real_source_url
            result["record_url"] = real_source_url
        result["is_live"] = True
    return result


@trace_error_decorator
async def get_lianjie_stream_url(
    url: str, proxy_addr: OptionalStr = None, cookies: OptionalStr = None
) -> dict[str, object]:
    # 获取连接直播流地址
    # 解析链路：roomNumber 直取 getRoomInfo → isonline==1 取 videoUrl；非 webrtc:// 拼不出可录地址按未开播；
    # 返回 is_live + m3u8 + flv + record_url；webrtc 转 https 后替换后缀得 flv/m3u8。
    headers = {
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/141.0.0.0 Safari/537.36 Edg/141.0.0.0",
        "accept-language": "zh-CN,zh;q=0.8,zh-TW;q=0.7,zh-HK;q=0.5,en-US;q=0.3,en;q=0.2",
    }

    # 调用方透传 cookie 时优先采用；否则走游客态/自动获取凭据（各平台未登录态取流能力不一，部分更易被风控）
    if cookies:
        headers["cookie"] = cookies

    room_id = url.split("?")[0].rsplit("lailianjie.com/", maxsplit=1)[-1]
    play_api = f"https://api.lailianjie.com/ApiServices/service/live/getRoomInfo?&_$t=&_sign=&roomNumber={room_id}"
    json_str = await async_req(play_api, proxy_addr=proxy_addr, headers=headers)
    json_str = _get_str_response(json_str)
    # MID-48（2026-09-21 海外批次）：getRoomInfo 对不存在的 roomNumber 返回不含 data 的信封
    # （或风控 HTML），原 `["data"]["nickname"]` 链式索引抛错被装饰器伪装成「未开播」。
    json_data = _loads_dict(json_str)
    room_data = cast(dict[str, object], _dig(json_data, "data") or {})
    if _dig(room_data, "isonline") is None:
        _warn_api_abnormal(json_str, "连接直播 getRoomInfo", "data.isonline", json_data)
        return {"anchor_name": _dig_str(room_data, "nickname"), "is_live": False}
    anchor_name = _dig_str(room_data, "nickname")
    live_status = _dig(room_data, "isonline")

    result: dict[str, object] = {"anchor_name": anchor_name, "is_live": False}
    if live_status == 1:
        title = _dig_str(room_data, "defaultRoomTitle")
        webrtc_url = _dig_str(room_data, "videoUrl")
        # videoUrl 非 webrtc:// 时无法拼出可录制的 https 地址，判未直播而非让 split 越界抛 IndexError
        if not str(webrtc_url).startswith("webrtc://"):
            return result
        https_url = "https://" + webrtc_url.split("webrtc://")[1]
        # MIN-2212（2026-09-23）：三路地址都是把容器后缀插在**查询串之前**（.flv?/.m3u8?），
        # 因为 CDN 按路径后缀判容器、签名参数须留在后缀之后。原实现完全依赖 URL 含 "?"——
        # videoUrl 不带查询串时 replace 是空操作，m3u8_url/flv_url/record_url 三字段同指
        # 原始无扩展路径 → stream_select 无从判容器、ffmpeg 每轮必失败，而 is_live=True
        # 会把这一轮记成**成功解析样本**（AGENTS「解析成功轮即上报成功样本」），
        # 熔断统计看不出该线路已坏。
        # 在「归因 + 按未开播返回」与「改成无 ? 时拼 .flv 到路径末尾」之间选前者：
        # 拿不到查询串即说明该 videoUrl 不是可直接 HTTP 拉流的地址（缺签名参数、或本就是
        # webrtc 信令地址），拼出后缀也必然 4xx，返回 is_live=False 才是该轮的诚实语义
        # （与同批「已判开播却拿不到任何线路 → 归因 + is_live=False」口径一致）。
        if "?" not in https_url:
            _warn_api_abnormal(json_str, "连接直播 getRoomInfo", "data.videoUrl", json_data)
            return result
        flv_url = https_url.replace("?", ".flv?")
        m3u8_url = https_url.replace("?", ".m3u8?")
        result |= {"is_live": True, "title": title, "m3u8_url": m3u8_url, "flv_url": flv_url, "record_url": flv_url}
    return result


@trace_error_decorator
async def get_laixiu_stream_url(
    url: str, proxy_addr: OptionalStr = None, cookies: OptionalStr = None
) -> dict[str, object]:
    # 获取来秀直播流地址
    # 解析链路：calculate_sign(md5 盐 u) 游客头 → getShareLiveVideo 拿 playUrl；
    # playStatus==0(注意是 0 而非 1) 取流；返回 is_live + flv + record_url；room_data 缺失按未开播返回并留归因告警。
    def generate_uuid(ua_type: str) -> str:
        # 生成 UUID（来秀签名用）
        if ua_type == "mobile":
            return str(uuid.uuid4())
        return str(uuid.uuid4()).replace("-", "")

    def calculate_sign(ua_type: str = "pc") -> dict[str, int | str]:
        # 计算来秀请求签名：md5("web" + 随机imei + 时间戳 + 固定盐u)。
        # u 是该 App 写死的签名盐（服务端硬编码），改了服务端无法校验；imei 每次随机即可。
        a = int(time.time() * 1000)
        s = generate_uuid(ua_type)
        u = "kk792f28d6ff1f34ec702c08626d454b39pro"

        input_str = f"web{s}{a}{u}"
        md5_hash = hashlib.md5(input_str.encode("utf-8")).hexdigest()

        return {"timestamp": a, "imei": s, "requestId": md5_hash, "inputString": input_str}

    sign_data = calculate_sign(ua_type="pc")
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/141.0.0.0 Safari/537.36 Edg/141.0.0.0",
        "mobileModel": "web",
        "timestamp": str(sign_data["timestamp"]),
        "loginType": "2",
        "versionCode": "10003",
        "imei": str(sign_data["imei"]),
        "requestId": str(sign_data["requestId"]),
        "channel": "9",
        "version": "1.0.0",
        "os": "web",
        "platform": "WEB",
        "Origin": "https://www.imkktv.com",
        "Referer": "https://www.imkktv.com/",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
    }

    # 调用方透传 cookie 时优先采用；否则走游客态/自动获取凭据（各平台未登录态取流能力不一，部分更易被风控）
    if cookies:
        headers["cookie"] = cookies

    pattern = r"(?:roomId|anchorId)=(.*?)(?=&|$)"
    match = re.search(pattern, url)
    room_id = match.group(1) if match else ""
    play_api = f"https://api.imkktv.com/liveroom/getShareLiveVideo?roomId={room_id}"
    json_str = await async_req(play_api, proxy_addr=proxy_addr, headers=headers)
    json_str = _get_str_response(json_str)
    # MID-48（2026-09-21 海外批次）：getShareLiveVideo 对不存在的 roomId 返回不含 data 的信封，
    # 原注释即自述「room_data 缺失 KeyError 由装饰器兜底」——但那等于把三种成因压成一条
    # 「未开播」。改为安全下钻并留区分性告警。
    json_data = _loads_dict(json_str)
    room_data = cast(dict[str, object], _dig(json_data, "data") or {})
    if _dig(room_data, "playStatus") is None:
        _warn_api_abnormal(json_str, "来秀 getShareLiveVideo", "data.playStatus", json_data)
        return {"anchor_name": _dig_str(room_data, "nickname"), "is_live": False}
    anchor_name = _dig_str(room_data, "nickname")
    # 来秀用 playStatus==0 表示在播（注意是 0 而非 1，与其它平台相反），非 0 视为未开播。
    live_status = _dig(room_data, "playStatus") == 0

    result: dict[str, object] = {"anchor_name": anchor_name, "is_live": False}
    # 来秀在播才取 playUrl
    if live_status:
        flv_url = _dig_str(room_data, "playUrl")
        if not flv_url:
            _warn_api_abnormal(json_str, "来秀 getShareLiveVideo", "data.playUrl", json_data)
            return result
        result |= {"is_live": True, "flv_url": flv_url, "record_url": flv_url}
    return result


@trace_error_decorator
async def get_picarto_stream_url(
    url: str, proxy_addr: OptionalStr = None, cookies: OptionalStr = None
) -> dict[str, object]:
    # 获取 Picarto 直播流地址
    # channel.online 布尔直接驱动 is_live；m3u8 由固定 edge host + anchor_name 拼出
    # （golive+{name}），非接口返回，依赖 anchor_name 稳定，拼错会得到无效地址。
    headers = {
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/141.0.0.0 Safari/537.36 Edg/141.0.0.0",
        "accept-language": "zh-CN,zh;q=0.8,zh-TW;q=0.7,zh-HK;q=0.5,en-US;q=0.3,en;q=0.2",
    }

    # 调用方透传 cookie 时优先采用；否则走游客态/自动获取凭据（各平台未登录态取流能力不一，部分更易被风控）
    if cookies:
        headers["cookie"] = cookies

    anchor_id = url.split("?")[0].rsplit("/", maxsplit=1)[-1]
    api = f"https://ptvintern.picarto.tv/api/channel/detail/{anchor_id}"

    json_str = await async_req(api, proxy_addr=proxy_addr, headers=headers)
    json_str = _get_str_response(json_str)
    # MID-48（2026-09-21 海外批次）：channel detail 对不存在的 anchor_id 返回不含 channel.online 的
    # 信封（或风控 HTML），原链式索引抛错被装饰器伪装成「未开播」。
    json_data = _loads_dict(json_str)
    channel = cast(dict[str, object], _dig(json_data, "channel") or {})
    if _dig(channel, "online") is None:
        _warn_api_abnormal(json_str, "Picarto channel detail", "channel.online", json_data)
        return {"anchor_name": _dig_str(channel, "name"), "is_live": False}
    anchor_name = _dig_str(channel, "name")
    live_status = _dig(channel, "online")

    result: dict[str, object] = {"anchor_name": anchor_name, "is_live": live_status}
    if live_status:
        title = _dig_str(channel, "title")
        m3u8_url = f"https://1-edge1-us-newyork.picarto.tv/stream/hls/golive+{anchor_name}/index.m3u8"
        result |= {"is_live": True, "title": title, "m3u8_url": m3u8_url, "record_url": m3u8_url}
    return result
