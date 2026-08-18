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
        with patch("src.stream_select._validate_stream_url", return_value=True):
            info: Mapping[str, object] = {
                "flv_url": "https://cdn.example.com/live.flv?codec=h265",
                "m3u8_url": "https://cdn.example.com/live.m3u8",
            }
            with patch.object(main_mod, "hls_collection_enabled", True):
                result = main_mod.select_source_url(info)
        assert result == "https://cdn.example.com/live.m3u8"

    def test_h265_flv_skipped_when_hls_disabled(self, main_mod):
        # 用户关闭 HLS 采集时不再强制切回 HLS
        with patch("src.stream_select._validate_stream_url", return_value=True):
            info: Mapping[str, object] = {
                "flv_url": "https://cdn.example.com/live.flv?codec=h265",
                "m3u8_url": "https://cdn.example.com/live.m3u8",
            }
            with patch.object(main_mod, "hls_collection_enabled", False):
                result = main_mod.select_source_url(info)
        assert result is None

    def test_h265_flv_hls_unreachable_returns_none(self, main_mod):
        with patch("src.stream_select._validate_stream_url", return_value=False):
            info: Mapping[str, object] = {
                "flv_url": "https://cdn.example.com/live.flv?codec=h265",
                "m3u8_url": "https://cdn.example.com/live.m3u8",
            }
            with patch.object(main_mod, "hls_collection_enabled", True):
                result = main_mod.select_source_url(info)
        assert result is None

    def test_plain_flv_returned(self, main_mod):
        with patch("src.stream_select._validate_stream_url", return_value=True):
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


class _FakeResponse:
    # 模拟 httpx 响应：默认 200 + 流媒体 content-type（走 video 分支直接判可达）.
    def __init__(self, status_code: int = 200, headers: dict | None = None):
        self.status_code = status_code
        self.headers = headers or {}


class _FakeStreamResponse:
    # 模拟 httpx stream 响应（GET 复核用）：只暴露状态码，不读 body.
    def __init__(self, status_code: int = 206):
        self.status_code = status_code

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class _RecordingClient:
    # 记录 httpx.Client 构造时的关键字参数（含 headers），用于断言 Referer 注入.
    last_kwargs: dict = {}

    def __init__(self, **kwargs):
        _RecordingClient.last_kwargs = kwargs
        self.stream_status = 206
        self.last_stream_kwargs: dict = {}

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def head(self, url, **_kw):
        return _FakeResponse(200, {"content-type": "video/x-flv"})

    def get(self, url, **_kw):
        return _FakeResponse(200, {"content-type": "video/x-flv"})

    def stream(self, method, url, **kw):
        # GET 复核默认 206；测试可改 stream_status 模拟 403 等，last_stream_kwargs 供请求头断言
        self.last_stream_kwargs = kw
        return _FakeStreamResponse(self.stream_status)


class _SequenceStreamClient(_RecordingClient):
    # GET 复核按序返回状态码：模拟「首探 403、重试 200」的偶发拒绝与「两次 403」的稳定拒绝.
    def __init__(self, statuses: list[int]):
        super().__init__()
        self._statuses = statuses
        self.stream_calls = 0

    def stream(self, method, url, **kw):
        status = self._statuses[min(self.stream_calls, len(self._statuses) - 1)]
        self.stream_calls += 1
        self.last_stream_kwargs = kw
        return _FakeStreamResponse(status)


class TestHuyaReferer:
    # 虎牙 CDN 现已反向校验：携带 Referer(https://www.huya.com/) 一律 403，不携带 Referer 时
    # HS 线路 GET 200 正常拉流。故 get_record_headers 对虎牙【不得】下发 Referer，且
    # _validate_stream_url 必须按 platform 透传（即不附加 Referer），否则校验误判不可达、
    # ffmpeg 同样拿不到流。

    def test_get_record_headers_returns_no_huya_referer(self, main_mod):
        headers = main_mod.get_record_headers("虎牙直播", "https://www.huya.com/660002")
        assert headers is None or "referer" not in headers

    def test_validate_with_huya_platform_sends_no_referer(self, main_mod):
        with patch("src.stream_select.httpx.Client", _RecordingClient):
            ok = main_mod._validate_stream_url(
                "http://hs-game.flv.huya.com/src/x.flv?wsSecret=1&wsTime=2",
                platform="虎牙直播",
            )
        assert ok is True
        headers = _RecordingClient.last_kwargs.get("headers") or {}
        assert "referer" not in headers

    def test_validate_without_platform_sends_no_referer(self, main_mod):
        with patch("src.stream_select.httpx.Client", _RecordingClient):
            ok = main_mod._validate_stream_url("http://example.com/x.flv")
        assert ok is True
        headers = _RecordingClient.last_kwargs.get("headers")
        assert headers is None or "referer" not in headers


class TestFlvGetConfirm:
    # 回归：虎牙 al.flv.huya.com 出现过 HEAD=200 而 GET=403（校验假绿，ffmpeg 打开即 403）。
    # 修复：FLV/record_url HEAD 判定通过后必须做流式 Range GET 复核，401/403 才推翻结论。

    def test_head_ok_get_403_returns_false(self, main_mod):
        client = _RecordingClient()
        client.stream_status = 403
        with patch("src.stream_select.httpx.Client", return_value=client), patch("src.stream_select.time.sleep"):
            ok = main_mod._validate_stream_url("http://al.flv.huya.com/src/x.flv")
        assert ok is False

    def test_head_ok_get_206_returns_true(self, main_mod):
        client = _RecordingClient()
        client.stream_status = 206
        with patch("src.stream_select.httpx.Client", return_value=client):
            ok = main_mod._validate_stream_url("http://al.flv.huya.com/src/x.flv")
        assert ok is True

    def test_get_confirm_error_keeps_head_verdict(self, main_mod):
        # GET 复核网络异常（超时等）不推翻 HEAD 结论，避免误杀可用源
        client = _RecordingClient()

        def _raise_stream(method, url, **_kw):
            raise OSError("timeout")

        client.stream = _raise_stream  # type: ignore[method-assign]
        with patch("src.stream_select.httpx.Client", return_value=client):
            ok = main_mod._validate_stream_url("http://al.flv.huya.com/src/x.flv")
        assert ok is True

    def test_get_confirm_sends_no_range_header(self, main_mod):
        # 回归：斗鱼 hwa CDN 对 Range-GET 偶发 403 而无 Range GET 正常（实测）。
        # ffmpeg 拉流是「无 Range 的全量 GET」，复核请求禁止携带 Range 头。
        client = _RecordingClient()
        with patch("src.stream_select.httpx.Client", return_value=client):
            ok = main_mod._validate_stream_url("http://al.flv.huya.com/src/x.flv")
        assert ok is True
        headers = client.last_stream_kwargs.get("headers")
        assert not headers or "Range" not in headers


class TestGetConfirmRetry:
    # 回归：斗鱼 hw/虎牙 al CDN 对毫秒级连击探针（HEAD→GET）偶发 403（实测同 URL 片刻后
    # 重试即 200，ffmpeg 单次 GET 正常）。修复：401/403 先原样重试一次再定罪；
    # 稳定拒绝且已是末位候选（无备选源）时仅告警放行，交由 ffmpeg 实际拉流定夺。

    def test_first_403_retry_200_passes(self, main_mod):
        # 偶发拒绝：首探 403、重试 200 → 判可达，且必须真的发了第二次复核
        client = _SequenceStreamClient([403, 200])
        with patch("src.stream_select.httpx.Client", return_value=client), patch("src.stream_select.time.sleep"):
            ok = main_mod._validate_stream_url("https://hw1a.douyucdn2.cn/live/100rPCLP.flv?wsAuth=1")
        assert ok is True
        assert client.stream_calls == 2

    def test_stable_403_retries_once_then_rejects(self, main_mod):
        # 稳定拒绝：两次 403 → 判不可达（非末位候选时否决，继续回退备选源）
        client = _SequenceStreamClient([403, 403])
        with patch("src.stream_select.httpx.Client", return_value=client), patch("src.stream_select.time.sleep"):
            ok = main_mod._validate_stream_url("https://al.flv.huya.com/src/x.flv")
        assert ok is False
        assert client.stream_calls == 2

    def test_stable_403_last_resort_passes_with_warning(self, main_mod):
        # 末位候选：稳定 403 也不否决（探针与 ffmpeg 客户端指纹不同），仅告警放行
        client = _SequenceStreamClient([403, 403])
        with (
            patch("src.stream_select.httpx.Client", return_value=client),
            patch("src.stream_select.time.sleep"),
            patch("src.stream_select.logger.warning") as warn,
        ):
            ok = main_mod._validate_stream_url("https://hw1a.douyucdn2.cn/live/100rPCLP.flv", last_resort=True)
        assert ok is True
        assert any("仍交由 ffmpeg 尝试" in str(c.args[0]) for c in warn.call_args_list)


class TestSelectSourceUrlLastResort:
    # select_source_url 的末位候选判定：flv 在无 record_url 时、record_url 恒为 last_resort。

    def test_flv_only_stable_403_still_selected(self, main_mod):
        # 端到端：仅 FLV 一档候选且复核稳定 403 → 仍选中该 URL 交给 ffmpeg
        client = _SequenceStreamClient([403, 403])
        url = "https://hw1a.douyucdn2.cn/live/100rPCLP.flv?wsAuth=1"
        with patch("src.stream_select.httpx.Client", return_value=client), patch("src.stream_select.time.sleep"):
            result = main_mod.select_source_url({"flv_url": url})
        assert result == url

    def test_flv_not_last_resort_when_record_url_exists(self, main_mod):
        # 有 record_url 备选时 FLV 复核否决生效（last_resort=False），回退链保持
        calls: list[tuple[str, bool]] = []

        def _fake_validate(url, **kw):
            calls.append((url, kw.get("last_resort", False)))
            return False

        with patch("src.stream_select._validate_stream_url", side_effect=_fake_validate):
            result = main_mod.select_source_url({"flv_url": "https://x/a.flv", "record_url": "https://x/b.flv"})
        assert result is None
        assert calls == [("https://x/a.flv", False), ("https://x/b.flv", True)]

    def test_flv_alone_validated_as_last_resort(self, main_mod):
        calls: list[tuple[str, bool]] = []

        def _fake_validate(url, **kw):
            calls.append((url, kw.get("last_resort", False)))
            return False

        with patch("src.stream_select._validate_stream_url", side_effect=_fake_validate):
            main_mod.select_source_url({"flv_url": "https://x/a.flv"})
        assert calls == [("https://x/a.flv", True)]


class TestSelectSourceUrlEmpty:
    # 回归：斗鱼 rtmp_live 为空时返回 is_live=True 但三类 URL 全空，
    # 旧逻辑静默 None → 房间永远“正在直播中...”却不录制且无诊断线索。

    def test_all_urls_empty_returns_none_with_warning(self, main_mod):
        info: Mapping[str, object] = {"anchor_name": "王者荣耀官方赛事", "is_live": True}
        with patch.object(main_mod, "hls_collection_enabled", True), patch("src.stream_select.logger.warning") as warn:
            result = main_mod.select_source_url(info)
        assert result is None
        assert any("均为空" in str(c.args[0]) for c in warn.call_args_list)

    def test_hls_present_but_collection_disabled_no_fallback_warns(self, main_mod):
        # 回归：m3u8 存在但 HLS 采集关闭、且无 flv/record_url 回退 → 此前静默 None。
        info: Mapping[str, object] = {"anchor_name": "坤记喜事多", "is_live": True, "m3u8_url": "https://x/abc.m3u8"}
        with patch.object(main_mod, "hls_collection_enabled", False), patch("src.stream_select.logger.warning") as warn:
            result = main_mod.select_source_url(info)
        assert result is None
        assert any("HLS 采集未启用" in str(c.args[0]) for c in warn.call_args_list)
