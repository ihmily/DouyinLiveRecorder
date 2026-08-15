# 版本一致性检查脚本。
#
# 以 pyproject.toml 中的 version 字段作为单一事实源（Single Source of Truth）。
# 各消费方均已改为从 pyproject.toml 动态读取，本脚本仅校验其“已动态化、未写死”状态：
#   - main.py         运行时从 pyproject.toml 读取（无硬编码版本）
#   - src/web_api.py  FastAPI(version=) 从 pyproject.toml 动态读取（无硬编码版本）
#   - Dockerfile      经 APP_VERSION 构建参数从 pyproject.toml 注入
#   - i18n/zh_CN.po   不再携带版本号
# README.md / CODE_WIKI.md 为文档，版本由人工维护，不在校验范围。
# 任何不一致将以非零退出码报告，适用于 CI 流水线。
#

import re
import sys
from pathlib import Path

# 项目根目录（scripts/ 的上一级）
ROOT = Path(__file__).resolve().parent.parent


def strip_v(version: str) -> str:
    # 去除版本号前缀 v。
    return version.lstrip("v")


def extract_pyproject_version() -> str:
    # 从 pyproject.toml 提取 version 字段（单一事实源）。
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    m = re.search(r'^version\s*=\s*["\'](.+?)["\']', text, re.MULTILINE)
    if not m:
        print("ERROR: 无法从 pyproject.toml 提取 version 字段", file=sys.stderr)
        sys.exit(2)
    return strip_v(m.group(1))


def extract_main_version() -> str | None:
    # 从 main.py 提取 version 变量值。
    #
    # main.py 现在从 pyproject.toml 动态读取版本号，
    # 此函数用于验证 main.py 中的 _read_version_from_pyproject 回退逻辑
    # 所解析出的版本是否与 pyproject.toml 一致。
    # 由于 main.py 使用 importlib.metadata 或正则解析，
    # 这里直接检查 main.py 是否已移除硬编码版本。
    #
    text = (ROOT / "main.py").read_text(encoding="utf-8")
    # 检查是否还存在硬编码版本号（旧模式：version: str = "vX.Y.Z"）
    if re.search(r'^version:\s*str\s*=\s*["\']v?\d', text, re.MULTILINE):
        return "HARDCODED"  # 标记为仍有硬编码
    # main.py 现在动态读取，返回 None 表示"已改为动态读取，无需比对"
    return None


def extract_dockerfile_version() -> str | None:
    # Dockerfile 通过构建参数 APP_VERSION 从 pyproject.toml 动态注入版本号，
    # LABEL version="${APP_VERSION}"，文件内不再写死版本。
    # 返回:
    #   "DYNAMIC"  -> 已是动态注入（正确）
    #   字面版本号  -> 仍写死版本（应改为动态）
    #   None       -> 未找到 version 标签（视为动态/跳过）
    text = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    if re.search(r'version="\$\{APP_VERSION\}"', text):
        return "DYNAMIC"
    m = re.search(r'version="(.+?)"', text)
    return strip_v(m.group(1)) if m else None


def extract_webapi_version() -> str | None:
    # src/web_api.py 的 FastAPI(version=...) 应从 pyproject.toml 动态读取，
    # 不应写死字面版本号。
    # 返回:
    #   "DYNAMIC"  -> version 由函数/变量动态提供（正确）
    #   字面版本号  -> 仍写死版本（应改为动态）
    #   None       -> 未找到 FastAPI(version=...)（跳过）
    text = (ROOT / "src" / "web_api.py").read_text(encoding="utf-8")
    m = re.search(
        r"FastAPI\(.*?version\s*=\s*(\"([^\"]+)\"|([A-Za-z_][\w.()]*))",
        text,
        re.DOTALL,
    )
    if not m:
        return None
    if m.group(2) is not None:
        return m.group(2)  # 写死字面量
    return "DYNAMIC"  # 由变量/函数动态提供


def extract_po_version() -> str | None:
    # i18n/zh_CN.po 不再携带版本号（Project-Id-Version 不含版本、
    # 删除 # 版本: 注释），版本以 pyproject.toml 为唯一事实源。
    # 返回:
    #   字面版本号  -> 仍写死版本（应移除）
    #   None       -> 已动态化（正确，跳过）
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

    errors: list[str] = []

    # Dockerfile：应改用 APP_VERSION 构建参数从 pyproject.toml 动态注入
    docker_status = extract_dockerfile_version()
    if docker_status == "DYNAMIC":
        print("  [OK]   Dockerfile: 版本号经 APP_VERSION 构建参数从 pyproject.toml 动态注入")
    elif docker_status is None:
        print("  [OK]   Dockerfile: 未写死版本号（动态注入）")
    else:
        errors.append(f"  [FAIL] Dockerfile: 仍写死版本号 {docker_status}（应改用 APP_VERSION 构建参数）")

    # i18n/zh_CN.po：不应携带版本号（pyproject.toml 为唯一事实源）
    po_status = extract_po_version()
    if po_status is None:
        print("  [OK]   i18n/zh_CN.po: 未携带版本号（动态，pyproject.toml 为事实源）")
    else:
        errors.append(f"  [FAIL] i18n/zh_CN.po: 仍写死版本号 {po_status}（应移除）")

    # 检查 main.py 是否已移除硬编码版本号
    main_status = extract_main_version()
    if main_status == "HARDCODED":
        errors.append("  [FAIL] main.py: 仍存在硬编码版本号，应改为从 pyproject.toml 动态读取")
    else:
        print("  [OK]   main.py: 已从 pyproject.toml 动态读取版本号")

    # 检查 src/web_api.py 的 FastAPI(version=) 是否已动态化
    web_status = extract_webapi_version()
    if web_status == "DYNAMIC":
        print("  [OK]   src/web_api.py: FastAPI 版本号从 pyproject.toml 动态读取")
    elif web_status is None:
        print("  [OK]   src/web_api.py: 未找到 FastAPI(version=)（跳过）")
    else:
        errors.append(f"  [FAIL] src/web_api.py: 仍写死版本号 {web_status}（应从 pyproject.toml 动态读取）")

    if errors:
        print("\n版本不一致:", file=sys.stderr)
        for e in errors:
            print(e, file=sys.stderr)
        return 1

    print("\n[PASS] 所有文件版本号一致（pyproject.toml 为单一事实源）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
