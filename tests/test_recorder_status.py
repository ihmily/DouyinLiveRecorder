# -*- coding: utf-8 -*-
# src.recorder_status 单元测试（离线，不依赖网络/真实控制台）。
#
# 覆盖两条与并发/守护线程节拍相关的回归锁：
#   - 该显示侧：控制台「同一时间访问网络的线程数」取自适应**容量**（上限本身），
#     而不是空闲槽数——有房间持槽时二者必然不同，显示空闲数同样误导。
#   - ：display_info 守护线程的异常路径必须有休眠且按连续失败退避；
#     无控制台环境（sys.stdout is None，见 AGENTS「无控制台环境」条目）下不得进 try 刷异常。
#
# 注：recorder_status 在模块导入期即 `import main`，故本文件的用例都必须先实例化 main_mod。

import json
import sys
import types
from collections.abc import Generator
from pathlib import Path
from typing import Any, cast

import pytest

from src.scheduler import ResizableSemaphore


@pytest.fixture(scope="module")
def main_mod() -> Generator[Any, None, None]:
    # main.py 的 _app_root() 基于 sys.argv[0] 定位 config/，pytest 下 argv[0] 指向 pytest 自身，
    # 需在导入前修正为项目 main.py（与 tests/test_record_failure_feedback.py 同一模式）。
    old_argv = sys.argv[:]
    sys.argv = [str(Path(__file__).resolve().parent.parent / "main.py")]
    try:
        import main

        yield main
    finally:
        sys.argv = old_argv


@pytest.fixture
def status_mod(main_mod: Any) -> Any:
    # 依赖 main_mod：确保 recorder_status 导入链里的 `import main` 走的是已修正 argv 的那一次
    import src.recorder_status as recorder_status

    return recorder_status


class _StopLoop(BaseException):
    # 必须派生自 BaseException：display_info 的循环里有 `except Exception`，
    # 用普通 Exception 作停止信号会被吞掉、用例永远停不下来。
    pass


class _RecordingLogger:
    # logger 替身：只记录调用，不写真实日志文件（本用例要数「刷了多少条异常日志」）。
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warnings: list[str] = []
        self.debugs: list[str] = []
        self.infos: list[str] = []

    def error(self, msg: object, *args: Any, **kwargs: Any) -> None:
        self.errors.append(str(msg))

    def warning(self, msg: object, *args: Any, **kwargs: Any) -> None:
        self.warnings.append(str(msg))

    def debug(self, msg: object, *args: Any, **kwargs: Any) -> None:
        self.debugs.append(str(msg))

    def info(self, msg: object, *args: Any, **kwargs: Any) -> None:
        self.infos.append(str(msg))


class _BrokenStdout:
    # 模拟两种真实形态：① pythonw/冻结 console=False 下 sys.stdout is None（用例内单独覆盖）；
    # ② Web 后台模式下 logs/web_console.log 被归档改名/句柄已关 → flush() 抛
    #   ValueError: I/O operation on closed file。
    # max_attempts 是硬上限：循环若不退避就会一直冲进来，此时由本对象抛出 _StopLoop 止损，
    # 保证「缺陷回归 → 用例失败」而不是「用例挂死」。
    def __init__(self, max_attempts: int = 8) -> None:
        self.attempts = 0
        self._max_attempts = max_attempts

    def flush(self) -> None:
        self.attempts += 1
        if self.attempts > self._max_attempts:
            raise _StopLoop("循环未按要求休眠，body 被重复调用超过上限")
        raise ValueError("I/O operation on closed file")

    def isatty(self) -> bool:
        return False

    def write(self, text: str) -> int:
        return len(text)


class _FlakyStdout:
    # 第一轮 flush 失败、其后成功：用于验证连续失败计数在成功一轮后归零（否则退避会一直叠加）。
    def __init__(self) -> None:
        self.fail_next = True

    def flush(self) -> None:
        if self.fail_next:
            self.fail_next = False
            raise ValueError("I/O operation on closed file")

    def isatty(self) -> bool:
        return False

    def write(self, text: str) -> int:
        return len(text)


def _install_fake_sleep(status_mod: Any, monkeypatch: pytest.MonkeyPatch, cap: int) -> list[float]:
    # 把模块内的 _sleep 间接层换成记录器：满 cap 次后抛 _StopLoop 结束死循环。
    # 禁止改成 patch recorder_status.time（stdlib 模块本体，会波及同进程其它线程）。
    sleeps: list[float] = []

    def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)
        if len(sleeps) >= cap:
            raise _StopLoop("已达到用例设定的休眠次数")

    monkeypatch.setattr(status_mod, "_sleep", fake_sleep)
    return sleeps


def test_live_network_capacity_reads_capacity_not_free_slots(
    status_mod: Any, main_mod: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    # 未就绪回退配置值；就绪后取并发上限（capacity），而不是被占用削弱的空闲数（value）。
    # 用真实 ResizableSemaphore（被测实现本体），不在测试里重算容量。
    monkeypatch.setattr(main_mod, "max_request", 3)
    monkeypatch.setattr(main_mod, "scheduler", None)
    assert status_mod._live_network_capacity() == 3

    sem = ResizableSemaphore(4)
    assert sem.acquire(blocking=False) is True
    assert sem.value == 3  # 空闲槽已被占用削到 3
    monkeypatch.setattr(main_mod, "scheduler", types.SimpleNamespace(network_semaphore=sem))
    assert status_mod._live_network_capacity() == 4  # 控制台显示的是调度器设定的上限

    sem.release()
    assert status_mod._live_network_capacity() == 4  # 与占用无关


def test_display_info_body_always_raising_still_sleeps_every_iteration(
    status_mod: Any, main_mod: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    # 核心：整个循环唯一的 sleep 曾位于 try 体内、紧跟 flush 之后，flush 自身抛错即跳过它
    # → 零间隔重入 → 单核跑满 + 日志洪水。修复后休眠在 try 之外，且异常按连续次数退避。
    recorder = _RecordingLogger()
    stdout = _BrokenStdout(max_attempts=8)
    monkeypatch.setattr(main_mod, "recording", set())
    monkeypatch.setattr(status_mod, "logger", recorder)
    monkeypatch.setattr(status_mod, "sys", types.SimpleNamespace(stdout=stdout))
    sleeps = _install_fake_sleep(status_mod, monkeypatch, cap=5)

    with pytest.raises(_StopLoop):
        status_mod.display_info()

    interval = status_mod._DISPLAY_INTERVAL_SECONDS
    # 每轮 body 之前都恰好有一次休眠：iterations 不得超过 sleeps+1（初始那次 + 每轮一次）
    assert stdout.attempts <= len(sleeps) + 1
    assert stdout.attempts >= 2  # 确实走过多轮，不是只跑一轮就结束
    assert sleeps[0] == interval  # 首轮仍为常规节拍
    assert sleeps[1] > interval  # 第二次起按连续失败次数退避
    assert sleeps == sorted(sleeps)  # 退避单调不减，不会退回忙等
    assert len(recorder.errors) == stdout.attempts  # 每次失败留一条痕，且未失控刷屏
    assert sleeps[-1] <= status_mod._DISPLAY_BACKOFF_MAX_SECONDS


def test_display_info_backoff_capped(status_mod: Any, main_mod: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    # 长期故障（如日志文件被永久占用）下退避必须有上限，否则一轮要睡到不可预期的秒数；
    # 同时上限仍须远大于常规节拍，才能真正消除忙等。
    recorder = _RecordingLogger()
    stdout = _BrokenStdout(max_attempts=200)
    monkeypatch.setattr(main_mod, "recording", set())
    monkeypatch.setattr(status_mod, "logger", recorder)
    monkeypatch.setattr(status_mod, "sys", types.SimpleNamespace(stdout=stdout))
    sleeps = _install_fake_sleep(status_mod, monkeypatch, cap=40)

    with pytest.raises(_StopLoop):
        status_mod.display_info()

    assert len(sleeps) == 40
    assert max(sleeps) == status_mod._DISPLAY_BACKOFF_MAX_SECONDS
    assert stdout.attempts <= len(sleeps) + 1


def test_display_info_without_console_never_enters_try(
    status_mod: Any, main_mod: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    # 无控制台环境（pythonw.exe / 冻结 console=False exe）：sys.stdout 就是 None，而 main.py
    # 无条件启动本线程。判空必须在 try 之前——否则每轮 AttributeError → logger.error → 忙等。
    recorder = _RecordingLogger()
    monkeypatch.setattr(main_mod, "recording", set())
    monkeypatch.setattr(status_mod, "logger", recorder)
    monkeypatch.setattr(status_mod, "sys", types.SimpleNamespace(stdout=None))
    interval = status_mod._DISPLAY_INTERVAL_SECONDS
    sleeps = _install_fake_sleep(status_mod, monkeypatch, cap=4)

    with pytest.raises(_StopLoop):
        status_mod.display_info()

    assert sleeps == [interval, interval, interval, interval]  # 常规节拍，无异常洪水也无忙等
    assert recorder.errors == []


def test_display_info_backoff_resets_after_successful_cycle(
    status_mod: Any, main_mod: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    # 一次失败 → 退避到 10s；下一轮成功后计数归零，节拍必须回到常规 5s（否则偶发一次 IO 异常
    # 会让状态面板永久变慢）。
    recorder = _RecordingLogger()
    monkeypatch.setattr(main_mod, "recording", set())
    monkeypatch.setattr(main_mod, "monitoring", 0)
    monkeypatch.setattr(main_mod, "scheduler", None)
    monkeypatch.setattr(main_mod, "max_request", 3)
    monkeypatch.setattr(status_mod, "logger", recorder)
    monkeypatch.setattr(status_mod, "sys", types.SimpleNamespace(stdout=_FlakyStdout()))
    interval = status_mod._DISPLAY_INTERVAL_SECONDS
    sleeps = _install_fake_sleep(status_mod, monkeypatch, cap=4)

    with pytest.raises(_StopLoop):
        status_mod.display_info()

    # [初始节拍, 失败后第一次退避, 成功轮内 no-recording 分支的既有 sleep, 成功后回到常规节拍]
    assert sleeps == [interval, interval * 2, interval, interval]
    assert len(recorder.errors) == 1


# ==========================================================================
# 追加段（2026-09-21 覆盖率专项）：get_status 快照与 display_info 的「正在录制」分支。
# get_status 是 Web 面板唯一的轮询数据源，字段形状一变前端就表现为「看不到在录房间」这类间接
# 症状，因此每个字段的存在与口径都要锁：
#   [start, quality, actual_quality] / 旧两元 / 空条目三种形态都要能渲染（兼容层不能只测理想
#   形态）；recent_errors 是 error_window 求和（瞬时口径）、error_count 是累计值，混用会让面板
#   显示倒退；磁盘探测失败报 -1.0（可区分于「真的剩 0GB」）；engine_alive 在
#   _recorder_thread is None（CLI 直跑）时规为存活。
# display_info 的录制分支：set 收敛去重、缺时间条目回退到当前时刻、isatty 为真才发 ANSI 清屏
# （重定向到日志文件时不得污染内容）。
# ==========================================================================


class _NormalStdout:
    # 一条正常可用的控制台：只记录写过的文本，不真刷屏幕（isatty=False 以跳过 ANSI 清屏）。
    def __init__(self, is_tty: bool = False) -> None:
        self.buffer: list[str] = []
        self._is_tty = is_tty

    def flush(self) -> None:
        return None

    def isatty(self) -> bool:
        return self._is_tty

    def write(self, text: str) -> int:
        self.buffer.append(text)
        return len(text)


class _ExplosiveCollection:
    # 模拟「迭代期被并发修改」：list(x) / set(x) 会抛 RuntimeError，
    # 用来触发 get_status 的兜底分支（MI-10 之后该分支理论不可达，但必须留痕）。
    def __init__(self) -> None:
        self._size = 1

    def __iter__(self) -> Any:
        raise RuntimeError("dictionary changed size during iteration")

    def __len__(self) -> int:
        return self._size


@pytest.fixture
def pinned_main(main_mod: Any, monkeypatch: pytest.MonkeyPatch) -> Any:
    # get_status 读遍 main 的运行时全局：一次性给一套「Web 面板在跑」的取值，
    # 单个用例只覆盖自己关心的那一项，避免每个用例重复 20 行 patch。
    monkeypatch.setattr(main_mod, "version", "9.9.9", raising=False)
    monkeypatch.setattr(main_mod, "monitoring", 3, raising=False)
    monkeypatch.setattr(main_mod, "error_count", 7, raising=False)
    monkeypatch.setattr(main_mod, "recording", set(), raising=False)
    monkeypatch.setattr(main_mod, "recording_time_list", {}, raising=False)
    monkeypatch.setattr(main_mod, "running_list", ["https://live.douyin.com/1"], raising=False)
    monkeypatch.setattr(main_mod, "error_window", __import__("collections").deque([1, 1, 0], maxlen=3), raising=False)
    monkeypatch.setattr(main_mod, "default_path", "D:/downloads", raising=False)
    monkeypatch.setattr(main_mod, "_recorder_thread", None, raising=False)
    monkeypatch.setattr(main_mod, "process_start_time", None, raising=False)
    monkeypatch.setattr(main_mod, "recording_enabled", True, raising=False)
    monkeypatch.setattr(main_mod, "start_display_time", __import__("datetime").datetime.now(), raising=False)
    return main_mod


class TestGetStatus:
    def test_idle_snapshot_shape(self, status_mod: Any, pinned_main: Any) -> None:
        snapshot = status_mod.get_status()
        assert snapshot["version"] == "9.9.9"
        assert snapshot["monitoring"] == 3
        assert snapshot["recording_count"] == 0
        assert snapshot["recording"] == []
        assert snapshot["error_count"] == 7
        assert snapshot["recent_errors"] == 2, "窗口口径取自 error_window 求和，不是累计值"
        assert snapshot["running_list"] == ["https://live.douyin.com/1"]
        assert snapshot["engine_alive"] is True, "_recorder_thread 为 None 表示 CLI 直跑，视作存活"
        assert snapshot["uptime"] == "0:00:00"
        assert snapshot["recording_enabled"] is True

    def test_disk_probe_failure_is_reported_as_negative(
        self, status_mod: Any, pinned_main: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def deny(_path: str) -> float:
            raise OSError("no such drive")

        monkeypatch.setattr(status_mod.utils, "check_disk_capacity", deny)
        assert status_mod.get_status()["disk_free_gb"] == -1.0

    def test_new_format_entries_expose_actual_quality(self, status_mod: Any, pinned_main: Any) -> None:
        start = __import__("datetime").datetime(2026, 9, 21, 8, 0, 0)
        pinned_main.recording = {"房间A"}
        pinned_main.recording_time_list = {"房间A": [start, "原画", "超清"]}
        entry = status_mod.get_status()["recording"][0]
        assert entry["name"] == "房间A"
        assert entry["quality"] == "原画"
        assert entry["actual_quality"] == "超清"
        assert entry["start_time"] == "2026-09-21 08:00:00"

    def test_legacy_two_field_entries_still_render(self, status_mod: Any, pinned_main: Any) -> None:
        # 兼容旧格式 [start, quality]：缺第三项时 actual_quality 为空串而不是抛 IndexError
        start = __import__("datetime").datetime(2026, 9, 21, 8, 0, 0)
        pinned_main.recording = {"房间B"}
        pinned_main.recording_time_list = {"房间B": [start, "标清"]}
        entry = status_mod.get_status()["recording"][0]
        assert entry["quality"] == "标清"
        assert entry["actual_quality"] == ""

    def test_missing_time_info_degrades_to_empty_strings(self, status_mod: Any, pinned_main: Any) -> None:
        pinned_main.recording = {"房间C"}
        pinned_main.recording_time_list = {"房间C": []}
        entry = status_mod.get_status()["recording"][0]
        assert entry == {
            "name": "房间C",
            "start_time": "",
            "quality": "",
            "actual_quality": "",
            "duration": "0:00:00",
        }

    def test_recording_without_time_entry_uses_defaults(self, status_mod: Any, pinned_main: Any) -> None:
        pinned_main.recording = {"房间D"}
        pinned_main.recording_time_list = {}
        entry = status_mod.get_status()["recording"][0]
        assert entry["duration"] == "0:00:00"

    def test_concurrent_modification_returns_empty_snapshot_with_warning(
        self, status_mod: Any, pinned_main: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        recorder = _RecordingLogger()
        monkeypatch.setattr(status_mod, "logger", recorder)
        pinned_main.recording = cast(Any, _ExplosiveCollection())
        snapshot = status_mod.get_status()
        assert snapshot["recording"] == []
        assert snapshot["recording_count"] == 0
        assert any("获取录制状态失败" in m for m in recorder.warnings), "兜底分支必须留痕，不能静默空快照"

    def test_dead_engine_thread_and_uptime(
        self, status_mod: Any, pinned_main: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import threading

        dead = threading.Thread(target=lambda: None)
        dead.start()
        # 审查 7.11（2026-10-18）：裸 join() 不带上限会在替身线程挂住时永久挂死；更关键的是本用例
        # 的前提就是「引擎线程已退出」（engine_alive 判据读的正是它的 is_alive 形态），join 超时
        # 返回不等于已退出——不显式断言，快照里 engine_alive=True 也可能被后面的断言放过。
        dead.join(timeout=10)
        assert not dead.is_alive(), "替身线程未在 10s 内退出：dead 前提不成立，不得判绿"
        pinned_main._recorder_thread = dead
        pinned_main.process_start_time = __import__("datetime").datetime.now() - __import__("datetime").timedelta(
            hours=1, minutes=2
        )
        snapshot = status_mod.get_status()
        assert snapshot["engine_alive"] is False
        assert snapshot["uptime"].startswith("1:02:")

    def test_snapshot_is_json_serializable(self, status_mod: Any, pinned_main: Any) -> None:
        pinned_main.recording = {"房间A"}
        pinned_main.recording_time_list = {"房间A": [__import__("datetime").datetime.now(), "原画", "原画"]}
        _ = json.dumps(status_mod.get_status())


class TestDisplayInfoRecordingBranch:
    def _prepare(
        self,
        status_mod: Any,
        main_mod: Any,
        monkeypatch: pytest.MonkeyPatch,
        stdout: _NormalStdout,
        cap: int,
    ) -> list[float]:
        # 注意：只把「窗口样式探测」用的 sys.stdout 换成桩（决定要不要发 ANSI 清屏），
        # display_info 正文走的是内建 print()，因此断言文本要从 capsys 取。
        monkeypatch.setattr(status_mod, "sys", types.SimpleNamespace(stdout=stdout))
        monkeypatch.setattr(main_mod, "scheduler", None)
        monkeypatch.setattr(main_mod, "max_request", 3)
        monkeypatch.setattr(main_mod, "use_proxy", False)
        monkeypatch.setattr(main_mod, "split_video_by_time", False)
        monkeypatch.setattr(main_mod, "create_time_file", False)
        monkeypatch.setattr(main_mod, "video_record_quality", "原画")
        monkeypatch.setattr(main_mod, "video_save_type", "ts")
        monkeypatch.setattr(main_mod, "delay_default", 60)
        return _install_fake_sleep(status_mod, monkeypatch, cap)

    def test_recording_rooms_are_listed_with_elapsed_time(
        self,
        status_mod: Any,
        main_mod: Any,
        pinned_main: Any,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        stdout = _NormalStdout(is_tty=True)
        pinned_main.recording = {"房间A", "房间B"}
        now = __import__("datetime").datetime.now()
        pinned_main.recording_time_list = {
            "房间A": [now - __import__("datetime").timedelta(seconds=90), "原画"],
            # 房间B 故意留空条目：走 `_rt_info[0] if _rt_info else now_time` 的兜底
            "房间B": [],
        }
        self._prepare(status_mod, main_mod, monkeypatch, stdout, cap=2)
        with pytest.raises(_StopLoop):
            status_mod.display_info()
        written = capsys.readouterr().out
        # 去重与计数口径由 display_info 内部的 set() 收敛保证
        assert "正在录制2个直播" in written
        assert "房间A" in written and "房间B" in written
        assert "1:30" in written
        # isatty 为真才发 ANSI 清屏序列；无控制台/重定向时不得污染日志
        assert any("\033[2J" in chunk for chunk in stdout.buffer)
        assert pinned_main.start_display_time is not None

    def test_monitoring_but_nothing_recording_prints_interval_hint(
        self,
        status_mod: Any,
        main_mod: Any,
        pinned_main: Any,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        stdout = _NormalStdout()
        pinned_main.recording = set()
        pinned_main.recording_time_list = {}
        monkeypatch.setattr(main_mod, "monitoring", 5)
        # 无录制分支的顺序是「先 sleep 再打提示」，所以 cap 需 3 才能跑到提示那一行
        self._prepare(status_mod, main_mod, monkeypatch, stdout, cap=3)
        with pytest.raises(_StopLoop):
            status_mod.display_info()
        written = capsys.readouterr().out
        assert "没有正在录制的直播" in written and "60" in written
        assert not any("\033[2J" in chunk for chunk in stdout.buffer)

    def test_idle_machine_prints_no_live_hint(
        self,
        status_mod: Any,
        main_mod: Any,
        pinned_main: Any,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        stdout = _NormalStdout()
        pinned_main.recording = set()
        pinned_main.recording_time_list = {}
        monkeypatch.setattr(main_mod, "monitoring", 0)
        self._prepare(status_mod, main_mod, monkeypatch, stdout, cap=3)
        with pytest.raises(_StopLoop):
            status_mod.display_info()
        assert "没有正在监测和录制的直播" in capsys.readouterr().out

    def test_segment_and_time_file_switches_are_rendered(
        self,
        status_mod: Any,
        main_mod: Any,
        pinned_main: Any,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        stdout = _NormalStdout()
        pinned_main.recording = set()
        pinned_main.recording_time_list = {}
        # 开关必须在 _prepare 之后改：_prepare 会把它们重置为关闭态
        self._prepare(status_mod, main_mod, monkeypatch, stdout, cap=3)
        monkeypatch.setattr(main_mod, "monitoring", 0)
        monkeypatch.setattr(main_mod, "split_video_by_time", True)
        monkeypatch.setattr(main_mod, "split_time", 1800)
        monkeypatch.setattr(main_mod, "create_time_file", True)
        monkeypatch.setattr(main_mod, "use_proxy", True)
        with pytest.raises(_StopLoop):
            status_mod.display_info()
        written = capsys.readouterr().out
        assert "录制分段开启: 1800秒" in written
        assert "是否生成时间文件: 是" in written
        assert "是否开启代理录制: 是" in written

    def test_missing_recording_time_entry_falls_back_to_now(
        self,
        status_mod: Any,
        main_mod: Any,
        pinned_main: Any,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        stdout = _NormalStdout()
        pinned_main.recording = {"幽灵房间"}
        pinned_main.recording_time_list = {}
        self._prepare(status_mod, main_mod, monkeypatch, stdout, cap=2)
        with pytest.raises(_StopLoop):
            status_mod.display_info()
        assert "幽灵房间" in capsys.readouterr().out

    def test_broken_lock_in_recording_branch_triggers_backoff(
        self, status_mod: Any, main_mod: Any, pinned_main: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        recorder = _RecordingLogger()
        monkeypatch.setattr(status_mod, "logger", recorder)
        stdout = _NormalStdout()
        pinned_main.recording = cast(Any, _ExplosiveCollection())
        sleeps = self._prepare(status_mod, main_mod, monkeypatch, stdout, cap=3)
        with pytest.raises(_StopLoop):
            status_mod.display_info()
        assert recorder.errors, "录制分支异常必须留痕"
        assert len(sleeps) == 3
        assert sleeps[0] == status_mod._DISPLAY_INTERVAL_SECONDS
        assert sleeps[-1] > sleeps[0], "连续失败要退避，不能零间隔重入"
