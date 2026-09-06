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

import importlib
import os
import re
import sys
import types
from pathlib import Path
from typing import Iterator

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
        monkeypatch.setattr(
            la,
            "datetime",
            types.SimpleNamespace(now=lambda: types.SimpleNamespace(strftime=lambda fmt: "20260830_120000")),
        )
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
        # 单文件改名失败（如句柄被第三方进程占用）仅告警跳过，其余文件照常归档且不抛异常
        real_rename = os.rename

        def fake_rename(src: str, dst: str) -> None:
            if os.path.basename(src) == "PlayURL.log":
                raise PermissionError(32, "模拟句柄被占用")
            real_rename(src, dst)

        monkeypatch.setattr(os, "rename", fake_rename)
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

    def test_reopen_streams_flag_controls_sink_readd(self, logs_dir: Path, fake_sink_ops: dict[str, list[str]]) -> None:
        # False（进程退出场景，atexit 传参）：只关闭+改名，不重建 sink；True（面板停止）：重建
        _touch(logs_dir, "streamget.log")
        assert la.archive_runtime_logs(reopen_streams=False)
        assert fake_sink_ops["remove"] and not fake_sink_ops["add"]
        _touch(logs_dir, "PlayURL.log")
        assert la.archive_runtime_logs(reopen_streams=True)
        assert fake_sink_ops["add"]


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


class TestMonitorHubCloseFile:
    def test_close_file_then_lazy_reopen(self, tmp_path: Path) -> None:
        # close_file 关闭边车句柄后，下一条事件写入经 _write_line 惰性重开，内容持续追加
        hub = DanmakuMonitorHub(log_path=str(tmp_path / "danmaku_monitor.jsonl"))
        path = tmp_path / "danmaku_monitor.jsonl"
        try:
            hub.room_message("roomA", "chat", "用户", "第一条")
            assert hub._file is not None
            size_before = path.stat().st_size
            hub.close_file()
            assert hub._file is None
            assert path.stat().st_size == size_before
            hub.room_message("roomA", "chat", "用户", "第二条")
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
