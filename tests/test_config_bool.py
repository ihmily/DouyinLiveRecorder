# 布尔配置解析统一口径的回归测试（src/config_bool.py + src/config_io.read_config_bool）。
#
# 背景（2026-09-17）：旧实现把「取值」与「解析」混在 main.py 的 `options = {"是": True, "否": False}`
# 字典查表里，非「是/否」写法会**静默**回落到 options.get 的兜底实参；logger.py / web_config.py /
# web/app.js / GUI 窗口层又各有一套口径。把 config.ini 批量改写成 true/false 后 8 项配置的生效值
# 全部漂移（最严重：「是否跳过代理检测 = true」被判 False → global_proxy=False → 9 个海外平台
# 解析分支走 else，100% 无法录制）。
#
# 本文件锁定三件事：① 两种编码等价；② 缺键补写仍是规范写法「是」/「否」；
# ③ main.py 不得再出现字典查表写法（源码级防回归，避免口径重新分叉）。

import ast
from pathlib import Path

import pytest
from pytest import MonkeyPatch

import main  # noqa: E402,F401  (打破 config_io ↔ main 导入环)
from src import config_io  # noqa: E402
from src.config_bool import FALSE_TOKENS, TRUE_TOKENS, format_config_bool, parse_config_bool  # noqa: E402

_MAIN_PY = Path(__file__).resolve().parents[1] / "main.py"
_KEY = "是否录制弹幕(是/否)"


def _make_parser(ini_text: str) -> config_io.configparser.RawConfigParser:
    parser = config_io.configparser.RawConfigParser()
    parser.read_string(ini_text)
    return parser


# ---------------- 纯解析函数 ----------------


@pytest.mark.parametrize("raw", ["是", "true", "TRUE", "True", " t ", "yes", "YES", "y", "on", "ON", "1"])
def test_parse_config_bool_true_tokens(raw: str) -> None:
    # 「是」与 true/1/yes/on 等写法必须等价——两种写法都真实出现在配置文件里
    assert parse_config_bool(raw, False) is True


@pytest.mark.parametrize("raw", ["否", "false", "FALSE", "False", " f ", "no", "NO", "n", "off", "OFF", "0"])
def test_parse_config_bool_false_tokens(raw: str) -> None:
    assert parse_config_bool(raw, True) is False


@pytest.mark.parametrize("raw", ["", "   ", None, "maybe", "真", "2", "-1", "是/否"])
def test_parse_config_bool_unknown_falls_back_to_default(raw: str | None) -> None:
    # 空值/未识别值返回调用方给的文档默认值，而不是沿用上一次取值
    assert parse_config_bool(raw, True) is True
    assert parse_config_bool(raw, False) is False


def test_parse_config_bool_passes_python_bool_through() -> None:
    # 从 API/测试直接传入 bool 时应短路返回，不受 default 影响
    assert parse_config_bool(True, False) is True
    assert parse_config_bool(False, True) is False


def test_token_sets_are_disjoint_and_cover_both_encodings() -> None:
    # 两个 token 集不得有交集，且必须同时覆盖「是/否」与 true/false 四种主写法
    assert TRUE_TOKENS & FALSE_TOKENS == frozenset()
    assert {"是", "true"} <= TRUE_TOKENS
    assert {"否", "false"} <= FALSE_TOKENS


def test_format_config_bool_canonical() -> None:
    # 缺键补写沿用本仓规范写法「是」/「否」（存量值不迁移，两种写法已等价）
    assert format_config_bool(True) == "是"
    assert format_config_bool(False) == "否"


# ---------------- read_config_bool（读取 + 缺键补写） ----------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("是", True),
        ("否", False),
        ("true", True),
        ("false", False),
        ("TRUE", True),
        ("False", False),
        ("1", True),
        ("0", False),
        ("yes", True),
        ("no", False),
        ("on", True),
        ("off", False),
    ],
)
def test_read_config_bool_accepts_both_encodings(
    tmp_path: Path, monkeypatch: MonkeyPatch, raw: str, expected: bool
) -> None:
    # 同一份配置文件里两种编码必须解析出相同结果（这是本次事故的核心保证）
    cfg = tmp_path / "config.ini"
    cfg.write_text(f"[录制设置]\n{_KEY}={raw}\n", encoding="utf-8")
    monkeypatch.setattr(main, "config_file", str(cfg))
    parser = _make_parser(f"[录制设置]\n{_KEY}={raw}\n")
    assert config_io.read_config_bool(parser, "录制设置", _KEY, False) is expected


def test_read_config_bool_missing_key_writes_canonical_default(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    # 缺键 → 按 default 补写规范写法并返回该值（与 read_config_value 的自愈语义一致）
    cfg = tmp_path / "config.ini"
    cfg.write_text("[录制设置]\nlanguage=zh_cn\n", encoding="utf-8")
    monkeypatch.setattr(main, "config_file", str(cfg))
    parser = _make_parser("[录制设置]\nlanguage=zh_cn\n")

    assert config_io.read_config_bool(parser, "录制设置", _KEY, True) is True
    migrated = config_io.configparser.RawConfigParser()
    migrated.read_string(cfg.read_text(encoding="utf-8-sig"))
    assert migrated.get("录制设置", _KEY) == "是"

    assert config_io.read_config_bool(parser, "录制设置", "是否弹幕监控(是/否)", False) is False
    migrated2 = config_io.configparser.RawConfigParser()
    migrated2.read_string(cfg.read_text(encoding="utf-8-sig"))
    assert migrated2.get("录制设置", "是否弹幕监控(是/否)") == "否"


def test_read_config_bool_unrecognized_value_returns_default_and_keeps_original(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    # 未识别值返回 default，但**不得**覆写用户原文（避免把用户手改的内容静默改掉）
    cfg = tmp_path / "config.ini"
    cfg.write_text(f"[录制设置]\n{_KEY}=maybe\n", encoding="utf-8")
    monkeypatch.setattr(main, "config_file", str(cfg))
    parser = _make_parser(f"[录制设置]\n{_KEY}=maybe\n")

    assert config_io.read_config_bool(parser, "录制设置", _KEY, False) is False
    on_disk = config_io.configparser.RawConfigParser()
    on_disk.read_string(cfg.read_text(encoding="utf-8-sig"))
    assert on_disk.get("录制设置", _KEY) == "maybe"


# ---------------- 「是否启用https录制」整合读取：两种编码 ----------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("是", True), ("true", True), ("1", True), ("否", False), ("false", False), ("0", False)],
)
def test_https_config_accepts_true_false_encoding(
    tmp_path: Path, monkeypatch: MonkeyPatch, raw: str, expected: bool
) -> None:
    # 本次事故的直接命中项：true 曾被判为「否」→ 流地址被降级为 http
    cfg = tmp_path / "config.ini"
    cfg.write_text(f"[录制设置]\n是否启用https录制={raw}\n", encoding="utf-8")
    monkeypatch.setattr(main, "config_file", str(cfg))
    parser = _make_parser(f"[录制设置]\n是否启用https录制={raw}\n")
    assert main._read_https_recording_config(parser) is expected


def test_https_config_legacy_key_true_encoding_migrates(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    # 旧键用 true 写法时同样应继承为 True，并迁移写回规范写法「是」
    cfg = tmp_path / "config.ini"
    cfg.write_text("[录制设置]\n是否强制启用https录制=true\n", encoding="utf-8")
    monkeypatch.setattr(main, "config_file", str(cfg))
    parser = _make_parser("[录制设置]\n是否强制启用https录制=true\n")
    assert main._read_https_recording_config(parser) is True
    migrated = config_io.configparser.RawConfigParser()
    migrated.read_string(cfg.read_text(encoding="utf-8-sig"))
    assert migrated.get("录制设置", "是否启用https录制") == "是"


# ---------------- 源码级防回归 ----------------


def test_main_has_no_legacy_options_dict_lookup() -> None:
    # 字典查表 + 静默兜底是本次事故的根因：main.py 不得再出现该写法。
    # 用 AST 而非原文子串判定——源码注释里会引用被删除的实现，子串匹配会把注释也算作命中。
    tree = ast.parse(_MAIN_PY.read_text(encoding="utf-8"), filename="main.py")

    # ① 不得存在 options.<attr>() 形式的调用
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if isinstance(node.func.value, ast.Name):
                assert node.func.value.id != "options", "main.py 仍存在 options.<attr>() 调用"

    # ② 不得再绑定名为 options 的模块级变量
    for stmt in tree.body:
        targets: list[ast.expr] = []
        if isinstance(stmt, ast.Assign):
            targets = list(stmt.targets)
        elif isinstance(stmt, ast.AnnAssign):
            targets = [stmt.target]
        for target in targets:
            assert not (isinstance(target, ast.Name) and target.id == "options"), "main.py 又新增了 options 变量"


@pytest.mark.parametrize(
    "key",
    [
        "是否跳过代理检测(是/否)",
        "保存文件夹是否以作者区分",
        "分段录制是否开启",
        "是否录制弹幕(是/否)",
        "是否启用HLS采集(是/否)",
        "生成时间字幕文件",
        "追加格式后删除原文件",
    ],
)
def test_main_drift_prone_keys_use_read_config_bool(key: str) -> None:
    # 2026-09-17 实测漂移的键必须走统一解析入口（漏改一个就会重新分叉口径）
    source = _MAIN_PY.read_text(encoding="utf-8")
    assert f'read_config_bool(config, "录制设置", "{key}"' in source
