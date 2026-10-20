# 录制结果反馈调度的回归测试（离线，不依赖网络/真实 ffmpeg）。
#
# 背景（2026-08-23 GUI 79 房间实测日志定稿）：虎牙房间 ffmpeg 秒级 403（探针 200/206 通过后紧随
# 被拒），此前录制失败既不记熔断失败样本、轮末还无条件记成功样本 → 按 host 的熔断统计被稀释、
# 永不触发，房间无限重撞同一条死线路。修复后 check_subprocess 按退出码上报（rc==0→record_success /
# rc!=0→record_error），快速失败时把实际拉流地址经 mark_ffmpeg_reject 记入探针退避。
# 直下路径（direct_download_stream，shopee/花椒直播专用）无 ffmpeg 退出码：非 200 / 网络异常在函数
# 内部消化成 False，调用方按「未被注释且无退出标志」判为真-失败并记 record_error，否则坏线路绕开
# 熔断统计被无限重撞。控制台并发容量显示调度器实时自适应值（旧实现显示配置值，实测 12 显示 3）。

import subprocess
import sys
import tempfile
import time
import types
from collections.abc import Generator
from pathlib import Path
from types import ModuleType
from typing import Any

import httpx
import pytest

# ffmpeg 输出路径必须落在**真实存在**的目录里：check_subprocess 以「输出父目录不存在」判定输出侧
# 本地 IO 失败并豁免探针退避（MID-02 引入、MID-N01 于 2026-09-22 收敛为单判据）。旧写法 "/tmp/out.ts"
# 在 Linux 父目录存在、Windows 不存在，同一条用例两侧语义相反；取 tempfile.gettempdir() 后两侧
# 都是健康可写目录，断言语义与平台无关。
_OUT_TS = str(Path(tempfile.gettempdir()) / "dvr_probe_out.ts")


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


def _module_shim(module: ModuleType) -> types.SimpleNamespace:
    # MID-66：把 stdlib / 第三方模块浅拷贝成替身，只替换 **main 命名空间里的全局名**，绝不 setattr
    # 到模块本体——time/os/httpx 是全进程唯一对象，loguru 的 enqueue 线程、harness 守护线程与
    # coverage 都在同一进程里跑，会被假实现波及。与 _make_subprocess_shim 同源，即 AGENTS.md 规定的模式。
    return types.SimpleNamespace(**vars(module))


def _make_subprocess_shim(returncode: int) -> types.SimpleNamespace:
    # 构造 main 模块级 subprocess 引用的替身（只换 main.subprocess 全局引用，不污染 stdlib——
    # 直接 patch stdlib Popen 会波及同进程 harness 守护线程）。Popen 必须是类且定义
    # __class_getitem__：check_subprocess 内层注解 subprocess.Popen[bytes] 在 def 时求值。
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
    # 只把 sleep 变成 no-op；time.time / time.strftime 保持真实实现（快速失败判定要用）
    _time_shim = _module_shim(time)
    _time_shim.sleep = lambda seconds: None
    monkeypatch.setattr(main, "time", _time_shim)
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
        ["ffmpeg", "-i", "http://hs.hls.huya.com/src/x.m3u8", _OUT_TS],
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
        ["ffmpeg", "-i", "http://hs.hls.huya.com/src/x.m3u8", _OUT_TS],
        "TS",
        None,
        platform="虎牙直播",
    )

    assert result is False
    assert failures == [("error", "www.huya.com")]
    assert successes == []
    # -i 后的第一个参数即 ffmpeg 实际拉流地址；platform 透传（退避白名单在 stream_select 内裁决）
    assert marks == [("http://hs.hls.huya.com/src/x.m3u8", "虎牙直播")]


def test_check_subprocess_interrupts_when_recording_disabled(main_mod: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    # 停止录制（Web 面板「停止录制」置 recording_enabled=False）：录制中的 ffmpeg
    # 被终止、返回 True（调用方据此结束房间线程）。poll 恒返回 None 模拟 ffmpeg
    # 一直运行，验证中断只能来自 recording_enabled 检测点。
    main = main_mod
    successes, failures, _marks = _setup_common(monkeypatch, main, 0)
    monkeypatch.setattr(main, "recording_enabled", False)

    class _RunningPopen:
        # 恒运行替身：poll 永远 None，__class_getitem__ 供 def 时注解求值（见 _setup_common 注释）
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            self.returncode = 0

        def __class_getitem__(cls, item: Any) -> Any:
            return cls

        def poll(self) -> int | None:
            return None

        def wait(self, timeout: int = 0) -> int:
            return 0

    shim = types.SimpleNamespace(**vars(subprocess))
    shim.Popen = _RunningPopen
    monkeypatch.setattr(main, "subprocess", shim)

    terminated: list[object] = []

    def _fake_terminate(proc: object, timeout: int = 30) -> bool:
        terminated.append(proc)
        return True

    monkeypatch.setattr(main, "_terminate_ffmpeg_process", _fake_terminate)

    result = main.check_subprocess(
        "主播名",
        "https://www.huya.com/16028551",
        ["ffmpeg", "-i", "http://hs.hls.huya.com/src/x.m3u8", _OUT_TS],
        "TS",
        None,
        platform="虎牙直播",
    )

    assert result is True
    assert len(terminated) == 1
    # 中断退出非自然结束：不计成功/失败样本（与注释退出路径语义一致）
    assert successes == []
    assert failures == []


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
        ["ffmpeg", "-i", "http://hs.hls.huya.com/src/x.m3u8", _OUT_TS],
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
        ["ffmpeg", "-y", _OUT_TS],
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

    # SEV-01：控制台显示的并发容量取调度器的 capacity（上限），不再是 value（剩余许可）
    fake_scheduler = types.SimpleNamespace(network_semaphore=types.SimpleNamespace(value=12, capacity=12))
    monkeypatch.setattr(main, "scheduler", fake_scheduler)
    assert _live_network_capacity() == 12


class _FakeStreamResponse:
    # httpx 流式响应替身：status_code/数据块由用例注入
    def __init__(self, status_code: int, chunks: list[bytes]) -> None:
        self.status_code = status_code
        self._chunks = chunks

    def __enter__(self) -> "_FakeStreamResponse":
        return self

    def __exit__(self, *args: Any) -> None:
        return None

    def iter_bytes(self, chunk_size: int) -> Any:
        return iter(self._chunks)


class _FakeHttpClient:
    # httpx.Client 替身：stream(method, url, headers=..., follow_redirects=...) 返回注入的响应
    def __init__(self, response: _FakeStreamResponse) -> None:
        self._response = response

    def __enter__(self) -> "_FakeHttpClient":
        return self

    def __exit__(self, *args: Any) -> None:
        return None

    def stream(self, method: str, url: str, **kwargs: Any) -> _FakeStreamResponse:
        return self._response


def test_direct_download_stream_rejects_non_200_as_failure(
    main_mod: Any, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # CDN 拒绝（非 200）＝真-失败签名：吞异常返回 False、不写半截文件后假装完成；
    # 调用方（start_record 直下分支）依据「未被注释且无退出标志」将 False 记入熔断失败样本
    main = main_mod
    monkeypatch.setattr(main, "get_record_headers", lambda *a, **k: {})
    monkeypatch.setattr(main, "get_record_user_agent", lambda *a, **k: "")
    # MID-66：httpx 同样是全进程共享的三方模块本体，改走浅拷贝替身
    _httpx_shim = _module_shim(httpx)
    _httpx_shim.Client = lambda **kw: _FakeHttpClient(_FakeStreamResponse(403, []))
    monkeypatch.setattr(main, "httpx", _httpx_shim)
    save_path = tmp_path / "out.flv"

    assert (
        main.direct_download_stream(
            "http://cdn.example/live.flv", str(save_path), "主播", "https://x/huya.com/1", "虎牙直播"
        )
        is False
    )


def test_direct_download_stream_writes_chunks_on_success(
    main_mod: Any, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # 正常拉流：逐块写入文件并返回 True（调用方据此记 record_success 样本）
    main = main_mod
    monkeypatch.setattr(main, "get_record_headers", lambda *a, **k: {})
    monkeypatch.setattr(main, "get_record_user_agent", lambda *a, **k: "")
    # MID-06 后「200 + 零/极小响应体」不再算成功，替身体量必须过 `_MIN_VALID_RECORD_BYTES`
    # 门槛，否则失败原因与断言不符（门槛本身由 tests/test_record_watchdog.py 逐条锁定）。
    payload = [b"flv-header", b"chunk" * 500, b"tail"]
    assert sum(len(c) for c in payload) > main._MIN_VALID_RECORD_BYTES, "替身须大于直下成功门槛"
    _httpx_shim = _module_shim(httpx)
    _httpx_shim.Client = lambda **kw: _FakeHttpClient(_FakeStreamResponse(200, payload))
    monkeypatch.setattr(main, "httpx", _httpx_shim)
    save_path = tmp_path / "out.flv"

    assert (
        main.direct_download_stream(
            "http://cdn.example/live.flv", str(save_path), "主播", "https://www.huya.com/1", "虎牙直播"
        )
        is True
    )
    assert save_path.read_bytes() == b"".join(payload)
