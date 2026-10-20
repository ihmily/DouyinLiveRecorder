# ci.yml「Gate frontend tests not skipped」的 node-id 清单 ↔ `tests/frontend/*.mjs` 的完备性回归锁。
#
# 治理症状（M-28）：`node --test <文件>` 只跑被点名的那一个文件、不会顺带发现同级其他 `.mjs`，
# 于是不进清单就等于该文件的全部回归锁在正常 CI 中从不执行，CI 依旧全绿。这条约束原先只有
# AGENTS.md 的文字与 `scripts/agent_hook_guard.py` 的 PostToolUse 规则两处载体；后者在 `.qoder/`
# 本地工具目录（不随仓库分发、不得进镜像），对其它贡献者与 CI 本身都不成立，漏登记仍会漂回仓库。
# 本文件把同一判据压成随仓库分发的机检锁：枚举目录下的用例本体与清单点名的入口求差集，非空即红。
#
# 事实源关系：清单本体仍在 ci.yml，本文件只**读取**它，不另抄一份副本（定位方式与
# tests/test_ci_retry_action.py 同口径——按 YAML 结构取步骤，不按行号、不按全文正则）。
#
# 为什么不照抄 Hook 的判据：Hook 认「同目录同名 `.py` 包装」，而现存包装里有两位于 tests/ 顶层
# 且与 `.mjs` 不同名（`test_frontend_quality_ui.py`、`test_frontend_regression_gates.py` 各驱动
# 一份），照它写会把既有合法形态判红。本文件改按「已登记的包装实际引用了哪个用例本体」
# 建立映射，映射取自包装源码里的路径常量，不靠命名巧合。
#
# 双向钉（对齐 tests/test_pre_commit_config.py 的「清单 ↔ 配置」口径）：
#   正向——目录里每个用例本体都必须被某个**已登记**的包装引用到（漏登记即红）；
#   反向——清单点名的包装必须存在、点名的用例函数必须真的定义、包装引用的文件必须还在盘上
#         （改名或删除后清单忘了同步 = 悬空入口，`node --test` 跑不到任何东西却仍然绿）。
# 两侧各带 fail-closed 前置守卫：解析不到步骤 / 入口或目录枚举为空都会显式失败，
# 否则「扫不到东西的绿灯」会让本锁在被掏空的那一刻反而显示通过。

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Any, cast

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
CI_FILE = ROOT / ".github" / "workflows" / "ci.yml"
FRONTEND_DIR = ROOT / "tests" / "frontend"

# 承载 node-id 清单的 CI 步骤名，逐字取自 ci.yml 与 AGENTS.md「测试」条目；按名字定位而不是按位置。
GATE_STEP_NAME = "Gate frontend tests not skipped"

# 本锁自身在清单里的入口。清单漂移时本文件必须**跑在那个步骤里**才会报（正向差集要红，前提是有人
# 执行这段比对），所以把「自己也进清单」也钉成一条断言，见 test_lock_itself_runs_inside_the_frontend_gate。
SELF_NODE_ID = "tests/test_ci_frontend_registration.py::test_every_frontend_mjs_is_registered"

# node-id 形态：tests/xxx.py::test_yyy。清单在 bash 里用反斜杠续行，续行符与行尾空白都不属于 id。
_NODE_ID_RE = re.compile(r"tests/[^\s'\"\\]+\.py::[A-Za-z_][A-Za-z0-9_]*")

# 包装里指向用例本体的字符串常量形态（`Path(__file__).parent / "x.mjs"` 里那个常量）。
# 必须限定「整串都是路径/文件名字符」：包装的断言文案里也会出现 .mjs 字样，放宽到 endswith
# 会把中文文案当成引用，反向判据随即要求那个不存在的文件在盘上，凭空判红。
# 连带约束：本锁文件自己也在清单里，所以本文件内**不得**出现整串像路径的 .mjs 字面量
# （自检夹具的用例名一律经 _synthetic_case() 拼出），否则会被自己的反向判据当成驱动关系。
_MJS_CONST_RE = re.compile(r"[\w.\-][\w.\-/\\]*\.mjs", re.ASCII)


def _ci_doc() -> dict[str, Any]:
    assert CI_FILE.is_file(), f"缺少 CI 工作流定义：{CI_FILE}"
    doc = yaml.safe_load(CI_FILE.read_text(encoding="utf-8"))
    assert isinstance(doc, dict), "ci.yml 必须解析为映射"
    return cast("dict[str, Any]", doc)


def _gate_step_run() -> str:
    # 按 YAML 结构取步骤脚本体。命中数必须恰为一处：零处说明步骤被删或改名（本锁失去基准），
    # 多处说明出现同名步骤（清单会被拆到两个地方，正是「并行清单」的雏形），两者都不得静默放过。
    doc = _ci_doc()
    jobs = doc.get("jobs") or {}
    assert isinstance(jobs, dict), "ci.yml 的 jobs 必须是映射"
    bodies: list[str] = []
    for job in jobs.values():
        if not isinstance(job, dict):
            continue
        steps = job.get("steps") or []
        if not isinstance(steps, list):
            # 调用他人 workflow 的 job 没有 steps，跳过而不是抛 AttributeError 掩盖真判据。
            continue
        for step in steps:
            if isinstance(step, dict) and str(step.get("name") or "").strip() == GATE_STEP_NAME:
                run = step.get("run")
                assert isinstance(run, str) and run.strip(), f"步骤 {GATE_STEP_NAME!r} 的 run 脚本体不得为空"
                bodies.append(run)
    assert len(bodies) == 1, f"ci.yml 中名为 {GATE_STEP_NAME!r} 的步骤应恰有一处，实际 {len(bodies)} 处"
    return bodies[0]


def _registered_node_ids() -> list[str]:
    # fail-closed：一条入口都解析不出来时，正向差集会「全体未登记」、反向差集恒空，
    # 看着像判据生效，实则清单形态已经漂移（例如改成整模块跑、或改用 --ignore 反选）。先拦下来。
    body = _gate_step_run()
    assert "pytest" in body, f"步骤 {GATE_STEP_NAME!r} 的 run 里不再调用 pytest，node-id 判据已失效"
    ids = _NODE_ID_RE.findall(body)
    assert ids, f"步骤 {GATE_STEP_NAME!r} 未解析到任何 node-id，清单写法漂移（期望 tests/x.py::test_y）"
    # 去重保序：同一入口重复点名不改变判定，但会让「清单条数」这类读数出现歧义。
    unique: list[str] = []
    for node_id in ids:
        if node_id not in unique:
            unique.append(node_id)
    return unique


def _frontend_cases() -> list[str]:
    # 枚举面非空是另一侧的 fail-closed 前置：目录被清空或 glob 写错时差集恒空，本锁会谎报「全部已登记」。
    assert FRONTEND_DIR.is_dir(), f"缺少前端用例目录：{FRONTEND_DIR}"
    names = sorted(path.name for path in FRONTEND_DIR.glob("*.mjs") if path.is_file())
    assert names, f"{FRONTEND_DIR} 下未枚举到任何 .mjs，扫描面为空即判据失效"
    return names


def _wrapper_tree(wrapper_rel: str) -> ast.Module:
    # 走 AST 而不是全文正则：这些包装的**头注释**会提到别的用例本体的名字（M-28 的成因叙述就在注释里），
    # 全文匹配会把注释里的名字也算成引用，于是「漏登记」能被一段历史说明掩盖掉——判据就此空转。
    wrapper = ROOT / wrapper_rel
    assert wrapper.is_file(), f"清单点名的包装不存在：{wrapper_rel}（入口悬空，CI 该步会以收集错误收场）"
    return ast.parse(wrapper.read_text(encoding="utf-8"), filename=str(wrapper))


def _case_refs_of(tree: ast.Module) -> set[str]:
    refs: set[str] = set()
    for node in ast.walk(tree):
        # 只取字符串常量：路径拼接的末段就是用例本体文件名。
        if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
            continue
        if _MJS_CONST_RE.fullmatch(node.value):
            refs.add(Path(node.value).name)
    return refs


def _registered_case_names() -> set[str]:
    # 并集只来自**已登记**的包装：写了 .py 包装却不进 ci.yml，等于该用例本体仍未闭合（M-28 原症状）。
    registered: set[str] = set()
    for node_id in _registered_node_ids():
        registered |= _case_refs_of(_wrapper_tree(node_id.partition("::")[0]))
    return registered


def _dangling_entries() -> list[str]:
    # 反向差集：清单点名的入口必须落得下来。三类悬空都会让那一步「跑了却什么都没跑」：
    #   ① 包装文件已不存在；② 用例函数改了名（pytest 以 collection error 收场，
    #      而该步的 grep '[0-9]+ skipped' 判据抓不到它）；③ 包装引用的用例本体被删或改名
    #      （`node --test` 指向不存在的文件）。这里只返回人可读的条目，报法交给调用方。
    on_disk = set(_frontend_cases())
    stale: list[str] = []
    for node_id in _registered_node_ids():
        wrapper_rel, _, func_name = node_id.partition("::")
        tree = _wrapper_tree(wrapper_rel)
        defined = {node.name for node in tree.body if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)}
        if func_name not in defined:
            stale.append(f"{node_id}（包装里没有这个用例函数）")
        for ref in _case_refs_of(tree):
            if ref not in on_disk:
                stale.append(f"{node_id} → {ref}（用例本体已不在 {FRONTEND_DIR.relative_to(ROOT).as_posix()}）")
    return stale


# ───────────────────────── 前置守卫：两侧「解析得出来」必须先成立 ─────────────────────────


def test_gate_step_and_both_scan_faces_are_parseable() -> None:
    # 本锁的两个输入面（ci.yml 清单 / tests/frontend 目录）各自非空才谈得上差集。
    # 判据都写在 helper 里，这里显式跑一次，让「基准塌了」以一条独立、可读的红呈现，
    # 而不是藏在后面某条断言的连锁失败里（同 tests/test_test_hygiene.py 的 test_scan_root_is_not_empty）。
    node_ids = _registered_node_ids()
    cases = _frontend_cases()
    assert node_ids, "清单为空"
    assert cases, "目录下没有用例本体"
    # 映射机制本身也要自证：登记入口至少解析出一个被引用的用例本体，
    # 否则正向差集会「全体未登记」，红是红了，报的却是与事实无关的原因。
    assert _registered_case_names(), "已登记的包装里没有引用任何 .mjs，映射关系失效"


# ───────────────────────── 正向：目录里的每个用例本体都必须已登记 ─────────────────────────


def test_every_frontend_mjs_is_registered() -> None:
    missing = sorted(set(_frontend_cases()) - _registered_case_names())
    assert not missing, (
        f"以下前端用例未登记进 ci.yml「{GATE_STEP_NAME}」的 node-id 清单：{missing}。"
        "`node --test <文件>` 只跑被点名的文件、不会顺带发现同级其他 .mjs，漏登记的后果是"
        "该文件的全部回归锁在正常 CI 中从不执行（AGENTS.md「测试」/ M-28 实证）。"
        "请把对应 .py 包装入口补进那条清单：只加 id，不得动 python_build / node_version 常量。"
    )


# ───────────────────────── 反向：清单里的每个入口都不许悬空 ─────────────────────────


def test_registered_entries_are_not_dangling() -> None:
    stale = _dangling_entries()
    assert not stale, (
        f"ci.yml「{GATE_STEP_NAME}」的清单存在悬空入口：{stale}。"
        "要么把入口改回真实存在的用例，要么连同其包装一起删净——留着会让这一步给出虚假的前端覆盖信心。"
    )


# ───────────────────────── 自举：本锁自己也在被点名之列 ─────────────────────────


def test_lock_itself_runs_inside_the_frontend_gate() -> None:
    # 从清单里摘掉本文件不会让上面几条变红（正向差集依旧成立），所以「本锁随 CI 执行」必须单独钉。
    # 这一步同时也是本锁的第二条执行回路：全量 pytest 那一步跑的是 tests/ 收集，改由前端门禁步骤
    # 显式点名后，清单与目录的漂移会在**同一个步骤**里报出来，而不是等到下一位贡献者手跑。
    node_ids = _registered_node_ids()
    assert SELF_NODE_ID in node_ids, (
        f"完备性锁自身未进清单（应含 {SELF_NODE_ID}）。它不跑在前端门禁那一步里，"
        f"「{GATE_STEP_NAME}」就仍只是一个靠人记住的约定。"
    )


# ───────────────────────── 门禁自检：差集判据不得是「扫不到东西的绿灯」 ─────────────────────────


def _synthetic_case(stem: str) -> str:
    # 合成用例本体的文件名一律由此拼装，不写字面量：本锁自己也在清单里，而 _case_refs_of()
    # 会把「整串像路径的 .mjs 常量」认成驱动关系——直写 "xxx.mjs" 会让真实仓库的反向判据
    # 拿着夹具名去 tests/frontend/ 找文件、凭空判红（f-string 里的字面段被拆成两截，恰好不命中该形态）。
    return f"synthetic_{stem}.mjs"


def test_diff_logic_actually_reports_violations(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # 上面四条读的是真实仓库，跑绿只能证明「此刻没有漂移」，证明不了判据有抓漂移的能力；
    # 而真去改 ci.yml 做盘上变异会波及同会话其它用例（变异验证的一次性改动必须当轮还原）。
    # 故在 tmp_path 合成一份最小仓库、只换本模块的三个路径全局，喂给同一批 helper。
    frontend = tmp_path / "tests" / "frontend"
    frontend.mkdir(parents=True)
    registered_case = _synthetic_case("registered")
    forgotten_case = _synthetic_case("forgotten")
    deleted_case = _synthetic_case("deleted")
    for case_name in (registered_case, forgotten_case):
        (frontend / case_name).write_text("// case\n", encoding="utf-8")
    # 包装甲：引用存在的用例本体、函数名与清单一致 —— 合成场景里唯一「健康」的入口。
    (tmp_path / "tests" / "test_wrapper_ok.py").write_text(
        f'_FRONTEND_TEST = Path("{registered_case}")\n\n\ndef test_ok() -> None:\n    pass\n', encoding="utf-8"
    )
    # 包装乙：函数名与清单不符、引用又指向一份已不在盘上的用例本体 —— 反向判据的两个悬空点一次凑齐。
    (tmp_path / "tests" / "test_wrapper_drifted.py").write_text(
        f'_FRONTEND_TEST = Path("{deleted_case}")\n\n\ndef test_renamed_away() -> None:\n    pass\n', encoding="utf-8"
    )
    ci = tmp_path / "ci.yml"
    ci.write_text(
        "jobs:\n"
        "  test:\n"
        "    steps:\n"
        f"      - name: {GATE_STEP_NAME}\n"
        "        shell: bash\n"
        "        run: |\n"
        "          set -euo pipefail\n"
        "          python -m pytest \\\n"
        "            tests/test_wrapper_ok.py::test_ok \\\n"
        "            tests/test_wrapper_drifted.py::test_ok \\\n"
        "            -q -rs\n",
        encoding="utf-8",
    )
    # 三个全局都在**调用时**按名字解析，所以替换模块命名空间即可整条切换扫描面，无需给 helper 加参数。
    monkeypatch.setattr("tests.test_ci_frontend_registration.ROOT", tmp_path)
    monkeypatch.setattr("tests.test_ci_frontend_registration.CI_FILE", ci)
    monkeypatch.setattr("tests.test_ci_frontend_registration.FRONTEND_DIR", frontend)

    assert _registered_node_ids() == [
        "tests/test_wrapper_ok.py::test_ok",
        "tests/test_wrapper_drifted.py::test_ok",
    ], "合成清单没被按原样解析，后面的差集断言就失去意义"
    # 正向：被忘下的那份必须进差集，已登记的那份不得被误报。
    assert set(_frontend_cases()) - _registered_case_names() == {forgotten_case}, "正向判据没抓到漏登记入口"
    # 反向：函数名漂移与用例本体已不在盘上两处悬空都要被点名。
    stale = _dangling_entries()
    assert len(stale) == 2, f"反向判据应报两处悬空，实际：{stale}"
    assert any("用例函数" in item for item in stale), f"函数名漂移未被点名：{stale}"
    assert any(deleted_case in item for item in stale), f"已不存在的用例本体未被点名：{stale}"
    # 包装整个失踪时 helper 必须 fail-fast（真实仓库里这等于清单指向不存在的文件）。
    with pytest.raises(AssertionError, match="包装不存在"):
        _wrapper_tree("tests/test_wrapper_missing.py")
