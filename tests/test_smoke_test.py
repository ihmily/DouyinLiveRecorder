# scripts/smoke_test.py 的 **HTML 报告输出面**回归用例（M-97，2026-10-21 审查）。
#
# 为什么单独成文件：tests/test_scripts_error_paths.py 锁的是 load_config 的形态契约与退出码
# （rc=0/1/2 的分档，消费方 scripts/_ci_web_smoke.sh 与 .github/actions/retry 的 fail_fast_codes
# 依赖它），tests/test_build_exe.py::MIN-2260 组锁的是「0 断言不算通过」——两条都不覆盖
# write_html_report。而 HTML 报告正是本工具**唯一被浏览器打开**的出口（CI 附件），
# 也是本文件唯一的判据对象：动态片段必须在拼接前过 html.escape。
#
# 威胁模型（写成注释而不是只留在审查记录里，避免后来者以为「配置可信」这条假设还在）：
#   errors 列表里装的不只是本地文案——`响应不是合法 JSON: {e}`、`JSON 字段 k={actual!r}`
#   与未命中的 expect_contains token 原文都直接来自被探测服务的响应体。报告被打开时，
#   远端返回的内容就成了报告页里的标记/脚本。故一律 escape，不做「目标可信」的推断。
#
# 全部离线：网络层按 AGENTS.md 的 shim 口径替换 build 目标模块命名空间里的 urllib 引用，
# 不动 stdlib 本体；产物一律写 tmp_path。

from __future__ import annotations

import importlib.util
import json
import types
from pathlib import Path
from typing import Any, cast

import pytest

ROOT = Path(__file__).resolve().parent.parent


def _load_smoke_test() -> Any:
    # scripts/ 不在包路径内，沿用仓内惯例（test_agent_hook_guard.py / test_build_exe.py）显式按路径加载。
    spec = importlib.util.spec_from_file_location("_smoke_report_probe", ROOT / "scripts" / "smoke_test.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


smoke_test = _load_smoke_test()

# 注入串：三种形态分别覆盖「开新标签」「带属性」「带引号闭合」，任何一种漏 escape 都会把
# 后续内容变成标记——断言按整串原文比对，不按 `<` 计数（后者会被 escape 后残留的 &lt; 混淆）。
_INJECT_TAG = "<script>alert(document.domain)</script>"
_INJECT_ATTR = '"><img src=x onerror=alert(1)>'
_INJECT_PLAIN = "a<b & c>d"


def _result(**overrides: Any) -> dict[str, object]:
    base: dict[str, object] = {
        "name": "GET /health",
        "method": "GET",
        "url": "http://127.0.0.1:8000/health",
        "expected_status": 200,
        "status": 200,
        "time_ms": 12.5,
        "matched_contains": [],
        "errors": [],
        "passed": True,
    }
    base.update(overrides)
    return base


def _render(tmp_path: Path, results: list[dict[str, object]]) -> str:
    report = tmp_path / "report.html"
    summary = smoke_test.build_summary(cast(Any, results), 34.0)
    smoke_test.write_html_report(cast(Any, results), cast(Any, summary), str(report))
    return report.read_text(encoding="utf-8")


@pytest.mark.parametrize("payload", [_INJECT_TAG, _INJECT_ATTR, _INJECT_PLAIN])
def test_html_report_escapes_every_dynamic_fragment(tmp_path: Path, payload: str) -> None:
    # 逐字段投毒：name / errors（异常文本位）/ matched_contains（响应文本位）都必须转义。
    results = [
        _result(name=payload, passed=False, errors=[f"连接失败: ConnectionRefusedError: {payload}"]),
        _result(matched_contains=[payload], errors=[]),
    ]
    text = _render(tmp_path, results)
    assert payload not in text, f"动态片段原样进了 HTML：{payload!r}"
    # 只看「会不会被解析成标记」：escape 后 `<`/`>` 都不再是裸的，`=`/`(` 这类无害字符保持原样，
    # 故这里断言的是起始尖括号，不是整条属性串。
    assert "<script>" not in text and "<img" not in text
    assert "&lt;script&gt;" in text or "&lt;" in text
    # 结构不被 escape 破坏：两行结果 + 一行表头，且 ok/bad 两个样式仍在
    assert text.count("<tr ") + text.count("<tr>") == 3, text
    assert "class='bad'" in text and "class='ok'" in text


def test_html_report_escapes_response_derived_error_end_to_end(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # 端到端：注入串来自**响应体**（expect_json 的实际值位），而不是配置文件——
    # 这正是 M-97 里「依赖配置可信」这条假设失效的那一类内容，必须走真实 run_check 通路取证。
    body = json.dumps({"status": _INJECT_TAG}).encode("utf-8")

    class _FakeResponse:
        status = 200

        def __init__(self, payload: bytes) -> None:
            self._payload = payload

        def read(self) -> bytes:
            return self._payload

        def __enter__(self) -> "_FakeResponse":
            return self

        def __exit__(self, *exc: Any) -> None:
            return None

    request_shim = types.SimpleNamespace(**vars(smoke_test.urllib.request))
    request_shim.urlopen = lambda req, timeout=None: _FakeResponse(body)
    urllib_shim = types.SimpleNamespace(request=request_shim, error=smoke_test.urllib.error)
    monkeypatch.setattr(smoke_test, "urllib", urllib_shim)

    check = cast(
        dict[str, object], {"name": "GET /api", "url": "http://127.0.0.1/api", "expect_json": {"status": "ok"}}
    )
    result = smoke_test.run_check(cast(Any, check), None, 5.0)
    errors = cast(list[str], result["errors"])
    assert errors and _INJECT_TAG in errors[0], "响应派生内容没进 errors，本用例的前提（响应可控）已不成立"
    text = _render(tmp_path, [result])
    assert _INJECT_TAG not in text, "响应派生内容未转义即拼进 HTML（M-97 回归）"
    assert "&lt;script&gt;alert(document.domain)&lt;/script&gt;" in text


def test_html_report_keeps_clean_values_readable(tmp_path: Path) -> None:
    # 放行面（escape 不是「把一切都打码」）：普通名称/状态码/耗时照常出现在报告里，
    # 否则报告作为 CI 附件失去可读性，使用者会转向「关掉转义」这种更坏的做法。
    results = [_result(name="健康检查 & 面板", status=204)]
    text = _render(tmp_path, results)
    assert "健康检查 &amp; 面板" in text
    assert ">204<" in text
    assert "12.5ms" in text
    assert "✅" in text
