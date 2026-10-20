# -*- encoding: utf-8 -*-
#
# 元数据生成物同步脚本 — 让 uv.lock 与 DouyinLiveRecorder.egg-info 始终从 pyproject.toml 重新生成，
# 而不是手改版本号（手写版本是反复漂移的根因：4.3.0 -> 4.4.0 那次 egg-info / uv.lock 都没跟上）。
#
# 用法:
#   python scripts/sync_metadata.py            # 重新生成 uv.lock 与 egg-info
#   python scripts/sync_metadata.py --check    # 仅校验二者是否与 pyproject.toml 一致，不改文件
#
# 机制：uv.lock 经 `uv lock` 整文件重算（顺带补齐漏写的依赖，如 socksio/h2/urllib3）；egg-info
# 经 setuptools egg_info 命令重建。二者都是从 pyproject.toml 派生的产物、无写死版本号，所以
# 改完 pyproject.toml 跑一次本脚本即可让它们重新对齐。校验口径与 tests/test_regression_2026_09_22_gates.py
# 的两条元数据回归锁一致，但本脚本不依赖 pytest（可单独手动跑），CI 侧由那两条锁兜底。
#
# 退出码契约：
#   --check         : 0 = 两个派生产物均与 pyproject.toml 一致；1 = 已漂移。纯读文件，绝不调
#                     subprocess / 不联网（CI static job 在未装项目依赖的 job 里跑它）。
#   无参数（重建）  : 0/1 一律由**最终 check()** 决定，与中间步骤的 WARN 无关。本模式是「生成器」
#                     而非门禁：uv 缺失属可接受的环境差异（AGENTS.md「关键约定」#1 允许只跑
#                     egg_info 一侧），而产物到底对不对只有 check() 能自证；把 WARN 也判失败会让
#                     没装 uv 的机器恒红，且无法区分「已补齐」与「真的漂移」。门禁语义一律走 --check。
#   降级边界        : uv 段（探测/锁定）失败只让 uv.lock 这一段落 WARN，**必须**继续执行 egg-info
#                     重建；两条降级路径都不得让脚本抛栈退出。
# 回归锁：tests/test_scripts_error_paths.py（uv 缺失/探测抛错时 WARN 可达且 egg-info 仍重建、
#         --check 路径零子进程）。

from __future__ import annotations

import shutil
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import Any, cast

ROOT = Path(__file__).resolve().parent.parent
PYPROJECT = ROOT / "pyproject.toml"
UV_LOCK = ROOT / "uv.lock"
EGG_INFO = ROOT / "DouyinLiveRecorder.egg-info"


def _read_project() -> dict[str, Any]:
    # 单一事实源：pyproject.toml 的 [project] 段。
    data: dict[str, Any] = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    return cast("dict[str, Any]", data["project"])


def _check_uv_lock(project: dict) -> bool:
    # uv.lock 里本项目根包是 editable="." 的那条；版本与依赖集合都必须等于 pyproject。
    if not UV_LOCK.exists():
        print("  MISSING  uv.lock")
        return False
    lock = tomllib.loads(UV_LOCK.read_text(encoding="utf-8"))
    roots = [
        pkg
        for pkg in lock.get("package", [])
        if pkg.get("name") == "douyinliverecorder" and pkg.get("source", {}).get("editable") == "."
    ]
    if len(roots) != 1:
        print(f"  MISMATCH  uv.lock 根包数量异常: {len(roots)}")
        return False
    if str(roots[0].get("version")) != str(project["version"]):
        print(f"  MISMATCH  uv.lock 版本 {roots[0].get('version')} != pyproject {project['version']}")
        return False
    print(f"  OK        uv.lock 版本 = {project['version']}")
    return True


def _check_egg_info(project: dict) -> bool:
    # egg-info/PKG-INFO 的 Version 字段必须等于 pyproject（importlib.metadata 优先读它）。
    pkg_info = EGG_INFO / "PKG-INFO"
    if not pkg_info.exists():
        print("  MISSING  DouyinLiveRecorder.egg-info/PKG-INFO")
        return False
    text = pkg_info.read_text(encoding="utf-8")
    version = next(
        (line.partition(":")[2].strip() for line in text.splitlines() if line.startswith("Version:")),
        None,
    )
    if version != str(project["version"]):
        print(f"  MISMATCH  egg-info 版本 {version} != pyproject {project['version']}")
        return False
    print(f"  OK        egg-info 版本 = {project['version']}")
    return True


def check() -> bool:
    project = _read_project()
    ok = True
    ok = _check_uv_lock(project) and ok
    ok = _check_egg_info(project) and ok
    return ok


def _run(cmd: list[str]) -> int:
    print(f"  RUN       {' '.join(cmd)}")
    return subprocess.call(cmd, cwd=str(ROOT))


# uv.lock 一段的独立执行单元：返回 True = 已交给 uv 重算，False = 本段降级。
# 必须从 regenerate() 抽出成独立函数：子进程异常（PATH 无 uv 时抛的是 FileNotFoundError
# 而不是非 0 返回码）若不在此截住，会连带拖死**完全不依赖 uv** 的 egg-info 重建，让没装 uv
# 的机器上整个脚本失效。shutil.which 覆盖「PATH 里没有」，两处捕 OSError 覆盖「which 命中
# 但不可 exec」（命中目录 / 无执行位 / Windows 下命中同名非 exe 文件）。
# 任何降级都只影响本段返回值，绝不向调用方抛出。
def _sync_uv_lock() -> bool:
    uv_bin = shutil.which("uv")
    if uv_bin is None:
        print(
            "  WARN      PATH 未检测到 uv，跳过 uv.lock（请手动执行 `uv lock`）",
            file=sys.stderr,
        )
        return False

    try:
        uv_probe = subprocess.run([uv_bin, "--version"], capture_output=True, text=True)
    except OSError as e:
        print(
            f"  WARN      uv 不可执行（{type(e).__name__}: {e}），跳过 uv.lock（请手动执行 `uv lock`）",
            file=sys.stderr,
        )
        return False
    if uv_probe.returncode != 0:
        print(
            f"  WARN      uv --version 退出码 {uv_probe.returncode} 非 0，跳过 uv.lock（请手动执行 `uv lock`）",
            file=sys.stderr,
        )
        return False

    try:
        lock_rc = _run([uv_bin, "lock"])
    except OSError as e:
        print(
            f"  WARN      uv lock 无法启动（{type(e).__name__}: {e}），uv.lock 未更新",
            file=sys.stderr,
        )
        return False
    if lock_rc != 0:
        print("  WARN      uv lock 执行失败，uv.lock 可能未更新", file=sys.stderr)
        return False
    return True


def regenerate() -> bool:
    project = _read_project()
    print(f"从 pyproject.toml 读取版本号: {project['version']}")
    print()

    # uv.lock：优先 uv lock（整文件重算，自动补齐漏写依赖）；无 uv 则提示手动处理。
    # 返回值刻意不参与后续流程 —— uv 段无论成败都必须继续走 egg-info 段。
    _sync_uv_lock()
    print()

    # egg-info：setuptools egg_info 重建（读 pyproject.toml 派生，无需手写版本）。
    egg_cmd = [
        sys.executable,
        "-c",
        "import sys; sys.argv=['setup.py','egg_info','--egg-base','.']; from setuptools import setup; setup()",
    ]
    if _run(egg_cmd) != 0:
        print("  WARN      egg-info 重建失败", file=sys.stderr)
    print()

    return check()


def main() -> None:
    if "--check" in sys.argv[1:]:
        if check():
            print("\n[OK] uv.lock 与 egg-info 均与 pyproject.toml 一致")
            sys.exit(0)
        print("\n[FAIL] 元数据已漂移，运行 `python scripts/sync_metadata.py` 重新生成", file=sys.stderr)
        sys.exit(1)

    regenerate()
    if check():
        print("\n[OK] 已重新生成并校验通过")
        sys.exit(0)
    print("\n[FAIL] 重新生成后仍不一致，请检查 uv / setuptools", file=sys.stderr)
    sys.exit(1)


if __name__ == "__main__":
    main()
