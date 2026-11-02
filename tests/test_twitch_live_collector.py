# -*- coding: utf-8 -*-
# Twitch 真实房间端到端验证:channel → collector(TwitchDanmaku) → SRT 产出。
#
# 用法:python tests/test_twitch_live_collector.py [频道名或URL] [秒数]
# 代理:默认跟随系统代理(getproxies),可选第三个参数显式指定,如 http://127.0.0.1:7890
#
# 本文件是「双模式」脚本：`python 本文件.py <频道> <秒数>` 手动跑真机验证，同时文件名匹配
# pyproject 的 python_files=["test_*.py"]，因此**也会被 pytest 收集**。(CODE_REVIEW_2026-09-29_2)
# 的事故形态正是「执行体全部落在模块级」：收集期即连真实 Twitch IRC、time.sleep(SECONDS)、
# 清空 tests/_out_live，并在失败路径 sys.exit(1) 直接终止整个收集会话
# （实测 `pytest 本文件 --collect-only -q` 耗时 20.55 秒、no tests collected、退出码 5）。
# 其余 4 个兄弟脚本（bili/douyin/douyu/huya_live_collector）都有 `if __name__ == "__main__":`
# 守卫，本文件曾是唯一漏网者；守卫结构现由文件末尾的 test_twitch_script_keeps_main_guard 锁住。

import ast
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.collector import DanmakuCollector
from src.platforms.twitch import TwitchDanmaku

# Twitch 弹幕走 IRC 网关(经 WebSocket 桥接),必须连真实在线频道;拼错或离线会导致
# 服务端直接断开,因此 channel 规范化得空串时立即 exit 1,不进入后续连接流程。
RAW = sys.argv[1] if len(sys.argv) > 1 else "forsen"
# 双模式参数守卫（`not startswith("-")` 一条与其余 4 个 live_collector 逐字同构）：pytest 运行时的
# sys.argv[2] 可能是 `-q`/`--collect-only` 等选项，缺该守卫会在**收集期**执行 int('-q') 抛
# ValueError——表现为「一跑 pytest 就崩」且报错位置离根因很远。
# 在此之上多一道 isdigit 回落（本文件独有的加固）：`pytest tests/test_twitch_live_collector.py
# tests/test_x.py ...` 这种「一次点多个文件」的跑法下，sys.argv[2] 是**下一个测试文件的路径**，
# int() 同样抛 ValueError 并让本模块的收集直接 ERROR（2026-09-29 实测复现）。兄弟脚本仍有此坑，
# 建议同批跟进；真机调用 `python 本文件.py forsen 20` 的语义完全不变。
_SECONDS_RAW = sys.argv[2] if len(sys.argv) > 2 and not sys.argv[2].startswith("-") else ""
SECONDS = int(_SECONDS_RAW) if _SECONDS_RAW.isdigit() else 20
PROXY = sys.argv[3] if len(sys.argv) > 3 else None


def main() -> None:
    # 从参数规范化频道名：去掉查询串/尾斜杠、取路径末段、转小写、剥离开头 #（兼容
    # 直接传 "forsen"、完整 URL 或 "#channel" 三种输入形态）。
    channel = RAW.split("?")[0].rstrip("/").split("/")[-1].lower().lstrip("#")
    if not channel:
        print("[FAIL] 无法从参数提取频道名")
        print(
            f'VERIFICATION_RESULT: {json.dumps({"platform": "twitch", "script": "test_twitch_live_collector.py", "url": RAW, "status": "FAIL", "messages": 0})}'
        )
        sys.exit(1)

    # 代理策略:默认 None 即跟随系统代理(getproxies 全局生效),仅显式传第三参才注入;
    # Twitch 国内常需代理,代理失效表现为连接超时而非「弹幕为空」。
    danmaku_args = {"channel": channel}
    if PROXY:
        danmaku_args["proxy"] = PROXY
    print(f"[OK] danmaku_args: {danmaku_args}")

    # tests/_out_live 是 5 个 live_collector 手跑真机时的产物目录（由 tests/conftest.py 在会话
    # 退出时统一清理），只在**真机运行**时清空重建——不得移回导入期 makedirs，否则又变成
    # 收集期副作用。
    base_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_out_live")
    os.makedirs(base_dir, exist_ok=True)
    # R7④：清理收窄到本脚本自己的产物前缀，并先判是文件再删。
    # 无差别删掉目录里每一项会把并行运行的其它平台验证产物一起删（真机验证常多平台同开），
    # 且目录里混进子目录时 os.remove 直接抛 IsADirectoryError/PermissionError。
    for f in os.listdir(base_dir):
        if f.startswith("Twitch弹幕验证"):
            stale = os.path.join(base_dir, f)
            # 子目录一律跳过，交由 tests/conftest.py 的会话收尾统一 rmtree。
            if os.path.isfile(stale):
                os.remove(stale)

    # 文件名含频道名,便于并行多次运行时区分不同频道的 SRT 产物。
    base = os.path.join(base_dir, f"Twitch弹幕验证_{channel}")
    collector = DanmakuCollector(
        danmaku_cls=TwitchDanmaku,
        danmaku_args=danmaku_args,
        base_filename=base,
        segment_seconds=None,
    )
    collector.start()
    print(f"[OK] collector 已启动,监听 {SECONDS}s (房间 #{channel})...")
    # SECONDS=20 覆盖 Twitch IRC 进房(JOIN #channel)+ 订阅能力协商(cap reqs/NAMES)往返;
    # 握手轻量但小于此可能收不到首批消息。stop() 在计数后调用以触发 SRT 落盘。
    time.sleep(SECONDS)
    count = collector.message_count
    collector.stop()
    print(f"[OK] 收到弹幕消息数: {count}")

    srt_file = base + ".srt"
    if os.path.isfile(srt_file):
        with open(srt_file, encoding="utf-8") as fh:
            content = fh.read()
        print("=== SRT 内容(前 20 行) ===")
        print("\n".join(content.splitlines()[:20]))
        # SRT 已生成而 count==0 仅表示静默频道(或刚 JOIN 尚无消息),连接正常;
        # SRT 未生成才是真正的连接/握手失败,二者必须区分。
        if count > 0:
            print("[PASS] 端到端:Twitch 真实弹幕已写入 SRT")
        else:
            print("[WARN] 当前房间该时段无弹幕(连接可能正常)")
    else:
        print(f"[FAIL] SRT 未生成: {srt_file}")
        print(
            f'VERIFICATION_RESULT: {json.dumps({"platform": "twitch", "script": "test_twitch_live_collector.py", "url": f"twitch.tv/{channel}", "status": "FAIL", "messages": 0})}'
        )
        sys.exit(1)
    _srt_sz = os.path.getsize(srt_file)
    print(
        f'VERIFICATION_RESULT: {json.dumps({"platform": "twitch", "script": "test_twitch_live_collector.py", "url": f"twitch.tv/{channel}", "status": "PASS" if count > 0 else "WARN", "messages": count, "srt_bytes": _srt_sz})}'
    )


if __name__ == "__main__":
    main()


# ---- 该回归锁（CODE_REVIEW_2026-09-29_2）----
# 结构锁而非运行时锁：本用例全程离线（只读自身源码 + ast.parse），因此能在 CI（ubuntu、无外网
# 无活房间）常驻；而「收集期不得连真机」这件事只能靠**结构**来证明——运行时 reload 判据反而要
# 先把真机依赖打进桩，等于在用例里重新实现一遍被测流程。
# 判据口径：模块级语句只允许「导入 / 常量赋值（右值不得是裸调用）/ 函数定义 / sys.path 引导 /
# __main__ 守卫」，其余任何模块级语句（函数调用、循环、with、try、raise…）都属收集期副作用形态。
# [历史注] 起初只锁本文件、称跨 5 个 live_collector 的统一门禁「尚未获批准」；该说法其后
# 证伪——统一门禁已获批并落地为 tests/test_test_hygiene.py 的 R7（①守卫 ②模块级零副作用
# ③argv 数值守卫 ④清理带前缀过滤与类型判定，逐文件参数化覆盖全部 5 个脚本，新增第 6 个自动纳入）。
# 本文件的文件内结构锁保留作该原始见证，与 R7 口径一致（②的「只看最外层节点」判据即由本锁
# 先立、R7 逐字沿用），不属重复实现需要清理的那一类。
_ALLOWED_MODULE_NODES = (
    ast.Import,
    ast.ImportFrom,
    ast.Assign,
    ast.AnnAssign,
    ast.FunctionDef,
    ast.AsyncFunctionDef,
    ast.ClassDef,
)


def _dotted_name(node: ast.AST) -> str | None:
    # a.b.c -> "a.b.c"；下标/属性链之外的复杂表达式返回 None（本文件只用于识别 sys.path.insert）
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = _dotted_name(node.value)
        return None if base is None else base + "." + node.attr
    return None


def _is_main_guard(node: ast.If) -> bool:
    # 认 `if __name__ == "__main__":`（及左右互换的写法）；其余 if 一律不算守卫
    test = node.test
    if not isinstance(test, ast.Compare) or not any(isinstance(op, ast.Eq) for op in test.ops):
        return False
    sides = [test.left, *test.comparators]
    names = {_dotted_name(side) for side in sides}
    literals = {side.value for side in sides if isinstance(side, ast.Constant) and isinstance(side.value, str)}
    return "__name__" in names and "__main__" in literals


def _module_level_offenders(tree: ast.Module) -> list[str]:
    # 返回收集期会被执行的模块级语句清单（"第N行 节点类型"），空列表 = 结构合规
    offenders: list[str] = []
    for node in tree.body:
        if isinstance(node, ast.Assign | ast.AnnAssign):
            # 模块级赋值合规，但**右值不得是裸调用**：`X = collector_start()` 对收集期的危害与
            # 直接写 `collector_start()` 完全等价，只按节点类型放行 Assign 会留下这个洞。
            # 条件表达式里嵌套的 int(...)/str.isdigit() 属纯取值调用，判据只看最外层节点、不拦。
            if isinstance(node.value, ast.Call):
                offenders.append(f"第{node.lineno}行 Assign(Call)")
            continue
        if isinstance(node, _ALLOWED_MODULE_NODES):
            continue
        if (
            isinstance(node, ast.Expr)
            and isinstance(node.value, ast.Call)
            and _dotted_name(node.value.func) == "sys.path.insert"
        ):
            continue
        if isinstance(node, ast.If) and _is_main_guard(node):
            continue
        offenders.append(f"第{node.lineno}行 {type(node).__name__}")
    return offenders


def test_twitch_script_keeps_main_guard() -> None:
    # 变异见证：把执行体摊回模块级、或删掉 __main__ 守卫，本用例必须变红。
    tree = ast.parse(Path(__file__).resolve().read_text(encoding="utf-8"), filename=str(__file__))
    offenders = _module_level_offenders(tree)
    assert not offenders, f"模块级存在收集期会执行的语句（S-2 事故形态），须移入 main(): {offenders}"

    guards = [node for node in tree.body if isinstance(node, ast.If) and _is_main_guard(node)]
    assert guards, '缺少 `if __name__ == "__main__":` 守卫——pytest 收集期将直接执行真机流程'
    guard_calls = [
        _dotted_name(inner.func)
        for inner in ast.walk(guards[0])
        if isinstance(inner, ast.Call) and isinstance(inner.func, (ast.Name, ast.Attribute))
    ]
    assert "main" in guard_calls, f"__main__ 守卫未调用 main(): {guard_calls}"
