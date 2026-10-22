# src/web_config.py / src/web_api.py「敏感配置不得被空值覆盖」的回归锁（MID-69 补，2026-09-21）。
#
# 范围刻意收窄：MID-69 点名的三个符号里，_looks_like_secret_value 与 _validate_room_url_target
# 已由 tests/test_web_config_secret_mask.py 用**真实函数**的表驱动用例逐条钉死（CR-08/09/10 批次），
# 本文件不再复制那两张表——出现第二份事实源后，改实现的人只会更新其中一处。
# 这里只补当时**零引用**的那一条：敏感键被空值覆盖的后端守卫（web_api.py 的
# `if is_sensitive_item(section, key) and not value.strip(): raise HTTPException(400, ...)`）。
#
# 为什么必须单独钉：面板对敏感项回显的是 '***' 掩码，前端只挡「原样提交 ***」这一种形态，
# 用户全选删空后提交 '' 既 ≠ '***' 也 ≠ 旧值，于是真实 cookie/token 被空串静默覆盖；
# 而 backup_config 副本按 CR-07 同样脱敏，**无从恢复**。这条路径此前只在
# tests/frontend/test_quality_ui.mjs 里以「前端桩把 400 文案渲染成 toast」的形式出现，
# 后端裁决本身没有 Python 用例——即删掉那行 raise 也不会有任何测试变红。
#
# 用例一律走真实 PUT /api/config（TestClient），判定函数是生产侧的 is_sensitive_item，
# 测试内不重新实现任何脱敏/判定逻辑。
#
# 掩码侧的对称防线（此前记为「已知残留」，已于同日 MID-37 残留修复关闭）：提交 value='***'
# 现在也被后端拒成 400（src/web_api.py 的 `elif value.strip() == SENSITIVE_MASK`），由
# tests/test_web_api.py::TestSensitiveValueBlankRejected::test_mask_sensitive_value_rejected 锁定；
# 本文件只负责「空值覆盖」那半边，掩码那半边不在此重述以免形成第二份事实源。

import sys
import threading
import types
from collections.abc import Generator
from pathlib import Path

import pytest
from starlette.testclient import TestClient

_BASE_URL = "http://127.0.0.1:8000"
# 与 src/web_api.py 里 raise HTTPException(400, ...) 的原文逐字一致：文案是契约的一部分，
# 面板把它当 detail 直接 toast 给用户（前端用例同样按子串断言），改一个字两处都会红。
_BLANK_SENSITIVE_DETAIL = "敏感配置项不得清空：如需移除请显式填写占位值并手工编辑 config.ini"


@pytest.fixture()
def fake_main() -> Generator[types.ModuleType, None, None]:
    # web_api 的处理函数内部 `import main as _main` 取 file_update_lock，注入轻量假模块
    # 避免导入真实 main.py 触发 FFmpeg/Node 检查等重副作用（与 tests/test_web_api.py 同源口径）。
    fake = types.ModuleType("main")
    # types.ModuleType 不接受任意属性赋值，一律经 setattr 注入替身符号
    setattr(fake, "file_update_lock", threading.RLock())
    setattr(fake, "running_list", [])
    setattr(fake, "record_state_lock", threading.Lock())
    setattr(fake, "max_request_lock", threading.Lock())
    setattr(fake, "recording", set())
    setattr(fake, "recording_enabled", False)
    setattr(fake, "text_encoding", "utf-8-sig")
    setattr(fake, "url_config_file", "")
    setattr(fake, "ini_URL_content", "")
    previous = sys.modules.get("main")
    sys.modules["main"] = fake
    try:
        yield fake
    finally:
        if previous is not None:
            sys.modules["main"] = previous
        else:
            sys.modules.pop("main", None)


@pytest.fixture()
def client(tmp_path: Path, fake_main: types.ModuleType) -> Generator[TestClient, None, None]:
    # 每个用例一份独立 config.ini：断言「未被覆盖」时必须看到写入前的原文。
    from src import web_api as wa

    cfg = tmp_path / "config.ini"
    cfg.write_text(
        "\n".join(
            [
                "[Web]",
                "web_host = 127.0.0.1",
                "web_port = 8000",
                "web_auth_enable = false",
                "web_password = ",
                "",
                "[推送配置]",
                "tgapi令牌 = REAL_TOKEN_MUST_SURVIVE",
                "pushplus推送token = REAL_PUSH_TOKEN",
                "钉钉推送接口链接 = https://oapi.dingtalk.com/robot/send?access_token=REAL_DING",
                "推送开关 = 是",
                "",
                # M-61（2026-10-21）把「推送配置」整节纳入敏感节后，反向用例需要一个
                # 真正不敏感的节来证明守卫没有扩大到普通键。
                "[录制设置]",
                "是否跳过代理检测(是/否) = 是",
                "",
            ]
        ),
        encoding="utf-8-sig",
    )
    # 中间件按每请求读配置缓存（MID-34），逐个用例清干净，避免串到本文件其余用例
    wa._invalidate_web_cfg_cache()
    with wa._tokens_lock:
        wa._tokens.clear()

    app = wa.create_app(
        config_file=str(cfg),
        url_config_file=str(tmp_path / "URL_config.ini"),
        downloads_root=str(tmp_path / "downloads"),
        logs_dir=str(tmp_path / "logs"),
    )
    # base_url 必须是 loopback：MID-36 之后 Host 头参与同源判定，testclient 默认 Host 会被拒
    test_client = TestClient(app, base_url=_BASE_URL)
    try:
        yield test_client
    finally:
        test_client.close()
        wa._invalidate_web_cfg_cache()


# ── 真实判定函数侧：确认这些键在生产侧确实算「敏感」 ──────────────────────────
@pytest.mark.parametrize(
    ("section", "key"),
    [
        ("推送配置", "tgapi令牌"),
        ("推送配置", "pushplus推送token"),
        ("推送配置", "钉钉推送接口链接"),
        ("Web", "web_password"),
    ],
)
def test_guarded_keys_are_sensitive_in_production(section: str, key: str) -> None:
    # 若某键不再被判成敏感，下面的 400 用例会因「前提失效」而失去意义，故先钉判定本身
    from src.web_config import is_sensitive_item

    assert is_sensitive_item(section, key) is True


def test_non_sensitive_key_blank_value_is_allowed(client: TestClient) -> None:
    # 反向用例：守卫不得扩大到普通键——否则用户没法清空这类常规开关项。
    # 键必须真实存在于 config.ini，否则命中处理函数的 404「未找到对应的配置项」分支。
    resp = client.put("/api/config", json={"section": "录制设置", "key": "是否跳过代理检测(是/否)", "value": ""})
    assert resp.status_code == 200, resp.text


class TestBlankSensitiveValueRejected:
    @pytest.mark.parametrize(
        ("section", "key", "value", "case"),
        [
            ("推送配置", "tgapi令牌", "", "empty"),
            ("推送配置", "pushplus推送token", "   ", "spaces-only"),
            # 键名带首尾空白：入口先 strip 再判定（C-1），不得靠空白绕过
            ("推送配置", "  tgapi令牌  ", "", "padded-key"),
            # 大小写变体：configparser 的 option 本就大小写不敏感（SEV-04 同口径）
            ("推送配置", "TGAPI令牌", "", "uppercase-key"),
        ],
    )
    def test_400_wording_and_original_value_kept(
        self, client: TestClient, tmp_path: Path, section: str, key: str, value: str, case: str
    ) -> None:
        resp = client.put("/api/config", json={"section": section, "key": key, "value": value})
        assert resp.status_code == 400, f"{case}: 期望 400，实际 {resp.status_code} {resp.text}"
        # 文案是给用户看的：必须是「怎么办」而不是泛泛的校验失败
        assert resp.json()["detail"] == _BLANK_SENSITIVE_DETAIL, case
        # 真正的不变量：**没写盘**。空串静默覆盖后无从恢复（备份副本同样脱敏）
        text = (tmp_path / "config.ini").read_text(encoding="utf-8-sig")
        assert "REAL_TOKEN_MUST_SURVIVE" in text, f"{case}: 真实凭据被空值覆盖"
        assert "REAL_PUSH_TOKEN" in text, f"{case}: 真实凭据被空值覆盖"

    def test_non_blank_value_still_writable(self, client: TestClient, tmp_path: Path) -> None:
        # 守卫不得变成「敏感键只读」：正常改值必须仍然可写，否则面板彻底没法配凭据
        resp = client.put("/api/config", json={"section": "推送配置", "key": "tgapi令牌", "value": "NEW_TOKEN_123"})
        assert resp.status_code == 200, resp.text
        text = (tmp_path / "config.ini").read_text(encoding="utf-8-sig")
        assert "NEW_TOKEN_123" in text and "REAL_TOKEN_MUST_SURVIVE" not in text
