# tests/test_web_api.py
import os
import sys
from pathlib import Path
from unittest import mock

import pytest
from fastapi.testclient import TestClient

# main.py 在模块导入时即读取由 sys.argv[0] 推导出的 config/URL_config.ini。
# 在 `python -m pytest` 下 sys.argv[0] 指向 pytest 的 __main__.py，导致路径解析失败。
# 将其指向项目根的 main.py，使配置路径解析到 /workspace/config/，从而 mock.patch
# 触发的 `import main` 能成功（不影响任何测试断言逻辑）。
sys.argv[0] = str(Path(__file__).resolve().parent.parent / "main.py")


@pytest.fixture
def web_app(tmp_config_ini: Path, tmp_url_config: Path, tmp_path: Path):
    """构造 FastAPI app，指向临时配置文件。"""
    # 准备 downloads 目录
    downloads = tmp_path / "downloads"
    downloads.mkdir()
    (downloads / "sub").mkdir()
    (downloads / "sub" / "a.ts").write_bytes(b"\x00" * 100)
    (downloads / "root.mp4").write_bytes(b"\x00" * 200)
    # 准备 logs 目录
    logs = tmp_path / "logs"
    logs.mkdir()
    (logs / "streamget.log").write_text("line1\nline2\nline3\n", encoding="utf-8")

    from src import web_api
    app = web_api.create_app(
        config_file=str(tmp_config_ini),
        url_config_file=str(tmp_url_config),
        downloads_root=str(downloads),
        logs_dir=str(logs),
    )
    return app, str(tmp_config_ini)


@pytest.fixture
def client(web_app):
    app, _ = web_app
    return TestClient(app)


def test_status_no_auth(client):
    """web_auth_enable=false 时 /api/status 直接可访问。"""
    with mock.patch("main.get_status", return_value={"version": "v4.0.7", "monitoring": 0}):
        r = client.get("/api/status")
    assert r.status_code == 200
    data = r.json()
    assert "version" in data


def test_auth_required_when_enabled(web_app, tmp_config_ini: Path):
    """开启认证后，未带 token 的请求返回 401。"""
    # 改写 config 启用认证
    import configparser
    parser = configparser.ConfigParser(interpolation=None)
    parser.read(tmp_config_ini, encoding="utf-8")
    parser.set("Web", "web_auth_enable", "true")
    parser.set("Web", "web_password", "secret123")
    with tmp_config_ini.open("w", encoding="utf-8") as f:
        parser.write(f)

    app, _ = web_app
    client = TestClient(app)
    r = client.get("/api/status")
    assert r.status_code == 401


def test_login_auth_disabled_returns_empty_token(web_app):
    """认证关闭时，/api/login 返回空 token 且 auth_required=False。"""
    app, _ = web_app
    client = TestClient(app)
    r = client.post("/api/login", json={"password": ""})
    assert r.status_code == 200
    data = r.json()
    assert data["auth_required"] is False
    assert data["token"] == ""


def test_login_wrong_password_401(web_app, tmp_config_ini: Path):
    import configparser
    parser = configparser.ConfigParser(interpolation=None)
    parser.read(tmp_config_ini, encoding="utf-8")
    parser.set("Web", "web_auth_enable", "true")
    parser.set("Web", "web_password", "secret123")
    with tmp_config_ini.open("w", encoding="utf-8") as f:
        parser.write(f)

    app, _ = web_app
    client = TestClient(app)
    r = client.post("/api/login", json={"password": "wrong"})
    assert r.status_code == 401


def test_login_then_access_ok(web_app, tmp_config_ini: Path):
    import configparser
    parser = configparser.ConfigParser(interpolation=None)
    parser.read(tmp_config_ini, encoding="utf-8")
    parser.set("Web", "web_auth_enable", "true")
    parser.set("Web", "web_password", "secret123")
    with tmp_config_ini.open("w", encoding="utf-8") as f:
        parser.write(f)

    app, _ = web_app
    client = TestClient(app)
    r = client.post("/api/login", json={"password": "secret123"})
    assert r.status_code == 200
    token = r.json()["token"]
    with mock.patch("main.get_status", return_value={"version": "v4.0.7"}):
        r = client.get("/api/status", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
