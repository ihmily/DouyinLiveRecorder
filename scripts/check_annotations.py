#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 注释规范检查与「逻辑等价性」校验工具（CI 可调用）
#
# 提供三种模式，覆盖两类不同需求：
#
#   1) 规范检查（默认，无需基线）：扫描源码，检查本仓的注释约定是否被遵守
#      - 禁止三引号 docstring（AGENTS.md 硬性约定：注释统一用 `#`）
#      - 注释密度不得低于阈值（默认 13%）
#      - 每个模块必须有模块头注释（前 30 行内）
#      适合作为常驻 CI 门禁，随时可跑。
#
#   2) 基线快照（--snapshot DIR）：把当前文件复制到 DIR 作为基线。
#
#   3) 等价性校验（--baseline DIR）：证明「只改了注释、没改逻辑」。
#      Python 文件比对 ast.dump 全量序列化；JS/CSS/HTML 剥离注释后比对有效代码行。
#      适合在大批量「只改注释/格式」的改动前后使用。
#
# 为什么用 ast.dump 而不是逐行 diff：注释不进入抽象语法树，而三引号 docstring
# 会作为 Expr 节点进入 AST。因此 AST 全等可同时证明两件事——
#   ① 可执行逻辑一字未动；② 没有误插 docstring。
#
# 已知盲点（AST 校验发现不了，须另行检查）：
#   - `except A, B:`（PEP 758）与 `except (A, B):` 的 AST 完全相同，
#     故「无括号写法被改成带括号」不会被本工具发现，需 grep 计数核对。
#   - 注释缩进错误不影响 AST，只有 black 能发现。故本工具应与 black 配套使用。
#
# 用法示例：
#   python scripts/check_annotations.py                       # 规范检查
#   python scripts/check_annotations.py --min-density 15       # 收紧密度阈值
#   python scripts/check_annotations.py --snapshot  /tmp/base   # 建基线
#   python scripts/check_annotations.py --baseline  /tmp/base   # 等价性校验
#
# 退出码：0 全部通过；1 存在违规或逻辑改动。

from __future__ import annotations

import argparse
import ast
import io
import shutil
import sys
import tokenize
from pathlib import Path

# 默认注释密度下限（百分比）。该阈值与本项目既有高质量文件的密度对齐：
# src/stream_select.py 约 35%、src/scheduler.py 约 22%，多数文件在 13%~20% 区间。
DEFAULT_MIN_DENSITY = 13.0

# 模块头注释的判定范围：文件前 N 行内必须出现注释，否则视为缺模块头
MODULE_HEADER_SCAN_LINES = 30

# 不参与检查的目录（与 .gitignore / pyproject 各工具排除列表同源）
EXCLUDE_DIRS = (
    "__pycache__",
    ".git",
    ".venv",
    ".mypy_cache",
    ".pytest_cache",
    ".workbuddy",
    "node",
    "ffmpeg",
    "build",
    "dist",
    "downloads",
    "logs",
)

# 不参与检查的文件：protoc 生成物（自带 docstring 且标注 DO NOT EDIT）、
# 以及按项目决策跳过的历史遗留文件
EXCLUDE_FILES = frozenset(
    {
        "douyin_pb2.py",
        "douyin_live_recorder_standalone.py",
        "gui_legacy.py",
    }
)


def is_excluded(path: Path, root: Path) -> bool:
    # 判断路径是否命中排除规则（目录名或文件名）
    try:
        rel = path.relative_to(root)
    except ValueError:
        return True
    parts = rel.parts
    if any(part in EXCLUDE_DIRS for part in parts[:-1]):
        return True
    return path.name in EXCLUDE_FILES


def iter_source_files(root: Path) -> list[Path]:
    # 收集待检查文件：Python 源码 + web/ 下的前端资源
    found: list[Path] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or is_excluded(path, root):
            continue
        if path.suffix == ".py":
            found.append(path)
        elif path.suffix in (".js", ".css", ".html") and "web" in path.relative_to(root).parts[:1]:
            found.append(path)
    return found


def comment_density(src: str) -> float:
    # 精确统计注释行占比。用 tokenize 而非前缀匹配，避免把字符串里的 # 误判为注释
    lines = src.splitlines()
    if not lines:
        return 0.0
    comment_lines: set[int] = set()
    try:
        for tok in tokenize.generate_tokens(io.StringIO(src).readline):
            if tok.type == tokenize.COMMENT:
                comment_lines.add(tok.start[0])
    except tokenize.TokenError:
        # 语法无法解析时退化为行首匹配，保证工具自身不因此崩溃
        comment_lines = {i + 1 for i, line in enumerate(lines) if line.strip().startswith("#")}
    return len(comment_lines) / len(lines) * 100.0


def has_module_header(src: str) -> bool:
    # 模块头判定：前若干行内出现 # 注释。空文件（0 行）视为无需模块头
    head = src.splitlines()[:MODULE_HEADER_SCAN_LINES]
    if not head:
        return True
    return any(line.strip().startswith("#") for line in head)


def find_docstrings(src: str) -> list[str]:
    # 找出所有三引号 docstring 的位置（模块级/类级/函数级），返回可读描述
    violations: list[str] = []
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return violations

    def is_docstring(node: ast.AST) -> bool:
        # docstring 的判定：body 首个语句是纯字符串常量表达式
        body = getattr(node, "body", None)
        if not isinstance(body, list) or not body:
            return False
        first = body[0]
        return (
            isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) and isinstance(first.value.value, str)
        )

    if is_docstring(tree):
        violations.append("模块级 docstring")

    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and is_docstring(node):
            violations.append(f"类 {node.name} 的 docstring")
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and is_docstring(node):
            violations.append(f"函数 {node.name} 的 docstring")
    return violations


def strip_js_comments(src: str) -> list[str]:
    # 剥离 JS/CSS 的行注释与块注释，返回有效代码行序列（用于等价性比对）
    result: list[str] = []
    buf: list[str] = []
    in_block = False
    i, n = 0, len(src)
    while i < n:
        char = src[i]
        nxt = src[i + 1] if i + 1 < n else ""
        if in_block:
            if char == "*" and nxt == "/":
                in_block = False
                i += 2
                continue
            i += 1
            continue
        if char == "/" and nxt == "*":
            in_block = True
            i += 2
            continue
        if char == "/" and nxt == "/":
            while i < n and src[i] != "\n":
                i += 1
            continue
        if char == "\n":
            line = "".join(buf).strip()
            buf = []
            if line:
                result.append(line)
            i += 1
            continue
        buf.append(char)
        i += 1
    tail = "".join(buf).strip()
    if tail:
        result.append(tail)
    return result


def strip_html_comments(src: str) -> list[str]:
    # 剥离 HTML 的 <!-- --> 注释，返回有效代码行序列
    import re

    without_comments = re.sub(r"<!--.*?-->", "", src, flags=re.S)
    return [line.strip() for line in without_comments.splitlines() if line.strip()]


def code_signature(path: Path, src: str) -> object:
    # 计算文件的「逻辑签名」：Python 用 AST 序列化，前端用剥离注释后的代码行序列。
    # 注释与空行不参与，故该签名相同即代表可执行逻辑一致
    if path.suffix == ".py":
        return ast.dump(ast.parse(src), include_attributes=False)
    if path.suffix in (".js", ".css"):
        return strip_js_comments(src)
    if path.suffix == ".html":
        return strip_html_comments(src)
    return src


def check_conventions(root: Path, min_density: float) -> int:
    # 模式一：规范检查（无需基线）。返回违规数
    problems: list[str] = []
    stats: list[tuple[str, float]] = []

    for path in iter_source_files(root):
        rel = path.relative_to(root).as_posix()
        src = path.read_text(encoding="utf-8", errors="replace")

        for item in find_docstrings(src):
            problems.append(f"[docstring] {rel}: 存在{item}（AGENTS.md 要求注释统一用 #）")

        # 前端文件用 Python 的 tokenize 统计不准，故密度检查只对 Python 生效
        if path.suffix == ".py":
            density = comment_density(src)
            stats.append((rel, density))
            if density < min_density:
                problems.append(f"[密度] {rel}: {density:.1f}% 低于阈值 {min_density:.1f}%")
            if not has_module_header(src):
                problems.append(f"[模块头] {rel}: 前 {MODULE_HEADER_SCAN_LINES} 行内无说明注释")

    print("=" * 78)
    print(f"注释规范检查（阈值 {min_density:.1f}%）—— 共扫描 {len(stats)} 个 Python 文件")
    print("=" * 78)
    if problems:
        for item in problems:
            print(f"  {item}")
        print("-" * 78)
        print(f"发现 {len(problems)} 项违规")
    else:
        lowest = sorted(stats, key=lambda x: x[1])[:5]
        print("全部通过。密度最低的 5 个文件：")
        for rel, density in lowest:
            print(f"  {density:6.1f}%  {rel}")
        avg = sum(d for _, d in stats) / len(stats) if stats else 0.0
        print("-" * 78)
        print(f"平均注释密度 {avg:.1f}%")
    print("=" * 78)
    return len(problems)


def take_snapshot(root: Path, baseline: Path) -> int:
    # 模式二：建立基线快照，供后续等价性校验使用
    if baseline.exists():
        shutil.rmtree(baseline)
    count = 0
    for path in iter_source_files(root):
        rel = path.relative_to(root)
        dest = baseline / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, dest)
        count += 1
    print(f"已建立基线快照：{count} 个文件 -> {baseline}")
    return 0


def check_equivalence(root: Path, baseline: Path) -> int:
    # 模式三：与基线比对逻辑签名，证明「只改了注释」
    if not baseline.exists():
        print(f"错误：基线目录不存在 -> {baseline}", file=sys.stderr)
        return 1

    passed: list[tuple[str, float, float]] = []
    changed: list[tuple[str, str]] = []
    missing: list[str] = []

    for base_file in sorted(p for p in baseline.rglob("*") if p.is_file()):
        rel = base_file.relative_to(baseline)
        current = root / rel
        if not current.exists():
            missing.append(rel.as_posix())
            continue
        old_src = base_file.read_text(encoding="utf-8", errors="replace")
        new_src = current.read_text(encoding="utf-8", errors="replace")
        try:
            same = code_signature(current, old_src) == code_signature(current, new_src)
        except SyntaxError as exc:
            changed.append((rel.as_posix(), f"语法错误: {exc}"))
            continue
        if same:
            passed.append((rel.as_posix(), comment_density(old_src), comment_density(new_src)))
        else:
            changed.append((rel.as_posix(), "逻辑签名不一致 -> 疑似改动了可执行代码"))

    print("=" * 78)
    print(f"{'密度前':>7} {'密度后':>7} {'增量':>7}  文件")
    print("=" * 78)
    for rel_str, d0, d1 in sorted(passed, key=lambda x: -(x[2] - x[1])):
        print(f"{d0:6.1f}% {d1:6.1f}% {d1 - d0:+6.1f}%  {rel_str}")
    print("-" * 78)
    if passed:
        avg_before = sum(d0 for _, d0, _ in passed) / len(passed)
        avg_after = sum(d1 for _, _, d1 in passed) / len(passed)
        print(f"等价 {len(passed)} 个文件；平均密度 {avg_before:.1f}% -> {avg_after:.1f}%")
    if changed:
        print("\n!!! 以下文件存在逻辑改动，必须修复 !!!")
        for rel_str, why in changed:
            print(f"  [FAIL] {rel_str}: {why}")
    if missing:
        print("\n!!! 以下文件在基线中存在但当前缺失 !!!")
        for rel_str in missing:
            print(f"  [MISS] {rel_str}")
    print("=" * 78)
    return len(changed) + len(missing)


def main() -> int:
    # 入口：解析参数并分派到三种模式
    parser = argparse.ArgumentParser(
        description="注释规范检查与逻辑等价性校验工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent.parent, help="项目根目录")
    parser.add_argument("--min-density", type=float, default=DEFAULT_MIN_DENSITY, help="注释密度下限（百分比）")
    parser.add_argument("--snapshot", type=Path, default=None, help="建立基线快照到指定目录")
    parser.add_argument("--baseline", type=Path, default=None, help="与指定基线目录做等价性校验")
    args = parser.parse_args()

    root: Path = args.root.resolve()
    if args.snapshot is not None:
        return take_snapshot(root, args.snapshot.resolve())
    if args.baseline is not None:
        return check_equivalence(root, args.baseline.resolve())
    return 1 if check_conventions(root, args.min_density) > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
