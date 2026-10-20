# tests/frontend/test_motion.mjs 的 pytest 驱动入口（M-28，CODE_REVIEW_2026-09-29_2）。
#
# 被驱动的 .mjs 锁 web/motion.js 的 5 条不变量：粒子数边界与移动端/低核数减半、
# reduced-motion 不建 canvas、正常模式单 rAF 循环、destroy() 的完整清理、
# 入场元素加 reveal / is-revealed。
#
# 为什么需要包装：`node --test <文件>` 只跑被点名的文件、不会发现同级其他 .mjs，而 CI 按
# node-id 点名前端入口；没有这条包装，动效回归锁在 pytest 全量与 CI 里都不会执行。包进
# pytest 与 ci.yml 的 node 清单两条回路，缺一条就会退回「游离门禁」。
#
# 子进程驱动复用 tests/test_frontend_quality_ui.py 的 _run_node / _parse_node_summary
# （MID-64 的管道挂死与 GBK 解码坑已在那侧沉淀成硬化代码，不复制第二份）。Node 缺失时
# 整体 skip（环境限制，不是失败），由 ci.yml 的「有 skip 即红」判据兜住这种静默消失（MID-2264）。
from pathlib import Path

import pytest

from tests.test_frontend_quality_ui import _NODE_BIN, _parse_node_summary, _run_node

_FRONTEND_TEST = Path(__file__).parent / "test_motion.mjs"

# 用例条数下限（M-28）：node --test 收集到 0 条也退出 0，只看 returncode 就是假绿。取下限而非
# 等号：新增不变量不必改这里，删掉既有用例则立刻变红。当前 .mjs 实跑 5 条。
_EXPECTED_MIN_PASS = 5

pytestmark = pytest.mark.skipif(_NODE_BIN is None, reason="Node.js 运行时不可用，跳过前端动效层用例")


def test_motion_frontend() -> None:
    # skipif 已保证 node 存在；assert 收窄 Optional 供类型检查（mypy / basedpyright）。
    assert _NODE_BIN is not None
    returncode, stdout, stderr = _run_node(_NODE_BIN, ["--test", str(_FRONTEND_TEST)])
    detail = f"前端动效层用例失败（exit {returncode}）:\n{stdout}\n{stderr}"
    assert returncode is not None, detail + "\n（node --test 超时未退出，进程树已尝试回收）"
    assert returncode == 0, detail

    # 「跑到了用例、且用例真的有断言」必须显式核对，口径与另两条前端包装完全一致。
    summary = _parse_node_summary(stdout)
    assert {"tests", "pass", "fail"} <= set(summary), f"未能从 node 输出解析到汇总行:\n{stdout}\n{stderr}"
    assert summary["fail"] == 0, detail
    # skipped 也要判：node 侧 test(..., {skip: true}) 既不红也不绿，是 M-2264 同族的静默消失形态。
    assert summary.get("skipped", 0) == 0, f"存在被跳过的动效用例（降级/清理锁未执行）:\n{stdout}"
    assert summary["pass"] >= _EXPECTED_MIN_PASS, (
        f"node --test 执行的用例数低于下限 {_EXPECTED_MIN_PASS}（包装层未真正驱动 .mjs，"
        f"或 motion 不变量用例被删）: {summary}\n{stdout}"
    )
    assert summary["tests"] >= summary["pass"], f"汇总计数自相矛盾: {summary}"
