# -*- coding: utf-8 -*-
# 同步 HTTP 客户端：urllib 直连 / requests 代理两条出站路径，含 ssl_verify 单次覆盖与响应体上限
import atexit
import gzip
import http.client
import io
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

import i18n

# JSON 可序列化类型别名：对齐 requests._types.JsonType 的结构（该别名在较新版 requests 中
# 定义于 TYPE_CHECKING 块内、运行时不可导入，故本地显式重定义，同时满足运行时注解求值
# 与 requests.post(json=...) 的参数类型校验两端）。
JsonType: TypeAlias = None | bool | int | float | str | Sequence["JsonType"] | Mapping[str, "JsonType"]

from . import http_config as config
from . import utils
from .logger import logger

# 禁用代理的处理器（本地请求不使用代理）
no_proxy_handler = urllib.request.ProxyHandler({})

# ── M-2（2026-09-29 审查 WP-B）：opener 的 handler 集合按「协议白名单」显式构造 ──────────
# 原先两支预构建 opener 都走 urllib.request.build_opener()，而它的默认 handler 集合里固定带着
# FileHandler / FTPHandler / DataHandler（CPython 3.14 urllib.request.build_opener 的
# default_classes 列表），于是：
#   ① 直连路径 sync_req("file:///etc/passwd") 会把本地文件当响应体原样返回——FileHandler 走的
#      就是内置 open()，与网络层毫无关系；
#   ② 更要命的是**跨 scheme 跳转**：HTTPRedirectHandler 把 Location 重新交给**同一个 opener**
#      处理，所以「公网地址先过入口白名单 → 302 到 file://…」一样能被读出来。入口那一道
#      （utils.is_safe_http_url）只看最初的 URL，看不见落地地址。
# 现在只显式注册 http/https 两类协议 handler + 重定向 + 错误处理 + UnknownHandler 兜底，
# **不再注册** file/ftp/data。协议无 handler 时 urllib 落到 UnknownHandler.unknown_open，抛
# URLError('unknown url type: …')，响应体一步都不读。选「显式白名单」而不是「build_opener 后
# remove_handler_by_class 摘掉」的两条理由：
#   · 摘除法只挡得住我点名摘的那三类；CPython 将来往默认集合里加任何新协议，都会自动进到本仓
#     的出站面上——白名单形态下「新增协议」必须是显式改动。
#   · OpenerDirector.remove_handler_by_class / .handlers 都不在 typeshed 声明里，得靠 cast+getattr
#     绕静态检查（AGENTS「三参 getattr 不做字面量名解析」那条同族风险）。
# UnknownHandler **必须保留**：它就是「白名单外协议」的统一拒绝口，摘掉它 urllib 会改抛
# 「unknown url type」以外的形态，失败语义反而漂移。
# 残余缺口（登记，不在本层闭合）：abroad=True 分支用的是 urllib.request.urlopen，即**进程全局
# 默认 opener**（仍带 FileHandler）；把它也换成本模块的白名单 opener，会连带换掉
# tests/test_sync_http.py 对 urlopen 的 patch 目标（AGENTS 硬约束），故该分支改为「事后核对落地
# URL」——文件已被读出但绝不外流，见 _reject_unsafe_scheme 的注释与该分支的调用点。
_HTTP_ONLY_HANDLERS: tuple[type[urllib.request.BaseHandler], ...] = (
    urllib.request.UnknownHandler,
    urllib.request.HTTPHandler,
    urllib.request.HTTPDefaultErrorHandler,
    urllib.request.HTTPRedirectHandler,
    urllib.request.HTTPErrorProcessor,
)


def _http_only_opener(https_handler: urllib.request.HTTPSHandler) -> urllib.request.OpenerDirector:
    # 按上面的白名单组装一支 opener：先 ProxyHandler({})（本地请求不走系统代理），再逐条 add_handler，
    # 最后带上调用方给的 HTTPSHandler。
    # HTTPSHandler 之所以是**必填实参**而不是白名单里的一条：两支 opener 的唯一差异就是它挂的
    # SSLContext（安全支默认 context / 降级支 CERT_NONE），而 OpenerDirector.add_handler 是
    # 「追加」不是「替换」——把它放进默认列表再补一支，opener 上就会出现两支 HTTPSHandler，
    # 由 handler_order 相同的两支按插入顺序竞争，降级语义可能被默认那支吃掉（实测会被
    # tests/test_sync_http.py::_opener_https_context 的「恰好一支」断言抓红）。必填实参把
    # 「只能有一支」变成构造层面的保证。
    # urllib 按 BaseHandler.handler_order 排序插入，其余顺序与 build_opener 的默认集合等价，
    # 差别只有「非 http/https 协议一律不注册」这一条。
    opener = urllib.request.OpenerDirector()
    for handler in (no_proxy_handler, *(klass() for klass in _HTTP_ONLY_HANDLERS), https_handler):
        opener.add_handler(handler)
    return opener


# 预构建 opener：仅禁用代理，保留默认证书验证（ssl_verify=True 时使用）
# M-2 起该支不再带 file/ftp/data 三类 handler（见上方白名单说明）。
_opener_secure = _http_only_opener(urllib.request.HTTPSHandler())

# ── 安全边界说明（2026-09-12 审查 6.7 / 2026-09-14 F-12 落地，行为向后兼容）──
# 「不校验证书」的 SSLContext 与 opener 一律**按需惰性构造**，禁止改回模块级常驻：import 期就
# 存在一个不校验的 SSLContext，等于给整个进程开了静默的全局降级面——任何误用（含第三方库走默认
# 上下文的分支）都是一次不告而变的跳过校验。惰性化后只有「本次请求要求跳过校验」的分支才创建它。
# 保留按需降级能力的原因：个别平台 CDN 存在证书链/主机名不匹配（虎牙 TX CDN 等），用户可能需要为
# 解析请求放行；同时 ssl_verify 单次覆盖参数让凭据类调用点（未来新增的登录 / token 刷新等）可以显式
# 强制校验，不被全局开关拖下水。CERT_NONE 路径在生产中同样不可达（`http_config.ssl_verify` 无任何
# set_ssl_verify(False) 调用点），风险是**潜在误用面**而非现实暴露面；惰性构造的防线仍保留。
#
# 调用面（如实写，不编造）：**本模块当前没有任何生产 importer**，去留待维护者决定。取证命令：
#   grep -rn "sync_http\|sync_req(" --include=*.py src/ main.py gui.py web.py msg_push.py i18n.py scripts/
# 实测只命中①本文件自身、②同样零生产调用点的 `src/weverse_auth.py`（2026-09-23 已删除）、③`tests/`；
# `src/spider.py` 导入的是 `from .async_http import async_req`（httpx 异步面），登录、消息推送
# （msg_push.py 自建 requests/urllib 调用）、Web 面板也不经本模块。
#   [历史注] 2026-09-23 之前本段写作「sync_req 调用点全部位于 src/spider.py」，已被证伪（SEV-2226）。
# 本体仍保留：它承载别处没有的两点——F-12 的「同步/异步两条出站路径同时透传 ssl_verify 单次覆盖」
# 不变量，以及 `tests/test_sync_http.py` 对该不变量的回归锁。若将来确认不再接线，应连同 F-12 的双侧
# 陈述一起清理，而不是留成第二条无人执行、却会被文档当作事实源的「同名不同实现」。
_ssl_context_insecure: ssl.SSLContext | None = None
_opener_insecure: urllib.request.OpenerDirector | None = None


def _get_insecure_context() -> ssl.SSLContext:
    # 惰性构造 CERT_NONE 上下文（仅在确实需要跳过校验时被调用）
    global _ssl_context_insecure
    if _ssl_context_insecure is None:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        _ssl_context_insecure = ctx
    return _ssl_context_insecure


def _get_insecure_opener() -> urllib.request.OpenerDirector:
    # 惰性构造「禁用代理 + 禁用证书验证」的 opener（仅在确实需要时被调用）
    # M-2：同样走 _http_only_opener 白名单（降级只降**证书校验**这一项，协议面不跟着放宽）。
    global _opener_insecure
    if _opener_insecure is None:
        _opener_insecure = _http_only_opener(urllib.request.HTTPSHandler(context=_get_insecure_context()))
    return _opener_insecure


def _resolve_ssl_verify(override: bool | None) -> bool:
    # 单次请求的证书校验裁决：显式 override 优先（凭据类调用点可强制校验），
    # 未指定时跟随控制面全局开关（现状语义，向后兼容）。
    return config.ssl_verify if override is None else override


def _get_opener(ssl_verify: bool | None = None) -> urllib.request.OpenerDirector:
    # 按「本次请求」的 SSL 验证裁决选择本地请求 opener。
    # ssl_verify=None 表示跟随全局开关（历史行为）；显式传值时以该次调用为准。
    return _opener_secure if _resolve_ssl_verify(ssl_verify) else _get_insecure_opener()


def _reject_unsafe_scheme(url: str, stage: str) -> None:
    # M-2（2026-09-29 审查 WP-B）：scheme 白名单的**唯一执行点**，两个调用位分别是
    #   ① sync_req 入口（最初那个 URL）；
    #   ② abroad 分支的重定向落地地址（该分支经 urllib.request.urlopen = 进程全局默认 opener，
    #      仍带 FileHandler，无法像无代理分支那样在**发出之前**拒绝，只能在收到之后立刻抛错，
    #      让文件内容绝不作为响应体外流）。
    # 判定函数与 async 侧**同一个** utils.is_safe_http_url（src/async_http.py 的 async_req /
    # get_response_status 入口用的就是它），不在本模块另写一份 urlparse 规则造成两份事实源。
    # 抛 ValueError 而不是 return ""：本模块的失败契约由 sync_req 的外层 except 统一收口
    # （记 error 日志 + 返回空串），因此调用方看到的形状与 async 侧「warning + 空值契约」一致，
    # 异常不会穿透；异常文本自带脱敏（外层 except 还会对 {e} 再过一次 mask_credentials，
    # 两层都留着——与 async 侧 WD-01 的双重脱敏同口径）。
    # 没有改用 warning 级 + 直接 return：那需要一条能诚实描述「sync_req 拒绝非白名单协议」的
    # tr 模板，而四语目录 + web/app.js 里现存的两条都写着 async_req / get_response_status
    # 的函数名，拿来复用会把日志前缀写假；新增 tr 串又必须同步五处目录并重编 .mo
    # （AGENTS「i18n 文案、目录与占位符」），不属本次改动的文件范围。
    if utils.is_safe_http_url(url):
        return
    raise ValueError(f"sync_req 拒绝非白名单协议的请求（{stage}）: {utils.mask_credentials(url)}")


_thread_local = threading.local()
# 进程内全部线程 Session 的弱引用登记：线程销毁后条目自动回收，不阻止 GC；
# 进程退出时（atexit）据此统一优雅关闭仍存活的连接池（80+ 房间长跑场景）
_all_sessions: "weakref.WeakSet[requests.Session]" = weakref.WeakSet()
_all_sessions_lock = threading.Lock()


def _session() -> requests.Session:
    # 线程内复用的 requests.Session。requests 的模块级 get/post 每次都新建一个 Session 并在
    # 退出时销毁，底层 urllib3 连接池随之丢弃——每次请求都要重做 TCP（HTTPS 还要重握手）：
    # 微基准实测单次 11.9ms vs 复用的 1.47ms（约 8×），200 次请求产生 200 条连接 vs 1 条。
    # 该读数取自**同步出站层被接线**的前提下；本模块当前无生产 importer（见模块头「调用面」），
    # 故只保留结论本身，不声称收益已落地。
    # Session 本身不是线程安全的，故用 thread-local 每线程一份：既避免跨线程共享（会互相踩
    # 连接状态），又能让长期存活的房间线程持续复用同一连接池。
    # 测试约定：打桩目标是 `src.sync_http._session`，**不是** `src.sync_http.requests`
    # ——改回后者会让用例绕过真实复用路径、失防（tests/test_sync_http.py 即按此写）。
    session: requests.Session | None = getattr(_thread_local, "session", None)
    if session is None:
        session = requests.Session()
        _thread_local.session = session
        with _all_sessions_lock:
            _all_sessions.add(session)
    return session


def session() -> requests.Session:
    # 线程级 Session 的公开出口（MIN-08 新增）：供「必须拿到状态码 / 响应头、因而无法走
    # sync_req」的调用点复用同一份连接池。sync_req 的返回契约是「响应文本，失败一律空串」，
    # 非 200 与网络异常都塌成同一个 ""，登录/令牌刷新类端点若走它会丢掉 MI-22 刚补的
    # status_code 诊断线索——这类调用点必须用本函数，而不是绕过 sync_http 直接 requests.post
    # （后者丢掉线程级 Session 复用、代理与 SSL 策略接线）。
    # 打桩时 patch 的仍是 _session（与本仓测试约定一致）。
    return _session()


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

# ─── 响应体上限（SEV-2226 收尾，2026-09-23）：读侧与解压侧各一道，缺一不可 ───────
# 为什么必须有上限：无参 `resp.read()` = 「对端给多少就申请多少」，而 gzip 压缩比可达 1000:1 以上
# ——被 MITM / 劫持的响应（或恶意平台）只要回几十 KB 的 gzip，就能让房间线程在解压时申请数 GB 内存；
# 本进程 OOM 不是「这一房间失败」而是**整个录制进程被带走**（80+ 房间与 Web 面板同进程）。且原
# `except Exception` 只兜网络/解析异常，MemoryError 属 BaseException、连兜底都兜不住。
# 为什么是**两道**而不是一道：只限压缩体会漏掉主要形态（压缩 30KB → 解压 30MB）；只限解压输出又会
# 先在 `_resp.read()` 上被无上限的压缩体打爆。故 ① 压缩态按块读、累计超过 _MAX_RESPONSE_BYTES 立即
# 拒绝（顺带挡住「无 Content-Length 的慢速大响应」这一非炸弹形态）；② 解压侧用 GzipFile 分块读、
# 累计超过 _MAX_DECOMPRESSED_BYTES 立即拒绝——峰值内存因此钉在「压缩上限 + 一个块」，而非解压后全量。
# 取值口径：平台页面 / JSON / m3u8 播放列表的真实量级在几十 KB ~ 1MB，两个上限都比最宽的正常响应高
# 一个数量级以上，宁可放宽也不误杀（误杀 = 该平台整轮漏录，代价高于内存风险）。超限后抛 ValueError →
# 由 sync_req 的既有失败分支记一条脱敏 error 日志并返回空串，调用方按「空响应 = 未开播/疑似风控」处理
# （与 async_req 的失败语义一致，不新增契约）。
_MAX_RESPONSE_BYTES = 8 * 1024 * 1024  # 压缩/原始响应体的读入上限
_MAX_DECOMPRESSED_BYTES = 32 * 1024 * 1024  # gzip 解压后的产出上限
_READ_CHUNK_BYTES = 64 * 1024


def _read_capped(resp: "http.client.HTTPResponse | urllib.error.HTTPError", limit: int, kind: str) -> bytes:
    # 单次带 amt 的 read：HTTPResponse.read(amt) 至多返回 amt 字节，故「读进内存的量」
    # 天然被钉在 limit+1 之内；读完仍满额即判超限并拒绝该响应。
    # **刻意不写成 while 累加循环**：本仓 tests/test_sync_http.py 的响应替身是 MagicMock，
    # 其 read() 无论传什么参数都返回同一个非空串——「读到空块才退出」的循环在测试里会变成
    # 死循环（且全量 pytest 表现为零输出挂死）。单次带 amt 的读法对该替身同样成立。
    # M-03（2026-10-18 审查）：形参扩到 urllib.error.HTTPError——400 分支的错误体读取同样走本函数
    # （HTTPError 的 read(amt)/close() 与 HTTPResponse 同形，fp 即错误体流），否则「仅 400 例外」
    # 那条支路绕过本模块的读取上限。
    data = resp.read(limit + 1)
    if len(data) > limit:
        raise ValueError(f"响应体超过{kind}上限 {limit} 字节，已拒绝该响应")
    return data


# Content-Encoding 的最外层编码（L-26，2026-10-19）：多值按 `,` 拆分后取最后一段并小写。
# 「最外层」是 HTTP 语义里最后被施加、因此也最先需要被解掉的编码；取值大小写不敏感。
def _outermost_content_encoding(raw: str | None) -> str:
    if not raw:
        return ""
    tokens = [token.strip().lower() for token in raw.split(",") if token.strip()]
    return tokens[-1] if tokens else ""


def _read_capped_session(response: "requests.Response", encoding: str) -> str:
    # M-18（2026-10-19）：代理分支的带上限读取。requests 的 iter_content 默认 decode_content=True，
    # 因此累计到的是**解码后**字节——一次即同时覆盖「压缩体上限」与「解压炸弹」（产出必然 ≥ 压缩体
    # 时才可能超限，此时先被本上限挡住）。上限取两道中较宽的那道：带 Content-Encoding 时用
    # _MAX_DECOMPRESSED_BYTES，否则 _MAX_RESPONSE_BYTES，与直连路径同一取值口径。
    # 超限抛 ValueError → sync_req 既有通用 except 记脱敏日志并返回空串（失败契约不变）。
    compressed = bool((response.headers.get("Content-Encoding") or "").strip())
    limit = _MAX_DECOMPRESSED_BYTES if compressed else _MAX_RESPONSE_BYTES
    chunks: list[bytes] = []
    total = 0
    for chunk in response.iter_content(chunk_size=_READ_CHUNK_BYTES):
        if not chunk:
            continue
        total += len(chunk)
        if total > limit:
            raise ValueError(f"响应体超过响应体上限 {limit} 字节，已拒绝该响应")
        chunks.append(chunk)
    return b"".join(chunks).decode(encoding)


def _gunzip_capped(data: bytes, limit: int) -> bytes:
    # 分块解压：GzipFile 每次 read() 只解压够数的量，因此峰值内存受 limit 约束；
    # 用 gzip.decompress(data) 做不到这一点——它一次性把整棵树展开成完整字节。
    # 这里可以安全地循环：底层是 io.BytesIO，EOF 必然返回 b''（与上面的替身形态无关）。
    handle = gzip.GzipFile(fileobj=io.BytesIO(data), mode="rb")
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = handle.read(_READ_CHUNK_BYTES)
        if not chunk:
            break
        total += len(chunk)
        if total > limit:
            raise ValueError(f"gzip 解压结果超过上限 {limit} 字节（解压炸弹形态），已拒绝该响应")
        chunks.append(chunk)
    return b"".join(chunks)


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
    ssl_verify: bool | None = None,
) -> str:
    # 同步 HTTP 请求：支持 GET/POST、代理、重定向、gzip 解压。失败一律返回空串。
    # ssl_verify：本次请求的证书校验覆盖（None = 跟随控制面全局开关）。
    # 凭据类调用点（登录 / token 刷新等）应显式传 True，避免被全局降级波及；
    # 该覆盖必须同时透传 urllib 与 requests(代理) 两条路径（F-12，曾只改一条即出现口径分叉）。
    if headers is None:
        headers = {}
    # MID-27：代理地址归一（裸 ip:port 补 http:// 前缀）原先只存在于异步侧
    # （async_http.async_req / get_response_status 入口都调 handle_proxy_addr），
    # 而配置项「代理地址」由 read_config_value 原样读入、用户普遍写成 127.0.0.1:7890。
    # 于是同一份配置下 async 解析正常、本函数的调用点（当时 src/ 里约 125 处）全部把裸值
    # 交给 requests → InvalidSchema/InvalidURL 被外层 except 吞成空串，形态是「开了代理后
    # 某平台解析全失败且表现为空响应」——本仓最难归因的一类失败。
    # 两侧现共用同一 helper、同一语义。（调用点计数为 MID-27 当时快照，本模块现已无生产 importer。）
    proxy_addr = utils.handle_proxy_addr(proxy_addr)
    verify = _resolve_ssl_verify(ssl_verify)
    resp_str = ""
    try:
        # M-2：入口 scheme 白名单（与 async 侧 async_req/get_response_status 同一道防线、同一个
        # 判定函数）。放在 try 内的第一条语句，是为了让拒绝路径继续走本函数既有的统一收口
        # （记日志 + 返回空串），而不是把 ValueError 抛穿给调用方——sync_req 的返回契约是
        # 「响应文本，失败一律空串」，调用方（含未来接线的平台解析函数）按空串判失败。
        _reject_unsafe_scheme(url, "入口")
        if proxy_addr:
            # 使用代理的请求
            proxies = {"http": proxy_addr, "https": proxy_addr}
            # M-18（2026-10-19）：代理分支原先不传 stream，`response.text` 由 requests/urllib3
            # 自行解压 gzip/deflate/br，两道字节上限对它完全不生效——一小份高压缩比响应就能让
            # 进程申请数 GB 内存。改 stream=True + 手工分块计数：requests 的 iter_content 默认
            # 已按 Content-Encoding 解码，因此累计的是**解压后**字节，一次即覆盖两种形态
            # （压缩体上限由累计产出上限顺带覆盖：产出 ≤ 压缩体时也不会有额外暴露面）。
            # redirect_url 分支改读 response.url（requests 在 stream=True 下同样已完成重定向、
            # 不物化正文），不再经过 .content。
            if data is not None or json_data is not None:
                # POST 请求（带代理）
                response = _session().post(
                    url,
                    data=data,
                    json=json_data,
                    headers=headers,
                    proxies=proxies,
                    timeout=timeout,
                    verify=verify,
                    stream=True,
                )
            else:
                # GET 请求（带代理）
                response = _session().get(
                    url, headers=headers, proxies=proxies, timeout=timeout, verify=verify, stream=True
                )
            if redirect_url:
                return response.url
            resp_str = _read_capped_session(response, content_encoding)
        else:
            # 2026-09-12 审查 6.3：请求体的判定由真值（`if data and ...`）改为 `is not None`。
            # 原写法与上方代理分支（`data is not None or json_data is not None`）语义相反——
            # data="" / json_data={} 时配代理走 POST、不配代理静默退化成 GET，调用方只看到
            # 空响应且无法归因（async_req 侧早于此处统一为 is not None）。
            if data is not None and not isinstance(data, bytes):
                if isinstance(data, dict):
                    data = urllib.parse.urlencode(data).encode(content_encoding)
                else:
                    data = str(data).encode(content_encoding)
            if json_data is not None and isinstance(json_data, (dict, list)):
                data = json.dumps(json_data).encode(content_encoding)

            # L-26（2026-10-19）：两条收紧。
            # ① 显式声明 `Accept-Encoding: identity`（调用方没自己给时）——urllib 不会自动解压，
            #    而服务器默认很可能回 gzip/deflate/br；让服务器别压是最省事也最省内存的做法。
            # ② 编码识别按 `,` 拆分并取**最外层**（最后一段）。原实现只认 `== "gzip"`：
            #    `gzip, br` 这类多值、或大小写变体都会落到 else 分支，把压缩字节当明文解码，
            #    产出一串乱码交给调用方当有效响应解析（本仓最难归因的静默失败形态之一）。
            #    仍只解 gzip：deflate 之外的 br/zstd 在 stdlib 侧没有解码器，显式判失败优于静默乱码。
            if not any(key.lower() == "accept-encoding" for key in headers):
                headers = {**headers, "Accept-Encoding": "identity"}
            req = urllib.request.Request(url, data=cast("bytes | None", data), headers=headers)

            try:
                if abroad:
                    # 海外请求：仅当（本次裁决为）不校验证书时才带上 CERT_NONE 上下文，
                    # 直连路径不经过 opener，故必须在此处单独透传同一份裁决
                    _resp = cast(
                        http.client.HTTPResponse,
                        urllib.request.urlopen(
                            req, timeout=timeout, context=None if verify else _get_insecure_context()
                        ),
                    )
                else:
                    # 本地请求：opener 按「本次调用」的 ssl_verify 覆盖选择（无代理）
                    _resp = cast(http.client.HTTPResponse, _get_opener(ssl_verify).open(req, timeout=timeout))
                try:
                    if abroad:
                        # M-2：abroad 分支的重定向由 **urllib 进程全局默认 opener**（仍带 FileHandler，
                        # 本模块不得 install_opener 去换它）执行，入口白名单只覆盖最初的 URL，
                        # 故落地地址必须复核。写在内层 try 的第一条是为了让拒绝路径照样落到
                        # 下面的 finally —— _resp.close() 归还句柄，否则每命中一次就漏一个已打开的
                        # 文件/连接对象。
                        # 这是「不外流」而非「不访问」：该跳请求已发出、目标已被读出，本行让它在
                        # 成为响应体之前随 ValueError 一起丢掉。无代理分支不需要这一步——它的
                        # opener 里根本没有 file/ftp/data handler，跨 scheme 跳转在**发出之前**
                        # 就被 UnknownHandler 拒成 URLError（见 _HTTP_ONLY_HANDLERS 上方说明）。
                        _reject_unsafe_scheme(_resp.url, "重定向落地")
                    if redirect_url:
                        return _resp.url

                    # 响应编码与 gzip 解压：两个上限（读入 / 解压产出）都必需，
                    # 理由与取值口径见 _MAX_RESPONSE_BYTES 上方的整段说明——无上限时
                    # 一个被 MITM 的小响应就足以把整个录制进程打成 OOM。
                    resp_encoding = _outermost_content_encoding(_resp.headers.get("Content-Encoding"))
                    if resp_encoding == "gzip":
                        resp_bytes = _gunzip_capped(
                            _read_capped(_resp, _MAX_RESPONSE_BYTES, "压缩响应体"), _MAX_DECOMPRESSED_BYTES
                        )
                        resp_str = resp_bytes.decode(content_encoding)
                    elif resp_encoding in ("", "identity"):
                        # 未压缩时同一条读入上限即已足够
                        resp_str = _read_capped(_resp, _MAX_RESPONSE_BYTES, "响应体").decode(content_encoding)
                    else:
                        # L-26：不支持的编码（deflate/br/zstd/多段叠加）显式失败，不把压缩字节当明文解码
                        raise ValueError(f"不支持的响应内容编码: {resp_encoding}")
                finally:
                    _resp.close()

            except urllib.error.HTTPError as e:
                # 仅 400 例外：部分平台在参数不合规时回 400 且正文含可用信息，原样返回给调用方；
                # 其余状态码继续上抛，交给下面的统一失败分支
                try:
                    if e.code == 400:
                        # M-03（2026-10-18 审查）：本分支原先是无参 `e.read()` 全量读取——与
                        # 成功路径改前的老形态同构的「对端给多少就申请多少」，超大 400 错误体
                        # 可直接威胁进程内存（MemoryError 连统一失败兜底都兜不住）。现与成功路径
                        # 同走 _read_capped。为何只需**一道**上限（成功路径 gzip 分支是两道）：
                        # 本分支从不解压 400 错误体（调用方拿原文），没有解压动作就没有
                        # 「解压产出」这个暴露面；若在此补 gzip 解压反而改变既有透传契约，超出
                        # 本次收口范围。超限抛 ValueError → 内层 finally 照常 e.close() 归还句柄
                        # → 外层通用 except 记一条脱敏 error 日志并返回空串（sync_req 既有失败
                        # 契约「失败一律空串」不变，异常不穿透给调用方）。
                        resp_str = _read_capped(e, _MAX_RESPONSE_BYTES, "400 错误响应体").decode(content_encoding)
                    else:
                        raise
                finally:
                    e.close()
            # L-27（2026-10-19）：此处原有 `except URLError`（warning + raise）与 `except Exception`
            # （error + raise）两级再上抛，而最外层还有一个统一失败分支——同一次请求失败固定落
            # 三条日志（两条 error、一条 warning），把轮转日志的有效容量浪费掉，排查时还要先分辨
            # 三条里哪条是「真原因」。两级都只是「记一条 + 原样上抛」，外层已经做了同一件事
            # （且带 type_name 与脱敏 URL），故整体删除、只留外层那一条。

    except Exception as e:
        # 请求失败统一记日志并返回空串：错误文本若伪装成响应体会被上游当有效数据解析。
        # URL 与异常文本同样先脱敏再落日志。
        logger.error(
            i18n.tr(
                "sync_req 请求失败: {masked_url} - {type_name}: {e}",
                masked_url=utils.mask_credentials(url),
                type_name=type(e).__name__,
                e=utils.mask_credentials(str(e)),
            )
        )
        resp_str = ""

    return resp_str
