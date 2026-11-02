# -*- coding: utf-8 -*-
# GUI 窗口层（PySide6）里可复用的框架无关工具：外部数据数值容错、子进程状态行匹配、
# Windows 控制台信号、进程清理提示解码、配置文件原子写与变更裁决。
#
# 为什么与 gui.py 各存一份：若干用例仍以 AST 静态锁把同名实现钉在 gui.py 源码里
# （锁的是「函数定义存在于 gui.py」这一事实），且 tests/test_gui_status_pattern_i18n.py
# 等走子进程驱动 gui 模块本体，直接搬走会同时打断这些锁。故本模块是**过渡期的第二副本**：
# 旧 GUI 退役（见 docs/worklog/PROPOSAL_2026-10-17_gui-pyside6-redesign.md §5）后删 gui.py、
# 把静态锁的读取源切到这里，届时只剩一份实现。差异只在日志入口（这里不持有 GUI 对象）。
from __future__ import annotations

import ctypes
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from typing import Any, Final, cast

import i18n as i18n_module
from src.logger import logger
from src.utils import atomic_write_text, mask_credentials

# 降级告警的「失效等待窗口」（秒，MID-54）：一次画质降级告警之后，若连续这么久
# 仍在输出录制状态行且没有新的降级告警，就认为该房间已按设置档位正常录制，清除降级标记。
# 取值依据：main.py 的房间主循环周期默认 delay_default=120s（含 ±5s 抖动），而画质降级告警
# 在**每轮录制启动时**都会重打一次——所以「还在降级」的房间每个周期都会刷新 alert_at。
# 取 2 个周期是为了避开「状态线程先于本轮告警行到达」的竞态。
QUALITY_ALERT_TTL_SECONDS: Final[float] = 240.0

# 「彻底退出」复用在途「停止录制」线程时的等待预算（M-16，秒）。
# 取 25s = 停止链自身的上限：wait(15) + taskkill(5) + wait(5)。
STOP_REUSE_JOIN_SECONDS: Final[float] = 25.0

ANSI_ESCAPE_PATTERN: Final[re.Pattern[str]] = re.compile(r"\x1b\[[0-9;]*m")


# 判定某房间的降级告警是否已被后续正常轮次取代（MID-54 的纯判据，独立成函数供用例直接驱动）。
#
# 为什么不能只看「录制行里的画质 == 设置档」：src/recorder_status.py 打印
# "{name}[{qa}] 正在录制中" 时取的是 main.recording_time_list[name][1]——那是**设置档位**，
# 故录制行的画质恒等于设置档，本身证明不了降级已恢复。真正可靠的信号是时间先后。
def quality_alert_expired(info: dict[str, str | bool | float], now: float) -> bool:
    if not info.get("downgraded"):
        return False
    try:
        alert_at = float(info.get("alert_at") or 0.0)
    except TypeError, ValueError:
        # 脏数据按「告警已在很久以前」处理：宁可清掉一个可疑标记，也不要永久红着一行
        return True
    if alert_at <= 0.0:
        return False
    return (now - alert_at) > QUALITY_ALERT_TTL_SECONDS


# 外部数据数值字段的**唯一**容错口径（M-15 的 ts 容错与 M-17 的逐事件容错同族，刻意只写一份）：
# None / 空串 / 非数值字符串一律回落 default，合法数值原样取值。
# 触发源真实存在：弹幕边车 logs/danmaku_monitor.jsonl 是外部可控数据，且 tail 首读会回放
# 旧文件末尾 64KB 的历史记录（2026-09-12 审查 6.2 已记过 float(None) 的事故）。
def as_float(value: object, default: float = 0.0) -> float:
    try:
        return float(cast(Any, value))
    except TypeError, ValueError:
        return default


def as_int(value: object, default: int = 0) -> int:
    # OverflowError 也在列：JSON 允许 Infinity 字面量，float('inf') 过 int() 即抛它。
    try:
        return int(cast(Any, value))
    except TypeError, ValueError, OverflowError:
        return default


# ─── 子进程状态行匹配（M-14） ───
#
# 三条状态行的 msgid 必须与**生产侧逐字相同**，否则 tr() 查不到键、退化为恒等映射，
# 非简中界面下依旧匹配不上。生产侧出处（只读、不得改动）：
#   src/recorder_status.py::display_info → tr("{recording_live}[{qa}] 正在录制中 {have_record_time}")
#   src/recorder_status.py::display_info → tr("\r没有正在录制的直播 循环监测间隔时间：{delay_default}秒")
#   main.py 录制启动处 → tr("{record_name} 画质降级：…")
STATUS_TPL_RECORDING: Final[str] = "{recording_live}[{qa}] 正在录制中 {have_record_time}"
STATUS_TPL_IDLE: Final[str] = "\r没有正在录制的直播 循环监测间隔时间：{delay_default}秒"
STATUS_TPL_DOWNGRADE: Final[str] = (
    "{record_name} 画质降级：设置 {record_quality_zh}({record_quality})"
    " 实际 {actual_quality_zh}({actual_quality_code})"
)
# [2026-09-29 M-14②] 刻意不对称的一条：该串生产侧**未过 tr()**
# （src/recorder_status.py::display_info 裸写 print("\r没有正在监测和录制的直播")），
# 它是否被翻译完全取决于 main.py 的 builtins.print 补丁与 _should_translate 的路径前缀判定——
# 后者在 PyInstaller 冻结下是否仍成立尚未实测，故 GUI 侧必须「tr() 结果 + 原文」两种形态都认。
STATUS_TPL_EMPTY: Final[str] = "\r没有正在监测和录制的直播"

# 每条模板中 GUI **必须取用**的占位符（= 下面正则片段表里登记过的那些）。
STATUS_REQUIRED_RECORDING: Final[tuple[str, ...]] = ("recording_live", "qa")
STATUS_REQUIRED_DOWNGRADE: Final[tuple[str, ...]] = (
    "record_name",
    "record_quality_zh",
    "record_quality",
    "actual_quality_zh",
    "actual_quality_code",
)

# 各占位符在**译文**里应展开成的正则片段。
# F-06（2026-09-12 审查修复）的两条语义在这里逐字保持，不得回退：
#   recording_live 贪婪 .+  —— 主播名里的 "[...]" 不能被当成画质段边界；
#   qa            [^\]]+ —— 使**最后一个** [...] 成为画质段。
STATUS_CAPTURE_GROUPS: Final[dict[str, str]] = {
    "recording_live": r"(?P<recording_live>.+)",
    "qa": r"(?P<qa>[^\]]+)",
    "record_name": r"(?P<record_name>.+?)",
    "record_quality_zh": r"(?P<record_quality_zh>.+?)",
    "record_quality": r"(?P<record_quality>.+?)",
    "actual_quality_zh": r"(?P<actual_quality_zh>.+?)",
    "actual_quality_code": r"(?P<actual_quality_code>.+?)",
}

# 哨兵：非可打印控制字符包裹的占位符名。译文里不可能出现同形态串，可安全当切分锚点。
STATUS_SENTINEL: Final[str] = "\x00"
STATUS_PLACEHOLDER_RE: Final[re.Pattern[str]] = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")
STATUS_SENTINEL_SPLIT_RE: Final[re.Pattern[str]] = re.compile("\x00([A-Za-z_][A-Za-z0-9_]*)\x00")


# 把模板变成「字面段 + 哨兵包裹的占位符名」形态，供后续切段。
# translated=True 走 tr()（先查表、后插值）：为什么不能裸 tr(template)——tr() 不喂实参时
# str.format 因缺键抛 KeyError、被 MI-23 的兜底吃掉，返回的是**未翻译**的原文模板。
# translated=False 取原文模板形态：子进程在「目录缺件 / print 补丁未生效」时输出的就是原文。
def _sentinel_text(template: str, *, translated: bool) -> str:
    if not translated:
        return STATUS_PLACEHOLDER_RE.sub(lambda m: f"{STATUS_SENTINEL}{m.group(1)}{STATUS_SENTINEL}", template)
    names = {m.group(1) for m in STATUS_PLACEHOLDER_RE.finditer(template)}
    if not names:
        return i18n_module.tr(template)
    return i18n_module.tr(template, **{name: f"{STATUS_SENTINEL}{name}{STATUS_SENTINEL}" for name in names})


# 按哨兵切成 (是否占位符, 段内容) 序列（re.split 带一个捕获组 → 奇数位即占位符名）。
def _split_sentinels(text: str) -> list[tuple[bool, str]]:
    parts: list[tuple[bool, str]] = []
    for index, chunk in enumerate(STATUS_SENTINEL_SPLIT_RE.split(text)):
        if index % 2 == 0:
            if chunk:
                parts.append((False, chunk))
        else:
            parts.append((True, chunk))
    return parts


# 切段 → 带命名捕获组的正则。字面段一律 re.escape：译文里的 "." "(" "：" 都是普通字符，
# 不是正则元字符，转义后译者改标点/改空格都不会让匹配漂移（AGENTS「关键约定 #13」）。
# 返回 None = required 里的占位符在该形态下取不到（正则必然永远匹配不上，显式判不可用）。
def _compile_parts(parts: list[tuple[bool, str]], required: tuple[str, ...]) -> re.Pattern[str] | None:
    body: list[str] = []
    captured: set[str] = set()
    for index, (is_placeholder, segment) in enumerate(parts):
        if not is_placeholder:
            literal = segment[1:] if index == 0 and segment.startswith("\r") else segment
            body.append(re.escape(literal))
            continue
        fragment = STATUS_CAPTURE_GROUPS.get(segment)
        if fragment is None:
            # 取值段（已录时长 / 循环间隔秒数）：GUI 不解析它的值，只要求「那里有内容」。
            body.append(".*" if index == len(parts) - 1 else ".*?")
            continue
        if segment in captured:
            # 同名的第二个占位符：re 不允许重名捕获组，降级为不捕获
            body.append(fragment.replace(f"(?P<{segment}>", "(?:", 1))
            continue
        body.append(fragment)
        captured.add(segment)
    if any(name not in captured for name in required):
        return None
    return re.compile("".join(body))


# 单条模板 → 可用正则 + 降级说明。先按 tr() 结果组装；组装不出（译稿删了必需占位符）时
# 记一条 problems 并回退到原文模板形态。
def _pattern_from_template(template: str, required: tuple[str, ...]) -> tuple[re.Pattern[str] | None, tuple[str, ...]]:
    pattern = _compile_parts(_split_sentinels(_sentinel_text(template, translated=True)), required)
    if pattern is not None:
        return pattern, ()
    detail = i18n_module.tr("状态行译文取不到必需占位符，已回退原文模板匹配（请核对 i18n 目录该条译文）")
    fallback = _compile_parts(_split_sentinels(_sentinel_text(template, translated=False)), required)
    if fallback is None:
        return None, (i18n_module.tr("{detail}；原文模板同样不可用", detail=detail),)
    return fallback, (detail,)


# 空态行的子串匹配表：命中任一即清除全部录制标记。取「第一个占位符之前」的字面段作子串，
# 尾部实参不参与匹配（免得 delay_default 一变就失配）；tr() 结果与原文两种形态**都收**。
def _idle_needles() -> tuple[str, ...]:
    needles: list[str] = []
    for template in (STATUS_TPL_IDLE, STATUS_TPL_EMPTY):
        for translated in (True, False):
            text = _sentinel_text(template, translated=translated)
            needle = text.split(STATUS_SENTINEL, 1)[0].lstrip("\r").strip()
            if needle and needle not in needles:
                needles.append(needle)
    return tuple(needles)


@dataclass(frozen=True)
class StatusPatterns:
    # 录制中行 / 画质降级行 / 空态子串。None = 该语言下这条模板拼不出可用正则（目录被写坏），
    # 该类行不解析，并由 problems 留痕。
    recording: re.Pattern[str] | None
    downgrade: re.Pattern[str] | None
    idle_needles: tuple[str, ...]
    problems: tuple[str, ...]


def _build_status_patterns() -> StatusPatterns:
    recording, recording_problems = _pattern_from_template(STATUS_TPL_RECORDING, STATUS_REQUIRED_RECORDING)
    downgrade, downgrade_problems = _pattern_from_template(STATUS_TPL_DOWNGRADE, STATUS_REQUIRED_DOWNGRADE)
    return StatusPatterns(
        recording=recording,
        downgrade=downgrade,
        idle_needles=_idle_needles(),
        problems=recording_problems + downgrade_problems,
    )


# 语言 → 已组装的匹配器。缓存键取 i18n.get_language()（MID-52 起它恒等于**实际装载**的语言码）。
# **不得改成模块级一次编译**：那等价于把简中串钉死，正是 M-14 要消灭的故障形态。
_STATUS_PATTERNS_BY_LANG: dict[str, StatusPatterns] = {}
# 组装期「语言是否被切走」复核的尝试上限，判据见 _status_patterns 的竞态说明。
_STATUS_PATTERNS_STABLE_ATTEMPTS: Final[int] = 3


def status_patterns() -> StatusPatterns:
    # 并发下最坏是同一语言被组装两遍（纯函数 + 原子赋值），不会读到半成品，故不加锁。
    # 但「原子赋值」挡不住**组装过程中**换语言：_build_status_patterns 要连读 6 次 i18n.tr，
    # 而本函数由录制输出线程调用、set_language 由 UI 线程调用，中途切走会组出混语 patterns。
    # 故组装后复验语言码未变才落缓存。
    for _attempt in range(_STATUS_PATTERNS_STABLE_ATTEMPTS):
        lang = i18n_module.get_language()
        cached = _STATUS_PATTERNS_BY_LANG.get(lang)
        if cached is not None:
            return cached
        built = _build_status_patterns()
        if i18n_module.get_language() == lang:
            _STATUS_PATTERNS_BY_LANG[lang] = built
            return built
    return _build_status_patterns()


# ─── Windows 控制台信号与进程清理 ───
#
# 为什么不能用 proc.send_signal(CTRL_BREAK_EVENT)：
#   - 子进程无控制台（CREATE_NO_WINDOW）时，事件永远送达不到；
#   - 子进程共享父控制台（仅 CREATE_NEW_PROCESS_GROUP）时，事件会连同 GUI 进程一起杀死。
# 正确做法：临时挂接到子进程控制台，注册吞掉事件的回调保护自身，再广播 CTRL_BREAK，最后还原。
_ATTACH_PARENT_PROCESS: Final[int] = 0xFFFFFFFF
_GUI_KERNEL32: Any = None


# 统一 kernel32 入口：一律 ctypes.WinDLL + 显式 argtypes/restype（MIN-2250 口径）。
# HWND 必须按指针宽度取 c_void_p——默认 c_int 会截断 64 位句柄。
def get_gui_kernel32() -> Any:
    global _GUI_KERNEL32
    if _GUI_KERNEL32 is not None:
        return _GUI_KERNEL32
    if sys.platform != "win32":
        return None
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.GetConsoleWindow.argtypes = []
    k32.GetConsoleWindow.restype = ctypes.c_void_p
    k32.FreeConsole.argtypes = []
    k32.FreeConsole.restype = ctypes.c_bool
    k32.AttachConsole.argtypes = [ctypes.c_uint]
    k32.AttachConsole.restype = ctypes.c_bool
    k32.SetConsoleCtrlHandler.argtypes = [ctypes.c_void_p, ctypes.c_bool]
    k32.SetConsoleCtrlHandler.restype = ctypes.c_bool
    k32.GenerateConsoleCtrlEvent.argtypes = [ctypes.c_uint, ctypes.c_uint]
    k32.GenerateConsoleCtrlEvent.restype = ctypes.c_bool
    k32.SetConsoleOutputCP.argtypes = [ctypes.c_uint]
    k32.SetConsoleOutputCP.restype = ctypes.c_bool
    k32.SetConsoleCP.argtypes = [ctypes.c_uint]
    k32.SetConsoleCP.restype = ctypes.c_bool
    _GUI_KERNEL32 = k32
    return k32


# 向指定 PID 的子进程发送 CTRL_BREAK 信号（仅 Windows），返回是否成功。
def send_ctrl_break_to_child(pid: int) -> bool:
    if sys.platform != "win32":
        return False
    k32 = get_gui_kernel32()
    if k32 is None:
        return False
    had_console = bool(k32.GetConsoleWindow())
    handler_routine = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_ulong)

    # 控制台 Ctrl 事件回调：返回 True 表示事件已处理，保护 GUI 不被终止。
    def _ignore(_ctrl_type: int) -> bool:
        return True

    cb = handler_routine(_ignore)

    # 把本进程的控制台挂回去，并在挂不回去时**留下告警**：ATTACH_PARENT_PROCESS 只在
    # 「父进程确实持有控制台」时才回得去；旧实现丢了返回值，此后本进程的 print 与 loguru
    # 控制台 sink 全写向无效句柄，用户视角就是「停止一次录制之后 GUI 终端再也看不到日志」。
    def _restore_own_console() -> None:
        if not had_console:
            return
        if k32.AttachConsole(_ATTACH_PARENT_PROCESS):
            return
        _report_console_restore_failure(int(ctypes.get_last_error()))

    def _report_console_restore_failure(last_error: int) -> None:
        # 拆成独立函数：让「读 GetLastError」与「发日志」两步解耦，日志本身抛错
        # （loguru 队列满等）不会污染错误码读取路径。
        try:
            logger.warning(
                i18n_module.tr(
                    "恢复本进程控制台失败（GetLastError={last_error}），此后 GUI 的控制台输出可能不再显示；"
                    "如需要查看控制台日志请重启程序",
                    last_error=last_error,
                )
            )
        except Exception:
            pass

    k32.FreeConsole()
    if not k32.AttachConsole(pid):
        _restore_own_console()
        return False
    try:
        k32.SetConsoleCtrlHandler(cb, True)
        if not k32.GenerateConsoleCtrlEvent(1, 0):  # 1 = CTRL_BREAK_EVENT
            return False
        time.sleep(0.2)  # 给事件分发留出时间
        return True
    finally:
        k32.FreeConsole()
        k32.SetConsoleCtrlHandler(cb, False)
        _restore_own_console()


# 把 taskkill / pkill 的输出解成一行可入日志的提示（MIN-2249）。
# 为什么按码页而不是按 UTF-8：Windows 系统工具输出的是**跟随控制台码页本地化**的消息
# （中文 Windows 上 taskkill 的「信息: 没有运行的任务…」是 GBK 字节），统一按 utf-8 解码会
# 解成一串替换符。关键约束：本函数只负责「把提示带进日志」，
# **清理是否成功的判据一律是 returncode**，解码不参与任何判定路径。
def process_kill_hint(*chunks: bytes | None) -> str:
    raw = b""
    for chunk in chunks:
        if chunk:
            raw = chunk
            break
    if not raw:
        return ""
    encoding = "mbcs" if sys.platform == "win32" else "utf-8"
    try:
        text = raw.decode(encoding, errors="replace")
    except LookupError:
        text = raw.decode("utf-8", errors="replace")
    for line in text.splitlines():
        stripped = line.strip()
        if stripped:
            # 提示本身不含凭据，但走同一道脱敏口径：外部工具的文本不可信
            return mask_credentials(stripped)
    return ""


# ─── 配置文件读写 ───


def read_config_snapshot(file_path: str) -> tuple[str | None, float | None]:
    try:
        mtime = os.path.getmtime(file_path)
    except OSError:
        return None, None
    try:
        with open(file_path, "r", encoding="utf-8-sig") as f:
            return f.read(), mtime
    except OSError:
        return None, mtime


def snapshots_equal(left: str | None, right: str | None) -> bool:
    # None 表示「当时没读到」，与任何已读到的内容都不相等。
    if left is None or right is None:
        return left is None and right is None
    return left == right


def normalize_editor_text(text: str) -> str:
    # Tk 的 get("1.0", END) 与 Qt 的 toPlainText() 都会在末尾多给一个换行，
    # 所以基线必须用同一口径存，否则一行未改的内容会被判成 conflict。
    return text.rstrip("\n")


def config_change_verdict(
    disk_baseline: str | None, disk_now: str | None, editor_text: str, editor_baseline: str
) -> str:
    # 外部变更裁决（MID-55 / MID-2252 的纯判据）：
    #   "unchanged" —— 磁盘仍是打开时那份，直接保存
    #   "reload"    —— 磁盘被改过但编辑器无改动：静默跟随磁盘
    #   "conflict"  —— 磁盘被改过且编辑器有改动：必须交用户裁决
    if snapshots_equal(disk_baseline, disk_now):
        return "unchanged"
    if disk_baseline is None or disk_now is None:
        return "conflict"
    return "reload" if editor_text == editor_baseline else "conflict"


def save_text_to_file(content: str, file_path: str) -> None:
    # 原子写（tmp + os.replace）：直接 "w" 覆盖在写入窗口内是半写状态，录制引擎并发读到截断
    # 内容会被当成有效配置。委托 src.utils.atomic_write_text（全仓唯一加固实现：flush + fsync +
    # 保留目标文件原 mode），避免另起一份实现重蹈 SEV-2211 的权限收紧缺口。
    content = content.rstrip("\n")
    if content and not content.endswith("\n"):
        content += "\n"
    if not atomic_write_text(file_path, content, encoding="utf-8-sig"):
        raise OSError(i18n_module.tr("写入配置文件失败（已保留原文件）: {err}", err=file_path))


def cleanup_process_tree(pid: int | None, log: Any) -> None:
    # 清理录制子进程树及其下的 ffmpeg 残留（跨平台，MIN-2249 口径：判据只看 returncode）。
    # taskkill 找不到 PID 返回 128、pkill 无匹配返回 1 —— 两种「什么都没杀」都不能记成成功，
    # 否则日志里「已清理」与「其实还在录」完全同形。
    #
    # 为什么只按 main.py 的 PID 整树强杀：ffmpeg 的父进程恒是录制子进程，按 GUI 自身 PID
    # 过滤结构性匹配不到（L-40 的旧形态已论证并删除过一次）。
    if pid is None:
        log(i18n_module.tr("未发现需要清理的 ffmpeg 进程"))
        return
    try:
        if sys.platform == "win32":
            proc = subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)], capture_output=True, timeout=5)
            if proc.returncode == 0:
                log(i18n_module.tr("已通过 taskkill 清理 PID {pid} 的进程树（含 ffmpeg）", pid=pid))
                return
            hint = process_kill_hint(proc.stdout, proc.stderr)
            log(
                i18n_module.tr("taskkill 未能清理 PID {pid} 的进程树（返回码 {code}）", pid=pid, code=proc.returncode)
                + (i18n_module.tr("，提示: {hint}", hint=hint) if hint else ""),
                "warn",
            )
        else:
            proc = subprocess.run(["pkill", "-P", str(pid), "-x", "ffmpeg"], capture_output=True, timeout=3)
            if proc.returncode == 0:
                log(i18n_module.tr("已通过 pkill 清理 PID {pid} 下的 ffmpeg 进程", pid=pid))
                return
            hint = process_kill_hint(proc.stdout, proc.stderr)
            log(
                i18n_module.tr("pkill 未能清理 PID {pid} 下的 ffmpeg（返回码 {code}）", pid=pid, code=proc.returncode)
                + (i18n_module.tr("，提示: {hint}", hint=hint) if hint else ""),
                "warn",
            )
    except Exception as e:
        log(i18n_module.tr("清理 ffmpeg 进程时出错: {type_name}: {err}", type_name=type(e).__name__, err=e), "warn")
