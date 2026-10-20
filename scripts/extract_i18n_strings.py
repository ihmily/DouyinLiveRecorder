# -*- coding: utf-8 -*-
# i18n 待翻译串提取器：AST 扫描运行时代码（main/gui/web/msg_push/i18n + src/ 全部 .py），
# 提取 print() 的全部常量实参、logger.*() 与 i18n.tr() 的首参（常量串或 f-string 模板底稿），
# 与四语目录（zh_CN.po / en_US.json / en_GB.json / zh_TW.yaml）比对并打印缺失清单。
# 只读工具、仅供维护期使用：不进运行时链路，也不在 AGENTS.md 的门禁命令块里（缺失靠人工跟进）。
#
# 三个**扫不到的盲区**（AGENTS.md 第 14 条同源）——新增这类用户可见文案必须手工登记进四语
# 目录并重编 .mo，否则本脚本会一直报「0 缺失」的假绿：
#   ① color_obj.print_colored(...)（main.py 彩色控制台输出，不是 print 调用）；
#   ② messagebox.show*（gui.py 弹窗标题与正文）；③ 推送正文（msg_push.py 裸字面量 + replace 模板）。
# 另两个边界：web/app.js 自带四套内嵌目录（与后端目录互不相干，不在扫描面内，须手工五处同改）；
# 「疑似冗余」段只是参考级——孤儿 msgid（目录比代码多）不会变红，改源码删功能时要人工回查。
#
# f-string 模板还原约定（与既有目录一致）：
#   1. 丢弃格式说明符：{_backoff:.0f} → {_backoff}
#   2. 丢弃转换符：{value!r} → {value}
#   3. 表达式内双引号转单引号：{d.get("k", "v")} → {d.get('k', 'v')}（po msgid 内双引号需转义）
#   4. 隐式拼接（相邻字符串/f-string 字面量）按语义合并为单条模板
#   5. i18n.tr(模板, **kw) 的首参常量串即模板（占位符已是标识符形态）——不收录会让 tr 化后的
#      调用点从提取结果中消失，缺失检测退化为假绿（f-string 与 tr 双形态并存期必须都扫）
#   4/5 只递归**首参/常量实参**：实参位的 f-string（`_backoff=f"{v:.0f}"`）发生在查表之后、
#   不影响 msgid，故不收录。

import ast
import importlib.util
import json
import re
import sys
from pathlib import Path
from typing import cast

ROOT = Path(__file__).resolve().parent.parent

SCAN_FILES = [
    ROOT / "main.py",
    ROOT / "gui.py",
    # [历史注] 原第三条是 gui_legacy.py（2026-09-10 随 v4.1.0-dev 删除，2026-09-21 清掉引用）；
    # 它此前恒被 main() 的 exists() 兜底跳过，留着只会让人误以为这里仍是扫描入口
    ROOT / "web.py",
    ROOT / "msg_push.py",
    ROOT / "i18n.py",
] + sorted((ROOT / "src").rglob("*.py"))

# 只有这些 logger 方法名的首参被视为「可翻译串」。tests/test_i18n_migration.py 里另有一份
# 同名集合并注明与之同口径——改这里必须同时改那里，否则门禁判的与提取的又是两套。
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


def _load_compile_po() -> object:
    # 按文件路径加载 scripts/compile_po.py 复用它的 parse_po()：.po 的多行 msgid 与转义还原
    # 只有那一份实现是对的，本脚本再写一份就会与它漂移（键集合比对随之假红）
    spec = importlib.util.spec_from_file_location("compile_po_probe", ROOT / "scripts" / "compile_po.py")
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def formatted_value_template(node: ast.FormattedValue, source: str) -> str:
    # 还原 {expr} 占位符：丢格式说明符与转换符、表达式内双引号转单引号
    seg = ast.get_source_segment(source, node.value) or ""
    seg = seg.replace('"', "'")
    return "{" + seg + "}"


def extract_constant_or_template(node: ast.AST, source: str) -> str | None:
    # 常量串直接返回；f-string（含隐式拼接）按 values 重建模板；其余返回 None
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        parts: list[str] = []
        for value in node.values:
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                parts.append(value.value)
            elif isinstance(value, ast.FormattedValue):
                parts.append(formatted_value_template(value, source))
        return "".join(parts) if parts else None
    return None


# i18n.tr(...) 的调用形态：裸 tr 或 <别名>.tr。别名集合必须覆盖仓内全部写法，
# 否则该调用点会从提取结果消失，缺失检测对它退化为假绿（gui.py 用的是 i18n_module）。
TR_CALLER_IDS = {"i18n", "i18n_module"}

# ui_i18n.T(...) 的调用形态：裸 T（gui.py 的静态标签标记，src/ui_i18n.py 提供）。
# i18n 静态标签（按钮/表头/窗口标题）经 T() 建时查表 + 登记重译，其 msgid 与 tr 同族；
# 不纳入扫描面则这批词条只有人工登记一条路，缺失检测对它们退化为假绿。
T_CALLER_IDS = {"T"}


def scan_file(path: Path) -> set[str]:
    # 单文件扫描：print 的每个实参、logger.* 与 tr 的首参，各按规则 1~5 还原成模板形态。
    # 已知局限（MID-68 同源）：只认「常量串 / 单个 f-string」两种首参，`f"A" + (f"B" if x else "")`
    # 这种 ast.BinOp 形态这里看不见——所以「目录覆盖完整」对本脚本是盲区，只能由
    # tests/test_i18n_migration.py 的收紧判据（首参**子树**）兜住；新增形参日志一律写 tr(常量模板)。
    source = path.read_text(encoding="utf-8-sig")
    tree = ast.parse(source, filename=str(path))
    found: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "print":
            for arg in node.args:
                text = extract_constant_or_template(arg, source)
                if text is not None:
                    found.add(text)
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in LOGGER_METHODS
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "logger"
            and node.args
        ):
            text = extract_constant_or_template(node.args[0], source)
            if text is not None:
                found.add(text)
        # i18n.tr(模板, **kw) / tr(模板, **kw)：首参常量串即模板（规则 5）
        if isinstance(node, ast.Call) and node.args:
            func = node.func
            is_tr = (isinstance(func, ast.Name) and func.id == "tr") or (
                isinstance(func, ast.Attribute)
                and func.attr == "tr"
                and isinstance(func.value, ast.Name)
                and func.value.id in TR_CALLER_IDS
            )
            # ui_i18n.T(模板)：静态标签标记，首参同样按规则 5 提取（apply_title 的第二参
            # 也是 T(...)，内层 T 调用被 ast.walk 独立访问，无需为它写特例）
            is_t = isinstance(func, ast.Name) and func.id in T_CALLER_IDS
            if is_tr or is_t:
                text = extract_constant_or_template(node.args[0], source)
                if text is not None:
                    found.add(text)

    return found


def is_valuable(text: str) -> bool:
    # 过滤无翻译价值项：纯符号装饰线 / 纯占位符无自然语言（与既有收录约定一致）
    if not text.strip():
        return False
    if set(text.strip()) <= set("=-.*#|+_/ \t\r\n"):
        return False
    # 剥掉 {expr} 占位符块后须残留自然语言（CJK 或字母词），否则属纯占位符
    # 模板（如 {color}{text}{Color.RESET} / {rec_info}/{filename}），无翻译价值。
    # 不能先剥花括号再查字母：占位符表达式内的标识符（color/Color）也是字母，会把纯模板
    # 误判为有价值——必须以「花括号块之外」的残渣为准。
    residue = re.sub(r"\{[^{}]*\}", "", text)
    return any(ch.isalpha() or "\u4e00" <= ch <= "\u9fff" for ch in residue)


def load_catalog_keys() -> dict[str, set[str]]:
    compile_po = _load_compile_po()
    # 剔除 gettext 头部空 msgid ""：JSON/YAML 目录本就不含它（运行时加载亦会 pop），
    # 不剔除会让一致性比对永远报「少 1」的假阳性
    keys = {"zh_CN(po)": set(parse_keys(compile_po)) - {""}}
    for lang in ("en_US", "en_GB"):
        keys[f"{lang}.json"] = set(json.loads((ROOT / "i18n" / f"{lang}.json").read_text(encoding="utf-8-sig")))
    # PyYAML 是可选依赖且无类型存根：与 i18n.py 一致，显式忽略 mypy 的
    # import-untyped，避免要求额外安装 types-PyYAML（本项目不把 PyYAML 当硬依赖）
    import yaml  # type: ignore[import-untyped]

    keys["zh_TW.yaml"] = set(yaml.safe_load((ROOT / "i18n" / "zh_TW.yaml").read_text(encoding="utf-8-sig")))
    return keys


def parse_keys(compile_po: object) -> dict[str, str]:
    # 复用 compile_po 的权威 po 解析（多行 msgid / 转义还原均正确）。
    # 经 getattr 动态取属性调用返回 Any，cast 收敛回声明类型（warn_return_any 门禁）
    return cast(dict[str, str], getattr(compile_po, "parse_po")(getattr(compile_po, "PO_PATH")))


def main() -> int:
    # 恒退 0：本脚本是「报告器」而不是门禁判据（AGENTS.md 的门禁命令块里也没有它），
    # 缺失条目由维护者跟进；真正会让 CI 变红的是 tests/test_i18n_migration.py 的三条不变量。
    runtime_strings: set[str] = set()
    for path in SCAN_FILES:
        if not path.exists():
            continue
        runtime_strings |= scan_file(path)
    runtime_strings = {s for s in runtime_strings if is_valuable(s)}

    catalogs = load_catalog_keys()
    zh_keys = catalogs["zh_CN(po)"]

    for name, keys in catalogs.items():
        if keys != zh_keys:
            print(f"[不一致] {name} 与 zh_CN.po 差异：多 {len(keys - zh_keys)} / 少 {len(zh_keys - keys)}")

    missing = sorted(runtime_strings - zh_keys)
    stale = sorted(zh_keys - runtime_strings)

    print(f"运行时提取（有价值）串：{len(runtime_strings)} 条")
    print(f"zh_CN.po 现有条目：{len(zh_keys)} 条")
    print(f"\n== 缺失（运行时有、目录无，{len(missing)} 条）==")
    for s in missing:
        print(f"  + {s!r}")
    print(f"\n== 疑似冗余（目录有、运行时无，{len(stale)} 条，含历史/兼容条目，仅参考）==")
    for s in stale[:25]:
        print(f"  - {s!r}")
    if len(stale) > 25:
        print(f"  …（另 {len(stale) - 25} 条省略）")
    _ = sys.stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
