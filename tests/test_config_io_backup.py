# src/config_io.backup_file 的备份轮换与备份脱敏回归用例（写侧契约，读侧见 test_config_io_readonly.py）。

import configparser
import os
import sys
import types
from pathlib import Path
from typing import Any

import pytest
from loguru import logger

# config_io 顶层 `import main`，而 main 又反向导入 config_io；
# 必须让 main 先进入 sys.modules 才能打破这个导入环。
import main  # noqa: E402,F401
from src import config_io  # noqa: E402
from src.config_io import backup_file  # noqa: E402


def _os_shim(**overrides: Any) -> types.SimpleNamespace:
    # 不得 `monkeypatch.setattr(os, "remove", 替身)`——monkeypatch 解析到的是**全进程唯一**
    # 的 os 模块本体，替身窗口内 loguru 的轮转删除、其他后台线程的重命名会一并被换成 no-op
    # （本文件的删除替身正是「只记账不删除」）。仓内约定：浅拷贝一份命名空间，只替换需要的
    # 1~2 个属性，再把替身绑到**被测模块自己的 os 引用**上（其余属性仍是真实现）。
    shim = types.SimpleNamespace(**vars(os))
    for name, value in overrides.items():
        setattr(shim, name, value)
    return shim


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
    real_remove = os.remove
    # 只替换 config_io 命名空间里的 os.remove，进程其余部分（loguru / 其他后台线程）不受影响
    monkeypatch.setattr(config_io, "os", _os_shim(remove=lambda p: calls.append(p)))
    # 替身必须只落在被测模块的命名空间里。恢复成 `setattr(os, "remove", ...)`
    # （全进程唯一 os 本体）时，紧跟着这一行就会变红。
    assert os.remove is real_remove

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

    # 同样只替换 config_io 命名空间的 os.remove——本用例要的正是「删除抛 OSError」这一条
    # 分支，替身挂在被测模块上即可精确命中，不会把全进程的删除都变成抛异常。
    real_remove = os.remove
    monkeypatch.setattr(config_io, "os", _os_shim(remove=_remove_and_raise))
    # 回归锁同 test_rotation_deletes_excess：进程全局 os.remove 不得在替身窗口内被换掉
    assert os.remove is real_remove

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


# ---- MID-N57 回归锁：备份脱敏必须与面板侧 read_config_safe（web_config ）同口径双判据
# 「键名/节命中 **或** 值本身形如凭据」。本组用例走 backup_file 端到端（真实 _redact_ini_secrets
# 路径，不打桩），仅用 tmp_path 隔离落盘位置。


def _make_backup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, source_text: str) -> str:
    # 写一份源配置 → 触发备份 → 返回备份文件全文（脱敏默认开启，显式清掉放行开关）
    source = tmp_path / "config.ini"
    source.write_text(source_text, encoding="utf-8")
    backup_dir = tmp_path / "backup"
    monkeypatch.delenv("DLR_BACKUP_KEEP_SECRETS", raising=False)
    backup_file(str(source), str(backup_dir))
    copies = [f for f in os.listdir(str(backup_dir)) if f.startswith("config.ini_")]
    assert len(copies) == 1, "应恰好生成一份新备份"
    # 备份经 main.text_encoding（utf-8-sig）落盘带 BOM，读取侧同样用 utf-8-sig 剥离
    return (backup_dir / copies[0]).read_text(encoding="utf-8-sig")


def test_backup_masks_value_shaped_secret_with_benign_key(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # 核心回归（MID-N57）：键名不含凭据关键词、节也不在白名单，但值是带 ?key= 的
    # webhook 形态——旧实现只按 is_sensitive_item 判，这类值会明文常驻 6 份备份。
    text = _make_backup(
        tmp_path,
        monkeypatch,
        "[自定义推送]\nfeishu_hook = https://open.feishu.cn/open-apis/bot/v2/hook/send?key=ABCDEF1234SECRETVALUE\n",
    )
    parser = configparser.ConfigParser(interpolation=None)
    parser.read_string(text)
    assert parser.get("自定义推送", "feishu_hook") == "***", "仅值形态命中也必须在备份里脱敏"
    assert "ABCDEF1234SECRETVALUE" not in text, "凭据明文不得出现在备份文件的任何位置"


def test_backup_keeps_ordinary_values_verbatim(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # 反向对照：拒绝面不得扩成「什么都不写」——普通文本、无凭据形态的 URL、空值
    # 都必须原样保留（备份仍可用于对照排查，这是该设计前提）。
    text = _make_backup(
        tmp_path,
        monkeypatch,
        "[基础]\n保存目录 = D:/downloads\n列表说明 = https://example.com/playlist.json\n空键 =\n",
    )
    parser = configparser.ConfigParser(interpolation=None)
    parser.read_string(text)
    assert parser.get("基础", "保存目录") == "D:/downloads"
    assert parser.get("基础", "列表说明") == "https://example.com/playlist.json"
    assert parser.get("基础", "空键") == ""


def test_backup_key_or_section_rule_still_applies(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # 既有第一道判据（节白名单 / 敏感键名）不得被新判据挤掉：
    # [Cookie] 节的普通值按节命中脱敏；「推送配置」节的 tgapi令牌 按键名命中脱敏
    # （其值非 URL 形态，_looks_like_secret_value 不命中，只能靠键名判据）。
    text = _make_backup(
        tmp_path,
        monkeypatch,
        "[Cookie]\nsome_cookie = plain-value-not-url\n[推送配置]\ntgapi令牌 = 123456:AAAA\n",
    )
    parser = configparser.ConfigParser(interpolation=None)
    parser.read_string(text)
    assert parser.get("Cookie", "some_cookie") == "***"
    assert parser.get("推送配置", "tgapi令牌") == "***"
