# scripts/agent_hook_guard.py 的回归用例（Hook/Command 项目级资产的行为锁）。
#
# 被测面按「行为优先」组织，绝不用正则钉生产代码字面量（AGENTS.md M-26：文本锁会在契约反转后
# 静默空洞成立，给出与事实相反的绿）：
#   1) PreToolUse 三条拦截规则（批量重装 venv / 清理越界 / 工作区级通配删除）与放行面
#      （AGENTS.md 自己给出的两条收尾清理命令、二级 pip 处置、常规开发命令）；
#   2) PostToolUse 三条「对门禁三面隐形」的即时反馈（MUTATION 残留 / 行尾形态混存 / .mjs 未登记）；
#   3) 触发条件与 AGENTS.md 约束的**一致性锁**——受保护目录集合必须与 AGENTS.md 声明的
#      「运行期产物目录」枚举逐项相等，改一侧不改另一侧即红；
#   4) CLI 契约（stdin JSON → 出口按事件能力双轨）：Pre 命中 = exit 2 + stderr 阻断；
#      Post 非阻断（provider 文档：exit 2 的 stderr 注入仅对 blockable 事件生效），命中 =
#      exit 0 + stdout JSON `hookSpecificOutput.feedback` 即时回传；证明注册形态与脚本入口对得上。
#   5) 资产接线锁：.qoder/settings.json 的 hooks 指向本脚本、command 资产不复制门禁清单。
#      这两处位于 .gitignore 忽略的 .qoder/ 内（AGENTS.md「dockerignore / gitignore 同源约定」），
#      全新克隆没有该目录 → 用例 skip，不把本地资产状态冒充成仓库门禁。
#
# 全部离线：不联网、不跑任何仓库门禁；子进程一律驱动本脚本自身。

from __future__ import annotations

import importlib.util
import json
import re
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parent.parent


def _load_guard() -> ModuleType:
    # scripts/ 不在包路径内，沿用仓内惯例（test_run_gates.py）用 spec_from_file_location 显式加载，
    # 避免 sys.path 注入被 isort 重排到 import 之前
    spec = importlib.util.spec_from_file_location("_agent_hook_guard_probe", ROOT / "scripts" / "agent_hook_guard.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


guard = _load_guard()

GUARD_SCRIPT = ROOT / "scripts" / "agent_hook_guard.py"

# AGENTS.md「CI / workflow 约定」的 dockerignore/gitignore 同源条目里「运行期产物目录（…）」的枚举；
# 事实源永远是 AGENTS.md 文本，本常量只用于反向见证（真值由 _agents_md_runtime_dirs() 现场解析）。
AGENTS_RUNTIME_DIR_PATTERN = re.compile(r"运行期产物目录（([^）]*)）")


def _agents_md_text() -> str:
    return (ROOT / "AGENTS.md").read_text(encoding="utf-8", errors="replace")


def _agents_md_runtime_dirs() -> set[str]:
    # 从 AGENTS.md 解析「运行期产物目录」枚举（`downloads/`/`recordings/`/… 形态）。
    # 解析不到必须抛，不得返回空集合——空集合会让「集合相等」断言退化成恒真（假绿）。
    match = AGENTS_RUNTIME_DIR_PATTERN.search(_agents_md_text())
    if match is None:
        raise AssertionError("AGENTS.md 未找到「运行期产物目录（…）」枚举，一致性锁失去比对基准")
    return {token.strip("`").strip("/") for token in match.group(1).split("/") if token.strip("`").strip("/")}


def test_protected_dirs_match_agents_md_enumeration() -> None:
    # 触发条件与 AGENTS.md 约束一致（本次修复的验收口径）：受保护目录集合 == 文档枚举集合
    assert set(guard.PROTECTED_RUNTIME_DIRS) == _agents_md_runtime_dirs()


def test_maintenance_dir_guard_matches_agents_md_sentence() -> None:
    # `scripts/` 是另一类禁区（「不要动 scripts/ 下正式维护脚本」），不并入运行期产物目录，
    # 但仍须能在 AGENTS.md 里找到原句，否则就是脚本单方面发明的规则
    text = _agents_md_text().replace("\r\n", "\n")
    assert guard.PROTECTED_MAINTENANCE_DIR == "scripts"
    assert "`scripts/` 下正式维护脚本" in text


@pytest.mark.parametrize(
    "command",
    [
        "pip install --force-reinstall -r requirements.txt",
        "pip install --ignore-installed --no-deps -r requirements.txt",
        "python -m pip install --force-reinstall --no-cache-dir -U .",
    ],
)
def test_bulk_venv_reinstall_is_blocked(command: str) -> None:
    # AGENTS.md「风险控制（前置）」：批量重装 venv 依赖必须由用户在普通终端执行
    verdict = guard.check_bash_command(command)
    assert verdict is not None
    assert verdict[0] == "R-PIP-BULK"


@pytest.mark.parametrize(
    "command",
    [
        # 一级/二级处置形态（wheel 直解、单个小包补装）是代理可以自行尝试的路径
        'HTTP_PROXY="" HTTPS_PROXY="" pip install --proxy "" brotli',
        "pip download --no-deps -d /tmp/wheels brotli",
        "python scripts/run_gates.py",
        "python -m pytest tests/test_agent_hook_guard.py -q",
        "git status --short",
        "python -c \"import pathlib;b=pathlib.Path(f).read_bytes();print(b.count(b'\\r\\n'))\"",
    ],
)
def test_legitimate_commands_are_allowed(command: str) -> None:
    # 放行面同样承重：拦截规则一旦过宽，代理会绕过 Hook 而不是修规则，约束就此失效
    assert guard.check_bash_command(command) is None


@pytest.mark.parametrize("target", ["downloads", "recordings", "logs", "backup_config", "scripts"])
def test_cleanup_reaching_protected_dirs_is_blocked(target: str) -> None:
    # 逐目录验证（含 scripts/），防止只锁运行期产物、放过误删维护脚本的形态
    assert guard.check_bash_command(f"Remove-Item -Recurse -Force ./{target}/") is not None
    assert guard.check_bash_command(f"rm -rf ./{target}") is not None


def test_agents_md_cleanup_commands_are_allowed() -> None:
    # AGENTS.md「测试收尾清理临时脚本」逐字给出的两条命令必须放行——它们是约定的正规收尾动作，
    # 其中 PowerShell 那条还把 .venv 写在 -notmatch 排除式里，不得被当成删除目标
    powershell = (
        "Get-ChildItem -Recurse -File -Include *_tmp_*.py,tmp_*.py,mock_*.py | "
        "Where-Object { $_.FullName -notmatch '\\\\(\\.venv|node_modules)\\\\' } | Remove-Item -Force"
    )
    posix = "find . -type f \\( -name '*_tmp_*.py' -o -name 'tmp_*.py' \\) -not -path '*/.venv/*' -delete"
    assert guard.check_bash_command(powershell) is None
    assert guard.check_bash_command(posix) is None


@pytest.mark.parametrize(
    "command",
    [
        "rm -rf .",
        "rm -rf *",
        "git clean -fdx",
        "Remove-Item -Recurse -Force .",
    ],
)
def test_wide_recursive_delete_is_blocked(command: str) -> None:
    # 无过滤面的通配/工作区级删除：AGENTS.md 要求绝对路径、逐个删
    verdict = guard.check_bash_command(command)
    assert verdict is not None
    assert verdict[0] == "R-WIPE-SCOPE"


def test_mutation_marker_residue_is_reported(tmp_path: Path) -> None:
    # MUTATION 残留对 black / mypy / 注释检查三面全隐形，只有写入当下报才有意义
    probe = tmp_path / "probe_mutation.py"
    probe.write_bytes(b"x = 1  # " + guard._MUTATION_MARK.encode() + b"  # probe\n")
    verdict = guard.check_written_file(probe)
    assert verdict is not None
    assert verdict[0] == "P-MUTATION"


def test_mixed_line_ending_is_reported_and_single_form_is_allowed(tmp_path: Path) -> None:
    # 行尾判据：本仓约定每个文件形态单一，混存是「整文件重写静默翻转」留下的唯一肉眼可见指纹
    mixed = tmp_path / "probe_mixed.py"
    mixed.write_bytes(b"a = 1\r\nb = 2\nc = 3\r\n")
    verdict = guard.check_written_file(mixed)
    assert verdict is not None
    assert verdict[0] == "P-LINE-ENDING"

    clean = tmp_path / "probe_clean.py"
    clean.write_bytes(b"a = 1\nb = 2\n")
    assert guard.check_written_file(clean) is None

    crlf_only = tmp_path / "probe_crlf.py"
    crlf_only.write_bytes(b"a = 1\r\nb = 2\r\n")
    assert guard.check_written_file(crlf_only) is None


def test_line_ending_check_skips_tool_directories(tmp_path: Path) -> None:
    # .venv / __pycache__ 里的 .py 不归本仓换行符约定，判了只会制造噪声
    probe = tmp_path / ".venv" / "lib" / "probe_mixed.py"
    probe.parent.mkdir(parents=True)
    probe.write_bytes(b"a = 1\r\nb = 2\n")
    assert guard.check_written_file(probe) is None


def test_unregistered_frontend_mjs_is_reported(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # M-28 实证：`node --test <文件>` 只跑被点名的文件，不登记进 ci.yml 的 .mjs 其回归锁从不执行
    ci = tmp_path / "ci.yml"
    ci.write_text("          node --version\n", encoding="utf-8")
    monkeypatch.setattr(guard, "_CI_WORKFLOW", ci)
    probe = tmp_path / "tests" / "frontend" / "test_motion_new.mjs"
    probe.parent.mkdir(parents=True)
    probe.write_text("// probe\n", encoding="utf-8")
    verdict = guard.check_written_file(probe)
    assert verdict is not None
    assert verdict[0] == "P-MJS-REGISTER"


def test_registered_frontend_mjs_is_allowed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ci = tmp_path / "ci.yml"
    ci.write_text("            tests/frontend/test_motion_new.py::test_motion_new_frontend \\\n", encoding="utf-8")
    monkeypatch.setattr(guard, "_CI_WORKFLOW", ci)
    probe = tmp_path / "tests" / "frontend" / "test_motion_new.mjs"
    probe.parent.mkdir(parents=True)
    probe.write_text("// probe\n", encoding="utf-8")
    assert guard.check_written_file(probe) is None


def _run_hook(event: Mapping[str, Any]) -> subprocess.CompletedProcess[bytes]:
    # 子进程输出只做字节比较（AGENTS.md 测试约定 #8）：中文 Windows 下 text=True 解码会抛错。
    # 不传 stdin=：subprocess.run 在给了 input 时自己接管道，两者同传会 ValueError。
    return subprocess.run(
        [sys.executable, str(GUARD_SCRIPT)],
        input=json.dumps(event).encode("utf-8"),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=ROOT,
        check=False,
    )


def test_cli_contract_blocks_with_exit_code_2() -> None:
    # PreToolUse 是唯一可阻断站：exit 2 + stderr 回给 agent，阻断声明与实际能力一致
    event = {
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": "pip install --force-reinstall -r requirements.txt"},
    }
    proc = _run_hook(event)
    assert proc.returncode == 2
    assert b"R-PIP-BULK" in proc.stderr
    # 拒绝消息不得回显完整命令原文（官方 hook 安全口径）
    assert b"--no-cache-dir" not in proc.stderr


def test_cli_contract_post_tool_use_reports_via_json_feedback(tmp_path: Path) -> None:
    # PostToolUse 非阻断：写入已发生、不可撤销，命中规则时必须走文档化通道
    # （exit 0 + stdout JSON feedback）而非 exit 2——后者的 stderr 注入按官方文档仅对
    # blockable 事件生效，继续依赖会把「即时回传」的声明架空成无人消费的静默。
    probe = tmp_path / "probe_mutation.py"
    probe.write_bytes(b"x = 1  # " + guard._MUTATION_MARK.encode() + b"  # probe\n")
    proc = _run_hook({"hook_event_name": "PostToolUse", "tool_name": "Write", "tool_input": {"file_path": str(probe)}})
    assert proc.returncode == 0, "Post 分支不得以 exit 2 冒充阻断（非阻断事件的 stderr 注入不生效）"
    payload = json.loads(proc.stdout.decode("utf-8"))
    specific = payload["hookSpecificOutput"]
    assert specific["hookEventName"] == "PostToolUse"
    assert "P-MUTATION" in specific["feedback"]


def test_cli_contract_post_tool_use_clean_write_is_silent(tmp_path: Path) -> None:
    # 放行面同样锁住：干净文件的 Post 事件不得产生任何 feedback/stderr 噪声
    probe = tmp_path / "probe_clean.py"
    probe.write_bytes(b"a = 1\nb = 2\n")
    proc = _run_hook({"hook_event_name": "PostToolUse", "tool_name": "Write", "tool_input": {"file_path": str(probe)}})
    assert proc.returncode == 0
    assert proc.stdout == b""
    assert proc.stderr == b""


def test_cli_contract_allows_and_stays_silent() -> None:
    proc = _run_hook({"hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_input": {"command": "git status"}})
    assert proc.returncode == 0
    assert proc.stderr == b""


def test_cli_contract_fails_open_on_unparsable_event() -> None:
    # 事件形态不认识时必须放行：Hook 坏掉不能演变成「agent 什么也做不了」，
    # 那不是 fail-safe，而是把工具故障伪装成代码不合格
    proc = subprocess.run(
        [sys.executable, str(GUARD_SCRIPT)],
        input=b"{not json",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=ROOT,
        check=False,
    )
    assert proc.returncode == 0
    assert b"\xe5\xb7\xb2\xe6\x94\xbe\xe8\xa1\x8c" in proc.stderr  # 「已放行」的 UTF-8 字节，避免依赖控制台代码页


def test_script_self_test_entrypoint_passes() -> None:
    # --self-test 是不依赖 IDE 是否已加载 Hook 的自证通道（配置存在 ≠ 已执行）。
    # stdin=DEVNULL：本用例不给 input，若让子进程继承调用方 stdin，在管道/IDE harness 下
    # 会撞到已关闭句柄（实测 OSError WinError 6，与 scripts/run_gates.run_command 同一坑）。
    proc = subprocess.run(
        [sys.executable, str(GUARD_SCRIPT), "--self-test"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        stdin=subprocess.DEVNULL,
        cwd=ROOT,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    assert b"self-test OK" in proc.stdout


def test_hook_registration_wires_the_guard() -> None:
    # 资产接线锁：.qoder/settings.json 的 hooks 必须把 PreToolUse(Bash) 与 PostToolUse(Write|Edit) 指向本脚本
    settings = ROOT / ".qoder" / "settings.json"
    if not settings.is_file():
        pytest.skip("本地项目级 Qoder 资产目录未创建（.qoder/ 被 .gitignore 忽略，非仓库门禁）")
    registered = json.loads(settings.read_text(encoding="utf-8"))
    hooks = registered.get("hooks", {})
    pre = [record for record in hooks.get("PreToolUse", []) if "Bash" in record.get("matcher", "")]
    post = [record for record in hooks.get("PostToolUse", []) if re.search(r"Write|Edit", record.get("matcher", ""))]
    assert pre and post, "Hook 已注册但缺 Pre/Post 任一入口"
    for record in pre + post:
        for handler in record.get("hooks", []):
            assert "agent_hook_guard.py" in handler.get("command", "")


def test_command_asset_does_not_duplicate_gate_list() -> None:
    # 命令资产只能引用门禁入口，不得复制清单——否则 AGENTS.md 章节更新后会静默漂移
    command_file = ROOT / ".qoder" / "commands" / "dlr-dod.md"
    if not command_file.is_file():
        pytest.skip("本地项目级 Qoder 命令资产未创建（.qoder/ 被 .gitignore 忽略）")
    text = command_file.read_text(encoding="utf-8")
    assert "run_gates.py" in text
    assert "AGENTS.md" in text
    # 逐字参数属「格式化命令」章节独有，出现在这里就是并行事实源
    assert "--line-length 120" not in text
    assert "--target-version py314" not in text


def test_runtime_pin_file_change_triggers_check_reminder(tmp_path: Path) -> None:
    # SEV-10：_PINNED_RUNTIME_SHA256 或 check_runtime_pins.py 变更后对 black / mypy / 注释检查
    # 三面全隐形，只有 check_runtime_pins.py 自己能兜住——PostToolUse 必须在写入当下提醒 agent
    probe = tmp_path / "build_exe.py"
    probe.write_text("_PINNED_RUNTIME_SHA256 = {}\n", encoding="utf-8")
    verdict = guard._check_runtime_pins_changed(probe, ["build_exe.py"])
    assert verdict is not None
    assert verdict[0] == "P-RUNTIME-PIN"
    assert "check_runtime_pins.py" in verdict[1]


def test_runtime_pin_check_scripts_itself_triggers_reminder(tmp_path: Path) -> None:
    # check_runtime_pins.py 自身变更同样触发——改判定逻辑后不跑检查 = 「门禁本身失效」无人知
    probe = tmp_path / "scripts" / "check_runtime_pins.py"
    probe.parent.mkdir(parents=True, exist_ok=True)
    probe.write_text("# probe\n", encoding="utf-8")
    verdict = guard._check_runtime_pins_changed(probe, ["scripts", "check_runtime_pins.py"])
    assert verdict is not None
    assert verdict[0] == "P-RUNTIME-PIN"


def test_runtime_pin_unrelated_file_does_not_trigger(tmp_path: Path) -> None:
    # 放行面：不相关文件不得误触发，否则 agent 每次写入都被骚扰会绕过 Hook
    probe = tmp_path / "utils.py"
    probe.write_text("x = 1\n", encoding="utf-8")
    assert guard._check_runtime_pins_changed(probe, ["utils.py"]) is None
    # 同名测试文件也不得触发（路径段精确匹配）
    test_probe = tmp_path / "test_build_exe.py"
    test_probe.write_text("# test\n", encoding="utf-8")
    assert guard._check_runtime_pins_changed(test_probe, ["tests", "test_build_exe.py"]) is None


def test_runtime_pin_via_check_written_file(tmp_path: Path) -> None:
    # 端到端：通过 check_written_file 主入口触发，证明 PostToolUse 路径真的能回传 feedback
    probe = tmp_path / "build_exe.py"
    probe.write_text("_PINNED_RUNTIME_SHA256 = {}\n", encoding="utf-8")
    verdict = guard.check_written_file(probe)
    assert verdict is not None
    assert verdict[0] == "P-RUNTIME-PIN"


def test_runtime_pin_via_cli_post_event(tmp_path: Path) -> None:
    # CLI 契约锁：PostToolUse 事件驱动 build_exe.py 写入 → exit 0 + JSON feedback
    probe = tmp_path / "build_exe.py"
    probe.write_text("_PINNED_RUNTIME_SHA256 = {}\n", encoding="utf-8")
    proc = _run_hook({"hook_event_name": "PostToolUse", "tool_name": "Write", "tool_input": {"file_path": str(probe)}})
    assert proc.returncode == 0, "Post 分支不得以 exit 2 冒充阻断"
    payload = json.loads(proc.stdout.decode("utf-8"))
    specific = payload["hookSpecificOutput"]
    assert specific["hookEventName"] == "PostToolUse"
    assert "P-RUNTIME-PIN" in specific["feedback"]


def test_mutation_proof_rules_are_load_bearing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # 变异验证（内存改写法，不落盘、不留标记）：逐项拆掉生产判据后，对应的行为锁必须失效，
    # 否则说明用例在自我实现规则而不是测生产实现（AGENTS.md 反假绿判定法）。
    # ① 受保护集合清空 + 维护目录改名 → 越界清理不再被拦
    monkeypatch.setattr(guard, "PROTECTED_RUNTIME_DIRS", ())
    monkeypatch.setattr(guard, "PROTECTED_MAINTENANCE_DIR", "no_such_dir")
    assert guard.check_bash_command("Remove-Item -Recurse -Force ./downloads/") is None
    monkeypatch.undo()

    # ② 删除动词面改宽 → 常规命令被误拦（证明动词集合不是装饰）
    monkeypatch.setattr(guard, "_DELETE_VERB_RE", re.compile(r"\b(status|pytest)\b", re.IGNORECASE))
    assert guard.check_bash_command("Remove-Item -Recurse -Force ./downloads/") is None
    monkeypatch.undo()

    # ③ git clean 正则失效 → 工作区级删除落空
    monkeypatch.setattr(guard, "_GIT_CLEAN_RE", re.compile(r"(?!)"))
    assert guard.check_bash_command("git clean -fdx") is None
    monkeypatch.undo()

    # ④ 变异标记常量改名 → 真残留不再被报（拿真带标记的文件验证，不靠文本比对）
    probe = tmp_path / "probe.py"
    probe.write_bytes(b"x = 1  # " + guard._MUTATION_MARK.encode() + b"\n")
    assert guard.check_written_file(probe) is not None
    monkeypatch.setattr(guard, "_MUTATION_MARK", "NO-SUCH-MARKER")
    assert guard.check_written_file(probe) is None
