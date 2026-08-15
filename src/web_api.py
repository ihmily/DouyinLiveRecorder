# src/web_api.py
# Web 管理面板 FastAPI 应用：认证、路由、静态资源。
# pyright: reportUnusedFunction=none, reportCallInDefaultInitializer=none
from __future__ import annotations

import asyncio
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

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, field_validator
from starlette.responses import Response

from src.web_config import (
    DANGEROUS_CONFIG_KEYS,
    format_url_line,
    hash_web_password,
    is_hashed_web_password,
    normalize_url,
    parse_url_config,
    read_config_safe,
    read_web_config,
    update_config_line,
    validate_config_target,
    validate_room_target,
    verify_web_password,
)

# web/ 静态资源目录（项目根/web）
_WEB_DIR = Path(__file__).resolve().parent.parent / "web"


def _read_app_version() -> str:
    # 版本号统一从 pyproject.toml（单一事实源）动态读取，不写死。
    # 优先使用 importlib.metadata（打包/安装后可用），
    # 回退到直接解析 pyproject.toml 文件（源码运行场景）。
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
    return "0.0.0"  # 最终回退


# token 存储：{token: expiry_timestamp}
_tokens: dict[str, float] = {}
# 保护 _tokens 并发访问的锁（login 写入、middleware 查询、密码变更时 clear 均需持锁）
_tokens_lock = threading.Lock()

# 登录失败限流：按客户端 IP 记录失败时间戳（float，来自 time.time()），防止在线爆破密码。
_FAILED_LOGINS: dict[str, deque[float]] = {}
_FAILED_LOGINS_LOCK = threading.Lock()
_LOGIN_MAX_ATTEMPTS = 5
_LOGIN_WINDOW_SECONDS = 60
# 失败记录 IP 数上限：超限时先清理过期条目、再按插入顺序淘汰最旧 IP，防内存无界增长（C5）
_FAILED_LOGINS_MAX_IPS = 2048


# app.state 上的自定义属性由 Starlette 动态承载（类型化为 Any），读取处统一用 cast 收敛类型。
class LoginRequest(BaseModel):
    password: str


class RoomCreate(BaseModel):
    url: str
    quality: str | None = None
    name: str | None = None

    @field_validator("url", "quality", "name")
    @classmethod
    def _no_newline(cls, v: str | None) -> str | None:
        if v and any(c in v for c in ("\n", "\r")):
            raise ValueError("不能包含换行符")
        return v


class RoomUpdate(BaseModel):
    old_url: str
    url: str
    quality: str | None = None
    name: str | None = None

    @field_validator("old_url", "url", "quality", "name")
    @classmethod
    def _no_newline(cls, v: str | None) -> str | None:
        if v and any(c in v for c in ("\n", "\r")):
            raise ValueError("不能包含换行符")
        return v


class RoomToggle(BaseModel):
    url: str
    enable: bool


class ConfigUpdate(BaseModel):
    section: str
    key: str
    value: str


def create_app(
    config_file: str,
    url_config_file: str,
    downloads_root: str,
    logs_dir: str,
) -> FastAPI:
    # 创建 FastAPI 应用。
    # 参数显式传入（而非读全局），便于测试时指向临时文件。
    app = FastAPI(title="DouyinLiveRecorder Web Panel", version=_read_app_version())

    # 将路径与配置存入 app.state，路由通过 request.app.state 访问
    # 写入处用 setattr 避免对已类型化为 Any 的 app.state 触发 reportAny。
    setattr(app.state, "config_file", config_file)
    setattr(app.state, "url_config_file", url_config_file)
    setattr(app.state, "downloads_root", os.path.realpath(downloads_root))
    setattr(app.state, "logs_dir", logs_dir)

    web_cfg = read_web_config(config_file)
    setattr(app.state, "web_cfg", web_cfg)

    # 认证中间件：每次请求重新读取配置，保证面板内修改配置即时生效。
    @app.middleware("http")
    async def auth_middleware(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        cfg = read_web_config(cast(str, cast(FastAPI, request.app).state.config_file))
        # 健康检查与登录端点与静态资源放行
        path = request.url.path
        if (
            not cast(bool, cfg["web_auth_enable"])
            or path == "/api/login"
            or path == "/"
            or path.startswith("/web/")
            or path == "/favicon.ico"
        ):
            return await call_next(request)

        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            token = auth[7:]
            with _tokens_lock:
                exp = _tokens.get(token)
                valid = exp is not None and exp > time.time()
            if valid:
                return await call_next(request)
        return JSONResponse(status_code=401, content={"detail": "unauthorized"})

    # ===== 路由 =====

    @app.post("/api/login")
    async def login(req: LoginRequest, request: Request) -> dict[str, object]:
        # 每次登录重新读取配置，保证面板内修改密码即时生效。
        cfg = read_web_config(cast(str, app.state.config_file))
        if not cast(bool, cfg["web_auth_enable"]):
            return {"token": "", "expires_in": 0, "auth_required": False}
        client_ip = _client_ip(request, cast(str, cfg.get("web_trusted_proxy", "")))
        # 登录失败限流：同一 IP 在窗口内失败次数过多则拒绝，防止在线爆破。
        if _login_blocked(client_ip):
            raise HTTPException(429, "尝试次数过多，请稍后再试")
        with _tokens_lock:
            _purge_expired_tokens()
        if not cast(str, cfg["web_password"]):
            raise HTTPException(500, "web_password 未配置但认证已开启")
        # 兼容历史明文存储：首次登录时升级为 PBKDF2 哈希，避免明文落盘
        if not is_hashed_web_password(cast(str, cfg["web_password"])):
            hashed = hash_web_password(cast(str, cfg["web_password"]))
            _ = update_config_line(cast(str, app.state.config_file), "Web", "web_password", hashed)
            cfg["web_password"] = hashed
        if not verify_web_password(req.password, cast(str, cfg["web_password"])):
            _record_failed_login(client_ip)
            raise HTTPException(401, "密码错误")
        _clear_failed_logins(client_ip)
        token = secrets.token_urlsafe(32)
        expiry = time.time() + cast(float, cfg["web_token_expiry"])
        with _tokens_lock:
            _tokens[token] = expiry
        return {"token": token, "expires_in": cast(float, cfg["web_token_expiry"])}

    @app.get("/api/status")
    async def get_status() -> dict[str, object]:
        try:
            import main

            status = main.get_status()
        except Exception as e:
            status = cast("dict[str, object]", {"error": str(e)})
        return status

    @app.get("/api/status/stream")
    async def status_stream() -> StreamingResponse:
        async def event_gen() -> AsyncGenerator[str, None]:
            while True:
                try:
                    import main

                    status = main.get_status()
                    yield f"data: {json.dumps(status, ensure_ascii=False)}\n\n"
                except Exception as e:
                    yield f"data: {json.dumps({'error': str(e)})}\n\n"
                await asyncio.sleep(2)

        return StreamingResponse(event_gen(), media_type="text/event-stream")

    @app.get("/api/rooms")
    async def list_rooms() -> list[dict[str, str | bool]]:
        rooms = parse_url_config(cast(str, app.state.url_config_file))
        # 标记是否正在录制
        try:
            import main

            with main.record_state_lock:
                running = list(main.running_list)
        except Exception:
            running = []
        for r in rooms:
            # running_list 存放正在录制的 URL；recording 集合存的是 "序号N 主播名" 而非 URL，故仅按 running_list 判定
            # 精确匹配：前缀子串匹配会把短 URL 的录制状态错误地套到长 URL 上（I3）
            r["recording"] = any(r["url"] == u for u in running)
        return rooms

    @app.post("/api/rooms")
    async def add_room(req: RoomCreate) -> dict[str, object]:
        url = normalize_url(req.url)
        line = format_url_line(url, req.quality, req.name)
        # 存在性检查与追加必须在同一把锁内完成，否则并发 POST 同一 URL 会
        # 双双通过检查而重复追加（C10 TOCTOU）。
        # 持有 file_update_lock 与录制主循环的 update_file/delete_line 互斥，
        # 避免热重载的 read→rewrite 窗口内追加行丢失（I2）。
        import main as _main

        with _main.file_update_lock:
            existing = parse_url_config(cast(str, app.state.url_config_file))
            if any(r["url"] == url for r in existing):
                raise HTTPException(409, "直播间已存在")
            # 空/新文件用 utf-8-sig（带 BOM），已有文件用 utf-8 追加，
            # 避免 Python 3.10-3.12 在文件中部写入 BOM 污染新增行（C8）。
            path = Path(cast(str, app.state.url_config_file))
            new_file = not path.exists() or path.stat().st_size == 0
            encoding = "utf-8-sig" if new_file else "utf-8"
            with open(path, "a", encoding=encoding) as f:
                _ = f.write(line + "\n")
        return {"ok": True}

    @app.put("/api/rooms")
    async def update_room(req: RoomUpdate) -> dict[str, object]:
        old_url = normalize_url(req.old_url)
        new_line = format_url_line(req.url, req.quality, req.name)
        old_rooms = parse_url_config(cast(str, app.state.url_config_file))
        # 找到匹配行（含注释状态）
        import main as _main

        replaced = False
        for r in old_rooms:
            if r["url"] == old_url:
                old_raw = cast(str, r["raw_line"]).rstrip("\n").rstrip("\r")
                prefix = "# " if not r["enabled"] else ""
                new_raw = (prefix + new_line) if prefix else new_line
                _ = _main.update_file(
                    cast(str, app.state.url_config_file),
                    old_str=old_raw,
                    new_str=new_raw,
                )
                replaced = True
                break
        if not replaced:
            raise HTTPException(404, "未找到原直播间")
        return {"ok": True}

    @app.delete("/api/rooms")
    async def delete_room(url: str = Query(...)) -> dict[str, object]:
        url = normalize_url(url)
        import main as _main

        rooms = parse_url_config(cast(str, app.state.url_config_file))
        for r in rooms:
            if r["url"] == url:
                _main.delete_line(cast(str, app.state.url_config_file), cast(str, r["raw_line"]))
                return {"ok": True}
        raise HTTPException(404, "未找到直播间")

    @app.post("/api/rooms/toggle")
    async def toggle_room(req: RoomToggle) -> dict[str, object]:
        url = normalize_url(req.url)
        import main as _main

        rooms = parse_url_config(cast(str, app.state.url_config_file))
        for r in rooms:
            if r["url"] == url:
                old_raw = cast(str, r["raw_line"]).rstrip("\n").rstrip("\r")
                content = old_raw.lstrip("#").strip()
                new_raw = content if req.enable else "# " + content
                _ = _main.update_file(
                    cast(str, app.state.url_config_file),
                    old_str=old_raw,
                    new_str=new_raw,
                )
                return {"ok": True, "enabled": req.enable}
        raise HTTPException(404, "未找到直播间")

    @app.get("/api/config")
    async def get_config() -> dict[str, dict[str, str]]:
        return read_config_safe(cast(str, app.state.config_file))

    @app.put("/api/config")
    async def update_config(req: ConfigUpdate) -> dict[str, object]:
        # 校验写入目标，防止 INI 注入（换行注入新行/新节）
        try:
            validate_config_target(req.section, req.key, req.value)
        except ValueError as e:
            raise HTTPException(400, f"非法配置项: {e}")
        # 认证关闭时拒绝改写可触发命令执行的危险配置键，避免未授权 RCE
        web_cfg = read_web_config(cast(str, app.state.config_file))
        if not cast(bool, web_cfg["web_auth_enable"]):
            if (req.section, req.key) in DANGEROUS_CONFIG_KEYS:
                raise HTTPException(403, "未开启 Web 认证，禁止通过 API 修改可触发命令执行的配置项；请先在面板开启认证")
        value = req.value
        if req.section == "Web" and req.key == "web_password":
            # 认证开启时禁止清空密码：空密码会导致登录恒 500、面板锁死（C11）
            if cast(bool, web_cfg["web_auth_enable"]) and not value.strip():
                raise HTTPException(400, "Web 认证已开启，密码不能为空")
            # 密码统一以 PBKDF2 哈希存储，避免明文落盘
            if value.strip() and not is_hashed_web_password(value):
                value = hash_web_password(value)
        ok = update_config_line(cast(str, app.state.config_file), req.section, req.key, value)
        if not ok:
            raise HTTPException(404, "未找到对应的配置项")
        # 密码任何变更（含清空）都吊销所有现有 token，强制重新登录
        if req.section == "Web" and req.key == "web_password":
            with _tokens_lock:
                _tokens.clear()
        return {"ok": True}

    @app.get("/api/files")
    async def list_files(path: str = Query("")) -> list[dict[str, str | int | float]]:
        root = cast(str, app.state.downloads_root)
        target = os.path.realpath(os.path.join(root, path))
        if not _is_within(target, root):
            raise HTTPException(400, "非法路径")
        if not os.path.exists(target):
            raise HTTPException(404, "路径不存在")
        if os.path.isfile(target):
            try:
                st = os.stat(target)
            except OSError:
                raise HTTPException(404, "路径不存在")
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
            full_real = os.path.realpath(full)
            if not _is_within(full_real, root):
                continue
            # 跳过符号链接：下载端点经 realpath 拦截穿越，列表同样不暴露外部文件信息（C9）
            if os.path.islink(full):
                continue
            try:
                st = os.stat(full_real)
                is_dir = os.path.isdir(full_real)
            except OSError:
                # 录制中文件可能被 ffmpeg 原子替换/重命名而瞬时消失，跳过该项而非整页 500（C6）
                continue
            rel = os.path.relpath(full_real, root).replace("\\", "/")
            items.append(
                {
                    "name": name,
                    "type": "dir" if is_dir else "file",
                    "size": st.st_size if not is_dir else 0,
                    "mtime": st.st_mtime,
                    "path": rel,
                }
            )
        return items

    @app.get("/api/files/download")
    async def download_file(path: str = Query(...)) -> FileResponse:
        root = cast(str, app.state.downloads_root)
        target = os.path.realpath(os.path.join(root, path))
        if not _is_within(target, root) or not os.path.isfile(target):
            raise HTTPException(400, "非法路径或文件不存在")
        return FileResponse(target, filename=os.path.basename(target))

    @app.get("/api/logs")
    async def get_logs(lines: int = Query(200, ge=1, le=5000)) -> dict[str, list[str]]:
        log_file = os.path.join(cast(str, app.state.logs_dir), "streamget.log")
        if not os.path.isfile(log_file):
            return {"lines": cast(list[str], [])}
        try:
            with open(log_file, "r", encoding="utf-8", errors="ignore") as f:
                tail = deque(f, maxlen=lines)
            return {"lines": list(tail)}
        except Exception as e:
            raise HTTPException(500, str(e))

    # ===== 静态资源 =====
    if _WEB_DIR.exists():
        app.mount("/web", StaticFiles(directory=str(_WEB_DIR), html=True), name="web")

        @app.get("/")
        async def index() -> FileResponse:
            return FileResponse(str(_WEB_DIR / "index.html"))

    return app


def _purge_expired_tokens() -> None:
    # 清除过期 token。调用方须持有 _tokens_lock。
    now = time.time()
    expired = [t for t, exp in _tokens.items() if exp <= now]
    for t in expired:
        _ = _tokens.pop(t, None)


def _client_ip(request: Request, trusted_proxy: str = "") -> str:
    # 取客户端 IP。仅当请求确实来自配置的可信反向代理时才采信 X-Forwarded-For 首地址，
    # 否则攻击者可伪造 XFF 头绕过登录限流（C4）。
    client_host = request.client.host if request.client is not None else "unknown"
    if trusted_proxy:
        allowed = {p.strip() for p in trusted_proxy.split(",") if p.strip()}
        if client_host in allowed:
            fwd = request.headers.get("X-Forwarded-For")
            if fwd:
                return fwd.split(",")[0].strip()
    return client_host


def _login_blocked(ip: str) -> bool:
    # 判断该 IP 是否在限流窗口内已达最大失败次数。调用方无需持锁。
    now = time.time()
    with _FAILED_LOGINS_LOCK:
        dq = _FAILED_LOGINS.get(ip)
        if dq is None:
            return False
        while dq and now - dq[0] > _LOGIN_WINDOW_SECONDS:
            dq.popleft()
        return len(dq) >= _LOGIN_MAX_ATTEMPTS


def _record_failed_login(ip: str) -> None:
    # 记录一次登录失败时间戳。调用方无需持锁。
    now = time.time()
    with _FAILED_LOGINS_LOCK:
        dq = _FAILED_LOGINS.setdefault(ip, deque())
        dq.append(now)
        # 防无界增长：IP 数超上限时先清理已过期的条目，仍超限则按插入顺序淘汰最旧 IP
        if len(_FAILED_LOGINS) > _FAILED_LOGINS_MAX_IPS:
            for stale_ip in list(_FAILED_LOGINS):
                stale_dq = _FAILED_LOGINS[stale_ip]
                while stale_dq and now - stale_dq[0] > _LOGIN_WINDOW_SECONDS:
                    stale_dq.popleft()
                if not stale_dq:
                    _ = _FAILED_LOGINS.pop(stale_ip, None)
                if len(_FAILED_LOGINS) <= _FAILED_LOGINS_MAX_IPS:
                    break
            while len(_FAILED_LOGINS) > _FAILED_LOGINS_MAX_IPS:
                _ = _FAILED_LOGINS.pop(next(iter(_FAILED_LOGINS)), None)


def _clear_failed_logins(ip: str) -> None:
    # 登录成功后清空该 IP 的失败记录。调用方无需持锁。
    with _FAILED_LOGINS_LOCK:
        _ = _FAILED_LOGINS.pop(ip, None)


def _is_within(child: str, parent: str) -> bool:
    # 校验 child 路径在 parent 目录内（防穿越）。
    try:
        return os.path.commonpath([child, parent]) == parent
    except ValueError:
        return False
