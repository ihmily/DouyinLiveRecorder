# src/web_api.py
# Web 管理面板 Starlette 应用：认证、路由、静态资源。
#
# 鉴权模型总览（web_api 与 web/ 前端共用）：
# ① 认证开关：config.ini [Web].web_auth_enable=true 时开启；关闭时所有 /api/* 公开访问（局域网用）
# ② 密码存储：首次登录时明文密码自动升级为 PBKDF2-HMAC-SHA256 哈希（盐随机，迭代次数 200k）
# ③ Token：secrets.token_urlsafe(32) 生成 256-bit bearer，过期时间由 web_token_expiry 控制
#    （出厂默认 86400 秒 = 24 小时，取值以 config.ini 与 WEB_DEFAULTS 为准；改它会影响所有既有
#     部署的登录频率）
#    [历史注] 2026-09-19 前本条误写作「默认 1 小时」
# ④ 登录限流：单 IP 滑动窗口 5 次失败/300 秒即 429；仅信任 web_trusted_proxy 列表内代理的 XFF。
#    另有与来源键无关的全局失败预算 40 次/300 秒（MID-35）与免鉴权端点的 per-IP 预算（MIN-2245）
# ⑤ 密码变更：吊销全部 token，强制重登；认证开启时禁止清空密码（防自锁）。Web 节敏感键
#    （web_auth_enable / web_password）做目标态对称校验——开启认证必须有非空密码，否则面板会被
#    锁死（详见 update_config 内注释）
# ⑥ 危险配置键：黑名单（_DANGEROUS_CONFIG_KEYS）即使 auth 关闭也禁止 Web 写入（防 RCE）
# ⑦ 认证开关为**唯一**分流依据：关闭时全放行；开启时只有白名单路径放行，其余一律需 Bearer，
#    **与 HTTP method 无关**——读接口同样拦，跨源读取也能拉走配置与日志。
#    白名单（见中间件 elif 分支，逐条枚举）：/api/login、/api/logout、/api/auth/status、
#    /health、/、/web/*、/favicon.ico。
#    [历史注] 2026-09-22 前写作「写接口需 Bearer；读接口/静态资源放行」，按它评估泄露面结论相反
# ⑧ 非幂等请求校验 Origin 同源（防无认证时的跨站写）；/api/logout 支持单点吊销当前 bearer；
#    配置读取带 mtime+size 缓存（避免每请求全量解析 config.ini）
# ⑨ 响应头：X-Content-Type-Options: nosniff（防 MIME 嗅探）、X-Frame-Options: DENY（防点击劫持）、
#    CSP（见中间件末尾）；GET /api/status 在认证关闭时返回 auth_required=false 与告警供前端提示
# ⑩ 2026-09-20（CODE_REVIEW_2026-09-20）新增的不变量：
#    · 房间写入口裁决唯一：校验下沉到 web_config.format_url_line（URL_config.ini 唯一写入口），
#      add/update/quality 三个接口不可能再次分叉（SEV-02/03）；
#    · Host/Origin 白名单：同源判定不再信任请求自带的 Host，改由服务端配置推导允许名单，
#      并在**每个请求**上重跑「非回环 + 无认证」不变量（SEV-04、MID-36）；
#    · 端点不占事件循环：阻塞的磁盘 IO / 跨线程锁 / 日志归档一律走线程池（同步 def 端点即
#      由 FastAPI 派发到 anyio 线程池），状态快照另加 TTL 缓存 + 单飞 + 超时回陈旧值（MID-34/35）；
#    · 对外不回显内部异常：绝对路径 / Errno 细节只写日志，响应里只给固定 error code（MID-39）；
#    · 敏感配置写入三重拒绝（MID-37 后端半边 + 2026-09-21 掩码补口）：命中 is_sensitive_item 的键
#      既不接受空值、也不接受面板回显用的字面掩码 '***'——前端跳过掩码只是省事，不得当唯一防线；
#    · 语言切换按**生效码**落盘（MID-52）：PUT /api/language 先 i18n.set_language() 再写 config.ini，
#      写的是目录可用性判定后的生效码，保证面板进程与录制子进程不会各说一种语言。
# ⑪ 2026-09-21（CODE_REVIEW_2026-09-21）安全侧新增的三条不变量：
#    · 监听地址基准只能来自进程（SEV-N03）：「非回环 + 无认证」与 Origin 同源判定一律用
#      create_app(bind_host/bind_port) 传入的**实际绑定地址**，不再读可被 PUT /api/config 改写的
#      web_host/web_port；同时对「把 web_host 写成回环值」这一步加目标态校验（两步旁路都拦）。
#    · Origin 与 Host 是**两套名单**（MID-N42）：Host 沿用 web_config.is_host_allowed
#      （放行 IP 字面量 / 无点单标签名、忽略端口），Origin 改判 web_config.is_origin_allowed——
#      host 与端口都要命中「实际绑定 host:port + 回环族 + web_allowed_hosts 显式登记的 host[:port]」。
#    · 会被本进程发出去的 config 值一律收口（MID-N45）：推送接口链接 / ntfy 地址 / 代理地址 /
#      SMTP 服务器的 scheme 与目标网段校验挂在 validate_config_target（config.ini 写侧唯一入口）
#      上，与房间地址共用同一份判定内核，多目标逗号分隔须逐段过判。
# ⑫ 2026-09-23（组 G 收尾）新增/收敛的三条：
#    · 认证两键的写入必须复验口令（MID-2241 后端半边）：认证已开启时 PUT /api/config 写
#      [Web] web_auth_enable / web_password 未携带可验过的 reauth_password 即 403——bearer 只
#      证明「已登录」，不再单独证明「知道口令」（细则见 update_config 内同名段）。
#    · 免鉴权端点有 per-IP 预算（MIN-2245）：/api/auth/status 与 /health 超窗即 429，
#      且 /api/login、/api/auth/status 的配置读取改走 _read_web_config_cached（磁盘 IO 不再按
#      请求放大）。反向边界：PUT /api/config 的口令/认证守卫**不得**用该缓存，必须读磁盘现值
#      （同一轮走过弯路，判据见 update_config 内「判定基准」段）。
#    · `main_loop_alive` 从 /api/status 契约里**撤下**（SEV-2221/SEV-2228 后半）：该键恒不下发、
#      是一条曾被测试当作已覆盖的死路径；面板改由 error/stale 两个真实信号承担「取证失败」，
#      取舍理由与接线点见 _read_engine_status 上方说明。
# pyright: reportUnusedFunction=none, reportCallInDefaultInitializer=none
from __future__ import annotations

import asyncio
import configparser
import inspect
import json
import os
import re
import secrets
import threading
import time
from collections import deque
from collections.abc import AsyncGenerator, Awaitable, Callable
from pathlib import Path
from typing import cast

from starlette.applications import Starlette
from starlette.concurrency import run_in_threadpool
from starlette.exceptions import HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, Response, StreamingResponse
from starlette.staticfiles import StaticFiles

# 错误文案随语言热切换：在产生点按当前目录渲染（tr 调用时查表，模块导入期不定型）。
# 稳定机器码 detail（如 "unauthorized" / "rate_limited" / "host_not_allowed"）是前端契约，刻意不经 tr。
import i18n as i18n_module
from src.web_models import (
    ConfigUpdate,
    LanguageUpdate,
    LoginRequest,
    QualityOptionsUpdate,
    RecordingToggle,
    RoomCreate,
    RoomQualityUpdate,
    RoomToggle,
    RoomUpdate,
)

# ─── Starlette 接线层（阶段 2：FastAPI → Starlette）────────────────────────────
# Starlette 不提供 FastAPI 的参数注入（模型自动解析 / Query 自动绑定 / dict→JSON 自动序列化），
# 这里用 `_route` 装饰器复刻等价语义：① JSON body 解析成 web_models dataclass 作为模型参数；
# ② 查询串按默认值回填、按上下界夹取；③ 同步 def 端点经 run_in_threadpool 派发到线程池
# （与 FastAPI 行为一致，避免阻塞事件循环）；④ 非 Response 返回值统一包成 JSONResponse。
# 业务逻辑与旧实现逐字一致，仅搬运到 Starlette 接线；安全不变量（MID-*/SEV-*）不受影响。
_BODY_MODELS = {
    LoginRequest,
    RoomCreate,
    RoomUpdate,
    RoomToggle,
    RoomQualityUpdate,
    QualityOptionsUpdate,
    RecordingToggle,
    ConfigUpdate,
    LanguageUpdate,
}

# 查询参数的默认值与上下界，复刻 FastAPI Query(default, ge=, le=) 的契约。
# 上下界必须为 int | None：夹取走 max/min 数值比较，声明成 object 会让 mypy 无法解析重载。
_QUERY_DEFAULTS: dict[str, dict[str, tuple[object, int | None, int | None]]] = {
    "delete_room": {"url": ("", None, None)},
    "list_files": {"path": ("", None, None)},
    "download_file": {"path": ("", None, None)},
    "get_logs": {"lines": (200, 1, 5000)},
    "get_danmaku": {"since": (0, 0, None)},
}


# L-30（2026-10-02）：JSON 请求体大小上限。认证关闭（出厂默认）时局域网任一主机可单请求
# 超大 JSON 耗内存（json.loads 全量物化后才谈得上校验），解析前先按 Content-Length 拒绝。
# 面板全部请求体（登录口令/房间/配置节）远小于该值，不影响正常使用。
_JSON_BODY_MAX_BYTES = 1 * 1024 * 1024


async def _read_json_body(request: Request) -> object:
    # 解析 JSON 请求体；非法/空体统一转 422（对齐旧 pydantic 的 422 契约）。
    # 仅当端点有模型参数时适配器才会调用，GET/无 body 端点不会走到这里。
    # L-30：Content-Length 缺失（chunked 传输）时不拦——保守启发式，只挡「声明了超大体积」
    # 的低成本放大面；逐字节读入后的上限由 Starlette 的流式读取与调用方超时兜底。
    content_length = request.headers.get("content-length", "")
    if content_length.isdigit() and int(content_length) > _JSON_BODY_MAX_BYTES:
        raise HTTPException(status_code=413, detail=i18n_module.tr("请求体过大"))
    try:
        return await request.json()
    except Exception:
        raise HTTPException(status_code=422, detail=i18n_module.tr("请求体不是合法 JSON"))


def _route(app: Starlette, methods: list[str], path: str) -> Callable[[Callable[..., object]], Callable[..., object]]:
    # 装饰器工厂：把 FastAPI 风格的端点（模型参数 / Query 参数 / dict→JSON 返回）适配到 Starlette。
    def _decorator(handler: Callable[..., object]) -> Callable[..., object]:
        sig = inspect.signature(handler, eval_str=True)
        params = sig.parameters
        is_async = inspect.iscoroutinefunction(handler)
        model_param: str | None = None
        query_names: list[str] = []
        takes_request = False
        for name, p in params.items():
            if name == "request":
                takes_request = True
            elif p.annotation in _BODY_MODELS:
                model_param = name
            else:
                query_names.append(name)

        async def _adapter(request: Request) -> Response:
            kwargs: dict[str, object] = {}
            if model_param is not None:
                payload = await _read_json_body(request)
                model_cls = params[model_param].annotation
                try:
                    kwargs[model_param] = model_cls.parse(payload)
                except ValueError as exc:
                    raise HTTPException(status_code=422, detail=str(exc))
            for qname in query_names:
                default, lo, hi = _QUERY_DEFAULTS.get(handler.__name__, {}).get(qname, ("", None, None))
                raw = request.query_params.get(qname)
                if raw is None or raw == "":
                    value: object = default
                elif isinstance(default, int):
                    try:
                        value = int(raw)
                    except ValueError:
                        value = default
                else:
                    value = raw
                if isinstance(value, int):
                    if lo is not None:
                        value = max(lo, value)
                    if hi is not None:
                        value = min(hi, value)
                kwargs[qname] = value
            if takes_request:
                kwargs["request"] = request
            if is_async:
                # handler 统一声明为 Callable[..., object]，异步分支按运行时判定收窄为可 await 形态
                result = await cast(Callable[..., Awaitable[object]], handler)(**kwargs)
            else:
                result = await run_in_threadpool(handler, **kwargs)
            if isinstance(result, Response):
                return result
            return JSONResponse(result)

        app.add_route(path, _adapter, methods=methods)
        return handler

    return _decorator


from src.web_config import (
    BUILTIN_QUALITIES,
    QUALITY_OPTIONS_KEY,
    QUALITY_OPTIONS_SECTION,
    SENSITIVE_MASK,
    TEXT_ENCODING,
    _looks_like_secret_value,
    format_url_line,
    hash_web_password,
    is_hashed_web_password,
    is_host_allowed,
    is_loopback_bind_host,
    is_origin_allowed,
    is_sensitive_item,
    normalize_url,
    parse_config_bool,
    parse_url_config,
    read_config_safe,
    read_quality_options,
    read_web_config,
    update_config_line,
    update_or_append_config_line,
    update_room_quality,
    validate_config_target,
    validate_room_target,
    verify_web_password,
    write_quality_options,
)

# web/ 静态资源目录（项目根/web）
_WEB_DIR = Path(__file__).resolve().parent.parent / "web"

# token 存储：{token: expiry_timestamp}
_tokens: dict[str, float] = {}
# 保护 _tokens 并发访问的锁（login 写入、middleware 查询、密码变更时 clear 均需持锁）
_tokens_lock = threading.Lock()
# WD-06：保护 _web_cfg_cache 的锁（见 _read_web_config_cached）
_web_cfg_cache_lock = threading.Lock()

# 登录失败限流：{client_ip: [失败时间戳...]}（滑动窗口内计数，成功登录即清零）
_FAILED_LOGINS: dict[str, list[float]] = {}
# 保护 _FAILED_LOGINS 并发访问的锁（多线程 uvicorn 下 login 并发写、定期清理均需持锁）
_FAILED_LOGINS_LOCK = threading.Lock()
# 窗口内最大失败次数（第 N+1 次尝试直接 429，不再到后端验证密码）
_LOGIN_MAX_FAILURES = 5
# 失败计数滑动窗口（秒）
_LOGIN_FAILURE_WINDOW = 300.0
# MID-35：与来源地址无关的全局失败预算。按 IP 计数有两个对称失效面——攻击者换一个键就换一个窗口
# （本机反代下 XFF 可伪造时尤其明显）；Docker 端口映射把所有真实用户的 client.host 收敛成网关地址，
# 5 次失败即把所有人锁在登录页外。全局预算只封顶「整站每秒能承受多少次口令校验」、与键粒度无关，
# 故既压住爆破吞吐，又不会因单键聚合而误伤合法用户到 5 次。
_GLOBAL_LOGIN_FAILURES: deque[float] = deque(maxlen=512)
_LOGIN_GLOBAL_MAX_FAILURES = 40

# ─── MIN-2245（2026-09-23）：免鉴权端点的 per-IP 预算 ─────────────────────────
# 上面的限流只管 /api/login 的**失败**计数，而白名单里的 /api/auth/status 与 /health 无论认证开关
# 如何都恒可访问、此前毫无预算：能访问端口 = 能零成本、无限次地驱动面板的读路径（/api/auth/status
# 在改走 _read_web_config_cached 之前每请求都是一趟全量 configparser 解析，放大面正好落在这条无人
# 看守的入口上）。阈值刻意放宽到「正常使用远够不到」：面板启动只拉一次本端点，探活/CI 是秒级
# 个位数，而 240 次/分钟 ≈ 4 次/秒已足以把「无限放大」压成「有界成本」。
# 刻意**不**给全局预算：这两个端点极便宜（缓存命中即一次 os.stat），按 IP 封顶只为挡住单点放大；
# Docker 端口映射下所有真实用户收敛到同一网关地址，全局预算会集体误伤（MID-35 已记过）。
_PUBLIC_BUDGET_WINDOW = 60.0
_PUBLIC_BUDGET_MAX = 240
_PUBLIC_BUDGET_PATHS = frozenset(("/api/auth/status", "/health"))
_PUBLIC_BUDGET: dict[str, deque[float]] = {}
_PUBLIC_BUDGET_LOCK = threading.Lock()


def _public_endpoint_over_budget(client_ip: str) -> bool:
    # 免鉴权端点的滑动窗口计数：True 表示该来源本窗口内已超预算（调用侧回 429）。
    # 每次进入都顺带回收窗口外条目（只在超限时整表清理会让键集合随 IPv6 前缀轮换无界增长）；
    # 键数远小于房间数，O(键数) 可接受。
    now = time.monotonic()
    with _PUBLIC_BUDGET_LOCK:
        for stale_ip in [k for k, q in _PUBLIC_BUDGET.items() if not q or now - q[-1] > _PUBLIC_BUDGET_WINDOW]:
            _PUBLIC_BUDGET.pop(stale_ip, None)
        hits = _PUBLIC_BUDGET.get(client_ip)
        if hits is None:
            hits = deque(maxlen=_PUBLIC_BUDGET_MAX + 8)
            _PUBLIC_BUDGET[client_ip] = hits
        while hits and now - hits[0] > _PUBLIC_BUDGET_WINDOW:
            hits.popleft()
        if len(hits) >= _PUBLIC_BUDGET_MAX:
            return True
        hits.append(now)
        return False


# 危险配置键黑名单：允许通过 Web 修改等价于远程命令执行，任何认证状态下都禁止写入
_DANGEROUS_CONFIG_KEYS = {"自定义脚本执行命令"}
# casefold 后的黑名单（2026-09-12 审查 C-1 加固）：行匹配大小写不敏感（re.IGNORECASE），
# 黑名单判定须同等强度，防止 ASCII 危险键的大小写变体绕过（当前集合为中文键，casefold 幂等）
_DANGEROUS_CONFIG_KEYS_FOLDED = {k.casefold() for k in _DANGEROUS_CONFIG_KEYS}

# 房间列表写入互斥锁：序列化「查重 + 追加」的 TOCTOU 窗口，
# 多线程 uvicorn 下并发 POST 同一 URL 时只允许一条成功
_rooms_config_lock = threading.Lock()

# ─── MID-39：对外错误契约 ─────────────────────────────────────────────────────
# 内部异常原文（Windows 绝对路径、Errno 13、loguru 句柄冲突细节）曾被直接塞进
# {"detail": ...} / {"error": ...} 并被前端原样弹成 toast，等于向任何能访问面板的人
# 泄露安装路径与 OS 细节（认证关闭时对局域网可见）。现在对外只给固定 code，细节进日志。
_STATUS_ERROR_CODE = "status_unavailable"
_LOGS_ERROR_CODE = "logs_unavailable"
_DANMAKU_ERROR_CODE = "danmaku_unavailable"
_ROOM_DELETE_ERROR_CODE = "room_delete_failed"
_ROOM_UPDATE_ERROR_CODE = "room_update_failed"
_HOST_DENIED_DETAIL = "host_not_allowed"

# ─── MID-2234：web_token_expiry 的目标态夹取 ─────────────────────────────────
# 该键经 PUT /api/config 可写，且因命中 _KEY_NOT_SECRET_PATTERN 的 expiry 例外而**不受敏感键守卫**，
# 于是既无上下界也无「不得清空」保护。两条真实失效形态：
#   ① 写成 0/负数 → 每次登录拿到的 exp = now + 0，中间件判 exp > time.time() 立即为假 →
#      所有 /api/*（**含再次 PUT 修正自身**）一律 401，用户只能手工编辑 config.ini 恢复，
#      与本文件头注释 ⑤「禁止清空密码（防自锁）」是同一防线却漏了它。
#   ② 写成超大值 → 令牌实际永不过期，且 _tokens 只增不减（内存无界），泄露的 bearer 成为永久凭据。
# 夹取而非拒绝：配置里留一个越界值本身无意义，登录时按边界生效最符合直觉，也不会把面板写成 401。
# 下界 60s（够一次正常会话交互，不至于「刚登录就过期」），上界 7 天（与默认 86400s 同量级放宽）。
_TOKEN_EXPIRY_MIN_SECONDS = 60.0
_TOKEN_EXPIRY_MAX_SECONDS = 7 * 86400.0


def _clamp_token_expiry(raw: object) -> float:
    # 把配置里的 web_token_expiry 夹到 [60, 604800] 秒；非数值/NaN 一律回落默认 86400。
    # 用 float() 而非 int()：配置文件可能写 "86400.0"/"1e6"，int() 会抛 ValueError 把登录打成 500。
    try:
        value = float(cast(float, raw))
    except TypeError, ValueError:
        return 86400.0
    # NaN 与任何比较都为假，必须先显式挡掉，否则下面的 min/max 会把 NaN 原样透传
    if value != value:
        return 86400.0
    return max(_TOKEN_EXPIRY_MIN_SECONDS, min(_TOKEN_EXPIRY_MAX_SECONDS, value))


# ─── MID-34：状态快照的 TTL 缓存 + 单飞 ───────────────────────────────────────
# get_status() 在录制进程里持 record_state_lock / max_request_lock，并调
# utils.check_disk_capacity → shutil.disk_usage：录制盘是 UNC/网络盘/可移动盘且已挂起时
# 该调用可达数十秒。旧实现把它放在 async def 里直接执行 → 一次挂起即停摆整个面板
# （含前端 2s 轮询与 SSE）。现在：① 采样在专用线程里跑；② 结果按 TTL 复用（磁盘容量
# 本就是秒级变化，2s 窗口对展示无损）；③ 同一时刻只允许一个采样在飞（单飞门），
# 超时方立即回陈旧快照并置 stale:true，从而把「慢」限制在数据新鲜度上而非可用性上。
_STATUS_TTL_SECONDS = 2.0
_STATUS_WAIT_SECONDS = 3.0
# 单飞门的租约：采样线程若被彻底卡死（磁盘 IO 永不返回），标记不能永久霸住，
# 否则面板会永远停留在陈旧快照上且再无自愈机会。超过租约即允许再发起一次采样。
_STATUS_INFLIGHT_LEASE = 60.0
_status_lock = threading.Lock()
_status_cache: dict[str, object] | None = None
_status_cache_at = 0.0
_status_inflight = False
_status_inflight_since = 0.0


def _log_internal_error(code: str, exc: BaseException | None = None, level: str = "error") -> None:
    # MID-39 的唯一出口：细节只落日志，响应体只带 code。
    # 消息体刻意写成「纯占位符 + 机器可读 code」而非中文散文：code 是接口契约的一部分
    # （前端按它映射文案），不属于待翻译文案，故不进 i18n 四语目录；
    # 异常类型与完整上下文由 loguru 的 exception 上下文带出，不写裸 str(e)
    # （Windows 下 socket.timeout/TimeoutError 的 str() 为空串，裸写会打成空白行）。
    try:
        from loguru import logger

        if level == "warning":
            logger.opt(exception=exc).warning("{}", code)
        else:
            logger.opt(exception=exc).error("{}", code)
    except Exception:
        # 日志不可用（无控制台/只读目录）时不得反过来影响接口响应；此处只吞「记录失败」本身
        pass


_DENIED_HOSTS_SEEN: set[str] = set()
_DENIED_HOSTS_SEEN_MAX = 64


def _should_warn_denied_host(host: str) -> bool:
    # 首次见到的被拒 Host 才记日志（返回 True）。集合有界，攻击者无法靠换子域把内存撑大。
    key = host.strip().lower()[:120]
    if key in _DENIED_HOSTS_SEEN:
        return False
    if len(_DENIED_HOSTS_SEEN) >= _DENIED_HOSTS_SEEN_MAX:
        _DENIED_HOSTS_SEEN.clear()
    _DENIED_HOSTS_SEEN.add(key)
    return True


def _insecure_bind_allowed() -> bool:
    # 与 web.py 启动检查同源的环境变量破例（DOUYIN_WEB_ALLOW_INSECURE=1）：
    # 中间件的每请求判定必须尊重同一个逃生阀，否则「明知风险仍要开放局域网」的部署
    # 会在启动成功后立刻被 403 掉，用户只看到面板全部报错。
    return os.environ.get("DOUYIN_WEB_ALLOW_INSECURE", "").strip().lower() in ("1", "true", "yes")


# SEV-N03（2026-09-21）：403 文案收敛到一处。两个触发点（关认证、把 web_host 写成回环值）此前各写
# 一份散文，而判定基准换成实际绑定地址后，旧文案「请先在 config.ini 把 web_host 改为 127.0.0.1」
# 会对用户失效——那个键改了也不改变真实监听面，只有重启才改得动。故文案必须报出**实际监听地址**，
# 并把「该做什么」按触发点分开。
_INSECURE_BIND_ENV_TAIL = "；确需对局域网无认证开放时，请设置环境变量 DOUYIN_WEB_ALLOW_INSECURE=1 后重启本进程"


def _insecure_bind_detail(context: str, action: str, bind_host: str) -> str:
    # 组合模板经 tr 渲染：bind/context/action/tail 四段均为调用时求值（语言可热切换）
    return i18n_module.tr(
        "非回环监听地址（当前实际监听 {bind}）下{context}：{action}{tail}",
        bind=bind_host.strip() or i18n_module.tr("(未知)"),
        context=context,
        action=action,
        tail=i18n_module.tr(_INSECURE_BIND_ENV_TAIL),
    )


def _guard_bind_host(app: Starlette, cfg: dict[str, str | int | bool]) -> str:
    # SEV-N03：安全判定的「监听地址」基准。首选 create_app 传入的**实际绑定地址**（web.py 已接线），
    # 只有「调用方未接线」（bind_host is None）才回落到配置值，三条理由：
    # ① 既有调用点（tests/ 多处直接构造 app、第三方复用 create_app 的代码）不传该参数，若默认按
    #    「未知 = 非回环」处理，认证关闭时它们会被中间件全量 403——安全修复变成功能回归，
    #    也让回归用例无法区分「守卫生效」与「守卫锁死」；
    # ② 回落方向与修复前语义逐字一致，新旧用例的差值只可能来自新守卫本身；
    # ③ 回落到配置值不等于放行：仍是 is_loopback_bind_host 的严格判定，只有配置写着回环才判回环。
    # 生产入口必须显式传入，否则「非回环 + 无认证」不变量退回可被两步写入旁路的旧形态。
    bound = cast("str | None", app.state.bind_host)
    if isinstance(bound, str) and bound.strip():
        return bound.strip()
    return str(cast(object, cfg.get("web_host", "")) or "")


def _guard_bind_port(app: Starlette) -> int:
    # SEV-N03 / MID-N42：端口与地址同判——web_port 同样可经 PUT /api/config 改写，而进程监听端口
    # 直到重启才会变；Origin 同源判定要靠端口区分「本站页面」与「本机/局域网里另一台服务器上的
    # 页面」，故基准也必须取实际绑定值。返回 0 表示「调用方未接线」，由 web_config.is_origin_allowed
    # 按配置里的 web_port 回落（理由与 _guard_bind_host 同一套：既不改既有调用点语义，也不把
    # 「未知」当「放行」）。
    return cast("int | None", app.state.bind_port) or 0


# app.state 上的自定义属性由 Starlette 动态承载（类型化为 Any），读取处统一用 cast 收敛类型。
def _trusted_proxy_set(cfg: dict[str, str | int | bool]) -> set[str]:
    return {h.strip() for h in str(cast(str, cfg.get("web_trusted_proxy", ""))).split(",") if h.strip()}


def _get_client_ip(request: Request, cfg: dict[str, str | int | bool]) -> str:
    # MID-35：解析客户端真实 IP，用作登录失败限流的键。
    #
    # 旧实现「直连对端可信时才取 XFF 最左值」在真实部署里挡不住伪造，因为 uvicorn 默认
    # proxy_headers=True 且 forwarded_allow_ips 含 127.0.0.1，会在**本函数之前**就用
    # X-Forwarded-For 最左值覆盖 scope["client"] —— request.client.host 本身已是攻击者写什么就是
    # 什么、且不在 trusted 集合内，函数原样返回该伪造值 → 每请求换一个键 → 「5 次/300 秒」窗口
    # 形同不存在。现依赖 web.py 显式 `proxy_headers=False`（见该处注释）：scope["client"] 即原始
    # socket 对端，本函数是全链路唯一的 XFF 解释者。
    # 直连对端不可信时**完全忽略** XFF（既不拿它当键、也不拿它派生任何键）；可信时按 RFC 7239 的
    # 「从右往左剥」语义取客户端：跳过仍属可信代理的条目，第一个非可信地址才是真客户端
    # （最左值由请求方自填，可以随便写）。
    peer = request.client.host if request.client else "unknown"
    trusted = _trusted_proxy_set(cfg)
    if peer not in trusted:
        return peer
    xff = request.headers.get("x-forwarded-for", "")
    for hop in reversed([h.strip() for h in xff.split(",") if h.strip()]):
        if hop not in trusted:
            return hop
    return peer


def _read_app_version() -> str:
    # 运行时从 pyproject.toml 读取版本号（单一事实源），失败回退 "0.0.0"。
    # 优先 importlib.metadata（已安装时），回退直接解析 pyproject.toml 文件。
    # 与 main.py 的 _read_version_from_pyproject 保持一致的数据来源。
    try:
        from importlib.metadata import version as _get_version

        return _get_version("DouyinLiveRecorder")
    except Exception:
        pass
    pyproject_path = Path(__file__).resolve().parent.parent / "pyproject.toml"
    if pyproject_path.exists():
        text = pyproject_path.read_text(encoding="utf-8")
        m = re.search(r'^version\s*=\s*["\'](.+?)["\']', text, re.MULTILINE)
        if m:
            return m.group(1)
    return "0.0.0"


_APP_VERSION = _read_app_version()


def create_app(
    config_file: str,
    url_config_file: str,
    downloads_root: str,
    logs_dir: str,
    bind_host: str | None = None,
    bind_port: int | None = None,
) -> Starlette:
    # 创建 Starlette 应用。参数显式传入（而非读全局），便于测试时指向临时文件；
    # version 由 _APP_VERSION 在运行时从 pyproject.toml 动态提供，避免硬编码。
    #
    # SEV-N03（2026-09-21）：bind_host / bind_port = **进程实际监听**的地址与端口，由 web.py 把它
    # 已经知道的那个 host/port 传进来。「非回环 + 无认证」不变量与 Origin 同源判定此前都读
    # config.ini 里的 web_host/web_port，而 web_host 自身可经同一个 PUT /api/config 改写（既不敏感
    # 也不在危险键黑名单里），于是「先写 web_host=127.0.0.1、再写 web_auth_enable=false」两步即可
    # 让仍监听 0.0.0.0 的进程变成「无认证 + 全网卡」——判定基准由请求方可写，防线形同不存在
    # （详见 web_config 的 MID-N42 段）。判定一律以本处传入的实际绑定地址为准；config 里的
    # web_host 只在「调用方未接线」时作回落值，理由见 _guard_bind_host。
    app = Starlette()

    # FastAPI 对端点内 raise HTTPException 的默认响应是 JSONResponse({"detail": ...})，而 Starlette
    # 的内建 handler 回 PlainTextResponse(detail)——正文变成裸字符串，前端 apiError() 读不到
    # detail 键，24 条路由的错误契约随之漂移。这里按 FastAPI 语义显式注册 JSON handler；
    # headers 透传保留 raise 时附带的 Retry-After 等（WebAuth 限流路径在用）。
    async def _http_exception_to_json(request: Request, exc: Exception) -> JSONResponse:
        # Starlette 异常处理协议要求形参收宽为 Exception；按注册键分发，运行期必为 HTTPException
        http_exc = cast(HTTPException, exc)
        return JSONResponse({"detail": http_exc.detail}, status_code=http_exc.status_code, headers=http_exc.headers)

    app.add_exception_handler(HTTPException, _http_exception_to_json)

    # 将路径与配置存入 app.state，路由通过 request.app.state 访问
    # 写入处用 setattr 避免对已类型化为 Any 的 app.state 触发 reportAny。
    setattr(app.state, "config_file", config_file)
    setattr(app.state, "url_config_file", url_config_file)
    setattr(app.state, "downloads_root", os.path.realpath(downloads_root))
    setattr(app.state, "logs_dir", logs_dir)
    # None 表达「调用方没告诉我」，空串表达「绑定在空地址」——混用会让未接线的调用点静默退化成
    # 「非回环」→ 全部 /api/* 被 403 锁死。判定处经 _guard_bind_host 回落到配置值。
    setattr(app.state, "bind_host", bind_host)
    setattr(app.state, "bind_port", bind_port)

    # L-28（2026-10-02）：原「web_cfg = read_web_config(...) + setattr(app.state, "web_cfg", ...)」
    # 已删除——该快照只写不读（认证中间件与各端点一律经 _read_web_config_cached 实时取带缓存的
    # 配置），且启动后即刻陈旧，留着会误导「改这里能影响行为」的读者。

    # 认证中间件：每次请求重新读取配置，保证面板内修改配置即时生效。
    # WD-06：读配置走带 mtime+size 失效的进程内缓存。原实现每请求全量 configparser.read + 逐键解析
    # （仅正则编译有 lru_cache），而前端每 2 秒轮询 /api/status、多标签页/多设备线性叠加，在无认证
    # 场景下可被低成本放大为磁盘 IO 压力；配置被改写时 mtime 必变，故「即时生效」语义不受影响。
    # MID-34 的刻意例外：本中间件仍留在事件循环里——每请求只做一次 os.stat（O(1)），只有配置真的
    # 变化时才走一次 configparser 全量解析（~1ms/150 行）；把它也挪进线程池会让**每个**请求多一次
    # 线程派发，反而比它要防的问题更贵。写侧的安全敏感变化另由 _invalidate_web_cfg_cache 兜住。
    # Starlette 没有 FastAPI 的 @app.middleware("http") 装饰器方法（迁移初稿误判为「Starlette 原生
    # 支持」，mypy attr-defined + 运行期导入即抛 AttributeError 双重证伪）；FastAPI 该装饰器的底层
    # 实现就是 add_middleware(BaseHTTPMiddleware, dispatch=func)，此处按同一语义显式注册。
    async def auth_middleware(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        cfg = _read_web_config_cached(cast(str, cast(Starlette, request.app).state.config_file))
        # WD-09：顺带回收过期 token。原实现只在 login 路径清理，长期运行后过期条目
        # 要等下一次登录才回收，token 表随之缓慢增长。
        _purge_expired_tokens()
        path = request.url.path
        # 显式标注为基类 Response：各分支分别产出 JSONResponse 与 call_next 的 Response，
        # 不标注时 mypy 会按首个赋值推断为 JSONResponse 并在后续赋值处报错
        response: Response
        if not is_host_allowed(request.headers.get("host", ""), cfg):
            # MID-36：Host 头必须落在服务端推导的允许名单内（回环 + web_host + web_allowed_hosts，
            # 另放行 IP 字面量与无点单标签名，理由见 web_config.is_host_allowed）。
            # DNS 重绑定（attacker.tld 的 A 记录 TTL=0 指向 127.0.0.1）下，浏览器发出的 Host 与
            # Origin 都是 attacker.tld —— 旧的同源判定拿**请求自带的 Host** 比 Origin，于是必然
            # 「同源」，全部写接口对攻击者页面开放。名单来自 config.ini 而非请求头，该等式即不再
            # 成立。判定放在最前面，读接口一并覆盖（跨源读取同样能拉走配置与日志）。
            if _should_warn_denied_host(request.headers.get("host", "")):
                # 每个被拒 Host 只在**首次**记一条 warning：重绑定/探测流量会以秒级重复同一请求，
                # 逐请求记日志等于让攻击者反向灌满 300KB 轮转的运行日志（logs/ 会保留多份）。
                _log_internal_error(_HOST_DENIED_DETAIL, level="warning")
            response = JSONResponse(status_code=400, content={"detail": _HOST_DENIED_DETAIL})
        elif _api_locked_out_by_insecure_bind(cfg, path, _guard_bind_host(app, cfg)):
            # SEV-04：把「非回环 + 无认证」不变量从 web.py 的启动瞬间检查升级为**每请求**检查。
            # 中间件本来就每请求重读 web_auth_enable（保证面板内改配置即时生效），只在启动时评估
            # 一次的后果是：一个已开认证、监听 0.0.0.0 的部署，任何持 token 者提交一次
            # web_auth_enable=false 即可在**不重启**的情况下把它变成「无认证 + 全网卡监听」，
            # /api/config、/api/logs、/api/files、房间写入随之全开。静态页与 /health 不在拦截范围内：
            # 面板仍要打得开，用户才知道要回去改配置。
            # [历史注] SEV-N03（2026-09-21）前判定基准是「配置里的 web_host」，可被同一个
            # PUT /api/config 两步改写（先写 web_host=127.0.0.1 再关认证）而进程仍监听 0.0.0.0，
            # 「配置自证清白」的判定不成立；现换成 _guard_bind_host 取到的实际绑定地址。
            response = JSONResponse(
                status_code=403,
                content={
                    "detail": "insecure_bind_disabled",
                    "message": i18n_module.tr("非回环监听地址下不允许关闭 Web 认证"),
                },
            )
        elif request.method not in ("GET", "HEAD", "OPTIONS") and not _is_same_origin(
            request, cfg, _guard_bind_host(app, cfg), _guard_bind_port(app)
        ):
            # WD-08：非幂等请求的同源校验。凭据走 Authorization 头，跨域**读取**被浏览器 SOP 挡住，
            # 但跨域**写入**不被挡——Content-Type: text/plain 的 POST 属 simple request，不发预检
            # 即可送达，任意被攻陷网页都能静默驱动写接口（增删房间、改配置、启停录制）。
            # 认证关闭时（出厂默认）这条路径此前完全没有阻碍。
            response = JSONResponse(status_code=403, content={"detail": "cross-origin request denied"})
        elif (
            not cast(bool, cfg["web_auth_enable"])
            or path == "/api/login"
            or path == "/api/logout"
            or path == "/api/auth/status"
            # /health 恒公开：探活方（CI 冒烟 / LB 健康检查 / 监控）不持有面板凭据，若受
            # web_auth_enable 支配，开关一开探活即拿 401 被误判成「服务挂了」。响应只含状态与应用
            # 版本，二者分别恒定、且 FastAPI 自身的 /docs 与 /api/auth/status 本就可公开取得，
            # 公开它不新增信息面。
            or path == "/health"
            or path == "/"
            or path.startswith("/web/")
            or path == "/favicon.ico"
        ):
            # MIN-2245：免鉴权端点里「会读盘/解析」的那两个（/api/auth/status、/health）先过 per-IP
            # 预算。超预算回 429 而不是静默丢弃：探活方与面板都要能区分「服务活着但被限流」与
            # 「服务挂了」，429 仍带下面的安全响应头、语义自证。刻意只对这两条路径生效：/web/* 与 /
            # 是静态资源（由 StaticFiles 直接送文件），给它们加预算只会把「打开面板」这一步限掉。
            if path in _PUBLIC_BUDGET_PATHS and _public_endpoint_over_budget(_get_client_ip(request, cfg)):
                # 不逐请求记日志：被限流的请求已以 429 显式回给调用方，而攻击者正可用「超限后继续打」
                # 把每一条都变成一行日志——等于把放大面从磁盘 IO 换成日志灌写（同 _should_warn_denied_host
                # 的教训）。
                response = JSONResponse(status_code=429, content={"detail": "rate_limited"})
            else:
                response = await call_next(request)
        else:
            auth = request.headers.get("Authorization", "")
            if auth.startswith("Bearer "):
                token = auth[7:]
                with _tokens_lock:
                    exp = _tokens.get(token)
                    valid = exp is not None and exp > time.time()
                if valid:
                    response = await call_next(request)
                else:
                    response = JSONResponse(status_code=401, content={"detail": "unauthorized"})
            else:
                response = JSONResponse(status_code=401, content={"detail": "unauthorized"})
        # 安全响应头（defense in depth：放行与拒绝路径均附加），防 MIME 嗅探与点击劫持
        # 注：SSE 端点 (/api/status/stream) 需 text/event-stream，nosniff 不会与之冲突
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        # 2026-09-12 审查（低危）：补 CSP。面板前端无 CDN 外链、无内联脚本、无 eval
        # （仅用 innerHTML 拼接表格，属 DOM 操作，不受 script-src 约束），故可收紧到
        # 'self'。style-src 放行 'unsafe-inline' 是唯一妥协——若后续出现内联 <style>
        # 或元素 style 属性由 HTML 解析产生（而非 JS DOM API 设置）时才需要它，
        # 保留以免收紧过度导致面板样式失效。
        # form-action / base-uri 显式限制，防表单劫持与 <base> 注入改相对路径指向。
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; "
            "script-src 'self'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; "
            "font-src 'self' data:; "
            # MI-27：面板无任何 WebSocket 用途（/api/status/stream 是 SSE），
            # 原 `ws: wss:` 是 scheme 通配、放行任意主机的 WS 连接，收紧为 'self'。
            "connect-src 'self'; "
            "object-src 'none'; "
            "base-uri 'self'; "
            "form-action 'self'; "
            "frame-ancestors 'none'",
        )
        return response

    # add_middleware 只能在应用开始处理请求之前调用（create_app 返回前即注册）；
    # lifespan 启动后再调用会抛 RuntimeError。
    app.add_middleware(BaseHTTPMiddleware, dispatch=auth_middleware)

    # ===== 路由 =====

    @_route(app, ["POST"], "/api/login")
    def login(req: LoginRequest, request: Request) -> dict[str, object]:
        # MID-34/35：本端点刻意声明为**同步 def**——FastAPI 会把同步端点派发到 anyio 线程池，于是下面的
        # read_web_config（磁盘）、PBKDF2 校验（约 150ms CPU）、首次登录的哈希升级写盘（持
        # file_update_lock + os.replace）全都不在事件循环里执行。旧实现是 async def：一次登录即把整个
        # 面板（含 2s 轮询与 SSE）按住 150ms，而成本可被 config.ini 里的迭代次数放大 → 面板级 CPU DoS
        # （迭代上界另见 web_config.clamp_pbkdf2_iterations）。
        # MIN-2245（2026-09-23）：改走 WD-06 的 mtime+size 缓存——本端点免鉴权，旧写法让「能访问端口」
        # 就等价于「每请求一次全量 configparser 解析」，与 /api/auth/status 同一失效形态。
        # 每次登录重新读取配置，保证面板内修改密码即时生效。
        # **必须 dict(...) 浅拷贝**：下面的明文→哈希升级会写 `cfg["web_password"] = hashed`，直接改缓存
        # 里的共享 dict 会让中间件与后续请求读到「内存已升级、磁盘还没升级」的混合态（升级写盘失败时
        # 尤其明显：缓存被污染成磁盘上并不存在的哈希值）。
        cfg = dict(_read_web_config_cached(cast(str, app.state.config_file)))
        if not cast(bool, cfg["web_auth_enable"]):
            return {"token": "", "expires_in": 0, "auth_required": False}
        client_ip = _get_client_ip(request, cfg)
        # 登录失败限流：滑动窗口内失败达上限后直接拒绝，避免密码被在线爆破
        now = time.time()
        with _FAILED_LOGINS_LOCK:
            # MID-35：先过与来源地址无关的全局失败预算（键可被换、预算换不掉）
            while _GLOBAL_LOGIN_FAILURES and now - _GLOBAL_LOGIN_FAILURES[0] > _LOGIN_FAILURE_WINDOW:
                _ = _GLOBAL_LOGIN_FAILURES.popleft()
            if len(_GLOBAL_LOGIN_FAILURES) >= _LOGIN_GLOBAL_MAX_FAILURES:
                raise HTTPException(429, i18n_module.tr("登录失败次数过多，请稍后再试"))
            # 顺带全表清理窗口外条目（2026-09-12 审查 6.6）：仅成功登录才 pop 的话，
            # IPv6 前缀轮换爆破可让键集合无界增长（内存泄漏面）
            for ip in [ip for ip, ts in _FAILED_LOGINS.items() if not any(now - t < _LOGIN_FAILURE_WINDOW for t in ts)]:
                _FAILED_LOGINS.pop(ip, None)
            failures = [t for t in _FAILED_LOGINS.get(client_ip, []) if now - t < _LOGIN_FAILURE_WINDOW]
            _FAILED_LOGINS[client_ip] = failures
            if len(failures) >= _LOGIN_MAX_FAILURES:
                raise HTTPException(429, i18n_module.tr("登录失败次数过多，请稍后再试"))
        # 注：_purge_expired_tokens 内部自行持锁（它现在也被中间件直接调用），
        # 此处**不可**再包一层 with _tokens_lock——threading.Lock 非重入，会与
        # 函数内的 acquire 形成自死锁（曾导致所有登录请求挂死）。
        _purge_expired_tokens()
        if not cast(str, cfg["web_password"]):
            raise HTTPException(500, i18n_module.tr("web_password 未配置但认证已开启"))
        # 兼容历史明文存储：首次登录时升级为 PBKDF2 哈希，避免明文落盘。
        # M-06（2026-09-30）：升级哈希同样以 strip 后的形态为准——登录比对统一 strip（见下），
        # 存量「首尾带空格」的明文口令才不会被这次升级锁死。
        if not is_hashed_web_password(cast(str, cfg["web_password"])):
            hashed = hash_web_password(cast(str, cfg["web_password"]).strip())
            # H-6：持引擎配置锁写 config.ini，避免与主循环热加载读/其他写并发交错
            import main as _main

            with _main.file_update_lock:
                _ = update_config_line(cast(str, app.state.config_file), "Web", "web_password", hashed)
            # MIN-2245 连带：升级落盘后必须让缓存失效，否则后续请求（含下一次登录、以及
            # 中间件的认证判定）仍读到**明文**那一份，本函数上面的浅拷贝只是把污染
            # 限制在单次请求内、并不能替缓存补上这次写入。
            _invalidate_web_cfg_cache()
            cfg["web_password"] = hashed
        # M-06（2026-09-30）：登录比对统一 strip。写入侧以 strip 后的值哈希（/api/config），
        # reauth 复验也用 strip 后的值（MID-2241）；登录侧若仍用原文，设置时粘贴带出的首尾
        # 空格会重现「能登录、不能 reauth」的口径分叉，进而变成认证配置经面板自锁。
        if not verify_web_password(req.password.strip(), cast(str, cfg["web_password"])):
            with _FAILED_LOGINS_LOCK:
                _FAILED_LOGINS.setdefault(client_ip, []).append(time.time())
                _GLOBAL_LOGIN_FAILURES.append(time.time())
            raise HTTPException(401, i18n_module.tr("密码错误"))
        # 登录成功：清零该 IP 的失败计数（全局预算不回收——它是「整站口令校验吞吐」的
        # 上限，按成功回收就又给了「拿真实账号登录一次即重置预算」的绕法）
        with _FAILED_LOGINS_LOCK:
            _FAILED_LOGINS.pop(client_ip, None)
        token = secrets.token_urlsafe(32)
        # MID-2234：生效值走夹取（见 _clamp_token_expiry 注释）。expires_in 回**生效值**而非原始配置值，
        # 否则前端按配置值算的到期倒计时与实际令牌寿命不一致。
        expires_in = _clamp_token_expiry(cfg["web_token_expiry"])
        expiry = time.time() + expires_in
        with _tokens_lock:
            _tokens[token] = expiry
        return {"token": token, "expires_in": expires_in}

    @_route(app, ["POST"], "/api/logout")
    def logout(request: Request) -> dict[str, object]:
        # WD-09 修复：原实现没有注销端点——前端登出只清 localStorage，服务端 token 在
        # web_token_expiry（默认 86400s）内依旧完全有效，泄露的 token 无法单独吊销，
        # 只能改全局密码（代价是全部会话下线）。此处按 Bearer 精确吊销当前会话。
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            with _tokens_lock:
                _ = _tokens.pop(auth[7:], None)
        return {"ok": True}

    @_route(app, ["GET"], "/api/status")
    async def get_status() -> dict[str, object]:
        # MID-34：唯一保持 async 的数据端点——它需要 asyncio.wait_for 的超时语义。
        # 阻塞采样在专用线程里跑，超时则回退到陈旧快照并置 stale:true，
        # 于是「网络盘挂起 → 整面板停摆」降级为「磁盘数字暂不刷新」。
        snapshot, stale = await _get_status_snapshot()
        if stale:
            return {**snapshot, "stale": True}
        return snapshot

    # 公开端点：暴露 Web 认证状态，供前端在登录前提示「当前面板未启用认证，所有接口可公开访问」
    # （/api/login 在认证关闭时也会经此契约告知前端放行）。故意不走 Bearer 校验——登录前拿不到 token。
    # MID-34：同步 def —— read_web_config 是全量 configparser.read（磁盘 IO），async def 下它会在
    # 事件循环线程里执行，与 /api/status 同属一类停摆源。
    @_route(app, ["GET"], "/api/auth/status")
    def auth_status() -> dict[str, object]:
        # MIN-2245（2026-09-22）：本端点免鉴权，旧写法仍每请求做一次全量 configparser 解析（WD-06 的
        # mtime+size 缓存当时只挂在中间件上）→ 能访问端口即可低成本把读盘放大为磁盘 IO 压力，而这正是
        # WD-06 加缓存的理由。改为走同一份缓存；写侧 _invalidate_web_cfg_cache 已兜底失效。
        cfg = _read_web_config_cached(cast(str, app.state.config_file))
        auth_enabled = cast(bool, cfg["web_auth_enable"])
        return {
            "auth_required": auth_enabled,
            # 显式说明关闭状态下无人能保护面板：仅供局域网可信环境使用
            "warning": (
                None if auth_enabled else i18n_module.tr("Web 认证未启用，任何能访问本面板的网络均可操控录制配置")
            ),
        }

    # 探活端点：进程存活 + ASGI/路由已就绪 + 应用版本可读（_APP_VERSION 在模块导入期即从
    # pyproject.toml 解析，读不到会回退 "0.0.0" 而非抛异常），故本端点**不**探测录制引擎、磁盘、
    # 平台接口等外部依赖——那些不健康时面板仍应可访问（用户需进面板改配置），把它们纳入探活只会让
    # 门禁误红。字段为对外契约：scripts/smoke_web.json 与 CI 冒烟步骤按 {"status": "ok"} 断言，
    # 新增字段可以、改名或改值不行。
    @_route(app, ["GET"], "/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "version": _APP_VERSION}

    @_route(app, ["GET"], "/api/status/stream")
    async def status_stream(request: Request) -> StreamingResponse:
        # 2026-09-12 修复（CODE_REVIEW_FIX_1 F-20）：消除「慢速占用面」。原实现 `while True` 无客户端
        # 断开检测——连接一旦建立就永不释放，每 2 秒轮询一次 main.get_status()（内含锁与字典拷贝）；
        # 误开标签页、爬虫或恶意连接可无限累积常驻协程，缓慢吃满线程池/内存。端点本身已文档化于
        # README（对外契约），故保留并修好而非删除：① 每轮开头检测客户端是否断开（ASGI
        # http.disconnect）后退出；② 连续失败达上限即终止，避免「错误流」也无限推送。
        _MAX_CONSECUTIVE_ERRORS = 5

        async def event_gen() -> AsyncGenerator[str, None]:
            consecutive_errors = 0
            while True:
                if await request.is_disconnected():
                    return
                # MID-34/39：与 /api/status 共用同一份带 TTL 的单飞快照——
                # 每个 SSE 连接各自去抢 record_state_lock + shutil.disk_usage 会把「一个
                # 慢请求停摆一个面板」放大成「一个慢请求停摆所有连接」；
                # 且失败时只推固定 error code，内部异常原文（绝对路径/Errno）不再进 data 帧。
                snapshot, _stale = await _get_status_snapshot()
                if _STATUS_ERROR_CODE in snapshot:
                    consecutive_errors += 1
                    yield f"data: {json.dumps(snapshot, ensure_ascii=False)}\n\n"
                    if consecutive_errors >= _MAX_CONSECUTIVE_ERRORS:
                        return
                else:
                    consecutive_errors = 0
                    yield f"data: {json.dumps(snapshot, ensure_ascii=False)}\n\n"
                await asyncio.sleep(2)

        return StreamingResponse(event_gen(), media_type="text/event-stream")

    @_route(app, ["POST"], "/api/recording/toggle")
    def toggle_recording(req: RecordingToggle) -> dict[str, object]:
        # Web 面板「开始/停止录制」按钮的后端：切换全局录制开关 main.recording_enabled。
        # 开启 → 主循环下一轮（≤3s）自动拉起全部已配置房间线程；
        # 关闭 → 各房间线程在检测点（内层循环顶/ffmpeg 轮询/直下分片/循环等待）自行退出，
        #         进行中的 ffmpeg 录制被终止，退出线程从运行列表移除，可随时重新开始。
        import main

        main.recording_enabled = req.enable
        if not req.enable:
            # Web 面板「停止录制」手动停止路径：立即归档四个运行日志（时间戳取停止操作
            # 发生时刻）。进程仍继续运行，reopen_streams=True 在改名后重建日志句柄，
            # 录制引擎与 Web 服务的日志写入链路不受影响；归档内部全程容错、绝不抛异常。
            from src.log_archive import archive_runtime_logs

            _ = archive_runtime_logs(reopen_streams=True)
        return {"ok": True, "recording_enabled": req.enable}

    @_route(app, ["GET"], "/api/rooms")
    def list_rooms() -> list[dict[str, str | bool]]:
        # MID-34：同步 def（走 FastAPI 线程池）——整文件读 + 抢 record_state_lock。
        rooms = parse_url_config(cast(str, app.state.url_config_file))
        try:
            import main

            with main.record_state_lock:
                running = list(main.running_list)
        except Exception:
            running = []
        for r in rooms:
            # running_list 存正在录制的 URL；recording 集合存的是 "序号N 主播名" 而非 URL，
            # 故仅按 running_list 判定。且必须精确匹配：前缀子串匹配会把短 URL 的录制状态
            # 错误地套到长 URL 上（I3）
            r["recording"] = any(r["url"] == u for u in running)
        return rooms

    @_route(app, ["POST"], "/api/rooms")
    def add_room(req: RoomCreate) -> dict[str, object]:
        # MID-34：同步 def —— validate_room_target 会做 DNS 解析（SEV-03），
        # 落盘又是整文件读 + os.replace；放在事件循环里会让一个慢域名卡死整个面板。
        url = normalize_url(req.url)
        try:
            # SEV-02：显式校验保留在此处（与 format_url_line 内下沉的校验同一入口、同一裁决），
            # 目的是把 ValueError 收敛成 422；format_url_line 里那次是纵深防御。
            validate_room_target(req.url, req.quality, req.name)
            line = format_url_line(url, req.quality, req.name)
        except ValueError as e:
            raise HTTPException(422, str(e)) from e
        # 持有 file_update_lock 与录制主循环的 update_file/delete_line 互斥，
        # 避免热重载的 read→rewrite 窗口内追加行丢失（I2）；
        # _rooms_config_lock 将「查重 + 追加」原子化，杜绝并发 TOCTOU 重复写入。
        import main as _main

        with _rooms_config_lock, _main.file_update_lock:
            existing = parse_url_config(cast(str, app.state.url_config_file))
            if any(r["url"] == url for r in existing):
                raise HTTPException(409, i18n_module.tr("直播间已存在"))
            # MIN-2242（2026-09-22）：追加前必须补末行换行。旧实现直接 open(...,"a") 写，而
            # URL_config.ini 末行可能无 \n（编辑器删掉尾回车、或 delete_line 后本就无尾换行）——
            # 新房间会粘到上一条之后变成 `https://…111https://…222`，**两个房间同时坏掉**，端点却
            # 仍回 {"ok": true}。同仓的 append_config_line 专门写了「末行无尾换行时先补一个」，
            # 这里采用同一手法（先读末字节，缺则先写一个 \n）。
            _url_cfg_path = cast(str, app.state.url_config_file)
            _needs_newline = False
            _is_fresh_file = False
            try:
                with open(_url_cfg_path, "rb") as rf:
                    _ = rf.seek(0, 2)  # 2 = SEEK_END
                    if rf.tell() > 0:
                        _ = rf.seek(-1, 2)
                        _needs_newline = rf.read(1) not in (b"\n", b"\r")
                    else:
                        _is_fresh_file = True  # 存在但为 0 字节：与新建同处理
            except FileNotFoundError:
                _is_fresh_file = True  # 尚不存在：由本次追加建文件，须带文件头 BOM
            except OSError:
                # 被锁/权限异常：交给下面的写入本身报错，此处不改变语义、也不猜 BOM
                pass
            # MIN-2242 后半（2026-09-23 实测收敛）：BOM 只在「文件为空/尚不存在」时写一次，追加改用
            # 不带 sig 的 utf-8。实测 incremental encoder 每次首 encode 都吐 BOM
            # （`codecs.lookup('utf-8-sig').incrementalencoder().encode('abc')` → b'\xef\xbb\xbfabc'），
            # 但 TextIOWrapper 在 "a" 模式下只有**写位为 0** 时才真落下它：先
            # `open(p,'w').write('abc')` 再 `open(p,'a',encoding='utf-8-sig').write('xyz')` 得
            # b'abcxyz'（无 BOM），只有空/新建文件得 b'\xef\xbb\xbfxyz'——报告担心的「首写先落 BOM
            # 再补 \n」在既有内容上并不成立。仍显式改写，是因为那份行为依赖 CPython TextIOWrapper 的
            # seek-to-end 细节（未文档化保证），而本仓 .ini 编码约定（web_config.TEXT_ENCODING /
            # main.py 的 text_encoding = utf-8-sig）以「文件头一个 BOM、行内零 BOM」为准；显式化后
            # 判据自证、回归锁可精确钉住（见 tests/test_web_api.py::TestRoomEndpoints）。
            with open(_url_cfg_path, "a", encoding="utf-8") as f:
                if _is_fresh_file:
                    # utf-8 编码下 U+FEFF 逐字节即 BOM；只在文件为空/新建时写这一份
                    _ = f.write("\ufeff")
                _ = f.write(("\n" if _needs_newline else "") + line + "\n")
        return {"ok": True}

    @_route(app, ["PUT"], "/api/rooms")
    def update_room(req: RoomUpdate) -> dict[str, object]:
        # SEV-02 主修复：本端点此前**完全不做**房间校验（POST 与 PUT/quality 都做），于是它成为绕过
        # SSRF/任意 scheme/画质白名单的第二条写入口。校验现已下沉进 format_url_line（唯一写入口），
        # 这里再显式调用一次，使「起手即校验」的顺序与其它写端点一致，并让 ValueError 统一转 422。
        old_url = normalize_url(req.old_url)
        try:
            validate_room_target(req.url, req.quality, req.name)
            # 写入行同样用归一化 URL：与 add/delete/toggle 的查重口径一致，否则 PUT 写回的原始 URL
            # 下一轮再也匹配不到（归一化 vs 未归一化）
            new_line = format_url_line(normalize_url(req.url), req.quality, req.name)
        except ValueError as e:
            raise HTTPException(422, str(e)) from e
        import main as _main

        # 2026-09-12 审查 6.6：与 add_room 同款双锁保护读改写窗口——无锁时并发「改房间/删房间/
        # 切开关」可 TOCTOU 静默失败或改错行
        replaced = False
        with _rooms_config_lock, _main.file_update_lock:
            old_rooms = parse_url_config(cast(str, app.state.url_config_file))
            # L-29（2026-10-02）：与新 URL 查重（POST /api/rooms 有 409 查重，PUT 此前漏检）——
            # 查重缺失时成功保存后配置出现重复 URL 行，删除/画质操作命中不确定。
            # 排除 old_url 自身：仅改画质/名字（new_url == old_url）不得被误杀。
            new_url = normalize_url(req.url)
            if any(r["url"] == new_url and r["url"] != old_url for r in old_rooms):
                raise HTTPException(409, i18n_module.tr("直播间已存在"))
            # 找到匹配行（含注释状态）
            for r in old_rooms:
                if r["url"] == old_url:
                    old_raw = cast(str, r["raw_line"]).rstrip("\n").rstrip("\r")
                    prefix = "# " if not r["enabled"] else ""
                    new_raw = (prefix + new_line) if prefix else new_line
                    # MIN-2243（2026-09-22）：update_file 的契约是「失败时返回 old_str」
                    # （config_io.update_file 读取失败/未写入分支的 `return old_str`）。旧实现丢弃
                    # 返回值并无条件 {"ok": True}——日志/配置目录只读、文件被占用或磁盘满时面板
                    # 提示「已保存」而文件字节未变。
                    # 与 SEV-05 的 delete_room 同口径：返回值只作**负信号**（返回 old_str 即失败），
                    # 最终裁决以**重新解析文件**为准（目标 URL 的行内容真的变了才算成功）。
                    _ = _main.update_file(
                        cast(str, app.state.url_config_file),
                        old_str=old_raw,
                        new_str=new_raw,
                    )
                    after = parse_url_config(cast(str, app.state.url_config_file))
                    target = next((rr for rr in after if rr["url"] == normalize_url(req.url)), None)
                    if target is None or cast(str, target["raw_line"]).rstrip("\n").rstrip("\r") != new_raw:
                        _log_internal_error(_ROOM_UPDATE_ERROR_CODE)
                        raise HTTPException(500, _ROOM_UPDATE_ERROR_CODE)
                    replaced = True
                    break
        if not replaced:
            raise HTTPException(404, i18n_module.tr("未找到原直播间"))
        return {"ok": True}

    @_route(app, ["DELETE"], "/api/rooms")
    def delete_room(url: str = "") -> dict[str, object]:
        url = normalize_url(url)
        import main as _main

        # 2026-09-12 审查 6.6：与 add_room 同款双锁保护「查行 + 删行」窗口
        with _rooms_config_lock, _main.file_update_lock:
            rooms = parse_url_config(cast(str, app.state.url_config_file))
            for r in rooms:
                if r["url"] == url:
                    # SEV-05 调用侧（协调契约）：config_io.delete_line 现在返回 bool
                    # （True = 真的删掉了一行）。旧实现丢弃返回值、无条件回报 {"ok": true}，而它在
                    # CRLF 文件上因整行精确比较失配而静默 no-op —— Windows 主平台必然发生：面板提示
                    # 删除成功、房间继续录制并占盘占并发槽，故障完全不可观测。负信号 + 重新解析裁决
                    # 的口径与 update_room 的 MIN-2243 完全一致。
                    removed = _main.delete_line(cast(str, app.state.url_config_file), cast(str, r["raw_line"]))
                    remaining = parse_url_config(cast(str, app.state.url_config_file))
                    still_there = any(rr["url"] == url for rr in remaining)
                    if still_there or removed is False:
                        _log_internal_error(_ROOM_DELETE_ERROR_CODE)
                        raise HTTPException(500, _ROOM_DELETE_ERROR_CODE)
                    return {"ok": True}
        raise HTTPException(404, i18n_module.tr("未找到直播间"))

    @_route(app, ["POST"], "/api/rooms/toggle")
    def toggle_room(req: RoomToggle) -> dict[str, object]:
        url = normalize_url(req.url)
        import main as _main

        # 2026-09-12 审查 6.6：与 add_room 同款双锁保护「查行 + 改注释前缀」窗口
        with _rooms_config_lock, _main.file_update_lock:
            rooms = parse_url_config(cast(str, app.state.url_config_file))
            for r in rooms:
                if r["url"] == url:
                    old_raw = cast(str, r["raw_line"]).rstrip("\n").rstrip("\r")
                    content = old_raw.lstrip("#").strip()
                    new_raw = content if req.enable else "# " + content
                    # MIN-2243（2026-09-22）：与 update_room 同款——不再无条件回报成功。写入失败
                    # （只读/占用/磁盘满）时旧实现仍回 {"ok": true, "enabled": ...}，面板显示状态翻转
                    # 而文件字节未变，房间继续按旧状态录制（占并发槽与磁盘）。
                    _ = _main.update_file(
                        cast(str, app.state.url_config_file),
                        old_str=old_raw,
                        new_str=new_raw,
                    )
                    after = parse_url_config(cast(str, app.state.url_config_file))
                    target = next((rr for rr in after if rr["url"] == url), None)
                    if target is None or cast(str, target["raw_line"]).rstrip("\n").rstrip("\r") != new_raw:
                        _log_internal_error(_ROOM_UPDATE_ERROR_CODE)
                        raise HTTPException(500, _ROOM_UPDATE_ERROR_CODE)
                    return {"ok": True, "enabled": req.enable}
        raise HTTPException(404, i18n_module.tr("未找到直播间"))

    # 按房间切换画质：与 GUI 画质监控页「切换画质」菜单共用 update_room_quality 落盘
    # （「画质,URL,主播: 名称」行格式），下一轮检测循环生效；两端的切换互相同步。
    @_route(app, ["PUT"], "/api/rooms/quality")
    def change_room_quality(req: RoomQualityUpdate) -> dict[str, object]:
        url = normalize_url(req.url)
        quality = (req.quality or "").strip()
        try:
            validate_room_target(req.url, quality)
        except ValueError as e:
            raise HTTPException(422, str(e)) from e
        # 白名单校验：与 GUI 下拉一致仅放行内置档位，杜绝写入永远不生效的档位名
        # （SEV-02 后 validate_room_target 内已含同款判定，此处保留以给出本端点的 422 文案）
        if quality and quality not in BUILTIN_QUALITIES:
            raise HTTPException(422, i18n_module.tr("未知画质档位: {quality}", quality=quality))
        import main as _main

        # 持锁与 add_room / 录制主循环的 update_file 互斥，避免「查房间 + 改画质段」的读改写窗口内
        # 被他方写回覆盖（update_room_quality 自身无锁，依赖调用方串行化）
        with _rooms_config_lock, _main.file_update_lock:
            rooms = parse_url_config(cast(str, app.state.url_config_file))
            if not any(r["url"] == url for r in rooms):
                raise HTTPException(404, i18n_module.tr("未找到直播间"))
            changed = update_room_quality(cast(str, app.state.url_config_file), url, quality)
        return {"ok": True, "changed": changed}

    # 画质选项：WEB 直播间设置的画质下拉与 GUI 画质监控的切换菜单共用同一份列表，
    # 落地 config.ini [录制设置]/自定义画质选项(逗号分隔)，保证两端选项一致。
    @_route(app, ["GET"], "/api/rooms/qualities")
    def list_quality_options() -> dict[str, object]:
        # builtin 一并返回，前端「添加画质」候选列表不必再硬编码一份档位名
        return {
            "options": read_quality_options(cast(str, app.state.config_file)),
            "builtin": list(BUILTIN_QUALITIES),
        }

    @_route(app, ["PUT"], "/api/rooms/qualities")
    def update_quality_options(req: QualityOptionsUpdate) -> dict[str, object]:
        try:
            validate_config_target(QUALITY_OPTIONS_SECTION, QUALITY_OPTIONS_KEY, ",".join(req.options))
        except ValueError as e:
            raise HTTPException(422, str(e)) from e
        # H-6：持引擎配置锁写 config.ini（write_quality_options 内部另有串行锁），
        # 避免与主循环热加载读/其他 Web 写并发交错
        import main as _main

        with _main.file_update_lock:
            options = write_quality_options(cast(str, app.state.config_file), req.options)
        return {"ok": True, "options": options}

    @_route(app, ["GET"], "/api/config")
    def get_config() -> dict[str, dict[str, str]]:
        # MID-34：同步 def（走线程池）——read_config_safe 是全量 configparser 解析。
        return read_config_safe(cast(str, app.state.config_file))

    @_route(app, ["PUT"], "/api/config")
    def update_config(req: ConfigUpdate) -> dict[str, object]:
        # 2026-09-12 审查 C-1：Pydantic 默认不 strip 字段，key 首尾空白可绕过黑名单的精确匹配、而
        # web_config 行匹配正则的 \s* 仍命中真实配置行（前缀捕获含尾空白），构成未认证 RCE；判定与
        # 写入前统一规范化（str.strip 覆盖半角/全角空格等 Unicode 空白），并用规范化后的值写入，
        # 保证黑名单判定与行匹配共用同一 key。
        key = req.key.strip()
        section = req.section.strip()
        # SEV-04 主修复：入口处**一次**归一，Web 节的**全部**判定都用它。旧代码只对危险键黑名单做
        # casefold，而 CR-08 的防锁死/防清空、口令哈希化、改密吊销 token 三处守卫全是大小写敏感的
        # 精确比较。configparser 的 option 本就大小写不敏感（且 _key_line_pattern 带 IGNORECASE），
        # 于是写入 WEB_PASSWORD 命中**同一行配置**却跳过全部三项守卫：明文密码落盘、旧 token 不失效
        # （「改密踢人」这一泄露兜底失效）、以及用 WEB_AUTH_ENABLE 绕开目标态判定开关认证 → 面板接管。
        key_norm = key.strip().lower()
        # 节名：configparser 的 section 大小写敏感，但写错大小写的节本就命中不了 [Web] 行
        # （update_config_line 走精确比较后返回 False），故此处按不敏感处理只会更严不会更松。
        is_web_section = section.strip().lower() == "web"
        # 危险配置键（可致远程命令执行）任何认证状态下都禁止修改（casefold：与行匹配的 IGNORECASE 同强度）
        if key.casefold() in _DANGEROUS_CONFIG_KEYS_FOLDED:
            raise HTTPException(403, i18n_module.tr("该配置项不允许通过 Web 修改"))
        # CR-08：对目标态做整体判定。旧实现只挡了「认证已开启时清空密码」一个方向，反向路径完全敞开
        # ——认证关闭（出厂默认）时任何能访问面板的人都可写入自己掌握的 web_password 再打开
        # web_auth_enable 直接接管面板（且写密码会触发下方 _tokens.clear() 踢掉全部在线会话）；或只把
        # web_auth_enable 置 true 而密码为空，使全部 /api/* 返回 401、/api/login 直接 500，面板被
        # 永久锁死，只能手工编辑 config.ini 恢复。
        current_cfg: dict[str, str | int | bool] | None = None
        if is_web_section and key_norm in ("web_auth_enable", "web_password", "web_host"):
            # 判定基准必须是**磁盘现值**（read_web_config），不能用 _read_web_config_cached：两端读同
            # 一份缓存时，「缓存 ≠ 现实」这一前提在写侧根本无从显现，下面两道守卫会变成死分支。
            # [历史注] 2026-09-23 MIN-2245 曾把 /api/login 的缓存顺手接到这里，实测期望 403 实得 200
            # （tests/test_web_api.py::TestInsecureBindInvariantUsesRealAddress
            # ::test_loopback_web_host_write_blocked_when_config_cache_says_auth_on 转红）。
            # 性能理由也不成立：缓存是为每请求都走的中间件准备的，这里是低频写接口——宁可多读一次盘，
            # 也不依据可能被陈旧缓存说服的乐观态放口令/认证/监听面过去（同 SEV-N03/MID-2241 取向）。
            current_cfg = dict(read_web_config(cast(str, app.state.config_file)))
            _currently_enabled = cast(bool, current_cfg["web_auth_enable"])
            # `_current_pwd` 的求值点从本行下移到下面的消费处（else 分支）：它只被 web_auth_enable /
            # web_password 的目标态判定消费，写在 if 之前会让**写 web_host 这条从不关心口令的路径**
            # 依赖「配置视图里存在 web_password 键」。该依赖 2026-09-23 确实炸过一次（同一用例以
            # KeyError: 'web_password' 转红，本应 403 的写入变成 500）；现基准已换回 read_web_config、
            # 键必然存在，但不回收这个惰性求值——「不消费的值不该出现在会抛异常的路径上」与基准选
            # 哪个无关。
            if key_norm == "web_host":
                # SEV-N03（2026-09-21）：对**可写的判定基准本身**施加目标态校验。web_host 既不命中
                # is_sensitive_item 也不在危险键黑名单里，于是不变量可被两步写入旁路：① 写
                # web_host=127.0.0.1（无守卫）② 写 web_auth_enable=false（旧判定看的是刚写进去的
                # 假回环值 → 放行）。中间件那半已改为只认实际绑定地址（本条不能再旁路它），这里补
                # 第二道是为了不把「配置比现实乐观」的状态放出去：认证已关闭时把监听地址改写成与真实
                # 绑定不同类的回环值，等于给下一次重启预置一个「无认证 + 看起来安全」的配置，而下次
                # 重启前用户看到的仍是被 403 的面板——两边都对不上账。
                # 只判这一个方向（配置比现实乐观）。反向（实际绑回环、配置写 0.0.0.0）不拦：中间件按
                # 现实（回环）判定、没有旁路可言，且下一次重启时 web.py 的启动检查会拒绝「无认证 +
                # 非回环」这一配置组合，不会静默开放。放开这一侧是为了不打死「本机调试时预填 0.0.0.0、
                # 准备下次开放」这类正常编辑。
                _bind_host = _guard_bind_host(app, current_cfg)
                if not _currently_enabled and not _insecure_bind_allowed():
                    if is_loopback_bind_host(req.value) and not is_loopback_bind_host(_bind_host):
                        raise HTTPException(
                            403,
                            _insecure_bind_detail(
                                i18n_module.tr("不允许把 web_host 改写为回环地址"),
                                i18n_module.tr(
                                    "改这个键不会让进程收回已监听的地址、只会让配置比现实更乐观（伪安全态）；"
                                    "请先开启 Web 认证，或改完后重启本进程使监听地址与配置一致"
                                ),
                                _bind_host,
                            ),
                        )
            else:
                # 目标态判定：外层条件已把取值域限定在 web_auth_enable / web_password 两键
                _current_pwd = str(cast(object, current_cfg.get("web_password") or "")).strip()
                if key_norm == "web_auth_enable":
                    _target_enabled = parse_config_bool(req.value, False)
                    _target_pwd = _current_pwd
                else:
                    _target_enabled = _currently_enabled
                    _target_pwd = req.value.strip()
                if _target_enabled and not _target_pwd:
                    raise HTTPException(400, i18n_module.tr("开启 Web 认证必须同时设置 web_password"))
                # SEV-04：把「认证降级」当作敏感变更拒绝——非回环监听地址下不允许把 web_auth_enable
                # 写成 false。旧语义下这一个写请求就能把「已开认证的 0.0.0.0 部署」变成「无认证 +
                # 全网卡监听」且无需重启，/api/config、/api/logs、/api/files、房间写入随之全开。
                # 中间件另有每请求的同一不变量兜底，这里先给 403 是为了让调用方拿到**可行动的**原因，
                # 而不是事后一串 403。破例仍走 web.py 的 DOUYIN_WEB_ALLOW_INSECURE=1（与启动检查同源）。
                # [历史注] SEV-N03（2026-09-21）前判定基准是 current_cfg["web_host"]，现换成
                # _guard_bind_host(app, ...) = 进程实际绑定地址，并在文案里报出该地址。
                if key_norm == "web_auth_enable" and not _target_enabled:
                    _bind = _guard_bind_host(app, current_cfg)
                    if not is_loopback_bind_host(_bind):
                        if not _insecure_bind_allowed():
                            raise HTTPException(
                                403,
                                _insecure_bind_detail(
                                    i18n_module.tr("不允许关闭 Web 认证"),
                                    i18n_module.tr(
                                        "请先在 config.ini 把 web_host 改为 127.0.0.1 并重启本进程"
                                        "（判定以进程实际监听地址为准，只改配置不重启不生效）"
                                    ),
                                    _bind,
                                ),
                            )
        # 认证开启时禁止清空密码：空密码 + 开启认证会让 login 直接 500，面板自锁
        if is_web_section and key_norm == "web_password" and not req.value.strip():
            if current_cfg is None:
                current_cfg = read_web_config(cast(str, app.state.config_file))
            if cast(bool, current_cfg["web_auth_enable"]):
                raise HTTPException(400, i18n_module.tr("请先关闭 Web 认证再清空密码"))
        value = req.value
        # MID-2236（2026-09-22）：读写两侧的敏感判据此前**分叉**——读侧 web_config.read_config_safe 判
        # `is_sensitive_item(section, key) or _looks_like_secret_value(value)`，写侧（此处，修复前）只有
        # 前一半。后果：键名不含凭据关键词、但值本身是凭据的项（推送接口链接 ?key=xxx、带账密的代理
        # 地址 http://user:pass@host、bark 设备地址…）在面板上是 '***' 掩码，后端却**不认**它是敏感项
        # → 用户把掩码删空提交（或脚本直接 PUT 空串/字面 '***'）会被当作普通配置写入，把真实凭据覆盖
        # 成空/掩码，而备份副本已按 CR-07 脱敏、无从恢复。修法：写侧复用**同一份**读侧判据（唯一事实
        # 来源在 web_config，不在此复制第二份实现），并对「掩码/空值」两种情况都生效。
        # 值形态判定只作用于**非空**入参（空值没有 URL 形态可判），故下面的 old_value 回退是必要的：
        # 否则「把值型凭据清空」这一步仍能从缝里溜过——那正是本条要堵的洞。
        # [历史注] old_value 最初取自 read_config_safe，实测**失效**：值型凭据回显的正是 SENSITIVE_MASK
        # → old_value == '***' → _looks_like_secret_value('***') 恒为 False，本分支在真实 PUT 路径上被
        # 整条放行（期望 400 实得 200 {"ok":true}、真实凭据被 '   ' 覆盖）。回归锁
        # tests/test_regression_2026_09_22_web_g.py::TestWriteSideSensitiveParity
        # ::test_blank_write_to_value_shaped_secret_rejected。现改为从 configparser 直接读**未脱敏**
        # 原始值：判据要的是「这一格原本是不是凭据」，脱敏后的副本恰恰丢掉该信息。读取失败（文件缺失/
        # 损坏）时降级为空串、不改变写入语义——后续 update_config_line 本就会返回 False 并给出 404。
        old_value = ""
        try:
            _raw_parser = configparser.ConfigParser(interpolation=None)
            _ = _raw_parser.read(cast(str, app.state.config_file), encoding=TEXT_ENCODING)
            if _raw_parser.has_option(section, key):
                old_value = str(_raw_parser.get(section, key) or "")
        except Exception:
            # 配置不可读时静默降级即可（不吞掉任何安全判定），理由已在上方注释说明
            old_value = ""
        if is_sensitive_item(section, key) or _looks_like_secret_value(value) or _looks_like_secret_value(old_value):
            # MID-37（后端半边）：敏感键**不得被空值覆盖**。面板对敏感项回显的是 '***' 掩码，
            # 旧的前端只挡「原样提交 ***」，用户全选删空后提交 '' 既 ≠ '***' 也 ≠ 旧值，
            # 于是真实 cookie/token 被空串静默覆盖。与 web_password 同口径：清空敏感凭据必须走
            # 显式路径，不能由一次误操作完成。
            if not value.strip():
                raise HTTPException(
                    400, i18n_module.tr("敏感配置项不得清空：如需移除请显式填写占位值并手工编辑 config.ini")
                )
            # MID-37 残留（2026-09-21）：掩码 '***' 同样必须被服务端拦住。read_config_safe 对敏感项
            # 回显的就是 SENSITIVE_MASK，前端 saveConfig 虽会跳过原样提交的掩码，但那是**唯一**防线——
            # 任何直接打 PUT /api/config 的调用方（脚本、旧版前端、被改过的页面）都能把真实凭据覆盖成
            # 字面 '***'。后端不接受掩码，才使「跳过掩码」从必要防线降级为纯粹的省一次无谓写入。
            elif value.strip() == SENSITIVE_MASK:
                raise HTTPException(400, i18n_module.tr("敏感配置项不得以掩码值提交：请填入真实值，或保持该项不修改"))
        # ─── MID-2241 后端强制复验（2026-09-23 落地）───────────────────────────────
        # 前端 confirm（web/app.js::saveConfig）只挡得住「手滑点保存」，挡不住任何直接打
        # PUT /api/config 的一方（脚本、旧版前端、被改过的页面、拿到 bearer 却没口令的攻击者），
        # 故复验必须在服务端做：**认证当前开启**时写入 `[Web] web_auth_enable` / `web_password`
        # 必须携带能过 verify_web_password 的 reauth_password，否则 403——bearer 自此只证明
        # 「这是一个已登录会话」，不再单独证明「操作者知道口令」（关认证与改口令都是能力降级）。
        # 三条判据的取舍（各对应一种会被误伤的真实场景，改动前先读完）：
        # · **只在认证已开启时要求**：认证关闭（出厂默认）时面板对任何能访问端口的人都全开，bearer
        #   本身不构成防线、也没有可信的「当前口令」可验（web_password 通常为空），此时强复验只会把
        #   「本机用户按提示收紧/放开配置」打死；非回环绑定下的关闭态另有 SEV-04 的每请求不变量兜底。
        # · **排在敏感空值/掩码守卫之后**：`web_password='***'` 或空值属「值形态非法」，裁决必须是
        #   400 + 可行动文案（tests/test_web_api.py::TestSensitiveValueBlankRejected 钉着），让 403
        #   抢在前面会把「不要把掩码写回去」这一提示降级成笼统的权限错误。
        # · **口令比对失败不回显任何口令线索**：只回固定 detail，细节走 _log_internal_error。
        # 反向边界（不得扩到的范围）：其余 Web 键（web_host/web_port/web_allowed_hosts…）与其他节的
        # 键一律不受本条影响，否则「改个端口也要复验」会逼人绕过面板手改文件。
        if is_web_section and key_norm in ("web_auth_enable", "web_password"):
            if current_cfg is None:
                current_cfg = dict(_read_web_config_cached(cast(str, app.state.config_file)))
            if cast(bool, current_cfg["web_auth_enable"]):
                _reauth = (req.reauth_password or "").strip()
                _stored_pwd = str(cast(object, current_cfg["web_password"]) or "")
                if not _reauth or not verify_web_password(_reauth, _stored_pwd):
                    # 只记键名与失败原因，绝不记口令（logs/ 轮转保留多份＝凭据长期落盘）
                    _log_internal_error(f"auth_reauth_denied: key={key_norm}", level="warning")
                    raise HTTPException(403, i18n_module.tr("修改 Web 认证配置必须复验当前访问口令（reauth_password）"))
        try:
            validate_config_target(section, key, value)
        except ValueError as e:
            raise HTTPException(422, str(e)) from e
        # 密码统一以 PBKDF2 哈希存储，避免明文落盘。
        # M-06（2026-09-30）：哈希前先 strip——reauth 复验用的是 strip 后的值（MID-2241），
        # 登录比对也已统一 strip；写入侧若用原文哈希，设置「首尾带空格」的口令（粘贴/输入法
        # 尾随空格是常见来源）后所有 reauth 永远 403，认证配置经面板永久自锁、只能手改文件。
        if is_web_section and key_norm == "web_password" and value.strip():
            normalized_password = value.strip()
            if not is_hashed_web_password(normalized_password):
                value = hash_web_password(normalized_password)
            else:
                value = normalized_password
        # H-6：持引擎配置锁写 config.ini，避免与主循环热加载读/其他 Web 写并发交错
        import main as _main

        with _main.file_update_lock:
            ok = update_config_line(cast(str, app.state.config_file), section, key, value)
        if not ok:
            raise HTTPException(404, i18n_module.tr("未找到对应的配置项"))
        # 密码变更后吊销所有现有 token，强制重新登录
        if is_web_section and key_norm == "web_password" and req.value.strip():
            with _tokens_lock:
                _tokens.clear()
        # 认证状态变更后必须让中间件的配置缓存失效：缓存按 mtime+size 失效，
        # 极端情况下同一秒内的等长改写不会改变 mtime（Windows FAT/粗精度时间戳），
        # 于是「关掉认证」这一安全相关的写入要到下一次改写才生效。显式失效，不留窗口。
        if is_web_section and key_norm in ("web_auth_enable", "web_password", "web_host"):
            _invalidate_web_cfg_cache()
        return {"ok": True}

    @_route(app, ["GET"], "/api/language")
    def get_language() -> dict[str, object]:
        # 当前语言 + 受支持语言列表（供前端语言选择器渲染）
        import i18n as i18n_module

        return {
            "language": i18n_module.get_language(),
            "available": i18n_module.available_languages(),
        }

    @_route(app, ["PUT"], "/api/language")
    def set_language(req: LanguageUpdate) -> dict[str, object]:
        # 即时切换语言：归一化校验 → **先**热切换本进程翻译目录 → 按**实际生效**的语言码写回 config.ini。
        # 本进程（uvicorn 与录制守护线程同进程）后续控制台/日志输出即时使用新语言；
        # main() 主循环每轮也会按配置重同步，两者一致。
        #
        # MID-52（Web 半边，2026-09-21）：旧顺序是「normalize_language → 写 config.ini → set_language」，
        # 而 i18n.set_language() 现在返回的是**实际生效**语言码（内部经 has_catalog/resolve_language 口径，
        # 目录缺失时回退，例如 PyYAML 未装则 zh_TW.yaml 加载不了 → en_US）。写请求值会把一个
        # 「本进程根本装载不到译文」的码落盘：录制子进程每轮经 resolve_language 重解析落到 en_US，
        # 于是同一部署的 GUI/面板与录制进程各说一种语言，且响应里的 language 是虚假成功。
        # 现改为「切换 → 落盘生效码 → 按生效码应答 + 回退提示」。
        import i18n as i18n_module

        if not req.language.strip() or not i18n_module.is_recognized_language(req.language):
            # 无法识别的语言值（既非受支持码也非已知别名）→ 400 而非静默回退
            raise HTTPException(400, i18n_module.tr("不支持的语言: {lang}", lang=req.language))
        normalized = i18n_module.normalize_language(req.language)
        previous = i18n_module.get_language()
        effective = i18n_module.set_language(normalized)
        # H-6：替换+补建两步经 update_or_append_config_line 持锁原子化，
        # 并持引擎配置锁与主循环热加载读互斥
        import main as _main

        with _main.file_update_lock:
            written = update_or_append_config_line(cast(str, app.state.config_file), "录制设置", "language", effective)
        if not written:
            # 写回失败必须回滚内存态：否则面板/本进程说 effective、config.ini（以及重启后的
            # 录制子进程）仍说旧码，正是要消灭的「两进程两种语言」形态的另一种达成路径。
            _ = i18n_module.set_language(previous)
            raise HTTPException(500, i18n_module.tr("语言配置写回失败"))
        return {
            "ok": True,
            # language 恒为**生效码**（前端据此更新本地语言状态，不得再按请求值回写）
            "language": effective,
            "requested": normalized,
            # 二者不等即「请求语言的目录缺失」，把回退事实显式回给调用方，不让它自行猜测
            "fallback": effective != normalized,
            # 面板可直接 toast 的回退说明；无回退时为空串（前端按 fallback 判定即可）
            "notice": (
                ""
                if effective == normalized
                else i18n_module.tr(
                    "{lang} 的翻译目录不可用，已回退为 {effective}（配置同样按 {effective} 写回）",
                    lang=normalized,
                    effective=effective,
                )
            ),
        }

    @_route(app, ["GET"], "/api/files")
    def list_files(path: str = "") -> list[dict[str, str | int | float]]:
        # MID-34：同步 def（FastAPI 自动派发到 anyio 线程池）——本端点对目录逐项
        # realpath + os.stat，大录像目录/慢盘下是纯阻塞调用。
        root = cast(str, app.state.downloads_root)
        target = os.path.realpath(os.path.join(root, path))
        if not _is_within(target, root):
            raise HTTPException(400, i18n_module.tr("非法路径"))
        if not os.path.exists(target):
            raise HTTPException(404, i18n_module.tr("路径不存在"))
        if os.path.isfile(target):
            st = os.stat(target)
            return [
                {
                    "name": os.path.basename(target),
                    "type": "file",
                    "size": st.st_size,
                    "mtime": st.st_mtime,
                    "path": path,
                }
            ]
        items: list[dict[str, str | int | float]] = []
        for name in sorted(os.listdir(target)):
            full = os.path.join(target, name)
            # 逐条解析真实路径并校验仍在 downloads 根内，跳过指向 root 之外（或
            # 逃出根目录）的符号链接，避免列目录泄露根外文件名（信息泄露）。
            resolved = os.path.realpath(full)
            if not _is_within(resolved, root):
                continue
            # 跟随符号链接 stat 时，悬空（指向不存在目标）的符号链接会抛
            # FileNotFoundError 导致整个接口 500；此处容错跳过该条目。
            try:
                st = os.stat(full)
            except OSError:
                continue
            rel = os.path.relpath(full, root).replace("\\", "/")
            items.append(
                {
                    "name": name,
                    "type": "dir" if os.path.isdir(full) else "file",
                    "size": st.st_size if os.path.isfile(full) else 0,
                    "mtime": st.st_mtime,
                    "path": rel,
                }
            )
        return items

    @_route(app, ["GET"], "/api/files/download")
    def download_file(path: str = "") -> FileResponse:
        root = cast(str, app.state.downloads_root)
        target = os.path.realpath(os.path.join(root, path))
        if not _is_within(target, root) or not os.path.isfile(target):
            raise HTTPException(400, i18n_module.tr("非法路径或文件不存在"))
        return FileResponse(target, filename=os.path.basename(target))

    @_route(app, ["GET"], "/api/logs")
    def get_logs(lines: int = 200) -> dict[str, list[str]]:
        log_file = os.path.join(cast(str, app.state.logs_dir), "streamget.log")
        if not os.path.isfile(log_file):
            return {"lines": cast(list[str], [])}
        try:
            with open(log_file, "r", encoding="utf-8", errors="ignore") as f:
                tail = deque(f, maxlen=lines)
            return {"lines": list(tail)}
        except Exception as e:
            # MID-39：日志文件被占用/权限异常时 str(e) 形如
            # "[Errno 13] Permission denied: 'D:\\...\\logs\\streamget.log'"，
            # 旧实现把它塞进 detail 并被前端原样弹成 toast —— 对局域网泄露安装绝对路径。
            # 对外只给固定 code，细节进日志（行为仍可观测：面板显示失败并能在日志里查到）。
            _log_internal_error(_LOGS_ERROR_CODE, e)
            raise HTTPException(500, _LOGS_ERROR_CODE) from e

    @_route(app, ["GET"], "/api/danmaku")
    def get_danmaku(since: int = 0) -> dict[str, object]:
        # 弹幕监控快照：rooms 为各房间统计，messages 为 seq 游标之后的增量消息。
        # 与录制引擎同进程，直接读 DanmakuMonitorHub 内存快照；异常时返回空快照而非 500，
        # 避免面板因监控旁路故障整页报错。
        # MID-34：同步 def —— snapshot() 抢的是弹幕枢纽全局锁，慢盘/写侧持锁时会排队。
        try:
            from src.danmaku_monitor import get_hub

            return get_hub().snapshot(since)
        except Exception as e:
            # MID-39：error 字段同 /api/status 口径，只给 code 不回显内部异常原文
            _log_internal_error(_DANMAKU_ERROR_CODE, e, level="warning")
            return {"rooms": [], "messages": [], "last_seq": since, "truncated": False, "error": _DANMAKU_ERROR_CODE}

    # ===== 静态资源 =====
    if _WEB_DIR.exists():
        app.mount("/web", StaticFiles(directory=str(_WEB_DIR), html=True), name="web")

        @_route(app, ["GET"], "/")
        async def index() -> FileResponse:
            return FileResponse(str(_WEB_DIR / "index.html"))

    return app


def _purge_expired_tokens() -> None:
    # 清除过期 token；自行加锁（调用方可能来自中间件，不再要求外部持锁）。
    now = time.time()
    with _tokens_lock:
        expired = [t for t, exp in _tokens.items() if exp <= now]
        for t in expired:
            _ = _tokens.pop(t, None)


# SEV-2221 / SEV-2228（2026-09-23 收敛）：**`main_loop_alive` 已从 /api/status 契约里撤下。**
# 撤下而不是留着：那版探针读的是 `main.main_loop_ticks`，而该名字在 main.py 里**从未定义、也从未
# 自增**（取证：`grep -rn main_loop_ticks main.py src/` 只命中 web_api.py 自身与 tests/），于是探针
# 恒走「计数器缺失 → 返回 None」分支、该键永不下发，前端 `s.main_loop_alive === false` 是一条
# **永不成立**的判定。更糟的是 `tests/frontend/*.mjs` 与 `tests/test_regression_2026_09_22_web_g.py`
# 都在锁这条死路径，其中两条用例（推进单调时钟后期望 False）2026-09-23 实测就已红——探针的时钟 shim
# 会永久留在 web_api 模块上（setattr 而非 monkeypatch），跨用例串扰。「有一个永不生效的存活信号」比
# 「没有该信号」更危险：它让后续排障以为停摆已被覆盖。
# 为什么不用「已真实存在的可观察量」替代（任务书允许的另一条路，实测逐个判过）：
#   · `main._recorder_thread.is_alive()` 已被 `engine_alive` 占用，再包一层是同一个量冒充两个证据；
#   · `main.monitoring` / `main.error_count` / `main.running_list` 只在房间增减或出错时变化，
#     「零变化」既可能是停摆也可能是安静运行 → 用它判活必然假红；
#   · `main.config` 的对象身份每轮被 `_hot_reload_config()` 整体替换，看着最接近「轮次进展」，但热
#     加载失败（OSError / 空配置）时它**保持不变**而主循环照旧推进——磁盘抖动即误报停摆；
#   · `display_info` / `adjust_max_request` 的节拍量都在**另外的守护线程**里，它们前进不能证明录制
#     主循环在推进（正是本条要区分的故障形态）。
# 真正的停摆判据必须来自 main 自己的轮次计数（一行 `main_loop_ticks += 1` 放在 while True 顶部），
# 而 main.py 不在本次改动所有权内 → 撤下该键并把接线点留给主会话。撤下后面板侧的「取证失败」改由两个
# **真实存在**的信号承担：`error`（采样抛错）与 `stale`（快照超时回退），见 _status_worker /
# _get_status_snapshot 与 web/app.js::updateStatusWarning。
def _read_engine_status() -> dict[str, object]:
    # 状态采样的唯一 seam：保留本函数而不是内联进 _status_worker，就是给未来的轮次探针留接线点——
    # 一旦 main.py 侧补上轮次计数，在此按「非 None 才挂键」的口径重新接上，并同时恢复前端
    # updateStatusWarning 里对应的 === false 判定与四语目录键。
    import main

    return cast("dict[str, object]", main.get_status())


def _status_worker(fetch_since: float) -> dict[str, object]:
    # 线程体：采样 + 写缓存 + 清「进行中」标记。**任何异常都在本函数内消化**，
    # 绝不把内部异常原文（绝对路径 / Errno）带到响应里（MID-39）。
    # 「进行中」标记必须在线程自己的 finally 里清，不能在等待方清：
    # asyncio.wait_for 超时只会取消「等待」，取消不了已经跑起来的线程——
    # 若由等待方清标记，下一个 2s 轮询又会起一条线程去撞同一块挂起的盘，线程无界增长。
    # 只在自己的租约仍是当前租约时才清（超时后可能已有第二次采样接管了门）。
    global _status_inflight, _status_inflight_since, _status_cache, _status_cache_at
    try:
        try:
            snapshot = _read_engine_status()
        except Exception as e:
            _log_internal_error(_STATUS_ERROR_CODE, e)
            return {"error": _STATUS_ERROR_CODE}
        with _status_lock:
            _status_cache = snapshot
            _status_cache_at = time.monotonic()
        return snapshot
    finally:
        with _status_lock:
            if _status_inflight and _status_inflight_since == fetch_since:
                _status_inflight = False


async def _get_status_snapshot() -> tuple[dict[str, object], bool]:
    # 返回 (状态快照, 是否为陈旧值)。
    # MID-34 的三层配合：
    # ① TTL 内直接复用缓存 —— 磁盘容量/错误数这类展示值本就是秒级变化，2s 窗口对面板无损，
    #    却把「每 2s 一次 shutil.disk_usage + 两把跨线程锁」从事件循环上彻底摘掉；
    # ② 单飞门 —— 已有一次采样在飞（可能正卡在挂起的网络盘上）时立即回陈旧值，
    #    绝不叠第二条线程，否则每个轮询/每个 SSE 连接都会再撞一次；
    # ③ wait_for 超时 —— 超时只让**等待**结束，线程照旧跑完并写缓存，
    #    于是「慢」体现在数据新鲜度（stale:true）而不是整个面板无响应。
    # 注：3.11 起 asyncio.TimeoutError 即内建 TimeoutError，故只捕一个（本仓下限 3.14）。
    global _status_inflight, _status_inflight_since
    now = time.monotonic()
    with _status_lock:
        cached, cached_at = _status_cache, _status_cache_at
        if cached is not None and (now - cached_at) < _STATUS_TTL_SECONDS:
            return cached, False
        # 租约：进行中的采样超过 _STATUS_INFLIGHT_LEASE 仍未回来（磁盘彻底挂死）时，
        # 放一次新的采样过去，避免单飞标记把面板永久钉在陈旧快照上。
        inflight = _status_inflight and (now - _status_inflight_since) < _STATUS_INFLIGHT_LEASE
        if not inflight:
            _status_inflight = True
            _status_inflight_since = now
    fallback: dict[str, object] = cached if cached is not None else {"error": _STATUS_ERROR_CODE}
    if inflight:
        return fallback, True
    with _status_lock:
        fetch_since = _status_inflight_since
    try:
        snapshot = await asyncio.wait_for(asyncio.to_thread(_status_worker, fetch_since), _STATUS_WAIT_SECONDS)
        return snapshot, False
    except TimeoutError:
        return fallback, True
    except Exception as e:
        # 理论上不可达（_status_worker 内部已吞掉 Exception），留此兜底避免陈旧标记卡死
        _log_internal_error(_STATUS_ERROR_CODE, e)
        return fallback, True


# WD-06：鉴权中间件用的配置缓存（mtime + size 失效）。
# 缓存的 key 含 config_file 路径，便于测试注入不同配置文件时互不串用。
# 值类型与 read_web_config 的返回注解保持一致（str | int | bool），
# 否则缓存回填时会因 dict 值类型不变性报 mypy assignment/return-value 错误
_web_cfg_cache: tuple[str, float, int, dict[str, str | int | bool]] = ("", -1.0, -1, {})


def _invalidate_web_cfg_cache() -> None:
    # 强制中间件下一次请求重新读 config.ini（SEV-04：认证/监听地址变更必须即刻生效）。
    # 缓存按 (path, mtime, size) 失效，正常写盘必然改变 mtime/size；但若文件系统时间戳粗
    # 且改写后大小恰好相同（例如 true→fals 之类的等长变更），mtime 精度不足时会命中旧值。
    # 安全相关的键不吃这个概率，直接清。
    global _web_cfg_cache
    with _web_cfg_cache_lock:
        _web_cfg_cache = ("", -1.0, -1, {})


def _read_web_config_cached(config_file: str) -> dict[str, str | int | bool]:
    # 读不到 stat（文件被删等）时退回直接读取，保证行为与原实现一致
    try:
        st = os.stat(config_file)
    except OSError:
        return read_web_config(config_file)
    global _web_cfg_cache
    with _web_cfg_cache_lock:
        path, mtime, size, cached = _web_cfg_cache
        if path == config_file and mtime == st.st_mtime and size == st.st_size:
            return cached
    cfg = read_web_config(config_file)
    with _web_cfg_cache_lock:
        _web_cfg_cache = (config_file, st.st_mtime, st.st_size, cfg)
    return cfg


def _is_same_origin(
    request: Request,
    cfg: dict[str, str | int | bool],
    bind_host: str,
    bind_port: int,
) -> bool:
    # WD-08：判断非幂等请求是否同源。无 Origin 头（curl/脚本/同源导航）放行——浏览器对跨域写请求
    # 必带 Origin，缺失即非浏览器场景，不属于本轮要拦的 CSRF 面。
    #
    # MID-36：期望值改由**服务端配置**推导，不再拿请求自带的 Host 当基准。旧实现
    # `origin in (f"http://{host}", f"https://{host}")` 的 host 取自 Host 头，于是 DNS 重绑定下
    # （attacker.tld → 127.0.0.1）Origin 与 Host 必然相等，判定形同不存在。另外 Sec-Fetch-Site 由
    # 浏览器强制覆盖、跨站页面无法伪装成 same-origin，故显式 cross-site 直接判否（缺该头不作为
    # 放行依据，避免非浏览器场景被误伤）。
    #
    # MID-N42（2026-09-21）：Origin 不再复用为 Host 头设计的 web_config.is_host_allowed。那套规则
    # 放行「任何 IP 字面量」与「任何无点单标签名」，且 _strip_host_port 会把端口丢掉——对 Host 头
    # 成立（重绑定需要注册域名、以 IP 访问面板是常态），对 Origin 不成立：http://192.168.1.47/
    # （局域网里另一台设备的页面）与 http://localhost:3000/（本机任意 dev server）都会被判同源，
    # 而认证关闭（出厂默认）时这条判定是写接口唯一防线。现改判**host 与端口都命中服务端推导的期望
    # 集合**（实际绑定 host:实际端口 + 回环族 + web_allowed_hosts 显式登记的 host[:port]），判定本体
    # 在 web_config.is_origin_allowed；Host 头那条继续用 is_host_allowed、行为不变（两套装进一个函数
    # 就会有一侧退化，MID-36 那条防线不能让 Origin 修复顺带砍掉）。
    if request.headers.get("Sec-Fetch-Site", "").strip().lower() == "cross-site":
        return False
    origin = request.headers.get("Origin")
    if not origin:
        return True
    return is_origin_allowed(origin, cfg, bind_host=bind_host, bind_port=bind_port)


def _api_locked_out_by_insecure_bind(cfg: dict[str, str | int | bool], path: str, bind_host: str) -> bool:
    # SEV-04：/api/* 的「非回环 + 无认证」不变量（每请求判定）。
    # 只作用于 API：静态页与 /health 仍放行，否则运维既打不开面板也看不到告警，
    # 只能靠改文件恢复——那正是本仓多处「只能手工编辑 config.ini 恢复」的成因。
    #
    # SEV-N03 修复（2026-09-21，CODE_REVIEW_2026-09-21）：第三个参数 bind_host 是**进程实际
    # 绑定地址**（调用侧经 _guard_bind_host 取值），不再读 cfg["web_host"]——后者可经
    # PUT /api/config 改写，两步写入即可旁路整条不变量。
    # 本函数只在内部做判定、不加锁也不改状态；调用方（鉴权中间件）负责每请求传新 cfg。
    if not path.startswith("/api/"):
        return False
    if cast(bool, cfg["web_auth_enable"]) or _insecure_bind_allowed():
        return False
    return not is_loopback_bind_host(bind_host)


def _is_within(child: str, parent: str) -> bool:
    # 校验 child 路径在 parent 目录内（防穿越）。
    try:
        return os.path.commonpath([child, parent]) == parent
    except ValueError:
        return False
