# .github/actions/retry 复合动作「按退出码分档」的回归用例。
#
# 被测面两块，互不替代：
#   1) 结构锁（无条件执行、纯静态）：fail_fast_codes 必须存在且 default 为空串（「默认零行为变化」的
#      声明面）、fail-fast 分支必须以**原退出码**退出并位于退避 sleep **之前**、兜底路径仍以
#      「重试到上限 + ::error:: + exit 1」收尾、两个 workflow 的既有调用点除 web smoke 外无人传参。
#   2) 行为锁（真起 bash）：把 action.yml 的 run 脚本体**原样**抽出、在 tmp_path 下真跑，用计数器
#      文件数「命令实际被执行了几次」。只有真跑才能证明「不传该 input = 与旧版逐字一致」与
#      「命中列表 = 一次都不重试、且保留原 rc」；静态锁对「分支位置写反」「列表解析漏 case」失明。
#
# 为什么没有 skipif：bash 在 CI（ubuntu）与本机（Windows + Git Bash）两侧都存在，缺 bash 时一律
# **显式失败**——行为锁是本文件唯一的自证手段，静默 skip 等于「门禁没跑却报绿」。
#
# 判据一律按字节比较（不传 text=True/encoding=）：脚本体 UTF-8 落盘、bash 原样 echo，
# 期望串在断言处 .encode("utf-8")，与宿主控制台码页彻底解耦。
#
# 变异验证（2026-09-30 实跑，三项均已当轮还原）：① 删掉 fail-fast 分支 → 结构锁与行为锁两格红；
# ② default 由 "" 改成 "2" → 声明面判据红；③ 分支挪到 sleep 之后 → 顺序判据与 runs 计数红。

from __future__ import annotations

import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
ACTION_FILE = ROOT / ".github" / "actions" / "retry" / "action.yml"
CI_FILE = ROOT / ".github" / "workflows" / "ci.yml"
BUILD_FILE = ROOT / ".github" / "workflows" / "build-release.yml"

# retry 复合动作的 uses 字面值（与 AGENTS 门禁命令 `grep 'uses: \./\.github/actions/retry'` 同口径）。
RETRY_USES_VALUE = "./.github/actions/retry"
RETRY_USES_RE = re.compile(r"uses:\s*\./\.github/actions/retry\b")

# retry 调用点数量下限（实测 2026-10-20：ci.yml 12 处 + build-release.yml 5 处 = 17 处，下限取 16）。
# 用 >= 而非 ==：新增调用点属放宽、不该弄红本用例；**减少**说明有人把重试内联回 job 里，
# 违反 AGENTS「网络安装重试统一走 .github/actions/retry」，必须拦。
MIN_RETRY_CALL_SITES = 16

# 唯一被允许传 fail_fast_codes 的调用点：Web 面板 HTTP 冒烟（rc=2 = 配置形态畸形，重试无意义）。
WEB_SMOKE_LABEL_KEYWORD = "冒烟"
WEB_SMOKE_COMMAND_KEYWORD = "_ci_web_smoke.sh"
# web smoke 传的具体值必须就是 2 —— 传成 0 会把假绿重新引进（rc=0 命中列表 → 立刻「成功」退出）。
WEB_SMOKE_FAIL_FAST_CODES = "2"

# 行为锁的标签，出现在 ::warning:: / ::error:: / 成功行里，用于把「谁的日志」钉在本用例上。
_PROBE_LABEL = "probe-label"


@dataclass(frozen=True)
class _BehaviourCase:
    # 一行一个场景；want_runs 是「被重试命令实际执行了几次」的唯一真判据（计数器文件字节数）。
    # want_in / want_not_in 存 str、断言处 encode("utf-8") 后按**字节**比对 stdout。
    title: str
    cmd_rc: int
    codes: str | None
    attempts: int
    want_runs: int
    want_rc: int
    want_in: tuple[str, ...]
    want_not_in: tuple[str, ...]


_BEHAVIOUR_CASES: tuple[_BehaviourCase, ...] = (
    _BehaviourCase(
        # 默认路径逐字未变：不传列表时 rc=2 与 rc=1 没有任何区别，仍跑满 attempts、最终收敛成 1。
        title="default_empty_codes_still_retries_to_cap_and_exits_1",
        cmd_rc=2,
        codes="",
        attempts=3,
        want_runs=3,
        want_rc=1,
        want_in=("::warning::", "失败（第 1/3 次）", "连续 3 次失败"),
        want_not_in=("属配置类错误",),
    ),
    _BehaviourCase(
        # RETRY_FAIL_FAST_CODES 整个未定义（set -u 形态）也必须等同空串，不得在半路炸掉动作。
        title="unset_env_var_behaves_as_disabled",
        cmd_rc=2,
        codes=None,
        attempts=2,
        want_runs=2,
        want_rc=1,
        want_in=("::warning::", "连续 2 次失败"),
        want_not_in=("属配置类错误", "unbound variable"),
    ),
    _BehaviourCase(
        # 命中列表：只跑 1 次、以**原退出码** 2 退出，且一条重试 warning 都不许有。
        title="fail_fast_code_hit_stops_immediately_with_original_rc",
        cmd_rc=2,
        codes="2",
        attempts=3,
        want_runs=1,
        want_rc=2,
        want_in=("属配置类错误", "退出码 2"),
        want_not_in=("::warning::" + _PROBE_LABEL, "连续 3 次失败"),
    ),
    _BehaviourCase(
        # 不误伤可重试故障：rc=1（面板起不来 / 瞬时 HTTP 抖动）即便列表里有 2 也照常重试。
        title="retryable_rc_1_is_not_affected_by_codes_2",
        cmd_rc=1,
        codes="2",
        attempts=3,
        want_runs=3,
        want_rc=1,
        want_in=("::warning::", "连续 3 次失败"),
        want_not_in=("属配置类错误",),
    ),
    _BehaviourCase(
        # 首次即成功：一次都不重试，rc=0，且不得出现任何 ::error:: / ::warning::。
        title="first_attempt_success_exits_0_without_noise",
        cmd_rc=0,
        codes="",
        attempts=3,
        want_runs=1,
        want_rc=0,
        want_in=("成功（第 1 次尝试）",),
        want_not_in=("::warning::", "::error::"),
    ),
    _BehaviourCase(
        # 解析容错：非法条目「x」被忽略并留 ::warning::，同串的合法 2 仍然生效（立刻停、rc=2）。
        # 这条同时钉住「忽略非法项 ≠ 整个列表失效」——否则配置类错误会退回无限重试。
        title="illegal_token_warned_and_ignored_legal_token_still_active",
        cmd_rc=2,
        codes="x, 2",
        attempts=3,
        want_runs=1,
        want_rc=2,
        want_in=("含非法条目", "属配置类错误"),
        want_not_in=("失败（第 1/3 次）",),
    ),
    _BehaviourCase(
        # 列表匹配必须按整码而非子串：rc=12 不得被列表里的「 2 」误命中（否则可重试故障会被吞掉）。
        title="code_12_is_not_matched_by_list_containing_only_2",
        cmd_rc=12,
        codes="2",
        attempts=2,
        want_runs=2,
        want_rc=1,
        want_in=("::warning::", "连续 2 次失败"),
        want_not_in=("属配置类错误",),
    ),
    _BehaviourCase(
        # 空格分隔与逗号分隔等价（多码列表），命中即立刻带原 rc 退出。
        title="space_separated_list_matches",
        cmd_rc=5,
        codes="2 5",
        attempts=3,
        want_runs=1,
        want_rc=5,
        want_in=("属配置类错误", "退出码 5"),
        want_not_in=("失败（第 1/3 次）",),
    ),
)


def _action_doc() -> dict[str, Any]:
    assert ACTION_FILE.is_file(), f"缺少复合动作定义：{ACTION_FILE}"
    doc = yaml.safe_load(ACTION_FILE.read_text(encoding="utf-8"))
    assert isinstance(doc, dict), "action.yml 必须解析为映射"
    return cast(dict[str, Any], doc)


def _retry_steps_of(path: Path) -> list[dict[str, Any]]:
    # 按 YAML 结构收全部 retry 调用点（jobs.<id>.steps[].uses），供「谁传了什么 input」判定用。
    # 走结构而不是行号：调用点在文件里挪动/换 job 都不该让本锁失效，形态漂移才该红。
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(doc, dict), f"{path.name} 必须解析为映射"
    jobs = doc.get("jobs") or {}
    assert isinstance(jobs, dict), f"{path.name} 的 jobs 必须是映射"
    sites: list[dict[str, Any]] = []
    for job in jobs.values():
        if not isinstance(job, dict):
            continue
        steps = job.get("steps") or []
        if not isinstance(steps, list):
            # 调用他人 workflow 的 job 没有 steps，一律跳过而不是抛 AttributeError 掩盖真判据。
            continue
        for step in steps:
            if isinstance(step, dict) and str(step.get("uses") or "").strip() == RETRY_USES_VALUE:
                sites.append(step)
    return sites


def _retry_run_body() -> str:
    # 取 run 脚本体本体（YAML 块标量已去掉缩进）：行为锁跑的就是生产脚本，而不是本文件另抄的副本
    # ——AGENTS「测试不得自实现被测逻辑」，删掉 action.yml 里的分支，行为锁必须跟着红。
    doc = _action_doc()
    steps = doc["runs"]["steps"]
    assert isinstance(steps, list) and len(steps) == 1, f"复合动作步骤数异常：{steps!r}"
    step = steps[0]
    assert isinstance(step, dict)
    assert step.get("shell") == "bash", "run 步骤必须显式声明 shell: bash（复合动作硬要求）"
    body = step.get("run")
    assert isinstance(body, str) and body.strip(), "run 脚本体不得为空"
    return body


def _require_bash() -> str:
    found = shutil.which("bash")
    if found is None:
        # 显式失败而非 skip：本函数的存在就是「行为锁不许静默消失」的实现。
        raise AssertionError("环境缺少 bash，retry 复合动作的行为锁无法执行（不得用 skip 掩盖）")
    return found


def _offset(body: str, needle: str, *, where: str) -> int:
    # 锚点缺失即红（结构锁的「缺失」与「存在」必须可区分），并带上位置信息便于定位。
    idx = body.find(needle)
    assert idx >= 0, f"{where}：run 脚本体缺少锚点 {needle!r}"
    return idx


def _while_loop_end(body: str) -> int:
    # while 主体的 `done` 必须**从循环头往后找**：列表解析那段自带一个缩进相同的 for…done，
    # 用 body.find("done") 会命中它（位置在所有重试逻辑之前），顺序判据于是全部反向成立。
    loop_start = _offset(body, 'while [ "$attempt" -le "$RETRY_ATTEMPTS" ]', where="while 循环头")
    idx = body.find("done", loop_start)
    assert idx >= 0, "while 循环缺少 done（重试主体不完整）"
    return idx


def test_fail_fast_codes_input_declared_with_empty_default() -> None:
    doc = _action_doc()
    inputs = doc["inputs"]
    assert isinstance(inputs, dict)
    assert "fail_fast_codes" in inputs, "inputs 必须声明 fail_fast_codes（缺则调用方传了也不生效）"
    spec = inputs["fail_fast_codes"]
    assert isinstance(spec, dict)
    # 默认空串 = 不启用。改成任何非空值都会让全部既有调用点在特定退出码上少重试——
    # 「默认零行为变化」这条硬约束的声明面就在这里。
    assert spec.get("default") == "", f"fail_fast_codes 的 default 必须是空串，实际 {spec.get('default')!r}"
    assert spec.get("required") is False, "fail_fast_codes 必须是可选 input"
    # input 必须以 env 形态进入脚本（与 command/attempts 同一口径），否则脚本读不到值。
    env = doc["runs"]["steps"][0]["env"]
    assert isinstance(env, dict), "run 步骤的 env 必须是映射"
    assert (
        env.get("RETRY_FAIL_FAST_CODES") == "${{ inputs.fail_fast_codes }}"
    ), f"env 未把 input 传给脚本：{env.get('RETRY_FAIL_FAST_CODES')!r}"


def test_fail_fast_branch_exits_with_original_rc_before_backoff() -> None:
    body = _retry_run_body()
    # 「带原退出码退出」的唯一形态就是 exit "$rc"（收尾兜底走 exit 1，成功出口走 exit 0）。
    # 出现次数必须恰为 1：多于一次说明有第二处以任意码提前退出，等于给旧路径开了后门。
    exit_rc_count = body.count('exit "$rc"')
    assert exit_rc_count == 1, f'exit "$rc" 应恰有一处（fail-fast 分支），实际 {exit_rc_count} 处'
    ff_idx = _offset(body, 'exit "$rc"', where="fail-fast 分支")
    sleep_idx = _offset(body, 'sleep "$wait_seconds"', where="退避 sleep")
    loop_end = _while_loop_end(body)
    # 重试 warning 的锚点要带 ${RETRY_LABEL} 前缀：解析列表时对非法条目也打一条
    # ::warning::fail_fast_codes …，它位置在循环**之前**，拿裸 ::warning:: 当锚点会误判顺序。
    warning_idx = _offset(body, "::warning::${RETRY_LABEL}", where="重试 warning")
    # 顺序判据：fail-fast 必须在退避 sleep **之前**、且仍在 while 循环体内。
    # 写反（挪到 sleep 之后）＝「白等一轮退避再失败」，对配置类错误毫无意义。
    assert ff_idx < sleep_idx, "fail-fast 分支必须位于退避 sleep 之前，不得先等再失败"
    assert ff_idx < loop_end, "fail-fast 分支必须仍在 while 循环体内（否则一次都不会执行到）"
    assert sleep_idx < loop_end, "退避 sleep 必须在循环体内"
    assert ff_idx < warning_idx, "命中 fail-fast 时不得再打重试 ::warning::（warning 属于旧路径）"
    # 取退出码的形态：set -e 下只有 `cmd || rc=$?` 既能拿到码又不会终止脚本。
    _offset(body, "|| rc=$?", where="退出码采集")


def test_default_fallback_path_still_retries_then_exits_1() -> None:
    body = _retry_run_body()
    # 兜底路径三要素逐条钉住：循环条件、attempt 自增、重试到上限后仍以 exit 1 收尾。
    # 这三条任何一个被「顺手优化」掉，既有 16 个调用点的语义就变了，而行为锁只会看到 rc 变化。
    _offset(body, 'while [ "$attempt" -le "$RETRY_ATTEMPTS" ]', where="循环条件")
    _offset(body, "attempt=$(( attempt + 1 ))", where="attempt 自增")
    loop_end = _while_loop_end(body)
    assert body.rstrip().endswith("exit 1"), "兜底收尾必须是最后一个语句 exit 1（不得改成 exit 0 / exit $rc）"
    # 收尾归因：循环之外必须还有一处 ::error::（重试到上限的落锤），否则红态只剩退出码没有原因。
    assert body.rfind("::error::") > loop_end, "循环之后必须留一条 ::error:: 收尾归因"
    # 列表命中判定必须「读解析出来的集合」而不是直读 input 字符串——空串时集合恒空、永不命中，
    # 这才是「默认零行为变化」的机制保证（行为锁的空列表那一格同时从外部见证）。
    _offset(body, "RETRY_FAIL_FAST_CODES", where="脚本读取 input 环境变量")


def test_call_sites_unchanged_except_web_smoke_passes_fail_fast_codes() -> None:
    ci_steps = _retry_steps_of(CI_FILE)
    build_steps = _retry_steps_of(BUILD_FILE)
    sites = ci_steps + build_steps
    assert len(sites) >= MIN_RETRY_CALL_SITES, f"retry 调用点少于 {MIN_RETRY_CALL_SITES}：{len(sites)}"

    # 两种口径必须给出同一个数：正则扫文本 vs YAML 结构。不等说明某个调用点形态漂移
    # （如 uses 前后加了注释/引号），那种漂移会让 AGENTS 的 grep 门禁本身失真。
    text_total = len(RETRY_USES_RE.findall(CI_FILE.read_text(encoding="utf-8"))) + len(
        RETRY_USES_RE.findall(BUILD_FILE.read_text(encoding="utf-8"))
    )
    assert text_total == len(sites), f"文本口径 {text_total} 与结构口径 {len(sites)} 不一致"

    passed = [step for step in sites if isinstance(step.get("with"), dict) and step["with"].get("fail_fast_codes")]
    assert len(passed) == 1, f"只允许 web smoke 一处传 fail_fast_codes，实际 {len(passed)} 处"
    with_map = passed[0]["with"]
    assert WEB_SMOKE_LABEL_KEYWORD in str(with_map.get("label", "")), "唯一传参的调用点必须是 Web 面板冒烟"
    assert WEB_SMOKE_COMMAND_KEYWORD in str(with_map.get("command", "")), "唯一传参的调用点必须跑 _ci_web_smoke.sh"
    assert str(with_map.get("fail_fast_codes")) == WEB_SMOKE_FAIL_FAST_CODES, (
        f"web smoke 的 fail_fast_codes 必须是 {WEB_SMOKE_FAIL_FAST_CODES!r}，"
        f"实际 {with_map.get('fail_fast_codes')!r}（传 0 会把假绿引进来）"
    )
    # build-release.yml 的调用点一律是 pip/brew/apt/choco 安装，不存在「配置类错误」这一档退出码，
    # 传任何值都只会削弱网络抖动重试；这里显式钉住「无人传」而不是放任漂移。
    assert not any(
        isinstance(step.get("with"), dict) and step["with"].get("fail_fast_codes") for step in build_steps
    ), "build-release.yml 的 retry 调用点不得传 fail_fast_codes"


@pytest.mark.parametrize("case", _BEHAVIOUR_CASES, ids=lambda c: c.title)
def test_retry_script_behaviour_with_real_bash(tmp_path: Path, case: _BehaviourCase) -> None:
    bash = _require_bash()
    body = _retry_run_body()
    script = tmp_path / "retry_script.sh"
    # 强制 LF：action.yml 本体是 LF，而 Windows 上「不写 newline 用默认换行」会把脚本转成 CRLF，
    # bash 会把行尾 \r 当命令的一部分（set -euo pipefail\r → command not found），
    # 那种失败与本次改动无关、极易误判成代码回归。
    script.write_text(body, encoding="utf-8", newline="\n")

    # 计数器落在 cwd（= tmp_path）的相对路径：两侧 runner 都能用，且完全不涉及路径分隔符转换。
    env = dict(os.environ)
    # PYTHONUTF8=1 与门禁同源（MID-63）：本用例不跑 Python 门禁，保留同一口径免得后来人当装饰删。
    env["PYTHONUTF8"] = "1"
    env.update(
        {
            "RETRY_COMMAND": f"printf x >>counter.txt; exit {case.cmd_rc}",
            "RETRY_ATTEMPTS": str(case.attempts),
            # backoff=0：退避算法 wait_seconds = attempt * backoff 仍逐字执行，只是不真等秒；
            # 保留 sleep 而不是去掉，才能让「跑满 attempts」这条判据在秒级内可复现。
            "RETRY_BACKOFF": "0",
            "RETRY_LABEL": _PROBE_LABEL,
        }
    )
    if case.codes is None:
        # 整串 env 都不给：验证 set -u 下 ${RETRY_FAIL_FAST_CODES:-} 的兜底，动作不得半路炸掉。
        env.pop("RETRY_FAIL_FAST_CODES", None)
    else:
        env["RETRY_FAIL_FAST_CODES"] = case.codes

    proc = subprocess.run(
        [bash, script.name],
        cwd=str(tmp_path),
        env=env,
        capture_output=True,  # 不传 text/encoding：判据一律按字节比较
    )

    counter = tmp_path / "counter.txt"
    runs = counter.read_bytes().count(b"x") if counter.is_file() else 0
    out = proc.stdout

    assert runs == case.want_runs, f"{case.title}：实际执行 {runs} 次，期望 {case.want_runs} 次；stdout={out!r}"
    assert (
        proc.returncode == case.want_rc
    ), f"{case.title}：最终 rc={proc.returncode}，期望 {case.want_rc}；stdout={out!r}"
    for needle in case.want_in:
        assert needle.encode("utf-8") in out, f"{case.title}：stdout 缺少 {needle!r}；实际 {out!r}"
    for needle in case.want_not_in:
        assert needle.encode("utf-8") not in out, f"{case.title}：stdout 不应出现 {needle!r}；实际 {out!r}"
