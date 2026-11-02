# -*- coding: utf-8 -*-
# 2026-09-22 审查报告 / 组 B2（main.py 剩余条目）修复的回归锁。
#
# 判据是「失效形态本身」而不是调用形状：
#   推给用户 IM 的正文若为裸字面量，extract_i18n_strings.py 的 print/logger/tr 三条提取
#             规则全部扫不到 → 非 zh_CN 语言下推送仍是简体中文。这里直接复用提取器的 scan_file 断言。
#   自然语言被提到变量再 print、或 f-string 直传 print_colored 时同样扫不到（「双重盲区」）。
#   FLV + 「停止录制 / URL 被注释」时 _convert_after_record 必须在 comment_end 早退**之前**
#             被调用，否则已录内容永久留在 .flv；MKV/MP4 保持不调用。
#
# 全部离线：该用真实 start_record 线程体 + 桩掉网络层与 ffmpeg 执行层。
#
# 2026-09-23 追加：补齐本文件上方曾点名、但当时**并不存在**的 9 条回归锁（grep 对 9 个用例名全部 0
# 命中），见文件末尾 TestSegmentTemplate* 起各节；另追加 test_watchdog_elapsed_ignores_wall_clock_jump /
# test_segment_observation_failure_is_not_stall（对应 / 该整改）。

import ast
import importlib.util
import inspect
import json
import re
import subprocess
import textwrap
import threading
import time
import types
from pathlib import Path
from typing import Any, cast
from urllib.parse import urlsplit

import httpx
import pytest

import i18n
import main
from src import spider, stream, utils
from src.scheduler import host_of

ROOT = Path(__file__).resolve().parents[1]
MAIN_SRC = ROOT / "main.py"


def _load_extractor() -> Any:
    # 复用生产提取器（scripts/extract_i18n_strings.py）做判据，而不是自写一份字符串匹配：
    # 自写匹配在提取器规则变化后会假绿，而本组条目的失效形态恰恰是「提取器扫不到」。
    spec = importlib.util.spec_from_file_location("extract_i18n_probe", ROOT / "scripts" / "extract_i18n_strings.py")
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ────────────────────────────────────────────────────────────
# 可翻译文案必须进入提取集合
# ────────────────────────────────────────────────────────────


class TestI18nStringsExtractable:
    # 修复前这 8 条串在 scan_file(main.py) 里**一条都没有**（裸字面量 / 变量中转 /
    # f-string 直传 print_colored），因此非 zh_CN 语言下这几处始终是简体中文。

    MSGIDS = [
        # 推送正文（占位符是方括号字面量，走 .replace 链而非 tr kwargs）
        "直播间状态更新：[直播间名称] 直播已结束！时间：[时间]",
        "直播间状态更新：[直播间名称] 正在直播中，时间：[时间]",
        # 自然语言
        "\r{record_name} 正在直播中...",
        "\r{anchor_name} 准备开始录制视频: {full_path}/{filename}",
        "\n{record_name} {stop_time} 直播录制出错,返回码: {return_code}\n",
        "\n{anchor_name} {strftime} 直播录制出错,请检查网络\n",
        "\r{line} 本行包含未知链接.此条跳过",
    ]

    @pytest.fixture(scope="class")
    @classmethod
    def extracted(cls) -> set[str]:
        return cast(set[str], _load_extractor().scan_file(MAIN_SRC))

    @pytest.mark.parametrize("msgid", MSGIDS)
    def test_msgid_reachable_by_extractor(self, msgid: str, extracted: set[str]) -> None:
        assert msgid in extracted, f"提取器扫不到，非 zh_CN 语言下该处仍是简体中文: {msgid!r}"

    def test_push_templates_not_naked_literals(self) -> None:
        # 防回归到「裸字面量」形态：两条推送模板出现处必须都是 i18n.tr( 的实参——只断言「提取器
        # 收录」锁不住「赋值右侧裸串」这一具体写法。
        tree = ast.parse(MAIN_SRC.read_text(encoding="utf-8-sig"))
        naked: list[str] = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Assign):
                continue
            targets = [t.id for t in node.targets if isinstance(t, ast.Name)]
            if "push_content" not in targets:
                continue
            if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                if "直播间状态更新" in node.value.value:
                    naked.append(node.value.value)
        assert naked == [], f"push_content 又被赋成裸字面量: {naked}"

    def test_tr_kwargs_are_actually_used(self) -> None:
        # tr 模板用了 {record_name}/{anchor_name} 等占位符就必须传 kwargs，否则 tr() 内部格式化抛
        # KeyError 时会静默降级回原文模板（i18n.tr 永不抛），译文形同虚设。这里只校验「能格式化成功」。
        import i18n

        cases = [
            ("\r{record_name} 正在直播中...", {"record_name": "张三"}),
            (
                "\r{anchor_name} 准备开始录制视频: {full_path}/{filename}",
                {"anchor_name": "张三", "full_path": "D:/rec", "filename": "a.flv"},
            ),
            (
                "\n{record_name} {stop_time} 直播录制出错,返回码: {return_code}\n",
                {"record_name": "张三", "stop_time": "2026-09-22 10:00:00", "return_code": "1"},
            ),
            (
                "\n{anchor_name} {strftime} 直播录制出错,请检查网络\n",
                {"anchor_name": "张三", "strftime": "2026-09-22 10:00:00"},
            ),
            ("\r{line} 本行包含未知链接.此条跳过", {"line": "http://x"}),
        ]
        for template, kwargs in cases:
            out = i18n.tr(template, **kwargs)
            assert "{" not in out, f"占位符未替换，kwargs 不完整: {template!r} -> {out!r}"


def _four_catalogs() -> dict[str, dict[str, str]]:
    # 断言对象是四语目录本身：_i18n_pending*.json 只是并行修复防撞车的一次性中转袋，已按收尾约定
    # 删除，「袋子写过、目录没合并」同样要红。复用 i18n 自己的三个加载器，不写第二套解析口径。
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
        # 逐语言断言而不是先算 broken 再 dict(v)：后者 mypy 仍视 value 为可空，
        # 前者让「目录缺件」与「类型收窄」共用同一个事实。
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
    # 新 msgid 必须已并入四语目录，且三语译文齐全（pending 袋子已随中央合并删除）。

    NEW_MSGIDS = TestI18nStringsExtractable.MSGIDS

    def test_catalogs_cover_new_msgids(self) -> None:
        cats = _four_catalogs()
        _assert_registered(self.NEW_MSGIDS, cats)

    def test_new_msgid_translations_keep_placeholders(self) -> None:
        _assert_translation_parity(self.NEW_MSGIDS)


# ────────────────────────────────────────────────────────────
# FLV 分支的 _convert_after_record 必须在 comment_end 早退之前
# ────────────────────────────────────────────────────────────


class TestFlvConvertBeforeCommentEnd:
    # 判据是「FLV + comment_end 早退路径上转码是否被调用」这一失效形态本身：从 main.py 里按 AST
    # 取出 FLV/MKV/MP4 分支的真实语句块，经 ast.unparse 后包进函数体编译执行，_convert_after_record
    # 打桩计数——执行的是生产源码本身，非测试自写逻辑，也不与真实录制时序耦合。
    # 复核失效形态：把 main.py 里 `if comment_end:` 的两个 _convert 调用删掉，下方 FLV 用例立即变红。

    def _branch_stmts(self) -> list[ast.stmt]:
        tree = ast.parse(MAIN_SRC.read_text(encoding="utf-8-sig"))
        target: list[ast.stmt] | None = None
        for node in ast.walk(tree):
            body = getattr(node, "body", None)
            if not isinstance(body, list):
                continue
            for idx, stmt in enumerate(body):
                if isinstance(stmt, ast.Assign) and any(
                    isinstance(t, ast.Name) and t.id == "_convert_if_flv" for t in stmt.targets
                ):
                    # 取该赋值语句起、到本块结束的后续语句（含 if comment_end 与尾部转码调用）
                    target = body[idx:]
                    break
            if target is not None:
                break
        assert target is not None, "main.py 中找不到 _convert_if_flv 分支（MIN-2235 修复形态已丢失）"
        return target

    def _drive(self, save_type: str, started: bool = True) -> list[str]:
        stmts = self._branch_stmts()
        # 分支语句里含 `return`（comment_end 早退），必须包在函数体里才能编译
        fn = ast.FunctionDef(
            name="_branch",
            args=ast.arguments(
                posonlyargs=[],
                args=[ast.arg(arg="comment_end")],
                kwonlyargs=[],
                kw_defaults=[],
                defaults=[],
            ),
            body=stmts,
            decorator_list=[],
        )
        mod = ast.Module(body=[fn], type_ignores=[])
        src = ast.unparse(ast.fix_missing_locations(mod))
        calls: list[str] = []
        # 2026-10-19：分支判据现在含 `started`（ffmpeg 是否真的起来了）。本用例执行的是生产
        # 源码的**真实语句块**，故必须把它一并注入命名空间——默认真值保持原断言语义不变。
        namespace: dict[str, Any] = {
            "started": started,
            "record_save_type": save_type,
            "save_file_path": f"D:/rec/a.{save_type.lower()}",
            "split_video_by_time": False,
            "_convert_after_record": lambda p, s: calls.append(p),
        }
        exec(compile(src, "<flv-branch>", "exec"), namespace)  # noqa: S102
        # comment_end=True 即「停止录制 / URL 被注释」导致的提前结束——修复前 FLV 在此路径
        # 直接 return，转码被跳过（已录内容永久留在 .flv）。
        namespace["_branch"](True)
        return calls

    @pytest.mark.parametrize("save_type,expected", [("FLV", 1), ("MKV", 0), ("MP4", 0)])
    def test_comment_end_convert_matrix(self, save_type: str, expected: int) -> None:
        # 修复前 FLV 在 comment_end 早退路径上是 0 次调用（已录内容永久留在 .flv）；
        # MKV/MP4 任何路径都必须是 0 次（成品容器不转码，历史行为不可改）。
        calls = self._drive(save_type)
        assert (
            len(calls) == expected
        ), f"{save_type} 在 comment_end 路径上转码调用次数应为 {expected}，实为 {len(calls)}"

    @pytest.mark.parametrize("save_type", ["FLV", "MKV", "MP4"])
    def test_not_started_never_converts(self, save_type: str) -> None:
        # 2026-10-19：ffmpeg 起不来时（Popen 抛 OSError / 二进制缺失）断言里既无产物也没有
        # 可转的文件，任何容器类型都不得提交转码——旧判据只看容器类型仍会转一次，把「本来就已失败」
        # 的一轮再包装成一条转码错误，真正原因被后一条日志盖住。
        assert self._drive(save_type, started=False) == []


# ────────────────────────────────────────────────────────────
# 该残留：分段枚举不得再走 glob
# ────────────────────────────────────────────────────────────


class TestNoGlobForSegmentEnumeration:
    def test_main_has_no_glob_call(self) -> None:
        # 分段枚举必须走 _segment_files（scandir + 字符串前缀/后缀判定）：glob 会把文件名
        # 里的方括号当字符类 → 恒返回空。main.py 内不得出现任何 Path.glob()/glob.glob() 调用。
        tree = ast.parse(MAIN_SRC.read_text(encoding="utf-8-sig"))
        offenders: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr == "glob":
                offenders.append(f"attr .glob @ line {node.lineno}")
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "glob":
                offenders.append(f"call glob() @ line {node.lineno}")
        assert offenders == [], f"main.py 内仍有 glob 调用: {offenders}"

    def test_no_glob_import(self) -> None:
        src = MAIN_SRC.read_text(encoding="utf-8-sig")
        assert re.search(r"^\s*(?:from|import)\s+glob\b", src, re.M) is None

    def test_segment_files_used_by_convert(self) -> None:
        # _convert_after_record 的分段枚举必须调用 _segment_files
        fn = inspect.getsource(main._convert_after_record)
        assert "_segment_files" in fn


# ════════════════════════════════════════════════════════════════════════════
# 2026-09-23 补口：main.py 内 9 处「回归锁：tests/…::test_xxx」注释此前**没有对应用例**，
# 本节按注释声称的判据逐条落地；写法优先「真调生产函数」，拿不到行为入口的才退化为 AST/静态锁。
# ════════════════════════════════════════════════════════════════════════════

_SHOPEE_UID_BASE = "https://live.shopee.sg/api/v1/live/play?item_id=123"


def _time_shim(**overrides: Any) -> types.SimpleNamespace:
    # 浅拷贝 stdlib time 的公开属性，只覆盖显式给出的那几个。绝不能 monkeypatch.setattr(main.time,
    # "sleep", ...)——main.time 就是 stdlib 模块本体，改它会波及同进程的 loguru enqueue 线程 /
    # harness 安全删除守护线程 / coverage；tests/test_test_hygiene.py 的 R1 也把这种写法直接判红。
    fresh = types.SimpleNamespace(**vars(time))
    for name, value in overrides.items():
        setattr(fresh, name, value)
    return fresh


class _PopenStub:
    # ffmpeg 子进程替身。必须是**类**且定义 __class_getitem__：check_subprocess 内层注解
    # `subprocess.Popen[bytes]` 在 def 时求值（main.py 未启用 from __future__ import annotations），
    # lambda 顶替报 not subscriptable，普通类报 type not subscriptable（AGENTS「FakePopen 必须是类」）。
    # 接线一律走 SimpleNamespace 浅拷贝 + setattr(main, "subprocess", shim)：直接改 stdlib Popen
    # 会让 harness 守护线程的 subprocess.run 先炸。子类覆写 poll_results / rc 即可，其余全部继承。
    poll_results: list[int | None] = [None]
    rc: int = 0
    started_at_tick: float | None = None

    def __class_getitem__(cls, item: Any) -> Any:
        return cls

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self._polled = 0
        self.returncode = self.rc

    def poll(self) -> int | None:
        # 前 len(poll_results) 次按表给出（None=存活），之后恒返回退出码
        if self._polled < len(self.poll_results):
            result = self.poll_results[self._polled]
            self._polled += 1
            return result
        return self.rc

    def wait(self, timeout: float = 0) -> int:
        return self.rc

    def terminate(self) -> None:
        return None

    def kill(self) -> None:
        return None

    @property
    def stdout(self) -> None:
        return None


class _CollectorStub:
    # 弹幕采集器替身：只记 start/stop 次数（生产语义「幂等 stop」由 src/collector 自己的用例锁）
    def __init__(self) -> None:
        self.start_calls = 0
        self.stop_calls = 0

    def start(self) -> None:
        self.start_calls += 1

    def stop(self) -> None:
        self.stop_calls += 1


def _prime_check_subprocess(
    monkeypatch: pytest.MonkeyPatch,
    popen_cls: type[_PopenStub],
    *,
    time_shim: types.SimpleNamespace | None = None,
    out_ts: str,
) -> dict[str, list]:
    # 装配 check_subprocess 运行所需的最小环境（只打桩子进程/网络/时钟/弹幕，不重写任何判定）
    calls: dict[str, list] = {"ok": [], "err": [], "term": [], "unregister": [], "marks": [], "release": []}
    sem = types.SimpleNamespace(acquire=lambda timeout=None: True, release=lambda: calls["release"].append(1))
    monkeypatch.setattr(main, "recording_semaphore", sem)
    monkeypatch.setattr(main, "exit_recording", False)
    monkeypatch.setattr(main, "recording_enabled", True)
    monkeypatch.setattr(main, "url_comments", set())
    monkeypatch.setattr(main, "recording", set())
    monkeypatch.setattr(main, "recording_time_list", {})
    monkeypatch.setattr(main, "running_list", [])
    monkeypatch.setattr(main, "record_state_lock", threading.Lock())
    monkeypatch.setattr(main, "enable_danmaku", False)
    monkeypatch.setattr(main, "enable_danmaku_monitor", False)
    monkeypatch.setattr(main, "danmaku_platforms", [])
    monkeypatch.setattr(main, "create_time_file", False)
    monkeypatch.setattr(main, "converts_to_mp4", False)
    monkeypatch.setattr(main, "delete_origin_file", False)
    monkeypatch.setattr(main, "register_ffmpeg_process", lambda proc: None)
    monkeypatch.setattr(main, "unregister_ffmpeg_process", lambda proc: calls["unregister"].append(proc))
    monkeypatch.setattr(main, "clear_ffmpeg_reject", lambda url, platform: None)
    monkeypatch.setattr(main, "mark_ffmpeg_reject", lambda url, platform: calls["marks"].append((url, platform)))
    monkeypatch.setattr(main, "record_success", lambda key=None: calls["ok"].append(key))
    monkeypatch.setattr(main, "record_error", lambda key=None: calls["err"].append(key))

    def _terminate(proc: Any, timeout: int = 30) -> bool:
        calls["term"].append(proc)
        return True

    monkeypatch.setattr(main, "_terminate_ffmpeg_process", _terminate)
    shim = types.SimpleNamespace(**vars(subprocess))
    shim.Popen = popen_cls
    monkeypatch.setattr(main, "subprocess", shim)
    if time_shim is None:
        time_shim = _time_shim(sleep=lambda seconds: None)
    monkeypatch.setattr(main, "time", time_shim)
    return calls


class TestSegmentTemplateSinglePercent:
    # ffmpeg 的 segment muxer 把输出路径当 printf 模板解释——除末位序号占位符外再出现裸 `%`
    # （主播名/标题里带的）就以 -22(EINVAL) 秒退，且失败码会被误归因成「容器不匹配」，进而落进
    # 「CDN 快速失败」把健康线路拉进探针退避。

    def test_segment_template_has_single_percent_placeholder(self, tmp_path: Any) -> None:
        # 行为用例：真调 main._build_record_output_path（生产函数本身拼模板）
        for save_type in ("TS", "FLV", "MKV", "MP4"):
            path = main._build_record_output_path(
                str(tmp_path), "主播100%名", "标题%d次", "260923_101112", save_type, True
            )
            assert path.count("%") == 1, f"{save_type} 分段模板残留多个 % : {path}"
            assert path.endswith("_%03d." + main._EXTENSION_BY_SAVE_TYPE.get(save_type, "ts")), path
            # 唯一幸存的 % 必须仍是序号占位符，否则 _is_segmented_output / SRT 分片对应全部错位
            assert main._is_segmented_output(path) is True, path
            assert "100" in path and "标题" in path, f"清洗把有效文件名字符一起吃掉了: {path}"

    def test_audio_template_uses_single_percent_placeholder(self, tmp_path: Any) -> None:
        for save_type, ext in (("MP3音频", "mp3"), ("M4A音频", "m4a")):
            path = main._build_record_output_path(
                str(tmp_path), "主播%名", "", "260923_101112", save_type, True, is_audio=True
            )
            assert path.count("%") == 1, f"{save_type} 音频分段模板残留多个 % : {path}"
            assert path.endswith("_%02d." + ext), path

    def test_non_segmented_output_has_no_percent_at_all(self, tmp_path: Any) -> None:
        # 非分段不走 segment muxer，但同一清洗照做：`%` 会再炸在录后转封装/合并环节
        for save_type in ("TS", "FLV", "MKV", "MP4"):
            path = main._build_record_output_path(str(tmp_path), "主播%名", "%标题", "260923_101112", save_type, False)
            assert "%" not in path, f"{save_type} 非分段输出仍含 % : {path}"

    def test_filename_filter_rstr_contains_percent(self) -> None:
        # 第一道防线（rstr 清洗）与第二道（_sanitize_output_name_base）互不替代：
        # rstr 由 src/stream_select.clean_name 经 main.rstr 消费，掉了 % 就等于放开入口面
        assert "%" in main.rstr, "rstr 必须过滤 `%`（SEV-2202 第一道防线）"

    def test_sanitizer_logs_a_warning_when_stripping(self) -> None:
        # 静默改名会让用户查不到「文件名怎么少了个 %」，必须留一条可检索告警
        seen: list[str] = []
        real_logger = main.logger

        class _SpyLogger:
            def __getattr__(self, name: str) -> Any:
                if name in ("warning", "error", "info", "debug"):
                    return lambda *a: seen.append(str(a[0]) if a else "")
                return getattr(real_logger, name)

        main.logger = cast(Any, _SpyLogger())
        try:
            main._sanitize_output_name_base("主播%名")
        finally:
            main.logger = real_logger
        assert any("主播%名" in line for line in seen), f"清洗未告警: {seen}"


class TestPlatformHostSchemeAgnostic:
    # 准入按 `url_host in PLATFORM_HOST`（与协议无关），分派却按子串匹配表项片段。
    # 表项一旦钉死 `https://`，`http://` 形态就是「准入通过 + 无解析器命中」→ _resolve_unrecognized
    # → sleep + continue 无限空转（永不录制、不记 record_error、白占监控位）。

    # PLATFORM_HOST 里两条非完整 host 的「前缀/后缀」条目（准入侧对 shopee 另有特判），
    # 用真实样例 host 代入，其余条目本身就是 host，直接拼 URL。
    _SAMPLE_HOSTS = {"live.shopee.": "live.shopee.sg", ".shp.ee": "s.shp.ee"}

    def test_every_platform_host_matches_without_scheme(self) -> None:
        unmatched: list[str] = []
        for entry in main.PLATFORM_HOST:
            host = self._SAMPLE_HOSTS.get(entry, entry)
            for scheme in ("http", "https"):
                url = f"{scheme}://{host}/123456"
                handlers = [handler.__name__ for matcher, handler in main._PLATFORM_RESOLVERS if matcher(url)]
                if not handlers:
                    unmatched.append(url)
        assert unmatched == [], f"以下准入地址无任何解析器命中（会无限空转）: {unmatched}"

    def test_xiaohongshu_http_and_https_hit_the_same_resolver(self) -> None:
        # 本轮修掉的第 8 条（该残留）：单点复现，避免上面的遍历将来因新增条目而漂移
        hit = {
            handler.__name__
            for matcher, handler in main._PLATFORM_RESOLVERS
            if matcher("http://www.xiaohongshu.com/1") or matcher("https://www.xiaohongshu.com/1")
        }
        assert hit == {"_resolve_xhslink_com"}, hit

    def test_no_resolver_fragment_pins_a_scheme(self) -> None:
        # 静态锁：分派表的匹配片段一律不得带 scheme（整个失效形态的族锁，比逐条遍历更直白）
        tree = ast.parse(MAIN_SRC.read_text(encoding="utf-8-sig"))
        offenders: list[str] = []
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)):
                continue
            if node.func.id not in {"_match_host", "_match_stream_suffix"}:
                continue
            for arg in node.args:
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str) and "://" in arg.value:
                    offenders.append(f"{node.func.id}({arg.value!r}) @ line {node.lineno}")
        assert offenders == [], f"匹配片段钉死协议，http/https 必有一侧空转: {offenders}"


class TestDiskLimitedRecoverable:
    # 磁盘限制必须是**可逆**的。exit_recording 是单向棘轮（全文件此前无处复位），用户清出
    # 空间后引擎仍活着但零录制、零提示。上一轮引入 disk_limited 时又把进入条件整条删了 → 首轮即置
    # 退出标志、recording 为空时 sys.exit(-1)，表现为「任何磁盘状态下启动即自行退出」。

    @staticmethod
    def _disk_block_src() -> str:
        tree = ast.parse(MAIN_SRC.read_text(encoding="utf-8-sig"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.If) or not isinstance(node.test, ast.Compare):
                continue
            left = node.test.left
            if not (isinstance(left, ast.Name) and left.id == "disk_free_gb"):
                continue
            assigned = {
                t.id
                for stmt in ast.walk(node)
                if isinstance(stmt, ast.Assign)
                for t in stmt.targets
                if isinstance(t, ast.Name)
            }
            if "disk_limited" in assigned and "exit_recording" in assigned:
                return ast.unparse(node)
        raise AssertionError("main.py 里找不到 `if disk_free_gb < disk_space_limit:` 磁盘限制块（SEV-2206 形态已丢失）")

    @classmethod
    def _drive(cls, **state: Any) -> tuple[bool, bool] | None:
        # 2026-10-21：判定块新增 `_disk_measure_failed`（本轮测量是否失败），
        # 它是 main() 循环体内的局部量、不在被抽取的 if/elif 块内赋值，故必须作为形参注入；
        # 取值由调用方显式给出，不在此补默认（「本轮没测到」与「测到且充足」是相反结论）。
        src = (
            "def _branch(disk_free_gb, disk_space_limit, disk_limited, exit_recording,"
            " recording, non_interactive, _disk_measure_failed):\n"
        )
        src += textwrap.indent(cls._disk_block_src(), "    ") + "\n"
        src += "    return disk_limited, exit_recording\n"
        ns: dict[str, Any] = {
            "logger": _QuietLogger(),
            "i18n": i18n,
            "sys": _SysStub(),
            "_shutdown_postprocess_executor": lambda: state["_shutdown"].append(1),
        }
        exec(compile(src, "<disk-block>", "exec"), ns)  # noqa: S102
        # 收敛点必须在「返回值」而不是「被调用对象」上：cast(Any, fn)(...) 的结果仍是 Any，
        # warn_return_any 照样报 no-any-return。ns 是 dict[str, Any]（exec 注入，静态无从推断），
        # 故显式收窄为本函数声明的类型，不牺牲运行期行为。
        return cast("tuple[bool, bool] | None", ns["_branch"](**{k: v for k, v in state.items() if k != "_shutdown"}))

    def test_disk_limited_is_recoverable(self) -> None:
        # ① 空间不足且仍有录制在跑 → 两个标志一起置位（停流但不退出）
        limited = self._drive(
            disk_free_gb=1.0,
            disk_space_limit=2.0,
            disk_limited=False,
            exit_recording=False,
            recording={"主播名"},
            non_interactive=False,
            _disk_measure_failed=False,
            _shutdown=[],
        )
        assert limited == (True, True), f"进入限制时未同时置位两标志: {limited}"
        # ② 空间恢复 → 两标志一起复位（exit_recording 不复位就是「暂停永不解除」）
        recovered = self._drive(
            disk_free_gb=99.0,
            disk_space_limit=2.0,
            disk_limited=True,
            exit_recording=True,
            recording=set(),
            non_interactive=False,
            _disk_measure_failed=False,
            _shutdown=[],
        )
        assert recovered == (False, False), f"空间恢复后未复位，房间线程不会被重新拉起: {recovered}"
        # ③ 复位后主循环的拉起闸门 `not exit_recording` 重新为真（行为可核对的口径）
        assert recovered is not None and recovered[1] is False

    def test_healthy_disk_does_not_enter_the_limit_branch(self) -> None:
        # 进入条件仍在位的行为面向：磁盘健康 + 从未受限 → 一条标志都不许动、不得置退出
        same = self._drive(
            disk_free_gb=99.0,
            disk_space_limit=2.0,
            disk_limited=False,
            exit_recording=False,
            recording=set(),
            non_interactive=False,
            _disk_measure_failed=False,
            _shutdown=[],
        )
        assert same == (False, False), f"进入条件被删成无条件进入 → 启动即自行退出: {same}"

    def test_disk_limit_exit_paths_split_by_mode(self) -> None:
        # 空间不足 + 无在录房间：Web（non_interactive）走 return 让线程干净退出、面板继续服务；
        # CLI/GUI 保留 sys.exit(-1)。两条路径都必须先排空录后线程池（该同族）。
        shutdown: list[int] = []
        web = self._drive(
            disk_free_gb=1.0,
            disk_space_limit=2.0,
            disk_limited=False,
            exit_recording=False,
            recording=set(),
            non_interactive=True,
            _disk_measure_failed=False,
            _shutdown=shutdown,
        )
        assert web is None, f"Web 模式应提前 return（不得 sys.exit 掉宿主线程）: {web}"
        assert shutdown == [1], "退出前未排空录后线程池"
        with pytest.raises(SystemExit) as excinfo:
            self._drive(
                disk_free_gb=1.0,
                disk_space_limit=2.0,
                disk_limited=False,
                exit_recording=False,
                recording=set(),
                non_interactive=False,
                _disk_measure_failed=False,
                _shutdown=[],
            )
        assert excinfo.value.code == -1, f"CLI/GUI 模式仍须 sys.exit(-1): {excinfo.value.code}"

    def test_entry_condition_still_in_place(self) -> None:
        # 静态锁（防再被删成无条件进入）：磁盘限制块的 test 必须仍是 disk_free_gb < disk_space_limit
        src = self._disk_block_src()
        assert src.startswith("if disk_free_gb < disk_space_limit:"), src.splitlines()[0]

    def test_flags_are_declared_global_in_main(self) -> None:
        # 复位要落到模块全局才有意义：main() 里缺 `global disk_limited` 时上面的写入只是局部变量
        tree = ast.parse(MAIN_SRC.read_text(encoding="utf-8-sig"))
        fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "main")
        declared: set[str] = set()
        for node in ast.walk(fn):
            if isinstance(node, ast.Global):
                declared.update(node.names)
        assert {"disk_limited", "exit_recording"} <= declared, "磁盘限制的可逆复位没有写回模块全局"


class TestDiskFullPauseCleanupStillRuns:
    # 2026-09-30：磁盘满暂停置位 exit_recording 后退出的房间线程也必须清 running_list。
    # 旧实现把 exit_recording=True 一律当「进程整体退出」跳过清理 → 暂停期退出的房间永久残留，
    # 空间恢复后主循环的「not in running_list」拉起条件恒假，全部房间不再被拉起。
    # 本类只锁「清理不再被 exit_recording 拦下」这半个不变量（reset 语义属于该那侧）。
    def test_room_thread_cleanup_survives_disk_full_pause(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import src.notify as notify_module

        monkeypatch.setattr(main, "exit_recording", True)
        monkeypatch.setattr(main, "running_list", ["https://room.example/1", "https://room.example/2"])
        monkeypatch.setattr(main, "monitoring", 2)
        notify_module.remove_room_from_running("https://room.example/1")
        assert main.running_list == ["https://room.example/2"], "磁盘满暂停期退出的房间未从 running_list 清理"
        assert main.monitoring == 1, "移除房间时未同步扣减监控计数"
        # 幂等：已被 clear_record_info 或上一轮移除的 URL 再次传入为无操作
        notify_module.remove_room_from_running("https://room.example/1")
        assert main.running_list == ["https://room.example/2"]
        assert main.monitoring == 1
        # 空串 URL 不做任何事（守卫保留）
        notify_module.remove_room_from_running("")
        assert main.running_list == ["https://room.example/2"]


class _QuietLogger:
    # 磁盘块 exec 时注入的静默 logger（生产代码里的告警不该刷进测试输出）
    def __getattr__(self, name: str) -> Any:
        return lambda *a, **k: None


class _SysStub:
    # 只用来把 sys.exit 变成可断言的异常（真实 sys.exit 抛 SystemExit；桩必须同形态，
    # 否则块内「sys.exit 之后的语句」会被误当成可达路径）
    def exit(self, code: int = 0) -> None:
        raise SystemExit(code)


class TestClockJudgements:
    # 时长判定（快速失败窗口 / 停滞窗口 / 单次时长上限）不得吃挂钟的跳变量——挂钟可被 NTP
    # 校时、手动改表、虚拟机挂起恢复拨动到任意值。

    @pytest.mark.parametrize(
        "wall_step, mono_step, expect_mark",
        [
            # 向前跳 7 小时：真实存活 1s（秒退）→ 必须仍判快速失败并记探针退避。
            # 旧判据（time.time() 差值）会算出 25200s → 逃过判定 → 坏线路无限重撞。
            (7 * 3600.0, 1.0, True),
            # 向后跳 7 小时：真实存活 60s（拉流中断/重连耗尽＝慢速失败）→ 不得判快速失败。
            # 旧判据算出 -25140s ≤ 20 → 把健康线路拉进探针退避。
            (-7 * 3600.0, 60.0, False),
        ],
        ids=["forward-jump-still-fast-fail", "backward-jump-not-fake-fast-fail"],
    )
    def test_fast_fail_judgement_ignores_wall_clock_jump(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
        wall_step: float,
        mono_step: float,
        expect_mark: bool,
    ) -> None:
        wall = {"now": 1_700_000_000.0}
        mono = {"now": 100.0}

        def _sleep(seconds: float) -> None:
            wall["now"] += wall_step
            mono["now"] += mono_step

        shim = _time_shim(
            time=lambda: wall["now"],
            monotonic=lambda: mono["now"],
            sleep=_sleep,
            strftime=lambda fmt, *a: "2026-09-23 00:00:00",
        )

        class _Popen(_PopenStub):
            poll_results = [None, 3436169992]  # 跑一拍即以 CDN 拒绝码退出
            rc = 3436169992

        calls = _prime_check_subprocess(monkeypatch, _Popen, time_shim=shim, out_ts="")
        out = tmp_path / "主播_2026-09-23_00-00-00.ts"
        assert (
            main.check_subprocess(
                "主播名",
                "https://www.huya.com/16028551",
                ["ffmpeg", "-i", "http://hs.hls.huya.com/src/x.m3u8", str(out)],
                "TS",
                None,
                platform="虎牙直播",
            )
            is False
        )
        # 挂钟确实被拨动过（否则这条用例什么都没测）
        assert abs(wall["now"] - 1_700_000_000.0) > main._FFMPEG_FAST_FAIL_SECONDS
        marked = [url for url, _plat in calls["marks"]]
        if expect_mark:
            assert marked == ["http://hs.hls.huya.com/src/x.m3u8"], "秒退未记入探针退避 → 房间无限重撞同一条死线路"
        else:
            assert marked == [], f"慢速失败被挂钟倒退误判成快速失败 → 误伤好线路: {marked}"
        assert calls["err"] == ["www.huya.com"]

    def test_watchdog_elapsed_ignores_wall_clock_jump(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        # 停滞判据同族：跳变后的第一次采样就「满 10 分钟」，旧实现会立刻杀掉健康录制，
        # 并向调度器投一条假 record_error（现按名义 sleep 时长累加，跳变量不进判定）
        wall = {"now": 1_700_000_000.0}
        ticks = {"n": 0}

        def _sleep(seconds: float) -> None:
            ticks["n"] += 1
            wall["now"] += 7 * 3600.0 if ticks["n"] == 5 else seconds

        shim = _time_shim(
            time=lambda: wall["now"],
            sleep=_sleep,
            strftime=lambda fmt, *a: "2026-09-23 00-00-00",
        )

        class _Popen(_PopenStub):
            # 存活 120 个守护轮后自然结束（远短于 10 分钟停滞窗口）
            poll_results = [None] * 120
            rc = 0

        calls = _prime_check_subprocess(monkeypatch, _Popen, time_shim=shim, out_ts="")
        out = tmp_path / "主播_2026-09-23_00-00-00.ts"
        out.write_bytes(b"\x00" * 4096)
        assert (
            main.check_subprocess(
                "主播名",
                "https://www.huya.com/16028551",
                ["ffmpeg", "-i", "http://hs.flv.huya.com/src/x.flv", str(out)],
                "TS",
                None,
                platform="虎牙直播",
            )
            is False
        )
        assert calls["term"] == [], "挂钟向前跳 7 小时不得把健康录制判成停滞并终止"
        assert calls["err"] == [], "停滞误杀会投一条假失败样本，污染按 host 的熔断统计"
        assert calls["ok"] == ["www.huya.com"]


class TestSubprocessUnwind:
    # 守护段抛错时的两条收尾不变量——弹幕采集器必被停止；进程已自然退出时 unregister /
    # clear_record_info 仍须执行（terminate 才需要存活判定）。

    def test_danmaku_collector_stopped_when_guard_section_raises(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        class _Popen(_PopenStub):
            poll_results = [None]
            rc = 0

        calls = _prime_check_subprocess(monkeypatch, _Popen, out_ts="")
        collector = _CollectorStub()
        monkeypatch.setattr(main, "get_danmaku_collector", lambda **kw: collector)
        monkeypatch.setattr(main, "enable_danmaku", True)
        monkeypatch.setattr(main, "danmaku_platforms", ["虎牙直播"])

        class _ExplodingDict(dict):
            # 现实形态：字幕线程 Thread.start() 抛「can't start new thread」（80+ 房间各持线程）
            def __setitem__(self, key: object, value: object) -> None:
                raise RuntimeError("can't start new thread")

        monkeypatch.setattr(main, "create_var", cast(Any, _ExplodingDict()))
        monkeypatch.setattr(main, "create_time_file", True)
        out = tmp_path / "主播_2026-09-23_00-00-00.ts"

        with pytest.raises(RuntimeError):
            main.check_subprocess(
                "主播名",
                "https://www.huya.com/16028551",
                ["ffmpeg", "-i", "http://hs.flv.huya.com/src/x.flv", str(out)],
                "TS",
                None,
                platform="虎牙直播",
                danmaku_args={"room": "1"},
            )
        assert collector.start_calls == 1
        assert collector.stop_calls >= 1, "弹幕采集器在守护段抛错时未被停止（SRT 句柄与采集线程双泄漏）"

    def test_finally_clears_state_when_process_already_exited(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        class _Popen(_PopenStub):
            # 一出生就已退出：poll 恒返回退出码
            poll_results: list[int | None] = []
            rc = 0

        calls = _prime_check_subprocess(monkeypatch, _Popen, out_ts="")
        monkeypatch.setattr(main, "recording", {"主播名"})
        monkeypatch.setattr(main, "recording_time_list", {"主播名": []})

        def _register_raises(proc: Any) -> None:
            raise RuntimeError("can't start new thread")

        monkeypatch.setattr(main, "register_ffmpeg_process", _register_raises)
        out = tmp_path / "主播_2026-09-23_00-00-00.ts"

        with pytest.raises(RuntimeError):
            main.check_subprocess(
                "主播名",
                "https://www.huya.com/16028551",
                ["ffmpeg", "-i", "http://hs.flv.huya.com/src/x.flv", str(out)],
                "TS",
            )
        assert len(calls["unregister"]) == 1, "进程已自然退出时也必须注销（否则 _ffmpeg_processes 只增不清）"
        assert main.recording == set(), "进程已自然退出时也必须回收 recording，否则面板恒显「录制中」"
        assert main.recording_time_list == {}
        assert calls["term"] == [], "进程已退出，terminate 仍应被跳过（存活判定只约束终止动作）"
        assert calls["release"] == [1], "finally 必须无条件归还录制槽"


class TestSegmentObservationTriState:
    # 后半：「观测失败」与「无匹配文件」不得同返 []，否则健康分段录制满 10 分钟被误杀。

    def test_segment_files_tri_state(self, tmp_path: Path) -> None:
        (tmp_path / "主播_000.ts").write_bytes(b"\x00" * 10)
        template = str(tmp_path / "主播_%03d.ts")
        assert main._segment_files(template) == [str(tmp_path / "主播_000.ts")]
        # 目录可读但没有分段 → [] （真实的「尚无产物」）
        empty = tmp_path / "空目录"
        empty.mkdir()
        assert main._segment_files(str(empty / "主播_%03d.ts")) == []
        # 目录不可读 → None（观测失败，绝不与 [] 混同）
        assert main._segment_files(str(tmp_path / "不存在的目录" / "主播_%03d.ts")) is None

    def test_record_output_bytes_distinguishes_none_from_minus_one(self, tmp_path: Path) -> None:
        (tmp_path / "主播_000.ts").write_bytes(b"\x00" * 120)
        assert main._record_output_bytes(str(tmp_path / "主播_%03d.ts"), True) == 120
        empty = tmp_path / "空目录"
        empty.mkdir()
        assert main._record_output_bytes(str(empty / "主播_%03d.ts"), True) == -1
        assert main._record_output_bytes(str(tmp_path / "nope" / "主播_%03d.ts"), True) is None

    def test_segment_observation_failure_is_not_stall(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        # 分段模板落在一个不存在的目录里（scandir 恒 OSError＝观测失败）：
        # 生产代码不得据此判停滞，ffmpeg 自然结束后按 rc==0 的正常链路收尾。
        class _Popen(_PopenStub):
            poll_results = [None] * 700  # 跑满 700 轮（> 10 分钟停滞窗口的累计秒数）
            rc = 0

        calls = _prime_check_subprocess(monkeypatch, _Popen, out_ts="")
        template = str(tmp_path / "产物目录尚未出现" / "主播_%03d.ts")
        assert (
            main.check_subprocess(
                "主播名",
                "https://www.huya.com/16028551",
                ["ffmpeg", "-i", "http://hs.hls.huya.com/src/x.m3u8", template],
                "TS",
                None,
                platform="虎牙直播",
            )
            is False
        )
        assert calls["term"] == [], "观测失败被当成「产物从未出现」→ 健康分段录制满 10 分钟被误杀"
        assert calls["err"] == []
        assert calls["ok"] == ["www.huya.com"]


class TestCredentialWritebackResilience:
    # 凭据回写的两个方向——「在播时必须落盘」与「落盘失败不得丢流」。

    @staticmethod
    def _patch_async(
        monkeypatch: pytest.MonkeyPatch, writes: list[tuple[str, str, str]], *, spider_returns: dict[str, Any]
    ) -> None:
        spider_shim = types.SimpleNamespace(**vars(spider))
        stream_shim = types.SimpleNamespace(**vars(stream))

        async def _spider(**kwargs: Any) -> dict[str, Any]:
            return spider_returns

        async def _stream(json_data: dict[str, Any], *args: Any, **kwargs: Any) -> dict[str, Any]:
            # 与生产一致：stream.get_stream_url 取到流时**新建** dict，不带 new_cookies
            # ——该失效形态正是「回写源错读到 port_info」
            return {"is_live": True, "anchor_name": "主播名", "durl": [{"url": "http://cdn/x.flv"}]}

        spider_shim.get_twitcasting_stream_url = cast(Any, _spider)
        spider_shim.get_shopee_stream_url = cast(Any, _spider)
        spider_shim.get_flextv_stream_data = cast(Any, _spider)
        stream_shim.get_stream_url = cast(Any, _stream)
        monkeypatch.setattr(main, "spider", spider_shim)
        monkeypatch.setattr(main, "stream", stream_shim)

        utils_shim = types.SimpleNamespace(**vars(utils))

        def _update_config(*args: Any, **kwargs: Any) -> None:
            writes.append(
                (
                    str(kwargs.get("section") or (args[1] if len(args) > 1 else "")),
                    str(kwargs.get("key") or (args[2] if len(args) > 2 else "")),
                    str(kwargs.get("new_value") or (args[3] if len(args) > 3 else "")),
                )
            )

        utils_shim.update_config = cast(Any, _update_config)
        monkeypatch.setattr(main, "utils", utils_shim)

    def test_twitcasting_persists_cookie_when_live(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # 在播 + 登录成功（json_data 带 new_cookies）→ 回写恰好一次，且值来自 json_data
        writes: list[tuple[str, str, str]] = []
        self._patch_async(monkeypatch, writes, spider_returns={"is_live": True, "new_cookies": "udid=abc;"})
        ctx = main._PlatformResolveContext("https://twitcasting.tv/example", None, "原画")
        main._resolve_twitcasting_tv(ctx)
        assert writes == [("Cookie", "twitcasting_cookie", "udid=abc;")], f"在播轮次未落盘 new_cookies: {writes}"
        assert ctx.port_info["is_live"] is True, "回写失败不得影响已拿到的流信息"

    def test_twitcasting_skips_writeback_when_no_new_cookies(self, monkeypatch: pytest.MonkeyPatch) -> None:
        writes: list[tuple[str, str, str]] = []
        self._patch_async(monkeypatch, writes, spider_returns={"is_live": True})
        main._resolve_twitcasting_tv(main._PlatformResolveContext("https://twitcasting.tv/example", None, "原画"))
        assert writes == []

    def test_flextv_cookie_writeback_failure_keeps_stream_url(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # 漏包的那一条：写盘抛 OSError 只许告警，不得把已拿到的流地址整轮丢弃
        writes: list[tuple[str, str, str]] = []
        self._patch_async(
            monkeypatch,
            writes,
            spider_returns={"new_cookies": "t=1", "play_url_list": {"masterUrl": "http://cdn/x.m3u8"}},
        )
        utils_shim = cast(types.SimpleNamespace, main.utils)

        def _boom(*args: Any, **kwargs: Any) -> None:
            raise OSError("Read-only file system")

        utils_shim.update_config = cast(Any, _boom)
        monkeypatch.setattr(main, "global_proxy", True)
        ctx = main._PlatformResolveContext("https://www.flextv.co.kr/channels/1", None, "原画")
        main._resolve_flextv_co_kr(ctx)  # 不得冒异常
        assert ctx.unrecognized is False, "凭据回写失败被冒成「未识别」→ 整轮流地址被丢弃"
        assert ctx.port_info.get("is_live") is True or ctx.port_info.get("durl"), ctx.port_info


class TestShopeeUrlSanitized:
    # Shopee 接口响应的 uid 段是半可信输入，拼出的 URL 会经 need_update_line_list 写进
    # URL_config.ini，而主循环用 `|` 分行、`,`/`，` 分字段、换行分行——含这些字符就等于把接口返回值
    # 升级成配置注入面；host 被改写则是第二道（同源）断言。

    @pytest.mark.parametrize(
        "uid",
        [
            "session_uid=abc&psid=def",  # 合法：常规 query 字符
            "session_uid=abc",
        ],
        ids=["plain-query", "minimal"],
    )
    def test_good_uid_is_appended_to_base_without_query(self, uid: str) -> None:
        got = main._build_shopee_record_url(_SHOPEE_UID_BASE, uid)
        assert got == _SHOPEE_UID_BASE.split("?")[0] + "?" + uid

    @pytest.mark.parametrize(
        "uid",
        [
            "session_uid=abc|https://evil.example/1",  # 行分隔符 → 截断本行
            "session_uid=abc,主播: 注入名",  # 字段分隔符 → 改写主播名字段
            "session_uid=abc，主播: 注入名",  # 全角逗号同样是分隔符
            "session_uid=abc\n#注入一行",  # 换行 → 往配置文件追加任意新行
            "session_uid=abc\r\ndef",  # CR 亦按行处理（CRLF 文件）
            "session uid=abc",  # 空格
            "",  # 空 uid 不写
            "sessión=1",  # 非白名单字符
        ],
    )
    def test_shopee_new_record_url_is_sanitized(self, uid: str) -> None:
        # 被测对象是 main.py 的 _build_shopee_record_url。不合格的 uid 段必须被**整段丢弃**（返回
        # 空串），调用方（start_record 的 `if new_record_url:`）因此不写配置 = 退回原 record_url。
        # 接线侧的端到端断言见下方 test_resolver_keeps_original_url_on_reject。
        assert main._build_shopee_record_url(_SHOPEE_UID_BASE, uid) == ""

    def test_accepted_url_always_keeps_the_original_host(self) -> None:
        # 第二道（同源）断言。诚实标注：uid 段过不了字符白名单里的 `@`，且 candidate 恒为
        # 「base 去 query + ? + uid」→ 现有实现下这条判定不可被 uid 触发，属**纵深防御**；
        # 因此只锁「被接受的回写地址必与原地址同源」，不谎称它抓得住注入。
        for base in (_SHOPEE_UID_BASE, "https://live.shopee.sg/x?token=1", "https://s.shp.ee/live/9"):
            for uid in ("a=1&b=2", "uid=1"):
                got = main._build_shopee_record_url(base, uid)
                assert got, f"合法 uid 被误拒: base={base} uid={uid}"
                assert urlsplit(got).hostname == urlsplit(base).hostname, got
                assert got.startswith(base.split("?")[0]), got

    def test_resolver_keeps_original_url_on_reject(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # 端到端接线：uid 不合格 → ctx.new_record_url 为空 → 调用方（start_record 的
        # `if new_record_url:`）不会写配置，行为与「未拿到 uid」一致（退回原 record_url）
        async def _spider(**kwargs: Any) -> dict[str, Any]:
            return {"is_live": True, "uid": "abc|https://evil.example/"}

        async def _stream(json_data: dict[str, Any], *args: Any, **kwargs: Any) -> dict[str, Any]:
            return {"is_live": True, "record_url": "http://cdn/x.flv"}

        spider_shim = types.SimpleNamespace(**vars(spider))
        stream_shim = types.SimpleNamespace(**vars(stream))
        spider_shim.get_shopee_stream_url = cast(Any, _spider)
        stream_shim.get_stream_url = cast(Any, _stream)
        monkeypatch.setattr(main, "spider", spider_shim)
        monkeypatch.setattr(main, "stream", stream_shim)

        ctx = main._PlatformResolveContext(_SHOPEE_UID_BASE, None, "原画")
        main._resolve_live_shopee(ctx)
        assert ctx.new_record_url == "", f"不合格 uid 仍被拼进回写地址: {ctx.new_record_url!r}"
        assert ctx.platform == "shopee"
        assert ctx.port_info.get("is_live") is True, "丢弃 uid 段不得连累本轮流信息"

    def test_resolver_writes_sanitized_url_when_uid_is_good(self, monkeypatch: pytest.MonkeyPatch) -> None:
        async def _spider(**kwargs: Any) -> dict[str, Any]:
            return {"is_live": True, "uid": "session_uid=abc"}

        async def _stream(json_data: dict[str, Any], *args: Any, **kwargs: Any) -> dict[str, Any]:
            return {"is_live": True, "record_url": "http://cdn/x.flv"}

        spider_shim = types.SimpleNamespace(**vars(spider))
        stream_shim = types.SimpleNamespace(**vars(stream))
        spider_shim.get_shopee_stream_url = cast(Any, _spider)
        stream_shim.get_stream_url = cast(Any, _stream)
        monkeypatch.setattr(main, "spider", spider_shim)
        monkeypatch.setattr(main, "stream", stream_shim)

        ctx = main._PlatformResolveContext(_SHOPEE_UID_BASE, None, "原画")
        main._resolve_live_shopee(ctx)
        assert ctx.new_record_url == "https://live.shopee.sg/api/v1/live/play?session_uid=abc"


class TestDirectDownloadUserAgent:
    # 强制直下的平台（shopee / 花椒）拿不到平台专属 UA 时必须回落 MOBILE_UA，否则 httpx
    # 以 `python-httpx/<版本>` 直发 → CDN 按 UA 风控拒（403），且函数头「与 ffmpeg 录制路径一致」是假的。

    @staticmethod
    def _install_httpx_capture(monkeypatch: pytest.MonkeyPatch, captured: dict[str, str]) -> None:
        class _Resp:
            status_code = 403

            def __enter__(self) -> "_Resp":
                return self

            def __exit__(self, *args: Any) -> None:
                return None

            def iter_bytes(self, chunk_size: int) -> Any:
                return iter([])

        class _Client:
            def __init__(self, **kwargs: Any) -> None:
                captured.update(kwargs.get("headers") or {})

            def __enter__(self) -> "_Client":
                return self

            def __exit__(self, *args: Any) -> None:
                return None

            def stream(self, method: str, url: str, **kwargs: Any) -> _Resp:
                captured.update(kwargs.get("headers") or {})
                return _Resp()

        # httpx 是全进程共享的三方模块本体 → 按该口径改走浅拷贝替身
        httpx_shim = types.SimpleNamespace(**vars(httpx))
        httpx_shim.Client = cast(Any, _Client)
        monkeypatch.setattr(main, "httpx", httpx_shim)

    @pytest.mark.parametrize(
        "platform_ua,expected", [("", main.MOBILE_UA), ("desktop-ua-for-huya", "desktop-ua-for-huya")]
    )
    def test_direct_download_always_sends_ua(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, platform_ua: str, expected: str
    ) -> None:
        captured: dict[str, str] = {}
        self._install_httpx_capture(monkeypatch, captured)
        monkeypatch.setattr(main, "get_record_headers", lambda *a, **k: {})
        # 花椒/shopee 这类「强制直下」平台在 get_record_user_agent 里返回空 → 必须回落常量
        monkeypatch.setattr(main, "get_record_user_agent", lambda *a, **k: platform_ua)

        assert (
            main.direct_download_stream(
                "http://cdn.example/live.flv",
                str(tmp_path / "out.flv"),
                "主播",
                "https://www.huajiao.com/1",
                "花椒直播",
            )
            is False
        )
        assert captured.get("User-Agent") == expected, (
            "直下路径 UA 缺失或被覆盖：空 UA 时 httpx 默认 python-httpx 会被 CDN 风控，"
            "平台专属 UA 时覆盖它会让 ffmpeg/直下两端指纹分叉"
        )

    def test_fallback_ua_is_the_same_constant_as_ffmpeg_path(self) -> None:
        # AGENTS「UA 双端一字不差」：回落值必须与 ffmpeg 拉流路径共用 stream_select.MOBILE_UA。
        # 延迟 import：src.stream_select 在模块级 import 会经 main 形成循环导入。
        from src import stream_select

        assert main.MOBILE_UA == stream_select.MOBILE_UA


class TestCredentialMasking:
    # 房间线程日志、熔断退避日志、直下日志三处曾原样入日志；
    # 且 scheduler.host_of 不剥 `user:pass@`，自定义流地址会把凭据带进熔断 key 与日志。

    def test_host_of_strips_userinfo(self) -> None:
        assert host_of("https://u:p@hw-hls-10.douyucdn.cn/app.m3u8?wsSecret=x") == "hw-hls-10.douyucdn.cn"
        assert host_of("http://user:pass@1.2.3.4:8080/live.flv") == "1.2.3.4:8080"
        # 无凭据形态逐字不变（保持既有 host 语义）
        assert host_of("https://live.douyin.com/123?a=1") == "live.douyin.com"
        assert host_of("https://www.huya.com/16028551") == "www.huya.com"
        assert host_of("http://[::1]:8080/x.m3u8") == "[::1]:8080"
        assert host_of("") == "unknown"
        # 同一真实 host 不因凭据不同被拆成多个熔断桶
        assert host_of("https://a:b@cdn.example/x.m3u8") == host_of("https://c:d@cdn.example/y.m3u8")

    def test_room_and_breaker_logs_mask_credentials(self) -> None:
        # 静态锁：这些 msgid 的 record_url / record_host 实参必须过 mask_credentials。行为侧位于
        # start_record 房间线程主循环内部，难以驱动，故按调用点判定——判据是「实参是 mask_credentials
        # 调用」而不是「源码里出现过这个词」。
        masked_msgids = {
            "检测到退出标志，录制线程退出: {record_url}",
            "录制已停止，房间线程退出: {record_url}",
            "[{record_url}]已被注释,本条线程将会退出",
            "[{record_host}] 并发熔断中，跳过本轮探测，退避 {_backoff}s",
            "Use Direct Downloader to Download FLV Stream: {record_url}",
            "无法识别的直播地址，本轮跳过: {record_url}",
        }
        tree = ast.parse(MAIN_SRC.read_text(encoding="utf-8-sig"))
        offenders: list[str] = []
        checked = 0
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
                continue
            if not (isinstance(node.func.value, ast.Name) and node.func.value.id == "i18n" and node.func.attr == "tr"):
                continue
            if not (node.args and isinstance(node.args[0], ast.Constant) and node.args[0].value in masked_msgids):
                continue
            checked += 1
            for kw in node.keywords:
                if kw.arg not in {"record_url", "record_host"}:
                    continue
                if "mask_credentials" not in ast.unparse(kw.value):
                    offenders.append(f"line {node.lineno}: {kw.arg} 未脱敏")
        assert checked == len(masked_msgids), f"目标调用点数量与预期不符（丢失或改名）: 找到 {checked} 处"
        assert offenders == [], f"凭据会明文进 PlayURL.log / streamget.log: {offenders}"


class TestPendingMainCatalog:
    # 本轮 main.py 新增的 tr 模板必须已并入四语目录（pending 袋子已随中央合并删除）。

    NEW_MSGIDS = [
        "分段目录不可读，跳过转换: {directory}",
    ]

    def test_catalogs_cover_main_new_msgids(self) -> None:
        _assert_registered(self.NEW_MSGIDS)

    def test_main_new_msgids_have_three_langs(self) -> None:
        _assert_translation_parity(self.NEW_MSGIDS)

    def test_runtime_templates_reachable_via_tr(self) -> None:
        # 占位符与关键字实参必须一一对齐，否则 tr 内部格式化失败后静默退回原文模板
        for msgid in self.NEW_MSGIDS:
            assert i18n.tr(msgid, directory="D:/rec") == msgid.replace("{directory}", "D:/rec")
