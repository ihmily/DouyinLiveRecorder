# -*- coding: utf-8 -*-
# CODE_REVIEW_2026-10-21 针对 scripts/douyin_live_recorder_standalone.py 的回归锁。
#
# 被测对象是按设计**不 import src/** 的单文件副本（src/scheduler.py 并发实现与部分录制链的
# 物理孪生），因此主线用例抓不到它的语义漂移，必须自带一份：
#   M-90  --selftest 的离线契约：自检只准驱动假实现。旧形态只换绑 http_probe 与
#           _throttle_probe，而 HLS 分支最终调用的是**真实** http_request —— 自检确实对
#           cdn.example 发包，异常又被 `except Exception: return True` 吞成 PASS（假绿）。
#           本文件把「建立 socket 的唯一接缝」换成拒绝器，用自检**必须全绿且一次都没碰到
#           该接缝**来钉住契约；
#   M-89  terminate_all_ffmpeg 必须在「写 q」与 terminate() 之间留出有界等待：Windows 下
#           terminate() 即 TerminateProcess 硬杀，不等就等于优雅收尾那一级从未生效，
#           停止录制后的 mp4/mov 缺 moov、不可播放；
#   M-42 / M-36a  主线 PlatformBreaker/Scheduler 的两处修复回灌后，副本侧的同名不变量
#           （min_samples 钳到窗口内、fail_rate=0 不得在满成功窗口熔断、熔断表 LRU 上限且
#           不逐出仍在熔断中的键）。
#
# 原则（与 tests/test_regression_standalone.py 同口径）：只打桩网络接缝与时间，
# 熔断状态机、终止链、自检判据一律走副本真实代码。

import importlib.util
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

_ROOT = Path(__file__).resolve().parent.parent
_STANDALONE_PATH = _ROOT / "scripts" / "douyin_live_recorder_standalone.py"


def _load_standalone() -> Any:
    # 与 tests/test_regression_standalone.py 同法按路径加载：顶层只有常量与函数定义，
    # 真网络请求只发生在 main() 里，故 import 无副作用。模块名刻意不同，避免与那份用例互相覆盖。
    spec = importlib.util.spec_from_file_location("dlr_standalone_2026_10_21_under_test", _STANDALONE_PATH)
    assert spec and spec.loader, "无法为单文件副本构造 importlib spec"
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


SA = _load_standalone()


@pytest.fixture
def _restore_ffmpeg_registry() -> Iterator[None]:
    # _ACTIVE_FFMPEG 是模块级 set，注入的假进程必须当条用例内回收（否则同文件后续用例
    # 会把它当成在录 ffmpeg 去终止）。
    saved = set(SA._ACTIVE_FFMPEG)
    SA._ACTIVE_FFMPEG.clear()
    yield
    SA._ACTIVE_FFMPEG.clear()
    SA._ACTIVE_FFMPEG.update(saved)


class _FakeStdin:
    def __init__(self) -> None:
        self.writes: list[Any] = []
        self.closed = False

    def write(self, data: Any) -> None:
        self.writes.append(data)

    def flush(self) -> None:
        return None

    def close(self) -> None:
        self.closed = True


class _GracefulExitPopen:
    # 只仿真「ffmpeg 读到 q 后自行收尾退出」这一种时序：第一次**带 timeout** 的 wait
    # （即优雅段的有界等待）返回退出码 0。终止链本身一律走副本真实代码，不在这里重写。
    def __class_getitem__(cls, item: object) -> type["_GracefulExitPopen"]:
        return cls

    def __init__(self) -> None:
        self.pid = 4242
        self.returncode: int | None = None
        self.stdin = _FakeStdin()
        self.terminate_called = False
        self.kill_called = False
        self.bounded_waits = 0

    def poll(self) -> int | None:
        return self.returncode

    def wait(self, timeout: float | None = None) -> int:
        if timeout is not None:
            self.bounded_waits += 1
            self.returncode = 0  # 模拟 ffmpeg 读到 q 后自行收尾退出
        return 0

    def terminate(self) -> None:
        self.terminate_called = True
        self.returncode = -15

    def kill(self) -> None:
        self.kill_called = True
        self.returncode = -9


class TestStandaloneSelftestOfflineContract:
    def test_selftest_never_reaches_the_socket_seam(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # M-90：http_request / http_probe / _confirm_get_ok 三条出站路径都经 _build_opener 建立
        # 连接——那是本副本**唯一**造出 socket 的接缝。把它换成拒绝器后自检仍须 0 失败，
        # 且拒绝器一次都没被调用（后半句才是「没发真实请求」的直接证据，光看 rc 会被
        # 「异常被保守吞成 True」的旧形态掩盖）。
        attempts: list[str] = []

        def _deny_opener(proxy: str | None) -> Any:
            attempts.append(str(proxy))
            raise AssertionError("selftest 试图建立真实网络连接（违反文件头的离线契约）")

        monkeypatch.setattr(SA, "_build_opener", _deny_opener)
        rc = SA.selftest()
        out = capsys.readouterr().out

        assert rc == 0, out[-2000:]
        assert "[FAIL]" not in out, out[-2000:]
        assert attempts == [], f"自检经 _build_opener 发了真实请求: {attempts}"
        # 判据自检：HLS 那组用例必须真的在自检里跑过（否则上面三条断言全是空转）
        assert "[PASS] 小写 .m3u8 走 HLS 分支(Range-GET 救回)" in out
        assert "[PASS] 大写 .M3U8 同走 HLS 分支(大小写不敏感)" in out
        assert "[PASS] HLS 自检全程走假 http_request(离线契约)" in out

    def test_selftest_restores_the_network_seams(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # 换绑必须随 finally 还原：自检结束后 http_request / http_probe / _throttle_probe
        # 仍指向真实实现，且 _SELFTEST_ACTIVE 归位为 False——否则「自检模式下的保守放行改判失败」
        # 会泄漏到正常录制链路，把「列表 GET 失败交由 ffmpeg」的真实语义改掉（M-90 的另一半）。
        saved = (SA.http_request, SA.http_probe, SA._throttle_probe)
        monkeypatch.setattr(SA, "_build_opener", lambda proxy: (_ for _ in ()).throw(AssertionError("离线守卫")))
        SA.selftest()
        capsys.readouterr()
        assert (SA.http_request, SA.http_probe, SA._throttle_probe) == saved
        assert SA._SELFTEST_ACTIVE is False

    def test_hls_probe_fails_loudly_under_selftest_when_request_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # 生产语义（保守维持列表可达）与自检语义（显式判失败）必须分叉：
        # _SELFTEST_ACTIVE=False 时异常仍返回 True，否则这条修复会把真实录制链的保守兜底改掉。
        monkeypatch.setattr(SA, "_SELFTEST_ACTIVE", False)
        monkeypatch.setattr(SA, "http_request", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("network down")))
        assert SA._probe_hls_segment_lite("https://cdn.example/a.m3u8", {}, None) is True

        monkeypatch.setattr(SA, "_SELFTEST_ACTIVE", True)
        assert SA._probe_hls_segment_lite("https://cdn.example/a.m3u8", {}, None) is False


class TestStandaloneTerminateStages:
    def test_graceful_stage_is_allowed_to_finish_before_terminate(self, _restore_ffmpeg_registry: None) -> None:
        # M-89：写 q + close 之后必须先进入有界等待。旧实现紧接着无条件 terminate()，
        # Windows 下即 TerminateProcess 硬杀——「优雅收尾补写 moov」那一级从未生效。
        proc = _GracefulExitPopen()
        SA._ACTIVE_FFMPEG.add(proc)

        killed = SA.terminate_all_ffmpeg()

        assert proc.stdin.writes == [b"q"], proc.stdin.writes
        assert proc.stdin.closed is True, "写完 q 未关闭 stdin：部分构建读不到 EOF 不处理 q"
        assert proc.bounded_waits >= 1, "q 之后没有留等待窗口，硬杀必然抢占优雅收尾"
        assert proc.terminate_called is False, "进程已在优雅段退出仍被 terminate()：mp4/mov 会缺 moov"
        assert proc.kill_called is False
        assert killed == 1

    def test_hard_kill_chain_still_runs_when_graceful_stage_times_out(
        self, _restore_ffmpeg_registry: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # 反向保证：优雅段等不到时，terminate → kill 两级照旧执行（不得为了「保 moov」
        # 把硬杀兜底删掉，那会留下继续拉流的孤儿 ffmpeg）。
        class _NeverExits(_GracefulExitPopen):
            def wait(self, timeout: float | None = None) -> int:
                if timeout is not None:
                    self.bounded_waits += 1
                    # 形参名是 cmd（不是 args）——传错关键字会抛 TypeError、被外层通用 except
                    # 吞掉，于是「进入下一级」这条路径根本不会被走到（假绿形态）。
                    raise subprocess.TimeoutExpired(["ffmpeg"], timeout)
                return 0

        proc = _NeverExits()
        SA._ACTIVE_FFMPEG.add(proc)
        monkeypatch.setattr(SA, "debug", lambda *a, **k: None)

        killed = SA.terminate_all_ffmpeg()

        assert proc.terminate_called is True
        assert proc.kill_called is True
        assert killed == 1


class TestStandaloneBreakerClamps:
    def test_min_samples_is_clamped_to_window(self) -> None:
        # M-42 回灌：MIN_SAMPLES(8) > window(3) 时旧写法永不开熔断，坏 host 拿满全部流量。
        breaker = SA.PlatformBreaker("t", window=3, fail_rate=0.5, cooldown=60.0)
        assert breaker._min_samples == 3
        for _ in range(3):
            breaker.record(False)
        assert breaker.state == "open", breaker.state
        assert breaker.allow() is False

    def test_zero_fail_rate_does_not_open_on_all_success(self) -> None:
        # M-42 回灌：fail_rate=0 时 0 >= 0 恒真，全成功窗口不得被判熔断。
        breaker = SA.PlatformBreaker("t", window=10, fail_rate=0.0, cooldown=60.0)
        for _ in range(10):
            breaker.record(True)
        assert breaker.state == "closed", breaker.state
        breaker.record(False)  # 「有任何失败即熔断」的合法语义仍要成立
        assert breaker.state == "open", breaker.state

    def test_fail_rate_is_clamped_into_unit_interval(self) -> None:
        assert SA.PlatformBreaker("t", fail_rate=1.5)._fail_rate == 1.0
        assert SA.PlatformBreaker("t", fail_rate=-2.0)._fail_rate == 0.0


class TestStandaloneBreakerTableBound:
    def test_breaker_table_is_bounded_by_lru(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # M-36a 回灌：key 来自 host_of(record_url)，属外部可控输入，旧写法只增不减。
        monkeypatch.setattr(SA.Scheduler, "MAX_BREAKERS", 4)
        scheduler = SA.Scheduler()
        for i in range(30):
            scheduler.record_failure(f"host{i}.example")
        assert len(scheduler._breakers) == 4, len(scheduler._breakers)
        assert list(scheduler._breakers) == [f"host{i}.example" for i in range(26, 30)], list(scheduler._breakers)

    def test_eviction_never_drops_a_tripped_breaker(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # 逐出只看 closed：open/half-open 是「仍在使用」的形态，摘掉等于把一次进行中的熔断
        # 重置成放行，坏 CDN 会立刻回到全部房间流量。
        monkeypatch.setattr(SA.Scheduler, "MAX_BREAKERS", 2)
        scheduler = SA.Scheduler()
        for _ in range(10):
            scheduler.record_failure("bad.example")
        assert scheduler._breaker("bad.example").state == "open"
        for key in ("a.example", "b.example", "c.example"):
            scheduler.record_failure(key)
        assert "bad.example" in scheduler._breakers, "熔断中的键被逐出：探针/冷却状态被重置"
