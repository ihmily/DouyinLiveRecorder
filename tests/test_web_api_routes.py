# -*- coding: utf-8 -*-
# 阶段2（Web 后端 FastAPI → Starlette）路由契约动态断言：取代 web_api_routes_baseline.json 的静态
# 逐字节比对。静态基线既撞 SENSITIVE_APPROVAL 门禁、又会因手工维护而漂移；本测试直接遍历 app.routes，
# 断言 Starlette 应用注册的 26 条路由（method/path 精确集合）+ /web 静态挂载点不变，
# 任何增删或改 method 的回归都会让集合断言转红（drift-proof，不依赖运行期快照）。
#
# 仅构建 app、遍历路由表，不发起任何 HTTP 请求；故不需要 fake main 的运行时替身
# （create_app 只在请求处理时才 import main，见 src/web_api.py::_read_engine_status），
# 但沿用 test_web_api.py 的临时 config 写入范式，保证 read_web_config 能解析出合法配置。

import sys
import threading
import types
from collections.abc import Generator
from pathlib import Path

import pytest
from starlette.applications import Starlette
from starlette.routing import Mount, Route


def _install_fake_main() -> types.ModuleType:
    # 注入轻量 fake main 模块：避免导入真实 main.py 触发 FFmpeg/Node 检查等重副作用。
    # web_api 路由在请求处理中才 import main，仅使用其 file_update_lock 等符号。
    fake = types.ModuleType("main")
    setattr(fake, "file_update_lock", threading.RLock())
    setattr(fake, "running_list", [])
    setattr(fake, "record_state_lock", threading.Lock())
    setattr(fake, "max_request_lock", threading.Lock())
    setattr(fake, "recording", set())
    setattr(fake, "recording_enabled", False)
    setattr(fake, "text_encoding", "utf-8-sig")
    setattr(fake, "url_config_file", "")
    setattr(fake, "ini_URL_content", "")
    sys.modules["main"] = fake
    return fake


@pytest.fixture(scope="function")
def fake_main() -> Generator[types.ModuleType, None, None]:
    # function 级 fixture：每个用例用独立假 main，避免模块级状态串扰。
    old = sys.modules.get("main")
    fake = _install_fake_main()
    yield fake
    if old is not None:
        sys.modules["main"] = old
    else:
        sys.modules.pop("main", None)


def _write_web_section(cfg_path: Path) -> None:
    # 写入最小合法 [Web] 节配置，使 create_app 内的 read_web_config 能解析。
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "[Web]",
        "web_host = 127.0.0.1",
        "web_port = 8000",
        "web_auth_enable = true",
        "web_password = x",
        "web_trusted_proxy = ",
    ]
    cfg_path.write_text("\n".join(lines) + "\n", encoding="utf-8-sig")


@pytest.fixture(scope="function")
def app(fake_main: types.ModuleType, tmp_path: Path) -> Generator[Starlette, None, None]:
    from src import web_api as wa

    cfg = tmp_path / "config.ini"
    url_cfg = tmp_path / "URL_config.ini"
    downloads = tmp_path / "downloads"
    downloads.mkdir()
    logs = tmp_path / "logs"
    logs.mkdir()
    _write_web_section(cfg)
    app = wa.create_app(
        config_file=str(cfg),
        url_config_file=str(url_cfg),
        downloads_root=str(downloads),
        logs_dir=str(logs),
    )
    yield app


# 阶段2 改写后 Starlette 应用必须精确注册的路由集合（method + path）。
# 顺序无关，集合相等才算契约守住；任何 method/path 的增删改都会让断言转红。
# HEAD 为 Starlette 对 GET 路由的自动派生方法，不计入显式契约（与旧 FastAPI 行为一致）。
EXPECTED_ROUTES = {
    ("POST", "/api/login"),
    ("POST", "/api/logout"),
    ("GET", "/api/status"),
    ("GET", "/api/auth/status"),
    ("GET", "/health"),
    ("GET", "/api/status/stream"),
    ("POST", "/api/recording/toggle"),
    ("GET", "/api/rooms"),
    ("POST", "/api/rooms"),
    ("PUT", "/api/rooms"),
    ("DELETE", "/api/rooms"),
    ("POST", "/api/rooms/toggle"),
    ("PUT", "/api/rooms/quality"),
    ("GET", "/api/rooms/qualities"),
    ("PUT", "/api/rooms/qualities"),
    ("GET", "/api/config"),
    ("PUT", "/api/config"),
    ("GET", "/api/language"),
    ("PUT", "/api/language"),
    ("GET", "/api/files"),
    ("GET", "/api/files/download"),
    ("GET", "/api/logs"),
    ("GET", "/api/danmaku"),
    # 图标：面板上传（走鉴权）+ 标签图标（免鉴权，见中间件白名单）
    ("POST", "/api/icon"),
    ("GET", "/favicon.ico"),
    ("GET", "/"),
}


def test_route_table_matches_contract(app: Starlette) -> None:
    # 遍历 app.routes，分别处理 Route（带 methods）与 Mount（静态目录挂载，仅 path）。
    seen_routes: set[tuple[str, str]] = set()
    seen_mounts: list[str] = []
    for r in app.routes:
        if isinstance(r, Route):
            methods = r.methods or set()
            for m in methods:
                if m == "HEAD":
                    # Starlette 为 GET 路由自动派生 HEAD，非显式契约，跳过以免掩盖/误增
                    continue
                seen_routes.add((m, r.path))
        elif isinstance(r, Mount):
            seen_mounts.append(r.path)

    # 集合相等：缺一条或多一条都转红（变异验证：临时删一个 @_route 装饰器会让 seen_routes 少一项）
    assert seen_routes == EXPECTED_ROUTES, (
        "路由契约漂移：\n"
        f"  新增(实际有、期望无)={seen_routes - EXPECTED_ROUTES}\n"
        f"  缺失(期望有、实际无)={EXPECTED_ROUTES - seen_routes}"
    )
    # /web 静态资源挂载点必须存在（前端动效/样式/js 经此服务）
    assert "/web" in seen_mounts, f"缺失 /web 静态挂载点，实际挂载={seen_mounts}"


def test_route_count_is_26(app: Starlette) -> None:
    # 健全性：路由条数必须等于 26（与 EXPECTED_ROUTES 集合规模一致，防集合去重掩盖重复注册）。
    seen = {(m, r.path) for r in app.routes if isinstance(r, Route) for m in (r.methods or set()) if m != "HEAD"}
    assert len(seen) == 26, f"路由条数应为 26，实际={len(seen)}"
