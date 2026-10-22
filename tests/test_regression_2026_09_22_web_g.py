# 组 G（2026-09-22）Web 侧回归锁：SEV-2221（引擎假绿的存活判据）+ MID-2236（敏感键读写判据分叉）。
#
# 与 tests/test_web_api.py 的分工：那边覆盖鉴权中间件、掩码/空值拒绝、房间写入等既有契约；本文件
# 只放本轮两条修复对应的**失效形态**锁：
#   ① SEV-2221：/api/status 需暴露「主循环是否还在推进」这条正交证据，且证据不足时不得下发——
#      否则未接线的部署会被前端刷成红色假告警。[2026-09-23 更正] 该键连同探针已被整体撤下（见 ④），
#      本条不变量收敛为「没有确凿证据就不得下发停摆判定」，锁点移到 TestMainLoopAliveProbeWithdrawn。
#   ② MID-2236：写侧敏感判据必须与读侧（web_config.read_config_safe）同源。修复前写侧只判
#      is_sensitive_item，「键名不敏感但值本身是凭据」的项在面板上是掩码、后端却不当敏感项 →
#      掩码/空值可直接写进去，真实凭据被静默覆盖且备份已脱敏、无从恢复。
#
# 全部用例驱动**真实函数/真实端点**，测试内不重新实现判定逻辑。
# 2026-09-23 同步两处 src 侧变更：
#   ③ MID-2241 后端强复验：`PUT /api/config` 写 `[Web] web_auth_enable` / `web_password` 时，认证
#      当前已开启必须携带能过 `verify_web_password` 的 `reauth_password`，否则 403。TestAuthKeyReauth
#      因此由「锁后端不判定」翻转为「锁后端判定 + 三条反向边界」。
#   ④ SEV-2221 / SEV-2228：`main_loop_alive` 连同 `_read_main_loop_alive()` 探针已从 /api/status
#      契约撤下（它读的 `main.main_loop_ticks` 从未定义，该键永不下发 = 一条永不生效的存活信号）。
#      原 8 条用例锁的正是这条死路径，故改写为 TestMainLoopAliveProbeWithdrawn：锁「撤下」这一事实，
#      并禁止在 main 侧轮次接线之前把它加回来。

import types
from collections.abc import Generator
from pathlib import Path
from typing import cast

import pytest

from src.web_config import SENSITIVE_MASK, append_config_line, is_sensitive_item

_BASE_URL = "http://127.0.0.1:8000"
# 各 fixture 落盘的是它的 PBKDF2 哈希；本明文同时是登录口令与 MID-2241 的合法复验值
# （reauth_password 走 verify_web_password 比对**磁盘上的哈希**，故只有这一个值能过）。
_PLAIN_PWD = "secret123"


def _login(client: object) -> str:
    # 复用 test_web_api.py 的登录样板（固定密码由 fixture 写入）
    resp = client.post("/api/login", json={"password": _PLAIN_PWD})  # type: ignore[attr-defined]
    assert resp.status_code == 200, resp.text
    return cast(str, resp.json()["token"])


def _reset_web_api_state(wa: types.ModuleType) -> None:
    # 与 test_web_api.py::_reset_web_api_state 同源：清进程级缓存，避免跨用例串扰
    with wa._tokens_lock:
        wa._tokens.clear()
    wa._invalidate_web_cfg_cache()
    with wa._status_lock:
        setattr(wa, "_status_cache", None)
        setattr(wa, "_status_cache_at", 0.0)
        setattr(wa, "_status_inflight", False)
        setattr(wa, "_status_inflight_since", 0.0)
    # SEV-2221 的主循环停摆探针状态（_main_loop_probe_lock / _main_loop_probe_count /
    # _main_loop_probe_at）已随该探针从 src/web_api.py 撤下（见文件头 ④）。这里若继续 setattr，
    # 就是给一个不存在的模块全局赋值：用例照绿，却凭空塞进生产代码从不读的名字。


def _install_fake_main() -> types.ModuleType:
    # 最小 main 桩：只提供 web_api 读到的属性。get_status 返回可直接 JSON 化的快照。
    mod = types.ModuleType("main")
    setattr(mod, "get_status", lambda: {"engine_alive": True, "monitoring": 1, "recording": []})
    setattr(mod, "file_update_lock", __import__("threading").RLock())
    return mod


@pytest.fixture(scope="function")
def fake_main(monkeypatch: pytest.MonkeyPatch) -> Generator[types.ModuleType, None, None]:
    mod = _install_fake_main()
    monkeypatch.setitem(__import__("sys").modules, "main", mod)
    yield mod


@pytest.fixture(scope="function")
def app_env(tmp_path: Path, fake_main: types.ModuleType) -> Generator[types.SimpleNamespace, None, None]:
    from starlette.testclient import TestClient

    from src import web_api as wa

    _reset_web_api_state(wa)

    cfg = tmp_path / "config.ini"
    url_cfg = tmp_path / "URL_config.ini"
    downloads = tmp_path / "downloads"
    downloads.mkdir()
    logs = tmp_path / "logs"
    logs.mkdir()

    cfg.parent.mkdir(parents=True, exist_ok=True)
    cfg.write_text(
        "\n".join(
            [
                "[Web]",
                "web_host = 127.0.0.1",
                "web_port = 8000",
                "web_auth_enable = true",
                f"web_password = {wa.hash_web_password(_PLAIN_PWD)}",
                "web_trusted_proxy =",
            ]
        )
        + "\n",
        encoding="utf-8-sig",
    )

    app = wa.create_app(
        config_file=str(cfg),
        url_config_file=str(url_cfg),
        downloads_root=str(downloads),
        logs_dir=str(logs),
    )
    client = TestClient(app, base_url=_BASE_URL)
    yield types.SimpleNamespace(app=app, client=client, cfg=cfg, url_cfg=url_cfg, wa=wa, fake_main=fake_main)
    client.close()


class TestMainLoopAliveProbeWithdrawn:
    # SEV-2221 / SEV-2228 收敛（2026-09-23）后的契约锁：/api/status 不再携带 `main_loop_alive`，
    # 因为那版探针读的是 `main.main_loop_ticks`——main.py 里从未定义、也从未自增，后果是「有一个
    # 永不生效的存活信号」，比「没有该信号」更危险：后续排障会以为停摆已被覆盖。
    #
    # 本类只锁一条**行为不变量**：main 侧没有确凿的轮次证据时，端点不得凭空挂出任何停摆判定。
    # 刻意不按符号名/源码子串设防——src 侧明写了「main.py 补上轮次计数后就重新接线」的正当路径。

    def test_status_omits_key_when_main_exposes_no_tick_counter(self, app_env: types.SimpleNamespace) -> None:
        # 未接线形态（fake main 只有 get_status，没有任何轮次计数）→ 该键必须缺席。
        # 前端按 `=== false` 判定，缺键即「未知 = 不告警」；若实现改成无条件下发，本用例变红。
        assert not hasattr(app_env.fake_main, "main_loop_ticks"), "用例前提：fake main 未接线轮次计数器"
        token = _login(app_env.client)
        resp = app_env.client.get("/api/status", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200, resp.text
        snapshot = cast("dict[str, object]", resp.json())
        assert "main_loop_alive" not in snapshot, f"无证据却下发了停摆判定键: {snapshot}"
        # 撤下停摆探针不得顺手砍掉既有契约：engine_alive 仍是唯一的存活证据、原样透传
        assert snapshot["engine_alive"] is True

    def test_status_omits_key_when_counter_is_bool(self, app_env: types.SimpleNamespace) -> None:
        # 误接线形态（保留原 SEV-2221 用例的洞见）：bool 是 int 子类，`main_loop_ticks = True`
        # 若被当 1 参与「是否增长」比较，判定会恒为「永不增长 → 停摆」，面板永久报红。
        setattr(app_env.fake_main, "main_loop_ticks", True)
        try:
            token = _login(app_env.client)
            resp = app_env.client.get("/api/status", headers={"Authorization": f"Bearer {token}"})
            assert resp.status_code == 200, resp.text
            snapshot = cast("dict[str, object]", resp.json())
            assert "main_loop_alive" not in snapshot, f"bool 计数器被当成轮次证据用: {snapshot}"
        finally:
            # 桩是进程级模块对象，不清掉会污染同会话里后续读 main 的用例
            delattr(app_env.fake_main, "main_loop_ticks")


class TestWriteSideSensitiveParity:
    # MID-2236：写侧敏感判据必须与读侧同源。「键名不敏感、值本身是凭据」的项
    # （推送接口链接 ?key=xxx / 带账密的代理地址）在修复前只有读侧认它是敏感项。

    @pytest.mark.parametrize(
        "value",
        [
            "https://oapi.dingtalk.com/robot/send?access_token=REALSECRET123",
            "http://user:pass@127.0.0.1:7890",
        ],
    )
    def test_blank_write_to_value_shaped_secret_rejected(self, app_env: types.SimpleNamespace, value: str) -> None:
        # 键名刻意取「不敏感」的（is_sensitive_item 判 False），把判定完全压到值形态上：
        # 这样用例失败只可能因为写侧没做值形态判定，而不是键名白名单顺带命中。
        section, key = "录制设置", "自定义推送标题"
        assert is_sensitive_item(section, key) is False, "用例前提：该键名不得命中敏感键名模式"
        assert append_config_line(str(app_env.cfg), section, key, value) is True

        token = _login(app_env.client)
        resp = app_env.client.put(
            "/api/config",
            json={"section": section, "key": key, "value": "   "},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 400, f"值型凭据被空值覆盖未拦住: {resp.text}"
        assert value in app_env.cfg.read_text(encoding="utf-8-sig"), "真实凭据必须原样保留"

    @pytest.mark.parametrize(
        "value",
        [
            "https://oapi.dingtalk.com/robot/send?access_token=REALSECRET123",
            "http://user:pass@127.0.0.1:7890",
        ],
    )
    def test_mask_write_to_value_shaped_secret_rejected(self, app_env: types.SimpleNamespace, value: str) -> None:
        # 掩码分支同理：面板把该项渲染成 '***'，用户原样提交（或脚本直接打接口）
        # 不得把真实凭据覆写成字面掩码 —— 备份副本已按 CR-07 脱敏，无从恢复。
        section, key = "录制设置", "自定义推送标题"
        assert is_sensitive_item(section, key) is False, "用例前提：该键名不得命中敏感键名模式"
        assert append_config_line(str(app_env.cfg), section, key, value) is True

        token = _login(app_env.client)
        resp = app_env.client.put(
            "/api/config",
            json={"section": section, "key": key, "value": SENSITIVE_MASK},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 400, f"值型凭据被掩码覆盖未拦住: {resp.text}"
        assert value in app_env.cfg.read_text(encoding="utf-8-sig")

    def test_read_side_treats_the_same_items_as_sensitive(self, app_env: types.SimpleNamespace) -> None:
        # 一致性锁：同一条目在**读侧**必须已被脱敏——写侧的判据就是从读侧同源来的，
        # 若读侧将来把值形态判定删掉，这条会先红，提示两端一起漂了。
        from src.web_config import read_config_safe

        section, key = "录制设置", "自定义推送标题"
        assert append_config_line(
            str(app_env.cfg), section, key, "https://oapi.dingtalk.com/robot/send?access_token=REALSECRET123"
        )
        safe = read_config_safe(str(app_env.cfg))
        assert safe[section][key] == SENSITIVE_MASK, "读侧未按值形态脱敏（两端判据已分叉）"

    def test_plain_non_secret_value_still_writable(self, app_env: types.SimpleNamespace) -> None:
        # 反向边界：值形态判定不得扩成「URL 都不能清空」或「含 key= 的都不能写」。
        # 无凭据的普通 URL 必须照常可写、可清空，否则这条防线变成功能回归。
        section, key = "录制设置", "自定义推送标题"
        assert append_config_line(str(app_env.cfg), section, key, "https://ntfy.sh/mytopic") is True

        token = _login(app_env.client)
        resp = app_env.client.put(
            "/api/config",
            json={"section": section, "key": key, "value": ""},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200, f"无凭据的普通地址被误伤: {resp.text}"

    def test_write_side_reuses_read_side_predicate(self) -> None:
        # 源码级锁：写侧不得**复制**一份值形态判定（两份实现必然漂移）。
        # 必须直接引用 web_config._looks_like_secret_value。
        src = (Path(__file__).resolve().parent.parent / "src" / "web_api.py").read_text(encoding="utf-8")
        assert "_looks_like_secret_value" in src, "写侧未复用读侧的值形态判据"
        # 必须同时覆盖「新值形态」与「旧值形态」两个方向（后者堵「清空值型凭据」）
        assert "_looks_like_secret_value(value)" in src, "写侧未判新值形态"
        assert "_looks_like_secret_value(old_value)" in src, "写侧未判旧值形态（清空路径漏判）"

    def test_old_value_must_come_from_unmasked_read(self) -> None:
        # 源码级锁（2026-09-22 补）：old_value 一旦取自 read_config_safe，值型凭据拿到的是
        # SENSITIVE_MASK，_looks_like_secret_value('***') 恒为 False —— 整条值形态分支被架空，
        # 端点静默放行。这里锁住「不得用脱敏读」这一根因：从 `old_value = ""` 到敏感判定之间
        # 若再出现 read_config_safe，即为退化。
        src = (Path(__file__).resolve().parent.parent / "src" / "web_api.py").read_text(encoding="utf-8")
        code = "\n".join(ln for ln in src.splitlines() if not ln.strip().startswith("#"))
        # 敏感判定的调用行是这段代码的终点；截取其前的片段做断言，避免命中别处的同名调用
        marker = "_looks_like_secret_value(old_value)"
        assert marker in code, "写侧未判旧值形态（清空路径漏判）"
        segment = code[: code.index(marker)]
        segment = segment[segment.index('old_value = ""') :]
        assert (
            "read_config_safe" not in segment
        ), "old_value 又从脱敏读（read_config_safe）取了：值型凭据会被读成掩码，判定失效"
        assert "configparser.ConfigParser" in segment, "old_value 未从未脱敏的原始配置读取"


class TestTokenExpiryClamp:
    # MID-2234：web_token_expiry 可经 PUT /api/config 写入，且因命中 expiry 例外不受敏感键守卫，
    # 既无上下界也无「不得清空」保护。写成 0 → 所有 /api/* 一律 401 面板自锁；超大值 → 令牌永不
    # 过期且 _tokens 无界增长。

    @pytest.mark.parametrize(
        "raw,expected",
        [
            (0, 60.0),
            (-1, 60.0),
            (1, 60.0),
            (59.9, 60.0),
            (60, 60.0),
            (86400, 86400.0),
            (7 * 86400, float(7 * 86400)),
            (10**9, float(7 * 86400)),
        ],
    )
    def test_clamp_bounds(self, raw: object, expected: float) -> None:
        from src import web_api as wa

        assert wa._clamp_token_expiry(raw) == expected

    @pytest.mark.parametrize("raw", ["", "abc", None, [], {}])
    def test_non_numeric_falls_back_to_default(self, raw: object) -> None:
        # 非数值不得抛异常把登录打成 500；回落默认 86400。
        from src import web_api as wa

        assert wa._clamp_token_expiry(raw) == 86400.0

    def test_nan_falls_back_to_default(self) -> None:
        # NaN 与任何比较都为假：若不显式挡掉，min/max 会把它原样透传（exp 变成 NaN → 永不过期）。
        from src import web_api as wa

        assert wa._clamp_token_expiry(float("nan")) == 86400.0

    def test_login_applies_clamp_end_to_end(self, app_env: types.SimpleNamespace) -> None:
        # 行为锁：把 web_token_expiry 写成 0，登录返回的 expires_in 必须仍为夹取下界，且 token 立即
        # 可用（若按 0 生效，下面这次 /api/status 会 401）。fixture 的 config.ini 不含该键，故补建。
        assert append_config_line(str(app_env.cfg), "Web", "web_token_expiry", "0") is True
        app_env.wa._invalidate_web_cfg_cache()

        resp = app_env.client.post("/api/login", json={"password": "secret123"})
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["expires_in"] == 60.0, f"登录未对 web_token_expiry 做下界夹取: {body}"
        token = body["token"]
        st = app_env.client.get("/api/status", headers={"Authorization": f"Bearer {token}"})
        assert st.status_code == 200, "令牌按 0 秒生效 → 刚签发就 401（面板自锁）"


class TestAuthKeyReauth:
    # MID-2241：`[Web] web_auth_enable` / `web_password` 是「面板信任边界本身」的开关——一次 PUT
    # 就能关掉认证（回环绑定下 SEV-04 不拦）或改口令（连带 _tokens.clear() 踢掉全部在线会话）。
    # 前端 confirm 只挡「手滑点保存」，挡不住脚本、旧版前端、被改过的页面，以及**拿到 bearer 却没
    # 口令**的攻击者，故复验必须在服务端做：认证当前已开启时写这两个键必须携带能过
    # verify_web_password 的 reauth_password，否则 403。
    # [历史注] 本类原锁相反语义（防线只落前端、后端刻意不判定，两条正向用例断言缺字段/错口令也
    # 回 200）；2026-09-23 后端强复验落地后整体翻转为「无复验 / 错复验必须被拒」+ 三条反向边界。

    def _auth_off_env(self, tmp_path: Path, wa: types.ModuleType) -> types.SimpleNamespace:
        # 关闭态（出厂默认）单独造：fixture 的 app_env 是开启态，而「认证关闭时不要求复验」这条
        # 反向边界只有在关闭态下才验得出来。绑定未接线 → _guard_bind_host 回落到配置里的 127.0.0.1。
        from starlette.testclient import TestClient

        cfg = tmp_path / "config_auth_off.ini"
        cfg.write_text(
            "\n".join(
                [
                    "[Web]",
                    "web_host = 127.0.0.1",
                    "web_port = 8000",
                    "web_auth_enable = false",
                    "web_password =",
                    "web_trusted_proxy =",
                ]
            )
            + "\n",
            encoding="utf-8-sig",
        )
        _reset_web_api_state(wa)
        app = wa.create_app(
            config_file=str(cfg),
            url_config_file=str(tmp_path / "url_off.ini"),
            downloads_root=str(tmp_path),
            logs_dir=str(tmp_path),
        )
        return types.SimpleNamespace(cfg=cfg, client=TestClient(app, base_url=_BASE_URL))

    @pytest.mark.parametrize(
        "key,value",
        [
            ("web_password", "atkpass1"),
            ("WEB_PASSWORD", "atkpass1"),
            ("Web_Password", "atkpass1"),
            (" web_password ", "atkpass1"),
            ("web_auth_enable", "false"),
            ("WEB_AUTH_ENABLE", "false"),
        ],
    )
    def test_password_write_without_reauth_is_403(self, app_env: types.SimpleNamespace, key: str, value: str) -> None:
        # 复验守卫本体（tests/test_web_api.py 里几条「带正确口令」的正向用例的配套反向锁）。
        # 键名变体一并参数化：判定用的是 key_norm = key.strip().lower()，大小写/首尾空白不得绕过
        # 守卫——本仓出过 configparser optionxform 与常量大小写不一致导致跳过判定的坑（SEV-04）。
        client = app_env.client
        headers = {"Authorization": f"Bearer {_login(client)}"}
        before = app_env.cfg.read_bytes()
        resp = client.put("/api/config", json={"section": "Web", "key": key, "value": value}, headers=headers)
        assert resp.status_code == 403, f"{key!r} 变体绕过了复验守卫: {resp.text}"
        assert "reauth_password" in resp.json()["detail"], resp.text
        # 403 必须发生在 update_config_line **之前**：配置文件字节一个都不能变
        assert app_env.cfg.read_bytes() == before, f"{key!r} 被拒却仍落了盘"
        # 改口令被拒 ⇒ 不得触发「改密吊销 token」；原口令仍可登录 ⇒ 落盘的仍是旧哈希
        assert client.get("/api/rooms", headers=headers).status_code == 200
        assert client.post("/api/login", json={"password": _PLAIN_PWD}).status_code == 200

    @pytest.mark.parametrize("reauth", ["", "   ", "wrong-password", "SECRET123"])
    def test_wrong_or_blank_reauth_is_403(self, app_env: types.SimpleNamespace, reauth: str) -> None:
        # 只带**正确**口令才算复验：空串/纯空白走「未携带」分支；错口令 → PBKDF2 比签名不过（口令
        # 大小写敏感，SECRET123 必须被拒——归一只发生在键名上，绝不得扩到口令值上）。
        client = app_env.client
        headers = {"Authorization": f"Bearer {_login(client)}"}
        before = app_env.cfg.read_bytes()
        resp = client.put(
            "/api/config",
            json={"section": "Web", "key": "web_password", "value": "atkpass1", "reauth_password": reauth},
            headers=headers,
        )
        assert resp.status_code == 403, f"复验形同虚设（reauth={reauth!r}）: {resp.text}"
        assert app_env.cfg.read_bytes() == before
        assert client.post("/api/login", json={"password": "atkpass1"}).status_code == 401

    def test_correct_reauth_is_what_makes_the_same_payload_pass(self, app_env: types.SimpleNamespace) -> None:
        # 归因锁：载荷与上面几条逐字相同、只多一个正确 reauth_password ⇒ 200。
        # 缺了这条，「403 来自复验守卫」就无法排除「其实是被 CR-08 / SEV-04 / 敏感项守卫挡的」
        # （那三条都在复验之前判定，且都可能在特定取值下命中）。
        client = app_env.client
        token = _login(client)
        headers = {"Authorization": f"Bearer {token}"}
        resp = client.put(
            "/api/config",
            json={"section": "Web", "key": "web_auth_enable", "value": "false", "reauth_password": _PLAIN_PWD},
            headers=headers,
        )
        assert resp.status_code == 200, f"正确复验仍被拒，403 另有来源: {resp.text}"
        assert "web_auth_enable = false" in app_env.cfg.read_text(encoding="utf-8-sig")
        # 认证关掉后 /api/* 立即开放（中间件缓存必须已失效）
        assert client.get("/api/rooms").status_code == 200

    def test_reauth_not_required_while_auth_disabled(self, tmp_path: Path, fake_main: types.ModuleType) -> None:
        # 反向边界①：认证关闭（出厂默认）时不得要求复验——那时面板对任何能访问端口的人全开，
        # bearer 不构成防线，也没有可信的「当前口令」可验，强复验只会把正常收紧配置打死。
        from src import web_api as wa

        env = self._auth_off_env(tmp_path, wa)
        try:
            # 关闭态下先设口令：无旧口令可验，必须放行
            resp = env.client.put("/api/config", json={"section": "Web", "key": "web_password", "value": "first-pass"})
            assert resp.status_code == 200, f"认证关闭时设口令被误拒: {resp.text}"
            # 再开启认证：这是**升级**而非能力降级，同样不复验（CR-08 的「必须同时有口令」已满足）
            resp2 = env.client.put("/api/config", json={"section": "Web", "key": "web_auth_enable", "value": "true"})
            assert resp2.status_code == 200, f"关闭态下开启认证被复验打死: {resp2.text}"
            text = env.cfg.read_text(encoding="utf-8-sig")
            assert "web_auth_enable = true" in text
            assert "first-pass" not in text, "口令必须哈希落盘"
            # 状态翻转后复验立刻生效（证明本条不是「守卫没跑」造成的假绿）。
            # 必须带 bearer：认证已开启时不带令牌的 PUT 会被中间件先 401，那就测不到复验守卫。
            token = env.client.post("/api/login", json={"password": "first-pass"}).json()["token"]
            denied = env.client.put(
                "/api/config",
                json={"section": "Web", "key": "web_auth_enable", "value": "false"},
                headers={"Authorization": f"Bearer {token}"},
            )
            assert denied.status_code == 403, f"开启认证后仍无需复验: {denied.text}"
            assert "web_auth_enable = true" in env.cfg.read_text(encoding="utf-8-sig")
        finally:
            env.client.close()

    def test_other_web_key_is_not_gated(self, app_env: types.SimpleNamespace) -> None:
        # 反向边界②：守卫的键集合恰好是那两项。web_host/web_port/web_allowed_hosts 等
        # 一律不受影响，否则「改个监听地址也要复验」会逼人绕过面板手改 config.ini。
        token = _login(app_env.client)
        resp = app_env.client.put(
            "/api/config",
            json={"section": "Web", "key": "web_host", "value": "localhost"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200, f"非认证键被复验要求误伤: {resp.text}"
        assert "web_host = localhost" in app_env.cfg.read_text(encoding="utf-8-sig")

    def test_frontend_sends_confirm_and_reuses_field_name(self) -> None:
        # 前端半边的源码级锁：确认弹窗与字段名必须同时存在——只断言「有 confirm」会被无关 confirm
        # 蒙混，只断言「有 reauth_password」又无法区分「发送」与「读取」。
        # [历史注 2026-09-23] 原注释写「后端虽不判定，但确认链应完整」；后端强复验落地后该字段是
        # **准入依据**，前端这条从「预留」变成「必须」。
        app_js = (Path(__file__).resolve().parent.parent / "web" / "app.js").read_text(encoding="utf-8")
        assert "body.reauth_password" in app_js, "前端未把复验口令放进请求体"
        assert "confirm(t('config.authChangeConfirm')" in app_js, "前端未在写入认证配置前做二次确认"
        assert "config.authChangeReauth" in app_js, "前端未即时询问当前口令（后端已据此准入）"

    def test_non_auth_key_needs_no_reauth(self, app_env: types.SimpleNamespace) -> None:
        # 反向边界：其余键不得被牵连（普通配置编辑不带 reauth_password 也必须能写）。
        token = _login(app_env.client)
        assert append_config_line(str(app_env.cfg), "录制设置", "输出格式", "ts") is True
        resp = app_env.client.put(
            "/api/config",
            json={"section": "录制设置", "key": "输出格式", "value": "mkv"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200, f"普通配置键被复验要求误伤: {resp.status_code} {resp.text}"
