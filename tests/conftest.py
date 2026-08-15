# Pytest configuration and fixtures.

import os


def pytest_configure(config) -> None:
    # 测试环境跳过 src 包导入期的运行时检查（node 子进程检查/自动安装），
    # 避免受限环境下子进程管道偶发失败导致收集崩溃，也使测试导入确定性。
    os.environ.setdefault("DOUYIN_SKIP_RUNTIME_CHECK", "1")
    # 禁用 loguru 异步入队：enqueue 依赖 multiprocessing 命名管道，受限环境可能阻塞/失败
    os.environ.setdefault("DOUYIN_LOG_NO_ENQUEUE", "1")
