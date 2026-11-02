#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 注释规范检查 + 逻辑等价性校验工具（CI 可调用，常驻门禁）
#
# 三种模式，对应两类互不相干的用途：
#
#   1) 规范检查（默认，无需基线）：本仓注释约定的机检面——不得有 docstring、
#      注释密度不低于阈值（默认 13%）、每个模块前 30 行内要有模块头注释。
#      约定本体见 AGENTS.md「注释约定」，这里只负责「违规即红」。
#
#   2) 基线快照（--snapshot DIR）：把待比对文件原样复制进 DIR，供模式 3 当基线。
#      DIR 必须是工作区子目录，防呆理由见 _reject_dangerous_baseline。
#
#   3) 等价性校验（--baseline DIR）：证明「只改了注释、没动逻辑」。
#      Python 比 ast.dump 全量序列化，JS/CSS/HTML 剥注释后比有效代码行；
#      批量「只改注释/格式」的改动前后各跑一次（模式 2 → 改 → 模式 3）。
#
#   另含一项常驻结构检查（随模式一一起跑）：**符号可达性**。删除模块级函数/常量时只删
#   定义、留下调用点，会让 mypy / basedpyright / pytest 三面同时转红；调用点落在 `and`
#   右侧时短路还会遮住它，肉眼极易误判成「纯静态问题」。该检查把「引用了全仓都没有绑定
#   的名字」变成门禁里的一条明确违规（细则见 check_dangling_symbols）。
#
# 为什么用 ast.dump 而不是逐行 diff：注释不进抽象语法树，而三引号 docstring 会作为 Expr 节点
# 进入 AST。因此 AST 全等可同时证明：① 可执行逻辑一字未动；② 没有误插 docstring。
#
# 已知盲点（AST 校验发现不了，须另行检查）：
#   - `except A, B:`（PEP 758）与 `except (A, B):` 的 AST 完全相同，故「无括号写法被改成带
#     括号」不会被本工具发现，需 grep 计数核对。
#   - 注释缩进错误不影响 AST，只有 black 能发现；换行符形态变化对两者都隐形，须按字节复核。
#     故本工具应与 black 配套使用。
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
import builtins
import io
import os
import shutil
import sys
import tokenize
from pathlib import Path

# 默认注释密度下限（百分比）。该阈值与本项目既有高质量文件的密度对齐：
# src/stream_select.py 约 35%、src/scheduler.py 约 22%，多数文件在 13%~20% 区间。
DEFAULT_MIN_DENSITY = 13.0

# 模块头注释的判定范围：文件前 N 行内必须出现注释，否则视为缺模块头
MODULE_HEADER_SCAN_LINES = 30

# 不参与检查的目录：必须覆盖 .gitignore / pyproject 各工具（black exclude / isort extend_skip /
# coverage omit）排除掉的每一个目录名。锁的方向只做「那边有、这里也得有」，比那边更严是保守侧。
#
# 这份清单承重：它同时是 check_dangling_symbols() 经 iter_source_files 聚合「全仓绑定名」的
# 扫描面。**任何一个未排除的第三方目录里出现同名绑定，就会让「被删符号的残留调用点」被判成
# 「全仓有绑定」而漏报**——悬空符号门禁就此静默失效。
# 跨文件回归锁见 tests/test_run_gates.py：
#   ::test_check_annotations_exclude_dirs_cover_pyproject_excludes（逐名比对 pyproject 三处清单）
#   ::test_check_annotations_scan_face_still_includes_tests_and_src（反向兜底：src/tests/scripts/web 不得被排掉）
EXCLUDE_DIRS = (
    "__pycache__",
    ".git",
    ".venv",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".workbuddy",
    "node",
    "node_modules",
    "typings",
    "ffmpeg",
    "build",
    "dist",
    # 运行期产物目录（录制文件 / 日志 / 配置备份；已在 .gitignore、.dockerignore 同源忽略）
    "downloads",
    "recordings",
    "logs",
    "backup_config",
    # 第三方/工具生成目录（本地工具在仓库里留下的缓存与临时根，均非项目代码）
    ".agents",
    ".qoder",
    ".qoder-credits",
    ".codebuddy",
    ".trae",
    ".plugin-src",
    ".dsh-validation",
    ".ego-browser-test",
    ".npm-cache",
    ".pnpm-store",
    ".mimosa",
    ".tmp-dps-extract",
    ".v2c",
    # SDD/治理式流程技能在仓库内留下的工作区（与 .gitignore/.dockerignore/pyproject 同源登记）
    ".superpowers",
)

# 不参与检查的文件：protoc 生成物（自带 docstring 且标注 DO NOT EDIT）、以及按项目决策跳过的
# 历史遗留单文件版 standalone。加条目前先想清楚后果：这里排除掉的文件同样不在悬空符号检查的
# 扫描面内（为什么这份清单承重，见上方 EXCLUDE_DIRS 的同名说明）。
EXCLUDE_FILES = frozenset(
    {
        "douyin_pb2.py",
        "douyin_live_recorder_standalone.py",
    }
)


def is_excluded(path: Path, root: Path) -> bool:
    # 排除判定：任一**父目录**命中 EXCLUDE_DIRS、或文件名命中 EXCLUDE_FILES 即跳过；
    # 不在 root 之下的路径（如绝对路径穿越到工作区外）同样跳过，不属本工具的检查面
    try:
        rel = path.relative_to(root)
    except ValueError:
        return True
    parts = rel.parts
    if any(part in EXCLUDE_DIRS for part in parts[:-1]):
        return True
    return path.name in EXCLUDE_FILES


def iter_source_files(root: Path) -> list[Path]:
    # 收集待检查文件：全部 .py + **只限顶层 web/** 下的 .js/.css/.html（等价性比对要覆盖前端）。
    # 前端限定顶层 web/ 是刻意的：src/javascript/ 下的签名脚本会整体随包分发、不参与本工具，
    # 若一并收进来，模式 1 会拿 Python 的规则去判它们的注释密度。
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


# —— 符号可达性检查 ——
# 起因（同一形态第二次复现，登记单号见下方 DANGLING_HINT）：删除模块级函数/常量
# 时只删定义、留下调用点，mypy 报 name-defined、basedpyright 报 reportUndefinedVariable、
# pytest 在触达该分支时抛 NameError；而调用点若在 `and` 右侧
# （`(not os.path.isdir(...)) and (_deleted(proc))`），短路会在多数场景遮住它，于是「红着的
# 门禁」被误读成纯静态噪音，新改动继续往上叠。mypy 本就能报，但它不是「删除动作」的回路：
# 本检查在门禁里给出带文件路径与行号的明确违规，并把「删前先 grep 全部调用点」写进提示。
# 判据刻意保守（宁漏勿噪）：只报「本文件内没有任何绑定」**且**「全仓其它文件也没有同名绑定」
# 的 Load 名。后者用于放行 `from x import *`、monkeypatch 注入、globals() 动态写入等合法来源；
# 漏报仍由 mypy / basedpyright 兜底，本检查只负责把「删了一半」挡在回路之外。
DANGLING_HINT = (
    "删除模块级函数/常量前必须先 `grep -n <符号名>` 收全调用点再删"
    "（AGENTS.md「已知坑」同名条目；CODE_REVIEW_2026-09-21 补-N04：同一形态已第二次复现）"
)


def _collect_bound_names(tree: ast.Module) -> set[str]:
    # 收集「该文件里出现过一次绑定」的全部名字（任意作用域）：赋值 / 参数 / 导入 / def / class /
    # with-as / except-as / global / 类型参数 / 模式匹配绑定，用于证明某个 Load 名**有来源**。
    bound: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
            bound.add(node.id)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            bound.add(node.name)
        elif isinstance(node, ast.arg):
            bound.add(node.arg)
        elif isinstance(node, ast.alias):
            bound.add(node.asname or node.name.split(".")[0])
        elif isinstance(node, (ast.Global, ast.Nonlocal)):
            bound.update(node.names)
        elif isinstance(node, (ast.TypeVar, ast.ParamSpec, ast.TypeVarTuple)):
            bound.add(node.name)
        elif isinstance(node, (ast.MatchAs, ast.MatchStar)) and node.name:
            bound.add(node.name)
        elif isinstance(node, ast.MatchMapping) and node.rest:
            bound.add(node.rest)
        else:
            # 3.14 起 except 的绑定不再是 ast.Name（改存 str），单独兜住；getattr 兼容后续改名
            handler_name = getattr(node, "name", None)
            if isinstance(node, ast.ExceptHandler) and isinstance(handler_name, str):
                bound.add(handler_name)
    return bound


def _dangling_loads(tree: ast.Module, global_bound: set[str]) -> list[tuple[int, str]]:
    # 返回 [(行号, 名字)]：本文件无绑定、全仓亦无同名绑定、且非 dunder / 内建的 Load 名
    local_bound = _collect_bound_names(tree)
    hits: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Name) or not isinstance(node.ctx, ast.Load):
            continue
        name = node.id
        if name in local_bound or name in global_bound:
            continue
        # dunder（__name__ / __file__ …）由解释器注入，不属「模块级符号被删」的范畴
        if name.startswith("__") and name.endswith("__"):
            continue
        if hasattr(builtins, name):
            continue
        hits.append((node.lineno, name))
    return hits


def check_dangling_symbols(root: Path) -> tuple[int, list[str]]:
    # 扫全部 Python 文件：先汇总「全仓任一处绑定过的名字」，再逐文件找无来源的 Load 名。
    # 返回 (已扫描文件数, 违规描述列表)。解析失败的文件跳过（语法问题由 pytest / compile 负责）。
    trees: dict[Path, ast.Module] = {}
    global_bound: set[str] = set()
    for path in iter_source_files(root):
        if path.suffix != ".py":
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError, ValueError:
            continue
        trees[path] = tree
        global_bound |= _collect_bound_names(tree)
    problems: list[str] = []
    for path, tree in trees.items():
        rel = path.relative_to(root).as_posix()
        for lineno, name in _dangling_loads(tree, global_bound):
            problems.append(f"{rel}:{lineno}: 引用了全仓都没有绑定的名字 `{name}`")
    return len(trees), problems


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
        # 读不动源文件（权限/被占用/设备错误）此前以 rc=1 + Traceback
        # 结束，而 rc=1 在 CI 语义里是「代码不符合注释规范」。真相是「这条文件没查」，与
        # check_runtime_pins / check_coverage 的 rc=2 分级契约冲突，故显式退 2 并给出重跑命令。
        try:
            src = path.read_text(encoding="utf-8", errors="replace")
        except (OSError, ValueError) as exc:
            print(
                f"ERROR: 门禁自身失效，无法读取 {rel}（{type(exc).__name__}: {exc}）——不是注释规范问题",
                file=sys.stderr,
            )
            print("       请确认文件可访问后重跑：python scripts/check_annotations.py", file=sys.stderr)
            # 不能 return 2：本函数的返回值是「违规条数」，会被调用方折算成 rc=1（代码不合格）。
            sys.exit(2)

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

    # 符号可达性（与注释规范同批输出，共用 problems 计数：命中即门禁变红）
    scanned, dangling = check_dangling_symbols(root)
    for item in dangling:
        problems.append(f"[悬空符号] {item}")

    print("=" * 78)
    print(f"注释规范检查（阈值 {min_density:.1f}%）—— 共扫描 {len(stats)} 个 Python 文件")
    print(f"符号可达性检查—— 共扫描 {scanned} 个 Python 文件，悬空引用 {len(dangling)} 处")
    print("=" * 78)
    if problems:
        if dangling:
            print(f"  提示：{DANGLING_HINT}")
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


def _reject_dangerous_baseline(baseline: Path) -> str | None:
    # --snapshot 会先 shutil.rmtree(baseline) 再重建。误传系统根 / 主目录 / 仓库根 / 祖先目录
    # 时，rmtree 会先递归删掉整个目录树——不可逆数据丢失，且发生在一个看似只读的
    # 「建立快照」动作里，用户极难预期。命中即拒绝执行并返回错误说明。
    resolved = baseline.resolve()
    # 文件系统根与各盘符根（Windows: C:\ 等）
    if resolved == resolved.parent:
        return f"拒绝：基线目录是文件系统根 -> {resolved}"
    # 用户主目录
    try:
        home = Path.home().resolve()
    except OSError, RuntimeError:
        home = None
    if home is not None and (resolved == home or resolved.parent == home):
        return f"拒绝：基线目录是用户主目录或其直接层级 -> {resolved}"
    # 当前工作目录与其祖先（含仓库根）：快照目录应是其子目录而非祖先
    try:
        cwd = Path.cwd().resolve()
    except OSError:
        cwd = None
    if cwd is not None and (resolved == cwd or resolved in cwd.parents):
        return f"拒绝：基线目录是当前工作目录或其祖先 -> {resolved}"
    # M-23：原判据 `home in resolved.parents` 拒绝主目录下**一切**路径，而本仓常见布局正是检出在
    # 家目录里（Windows `C:\Users\<you>\...`、Linux `~\...`），连工具自己提示的工作区子目录
    # （`.workbuddy/ast-baseline`）也被误拒。防呆目的逐条保住：① 家目录本体与被直接当基线传进来
    # 的第一层子目录（Documents/AppData/Temp 这些「一个人全部数据」的入口）仍一律拒绝；② 文件
    # 系统根、cwd 本体及其祖先仍先于放行判定；③ 放行只覆盖「严格位于当前工作目录之下」的目录——
    # 那是用户自己 cd 进来的仓库子目录，rmtree 它正是 --snapshot 的既定用法。cwd 本身是家目录时
    # 不放行（否则等于把整棵家目录树声明成「工作区」，把上面两条防线一次让掉）。
    # 位置必须在这里而不是并入 home 那条：Windows 侧的 system_roots 含 `C:\Users`，检出在
    # `C:\Users\<you>\repo` 时其下的快照目录会先被那条 `sr in resolved.parents` 误拒。
    # S-13：这一段原先是「命中即 return None」的放行分支，未命中则继续往下走，
    # 末尾还有一条 `return None` —— 于是 cwd 之外的任意绝对路径（`--snapshot D:\OtherRepo`、
    # `/srv/data`、`E:\backup`）落到函数末尾被放行，rmtree 整树删除无关目录。排除式黑名单无法
    # 穷举危险形态（任何用户目录、挂载点、其它仓库都可能被误传），故改为**白名单正向判定**：
    # 只有「严格位于 cwd 之下」这一种形态放行，其余一律拒绝。cwd 本身是家目录时也不放行
    # （否则等于把整棵家目录树声明成「工作区」，把上面两条防线一次让掉）。
    if cwd is not None and (home is None or cwd != home) and cwd in resolved.parents:
        return None
    # S-13：白名单之外一律拒绝。系统目录清单保留，只为给出**更准确的理由**——它原本是
    # 独立一条拒绝分支，现在与「不在 cwd 之下」结论相同，但点名「系统目录」对排障更有用
    # （tests/test_check_annotations.py::test_snapshot_guard_still_rejects_system_dirs 钉这条文案）。
    # 该清单刻意不含 Path(os.sep)：Windows 上 Path("\\").resolve() 是「当前盘符根」，任何绝对
    # 路径都在其下，会把合法工作区子目录一并误拒。盘符根/文件系统根由上方 `resolved ==
    # resolved.parent` 覆盖，二者现在都是白名单的子集。
    if os.name == "nt":
        system_roots: list[Path] = [
            Path("C:\\Windows"),
            Path("C:\\Program Files"),
            Path("C:\\Program Files (x86)"),
            Path("C:\\Users"),
        ]
    else:
        system_roots = [
            Path("/etc"),
            Path("/usr"),
            Path("/var"),
            Path("/bin"),
            Path("/sbin"),
            Path("/System"),
            Path("/Library"),
        ]
    for sys_root in system_roots:
        try:
            sr = sys_root.resolve()
        except OSError:
            continue
        if resolved == sr or sr in resolved.parents:
            return f"拒绝：基线目录是系统目录或其祖先 -> {resolved}"
    # 相对路径必须至少有一层父目录（拒绝 "." / ".."）
    if not resolved.parts or len(resolved.parts) < 2:
        return f"拒绝：基线目录层级过浅 -> {resolved}"
    return f"拒绝：基线目录必须是当前工作目录的子目录 -> {resolved}（如需外部目录请手工建快照）"


def take_snapshot(root: Path, baseline: Path) -> int:
    # 模式二：建立基线快照，供后续等价性校验使用
    # 删除前先防呆：rmtree 不可逆，误传根目录 = 整盘数据丢失
    danger = _reject_dangerous_baseline(baseline)
    if danger is not None:
        print(danger, file=sys.stderr)
        print("提示：快照目录应形如 .workbuddy/ast-baseline 之类的工作区子目录。", file=sys.stderr)
        return 1
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

    # M-92 残留（2026-10-21）：比对范围必须是「基线 ∪ 当前」的**并集**。旧写法只遍历 baseline，
    # 于是快照之后新增的源文件完全不参与比对——本工具的结论恰恰是「只改了注释」，而新增文件是
    # 最容易夹带逻辑改动的形态，旧实现却对它永久失明。新增文件按 changed 计（门禁变红），
    # 由使用者显式重建基线，不得默认放行。
    rel_set = {p.relative_to(baseline).as_posix() for p in baseline.rglob("*") if p.is_file()}
    rel_set |= {p.relative_to(root).as_posix() for p in iter_source_files(root)}

    for rel_posix in sorted(rel_set):
        rel = Path(rel_posix)
        base_file = baseline / rel
        current = root / rel
        if not base_file.is_file():
            changed.append((rel_posix, "快照后新增的文件未参与基线比对（请重建基线后重跑）"))
            continue
        if not current.exists():
            missing.append(rel_posix)
            continue
        try:
            old_src = base_file.read_text(encoding="utf-8", errors="replace")
            new_src = current.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            # 纯读路径兜底：存在但不可读（权限/占用）按 changed 计——「无法证明
            # 等价」对本门禁同样是红，但要有可读理由而非 rc=1 裸栈冒充「代码不等价」。
            changed.append((rel_posix, f"无法读取（{type(exc).__name__}: {exc}），等价性无法验证"))
            continue
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
    # 入口：按 --snapshot > --baseline > 规范检查 的优先级分派（三者互斥，同时给也只跑前者）
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
