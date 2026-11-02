# ffmpeg 进程清理链路回归（CODE_REVIEW_2026-09-20）。
#
# 全部离线：不启动真实 ffmpeg，进程对象用桩替代。
#
# 锁定的不变量：
#   ① cleanup_all_ffmpeg_processes() 必须有总预算：一个卡死的 worker 不得挂住整条退出链路
#      （它由 atexit 与面板「停止录制」两处调用）；未确认的进程必须留在注册表，清理线程必须是守护线程；
#   ② 三段终止等待按剩余预算分摊且永不为 0（timeout//3 == 0 等于跳过优雅退出，MP4 丢 moov）；
#   ③ Windows 下 stdin 写完即关闭（写失败也要关）。
#   ④ 三级终止全部失败时的兜底必须关闭 stdout/stderr/stdin 三支管道，
#      且逐支独立 best-effort（一支关不上不得拖累其余两支）。
#
# ③ 是 Windows 专属形态（POSIX 侧发 SIGINT、根本不碰 stdin，原因见 src/ffmpeg_proc.py
# 的 _QUIT_VIA_STDIN 注释），但 CI 跑在 ubuntu——若按平台 skip，这两条锁会在 CI 上静默
# 消失（与「skipped 与 passed 不可区分」同一风险）。故统一用 monkeypatch 把
# fp._QUIT_VIA_STDIN 置 True，让 Windows 路径在 Linux CI 上也被真实执行。

import ast
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, cast

import pytest

import src.ffmpeg_proc as fp


class _FakeStdin:
    def __init__(self, raise_on_write: bool = False) -> None:
        self.raise_on_write = raise_on_write
        self.is_closed = False

    def write(self, data: Any) -> int:
        if self.raise_on_write:
            raise OSError("pipe busy")  # 模拟管道缓冲满 / ffmpeg 不读 stdin
        return len(data)

    def flush(self) -> None:
        if self.raise_on_write:
            raise OSError("pipe busy")

    def close(self) -> None:
        self.is_closed = True


class _FakeStdout:
    def __init__(self) -> None:
        self.is_closed = False

    def close(self) -> None:
        self.is_closed = True


class _FailingPipe:
    # close() 必抛（模拟句柄已被对端销毁 / 杀软占用），用于证明「逐支独立 best-effort」
    is_closed = False

    def close(self) -> None:
        raise OSError("模拟管道句柄不可关")


class _FakeProc:
    # 只实现 _terminate_ffmpeg_process / cleanup 用到的那部分 Popen 接口。
    # exits_on: None=永不退出（wait 一律抛超时）；"terminate"/"kill"=该级之后退出。
    def __init__(self, exits_on: str | None = "terminate", raise_on_stdin_write: bool = False) -> None:
        self.pid = 4242
        self.stdin: Any = _FakeStdin(raise_on_stdin_write)
        self.stdout: Any = _FakeStdout()
        # ③：兜底关闭覆盖三支管道，替身必须有 stderr（真实 Popen 在 PIPE 下三支都在）
        self.stderr: Any = _FakeStdout()
        self.returncode: int | None = None
        self._exits_on = exits_on
        self.waits: list[float | None] = []
        self.signals: list[int] = []

    def poll(self) -> int | None:
        return self.returncode

    def wait(self, timeout: float | None = None) -> int | None:
        self.waits.append(timeout)
        if self.returncode is None:
            raise subprocess.TimeoutExpired(cmd="ffmpeg", timeout=timeout if timeout is not None else 0.0)
        return self.returncode

    def send_signal(self, sig: int) -> None:
        self.signals.append(sig)
        if self._exits_on == "signal":
            self.returncode = 0

    def terminate(self) -> None:
        if self._exits_on in ("terminate", "signal"):
            self.returncode = -15

    def kill(self) -> None:
        if self._exits_on in ("terminate", "kill", "signal"):
            self.returncode = -9


def _clear_registry() -> None:
    with fp._processes_lock:
        fp._ffmpeg_processes.clear()


@pytest.fixture(autouse=True)
def _isolate_registry() -> Any:
    # 注册表是模块级全局：逐用例前后清空，避免残留把别的用例带下水
    _clear_registry()
    yield
    _clear_registry()


def test_recording_popen_wires_stdin_pipe() -> None:
    # S-06 接线锁：录制 Popen 若接 DEVNULL，Popen.stdin 恒为 None，_terminate_ffmpeg_process 的
    # 「写 q」分支与末级关管道都是空操作，Windows 上停止录制只能走 TerminateProcess 硬杀——
    # 正在写的 mp4/mkv/m4a 分段缺 moov/索引、产物不可播。本锁只认接线（分支行为由上面几条覆盖），
    # 不重复测分支逻辑；纯静态、平台无关，Windows 能力在 Linux CI 上同样被锁住。
    source = (Path(__file__).resolve().parent.parent / "main.py").read_text(encoding="utf-8")
    wired = [
        ast.unparse(kw.value)
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Call) and ast.unparse(node.func) == "subprocess.Popen"
        for kw in node.keywords
        if kw.arg == "stdin"
    ]
    assert wired, "main.py 未找到带 stdin= 的录制 Popen 接线，锁的枚举面失效"
    assert wired == ["subprocess.PIPE"], f"录制 Popen 的 stdin 必须接 PIPE（否则写 q 不可达）: {wired}"


def test_unregister_closes_stdin_pipe() -> None:
    # 自然退出（poll 非空）根本不进 _terminate_ffmpeg_process，录制期 PIPE 只能由 unregister 收尾，
    # 否则句柄留到解释器收尾（S-06 接线后的配套释放点）。
    proc = _FakeProc()
    fp.register_ffmpeg_process(cast("Any", proc))
    fp.unregister_ffmpeg_process(cast("Any", proc))
    assert proc.stdin.is_closed is True


def test_stage_budget_never_zero_for_small_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    # timeout=1 时旧实现 timeout//3 == 0 → proc.wait(0) 立即超时，优雅退出整段被跳过
    monkeypatch.setattr(fp, "_QUIT_VIA_STDIN", True)
    proc = _FakeProc(exits_on="terminate")
    ok = fp._terminate_ffmpeg_process(cast(Any, proc), timeout=1)

    assert ok is True
    assert proc.waits, "未进行任何等待"
    assert all(w is not None and w >= fp._MIN_STAGE_WAIT_SECONDS for w in proc.waits), proc.waits
    # 优雅退出（q / SIGINT）确实被等过：至少有一段等待发生在 terminate 之前
    assert proc.stdin.is_closed is True


def test_stage_budget_splits_full_timeout() -> None:
    # timeout=30 的默认口径：首段约占三分之一，后续段随剩余预算收敛
    proc = _FakeProc(exits_on="kill")
    ok = fp._terminate_ffmpeg_process(cast(Any, proc), timeout=30)

    assert ok is True
    first = proc.waits[0]
    assert first is not None and 9.0 <= first <= 11.0, proc.waits
    assert len(proc.waits) == 3, proc.waits


def test_stdin_closed_even_when_write_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    # 旧实现把 close() 与 write/flush 放在同一个 try 里：写失败即跳过 close，
    # 部分 ffmpeg 构建要读到 EOF 才处理 'q'，于是优雅退出形同虚设
    monkeypatch.setattr(fp, "_QUIT_VIA_STDIN", True)
    proc = _FakeProc(exits_on="kill", raise_on_stdin_write=True)
    fp._terminate_ffmpeg_process(cast(Any, proc), timeout=3)

    assert proc.stdin.is_closed is True


def test_cleanup_returns_within_budget_when_worker_wedges(monkeypatch: pytest.MonkeyPatch) -> None:
    # 主用例：一个「卡在终止阶段」的进程不得挂住整个清理函数
    # （旧实现 as_completed 无超时、且 with ThreadPoolExecutor 退出即 shutdown(wait=True)）。
    wedged = _FakeProc(exits_on=None)
    release = threading.Event()

    def _blocking_terminate(proc: Any, timeout: int = 30) -> bool:
        _ = release.wait(timeout=30)
        return False

    monkeypatch.setattr(fp, "_terminate_ffmpeg_process", _blocking_terminate)
    monkeypatch.setattr(fp, "_CLEANUP_WAIT_SECONDS", 0.3)
    with fp._processes_lock:
        fp._ffmpeg_processes.append(cast(Any, wedged))

    started = time.monotonic()
    fp.cleanup_all_ffmpeg_processes()
    elapsed = time.monotonic() - started

    release.set()
    assert elapsed < 5.0, f"清理链路被卡死的 worker 挂住: {elapsed:.1f}s"
    # 未确认的进程必须留在注册表里（旧实现无条件 clear() → 孤儿进程失联）
    with fp._processes_lock:
        assert wedged in fp._ffmpeg_processes
    # 清理线程必须是守护线程：否则解释器收尾仍会 join 它（atexit 链路二次挂死）
    lingering = [t for t in threading.enumerate() if t.name.startswith("ffmpeg_cleanup_")]
    assert all(t.daemon for t in lingering), [t.name for t in lingering]


def test_cleanup_confirmed_processes_are_unregistered(monkeypatch: pytest.MonkeyPatch) -> None:
    # 正常路径：能退出的进程清理后从注册表移除，且用例结束时不留非守护线程
    good = _FakeProc(exits_on="terminate")
    with fp._processes_lock:
        fp._ffmpeg_processes.append(cast(Any, good))

    fp.cleanup_all_ffmpeg_processes()

    with fp._processes_lock:
        assert fp._ffmpeg_processes == []
    assert good.returncode is not None


def test_single_process_cleanup_sets_event_even_on_error(monkeypatch: pytest.MonkeyPatch) -> None:
    # worker 抛错也必须置位「已处理完」事件，否则总预算等待方只能干等到超时，
    # 把一次「已处理完」误报成「未确认清理」
    boom = _FakeProc(exits_on="terminate")

    def _raise(proc: Any, timeout: int = 30) -> bool:
        raise RuntimeError("boom")

    monkeypatch.setattr(fp, "_terminate_ffmpeg_process", _raise)
    finished = threading.Event()
    fp._cleanup_single_ffmpeg_process(cast(Any, boom), finished)
    assert finished.is_set()


# ── 三级终止全部失败后的管道兜底必须覆盖三支 ──────────
# 旧形态只关 proc.stdout。走不到「进程已退出」这一步时，stderr（ffmpeg 的进度与错误输出，
# 7×24 多房间下每条录制都开着一支）与 stdin 一律留到解释器收尾才回收：清理线程反复启停
# 就一路攒 fd，而 Windows 上残留句柄还会让 logs/ 与媒体文件的归档改名撞 WinError 32。
# 两支用例都强制走 POSIX 分支（_QUIT_VIA_STDIN=False）：那条路径第一级发 SIGINT、**根本不碰
# stdin**，只有兜底块关过才算数（Windows 分支的 stdin 早在第一步就关了，判据会被掩盖）。


def test_last_resort_closes_all_three_pipes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(fp, "_QUIT_VIA_STDIN", False)
    proc = _FakeProc(exits_on=None)
    ok = fp._terminate_ffmpeg_process(cast(Any, proc), timeout=1)

    assert ok is False, "永不退出的桩进程必须判为未终止"
    assert proc.stdout.is_closed is True
    assert proc.stderr.is_closed is True, "stderr 句柄未随兜底关闭（M-58③ 回归）"
    assert proc.stdin.is_closed is True, "stdin 句柄未随兜底关闭（M-58③ 回归）"


def test_last_resort_pipe_close_failure_does_not_skip_the_other_pipes(monkeypatch: pytest.MonkeyPatch) -> None:
    # 逐支独立 best-effort：任一支 close 抛错（句柄已被对端销毁/杀软占用）不得阻止后面两支，
    # 否则「一支关不上」演变成「三支全泄漏」
    monkeypatch.setattr(fp, "_QUIT_VIA_STDIN", False)
    proc = _FakeProc(exits_on=None)
    proc.stdout = _FailingPipe()
    ok = fp._terminate_ffmpeg_process(cast(Any, proc), timeout=1)

    assert ok is False
    assert proc.stderr.is_closed is True
    assert proc.stdin.is_closed is True
