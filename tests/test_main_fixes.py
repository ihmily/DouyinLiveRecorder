# main.py 并发 / 配置 / 录制路径回归。
# 注意：import main 放到 fixture 中延迟执行——收集阶段会因 src/__init__ 的 node 检查 spawn 子进程
# 而偶发 WinError 6/50，用例执行阶段则稳定。

import subprocess
import sys
import threading
import types
from collections.abc import Mapping
from typing import Any
from unittest.mock import patch

import pytest

from src import web_config

# 与 tests/test_stream_select.py / tests/test_sync_probe_internal_guard.py 同一个公网解析结果
# （示例 IP，只作 DNS seam 的返回值，不参与任何判定规则）。
_PUBLIC_DNS_IP = "93.184.216.34"


@pytest.fixture(scope="module")
def main_mod() -> Any:
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

    def test_safe_int_valid(self, main_mod: Any) -> None:
        # 合法整数字符串原样解析，不被默认值覆盖
        assert main_mod._safe_int("7", 3) == 7

    def test_safe_int_invalid_falls_back(self, main_mod: Any) -> None:
        # 非数字/None/空串等脏配置值一律回落默认 3，防止主循环用 None 做算术而崩
        assert main_mod._safe_int("abc", 3) == 3
        assert main_mod._safe_int(None, 3) == 3
        assert main_mod._safe_int("", 3) == 3

    def test_safe_float_invalid_falls_back(self, main_mod: Any) -> None:
        # 同上：float 解析失败回落默认；解析成功路径与 int 对称
        assert main_mod._safe_float("x", 1.5) == 1.5
        assert main_mod._safe_float("2.5", 1.0) == 2.5


class TestErrorWindow:
    # 错误窗口混合 0/1 采样：错误率可降可升（此前只记 1 导致只能降不能升）.

    def setup_method(self) -> None:
        # 每个用例前清空模块级 error_window（防止 record_error/record_success 跨用例累积污染）。
        import main

        main.error_window.clear()

    def test_window_mixes_success_and_error(self, main_mod: Any) -> None:
        # 混合 0/1 采样：旧实现只记 1 导致错误率只能降不能升；[1,0,0] 验证升降皆可。
        main_mod.record_error()
        main_mod.record_success()
        main_mod.record_success()
        assert list(main_mod.error_window) == [1, 0, 0]
        assert sum(main_mod.error_window) / len(main_mod.error_window) == pytest.approx(1 / 3)

    def test_window_bounded(self, main_mod: Any) -> None:
        # 写入 20 条（远超窗口容量）：旧样本被丢弃，长度恒等于 error_window_size
        # （否则无限增长会拖慢错误率计算并污染长期统计）
        for _ in range(20):
            main_mod.record_error()
        assert len(main_mod.error_window) == main_mod.error_window_size

    def test_error_count_increments(self, main_mod: Any) -> None:
        # 全局错误计数器随 record_error 单调 +1，供错误率背压与熔断统计使用。
        before = main_mod.error_count
        main_mod.record_error()
        assert main_mod.error_count == before + 1


class TestFileUpdateLock:
    def test_file_update_lock_is_reentrant(self, main_mod: Any) -> None:
        # RLock：主循环持锁读配置期间可重入 read_config_value 的写入路径；
        # 同一线程连续两次非阻塞 acquire 都成功（普通 Lock 第二次会死锁）。
        lock = main_mod.file_update_lock
        assert lock.acquire(blocking=False)
        try:
            assert lock.acquire(blocking=False)
            lock.release()
        finally:
            lock.release()


class TestSelectSourceUrl:
    # h265 FLV 无法 copy 录制：启用 HLS 采集且校验通过才切 HLS；关闭时尊重配置.

    @pytest.fixture(autouse=True)
    def _stub_dns_public(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # WP-J（方案 1-A）后，select_source_url 把地址交给 ffmpeg -i 之前要过一次「内网/保留目标」
        # 落地复核（src/stream_select.py 的 _accept_source），非字面量主机名走 DNS seam
        # web_config._resolve_host_ips。本类用例 mock 了 _validate_stream_url、地址又是合成域名
        # cdn.example.com，真解析在无外网环境会 NXDOMAIN → 复核定罪「主机名无法解析」→ 选源返回
        # None（用例假失败，且把「本机有没有 DNS」当成被测行为）。打桩口径沿用
        # src/async_http.py 的 _internal_stream_target_reason 注释里写明的唯一 seam；落地复核自身
        # 的行为锁在 tests/test_sync_probe_internal_guard.py::TestSourceUrlHandoff。
        monkeypatch.setattr(web_config, "_resolve_host_ips", lambda host: [_PUBLIC_DNS_IP])

    def test_h265_flv_uses_hls_when_enabled_and_valid(self, main_mod: Any) -> None:
        # 端到端：h265 FLV 校验通过 + HLS 采集开 → 选源命中 m3u8。
        # [历史注] 原注释「规避 h265 copy 限制」已证伪——h265 在 TS/MKV/MP4 下
        # 已放行进常规序列（_h265_copy_format_supported），此处 m3u8 胜出靠的是默认
        # HLS-first 排序而非 h265 过滤。
        with patch("src.stream_select._validate_stream_url", return_value=True):
            info: Mapping[str, object] = {
                "flv_url": "https://cdn.example.com/live.flv?codec=h265",
                "m3u8_url": "https://cdn.example.com/live.m3u8",
            }
            with patch.object(main_mod, "hls_collection_enabled", True):
                result = main_mod.select_source_url(info)
        assert result == "https://cdn.example.com/live.m3u8"

    def test_h265_flv_skipped_when_hls_disabled(self, main_mod: Any) -> None:
        # 用户关闭 HLS 采集时不再强制切回 HLS；保存格式钉为 FLV（不支持 HEVC 直拷），
        # h265 FLV 被剔除且无 HLS/record_url 可回退 → 本轮 None
        # （TS/MKV/MP4 下 h265 已放行，行为见 tests/test_stream_select.py 放宽矩阵）
        with patch("src.stream_select._validate_stream_url", return_value=True):
            info: Mapping[str, object] = {
                "flv_url": "https://cdn.example.com/live.flv?codec=h265",
                "m3u8_url": "https://cdn.example.com/live.m3u8",
            }
            with (
                patch.object(main_mod, "hls_collection_enabled", False),
                patch.object(main_mod, "video_save_type", "FLV"),
            ):
                result = main_mod.select_source_url(info)
        assert result is None

    def test_h265_flv_hls_unreachable_returns_none(self, main_mod: Any) -> None:
        with patch("src.stream_select._validate_stream_url", return_value=False):
            info: Mapping[str, object] = {
                "flv_url": "https://cdn.example.com/live.flv?codec=h265",
                "m3u8_url": "https://cdn.example.com/live.m3u8",
            }
            with patch.object(main_mod, "hls_collection_enabled", True):
                result = main_mod.select_source_url(info)
        assert result is None

    def test_plain_flv_returned(self, main_mod: Any) -> None:
        # 对照：h264 FLV 不受 h265 限制，HLS 采集开启时仍尊重配置返回 FLV 原文。
        with patch("src.stream_select._validate_stream_url", return_value=True):
            info: Mapping[str, object] = {"flv_url": "https://cdn.example.com/live.flv?codec=h264"}
            with patch.object(main_mod, "hls_collection_enabled", True):
                result = main_mod.select_source_url(info)
        assert result == "https://cdn.example.com/live.flv?codec=h264"


class FakeProcess:
    # 模拟 subprocess.Popen：验证 _run_ffmpeg_checked 的超时终止与退出码处理
    def __init__(self, returncode: int = 0, out: bytes = b"", timeout_on_communicate: bool = False) -> None:
        # timeout_on_communicate 模拟首次 communicate 超时（供 kill 后重读）。
        self.returncode = returncode
        self.out = out
        self.timeout_on_communicate = timeout_on_communicate
        self.killed = False

    def __enter__(self) -> "FakeProcess":
        return self

    def __exit__(self, *exc: Any) -> None:
        return None

    def communicate(self, timeout: int | None = None) -> tuple[object, ...]:
        if self.timeout_on_communicate:
            self.timeout_on_communicate = False  # 仅第一次超时，供 kill 后重读
            raise subprocess.TimeoutExpired(cmd=["ffmpeg"], timeout=timeout or 1)
        return self.out, b""

    def kill(self) -> None:
        # 记录 kill 被调用（验证超时路径确实终止了 ffmpeg 子进程）。
        self.killed = True


def _popen_class_returning(proc: FakeProcess) -> type[Any]:
    # 迁移：Popen 替身必须是**类**且定义 __class_getitem__——本仓 main.check_subprocess
    # 的内层函数注解 subprocess.Popen[bytes] 在 def 时即求值，lambda / 缺该钩子的普通类分别报
    # 'function' object is not subscriptable / type 'X' is not subscriptable（AGENTS.md 硬约定）。
    # __new__ 直接返回预置实例（with subprocess.Popen(...) 拿到的就是它）；每次调用的实参记进
    # popen_calls，替代旧写法的 mock_popen.call_count（断言能力不降）。
    calls: list[tuple[Any, ...]] = []

    class _Popen:
        popen_calls = calls

        def __class_getitem__(cls, item: Any) -> type[Any]:
            return cls

        def __new__(cls, *args: Any, **kwargs: Any) -> Any:
            calls.append((args, kwargs))
            return proc

    return _Popen


def _install_subprocess_shim(module_globals: dict[str, Any], monkeypatch: pytest.MonkeyPatch, popen: type[Any]) -> None:
    # 只替换「真正执行 subprocess 的那个模块命名空间」里的全局引用，绝不改 stdlib 模块本体：
    # 旧写法 patch("subprocess.Popen") 的容器是全进程唯一的 stdlib 模块对象，with 窗口内同进程的
    # harness safe-delete 守卫线程（要求真 Popen 支持上下文管理协议，否则报
    # SAFE_DELETE_BULK_GUARD_ERROR）、loguru enqueue 线程、coverage 全都拿到假实现。
    # vars(subprocess) 浅拷贝保留 PIPE / STDOUT / TimeoutExpired / CalledProcessError 等常量，仅换 Popen。
    shim = types.SimpleNamespace(**vars(subprocess))
    shim.Popen = popen
    monkeypatch.setitem(module_globals, "subprocess", shim)


@pytest.fixture
def ffmpeg_checked_globals(main_mod: Any) -> dict[str, Any]:
    # 替身必须装进 src.video_postprocess 的模块字典，**不是** main 的：`_run_ffmpeg_checked` 定义在
    # src/video_postprocess.py，main.py 只是 re-export，函数的 __globals__ 指向前者。照搬成
    # monkeypatch.setattr(main, "subprocess", shim) 就是**静默 no-op**（假绿）：三条用例会去起真
    # ffmpeg 进程——有 ffmpeg 时靠退出码蒙断言、没有时 FileNotFoundError。故按 __globals__ 取容器
    # 并核对归属，归属一旦变化当场变红而不是悄悄失效。
    module_globals: dict[str, Any] = main_mod._run_ffmpeg_checked.__globals__
    assert module_globals.get("__name__") == "src.video_postprocess"
    return module_globals


class TestRunFfmpegChecked:
    # _run_ffmpeg_checked：超时终止 + 非零退出抛 CalledProcessError（转码不再挂死线程）.
    # 旧实现直接 subprocess.run 阻塞，ffmpeg 卡死会拖垮整个录制线程。

    def test_success_returns_output(
        self, main_mod: Any, ffmpeg_checked_globals: dict[str, Any], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        proc = FakeProcess(returncode=0, out=b"ok output")
        popen = _popen_class_returning(proc)
        _install_subprocess_shim(ffmpeg_checked_globals, monkeypatch, popen)
        out = main_mod._run_ffmpeg_checked(["ffmpeg", "-version"])
        assert "ok output" in out
        assert len(popen.popen_calls) == 1

    def test_failure_raises_called_process_error(
        self, main_mod: Any, ffmpeg_checked_globals: dict[str, Any], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        popen = _popen_class_returning(FakeProcess(returncode=1, out=b"bad"))
        _install_subprocess_shim(ffmpeg_checked_globals, monkeypatch, popen)
        with pytest.raises(subprocess.CalledProcessError):
            main_mod._run_ffmpeg_checked(["ffmpeg", "-this-flag-does-not-exist"])
        # 必须断言替身真被走到：本机真实 ffmpeg 对不存在的参数同样回非零码，于是「shim 装错命名
        # 空间 → 起了真进程」也会让上面那条 raise 通过（变异验证：故意把 shim 装到 main 命名空间时，
        # 另两条变红而本条仍绿；补上这条计数断言后三条全红）。
        assert len(popen.popen_calls) == 1

    def test_timeout_kills_process(
        self, main_mod: Any, ffmpeg_checked_globals: dict[str, Any], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake = FakeProcess(returncode=0, out=b"", timeout_on_communicate=True)
        _install_subprocess_shim(ffmpeg_checked_globals, monkeypatch, _popen_class_returning(fake))
        with pytest.raises(subprocess.TimeoutExpired):
            main_mod._run_ffmpeg_checked(["ffmpeg", "-i", "x"], timeout=1)
        assert fake.killed


class _FakeResponse:
    # 模拟 httpx 响应：默认 200 + 流媒体 content-type（走 video 分支直接判可达）.
    # 仅暴露 status_code/headers，足以驱动 _validate_stream_url 的 HEAD 判定。
    def __init__(self, status_code: int = 200, headers: dict | None = None) -> None:
        self.status_code = status_code
        self.headers = headers or {}


class _FakeStreamResponse:
    # 模拟 httpx stream 响应（GET 复核用）：只暴露状态码，不读 body.
    def __init__(self, status_code: int = 206) -> None:
        self.status_code = status_code

    def __enter__(self) -> "_FakeStreamResponse":
        return self

    def __exit__(self, *exc: Any) -> None:
        return None


class _RecordingClient:
    # 记录 httpx.Client 构造时的关键字参数（含 headers），用于断言 Referer 注入.
    # last_kwargs 跨用例累积，故每个用例新建实例以隔离请求头断言。
    last_kwargs: dict = {}

    def __init__(self, **kwargs: Any) -> None:
        _RecordingClient.last_kwargs = kwargs
        self.stream_status = 206
        self.last_stream_kwargs: dict = {}

    def __enter__(self) -> "_RecordingClient":
        return self

    def __exit__(self, *exc: Any) -> None:
        return None

    def head(self, url: Any, **_kw: Any) -> _FakeResponse:
        return _FakeResponse(200, {"content-type": "video/x-flv"})

    def get(self, url: Any, **_kw: Any) -> _FakeResponse:
        return _FakeResponse(200, {"content-type": "video/x-flv"})

    def stream(self, method: Any, url: Any, **kw: Any) -> _FakeStreamResponse:
        # GET 复核默认 206；测试可改 stream_status 模拟 403 等，last_stream_kwargs 供请求头断言
        self.last_stream_kwargs = kw
        return _FakeStreamResponse(self.stream_status)


class _SequenceStreamClient(_RecordingClient):
    # GET 复核按序返回状态码：模拟「首探 403、重试 200」的偶发拒绝与「两次 403」的稳定拒绝.
    def __init__(self, statuses: list[int]) -> None:
        super().__init__()
        self._statuses = statuses
        self.stream_calls = 0

    def stream(self, method: Any, url: Any, **kw: Any) -> _FakeStreamResponse:
        # 按调用次数取预设状态码；超出长度则钳到末位（稳定拒绝场景复用末状态）。
        status = self._statuses[min(self.stream_calls, len(self._statuses) - 1)]
        self.stream_calls += 1
        self.last_stream_kwargs = kw
        return _FakeStreamResponse(status)


class TestHuyaReferer:
    # 虎牙 CDN 现已反向校验：携带 Referer(https://www.huya.com/) 一律 403，不携带 Referer 时
    # HS 线路 GET 200 正常拉流。故 get_record_headers 对虎牙【不得】下发 Referer，且
    # _validate_stream_url 必须按 platform 透传（即不附加 Referer），否则校验误判不可达、
    # ffmpeg 同样拿不到流。

    def test_get_record_headers_returns_no_huya_referer(self, main_mod: Any) -> None:
        headers = main_mod.get_record_headers("虎牙直播", "https://www.huya.com/660002")
        assert headers is None or "referer" not in headers

    def test_validate_with_huya_platform_sends_no_referer(self, main_mod: Any) -> None:
        with patch("src.stream_select.httpx.Client", _RecordingClient):
            ok = main_mod._validate_stream_url(
                "http://hs-game.flv.huya.com/src/x.flv?wsSecret=1&wsTime=2",
                platform="虎牙直播",
            )
        assert ok is True
        headers = _RecordingClient.last_kwargs.get("headers") or {}
        assert "referer" not in headers

    def test_validate_without_platform_sends_no_referer(self, main_mod: Any) -> None:
        with patch("src.stream_select.httpx.Client", _RecordingClient):
            ok = main_mod._validate_stream_url("http://example.com/x.flv")
        assert ok is True
        headers = _RecordingClient.last_kwargs.get("headers")
        assert headers is None or "referer" not in headers


class TestFlvGetConfirm:
    # 回归：虎牙 al.flv.huya.com 出现过 HEAD=200 而 GET=403（校验假绿，ffmpeg 打开即 403）。
    # 修复：FLV/record_url HEAD 判定通过后必须做流式 Range GET 复核，401/403 才推翻结论。

    def test_head_ok_get_403_returns_false(self, main_mod: Any) -> None:
        # 回归：HEAD=200 但 GET 复核 403（校验假绿）必须推翻结论返回 False。
        client = _RecordingClient()
        client.stream_status = 403
        with patch("src.stream_select.httpx.Client", return_value=client), patch("src.stream_select.time.sleep"):
            ok = main_mod._validate_stream_url("http://al.flv.huya.com/src/x.flv")
        assert ok is False

    def test_head_ok_get_206_returns_true(self, main_mod: Any) -> None:
        client = _RecordingClient()
        client.stream_status = 206
        with patch("src.stream_select.httpx.Client", return_value=client):
            ok = main_mod._validate_stream_url("http://al.flv.huya.com/src/x.flv")
        assert ok is True

    def test_get_confirm_error_keeps_head_verdict(self, main_mod: Any) -> None:
        # GET 复核网络异常（超时等）不推翻 HEAD 结论，避免误杀可用源
        client = _RecordingClient()

        def _raise_stream(method: Any, url: Any, **_kw: Any) -> None:
            raise OSError("timeout")

        client.stream = _raise_stream  # type: ignore[method-assign,assignment]
        with patch("src.stream_select.httpx.Client", return_value=client):
            ok = main_mod._validate_stream_url("http://al.flv.huya.com/src/x.flv")
        assert ok is True

    def test_get_confirm_sends_no_range_header(self, main_mod: Any) -> None:
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

    def test_first_403_retry_200_passes(self, main_mod: Any) -> None:
        # 偶发拒绝：首探 403、重试 200 → 判可达，且必须真的发了第二次复核
        # （stream_calls==2 证明重试确实发生，而非首探即定罪）。
        client = _SequenceStreamClient([403, 200])
        with patch("src.stream_select.httpx.Client", return_value=client), patch("src.stream_select.time.sleep"):
            ok = main_mod._validate_stream_url("https://hw1a.douyucdn2.cn/live/100rPCLP.flv?wsAuth=1")
        assert ok is True
        assert client.stream_calls == 2

    def test_stable_403_retries_once_then_rejects(self, main_mod: Any) -> None:
        # 稳定拒绝：两次 403 → 判不可达（非末位候选时否决，继续回退备选源）
        client = _SequenceStreamClient([403, 403])
        with patch("src.stream_select.httpx.Client", return_value=client), patch("src.stream_select.time.sleep"):
            ok = main_mod._validate_stream_url("https://al.flv.huya.com/src/x.flv")
        assert ok is False
        assert client.stream_calls == 2

    def test_stable_403_last_resort_passes_with_warning(self, main_mod: Any) -> None:
        # 末位候选：稳定 403 也不否决（探针与 ffmpeg 客户端指纹不同），仅告警放行
        # 告警文案须含「仍交由 ffmpeg 尝试」，便于运维识别末位兜底放行。
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

    def test_flv_only_stable_403_still_selected(self, main_mod: Any) -> None:
        # 端到端：仅 FLV 一档候选且复核稳定 403 → 仍选中该 URL 交给 ffmpeg
        client = _SequenceStreamClient([403, 403])
        url = "https://hw1a.douyucdn2.cn/live/100rPCLP.flv?wsAuth=1"
        with patch("src.stream_select.httpx.Client", return_value=client), patch("src.stream_select.time.sleep"):
            result = main_mod.select_source_url({"flv_url": url})
        assert result == url

    def test_flv_not_last_resort_when_record_url_exists(self, main_mod: Any) -> None:
        # 有 record_url 备选时 FLV 复核否决生效（last_resort=False），回退链保持
        calls: list[tuple[str, bool]] = []

        def _fake_validate(url: Any, **kw: Any) -> bool:
            calls.append((url, kw.get("last_resort", False)))
            return False

        with patch("src.stream_select._validate_stream_url", side_effect=_fake_validate):
            result = main_mod.select_source_url({"flv_url": "https://x/a.flv", "record_url": "https://x/b.flv"})
        assert result is None
        assert calls == [("https://x/a.flv", False), ("https://x/b.flv", True)]

    def test_flv_alone_validated_as_last_resort(self, main_mod: Any) -> None:
        calls: list[tuple[str, bool]] = []

        def _fake_validate(url: Any, **kw: Any) -> bool:
            calls.append((url, kw.get("last_resort", False)))
            return False

        with patch("src.stream_select._validate_stream_url", side_effect=_fake_validate):
            main_mod.select_source_url({"flv_url": "https://x/a.flv"})
        assert calls == [("https://x/a.flv", True)]


class TestSelectSourceUrlEmpty:
    # 回归：斗鱼 rtmp_live 为空时返回 is_live=True 但三类 URL 全空，
    # 旧逻辑静默 None → 房间永远“正在直播中...”却不录制且无诊断线索。

    def test_all_urls_empty_returns_none_with_warning(self, main_mod: Any) -> None:
        # 告警文案须能让运维定位（三类 URL 全空 / HLS 采集未启用）
        info: Mapping[str, object] = {"anchor_name": "王者荣耀官方赛事", "is_live": True}
        with patch.object(main_mod, "hls_collection_enabled", True), patch("src.stream_select.logger.warning") as warn:
            result = main_mod.select_source_url(info)
        assert result is None
        assert any("均为空" in str(c.args[0]) for c in warn.call_args_list)

    def test_hls_present_but_collection_disabled_no_fallback_warns(self, main_mod: Any) -> None:
        # m3u8 存在但 HLS 采集关闭、且无 flv/record_url 回退 → 此前静默 None
        info: Mapping[str, object] = {"anchor_name": "坤记喜事多", "is_live": True, "m3u8_url": "https://x/abc.m3u8"}
        with patch.object(main_mod, "hls_collection_enabled", False), patch("src.stream_select.logger.warning") as warn:
            result = main_mod.select_source_url(info)
        assert result is None
        assert any("HLS 采集未启用" in str(c.args[0]) for c in warn.call_args_list)
