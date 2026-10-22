# -*- coding: utf-8 -*-
# src/notify.py 录后自定义脚本钩子（run_script）的安全不变量回归锁（WP-C / M-5）。
#
# 四条必须锁住的行为（任意一条被改回旧形态即应变红）：
#   ① 凭据不落盘：command 与异常文本一律过 utils.mask_credentials 才进 logger（logs/ 按 rotation
#      保留多份 ⇒ 原文入日志＝凭据长期落盘）。断言口径是「密钥确实从日志文本里消失」，而不是
#      「调用过 mask_credentials」——后者即使删掉生产实现里的那次调用也照样全绿。
#   ② 超时后第二次 communicate() 必须带**有限**超时：无超时的读取会被「握着管道写端的孙进程」
#      永久挂住（实测：孙进程 sleep 60 时只 kill 直接子进程，communicate 仍取不到输出）。
#   ③ 进程树回收：Windows 走 `taskkill /T /F /PID`（argv 列表、禁 shell=True、输出按字节丢弃），
#      POSIX 走 start_new_session + os.killpg；两分支失败时一律退化到 process.kill()，回收路径的
#      异常绝不许改变 run_script 对外的成败语义。
#   ④ 平台分支由模块级常量 _KILL_TREE_VIA_TASKKILL 选择，用例强制置 True，让 taskkill 路径在
#      Linux CI 上真实执行（平台专属分支不得靠 skipif 让 CI 跳过；CI 全在 ubuntu）。
#
# 打桩面只有 subprocess（浅拷贝 shim 后替换 src.notify 命名空间里的引用，不改 stdlib 本体，
# tests/test_test_hygiene.py R1）与超时常量；脱敏 / 分支选择 / 退化路径全部走真实代码。
# 唯一真起进程的是最后那条端到端用例，判定只看耗时与日志文本，从不解码子进程输出
# （taskkill/python 在中文 Windows 上按 GBK 码页回显）。

import io
import os
import shlex
import signal
import subprocess
import sys
import time
import types
from collections.abc import Generator
from pathlib import Path
from typing import Any, cast

import pytest
from loguru import logger

# src.notify 通过 `import main` 读写运行时全局；必须先引入 main 才能加载 src.notify。
# [LT-07] 注入只为下面两行的**导入期**服务，用完当场摘回（完整理由见 tests/test_notify.py 的同名
# 注释：旧形态把仓库根永久留在 sys.path[0]、从不还原，而 fixture 又晚于模块级 import、搬不进去）。
_REPO_ROOT = str(Path(__file__).resolve().parent.parent)
_PATH_BASELINE = sys.path.count(_REPO_ROOT)  # 注入前的条目数（各调用形态下都实测为 0 或 1）
sys.path.insert(0, _REPO_ROOT)
try:
    import main  # noqa: E402  必须在 src.notify 之前（本文件不直接用其成员，仅为导入顺序）
    import src.notify as notify  # noqa: E402
finally:
    if _REPO_ROOT in sys.path:
        sys.path.remove(_REPO_ROOT)
# LT-07 泄漏判据：「注入 → 导入 → 摘回」三步必须把 sys.path 归还成注入前的条目数（按计数比，不按
# 整表相等）。与 tests/test_notify.py 末尾同一条守卫。
assert sys.path.count(_REPO_ROOT) == _PATH_BASELINE, "仓库根被永久留在 sys.path：注入未归还，状态泄漏"

# 四类真实凭据形态，全部落在 utils.mask_credentials 的五条模式覆盖范围内（写用例前逐条实测）：
# 裸 user:pass@host、scheme://user:pass@host、请求头 Authorization、命令行 --password=。
_SECRET_PROXY_USER = "sup3clone"
_SECRET_PROXY_PASS = "Sup3rSecretRclonePass"
_SECRET_BEARER = "AbcDef0123456789TOKENVALUE"
_SECRET_DB_PASS = "SuPerDbPassw0rd"
_ALL_SECRETS = (_SECRET_PROXY_PASS, _SECRET_BEARER, _SECRET_DB_PASS)

# 一条典型的「上传网盘 + 回写数据库」录后脚本命令：用户真的会这么写（rclone remote + curl 头）。
# 引号成对，保证 shlex.split 不会先炸（超时/回收分支要用例内的替身进程驱动）。
SCRIPT_COMMAND = (
    f"rclone copy https://{_SECRET_PROXY_USER}:{_SECRET_PROXY_PASS}@storage.example.com:5550:remote /rec"
    f' --header "Authorization: Bearer {_SECRET_BEARER}"'
    " --log-file ./up.log"
    f" and mysql --password={_SECRET_DB_PASS} -h db.example.com rec -e 'insert'"
)

# 会命中 ValueError 的畸形命令（未闭合引号）：shlex.split 直接抛，压根不起进程
BROKEN_COMMAND = f'curl -H "Authorization: Bearer {_SECRET_BEARER} https://x.example.com/api'

# 端到端用例的脚本体：先起一个长睡的孙进程（继承 stdout 管道写端），自己再长睡。
# 孙进程 sleep 秒数刻意远大于断言阈值，但不至于在「回归真发生时」把会话拖太久。
_GRANDCHILD_BODY = (
    "import subprocess, sys, time\n"
    "subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])\n"
    "time.sleep(60)\n"
)


@pytest.fixture
def short_timeouts(monkeypatch: pytest.MonkeyPatch) -> None:
    # 执行超时压到 1 秒；回收读取超时**放大**到 20 秒——放大后一旦进程树回收失效
    # （孙进程仍握着管道写端），端到端用例的耗时会顶到 20 秒，而不是侥幸落在断言阈值内。
    monkeypatch.setattr(notify, "_SCRIPT_TIMEOUT_SECONDS", 1.0)
    monkeypatch.setattr(notify, "_SCRIPT_REAP_TIMEOUT_SECONDS", 20.0)


@pytest.fixture
def log_capture() -> Generator[io.StringIO, None, None]:
    # 内存 sink 直接接管 loguru（caplog 抓不到：本仓不把 loguru 桥接到 stdlib logging）。
    # format 带 {level}：用例要区分「error 主路径」与「warning 降级留痕」两个级别。
    buf = io.StringIO()
    sink_id = logger.add(buf, format="{level} {message}", level="DEBUG")
    try:
        yield buf
    finally:
        try:
            logger.remove(sink_id)
        except ValueError:
            pass


class _FakeProc:
    # subprocess.Popen[bytes] 的替身：只实现 run_script 与回收路径真正消费的三个成员。
    # results 逐条对应第 1、2、… 次 communicate()：异常实例=抛出，元组=返回。
    # kill_error：模拟「子进程已自行退出」——POSIX 下 process.kill() 会抛 ProcessLookupError，
    # 回收路径必须把它当期望终态吞掉（覆盖率上那也是 finally 里唯一一条异常分支）。
    def __init__(
        self, results: list[Any] | None = None, pid: int = 424242, kill_error: Exception | None = None
    ) -> None:
        self.pid = pid
        self.killed = 0
        self.kill_error = kill_error
        self.communicate_timeouts: list[float | None] = []
        self._results: list[Any] = list(results or [])

    def __class_getitem__(cls, item: object) -> type["_FakeProc"]:
        # 仓内替身惯例（AGENTS「FakePopen 必须是类且定义 __class_getitem__」）：被测模块里
        # `subprocess.Popen[bytes]` 这类下标注解在 def 时求值，替身一旦被拿去喂注解就得可下标。
        return cls

    def communicate(self, timeout: float | None = None) -> tuple[bytes, bytes]:
        self.communicate_timeouts.append(timeout)
        item = self._results.pop(0) if self._results else (b"", b"")
        if isinstance(item, BaseException):
            raise item
        return cast("tuple[bytes, bytes]", item)

    def kill(self) -> None:
        self.killed += 1
        if self.kill_error is not None:
            raise self.kill_error


class _PopenFactory:
    # 记录每次 Popen 的 args/kwargs（「进程树回收」的前提是脚本确实自成会话，故 start_new_session
    # 也要被锁），并按预置返回 _FakeProc 或直接抛异常（模拟无执行权限 / 找不到二进制 / 解析失败）。
    def __init__(self, proc: _FakeProc | None = None, error: BaseException | None = None) -> None:
        self.calls: list[tuple[list[Any], dict[str, Any]]] = []
        self._proc = proc
        self._error = error

    def __call__(self, args: Any, **kwargs: Any) -> _FakeProc:
        self.calls.append((list(args), kwargs))
        if self._error is not None:
            raise self._error
        assert self._proc is not None, "用例没预置替身进程，也没有异常可抛"
        return self._proc


class _RunRecorder:
    # subprocess.run 的替身：taskkill 分支用它记录 argv 与 kwargs，可注入异常模拟回收失败。
    def __init__(self, error: BaseException | None = None) -> None:
        self.calls: list[tuple[list[Any], dict[str, Any]]] = []
        self._error = error

    def __call__(self, argv: Any, **kwargs: Any) -> subprocess.CompletedProcess[bytes]:
        self.calls.append((list(argv), kwargs))
        if self._error is not None:
            raise self._error
        return subprocess.CompletedProcess[bytes](list(argv), 0, b"", b"")


class _PosixSpy:
    # _kill_posix_process_group 的替身：记录被调用时的 pid，可注入异常模拟 killpg 失败。
    def __init__(self, error: BaseException | None = None) -> None:
        self.calls: list[int] = []
        self._error = error

    def __call__(self, pid: int) -> None:
        self.calls.append(pid)
        if self._error is not None:
            raise self._error


def _install_subprocess_stub(
    monkeypatch: pytest.MonkeyPatch, popen: _PopenFactory, run: _RunRecorder | None = None
) -> None:
    # 浅拷贝 vars(subprocess) 成 SimpleNamespace 后**只替换 src.notify 命名空间里的引用**：
    # 直接 monkeypatch.setattr(subprocess, "Popen", ...) 改的是全进程唯一的 stdlib 模块本体，
    # 会波及 harness 守护线程与其他用例（AGENTS + tests/test_test_hygiene.py R1）。
    # PIPE / TimeoutExpired 仍从真 subprocess 继承，故生产代码里的异常判定照常成立。
    shim = types.SimpleNamespace(**vars(subprocess))
    shim.Popen = popen
    if run is not None:
        shim.run = run
    monkeypatch.setattr(notify, "subprocess", shim)


def _timeout_after_run() -> subprocess.TimeoutExpired:
    # 真 subprocess 抛的 TimeoutExpired 文本里会带上**完整命令行**（正是需要脱敏的形态），
    # 这里刻意用真实 args 构造，保证「异常文本含凭据」这一前提成立。
    return subprocess.TimeoutExpired(shlex.split(SCRIPT_COMMAND), 1.0, output=b"partial-before-timeout")


@pytest.mark.parametrize("via_taskkill", [True, False], ids=["windows-taskkill", "posix-killpg"])
def test_spawn_branch_kwargs(monkeypatch: pytest.MonkeyPatch, via_taskkill: bool) -> None:
    # 进程树回收的前提锁（两个分支都在同一台机器上跑）：
    #   POSIX 分支 ⇒ 必须 start_new_session=True，killpg 才有目标进程组；
    #   Windows 分支 ⇒ 不得把 POSIX-only 的会话 detach 参数塞进进程创建参数（CPython 的 Windows
    #   侧本就忽略它，本机实测还撞过一次偶发 OSError [WinError 50]）。两分支都不得回退到 shell=True。
    proc = _FakeProc([_timeout_after_run(), (b"", b"")])
    popen = _PopenFactory(proc)
    run = _RunRecorder()
    _install_subprocess_stub(monkeypatch, popen, run)
    monkeypatch.setattr(notify, "_KILL_TREE_VIA_TASKKILL", via_taskkill)
    monkeypatch.setattr(notify, "_kill_posix_process_group", _PosixSpy())
    notify.run_script(SCRIPT_COMMAND)

    assert len(popen.calls) == 1, popen.calls
    args, kwargs = popen.calls[0]
    assert kwargs.get("shell") is not True, "run_script 的『不用 shell』前提被推倒＝命令注入面回归"
    assert args and all(isinstance(a, str) for a in args), "必须传 shlex.split 后的 argv 列表"
    if via_taskkill:
        assert "start_new_session" not in kwargs, f"Windows 分支不该收到 POSIX-only 参数: {kwargs}"
    else:
        assert kwargs.get("start_new_session") is True, "孙进程继承管道写端时，无 setsid 就杀不掉整棵树"


@pytest.mark.parametrize(
    ("stage", "error"),
    [
        # 三条 Popen 侧失败分支：替身里的异常文本刻意带上整条命令（含凭据），
        # 于是「command 过了码、e 没过码」这种半截修复也会被同一条用例抓到。
        ("permission", PermissionError(13, f"Permission denied: {SCRIPT_COMMAND}")),
        ("oserror", FileNotFoundError(2, f"No such file or directory: {SCRIPT_COMMAND}")),
        ("valueerror", ValueError(f"No closing quotation in: {SCRIPT_COMMAND}")),
    ],
    ids=["permission-denied", "os-error", "value-error"],
)
def test_failure_branches_never_write_raw_credentials(
    monkeypatch: pytest.MonkeyPatch,
    log_capture: io.StringIO,
    stage: str,
    error: BaseException,
) -> None:
    # ① 无执行权限 / OSError / ValueError 三条分支：命令原文与异常文本都不得原样落日志。
    popen = _PopenFactory(error=error)
    _install_subprocess_stub(monkeypatch, popen)
    notify.run_script(SCRIPT_COMMAND)

    text = log_capture.getvalue()
    # 见证「确实进了预期分支并落了日志」：空日志会让下面的「不含密钥」空洞成立（假绿）
    expect_fragment = {
        "permission": "执行自定义脚本失败（无执行权限）",
        "oserror": "执行自定义脚本失败",
        "valueerror": "脚本命令解析失败",
    }[stage]
    assert expect_fragment in text, f"未进入 {stage} 分支，日志为: {text!r}"
    for secret in _ALL_SECRETS:
        assert secret not in text, f"{stage} 分支把凭据 {secret!r} 原样写进了日志"
    assert "***" in text, "脱敏痕迹缺失＝可能根本没走 mask_credentials（或整行被抹空）"
    # 非敏感部分必须留着：日志还得能定位是哪条脚本命令出的问题
    assert "storage.example.com" in text and "rclone" in text, text
    # AGENTS「异常日志必须带异常类型与上下文」：type_name 实参要真的出现在文本里
    assert type(error).__name__ in text, text


def test_broken_shlex_command_masks_command_and_keeps_type_name(log_capture: io.StringIO) -> None:
    # ① 的真实触发路径（不经任何替身）：未闭合引号让 shlex.split 抛 ValueError，
    # 而命令原文里带着 Authorization 头 —— 落日志时必须只剩掩码。
    notify.run_script(BROKEN_COMMAND)
    text = log_capture.getvalue()
    assert "脚本命令解析失败" in text, text
    assert "ValueError" in text, text
    assert _SECRET_BEARER not in text, "未闭合引号分支把 Bearer 令牌原样写进了日志"
    assert "***" in text


def test_timeout_branch_masks_command_and_logs_termination(
    monkeypatch: pytest.MonkeyPatch,
    log_capture: io.StringIO,
) -> None:
    # ①+② 的超时分支：回收进程树后记的那条 error 里同样不得出现凭据原文。
    proc = _FakeProc([_timeout_after_run(), (b"", b"")])
    popen = _PopenFactory(proc)
    run = _RunRecorder()
    _install_subprocess_stub(monkeypatch, popen, run)
    monkeypatch.setattr(notify, "_KILL_TREE_VIA_TASKKILL", True)
    monkeypatch.setattr(notify, "_kill_posix_process_group", _PosixSpy())
    notify.run_script(SCRIPT_COMMAND)

    text = log_capture.getvalue()
    assert "执行自定义脚本超时" in text, text
    for secret in _ALL_SECRETS:
        assert secret not in text, f"超时分支把凭据 {secret!r} 原样写进了日志"
    assert "***" in text


def test_second_communicate_carries_a_finite_timeout(
    monkeypatch: pytest.MonkeyPatch,
    log_capture: io.StringIO,
) -> None:
    # ② 的核心形态锁：第一次 communicate 带执行超时，第二次**也必须带有限超时**，
    # 否则孙进程握着管道写端时录后钩子线程被永久挂住（旧代码此处是 communicate() 无参）。
    proc = _FakeProc([_timeout_after_run(), (b"", b"")])
    popen = _PopenFactory(proc)
    run = _RunRecorder()
    _install_subprocess_stub(monkeypatch, popen, run)
    monkeypatch.setattr(notify, "_KILL_TREE_VIA_TASKKILL", True)
    monkeypatch.setattr(notify, "_kill_posix_process_group", _PosixSpy())
    notify.run_script(SCRIPT_COMMAND)

    assert len(proc.communicate_timeouts) == 2, proc.communicate_timeouts
    assert proc.communicate_timeouts[0] == notify._SCRIPT_TIMEOUT_SECONDS
    reap_timeout = proc.communicate_timeouts[1]
    assert reap_timeout is not None, "第二次 communicate() 回到无超时 = 可被孙进程永久挂住"
    assert 0.0 < reap_timeout <= notify._SCRIPT_REAP_TIMEOUT_SECONDS, reap_timeout
    assert log_capture.getvalue() != "", "超时分支没落日志，后面的断言全在空转"


def test_reap_timeout_gives_up_reading_and_leaves_warning(
    monkeypatch: pytest.MonkeyPatch,
    log_capture: io.StringIO,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # ② 的行为面：第二次 communicate 也超时 ⇒ run_script 必须**返回**（不抛、不再等），
    # 留一条 warning，并把已读到的部分输出照常打印（一条都没读到也不崩）。
    reap_error = subprocess.TimeoutExpired(shlex.split(SCRIPT_COMMAND), 20.0, output=b"partial-out")
    proc = _FakeProc([_timeout_after_run(), reap_error])
    popen = _PopenFactory(proc)
    run = _RunRecorder()
    _install_subprocess_stub(monkeypatch, popen, run)
    monkeypatch.setattr(notify, "_KILL_TREE_VIA_TASKKILL", True)
    monkeypatch.setattr(notify, "_kill_posix_process_group", _PosixSpy())

    started = time.monotonic()
    notify.run_script(SCRIPT_COMMAND)  # 不得抛
    assert time.monotonic() - started < 5.0, "放弃读取的分支自己又在等真实超时"

    text = log_capture.getvalue()
    assert "WARNING" in text and "TimeoutExpired" in text, f"放弃读取时未留 warning: {text!r}"
    assert "执行自定义脚本超时" in text, text
    for secret in _ALL_SECRETS:
        assert secret not in text, f"放弃读取分支把凭据 {secret!r} 写进了日志"
    assert "partial-out" in capsys.readouterr().out, "已读到的部分输出不得被顺手丢掉"


def test_windows_branch_uses_taskkill_argv_list(
    monkeypatch: pytest.MonkeyPatch,
    log_capture: io.StringIO,
) -> None:
    # ③+④：强制 _KILL_TREE_VIA_TASKKILL=True，让 Windows 回收链在 Linux CI 上真实执行。
    monkeypatch.setattr(notify, "_KILL_TREE_VIA_TASKKILL", True)
    proc = _FakeProc([_timeout_after_run(), (b"", b"")])
    popen = _PopenFactory(proc)
    run = _RunRecorder()
    _install_subprocess_stub(monkeypatch, popen, run)
    posix_spy = _PosixSpy()
    monkeypatch.setattr(notify, "_kill_posix_process_group", posix_spy)

    notify.run_script(SCRIPT_COMMAND)

    assert len(run.calls) == 1, run.calls
    argv, kwargs = run.calls[0]
    assert argv == ["taskkill", "/T", "/F", "/PID", str(proc.pid)], argv
    assert "shell" not in kwargs, "taskkill 必须 argv 列表调用，禁 shell=True"
    assert kwargs.get("capture_output") is True, kwargs
    # 输出按字节丢弃：解码会踩 taskkill 的 GBK 码页（AGENTS「探测子进程输出一律按字节比较」）
    assert not kwargs.get("text") and "encoding" not in kwargs and "errors" not in kwargs, kwargs
    assert kwargs.get("check") is False, "taskkill 退出码不参与判定，回收失败由退化路径处理"
    assert kwargs.get("timeout") == notify._TREE_KILL_TIMEOUT_SECONDS, kwargs
    assert posix_spy.calls == [], "Windows 分支不该再去碰 killpg"
    assert proc.killed == 1, "taskkill 之后仍要 kill 直接子进程兜底"
    assert "WARNING" not in log_capture.getvalue(), "taskkill 正常返回时不该有降级告警"


def test_posix_branch_delegates_to_process_group_kill(
    monkeypatch: pytest.MonkeyPatch,
    log_capture: io.StringIO,
) -> None:
    # ③+④：POSIX 分支去进程组回收，且不碰 taskkill。
    monkeypatch.setattr(notify, "_KILL_TREE_VIA_TASKKILL", False)
    proc = _FakeProc([_timeout_after_run(), (b"", b"")])
    popen = _PopenFactory(proc)
    run = _RunRecorder()
    _install_subprocess_stub(monkeypatch, popen, run)
    posix_spy = _PosixSpy()
    monkeypatch.setattr(notify, "_kill_posix_process_group", posix_spy)

    notify.run_script(SCRIPT_COMMAND)

    assert posix_spy.calls == [proc.pid], posix_spy
    assert run.calls == [], "POSIX 分支不得去起 taskkill（Linux 上没有该可执行文件）"
    assert proc.killed == 1
    assert "WARNING" not in log_capture.getvalue(), "回收正常时不该有降级告警"


@pytest.mark.parametrize(("via", "tree_error"), [("taskkill", FileNotFoundError), ("killpg", PermissionError)])
def test_tree_kill_failure_degrades_to_plain_kill_and_never_raises(
    monkeypatch: pytest.MonkeyPatch,
    log_capture: io.StringIO,
    via: str,
    tree_error: type[Exception],
) -> None:
    # ③ 的退化面：两条分支的任何异常（Linux CI 上没有 taskkill / 子进程已退出 / 权限不足）
    # 都必须落回既有的 process.kill()，**绝不**抛给 run_script 的调用方——
    # 录后脚本钩子的成败语义由脚本进程决定，不由回收路径决定。
    error = tree_error(2, f"recycle failed for {SCRIPT_COMMAND}")
    proc = _FakeProc([_timeout_after_run(), (b"", b"")])
    popen = _PopenFactory(proc)
    run = _RunRecorder(error=error) if via == "taskkill" else _RunRecorder()
    _install_subprocess_stub(monkeypatch, popen, run)
    posix_spy = _PosixSpy(error=None if via == "taskkill" else error)
    monkeypatch.setattr(notify, "_kill_posix_process_group", posix_spy)
    monkeypatch.setattr(notify, "_KILL_TREE_VIA_TASKKILL", via == "taskkill")

    notify.run_script(SCRIPT_COMMAND)  # 不得抛

    assert proc.killed == 1, f"{via} 失败后没有退化到 process.kill()"
    text = log_capture.getvalue()
    assert "WARNING" in text and tree_error.__name__ in text, f"回收退化路径未留痕: {text!r}"
    assert "执行自定义脚本超时" in text, "主流程必须继续走完（回收失败 ≠ 跳过超时记录）"
    for secret in _ALL_SECRETS:
        assert secret not in text, f"{via} 退化分支把凭据 {secret!r} 写进了日志"


def test_posix_group_kill_sends_sigkill_to_the_childs_own_group(monkeypatch: pytest.MonkeyPatch) -> None:
    # 真跑 _kill_posix_process_group（不用替身），但把 src.notify 命名空间里的 os 换成记录型 shim：
    # 绝不能真发 SIGKILL——Linux 上 getpgid(真 PID)+killpg 会把跑测试的进程自己打死。
    # 两种平台形态一起断言：win32 必须走 sys.platform 早返回（Windows 根本没有这组符号），
    # POSIX 必须对 pid 本身发 SIGKILL —— 「进程组 ID == 子进程 PID」正是 start_new_session 换来的。
    calls: list[tuple[int, int]] = []
    os_shim = types.SimpleNamespace(**vars(os))
    os_shim.getpgid = lambda pid: pid
    os_shim.killpg = lambda pgid, sig: calls.append((pgid, int(sig)))
    monkeypatch.setattr(notify, "os", os_shim)

    notify._kill_posix_process_group(424242)

    if sys.platform == "win32":
        assert calls == [], "win32 门控失效：Windows 上真去调了 killpg"
    else:
        assert calls == [(424242, int(signal.SIGKILL))], calls


def test_kill_of_already_exited_child_is_swallowed(monkeypatch: pytest.MonkeyPatch, log_capture: io.StringIO) -> None:
    # finally 里 process.kill() 对「已自行退出的子进程」抛 ProcessLookupError（POSIX 的常态终态），
    # 既不许冒泡给调用方，也不该再刷一条告警把人引向「回收失败」的错误方向。
    monkeypatch.setattr(notify, "_KILL_TREE_VIA_TASKKILL", False)
    proc = _FakeProc([_timeout_after_run(), (b"", b"")], kill_error=ProcessLookupError(3, "No such process"))
    popen = _PopenFactory(proc)
    run = _RunRecorder()
    _install_subprocess_stub(monkeypatch, popen, run)
    monkeypatch.setattr(notify, "_kill_posix_process_group", _PosixSpy())

    notify.run_script(SCRIPT_COMMAND)  # 不得抛

    assert proc.killed == 1
    text = log_capture.getvalue()
    assert "ProcessLookupError" not in text, "已退出的子进程不该被报成回收失败"
    assert "WARNING" not in text, text
    assert "执行自定义脚本超时" in text, text


def test_platform_gate_direction_is_locked_in_source() -> None:
    # ③ 的门控方向锁：os.killpg/os.getpgid/signal.SIGKILL 是 POSIX-only 符号（typeshed 在
    # win32 不导出它们），必须用 sys.platform **字面量**早返回门控，否则本地 mypy（win32）红；
    # 而门控条件写反（!= "win32"）静态检查发现不了、只有运行时才暴露 —— 故连文本与顺序一起锁。
    src = Path(cast(str, notify.__file__)).read_text(encoding="utf-8")
    start = src.index("def _kill_posix_process_group(")
    end = start + 1 + src[start + 1 :].index("\ndef ")
    # 剥掉注释行：函数上方的解释性注释里也写了 sys.platform/win32，不剥会被自己的注释误判
    body = "\n".join(line for line in src[start:end].splitlines() if not line.strip().startswith("#"))
    assert 'if sys.platform == "win32":' in body, body
    assert 'sys.platform != "win32"' not in body, "门控条件写反＝Windows 上真去调 killpg"
    assert body.index('if sys.platform == "win32":') < body.index("os.killpg("), "早返回排在 killpg 之后＝门控无效"
    assert "os.getpgid(" in body and "signal.SIGKILL" in body, body


def test_kill_refactor_keeps_success_path_semantics(monkeypatch: pytest.MonkeyPatch, log_capture: io.StringIO) -> None:
    # ④ 的对外契约锁：正常完成的脚本仍原样打印 stdout/stderr、返回 None、一条日志都不多
    # （成功路径不得被回收改造顺带污染；调用方 main.py 只期望「执行完返回」）。
    proc = _FakeProc([(b"hello-out\n", b"hello-err\n")])
    popen = _PopenFactory(proc)
    run = _RunRecorder()
    _install_subprocess_stub(monkeypatch, popen, run)
    # 「返回 None」这一契约由生产签名 `-> None` 本身经 mypy 锁住：这里若写成
    # `completed = notify.run_script(...)` 会撞 [func-returns-value]（mypy 禁止接住
    # 恒返回 None 的调用结果），故只调一次、用「不抛异常 + 日志为零 + 未起 taskkill」证明语义未变。
    notify.run_script(SCRIPT_COMMAND)
    assert log_capture.getvalue() == "", "成功路径新增了日志，说明改动越界"
    assert run.calls == [], "没超就不该去收进程树"
    assert proc.communicate_timeouts == [notify._SCRIPT_TIMEOUT_SECONDS]


def test_real_script_with_grandchild_is_reaped_quickly(short_timeouts: None, log_capture: io.StringIO) -> None:
    # 端到端（真起进程，不打桩）：脚本自己再起一个孙进程并让它长时间 sleep，然后自己也长时间 sleep。
    # 只 kill 直接子进程时，孙进程继承的管道写端让第二次 communicate 读不到 EOF，用时会顶到
    # _SCRIPT_TIMEOUT_SECONDS(1s) + _SCRIPT_REAP_TIMEOUT_SECONDS(20s)；进程树回收生效时应当在
    # 1 秒超时后立刻拿到 EOF。断言阈值 8 秒远小于 20 秒 ⇒ 回收失效必红。
    # 本机 Windows 实测（taskkill /T /F）约 1.8 秒；Linux CI 走 start_new_session + killpg 同形。
    command = f"{shlex.quote(sys.executable)} -c {shlex.quote(_GRANDCHILD_BODY)}"
    started = time.monotonic()
    notify.run_script(command)
    elapsed = time.monotonic() - started
    text = log_capture.getvalue()
    assert "执行自定义脚本超时" in text, (
        "用例前提失效：这条脚本应当走进超时分支（若日志里是 OSError [WinError 50]/[WinError 6] "
        "「不支持该请求/句柄无效」，属本机受限环境偶发拒绝创建子进程，重跑本文件即可；"
        f"真回归则是回收失效导致耗时超阈值）。实际日志: {text!r}"
    )
    assert elapsed < 8.0, f"进程树未被回收，第二次 communicate 仍被孙进程拖着: elapsed={elapsed:.2f}s"
    # 判定只看耗时/日志文本，从不解码子进程输出（跨码页安全）；同时确认命令上下文仍在日志里
    assert Path(sys.executable).name in text, text
