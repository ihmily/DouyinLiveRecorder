# WEB 端「按房间切换画质」前端功能（web/app.js）单元测试的 pytest 驱动入口。
# 测试本体为 Node 内置 node:test 编写的 tests/frontend/test_quality_ui.mjs：以 node:vm 沙箱
# 加载 app.js（IIFE 加载期零副作用），用 DOM/fetch 桩触发 DOMContentLoaded 后经真实事件委托
# 链路驱动（tab 点击 → 渲染下拉 → change 委托 → PUT /api/rooms/quality → toast/回拉），
# 零 npm 依赖。此处子进程运行并透传失败输出，保持 pytest 单一测试入口。
# Node 为项目运行时基线（node/ 自动下载、Dockerfile 安装 Node 24 LTS），但开发机可能未装：
# 缺失时 skip 而非 fail，与沙箱环境限制类用例的既有口径一致。
import shutil
import subprocess
from pathlib import Path

import pytest

_FRONTEND_TEST = Path(__file__).parent / "frontend" / "test_quality_ui.mjs"
_NODE_BIN = shutil.which("node")

pytestmark = pytest.mark.skipif(_NODE_BIN is None, reason="Node.js 运行时不可用，跳过前端单元测试")


def test_frontend_quality_ui() -> None:
    # skipif 已保证 node 存在；assert 收窄 Optional 供类型检查（mypy/basedpyright）
    assert _NODE_BIN is not None
    result = subprocess.run(
        [_NODE_BIN, "--test", str(_FRONTEND_TEST)],
        capture_output=True,
        text=True,
        timeout=300,
        cwd=str(_FRONTEND_TEST.parent),
    )
    assert result.returncode == 0, f"前端测试失败（exit {result.returncode}）:\n{result.stdout}\n{result.stderr}"
