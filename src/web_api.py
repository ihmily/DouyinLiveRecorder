# src/web_api.py
# Web 管理面板 FastAPI 应用：认证、路由、静态资源。
from __future__ import annotations

import asyncio
import json
import os
import secrets
import threading
import time
from collections import deque
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, Query
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from src.web_config import (
    read_web_config,
    read_config_safe,
    parse_url_config,
    format_url_line,
    normalize_url,
)

# web/ 静态资源目录（项目根/web）
_WEB_DIR = Path(__file__).resolve().parent.parent / "web"

# token 存储：{token: expiry_timestamp}
_tokens: dict[str, float] = {}
# 保护 _tokens 并发访问的锁（login 写入、middleware 查询、密码变更时 clear 均需持锁）
_tokens_lock = threading.Lock()


class LoginRequest(BaseModel):
    password: str


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
    app = FastAPI(title="DouyinLiveRecorder Web Panel", version="1.0.0")

    # 将路径与配置存入 app.state，路由通过 request.app.state 访问
    app.state.config_file = config_file
    app.state.url_config_file = url_config_file
    app.state.downloads_root = os.path.realpath(downloads_root)
    app.state.logs_dir = logs_dir

    web_cfg = read_web_config(config_file)
    app.state.web_cfg = web_cfg

    # 认证中间件：每次请求重新读取配置，保证面板内修改配置即时生效。
    @app.middleware("http")
    async def auth_middleware(request: Request, call_next):
        cfg = read_web_config(request.app.state.config_file)
        # 健康检查与登录端点与静态资源放行
        path = request.url.path
        if (not cfg["web_auth_enable"]
                or path == "/api/login"
                or path == "/"
                or path.startswith("/web/")
                or path == "/favicon.ico"):
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
    async def login(req: LoginRequest):
        # 每次登录重新读取配置，保证面板内修改密码即时生效。
        cfg = read_web_config(app.state.config_file)
        if not cfg["web_auth_enable"]:
            return {"token": "", "expires_in": 0, "auth_required": False}
        with _tokens_lock:
            _purge_expired_tokens()
        if not cfg["web_password"]:
            raise HTTPException(500, "web_password 未配置但认证已开启")
        if not secrets.compare_digest(req.password, cfg["web_password"]):
            raise HTTPException(401, "密码错误")
        token = secrets.token_urlsafe(32)
        expiry = time.time() + cfg["web_token_expiry"]
        with _tokens_lock:
            _tokens[token] = expiry
        return {"token": token, "expires_in": cfg["web_token_expiry"]}

    @app.get("/api/status")
    async def get_status():
        try:
            import main
            status = main.get_status()
        except Exception as e:
            status = {"error": str(e)}
        return status

    @app.get("/api/status/stream")
    async def status_stream():
        async def event_gen():
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
    async def list_rooms():
        rooms = parse_url_config(app.state.url_config_file)
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
    async def add_room(req: RoomCreate):
        url = normalize_url(req.url)
        existing = parse_url_config(app.state.url_config_file)
        if any(r["url"] == url for r in existing):
            raise HTTPException(409, "直播间已存在")
        line = format_url_line(url, req.quality, req.name)
        # 持有 file_update_lock 与录制主循环的 update_file/delete_line 互斥，
        # 避免热重载的 read→rewrite 窗口内追加行丢失（I2）。
        import main as _main
        with _main.file_update_lock:
            with open(app.state.url_config_file, "a", encoding="utf-8-sig") as f:
                f.write(line + "\n")
        return {"ok": True}

    @app.put("/api/rooms")
    async def update_room(req: RoomUpdate):
        old_url = normalize_url(req.old_url)
        new_line = format_url_line(req.url, req.quality, req.name)
        old_rooms = parse_url_config(app.state.url_config_file)
        # 找到匹配行（含注释状态）
        import main as _main
        replaced = False
        for r in old_rooms:
            if r["url"] == old_url:
                old_raw = r["raw_line"].rstrip("\n").rstrip("\r")
                prefix = "# " if not r["enabled"] else ""
                new_raw = (prefix + new_line) if prefix else new_line
                _main.update_file(
                    app.state.url_config_file,
                    old_str=old_raw,
                    new_str=new_raw,
                )
                replaced = True
                break
        if not replaced:
            raise HTTPException(404, "未找到原直播间")
        return {"ok": True}

    @app.delete("/api/rooms")
    async def delete_room(url: str = Query(...)):
        url = normalize_url(url)
        import main as _main
        rooms = parse_url_config(app.state.url_config_file)
        for r in rooms:
            if r["url"] == url:
                _main.delete_line(app.state.url_config_file, r["raw_line"])
                return {"ok": True}
        raise HTTPException(404, "未找到直播间")

    @app.post("/api/rooms/toggle")
    async def toggle_room(req: RoomToggle):
        url = normalize_url(req.url)
        import main as _main
        rooms = parse_url_config(app.state.url_config_file)
        for r in rooms:
            if r["url"] == url:
                old_raw = r["raw_line"].rstrip("\n").rstrip("\r")
                content = old_raw.lstrip("#").strip()
                new_raw = content if req.enable else "# " + content
                _main.update_file(
                    app.state.url_config_file,
                    old_str=old_raw,
                    new_str=new_raw,
                )
                return {"ok": True, "enabled": req.enable}
        raise HTTPException(404, "未找到直播间")

    @app.get("/api/config")
    async def get_config():
        return read_config_safe(app.state.config_file)

    @app.put("/api/config")
    async def update_config(req: ConfigUpdate):
        from src.web_config import update_config_line
        ok = update_config_line(app.state.config_file, req.section, req.key, req.value)
        if not ok:
            raise HTTPException(404, "未找到对应的配置项")
        # 密码变更后吊销所有现有 token，强制重新登录
        if req.section == "Web" and req.key == "web_password" and req.value.strip():
            with _tokens_lock:
                _tokens.clear()
        return {"ok": True}

    @app.get("/api/files")
    async def list_files(path: str = Query("")):
        root = app.state.downloads_root
        target = os.path.realpath(os.path.join(root, path))
        if not _is_within(target, root):
            raise HTTPException(400, "非法路径")
        if not os.path.exists(target):
            raise HTTPException(404, "路径不存在")
        if os.path.isfile(target):
            st = os.stat(target)
            return [{"name": os.path.basename(target), "type": "file",
                     "size": st.st_size, "mtime": st.st_mtime, "path": path}]
        items = []
        for name in sorted(os.listdir(target)):
            full = os.path.join(target, name)
            st = os.stat(full)
            rel = os.path.relpath(full, root).replace("\\", "/")
            items.append({
                "name": name,
                "type": "dir" if os.path.isdir(full) else "file",
                "size": st.st_size if os.path.isfile(full) else 0,
                "mtime": st.st_mtime,
                "path": rel,
            })
        return items

    @app.get("/api/files/download")
    async def download_file(path: str = Query(...)):
        root = app.state.downloads_root
        target = os.path.realpath(os.path.join(root, path))
        if not _is_within(target, root) or not os.path.isfile(target):
            raise HTTPException(400, "非法路径或文件不存在")
        return FileResponse(target, filename=os.path.basename(target))

    @app.get("/api/logs")
    async def get_logs(lines: int = Query(200, ge=1, le=5000)):
        log_file = os.path.join(app.state.logs_dir, "streamget.log")
        if not os.path.isfile(log_file):
            return {"lines": []}
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
        async def index():
            return FileResponse(str(_WEB_DIR / "index.html"))

    return app


def _purge_expired_tokens() -> None:
    # 清除过期 token。调用方须持有 _tokens_lock。
    now = time.time()
    expired = [t for t, exp in _tokens.items() if exp <= now]
    for t in expired:
        _tokens.pop(t, None)


def _is_within(child: str, parent: str) -> bool:
    # 校验 child 路径在 parent 目录内（防穿越）。
    try:
        return os.path.commonpath([child, parent]) == parent
    except ValueError:
        return False
