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
# 改完 pyproject.toml 跑一次本脚本即可让它们重新对齐。校验口径与 tests/test_regression_gates.py
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
#   2（M-94 追加，仅重建模式）: 生成步骤的子进程超过 _CHILD_TIMEOUT_SECONDS 未结束被
#                     终止 —— 「没跑成」既不是 0（已同步）也不是 1（漂移）。--check 是纯读路径、
#                     不产生这一档（它零子进程，由回归锁钉住）。
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

# —— 有界执行（M-94）———————————————————————————————
# 三条生成步骤里唯一可能永不返回的是子进程：`uv lock` 解析索引要走网络、egg_info 走 setuptools
# 插件链，任一处挂住本脚本就既没同步、也没结论。上界一律取「慢机器实测量级 × 余量」而不是
# 「CI job 超时」——job 超时那种红里没有任何一步的结论（与 run_gates.py 的同一改动同批）。
_CHILD_TIMEOUT_SECONDS = 600.0
# 超时的哨兵 rc：与 AGENTS.md 的门禁分级一致（2 = 门禁/生成器自己没跑成），
# 绝不是 0（「已同步」）也不是 1（「产物漂移」——那是在怪代码，而真相是没跑）。
_RC_TIMEOUT = 2
# 本次进程内因超时而没跑完的子进程步骤（由 _run 追加、main 消费）。
# 用列表而不是 bool：报告要点名**是哪一步**挂的，且 append 无需 global 声明。
_RUN_TIMED_OUT: list[str] = []


def _read_project() -> dict[str, Any]:
    # 单一事实源：pyproject.toml 的 [project] 段。
    try:
        data: dict[str, Any] = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as e:
        # 纯读路径兜底：读不出/解析不出时以 rc=2（没跑成，同 _RC_TIMEOUT 分档）
        # 明示「工具无法产出结论」，不得以 rc=1 + 裸栈冒充「元数据已漂移」——两者排障方向相反。
        print(f"ERROR: pyproject.toml 无法读取/解析（{type(e).__name__}: {e}）", file=sys.stderr)
        sys.exit(2)
    return cast("dict[str, Any]", data["project"])


def _check_uv_lock(project: dict) -> bool:
    # uv.lock 里本项目根包是 editable="." 的那条；版本与依赖集合都必须等于 pyproject。
    if not UV_LOCK.exists():
        print("  MISSING  uv.lock")
        return False
    try:
        lock = tomllib.loads(UV_LOCK.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as e:
        # 同 _read_project：不可读/不可解析 → rc=2「没跑成」，不冒充一致性结论。
        print(f"ERROR: uv.lock 无法读取/解析（{type(e).__name__}: {e}）", file=sys.stderr)
        sys.exit(2)
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
    try:
        text = pkg_info.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        # 同 _read_project：不可读 → rc=2「没跑成」，不冒充一致性结论。
        print(f"ERROR: egg-info/PKG-INFO 无法读取（{type(e).__name__}: {e}）", file=sys.stderr)
        sys.exit(2)
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


def _run(cmd: list[str], timeout: float = _CHILD_TIMEOUT_SECONDS) -> int:
    print(f"  RUN       {' '.join(cmd)}")
    try:
        # [2026-10-31 L-11] stdin=DEVNULL：run_gates.py:311-313 实证的同族防线——子进程读 stdin
        # 会拿到已关闭的管道句柄（WinError 6）。
        return int(subprocess.call(cmd, cwd=str(ROOT), timeout=timeout, stdin=subprocess.DEVNULL))
    except subprocess.TimeoutExpired:
        # M-94：挂住成因见文件头「有界执行」（uv lock 解析索引走网络 / egg_info 走 setuptools
        # 插件链，可能**永不返回**）。超时不是「跑成功」（rc 0）也不是「漂移」（rc 1），
        # 而是「这一步没跑成」→ 记入 _RUN_TIMED_OUT，由 main() 以 rc=2 收口（同 run_gates 口径）。
        # 只捕 TimeoutExpired：OSError 继续原样上抛，交给调用侧既有的降级分支
        # （tests/test_scripts_error_paths.py 锁的 M-32① 形态：uv 缺失只让本段 WARN）。
        _RUN_TIMED_OUT.append(" ".join(cmd) + f"（超过 {timeout:.0f}s 未结束）")
        print(
            f"  TIMEOUT   子进程超过 {timeout:.0f}s 未结束，已终止：{' '.join(cmd)}" "——属「没跑成」，不等于「已同步」",
            file=sys.stderr,
        )
        return _RC_TIMEOUT


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
        # M-94：uv --version 探测必须有上界——命中 PATH 里的目录 / 无执行位文件 / Windows 下
        # 同名非 exe 时不会抛 OSError，而是挂住等系统层面超时——本脚本常在 CI 的元数据同步
        # 步骤里跑，挂住等于整步无结论。
        uv_probe = subprocess.run(
            [uv_bin, "--version"],
            capture_output=True,
            text=True,
            timeout=_CHILD_TIMEOUT_SECONDS,
            stdin=subprocess.DEVNULL,  # 同族 WinError 6 防线，见 _run
        )
    except subprocess.TimeoutExpired:
        print(
            f"  WARN      uv --version 超过 {_CHILD_TIMEOUT_SECONDS:.0f}s 未返回，跳过 uv.lock（请手动执行 `uv lock`）",
            file=sys.stderr,
        )
        return False
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
    if lock_rc == _RC_TIMEOUT:
        print("  WARN      uv lock 超时无结论，uv.lock 未更新（成因见上一条 TIMEOUT 行）", file=sys.stderr)
        return False
    if lock_rc != 0:
        print("  WARN      uv lock 执行失败，uv.lock 可能未更新", file=sys.stderr)
        return False
    return True


def regenerate() -> bool:
    # 每次「生成」从干净的超时台账开始：调用方（main / 用例）读到的必须只属于这一轮，
    # 否则上一轮的超时会把这一轮明明跑完的结果也打成 rc=2。
    _RUN_TIMED_OUT.clear()
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
    egg_rc = _run(egg_cmd)
    if egg_rc == _RC_TIMEOUT:
        # 超时＝这一步没跑完，产物可能是上一轮的旧物；后面的 check() 即使恰好一致也不能当「已重建」。
        print("  TIMEOUT   egg-info 重建超时无结论（见上）", file=sys.stderr)
    elif egg_rc != 0:
        print("  WARN      egg-info 重建失败", file=sys.stderr)
    print()

    return check()


def main() -> None:
    if "--check" in sys.argv[1:]:
        # --check 是纯读路径（零子进程、零联网，由 tests/test_scripts_error_paths.py 钉住），
        # 因此它天然不会产生超时记录；清空只是防御「同一进程内被复用」的形态。
        _RUN_TIMED_OUT.clear()
        if check():
            print("\n[OK] uv.lock 与 egg-info 均与 pyproject.toml 一致")
            sys.exit(0)
        print("\n[FAIL] 元数据已漂移，运行 `python scripts/sync_metadata.py` 重新生成", file=sys.stderr)
        sys.exit(1)

    _RUN_TIMED_OUT.clear()
    regenerate()
    if _RUN_TIMED_OUT:
        # M-94：生成步骤里有子进程超时就**不得**退 0——旧形态下「uv lock 挂住被终止 + uv.lock
        # 恰好还是上一轮同步过的」会一路走到 check() 并打印「已重新生成并校验通过」，
        # 那等于用一句「产物一致」冒充「本步真的跑过」。退出码 2 = 没跑成，与 0/1 分档。
        print(
            "\n[FAIL] 生成步骤超时无结论：" + "；".join(_RUN_TIMED_OUT) + "\n"
            "       产物一致性检查不能代替这一步本身，请复查网络/锁文件竞争后重跑。",
            file=sys.stderr,
        )
        sys.exit(_RC_TIMEOUT)
    if check():
        print("\n[OK] 已重新生成并校验通过")
        sys.exit(0)
    print("\n[FAIL] 重新生成后仍不一致，请检查 uv / setuptools", file=sys.stderr)
    sys.exit(1)


if __name__ == "__main__":
    main()
