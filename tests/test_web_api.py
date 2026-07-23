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


def test_rooms_update_enabled_room(client, tmp_url_config):
    """更新一个启用中的直播间：行被替换、enabled 保持 True、url/quality/name 更新。"""
    r = client.put("/api/rooms", json={
        "old_url": "https://live.douyin.com/123",
        "url": "https://live.douyin.com/9999",
        "quality": "高清",
        "name": "新主播",
    })
    assert r.status_code == 200
    from src.web_config import parse_url_config
    rooms = parse_url_config(tmp_url_config)
    updated = next(rr for rr in rooms if rr["url"] == "https://live.douyin.com/9999")
    assert updated["enabled"] is True
    assert updated["quality"] == "高清"
    assert updated["name"] == "新主播"
    # 旧 URL 不再存在
    assert not any(rr["url"] == "https://live.douyin.com/123" for rr in rooms)


def test_rooms_update_disabled_room_no_double_hash(client, tmp_url_config):
    """回归 I-1：更新一个被注释（禁用）的直播间，不得产生双重 #。"""
    r = client.put("/api/rooms", json={
        "old_url": "https://www.huya.com/789",
        "url": "https://www.huya.com/new",
        "quality": "超清",
        "name": "虎牙新",
    })
    assert r.status_code == 200
    # 直接读文件，确认没有 "# #" 双井号
    text = tmp_url_config.read_text(encoding="utf-8")
    assert "# #" not in text
    from src.web_config import parse_url_config
    rooms = parse_url_config(tmp_url_config)
    updated = next(rr for rr in rooms if rr["url"] == "https://www.huya.com/new")
    assert updated["enabled"] is False  # 保持禁用状态
    assert updated["quality"] == "超清"
    assert updated["name"] == "虎牙新"


def test_rooms_update_not_found_404(client):
    r = client.put("/api/rooms", json={
        "old_url": "https://example.com/nope",
        "url": "https://example.com/x",
    })
    assert r.status_code == 404


def test_rooms_list(client, tmp_url_config):
    r = client.get("/api/rooms")
    assert r.status_code == 200
    rooms = r.json()
    assert len(rooms) == 5
    urls = [room["url"] for room in rooms]
    assert "https://live.douyin.com/123" in urls


def test_rooms_add(client, tmp_url_config):
    r = client.post("/api/rooms", json={"url": "https://live.douyin.com/new"})
    assert r.status_code == 200
    from src.web_config import parse_url_config
    rooms = parse_url_config(tmp_url_config)
    assert any(r2["url"] == "https://live.douyin.com/new" for r2 in rooms)


def test_rooms_add_duplicate_409(client, tmp_url_config):
    r = client.post("/api/rooms", json={"url": "https://live.douyin.com/123"})
    assert r.status_code == 409


def test_rooms_add_with_quality_and_name(client, tmp_url_config):
    r = client.post("/api/rooms", json={
        "url": "https://live.bilibili.com/999",
        "quality": "超清",
        "name": "测试"
    })
    assert r.status_code == 200
    from src.web_config import parse_url_config
    rooms = parse_url_config(tmp_url_config)
    added = next(r2 for r2 in rooms if r2["url"] == "https://live.bilibili.com/999")
    assert added["quality"] == "超清"
    assert added["name"] == "测试"


def test_rooms_delete(client, tmp_url_config):
    r = client.delete("/api/rooms?url=https://live.douyin.com/123")
    assert r.status_code == 200
    from src.web_config import parse_url_config
    rooms = parse_url_config(tmp_url_config)
    assert not any(r2["url"] == "https://live.douyin.com/123" for r2 in rooms)


def test_rooms_delete_not_found_404(client):
    r = client.delete("/api/rooms?url=https://example.com/nope")
    assert r.status_code == 404


def test_rooms_toggle_disable(client, tmp_url_config):
    r = client.post("/api/rooms/toggle", json={
        "url": "https://live.douyin.com/123",
        "enable": False
    })
    assert r.status_code == 200
    from src.web_config import parse_url_config
    rooms = parse_url_config(tmp_url_config)
    target = next(r2 for r2 in rooms if r2["url"] == "https://live.douyin.com/123")
    assert target["enabled"] is False


def test_rooms_toggle_enable(client, tmp_url_config):
    # huya 原本是注释（禁用）
    r = client.post("/api/rooms/toggle", json={
        "url": "https://www.huya.com/789",
        "enable": True
    })
    assert r.status_code == 200
    from src.web_config import parse_url_config
    rooms = parse_url_config(tmp_url_config)
    target = next(r2 for r2 in rooms if r2["url"] == "https://www.huya.com/789")
    assert target["enabled"] is True


def test_config_get(client, tmp_config_ini):
    r = client.get("/api/config")
    assert r.status_code == 200
    sections = r.json()
    assert "录制设置" in sections
    assert sections["录制设置"]["循环时间(秒)"] == "300"
    # Cookie 非空值脱敏
    assert sections["Cookie"]["抖音cookie"] == "***"
    # 空值不脱敏
    assert sections["账号密码"]["sooplive账号"] == ""


def test_config_update(client, tmp_config_ini):
    r = client.put("/api/config", json={
        "section": "录制设置",
        "key": "循环时间(秒)",
        "value": "60"
    })
    assert r.status_code == 200
    # 回读验证
    r = client.get("/api/config")
    assert r.json()["录制设置"]["循环时间(秒)"] == "60"


def test_config_update_sensitive_unmasks(client, tmp_config_ini):
    # 写入敏感字段后回读应显示新值（非 ***），因为脱敏仅在前端展示层
    # 但 GET 始终脱敏非空值，所以这里验证写入成功即可
    r = client.put("/api/config", json={
        "section": "Cookie",
        "key": "抖音cookie",
        "value": "newcookie"
    })
    assert r.status_code == 200
    # 直接读文件验证（update_config 以 utf-8-sig 写入，故以 utf-8-sig 读回）
    import configparser
    parser = configparser.ConfigParser(interpolation=None)
    parser.read(tmp_config_ini, encoding="utf-8-sig")
    assert parser["Cookie"]["抖音cookie"] == "newcookie"


def test_config_update_preserves_comments(client, tmp_config_ini):
    # I4: 注释保留式更新——写入前后注释行都应存在
    text_before = tmp_config_ini.read_text(encoding="utf-8-sig")
    # fixture 无注释，先手工加一条注释到录制设置节
    text_before = text_before.replace(
        "[录制设置]\n", "[录制设置]\n# 这是注释\n"
    )
    tmp_config_ini.write_text(text_before, encoding="utf-8")
    r = client.put("/api/config", json={
        "section": "录制设置",
        "key": "循环时间(秒)",
        "value": "120"
    })
    assert r.status_code == 200
    text_after = tmp_config_ini.read_text(encoding="utf-8-sig")
    assert "# 这是注释" in text_after  # 注释保留
    assert "循环时间(秒) = 120" in text_after  # 值已更新


def test_config_update_missing_key_returns_404(client, tmp_config_ini):
    # I5: 未找到对应配置项时返回 404 而非 {ok:true}
    r = client.put("/api/config", json={
        "section": "录制设置",
        "key": "不存在的键",
        "value": "1"
    })
    assert r.status_code == 404


def test_config_update_missing_section_returns_404(client, tmp_config_ini):
    r = client.put("/api/config", json={
        "section": "不存在的节",
        "key": "循环时间(秒)",
        "value": "1"
    })
    assert r.status_code == 404


def test_files_list_root(client):
    r = client.get("/api/files")
    assert r.status_code == 200
    items = r.json()
    names = [i["name"] for i in items]
    assert "sub" in names
    assert "root.mp4" in names


def test_files_list_subdir(client):
    r = client.get("/api/files?path=sub")
    assert r.status_code == 200
    items = r.json()
    assert any(i["name"] == "a.ts" for i in items)


def test_files_traversal_blocked_400(client):
    r = client.get("/api/files?path=../../etc")
    assert r.status_code == 400


def test_files_download_traversal_blocked_400(client):
    r = client.get("/api/files/download?path=../../etc/passwd")
    assert r.status_code == 400


def test_files_download_ok(client):
    r = client.get("/api/files/download?path=root.mp4")
    assert r.status_code == 200
    assert r.content == b"\x00" * 200


def test_logs_get(client):
    r = client.get("/api/logs?lines=2")
    assert r.status_code == 200
    data = r.json()
    assert len(data["lines"]) == 2
    assert data["lines"][0].strip() == "line2"


def test_get_status_engine_alive_field_present():
    """get_status() 返回 engine_alive 字段。"""
    import main
    # 默认 _recorder_thread 为 None（CLI 模式），视作存活
    old = main._recorder_thread
    main._recorder_thread = None
    try:
        s = main.get_status()
        assert "engine_alive" in s
        assert s["engine_alive"] is True
    finally:
        main._recorder_thread = old


def test_get_status_engine_dead_when_thread_not_alive():
    """守护线程已结束时 engine_alive 为 False。"""
    import main
    import threading
    t = threading.Thread(target=lambda: None, daemon=True)
    t.start()
    t.join()  # 等线程结束 → is_alive() False
    old = main._recorder_thread
    main._recorder_thread = t
    try:
        s = main.get_status()
        assert s["engine_alive"] is False
    finally:
        main._recorder_thread = old


def test_config_change_password_revokes_tokens(web_app, tmp_config_ini: Path):
    """修改 web_password 后，旧 token 立即失效。"""
    import configparser
    # 先开启认证并设置密码
    parser = configparser.ConfigParser(interpolation=None)
    parser.read(tmp_config_ini, encoding="utf-8")
    parser.set("Web", "web_auth_enable", "true")
    parser.set("Web", "web_password", "oldpass")
    with tmp_config_ini.open("w", encoding="utf-8") as f:
        parser.write(f)

    app, _ = web_app
    client = TestClient(app)
    # 登录拿 token
    r = client.post("/api/login", json={"password": "oldpass"})
    assert r.status_code == 200
    token = r.json()["token"]
    # token 可用
    with mock.patch("main.get_status", return_value={"version": "v"}):
        r = client.get("/api/status", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    # 修改密码（请求本身需携带有效 token）
    r = client.put("/api/config", json={
        "section": "Web", "key": "web_password", "value": "newpass"
    }, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    # 旧 token 应失效
    with mock.patch("main.get_status", return_value={"version": "v"}):
        r = client.get("/api/status", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 401
    # 新密码登录可用
    r = client.post("/api/login", json={"password": "newpass"})
    assert r.status_code == 200


def test_config_change_non_password_does_not_revoke(web_app, tmp_config_ini: Path):
    """修改非密码项不吊销 token。"""
    import configparser
    parser = configparser.ConfigParser(interpolation=None)
    parser.read(tmp_config_ini, encoding="utf-8")
    parser.set("Web", "web_auth_enable", "true")
    parser.set("Web", "web_password", "pass1")
    with tmp_config_ini.open("w", encoding="utf-8") as f:
        parser.write(f)

    app, _ = web_app
    client = TestClient(app)
    r = client.post("/api/login", json={"password": "pass1"})
    token = r.json()["token"]
    # 修改 web_port（非密码，请求需携带有效 token）
    r = client.put("/api/config", json={
        "section": "Web", "key": "web_port", "value": "9000"
    }, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    # token 仍有效
    with mock.patch("main.get_status", return_value={"version": "v"}):
        r = client.get("/api/status", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200


def test_password_change_clears_tokens_safely(web_app, tmp_config_ini: Path):
    """密码变更清空 token 时不引发并发错误（锁正确性冒烟）。"""
    import configparser
    import threading
    parser = configparser.ConfigParser(interpolation=None)
    parser.read(tmp_config_ini, encoding="utf-8")
    parser.set("Web", "web_auth_enable", "true")
    parser.set("Web", "web_password", "pass1")
    with tmp_config_ini.open("w", encoding="utf-8") as f:
        parser.write(f)

    app, _ = web_app
    client = TestClient(app)
    # 登录拿几个 token
    tokens = []
    for _ in range(5):
        r = client.post("/api/login", json={"password": "pass1"})
        tokens.append(r.json()["token"])
    # 并发：一边轮询 /api/status（触发 middleware 读 _tokens），一边改密码（clear _tokens）
    errors = []
    def poll_status():
        try:
            for _ in range(20):
                client.get("/api/status", headers={"Authorization": f"Bearer {tokens[0]}"})
        except Exception as e:
            errors.append(e)
    def change_password():
        try:
            for i in range(5):
                client.put("/api/config", json={
                    "section": "Web", "key": "web_password", "value": f"pass{i+2}"
                }, headers={"Authorization": f"Bearer {tokens[0]}"})
        except Exception as e:
            errors.append(e)
    t1 = threading.Thread(target=poll_status)
    t2 = threading.Thread(target=change_password)
    t1.start(); t2.start()
    t1.join(); t2.join()
    # 不应有 RuntimeError: dictionary changed size during iteration
    runtime_errors = [e for e in errors if "changed size" in str(e)]
    assert not runtime_errors, f"并发访问 _tokens 触发 RuntimeError: {runtime_errors}"
