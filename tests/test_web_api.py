# -*- coding: utf-8 -*-
# src/web_api.py 测试：Web 面板 FastAPI 应用的安全与健壮性回归。聚焦四类契约 ——
# ① 鉴权中间件（启用认证时所有 /api/* 须 401，禁用时开放）；② 登录限流（防 XFF 伪造绕过、
# 失败计数与成功重置、密码变更吊销 token）；③ 写接口的注入/越权防护（quality 含换行被 422、
# 危险配置键被 403 阻断 RCE）；④ 并发安全（TOCTOU 重复添加房间）与副作用（停止录制触发日志归档、
# 语言即时切换写回 config）。
# 测试策略：用 types.ModuleType 注入轻量 fake main（避免导入真实 main.py 触发的 FFmpeg/Node 检查
# 等重副作用，web_api 仅在请求处理时才 import main、仅用到 file_update_lock 等符号）；通过
# create_app 注入临时 config/URL_config/downloads/logs 目录隔离文件系统；用 FastAPI TestClient
# 同步驱动异步路由，全程不监听端口。用例内 C4/C8/C10/C11 等为安全/健壮性回归编号（见 CODE_WIKI 变更记录）。

import os
import sys
import threading
import types
from collections.abc import Generator
from pathlib import Path
from typing import cast

import pytest
from fastapi.testclient import TestClient


def _install_fake_main() -> types.ModuleType:
    # 注入轻量 fake main 模块：避免导入真实 main.py 触发 FFmpeg/Node 检查等重副作用。
    # web_api 路由在请求处理中才 import main，仅使用其 file_update_lock 等符号。
    fake = types.ModuleType("main")
    # types.ModuleType 不接受静态注解的任意属性赋值，用 setattr 注入测试替身符号
    setattr(fake, "file_update_lock", threading.Lock())
    setattr(fake, "running_list", [])
    setattr(fake, "record_state_lock", threading.Lock())
    setattr(fake, "recording", set())
    setattr(fake, "recording_enabled", False)
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


def _write_web_section(cfg_path: Path, *, auth: str = "true", password: str = "", trusted_proxy: str = "") -> None:
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
def app_env(tmp_path: Path, fake_main: types.ModuleType) -> Generator[types.SimpleNamespace, None, None]:
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
    # 测试辅助：复用固定密码登录换取 token，避免每个用例重复登录样板。
    resp = client.post("/api/login", json={"password": "secret123"})
    assert resp.status_code == 200, resp.text
    token = resp.json()["token"]
    assert token
    return cast(str, token)


class TestAuthMiddleware:
    # 守护鉴权中间件：认证启用时所有 /api/* 无 Bearer token 必须 401（fail-closed），
    # 禁用时面板完全开放（200）。验证默认拒绝与可配置开放两种契约。
    def test_api_requires_token_when_auth_enabled(self, app_env: types.SimpleNamespace) -> None:
        # 认证启用时未带 Bearer token 访问受保护接口必须 401，验证中间件默认拒绝（fail-closed）。
        resp = app_env.client.get("/api/rooms")
        assert resp.status_code == 401

    def test_api_open_when_auth_disabled(self, tmp_path: Path, fake_main: types.ModuleType) -> None:
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
    def test_xff_spoofing_cannot_bypass_without_trusted_proxy(self, app_env: types.SimpleNamespace) -> None:
        # 无可信代理时 XFF 被忽略：所有请求计为同一 IP，第 6 次被限流（C4）
        client = app_env.client
        for i in range(5):
            resp = client.post("/api/login", json={"password": "wrong"}, headers={"X-Forwarded-For": f"1.2.3.{i}"})
            assert resp.status_code == 401
        resp = client.post("/api/login", json={"password": "wrong"}, headers={"X-Forwarded-For": "9.9.9.9"})
        assert resp.status_code == 429

    def test_trusted_proxy_trusts_xff(self, app_env: types.SimpleNamespace) -> None:
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

    def test_successful_login_resets_failures(self, app_env: types.SimpleNamespace) -> None:
        # 连续失败计数后一次成功登录须清零失败表；
        # 防止合法用户被持续限流（C4 失败后重置）。
        client = app_env.client
        for _ in range(3):
            resp = client.post("/api/login", json={"password": "wrong"})
            assert resp.status_code == 401
        resp = client.post("/api/login", json={"password": "secret123"})
        assert resp.status_code == 200


class TestRoomEndpoints:
    def test_quality_newline_rejected(self, app_env: types.SimpleNamespace) -> None:
        # quality 字段含换行（"高清\n# evil"）属于响应头/配置注入向量，须被 422 校验拒绝而非落盘。
        token = _login(app_env.client)
        resp = app_env.client.post(
            "/api/rooms",
            json={"url": "https://live.douyin.com/1", "quality": "高清\n# evil", "name": None},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 422

    def test_add_room_no_bom_in_middle(self, app_env: types.SimpleNamespace) -> None:
        # 连续追加两行后，除文件头部 BOM 外不应再出现 U+FEFF（C8 回归）
        token = _login(app_env.client)
        for u in ("https://live.douyin.com/1", "https://live.douyin.com/2"):
            resp = app_env.client.post("/api/rooms", json={"url": u}, headers={"Authorization": f"Bearer {token}"})
            assert resp.status_code == 200, resp.text
        text = app_env.url_cfg.read_text(encoding="utf-8-sig")
        assert "\ufeff" not in text
        assert "https://live.douyin.com/1" in text
        assert "https://live.douyin.com/2" in text

    def test_add_room_duplicate_409(self, app_env: types.SimpleNamespace) -> None:
        # 同一 URL 二次添加须返回 409（去重），不重复写入；
        # 验证 URL_config 幂等守护。
        token = _login(app_env.client)
        headers = {"Authorization": f"Bearer {token}"}
        resp = app_env.client.post("/api/rooms", json={"url": "https://live.douyin.com/3"}, headers=headers)
        assert resp.status_code == 200
        resp = app_env.client.post("/api/rooms", json={"url": "https://live.douyin.com/3"}, headers=headers)
        assert resp.status_code == 409

    def test_add_room_concurrent_no_duplicates(self, app_env: types.SimpleNamespace) -> None:
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


class TestRoomQualityApi:
    # 守护按房间切换画质端点（PUT /api/rooms/quality）：与 GUI 画质监控共用
    # update_room_quality 落盘画质段，验证切换/恢复默认/幂等/404/422 全链路契约。
    def _auth_headers(self, app_env: types.SimpleNamespace) -> dict[str, str]:
        token = _login(app_env.client)
        return {"Authorization": f"Bearer {token}"}

    def test_change_and_reset_quality(self, app_env: types.SimpleNamespace) -> None:
        # 切换画质 → 文件含画质段；恢复默认（quality=null）→ 画质段移除且行保持完整
        headers = self._auth_headers(app_env)
        url = "https://www.huya.com/dank1ng"
        resp = app_env.client.post("/api/rooms", json={"url": url, "name": "DANK1NG"}, headers=headers)
        assert resp.status_code == 200, resp.text

        resp = app_env.client.put("/api/rooms/quality", json={"url": url, "quality": "蓝光8M"}, headers=headers)
        assert resp.status_code == 200, resp.text
        assert resp.json()["changed"] is True
        text = app_env.url_cfg.read_text(encoding="utf-8-sig")
        assert "蓝光8M,https://www.huya.com/dank1ng,主播: DANK1NG" in text

        # 幂等：重复切换同一画质 changed=False
        resp = app_env.client.put("/api/rooms/quality", json={"url": url, "quality": "蓝光8M"}, headers=headers)
        assert resp.status_code == 200
        assert resp.json()["changed"] is False

        # 恢复默认：quality 为空移除画质段，主播名保留
        resp = app_env.client.put("/api/rooms/quality", json={"url": url, "quality": None}, headers=headers)
        assert resp.status_code == 200, resp.text
        assert resp.json()["changed"] is True
        text = app_env.url_cfg.read_text(encoding="utf-8-sig")
        assert "https://www.huya.com/dank1ng,主播: DANK1NG" in text
        assert "蓝光8M," not in text

    def test_change_quality_room_not_found_404(self, app_env: types.SimpleNamespace) -> None:
        # 未配置的 URL 切画质须 404，不得写入任何内容
        headers = self._auth_headers(app_env)
        resp = app_env.client.put(
            "/api/rooms/quality", json={"url": "https://live.douyin.com/404", "quality": "高清"}, headers=headers
        )
        assert resp.status_code == 404

    def test_change_quality_invalid_rejected_422(self, app_env: types.SimpleNamespace) -> None:
        # 白名单外档位与含换行的画质名均须 422（后者为换行注入防护），文件不被写入
        headers = self._auth_headers(app_env)
        url = "https://www.douyu.com/36252"
        resp = app_env.client.post("/api/rooms", json={"url": url}, headers=headers)
        assert resp.status_code == 200

        resp = app_env.client.put(
            "/api/rooms/quality", json={"url": url, "quality": "8K无敌"}, headers=headers
        )
        assert resp.status_code == 422
        resp = app_env.client.put(
            "/api/rooms/quality", json={"url": url, "quality": "高清\n# evil"}, headers=headers
        )
        assert resp.status_code == 422
        text = app_env.url_cfg.read_text(encoding="utf-8-sig")
        assert "8K无敌" not in text
        assert "evil" not in text

    def test_change_quality_requires_auth(self, app_env: types.SimpleNamespace) -> None:
        # 认证启用时无 Bearer token 的画质切换请求必须 401（写接口 fail-closed）
        resp = app_env.client.put(
            "/api/rooms/quality", json={"url": "https://live.douyin.com/1", "quality": "高清"}
        )
        assert resp.status_code == 401

    def test_change_quality_on_disabled_room_preserves_comment(self, app_env: types.SimpleNamespace) -> None:
        # 已注释（禁用）的房间也可预设画质：切换成功、# 前缀原样保留（含其后空格）、房间保持禁用态
        headers = self._auth_headers(app_env)
        app_env.url_cfg.write_text(
            "# https://www.huya.com/dank1ng,主播: DANK1NG\n",
            encoding="utf-8-sig",
        )
        resp = app_env.client.put(
            "/api/rooms/quality",
            json={"url": "https://www.huya.com/dank1ng", "quality": "超清"},
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["changed"] is True
        assert (
            app_env.url_cfg.read_text(encoding="utf-8-sig")
            == "# 超清,https://www.huya.com/dank1ng,主播: DANK1NG\n"
        )
        # 房间列表仍为禁用，但画质已更新（重新启用后即按预设画质录制）
        rooms = app_env.client.get("/api/rooms", headers=headers).json()
        room = next(r for r in rooms if r["url"] == "https://www.huya.com/dank1ng")
        assert room["enabled"] is False
        assert room["quality"] == "超清"

    def test_quality_visible_in_room_list_after_change(self, app_env: types.SimpleNamespace) -> None:
        # 读-写一致性：PUT 切换后 GET /api/rooms 立即返回新画质；相邻房间行不受影响
        headers = self._auth_headers(app_env)
        resp = app_env.client.post(
            "/api/rooms", json={"url": "https://live.douyin.com/1", "name": "A"}, headers=headers
        )
        assert resp.status_code == 200
        resp = app_env.client.post(
            "/api/rooms", json={"url": "https://live.douyin.com/2", "quality": "标清", "name": "B"}, headers=headers
        )
        assert resp.status_code == 200

        resp = app_env.client.put(
            "/api/rooms/quality", json={"url": "https://live.douyin.com/1", "quality": "蓝光4M"}, headers=headers
        )
        assert resp.status_code == 200
        rooms = app_env.client.get("/api/rooms", headers=headers).json()
        by_url = {r["url"]: r for r in rooms}
        assert by_url["https://live.douyin.com/1"]["quality"] == "蓝光4M"
        assert by_url["https://live.douyin.com/2"]["quality"] == "标清"

    def test_change_quality_matches_schemeless_url(self, app_env: types.SimpleNamespace) -> None:
        # PUT 侧 URL 归一化：不带 scheme 的地址也能匹配到（add_room 已规范化写入的）配置行
        headers = self._auth_headers(app_env)
        resp = app_env.client.post("/api/rooms", json={"url": "www.huya.com/dank1ng"}, headers=headers)
        assert resp.status_code == 200
        resp = app_env.client.put(
            "/api/rooms/quality", json={"url": "www.huya.com/dank1ng", "quality": "高清"}, headers=headers
        )
        assert resp.status_code == 200, resp.text
        assert "高清,https://www.huya.com/dank1ng" in app_env.url_cfg.read_text(encoding="utf-8-sig")

    def test_empty_string_quality_resets_to_default(self, app_env: types.SimpleNamespace) -> None:
        # quality 传空串与 null 等价：均移除画质段恢复默认（前端 quality||null 之外的直连调用路径）
        headers = self._auth_headers(app_env)
        url = "https://www.douyu.com/36252"
        resp = app_env.client.post("/api/rooms", json={"url": url}, headers=headers)
        assert resp.status_code == 200
        resp = app_env.client.put("/api/rooms/quality", json={"url": url, "quality": "超清"}, headers=headers)
        assert resp.status_code == 200

        resp = app_env.client.put("/api/rooms/quality", json={"url": url, "quality": ""}, headers=headers)
        assert resp.status_code == 200, resp.text
        assert resp.json()["changed"] is True
        text = app_env.url_cfg.read_text(encoding="utf-8-sig")
        assert "超清," not in text
        assert url in text


class TestPasswordManagement:
    # 守护密码管理：认证启用时清空密码须 400（防误关认证）；改密须吊销旧 token（C11）、
    # 且新密码以 pbkdf2 哈希落盘而非明文。覆盖越权与凭据泄露回归。
    def test_clear_password_rejected_when_auth_enabled(self, app_env: types.SimpleNamespace) -> None:
        # 认证启用时清空密码（web_password=""）须被 400 拒绝；
        # 防误关认证（空密码=任何人可登录）。
        token = _login(app_env.client)
        resp = app_env.client.put(
            "/api/config",
            json={"section": "Web", "key": "web_password", "value": ""},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 400

    def test_password_change_revokes_tokens(self, app_env: types.SimpleNamespace) -> None:
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

    def test_new_password_stored_hashed(self, app_env: types.SimpleNamespace) -> None:
        # 修改密码后配置文件须存哈希（pbkdf2）而非明文；
        # 验证密码落盘安全，防明文泄露。
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


# POST /api/recording/toggle：Web 面板「开始/停止录制」按钮的录制开关。
class TestRecordingToggle:
    def test_toggle_requires_auth(self, app_env: types.SimpleNamespace) -> None:
        # 录制开关是写操作，未带 token 必须 401（与读接口同受中间件保护）；
        # 锁住「控制面变更须认证」契约，防未授权启停录制。
        resp = app_env.client.post("/api/recording/toggle", json={"enable": True})
        assert resp.status_code == 401

    def test_toggle_flips_engine_flag(self, app_env: types.SimpleNamespace, fake_main: types.ModuleType) -> None:
        # enable 真/假须同步翻转引擎开关（返回体与 fake main 的 recording_enabled 双校验）；
        # 锁住「Web 开关 ↔ 引擎状态」一致契约，防止面板与实际录制脱节。
        token = _login(app_env.client)
        headers = {"Authorization": f"Bearer {token}"}
        resp = app_env.client.post("/api/recording/toggle", json={"enable": True}, headers=headers)
        assert resp.status_code == 200, resp.text
        assert resp.json()["recording_enabled"] is True
        assert fake_main.recording_enabled is True
        resp = app_env.client.post("/api/recording/toggle", json={"enable": False}, headers=headers)
        assert resp.status_code == 200, resp.text
        assert resp.json()["recording_enabled"] is False
        assert fake_main.recording_enabled is False

    def test_toggle_stop_triggers_log_archive(
        self, app_env: types.SimpleNamespace, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # 停止录制（enable=False）是手动停止路径，须触发运行日志归档；
        # 开始录制（enable=True）不触发。归档进程仍继续运行，故 reopen_streams=True。
        import src.log_archive as la

        calls: list[bool] = []

        def fake_archive(*, reopen_streams: bool = True) -> list[str]:
            calls.append(reopen_streams)
            return []

        monkeypatch.setattr(la, "archive_runtime_logs", fake_archive)
        token = _login(app_env.client)
        headers = {"Authorization": f"Bearer {token}"}
        resp = app_env.client.post("/api/recording/toggle", json={"enable": True}, headers=headers)
        assert resp.status_code == 200, resp.text
        assert calls == []
        resp = app_env.client.post("/api/recording/toggle", json={"enable": False}, headers=headers)
        assert resp.status_code == 200, resp.text
        assert calls == [True]


class TestDangerousKeys:
    # 守护危险配置键护栏：即便认证禁用，自定义脚本执行命令等危险键仍须 403 阻断，
    # 防未授权 RCE（危险配置键无视认证的 C 类回归）。
    def test_dangerous_key_blocked_when_auth_disabled(self, tmp_path: Path, fake_main: types.ModuleType) -> None:
        # 即便认证禁用，自定义脚本执行命令等危险键仍须 403 阻断；
        # 防未授权 RCE（危险配置键无视认证的 C 类回归）。
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
    # 守护文件列举：损坏符号链接与指向 downloads 之外的符号链接（目录遍历）均须被跳过不列出；
    # 子目录须能递归浏览。防通过软链泄露任意文件。
    def test_broken_symlink_skipped(self, app_env: types.SimpleNamespace) -> None:
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

    def test_symlink_outside_skipped(self, app_env: types.SimpleNamespace) -> None:
        # 指向 downloads 之外的符号链接（目录遍历）须被跳过、不列出；
        # 防通过软链泄露任意文件。
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

    def test_nested_listing_ok(self, app_env: types.SimpleNamespace) -> None:
        # 子目录文件须能被递归列出（?path=sub）；
        # 验证嵌套目录浏览正常。
        sub = app_env.downloads / "sub"
        sub.mkdir()
        (sub / "a.ts").write_text("x", encoding="utf-8")
        token = _login(app_env.client)
        resp = app_env.client.get("/api/files?path=sub", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        names = [i["name"] for i in resp.json()]
        assert "a.ts" in names


# GET/PUT /api/language：语言查询与即时切换（写回 config + 热切换进程内翻译）。
class TestLanguageApi:
    def _write_language_section(self, cfg: Path, value: str = "zh_cn") -> None:
        # 追加 [录制设置] 节与 language 键（update_config_line 行级更新需键已存在）
        text = cfg.read_text(encoding="utf-8-sig")
        if "[录制设置]" not in text:
            text += "\n[录制设置]\n"
        if not any(line.strip().startswith("language") for line in text.splitlines()):
            text += f"language = {value}\n"
        cfg.write_text(text, encoding="utf-8-sig")

    def test_get_language_returns_current_and_available(self, app_env: types.SimpleNamespace) -> None:
        # GET /api/language 须返回当前语言码与全部可用语言集合；
        # 锁住枚举契约（zh_CN/en_US/en_GB/zh_TW）。
        token = _login(app_env.client)
        resp = app_env.client.get("/api/language", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["language"] in ("zh_CN", "en_US", "en_GB", "zh_TW")
        assert set(data["available"].keys()) == {"zh_CN", "en_US", "en_GB", "zh_TW"}

    def test_put_language_switches_and_persists(self, app_env: types.SimpleNamespace) -> None:
        import i18n as i18n_module

        saved = i18n_module.get_language()
        try:
            self._write_language_section(app_env.cfg, "zh_cn")
            token = _login(app_env.client)
            resp = app_env.client.put(
                "/api/language", json={"language": "en_US"}, headers={"Authorization": f"Bearer {token}"}
            )
            assert resp.status_code == 200, resp.text
            assert resp.json()["language"] == "en_US"
            # 进程内翻译已热切换
            assert i18n_module.get_language() == "en_US"
            # config.ini 已写回归一化语言码
            assert "language = en_US" in app_env.cfg.read_text(encoding="utf-8-sig")
        finally:
            _ = i18n_module.set_language(saved)

    def test_put_language_accepts_alias(self, app_env: types.SimpleNamespace) -> None:
        # 方言码 "zh-TW" 须被规整为内部键 "zh_TW"；锁住别名归一契约，
        # 防连字符格式的语言码绕过校验或写成非标键。
        import i18n as i18n_module

        saved = i18n_module.get_language()
        try:
            self._write_language_section(app_env.cfg, "zh_cn")
            token = _login(app_env.client)
            resp = app_env.client.put(
                "/api/language", json={"language": "zh-TW"}, headers={"Authorization": f"Bearer {token}"}
            )
            assert resp.status_code == 200
            assert resp.json()["language"] == "zh_TW"
        finally:
            _ = i18n_module.set_language(saved)

    def test_put_language_rejects_unknown(self, app_env: types.SimpleNamespace) -> None:
        # 不在白名单的语言码（"klingon"）须 400 拒绝；锁住枚举护栏，
        # 防非法值写入 config 导致 i18n 初始化失败。
        self._write_language_section(app_env.cfg, "zh_cn")
        token = _login(app_env.client)
        resp = app_env.client.put(
            "/api/language", json={"language": "klingon"}, headers={"Authorization": f"Bearer {token}"}
        )
        assert resp.status_code == 400

    def test_put_language_missing_key_appends_and_succeeds(self, app_env: types.SimpleNamespace) -> None:
        # 历史 config.ini 无 [录制设置]/language 键时不得恒 500：行级替换失败须降级为节末追加补建
        # （此前 update_config_line 对缺键返回 False 直接抛 500，测试为求绿先手工写键、掩盖了真实路径）
        import i18n as i18n_module

        saved = i18n_module.get_language()
        try:
            assert "[录制设置]" not in app_env.cfg.read_text(encoding="utf-8-sig")
            token = _login(app_env.client)
            resp = app_env.client.put(
                "/api/language", json={"language": "en_US"}, headers={"Authorization": f"Bearer {token}"}
            )
            assert resp.status_code == 200, resp.text
            text = app_env.cfg.read_text(encoding="utf-8-sig")
            # 补建的节与键均在位，且不影响已有 Web 节
            assert "[录制设置]" in text and "language = en_US" in text and "[Web]" in text
        finally:
            _ = i18n_module.set_language(saved)

    def test_append_config_line_edge_cases(self, app_env: types.SimpleNamespace) -> None:
        # append_config_line 行级追加的边界：目标节存在（含无尾换行文件）与节缺失时新建于尾部
        wa = app_env.wa

        # 节存在但中间夹有其他内容：插入点应在下一节头之前、保留注释与顺序
        cfg = app_env.cfg
        cfg.write_text(
            "[Web]\nweb_auth = true\n# 注释行\n[录制设置]\ndelay = 5\n[Cookie]\nk = v\n", encoding="utf-8-sig"
        )
        assert wa.append_config_line(str(cfg), "录制设置", "language", "en_US") is True
        lines = cfg.read_text(encoding="utf-8-sig").splitlines()
        assert lines.index("language = en_US") < lines.index("[Cookie]")
        assert "# 注释行" in lines

        # 目标节是最后一节且文件无尾换行：追加后不应与原末行粘连
        cfg.write_text("[Web]\nweb_auth = true\n[录制设置]\ndelay = 5", encoding="utf-8-sig")
        assert wa.append_config_line(str(cfg), "录制设置", "language", "zh_TW") is True
        text = cfg.read_text(encoding="utf-8-sig")
        assert "delay = 5\nlanguage = zh_TW" in text

        # 节缺失：文件尾新建节再插键，返回 True
        cfg.write_text("[Web]\nweb_auth = true\n", encoding="utf-8-sig")
        assert wa.append_config_line(str(cfg), "录制设置", "language", "en_GB") is True
        assert "[录制设置]\nlanguage = en_GB\n" in cfg.read_text(encoding="utf-8-sig")

    def test_put_language_rejects_empty(self, app_env: types.SimpleNamespace) -> None:
        # 全空白语言码（"  "）须被 400 拒绝；
        # 防空/空格绕过校验。
        token = _login(app_env.client)
        resp = app_env.client.put(
            "/api/language", json={"language": "  "}, headers={"Authorization": f"Bearer {token}"}
        )
        assert resp.status_code == 400


class TestQualityOptionsEndpoints:
    # GET/PUT /api/rooms/qualities：WEB 端「画质选项」管理与 GUI 端画质切换菜单共用入口。
    # 守护：① 缺省返回内置全集；② PUT 仅接受内置档位（白名单外的会被后端剔除而非写入）；
    #     ③ PUT 持久化到 config.ini，再次 GET 应回读到同样的列表；④ 换行注入必须 422。

    def test_get_defaults_to_builtin(self, app_env: types.SimpleNamespace) -> None:
        # 缺省：config.ini 无「自定义画质选项」键 → 返回 builtin 全集，且 builtin 字段也在
        token = _login(app_env.client)
        resp = app_env.client.get("/api/rooms/qualities", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        body = resp.json()
        from src.web_config import BUILTIN_QUALITIES

        assert body["options"] == list(BUILTIN_QUALITIES)
        assert body["builtin"] == list(BUILTIN_QUALITIES)

    def test_put_persists_to_config_ini(self, app_env: types.SimpleNamespace) -> None:
        # 写回的选项必须落到 config.ini [录制设置] 自定义画质选项(逗号分隔)
        token = _login(app_env.client)
        resp = app_env.client.put(
            "/api/rooms/qualities",
            json={"options": ["超清", "高清", "流畅"]},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["options"] == ["超清", "高清", "流畅"]
        text = app_env.cfg.read_text(encoding="utf-8-sig")
        assert "自定义画质选项(逗号分隔) = 超清,高清,流畅" in text
        # 持久化后再读仍能复现
        resp2 = app_env.client.get("/api/rooms/qualities", headers={"Authorization": f"Bearer {token}"})
        assert resp2.json()["options"] == ["超清", "高清", "流畅"]

    def test_put_drops_unknown_quality_silently(self, app_env: types.SimpleNamespace) -> None:
        # 白名单外的画质名（如 "2K"）不应写入；后端用规范化列表兜底，避免静默丢失用户输入
        token = _login(app_env.client)
        resp = app_env.client.put(
            "/api/rooms/qualities",
            json={"options": ["超清", "2K", "流畅"]},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["options"] == ["超清", "流畅"]

    def test_put_newline_rejected_422(self, app_env: types.SimpleNamespace) -> None:
        # 换行注入与 format_url_line / validate_config_target 同款防护（C3）
        token = _login(app_env.client)
        resp = app_env.client.put(
            "/api/rooms/qualities",
            json={"options": ["超清\n# evil"]},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 422
