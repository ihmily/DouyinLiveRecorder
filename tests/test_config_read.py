# src/config_read.py 回归锁：重复键容错读取与「点名一次」告警（2026-10-17 现场：config.ini
# 的 [录制设置] 内落出两行同名键）。
#
# 锁什么：
#   · 反向见证——strict=True 的默认解析器在同一份文件上确实整份读不出，证明这里测的是真实
#     故障形态而非造不出来的场景；
#   · tolerant_config_parser 读出全部其余键、重复键取最后一次；
#   · find_duplicate_options 点名到 节/键/行号，且「注释行」「跨节同名键」「多行值续行」
#     三类形态不误报（L-17），同时「真重复混在续行之间」仍必须报出；
#     M-54 把「带 = / : 的缩进续行」也归入不误报的一类——这类形态在 cookie/长值
#     折行里最常见，误报会吃掉「同一形态只报一次」的额度、把真重复淹没；
#   · warn_duplicate_options 同一文件形态只落一条 warning（状态链每 10s 读一次配置，不去重
#     会刷满日志），文件一改写就重新点名，缓存封顶后仍能点名；
#   · preserve_case 复刻被替换掉的 GUI 侧 optionxform 闭包；main.py 的模块级 config 必须是
#     容错解析器（那条裸读是「录制核心 import 即崩」的第一现场）。
#
# 全部写入 tmp_path，绝不碰仓库里已跟踪的脱敏基线模板 config/config.ini。

import os
import time
from pathlib import Path

import pytest
from loguru import logger
from pytest import MonkeyPatch

import main  # noqa: E402  (config_read 不依赖 main，但本文件要核对 main 的模块级解析器接线)
from src import config_read
from src.config_read import find_duplicate_options, tolerant_config_parser, warn_duplicate_options

# 一份「同节内重复 + 注释里出现同名键 + 跨节同名键」三态并存的样本：
# 第 4 行与第 7 行是 [录制设置] 内的真重复；第 6 行是注释（不得误报）；
# [推送配置] 里的同名键属于另一节（不得误报）。
_DUP_INI = """[录制设置]
language =
循环时间(秒) = 60
是否启动时清理陈旧字节码缓存(是/否) = 否
视频保存格式ts|mkv|flv|mp4|mp3音频|m4a音频 = flv
# 手工抄写时最容易踩的形态：把键名连同说明再写一遍 —— 注释不得参与重复判定
是否启动时清理陈旧字节码缓存(是/否) = 是

[推送配置]
是否启动时清理陈旧字节码缓存(是/否) = 是
"""

_CLEAN_INI = "[录制设置]\n循环时间(秒) = 60\n\n[推送配置]\nx = 1\n"


@pytest.fixture
def dup_ini(tmp_path: Path) -> Path:
    path = tmp_path / "config.ini"
    path.write_text(_DUP_INI, encoding="utf-8")
    return path


@pytest.fixture(autouse=True)
def _isolate_warn_cache(monkeypatch: MonkeyPatch) -> None:
    # 点名记忆集是模块级全局：不隔离会让用例互相吃掉告警（后来的用例看同一形态，
    # 会把前一条的告警判成「已报过」）。
    monkeypatch.setattr(config_read, "_DUP_WARNED", set())


def _capture_warnings() -> tuple[list[str], int]:
    # 返回 (消息列表, handler id)；调用方负责在 finally 里 logger.remove。
    captured: list[str] = []
    handler_id = logger.add(lambda msg: captured.append(str(msg)), level="WARNING")
    return captured, handler_id


def test_default_strict_parser_cannot_read_any_key(dup_ini: Path) -> None:
    # 反向见证：默认 strict=True 解析器在重复键上抛 DuplicateOptionError，且一个键都读不出——
    # 这正是录制核心 import 即崩的成因。删掉容错读取即本条转红。
    import configparser

    strict = configparser.ConfigParser(interpolation=None)
    with pytest.raises(configparser.DuplicateOptionError) as excinfo:
        strict.read(str(dup_ini), encoding="utf-8-sig")
    assert excinfo.value.section == "录制设置"
    assert excinfo.value.option == "是否启动时清理陈旧字节码缓存(是/否)"
    assert excinfo.value.lineno == 7


def test_tolerant_parser_reads_every_key_and_keeps_last_value(dup_ini: Path) -> None:
    parser = tolerant_config_parser()
    parser.read(str(dup_ini), encoding="utf-8-sig")
    assert parser.get("录制设置", "循环时间(秒)") == "60"
    assert parser.get("录制设置", "视频保存格式ts|mkv|flv|mp4|mp3音频|m4a音频") == "flv"
    # 重复键取最后一次（与 configparser 内存态的 dict 覆盖语义一致）
    assert parser.get("录制设置", "是否启动时清理陈旧字节码缓存(是/否)") == "是"
    # 跨节同名键不受影响：另一节里的它仍是它自己
    assert parser.get("推送配置", "是否启动时清理陈旧字节码缓存(是/否)") == "是"


def test_find_duplicate_options_names_section_option_and_lines(dup_ini: Path) -> None:
    found = find_duplicate_options(dup_ini.read_text(encoding="utf-8"))
    # 只有一处真重复：注释行与 [推送配置] 里的那两行都不算
    assert found == [("录制设置", "是否启动时清理陈旧字节码缓存(是/否)", (4, 7))]


def test_find_duplicate_options_accepts_colon_delimiter_and_ignores_case() -> None:
    # configparser 的默认 delimiters 是 ('=', ':')、默认 optionxform 转小写——扫描器判据必须
    # 与「解析器实际看到的键集合」一致，否则会漏报真重复、误报假重复。
    assert find_duplicate_options("[s]\nLanguage = zh\nlanguage: en\n") == [("s", "Language", (2, 3))]


def test_find_duplicate_options_ignores_multiline_value_continuation_lines() -> None:
    # L-17：缩进的续行会被 configparser 并入上一条键的值，它根本不是键。
    # 旧实现先 strip 缩进再把整行当独立键统计，于是每份带多行值的配置都被点名成「重复配置项」
    # （两条续行文本相同即命中），虚假告警把真重复淹没。
    text = "[s]\nkey = 第一段\n    第二段 相同文本\nother = 1\n    第二段 相同文本\n"
    assert find_duplicate_options(text) == []
    # 反向见证：这几行在解析器里确实是**值**而不是键（值里带着拼接后的续行）
    parser = tolerant_config_parser()
    parser.read_string(text)
    assert parser.get("s", "key") == "第一段\n第二段 相同文本"
    assert parser.get("s", "other") == "1\n第二段 相同文本"
    assert set(parser["s"]) == {"key", "other"}


def test_find_duplicate_options_ignores_indented_continuations_that_contain_delimiters() -> None:
    # M-54 回归锁：上一条判据只放过了「整行不含 = / :」的续行，所以**带分隔符的
    # 缩进续行**仍被当成独立键。config.ini 里最常见的正是这一形态——cookie / 多行脚本值折行后
    # 逐行形如 `   token=abc`，两行折行文本同名即被误报成「存在重复配置项」。
    # 误报的代价不是噪声而已：warn_duplicate_options 的「同一形态只点名一次」额度只有
    # _DUP_WARN_CACHE_MAX(32) 项，被假告警吃满后真重复反而永不点名（本函数存在的意义被抵消）。
    text = "[s]\ncookie = v1\n   token=abc\n   token=def\n"
    assert find_duplicate_options(text) == []
    # 反向见证：缩进行在解析器里是**值的一部分**，不是键——因此「跳过缩进行」不可能放过真重复键
    parser = tolerant_config_parser()
    parser.read_string(text)
    assert parser.get("s", "cookie") == "v1\ntoken=abc\ntoken=def"
    assert set(parser["s"]) == {"cookie"}
    # 冒号形态同判据（configparser 的默认 delimiters 是 ('=', ':')）
    assert find_duplicate_options("[s]\nreferer = http://a\n   Host: x.example\n   Host: y.example\n") == []


def test_find_duplicate_options_reports_real_duplicates_on_unindented_lines() -> None:
    # 同一条跳过判据不得把真重复也放过：顶格写的重复键必须仍被报出，且行号按出现顺序给全
    # （变异验证短 id M54：把缩进守卫放宽成「strip 后再判」会让本条转红）。
    text = "[s]\nk = v1\n    续行 k = 伪键\nk = v3\n"
    assert find_duplicate_options(text) == [("s", "k", (2, 4))]


def test_find_duplicate_options_still_reports_real_duplicates_beside_continuations() -> None:
    # 同一条跳过判据不得把真重复也放过：混在多行值之间的两行 `k = v` 必须仍被报出，
    # 且行号按出现顺序给全（变异验证短 id L17：把 `continue` 去掉后本条转红）。
    text = "[s]\nk = v1\n    续行文本\nother = 2\nK = v3\n"
    assert find_duplicate_options(text) == [("s", "k", (2, 5))]
    # 无分隔符的裸行同样不算键（allow_no_value 从未开启，这种行 configparser 自己判解析错误）
    assert find_duplicate_options("[s]\nbareline\nanother-bareline\n") == []


def test_find_duplicate_options_is_empty_for_clean_file() -> None:
    assert find_duplicate_options(_CLEAN_INI) == []


def test_warn_duplicate_options_logs_once_per_file_version(dup_ini: Path) -> None:
    captured, handler_id = _capture_warnings()
    try:
        assert warn_duplicate_options(dup_ini) == 1
        assert warn_duplicate_options(dup_ini) == 1
        assert len(captured) == 1, "同一文件形态只允许落一条（状态链每 10s 读一次）"
        assert "录制设置" in captured[0]
        assert "是否启动时清理陈旧字节码缓存(是/否)" in captured[0]
        assert "4, 7" in captured[0], captured[0]

        # 文件被改写（mtime 变）→ 必须重新点名一次，否则用户改完配置看不到最新形态
        future = time.time() + 5
        os.utime(str(dup_ini), (future, future))
        assert warn_duplicate_options(dup_ini) == 1
        assert len(captured) == 2
    finally:
        logger.remove(handler_id)


def test_warn_duplicate_options_stays_silent_and_zero_when_clean(tmp_path: Path) -> None:
    clean = tmp_path / "config.ini"
    clean.write_text(_CLEAN_INI, encoding="utf-8")
    captured, handler_id = _capture_warnings()
    try:
        assert warn_duplicate_options(clean) == 0
        # 读不出内容（文件不存在）也返回 0 且不抛：解析结论由调用方的读取路径给出
        assert warn_duplicate_options(tmp_path / "missing.ini") == 0
    finally:
        logger.remove(handler_id)
    assert captured == []


def test_warn_duplicate_options_capped_cache_still_reports(dup_ini: Path, monkeypatch: MonkeyPatch) -> None:
    # 缓存被填满时不得「因为放不下而不再点名」——清空重记才是本函数的语义
    monkeypatch.setattr(
        config_read, "_DUP_WARNED", {(f"stale-{i}.ini", 1.0) for i in range(config_read._DUP_WARN_CACHE_MAX)}
    )
    captured, handler_id = _capture_warnings()
    try:
        assert warn_duplicate_options(dup_ini) == 1
    finally:
        logger.remove(handler_id)
    assert len(captured) == 1
    assert len(config_read._DUP_WARNED) == 1


def test_tolerant_parser_preserve_case_keeps_key_case(tmp_path: Path) -> None:
    # GUI 侧此前用本地闭包把 optionxform 置为恒等；工厂必须复刻同一形态，
    # 否则 [GUI] 里的大小写混排键会在换实现后悄悄读不到。
    path = tmp_path / "config.ini"
    path.write_text("[GUI]\nGui_Font = ABC\nlanguage = en_US\n", encoding="utf-8")
    preserved = tolerant_config_parser(preserve_case=True)
    preserved.read(str(path), encoding="utf-8-sig")
    assert preserved.has_option("GUI", "Gui_Font")
    assert not preserved.has_option("GUI", "gui_font")

    lowered = tolerant_config_parser()
    lowered.read(str(path), encoding="utf-8-sig")
    assert lowered.has_option("GUI", "gui_font")


def test_tolerant_parser_disables_interpolation(tmp_path: Path) -> None:
    # 配置值里出现 % 是常见形态（百分比、脚本模板）；插值开启时 read 直接抛
    # InterpolationSyntaxError，与本次要消灭的「整份读不出」同族。
    path = tmp_path / "config.ini"
    path.write_text("[录制设置]\n自定义脚本执行命令 = echo 100%%done\n", encoding="utf-8")
    parser = tolerant_config_parser()
    parser.read(str(path), encoding="utf-8-sig")
    assert parser.get("录制设置", "自定义脚本执行命令") == "echo 100%%done"


def test_main_module_level_parser_is_duplicate_tolerant() -> None:
    # 接线锁：main.py 的模块级 config 必须是容错解析器。configparser 只把 strict 存成私有字段
    # _strict（默认解析器为 True、strict=False 构造的为 False），没有公开读回入口；该字段若随
    # CPython 改名，本条以 AttributeError 当场失败而不会静默放行（三参 getattr 绕过 mypy）。
    assert getattr(main.config, "_strict", None) is False, "main.py 的模块级 config 必须是容错解析器"
