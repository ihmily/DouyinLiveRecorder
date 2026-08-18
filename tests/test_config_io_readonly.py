# 回归测试：read_config_value 写回失败时 best-effort（与 backup_file 一致），
# 以及 main.py 兼容旧键「虎牙是否禁用SSL证书验证(是/否)」仅读取、绝不写回。

import pytest
from loguru import logger

import main  # noqa: E402,F401  (打破 config_io ↔ main 导入环)
from src import config_io  # noqa: E402


def test_read_config_value_missing_key_readonly_ok(tmp_path, monkeypatch):
    # 关键回归：缺键时 read_config_value 会尝试写回 config.ini；当 config.ini 不可写
    # （只读 / 被占用）时，必须只记 warning 并返回默认值，而不是抛出 PermissionError
    # 导致整个 app 在 import main 阶段崩溃。
    cfg = tmp_path / "config.ini"
    cfg.write_text("[录制设置]\nlanguage(zh_cn/en)=zh_cn\n", encoding="utf-8")
    # 设为只读，模拟「配置文件被占用 / 不可写」场景
    cfg.chmod(0o444)

    captured: list[str] = []
    handler_id = logger.add(lambda msg: captured.append(str(msg)), level="WARNING")
    try:
        parser = config_io.configparser.RawConfigParser()
        parser.read(str(cfg), encoding="utf-8")
        monkeypatch.setattr(main, "config_file", str(cfg))
        # 缺键查询：应返回默认值且不抛异常
        result = config_io.read_config_value(parser, "录制设置", "_缺失的键_xyz", "默认")
    finally:
        logger.remove(handler_id)
        cfg.chmod(0o644)

    assert result == "默认"
    # 原始配置文件内容未被写入该缺省键（写回失败被忽略）
    assert "_缺失的键_xyz" not in cfg.read_text(encoding="utf-8")
    # 记了 warning 而非崩溃
    assert any("写回失败" in c for c in captured)


def test_main_huya_old_key_compat_missing_only_reads(tmp_path, monkeypatch):
    # main.py 兼容旧键在缺键时仅读取、绝不写回——缺失时不进入写回路径。
    options = {"是": True, "否": False}
    parser = config_io.configparser.RawConfigParser()
    parser.read_string("[录制设置]\n禁用SSL证书验证的平台(逗号分隔)=抖音直播\n")
    platforms = {p.strip() for p in parser.get("录制设置", "禁用SSL证书验证的平台(逗号分隔)").split(",") if p.strip()}

    # 旧键缺失 → has_option 为 False → 不触发任何写回
    assert not parser.has_option("录制设置", "虎牙是否禁用SSL证书验证(是/否)")

    # 复刻 main.py guard：仅读取，不应抛异常
    if parser.has_option("录制设置", "虎牙是否禁用SSL证书验证(是/否)"):
        if options.get(parser.get("录制设置", "虎牙是否禁用SSL证书验证(是/否)").strip(), False):
            platforms.add("虎牙直播")

    assert platforms == {"抖音直播"}


def test_main_huya_old_key_compat_present_yes_adds(tmp_path):
    # 旧键存在且 =是 时，等价于把「虎牙直播」加入禁用列表（保留迁移前的语义）。
    options = {"是": True, "否": False}
    parser = config_io.configparser.RawConfigParser()
    parser.read_string("[录制设置]\n虎牙是否禁用SSL证书验证(是/否)=是\n")
    platforms: set[str] = set()

    if parser.has_option("录制设置", "虎牙是否禁用SSL证书验证(是/否)"):
        if options.get(parser.get("录制设置", "虎牙是否禁用SSL证书验证(是/否)").strip(), False):
            platforms.add("虎牙直播")

    assert platforms == {"虎牙直播"}
