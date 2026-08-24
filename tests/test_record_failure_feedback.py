# 录制结果反馈调度的回归测试（离线，不依赖网络/真实 ffmpeg）。
#
# 背景（2026-08-23 GUI 79 房间实测日志定稿）：
# - 虎牙房间 ffmpeg 秒级 403（探针 200/206 通过后紧随被拒），此前录制失败既不记
#   熔断失败样本、轮末还无条件记成功样本 → 按 host 熔断统计被稀释、永不触发，
#   房间无限重撞同一条死线路。
# - 修复：check_subprocess 按退出码上报（rc==0→record_success / rc!=0→record_error），
#   且快速失败（输入打开被拒的签名）时把 ffmpeg 实际拉流地址经 mark_ffmpeg_reject
#   记入探针退避——下一轮 select_source_url 跳过该线路探针、改试下一 CDN 候选。
# - 控制台并发容量显示调度器实时自适应值（旧实现显示配置值，实测容量 12 显示 3）。

import subprocess
import sys
import types
from collections.abc import Generator
from pathlib import Path
from typing import Any

import pytest


@pytest.fixture(scope="module")
def main_mod() -> Generator[Any, None, None]:
    # main.py 的 _app_root() 基于 sys.argv[0] 定位 config/，pytest 下 argv[0] 指向 pytest 自身，
    # 需在导入前修正为项目 main.py（与 tests/test_danmaku_wiring.py 同一模式）。
    old_argv = sys.argv[:]
    sys.argv = [str(Path(__file__).resolve().parent.parent / "main.py")]
    try:
        import main

        yield main
    finally:
        sys.argv = old_argv


def _make_subprocess_shim(returncode: int) -> types.SimpleNamespace:
    # 构造 main 模块级 subprocess 引用的替身（只换 main.subprocess 全局引用，不污染 stdlib——
    # 直接 patch stdlib Popen 会波及同进程 harness 守护线程）。Popen 必须是类且定义
    # __class_getitem__：check_subprocess 内层函数注解 subprocess.Popen[bytes] 在 def 时求值。
    # poll 首次返回 None（模拟运行一拍），随后返回退出码，循环退出。

    class _FakePopen:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            self._polled = False
            self.returncode = returncode

        def __class_getitem__(cls, item: Any) -> Any:
            return cls

        def poll(self) -> int | None:
            if not self._polled:
                self._polled = True
                return None  # 第一拍仍在运行，走一次循环体（sleep 已 mock 为 no-op）
            return returncode

        def wait(self, timeout: int = 0) -> int:
            return returncode

    shim = types.SimpleNamespace(**vars(subprocess))
    shim.Popen = _FakePopen
    return shim


def _setup_common(
    monkeypatch: pytest.MonkeyPatch,
    main: Any,
    returncode: int,
) -> tuple[list[tuple[str, str | None]], list[tuple[str, str | None]], list[tuple[str, str | None]]]:
    # 装配 check_subprocess 运行所需的外部依赖 mock；返回 (成功样本, 失败样本, 退避标记) 捕获列表。
    monkeypatch.setattr(main, "enable_danmaku", False)
    monkeypatch.setattr(main, "enable_danmaku_monitor", False)
    monkeypatch.setattr(main, "create_time_file", False)
    monkeypatch.setattr(main, "converts_to_mp4", False)
    monkeypatch.setattr(main, "exit_recording", False)
    monkeypatch.setattr(main, "url_comments", set())
    monkeypatch.setattr(main, "register_ffmpeg_process", lambda proc: None)
    monkeypatch.setattr(main, "unregister_ffmpeg_process", lambda proc: None)
    monkeypatch.setattr(main.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(main, "subprocess", _make_subprocess_shim(returncode))

    successes: list[tuple[str, str | None]] = []
    failures: list[tuple[str, str | None]] = []
    marks: list[tuple[str, str | None]] = []
    monkeypatch.setattr(main, "record_success", lambda key=None: successes.append(("success", key)))
    monkeypatch.setattr(main, "record_error", lambda key=None: failures.append(("error", key)))
    monkeypatch.setattr(main, "mark_ffmpeg_reject", lambda url, platform: marks.append((url, platform)))
    return successes, failures, marks


def test_check_subprocess_success_records_success_sample(main_mod: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    # rc==0（流正常结束）＝平台健康：按房间 host 记一次成功样本
    main = main_mod
    successes, failures, _marks = _setup_common(monkeypatch, main, 0)

    result = main.check_subprocess(
        "主播名",
        "https://www.huya.com/16028551",
        ["ffmpeg", "-i", "http://hs.hls.huya.com/src/x.m3u8", "/tmp/out.ts"],
        "TS",
        None,
        platform="虎牙直播",
    )

    assert result is False
    assert successes == [("success", "www.huya.com")]
    assert failures == []


def test_check_subprocess_fast_failure_records_error_and_backoff(
    main_mod: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    # 快速失败（实测形态：探针 200 后 ffmpeg 立即 403）：记失败样本 + 实际拉流地址记入探针退避
    main = main_mod
    successes, failures, marks = _setup_common(monkeypatch, main, 3436169992)

    result = main.check_subprocess(
        "主播名",
        "https://www.huya.com/16028551",
        ["ffmpeg", "-i", "http://hs.hls.huya.com/src/x.m3u8", "/tmp/out.ts"],
        "TS",
        None,
        platform="虎牙直播",
    )

    assert result is False
    assert failures == [("error", "www.huya.com")]
    assert successes == []
    # -i 后的第一个参数即 ffmpeg 实际拉流地址；platform 透传（退避白名单在 stream_select 内裁决）
    assert marks == [("http://hs.hls.huya.com/src/x.m3u8", "虎牙直播")]


def test_check_subprocess_slow_failure_skips_backoff_mark(main_mod: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    # 慢速失败（拉流中断/重连耗尽，通常 >60s）：只记失败样本，不记探针退避——
    # 该线路此前可正常拉流，标记退避会误伤下一轮的候选选择。
    # 通过注入负阈值模拟「存活时长超过快速失败窗口」（进程实际瞬间退出，真实 elapsed≈0），
    # 避免 patch stdlib time.time 扰动 harness 守护线程。
    main = main_mod
    successes, failures, marks = _setup_common(monkeypatch, main, 1)
    monkeypatch.setattr(main, "_FFMPEG_FAST_FAIL_SECONDS", -1.0)

    result = main.check_subprocess(
        "主播名",
        "https://www.huya.com/16028551",
        ["ffmpeg", "-i", "http://hs.hls.huya.com/src/x.m3u8", "/tmp/out.ts"],
        "TS",
        None,
        platform="虎牙直播",
    )

    assert result is False
    assert failures == [("error", "www.huya.com")]
    assert successes == []
    assert marks == []


def test_check_subprocess_failure_without_input_flag_is_safe(main_mod: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    # ffmpeg 命令缺 -i 参数（异常入参）：快速失败分支不抛异常，仅记失败样本、跳过退避标记
    main = main_mod
    successes, failures, marks = _setup_common(monkeypatch, main, 1)

    result = main.check_subprocess(
        "主播名",
        "https://live.douyin.com/123456",
        ["ffmpeg", "-y", "/tmp/out.ts"],
        "TS",
        None,
        platform="抖音直播",
    )

    assert result is False
    assert failures == [("error", "live.douyin.com")]
    assert marks == []


def test_live_network_capacity_fallback_and_scheduler_value(main_mod: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    # 控制台并发容量显示：调度器就绪时取自适应实时值，未就绪时回退配置值
    # （2026-08-23 实测：容量自适应 12/20 而旧显示固定打印配置值 3，严重误导）
    from src.recorder_status import _live_network_capacity

    main = main_mod
    monkeypatch.setattr(main, "max_request", 3)

    monkeypatch.setattr(main, "scheduler", None)
    assert _live_network_capacity() == 3

    fake_scheduler = types.SimpleNamespace(network_semaphore=types.SimpleNamespace(value=12))
    monkeypatch.setattr(main, "scheduler", fake_scheduler)
    assert _live_network_capacity() == 12
