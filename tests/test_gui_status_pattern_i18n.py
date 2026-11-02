# tests/test_gui_status_pattern_i18n.py — 画质监控状态行的跨语言回归锁（M-14）。
#
# 故障形态：状态行生产侧经 i18n.tr 翻译（src/recorder_status.py::display_info、main.py 的录制
# 启动处），消费侧若用硬编码简中正则/子串解析，英文用户切语言并重启录制后三类匹配全静默失败，
# 画质页不再刷新且无日志。AGENTS「关键约定 #13」禁止拿自然语言子串当跨模块契约，比较对象必须
# 取 i18n.tr(...) 后形态。
#
# 锁：① 四种受支持语言下三类行都能解析（行为锁）；② 语言热切换后匹配器重算；
# ③ 审查 F-06 的解析语义（贪婪 name 段 + [^\]]+ 画质段）不回退；
# ④ src/gui_qt/shared.py 不得再出现裸简中匹配字面量（AST 静态锁）。
#
# 走子进程而不在 pytest 进程跑：conftest 的 _pin_identity_translation 把 i18n._tr 钉成恒等映射，
# 跨语言判据必须在干净子进程里跑。被测实现是 src.gui_qt.quality_monitor.QualityMonitor（PySide6
# 窗口层的纯数据模型，不建窗口）；探测子进程一律按字节比较并显式注入 UTF-8。

import ast
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, cast

import pytest

ROOT = Path(__file__).resolve().parents[1]
SHARED_SOURCE = (ROOT / "src" / "gui_qt" / "shared.py").read_text(encoding="utf-8")
_MARKER = "\n@@WP_E_I18N@@ "

# 支持的语言全集（四语目录都齐，见 _SUPPORTED 断言）；用例逐语言跑同三条判据。
_LANGUAGES = ["zh_CN", "en_US", "en_GB", "zh_TW"]

# 子进程内驱动真实解析实现。三条 msgid 在这里**独立重写一份**（不引用 shared.STATUS_TPL_*）：
# 生产侧与消费侧必须同键，共用一个常量的话漂移会同时消失、用例假绿。
_SCRIPT = r"""
import json
import sys

import i18n
from src.gui_qt import shared as shared_module
from src.gui_qt.quality_monitor import QualityMonitor

TPL_RECORDING = "{recording_live}[{qa}] 正在录制中 {have_record_time}"
TPL_IDLE = "\r没有正在录制的直播 循环监测间隔时间：{delay_default}秒"
TPL_EMPTY = "\r没有正在监测和录制的直播"
TPL_DOWNGRADE = (
    "{record_name} 画质降级：设置 {record_quality_zh}({record_quality})"
    " 实际 {actual_quality_zh}({actual_quality_code})"
)
_TPLS = {"recording": TPL_RECORDING, "idle": TPL_IDLE, "empty": TPL_EMPTY, "downgrade": TPL_DOWNGRADE}


def _feed_line(tpl_key, kwargs, raw, loguru_prefix):
    template = _TPLS[tpl_key]
    # raw=True：不经 tr() 直接按原文打印——复刻 src/recorder_status.py 里
    # print("\r没有正在监测和录制的直播") 那条未过 tr 的裸字面量形态。
    text = template if raw else i18n.tr(template, **kwargs)
    if loguru_prefix:
        # 复刻 loguru 控制台 sink 的行形态（src/logger.py::custom_format），解析器会先剥前缀。
        text = "2026-09-29 12:00:00.000 | WARNING  - " + text
    return text


req = json.loads(sys.stdin.read())
out = {"cases": []}

for case in req["cases"]:
    requested = case["language"]
    effective = i18n.set_language(requested)
    monitor = QualityMonitor()
    lines = []
    for feed in case["feed"]:
        monitor.parse_line(
            _feed_line(feed["tpl"], feed.get("kwargs") or {}, feed.get("raw", False), feed.get("prefix", False)),
            lambda message, level: lines.append([message, level]),
            "12:00:00",
        )
    out["cases"].append(
        {
            "requested": requested,
            "effective": effective,
            "data": {name: dict(info) for name, info in monitor._data.items()},
            "lines": lines,
        }
    )

if req.get("reorder_check"):
    # 译文把占位符**换了顺序**（翻译完全可能这么写）。派生实现按占位符名字映射，顺序无关；
    # 这里用一支临时的 _tr 替身验证，不改仓库里的任何 i18n 目录文件（子进程自行还原）。
    i18n.set_language("en_US")
    real_tr = i18n._tr
    reordered = "recording in progress: {have_record_time} by {qa} <- {recording_live}"
    i18n._tr = lambda text: reordered if text == TPL_RECORDING else real_tr(text)
    shared_module._STATUS_PATTERNS_BY_LANG.clear()
    built = shared_module.status_patterns()
    line = "recording in progress: 0:00:12 by 原画 <- 主播[1号]"
    match = built.recording.match(line) if built.recording is not None else None
    out["reorder"] = None if match is None else {"name": match.group("recording_live"), "qa": match.group("qa")}
    i18n._tr = real_tr

if req.get("cache_race_check"):
    # 组装期换语言不得把**混语** patterns 固化进缓存（status_patterns 的复核逻辑）。
    # 语言码序列即注入本身：第 1 次读=zh_CN（进入组装），第 2 次读=组装期间被 UI 线程切走
    # →en_US（复核不等→本轮结果丢弃、不写缓存），第 3/4 次=en_US（重取并落定）。
    i18n.set_language("zh_CN")
    shared_module._STATUS_PATTERNS_BY_LANG.clear()
    seq = ["zh_CN", "en_US", "en_US", "en_US"]
    state = {"idx": 0, "builds": 0}
    real_get = shared_module.i18n_module.get_language
    real_build = shared_module._build_status_patterns

    def _flaky_get():
        value = seq[min(state["idx"], len(seq) - 1)]
        state["idx"] += 1
        return value

    def _counting_build():
        state["builds"] += 1
        return real_build()

    shared_module.i18n_module.get_language = _flaky_get
    shared_module._build_status_patterns = _counting_build
    try:
        built = shared_module.status_patterns()
        out["cache_race"] = {
            "keys": sorted(shared_module._STATUS_PATTERNS_BY_LANG.keys()),
            "builds": state["builds"],
            "get_calls": state["idx"],
            "cached_is_returned": shared_module._STATUS_PATTERNS_BY_LANG.get("en_US") is built,
        }
    finally:
        shared_module.i18n_module.get_language = real_get
        shared_module._build_status_patterns = real_build
        shared_module._STATUS_PATTERNS_BY_LANG.clear()

sys.stdout.write("\n@@WP_E_I18N@@ " + json.dumps(out, ensure_ascii=False))
"""


def _child_env() -> dict[str, str]:
    # M-31① 同口径：显式钉 UTF-8，不依赖宿主 shell 恰好带该环境变量。
    env = dict(os.environ)
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def _run_child(
    cases: list[dict[str, Any]], *, reorder_check: bool = False, cache_race_check: bool = False
) -> dict[str, Any]:
    payload = json.dumps(
        {"cases": cases, "reorder_check": reorder_check, "cache_race_check": cache_race_check}, ensure_ascii=False
    )
    proc = subprocess.run(
        [sys.executable, "-c", _SCRIPT],
        input=payload.encode("utf-8"),
        capture_output=True,
        timeout=180,
        cwd=str(ROOT),
        env=_child_env(),
    )
    marker = _MARKER.encode("utf-8")
    detail = proc.stderr.decode("utf-8", errors="replace")
    assert proc.returncode == 0, "status pattern subprocess failed: " + detail[-3000:]
    assert marker in proc.stdout, "no result marker in: " + proc.stdout.decode("utf-8", errors="replace")[-800:]
    # json.loads 返回 Any，直接 return 会让父侧所有下标检查整体失效（mypy 还会报
    # no-any-return）。这里只做声明收窄、不改运行时：结构校验仍在各用例的断言里。
    return cast(dict[str, Any], json.loads(proc.stdout.split(marker, 1)[1].decode("utf-8")))


def _recording_case(language: str) -> dict[str, Any]:
    # 只喂录制中行：降级告警会把同一房间条目的 set_quality/actual_quality 改写成告警档位，
    # 两类行必须各测各的，否则「录制行解析对了」会被后喂的降级行盖掉（见 _downgrade_case）。
    return {
        "language": language,
        "feed": [
            {
                "tpl": "recording",
                "kwargs": {
                    "recording_live": "主播甲",
                    "qa": "原画",
                    "have_record_time": "0:01:23",
                },
            }
        ],
    }


def _downgrade_case(language: str) -> dict[str, Any]:
    return {
        "language": language,
        "feed": [
            {
                "tpl": "recording",
                "kwargs": {
                    "recording_live": "主播甲",
                    "qa": "原画",
                    "have_record_time": "0:01:23",
                },
            },
            {
                "tpl": "downgrade",
                "kwargs": {
                    "record_name": "主播甲",
                    "record_quality_zh": "蓝光",
                    "record_quality": "3",
                    "actual_quality_zh": "超清",
                    "actual_quality_code": "2",
                },
                "prefix": True,
            },
        ],
    }


def _empty_case(language: str, *, raw: bool) -> dict[str, Any]:
    # 先喂一行录制中、再喂空态行：空态必须把 recording 标记清掉。
    # raw=True 走「未过 tr() 的原文」形态（STATUS_TPL_EMPTY 那条刻意不对称的串）。
    recording = {
        "tpl": "recording",
        "kwargs": {"recording_live": "主播甲", "qa": "原画", "have_record_time": "0:01:23"},
    }
    empty = {
        "tpl": "empty" if raw else "idle",
        "kwargs": {"delay_default": 120},
        "raw": raw,
    }
    return {"language": language, "feed": [recording, empty]}


def _case_result(payload: dict[str, Any], index: int) -> dict[str, Any]:
    # 载荷收窄的唯一出口：payload["cases"] 来自 json.loads、类型是 Any，逐处下标取值会把
    # Any 一路扩散到断言里（mypy 在定义处即报 no-any-return）。此处一次 cast 后，调用方拿到
    # dict[str, Any]；键写错仍由运行期 KeyError 兜住。
    return cast(dict[str, Any], payload["cases"][index])


# ─── 行为锁：四种语言下三类行都能被解析 ─────────────────────


@pytest.mark.parametrize("language", _LANGUAGES)
def test_recording_line_is_parsed_in_every_language(language: str) -> None:
    # 录制中行必须解析出主播名与画质档；硬编码简中正则在非简中语言下这里就红。
    result = _case_result(_run_child([_recording_case(language)]), 0)
    assert result["effective"] == language, f"{language} 语言目录缺失/未生效（实际 {result['effective']}）"
    data = result["data"]
    assert "主播甲" in data, f"{language}: 录制中行未被解析，data={data}"
    assert data["主播甲"]["recording"] is True
    assert data["主播甲"]["set_quality"] == "原画"
    assert data["主播甲"]["actual_quality"] == "原画"


@pytest.mark.parametrize("language", _LANGUAGES)
def test_downgrade_alert_is_parsed_in_every_language(language: str) -> None:
    # 降级告警（loguru 前缀行）必须置 downgraded/alert_*；
    # 且顺序上「录制中行在前、降级行在后」，验证降级行覆盖的是同一个房间条目。
    result = _case_result(_run_child([_downgrade_case(language)]), 0)
    info = result["data"].get("主播甲")
    assert info is not None, f"{language}: 两条行都没解析出来，data={result['data']}"
    assert info.get("downgraded") is True, f"{language}: 降级告警未被识别，info={info}"
    assert info.get("set_quality") == "蓝光"
    assert info.get("actual_quality") == "超清"
    assert str(info.get("alert_message")).find("蓝光") >= 0


@pytest.mark.parametrize("language", _LANGUAGES)
def test_idle_line_clears_recording_flag_in_every_language(language: str) -> None:
    # 空态行（经 tr() 的那条）必须把 recording 清掉——英文界面下旧实现恒不匹配，
    # 表现为「早已停止录制，画质监控页仍显示录制中」。
    result = _case_result(_run_child([_empty_case(language, raw=False)]), 0)
    info = result["data"].get("主播甲")
    assert info is not None, f"{language}: 录制中行未被解析，data={result['data']}"
    assert info["recording"] is False, f"{language}: 空态行未清除录制标记，info={info}"


@pytest.mark.parametrize("language", _LANGUAGES)
def test_untranslated_empty_line_still_clears_in_every_language(language: str) -> None:
    # M-14② 的不对称：src/recorder_status.py 的 print("\r没有正在监测和录制的直播")
    # 生产侧**没有** tr() 调用，能否被翻译取决于 main.py 的 builtins.print 补丁（冻结环境
    # 尚待实测）。所以消费侧必须连原文形态也认得——改成「只匹配 tr() 结果」即在
    # en_US/en_GB/zh_TW 下变红。
    result = _case_result(_run_child([_empty_case(language, raw=True)]), 0)
    info = result["data"].get("主播甲")
    assert info is not None, f"{language}: 录制中行未被解析，data={result['data']}"
    assert info["recording"] is False, f"{language}: 未翻译的空态原文未被识别，info={info}"


def test_bracketed_anchor_name_keeps_f06_semantics() -> None:
    # 审查 F-06：主播名里的 "[...]" 不得被当成画质段边界。
    # 派生实现必须逐字保持「贪婪 name 段 + [^\]]+ 画质段」，两种语言都验。
    case = {
        "language": "zh_CN",
        "feed": [
            {
                "tpl": "recording",
                "kwargs": {"recording_live": "主播[1号]", "qa": "原画", "have_record_time": "0:01:23"},
            }
        ],
    }
    en_case = dict(case, language="en_US")
    for payload_case in (case, en_case):
        result = _case_result(_run_child([payload_case]), 0)
        assert "主播[1号]" in result["data"], f"{payload_case['language']}: 幽灵行/丢行，data={result['data']}"
        assert result["data"]["主播[1号]"]["set_quality"] == "原画"


def test_language_hot_switch_recomputes_patterns() -> None:
    # M-14 要求的失效时机：GUI 语言菜单经 i18n.set_language 热切换，匹配器必须跟着重算。
    # 一个子进程里连跑 zh_CN → en_US → zh_CN：退回「模块级一次编译」时中间英文行必然失配。
    zh = _recording_case("zh_CN")
    en = _recording_case("en_US")
    payload = _run_child([zh, en, dict(zh)])
    for index, expected in enumerate(("zh_CN", "en_US", "zh_CN")):
        case = _case_result(payload, index)
        assert case["effective"] == expected
        assert "主播甲" in case["data"], f"第 {index + 1} 轮（{expected}）未解析：{case['data']}"


def test_reordered_translation_still_parsed() -> None:
    # 派生实现按**占位符名字**映射，不依赖译文里占位符的顺序。
    # 用临时目录替身把英文译文的顺序打乱（不改仓库里的 i18n 文件）。
    payload = _run_child([_recording_case("en_US")], reorder_check=True)
    reorder = payload["reorder"]
    assert reorder == {"name": "主播[1号]", "qa": "原画"}, f"占位符换序后解析失败：{reorder}"


def test_mid_build_language_switch_is_not_cached() -> None:
    # status_patterns 的组装期竞态（按语言缓存自带的问题）：组装要连读 6 次 i18n.tr()，
    # 语言若在中间被 UI 线程切走，得到的是**混语** patterns。判据不是「不抛异常」，而是
    # **缓存键集合**——混语结果不允许落进任何语言码为键的缓存（落了就长期失配）。
    # 注入方式就是语言码读取序列本身，不 patch 被测函数。
    payload = _run_child([], cache_race_check=True)
    case = payload["cache_race"]
    assert case["keys"] == ["en_US"], f"混语组装被固化进缓存：{case}"
    assert case["builds"] == 2, f"组装轮数不对（应为「丢弃一轮 + 按新语言重取一轮」）: {case}"
    # 每轮两次取值（进入前读语言、组装后复核），两轮共 4 次；少于 4 说明复核根本没跑。
    assert case["get_calls"] == 4, case
    assert case["cached_is_returned"] is True, "返回的不是落进缓存的那一份，缓存与返回值会分叉"


# ─── 静态锁：不得再出现裸简中匹配字面量 ──────────────────────

# 三类行的特征串：出现在**匹配代码**里即为 M-14 回归，只允许作为 tr() 的 msgid 常量存在。
_MATCHING_MARKERS = ("画质降级：设置", "正在录制中", "没有正在录制", "没有正在监测和录制的直播")


def _status_tpl_assigned_names(tree: ast.Module) -> set[str]:
    # 收集 shared.py 里赋给 STATUS_TPL_* 的字符串常量值——它们就是「msgid 常量」，
    # 特征串出现在这些值里是**正确**的（tr() 的键必须与生产侧逐字相同）。
    values: set[str] = set()
    for node in ast.walk(tree):
        targets = []
        value = None
        if isinstance(node, ast.Assign):
            targets, value = node.targets, node.value
        elif isinstance(node, ast.AnnAssign):
            targets, value = [node.target], node.value
        if value is None:
            continue
        if not any(isinstance(t, ast.Name) and t.id.startswith("STATUS_TPL") for t in targets):
            continue
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            values.add(value.value)
    return values


def test_no_bare_chinese_literals_outside_tr_templates() -> None:
    # 特征串只允许待在 STATUS_TPL_* 常量里（作为 tr 的 msgid）；
    # 一旦有人在 re.compile(...) 或 `xxx in msg` 里重新写死简中，本用例即红。
    tree = ast.parse(SHARED_SOURCE)
    allowed = _status_tpl_assigned_names(tree)
    assert allowed, "shared.py 里找不到 STATUS_TPL_* 常量（M-14 的派生实现被删了？）"
    offenders: list[str] = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Constant) and isinstance(node.value, str)):
            continue
        text = node.value
        if not any(marker in text for marker in _MATCHING_MARKERS):
            continue
        if text in allowed:
            continue
        offenders.append(f"shared.py:{node.lineno} {text[:40]!r}")
    assert offenders == [], "状态行匹配串不得硬编码简中（应由 tr() 结果派生）：" + "; ".join(offenders)


def test_patterns_are_derived_from_tr_and_cached_per_language() -> None:
    # 结构锁：匹配器必须由 i18n 的公开翻译入口派生、且**按语言惰性重算**。
    # 「模块级 re.compile(...) 一次钉死简中」正是 M-14 的原始形态，故这里反向钉死它。
    tree = ast.parse(SHARED_SOURCE)
    compiled_literals: list[str] = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "compile"
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)
        ):
            compiled_literals.append(node.args[0].value)
    assert not any(
        marker in literal for marker in _MATCHING_MARKERS for literal in compiled_literals
    ), "shared.py 仍有硬编码状态行的 re.compile 字面量"

    names = {n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
    assert "_build_status_patterns" in names and "status_patterns" in names
    # 语言变化必然经 get_language()，否则缓存键无从失效。
    status_fn = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "status_patterns")
    dumped = ast.dump(status_fn)
    assert "get_language" in dumped, "status_patterns 必须以当前语言为缓存键"
