# 验证 GUI 父进程与录制进程的日志文件归属隔离（多进程句柄互锁的根因修复）：
# GUI 进程（gui.py）经 src.web_config → src/__init__ → src.logger 导入链也会初始化文件
# sink，若与录制子进程双开同一 logs/streamget.log，任一方到达轮转阈值（rotation="300 KB"）
# 都要 os.rename 改名，对方句柄未关即抛 PermissionError WinError 32——轮转永不成功、
# 该进程的文件日志自此全量静默丢失。修复后 GUI 进程只写本进程独占的 logs/gui.log，
# 绝不创建录制日志文件；录制进程行为不变。见 src/logger.py::GUI_PARENT_ENV。

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from typing import Iterator

import pytest
from loguru import logger

import src.logger as logger_mod


@pytest.fixture()
def reload_logger(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    # 把 _app_root() 的落点（sys.argv[0] 所在目录）指到 tmp_path，隔离 config/ logs/ 读写；
    # sys.stderr 置 None 跳过控制台 sink，用例仅关注文件 sink 的创建与否（add() 即建文件）。
    # 重载会清空全局 sink，退出时一并复位，避免 tmp 句柄/异步写线程泄漏给其他用例
    monkeypatch.setattr(sys, "argv", [str(tmp_path / "main.py")])
    monkeypatch.setattr(sys, "stderr", None)
    yield tmp_path
    logger.complete()
    logger.remove()
    logger_mod._console_sink_id = None


def _write_config(tmp_path: Path, enabled: str) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir(exist_ok=True)
    (config_dir / "config.ini").write_text(f"[录制设置]\n是否启用日志文件(是/否) = {enabled}\n", encoding="utf-8")


def test_recorder_process_owns_recording_log_files(reload_logger: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # 未设 GUI 标记（CLI / Web / GUI 拉起的录制子进程）：正常持有 streamget + PlayURL，不产生 gui.log
    monkeypatch.delenv(logger_mod.GUI_PARENT_ENV, raising=False)
    _write_config(reload_logger, "是")
    importlib.reload(logger_mod)
    assert (reload_logger / "logs" / "streamget.log").is_file()
    assert (reload_logger / "logs" / "PlayURL.log").is_file()
    assert not (reload_logger / "logs" / "gui.log").exists()


def test_gui_parent_process_writes_only_gui_log(reload_logger: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # GUI 父进程：只写本进程独占的 gui.log，绝不创建录制日志文件（多进程句柄互锁的根因）
    monkeypatch.setenv(logger_mod.GUI_PARENT_ENV, "1")
    _write_config(reload_logger, "是")
    importlib.reload(logger_mod)
    assert (reload_logger / "logs" / "gui.log").is_file()
    assert not (reload_logger / "logs" / "streamget.log").exists()
    assert not (reload_logger / "logs" / "PlayURL.log").exists()


def test_gui_parent_respects_log_file_disabled(reload_logger: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # 「是否启用日志文件(是/否)=否」对 GUI 进程同样生效：连 gui.log 也不建
    monkeypatch.setenv(logger_mod.GUI_PARENT_ENV, "1")
    _write_config(reload_logger, "否")
    importlib.reload(logger_mod)
    assert not (reload_logger / "logs" / "gui.log").exists()


def test_child_process_env_strips_marker(monkeypatch: pytest.MonkeyPatch) -> None:
    # 拉起录制子进程必须剔除标记（否则子进程被判为 GUI、录制日志全丢）并固定 UTF-8 输出
    monkeypatch.setenv(logger_mod.GUI_PARENT_ENV, "1")
    env = logger_mod.child_process_env({"PATH": "keep", "PYTHONIOENCODING": "gbk"})
    assert logger_mod.GUI_PARENT_ENV not in env
    assert env["PATH"] == "keep"
    assert env["PYTHONIOENCODING"] == "utf-8"
    # base 缺省时以当前进程环境为底，仅做剔除与编码固定、不丢其余变量
    probe = "DLR_CHILD_PROCESS_ENV_PROBE"
    monkeypatch.setenv(probe, "1")
    env_default_base = logger_mod.child_process_env()
    assert env_default_base[probe] == "1"


def test_gui_entry_sets_marker_before_src_import() -> None:
    # 静态回归锁：gui.py 的标记设置必须先于首个 src 导入（src.logger 在导入期即读标记，
    # 若先导入 src 再设标记，GUI 进程照样持有录制日志句柄，修复失效），
    # 且拉起子进程的 env 必须经 child_process_env() 构建
    marker_line = f'os.environ["{logger_mod.GUI_PARENT_ENV}"] = "1"'
    source = (Path(__file__).resolve().parents[1] / "gui.py").read_text(encoding="utf-8")
    marker_pos = source.find(marker_line)
    src_candidates = [pos for pos in (source.find("from src."), source.find("import src")) if pos != -1]
    assert marker_pos != -1, "gui.py 缺少 GUI 父进程标记设置"
    assert src_candidates, "gui.py 未找到 src 导入"
    assert marker_pos < min(src_candidates), "gui.py 的标记设置必须先于任何 src 导入"
    assert "child_process_env()" in source, "gui.py 拉起录制子进程必须经 child_process_env() 构建 env"
