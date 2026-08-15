# Tests for main.py 批次2修复 - 并发/配置/录制路径回归测试.
# 注意: import main 放到 fixture 中延迟执行——本环境在 pytest 收集阶段 spawn
# 子进程（src/__init__ 的 node 检查）偶发 WinError 6/50，测试阶段执行则稳定.

import subprocess
import sys
import threading
from collections.abc import Mapping
from unittest.mock import patch

import pytest


@pytest.fixture(scope="module")
def main_mod():
    # main.py 的 _app_root() 基于 sys.argv[0] 定位 config/，pytest 下 argv[0] 指向 pytest 自身，
    # 需在导入前修正为项目 main.py，否则 config 路径解析到 site-packages 下。
    from pathlib import Path

    old_argv = sys.argv[:]
    sys.argv = [str(Path(__file__).resolve().parent.parent / "main.py")]
    try:
        import main

        return main
    finally:
        sys.argv = old_argv


class TestSafeNumberParsers:
    # _safe_int/_safe_float：非法配置值回退默认，避免主循环崩溃.

    def test_safe_int_valid(self, main_mod):
        assert main_mod._safe_int("7", 3) == 7

    def test_safe_int_invalid_falls_back(self, main_mod):
        assert main_mod._safe_int("abc", 3) == 3
        assert main_mod._safe_int(None, 3) == 3
        assert main_mod._safe_int("", 3) == 3

    def test_safe_float_invalid_falls_back(self, main_mod):
        assert main_mod._safe_float("x", 1.5) == 1.5
        assert main_mod._safe_float("2.5", 1.0) == 2.5


class TestErrorWindow:
    # 错误窗口混合 0/1 采样：错误率可降可升（此前只记 1 导致只能降不能升）.

    def setup_method(self) -> None:
        import main

        main.error_window.clear()

    def test_window_mixes_success_and_error(self, main_mod):
        main_mod.record_error()
        main_mod.record_success()
        main_mod.record_success()
        assert list(main_mod.error_window) == [1, 0, 0]
        assert sum(main_mod.error_window) / len(main_mod.error_window) == pytest.approx(1 / 3)

    def test_window_bounded(self, main_mod):
        for _ in range(20):
            main_mod.record_error()
        assert len(main_mod.error_window) == main_mod.error_window_size

    def test_error_count_increments(self, main_mod):
        before = main_mod.error_count
        main_mod.record_error()
        assert main_mod.error_count == before + 1


class TestFileUpdateLock:
    def test_file_update_lock_is_reentrant(self, main_mod):
        # RLock：主循环持锁读配置期间可重入 read_config_value 的写入路径。
        # 行为化验证：同一线程连续两次 acquire 不阻塞（普通 Lock 会死锁）。
        lock = main_mod.file_update_lock
        assert lock.acquire(blocking=False)
        try:
            assert lock.acquire(blocking=False)
            lock.release()
        finally:
            lock.release()


class TestSelectSourceUrl:
    # h265 FLV 无法 copy 录制：启用 HLS 采集且校验通过才切 HLS；关闭时尊重配置.

    def test_h265_flv_uses_hls_when_enabled_and_valid(self, main_mod):
        with patch("main._validate_stream_url", return_value=True):
            info: Mapping[str, object] = {
                "flv_url": "https://cdn.example.com/live.flv?codec=h265",
                "m3u8_url": "https://cdn.example.com/live.m3u8",
            }
            with patch.object(main_mod, "hls_collection_enabled", True):
                result = main_mod.select_source_url(info)
        assert result == "https://cdn.example.com/live.m3u8"

    def test_h265_flv_skipped_when_hls_disabled(self, main_mod):
        # 用户关闭 HLS 采集时不再强制切回 HLS
        with patch("main._validate_stream_url", return_value=True):
            info: Mapping[str, object] = {
                "flv_url": "https://cdn.example.com/live.flv?codec=h265",
                "m3u8_url": "https://cdn.example.com/live.m3u8",
            }
            with patch.object(main_mod, "hls_collection_enabled", False):
                result = main_mod.select_source_url(info)
        assert result is None

    def test_h265_flv_hls_unreachable_returns_none(self, main_mod):
        with patch("main._validate_stream_url", return_value=False):
            info: Mapping[str, object] = {
                "flv_url": "https://cdn.example.com/live.flv?codec=h265",
                "m3u8_url": "https://cdn.example.com/live.m3u8",
            }
            with patch.object(main_mod, "hls_collection_enabled", True):
                result = main_mod.select_source_url(info)
        assert result is None

    def test_plain_flv_returned(self, main_mod):
        with patch("main._validate_stream_url", return_value=True):
            info: Mapping[str, object] = {"flv_url": "https://cdn.example.com/live.flv?codec=h264"}
            with patch.object(main_mod, "hls_collection_enabled", True):
                result = main_mod.select_source_url(info)
        assert result == "https://cdn.example.com/live.flv?codec=h264"


class FakeProcess:
    # 模拟 subprocess.Popen：验证 _run_ffmpeg_checked 的超时终止与退出码处理
    def __init__(self, returncode: int = 0, out: bytes = b"", timeout_on_communicate: bool = False):
        self.returncode = returncode
        self.out = out
        self.timeout_on_communicate = timeout_on_communicate
        self.killed = False

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def communicate(self, timeout: int | None = None):
        if self.timeout_on_communicate:
            self.timeout_on_communicate = False  # 仅第一次超时，供 kill 后重读
            raise subprocess.TimeoutExpired(cmd=["ffmpeg"], timeout=timeout or 1)
        return self.out, b""

    def kill(self):
        self.killed = True


class TestRunFfmpegChecked:
    # _run_ffmpeg_checked：超时终止 + 非零退出抛 CalledProcessError（转码不再挂死线程）.

    def test_success_returns_output(self, main_mod):
        with patch("subprocess.Popen", return_value=FakeProcess(returncode=0, out=b"ok output")) as mock_popen:
            out = main_mod._run_ffmpeg_checked(["ffmpeg", "-version"])
        assert "ok output" in out
        assert mock_popen.call_count == 1

    def test_failure_raises_called_process_error(self, main_mod):
        with patch("subprocess.Popen", return_value=FakeProcess(returncode=1, out=b"bad")):
            with pytest.raises(subprocess.CalledProcessError):
                main_mod._run_ffmpeg_checked(["ffmpeg", "-this-flag-does-not-exist"])

    def test_timeout_kills_process(self, main_mod):
        fake = FakeProcess(returncode=0, out=b"", timeout_on_communicate=True)
        with patch("subprocess.Popen", return_value=fake):
            with pytest.raises(subprocess.TimeoutExpired):
                main_mod._run_ffmpeg_checked(["ffmpeg", "-i", "x"], timeout=1)
        assert fake.killed
