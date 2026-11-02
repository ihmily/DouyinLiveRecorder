# scripts/check_coverage.py 的回归锁（该门禁此前全库零回归锁）。
#
# 口径：按「删掉某条 fail-closed 判据必须变红」组织用例，全部离线——只喂构造好的
# coverage 报告 dict / 临时目录树，不跑 pytest 自身、不调用真实 .coverage。
#
# 锁住的行为：
#   A) ：拿不到数据（文件缺失 / files 为空 / 报告不可解析 / src 枚举为空 /
#      登记表腐烂）一律 rc=2 并打印**下一步命令**，绝不退回 WARN 或「全部通过」；
#   B) ：判定面 = src/ 下**全部**模块，未登记阈值者按 GLOBAL_FLOOR 判定，
#      新增 src/*.py 不再自动豁免；
#   C) 数据文件比 src/、tests/ 最新 .py 陈旧 → rc=2（旧数据评门禁＝假绿）；
#   D) 报告键匹配必须整段模块路径（含 src/）落在尾部，只含 tests/utils.py 的报告
#      不得顶替 src/utils.py；
#   E) 白名单（GATE_EXEMPT_MODULES）每条必须写理由，且指向真实存在的模块；
#   F) CLI 出口必须把 0/1/2 三种 rc 原样 sys.exit（改成 `return` 就让门禁在 CI 里
#      退化成一行装饰性输出）；
#   G) 该分层：登记阈值 > 债务基线 > 全局下限；债务条目须有 tracker 出处与复核日期，
#      豁免理由写「生成物」必须能在文件里找到生成器标记（DEBT_CEILING 是条目数闸门）。
#
# **组织口径：一个用例只做一次门禁判定**（机检见 test_each_case_performs_a_single_gate_judgment）。
# 原因：多次判定共用同一份被 monkeypatch 改过的模块状态，而 setattr 要到用例 teardown 才生效——
# 第二次判定读到的还是第一次那份数据，于是「先写新数据、后还原旧数据」这类追加写法一进来就
# 产出成串假失败（单跑全绿、换个顺序就红）。确需两次判定的那一条用 ExitStack 把还原
# **推到两次判定之间**（见 test_stale_table_entry_exits_2_then_clean_table_passes）。
#
# 加载方式与 tests/test_run_gates.py 相同：scripts/ 不在包路径内，用
# spec_from_file_location 显式加载，避免 sys.path 注入被 isort 重排到 import 之前。

import ast
import contextlib
import importlib.util
import json
import os
import subprocess
import sys
import tomllib
import types
from pathlib import Path
from types import ModuleType
from typing import Any, cast

import pytest

ROOT = Path(__file__).resolve().parent.parent

# 门禁判定入口：本文件「一次判定一个用例」的机检按这份名单数调用次数。
_JUDGMENTS = frozenset({"evaluate_report", "check_coverage", "main"})


def _load_check_coverage() -> ModuleType:
    spec = importlib.util.spec_from_file_location("_check_coverage_probe", ROOT / "scripts" / "check_coverage.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _read_this_file() -> str:
    # 机检本文件自身用：读源码而不是 import（用例文件不该 import 自己）。
    return Path(__file__).resolve().read_text(encoding="utf-8")


check_coverage: Any = (
    _load_check_coverage()
)  # 动态加载的门禁脚本：属性由 mypy 视角不可见，按 Any 处理（与 tests/test_run_gates.py 同法）

# 登记表 + 白名单的全部模块：构造临时 root 时以它为「已登记面」，用例再各自追加新模块。
_REGISTERED = tuple(check_coverage.MODULE_THRESHOLDS) + tuple(check_coverage.GATE_EXEMPT_MODULES)


def _make_root(tmp_path: Path, extra_modules: tuple[str, ...] = ()) -> Path:
    # 造一棵最小「项目根」：src/ 下含全部登记表模块 + 本用例追加的模块。
    # 只建判定所需的东西（check_coverage 按文件系统枚举模块、按 mtime 比新鲜度），
    # 不复制真实源码——复制就会让「登记表指向磁盘模块」这类断言变成自证。
    for module in _REGISTERED + tuple(extra_modules):
        path = tmp_path / module
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# 占位模块（仅供门禁枚举，不执行）\n", encoding="utf-8")
    return tmp_path


def _report(percent_by_module: dict[str, float], *, backslash_keys: bool = False) -> dict[str, Any]:
    # 造 coverage JSON 报告。backslash_keys=True 时按 Windows 形态出题
    # （coverage json 在 Windows 上确实以反斜杠为键，尾部匹配规则必须吃得住）。
    files: dict[str, Any] = {}
    for module, pct in percent_by_module.items():
        key = module.replace("/", "\\") if backslash_keys else module
        files[key] = {"summary": {"percent_covered": pct}}
    return {"files": files, "totals": {"percent_covered": 0.0}}


def _full_pass_report() -> dict[str, Any]:
    return _report({module: 100.0 for module in _REGISTERED})


# ---------------------------------------------------------------------------
# E) 登记表自身的质量（表空 / 键腐烂都会让「判定面」悄悄缩小）


def test_registered_threshold_table_is_nonempty_and_points_at_real_modules() -> None:
    # 表为空 → evaluate_report 只会按下限评全部模块，登记语义静默消失；
    # 键指向不存在的模块 → 门禁配置腐烂（模块改名后表没跟着改）。
    assert check_coverage.MODULE_THRESHOLDS, "MODULE_THRESHOLDS 不得为空（AGENTS.md 认定它是阈值唯一事实源）"
    for module, threshold in check_coverage.MODULE_THRESHOLDS.items():
        assert (ROOT / module).is_file(), f"登记表阈值指向不存在的模块: {module}"
        assert 0 < threshold <= 100, f"{module} 的阈值不合理: {threshold}"


def test_exempt_whitelist_entries_are_justified_and_real() -> None:
    # 白名单是此后的「第三条路」，条目必须写明理由且指向真实模块，
    # 否则它会重新变成「自动豁免」的旁门（正是本门禁要消灭的形态）。
    assert isinstance(check_coverage.GATE_EXEMPT_MODULES, dict)
    for module, reason in check_coverage.GATE_EXEMPT_MODULES.items():
        assert (ROOT / module).is_file(), f"豁免名单指向不存在的模块: {module}"
        assert isinstance(reason, str) and len(reason.strip()) >= 8, f"{module} 的豁免理由缺失或过短: {reason!r}"
        assert module not in check_coverage.MODULE_THRESHOLDS, f"{module} 同时被登记阈值又豁免，语义冲突"


def test_global_floor_is_not_looser_than_project_fail_under() -> None:
    # 逐模块闸不得比 pyproject [tool.coverage.report].fail_under（全库总闸）更宽，
    # 否则「新模块零测试」能过逐模块闸、只被总闸拦下——判定面就漏了一半。
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    fail_under = float(pyproject["tool"]["coverage"]["report"]["fail_under"])
    assert (
        float(check_coverage.GLOBAL_FLOOR) >= fail_under
    ), f"GLOBAL_FLOOR={check_coverage.GLOBAL_FLOOR} 低于全库 fail_under={fail_under}：新模块可自动豁免"


def test_registered_thresholds_never_sit_below_global_floor_without_debt() -> None:
    # M-15：登记表不得存在「阈值 < GLOBAL_FLOOR 且未走 COVERAGE_DEBT」的条目——
    # 那是无 tracker/无到期/不受条数上限约束的债务基线（2026-10-24 抬闸时 spider/proxy=50 曾
    # 静默落入该形态）。运行时同回路机检在 check_coverage._validate_debt_and_exempt（rc=2）。
    below = {
        module: threshold
        for module, threshold in check_coverage.MODULE_THRESHOLDS.items()
        if threshold < check_coverage.GLOBAL_FLOOR
    }
    offenders = {module: value for module, value in below.items() if module not in check_coverage.COVERAGE_DEBT}
    assert not offenders, f"登记阈值低于 GLOBAL_FLOOR 且未走债务表（须抬值或登记债务）: {offenders}"


# 本文件的组织口径机检（防「两次判定塞进一个用例」这一族假失败回归）


def test_each_case_performs_a_single_gate_judgment() -> None:
    # 机检文件头的「组织口径」：每个 test_* 里对 evaluate_report / check_coverage / main
    # 的调用合计 ≤ 1；例外只放行「两次判定之间完成还原」的写法（函数体里出现 ExitStack）。
    # 判据按「test_ 前缀函数体 + _JUDGMENTS 名单上的属性调用」数次数：把判定挪进 helper
    # 或给用例改名都不计入——名单与判据范围须与文件头同步维护。
    offenders: dict[str, int] = {}
    for node in ast.walk(ast.parse(_read_this_file())):
        if not isinstance(node, ast.FunctionDef) or not node.name.startswith("test_"):
            continue
        allowed = any(
            (isinstance(inner, ast.Name) and inner.id == "ExitStack")
            or (isinstance(inner, ast.Attribute) and inner.attr in {"ExitStack", "context"})
            for inner in ast.walk(node)
        )
        hits = sum(
            1
            for call in ast.walk(node)
            if isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute) and call.func.attr in _JUDGMENTS
        )
        if hits > 1 and not allowed:
            offenders[node.name] = hits
    assert not offenders, f"以下用例在一次里做了多次门禁判定（判定之间未还原），会产生顺序假失败：{offenders}"


def test_subprocess_probes_compare_bytes_not_decoded_text() -> None:
    # AGENTS.md「探测子进程输出一律按字节比较」+「这类用例必须能单文件独立运行」：
    # 本仓门禁口径要求 PYTHONUTF8=1，而子进程在中文 Windows 上按码页发本地化消息，
    # text=True/encoding= 会让解码进入判定路径（reader 线程抛 UnicodeDecodeError → stdout=None）。
    offenders: list[int] = []
    for node in ast.walk(ast.parse(_read_this_file())):
        if not isinstance(node, ast.Call) or not (
            isinstance(node.func, ast.Attribute) and node.func.attr in {"run", "Popen", "check_output"}
        ):
            continue
        for kw in node.keywords:
            if kw.arg in {"text", "encoding", "universal_newlines"}:
                offenders.append(node.lineno)
    assert not offenders, f"子进程探测不得让解码参与判定（行 {offenders}）"


# B) ：未登记模块不再自动豁免


def test_new_src_module_is_gated_even_without_registered_threshold(tmp_path: Path) -> None:
    # 核心回归锁：把 evaluate_report 改回「只遍历 MODULE_THRESHOLDS」，本条立刻变红
    # （旧形态下 34 个 src/*.py 里只有 6 个被评，其余自动免检）。
    root = _make_root(tmp_path, ("src/brand_new.py",))
    rc = check_coverage.evaluate_report(_full_pass_report(), root)
    assert rc == 1, "src/brand_new.py 未出现在报告里却被放行 = 新增模块自动豁免（MID-2259 回归）"


def test_unregistered_module_below_global_floor_exits_1(tmp_path: Path) -> None:
    root = _make_root(tmp_path, ("src/brand_new.py",))
    floor = float(check_coverage.GLOBAL_FLOOR)
    percents = {module: 100.0 for module in _REGISTERED}
    percents["src/brand_new.py"] = floor - 1.0
    assert check_coverage.evaluate_report(_report(percents), root) == 1, "低于下限却放行：GLOBAL_FLOOR 未生效"


def test_unregistered_module_at_global_floor_passes(tmp_path: Path) -> None:
    # 与上一条分开成例：同一用例里两次判定会共用被 monkeypatch 改过的模块状态（见文件头）。
    # 恰好等于下限必须判达标（>= 语义），否则「按下限放水」这条规则本身就不可用。
    root = _make_root(tmp_path, ("src/brand_new.py",))
    percents = {module: 100.0 for module in _REGISTERED}
    percents["src/brand_new.py"] = float(check_coverage.GLOBAL_FLOOR)
    assert check_coverage.evaluate_report(_report(percents), root) == 0, "恰好等于下限应判达标（>= 语义）"


def test_registered_module_still_uses_its_own_higher_threshold(tmp_path: Path) -> None:
    # 反向锁：登记了 85% 的模块不得被 60% 的下限放水（否则「登记」这层毫无意义）。
    root = _make_root(tmp_path)
    ttwid_threshold = check_coverage.MODULE_THRESHOLDS["src/ttwid.py"]
    assert ttwid_threshold > check_coverage.GLOBAL_FLOOR, "用例前提失效：ttwid 阈值须高于全局下限"
    percents = {module: 100.0 for module in _REGISTERED}
    percents["src/ttwid.py"] = ttwid_threshold - 1.0
    assert check_coverage.evaluate_report(_report(percents), root) == 1


def test_exempt_module_does_not_block_the_gate(tmp_path: Path) -> None:
    # 豁免只作用于该模块自身，不得顺手放行别的缺口（否则白名单就成了总开关）。
    root = _make_root(tmp_path)
    percents = {module: 100.0 for module in _REGISTERED if module not in check_coverage.GATE_EXEMPT_MODULES}
    rc = check_coverage.evaluate_report(_report(percents), root)
    assert rc == 0, "被豁免模块缺席报告即判失败：豁免名单没起作用"


# A) / fail-closed：拿不到输入一律 rc=2 + 下一步命令


def test_empty_files_report_exits_2(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as excinfo:
        check_coverage.evaluate_report({"files": {}})
    assert excinfo.value.code == 2, "files 为空必须按「门禁没跑」处理，不得继续判定"
    err = capsys.readouterr().err
    assert "--cov=src" in err, f"rc=2 必须打印下一步命令: {err}"


def test_missing_data_file_exits_2(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as excinfo:
        check_coverage.check_coverage(data_file=str(tmp_path / "no-such-.coverage"), root=tmp_path)
    assert excinfo.value.code == 2
    assert "--cov=src" in capsys.readouterr().err


def test_root_without_src_dir_exits_2(tmp_path: Path) -> None:
    # 判定面为空（root 解析错位、src/ 被误删）→ 旧形态会打印「PASSED: All 0 module(s)」。
    with pytest.raises(SystemExit) as excinfo:
        check_coverage.evaluate_report(_report({"src/spider.py": 100.0}), tmp_path)
    assert excinfo.value.code == 2, "枚举不到任何模块却继续判定 = 空门禁自证通过"


def test_stale_table_entry_exits_2(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # 登记表指向不存在的模块（改名后的残留）→ 门禁配置腐烂，按 rc=2 而不是 rc=1：
    # 让人去改表，而不是误以为「补测试就能变绿」。
    root = _make_root(tmp_path)
    broken = dict(check_coverage.MODULE_THRESHOLDS)
    broken["src/renamed_away.py"] = 60.0
    monkeypatch.setattr(check_coverage, "MODULE_THRESHOLDS", broken)
    with pytest.raises(SystemExit) as excinfo:
        check_coverage.evaluate_report(_full_pass_report(), root)
    assert excinfo.value.code == 2
    assert "src/renamed_away.py" in capsys.readouterr().err


def test_stale_table_entry_exits_2_then_clean_table_passes(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    # 「rc=2 是因为那条坏键」而不是「这份报告本来就该 rc=2」——必须两次判定才能证明。
    # 还原用 ExitStack 当场完成：留给用例 teardown 会让第二次判定仍读到被改坏的表，
    # 于是本断言与上一条互相串味、失败原因指向错的地方。
    root = _make_root(tmp_path)
    report = _full_pass_report()
    broken = dict(check_coverage.MODULE_THRESHOLDS)
    broken["src/renamed_away.py"] = 60.0
    with contextlib.ExitStack() as stack:
        patch = stack.enter_context(pytest.MonkeyPatch.context())
        patch.setattr(check_coverage, "MODULE_THRESHOLDS", broken)
        with pytest.raises(SystemExit) as excinfo:
            check_coverage.evaluate_report(report, root)
        assert excinfo.value.code == 2
        assert "src/renamed_away.py" in capsys.readouterr().err
    assert check_coverage.evaluate_report(report, root) == 0, "还原真表后仍 rc!=0：rc=2 的归因不成立（坏键以外的原因）"


def test_unparseable_report_exits_2(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # 「数据文件在、coverage json 生成失败」这一类必须走 rc=2（该明列的第三形态）。
    # 只桩 coverage 子进程这一层（返回非 0、且不落 JSON），判定逻辑仍走真实实现。
    root = _make_root(tmp_path)
    data = root / ".coverage"
    data.write_bytes(b"not-really-coverage-data")

    def fake_run(*args: Any, **kwargs: Any) -> Any:
        return subprocess.CompletedProcess(args=list(args), returncode=1, stdout="", stderr="no data")

    # 只换**门禁模块自己的** subprocess 全局引用，不动 stdlib 模块本体（patch subprocess
    # 会波及同进程 harness 的守护线程与其它用例，AGENTS.md「patch main 的 subprocess」同族约定）。
    shim = types.SimpleNamespace(**vars(subprocess))
    shim.run = fake_run
    monkeypatch.setattr(check_coverage, "subprocess", cast(types.SimpleNamespace, shim))
    with pytest.raises(SystemExit) as excinfo:
        check_coverage.check_coverage(data_file=str(data), root=root)
    assert excinfo.value.code == 2, "报告不可解析必须按「门禁没数据」处理，不得继续判定"
    assert "--cov=src" in capsys.readouterr().err


def test_missing_summary_counts_as_zero(tmp_path: Path) -> None:
    # 报告里有文件名条目却没有 summary（数据被截断）→ 按 0% 处理，绝不当满分。
    root = _make_root(tmp_path)
    report: dict[str, Any] = {"files": {module: {} for module in _REGISTERED}, "totals": {}}
    assert check_coverage.evaluate_report(report, root) == 1


# C) 该补：新鲜度


def _touch(path: Path, mtime: float) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("# data\n", encoding="utf-8")
    os.utime(path, (mtime, mtime))


def _freeze_tree(root: Path, mtime: float) -> None:
    # 把整棵伪造根的 mtime 统一钉到同一时刻。
    # 为什么必需：_make_root 刚写出的文件 mtime 是「现在」（本仓时钟已到 2026），
    # 而用例要模拟的是「数据 2023 年写好、之后源码被改」这种相对关系；
    # 不冻结就会让 _make_root 自己的写入把比较基准抬上去，陈旧/新鲜两条用例同时失真。
    for path in sorted(root.rglob("*")):
        if path.is_file():
            os.utime(path, (mtime, mtime))


def test_stale_diagnosis_names_the_newest_source_file(tmp_path: Path) -> None:
    # 只查诊断（不判 rc）：陈旧时必须点名**最新**那个文件，否则用户照着提示去重跑也找不到成因。
    root = _make_root(tmp_path)
    old = 1_700_000_000.0
    _freeze_tree(root, old)
    data = root / ".coverage"
    _touch(data, old)
    newer = root / "tests" / "test_fresh_case.py"
    _touch(newer, old + 600.0)

    stale = check_coverage._data_is_stale(data, root)
    assert stale is not None, "数据比源码陈旧却判为新鲜：陈旧门禁静默通过（MID-2261）"
    _data_mtime, culprit, _culprit_mtime = stale
    assert culprit == newer, f"陈旧诊断应点名最新的那个文件，实际 {culprit}"


def test_stale_data_file_exits_2(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # 这条必须**同时**桩掉 coverage 子进程并让它成功产出报告：否则 rc=2 会被
    # 「假 .coverage 生不出 JSON」那条分支顺带满足，把新鲜度判据整个删掉用例照样绿。
    # 现在成功路径就在眼前（报告合法、模块全覆盖、本可 rc=0），唯一能给出 rc=2 的就是新鲜度。
    root = _make_root(tmp_path)
    old = 1_700_000_000.0
    _freeze_tree(root, old)
    data = root / ".coverage"
    _touch(data, old)
    _touch(root / "tests" / "test_fresh_case.py", old + 600.0)

    def fake_run(*args: Any, **kwargs: Any) -> Any:
        # 假装 `coverage json -o <tmp>` 成功并写出「全部达标」的合法报告
        cmd = list(args)
        out = Path(cmd[cmd.index("-o") + 1])
        out.write_text(json.dumps(_full_pass_report()), encoding="utf-8")
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")

    shim = types.SimpleNamespace(**vars(subprocess))
    shim.run = fake_run
    monkeypatch.setattr(check_coverage, "subprocess", cast(types.SimpleNamespace, shim))

    with pytest.raises(SystemExit) as excinfo:
        check_coverage.check_coverage(data_file=str(data), root=root)
    assert excinfo.value.code == 2
    err = capsys.readouterr().err
    assert "陈旧" in err, f"必须指明成因是数据陈旧，而不是笼统报「没数据」: {err}"
    assert "--cov=src" in err, "陈旧也必须给重跑命令，否则用户不知道下一步做什么"


def test_stale_check_covers_tests_dir_not_only_src(tmp_path: Path) -> None:
    # 只比 src/ 会漏掉「仅改用例后拿旧数据判门禁」这一半形态：
    # 新增/删除用例同样让 .coverage 的读数失去代表性。
    root = _make_root(tmp_path)
    old = 1_700_000_000.0
    _freeze_tree(root, old)
    data = root / ".coverage"
    _touch(data, old)
    _touch(root / "tests" / "test_only_case_changed.py", old + 60.0)
    assert check_coverage._data_is_stale(data, root) is not None


def test_fresh_data_file_is_not_flagged(tmp_path: Path) -> None:
    root = _make_root(tmp_path)
    old = 1_700_000_000.0
    _freeze_tree(root, old)
    data = root / ".coverage"
    _touch(data, old + 60.0)
    assert check_coverage._data_is_stale(data, root) is None, "数据比源码更新却被判陈旧：门禁无法在正常流程下变绿"


# D) 审查 6.7 的尾部匹配收紧（防同名顶替）


def test_find_module_coverage_rejects_tests_only_key(tmp_path: Path) -> None:
    root = _make_root(tmp_path)
    report = _report({"tests/utils.py": 99.5})
    assert (
        check_coverage._find_module_coverage(report, "src/utils.py") is None
    ), "tests/utils.py 顶替了 src/utils.py 的读数（6.7 的形态回来了）"


def test_tests_only_report_exits_1(tmp_path: Path) -> None:
    # 顶替不成立时整份报告必须整体判失败，而不是「查不到就算过」。
    root = _make_root(tmp_path)
    assert check_coverage.evaluate_report(_report({"tests/utils.py": 99.5}), root) == 1


def test_windows_backslash_report_keys_match(tmp_path: Path) -> None:
    # 正向锁：收紧匹配不得把合法形态一起杀掉——coverage json 在 Windows 上就是反斜杠键。
    root = _make_root(tmp_path)
    assert (
        check_coverage.evaluate_report(_report({module: 100.0 for module in _REGISTERED}, backslash_keys=True), root)
        == 0
    )


def test_absolute_ci_report_keys_match(tmp_path: Path) -> None:
    # CI（Linux runner）上 coverage 写绝对路径键，尾部匹配规则同样必须命中。
    root = _make_root(tmp_path)
    absolute = _report({f"/__w/repo/{module}": 100.0 for module in _REGISTERED})
    assert check_coverage.evaluate_report(absolute, root) == 0


def test_real_src_tree_enumeration_is_populated_and_classified() -> None:
    # 判定面见证：真仓 src/ 下确实被枚举到（不是 6 个、也不是 0 个），
    # 且每个模块都能拿到阈值或落进白名单——否则「全部模块」这句话说不上。
    modules = check_coverage._src_modules(ROOT)
    assert len(modules) >= 30, f"src/ 模块枚举异常（{len(modules)} 个），判定面可能已缩小"
    assert all(m.startswith("src/") and m.endswith(".py") for m in modules)
    for module in modules:
        threshold, source = check_coverage._threshold_for(module)
        assert 0 < threshold <= 100, f"{module} 的阈值异常: {threshold} ({source})"


# F) CLI 出口：三种 rc 都必须原样透出去


@pytest.mark.parametrize("gate_rc", [0, 1, 2])
def test_cli_main_exits_with_the_gate_rc(gate_rc: int, monkeypatch: pytest.MonkeyPatch) -> None:
    # 上面几条直调判定函数，这组锁 **CLI 出口**：main() 必须把 rc 原样 sys.exit 出去。
    # 若有人把 `sys.exit(check_coverage(...))` 改成 `return`，脚本会恒以 0 结束——
    # 门禁在 CI 里就变成一行装饰性输出（该想消灭的正是这一族）。
    # 这里只桩「取数据 + 判定」这一层（真实判定逻辑由上面各条分别锁），每个参数化实例只调一次
    # main()，因此不触发文件头的单次判定口径。
    seen: dict[str, Any] = {}

    def fake_check_coverage(data_file: str | None = None) -> int:
        seen["data_file"] = data_file
        return gate_rc

    monkeypatch.setattr(check_coverage, "check_coverage", fake_check_coverage)
    monkeypatch.setattr(sys, "argv", ["check_coverage.py", "--data-file", "given/path"])
    with pytest.raises(SystemExit) as excinfo:
        check_coverage.main()
    assert excinfo.value.code == gate_rc, f"rc={gate_rc} 未原样透出（退出码被改写 = 门禁被旁路）"
    assert seen["data_file"] == "given/path", "--data-file 必须透传到判定层"


def test_cli_entrypoint_propagates_rc2_for_unusable_data(tmp_path: Path) -> None:
    # 真实子进程跑一遍脚本，锁「rc=2 真的成了进程退出码」——in-process 那组只能证 sys.exit
    # 被调用，证不了 SystemExit 未被某处 except 吞掉。
    # 输出**按字节**判定（不用 text=True/encoding=）：中文 Windows 下子进程 stderr 是码页
    # 编码的本地化文本，让解码进入判定路径就会在 UTF-8 门禁下炸 reader 线程。
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "check_coverage.py"), "--data-file", str(tmp_path / "absent")],
        capture_output=True,
        stdin=subprocess.DEVNULL,
        cwd=ROOT,
        check=False,
    )
    assert proc.returncode == 2, f"CLI 未透出门禁失效码：rc={proc.returncode}\n{proc.stdout!r}\n{proc.stderr!r}"
    assert b"--cov=src" in proc.stderr, proc.stderr


# G) 该白名单分层（登记阈值 > 债务基线 > 全局下限；豁免另设机检）
#    组织口径沿用本文件：一个用例只做一次门禁判定；纯校验器逻辑直接调
#    _validate_debt_and_exempt(today=…) 注入固定日期，不依赖真实时钟。


def _debt(floor: float = 20.0, tracker: str = "CODE_REVIEW_2026-09-22_3.md §7-2", review_by: str = "2099-01-01") -> Any:
    return check_coverage.DebtEntry(floor=floor, reason="离线用例构造", tracker=tracker, review_by=review_by)


def test_debt_baseline_floor_is_applied(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # 债务基线要真的参与判定：30% 低于全局下限 50%、但高于登记基线 20% → 放行。
    root = _make_root(tmp_path, ("src/debt_mod.py",))
    monkeypatch.setattr(check_coverage, "COVERAGE_DEBT", {"src/debt_mod.py": _debt(20.0)})
    monkeypatch.setattr(check_coverage, "DEBT_CEILING", 1)  # 抬到 1：让 rc 只反映被测的那条规则，不与条数上限纠缠
    percents = {module: 100.0 for module in _REGISTERED}
    percents["src/debt_mod.py"] = 30.0
    assert check_coverage.evaluate_report(_report(percents), root) == 0, "债务基线未参与判定（仍按下限杀）"


def test_debt_baseline_blocks_regression(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # 棘轮的另一半：从基线再往下掉必须红（表只用于记录已知缺口，不是免死金牌）。
    root = _make_root(tmp_path, ("src/debt_mod.py",))
    monkeypatch.setattr(check_coverage, "COVERAGE_DEBT", {"src/debt_mod.py": _debt(20.0)})
    monkeypatch.setattr(check_coverage, "DEBT_CEILING", 1)
    percents = {module: 100.0 for module in _REGISTERED}
    percents["src/debt_mod.py"] = 10.0
    assert check_coverage.evaluate_report(_report(percents), root) == 1, "低于债务基线仍放行 = 只降不升失效"


def test_debt_entry_shadowing_a_passing_module_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # 已达全局下限却仍躺在表里 = 给未来退化预留合法空间，必须红（否则会长期滞留）。
    root = _make_root(tmp_path, ("src/debt_mod.py",))
    monkeypatch.setattr(check_coverage, "COVERAGE_DEBT", {"src/debt_mod.py": _debt(20.0)})
    monkeypatch.setattr(check_coverage, "DEBT_CEILING", 1)
    percents = {module: 100.0 for module in _REGISTERED}
    percents["src/debt_mod.py"] = 90.0
    assert check_coverage.evaluate_report(_report(percents), root) == 1, "达标模块未从债务表移出却被放行"


def test_debt_key_absent_from_src_exits_2(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # 表指向不存在的模块属「门禁配置腐烂」，与「不达标」不同类 → rc=2 逼人去改表。
    root = _make_root(tmp_path, ("src/debt_mod.py",))
    monkeypatch.setattr(check_coverage, "COVERAGE_DEBT", {"src/renamed_away.py": _debt(20.0)})
    with pytest.raises(SystemExit) as exc:
        check_coverage.evaluate_report(_full_pass_report(), root)
    assert exc.value.code == 2


def test_debt_missing_tracker_is_config_untrustworthy(tmp_path: Path) -> None:
    # tracker 必须是报告条目指针：没有出处的豁免迟早变成无人敢删的账。
    root = _make_root(tmp_path, ("src/debt_mod.py",))
    bad = _debt(20.0, tracker="TODO 后面再看")
    errors, violations = check_coverage._validate_debt_and_exempt(root, today="2026-09-23")
    assert not errors and not violations, "空表不应报问题"
    monkey = check_coverage.COVERAGE_DEBT
    try:
        check_coverage.COVERAGE_DEBT = {"src/debt_mod.py": bad}
        errors, _v = check_coverage._validate_debt_and_exempt(root, today="2026-09-23")
    finally:
        check_coverage.COVERAGE_DEBT = monkey
    assert errors, "tracker 不合规格却未判为配置不可信"


def test_debt_expired_review_date_is_a_violation(tmp_path: Path) -> None:
    root = _make_root(tmp_path, ("src/debt_mod.py",))
    entry = _debt(20.0, review_by="2026-01-01")
    saved = check_coverage.COVERAGE_DEBT
    try:
        check_coverage.COVERAGE_DEBT = {"src/debt_mod.py": entry}
        _e, violations = check_coverage._validate_debt_and_exempt(root, today="2026-09-23")
    finally:
        check_coverage.COVERAGE_DEBT = saved
    assert any("到期" in line for line in violations), f"到期未复核必须是违规：{violations}"


def test_debt_floor_must_stay_below_global_floor(tmp_path: Path) -> None:
    # 基线 ≥ 全局下限时，表就把一个本该达标的模块洗成「已登记」——无意义且掩盖退化。
    root = _make_root(tmp_path, ("src/debt_mod.py",))
    saved = check_coverage.COVERAGE_DEBT
    try:
        check_coverage.COVERAGE_DEBT = {"src/debt_mod.py": _debt(check_coverage.GLOBAL_FLOOR)}
        _e, violations = check_coverage._validate_debt_and_exempt(root, today="2026-09-23")
    finally:
        check_coverage.COVERAGE_DEBT = saved
    assert any("不得低于全局下限" in line for line in violations), f"基线不低于下限应报违规：{violations}"


def test_debt_count_cannot_exceed_ceiling(tmp_path: Path) -> None:
    root = _make_root(tmp_path, ("src/debt_mod.py",))
    saved_debt = check_coverage.COVERAGE_DEBT
    saved_ceiling = check_coverage.DEBT_CEILING
    try:
        check_coverage.DEBT_CEILING = 0
        check_coverage.COVERAGE_DEBT = {"src/debt_mod.py": _debt(20.0)}
        _e, violations = check_coverage._validate_debt_and_exempt(root, today="2026-09-23")
    finally:
        check_coverage.COVERAGE_DEBT = saved_debt
        check_coverage.DEBT_CEILING = saved_ceiling
    assert any("超过上限" in line for line in violations), f"条目数超上限必须违规：{violations}"


def test_exempt_claiming_generated_code_is_machine_checked() -> None:
    # 理由写「生成物」就得真在文件里找到生成器标记，否则就是拿一句注释把人写模块洗出门禁。
    # 取真实仓库根 + 一个确定手写、且不含 GENERATED_MARKERS 任一标记的模块（src/proxy.py）：
    # 核对只对 ROOT 生效（tmp 桩树里是占位文件，核对它必然假阳性）。
    saved = check_coverage.GATE_EXEMPT_MODULES
    try:
        check_coverage.GATE_EXEMPT_MODULES = {"src/proxy.py": "protoc 生成物（DO NOT EDIT，不参与人工补测）"}
        errors, _v = check_coverage._validate_debt_and_exempt(ROOT)
    finally:
        check_coverage.GATE_EXEMPT_MODULES = saved
    assert any("虚报豁免" in line for line in errors), f"虚报生成物须判配置不可信：{errors}"


def test_shipped_exempt_stub_really_carries_the_marker() -> None:
    # 反向锁：机检本身不能空转——出厂那条豁免必须真命中一个标记，
    # 否则上面那条「虚报生成物」的用例只是恰好匹配到空文件。
    for module, reason in check_coverage.GATE_EXEMPT_MODULES.items():
        if "生成物" not in reason:
            continue
        text = (ROOT / module).read_text(encoding="utf-8-sig", errors="replace")
        assert any(marker in text for marker in check_coverage.GENERATED_MARKERS), module


def test_debt_table_is_empty_by_design() -> None:
    # 2026-09-23 实测读数：`_src_modules(ROOT)` 得 43 个 src 模块 = 42 达标 + 1 个 protoc 桩豁免，
    # 没有任何模块需要债务基线（读数随 src/ 增删漂移，复核跑同一函数即可）。
    # 这条把「表为空」钉成事实：将来加条目时必须显式上调 DEBT_CEILING 并在此注明理由。
    assert check_coverage.COVERAGE_DEBT == {}, "债务基线表默认必须为空；新增条目须同步上调 DEBT_CEILING"
    assert check_coverage.DEBT_CEILING == 0
