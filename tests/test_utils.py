# Tests for src/utils.py - utility function tests for coverage improvement.

import ast
import builtins
import configparser
import inspect
import os
import signal
import stat
import subprocess
import sys
import tempfile
import threading
import time
import zipfile
from collections.abc import Generator
from pathlib import Path
from types import SimpleNamespace
from typing import IO, Any, cast

import pytest
from loguru import logger

import src.utils as utils_module
from src.utils import (
    ProgramError,
    atomic_write_text,
    check_disk_capacity,
    check_md5,
    dict_to_cookie_str,
    get_file_paths,
    get_query_params,
    handle_proxy_addr,
    jsonp_to_json,
    mask_credentials,
    read_ini_value,
    remove_duplicate_lines,
    remove_emojis,
    replace_url,
    run_node_script_async,
    trace_error_decorator,
    trace_error_decorator_or_none,
    unzip_file,
    update_config,
)


@pytest.fixture()
def log_capture() -> Generator[list[str]]:
    # MI-19 修复后，read_ini_value / update_config 的失败与缺键提示改走 logger 而非 print——
    # print 只进 stdout，冻结打包（无控制台）时会被直接丢弃，用户提交日志文件求助时看不到
    # 「凭据键缺失 / 写配置失败」这类关键原因。相应地断言须从 capsys 改为捕获 loguru sink。
    # 与 tests/test_notify.py、tests/test_machine_validation_fixes.py 采用同一模式。
    captured: list[str] = []
    sink_id = logger.add(lambda msg: captured.append(str(msg)), format="{message}", level="DEBUG")
    try:
        yield captured
    finally:
        logger.remove(sink_id)


# 字典转 Cookie 头字符串：把爬虫拿到的 cookie 字典拼成请求头。
# 守卫空/单/多键值三种形态的拼接正确性。
class TestDictToCookieStr:
    # Test dict_to_cookie_str.

    def test_empty_dict(self) -> None:
        assert dict_to_cookie_str({}) == ""

    # 单键值须拼成 "k=v" 单一片段
    def test_single_cookie(self) -> None:
        assert dict_to_cookie_str({"key": "value"}) == "key=value"

    # 多键值须全部出现并以 "; " 连接（顺序无关但分隔符固定）
    def test_multiple_cookies(self) -> None:
        result = dict_to_cookie_str({"a": "1", "b": "2"})
        assert "a=1" in result
        assert "b=2" in result
        assert "; " in result


class TestCheckMd5:
    # Test check_md5.

    def test_returns_md5(self, tmp_path: Path) -> None:
        test_file = tmp_path / "test.txt"
        test_file.write_text("hello world", encoding="utf-8")
        result = check_md5(test_file)
        assert len(result) == 32
        assert result.isalnum()

    def test_same_content_same_md5(self, tmp_path: Path) -> None:
        f1 = tmp_path / "a.txt"
        f2 = tmp_path / "b.txt"
        f1.write_text("same content", encoding="utf-8")
        f2.write_text("same content", encoding="utf-8")
        assert check_md5(f1) == check_md5(f2)


class TestCheckDiskCapacity:
    # Test check_disk_capacity.

    def test_returns_positive_float(self, tmp_path: Path) -> None:
        # 磁盘容量查询返回正浮点（字节数），负值/异常代表挂载失败（录制前需据此告警）
        result = check_disk_capacity(str(tmp_path))
        assert isinstance(result, float)
        assert result > 0

    # show=True 时须打印 Total/Free 信息，供用户在 UI 确认剩余空间
    def test_with_show(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        result = check_disk_capacity(str(tmp_path), show=True)
        captured = capsys.readouterr()
        assert "Total" in captured.out
        assert "Free" in captured.out
        assert isinstance(result, float)


class TestRemoveDuplicateLines:
    # Test remove_duplicate_lines.

    # 连续/间隔重复行须去重且仅保留首次出现顺序，编码用 utf-8-sig 兼容 BOM
    def test_removes_duplicates(self, tmp_path: Path) -> None:
        test_file = tmp_path / "test.txt"
        test_file.write_text("line1\nline2\nline1\nline3\nline2\n", encoding="utf-8-sig")
        remove_duplicate_lines(test_file)
        content = test_file.read_text(encoding="utf-8-sig")
        lines = [l for l in content.strip().split("\n") if l]
        assert len(lines) == 3
        assert "line1" in lines
        assert "line2" in lines
        assert "line3" in lines


class TestReadConfigValue:
    # Test read_ini_value (F-16: 原 read_config_value，与 config_io 同名函数区分).

    # 存在的 section/key 须返回原始字符串值
    def test_read_existing_key(self, tmp_path: Path) -> None:
        config_file = tmp_path / "config.ini"
        config_file.write_text("[section1]\nkey1 = value1\n", encoding="utf-8-sig")
        result = read_ini_value(config_file, "section1", "key1")
        assert result == "value1"

    def test_read_missing_key(self, tmp_path: Path, log_capture: list[str]) -> None:
        config_file = tmp_path / "config.ini"
        config_file.write_text("[section1]\nkey1 = value1\n", encoding="utf-8-sig")
        result = read_ini_value(config_file, "section1", "missing_key")
        assert result is None
        assert any("does not exist" in m for m in log_capture)

    # 缺失 section 须返回 None 并提示，与缺失 key 同处理
    def test_read_missing_section(self, tmp_path: Path, log_capture: list[str]) -> None:
        config_file = tmp_path / "config.ini"
        config_file.write_text("[section1]\nkey1 = value1\n", encoding="utf-8-sig")
        result = read_ini_value(config_file, "missing_section", "key1")
        assert result is None
        assert any("does not exist" in m for m in log_capture)

    # read_ini_value 关闭 BasicInterpolation：含 % 的值（cookie/URL 编码）不应抛异常（批次5修复）.
    def test_percent_value_readable(self, tmp_path: Path) -> None:
        # % 在 ini 默认插值中是特殊字符（BasicInterpolation 会解析 %(x)s），关闭后含 % 的 cookie/URL 才能原样读出
        cfg = tmp_path / "c.ini"
        cfg.write_text("[s]\nk = 100%x\n", encoding="utf-8")
        assert read_ini_value(cfg, "s", "k") == "100%x"

    def test_missing_key_returns_none(self, tmp_path: Path, log_capture: list[str]) -> None:
        cfg = tmp_path / "c.ini"
        cfg.write_text("[s]\nk = v\n", encoding="utf-8")
        assert read_ini_value(cfg, "s", "nope") is None
        _ = log_capture  # 仅为建立 sink，吞掉提示输出


class TestUpdateConfig:
    # Test update_config.

    def test_update_existing_key(self, tmp_path: Path, log_capture: list[str]) -> None:
        config_file = tmp_path / "config.ini"
        config_file.write_text("[section1]\nkey1 = old_value\n", encoding="utf-8-sig")
        update_config(config_file, "section1", "key1", "new_value")
        result = read_ini_value(config_file, "section1", "key1")
        assert result == "new_value"
        assert any("updated" in m for m in log_capture)

    def test_update_missing_section(self, tmp_path: Path, log_capture: list[str]) -> None:
        config_file = tmp_path / "config.ini"
        config_file.write_text("[section1]\nkey1 = value1\n", encoding="utf-8-sig")
        update_config(config_file, "missing_section", "key1", "new_value")
        assert any("does not exist" in m for m in log_capture)


class TestDuplicateKeyWriteback:
    # M-08（2026-10-19）：src/utils.py 的两处解析器改走 config_read.tolerant_config_parser。
    # 旧形态 configparser.ConfigParser(interpolation=None) 的 strict 默认为 True，遇到「同一节内
    # 两行同名键」（2026-10-17 在本仓 config/config.ini 的 [录制设置] 实测到过）时在 read() 就抛
    # DuplicateOptionError → read_ini_value 吞成 warning 返 None、update_config 更早退，
    # [Cookie]/[Authorization] 的刷新在这种形态下**永远写不回**。
    # 三条自证缺一不可：① 重复键输入下仍能写回；② 写回产物必须能被 **strict** 解析器整份读出
    # （否则就是在制造「缺键补写幂等」事故的第二半——把坏形态留给外部编辑器与其它程序）；
    # ③ 键匹配的大小写口径不变（两处历来用默认 optionxform＝转小写后比较，不得顺手改成保留大小写）。

    _DUP_TEXT = "[Cookie]\nbili_cookie = fresh-from-api\nbili_cookie = stale-value\n[录制设置]\nlanguage = zh_CN\n"

    def test_strict_parser_is_the_reverse_witness(self, tmp_path: Path) -> None:
        # 反向见证：本类测的故障形态真造得出来——strict 解析器在这份文件上**一个键都读不出**。
        # 若哪天 configparser 默认改成不严格，这条会红，提醒下面两条锁的前提已不存在。
        cfg = tmp_path / "config.ini"
        cfg.write_text(self._DUP_TEXT, encoding="utf-8-sig")
        strict = configparser.ConfigParser(interpolation=None)
        with pytest.raises(configparser.DuplicateOptionError):
            strict.read(str(cfg), encoding="utf-8-sig")

    def test_update_config_writes_back_under_duplicate_key(self, tmp_path: Path) -> None:
        cfg = tmp_path / "config.ini"
        cfg.write_text(self._DUP_TEXT, encoding="utf-8-sig")
        update_config(cfg, "Cookie", "bili_cookie", "refreshed-value")
        assert read_ini_value(cfg, "Cookie", "bili_cookie") == "refreshed-value"

    def test_writeback_product_is_strict_readable(self, tmp_path: Path) -> None:
        # 判据②：容错读进来、按内存态写出去后，同节重复键被折叠成一行，产物必须仍能被
        # strict 解析器**整份**读出（逐节取值而不是「读一次不抛错」，防止只测一半）。
        cfg = tmp_path / "config.ini"
        cfg.write_text(self._DUP_TEXT, encoding="utf-8-sig")
        update_config(cfg, "Cookie", "bili_cookie", "refreshed-value")
        strict = configparser.ConfigParser(interpolation=None)
        strict.read(str(cfg), encoding="utf-8-sig")
        assert strict.get("Cookie", "bili_cookie") == "refreshed-value"
        assert strict.get("录制设置", "language") == "zh_CN"
        written = cfg.read_text(encoding="utf-8-sig")
        assert written.count("bili_cookie") == 1, written

    def test_key_matching_stays_case_insensitive(self, tmp_path: Path) -> None:
        # 判据③：大小写口径与改前一致——入参大写、文件小写仍要能命中（configparser 的
        # optionxform 转小写行为），preserve_case 若被误开，这里会退化成「找不到键」。
        cfg = tmp_path / "config.ini"
        cfg.write_text("[section1]\nkey1 = v1\n", encoding="utf-8-sig")
        assert read_ini_value(cfg, "section1", "KEY1") == "v1"
        update_config(cfg, "section1", "KEY1", "v2")
        assert read_ini_value(cfg, "section1", "key1") == "v2"

    def test_read_ini_value_keeps_last_value_with_duplicate_key(self, tmp_path: Path, log_capture: list[str]) -> None:
        # 读侧同病同治：strict 形态下这份文件读不出任何键（返回 None + 一条「读取异常」warning），
        # 容错后按「最后一次取值」返回，与 tolerant_config_parser 的语义一致。
        cfg = tmp_path / "config.ini"
        cfg.write_text("[s]\nk = first\nk = second\n", encoding="utf-8-sig")
        assert read_ini_value(cfg, "s", "k") == "second"
        assert not any("Error occurred while reading" in m for m in log_capture), log_capture

    def test_update_config_does_not_import_config_read_at_module_level(self) -> None:
        # 结构锁：utils 位于依赖链最底层，而 src/config_read → src/web_config → src/utils 是既有链，
        # 把 config_read 提到 utils 顶层 import 会构成导入环（环里 atomic_write_text 尚未定义）。
        # 判据取「源码里 config_read 只出现在函数体内」——AST 级、随重构自动失效，不会像
        # 文本匹配那样被注释里的同名提及骗到。
        tree = ast.parse(inspect.getsource(utils_module))
        # ast.Import 没有 level 属性（只有 ImportFrom 有），统一用 getattr 取，缺省按绝对导入算
        top_level = [
            node
            for node in tree.body
            if isinstance(node, (ast.Import, ast.ImportFrom)) and getattr(node, "level", 0) == 0
        ]
        imported: list[str] = []
        for node in top_level:
            if isinstance(node, ast.ImportFrom):
                imported.append(node.module or "")
            else:
                imported.extend(alias.name for alias in node.names)
        assert "src.config_read" not in imported, "config_read 必须在函数内延迟导入，否则 utils 成环"
        assert "src.utils" not in imported


class TestGetFilePaths:
    # Test get_file_paths.

    # 须递归列出目录下所有文件（含子目录），返回数量与路径匹配
    def test_returns_files(self, tmp_path: Path) -> None:
        (tmp_path / "a.txt").write_text("hello")
        sub = tmp_path / "sub"
        sub.mkdir()
        (sub / "b.txt").write_text("world")
        result = get_file_paths(str(tmp_path))
        assert len(result) == 2
        assert any("a.txt" in p for p in result)
        assert any("b.txt" in p for p in result)

    def test_empty_directory(self, tmp_path: Path) -> None:
        result = get_file_paths(str(tmp_path))
        assert result == []


class TestRemoveEmojis:
    # Test remove_emojis.

    # 无 emoji 文本须原样返回，不引入多余空白
    def test_no_emojis(self) -> None:
        assert remove_emojis("hello world") == "hello world"

    def test_with_emojis(self) -> None:
        # \U0001f600 为笑脸 emoji（多字节），验证其被剥离而非残留乱码或报错
        result = remove_emojis("hello \U0001f600 world")
        assert result == "hello  world"

    def test_replace_text(self) -> None:
        # 提供 replace 参数时 emoji 被替换为占位串而非删除，保留文本长度结构
        result = remove_emojis("hello \U0001f600", "[emoji]")
        assert result == "hello [emoji]"


# handle_proxy_addr 规范化代理地址，补齐 http 前缀。
# 守卫 None/空/有无前缀四种输入。
class TestHandleProxyAddr:
    # Test handle_proxy_addr.

    # None 代理须返回 None，避免把 None 当字符串传给 requests
    def test_none_returns_none(self) -> None:
        assert handle_proxy_addr(None) is None

    def test_empty_returns_none(self) -> None:
        # 空串代理视为未配置，返回 None（不应把空串当地址传给 requests）
        assert handle_proxy_addr("") is None

    def test_no_prefix_adds_http(self) -> None:
        assert handle_proxy_addr("127.0.0.1:8080") == "http://127.0.0.1:8080"

    def test_with_prefix_kept(self) -> None:
        assert handle_proxy_addr("https://proxy.com:1080") == "https://proxy.com:1080"


class TestJsonpToJson:
    # Test jsonp_to_json.

    def test_valid_jsonp(self) -> None:
        # 标准 callback({...}) 包裹的 JSONP 须正确提取为 dict
        jsonp = 'callback({"key": "value"});'
        result = jsonp_to_json(jsonp)
        assert result == {"key": "value"}

    def test_dotted_callback_name(self) -> None:
        # 回调名可含点号（命名空间，如 namespace.callback），正则须能匹配带点的名字
        jsonp = 'a.b.callback({"a": 1});'
        result = jsonp_to_json(jsonp)
        assert result == {"a": 1}

    def test_no_callback_raises(self) -> None:
        # 无法定位 callback(...) 包裹的 JSON 时必须抛 "No JSON data" 异常，而非返回 None 误导调用方
        with pytest.raises(Exception, match="No JSON data"):
            jsonp_to_json("not a jsonp string")


class TestReplaceUrl:
    # Test replace_url.

    # 整行即 URL 时须整行替换为新地址
    def test_replace_exact_line(self, tmp_path: Path) -> None:
        f = tmp_path / "test.txt"
        f.write_text("https://old.com/stream\nother line\n", encoding="utf-8-sig")
        replace_url(f, "https://old.com/stream", "https://new.com/stream")
        content = f.read_text(encoding="utf-8-sig")
        assert "https://new.com/stream" in content

    def test_replace_segment_in_config_line(self, tmp_path: Path) -> None:
        # M-18（2026-09-30）：URL_config.ini 的真实行形态是逗号分段，URL 段须整段替换。
        # [历史注] 本用例原为 `url = <url>` 行内子串替换形态（test_replace_inline），
        # 那正是 M-18 判定要移除的无边界子串行为。
        f = tmp_path / "URL_config.ini"
        f.write_text("https://old.com/live,主播: 张三,原画\n", encoding="utf-8-sig")
        replace_url(f, "https://old.com/live", "https://new.com/live")
        content = f.read_text(encoding="utf-8-sig")
        assert content == "https://new.com/live,主播: 张三,原画\n"

    def test_prefix_overlapping_sibling_line_untouched(self, tmp_path: Path) -> None:
        # M-18 变异判据（安全不变量）：URL 前缀重叠的兄弟房间行不得被误伤。旧实现的
        # `elif old in line: line.replace(...)` 会把 …/l/1234567 整行 replace 成
        # 「#…/l/123456」+「7,主播: 长号」尾巴——兄弟房间被静默注释（停止监测）。
        f = tmp_path / "URL_config.ini"
        f.write_text(
            "https://x.example/l/123456,主播: 短号\nhttps://x.example/l/1234567,主播: 长号\n",
            encoding="utf-8-sig",
        )
        replace_url(f, "https://x.example/l/123456", "#https://x.example/l/123456")
        content = f.read_text(encoding="utf-8-sig")
        assert content == "#https://x.example/l/123456,主播: 短号\nhttps://x.example/l/1234567,主播: 长号\n"

    def test_no_match_unchanged(self, tmp_path: Path) -> None:
        f = tmp_path / "test.txt"
        f.write_text("unrelated content\n", encoding="utf-8-sig")
        replace_url(f, "https://old.com", "https://new.com")
        content = f.read_text(encoding="utf-8-sig")
        assert "unrelated content" in content


# get_query_params 解析 URL query 参数，支持按 key 过滤。
# 守卫全量/单 key/缺失三种查询。
class TestGetQueryParams:
    # Test get_query_params.

    def test_all_params(self) -> None:
        result = get_query_params("https://example.com?a=1&b=2", None)
        assert "a" in result
        assert "b" in result

    # 指定 key 时只返回该 key 对应的值列表（支持多值）
    def test_specific_param(self) -> None:
        result = get_query_params("https://example.com?a=1&b=2", "a")
        assert result == ["1"]

    # 缺失的 key 须返回空列表而非 None 或抛出异常
    def test_missing_param(self) -> None:
        result = get_query_params("https://example.com?a=1", "missing")
        assert result == []


class TestTraceErrorGuard:
    # Test trace_error_decorator / trace_error_decorator_or_none（同步路径此前完全未覆盖）。

    # 同步正常路径：无异常时原样返回，不得落入任何兜底分支
    def test_sync_success(self) -> None:
        @trace_error_decorator
        def ok() -> dict[str, bool]:
            return {"is_live": True}

        assert ok() == {"is_live": True}

    # 同步 ProgramError（Node 环境缺失等 JS 执行失败）：吞异常返回 fallback，而非向调用方抛出
    def test_sync_program_error(self) -> None:
        @trace_error_decorator_or_none
        def boom() -> str:
            raise ProgramError("node missing")

        assert boom() is None

    # 同步任意异常：同样吞掉返回 fallback，把「崩溃」降级为「未开播/空结果」语义
    def test_sync_generic_error(self) -> None:
        @trace_error_decorator_or_none
        def boom() -> str:
            raise RuntimeError("disk gone")

        assert boom() is None

    # 异步包装器的 ProgramError 分支与同步是独立代码路径，须单独守卫
    async def test_async_program_error(self) -> None:
        @trace_error_decorator_or_none
        async def boom() -> str:
            raise ProgramError("node missing")

        assert await boom() is None


class TestUnzipFile:
    # Test unzip_file.

    # 正常解压：文件落位，且默认 delete=True 时源 zip 被清理（node/ffmpeg 安装缓存场景）
    def test_unzip_and_delete(self, tmp_path: Path) -> None:
        zip_file = tmp_path / "pkg.zip"
        with zipfile.ZipFile(zip_file, "w") as zf:
            zf.writestr("inner.txt", "payload")
        dest = tmp_path / "out"
        unzip_file(zip_file, dest)
        assert (dest / "inner.txt").read_text(encoding="utf-8") == "payload"
        assert not zip_file.exists()

    # delete=False 保留源 zip（共享缓存复用场景）
    def test_keep_zip_when_delete_false(self, tmp_path: Path) -> None:
        zip_file = tmp_path / "pkg.zip"
        with zipfile.ZipFile(zip_file, "w") as zf:
            zf.writestr("a.txt", "1")
        dest = tmp_path / "out"
        unzip_file(zip_file, dest, delete=False)
        assert (dest / "a.txt").exists()
        assert zip_file.exists()

    # Zip Slip 目录穿越必须被拒绝：成员经 ../ 逃逸出目标目录时抛 ValueError 且不落盘
    def test_zip_slip_rejected(self, tmp_path: Path) -> None:
        zip_file = tmp_path / "evil.zip"
        with zipfile.ZipFile(zip_file, "w") as zf:
            zf.writestr("../escape.txt", "pwn")
        dest = tmp_path / "out"
        with pytest.raises(ValueError, match="Unsafe path"):
            unzip_file(zip_file, dest)
        assert not (dest / "escape.txt").exists()


class TestReadConfigValueErrors:
    # Test read_ini_value 异常兜底。

    # ini 内容非法（缺 section 头）时 config.read 抛解析异常 → 必须返回 None 并打印原因，
    # 而非让解析异常击穿调用方（注意：目录路径等 OSError 会被 configparser.read 吞掉，走不到这里）
    def test_invalid_ini_returns_none(self, tmp_path: Path, log_capture: list[str]) -> None:
        bad_file = tmp_path / "bad.ini"
        bad_file.write_text("no_section_header = oops\n", encoding="utf-8")
        assert read_ini_value(bad_file, "s", "k") is None
        assert any("Error occurred while reading" in m for m in log_capture)


class TestUpdateConfigErrors:
    # Test update_config 异常兜底。

    # ini 内容非法时读取阶段失败 → 直接返回，目标文件内容保持原样
    def test_invalid_ini_returns_early(self, tmp_path: Path, log_capture: list[str]) -> None:
        cfg = tmp_path / "bad.ini"
        cfg.write_text("no_section_header = oops\n", encoding="utf-8")
        update_config(cfg, "s", "k", "v")
        assert any("An error occurred while reading" in m for m in log_capture)
        assert cfg.read_text(encoding="utf-8") == "no_section_header = oops\n"

    # 写失败（只读文件）必须被捕获并记录原因，源内容保留——只读目录/磁盘满等场景不应崩掉录制流程
    def test_readonly_file_write_failure(self, tmp_path: Path, log_capture: list[str]) -> None:
        cfg = tmp_path / "cfg.ini"
        cfg.write_text("[s]\nk = old\n", encoding="utf-8")
        cfg.chmod(0o444)
        try:
            update_config(cfg, "s", "k", "new")
            # WD-15 改为原子写（同目录 tmp + os.replace）后，失败信息由
            # utils.atomic_write_text 记录；文案为「写入配置文件失败（已保留原文件）」。
            # 注：原子写在部分平台会绕过只读文件本身（replace 只校验目录写权限），
            # 因此这里只断言「不抛异常 + 原内容不丢」，不强制要求必定失败。
            assert "k = old" in cfg.read_text(encoding="utf-8") or "k = new" in cfg.read_text(encoding="utf-8")
            _ = log_capture
        finally:
            cfg.chmod(0o644)  # 恢复可写，避免 pytest 清理 tmp_path 时因只读残留


class TestRemoveDuplicateLinesEncodingFallback:
    # Test remove_duplicate_lines 的编码回退路径。

    # utf-8-sig 严格读取撞上 UnicodeDecodeError → 须回退重读且去重结果正确。
    # 回退轮的编码：MIN-2244③ 之前是「系统默认编码」（宿主 locale），现改为显式
    # utf-8-sig + errors="surrogateescape"，故真实非 UTF-8 字节的用例已跨平台稳定
    # （见 test_regression_2026_09_22_utils.py 的 MIN-2244 段）；本用例仍用 monkeypatch
    # 模拟「严格轮炸掉」，为的是单独驱动回退分支本身而不是测解码器。
    def test_fallback_on_unicode_error(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        real_open = builtins.open

        # 只拦截严格解码那一轮：回退轮（errors="surrogateescape"）与回写必须放行走真 open。
        # MIN-2244③ 之后两轮编码同为显式 utf-8-sig（不再用宿主 locale），故拦截判据由
        # 「encoding」换成「errors」——否则回退轮也会被拦、用例根本测不到回退路径。
        def fake_open(file: Any, mode: str = "r", **kwargs: Any) -> IO[Any]:
            if "r" in mode and kwargs.get("errors") is None:
                raise UnicodeDecodeError("utf-8-sig", b"\xff", 0, 1, "simulated decode failure")
            return real_open(file, mode, **kwargs)

        monkeypatch.setattr(builtins, "open", fake_open)

        test_file = tmp_path / "dup.txt"
        test_file.write_text("alpha\nalpha\nbeta\n", encoding="ascii")
        remove_duplicate_lines(test_file)
        # 用 bytes 解码绕开被 patch 的 open，utf-8-sig 同时剥掉回写产生的 BOM
        content = test_file.read_bytes().decode("utf-8-sig")
        assert content.split() == ["alpha", "beta"]


# ── MID-28：mask_credentials 覆盖面表 ──────────────────────────
# 9 条取自 2026-09-20 审查的实测样本 + 「不得误伤」的公开地址样本。
# 键黑名单与三形态（查询串 / 请求头 / JSON 体）缺一即漏，故整表参数化。
class TestMaskCredentialsCoverage:
    @pytest.mark.parametrize(
        ("raw", "secret"),
        [
            # ① URL query 签名类（旧实现已覆盖，留作回归）
            ("https://p.example/a.flv?signature=AAAAAAA&wsTime=1699", "AAAAAAA"),
            ("https://p.example/a.flv?wsSecret=SECRETWS&wsTime=1699", "SECRETWS"),
            ("https://p.example/a.flv?txSecret=SECRETTX&txTime=6F2A", "SECRETTX"),
            # ② scheme 内代理凭据（旧实现已覆盖）
            ("http://user:pass@127.0.0.1:7890", "user:pass"),
            # ③ 无 scheme 的代理凭据（旧 _PROXY_CREDENTIAL_RE 依赖 ://，完全不认）
            ("user:pass@127.0.0.1:7890", "user:pass"),
            # ④⑤⑥ cookie / sid_guard / ttwid / verifyFingerprint（旧黑名单缺名）
            (
                "https://live.douyin.com/123?cookie=ttwid%7Cabc%7C1699; sid_guard=GUARDVAL%7C1699%7C15552000",
                "GUARDVAL",
            ),
            ("https://webcast.amemv.com/x?ttwid=TTWIDVALUE|1|1699&verifyFingerprint=VFPPPPPP", "TTWIDVALUE"),
            # ⑦ 请求头形态（旧实现两条正则都要求字面 =，永不匹配）
            ("Authorization: Bearer eyJhbGciOi.SECRETBEARER", "SECRETBEARER"),
            # ⑧⑨ JSON 体形态（同上）
            ('{"access_token": "JSONTOKENVALUE", "expires_in": 7200}', "JSONTOKENVALUE"),
            ('{"refresh_token":"RTVALUE","new":"keepme"}', "RTVALUE"),
        ],
    )
    def test_credentials_are_masked(self, raw: str, secret: str) -> None:
        masked = mask_credentials(raw)
        assert secret not in masked
        assert "***" in masked

    @pytest.mark.parametrize(
        "raw",
        [
            "https://live.douyin.com/746171898479",
            "https://www.huya.com/880214",
            "https://devlivepull.douyucdn.cn/live/1234567890.flv",
            "https://example.com/path?quality=10000&codec=h265&origin=1&design=2",
            "rtmp://push.example.com/app/streamid",
            "sender_name@qq.com 发件人邮箱",
            "序号3 主播名 正在录制中 https://live.douyin.com/746171898479",
            "wss://webcast100-ws-web-lf.douyin.com/webcast/im/push/v2/?room_id=1",
        ],
    )
    def test_public_urls_untouched(self, raw: str) -> None:
        # 「不得误伤公开平台地址」：普通房间号 / 画质参数 / 邮箱 / 无凭据形态必须逐字保留
        assert mask_credentials(raw) == raw

    def test_header_query_and_proxy_all_masked(self) -> None:
        # 一条日志里同时出现头形态、查询串形态与代理凭据时三处都要覆盖（旧实现只处理后者）
        text = "Cookie: ttwid=COOKIEVAL; proxy=http://u:p@10.0.0.1:80 url=https://x.example/a?sign=SIGNVAL"
        masked = mask_credentials(text)
        assert "COOKIEVAL" not in masked
        assert "u:p@" not in masked
        assert "SIGNVAL" not in masked

    def test_lookalike_keys_are_not_swallowed(self) -> None:
        # 非凭据键不得被误判：presigned / design 只是含同样的字母
        raw = "https://x.example/a?presigned=1&design=2"
        assert mask_credentials(raw) == raw

    def test_compound_and_prefixed_keys_still_masked(self) -> None:
        # 反过来：黑名单滞后于平台命名，my_token / x-signature 这类复合键仍须被认出来
        # （左侧只挡字母数字，不挡下划线与连字符）
        assert "SECRETVALUE" not in mask_credentials("https://x.example/a?my_token=SECRETVALUE")
        assert "SIGNATUREVALUE" not in mask_credentials("https://x.example/a?x-signature=SIGNATUREVALUE")

    @pytest.mark.parametrize(
        ("raw", "secret"),
        [
            # M-01（2026-10-02）：B 站主会话凭据与 CSRF 键、抖音 Cookie 会话键——修复前四键
            # 整体逃逸（query 形态实测原样返回）。判据是「值确实消失」，不只断言调用了过码。
            ("https://api.bilibili.com/x?SESSDATA=SESSVALUE123", "SESSVALUE123"),
            ("https://api.bilibili.com/x?bili_jct=JCTVALUE456", "JCTVALUE456"),
            ("sessionid_ss=SESSSSVAL; sid_tt=SIDTTVAL", "SESSSSVAL"),
            ("https://webcast.amemv.com/x?sid_tt=SIDTTVAL789", "SIDTTVAL789"),
        ],
    )
    def test_bili_douyin_session_keys_masked(self, raw: str, secret: str) -> None:
        assert secret not in mask_credentials(raw)
        assert "***" in mask_credentials(raw)

    def test_cookie_header_multi_segment_all_masked(self) -> None:
        # Cookie 头形态多段凭据：_SECRET_HEADER_RE 的值在首个 `;` 截断只抹第一段，
        # 剩余段由 query 形态正则逐段兜底（`bili_jct` 等键以 `=` 相连仍被认出）——
        # 修复前 `bili_jct` 不在黑名单、整段明文。每一段的值都必须确实消失。
        text = "Cookie: SESSDATA=SESSVAL1; bili_jct=JCTVAL2; sessionid_ss=SSVAL3; sid_tt=TTVAL4"
        masked = mask_credentials(text)
        for secret in ("SESSVAL1", "JCTVAL2", "SSVAL3", "TTVAL4"):
            assert secret not in masked


# ── MID-57 / MIN-21：原子写的耐久、临时名唯一性与权限保留 ───────
class TestAtomicWriteTextDurability:
    def test_fsync_happens_before_replace(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        # 顺序即不变量：close() 只把数据交给内核页缓存，若 fsync 晚于 replace，
        # 掉电仍可能留下「新目录项 + 空数据页」的 0 字节配置（WD-15 立论要消灭的形态）。
        # 只断言调用顺序，不假装验证了真实耐久性等。
        order: list[str] = []
        target = tmp_path / "cfg.ini"
        _ = target.write_text("old", encoding="utf-8")
        real_replace = os.replace

        def _spy_fsync(fd: int) -> None:
            assert isinstance(fd, int)
            order.append("fsync")

        def _spy_replace(src: str, dst: str) -> None:
            order.append("replace")
            real_replace(src, dst)

        monkeypatch.setattr(utils_module, "_fsync_file", _spy_fsync)
        monkeypatch.setattr(utils_module, "_replace", _spy_replace)
        assert atomic_write_text(target, "new content") is True
        assert order == ["fsync", "replace"]
        assert target.read_text(encoding="utf-8-sig") == "new content"

    def test_temp_names_are_unique_within_one_process(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        # MIN-21：原 tmp 名只含 pid → 同进程两线程写同一目标会共用同一个 tmp 文件
        # （互相截断），os.replace 可把半写内容替换进目标。现必须每线程各自独立。
        seen: list[str] = []
        contents: list[str] = []
        real_replace = os.replace

        def _spy_replace(src: str, dst: str) -> None:
            seen.append(src)
            # 在替换发生的那一刻读临时文件：必须是某个线程**完整**的内容
            with real_open(src, "r", encoding="utf-8-sig", newline="") as f:
                contents.append(f.read())
            real_replace(src, dst)

        real_open = builtins.open
        monkeypatch.setattr(utils_module, "_replace", _spy_replace)
        target = tmp_path / "same.ini"
        _ = target.write_text("", encoding="utf-8")
        payloads = [f"payload-{i}-" + ("x" * 5000) for i in range(4)]
        threads = [threading.Thread(target=lambda p=payloads[i]: atomic_write_text(target, p)) for i in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)
        # 审查 7.11（2026-10-18）：join 超时是静默返回的，seen 收满 4 条也不代表 4 条写线程都跑完
        # （replace 之后还有返回/清理路径），挂死形态必须显式判出来而不是留给下一条断言碰运气。
        alive = [t.name for t in threads if t.is_alive()]
        assert not alive, f"4 条并发写线程未在 10s 内退出（疑似原子写链挂死）：{alive}"
        assert len(seen) == 4
        assert len(set(seen)) == 4, "同进程并发写入共用了同一个临时文件"
        assert all(c in payloads for c in contents), "临时文件被其它线程截断/交错写入"
        assert target.read_text(encoding="utf-8-sig") in payloads

    @pytest.mark.skipif(sys.platform == "win32", reason="Windows 的 os.chmod 仅影响只读位，无法断言权限位")
    def test_original_file_mode_is_preserved(self, tmp_path: Path) -> None:
        # MIN-21：mkstemp 固定 0600，不回填原 mode 时任一整文件重写都会把公读文件收紧、
        # 或把 CR-07 收紧过的 0600 放宽回 umask 值（凭据文件权限被静默改变）。
        target = tmp_path / "cfg.ini"
        _ = target.write_text("old", encoding="utf-8")
        os.chmod(target, 0o644)
        assert atomic_write_text(target, "new") is True
        assert stat.S_IMODE(os.stat(target).st_mode) == 0o644
        os.chmod(target, 0o600)
        assert atomic_write_text(target, "newer") is True
        assert stat.S_IMODE(os.stat(target).st_mode) == 0o600
        assert target.read_text(encoding="utf-8-sig") == "newer"

    def test_replace_failure_leaves_original_and_returns_false(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        target = tmp_path / "cfg.ini"
        _ = target.write_text("keepme", encoding="utf-8")

        def _deny(src: str, dst: str) -> None:
            raise PermissionError(13, "simulated", dst)

        monkeypatch.setattr(utils_module, "_replace", _deny)
        assert atomic_write_text(target, "gone") is False
        assert target.read_text(encoding="utf-8") == "keepme"
        # 失败路径必须清掉自己留下的临时文件，不在配置目录里留残渣
        assert list(tmp_path.iterdir()) == [target]


# ── MID-29 / MIN-11：URL 配置旁路写盘必须持锁 + 原子 ────────────
class _LockRecorder:
    # 替身锁：记录 with 进入次数（main.file_update_lock 是 RLock，测试里换成计数器）

    def __init__(self) -> None:
        self.entered = 0

    def __enter__(self) -> "_LockRecorder":
        self.entered += 1
        return self

    def __exit__(self, *exc_info: object) -> None:
        return None


class TestUrlConfigWritePaths:
    def test_replace_url_holds_main_lock(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        import main as main_module

        f = tmp_path / "URL_config.ini"
        _ = f.write_text("https://old.example/1\n", encoding="utf-8-sig")
        recorder = _LockRecorder()
        monkeypatch.setattr(main_module, "file_update_lock", recorder)
        replace_url(f, "https://old.example/1", "https://new.example/1")
        assert recorder.entered == 1
        assert "https://new.example/1" in f.read_text(encoding="utf-8-sig")

    def test_remove_duplicate_lines_holds_main_lock(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        import main as main_module

        f = tmp_path / "URL_config.ini"
        _ = f.write_text("a\na\nb\n", encoding="utf-8-sig")
        recorder = _LockRecorder()
        monkeypatch.setattr(main_module, "file_update_lock", recorder)
        remove_duplicate_lines(f)
        assert recorder.entered == 1
        assert f.read_text(encoding="utf-8-sig").split() == ["a", "b"]

    def test_replace_url_never_truncates_target(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        # MID-29①②：写盘必须经「同目录临时文件 + os.replace」。判据用真 open 拦截：
        # 任何以 "w" 直开目标文件的路径都会先 truncate（读方可见空/半写；Windows 上还会
        # 让对端的 os.replace 抛 PermissionError），这里直接让它炸掉。
        real_open = builtins.open
        target = tmp_path / "URL_config.ini"
        _ = target.write_text("https://old.example/1\n", encoding="utf-8-sig")

        def _deny_target_writes(file: Any, mode: str = "r", **kwargs: Any) -> IO[Any]:
            if "w" in mode and str(file) == str(target):
                raise AssertionError("非原子写：直接以 w 打开目标文件")
            return real_open(file, mode, **kwargs)

        monkeypatch.setattr(builtins, "open", _deny_target_writes)
        replace_url(target, "https://old.example/1", "#https://old.example/1")
        # 经 os.fdopen 的原子写不受该拦截影响，内容确已更新
        assert target.read_text(encoding="utf-8-sig") == "#https://old.example/1\n"

    def test_replace_url_preserves_crlf_endings(self, tmp_path: Path) -> None:
        # 与 config_io.update_file 的 MI-11 口径一致：一次替换不得把 CRLF 整体改成 LF
        target = tmp_path / "URL_config.ini"
        with open(target, "w", encoding="utf-8-sig", newline="") as f:
            _ = f.write("https://a.example/1\r\nhttps://b.example/2\r\n")
        replace_url(target, "https://a.example/1", "https://c.example/3")
        with open(target, "r", encoding="utf-8-sig", newline="") as f:
            lines = f.readlines()
        assert lines == ["https://c.example/3\r\n", "https://b.example/2\r\n"]

    def test_remove_duplicate_lines_fallback_clears_first_pass(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # MIN-11：首轮按 utf-8-sig 读到一半才抛 UnicodeDecodeError 时，已读进 OrderedDict 的
        # 那几行必须清空，否则两轮结果混在同一 dict、把首轮产物写回文件。
        # 用「读出一行后才炸」的假句柄模拟，直接锁定 clear() 这一步本身（真字节的非 UTF-8
        # 往返另有跨平台稳定的用例，见 test_regression_2026_09_22_utils.py 的 MIN-2244③ 段）。
        real_open = builtins.open
        # 纯 ASCII 内容：回退轮（显式 utf-8-sig + surrogateescape）也必须得到同样结果
        target = tmp_path / "dup.txt"
        _ = target.write_text("alpha\nbeta\n", encoding="ascii")
        first_pass_line = "首轮残留行\n"

        class _HalfThenBoom:
            def __enter__(self) -> "_HalfThenBoom":
                return self

            def __exit__(self, *exc_info: object) -> None:
                return None

            def __iter__(self) -> Any:
                yield first_pass_line
                raise UnicodeDecodeError("utf-8-sig", b"\xff", 0, 1, "simulated mid-file failure")

        def fake_open(file: Any, mode: str = "r", **kwargs: Any) -> IO[Any]:
            # 判据取 errors：MIN-2244③ 后两轮编码同为显式 utf-8-sig，只有严格轮不带 errors
            if "r" in mode and kwargs.get("errors") is None:
                return cast("IO[Any]", _HalfThenBoom())
            return real_open(file, mode, **kwargs)

        monkeypatch.setattr(builtins, "open", fake_open)
        remove_duplicate_lines(target)
        written = target.read_bytes().decode("utf-8-sig")
        assert written.split() == ["alpha", "beta"]
        assert first_pass_line not in written, "回退分支未清空首轮结果（MIN-11 回归）"


# ── MID-62：run_node_script_async 校验与执行的必须是同一份内容 ──
class TestRunNodeScriptNoToctou:
    @pytest.mark.asyncio
    async def test_verified_bytes_are_the_executed_bytes(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        # 旧实现「读文件算哈希 → 把**路径**交给 node」：node 会独立二次读盘，
        # 两步之间换掉文件内容即绕过钉定表（check-then-use）。
        # 现改为把校验过的那一份字节经 stdin 交给 node（argv 位置保持不变）。
        # [L-19 2026-10-19 适配] 执行原语从 subprocess.run 换成自管 Popen + communicate(input=…)，
        # 「把校验过的字节交给 node」这条契约因此落在 communicate 的 input 实参上（旧形态落在
        # run 的 input 关键字上），argv 与篡改时序的断言逐字保留、不改松。
        script = tmp_path / "sign.js"
        original = b"console.log('orig')"
        _ = script.write_bytes(original)
        captured: dict[str, object] = {}

        class _FakePopen:
            def __init__(self, argv: list[str], **kwargs: Any) -> None:
                captured["cmd"] = argv
                captured["spawn_kwargs"] = kwargs
                # 正常路径的退出码：run_node_script_async 用 proc.returncode 复刻 check=True 契约
                self.returncode: int | None = 0

            def communicate(self, *_args: Any, **kwargs: Any) -> tuple[bytes, bytes]:
                captured["input"] = kwargs.get("input")
                captured["timeout"] = kwargs.get("timeout")
                return b"  ok\n", b""

            def kill(self) -> None:
                raise AssertionError("正常路径不该走到进程树回收")

            def wait(self, timeout: Any = None) -> int:
                raise AssertionError("正常路径不该走到收尸")

        # subprocess 是 stdlib 模块本体，不得就地改属性（AGENTS 测试约定）→ 浅拷贝 shim 替换
        shim = SimpleNamespace(**vars(subprocess))
        shim.Popen = _FakePopen
        monkeypatch.setattr(utils_module, "subprocess", shim)
        checked: list[bytes] = []
        real_check = utils_module._check_js_hash

        def _spy_check(js_path: str, raw: bytes) -> None:
            checked.append(raw)
            # 在「校验」与「执行」之间篡改磁盘上的文件：旧实现会让 node 执行被篡改的副本
            script.write_bytes(b"console.log('evil')")
            real_check(js_path, raw)

        monkeypatch.setattr(utils_module, "_check_js_hash", _spy_check)
        result = await run_node_script_async(str(script), "https://example/x", timeout=5)
        assert result == "ok"
        assert captured["cmd"] == ["node", "-", "https://example/x"]
        assert captured["input"] == original, "交给 node 的不是校验过的那份字节（TOCTOU 回归）"
        assert captured["timeout"] == 5, "内层超时预算必须真的传给了 communicate（缺了它 node 卡住即整轮挂死）"
        assert checked == [original]

    def test_pinned_node_script_does_not_rely_on_its_own_path(self) -> None:
        # 选 stdin 方案的代价：经 stdin 执行的脚本里 __filename 是 "-"、__dirname 指向 CWD，
        # 不能再按自身所在目录解析相对路径。本用例把「唯一使用者 migu.js 只读 argv[2]」
        # 钉成契约：将来若接入依赖 __dirname 的脚本，此断言变红，必须改走「私有副本」变体
        # 而不是直接退回传路径（那样会重新引入 TOCTOU）。
        src = Path(__file__).resolve().parents[1] / "src" / "javascript" / "migu.js"
        if not src.is_file():  # pragma: no cover - 打包环境可能不含源码
            pytest.skip("migu.js 不在仓库内")
        text = src.read_text(encoding="utf-8")
        assert "process.argv[2]" in text
        assert "__filename" not in text
        assert "__dirname" not in text
        assert "require(" not in text


# ── L-19（2026-10-19）：run_node_script_async 的超时预算与进程树回收 ──
# 锁两层，缺一层就退化成「静默挂死」：
#   ① 内层 communicate(timeout=) —— 唯一能真正回收 node 进程树的一层；超时后必须收**整棵树**
#      （POSIX start_new_session + killpg / Windows taskkill /T /F），且**绝不再读一次管道**
#      （subprocess.run 的超时分支正是栽在 kill 后又调一次不带超时的 communicate 上）；
#   ② 外层 asyncio.wait_for —— 管 await 侧：阻塞段在 to_thread 的线程里，而线程不可取消，
#      ① 不生效时协程就永久 await，房间线程不归还网络信号量（AGENTS「并发与事件循环」最忌形态）。
# 平台分支由模块级常量 _NODE_TREE_KILL_VIA_TASKKILL 选择，用例强制置位，
# 让 Windows 回收链在 Linux CI 上真实执行（AGENTS「平台专属分支的测试不得靠 skipif」）。
class _HangingPopen:
    # communicate 永不返回（模拟孙进程握着 stdout 管道写端）；调用方给 input 是为了与真实形态一致。
    def __init__(self, argv: list[str], **kwargs: Any) -> None:
        self.pid = 4242
        self.returncode: int | None = None

    def communicate(self, *_args: Any, **kwargs: Any) -> tuple[bytes, bytes]:
        threading.Event().wait(0.6)
        return b"", b""

    def kill(self) -> None:
        self.returncode = -9

    def wait(self, timeout: Any = None) -> int:
        return -9


class _TimeoutPopen:
    # communicate 按真实语义在预算到点时抛 TimeoutExpired；顺带记账「有没有被二次调用」
    # ——再读一次管道就是 subprocess.run 的挂死形态，必须只发生一次。
    instances: list["_TimeoutPopen"] = []

    def __init__(self, argv: list[str], **kwargs: Any) -> None:
        self.pid = 4242
        self.returncode: int | None = None
        self.communicate_calls = 0
        self.kill_calls = 0
        self.wait_timeouts: list[Any] = []
        _TimeoutPopen.instances.append(self)

    def communicate(self, *_args: Any, **kwargs: Any) -> tuple[bytes, bytes]:
        self.communicate_calls += 1
        raise subprocess.TimeoutExpired(["node", "-"], cast("float", kwargs.get("timeout", 1.0)))

    def kill(self) -> None:
        self.kill_calls += 1

    def wait(self, timeout: Any = None) -> int:
        self.wait_timeouts.append(timeout)
        self.returncode = -9
        return -9


@pytest.fixture(autouse=True)
def _reset_node_poppen_registry() -> Generator[None, None, None]:
    _TimeoutPopen.instances = []
    yield
    _TimeoutPopen.instances = []


def _node_subprocess_shim(popen_cls: type) -> SimpleNamespace:
    # vars(subprocess) 浅拷贝保留 PIPE / TimeoutExpired / CalledProcessError 等常量，只换 Popen
    shim = SimpleNamespace(**vars(subprocess))
    shim.Popen = popen_cls
    return shim


class TestRunNodeScriptTimeoutBudget:
    def test_signature_exposes_a_positive_timeout(self) -> None:
        # 与姊妹函数 run_js_async 同口径：预算存在、可关键字覆盖、默认值为正
        param = inspect.signature(utils_module.run_node_script_async).parameters["timeout"]
        assert param.kind is inspect.Parameter.KEYWORD_ONLY
        assert isinstance(param.default, (int, float))
        assert cast("float", param.default) > 0

    @pytest.mark.asyncio
    async def test_coroutine_returns_at_budget_even_when_the_worker_thread_hangs(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # 判据②的正面锁：删掉外层 wait_for（回到 `return await asyncio.to_thread(_sync_run)`）
        # 本用例就永久 await 到超时被 pytest-asyncio 掐掉而转红。
        script = tmp_path / "sign.js"
        script.write_bytes(b"console.log(1)")
        utils_module._js_unpinned_warned.add("sign.js")  # 不打「未登记」告警，保持 0 警告口径
        monkeypatch.setattr(utils_module, "subprocess", _node_subprocess_shim(_HangingPopen))
        started = time.monotonic()
        with pytest.raises(TimeoutError):
            await run_node_script_async(str(script), "u", timeout=0.2)
        assert time.monotonic() - started < 0.5, "外层预算必须与内层同值，不得额外加宽限"

    @pytest.mark.asyncio
    @pytest.mark.parametrize("via_taskkill", [True, False], ids=["windows-taskkill", "posix-killpg"])
    async def test_communicate_timeout_reaps_the_whole_process_tree(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, via_taskkill: bool
    ) -> None:
        script = tmp_path / "sign.js"
        script.write_bytes(b"console.log(1)")
        utils_module._js_unpinned_warned.add("sign.js")
        run_calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

        shim = _node_subprocess_shim(_TimeoutPopen)

        def fake_run(argv: object, **kwargs: object) -> SimpleNamespace:
            run_calls.append((cast("tuple", tuple(argv) if isinstance(argv, list) else (argv,)), kwargs))
            return SimpleNamespace(returncode=0, stdout=b"", stderr=b"")

        shim.run = fake_run
        monkeypatch.setattr(utils_module, "subprocess", shim)
        monkeypatch.setattr(utils_module, "_NODE_TREE_KILL_VIA_TASKKILL", via_taskkill)
        posix_calls: list[int] = []
        monkeypatch.setattr(utils_module, "_kill_posix_process_group", lambda pid: posix_calls.append(pid))

        with pytest.raises(subprocess.TimeoutExpired):
            await run_node_script_async(str(script), "u", timeout=1.0)

        proc = _TimeoutPopen.instances[0]
        assert proc.communicate_calls == 1, "超时后不得再读一次管道（那正是 subprocess.run 的挂死点）"
        assert proc.kill_calls == 1, "回收必须退化到杀直接子进程"
        assert proc.wait_timeouts, "必须收尸（Popen.__del__ 见 returncode 为 None 会发 ResourceWarning）"
        assert proc.wait_timeouts[0] is not None, "收尸必须带上限，无界等待正是本次要消灭的形态"
        if via_taskkill:
            assert posix_calls == [], "Windows 分支不该再去碰 killpg"
            assert run_calls, "Windows 分支必须发 taskkill"
            argv, kwargs = run_calls[0]
            assert list(argv) == ["taskkill", "/T", "/F", "/PID", "4242"], argv
            # argv 列表 + check=False + **禁 shell=True**：参数位是 pid，交给 cmd 解释等于把
            # 「不用 shell」的前提推倒（AGENTS 录后脚本回收同口径）
            assert kwargs.get("shell") is not True and "shell" not in kwargs, kwargs
            assert kwargs.get("check") is False, kwargs
        else:
            assert posix_calls == [4242], "POSIX 分支必须 killpg 整个进程组"
            assert run_calls == [], "POSIX 分支不该去起 taskkill（本机没有该命令）"

    @pytest.mark.asyncio
    async def test_tree_kill_failure_still_kills_child_and_reraises(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # 「任一步失败退化到 kill()」：Linux CI 上被强制走 Windows 分支时压根没有 taskkill
        # （FileNotFoundError），回收失败**不得**改写超时语义——异常必须照原样上抛。
        script = tmp_path / "sign.js"
        script.write_bytes(b"console.log(1)")
        utils_module._js_unpinned_warned.add("sign.js")
        shim = _node_subprocess_shim(_TimeoutPopen)

        def deny(*args: object, **kwargs: object) -> None:
            raise FileNotFoundError("taskkill not found")

        shim.run = deny
        monkeypatch.setattr(utils_module, "subprocess", shim)
        monkeypatch.setattr(utils_module, "_NODE_TREE_KILL_VIA_TASKKILL", True)
        captured: list[str] = []
        sink_id = logger.add(lambda msg: captured.append(str(msg)), format="{message}", level="WARNING")
        try:
            with pytest.raises(subprocess.TimeoutExpired):
                await run_node_script_async(str(script), "u", timeout=1.0)
        finally:
            logger.remove(sink_id)
        proc = _TimeoutPopen.instances[0]
        assert proc.kill_calls == 1
        assert any("回收 node 签名子进程树失败" in m and "FileNotFoundError" in m for m in captured), captured

    @pytest.mark.asyncio
    async def test_spawn_kwargs_match_the_platform_contract(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # start_new_session 只属于 POSIX：Windows 侧那是 unused_start_new_session（传了零收益、
        # 还把 POSIX 语义塞进进程创建参数），本仓实测过一次偶发 WinError 50。
        # killpg 只有让子进程自成会话才收得到整棵树，故 POSIX 分支必须带上它。
        script = tmp_path / "sign.js"
        script.write_bytes(b"console.log(1)")
        utils_module._js_unpinned_warned.add("sign.js")
        seen: list[dict[str, object]] = []

        class _RecordingPopen(_HangingPopen):
            def __init__(self, argv: list[str], **kwargs: Any) -> None:
                super().__init__(argv, **kwargs)
                seen.append(kwargs)

        monkeypatch.setattr(utils_module, "subprocess", _node_subprocess_shim(_RecordingPopen))
        for via_taskkill, expected in ((True, False), (False, True)):
            monkeypatch.setattr(utils_module, "_NODE_TREE_KILL_VIA_TASKKILL", via_taskkill)
            with pytest.raises(TimeoutError):
                await run_node_script_async(str(script), "u", timeout=0.2)
            # 判据取**值**而不是「键在不在」：只判 in 的话 `start_new_session=False` 这种
            # 「POSIX 忘了开独立会话」的变异会带着键一起通过（变异短 id L19C 实测如此）。
            assert bool(seen[-1].get("start_new_session", False)) is expected, seen[-1]

    def test_posix_gate_direction_is_locked_in_source(self) -> None:
        # ③ 的门控方向锁：os.killpg/os.getpgid/signal.SIGKILL 是 POSIX-only 符号（typeshed 在
        # win32 不导出它们），必须用 sys.platform **字面量**早返回门控，否则本机 mypy（win32）红；
        # 门控条件写反（!= "win32"）静态检查发现不了、Windows 上会真去调 killpg。
        # 剥掉注释行：函数上方的解释性注释里也写了 sys.platform/win32，不剥会被自己的注释误判。
        src = inspect.getsource(utils_module._kill_posix_process_group)
        body = "\n".join(line for line in src.splitlines() if not line.strip().startswith("#"))
        assert 'if sys.platform == "win32":' in body, body
        assert 'sys.platform != "win32"' not in body, "门控条件写反＝Windows 上真去调 killpg"
        assert body.index('if sys.platform == "win32":') < body.index("os.killpg("), "早返回排在 killpg 之后＝门控无效"

    def test_kill_posix_process_group_is_a_noop_on_windows(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # 行为侧证据：本机若真是 win32，绝不允许真发 SIGKILL（Linux 上 getpgid(真 PID)+killpg
        # 会把跑测试的进程自己打死，两种平台形态一起断言才不会「只在某一侧被验过」）。
        calls: list[tuple[int, int]] = []
        os_shim = SimpleNamespace(**vars(os))
        os_shim.getpgid = lambda pid: int(pid) + 1
        os_shim.killpg = lambda pgid, sig: calls.append((pgid, int(sig)))
        monkeypatch.setattr(utils_module, "os", os_shim)
        utils_module._kill_posix_process_group(4242)
        if sys.platform == "win32":
            assert calls == [], "win32 门控失效：Windows 上真去调了 killpg"
        else:
            assert calls == [(4243, int(signal.SIGKILL))], calls

    def test_node_execution_does_not_use_subprocess_run(self) -> None:
        # 结构锁：subprocess.run 的超时分支会在 kill 后再调一次不带超时的 communicate()——
        # 那是 L-19 的根因，不得被「顺手改回 run」的重构复活。run 只允许出现在回收 taskkill 那一处。
        src = inspect.getsource(utils_module.run_node_script_async)
        body = "\n".join(line for line in src.splitlines() if not line.strip().startswith("#"))
        assert "subprocess.run" not in body, "run_node_script_async 本体不得再用 subprocess.run 执行 node"
        assert "proc.communicate(" in body and "timeout=timeout" in body, body


# ── 补-03 / 补-04：钉定表只覆盖在用的签名脚本 ───────────────────
class TestJsPinTable:
    def test_dead_scripts_are_unpinned(self) -> None:
        # laixiu.js / taobao-sign.js 在全仓 *.py 内除钉定表外零调用点（来秀已用纯 Python
        # calculate_sign 重写、淘宝签名无入口），且 taobao-sign.js 注释里留有真实抓包样本。
        assert "laixiu.js" not in utils_module._JS_SHA256_EXPECTED
        assert "taobao-sign.js" not in utils_module._JS_SHA256_EXPECTED
        # 其余 5 份仍在用，一条都不能少
        assert set(utils_module._JS_SHA256_EXPECTED) == {
            "crypto-js.min.js",
            "haixiu.js",
            "liveme.js",
            "migu.js",
            "x-bogus.js",
        }

    def test_pinned_scripts_exist(self) -> None:
        js_dir = Path(__file__).resolve().parents[1] / "src" / "javascript"
        if not js_dir.is_dir():  # pragma: no cover
            pytest.skip("src/javascript 不存在")
        for name in utils_module._JS_SHA256_EXPECTED:
            assert (js_dir / name).is_file(), f"钉定表引用了不存在的脚本 {name}"

    # MIN-2266 ①：上面两条只锁「表 == 硬编码 5 项」与「表里的键都有文件」，
    # 缺的是**反方向**——「目录里的每个 .js 都在表里」。缺了它，新增（或被投放）第 6 个
    # 签名脚本时 _check_js_hash 会走「未登记」分支静默放行，AGENTS 第③类钉定面悄悄缩小，
    # 而 black / isort / mypy / pytest 全绿。本用例即那条缺失的锁。
    def test_every_executable_js_is_pinned(self) -> None:
        js_dir = Path(__file__).resolve().parents[1] / "src" / "javascript"
        if not js_dir.is_dir():  # pragma: no cover - 冻结包内可能不含源码
            pytest.skip("src/javascript 不存在")
        on_disk = sorted(p.name for p in js_dir.glob("*.js"))
        pinned = sorted(utils_module._JS_SHA256_EXPECTED)
        # 相等而非子集：只判「盘上的都在表里」会让表里残留已删脚本（反向漂移）无人发现。
        # 本仓刻意不设白名单——vendored 的 crypto-js.min.js 也照样钉了哈希；确需例外时
        # 须在 utils._JS_SHA256_EXPECTED 上方注明理由并同步放宽本断言，见该处注释。
        assert on_disk == pinned, f"盘上 *.js={on_disk} 与钉定表={pinned} 不一致（未登记的脚本=不校验的脚本）"

    def test_unregistered_js_emits_warning_once(self, tmp_path: Path, log_capture: list[str]) -> None:
        # 「未登记」不得再是静默分支：首见必须告警（MIN-2266 ①）。
        # 把告警改回 `return`（原实现）会让本用例变红——它就是那条变异验证要抓的形态。
        name = "evil-injected.js"
        utils_module._js_unpinned_warned.discard(name)
        utils_module._check_js_hash(str(tmp_path / name), b"console.log(1)")
        assert any(name in line for line in log_capture), f"未登记的 {name} 未产生任何告警：{log_capture}"
        assert any("未登记" in line for line in log_capture), "告警文案须说明「未登记」而非「哈希不符」"

    def test_unregistered_js_warning_is_deduped_per_name(self, tmp_path: Path, log_capture: list[str]) -> None:
        # 去重：run_node_script_async 每次都校验，未登记脚本若每条都告警会按房间数×轮数刷屏，
        # 把真线索淹掉（与「主播未开播的正常轮次刻意静默」同一口径）。
        name = "noisy-unpinned.js"
        utils_module._js_unpinned_warned.discard(name)
        utils_module._check_js_hash(str(tmp_path / name), b"a")
        utils_module._check_js_hash(str(tmp_path / name), b"b")
        assert sum(1 for line in log_capture if name in line) == 1, log_capture
