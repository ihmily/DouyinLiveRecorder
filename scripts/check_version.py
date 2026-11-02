# 版本一致性门禁（CI 可调用）。
#
# 单一事实源 = pyproject.toml 的 version 字段。各消费方一律**动态读取**，所以本脚本查的不是
# 「各处版本号字符串是否相等」，而是「动态化是否还在、有没有人重新写死」：
#   - main.py         运行时经 importlib.metadata / 正则从 pyproject.toml 读
#   - src/web_api.py  经 importlib.metadata 动态读取（_read_app_version）
#                     [历史注] FastAPI 依赖移除后检查对象同步换成 importlib.metadata，fail-closed 语义保留
#   - Dockerfile      经 APP_VERSION 构建参数注入；另校验「ARG APP_VERSION 声明行早于使用它的
#                     指令行」（——顺序颠倒时标签被固化成空串，只看字面的检查查不出来）
#   - i18n/zh_CN/LC_MESSAGES/zh_CN.po   不再携带版本号
# README.md / CODE_WIKI.md 是文档、版本由人工维护，刻意不在校验范围内。
# 退出码：0 一致；1 任一消费方写死/消失；2 连基准都取不到（pyproject.toml 无 version 字段）
#         ——「门禁没有可判定的数据」，与 run_gates.py 同口径，不得与「代码不合格」混为一谈。
#

import re
import sys
from pathlib import Path

# 项目根目录（scripts/ 的上一级）
ROOT = Path(__file__).resolve().parent.parent


# read_text 失败一律退 2：rc=1 的语义是「代码不合格」，而门禁自己没读成文件（缺失/权限/编码）
# 属「门禁没有可判定的数据」，混同会让排障方向整体错掉。
def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, ValueError, UnicodeDecodeError) as exc:
        print(
            f"ERROR: 门禁自身失效，无法读取 {path.name}（{type(exc).__name__}: {exc}）——不是版本不一致",
            file=sys.stderr,
        )
        sys.exit(2)


def strip_v(version: str) -> str:
    # 去除版本号前缀 v。
    # 必须用 removeprefix 而非 lstrip：lstrip("v") 是按字符集剥离，
    # 会把 "vv1.2" 剥成 "1.2"、也会误伤本身含 v 的版本串。
    return version.removeprefix("v")


def extract_pyproject_version() -> str:
    # 从 pyproject.toml 提取 version 字段（单一事实源）。
    text = _read_text(ROOT / "pyproject.toml")
    m = re.search(r'^version\s*=\s*["\'](.+?)["\']', text, re.MULTILINE)
    if not m:
        print("ERROR: 无法从 pyproject.toml 提取 version 字段", file=sys.stderr)
        sys.exit(2)
    return strip_v(m.group(1))


def extract_main_version() -> str | None:
    # 只判 main.py 里有没有**重新出现**的硬编码版本（旧模式 `version: str = "vX.Y.Z"`）。
    # 动态化之后它取的是 _read_version_from_pyproject() 的返回值，正则不再匹配，
    # 故本函数不可能、也不需要报出具体版本号——比对由 pyproject.toml 单点承担。
    # 返回 "HARDCODED" 表示有人把版本又写回了源码；返回 None 表示已是动态读取、无需比对。
    text = _read_text(ROOT / "main.py")
    # 锚点必须同时覆盖带注解（^version: str = "…"）与裸赋值（^version = "…"）两种写死形态，
    # 只匹配前者会让裸赋值形态的硬编码版本整体漏检。注解段为可选，两种形态都钉。
    if re.search(r'^version(?:\s*:\s*str)?\s*=\s*["\']v?\d', text, re.MULTILINE):
        return "HARDCODED"  # 标记为仍有硬编码
    return None


def extract_dockerfile_version() -> str | None:
    # Dockerfile 通过构建参数 APP_VERSION 从 pyproject.toml 动态注入版本号，
    # LABEL version="${APP_VERSION}"，文件内不再写死版本。
    # 返回:
    #   "DYNAMIC"  -> 已是动态注入（正确）
    #   字面版本号  -> 仍写死版本（应改为动态）
    #   None       -> 未找到 version 标签（调用方按**失败**处理，不得当通过）
    text = _read_text(ROOT / "Dockerfile")
    if re.search(r'version="\$\{APP_VERSION\}"', text):
        return "DYNAMIC"
    m = re.search(r'version="(.+?)"', text)
    return strip_v(m.group(1)) if m else None


def check_dockerfile_arg_order() -> str | None:
    # 校验「ARG APP_VERSION 的声明行早于使用它的指令起始行」，返回错误描述（None = 通过）。
    #
    # Dockerfile 按行做变量替换，若 LABEL version="${APP_VERSION}" 写在
    # `ARG APP_VERSION` 之前，构建期该变量尚未声明，标签会被固化成空串——`--build-arg`
    # 看着成功、实际毫无效果。extract_dockerfile_version() 只匹配「有没有 version="${APP_VERSION}"
    # 这个字面」，顺序颠倒时照样判 DYNAMIC，故门禁对这一整类失效永久失明。
    # 多行续写（行尾 `\`）要回溯到指令起始行：ARG 写在 LABEL 的续写行之间同样是错的，
    # 因为该指令在第一行就已经开始求值。
    lines = _read_text(ROOT / "Dockerfile").splitlines()
    decl_line: int | None = None
    use_line: int | None = None
    for idx, line in enumerate(lines, 1):
        # 注释行一律跳过：本仓 Dockerfile 的说明注释里会原样出现
        # version="${APP_VERSION}" 这类字面，按行匹配会把注释当成「使用点」而误报。
        if line.lstrip().startswith("#"):
            continue
        if decl_line is None and re.match(r"^\s*ARG\s+.*\bAPP_VERSION\b", line):
            decl_line = idx
            continue
        if use_line is None and "APP_VERSION" in line and re.search(r"version\s*=\s*\"?\$\{?APP_VERSION", line):
            start = idx
            # 向上回溯到本条指令的起始行（上一行以 `\` 结尾即为续写）
            while (
                start > 1 and lines[start - 2].rstrip().endswith("\\") and not lines[start - 2].lstrip().startswith("#")
            ):
                start -= 1
            use_line = start
    if decl_line is None:
        # 使用了却没声明 = 构建期变量为空，真缺陷；两者都不存在则是这套机制整体不在，
        # 交由 extract_dockerfile_version() 的「仍写死版本 / 找不到 version 标签」去判失败，
        # 不在这里重复报第二条。
        return "Dockerfile 未声明 ARG APP_VERSION（版本号无从注入）" if use_line else None
    if use_line is None:
        # 没有使用点：要么整块被删（不属于本脚本职责），要么写法变了；不判失败，
        # 但 DYNAMIC 那条检查已经会在「改成写死版本」时报错。
        return None
    if decl_line > use_line:
        return (
            f"Dockerfile 的 ARG APP_VERSION 声明在第 {decl_line} 行，"
            f"但第 {use_line} 行的指令就已经使用它——LABEL 会被固化为空值，"
            f"--build-arg 失效。请把 ARG 声明上移到使用点之前。"
        )
    return None


def extract_webapi_version() -> str | None:
    # src/web_api.py 的版本号应经 _read_app_version 动态读取（importlib.metadata 优先、
    # 解析 pyproject.toml 兜底），不应写死字面版本号。
    # 返回:
    #   "DYNAMIC"  -> 经 importlib.metadata 动态读取（正确）
    #   字面版本号  -> 模块级版本常量写死了字面量（应改为动态）
    #   None       -> 未找到动态读取形态（调用方按**失败**处理，不得当通过）
    text = _read_text(ROOT / "src" / "web_api.py")
    if not re.search(r"importlib\.metadata", text):
        return None
    # 动态读取形态在位；再防「保留 import 但把模块级常量回填成字面量」的半吊子写法
    m = re.search(r"_APP_VERSION\s*=\s*[\"'](\d[\w.]*)[\"']", text)
    if m:
        return m.group(1)
    return "DYNAMIC"


def extract_po_version() -> str | None:
    # i18n/zh_CN/LC_MESSAGES/zh_CN.po 不再携带版本号（Project-Id-Version 不带版本、`# 版本:` 注释已删），
    # 版本以 pyproject.toml 为唯一事实源。
    # 返回:
    #   字面版本号  -> 仍写死版本（应移除）
    #   None       -> 未携带版本号（正确）
    po_path = ROOT / "i18n" / "zh_CN" / "LC_MESSAGES" / "zh_CN.po"
    if not po_path.exists():
        # 文件缺席也返回 None，但**不**是「查不到就算通过」：同一条缺失会被门禁块里的
        # scripts/compile_po.py 以 rc=2 拦下（它找不到 PO_PATH），不必在这里重复报一份。
        return None
    text = _read_text(po_path)
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
        # None 原样打印 [OK] 属「检查对象消失即通过」——把 `LABEL version=...` 整块删掉
        # 是本项最省事的破坏方式，删完门禁反而更绿。与 sync_version.py::check_all 的
        # 「先判命中再判等」同构：未命中一律判失败。
        errors.append("  [FAIL] Dockerfile: 未找到任何 version 标签（检查对象消失，不得当作通过）")
    else:
        errors.append(f"  [FAIL] Dockerfile: 仍写死版本号 {docker_status}（应改用 APP_VERSION 构建参数）")

    # Dockerfile：动态「写法」还不够，ARG 声明还必须早于使用点——
    # 顺序颠倒时上面的 DYNAMIC 判定依旧通过，但镜像 version 标签会被固化成空串。
    docker_order = check_dockerfile_arg_order()
    if docker_order is None:
        print("  [OK]   Dockerfile: ARG APP_VERSION 声明先于使用点")
    else:
        errors.append(f"  [FAIL] Dockerfile: {docker_order}")

    # i18n/zh_CN/LC_MESSAGES/zh_CN.po：不应携带版本号（pyproject.toml 为唯一事实源）
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

    # 检查 src/web_api.py 的版本号是否动态读取
    web_status = extract_webapi_version()
    if web_status == "DYNAMIC":
        print("  [OK]   src/web_api.py: 版本号经 importlib.metadata 动态读取")
    elif web_status is None:
        # 把动态读取整段删掉即可让本项从「检查」变成「跳过」，属最省事的破坏。
        # 要求检查对象存在，确需放行时显式加开关，不得默认放行消失态。
        errors.append(
            "  [FAIL] src/web_api.py: 未找到版本号动态读取形态（importlib.metadata）（检查对象消失，不得当作通过）"
        )
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
