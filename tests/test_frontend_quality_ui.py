# WEB 端「按房间切换画质」前端功能（web/app.js）单元测试的 pytest 驱动入口。
# 测试本体为 Node 内置 node:test 编写的 tests/frontend/test_quality_ui.mjs：以 node:vm 沙箱
# 加载 app.js（IIFE 加载期零副作用），用 DOM/fetch 桩手工触发事件、经真实事件委托
# 链路驱动（tab 点击 → 渲染下拉 → change 委托 → PUT /api/rooms/quality → toast/回拉），
# 零 npm 依赖。此处子进程运行并透传失败输出，保持 pytest 单一测试入口。
# Node 为项目运行时基线（node/ 自动下载、Dockerfile 安装 Node 24 LTS），但开发机可能未装：
# 缺失时 skip 而非 fail，与沙箱环境限制类用例的既有口径一致。
#
# 子进程形态的两条硬约束（MID-64，2026-09-20 实测挂死）：
#   ① 输出重定向到临时文件 + Popen/wait，不用管道：node --test 会派生 worker 子进程，超时只杀
#      直接子进程，run() 内补跑的 communicate() 仍被孙进程持有的写端阻塞，timeout 根本不是上界。
#      没有管道就没有可被孙进程挂住的读端，wait(timeout=) 才是真上界。
#   ② 一律二进制捕获后显式按 UTF-8 解码，不用 text=True：text 走 locale 编码（中文 Windows 为 GBK），
#      node 报告里的 UTF-8 字符会让 reader 线程抛 UnicodeDecodeError（PytestUnhandledThreadExceptionWarning，违反本仓「0 警告」口径）。
# 超时后仍须回收整棵进程树（Windows 无 killpg → taskkill /F /T；POSIX 用进程组），否则孤儿 node worker
# 长期占着输出文件与连接。这两条性质由 test_node_test_timeout_bounds_wait_and_reaps_tree 锁住。
#
# 本文件必须能在 `pytest tests/test_frontend_quality_ui.py` 独立运行下全绿，不得依赖同会话内
# 其他用例先把控制台码页切成 UTF-8（main.py 的 SetConsoleOutputCP(65001) 曾让「全量绿、单跑红」）。
# 全部进程检查调用点由文件末尾三条回归锁覆盖：GBK 载荷 / 源码级禁 text=True / 真实进程往返。
import ast
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import types
from pathlib import Path
from typing import Any

import pytest

_FRONTEND_TEST = Path(__file__).parent / "frontend" / "test_quality_ui.mjs"
_NODE_BIN = shutil.which("node")

# 9 个用例离线跑完实测 133ms，300s 上限只为兜住「CI 冷启动下载 Node」这类极端情形。
_TIMEOUT_SECONDS = 300.0
# 杀掉进程树之后再给直接子进程的收尾宽限（含 Windows 上 taskkill 自身的调用超时）。
_KILL_GRACE_SECONDS = 15.0

pytestmark = pytest.mark.skipif(_NODE_BIN is None, reason="Node.js 运行时不可用，跳过前端单元测试")


def _popen_session_kwargs() -> dict[str, Any]:
    # 让子进程自成一组，超时后才能整棵树回收；Windows 没有 setsid，等价手段是
    # CREATE_NEW_PROCESS_GROUP（回收走 taskkill /T，见 _kill_process_tree）。
    if sys.platform == "win32":  # 平台门控一律用 sys.platform 字面量（mypy 跨平台门禁要求）
        return {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
    return {"start_new_session": True}


def _kill_process_tree(proc: "subprocess.Popen[Any]") -> None:
    # 回收 node --test 及其 worker 孙进程。整棵树杀不掉时只忽略不抛错——
    # 用例此时已经判定失败，收尾异常会掩盖真正的断言输出。
    if sys.platform == "win32":
        try:
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=_KILL_GRACE_SECONDS,
                check=False,
            )
        except OSError, subprocess.SubprocessError:
            pass
    else:
        try:
            # 9 = SIGKILL：刻意写字面量而不是 signal.SIGKILL——该符号在 Windows typeshed 中不存在，
            # 引用它会让本仓 mypy（Linux CI）与 basedpyright（Windows 本地）双平台门禁不对称。
            os.killpg(os.getpgid(proc.pid), 9)
        except OSError:
            pass
    try:
        proc.kill()
    except OSError:
        pass


def _run_node(node_bin: str, args: list[str], timeout: float = _TIMEOUT_SECONDS) -> tuple[int | None, str, str]:
    # 返回 (退出码, stdout, stderr)；退出码为 None 表示「超时且连杀都收不回」。
    # 输出走临时文件而不是管道，理由见模块头 MID-64 第 ① 点。
    # ignore_cleanup_errors：Windows 下孙进程会继承被重定向的文件句柄，worker 若比直接子进程
    # 活得久，整目录删除必抛 PermissionError（实测 WinError 32）——那是收尾噪声而非用例结论，
    # 临时目录位于 %TEMP%/tmp，由系统回收，不值得为此挂掉用例。
    with tempfile.TemporaryDirectory(prefix="dlr-node-test-", ignore_cleanup_errors=True) as tmpdir:
        out_path = Path(tmpdir) / "stdout.txt"
        err_path = Path(tmpdir) / "stderr.txt"
        returncode: int | None
        with out_path.open("wb") as out_fh, err_path.open("wb") as err_fh:
            proc = subprocess.Popen(
                [node_bin, *args],
                stdin=subprocess.DEVNULL,
                stdout=out_fh,
                stderr=err_fh,
                cwd=str(_FRONTEND_TEST.parent),
                **_popen_session_kwargs(),
            )
            try:
                returncode = proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                _kill_process_tree(proc)
                try:
                    returncode = proc.wait(timeout=_KILL_GRACE_SECONDS)
                except subprocess.TimeoutExpired:
                    returncode = None
        stdout = out_path.read_text(encoding="utf-8", errors="replace")
        stderr = err_path.read_text(encoding="utf-8", errors="replace")
        return returncode, stdout, stderr


# node --test 的汇总行：非 TTY 下是 spec 报告器的「ℹ pass 27」，TTY/旧版本为 TAP 的「# pass 27」。
# 两种形态都要认，否则换 node 版本就会「解析不到汇总 → 用例红」，而那与前端质量毫无关系。
_NODE_SUMMARY_RE = re.compile(r"^\s*(?:ℹ|#)\s*(tests|pass|fail|cancelled|skipped)\s+(\d+)\s*$", re.MULTILINE)


def _parse_node_summary(text: str) -> dict[str, int]:
    # 从 node 输出里切出计数汇总（缺失的键不填 0，交由调用方判断「没解析到」）
    return {name: int(value) for name, value in _NODE_SUMMARY_RE.findall(text)}


def _pid_alive(pid: int) -> bool:
    # 跨平台存活判定。Windows 上不能用 os.kill(pid, 0)——CPython 在 nt 下会把它翻译成
    # TerminateProcess(handle, 0)，即「杀掉它」而不是「探一下」。
    #
    # 为什么按**字节**判定而不是 text=True 解码（MID-64 ② 的补集，实测）：
    # 中文 Windows 上 tasklist 对「无匹配任务」输出 GBK 消息（首字节 b'\xd0\xc5\xcf\xa2'），
    # 而门禁口径要求 PYTHONUTF8=1 → UTF-8 模式下 text=True 按 utf-8 解码该字节流，subprocess 的
    # reader 线程直接抛 UnicodeDecodeError，communicate() 返回 stdout=None，`str(pid) in None` 即
    # TypeError，并额外产生一条 PytestUnhandledThreadExceptionWarning（违反本仓「0 警告」）。
    # 该缺陷只在单独跑本文件时显现：全量跑时 main.py 的模块级 SetConsoleOutputCP(65001) 已把码页
    # 切成 UTF-8，tasklist 改吐 UTF-8 而侥幸可解（即「全量绿、单跑红」）。字节包含判定与码页
    # 彻底解耦：PID 出现在 tasklist 表格里 ⟺ 进程存活，与消息语言无关。
    if sys.platform == "win32":
        probe = subprocess.run(
            ["tasklist", "/FI", "PID eq %d" % pid, "/NH"],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            timeout=30,
            check=False,
        )
        return str(pid).encode("ascii") in probe.stdout
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def test_frontend_quality_ui() -> None:
    # skipif 已保证 node 存在；assert 收窄 Optional 供类型检查（mypy/basedpyright）
    assert _NODE_BIN is not None
    returncode, stdout, stderr = _run_node(_NODE_BIN, ["--test", str(_FRONTEND_TEST)])
    detail = f"前端测试失败（exit {returncode}）:\n{stdout}\n{stderr}"
    assert returncode is not None, detail + "\n（node --test 超时未退出，进程树已尝试回收）"
    assert returncode == 0, detail

    # 「跑到了用例、且用例真的有断言」必须显式核对：node --test 在**收集到 0 个用例**时
    # 同样退出 0（例如 .mjs 被误改名/整个 test() 块被删），只看 returncode 就是假绿。
    # 故解析汇总行，要求 pass > 0 且 fail == 0。
    summary = _parse_node_summary(stdout)
    assert {"tests", "pass", "fail"} <= set(summary), f"未能从 node 输出解析到汇总行:\n{stdout}\n{stderr}"
    assert summary["fail"] == 0, detail
    assert summary["pass"] > 0, f"node --test 收集到 0 个用例（包装层未真正驱动 .mjs）:\n{stdout}"
    assert summary["tests"] >= summary["pass"], f"汇总计数自相矛盾: {summary}"


# 挂死的 node 子进程 + 两个 25s 的孙进程：一个 stdio 继承、一个 ignore。
# **继承 stdio 的那只**才是 MID-64 的真实形态——node --test 的 worker 会继承父进程的
# stdout/stderr；旧写法把它们接到管道上，超时只杀直接子进程，随后的收尾读取仍会等
# 孙进程持有的写端关闭。新写法把输出重定向到临时文件，根本没有管道可读，
# 所以 wait(timeout=) 是真上界（test_node_test_timeout_bounds_wait_and_reaps_tree 逐条断言）。
_HANG_JS = (
    "const {spawn} = require('node:child_process');"
    "const a = spawn(process.execPath, ['-e', 'setTimeout(()=>{}, 25000)'], {stdio: 'ignore'});"
    "const b = spawn(process.execPath, ['-e', 'setTimeout(()=>{}, 25000)'], {stdio: 'inherit'});"
    "console.log('GCHILD ' + a.pid);"
    "console.log('GCHILD ' + b.pid);"
    "setTimeout(()=>{}, 25000);"
)


def test_node_test_timeout_bounds_wait_and_reaps_tree() -> None:
    # 回归锁（MID-64）：① timeout 必须是真上界；② 超时必须杀整棵进程树
    # （含继承 stdio 的 worker 孙进程，否则它继续持有输出句柄）。
    assert _NODE_BIN is not None
    started = time.monotonic()
    returncode, stdout, _stderr = _run_node(_NODE_BIN, ["-e", _HANG_JS], timeout=5.0)
    elapsed = time.monotonic() - started

    gchild_pids = [int(line.split()[1]) for line in stdout.splitlines() if line.startswith("GCHILD ")]
    assert len(gchild_pids) == 2, f"孙进程未按预期启动（拿到 {gchild_pids}），用例前提失效:\n{stdout}"

    # 上界：5s 等待 + 15s 收尾宽限，留一倍余量；旧形态要等满孙进程的存活时间。
    assert elapsed < 60.0, f"timeout 未能兜住等待：耗时 {elapsed:.1f}s（旧形态即挂死在此）"
    assert returncode is not None, "超时后连进程树都收不回，说明杀进程组的路径失效"
    time.sleep(0.5)  # 等 taskkill/SIGKILL 在系统层面落地
    for pid in gchild_pids:
        assert not _pid_alive(pid), f"孙进程 {pid} 未被回收：只杀了直接子进程（MID-64 原症状）"


# ---------------------------------------------------------------------------
# _pid_alive 回归锁（MID-64 ② 的补集）：进程存活检测必须与码页/语言解耦。
# 三条一起用，缺一不可：
#   · test_pid_alive_survives_gbk_tasklist_output —— 把 tasklist 载荷钉成事故里的 GBK 字节，
#     与宿主当前码页无关（全量跑时码页已被 main 切成 UTF-8，只跑真进程反而测不到红点）；
#   · test_pid_alive_roundtrip_with_real_processes —— 不打桩，证明判定逻辑本身生效；
#   · test_no_subprocess_call_in_this_module_decodes_output —— 源码级锁，覆盖本文件全部
#     子进程调用点（_pid_alive 的存活探针 + _kill_process_tree 的 taskkill + _run_node 的 Popen），
#     防止有人「顺手加个 text=True」把三类形态一起退回。

# 实测抓取自中文 Windows 上 `tasklist /FI "PID eq <已退出的 pid>" /NH` 的原始字节
# （GBK 的「信息: 没有运行的任务匹配指定标准。」，正是让 text=True 崩掉的载荷）。
# 刻意写死字节而不是 "…".encode("gbk")：常量本身即事故证据，且不得随宿主码页/系统语言漂移。
_TASKLIST_NO_MATCH_GBK = (
    b"\xd0\xc5\xcf\xa2: \xc3\xbb\xd3\xd0\xd4\xcb\xd0\xd0\xb5\xc4\xc8\xce\xce\xf1"
    b"\xc6\xa5\xc5\xe4\xd6\xb8\xb6\xa8\xb1\xea\xd7\xbc\xa1\xa3\r\n"
)


def _tasklist_table_row(pid: int) -> bytes:
    # 命中进程时的表格行（/NH 无表头、内容全 ASCII）——旧写法对这条能正常解码，
    # 于是「判存活」从来没暴露问题，只有「进程已退出」那条本地化消息会炸。
    return f"node.exe                      {pid} Console                    1      9,132 K\r\n".encode("ascii")


def _stub_tasklist(monkeypatch: pytest.MonkeyPatch, payload: bytes) -> list[Any]:
    # 只替换**本模块的全局名** subprocess（SimpleNamespace 副本），不改 stdlib 模块本体：
    # 与 AGENTS.md「patch main 的 subprocess 须换全局引用」同源——改模块本体会波及同进程
    # 其他持有者（本文件里 _run_node/_kill_process_tree 与 harness 守护线程共用一个 subprocess）。
    seen: list[Any] = []

    def fake_run(*args: Any, **kwargs: Any) -> types.SimpleNamespace:
        # 转发型桩的 *args/**kwargs 注解统一 Any（写成 object 只有 basedpyright 报错）
        seen.append((args, kwargs))
        return types.SimpleNamespace(stdout=payload, stderr=b"", returncode=0)

    monkeypatch.setattr(
        sys.modules[__name__], "subprocess", types.SimpleNamespace(run=fake_run, DEVNULL=subprocess.DEVNULL)
    )
    return seen


@pytest.mark.skipif(sys.platform != "win32", reason="tasklist 存活探针分支仅存在于 Windows")
def test_pid_alive_survives_gbk_tasklist_output(monkeypatch: pytest.MonkeyPatch) -> None:
    # 死进程分支：GBK 本地化消息不得让探针抛 TypeError（旧写法返回 stdout=None → `in None`）
    seen = _stub_tasklist(monkeypatch, _TASKLIST_NO_MATCH_GBK)
    assert _pid_alive(4242) is False, "已退出进程（GBK 无匹配消息）必须判不存活"
    assert seen, "探针根本没调用 tasklist，断言成了自证"
    assert seen[0][1].get("text") is not True, "存活探针又开回 text=True：解码重新参与判定"


@pytest.mark.skipif(sys.platform != "win32", reason="tasklist 存活探针分支仅存在于 Windows")
def test_pid_alive_reports_true_from_table_row(monkeypatch: pytest.MonkeyPatch) -> None:
    # 存活分支：同一套字节捕获必须仍能认出表格里的那一行（防止把探针改成恒 False 来「绕过」崩溃）
    _stub_tasklist(monkeypatch, _tasklist_table_row(4242))
    assert _pid_alive(4242) is True, "tasklist 已列出该 PID 却判不存活，进程回收断言会失去意义"


def test_pid_alive_roundtrip_with_real_processes() -> None:
    # 「检测逻辑生效」的真实证据，全程不打桩：起一个长驻子进程判存活，回收后判不存活。
    # 旧写法在 GBK 码页下第二步必抛 TypeError，故这条同时是码页无关性的现场验证。
    proc = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(30)"],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        assert _pid_alive(proc.pid) is True, f"刚启动的子进程 {proc.pid} 被判不存在"
    finally:
        proc.terminate()
        proc.wait(timeout=30)
    time.sleep(0.5)  # 等 OS 释放 pid，避免 tasklist 短暂残留该行
    assert _pid_alive(proc.pid) is False, f"已回收的子进程 {proc.pid} 仍被判存活"


def test_no_subprocess_call_in_this_module_decodes_output() -> None:
    # 源码级锁：本文件任何 subprocess.run/Popen 调用点都不得要求解码（text/encoding/
    # universal_newlines），进程检查一律按字节比较。AST 等价性校验发现不了这种改动
    # （参数只是调用实参、不影响结构等价），故必须单独锁。
    tree = ast.parse(Path(__file__).read_text(encoding="utf-8"), filename=str(__file__))
    offenders: list[str] = []
    probed_calls = 0
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        target = node.func
        if not (
            isinstance(target.value, ast.Name) and target.value.id == "subprocess" and target.attr in ("run", "Popen")
        ):
            continue
        probed_calls += 1
        for kw in node.keywords:
            if kw.arg in ("text", "encoding", "universal_newlines"):
                offenders.append(f"{target.attr}() at line {node.lineno}: {kw.arg}= 会让解码参与判定")
    # 断言「扫到了调用点」再断言「无违规」，否则正则/AST 落空会造出恒绿的假绿门禁
    assert probed_calls >= 3, f"AST 未覆盖到本文件的子进程调用点（实际 {probed_calls} 处），本用例前提失效"
    assert not offenders, "进程检查调用点须按字节捕获输出（MID-64 ②）:\n" + "\n".join(offenders)
