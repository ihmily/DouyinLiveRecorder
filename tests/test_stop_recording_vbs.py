# tests/test_stop_recording_vbs.py - 守护 StopRecording.vbs 的编码约定与进程匹配判据。
#
# 覆盖 MID-60 的三个形态：
#   ① 漏杀：pip 启动器 douyin-recorder.exe / -gui.exe / -web.exe 是独立映像名，
#      早先不在枚举内 → 以 pip 入口启动的录制主进程不被匹配，只有它的 ffmpeg 孙进程被杀，
#      主进程存活并在下一轮重新拉起（正是文件头声称已消除的竞态）；
#   ② 误杀：ENTRY_SHIM_KEY 曾是裸子串匹配，venv 目录恰好同名时其中任意 python 进程
#      （编辑器 LSP、pytest）都会被整树杀掉；进一步由「token 文件名前缀」
#      收紧为「剥掉启动器后缀后的整名匹配」，以关键字开头的同名数据文件不再定罪；
#   ③ 静默模式判据过松（Arguments.Count > 0），`/?` 之类误调用即跳过确认框直接强杀。
#
# 另外锁死文件编码：本文件由 wscript/cscript 按系统 ANSI 代码页解释，必须保存为
# UTF-16 LE（带 FF FE BOM）+ 全量 CRLF，改成 UTF-8 会让全部中文提示乱码（AGENTS 硬约定）。
#
# 行为用例把**真文件里的函数原文**抽进临时脚本用 cscript 驱动（不在测试里重写一份判据），
# 非 Windows（CI 的 linux runner）无 cscript 时按环境限制 skip。

import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
VBS_PATH = ROOT / "StopRecording.vbs"
CSCRIPT = shutil.which("cscript")

# 程序专属映像名（build_exe.py 的三个 name= + pyproject [project.scripts] 的三个启动器）
APP_IMAGE_NAMES = [
    "DouyinLiveRecorder.exe",
    "DouyinLiveRecorder-GUI.exe",
    "DouyinLiveRecorder-Web.exe",
    "douyin-recorder.exe",
    "douyin-recorder-gui.exe",
    "douyin-recorder-web.exe",
]


# 读出解码后的脚本文本（顺带验证 BOM 与编码可解码）。
def _vbs_text() -> str:
    raw = VBS_PATH.read_bytes()
    assert raw[:2] == b"\xff\xfe", "StopRecording.vbs 必须是 UTF-16 LE 且带 FF FE BOM（不得存成 UTF-8）"
    text = raw.decode("utf-16-le")
    assert text.startswith("\ufeff"), "BOM 解码后应为 U+FEFF 首字符"
    # M-02 审查修复：BOM 必须恰好一支——WSH 只剥离流首一个 BOM，第二个 U+FEFF
    # 会落在语句位置（其后才是注释符 '），cscript/wscript 直接报 800A408「无效字符」，
    # 紧急停录兜底脚本必然解析失败。上一轮双 BOM 事故（ff fe ff fe …）正是只查 raw[:2] 漏掉的。
    assert not text[1:].startswith("\ufeff"), "StopRecording.vbs 不得出现双重 BOM（第二支会打成 Invalid character）"
    # 全部换行必须是 CRLF：LF 计数等于 CRLF 计数即不存在孤立 LF
    assert text.count("\n") == text.count("\r\n"), "StopRecording.vbs 必须全量 CRLF，不得出现孤立 LF"
    return text[1:]


def _extract_block(text: str, name: str) -> str:
    # VBScript 的过程分两种：Function（有返回值）与 Sub（无返回值），结尾关键字同名。
    match = re.search(r"(Function|Sub) " + re.escape(name) + r"\(.*?\r\nEnd \1", text, re.S)
    assert match is not None, f"未在 StopRecording.vbs 中找到 {name}"
    return match.group(0)


def _vb_literal(value: str) -> str:
    # VBScript 字符串字面量：内部双引号按 "" 转义
    return '"' + value.replace('"', '""') + '"'


class TestEncodingContract:
    def test_utf16le_bom_and_crlf(self) -> None:
        _ = _vbs_text()

    def test_chinese_prompts_survive_roundtrip(self) -> None:
        # 乱码风险的实际表现：中文提示语必须能在解码后的文本里找到
        text = _vbs_text()
        assert "确定要结束所有直播录制进程吗" in text
        assert "已成功结束所有直播录制进程" in text


class TestThreeLayerMatchingDesign:
    def test_app_image_names_enumerated_once(self) -> None:
        # 映像名判定收敛到 IsAppImageName 一张表，避免查询串 / 归类 / 兜底三处各写一份
        text = _vbs_text()
        body = _extract_block(text, "IsAppImageName")
        for name in APP_IMAGE_NAMES:
            const = (
                "APP_EXE_"
                + {
                    "DouyinLiveRecorder.exe": "CLI",
                    "DouyinLiveRecorder-GUI.exe": "GUI",
                    "DouyinLiveRecorder-Web.exe": "WEB",
                    "douyin-recorder.exe": "SHIM_CLI",
                    "douyin-recorder-gui.exe": "SHIM_GUI",
                    "douyin-recorder-web.exe": "SHIM_WEB",
                }[name]
            )
            assert f'Const {const} = "{name}"' in text, f"缺少常量 {const}={name}"
            assert const in body, f"{const} 未进入 IsAppImageName 表"

    def test_wmi_query_covers_all_app_images(self) -> None:
        text = _vbs_text()
        collect = _extract_block(text, "CollectProcesses")
        query_part = collect.split("ExecQuery", 1)[1].split("End If", 1)[0]
        for const in ("APP_EXE_SHIM_CLI", "APP_EXE_SHIM_GUI", "APP_EXE_SHIM_WEB"):
            assert const in query_part, f"WMI 查询串漏掉 {const}（漏一个即漏杀该形态主进程）"

    def test_commandline_fallback_covers_all_app_images(self) -> None:
        text = _vbs_text()
        fallback = _extract_block(text, "TerminateAllProcesses_CommandLine")
        for const in ("APP_EXE_SHIM_CLI", "APP_EXE_SHIM_GUI", "APP_EXE_SHIM_WEB"):
            assert const in fallback, f"WMI 不可用时的兜底漏掉 {const}"

    def test_kill_order_main_tree_before_stray_ffmpeg(self) -> None:
        # 顺序不可调换：先杀 ffmpeg 会让存活的主进程在下一轮重新拉起（竞态）
        text = _vbs_text()
        main_flow = _extract_block(text, "StopRecordingProcesses")
        first = main_flow.index("TerminateProcesses(recorderList, True)")
        second = main_flow.index("TerminateProcesses(ffmpegList, False)")
        assert first < second


class TestSilentMode:
    def test_uses_explicit_switch_not_argument_count(self) -> None:
        # 只看赋值语句本身：解释性注释里提到旧判据是正常的（不得按「全文不含」来断言）
        text = _vbs_text()
        assert "silentMode = (WScript.Arguments.Count > 0)" not in text, "静默模式不得按「有无参数」判定"
        assert "silentMode = HasSilentSwitch()" in text
        assert '"-y"' in _extract_block(text, "HasSilentSwitch")


# ─── 行为用例（cscript 驱动真函数原文） ──────────────────────
def _vb_bool(value: bool) -> str:
    return "True" if value else "False"


# 把真文件里的函数原文（连同它依赖的辅助函数）搬进临时脚本，用 cscript 逐条求值。
# 之所以抽函数而不是跑整份 StopRecording.vbs：跑整份会真的结束进程。
def _drive(tmp_path: Path, consts: str, func_name: str, cases: list[tuple[str, bool]]) -> None:
    assert CSCRIPT is not None
    text = _vbs_text()
    deps = {
        # L-41：IsRecorderPython 的入口命中二次确认调用了 ContainsAtWordBoundary
        "IsRecorderPython": ["HasShimToken", "ContainsAtWordBoundary"],
        "HasShimToken": [],
    }.get(func_name, [])
    bodies = [_extract_block(text, name) for name in [func_name, *deps]]
    lines = ["Option Explicit", consts, *bodies, ""]
    for idx, (cmd, _expected) in enumerate(cases):
        lines.append(f'WScript.Echo "case{idx}=" & CStr({func_name}({_vb_literal(cmd)}))')
    script = "\r\n".join(lines) + "\r\n"
    scratch = tmp_path / "tmp_selftest.vbs"
    # 与主文件同编码写出：cscript 直接识别 UTF-16 LE + BOM，不受系统 ANSI 代码页影响
    scratch.write_bytes(b"\xff\xfe" + script.encode("utf-16-le"))
    proc = subprocess.run(
        [CSCRIPT, "//nologo", str(scratch)], capture_output=True, text=True, encoding="utf-8", timeout=120
    )
    assert proc.returncode == 0, f"cscript failed rc={proc.returncode} err={proc.stderr[-800:]}"
    got: dict[str, str] = {}
    for line in proc.stdout.splitlines():
        line = line.strip()
        if line.startswith("case") and "=" in line:
            key, value = line.split("=", 1)
            got[key] = value
    assert len(got) == len(cases), f"cscript 输出不完整：{proc.stdout[-500:]}"
    for idx, (cmd, expected) in enumerate(cases):
        assert got[f"case{idx}"] == _vb_bool(expected), f"{func_name}({cmd}) → {got[f'case{idx}']}，期望 {expected}"


class TestRecorderPythonMatching:
    CONSTS = "\r\n".join(
        [
            'Const ENTRY_SCRIPTS = "main.py|gui.py|web.py"',
            'Const ENTRY_SHIM_KEY = "douyin-recorder"',
            # L-41：IsRecorderPython 入口名命中后需按程序目录词边界二次确认
            'Const APP_DIR_KEY = "douyinliverecorder"',
        ]
    )

    @pytest.mark.skipif(CSCRIPT is None, reason="cscript 仅存在于 Windows（环境限制，非失败）")
    def test_venv_directory_named_like_shim_is_not_killed(self, tmp_path: Path) -> None:
        # MID-60② 的误杀形态：venv 目录恰好叫 douyin-recorder，其中编辑器 LSP 进程
        # 与测试进程都不得被判成录制主程序
        cases = [
            (r'"C:\venv\douyin-recorder\Scripts\python.exe" -m pylsp', False),
            (r'"C:\venv\douyin-recorder\Scripts\python.exe" -m pytest tests/test_main.py', False),
            (r"C:\venv\douyin-recorder\python.exe serve.py", False),
        ]
        _drive(tmp_path, self.CONSTS, "IsRecorderPython", cases)

    @pytest.mark.skipif(CSCRIPT is None, reason="cscript 仅存在于 Windows（环境限制，非失败）")
    def test_real_recorder_shapes_still_match(self, tmp_path: Path) -> None:
        cases = [
            # 源码启动：命令行含入口脚本且路径锚定到程序目录（L-41 二次确认后仍命中）
            (r'"C:\venv\x\Scripts\python.exe" D:\douyinliverecorder\main.py', True),
            (r'"C:\venv\x\Scripts\pythonw.exe" "D:\proj\DouyinLiveRecorder\gui.py"', True),
            # [历史注] L-41 收窄：入口名命中但命令行不含程序目录 → 不再定罪。
            # 旧用例预期 D:\proj\main.py 为 True——那正是「其他项目 main.py 被误杀」的形态。
            (r'"C:\venv\x\Scripts\python.exe" D:\proj\main.py', False),
            # pip 启动器形态：启动器 exe 作为首个 token（shim 分支不受 L-41 影响）
            (r'"C:\venv\x\Scripts\douyin-recorder.exe"', True),
            # 旧式 setuptools 脚本：启动器脚本作为第二个 token
            (r'"C:\venv\x\Scripts\python.exe" C:\venv\x\Scripts\douyin-recorder-script.py', True),
            (r"douyin-recorder main.py", True),
        ]
        _drive(tmp_path, self.CONSTS, "IsRecorderPython", cases)

    @pytest.mark.skipif(CSCRIPT is None, reason="cscript 仅存在于 Windows（环境限制，非失败）")
    def test_entry_script_boundary_hardening_kept(self, tmp_path: Path) -> None:
        # 既有加固不得回退：test_main.py 里的 "main.py" 前面是 '_'，不算入口脚本
        cases = [
            (r"C:\tools\pytest.exe tests/test_main.py", False),
            # [历史注] L-41：入口名命中还需程序目录词边界锚定——
            # 「--target main.py 且路径无关」的裸命中不再定罪；命令行含程序目录才命中。
            (r"C:\tools\runner.exe --target main.py", False),
            (r"C:\tools\runner.exe --target D:\douyinliverecorder\main.py", True),
        ]
        _drive(tmp_path, self.CONSTS, "IsRecorderPython", cases)

    @pytest.mark.skipif(CSCRIPT is None, reason="cscript 仅存在于 Windows（环境限制，非失败）")
    def test_shim_token_requires_whole_launcher_name(self, tmp_path: Path) -> None:
        consts = 'Const ENTRY_SHIM_KEY = "douyin-recorder"'
        cases = [
            (r'"d:\venv\scripts\douyin-recorder.exe" main.py', True),
            (r"c:\venv\douyin-recorder\scripts\python.exe pylsp.py", False),
            (r"python.exe d:\x\douyin-recorder-script.py", True),
            # 关键字出现在文件名中间（而非开头）不算：避免把无关同名文件一并杀掉
            (r"d:\x\my-douyin-recorder-helper.exe", False),
            # 路径含空格被 Split 切开时，关键字仍在某 token 的文件名开头
            (r'"c:\program files\douyin-recorder\scripts\douyin-recorder.exe" main.py', True),
            # 另两个 pip 入口（GUI / Web）的启动器形态
            (r'"C:\venv\x\Scripts\douyin-recorder-gui.exe"', True),
            (r'"C:\venv\x\Scripts\python.exe" C:\venv\x\Scripts\douyin-recorder-web-script.py', True),
            # 收紧（MID-60② 的残余误杀面）：以关键字开头的**同名数据文件**
            # 不得定罪——旧的前缀判据会把 python.exe d:\notes\douyin-recorder-guide.pdf
            # 这类进程整树 taskkill 掉（正是本仓「不得误杀编辑器 / 工具进程」的反面）。
            (r"python.exe d:\notes\douyin-recorder-guide.pdf", False),
            (r'"C:\tools\python.exe" -m pytest d:\douyin-recorder-notes.txt', False),
        ]
        _drive(tmp_path, consts, "HasShimToken", cases)
