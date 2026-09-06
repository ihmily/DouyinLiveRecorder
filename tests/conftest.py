# Pytest configuration and fixtures.

import os
import shutil
from typing import Any

import pytest

_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
# 测试运行期产生的临时输出目录（SRT 落盘等），会话结束后统一清理，避免残留
_TEST_OUT_DIRS = (
    os.path.join(_TESTS_DIR, "_out_live"),
    os.path.join(_TESTS_DIR, "_out_e2e"),
)


def pytest_configure(config: Any) -> None:
    # 测试环境跳过 src 包导入期的运行时检查（node 子进程检查/自动安装），
    # 避免受限环境下子进程管道偶发失败导致收集崩溃，也使测试导入确定性。
    os.environ.setdefault("DOUYIN_SKIP_RUNTIME_CHECK", "1")
    # 禁用 loguru 异步入队：enqueue 依赖 multiprocessing 命名管道，受限环境可能阻塞/失败
    os.environ.setdefault("DOUYIN_LOG_NO_ENQUEUE", "1")
    # 测试进程导入 main 会注册日志归档 atexit；pytest 退出并非「停止录制」事件，
    # 禁用归档以免改名开发者工作副本里的真实 logs/ 日志（归档专项用例内自行 delenv）
    os.environ.setdefault("DOUYIN_DISABLE_LOG_ARCHIVE", "1")


@pytest.fixture(autouse=True)
def _hermetic_danmaku_hub(monkeypatch: pytest.MonkeyPatch) -> None:
    # 弹幕监控枢纽替换为无文件输出的隔离实例：任何经 DanmakuCollector 上报的测试
    # 都不会写真实 logs/danmaku_monitor.jsonl，保持测试与仓库目录互不污染。
    import src.danmaku_monitor as dm

    monkeypatch.setattr(dm, "_hub", dm.DanmakuMonitorHub(log_path=None))


def pytest_unconfigure(config: Any) -> None:
    # 会话结束（含 pytest 收集失败/中断退出）后清理测试输出目录，确保不残留临时文件；
    # ignore_errors=True：目录不存在或 Windows 下偶发句柄占用（杀毒/索引扫描）时静默跳过，
    # 清理失败不应让 pytest 以异常退出码结束。两个目录已在 .gitignore，残留亦不污染仓库。
    for out_dir in _TEST_OUT_DIRS:
        shutil.rmtree(out_dir, ignore_errors=True)
