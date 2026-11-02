# 分段录制「容器 ↔ 扩展名」一致性回归测试（2026-09-04 P0 事故沉淀）。
#
# 背景：main.py 的 TS 分段分支曾把 -segment_format 写成 ipod（应为 mpegts），M4A 分支写成
# mpegts（应为 ipod）。ipod 是 iPod H.264 MP4 子集封装器，codec tag 表无 HEVC 条目：HEVC 原画
# copy 进去直接 AVERROR(EINVAL)（Windows 退出码呈现为 4294967274）；H.264 则不报错、只是把
# MP4 内容写进 .ts 文件名（静默损坏，比报错更难排查）。
#
# 本文件把「扩展名 → 容器」映射固化为断言，并禁止裸字面量取值——字面量错位能通过格式、类型与
# AST 等价性校验，只有这类语义断言能拦住。

import ast
import sys
from pathlib import Path
from typing import Any

import pytest

from src.spider import extract_douyin_hevc_flv_url

_MAIN_PATH = Path(__file__).resolve().parent.parent / "main.py"
# 同类回归的第二处定义点：转码/合流命令同用 -segment_format。
# 只扫 main.py 时「换个文件重犯」会完全绕过防线（2026-09-10 审查发现）。
_POSTPROCESS_PATH = Path(__file__).resolve().parent.parent / "src" / "video_postprocess.py"


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


# 从 main.py 的 AST 中取出所有 "-segment_format" 后紧跟的取值节点：ffmpeg 命令是函数内的 list
# 字面量，取值节点的类型即「是否走了映射表」的唯一判据。path 缺省 main.py，可传入第二处定义点。
def _segment_format_nodes(path: Path = _MAIN_PATH) -> list[ast.expr]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
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
            ".mp3": "mp3",
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


class TestSegmentFormatSecondDefinitionPoint:
    # src/video_postprocess.py 是同类回归的第二处定义点：该处取值来自函数参数（Name），容器值由
    # 调用方经 SEGMENT_FORMAT_BY_SUFFIX 传入。裸字面量互换正是 2026-09-04 事故的根因，故此处
    # 至少必须禁止字面量。

    def test_definition_point_still_exists(self) -> None:
        nodes = _segment_format_nodes(_POSTPROCESS_PATH)
        assert len(nodes) == 1, f"video_postprocess.py 的 -segment_format 定义点数量变化: {len(nodes)}"

    def test_value_is_not_bare_literal(self) -> None:
        for node in _segment_format_nodes(_POSTPROCESS_PATH):
            assert not isinstance(
                node, ast.Constant
            ), f"video_postprocess.py 的 -segment_format 不得使用裸字面量: {ast.unparse(node)}"


class TestNoBareSegmentFormatLiteral:
    # 取值来源：必须查表，禁止裸字面量（本次事故的根因就是两处裸字面量被互换）

    def test_scan_finds_all_branches(self) -> None:
        # 扫描本身必须命中 6 处（FLV/MKV/MP4/TS 视频 + 音频 M4A + 音频 MP3），否则下面的断言会
        # 退化成空跑假绿。MP3 分支于 2026-09-10 补齐：此前 MP3 分段无显式 -segment_format，容器
        # 靠 ffmpeg 按扩展名猜测，属「扩展名 ↔ 容器」错配的同类隐患。
        assert len(_segment_format_nodes(_MAIN_PATH)) == 6

    def test_every_value_comes_from_mapping(self) -> None:
        for node in _segment_format_nodes(_MAIN_PATH):
            if isinstance(node, ast.Subscript):
                continue
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "get":
                continue
            pytest.fail(f"-segment_format 必须经 SEGMENT_FORMAT_BY_SUFFIX 查表，发现: {ast.unparse(node)}")

    def test_subscript_keys_are_registered(self, main_mod: Any) -> None:
        # 查表键必须是已注册的扩展名，否则运行期 KeyError 会直接中断录制
        for node in _segment_format_nodes(_MAIN_PATH):
            if not isinstance(node, ast.Subscript):
                continue
            key = node.slice
            assert isinstance(key, ast.Constant), f"查表键必须是字面量扩展名: {ast.unparse(node)}"
            # 用 unparse 输出而非直接插值 key.value：Constant.value 的类型含 bytes，
            # 直接 f-string 插值会触发 mypy str-bytes-safe
            assert key.value in main_mod.SEGMENT_FORMAT_BY_SUFFIX, f"扩展名未注册: {ast.unparse(key)}"

    def test_no_get_fallback_masks_missing_key(self) -> None:
        # 回归防线（2026-09-10）：音频分支曾用 SEGMENT_FORMAT_BY_SUFFIX.get("." + extension, "ipod")，
        # 兜底会把「查表落空」静默掩盖成错误容器（纯音频平台在默认保存类型下产出 .mp3 却装 AAC/MP4）。
        # 现在 extension 与编码器同源推导、键值确定，一律直接下标取值，缺键以 KeyError 暴露。
        calls = [n for n in _segment_format_nodes(_MAIN_PATH) if isinstance(n, ast.Call)]
        assert not calls, f"-segment_format 不得再使用 .get 兜底: {[ast.unparse(c) for c in calls]}"

    def test_audio_branches_match_their_extension(self, main_mod: Any) -> None:
        # 两路音频的容器必须各自等于其扩展名对应的容器（.mp3→mp3、.m4a→ipod），
        # 且扩展名由与编码器同源的条件推导，杜绝「扩展名 ↔ 编码 ↔ 容器」三方错配
        assert main_mod.SEGMENT_FORMAT_BY_SUFFIX[".mp3"] == "mp3"
        assert main_mod.SEGMENT_FORMAT_BY_SUFFIX[".m4a"] == "ipod"


class TestHevcFlvUrlCarriesCodecMarker:
    # hevc_flv_url 从直播间 HTML 正则抠出，此前不带 codec 参数，导致 _is_h265() 与 main.py 的
    # h265 兜底判定全部漏判：HEVC 源伪装成普通 FLV 通过校验、直接进 -c copy。

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


class TestRecordOutputBytesSegmentShape:
    # MID-05（CODE_REVIEW_2026-09-20）：分段产物求和必须按**模板自身的扩展名**匹配。原实现把
    # `.ts` 写死在 glob 里 → 分段 FLV/MKV/MP4/音频恒不命中 → 恒返回 -1 → check_subprocess 的
    # 「零字节不得记成功」闭环在所有非 TS 分段形态上静默缺失（分段 FLV 恰是虎牙/斗鱼的常见形态）；
    # 且定长 `???` 漏计序号超过 999 的段。

    def test_segmented_flv_is_summed(self, main_mod: Any, tmp_path: Path) -> None:
        for index in (0, 1, 2):
            (tmp_path / f"主播_2026-09-20_10-00-00_{index:03d}.flv").write_bytes(b"\x00" * 100)
        template = str(tmp_path / "主播_2026-09-20_10-00-00_%03d.flv")
        assert main_mod._record_output_bytes(template, True) == 300

    def test_segmented_mkv_mp4_and_audio_are_summed(self, main_mod: Any, tmp_path: Path) -> None:
        for template_name, ext in (("_%03d.mkv", "mkv"), ("_%03d.mp4", "mp4"), ("_%02d.m4a", "m4a")):
            (tmp_path / f"主播_{ext}_000.{ext}").write_bytes(b"\x00" * 40)
            (tmp_path / f"主播_{ext}_001.{ext}").write_bytes(b"\x00" * 60)
            template = str(tmp_path / f"主播_{ext}{template_name}")
            assert main_mod._record_output_bytes(template, True) == 100, f"扩展名 {ext} 的分段未被求和"

    def test_segment_index_beyond_999_is_counted(self, main_mod: Any, tmp_path: Path) -> None:
        # ffmpeg 的 %03d 在段号超过 999 时输出 4 位，定长 `???` 会静默漏计这一段
        (tmp_path / "主播_ts_000.ts").write_bytes(b"\x00" * 10)
        (tmp_path / "主播_ts_1000.ts").write_bytes(b"\x00" * 250)
        template = str(tmp_path / "主播_ts_%03d.ts")
        assert main_mod._record_output_bytes(template, True) == 260

    def test_non_index_suffix_is_excluded(self, main_mod: Any, tmp_path: Path) -> None:
        # `_000_extra` 这类同前缀文件不得混进分段求和（与 _convert_after_record 的精确匹配口径一致）
        (tmp_path / "主播_ts_000.ts").write_bytes(b"\x00" * 10)
        (tmp_path / "主播_ts_000_extra.ts").write_bytes(b"\x00" * 5000)
        template = str(tmp_path / "主播_ts_%03d.ts")
        assert main_mod._record_output_bytes(template, True) == 10

    def test_missing_segments_still_return_minus_one(self, main_mod: Any, tmp_path: Path) -> None:
        # 「找不到任何分段」必须仍是 -1（跳过校验），不能被当成 0 字节判失败
        template = str(tmp_path / "主播_%03d.flv")
        assert main_mod._record_output_bytes(template, True) == -1

    def test_no_hardcoded_ts_glob_in_implementation(self) -> None:
        # 防回归：函数体里不得再出现写死 `.ts` / 定长 `???` 的 glob 模式
        tree = ast.parse(_MAIN_PATH.read_text(encoding="utf-8"))
        fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "_record_output_bytes")
        literals = [n.value for n in ast.walk(fn) if isinstance(n, ast.Constant) and isinstance(n.value, str)]
        offenders = [v for v in literals if "_???" in v or (".ts" in v and "*" in v)]
        assert not offenders, f"_record_output_bytes 不得再按固定扩展名 glob: {offenders}"


class TestSegmentTemplateDerivedFromPath:
    # MID-08：是否分段必须由「已冻结的命令输出模板」推导，不能读运行期热更新的全局

    def test_template_shapes_are_recognized(self, main_mod: Any) -> None:
        assert main_mod._is_segmented_output("/d/主播_2026-09-20_10-00-00_%03d.ts") is True
        assert main_mod._is_segmented_output("/d/主播_10-00-00_%02d.m4a") is True

    def test_plain_and_history_shaped_paths_are_not(self, main_mod: Any) -> None:
        assert main_mod._is_segmented_output("/d/主播_2026-09-20_10-00-00.ts") is False
        # FLV 非分段保留的历史 `_00` 后缀不含占位符，必须按单文件处理
        assert main_mod._is_segmented_output("/d/主播_2026-09-20_10-00-00_00.flv") is False
        # 标题里恰好出现 %d 不得被误判成分段模板（判定锚定在扩展名之前的序号位）
        assert main_mod._is_segmented_output("/d/主播%d_标题.ts") is False


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
