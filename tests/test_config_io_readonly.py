# 回归测试：read_config_value 写回失败时 best-effort（与 backup_file 一致），
# 以及 main.py 兼容旧键「虎牙是否禁用SSL证书验证(是/否)」仅读取、绝不写回。

from pathlib import Path

import pytest
from loguru import logger
from pytest import MonkeyPatch

import main  # noqa: E402,F401  (打破 config_io ↔ main 导入环)
from src import config_io  # noqa: E402


def test_read_config_value_missing_key_readonly_ok(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    # 关键回归：缺键时 read_config_value 会尝试写回 config.ini；当 config.ini 不可写
    # （只读 / 被占用）时，必须只记 warning 并返回默认值，而不是抛出 PermissionError
    # 导致整个 app 在 import main 阶段崩溃。
    cfg = tmp_path / "config.ini"
    cfg.write_text("[录制设置]\nlanguage=zh_cn\n", encoding="utf-8")
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


def test_read_config_value_delimiter_key_no_crash(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    # 关键回归（2026-08 启动崩溃）：键名含 = 等 configparser 分隔符时（历史键
    # 「最大同时录制数(0=不限制)」），读取侧在首个 = 处截断必查不到键，写回侧
    # Python 3.13+ 的 write() 抛 InvalidWriteError——必须降级为 warning + 返回默认值，
    # 不得让整个 app 在启动阶段崩溃，且坏键须回滚、不得滞留解析器污染后续写回。
    cfg = tmp_path / "config.ini"
    cfg.write_text("[录制设置]\nlanguage=zh_cn\n", encoding="utf-8")
    monkeypatch.setattr(main, "config_file", str(cfg))

    captured: list[str] = []
    handler_id = logger.add(lambda msg: captured.append(str(msg)), level="WARNING")
    try:
        parser = config_io.configparser.RawConfigParser()
        parser.read_string("[录制设置]\nlanguage=zh_cn\n")
        result = config_io.read_config_value(parser, "录制设置", "坏键(0=不限)", "0")
    finally:
        logger.remove(handler_id)

    assert result == "0"
    # 记了 warning（含异常类型）而非崩溃
    assert any("写回失败" in c and "InvalidWriteError" in c for c in captured)
    # 坏键已从内存解析器回滚：后续其他缺键的写回不再被坏键拖垮
    assert not parser.has_option("录制设置", "坏键(0=不限)")
    # 序列化在内存完成后才落盘：配置文件未被截断，原有键仍完整
    assert "language" in cfg.read_text(encoding="utf-8")


def test_read_config_value_delimiter_key_then_normal_key_still_writes(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    # 坏键写回失败后，同一解析器上另一个正常缺键的写回应能成功（坏键未污染解析器）
    cfg = tmp_path / "config.ini"
    cfg.write_text("[录制设置]\nlanguage=zh_cn\n", encoding="utf-8")
    monkeypatch.setattr(main, "config_file", str(cfg))

    parser = config_io.configparser.RawConfigParser()
    parser.read_string("[录制设置]\nlanguage=zh_cn\n")
    _ = config_io.read_config_value(parser, "录制设置", "坏键(0=不限)", "0")
    result = config_io.read_config_value(parser, "录制设置", "正常缺键", "5")

    assert result == "5"
    migrated = config_io.configparser.RawConfigParser()
    migrated.read_string(cfg.read_text(encoding="utf-8-sig"))
    assert migrated.get("录制设置", "正常缺键") == "5"
    assert not migrated.has_option("录制设置", "坏键(0=不限)")


def test_main_huya_old_key_compat_missing_only_reads(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
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


def test_main_huya_old_key_compat_present_yes_adds(tmp_path: Path) -> None:
    # 旧键存在且 =是 时，等价于把「虎牙直播」加入禁用列表（保留迁移前的语义）。
    options = {"是": True, "否": False}
    parser = config_io.configparser.RawConfigParser()
    parser.read_string("[录制设置]\n虎牙是否禁用SSL证书验证(是/否)=是\n")
    platforms: set[str] = set()

    if parser.has_option("录制设置", "虎牙是否禁用SSL证书验证(是/否)"):
        if options.get(parser.get("录制设置", "虎牙是否禁用SSL证书验证(是/否)").strip(), False):
            platforms.add("虎牙直播")

    assert platforms == {"虎牙直播"}


# ---------------- 「是否启用https录制」整合读取（旧键迁移） ----------------


def _make_parser(ini_text: str) -> config_io.configparser.RawConfigParser:
    parser = config_io.configparser.RawConfigParser()
    parser.read_string(ini_text)
    return parser


def _read_migrated(cfg: Path) -> config_io.configparser.RawConfigParser:
    # read_config_value 以 main.text_encoding（utf-8-sig，带 BOM）写回配置，
    # 读回时须用同编码剥掉 BOM，否则首行 section 头解析失败
    return _make_parser(cfg.read_text(encoding="utf-8-sig"))


def test_https_config_new_key_present(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    # 新键存在 → 直接取值，不触发任何写回
    cfg = tmp_path / "config.ini"
    cfg.write_text("[录制设置]\n是否启用https录制=是\n", encoding="utf-8")
    monkeypatch.setattr(main, "config_file", str(cfg))
    parser = _make_parser("[录制设置]\n是否启用https录制=是\n")
    assert main._read_https_recording_config(parser) is True
    assert "是否强制启用https录制" not in cfg.read_text(encoding="utf-8")


def test_https_config_legacy_key_migrates_yes(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    # 新键缺失、旧键「是否强制启用https录制=是」→ 继承 True，并把值迁移写回新键
    cfg = tmp_path / "config.ini"
    cfg.write_text("[录制设置]\n是否强制启用https录制=是\n", encoding="utf-8")
    monkeypatch.setattr(main, "config_file", str(cfg))
    parser = _make_parser("[录制设置]\n是否强制启用https录制=是\n")
    assert main._read_https_recording_config(parser) is True
    # 新键已写入继承值（Web 配置页可见可编辑），旧键保留仅作历史
    migrated = _read_migrated(cfg)
    assert migrated.get("录制设置", "是否启用https录制") == "是"
    assert migrated.has_option("录制设置", "是否强制启用https录制")


def test_https_config_legacy_key_migrates_no(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    # 旧键=否 → 继承 False，新键迁移写回「否」
    cfg = tmp_path / "config.ini"
    cfg.write_text("[录制设置]\n是否强制启用https录制=否\n", encoding="utf-8")
    monkeypatch.setattr(main, "config_file", str(cfg))
    parser = _make_parser("[录制设置]\n是否强制启用https录制=否\n")
    assert main._read_https_recording_config(parser) is False
    migrated = _read_migrated(cfg)
    assert migrated.get("录制设置", "是否启用https录制") == "否"


def test_https_config_both_missing_writes_default(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    # 新旧键皆无 → read_config_value 补写新键默认值「否」（配置自愈）
    cfg = tmp_path / "config.ini"
    cfg.write_text("[录制设置]\nlanguage=zh_cn\n", encoding="utf-8")
    monkeypatch.setattr(main, "config_file", str(cfg))
    parser = _make_parser("[录制设置]\nlanguage=zh_cn\n")
    assert main._read_https_recording_config(parser) is False
    migrated = _read_migrated(cfg)
    assert migrated.get("录制设置", "是否启用https录制") == "否"


def test_https_config_new_key_overrides_legacy(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    # 新旧键同时存在（迁移后旧键残留）→ 以新键为准，旧键值被忽略
    cfg = tmp_path / "config.ini"
    cfg.write_text("[录制设置]\n是否启用https录制=否\n是否强制启用https录制=是\n", encoding="utf-8")
    monkeypatch.setattr(main, "config_file", str(cfg))
    parser = _make_parser("[录制设置]\n是否启用https录制=否\n是否强制启用https录制=是\n")
    assert main._read_https_recording_config(parser) is False


# ---------------- 「禁用SSL证书验证的平台」自动追加 ----------------


def test_sync_ssl_disable_platforms_appends_missing(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    # 现值缺必需平台时自动追加并写回：用户手填项保留、必需项补齐
    cfg = tmp_path / "config.ini"
    cfg.write_text("[录制设置]\n禁用ssl证书验证的平台(逗号分隔)=斗鱼直播\n", encoding="utf-8")
    monkeypatch.setattr(main, "config_file", str(cfg))
    parser = _make_parser("[录制设置]\n禁用ssl证书验证的平台(逗号分隔)=斗鱼直播\n")
    result = main._sync_ssl_disable_platforms(parser)
    assert result == {"斗鱼直播", "虎牙直播", "B站直播"}
    # 配置文件已写回合并值（大小写不敏感匹配文件行，保留原键写法）
    text = cfg.read_text(encoding="utf-8")
    assert "斗鱼直播,虎牙直播,B站直播" in text
    # 内存解析器同步更新
    assert parser.get("录制设置", "禁用ssl证书验证的平台(逗号分隔)") == "斗鱼直播,虎牙直播,B站直播"


def test_sync_ssl_disable_platforms_idempotent(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    # 现值已含全部必需平台 → 不写回、值不变（幂等）
    cfg = tmp_path / "config.ini"
    cfg.write_text("[录制设置]\n禁用ssl证书验证的平台(逗号分隔)=虎牙直播,B站直播\n", encoding="utf-8")
    monkeypatch.setattr(main, "config_file", str(cfg))
    parser = _make_parser("[录制设置]\n禁用ssl证书验证的平台(逗号分隔)=虎牙直播,B站直播\n")
    result = main._sync_ssl_disable_platforms(parser)
    assert result == {"虎牙直播", "B站直播"}
    assert cfg.read_text(encoding="utf-8") == "[录制设置]\n禁用ssl证书验证的平台(逗号分隔)=虎牙直播,B站直播\n"


def test_sync_ssl_disable_platforms_missing_key_writes_default(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    # 键整体缺失 → read_config_value 补写空默认值，随后追加必需平台
    cfg = tmp_path / "config.ini"
    cfg.write_text("[录制设置]\nlanguage=zh_cn\n", encoding="utf-8")
    monkeypatch.setattr(main, "config_file", str(cfg))
    parser = _make_parser("[录制设置]\nlanguage=zh_cn\n")
    result = main._sync_ssl_disable_platforms(parser)
    assert result == set(main.SSL_DISABLE_REQUIRED_PLATFORMS)


# ---------------- 「language」语言键迁移读取 ----------------


def test_language_new_key_present(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    # language 键存在 → 直接取值，不触发任何写回
    cfg = tmp_path / "config.ini"
    cfg.write_text("[录制设置]\nlanguage=en_US\n", encoding="utf-8")
    monkeypatch.setattr(main, "config_file", str(cfg))
    parser = _make_parser("[录制设置]\nlanguage=en_US\n")
    assert main._read_language_config(parser) == "en_US"
    assert cfg.read_text(encoding="utf-8") == "[录制设置]\nlanguage=en_US\n"


def test_language_both_missing_writes_empty_default(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    # language 键缺失 → read_config_value 补写新键空默认值（空 = 跟随系统语言，解析由 i18n 兜底）
    cfg = tmp_path / "config.ini"
    cfg.write_text("[录制设置]\n是否启用https录制=否\n", encoding="utf-8")
    monkeypatch.setattr(main, "config_file", str(cfg))
    parser = _make_parser("[录制设置]\n是否启用https录制=否\n")
    assert main._read_language_config(parser) == ""
    migrated = _read_migrated(cfg)
    assert migrated.get("录制设置", "language") == ""
