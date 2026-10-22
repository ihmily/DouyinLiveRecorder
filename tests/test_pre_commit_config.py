# .pre-commit-config.yaml 与 AGENTS.md「格式化命令（门禁唯一基准）」的同源回归锁。
#
# 治理症状：五条仓库级门禁（check_annotations / compile_po / check_version / check_runtime_pins /
# check_skill_agents_consistency）曾只在 CI 与 `python scripts/run_gates.py` 执行，pre-commit 侧
# 完全漏配——本地提交绿不等于门禁全绿。本用例把「AGENTS.md 章节列出的每条常驻门禁都必须在
# pre-commit 找到对应 hook」钉成机检，新增门禁漏配即刻拦下。
#
# 断言口径：不钉整行字面量——`python -m black` 由 mirror hook `id: black` 覆盖，`python scripts/x.py`
# 由 local hook `entry:` 覆盖；锁的是「该门禁由 pre-commit 触发」这一不变量，只钉「谁被调用」，
# 不钉参数顺序（避免 M-26 类反转：钉旧实参名 → 契约反转后静默空洞成立）。
#
# 未纳入断言：`mypy --platform linux` 属按需触发的条件增跑；pre-commit 不覆盖是刻意设计，
# 否则每次提交要跑两遍 mypy（本机 + Linux 交叉），噪声大而无收益。

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any, cast

import yaml

ROOT = Path(__file__).resolve().parent.parent

# AGENTS.md「格式化命令」章节列出的五条仓库级门禁脚本（匹配口径取脚本相对路径子串：
# entry 可再携带参数，只要脚本本身被调用即视为覆盖，不钉参数顺序与字符串完全相等）。
REPO_LEVEL_GATE_SCRIPTS: tuple[str, ...] = (
    "scripts/check_annotations.py",
    "scripts/compile_po.py",
    "scripts/check_version.py",
    "scripts/check_runtime_pins.py",
    "scripts/check_skill_agents_consistency.py",
)


def _load_run_gates() -> Any:
    # 沿用 test_run_gates.py 惯例：scripts/ 不在包路径内，用 spec_from_file_location 显式加载；
    # 复用它的 extract_gate_commands，本文件绝不重抄解析器（两处各写一份迟早演化出两种章节口径）。
    spec = importlib.util.spec_from_file_location("_pre_commit_gate_probe", ROOT / "scripts" / "run_gates.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_run_gates = _load_run_gates()


def _load_agents_gate_commands() -> list[str]:
    # 走 run_gates 现成的解析器：AGENTS.md 章节若被改（新增/删除门禁行），本用例立即同步。
    return cast("list[str]", _run_gates.extract_gate_commands(ROOT / "AGENTS.md"))


def _load_pre_commit_config() -> dict[str, Any]:
    cfg_path = ROOT / ".pre-commit-config.yaml"
    assert cfg_path.exists(), f"缺少 {cfg_path}"
    loaded = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict), "pre-commit 配置文件顶层必须是 mapping"
    return cast("dict[str, Any]", loaded)


def _iter_hooks(cfg: dict[str, Any]) -> list[dict[str, Any]]:
    # 摊平所有 repo 下的 hooks；调用方按 repo/entry/id 自行筛选。
    hooks: list[dict[str, Any]] = []
    for repo in cfg.get("repos", []):
        for hook in repo.get("hooks", []) or []:
            hook_with_repo = dict(hook)
            hook_with_repo["__repo__"] = repo.get("repo")
            hooks.append(hook_with_repo)
    return hooks


def _local_entries(cfg: dict[str, Any]) -> list[str]:
    # 返回 repo: local 下所有 hook 的 entry 字符串。
    out: list[str] = []
    for hook in _iter_hooks(cfg):
        if hook.get("__repo__") != "local":
            continue
        entry = hook.get("entry")
        if isinstance(entry, str):
            out.append(entry)
    return out


# ───────────────────────── 前置：AGENTS.md 侧不能被"清空" ─────────────────────────


def test_agents_gate_section_includes_repo_level_gates() -> None:
    # 前置守卫：章节必须**确实列出**这五条门禁脚本；若章节被误删，下面的覆盖用例会因
    # 「AGENTS.md 里根本没这条」而空过，反而给出「门禁同源」的假绿（SEV-2219 同口径 fail-closed）。
    cmds = _load_agents_gate_commands()
    assert cmds, "未能从 AGENTS.md「格式化命令」章节解析到任何门禁，同源锁失去基准"
    for script in REPO_LEVEL_GATE_SCRIPTS:
        assert any(script in c for c in cmds), f"AGENTS.md「格式化命令」章节缺失门禁行：{script}"


def test_agents_gate_section_includes_formatter_tools() -> None:
    # black/isort/mypy 同样不能从章节里消失——两侧同时钉住，任何一侧被「精简」都会有一头变红。
    cmds = _load_agents_gate_commands()
    assert any("black" in c and "--check" in c for c in cmds), "AGENTS.md 章节缺 black --check 门禁"
    assert any("isort" in c and "--check-only" in c for c in cmds), "AGENTS.md 章节缺 isort --check-only 门禁"
    # 至少一条不带路径参数的 `mypy` 门禁（另一条 `mypy --platform linux` 属条件增跑）
    assert any(c.strip().split()[0] == "mypy" for c in cmds), "AGENTS.md 章节缺常驻 mypy 门禁"


# ───────────────────────── 核心：pre-commit 必须覆盖上述每一条 ─────────────────────────


def test_pre_commit_local_hooks_cover_repo_level_gates() -> None:
    # 核心回归锁：五份仓库级门禁脚本必须在 local hook 的 entry 里出现（子串匹配，允许额外参数）。
    # 缺失任一条 = 本次修复回归，CI 与本地门禁再次脱钩。
    entries = _local_entries(_load_pre_commit_config())
    missing = [s for s in REPO_LEVEL_GATE_SCRIPTS if not any(s in e for e in entries)]
    assert not missing, f"pre-commit 未覆盖 AGENTS.md 仓库级门禁脚本：{missing}"


def test_pre_commit_mirror_hooks_cover_formatter_tools() -> None:
    # black / isort 由官方 mirror hook 覆盖（id 分别为 "black"、"isort"），
    # 参数走 pyproject；本用例只锁"存在"，不重述参数（AGENTS.md 硬约束）。
    hook_ids = {h.get("id") for h in _iter_hooks(_load_pre_commit_config()) if h.get("__repo__") != "local"}
    assert "black" in hook_ids, "pre-commit 缺失 black mirror hook（AGENTS.md 格式化门禁依赖）"
    assert "isort" in hook_ids, "pre-commit 缺失 isort mirror hook（AGENTS.md 格式化门禁依赖）"


def test_pre_commit_local_hook_covers_mypy_without_path_args() -> None:
    # mypy 必须是 local hook 且 entry 是**裸** `mypy`：显式传路径会覆盖 [tool.mypy].files
    # （AGENTS.md 硬约束）；「mypy src/」曾让 gui.py / main.py 等根入口长期逃逸，本用例是那道墙。
    cfg = _load_pre_commit_config()
    mypy_hooks = [h for h in _iter_hooks(cfg) if h.get("__repo__") == "local" and h.get("id") == "mypy"]
    assert mypy_hooks, "pre-commit 缺失 mypy local hook"
    for hook in mypy_hooks:
        entry = hook.get("entry", "")
        assert isinstance(entry, str), f"mypy hook entry 形态异常：{entry!r}"
        tokens = entry.split()
        assert tokens and tokens[0] == "mypy", f"mypy hook entry 首 token 应为 `mypy`：{entry!r}"
        # 除带值 flag（如 `--platform linux`）之外不得出现目录参数
        non_flag_args = [t for t in tokens[1:] if not t.startswith("-") and t != "linux"]
        assert not non_flag_args, f"mypy hook entry 传了路径参数，会覆盖 [tool.mypy].files：{entry!r}"


# ───────────────────────── 结构不变量：四个 hook 的控制位必须一致 ─────────────────────────


def test_repo_level_gate_hooks_share_system_pass_filenames_false_always_run() -> None:
    # 结构不变量：五份仓库级门禁 hook 必须 language=system + pass_filenames=false + always_run=true。
    # 五个脚本按仓库根遍历做跨文件比对（i18n 双侧、版本号三处、钉定表对账、Skill 目录表与 AGENTS.md），
    # 若允许 pass_filenames 会把 staged 文件当参数传入而破坏自身遍历；若非 always_run 则改 .po /
    # build_exe.py / pyproject.toml 时不触发，等于回到本次修复前的症状（语义细则见配置文件内注释）。
    cfg = _load_pre_commit_config()
    matched = 0
    for hook in _iter_hooks(cfg):
        if hook.get("__repo__") != "local":
            continue
        entry = hook.get("entry", "")
        if not isinstance(entry, str):
            continue
        if not any(s in entry for s in REPO_LEVEL_GATE_SCRIPTS):
            continue
        matched += 1
        hook_id = hook.get("id")
        assert hook.get("language") == "system", f"hook {hook_id!r} 应为 language=system（消费 venv 已装包）"
        assert hook.get("pass_filenames") is False, f"hook {hook_id!r} 必须 pass_filenames: false"
        assert (
            hook.get("always_run") is True
        ), f"hook {hook_id!r} 必须 always_run: true（跨文件比对不能被 staged 类型漏掉）"
    assert matched == len(
        REPO_LEVEL_GATE_SCRIPTS
    ), f"pre-commit 应命中 {len(REPO_LEVEL_GATE_SCRIPTS)} 条仓库级门禁 hook，实际 {matched} 条"


# ───────────────────────── run_gates.py 作为 single hook 入口的可用性锁 ─────────────────────────


def test_run_gates_is_invocable_as_single_hook_entry() -> None:
    # AGENTS.md 明写 run_gates.py 是「本地一次性触发点」；本用例证明它也能被 pre-commit 风格的
    # (language: system, entry: python scripts/run_gates.py, pass_filenames: false) 调用。没有把它
    # 加进当前配置，是因为会与既有 black / isort / mypy hook 重复执行——但作为备选入口，
    # 「--list 只解析、不执行」的分支必须可用且退出码遵循文档定义。判据形态：直接调 main()
    # 而非 subprocess（避开 CI 无 venv 环境下 pre-commit 侧依赖）。
    import sys
    import types as _types

    argv_backup = list(sys.argv)
    stdout_backup = sys.stdout
    sys.argv = ["run_gates.py", "--list"]
    try:
        import io as _io

        captured = _io.StringIO()
        sys.stdout = captured
        rc = _run_gates.main(["--list"])
    finally:
        sys.stdout = stdout_backup
        sys.argv = argv_backup
    out_lines = [ln for ln in captured.getvalue().splitlines() if ln.strip()]
    assert rc == 0, f"run_gates.py --list 应以 0 退出，实际 {rc}"
    # --list 输出必须覆盖四条仓库级门禁脚本 + black/isort/mypy
    for script in REPO_LEVEL_GATE_SCRIPTS:
        assert any(
            script in ln for ln in out_lines
        ), f"run_gates.py --list 未列出 {script}，AGENTS.md 章节与本地入口脱钩"
    assert any("black" in ln and "--check" in ln for ln in out_lines)
    assert any("isort" in ln and "--check-only" in ln for ln in out_lines)
    assert any(ln.strip().startswith("mypy") for ln in out_lines)


# ───────────────────── 变异验证回归锁：故意去掉一条会红 ─────────────────────
# 其余用例都是「配置文件 + AGENTS.md」两侧结构比对，不需真跑子进程；变异验证已由开发期一次性
# 完成（临时移除 check_annotations hook 条目 → test_pre_commit_local_hooks_cover_repo_level_gates 变红），
# 此处不再就地改文件（AGENTS.md：变异改动必须当轮还原并带 MUTATION 标记）。
