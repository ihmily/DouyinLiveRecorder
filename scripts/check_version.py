"""版本一致性检查脚本。

以 pyproject.toml 中的 version 字段作为单一事实源（Single Source of Truth），
与 main.py、Dockerfile、README.md、CODE_WIKI.md、i18n/zh_CN.po 中的版本号比对。
任何不一致将以非零退出码报告，适用于 CI 流水线。
"""

import re
import sys
from pathlib import Path

# 项目根目录（scripts/ 的上一级）
ROOT = Path(__file__).resolve().parent.parent


def strip_v(version: str) -> str:
    """去除版本号前缀 v。"""
    return version.lstrip("v")


def extract_pyproject_version() -> str:
    """从 pyproject.toml 提取 version 字段（单一事实源）。"""
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    m = re.search(r'^version\s*=\s*["\'](.+?)["\']', text, re.MULTILINE)
    if not m:
        print("ERROR: 无法从 pyproject.toml 提取 version 字段", file=sys.stderr)
        sys.exit(2)
    return strip_v(m.group(1))


def extract_main_version() -> str | None:
    """从 main.py 提取 version 变量值。

    main.py 现在从 pyproject.toml 动态读取版本号，
    此函数用于验证 main.py 中的 _read_version_from_pyproject 回退逻辑
    所解析出的版本是否与 pyproject.toml 一致。
    由于 main.py 使用 importlib.metadata 或正则解析，
    这里直接检查 main.py 是否已移除硬编码版本。
    """
    text = (ROOT / "main.py").read_text(encoding="utf-8")
    # 检查是否还存在硬编码版本号（旧模式：version: str = "vX.Y.Z"）
    if re.search(r'^version:\s*str\s*=\s*["\']v?\d', text, re.MULTILINE):
        return "HARDCODED"  # 标记为仍有硬编码
    # main.py 现在动态读取，返回 None 表示"已改为动态读取，无需比对"
    return None


def extract_dockerfile_version() -> str | None:
    """从 Dockerfile LABEL 中提取 version。"""
    text = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    m = re.search(r'version="(.+?)"', text)
    return strip_v(m.group(1)) if m else None


def extract_readme_version() -> str | None:
    """从 README.md 变更日志标题提取最新版本号。"""
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    m = re.search(r"^###\s+v?(\d+\.\d+\.\d+(?:\.\d+)?)", text, re.MULTILINE)
    return strip_v(m.group(1)) if m else None


def extract_codewiki_version() -> str | None:
    """从 CODE_WIKI.md 项目概览中提取版本号。"""
    text = (ROOT / "CODE_WIKI.md").read_text(encoding="utf-8")
    m = re.search(r"\*\*版本\*\*:\s*(\d+\.\d+\.\d+(?:\.\d+)?)", text)
    return strip_v(m.group(1)) if m else None


def extract_po_version() -> str | None:
    """从 i18n/zh_CN.po 注释或 Project-Id-Version 中提取版本号。"""
    po_path = ROOT / "i18n" / "zh_CN" / "LC_MESSAGES" / "zh_CN.po"
    if not po_path.exists():
        return None
    text = po_path.read_text(encoding="utf-8")
    m = re.search(r"Project-Id-Version:.*?(\d+\.\d+\.\d+(?:\.\d+)?)", text)
    if not m:
        m = re.search(r"#\s*版本:\s*(\d+\.\d+\.\d+(?:\.\d+)?)", text)
    return strip_v(m.group(1)) if m else None


def main() -> int:
    base_version = extract_pyproject_version()
    print(f"基准版本 (pyproject.toml): {base_version}")

    checks: list[tuple[str, str | None]] = [
        ("Dockerfile", extract_dockerfile_version()),
        ("README.md", extract_readme_version()),
        ("CODE_WIKI.md", extract_codewiki_version()),
        ("i18n/zh_CN.po", extract_po_version()),
    ]

    errors: list[str] = []
    for name, ver in checks:
        if ver is None:
            errors.append(f"  [WARN] {name}: 未能提取版本号")
        elif ver != base_version:
            errors.append(f"  [FAIL] {name}: {ver} != {base_version}")
        else:
            print(f"  [OK]   {name}: {ver}")

    # 检查 main.py 是否已移除硬编码版本号
    main_status = extract_main_version()
    if main_status == "HARDCODED":
        errors.append("  [FAIL] main.py: 仍存在硬编码版本号，应改为从 pyproject.toml 动态读取")
    else:
        print("  [OK]   main.py: 已从 pyproject.toml 动态读取版本号")

    if errors:
        print("\n版本不一致:", file=sys.stderr)
        for e in errors:
            print(e, file=sys.stderr)
        return 1

    print("\n[PASS] 所有文件版本号一致（pyproject.toml 为单一事实源）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
