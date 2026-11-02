# src/web_api.py
# Web 管理面板 Starlette 应用：认证、路由、静态资源。
#
# 鉴权模型总览（web_api 与 web/ 前端共用）：
# ① 认证开关：config.ini [Web].web_auth_enable=true 时开启；关闭时所有 /api/* 公开访问（局域网用）
# ② 密码存储：首次登录时明文自动升级为 PBKDF2-HMAC-SHA256 哈希（盐随机，迭代 200k）
# ③ Token：secrets.token_urlsafe(32) 生成 256-bit bearer，过期时间由 web_token_expiry 控制
#    （出厂默认 86400 秒 = 24 小时，以 config.ini 与 WEB_DEFAULTS 为准；改它影响所有既有部署的登录频率）
# ④ 登录限流：单 IP 滑动窗口 5 次失败/300 秒即 429，仅信任 web_trusted_proxy 列表内代理的 XFF；
#    另有与来源键无关的全局失败预算 40 次/300 秒，以及免鉴权端点的 per-IP 预算 240 次/60 秒。
# ⑤ 密码变更：吊销全部 token，强制重登；认证开启时禁止清空密码（防自锁）。Web 节敏感键
#    （web_auth_enable / web_password）做目标态对称校验——开启认证必须有非空密码，否则面板被锁死。
# ⑥ 危险配置键：黑名单（_DANGEROUS_CONFIG_KEYS）即使 auth 关闭也禁止 Web 写入（防 RCE）
# ⑦ 认证开关为唯一分流依据：关闭时全放行；开启时只有白名单路径放行，其余一律需 Bearer，
#    与 HTTP method 无关——读接口同样拦，跨源读取也能拉走配置与日志。
#    白名单（中间件 elif 分支逐条枚举）：/api/login、/api/logout、/api/auth/status、
#    /health、/、/web、/web/*、/favicon.ico。
# ⑧ 非幂等请求校验 Origin 同源（防无认证时的跨站写）；/api/logout 支持单点吊销当前 bearer；
#    配置读取带 mtime+size 缓存（避免每请求全量解析 config.ini）
# ⑨ 响应头：X-Content-Type-Options: nosniff（防 MIME 嗅探）、X-Frame-Options: DENY（防点击劫持）、
#    CSP（见中间件末尾）；GET /api/status 在认证关闭时返回 auth_required=false 与告警供前端提示
# ⑩ 安全不变量（改动时逐条核对）：
#    · 房间写入口裁决唯一：校验下沉到 web_config.format_url_line（URL_config.ini 唯一写入口），
#      add/update/quality 三个接口不可能再次分叉；
#    · Host/Origin 白名单：同源判定不信任请求自带的 Host，改由服务端配置推导允许名单，并在
#      每个请求上重跑「非回环 + 无认证」不变量；判定基准取 create_app(bind_host/bind_port)
#      传入的实际绑定值，不读可被 PUT /api/config 改写的 web_host/web_port；Host 与 Origin 是
#      两套名单（Host 放行 IP 字面量 / 无点单标签名，Origin 要 host 与端口双命中）；
#    · 端点不占事件循环：阻塞的磁盘 IO / 跨线程锁 / 日志归档一律走线程池，状态快照另加 TTL 缓存
#      + 单飞 + 超时回陈旧值；
#    · 对外不回显内部异常：绝对路径 / Errno 细节只写日志，响应里只给固定 error code；
#    · 敏感配置写入三重拒绝：命中 is_sensitive_item 的键既不接受空值、也不接受面板回显用的
#      字面掩码 '***'；认证开启时写认证两键还须复验口令——前端跳过掩码只是省事，不是防线；
#    · 会被本进程发出去的 config 值一律收口：推送接口链接 / ntfy 地址 / 代理地址 / SMTP 服务器的
#      scheme 与目标网段校验挂在 validate_config_target（config.ini 写侧唯一入口）上，多目标
#      逗号分隔须逐段过判；
#    · 认证两键的写入必须复验口令：认证已开启时写 web_auth_enable / web_password 未携带可验过的
#      reauth_password 即 403——bearer 只证明「已登录」，不证明「知道口令」。该守卫不得用
#      _read_web_config_cached，必须读磁盘现值；
#    · 语言切换按生效码落盘：PUT /api/language 先 i18n.set_language() 再写 config.ini，保证
#      面板进程与录制子进程不会各说一种语言；
#    · main_loop_alive 已从 /api/status 契约撤下（恒不下发），面板改由 error/stale 两个真实信号
#      承担「取证失败」（见 _read_engine_status 上方说明）。
# pyright: reportUnusedFunction=none, reportCallInDefaultInitializer=none
from __future__ import annotations

import asyncio
import base64
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
from src.logger import logger
from src.ui_icons import (
    MAX_ICON_BYTES,
    WEB_ICON_KEY,
    WEB_SECTION,
    current_icon_path,
    install_icon_bytes,
    load_icon_preference,
    probe_ico_sizes,
    save_icon_preference,
    validate_icon_bytes,
)
from src.web_models import (
    ConfigUpdate,
    IconUpload,
    LanguageUpdate,
    LoginRequest,
    QualityOptionsUpdate,
    RecordingToggle,
    RoomCreate,
    RoomQualityUpdate,
    RoomToggle,
    RoomUpdate,
)

# ─── Starlette 接线层 ─────────────────────────────────────────────────────────
# Starlette 不提供 FastAPI 的参数注入（模型自动解析 / Query 自动绑定 / dict→JSON 自动序列化），
# 这里用 `_route` 装饰器复刻等价语义：① JSON body 解析成 web_models dataclass 作为模型参数；
# ② 查询串按默认值回填、按上下界夹取；③ 同步 def 端点经 run_in_threadpool 派发到线程池（与 FastAPI
# 行为一致，避免阻塞事件循环）；④ 非 Response 返回值统一包成 JSONResponse。业务逻辑与旧实现逐字一致。
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
    IconUpload,
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


# JSON 请求体大小上限。认证关闭（出厂默认）时局域网任一主机可单请求超大 JSON 耗内存
# （json.loads 全量物化后才谈得上校验），解析前先按 Content-Length 拒绝。面板全部请求体
# （登录口令/房间/配置节）远小于该值。
_JSON_BODY_MAX_BYTES = 1 * 1024 * 1024


async def _read_json_body(request: Request) -> object:
    # 解析 JSON 请求体；非法/空体统一转 422（对齐旧 pydantic 的 422 契约）。仅当端点有模型参数时
    # 适配器才会调用，GET/无 body 端点不会走到这里。
    # 上限在无 Content-Length 时同样成立：request.json() 会把无上限的 chunked 流整体物化进内存，
    # 故用 request.stream() 逐块计量；超限沿用预检同一 413 出口与「请求体过大」msgid，不新增目录键。
    # [历史注] 旧注释称「Content-Length 缺失时不拦、由 Starlette 流式读取兜底」，已被证伪。
    content_length = request.headers.get("content-length", "")
    if content_length.isdigit() and int(content_length) > _JSON_BODY_MAX_BYTES:
        raise HTTPException(status_code=413, detail=i18n_module.tr("请求体过大"))
    try:
        chunks: list[bytes] = []
        total = 0
        async for chunk in request.stream():
            total += len(chunk)
            if total > _JSON_BODY_MAX_BYTES:
                raise HTTPException(status_code=413, detail=i18n_module.tr("请求体过大"))
            chunks.append(chunk)
        return json.loads(b"".join(chunks))
    except HTTPException:
        # 超限的 413 不得被下面的 except Exception 退成 422——两条出口的语义不同
        raise
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
    DEFAULT_QUALITY,
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
# 与来源地址无关的全局失败预算。按 IP 计数有两个对称失效面：攻击者换一个键就换一个窗口（本机反代
# 下 XFF 可伪造时尤其明显）；Docker 端口映射把真实用户的 client.host 收敛成网关地址，5 次失败即把
# 所有人锁在登录页外。全局预算只封顶「整站每秒能承受多少次口令校验」、与键粒度无关，故既压住爆破
# 吞吐，又不会因单键聚合而误伤合法用户到 5 次。
# 条目带来源 (失败时刻, client_ip)：纯时间戳形态下「成功登录回收自身份额」无从谈起，持续打错密码会让
# 全局预算把所有合法用户 429 到窗口滑完（旧口径见 login 成功分支的 [历史注]）。判定与预算语义不变
# ——仍是跨来源合计 40 次/300 秒，窗口滑出回收逻辑逐字不变。
_GLOBAL_LOGIN_FAILURES: deque[tuple[float, str]] = deque(maxlen=512)
_LOGIN_GLOBAL_MAX_FAILURES = 40

# ─── 免鉴权端点的 per-IP 预算 ─────────────────────────────────────
# 上面的限流只管 /api/login 的失败计数，而白名单里的 /api/auth/status 与 /health 恒可访问、毫无
# 预算：能访问端口 = 能零成本、无限次驱动面板的读路径。阈值刻意放宽到「正常使用远够不到」——面板
# 启动只拉一次，探活/CI 是秒级个位数，240 次/分钟 ≈ 4 次/秒已足以把「无限放大」压成「有界成本」。
# 刻意不给全局预算：这两条极便宜（缓存命中即一次 os.stat），按 IP 封顶只为挡单点放大；Docker 端口
# 映射下真实用户收敛到同一网关地址，全局预算会集体误伤。
_PUBLIC_BUDGET_WINDOW = 60.0
_PUBLIC_BUDGET_MAX = 240
# 键集合上限（同 _DENIED_HOSTS_SEEN_MAX 形态）：窗口回收只清「最后一条已出窗」的键，持有 IPv6 /32
# 前缀的攻击者可轮换源地址让 dict 无界增长；到限整表清空（预算重置）换取有界内存，接受这一宽松化。
_PUBLIC_BUDGET_MAX_KEYS = 64
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
            # 新键入库前先查键数上限（回收后的残余仍无界增长的那条路在这里封死）
            if len(_PUBLIC_BUDGET) >= _PUBLIC_BUDGET_MAX_KEYS:
                _PUBLIC_BUDGET.clear()
            hits = deque(maxlen=_PUBLIC_BUDGET_MAX + 8)
            _PUBLIC_BUDGET[client_ip] = hits
        while hits and now - hits[0] > _PUBLIC_BUDGET_WINDOW:
            hits.popleft()
        if len(hits) >= _PUBLIC_BUDGET_MAX:
            return True
        hits.append(now)
        return False


# 危险配置键黑名单：允许通过 Web 修改等价于远程命令执行，任何认证状态下都禁止写入。
# 三项非命令键同样列入（翻转或写入即旁路前述守卫）：「是否录制完成后执行自定义脚本」是黑名单命令
# 的启用位（录后脚本经 notify.py 直接进 shell）；web_trusted_proxy 决定 XFF 是否可信（登录限流按此
# 分桶，写入即换限流键）；web_allowed_hosts 决定哪些 Host/Origin 能驱动写接口（DNS 重绑定防线）。
# 刻意仍维持黑名单口径：改白名单会打死 [录制设置] 全节的正常面板编辑，属另一项待批准改造
_DANGEROUS_CONFIG_KEYS = {
    "自定义脚本执行命令",
    "是否录制完成后执行自定义脚本",
    "web_trusted_proxy",
    "web_allowed_hosts",
    # 本键即 favicon 路由（免鉴权）的图标路径源（WEB_ICON_KEY）。经面板写成
    # 任意绝对路径后，GET /favicon.ico 会把该文件原文回给持会话者——raw config.ini 的 Cookie/口令
    # 经此整条绕开读侧 '***' 掩码与写侧危险键拦截。正常导入图标走 /api/icon → save_icon_preference
    # （直写 config，不经 /api/config 守卫），入黑名单不影响该路径。
    "web_tray_icon",
}
# casefold 后的黑名单：行匹配大小写不敏感（re.IGNORECASE），黑名单判定须同等强度，否则 ASCII 键
# web_* 的大小写变体可绕过。
_DANGEROUS_CONFIG_KEYS_FOLDED = {k.casefold() for k in _DANGEROUS_CONFIG_KEYS}

# 房间列表写入互斥锁：序列化「查重 + 追加」的 TOCTOU 窗口，
# 多线程 uvicorn 下并发 POST 同一 URL 时只允许一条成功
_rooms_config_lock = threading.Lock()

# ─── 对外错误契约 ─────────────────────────────────────────────────────
# 内部异常原文（Windows 绝对路径、Errno 13、loguru 句柄冲突细节）不得进 {"detail": ...}：前端会
# 原样弹成 toast，等于向任何能访问面板的人泄露安装路径与 OS 细节（认证关闭时对局域网可见）。
# 对外只给固定 code，细节进日志。
_STATUS_ERROR_CODE = "status_unavailable"
_LOGS_ERROR_CODE = "logs_unavailable"
_DANMAKU_ERROR_CODE = "danmaku_unavailable"
_ROOM_DELETE_ERROR_CODE = "room_delete_failed"
_ROOM_UPDATE_ERROR_CODE = "room_update_failed"
# 写入失败只回固定 code：绝对路径只经 _log_internal_error 进内部日志，不进 500 detail
# （认证关闭时，detail 里的绝对路径等于对局域网泄露安装路径）。
_QUALITY_WRITE_ERROR_CODE = "quality_write_failed"
_HOST_DENIED_DETAIL = "host_not_allowed"

# ─── web_token_expiry 的目标态夹取 ─────────────────────────────────
# 该键经 PUT /api/config 可写，且因命中 _KEY_NOT_SECRET_PATTERN 的 expiry 例外而不受敏感键守卫，
# 既无上下界也无「不得清空」保护。两条失效形态：① 写成 0/负数 → 登录拿到的 exp = now，中间件判
# exp > time.time() 立即为假 → 所有 /api/*（含再次 PUT 修正自身）一律 401，只能手改 config.ini；
# ② 写成超大值 → 令牌实际永不过期且 _tokens 只增不减（内存无界），泄露的 bearer 成为永久凭据。
# 夹取而非拒绝：越界值本身无意义，登录时按边界生效。下界 60s，上界 7 天（与默认 86400s 同量级）。
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


# ─── 状态快照的 TTL 缓存 + 单飞 ───────────────────────────────────────
# get_status() 在录制进程里持 record_state_lock / max_request_lock，并调 check_disk_capacity →
# shutil.disk_usage：录制盘是 UNC/网络盘/可移动盘且已挂起时该调用可达数十秒，放在 async def 里
# 直接执行即一次挂起停摆整个面板。现在 ① 采样在专用线程里跑；② 结果按 TTL 复用；③ 同一时刻只
# 允许一个采样在飞，超时方回陈旧快照并置 stale:true——「慢」只落在数据新鲜度上，不落在可用性上。
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
    # 唯一出口：细节只落日志，响应体只带 code。消息体是「纯占位符 + 机器可读 code」而非
    # 中文散文：code 属接口契约（前端按它映射文案）、不进 i18n 四语目录。异常类型与上下文由 loguru
    # 的 exception 上下文带出，不写裸 str(e)——Windows 下 socket.timeout/TimeoutError 的 str() 为空串，
    # 裸写会打成空白行。
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
    # 与 web.py 启动检查同源的环境变量破例（DOUYIN_WEB_ALLOW_INSECURE=1）：中间件的每请求判定必须
    # 尊重同一个逃生阀，否则「明知风险仍要开放局域网」的部署启动成功后立刻被 403，面板全部报错。
    return os.environ.get("DOUYIN_WEB_ALLOW_INSECURE", "").strip().lower() in ("1", "true", "yes")


# 403 文案收敛到一处（两个触发点：关认证、把 web_host 写成回环值）。判定基准换成实际绑定地址后，
# 「请先在 config.ini 把 web_host 改为 127.0.0.1」对用户失效——那个键改了也不改变真实监听面，只有
# 重启才改得动。故文案必须报出实际监听地址，并把「该做什么」按触发点分开。
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
    # 安全判定的「监听地址」基准：首选 create_app 传入的实际绑定地址（web.py 已接线），只有调用方
    # 未接线（bind_host is None）才回落配置值。理由：① 既有调用点（tests/ 直接构造 app、第三方复用
    # create_app）不传该参数，若默认按「未知 = 非回环」，认证关闭时它们会被中间件全量 403——安全
    # 修复变成功能回归，回归用例也分不清「守卫生效」与「守卫锁死」；② 回落方向与修复前逐字一致，
    # 新旧用例的差值只可能来自新守卫；③ 回落不等于放行，仍是 is_loopback_bind_host 的严格判定。
    # 生产入口必须显式传入，否则「非回环 + 无认证」不变量退回可被两步写入旁路的旧形态。
    bound = cast("str | None", app.state.bind_host)
    if isinstance(bound, str) and bound.strip():
        return bound.strip()
    return str(cast(object, cfg.get("web_host", "")) or "")


def _guard_bind_port(app: Starlette) -> int:
    # 端口与地址同判：web_port 同样可经 PUT /api/config 改写，而进程监听端口直到重启才变；Origin
    # 同源判定靠端口区分「本站页面」与「本机/局域网另一台服务器上的页面」，基准必须取实际绑定值。
    # 返回 0 表示调用方未接线，由 web_config.is_origin_allowed 按配置 web_port 回落（理由同
    # _guard_bind_host：不改既有调用点语义，也不把「未知」当「放行」）。
    return cast("int | None", app.state.bind_port) or 0


# app.state 上的自定义属性由 Starlette 动态承载（类型化为 Any），读取处统一用 cast 收敛类型。
def _trusted_proxy_set(cfg: dict[str, str | int | bool]) -> set[str]:
    return {h.strip() for h in str(cast(str, cfg.get("web_trusted_proxy", ""))).split(",") if h.strip()}


def _get_client_ip(request: Request, cfg: dict[str, str | int | bool]) -> str:
    # 解析客户端真实 IP，用作登录失败限流的键。本函数是全链路唯一的 XFF 解释者：web.py 显式
    # proxy_headers=False，scope["client"] 即原始 socket 对端（uvicorn 默认 proxy_headers=True 且
    # forwarded_allow_ips 含 127.0.0.1，会在本函数之前用 XFF 最左值覆盖 client.host）。
    # 直连对端不可信时完全忽略 XFF（既不拿它当键、也不拿它派生任何键）；可信时按 RFC 7239 的
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
    # 运行时从 pyproject.toml 读取版本号（单一事实源），失败回退 "0.0.0"：优先 importlib.metadata
    # （已安装时），回退直接解析 pyproject.toml 文件。与 main.py 的 _read_version_from_pyproject 同源。
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


# 日志尾读的字节预算：deque(maxlen=lines) 只限保留条数，数百 MB 的 streamget.log 仍会被逐行读完；
# 本端点是同步 def、占 anyio 线程池（默认 40 槽）一格，几条并发轮询即可耗尽线程池、拖死整个面板。
# 从 EOF 反向按块读，成本 O(max_bytes) 而非 O(文件大小)。
_LOG_TAIL_MAX_BYTES = 1024 * 1024
_LOG_TAIL_CHUNK_BYTES = 64 * 1024


def _read_log_tail(log_file: str, lines: int, max_bytes: int) -> list[str]:
    # seek 到 EOF 后按块回退，攒够 lines+1 个换行（多一个的余量给被截断的首行）或读完字节预算即停。
    # 窗口起点若落在行中间（pos>0 且前一字节不是 \n/\r），首行是不完整碎片，整行丢弃——宁可少给
    # 一行，也不把半截 UTF-8 序列渲染成乱码（errors="ignore" 已兜住残字节）
    data = b""
    newlines = 0
    with open(log_file, "rb") as f:
        pos = f.seek(0, os.SEEK_END)
        read_bytes = 0
        while pos > 0 and read_bytes < max_bytes and newlines < lines + 1:
            step = min(_LOG_TAIL_CHUNK_BYTES, pos, max_bytes - read_bytes)
            pos -= step
            f.seek(pos)
            block = f.read(step)
            data = block + data
            read_bytes += len(block)
            newlines += block.count(b"\n")
        head_complete = True
        if pos > 0:
            f.seek(pos - 1)
            head_complete = f.read(1) in (b"\n", b"\r")
    out = data.decode("utf-8", errors="ignore").splitlines()
    if not head_complete and out:
        out = out[1:]
    return out[-lines:] if lines > 0 else []


def create_app(
    config_file: str,
    url_config_file: str,
    downloads_root: str,
    logs_dir: str,
    bind_host: str | None = None,
    bind_port: int | None = None,
) -> Starlette:
    # 创建 Starlette 应用。参数显式传入（而非读全局），便于测试时指向临时文件；version 由
    # _APP_VERSION 在运行时从 pyproject.toml 动态提供，避免硬编码。
    # bind_host / bind_port = 进程实际监听的地址与端口，由 web.py 把已知 host/port 传进来：「非回环 +
    # 无认证」不变量与 Origin 同源判定此前都读 config.ini 的 web_host/web_port，而 web_host 自身可经
    # 同一个 PUT /api/config 改写，于是「先写 web_host=127.0.0.1、再写 web_auth_enable=false」两步即可
    # 让仍监听 0.0.0.0 的进程变成「无认证 + 全网卡」。判定一律以本处传入的实际绑定地址为准。
    app = Starlette()

    # Starlette 内建 handler 回 PlainTextResponse(detail)——正文变成裸字符串，前端 apiError() 读不到
    # detail 键。这里按 FastAPI 语义显式注册 JSON handler；headers 透传保留 raise 时附带的
    # Retry-After（限流路径在用）。
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

    # 不设 app.state.web_cfg 快照：它只写不读（中间件与各端点一律经 _read_web_config_cached 取带缓存
    # 的配置），且启动后即刻陈旧，留着会误导「改这里能影响行为」的读者。

    # 认证中间件：每次请求重新读取配置，保证面板内修改配置即时生效。读配置走带 mtime+size 失效的
    # 进程内缓存：前端每 2 秒轮询 /api/status、多标签页线性叠加，无认证场景下可被低成本放大为磁盘
    # IO 压力；配置被改写时 mtime 必变，故「即时生效」不受影响。
    # 刻意例外：本中间件留在事件循环里——每请求只做一次 os.stat（O(1)），只有配置真的变化时才走一次
    # configparser 全量解析（~1ms/150 行）；挪进线程池会让每个请求多一次线程派发，比要防的问题更贵。
    # 写侧的安全敏感变化另由 _invalidate_web_cfg_cache 兜住。Starlette 没有 FastAPI 的
    # @app.middleware("http")，底层即 add_middleware(BaseHTTPMiddleware, dispatch=func)，此处同语义注册。
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
            # Host 头必须落在服务端推导的允许名单内（回环 + web_host + web_allowed_hosts，另放行
            # IP 字面量与无点单标签名，理由见 web_config.is_host_allowed）。DNS 重绑定（attacker.tld
            # 的 A 记录 TTL=0 指向 127.0.0.1）下浏览器发出的 Host 与 Origin 都是 attacker.tld，拿
            # 请求自带的 Host 比 Origin 必然「同源」；名单来自 config.ini 而非请求头，该等式即不再
            # 成立。判定放在最前面，读接口一并覆盖（跨源读取同样能拉走配置与日志）。
            if _should_warn_denied_host(request.headers.get("host", "")):
                # 每个被拒 Host 只在**首次**记一条 warning：重绑定/探测流量会以秒级重复同一请求，
                # 逐请求记日志等于让攻击者反向灌满 300KB 轮转的运行日志（logs/ 会保留多份）。
                _log_internal_error(_HOST_DENIED_DETAIL, level="warning")
            response = JSONResponse(status_code=400, content={"detail": _HOST_DENIED_DETAIL})
        elif _api_locked_out_by_insecure_bind(cfg, path, _guard_bind_host(app, cfg)):
            # 「非回环 + 无认证」不变量必须每请求判定，不能只在 web.py 启动时检查一次：一个已开认证、
            # 监听 0.0.0.0 的部署，任何持 token 者提交一次 web_auth_enable=false 即可在不重启的情况下
            # 把它变成「无认证 + 全网卡监听」，/api/config、/api/logs、/api/files、房间写入随之全开。
            # 静态页与 /health 不在拦截范围内：面板仍要打得开，用户才知道要回去改配置。
            # [历史注] 判定基准曾是配置里的 web_host，可被两步改写（先写 127.0.0.1 再关认证）而进程
            # 仍监听 0.0.0.0；现取 _guard_bind_host 的实际绑定地址。
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
            # web_auth_enable 支配，开关一开探活即 401 被误判成「服务挂了」。响应只含状态与应用版本，
            # 公开它不新增信息面。
            or path == "/health"
            or path == "/"
            or path.startswith("/web/")
            # 无尾斜杠的 `/web` 也必须免鉴权。本中间件由 BaseHTTPMiddleware 包在 StaticFiles 之外，
            # StaticFiles 自己那条「/web → /web/」的 307 还没机会执行就被这里判死，于是认证开启时
            # GET /web 拿到 401 {"detail":"unauthorized"}（auth=true 带 token 或 auth=false 才是 307，
            # /web/ 恒 200），症状是「新开标签输 http://<host>:8000/web 只见一串 unauthorized」。
            # 放行它不新增信息面：这一跳最终送出的正是已恒公开的 /web/ 静态首页。
            # 回归锁：tests/test_web_api.py::TestAuthMiddleware::test_static_panel_reachable_without_trailing_slash
            or path == "/web"
            or path == "/favicon.ico"
        ):
            # 免鉴权端点里「会读盘/解析」的那两个（/api/auth/status、/health）先过 per-IP 预算。超预算
            # 回 429 而非静默丢弃：探活方与面板要能区分「服务活着但被限流」与「服务挂了」。只对这两条
            # 生效：/web/* 与 / 是静态资源（StaticFiles 直接送文件），加预算只会把「打开面板」限掉。
            if path in _PUBLIC_BUDGET_PATHS and _public_endpoint_over_budget(_get_client_ip(request, cfg)):
                # 不逐请求记日志：攻击者正可用「超限后继续打」把每条都变成一行日志，等于把放大面从
                # 磁盘 IO 换成日志灌写（同 _should_warn_denied_host 的教训）。
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
        # CSP：面板前端无 CDN 外链、无内联脚本、无 eval（仅用 innerHTML 拼接表格，属 DOM 操作，
        # 不受 script-src 约束），故可收紧到 'self'。style-src 放行 'unsafe-inline' 是唯一妥协——
        # 若后续出现内联 <style> 或元素 style 属性由 HTML 解析产生（而非 JS DOM API 设置）才需要它。
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
        # 本端点刻意声明为同步 def——FastAPI 会把同步端点派发到 anyio 线程池，于是 read_web_config
        # （磁盘）、PBKDF2 校验（约 150ms CPU）、首次登录的哈希升级写盘全都不在事件循环里执行；
        # async def 下一次登录即把整个面板按住 150ms，成本还可被 config.ini 的迭代次数放大 → 面板级
        # CPU DoS（迭代上界见 web_config.clamp_pbkdf2_iterations）。配置读取走缓存（本端点免鉴权）。
        # 必须 dict(...) 浅拷贝：下面的明文→哈希升级会写 cfg["web_password"]，直接改缓存里的共享
        # dict 会让中间件与后续请求读到「内存已升级、磁盘还没升级」的混合态。
        cfg = dict(_read_web_config_cached(cast(str, app.state.config_file)))
        if not cast(bool, cfg["web_auth_enable"]):
            return {"token": "", "expires_in": 0, "auth_required": False}
        client_ip = _get_client_ip(request, cfg)
        # 登录失败限流：滑动窗口内失败达上限后直接拒绝，避免密码被在线爆破
        now = time.time()
        with _FAILED_LOGINS_LOCK:
            # 先过与来源地址无关的全局失败预算（键可被换、预算换不掉）
            # 条目为 (时刻, 来源)，滑窗回收按 [0] 取时刻
            while _GLOBAL_LOGIN_FAILURES and now - _GLOBAL_LOGIN_FAILURES[0][0] > _LOGIN_FAILURE_WINDOW:
                _ = _GLOBAL_LOGIN_FAILURES.popleft()
            if len(_GLOBAL_LOGIN_FAILURES) >= _LOGIN_GLOBAL_MAX_FAILURES:
                raise HTTPException(429, i18n_module.tr("登录失败次数过多，请稍后再试"))
            # 顺带全表清理窗口外条目：仅成功登录才 pop 的话，
            # IPv6 前缀轮换爆破可让键集合无界增长（内存泄漏面）
            for ip in [ip for ip, ts in _FAILED_LOGINS.items() if not any(now - t < _LOGIN_FAILURE_WINDOW for t in ts)]:
                _FAILED_LOGINS.pop(ip, None)
            failures = [t for t in _FAILED_LOGINS.get(client_ip, []) if now - t < _LOGIN_FAILURE_WINDOW]
            _FAILED_LOGINS[client_ip] = failures
            if len(failures) >= _LOGIN_MAX_FAILURES:
                raise HTTPException(429, i18n_module.tr("登录失败次数过多，请稍后再试"))
        # _purge_expired_tokens 内部自行持锁（中间件也直接调用），此处不可再包一层 with _tokens_lock
        # ——threading.Lock 非重入，会与函数内的 acquire 形成自死锁。
        _purge_expired_tokens()
        if not cast(str, cfg["web_password"]):
            raise HTTPException(500, i18n_module.tr("web_password 未配置但认证已开启"))
        # 兼容历史明文存储：首次登录时升级为 PBKDF2 哈希，避免明文落盘。升级哈希同样以 strip 后的
        # 形态为准——登录比对统一 strip（见下），存量「首尾带空格」的明文口令才不会被这次升级锁死。
        if not is_hashed_web_password(cast(str, cfg["web_password"])):
            hashed = hash_web_password(cast(str, cfg["web_password"]).strip())
            # 持引擎配置锁写 config.ini，避免与主循环热加载读/其他写并发交错
            import main as _main

            with _main.file_update_lock:
                _ = update_config_line(cast(str, app.state.config_file), "Web", "web_password", hashed)
            # 升级落盘后必须让缓存失效，否则后续请求（含下一次登录与中间件的认证判定）仍读到明文
            # 那一份；上面的浅拷贝只把污染限制在单次请求内，不能替缓存补上这次写入。
            _invalidate_web_cfg_cache()
            cfg["web_password"] = hashed
        # 登录比对统一 strip。写入侧以 strip 后的值哈希（/api/config），
        # reauth 复验也用 strip 后的值；登录侧若仍用原文，设置时粘贴带出的首尾
        # 空格会重现「能登录、不能 reauth」的口径分叉，进而变成认证配置经面板自锁。
        if not verify_web_password(req.password.strip(), cast(str, cfg["web_password"])):
            with _FAILED_LOGINS_LOCK:
                _FAILED_LOGINS.setdefault(client_ip, []).append(time.time())
                _GLOBAL_LOGIN_FAILURES.append((time.time(), client_ip))
            raise HTTPException(401, i18n_module.tr("密码错误"))
        # 登录成功：清零该 IP 的失败计数，并回收该来源在全局预算中的份额。
        # 只回收 client_ip 自己贡献的条目，其它来源的失败照记——攻击者无法借自己的成功登录清空
        # 别人挣出的预算，跨来源合计上限仍然成立；来源键伪造面由 _get_client_ip 的 trusted-proxy
        # 收口兜住。预算已打满时成功登录同样先吃 429（判定在验密之前），恢复窗口即 300 秒滑出。
        # [历史注] 旧口径完全不回收，把「持续打错密码 → 所有合法用户 429 到窗口滑完」当可接受代价。
        with _FAILED_LOGINS_LOCK:
            _FAILED_LOGINS.pop(client_ip, None)
            _kept = [entry for entry in _GLOBAL_LOGIN_FAILURES if entry[1] != client_ip]
            _GLOBAL_LOGIN_FAILURES.clear()
            _GLOBAL_LOGIN_FAILURES.extend(_kept)
        token = secrets.token_urlsafe(32)
        # 生效值走夹取（见 _clamp_token_expiry 注释）。expires_in 回**生效值**而非原始配置值，
        # 否则前端按配置值算的到期倒计时与实际令牌寿命不一致。
        expires_in = _clamp_token_expiry(cfg["web_token_expiry"])
        expiry = time.time() + expires_in
        with _tokens_lock:
            _tokens[token] = expiry
        return {"token": token, "expires_in": expires_in}

    @_route(app, ["POST"], "/api/logout")
    def logout(request: Request) -> dict[str, object]:
        # 按 Bearer 精确吊销当前会话：没有它会话时前端登出只清 localStorage，服务端 token 在
        # web_token_expiry（默认 86400s）内依旧有效，泄露的 token 只能靠改全局密码（全部会话下线）吊销。
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            with _tokens_lock:
                _ = _tokens.pop(auth[7:], None)
        return {"ok": True}

    @_route(app, ["GET"], "/api/status")
    async def get_status() -> dict[str, object]:
        # 唯一保持 async 的数据端点——需要 asyncio.wait_for 的超时语义。阻塞采样在专用线程里跑，
        # 超时回退陈旧快照并置 stale:true，「网络盘挂起 → 整面板停摆」降级为「磁盘数字暂不刷新」。
        snapshot, stale = await _get_status_snapshot()
        if stale:
            return {**snapshot, "stale": True}
        return snapshot

    # 公开端点：暴露 Web 认证状态，供前端在登录前提示「当前面板未启用认证」（故意不走 Bearer 校验
    # ——登录前拿不到 token）。同步 def：全量 configparser.read 是磁盘 IO，不能占事件循环。本端点
    # 免鉴权，故必须走缓存，否则「能访问端口」即可把读盘放大成磁盘 IO 压力（写侧已兜底失效）。
    @_route(app, ["GET"], "/api/auth/status")
    def auth_status() -> dict[str, object]:
        cfg = _read_web_config_cached(cast(str, app.state.config_file))
        auth_enabled = cast(bool, cfg["web_auth_enable"])
        return {
            "auth_required": auth_enabled,
            # 显式说明关闭状态下无人能保护面板：仅供局域网可信环境使用
            "warning": (
                None if auth_enabled else i18n_module.tr("Web 认证未启用，任何能访问本面板的网络均可操控录制配置")
            ),
        }

    # 探活端点：进程存活 + ASGI/路由已就绪 + 应用版本可读（_APP_VERSION 在模块导入期从
    # pyproject.toml 解析，读不到回退 "0.0.0"），故不探测录制引擎、磁盘、平台接口等外部依赖——那些
    # 不健康时面板仍应可访问（用户需进面板改配置），纳入探活只会让门禁误红。字段为对外契约：
    # scripts/smoke_web.json 与 CI 冒烟按 {"status": "ok"} 断言，新增字段可以、改名或改值不行。
    @_route(app, ["GET"], "/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "version": _APP_VERSION}

    @_route(app, ["GET"], "/api/status/stream")
    async def status_stream(request: Request) -> StreamingResponse:
        # 消除「慢速占用面」。原实现 `while True` 无断开检测——连接一旦建立就永不释放，
        # 误开标签页、爬虫或恶意连接可无限累积常驻协程。端点已文档化于 README（对外契约），
        # 故保留并修好：① 每轮检测客户端断开（http.disconnect）后退出；② 连续失败达上限即终止。
        _MAX_CONSECUTIVE_ERRORS = 5

        async def event_gen() -> AsyncGenerator[str, None]:
            consecutive_errors = 0
            while True:
                if await request.is_disconnected():
                    return
                # 39：与 /api/status 共用同一份带 TTL 的单飞快照——
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
    def list_rooms() -> list[dict[str, object]]:
        # 同步 def（走 FastAPI 线程池）——整文件读 + 抢 record_state_lock。
        rooms: list[dict[str, object]] = cast(
            list[dict[str, object]], parse_url_config(cast(str, app.state.url_config_file))
        )
        running: list[str] | None
        try:
            import main

            with main.record_state_lock:
                running = list(main.running_list)
        except Exception as e:
            # 把「取不到」与「确实没在录」区分开（与 /api/status 的 error / stale 口径一致）：
            # recording 写 None 而非 False，并在服务端留一条带异常类型的告警。前端按 falsy 处理
            # null、显示效果不变，但响应体与日志不再宣称「确定没在录制」——假阴性会推着用户去
            # 停止或重启录制。
            running = None
            logger.warning(
                i18n_module.tr(
                    "读取录制状态失败，房间列表中的录制态标记为未知: {type_name}: {e}",
                    type_name=type(e).__name__,
                    e=e,
                )
            )
        for r in rooms:
            # running_list 存正在录制的 URL；recording 集合存的是 "序号N 主播名" 而非 URL，
            # 故仅按 running_list 判定。且必须精确匹配：前缀子串匹配会把短 URL 的录制状态
            # 错误地套到长 URL 上（I3）
            r["recording"] = None if running is None else any(r["url"] == u for u in running)
        return rooms

    @_route(app, ["POST"], "/api/rooms")
    def add_room(req: RoomCreate) -> dict[str, object]:
        # 同步 def —— validate_room_target 会做 DNS 解析，
        # 落盘又是整文件读 + os.replace；放在事件循环里会让一个慢域名卡死整个面板。
        url = normalize_url(req.url)
        try:
            # 显式校验保留在此处（与 format_url_line 内下沉的校验同一入口、同一裁决），
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
            # 追加前必须补末行换行：URL_config.ini 末行可能无 \n（编辑器删掉尾回车、或 delete_line 后
            # 本就无尾换行），直接 open(...,"a") 会让新房间粘到上一条之后变成
            # `https://…111https://…222`，两个房间同时坏掉。手法与 append_config_line 一致：先读末
            # 字节，缺则先写一个 \n。
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
                # 被锁/权限异常：交给下面的写入本身报错，也不猜 BOM（_is_fresh_file 保持 False）。
                # 但 _needs_newline 必须保守置 True——Windows 上录制进程正持有
                # URL_config.ini 时 sharing violation 属常态，旧分支判不出末字节仍按「有换行」追加，
                # 恰好重开该「新房间粘上末行、两个房间同时坏掉」；补一个多余 \n 无害
                _needs_newline = True
            # BOM 只在「文件为空/尚不存在」时写一次，追加改用不带 sig 的 utf-8。
            # TextIOWrapper 在 "a" 模式下只有写位为 0 时才真落下 BOM，但该行为依赖 CPython 的
            # seek-to-end 细节（未文档化）；本仓 .ini 约定是「文件头一个 BOM、行内零 BOM」，
            # 显式化后判据自证、回归锁可精确钉住（tests/test_web_api.py::TestRoomEndpoints）。
            with open(_url_cfg_path, "a", encoding="utf-8") as f:
                if _is_fresh_file:
                    # utf-8 编码下 U+FEFF 逐字节即 BOM；只在文件为空/新建时写这一份
                    _ = f.write("\ufeff")
                _ = f.write(("\n" if _needs_newline else "") + line + "\n")
        return {"ok": True}

    @_route(app, ["PUT"], "/api/rooms")
    def update_room(req: RoomUpdate) -> dict[str, object]:
        # 校验已下沉进 format_url_line（唯一写入口），这里再显式调用一次，使顺序与其它写端点
        # 一致，并让 ValueError 统一转 422。[历史注] 本端点曾**完全不做**房间校验（POST 与
        # PUT/quality 都做），成为绕过 SSRF/任意 scheme/画质白名单的第二条写入口。
        old_url = normalize_url(req.old_url)
        try:
            validate_room_target(req.url, req.quality, req.name)
            # 写入行同样用归一化 URL：与 add/delete/toggle 的查重口径一致，否则 PUT 写回的原始 URL
            # 下一轮再也匹配不到（归一化 vs 未归一化）
            new_line = format_url_line(normalize_url(req.url), req.quality, req.name)
        except ValueError as e:
            raise HTTPException(422, str(e)) from e
        import main as _main

        # 与 add_room 同款双锁保护读改写窗口——无锁时并发「改房间/删房间/
        # 切开关」可 TOCTOU 静默失败或改错行
        replaced = False
        with _rooms_config_lock, _main.file_update_lock:
            old_rooms = parse_url_config(cast(str, app.state.url_config_file))
            # 与新 URL 查重（POST 已 409，PUT 此前漏检）——查重缺失时保存后配置出现重复
            # URL 行，删除/画质操作命中不确定。排除 old_url 自身：仅改画质/名字不得被误杀。
            new_url = normalize_url(req.url)
            if any(r["url"] == new_url and r["url"] != old_url for r in old_rooms):
                raise HTTPException(409, i18n_module.tr("直播间已存在"))
            # 找到匹配行（含注释状态）
            for r in old_rooms:
                if r["url"] == old_url:
                    old_raw = cast(str, r["raw_line"]).rstrip("\n").rstrip("\r")
                    prefix = "# " if not r["enabled"] else ""
                    new_raw = (prefix + new_line) if prefix else new_line
                    # update_file 的契约是「失败时返回 old_str」。返回值只作负信号，最终裁决以重新解析
                    # 文件为准（目标 URL 的行内容真的变了才算成功）：只读/被占/磁盘满时不能回报成功。
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

        # 与 add_room 同款双锁保护「查行 + 删行」窗口
        with _rooms_config_lock, _main.file_update_lock:
            rooms = parse_url_config(cast(str, app.state.url_config_file))
            for r in rooms:
                if r["url"] == url:
                    # delete_line 返回 bool（True = 真的删掉了一行）。返回值 + 重新解析双重裁决：
                    # 它在 CRLF 文件上会因整行精确比较失配而静默 no-op——Windows 主平台必然发生，
                    # 面板提示删除成功而房间继续录制并占盘。
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

        # 与 add_room 同款双锁保护「查行 + 改注释前缀」窗口
        with _rooms_config_lock, _main.file_update_lock:
            rooms = parse_url_config(cast(str, app.state.url_config_file))
            for r in rooms:
                if r["url"] == url:
                    old_raw = cast(str, r["raw_line"]).rstrip("\n").rstrip("\r")
                    # 缩进注释行（「  # url」）上 lstrip("#") 剥不动前导空白，
                    # content 仍以 # 开头——enable 写回后仍是注释行却报 enabled:true（假成功，房间
                    # 永不录制），disable 则写出「# # url」双注释。对齐 web_config._rewrite_quality_field
                    # 的行首前缀解析：整体剥掉「缩进 + # + 可选空白」。
                    content = re.sub(r"^\s*#\s*", "", old_raw)
                    new_raw = content if req.enable else "# " + content
                    # 与 update_room 同款——不再无条件回报成功。写入失败（只读/占用/
                    # 磁盘满）时旧实现仍回 {"ok": true}，面板显示状态翻转而文件字节未变。
                    _ = _main.update_file(
                        cast(str, app.state.url_config_file),
                        old_str=old_raw,
                        new_str=new_raw,
                    )
                    after = parse_url_config(cast(str, app.state.url_config_file))
                    target = next((rr for rr in after if rr["url"] == url), None)
                    # 写后验证改为语义判定（重解析出的 enabled 必须等于请求方向）。
                    # 只比「raw_line == new_raw」文本相等证明不了启用态真的翻转——正是缩进注释行
                    # 假成功从这道验证漏过的原因。
                    if target is None or cast(bool, target["enabled"]) != req.enable:
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
        # （该后 validate_room_target 内已含同款判定，此处保留以给出本端点的 422 文案）
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
            # update_room_quality 的 False 同时表示「已是目标画质」与「原子写失败」；无条件回
            # ok:true 会把只读/占用/磁盘满报成成功（前端还忽略 changed 恒弹成功）。与 update_room
            # 同口径：写后重解析裁决，文件里没变成目标值一律 500（CODE_REVIEW_2026-10-29 M-26）。
            expected_quality = quality if quality else DEFAULT_QUALITY
            after = parse_url_config(cast(str, app.state.url_config_file))
            target = next((rr for rr in after if rr["url"] == url), None)
            if target is None or str(target["quality"]) != expected_quality:
                _log_internal_error(_ROOM_UPDATE_ERROR_CODE)
                raise HTTPException(500, _ROOM_UPDATE_ERROR_CODE)
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
        # 持引擎配置锁写 config.ini（write_quality_options 内部另有串行锁），
        # 避免与主循环热加载读/其他 Web 写并发交错
        import main as _main

        with _main.file_update_lock:
            options = write_quality_options(cast(str, app.state.config_file), req.options)
        # 写失败不能再返回 {"ok": true}。write_quality_options 在 config.ini 缺失 / 节缺失 /
        # 原子写失败时返回 None——旧实现丢弃写结果，前端显示「已保存」而磁盘未变。
        if options is None:
            # detail 用固定 code，绝对路径只经 _log_internal_error 进日志
            # （旧写法把 config_file 拼进 tr 模板，是本文件唯一一处「对外不回显内部路径」违例）
            _log_internal_error(f"{_QUALITY_WRITE_ERROR_CODE} config_file={cast(str, app.state.config_file)}")
            raise HTTPException(500, _QUALITY_WRITE_ERROR_CODE)
        return {"ok": True, "options": options}

    @_route(app, ["GET"], "/api/config")
    def get_config() -> dict[str, dict[str, str]]:
        # 同步 def（走线程池）——read_config_safe 是全量 configparser 解析。
        return read_config_safe(cast(str, app.state.config_file))

    @_route(app, ["PUT"], "/api/config")
    def update_config(req: ConfigUpdate) -> dict[str, object]:
        # Pydantic 默认不 strip 字段，key 首尾空白可绕过黑名单的精确匹配、而 web_config 行匹配
        # 正则的 \s* 仍命中真实配置行，构成未认证 RCE；判定与写入前统一规范化，保证两者共用同一 key。
        key = req.key.strip()
        section = req.section.strip()
        # 入口处一次归一，Web 节的全部判定都用它。只对危险键黑名单做 casefold 时，防锁死/防清空、
        # 口令哈希化、改密吊销 token 三处守卫仍是大小写敏感的精确比较；而 configparser 的 option 本就
        # 大小写不敏感（_key_line_pattern 带 IGNORECASE），于是写入 WEB_PASSWORD 命中同一行配置却
        # 跳过全部三项守卫：明文落盘、旧 token 不失效、用 WEB_AUTH_ENABLE 绕开目标态判定开关认证。
        key_norm = key.strip().lower()
        # 节名：configparser 的 section 大小写敏感，但写错大小写的节本就命中不了 [Web] 行
        # （update_config_line 走精确比较后返回 False），故此处按不敏感处理只会更严不会更松。
        is_web_section = section.strip().lower() == "web"
        # 危险配置键（可致远程命令执行）任何认证状态下都禁止修改（casefold：与行匹配的 IGNORECASE 同强度）
        if key.casefold() in _DANGEROUS_CONFIG_KEYS_FOLDED:
            raise HTTPException(403, i18n_module.tr("该配置项不允许通过 Web 修改"))
        # 对目标态做整体判定，不只挡「认证已开启时清空密码」一个方向——认证关闭（出厂默认）时，
        # 任何能访问面板的人都能写入自己掌握的 web_password 再打开 web_auth_enable 接管面板；或只把
        # web_auth_enable 置 true 而密码为空，使全部 /api/* 返回 401、面板被永久锁死。
        current_cfg: dict[str, str | int | bool] | None = None
        if is_web_section and key_norm in ("web_auth_enable", "web_password", "web_host"):
            # 判定基准必须是**磁盘现值**（read_web_config），不能用 _read_web_config_cached：两端读同
            # 一份缓存时，「缓存 ≠ 现实」这一前提在写侧无从显现，下面两道守卫会变成死分支。
            # [历史注] 该曾把缓存接到这里，实测期望 403 实得 200（回归锁
            # tests/test_web_api.py::TestInsecureBindInvariantUsesRealAddress）。性能理由也不成立：
            # 缓存是为每请求都走的中间件准备的，这里是低频写接口——宁可多读一次盘。
            current_cfg = dict(read_web_config(cast(str, app.state.config_file)))
            _currently_enabled = cast(bool, current_cfg["web_auth_enable"])
            # `_current_pwd` 只在下面的 else 分支求值：写在 if 之前会让写 web_host 这条从不关心口令的
            # 路径依赖「配置视图里存在 web_password 键」（曾以 KeyError 炸成 500）。
            if key_norm == "web_host":
                # 对可写的判定基准本身施加目标态校验：web_host 既不命中 is_sensitive_item 也不在危险键
                # 黑名单里，不变量可被「① 写 web_host=127.0.0.1 ② 写 web_auth_enable=false」两步旁路。
                # 中间件已只认实际绑定地址，这里补第二道是为了不把「配置比现实乐观」的状态放出去。
                # 只判这一个方向：反向（实际绑回环、配置写 0.0.0.0）不拦——中间件按现实判定无旁路，且
                # 重启时 web.py 的启动检查会拒绝这一组合，放开它是为了不打死「本机调试预填 0.0.0.0」。
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
                # 把「认证降级」当作敏感变更拒绝——非回环监听地址下不允许把 web_auth_enable
                # 写成 false（旧语义下这一个写请求就能把「已开认证的 0.0.0.0 部署」变成「无认证 +
                # 全网卡监听」且无需重启）。中间件另有每请求的同一不变量兜底，这里先给 403 是为了让
                # 调用方拿到**可行动的**原因。破例仍走 DOUYIN_WEB_ALLOW_INSECURE=1（与启动检查同源）。
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
        # 读写两侧的敏感判据必须同源：读侧是 `is_sensitive_item(section, key) or
        # _looks_like_secret_value(value)`，只判前一半时，键名不含凭据关键词但值本身是凭据的项（推送
        # 接口链接 ?key=xxx、带账密的代理地址、bark 设备地址…）在面板上是 '***'，后端却当作普通配置，
        # 把掩码删空提交即把真实凭据覆盖成空/掩码。写侧复用同一份读侧判据（事实源在 web_config）。
        # old_value 回退是必要的：否则「把值型凭据清空」仍能溜过（空值没有 URL 形态可判）。
        # [历史注] old_value 曾取自 read_config_safe，回显的正是 SENSITIVE_MASK，
        # _looks_like_secret_value('***') 恒为 False 使本分支被整条放行；现从 configparser 读未脱敏
        # 原始值，读取失败时降级为空串、不改变写入语义。
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
            # 敏感键不得被空值覆盖：面板回显 '***'，用户全选删空后提交 '' 既 ≠ '***' 也 ≠ 旧值，
            # 真实 cookie/token 就被空串静默覆盖。清空敏感凭据必须走显式路径，不能由一次误操作完成。
            if not value.strip():
                raise HTTPException(
                    400, i18n_module.tr("敏感配置项不得清空：如需移除请显式填写占位值并手工编辑 config.ini")
                )
            # 掩码 '***' 同样必须被服务端拦住：read_config_safe 回显的就是 SENSITIVE_MASK，前端
            # saveConfig 跳过原样提交的掩码只是唯一一道前端防线——任何直接打 PUT /api/config 的调用方
            # 都能把真实凭据覆盖成字面 '***'。后端不接受掩码，前端跳过才降级为「省一次写入」。
            elif value.strip() == SENSITIVE_MASK:
                raise HTTPException(400, i18n_module.tr("敏感配置项不得以掩码值提交：请填入真实值，或保持该项不修改"))
        # ─── 该后端强制复验 ───────────────────────────────────────
        # 前端 confirm 只挡「手滑点保存」，挡不住直接打 PUT /api/config 的一方（脚本、旧版前端、拿到
        # bearer 却没口令的攻击者）：认证当前开启时写入 web_auth_enable / web_password 必须携带能过
        # verify_web_password 的 reauth_password，否则 403——bearer 只证明「这是个已登录会话」，
        # 不证明「操作者知道口令」。三条判据（各对应一种会被误伤的真实场景）：
        # · 只在认证已开启时要求：认证关闭（出厂默认）时面板对任何能访问端口的人都全开，也没有可信的
        #   「当前口令」可验，强复验只会把「本机用户按提示收紧配置」打死；
        # · 排在敏感空值/掩码守卫之后：web_password='***' 或空值属值形态非法，裁决必须是 400 +
        #   可行动文案（回归锁 tests/test_web_api.py::TestSensitiveValueBlankRejected）；
        # · 口令比对失败不回显任何口令线索：只回固定 detail，细节走 _log_internal_error。
        # 反向边界：其余 Web 键（web_host/web_port/web_allowed_hosts…）与其他节的键一律不受本条影响，
        # 否则「改个端口也要复验」会逼人绕过面板手改文件。
        if is_web_section and key_norm in ("web_auth_enable", "web_password"):
            # 旧「current_cfg is None → 改读 _read_web_config_cached」回退分支
            # 不可达——上方同键集的超集分支（web_auth_enable/web_password/web_host）必然已从磁盘现值
            # 赋值 current_cfg；且该回退读的是缓存，与「判定基准必须是磁盘现值」的不变量注释矛盾
            # （回归锁 TestInsecureBindInvariantUsesRealAddress）。现以 cast 收窄替代死分支。
            _reauth_cfg = cast("dict[str, str | int | bool]", current_cfg)
            if cast(bool, _reauth_cfg["web_auth_enable"]):
                _reauth = (req.reauth_password or "").strip()
                _stored_pwd = str(cast(object, _reauth_cfg["web_password"]) or "")
                if not _reauth or not verify_web_password(_reauth, _stored_pwd):
                    # 只记键名与失败原因，绝不记口令（logs/ 轮转保留多份＝凭据长期落盘）
                    _log_internal_error(f"auth_reauth_denied: key={key_norm}", level="warning")
                    raise HTTPException(403, i18n_module.tr("修改 Web 认证配置必须复验当前访问口令（reauth_password）"))
        try:
            validate_config_target(section, key, value)
        except ValueError as e:
            raise HTTPException(422, str(e)) from e
        # 密码统一以 PBKDF2 哈希存储，避免明文落盘。哈希前先 strip：reauth 复验与登录比对都用
        # strip 后的值；写入侧若用原文哈希，设置「首尾带空格」的口令后所有 reauth 永远 403，
        # 认证配置经面板永久自锁、只能手改文件。
        if is_web_section and key_norm == "web_password" and value.strip():
            normalized_password = value.strip()
            if not is_hashed_web_password(normalized_password):
                value = hash_web_password(normalized_password)
            else:
                value = normalized_password
        # 持引擎配置锁写 config.ini，避免与主循环热加载读/其他 Web 写并发交错
        import main as _main

        with _main.file_update_lock:
            ok = update_config_line(cast(str, app.state.config_file), section, key, value)
        if not ok:
            raise HTTPException(404, i18n_module.tr("未找到对应的配置项"))
        # 密码变更后吊销所有现有 token，强制重新登录
        if is_web_section and key_norm == "web_password" and req.value.strip():
            with _tokens_lock:
                _tokens.clear()
        # web_auth_enable 的任一变更同样要吊销令牌：只在写 web_password 时清，则「关认证 → 再开认证」
        # 无法切断此前签发的 bearer（最长 7 天），而重新打开认证本应等价于切断所有既有访问。
        if is_web_section and key_norm == "web_auth_enable":
            with _tokens_lock:
                _tokens.clear()
        # 安全判定键变更后必须显式失效中间件的配置缓存：缓存按 mtime+size 失效，而同一秒内的等长
        # 改写可能不改变 mtime（Windows FAT/粗精度时间戳），「关掉认证」这类写入要到下一次改写才生效。
        # 清单只登记「判定会因此改变」的键：web_allowed_hosts 决定哪些 Host/Origin 能驱动写接口
        # （DNS 重绑定防线），web_trusted_proxy 决定 XFF 是否可信（登录限流按此分桶，配错等于限流
        # 整体失效）。反向边界：web_port/web_token_expiry 等不参与安全判定，多失效一次只是重读磁盘。
        if is_web_section and key_norm in (
            "web_auth_enable",
            "web_password",
            "web_host",
            "web_allowed_hosts",
            "web_trusted_proxy",
        ):
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
        # 顺序必须是「先热切换 → 按生效码落盘 → 按生效码应答 + 回退提示」：set_language() 返回的是
        # 实际生效语言码（目录缺失时回退，如 PyYAML 未装则 zh_TW 回退 en_US），写请求值会把「本进程
        # 装载不到译文」的码落盘——录制子进程重解析后落到 en_US，两进程各说一种语言且响应虚假成功。
        import i18n as i18n_module

        if not req.language.strip() or not i18n_module.is_recognized_language(req.language):
            # 无法识别的语言值（既非受支持码也非已知别名）→ 400 而非静默回退
            raise HTTPException(400, i18n_module.tr("不支持的语言: {lang}", lang=req.language))
        normalized = i18n_module.normalize_language(req.language)
        previous = i18n_module.get_language()
        effective = i18n_module.set_language(normalized)
        # 替换+补建两步经 update_or_append_config_line 持锁原子化，
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
        # 同步 def（FastAPI 自动派发到 anyio 线程池）——本端点对目录逐项
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
        # 磁盘文件名过去原样交给 FileResponse(filename=...) 拼进
        # Content-Disposition——Linux 文件名可含 CR/LF/引号，足以注入额外响应头或撕裂
        # quoted-string（Windows 命名规则恰好挡得住，属「靠平台侥幸」而非防护）
        return FileResponse(target, filename=_safe_download_filename(os.path.basename(target)))

    @_route(app, ["GET"], "/api/logs")
    def get_logs(lines: int = 200) -> dict[str, list[str]]:
        log_file = os.path.join(cast(str, app.state.logs_dir), "streamget.log")
        if not os.path.isfile(log_file):
            return {"lines": cast(list[str], [])}
        try:
            # 反向按块读尾（见 _read_log_tail），不再整文件逐行物化
            return {"lines": _read_log_tail(log_file, lines, _LOG_TAIL_MAX_BYTES)}
        except Exception as e:
            # 日志文件被占用/权限异常时 str(e) 带安装绝对路径，旧实现把它塞进 detail 并被
            # 前端弹成 toast——对局域网泄露路径。对外只给固定 code，细节进日志（面板仍能看到失败）。
            _log_internal_error(_LOGS_ERROR_CODE, e)
            raise HTTPException(500, _LOGS_ERROR_CODE) from e

    @_route(app, ["GET"], "/api/danmaku")
    def get_danmaku(since: int = 0) -> dict[str, object]:
        # 弹幕监控快照：rooms 为各房间统计，messages 为 seq 游标之后的增量消息。与录制引擎同进程，
        # 直接读 DanmakuMonitorHub 内存快照；异常时返回空快照而非 500，避免面板因监控旁路故障整页
        # 报错。同步 def：snapshot() 抢的是弹幕枢纽全局锁，慢盘/写侧持锁时会排队。
        try:
            from src.danmaku_monitor import get_hub

            return get_hub().snapshot(since)
        except Exception as e:
            # error 字段同 /api/status 口径，只给 code 不回显内部异常原文
            _log_internal_error(_DANMAKU_ERROR_CODE, e, level="warning")
            return {"rooms": [], "messages": [], "last_seq": since, "truncated": False, "error": _DANMAKU_ERROR_CODE}

    # ===== 图标（面板标签 / Web 托盘）=====
    # 两个出口共用 ui_icons.current_icon_path 这一个解析点：分开各写一遍就会出现「标签换了、
    # 托盘没换」这种一半生效的现象。
    @_route(app, ["POST"], "/api/icon")
    def upload_icon(body: IconUpload) -> dict[str, object]:
        # 面板上传 ICO 图标。走 base64 JSON 而非 multipart：python-multipart 已摘除（Starlette 只在
        # Request.form() 内部 import 它，全仓无 .form() 调用点），为一条上传接口把整条依赖拖回运行时
        # 清单不划算；JSON 体还让「体积上限」校验落在解码之后、落盘之前这一处，与 GUI 侧「导入图标…」
        # 共用 ui_icons 的同一份判据（不会两处各判一套）。
        # 同步 def：base64 解码 + 落盘 + 配置写回全是阻塞 IO，走线程池。
        config_file = cast(str, app.state.config_file)
        try:
            raw = base64.b64decode(body.data, validate=True)
        except Exception:
            raise HTTPException(status_code=422, detail="bad_base64")
        check = validate_icon_bytes(raw)
        if not check.ok:
            # 400 而非 422：语法层没问题，是内容不合格。detail 回**机器码**（前端按码取文案），
            # 与 unauthorized / rate_limited 同一条「稳定机器码即前端契约」的口径。
            raise HTTPException(status_code=400, detail=check.code or "not_ico")
        # app_root = config.ini 的上两级，与 GUI 侧 app_root 同义：两个入口的 config/icons/ 是
        # 同一个目录，面板上传的图标桌面端下次启动也能直接用。
        target = install_icon_bytes(raw, Path(config_file).parent.parent, body.name)
        if target is None:
            raise HTTPException(status_code=500, detail="write_failed")
        persisted = save_icon_preference(config_file, WEB_SECTION, WEB_ICON_KEY, str(target))
        return {"ok": True, "path": str(target), "code": check.code, "persisted": persisted}

    @_route(app, ["GET"], "/favicon.ico")
    def favicon() -> Response:
        # 浏览器标签图标。免鉴权（中间件白名单已放行）：标签页的 favicon 请求不带 Bearer，
        # 不放行就变成「开了认证就没有图标」，而它只是个装饰资源。
        # 没有可用图标时回 404 而不是空 200：浏览器对 404 的处理是「用默认图标」，与未配置等价；
        # 空 200 反而会被缓存成一个坏图标，之后即使导入了也刷不掉。
        config_file = cast(str, app.state.config_file)
        configured = load_icon_preference(config_file, WEB_SECTION, WEB_ICON_KEY)
        resolved = current_icon_path(Path(config_file).parent.parent, configured)
        if resolved is None:
            raise HTTPException(status_code=404, detail="not_found")
        # 读取侧防线：resolve_icon_path 对绝对路径只做 is_file 判定，而本路由免鉴权。
        # config.ini 若被绕过面板的手段写入任意路径（手编辑/旧版本面板写入），这里会把该文件原文回给
        # 请求方——'***' 掩码只作用于 /api/config 读侧，对响应体不生效。回读前复验体积与 ICO 魔数：
        # 非 ICO 一律 404（浏览器回落默认图标，与「未配置」等价）；上传/导入侧判据仍是 validate_icon_bytes。
        try:
            if resolved.stat().st_size > MAX_ICON_BYTES:
                raise HTTPException(status_code=404, detail="not_found")
            payload = resolved.read_bytes()
        except OSError as e:
            # resolve 与回读之间文件被删/被占：按「无可用图标」404，与上游 None 同形
            raise HTTPException(status_code=404, detail="not_found") from e
        if probe_ico_sizes(payload) is None:
            raise HTTPException(status_code=404, detail="not_found")
        # no-cache：图标可被用户随时替换，让浏览器每次回源（前端另加时间戳参数破缓存，
        # 这里是给「直接访问 /favicon.ico」的场景兜底）。
        return FileResponse(str(resolved), media_type="image/x-icon", headers={"Cache-Control": "no-cache"})

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


# ─── main_loop_alive 已从 /api/status 契约里撤下 ──────────────────────────────
# 它读 main.main_loop_ticks，而该名字在 main.py 里从未定义、也从未自增（取证：
# `grep -rn main_loop_ticks main.py src/` 只命中 web_api.py 自身与 tests/），于是键永不下发，前端
# `s.main_loop_alive === false` 是永不成立的判定。「永不生效的存活信号」比「没有该信号」更危险：
# 后续排障会以为停摆已被覆盖。不用其他可观察量替代：engine_alive 已占 _recorder_thread；
# monitoring/error_count/running_list 只在变化时动，「零变化」可能是停摆也可能是安静运行；main.config
# 热加载失败时对象不变而主循环照旧推进（磁盘抖动即误报）；节拍量都在另外的守护线程里。
# 真正的判据必须来自 main 自己的轮次计数，故撤下该键；面板侧改由 error（采样抛错）与 stale
# （快照超时回退）两个真实信号承担，见 _status_worker / _get_status_snapshot 与 updateStatusWarning。
def _read_engine_status() -> dict[str, object]:
    # 状态采样的唯一 seam：保留本函数而不是内联进 _status_worker，就是给未来的轮次探针留接线点——
    # 一旦 main.py 侧补上轮次计数，在此按「非 None 才挂键」的口径重新接上，并同时恢复前端
    # updateStatusWarning 里对应的 === false 判定与四语目录键。
    import main

    return cast("dict[str, object]", main.get_status())


def _status_worker(fetch_since: float) -> dict[str, object]:
    # 线程体：采样 + 写缓存 + 清「进行中」标记。**任何异常都在本函数内消化**。
    # 「进行中」标记必须在线程自己的 finally 里清：asyncio.wait_for 超时只取消「等待」，取消不了
    # 已跑起来的线程——若由等待方清标记，下一个 2s 轮询又会起一条线程去撞同一块挂起的盘。
    # 且只在自己的租约仍是当前租约时才清（超时后可能已有第二次采样接管了门）。
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
    # 返回 (状态快照, 是否为陈旧值)。三层配合：① TTL 内直接复用缓存——展示值本就是秒级变化，2s
    # 窗口对面板无损，却把「每 2s 一次 disk_usage + 两把跨线程锁」从事件循环上彻底摘掉；② 单飞门
    # ——已有采样在飞（可能卡在挂起的网络盘上）时立即回陈旧值，绝不叠第二条线程；③ wait_for 超时只
    # 让等待结束，线程照旧跑完并写缓存，于是「慢」体现在数据新鲜度（stale:true）而非面板无响应。
    # 注：3.11 起 asyncio.TimeoutError 即内建 TimeoutError，故只捕一个（本仓下限 3.14）。
    global _status_inflight, _status_inflight_since
    now = time.monotonic()
    # 租约令牌就在下面的临界区里赋给 _status_inflight_since，其值即 now；
    # 传出时**直接复用 now**，不再「释锁后另起一段持锁从全局读回」。旧写法在两步之间若正好
    # 跨过租约到期，第二个采样会把 _status_inflight_since 覆盖成自己的 now，第一个采样读回的
    # fetch_since 就变成第二位的令牌 → 两个在飞采样共享同一令牌、任一回程即开门（单飞退化）
    fetch_since = now
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
    try:
        snapshot = await asyncio.wait_for(asyncio.to_thread(_status_worker, fetch_since), _STATUS_WAIT_SECONDS)
        return snapshot, False
    except TimeoutError:
        return fallback, True
    except Exception as e:
        # 理论上不可达（_status_worker 内部已吞掉 Exception），留此兜底避免陈旧标记卡死
        _log_internal_error(_STATUS_ERROR_CODE, e)
        return fallback, True


# 鉴权中间件用的配置缓存（mtime + size 失效）。key 含 config_file 路径，便于测试注入不同配置文件时
# 互不串用。值类型与 read_web_config 的返回注解一致（str | int | bool），否则缓存回填会因 dict 值
# 类型不变性报 mypy assignment/return-value 错误。
_web_cfg_cache: tuple[str, float, int, dict[str, str | int | bool]] = ("", -1.0, -1, {})


def _invalidate_web_cfg_cache() -> None:
    # 强制中间件下一次请求重新读 config.ini（认证/监听地址变更必须即刻生效）。缓存按
    # (path, mtime, size) 失效，正常写盘必然改变 mtime/size；但时间戳精度不足且改写后大小恰好相同
    # （等长变更）时会命中旧值。安全相关的键不吃这个概率，直接清。
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
    # 判断非幂等请求是否同源。无 Origin 头（curl/脚本/同源导航）放行——浏览器对跨域写请求必带
    # Origin，缺失即非浏览器场景。期望值由服务端配置推导，不拿请求自带的 Host 当基准：DNS 重绑定下
    # （attacker.tld → 127.0.0.1）Origin 与 Host 必然相等，判定形同不存在。Sec-Fetch-Site 由浏览器
    # 强制覆盖，故显式 cross-site 直接判否（缺该头不作为放行依据，避免非浏览器场景被误伤）。
    # Origin 不复用为 Host 头设计的 is_host_allowed：那套规则放行「任何 IP 字面量」与「任何无点单
    # 标签名」、且丢掉端口——http://192.168.1.47/（局域网另一台设备的页面）与 http://localhost:3000/
    # （本机 dev server）都会被判同源，而认证关闭（出厂默认）时这条判定是写接口唯一防线。现改判
    # host 与端口都命中服务端推导的期望集合（判定本体在 web_config.is_origin_allowed）；Host 头那条
    # 继续用 is_host_allowed，两套装进一个函数会有一侧退化。
    if request.headers.get("Sec-Fetch-Site", "").strip().lower() == "cross-site":
        return False
    origin = request.headers.get("Origin")
    if not origin:
        return True
    return is_origin_allowed(origin, cfg, bind_host=bind_host, bind_port=bind_port)


def _api_locked_out_by_insecure_bind(cfg: dict[str, str | int | bool], path: str, bind_host: str) -> bool:
    # /api/* 的「非回环 + 无认证」不变量（每请求判定）。只作用于 API：静态页与 /health 仍放行，
    # 否则运维既打不开面板也看不到告警，只能靠改文件恢复。bind_host 是进程实际绑定地址（调用侧经
    # _guard_bind_host 取值），不读 cfg["web_host"]——后者可经 PUT /api/config 改写，两步即旁路整条
    # 不变量。本函数只判定、不加锁不改状态；调用方负责每请求传新 cfg。
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


# Content-Disposition 文件名净化：CR/LF 会撕裂响应头（跨平台部署时 Starlette 不再替我们把住 Windows
# 命名规则的关），引号会闭合 quoted-string，控制字符不可打印。反斜杠一并剥除以免与转义混淆。
# 非 ASCII 字节交给 FileResponse 按 RFC 5987 出 filename* 形态——本层不猜、不做二次编码，只保证进入
# quoted-string 的裸名不携带分隔/控制字符。
_UNSAFE_FILENAME_RE = re.compile(r'[\r\n"\'\\\x00-\x1f\x7f]')


def _safe_download_filename(name: str) -> str:
    # 剥除 CR/LF/引号/反斜杠/控制字符；净化后为空则回落占位名，避免 filename="" 让
    # Content-Disposition 退化成无文件名的下载（浏览器落到目录名，用户拿不到可辨文件）
    cleaned = _UNSAFE_FILENAME_RE.sub("", name).strip()
    return cleaned or "download"
