# tests/test_video_postprocess_paths.py - src/video_postprocess.py 的分支补全。
#
# test_video_postprocess.py 只锁了（转码超时放大 + 半成品清理）这一条
# 与 converts_mp4 相关的不变量；本文件补其余三条**会静默丢产物**的路径：
#   1) segment_video / converts_m4a 的异常分类——超时必须与「转换失败」「未知错误」
#      区分开，否则 ffmpeg 卡死被兜底成 unknown error，用户排查方向全错；
#   2) generate_subtitles 的退出条件——房间不在录制集合时必须立刻返回，
#      否则后台线程永久残留、字幕文件无限增长（长期运行的内存/句柄泄漏面）；
#   3) get_startup_info 的平台分支——非 Windows 不得构造 STARTUPINFO。
#
# 全部离线：ffmpeg 由 _run_ffmpeg_checked 的替身模拟，不启动真实进程；
# time.sleep 经模块内 time 引用的 SimpleNamespace 浅拷贝替换（AGENTS：不改 stdlib 本体）。

# 本文件只管「异常分类」与「退出条件」两类行为，因为这两类缺陷的共同症状是
# 「产物目录里莫名多/少一个文件」，而后端的转码线程又是长驻的：
#   · 异常分类——超时 / CalledProcessError / 其它异常必须落入三条不同日志文案。
#     旧实现只有 except Exception 一条，ffmpeg 卡死被兜底成 unknown error，
#     用户拿着日志找不到「该去查输入文件还是查磁盘」。
#   · 退出条件——generate_subtitles 是后台逐秒追加写的线程，房间不在录制集合时
#     必须立刻 return；否则会留下永久增长的字幕文件与不死的线程。
# 另两个容易被改坏点单独锁住：
#   · _convert_timeout 的下限/上限/显式优先三档（该放大策略）；
#   · get_startup_info 的「os.name == nt 但 sys.platform 不是 win32」组合——这是
#     交叉测试/异常环境里会走到的分支，不得尝试构造 Windows 专属对象。
# Mock 口径：ffmpeg 由 _run_ffmpeg_checked 替身模拟；体积读取与 os.remove 都经
# types.SimpleNamespace(**vars(mod)) 浅拷贝注入，不改 stdlib 模块本体（R1 门禁）。


import datetime
import os
import subprocess
import sys
import threading
import types
from pathlib import Path
from typing import Any, cast

import pytest

import main
import src.video_postprocess as vp


@pytest.fixture(autouse=True)
def _stub_main_globals(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(main, "converts_to_h264", False, raising=False)
    monkeypatch.setattr(main, "os_type", "nt", raising=False)
    monkeypatch.setattr(main, "text_encoding", "utf-8", raising=False)

    class _Color:
        YELLOW = ""

        def print_colored(self, *_a: Any, **_k: Any) -> None:
            return None

    monkeypatch.setattr(main, "color_obj", _Color(), raising=False)
    monkeypatch.setattr(main, "recording", set(), raising=False)
    monkeypatch.setattr(main, "record_state_lock", threading.Lock(), raising=False)


def _make_source(tmp_path: Path, size: int = 64, name: str = "live_000.ts") -> Path:
    # 真写一个小文件而不是 mock exists()/getsize()：三个入口函数都是
    # 「先判存在且非零、再拼命令」，mock 两个条件就把这条守卫本身测不到。
    # 空文件（size=0）与不存在文件是两种不同的跳过形态，都由调用方送进来。
    src = tmp_path / name
    src.write_bytes(b"\x47" * size)
    return src


def _runner(monkeypatch: pytest.MonkeyPatch, error: BaseException | None = None) -> dict[str, Any]:
    recorded: dict[str, Any] = {}

    def _fake_run(command: list[str], timeout: int = 600) -> str:
        recorded["command"] = command
        recorded["timeout"] = timeout
        if error is not None:
            raise error
        return "ffmpeg version n7.1"

    monkeypatch.setattr(vp, "_run_ffmpeg_checked", _fake_run)
    return recorded


def _errors(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    captured: list[str] = []
    monkeypatch.setattr(vp.logger, "error", lambda msg, *a, **k: captured.append(str(msg)))
    return captured


def _recorder(sink: list[list[str]]) -> Any:
    # 记录调用过的 ffmpeg 命令并回空串（_run_ffmpeg_checked 的返回型）。
    # 不能写成 `lambda cmd, timeout=600: sink.append(cmd) or ""`，也不能 `_ = sink.append(...)`：
    # mypy 的 func-returns-value 会因「取用 list.append 的返回值」报错。
    def _fake_run(command: list[str], timeout: int = 600) -> str:
        sink.append(command)
        return ""

    return _fake_run


def _os_shim(**overrides: Any) -> types.SimpleNamespace:
    # 浅拷贝 os / os.path 再覆盖指定符号：避开「经模块命名空间改写 stdlib 本体」（R1 门禁）。
    shim = types.SimpleNamespace(**vars(os))
    path_shim = types.SimpleNamespace(**vars(os.path))
    for name, value in overrides.items():
        setattr(path_shim, name, value)
    shim.path = path_shim
    return shim


class TestConvertTimeoutEstimation:
    @pytest.mark.parametrize(
        "size_mb,re_encoding,explicit,expected",
        [
            (0, False, None, 600),  # 小文件落到 600s 下限
            (100, False, None, 600),  # 100MB×0.04 = 4s → 仍取下限
            (1000, True, None, 1500),  # 1000MB×1.5
            (5000, True, None, 3600),  # 放大后仍被上限钳住
            (1000, True, 30, 30),  # 显式 timeout 优先
        ],
    )
    def test_matrix(
        self, monkeypatch: pytest.MonkeyPatch, size_mb: int, re_encoding: bool, explicit: int | None, expected: int
    ) -> None:
        # 用替身报体积：真写 5GB 稀疏文件在 NTFS 上默认仍会实占磁盘。
        monkeypatch.setattr(vp, "os", _os_shim(getsize=lambda _p: size_mb * 1024 * 1024))
        assert vp._convert_timeout("any.ts", re_encoding, explicit) == expected

    def test_unreadable_size_falls_back_to_floor(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # 文件刚被移走：按 0 处理落到 600s 下限，行为与修复前的固定超时一致（不额外告警）
        def deny(_path: str) -> int:
            raise OSError("gone")

        monkeypatch.setattr(vp, "os", _os_shim(getsize=deny))
        assert vp._convert_timeout("gone.ts", True, None) == 600


class TestStartupInfo:
    def test_non_windows_returns_none(self) -> None:
        assert vp.get_startup_info("posix") is None

    @pytest.mark.skipif(sys.platform != "win32", reason="STARTUPINFO 仅在 Windows 构造")
    def test_windows_builds_hidden_console_startupinfo(self) -> None:
        info = vp.get_startup_info("nt")
        assert info is not None
        # 返回型是 object | None（跨平台），此处按 Windows 实际型取 dwFlags。STARTUPINFO 与
        # STARTF_USESHOWWINDOW 只存在于 Windows typeshed，裸引用会让 `mypy --platform linux`
        # 这一路门禁红在 Linux 侧（AGENTS「平台符号双跑」），故常量取 getattr + 1（真实值）、
        # cast 也不以 STARTUPINFO 为目标；用例本身已由 skipif 保证只在 win32 运行。
        assert cast(Any, info).dwFlags & getattr(subprocess, "STARTF_USESHOWWINDOW", 1)

    def test_nt_on_non_win32_platform_returns_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # os.name == "nt" 但 sys.platform 不是 win32 的组合（交叉测试/异常环境）：
        # 走最后的 return None，不得尝试构造 Windows 专属对象。
        monkeypatch.setattr(vp, "sys", types.SimpleNamespace(platform="linux"))
        assert vp.get_startup_info("nt") is None


class TestRunFfmpegChecked:
    def test_nonzero_returncode_raises_called_process_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        class _Proc:
            returncode = 1

            def communicate(self, timeout: int | None = None) -> tuple[bytes, bytes]:
                return b"boom", b""

            def __enter__(self) -> "_Proc":
                return self

            def __exit__(self, *exc: object) -> None:
                return None

        shim = types.SimpleNamespace(**vars(subprocess))
        shim.Popen = lambda *a, **k: _Proc()
        monkeypatch.setattr(vp, "subprocess", shim)
        with pytest.raises(subprocess.CalledProcessError):
            vp._run_ffmpeg_checked(["ffmpeg", "-version"])

    def test_timeout_kills_process_and_reraises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        state = {"killed": 0, "calls": 0}

        class _Proc:
            returncode = -9

            def communicate(self, timeout: int | None = None) -> tuple[bytes, bytes]:
                state["calls"] += 1
                if state["calls"] == 1:
                    raise subprocess.TimeoutExpired(cmd=["ffmpeg"], timeout=timeout or 1)
                return b"partial", b""

            def kill(self) -> None:
                state["killed"] += 1

            def __enter__(self) -> "_Proc":
                return self

            def __exit__(self, *exc: object) -> None:
                return None

        shim = types.SimpleNamespace(**vars(subprocess))
        shim.Popen = lambda *a, **k: _Proc()
        monkeypatch.setattr(vp, "subprocess", shim)
        with pytest.raises(subprocess.TimeoutExpired):
            vp._run_ffmpeg_checked(["ffmpeg", "-i", "x"], timeout=1)
        assert state == {"killed": 1, "calls": 2}

    def test_success_returns_decoded_output(self, monkeypatch: pytest.MonkeyPatch) -> None:
        class _Proc:
            returncode = 0

            def communicate(self, timeout: int | None = None) -> tuple[bytes, bytes]:
                return "ffmpeg ok \u4e2d\u6587".encode("gbk", errors="ignore"), b""

            def __enter__(self) -> "_Proc":
                return self

            def __exit__(self, *exc: object) -> None:
                return None

        shim = types.SimpleNamespace(**vars(subprocess))
        shim.Popen = lambda *a, **k: _Proc()
        monkeypatch.setattr(vp, "subprocess", shim)
        assert isinstance(vp._run_ffmpeg_checked(["ffmpeg"]), str)


class TestSegmentVideo:
    # segment_video / converts_m4a 两个入口同构：「拼对命令」与「异常分类」各一类用例。
    # 命令本身有回归价值（-segment_format / -reset_timestamps / -movflags 都是历史修复点），
    # 所以断言的是参数对，而不是只断言「调了一次 ffmpeg」。
    def test_happy_path_builds_segment_command(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        src = _make_source(tmp_path)
        recorded = _runner(monkeypatch)
        sleeps: list[float] = []
        monkeypatch.setattr(vp, "time", types.SimpleNamespace(sleep=sleeps.append))
        vp.segment_video(str(src), str(tmp_path / "out_%03d.ts"), "mpegts", "1800")
        cmd = recorded["command"]
        assert cmd[cmd.index("-f") + 1] == "segment"
        assert cmd[cmd.index("-segment_time") + 1] == "1800"
        assert cmd[cmd.index("-segment_format") + 1] == "mpegts"
        assert src.exists() is False, "is_original_delete 默认 True，源文件应被删除"

    def test_keeps_source_when_delete_disabled(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        src = _make_source(tmp_path)
        _runner(monkeypatch)
        monkeypatch.setattr(vp, "time", types.SimpleNamespace(sleep=lambda _s: None))
        vp.segment_video(str(src), str(tmp_path / "out.ts"), "mp4", "60", is_original_delete=False)
        assert src.exists()

    def test_empty_or_missing_source_is_skipped(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        called: list[list[str]] = []
        monkeypatch.setattr(vp, "_run_ffmpeg_checked", _recorder(called))
        empty = tmp_path / "empty.ts"
        empty.write_bytes(b"")
        vp.segment_video(str(empty), "out.ts", "mp4", "60")
        vp.segment_video(str(tmp_path / "missing.ts"), "out.ts", "mp4", "60")
        assert called == []

    def test_timeout_is_distinguished_from_generic_error(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        src = _make_source(tmp_path)
        errors = _errors(monkeypatch)
        _runner(monkeypatch, error=subprocess.TimeoutExpired(cmd=["ffmpeg"], timeout=1))
        vp.segment_video(str(src), "out.ts", "mp4", "60")
        assert any("超时" in m for m in errors)

        errors.clear()
        _runner(monkeypatch, error=subprocess.CalledProcessError(1, ["ffmpeg"]))
        vp.segment_video(str(src), "out.ts", "mp4", "60")
        assert any("conversion" in m for m in errors)

        errors.clear()
        _runner(monkeypatch, error=RuntimeError("weird"))
        vp.segment_video(str(src), "out.ts", "mp4", "60")
        assert any("unknown error" in m for m in errors)


class TestConvertsM4a:
    def test_audio_only_command_is_built(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        src = _make_source(tmp_path)
        recorded = _runner(monkeypatch)
        monkeypatch.setattr(vp, "time", types.SimpleNamespace(sleep=lambda _s: None))
        vp.converts_m4a(str(src))
        cmd = recorded["command"]
        assert "-vn" in cmd and "aac" in cmd and "320k" in cmd
        assert cmd[-1].endswith(".m4a")
        assert src.exists() is False

    def test_no_source_no_work(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        called: list[list[str]] = []
        monkeypatch.setattr(vp, "_run_ffmpeg_checked", _recorder(called))
        vp.converts_m4a(str(tmp_path / "missing.ts"), is_original_delete=False)
        assert called == []

    def test_error_classes_are_reported_separately(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        src = _make_source(tmp_path)
        errors = _errors(monkeypatch)
        _runner(monkeypatch, error=subprocess.TimeoutExpired(cmd=["ffmpeg"], timeout=1))
        vp.converts_m4a(str(src))
        assert any("抽音频超时" in m for m in errors)

        errors.clear()
        _runner(monkeypatch, error=subprocess.CalledProcessError(1, ["ffmpeg"]))
        vp.converts_m4a(str(src))
        assert any("conversion" in m for m in errors)

        errors.clear()
        _runner(monkeypatch, error=RuntimeError("weird"))
        vp.converts_m4a(str(src))
        assert any("unknown error" in m for m in errors)


class TestDiscardPartialOutput:
    def test_noop_when_nothing_to_do(self, tmp_path: Path) -> None:
        assert vp._discard_partial_output("", False, "src") is False
        gone = tmp_path / "out.mp4"
        assert vp._discard_partial_output(str(gone), False, "src") is False
        assert vp._discard_partial_output(str(gone), True, "src") is False

    def test_removes_file_created_by_this_call(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        out = tmp_path / "out.mp4"
        out.write_bytes(b"partial")
        monkeypatch.setattr(vp.logger, "warning", lambda *_a, **_k: None)
        assert vp._discard_partial_output(str(out), False, "src.ts") is True
        assert not out.exists()

    def test_remove_failure_is_reported(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        out = tmp_path / "out.mp4"
        out.write_bytes(b"partial")
        warnings: list[str] = []
        monkeypatch.setattr(vp.logger, "warning", lambda msg, *a, **k: warnings.append(str(msg)))
        # 浅拷贝 shim 替换 vp 命名空间里的 os 引用：直接 setattr(vp.os, "remove", ...)
        # 会改写全进程唯一的 os 模块本体（R1 门禁）。
        shim = types.SimpleNamespace(**vars(os))
        shim.remove = lambda *_a, **_k: (_ for _ in ()).throw(OSError("locked"))
        monkeypatch.setattr(vp, "os", shim)
        assert vp._discard_partial_output(str(out), False, "src.ts") is False
        assert any("locked" in m for m in warnings)


class TestGeneratesSubtitles:
    def test_loop_ends_when_room_stops_recording(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        # generate_subtitles 的入参是**不含扩展名**的前缀（函数自己拼 .srt/.ass）
        prefix = tmp_path / "sub"
        sleeps: list[float] = []

        def stop_after_one(_seconds: float) -> None:
            sleeps.append(_seconds)
            main.recording.discard("room-a")

        monkeypatch.setattr(vp, "time", types.SimpleNamespace(sleep=stop_after_one))
        main.recording.add("room-a")
        vp.generate_subtitles("room-a", str(prefix))
        text = (tmp_path / "sub.srt").read_text(encoding="utf-8")
        assert text.startswith("1\n00:00:01,000 --> 00:00:02,000")
        # 房间已不在录制集合 → 再写一条就退出，不会留下永久增长的后台线程
        assert sleeps == [1]
        assert text.count("\n\n") == 2

    def test_format_and_case_of_extension(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(vp, "time", types.SimpleNamespace(sleep=lambda _s: None))
        vp.generate_subtitles("absent-room", str(tmp_path / "sub"), sub_format="ASS")
        assert (tmp_path / "sub.ass").exists(), "sub_format 大写应被归一为小写扩展名"

    def test_timestamp_advances_across_iterations(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        ticks = iter(
            [
                datetime.datetime(2026, 9, 21, 10, 0, 0),
                datetime.datetime(2026, 9, 21, 10, 0, 1),
                datetime.datetime(2026, 9, 21, 10, 0, 2),
            ]
        )

        # 被测代码走的是 datetime.datetime.now()，因此命名空间需保留这层嵌套
        monkeypatch.setattr(
            vp, "datetime", types.SimpleNamespace(datetime=types.SimpleNamespace(now=lambda: next(ticks)))
        )
        count = {"n": 0}

        def step(_seconds: float) -> None:
            count["n"] += 1
            if count["n"] >= 2:
                main.recording.discard("room-b")

        monkeypatch.setattr(vp, "time", types.SimpleNamespace(sleep=step))
        main.recording.add("room-b")
        vp.generate_subtitles("room-b", str(tmp_path / "sub"))
        text = (tmp_path / "sub.srt").read_text(encoding="utf-8")
        assert "00:00:02,000 --> 00:00:03,000" in text
        assert "10:00:01" in text
