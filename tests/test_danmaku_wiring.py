# 弹幕录制集成测试（离线，不依赖网络/真实 ffmpeg）。
#
# 覆盖 danmaku_check.md 审查报告的修复回归：
# 1. check_subprocess 收到 platform/danmaku_args 并按预期启停弹幕采集器（接线回归）
# 2. ffmpeg 正常退出时 stop() 在轮询循环外恰好执行一次（非每次迭代）
# 3. SRT 基名剥离 _%02d/_%03d 占位符，分片文件名与 ffmpeg 三位宽度对齐
# 4. 提前中断（URL 被注释）场景弹幕正确停止并终止 ffmpeg
# 5. DanmakuCollector.stop() 幂等（防重入）
# 6. 抖音弹幕空 cookie 时经 get_ttwid 动态获取（不再硬编码过期凭据）

import subprocess
import sys
import types
from collections.abc import Generator
from pathlib import Path
from typing import Any, cast
from unittest.mock import MagicMock

import pytest

from src.collector import DanmakuCollector
from src.srt_writer import SrtWriter


@pytest.fixture(scope="module")
def main_mod() -> Generator[Any, None, None]:
    # main.py 的 _app_root() 基于 sys.argv[0] 定位 config/，pytest 下 argv[0] 指向 pytest 自身，
    # 需在导入前修正为项目 main.py（与 tests/test_main_fixes.py 同一模式）。
    old_argv = sys.argv[:]
    sys.argv = [str(Path(__file__).resolve().parent.parent / "main.py")]
    try:
        import main

        yield main
    finally:
        sys.argv = old_argv


def _make_subprocess_shim(poll_results: list[int | None]) -> types.SimpleNamespace:
    # 构造 main 模块级 subprocess 引用的替身（只换 main.subprocess 全局引用，不污染 stdlib——
    # 直接 patch stdlib Popen 会波及同进程 harness 守护线程的 subprocess.run）。
    # AGENTS.md 约定：patch main.py 的 subprocess 必须替换 main 的全局引用，不能改 stdlib 模块本体。
    # Popen 必须是类：check_subprocess 内层函数注解 subprocess.Popen[bytes] 在 def 时求值，
    # 故需 __class_getitem__；poll 按给定序列返回，耗尽后视为已退出（返回 0）。

    class _FakePopen:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            # poll 序列转为可变列表，逐次 pop 模拟「还在录 / 已退出」的轮询过程。
            self._poll_results = list(poll_results)
            self.returncode = 0

        def __class_getitem__(cls, item: Any) -> Any:
            return cls

        def poll(self) -> int | None:
            if self._poll_results:
                return self._poll_results.pop(0)
            return 0

        def wait(self, timeout: int = 0) -> int:
            return 0

    # 浅拷贝 stdlib subprocess 全部属性，仅覆盖 Popen（STARTUPINFO/PIPE/CalledProcessError 等保持真实）
    shim = types.SimpleNamespace(**vars(subprocess))
    shim.Popen = _FakePopen
    return shim


def _setup_common(monkeypatch: pytest.MonkeyPatch, main: Any, poll_results: list) -> MagicMock:
    # 装配 check_subprocess 运行所需的全部外部依赖 mock，返回弹幕工厂 Mock。
    # poll_results 是 FakePopen.poll() 的逐次返回值序列：None 表示「还在录」（循环继续），
    # 0 表示 ffmpeg 已退出（结束录制）。如 [None, None, None, 0] 模拟 3 轮轮询后自然结束，
    # [0] 模拟启动即退，[None] 模拟一直录（配合 url_comments 触发提前中断）。
    # 默认开录制弹幕、关监控；平台仅抖音直播，便于各用例按需覆写开关验证分支。
    monkeypatch.setattr(main, "enable_danmaku", True)
    monkeypatch.setattr(main, "enable_danmaku_monitor", False)
    monkeypatch.setattr(main, "danmaku_platforms", ["抖音直播"])
    # 1800.0 = 默认 30 分钟分段阈值：决定采集器是否启用按时间分片（segment_seconds 非 None）。
    # 该值经 _setup_common 注入后，会原样透传给 get_danmaku_collector 的 segment_seconds 参数。
    monkeypatch.setattr(main, "danmaku_split_time", 1800.0)
    # 关闭时间文件/转 mp4/退出录制等副作用开关，聚焦弹幕接线而非后处理；url_comments 置空（无提前中断）。
    monkeypatch.setattr(main, "create_time_file", False)
    monkeypatch.setattr(main, "converts_to_mp4", False)
    monkeypatch.setattr(main, "exit_recording", False)
    monkeypatch.setattr(main, "url_comments", set())
    # 注册/注销 ffmpeg 进程为无操作（真实实现会写入全局守护列表，测试无需）。
    monkeypatch.setattr(main, "register_ffmpeg_process", lambda proc: None)
    monkeypatch.setattr(main, "unregister_ffmpeg_process", lambda proc: None)
    monkeypatch.setattr(main.time, "sleep", lambda seconds: None)  # 轮询不等真实 1 秒
    monkeypatch.setattr(main, "subprocess", _make_subprocess_shim(poll_results))

    factory = MagicMock(name="get_danmaku_collector")
    factory.return_value = MagicMock(name="danmaku_collector")
    monkeypatch.setattr(main, "get_danmaku_collector", factory)
    return factory


def test_wiring_starts_collector_with_platform_and_args(main_mod: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    # 接线回归：platform/danmaku_args 必须送达弹幕工厂，采集器随 ffmpeg 启动。
    main = main_mod
    # 开启按时间分片：segment_seconds 由 danmaku_split_time(1800) 注入，SRT 按分段落盘。
    monkeypatch.setattr(main, "split_video_by_time", True)
    factory = _setup_common(monkeypatch, main, [0])

    save_path = "/tmp/主播名_2026-08-16_10-00-00_%03d.ts"
    result = main.check_subprocess(
        "主播名",
        "https://live.douyin.com/123456",
        ["ffmpeg", "-i", "x", save_path],
        "TS",
        None,
        platform="抖音直播",
        danmaku_args={"room_id": "999"},
    )

    assert result is False
    # 弹幕工厂应收到：platform/danmaku_args、剥离 _%03d 的基名、segment_seconds=1800、write_srt=True。
    factory.assert_called_once_with(
        platform="抖音直播",
        danmaku_args={"room_id": "999"},
        base_filename="/tmp/主播名_2026-08-16_10-00-00",
        segment_seconds=1800.0,
        room_name="主播名",
        write_srt=True,
    )
    collector = factory.return_value
    assert collector.start.call_count == 1


def test_monitor_only_mode_skips_srt(main_mod: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    # 弹幕监控独立开关回归：录制弹幕关、弹幕监控开时仍创建采集器（write_srt=False），
    # 且房间名（监控显示名）正确透传。
    main = main_mod
    monkeypatch.setattr(main, "split_video_by_time", False)
    factory = _setup_common(monkeypatch, main, [0])
    monkeypatch.setattr(main, "enable_danmaku", False)
    monkeypatch.setattr(main, "enable_danmaku_monitor", True)
    # 仅开监控开关：验证采集器仍被创建（write_srt=False），监控显示名正确透传。
    result = main.check_subprocess(
        "主播名",
        "https://live.douyin.com/123456",
        ["ffmpeg", "-i", "x", "/tmp/主播名_2026-08-16_10-00-00.ts"],
        "TS",
        None,
        platform="抖音直播",
        danmaku_args={"room_id": "999"},
    )

    assert result is False
    factory.assert_called_once_with(
        platform="抖音直播",
        danmaku_args={"room_id": "999"},
        base_filename="/tmp/主播名_2026-08-16_10-00-00",
        segment_seconds=None,
        room_name="主播名",
        write_srt=False,
    )


def test_no_danmaku_when_both_switches_off(main_mod: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    # 双开关全关时不创建采集器（不建立弹幕连接）。
    main = main_mod
    monkeypatch.setattr(main, "split_video_by_time", False)
    factory = _setup_common(monkeypatch, main, [0])
    monkeypatch.setattr(main, "enable_danmaku", False)
    monkeypatch.setattr(main, "enable_danmaku_monitor", False)

    result = main.check_subprocess(
        "主播名",
        "https://live.douyin.com/123456",
        ["ffmpeg", "-i", "x", "/tmp/主播名_2026-08-16_10-00-00.ts"],
        "TS",
        None,
        platform="抖音直播",
        danmaku_args={"room_id": "999"},
    )

    assert result is False
    # 双开关全关：不创建采集器、不建立弹幕连接，录制流程完全跳过弹幕路径。
    factory.assert_not_called()


def test_stop_called_once_after_loop_not_per_iteration(main_mod: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    # stop 位置回归：轮询 3 轮后 ffmpeg 自然退出，stop() 必须恰好调用一次
    # （修复前 stop 在循环体内，此场景会被调用 3 次，弹幕 1 秒即被终止）。
    main = main_mod
    monkeypatch.setattr(main, "split_video_by_time", False)
    factory = _setup_common(monkeypatch, main, [None, None, None, 0])

    result = main.check_subprocess(
        "主播名",
        "https://live.douyin.com/123456",
        ["ffmpeg", "-i", "x", "/tmp/主播名_2026-08-16_10-00-00.ts"],
        "TS",
        None,
        platform="抖音直播",
        danmaku_args={"room_id": "999"},
    )

    assert result is False
    collector = factory.return_value
    # 轮询 3 轮后 ffmpeg 自然退出，stop() 在循环外恰好一次（修复前在循环体内被调 3 次）。
    assert collector.stop.call_count == 1, "ffmpeg 正常退出时 stop() 应在循环外恰好执行一次"


def test_srt_base_strips_02d_and_03d_placeholders(main_mod: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    # 占位符剥离回归：_%02d(音频/历史 FLV) 与 _%03d(视频分段) 都必须从 SRT 基名剥除。
    main = main_mod
    monkeypatch.setattr(main, "split_video_by_time", True)

    for template in ("_%02d.flv", "_%03d.ts"):
        factory = _setup_common(monkeypatch, main, [0])
        main.check_subprocess(
            "主播名",
            "https://live.douyin.com/123456",
            ["ffmpeg", "-i", "x", f"/tmp/主播名_now{template}"],
            "TS",
            None,
            platform="抖音直播",
            danmaku_args={"room_id": "999"},
        )
        base = factory.call_args.kwargs["base_filename"]
        assert base == "/tmp/主播名_now", f"模板 {template} 未正确剥离: {base}"


def test_early_interrupt_stops_danmaku_and_terminates(main_mod: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    # 提前中断回归：URL 被注释时弹幕立即停止、ffmpeg 被终止、返回 True 通知线程退出。
    main = main_mod
    monkeypatch.setattr(main, "split_video_by_time", False)
    record_url = "https://live.douyin.com/123456"
    factory = _setup_common(monkeypatch, main, [None])
    monkeypatch.setattr(main, "url_comments", {record_url})
    terminate = MagicMock(return_value=True)
    monkeypatch.setattr(main, "_terminate_ffmpeg_process", terminate)
    monkeypatch.setattr(main, "clear_record_info", lambda name, url: None)

    result = main.check_subprocess(
        "主播名",
        record_url,
        ["ffmpeg", "-i", "x", "/tmp/主播名_2026-08-16_10-00-00.ts"],
        "TS",
        None,
        platform="抖音直播",
        danmaku_args={"room_id": "999"},
    )

    assert result is True
    collector = factory.return_value
    assert collector.stop.call_count == 1, "提前中断时弹幕应立即停止一次"
    assert terminate.call_count == 1


def test_unsupported_platform_skips_collector(main_mod: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    # 负向用例：平台不在弹幕列表时不创建采集器，录制流程不受影响。
    main = main_mod
    monkeypatch.setattr(main, "split_video_by_time", False)
    # 平台「某不支持平台」不在 danmaku_platforms（仅含抖音直播）列表中。
    factory = _setup_common(monkeypatch, main, [0])

    result = main.check_subprocess(
        "主播名",
        "https://example.com/live",
        ["ffmpeg", "-i", "x", "/tmp/主播名_2026-08-16_10-00-00.ts"],
        "TS",
        None,
        platform="某不支持平台",
        danmaku_args={"room_id": "999"},
    )

    assert result is False
    # 负向：平台不在 danmaku_platforms 列表 → 不创建采集器，录制不受弹幕影响。
    factory.assert_not_called()


def test_srt_segment_path_matches_ffmpeg_3wide(tmp_path: Path) -> None:
    # 文件名对齐：SRT 分片宽度与 ffmpeg 分段模板 _%03d 落盘结果一致（_000/_001…）。
    base = str(tmp_path / "主播名_now")
    w = SrtWriter(base_filename=base, segment_seconds=60.0)
    assert w._segment_path(0) == base + "_000.srt"
    assert w._segment_path(12) == base + "_012.srt"
    w_none = SrtWriter(base_filename=base, segment_seconds=None)
    # 不分片时 SRT 为单文件，路径无序号后缀（与 ffmpeg 非分段输出一致）。
    assert w_none._segment_path(0) == base + ".srt"


def test_collector_stop_idempotent(tmp_path: Path) -> None:
    # 幂等回归：stop() 重复调用安全（防重入），SRT close 不会重复执行。
    # 用 MagicMock 作弹幕客户端（无头）；监控 SRT.close 调用次数验证幂等。
    collector = DanmakuCollector(
        danmaku_cls=cast(Any, MagicMock()),
        danmaku_args={},
        base_filename=str(tmp_path / "idem"),
        segment_seconds=None,
    )
    close_spy = MagicMock()
    srt = collector._srt
    assert srt is not None
    srt.close = close_spy  # type: ignore[method-assign]
    collector.stop()
    collector.stop()
    assert close_spy.call_count == 1


async def test_douyin_empty_cookie_fetches_ttwid(monkeypatch: pytest.MonkeyPatch) -> None:
    # 动态凭据回归：空 cookie 时必须调用 get_ttwid 并把结果放进 WS 握手头。
    import src.platforms.douyin as dy_mod

    # _FakeWs 捕获 connect 时的关键字参数（含 headers），用于断言 ttwid 注入握手头。
    captured: dict = {}

    class _FakeWs:
        def __init__(self, **kwargs: Any) -> None:
            captured.update(kwargs)

        async def connect(self) -> None:
            captured["connected"] = True

    async def _fake_get_ttwid(proxy_addr: Any = None) -> str:
        return "ttwid=fake_dynamic_value"

    monkeypatch.setattr(dy_mod, "WsClient", _FakeWs)
    monkeypatch.setattr(dy_mod, "get_ttwid", _fake_get_ttwid)

    danmaku = dy_mod.DouyinDanmaku()
    # 空 cookie 启动：应动态获取 ttwid 并写入 WS 握手头，否则抖音弹幕服务器拒绝连接。
    await danmaku.start({"room_id": "123", "user_id": "456", "cookie": ""})

    assert captured.get("connected") is True
    assert captured["headers"]["Cookie"] == "ttwid=fake_dynamic_value"


async def test_douyin_ttwid_fetch_failure_warns_but_continues(monkeypatch: pytest.MonkeyPatch) -> None:
    # 兜底回归：get_ttwid 异常不向上传播（弹幕失败不影响录像），cookie 置空。
    import src.platforms.douyin as dy_mod

    captured: dict = {}

    class _FakeWs:
        def __init__(self, **kwargs: Any) -> None:
            captured.update(kwargs)

        async def connect(self) -> None:
            pass

    async def _boom(proxy_addr: Any = None) -> str:
        # 模拟 get_ttwid 网络异常：验证异常被捕获、cookie 置空、不中断录制流程。
        raise RuntimeError("network down")

    monkeypatch.setattr(dy_mod, "WsClient", _FakeWs)
    monkeypatch.setattr(dy_mod, "get_ttwid", _boom)

    danmaku = dy_mod.DouyinDanmaku()
    # get_ttwid 异常：cookie 置空继续（弹幕失败不影响录像），不得向上传播中断录制。
    await danmaku.start({"room_id": "123", "user_id": "456", "cookie": ""})

    assert captured["headers"]["Cookie"] == ""


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
