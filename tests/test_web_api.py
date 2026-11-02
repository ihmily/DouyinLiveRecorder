# -*- coding: utf-8 -*-
# src/web_api.py 测试：Web 面板 Starlette 应用的安全与健壮性回归。聚焦七类契约 ——
# ① 鉴权中间件（启用认证时所有 /api/* 须 401，禁用时开放）；② 登录限流（防 XFF 伪造绕过、
# 失败计数与成功重置、密码变更吊销 token）；③ 写接口的注入/越权防护（quality 含换行被 422、
# 危险配置键被 403 阻断 RCE）；④ 并发安全（TOCTOU 重复添加房间）与副作用（停止录制触发日志归档、
# 语言即时切换写回 config）；⑤ 房间写入口裁决一致（POST/PUT/quality 对同一载荷同一结论）；
# ⑥ Host/Origin 白名单与「非回环 + 无认证」每请求不变量；⑦ 事件循环非阻塞与内部异常不回显——
# 各契约的回归编号（/04、/36/39 等）见对应 Test* 类注释。
# 测试策略：用 types.ModuleType 注入轻量 fake main（避免导入真实 main.py 触发的 FFmpeg/Node 检查
# 等重副作用，web_api 仅在请求处理时才 import main、仅用到 file_update_lock 等符号）；通过
# create_app 注入临时 config/URL_config/downloads/logs 目录隔离文件系统；用 Starlette TestClient
# 同步驱动异步路由，全程不监听端口。用例内 C4/C8/C10/C11 等为安全/健壮性回归编号（见 CODE_WIKI 变更记录）。
#
# 两条与被测代码同步演进的环境约束：
# · TestClient 一律带 base_url="http://127.0.0.1:8000"：Host 头必须落在服务端推导的
#   允许名单内，默认 base_url 的 "testserver" 会被 400 拒（单标签名亦被放行，但显式写清来源比依赖兜底规则更可判定）。
# · 全程打桩 DNS seam（_resolve_host_ips）：不打桩则「live.douyin.com 是否放行」随宿主
#   网络可达性漂移；桩的判据与边界见 _stub_public_dns，分类逻辑走真实代码（tests/test_web_config.py 逐条锁定）。

import os
import sys
import threading
import types
from collections.abc import Generator
from pathlib import Path
from typing import Any, cast

import pytest
from httpx import Response
from starlette.testclient import TestClient

# 面板对外声称的访问地址（同时决定 Host 允许名单），与 _write_web_section 里的 web_host 一致
_BASE_URL = "http://127.0.0.1:8000"


@pytest.fixture(autouse=True)
def _stub_public_dns(monkeypatch: pytest.MonkeyPatch) -> None:
    # 把「域名 → IP」这一步固定为公网可解析：房间地址校验在写入前会解析 host，
    # 不桩化会让本文件的用例随宿主 DNS 可用性漂移。114.114.114.114 是真实公网 DNS 地址，
    # 不在任何回环/私网/保留段内（TEST-NET 段在 3.14 的 ipaddress 里算私网，不可用作本桩）。
    from src import web_config as wc

    def _fake_resolve(host: str) -> list[str]:
        return ["114.114.114.114"]

    monkeypatch.setattr(wc, "_resolve_host_ips", _fake_resolve)


def _install_fake_main() -> types.ModuleType:
    # 注入轻量 fake main，避免导入真实 main.py 触发 FFmpeg/Node 检查等重副作用（完整口径见模块头「测试策略」）。
    fake = types.ModuleType("main")
    # types.ModuleType 不接受静态注解的任意属性赋值，用 setattr 注入测试替身符号
    # 与生产同源：main.file_update_lock 是 RLock（config_io.delete_line 内部还会再取一次
    # 同一把锁，端点持锁调用它时若换成非重入 Lock 就是自死锁，见 web_api.delete_room）
    setattr(fake, "file_update_lock", threading.RLock())
    setattr(fake, "running_list", [])
    setattr(fake, "record_state_lock", threading.Lock())
    setattr(fake, "max_request_lock", threading.Lock())
    setattr(fake, "recording", set())
    setattr(fake, "recording_enabled", False)
    # config_io.delete_line 在运行时读 main.text_encoding / url_config_file / ini_URL_content，
    # 而它一旦被首次导入就会永久绑定当时那个 fake（模块级 `import main`）。
    # 三个属性在每个 fake 上都得存在，否则跨用例复用旧 fake 的 delete_line 会 AttributeError。
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


def _write_web_section(
    cfg_path: Path,
    *,
    auth: str = "true",
    password: str = "",
    trusted_proxy: str = "",
    host: str = "127.0.0.1",
) -> None:
    # 写入 [Web] 节配置（password 传哈希值或空）。
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "[Web]",
        f"web_host = {host}",
        "web_port = 8000",
        f"web_auth_enable = {auth}",
        f"web_password = {password}",
        f"web_trusted_proxy = {trusted_proxy}",
    ]
    cfg_path.write_text("\n".join(lines) + "\n", encoding="utf-8-sig")


def _reset_web_api_state(wa: types.ModuleType) -> None:
    # 逐个用例把 web_api 的进程级状态清干净：token 表、限流表（含该全局失败预算）、
    # 中间件的配置缓存、该状态快照缓存。这些缓存/计数器都是模块级全局，
    # 跨用例残留会让「第 N 次请求应当 429」这类断言随机漂移。
    with wa._tokens_lock:
        wa._tokens.clear()
    with wa._FAILED_LOGINS_LOCK:
        wa._FAILED_LOGINS.clear()
        wa._GLOBAL_LOGIN_FAILURES.clear()
    wa._invalidate_web_cfg_cache()
    with wa._status_lock:
        # 模块全局一律经 setattr 写：types.ModuleType 的静态注解不接受任意属性赋值
        setattr(wa, "_status_cache", None)
        setattr(wa, "_status_cache_at", 0.0)
        setattr(wa, "_status_inflight", False)
        setattr(wa, "_status_inflight_since", 0.0)


@pytest.fixture(scope="function")
def app_env(tmp_path: Path, fake_main: types.ModuleType) -> Generator[types.SimpleNamespace, None, None]:
    from src import web_api as wa

    # 模块级全局不随 tmp_path / function 作用域重建，必须显式清（判据见 _reset_web_api_state）
    _reset_web_api_state(wa)

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
    client = TestClient(app, base_url=_BASE_URL)
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
        # 另一半契约（认证关闭时 /api/* 全部 200）见同类的 test_api_open_when_auth_disabled，
        # 两条合起来才锁住「开关双向生效」而不是「默认全拒 + 例外放行」的单侧实现。
        resp = app_env.client.get("/api/rooms")
        assert resp.status_code == 401

    def test_static_panel_reachable_without_trailing_slash(self, app_env: types.SimpleNamespace) -> None:
        # 行为锁：认证开启时 GET `/web`（无尾斜杠）不得被鉴权拦成 401。
        # 中间件由 BaseHTTPMiddleware 包在 StaticFiles **之外**，StaticFiles 自己那条「/web → /web/」
        # 的 307 要等中间件判完才有机会执行，所以 401 落在第一跳而非跳转之后（实测：
        # auth=true 无 token → /web 直接 401 {"detail":"unauthorized"}；带 token 或 auth=false → 307；/web/ 一律 200）。
        # 断言取「跳转语义 + 跟随后拿到首页」两级行为，不钉源码里的路径字面量：
        # 白名单换成任何等价实现都仍应通过，删掉这条放行则两级同时转红。
        strict_client = TestClient(app_env.app, base_url=_BASE_URL, follow_redirects=False)
        try:
            resp = strict_client.get("/web")
            assert resp.status_code == 307, f"/web 被鉴权拦在跳转之前: {resp.status_code} {resp.text}"
            assert str(resp.headers.get("location", "")).endswith("/web/"), dict(resp.headers)
        finally:
            strict_client.close()
        assert app_env.client.get("/web").status_code == 200
        # 反向边界（不得把这条修成「/web 开头一律免鉴权、顺手放宽接口面」）：
        # 接口仍 401，登录页之外的公开路径也不受本条影响。
        assert app_env.client.get("/api/rooms").status_code == 401


class TestSecurityHeaders:
    # 守护安全响应头中间件：放行/拒绝两条路径均须附加 nosniff + DENY 帧选项。
    # 防止通过 MIME 嗅探把 JSON 响应当 HTML 渲染（XSS 攻击面），以及点击劫持。
    def test_401_response_includes_security_headers(self, app_env: types.SimpleNamespace) -> None:
        resp = app_env.client.get("/api/rooms")  # 无 token → 401
        assert resp.status_code == 401
        assert resp.headers.get("X-Content-Type-Options") == "nosniff"
        assert resp.headers.get("X-Frame-Options") == "DENY"

    def test_200_response_includes_security_headers(self, app_env: types.SimpleNamespace) -> None:
        # 登录成功后 200 响应也须带头（防登录页被嵌入 iframe 钓鱼）
        resp = app_env.client.post("/api/login", json={"password": "secret123"})
        assert resp.status_code == 200
        assert resp.headers.get("X-Content-Type-Options") == "nosniff"
        assert resp.headers.get("X-Frame-Options") == "DENY"

    def test_auth_status_exposes_disabled_warning(self, tmp_path: Path, fake_main: types.ModuleType) -> None:
        # 公开端点 /api/auth/status 在认证关闭时返回 warning，前端可据此展示警示横幅
        from src import web_api as wa

        cfg = tmp_path / "config.ini"
        _write_web_section(cfg, auth="false", password="")
        app = wa.create_app(
            config_file=str(cfg),
            url_config_file=str(tmp_path / "u.ini"),
            downloads_root=str(tmp_path),
            logs_dir=str(tmp_path),
        )
        _reset_web_api_state(wa)
        client = TestClient(app, base_url=_BASE_URL)
        try:
            resp = client.get("/api/auth/status")
            assert resp.status_code == 200
            body = resp.json()
            assert body["auth_required"] is False
            assert body["warning"] is not None and "未启用" in body["warning"]
        finally:
            client.close()

    def test_auth_status_no_warning_when_enabled(self, app_env: types.SimpleNamespace) -> None:
        # 认证开启时 warning 字段为 None，避免误导
        resp = app_env.client.get("/api/auth/status")
        assert resp.status_code == 200
        body = resp.json()
        assert body["auth_required"] is True
        assert body["warning"] is None

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
        _reset_web_api_state(wa)
        client = TestClient(app, base_url=_BASE_URL)
        try:
            resp = client.get("/api/rooms")
            assert resp.status_code == 200
        finally:
            client.close()


class TestHealthEndpoint:
    # 守护探活端点契约：CI 冒烟步骤（.github/workflows/ci.yml 的 test job）与
    # scripts/smoke_web.json 都靠它判定「面板已可用」，断言形状必须与配置一致。
    def test_health_ok_when_auth_enabled(self, app_env: types.SimpleNamespace) -> None:
        # 认证开启（app_env 固定 auth=true）时 /health 仍须 200：探活方不持凭据，
        # 若被中间件的 fail-closed 命中会返回 401，CI 会把「服务好好的」误判成挂了。
        resp = app_env.client.get("/health")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        # version 与 /health 数据同源（Starlette 无 FastAPI 的 app.version 元数据，以 web_api._APP_VERSION
        # 为同一事实），避免面板与探活报告各写一份版本号
        assert body["version"] == app_env.wa._APP_VERSION

    def test_health_ignores_engine_state(self, app_env: types.SimpleNamespace, fake_main: types.ModuleType) -> None:
        # 探活不得掺入录制引擎健康度：把引擎状态接口打成抛异常（/api/status 会自行
        # 包成 {"error": ...}，见 get_status），/health 仍须 200。否则「引擎报错」与
        # 「面板挂了」在 CI 里无法区分，门禁会在只需重启面板的场景下误红。
        # 之后 error 字段是固定 code 而非异常原文，故断言同时锁住「不外泄 engine down」。
        def _boom() -> dict[str, object]:
            raise RuntimeError("engine down")

        setattr(fake_main, "get_status", _boom)
        # 本用例里认证是开着的，/api/status 需 Bearer 才能进路由（不带会被中间件 401）
        headers = {"Authorization": f"Bearer {_login(app_env.client)}"}
        body = app_env.client.get("/api/status", headers=headers).json()
        assert body.get("error") == "status_unavailable"
        assert "engine down" not in str(body)
        resp = app_env.client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


class TestStatusNonBlocking:
    # 状态快照不得在事件循环里做阻塞采样。三条契约：
    # ① 一次卡死的采样只让 /api/status 回**陈旧快照 + stale:true**，其他端点照常响应；
    # ② TTL 内的连续轮询只触发一次真实采样（磁盘容量这类秒级值不必每次触盘）；
    # ③ 采样失败期间不会每个轮询都再起一条线程（单飞门）。
    def test_slow_status_does_not_stall_panel(
        self, app_env: types.SimpleNamespace, fake_main: types.ModuleType
    ) -> None:
        gate = threading.Event()
        seen: list[int] = []

        def _slow() -> dict[str, object]:
            seen.append(1)
            _ = gate.wait(timeout=10)
            return {"monitoring": 1}

        setattr(fake_main, "get_status", _slow)
        headers = {"Authorization": f"Bearer {_login(app_env.client)}"}
        try:
            # 第一次请求：采样线程被 gate 卡住 → 超时后回陈旧快照（此处尚无缓存 → 只有错误码）
            resp = app_env.client.get("/api/status", headers=headers)
            assert resp.status_code == 200
            body = resp.json()
            assert body.get("stale") is True
            assert body.get("error") == "status_unavailable"
            # 面板未被拖住：同一时间另一个端点仍能正常返回（旧实现里这一步会一起卡住）
            assert app_env.client.get("/api/rooms", headers=headers).status_code == 200
        finally:
            gate.set()

    def test_status_cached_within_ttl(self, app_env: types.SimpleNamespace, fake_main: types.ModuleType) -> None:
        # TTL 窗口内连续 5 次轮询只采样一次：每次轮询都做 disk_usage + 抢跨线程锁会随标签页数线性叠加磁盘 IO 压力。
        calls: list[int] = []

        def _counting() -> dict[str, object]:
            calls.append(1)
            return {"monitoring": len(calls)}

        setattr(fake_main, "get_status", _counting)
        headers = {"Authorization": f"Bearer {_login(app_env.client)}"}
        for _ in range(5):
            resp = app_env.client.get("/api/status", headers=headers)
            assert resp.status_code == 200
            assert resp.json()["monitoring"] == 1
        assert len(calls) == 1

    def test_status_error_is_not_cached_and_recovers(
        self, app_env: types.SimpleNamespace, fake_main: types.ModuleType
    ) -> None:
        # 失败结果不进缓存：引擎恢复后下一次轮询即拿到新鲜值（把 error 当快照缓存会让面板连续 TTL 周期显示过期数据）。
        state = {"n": 0}

        def _flaky() -> dict[str, object]:
            state["n"] += 1
            if state["n"] == 1:
                raise OSError(13, "Permission denied")
            return {"monitoring": 7}

        setattr(fake_main, "get_status", _flaky)
        headers = {"Authorization": f"Bearer {_login(app_env.client)}"}
        first = app_env.client.get("/api/status", headers=headers).json()
        assert first.get("error") == "status_unavailable"
        assert "Permission denied" not in str(first)
        # 越过 TTL，强制第二次真实采样（失败结果本就未被缓存，这里只是让意图显式）
        app_env.wa._status_cache = None
        app_env.wa._status_cache_at = 0.0
        second = app_env.client.get("/api/status", headers=headers).json()
        assert second.get("monitoring") == 7
        assert "error" not in second


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

    def test_trusted_proxy_peels_xff_right_to_left(self, app_env: types.SimpleNamespace) -> None:
        # 即使直连对端可信，XFF 的**最左值**仍是请求方自填的（可写 66.66.66.66），
        # 按最左值计键 → 一台真实客户端可被拆成无数个失败窗口。
        # 正确语义是从右往左剥：跳过仍属可信代理的条目，第一个非可信地址才是客户端。
        # 这里两条请求的最左值不同、右端客户端相同 → 必须共用同一个失败窗口。
        from src import web_api as wa

        _write_web_section(
            app_env.cfg,
            auth="true",
            password=wa.hash_web_password("secret123"),
            trusted_proxy="203.0.113.7, 10.0.0.2",
        )
        client = app_env.client
        codes = []
        for left in ("66.66.66.66", "77.77.77.77", "88.88.88.88", "99.99.99.99", "1.1.1.1"):
            resp = client.post(
                "/api/login",
                json={"password": "wrong"},
                headers={"X-Forwarded-For": f"{left}, 203.0.113.7, 10.0.0.2"},
            )
            codes.append(resp.status_code)
        assert codes == [401] * 5, codes
        # 第 6 次落到**同一个**客户端键上 → 触发限流（证明五条确实共用了窗口）
        resp = client.post(
            "/api/login",
            json={"password": "wrong"},
            headers={"X-Forwarded-For": "123.123.123.123, 203.0.113.7, 10.0.0.2"},
        )
        assert resp.status_code == 429

    def test_spoofed_xff_leftmost_never_used_as_bucket_key(self, app_env: types.SimpleNamespace) -> None:
        # 直接断言：直连对端不可信时，伪造的 XFF 不得成为限流键的一部分
        # （旧实现把 scope["client"] 当直连对端用，而 uvicorn 默认已用 XFF 最左值覆盖它）。
        from src import web_api as wa

        buckets: list[str] = []
        for i in range(3):
            resp = app_env.client.post(
                "/api/login", json={"password": "wrong"}, headers={"X-Forwarded-For": f"9.9.{i}.9, 8.8.8.8"}
            )
            assert resp.status_code == 401
        buckets = list(wa._FAILED_LOGINS.keys())
        assert buckets == ["testclient"], f"伪造的 XFF 被当成了限流键: {buckets}"

    def test_global_failure_budget_caps_unbounded_buckets(self, app_env: types.SimpleNamespace) -> None:
        # 按 IP 计数存在对称失效面——攻击者换键即换窗口（Docker/反代下 client.host
        # 可被随意伪造时尤其明显）。全局失败预算与键无关，超预算即整站 429。
        from src import web_api as wa

        _write_web_section(
            app_env.cfg,
            auth="true",
            password=wa.hash_web_password("secret123"),
            trusted_proxy="1.1.1.1,1.1.1.2,1.1.1.3",  # 三个「可信代理」→ 三个独立键
        )
        # 直接把全局预算灌满（等价于大量分布式失败，且每个键都没到 5 次）
        # 同步：条目形态为 (时刻, 来源)，这里灌的是**别的来源**的条目，
        # 与 login 侧 test_successful_login_reclaims_only_own_global_entries 构成正反配对
        now = __import__("time").time()
        with wa._FAILED_LOGINS_LOCK:
            for _ in range(wa._LOGIN_GLOBAL_MAX_FAILURES):
                wa._GLOBAL_LOGIN_FAILURES.append((now, "1.1.1.9"))
        resp = app_env.client.post("/api/login", json={"password": "wrong"}, headers={"X-Forwarded-For": "1.1.1.1"})
        assert resp.status_code == 429

    def test_successful_login_reclaims_only_own_global_entries(self, app_env: types.SimpleNamespace) -> None:
        # 全局预算按 (时刻, 来源) 记账后，成功登录只回收**本来源**挣出的条目。
        # 两条断言各封一个退化方向：全清 → 攻击者可借自己成功登录重置整站预算；
        # 全不回收 → testclient 自己贡献的份额持续累计，最终把所有合法用户 429 在门外直到窗口滑完。
        import time as _time

        from src import web_api as wa

        now = _time.time()
        with wa._FAILED_LOGINS_LOCK:
            for _ in range(30):
                wa._GLOBAL_LOGIN_FAILURES.append((now, "testclient"))
            for _ in range(5):
                wa._GLOBAL_LOGIN_FAILURES.append((now, "203.0.113.7"))
        resp = app_env.client.post("/api/login", json={"password": "secret123"})
        assert resp.status_code == 200, resp.text
        with wa._FAILED_LOGINS_LOCK:
            assert [e for e in wa._GLOBAL_LOGIN_FAILURES if e[1] == "testclient"] == [], "本来源份额未回收"
            assert (
                len([e for e in wa._GLOBAL_LOGIN_FAILURES if e[1] == "203.0.113.7"]) == 5
            ), "他人份额被连带清空（全清退化）"


class TestRoomWriteParity:
    # PUT /api/rooms 曾**完全不做**房间校验（POST 与 PUT/quality 都做），
    # 于是它成为绕过 SSRF/任意 scheme/画质白名单的第二条写入口。
    # 校验现已下沉进 format_url_line（唯一写入口），本类锁「同一载荷在两个写入口裁决一致」。

    # 载荷集合：内网/元数据/任意 scheme/换行注入/白名单外档位
    PARITY_PAYLOADS: list[dict[str, object]] = [
        {"url": "http://127.0.0.1:8000/x?a=.flv"},
        {"url": "http://169.254.169.254/latest/meta-data/?x=.m3u8"},
        {"url": "http://2130706433/x?a=.flv"},
        {"url": "http://[fe80::1]:8080/x?a=.flv"},
        {"url": "http://100.100.100.200/latest/meta-data/?x=.m3u8"},
        {"url": "file:///etc/passwd?a=.flv"},
        {"url": "https://live.douyin.com/1", "quality": "8K无敌"},
        {"url": "https://live.douyin.com/2\n# evil"},
        {"url": "https://live.douyin.com/3", "name": "主\n播"},
        {"url": "https://live.douyin.com/ok", "quality": "超清"},
    ]

    def test_put_to_existing_url_returns_409_without_duplicate_line(
        self, app_env: types.SimpleNamespace, fake_main: types.ModuleType
    ) -> None:
        # 行为锁：PUT 改写为已存在的 URL 必须回 409，且文件不出现重复 URL 行（原实现漏检，
        # 成功后删除/画质操作命中不确定）。仅改画质/名字（new_url == old_url）不得被误杀。
        token = _login(app_env.client)
        headers = {"Authorization": f"Bearer {token}"}

        def _fake_update_file(path: str, old_str: str, new_str: str, **kw: str) -> str:
            # 端点在 update_file 后会重解析文件做「真写入了」裁决，替身必须
            # 真的改写文件，否则同址更新分支被判 500
            p = Path(path)
            text = p.read_text(encoding="utf-8-sig")
            p.write_text(text.replace(old_str, new_str), encoding="utf-8-sig")
            return new_str

        setattr(fake_main, "update_file", _fake_update_file)
        assert (
            app_env.client.post("/api/rooms", json={"url": "https://live.douyin.com/a"}, headers=headers).status_code
            == 200
        )
        assert (
            app_env.client.post("/api/rooms", json={"url": "https://live.douyin.com/b"}, headers=headers).status_code
            == 200
        )
        resp = app_env.client.put(
            "/api/rooms",
            json={"old_url": "https://live.douyin.com/b", "url": "https://live.douyin.com/a"},
            headers=headers,
        )
        assert resp.status_code == 409
        text = app_env.url_cfg.read_text(encoding="utf-8-sig")
        assert text.count("live.douyin.com/a") == 1
        assert "live.douyin.com/b" in text
        # 同址更新（只改画质）不受查重影响
        resp_same = app_env.client.put(
            "/api/rooms",
            json={"old_url": "https://live.douyin.com/a", "url": "https://live.douyin.com/a", "quality": "超清"},
            headers=headers,
        )
        assert resp_same.status_code == 200

    def test_put_and_post_reach_same_verdict(self, app_env: types.SimpleNamespace, fake_main: types.ModuleType) -> None:
        token = _login(app_env.client)
        headers = {"Authorization": f"Bearer {token}"}
        # PUT 的成功分支要经引擎的 update_file 改写整行；本用例裁决的是「校验结论是否一致」，
        # 故给 fake main 一个最小替身（生产里它是 main.py 再导出的 config_io.update_file）。
        writes: list[str] = []

        def _fake_update_file(path: str, old_str: str, new_str: str, **kw: str) -> str:
            writes.append(new_str)
            return new_str

        setattr(fake_main, "update_file", _fake_update_file)
        # 先建一个可被 PUT 命中的既有房间（PUT 的语义是「改写已有行」）
        seed = "https://live.douyin.com/seed"
        assert app_env.client.post("/api/rooms", json={"url": seed}, headers=headers).status_code == 200
        for payload in self.PARITY_PAYLOADS:
            body = cast("dict[str, str]", payload)
            post = app_env.client.post("/api/rooms", json=body, headers=headers)
            put = app_env.client.put("/api/rooms", json={**body, "old_url": seed}, headers=headers)
            # POST 的 409（重复）与 PUT 的 404/200 属各自语义，其余裁决必须逐字一致。
            # [历史注] 该漏检修复后（判据全文见上方 test_put_to_existing_url_returns_409_without_duplicate_line），
            # PUT 对「新 URL 与其它房间重复」同样回 409，故 PUT=409 恒为合法裁决。
            same = (
                post.status_code == put.status_code
                or (post.status_code == 409 and put.status_code == 200)
                or put.status_code == 409
            )
            assert same, f"{body}: POST={post.status_code} PUT={put.status_code}"
            if post.status_code == 422:
                assert put.status_code == 422, f"PUT 仍可写入被 POST 拒绝的载荷: {body}"
        # 关键收口：全部坏载荷都没落到写盘调用里（POST 直写文件、PUT 经 update_file）
        text = app_env.url_cfg.read_text(encoding="utf-8-sig")
        for needle in (
            "127.0.0.1",
            "169.254",
            "2130706433",
            "fe80",
            "100.100.100.200",
            "file://",
            "8K无敌",
            "evil",
            "4K",
        ):
            assert needle not in text, f"坏载荷已落盘: {needle}"
            assert not any(needle in w for w in writes), f"坏载荷被 PUT 写进 update_file: {needle}"

    def test_update_room_rejects_internal_target(self, app_env: types.SimpleNamespace) -> None:
        # 报告给出的原始攻击序列：PUT 把已有房间改成本机面板地址（带 .flv 尾巴命中自定义流分支）
        token = _login(app_env.client)
        headers = {"Authorization": f"Bearer {token}"}
        seed = "https://live.douyin.com/victim"
        assert app_env.client.post("/api/rooms", json={"url": seed}, headers=headers).status_code == 200
        resp = app_env.client.put(
            "/api/rooms",
            json={"old_url": seed, "url": "http://127.0.0.1:8000/x?a=.flv"},
            headers=headers,
        )
        assert resp.status_code == 422
        assert "127.0.0.1" not in app_env.url_cfg.read_text(encoding="utf-8-sig")

    def test_update_room_rejects_unknown_quality(self, app_env: types.SimpleNamespace) -> None:
        token = _login(app_env.client)
        headers = {"Authorization": f"Bearer {token}"}
        seed = "https://live.douyin.com/q"
        assert app_env.client.post("/api/rooms", json={"url": seed}, headers=headers).status_code == 200
        resp = app_env.client.put("/api/rooms", json={"old_url": seed, "url": seed, "quality": "4K"}, headers=headers)
        assert resp.status_code == 422
        assert "4K" not in app_env.url_cfg.read_text(encoding="utf-8-sig")


class TestInternalErrorNotEchoed:
    # 内部异常原文（Windows 绝对路径、Errno 13）曾被 {"detail": ...} / error 字段
    # 原样回显并被前端弹成 toast，对局域网泄露安装路径。现对外只给固定 code，细节进日志。

    def test_logs_endpoint_hides_os_error(
        self, app_env: types.SimpleNamespace, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # 日志归档会 logger.remove() + 改名，Windows 下句柄/共享冲突常见，
        # 此时 str(e) 形如 "[Errno 13] Permission denied: 'D:\...\logs\streamget.log'"。
        token = _login(app_env.client)
        # 先造一个存在的日志文件（否则端点走「文件不存在 → 空列表」分支，测不到 except）
        (app_env.downloads.parent / "logs" / "streamget.log").write_text("x", encoding="utf-8")
        real_open = open

        def fake_open(file: object, mode: str = "r", **kw: str) -> object:
            name = str(file)
            if name.endswith("streamget.log"):
                raise OSError(13, "Permission denied", name)
            # 逐个具名传参（**kw 的展开形态 mypy 无法匹配 open() 的重载）：
            # 其余路径仍走真实 open，保证同一请求里别的读取不受本桩影响
            return real_open(name, mode, encoding=kw.get("encoding"), errors=kw.get("errors"))

        monkeypatch.setattr("builtins.open", fake_open)
        resp = app_env.client.get("/api/logs", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 500
        assert resp.json()["detail"] == "logs_unavailable"
        assert "streamget.log" not in resp.text and "D:" not in resp.text

    def test_danmaku_error_field_is_code_only(
        self, app_env: types.SimpleNamespace, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import src.danmaku_monitor as dm

        def _boom(since: int) -> dict[str, object]:
            raise RuntimeError("C:\\Users\\dev\\logs\\danmaku_monitor.jsonl locked")

        monkeypatch.setattr(dm.DanmakuMonitorHub, "snapshot", _boom)
        token = _login(app_env.client)
        resp = app_env.client.get("/api/danmaku", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["error"] == "danmaku_unavailable"
        assert "Users" not in resp.text and "jsonl" not in resp.text


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
        # 409 而不是幂等 200：面板需要明确的冲突信号来提示「该地址已添加」；
        # 去重判定取 normalize_url 后的地址，无锁的「查行—写行」窗口由下一条（C10）单独锁。
        token = _login(app_env.client)
        headers = {"Authorization": f"Bearer {token}"}
        resp = app_env.client.post("/api/rooms", json={"url": "https://live.douyin.com/3"}, headers=headers)
        assert resp.status_code == 200
        resp = app_env.client.post("/api/rooms", json={"url": "https://live.douyin.com/3"}, headers=headers)
        assert resp.status_code == 409

    def test_add_room_prepends_newline_when_tail_probe_blocked(
        self, app_env: types.SimpleNamespace, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # 末字节探测 open(...,"rb") 被 Windows sharing violation 挡住是常态（录制进程
        # 正持有 URL_config.ini），此时必须保守补一个 \n——让 _needs_newline 停在 False 直接追加
        # 会重开该「新房间粘上无尾换行的末行、两个房间同时坏掉」形态。
        # 打桩按「对象+模式」收窄：只对本用例 url_cfg 的二进制读制造失败，其余调用透传真实 open
        # （AGENTS 替身收窄口径）。变异可见性：改回 pass → 追加粘连成 oldhttps://…，逐字节断言转红
        token = _login(app_env.client)
        app_env.url_cfg.write_text("https://live.douyin.com/old", encoding="utf-8-sig")  # 无尾换行
        target = str(app_env.url_cfg)
        real_open = open

        def fake_open(file: object, mode: Any = "r", **kw: object) -> object:
            if str(file) == target and "b" in mode:
                raise OSError(32, "Sharing violation", str(file))
            # 与 test_logs_endpoint_hides_os_error 桩同型：逐个具名传参后其余路径走真实 open（具名传参理由见彼处首注）
            return real_open(
                str(file),
                mode,
                encoding=cast(str | None, kw.get("encoding")),
                errors=cast(str | None, kw.get("errors")),
            )

        monkeypatch.setattr("builtins.open", fake_open)
        resp = app_env.client.post(
            "/api/rooms", json={"url": "https://live.douyin.com/new"}, headers={"Authorization": f"Bearer {token}"}
        )
        assert resp.status_code == 200, resp.text
        text = app_env.url_cfg.read_text(encoding="utf-8-sig")
        assert (
            text == "https://live.douyin.com/old\nhttps://live.douyin.com/new\n"
        ), f"探测失败时未按保守形态补换行: {text!r}"

    def test_add_room_concurrent_no_duplicates(self, app_env: types.SimpleNamespace) -> None:
        # TOCTOU 回归（C10）：并发 POST 同一 URL，仅一条成功，其余 409
        token = _login(app_env.client)
        n = 8
        barrier = threading.Barrier(n)
        results: list[int] = []

        def worker() -> None:
            client = TestClient(app_env.app, base_url=_BASE_URL)
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
        # 审查 7.11：join(timeout=20) 静默返回时线程可能还卡在 add_room 的锁上；
        # 此时 results 已够 n 条（append 在 post 之后）却仍有线程未收尾，「仅一条 200」的判据
        # 会被半截状态满足。逐线程确认退出，才钉住 TOCTOU 竞态窗口真的被并发跑满。
        alive = [t.name for t in threads if t.is_alive()]
        assert not alive, f"8 条并发添加线程未在 20s 内退出（疑似房间锁死锁）：{alive}"
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

    # M-26①（CODE_REVIEW_2026-10-29）：update_room_quality 的 False 同时表示「已是目标画质」与
    # 「原子写失败」，端点无条件回 ok:true 会把写失败报成成功（前端忽略 changed 恒弹成功 toast）。
    def test_write_failure_is_not_reported_as_success(
        self, app_env: types.SimpleNamespace, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from src import web_api as wa

        headers = self._auth_headers(app_env)
        url = "https://www.huya.com/dank1ng"
        resp = app_env.client.post("/api/rooms", json={"url": url, "name": "DANK1NG"}, headers=headers)
        assert resp.status_code == 200, resp.text
        monkeypatch.setattr(wa, "update_room_quality", lambda *a, **k: False)
        resp = app_env.client.put("/api/rooms/quality", json={"url": url, "quality": "蓝光8M"}, headers=headers)
        assert resp.status_code == 500, resp.text

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

        resp = app_env.client.put("/api/rooms/quality", json={"url": url, "quality": "8K无敌"}, headers=headers)
        assert resp.status_code == 422
        resp = app_env.client.put("/api/rooms/quality", json={"url": url, "quality": "高清\n# evil"}, headers=headers)
        assert resp.status_code == 422
        text = app_env.url_cfg.read_text(encoding="utf-8-sig")
        assert "8K无敌" not in text
        assert "evil" not in text

    def test_change_quality_requires_auth(self, app_env: types.SimpleNamespace) -> None:
        # 认证启用时无 Bearer token 的画质切换请求必须 401（写接口 fail-closed）
        resp = app_env.client.put("/api/rooms/quality", json={"url": "https://live.douyin.com/1", "quality": "高清"})
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
        assert app_env.url_cfg.read_text(encoding="utf-8-sig") == "# 超清,https://www.huya.com/dank1ng,主播: DANK1NG\n"
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
        headers = {"Authorization": f"Bearer {token}"}
        # 复验守卫的本地锁（与 tests/test_regression_web_g.py:
        # TestAuthKeyReauth::test_password_write_without_reauth_is_403 同源）：不带 reauth_password
        # 必须先 403 且配置文件一个字节都不能动。本用例测「改密后旧 token 失效」，与复验正交，
        # 故随后带上正确口令满足前置——200 也因此证明确实是被复验放行的，而非别的分支。
        before = app_env.cfg.read_bytes()
        denied = client.put(
            "/api/config",
            json={"section": "Web", "key": "web_password", "value": "newpass456"},
            headers=headers,
        )
        assert denied.status_code == 403, f"改口令未复验却被放行: {denied.text}"
        assert app_env.cfg.read_bytes() == before, "被拒的写入仍改了 config.ini"
        # 被拒 ⇒ 不得触发「改密吊销 token」，否则 403 实际完成了一次 DoS
        assert client.get("/api/rooms", headers=headers).status_code == 200
        resp = client.put(
            "/api/config",
            json={"section": "Web", "key": "web_password", "value": "newpass456", "reauth_password": "secret123"},
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        # 旧 token 立即失效（C11）
        resp = client.get("/api/rooms", headers=headers)
        assert resp.status_code == 401
        # 新密码可登录
        resp = client.post("/api/login", json={"password": "newpass456"})
        assert resp.status_code == 200

    def test_new_password_stored_hashed(self, app_env: types.SimpleNamespace) -> None:
        # 修改密码后配置文件须存哈希（pbkdf2）而非明文；
        # 判据取配置文件文本而非响应体：哈希化发生在写盘那一步，应答里本来就不含口令。
        token = _login(app_env.client)
        # 未复验的改口令必须先被拒、且不得落盘任何新值（旧哈希原样保留）
        before = app_env.cfg.read_bytes()
        denied = app_env.client.put(
            "/api/config",
            json={"section": "Web", "key": "web_password", "value": "newpass456"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert denied.status_code == 403, denied.text
        assert app_env.cfg.read_bytes() == before, "被拒的改口令仍写进了 config.ini"
        resp = app_env.client.put(
            "/api/config",
            json={"section": "Web", "key": "web_password", "value": "newpass456", "reauth_password": "secret123"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200, resp.text
        text = app_env.cfg.read_text(encoding="utf-8-sig")
        assert "newpass456" not in text
        assert "pbkdf2_sha256$" in text

    def test_password_with_surrounding_whitespace_not_self_locking(self, app_env: types.SimpleNamespace) -> None:
        # 「首尾带空格」的口令在写入/登录/reauth 三处必须同口径 strip——若写入侧用原文哈希
        # 而 reauth 侧 strip 比对，这类口令（粘贴/输入法尾随空格是常见来源）一旦设置，
        # 此后所有 reauth 永远 403，认证配置经面板永久自锁。
        # 口令值沿用本文件既有夹具取值（拆写拼接），被测行为与口令取值本身无关。
        client = app_env.client
        current = "secret" + "123"
        rotated = "  " + "newpass" + "456" + "  "
        token = _login(client)
        headers = {"Authorization": f"Bearer {token}"}
        resp = client.put(
            "/api/config",
            json={"section": "Web", "key": "web_password", "value": rotated, "reauth_password": current},
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        # 改密吊销旧 token 后，strip 形态登录必须成功（写入侧已按 strip 哈希）
        resp = client.post("/api/login", json={"password": rotated.strip()})
        assert resp.status_code == 200, f"strip 形态登录失败: {resp.text}"
        # 原样（带空格）登录同样成功——登录侧与 reauth 同口径 strip
        resp = client.post("/api/login", json={"password": rotated})
        assert resp.status_code == 200, f"原文形态登录失败: {resp.text}"
        # 核心判据：新口令的 reauth 不再 403 自锁（改 web_auth_enable 必须复验）
        token2 = cast(str, resp.json()["token"])
        resp = client.put(
            "/api/config",
            json={"section": "Web", "key": "web_auth_enable", "value": "false", "reauth_password": rotated},
            headers={"Authorization": f"Bearer {token2}"},
        )
        assert resp.status_code == 200, f"带空格口令 reauth 仍被 403 自锁: {resp.text}"


class TestPasswordGuardCaseParity:
    # Web 节的三项守卫（口令哈希化 / 防清空 / 改密吊销 token）曾被大小写变体整体绕过
    # ——危险键黑名单做了 casefold，这三处却是精确比较，而 configparser 的 option 本就
    # 大小写不敏感：写入 WEB_PASSWORD 命中同一行配置却跳过全部守卫。
    # 现统一在入口处归一 key_norm，本类锁「大小写变体与规范写法裁决一致」。

    @pytest.mark.parametrize("key", ["web_password", "WEB_PASSWORD", "Web_Password", " web_password "])
    def test_password_variant_always_hashed_and_revokes(self, app_env: types.SimpleNamespace, key: str) -> None:
        client = app_env.client
        token = _login(client)
        # 本用例测「键名大小写/空白变体不得跳过口令守卫」，与该复验正交：
        # 固定带正确 reauth_password 把复验满足掉（同 test_password_change_revokes_tokens 的处理）。
        # 关键一点：**复验也必须走同一份归一化**——若实现里用 req.reauth_password 去比对
        # 而未先解析当前口令哈希，四个变体会一起变红（复验与哈希化是两个独立防线）。
        # 前置一段（该本地锁）：判定用的是 key_norm（strip + lower），四个变体不带
        # reauth_password 时必须一律 403 且配置字节不变；少了这一段，归一化被摘掉时仍是全绿。
        before = app_env.cfg.read_bytes()
        denied = client.put(
            "/api/config",
            json={"section": "Web", "key": key, "value": "AtkPass999"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert denied.status_code == 403, f"{key!r} 变体绕过了复验守卫: {denied.text}"
        assert app_env.cfg.read_bytes() == before, f"{key!r} 变体的被拒写入仍落了盘"
        resp = client.put(
            "/api/config",
            json={"section": "Web", "key": key, "value": "AtkPass999", "reauth_password": "secret123"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200, resp.text
        text = app_env.cfg.read_text(encoding="utf-8-sig")
        # ① 明文绝不落盘（configparser 写回的是同一行，因为行匹配带 IGNORECASE）
        assert "AtkPass999" not in text, f"{key} 变体把明文密码写进了 config.ini"
        assert "pbkdf2_sha256$" in text
        # ② 改密必须吊销全部 token（「改密踢人」是凭据泄露后的唯一兜底）
        assert client.get("/api/rooms", headers={"Authorization": f"Bearer {token}"}).status_code == 401
        # ③ 新密码可用（大小写变体写入的必须是同一行，否则这里登不上）
        assert client.post("/api/login", json={"password": "AtkPass999"}).status_code == 200

    @pytest.mark.parametrize("key", ["web_password", "WEB_PASSWORD"])
    def test_clear_password_rejected_regardless_of_case(self, app_env: types.SimpleNamespace, key: str) -> None:
        # 认证开启时清空密码会让 /api/login 直接 500（面板自锁）——大小写变体不得漏网
        token = _login(app_env.client)
        resp = app_env.client.put(
            "/api/config",
            json={"section": "Web", "key": key, "value": "   "},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 400

    def test_auth_enable_variant_still_requires_password(self, tmp_path: Path, fake_main: types.ModuleType) -> None:
        # 反向路径：认证关闭 + 密码为空时把 WEB_AUTH_ENABLE 写成 true，
        # 会让全部 /api/* 变 401 且 /api/login 直接 500 → 面板永久锁死，只能手工改文件。
        # 大小写变体必须与规范写法一样被 400 拦住（旧实现该判定用精确比较，变体可绕）。
        from src import web_api as wa

        cfg = tmp_path / "lockout.ini"
        _write_web_section(cfg, auth="false", password="")
        _reset_web_api_state(wa)
        app = wa.create_app(
            config_file=str(cfg),
            url_config_file=str(tmp_path / "u.ini"),
            downloads_root=str(tmp_path),
            logs_dir=str(tmp_path),
        )
        client = TestClient(app, base_url=_BASE_URL)
        try:
            for key in ("web_auth_enable", "WEB_AUTH_ENABLE", "Web_Auth_Enable"):
                resp = client.put("/api/config", json={"section": "Web", "key": key, "value": "true"})
                assert resp.status_code == 400, f"{key} 变体绕过了防锁死判定: {resp.text}"
            # 兜底确认：三次尝试都没把配置改成开启态
            assert "web_auth_enable = false" in cfg.read_text(encoding="utf-8-sig")
        finally:
            client.close()


class TestAuthDowngradeRejected:
    # 把「认证降级」当作敏感变更 —— 非回环监听地址下拒绝 web_auth_enable=false，
    # 并让「非回环 + 无认证」不变量在**每个请求**上重跑（旧实现只在 web.py 启动时看一次）。

    def _env(self, tmp_path: Path, fake_main: types.ModuleType, wa: object, *, host: str, auth: str) -> TestClient:
        cfg = tmp_path / "config.ini"
        _write_web_section(
            cfg,
            auth=auth,
            password=cast("types.ModuleType", wa).hash_web_password("secret123"),
            host=host,
        )
        _reset_web_api_state(cast("types.ModuleType", wa))
        app = cast("types.ModuleType", wa).create_app(
            config_file=str(cfg),
            url_config_file=str(tmp_path / "u.ini"),
            downloads_root=str(tmp_path),
            logs_dir=str(tmp_path),
        )
        return TestClient(app, base_url=_BASE_URL)

    def test_downgrade_on_public_bind_rejected_403(self, tmp_path: Path, fake_main: types.ModuleType) -> None:
        from src import web_api as wa

        client = self._env(tmp_path, fake_main, wa, host="0.0.0.0", auth="true")
        try:
            token = client.post("/api/login", json={"password": "secret123"}).json()["token"]
            headers = {"Authorization": f"Bearer {token}"}
            for key in ("web_auth_enable", "WEB_AUTH_ENABLE"):
                resp = client.put(
                    "/api/config",
                    json={"section": "Web", "key": key, "value": "false"},
                    headers=headers,
                )
                assert resp.status_code == 403, f"{key} 变体未被同一守卫拦住: {resp.text}"
            # 且认证仍在生效：配置未被改成关闭态
            assert client.get("/api/rooms").status_code == 401
        finally:
            client.close()

    def test_downgrade_on_loopback_allowed(self, app_env: types.SimpleNamespace) -> None:
        # 回环监听下关闭认证仍是合法操作（出厂默认即如此），不得因新守卫而锁死本机用户。
        # 后这条「合法降级」还须带正确复验口令才放行：拦的是「无口令降级」，不是「降级」本身。
        token = _login(app_env.client)
        headers = {"Authorization": f"Bearer {token}"}
        # 本条同时锁「回环不是复验的豁免条件」：该在回环下放行降级，
        # 必须仍然把不带口令的那一次挡在门外（配置字节不得变化）。
        before = app_env.cfg.read_bytes()
        denied = app_env.client.put(
            "/api/config",
            json={"section": "Web", "key": "web_auth_enable", "value": "false"},
            headers=headers,
        )
        assert denied.status_code == 403, f"回环绑定下关认证免复验: {denied.text}"
        assert app_env.cfg.read_bytes() == before, "被拒的降级仍写进了 config.ini"
        assert app_env.client.get("/api/rooms", headers=headers).status_code == 200
        resp = app_env.client.put(
            "/api/config",
            json={"section": "Web", "key": "web_auth_enable", "value": "false", "reauth_password": "secret123"},
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        # 关掉后所有 /api/* 立即可读（无需 token）——中间件的缓存必须已失效
        assert app_env.client.get("/api/rooms").status_code == 200

    def test_middleware_enforces_invariant_per_request(
        self, tmp_path: Path, fake_main: types.ModuleType, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # 绕过写接口、直接改文件把认证关掉（模拟「启动后配置漂移」）：
        # 中间件必须在下一个请求就发现并锁住 /api/*，而不是等进程重启。
        from src import web_api as wa

        client = self._env(tmp_path, fake_main, wa, host="0.0.0.0", auth="true")
        try:
            token = client.post("/api/login", json={"password": "secret123"}).json()["token"]
            assert client.get("/api/rooms", headers={"Authorization": f"Bearer {token}"}).status_code == 200
            _ = wa.update_config_line(str(tmp_path / "config.ini"), "Web", "web_auth_enable", "false")
            _reset_web_api_state(wa)  # 等价于一次 mtime 变化：让中间件重读配置
            resp = client.get("/api/rooms", headers={"Authorization": f"Bearer {token}"})
            assert resp.status_code == 403
            assert resp.json()["detail"] == "insecure_bind_disabled"
            # 静态资源与探活不受影响：运维仍打得开面板 / CI 仍能探活
            assert client.get("/health").status_code == 200
        finally:
            client.close()

    def test_insecure_env_override_still_works(
        self, tmp_path: Path, fake_main: types.ModuleType, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # 环境变量逃生阀与 web.py 同源：设了它就必须继续放行，否则用户只会看到一堆 403
        from src import web_api as wa

        monkeypatch.setenv("DOUYIN_WEB_ALLOW_INSECURE", "1")
        client = self._env(tmp_path, fake_main, wa, host="0.0.0.0", auth="false")
        try:
            assert client.get("/api/rooms").status_code == 200
        finally:
            client.close()


class TestSecurityConfigCacheInvalidation:
    # 安全判定键的写入必须让中间件的配置缓存**即时**失效。
    # 缓存本会按 mtime+size 自然失效，本类把这条物理前提冻住（web_api 命名空间里的 os.stat 换成
    # 恒返同一 (mtime, size) 的替身），等价于「同秒等长改写 + 粗精度时间戳」那一档病态场景；
    # 于是「改完立刻生效」只剩写侧 _invalidate_web_cfg_cache() 一条路——失效清单里漏掉该键即红。
    # 打桩口径按仓库约定：浅拷贝 os 命名空间、只覆盖 stat，再把替身绑到**被测模块**的 os 引用上，
    # 不改 stdlib 本体（web_api 里 os.stat 的唯一消费点就是 _read_web_config_cached，
    # /api/files 那两个 stat 调用不在本用例路径上）。

    def _frozen_client(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, wa: types.ModuleType) -> TestClient:
        # [Web] 里预置两个待验证的安全键（update_config_line 只改已存在的键，缺键会退 404）
        cfg = tmp_path / "config.ini"
        cfg.write_text(
            "\n".join(
                [
                    "[Web]",
                    "web_host = 127.0.0.1",
                    "web_port = 8000",
                    "web_auth_enable = true",
                    f"web_password = {cast('types.ModuleType', wa).hash_web_password('secret123')}",
                    "web_trusted_proxy = ",
                    "web_allowed_hosts = ",
                ]
            )
            + "\n",
            encoding="utf-8-sig",
        )
        _reset_web_api_state(cast("types.ModuleType", wa))
        frozen = types.SimpleNamespace(st_mtime=1_000.0, st_size=1_000)
        os_shim = types.SimpleNamespace(**vars(os))
        os_shim.stat = lambda _path: frozen
        monkeypatch.setattr(wa, "os", cast("object", os_shim))
        app = cast("types.ModuleType", wa).create_app(
            config_file=str(cfg),
            url_config_file=str(tmp_path / "u.ini"),
            downloads_root=str(tmp_path),
            logs_dir=str(tmp_path),
        )
        return TestClient(app, base_url=_BASE_URL)

    def test_web_host_change_takes_effect_without_mtime_change(
        self, tmp_path: Path, fake_main: types.ModuleType, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # 端到端锁：Host 允许名单（ DNS 重绑定防线）只从这份带缓存的 cfg 里取，
        # 所以「把名单改宽/改窄」是否即时生效，直接 observable 在带 Host 头的请求上。
        # 三段顺序本身就是判据：改宽前 400（证明用例不恒真）→ 改宽后 200 → 改窄后重新 400
        # （证明失效是双向的，而不是「第一次读了盘之后就一直对」）。
        # [历史注] 本条原用 web_allowed_hosts 驱动；此起该键进危险黑名单（见 TestDangerousKeys
        #  该参数化用例），场景改由**仍可写**的安全键 web_host 承担——get_allowed_hosts 同样吃它，判定面逐字等价
        from src import web_api as wa

        client = self._frozen_client(tmp_path, monkeypatch, wa)
        try:
            token = client.post("/api/login", json={"password": "secret123"}).json()["token"]
            headers = {"Authorization": f"Bearer {token}"}
            panel_host = {"Host": "panel.example.com:8000"}
            assert client.get("/api/rooms", headers=panel_host).status_code == 400, "名单未含该域名却已放行：判据恒真"
            resp = client.put(
                "/api/config",
                json={"section": "Web", "key": "web_host", "value": "panel.example.com"},
                headers=headers,
            )
            assert resp.status_code == 200, resp.text
            got = client.get("/api/rooms", headers={**panel_host, "Authorization": f"Bearer {token}"})
            assert got.status_code == 200, f"改宽名单后缓存仍按旧值判 Host: {got.status_code} {got.text}"
            resp = client.put(
                "/api/config",
                json={"section": "Web", "key": "web_host", "value": "127.0.0.1"},
                headers=headers,
            )
            assert resp.status_code == 200, resp.text
            assert client.get("/api/rooms", headers=panel_host).status_code == 400, "收紧名单同样必须即时生效"
        finally:
            client.close()

    def test_proxy_and_hosts_keys_are_no_longer_panel_writable(
        self, tmp_path: Path, fake_main: types.ModuleType, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # [历史注] 本条原锁「web_trusted_proxy 经面板变更后的缓存失效 + XFF 分桶换窗」；该把
        # web_trusted_proxy / web_allowed_hosts 列入危险键黑名单后该驱动路径整体不复存在，
        # XFF 分桶仍由 TestLoginRateLimit 在 create_app 起点锁住。
        # 现锁 **认证开启侧**：两键在登录态下必须 403 且文件逐字不变
        from src import web_api as wa

        client = self._frozen_client(tmp_path, monkeypatch, wa)
        try:
            token = client.post("/api/login", json={"password": "secret123"}).json()["token"]
            headers = {"Authorization": f"Bearer {token}"}
            before = (tmp_path / "config.ini").read_bytes()
            for key, value in (("web_trusted_proxy", "9.9.9.9"), ("web_allowed_hosts", "evil.example.com")):
                resp = client.put("/api/config", json={"section": "Web", "key": key, "value": value}, headers=headers)
                assert resp.status_code == 403, f"{key} 仍可经面板改写（危险键黑名单失效）: {resp.text}"
            assert (tmp_path / "config.ini").read_bytes() == before, "被拒的安全键写入仍改了 config.ini"
        finally:
            client.close()


class TestHostHeaderAllowList:
    # 同源判定曾拿**请求自带的 Host** 与 Origin 比较，DNS 重绑定
    # （attacker.tld 的 A 记录 TTL=0 指向 127.0.0.1）下二者必然相同 → SOP 与 CSRF 同时失效。
    # 现在 Host 必须命中服务端推导的允许名单；Origin 亦按同一名单判定。

    def test_attacker_host_rejected_loopback_host_accepted(self, app_env: types.SimpleNamespace) -> None:
        resp = app_env.client.get("/api/rooms", headers={"Host": "attacker.tld:8000"})
        assert resp.status_code == 400
        assert resp.json()["detail"] == "host_not_allowed"
        # 名单内的两种写法必须放行：配置的 web_host（带端口）与 localhost
        assert app_env.client.get("/api/rooms", headers={"Host": "127.0.0.1:8000"}).status_code == 401
        assert app_env.client.get("/api/rooms", headers={"Host": "localhost"}).status_code == 401
        # 写接口同样受保护（旧实现只在这里比较 Origin，Host 完全不校验）
        resp = app_env.client.put(
            "/api/config", json={"section": "Web", "key": "x", "value": "y"}, headers={"Host": "attacker.tld"}
        )
        assert resp.status_code == 400

    def test_rebinding_origin_no_longer_self_certifies(self, app_env: types.SimpleNamespace) -> None:
        # 重绑定场景的完整形态：Host 与 Origin 同为 attacker.tld。
        # 旧判定 origin == "http://" + host → 通过；新判定两边都要过服务端名单 → 拒绝。
        resp = app_env.client.put(
            "/api/config",
            json={"section": "Web", "key": "web_auth_enable", "value": "false"},
            headers={"Host": "attacker.tld:8000", "Origin": "http://attacker.tld:8000"},
        )
        assert resp.status_code == 400

    def test_same_origin_write_still_works_and_cross_site_denied(self, app_env: types.SimpleNamespace) -> None:
        token = _login(app_env.client)
        headers = {"Authorization": f"Bearer {token}"}
        resp = app_env.client.post(
            "/api/rooms",
            json={"url": "https://live.douyin.com/host-check"},
            headers={**headers, "Origin": "http://127.0.0.1:8000"},
        )
        assert resp.status_code == 200, resp.text
        # 真跨站（Host 是本站、Origin 是外站）仍按 WD-08 拒绝
        resp = app_env.client.post(
            "/api/rooms",
            json={"url": "https://live.douyin.com/host-check2"},
            headers={**headers, "Origin": "http://evil.example.com"},
        )
        assert resp.status_code == 403
        # Sec-Fetch-Site: cross-site 即便 Origin 缺失也判跨站（浏览器会强制覆盖该头）
        resp = app_env.client.post(
            "/api/rooms",
            json={"url": "https://live.douyin.com/host-check3"},
            headers={**headers, "Sec-Fetch-Site": "cross-site"},
        )
        assert resp.status_code == 403

    def test_uvicorn_must_not_rewrite_client_addr(self) -> None:
        # 结构性前提：web.py 必须以 proxy_headers=False 起 uvicorn。
        # 否则 uvicorn 的 ProxyHeaders 中间件会在鉴权中间件之前用 XFF 最左值覆盖
        # scope["client"]，_get_client_ip 的「只信直连对端」就变成「只信伪造值」。
        # 本用例锁源码事实（与仓库既有的 AST/文本级防回归断言同口径）。
        source = (Path(__file__).resolve().parent.parent / "web.py").read_text(encoding="utf-8")
        assert "proxy_headers=False" in source, "web.py 未关闭 uvicorn proxy_headers → XFF 限流可被绕过"
        # SEV-N03 的结构性前提：判定基准是**实际绑定地址**，它只有一个来源——web.py 把
        # 自己用来起 uvicorn 的那个 host/port 传给 create_app。接线被摘掉时 app.state 退回
        # 「未接线」，判定会静默回落到可被 PUT /api/config 改写的配置值（即回到旧的可旁路形态），
        # 而单侧的 HTTP 用例发现不了。故与 proxy_headers 同口径锁源码事实。
        assert "bind_host=host" in source and "bind_port=port" in source, "web.py 未把实际绑定地址传给 create_app"


class TestInsecureBindInvariantUsesRealAddress:
    # SEV-N03：「非回环 + 无认证」不变量若以 config.ini 的 web_host 为判定基准，而
    # web_host 自身可经同一个 PUT /api/config 改写（既非敏感项、也不在危险键黑名单内），
    # 「① 写 web_host=127.0.0.1 ② 写 web_auth_enable=false」两步即可把仍监听 0.0.0.0 的进程
    # 变成「无认证 + 全网卡」——一个由请求方可写的量不能用来证明请求方安全。
    # 现状：两处判定都以**进程实际绑定地址**为准，并对 web_host 的写入补一道目标态校验。

    def _client(
        self,
        tmp_path: Path,
        wa: types.ModuleType,
        *,
        cfg_host: str,
        auth: str,
        bind_host: str | None,
        bind_port: int | None = None,
        cfg_name: str = "config.ini",
    ) -> TestClient:
        # 独立工厂：让「配置里的监听地址」与「进程实际绑定地址」成为两个互不绑定的参数
        # ——SEV-N03 的全部要害就在这两者的分歧上，沿用 _write_web_section 的单值口径造不出该分歧。
        cfg = tmp_path / cfg_name
        _write_web_section(
            cfg, auth=auth, password=cast("types.ModuleType", wa).hash_web_password("secret123"), host=cfg_host
        )
        _reset_web_api_state(cast("types.ModuleType", wa))
        app = cast("types.ModuleType", wa).create_app(
            config_file=str(cfg),
            url_config_file=str(tmp_path / "u.ini"),
            downloads_root=str(tmp_path),
            logs_dir=str(tmp_path),
            bind_host=bind_host,
            bind_port=bind_port,
        )
        return TestClient(app, base_url=_BASE_URL)

    def test_two_step_web_host_then_auth_off_is_403(self, tmp_path: Path, fake_main: types.ModuleType) -> None:
        # 攻击序列本体（回归锁表 SEV-N03 第一条）：现有该用例只测「一步关认证」，
        # 两步序列在修复前是完全通过的。
        from src import web_api as wa

        client = self._client(tmp_path, wa, cfg_host="0.0.0.0", auth="true", bind_host="0.0.0.0", bind_port=8000)
        try:
            token = client.post("/api/login", json={"password": "secret123"}).json()["token"]
            headers = {"Authorization": f"Bearer {token}"}
            # 第①步：认证仍开启时，把监听地址改成回环是**合法**编辑（用户照提示收紧配置）。
            step1 = client.put(
                "/api/config", json={"section": "Web", "key": "web_host", "value": "127.0.0.1"}, headers=headers
            )
            assert step1.status_code == 200, step1.text
            # 前提自证：配置里现在确实写着回环值——否则第②步的 403 可能来自别的分支，
            # 本用例就会退化成「与该单步用例同义」的假绿。
            cfg_text = (tmp_path / "config.ini").read_text(encoding="utf-8-sig")
            assert "web_host = 127.0.0.1" in cfg_text, cfg_text
            # 第②步：关认证。判定读实际绑定 0.0.0.0 → 必须 403（修复前读刚写进去的 127.0.0.1 判为回环 → 放行）。
            # 带上**正确**复验口令：否则这条 403 可能来自复验守卫而非监听地址守卫，
            # 与下面 test_two_step_sequence_allowed_when_real_bind_is_loopback 也不再是
            # 「唯一差别是 bind_host」的对照。下面的 detail 断言才是归因所在。
            step2 = client.put(
                "/api/config",
                json={"section": "Web", "key": "web_auth_enable", "value": "false", "reauth_password": "secret123"},
                headers=headers,
            )
            assert step2.status_code == 403, f"两步序列仍可旁路认证: {step2.text}"
            assert "当前实际监听 0.0.0.0" in step2.json()["detail"], step2.json()["detail"]
            assert "reauth_password" not in step2.json()["detail"], "403 来自复验守卫而非监听地址守卫"
            # 收尾：安全态没被改动（认证仍在，配置也没被写成关闭态）
            assert client.get("/api/rooms").status_code == 401
            assert "web_auth_enable = true" in (tmp_path / "config.ini").read_text(encoding="utf-8-sig")
        finally:
            client.close()

    def test_two_step_sequence_allowed_when_real_bind_is_loopback(
        self, tmp_path: Path, fake_main: types.ModuleType
    ) -> None:
        # 与上一条**唯一**差别是 bind_host（127.0.0.1 vs 0.0.0.0），其余入参逐字相同：
        # 配置里写着 0.0.0.0、先改回环、再关认证——这一步序列在两种绑定下结论必须相反。
        # 若判定基准错配回 cfg["web_host"]（或错配回 req.value），两条会同时通过、拒绝无法归因；
        # 本条正是那条 403 的反向对照，证明拒绝来自「进程实际监听地址」而非「配置值」。
        # 出厂默认形态（绑回环 + 允许关认证）不得被这次收紧打死。
        from src import web_api as wa

        client = self._client(tmp_path, wa, cfg_host="0.0.0.0", auth="true", bind_host="127.0.0.1", bind_port=8000)
        try:
            token = client.post("/api/login", json={"password": "secret123"}).json()["token"]
            headers = {"Authorization": f"Bearer {token}"}
            step1 = client.put(
                "/api/config", json={"section": "Web", "key": "web_host", "value": "127.0.0.1"}, headers=headers
            )
            assert step1.status_code == 200, f"实际绑定回环时第①步被误拒: {step1.text}"
            # 本地锁：第②步不带复验必须先被拒（且这一步之后配置字节不变），
            # 于是本用例的 200 唯一来自「bind 是回环 + 口令正确」这一组合，
            # 与对照用例（bind=0.0.0.0、同样带正确复验 → 403）仍然逐字段可比。
            after_step1 = (tmp_path / "config.ini").read_bytes()
            denied = client.put(
                "/api/config",
                json={"section": "Web", "key": "web_auth_enable", "value": "false"},
                headers=headers,
            )
            assert denied.status_code == 403, f"回环两步序列的第②步免复验: {denied.text}"
            assert (tmp_path / "config.ini").read_bytes() == after_step1, "被拒的第②步仍改了 config.ini"
            step2 = client.put(
                "/api/config",
                json={"section": "Web", "key": "web_auth_enable", "value": "false", "reauth_password": "secret123"},
                headers=headers,
            )
            assert step2.status_code == 200, f"实际绑定回环时两步序列仍被拒: {step2.text}"
            # 生效态核对：配置确实写成了「回环 + 无认证」，且中间件据此放行（不是被 403 挡在门外）
            cfg_text = (tmp_path / "config.ini").read_text(encoding="utf-8-sig")
            assert "web_host = 127.0.0.1" in cfg_text, cfg_text
            assert "web_auth_enable = false" in cfg_text, cfg_text
            assert client.get("/api/rooms").status_code == 200
        finally:
            client.close()

    def test_middleware_lockout_follows_real_bind_not_config(self, tmp_path: Path, fake_main: types.ModuleType) -> None:
        # 判定基准的第二半：中间件的每请求判定。配置里写着回环（修复前据此判「安全」），
        # 实际进程监听 0.0.0.0，认证被绕过写接口直接改文件关掉 —— 必须锁住 /api/*。
        # 只测写侧 403 排不掉「守卫被改坏但中间件仍读配置」这一组合，故两侧分别钉。
        from src import web_api as wa

        client = self._client(tmp_path, wa, cfg_host="127.0.0.1", auth="true", bind_host="0.0.0.0", bind_port=8000)
        try:
            token = client.post("/api/login", json={"password": "secret123"}).json()["token"]
            assert client.get("/api/rooms", headers={"Authorization": f"Bearer {token}"}).status_code == 200
            assert wa.update_config_line(str(tmp_path / "config.ini"), "Web", "web_auth_enable", "false") is True
            _reset_web_api_state(wa)  # 等价于一次 mtime 变化：让中间件重读配置
            resp = client.get("/api/rooms")
            assert resp.status_code == 403, "配置自称回环即解除锁住：判定仍读的是配置值"
            assert resp.json()["detail"] == "insecure_bind_disabled"
            # 静态页/探活不受影响（否则运维连改回来的界面都打不开）
            assert client.get("/health").status_code == 200
        finally:
            client.close()

    def test_loopback_web_host_write_blocked_when_config_cache_says_auth_on(
        self, tmp_path: Path, fake_main: types.ModuleType, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # web_host 写入侧的目标态校验。可达性说明：中间件与写侧守卫用的是同一个 _guard_bind_host，
        # 缓存视图与磁盘视图一致时「认证已关 + 非回环」永远到不了处理函数（先被 403 锁住）；
        # 真正分歧只发生在 mtime+size 缓存失效失灵（同秒等长改写）或改文件绕过失效逻辑时——
        # 这正是这道守卫存在的理由。本用例直接造出「中间件认为认证开着、文件其实已关」的分歧，
        # 证明写侧不是永不生效的死分支。
        from src import web_api as wa

        client = self._client(tmp_path, wa, cfg_host="0.0.0.0", auth="true", bind_host="0.0.0.0", bind_port=8000)
        try:
            token = client.post("/api/login", json={"password": "secret123"}).json()["token"]
            assert token
            # 让中间件停留在「认证仍开启」的旧快照上（等价于缓存未按 mtime+size 失效），
            # 再把磁盘现值改成关闭态——处理函数按磁盘现值判定，此时必须自己拦住。
            # 注：这里打的是中间件唯一的配置入口 _read_web_config_cached，不替换 stdlib、
            # 也不改判定函数本体。
            stale: dict[str, str | int | bool] = {"web_host": "0.0.0.0", "web_port": 8000, "web_auth_enable": True}
            monkeypatch.setattr(wa, "_read_web_config_cached", lambda _path: dict(stale))
            assert wa.update_config_line(str(tmp_path / "config.ini"), "Web", "web_auth_enable", "false") is True
            resp = client.put(
                "/api/config",
                json={"section": "Web", "key": "web_host", "value": "127.0.0.1"},
                headers={"Authorization": f"Bearer {token}"},
            )
            assert resp.status_code == 403, f"认证实际已关闭时仍可把 web_host 写成回环伪安全态: {resp.text}"
            assert "不允许把 web_host 改写为回环地址" in resp.json()["detail"], resp.json()["detail"]
            assert "web_host = 0.0.0.0" in (tmp_path / "config.ini").read_text(encoding="utf-8-sig")
        finally:
            client.close()

    def test_real_loopback_bind_still_allows_auth_off(self, tmp_path: Path, fake_main: types.ModuleType) -> None:
        # 反向边界（不得把修复做成「非出厂形态一律锁死」）：实际绑定就是回环时，
        # 关掉认证依旧合法放行（与出厂默认 web_host=127.0.0.1 + 无认证同形）。
        from src import web_api as wa

        client = self._client(tmp_path, wa, cfg_host="0.0.0.0", auth="false", bind_host="127.0.0.1", bind_port=8000)
        try:
            # 配置里写的是 0.0.0.0（准备下次重启开放），实际仍监听回环 → 按现实放行、不按配置锁死。
            assert client.get("/api/rooms").status_code == 200
        finally:
            client.close()

    def test_insecure_env_override_bypasses_both_guards(
        self, tmp_path: Path, fake_main: types.ModuleType, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # 破例通道保持原语义：设了 DOUYIN_WEB_ALLOW_INSECURE=1 的用户，两道新守卫都不添乱。
        from src import web_api as wa

        monkeypatch.setenv("DOUYIN_WEB_ALLOW_INSECURE", "1")
        client = self._client(tmp_path, wa, cfg_host="0.0.0.0", auth="false", bind_host="0.0.0.0", bind_port=8000)
        try:
            assert client.get("/api/rooms").status_code == 200
            resp = client.put("/api/config", json={"section": "Web", "key": "web_host", "value": "127.0.0.1"})
            assert resp.status_code == 200, resp.text
        finally:
            client.close()

    def test_two_step_attack_reproduces_when_basis_reverts_to_config_value(
        self, tmp_path: Path, fake_main: types.ModuleType, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # 归因用例（本工作区禁止「改坏生产实现再跑用例」的变异验证）：在**测试内**把判定基准
        # 换回修复前的 cfg["web_host"]，中间件顺序、写侧守卫、请求载荷逐字不动。
        # 若此时两步序列一路通过，即证明上面那条 403 唯一来自 _guard_bind_host 的「实际绑定地址」
        # 基准，而非危险键黑名单 / 敏感项空值守卫 / 该目标态校验等其它分支恰好挡掉的假绿；
        # 把 _guard_bind_host 整个删掉（退化为未接线时的配置回落）会得到同一结论。
        from src import web_api as wa

        def _legacy_basis(_app: object, cfg: dict[str, str | int | bool]) -> str:
            return str(cast(object, cfg.get("web_host", "")) or "")

        monkeypatch.setattr(wa, "_guard_bind_host", _legacy_basis)
        client = self._client(tmp_path, wa, cfg_host="0.0.0.0", auth="true", bind_host="0.0.0.0", bind_port=8000)
        try:
            token = client.post("/api/login", json={"password": "secret123"}).json()["token"]
            headers = {"Authorization": f"Bearer {token}"}
            step1 = client.put(
                "/api/config", json={"section": "Web", "key": "web_host", "value": "127.0.0.1"}, headers=headers
            )
            assert step1.status_code == 200, step1.text
            # 第②步必须带正确复验口令：否则 403 会抢在「旧基准放行」之前发生、归因失效（假红）。
            # 先补一次不带复验的探测（该本地锁）：即便判定基准已被换回配置值，
            # 无口令的降级仍必须被拒且不动配置——证明复验守卫与监听地址守卫**互不覆盖**，
            # 摘掉任一道的形态都各自有红点，而不是「两道守卫视作同一件事」。
            after_step1 = (tmp_path / "config.ini").read_bytes()
            denied = client.put(
                "/api/config",
                json={"section": "Web", "key": "web_auth_enable", "value": "false"},
                headers=headers,
            )
            assert denied.status_code == 403, f"旧基准下复验守卫一并失效: {denied.text}"
            assert (tmp_path / "config.ini").read_bytes() == after_step1, "被拒的探测改了 config.ini"
            step2 = client.put(
                "/api/config",
                json={"section": "Web", "key": "web_auth_enable", "value": "false", "reauth_password": "secret123"},
                headers=headers,
            )
            # 旧基准下第②步被「配置里的假回环值」说服 → 漏洞完整重现
            assert step2.status_code == 200, f"旧基准下仍能拦住两步序列，说明 403 另有来源: {step2.text}"
            # 第③步：无 token 直接读房间 —— SEV-N03 的实际危害（仍监听 0.0.0.0 却已无认证）
            assert client.get("/api/rooms").status_code == 200, "旧基准下未认证即可读 API：危害面确认"
        finally:
            client.close()

    def test_update_config_insecure_detail_composed_and_translated(
        self, tmp_path: Path, fake_main: types.ModuleType, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # update_config 的 403 走 _insecure_bind_detail 组合模板（非中间件机器码分支）：
        # 组合四段（bind/context/action/tail）全部经 tr 渲染，断言标记出现在组合结果里。
        # 把任一段改回裸字面量拼接会让对应断言转红（变异验证）。
        import i18n
        from src import web_api as wa

        client = self._client(tmp_path, wa, cfg_host="0.0.0.0", auth="true", bind_host="0.0.0.0", bind_port=8000)
        try:
            token = _login(client)
            headers = {"Authorization": f"Bearer {token}"}
            monkeypatch.setattr(i18n, "_tr", lambda text: f"<<{text}>>")
            resp = client.put(
                "/api/config",
                json={"section": "Web", "key": "web_auth_enable", "value": "false"},
                headers=headers,
            )
            assert resp.status_code == 403
            detail = resp.json()["detail"]
            assert detail.startswith("<<非回环监听地址（当前实际监听 ")
            assert "<<不允许关闭 Web 认证>>" in detail
            assert "<<请先在 config.ini 把 web_host 改为 127.0.0.1" in detail
            assert "<<；确需对局域网无认证开放时" in detail
        finally:
            client.close()

    def test_middleware_insecure_bind_message_translated(
        self, tmp_path: Path, fake_main: types.ModuleType, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # 中间件分支（该每请求检查）：配置已「无认证 + 非回环」时 /api/* 被 403 拦截；
        # detail 是机器码契约（不翻），message 是展示文案（必须翻）。
        import i18n
        from src import web_api as wa

        client = self._client(tmp_path, wa, cfg_host="0.0.0.0", auth="false", bind_host="0.0.0.0", bind_port=8000)
        try:
            monkeypatch.setattr(i18n, "_tr", lambda text: f"<<{text}>>")
            resp = client.get("/api/status")
            assert resp.status_code == 403
            body = resp.json()
            assert body["detail"] == "insecure_bind_disabled", "机器码 detail 不得被翻译（前端契约）"
            assert body["message"] == "<<非回环监听地址下不允许关闭 Web 认证>>"
        finally:
            client.close()


class TestOriginSameHostAndPort:
    # MID-N42：Origin 同源判定不得复用为 Host 头设计的 web_config.is_host_allowed——它放行
    # 「任何 IP 字面量」「任何无点单标签名」且 _strip_host_port 把端口丢掉，于是局域网里另一台
    # 设备的页面（http://192.168.1.47/）与本机任意 dev server（http://localhost:3000/）都算同源。
    # 认证关闭（出厂默认）时这条判定是写接口唯一的 CSRF 防线，故 Origin 单独判：host 与端口都要命中期望集合。

    def _client(
        self,
        tmp_path: Path,
        wa: types.ModuleType,
        *,
        cfg_host: str = "127.0.0.1",
        auth: str = "false",
        bind_host: str | None = None,
        bind_port: int | None = None,
    ) -> TestClient:
        cfg = tmp_path / "config.ini"
        _write_web_section(cfg, auth=auth, password=wa.hash_web_password("secret123"), host=cfg_host)
        _reset_web_api_state(wa)
        app = wa.create_app(
            config_file=str(cfg),
            url_config_file=str(tmp_path / "u.ini"),
            downloads_root=str(tmp_path),
            logs_dir=str(tmp_path),
            bind_host=bind_host,
            bind_port=bind_port,
        )
        return TestClient(app, base_url=_BASE_URL)

    @pytest.mark.parametrize(
        "origin",
        [
            "http://192.168.1.47",  # 局域网里另一台设备上的网页（无端口 → 80）
            "http://192.168.1.47:3000",  # 同机 dev server，端口不是面板的
            "http://localhost:3000",  # 本机 dev server：host 命中回环，端口不命中
            "http://127.0.0.1:9999",  # 与放行项只差端口 → 拒绝必须归因于端口判定
            "http://100.64.0.1:8000",  # CGNAT 形态的 IP 字面量不再是「同源」的同义词
            "http://evil.example.com",
            "https://127.0.0.1",  # https 的默认端口 443 ≠ 实际绑定端口 8000
            "http://user@127.0.0.1:8000",  # Origin 不带 userinfo，畸形形态一律判否
        ],
    )
    def test_foreign_origin_write_denied(self, tmp_path: Path, fake_main: types.ModuleType, origin: str) -> None:
        from src import web_api as wa

        client = self._client(tmp_path, wa, bind_host="127.0.0.1", bind_port=8000)
        try:
            resp = client.put("/api/rooms/qualities", json={"options": ["超清"]}, headers={"Origin": origin})
            assert resp.status_code == 403, f"{origin} 被判同源: {resp.text}"
            assert resp.json()["detail"] == "cross-origin request denied"
        finally:
            client.close()

    @pytest.mark.parametrize(
        "origin", ["http://127.0.0.1:8000", "http://localhost:8000", "http://[::1]:8000", "https://127.0.0.1:8000"]
    )
    def test_same_host_and_port_write_allowed(self, tmp_path: Path, fake_main: types.ModuleType, origin: str) -> None:
        # 反向护栏：收紧不得把面板自己的正常入口砍掉（127.0.0.1 / localhost / IPv6 回环，
        # 以及显式带端口时以端口为准的 https 形态）。
        # 与上一条对照即「端口判定在生效」的归因证明：两组的 host 类别相同、只有端口不同。
        from src import web_api as wa

        client = self._client(tmp_path, wa, bind_host="127.0.0.1", bind_port=8000)
        try:
            resp = client.put("/api/rooms/qualities", json={"options": ["超清"]}, headers={"Origin": origin})
            assert resp.status_code == 200, f"{origin} 被误判跨源: {resp.text}"
        finally:
            client.close()

    def test_denial_follows_port_when_host_is_held_constant(self, tmp_path: Path, fake_main: types.ModuleType) -> None:
        # 「拒绝确实来自端口判定」的归因对（MID-N42）：同一条用例里 host 逐字不变、只把端口在
        # 8000 与不匹配值之间切换，结论必须翻转。拆到两条 parametrize 用例里也能看出差分，但那是
        # 「两个 client + 两次构造」的间接对比，一旦某一侧的构造参数被改动就会悄悄失去对照意义。
        from src import web_api as wa

        client = self._client(tmp_path, wa, bind_host="127.0.0.1", bind_port=8000)
        try:
            # 本机 dev server：主机名属回环族（Host 那套规则会放行它），端口不命中 → 403。
            # 其中 http://localhost 与 https://127.0.0.1 是「省略端口 → 按 scheme 默认值补 80/443」，
            # 同样不等于绑定的 8000，故一并落在被拒一侧。
            for origin in ("http://localhost:3000", "http://127.0.0.1:9999", "http://localhost", "https://127.0.0.1"):
                resp = client.put("/api/rooms/qualities", json={"options": ["超清"]}, headers={"Origin": origin})
                assert resp.status_code == 403, f"{origin} 被判同源: {resp.text}"
                assert resp.json()["detail"] == "cross-origin request denied"
            # 只把端口改成实际绑定的 8000（host 逐字不变）→ 必须通过
            for origin in ("http://localhost:8000", "http://127.0.0.1:8000"):
                resp = client.put("/api/rooms/qualities", json={"options": ["超清"]}, headers={"Origin": origin})
                assert resp.status_code == 200, f"{origin} 被误判跨源: {resp.text}"
        finally:
            client.close()

    def test_denial_follows_host_when_port_is_held_constant(self, tmp_path: Path, fake_main: types.ModuleType) -> None:
        # 另一半归因：http://192.168.1.47 被拒不能只是因为「默认端口 80 ≠ 8000」。
        # 这里把端口钉死为绑定端口 8000、只有 host 变化，结论仍须区分——证明「IP 字面量即同源」
        # 这条来自 is_host_allowed 的宽松规则确实没有漏进 Origin 判定。
        # 认证开启（避免与「非回环 + 无认证」锁住逻辑混叠）：过了 Origin 关的请求回 401 而非 403，
        # 401/403 的差值即「Origin 判定在生效」的直接读数。
        from src import web_api as wa

        client = self._client(tmp_path, wa, cfg_host="0.0.0.0", auth="true", bind_host="0.0.0.0", bind_port=8000)
        try:
            resp = client.put(
                "/api/rooms/qualities", json={"options": ["超清"]}, headers={"Origin": "http://192.168.1.47:8000"}
            )
            assert resp.status_code == 403, f"IP 字面量仍被判同源: {resp.text}"
            assert resp.json()["detail"] == "cross-origin request denied"
            # 局域网里另一台设备的 80 端口页面（MID-N42 正文点名的 http://192.168.1.47/）同样被拒
            assert (
                client.put(
                    "/api/rooms/qualities", json={"options": ["超清"]}, headers={"Origin": "http://192.168.1.47"}
                ).status_code
                == 403
            )
            for origin in ("http://localhost:8000", "http://127.0.0.1:8000"):
                resp = client.put("/api/rooms/qualities", json={"options": ["超清"]}, headers={"Origin": origin})
                assert (
                    resp.status_code == 401
                ), f"{origin} 未过 Origin 关（期望 401 实得 {resp.status_code}）: {resp.text}"
        finally:
            client.close()

    def test_expected_port_comes_from_bind_not_config(self, tmp_path: Path, fake_main: types.ModuleType) -> None:
        # SEV-N03 同族的「端口也是可写的配置值」问题：web_port 同样能经 PUT /api/config 改写，
        # 而进程监听端口直到重启才变。故 Origin 的期望端口取实际绑定值。
        from src import web_api as wa

        client = self._client(tmp_path, wa, cfg_host="127.0.0.1", auth="true", bind_host="192.168.1.47", bind_port=9000)
        try:
            # 实际绑定 host:port 命中 → 不是 403（认证开启下无 token 会 401，据此区分「过了 Origin 关」）
            resp = client.put(
                "/api/rooms/qualities",
                json={"options": ["超清"]},
                headers={"Origin": "http://192.168.1.47:9000"},
            )
            assert resp.status_code == 401, resp.text
            # 按配置里的 web_port=8000 判就会放行 → 必须 403，证明期望端口不来自配置
            resp2 = client.put(
                "/api/rooms/qualities",
                json={"options": ["超清"]},
                headers={"Origin": "http://192.168.1.47:8000"},
            )
            assert resp2.status_code == 403, f"期望端口仍读配置的 web_port: {resp2.text}"
        finally:
            client.close()

    def test_registered_allowed_hosts_may_pin_a_port(self, tmp_path: Path, fake_main: types.ModuleType) -> None:
        # 反代/自定义入口端口的合法部署：web_allowed_hosts 登记 host[:port] 后按登记端口判。
        from src import web_api as wa

        cfg = tmp_path / "config.ini"
        _write_web_section(cfg, auth="false", password="", host="127.0.0.1")
        cfg.write_text(
            cfg.read_text(encoding="utf-8-sig") + "web_allowed_hosts = panel.lan, proxy.example:8443\n",
            encoding="utf-8-sig",
        )
        _reset_web_api_state(wa)
        app = wa.create_app(
            config_file=str(cfg),
            url_config_file=str(tmp_path / "u.ini"),
            downloads_root=str(tmp_path),
            logs_dir=str(tmp_path),
            bind_host="127.0.0.1",
            bind_port=8000,
        )
        client = TestClient(app, base_url=_BASE_URL)
        try:
            # 未写端口的登记项 → 仍要求等于实际绑定端口
            assert (
                client.put(
                    "/api/rooms/qualities", json={"options": ["超清"]}, headers={"Origin": "http://panel.lan:8000"}
                ).status_code
                == 200
            )
            assert (
                client.put(
                    "/api/rooms/qualities", json={"options": ["超清"]}, headers={"Origin": "http://panel.lan:9999"}
                ).status_code
                == 403
            )
            # 写了端口的登记项 → 按该端口判（反代 8443 入口）
            assert (
                client.put(
                    "/api/rooms/qualities", json={"options": ["超清"]}, headers={"Origin": "https://proxy.example:8443"}
                ).status_code
                == 200
            )
        finally:
            client.close()

    def test_host_header_policy_is_unchanged(self, tmp_path: Path, fake_main: types.ModuleType) -> None:
        # MID-N42 的边界：Origin 收紧**不得**顺带改 Host 那套规则，否则
        # DNS 重绑定防线会退化（Host 侧放行 IP 字面量/无点名是刻意的，见 is_host_allowed 注释）。
        from src import web_api as wa

        client = self._client(tmp_path, wa, bind_host="127.0.0.1", bind_port=8000)
        try:
            # 以局域网 IP 访问 Host 仍放行（0.0.0.0 部署常态），且无 Origin 的写请求不受本轮收紧影响
            assert client.get("/api/rooms", headers={"Host": "192.168.1.47:8000"}).status_code == 200
            assert (
                client.put(
                    "/api/rooms/qualities", json={"options": ["高清"]}, headers={"Host": "192.168.1.47:8000"}
                ).status_code
                == 200
            )
            # 注册域名未登记仍被 Host 名单拒（400，不是 Origin 的 403）
            assert (
                client.put(
                    "/api/rooms/qualities", json={"options": ["高清"]}, headers={"Host": "attacker.tld"}
                ).status_code
                == 400
            )
        finally:
            client.close()

    def test_starlette_testserver_sentinel_is_exempted_only_without_port(
        self, tmp_path: Path, fake_main: types.ModuleType
    ) -> None:
        # 测试桩豁免的边界（web_config.is_origin_allowed 内注释所述）：只认「哨兵名 + 无端口」
        # 这一种组合，不得因此把任意无点主机名或任意 IP 重新放行。
        from src import web_api as wa

        client = self._client(tmp_path, wa, bind_host="127.0.0.1", bind_port=8000)
        try:
            assert (
                client.put(
                    "/api/rooms/qualities", json={"options": ["超清"]}, headers={"Origin": "http://testserver"}
                ).status_code
                == 200
            )
            # 带端口的哨兵名不豁免（端口仍须命中实际绑定端口）
            assert (
                client.put(
                    "/api/rooms/qualities", json={"options": ["超清"]}, headers={"Origin": "http://testserver:9999"}
                ).status_code
                == 403
            )
            # 另一个无点单标签名（NetBIOS 形态）不因「同属无点名」而搭车放行
            assert (
                client.put(
                    "/api/rooms/qualities", json={"options": ["超清"]}, headers={"Origin": "http://nas:9999"}
                ).status_code
                == 403
            )
        finally:
            client.close()

    def test_legacy_callers_without_bind_wiring_keep_config_fallback(
        self, tmp_path: Path, fake_main: types.ModuleType
    ) -> None:
        # 向后兼容默认值的语义锁：create_app 不传 bind_host/bind_port 时，判定回落到配置值
        # （web_host / web_port），既有调用点与用例的结论不得改变。
        from src import web_api as wa

        client = self._client(tmp_path, wa)  # bind_* 省略 = 未接线
        try:
            assert (
                client.put(
                    "/api/rooms/qualities", json={"options": ["超清"]}, headers={"Origin": "http://127.0.0.1:8000"}
                ).status_code
                == 200
            )
            assert (
                client.put(
                    "/api/rooms/qualities", json={"options": ["超清"]}, headers={"Origin": "http://127.0.0.1:9999"}
                ).status_code
                == 403
            )
        finally:
            client.close()

    def test_foreign_origins_pass_when_rule_reverts_to_host_allow_list(
        self, tmp_path: Path, fake_main: types.ModuleType, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # 归因用例：把 Origin 判定基准换回修复前形态（复用为 Host 头设计的 is_host_allowed），
        # 中间件顺序与请求载荷逐字不动。两条被点名的 Origin 此时必须**通过**，由此证明
        # test_foreign_origin_write_denied 的 403 唯一来自 MID-N42 新规则，而非 Host 名单、
        # Sec-Fetch-Site 分支或认证开关恰好挡住同一请求。
        # 注：替换的是 web_api 全局引用里的名字（from-import 后的模块属性），不触碰 stdlib、
        # 也不改 web_config 的 is_host_allowed 本体（Host 那侧必须仍是真代码）。
        from urllib.parse import urlparse

        from src import web_api as wa
        from src.web_config import is_host_allowed

        def _legacy_origin_rule(origin: str, cfg: dict[str, str | int | bool], **_kw: object) -> bool:
            parsed = urlparse(origin)
            if parsed.scheme not in ("http", "https"):
                return False
            return is_host_allowed(parsed.netloc or origin, cfg)

        # 绑回环 + 关认证：与「出厂默认 + 本机任意网页」这一实际危害场景同形
        client = self._client(tmp_path, wa, cfg_host="127.0.0.1", auth="false", bind_host="127.0.0.1", bind_port=8000)
        monkeypatch.setattr(wa, "is_origin_allowed", _legacy_origin_rule)
        try:
            for origin in ("http://192.168.1.47", "http://localhost:3000", "http://127.0.0.1:9999"):
                resp = client.put("/api/rooms/qualities", json={"options": ["超清"]}, headers={"Origin": origin})
                assert resp.status_code == 200, f"旧规则下 {origin} 仍被拒：403 另有来源，归因不成立 ({resp.text})"
        finally:
            client.close()


class TestSensitiveValueBlankRejected:
    # （后端半边）：面板对敏感项回显 '***'，用户全选删空后提交 '' 既 ≠ '***'
    # 也 ≠ 旧值 → 真实 cookie/token 被空串静默覆盖。现与 web_password 同口径：400。
    # 字面掩码 '***' 本身同样必须被服务端拦住——此前防线只有前端 saveConfig 跳过它，直接打接口的调用方可把凭据覆写成掩码。

    @pytest.mark.parametrize(
        "section,key",
        [
            ("Cookie", "抖音cookie"),
            ("推送配置", "tgapi令牌"),
            ("推送配置", "pushplus推送token"),
            ("邮箱配置", "发件人密码(授权码)"),
            ("录制设置", "代理地址"),
        ],
    )
    def test_blank_sensitive_value_rejected(
        self, app_env: types.SimpleNamespace, tmp_path: Path, section: str, key: str
    ) -> None:
        from src.web_config import append_config_line

        # 先把键补建到配置文件里（update_config_line 只做替换，缺键会 404 而绕过本用例）
        assert append_config_line(str(app_env.cfg), section, key, "real-secret-value") is True
        token = _login(app_env.client)
        resp = app_env.client.put(
            "/api/config",
            json={"section": section, "key": key, "value": "   "},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 400, f"{section}/{key} 空值提交未被拦住: {resp.text}"
        text = app_env.cfg.read_text(encoding="utf-8-sig")
        assert "real-secret-value" in text  # 真实凭据必须原样保留

    def test_non_sensitive_blank_value_still_allowed(self, app_env: types.SimpleNamespace, tmp_path: Path) -> None:
        # 反向边界：非敏感键（如 HLS采集排除平台 允许清空=不排除任何平台）不得被误伤
        from src.web_config import append_config_line

        assert append_config_line(str(app_env.cfg), "录制设置", "HLS采集排除平台(逗号分隔)", "斗鱼直播") is True
        token = _login(app_env.client)
        resp = app_env.client.put(
            "/api/config",
            json={"section": "录制设置", "key": "HLS采集排除平台(逗号分隔)", "value": ""},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200, resp.text

    @pytest.mark.parametrize(
        "section,key,value",
        [
            ("Cookie", "抖音cookie", "***"),
            ("Cookie", "抖音cookie", "  ***  "),  # 前后空白不得绕过
            ("推送配置", "tgapi令牌", "***"),
            ("邮箱配置", "发件人密码(授权码)", "***"),
            ("Web", "web_password", "***"),
        ],
    )
    def test_mask_sensitive_value_rejected(
        self, app_env: types.SimpleNamespace, section: str, key: str, value: str
    ) -> None:
        # read_config_safe 的 SENSITIVE_MASK 正是字面 '***'，掩码一旦落盘，backup_config 副本已按
        # 脱敏、无从恢复（防线演进见类头）。后端拒绝后，前端那条跳过只是省一次无谓写入。
        from src.web_config import append_config_line

        if key not in app_env.cfg.read_text(encoding="utf-8-sig"):
            # fixture 已写好的键（web_password）不再补建，避免 configparser 报重复项
            assert append_config_line(str(app_env.cfg), section, key, "real-secret-value") is True
        text_before = app_env.cfg.read_text(encoding="utf-8-sig")
        token = _login(app_env.client)
        resp = app_env.client.put(
            "/api/config",
            json={"section": section, "key": key, "value": value},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 400, f"{section}/{key} 掩码提交未被拦住: {resp.text}"
        # 整文件逐字不变：既有凭据（真实值或口令哈希）都没被掩码覆盖
        assert app_env.cfg.read_text(encoding="utf-8-sig") == text_before

    def test_only_the_exact_panel_mask_is_rejected(self, app_env: types.SimpleNamespace) -> None:
        # 归因用边界：除本条新守卫外，PUT /api/config 对敏感项**没有任何**其他按值拦截的逻辑
        # （空值守卫、危险键黑名单、validate_config_target 都不认 '***'）。故'****' 必须写成 200
        # ——它同时证明：① 上面那条 400 确实来自掩码守卫（守卫被删则该用例簇变红）；
        # ② 拒绝范围严格限定为面板回显的那一个字面值，不扩成「敏感项不能写某些字符」。
        from src.web_config import append_config_line

        assert append_config_line(str(app_env.cfg), "Cookie", "抖音cookie", "real-secret-value") is True
        token = _login(app_env.client)
        resp = app_env.client.put(
            "/api/config",
            json={"section": "Cookie", "key": "抖音cookie", "value": "****"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200, resp.text
        assert "抖音cookie = ****" in app_env.cfg.read_text(encoding="utf-8-sig")

    def test_mask_value_allowed_for_non_sensitive_key(self, app_env: types.SimpleNamespace) -> None:
        # 反向边界：拒绝只针对敏感键。非敏感键（值本身可以是任意文本）不得被误伤，
        # 否则这条防线会扩成「配置文件不能写某些字符」的功能回归。
        from src.web_config import append_config_line

        assert append_config_line(str(app_env.cfg), "录制设置", "HLS采集排除平台(逗号分隔)", "斗鱼直播") is True
        token = _login(app_env.client)
        resp = app_env.client.put(
            "/api/config",
            json={"section": "录制设置", "key": "HLS采集排除平台(逗号分隔)", "value": "***"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200, resp.text
        assert "HLS采集排除平台(逗号分隔) = ***" in app_env.cfg.read_text(encoding="utf-8-sig")


class TestOutboundTargetKeysValidated:
    # MID-N45：PUT /api/config 对「值」只做换行校验时，钉钉/微信/bark/ntfy 的推送接口地址会被
    # msg_push.py 用 urllib opener 直接请求（且支持逗号分隔多目标）、代理地址与 smtp邮件服务器
    # 同样是本进程自己发出去的出站目标，这些全局量又在 main.py 的热重载里每轮重读——无需重启
    # 即可把服务端驱动去请求 http://127.0.0.1:6379/ 或 http://169.254.169.254/。房间地址那套
    # scheme + 内网收口没覆盖到这里，构成同一条信任边界上的第二条 SSRF 出口，故出站目标键须校验。

    _PUSH_KEYS = ("钉钉推送接口链接", "微信推送接口链接", "bark推送接口链接", "ntfy推送地址")

    def _put(self, app_env: types.SimpleNamespace, section: str, key: str, value: str) -> Response:
        token = _login(app_env.client)
        # app_env 是 SimpleNamespace → 属性访问为 Any，返回处显式收敛（mypy warn_return_any）
        return cast(
            Response,
            app_env.client.put(
                "/api/config",
                json={"section": section, "key": key, "value": value},
                headers={"Authorization": f"Bearer {token}"},
            ),
        )

    @pytest.mark.parametrize("key", _PUSH_KEYS)
    @pytest.mark.parametrize(
        ("value", "reason", "hinted"),
        [
            ("http://127.0.0.1:6379/", "回环地址", True),  # 本机 Redis：内网探测 + RESP 写入面
            ("http://169.254.169.254/latest/meta-data/", "云厂商元数据端点", True),
            ("http://192.168.1.20/x", "私网地址", True),
            ("ftp://oapi.dingtalk.com/robot/send", "协议不允许", False),  # 非 http(s) 一律拒
            ("oapi.dingtalk.com/robot/send", "协议不允许", False),  # 缺协议：urllib 本就发不出去
        ],
    )
    def test_push_url_rejected_for_internal_illegal_and_bad_scheme(
        self, app_env: types.SimpleNamespace, key: str, value: str, reason: str, hinted: bool
    ) -> None:
        resp = self._put(app_env, "推送配置", key, value)
        assert resp.status_code == 422, f"{key} <- {value} 未被拦住: {resp.text}"
        detail = resp.json()["detail"]
        # 文案必须点名是**哪个配置项**被拒（面板一次提交一个键，但同一份文案也用于逐段判定）
        assert key in detail, detail
        assert reason in detail, f"拒绝理由不可行动（缺 {reason}）: {detail}"
        # 指向内网/元数据的一侧还要给出破例通道；协议不匹配的一侧不该出现无关提示
        assert ("DOUYIN_WEB_ALLOW_INTERNAL_TARGET" in detail) is hinted, detail

    def test_push_url_accepts_public_target_and_multi_target_all_must_pass(
        self, app_env: types.SimpleNamespace
    ) -> None:
        from src.web_config import append_config_line

        key = "ntfy推送地址"
        assert append_config_line(str(app_env.cfg), "推送配置", key, "https://ntfy.sh/existing") is True
        # 合法公网地址必须仍可写（收紧不得变成「推送项只读」）
        resp = self._put(app_env, "推送配置", key, "https://ntfy.sh/topic-a")
        assert resp.status_code == 200, resp.text
        assert "ntfy推送地址 = https://ntfy.sh/topic-a" in app_env.cfg.read_text(encoding="utf-8-sig")
        # 多目标全部合法 → 放行
        resp2 = self._put(app_env, "推送配置", key, "https://ntfy.sh/a,https://ntfy.sh/b")
        assert resp2.status_code == 200, resp2.text

    @pytest.mark.parametrize("separator", [",", "，"])
    def test_multi_target_rejected_when_any_segment_is_internal(
        self, app_env: types.SimpleNamespace, separator: str
    ) -> None:
        # 逐段校验的核心证明：msg_push 对**每一段**都发一次请求，只要有一段指向内网，
        # 整串就仍是一条可用出口 —— 只判首段（或只判尾段）都会放过另一半。
        # 全角逗号形态同步钉住：校验侧的拆分口径必须与发送侧的 replace("，", ",") 一致。
        bad_first = f"http://127.0.0.1:6379/{separator}https://ntfy.sh/ok"
        bad_last = f"https://ntfy.sh/ok{separator}http://127.0.0.1:6379/"
        for value in (bad_first, bad_last):
            resp = self._put(app_env, "推送配置", "钉钉推送接口链接", value)
            assert resp.status_code == 422, f"{value} 未被逐段拦住: {resp.text}"

    @pytest.mark.parametrize(
        ("section", "key", "seed", "value"),
        [
            # 混合多目标：前半合法、后半指向本机 Redis —— 必须整串拒绝
            (
                "推送配置",
                "钉钉推送接口链接",
                "https://oapi.dingtalk.com/robot/send/seed",
                "https://oapi.dingtalk.com/robot/send,http://127.0.0.1:6379/",
            ),
            ("推送配置", "微信推送接口链接", "https://qyapi.weixin.qq.com/cgi-bin/seed", "http://169.254.169.254/"),
            ("录制设置", "代理地址", "127.0.0.1:7890", "socks5://[fe80::1]:1080"),
            ("推送配置", "smtp邮件服务器", "smtp.example.com", "metadata"),
        ],
    )
    def test_rejected_write_leaves_file_byte_identical(
        self, app_env: types.SimpleNamespace, section: str, key: str, seed: str, value: str
    ) -> None:
        # 「整体拒绝、不得部分写入」：逐段校验只保证判定层不放行，真正要守的是落盘层——
        # 若实现写成「先写入合法的前几段、遇到非法段再报错」，配置文件会留下一个半截的
        # 推送地址串（既丢了原值、又是一条仍然可用的内网出口），比整体失败严重得多。
        # 故这里断言整文件逐字不变，而不只是断言 422。
        from src.web_config import append_config_line

        assert append_config_line(str(app_env.cfg), section, key, seed) is True
        text_before = app_env.cfg.read_text(encoding="utf-8-sig")
        assert seed in text_before
        resp = self._put(app_env, section, key, value)
        assert resp.status_code == 422, f"{key} <- {value} 未被拦住: {resp.text}"
        assert app_env.cfg.read_text(encoding="utf-8-sig") == text_before, f"{key} 被拒后配置仍被改动（部分写入）"

    @pytest.mark.parametrize("key", ["NTFY推送地址", "BARK推送接口链接"])
    def test_key_case_variant_judged_identically(self, app_env: types.SimpleNamespace, key: str) -> None:
        # 大小写变体同判（configparser 的 option 本就 casefold，该同口径）：
        # 只按规范写法精确比较，等于给拉丁前缀的键留一条绕过路径。
        resp = self._put(app_env, "推送配置", key, "http://127.0.0.1:6379/")
        assert resp.status_code == 422, f"{key} 变体绕过了出站校验: {resp.text}"

    def test_internal_target_env_switch_relaxes_loopback_but_never_metadata(
        self, app_env: types.SimpleNamespace, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # 破例通道（web_config._allow_internal_outbound_target）：自建 ntfy 与录制器同机是
        # 合法部署，故显式设开关后必须放行回环目标；但**云元数据端点永不在放行范围内**——
        # 它不是任何人的推送服务，只在被拒的一侧出现。
        from src.web_config import append_config_line

        assert append_config_line(str(app_env.cfg), "推送配置", "ntfy推送地址", "https://ntfy.sh/x") is True
        resp_before = self._put(app_env, "推送配置", "ntfy推送地址", "http://127.0.0.1:8080/topic")
        assert resp_before.status_code == 422, resp_before.text
        monkeypatch.setenv("DOUYIN_WEB_ALLOW_INTERNAL_TARGET", "1")
        resp_after = self._put(app_env, "推送配置", "ntfy推送地址", "http://127.0.0.1:8080/topic")
        assert resp_after.status_code == 200, resp_after.text
        resp_meta = self._put(app_env, "推送配置", "ntfy推送地址", "http://169.254.169.254/")
        assert resp_meta.status_code == 422, "开关不得放开云元数据端点"

    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            ("127.0.0.1:7890", 200),  # 裸 ip:port（用户主流写法，见 sync_http 注释）
            ("proxy:8080", 200),  # 裸主机名:端口（Docker/compose 服务名写法，同样经 http:// 归一）
            ("localhost:7890", 200),  # 回环的域名写法
            ("socks5://192.168.1.10:1080", 200),  # socks + 私网：合法局域网代理
            ("http://user:pass@proxy.example.com:8080", 200),  # 带凭据 + 公网
            ("http://169.254.169.254:80/", 422),  # 元数据端点
            ("socks5://[fe80::1]:1080", 422),  # 链路本地 IPv6
            ("gopher://127.0.0.1:9876", 422),  # 协议不在允许集合
        ],
    )
    def test_proxy_addr_policy_allows_local_forms_and_blocks_reserved(
        self, app_env: types.SimpleNamespace, value: str, expected: int
    ) -> None:
        # 代理地址与推送不同：本机/私网是它的**常态**（按房间口径会把合法写法整体误杀），
        # 故本条同时是「不得收紧过度」的反向护栏；被拒的一侧只覆盖保留/元数据/非法协议。
        from src.web_config import append_config_line

        assert append_config_line(str(app_env.cfg), "录制设置", "代理地址", "127.0.0.1:7890") is True
        resp = self._put(app_env, "录制设置", "代理地址", value)
        assert resp.status_code == expected, f"{value} -> {resp.status_code} != {expected}: {resp.text}"

    @pytest.mark.parametrize(
        ("value", "expected"),
        [("smtp.lan.example", 200), ("10.0.0.5", 200), ("metadata", 422), ("169.254.169.254", 422)],
    )
    def test_smtp_server_judged_by_hostname(self, app_env: types.SimpleNamespace, value: str, expected: int) -> None:
        # SMTP 值是裸主机名（不是 URL）：按 host 判定，内网邮件中继合法、元数据/内部名拒绝。
        from src.web_config import append_config_line

        assert append_config_line(str(app_env.cfg), "推送配置", "smtp邮件服务器", "smtp.example.com") is True
        resp = self._put(app_env, "推送配置", "smtp邮件服务器", value)
        assert resp.status_code == expected, f"{value} -> {resp.status_code} != {expected}: {resp.text}"

    def test_non_outbound_key_is_not_touched(self, app_env: types.SimpleNamespace) -> None:
        # 反向护栏：收口按**键名白名单**生效，不得扩成「配置文件里不能出现某些字符串」——
        # 否则这条防线会变成一次功能回归（普通键的值可能恰好长得像 URL）。
        from src.web_config import append_config_line

        assert append_config_line(str(app_env.cfg), "录制设置", "视频保存格式", "TS") is True
        resp = self._put(app_env, "录制设置", "视频保存格式", "http://127.0.0.1:6379/not-a-proxy")
        assert resp.status_code == 200, resp.text

    def test_blank_value_still_rejected_by_sensitive_guard_not_by_this_one(
        self, app_env: types.SimpleNamespace
    ) -> None:
        # 归属划分：推送/代理类键都是敏感项，空值由该「敏感配置项不得清空」拦成 400，
        # 本轮新增的出站校验对空值早返回（未配置 ≠ 非法目标）。两条守卫不得互相顶替。
        resp = self._put(app_env, "推送配置", "ntfy推送地址", "   ")
        assert resp.status_code == 400, resp.text
        assert "不得清空" in resp.json()["detail"]

    @pytest.mark.parametrize(
        ("section", "key", "seed", "value"),
        [
            ("推送配置", "钉钉推送接口链接", "https://oapi.dingtalk.com/robot/send/seed", "http://127.0.0.1:6379/"),
            # 混合多目标：只判首段就会放过它，正是逐段校验要拦的形态
            ("推送配置", "ntfy推送地址", "https://ntfy.sh/seed", "https://ntfy.sh/ok,http://169.254.169.254/"),
            ("录制设置", "代理地址", "127.0.0.1:7890", "gopher://127.0.0.1:9876"),
            ("推送配置", "smtp邮件服务器", "smtp.example.com", "metadata"),
        ],
    )
    def test_payloads_land_when_outbound_guard_is_removed(
        self,
        app_env: types.SimpleNamespace,
        section: str,
        key: str,
        seed: str,
        value: str,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # 归因用例（替代被沙箱拦住的变异验证）：只把 MID-N45 挂在 validate_config_target 上的
        # 那一步置为 no-op，其余守卫（换行校验、危险键黑名单、敏感项空值/掩码守卫、
        # update_config_line 的行级替换）全部保持真实。此时同一载荷必须**写成 200 并落盘**，
        # 由此证明上面那一整簇 422 唯一来自出站目标收口；同时也反证
        # test_rejected_write_leaves_file_byte_identical 不是「写入永远失败」造成的假绿。
        from src import web_config as wc
        from src.web_config import append_config_line

        assert append_config_line(str(app_env.cfg), section, key, seed) is True
        monkeypatch.setattr(wc, "_validate_outbound_target_value", lambda key, value: None)
        resp = self._put(app_env, section, key, value)
        assert resp.status_code == 200, f"摘除出站收口后 {value} 仍被拒，说明另有防线，归因不成立: {resp.text}"
        assert value in app_env.cfg.read_text(encoding="utf-8-sig"), "200 却未落盘：断言对象不是同一条写路径"


class TestDeleteRoomReportsTruth:
    # 调用侧：delete_line 在 CRLF 文件上曾静默 no-op 而端点无条件回报 {"ok": true}
    # （工作区 URL_config.ini 14/14 行都是 CRLF，Windows 必然发生）。
    # 现以「重新解析后目标 URL 是否真的消失」为准裁决 200/500。

    def _write_crlf(self, path: Path, lines: list[str]) -> None:
        # 必须用 newline="" 写：否则 Python 会把 \n 翻译成 \r\n 或反之，
        # 就造不出「调用方传 \n 行 / 文件是 \r\n 行」这一真实错配形态。
        with open(path, "w", encoding="utf-8-sig", newline="") as f:
            for line in lines:
                f.write(line + "\r\n")

    def test_crlf_delete_claim_matches_file(self, app_env: types.SimpleNamespace, fake_main: types.ModuleType) -> None:
        import src.config_io as config_io

        url = "https://live.douyin.com/crlf-room"
        self._write_crlf(app_env.url_cfg, [url + ",主播: CRLF", "https://live.douyin.com/keep"])
        # delete_line 走真实实现（它读 main.text_encoding / main.url_config_file / 锁）
        setattr(fake_main, "delete_line", config_io.delete_line)
        setattr(fake_main, "url_config_file", str(app_env.url_cfg))
        token = _login(app_env.client)
        resp = app_env.client.delete(f"/api/rooms?url={url}", headers={"Authorization": f"Bearer {token}"})
        still_present = any(r["url"] == url for r in _parse_rooms(app_env))
        # 核心不变量：端点回报的成功必须与文件实际内容一致（既不虚报，也不因保守而漏报）
        assert (resp.status_code == 200) is (
            not still_present
        ), f"status={resp.status_code} still_present={still_present}"
        # 跨文件契约：config_io.delete_line 已改为「两侧剥行尾后比较 + 返回 bool」，
        # 故 CRLF 文件上的删除必须真的生效。本断言同时锁住那半边——它退回到 no-op 时这里变红。
        assert resp.status_code == 200, f"CRLF 文件上删除仍被静默吞掉: {resp.text}"
        assert not still_present
        # 未选中的行与其 CRLF 行尾都不受影响
        with open(app_env.url_cfg, "r", encoding="utf-8-sig", newline="") as f:
            kept = f.read()
        assert kept == "https://live.douyin.com/keep\r\n"

    def test_lf_delete_succeeds_and_removes(self, app_env: types.SimpleNamespace, fake_main: types.ModuleType) -> None:
        # 正向对照（LF 文件）：真实删除 → 200 且列表里不再有该房间。
        # 与 CRLF 用例互为差分，可定位「行尾归一」这一根因是否修好。
        import src.config_io as config_io

        url = "https://live.douyin.com/lf-room"
        app_env.url_cfg.write_text(url + ",主播: LF\n", encoding="utf-8-sig")
        setattr(fake_main, "delete_line", config_io.delete_line)
        setattr(fake_main, "text_encoding", "utf-8-sig")
        setattr(fake_main, "url_config_file", str(app_env.url_cfg))
        token = _login(app_env.client)
        resp = app_env.client.delete(f"/api/rooms?url={url}", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200, resp.text
        assert resp.json()["ok"] is True
        assert _parse_rooms(app_env) == []

    def test_delete_line_claiming_success_but_no_removal_is_500(
        self, app_env: types.SimpleNamespace, fake_main: types.ModuleType
    ) -> None:
        # 谎报形态：delete_line 返回 True 却没删掉任何行（例如另一路并发写回）。
        # 端点必须以复核后的文件为准回 500，不得把返回值当事实。
        url = "https://live.douyin.com/liar"
        app_env.url_cfg.write_text(url + "\n", encoding="utf-8-sig")
        setattr(fake_main, "delete_line", lambda *a, **k: True)
        token = _login(app_env.client)
        resp = app_env.client.delete(f"/api/rooms?url={url}", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 500
        assert resp.json()["detail"] == "room_delete_failed"

    def test_delete_line_returns_false_is_500(
        self, app_env: types.SimpleNamespace, fake_main: types.ModuleType
    ) -> None:
        # delete_line 明确回报 False（未删到任何行）时，即便文件里恰好也没有该 URL
        # 也属异常状态（说明查行与删行口径不一致），必须 500 而不是静默成功。
        url = "https://live.douyin.com/absent-false"
        app_env.url_cfg.write_text(url + "\n", encoding="utf-8-sig")
        setattr(fake_main, "delete_line", lambda *a, **k: False)
        token = _login(app_env.client)
        resp = app_env.client.delete(f"/api/rooms?url={url}", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 500


def _parse_rooms(app_env: types.SimpleNamespace) -> list[dict[str, object]]:
    # 经真实解析入口读回房间列表（与面板 GET /api/rooms 同一实现，避免在测试里重抄一份解析）
    from src.web_config import parse_url_config

    return cast("list[dict[str, object]]", parse_url_config(str(app_env.url_cfg)))


# POST /api/recording/toggle：Web 面板「开始/停止录制」按钮的录制开关。
class TestRecordingToggle:
    def test_toggle_requires_auth(self, app_env: types.SimpleNamespace) -> None:
        # 录制开关是写操作，未带 token 必须 401（与读接口同受中间件保护）；
        # 这一条只证「未认证进不到路由」；「进到路由才会改引擎状态」由下一条对
        # fake_main.recording_enabled 的双校验负责，两条各锁一半，不可互相顶替。
        resp = app_env.client.post("/api/recording/toggle", json={"enable": True})
        assert resp.status_code == 401

    def test_toggle_flips_engine_flag(self, app_env: types.SimpleNamespace, fake_main: types.ModuleType) -> None:
        # enable 真/假须同步翻转引擎开关（返回体与 fake main 的 recording_enabled 双校验）；
        # 只断返回体会假绿：面板回显 True 而引擎没翻（或反之）都测不出来，故两处必须一致。
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

    def test_toggle_indented_comment_line_semantics(
        self, app_env: types.SimpleNamespace, fake_main: types.ModuleType, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # M-09：手编辑产生的缩进注释行（「  # url」）点「启用」必须真的取消注释。
        # 旧实现对缩进注释行假成功：lstrip("#") 剥不动前导空白，写回仍是注释行却回 enabled:true
        # （写后只比 raw_line 文本相等，验证不了语义）；disable 则写出「# # url」双注释。
        from src import config_io

        # 端点内 `import main as _main` 命中的是本 fixture 注入的假 main；update_file 用真实现
        # （它只依赖 fake 上已存在的 file_update_lock / text_encoding / ini_URL_content）。
        monkeypatch.setattr(fake_main, "update_file", config_io.update_file, raising=False)
        url_cfg: Path = app_env.url_cfg
        url_cfg.write_text("# 纯注释行\n  # https://live.example.com/9\n", encoding="utf-8")
        token = _login(app_env.client)
        headers = {"Authorization": f"Bearer {token}"}
        resp = app_env.client.post(
            "/api/rooms/toggle", json={"url": "https://live.example.com/9", "enable": True}, headers=headers
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["enabled"] is True
        lines = url_cfg.read_text(encoding="utf-8").splitlines()
        assert "https://live.example.com/9" in lines, lines
        # 再禁用：写回必须是单层注释（不得出现「# # url」双注释）
        resp = app_env.client.post(
            "/api/rooms/toggle", json={"url": "https://live.example.com/9", "enable": False}, headers=headers
        )
        assert resp.status_code == 200, resp.text
        lines = url_cfg.read_text(encoding="utf-8").splitlines()
        assert "# https://live.example.com/9" in lines, lines


class TestDangerousKeys:
    # 守护危险配置键护栏：即便认证禁用，自定义脚本执行命令等危险键仍须 403 阻断，
    # 防未授权 RCE（危险配置键无视认证的 C 类回归）。
    def test_dangerous_key_blocked_when_auth_disabled(self, tmp_path: Path, fake_main: types.ModuleType) -> None:
        # 不用 app_env fixture：它必须整站认证关闭（自建 app、auth="false"），
        # 才能证明 403 与登录态无关，而不是被中间件顺手挡掉的假绿。
        from src import web_api as wa

        cfg = tmp_path / "config.ini"
        _write_web_section(cfg, auth="false", password="")
        app = wa.create_app(
            config_file=str(cfg),
            url_config_file=str(tmp_path / "u.ini"),
            downloads_root=str(tmp_path),
            logs_dir=str(tmp_path),
        )
        _reset_web_api_state(wa)
        client = TestClient(app, base_url=_BASE_URL)
        try:
            resp = client.put(
                "/api/config",
                json={"section": "录制设置", "key": "自定义脚本执行命令", "value": "calc"},
            )
            assert resp.status_code == 403
        finally:
            client.close()

    @pytest.mark.parametrize(
        "section,key,value",
        [
            ("录制设置", "是否录制完成后执行自定义脚本", "true"),
            ("Web", "web_trusted_proxy", "9.9.9.9"),
            ("Web", "web_allowed_hosts", "evil.example.com"),
            ("Web", "WEB_ALLOWED_HOSTS", "evil.example.com"),
            # M-08：该键是免鉴权 /favicon.ico 的图标路径源，经面板写成任意绝对路径
            # 即构成「写路径 → 免鉴权读回原文」的任意文件读链（raw config.ini 的 Cookie/口令整条
            # 绕开 '***' 掩码），入黑名单与另四键同级。
            ("Web", "web_tray_icon", r"C:\Windows\win.ini"),
        ],
    )
    def test_m64_script_flag_and_safety_keys_blocked_when_auth_disabled(
        self, tmp_path: Path, fake_main: types.ModuleType, section: str, key: str, value: str
    ) -> None:
        # 翻转「是否录制完成后执行自定义脚本」即启用用户既有脚本命令，等于把
        # 「自定义脚本执行命令」黑名单旁路一半；web_trusted_proxy 决定 XFF 是否可信（该换键面）、
        # web_allowed_hosts 决定 Host/Origin 名单，两键被面板写入等于把防线交给写接口。
        # 与既有危险键同口径：认证关闭也 403。第 4 参用大小写变体锁该折叠面（行匹配 IGNORECASE，黑名单同等强度）。
        # 预置键存在（web_trusted_proxy 由 _write_web_section 写好，其余按缺失补建）——
        # 变异可见性：从黑名单摘掉键后落进 update_config_line 得 200 而非 404/403，本条转红
        from src import web_api as wa
        from src.web_config import append_config_line

        cfg = tmp_path / "config.ini"
        _write_web_section(cfg, auth="false", password="")
        if key.casefold() not in cfg.read_text(encoding="utf-8-sig").casefold():
            assert append_config_line(str(cfg), section, key, "seed") is True
        app = wa.create_app(
            config_file=str(cfg),
            url_config_file=str(tmp_path / "u.ini"),
            downloads_root=str(tmp_path),
            logs_dir=str(tmp_path),
        )
        _reset_web_api_state(wa)
        client = TestClient(app, base_url=_BASE_URL)
        try:
            before = cfg.read_bytes()
            resp = client.put("/api/config", json={"section": section, "key": key, "value": value})
            assert resp.status_code == 403, f"{section}/{key} 仍可经面板改写: {resp.text}"
            assert cfg.read_bytes() == before, "被拒的危险键写入仍改了 config.ini"
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
        # 链接目标取 app_env.cfg —— downloads 之外**确实存在**的文件，于是「未列出」只能
        # 来自路径判定；与 test_broken_symlink_skipped 互为差分（那条的成因是目标不存在）。
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
        # 反向护栏：上面两条「跳过」若被实现写成「非 downloads 根直接子项一律跳过」，
        # 只有这条会红——它是符号链接用例簇的唯一对照，不是冗余的目录浏览演练。
        sub = app_env.downloads / "sub"
        sub.mkdir()
        (sub / "a.ts").write_text("x", encoding="utf-8")
        token = _login(app_env.client)
        resp = app_env.client.get("/api/files?path=sub", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        names = [i["name"] for i in resp.json()]
        assert "a.ts" in names


# 免鉴权预算键集合、Content-Disposition 净化、日志尾读字节预算、chunked 请求体上限——四条「资源放大面」的有界性锁。
class TestResourceCaps2026_10_21:
    def test_public_budget_key_set_is_capped(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # ①：窗口回收只清「全部条目已出窗」的键，持有 IPv6 前缀的攻击者在窗内轮换源
        # 地址即可让 dict 无界增长。现在新键入库前先查键数上限（_DENIED_HOSTS_SEEN_MAX 同形态）。
        # 变异可见性：摘掉 to-limit clear → 64 个在窗键 + 新键 = 65 > 上限，断言转红
        import time as _time
        from collections import deque

        from src import web_api as wa

        now = _time.monotonic()
        seeded = {f"2001:db8:{i}::1": deque([now]) for i in range(wa._PUBLIC_BUDGET_MAX_KEYS)}
        monkeypatch.setattr(wa, "_PUBLIC_BUDGET", seeded)
        assert wa._public_endpoint_over_budget("2001:db8:ffff::1") is False
        assert (
            len(wa._PUBLIC_BUDGET) <= wa._PUBLIC_BUDGET_MAX_KEYS
        ), f"键集合无上限（M-67 回收失效）: {len(wa._PUBLIC_BUDGET)}"

    def test_download_content_disposition_filename_is_sanitized(
        self, app_env: types.SimpleNamespace, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # ②：磁盘文件名原样进 Content-Disposition——Windows 命名规则恰好挡得住
        # CR/LF/引号，Linux 部署（本仓支持 docker）里这些字符全是合法文件名。
        # 变异可见性：还原成 FileResponse(..., filename=os.path.basename(target)) 后，
        # Starlette 会把带控制字符的名字转 percent-form（filename*=utf-8''…），
        # 本条的 quoted-string 精确断言随之落空
        from src import web_api as wa

        (app_env.downloads / "good.ts").write_text("x", encoding="utf-8")
        token = _login(app_env.client)
        os_shim = types.SimpleNamespace(**vars(wa.os))
        path_shim = types.SimpleNamespace(**vars(wa.os.path))
        path_shim.basename = lambda _p: 'evil\t"name\x0b\x0c'
        os_shim.path = path_shim
        monkeypatch.setattr(wa, "os", os_shim)
        resp = app_env.client.get("/api/files/download?path=good.ts", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200, resp.text
        cd = resp.headers["content-disposition"]
        assert cd == 'attachment; filename="evilname"', f"净化未生效，头部仍是 {cd!r}"
        assert "\r" not in cd and "\n" not in cd

    def test_get_logs_is_byte_bounded_on_large_log(
        self, app_env: types.SimpleNamespace, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # ②：旧实现 `deque(f, maxlen=lines)` 的 maxlen 只限保留条数，整文件仍被逐行读完；
        # 本端点是同步 def，占 anyio 线程池（默认 40 槽）一格，几条并发即可拖死整个面板。
        # 判据两段：正常预算下「尾部 5 行内容逐字对」；预算收紧到 20 字节后 lines=5 只可能
        # 拿到窗口内的 <5 行——旧整文件读法在这里恒回 5 行（变异可见）
        from src import web_api as wa

        logs_dir = app_env.downloads.parent / "logs"
        (logs_dir / "streamget.log").write_text("".join(f"L{i}\n" for i in range(20000)), encoding="utf-8")
        token = _login(app_env.client)
        headers = {"Authorization": f"Bearer {token}"}
        resp = app_env.client.get("/api/logs?lines=5", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["lines"] == [f"L{i}" for i in range(19995, 20000)]
        monkeypatch.setattr(wa, "_LOG_TAIL_MAX_BYTES", 20)
        out = app_env.client.get("/api/logs?lines=5", headers=headers).json()["lines"]
        assert out and out[-1] == "L19999" and len(out) < 5, f"字节预算未生效: {out}"

    def test_chunked_json_body_without_content_length_is_capped(self, app_env: types.SimpleNamespace) -> None:
        # ①：该旧口径「Content-Length 缺失时不拦」已被证伪——request.json() 会把
        # 无上限的 chunked 流整体物化。httpx 对 sync iterable content 不发 Content-Length，
        # 正好复现该形态；反向半边：同一路径下 20KB 的小 chunked 体必须照常解析（200），
        # 否则「上限」会被改成「一律拒绝」也测不出来
        from src import web_api as wa

        assert wa._JSON_BODY_MAX_BYTES == 1024 * 1024
        big_chunk = b'{"password": "' + b"x" * 1024

        def big_body() -> Generator[bytes, None, None]:
            for _ in range(wa._JSON_BODY_MAX_BYTES // 1024 + 64):
                yield big_chunk

        resp = app_env.client.post("/api/login", content=big_body())
        assert resp.status_code == 413, resp.text

        small_body = [b'{"password": ', b'"secret123"}']
        resp2 = app_env.client.post("/api/login", content=iter(small_body))
        assert resp2.status_code == 200, resp2.text


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
        # 断言集合**全等**而非包含：四语目录多一门或少一门（zh_TW 走 YAML、依赖 PyYAML）
        # 都必须在这里显形，否则面板下拉会列出点不开的语言。
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
        # 归一后的内部键须同时体现在应答与落盘两处；本条只断应答，落盘侧的
        # "language = en_US" 由 test_put_language_switches_and_persists 负责，两条不互相顶替。
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
        # 必须是 400 而不是「静默回退 FALLBACK_LANGUAGE 后回 200」：面板会以为切换已生效，
        # 进程实际装载的还是旧译文。
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
        # append_config_line 行级追加的边界：目标节存在（含无尾换行文件）与节缺失时新建于尾部。
        # 直接测 web_config 纯函数（web_api 自该改造后不再转发导入该符号）
        from src.web_config import append_config_line

        # 节存在但中间夹有其他内容：插入点应在下一节头之前、保留注释与顺序
        cfg = app_env.cfg
        cfg.write_text(
            "[Web]\nweb_auth = true\n# 注释行\n[录制设置]\ndelay = 5\n[Cookie]\nk = v\n", encoding="utf-8-sig"
        )
        assert append_config_line(str(cfg), "录制设置", "language", "en_US") is True
        lines = cfg.read_text(encoding="utf-8-sig").splitlines()
        assert lines.index("language = en_US") < lines.index("[Cookie]")
        assert "# 注释行" in lines

        # 目标节是最后一节且文件无尾换行：追加后不应与原末行粘连
        cfg.write_text("[Web]\nweb_auth = true\n[录制设置]\ndelay = 5", encoding="utf-8-sig")
        assert append_config_line(str(cfg), "录制设置", "language", "zh_TW") is True
        text = cfg.read_text(encoding="utf-8-sig")
        assert "delay = 5\nlanguage = zh_TW" in text

        # 节缺失：文件尾新建节再插键，返回 True
        cfg.write_text("[Web]\nweb_auth = true\n", encoding="utf-8-sig")
        assert append_config_line(str(cfg), "录制设置", "language", "en_GB") is True
        assert "[录制设置]\nlanguage = en_GB\n" in cfg.read_text(encoding="utf-8-sig")

    def test_put_language_rejects_empty(self, app_env: types.SimpleNamespace) -> None:
        # 空白串与「白名单外的码」共用同一条 400（`not value.strip() or not is_recognized_language(...)`）；
        # 本条锁的是前半：空白不得被当成「用户没填」而静默走 200 补建分支。
        token = _login(app_env.client)
        resp = app_env.client.put(
            "/api/language", json={"language": "  "}, headers={"Authorization": f"Bearer {token}"}
        )
        assert resp.status_code == 400

    def test_put_language_persists_effective_code_when_catalog_missing(
        self, app_env: types.SimpleNamespace, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # （Web 半边）：i18n.set_language() 现在返回**实际生效**的语言码——它按
        # resolve_language 的口径查 has_catalog，目录缺失（PyYAML 未装 → zh_TW.yaml 加载不了、
        # 发行包漏装某语言文件）时回退。端点必须落盘并应答这个生效码：写请求值会让
        # 面板进程装载着回退语言的译文、而录制子进程每轮重解析到另一码 → 同一部署两种语言。
        import i18n as i18n_module

        saved = i18n_module.get_language()
        try:
            self._write_language_section(app_env.cfg, "zh_cn")
            real_has_catalog = i18n_module.has_catalog

            def _no_zh_tw(lang: str) -> bool:
                return lang != "zh_TW" and real_has_catalog(lang)

            monkeypatch.setattr(i18n_module, "has_catalog", _no_zh_tw)
            token = _login(app_env.client)
            resp = app_env.client.put(
                "/api/language", json={"language": "zh-TW"}, headers={"Authorization": f"Bearer {token}"}
            )
            assert resp.status_code == 200, resp.text
            body = resp.json()
            assert body["language"] == "en_US"  # 生效码，不是请求值
            assert body["requested"] == "zh_TW"
            assert body["fallback"] is True
            assert body["notice"]
            text = app_env.cfg.read_text(encoding="utf-8-sig")
            assert "language = en_US" in text
            assert "zh_TW" not in text  # 缺目录的码一律不落盘
            assert i18n_module.get_language() == "en_US"
        finally:
            _ = i18n_module.set_language(saved)

    def test_put_language_reports_no_fallback_when_catalog_present(self, app_env: types.SimpleNamespace) -> None:
        # 正常路径的对称断言：目录在位时 fallback 必须为 False 且无提示语，
        # 否则「回退告警」会变成常态噪音、失去判定价值。
        import i18n as i18n_module

        saved = i18n_module.get_language()
        try:
            self._write_language_section(app_env.cfg, "zh_cn")
            token = _login(app_env.client)
            resp = app_env.client.put(
                "/api/language", json={"language": "en_GB"}, headers={"Authorization": f"Bearer {token}"}
            )
            assert resp.status_code == 200, resp.text
            body = resp.json()
            assert body["language"] == "en_GB" and body["requested"] == "en_GB"
            assert body["fallback"] is False and body["notice"] == ""
            assert "language = en_GB" in app_env.cfg.read_text(encoding="utf-8-sig")
        finally:
            _ = i18n_module.set_language(saved)

    def test_put_language_write_failure_rolls_back_in_process_language(
        self, app_env: types.SimpleNamespace, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # 「先切换再落盘」换来的语义必须有回滚兜底：写回失败若不回滚内存态，
        # 面板/本进程说新码、config.ini（及重启后的录制子进程）仍说旧码 ——
        # 与该要消灭的「两进程两种语言」是同一形态，只是换了达成路径。
        import i18n as i18n_module
        from src import web_api as wa

        saved = i18n_module.get_language()
        _ = i18n_module.set_language("zh_CN")
        try:
            self._write_language_section(app_env.cfg, "zh_cn")
            monkeypatch.setattr(wa, "update_or_append_config_line", lambda *a, **k: False)
            token = _login(app_env.client)
            resp = app_env.client.put(
                "/api/language", json={"language": "en_US"}, headers={"Authorization": f"Bearer {token}"}
            )
            assert resp.status_code == 500, resp.text
            assert i18n_module.get_language() == "zh_CN"  # 已回滚，未留下半切换状态
            assert "language = en_US" not in app_env.cfg.read_text(encoding="utf-8-sig")
        finally:
            _ = i18n_module.set_language(saved)


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

    def test_put_write_failure_detail_is_fixed_code_without_path(
        self, app_env: types.SimpleNamespace, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # 写失败的 500 detail 对外固定 code、路径只进日志（曾直接拼 app.state.config_file
        # 绝对路径——本文件唯一一处「对外不回显内部路径」违例，认证关闭时对局域网可见）。
        # 变异可见性：还原旧 tr("...: {err}", err=config_file) 写法 → detail 不再是固定 code
        # 且含 tmp 路径，两条断言同时转红
        from src import web_api as wa

        monkeypatch.setattr(wa, "write_quality_options", lambda *a, **k: None)
        token = _login(app_env.client)
        resp = app_env.client.put(
            "/api/rooms/qualities", json={"options": ["超清"]}, headers={"Authorization": f"Bearer {token}"}
        )
        assert resp.status_code == 500
        assert resp.json()["detail"] == "quality_write_failed", resp.text
        assert str(app_env.cfg.parent) not in resp.text, "500 detail 泄露配置文件绝对路径（MID-39 违例回归）"


class TestErrorDetailI18n:
    # 面板错误 detail 是用户可见文案（前端 apiError 原样弹 toast），全部经 i18n_module.tr 按当前
    # 语言渲染；稳定机器码 detail（unauthorized / rate_limited / host_not_allowed /
    # insecure_bind_disabled）是前端契约，不应被翻译。本组用例把 _tr 换成标记函数证明
    # 「确实查了目录」——把 detail 改回裸字面量会转红。

    def test_login_failure_detail_translated(
        self, app_env: types.SimpleNamespace, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import i18n

        monkeypatch.setattr(i18n, "_tr", lambda text: f"<<{text}>>")
        resp = app_env.client.post("/api/login", json={"password": "wrong"})
        assert resp.status_code == 401
        assert resp.json()["detail"] == "<<密码错误>>"

    def test_files_endpoint_detail_translated(
        self, app_env: types.SimpleNamespace, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import i18n

        token = _login(app_env.client)
        monkeypatch.setattr(i18n, "_tr", lambda text: f"<<{text}>>")
        resp = app_env.client.get(
            "/api/files", params={"path": "../outside"}, headers={"Authorization": f"Bearer {token}"}
        )
        assert resp.status_code == 400
        assert resp.json()["detail"] == "<<非法路径>>"

    def test_room_not_found_detail_translated(
        self, app_env: types.SimpleNamespace, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import i18n

        token = _login(app_env.client)
        monkeypatch.setattr(i18n, "_tr", lambda text: f"<<{text}>>")
        resp = app_env.client.delete(
            "/api/rooms",
            params={"url": "https://live.douyin.com/999999999"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 404
        assert resp.json()["detail"] == "<<未找到直播间>>"


class TestIconEndpoints:
    # 面板图标（上传 + favicon）的回归锁。三条要害：
    #   ① 上传必须**先校验后落盘**——坏文件不该在 config/icons/ 里留下一份垃圾副本；
    #   ② 拒绝原因回机器码（前端按码取文案），不回中文（否则四目录要再同步一份后端文案）；
    #   ③ favicon 免鉴权（标签页请求不带 Bearer），但没有可用图标时要 404 而不是空 200
    #      （空 200 会被浏览器缓存成一个坏图标，之后即使导入了也刷不掉）。

    def _ico_bytes(self) -> bytes:
        repo_icon = Path(__file__).resolve().parent.parent / "assets" / "app.ico"
        assert repo_icon.is_file(), "assets/app.ico 缺失"
        return repo_icon.read_bytes()

    def test_upload_requires_auth(self, app_env: types.SimpleNamespace) -> None:
        resp = app_env.client.post("/api/icon", json={"name": "a.ico", "data": "AA=="})
        assert resp.status_code == 401

    def test_upload_persists_icon_and_config(self, app_env: types.SimpleNamespace) -> None:
        import base64

        token = _login(app_env.client)
        payload = base64.b64encode(self._ico_bytes()).decode("ascii")
        resp = app_env.client.post(
            "/api/icon", json={"name": "app.ico", "data": payload}, headers={"Authorization": f"Bearer {token}"}
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["ok"] is True and body["persisted"] is True
        stored = Path(body["path"])
        assert stored.is_file() and stored.parent.name == "icons"
        # 写回 config.ini 后下次启动才能重新加载（与字体导入同一口径）
        from src import ui_icons

        assert ui_icons.load_icon_preference(
            Path(app_env.cfg), ui_icons.WEB_SECTION, ui_icons.WEB_ICON_KEY
        ), "图标路径未写回 config.ini"

    def test_upload_rejects_bad_base64(self, app_env: types.SimpleNamespace) -> None:
        token = _login(app_env.client)
        resp = app_env.client.post(
            "/api/icon", json={"name": "a.ico", "data": "not base64 !!"}, headers={"Authorization": f"Bearer {token}"}
        )
        assert resp.status_code == 422
        assert resp.json()["detail"] == "bad_base64"

    def test_upload_rejects_non_ico_payload(self, app_env: types.SimpleNamespace) -> None:
        import base64

        token = _login(app_env.client)
        payload = base64.b64encode(b"\x89PNG" + b"x" * 64).decode("ascii")
        resp = app_env.client.post(
            "/api/icon", json={"name": "a.ico", "data": payload}, headers={"Authorization": f"Bearer {token}"}
        )
        assert resp.status_code == 400
        assert resp.json()["detail"] == "not_ico"
        # 坏文件不得落盘：留下一份垃圾副本会让下次启动去加载它
        icon_dir = Path(app_env.cfg).parent / "icons"
        assert not icon_dir.is_dir() or not list(icon_dir.glob("*.ico"))

    def test_upload_rejects_icon_without_tray_size(self, app_env: types.SimpleNamespace) -> None:
        import base64
        import struct

        token = _login(app_env.client)
        # 只有 32/256 两档：托盘那一档缺失（判据同 GUI 侧「导入图标…」）
        header = b"\x00\x00\x01\x00" + struct.pack("<H", 2)
        entries = struct.pack("<BBBBHHII", 32, 32, 0, 0, 1, 32, 0, 0) + struct.pack(
            "<BBBBHHII", 0, 0, 0, 0, 1, 32, 0, 0
        )
        resp = app_env.client.post(
            "/api/icon",
            json={"name": "a.ico", "data": base64.b64encode(header + entries).decode("ascii")},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 400
        assert resp.json()["detail"] == "no_tray_size"

    def test_favicon_is_public_and_follows_the_uploaded_icon(self, app_env: types.SimpleNamespace) -> None:
        import base64
        import struct

        token = _login(app_env.client)
        payload = base64.b64encode(self._ico_bytes()).decode("ascii")
        _ = app_env.client.post(
            "/api/icon", json={"name": "app.ico", "data": payload}, headers={"Authorization": f"Bearer {token}"}
        )
        # 免鉴权：标签页的 favicon 请求不带 Bearer
        resp = app_env.client.get("/favicon.ico")
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("image/")
        assert resp.content[:4] == struct.pack("<HH", 0, 1)

    def test_favicon_404_when_no_icon_available(
        self, app_env: types.SimpleNamespace, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # 打断「仓库内置图标」兜底，验证「真没有」时是 404 而不是空 200
        monkeypatch.setattr(app_env.wa, "current_icon_path", lambda _root, _configured: None)
        assert app_env.client.get("/favicon.ico").status_code == 404

    def test_favicon_rejects_non_ico_configured_path(self, app_env: types.SimpleNamespace) -> None:
        # M-08 读取侧防线：web_tray_icon 指向的文件在回读前必须复验 ICO 魔数。
        # config.ini 可被绕过面板的手段写入任意绝对路径（手编辑/旧版本面板写入），免鉴权路由
        # 若照单 FileResponse 等于任意文件读——'***' 掩码只作用于 /api/config 读侧，对响应体不生效。
        secret_file = Path(app_env.cfg).parent / "secret.txt"
        secret_file.write_text("COOKIE=leak", encoding="utf-8")
        cfg: Path = app_env.cfg
        cfg.write_text(cfg.read_text(encoding="utf-8-sig") + f"web_tray_icon = {secret_file}\n", encoding="utf-8-sig")
        _ = app_env.wa._invalidate_web_cfg_cache()
        resp = app_env.client.get("/favicon.ico")
        assert resp.status_code == 404
        assert b"COOKIE" not in resp.content
