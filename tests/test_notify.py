# -*- coding: utf-8 -*-
# 通知模块单测
#
# 覆盖 run_script 的超时保护：用户脚本挂起时必须被强制终止并回收管道，
# 不能让 communicate() 无 timeout 永久占用调用线程。
#
# 备注：项目用 loguru 记录错误，loguru 默认不桥接 stdlib logging，
# 故 caplog 抓不到——测试自带 InMemorySink 捕获消息文本。

import io
import shlex
import sys
import time
from collections.abc import Generator
from pathlib import Path

import pytest
from loguru import logger

# 通知模块的 run_script 通过 import main 读写运行时全局；
# 测试需先把 main 引入，才能加载 src.notify
# [LT-07 2026-10-18] 这条 sys.path 注入只为下面两行**导入期**服务，用完当场摘回：旧形态把仓库根
# 永久留在 sys.path[0] 且从不还原（同会话其它包的模块解析顺序被单方面改写，多个用例各插一次还会累积）。
# 不搬进 fixture：`import main` 就在模块级、收集期即执行，fixture 要等用例开跑才运行。
# 摘回按值 remove 首个同名条目：tests/__init__.py 已登记一条时，移除的是我们插的那条；
# main / src.notify 此后由 sys.modules 兜住，用例内的再次 import 不依赖这条路径。
_REPO_ROOT = str(Path(__file__).resolve().parent.parent)
_PATH_BASELINE = sys.path.count(_REPO_ROOT)  # 注入前的条目数（各调用形态下都实测为 0 或 1）
sys.path.insert(0, _REPO_ROOT)
try:
    import main  # noqa: E402  必须在 src.notify 之前
    import src.notify as notify  # noqa: E402
finally:
    if _REPO_ROOT in sys.path:
        sys.path.remove(_REPO_ROOT)
# LT-07 泄漏判据：「注入 → 导入 → 摘回」三步必须把 sys.path 归还成注入前的条目数。按计数比而不按
# 整表相等——别的库导入期正当注册的搜索路径不该被本文件判红；生产代码零处碰 sys.path，故判据确定。
assert sys.path.count(_REPO_ROOT) == _PATH_BASELINE, "仓库根被永久留在 sys.path：注入未归还，状态泄漏"

# M-30：命令一律用 sys.executable，不写死字面量 `python`——生产 run_script 以 shell=False +
# shlex.split 在 PATH 里查找可执行文件，Linux/CI 镜像常只提供 python3（无 python 软链），旧写法在
# CI 上「正常完成 / 超时」两条用例必失败，本机 Windows 单跑必绿——典型的「本地绿、CI 红」。换绑
# 口径与 tests/test_run_gates.py::test_run_command_rebinds_interpreter_to_current_python 同族。
# 必须 shlex.quote：路径可能含空格，且 run_script 走 shlex.split(posix=True)——单引号内的 Windows
# 反斜杠按字面保留，round-trip 无损。本文件其余两处「可执行文件字面量」刻意不改写：
#   __definitely_not_a_real_binary_42__ 要的正是「PATH 里查不到」⇒ OSError 分支；
#   echo "unterminated 在 shlex.split 阶段就抛 ValueError，永远不会真的起进程。


@pytest.fixture
def short_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    # 把超时压到 1 秒，让测试快速断言「超时后被 kill」而不是等满 300 秒
    monkeypatch.setattr(notify, "_SCRIPT_TIMEOUT_SECONDS", 1.0)


@pytest.fixture
def log_capture() -> Generator[io.StringIO, None, None]:
    # 内存 sink：直接接管 loguru 消息（不依赖 caplog / stdlib logging 桥接），
    # 退出 fixture 时自动 remove 不污染全局 handler
    buf = io.StringIO()
    sink_id = logger.add(buf, format="{message}", level="DEBUG")
    try:
        yield buf
    finally:
        try:
            logger.remove(sink_id)
        except ValueError:
            pass


def test_run_script_normal_completion(capsys: pytest.CaptureFixture[str]) -> None:
    # 正常完成的脚本：stdout 应原样打印到当前 stdout
    notify.run_script(f"{shlex.quote(sys.executable)} -c \"print('hello-from-script')\"")
    captured = capsys.readouterr()
    assert "hello-from-script" in captured.out


def test_run_script_timeout_kills_process(
    short_timeout: None,
    log_capture: io.StringIO,
) -> None:
    # 挂起脚本（sleep 30）必须在 1 秒超时后被 kill，且 log 记超时
    started = time.monotonic()
    notify.run_script(f'{shlex.quote(sys.executable)} -c "import time; time.sleep(30)"')
    elapsed = time.monotonic() - started
    # 超时 1 秒 + 杀树 + 二次 communicate 回收管道；余量由生产常量推导：超时 +
    # _TREE_KILL_TIMEOUT_SECONDS（杀树路径自身的设计预算）+ 2s 调度余量，杀树吃满预算也不误报。
    # 固定的 4.0s 手拍余量已被实测证伪：taskkill.exe 杀一个真实进程稳定 2.5~3.1s，1s + 3s ≈ 4.01s
    # 恰好撞线。进程树与超时分支的逐条锁在 tests/test_notify_script_guard.py，本文件只管
    # 「超时后确实不再占着调用线程」。
    kill_budget = notify._SCRIPT_TIMEOUT_SECONDS + notify._TREE_KILL_TIMEOUT_SECONDS + 2.0
    assert elapsed < kill_budget, f"超时未被强制回收: elapsed={elapsed:.2f}s"
    log_text = log_capture.getvalue()
    assert "执行自定义脚本超时" in log_text


def test_run_script_bad_command_logs_oserror(log_capture: io.StringIO) -> None:
    # 不存在的命令应被 shlex.Popen 触发 OSError 路径（Windows FileNotFoundError / Linux [Errno 2]）
    notify.run_script("__definitely_not_a_real_binary_42__")
    log_text = log_capture.getvalue()
    # 不强求精确匹配 "FileNotFoundError" / "No such file"：跨平台文案差异大
    # 仅要求确实进入 OSError 分支并记录了失败
    assert "执行自定义脚本失败" in log_text


def test_run_script_uses_safe_split_not_shell(log_capture: io.StringIO) -> None:
    # 验证 run_script 不走 shell=True：传入明显会触发 shell 展开的字符串时，
    # 子进程 Popen 收到的应是 list[str]（来自 shlex.split），若 shlex 解析失败应被 except ValueError 接住
    # 这里用一个会被 shlex 报 ValueError 的非闭合引号
    notify.run_script('echo "unterminated')
    log_text = log_capture.getvalue()
    assert "脚本命令解析失败" in log_text
