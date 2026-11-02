# src/utils.py 两个兜底装饰器「返回契约 → 装饰器配对」与「装饰器贴 def」的全仓 AST 回归锁。
#
# 背景（ / 该建议④ /）：
#   - trace_error_decorator 的失败兜底值是 {"is_live": False}，只适用于**返回 dict** 的平台函数；
#     返回 str/tuple/OptionalStr 的函数误挂它时，故障值是个恒真的 dict——元组解包抛 ValueError
#     被调用方装饰器二次吞没（login_popkontv 形态），或 dict 被当成 Cookie 写进请求头
#     （login_twitcasting 形态），用户可动作的错误提示彻底丢失、表现为静默「未开播」。
#   - Python 允许 @decorator 与 def 之间夹注释行，装饰器仍绑到**紧随其后的那个 def**——一旦把
#     说明性注释插在两者之间，装饰器就绑到下一个函数上（haixiu 事故形态）。
# 两条不变量只有静态扫全仓才能在「新增平台函数」的当下拦住，故收敛为本文件：
#   ① 返回注解含 dict → 必须 trace_error_decorator；注解为 str/tuple/其他 → 必须
#      trace_error_decorator_or_none（无注解不判）；
#   ② @decorator 必须紧贴 def（中间只允许另一个装饰器行），注释一律写在装饰器上方。
#
# 「含 dict」按模块级类型别名递归展开（OptionalDict/OptionalStreamDict 等）：
# dict[str, object] | None 也算 dict 返回（内部分支回 None 是该装饰器的既定适用场景，
# 如 get_bilibili_stream_data）。

import ast
from pathlib import Path
from typing import Union

ROOT = Path(__file__).resolve().parent.parent
DEC_DICT = "trace_error_decorator"
DEC_NONE = "trace_error_decorator_or_none"
_DEC_NAMES = {DEC_DICT, DEC_NONE}

# 排除目录与文件：对齐 black/coverage 的排除口径 + 本地工具生成目录（点开头目录整体排除）。
_EXCLUDE_DIR_PARTS = {
    "node",
    "ffmpeg",
    "downloads",
    "logs",
    "backup_config",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
}
_EXCLUDE_FILE_NAMES = {"douyin_live_recorder_standalone.py", "douyin_pb2.py"}


def _iter_py_files() -> list[Path]:
    files: list[Path] = []
    for p in ROOT.rglob("*.py"):
        parts = p.relative_to(ROOT).parts[:-1]
        if any(
            part in _EXCLUDE_DIR_PARTS
            or part.startswith(".")
            or part.endswith("egg-info")
            or part.startswith("pytest-cache-files")
            for part in parts
        ):
            continue
        if p.name in _EXCLUDE_FILE_NAMES:
            continue
        files.append(p)
    return files


def _decorator_name(dec: ast.expr) -> str:
    if isinstance(dec, ast.Name):
        return dec.id
    if isinstance(dec, ast.Attribute):
        return dec.attr
    return ""


def _module_dict_aliases(tree: ast.Module) -> dict[str, ast.expr]:
    # 模块级 `NAME = <expr>` 类型别名表，供 _is_dict_annotation 递归展开（OptionalDict 等）
    aliases: dict[str, ast.expr] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name):
                    aliases[t.id] = node.value
    return aliases


def _is_dict_annotation(node: Union[ast.expr, None], aliases: dict[str, ast.expr], depth: int = 0) -> bool:
    # 注解是否「返回 dict（含 dict|None 联合）」。递归展开模块别名；深度兜底防自引用别名死循环。
    if node is None or depth > 6:
        return False
    if isinstance(node, ast.Subscript):
        # dict[str, object] / collections.OrderedDict[...] 等——按 value 主体判定
        return _is_dict_annotation(node.value, aliases, depth + 1)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
        return _is_dict_annotation(node.left, aliases, depth + 1) or _is_dict_annotation(node.right, aliases, depth + 1)
    if isinstance(node, ast.Name):
        if node.id == "dict":
            return True
        if node.id in aliases:
            return _is_dict_annotation(aliases[node.id], aliases, depth + 1)
        # 命名兜底：本仓类型别名统一以 ...Dict 结尾（OptionalDict/OptionalStreamDict）
        return "dict" in node.id.lower()
    return False


def test_trace_error_decorator_contract_across_repo() -> None:
    violations: list[str] = []
    # 本用例原本是「扫到了多少」零见证的纯遍历——两个 `except …: continue`
    # 让出问题的文件静默出局，且只断言 violations 为空，于是给两个装饰器改名（含全部调用点）会让
    # 扫描命中数归零、violations 恒空、门禁全绿而该两条防线同时消失。现固定三件见证：
    # 扫描文件数、命中装饰器的函数数、未能读取/解析的文件数。阈值取现实测值的保守下界
    # （2026-09-23 实测：文件 >150、装饰函数 86），放宽不误红，收紧到「扫不到东西」时才红。
    unscanned: list[str] = []
    scanned_files = 0
    decorated_functions = 0
    files = _iter_py_files()
    assert len(files) > 100, f"扫描面异常（{len(files)} 个文件），_iter_py_files 的排除口径可能把仓库筛空了"
    for path in files:
        try:
            src = path.read_text(encoding="utf-8-sig")
        except (OSError, UnicodeDecodeError) as exc:
            # 不再 continue：读不到的文件必须体现在判定里，否则「整目录读失败」＝「全绿」
            unscanned.append(f"{path.relative_to(ROOT)}: 读取失败 {type(exc).__name__}: {exc}")
            continue
        try:
            tree = ast.parse(src, filename=str(path))
        except SyntaxError as exc:
            unscanned.append(f"{path.relative_to(ROOT)}: 解析失败 {exc}")
            continue
        scanned_files += 1
        lines = src.splitlines()
        aliases = _module_dict_aliases(tree)
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) or not node.decorator_list:
                continue
            dec_names = [_decorator_name(d) for d in node.decorator_list]
            hit = [d for d in node.decorator_list if _decorator_name(d) in _DEC_NAMES]
            if not hit:
                continue
            decorated_functions += 1
            rel = path.relative_to(ROOT)
            # ② 装饰器必须紧贴 def：def 上一行必须是某个装饰器行（@ 开头），
            #    且从第一个本装饰器到 def 之间的每一行都不允许是注释。
            prev_line = lines[node.lineno - 2] if node.lineno >= 2 else ""
            if not prev_line.lstrip().startswith("@"):
                violations.append(f"{rel}:{node.lineno} {node.name}: @decorator 未紧贴 def（中间夹了空行/其它语句?）")
            first_hit_line = min(d.lineno for d in hit)
            for ln in range(first_hit_line, node.lineno):
                if lines[ln - 1].strip().startswith("#"):
                    violations.append(
                        f"{rel}:{ln} {node.name}: @decorator 与 def 之间夹注释——装饰器绑定点极易误判（CR-12 形态）"
                    )
            # ① 返回注解 -> 装饰器配对（无注解的测试桩函数不判）
            if node.returns is None:
                continue
            has_dict = _is_dict_annotation(node.returns, aliases)
            ann_src = ast.get_source_segment(src, node.returns) or "?"
            if DEC_DICT in dec_names and not has_dict:
                violations.append(
                    f"{rel}:{node.lineno} {node.name}: 注解 {ann_src!r} 非 dict，却挂 {DEC_DICT}"
                    f"（失败值 dict 会伪装成正常结果，须改 {DEC_NONE}）"
                )
            if DEC_NONE in dec_names and has_dict:
                violations.append(
                    f"{rel}:{node.lineno} {node.name}: 注解 {ann_src!r} 含 dict，却挂 {DEC_NONE}"
                    f"（dict 返回契约应统一用 {DEC_DICT} 的 is_live 兜底）"
                )
    assert scanned_files == len(files), "存在静默出局的文件: " + "; ".join(unscanned)
    # 命中数见证：装饰器被改名 / 判定名写错时，violations 会「因为什么都扫不到」而为空。
    # 40 是本仓装饰函数数的下界守卫（2026-09-23 实测 86：spider.py 70 + stream.py 10 + 测试桩），
    # 装饰器改名或 _DEC_NAMES 被清空都会立刻让它变红。
    assert decorated_functions >= 40, (
        f"只扫到 {decorated_functions} 个挂了兜底装饰器的函数（下界 40）："
        "装饰器被改名、_DEC_NAMES 与源码脱节，或扫描面被排除规则吃掉——本门禁已在自我证明之外"
    )
    assert not violations, "兜底装饰器契约违规：\n" + "\n".join(violations)


def test_decorator_names_are_still_defined_and_used() -> None:
    # 与上一条互补的**指向性**锁：若有人把装饰器改名后连本文件的 _DEC_NAMES 一起改掉，命中数
    # 守卫就可能救不回来（两个名字都换新、新名字同样挂满全仓 → 命中数不降）。这条额外钉住
    # 「判定名确实定义在 src/utils.py、且仓库里仍有 @该名 的挂点」，让「改名 + 同步改测试」
    # 不能一次性骗过两面。
    utils_src = (ROOT / "src" / "utils.py").read_text(encoding="utf-8-sig")
    corpus = chr(10).join(path.read_text(encoding="utf-8-sig", errors="replace") for path in _iter_py_files())
    for name in sorted(_DEC_NAMES):
        assert (
            f"def {name}" in utils_src
        ), f"src/utils.py 里已无 {name} 的定义：判定名需同步更新（并同步 AGENTS.md CR-12 条目）"
        assert f"@{name}" in corpus, f"仓库里已无 @{name} 挂点：要么平台函数全删了，要么装饰器改了名"
