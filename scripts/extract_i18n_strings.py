# -*- coding: utf-8 -*-
# i18n 待翻译串提取器：AST 扫描运行时代码（main/gui/web/msg_push/i18n/src），
# 提取 print() 全部常量参数 + logger.*() 首参常量串与 f-string 模板底稿，
# 与四语目录比对输出缺失清单。仅供维护期使用，不进运行时链路。
#
# f-string 模板还原约定（与既有目录一致）：
#   1. 格式说明符（如 :.0f）丢弃——{_backoff:.0f} → {_backoff}
#   2. 转换符（如 !r）丢弃——{value!r} → {value}
#   3. 表达式内双引号转单引号——{d.get("k", "v")} → {d.get('k', 'v')}
#      （po msgid 内双引号需转义，目录统一用单引号形态）
#   4. 隐式拼接（相邻字符串/f-string 字面量）按语义合并为单条模板

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
    ROOT / "gui_legacy.py",
    ROOT / "web.py",
    ROOT / "msg_push.py",
    ROOT / "i18n.py",
] + sorted((ROOT / "src").rglob("*.py"))

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


def scan_file(path: Path) -> set[str]:
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

    return found


def is_valuable(text: str) -> bool:
    # 过滤无翻译价值项：纯符号装饰线 / 纯占位符无自然语言（与既有收录约定一致）
    if not text.strip():
        return False
    if set(text.strip()) <= set("=-.*#|+_/ \t\r\n"):
        return False
    # 剥掉 {expr} 占位符块后须残留自然语言（CJK 或字母词），否则属纯占位符
    # 模板（如 {color}{text}{Color.RESET} / {rec_info}/{filename}），无翻译价值。
    # 注意不能先剥花括号再查字母：占位符表达式内的标识符（color/Color）也是字母，
    # 会让纯模板被误判为有价值——必须以「花括号块之外」的残渣为准。
    residue = re.sub(r"\{[^{}]*\}", "", text)
    return any(ch.isalpha() or "\u4e00" <= ch <= "\u9fff" for ch in residue)


def load_catalog_keys() -> dict[str, set[str]]:
    compile_po = _load_compile_po()
    # 剔除 gettext 头部空 msgid ""：JSON/YAML 目录本就不含它（运行时加载亦会 pop），
    # 不剔除会让一致性比对永远报「少 1」的假阳性
    keys = {"zh_CN(po)": set(parse_keys(compile_po)) - {""}}
    for lang in ("en_US", "en_GB"):
        keys[f"{lang}.json"] = set(json.loads((ROOT / "i18n" / f"{lang}.json").read_text(encoding="utf-8-sig")))
    import yaml

    keys["zh_TW.yaml"] = set(yaml.safe_load((ROOT / "i18n" / "zh_TW.yaml").read_text(encoding="utf-8-sig")))
    return keys


def parse_keys(compile_po: object) -> dict[str, str]:
    # 复用 compile_po 的权威 po 解析（多行 msgid / 转义还原均正确）。
    # 经 getattr 动态取属性调用返回 Any，cast 收敛回声明类型（warn_return_any 门禁）
    return cast(dict[str, str], getattr(compile_po, "parse_po")(getattr(compile_po, "PO_PATH")))


def main() -> int:
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
