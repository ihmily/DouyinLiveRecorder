# tests/test_regression_postprocess.py - src/video_postprocess.py 回归锁。
#
# 覆盖三条 2026-09-23 实测确认「仍未修复」的条目：
#   ① generate_subtitles 的写盘段无 try/except：线程跑在**录制子进程**里（main.py 的
#      _subtitle_thread_target），而 threading.excepthook 只装在 GUI 窗口层（src/gui_qt/app.py）→ 磁盘满 / 目录被改名 /
#      路径过长时线程静默死掉，traceback 落 stderr 后被 display_info 的 "\033[2J" 刷掉，房间仍显示
#      「正在录制」。锁：异常不外抛 + 告警按时间窗聚合 + 失败后按间隔退避重开 + 恢复只报一次。
#   ② converts_m4a / segment_video 未接该半成品清理（只有 converts_mp4 有）
#      → 失败/超时/取消后留下「大小可观但打不开」的产物被上层当有效文件。
#      锁：三个入口的失败路径都清理，且**只删本次新增**（快照不可得时一律不删）。
#   ③ segment_video 缺 `-n`：撞名时 ffmpeg 会问 Overwrite、无 stdin → EOF →
#      走满 600s 超时才被 kill。锁：三条命令都带 `-n` 且紧跟输出参数。
#
# 全部离线：ffmpeg 由 vp._run_ffmpeg_checked 的替身模拟，不启动真实进程；time.sleep 经模块内 time
# 引用的 SimpleNamespace 浅拷贝替换。计时口径：generate_subtitles 的退避/聚合以循环自身的秒计数
# index_time 为基准，故用例只需控制 sleep 次数即可确定性推进窗口，不依赖真实时钟。

import ast
import importlib.util
import json
import re
import subprocess
import threading
import types
from pathlib import Path
from typing import Any

import pytest

import main
import src.video_postprocess as vp

ROOT = Path(__file__).resolve().parents[1]
_PLACEHOLDER_RE = re.compile(r"\{([^{}]+)\}")

# 本模块新增的 msgid（已并入四语目录；pending 袋子已随中央合并删除）。
NEW_MSGIDS = [
    "[后处理]无法读取产物目录，本次跳过半成品清理: {out_path} - {type_name}: {e}",
    "[后处理]失败后无法读取产物目录，半成品未清理: {out_path} - {type_name}: {e}",
    "[时间字幕]写入失败，{retry}s 后重试打开；本窗口丢失 {lost} 条、累计 {total} 条: {out_path} - {type_name}: {e}",
    "[时间字幕]写入已恢复，故障期间共丢失 {total} 条: {out_path}",
]


@pytest.fixture(autouse=True)
def _stub_main_globals(monkeypatch: pytest.MonkeyPatch) -> None:
    # 三个入口都在运行时惰性读 main 的少量全局，这里全部打桩，避免依赖真实 config.ini
    monkeypatch.setattr(main, "converts_to_h264", False, raising=False)
    monkeypatch.setattr(main, "os_type", "nt", raising=False)
    monkeypatch.setattr(main, "text_encoding", "utf-8", raising=False)
    monkeypatch.setattr(main, "recording", set(), raising=False)
    monkeypatch.setattr(main, "record_state_lock", threading.Lock(), raising=False)

    class _Color:
        YELLOW = ""

        def print_colored(self, *_a: Any, **_k: Any) -> None:
            return None

    monkeypatch.setattr(main, "color_obj", _Color(), raising=False)


@pytest.fixture()
def warnings_sink(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    captured: list[str] = []
    monkeypatch.setattr(vp.logger, "warning", lambda msg, *a, **k: captured.append(str(msg)))
    return captured


@pytest.fixture()
def errors_sink(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    captured: list[str] = []
    monkeypatch.setattr(vp.logger, "error", lambda msg, *a, **k: captured.append(str(msg)))
    return captured


def _no_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    # 浅拷贝 time 模块再覆盖 sleep：vp.time 就是 stdlib time 本体，直接 setattr 会换掉全进程 sleep
    shim = types.SimpleNamespace(**vars(vp.time))
    shim.sleep = lambda _s: None
    monkeypatch.setattr(vp, "time", shim)


def _make_source(tmp_path: Path, name: str = "live_000.ts", size: int = 64) -> Path:
    src = tmp_path / name
    src.write_bytes(b"\x47" * size)
    return src


def _install_runner(
    monkeypatch: pytest.MonkeyPatch,
    error: BaseException | None,
    produced: list[Path],
    contents: bytes = b"partial-bytes",
) -> dict[str, Any]:
    # 替身 _run_ffmpeg_checked：先把「本次已经写出的产物」落到磁盘（模拟 ffmpeg 中途被杀/
    # 中途报错时的半截文件），再抛出指定异常。produced 里哪些算「本次新建」由用例安排。
    recorded: dict[str, Any] = {}

    def _fake_run(command: list[str], timeout: int = 600) -> str:
        recorded["command"] = command
        recorded["timeout"] = timeout
        for path in produced:
            path.write_bytes(contents)
        if error is not None:
            raise error
        return ""

    monkeypatch.setattr(vp, "_run_ffmpeg_checked", _fake_run)
    return recorded


# ────────────────────────────────────────────────────────────
# ⑤：converts_m4a 的半成品清理
# ────────────────────────────────────────────────────────────


class TestM4aPartialCleanup:
    def test_timeout_discards_partial_m4a(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        src = _make_source(tmp_path, "live.ts")
        out = tmp_path / "live.m4a"
        _install_runner(monkeypatch, subprocess.TimeoutExpired(cmd=["ffmpeg"], timeout=1), [out])
        vp.converts_m4a(str(src))
        assert not out.exists(), "超时后仍留下半截 .m4a（AAC 帧头已写、尾部截断）"
        assert src.exists(), "源文件必须保留（is_original_delete 分支未走到）"

    def test_nonzero_exit_discards_partial_m4a(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        src = _make_source(tmp_path, "live.ts")
        out = tmp_path / "live.m4a"
        _install_runner(monkeypatch, subprocess.CalledProcessError(1, ["ffmpeg"]), [out])
        vp.converts_m4a(str(src), is_original_delete=False)
        assert not out.exists()
        assert src.exists()

    def test_pre_existing_m4a_is_kept(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        # 调用前同名 .m4a 已存在 → 不删：那可能是上一次的成功产物（该既有判据）。桩里刻意让
        # 「本次 ffmpeg」又往同名路径写了一截，锁的是**文件不被删**而非内容不变（判据是「快照里出现过」）。
        src = _make_source(tmp_path, "live.ts")
        out = tmp_path / "live.m4a"
        out.write_bytes(b"previous-good-file")
        _install_runner(monkeypatch, subprocess.CalledProcessError(1, ["ffmpeg"]), [out])
        vp.converts_m4a(str(src), is_original_delete=False)
        assert out.exists()

    def test_success_keeps_output_and_deletes_source(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        src = _make_source(tmp_path, "live.ts")
        out = tmp_path / "live.m4a"
        _install_runner(monkeypatch, None, [out], contents=b"complete-m4a")
        _no_sleep(monkeypatch)
        vp.converts_m4a(str(src), is_original_delete=True)
        assert out.exists(), "成功产物不得被清理出口误删"
        assert not src.exists()

    def test_base_exception_also_discards_and_propagates(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        # 「取消/KeyboardInterrupt」不走 except Exception：清理出口必须同样覆盖，
        # 且异常原样上抛（本函数不得替上层把 BaseException 吞掉）
        src = _make_source(tmp_path, "live.ts")
        out = tmp_path / "live.m4a"
        _install_runner(monkeypatch, KeyboardInterrupt(), [out])
        with pytest.raises(KeyboardInterrupt):
            vp.converts_m4a(str(src))
        assert not out.exists()


# ────────────────────────────────────────────────────────────
# ⑤ + ⑥：segment_video 的半成品清理与 -n
# ────────────────────────────────────────────────────────────


class TestSegmentPartialCleanup:
    def test_failure_discards_only_new_segments(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        src = _make_source(tmp_path, "live.ts")
        old = tmp_path / "out_000.ts"
        old.write_bytes(b"previous-good-segment")
        new1 = tmp_path / "out_001.ts"
        new2 = tmp_path / "out_002.ts"
        _install_runner(monkeypatch, subprocess.TimeoutExpired(cmd=["ffmpeg"], timeout=1), [new1, new2])
        vp.segment_video(str(src), str(tmp_path / "out_%03d.ts"), "mpegts", "1800", is_original_delete=False)
        assert old.read_bytes() == b"previous-good-segment", "上一次的成功分段被误删"
        assert not new1.exists() and not new2.exists(), "本次新增的残缺分段未被清理"
        assert src.exists()

    def test_more_than_999th_segment_is_matched(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        # %03d 在段数超 999 时输出 4 位（main.py 的转码分支已按此兼容），
        # 恰好 3 位的匹配器会漏掉 _1000.ts，让它以残缺形态留在目录里
        src = _make_source(tmp_path, "live.ts")
        big = tmp_path / "out_1000.ts"
        _install_runner(monkeypatch, subprocess.CalledProcessError(1, ["ffmpeg"]), [big])
        vp.segment_video(str(src), str(tmp_path / "out_%03d.ts"), "mpegts", "60", is_original_delete=False)
        assert not big.exists()

    def test_success_keeps_all_segments(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        src = _make_source(tmp_path, "live.ts")
        segs = [tmp_path / "out_000.ts", tmp_path / "out_001.ts"]
        _install_runner(monkeypatch, None, segs, contents=b"good-segment")
        _no_sleep(monkeypatch)
        vp.segment_video(str(src), str(tmp_path / "out_%03d.ts"), "mpegts", "60", is_original_delete=True)
        assert all(p.exists() for p in segs), "成功产物不动"
        assert not src.exists()

    def test_unreadable_output_dir_skips_cleanup(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, warnings_sink: list[str]
    ) -> None:
        # 快照不可得时**必须放弃清理**：把「看不见」当成「原先没有」，
        # 下一次列目录成功就会把上一次录制的有效分段全判成本次新增而删掉
        src = _make_source(tmp_path, "live.ts")
        old = tmp_path / "out_000.ts"
        old.write_bytes(b"previous-good-segment")
        new = tmp_path / "out_001.ts"
        real_match = vp._match_outputs
        calls = {"n": 0}

        def flaky(out_spec: str) -> list[str]:
            calls["n"] += 1
            if calls["n"] == 1:
                raise OSError("simulated unreadable dir")
            return real_match(out_spec)

        monkeypatch.setattr(vp, "_match_outputs", flaky)
        _install_runner(monkeypatch, subprocess.CalledProcessError(1, ["ffmpeg"]), [new])
        vp.segment_video(str(src), str(tmp_path / "out_%03d.ts"), "mpegts", "60", is_original_delete=False)
        # 快照不可得 → 清理整段跳过（第二次列目录根本不该发生，更不能用它推导"哪些是新增"）
        assert calls["n"] == 1, f"快照失败后不得再据第二次列目录做删除：{calls}"
        assert old.exists() and new.exists(), "宁可留一份半成品（用户还能自行判断），也不能删错可用产物"
        assert any("跳过半成品清理" in m for m in warnings_sink)

    def test_command_carries_no_overwrite_flag(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        # ⑥：`-n` 必须存在且**紧跟输出参数**（ffmpeg 的文件级选项只对下一个文件生效）
        src = _make_source(tmp_path, "live.ts")
        template = str(tmp_path / "out_%03d.ts")
        recorded = _install_runner(monkeypatch, None, [])
        _no_sleep(monkeypatch)
        vp.segment_video(str(src), template, "mpegts", "60", is_original_delete=False)
        cmd = recorded["command"]
        assert "-n" in cmd, "缺 -n：撞名时 ffmpeg 询问 Overwrite，无 stdin → 走满 600s 超时"
        assert cmd[cmd.index("-n") + 1] == template


class TestNoOverwriteFlagOnAllConverters:
    # 三个 ffmpeg 后处理入口的 `-n` 口径必须一致（审查 6.1 只补了 mp4/m4a）
    def test_mp4_and_m4a_still_carry_flag(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        for name, call in (("mp4", vp.converts_mp4), ("m4a", vp.converts_m4a)):
            src = _make_source(tmp_path, f"live_{name}.ts")
            recorded = _install_runner(monkeypatch, None, [])
            _no_sleep(monkeypatch)
            call(str(src), is_original_delete=False)
            cmd: list[str] = recorded["command"]
            assert "-n" in cmd, f"converts_{name} 丢了 -n"
            # `-n` 必须出现在输出参数**之前**：它在 ffmpeg 里是"对下一个文件生效"的选项，
            # 写到输出文件名之后等于没写（与 -reconnect* 必须在 -i 之前同族）
            assert cmd.index("-n") < len(cmd) - 1, f"converts_{name} 的 -n 落到了输出参数之后"


# ────────────────────────────────────────────────────────────
# ①：generate_subtitles 的写盘守卫
# ────────────────────────────────────────────────────────────


def _run_subtitles_for(monkeypatch: pytest.MonkeyPatch, room: str, stop_after: int) -> None:
    # 让线程跑满 stop_after 轮后自行退出（sleep 桩推进计数并把房间移出 recording）
    state = {"n": 0}
    shim = types.SimpleNamespace(**vars(vp.time))

    def _sleep(seconds: float) -> None:
        state["n"] += 1
        if state["n"] >= stop_after:
            main.recording.discard(room)

    shim.sleep = _sleep
    monkeypatch.setattr(vp, "time", shim)
    main.recording.add(room)


class TestSubtitleWriteGuard:
    def test_oserror_does_not_kill_thread(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, warnings_sink: list[str]
    ) -> None:
        # 目录不存在 → open(..., "a") 抛 FileNotFoundError(OSError)。
        # 修复前：异常直接结束线程，且录制子进程内无 threading.excepthook，日志里什么都不留。
        target = tmp_path / "gone_dir" / "sub"
        _run_subtitles_for(monkeypatch, "room-a", 5)
        vp.generate_subtitles("room-a", str(target))  # 不得抛出
        assert len(warnings_sink) == 1
        assert "FileNotFoundError" in warnings_sink[0], "告警必须带异常类型（socket.timeout 类 str() 为空）"
        assert "gone_dir" in warnings_sink[0]

    def test_warning_aggregated_per_window(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, warnings_sink: list[str]
    ) -> None:
        # 70 轮（每轮 1 秒）→ 只在第 1、61 秒各一条，验证「按时间窗聚合」而非每帧一条。第 1 轮 open
        # 失败即告警；随后每 10s 才重试，到第 61 轮再次告警时窗口内累计 60 条、总累计 61 条。
        target = tmp_path / "gone_dir" / "sub"
        _run_subtitles_for(monkeypatch, "room-b", vp._SUB_WRITE_WARN_WINDOW + 10)
        vp.generate_subtitles("room-b", str(target))
        assert len(warnings_sink) == 2, f"告警条数应等于窗口数，实得: {warnings_sink}"
        assert "本窗口丢失 60 条、累计 61 条" in warnings_sink[1], warnings_sink[1]

    def test_reopen_backoff_skips_open_inside_window(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, warnings_sink: list[str]
    ) -> None:
        # 仿 SrtWriter 的节流重开：失败后每 _SUB_WRITE_RETRY_INTERVAL 秒才试一次 open()，
        # 故障期间不得每秒发起 open（网络盘/USB 掉线时 open 本身会拖住线程）
        attempts: list[int] = []

        def failing_open(file: Any, mode: str = "r", **kw: Any) -> Any:
            attempts.append(len(attempts) + 1)
            raise OSError(28, "No space left on device")

        monkeypatch.setattr(vp, "open", failing_open, raising=False)
        _run_subtitles_for(monkeypatch, "room-c", 25)
        vp.generate_subtitles("room-c", str(tmp_path / "sub"))
        assert len(attempts) == 3, f"25 轮内应只尝试 3 次打开（第 1/11/21 轮），实得 {len(attempts)}"

    def test_recovery_reports_total_lost_once(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        # 前两次 open 失败、第三次成功 → 恢复只补一条汇总（含故障期间丢失的条数）
        real_open = open
        state = {"calls": 0}

        def flaky_open(file: Any, mode: str = "r", **kw: Any) -> Any:
            state["calls"] += 1
            if state["calls"] <= 2:
                raise OSError(28, "No space left on device")
            return real_open(file, mode, **kw)

        monkeypatch.setattr(vp, "open", flaky_open, raising=False)
        warnings: list[str] = []
        monkeypatch.setattr(vp.logger, "warning", lambda msg, *a, **k: warnings.append(str(msg)))
        _run_subtitles_for(monkeypatch, "room-d", 21)
        vp.generate_subtitles("room-d", str(tmp_path / "sub"))
        # 第 1 轮失败即告警；第 11 轮仍失败但在窗口内不重复；第 21 轮成功 → 恢复汇总
        assert len(warnings) == 2
        assert "共丢失 20 条" in warnings[1], warnings[1]
        # 字幕条目按循环自身的 index_time 编号，退避期间丢的帧不会被"补号"，
        # 因此恢复后的首块编号是 21 而不是 2——时间轴与录制时长仍然对齐
        text = (tmp_path / "sub.srt").read_text(encoding="utf-8")
        assert text.startswith("21\n00:00:21,000 --> 00:00:22,000")
        # 第 22 轮写完才检查 recording（退出条件在写之后，语义未改）→ 共 2 块
        assert text.count("\n\n") == 2

    def test_non_oserror_is_not_swallowed(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        # 守卫只捕 OSError：main.text_encoding 配成非法编码名属真 bug（LookupError），
        # 在这里吞掉会让「字幕永远不生成」再次变成无解释的现象
        monkeypatch.setattr(main, "text_encoding", "no-such-codec", raising=False)
        _run_subtitles_for(monkeypatch, "room-e", 3)
        with pytest.raises(LookupError):
            vp.generate_subtitles("room-e", str(tmp_path / "sub"))


# ────────────────────────────────────────────────────────────
# i18n：新 msgid 已登记 pending（四语目录由主会话统一合并）
# ────────────────────────────────────────────────────────────


def _tr_templates_in_module() -> set[str]:
    tree = ast.parse((ROOT / "src" / "video_postprocess.py").read_text(encoding="utf-8"))
    found: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not (isinstance(func, ast.Attribute) and func.attr == "tr" and node.args):
            continue
        first = node.args[0]
        if isinstance(first, ast.Constant) and isinstance(first.value, str):
            found.add(first.value)
    return found


def _catalog_keys() -> set[str]:
    # 直接复用 scripts/compile_po.py 的权威 .po 解析（多行 msgid / 转义还原均正确），不写第二套口径
    spec = importlib.util.spec_from_file_location("_compile_po_probe", ROOT / "scripts" / "compile_po.py")
    assert spec is not None and spec.loader is not None
    cp = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cp)
    return set(cp.parse_po(cp.PO_PATH))


def _four_catalogs() -> dict[str, dict[str, str]]:
    # 断言对象是四语目录本身：pending 袋子已按收尾约定删除，「袋子写过、目录没合并」同样要红。
    # 复用 i18n 自己的三个加载器，不写第二套解析口径。
    from pathlib import Path

    import i18n

    cats = {
        "zh_CN": i18n._load_mo_catalog(i18n.locale_path, "zh_CN"),
        "en_US": i18n._load_json_catalog(Path(i18n.locale_path) / "en_US.json"),
        "en_GB": i18n._load_json_catalog(Path(i18n.locale_path) / "en_GB.json"),
        "zh_TW": i18n._load_yaml_catalog(Path(i18n.locale_path) / "zh_TW.yaml"),
    }
    loaded: dict[str, dict[str, str]] = {}
    for lang_key, value in cats.items():
        # 逐语言断言而不是先算 broken 再 dict(v)：后者 mypy 仍视 value 为可空，前者让「目录缺件」
        # 与「类型收窄」共用同一个事实。
        assert value is not None, f"{lang_key} 语言目录加载失败或缺失（目录缺件 ≠ 用例可跳过）"
        loaded[lang_key] = dict(value)
    return loaded


def _assert_registered(msgids: set[str] | list[str], cats: dict[str, dict[str, str]] | None = None) -> None:
    # 「已登记」= 四语目录都有该 msgid，且三条非默认语言的译文**非空**。只查 zh_CN 会漏掉「键在但
    # 译文空」的静默不翻译；译文留空正是 MI-23 之后「繁体用户看到的仍是简体」的成因形态。
    cats = cats or _four_catalogs()
    for msgid in msgids:
        missing = sorted(lang for lang, cat in cats.items() if msgid not in cat)
        assert not missing, f"msgid 未并入这些语言目录：{missing} <- {msgid[:60]!r}"
        for lang in ("en_US", "en_GB", "zh_TW"):
            # 只断言「非空」：英文源串的 en_US/en_GB 译文按本仓惯例本就是恒等同文
            # （如 'Disk space remaining is below'），加「不得等于 msgid」会把恒等惯例打成假失败。
            assert cats[lang][msgid].strip(), f"{lang} 译文为空：{msgid[:40]!r}"


def _assert_translation_parity(msgids: set[str] | list[str], cats: dict[str, dict[str, str]] | None = None) -> None:
    # 译文内部的占位符集合与换行个数必须与 msgid 逐字一致：不一致时 tr() 当场 KeyError
    # （zh_TW 曾把 {msg} 写成 {msg_2}，钉钉/微信/Bark/PushPlus 的失败告警整条崩掉）。
    import re

    cats = cats or _four_catalogs()
    pat = re.compile(r"\{[^{}]*\}")
    for msgid in msgids:
        want = set(pat.findall(msgid))
        for lang in ("en_US", "en_GB", "zh_TW"):
            text = cats[lang].get(msgid, "")
            assert set(pat.findall(text)) == want, f"{lang} 译文占位符与源串不一致：{msgid[:40]!r}"
            assert len(text.splitlines()) == len(msgid.splitlines()), f"{lang} 译文行数与源串不一致：{msgid[:40]!r}"


class TestPendingCatalogEntries:
    def test_all_runtime_templates_are_registered(self) -> None:
        # 本模块源码里每一处 tr() 模板都必须已并入四语目录（合并前靠 pending 中转，
        # 合并后袋子按收尾约定删除，故这里直接对目录取证）
        cats = _four_catalogs()
        unregistered = sorted(_tr_templates_in_module() - set(cats["zh_CN"]))
        assert unregistered == [], f"未并入 zh_CN 目录的本模块模板: {unregistered}"

    def test_new_msgids_have_three_langs(self) -> None:
        _assert_registered(NEW_MSGIDS)

    def test_new_msgid_placeholders_render(self) -> None:
        _assert_translation_parity(NEW_MSGIDS)
