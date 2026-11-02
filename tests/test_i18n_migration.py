# -*- coding: utf-8 -*-
# i18n.tr() 形参迁移的静态防回归。
#
# 背景：logger/print 的 f-string 会在查目录之前先完成插值，目录里带占位符的 msgid 永远匹配不上，
# 翻译静默退化为原文；迁移把这些调用点改写为 i18n.tr(模板, **kw)——「先查表、后插值」。
#
# 四条不变量（全部静态成立，零运行时依赖）：
#   ① logger/print 不再出现「有价值的」插值 f-string；判据是「首参**子树**含带 FormattedValue
#      的 JoinedStr」而非「首参直接是 JoinedStr」——后者会漏掉 `f"A" + (f"B" if x else "") + f"C"`
#      这类 ast.BinOp 形态（MID-68，详见该用例内注释）；
#   ② 每个 tr() 调用的模板占位符集合 == 关键字实参集合（防止改模板漏改实参）；
#   ③ 运行时模板集合 ⊆ zh_CN.po 键集合（等价于提取器「缺失 0」）；
#   ④ print_colored 实参位不再出现插值 f-string：这是提取器盲区①，主提取器与不变量①
#      都看不见；盲区文案须 tr 预格式化后整体传入，否则目录词条静默失效。

import ast
import importlib.util
import re
from pathlib import Path
from typing import TypeGuard

# 项目根：本文件位于 tests/ 下，取上级目录；后续所有路径都相对它解析
ROOT = Path(__file__).resolve().parent.parent
# 与 scripts/extract_i18n_strings.py 的 LOGGER_METHODS 保持同口径：
# 只有 logger.<这些方法>(...) 的首参才被提取器视为「可翻译串」
LOGGER_METHODS = {
    "debug",
    "info",
    "success",
    "warning",
    "error",
    "critical",
    "exception",
    "trace",
    "log",
    "catch",
}


def _load_extractor() -> object:
    # 提取器是 scripts/ 下的独立脚本（不在包内），按文件路径加载并复用其 SCAN_FILES /
    # scan_file / is_valuable：复制一份扫描口径一旦漂移，回归结论就会与真实提取器不同（假绿/假红）
    spec = importlib.util.spec_from_file_location("_extract_i18n_probe", ROOT / "scripts" / "extract_i18n_strings.py")
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_EX = _load_extractor()
SCAN_FILES: list[Path] = getattr(_EX, "SCAN_FILES")
is_valuable = getattr(_EX, "is_valuable")
scan_file = getattr(_EX, "scan_file")
# 占位符还原（丢格式说明符/转换符、双引号转单引号）复用提取器实现：本文件与提取器
# 必须给出同一个 msgid 形态，否则门禁与目录登记两侧口径漂移
extract_constant_or_template = getattr(_EX, "extract_constant_or_template")
# tr() 的模块别名集合取自提取器，避免两处硬编码各自漂移
TR_CALLER_IDS: set[str] = getattr(_EX, "TR_CALLER_IDS")
# ui_i18n.T()（静态标签标记）同样取自提取器：T 的首参是 msgid/模板，占位符与 kwargs
# 也必须一致（窗口层的 text=T("...") 由工厂建时查表 + 登记重译）。
T_CALLER_IDS: set[str] = getattr(_EX, "T_CALLER_IDS")


def _iter_files() -> list[Path]:
    # gui_legacy.py 已删除，SCAN_FILES 里可能仍留历史条目 → 统一用 exists() 过滤，
    # 避免某个待扫描文件不存在就让整轮回归误报
    return [p for p in SCAN_FILES if p.exists()]


def _is_tr_call(node: ast.AST) -> TypeGuard[ast.Call]:
    # tr(模板, **kw) / i18n.tr(...) / i18n_module.tr(...) / T(模板)（ui_i18n 静态标签标记）
    # ——别名集合取自提取器，避免两处硬编码。
    # 用 TypeGuard 而非 bool：调用点要在判定后直接取 node.args，纯 bool 不会收窄类型（mypy attr-defined）
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    if isinstance(func, ast.Name) and func.id in T_CALLER_IDS:
        return True
    return (isinstance(func, ast.Name) and func.id == "tr") or (
        isinstance(func, ast.Attribute)
        and func.attr == "tr"
        and isinstance(func.value, ast.Name)
        and func.value.id in TR_CALLER_IDS
    )


def _interpolated_fstrings(node: ast.AST) -> list[ast.JoinedStr]:
    # MID-68：判据由「首参**直接是** JoinedStr」收紧为「首参**子树里**有带
    # FormattedValue 的 JoinedStr」。旧判据看不见 `f"A" + (f"B" if x else "") + f"C"` 这类
    # ast.BinOp 形态，「先插值、后查目录」的违规整类逃逸（实测 6 处真实违规从此漏过：
    # 斗鱼降级链、画质降级告警、磁盘空间提示等）。
    # 唯一收敛处是 tr() 调用：约定②「格式说明符/转换符由调用方预求值后作实参传入」的
    # f-string（`_backoff=f"{v:.0f}"`）发生在查表**之后**、不影响 msgid 匹配，一并判违规
    # 会把本仓推荐写法打成回归；故只递归其模板位（首参）。
    if isinstance(node, ast.JoinedStr):
        return [node] if any(isinstance(v, ast.FormattedValue) for v in node.values) else []
    if _is_tr_call(node):
        return _interpolated_fstrings(node.args[0]) if node.args else []
    found: list[ast.JoinedStr] = []
    for child in ast.iter_child_nodes(node):
        found.extend(_interpolated_fstrings(child))
    return found


def _message_text(node: ast.AST, src: str) -> str:
    # 还原「将要送给 logger/print 的整条消息模板」供价值判定（与提取器 is_valuable 同口径）：
    # 常量原样取、f-string 占位符还原为 {expr}、`+` 拼接与三元/布尔分支两侧都并入；
    # 其余节点（函数调用等）视为无自然语言
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        return extract_constant_or_template(node, src) or ""
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        return _message_text(node.left, src) + _message_text(node.right, src)
    if isinstance(node, ast.BoolOp):
        return "".join(_message_text(v, src) for v in node.values)
    if isinstance(node, ast.IfExp):
        return _message_text(node.body, src) + _message_text(node.orelse, src)
    if _is_tr_call(node) and node.args:
        return _message_text(node.args[0], src)
    return ""


def _offending_linenos(src: str) -> list[int]:
    # 判据本体（供全仓扫描与下方的判据自检用例共用，避免两处各写一份遍历而漂移）：
    # logger.* 只看首参；print 看全部位置参。命中条件 = 子树含被插值的 f-string
    # 且整条消息有自然语言（与提取器 is_valuable 同口径，纯占位符/装饰线不入目录）
    out: list[int] = []
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        is_print = isinstance(node.func, ast.Name) and node.func.id == "print"
        is_log = (
            isinstance(node.func, ast.Attribute)
            and node.func.attr in LOGGER_METHODS
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "logger"
        )
        if not (is_print or is_log):
            continue
        args = node.args if is_print else node.args[:1]
        for arg in args:
            if not _interpolated_fstrings(arg):
                continue
            if is_valuable(_message_text(arg, src)):
                out.append(node.lineno)
    return out


def test_no_valuable_fstring_in_logger_or_print() -> None:
    # ① 迁移后不应再有「有价值的」f-string 出现在 logger.* 首参（含拼接形态）或 print 任意位置
    offenders: list[str] = []
    for path in _iter_files():
        src = path.read_text(encoding="utf-8-sig")
        offenders.extend(f"{path.relative_to(ROOT)}:{lineno}" for lineno in _offending_linenos(src))
    assert not offenders, "以下位置仍是 logger/print f-string（应改用 i18n.tr）：" + ", ".join(offenders)


def test_gate_predicate_sees_concatenated_fstring() -> None:
    # 判据自检（MID-68）：上面那条全仓扫描必须真的**能**抓到拼接形态，否则它仍是假绿。
    # 把 _interpolated_fstrings 退回旧判据 `isinstance(arg, ast.JoinedStr)` 会让本用例变红。
    src = (
        "logger.warning(f'A rate={a}' + (f', msg={m}' if m else '') + f' next rate={b}')\n"
        "print(f'x: {v}' + ' tail text')\n"
        "logger.error(i18n.tr(f'模板位被插值 {x}', x=x))\n"
    )
    assert _offending_linenos(src) == [1, 2, 3], "门禁漏抓：拼接 f-string / tr 模板位 f-string 必须全部命中"
    # 反向：约定②允许「把格式说明符预求值为实参」——这类 f-string 发生在查表之后，
    # 不影响 msgid 匹配，判违规会把本仓推荐写法打成回归（旧 `_backoff=f"{v:.0f}"` 即此形态）
    assert _offending_linenos("logger.debug(i18n.tr('退避 {_backoff}s', _backoff=f'{v:.0f}'))\n") == []
    assert _offending_linenos("logger.debug(i18n.tr('常量模板 {masked_url}', masked_url=url))\n") == []


def test_tr_template_placeholders_match_kwargs() -> None:
    # ② 每个 tr() 调用的模板占位符集合必须与关键字实参集合一致
    offenders: list[str] = []
    for path in _iter_files():
        src = path.read_text(encoding="utf-8-sig")
        tree = ast.parse(src, filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not node.args:
                continue
            func = node.func
            is_tr = (isinstance(func, ast.Name) and func.id == "tr") or (
                isinstance(func, ast.Attribute)
                and func.attr == "tr"
                and isinstance(func.value, ast.Name)
                and func.value.id in TR_CALLER_IDS
            )
            if not is_tr:
                continue
            first = node.args[0]
            if not (isinstance(first, ast.Constant) and isinstance(first.value, str)):
                continue
            placeholders = set(re.findall(r"\{([^{}]*)\}", first.value))
            kwargs = {kw.arg for kw in node.keywords if kw.arg}
            # 占位符必须是纯标识符：tr() 内部走 str.format，花括号里出现表达式/属性/下标
            # 会直接抛 KeyError（这正是迁移前 f-string 形态无法被目录命中的原因）
            non_ident = sorted(p for p in placeholders if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", p))
            if non_ident or placeholders != kwargs:
                offenders.append(
                    f"{path.relative_to(ROOT)}:{node.lineno} 模板={sorted(placeholders)} 实参={sorted(kwargs)}"
                    + (f" 非标识符占位符={non_ident}" if non_ident else "")
                )
    assert not offenders, "tr() 模板占位符与关键字实参不一致：\n" + "\n".join(offenders)


def test_runtime_templates_covered_by_catalog() -> None:
    # ③ 运行时提取到的模板集合必须被 zh_CN.po 键集合完全覆盖（等价于提取器「缺失 0」）
    runtime: set[str] = set()
    for path in _iter_files():
        runtime |= scan_file(path)
    # 只保留有价值串（与提取器同口径）：纯装饰线/纯占位符模板本就不入目录
    runtime = {s for s in runtime if is_valuable(s)}

    # 直接复用 compile_po 的权威 .po 解析（多行 msgid / 转义还原均正确），
    # 不自己写解析器，避免两套解析口径不一致导致误判
    spec = importlib.util.spec_from_file_location("_compile_po_probe", ROOT / "scripts" / "compile_po.py")
    assert spec is not None and spec.loader is not None
    cp = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cp)
    # 剔除 gettext 头部空 msgid（目录本就不含它，不剔除会永远报「多 1 条」）
    keys = set(cp.parse_po(cp.PO_PATH)) - {""}

    missing = sorted(runtime - keys)
    assert not missing, f"目录缺失 {len(missing)} 条运行时模板：\n" + "\n".join(repr(m) for m in missing)


def _blindspot_fstring_offenders(src: str) -> list[int]:
    # 不变量④判据本体（供全仓扫描与下方判据自检共用，避免两处各写一份遍历而漂移）：
    # print_colored 只看首参（第二参是颜色）。
    out: list[int] = []
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr != "print_colored" or not node.args:
            continue
        if _interpolated_fstrings(node.args[0]) and is_valuable(_message_text(node.args[0], src)):
            out.append(node.lineno)
    return out


def test_no_valuable_fstring_in_print_colored() -> None:
    # ④ 盲区①实参位禁插值 f-string：翻译须 tr(常量模板, **kw) 预格式化后整体传入。
    # 全仓扫描：全部调用点已迁移，任何一处改回 f-string 直传都会让对应目录词条静默失效。
    offenders: list[str] = []
    for path in _iter_files():
        src = path.read_text(encoding="utf-8-sig")
        offenders.extend(f"{path.relative_to(ROOT)}:{lineno}" for lineno in _blindspot_fstring_offenders(src))
    assert not offenders, "以下位置仍是 print_colored f-string（应改用 i18n.tr 预格式化）：" + ", ".join(offenders)
    # 判据自检：谓词必须真抓得到盲区形态，且不误伤 tr 预格式化/常量/动态非模板实参
    hits = "color_obj.print_colored(f'[{n}]录制时已被注释', c)\n"
    assert _blindspot_fstring_offenders(hits) == [1], "门禁漏抓：盲区实参位的插值 f-string 必须命中"
    clean = (
        "color_obj.print_colored(i18n.tr('[{n}]已注释', n=n), c)\n"  # tr 预格式化（推荐形态）
        "color_obj.print_colored('\\n正在安全退出...', c)\n"  # 常量串（translated_print 直查）
    )
    assert _blindspot_fstring_offenders(clean) == [], "误伤：tr 预格式化 / 常量 / 非模板实参不应命中"


def test_extractor_sees_T_marker_templates(tmp_path: Path) -> None:
    # 提取器必须与 tr 同口径认识 ui_i18n.T()（静态标签标记）：T 的首参是 msgid，
    # 不被 scan_file 收录时「目录覆盖完整」（不变量③）对这批词条退化为假绿——
    # 缺失检测看不见它们，孤儿/缺词条都不会变红。set_text 的第二参是 T(...)，
    # 由 ast.walk 独立访问，不需要特例。
    probe = tmp_path / "probe_t.py"
    probe.write_text(
        "x = T('静态标签探针')\ny = set_text(win, T('标题探针'))\nz = str('非 T 串不计')\n",
        encoding="utf-8",
    )
    found = scan_file(probe)
    assert "静态标签探针" in found, "T(...) 首参必须被提取"
    assert "标题探针" in found, "set_text 内层 T(...) 必须被提取"
    assert "非 T 串不计" not in found, "普通字面量不得被提取（防误收）"
