# tests/frontend/test_regression_gates.mjs 的 pytest 驱动入口。
#
# 该 .mjs 是「组 G 前端回归锁」的用例本体（SEV-2221 / SEV-2227 / SEV-2228 /
# MID-2237 / MID-2240 / MID-2241 / MID-2253 / MIN-2237~2241 等），以 node:vm 沙箱驱动
# web/app.js（IIFE 加载期零副作用），DOM/fetch/定时器桩手工触发事件、经真实事件委托链路断言，
# 零 npm 依赖。按 AGENTS.md「.mjs 真用例 + .py 包装」双文件结构，本包装让整组锁随 test job 的
# 全量 pytest 一起被收集、执行。
#
# 不重复实现子进程驱动：node --test 的「挂死 + GBK 解码」两类坑（MID-64）已在
# tests/test_frontend_quality_ui.py 里沉淀成 _run_node（输出重定向到临时文件、超时回收整棵
# 进程树、一律二进制捕获后显式 UTF-8 解码）与 _parse_node_summary（cwd 取 tests/frontend/）。
# 直接复用避免第二份「改了这份、忘改那份」的子进程硬化代码；上游重构掉这些符号时 import 会立即
# 报错，而不是静默退化成「管道形态挂死 / text=True 崩码页」的老问题。
#
# Node 缺失时整体 skip（环境限制口径，不是失败），与同目录另一前端包装保持一致。
from pathlib import Path

import pytest

from tests.test_frontend_quality_ui import _NODE_BIN, _parse_node_summary, _run_node

_FRONTEND_TEST = Path(__file__).parent / "frontend" / "test_regression_gates.mjs"

pytestmark = pytest.mark.skipif(_NODE_BIN is None, reason="Node.js 运行时不可用，跳过前端回归锁用例")


def test_frontend_regression_gates() -> None:
    # skipif 已保证 node 存在；assert 收窄 Optional 供类型检查（mypy / basedpyright）。
    assert _NODE_BIN is not None
    returncode, stdout, stderr = _run_node(_NODE_BIN, ["--test", str(_FRONTEND_TEST)])
    detail = f"前端回归锁用例失败（exit {returncode}）:\n{stdout}\n{stderr}"
    assert returncode is not None, detail + "\n（node --test 超时未退出，进程树已尝试回收）"
    assert returncode == 0, detail

    # 「跑到了用例、且用例真的有断言」必须显式核对：node --test 在**收集到 0 个用例**时
    # 同样退出 0（例如 .mjs 被误改名 / 整个 test() 块被删），只看 returncode 就是假绿。
    # 故解析汇总行，要求 fail == 0 且 pass > 0——与 test_frontend_quality_ui 完全同口径。
    summary = _parse_node_summary(stdout)
    assert {"tests", "pass", "fail"} <= set(summary), f"未能从 node 输出解析到汇总行:\n{stdout}\n{stderr}"
    assert summary["fail"] == 0, detail
    assert summary["pass"] > 0, f"node --test 收集到 0 个用例（包装层未真正驱动 .mjs）:\n{stdout}"
    assert summary["tests"] >= summary["pass"], f"汇总计数自相矛盾: {summary}"
