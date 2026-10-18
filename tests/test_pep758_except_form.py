# 常驻门禁：PEP 758 无括号多异常写法的形态锁（CODE_REVIEW_2026-10-18 §7.11 第③条）。
#
# 为什么需要它：AGENTS.md 把「本仓统一写 `except A, B:`（无括号、不带 as）」定为**风格约定**而非
# 门禁强制，并且明令「存量带括号写法不要为对齐而批量改动」——因为批量加括号会让 black / mypy /
# 注释检查三面全绿地造出一大片无意义 diff（`ast.dump` 对两种形态给出**完全相同**的结果，这正是
# 「注释检查工具」条目里登记的盲点①）。既然 AST 看不见，防误改就只能靠「按源码文本分类 + 计数棘轮」。
#
# 三条判据：
#   ① 全仓 .py 必须能被**当前解释器（3.14+）**整树解析——把「用 3.13 跑 compileall 会把无括号形态
#      误报成 SyntaxError」这条反复出现的排查坑固化成锁（AGENTS.md「已知坑·类型检查」同条）。
#   ② 无括号多异常处理器数量不得低于 `_BARE_MULTIPLE_BASELINE`——有人批量加括号时该计数会骤降即红；
#      刻意**不设上限**：新增代码按约定就该写无括号形态，计数上升是合规方向。
#   ③ `except A, B as e:`（无括号 + as）在本仓目标版本必须是**语法错误**。它没法做成 lint 规则
#      （解析阶段就炸），但把它做成一条断言有真实价值：哪天运行时/目标版本允许了这形态，本锁会红，
#      逼回来重审「带 as 时必须加括号」这条约定，而不是让新形态静默扩散。
#
# 分类为什么能免疫注释与字符串：判据取 AST 定位到的 ExceptHandler，再用 ast.get_source_segment 回取
# 该 handler.type 的**源码文本**——3.14.8 实测 `except (A, B) as e:` 的段文本带前导 `(`、
# `except A, B:` 的不带，因此括号形态可由 AST 位置直接判定，不必扫全文正则。
import ast
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent
_EXCLUDED_PARTS = {
    ".git",
    ".venv",
    "node",
    "ffmpeg",
    "build",
    "dist",
    "__pycache__",
    ".workbuddy",
    ".qoder",
    ".qoder-credits",
    "node_modules",
    "typings",
    "downloads",
    "logs",
    "backup_config",
    ".agents",
    ".superpowers",
}
# ②的基线：2026-10-18 由**本锁自己的 AST 分类器**实测得到 61 处带括号 43 处（同口径复算：
# 跑 `_classify(_scan_roots())` 读 len(bare)）。
# [实测注] 首版基线 60 是先用行正则粗扫得到的，与 AST 分类器不同源——变异验证当场发现「摘掉一处
# 无括号形态」仍判绿（61→60 ≥ 60 恒真）。正则漏掉 1 处无括号 / 2 处带括号，成因是行尾带注释与
# 跨行写法；判据与其基线必须由**同一个分类器**产出，否则棘轮天生带一条松缝。
# 复算命令写在这里，读数过期时重跑而不是凭印象改：
#   PYTHONUTF8=1 python -c "import importlib.util as u;s=u.spec_from_file_location('p','tests/test_pep758_except_form.py');m=u.module_from_spec(s);s.loader.exec_module(m);print(len(m._classify(m._scan_roots())[0]))"
_BARE_MULTIPLE_BASELINE = 61


def _scan_roots() -> list[Path]:
    return [p for p in _REPO_ROOT.rglob("*.py") if not (set(p.parts) & _EXCLUDED_PARTS)]


def _classify(files: list[Path]) -> tuple[list[str], list[str], list[str]]:
    # 返回 (无括号多异常站点, 带括号多异常站点, 无括号 yet 带 as 的违例站点)。
    bare: list[str] = []
    paren: list[str] = []
    illegal: list[str] = []
    for path in files:
        rel = str(path.relative_to(_REPO_ROOT)).replace("\\", "/")
        text = path.read_text(encoding="utf-8")
        tree = ast.parse(text)
        for node in ast.walk(tree):
            if not isinstance(node, ast.ExceptHandler) or not isinstance(node.type, ast.Tuple):
                continue
            if len(node.type.elts) < 2:
                continue
            seg = ast.get_source_segment(text, node.type) or ""
            if seg.lstrip().startswith("("):
                paren.append(f"{rel}:{node.lineno}")
            else:
                bare.append(f"{rel}:{node.lineno}")
                if node.name:
                    illegal.append(f"{rel}:{node.lineno}")
    return bare, paren, illegal


def test_repo_parses_under_the_running_interpreter() -> None:
    # 判据①：整树解析。用错解释器（3.13）时这里会成片报错，正是本仓踩过的排查坑。
    broken: list[str] = []
    for path in _scan_roots():
        try:
            ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError as exc:
            broken.append(f"{path.relative_to(_REPO_ROOT)}: {exc.msg}@{exc.lineno}")
    assert not broken, f"以下文件在当前解释器下解析失败: {broken}"


def test_bare_multiple_except_form_is_not_mass_converted() -> None:
    # 判据②：无括号形态计数只降不得（降 = 有人为「对齐风格」批量加括号，制造 AST 隐形的整片 diff）。
    bare, paren, _illegal = _classify(_scan_roots())
    assert len(bare) >= _BARE_MULTIPLE_BASELINE, (
        f"无括号多异常处理器由基线 {_BARE_MULTIPLE_BASELINE} 降到 {len(bare)}——"
        "AGENTS.md 明令存量带括号不为对齐而批量改，反向批量加括号同样禁止（black/mypy/注释检查三面对此全隐形）"
    )
    # 反向见证：两类形态都必须真实存在，否则分类器失明时上面那条会恒真。
    assert bare, "分类器一个无括号形态都没看到，判据已失效"
    assert paren, "分类器一个带括号形态都没看到，判据已失效"


def test_unparenthesized_with_as_is_a_syntax_error_on_target_version() -> None:
    # 判据③：这条把「有 as 就必须加括号」从口头约定钉成可执行事实。
    _bare, _paren, illegal = _classify(_scan_roots())
    assert not illegal, f"出现 `except A, B as e:` 形态（解析期即应报错，说明解释器口径已变）: {illegal}"
    with pytest.raises(SyntaxError):
        ast.parse("try:\n    pass\nexcept TypeError, ValueError as e:\n    pass\n")


def test_classifier_separates_the_four_forms() -> None:
    # 自检（防空转）：四种写法必须各归其类——尤其是「无括号/带括号」这一对，AST 结构完全相同。
    cases = {
        "try:\n     pass\n except TypeError, ValueError:\n     pass\n": "bare",
        "try:\n     pass\n except (TypeError, ValueError):\n     pass\n": "paren",
        "try:\n     pass\n except (TypeError, ValueError) as e:\n     pass\n": "paren",
        "try:\n     pass\n except TypeError as e:\n     pass\n": "single",
    }
    got: list[str] = []
    for text, _label in cases.items():
        # 上面样例为嵌在测试里的对照串，去掉缩进后按真实形态解析。
        tree = ast.parse(text.replace("\n ", "\n"))
        handler = next(n for n in ast.walk(tree) if isinstance(n, ast.ExceptHandler))
        if not isinstance(handler.type, ast.Tuple) or len(handler.type.elts) < 2:
            got.append("single")
            continue
        seg = ast.get_source_segment(text.replace("\n ", "\n"), handler.type) or ""
        got.append("paren" if seg.lstrip().startswith("(") else "bare")
    assert got == ["bare", "paren", "paren", "single"], f"形态分类失效: {got}"
