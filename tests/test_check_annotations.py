# scripts/check_annotations.py「符号可达性检查」与 --snapshot 防呆的回归用例。
#
# 本文件锁三件事：
#   1) 真能报：留下调用点但全仓无绑定的名字必须被点名（含文件与行号）；
#   2) 不误报：导入 / def / 参数 / 内建 / dunder 一律放行——判据是「宁漏勿噪」，
#      误报会让门禁天天红、反而被忽略；
#   3) 当前仓库零悬空引用：谁删了模块级符号留下调用点，本条立刻变红（端到端回路锁）。
#
# 另覆盖 `_reject_dangerous_baseline`（M-23）：它防的是误把家目录 / 系统目录 / 仓库根本体
# 当基线目录、被 shutil.rmtree 整棵删掉，故两个方向都必须成立——危险输入逐个拒绝，
# 工作区子目录（如 `<仓库根>/.workbuddy/ast-baseline`）必须放行；旧判据
# `home in resolved.parents` 在家目录检出下会把后者一起误拒，功能在常见布局下不可用。
# 用例一律把 home/cwd 打桩成 tmp_path 下的受控目录（不改 stdlib pathlib 本体），
# 判定与本机检出位置无关（Linux CI 与 Windows 同真）。
#
# 全部离线：只做 AST 扫描，不执行任何子进程。

from __future__ import annotations

import importlib.util
import os
import textwrap
from pathlib import Path
from types import ModuleType
from typing import Any, cast

import pytest

ROOT = Path(__file__).resolve().parent.parent


def _load_check_annotations() -> ModuleType:
    # 沿用仓内惯例（tests/test_run_gates.py）：scripts/ 不在包路径内，用
    # spec_from_file_location 显式加载，避免 sys.path 注入被 isort 重排到 import 之前
    spec = importlib.util.spec_from_file_location("_check_annotations_probe", ROOT / "scripts" / "check_annotations.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


check_annotations = _load_check_annotations()


def _write(root: Path, rel: str, source: str) -> None:
    # 按相对路径落盘（自动补父目录），源码统一 dedent 以便用例里缩进可读
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(source), encoding="utf-8")


def test_dangling_call_site_is_reported(tmp_path: Path) -> None:
    # 复现「定义已删除、调用点留在 `and` 右侧」的形态：短路会在多数场景遮住它，肉眼易误判
    _write(
        tmp_path,
        "pkg/mod.py",
        """
        # 模块头注释


        def caller(flag: bool) -> bool:
            return flag and missing_symbol(1)
        """,
    )
    _scanned, problems = check_annotations.check_dangling_symbols(tmp_path)
    assert len(problems) == 1, f"应只报一处悬空引用：{problems}"
    assert "missing_symbol" in problems[0]
    assert problems[0].startswith("pkg/mod.py:"), f"违规描述须带相对路径与行号：{problems[0]}"


def test_bound_builtin_and_dunder_names_are_not_reported(tmp_path: Path) -> None:
    # 宁漏勿噪：导入名 / def 名 / 参数 / 内建 / dunder 都不得报（否则门禁会被误报淹没）
    _write(
        tmp_path,
        "pkg/mod.py",
        """
        # 模块头注释

        import os

        CONSTANT = 1


        def helper(value: int) -> int:
            name = __name__
            return value + len(name) + CONSTANT + len(os.getcwd())
        """,
    )
    _scanned, problems = check_annotations.check_dangling_symbols(tmp_path)
    assert problems == [], f"有来源的名字不得报悬空：{problems}"


def test_wildcard_dynamic_injection_is_not_reported(tmp_path: Path) -> None:
    # 同仓另一处存在同名绑定时放行：覆盖 `from x import *` / monkeypatch / globals() 注入
    _write(tmp_path, "pkg/producer.py", "PLUGIN = 1\n")
    _write(
        tmp_path,
        "pkg/consumer.py",
        """
        # 模块头注释


        def use() -> int:
            return PLUGIN
        """,
    )
    _scanned, problems = check_annotations.check_dangling_symbols(tmp_path)
    assert problems == [], f"全仓别处有绑定的名字不得报悬空：{problems}"


def test_repository_has_no_dangling_symbols() -> None:
    # 端到端回路锁：本仓当前必须零悬空引用。谁删了模块级符号留下调用点，本条立刻变红，
    # 并会在门禁输出里收到「删前先 grep 全部调用点」的提示
    _scanned, problems = check_annotations.check_dangling_symbols(ROOT)
    assert problems == [], f"存在悬空引用：{problems}"


# --snapshot 基线目录防呆的判定表（M-23）
#
# 三个方向都要锁，缺一个都会让功能退化成另一种故障：
#   ① 工作区子目录放行——不锁则功能在家目录检出下依旧不可用；
#   ② 危险输入仍拒绝——rmtree 不可逆，削掉它比误拒更危险；
#   ③ 放行不得越界到「cwd 本体/祖先」与「cwd 就是家目录」两种入口形态。


def _fixed_layout_path(home: Path, cwd: Path) -> Any:
    # 只替换被测模块命名空间里的 Path 名字（不改 stdlib 本体，否则波及全进程）。
    # 基类取本机 flavour：Windows 上用 PosixPath 建目录名会把盘符当普通段处理，判定就失真。
    base_flavour: Any = type(Path())

    class _Fixed(base_flavour):  # type: ignore[misc]
        @classmethod
        def home(cls) -> Any:
            return base_flavour(str(home))

        @classmethod
        def cwd(cls) -> Any:
            return base_flavour(str(cwd))

    return _Fixed


def _reject_candidate(monkeypatch: pytest.MonkeyPatch, home: Path, cwd: Path, candidate: Path) -> str | None:
    # 单点驱动：装好受控 home/cwd 后调用防呆本身，返回 None 表示「放行」
    monkeypatch.setattr(check_annotations, "Path", _fixed_layout_path(home, cwd))
    # cast 而非直返：ModuleType 的属性访问是 Any，warn_return_any 下直返会报 no-any-return
    return cast("str | None", check_annotations._reject_dangerous_baseline(candidate))


@pytest.mark.parametrize("layout", ["under_home", "outside_home"], ids=lambda v: f"检出在{v}")
def test_snapshot_guard_accepts_workspace_subdir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, layout: str) -> None:
    # ① 工具自己提示的形态必须放行；under_home 那一格就是 M-23 的缺陷面（旧判据会误拒）。
    base = tmp_path.resolve()
    home = base / "home-user"
    repo = (home / "repos" / "DouyinLiveRecorder") if layout == "under_home" else (base / "work" / "DouyinLiveRecorder")
    verdict = _reject_candidate(monkeypatch, home, repo, repo / ".workbuddy" / "ast-baseline")
    assert verdict is None, f"工作区子目录被误拒：{verdict}"


def test_snapshot_guard_still_rejects_home_and_its_direct_levels(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # ② 家目录本体与其直接层级仍须拒绝：这两级才是「把一个人全部数据当基线目录」的入口，
    # M-23 只削到「直接层级」为止，不得再往下放。
    base = tmp_path.resolve()
    home = base / "home-user"
    for candidate, why in ((home, "家目录本体"), (home / "ast-baseline", "家目录直接层级")):
        verdict = _reject_candidate(monkeypatch, home, home / "repos" / "repo", candidate)
        assert verdict is not None, f"{why} 被放行 -> rmtree 会整棵删除 {candidate}"
        assert "主目录" in verdict, f"{why} 的拒绝理由须点名主目录：{verdict}"


def test_snapshot_guard_still_rejects_cwd_and_filesystem_root(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    # ② cwd 本体/祖先与文件系统根（Windows 盘符根）仍逐条拒绝——cwd 打桩在**不受家目录规则影响**
    # 的位置，才能确认这三条各自的拒绝理由，而不是被同一条兜住后误以为都测到了。
    base = tmp_path.resolve()
    home = base / "home-user"
    repo = base / "work" / "repo"
    anchor = str(base.anchor) or "/"
    for candidate, needle in (
        (repo, "当前工作目录"),
        (repo.parent, "当前工作目录"),
        (Path(anchor), "文件系统根"),
    ):
        verdict = _reject_candidate(monkeypatch, home, repo, candidate)
        assert verdict is not None and needle in verdict, f"{candidate} 的判定不符预期：{verdict!r}"


def test_snapshot_guard_still_rejects_system_dirs(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    # ② 系统目录：样本按 os.name 取**该侧真实存在**的形态（不是 skipif 跳过另一侧，
    # 见 AGENTS.md「平台专属分支的测试不得靠 skipif 让 CI 跳过」——两侧都要真跑一条）。
    base = tmp_path.resolve()
    home = base / "home-user"
    repo = base / "work" / "repo"
    sample = Path("C:/Windows/System32/drivers/etc") if os.name == "nt" else Path("/etc/ssl/private")
    verdict = _reject_candidate(monkeypatch, home, repo, sample)
    assert verdict is not None and "系统目录" in verdict, f"系统目录下的基线被放行：{verdict!r}"


@pytest.mark.parametrize(
    "outside",
    ["sibling_repo", "other_drive", "srv_data"],
    ids=["cwd外同级目录", "cwd外盘符", "cwd外绝对路径"],
)
def test_snapshot_guard_rejects_any_target_outside_cwd(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, outside: str
) -> None:
    # S-13：旧实现是排除式黑名单——不在任何一条拒绝规则里的路径落到函数末尾
    # 的 `return None` 被放行，于是 `--snapshot D:\OtherRepo` / `/srv/data` 会 rmtree 整棵无关
    # 目录树。本用例钉的是**白名单正向判定**：cwd 之外的任何绝对路径都必须被拒绝。
    base = tmp_path.resolve()
    home = base / "home-user"
    repo = base / "work" / "repo"
    candidate = {
        "sibling_repo": base / "work" / "OtherRepo",
        "other_drive": Path(str(base.anchor) or "/") / "backup",
        "srv_data": Path("/srv/data") if os.name != "nt" else Path("D:/srv/data"),
    }[outside]
    verdict = _reject_candidate(monkeypatch, home, repo, candidate)
    assert verdict is not None, f"cwd 之外的路径被放行 -> rmtree 会整棵删除 {candidate}"


def test_snapshot_guard_carve_out_does_not_apply_when_cwd_is_home(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # ③ 放行边界：cwd 恰好是家目录时（在 ~ 下直接跑脚本）不得把整棵家目录树声明成「工作区」。
    # 此刻家目录直接层级仍由主目录那条拦住；用例钉的是「这条拒绝必须存在且给出理由」。
    base = tmp_path.resolve()
    home = base / "home-user"
    verdict = _reject_candidate(monkeypatch, home, home, home / "ast-baseline")
    assert verdict is not None and "主目录" in verdict, f"cwd=家目录时工作区子目录被放行：{verdict!r}"
