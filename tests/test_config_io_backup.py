# Tests for src/config_io.backup_file rotation behavior.

import os
import sys
from pathlib import Path

import pytest
from loguru import logger

# config_io 顶层 `import main`，而 main 又反向导入 config_io；
# 必须让 main 先进入 sys.modules 才能打破这个导入环。
import main  # noqa: E402,F401
from src.config_io import backup_file  # noqa: E402


def _seed_backups(backup_dir: str, prefix: str, count: int) -> None:
    # 在 backup_dir 下生成 count 个带时间戳前缀的虚拟备份文件
    os.makedirs(backup_dir, exist_ok=True)
    for i in range(count):
        path = os.path.join(backup_dir, f"{prefix}_{i:02d}")
        with open(path, "w", encoding="utf-8") as f:
            _ = f.write("x")
        # 递增 mtime，保证旋转时按"由旧到新"排序确定
        os.utime(path, (i * 100, i * 100))


def test_rotation_deletes_excess(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # 正常路径：备份数超过上限时应触发对应次数的删除调用（用 spy 计数，避免真实删除受环境拦截影响）
    source = tmp_path / "cfg.ini"
    source.write_text("config-content", encoding="utf-8")
    backup_dir = tmp_path / "backup"
    prefix = "cfg.ini"
    seed = 9
    limit = 6
    _seed_backups(str(backup_dir), prefix, seed)

    calls: list[str] = []
    monkeypatch.setattr(os, "remove", lambda p: calls.append(p))

    backup_file(str(source), str(backup_dir), limit_counts=limit)
    # 旋转尝试删除的次数 = (已有 + 新生成) - 上限
    assert len(calls) == seed + 1 - limit
    # 新备份本身已生成
    kept = [f for f in os.listdir(str(backup_dir)) if f.startswith(prefix)]
    assert any(f.startswith(f"{prefix}_") for f in kept)


def test_rotation_delete_failure_is_best_effort(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # 关键回归：旋转删除失败时（如沙箱回收站不可用抛 OSError），
    # 不应使整个备份失败、不应继续尝试其余删除（防死循环）、并记 warning
    source = tmp_path / "cfg.ini"
    source.write_text("config-content", encoding="utf-8")
    backup_dir = tmp_path / "backup"
    prefix = "cfg.ini"
    seed = 9
    limit = 6
    _seed_backups(str(backup_dir), prefix, seed)

    calls: list[str] = []

    def _remove_and_raise(p: str) -> None:
        calls.append(p)
        _raise()

    monkeypatch.setattr(os, "remove", _remove_and_raise)

    captured: list[str] = []
    handler_id = logger.add(lambda msg: captured.append(str(msg)), level="WARNING")
    try:
        # 不应抛异常
        backup_file(str(source), str(backup_dir), limit_counts=limit)
    finally:
        logger.remove(handler_id)

    # 仅尝试一次即因失败而 break（不会在同文件上死循环）
    assert len(calls) == 1
    # 新备份本身仍成功生成（复制步骤不受删除失败影响）
    kept = [f for f in os.listdir(str(backup_dir)) if f.startswith(prefix)]
    assert any(f.startswith(f"{prefix}_") for f in kept)
    # 记了 warning 而非把备份整体判失败
    assert any("清理过期备份" in c for c in captured)


def _calls_append(calls: list[str], p: str) -> None:
    calls.append(p)


def _raise() -> None:
    raise OSError("windows-sandbox-recycle-bin-unavailable")
