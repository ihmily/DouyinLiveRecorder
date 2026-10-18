# scripts/check_skill_agents_consistency.py 的回归用例。
#
# 锁的是「门禁自身完整性」四条（对应 SR-06，docs/worklog/CODE_REVIEW_2026-10-04.md）：
#   1) .agents/skills/ 必须入库——该目录缺失时脚本退 2，而它是 required check `ci-summary`
#      的 needs 之一，干净检出上必然全链红；故用「.agents/* + !.agents/skills/」反选，
#      且不得退化回 `.agents/` 目录级排除（git 会停止下钻，反选即失效）。
#   2) 「目录缺失 = 门禁自身失效（2）」与「表格条目指向不存在路径 = 一致性不合格（1）」
#      必须是两档不同结论，后者不得被前者吞掉。
#   3) SKILL.md 的四条判据各自能单独转红：文件存在 / frontmatter name 与目录名对齐 /
#      声明 AGENTS.md 为约束事实源 / 引用的 AGENTS.md 章节实际存在。
#   4) 真实仓库面必须自证一致（AGENTS.md 表格 ↔ .agents/skills/ 目录）。
#
# 全部离线：一致性判定的用例一律在 tmp_path 造面后 monkeypatch 模块级常量，不触碰真实资产；
# 只有最后真实仓库面那条直接跑本机，因为它锁的正是「资产必须存在」这件事。

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parent.parent


def _load_checker() -> ModuleType:
    # 沿用仓内惯例（test_run_gates.py / test_i18n.py）：scripts/ 不在包路径内，用
    # spec_from_file_location 显式加载，避免 sys.path 注入被 isort 重排到 import 之前
    spec = importlib.util.spec_from_file_location(
        "_skill_consistency_probe", ROOT / "scripts" / "check_skill_agents_consistency.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


checker = _load_checker()

# 与脚本 _parse_agents_skill_table 的解析口径对齐：表头两列必须是「Skill | 路径」，
# 路径列用反引号包裹且以 .agents/skills/ 开头，否则该行不进条目
_AGENTS_HEAD = """# AGENTS.md

## 项目级 Skill

| Skill | 路径 | 触发词 / 场景 | 覆盖领域 |
| --- | --- | --- | --- |
"""


def _build_agents_md(rows: list[tuple[str, str]], extra_headers: tuple[str, ...] = ("已知坑",)) -> str:
    # 造一份最小但可被解析的 AGENTS.md：表格 + 若干 ## 章节（供「引用章节存在性」判定命中）
    lines = [_AGENTS_HEAD]
    for display, path in rows:
        lines.append(f"| {display} | `{path}` | 触发词 | 覆盖领域 |\n")
    for header in extra_headers:
        lines.append(f"\n## {header}\n")
    return "".join(lines)


def _build_skill_md(name: str, refs_agents: bool = True, section: str = "已知坑") -> str:
    # 造一份最小 SKILL.md；refs_agents=False 用于验证「未声明约束事实源」必须转红
    body = f"# {name}\n"
    if refs_agents:
        body += f"\n约束事实源：`AGENTS.md`「{section}」\n"
    return f"---\nname: {name}\ndescription: 触发词\n---\n\n{body}"


def _point_checker_at(monkeypatch: pytest.MonkeyPatch, root: Path) -> None:
    # main() 只消费这三个模块级常量，全部改指到 tmp_path 即可在离线面上跑真实判定逻辑
    monkeypatch.setattr(checker, "_REPO_ROOT", root)
    monkeypatch.setattr(checker, "_AGENTS_MD", root / "AGENTS.md")
    monkeypatch.setattr(checker, "_SKILLS_DIR", root / ".agents" / "skills")


def _make_skill(root: Path, dir_name: str, **kwargs: object) -> None:
    # 在 tmp_path 下造一个 Skill 目录；kwargs 透传给 _build_skill_md
    skill_dir = root / ".agents" / "skills" / dir_name
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        _build_skill_md(dir_name, **kwargs),  # type: ignore[arg-type]
        encoding="utf-8",
    )


def test_missing_skills_dir_is_rc2_not_silent_pass(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # 目录缺失必须仍是「门禁自身失效」(2)：资产已入库后，干净检出缺它说明检出/ignore 被改坏
    (tmp_path / "AGENTS.md").write_text(
        _build_agents_md([("DLR 开发手册", ".agents/skills/dlr-dev-playbook/")]),
        encoding="utf-8",
    )
    _point_checker_at(monkeypatch, tmp_path)
    assert checker.main() == 2


def test_missing_agents_md_is_rc2(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _point_checker_at(monkeypatch, tmp_path)
    assert checker.main() == 2


def test_table_entry_pointing_at_missing_dir_is_rc1(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # 与「目录缺失」分档：skills 目录存在但条目路径不存在 → 一致性不合格 (1)，不能被退 2 吞掉
    (tmp_path / ".agents" / "skills").mkdir(parents=True)
    (tmp_path / "AGENTS.md").write_text(
        _build_agents_md([("幽灵技能", ".agents/skills/ghost/")]),
        encoding="utf-8",
    )
    _point_checker_at(monkeypatch, tmp_path)
    assert checker.main() == 1


def test_skill_dir_without_skill_md_is_rc1(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / ".agents" / "skills" / "ghost").mkdir(parents=True)
    (tmp_path / "AGENTS.md").write_text(
        _build_agents_md([("幽灵技能", ".agents/skills/ghost/")]),
        encoding="utf-8",
    )
    _point_checker_at(monkeypatch, tmp_path)
    assert checker.main() == 1


def test_frontmatter_name_mismatch_is_rc1(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _make_skill(tmp_path, "dlr-dev-playbook")
    skill_md = tmp_path / ".agents" / "skills" / "dlr-dev-playbook" / "SKILL.md"
    skill_md.write_text(
        skill_md.read_text(encoding="utf-8").replace("name: dlr-dev-playbook", "name: 另一个名字"), encoding="utf-8"
    )
    (tmp_path / "AGENTS.md").write_text(
        _build_agents_md([("DLR 开发手册", ".agents/skills/dlr-dev-playbook/")]),
        encoding="utf-8",
    )
    _point_checker_at(monkeypatch, tmp_path)
    assert checker.main() == 1


def test_skill_md_without_agents_reference_is_rc1(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # 项目级 Skill 必须声明 AGENTS.md 为约束事实源，否则 Skill 会变成第二份事实源
    _make_skill(tmp_path, "some-skill", refs_agents=False)
    (tmp_path / "AGENTS.md").write_text(
        _build_agents_md([("某技能", ".agents/skills/some-skill/")]),
        encoding="utf-8",
    )
    _point_checker_at(monkeypatch, tmp_path)
    assert checker.main() == 1


def test_dangling_agents_section_reference_is_rc1(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # 引用了 AGENTS.md 里不存在的章节标题（章节被改名/删除后 Skill 会静默断链）
    _make_skill(tmp_path, "some-skill", section="早已删除的章节")
    (tmp_path / "AGENTS.md").write_text(
        _build_agents_md([("某技能", ".agents/skills/some-skill/")]),
        encoding="utf-8",
    )
    _point_checker_at(monkeypatch, tmp_path)
    assert checker.main() == 1


def test_external_skill_is_exempt_from_agents_reference(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # 展示名含「外部」的条目是第三方工具技能，不要求引用 AGENTS.md（脚本内的显式例外）
    _make_skill(tmp_path, "browser-skill", refs_agents=False)
    (tmp_path / "AGENTS.md").write_text(
        _build_agents_md([("BrowserSkill（外部工具技能，非本仓领域约定）", ".agents/skills/browser-skill/")]),
        encoding="utf-8",
    )
    _point_checker_at(monkeypatch, tmp_path)
    assert checker.main() == 0


def test_consistent_skill_is_rc0(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _make_skill(tmp_path, "dlr-dev-playbook")
    (tmp_path / "AGENTS.md").write_text(
        _build_agents_md([("DLR 开发手册", ".agents/skills/dlr-dev-playbook/")]),
        encoding="utf-8",
    )
    _point_checker_at(monkeypatch, tmp_path)
    assert checker.main() == 0
    assert "一致" in capsys.readouterr().out


def test_unregistered_skill_dir_emits_warning(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # 目录存在但未登记的方向至少必须可见（WARN 行）。[已知缺口] 该方向目前只进 warnings、
    # rc 仍 0（同批审查记录第 3.2 节），本用例只锁「可见性」，不锁退出码，留待收口时再收紧
    _make_skill(tmp_path, "orphan-skill")
    (tmp_path / "AGENTS.md").write_text(
        _build_agents_md([("DLR 开发手册", ".agents/skills/dlr-dev-playbook/")]),
        encoding="utf-8",
    )
    _point_checker_at(monkeypatch, tmp_path)
    checker.main()
    assert "未在 AGENTS.md 表格登记" in capsys.readouterr().out


def test_gitignore_reincludes_skills_dir_but_not_sibling_dirs() -> None:
    # 资产入库的写法锁：必须是「排除内容物 + 反选 skills」，写成 .agents/ 目录级排除会让
    # git 停止下钻、反选失效（git 不对已排除目录做逐文件匹配）——失效形态正是 SR-06 的原状
    raw = (ROOT / ".gitignore").read_bytes().decode("utf-8")
    lines = [line.strip() for line in raw.splitlines()]
    assert ".agents/*" in lines
    assert "!.agents/skills/" in lines
    assert ".agents/" not in lines


def test_real_repo_skill_table_matches_skills_dir() -> None:
    # 真实仓库面自证：资产已入库后这条在任何干净检出上都必须成立（CI 跑的正是这条判定）
    assert (ROOT / ".agents" / "skills").is_dir()
    assert checker.main() == 0
