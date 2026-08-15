# Tests for src/web_api.py - Web 面板 FastAPI 应用安全与健壮性回归测试.

import os
import sys
import threading
import types

import pytest
from fastapi.testclient import TestClient


def _install_fake_main() -> types.ModuleType:
    # 注入轻量 fake main 模块：避免导入真实 main.py 触发 FFmpeg/Node 检查等重副作用。
    # web_api 路由在请求处理中才 import main，仅使用其 file_update_lock 等符号。
    fake = types.ModuleType("main")
    fake.file_update_lock = threading.Lock()
    fake.running_list: list[str] = []
    fake.record_state_lock = threading.Lock()
    fake.recording: set[str] = set()
    sys.modules["main"] = fake
    return fake


@pytest.fixture(scope="function")
def fake_main() -> types.ModuleType:
    old = sys.modules.get("main")
    fake = _install_fake_main()
    yield fake
    if old is not None:
        sys.modules["main"] = old
    else:
        sys.modules.pop("main", None)


def _write_web_section(cfg_path, *, auth: str = "true", password: str = "", trusted_proxy: str = "") -> None:
    # 写入 [Web] 节配置（password 传哈希值或空）。
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "[Web]",
        "web_host = 127.0.0.1",
        "web_port = 8000",
        f"web_auth_enable = {auth}",
        f"web_password = {password}",
        f"web_trusted_proxy = {trusted_proxy}",
    ]
    cfg_path.write_text("\n".join(lines) + "\n", encoding="utf-8-sig")


@pytest.fixture(scope="function")
def app_env(tmp_path, fake_main):
    from src import web_api as wa

    # 重置模块级状态，避免测试间串扰
    with wa._tokens_lock:
        wa._tokens.clear()
    with wa._FAILED_LOGINS_LOCK:
        wa._FAILED_LOGINS.clear()

    cfg = tmp_path / "config.ini"
    url_cfg = tmp_path / "URL_config.ini"
    downloads = tmp_path / "downloads"
    downloads.mkdir()
    logs = tmp_path / "logs"
    logs.mkdir()

    _write_web_section(cfg, auth="true", password=wa.hash_web_password("secret123"))

    app = wa.create_app(
        config_file=str(cfg),
        url_config_file=str(url_cfg),
        downloads_root=str(downloads),
        logs_dir=str(logs),
    )
    client = TestClient(app)
    env = types.SimpleNamespace(
        app=app,
        client=client,
        cfg=cfg,
        url_cfg=url_cfg,
        downloads=downloads,
        wa=wa,
    )
    yield env
    client.close()


def _login(client: TestClient) -> str:
    resp = client.post("/api/login", json={"password": "secret123"})
    assert resp.status_code == 200, resp.text
    token = resp.json()["token"]
    assert token
    return token


class TestAuthMiddleware:
    def test_api_requires_token_when_auth_enabled(self, app_env):
        resp = app_env.client.get("/api/rooms")
        assert resp.status_code == 401

    def test_api_open_when_auth_disabled(self, tmp_path, fake_main):
        from src import web_api as wa

        cfg = tmp_path / "config.ini"
        _write_web_section(cfg, auth="false", password="")
        app = wa.create_app(
            config_file=str(cfg),
            url_config_file=str(tmp_path / "u.ini"),
            downloads_root=str(tmp_path),
            logs_dir=str(tmp_path),
        )
        client = TestClient(app)
        try:
            resp = client.get("/api/rooms")
            assert resp.status_code == 200
        finally:
            client.close()


class TestLoginRateLimit:
    def test_xff_spoofing_cannot_bypass_without_trusted_proxy(self, app_env):
        # 无可信代理时 XFF 被忽略：所有请求计为同一 IP，第 6 次被限流（C4）
        client = app_env.client
        for i in range(5):
            resp = client.post("/api/login", json={"password": "wrong"}, headers={"X-Forwarded-For": f"1.2.3.{i}"})
            assert resp.status_code == 401
        resp = client.post("/api/login", json={"password": "wrong"}, headers={"X-Forwarded-For": "9.9.9.9"})
        assert resp.status_code == 429

    def test_trusted_proxy_trusts_xff(self, app_env):
        # TestClient 的 client.host 为 testclient；将其配置为可信代理后 XFF 才生效：
        # 不同伪造 IP 各自计数，不应触发限流。
        app_env.wa.hash_web_password  # noqa: B018 - 仅确认模块可用
        _write_web_section(
            app_env.cfg,
            auth="true",
            password=app_env.wa.hash_web_password("secret123"),
            trusted_proxy="testclient",
        )
        client = app_env.client
        for i in range(5):
            resp = client.post("/api/login", json={"password": "wrong"}, headers={"X-Forwarded-For": f"1.2.3.{i}"})
            assert resp.status_code == 401
        resp = client.post("/api/login", json={"password": "wrong"}, headers={"X-Forwarded-For": "6.6.6.6"})
        assert resp.status_code == 401

    def test_successful_login_resets_failures(self, app_env):
        client = app_env.client
        for _ in range(3):
            resp = client.post("/api/login", json={"password": "wrong"})
            assert resp.status_code == 401
        resp = client.post("/api/login", json={"password": "secret123"})
        assert resp.status_code == 200


class TestRoomEndpoints:
    def test_quality_newline_rejected(self, app_env):
        token = _login(app_env.client)
        resp = app_env.client.post(
            "/api/rooms",
            json={"url": "https://live.douyin.com/1", "quality": "高清\n# evil", "name": None},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 422

    def test_add_room_no_bom_in_middle(self, app_env):
        # 连续追加两行后，除文件头部 BOM 外不应再出现 U+FEFF（C8 回归）
        token = _login(app_env.client)
        for u in ("https://live.douyin.com/1", "https://live.douyin.com/2"):
            resp = app_env.client.post("/api/rooms", json={"url": u}, headers={"Authorization": f"Bearer {token}"})
            assert resp.status_code == 200, resp.text
        text = app_env.url_cfg.read_text(encoding="utf-8-sig")
        assert "\ufeff" not in text
        assert "https://live.douyin.com/1" in text
        assert "https://live.douyin.com/2" in text

    def test_add_room_duplicate_409(self, app_env):
        token = _login(app_env.client)
        headers = {"Authorization": f"Bearer {token}"}
        resp = app_env.client.post("/api/rooms", json={"url": "https://live.douyin.com/3"}, headers=headers)
        assert resp.status_code == 200
        resp = app_env.client.post("/api/rooms", json={"url": "https://live.douyin.com/3"}, headers=headers)
        assert resp.status_code == 409

    def test_add_room_concurrent_no_duplicates(self, app_env):
        # TOCTOU 回归（C10）：并发 POST 同一 URL，仅一条成功，其余 409
        token = _login(app_env.client)
        n = 8
        barrier = threading.Barrier(n)
        results: list[int] = []

        def worker() -> None:
            client = TestClient(app_env.app)
            try:
                barrier.wait(timeout=10)
                resp = client.post(
                    "/api/rooms",
                    json={"url": "https://live.douyin.com/9"},
                    headers={"Authorization": f"Bearer {token}"},
                )
                results.append(resp.status_code)
            finally:
                client.close()

        threads = [threading.Thread(target=worker) for _ in range(n)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=20)
        assert len(results) == n
        assert results.count(200) == 1
        assert results.count(409) == n - 1


class TestPasswordManagement:
    def test_clear_password_rejected_when_auth_enabled(self, app_env):
        token = _login(app_env.client)
        resp = app_env.client.put(
            "/api/config",
            json={"section": "Web", "key": "web_password", "value": ""},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 400

    def test_password_change_revokes_tokens(self, app_env):
        client = app_env.client
        token = _login(client)
        resp = client.put(
            "/api/config",
            json={"section": "Web", "key": "web_password", "value": "newpass456"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        # 旧 token 立即失效（C11）
        resp = client.get("/api/rooms", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 401
        # 新密码可登录
        resp = client.post("/api/login", json={"password": "newpass456"})
        assert resp.status_code == 200

    def test_new_password_stored_hashed(self, app_env):
        token = _login(app_env.client)
        resp = app_env.client.put(
            "/api/config",
            json={"section": "Web", "key": "web_password", "value": "newpass456"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        text = app_env.cfg.read_text(encoding="utf-8-sig")
        assert "newpass456" not in text
        assert "pbkdf2_sha256$" in text


class TestDangerousKeys:
    def test_dangerous_key_blocked_when_auth_disabled(self, tmp_path, fake_main):
        from src import web_api as wa

        cfg = tmp_path / "config.ini"
        _write_web_section(cfg, auth="false", password="")
        app = wa.create_app(
            config_file=str(cfg),
            url_config_file=str(tmp_path / "u.ini"),
            downloads_root=str(tmp_path),
            logs_dir=str(tmp_path),
        )
        client = TestClient(app)
        try:
            resp = client.put(
                "/api/config",
                json={"section": "录制设置", "key": "自定义脚本执行命令", "value": "calc"},
            )
            assert resp.status_code == 403
        finally:
            client.close()


class TestListFiles:
    def test_broken_symlink_skipped(self, app_env):
        (app_env.downloads / "ok.ts").write_text("x", encoding="utf-8")
        broken = app_env.downloads / "broken.ts"
        try:
            os.symlink(str(app_env.downloads / "not_exists.ts"), str(broken))
        except OSError as e:
            pytest.skip(f"无法创建符号链接: {e}")
        else:
            # Windows sandbox 下 os.symlink 可能不抛异常却创建普通文件（islink=False），需校验
            if not os.path.islink(broken):
                pytest.skip("当前环境未真正创建符号链接（islink=False）")
        token = _login(app_env.client)
        resp = app_env.client.get("/api/files", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        names = [i["name"] for i in resp.json()]
        assert "ok.ts" in names
        assert "broken.ts" not in names

    def test_symlink_outside_skipped(self, app_env):
        outside = app_env.cfg  # downloads 目录之外的任意文件
        link = app_env.downloads / "leak.ts"
        try:
            os.symlink(str(outside), str(link))
        except OSError as e:
            pytest.skip(f"无法创建符号链接: {e}")
        else:
            if not os.path.islink(link):
                pytest.skip("当前环境未真正创建符号链接（islink=False）")
        token = _login(app_env.client)
        resp = app_env.client.get("/api/files", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        names = [i["name"] for i in resp.json()]
        assert "leak.ts" not in names

    def test_nested_listing_ok(self, app_env):
        sub = app_env.downloads / "sub"
        sub.mkdir()
        (sub / "a.ts").write_text("x", encoding="utf-8")
        token = _login(app_env.client)
        resp = app_env.client.get("/api/files?path=sub", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        names = [i["name"] for i in resp.json()]
        assert "a.ts" in names
