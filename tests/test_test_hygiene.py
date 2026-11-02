# 静态守卫：全仓 tests/*.py 的「测试可信度」门禁（MID-64/65/66/67 沉淀）。
#
# 为什么用 AST 而不是运行时用例：这几类缺陷的共同征兆是「用例全绿但什么都没证明」
# 或「用一例拖挂整个会话」，征兆只在**别的**用例身上显现（进程级 stdlib 被改写、GC 延迟
# 抛出的告警逸出到任意后续用例），靠人眼 grep 一定会漏。本文件不 import 任何被测模块，
# 只读源码文本 + ast.parse，因此自身零副作用、秒级完成。
#
# 九条规则（R1–R4 + R6–R10；R5 全仓无定义，是跳号而非漏实现——2026-09-23 按 grep 核对）：
#   [历史注] 本行计数历经两轮证伪修正（曾写「五条」、后写「六条」漏计 R8），现按实际规则数固定为九条；
#   R8 与 R7 同日（2026-09-30）新增却一度漏登记。按 AGENTS.md「注释约定」的「被证伪的事实
#   性陈述改正正文」例外处理。
#   R1 禁止改写 stdlib / 第三方模块本体（两种形态同罪，SEV-2225 补齐第二种）：
#      a) 经「别的模块的命名空间」拿到模块对象再 setattr：monkeypatch.setattr(main.time, "sleep", ...)
#         改的是全进程唯一的那个 time 模块本体，loguru enqueue 线程 / harness 守护线程 / coverage
#         都会吃到假实现（MID-66 的 10 处实例）。
#      b) 字符串形态 patch("subprocess.Popen") / patch("time.sleep")：mock 与 monkeypatch 都会先
#         按导入根 importlib 出那个 stdlib 模块对象、再 setattr 到它**本体**上，与 a) 完全同形。
#      正确写法见 AGENTS.md「测试编写强制约定」：types.SimpleNamespace(**vars(mod)) 浅拷贝后
#      setattr(模块, "名", shim)（即只替换**被测模块命名空间里的全局引用**）。
#   R2 禁止宽泛 filterwarnings("ignore::<整类告警>")（本仓「pytest 0 警告口径」要求修根因）。
#   R3 名为 known_hash / known_answer / *_kat 的用例必须断言**具体字面值**，
#      只断 isinstance/len 即假绿（MID-67 的 SM3 实例）。
#   R4 tests/ 目录里不得留下一次性调试产物（MID-64/66 排查期写下的 _exc.log 一类残留）。
#   R6 手工 pytest.MonkeyPatch() 实例必须配对 undo()：pytest 不会自动还原它们，
#      漏 undo 的用例**单独运行**永远是对的，只有全量跑才暴露成跨文件假失败。
#   R7 真机 collector 脚本 `tests/test_*_live_collector.py` 必须守「双模式模板」四条，
#      逐条 AST 判定（不用自然语言子串，改文案不会让门禁失效）：
#      ① 模块级存在 `if __name__ == "__main__":` 守卫（左右互换写法都算）且守卫体内真的调用 main()；
#      ② 守卫之外的模块级零副作用（只允许导入 / 常量赋值 / sys.path 注入 / def / class /
#         导入保护 try / docstring 与注释；表达式调用、循环、with、raise、sys.exit、真机连接一律违例）；
#      ③ 从 sys.argv 取数值处必须带「非选项」判定（AGENTS「双模式测试脚本须带 int(sys.argv) 守卫」的
#         机器化——否则 `pytest -q -k xxx` 会把 `-k` 当秒数 int() 掉，当场炸在收集期）；
#         [实测后收紧到「数值性判定」] 只判非选项仍挡不住：一次点多个文件时 sys.argv[2] 是
#         下一个测试文件的路径，`not startswith("-")` 合规通过、`int(路径)` 当场 ValueError（当时 4 个
#         兄弟脚本集体 errors during collection）。故本条现在要求 isdigit/isnumeric/isdecimal 这一类
#         数值性判定，或整段转换包在 `except ValueError`（Exception/BaseException 同认；只捕
#         TypeError 不算，见 `_R7_INT_ERROR_TYPES`）里；AGENTS 样例的 startswith
#         一支仍保留在脚本源码里（作第一层语义），只是单独出现不再算够。
#      ④ 删输出目录条目不得无差别：既要按产物前缀过滤，又要先判类型/存在性（S-2 的兄弟缺陷形态：
#         清空 tests/_out_live 时混入子目录即抛错、并行验证互删）。
#      为什么值得单独立规：S-2 只修了 test_twitch_live_collector.py 一个文件、锁也只钉在它身上，
#      管不住「第 6 个真机脚本又被写成模块级」，也管不住另外 4 个脚本的清理越界。
#      已知取舍：③④ 只验「守卫存在且形态正确」，不验守卫与删除目标的变量数据流（与 R3 的
#      `_has_literal_equality` 同一档口径），构造出来的对抗样本仍可绕过，但会改坏模板的真实回归跑不掉。
#
# 例外表 _SANCTIONED 逐条给出理由：AGENTS.md 亲自规定的跨平台写法（config_io.os.replace 的
# 「文件只读」用例）与被守卫的形态同形，门禁不得推翻文档级约定。
# 例外表的键空间：R1 用「被改模块.属性名」（如 os.replace），R7 用规则标签
# "R7①"…"R7④"，两套形态天然不相交，共用一张表不会互相放行；R7 现无条目（5 个真机脚本逐条实测
# 全绿或已修到全绿）。新增条目必须同时写清「为什么这是合规写法」，不得用来掩盖判据自身的误报。
import ast
import re
import sys
from pathlib import Path

import pytest

_TESTS_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _TESTS_DIR.parent
# 经模块命名空间改写这些模块的本体 = 全进程生效，一律禁止。
# stdlib 侧取本仓测试实际踩过的集合 + 常见的「被 main/src 直接引用」的模块；
# 第三方侧 httpx/requests/websockets 同理（main.httpx.Client 即 MID-66 的实例之一）。
# 刻意**不含 sys**：sys.frozen / sys.argv / sys.executable 是解释器状态标志，
# 没有替代手段能进入 PyInstaller 冻结分支等代码路径（tests/test_ttwid.py 的
# TestAppRootFrozen 即靠它），且 monkeypatch 会逐属性还原，不掩盖被测逻辑。
_MUTABLE_MODULE_NAMES = frozenset(
    {
        "time",
        "os",
        "datetime",
        "subprocess",
        "random",
        "shutil",
        "socket",
        "signal",
        "threading",
        "json",
        "logging",
        "math",
        "re",
        "httpx",
        "requests",
        "aiohttp",
        "websockets",
        "PIL",
    }
)
# 字符串形态 patch("<名>.<路径>") 的判定子集：只取名单里确属标准库的那些名字。
# 为什么不整份复用 _MUTABLE_MODULE_NAMES（三方名也在其中）：判据要表达的是「改的是不是
# 全进程唯一的 stdlib 模块本体」，而 httpx/requests/PIL 等三方模块被 patch 的是**它们自己包
# 内的属性**，危害面不同；现网仍有 6 处 patch("httpx.AsyncClient")（tests/test_async_http_lock.py，
# 不属本条目范围）未迁，直接按整份名单判会让别人负责的文件无故变红。
# 取 sys.stdlib_module_names（3.10+ 提供）而不是再手写一份名字清单，避免第二事实源。
# **已知未覆盖面（不得读成「已全覆盖」）**：patch("src.x.time.sleep") 这类「首段是被测模块、
# 中间段才是 stdlib 模块」的深路径同样改到 time 本体，现网 11+ 处（SEV-2225 的兄弟形态），
# 本规则按首段判定、不覆盖它 —— **不覆盖 ≠ 合规**，扩判据前必须先迁完那些调用点。
_STDLIB_MUTABLE_NAMES = frozenset(_MUTABLE_MODULE_NAMES) & sys.stdlib_module_names
# R3 的触发词：只认「哈希/标准答案」类命名，避免把普通枚举用例误判成 KAT
_KAT_NAME_PREFIXES = ("test_known_hash", "test_known_answer", "test_kat", "test_known_vector")
# tests/ 下允许存在的非 .py 正式资产（黄金基准与前端用例目录）；其余按一次性产物处理。
# 2026-09-24 收敛：删去 `_out_e2e` —— 唯一写它的 tests/test_srt_timeline_anchor.py 已改走
# tmp_path，`tests/conftest.py::_TEST_OUT_DIRS` 也同步不再清理它；保留 `_out_live` 是因为
# 五个 `test_*_live_collector.py` 双模式脚本（含真机验证）仍往该目录写 SRT。
# 注意（避免误读成本次改动有行为变化）：下方 R4 的谓词只筛 `.is_file()` 且 `suffix == ".py"`
# 的条目，目录名在此处不参与判定（它们只在 `_TEST_OUT_DIRS` 那边才承担清理语义），
# 所以本项收敛是「名单与实际写入方对齐」，不是放宽门禁。
_ALLOWED_TESTS_ENTRIES = frozenset({"__init__.py", "conftest.py", "__pycache__", "golden", "frontend", "_out_live"})
_SANCTIONED: dict[str, frozenset[str]] = {
    # AGENTS.md「『文件只读』用例不能只靠 chmod(0o444)」条目明文规定的写法：
    # os.replace 是 config_io 原子写的唯一失败点，Windows/Linux 语义不同，只能在此处拦截；
    # 该条目同时要求「其余路径透传真实 os.replace」，影响面受控。
    "test_config_io_readonly.py": frozenset({"os.replace"}),
}


def _test_files() -> list[Path]:
    # 只扫 tests/ 顶层正式用例；tests/frontend/*.mjs 是 Node 用例，不在本门禁范围内
    return sorted(p for p in _TESTS_DIR.glob("test_*.py") if p.is_file())


def _dotted_name(node: ast.AST) -> str | None:
    # a.b.c -> "a.b.c"；下标/调用等复杂表达式返回 None
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = _dotted_name(node.value)
        return None if base is None else base + "." + node.attr
    return None


def _is_setter(fname: str | None) -> bool:
    # setattr 家族：setattr(obj, "name", v) / monkeypatch.setattr(...) / mock.patch.object(...)
    # —— 约定第一参是「被改的容器」、第二参是属性名字面量，故容器是模块对象时就构成 R1 违例。
    if fname is None:
        return False
    return fname == "setattr" or fname.endswith(".setattr") or fname.endswith("patch.object")


def _is_dotted_target_call(fname: str | None) -> bool:
    # 首参是「点路径字符串」的替身写法：patch("a.b") / mock.patch("a.b") /
    # monkeypatch.setattr("a.b", v) —— 三者都先解析出 a.b 的**容器对象**再 setattr。
    # 刻意不含 patch.object(obj, "name")：它的 obj 是 AST 里的真模块对象，走 _is_setter 那一支。
    if fname is None:
        return False
    return fname == "patch" or fname.endswith(".patch") or fname.endswith(".setattr")


def _stdlib_body_key_from_dotted(target: ast.expr) -> str | None:
    # R1 的字符串形态：返回违规键 "subprocess.Popen"，合规时 None。
    # 判据只看**首段**：mock/monkeypatch 解析 "a.b.c" 时会 importlib 出顶层包 a、沿 getattr 链
    # 走到 a.b，最后 setattr(a.b, "c", 替身)。故 a 是 stdlib 顶层模块名时，被改对象就是
    # 全进程唯一的 stdlib 模块本体 —— 与被拦下的 setattr(模块对象, "c", ...) 同形同害。
    if not isinstance(target, ast.Constant) or not isinstance(target.value, str):
        return None
    parts = target.value.split(".")
    if len(parts) < 2:
        return None
    if parts[0] not in _STDLIB_MUTABLE_NAMES:
        return None
    return target.value


def _module_body_mutation_calls(tree: ast.Module) -> list[tuple[int, str]]:
    # R1：返回 [(行号, "被改模块.属性名"), ...]
    out: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not node.args:
            continue
        fname = _dotted_name(node.func)
        target = node.args[0]
        # 两支的分流判据是「首参是不是点路径字符串」，不是函数名：
        # monkeypatch.setattr 同时出现在两支里（setattr("time.sleep", v) 是字符串形态、
        # setattr(main.time, "sleep", v) 是对象形态），早期实现按函数名互斥处理，
        # 会让后者整条被 continue 掉——R1 的原有 setattr 判据当场失效（由
        # test_guard_actually_catches_the_patterns 抓到，勿再改回去）。
        if _is_dotted_target_call(fname) and isinstance(target, ast.Constant) and isinstance(target.value, str):
            key = _stdlib_body_key_from_dotted(target)
            if key is not None:
                out.append((node.lineno, key))
            continue
        if not _is_setter(fname):
            continue
        # 对象形态只认 setattr(obj, "name")（obj 必须是属性访问，如 main.time / config_io.os）
        #   [历史注] 2026-09-23 前此处写着「字符串形态在本仓未使用」，实测相反（test_main_fixes /
        #   test_spider_fixes 共 6 处 patch("subprocess.Popen"|"subprocess.run") 在用），
        #   字符串形态已由上面的首支判据接管。
        if not isinstance(target, ast.Attribute):
            continue
        owner = target.attr  # main.time -> "time"；config_io.os -> "os"
        if owner not in _MUTABLE_MODULE_NAMES:
            continue
        attr = ""
        if len(node.args) > 1 and isinstance(node.args[1], ast.Constant) and isinstance(node.args[1].value, str):
            attr = str(node.args[1].value)
        out.append((node.lineno, f"{owner}.{attr}"))
    return out


def _broad_filterwarnings_calls(tree: ast.Module) -> list[tuple[int, str]]:
    # R2：pytest.mark.filterwarnings 里出现整类/全量 ignore
    out: list[tuple[int, str]] = []
    broad = (
        "RuntimeWarning",
        "UserWarning",
        "Warning",
        "DeprecationWarning",
        "PendingDeprecationWarning",
        "WarningMessage",
    )
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or _dotted_name(node.func) != "pytest.mark.filterwarnings":
            continue
        for arg in node.args:
            text = arg.value if isinstance(arg, ast.Constant) and isinstance(arg.value, str) else None
            if text is None:
                out.append((node.lineno, "<非字面量参数，无法审计>"))
                continue
            if not text.startswith("ignore"):
                continue
            # 「ignore:具体消息:具体告警类」是精确过滤，允许；整类 / 无类别 / 全量禁止。
            # 注意 filterwarnings 的完整语法是 action:message:category:module:lineno，
            # 「ignore::RuntimeWarning」split 后 message 为空、category 在第 3 段——
            # 早期实现只按 "::" 切，会把 ignore:msg:ResourceWarning 这种精确过滤误判为宽泛。
            parts = text.split(":")
            category = parts[2].strip() if len(parts) > 2 else ""
            if not category or category in broad or category == "Exception":
                out.append((node.lineno, text))
    return out


def _has_literal_equality(func: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    # KAT 断言的最低门槛：存在一次 Eq 比较，且比较对象不是「整数/布尔字面量」——
    # 于是 isinstance(x, str) + len(x) == 64 这种假绿形态不算数，
    # 而 x == "66c7f0..."（字面摘要）与 x == digest（参数化进来的模块级字面量表）都算。
    # 局限：只比对两个变量的 r1 == r2 也会被放行，所以触发词刻意只认 known_hash/known_answer/
    # kat/known_vector 前缀（这类命名才承诺「外部标准答案」）。
    for node in ast.walk(func):
        if not isinstance(node, ast.Compare):
            continue
        if not any(isinstance(op, ast.Eq) for op in node.ops):
            continue
        operands = [node.left, *node.comparators]
        for operand in operands:
            if isinstance(operand, ast.Constant):
                if isinstance(operand.value, str) or isinstance(operand.value, bytes):
                    return True
                continue  # int/bool/None 字面量：len()==64 之类不算真值断言
            if isinstance(operand, ast.Name):
                return True
            if isinstance(operand, ast.Subscript):
                return True
    return False


def _fake_kat_funcs(tree: ast.Module) -> list[tuple[int, str]]:
    # R3：自称「已知标准值」却没有任何字面等价断言的用例
    out: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if not any(node.name.startswith(p) for p in _KAT_NAME_PREFIXES):
            continue
        if not _has_literal_equality(node):
            out.append((node.lineno, node.name))
    return out


@pytest.mark.parametrize("path", _test_files(), ids=lambda p: p.name)
def test_no_stdlib_module_body_mutation(path: Path) -> None:
    # R1 回归锁（MID-66 的 setattr 形态 + SEV-2225 的字符串形态）：实例已改为浅拷贝 shim，此处防止再被写回来
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    allowed = _SANCTIONED.get(path.name, frozenset())
    hits = _module_body_mutation_calls(tree)
    offenders = [(ln, key) for ln, key in hits if key not in allowed]
    assert not offenders, (
        f"{path.name} 改写了 stdlib 模块本体（全进程生效：harness 守护线程 / loguru enqueue 线程 / coverage "
        f"都会吃到假实现；patch('subprocess.Popen') 这类字符串形态与 setattr(模块.time, 'sleep', ...) 同罪）。"
        f"须改 types.SimpleNamespace(**vars(mod)) 浅拷贝后 setattr(被测模块, 名, shim): "
        + ", ".join(f"第{ln}行 {key}" for ln, key in offenders)
    )


@pytest.mark.parametrize("path", _test_files(), ids=lambda p: p.name)
def test_no_broad_filterwarnings(path: Path) -> None:
    # R2 回归锁（MID-65）：全仓唯一一处 ignore::RuntimeWarning 已移除并修根因（在
    # tests/test_async_http_lock.py）。宽泛过滤之所以禁止：协程类告警由 GC 延迟触发、会逸出到
    # 任意后续用例，ignore 既拦不住也顺手吃掉「实现里真有个 never-awaited 协程」这个缺陷；
    # 精确到消息 + 类别的 ignore 不在禁止之列（判据见 _broad_filterwarnings_calls 的分段口径）。
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    hits = _broad_filterwarnings_calls(tree)
    assert not hits, f"{path.name} 使用宽泛 filterwarnings（0 警告口径要求修根因）: " + ", ".join(
        f"第{ln}行 {text!r}" for ln, text in hits
    )


@pytest.mark.parametrize("path", _test_files(), ids=lambda p: p.name)
def test_digest_reference_tests_pin_concrete_values(path: Path) -> None:
    # R3 回归锁（MID-67）：SM3 那条假绿已补真值，此处防同类「只断长度」再出现
    # （函数名刻意不以 test_known_hash 开头，否则本门禁会扫到自己）
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    hits = _fake_kat_funcs(tree)
    assert not hits, f"{path.name} 的 known-hash/KAT 用例没有字面值断言（任何实现都能过）: " + ", ".join(
        f"第{ln}行 {name}" for ln, name in hits
    )


def test_no_stray_debug_artifacts_in_tests_dir() -> None:
    # R4：一次性排查产物（_exc.log / *.tmp / 临时脚本）不得留在 tests/。
    # 本条同时是自我约束——门禁自身若开始写文件，下一轮就会变红。
    stray = [
        p.name
        for p in _TESTS_DIR.iterdir()
        if p.is_file() and p.name not in _ALLOWED_TESTS_ENTRIES and not p.name.startswith("test_") and p.suffix == ".py"
    ]
    # 只拦「.py 但不是 test_ 前缀」的临时脚本 + 已知调试日志后缀，避免误伤 README 类文档
    stray += [p.name for p in _TESTS_DIR.glob("*.log") if p.is_file()]
    assert not stray, f"tests/ 下存在一次性调试产物（收尾须删除）: {sorted(set(stray))}"


def test_guard_actually_catches_the_patterns() -> None:
    # 自检：门禁不得退化成「扫不到任何东西的绿灯」。用等价违规片段逐条验证能报。
    bad_r1 = ast.parse('monkeypatch.setattr(main.time, "sleep", lambda s: None)\n')
    bad_r2 = ast.parse('@pytest.mark.filterwarnings("ignore::RuntimeWarning")\ndef test_x():\n    pass\n')
    bad_r3 = ast.parse(
        "def test_known_hash():\n    result = SM3().sum('abc', output_format='hex')\n    assert len(result) == 64\n"
    )
    assert _module_body_mutation_calls(bad_r1) == [(1, "time.sleep")], "R1 失效：setattr(main.time, ...) 未被发现"
    assert _broad_filterwarnings_calls(bad_r2), "R2 失效：ignore::RuntimeWarning 未被发现"
    assert _fake_kat_funcs(bad_r3), "R3 失效：只断长度的 KAT 用例未被发现"
    # 反向自检：合规写法不得误报（浅拷贝 shim / 命名空间重绑 / 精确过滤 / 带真值的 KAT）
    good_r1 = ast.parse('monkeypatch.setattr(main, "time", shim)\n')
    # patch("src.spider.time") 是把 src.spider 命名空间里的 time 重绑为替身，不改 stdlib 本体
    good_r1b = ast.parse('patch.object(spider, "time", shim)\n')
    good_r2 = ast.parse('@pytest.mark.filterwarnings("ignore:by e:ResourceWarning")\ndef test_x():\n    pass\n')
    good_r3 = ast.parse("def test_known_hash():\n    assert md5('hello') == '5d41402abc4b2a76b9719d911017c592'\n")
    # 参数化 KAT：期望值来自模块级字面量表，比较对象是变量名——同样视为已钉死
    good_r3b = ast.parse(
        "def test_known_hash(msg, digest):\n    assert SM3().sum(msg, output_format='hex') == digest\n"
    )
    assert not _module_body_mutation_calls(good_r1), "R1 误报：浅拷贝 shim 写法被拦"
    assert not _module_body_mutation_calls(good_r1b), "R1 误报：项目模块命名空间重绑被拦"
    assert not _broad_filterwarnings_calls(good_r2), "R2 误报：精确过滤被拦"
    assert not _fake_kat_funcs(good_r3), "R3 误报：真值 KAT 被拦"
    assert not _fake_kat_funcs(good_r3b), "R3 误报：参数化 KAT 被拦"
    # R7 四条判据各喂一段最坏的模块级形态，断言必红；
    # 「合规不误报」与「只破坏一条时另三条不连坐」的完整见证在
    # test_guard_r7_actually_catches_template_violations / test_guard_r7_accepts_equivalent_compliant_spellings。
    bad_r7 = ast.parse(
        "import os\nimport sys\n\n"
        'sys.path.insert(0, ".")\n\n'
        'URL = sys.argv[1] if len(sys.argv) > 1 else "x"\n'
        "SECONDS = int(sys.argv[2])\n"
        "for _name in os.listdir('.'):\n"
        "    os.remove(_name)\n"
        "os.makedirs('_out_live', exist_ok=True)\n"
    )
    bad_r7_violations = _r7_violations(bad_r7)
    assert bad_r7_violations["R7①"], "R7 失效：没有 __main__ 守卫未被发现"
    assert bad_r7_violations["R7②"], "R7 失效：模块级 for / makedirs 未被发现"
    assert bad_r7_violations["R7③"], "R7 失效：无守卫的 int(sys.argv[2]) 未被发现"
    assert bad_r7_violations["R7④"], "R7 失效：无差别 os.listdir + os.remove 未被发现"


def test_guard_catches_string_form_stdlib_module_patch() -> None:
    # SEV-2225 的反向见证（防「新判据自己就是假绿」）：合成样本里三种字符串形态改写 stdlib
    # 模块本体都必须被报出。逐条断言**具体键**，不只看「有没有报」——
    # 只断非空会让「把 os.replace 误报成 subprocess.Popen」这类判据错位照样通过。
    bad_popen = ast.parse('with patch("subprocess.Popen", return_value=fake):\n    pass\n')
    bad_run = ast.parse('with patch("subprocess.run", side_effect=fake_run):\n    pass\n')
    # monkeypatch.setattr 的点路径首参同罪：解析后 setattr 的容器就是 stdlib 模块本体
    bad_mp_setattr = ast.parse('monkeypatch.setattr("time.sleep", lambda s: None)\n')
    want_popen = [(1, "subprocess.Popen")]
    want_run = [(1, "subprocess.run")]
    want_mp = [(1, "time.sleep")]
    assert _module_body_mutation_calls(bad_popen) == want_popen, "R1 失效：patch('subprocess.Popen') 未被发现"
    assert _module_body_mutation_calls(bad_run) == want_run, "R1 失效：patch('subprocess.run') 未被发现"
    assert _module_body_mutation_calls(bad_mp_setattr) == want_mp, "R1 失效：setattr('time.sleep', ...) 未被发现"


def test_guard_allows_module_namespace_shim_for_subprocess() -> None:
    # SEV-2225 的合规侧见证：仓内规定范式（浅拷贝 + 只换被测模块命名空间里的引用）不得被误报，
    # 否则这条判据会把 test_record_failure_feedback.py / test_main_fixes.py 迁移后的写法一起打死，
    # 后来者只会把判据删掉而不是改写法。
    good_shim = ast.parse(
        "shim = types.SimpleNamespace(**vars(subprocess))\n"
        "shim.Popen = FakePopen\n"
        'monkeypatch.setattr(video_postprocess, "subprocess", shim)\n'
    )
    # 字符串形态、但被改容器是**项目模块自身的属性**（现网主流写法，如 patch("src.spider.async_req")）：
    # 改的是 src.spider 命名空间里的名字，不涉及 stdlib 本体
    good_dotted_project_root = ast.parse('patch("src.spider.async_req", new=fake_req)\n')
    # patch.object 的容器是 AST 里的真模块对象、不是字符串，走另一支判据
    good_patch_object = ast.parse('with patch.object(utils, "subprocess", shim):\n    pass\n')
    assert not _module_body_mutation_calls(good_shim), "R1 误报：浅拷贝 shim + 换被测模块全局引用的合规写法被拦"
    assert not _module_body_mutation_calls(good_dotted_project_root), "R1 误报：首段为被测模块的点路径替身被拦"
    assert not _module_body_mutation_calls(good_patch_object), "R1 误报：patch.object(项目模块, ...) 被拦"


def test_scan_root_is_not_empty() -> None:
    # 兜底：路径解析错位时 glob 会扫到 0 个文件、三条参数化用例集体「空跑通过」——
    # 正是本文件要消灭的假绿形态，故显式断言扫描根与文件数。
    files = _test_files()
    assert len(files) > 50, f"tests/ 用例文件数异常（{len(files)}），扫描根目录可能错位: {_TESTS_DIR}"
    assert (_REPO_ROOT / "main.py").exists()


def _manual_monkeypatch_violations(tree: ast.AST) -> list[str]:
    # R6：手工 `pytest.MonkeyPatch()` 实例不会被 pytest 自动还原，必须自己 undo()。
    # 本仓已因此付出过一次真实代价：src/sync_http.py 的代理用例在同一会话里发出了
    # 一次未打桩的出站请求（漏 undo 的补丁把 src.utils.handle_proxy_addr 置空，
    # 令代理分支静默落到直连分支），表现为 11 条「跨文件假失败」。
    offenders: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        created = 0
        undone = 0
        for inner in ast.walk(node):
            if not isinstance(inner, ast.Call):
                continue
            func = inner.func
            if isinstance(func, ast.Attribute) and func.attr == "undo":
                undone += 1
            elif (
                isinstance(func, ast.Attribute)
                and func.attr == "MonkeyPatch"
                and isinstance(func.value, ast.Name)
                and func.value.id == "pytest"
            ):
                created += 1
        if created > undone:
            offenders.append(f"{node.name}:{node.lineno} 创建 {created} 个、undo {undone} 个")
    return offenders


@pytest.mark.parametrize("path", _test_files(), ids=lambda p: p.name)
def test_manual_monkeypatch_instances_are_undone(path: Path) -> None:
    # 逐文件判据。漏 undo 的用例在**单独运行**时永远是对的，只有全量跑才暴露——
    # 所以这条必须扫全部 tests/，不能只扫被改文件。
    tree = ast.parse(path.read_text(encoding="utf-8-sig"))
    offenders = _manual_monkeypatch_violations(tree)
    assert not offenders, f"{path.relative_to(_REPO_ROOT)} 有手工 MonkeyPatch 未配对 undo(): {offenders}"


def test_guard_r6_actually_catches_a_leaked_monkeypatch() -> None:
    # 反向见证（防空门禁）：合成一段「创建了却从不 undo」的源码，判据必须报出来；
    # 再给一段配对正确的，必须不报——否则 R6 只是摆设。
    bad = ast.parse("def test_x():\n    mp = pytest.MonkeyPatch()\n    mp.setattr(a, 'b', 1)\n")
    assert _manual_monkeypatch_violations(bad), "R6 判据失效：漏 undo 的形态没被抓到"
    good = ast.parse("def test_y():\n    mp = pytest.MonkeyPatch()\n    mp.setattr(a, 'b', 1)\n    mp.undo()\n")
    assert not _manual_monkeypatch_violations(good), "R6 误报：配对 undo() 的合规写法被拦"


# ---- R7：真机 collector 脚本的「双模式模板」门禁（S-2 的跨文件收口）----
# 扫描根与 _test_files() 分开：这四条只对 tests/test_*_live_collector.py 生效。普通用例没有
# 「既被 pytest 收集、又能被 `python <文件> <URL> <秒数>` 直接跑真机」的双重身份，套上去会大面积误报。
_LIVE_COLLECTOR_GLOB = "test_*_live_collector.py"
# R7②：模块级唯一被放行的表达式调用——sys.path 注入。本仓 5 个真机脚本都靠它定位 src/，
# 去掉就 import 不上；它不写外部状态、不阻塞，与「连平台 / 删文件 / 睡眠 / sys.exit」不同罪。
_R7_SYS_PATH_CALLS = frozenset({"sys.path.insert", "sys.path.append"})
# R7②：模块级赋值的「常量名」形态（AGENTS 双模式模板里的 URL / SECONDS / _SECONDS_RAW 全在此列）。
_R7_CONSTANT_NAME_RE = re.compile(r"^_?[A-Z][A-Z0-9_]*$")
# R7③：把 sys.argv 取来的值转成数值时**必须**出现的「数值性判定」（或等价的 try/except ValueError 包裹）。
# 为什么门禁切在「数值性」而不是 AGENTS 样例里的「非选项」判定：2026-09-30 实测——
# `python -m pytest tests/test_test_hygiene.py tests/test_bili_live_collector.py …` 一次点多个文件时
# sys.argv[2] 是**下一个测试文件的路径**，`not sys.argv[2].startswith("-")` 判它合规、随后
# `int('tests/test_bili_live_collector.py')` 当场抛 ValueError，4 个兄弟脚本集体
# 「4 errors during collection」。与 test_twitch_live_collector.py 里
# 「兄弟脚本仍有此坑，建议同批跟进」那条注释同源。isdigit/isnumeric/isdecimal 同时挡住选项串与路径，
# 所以判据要求这一类；单靠 startswith("-") 视为**不足**（不是合规）。
# 已知残留边界：`"²".isdigit()` 为真而 int("²") 抛错——上标数字属人为构造，不在本门禁射程内。
_R7_NUMERIC_CHECKS = frozenset({"isdigit", "isnumeric", "isdecimal"})
# R7③：数值转换外面包一层 try 时，能真正兜住 int('…') 抛错的异常类型。
# 只认 ValueError/Exception/BaseException——`except TypeError` 兜不住 `int('x')`（那是 ValueError），
# 由 test_guard_r7_accepts_equivalent_compliant_spellings 里的阴性对照钉住这条边界。
_R7_INT_ERROR_TYPES = frozenset({"ValueError", "Exception", "BaseException"})
# R7④：算「按产物前缀过滤」的判定调用尾段。
_R7_PREFIX_FILTERS = frozenset({"startswith", "fnmatch", "match", "fullmatch"})
# R7④：算「先判目标类型 / 是否存在」的判定调用尾段。
_R7_KIND_CHECKS = frozenset({"isfile", "is_file", "isdir", "is_dir", "exists", "lexists"})
# R7④：整目录删除调用——无论落在哪儿都属「无差别」形态，一律要求守卫。
_R7_TREE_DELETES = frozenset({"shutil.rmtree", "os.rmdir"})
# R7④：单文件删除调用——只在「遍历目录的循环」内才算无差别清空；
# 定点删某个已知路径（如重跑前删自己的旧 SRT）不是本条针对的风险形态，误拦会逼人放宽判据。
_R7_FILE_DELETES = frozenset({"os.remove", "os.unlink"})
# R7④：判定「这个循环正在遍历目录」的调用尾段。
_R7_DIR_SCAN_CALLS = frozenset({"listdir", "scandir", "iterdir", "glob", "iglob"})


def _live_collector_files() -> list[Path]:
    # R7 的扫描根（将来新增的第 6 个真机脚本自动纳入，正是本次立规的目的）
    return sorted(p for p in _TESTS_DIR.glob(_LIVE_COLLECTOR_GLOB) if p.is_file())


def _build_parent_map(tree: ast.AST) -> dict[ast.AST, ast.AST]:
    # AST 没有父指针，②③④ 都要「从被检查节点往上找守卫」，故一次性建反查表
    parents: dict[ast.AST, ast.AST] = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parents[child] = node
    return parents


def _call_leaf(node: ast.AST) -> str | None:
    # 调用尾段名：os.path.isfile(...) -> "isfile"；p.unlink() -> "unlink"；int(...) -> "int"
    # （_dotted_name 对 `Path(x).unlink()` 这种「属性挂在调用结果上」的形态返回 None，故另开一支）
    if not isinstance(node, ast.Call):
        return None
    func = node.func
    if isinstance(func, ast.Attribute):
        return func.attr
    if isinstance(func, ast.Name):
        return func.id
    return None


def _call_attrs(node: ast.AST) -> set[str]:
    # 一段表达式里出现过的所有调用尾段名，用于回答「这个守卫条件到底判了什么」
    return {leaf for leaf in (_call_leaf(inner) for inner in ast.walk(node)) if leaf is not None}


def _contains_node(stmt: ast.AST, node: ast.AST) -> bool:
    return any(inner is node for inner in ast.walk(stmt))


def _escaping_sibling_guards(container: ast.AST, path_child: ast.AST) -> list[ast.expr]:
    # 卫语句形态：container.body 里位于「通往被检查节点那条语句」之前、且体内会 continue/return/raise/break
    # 的 if。`if not f.startswith(P): continue` 与 `if f.startswith(P): os.remove(...)` 语义完全等价，
    # 只认嵌套 if 那一支就会把前者误报成违例，后来者便会去放宽判据而不是改写法。
    body = getattr(container, "body", None)
    if not isinstance(body, list):
        return []
    index = next((pos for pos, stmt in enumerate(body) if stmt is path_child or _contains_node(stmt, path_child)), None)
    if index is None:
        return []
    guards: list[ast.expr] = []
    for earlier in body[:index]:
        if not isinstance(earlier, ast.If):
            continue
        if any(isinstance(inner, (ast.Continue, ast.Return, ast.Raise, ast.Break)) for inner in ast.walk(earlier)):
            guards.append(earlier.test)
    return guards


def _inline_conditions(expr: ast.expr) -> list[ast.expr]:
    # 表达式内部自带条件的位置：三元式的 test、推导式的每个 if 子句
    conditions: list[ast.expr] = []
    for inner in ast.walk(expr):
        if isinstance(inner, ast.IfExp):
            conditions.append(inner.test)
        elif isinstance(inner, ast.comprehension):
            conditions.extend(inner.ifs)
    return conditions


def _guard_exprs_for(node: ast.AST, parents: dict[ast.AST, ast.AST]) -> list[ast.expr]:
    # 覆盖「从模块/函数体到该节点」整条路径上的保护性条件：If/IfExp 的 test、推导式的 if、
    # 以及每一层容器里前置的卫语句。走到 Module 即停，跨函数不借守卫。
    guards: list[ast.expr] = []
    current: ast.AST = node
    while True:
        parent = parents.get(current)
        if parent is None:
            break
        if isinstance(parent, (ast.If, ast.IfExp)):
            guards.append(parent.test)
        elif isinstance(parent, ast.comprehension):
            guards.extend(parent.ifs)
        guards.extend(_escaping_sibling_guards(parent, current))
        current = parent
        if isinstance(parent, ast.Module):
            break
    return guards


def _handler_names(handler: ast.ExceptHandler) -> set[str]:
    if handler.type is None:
        return set()
    if isinstance(handler.type, ast.Name):
        return {handler.type.id}
    if isinstance(handler.type, ast.Tuple):
        return {inner.id for inner in handler.type.elts if isinstance(inner, ast.Name)}
    return set()


def _is_dunder_main_guard(node: ast.AST) -> bool:
    # 认 `if __name__ == "__main__":` 与左右互换的 `if "__main__" == __name__:`；其余 if 一律不算守卫
    if not isinstance(node, ast.If):
        return False
    test = node.test
    if not isinstance(test, ast.Compare):
        return False
    if not any(isinstance(op, ast.Eq) for op in test.ops):
        return False
    sides = [test.left, *test.comparators]
    names = {_dotted_name(side) for side in sides}
    literals = {side.value for side in sides if isinstance(side, ast.Constant) and isinstance(side.value, str)}
    return "__name__" in names and "__main__" in literals


def _is_literal_value(node: ast.expr) -> bool:
    # 字面量容器：常量 / 元组 / 列表 / 集合 / 字典（递归），以及常量的取负与四则组合。
    # JoinedStr 刻意不算——f-string 里可能挂着 sys.argv / __file__ 之类的运行期取值。
    if isinstance(node, ast.Constant):
        return True
    if isinstance(node, (ast.Tuple, ast.List, ast.Set)):
        return all(_is_literal_value(elt) for elt in node.elts)
    if isinstance(node, ast.Dict):
        return all(key is None or _is_literal_value(key) for key in node.keys) and all(
            _is_literal_value(value) for value in node.values
        )
    if isinstance(node, ast.UnaryOp):
        return _is_literal_value(node.operand)
    if isinstance(node, ast.BinOp):
        return _is_literal_value(node.left) and _is_literal_value(node.right)
    return False


def _assignee_names(node: ast.Assign | ast.AnnAssign) -> list[str]:
    targets: list[ast.expr] = list(node.targets) if isinstance(node, ast.Assign) else [node.target]
    return [inner.id for target in targets for inner in ast.walk(target) if isinstance(inner, ast.Name)]


def _is_import_guard(node: ast.Try) -> bool:
    # 「导入保护」的边界：至少一个 except 明确捕 ImportError/ModuleNotFoundError（捕 Exception 的裸 try
    # 不算保护），且 try/else/finally/各 handler 体内没有别的模块级副作用——递归复用同一条模块级判据，
    # 免得「用 try 包一层就能在收集期连真机」变成绕道。
    if not any(_handler_names(handler) & {"ImportError", "ModuleNotFoundError"} for handler in node.handlers):
        return False
    inner: list[ast.stmt] = [*node.body, *node.orelse, *node.finalbody]
    for handler in node.handlers:
        inner.extend(handler.body)
    return all(_r7_module_stmt_offense(stmt) is None for stmt in inner)


def _r7_module_stmt_offense(node: ast.stmt) -> str | None:
    # R7② 的单条判据：返回「这条语句在导入期就会做外部动作」的说明，None = 合规。
    # 边界为什么这么切：收集期的危害来自「做了不可撤销的外部动作」（连网络 / 起进程 / 删文件 / 睡眠 /
    # 退出进程），而不是「出现了函数调用」——AGENTS 的 argv 守卫范式本身就要求模块级写成
    # `X = int(sys.argv[2]) if <非选项判定> else N`，把它判成副作用等于推翻文档级约定。
    # 故与 test_twitch_live_collector.py 里 S-2 那条文件内结构锁同口径：**只看最外层节点是不是调用**，
    # `X = os.makedirs(...)` 与 `os.makedirs(...)` 在收集期完全等价、都要拦；三元式右值内部的 int()/
    # len()/isdigit() 属纯取值、放行（两条门禁不得互相矛盾，否则后来者只能删掉其中一条）。
    if isinstance(node, (ast.Import, ast.ImportFrom, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        return None
    if isinstance(node, ast.Pass):
        return None
    if isinstance(node, (ast.Assign, ast.AnnAssign)):
        value = node.value
        if value is None:
            return None  # 纯注解声明（X: int），不产生任何运行期动作
        if isinstance(value, ast.Call):
            return f"第{node.lineno}行 模块级赋值右值是裸调用（与直接写这条调用等价，收集期即执行）"
        if _assignee_names(node) and all(_R7_CONSTANT_NAME_RE.match(name) for name in _assignee_names(node)):
            return None  # AGENTS 双模式模板的常量赋值形态
        if _is_literal_value(value):
            return None
        return f"第{node.lineno}行 模块级赋值既不是全大写常量名、右值也不是字面量容器"
    if isinstance(node, ast.Expr):
        value = node.value
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            return None  # 模块 docstring
        if isinstance(value, ast.Call) and _dotted_name(value.func) in _R7_SYS_PATH_CALLS:
            return None
        return f"第{node.lineno}行 模块级 {(_call_leaf(value) or type(value).__name__)}(...) 表达式语句（真机连接/删目录/睡眠/sys.exit 都长这样）"
    if isinstance(node, ast.If):
        if _is_dunder_main_guard(node):
            return None
        return f"第{node.lineno}行 模块级 If（非 __main__ 守卫，条件与体内动作都在收集期执行）"
    if isinstance(node, ast.Try):
        if _is_import_guard(node):
            return None
        return f"第{node.lineno}行 模块级 Try（只允许 ImportError/ModuleNotFoundError 导入保护）"
    return f"第{node.lineno}行 模块级 {type(node).__name__} 语句"


def _r7_main_guard_offenders(tree: ast.Module) -> list[str]:
    # R7①：守卫存在且真的调用 main()
    guards = [node for node in tree.body if _is_dunder_main_guard(node)]
    if not guards:
        return ['模块级没有 `if __name__ == "__main__":` 守卫（pytest 收集期会直接执行真机流程）']
    offenders: list[str] = []
    for guard in guards:
        leaves = {leaf for leaf in (_call_leaf(inner) for inner in ast.walk(guard)) if leaf}
        if "main" not in leaves:
            offenders.append(
                f"第{guard.lineno}行 __main__ 守卫体内没有 main() 调用（实际调用尾段：{sorted(leaves) or '无'}）"
            )
    return offenders


def _r7_module_side_effect_offenders(tree: ast.Module) -> list[str]:
    # R7②：守卫之外的模块级零副作用
    return [msg for msg in (_r7_module_stmt_offense(stmt) for stmt in tree.body) if msg is not None]


def _is_direct_argv_read(node: ast.expr, tainted: frozenset[str]) -> bool:
    # 「直接取 argv」的形态判定（不做全子树搜索）：sys.argv[i] 下标、`from sys import argv` 的名字本身、
    # 已由 argv 派生出的名字；三元式则沿 body/orelse 各判一次。
    # 为什么必须这么窄：早期实现按「子树里出现过 sys.argv 或 tainted 名」判，于是
    # `info = asyncio.run(spider.get_huya_app_stream_url(url=URL))` 里的 URL 也算 taint，
    # 接着 main() 里那些与命令行无关的 `int(cast(Any, info["yyid"]))`（虎牙协议三参数）全部被误报——
    # 「传参给接口」不等于「取命令行数值」。
    if isinstance(node, ast.IfExp):
        return _is_direct_argv_read(node.body, tainted) or _is_direct_argv_read(node.orelse, tainted)
    if isinstance(node, ast.Subscript):
        return _dotted_name(node.value) in ("sys.argv", "os.sys.argv") or (
            isinstance(node.value, ast.Name) and node.value.id == "argv"
        )
    if isinstance(node, ast.Name):
        return node.id == "argv" or node.id in tainted
    return False


def _assignment_values_for(name: str, tree: ast.Module) -> list[ast.expr]:
    out: list[ast.expr] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Assign, ast.AnnAssign)) or node.value is None:
            continue
        if name in _assignee_names(node):
            out.append(node.value)
    return out


def _numeric_guard_present(guards: list[ast.expr]) -> bool:
    # 「数值性判定」是否出现在守卫链里：`argv 派生值.isdigit()` 这类
    return any(_call_attrs(guard) & _R7_NUMERIC_CHECKS for guard in guards)


def _wrapped_in_valueerror_try(node: ast.AST, parents: dict[ast.AST, ast.AST]) -> bool:
    # 等价写法之二：转换整段包在 `try: … except ValueError:`（Exception/BaseException 同认）里——
    # 判据要认这种形态，否则后来者只能去放宽门禁而不是改写法；只捕 TypeError 不算（兜不住 int('x')）。
    current: ast.AST = node
    while True:
        parent = parents.get(current)
        if parent is None:
            return False
        if isinstance(parent, ast.Try) and any(_handler_names(h) & _R7_INT_ERROR_TYPES for h in parent.handlers):
            return True
        current = parent
        if isinstance(parent, ast.Module):
            return False


def _r7_argv_number_offenders(tree: ast.Module) -> list[str]:
    # R7③：从 sys.argv 取数值处必须做到「转换不可能抛」——数值性判定，或 try/except ValueError 包裹
    parents = _build_parent_map(tree)
    assigns = sorted(
        (node for node in ast.walk(tree) if isinstance(node, (ast.Assign, ast.AnnAssign)) and node.value is not None),
        key=lambda node: node.lineno,
    )
    taint_guards: dict[str, list[ast.expr]] = {}
    # 不动点迭代：`_SECONDS_RAW = sys.argv[2] if … else ""` 再 `int(_SECONDS_RAW)` 是 twitch 的既有形态，
    # 守卫落在派生名的定义处，按行号单趟扫会先遇到消费者、认不出它是 argv 派生值。
    while True:
        added = False
        for stmt in assigns:
            names = _assignee_names(stmt)
            value = stmt.value
            if not names or value is None or any(name in taint_guards for name in names):
                continue
            if not _is_direct_argv_read(value, frozenset(taint_guards)):
                continue
            guards = _guard_exprs_for(value, parents) + _inline_conditions(value)
            for name in [name for name in names if name not in taint_guards]:
                taint_guards[name] = guards
            added = True
        if not added:
            break
    offenders: list[str] = []
    # ast.walk 是 BFS，输出顺序与行号无关；按行号排序让报告稳定可比、违例清单可逐条对照
    for call in sorted((inner for inner in ast.walk(tree) if isinstance(inner, ast.Call)), key=lambda n: n.lineno):
        leaf = _call_leaf(call)
        if leaf not in ("int", "float") or not call.args:
            continue
        arg = call.args[0]
        if not _is_direct_argv_read(arg, frozenset(taint_guards)):
            continue
        guards = _guard_exprs_for(call, parents) + _inline_conditions(arg)
        for name_node in (inner for inner in ast.walk(arg) if isinstance(inner, ast.Name)):
            if name_node.id in taint_guards:
                guards.extend(taint_guards[name_node.id])
        if _numeric_guard_present(guards) or _wrapped_in_valueerror_try(call, parents):
            continue
        offenders.append(
            f"第{call.lineno}行 {leaf}(...) 直接吃 sys.argv 派生值、又无数值性判定或 try 兜底："
            f"`pytest -q -k xxx` 的 -k、以及一次点多个文件时的下一个路径都会让它当场抛 ValueError 中断收集"
        )
    return offenders


def _product_name_literals(tree: ast.Module) -> list[str]:
    # 本脚本自己的产物名：字符串常量 + f-string 的常量段（twitch 的产物名就是 f-string）
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            names.append(node.value)
        elif isinstance(node, ast.JoinedStr):
            parts = [
                inner.value for inner in node.values if isinstance(inner, ast.Constant) and isinstance(inner.value, str)
            ]
            if parts:
                names.append("".join(parts))
    return names


def _module_string_constants(tree: ast.Module) -> dict[str, str]:
    # 模块级「名字 -> 字符串字面量」小表：前缀写成模块级常量（`_PREFIX = "Douyin弹幕验证"`）的形态
    # 同样要认，否则判据就过拟合到「必须就地写字面量」那一种写法。只解析模块级直接赋值，不做数据流分析。
    constants: dict[str, str] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    constants[target.id] = node.value.value
    return constants


def _prefix_filter_literals(node: ast.AST, constants: dict[str, str]) -> list[str]:
    # 守卫条件里传给前缀过滤器的**字面量**实参（元组/列表形态一并展开）。
    # 既非字面量又不在模块级常量表里的参数（如 f.startswith(other_var)）无法机检
    # 「是不是本项目产物前缀」，一律不计入——宁可按违例报出来让人改成常量，也不放恒真的过滤过去。
    out: list[str] = []
    for inner in ast.walk(node):
        if not isinstance(inner, ast.Call) or _call_leaf(inner) not in _R7_PREFIX_FILTERS:
            continue
        for arg in inner.args[:1]:
            elements: list[ast.expr] = list(arg.elts) if isinstance(arg, (ast.Tuple, ast.List)) else [arg]
            for elt in elements:
                if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                    out.append(elt.value)
                elif isinstance(elt, ast.Name) and elt.id in constants:
                    out.append(constants[elt.id])
    return out


def _is_output_delete(call: ast.Call) -> str | None:
    dotted = _dotted_name(call.func)
    if dotted in _R7_TREE_DELETES or dotted in _R7_FILE_DELETES:
        return dotted
    if _call_leaf(call) == "unlink":
        return "Path.unlink"
    return None


def _dir_sweep_loops(node: ast.AST, parents: dict[ast.AST, ast.AST], tree: ast.Module) -> list[ast.For | ast.AsyncFor]:
    # 「遍历目录的循环」= 循环体上游的 For，其 iter 直接是 listdir/scandir/iterdir/glob 调用，
    # 或 iter 是被这类调用赋过值的名字（先过滤成列表再逐个删，同样是无差别清空形态）。
    loops: list[ast.For | ast.AsyncFor] = []
    current: ast.AST = node
    while True:
        parent = parents.get(current)
        if parent is None:
            break
        if isinstance(parent, (ast.For, ast.AsyncFor)):
            sources: list[ast.expr] = [parent.iter]
            if isinstance(parent.iter, ast.Name):
                sources.extend(_assignment_values_for(parent.iter.id, tree))
            if any(_call_attrs(src) & _R7_DIR_SCAN_CALLS for src in sources):
                loops.append(parent)
        current = parent
    return loops


def _r7_cleanup_offenders(tree: ast.Module) -> list[str]:
    # R7④：删输出目录条目必须「按本脚本产物前缀过滤」+「先判类型/存在性」
    parents = _build_parent_map(tree)
    products = _product_name_literals(tree)
    constants = _module_string_constants(tree)
    offenders: list[str] = []
    # 同 ③：按行号排序，保证报告与 offenders[0] 断言的稳定性
    delete_calls = sorted((inner for inner in ast.walk(tree) if isinstance(inner, ast.Call)), key=lambda n: n.lineno)
    for node in delete_calls:
        kind = _is_output_delete(node)
        if kind is None:
            continue
        sweeps = _dir_sweep_loops(node, parents, tree)
        if kind not in _R7_TREE_DELETES and not sweeps:
            continue  # 定点删单个文件：不是「清空目录」形态，本条不拦
        guards = _guard_exprs_for(node, parents)
        for loop in sweeps:
            # 遍历源自身的过滤条件同样算守卫（列表推导式里先筛完再删的写法）
            sources: list[ast.expr] = [loop.iter]
            if isinstance(loop.iter, ast.Name):
                sources.extend(_assignment_values_for(loop.iter.id, tree))
            for src in sources:
                guards.extend(_inline_conditions(src))
        prefix_literals: list[str] = [lit for guard in guards for lit in _prefix_filter_literals(guard, constants)]
        attrs: set[str] = {attr for guard in guards for attr in _call_attrs(guard)}
        # (a) 前缀过滤：必须是字面量、非空，且确实是本脚本某个产物名的前缀——否则 startswith("")
        #     这种恒真写法也能过关，「按平台/本项目前缀」这条就白写了。
        prefix_ok = any(
            lit and any(other != lit and other.startswith(lit) for other in products) for lit in prefix_literals
        )
        kind_ok = bool(attrs & _R7_KIND_CHECKS)
        label = f"第{node.lineno}行 {kind}(...)"
        if not prefix_ok:
            offenders.append(f"{label} 清空输出目录未按本脚本产物名前缀过滤（并行真机验证会互删对方产物）")
        if not kind_ok:
            offenders.append(f"{label} 删除前未判类型/存在性（目录里混进子目录即抛 IsADirectoryError/PermissionError）")
    return offenders


def _r7_violations(tree: ast.Module) -> dict[str, list[str]]:
    # 四条判据各自独立返回，反向见证才能断言「只破坏一条时另三条不误红」
    return {
        "R7①": _r7_main_guard_offenders(tree),
        "R7②": _r7_module_side_effect_offenders(tree),
        "R7③": _r7_argv_number_offenders(tree),
        "R7④": _r7_cleanup_offenders(tree),
    }


def _r7_offenders(violations: dict[str, list[str]]) -> list[str]:
    # 摊平成「规则标签 + 说明」的一行清单。合规侧断言一律用本函数（`assert not _r7_violations(...)`
    # 是假断言——返回的是四个键的 dict，永远为真），违例侧则按标签逐条点名。
    return [f"{rule} {msg}" for rule, msgs in violations.items() for msg in msgs]


def _r7_good_template_source() -> str:
    # AGENTS「双模式测试脚本」模板的最小可执行样本（按 5 个真机脚本修后的共同形态缩编：
    # 第一步取 argv 并判「非选项」、第二步带 isdigit 数值性判定再转数）。
    # 它同时是「合规形态」的可执行定义：R7 的坏样本全部由它**单点改动**派生，
    # 一次只破坏一条判据，才能证明四条判据各自独立敏感。
    return (
        "import json\n"
        "import os\n"
        "import sys\n"
        "import time\n"
        "\n"
        "sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))\n"
        "\n"
        "from src import spider\n"
        "from src.collector import DanmakuCollector\n"
        "\n"
        '_PREFIX = "Douyin弹幕验证"\n'
        'URL = sys.argv[1] if len(sys.argv) > 1 else "https://live.douyin.com/699394970561"\n'
        '_SECONDS_RAW = sys.argv[2] if len(sys.argv) > 2 and not sys.argv[2].startswith("-") else ""\n'
        "SECONDS = int(_SECONDS_RAW) if _SECONDS_RAW.isdigit() else 20\n"
        "\n"
        "\n"
        "def main() -> None:\n"
        '    base_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_out_live")\n'
        "    os.makedirs(base_dir, exist_ok=True)\n"
        "    for entry in os.listdir(base_dir):\n"
        "        if entry.startswith(_PREFIX):\n"
        "            stale = os.path.join(base_dir, entry)\n"
        "            if os.path.isfile(stale):\n"
        "                os.remove(stale)\n"
        '    base = os.path.join(base_dir, "Douyin弹幕验证_699394970561")\n'
        "    time.sleep(SECONDS)\n"
        "    print(json.dumps({'platform': 'douyin', 'status': 'PASS'}))\n"
        "\n"
        "\n"
        'if __name__ == "__main__":\n'
        "    main()\n"
    )


# ③ 的两种写法锚点：模板里的两步式（第二步带 isdigit 数值性判定），与 AGENTS 样例的一行式（只判非选项）。
# 后者在「一次点多个文件」的跑法下仍会 int(路径) 抛 ValueError，故 R7③ 判它不合规（见上方沿革说明）。
_R7_TWO_STEP_SECONDS = (
    '_SECONDS_RAW = sys.argv[2] if len(sys.argv) > 2 and not sys.argv[2].startswith("-") else ""\n'
    "SECONDS = int(_SECONDS_RAW) if _SECONDS_RAW.isdigit() else 20\n"
)
_R7_ONELINE_NO_NUMERIC = 'SECONDS = int(sys.argv[2]) if len(sys.argv) > 2 and not sys.argv[2].startswith("-") else 20\n'
_R7_ONELINE_WITH_NUMERIC = (
    'SECONDS = int(sys.argv[2]) if len(sys.argv) > 2 and not sys.argv[2].startswith("-") '
    "and sys.argv[2].isdigit() else 20\n"
)


def _r7_drop_main_guard(source: str) -> str:
    # 只抹掉守卫连同其中的 main() 调用：这样模块级依旧干净、②不会被连累，
    # 才能单独证明「R7① 独立敏感」。把执行体挪回模块级那种破坏会同时点亮 ①②
    # （同一缺陷的两个视角），由 test_guard_r7_red_when_real_script_body_moves_to_module_level 见证。
    return source.replace('if __name__ == "__main__":\n    main()\n', "")


# 变异验证 ④ 的锚点与替换体：5 个真机脚本的清理段一律是「4 空格 for + 8 空格起的循环体」，
# 整块换成 S-2 修复前的无差别清空写法（正则匹配次数即锚点是否仍然存在的自检）。
_R7_CLEANUP_BLOCK_RE = re.compile(r"^    for f in os\.listdir\(base_dir\):\n(?: {8}.*\n)+", re.MULTILINE)
_R7_BLIND_CLEANUP_BLOCK = "    for f in os.listdir(base_dir):\n" "        os.remove(os.path.join(base_dir, f))\n" "\n"
# 变异验证 ③ 的锚点：5 个真机脚本共用的两步式取值段（第一步判非选项、第二步判数值性；默认秒数各文件不同）。
_R7_TWO_STEP_SECONDS_RE = re.compile(
    r'^_SECONDS_RAW = sys\.argv\[2\] if len\(sys\.argv\) > 2 and not sys\.argv\[2\]\.startswith\("-"\) else ""\n'
    r"SECONDS = int\(_SECONDS_RAW\) if _SECONDS_RAW\.isdigit\(\) else \d+\n",
    re.MULTILINE,
)


@pytest.mark.parametrize("path", _live_collector_files(), ids=lambda p: p.name)
def test_live_collector_scripts_follow_the_dual_mode_template(path: Path) -> None:
    # R7 回归锁（S-2 的模板化收口）：真机 collector 脚本必须「独立可跑、被收集无副作用」。
    # 本条全程静态（只读源码 + ast.parse），不连平台、不 sleep、不删 tests/_out_live——
    # 由不得用运行时用例证明：运行时判据得先把真机依赖打进桩，等于在用例里重跑一遍被测流程。
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    allowed = _SANCTIONED.get(path.name, frozenset())
    violations = _r7_violations(tree)
    offenders = [f"{rule} {msg}" for rule, msgs in violations.items() for msg in msgs if rule not in allowed]
    assert not offenders, (
        f"{path.name} 破了真机 collector 双模式模板（模块级执行体会在 pytest **收集期**连真机、"
        f"sleep、清空 tests/_out_live 并 sys.exit(1) 中断收集）：" + "; ".join(offenders)
    )


def test_live_collector_scan_root_is_not_empty() -> None:
    # 兜底：glob 错位或脚本集体改名时，上面那条参数化用例会「空跑通过」——正是本文件要消灭的假绿形态
    files = [p.name for p in _live_collector_files()]
    assert len(files) >= 5, f"真机 collector 脚本数异常（{files}），扫描根可能错位: {_TESTS_DIR}"


def test_guard_r7_actually_catches_template_violations() -> None:
    # R7 反向见证：①②③④ 各造一段坏源码喂进判定函数、断言必红；再给一段合规源码断言不误报。
    # 好模板同时是「合规形态」的可执行定义：改判据前先看这里有没有被误伤。
    good = _r7_good_template_source()
    assert not _r7_offenders(_r7_violations(ast.parse(good))), "R7 误报：AGENTS 双模式模板本身被判违例"
    no_guard = _r7_drop_main_guard(good)
    violations = _r7_violations(ast.parse(no_guard))
    assert violations["R7①"], "R7① 失效：删掉 __main__ 守卫没被发现"
    assert not any(violations[key] for key in ("R7②", "R7③", "R7④")), f"R7① 的坏样本连累了别的判据: {violations}"
    wrong_callee = good.replace("    main()\n", "    run()\n")
    violations = _r7_violations(ast.parse(wrong_callee))
    assert violations["R7①"], "R7① 失效：守卫没调用 main() 没被发现"
    assert not any(violations[key] for key in ("R7②", "R7③", "R7④")), f"R7① 的坏样本连累了别的判据: {violations}"
    module_level_call = good.replace(
        "def main() -> None:\n", 'os.makedirs("_out_live", exist_ok=True)\n\n\ndef main() -> None:\n'
    )
    violations = _r7_violations(ast.parse(module_level_call))
    assert violations["R7②"], "R7② 失效：模块级 makedirs 调用没被发现"
    assert not any(violations[key] for key in ("R7①", "R7③", "R7④")), f"R7② 的坏样本连累了别的判据: {violations}"
    module_level_loop = good.replace(
        "def main() -> None:\n", "for _i in range(3):\n    time.sleep(1)\n\n\ndef main() -> None:\n"
    )
    violations = _r7_violations(ast.parse(module_level_loop))
    assert violations["R7②"], "R7② 失效：模块级 for 循环没被发现"
    assert not any(violations[key] for key in ("R7①", "R7③", "R7④")), f"R7② 的坏样本连累了别的判据: {violations}"
    no_nonoption = good.replace(_R7_TWO_STEP_SECONDS, "SECONDS = int(sys.argv[2]) if len(sys.argv) > 2 else 20\n")
    violations = _r7_violations(ast.parse(no_nonoption))
    assert violations["R7③"], "R7③ 失效：只判长度、没判非选项的 int(sys.argv) 没被发现"
    assert not any(violations[key] for key in ("R7①", "R7②", "R7④")), f"R7③ 的坏样本连累了别的判据: {violations}"
    # 关键一条：AGENTS 样例那种「只判非选项」的一行式必须仍被判违例——
    # 一次点多个文件时 sys.argv[2] 是下一个测试文件的路径，不以 - 开头、int() 照样抛（实测读数见上方注释）。
    nonoption_only = good.replace(_R7_TWO_STEP_SECONDS, _R7_ONELINE_NO_NUMERIC)
    violations = _r7_violations(ast.parse(nonoption_only))
    assert violations["R7③"], 'R7③ 失效：只有 startswith("-") 非选项判定、无数值性判定的形态没被发现'
    assert not any(violations[key] for key in ("R7①", "R7②", "R7④")), f"R7③ 的坏样本连累了别的判据: {violations}"
    blind_delete = good.replace(
        "    for entry in os.listdir(base_dir):\n"
        "        if entry.startswith(_PREFIX):\n"
        "            stale = os.path.join(base_dir, entry)\n"
        "            if os.path.isfile(stale):\n"
        "                os.remove(stale)\n",
        "    for entry in os.listdir(base_dir):\n" "        os.remove(os.path.join(base_dir, entry))\n",
    )
    violations = _r7_violations(ast.parse(blind_delete))
    assert violations["R7④"], "R7④ 失效：无差别清空输出目录没被发现"
    assert not any(violations[key] for key in ("R7①", "R7②", "R7③")), f"R7④ 的坏样本连累了别的判据: {violations}"
    no_prefix = blind_delete.replace(
        "        os.remove(os.path.join(base_dir, entry))\n",
        "        stale = os.path.join(base_dir, entry)\n"
        "        if os.path.isfile(stale):\n"
        "            os.remove(stale)\n",
    )
    violations = _r7_violations(ast.parse(no_prefix))
    assert violations["R7④"], "R7④ 失效：有 isfile 但无前缀过滤的清空没被发现（要求是「且」不是「或」）"
    assert not any(violations[key] for key in ("R7①", "R7②", "R7③")), f"R7④ 的坏样本连累了别的判据: {violations}"
    no_kind_check = blind_delete.replace(
        "        os.remove(os.path.join(base_dir, entry))\n",
        "        if entry.startswith(_PREFIX):\n" "            os.remove(os.path.join(base_dir, entry))\n",
    )
    violations = _r7_violations(ast.parse(no_kind_check))
    assert violations["R7④"], "R7④ 失效：有前缀过滤但不判类型/存在性的清空没被发现（要求是「且」不是「或」）"
    assert not any(violations[key] for key in ("R7①", "R7②", "R7③")), f"R7④ 的坏样本连累了别的判据: {violations}"
    always_true_prefix = blind_delete.replace(
        "        os.remove(os.path.join(base_dir, entry))\n",
        '        if entry.startswith(""):\n' "            os.remove(os.path.join(base_dir, entry))\n",
    )
    assert _r7_violations(ast.parse(always_true_prefix))["R7④"], 'R7④ 失效：startswith("") 恒真过滤被当成前缀过滤'


def test_guard_r7_accepts_equivalent_compliant_spellings() -> None:
    # 判据不得过拟合到某一种缩进/写法，否则后来者只能放宽判据而不是照模板写：
    # ①卫语句（if not …: continue）与嵌套 if 等价；②列表推导式先过滤再删等价；
    # ③twitch 的「派生名 + isdigit」两步式与兄弟脚本的一行式等价；④互换写法的 __main__ 守卫等价。
    escaping = _r7_good_template_source().replace(
        "    for entry in os.listdir(base_dir):\n"
        "        if entry.startswith(_PREFIX):\n"
        "            stale = os.path.join(base_dir, entry)\n"
        "            if os.path.isfile(stale):\n"
        "                os.remove(stale)\n",
        "    for entry in os.listdir(base_dir):\n"
        "        if not entry.startswith(_PREFIX):\n"
        "            continue\n"
        "        stale = os.path.join(base_dir, entry)\n"
        "        if not os.path.isfile(stale):\n"
        "            continue\n"
        "        os.remove(stale)\n",
    )
    assert not _r7_offenders(_r7_violations(ast.parse(escaping))), "R7 误报：卫语句形态的等价清理写法被拦"
    # 阴性对照：证明上面「不报」是因为认出了守卫，而不是因为没认出这是遍历目录的删除形态
    # （少一层判据的话，④ 会对所有写法都沉默，照样全绿——那是最隐蔽的假绿形态）。
    escaping_blind = escaping.replace("        if not entry.startswith(_PREFIX):\n", "        if not entry:\n")
    assert _r7_violations(ast.parse(escaping_blind))[
        "R7④"
    ], "R7④ 假绿：卫语句形态根本没进判定范围（前缀过滤被拿掉仍不报）"
    escaping_no_kind = escaping.replace("        if not os.path.isfile(stale):\n", "        if not stale:\n")
    assert _r7_violations(ast.parse(escaping_no_kind))["R7④"], "R7④ 假绿：卫语句形态的类型判定没被识别（拿掉仍不报）"
    comprehension = _r7_good_template_source().replace(
        "    for entry in os.listdir(base_dir):\n"
        "        if entry.startswith(_PREFIX):\n"
        "            stale = os.path.join(base_dir, entry)\n"
        "            if os.path.isfile(stale):\n"
        "                os.remove(stale)\n",
        "    stale_files = [\n"
        "        os.path.join(base_dir, entry)\n"
        "        for entry in os.listdir(base_dir)\n"
        "        if entry.startswith(_PREFIX) and os.path.isfile(os.path.join(base_dir, entry))\n"
        "    ]\n"
        "    for stale in stale_files:\n"
        "        os.remove(stale)\n",
    )
    assert not _r7_offenders(_r7_violations(ast.parse(comprehension))), "R7 误报：推导式先过滤再逐个删的等价写法被拦"
    # 阴性对照（同上）：把推导式里的两个过滤条件逐个抽掉，必须立刻报——
    # 否则「推导式写法不报」可能只是判据根本没顺着赋值把过滤条件找回来。
    comp_no_prefix = comprehension.replace(
        "        if entry.startswith(_PREFIX) and os.path.isfile(os.path.join(base_dir, entry))\n",
        "        if os.path.isfile(os.path.join(base_dir, entry))\n",
    )
    assert _r7_violations(ast.parse(comp_no_prefix))["R7④"], "R7④ 假绿：推导式里的前缀过滤被抽掉仍不报"
    comp_no_kind = comprehension.replace(
        "        if entry.startswith(_PREFIX) and os.path.isfile(os.path.join(base_dir, entry))\n",
        "        if entry.startswith(_PREFIX)\n",
    )
    assert _r7_violations(ast.parse(comp_no_kind))["R7④"], "R7④ 假绿：推导式里的类型判定被抽掉仍不报"
    # ③ 的两种等价写法：模板用的是「派生名 + isdigit」两步式（twitch 现存形态），
    # 一行式只要带上数值性判定同样合规。
    one_line_numeric = _r7_good_template_source().replace(_R7_TWO_STEP_SECONDS, _R7_ONELINE_WITH_NUMERIC)
    assert not _r7_violations(ast.parse(one_line_numeric))["R7③"], "R7 误报：一行式 + isdigit 的等价写法被拦"
    # ③ 的第三种等价写法：转换整段包在 try/except ValueError 里（真机脚本没在用，但判据必须认，
    # 否则后来者遇到判据不认的合规写法时只会去放宽判据）。
    try_wrapped = (
        "import sys\n"
        "\n"
        "\n"
        "def main() -> None:\n"
        "    try:\n"
        "        seconds = int(sys.argv[2])\n"
        "    except ValueError:\n"
        "        seconds = 20\n"
        "    print(seconds)\n"
        "\n"
        "\n"
        'if __name__ == "__main__":\n'
        "    main()\n"
    )
    assert not _r7_violations(ast.parse(try_wrapped))["R7③"], "R7 误报：try/except ValueError 包裹的等价写法被拦"
    # 阴性对照：只捕 TypeError 兜不住 int('x') 的 ValueError，必须报。
    wrong_exception = try_wrapped.replace("    except ValueError:\n", "    except TypeError:\n")
    assert _r7_violations(ast.parse(wrong_exception))["R7③"], "R7③ 失效：except TypeError 兜不住 ValueError 却算合规"
    swapped_guard = _r7_good_template_source().replace('if __name__ == "__main__":\n', 'if "__main__" == __name__:\n')
    assert not _r7_offenders(_r7_violations(ast.parse(swapped_guard))), "R7 误报：左右互换写法的 __main__ 守卫被拦"
    unguarded_derived = _r7_good_template_source().replace(
        _R7_TWO_STEP_SECONDS,
        'RAW_SECONDS = sys.argv[2] if len(sys.argv) > 2 else ""\n'
        "SECONDS = int(RAW_SECONDS) if RAW_SECONDS else 20\n",
    )
    assert _r7_violations(ast.parse(unguarded_derived))["R7③"], "R7③ 失效：派生名无守卫时 int() 没被发现"


def test_guard_r7_red_when_real_script_body_moves_to_module_level() -> None:
    # 变异验证（AGENTS「新增安全不变量类用例必做变异验证」）：拿**真实脚本**的源码做手术，
    # 把执行体从守卫里挪回模块级（S-2 的原始形态），R7 必须立刻红。
    sources = [(p, p.read_text(encoding="utf-8")) for p in _live_collector_files()]
    assert sources, "真机脚本源码为空，本用例无从见证"
    for path, text in sources:
        mutated = text.replace('if __name__ == "__main__":\n    main()', "main()")
        assert mutated != text, f"{path.name} 尾部形态已变，变异锚点失效（须同步更新本用例）"
        violations = _r7_violations(ast.parse(mutated))
        assert violations["R7①"], f"{path.name}: 守卫被拆掉却未被 R7① 发现（假绿）"
        assert violations["R7②"], f"{path.name}: 执行体挪回模块级却未被 R7② 发现（假绿）"
        assert (
            not violations["R7③"] and not violations["R7④"]
        ), f"{path.name}: 只破坏守卫结构，③④ 不应连坐（独立敏感性）: {violations}"


def test_guard_r7_red_when_real_script_numeric_guard_is_removed() -> None:
    # 变异验证 ③（实测坑）：把真实脚本的两步式退回 AGENTS 样例那种「只判非选项」的一行式，
    # R7③ 必须红、且只红 ③。这一形态就是「`pytest a.py b.py` 一次点多个文件 → 4 errors during
    # collection」的现场，只判 startswith("-") 挡不住下一个文件路径。
    for path in _live_collector_files():
        text = path.read_text(encoding="utf-8")
        mutated, hits = _R7_TWO_STEP_SECONDS_RE.subn(_R7_ONELINE_NO_NUMERIC, text)
        assert hits == 1, f"{path.name} 两步式取值段匹配到 {hits} 处（应为 1），变异锚点失效（须同步更新本用例）"
        violations = _r7_violations(ast.parse(mutated))
        assert violations["R7③"], f"{path.name}: 摘掉 isdigit 的退回形态未被 R7③ 发现（假绿）"
        assert not any(
            violations[key] for key in ("R7①", "R7②", "R7④")
        ), f"{path.name}: 只破坏 ③，另三条不应连坐: {violations}"


def test_guard_r7_red_when_real_script_cleanup_is_blind() -> None:
    # 变异验证 ④：把真实脚本的清理段整块换回 S-2 修复前的「无差别清空 tests/_out_live」形态
    # （审查报告点名 bili:43-44 / huya:47-48 的原始写法），R7④ 必须红、且只红 ④。
    for path in _live_collector_files():
        text = path.read_text(encoding="utf-8")
        mutated, hits = _R7_CLEANUP_BLOCK_RE.subn(_R7_BLIND_CLEANUP_BLOCK, text)
        assert hits == 1, f"{path.name} 清理段匹配到 {hits} 处（应为 1），变异锚点失效（须同步更新本用例）"
        violations = _r7_violations(ast.parse(mutated))
        assert (
            len(violations["R7④"]) == 2
        ), f"{path.name}: 无差别清空应同时报「缺前缀过滤」与「缺类型判定」: {violations}"
        assert not any(
            violations[key] for key in ("R7①", "R7②", "R7③")
        ), f"{path.name}: 只破坏 ④，另三条不应连坐: {violations}"


# ─── R8：变异验证的一次性改动不得留在盘上 ────────────────
# 成因（本仓实测，非假想）：一个并行工作包在 src/stream_select.py 的分片探测分支上做
# 「摘掉 except RedirectHopRejected 的 re-raise」变异，跑到轮次上限中断，把带标记的 pass 原样留在了
# 生产代码里。后果不是「少一条注释」：seg_resp 因此未赋值 → UnboundLocalError 被外层
# except Exception 当「探测异常」吞掉 → 末位候选 return True，内网地址被交给 ffmpeg -i。
# 三面门禁（black / mypy / 注释检查）对这种形态全部隐形——语法合法、类型不报错、注释反而更多。
# 唯一可靠的收口是「标记不得存活到收尾」：做在盘变异时必须给改动行加标记 + 短 id，还原后标记随之
# 消失；忘了还原即由本条点名。判据只认标记本身，不猜改动内容。
# 标记字面量刻意拆成两段拼接：本文件若含完整字面量会被自己判红（自指门禁的通用做法）。
_R8_MUTATION_MARKER = "MUT" + "ATION-"
_R8_SOURCE_SUFFIXES = (".py", ".js", ".mjs", ".yml", ".yaml", ".sh", ".vbs", ".html", ".css")
# 与 pyproject/black 排除集同源：第三方与运行期产物目录不参与本判据。
_R8_SKIP_DIRS = frozenset(
    {
        ".git",
        ".venv",
        "__pycache__",
        "node",
        "node_modules",
        "ffmpeg",
        "downloads",
        "recordings",
        "logs",
        "backup_config",
        "build",
        "dist",
        ".mimosa",
        ".qoder",
        ".agents",
    }
)
_R8_SCAN_ROOTS = ("src", "tests", "scripts", "web", ".github")


def _r8_marker_offenders(text: str, name: str) -> list[tuple[str, int, str]]:
    # 单条判据：返回「第几行含标记」的违例列表。抽成纯函数是为了让反向见证能在内存里造一份
    # 带标记的源码喂它，不必往仓库写真脏文件（AGENTS「临时文件零残留」）。
    return [
        (name, number, line.strip()) for number, line in enumerate(text.splitlines(), 1) if _R8_MUTATION_MARKER in line
    ]


def _r8_iter_source_files() -> list[Path]:
    # 返回 list 而非生成器：mypy 的 disallow_untyped_defs 要求标注返回类型，而本文件不 import
    # typing/collections.abc，用内置 list[Path] 最省；待扫文件量在本仓量级（数百）不构成内存问题。
    found: list[Path] = []
    for root in _R8_SCAN_ROOTS:
        base = _REPO_ROOT / root
        if not base.is_dir():
            continue
        for path in base.rglob("*"):
            if not path.is_file() or path.suffix not in _R8_SOURCE_SUFFIXES:
                continue
            if any(part in _R8_SKIP_DIRS for part in path.parts):
                continue
            found.append(path)
    for path in _REPO_ROOT.glob("*.py"):
        if path.is_file():
            found.append(path)
    return found


def _r8_scan_repo(paths: list[Path] | None = None) -> list[tuple[str, int, str]]:
    offenders: list[tuple[str, int, str]] = []
    seen: set[str] = set()
    for path in _r8_iter_source_files() if paths is None else paths:
        key = str(path)
        if key in seen:
            continue
        seen.add(key)
        try:
            body = path.read_text(encoding="utf-8")
        except OSError, UnicodeDecodeError:
            # 读不动的文件不作判据：StopRecording.vbs 按 AGENTS 规定存 UTF-16 LE，
            # 它既不在扫描根内、后缀也不在集合内，这里只是兜底而非放宽。
            continue
        offenders += _r8_marker_offenders(body, path.relative_to(_REPO_ROOT).as_posix())
    return sorted(offenders)


def test_no_unrestored_mutation_markers() -> None:
    # 全仓扫描：任何源文件里留着变异标记，就说明某次变异验证没有还原。
    # 自证覆盖（缺它就是一条会空转的门禁）：先断言遍历面不为零，再谈「无违例」。
    # 阈值取 200 而非精确文件数——本仓源文件数随功能增长，钉精确值会把「新增文件」误报成
    # 门禁失效；但扫描根写错/目录改名会让遍历悄悄归零，那时必须由这条点名。
    paths = _r8_iter_source_files()
    assert (
        len(paths) > 200
    ), f"R8 遍历面异常（{len(paths)} 个文件），判据即将空转：检查 _R8_SCAN_ROOTS / _R8_SOURCE_SUFFIXES"
    offenders = _r8_scan_repo()
    detail = [chr(34) + "发现未还原的变异验证改动（代码被留在变异态）:" + chr(34)]
    for name, line_no, snippet in offenders:
        detail.append("  " + name + ":" + str(line_no) + ": " + snippet)
    detail.append("处置: 把代码改回目标形态并删除标记，再复跑门禁。")
    assert not offenders, chr(10).join(detail)


def test_guard_r8_red_when_marker_survives() -> None:
    # 反向见证（三条缺一不可）：
    # ① 内存里造一段「带标记的 pass 分支」，判据必须点名它——证明本门禁不是空转；
    # ② 同一段去掉标记后必须干净——证明判据只认标记，不会把普通 pass 误报成变异残留；
    # ③ 本守卫文件自身不得含完整字面量——否则 R8 会把自己判红（拆分写法的必要性由这条自证）。
    marker_line = "            pass  # " + _R8_MUTATION_MARKER + "M4c remove re-raise"
    bad_lines = ["        except RedirectHopRejected:", marker_line]
    bad = chr(10).join(bad_lines)
    assert _r8_marker_offenders(bad, "mem://snippet.py"), "R8 失效：带标记的源码未被发现"
    clean = bad.replace(_R8_MUTATION_MARKER, "M4c ")
    assert not _r8_marker_offenders(clean, "mem://snippet.py"), "R8 误报：无标记的普通分支被拦"
    own = Path(__file__).resolve().read_text(encoding="utf-8")
    assert not _r8_marker_offenders(own, "tests/test_test_hygiene.py"), "R8 自指：守卫自己含完整标记字面量"


# ─── R9：名为 test_*.py 的文件必须至少产出一条可收集用例 ──────────
# 立规背景：同轮审查的 MT-02——tests/test_bilibili_danmaku.py 全文没有任何 test_ 函数，
# pytest 收集 0 条，文件里那些真机断言（token / WS 连通）永不自动执行，可以无限腐烂而不报错。
# 「整轮全绿」在这里的真实含义是「这个文件什么都没跑」，与假绿同级，且比假绿更难发现——
# 假绿至少有条用例名出现在报告里，0 收集只剩一行 `no tests collected`，混在几百行输出中。
# 判据取 AST 而不是真跑 `--collect-only`：后者要 import 每个测试模块，而本仓 tests/conftest.py
# 的三个 autouse fixture 会拉起整份运行时依赖（AGENTS.md「跑 pytest 的 job 必须装齐
# requirements.txt」即此坑），代价与副作用都高；「模块里有没有 test_ 前缀的可调用定义」
# 是纯结构事实，与 pyproject 的 python_functions=["test_*"] / python_classes=["Test*"] 同源。
# 例外表**双向相等**：新增 0 收集文件必须先入表并给理由；已补上用例的文件若还赖在表里同样判红
# （否则表会退化成一堵谁都能跨、且没人回来拆的墙）。
_R9_ZERO_COLLECTION_SANCTIONED: dict[str, str] = {
    "test_bili_live_collector.py": (
        "双模真机采集脚本：按 `python <文件> <URL> [秒]` 独立跑，模块级零副作用 + __main__ 守卫由 R7 逐条机检，"
        "收集 0 条是该形态的必然结果。AGENTS.md「真机 collector 脚本」的取证口径句写的是 collected ≥ 1，"
        "与 2026-10-18 实测（--collect-only -q → no tests collected）不符，已交回用户定夺"
        "（给每个脚本补一条离线收集型用例，或改正该句）；本表按实测登记。"
    ),
    "test_douyin_live_collector.py": "同上（双模真机采集脚本）",
    "test_douyu_live_collector.py": "同上（双模真机采集脚本）",
    "test_huya_live_collector.py": "同上（双模真机采集脚本）",
    "test_douyu_danmaku.py": (
        "文件头自述「手动验证脚本而非 pytest 用例」，须真连斗鱼接口验证弹幕握手与 STT 编解码。"
        "与 5 个 collector 同形但不在 AGENTS 的 collector 清单内；改造为离线收集型用例"
        "（参照 MT-02 定稿后的 tests/test_bilibili_danmaku.py 形态）是后续动作，不得长期赖在本表。"
    ),
    "test_douyu_stream_url.py": "同上（斗鱼签名链手动验证脚本，待改造为离线收集型用例）",
}


def _r9_collectible_count(tree: ast.Module) -> int:
    # 与 pyproject 的收集口径一致：模块级/嵌套的 test_* 函数，或 Test* 类内的 test_* 方法。
    # 必须先去重再计数：ast.walk 会同时命中类与类内方法，直接两条分支累加会把一个方法数成两次
    # （本条由 test_guard_r9 的 classed 反向见证实测抓出）。
    parents: dict[ast.AST, ast.AST] = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parents[child] = node
    loose = 0
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) or not node.name.startswith("test_"):
            continue
        owner = parents.get(node)
        if isinstance(owner, ast.ClassDef) and owner.name.startswith("Test"):
            continue
        loose += 1
    in_class = 0
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name.startswith("Test"):
            in_class += sum(
                1
                for item in node.body
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name.startswith("test_")
            )
    return loose + in_class


def _r9_zero_collection_modules() -> list[str]:
    offenders: list[str] = []
    for path in sorted(_TESTS_DIR.rglob("test_*.py")):
        if path.name == Path(__file__).name:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError as exc:
            raise AssertionError(f"{path.name} 解析失败，R9 无法自证覆盖: {exc.msg}@{exc.lineno}") from exc
        if _r9_collectible_count(tree) == 0:
            offenders.append(path.name)
    return offenders


def test_every_test_module_is_collectible_or_registered() -> None:
    offenders = _r9_zero_collection_modules()
    unregistered = sorted(set(offenders) - set(_R9_ZERO_COLLECTION_SANCTIONED))
    stale = sorted(set(_R9_ZERO_COLLECTION_SANCTIONED) - set(offenders))
    assert (
        not unregistered
    ), f"以下 test_*.py 收集 0 条用例且未登记理由（MT-02 同形态：全绿=什么都没跑）: {unregistered}"
    assert not stale, f"以下文件已产出可收集用例，必须从 R9 例外表删行: {stale}"


def test_guard_r9_red_for_a_module_without_cases() -> None:
    # 反向见证：① 判据必须真的在扫描（本仓绝大多数测试文件都产出用例，若枚举数异常小说明目录写错）；
    # ② 内存里造一段「只有辅助函数、没有 test_ 函数」的模块，判据必须判它 0 收集。
    total = sum(1 for _ in _TESTS_DIR.rglob("test_*.py"))
    assert total > 100, f"R9 遍历面异常（{total} 个 test_*.py），判据即将空转：检查 _TESTS_DIR 口径"
    hollow = ast.parse("def _helper():\n    return 1\n\n\nclass Runner:\n    def run(self):\n        return 2\n")
    assert _r9_collectible_count(hollow) == 0, "R9 失效：无 test_ 函数的模块未被判为 0 收集"
    filled = ast.parse("def test_real():\n    assert True\n")
    assert _r9_collectible_count(filled) == 1, "R9 失效：普通 test_ 函数未被计入"
    classed = ast.parse("class TestThing:\n    def test_a(self):\n        assert True\n")
    assert _r9_collectible_count(classed) == 1, "R9 失效：Test* 类内方法未被计入（与 pyproject 口径脱钩）"


# ─── R10：线程 join 之后必须断言该线程已退出 ────────────────────
# 立规背景：同轮审查的 LT-01/02/03/04 与 MT-04——`t.join(timeout=15)` 既不看返回值也不查
# is_alive，被测逻辑真死锁时 join 超时返回、收集到的 errors 为空，用例照样全绿；而「死锁」
# 恰恰是这批并发用例唯一要防的东西。本仓已按同口径修过 5 批（async_http / cookie_cache /
# concurrency 系），R10 把它固化成零容忍，18 处存量违例全部补齐。
# 判据粒度取「函数」而不是「文件」：join 与 is_alive 必须落在同一个函数体内，否则别处的一句
# 断言会替它遮丑（本仓出现过同文件另一条用例里有 is_alive 的形态）。
# 线程对象识别刻意保守：只认 ① `X = threading.Thread(...)` 直接绑定 ② 由 Thread 构造填充的
# 容器被 `for X in <容器>` 迭代。识别不到的 join（跨文件传进来的线程句柄等）漏报——
# 宁可漏报也不把 `"\n".join(lines)` 与 `queue.Queue.join()` 报成违例，那才是真正会让门禁
# 被静音的噪声源（MID-2264 同族：判据一旦天天误报，人就把它设成 skip）。
_R10_FACTORY = "Thread"


def _r10_thread_names(tree: ast.Module) -> set[str]:
    names: set[str] = set()
    containers: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
            func = node.value.func
            if (getattr(func, "attr", "") or getattr(func, "id", "")) == _R10_FACTORY:
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        names.add(target.id)
        elif isinstance(node, ast.Assign) and isinstance(node.value, (ast.List, ast.ListComp)):
            # 容器形态：threads = [Thread(...) for ...] 或 threads = [Thread(...), ...]
            if any(
                isinstance(c, ast.Call) and (getattr(c.func, "attr", "") or getattr(c.func, "id", "")) == _R10_FACTORY
                for c in ast.walk(node.value)
            ):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        containers.add(target.id)
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "append":
            recv = getattr(node.func.value, "id", "")
            if recv and any(
                isinstance(c, ast.Call) and (getattr(c.func, "attr", "") or getattr(c.func, "id", "")) == _R10_FACTORY
                for c in node.args
            ):
                containers.add(recv)
    for node in ast.walk(tree):
        if isinstance(node, ast.For) and isinstance(node.iter, ast.Name) and node.iter.id in containers:
            if isinstance(node.target, ast.Name):
                names.add(node.target.id)
    return names


def _r10_offenders(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(text)
    except SyntaxError as exc:
        raise AssertionError(f"{path.name} 解析失败，R10 无法自证覆盖: {exc.msg}@{exc.lineno}") from exc
    thread_names = _r10_thread_names(tree)
    if not thread_names:
        return []
    rel = path.name
    out: list[str] = []
    for func in ast.walk(tree):
        if not isinstance(func, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        joins = [
            node.lineno
            for node in ast.walk(func)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "join"
            and (
                getattr(node.func.value, "id", "") in thread_names
                or getattr(node.func.value, "attr", "") in thread_names
            )
        ]
        if not joins:
            continue
        alive = [node for node in ast.walk(func) if isinstance(node, ast.Attribute) and node.attr == "is_alive"]
        if len(alive) < len(joins):
            out.append(f"{rel}::{func.name}(join@{joins} 仅 {len(alive)} 处 is_alive)")
    return out


def test_thread_joins_assert_thread_exit() -> None:
    offenders: list[str] = []
    for path in sorted(_TESTS_DIR.rglob("test_*.py")):
        offenders.extend(_r10_offenders(path))
    assert not offenders, f"以下并发用例 join 后未断言线程退出（死锁时会假绿）: {offenders}"


def test_guard_r10_red_when_join_has_no_exit_check() -> None:
    # 反向见证三条：① 判据必须真的看到合规站点（否则「零违例」是空转）；
    # ② 内存里造「join 无 is_alive」必须判红；③ 同段补上断言后必须转干净，
    #    且字符串 join / queue.join 不得被误报。
    compliant = 0
    for path in sorted(_TESTS_DIR.rglob("test_*.py")):
        names = _r10_thread_names(ast.parse(path.read_text(encoding="utf-8")))
        if names:
            compliant += 1
    assert compliant >= 10, f"R10 附着面异常（仅 {compliant} 个文件构造线程），判据即将空转"

    bad = ast.parse(
        "import threading\n"
        "def test_wait():\n"
        "    t = threading.Thread(target=lambda: None)\n"
        "    t.start()\n"
        "    t.join(timeout=5)\n"
    )
    assert _r10_offenders_from_tree(bad, "mem://x.py"), "R10 失效：join 后无 is_alive 未被发现"
    good = ast.parse(
        "import threading\n"
        "def test_wait():\n"
        "    t = threading.Thread(target=lambda: None)\n"
        "    t.start()\n"
        "    t.join(timeout=5)\n"
        "    assert not t.is_alive()\n"
    )
    assert not _r10_offenders_from_tree(good, "mem://x.py"), "R10 误报：已断言线程退出的站点被拦"
    noise = ast.parse(
        "import queue\n"
        "def test_strings():\n"
        "    q = queue.Queue()\n"
        "    q.join()\n"
        "    return '\\n'.join(['a'])\n"
    )
    assert not _r10_offenders_from_tree(noise, "mem://x.py"), "R10 误报：queue.join / 字符串 join 被当成线程 join"


def _r10_offenders_from_tree(tree: ast.Module, label: str) -> list[str]:
    # 与 _r10_offenders 同判据的「已解析树」入口，专供上面的反向见证喂内存样例（不落盘，见铁律 1）。
    thread_names = _r10_thread_names(tree)
    if not thread_names:
        return []
    out: list[str] = []
    for func in ast.walk(tree):
        if not isinstance(func, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        joins = [
            node.lineno
            for node in ast.walk(func)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "join"
            and getattr(node.func.value, "id", "") in thread_names
        ]
        if joins and len([n for n in ast.walk(func) if isinstance(n, ast.Attribute) and n.attr == "is_alive"]) < len(
            joins
        ):
            out.append(f"{label}::{func.name}")
    return out


# ─── R11（来自 CODE_REVIEW_2026-10-21 S-14）：弱断言棘轮 ────────────────
# 立规背景：审查实测「14 个测试函数体内无任何判据、17 处只锁调用次数」。这类用例的共同征兆是
# 「用例名承诺了契约、实现退化后照样绿」——生产代码静默做了错事但不上抛时，它们不会变红，
# 于是后续所有修复都失去验证能力（报告 §8.1 第 4 条把它列为门禁缺口的根因）。
# 本轮不做「一次性全清」：判据面刻意保守（见下三条），一次性全清会逼着把大量 helper 委托型
# 用例判成违例而误伤。故取**双向棘轮**（与 R9 例外表同构）：
#   ① 现有存量按「文件 → 条数」登记为债务表，条数只许降不许升；
#   ② 已修好的文件必须登记为 0，否则「修完又退化」不会被发现；
#   ③ 债务表里的文件名必须真实存在，删/改名后条目必须同批删除（防表变成僵尸账）。
#   ④ [S-14 整改二轮补] 上述 ①②③ 首版只由 `实测 > 表行` **单向**实现，与本注释宣称的
#      「双向棘轮」不符（同轮审计实测确认）：一个文件修掉两处违例却不改表时，膨胀的表行原地留着，
#      等于给它发了一张「可悄悄退化回旧上限」的免费额度，债务表与现实脱钩且无人被告知。
#      现比较口径改为**逐文件实测条数 == 表行**的双向相等（与 R9 例外表的 `unregistered`/`stale`
#      两个方向同构，只是把「有无」换成「条数」）：grew=实测高于表（新增债务）、
#      shrunk=实测低于表（债务已修但行没降，实测归零时整条删除）。文件集合也因此天然双向相等
#      ——表外的新违例文件按 0 计入 grew，表内但实测已归零的行计入 shrunk，不需要额外的集合比较。
# 判据（函数级，剔除 docstring 后看函数体）：
#   · 「无判据」= 函数体内无 assert / pytest.raises|warns|fail / 任何 assert_* 方法调用 / 自研
#     helper 调用（helper 名以 check_/expect_/assert_ 开头视为判据载体——本仓既有形态）。
#   · 「只锁次数」= 无参 assert_called*()。它并非**总是**弱：`response.close.assert_called_once()`
#     的契约就是「关且只关一次」，参数不承载语义。故只对「带请求语义的 mock 名」判违例：
#     get/post/head/put/delete/open/request/write/read/run/call 这一类。
_R11_NO_ASSERT_DEBT: dict[str, int] = {
    # S-14 存量（首次登记，实测值）。条数只许降不许升；修好一个就把该文件计数下调，
    # 全部清零时删条目（test_r11_debt_table_files_exist 会拦住「删了用例忘记删条目」的僵尸账）。
    "test_xhs_live_links.py": 6,
    "test_stop_recording_vbs.py": 5,
    "test_platform_danmaku_offline.py": 4,
    "test_spider_hardening.py": 4,
    "test_srt_timeline_anchor.py": 4,
    "test_regression_main.py": 4,
    "test_web_tray.py": 3,
    "test_regression_postprocess.py": 2,
    "test_sync_http.py": 2,
    "test_web_config.py": 2,
    "test_async_http.py": 1,
    "test_bili_e2e.py": 1,
    "test_build_exe.py": 1,
    "test_config_io_update_file.py": 1,
    "test_cookie_cache.py": 1,
    "test_recorder_status.py": 1,
    "test_run_gates.py": 1,
    "test_ttwid.py": 1,
    "test_web_config_secret_mask.py": 1,
}

_R11_BARE_CALLED_DEBT: dict[str, int] = {
    # 同上：无参 assert_called* 且 mock 方法名承载请求语义的存量。
    "test_async_http.py": 6,
    "test_sync_http.py": 3,
    "test_regression_wp_b_netguard.py": 1,
}

# 无参 assert_called* 只对「参数承载语义」的 mock 方法名判违例；close/remove 这类零参契约不算。
_R11_ARG_BEARING_CALLEES = frozenset(
    {"get", "post", "head", "put", "patch", "delete", "open", "request", "write", "read", "run", "call", "send"}
)
_R11_HELPER_PREFIXES = ("check_", "expect_", "assert_")


def _r11_function_body(node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[ast.stmt]:
    # 剔除 docstring：否则「只写了说明、没有任何判据」的用例会因为字符串常量被当成有内容。
    body = list(node.body)
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
        body = body[1:]
    return body


def _r11_calls(stmts: list[ast.stmt]) -> list[ast.Call]:
    out: list[ast.Call] = []
    for stmt in stmts:
        out.extend(n for n in ast.walk(stmt) if isinstance(n, ast.Call))
    return out


def _r11_has_judgement(stmts: list[ast.stmt]) -> bool:
    for stmt in stmts:
        for node in ast.walk(stmt):
            if isinstance(node, ast.Assert):
                return True
            if isinstance(node, ast.Attribute) and node.attr.startswith("assert_"):
                return True
        for call in _r11_calls([stmt]):
            func = call.func
            name = func.attr if isinstance(func, ast.Attribute) else (func.id if isinstance(func, ast.Name) else "")
            if name in ("raises", "warns", "fail", "approx"):
                return True
            if name.startswith(_R11_HELPER_PREFIXES):
                return True
    return False


def _r11_no_assert_offenders(source: str) -> list[str]:
    tree = ast.parse(source)
    out: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) or not node.name.startswith("test_"):
            continue
        body = _r11_function_body(node)
        if not body:
            continue
        if not _r11_has_judgement(body):
            out.append(node.name)
    return out


def _r11_bare_called_offenders(source: str) -> list[str]:
    tree = ast.parse(source)
    out: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if not node.func.attr.startswith("assert_called"):
            continue
        if node.args or node.keywords:
            continue
        target = node.func.value
        # mock 名形如 <obj>.<method>.assert_called_once()：取 method 名判是否承载参数语义
        if isinstance(target, ast.Attribute) and target.attr in _R11_ARG_BEARING_CALLEES:
            out.append(f"{node.lineno}:{target.attr}")
    return out


def _r11_counts() -> tuple[dict[str, int], dict[str, int]]:
    no_assert: dict[str, int] = {}
    bare: dict[str, int] = {}
    for path in _test_files():
        source = path.read_text(encoding="utf-8", errors="replace")
        try:
            first = len(_r11_no_assert_offenders(source))
            second = len(_r11_bare_called_offenders(source))
        except SyntaxError as exc:
            raise AssertionError(f"{path.name} 解析失败，R11 无法自证覆盖: {exc.msg}@{exc.lineno}") from exc
        if first:
            no_assert[path.name] = first
        if second:
            bare[path.name] = second
    return no_assert, bare


def _r11_debt_drift(
    actual: dict[str, int], table: dict[str, int]
) -> tuple[dict[str, tuple[int, int]], dict[str, tuple[int, int]]]:
    # 双向相等（④）：返回 (grew, shrunk)，两项都是「文件 → (表行, 实测)」。
    # 键集合取两侧并集、缺失侧按 0 计，于是「表外的新违例文件」落 grew、「实测已归零的僵尸表行」落
    # shrunk——与 R9 用 set 差集同时抓 unregistered/stale 是同一件事，只是判据从「有无」换成「条数」。
    grew: dict[str, tuple[int, int]] = {}
    shrunk: dict[str, tuple[int, int]] = {}
    for name in sorted(set(actual) | set(table)):
        allowed, measured = table.get(name, 0), actual.get(name, 0)
        if measured > allowed:
            grew[name] = (allowed, measured)
        elif measured < allowed:
            shrunk[name] = (allowed, measured)
    return grew, shrunk


def _r11_drift_lines(drift: dict[str, tuple[int, int]]) -> str:
    return "\n".join(
        f"  {name}: 表行 {allowed} → 实测 {measured}" for name, (allowed, measured) in sorted(drift.items())
    )


def test_r11_no_assert_debt_matches_the_table() -> None:
    actual, _ = _r11_counts()
    grew, shrunk = _r11_debt_drift(actual, _R11_NO_ASSERT_DEBT)
    # 两条方向的文案各先拼成局部变量：写在 assert 实参位上会被 black 拆成「括号包 not grew」的形态，
    # 消息本身反而读不出结构（同文件里 R8 的 detail 列表是同一取舍）。
    grew_detail = (
        "「函数体内无任何判据」的测试函数比债务表还多（S-14 同族弱断言）。方向: 实测 > 表行。"
        "处置: 给对应用例补真实判据；确属合规的委托形态才把表行改大并写明理由:\n" + _r11_drift_lines(grew)
    )
    shrunk_detail = (
        "债务表高于实测。方向: 实测 < 表行——债务已修但表行停在旧上限，留着就等于给该文件一张"
        "「可悄悄退化回旧上限」的免费额度，且债务表从此与现实脱钩。"
        "处置: 把表行改成实测值，实测为 0 时整条删除:\n" + _r11_drift_lines(shrunk)
    )
    assert not grew, grew_detail
    assert not shrunk, shrunk_detail
    assert len(_test_files()) > 50, "R11 扫描面异常（用例文件数过少），判据可能空转"


def test_r11_bare_called_debt_matches_the_table() -> None:
    _, actual = _r11_counts()
    grew, shrunk = _r11_debt_drift(actual, _R11_BARE_CALLED_DEBT)
    assert not grew, (
        "不带参数的 assert_called*（请求参数承载契约，只数次数锁不住）比债务表还多。"
        "方向: 实测 > 表行，处置: 补 assert_called_once_with(...) 一类的参数断言，"
        "确属零参契约才把表行改大并写明理由:\n" + _r11_drift_lines(grew)
    )
    assert not shrunk, (
        "债务表高于实测。方向: 实测 < 表行——修掉的裸 assert_called* 没同步下调表行，"
        "该文件因此握有「退化回旧上限」的免费额度。处置: 表行改成实测值，归零则整条删除:\n" + _r11_drift_lines(shrunk)
    )


def test_r11_debt_table_files_exist() -> None:
    names = {p.name for p in _test_files()}
    for table in (_R11_NO_ASSERT_DEBT, _R11_BARE_CALLED_DEBT):
        missing = sorted(set(table) - names)
        assert not missing, f"R11 债务表登记了不存在的文件（用例已删/改名，须同批删条目）: {missing}"


def test_r11_guard_red_in_both_table_drift_directions() -> None:
    # 双向比较的自证（少它就是本轮要消灭的形态）：同一组实测值分别与「表偏高 1」「表偏低 1」比对，
    # 两个方向都必须被点名；再补两侧的文件集合漂移（表外新文件 / 实测归零的僵尸行）与逐文件相等时
    # 必须零漂移。若有人把比较退回 `实测 > 表` 单向，这一条会当场变红，而不是等到债务表烂掉才发现。
    actual = {"test_a.py": 2}
    grew, shrunk = _r11_debt_drift(actual, {"test_a.py": 1})
    assert grew == {"test_a.py": (1, 2)} and not shrunk, "R11 失效：实测高于表行未被判为新增债务"
    grew, shrunk = _r11_debt_drift(actual, {"test_a.py": 3})
    assert shrunk == {"test_a.py": (3, 2)} and not grew, "R11 失效：修掉债务却留着膨胀表行未被判红（单向棘轮回归）"
    grew, shrunk = _r11_debt_drift(actual, {})
    assert grew == {"test_a.py": (0, 2)} and not shrunk, "R11 失效：表外的新违例文件未被判红（文件集合须双向相等）"
    grew, shrunk = _r11_debt_drift({}, {"test_a.py": 2})
    assert shrunk == {"test_a.py": (2, 0)} and not grew, "R11 失效：实测归零的僵尸表行未被判红（须整条删除）"
    assert _r11_debt_drift(actual, {"test_a.py": 2}) == ({}, {}), "R11 误报：表行与实测逐文件相等时仍被判为漂移"
    assert _r11_debt_drift({}, {}) == ({}, {}), "R11 误报：两侧皆空时仍被判为漂移"


def test_r11_guard_actually_catches_the_weak_forms() -> None:
    # 反向见证：判据必须认出两种弱形态，且不得把「有 assert」「helper 委托」「零参契约」判成违例。
    no_assert = "def test_x():\n    do_something()\n"
    assert _r11_no_assert_offenders(no_assert) == ["test_x"], "R11 失效：无判据用例未被发现"
    has_assert = "def test_y():\n    do_something()\n    assert 1 == 1\n"
    assert _r11_no_assert_offenders(has_assert) == [], "R11 误报：含 assert 的用例被判违例"
    helper = "def test_z():\n    check_contract(1)\n"
    assert _r11_no_assert_offenders(helper) == [], "R11 误报：helper 委托型用例被判违例"
    bare = "def test_w(mock_client):\n    mock_client.get.assert_called_once()\n"
    assert _r11_bare_called_offenders(bare) == ["2:get"], "R11 失效：参数承载语义的裸 assert_called_once 未被发现"
    zero_arg = "def test_v(response):\n    response.close.assert_called_once()\n"
    assert _r11_bare_called_offenders(zero_arg) == [], "R11 误报：零参契约（close）被判违例"
