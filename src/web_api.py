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
from pydantic import BaseModel
from starlette.responses import Response

from src.web_config import (
    append_config_line,
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

# token 存储：{token: expiry_timestamp}
_tokens: dict[str, float] = {}
# 保护 _tokens 并发访问的锁（login 写入、middleware 查询、密码变更时 clear 均需持锁）
_tokens_lock = threading.Lock()

# 登录失败限流：{client_ip: [失败时间戳...]}（滑动窗口内计数，成功登录即清零）
_FAILED_LOGINS: dict[str, list[float]] = {}
# 保护 _FAILED_LOGINS 并发访问的锁（多线程 uvicorn 下 login 并发写、定期清理均需持锁）
_FAILED_LOGINS_LOCK = threading.Lock()
# 窗口内最大失败次数（第 N+1 次尝试直接 429，不再到后端验证密码）
_LOGIN_MAX_FAILURES = 5
# 失败计数滑动窗口（秒）
_LOGIN_FAILURE_WINDOW = 300.0

# 危险配置键黑名单：允许通过 Web 修改等价于远程命令执行，任何认证状态下都禁止写入
_DANGEROUS_CONFIG_KEYS = {"自定义脚本执行命令"}

# 房间列表写入互斥锁：序列化「查重 + 追加」的 TOCTOU 窗口，
# 多线程 uvicorn 下并发 POST 同一 URL 时只允许一条成功
_rooms_config_lock = threading.Lock()


# app.state 上的自定义属性由 Starlette 动态承载（类型化为 Any），读取处统一用 cast 收敛类型。
class LoginRequest(BaseModel):
    password: str


def _get_client_ip(request: Request, cfg: dict[str, str | int | bool]) -> str:
    # 解析客户端真实 IP：仅当 TCP 直连对端在 web_trusted_proxy 列表中才信任
    # X-Forwarded-For（取第一个即最初客户端），否则一律用直连对端地址，
    # 防止伪造 XFF 头绕过按 IP 的登录限流
    peer = request.client.host if request.client else "unknown"
    trusted = {h.strip() for h in str(cast(str, cfg.get("web_trusted_proxy", ""))).split(",") if h.strip()}
    if peer in trusted:
        xff = request.headers.get("x-forwarded-for", "")
        if xff:
            return xff.split(",")[0].strip()
    return peer


class RoomCreate(BaseModel):
    url: str
    quality: str | None = None
    name: str | None = None


class RoomUpdate(BaseModel):
    old_url: str
    url: str
    quality: str | None = None
    name: str | None = None


class RoomToggle(BaseModel):
    url: str
    enable: bool


class RecordingToggle(BaseModel):
    enable: bool


class ConfigUpdate(BaseModel):
    section: str
    key: str
    value: str


class LanguageUpdate(BaseModel):
    language: str


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
    return "0.0.0"  # 最终回退


# 应用版本号：运行时从 pyproject.toml 动态读取（单一事实源）
_APP_VERSION = _read_app_version()


def create_app(
    config_file: str,
    url_config_file: str,
    downloads_root: str,
    logs_dir: str,
) -> FastAPI:
    # 创建 FastAPI 应用。
    # 参数显式传入（而非读全局），便于测试时指向临时文件。
    # version 由 _APP_VERSION 在运行时从 pyproject.toml 动态提供，避免硬编码。
    app = FastAPI(title="DouyinLiveRecorder Web Panel", version=_APP_VERSION)

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
        client_ip = _get_client_ip(request, cfg)
        # 登录失败限流：滑动窗口内失败达上限后直接拒绝，避免密码被在线爆破
        now = time.time()
        with _FAILED_LOGINS_LOCK:
            failures = [t for t in _FAILED_LOGINS.get(client_ip, []) if now - t < _LOGIN_FAILURE_WINDOW]
            _FAILED_LOGINS[client_ip] = failures
            if len(failures) >= _LOGIN_MAX_FAILURES:
                raise HTTPException(429, "登录失败次数过多，请稍后再试")
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
            with _FAILED_LOGINS_LOCK:
                _FAILED_LOGINS.setdefault(client_ip, []).append(time.time())
            raise HTTPException(401, "密码错误")
        # 登录成功：清零该 IP 的失败计数
        with _FAILED_LOGINS_LOCK:
            _FAILED_LOGINS.pop(client_ip, None)
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

    @app.post("/api/recording/toggle")
    async def toggle_recording(req: RecordingToggle) -> dict[str, object]:
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
        try:
            validate_room_target(req.url, req.quality, req.name)
        except ValueError as e:
            raise HTTPException(422, str(e)) from e
        line = format_url_line(url, req.quality, req.name)
        # 持有 file_update_lock 与录制主循环的 update_file/delete_line 互斥，
        # 避免热重载的 read→rewrite 窗口内追加行丢失（I2）；
        # _rooms_config_lock 将「查重 + 追加」原子化，杜绝并发 TOCTOU 重复写入。
        import main as _main

        with _rooms_config_lock, _main.file_update_lock:
            existing = parse_url_config(cast(str, app.state.url_config_file))
            if any(r["url"] == url for r in existing):
                raise HTTPException(409, "直播间已存在")
            with open(cast(str, app.state.url_config_file), "a", encoding="utf-8-sig") as f:
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
        # 危险配置键（可致远程命令执行）任何认证状态下都禁止修改
        if req.key in _DANGEROUS_CONFIG_KEYS:
            raise HTTPException(403, "该配置项不允许通过 Web 修改")
        # 认证开启时禁止清空密码：空密码 + 开启认证会让 login 直接 500，面板自锁
        if req.section == "Web" and req.key == "web_password" and not req.value.strip():
            current_cfg = read_web_config(cast(str, app.state.config_file))
            if cast(bool, current_cfg["web_auth_enable"]):
                raise HTTPException(400, "请先关闭 Web 认证再清空密码")
        value = req.value
        try:
            validate_config_target(req.section, req.key, value)
        except ValueError as e:
            raise HTTPException(422, str(e)) from e
        # 密码统一以 PBKDF2 哈希存储，避免明文落盘
        if req.section == "Web" and req.key == "web_password" and value.strip():
            if not is_hashed_web_password(value):
                value = hash_web_password(value)
        ok = update_config_line(cast(str, app.state.config_file), req.section, req.key, value)
        if not ok:
            raise HTTPException(404, "未找到对应的配置项")
        # 密码变更后吊销所有现有 token，强制重新登录
        if req.section == "Web" and req.key == "web_password" and req.value.strip():
            with _tokens_lock:
                _tokens.clear()
        return {"ok": True}

    @app.get("/api/language")
    async def get_language() -> dict[str, object]:
        # 当前语言 + 受支持语言列表（供前端语言选择器渲染）
        import i18n as i18n_module

        return {
            "language": i18n_module.get_language(),
            "available": i18n_module.available_languages(),
        }

    @app.put("/api/language")
    async def set_language(req: LanguageUpdate) -> dict[str, object]:
        # 即时切换语言：归一化校验 → 写回 config.ini → 热切换本进程翻译目录。
        # 本进程（uvicorn 与录制守护线程同进程）后续控制台/日志输出即时使用新语言；
        # main() 主循环每轮也会按配置重同步，两者一致。
        import i18n as i18n_module

        if not req.language.strip() or not i18n_module.is_recognized_language(req.language):
            # 无法识别的语言值（既非受支持码也非已知别名）→ 400 而非静默回退
            raise HTTPException(400, f"不支持的语言: {req.language}")
        normalized = i18n_module.normalize_language(req.language)
        if not update_config_line(cast(str, app.state.config_file), "录制设置", "language", normalized):
            # 键不存在（历史 config.ini 无 language 键，Web 先于引擎首轮读配置启动）：
            # 行级替换失败时降级为节末追加补建，仍失败才 500
            if not append_config_line(cast(str, app.state.config_file), "录制设置", "language", normalized):
                raise HTTPException(500, "语言配置写回失败")
        _ = i18n_module.set_language(normalized)
        return {"ok": True, "language": normalized}

    @app.get("/api/files")
    async def list_files(path: str = Query("")) -> list[dict[str, str | int | float]]:
        root = cast(str, app.state.downloads_root)
        target = os.path.realpath(os.path.join(root, path))
        if not _is_within(target, root):
            raise HTTPException(400, "非法路径")
        if not os.path.exists(target):
            raise HTTPException(404, "路径不存在")
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

    @app.get("/api/danmaku")
    async def get_danmaku(since: int = Query(0, ge=0)) -> dict[str, object]:
        # 弹幕监控快照：rooms 为各房间统计，messages 为 seq 游标之后的增量消息。
        # 与录制引擎同进程，直接读 DanmakuMonitorHub 内存快照；异常时返回空快照而非 500，
        # 避免面板因监控旁路故障整页报错。
        try:
            from src.danmaku_monitor import get_hub

            return get_hub().snapshot(since)
        except Exception as e:
            return {"rooms": [], "messages": [], "last_seq": since, "truncated": False, "error": str(e)}

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


def _is_within(child: str, parent: str) -> bool:
    # 校验 child 路径在 parent 目录内（防穿越）。
    try:
        return os.path.commonpath([child, parent]) == parent
    except ValueError:
        return False
