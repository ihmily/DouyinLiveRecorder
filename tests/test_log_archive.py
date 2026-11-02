# 运行日志归档（停止录制流程收尾步骤）回归测试。
#
# 覆盖：
# 1. archive_runtime_logs：改名格式（原名_YYYYMMDD_HHMMSS.扩展名）、目标冲突追加 _N 序号、
#    文件缺失跳过、单文件改名失败不中断整批、GUI 父进程守卫、reopen_streams 语义
# 2. web_console.log：sys.stdout/stderr 绑定句柄的关闭-改名-重建轮转、
#    未绑定标准流的遗留文件仅改名不劫持 stdout
# 3. 弹幕监控边车：DanmakuMonitorHub.close_file() 关闭后下一条事件自动重开
# 4. src.logger 文件 sink：remove_file_sinks/add_file_sinks 往返与幂等、GUI/配置关闭时不注册
# 5. main.py atexit 注册顺序静态锁（atexit 为 LIFO，归档须先注册、后执行）
# 6. M-46 归档裁剪：按文件名时间戳保留最新 N 份 + 删除超龄份、活动文件与非归档名不碰、
#    裁剪必须落在全部关句柄步骤之后、单个删除失败只告警不中断归档
# 7. M-50 两处环境变量的布尔判定走全仓唯一入口（on/是/TRUE 这类写法必须真的生效）

import ast
import importlib
import inspect
import os
import re
import sys
import threading
import time
import types
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Iterator

import pytest
from loguru import logger

import src.log_archive as la
import src.logger as logger_mod
from src.danmaku_monitor import DanmakuMonitorHub


# 在隔离 logs 目录内创建一个待归档日志文件
def _touch(logs_dir: Path, name: str, content: str = "content") -> None:
    (logs_dir / name).write_text(content, encoding="utf-8")


@pytest.fixture()
def logs_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    # 把归档根目录指向 tmp_path：log_archive 以模块级 script_path 拼接 logs/，
    # 替换后全部文件操作都落在临时目录，不触碰仓库真实 logs/。
    # 同时 delenv 掉 conftest 设置的归档禁用开关与 GUI 守卫标记，归档用例才能正常执行
    monkeypatch.delenv(la._DISABLE_ENV, raising=False)
    monkeypatch.delenv(la.GUI_PARENT_ENV, raising=False)
    logs = tmp_path / "logs"
    logs.mkdir()
    monkeypatch.setattr(la, "script_path", str(tmp_path))
    return logs


@pytest.fixture()
def fake_sink_ops(monkeypatch: pytest.MonkeyPatch) -> dict[str, list[str]]:
    # 用记录器替身替换全局副作用点：loguru 文件 sink 的移除/重建、弹幕监控句柄关闭、
    # 控制台 sink 重建——编排类用例只验证调用编排与文件操作，不触碰全局 loguru 状态
    calls: dict[str, list[str]] = {"remove": [], "add": [], "close_monitor": [], "rebind": []}
    monkeypatch.setattr(la, "remove_file_sinks", lambda: calls["remove"].append("remove"))
    monkeypatch.setattr(la, "add_file_sinks", lambda: calls["add"].append("add"))
    monkeypatch.setattr(la, "close_monitor_file", lambda: calls["close_monitor"].append("close"))
    monkeypatch.setattr(la, "rebind_console_sink", lambda: calls["rebind"].append("rebind"))
    return calls


class TestArchiveRuntimeLogs:
    def test_renames_with_timestamp_and_keeps_extension(
        self, logs_dir: Path, fake_sink_ops: dict[str, list[str]]
    ) -> None:
        # 四个日志全部存在：逐一改名为 原名_YYYYMMDD_HHMMSS.扩展名，原路径不再存在
        for name in la.ARCHIVE_LOG_NAMES:
            _touch(logs_dir, name)
        archived = la.archive_runtime_logs()
        assert len(archived) == 4
        for name in la.ARCHIVE_LOG_NAMES:
            stem, ext = os.path.splitext(name)
            renamed = [os.path.basename(p) for p in archived if os.path.basename(p).startswith(stem)]
            assert len(renamed) == 1
            assert re.fullmatch(re.escape(stem) + r"_\d{8}_\d{6}" + re.escape(ext), renamed[0]), renamed[0]
            assert not (logs_dir / name).exists()
        # 默认 reopen_streams=True：进程继续运行场景须重建日志链路
        assert fake_sink_ops["remove"] and fake_sink_ops["add"] and fake_sink_ops["close_monitor"]

    def test_target_conflict_appends_sequence(
        self, logs_dir: Path, fake_sink_ops: dict[str, list[str]], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # 固定时间戳并预置同名归档目标：新归档追加 _1/_2 序号，绝不覆盖已有文件
        # [M-46 适配] 替身现在必须返回**真 datetime**：归档裁剪要算保留窗口下界
        # （datetime.now() - timedelta(days=...)），只带 strftime 的匿名对象会让裁剪步骤抛错、
        # 被外层 except 吞成「归档返回空列表」，把本用例打成假失败。
        monkeypatch.setattr(la, "datetime", types.SimpleNamespace(now=lambda: datetime(2026, 8, 30, 12, 0, 0)))
        _touch(logs_dir, "streamget.log")
        _touch(logs_dir, "streamget_20260830_120000.log")
        _touch(logs_dir, "streamget_20260830_120000_1.log")
        archived = la.archive_runtime_logs()
        assert archived == [str(logs_dir / "streamget_20260830_120000_2.log")]
        # 既有归档文件内容原封不动
        assert (logs_dir / "streamget_20260830_120000.log").read_text(encoding="utf-8") == "content"

    def test_missing_files_skipped(self, logs_dir: Path, fake_sink_ops: dict[str, list[str]]) -> None:
        # 目录为空（文件不存在）：全部跳过、不报错、返回空列表
        assert la.archive_runtime_logs() == []
        assert la.archive_runtime_logs(reopen_streams=False) == []

    def test_single_rename_failure_does_not_interrupt(
        self, logs_dir: Path, fake_sink_ops: dict[str, list[str]], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # 单文件改名失败（如句柄被第三方进程占用）仅告警跳过，其余文件照常归档且不抛异常。
        # M-27：`monkeypatch.setattr(os, "rename", ...)` 改的是**全进程唯一**的 os 模块本体，
        # 窗口内 loguru 文件轮转、弹幕边车、GUI/录制后台线程的 rename 会一并命中「遇 PlayURL.log
        # 就抛 PermissionError」这条规则，属跨用例竞态源。与本文件对 datetime 的处置同口径：
        # 替身只落进被测模块命名空间。
        real_rename = os.rename

        def fake_rename(src: str, dst: str) -> None:
            if os.path.basename(src) == "PlayURL.log":
                raise PermissionError(32, "模拟句柄被占用")
            real_rename(src, dst)

        monkeypatch.setattr(la, "os", types.SimpleNamespace(**{**vars(os), "rename": fake_rename}))
        # M-27 回归锁：替身只落进 src.log_archive 的命名空间；进程全局 os.rename 必须仍是真实现。
        # 恢复成 `monkeypatch.setattr(os, "rename", ...)` 形态时，这一行当场变红。
        assert os.rename is real_rename
        _touch(logs_dir, "streamget.log")
        _touch(logs_dir, "PlayURL.log")
        archived = la.archive_runtime_logs()
        names = [os.path.basename(p) for p in archived]
        assert len(names) == 1
        assert names[0].startswith("streamget_")
        assert (logs_dir / "PlayURL.log").exists()

    def test_disable_env_guard(
        self, logs_dir: Path, fake_sink_ops: dict[str, list[str]], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # 测试进程禁用开关（tests/conftest.py 设置）：置位时归档整体为 no-op，
        # pytest 退出不得改名开发者工作副本里的真实日志
        monkeypatch.setenv(la._DISABLE_ENV, "1")
        _touch(logs_dir, "streamget.log")
        assert la.archive_runtime_logs() == []
        assert (logs_dir / "streamget.log").exists()
        assert not fake_sink_ops["remove"]

    def test_gui_parent_guard(
        self, logs_dir: Path, fake_sink_ops: dict[str, list[str]], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # GUI 父进程（DLR_GUI_PARENT=1）不持有录制日志句柄，绝不能改名录制子进程正在写的日志
        monkeypatch.setenv(la.GUI_PARENT_ENV, "1")
        _touch(logs_dir, "streamget.log")
        assert la.archive_runtime_logs() == []
        assert (logs_dir / "streamget.log").exists()
        assert not fake_sink_ops["remove"]

    @pytest.mark.parametrize("marker", ["1", "true", "TRUE", "yes", "y", "on", "ON", "是", "t"])
    def test_disable_env_guard_accepts_every_documented_true_token(
        self, logs_dir: Path, fake_sink_ops: dict[str, list[str]], monkeypatch: pytest.MonkeyPatch, marker: str
    ) -> None:
        # M-50 回归锁：归档禁用开关必须走全仓唯一布尔入口（关键约定 #9 的 token 集合）。
        # 旧形态 `os.environ.get(...).strip().lower() in ("1","true","yes")` 认不出 on / y / t / 是，
        # 而开发者按配置口径写 DOUYIN_DISABLE_LOG_ARCHIVE=on 时归档照样执行——pytest 退出会把
        # 开发者工作副本里正在看的真实日志改名归档（AGENTS「风险控制」的清理越界同族故障）。
        monkeypatch.setenv(la._DISABLE_ENV, marker)
        _touch(logs_dir, "streamget.log")
        assert la.archive_runtime_logs() == []
        assert (logs_dir / "streamget.log").exists()
        assert not fake_sink_ops["remove"]

    @pytest.mark.parametrize("marker", ["1", "TRUE", "on", "是", "yes"])
    def test_gui_parent_guard_accepts_every_documented_true_token(
        self, logs_dir: Path, fake_sink_ops: dict[str, list[str]], monkeypatch: pytest.MonkeyPatch, marker: str
    ) -> None:
        # M-50 同族的第二处：GUI 父进程标记原先只认字符 "1"。DLR_GUI_PARENT=TRUE 时 GUI 进程
        # 照样进归档链路，与录制子进程抢同一批日志文件句柄（轮转 PermissionError + 文件日志全丢）
        monkeypatch.setenv(la.GUI_PARENT_ENV, marker)
        _touch(logs_dir, "streamget.log")
        assert la.archive_runtime_logs() == []
        assert (logs_dir / "streamget.log").exists()
        assert not fake_sink_ops["remove"]

    @pytest.mark.parametrize("marker", ["maybe", "", "  ", "2"])
    def test_guards_fall_back_to_archiving_for_unrecognized_values(
        self, logs_dir: Path, fake_sink_ops: dict[str, list[str]], monkeypatch: pytest.MonkeyPatch, marker: str
    ) -> None:
        # 默认值方向不得翻转：无法识别的取值按 default=False（未禁用 / 不是 GUI）处理，照旧归档。
        # 「写错一个字母就从此不归档」会让日志无限堆在原地，比误报更难被发现
        monkeypatch.setenv(la._DISABLE_ENV, marker)
        monkeypatch.setenv(la.GUI_PARENT_ENV, marker)
        _touch(logs_dir, "streamget.log")
        archived = la.archive_runtime_logs(reopen_streams=False)
        assert len(archived) == 1
        assert os.path.basename(archived[0]).startswith("streamget_")

    def test_reopen_streams_flag_controls_sink_readd(self, logs_dir: Path, fake_sink_ops: dict[str, list[str]]) -> None:
        # False（进程退出场景，atexit 传参）：只关闭+改名，不重建 sink；True（面板停止）：重建
        _touch(logs_dir, "streamget.log")
        assert la.archive_runtime_logs(reopen_streams=False)
        assert fake_sink_ops["remove"] and not fake_sink_ops["add"]
        _touch(logs_dir, "PlayURL.log")
        assert la.archive_runtime_logs(reopen_streams=True)
        assert fake_sink_ops["add"]


# M-46：归档裁剪。归档只改名不删除时，7×24 循环监测下每天数十次启停会让 logs/
# 无界增长；下列用例锁四件事——保留上限、保留窗口、排序一律取文件名时间戳（非 mtime）、
# 以及「裁剪必须落在全部关句柄步骤之后」（Windows 下句柄未关 os.remove 直接抛 WinError 32）。
class TestArchivePrune:
    # 固定「本轮归档时刻」：档案名与保留窗口下界都由它推出，用例不依赖真实当天日期
    _NOW = datetime(2026, 8, 30, 12, 0, 0)

    @pytest.fixture()
    def frozen_now(self, monkeypatch: pytest.MonkeyPatch) -> datetime:
        monkeypatch.setattr(la, "datetime", types.SimpleNamespace(now=lambda: self._NOW))
        return self._NOW

    @staticmethod
    def _names(logs_dir: Path, stem: str) -> list[str]:
        return sorted(p.name for p in logs_dir.glob(f"{stem}_*.log"))

    def test_prune_keeps_newest_by_name_and_drops_extra(
        self, logs_dir: Path, fake_sink_ops: dict[str, list[str]], monkeypatch: pytest.MonkeyPatch, frozen_now: datetime
    ) -> None:
        # 数量上限：超出最新 N 份的旧归档被删除，留下的恰是文件名时间戳最大的 N 份
        monkeypatch.setattr(la, "_ARCHIVE_MAX_KEEP", 3)
        for ts in ("20260829_000001", "20260829_000002", "20260829_000003", "20260829_000004"):
            _touch(logs_dir, f"streamget_{ts}.log")
        archived = la.archive_runtime_logs(reopen_streams=False)
        assert archived == []  # 本轮没有活动日志可归档，只清理历史
        assert self._names(logs_dir, "streamget") == [
            "streamget_20260829_000002.log",
            "streamget_20260829_000003.log",
            "streamget_20260829_000004.log",
        ]

    def test_prune_drops_archives_beyond_age_window(
        self, logs_dir: Path, fake_sink_ops: dict[str, list[str]], monkeypatch: pytest.MonkeyPatch, frozen_now: datetime
    ) -> None:
        # 时间上限与数量上限取**并集**删除：份数没超但已超龄的也必须删（否则常年只启停两三次的
        # 部署里 logs/ 仍会无限堆着几年前的归档）
        monkeypatch.setattr(la, "_ARCHIVE_MAX_KEEP", 50)
        monkeypatch.setattr(la, "_ARCHIVE_MAX_AGE_DAYS", 3)
        old = (frozen_now - timedelta(days=10)).strftime("%Y%m%d_%H%M%S")
        recent = (frozen_now - timedelta(days=1)).strftime("%Y%m%d_%H%M%S")
        _touch(logs_dir, f"streamget_{old}.log")
        _touch(logs_dir, f"streamget_{recent}.log")
        la.archive_runtime_logs(reopen_streams=False)
        assert self._names(logs_dir, "streamget") == [f"streamget_{recent}.log"]

    def test_prune_orders_by_name_not_mtime(
        self, logs_dir: Path, fake_sink_ops: dict[str, list[str]], monkeypatch: pytest.MonkeyPatch, frozen_now: datetime
    ) -> None:
        # 排序判据必须是文件名里的时间戳：取证时拷贝日志、杀软扫描、同步工具都会把 mtime 改成
        # 与生成顺序相反的形态，按 mtime 保留「最新 N 份」会删掉真正最新的归档。
        # 本用例把最旧的档案打上一个**未来的** mtime：按 mtime 它会活下来，按名字它必须被删。
        monkeypatch.setattr(la, "_ARCHIVE_MAX_KEEP", 1)
        _touch(logs_dir, "streamget_20260820_000000.log")
        _touch(logs_dir, "streamget_20260829_000000.log")
        future = frozen_now.timestamp() + 86400
        os.utime(str(logs_dir / "streamget_20260820_000000.log"), (future, future))
        la.archive_runtime_logs(reopen_streams=False)
        assert self._names(logs_dir, "streamget") == ["streamget_20260829_000000.log"]

    def test_prune_never_touches_live_logs_or_non_archive_names(
        self, logs_dir: Path, monkeypatch: pytest.MonkeyPatch, frozen_now: datetime
    ) -> None:
        # 只认 <基名>_<YYYYMMDD_HHMMSS>[_N].<扩展名> 这一种名字：活动日志本体（下一轮还要继续写）、
        # 同前缀但时间戳形态不合法的文件、扩展名不符的文件一律不碰。
        # 这里**直接调用**裁剪函数：经 archive_runtime_logs 走一遍的话活动文件会先被改名归档，
        # 「活动日志不被裁剪删除」这条判据就永远观察不到。
        monkeypatch.setattr(la, "_ARCHIVE_MAX_KEEP", 0)
        _touch(logs_dir, "streamget.log")
        _touch(logs_dir, "streamget_notes.log")
        _touch(logs_dir, "streamget_20260829_00000.txt")
        _touch(logs_dir, "PlayURL_20260829_000000.log")
        _touch(logs_dir, "PlayURL_20260829_000000_1.log")
        cutoff = (frozen_now - timedelta(days=la._ARCHIVE_MAX_AGE_DAYS)).strftime("%Y%m%d_%H%M%S")
        la._prune_archives(str(logs_dir), cutoff)
        assert (logs_dir / "streamget.log").is_file()
        assert (logs_dir / "streamget_notes.log").is_file()
        assert (logs_dir / "streamget_20260829_00000.txt").is_file()
        # 同一时刻的冲突序号（_1）各算一份归档、同样被识别；数量上限 0 → 两支都被清理
        assert self._names(logs_dir, "PlayURL") == []

    def test_prune_is_per_stem(
        self, logs_dir: Path, fake_sink_ops: dict[str, list[str]], monkeypatch: pytest.MonkeyPatch, frozen_now: datetime
    ) -> None:
        # 每个基名各算各的额度：四个运行日志互不挤占（否则 streamget 的几十份归档会把
        # danmaku_monitor 的历史清空）
        monkeypatch.setattr(la, "_ARCHIVE_MAX_KEEP", 1)
        monkeypatch.setattr(la, "_ARCHIVE_MAX_AGE_DAYS", 3650)
        _touch(logs_dir, "streamget_20260829_000001.log")
        _touch(logs_dir, "streamget_20260829_000002.log")
        _touch(logs_dir, "danmaku_monitor_20260829_000001.jsonl")
        la.archive_runtime_logs(reopen_streams=False)
        assert self._names(logs_dir, "streamget") == ["streamget_20260829_000002.log"]
        assert [p.name for p in logs_dir.glob("danmaku_monitor_*.jsonl")] == ["danmaku_monitor_20260829_000001.jsonl"]

    def test_prune_remove_failure_warns_and_does_not_abort(
        self,
        logs_dir: Path,
        fake_sink_ops: dict[str, list[str]],
        monkeypatch: pytest.MonkeyPatch,
        frozen_now: datetime,
    ) -> None:
        # 单个删除失败（第三方进程占用句柄/只读属性）只留一条 warning：其余照删、归档照做、
        # 绝不向调用方（面板「停止录制」与 atexit）抛异常
        monkeypatch.setattr(la, "_ARCHIVE_MAX_KEEP", 1)
        _touch(logs_dir, "streamget.log")
        _touch(logs_dir, "streamget_20260829_000001.log")
        _touch(logs_dir, "streamget_20260829_000002.log")
        _touch(logs_dir, "streamget_20260829_000003.log")
        real_remove = os.remove
        victim = logs_dir / "streamget_20260829_000002.log"

        def _deny_remove(path: Any, *args: Any, **kwargs: Any) -> None:
            if os.path.basename(str(path)) == victim.name:
                raise PermissionError(32, "模拟句柄被占用", str(path))
            real_remove(path, *args, **kwargs)

        # M-27 口径：stdlib 替身只落进被测模块命名空间，不污染进程全局 os
        monkeypatch.setattr(la, "os", types.SimpleNamespace(**{**vars(os), "remove": _deny_remove}))
        assert os.remove is real_remove  # 反向见证：替身没有改掉全局
        captured: list[str] = []
        sink_id = logger.add(lambda msg: captured.append(str(msg)), level="WARNING")
        try:
            archived = la.archive_runtime_logs(reopen_streams=False)
        finally:
            logger.remove(sink_id)
        assert len(archived) == 1 and os.path.basename(archived[0]).startswith("streamget_")
        assert victim.is_file(), "删除失败被静默吞掉：本份归档应仍在原地"
        assert not (logs_dir / "streamget_20260829_000001.log").exists(), "同批其余归档被一次删除失败连带中断"
        assert any(victim.name in line for line in captured), captured

    def test_prune_runs_after_every_handle_close_step(
        self,
        logs_dir: Path,
        fake_sink_ops: dict[str, list[str]],
        monkeypatch: pytest.MonkeyPatch,
        frozen_now: datetime,
    ) -> None:
        # 接线顺序硬锁：裁剪必须看到「loguru sink 已 remove、边车已 close、web_console 已关」之后
        # 的时刻，Windows 下才不会撞 WinError 32；同时必须早于 add_file_sinks() 重新开句柄。
        # 判据取「真实调用顺序」而非源码行号：把 _prune_archives 换成记账替身，记录它被调用时
        # 各关句柄替身已经跑过几次。
        seen: dict[str, object] = {}
        real_prune = la._prune_archives

        def _spy_prune(logs: str, cutoff: str) -> None:
            seen["after_remove"] = list(fake_sink_ops["remove"])
            seen["after_close_monitor"] = list(fake_sink_ops["close_monitor"])
            seen["after_add"] = list(fake_sink_ops["add"])
            seen["cutoff"] = cutoff
            real_prune(logs, cutoff)

        monkeypatch.setattr(la, "_prune_archives", _spy_prune)
        _touch(logs_dir, "streamget.log")
        _touch(logs_dir, "PlayURL.log")
        assert len(la.archive_runtime_logs(reopen_streams=True)) == 2
        assert seen["after_remove"] == ["remove"], "裁剪跑在 remove_file_sinks() 之前（句柄未关即删）"
        assert seen["after_close_monitor"] == ["close"], "裁剪跑在边车 close_monitor_file() 之前"
        assert seen["after_add"] == [], "裁剪必须早于 add_file_sinks() 重新开句柄"
        assert seen["cutoff"] == (frozen_now - timedelta(days=la._ARCHIVE_MAX_AGE_DAYS)).strftime("%Y%m%d_%H%M%S")

    def test_archive_runtime_logs_source_orders_prune_last(self) -> None:
        # 源码结构锁（与上一条互为见证，判据取 AST 调用节点而不是文本 index：本函数里的解释性
        # 注释也会提到这些函数名，纯文本 index 会先命中注释）。
        # 锁的是接线：_prune_archives 的调用点必须晚于三处关句柄动作、早于 add_file_sinks()。
        tree = ast.parse(inspect.getsource(la.archive_runtime_logs))
        lines: dict[str, int] = {}
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = getattr(func, "id", None) or getattr(func, "attr", None)
            if name in {"remove_file_sinks", "close_monitor_file", "_archive_web_console", "add_file_sinks"}:
                lines[name] = min(lines.get(name, node.lineno), node.lineno)
        prune_node = next(
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "_prune_archives"
        )
        for closer in ("remove_file_sinks", "close_monitor_file", "_archive_web_console"):
            assert lines[closer] < prune_node.lineno, f"裁剪跑在 {closer}() 之前（Windows 下句柄未关即删）"
        assert prune_node.lineno < lines["add_file_sinks"], "裁剪必须早于 add_file_sinks() 重新开句柄"


class TestWebConsoleRotation:
    def test_bound_stream_rotated_and_rebound(
        self, logs_dir: Path, fake_sink_ops: dict[str, list[str]], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # web.py 后台模式形态：sys.stdout/stderr 同指 web_console.log。
        # 归档须先关句柄再改名，改名后重建全新同名文件并重新接管标准流与控制台 sink
        path = logs_dir / "web_console.log"
        handle = open(path, "a", encoding="utf-8", buffering=1)
        try:
            handle.write("before-stop\n")
            handle.flush()
            monkeypatch.setattr(sys, "stdout", handle)
            monkeypatch.setattr(sys, "stderr", handle)
            archived = la.archive_runtime_logs(reopen_streams=False)
            assert len(archived) == 1
            assert os.path.basename(archived[0]).startswith("web_console_")
            assert handle.closed  # 改名前已 flush+close（Windows 下句柄未关 rename 必失败）
            assert path.is_file()  # 全新同名文件已重建
            new_stream = sys.stdout
            assert new_stream is not None and not new_stream.closed
            assert new_stream.name == str(path)
            assert fake_sink_ops["rebind"]  # 控制台 sink 已重建
        finally:
            # 收尾关闭归档后重建的句柄，避免 ResourceWarning；monkeypatch 负责还原标准流
            stream = sys.stdout
            if stream is not None and not stream.closed:
                stream.close()
            if not handle.closed:
                handle.close()

    def test_stale_file_without_bound_stream_renamed_only(
        self, logs_dir: Path, fake_sink_ops: dict[str, list[str]]
    ) -> None:
        # 遗留的 web_console.log 未绑定任何标准流（如 CLI 进程内）：仅改名，
        # 绝不把当前 stdout 重定向到日志文件
        original_stdout = sys.stdout
        _touch(logs_dir, "web_console.log")
        archived = la.archive_runtime_logs(reopen_streams=False)
        assert len(archived) == 1
        assert sys.stdout is original_stdout
        assert not fake_sink_ops["rebind"]

    def test_concurrent_print_inside_archive_window_does_not_raise(
        self, logs_dir: Path, fake_sink_ops: dict[str, list[str]], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # M-09 回归锁：改名窗口内其它线程 print() 不得抛 ValueError: I/O operation on closed file。
        # 旧顺序「flush+close → os.rename → _rebind_web_console」期间 sys.stdout/sys.stderr 仍指向
        # **已关闭对象**，Windows 慢盘/杀软扫描会把窗口从微秒放大到秒级，Web 请求线程的 print()
        # 落在里面就崩。取证手法：os.rename 换成「先睡 0.3s、再打一条、最后真改名」的替身，
        # 睡眠段即被人为放大的归档窗口（旧顺序下此刻标准流已关、替身尚未接管），另起一支线程
        # 整窗口持续 print()。判据：① 两支打印都不许抛；② 窗口内那条输出最终并入重建后的新文件
        # （替身不是黑洞）。按 M-27/MT-11 口径，替身只落进 src.log_archive 命名空间。
        path = logs_dir / "web_console.log"
        real_rename = os.rename
        marker = "窗口内主线程打印的一行\n"

        def _slow_rename(src: str, dst: str) -> None:
            time.sleep(0.3)
            print(marker, end="")
            real_rename(src, dst)

        monkeypatch.setattr(la, "os", types.SimpleNamespace(**{**vars(os), "rename": _slow_rename}))
        assert os.rename is real_rename  # 反向见证：替身没有污染进程全局

        errors: list[str] = []
        stop = threading.Event()

        def _hammer() -> None:
            # 一支「其它线程」在归档全程持续 print；命中已关闭标准流时 ValueError 会被记下来
            while not stop.is_set():
                try:
                    print("并发输出\n", end="")
                except Exception as e:
                    # 本线程的职责就是把「窗口内 print() 是否抛」原样带回主线程断言；
                    # 记下第一条即退出，避免旧形态下每条都抛同一异常刷满 errors
                    errors.append(f"{type(e).__name__}: {e}")
                    return
                time.sleep(0.002)

        handle = open(path, "a", encoding="utf-8", buffering=1)
        hammer = threading.Thread(target=_hammer, name="dlr-archive-print-hammer")
        try:
            handle.write("before-stop\n")
            handle.flush()
            monkeypatch.setattr(sys, "stdout", handle)
            monkeypatch.setattr(sys, "stderr", handle)
            hammer.start()
            try:
                archived = la.archive_runtime_logs(reopen_streams=False)
            finally:
                stop.set()
                hammer.join(timeout=5)
            assert not hammer.is_alive(), "打印线程未退出（很可能卡在已关闭的标准流上）"
            assert errors == [], f"归档窗口内 print() 抛异常: {errors}"
            assert any(os.path.basename(p).startswith("web_console_") for p in archived), archived
            assert handle.closed, "改名前未关闭原句柄（Windows 下 rename 必失败）"
            stream = sys.stdout
            assert stream is not handle and not stream.closed
            assert stream.name == str(path)
            assert fake_sink_ops["rebind"]
            stream.flush()
            assert marker in path.read_text(encoding="utf-8"), "窗口期内经替身缓存的输出未并入新文件"
        finally:
            stop.set()
            if hammer.is_alive():
                hammer.join(timeout=5)
            stream = sys.stdout
            if stream is not None and not stream.closed and stream is not handle:
                stream.close()
            if not handle.closed:
                handle.close()


class TestMonitorHubCloseFile:
    def test_close_file_then_lazy_reopen(self, tmp_path: Path) -> None:
        # close_file 关闭边车句柄后，下一条事件写入经 _write_line 惰性重开，内容持续追加
        hub = DanmakuMonitorHub(log_path=str(tmp_path / "danmaku_monitor.jsonl"))
        path = tmp_path / "danmaku_monitor.jsonl"
        try:
            hub.room_message("roomA", "chat", "用户", "第一条")
            # MT-07：MID-25 之后落盘在独立边车写线程，任何「读磁盘 / 读句柄登记表」之前必须先
            # 排空队列。`hub._file` 内部的 drain **不带断言**，超时（慢盘 / 队列被占满）即返回 None，
            # 于是「首条事件尚未落盘」会表现为 size_before=0 或 _file is None 的随机假红；
            # 显式 `assert hub.flush()` 把「队列没排空」与「行为真的错了」两种故障分开（口径同
            # tests/test_regression_infra.py::TestSidecarArchiveWindow）。
            assert hub.flush()
            assert hub._file is not None
            size_before = path.stat().st_size
            hub.close_file()
            assert hub.flush()
            assert hub._file is None
            assert path.stat().st_size == size_before
            hub.room_message("roomA", "chat", "用户", "第二条")
            assert hub.flush()
            assert hub._file is not None
            assert path.stat().st_size > size_before
        finally:
            hub.close_file()

    def test_close_file_idempotent_without_handle(self, tmp_path: Path) -> None:
        # 无句柄（未写过文件）与重复关闭均为幂等 no-op，不抛异常
        hub = DanmakuMonitorHub(log_path=str(tmp_path / "danmaku_monitor.jsonl"))
        hub.close_file()
        hub.close_file()
        assert hub._file is None


class TestLoggerFileSinkOps:
    @pytest.fixture()
    def reload_logger(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
        # 复用 test_logger_gui_parent 的隔离模式：argv 指向 tmp 隔离 script_path，
        # stderr 置 None 跳过控制台 sink；重载产生的全局 sink 在退出时统一清空复位
        monkeypatch.setattr(sys, "argv", [str(tmp_path / "main.py")])
        monkeypatch.setattr(sys, "stderr", None)
        yield tmp_path
        logger.complete()
        logger.remove()
        logger_mod._console_sink_id = None
        logger_mod._streamget_sink_id = None
        logger_mod._playurl_sink_id = None

    @staticmethod
    def _write_config(tmp_path: Path, enabled: str) -> None:
        config_dir = tmp_path / "config"
        config_dir.mkdir(exist_ok=True)
        (config_dir / "config.ini").write_text(f"[录制设置]\n是否启用日志文件(是/否) = {enabled}\n", encoding="utf-8")

    def test_remove_then_add_roundtrip_and_idempotent(
        self, reload_logger: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv(logger_mod.GUI_PARENT_ENV, raising=False)
        self._write_config(reload_logger, "是")
        importlib.reload(logger_mod)
        assert logger_mod._streamget_sink_id is not None
        assert logger_mod._playurl_sink_id is not None
        logger_mod.remove_file_sinks()
        assert logger_mod._streamget_sink_id is None
        assert logger_mod._playurl_sink_id is None
        logger_mod.remove_file_sinks()  # 已移除后重复移除：幂等 no-op
        logger_mod.add_file_sinks()
        assert logger_mod._streamget_sink_id is not None
        assert logger_mod._playurl_sink_id is not None
        # loguru add() 即创建全新同名文件：归档改名后重建 sink 即恢复日志写入
        assert (reload_logger / "logs" / "streamget.log").is_file()
        assert (reload_logger / "logs" / "PlayURL.log").is_file()

    def test_add_file_sinks_noop_when_gui_or_disabled(
        self, reload_logger: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv(logger_mod.GUI_PARENT_ENV, "1")
        self._write_config(reload_logger, "否")
        importlib.reload(logger_mod)
        logger_mod.remove_file_sinks()
        logger_mod.add_file_sinks()
        assert logger_mod._streamget_sink_id is None
        assert logger_mod._playurl_sink_id is None


def test_main_registers_archive_before_cleanup_atexit() -> None:
    # 静态回归锁：atexit 为 LIFO，归档必须先于两个 cleanup 注册，
    # 才能在 ffmpeg 清理等收尾日志落盘之后最后执行（close_all_clients → cleanup → archive）
    source = (Path(__file__).resolve().parents[1] / "main.py").read_text(encoding="utf-8")
    archive_pos = source.find("atexit.register(archive_runtime_logs")
    cleanup_pos = source.find("atexit.register(cleanup_all_ffmpeg_processes)")
    clients_pos = source.find("atexit.register(close_all_clients_sync)")
    assert archive_pos != -1, "main.py 缺少归档 atexit 注册"
    assert cleanup_pos != -1 and clients_pos != -1
    assert archive_pos < cleanup_pos < clients_pos, "归档必须先于 cleanup 注册（LIFO 后执行）"
    register_line = source[archive_pos : source.find("\n", archive_pos)]
    assert "reopen_streams=False" in register_line, "进程退出场景归档不重建 sink（下次启动自然重建）"
