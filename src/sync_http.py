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

# ── opener 的 handler 集合按「协议白名单」显式构造 ────────────────────────────────
# 不用 urllib.request.build_opener()：它的默认集合固定带 FileHandler / FTPHandler /
# DataHandler，于是直连路径可读 file:// 本地文件，且 HTTPRedirectHandler 会把 Location 交给
# 同一个 opener，「公网地址 302 到 file://…」同样能被读出——入口白名单只看最初的 URL，
# 看不见落地地址。这里只注册 http/https 两类协议 handler + 重定向 + 错误处理 +
# UnknownHandler：协议无 handler 时 urllib 落到 UnknownHandler.unknown_open，抛 URLError
# 且响应体一步不读。选显式白名单而非「build_opener 后 remove_handler_by_class 摘掉」：
# 摘除法挡不住 CPython 未来新增的默认协议，且 remove_handler_by_class/.handlers 不在
# typeshed 声明里。UnknownHandler 必须保留：它是「白名单外协议」的统一拒绝口，摘掉会让
# 失败语义漂移。
# 残余缺口：abroad=True 分支用 urllib.request.urlopen（进程全局默认 opener，仍带 FileHandler），
# 换掉它会连带换掉 tests/test_sync_http.py 的 patch 目标，故该分支改为「事后核对落地 URL」——
# 文件已被读出但绝不外流，见 _reject_unsafe_scheme 与该分支的调用点。
_HTTP_ONLY_HANDLERS: tuple[type[urllib.request.BaseHandler], ...] = (
    urllib.request.UnknownHandler,
    urllib.request.HTTPHandler,
    urllib.request.HTTPDefaultErrorHandler,
    urllib.request.HTTPRedirectHandler,
    urllib.request.HTTPErrorProcessor,
)


def _http_only_opener(https_handler: urllib.request.HTTPSHandler) -> urllib.request.OpenerDirector:
    # 按上方白名单组装 opener：先 ProxyHandler({})（本地请求不走系统代理），再逐条
    # add_handler，最后带上调用方给的 HTTPSHandler。
    # HTTPSHandler 必须是必填实参而不是白名单里的一条：两支 opener 的唯一差异是它挂的
    # SSLContext，而 add_handler 是「追加」不是「替换」，放进默认列表再补一支会让两支同序
    # handler 竞争，降级语义可能被默认那支吃掉（由 tests 的「恰好一支」断言抓红）。
    # urllib 按 BaseHandler.handler_order 排序插入，其余顺序与 build_opener 默认集合等价。
    opener = urllib.request.OpenerDirector()
    for handler in (no_proxy_handler, *(klass() for klass in _HTTP_ONLY_HANDLERS), https_handler):
        opener.add_handler(handler)
    return opener


# 预构建 opener：仅禁用代理，保留默认证书验证（ssl_verify=True 时使用）；
# 不带 file/ftp/data 三类 handler（见上方白名单说明）。
_opener_secure = _http_only_opener(urllib.request.HTTPSHandler())

# ── 安全边界：降级只降证书校验，且必须惰性构造 ────────────────────────────────
# 「不校验证书」的 SSLContext 与 opener 一律按需惰性构造，禁止改回模块级常驻：import 期就
# 存在一个不校验的上下文，等于给整个进程开静默的全局降级面，任何误用都会不告而变地跳过校验。
# 保留按需降级的原因：个别平台 CDN 存在证书链/主机名不匹配（虎牙 TX CDN 等），用户可能需
# 为解析请求放行；ssl_verify 单次覆盖参数让凭据类调用点可显式强制校验，不被全局开关拖下水。
#
# 调用面：本模块当前没有任何生产 importer，去留待维护者决定（取证：grep -rn "sync_http\|sync_req("
# --include=*.py src/ main.py gui.py web.py msg_push.py i18n.py scripts/）。本体保留的理由：
# 承载「同步/异步两条出站路径同时透传 ssl_verify 单次覆盖」不变量，以及 tests/test_sync_http.py
# 对该不变量的回归锁；若确认不再接线，应连同该双侧陈述一起清理。
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
    # 惰性构造「禁用代理 + 禁用证书验证」的 opener；降级只降证书校验，协议面不跟着放宽。
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
    # scheme 白名单的唯一执行点，两个调用位：① sync_req 入口（最初的 URL）；② abroad 分支的
    # 重定向落地地址（该分支经进程全局 opener，仍带 FileHandler，无法在发出前拒绝，只能在
    # 收到后立刻抛错，让文件内容绝不作为响应体外流）。
    # 判定函数与 async 侧同一个 utils.is_safe_http_url，不另写一份 urlparse 规则造成两份事实源。
    # 抛 ValueError 而非 return ""：由 sync_req 外层 except 统一收口（记 error + 返回空串），
    # 异常不穿透；异常文本自带脱敏，外层再过一次 mask_credentials（与 async 侧双重脱敏同口径）。
    if utils.is_safe_http_url(url):
        return
    raise ValueError(f"sync_req 拒绝非白名单协议的请求（{stage}）: {utils.mask_credentials(url)}")


_thread_local = threading.local()
# 进程内全部线程 Session 的弱引用登记：线程销毁后自动回收，不阻止 GC；进程退出时
# （atexit）据此统一关闭仍存活的连接池（80+ 房间长跑场景）。
_all_sessions: "weakref.WeakSet[requests.Session]" = weakref.WeakSet()
_all_sessions_lock = threading.Lock()


def _session() -> requests.Session:
    # 线程内复用的 requests.Session。模块级 get/post 每次都新建 Session 并在退出时销毁，
    # 底层连接池随之丢弃，每次请求都要重做 TCP（HTTPS 还要重握手），实测约 8× 差距。
    # 本模块当前无生产 importer（见模块头「调用面」），故只保留结论本身，不声称收益已落地。
    # Session 不是线程安全的，故用 thread-local 每线程一份：既避免跨线程共享连接状态，
    # 又让长期存活的房间线程持续复用同一连接池。
    # 测试约定：打桩目标是 `src.sync_http._session`，不是 `src.sync_http.requests`——
    # 改回后者会让用例绕过真实复用路径、失防。
    session: requests.Session | None = getattr(_thread_local, "session", None)
    if session is None:
        session = requests.Session()
        _thread_local.session = session
        with _all_sessions_lock:
            _all_sessions.add(session)
    return session


def session() -> requests.Session:
    # 线程级 Session 的公开出口：供「必须拿到状态码/响应头、因而无法走 sync_req」的调用点
    # 复用同一份连接池——sync_req 把非 200 与网络异常都塌成空串，登录/令牌刷新类端点需要
    # 保留 status_code 诊断线索。不要绕过 sync_http 直接 requests.post（会丢线程级 Session
    # 复用、代理与 SSL 策略接线）。打桩时 patch 的仍是 _session。
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

# ─── 响应体上限：读侧与解压侧各一道，缺一不可 ────────────────────────────────
# 无参 resp.read() = 对端给多少就申请多少，而 gzip 压缩比可达 1000:1 以上：被 MITM/劫持的
# 响应只要回几十 KB gzip，就能让房间线程在解压时申请数 GB 内存，整个录制进程（80+ 房间与
# Web 面板同进程）被带走；MemoryError 属 BaseException，连统一兜底都兜不住。
# 两道的原因：只限压缩体会漏掉主要形态（压缩 30KB → 解压 30MB），只限解压输出又会先在读入
# 压缩体时被打爆。故①压缩态按块读、累计超过 _MAX_RESPONSE_BYTES 立即拒绝（顺带挡住无
# Content-Length 的慢速大响应）；②解压侧用 GzipFile 分块读、累计超过 _MAX_DECOMPRESSED_BYTES
# 立即拒绝——峰值内存钉在「压缩上限 + 一个块」。
# 取值：平台页面/JSON/m3u8 的真实量级在几十 KB ~ 1MB，两个上限都比最宽的正常响应高一个数
# 量级以上，宁可放宽也不误杀（误杀 = 该平台整轮漏录）。超限抛 ValueError → sync_req 既有
# 失败分支记脱敏日志并返回空串，调用方按「空响应 = 未开播/疑似风控」处理。
_MAX_RESPONSE_BYTES = 8 * 1024 * 1024  # 压缩/原始响应体的读入上限
_MAX_DECOMPRESSED_BYTES = 32 * 1024 * 1024  # gzip 解压后的产出上限
_READ_CHUNK_BYTES = 64 * 1024


def _read_capped(resp: "http.client.HTTPResponse | urllib.error.HTTPError", limit: int, kind: str) -> bytes:
    # 单次带 amt 的 read：HTTPResponse.read(amt) 至多返回 amt 字节，读进内存的量天然钉在
    # limit+1 之内；读完仍满额即判超限。
    # 刻意不写成 while 累加循环：tests 的响应替身是 MagicMock，read() 无论传什么都返回同一
    # 非空串，「读到空块才退出」的循环会死循环（全量 pytest 表现为零输出挂死）。
    # 形参含 urllib.error.HTTPError：400 分支的错误体读取同样走本函数，否则该支路绕过上限。
    data = resp.read(limit + 1)
    if len(data) > limit:
        raise ValueError(f"响应体超过{kind}上限 {limit} 字节，已拒绝该响应")
    return data


# Content-Encoding 的最外层编码：多值按 `,` 拆分后取最后一段并小写。
# 「最外层」是 HTTP 语义里最后被施加、因此也最先需要被解掉的编码；取值大小写不敏感。
def _outermost_content_encoding(raw: str | None) -> str:
    if not raw:
        return ""
    tokens = [token.strip().lower() for token in raw.split(",") if token.strip()]
    return tokens[-1] if tokens else ""


def _read_capped_session(response: "requests.Response", encoding: str) -> str:
    # 代理分支的带上限读取。requests 的 iter_content 默认 decode_content=True，累计到的是解压后
    # 字节——一次即覆盖「压缩体上限」与「解压炸弹」。上限取两道中较宽的那道：带 Content-Encoding
    # 时用 _MAX_DECOMPRESSED_BYTES，否则 _MAX_RESPONSE_BYTES，与直连路径同一口径。
    # 超限抛 ValueError → sync_req 既有通用 except 记脱敏日志并返回空串。
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
    # 分块解压：GzipFile 每次 read() 只解压够数的量，峰值内存受 limit 约束；
    # gzip.decompress(data) 会一次性展开整棵树，做不到这一点。
    # 这里可以安全循环：底层是 io.BytesIO，EOF 必然返回 b''（与响应替身形态无关）。
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
    # 代理地址归一（裸 ip:port 补 http:// 前缀）与异步侧共用同一 helper：配置项由
    # read_config_value 原样读入、用户普遍写 127.0.0.1:7890，不归一会让 requests 抛
    # InvalidSchema/InvalidURL 被外层 except 吞成空串，表现为「开代理后某平台解析全失败」。
    proxy_addr = utils.handle_proxy_addr(proxy_addr)
    verify = _resolve_ssl_verify(ssl_verify)
    resp_str = ""
    try:
        # 入口 scheme 白名单（与 async 侧同一道防线、同一个判定函数）。放在 try 内第一条，
        # 是为了让拒绝路径走本函数既有的统一收口（记日志 + 返回空串），而不是把 ValueError
        # 抛穿给调用方——sync_req 的契约是「响应文本，失败一律空串」。
        _reject_unsafe_scheme(url, "入口")
        if proxy_addr:
            # 使用代理的请求
            proxies = {"http": proxy_addr, "https": proxy_addr}
            # 代理分支必须 stream=True + 手工分块计数：原先 response.text 由 requests/urllib3
            # 自行解压，两道字节上限完全不生效——一小份高压缩比响应就能让进程申请数 GB 内存。
            # iter_content 默认已按 Content-Encoding 解码，累计的是解压后字节，一次覆盖两种形态。
            # redirect_url 分支改读 response.url（stream=True 下同样已完成重定向、不物化正文）。
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
            # 请求体判定用 `is not None`，与上方代理分支一致：用真值判断会让 data="" /
            # json_data={} 在配代理时走 POST、不配代理时静默退化成 GET，调用方只看到空响应。
            # （async_req 侧早已统一为 is not None。）
            if data is not None and not isinstance(data, bytes):
                if isinstance(data, dict):
                    data = urllib.parse.urlencode(data).encode(content_encoding)
                else:
                    data = str(data).encode(content_encoding)
            if json_data is not None and isinstance(json_data, (dict, list)):
                data = json.dumps(json_data).encode(content_encoding)

            # ① 调用方没给时显式声明 Accept-Encoding: identity——urllib 不会自动解压，
            #    让服务器别压是最省内存的做法。
            # ② 编码识别按 `,` 拆分取最外层（最后一段）：原先只认 == "gzip"，`gzip, br` 或
            #    大小写变体会落到 else 把压缩字节当明文解码，产出一串乱码交给调用方当有效响应。
            #    仍只解 gzip：deflate 之外的 br/zstd 在 stdlib 无解码器，显式判失败优于静默乱码。
            if not any(key.lower() == "accept-encoding" for key in headers):
                headers = {**headers, "Accept-Encoding": "identity"}
            req = urllib.request.Request(url, data=cast("bytes | None", data), headers=headers)

            try:
                if abroad:
                    # 海外请求：仅当（本次裁决为）不校验证书时才带上 CERT_NONE 上下文；
                    # 直连不经过 opener，故必须在此单独透传同一份裁决。
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
                        # abroad 分支的重定向由进程全局默认 opener 执行（仍带 FileHandler），
                        # 入口白名单只覆盖最初的 URL，故落地地址必须复核。写在内层 try 的第一条，
                        # 是为了让拒绝路径照样落到 finally 的 _resp.close()。
                        # 这是「不外流」而非「不访问」：跳转请求已发出、目标已被读出，本行让它
                        # 在成为响应体之前随 ValueError 一起丢掉。无代理分支不需要这一步——
                        # 其 opener 没有 file/ftp/data handler，跨 scheme 在发出之前就被
                        # UnknownHandler 拒成 URLError（见 _HTTP_ONLY_HANDLERS 上方说明）。
                        _reject_unsafe_scheme(_resp.url, "重定向落地")
                    if redirect_url:
                        return _resp.url

                    # 两个上限（读入 / 解压产出）都必需，理由与取值口径见 _MAX_RESPONSE_BYTES
                    # 上方说明——无上限时一个被 MITM 的小响应就足以把录制进程打成 OOM。
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
                        # 不支持的编码（deflate/br/zstd/多段叠加）显式失败，不把压缩字节当明文解码
                        raise ValueError(f"不支持的响应内容编码: {resp_encoding}")
                finally:
                    _resp.close()

            except urllib.error.HTTPError as e:
                # 仅 400 例外：部分平台参数不合规时回 400 且正文含可用信息，原样返回调用方；
                # 其余状态码继续上抛，交给下面的统一失败分支。
                try:
                    if e.code == 400:
                        # 400 错误体同样受读入上限约束：原先无参 e.read() 是对端给多少就申请多少，
                        # MemoryError 连统一兜底都兜不住。只设一道上限——本分支从不解压错误体，
                        # 没有「解压产出」暴露面；补 gzip 解压反而会改变既有透传契约。
                        # 超限抛 ValueError → finally 照常 e.close() → 外层通用 except 记脱敏
                        # 日志并返回空串（「失败一律空串」契约不变，异常不穿透）。
                        resp_str = _read_capped(e, _MAX_RESPONSE_BYTES, "400 错误响应体").decode(content_encoding)
                    else:
                        raise
                finally:
                    e.close()
            # 此处不再保留 URLError/Exception 两级再上抛：它们只是「记一条 + 原样上抛」，
            # 会让同一次失败固定落三条日志；统一由最外层记一条带类型与脱敏 URL 的日志。

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
