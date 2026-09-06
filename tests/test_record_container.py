# 分段录制「容器 ↔ 扩展名」一致性回归测试（2026-09-04 P0 事故沉淀）。
#
# 背景：main.py 的 TS 分段分支曾把 -segment_format 写成 ipod（应为 mpegts），
# M4A 分段分支写成 mpegts（应为 ipod）——两个值被互换。ipod 是「iPod H.264 MP4」
# 子集封装器，codec tag 表里没有 HEVC 条目：HEVC 原画 copy 进去直接
# AVERROR(EINVAL) 退出（Windows 上退出码以无符号呈现为 4294967274），
# 而 H.264 并不报错、只是把 MP4 内容写进 .ts 文件名（静默损坏，比报错更难排查）。
#
# 本文件把「扩展名 → 容器」映射固化为断言，并禁止再出现裸字面量取值——
# 字面量错位能通过格式检查、类型检查与 AST 等价性校验，只有这类语义断言能拦住。

import ast
import sys
from pathlib import Path
from typing import Any

import pytest

from src.spider import extract_douyin_hevc_flv_url

_MAIN_PATH = Path(__file__).resolve().parent.parent / "main.py"


@pytest.fixture(scope="module")
def main_mod() -> Any:
    # 同 tests/test_main_fixes.py：main.py 的 _app_root() 基于 sys.argv[0] 定位 config/，
    # pytest 下 argv[0] 指向 pytest 自身，需在导入前修正为项目 main.py。
    old_argv = sys.argv[:]
    sys.argv = [str(_MAIN_PATH)]
    try:
        import main

        return main
    finally:
        sys.argv = old_argv


# 从 main.py 的 AST 中取出所有 "-segment_format" 后紧跟的取值节点：
# ffmpeg 命令是函数内的 list 字面量，取值节点的类型即「是否走了映射表」的唯一判据
def _segment_format_nodes() -> list[ast.expr]:
    tree = ast.parse(_MAIN_PATH.read_text(encoding="utf-8"))
    nodes: list[ast.expr] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.List):
            continue
        for index, item in enumerate(node.elts[:-1]):
            if isinstance(item, ast.Constant) and item.value == "-segment_format":
                nodes.append(node.elts[index + 1])
    return nodes


class TestSegmentFormatMapping:
    # 映射表本体：容器必须与输出文件扩展名严格一致

    def test_mapping_table_is_complete(self, main_mod: Any) -> None:
        assert main_mod.SEGMENT_FORMAT_BY_SUFFIX == {
            ".ts": "mpegts",
            ".flv": "flv",
            ".mkv": "matroska",
            ".mp4": "mp4",
            ".m4a": "ipod",
        }

    def test_ts_uses_mpegts_not_ipod(self, main_mod: Any) -> None:
        # 回归防线一：TS 曾误用 ipod → HEVC copy 直接 EINVAL 退出（退出码 4294967274）
        assert main_mod.SEGMENT_FORMAT_BY_SUFFIX[".ts"] == "mpegts"
        assert main_mod.SEGMENT_FORMAT_BY_SUFFIX[".ts"] != "ipod"

    def test_m4a_uses_ipod_not_mpegts(self, main_mod: Any) -> None:
        # 回归防线二：M4A 曾误用 mpegts → .m4a 文件里装的是 MPEG-TS，
        # 播放器按扩展名走 MP4 解复用，读到 TS 同步字节即报无法播放
        assert main_mod.SEGMENT_FORMAT_BY_SUFFIX[".m4a"] == "ipod"
        assert main_mod.SEGMENT_FORMAT_BY_SUFFIX[".m4a"] != "mpegts"


class TestNoBareSegmentFormatLiteral:
    # 取值来源：必须查表，禁止裸字面量（本次事故的根因就是两处裸字面量被互换）

    def test_scan_finds_all_branches(self) -> None:
        # 扫描本身必须命中 5 处（FLV/MKV/MP4/TS 视频 + 音频 M4A），
        # 否则下面的断言会退化成空跑的假绿
        assert len(_segment_format_nodes()) == 5

    def test_every_value_comes_from_mapping(self) -> None:
        for node in _segment_format_nodes():
            if isinstance(node, ast.Subscript):
                continue
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "get":
                continue
            pytest.fail(f"-segment_format 必须经 SEGMENT_FORMAT_BY_SUFFIX 查表，发现: {ast.unparse(node)}")

    def test_subscript_keys_are_registered(self, main_mod: Any) -> None:
        # 查表键必须是已注册的扩展名，否则运行期 KeyError 会直接中断录制
        for node in _segment_format_nodes():
            if not isinstance(node, ast.Subscript):
                continue
            key = node.slice
            assert isinstance(key, ast.Constant), f"查表键必须是字面量扩展名: {ast.unparse(node)}"
            # 用 unparse 输出而非直接插值 key.value：Constant.value 的类型含 bytes，
            # 直接 f-string 插值会触发 mypy str-bytes-safe
            assert key.value in main_mod.SEGMENT_FORMAT_BY_SUFFIX, f"扩展名未注册: {ast.unparse(key)}"

    def test_get_fallback_is_ipod(self) -> None:
        # 音频分支的 extension 可能是 mp3（only_audio_record 平台且保存类型不含 m4a），
        # 此时仍走 aac 编码，必须沿用 ipod 兜底而非抛 KeyError
        calls = [n for n in _segment_format_nodes() if isinstance(n, ast.Call)]
        assert len(calls) == 1
        assert isinstance(calls[0].args[-1], ast.Constant)
        assert calls[0].args[-1].value == "ipod"


class TestHevcFlvUrlCarriesCodecMarker:
    # hevc_flv_url 从直播间 HTML 正则抠出，此前不带 codec 参数，
    # 导致 _is_h265() 与 main.py 的 h265 兜底判定全部漏判，
    # HEVC 源伪装成普通 FLV 通过全部校验、直接进 -c copy。

    def test_appends_codec_marker(self) -> None:
        html = (
            '<script>var a = "https://pull-flv-q11.douyincdn.com/thirdgame/'
            'stream-731829344212345678.flv?expire=123\\u0026major_anchor_level=svip"</script>'
        )
        result = extract_douyin_hevc_flv_url(html)
        assert result is not None
        assert result.endswith("codec=h265")
        assert result.count("codec=") == 1

    def test_marker_is_visible_to_is_h265(self) -> None:
        # 端到端：补标记后下游判定必须能识别，否则这个修复等于没做
        from src.stream_select import _is_h265

        html = '"https://pull-flv-q11.douyincdn.com/thirdgame/stream-731829344212345678.flv?expire=123"'
        result = extract_douyin_hevc_flv_url(html)
        assert result is not None
        assert _is_h265(result) is True

    def test_existing_codec_is_not_duplicated(self) -> None:
        # 已带 codec 参数的地址原样返回，避免重复拼接污染 URL
        html = '"https://pull-flv-q11.douyincdn.com/thirdgame/stream-731829344212345678.flv?codec=h264"'
        result = extract_douyin_hevc_flv_url(html)
        assert result is not None
        assert result.count("codec=") == 1
        assert "codec=h264" in result

    def test_audio_only_still_skipped(self) -> None:
        # 补标记不能绕过「跳过纯音频流」的既有语义
        html = (
            '"https://pull-flv-q11.douyincdn.com/thirdgame/stream-731829344212345678.flv?only_audio=1"'
            '"https://pull-flv-q11.douyincdn.com/thirdgame/stream-731829344212345679.flv?expire=456"'
        )
        result = extract_douyin_hevc_flv_url(html)
        assert result is not None
        assert "stream-731829344212345679.flv" in result
        assert "only_audio=1" not in result


class TestDescribeReturnCode:
    # 退出码归一化：Windows 上 ffmpeg 的 -22 以无符号 4294967274 呈现，
    # 直接打印原值只能靠经验猜，换算回有符号并附 errno 语义才能指路。

    def test_unsigned_einval_is_normalized(self, main_mod: Any) -> None:
        described = main_mod._describe_return_code(4294967274)
        assert described.startswith("-22")
        assert "EINVAL" in described

    def test_known_codes_get_hint(self, main_mod: Any) -> None:
        assert "ffmpeg 常规错误" in main_mod._describe_return_code(1)

    def test_small_code_unchanged(self, main_mod: Any) -> None:
        assert main_mod._describe_return_code(0) == "0"

    def test_unknown_code_has_no_hint(self, main_mod: Any) -> None:
        # 未知取值不加提示，避免给日志堆噪音
        assert main_mod._describe_return_code(77) == "77"
