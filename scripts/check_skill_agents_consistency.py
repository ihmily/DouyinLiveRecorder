# 校验 .agents/skills/ 下项目级 Skill 内容与 AGENTS.md 对应章节的一致性。
#
# 为什么需要单独一个检查：AGENTS.md「项目级 Skill」表是 Skill 与约束事实源之间的桥梁——
#   Skill 展开操作步骤，AGENTS.md 保留硬约束摘要。两侧手动维护，漂移是常态（新增/删除 Skill
#   忘改表、SKILL.md 引用的章节被重命名或删除、frontmatter name 与目录名不一致）。本脚本把
#   「表与目录不一致 / 引用断链」从静默漂移升级为硬失败。
#
# 检查项：
#   1. AGENTS.md「项目级 Skill」表条目 → 目录与 SKILL.md 必须存在
#   2. SKILL.md frontmatter name 必须与目录名一致
#   3. SKILL.md 必须声明 AGENTS.md 为约束事实源
#   4. SKILL.md 引用的 AGENTS.md 章节标题必须实际存在
#   5. .agents/skills/ 下存在但未被 AGENTS.md 表登记的项目级 Skill 目录（硬失败）
#      曾为「只告警 rc=0」：告警形态在真实漂移（三个已合并删除的旧 Skill 目录随坏提交回流）
#      面前仍返回 0，等于同源锁不自证——违 AGENTS「告警即失败」同回路判定。
#
# 用法：
#   python scripts/check_skill_agents_consistency.py
#
# 退出码：0 一致；1 存在不一致；2 脚本自身失效（文件缺失 / 解析失败）。

from __future__ import annotations

import re
import sys
from pathlib import Path

# 项目根目录（脚本在 scripts/ 下，上一级即根）
_REPO_ROOT = Path(__file__).resolve().parent.parent
_AGENTS_MD = _REPO_ROOT / "AGENTS.md"
_SKILLS_DIR = _REPO_ROOT / ".agents" / "skills"

# AGENTS.md 中「项目级 Skill」表格的解析状态机
# 表格有 4 列：| Skill | 路径 | 触发词 / 场景 | 覆盖领域 |
_TABLE_HEADER_RE = re.compile(r"^\|\s*Skill\s*\|\s*路径\s*\|", re.MULTILINE)
_TABLE_ROW_RE = re.compile(
    r"^\|\s*(?P<name>.+?)\s*\|\s*`(?P<path>.+?)`\s*\|\s*(?P<triggers>.+?)\s*\|\s*(?P<coverage>.+?)\s*\|",
    re.MULTILINE,
)
_TABLE_SEPARATOR_RE = re.compile(r"^\|\s*---")


def _parse_agents_skill_table(agents_text: str) -> list[dict[str, str]]:
    # 提取 AGENTS.md「项目级 Skill」表格中的条目
    header_match = _TABLE_HEADER_RE.search(agents_text)
    if not header_match:
        return []
    table_start = header_match.end()
    # 跳过分隔行（| --- | --- | --- |）
    rest = agents_text[table_start:]
    sep_match = _TABLE_SEPARATOR_RE.match(rest)
    if sep_match:
        rest = rest[sep_match.end() :]
    entries: list[dict[str, str]] = []
    for m in _TABLE_ROW_RE.finditer(rest):
        # 遇到非表格行（空行 / 新标题）即停
        line_start = rest.rfind("\n", 0, m.start()) + 1
        line = rest[line_start : m.end()]
        if not line.startswith("|"):
            break
        # 路径必须以 .agents/skills/ 开头（避免误匹配后续其他表格）
        path_val = m.group("path").strip()
        if not path_val.startswith(".agents/skills/"):
            break
        entries.append(
            {
                "display_name": m.group("name").strip(),
                "path": path_val,
                "coverage": m.group("coverage").strip(),
            }
        )
    return entries


def _parse_frontmatter(skill_md_text: str) -> dict[str, str]:
    # 解析 YAML frontmatter（--- 包围的头部）
    if not skill_md_text.startswith("---"):
        return {}
    end = skill_md_text.find("---", 3)
    if end == -1:
        return {}
    fm_block = skill_md_text[3:end].strip()
    result: dict[str, str] = {}
    current_key: str | None = None
    current_val_lines: list[str] = []
    for line in fm_block.splitlines():
        # 新键（非缩进行且含冒号）
        key_match = re.match(r"^([a-zA-Z_]\w*)\s*:\s*(.*)", line)
        if key_match:
            if current_key is not None:
                result[current_key] = " ".join(current_val_lines).strip()
            current_key = key_match.group(1)
            current_val_lines = [key_match.group(2)]
        elif current_key is not None and line.startswith(("  ", "\t", ">")):
            # 续行（YAML 多行字符串的 > 或缩进续行）
            current_val_lines.append(line.strip().lstrip(">").strip())
    if current_key is not None:
        result[current_key] = " ".join(current_val_lines).strip()
    return result


def _extract_agents_section_headers(agents_text: str) -> list[str]:
    # 提取 AGENTS.md 中所有 ## 和 ### 标题
    headers: list[str] = []
    for m in re.finditer(r"^(#{2,3})\s+(.+)$", agents_text, re.MULTILINE):
        headers.append(m.group(2).strip())
    return headers


def _extract_skill_referenced_sections(skill_md_text: str) -> list[str]:
    # 从 SKILL.md 中提取它声称引用的 AGENTS.md 章节关键词
    # 匹配模式：`AGENTS.md`「...」 或 `AGENTS.md` 的 "..." 章节引用
    refs: list[str] = []
    seen: set[str] = set()
    # 中文书名号引用：AGENTS.md「已知坑 → xxx」或 AGENTS.md「xxx」
    for m in re.finditer(r"AGENTS\.md[`'」\s]*[「\"']([^」\"']+)[」\"']", skill_md_text):
        ref = m.group(1).strip()
        if ref not in seen:
            refs.append(ref)
            seen.add(ref)
    # 也匹配「约束事实源」行里的章节路径
    for m in re.finditer(r"约束事实源.*?AGENTS\.md[^\n]*?[「\"']([^」\"']+)[」\"']", skill_md_text):
        ref = m.group(1).strip()
        if ref not in seen:
            refs.append(ref)
            seen.add(ref)
    return refs


def _check_section_ref_exists(ref_text: str, headers: list[str]) -> bool:
    # 检查引用文本是否能匹配到某个 AGENTS.md 标题
    # 引用可能是「已知坑 → ffmpeg 命令构造与容器格式」这种路径形式
    # 取最后一段（→ 分隔后的末段）做精确匹配
    parts = re.split(r"[→►]", ref_text)
    target = parts[-1].strip()
    if not target:
        return False
    # 精确匹配（标题必须完全等于目标，或以目标开头且紧接括号/冒号等标点）
    for header in headers:
        if header == target:
            return True
        # 允许标题以目标开头但后续只是括号补充（如「已知坑（避免回归）」匹配「已知坑」）
        if header.startswith(target) and len(header) > len(target):
            next_char = header[len(target)]
            if next_char in "（(：:、，, ":
                return True
    return False


def ensure_utf8_streams() -> None:
    # 把本进程 stdout/stderr 固定为 UTF-8 且显式给 errors：本脚本的成功/失败汇总行含
    # U+2713/U+2717（✓/✗），中文 Windows 控制台默认 cp936 编不出这两个码点 → print 抛
    # UnicodeEncodeError 炸掉脚本本身；pre-commit 侧不像 run_gates 会给子进程注入 PYTHONUTF8=1，
    # 故接进门禁链后必现。与 run_gates、agent_hook_guard 的同名函数同根因同手法；
    # errors="replace" 只兜底显示，绝不允许「输出失败」升级成「门禁没有结论」。
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if not callable(reconfigure):
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except ValueError, OSError:
            # 已被重定向到已关闭/非法句柄时静默放过：本函数只改善输出，不参与判定。
            pass


def main() -> int:
    ensure_utf8_streams()
    if not _AGENTS_MD.is_file():
        print(f"[ERROR] AGENTS.md 不存在: {_AGENTS_MD}", file=sys.stderr)
        return 2
    if not _SKILLS_DIR.is_dir():
        print(f"[ERROR] skills 目录不存在: {_SKILLS_DIR}", file=sys.stderr)
        return 2

    agents_text = _AGENTS_MD.read_text(encoding="utf-8")
    table_entries = _parse_agents_skill_table(agents_text)
    if not table_entries:
        print("[ERROR] AGENTS.md 中未找到「项目级 Skill」表格", file=sys.stderr)
        return 2

    agents_headers = _extract_agents_section_headers(agents_text)
    errors: list[str] = []
    warnings: list[str] = []
    referenced_dirs: set[str] = set()

    for entry in table_entries:
        display_name = entry["display_name"]
        rel_path = entry["path"]
        # 规范化路径（去掉尾部斜杠）
        rel_path_clean = rel_path.rstrip("/")
        skill_dir = _REPO_ROOT / rel_path_clean
        referenced_dirs.add(rel_path_clean)

        # 检查 1: 目录必须存在
        if not skill_dir.is_dir():
            errors.append(f"[FAIL] 表格条目「{display_name}」的路径不存在: {rel_path}")
            continue

        skill_md = skill_dir / "SKILL.md"
        # 检查 1b: SKILL.md 必须存在
        if not skill_md.is_file():
            errors.append(f"[FAIL] 目录存在但缺少 SKILL.md: {rel_path_clean}/SKILL.md")
            continue

        skill_text = skill_md.read_text(encoding="utf-8")
        fm = _parse_frontmatter(skill_text)
        dir_name = skill_dir.name

        # 检查 2: frontmatter name 必须与目录名一致
        fm_name = fm.get("name", "")
        if fm_name and fm_name != dir_name:
            errors.append(
                f"[FAIL] {rel_path_clean}/SKILL.md frontmatter name='{fm_name}' " f"与目录名 '{dir_name}' 不一致"
            )
        elif not fm_name:
            errors.append(f"[FAIL] {rel_path_clean}/SKILL.md 缺少 frontmatter name 字段")

        # 检查 3: SKILL.md 必须声明 AGENTS.md 为约束事实源
        # 例外：明确标注为「外部工具技能」的条目不要求引用 AGENTS.md
        is_external = "外部" in display_name or "非本仓" in display_name
        if not is_external:
            if "AGENTS.md" not in skill_text:
                errors.append(f"[FAIL] {rel_path_clean}/SKILL.md 未引用 AGENTS.md 作为约束事实源")
            elif "约束事实源" not in skill_text and "事实源" not in skill_text:
                warnings.append(f"[WARN] {rel_path_clean}/SKILL.md 引用了 AGENTS.md 但未标注「约束事实源」")

        # 检查 4: SKILL.md 引用的 AGENTS.md 章节必须存在
        refs = _extract_skill_referenced_sections(skill_text)
        for ref in refs:
            if not _check_section_ref_exists(ref, agents_headers):
                errors.append(f"[FAIL] {rel_path_clean}/SKILL.md 引用的 AGENTS.md 章节「{ref}」不存在")

    # 检查 5: 未被 AGENTS.md 表登记的项目级 Skill 目录（告警）
    # 只检查含 SKILL.md 且 frontmatter 声明了 name 的目录
    if _SKILLS_DIR.is_dir():
        for child in sorted(_SKILLS_DIR.iterdir()):
            if not child.is_dir():
                continue
            child_skill_md = child / "SKILL.md"
            if not child_skill_md.is_file():
                continue
            child_rel = f".agents/skills/{child.name}/"
            if child_rel.rstrip("/") not in referenced_dirs:
                # 读 frontmatter 判断是否是项目级 Skill（排除第三方/ marketplace 安装的）
                child_text = child_skill_md.read_text(encoding="utf-8")
                # 如果 SKILL.md 内引用了 AGENTS.md 作为事实源，说明它是项目级 Skill
                if "约束事实源" in child_text and "AGENTS.md" in child_text:
                    errors.append(f"[FAIL] 项目级 Skill 目录存在但未在 AGENTS.md 表格登记: " f"{child_rel}")

    # 输出结果
    for w in warnings:
        print(w)
    for e in errors:
        print(e)

    if errors:
        print(f"\n✗ 发现 {len(errors)} 个错误、{len(warnings)} 个警告")
        return 1
    elif warnings:
        print(f"\n✓ 无错误，{len(warnings)} 个警告")
        return 0
    else:
        print(f"\n✓ 全部 {len(table_entries)} 个 Skill 条目与 AGENTS.md 一致")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
