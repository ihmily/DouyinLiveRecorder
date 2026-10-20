# converts_mp4 半成品产物与超时放大回归（CODE_REVIEW_2026-09-20 的 MIN-04）。
#
# 全部离线：ffmpeg 由 _run_ffmpeg_checked 的替身模拟，不启动真实进程。
#
# 锁定的不变量：
#   ① 失败/超时后必须删除**本次调用生成**的半截 .mp4（重编码路径无 +faststart，
#      被杀后 moov 缺失、完全不可播），并明确「源文件已保留」；
#   ② 调用前同名 .mp4 已存在时不得删（那可能是上一次的成功产物）；
#   ③ 默认超时随源文件体积线性放大（固定 600s 对 1800s 分段的重编码不够），
#      显式传入的 timeout 优先。

import subprocess
import types
from pathlib import Path
from typing import Any

import pytest

import main
import src.video_postprocess as vp


@pytest.fixture(autouse=True)
def _stub_main_globals(monkeypatch: pytest.MonkeyPatch) -> Any:
    # converts_mp4 运行时读取 main 的两个全局：把「是否重编码」与彩色输出对象打桩，
    # 避免依赖真实 config.ini 与控制台（AGENTS：不 patch stdlib 模块本体，只换属性）
    monkeypatch.setattr(main, "converts_to_h264", False, raising=False)

    class _Color:
        YELLOW = ""

        def print_colored(self, *args: Any, **kwargs: Any) -> None:
            return None

    monkeypatch.setattr(main, "color_obj", _Color(), raising=False)
    yield


def _make_source(tmp_path: Path, size: int = 32) -> Path:
    src = tmp_path / "live_000.ts"
    src.write_bytes(b"\x47" * size)
    return src


def _install_runner(
    monkeypatch: pytest.MonkeyPatch,
    out_path: Path,
    error: BaseException | None,
    write_partial: bool = True,
) -> dict[str, Any]:
    recorded: dict[str, Any] = {}

    def _fake_run(command: list[str], timeout: int = 600) -> str:
        recorded["timeout"] = timeout
        recorded["command"] = command
        if write_partial:
            # 模拟 ffmpeg 已经写了一半输出（大小可观但不可播）
            out_path.write_bytes(b"ftyp-partial" * 64)
        if error is not None:
            raise error
        out_path.write_bytes(b"complete-mp4")
        return ""

    monkeypatch.setattr(vp, "_run_ffmpeg_checked", _fake_run)
    return recorded


def test_partial_output_deleted_on_timeout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    src = _make_source(tmp_path)
    out = tmp_path / "live_000.mp4"
    err = subprocess.TimeoutExpired(cmd=["ffmpeg"], timeout=1)
    recorded = _install_runner(monkeypatch, out, err)

    vp.converts_mp4(str(src), is_original_delete=True, timeout=1)

    assert not out.exists(), "超时后仍留下半成品 .mp4（无 moov、不可播）"
    assert src.exists(), "源文件必须保留（is_original_delete 分支未走到）"
    assert recorded["timeout"] == 1


def test_pre_existing_output_not_deleted(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # 同名 .mp4 在本次调用前就存在 → 不删：本次只是覆盖失败，删掉等于毁掉可用产物
    src = _make_source(tmp_path)
    out = tmp_path / "live_000.mp4"
    out.write_bytes(b"previous-good-file")
    err = subprocess.CalledProcessError(returncode=1, cmd=["ffmpeg"])
    _install_runner(monkeypatch, out, err)

    vp.converts_mp4(str(src), is_original_delete=False, timeout=1)

    assert out.exists()
    assert src.exists()


def test_partial_output_deleted_on_nonzero_exit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    src = _make_source(tmp_path)
    out = tmp_path / "live_000.mp4"
    err = subprocess.CalledProcessError(returncode=1, cmd=["ffmpeg"])
    _install_runner(monkeypatch, out, err)

    vp.converts_mp4(str(src), is_original_delete=False, timeout=1)

    assert not out.exists()
    assert src.exists()


def test_success_keeps_output_and_deletes_source(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    src = _make_source(tmp_path)
    out = tmp_path / "live_000.mp4"
    _install_runner(monkeypatch, out, None)
    # 跳过删源前的 1s 等待。**必须**用浅拷贝 shim：vp.time 就是 stdlib time 模块本体，
    # 直接 monkeypatch.setattr(vp.time, "sleep", ...) 会替换全进程 sleep（AGENTS 明令禁止）
    time_shim = types.SimpleNamespace(**vars(vp.time))
    time_shim.sleep = lambda _s: None
    monkeypatch.setattr(vp, "time", time_shim)

    vp.converts_mp4(str(src), is_original_delete=True, timeout=60)

    assert out.exists()
    assert not src.exists()


def test_default_timeout_scales_with_source_size(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # 重编码：1.5 s/MB；600s 下限、_MAX_CONVERT_TIMEOUT 上限（稀疏文件，不实际写盘）
    big = tmp_path / "big.ts"
    with open(big, "wb") as fh:
        fh.truncate(1000 * vp._MB)
    scaled = vp._convert_timeout(str(big), re_encoding=True, explicit=None)
    assert 600 < scaled < vp._MAX_CONVERT_TIMEOUT
    assert abs(scaled - int(1000 * vp._REENCODE_SECONDS_PER_MB)) <= 1
    # 小文件仍走 600s 下限（放大只会变长不会变短）
    small = _make_source(tmp_path)
    assert vp._convert_timeout(str(small), re_encoding=True, explicit=None) == 600
    # 转封装（-c copy）口径远小于重编码：1000MB × 0.04s = 40s → 仍取下限
    assert vp._convert_timeout(str(big), re_encoding=False, explicit=None) == 600
    # 上限封顶 + 显式值优先
    monkeypatch.setattr(vp, "_MAX_CONVERT_TIMEOUT", 1000)
    assert vp._convert_timeout(str(big), re_encoding=True, explicit=None) == 1000
    assert vp._convert_timeout(str(small), re_encoding=True, explicit=42) == 42
