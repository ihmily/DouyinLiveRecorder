# 录制守护（看门狗）与录制状态收尾的回归测试（离线：不触网、不起真实 ffmpeg）。
#
# 覆盖 CODE_REVIEW_2026-09-20 条目（判据一律「删掉生产实现就该失败」：只打桩子进程 / 网络 / 时钟 /
# 弹幕，不重新实现任何判定逻辑）：
#   停滞基准按「最后一次观测到增长」计时，而非进程起跑时刻（45s 空档不得被杀 / 11min 必须被杀）；
#   单次录制时长上限：分段关闭时不生效，命中上限按「正常录完」收尾（记成功、不判挂起）；
#   等待录制槽的放弃分支必须回收录制状态（否则留下永久幽灵「录制中」）；
#   Popen 之后抛错必须统一收敛子进程与录制状态（否则孤儿 ffmpeg + 同目录双路写盘）；
#   直下路径「HTTP 200 + 空/极小响应体」不得判成功；
#   only_flv 分支缺 flv_url：recording 必须为空、且不得留下存活的时间字幕线程。
#
# 写法约定（AGENTS.md）：main 引用的 stdlib / 第三方模块（time / subprocess / httpx）一律用浅拷贝
# shim 替换 main 命名空间里的全局名，绝不 setattr 到模块本体（会波及同进程守护线程）。

import subprocess
import sys
import threading
import time
import types
from collections.abc import Callable
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent
_HUYA_URL = "https://www.huya.com/16028551"
_HUYA_HOST = "www.huya.com"
_DOUYIN_URL = "https://live.douyin.com/123456"


@pytest.fixture(scope="module")
def main_mod() -> Any:
    # main.py 的 _app_root() 基于 sys.argv[0] 定位 config/，pytest 下 argv[0] 指向 pytest 自身，
    # 需在导入前修正为项目 main.py（与 tests/test_danmaku_wiring.py 同一模式）。
    old_argv = sys.argv[:]
    sys.argv = [str(_REPO_ROOT / "main.py")]
    try:
        import main

        return main
    finally:
        sys.argv = old_argv


class _Clock:
    # 可控时钟：time.time() 取自假时钟、time.sleep(n) 直接把时钟推进 n 秒。
    # 于是「11 分钟的停滞窗口」几乎零真实耗时，而判定逻辑走的仍是生产实现本体。
    def __init__(self, start: float = 1_000_000.0) -> None:
        self.now = start
        self.on_advance: Callable[[float], None] | None = None

    def time(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        # 推进假时钟 = 「这一轮循环真的睡了这么久」，所以产物增长计划（on_advance）必须挂在
        # 这里：增长只发生在两次 stat 之间，与真实形态（ffmpeg 持续写盘、守护循环每秒 stat）同构；
        # 挂在 time() 上会让读到的大小取决于「先 stat 还是先推进」，换个取数顺序就能红绿摆动。
        self.now += seconds
        if self.on_advance is not None:
            self.on_advance(self.now)

    def shim(self) -> types.SimpleNamespace:
        # 浅拷贝 stdlib time 的公开属性，只覆盖 time/sleep，其余保持真实实现
        fresh = types.SimpleNamespace(**{k: getattr(time, k) for k in dir(time) if not k.startswith("_")})
        fresh.time = self.time
        fresh.sleep = self.sleep
        return fresh


class _FakeProc:
    # ffmpeg 子进程替身：存活与否由调用方给的谓词裁决（可随假时钟变化）。
    # 必须定义 __class_getitem__：check_subprocess 内层函数注解 subprocess.Popen[bytes] 在 def 时求值。
    def __init__(self, alive: Callable[[], bool], returncode: int = 0) -> None:
        self._alive = alive
        self._returncode = returncode

    def __class_getitem__(cls, item: Any) -> Any:
        return cls

    @property
    def returncode(self) -> int | None:
        # 存活时为 None，退出后才给出码（与真实 Popen 语义一致）
        return None if self._alive() else self._returncode

    def poll(self) -> int | None:
        return None if self._alive() else self._returncode

    def wait(self, timeout: float = 0) -> int:
        # 立即给出退出码：把「终止是否成功」固定在桩侧，使该用例只测「异常出口有没有去
        # 终止/注销/清状态」，不去测真实 waitpid 超时语义（那是 _terminate_ffmpeg_process 的用例面）
        return self._returncode

    def terminate(self) -> None:
        return None

    def kill(self) -> None:
        return None

    @property
    def stdout(self) -> None:
        # 收尾的「写侧故障」二级判定会读这条管道；离线用例没有输出可读
        return None


def _prime(main: Any, monkeypatch: pytest.MonkeyPatch, clock: _Clock) -> dict[str, list]:
    # 装配 check_subprocess 的最小环境，返回各类调用/样本的捕获容器。acquire 恒真 =「录制槽可得」，
    # 让看门狗/收尾分支不被并发闸门干扰；反向用法见 test_giving_up_slot_wait_clears_recording_state
    # （acquire 恒假 + Popen 桩抛错，才能证明「放弃分支发生在 Popen 之前」——槽位必须先 acquire）。
    samples: dict[str, list] = {"ok": [], "err": [], "term": [], "unregister": [], "marks": []}
    sem = types.SimpleNamespace(acquire=lambda timeout=None: True, release=lambda: None)
    monkeypatch.setattr(main, "recording_semaphore", sem)
    monkeypatch.setattr(main, "exit_recording", False)
    monkeypatch.setattr(main, "recording_enabled", True)
    monkeypatch.setattr(main, "url_comments", set())
    monkeypatch.setattr(main, "recording", set())
    monkeypatch.setattr(main, "recording_time_list", {})
    monkeypatch.setattr(main, "record_state_lock", threading.Lock())
    monkeypatch.setattr(main, "enable_danmaku", False)
    monkeypatch.setattr(main, "enable_danmaku_monitor", False)
    monkeypatch.setattr(main, "danmaku_platforms", [])
    monkeypatch.setattr(main, "create_time_file", False)
    monkeypatch.setattr(main, "converts_to_mp4", False)
    monkeypatch.setattr(main, "delete_origin_file", False)
    monkeypatch.setattr(main, "register_ffmpeg_process", lambda proc: None)
    monkeypatch.setattr(main, "unregister_ffmpeg_process", lambda proc: samples["unregister"].append(proc))
    monkeypatch.setattr(main, "clear_ffmpeg_reject", lambda url, platform: None)
    monkeypatch.setattr(main, "mark_ffmpeg_reject", lambda url, platform: samples["marks"].append(url))
    monkeypatch.setattr(main, "record_success", lambda key=None: samples["ok"].append(key))
    monkeypatch.setattr(main, "record_error", lambda key=None: samples["err"].append(key))
    monkeypatch.setattr(main, "time", clock.shim())
    return samples


def _install_ffmpeg(
    main: Any, monkeypatch: pytest.MonkeyPatch, clock: _Clock, alive_at: float, samples: dict[str, list]
) -> None:
    # 装一个「假时钟走到 alive_at 即退出」的 ffmpeg；终止动作只记录调用、不改存活判定。
    # 存活判定刻意不受 terminate 影响：若实现改成 kill 后继续轮询等退出，alive_at=inf 的用例会
    # 无限循环而不是静默通过（挂死比假绿诚实）。
    def _factory(*args: Any, **kwargs: Any) -> _FakeProc:
        return _FakeProc(lambda: clock.now < alive_at)

    def _terminate(proc: Any, timeout: int = 30) -> bool:
        samples["term"].append(proc)
        return True

    shim = types.SimpleNamespace(**vars(subprocess))
    shim.Popen = _factory
    monkeypatch.setattr(main, "subprocess", shim)
    monkeypatch.setattr(main, "_terminate_ffmpeg_process", _terminate)


def _writer(out_file: Path, until: float, chunk: int = 64) -> Callable[[float], None]:
    # 产物增长计划：假时钟推进时向真实文件追加字节 —— 「有没有增长」由生产代码自己 stat 出来
    # until 取「假时钟绝对值」而非相对秒数：与 _Clock 的起点解耦，改起点不必连带改所有增长窗口
    def _advance(now: float) -> None:
        if now < until:
            with open(out_file, "ab") as fp:
                fp.write(b"\x00" * chunk)

    return _advance


class TestStallWatchdogBaseline:
    # 停滞窗口必须从「最后一次观测到增长」的时刻起算

    def test_45s_write_gap_after_ten_minutes_is_not_killed(
        self, main_mod: Any, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        # 现场形态：非分段录制已跑过 10 分钟，随后 45 秒没有新字节（FLV 输入刻意保留
        # -reconnect_delay_max 60，指数退避期间一个字节都不写；主播暂停推流、CDN 短抖同理），
        # 之后 ffmpeg 自然结束。旧判据拿进程起跑时刻比较 → 空档内第一次采样就把进程杀掉。
        main = main_mod
        out = tmp_path / "主播名_2026-09-20_10-00-00.ts"
        out.write_bytes(b"\x00" * 4096)
        clock = _Clock()
        samples = _prime(main, monkeypatch, clock)
        # 前 700s 正常增长，700~745s 空档，745s 起 ffmpeg 自然退出。节拍前提：守护循环每轮
        # sleep(1)，停滞判定另有 30s 最小采样间隔（_RECORD_STALL_PROBE_INTERVAL），故 45s 空档在
        # 生产视角只等于 1~2 次采样——正是旧判据「满 10 分钟后相邻两次采样字节不变即定罪」误杀的形态。
        clock.on_advance = _writer(out, until=700.0)
        _install_ffmpeg(main, monkeypatch, clock, alive_at=745.0, samples=samples)

        result = main.check_subprocess(
            "主播名",
            _HUYA_URL,
            ["ffmpeg", "-i", "http://hs.flv.huya.com/src/x.flv", str(out)],
            "TS",
            platform="虎牙直播",
        )

        assert result is False
        assert samples["term"] == [], "45 秒写入空档不得被判定为停滞"
        assert samples["err"] == []
        assert samples["ok"] == [_HUYA_HOST]

    def test_11min_write_gap_is_killed_as_stall(
        self, main_mod: Any, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        # 真正的停滞：10 分钟里一个字节都没有 → 必须终止并记失败样本（保留线路退避）。
        # 两条不可省的时序前提：① 产物文件必须**先存在**——getsize 抛 OSError 时生产代码判「无法
        # 观测」并 return ""，用例会以「从未触发」的形式假绿；② 增长窗口（until=100）必须远早于
        # 「100 + 停滞窗口」，否则 _stall_since 被持续刷新、阈值永不越过。ffmpeg 寿命设为无限，
        # 于是「停滞终止分支」是唯一退出路径——用例结束即证明是看门狗杀的。
        main = main_mod
        out = tmp_path / "主播名_2026-09-20_10-00-00.ts"
        out.write_bytes(b"\x00" * 4096)
        clock = _Clock()
        samples = _prime(main, monkeypatch, clock)
        clock.on_advance = _writer(out, until=100.0)  # 100s 之后永不增长
        _install_ffmpeg(main, monkeypatch, clock, alive_at=float("inf"), samples=samples)

        result = main.check_subprocess(
            "主播名",
            _HUYA_URL,
            ["ffmpeg", "-i", "http://hs.flv.huya.com/src/x.flv", str(out)],
            "TS",
            platform="虎牙直播",
        )

        assert result is False
        assert len(samples["term"]) == 1, "连续 11 分钟无增长必须终止 ffmpeg"
        assert samples["err"] == [_HUYA_HOST]
        assert samples["ok"] == []
        # 停滞收尾必须清掉录制状态，否则面板永久「录制中」
        assert main.recording == set()


class TestRecordTimeLimit:
    # 单次录制时长上限改为可配置 + 命中后按成功收尾

    def test_limit_rolls_over_as_successful_round(
        self, main_mod: Any, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        # 分段开启：命中上限时应「结束本轮并分段续录」——与 rc==0 同一条收尾链路：
        # 记成功样本、不记 record_error（旧实现把 24 小时轮播房间每 6 小时判一次挂起，
        # 既污染按 host 的熔断窗口，又跳过 converts_to_mp4 与 clear_ffmpeg_reject）。
        main = main_mod
        stem = tmp_path / "主播名_2026-09-20_10-00-00"
        seg = stem.with_name(stem.name + "_000.ts")
        seg.write_bytes(b"\x00" * 4096)
        clock = _Clock()
        samples = _prime(main, monkeypatch, clock)
        monkeypatch.setattr(main, "max_record_seconds", 60)
        # 时序：上限判定在「30s 最小采样间隔」闸门**之前**，故 60s 上限会在第 61 次 1s 轮询
        # 立即命中，不必等采样窗口；同时传给 check_subprocess 的是含 %03d 的模板路径，
        # stat 恒失败 → 停滞分支必然不参与，本案与该判据互不干扰（否则同一红有两种成因）
        _install_ffmpeg(main, monkeypatch, clock, alive_at=float("inf"), samples=samples)

        result = main.check_subprocess(
            "主播名",
            _HUYA_URL,
            ["ffmpeg", "-i", "http://hs.flv.huya.com/src/x.flv", str(stem) + "_%03d.ts"],
            "TS",
            platform="虎牙直播",
        )

        assert result is False
        assert len(samples["term"]) == 1
        assert samples["err"] == [], "达到时长上限不是故障，不得记失败样本"
        assert samples["ok"] == [_HUYA_HOST]

    def test_limit_not_applied_when_segmentation_off(
        self, main_mod: Any, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        # 分段关闭时单文件长录是用户的显式选择 → 上限不参与判定（60s 上限、跑了 200s 也不该停）
        main = main_mod
        out = tmp_path / "主播名_2026-09-20_10-00-00.ts"
        out.write_bytes(b"\x00" * 4096)
        clock = _Clock()
        samples = _prime(main, monkeypatch, clock)
        monkeypatch.setattr(main, "max_record_seconds", 60)
        clock.on_advance = _writer(out, until=200.0)
        _install_ffmpeg(main, monkeypatch, clock, alive_at=200.0, samples=samples)

        result = main.check_subprocess(
            "主播名",
            _HUYA_URL,
            ["ffmpeg", "-i", "http://hs.flv.huya.com/src/x.flv", str(out)],
            "TS",
            platform="虎牙直播",
        )

        assert result is False
        assert samples["term"] == [], "分段关闭时单次时长上限不得生效"
        assert samples["ok"] == [_HUYA_HOST]

    def test_stall_threshold_is_not_the_old_start_time_baseline(self, main_mod: Any) -> None:
        # 常量口径锁：停滞窗口仍是 10 分钟、采样间隔 30s。该前提本身也是语义的一部分：窗口一旦
        # <= 2×采样间隔，「连续 10 分钟无增长」就退化成「相邻两次采样字节不变」，45s 空档用例随之
        # 失去区分度，而常量比较仍全绿。
        assert main_mod._RECORD_STALL_SECONDS > main_mod._RECORD_STALL_PROBE_INTERVAL * 2
        assert main_mod._MAX_RECORD_SECONDS == 6 * 60 * 60


class TestRecordingStateUnwind:
    # 任何出口都必须把录制状态与子进程收敛干净

    def test_giving_up_slot_wait_clears_recording_state(self, main_mod: Any, monkeypatch: pytest.MonkeyPatch) -> None:
        main = main_mod
        monkeypatch.setattr(main, "recording", {"主播名"})
        monkeypatch.setattr(main, "recording_time_list", {"主播名": []})
        monkeypatch.setattr(main, "url_comments", {_DOUYIN_URL})
        monkeypatch.setattr(main, "running_list", [])
        monkeypatch.setattr(main, "record_state_lock", threading.Lock())
        # acquire 恒失败 → 只能走「等待期间检测到停止信号，放弃本轮」分支
        monkeypatch.setattr(
            main, "recording_semaphore", types.SimpleNamespace(acquire=lambda timeout=None: False, release=lambda: None)
        )

        def _boom(*args: Any, **kwargs: Any) -> None:
            raise AssertionError("放弃本轮录制时不得启动 ffmpeg")

        shim = types.SimpleNamespace(**vars(subprocess))
        shim.Popen = _boom
        monkeypatch.setattr(main, "subprocess", shim)

        assert main.check_subprocess("主播名", _DOUYIN_URL, ["ffmpeg", "-i", "x", "/tmp/out.ts"], "TS") is True
        assert main.recording == set(), "放弃录制槽等待时必须回收 recording 条目"
        assert main.recording_time_list == {}

    def test_exception_after_popen_terminates_process_and_clears_state(
        self, main_mod: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Popen 成功之后的抛错点（现实形态为 Thread.start 的 can't start new thread）
        # 必须与早退路径同样收敛：终止 + 注销 + 清录制状态。
        main = main_mod
        clock = _Clock()
        samples = _prime(main, monkeypatch, clock)
        _install_ffmpeg(main, monkeypatch, clock, alive_at=float("inf"), samples=samples)
        monkeypatch.setattr(main, "recording", {"主播名"})
        monkeypatch.setattr(main, "recording_time_list", {"主播名": []})

        def _register_raises(proc: Any) -> None:
            raise RuntimeError("can't start new thread")

        monkeypatch.setattr(main, "register_ffmpeg_process", _register_raises)

        with pytest.raises(RuntimeError):
            main.check_subprocess(
                "主播名", _HUYA_URL, ["ffmpeg", "-i", "http://x/y.flv", "/tmp/out.ts"], "TS", platform="虎牙直播"
            )

        assert len(samples["term"]) == 1, "异常出口必须终止已启动的 ffmpeg"
        assert main.recording == set(), "异常出口必须回收 recording 条目"
        assert main.recording_time_list == {}


class _FakeStreamResponse:
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
    def __init__(self, response: _FakeStreamResponse) -> None:
        self._response = response

    def __enter__(self) -> "_FakeHttpClient":
        return self

    def __exit__(self, *args: Any) -> None:
        return None

    def stream(self, method: str, url: str, **kwargs: Any) -> _FakeStreamResponse:
        return self._response


class TestDirectDownloadResultContract:
    # 直下路径（shopee / 花椒）的成功判定必须与 ffmpeg 路径的「产物达标」口径一致

    def _download(self, main: Any, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, chunks: list[bytes]) -> bool:
        monkeypatch.setattr(main, "get_record_headers", lambda *a, **k: {})
        monkeypatch.setattr(main, "get_record_user_agent", lambda *a, **k: "")
        response = _FakeStreamResponse(200, chunks)
        # 只替换 main 命名空间里的 httpx 引用（不改第三方模块本体）
        shim = types.SimpleNamespace(**vars(main.httpx))
        shim.Client = lambda **kw: _FakeHttpClient(response)
        monkeypatch.setattr(main, "httpx", shim)
        save_path = tmp_path / "out.flv"
        return bool(
            main.direct_download_stream(
                "http://cdn.example/live.flv?wsSecret=abc", str(save_path), "主播", _DOUYIN_URL, "shopee"
            )
        )

    def test_200_with_empty_body_is_not_success(
        self, main_mod: Any, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        # HTTP 200 + 空响应体：文件被 finally 清成 0 字节，函数不得再回报成功
        # （否则调用方打印「直播录制完成」并记 record_success，坏线路一条失败样本都不留）
        assert self._download(main_mod, monkeypatch, tmp_path, []) is False

    def test_200_with_tiny_body_is_not_success(
        self, main_mod: Any, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        assert self._download(main_mod, monkeypatch, tmp_path, [b"x" * 16]) is False

    def test_200_with_valid_body_is_success(
        self, main_mod: Any, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        assert self._download(main_mod, monkeypatch, tmp_path, [b"y" * (main_mod._MIN_VALID_RECORD_BYTES + 1)]) is True

    def test_min_valid_bytes_constant(self, main_mod: Any) -> None:
        # 直下与 ffmpeg 两条路径共用同一阈值（口径漂移即回归）
        assert main_mod._MIN_VALID_RECORD_BYTES == 1024


def _prime_start_record(
    main: Any,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    port_info: dict[str, Any],
    platform: str,
) -> dict[str, list]:
    # 装配 start_record 单轮运行所需的全部模块全局（与 test_start_record_command_golden
    # 的 harness 同一组键）；返回字幕线程 / 直下调用 / 状态清理的捕获容器。
    captured: dict[str, list] = {"subs": [], "downloads": [], "clears": [], "ok": [], "err": []}
    plain: dict[str, Any] = {
        "exit_recording": False,
        "recording_enabled": True,
        "recording": set(),
        "recording_time_list": {},
        "record_state_lock": threading.Lock(),
        "need_update_line_list": [],
        "not_record_list": [],
        "error_window": [],
        "url_comments": set(),
        "running_list": [],
        "monitoring": 0,
        "scheduler": None,
        "auto_update_anchor_name": False,
        "show_url": False,
        "live_status_push": "",
        "begin_show_push": False,
        "over_show_push": False,
        "over_push_message_text": "",
        "begin_push_message_text": "",
        "disable_record": False,
        "push_check_seconds": 0,
        "create_time_file": True,  # 触发前提：勾选「生成时间字幕文件」
        "converts_to_mp4": False,
        "delete_origin_file": False,
        "custom_script": "",
        "video_save_path": "",
        "folder_by_author": False,
        "folder_by_time": False,
        "folder_by_title": False,
        "filename_by_title": False,
        "default_path": str(tmp_path),
        "enable_https_recording": False,
        "loop_time": False,
        "delay_default": 0,
        "video_save_type": "FLV",
        "split_video_by_time": False,
        "split_time": "600",
        "proxy_addr": "",
        "proxy_addr_bak": "",
        "enable_proxy_platform_list": [],
        "extra_enable_proxy_platform_list": [],
        "OVERSEAS_PLATFORM_HOST": [],
        "color_obj": MagicMock(),
        "create_var": {},
    }
    for name, value in plain.items():
        monkeypatch.setattr(main, name, value, raising=False)
    for ck in ("shopee_cookie", "huajiao_cookie", "dy_cookie", "hy_cookie"):
        monkeypatch.setattr(main, ck, "", raising=False)

    monkeypatch.setattr(main, "_resolve_platform_stream", lambda *a, **k: (platform, port_info, None, ""))
    # 只有 m3u8、没有 flv_url 时，选源仍给出可用地址（游客态/接口结构变更的真实形态），
    # 否则会在「本轮未获取到可用流地址」处提前 continue，测不到 only_flv 分支
    monkeypatch.setattr(main, "select_source_url", lambda *a, **k: port_info.get("m3u8_url") or "")
    monkeypatch.setattr(main, "get_record_headers", lambda *a, **k: None)
    monkeypatch.setattr(main, "get_record_user_agent", lambda *a, **k: None)
    # 时间字幕线程体：只登记线程名即返回（真实实现是 while True 每秒追加一行 SRT）
    _real_current = threading.current_thread

    def _fake_generate_subtitles(record_name: str, subs_file_path: str) -> None:
        captured["subs"].append(_real_current().name)

    monkeypatch.setattr(main, "generate_subtitles", _fake_generate_subtitles)

    def _fake_download(
        flv_url: str, save_file_path: str, record_name: str, record_url: str, platform: str, cookies: str | None = None
    ) -> bool:
        captured["downloads"].append(flv_url)
        return True

    monkeypatch.setattr(main, "direct_download_stream", _fake_download)
    monkeypatch.setattr(main, "record_success", lambda key=None: captured["ok"].append(key))
    monkeypatch.setattr(main, "record_error", lambda key=None: captured["err"].append(key))

    # 真实 clear_record_info（负责回收 recording/recording_time_list）+ 记录调用 + 结束本轮：
    # start_record 是 while True，靠置 exit_recording 让线程在下一轮顶部干净退出
    real_clear = main.clear_record_info

    def _spy_clear(record_name: str, record_url: str) -> None:
        real_clear(record_name, record_url)
        captured["clears"].append(record_name)
        setattr(main, "exit_recording", True)

    monkeypatch.setattr(main, "clear_record_info", _spy_clear)
    # 轮末等待用假时钟：sleep 只推进虚拟时间、绝不真睡（delay_default=0，靠 _spy_clear 置
    # exit_recording 在下一轮顶部干净退出）；on_advance 置 no-op 因为这里不建模产物增长。
    # 仍走 shim 结构：只覆盖 time/sleep 两个属性，不动 stdlib 本体。
    idle = _Clock()
    idle.on_advance = lambda _now: None
    monkeypatch.setattr(main, "time", idle.shim())
    return captured


class TestOnlyFlvWithoutFlvUrl:
    # 强制直下平台未拿到 flv_url 时，既不能留幽灵「录制中」，也不能起永不退出的字幕线程。
    # 这里查的是时序而非仅「有没有起线程」：generate_subtitles 是 while True，唯一退出条件是
    # record_name not in recording——原始缺陷正是「线程在 flv_url 校验之前启动」叠加「未命中的 else
    # 分支不清 recording」，于是名字永不回收、线程永不停止地写 .srt，而房间线程每轮（默认 120s）
    # 又再起一条。既查 captured["subs"]（本用例内启动次数）也查 threading.enumerate()（跨用例残留），
    # 只查前者会漏「起了但没登记名字」，只查后者会漏「起得太早」这类顺序问题。

    def test_no_flv_url_leaves_no_recording_state_and_no_subtitle_thread(
        self, main_mod: Any, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        main = main_mod
        port_info = {
            "is_live": True,
            "anchor_name": "主播名",
            "title": "",
            "m3u8_url": "http://pull.example.com/1.m3u8",
            "flv_url": None,
            "actual_quality": None,
        }
        captured = _prime_start_record(main, monkeypatch, tmp_path, port_info, "shopee")

        main.start_record(("原画", "https://live.shopee.sg/share/1", "主播名"), 1)

        assert captured["downloads"] == [], "无 flv_url 时不得进入直下"
        assert main.recording == set(), "未找到 FLV 时必须回收 recording 条目"
        assert main.recording_time_list == {}
        assert captured["clears"], "未命中的 else 分支必须调 clear_record_info"
        assert captured["subs"] == [], "未拿到 flv_url 前不得启动时间字幕线程"
        alive_subs = [t.name for t in threading.enumerate() if t.name.startswith("subs_")]
        assert alive_subs == [], f"不得留下会永久写盘的字幕线程: {alive_subs}"

    def test_with_flv_url_subtitle_thread_is_started_after_validation(
        self, main_mod: Any, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        # 对照组（防假绿）：拿到 flv_url 时字幕线程照旧启动、直下照旧执行、收尾状态照旧回收
        main = main_mod
        flv = "http://pull.example.com/1.flv"
        port_info = {
            "is_live": True,
            "anchor_name": "主播名",
            "title": "",
            "m3u8_url": "http://pull.example.com/1.m3u8",
            "flv_url": flv,
            "actual_quality": None,
        }
        captured = _prime_start_record(main, monkeypatch, tmp_path, port_info, "shopee")

        main.start_record(("原画", "https://live.shopee.sg/share/1", "主播名"), 1)

        assert captured["downloads"] == [flv]
        assert len(captured["subs"]) == 1, "flv_url 校验通过后应启动时间字幕线程"
        assert main.recording == set()
