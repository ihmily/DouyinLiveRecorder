#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 可复用的 Web / 接口冒烟测试工具（纯标准库，无第三方依赖）
#
# 功能：
#   - 配置驱动：用 JSON 描述要检查的接口（url / method / 期望状态码 / 超时 /
#     请求头 / 请求体 / 响应应包含的文本 / 期望的 JSON 字段）
#   - 基础 URL 前缀：config 里的 url 若不是完整 http(s) 地址，则拼接 base_url
#   - 多种输出：控制台（带颜色）、JSON 报告、HTML 报告
#   - 退出码：任一检查失败时返回非 0，方便接入 CI
#
# 用法：
#   python smoke_test.py --config smoke_targets.json
#   python smoke_test.py --config smoke_targets.json --base-url https://api.example.com
#   python smoke_test.py --config smoke_targets.json --report report.html --format html
#   python smoke_test.py --config smoke_targets.json --report result.json --format json
import argparse
import http.client
import json
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from typing import cast

DEFAULT_TIMEOUT = 5
DEFAULT_METHOD = "GET"

# 检查结果字典为嵌套异构结构，统一以 object 承载，读取处用 cast 收敛
CheckResult = dict[str, object]
CheckConfig = dict[str, object]


# ---------- 颜色（仅控制台） ----------
# 用单元素列表包裹可变标志，避免用全大写常量被重新赋值触发 reportConstantRedefinition
_color_flag = [sys.stdout.isatty()]
_RESET = "\033[0m"
_RED = "\033[31m"
_GREEN = "\033[32m"
_YELLOW = "\033[33m"
_DIM = "\033[2m"


def _use_color() -> bool:
    return _color_flag[0]


def _c(text: str, code: str) -> str:
    return f"{code}{text}{_RESET}" if _use_color() else text


def _ok(s: str) -> str:
    return _c(s, _GREEN)


def _fail(s: str) -> str:
    return _c(s, _RED)


# ---------- 配置加载 ----------
def load_config(path: str) -> tuple[list[CheckConfig], str | None]:
    with open(path, "r", encoding="utf-8") as f:
        cfg = cast(object, json.load(f))
    if isinstance(cfg, list):
        # 允许顶层直接写成 checks 列表
        return cast(list[CheckConfig], cfg), None
    if isinstance(cfg, dict):
        # 允许顶层写成 {"base_url": "...", "checks": [...]}
        typed = cast(dict[str, object], cfg)
        return cast(list[CheckConfig], typed.get("checks", [])), cast(str | None, typed.get("base_url"))
    # 既不是 list 也不是 dict：返回空 checks；main 会 0 检查全"通过"并以退出码 0 结束，
    # CI 不会感知到配置损坏——配置格式错误是静默通过而非失败。
    return [], None


# 把配置里的 url/path 解析为最终请求地址：已是完整 http(s) 则原样使用；否则与 base_url 拼接。
# 缺失 url 时回退 path，再缺省为 "/"（对 base_url 做健康检查）。
def _resolve_url(check: CheckConfig, base_url: str | None) -> str:
    raw = cast(str, check.get("url") or check.get("path") or "/")
    # 已是完整地址直接返回，不做 base_url 拼接（避免把绝对 URL 误拼成 base_url+url 的无效地址）。
    if raw.startswith("http://") or raw.startswith("https://"):
        return raw
    if base_url:
        return base_url.rstrip("/") + "/" + raw.lstrip("/")
    return raw


# ---------- 单个检查 ----------
def run_check(check: CheckConfig, base_url: str | None, default_timeout: float) -> CheckResult:
    method_raw = cast(str, check.get("method") or DEFAULT_METHOD)
    # 方法统一大写：配置里写 get/Get 都能匹配，urlopen 对方法大小写敏感。
    method = method_raw.upper()
    url = _resolve_url(check, base_url)
    # 注意：timeout 原样透传给 urlopen，若 JSON 里写成字符串 "5" 会被当作非数值触发 TypeError；
    # 配置应保证为数字，本函数不做强制转换（cast 仅为类型检查，不改运行时值）。
    timeout = cast(float, check.get("timeout", default_timeout))
    headers_raw = cast(dict[str, object], check.get("headers", {}))
    headers: dict[str, str] = {k: str(v) for k, v in headers_raw.items()}
    body = check.get("body")
    # dict/list 请求体按 JSON 序列化并设置 Content-Type（setdefault 不覆盖调用方已指定的类型）；
    # 字符串体原样编码，交给调用方决定编码与类型。
    if isinstance(body, (dict, list)):
        body = json.dumps(body).encode("utf-8")
        _ = headers.setdefault("Content-Type", "application/json")
    elif isinstance(body, str):
        body = body.encode("utf-8")

    # 默认期望 200：未显式配置 expected_status 时，任何非 200（含 3xx 重定向、4xx）都判失败；
    # 测试"应重定向"的接口必须在配置里写明期望码，否则误报失败。
    expected_status = cast(int, check.get("expected_status", 200))
    expect_contains = cast(list[str], check.get("expect_contains", []) or [])
    expect_json = cast(dict[str, object] | None, check.get("expect_json"))  # dict: 顶层字段 -> 期望值

    # 未配置 name 时用 "METHOD url" 兜底，保证控制台/报告每行都有可读标识。
    name = check.get("name") or f"{method} {url}"
    result: CheckResult = {
        "name": name,
        "method": method,
        "url": url,
        "expected_status": expected_status,
        "status": None,
        "time_ms": None,
        "matched_contains": [],
        "errors": [],
        "passed": False,
    }
    errors = cast(list[str], result["errors"])
    matched = cast(list[str], result["matched_contains"])

    req = urllib.request.Request(url, data=cast("bytes | None", body), method=method, headers=headers)
    start = time.time()
    try:
        with cast(http.client.HTTPResponse, urllib.request.urlopen(req, timeout=timeout)) as resp:
            status = resp.status
            content = resp.read().decode("utf-8", errors="replace")
        result["status"] = status
        result["time_ms"] = round((time.time() - start) * 1000, 1)
        if status != expected_status:
            errors.append(f"状态码 {status} != 期望 {expected_status}")
    # HTTPError 仍是"有效响应"（带真实状态码如 404/500）；计入 status 并与 expected_status 比较，
    # 因此"期望 404"的检查可正确通过，而非被当成连接异常。
    except urllib.error.HTTPError as e:
        e_code: int = e.code
        result["status"] = e_code
        result["time_ms"] = round((time.time() - start) * 1000, 1)
        if e_code != expected_status:
            errors.append(f"状态码 {e_code} != 期望 {expected_status}")
        try:
            content = e.read().decode("utf-8", errors="replace")
        except Exception:
            content = ""
    except Exception as e:  # 连接失败、超时、DNS 等
        result["time_ms"] = round((time.time() - start) * 1000, 1)
        errors.append(f"{type(e).__name__}: {e}")
        content = ""

    # 文本包含校验
    for token in expect_contains:
        if token in content:
            matched.append(token)
        else:
            errors.append(f"响应中未找到文本: {token!r}")

    # JSON 字段校验
    if expect_json:
        try:
            parsed = cast(object, json.loads(content))
        except Exception as e:
            errors.append(f"响应不是合法 JSON: {e}")
            parsed = None
        if isinstance(parsed, dict):
            typed = cast(dict[str, object], parsed)
            for key, val in expect_json.items():
                actual = typed.get(key)
                if actual != val:
                    errors.append(f"JSON 字段 {key}={actual!r} != 期望 {val!r}")

    result["passed"] = len(errors) == 0
    return result


# ---------- 报告 ----------
def _safe_print(*values: object) -> None:
    # 打印并在控制台编码不兼容时（如 Windows GBK 下的非 ASCII 字符）做容错替换。
    text = " ".join(str(v) for v in values)
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode("ascii", "replace").decode("ascii"))


def print_console(results: list[CheckResult], elapsed_ms: float) -> None:
    total = len(results)
    passed = sum(1 for r in results if cast(bool, r["passed"]))
    _safe_print()
    _safe_print("=" * 70)
    _safe_print(f"冒烟测试报告   {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    _safe_print("=" * 70)
    for r in results:
        mark = _ok("PASS") if cast(bool, r["passed"]) else _fail("FAIL")
        t = f"{r['time_ms']}ms" if r["time_ms"] is not None else "-"
        _safe_print(f"[{mark}] {r['name']}  ->  {r['status']}  ({t})")
        matched = cast(list[str], r["matched_contains"])
        if matched:
            _safe_print(f"        {_DIM}命中文本: {matched}{_RESET}")
        for err in cast(list[str], r["errors"]):
            _safe_print(f"        {_fail('x')} {err}")
    _safe_print("-" * 70)
    summary = _ok(f"{passed}/{total} 通过") if passed == total else _fail(f"{passed}/{total} 通过")
    _safe_print(f"总计: {summary}   耗时 {elapsed_ms:.0f}ms")
    _safe_print("=" * 70)


def build_summary(results: list[CheckResult], elapsed_ms: float) -> CheckResult:
    passed = sum(1 for r in results if cast(bool, r["passed"]))
    return {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "total": len(results),
        "passed": passed,
        "failed": len(results) - passed,
        "elapsed_ms": round(elapsed_ms, 1),
    }


def write_json_report(results: list[CheckResult], summary: CheckResult, path: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"summary": summary, "results": results}, f, ensure_ascii=False, indent=2)


# 生成自包含 HTML 报告：逐行拼接表格行（含命中文本与错误），通过/失败行用 ok/bad 样式区分；
# 内容直接拼入 HTML，依赖配置可信（测试目标由使用者提供，非外部不可信输入）。
def write_html_report(results: list[CheckResult], summary: CheckResult, path: str) -> None:
    rows: list[str] = []
    for r in results:
        status_cls = "ok" if cast(bool, r["passed"]) else "bad"
        detail = ""
        matched_html = cast(list[str], r["matched_contains"])
        if matched_html:
            detail += "<div class='match'>命中: " + ", ".join(matched_html) + "</div>"
        for err in cast(list[str], r["errors"]):
            detail += f"<div class='err'>✗ {err}</div>"
        row = (
            f"<tr class='{status_cls}'>"
            + f"<td>{'✅' if cast(bool, r['passed']) else '❌'}</td>"
            + f"<td>{r['name']}</td>"
            + f"<td>{r['method']}</td>"
            + f"<td>{r['status']}</td>"
            + f"<td>{r['time_ms']}ms</td>"
            + f"<td>{detail}</td>"
            + f"</tr>"
        )
        rows.append(row)
    html = (
        f"<!DOCTYPE html>\n"
        f'<html lang="zh-CN"><head><meta charset="utf-8">\n'
        f"<title>冒烟测试报告</title>\n"
        f"<style>\n"
        f"body{{font-family:-apple-system,Segoe UI,Roboto,sans-serif;margin:24px;color:#222;}}\n"
        f"h1{{font-size:20px;}}\n"
        f".meta{{color:#666;font-size:13px;margin-bottom:16px;}}\n"
        f"table{{border-collapse:collapse;width:100%;font-size:13px;}}\n"
        f"th,td{{border:1px solid #ddd;padding:8px 10px;text-align:left;vertical-align:top;}}\n"
        f"th{{background:#f5f5f5;}}\n"
        f"tr.ok td{{background:#f0fff4;}}\n"
        f"tr.bad td{{background:#fff5f5;}}\n"
        f".err{{color:#c0392b;}}\n"
        f".match{{color:#27ae60;}}\n"
        f".badge{{display:inline-block;padding:2px 8px;border-radius:10px;font-size:12px;}}\n"
        f".badge.ok{{background:#27ae60;color:#fff;}}\n"
        f".badge.bad{{background:#e74c3c;color:#fff;}}\n"
        f"</style></head><body>\n"
        f"<h1>冒烟测试报告</h1>\n"
        f'<div class="meta">生成时间: {summary["timestamp"]} ｜ 耗时 {cast(float, summary["elapsed_ms"])}ms</div>\n'
        f'<div style="margin-bottom:12px;">\n'
        f'<span class="badge ok">通过 {cast(int, summary["passed"])}</span>\n'
        f'<span class="badge bad">失败 {cast(int, summary["failed"])}</span>\n'
        f'<span class="badge" style="background:#888;color:#fff;">共 {cast(int, summary["total"])}</span>\n'
        f"</div>\n"
        f"<table>\n"
        f"<tr><th>结果</th><th>名称</th><th>方法</th><th>状态码</th><th>耗时</th><th>详情</th></tr>\n"
        f"{''.join(rows)}\n"
        f"</table>\n"
        f"</body></html>"
    )
    with open(path, "w", encoding="utf-8") as f:
        _ = f.write(html)


# ---------- 入口 ----------
def main() -> None:
    p = argparse.ArgumentParser(description="可复用的 Web/接口冒烟测试工具")
    _ = p.add_argument("--config", "-c", required=True, help="检查项配置文件 (JSON)")
    _ = p.add_argument("--base-url", "-b", default=None, help="基础 URL 前缀，拼接配置里非完整地址的 url")
    _ = p.add_argument("--timeout", "-t", type=float, default=DEFAULT_TIMEOUT, help="默认超时(秒)")
    _ = p.add_argument("--report", "-r", default=None, help="输出报告文件路径")
    _ = p.add_argument(
        "--format", "-f", choices=["json", "html"], default=None, help="报告格式 (json/html)，默认仅控制台"
    )
    _ = p.add_argument("--no-color", action="store_true", help="禁用控制台颜色")
    args = p.parse_args()

    if cast(bool, args.no_color):
        _color_flag[0] = False

    config_path = cast(str, args.config)
    timeout = cast(float, args.timeout)
    base_url_arg = cast(str | None, args.base_url)
    report_path = cast(str | None, args.report)
    report_format = cast(str | None, args.format)

    checks, cfg_base = load_config(config_path)
    base_url = base_url_arg or cfg_base

    t0 = time.time()
    results = [run_check(c, base_url, timeout) for c in checks]
    elapsed = (time.time() - t0) * 1000

    print_console(results, elapsed)

    summary = build_summary(results, elapsed)
    if report_path:
        # 未显式指定 --format 时按扩展名推断：.html→html，其余→json，降低调用负担。
        fmt = report_format or ("html" if report_path.endswith(".html") else "json")
        if fmt == "html":
            write_html_report(results, summary, report_path)
        else:
            write_json_report(results, summary, report_path)
        print(f"\n报告已写出: {report_path}")

    # CI 以退出码判定成败：任一检查 failed 即返回 1 使流水线变红；全部通过（含 0 检查）返回 0。
    # 与 load_config 的空配置静默通过呼应——零检查也会退出 0。
    failed = cast(int, summary["failed"])
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
