#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 可复用的 Web / 接口冒烟测试工具（纯标准库，无第三方依赖）
#
# 功能：
#   - 配置驱动：用 JSON 描述要检查的接口（url / method / 期望状态码 / 超时 /
#     请求头 / 请求体 / 响应应包含的文本 / 期望的 JSON 字段）
#   - 基础 URL 前缀：config 里的 url 若不是完整 http(s) 地址，则拼接 base_url
#   - 多种输出：控制台（带颜色）、JSON 报告、HTML 报告
#   - 退出码：0 = 已执行的检查全通过；1 = 至少一条失败；2 = 配置读不出/格式非法/一条断言都没有
#     **0 断言不等于通过**：消费方 scripts/_ci_web_smoke.sh 原样透传本退出码，而 .github/actions/retry
#     对任何非 0 都按可重试失败处理，故「2（配置问题）」必须与「1（接口不符合预期）」分得开，
#     否则配置写坏会被读成面板故障，白跑一轮起面板 + 重试退避。
#     2 的覆盖面是**任意**形态畸形：checks 不是 array、checks 元素不是 object、headers/expect_json
#     不是 object、expect_contains 元素不是 string、base_url 类型错，全部在 load_config 前置拒绝，
#     绝不允许「先打了几个请求才第 N 条炸」的半执行状态（旧形态抛 AttributeError → rc=1 崩溃栈）。
#     回归锁：tests/test_scripts_error_paths.py::TestSmokeConfigMalformed。
#
# 用法：
#   python smoke_test.py --config smoke_targets.json
#   python smoke_test.py --config smoke_targets.json --base-url https://api.example.com
#   python smoke_test.py --config smoke_targets.json --report report.html --format html
#   python smoke_test.py --config smoke_targets.json --report result.json --format json
import argparse
import html
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
# 响应体读取上限（字节）：冒烟对象是本项目自己的面板/健康端点，正常响应远小于该值；上限只为挡住
# 「配置被指到不受控目标 / 跟随后的重定向返回超大正文」时把整个响应读进内存（resp.read() 原先无界）。
# 取值与 src/async_http.py 的 _MAX_RESPONSE_BYTES 同值不同源——本脚本是零依赖
# 单文件，不 import src/。
_SMOKE_BODY_LIMIT = 8 * 1024 * 1024

# 检查结果字典为嵌套异构结构，统一以 object 承载，读取处用 cast 收敛
CheckResult = dict[str, object]
CheckConfig = dict[str, object]


# ---------- 颜色（仅控制台） ----------
# 用单元素列表包裹可变标志，避免用全大写常量被重新赋值触发 reportConstantRedefinition
_color_flag = [sys.stdout.isatty()]
_RESET = "\033[0m"
_RED = "\033[31m"
_GREEN = "\033[32m"
_DIM = "\033[2m"


def _use_color() -> bool:
    return _color_flag[0]


def _c(text: str, code: str) -> str:
    return f"{code}{text}{_RESET}" if _use_color() else text


def _ok(s: str) -> str:
    return _c(s, _GREEN)


def _fail(s: str) -> str:
    return _c(s, _RED)


# 不跟随重定向的 handler：urlopen 默认自动跟随 3xx，
# 使「期望 301/302」的断言永远拿不到 3xx 状态码。redirect_request 返回 None 即
# 中止跟随，3xx 会以 urllib.error.HTTPError 抛出（带真实 code），从而可被断言。
# 只在「期望 3xx」时挂上（见 run_check）：默认仍跟随，不破坏依赖短链跳转的既有检查。
class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        return None


# ---------- 配置加载 ----------
# 配置形状校验表：键 -> (允许的 JSON 类型, 报错里给出的期望形状示例)。
# 为什么只列这三项：run_check 对它们**按形状遍历**（headers / expect_json 调 .items()、
# expect_contains 直接迭代），形态写错就是 AttributeError 崩栈（rc=1）或「按字符迭代字符串」
# 的静默误判；而 timeout / expected_status 这类标量原样透传给 urlopen/比较，本文件刻意
# 声明「配置应保证为数字，不做强制转换」（见 run_check 内注释），不在这里偷偷改口径。
_SHAPE_REQUIREMENTS: tuple[tuple[str, tuple[type, ...], str], ...] = (
    ("headers", (dict,), 'object，如 {"Referer": "https://x/"}'),
    ("expect_json", (dict,), 'object，如 {"status": "ok"}'),
    ("expect_contains", (list,), 'array，如 ["欢迎", "在线"]'),
)


def _json_type(value: object) -> str:
    # 报错文案用 JSON 术语而不是 Python 类名：配置文件是 JSON，作者脑子里的形状词是
    # object/array/string，用 dict/list/str 反而要多做一次心智翻译。bool 必须先于 int 判
    # （bool 是 int 的子类），None 单列（isinstance(None, ...) 全 False 会退化成 NoneType）。
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, str):
        return "string"
    if isinstance(value, dict):
        return "object"
    if isinstance(value, list):
        return "array"
    if isinstance(value, (int, float)):
        return "number"
    return type(value).__name__


def _validate_check_item(item: object, index: int, path: str) -> CheckConfig:
    # 单条检查的形态校验：非 object 直接拒绝（旧形态会让 run_check 拿到 str/number，
    # 在 .get() 上抛 AttributeError 崩栈 → rc=1，被消费方读成「接口故障」）。
    if not isinstance(item, dict):
        raise ValueError(
            f"冒烟配置 checks[{index}] 是 {_json_type(item)}，每条检查必须是 JSON object（键值对）: {path}"
        )
    typed = cast(dict[str, object], item)
    # 定位信息优先用配置作者自己写的 name，退化到 path/url，再退化到数组下标：
    # 「第 3 条的 headers 写成了字符串」必须一眼能定位，不能只说「类型不对」。
    label = typed.get("name") or typed.get("path") or typed.get("url") or f"checks[{index}]"
    for key, allowed, expect_shape in _SHAPE_REQUIREMENTS:
        if key not in typed:
            continue
        value = typed[key]
        # 显式 null 与「不写该键」一律放行：三个键在 run_check 侧的读取都已归一到「空即跳过」
        # （headers 走 `or {}`、expect_contains 走 `or []`、expect_json 走 `if expect_json:`），
        # 拒绝 null 会让原本合法的配置突然变红，属行为回归而不是收口。
        if value is None:
            continue
        if not isinstance(value, allowed):
            raise ValueError(f"冒烟配置 {label} 的 {key!r} 是 {_json_type(value)}，期望 {expect_shape}: {path}")
    # 容器类型对上**不等于**元素类型对上：run_check 对 expect_contains 是 `token in content`，
    # 元素写成数字/对象会抛 TypeError 并穿透 main()（那里只接 OSError/ValueError）→ rc=1 崩溃栈，
    # 被消费方读成「面板接口挂了」。故属「配置畸形」：与上面三条同点、同码，一条请求都不发。
    # headers 不必同检：run_check 侧对值统一 `str(v)`，数字/布尔值会被转成字符串头，不崩。
    contains = typed.get("expect_contains")
    if isinstance(contains, list):
        for idx, token in enumerate(cast(list[object], contains)):
            if not isinstance(token, str):
                raise ValueError(
                    f"冒烟配置 {label} 的 'expect_contains[{idx}]' 是 {_json_type(token)}，"
                    f'期望 array 的元素必须是 JSON string（如 {{"expect_contains": ["欢迎", "在线"]}}）: {path}'
                )
    # expected_status 标量畸形（如写成 string "200" 或 null）必须前置挡住：run_check 里
    # `300 <= expected_status < 400` 的重定向开关判定在 try 之外，TypeError 会穿透 main() 的
    # except (OSError, ValueError) → rc=1 崩溃栈，被消费方读成「面板接口挂了」——与上面
    # expect_contains 元素检同族。仍不做强制转换（见 _SHAPE_REQUIREMENTS
    # 处「标量原样透传」的口径说明），只把畸形挡在发请求之前。bool 先拒（bool 是 int 子类，
    # true/false 当状态码没有语义）。timeout 不必同检：它在 run_check 的 try 内被 urlopen
    # 消费，TypeError 落进单条 errors，不构成崩溃路径。
    if "expected_status" in typed:
        raw_expected = typed["expected_status"]
        if isinstance(raw_expected, bool) or not isinstance(raw_expected, (int, float)):
            raise ValueError(
                f"冒烟配置 {label} 的 'expected_status' 是 {_json_type(raw_expected)}，"
                f'期望 JSON number（如 {{"expected_status": 200}}）: {path}'
            )
    return typed


def load_config(path: str) -> tuple[list[CheckConfig], str | None]:
    # 编码用 utf-8-sig：配置若带 BOM（记事本等保存产物），utf-8 读取会把 BOM 当首字符并让
    # json.load 抛 JSONDecodeError，排障时很难想到是 BOM；utf-8-sig 对无 BOM 文件行为一致。
    #
    # 本函数是配置形态的**唯一**校验点：所有畸形一律在这里抛 ValueError，由 main() 的
    # `except (OSError, ValueError)` 转成退出码 2。必须前置挡住而非留给 run_check 运行时炸：
    # ① 崩栈是 rc=1，消费方会按可重试失败处理并误判成面板故障；② 校验晚于发请求会留下
    # 「前几条已打网络、第 N 条才崩」的半执行状态，报告工件与结论都不自洽。
    with open(path, "r", encoding="utf-8-sig") as f:
        cfg = cast(object, json.load(f))
    if isinstance(cfg, list):
        # 允许顶层直接写成 checks 列表（该形态没有 base_url 位，返回 None 由命令行补）
        items = cast(list[object], cfg)
        return [_validate_check_item(item, i, path) for i, item in enumerate(items)], None
    if isinstance(cfg, dict):
        # 允许顶层写成 {"base_url": "...", "checks": [...]}
        # 原写法 typed.get("checks", []) 把「键名拼错」（check / targets / 少引号）
        # 与「checks 被清空」都变成合法的 0 检查，配合 main() 的「0 失败即退 0」，CI 会在
        # **一条断言都没执行**时报成功。故此处要求键必须存在（缺键即 ValueError → 退 2）。
        typed = cast(dict[str, object], cfg)
        if "checks" not in typed:
            raise ValueError(f'冒烟配置缺少 "checks" 键（拼错或漏写都会被当成 0 检查）: {path}')
        # ②：checks 写成 object/string 时，`for c in checks` 迭代的是键名或字符，
        # 每条都是 str → run_check 立刻 AttributeError（rc=1）。这里按期望形态收紧。
        raw_checks = typed["checks"]
        if not isinstance(raw_checks, list):
            raise ValueError(
                f'冒烟配置的 "checks" 是 {_json_type(raw_checks)}，'
                f'期望 JSON array（如 {{"checks": [{{"path": "/"}}]}}）: {path}'
            )
        items = cast(list[object], raw_checks)
        # base_url 同族缺陷：非 str 时 _resolve_url 的 base_url.rstrip 直接 AttributeError。
        cfg_base = typed.get("base_url")
        if cfg_base is not None and not isinstance(cfg_base, str):
            raise ValueError(
                f'冒烟配置的 "base_url" 是 {_json_type(cfg_base)}，期望 JSON string（如 "http://127.0.0.1:8000"）: '
                f"{path}"
            )
        return [_validate_check_item(item, i, path) for i, item in enumerate(items)], cast("str | None", cfg_base)
    # 既不是 list 也不是 dict：配置已损坏，必须让 CI 感知。原实现返回空 checks，
    # main 会 0 检查全"通过"并以退出码 0 结束——门禁形同虚设。
    raise ValueError(f"冒烟配置格式非法（顶层须为 list 或 {{'checks': [...]}}）: {path}")


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
# 单条检查的入口：发一次请求，再按配置做状态码 / 文本包含 / JSON 字段三类断言。
def run_check(check: CheckConfig, base_url: str | None, default_timeout: float) -> CheckResult:
    # 重定向策略按**期望码**二选一（机制与理由见 _NoRedirectHandler 的类注释）：
    # 期望 3xx 才换用不跟随重定向的 opener，其余保持 urlopen 默认的自动跟随。
    _no_redirect_opener = urllib.request.build_opener(_NoRedirectHandler)
    method_raw = cast(str, check.get("method") or DEFAULT_METHOD)
    # 方法统一大写：配置里写 get/Get 都能匹配，urlopen 对方法大小写敏感。
    method = method_raw.upper()
    url = _resolve_url(check, base_url)
    # 期望状态码非 3xx 时保持 urlopen 默认自动跟随；期望 3xx 才换不跟随的 opener。
    # timeout 原样透传给 urlopen，配置应保证为数字（cast 仅为类型检查，不改运行时值）。
    timeout = cast(float, check.get("timeout", default_timeout))
    # ② 配套：load_config 已保证 headers 存在时必为 object，且刻意放行显式 null（与不写等价）。
    # 此处必须用 `or {}` 而不是只靠默认值 —— dict.get 的默认值只在**键缺失**时生效，键在而值为
    # null 时返回 None，`None.items()` 又是 AttributeError（rc=1），等于放行后再开一个同族崩口。
    headers_raw = cast(dict[str, object], check.get("headers") or {})
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
    # 期望 3xx → 用不跟随重定向的 opener（详见函数头说明）
    _opener = _no_redirect_opener if 300 <= expected_status < 400 else None

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
        # 期望 3xx 时走 _opener.open（不跟随重定向）；否则走默认 urlopen
        if _opener is not None:
            with cast(http.client.HTTPResponse, _opener.open(req, timeout=timeout)) as resp:
                status = resp.status
                content = resp.read(_SMOKE_BODY_LIMIT).decode("utf-8", errors="replace")
        else:
            with cast(http.client.HTTPResponse, urllib.request.urlopen(req, timeout=timeout)) as resp:
                status = resp.status
                content = resp.read(_SMOKE_BODY_LIMIT).decode("utf-8", errors="replace")
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
            content = e.read(_SMOKE_BODY_LIMIT).decode("utf-8", errors="replace")
        except Exception:
            content = ""
    except Exception as e:  # 连接失败、超时、DNS 等
        result["time_ms"] = round((time.time() - start) * 1000, 1)
        errors.append(f"{type(e).__name__}: {e}")
        content = ""

    # 文本包含：expect_contains 是 AND 语义——每一条都必须命中，缺一条记一条错误，
    # 不因先命中一条就放行（那是 OR，会让配置里少写/写错一项悄悄通过）。
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

    # 三类断言（状态码 / 文本包含 / JSON 字段）共用同一个 errors 列表、全程不短路：
    # 一次运行就把「这次响应错在哪」全部打出来，不必改一条配置再跑一次。
    result["passed"] = len(errors) == 0
    return result


# ---------- 报告 ----------
def _safe_print(*values: object) -> None:
    # 打印并在控制台编码不兼容时（如 Windows GBK 下的非 ASCII 字符）做容错替换：按标准输出
    # 实际编码 replace（而不是回退 ascii），只损少数字符，保留「哪个检查失败、响应片段」等关键信息。
    text = " ".join(str(v) for v in values)
    try:
        print(text)
    except UnicodeEncodeError:
        enc = getattr(sys.stdout, "encoding", None) or "utf-8"
        print(text.encode(enc, "replace").decode(enc, "replace"))


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


# 生成自包含 HTML 报告：逐行拼接表格行（含命中文本与错误），通过/失败行用 ok/bad 样式区分。
# 动态片段**一律** html.escape 后再拼：「依赖配置可信」只对
# name/url 成立（测试目标由使用者提供），对 errors/detail 不成立：errors 装的是异常文本与
# **HTTP 响应派生内容**（未命中的 expect_contains token 原文、`响应不是合法 JSON: {e}`、
# JSON 字段的实际值 actual!r），全部来自被探测服务的返回；而本产物是 CI 附件、由浏览器打开，
# 于是远端响应可以直接在报告页里注入 <script>（存储型 XSS 的本地版：攻击面是打开报告的人）。
# 局部变量名从 html 改为 document——模块名 html 被同名局部量遮蔽会让 escape() 在运行期抛错。
def write_html_report(results: list[CheckResult], summary: CheckResult, path: str) -> None:
    rows: list[str] = []
    for r in results:
        status_cls = "ok" if cast(bool, r["passed"]) else "bad"
        detail = ""
        matched_html = cast(list[str], r["matched_contains"])
        if matched_html:
            detail += "<div class='match'>命中: " + ", ".join(html.escape(token) for token in matched_html) + "</div>"
        for err in cast(list[str], r["errors"]):
            detail += f"<div class='err'>✗ {html.escape(err)}</div>"
        # detail 的每个分量都已单独 escape，剩下的只有本函数自己写的标签，故原样拼入。
        row = (
            f"<tr class='{status_cls}'>"
            + f"<td>{'✅' if cast(bool, r['passed']) else '❌'}</td>"
            + f"<td>{html.escape(str(r['name']))}</td>"
            + f"<td>{html.escape(str(r['method']))}</td>"
            + f"<td>{html.escape(str(r['status']))}</td>"
            + f"<td>{html.escape(str(r['time_ms']))}ms</td>"
            + f"<td>{detail}</td>"
            + f"</tr>"
        )
        rows.append(row)
    document = (
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
        f'<div class="meta">生成时间: {html.escape(str(summary["timestamp"]))} ｜ 耗时'
        f' {cast(float, summary["elapsed_ms"])}ms</div>\n'
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
        _ = f.write(document)


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

    try:
        checks, cfg_base = load_config(config_path)
    except (OSError, ValueError) as e:
        # 配置读取/格式错误退出码 2，与「检查失败(1)」区分，便于 CI 分辨是脚本/配置问题还是接口问题
        # ②：load_config 现在对**任意**形态畸形都抛 ValueError（不再留 AttributeError 给
        # run_check 崩栈），故这里的 2 是「配置问题」的唯一出口，本 except 元组不得缩窄。
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(2)
    base_url = base_url_arg or cfg_base

    # 合法但空的 checks 列表同样是「查了个空气」，必须与「配置损坏」同码退出。
    # 放在 main 而非 load_config，是因为顶层直接写成 [] 的合法形态也要覆盖。
    if not checks:
        print(f"ERROR: 冒烟配置的 checks 为空（0 条断言不构成通过）: {config_path}", file=sys.stderr)
        sys.exit(2)

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

    # CI 只看这里的退出码：任一检查失败 → 1，全部通过 → 0。走到这一步时 checks 至少有一条
    # 断言：配置损坏与「0 条断言」都已在上方以 rc=2 退出，故「一条都没跑」不可能被报告成通过。
    # 不得把 2 并入 1：scripts/_ci_web_smoke.sh 原样透传退出码，混同会让「配置写坏了」看起来像
    # 「面板接口挂了」，排障方向整个错掉。
    failed = cast(int, summary["failed"])
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
