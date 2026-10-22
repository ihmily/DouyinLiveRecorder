# tests/frontend/test_auth_reauth.mjs 的 pytest 驱动入口（与 test_frontend_regression_gates.py 同构）。
#
# 被驱动的 .mjs 是 CODE_REVIEW_2026-09-29_2 的 M-22/M-26 前端行为锁：node:vm 沙箱驱动真实
# web/app.js，走真实事件链路（tab → GET /api/config → 改 input → 保存 → confirm → 口令窗 → PUT），
# 断言真实请求体与 toast 文案，零 npm 依赖。包装把它接进 pytest / CI 回路（AGENTS「.mjs 真用例
# + .py 包装」双文件结构），否则只在手跑 node 时执行、CI 静默漏跑。
#
# 子进程驱动复用 tests/test_frontend_quality_ui.py 的 _run_node / _parse_node_summary
# （MID-64 的管道挂死与 GBK 解码坑已在那侧沉淀），不复制第二份。Node 缺失时整体 skip
# （环境限制，不是失败），CI 侧由 ci.yml「Gate frontend tests not skipped」按 node-id 点名兜住。
# 新增前端入口须同步补进那条列表。
from pathlib import Path

import pytest

from tests.test_frontend_quality_ui import _NODE_BIN, _parse_node_summary, _run_node

_FRONTEND_TEST = Path(__file__).parent / "test_auth_reauth.mjs"

pytestmark = pytest.mark.skipif(_NODE_BIN is None, reason="Node.js 运行时不可用，跳过认证复验口令前端用例")


def test_auth_reauth() -> None:
    # skipif 已保证 node 存在；assert 收窄 Optional 供类型检查（mypy / basedpyright）。
    assert _NODE_BIN is not None
    returncode, stdout, stderr = _run_node(_NODE_BIN, ["--test", str(_FRONTEND_TEST)])
    detail = f"认证复验口令前端用例失败（exit {returncode}）:\n{stdout}\n{stderr}"
    assert returncode is not None, detail + "\n（node --test 超时未退出，进程树已尝试回收）"
    assert returncode == 0, detail

    # 「跑到了用例、且用例真的有断言」必须显式核对：node --test 在**收集到 0 个用例**时同样退出 0
    # （例如 .mjs 被误改名 / 整个 test() 块被删），只看 returncode 就是假绿。
    summary = _parse_node_summary(stdout)
    assert {"tests", "pass", "fail"} <= set(summary), f"未能从 node 输出解析到汇总行:\n{stdout}\n{stderr}"
    assert summary["fail"] == 0, detail
    assert summary["pass"] > 0, f"node --test 收集到 0 个用例（包装层未真正驱动 .mjs）:\n{stdout}"
    # 本文件锁的是「口令随哪些请求下发」这类逐请求断言，用例数一旦掉下去就是整段被删：
    # 按既有 13 条设下限（新增用例不必同步本行，删用例才会红）。
    assert summary["pass"] >= 13, f"认证复验用例数异常偏少（{summary['pass']}），疑似整段丢失:\n{stdout}"
    assert summary["tests"] >= summary["pass"], f"汇总计数自相矛盾: {summary}"
