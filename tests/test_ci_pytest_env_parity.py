# ci.yml「跑 pytest 的 job 必须装齐运行时依赖」与「Qt 窗口层 job 必须装 Qt 运行库」的回归锁。
#
# 事故一（2026-10-18 手动触发 CI 实测）：vbs-behavior-test job 只装了 pytest，
#   tests/test_stop_recording_vbs.py 的 11 条用例在 setup 阶段全数 ERROR——
#   `ModuleNotFoundError: No module named 'distro'`。被测文件本身只 import 标准库 + pytest，
#   故障来自 tests/conftest.py 的三个 **autouse** fixture：
#     · _clean_credential_caches → `from src import spider` → src/node_install.py 顶层 `import distro`；
#     · _hermetic_danmaku_hub → `import src.danmaku_monitor`（同一条 src 导入链）；
#     · _pin_identity_translation → `import i18n` → i18n.py 顶层 `from loguru import logger`。
#   即「跑仓库里任何一条 pytest」的真实门槛是**整份 requirements.txt**，与被测文件自己的 import 无关。
#
# 判据：任何出现 pytest（执行或安装）的 job，其步骤里必须另有 `pip install -r requirements.txt`。
#   新增「轻量 job」时会被当场拦下，而不是等一次手动触发 CI 才在 ERROR 里发现。
#
# 事故二（同日）：test job 的 apt 只装了 ffmpeg + xvfb，而 GUI 窗口层已迁 PySide6：ubuntu runner 缺
#   libEGL.so.1 时 `from PySide6.QtGui import ...` 抛 ImportError，两个 Qt 测试模块以 collection error
#   形态**中断整轮**（4337 collected / 2 errors → Interrupted，rc=2，覆盖率与逐模块门禁全部拿不到数据）。
#   故再钉两条：
#     · apt 侧必须装 Qt 运行库（锚点 libegl1，见 _QT_RUNTIME_LIB_RE）——系统库不属于 pip 的兜底面；
#     · test job 必须有一道 collect-only 闸门拦「整模块 skip 而 rc 仍为 0」的假绿。
#
# 事实源关系：判据对象只有 ci.yml 本体，本文件只**读取**它（与 tests/test_ci_retry_action.py
#   同口径：按 YAML 结构取步骤，不按行号、不按全文正则，步骤挪动或换 job 都不该让锁失效）。
#
# 双向钉（对齐 tests/test_ci_frontend_registration.py 的「清单 ↔ 配置」口径）：
#   正向——每个 pytest job 都必须装 requirements.txt（漏装即红，正是事故一形态）；
#   反向——检测器必须**认得出**已知的 pytest job、且**认不出** setup job（后者只 echo 版本
#         常量字符串 `pytest_version=9.2.0`；认错说明正则退化成子串匹配，正向判据随即失真）。
#
# 变异验证（2026-10-18 实跑，均已当轮还原）：① vbs-behavior-test 改回 `pip install pytest` →
#   正向判据红；② 检测器放宽成裸子串 `pytest` → 反向判据红；③ 摘掉 `libegl1` → Qt 运行库判据红
#   （点名 test / build-verify）；④ 去掉收集闸门的 `--co` → collect-only 判据红。

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, cast

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
CI_FILE = ROOT / ".github" / "workflows" / "ci.yml"

# 独立 token 形态的 pytest：既排除 `pytest_version=9.2.0`（setup job 的 echo，后随 `_`），
# 也排除 `pytest-cov` / `pytest-asyncio`（后随 `-`）——两者都不是「跑/装 pytest」本身。
# 装上 `pytest==9.2.0` 的 typecheck job 会被认出（后随 `=` 不在排除集内），这是有意的：
# 那条 job 也是靠 requirements.txt 兜底的，纳入判定面只会让锁更紧而非更松。
_PYTEST_TOKEN_RE = re.compile(r"(?<![A-Za-z0-9_.\-])pytest(?![A-Za-z0-9_\-])")

# 运行时依赖安装锚点：必须落到 requirements.txt（唯一事实源，见 requirements.txt 文件头）。
# 不认 `pip install .[dev]` 之类旁支——它们不含运行时依赖，替代不了本判据。
_REQUIREMENTS_INSTALL_RE = re.compile(r"pip install\b[^\n|&;]*-r requirements\.txt")

# 已知「真跑 pytest」的 job。用「必须是检测结果的子集」而不是相等：
# 新增 pytest job 属放宽，不该弄红；**减少**（把某条 job 改成不再跑 pytest，或检测器退化）
# 会让覆盖面悄悄缩水，必须拦。
_KNOWN_PYTEST_JOBS = ("test", "concurrency-test", "vbs-behavior-test")

# 检测器精度守卫：这些 job 不得被认成 pytest job。`setup` 是最关键的一格——它只 echo 版本常量
# （`pytest_version=9.2.0`），裸子串匹配会命中它，于是正向判据会被一个从不跑 pytest 的 job 稀释。
_KNOWN_NON_PYTEST_JOBS = ("setup", "static", "deps-audit", "integration-verify", "build-verify")


def _ci_doc() -> dict[str, Any]:
    assert CI_FILE.is_file(), f"缺少 CI 工作流定义：{CI_FILE}"
    doc = yaml.safe_load(CI_FILE.read_text(encoding="utf-8"))
    assert isinstance(doc, dict), "ci.yml 必须解析为映射"
    return cast("dict[str, Any]", doc)


def _jobs() -> dict[str, dict[str, Any]]:
    # 按结构取 jobs。空 jobs 一律显式失败：扫不到东西的绿灯等于锁被掏空还显示通过。
    doc = _ci_doc()
    jobs = doc.get("jobs") or {}
    assert isinstance(jobs, dict), "ci.yml 的 jobs 必须是映射"
    typed = cast("dict[str, dict[str, Any]]", jobs)
    assert typed, "ci.yml 的 jobs 不得为空（解析失败或结构漂移）"
    return typed


def _strip_comment_lines(text: str) -> str:
    # 只保留**会被执行**的行：bash 块里的 `#` 注释同样会出现 pytest 字样（setup job 的常量
    # 步骤就有一整段 `# pytest 同属此类…`），带注释一起判等于把「提到」当成「执行」——
    # 判据随即被一个从不跑 pytest 的 job 稀释。行首（去空白后）为 # 的行一律丢掉。
    kept = [line for line in text.splitlines() if not line.lstrip().startswith("#")]
    return "\n".join(kept)


def _step_texts(job: dict[str, Any]) -> list[str]:
    # 一条 job 的「可判定文本」= 每个 step 的 run 脚本体 + retry 复合动作的 with.command。
    # 必须同时看两处：网络安装统一走 ./.github/actions/retry（AGENTS「CI / workflow 约定」），
    # 只看 run 会漏掉全部经该动作执行的 pip install。
    # 刻意**不**收 step.name / with.label：它们是给人看的文案，写「requirements + pytest」
    # 只是描述，不代表真跑 pytest。
    steps = job.get("steps") or []
    if not isinstance(steps, list):
        # 调用他人 workflow 的 job 没有 steps，跳过而不是抛 AttributeError 掩盖真判据。
        return []
    texts: list[str] = []
    for step in steps:
        if not isinstance(step, dict):
            continue
        run_body = step.get("run")
        if isinstance(run_body, str):
            texts.append(_strip_comment_lines(run_body))
        with_map = step.get("with")
        if isinstance(with_map, dict):
            command = with_map.get("command")
            if isinstance(command, str):
                texts.append(_strip_comment_lines(command))
    return texts


def _pytest_jobs() -> dict[str, list[str]]:
    found: dict[str, list[str]] = {}
    for name, job in _jobs().items():
        texts = _step_texts(job)
        if any(_PYTEST_TOKEN_RE.search(text) for text in texts):
            found[name] = texts
    return found


def test_every_pytest_job_installs_runtime_requirements() -> None:
    found = _pytest_jobs()
    assert found, "未检测到任何 pytest job（ci.yml 结构漂移或检测器失效，不得静默放行）"
    offenders = [name for name, texts in found.items() if not any(_REQUIREMENTS_INSTALL_RE.search(t) for t in texts)]
    assert not offenders, (
        "以下 job 会执行/安装 pytest，却没装 requirements.txt："
        f"{sorted(offenders)}。tests/conftest.py 的 autouse fixture 会 import src 与 i18n"
        "（分别拉起 distro / loguru 等运行时依赖），只装 pytest 会让全部用例在 setup 阶段"
        " ModuleNotFoundError（2026-10-18 vbs-behavior-test 实测形态）"
    )


def test_known_pytest_jobs_are_detected() -> None:
    found = _pytest_jobs()
    missing = [name for name in _KNOWN_PYTEST_JOBS if name not in found]
    assert not missing, f"检测器漏掉了已知 pytest job {missing}（正则或结构解析失效，正向判据随之失真）"


# Qt 运行库锚点：只钉 **libegl1** 这一枚（Qt6Gui 的 dlopen 目标，缺它 `from PySide6.QtGui
# import ...` 立即 ImportError），不逐个枚举 xcb / GL 同族 —— 那会把判据变成「照抄 ci.yml
# 清单」，apt 包换名即假红，而我们真正要锁的是「这份依赖被想过」这件事。
_QT_RUNTIME_LIB_RE = re.compile(r"apt-get install\b[^\n]*libegl1\b")

# 会真的把 Qt 窗口层装起来的 job：test（pytest 会收集到依赖 src/gui_qt 的 Qt 窗口层用例）
# 与 build-verify（打出来的 GUI exe 由 PySide6 窗口层驱动，smoke_gui 起进程即 dlopen 同一组库）。
_QT_JOBS = ("test", "build-verify")


def test_qt_window_layer_jobs_install_qt_runtime_libs() -> None:
    jobs = _jobs()
    offenders: list[str] = []
    for name in _QT_JOBS:
        texts = _step_texts(jobs.get(name) or {})
        if not any(_QT_RUNTIME_LIB_RE.search(text) for text in texts):
            offenders.append(name)
    assert not offenders, (
        f"以下 job 会用到 Qt 窗口层却没有 apt 装 Qt 运行库：{sorted(offenders)}。"
        "PySide6 随 requirements.txt 安装，但 Qt 的 .so 还要 dlopen 系统库（libEGL.so.1 等），"
        "缺一枚时窗口层 import 即以 collection error 中断整轮 pytest（2026-10-18 实测："
        "4337 collected / 2 errors → Interrupted，rc=2，覆盖率与逐模块门禁全部拿不到数据）"
    )


def test_test_job_gates_qt_gui_collection() -> None:
    # 反假绿的第二道防线：Qt 窗口层用例靠 pytest.importorskip 降级，而 ci-summary 分不清
    # skipped 与 passed —— 一旦上面那条 apt 判据之后仍有人把系统库摘掉（换镜像 / 精简步骤），
    # 两个模块会整片 skip 而 rc 仍为 0。collect-only 闸门就是专门关这个洞的，这里钉它必须存在。
    texts = _step_texts(_jobs().get("test") or {})
    gated = [
        text for text in texts if "--co" in text and "test_gui_qt_units.py" in text and "test_gui_qt_window.py" in text
    ]
    assert gated, (
        "test job 缺少 Qt GUI 的 collect-only 闸门（`pytest --co` 点名两个 Qt 测试模块）。"
        "没有它，importorskip 造成的整模块 skip 会以 rc=0 通过，窗口层断言从此静默空转"
        "（判决形态见 ci.yml 的 “Gate Qt GUI tests are collected” 步骤）"
    )


@pytest.mark.parametrize("job_name", _KNOWN_NON_PYTEST_JOBS)
def test_setup_job_is_not_mistaken_for_a_pytest_job(job_name: str) -> None:
    # 反向钉：这些 job 不该被检测器认成 pytest job。setup 是最关键的一格——它只有
    # `echo "pytest_version=9.2.0"` 这类版本常量字符串，裸子串匹配会命中它，
    # 于是「pytest job 必须装 requirements」这条判据会被一个从不跑 pytest 的 job 稀释。
    assert job_name not in _pytest_jobs(), f"{job_name} 不含 pytest 执行/安装，检测器不应命中它"
