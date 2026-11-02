# -*- coding: utf-8 -*-
# 按名传入 i18n.tr()/ui_i18n.T() 的 msgid 必须命中四语目录（提取器盲区④的可机检化）。
#
# 为什么单独成文件：scripts/extract_i18n_strings.py 与 tests/test_i18n_migration.py 的不变量③
# 都只看 tr()/T() 的**字面量首参**；`i18n.tr(msgid)`（msgid 来自元组表）、`tr(THEME_LABELS[k])`、
# `T(title)`（title 是循环变量）这类按名传入对两者完全隐形。实测事故即此类：
# Qt 侧栏导航 msgid 以「两空格」的 📊  控制台 存放在元组里，四目录只有 Tk 遗留的「三空格」形态，
# 切到 en_US/en_GB/zh_TW 后静默回落简中原文，而提取器仍报「0 缺失」（假绿）。
#
# 三条锁：
#   ⑤-A 按名调用点解析出的 msgid 候选，必须在**四份目录**里都存在（不止 zh_CN.po）；
#   ⑤-B 解析不出候选的按名调用点用**白名单集合相等**判定（新增即红、已消解却不收回也红）；
#   ⑤-C 四份目录键集合逐项相等（单侧漏登记/多登记会让某语言静默回落原文）。
#
# 变异验证锚点（删掉任一判据必须让某条用例变红）：把 ⑤-A 的 key_sets 收窄到只查 zh_CN.po →
# ::test_by_name_msgids_covered_by_catalogs 红；从白名单删掉 ui_i18n.py::render →
# ::test_unresolved_by_name_calls_match_allowlist 红；把 ⑤-C 退化成「只比 po 与 en_US」→
# ::test_catalog_key_sets_are_identical 红。

import ast
import functools
import importlib.util
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent

# 按名调用点里「按设计无法静态解析」的白名单（集合相等判定，多一处少一处都红）：
# src/ui_i18n.py::Translatable.render 是 Translatable.render() 的 `tr(self.msgid)`——候选即全仓
# T(...) 的字面量首参，那批串由 tests/test_i18n_migration.py 的不变量③逐条核对，本锁不重复收。
# 新增不可解析点必须先进本白名单并写明「由哪条锁覆盖」，否则该 msgid 无人核对。
# 键形态 = 「文件::函数名」（M-35④）：行号会随同文件增删漂移，锚点不会。
ALLOWED_UNRESOLVED_BY_NAME_CALLS = {"src/ui_i18n.py::render"}

# 参数位实参链式解析的收敛轮数：`模块常量 → 调用方实参 → 形参 → 再传入下一层 → tr(形参)`
# 在 src/gui_qt/shared.py 的实际深度是 2 层（_pattern_from_template → _sentinel_text），
# 留一轮余量；轮数本身不是判据，白名单才是。
_INDEX_PASSES = 3


def _load_probe(module_name: str, filename: str) -> Any:
    # 按文件路径加载 scripts/ 下的独立脚本（不在包内），与 tests/test_i18n_migration.py 同先例：
    # 复用 compile_po 的 .po 解析与提取器的价值判定/模板还原口径，避免两套解析漂移
    spec = importlib.util.spec_from_file_location(module_name, ROOT / "scripts" / filename)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_CP = _load_probe("_catalog_po_probe", "compile_po.py")
_EX = _load_probe("_catalog_extract_probe", "extract_i18n_strings.py")
is_valuable = getattr(_EX, "is_valuable")
template_of = getattr(_EX, "extract_constant_or_template")
# 扫描面直接取提取器的 SCAN_FILES（根入口 + src/**），不另建第二份清单：
# 本仓「清单复制即漂移」已有多处先例（见 .mjs 登记与 mypy exclude 的机检锁）
SCAN_FILES: list[Path] = [p for p in getattr(_EX, "SCAN_FILES") if p.exists()]


def _parse(path: Path) -> tuple[ast.Module, str]:
    src = path.read_text(encoding="utf-8-sig")
    return ast.parse(src, filename=str(path)), src


def _literals_of(node: ast.AST, src: str, via: dict[str, set[str]] | None = None) -> set[str]:
    # 表达式内所有可作 msgid 的字符串常量：常量、隐式拼接、f-string 还原模板、
    # 容器字面量（dict 取**值**——标签表的键是 light/dark 这类 id，不是文案）、元组/列表取全部元素。
    # via 非空时额外按「已解析出的名字绑定」展开 Name/Subscript（链式参数解析用，见 _INDEX_PASSES）
    out: set[str] = set()
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        out.add(node.value)
    elif isinstance(node, ast.JoinedStr):
        text = template_of(node, src)
        if text:
            out.add(text)
    elif isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        out |= _literals_of(node.left, src, via) | _literals_of(node.right, src, via)
    elif isinstance(node, (ast.Tuple, ast.List, ast.Set)):
        for elt in node.elts:
            out |= _literals_of(elt, src, via)
    elif isinstance(node, ast.Dict):
        for value in node.values:
            out |= _literals_of(value, src, via)
    elif via is not None:
        if isinstance(node, ast.Name):
            out |= via.get(node.id, set())
        elif isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name):
            out |= via.get(node.value.id, set())
    return out


def _assign_pairs(tree: ast.AST) -> list[tuple[str, ast.AST]]:
    # (绑定名, 值表达式) 序列：覆盖 Assign 与 AnnAssign
    pairs: list[tuple[str, ast.AST]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            targets: list[ast.AST] = list(node.targets)
            value: ast.AST | None = node.value
        elif isinstance(node, ast.AnnAssign):
            targets = [node.target]
            value = node.value
        else:
            continue
        if value is None:
            continue
        for target in targets:
            if isinstance(target, ast.Name):
                pairs.append((target.id, value))
    return pairs


def _binding_index(
    tree: ast.Module, src: str, scope: str, via: dict[str, set[str]] | None = None
) -> dict[str, set[str]]:
    # 名字 -> 候选 msgid 集合。
    #   scope="upper"：只收模块级 UPPER_CASE 常量（跨文件合并，用于导入进来的标签表，
    #     如 src/gui_qt/theme.py 的 THEME_LABELS 被 main_window.py 按下标取用）；
    #   scope="local"：收本文件全部字面量绑定 + 循环变量按位取值 + 函数参数位实参，
    #     但**不跨文件**——不同文件里同名小写变量会把非文案串灌进候选，造成假红。
    index: dict[str, set[str]] = {}

    def put(name: str, values: set[str]) -> None:
        if values:
            index.setdefault(name, set()).update(values)

    if scope == "upper":
        for stmt in tree.body:
            if isinstance(stmt, ast.Assign):
                for target in stmt.targets:
                    if isinstance(target, ast.Name) and target.id.isupper():
                        put(target.id, _literals_of(stmt.value, src, via))
            elif isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name) and stmt.value is not None:
                if stmt.target.id.isupper():
                    put(stmt.target.id, _literals_of(stmt.value, src, via))
        return index

    for name, value in _assign_pairs(tree):
        put(name, _literals_of(value, src, via))

    # 调用点整体收一次：本函数在 _INDEX_PASSES 轮里被反复重建，逐函数 ast.walk(tree)
    # 会让复杂度变成 O(函数数 × 节点数)（实测 35s → 优化后 <10s）
    all_calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call)]
    for node in ast.walk(tree):
        # for page_id, msgid in (("dashboard", "📊  控制台"), ...): → 按**位置**对齐取元素，
        # 取错位会把 "dashboard" 这类 id 当文案（假红）
        if isinstance(node, ast.For) and isinstance(node.target, (ast.Tuple, ast.List)):
            names = [e.id for e in node.target.elts if isinstance(e, ast.Name)]
            for row in _iter_rows(node.iter, tree):
                if not isinstance(row, (ast.Tuple, ast.List)):
                    continue
                for i, name in enumerate(names):
                    if i < len(row.elts):
                        put(name, _literals_of(row.elts[i], src, via))
        # def f(template: str): ... tr(template) → 取本文件内对该函数实参位的字面量
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            params = [a.arg for a in node.args.args + node.args.kwonlyargs]
            if not params:
                continue
            for call in all_calls:
                if not (isinstance(call.func, ast.Name) and call.func.id == node.name):
                    continue
                for i, arg in enumerate(call.args[: len(params)]):
                    put(params[i], _literals_of(arg, src, via))
                for kw in call.keywords:
                    if kw.arg in params:
                        put(kw.arg, _literals_of(kw.value, src, via))
    return index


def _iter_rows(iterable: ast.AST, tree: ast.Module) -> list[ast.AST]:
    # 循环可迭代表达式 → 行元素列表：直接写元组/列表字面量，或取自同文件的同名字面量绑定
    if isinstance(iterable, (ast.Tuple, ast.List)):
        return list(iterable.elts)
    if isinstance(iterable, ast.Name):
        for name, value in _assign_pairs(tree):
            if name == iterable.id and isinstance(value, (ast.Tuple, ast.List)):
                return list(value.elts)
    return []


def _resolve(arg: ast.AST, src: str, local: dict[str, set[str]], upper: dict[str, set[str]]) -> set[str]:
    # 首参表达式 → msgid 候选集合；解析不出返回空集（计入不可解析棘轮，不放行）
    direct = _literals_of(arg, src)
    if direct:
        return direct
    if isinstance(arg, ast.Name):
        return local.get(arg.id, set()) or upper.get(arg.id, set())
    if isinstance(arg, ast.Subscript) and isinstance(arg.value, ast.Name):
        base = arg.value.id
        return local.get(base, set()) or upper.get(base, set())
    if isinstance(arg, ast.BinOp) and isinstance(arg.op, ast.Add):
        return _resolve(arg.left, src, local, upper) | _resolve(arg.right, src, local, upper)
    return set()


# 函数/类定义的行区间表：label 取最内层包含该行的定义名，用于构造与行号无关的锚点。
def _symbol_spans(tree: ast.Module) -> list[tuple[int, int, str]]:
    spans: list[tuple[int, int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            spans.append((node.lineno, getattr(node, "end_lineno", None) or node.lineno, node.name))
    return spans


def _enclosing_symbol(spans: list[tuple[int, int, str]], lineno: int) -> str:
    innermost: tuple[int, str] | None = None
    for start, end, name in spans:
        if start <= lineno <= end and (innermost is None or start > innermost[0]):
            innermost = (start, name)
    return innermost[1] if innermost is not None else "<module>"


def collect_by_name_calls() -> tuple[dict[str, set[str]], list[str]]:
    # 返回 ({调用点: msgid 候选集合}, [解析不出候选的调用点])
    # 缓存理由：三条用例共用同一次全量解析（74 个文件 × _INDEX_PASSES 轮），
    # 不缓存会让本文件自身跑两遍同样的 AST（实测 6s × 2）
    parsed: dict[Path, tuple[ast.Module, str]] = {path: _parse(path) for path in SCAN_FILES}

    # 跨文件合并的模块级 UPPER_CASE 标签表（THEME_LABELS 定义在 theme.py、取用在 main_window.py）
    upper: dict[str, set[str]] = {}
    for tree, src in parsed.values():
        for name, values in _binding_index(tree, src, scope="upper").items():
            upper.setdefault(name, set()).update(values)

    # 迭代 _INDEX_PASSES 轮：上一轮解出的名字绑定喂给下一轮，让「模块常量 → 实参 → 形参 →
    # 再作实参 → 再进形参」这类跨层链收敛（gui/shared 的 _pattern_from_template→_sentinel_text 两层）
    locals_by_path = {path: _binding_index(tree, src, scope="local") for path, (tree, src) in parsed.items()}
    for _ in range(_INDEX_PASSES):
        grew = False
        for path, (tree, src) in parsed.items():
            nxt = _binding_index(tree, src, scope="local", via=locals_by_path[path])
            for name, values in nxt.items():
                if not values <= locals_by_path[path].get(name, set()):
                    grew = True
                locals_by_path[path].setdefault(name, set()).update(values)
        if not grew:
            break

    found: dict[str, set[str]] = {}
    unresolved: list[str] = []
    for path, (tree, src) in parsed.items():
        local = locals_by_path[path]
        rel = path.relative_to(ROOT).as_posix()
        # 锚点用「文件::函数名」而不是行号（M-35④，口径同上方白名单处）：行号漂移会让白名单造出假红（AGENTS「引用代码位置优先写锚点」同一口径）。
        symbols = _symbol_spans(tree)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not node.args:
                continue
            func = node.func
            fname = func.attr if isinstance(func, ast.Attribute) else (func.id if isinstance(func, ast.Name) else None)
            if fname not in ("tr", "T"):
                continue
            arg = node.args[0]
            if isinstance(arg, (ast.Constant, ast.JoinedStr)):
                continue  # 字面量形态归不变量③/提取器管，本锁只补按名这一类
            cands = _resolve(arg, src, local, upper)
            label = f"{rel}::{_enclosing_symbol(symbols, node.lineno)}"
            if cands:
                found.setdefault(label, set()).update(cands)
            else:
                unresolved.append(label)
    return found, unresolved


def _catalog_key_sets() -> dict[str, set[str]]:
    # 四份目录的键集合；.po 需剔除 gettext 头部空 msgid（不剔除永远「多 1 条」假阳性）
    keys: dict[str, set[str]] = {"zh_CN.po": set(_CP.parse_po(_CP.PO_PATH)) - {""}}
    for lang in ("en_US", "en_GB"):
        keys[f"{lang}.json"] = set(json.loads((ROOT / "i18n" / f"{lang}.json").read_text(encoding="utf-8-sig")))
    import yaml  # type: ignore[import-untyped]

    keys["zh_TW.yaml"] = set(yaml.safe_load((ROOT / "i18n" / "zh_TW.yaml").read_text(encoding="utf-8-sig")))
    return keys


# 三条用例共用同一份解析结果与同一份目录键集合：整仓 AST 扫描按文件数线性、
# _INDEX_PASSES 轮内还嵌套遍历（实测单次 ~6s），不缓存会让同批解析在同一会话里跑三遍。
# 返回的是同一批可变对象，用例只读不改（改判据时请改为返回深拷贝，别在用例里就地修改）。
@functools.lru_cache(maxsize=1)
def _cached_catalog_key_sets() -> dict[str, set[str]]:
    return _catalog_key_sets()


@functools.lru_cache(maxsize=1)
def _cached_by_name_calls() -> tuple[frozenset[tuple[str, frozenset[str]]], tuple[str, ...]]:
    found, unresolved = collect_by_name_calls()
    return frozenset((k, frozenset(v)) for k, v in found.items()), tuple(unresolved)


def _by_name_calls() -> tuple[dict[str, set[str]], list[str]]:
    pairs, unresolved = _cached_by_name_calls()
    return {k: set(v) for k, v in pairs}, list(unresolved)


def test_catalog_key_sets_are_identical() -> None:
    # ⑤-C 四语目录键集合逐项相等
    keys = _cached_catalog_key_sets()
    baseline = keys["zh_CN.po"]
    offenders = [
        f"{name}: 多 {len(v - baseline)} / 少 {len(baseline - v)}" for name, v in keys.items() if v != baseline
    ]
    assert not offenders, "四语目录键集合不一致：\n" + "\n".join(offenders)


def test_by_name_msgids_covered_by_catalogs() -> None:
    # ⑤-A 按名传入 tr()/T() 的 msgid 候选必须四目录齐全
    found, _ = _by_name_calls()
    # 锚点自检：解析结果为空 = 判据本身失效，此时「0 缺失」是假绿
    assert found, "按名调用点解析结果为空，判据失效（至少应解析出侧栏导航的 msgid）"
    key_sets = _cached_catalog_key_sets()
    missing = []
    for label, cands in sorted(found.items()):
        for msgid in sorted(c for c in cands if is_valuable(c)):
            absent = [name for name, keys in key_sets.items() if msgid not in keys]
            if absent:
                missing.append(f"{label} {msgid!r} 缺于 {absent}")
    assert not missing, "按名传入 tr()/T() 的 msgid 未登记进全部目录：\n" + "\n".join(missing)
    nav = {c for cands in found.values() for c in cands if "控制台" in c}
    assert nav, "必须解析出导航 msgid（含「控制台」），否则盲区④仍不可见"


def test_unresolved_by_name_calls_match_allowlist() -> None:
    # ⑤-B 白名单集合相等判定：新增不可解析点即红；已知点被消解后不收回白名单也红
    _, unresolved = _by_name_calls()
    actual = set(unresolved)
    extra = sorted(actual - ALLOWED_UNRESOLVED_BY_NAME_CALLS)
    stale = sorted(ALLOWED_UNRESOLVED_BY_NAME_CALLS - actual)
    assert not extra, (
        "新增按名 tr()/T() 调用点无法静态解析出 msgid 候选：" + ", ".join(extra) + " —— 改成可解析形态，"
        "或确证「另有锁覆盖」后把它写进 ALLOWED_UNRESOLVED_BY_NAME_CALLS 并注明那条锁"
    )
    assert not stale, "白名单里有已不存在的调用点（多为行号漂移）：" + ", ".join(stale) + " —— 收回本项，勿留空壳"
