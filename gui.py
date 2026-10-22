# -*- encoding: utf-8 -*-
# 直播录制器 GUI（tkinter 版，迁移期保留）：构建主窗口与五个页面（控制台 / 画质监控 /
# 弹幕监控 / URL 配置 / 运行日志），管理录制子进程生命周期、跨线程日志队列与 UI 事件泵、
# 画质降级监控、弹幕监控（tail 边车 JSONL 文件）以及优雅退出清理。
# 产品入口 main() 已转发到 src.gui_qt.app（PySide6 窗口层，含系统托盘）；本模块的 tkinter
# 实现只作回退路径与回归锁宿主，不再持有托盘。
# 对外主要类：LiveRecorderGUI（主界面）、AdvancedSettingsWindow（config.ini 编辑器）、
# Colors / Fonts（主题与字体）。
from __future__ import annotations

# 窗口化运行（pythonw / PyInstaller console=False 冻结 exe）下 sys.stderr 为 None，
# 任何未捕获异常（含模块顶层 import 失败、后台线程异常）都会被静默吞掉，表现为
# 「启动后无窗口、无报错」。这里在一切风险导入之前安装全局异常钩子，把堆栈落盘到
# 临时目录并尽力弹窗，保证可观测。
# _bootstrap_crash_reported：main() 顶层异常先经 _bootstrap_error_sink 落盘弹窗再 re-raise，
# 随后会再次触发本钩子；不去重会弹两个错误框、日志写两份堆栈
# （前者以 "w" 覆盖写，本钩子以 "a" 追加写，最终文件含双份）。
_bootstrap_crash_reported = False
# 画质监控「数据未变则跳过重建」比较时剔除的字段：last_seen 每轮心跳刷新，recording
# 只用于筛选、alert_at 只用于判定降级告警是否已被后续轮次取代（渲染用给人看的
# alert_time 字符串）。它们参与整表比较会让「未变化」恒不成立，录制期间每轮
# destroy+重建整表 → 闪烁 + 点击落空（鼠标按下与抬起之间行已被销毁）。
_QUALITY_NON_DISPLAY_FIELDS = frozenset({"last_seen", "recording", "alert_at"})

# 降级告警的失效等待窗口（秒）：告警之后若连续这么久仍在输出录制状态行且没有新告警，
# 视为该房间已按设置档位正常录制，清除降级标记。main.py 房间主循环默认 120s（含 ±5s
# 抖动，错误多时再 +60s），而降级告警每轮录制启动都会重打——仍在降级的房间每周期都会
# 刷新 alert_at。取 2 个周期是为了避开「状态行先于本轮告警行到达」的竞态（宁可晚一个
# 周期清，也不要把仍在降级的房间误判为正常）。
_QUALITY_ALERT_TTL_SECONDS = 240.0

# 「彻底退出」复用在途「停止录制」线程时的等待预算（秒）：25s = 停止链自身上限
# （proc.wait(15) + taskkill(5) + proc.wait(5)）。超时后退出路径仍会在 _stop_child_once
# 的锁上排队，且拿锁后先复核 proc.poll()，最坏只是多等一轮，不会二次附着控制台。
_STOP_REUSE_JOIN_SECONDS = 25.0


# 判定某房间的降级告警是否已被后续正常轮次取代（纯判据，独立成函数供用例直接驱动）。
# 不能只看「录制行里的画质 == 设置档」：src/recorder_status.py 打印
# "{name}[{qa}] 正在录制中" 取的是 main.recording_time_list[name][1]（设置档位），
# 实际档在 [2] 且不进这行日志，故该画质恒等于设置档。可靠信号是时间先后：告警每轮
# 录制启动都会重打，「距最近一次告警已过完整周期仍有录制行」= 新一轮按设置档正常开播
# 且未再报警；新告警会把 alert_at 推后、TTL 重新计时，迟到的旧告警不会清掉新告警。
def _quality_alert_expired(info: dict[str, str | bool | float], now: float) -> bool:
    if not info.get("downgraded"):
        return False
    try:
        alert_at = float(info.get("alert_at") or 0.0)
    except TypeError, ValueError:
        # 条目被外部/旧版本数据污染（alert_at 非数值）时按「无告警时刻」处理：立即允许
        # 复位，否则该房间会永久钉在降级态。
        return True
    return (now - alert_at) >= _QUALITY_ALERT_TTL_SECONDS


# 启动期 / 运行期标记：主窗口构建完成前异常必须弹窗（否则用户看不到任何反馈）；主窗口
# 就绪后 Tk 回调里的异常多是周期性的（如弹幕时间戳字段的 float 转换遇 null，每轮刷新都
# 触发一次），逐个弹窗会在几秒内淹没界面，故运行期只落盘 + 写应用内日志。
_gui_main_window_ready = False


def _mark_gui_ready() -> None:
    # 由 LiveRecorderGUI 主窗口构建完成后调用，把 crash sink 切到运行期模式
    global _gui_main_window_ready
    _gui_main_window_ready = True


def _install_crash_sink() -> None:
    import os
    import sys
    import tempfile
    import threading
    import traceback
    from types import TracebackType

    _LOG = os.path.join(tempfile.gettempdir(), "douyin_recorder_gui_error.log")

    def _dump(
        exc_type: type[BaseException],
        exc_value: BaseException,
        exc_tb: TracebackType | None,
    ) -> None:
        global _bootstrap_crash_reported
        if _bootstrap_crash_reported:
            # _bootstrap_error_sink 已处理同一异常（落盘+弹窗），跳过避免双份上报
            return
        try:
            text = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        except Exception:
            text = repr(exc_value)
        try:
            with open(_LOG, "a", encoding="utf-8") as _f:
                _f.write(text)
        except Exception:
            pass
        # 运行期只落盘不弹窗：周期性 Tk 回调异常会刷出无数错误框。此处位于一切业务导入
        # 之前，不可引用 src 包的 logger（会破坏「GUI 入口标记必须先于 src 导入」的静态
        # 断言，src 缺失时还会二次抛错），应用内日志由日志哨兵/状态栏在下一轮自然呈现。
        if _gui_main_window_ready:
            return
        # 启动期尽力弹窗（三方 UI 库缺失时，标准库 tkinter 通常仍可用）
        try:
            import tkinter as _tk
            import tkinter.messagebox as _messagebox

            _root = _tk.Tk()
            _root.withdraw()
            # 先判 i18n_module 是否已导入：本钩子的设计场景正是导入期崩溃，此时直接引用
            # 全局名会抛 NameError 被外层 except 吞掉，弹窗静默失效；未导入时回退字面量标题。
            _i18n_tr = getattr(globals().get("i18n_module"), "tr", None)
            _title = cast(str, _i18n_tr("GUI 启动失败")) if callable(_i18n_tr) else "GUI 启动失败"
            _messagebox.showerror(_title, text[-3000:])
        except Exception:
            pass

    sys.excepthook = _dump  # type: ignore[assignment]
    if hasattr(threading, "excepthook"):
        _orig_thread_hook = threading.excepthook

        def _thread_dump(args: threading.ExceptHookArgs) -> None:
            if args.exc_value is None:
                return
            _dump(args.exc_type, args.exc_value, args.exc_traceback)
            try:
                _orig_thread_hook(args)  # type: ignore[call-arg]
            except Exception:
                pass

        threading.excepthook = _thread_dump  # type: ignore[assignment]


# 仅作为入口脚本（pythonw gui.py / GUI 冻结 exe）时才劫持进程级钩子；安排在重活导入
# 之前，使 tkinter/ttk、src 包及 PySide6 缺失这类导入期崩溃也纳入兜底。被当作模块导入时
# 不安装：那时钩子属于宿主进程，而 pytest 收集会 import 本模块——接管后会把会话收尾的
# 未捕获异常弹成「GUI 启动失败」并吞掉原始堆栈（2026-09-23 事故，见 DIAGNOSIS 文档）。
if __name__ == "__main__":
    _install_crash_sink()


import configparser
import ctypes
import io
import json
import os
import queue
import re
import signal
import subprocess
import sys
import threading
import time
import tkinter as tk
import traceback
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from tkinter import filedialog
from tkinter import font as tkfont
from tkinter import messagebox, ttk
from typing import Any, Literal, cast, final

# GUI 父进程标记：必须先于任何 src 导入设置——src.logger 在导入期读取该标记决定文件 sink
# 归属（GUI 进程只写 logs/gui.log，不持有 streamget/PlayURL 句柄，避免与录制子进程的轮转
# 改名互锁致日志全量丢失，详见 src/logger.py::GUI_PARENT_ENV）。
os.environ["DLR_GUI_PARENT"] = "1"

# i18n：侧边栏语言菜单即时热切换（set_language 重载翻译目录，后续 print/日志即时换语言），
# 界面静态标签经 ui_i18n.T 登记、由 retranslate_all 回填；config 写回经
# web_config.update_config_line（与 Web 面板同款行级更新，保留注释）。
import i18n as i18n_module
from src.config_bool import parse_config_bool
from src.logger import child_process_env, logger
from src.ui_fonts import (
    SUPPORTED_FONT_SUFFIXES,
    available_preset_families,
    family_resolves,
    install_font_file,
    is_family_available,
    load_font_file_preference,
    load_font_preference,
    register_private_font,
    save_font_preference,
)
from src.ui_i18n import T, Translatable, apply_title, retranslate_all
from src.ui_kit import (
    NAV_ACTIVE_STYLE,
    NAV_STYLE,
    TAG_NORMAL,
    Button,
    DataTable,
    EditorText,
    Frame,
    Label,
    Menu,
    blend,
    font_style,
    restyle_fonts,
    scale_in_window,
    set_scale_percent,
    slide_in,
    terminal_text,
)
from src.ui_motion import (
    DIALOG_START_SCALE,
    FOLLOW_SYSTEM_MOTION_ID,
    MOTION_IDS,
    PAGE_SLIDE_PX,
    ROW_HIGHLIGHT_FRAMES,
    ROW_HIGHLIGHT_MS,
    MotionController,
    detect_system_animations,
    effective_motion,
    load_motion_preference,
    save_motion_preference,
)
from src.ui_scale import (
    AUTO_SCALE_ID,
    FONT_FAMILY,
    MONO_FAMILY,
    SCALE_PRESETS,
    SCREEN_FILL_CEILING,
    TYPE_SCALE,
    ScaleProfile,
    auto_scale_for_screen,
    load_scale_preference,
    save_scale_preference,
)
from src.ui_theme import (
    DEFAULT_THEME,
    GUI_SECTION,
    THEME_IDS,
    THEME_KEY,
    THEMES,
    ThemeManager,
    detect_system_appearance,
    load_theme_preference,
    save_theme_preference,
)
from src.utils import atomic_write_text, mask_credentials
from src.web_config import (
    parse_url_config,
    read_quality_options,
    update_config_line,
    update_or_append_config_line,
    update_room_quality,
)

# tkinter 的 pack/grid/configure/after 等副作用方法在 typeshed 中被类型化为返回
# 非 None（如配置字典、网格信息或计时器 id），实际调用仅为产生副作用。本文件统一
# 关闭 reportUnusedCallResult，避免对大量纯副作用调用误报「结果未使用」。
# pyright: reportUnusedCallResult=none
# LiveRecorderGUI 的实例组件在 _build_* 中初始化，而 _build_* 均由 __init__ 经 _setup_ui()
# 调用；类型检查器无法跨方法证明，故关闭该告警（类体已做非可选类型声明，确保 .configure
# 等方法可类型检查）。
# pyright: reportUninitializedInstanceVariable=none


# kernel32 句柄缓存为模块级单例（对齐 web.py 的 _get_kernel32 惯例）：避免重复 WinDLL
# 构造，保证 argtypes/restype 全进程只声明一遍（_fix_encoding / _send_ctrl_break_to_child
# 共用同一份声明）；加载失败保持 None，下次调用自动重试。
_GUI_KERNEL32: ctypes.CDLL | None = None

# AttachConsole 的保留值：挂到「本进程的父进程」所持有的控制台。
_ATTACH_PARENT_PROCESS = 0xFFFFFFFF


# 加载并声明 kernel32。返回 None = 本进程拿不到可用的 kernel32（非 Windows、或被策略
# 限制），调用方必须显式判空，不得再退回 windll 形态。
def _get_gui_kernel32() -> ctypes.CDLL | None:
    global _GUI_KERNEL32
    if _GUI_KERNEL32 is not None:
        return _GUI_KERNEL32
    # WinDLL 只存在于 Windows typeshed：必须按 sys.platform 早返回，否则
    # mypy --platform linux 报 attr-defined（AGENTS「平台专属符号门控」条）。
    if sys.platform != "win32":
        return None
    try:
        # use_last_error=True：错误码存进线程本地，须用 ctypes.get_last_error() 读，
        # 这是 AttachConsole 失败时能报出真实原因（ERROR_ACCESS_DENIED=5 /
        # ERROR_INVALID_STATE=1168 等）的前提。
        dll = ctypes.WinDLL("kernel32", use_last_error=True)
        # GetConsoleWindow 返回 HWND（64 位指针），不声明 restype 会按默认 c_int 截断。
        dll.GetConsoleWindow.argtypes = []
        dll.GetConsoleWindow.restype = ctypes.c_void_p
        dll.FreeConsole.argtypes = []
        dll.FreeConsole.restype = ctypes.c_int
        dll.AttachConsole.argtypes = [ctypes.c_uint]
        dll.AttachConsole.restype = ctypes.c_int
        dll.SetConsoleCtrlHandler.argtypes = [ctypes.c_void_p, ctypes.c_int]
        dll.SetConsoleCtrlHandler.restype = ctypes.c_int
        dll.GenerateConsoleCtrlEvent.argtypes = [ctypes.c_uint, ctypes.c_uint]
        dll.GenerateConsoleCtrlEvent.restype = ctypes.c_int
        dll.SetConsoleOutputCP.argtypes = [ctypes.c_uint]
        dll.SetConsoleOutputCP.restype = ctypes.c_int
        dll.SetConsoleCP.argtypes = [ctypes.c_uint]
        dll.SetConsoleCP.restype = ctypes.c_int
        # 退出链在整树强杀前要读出「这个 PID 现在是谁」：OpenProcess 只取
        # PROCESS_QUERY_LIMITED_INFORMATION，不请求写/终止权限，别的用户的进程同样拿不到，
        # 那种情形由调用方按「无法判定」退回原形态。
        dll.OpenProcess.argtypes = [ctypes.c_uint, ctypes.c_int, ctypes.c_uint]
        dll.OpenProcess.restype = ctypes.c_void_p
        dll.QueryFullProcessImageNameW.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_void_p, ctypes.c_void_p]
        dll.QueryFullProcessImageNameW.restype = ctypes.c_int
        dll.CloseHandle.argtypes = [ctypes.c_void_p]
        dll.CloseHandle.restype = ctypes.c_int
        # PID 复用的第二道判据——创建时间：映像名挡不住「另一个同名进程接手」（源码态下
        # 录制核心就叫 python.exe）。GetProcessTimes 同样只需 QUERY_LIMITED_INFORMATION。
        dll.GetProcessTimes.argtypes = [
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_void_p,
        ]
        dll.GetProcessTimes.restype = ctypes.c_int
        _GUI_KERNEL32 = dll
        return dll
    except Exception:
        return None


# OpenProcess 的权限位：只查进程映像路径与基本退出信息（Vista+）。
_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
# QueryFullProcessImageNameW 的缓冲区字符数：路径可超 MAX_PATH，留足余量，
# 免得截断后的基名与真实基名不一致反而判成「PID 已被复用」。
_PID_IMAGE_NAME_BUFFER_CHARS = 4096


# 读出指定 PID 当前的映像基名（小写）。取不到一律返回空串，由调用方按「无法判定」处理：
# 非 Windows / kernel32 不可用时本判据不存在；OpenProcess 失败（进程已不存在，实测
# last_error=87，或权限不足）时本来就没有可误杀的活对象，继续交给 taskkill 返回 128 并
# 如实记「未能清理」。真正要拦的只有「映像名确实读到、且不是我们启动的那个程序」——
# 判据失效即放行，是为了保证本兜底不会因判据本身而失去清理能力。
def _win_pid_image_name(pid: int) -> str:
    if sys.platform != "win32":
        return ""
    k32 = _get_gui_kernel32()
    if k32 is None:
        return ""
    handle = None
    try:
        handle = k32.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION, 0, pid)
        if not handle:
            return ""
        buffer = ctypes.create_unicode_buffer(_PID_IMAGE_NAME_BUFFER_CHARS)
        size = ctypes.c_uint(len(buffer))
        if not k32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
            return ""
        return os.path.basename(str(buffer.value)).lower()
    except Exception:
        return ""
    finally:
        # 句柄必须关掉：该权限位不持有进程对象，但泄漏会让 GUI 进程句柄数随退出次数增长。
        if handle:
            try:
                _ = k32.CloseHandle(handle)
            except Exception:
                pass


# 判定「已捕获的 PID 是否已被别的映像接手」：确证复用时返回 (当前映像名, 期望映像名)，
# 否则返回 None（按原有无条件强杀形态继续）。期望映像名缺席时不判定：本判据只为收窄
# 「子进程已退出 → PID 进入复用池 → taskkill /T 打到接手者」这段窗口，从未启动过录制
# 核心（或测试桩实例不跑 __init__）本就没有该窗口。
# [2026-10-21 M-72 补充] 本函数的返回值契约不变（读不到映像名仍回 None），因为「取不到判据」
# 的后果已由调用点的下一格 _reused_pid_same_image 承担：映像名与创建时间同源于同一次
# OpenProcess，两者都读不出来时那一格现在判「已复用」→ 不收 taskkill；映像名读不出而创建时间
# 读得出时，创建时间是更强的同一性证据，比对结论照常生效。源码态下 _child_image_name 恒为
# python.exe，映像名比对对任何别的 python 进程都判不出复用，因此这一格的收窄真正落在创建时间上。
def _reused_pid_image_pair(recorded_image: str, pid: int) -> tuple[str, str] | None:
    expected = recorded_image.strip().lower()
    if not expected:
        return None
    current = _win_pid_image_name(pid)
    if not current or current == expected:
        return None
    return current, expected


# 读出指定 PID 的创建时间（FILETIME 的 100ns 计数，不透明比较值）。取不到返回 None，
# 与 _win_pid_image_name 的「无法判定即放行」同口径：本判据只用于收窄误杀窗口。
# [2026-10-21 M-72 改判] 上面这句的「放行」只对映像名判据成立；本函数的 None 现在由
# _reused_pid_same_image 当作「无法证明还是那个进程」→ 不收 taskkill（宁可漏清不可误杀）。
def _win_pid_creation_stamp(pid: int) -> int | None:
    if sys.platform != "win32":
        return None
    k32 = _get_gui_kernel32()
    if k32 is None:
        return None
    handle = None
    try:
        handle = k32.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION, 0, pid)
        if not handle:
            return None
        created = ctypes.c_uint64(0)
        exited = ctypes.c_uint64(0)
        kernel = ctypes.c_uint64(0)
        user = ctypes.c_uint64(0)
        ok = k32.GetProcessTimes(
            handle,
            ctypes.byref(created),
            ctypes.byref(exited),
            ctypes.byref(kernel),
            ctypes.byref(user),
        )
        if not ok:
            return None
        return int(created.value)
    except Exception:
        return None
    finally:
        if handle:
            try:
                _ = k32.CloseHandle(handle)
            except Exception:
                pass


# 判定「已捕获的 PID 是否已被同名进程接手」：映像名相同但创建时间与登记值不同 → 确证复用。
# 期望值为空/读不到（非 Windows、桩实例、权限不足）时一律不判定，理由同上。
# [2026-10-21 M-72 改判] 「登记值在、当前值读不到」这一支已从放行翻成收手：
# 源码运行态下 _child_image_name 恒为 python.exe（record_cmd[0] 就是解释器本体），
# 映像名判据在该形态上结构性失效，创建时间是唯一能把「还是那个进程」与「号码已被另一个
# 同名进程接管」分开的证据；证据读不出来时继续 taskkill /F /T，打的就是别人那一棵子树。
# 本兜底的政策取向是宁可漏清不可误杀——漏清最多留一只孤儿 ffmpeg，误杀拿走的是无关进程。
# 「期望值本身缺席」（recorded_stamp is None）仍不判定：那代表从未登记过基线（非 Windows /
# 桩实例不跑 __init__ / 启动那次读取也失败），PID 复用窗口本不存在，收窄它只会凭空失去清理能力。
def _reused_pid_same_image(recorded_stamp: int | None, pid: int) -> bool:
    if recorded_stamp is None:
        return False
    current = _win_pid_creation_stamp(pid)
    if current is None:
        return True
    return current != recorded_stamp


# 强制标准流以 UTF-8 输出（窗口化 exe 的 stdout/stderr 可能为 None，已做保护）。
# 保证本进程自身及被它启动/读取的子进程日志在中文 Windows 下不乱码。
def _fix_encoding() -> None:
    _streams: list[io.TextIOWrapper | None] = [
        cast("io.TextIOWrapper | None", getattr(sys, "stdout", None)),
        cast("io.TextIOWrapper | None", getattr(sys, "stderr", None)),
    ]
    if sys.platform == "win32":
        for _s in _streams:
            if _s is not None and hasattr(_s, "reconfigure"):
                try:
                    _s.reconfigure(encoding="utf-8", errors="replace")
                except Exception:
                    pass
        try:
            # 统一走 _get_gui_kernel32() 的单点声明（AGENTS 要求新代码用 ctypes.WinDLL，
            # 且 windll 形态下这两个调用没有 argtypes/restype 声明）。
            _k32 = _get_gui_kernel32()
            if _k32 is not None:
                _ = _k32.SetConsoleOutputCP(65001)
                _ = _k32.SetConsoleCP(65001)
        except Exception:
            pass
    else:
        for _s in _streams:
            if _s is not None and hasattr(_s, "reconfigure"):
                try:
                    _s.reconfigure(encoding="utf-8", errors="replace")
                except Exception:
                    pass


_fix_encoding()

# ─── 色彩系统（浅色 / 深色双主题） ──────────────────


# 主题色值常量集合（浅色 / 深色双主题统一色板）。
@final
class Colors:
    # 品牌主色：与 src/ui_theme.THEMES 的 primary/primary_hover 同值同源——两处同为品牌色
    # 落点，改一处必须同改另一处（设计语言见 docs/gui-redesign）。
    PRIMARY = "#B5573A"
    PRIMARY_HOVER = "#9C4A2C"
    PRIMARY_SOFT_LIGHT = "#F5E9E4"
    PRIMARY_SOFT_DARK = "#3A2B25"
    # 语义色：SUCCESS 与 ui_theme 的 success token 同批统一为 #15803D——ttk 变体按钮的
    # 白字标签要达正文 AA 4.5（白压 #16A34A 实测 3.30），状态点/录制按钮/托盘图标同绿。
    SUCCESS = "#15803D"
    SUCCESS_HOVER = "#15803D"
    DANGER = "#DC2626"
    DANGER_HOVER = "#B91C1C"
    WARNING = "#D97706"
    # 中性色（深色模式自动映射）：与 ui_theme 的 surface/surface_alt/text/text_muted
    # 同批换色；本组是品牌基调声明，控件实际着色走 ui_theme 槽位。
    BG_LIGHT = "#F7F7F5"
    BG_DARK = "#1B1B19"
    CARD_LIGHT = "#FFFFFF"
    CARD_DARK = "#262624"
    SIDEBAR_LIGHT = "#F0EFEC"
    SIDEBAR_DARK = "#171716"
    BORDER_LIGHT = "#E5E2DC"
    BORDER_DARK = "#33322F"
    TEXT_LIGHT = "#1A1A1A"
    TEXT_DARK = "#ECECEA"
    MUTED_LIGHT = "#5C5C5C"
    MUTED_DARK = "#A3A3A0"
    # 日志终端（两种主题下均保持深色终端风格）
    TERMINAL_BG = "#0D1117"
    TERMINAL_FG = "#7DA7FF"
    TERMINAL_ERROR = "#F85149"
    TERMINAL_WARN = "#D29922"
    TERMINAL_SELECT = "#1F3A5F"


# ─── 字体系统（语义档位 + 全局缩放） ──────────────────────────────────
#
# 档位定义收敛到 src/ui_scale.TYPE_SCALE（唯一事实源），本类只做缓存与分发。
#   · 换缩放时**不重建控件树**：tkfont.Font 是共享对象，已创建控件持有的引用会随
#     configure(size=) 一起变。重建控件树会清空日志内容、未保存编辑与两张监控表。
#   · 字号一律**负数点值**（-N pt）：Tk 的负值 = 点，随 `tk scaling` 跨 DPI 自动缩放；
#     正数是屏幕像素、不缩放，高 DPI 屏上整窗偏小。


@final
class Fonts:
    # 常用字体配置（惰性创建 + 跨控件共享；换档时原地改 size，见 rescale_all）
    _cache: dict[str, tkfont.Font] = {}
    # 当前尺寸档位。换档时由 rescale_all() 写回，get() 读它算字号。
    _profile: ScaleProfile = ScaleProfile(100)
    # 当前比例字体的族名（自选字体功能的唯一落点）。空 = 未显式选择，用 FONT_FAMILY。
    # 作为类字段：所有构造点从同一处取值，分散传参会立刻出现「有的控件换了、有的没换」。
    _family: str = ""

    @classmethod
    def bind_profile(cls, profile: ScaleProfile) -> None:
        # 绑定尺寸档位。构造期（建第一个字体之前）调用；运行中换档走 rescale_all。
        cls._profile = profile

    @classmethod
    def bind_family(cls, family: str) -> None:
        # 绑定字体族（构造期调用，必须在任何字体被创建之前——已缓存的对象改用
        # set_family 走原地 configure）。
        cls._family = (family or "").strip()

    # 热切换字体族：对**已缓存**的比例字体对象原地 configure(family=)。Tk 字体是具名
    # 共享资源，改一次定义所有引用者立即重排重绘；重建控件树会清空日志内容、未保存编辑
    # 与两张监控表。等宽链路（mono_*）刻意不动——日志终端与 URL 编辑器靠字符对齐读。
    # 返回实际写了一遍的字体对象数（0 = 没有已实例化的比例字体，无需重排）。
    @classmethod
    def set_family(cls, family: str) -> int:
        normalized = (family or "").strip()
        cls._family = normalized
        touched = 0
        for key, font in cls._cache.items():
            if key.startswith("mono"):
                continue
            try:
                font.configure(family=normalized or FONT_FAMILY)
            except Exception:
                continue
            touched += 1
        return touched

    @classmethod
    def rescale_all(cls, profile: ScaleProfile) -> None:
        # 换档：改 profile 后对**已缓存的全部字体对象**原地 configure(size=)，已创建控件
        # 无需重建（运行态零损失）。未缓存的档位不预建——按需创建，避免启动时把 7 档 ×
        # 8 级字体全实例化。
        cls._profile = profile
        for key, font in cls._cache.items():
            size = cls._resolve_size(key)
            if size is not None:
                font.configure(size=size)

    @classmethod
    def _resolve_size(cls, key: str) -> int | None:
        # 由缓存键反解出目标字号。键有两种形态：
        #   "<token>_<weight>"   → 语义档位，键入 TYPE_SCALE 查表
        #   "px_<weight>_px<N>"  → 显式像素档（品牌/弹窗图标等非正文元素）
        # 解析不出 token 时返回 None（跳过而不是猜——错字号比不改更糟）。
        parts = key.split("_")
        if parts[0] == "px" and len(parts) >= 3 and parts[-1].startswith("px"):
            # 显式像素档：按 3/4 折成点再随缩放走
            return -max(7, round(int(parts[-1][2:]) * 3 / 4 * cls._profile._pt_gain))
        token = parts[0]
        if token not in TYPE_SCALE:
            return None
        # 等宽档必须走 mono_pt()（含 MONO_SCALE_FACTOR=0.9 收敛）：创建路径用的就是它，
        # 换档路径若走通用的 pt("mono") 会丢掉 0.9 系数——启动时 10pt、换一次缩放档后
        # 变 11pt 且回不去。两个入口共用同一个换算才是唯一事实源。
        if token == "mono":
            return cls._profile.mono_pt()
        return cls._profile.pt(token)

    # 为什么不动家族：家族由 bind_family/set_family 统一裁决（见 _family 的注释），
    # 这里对空字符串回落到「已选族或默认族」，保证任何新构造点都自动跟随当前选择。
    @classmethod
    def get(
        cls,
        size: int,
        weight: Literal["normal", "bold"] = "normal",
        family: str = "",
        *,
        token: str = "body",
    ) -> tkfont.Font:
        # 按语义档位取字体（并缓存）。size 形参只服务「显式像素档」（品牌图标、弹窗图标
        # 这类非正文元素），随缩放按 3/4 折成点；正文一律走 small/body/heading 等具名方法。
        key = f"{token}_{weight}_px{size}" if token == "px" else f"{token}_{weight}"
        if key not in cls._cache:
            resolved = cls._resolve_size(key)
            if resolved is None:
                raise KeyError(f"未知字号 token: {token!r}（合法值: {tuple(TYPE_SCALE)}）")
            cls._cache[key] = tkfont.Font(family=family or cls._family or FONT_FAMILY, size=resolved, weight=weight)
        return cls._cache[key]

    # 辅助文字（卡片副标题、列标签、状态说明、提示条、时间戳）
    @classmethod
    def small(cls, bold: bool = False) -> tkfont.Font:
        return cls.get(0, "bold" if bold else "normal", token="caption")

    # 正文（按钮文字、导航项、输入内容、占位文案）
    @classmethod
    def body(cls, bold: bool = False) -> tkfont.Font:
        return cls.get(0, "bold" if bold else "normal", token="body")

    # 表格/列表行文字（比正文轻一档，让同行的数值更跳）
    @classmethod
    def label(cls, bold: bool = False) -> tkfont.Font:
        return cls.get(0, "bold" if bold else "normal", token="label")

    # 统计数值（与 label 成对使用，比 label 重一档）
    @classmethod
    def stat(cls, bold: bool = True) -> tkfont.Font:
        return cls.get(0, "bold" if bold else "normal", token="stat")

    # 小节标题（卡片标题、弹窗标题）
    @classmethod
    def heading(cls, bold: bool = True) -> tkfont.Font:
        return cls.get(0, "bold" if bold else "normal", token="heading")

    # 页面/品牌标题
    @classmethod
    def title(cls) -> tkfont.Font:
        return cls.get(0, "bold", token="title")

    # 大状态文字（控制台的「待 机 / 录制中」）
    @classmethod
    def big_status(cls) -> tkfont.Font:
        return cls.get(0, "bold", token="display")

    # 品牌/弹窗图标（emoji 类非文字元素）：走显式像素档，随缩放同步放大
    @classmethod
    def mark(cls, size: int = 30) -> tkfont.Font:
        return cls.get(size, "normal", token="px")

    # 等宽字体（日志终端、URL 编辑器、config.ini 编辑器）
    @classmethod
    def mono(cls) -> tkfont.Font:
        # 返回 Font 对象而非元组：元组是快照，换缩放后不会跟着变；Font 对象能被
        # rescale_all 原地改字号（tk.Text / ttk.Combobox 的 -font 两者都接受）。
        key = "mono_normal"
        if key not in cls._cache:
            cls._cache[key] = tkfont.Font(family=MONO_FAMILY, size=cls._profile.mono_pt())
        return cls._cache[key]

    # 等宽斜体（丢弃弹幕标记）。同样返回 Font 对象以参与缩放。
    @classmethod
    def mono_italic(cls) -> tkfont.Font:
        key = "mono_italic"
        if key not in cls._cache:
            font = tkfont.Font(family=MONO_FAMILY, size=cls._profile.mono_pt(), slant="italic")
            cls._cache[key] = font
        return cls._cache[key]


# 将 #RRGGBB 十六进制颜色字符串解析为 (R, G, B) 整数元组。
def _hex_to_rgb(color: str) -> tuple[int, int, int]:
    color = color.lstrip("#")
    return (int(color[0:2], 16), int(color[2:4], 16), int(color[4:6], 16))


# 按给定比例混合两种十六进制颜色，用于状态点呼吸动画。
def _mix(color_a: str, color_b: str, ratio: float) -> str:
    ra, ga, ba = _hex_to_rgb(color_a)
    rb, gb, bb = _hex_to_rgb(color_b)
    r = round(ra + (rb - ra) * ratio)
    g = round(ga + (gb - ga) * ratio)
    b = round(ba + (bb - ba) * ratio)
    return f"#{r:02X}{g:02X}{b:02X}"


# 「跟随系统」在界面主题菜单里的哨兵 id（刻意不在 THEME_IDS 内）：_on_theme_change 见它
# 即经 detect_system_appearance() 探测系统明暗落主题，并清空 [GUI] gui_theme 显式偏好
# （写空值，load_theme_preference 对空值按「未设置」处理 → 下次启动继续跟随系统）。
_FOLLOW_SYSTEM_ID = "_follow_system_"

# 主题 id → i18n msgid（菜单显示名）。msgid 用简中原文（本仓 msgid 惯例），四语目录同批维护。
_THEME_LABELS: dict[str, str] = {"light": "浅色", "dark": "深色", "high_contrast": "高对比度"}

# 动效等级 → i18n msgid。id 与 src/ui_motion.MOTION_IDS 一一对应。
_MOTION_LABELS: dict[str, str] = {"off": "关闭", "subtle": "轻微", "full": "完整"}


def _compute_wraplength(width_device_px: float, margin: int = 8) -> int:
    # 由标签窗口的设备像素宽折算 wraplength。ttk 的 wraplength 是原始设备像素、不随
    # tk scaling 缩放，可直接用；120 设备像素是下限——极窄容器里宁可逐字折行也不得
    # 让 wraplength 掉到 0（0 = 不折行 = 回到两侧裁切的老路）。
    return max(120, int(width_device_px - margin))


def _wrap_should_apply(current: int, new: int) -> bool:
    # 迟滞判据（纯函数，供无头测试）：新值与已应用值差异显著才写。阈值取 max(12, 2%)：
    # 滚动条出现/消失让容器宽 ±~11 逻辑像素，逐次照写会让「折行变高 → 滚动条翻转 →
    # 宽度变化 → 再折行」在阈值边界无限互振。current==0（从未应用）恒写。
    if current == 0:
        return True
    return abs(new - current) > max(12, int(current * 0.02))


def _bind_adaptive_wraplength(label: ttk.Label, margin: int = 8, debounce_ms: int = 120) -> None:
    # 长提示文案自适应换行（防抖 + 迟滞）。label 形参是 ttk.Label 与 CTkLabel 的联合：
    # 后者无存根、只能按命名参数 configure（cnf 字典会被静默忽略，wraplength 恒 0）。
    #
    # 防抖的必要性：窗口拖拽/滚动条出现消失会产生高频 <Configure>，同步追写 wraplength
    # 会让几何失效排进同一 idle 队列；回调里 label 可能已被销毁（占位每轮刷新重建），
    # 故保留 TclError 守卫。
    #
    # 前提：标签以 pack(fill=tk.X) / grid 拉伸布局（窗口宽由布局器分配，与标签自请求
    # 解耦）；绑定时若已有实宽（启动重建场景）同步先应用一次，让首帧即成形。
    state: dict[str, Any] = {"job": None, "last_applied": 0}

    def _run() -> None:
        state["job"] = None
        try:
            wrap = _compute_wraplength(label.winfo_width(), margin)
        except tk.TclError:
            # 标签已销毁（弹幕/画质占位每轮刷新重建，防抖回调可能与销毁竞态）
            return
        if not _wrap_should_apply(state["last_applied"], wrap):
            return
        try:
            label.configure(wraplength=wrap)
        except tk.TclError:
            return
        state["last_applied"] = wrap

    def _adapt(event: tk.Event) -> None:
        # 真防抖：风暴期间每个 Configure 都重置计时器，风暴不安静就**一次都不写**。
        if state["job"] is not None:
            label.after_cancel(state["job"])
        state["job"] = label.after(debounce_ms, _run)

    label.bind("<Configure>", _adapt, add="+")
    if label.winfo_width() > 1:
        _run()


# 高级设置窗口：以文本形式编辑并保存 config/config.ini。


# 读取配置文件的「基线快照」：返回 (文本内容或 None, mtime 或 None)。
# 读失败时尽量保留已拿到的信息，由调用方按「无法判定」处理。
def _read_config_snapshot(file_path: str) -> tuple[str | None, float | None]:
    try:
        mtime = os.path.getmtime(file_path)
    except OSError:
        return None, None
    try:
        with open(file_path, "r", encoding="utf-8-sig") as f:
            return f.read(), mtime
    except OSError:
        return None, mtime


# 两份磁盘快照是否等同（None 表示「当时没读到」，与任何已读到的内容都不相等）。
def _snapshots_equal(left: str | None, right: str | None) -> bool:
    if left is None or right is None:
        return left is None and right is None
    return left == right


# 编辑器文本的归一化口径：Tk 的 get("1.0", END) 总在末尾多给一个换行，与文件原文
# 天然差一个尾换行。基线必须用同一口径存，否则一行未改的编辑器会被判成 conflict。
def _normalize_editor_text(text: str) -> str:
    return text.rstrip("\n")


# 外部变更裁决（纯判据，独立成函数供用例直接驱动）：
#   "unchanged" —— 磁盘仍是打开窗口时那份，直接保存即可
#   "reload"    —— 磁盘被改过但编辑器无未保存改动：静默跟随磁盘
#   "conflict"  —— 磁盘被改过且编辑器有改动：必须由用户裁决，否则整文件写回会
#                  回滚窗口打开期间录制进程写入的内容
# 任一侧读不到内容（基线不可知）时一律按 conflict：宁可多问一句，也不能在不知道
# 磁盘内容的情况下整文件覆盖。
def _config_change_verdict(
    disk_baseline: str | None, disk_now: str | None, editor_text: str, editor_baseline: str
) -> str:
    if _snapshots_equal(disk_baseline, disk_now):
        return "unchanged"
    if disk_baseline is None or disk_now is None:
        return "conflict"
    return "reload" if editor_text == editor_baseline else "conflict"


# M-76②（2026-10-21，CODE_REVIEW_2026-10-21）：编辑器内容读不出来（控件已被销毁）时的哨兵值。
# 旧形态回退到 _baseline_content，语义等于「按无改动处理」——于是磁盘侧的外部改动会把用户的
# 未保存编辑静默覆盖（reload 分支）或直接被基线写回。含 NUL 的定长标记不可能出现在配置文件
# 文本里，因此 _config_change_verdict 拿它比对必然判成 conflict，走既有的「先询问再覆盖」分支。
# 消费方必须显式识别该哨兵（见 AdvancedSettingsWindow.save_config），绝不能把它当正文落盘。
_EDITOR_CONTENT_UNREADABLE = "\x00__dlr_editor_content_unreadable__"


@final
class AdvancedSettingsWindow:

    # 磁盘基线核对间隔（毫秒）：与 URL 配置页的 mtime 监听同量级（主窗口刷新为 3~10s），
    # 取 5s 兼顾「窗口长时间打开」场景下的及时提醒与主线程开销。
    _CONFIG_WATCH_INTERVAL_MS = 5000

    # 初始化高级设置窗口（构建 UI、加载配置并延迟安全 grab）。
    # tokens：编辑器（tk.Text）的主题 token 配色由宿主 GUI 传入当前主题；未传
    # （独立/测试场景）按默认主题取值。
    def __init__(
        self,
        parent: tk.Tk,
        config_file: str,
        log_callback: Callable[[str], None] | None = None,
        *,
        tokens: dict[str, str] | None = None,
    ):
        self.config_file = config_file
        self.log_callback = log_callback
        self._tokens = tokens if tokens is not None else dict(THEMES[DEFAULT_THEME])
        # 两份基线：_baseline_content 是编辑器上次加载/保存时的内容，_disk_snapshot 是
        # 上次看到的磁盘内容；保存前比对二者即可识别冲突。
        self._baseline_content = ""
        self._disk_snapshot: str | None = None
        self._disk_mtime: float | None = None
        self._conflict_hint_shown = False
        # 磁盘监听 job 的 after id。root/父窗口的 `after` 注册在解释器上、不随子窗口销毁
        # 而撤销：若不保存 id 并在 destroy 前取消，已排期的 _watch_config_file 仍会跑，
        # 编辑器控件已死 → TclError → 被兜成没有父窗口、文案误导的错误框。
        self._config_watch_job_id: str | None = None

        # tk.Toplevel：底色调随主题 token；标题栏跟随系统明暗（自绘暗色标题栏需
        # dwmapi 额外接入，未纳入本批）。
        self.window = tk.Toplevel(parent, bg=self._tokens["surface"])
        apply_title(self.window, T("高级设置 - config.ini"))
        self.window.geometry("780x560")
        self.window.minsize(560, 400)
        self.window.transient(parent)

        self._setup_ui()
        self._load_config()

        # 延迟 grab，等窗口可见后再 grab_set（Windows 下立即调用会报错）；同样记下 id，
        # 窗口在这 100ms 内被销毁时可在 _close 里取消。
        self._grab_job_id: str | None = self.window.after(100, self._safe_grab)
        # 与 URL 配置页 _watch_url_config 等价的 mtime/内容监听
        self._schedule_config_watch()

    # 安全地为窗口设置模态（容错 grab_set，避免 Windows 报错）。
    def _safe_grab(self) -> None:
        try:
            self.window.grab_set()
        except Exception:
            pass

    # 构建高级设置窗口 UI（标题栏、编辑器、保存 / 取消按钮）。
    def _setup_ui(self) -> None:
        # 顶部标题栏
        header = Frame(self.window, variant="primary", height=52)
        header.pack(fill=tk.X)
        header.pack_propagate(False)
        Label(header, text=T("⚙  高级设置"), font=Fonts.heading(), variant="on_primary").pack(
            side=tk.LEFT, padx=20, pady=12
        )

        # 内容区域
        content = Frame(self.window)
        content.pack(fill=tk.BOTH, expand=True, padx=16, pady=(16, 0))

        Label(content, text=T("📄 配置文件内容 (config/config.ini)"), font=Fonts.body(), anchor=tk.W).pack(
            fill=tk.X, pady=(0, 8)
        )

        # 外部改动提示行：窗口长时间打开时 config.ini 可能已被录制进程写过；有未保存
        # 编辑时不弹窗打断（保存时才裁决），只在这一行给出可见信号。
        self._hint_label = Label(
            content,
            text="",
            font=Fonts.small(),
            variant="danger",
            anchor=tk.W,
        )
        self._hint_label.pack(fill=tk.X, pady=(0, 4))

        # 编辑器（等宽字体；tk.Text + token 配色，主题切换经 restyle 跟随）
        self.config_text = EditorText(content, tokens=self._tokens, font=Fonts.mono())
        self.config_text.pack(fill=tk.BOTH, expand=True)

        # 底部按钮
        btn_frame = Frame(self.window)
        btn_frame.pack(fill=tk.X, padx=16, pady=16)

        Button(
            btn_frame,
            text=T("取消"),
            command=self._close,
            font=Fonts.body(),
            padding=(12, 6),
            variant="ghost",
            width=8,
        ).pack(side=tk.RIGHT, padx=(8, 0))

        Button(
            btn_frame,
            text=T("💾  保存配置"),
            command=self.save_config,
            font=Fonts.body(bold=True),
            padding=(12, 6),
            width=10,
        ).pack(side=tk.RIGHT)

    # 加载 config.ini 内容到编辑器（文件不存在时提示新建），并刷新两份基线快照。
    def _load_config(self) -> None:
        try:
            with open(self.config_file, "r", encoding="utf-8-sig") as f:
                content = f.read()
            self.config_text.delete("1.0", tk.END)
            self.config_text.insert("1.0", content)
            # 基线按编辑器口径归一化（见 _normalize_editor_text），磁盘快照保留原文
            self._baseline_content = _normalize_editor_text(content)
            self._disk_snapshot = content
        except FileNotFoundError:
            self.config_text.delete("1.0", tk.END)
            not_found_hint = i18n_module.tr("# 配置文件不存在，请新建")
            self.config_text.insert("1.0", not_found_hint)
            self._baseline_content = _normalize_editor_text(not_found_hint)
            self._disk_snapshot = None
        except Exception as e:
            # messagebox 标题与正文一并走 tr（f-string 直传是 i18n 提取盲区）
            messagebox.showerror(i18n_module.tr("错误"), i18n_module.tr("加载配置文件失败: {e}", e=e))
            return
        try:
            self._disk_mtime = os.path.getmtime(self.config_file)
        except OSError:
            self._disk_mtime = None
        self._conflict_hint_shown = False
        self._set_hint("")

    # 读取编辑器当前内容（与基线同样去掉末尾多余换行，保证可直接比对）。
    def _editor_content(self) -> str:
        try:
            return _normalize_editor_text(str(self.config_text.get("1.0", tk.END)))
        except Exception:
            # 控件已销毁：返回 _EDITOR_CONTENT_UNREADABLE 哨兵（M-76②，2026-10-21）。
            # [历史注] 原先回退 self._baseline_content，把「读不到」伪装成「没有未保存改动」，
            # 于是外部改动可被静默 reload 覆盖、或按基线写回，用户的编辑无任何提示地消失。
            return _EDITOR_CONTENT_UNREADABLE

    # 设置外部改动提示行。
    def _set_hint(self, text: str) -> None:
        try:
            self._hint_label.configure(text=text)
        except Exception:
            pass

    # 排期下一次磁盘基线核对；窗口已销毁时不再排期（否则 _watch_config_file 会在
    # 失效控件上跑一轮，TclError 被兜成误导的错误弹窗）。
    def _schedule_config_watch(self) -> None:
        try:
            if not self.window.winfo_exists():
                self._config_watch_job_id = None
                return
            self._config_watch_job_id = self.window.after(self._CONFIG_WATCH_INTERVAL_MS, self._watch_config_file)
        except Exception:
            self._config_watch_job_id = None

    # 取消尚未触发的 after job 并销毁窗口。after_cancel 对「已触发 / 已取消 / 窗口已
    # 销毁」的 id 会抛 TclError，故与主窗口各处 after_cancel 一样包裹容错。
    def _close(self) -> None:
        watch_job_id = self._config_watch_job_id
        grab_job_id = self._grab_job_id
        self._config_watch_job_id = None
        self._grab_job_id = None
        for job_id in (watch_job_id, grab_job_id):
            if job_id is None:
                continue
            try:
                self.window.after_cancel(job_id)
            except Exception:
                pass
        self.window.destroy()

    # 周期性核对 config.ini 是否被本窗口之外的进程改写。录制进程会在运行期回写
    # sooplive/flextv/popkontv 凭据、禁用 SSL 校验的平台清单以及缺键；窗口打开期间的
    # 这些改动若不被跟踪，保存时就会被整文件快照回滚。
    def _watch_config_file(self) -> None:
        # 第二道防线（`_close` 之外的销毁路径：标题栏 X、父窗口先销毁等）：在已销毁的
        # 窗口上继续跑会去动 self.config_text 并抛误导性错误框，故先判存活再做事。
        try:
            if not self.window.winfo_exists():
                self._config_watch_job_id = None
                return
        except Exception:
            # 连 winfo_exists 都调不动 = 解释器已不可用，直接终止链路（不再排期）
            self._config_watch_job_id = None
            return
        try:
            disk_now, mtime = _read_config_snapshot(self.config_file)
            if _snapshots_equal(self._disk_snapshot, disk_now):
                self._disk_mtime = mtime
                return
            if (
                _config_change_verdict(self._disk_snapshot, disk_now, self._editor_content(), self._baseline_content)
                == "reload"
            ):
                # 编辑器无未保存改动：静默跟随磁盘，否则用户看不到最新值、保存时还会覆盖它
                self._load_config()
                if self.log_callback:
                    self.log_callback(i18n_module.tr("config.ini 已被外部修改，已重新加载到编辑器"))
            elif not self._conflict_hint_shown:
                self._conflict_hint_shown = True
                self._set_hint(i18n_module.tr("⚠ config.ini 已被外部修改，而你有未保存的编辑；保存时会先询问是否覆盖"))
        finally:
            self._schedule_config_watch()

    # 保存编辑器内容到 config.ini 并提示成功、关闭窗口。
    def save_config(self) -> None:
        try:
            editor_text = self._editor_content()
            # M-76②：读不到正文时必须在这里收手。上面的 conflict 判据靠「哨兵 ≠ 基线」生效，
            # 但磁盘与基线逐字一致时判据回 "unchanged" 并照常落盘——那会把哨兵字符串本身
            # 写进 config.ini（含 NUL 的一行），把配置文件写成解析器读不回的东西。
            if editor_text == _EDITOR_CONTENT_UNREADABLE:
                # 文案复用既有 msgid（本包不改 i18n/ 目录）：结论一致——本次没有写盘、
                # 外部改动也没被覆盖，重新打开窗口即可拿到最新内容。
                self._set_hint(i18n_module.tr("已取消保存：外部改动未被覆盖，可重新打开高级设置加载最新内容"))
                if self.log_callback:
                    self.log_callback(i18n_module.tr("已取消保存：外部改动未被覆盖，可重新打开高级设置加载最新内容"))
                return
            disk_now, _ = _read_config_snapshot(self.config_file)
            # 整文件写回前必须重读磁盘并与打开窗口时的基线比对：GUI 与录制进程是两个
            # 进程，main.file_update_lock / web_config._config_write_lock 只在各自进程内
            # 生效，跨进程只剩「原子替换不会半写」一条保护——丢失更新只能显式检测 +
            # 交用户裁决（与 URL 配置页的脏检查同口径）。
            if _config_change_verdict(
                self._disk_snapshot, disk_now, editor_text, self._baseline_content
            ) == "conflict" and not messagebox.askyesno(
                i18n_module.tr("配置文件已变更"),
                i18n_module.tr(
                    "config.ini 在你打开本窗口之后已被外部修改（录制进程可能刚写入凭据、"
                    "平台清单或补写了缺失键）。\n\n"
                    "点击「是」仍按当前编辑内容保存：外部改动会被覆盖；\n"
                    "点击「否」取消保存，可先复制外部改动或重新加载文件。"
                ),
            ):
                self._set_hint(i18n_module.tr("已取消保存：外部改动未被覆盖，可重新打开高级设置加载最新内容"))
                return
            _save_text_to_file(editor_text, self.config_file)
            self._baseline_content = editor_text
            # 磁盘基线取「写完之后重读的那份」而非编辑器文本：_save_text_to_file 会补
            # 末尾换行，直接用 editor_text 会少一个 \n，监听器下一轮据此判成外部改动
            self._disk_snapshot, self._disk_mtime = _read_config_snapshot(self.config_file)
            self._conflict_hint_shown = False
            # messagebox 正文不经 i18n.tr 就永远查不到目录（scripts/extract_i18n_strings.py
            # 扫不到 messagebox.*，见 AGENTS「i18n 提取器盲区」条），英文用户只拿到中文；
            # 标题与正文一并走 tr。
            messagebox.showinfo(i18n_module.tr("成功"), i18n_module.tr("配置文件已保存！"))
            if self.log_callback:
                self.log_callback(i18n_module.tr("高级设置配置已保存"))
            self._close()
        except Exception as e:
            messagebox.showerror(i18n_module.tr("错误"), i18n_module.tr("保存配置文件失败: {e}", e=e))


# 把纯文本原子写入配置文件（UTF-8-SIG，自动补末尾换行）。
# 这是本文件两条保存路径（URL 配置页 / 高级设置窗口）共用的唯一实现。
def _save_text_to_file(content: str, file_path: str) -> None:
    # 原子写（tmp + os.replace），委托 src.utils.atomic_write_text：半写窗口内录制引擎会
    # 读到截断配置（历史形态：保存瞬间偶尔丢房间且难复现）；该实现带 flush+fsync 且在
    # replace 前保留目标文件原 mode（POSIX 下不把 0600 还原成 umask 权限）。
    # 不用 src.config_io：它模块级 `import main`，会连带触发 FFmpeg 检查、配置读取、备份
    # 线程等副作用。失败语义：False 转成 OSError 上抛，由两处保存按钮弹错误框。
    content = content.rstrip("\n")
    if content and not content.endswith("\n"):
        content += "\n"
    if not atomic_write_text(file_path, content, encoding="utf-8-sig"):
        raise OSError(i18n_module.tr("写入配置文件失败（已保留原文件）: {err}", err=file_path))


# 将文本控件内容保存为文件（UTF-8-SIG，自动补末尾换行）。
def _save_text_widget_to_file(text_widget: tk.Text, file_path: str) -> None:
    # 形参是 tk.Text（EditorText 即 tk.Text），get("1.0", tk.END) 调用面一致。
    _save_text_to_file(str(text_widget.get("1.0", tk.END)), file_path)


# 启动一个外部程序并在后台回收它。
# 不能直接 Popen 了事：POSIX 上子进程退出后会留僵尸，直到解释器退出才由 subprocess 的
# _active 表统一回收——GUI 是常驻进程，反复点「打开目录」会持续堆积。也不能在 UI 线程
# 同步 wait()：xdg-open 在无默认处理程序的桌面环境里能挂很久，会把界面卡死。
# 折中：wait 放进守护线程并给上限——超时只表示外部程序还没退，调用方成败只看 Popen 本身。
_DETACHED_REAP_TIMEOUT_SECONDS = 5.0


def _spawn_detached(argv: list[str]) -> subprocess.Popen[bytes]:
    proc = subprocess.Popen(list(argv), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def _reap() -> None:
        try:
            _ = proc.wait(timeout=_DETACHED_REAP_TIMEOUT_SECONDS)
        except Exception:
            # 超时/已被回收都不影响调用方：本线程的唯一职责就是不让僵尸留在进程表里。
            pass

    threading.Thread(target=_reap, name="gui-spawn-reap", daemon=True).start()
    return proc


# 把 taskkill / pkill 的输出解成一行可入日志的提示。
# 按码页而非 UTF-8 解码：Windows 系统工具的消息跟随控制台码页本地化（中文 Windows 上
# taskkill 的「信息: 没有运行的任务…」是 GBK 字节），统一按 utf-8 会解成一片替换符；
# mbcs 就是当前 ANSI 码页。清理是否成功一律以 returncode 判定，解码不参与任何判定路径，
# 故 errors="replace" + LookupError 兜底后不可能抛错。
def _process_kill_hint(*chunks: bytes | None) -> str:
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
            # 提示本身不含凭据，但走同一道脱敏口径：外部工具的文本不可信，
            # 万一将来换成带 URL 的工具输出也不至于把凭据原样写进 logs/gui.log。
            return mask_credentials(stripped)
    return ""


# 向指定 PID 的子进程发送 CTRL_BREAK 信号（仅 Windows），返回是否成功。
def _send_ctrl_break_to_child(pid: int) -> bool:
    # 不能用 proc.send_signal(CTRL_BREAK_EVENT)：子进程无控制台（CREATE_NO_WINDOW）时
    # 事件送不到；子进程共享父控制台时事件会连同 GUI 一起杀死（实测收到
    # STATUS_CONTROL_C_EXIT）。做法：临时挂到子进程控制台，注册吞掉事件的回调保护自身，
    # 向该控制台广播 CTRL_BREAK，最后还原。子进程须以 CREATE_NEW_CONSOLE |
    # CREATE_NEW_PROCESS_GROUP 启动（后者会屏蔽 CTRL_C，故必须发 CTRL_BREAK）。
    if sys.platform != "win32":
        return False
    # 统一走 _get_gui_kernel32()：AGENTS 要求新代码用 ctypes.WinDLL，且 windll 形态下
    # 这些调用没有 argtypes/restype 声明（HWND 会被按默认 c_int 截断）。
    k32 = _get_gui_kernel32()
    if k32 is None:
        return False
    had_console = bool(k32.GetConsoleWindow())
    handler_routine = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_ulong)

    # 控制台 Ctrl 事件回调：返回 True 表示事件已处理，保护 GUI 不被终止。
    def _ignore(_ctrl_type: int) -> bool:
        return True  # 声明事件已处理，避免 GUI 自身被 CTRL_BREAK 终止

    cb = handler_routine(_ignore)

    # 把本进程的控制台挂回去，挂不回去时留下告警。ATTACH_PARENT_PROCESS 只在父进程确实
    # 持有控制台时才回得去：从 cmd/PowerShell 直接起 GUI 成立；GUI 自己拥有控制台时
    # （start 派生、explorer 双击带控制台的 exe、计划任务）恢复必然失败，此后 print 与
    # loguru 控制台 sink 全部写向无效句柄，表现为「停止一次录制后终端再也看不到日志」。
    # 刻意不退回 AllocConsole：它会凭空弹窗，而 sys.stdout/sys.stderr 仍绑在启动时那份
    # 句柄上，新窗口照样收不到日志；真要恢复必须重绑流，不在本条范围内。
    def _restore_own_console() -> None:
        if not had_console:
            return
        if k32.AttachConsole(_ATTACH_PARENT_PROCESS):
            return
        # use_last_error=True 才会把错误码存进线程本地；必须在下一个 ctypes 调用之前读。
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


# ─── 子进程状态行匹配与外部数据数值容错 ───
#
# 两类工具都只服务 LiveRecorderGUI「解析外部数据」的路径，放在类定义之前便于用例直接驱动
# （tests/test_gui_status_pattern_i18n.py / tests/test_gui_tail_robustness.py 以子进程调用
# 本模块真实实现，不在 pytest 进程 import gui）。
#
# 外部数据数值字段的**唯一**容错口径：None / 空串 / 非数值字符串一律回落 default，
# 合法数值原样取值——对合法输入与直接 float()/int() 逐字一致，只是不再抛
# TypeError/ValueError。触发源真实存在：弹幕边车 logs/danmaku_monitor.jsonl 外部可控，
# 且 tail 首读会回放旧文件末尾 64KB 的历史记录（含历史脏记录）。
def _as_float(value: object, default: float = 0.0) -> float:
    try:
        return float(cast(Any, value))
    except TypeError, ValueError:
        return default


def _as_int(value: object, default: int = 0) -> int:
    # OverflowError 也在列：JSON 允许 Infinity 字面量，float('inf') 过 int() 即抛它，
    # 少这一条会让逐事件防护被一条脏数据打穿。
    try:
        return int(cast(Any, value))
    except TypeError, ValueError, OverflowError:
        return default


# 三条状态行的 msgid：必须与**生产侧逐字相同**，否则 tr() 查不到键、退化为恒等映射，
# 非简中界面下依旧匹配不上。生产侧出处（只读、不得改动）：
#   src/recorder_status.py::display_info → tr("{recording_live}[{qa}] 正在录制中 {have_record_time}")
#   src/recorder_status.py::display_info → tr("\r没有正在录制的直播 循环监测间隔时间：{delay_default}秒")
#   main.py 录制启动处（ffmpeg 分支与强制直下分支共用同一条 msgid）→
#     tr("{record_name} 画质降级：设置 {record_quality_zh}({record_quality}) 实际 {actual_quality_zh}({actual_quality_code})")
_STATUS_TPL_RECORDING = "{recording_live}[{qa}] 正在录制中 {have_record_time}"
_STATUS_TPL_IDLE = "\r没有正在录制的直播 循环监测间隔时间：{delay_default}秒"
_STATUS_TPL_DOWNGRADE = (
    "{record_name} 画质降级：设置 {record_quality_zh}({record_quality})"
    " 实际 {actual_quality_zh}({actual_quality_code})"
)
# 刻意不对称的一条：该串生产侧**未过 tr()**（src/recorder_status.py::display_info 裸写
# print("\r没有正在监测和录制的直播")），是否被翻译取决于 main.py 的
# `builtins.print = translated_print` 补丁与 i18n._should_translate 的调用方路径判定
# （冻结下是否仍成立尚未实测），且四语目录缺件时会退回原文。故 GUI 侧必须同时认
# 「tr() 结果 + 原文」：删掉原文匹配会让冻结/缺目录部署立刻失效，只留原文则会让源码
# 运行 + 英文界面下的空态清除静默失效。
_STATUS_TPL_EMPTY = "\r没有正在监测和录制的直播"

# 各条模板中 GUI **必须取用**的占位符（= 下面正则片段表里登记过的那些）。
# 译文若把它们删掉，拼不出可用正则 → 该类行判为不可解析并留痕，而不是默默匹配不上。
_STATUS_REQUIRED_RECORDING = ("recording_live", "qa")
_STATUS_REQUIRED_DOWNGRADE = (
    "record_name",
    "record_quality_zh",
    "record_quality",
    "actual_quality_zh",
    "actual_quality_code",
)

# 各占位符在**译文**里应展开成的正则片段；未列出的占位符（时长、间隔秒数）按通配处理，
# GUI 不取用其值。按名字映射，译者可自由调整占位符顺序。键名即命名捕获组名。
# 两条语义不得回退：recording_live 贪婪 .+（主播名里的 "[...]" 不能当成画质段边界）、
# qa [^\]]+（使**最后一个** [...] 成为画质段）。
_STATUS_CAPTURE_GROUPS: dict[str, str] = {
    "recording_live": r"(?P<recording_live>.+)",
    "qa": r"(?P<qa>[^\]]+)",
    "record_name": r"(?P<record_name>.+?)",
    "record_quality_zh": r"(?P<record_quality_zh>.+?)",
    "record_quality": r"(?P<record_quality>.+?)",
    "actual_quality_zh": r"(?P<actual_quality_zh>.+?)",
    "actual_quality_code": r"(?P<actual_quality_code>.+?)",
}

# 哨兵：非可打印控制字符包裹的占位符名。译文里不可能出现同形态串，故可安全地当切分锚点用。
_STATUS_SENTINEL = "\x00"
_STATUS_PLACEHOLDER_RE = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")
_STATUS_SENTINEL_SPLIT_RE = re.compile("\x00([A-Za-z_][A-Za-z0-9_]*)\x00")


# 把模板变成「字面段 + \x00占位符名\x00 哨兵」的形态，供后续切段。
# translated=True 走 tr()（先查表、后插值）：不能裸 tr(template)——不喂实参时 str.format
# 因缺键抛 KeyError，被兜底吃掉后返回的是**未翻译**原文，非简中界面永远拿到简中串。
# 给每个占位符喂哨兵即可正常走完「查表 + 插值」并保留占位符位置。只用公开接口，不碰
# i18n._tr（_tr 是 tests/conftest.py 恒等钉定的对象，依赖它会让用例与真实目录分叉）。
# translated=False 取原文模板形态：录制子进程在「目录缺件 / builtins.print 补丁未生效」
# 时输出的正是原文，两侧必须同样认得。
def _sentinel_text(template: str, *, translated: bool) -> str:
    if not translated:
        return _STATUS_PLACEHOLDER_RE.sub(lambda m: f"{_STATUS_SENTINEL}{m.group(1)}{_STATUS_SENTINEL}", template)
    names = {m.group(1) for m in _STATUS_PLACEHOLDER_RE.finditer(template)}
    if not names:
        return i18n_module.tr(template)
    return i18n_module.tr(template, **{name: f"{_STATUS_SENTINEL}{name}{_STATUS_SENTINEL}" for name in names})


# 按哨兵切成 (是否占位符, 段内容) 序列（re.split 带一个捕获组 → 奇数位即占位符名）。
def _split_sentinels(text: str) -> list[tuple[bool, str]]:
    parts: list[tuple[bool, str]] = []
    for index, chunk in enumerate(_STATUS_SENTINEL_SPLIT_RE.split(text)):
        if index % 2 == 0:
            if chunk:
                parts.append((False, chunk))
        else:
            parts.append((True, chunk))
    return parts


# 切段 → 带命名捕获组的正则。字面段一律 re.escape：译文的标点/空格都是普通字符，转义后
# 改标点不会让匹配漂移（落地 AGENTS「比较对象取 i18n.tr(...) 后形态」的口径）。
# 返回 None = required 里的占位符在该形态下取不到（显式判不可用）。
def _compile_parts(parts: list[tuple[bool, str]], required: tuple[str, ...]) -> re.Pattern[str] | None:
    body: list[str] = []
    captured: set[str] = set()
    for index, (is_placeholder, segment) in enumerate(parts):
        if not is_placeholder:
            literal = segment[1:] if index == 0 and segment.startswith("\r") else segment
            body.append(re.escape(literal))
            continue
        fragment = _STATUS_CAPTURE_GROUPS.get(segment)
        if fragment is None:
            # 取值段（已录时长 / 循环间隔秒数）：GUI 不解析它的值，只要求「那里有内容」。
            # 末位用 .*（该行到此为止也要匹配），其余位置用 .*? 以保证后续字面段能回溯。
            body.append(".*" if index == len(parts) - 1 else ".*?")
            continue
        if segment in captured:
            # 同名的第二个占位符：re 不允许重名捕获组（re.error: redefinition of group name），
            # 降级为不捕获——第一个同名段已经拿到了值。
            body.append(fragment.replace(f"(?P<{segment}>", "(?:", 1))
            continue
        body.append(fragment)
        captured.add(segment)
    if any(name not in captured for name in required):
        return None
    return re.compile("".join(body))


# 单条模板 → 可用正则 + 降级说明。先按 tr() 结果组装；组装不出（译稿删了必需占位符）时
# 记一条 problems 并回退到原文模板形态——子进程若同样取不到译文（目录缺件）输出的就是原文，
# 回退后两侧仍对齐；若子进程拿到的是坏译文，则本语言下该类行不解析，但**有留痕**。
def _pattern_from_template(template: str, required: tuple[str, ...]) -> tuple[re.Pattern[str] | None, tuple[str, ...]]:
    pattern = _compile_parts(_split_sentinels(_sentinel_text(template, translated=True)), required)
    if pattern is not None:
        return pattern, ()
    detail = i18n_module.tr("状态行译文取不到必需占位符，已回退原文模板匹配（请核对 i18n 目录该条译文）")
    fallback = _compile_parts(_split_sentinels(_sentinel_text(template, translated=False)), required)
    if fallback is None:
        return None, (i18n_module.tr("{detail}；原文模板同样不可用", detail=detail),)
    return fallback, (detail,)


# 空态行的子串匹配表：命中任一即清除全部录制标记。
# 取「第一个占位符之前」的字面段作子串（zh「没有正在录制的直播 循环监测间隔时间：」、
# en "No live rooms being recorded. Loop monitoring interval: "），尾部实参不参与匹配，
# 免得 delay_default 一变就失配；无占位符的那条（_STATUS_TPL_EMPTY）自然取整串。
# tr() 结果与原文两种形态**都收**（去重后保留顺序），理由见 _STATUS_TPL_EMPTY 注释。
def _idle_needles() -> tuple[str, ...]:
    needles: list[str] = []
    for template in (_STATUS_TPL_IDLE, _STATUS_TPL_EMPTY):
        for translated in (True, False):
            text = _sentinel_text(template, translated=translated)
            needle = text.split(_STATUS_SENTINEL, 1)[0].lstrip("\r").strip()
            if needle and needle not in needles:
                needles.append(needle)
    return tuple(needles)


@dataclass(frozen=True)
class _StatusPatterns:
    # 录制中行 / 画质降级行的正则；None = 该语言下这条模板拼不出可用正则（目录被写坏），
    # 该类行不解析，并由 problems 留痕。空态子串表独立工作，不受影响。
    recording: re.Pattern[str] | None
    downgrade: re.Pattern[str] | None
    # 空态行子串（tr() 结果 + 原文两种形态）
    idle_needles: tuple[str, ...]
    # 组装期的降级说明：由 _parse_quality_log 经 self._log 呈现一次。刻意不走 logger.*
    # ——那等于新增一条内部诊断 msgid，要同步四语目录（AGENTS「关键约定 #14」），
    # 而这条只在「译稿被写坏」时出现，与本文件其余 GUI 内部提示同走 self._log。
    problems: tuple[str, ...]


def _build_status_patterns() -> _StatusPatterns:
    recording, recording_problems = _pattern_from_template(_STATUS_TPL_RECORDING, _STATUS_REQUIRED_RECORDING)
    downgrade, downgrade_problems = _pattern_from_template(_STATUS_TPL_DOWNGRADE, _STATUS_REQUIRED_DOWNGRADE)
    return _StatusPatterns(
        recording=recording,
        downgrade=downgrade,
        idle_needles=_idle_needles(),
        problems=recording_problems + downgrade_problems,
    )


# 语言 → 已组装的匹配器。键取 i18n.get_language()（恒等于**实际装载**的语言码，不会
# 「请求 zh_TW、实际 en_US」漂移），语言一变必然 miss 并重算。**不得改成模块级一次
# 编译**——那等价于把简中串钉死。
_STATUS_PATTERNS_BY_LANG: dict[str, _StatusPatterns] = {}
# 组装期「语言是否被切走」复核的重试上限，判据见 _status_patterns 的竞态说明。
_STATUS_PATTERNS_STABLE_ATTEMPTS = 3


def _status_patterns() -> _StatusPatterns:
    # 不加锁：并发最坏是同一语言被组装两遍（纯函数 + 原子赋值），不会读到半成品。
    # 但「原子赋值」挡不住**组装过程中**换语言：_build_status_patterns() 要连读 6 次
    # i18n.tr()，本函数由录制输出线程调用、set_language 由 UI 线程调用；语言在读取之间
    # 切走会组出混语 patterns，一旦永久缓存就会拿混排串匹配纯英文行并长期静默失配。
    # 故组装后复验语言码未变才落缓存，变了按新语言重取；连续不稳时返回最后一遍结果但
    # 不写缓存，把混语形态的存活期压在一轮之内。加锁只是把竞态窗口挪个位置，复核才能
    # 真正证明「组装期间没换过语言」。
    # 已知边界：目录文件在运行期被替换而语言码不变时不会重算——GUI 没有「重载目录」入口。
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


# 直播录制 GUI 主类：整合界面、子进程录制、日志队列与画质监控。
@final
class LiveRecorderGUI:

    ANSI_ESCAPE_PATTERN = re.compile(r"\x1b\[[0-9;]*m")
    # 画质降级行与录制中行的匹配串由**与生产侧同 msgid 的 tr() 结果**派生，并按语言惰性
    # 重算（定义见模块级 _status_patterns）；不得硬编码简中正则。
    # 两段语义不得回退：recording_live 贪婪 .+、qa 限定「不含 ] 的字符」——否则
    # 「主播[1号][原画] 正在录制中」会被解析成 name="主播"、quality="1号][原画"，
    # 画质监控表出现幽灵行、画质切换反查主播名失败。空态行见 _parse_quality_log。
    _MAX_LOG_LINES = 1000
    # 日志截断契约：超过 _MAX_LOG_LINES 行时一次裁到 _LOG_TRIM_TO 行（成批裁剪，避免逐行
    # 删除）；界面提示的「超过 1000 行自动截断」与本组常量同源，改值必须同改提示文案。
    _LOG_TRIM_TO = 800
    _LOG_FLUSH_INTERVAL = 200
    # M-71（2026-10-21，CODE_REVIEW_2026-10-21）：输出线程批次的**时间兜底**（秒）。
    # 稳定录制的房间约 120s 才输出一条状态行，只按「攒满 batch_size 行」刷新的话日志页要
    # 空白约 20 分钟——用户视角就是「界面冻住了」，且这是正常运行路径必然出现的失效。
    # 取 0.8s 而非更小：突发日志仍按 10 行成批（Tk 插入次数不变），稀疏日志最多滞留一个
    # 读取节拍即入队；UI 侧 _LOG_FLUSH_INTERVAL(200ms) 决定实际可见延迟，两者相加仍 <1.5s。
    _LOG_BATCH_FLUSH_SECONDS = 0.8
    _STATUS_REFRESH_INTERVAL = 10000  # 未录制时的刷新间隔（毫秒）
    _STATUS_REFRESH_INTERVAL_ACTIVE = 3000  # 有录制直播间时的刷新间隔（毫秒）
    # 周期链异常留痕的限频窗口（秒，见 _warn_chain）：故障是持续性的，不限频会把日志页
    # 刷满，全静默又让编程错误不可见。
    _CHAIN_WARN_INTERVAL_SECONDS = 30.0

    # 由 _build_* 初始化的实例组件声明（供类型检查器识别）。ttk.Frame 不是 tkinter.Frame
    # 子类（ttk.Widget 一族），故 sidebar/status_pill 声明为 ui_kit.Frame。
    sidebar: "Frame"
    status_pill: "Frame"

    # 以下组件仅在 _build_* 中初始化，而 _build_* 均由 __init__ 经 _setup_ui() 调用，
    # 运行期必然已初始化；「未初始化」告警由文件顶部的 pyright 指令关闭。
    _sidebar_dot_item: int
    _big_dot: tk.Canvas
    _big_dot_item: int
    sidebar_status_label: Label
    theme_menu: Menu
    language_menu: Menu
    big_status_label: Label
    big_status_sub: Label
    info_interval: Label
    info_format: Label
    info_tray: Label
    info_time: Label
    start_btn: Button
    stop_btn: Button
    config_text: EditorText
    reload_btn: Button
    save_btn: Button
    log_text: tk.Text
    _q_stat_total: Label
    _q_stat_ok: Label
    _q_stat_down: Label
    _quality_table: DataTable
    _quality_placeholder: Label
    _quality_row_setq: dict[str, str]
    _dm_stat_rooms: Label
    _dm_stat_connected: Label
    _dm_stat_msgs: Label
    _dm_table: DataTable
    _dm_placeholder: Label
    _dm_filter_menu: Menu
    danmaku_text: tk.Text

    # 初始化 GUI 主窗口、路径配置、状态与所有后台调度。
    def __init__(self, root: tk.Tk):
        self.root = root
        apply_title(root, T("直播录制控制台"))

        self.script_dir = os.path.dirname(os.path.abspath(__file__))
        # 冻结后 GUI 模块位于 exe 同级的 _internal/，而 config/ ffmpeg/ node/ downloads/
        # 等运行时资源保持在 exe 同级目录（_internal 的父目录）。源码运行时
        # self.script_dir 即项目根，无需回退。
        if os.path.basename(os.path.normpath(self.script_dir)) == "_internal":
            self.app_root = os.path.dirname(self.script_dir)
        else:
            self.app_root = self.script_dir
        self.url_config_file = os.path.join(self.app_root, "config", "URL_config.ini")
        self.main_config_file = os.path.join(self.app_root, "config", "config.ini")
        self.downloads_dir = os.path.join(self.app_root, "downloads")

        # 尺寸档位必须在建任何控件**之前**确定：Fonts 档位、ttk padding 与窗口初始几何都
        # 从它派生，事后改会让控件先按旧尺寸建再放大。顺序：读偏好（依赖 main_config_file）
        # → 「自动」按屏幕可用区现算 → 构造 profile → 绑定 Fonts → 设几何。
        self.scale_profile = self._resolve_initial_scale()
        Fonts.bind_profile(self.scale_profile)
        # 自选字体：顺序必须是「注册私有字体 → 绑定族名 → 建任何控件」。family 在建控件时
        # 被快照进 tkfont.Font，启动期一次到位可避免首帧按默认族排一遍再重排的可见跳动。
        self._font_file_pref = load_font_file_preference(self.main_config_file)
        self._selected_font_family = self._activate_saved_font(load_font_preference(self.main_config_file))
        # 窗口几何按档位放大后 clamp 到屏幕可用区（150% 档在 1366x768 上不能开出比屏幕
        # 还大的窗口）。
        _win_w, _win_h, _min_w, _min_h = self.scale_profile.window_size(
            root.winfo_screenwidth(), root.winfo_screenheight()
        )
        self.root.geometry(f"{_win_w}x{_win_h}")
        self.root.minsize(_min_w, _min_h)

        # status_pill 由 _build_sidebar 重建并布局；此处先以真实占位实例初始化（未打包的
        # Frame 不会渲染），_sidebar_dot 的占位 Canvas 也需要一个父容器。占位实例从不显示，
        # 随后会被 _build_sidebar 的 themed Frame 替换。
        self.status_pill = Frame(self.root)
        # _sidebar_dot 同理：构建方法会重建并打包，此处只做有类型占位。
        self._sidebar_dot: tk.Canvas = tk.Canvas(self.status_pill)

        # 主题层：ttk 主题注册 + 偏好持久化（[GUI] gui_theme）。未设置（""）时按明暗落
        # 主题——无显式偏好即「跟随系统」。ttk 控件配色由 ThemeManager 的变体样式从 token
        # 派生（本调用即注册），根窗口底色由 _apply_root_chrome() 按 token 上色。
        self.theme_manager = ThemeManager(self.scale_profile)
        saved_theme = load_theme_preference(self.main_config_file)
        # 「跟随系统」当前是否生效：无显式偏好即跟随（含菜单里选「跟随系统」并写回空值）；
        # 主题菜单初值与选择回调都读它。
        self._theme_follow_system = saved_theme == ""
        if saved_theme:
            self.theme_manager.select(saved_theme)
        else:
            self.theme_manager.select(detect_system_appearance())
        self.theme_manager.apply(self.root)
        set_scale_percent(self.scale_profile.percent)
        self._apply_root_chrome()

        # 动效等级：用户偏好与系统「关闭动画」开关合成后的有效等级。系统开关优先于用户
        # 选择（无障碍），故这里存的是合成结果，菜单显示的仍是用户偏好本身；_ensure_motion_
        # feedback 会把「系统强制 off」显式落到菜单上。
        self._motion_follow_system = load_motion_preference(self.main_config_file) == ""
        self.motion = MotionController(
            effective_motion(
                "" if self._motion_follow_system else load_motion_preference(self.main_config_file),
                system_animations=detect_system_animations(),
            )
        )

        # 进程状态（线程安全访问）
        self._process_lock = threading.Lock()
        self._process: subprocess.Popen[str] | None = None
        self._process_pid: int | None = None
        # 本次录制核心子进程的映像基名（小写），在 start_recording 成功拉起时登记。
        # 退出兜底的 taskkill 打的是**号码**，而 Windows 的 PID 在进程退出后即进入复用池；
        # 记下基名才可能在动手前读出「这个号现在是谁」。空串 = 从未启动过子进程。
        self._child_image_name: str = ""
        self._running = False
        self._stopping = False  # 停止进行中标志：阻塞启动/重复停止，消除停止竞态窗口
        # 录制会话代号：每次成功启动子进程时自增。停止收尾有两条独立路径（手动停止的
        # _wait_and_update_ui 与日志哨兵的 _process_ended），时序颠倒会双重收尾；更糟的是
        # 「停止 → 立即重启」时旧会话迟到的回调会把新会话的 UI 状态打回「未运行」。
        # 收尾回调携带启动时刻捕获的 session_id，不一致即跳过。
        self._session_id = 0

        # 「停止录制」与「彻底退出」都要对同一子进程执行
        # FreeConsole→AttachConsole→GenerateConsoleCtrlEvent→FreeConsole，而控制台附着是
        # **进程全局**状态——并发时 CTRL_BREAK 会错投/丢失，最坏退化成 taskkill 硬杀，子进程
        # safe_exit 清理 ffmpeg 的机会随之失去。停止链后台最长跑 15s+，退出入口仍可点。
        # 两把锁、层次各一（AGENTS「调用方持锁 vs 内部自持锁 二选一」口径）：
        #   _stop_inflight_lock 只保护 _stop_inflight 字段，持锁期仅一次赋值/读取；
        #   _console_stop_lock 是停止子进程临界区的串行化闸门，**只由 _stop_child_once
        #   在 with 块内持锁**；被它调用的 _send_stop_signal_and_wait 不得自己加锁、也不得
        #   被别处直接调用。
        # 均为普通 threading.Lock（本文件无协程，不存在跨 await 持锁）；刻意用非重入锁，
        # 嵌套调用属实现错误，应当当场炸出。
        self._stop_inflight: threading.Thread | None = None
        self._stop_inflight_lock = threading.Lock()
        self._console_stop_lock = threading.Lock()

        # 三条 after 自续期链（状态刷新 / 弹幕刷新 / 日志 flush）的异常留痕限频时刻，key
        # 为链名。仅 UI 线程读写（root.after 回调只可能跑在主线程），故不加锁。
        self._chain_warn_at: dict[str, float] = {}

        # 状态行正则组装期的降级说明（按语言惰性重算，problems 变化才重记一条日志）。
        self._status_pattern_problems: tuple[str, ...] | None = None

        self.output_thread: threading.Thread | None = None

        self._last_url_config_mtime = 0.0
        # 外部改动确认框的「已弹出」标志。Tk 的 messagebox 是**嵌套事件循环**：放进 after
        # 链后，用户尚未应答时下一轮定时器照常触发，每 3 秒叠一个同样的确认框（录制子进程
        # 每轮回写 URL_config.ini 时 mtime 持续变化，正好喂饱这条链）。等待应答期间直接返回。
        self._url_config_prompt_open = False
        # 编辑器内容的「已保存」基线：判断是否存在未保存编辑，避免外部 mtime 变化触发的
        # 自动重载把用户正在编辑的内容静默覆盖。
        self._config_baseline_content = ""
        # 磁盘侧基线（与 AdvancedSettingsWindow 的 _disk_snapshot 同语义）：上次从磁盘
        # 读到 / 写回的那份**原文**。保存前与当前磁盘内容比对即可识别「录制子进程刚改过」
        # ——mtime 轮询挡不住「点保存那一瞬间磁盘已被改」，整文件写回也没有跨进程锁可依赖。
        self._url_disk_snapshot: str | None = None
        # 高级设置窗口单例引用：见 open_advanced_settings()，防止连点打开多个 config.ini
        # 编辑器互相覆盖保存。
        self._adv_settings_window: AdvancedSettingsWindow | None = None
        self._refresh_job_id: str | None = None

        # 状态缓存（避免频繁读取配置）
        self._status_cache_mtime = 0.0
        self._status_cache: tuple[str, str] | None = None

        # 日志队列（线程间通信）。元素二选一：日志批次 list[...] / 进程结束哨兵 (session_id,)。
        # 哨兵必须携带会话代号：EOF 在子线程感知、收尾只能在 UI 线程做，停止后立即重启时
        # 旧会话的迟到 EOF 会把新会话状态打回「未运行」，故由 _process_ended 比对后丢弃。
        self._log_queue: queue.Queue[list[tuple[str, str]] | tuple[int | None]] = queue.Queue()
        self._log_flush_job_id: str | None = None
        self._log_queue_has_data = False
        self._log_queue_lock = threading.Lock()  # 保护 _log_queue_has_data 跨线程访问

        # 画质监控数据（线程安全：_quality_lock 保护 _quality_data）
        # {name: {set_quality, actual_quality, downgraded, alert_time, alert_message, recording, last_seen}}
        self._quality_lock = threading.Lock()
        self._quality_data: dict[str, dict[str, str | bool | float]] = {}
        self._quality_last_displayed: dict[str, dict[str, str | bool | float]] = {}
        # 画质切换相关（仅 UI 线程访问）：_quality_options 为可选画质（读 config.ini，与
        # Web 端共用）；_quality_default_label 为菜单首项（选中即移除配置行画质段、回落
        # 全局默认）；_anchor_url_map / _anchor_quality_map 为 主播名 → 地址 / 当前画质。
        self._quality_options: list[str] = []
        # 哨兵存 tr 后形态（比较对象一律取 i18n.tr(...) 后形态）；语言切换钩子重置本值
        # 并重读上下文，比较与菜单展示随之整体换语言。
        self._quality_default_label = i18n_module.tr("默认画质")
        self._anchor_url_map: dict[str, str] = {}
        self._anchor_quality_map: dict[str, str] = {}

        # 弹幕监控数据（线程安全：_danmaku_lock 保护以下字段）
        # _danmaku_rooms: {room: {platform/connected/started_at/msg_total/msg_rate/gift_total/online}}
        # _danmaku_msgs: 近期消息环形缓冲（tail 线程追加，UI 线程渲染，最多 300 条）
        self._danmaku_lock = threading.Lock()
        self._danmaku_rooms: dict[str, dict[str, str | bool | int | float]] = {}
        self._danmaku_msgs: deque[dict[str, Any]] = deque(maxlen=300)
        # 哨兵存 tr 后形态（同 _quality_default_label 的口径），语言切换钩子重置后重渲染
        self._danmaku_filter = i18n_module.tr("全部房间")
        self._danmaku_stats_dirty = True  # 统计表是否有变化待重绘
        self._danmaku_stream_dirty = True  # 弹幕流是否有新消息待重绘
        # 仅缓存上次渲染的 rows 用于比较去重（见 _update_danmaku_display），值不含 float
        self._danmaku_last_stats: list[dict[str, str | bool | int]] | None = None
        self._danmaku_tail_thread: threading.Thread | None = None
        # 停止标志属于「当前那一条 tail 线程」而**不属于**本对象：初值 None，由
        # _start_danmaku_tail 每次新建后交给该线程独占。若复用共享 Event 并在下次启动时
        # clear()，仍卡在 sleep/f.read 的旧线程醒来只能看到 False，于是永不退出且无人持有
        # 引用——每「停止→启动」一次多留一条 tail 线程，各自读同一份 JSONL，弹幕/礼物计数
        # 随重启次数成倍虚增且无日志。
        self._danmaku_tail_stop: threading.Event | None = None
        self._danmaku_refresh_job_id: str | None = None

        # UI 线程事件队列：后台线程一律经 post_ui 投递回调，由 _pump_ui_events 在 UI 线程
        # 执行。tkinter 不是线程安全的，后台线程直接调 root.after/createcommand 会随机崩溃
        # （RuntimeError: main thread is not in main loop）。
        self._ui_event_queue: queue.Queue[tuple[Callable[..., None], tuple[object, ...]]] = queue.Queue()
        self._pump_active = True
        self._ui_pump_job_id: str | None = None

        self._status_animating = False
        self._status_anim_index = 0
        self._status_anim_timer: str | None = None
        # M-77②（2026-10-21）：一次性 after 的 job id 必须记账。root/控件的 after 注册在
        # 解释器上、不随窗口销毁而撤销；窗口化构建（pythonw / PyInstaller console=False）
        # 下 sys.stderr 为 None，销毁后回调抛的 TclError 连一行堆栈都留不下，故障表现为
        # 「切了主题圆点没变色」「对话框没 modal 也没日志」且无从归因。
        self._canvas_bg_job_id: str | None = None
        self._close_dialog_grab_job_id: str | None = None

        self._nav_buttons: dict[str, Button] = {}
        self._pages: dict[str, Frame] = {}
        self._current_page = ""

        # 退出/对话框防重入标志
        self._quitting = False
        self._close_dialog: tk.Toplevel | None = None

        self.sidebar = self._build_sidebar()
        self._setup_ui()
        self._load_config()
        self._schedule_log_flush()
        self._schedule_status_refresh()
        self._danmaku_refresh_job_id = self.root.after(1000, self._schedule_danmaku_refresh)
        self._ui_pump_job_id = self.root.after(100, self._pump_ui_events)

    # 读取缩放偏好并解析成运行期档位。「未设置」与「自动」都按屏幕可用区现算——用户没
    # 选过就不该被上次在这台机器上的值钉死（换台分辨率不同的机器就再也不对了）。屏幕
    # 尺寸取不到（无头/异常）时落到小屏分支，ScaleProfile 内部对 <=0 另有兜底，不会崩。
    def _resolve_initial_scale(self) -> ScaleProfile:
        try:
            screen_w = self.root.winfo_screenwidth()
            screen_h = self.root.winfo_screenheight()
        except tk.TclError:
            screen_w = screen_h = 0
        preference = load_scale_preference(self.main_config_file)
        if preference == AUTO_SCALE_ID or not preference:
            return ScaleProfile(auto_scale_for_screen(screen_w, screen_h))
        return ScaleProfile(int(preference))

    # ─── UI 线程事件泵（线程安全调度） ──────────────────────

    # 从任意线程安全地调度回调到 UI 线程执行（仅入队，不触碰 Tk）。
    def post_ui(self, callback: Callable[..., None], *args: object) -> None:
        self._ui_event_queue.put((callback, args))

    # UI 线程事件泵：执行后台投递的回调并激活日志刷新链。
    def _pump_ui_events(self) -> None:
        if not self._pump_active:
            return
        while True:
            try:
                callback, args = self._ui_event_queue.get_nowait()
            except queue.Empty:
                break
            try:
                callback(*args)
            except Exception:
                # 不能 traceback.print_exc()：窗口化运行下 sys.stderr 为 None，会二次崩溃
                # （AttributeError: 'NoneType' object has no attribute 'write'）。
                self._log(i18n_module.tr("UI 事件回调执行异常（详见运行日志）"), "error")
                self._log(traceback.format_exc(), "error")

        if not self._pump_active:
            return

        # 第四支同族自续期 after 链：续期必须落 finally——前面的「激活日志刷新链」会在
        # 窗口销毁竞态中抛 TclError，一抛就跳过续期，UI 事件泵永久停摆（用户视角 = 关不掉
        # 窗口），post_ui 排队的 _on_recording_stopped / _finalize_quit 从此不再执行。
        try:
            # 后台线程只往日志队列放数据，由这里在 UI 线程按需激活刷新链
            with self._log_queue_lock:
                has_data = self._log_queue_has_data
            if has_data and self._log_flush_job_id is None:
                # 重排失败时 _after_retry 返回 None，_log_flush_job_id 保持「未激活」态，
                # 下一轮泵仍会重试激活。不得把失败写成「已有一个作业」，否则刷新链无人唤醒。
                self._log_flush_job_id = self._after_retry(self._LOG_FLUSH_INTERVAL, self._schedule_log_flush)
        finally:
            self._ui_pump_job_id = self._after_retry(100, self._pump_ui_events)

    # ─── 进程状态线程安全访问 ───────────────────────────────

    @property
    def process(self) -> subprocess.Popen[str] | None:
        with self._process_lock:
            return self._process

    # 设置当前子进程对象（线程安全）。
    @process.setter
    def process(self, value: subprocess.Popen[str] | None) -> None:
        with self._process_lock:
            self._process = value

    # 读取当前子进程 PID（线程安全）。
    @property
    def process_pid(self) -> int | None:
        with self._process_lock:
            return self._process_pid

    # 设置当前子进程 PID（线程安全）。
    @process_pid.setter
    def process_pid(self, value: int | None) -> None:
        with self._process_lock:
            self._process_pid = value

    # 读取录制运行状态（线程安全）。
    @property
    def running(self) -> bool:
        with self._process_lock:
            return self._running

    # 设置录制运行状态（线程安全）。
    @running.setter
    def running(self, value: bool) -> None:
        with self._process_lock:
            self._running = value

    # ─── UI 初始化 ─────────────────────────────────────────

    # 构建主布局（左侧导航栏 + 右侧内容区）并展示默认页。
    def _setup_ui(self) -> None:
        # 侧栏宽度随档位缩放：导航项文字（10 字）+ 左右留白在 150% 档会超出原 230px
        # 而折行，折行后整栏高度跳变、当前项可能被挤出视野。
        self.root.grid_columnconfigure(0, minsize=self.scale_profile.sidebar_width(), weight=0)
        self.root.grid_columnconfigure(1, weight=1)
        self.root.grid_rowconfigure(0, weight=1)

        self._build_content()
        self._show_page("dashboard")
        # 侧栏高度不随内容伸缩：窗口高小于需求高时，pack 会把最后一个控件（彻底退出）
        # 顶到窗口外。故把侧栏的**实测**需求高纳入 minsize 下限。
        self._raise_minsize_to_fit_sidebar()
        self._raise_width_to_fit_content()
        # 启动期统一重译：配置语言之前构建的少数标签（品牌/主题菜单初值）按导入默认语言
        # 定型，此处回填一次保证整窗语言一致（登记表回填幂等）。
        retranslate_all()

    # 把窗口最小高度抬到「侧栏实测需求高」，让底部控件不被挤出窗口。
    # 用实测而非写死常量：侧栏高度随档位、语言、译文行数变化；winfo_reqheight 与渲染同源。
    # 以当前窗口高为上限：屏幕本身装不下时不能把 minsize 设得超过屏幕，否则用户再也拖不动。
    def _raise_minsize_to_fit_sidebar(self) -> None:
        try:
            self.sidebar.update_idletasks()
            needed = self.sidebar.winfo_reqheight()
            _cur_w, _cur_h, min_w, min_h = self.scale_profile.window_size(
                self.root.winfo_screenwidth(), self.root.winfo_screenheight()
            )
        except tk.TclError:
            return
        if needed <= min_h:
            return
        self.root.minsize(min_w, min(needed, _cur_h))

    # 把窗口宽抬到「整窗实测需求宽」。Tk grid 对「需求宽 > 分配宽」的列是**裁切**而非
    # 收缩：root reqwidth 一旦超过 geometry 宽度，内容列右缘（卡片右边框 + 20px 右边距）
    # 会被整段切掉，且 minsize 不拦用户缩到更窄。三件事缺一都只治标：
    #   ① 把首窗几何抬到需求宽（消掉首帧赤字）；
    #   ② 首次绘制前先把几何压到档位最小宽、读一次需求宽，得到内容的**收缩地板**，再把
    #      minsize 宽抬到地板——抬到需求宽会失去「窗口还能拖小」的可用性；
    #   ③ 所有尺寸 clamp 到屏幕可用区（与 _raise_minsize_to_fit_sidebar 同一口径）。
    def _raise_width_to_fit_content(self) -> None:
        try:
            screen_w = self.root.winfo_screenwidth()
            cur_h = self.root.winfo_height()
            needed = self._settled_reqwidth()
            _w, _h, min_w, _min_h = self.scale_profile.window_size(screen_w, self.root.winfo_screenheight())
        except tk.TclError:
            return
        cap = int(screen_w * SCREEN_FILL_CEILING)
        fit = min(max(min_w, needed), cap)
        floor = fit
        if min_w < fit:
            try:
                self.root.geometry(f"{min_w}x{cur_h}")
                floor = min(max(min_w, self._settled_reqwidth()), cap)
            except tk.TclError:
                floor = min_w
        try:
            self.root.geometry(f"{fit}x{cur_h}")
            _cur_min_w, cur_min_h = self.root.minsize()
            self.root.minsize(floor, cur_min_h)
        except tk.TclError:
            return

    # 按偏好恢复字体族（构造期调用，必须在控件创建前）。三级回退：自定义字体文件（可能
    # 被删/损坏）→ 显式选择的系统字体族（可能随系统重装消失）→ 默认族；任一环节不通过
    # 就降一级并记日志，绝不让失效偏好把界面渲染成方块。返回实际生效的族名（"" = 默认族）。
    def _activate_saved_font(self, family_pref: str) -> str:
        file_pref = getattr(self, "_font_file_pref", "") or ""
        if file_pref and os.path.exists(file_pref):
            registered = register_private_font(file_pref, self.root)
            if registered:
                Fonts.bind_family(registered)
                return registered
            # 字体路径可能含用户名 Home 段，按 AGENTS 凭据红线入日志前必须脱敏
            logger.warning(
                i18n_module.tr("自定义字体加载失败，回落到默认字体: {path}", path=mask_credentials(file_pref))
            )
        if family_pref and is_family_available(family_pref, self.root):
            Fonts.bind_family(family_pref)
            return family_pref
        if family_pref:
            # 选过但本机已无此字体（系统重装/字体卸载）：降级并明示，避免用户以为界面没变。
            logger.warning(i18n_module.tr("字体不可用，回落到默认字体: {family}", family=family_pref))
        Fonts.bind_family("")
        return ""

    # 热应用字体族并把几何收敛在同一 sync 里做完：换族后字形宽度全变，卡片/状态网格的
    # 需求宽随之变，不重新结算会偏到右边框裁切那条路上。
    def _apply_font_family(self, family: str) -> None:
        Fonts.set_family(family)
        self._selected_font_family = family
        restyle_fonts(self.root)
        for page in self._pages.values():
            page.update_idletasks()
        self._raise_width_to_fit_content()
        self._raise_minsize_to_fit_sidebar()

    # 读数要迭代到稳定：Treeview 的列宽在 <Configure> 回调里按树宽重算，列宽变了
    # 需求宽跟着变，单次 update() 拿到的是上一轮的中介值（实测能差 300+px）。
    # M-77①（2026-10-21，CODE_REVIEW_2026-10-21）：收敛一律走 update_idletasks()，不再走
    # self.root.update()——后者重入**整个**事件循环，会把排队中的鼠标/键盘事件与尚未接完线
    # 的回调打在半成品控件上（本方法由 _setup_ui 末尾调用，那时 __init__ 的后半段与
    # _load_config 都还没跑；换字体/换档位路径同样可能在动效中间态进来）。
    # 「迭代到稳定」这个判据原样保留：它要的只是让列宽重算落地，而重算挂在 <Configure> 绑定
    # 上、不会由 idle 自己触发，故每轮 idle 之后对两张监控表**定向补发一次** <Configure>
    # （event_generate 只走绑定链，不消费任何排队事件）。窗口尚未 realized 时它抛 TclError，
    # 那正是「列宽还没有可算的树宽」，接住后按 idle 读数继续收敛即可。
    def _settled_reqwidth(self, passes: int = 4) -> int:
        measured = self.root.winfo_reqwidth()
        for _ in range(passes):
            self.root.update_idletasks()
            self._nudge_table_configure()
            self.root.update_idletasks()
            current = self.root.winfo_reqwidth()
            if current == measured:
                break
            measured = current
        return measured

    # 定向补发 <Configure>：只为触发 src/ui_kit.DataTable 挂在事件上的列宽重算，等价于
    # 旧实现里 root.update() 顺带做掉的那一步，但不重入事件循环（M-77①）。
    # 用 getattr 而非直接读 self._quality_table / self._dm_table：_settled_reqwidth 也会被
    # 不跑 __init__ 的桩实例驱动，直接访问会抛 AttributeError 把整轮读数带崩。
    def _nudge_table_configure(self) -> None:
        for table in (getattr(self, "_quality_table", None), getattr(self, "_dm_table", None)):
            if table is None:
                continue
            try:
                table.tree.event_generate("<Configure>")
            except tk.TclError:
                # 控件未 realize / 已销毁：没有树宽可算，交由下一轮 idle 结算继续收敛。
                continue

    # 构建左侧导航栏（品牌、状态胶囊、导航按钮、主题/缩放/动效/语言设置与退出）。
    # 控件层用 src.ui_kit 的 ttk 工厂，配色全部走 ui_theme 变体样式。
    def _build_sidebar(self) -> Frame:
        sidebar = Frame(self.root)
        sidebar.grid(row=0, column=0, sticky="nsew")
        sidebar.grid_propagate(False)

        # 品牌区
        brand = Frame(sidebar)
        brand.pack(fill=tk.X, padx=20, pady=(24, 6))
        Label(brand, text="🎬", font=Fonts.mark(30)).pack(side=tk.LEFT)
        brand_text = Frame(brand)
        brand_text.pack(side=tk.LEFT, padx=(10, 0))
        Label(brand_text, text=T("直播录制"), font=Fonts.title()).pack(anchor=tk.W)
        Label(brand_text, text="DouyinLiveRecorder", font=Fonts.small(), variant="muted").pack(anchor=tk.W)

        # 状态胶囊（底色 = surface_alt，圆点画布与文字标签底色必须同槽）
        self.status_pill = Frame(sidebar, variant="alt", height=38)
        self.status_pill.pack(fill=tk.X, padx=16, pady=(14, 6))
        self.status_pill.pack_propagate(False)

        self._sidebar_dot = tk.Canvas(self.status_pill, width=12, height=12, highlightthickness=0, bd=0)
        self._sidebar_dot.pack(side=tk.LEFT, padx=(14, 8))
        self._sidebar_dot_item = self._sidebar_dot.create_oval(1, 1, 11, 11, fill=Colors.DANGER, outline="")
        self._sync_dot_bg()

        self.sidebar_status_label = Label(
            self.status_pill,
            # 运行态由 _update_status_bar 周期改写，不能走 T() 登记（重译会把状态打回
            # 初始值）；建时 tr + 语言切换钩子显式调 _update_status_bar 重渲染
            text=i18n_module.tr("未运行"),
            font=Fonts.body(bold=True),
            variant="alt",
        )
        self.sidebar_status_label.pack(side=tk.LEFT)

        # 导航按钮
        nav = Frame(sidebar)
        nav.pack(fill=tk.X, padx=12, pady=(18, 0))

        self._add_nav_button(nav, "dashboard", T("📊   控制台"))
        self._add_nav_button(nav, "quality", T("🎯   画质监控"))
        self._add_nav_button(nav, "danmaku", T("💬   弹幕监控"))
        self._add_nav_button(nav, "config", T("📝   URL 配置"))
        self._add_nav_button(nav, "logs", T("📋   运行日志"))

        # 底部区域
        bottom = Frame(sidebar)
        bottom.pack(side=tk.BOTTOM, fill=tk.X, padx=12, pady=16)

        # 四个偏好设置（主题 / 缩放 / 动效 / 语言）统一排成 2×2 网格：竖排四项在 85% 档
        # （窗口高 629px、侧栏需求高 662px）会把「彻底退出」顶出窗口；2×2 把底部压回约
        # 200px，且四个次级设置的视觉权重一致。
        settings = Frame(bottom)
        settings.pack(fill=tk.X)
        settings.grid_columnconfigure((0, 1), weight=1, uniform="settings")

        def _setting_label(row: int, col: int, text: "str | Translatable") -> None:
            # 设置项标签统一 caption 档 + muted 变体：它们是「控件的说明」而非内容，
            # 视觉权重必须低于下拉本身。
            Label(settings, text=text, font=Fonts.small(), variant="muted", anchor=tk.W).grid(
                row=row * 2, column=col, sticky="ew", padx=(4 if col == 0 else 8, 4), pady=(0, 3)
            )

        # 界面主题（唯一明暗/对比度入口）：「跟随系统」= 清空显式偏好并按系统明暗落
        # light/dark（下次启动继续跟随）；三个显式主题即选即持久化（[GUI] gui_theme）。
        _setting_label(0, 0, i18n_module.tr("界面主题"))
        self._theme_ids_by_display: dict[str, str] = {}
        _theme_values: list[str] = []
        for _tid in (_FOLLOW_SYSTEM_ID, *THEME_IDS):
            _display = i18n_module.tr("跟随系统") if _tid == _FOLLOW_SYSTEM_ID else i18n_module.tr(_THEME_LABELS[_tid])
            self._theme_ids_by_display[_display] = _tid
            _theme_values.append(_display)
        self.theme_menu = Menu(settings, values=_theme_values, command=self._on_theme_change, font=Fonts.small())
        self.theme_menu.grid(row=1, column=0, sticky="ew", padx=(4, 4), pady=(0, 10))
        # 初始值：跟随系统时不得显示解析后的主题名（用户并未显式选过它）
        if self._theme_follow_system:
            self.theme_menu.set(i18n_module.tr("跟随系统"))
        else:
            self.theme_menu.set(i18n_module.tr(_THEME_LABELS[self.theme_manager.theme_id]))

        # 界面缩放：档位列表来自 src/ui_scale.SCALE_PRESETS，首项「自动」按屏幕现算。
        _setting_label(0, 1, T("界面缩放"))
        self._scale_ids_by_display: dict[str, str] = {}
        _scale_values: list[str] = []
        for _pct in (AUTO_SCALE_ID, *(str(p) for p in SCALE_PRESETS)):
            _display = i18n_module.tr("自动") if _pct == AUTO_SCALE_ID else i18n_module.tr("{percent}%", percent=_pct)
            self._scale_ids_by_display[_display] = _pct
            _scale_values.append(_display)
        self.scale_menu = Menu(settings, values=_scale_values, command=self._on_scale_change, font=Fonts.small())
        self.scale_menu.grid(row=1, column=1, sticky="ew", padx=(8, 4), pady=(0, 10))
        # 初始值：显示「自动」而非解析后的档位（未显式选过时不该假装用户选过 100%）
        _saved_scale = load_scale_preference(self.main_config_file)
        self._scale_follow_system = _saved_scale in ("", AUTO_SCALE_ID)
        self.scale_menu.set(
            i18n_module.tr("自动")
            if self._scale_follow_system
            else i18n_module.tr("{percent}%", percent=self.scale_profile.percent)
        )

        # 动效强度：off/subtle/full，首项「跟随系统」读系统的「显示动画」开关。
        _setting_label(1, 0, T("动效强度"))
        self._motion_ids_by_display: dict[str, str] = {}
        _motion_values: list[str] = []
        for _mid in (FOLLOW_SYSTEM_MOTION_ID, *MOTION_IDS):
            _display = (
                i18n_module.tr("跟随系统") if _mid == FOLLOW_SYSTEM_MOTION_ID else i18n_module.tr(_MOTION_LABELS[_mid])
            )
            self._motion_ids_by_display[_display] = _mid
            _motion_values.append(_display)
        self.motion_menu = Menu(settings, values=_motion_values, command=self._on_motion_change, font=Fonts.small())
        self.motion_menu.grid(row=3, column=0, sticky="ew", padx=(4, 4), pady=(0, 10))
        # 初始值：显示用户的显式选择（可能与实际生效等级不同——系统关闭动画时
        # 实际是 off 而菜单仍显示用户选的值，这是有意的，见 _ensure_motion_feedback）
        self.motion_menu.set(
            i18n_module.tr("跟随系统")
            if self._motion_follow_system
            else i18n_module.tr(_MOTION_LABELS[self.motion.motion_id])
        )
        # 系统关闭动画时把菜单显式落到「关闭」并告知原因——用户选了却没反应
        # 是最容易被当成 bug 的交互。
        self._ensure_motion_feedback()

        # 语言切换：显示名 → 语言码映射；选择即热切换本进程翻译目录并写回 config.ini
        # 排在 2×2 网格的第二行第二列（与前三项同格，标签仍写「语言 Language」——
        # 中英双语标签是本仓既有惯例，英文界面下用户不必猜这是什么设置）。
        _setting_label(1, 1, T("语言 Language"))
        # 显示名一律取 i18n.unique_display_names()，不得再在本文件裁剪括注。
        # 旧写法 `name.split(" (")[0]` 把 "English (US)" / "English (UK)" 折成同一个
        # "English"，于是下面的反向表后写覆盖前写只剩 en_GB —— 用户点任一 English 都写回
        # en_GB、en_US 永远无法从 GUI 选择，且下拉里出现两个同名项（Web 面板却能选，两端不一致）。
        self._language_names: dict[str, str] = i18n_module.unique_display_names()
        # 显示名 → 语言码（unique_display_names 已保证值互不相同，故此表无覆盖风险）
        self._language_codes: dict[str, str] = {name: code for code, name in self._language_names.items()}
        self.language_menu = Menu(
            settings,
            values=list(self._language_names.values()),
            command=self._on_language_change,
            font=Fonts.small(),
        )
        self.language_menu.grid(row=3, column=1, sticky="ew", padx=(8, 4), pady=(0, 10))
        # 初始值：读 config.ini 的 language 键（空 → 系统语言，未识别/目录缺失 → en_US）
        try:
            _cfg = configparser.ConfigParser(interpolation=None)
            _cfg.read(self.main_config_file, encoding="utf-8-sig")
            _raw_lang = ""
            if _cfg.has_option("录制设置", "language"):
                _raw_lang = _cfg.get("录制设置", "language", fallback="")
        except Exception:
            _raw_lang = ""
        _norm_lang = i18n_module.resolve_language(_raw_lang)
        # 取 set_language 的返回值（**实际生效**的语言码）作为菜单初值，而不是请求值：
        # 二者只在「该语言目录缺失」时不同，显示请求值会让用户以为已切到那个语言。
        _effective_lang = i18n_module.set_language(_norm_lang)
        self.language_menu.set(
            self._language_names.get(_effective_lang, self._language_names[i18n_module.DEFAULT_LANGUAGE])
        )

        # 界面字体：[GUI] gui_font / gui_font_file。下拉给「系统默认 + 本机可用预设族 +
        # 已导入的自定义字体」，右侧「导入…」另辟一路装载私有字体文件。
        # 仍占半宽：侧栏底部每多一行就抬高窗口最小高，扩成整行会把「彻底退出」重新顶出
        # 矮窗口；族名可能被截断，但选完整窗立刻按新字体重排，用户不必靠名字认。
        _setting_label(2, 0, T("界面字体"))
        self._font_menu = Menu(settings, values=[], command=self._on_font_change, font=Fonts.small(), width=14)
        self._font_menu.grid(row=5, column=0, sticky="ew", padx=(4, 4), pady=(0, 10))
        Button(
            settings,
            text=T("导入字体…"),
            command=self._on_import_font,
            font=Fonts.small(),
            padding=(6, 5),
            variant="side_ghost",
        ).grid(row=5, column=1, sticky="ew", padx=(8, 4), pady=(0, 10))
        self._refresh_font_menu_values()

        # 两个动作按钮在设置网格**之后** pack（bottom 内部按 pack 顺序自上而下），
        # 故落在网格下方。
        Button(
            bottom,
            text=T("📥   最小化到托盘"),
            command=self.minimize_to_tray,
            font=Fonts.body(),
            variant="side_ghost",
        ).pack(fill=tk.X, pady=(12, 8))

        Button(
            bottom,
            text=T("❌   彻底退出"),
            command=self.quit_application,
            font=Fonts.body(bold=True),
            variant="side_danger",
        ).pack(fill=tk.X)

        return sidebar

    # 重建字体下拉取值（系统默认 → 本机可用的预设族 → 当前自定义字体）并回显。
    # 不留不可用项：Tk 对不可用 family 会静默回退到默认族（选了没反应），且失败时
    # 一行日志都不会有。
    def _refresh_font_menu_values(self) -> None:
        try:
            values: list[str] = [i18n_module.tr("系统默认")]
            for family in available_preset_families(self.root):
                if family not in values:
                    values.append(family)
            current = getattr(self, "_selected_font_family", "") or ""
            if current and current not in values:
                values.append(current)
            self._font_menu.configure(values=values)
            # 回显用 family_resolves 而不是 is_family_available：私有注册的自定义字体
            # 不出现在 Tk 的 families() 里（实测，见 ui_fonts.family_resolves 的注释），
            # 用后者会把已生效的自定义字体显示成「系统默认」。
            display = values[0]
            if current and family_resolves(current, self.root):
                display = current
            self._font_menu.set(display)
        except tk.TclError:
            return

    # 字体下拉选择回调：热应用到整窗 + 持久化。写回失败只告警不阻断（与主题/缩放
    # 同一口径：界面已经按新字体重绘了，写不回只是下次启动不记住）。
    def _on_font_change(self, choice: str) -> None:
        family = "" if choice == i18n_module.tr("系统默认") else choice
        try:
            self._apply_font_family(family)
        except Exception as e:
            logger.error(
                i18n_module.tr("应用字体失败: {type_name}: {err}", type_name=type(e).__name__, err=e),
                "error",
            )
            self._refresh_font_menu_values()
            return
        saved = False
        try:
            saved = save_font_preference(self.main_config_file, family, getattr(self, "_font_file_pref", ""))
        except Exception as e:
            logger.warning(
                i18n_module.tr(
                    "界面字体已调整为 {family}，但配置写回失败: {type_name}: {err}",
                    family=family or i18n_module.tr("系统默认"),
                    type_name=type(e).__name__,
                    err=e,
                ),
                "warn",
            )
            return
        if not saved:
            logger.warning(
                i18n_module.tr(
                    "界面字体已调整为 {family}，但配置写回失败", family=family or i18n_module.tr("系统默认")
                ),
                "warn",
            )

    # 「导入字体…」回调：选文件 → 复制到 config/fonts → 注册为进程私有字体 → 选中它。
    # woff2/woff 是 Web 传输格式，GDI 只认 SFNT（见 src/ui_fonts 模块头），故明确拒绝
    # 并给出可读原因，而不是「导入成功但没变化」。
    def _on_import_font(self) -> None:
        try:
            path = filedialog.askopenfilename(
                parent=self.root,
                title=i18n_module.tr("选择字体文件"),
                filetypes=[(i18n_module.tr("字体文件"), " ".join(f"*{s}" for s in SUPPORTED_FONT_SUFFIXES))],
            )
        except Exception:
            path = ""
        if not path:
            return
        if Path(path).suffix.lower() not in SUPPORTED_FONT_SUFFIXES:
            # 明确拒绝并给出原因：woff2 是网页传输格式、GDI 只认 SFNT（见 ui_fonts 模块头）
            messagebox.showwarning(
                i18n_module.tr("不支持的字体格式"),
                i18n_module.tr(
                    "仅支持 {formats} 字体文件；woff/woff2 是网页传输格式，请先转成 ttf/otf 再导入。",
                    formats="/".join(SUPPORTED_FONT_SUFFIXES),
                ),
            )
            return
        installed = install_font_file(path, self.app_root)
        if installed is None:
            messagebox.showwarning(
                i18n_module.tr("导入字体失败"),
                i18n_module.tr("无法读取或复制该字体文件，请确认文件未被占用且可读取。"),
            )
            return
        family = register_private_font(installed, self.root)
        if not family:
            messagebox.showwarning(
                i18n_module.tr("导入字体失败"),
                i18n_module.tr("系统无法加载该字体，可能是文件已损坏或系统不支持私有字体装载。"),
            )
            return
        self._font_file_pref = str(installed)
        self._apply_font_family(family)
        self._refresh_font_menu_values()
        try:
            save_font_preference(self.main_config_file, family, str(installed))
        except Exception as e:
            logger.warning(
                i18n_module.tr(
                    "界面字体已调整为 {family}，但配置写回失败: {type_name}: {err}",
                    family=family,
                    type_name=type(e).__name__,
                    err=e,
                ),
                "warn",
            )
        else:
            logger.info(i18n_module.tr("已导入并应用字体: {family}", family=family))

    # 向侧边栏添加一项导航按钮并绑定页面切换回调。
    def _add_nav_button(self, parent: Frame, page_id: str, text: str | Translatable) -> None:
        btn = Button(parent, text=text, command=lambda: self._show_page(page_id), font=Fonts.body(), variant="nav")
        btn.pack(fill=tk.X, pady=2)
        self._nav_buttons[page_id] = btn

    # 切换至指定页面并高亮对应导航按钮。页面滑入用 place 借用位移、终帧交回 grid
    # （不改变布局语义，见 ui_kit.slide_in）；动效关闭时同步落终态，不排 after。
    def _show_page(self, page_id: str) -> None:
        if page_id not in self._pages:
            return
        self._current_page = page_id
        page = self._pages[page_id]
        page.tkraise()
        for pid, btn in self._nav_buttons.items():
            if pid == page_id:
                btn.configure(style=font_style(NAV_ACTIVE_STYLE, Fonts.body(bold=True), btn))
            else:
                btn.configure(style=font_style(NAV_STYLE, Fonts.body(), btn))
        slide_in(
            page,
            self.motion,
            distance=self.scale_profile.px(PAGE_SLIDE_PX),
            duration_ms=190,
            job_key=f"page:{page_id}",
        )

    # 界面缩放菜单选择回调：换档 → 重建 ttk 主题（新 padding/rowheight）+ 原地改字号 +
    # 调整窗口与侧栏尺寸。即时生效、不重启、不丢运行态。
    def _on_scale_change(self, choice: str) -> None:
        raw_id = self._scale_ids_by_display.get(choice, AUTO_SCALE_ID)
        follow = raw_id == AUTO_SCALE_ID
        if follow:
            percent = auto_scale_for_screen(self.root.winfo_screenwidth(), self.root.winfo_screenheight())
        else:
            percent = int(raw_id)
        self._apply_scale(ScaleProfile(percent))
        try:
            # 「自动」写哨兵 id 而非空值：让用户下次进菜单仍看到自己选的是「自动」；
            # gui_theme 的「跟随系统」则写空值、靠菜单初值判断。两者都只影响菜单显示。
            saved = save_scale_preference(self.main_config_file, AUTO_SCALE_ID if follow else str(percent))
            if saved:
                self._log(i18n_module.tr("界面缩放已调整为 {percent}%", percent=percent))
            else:
                self._log(i18n_module.tr("界面缩放已调整为 {percent}%，但配置写回失败", percent=percent), "warn")
        except Exception as e:
            self._log(
                i18n_module.tr(
                    "界面缩放已调整为 {percent}%，但配置写回失败: {type_name}: {err}",
                    percent=percent,
                    type_name=type(e).__name__,
                    err=e,
                ),
                "warn",
            )
        self._scale_follow_system = follow

    # 把新档位落到运行态。拆成独立方法，使「菜单回调」只管偏好与日志，档位切换只有这一处实现。
    def _apply_scale(self, profile: ScaleProfile) -> None:
        self.scale_profile = profile
        # 1) 字号：改已缓存的 tkfont.Font 对象本身，引用它的控件自动重绘——重建控件树会
        #    清空日志内容、URL 编辑器未保存内容与两张监控表。
        Fonts.rescale_all(profile)
        # 2) ttk：主题名带档位段，重注册才能拿到新 padding/rowheight；派生字体样式缓存
        #    必须清（其名按旧档位的 padding 生成）。
        self.theme_manager.set_scale(profile)
        set_scale_percent(profile.percent)
        self.theme_manager.apply(self.root)
        # 3) 带字体的按钮要重新指向按新 padding 派生的样式（派生样式是创建时的快照）
        restyle_fonts(self.root)
        # 4) 窗口与侧栏几何：min 尺寸先落，避免 geometry 被旧 minsize 顶回。
        width, height, min_w, min_h = profile.window_size(self.root.winfo_screenwidth(), self.root.winfo_screenheight())
        self.root.minsize(min_w, min_h)
        self.root.geometry(f"{width}x{height}")
        self.root.grid_columnconfigure(0, minsize=profile.sidebar_width(), weight=0)
        # 5) tk 自绘件（Canvas 圆点、tk.Text 编辑器）随主题 token 重上色
        self._sync_theme_extras()
        # 6) 状态胶囊等固定像素高度的 Frame 不会自动跟档，需显式重设
        self._apply_scaled_geometry()
        # 7) 长文案的 wraplength 绑的是容器实宽，缩放后要重新结算一次
        for page in self._pages.values():
            page.update_idletasks()
        # 8) 换档后字号/边距都变了，需求宽随之变：重新抬窗口宽与 minsize 下限，
        #    否则升档后 root reqwidth 可能已反超 geometry（右边框裁切同根因）。
        self._raise_width_to_fit_content()

    # 固定像素高度的容器随档位重设。ttk.Frame 的 height 只在 pack_propagate(False)
    # 下生效，缩放后不重设就会出现「大字号被裁 / 小字号留白」两种错位。
    def _apply_scaled_geometry(self) -> None:
        s = self.scale_profile
        # [历史注] 此处原还有一项 close_dialog 的高度缩放，实际空转（属性名少了前导
        # 下划线恒取到 None，且基准值 0 会让 `and base` 短路）；关闭确认框高度由内容
        # pack 决定，故整项删除而不是把名字改对。
        for widget, base in ((getattr(self, "status_pill", None), 38),):
            # status_pill 是唯一需要按档缩放高度的固定高容器（其余卡片头高由
            # pack 内容决定，pack_propagate(False) 只在 status_pill 上开着）
            if widget is not None and base:
                try:
                    widget.configure(height=s.px(base))
                except tk.TclError:
                    pass

    # 动效强度菜单选择回调：改内存态等级 + 持久化。写回失败只告警不阻断（与主题/缩放
    # 同口径：界面已按新等级动起来了，配置写不回只是下次启动不记住）。
    def _on_motion_change(self, choice: str) -> None:
        motion_id = self._motion_ids_by_display.get(choice, FOLLOW_SYSTEM_MOTION_ID)
        follow = motion_id == FOLLOW_SYSTEM_MOTION_ID
        effective = self.motion.set_motion(
            effective_motion(
                "" if follow else motion_id,
                system_animations=detect_system_animations(),
            )
        )
        self._motion_follow_system = follow
        # 关掉动效必须立刻停掉在途的呼吸动画，否则用户关了它圆点还在跳。
        if effective == "off":
            self._stop_status_animation()
        self._ensure_motion_feedback()
        try:
            saved = save_motion_preference(self.main_config_file, FOLLOW_SYSTEM_MOTION_ID if follow else motion_id)
            if saved:
                self._log(i18n_module.tr("动效已切换为 {motion}", motion=effective))
            else:
                self._log(i18n_module.tr("动效已切换为 {motion}，但配置写回失败", motion=effective), "warn")
        except Exception as e:
            self._log(
                i18n_module.tr(
                    "动效已切换为 {motion}，但配置写回失败: {type_name}: {err}",
                    motion=effective,
                    type_name=type(e).__name__,
                    err=e,
                ),
                "warn",
            )

    # 系统关闭动画时，把菜单显示值与实际生效等级对齐并留一条日志：无障碍用户开了系统
    # 「关闭动画」后，选了「完整」却毫无反应，没有提示几乎必然被当成 bug。
    def _ensure_motion_feedback(self) -> None:
        if self.motion.motion_id != "off" or self._motion_follow_system:
            return
        if not detect_system_animations():
            if self.motion_menu.winfo_exists():
                self.motion_menu.set(i18n_module.tr(_MOTION_LABELS["off"]))
            self._log(i18n_module.tr("系统已关闭动画效果，动效强制为「关闭」"), "warn")

    # 界面主题菜单选择回调：内存态切换 + ttk 注册 + 持久化（「跟随系统」写空值 = 清空
    # 显式偏好）+ 根窗口底色 + 自绘控件重上色。写回失败只告警不阻断。
    def _on_theme_change(self, choice: str) -> None:
        theme_id = self._theme_ids_by_display.get(choice, _FOLLOW_SYSTEM_ID)
        follow = theme_id == _FOLLOW_SYSTEM_ID
        if follow:
            effective = self.theme_manager.select(detect_system_appearance())
        else:
            effective = self.theme_manager.select(theme_id)
        self.theme_manager.apply(self.root)
        try:
            if follow:
                # 写空值而非删键：load_theme_preference 对空值按「未设置」处理，行级写回
                # 同时保留注释与节顺序。
                saved = update_or_append_config_line(self.main_config_file, GUI_SECTION, THEME_KEY, "")
            else:
                saved = save_theme_preference(self.main_config_file, effective)
            if saved:
                self._log(i18n_module.tr("界面主题已切换: {theme}", theme=effective))
            else:
                self._log(
                    i18n_module.tr("界面主题已切换为 {theme}，但配置写回失败", theme=effective),
                    "warn",
                )
        except Exception as e:
            # 写回异常（磁盘/权限）不吞栈：带类型名与原因落日志（裸 {e} 在 Windows 超时类异常下是空串）
            self._log(
                i18n_module.tr(
                    "界面主题已切换为 {theme}，但配置写回失败: {type_name}: {err}",
                    theme=effective,
                    type_name=type(e).__name__,
                    err=e,
                ),
                "warn",
            )
        self._theme_follow_system = follow
        # 带字体的按钮重新指向派生样式：派生名按 (基础变体, 字体, 档位) 缓存，换主题后
        # 沿用旧派生样式会停留在旧主题的体量上。
        restyle_fonts(self.root)
        # 根窗口底色随主题 token；ttk 控件由全局样式重绘，tk 自绘件见 _sync_theme_extras。
        self._apply_root_chrome()
        self._sync_theme_extras()
        # M-77②：id 记账 + 连点主题时先取消上一支（否则同一轮排两支、后一支仍会在窗口销毁后
        # 触发，抛的 TclError 在窗口化构建下完全静默）。
        self._cancel_after_job(getattr(self, "_canvas_bg_job_id", None))
        self._canvas_bg_job_id = self.root.after(50, self._sync_canvas_bg)

    # 语言菜单选择回调：即时热切换翻译目录并持久化到 config.ini。
    def _on_language_change(self, choice: str) -> None:
        # 显示名 → 语言码（显示名由 i18n.unique_display_names 保证唯一，见 _build_sidebar）
        lang_code = self._language_codes.get(choice, i18n_module.DEFAULT_LANGUAGE)
        # set_language 返回**实际生效**的语言码：目录缺失（PyYAML 未装导致 zh_TW.yaml
        # 加载不了、发行包漏装 en_GB.json）时按 resolve_language 的口径回退。写回配置
        # 与提示都必须用回退后的码，否则 GUI 与录制子进程各说一种语言、「已切换」成虚假成功。
        effective = i18n_module.set_language(lang_code)
        # 界面重译：静态标签回填当前语言，动态面（状态栏/画质/弹幕/筛选哨兵）重建或重渲染。
        # 顺序必须先回填登记表再重置哨兵，否则 refresh 用旧语言哨兵比对会立刻把筛选菜单打回旧值。
        try:
            retranslate_all()
            self._quality_default_label = i18n_module.tr("默认画质")
            self._danmaku_filter = i18n_module.tr("全部房间")
            self._refresh_quality_context()
            self._update_status_bar()
            self._update_quality_display()
            self._update_danmaku_display()
            # 字体下拉首项是「系统默认」这条**译文**，不走 ui_i18n 登记表（Menu 的 values
            # 是控件自身取值），语言切换后必须重建取值与回显，否则会混着上一语言的首项。
            # 排在最后：纯回显刷新，失败不得挡住上面已有的状态刷新。
            self._refresh_font_menu_values()
        except Exception as e:
            # 重译失败不阻断语言切换本身（目录已切换、配置写回在下方）；仅记录现场
            self._log(
                i18n_module.tr(
                    "界面重译失败（当前语言 {lang}）: {type_name}: {err}",
                    lang=effective,
                    type_name=type(e).__name__,
                    err=e,
                ),
                "warn",
            )
        # 写回 config.ini（行级更新保留注释；失败仅告警，不影响内存态切换）
        try:
            if not update_config_line(self.main_config_file, "录制设置", "language", effective):
                self._log(
                    i18n_module.tr("语言已切换为 {lang}，但配置写回失败：未找到 language 配置行", lang=effective),
                    "warn",
                )
            elif effective != lang_code:
                self._log(
                    i18n_module.tr(
                        "{lang} 的翻译目录不可用，已回退为 {effective}（配置同样按 {effective} 写回）",
                        lang=lang_code,
                        effective=effective,
                    ),
                    "warn",
                )
            else:
                self._log(i18n_module.tr("语言已切换: {lang}（录制子进程重启后同步生效）", lang=effective))
        except Exception as e:
            self._log(i18n_module.tr("语言已切换为 {lang}，但配置写回失败: {err}", lang=effective, err=e), "warn")

    # 根窗口底色随主题 token：ttk 内容区铺满两列，root 底色只在缝隙可见，取 surface
    # 与侧边栏同槽。
    def _apply_root_chrome(self) -> None:
        try:
            self.root.configure(bg=self.theme_manager.tokens()["surface"])
        except tk.TclError:
            pass

    # 主题切换后同步自绘控件（Canvas 圆点 / Treeview 行标记 / tk.Text 编辑器）。
    # ttk 控件由全局样式自绘，只剩这三类 tk 控件需要显式跟随。
    def _sync_theme_extras(self) -> None:
        tokens = self.theme_manager.tokens()
        self._sync_dot_bg()
        self._sync_big_dot_bg()
        self._sync_table_tags(tokens)
        self.config_text.restyle(tokens)
        if self._adv_settings_window is not None:
            # 高级设置窗口打开期间切主题：编辑器同为 tk.Text，一并跟随（其余部分为 ttk，
            # 随全局样式重绘）。
            self._adv_settings_window.config_text.restyle(tokens)

    # 主题切换后延迟重取 Canvas 圆点底色（after(50) 的入口）。
    def _sync_canvas_bg(self) -> None:
        # 回调既已触发，id 就作废：留着会让下一次取消打到一支早已跑完的 job 上。
        self._canvas_bg_job_id = None
        self._sync_dot_bg()
        self._sync_big_dot_bg()

    def _sync_dot_bg(self) -> None:
        try:
            # 圆点画在状态胶囊（surface_alt）里，画布底色必须与胶囊同槽
            self._sidebar_dot.configure(bg=self.theme_manager.tokens()["surface_alt"])
        except Exception:
            pass

    # 构建右侧内容区并叠放五个页面（控制台 / 画质 / 弹幕 / URL 配置 / 运行日志，tkraise 切换）。
    def _build_content(self) -> None:
        container = Frame(self.root, variant="alt")
        container.grid(row=0, column=1, sticky="nsew")
        container.grid_columnconfigure(0, weight=1)
        container.grid_rowconfigure(0, weight=1)

        self._pages["dashboard"] = self._build_dashboard_page(container)
        self._pages["quality"] = self._build_quality_page(container)
        self._pages["danmaku"] = self._build_danmaku_page(container)
        self._pages["config"] = self._build_config_page(container)
        self._pages["logs"] = self._build_logs_page(container)

        for page in self._pages.values():
            page.grid(row=0, column=0, sticky="nsew", padx=20, pady=20)

    # 给两张监控表上/换行级标记颜色（构建时与主题切换时共用）。Treeview 的 tag 是行级的：
    # 降级行整行红字 + 浅红底（_mix 派生自 danger/surface，不引入第二套手写色）；断连行
    # 整行淡化为 muted。逐列着色在 Treeview 下不可表达，✓/⚠ 字形保留状态语义。
    def _sync_table_tags(self, tokens: dict[str, str]) -> None:
        soft_danger = _mix(tokens["danger"], tokens["surface"], 0.9)
        self._quality_table.restyle_tags(
            {
                TAG_NORMAL: {"foreground": tokens["text"], "background": tokens["surface_alt"]},
                "downgraded": {
                    "foreground": tokens["danger"],
                    "background": soft_danger,
                    "font": Fonts.body(bold=True),
                },
            }
        )
        self._dm_table.restyle_tags(
            {
                TAG_NORMAL: {"foreground": tokens["text"], "background": tokens["surface_alt"]},
                "disconnected": {"foreground": tokens["text_muted"], "background": tokens["surface_alt"]},
            }
        )

    # 创建带可选标题的圆角卡片容器，返回卡片 Frame。
    def _create_card(self, parent: Frame, title: str | Translatable = "") -> Frame:
        card = Frame(parent, variant="card")
        if title:
            header = Frame(card, height=46)
            header.pack(fill=tk.X)
            header.pack_propagate(False)
            Label(header, text=title, font=Fonts.body(bold=True)).pack(side=tk.LEFT, padx=18, pady=12)
        return card

    # ─── 页面：控制台 ───────────────────────────────────────

    # 构建控制台页：状态总览、录制控制与快捷操作卡片。
    def _build_dashboard_page(self, parent: Frame) -> Frame:
        page = Frame(parent)
        page.grid_columnconfigure(0, weight=1)
        page.grid_rowconfigure(0, weight=0)
        page.grid_rowconfigure(1, weight=0)
        page.grid_rowconfigure(2, weight=1)

        # ── 状态总览卡片 ──
        status_card = self._create_card(page)
        status_card.grid(row=0, column=0, sticky="ew", pady=(0, 14))
        status_card.grid_columnconfigure(1, weight=1)

        # 左侧大圆点（呼吸动画）
        dot_wrap = Frame(status_card, width=90, height=90)
        dot_wrap.grid(row=0, column=0, padx=(20, 6), pady=22)
        dot_wrap.grid_propagate(False)
        self._big_dot = tk.Canvas(dot_wrap, width=64, height=64, highlightthickness=0, bd=0)
        self._big_dot.place(relx=0.5, rely=0.5, anchor=tk.CENTER)
        self._big_dot_item = self._big_dot.create_oval(8, 8, 56, 56, fill=Colors.DANGER, outline="")
        self._sync_big_dot_bg()

        # 中间：状态文字（运行态被 _update_status_bar 周期改写，建时 tr 不登记重译）
        mid = Frame(status_card)
        mid.grid(row=0, column=1, sticky="w", pady=18)
        self.big_status_label = Label(mid, text=i18n_module.tr("待 机"), font=Fonts.big_status())
        self.big_status_label.pack(anchor=tk.W)
        self.big_status_sub = Label(mid, text=i18n_module.tr("录制进程未运行"), font=Fonts.body(), variant="muted")
        self.big_status_sub.pack(anchor=tk.W, pady=(2, 0))

        # 右侧：信息网格（2 列 x 2 行）
        info = Frame(status_card)
        info.grid(row=0, column=2, padx=24, pady=18, sticky="e")

        self.info_interval = self._add_info_item(info, T("循环检测"), "-", 0, 0)
        self.info_format = self._add_info_item(info, T("输出格式"), "-", 0, 1)
        self.info_tray = self._add_info_item(info, T("系统托盘"), "-", 1, 0)
        self.info_time = self._add_info_item(info, T("当前时间"), "-", 1, 1)

        # ── 录制控制卡片 ──
        ctrl_card = self._create_card(page, T("录制控制"))
        ctrl_card.grid(row=1, column=0, sticky="ew", pady=(0, 14))

        ctrl_body = Frame(ctrl_card)
        ctrl_body.pack(fill=tk.X, padx=18, pady=(0, 16))

        self.start_btn = Button(
            ctrl_body,
            text=T("▶   开始录制"),
            command=self.start_recording,
            font=Fonts.heading(),
            padding=(24, 11),
            variant="success",
        )
        self.start_btn.pack(side=tk.LEFT, padx=(0, 12))

        self.stop_btn = Button(
            ctrl_body,
            text=T("⏹   停止录制"),
            command=self.stop_recording,
            font=Fonts.heading(),
            padding=(24, 11),
            variant="danger",
            state=tk.DISABLED,
        )
        self.stop_btn.pack(side=tk.LEFT)

        # fill+expand 让标签窗口 = 按钮行右侧剩余宽（由 packer 分配，是自适应换行的前提）。
        # 初始 wraplength 必须给非零小值：缺省 0 = 不折行，标签按单行全文计入窗口
        # reqwidth（本标签单行 ~725px），会把 root reqwidth 撑过 geometry，Tk grid 对超宽
        # slave 裁切而非收缩——卡片右边框连同右边距被整段切掉。初值只影响首帧前的需求宽
        # 计算，布局分配后由 _bind_adaptive_wraplength 按实宽改写。
        hint_label = Label(
            ctrl_body,
            text=T("启动后将调用 main.py 循环监测 URL 配置中的直播间并自动录制"),
            font=Fonts.small(),
            variant="muted",
            anchor=tk.W,
            justify=tk.LEFT,
            wraplength=self.scale_profile.px(320),
        )
        hint_label.pack(side=tk.LEFT, padx=20, fill=tk.X, expand=True)
        _bind_adaptive_wraplength(hint_label)

        # ── 快捷操作卡片 ──
        quick_card = self._create_card(page, T("快捷操作"))
        quick_card.grid(row=2, column=0, sticky="new")

        quick_body = Frame(quick_card)
        quick_body.pack(fill=tk.X, padx=18, pady=(0, 16))

        Button(
            quick_body,
            text=T("📂   打开下载目录"),
            command=self.open_downloads_folder,
            font=Fonts.body(),
            padding=(14, 8),
            variant="ghost",
        ).pack(side=tk.LEFT, padx=(0, 10))

        Button(
            quick_body,
            text=T("⚙   高级设置"),
            command=self.open_advanced_settings,
            font=Fonts.body(),
            padding=(14, 8),
            variant="ghost",
        ).pack(side=tk.LEFT)

        return page

    # 在状态卡片添加一项信息（标签 + 值），返回值标签以便后续更新。
    def _add_info_item(self, parent: Frame, label: str | Translatable, value: str, row: int, col: int) -> Label:
        box = Frame(parent)
        box.grid(row=row, column=col, padx=16, pady=6, sticky="w")
        Label(box, text=label, font=Fonts.small(), variant="muted").pack(anchor=tk.W)
        val = Label(box, text=value, font=Fonts.body(bold=True))
        val.pack(anchor=tk.W)
        return val

    # 同步控制台大状态圆点的画布背景色（Canvas 不随主题自动变化）。
    def _sync_big_dot_bg(self) -> None:
        try:
            # 大圆点画在控制台状态卡片（surface）上
            self._big_dot.configure(bg=self.theme_manager.tokens()["surface"])
        except Exception:
            pass

    # ─── 页面：URL 配置 ─────────────────────────────────────

    # 构建 URL 配置编辑页（文本编辑器 + 重新读取 / 保存按钮）。
    def _build_config_page(self, parent: Frame) -> Frame:
        page = Frame(parent)
        page.grid_columnconfigure(0, weight=1)
        page.grid_rowconfigure(0, weight=1)

        card = self._create_card(page, T("📝  URL 配置编辑区 (config/URL_config.ini)"))
        card.grid(row=0, column=0, sticky="nsew")

        # 编辑器
        editor_wrap = Frame(card)
        editor_wrap.pack(fill=tk.BOTH, expand=True, padx=14, pady=(0, 6))

        self.config_text = EditorText(
            editor_wrap,
            tokens=self.theme_manager.tokens(),
            font=Fonts.mono(),
            pad_x=self.scale_profile.spacing("md"),
            pad_y=self.scale_profile.spacing("sm"),
        )
        self.config_text.pack(fill=tk.BOTH, expand=True)

        # 提示：同控制台/画质提示——初始 wraplength 非零小值 + 自适应绑定，否则单行全文
        # （~820px）计入窗口 reqwidth，Tk grid 赤字时裁切页面右缘。
        config_hint_label = Label(
            card,
            text=T(
                "每行一个直播链接，支持 # 开头的注释行  │  外部修改文件后将自动重新加载  │  点击窗口关闭按钮将最小化到系统托盘"
            ),
            font=Fonts.small(),
            variant="muted",
            anchor=tk.W,
            wraplength=self.scale_profile.px(320),
        )
        config_hint_label.pack(fill=tk.X, padx=18, pady=(4, 4))
        _bind_adaptive_wraplength(config_hint_label)

        # 操作按钮
        btn_row = Frame(card)
        btn_row.pack(fill=tk.X, padx=14, pady=(4, 14))

        self.reload_btn = Button(
            btn_row,
            text=T("🔄   重新读取"),
            command=self._load_config,
            font=Fonts.body(),
            padding=(14, 7),
            variant="ghost",
        )
        self.reload_btn.pack(side=tk.RIGHT, padx=(8, 0))

        self.save_btn = Button(
            btn_row,
            text=T("💾   保存 URL 配置"),
            command=self.save_config,
            font=Fonts.body(bold=True),
            padding=(14, 7),
        )
        self.save_btn.pack(side=tk.RIGHT)

        return page

    # ─── 页面：运行日志 ─────────────────────────────────────

    # 构建运行日志页（终端风格文本框 + 清空日志按钮）。
    def _build_logs_page(self, parent: Frame) -> Frame:
        page = Frame(parent)
        page.grid_columnconfigure(0, weight=1)
        page.grid_rowconfigure(0, weight=1)

        card = self._create_card(page, T("📋  运行日志 (main.py 输出)"))
        card.grid(row=0, column=0, sticky="nsew")

        # 终端容器（tk.Frame + tk.Text + ttk 滚动条；配色是刻意的主题无关常量）
        term_wrap, self.log_text = terminal_text(
            card,
            font=Fonts.mono(),
            bg=Colors.TERMINAL_BG,
            fg=Colors.TERMINAL_FG,
            select_bg=Colors.TERMINAL_SELECT,
            # 内边距随档位：tk.Text 的 padx/pady 是裸像素，不吃 ttk 样式
            pad_x=self.scale_profile.spacing("md"),
            pad_y=self.scale_profile.spacing("sm"),
        )
        term_wrap.pack(fill=tk.BOTH, expand=True, padx=14, pady=(0, 6))

        self.log_text.tag_config("error", foreground=Colors.TERMINAL_ERROR)
        self.log_text.tag_config("warn", foreground=Colors.TERMINAL_WARN)

        # 底部操作栏
        btn_row = Frame(card)
        btn_row.pack(fill=tk.X, padx=14, pady=(4, 14))

        Button(
            btn_row,
            text=T("🗑   清空日志"),
            command=self._clear_log,
            font=Fonts.body(),
            padding=(12, 6),
            variant="ghost",
        ).pack(side=tk.RIGHT)

        Label(
            btn_row,
            text=T("日志超过 1000 行将自动截断"),
            font=Fonts.small(),
            variant="muted",
        ).pack(side=tk.LEFT, padx=6)

        return page

    # ─── 页面：画质监控 ─────────────────────────────────────

    # 构建画质监控页（统计卡片 + Treeview 实时详情表）。
    # 空状态占位工厂：占位与表格叠放同格、按行数切换可见性，不再每轮刷新重建；文案各持
    # 一份。fill/sticky=ew 让标签窗口 = 容器分配宽，配合 _bind_adaptive_wraplength 自动折行。

    def _make_quality_placeholder(self, parent: tk.Misc) -> Label:
        label = Label(
            parent,
            text=T("暂无录制中的直播间\n\n启动录制后，将自动检测各直播间的实际画质是否与设置一致"),
            font=Fonts.body(),
            variant="muted",
            justify=tk.CENTER,
        )
        label.grid(row=0, column=0, sticky="ew", pady=60)
        _bind_adaptive_wraplength(label)
        return label

    def _make_danmaku_placeholder(self, parent: tk.Misc) -> Label:
        label = Label(
            parent,
            text=T(
                "暂无弹幕监控数据\n\n启动录制并在 config.ini 开启「是否弹幕监控(是/否)」后，"
                "支持弹幕的平台（斗鱼/B站/虎牙/抖音/Twitch）将显示实时弹幕"
            ),
            font=Fonts.body(),
            variant="muted",
            justify=tk.CENTER,
        )
        label.grid(row=0, column=0, sticky="ew", pady=30)
        _bind_adaptive_wraplength(label)
        return label

    def _build_quality_page(self, parent: Frame) -> Frame:
        page = Frame(parent)
        page.grid_columnconfigure(0, weight=1)
        page.grid_rowconfigure(1, weight=1)

        # 统计卡片
        summary_card = self._create_card(page)
        summary_card.grid(row=0, column=0, sticky="ew", pady=(0, 14))

        summary_body = Frame(summary_card)
        summary_body.pack(fill=tk.X, padx=18, pady=16)
        summary_body.grid_columnconfigure((0, 1, 2), weight=1)

        self._q_stat_total = self._add_stat_item(summary_body, T("录制中"), "0", 0, "primary")
        self._q_stat_ok = self._add_stat_item(summary_body, T("画质正常"), "0", 1, "success")
        self._q_stat_down = self._add_stat_item(summary_body, T("画质降级"), "0", 2, "danger")

        # 详情卡片
        detail_card = self._create_card(page, T("🎯  画质监控（实时检测实际画质是否与设置一致）"))
        detail_card.grid(row=1, column=0, sticky="nsew")

        inner = Frame(detail_card)
        inner.pack(fill=tk.BOTH, expand=True, padx=14, pady=(0, 14))

        # 画质可选项与「主播名 → 直播间地址」反查表首次构建时加载一次
        self._refresh_quality_context()

        # 表格区（DataTable 行级增量更新）
        table_area = Frame(inner)
        table_area.pack(fill=tk.BOTH, expand=True, pady=(0, 6))
        table_area.grid_rowconfigure(0, weight=1)
        table_area.grid_columnconfigure(0, weight=1)

        self._quality_table = DataTable(
            table_area,
            [
                ("name", T("主播名称"), 3, tk.W),
                ("set_quality", T("设置画质"), 1, tk.W),
                ("actual", T("实际画质"), 1, tk.W),
                ("status", T("状态"), 1, tk.W),
                ("alert_time", T("告警时间"), 2, tk.W),
                ("switch", T("切换画质"), 2, tk.W),
            ],
        )
        # 行内「切换画质」浮层编辑器：行数据在 sync 时缓存（_quality_row_setq），点该列在
        # 单元格 bbox 上弹 readonly 下拉，选中即走 _on_room_quality_change。
        self._quality_row_setq = {}
        self._quality_table.bind_cell_editor(
            "switch",
            values_for=lambda name: self._quality_menu_values(self._quality_row_setq.get(name, "")),
            initial_for=lambda name: self._quality_row_setq.get(name, "") or self._quality_default_label,
            on_commit=self._on_room_quality_change,
            font=Fonts.small(),
        )
        self._quality_table.tree.grid(row=0, column=0, sticky="nsew")

        # 空态占位与表格叠放同格，按行数切换可见性（grid_remove 保留 grid 配置）
        self._quality_placeholder = self._make_quality_placeholder(table_area)
        self._quality_placeholder.grid_remove()

        # 定宽 wraplength=1000 在窄窗口下会被 pack 两侧裁切（标签请求宽超出容器分配宽），
        # 改为绑容器实宽的自适应折行。
        quality_hint_label = Label(
            inner,
            text=T(
                "「切换画质」选中非默认画质时，会以「画质,直播间地址」格式写回 config/URL_config.ini，"
                "在下一轮检测循环（默认 120 秒）自动生效；选择「默认画质」则移除该行画质段、回落到全局默认画质。"
            ),
            font=Fonts.small(),
            variant="muted",
            anchor=tk.W,
            justify=tk.LEFT,
            # [2026-10-17] 初始 wraplength 非零小值：缺省 0 会把单行全文（~820px）计入
            # 窗口 reqwidth，撑爆 geometry 后 Tk grid 裁切页面右缘（见控制台提示同款注释）
            wraplength=self.scale_profile.px(320),
        )
        quality_hint_label.pack(fill=tk.X, pady=(0, 10))
        _bind_adaptive_wraplength(quality_hint_label)

        # 初始空状态
        self._show_quality_placeholder(True)

        return page

    # 空态占位与表格互斥显示（构建时与每轮刷新共用；grid_remove 不销毁配置）。
    def _show_quality_placeholder(self, visible: bool) -> None:
        if visible:
            self._quality_table.tree.grid_remove()
            self._quality_placeholder.grid()
        else:
            self._quality_placeholder.grid_remove()
            self._quality_table.tree.grid()

    # 在统计卡片添加一项统计（标签 + 值），返回值标签（画质/弹幕监控页共用）。
    # variant 为 ui_kit 标签变体名（"primary"/"success"/"danger"），颜色由 ui_theme 槽位派生。
    def _add_stat_item(self, parent: Frame, label: str | Translatable, value: str, col: int, variant: str) -> Label:
        box = Frame(parent)
        box.grid(row=0, column=col, padx=10, pady=4, sticky="ew")
        box.grid_columnconfigure(0, weight=1)
        Label(box, text=label, font=Fonts.small(), variant="muted").pack(anchor=tk.CENTER)
        # 统计数值用 stat 档（title 档会让数值与控制台大状态抢层级）
        val = Label(box, text=value, font=Fonts.stat(), variant=variant)
        val.pack(anchor=tk.CENTER, pady=(2, 0))
        return val

    # 重新加载「切换画质」所需的上下文：可选画质（config.ini）+ 主播名 → URL 反查表
    # （URL_config.ini）。两者都随配置文件变化，故在首次构建画质页与 URL 配置被重载时调用。
    def _refresh_quality_context(self) -> None:
        try:
            self._quality_options = read_quality_options(self.main_config_file)
        except Exception as e:
            # 配置读取失败不应阻断页面构建：退化为无可选画质（菜单只剩「默认画质」）
            self._log(i18n_module.tr("读取画质选项失败: {err}", err=e), "error")
            self._quality_options = []
        try:
            rooms = parse_url_config(self.url_config_file)
            named = [r for r in rooms if str(r["name"]).strip()]
            self._anchor_url_map = {str(r["name"]).strip(): str(r["url"]) for r in named}
            self._anchor_quality_map = {str(r["name"]).strip(): str(r["quality"]) for r in named}
        except Exception as e:
            self._log(i18n_module.tr("解析 URL 配置失败: {err}", err=e), "error")
            self._anchor_url_map = {}
            self._anchor_quality_map = {}

    # 供「切换画质」菜单使用：返回「默认画质 + 用户自选档位」的展示列表。
    def _quality_menu_values(self, current: str) -> list[str]:
        values = [self._quality_default_label, *self._quality_options]
        # 当前画质可能已被用户从选项列表中移除，仍需在菜单里可见，否则显示值会错位到首项
        if current and current not in values:
            values.insert(1, current)
        return values

    # 用户切换某直播间画质：非默认画质按「画质,URL」写回 URL_config.ini，默认画质则移除画质段。
    def _on_room_quality_change(self, anchor_name: str, selected: str) -> None:
        # 行名来自子进程日志（record_name = "序号N 主播名"），反查表键为 URL_config.ini 中的
        # 纯主播名，查表前须剥离序号前缀，否则必然查不到（表现为「找不到…画质未修改」）。
        key = re.sub(r"^序号\d+\s+", "", anchor_name).strip()
        url = self._anchor_url_map.get(key, "")
        if not url:
            self._log(
                i18n_module.tr(
                    "未能在 URL_config.ini 中找到「{anchor_name}」对应的直播间地址，画质未修改", anchor_name=anchor_name
                ),
                "error",
            )
            messagebox.showerror(
                i18n_module.tr("切换画质失败"),
                i18n_module.tr(
                    "未能在 config/URL_config.ini 中找到「{anchor_name}」对应的直播间地址", anchor_name=anchor_name
                ),
            )
            return
        # 菜单首项「默认画质」= 不写画质段，回落到全局默认画质。
        # Menu.set() 只改显示值、不触发 command，故表格回设当前画质不会误写配置。
        new_quality = "" if selected == self._quality_default_label else selected
        # update_room_quality 本身是行级的读-改-写、不会整文件覆盖，但紧随其后的
        # _load_config() 会用磁盘内容重建编辑器，用户尚未保存的整页编辑因此被静默丢弃。
        # 写盘前先交用户裁决（判据与 _watch_url_config 的脏检查同源）。
        if self._has_unsaved_config_edits() and not messagebox.askyesno(
            i18n_module.tr("配置文件已变更"),
            i18n_module.tr(
                "直播间配置编辑器中有尚未保存的更改，切换画质会重新加载文件并丢弃这些更改。\n\n"
                "点击「是」放弃未保存的更改并继续切换画质；\n点击「否」取消本次画质切换。"
            ),
        ):
            self._log(i18n_module.tr("已取消画质切换：URL 配置编辑器中有未保存的更改"), "warn")
            return
        try:
            changed = update_room_quality(self.url_config_file, url, new_quality)
        except (OSError, ValueError) as e:
            self._log(i18n_module.tr("切换「{anchor_name}」画质失败: {err}", anchor_name=anchor_name, err=e), "error")
            # 标题与正文一并走 tr（messagebox 不在 i18n 提取器扫描范围内）
            messagebox.showerror(
                i18n_module.tr("切换画质失败"), i18n_module.tr("写入 config/URL_config.ini 失败：{e}", e=e)
            )
            return
        # 写回成功后重载编辑器：config_text 若仍持有写回前的旧快照，用户点「保存」会把
        # 画质段覆盖回旧内容（表现为切换「失效」）。_load_config 内部会同步 mtime（避免
        # _watch_url_config 重复触发）、刷新编辑器并重建反查表/画质映射。
        self._load_config()
        if changed:
            tip = i18n_module.tr(
                "「{anchor_name}」画质已切换为 {selected}，将在下一轮检测循环生效",
                anchor_name=anchor_name,
                selected=selected,
            )
            self._log(tip)
        else:
            self._log(
                i18n_module.tr(
                    "「{anchor_name}」画质未发生变化（已是 {selected}）", anchor_name=anchor_name, selected=selected
                )
            )

    # ─── 页面：弹幕监控 ─────────────────────────────────────

    # 构建弹幕监控页（统计卡片 + Treeview 房间明细表 + 终端风格实时弹幕流）。
    def _build_danmaku_page(self, parent: Frame) -> Frame:
        # 弹幕监控页面：数据来自 tail 线程解析 logs/danmaku_monitor.jsonl
        page = Frame(parent)
        page.grid_columnconfigure(0, weight=1)
        page.grid_rowconfigure(0, weight=0)
        page.grid_rowconfigure(1, weight=0)
        page.grid_rowconfigure(2, weight=1)

        # 统计卡片
        summary_card = self._create_card(page)
        summary_card.grid(row=0, column=0, sticky="ew", pady=(0, 14))

        summary_body = Frame(summary_card)
        summary_body.pack(fill=tk.X, padx=18, pady=16)
        summary_body.grid_columnconfigure((0, 1, 2), weight=1)

        self._dm_stat_rooms = self._add_stat_item(summary_body, T("监控房间"), "0", 0, "primary")
        self._dm_stat_connected = self._add_stat_item(summary_body, T("已连接"), "0", 1, "success")
        self._dm_stat_msgs = self._add_stat_item(summary_body, T("累计弹幕"), "0", 2, "primary")

        # 房间明细卡片（DataTable 行级增量更新）
        detail_card = self._create_card(page, T("💬  弹幕房间（连接状态 / 累计弹幕 / 速率 / 礼物）"))
        detail_card.grid(row=1, column=0, sticky="ew", pady=(0, 14))

        inner = Frame(detail_card)
        inner.pack(fill=tk.BOTH, expand=True, padx=14, pady=(0, 14))
        inner.grid_rowconfigure(0, weight=1)
        inner.grid_columnconfigure(0, weight=1)

        self._dm_table = DataTable(
            inner,
            [
                ("room", T("房间"), 3, tk.W),
                ("platform", T("平台"), 2, tk.W),
                ("status", T("状态"), 1, tk.W),
                ("msg_total", T("累计弹幕"), 1, tk.E),
                ("msg_rate", T("速率(条/分)"), 1, tk.E),
                ("gift_total", T("礼物"), 1, tk.E),
                ("online", T("在线"), 1, tk.E),
                ("started_at", T("开始时间"), 2, tk.W),
            ],
        )
        self._dm_table.tree.grid(row=0, column=0, sticky="nsew")

        # 空态占位与表格叠放同格，按行数切换可见性（构建时占位可见）
        self._dm_placeholder = self._make_danmaku_placeholder(inner)
        self._show_danmaku_placeholder(True)

        # 实时弹幕流卡片
        stream_card = self._create_card(page, T("📋  实时弹幕"))
        stream_card.grid(row=2, column=0, sticky="nsew")

        stream_inner = Frame(stream_card)
        stream_inner.pack(fill=tk.BOTH, expand=True, padx=14, pady=(0, 14))

        # 工具栏：房间筛选 + 清空
        toolbar = Frame(stream_inner)
        toolbar.pack(fill=tk.X, pady=(0, 8))

        self._dm_filter_menu = Menu(
            toolbar,
            # 筛选菜单初值走 tr（值列表会被 _update_danmaku_display 周期重建，不登记重译）
            values=[i18n_module.tr("全部房间")],
            command=self._on_danmaku_filter_change,
            font=Fonts.small(),
            width=14,
        )
        self._dm_filter_menu.pack(side=tk.LEFT)
        self._dm_filter_menu.set(i18n_module.tr("全部房间"))

        Button(
            toolbar,
            text=T("🗑   清空"),
            command=self._clear_danmaku,
            font=Fonts.small(),
            padding=(10, 5),
            variant="ghost",
        ).pack(side=tk.RIGHT)

        Label(
            toolbar,
            text=T("高频房间弹幕按每秒 10 条采样展示，统计计数始终精确"),
            font=Fonts.small(),
            variant="muted",
        ).pack(side=tk.RIGHT, padx=(0, 12))

        # 终端容器（tk.Frame + tk.Text + ttk 滚动条；配色是刻意的主题无关常量）
        term_wrap, self.danmaku_text = terminal_text(
            stream_inner,
            font=Fonts.mono(),
            bg=Colors.TERMINAL_BG,
            fg=Colors.TERMINAL_FG,
            select_bg=Colors.TERMINAL_SELECT,
            pad_x=self.scale_profile.spacing("md"),
            pad_y=self.scale_profile.spacing("sm"),
        )
        term_wrap.pack(fill=tk.BOTH, expand=True)

        # 弹幕类型着色：普通弹幕用默认前景，礼物黄色，SC 粉色，采样折叠灰斜体
        self.danmaku_text.tag_config("gift", foreground=Colors.TERMINAL_WARN)
        self.danmaku_text.tag_config("superChat", foreground="#DB61A2")
        # 等宽斜体用 Font 对象：元组是快照，不随缩放变
        self.danmaku_text.tag_config("dropped", foreground="#8B949E", font=Fonts.mono_italic())

        return page

    # 空态占位与表格互斥显示（与画质页同款；grid_remove 不销毁配置）。
    def _show_danmaku_placeholder(self, visible: bool) -> None:
        if visible:
            self._dm_table.tree.grid_remove()
            self._dm_placeholder.grid()
        else:
            self._dm_placeholder.grid_remove()
            self._dm_table.tree.grid()

    # 筛选下拉变化：立即重绘弹幕流。
    def _on_danmaku_filter_change(self, choice: str) -> None:
        with self._danmaku_lock:
            self._danmaku_filter = choice
            self._danmaku_stream_dirty = True
        self._render_danmaku_stream()

    # 清空弹幕流显示。
    def _clear_danmaku(self) -> None:
        with self._danmaku_lock:
            self._danmaku_msgs.clear()
            self._danmaku_stream_dirty = True
        self._render_danmaku_stream()

    # 清空运行日志文本框内容。
    def _clear_log(self) -> None:
        self.log_text.config(state=tk.NORMAL)
        self.log_text.delete("1.0", tk.END)
        self.log_text.config(state=tk.DISABLED)

    # ─── 表格变化行高亮（动效） ────────────────────────────

    # 变化行高亮：sync 返回本轮变化的行，逐帧把背景色从「高亮」混回「常态」；动效关闭时
    # sync 落终态（直接摘 tag）。高亮取 primary 而非 success/danger——高亮表达的是「这一行
    # 刚变了」，好坏已由 downgraded/disconnected 两个 tag 表达，复用语义色会混淆。
    def _highlight_changed_rows(self, table: DataTable, changed: list[str]) -> None:
        if not changed:
            # 无变化轮零开销：不排 after、不动 tag（这是「未变化轮零触碰」的延伸）
            return
        tokens = self.theme_manager.tokens()
        base_color = tokens["surface_alt"]
        # 高亮取 primary 与 surface_alt 的中间色：既明显可辨，又不与降级红/断连灰撞色
        highlight_color = blend(tokens["primary"], base_color, 0.78)

        def _apply(frame_keys: list[str], color: str) -> None:
            table.highlight_rows(frame_keys, tag="flash", colors={"background": color})

        def _clear(_progress: float = 0.0) -> None:
            # 末帧摘 tag：传空 colors 让 highlight_rows 进入「摘除」分支
            table.highlight_rows(changed, tag="flash", colors={})

        self.motion.run_frames(
            self.root,
            f"rows:{id(table)}",
            lambda progress: _apply(changed, blend(highlight_color, base_color, progress)),
            duration_ms=ROW_HIGHLIGHT_MS,
            frames=ROW_HIGHLIGHT_FRAMES,
            # 末帧必须显式摘掉 flash tag：末帧颜色已等于常态底色，但 tag 仍在，
            # 下一轮 sync 改tags 时会因「多了一个 tag」被判成变化而误触高亮，
            # 形成「每轮都闪一下」的自激循环。
            on_done=_clear,
        )

    # ─── 状态指示器动画 ─────────────────────────────────────

    # 启动大状态圆点的呼吸式动画（若未在运行）。动效等级为 off 时不启动：呼吸是 120ms
    # 一帧的常驻 after 链，是本窗口唯一「界面静止也在重绘」的来源，低性能设备上必须可关。
    def _start_status_animation(self) -> None:
        if self._status_animating or not self.motion.enabled:
            return
        self._status_animating = True
        self._status_anim_index = 0
        self._animate_status_dot()

    # 停止状态指示器动画并取消定时回调。
    def _stop_status_animation(self) -> None:
        self._status_animating = False
        if self._status_anim_timer is not None:
            try:
                self.root.after_cancel(self._status_anim_timer)
            except Exception:
                pass
            self._status_anim_timer = None

    # 状态圆点呼吸动画的单帧回调（大小 + 亮度往返渐变）。
    def _animate_status_dot(self) -> None:
        if not self._status_animating:
            return
        sizes = [40, 42, 44, 46, 48, 46, 44, 42, 40]
        idx = self._status_anim_index % len(sizes)
        s = sizes[idx]
        offset = 32 - s // 2
        # 呼吸亮度：在 SUCCESS 与亮绿之间往返渐变（ping-pong，避免跳变）
        phase = self._status_anim_index % 32
        ratio = phase / 16.0 if phase < 16 else (32 - phase) / 16.0
        color = _mix(Colors.SUCCESS, "#4ADE80", ratio)
        try:
            self._big_dot.coords(self._big_dot_item, offset, offset, offset + s, offset + s)
            self._big_dot.itemconfig(self._big_dot_item, fill=color)
        except Exception:
            pass
        self._status_anim_index += 1
        self._status_anim_timer = self.root.after(120, self._animate_status_dot)

    # 设置整体状态指示（圆点颜色 / 动画）并刷新状态栏。
    def _set_status(self, color: str, running: bool) -> None:
        self._sync_dot_bg()
        self._sync_big_dot_bg()
        if running:
            self._sidebar_dot.itemconfig(self._sidebar_dot_item, fill=Colors.SUCCESS)
            self._start_status_animation()
        else:
            self._stop_status_animation()
            try:
                # 动效关闭时圆点停在中间尺寸（呼吸链的起点）而非最小尺寸：
                # 中间尺寸是「录制中」的静态可读信号，用户仍能一眼看出在跑。
                _rest = 44 if not self.motion.enabled else 48
                self._big_dot.coords(
                    self._big_dot_item, 32 - _rest // 2, 32 - _rest // 2, 32 + _rest // 2, 32 + _rest // 2
                )
                self._big_dot.itemconfig(self._big_dot_item, fill=color)
            except Exception:
                pass
            self._sidebar_dot.itemconfig(self._sidebar_dot_item, fill=color)
        self._update_status_bar()

    # ─── 配置读写 ──────────────────────────────────────────

    # 加载 URL_config.ini 到编辑器，并跳过无变化的重载。
    def _load_config(self) -> None:
        config_dir = os.path.dirname(self.url_config_file)
        os.makedirs(config_dir, exist_ok=True)

        if not os.path.exists(self.url_config_file):
            with open(self.url_config_file, "w", encoding="utf-8-sig") as f:
                f.write("")

        try:
            with open(self.url_config_file, "r", encoding="utf-8-sig") as f:
                content = f.read()
            # 每次真正读到磁盘都刷新磁盘基线（含下方「内容未变提前 return」分支），否则
            # 保存前的冲突裁决会拿过期基线比对。
            self._url_disk_snapshot = content

            current_content = self.config_text.get("1.0", tk.END).rstrip("\n")
            # 任意外部修改（Web 面板 / 录制子进程写回 / 手工编辑）都同步刷新反查表，
            # 保证画质切换菜单的 URL 解析始终最新。
            self._refresh_quality_context()
            # 两侧统一去掉尾部换行再比较，否则文件末尾换行会导致比较永远失败
            if content.rstrip("\n") == current_content:
                self._last_url_config_mtime = os.path.getmtime(self.url_config_file)
                # M-76③（2026-10-21）：早退分支同样要刷新「已保存」基线。这里的内容与磁盘
                # 逐字相等，跳过本行会让 _config_baseline_content 停在更早的一版（例如外部
                # 改动已被上面的编辑器回填、但基线从没更新过），退出确认与 URL 页保存前都按
                # 「当前内容 != 基线」判脏，于是同一句「有未保存更改」被反复弹给用户。
                self._mark_config_saved()
                return

            self.config_text.delete("1.0", tk.END)
            self.config_text.insert("1.0", content)
            self._last_url_config_mtime = os.path.getmtime(self.url_config_file)
            # 刚从磁盘载入 → 与磁盘一致，记为已保存基线
            self._mark_config_saved()
        except Exception as e:
            self._log(i18n_module.tr("加载配置文件失败: {err}", err=e), "error")

    # 将编辑器中的 URL 配置写入 URL_config.ini 并提示。
    def save_config(self) -> None:
        try:
            editor_text = _normalize_editor_text(str(self.config_text.get("1.0", tk.END)))
            disk_now, _ = _read_config_snapshot(self.url_config_file)
            # 整文件写回前必须重读磁盘并与上次基线比对：URL 页只靠 _watch_url_config 的
            # 3~10s mtime 轮询，窗口内落盘的改动会被静默回滚。录制子进程运行期**确实在写**
            # URL_config.ini（回写主播名、归一 URL、把被风控的房间整行注释掉），且与 GUI 是
            # 两个进程——跨进程只剩「原子替换不半写」一条保护，丢失更新只能显式检测 + 交
            # 用户裁决。后果：点一次「保存」就能把刚被自动注释的坏房间重新启用。
            if _config_change_verdict(
                self._url_disk_snapshot, disk_now, editor_text, self._config_baseline_content
            ) == "conflict" and not messagebox.askyesno(
                i18n_module.tr("配置文件已变更"),
                i18n_module.tr(
                    "config/URL_config.ini 在你上次加载之后已被外部修改（录制进程可能刚回写过主播名、"
                    "归一过地址或注释掉了失效房间）。\n\n"
                    "点击「是」仍按当前编辑内容保存：外部改动会被覆盖；\n"
                    "点击「否」取消保存，可先复制外部改动或重新加载文件。"
                ),
            ):
                # 用户拒覆盖：什么都不写，也不把 mtime/基线对齐到磁盘——保留差异才能在
                # 下一次保存时再问；轮询侧已由 _watch_url_config 的「答否后对齐 mtime」处理。
                self._log(i18n_module.tr("已取消保存：URL_config.ini 的外部改动未被覆盖"), "warn")
                return
            _save_text_widget_to_file(self.config_text, self.url_config_file)
            self._last_url_config_mtime = os.path.getmtime(self.url_config_file)
            # 磁盘基线取「写完之后重读的那份」而非编辑器文本：_save_text_to_file 会补末尾
            # 换行，直接记 editor_text 会让下一次裁决误判成「磁盘被外部改过」。
            self._url_disk_snapshot, _ = _read_config_snapshot(self.url_config_file)
            # 已落盘 → 刷新基线，使后续外部变更能被识别为「无未保存编辑」而自动重载
            self._mark_config_saved()
            # 同步刷新反查表：该表只在 _load_config 里重建，而保存后内容与编辑器一致、
            # _load_config 的「内容未变提前 return」可能跳过重建，导致刚新增/改名的房间
            # 去画质页切换时查不到，弹出「未找到…画质未修改」。
            self._refresh_quality_context()
            self._log(i18n_module.tr("URL 配置已保存"))
            messagebox.showinfo(i18n_module.tr("成功"), i18n_module.tr("URL 配置已保存成功！"))
        except Exception as e:
            self._log(i18n_module.tr("保存配置文件失败: {err}", err=e), "error")
            messagebox.showerror(i18n_module.tr("错误"), i18n_module.tr("保存配置文件失败: {e}", e=e))

    # ─── 状态信息 ──────────────────────────────────────────

    # 从 config.ini 读取循环间隔 / 输出格式与托盘状态（带缓存）。
    def _get_dynamic_status_info(self) -> tuple[str, str, str]:
        check_interval = i18n_module.tr("120秒")
        output_format = "ts → mp4"

        if not os.path.exists(self.main_config_file):
            return check_interval, output_format, self._tray_status_str()

        try:
            file_mtime = os.path.getmtime(self.main_config_file)
            if self._status_cache is not None and file_mtime == self._status_cache_mtime:
                ci, ofmt = self._status_cache
                return ci, ofmt, self._tray_status_str()

            # 必须关插值：config.ini 里含裸 % 的值（cookie、时间格式、自定义脚本命令）会让
            # 默认 ConfigParser 抛 InterpolationSyntaxError，被下方 except 吞掉后状态栏
            # 永久显示默认值且无任何提示。
            config = configparser.ConfigParser(interpolation=None)

            # mypy 不允许直接给方法 optionxform 赋值，用 setattr 绕过；函数显式标注
            # (str) -> str 以满足 basedpyright。键名保持原样（不转小写）以匹配中文节名。
            def _preserve_case(optionstr: str) -> str:
                return optionstr

            setattr(config, "optionxform", _preserve_case)
            config.read(self.main_config_file, encoding="utf-8-sig")

            if "录制设置" in config:
                interval = config["录制设置"].get("循环时间(秒)", "120")
                check_interval = i18n_module.tr("{interval}秒", interval=interval)

                fmt = config["录制设置"].get("录制完成后自动转为mp4格式", "否")
                # 与 main.py / logger.py 共用同一解析口径：原实现只比较 == "是"，
                # 用户把该键写成 true 时状态栏会误显示为「未开启 mp4 转换」。
                if parse_config_bool(fmt, False):
                    output_format = "ts → mp4"
                else:
                    save_fmt = config["录制设置"].get("视频保存格式ts|mkv|flv|mp4|mp3音频|m4a音频", "ts")
                    output_format = f"ts → {save_fmt}"

            self._status_cache = (check_interval, output_format)
            self._status_cache_mtime = file_mtime

        except Exception as e:
            # 不再静默吞：状态栏取不到配置时至少留一条 warning，
            # 否则「配置损坏」与「未配置」表现完全一致，排障无从下手
            logger.warning(
                i18n_module.tr(
                    "状态栏读取 config.ini 失败，使用默认值: {type_name}: {e}", type_name=type(e).__name__, e=e
                )
            )

        return check_interval, output_format, self._tray_status_str()

    # 返回系统托盘是否启用的中文状态字符串。
    def _tray_status_str(self) -> str:
        # 状态栏展示值（唯一消费点 _update_status_bar），必须走 tr——裸中文在非简中界面不译。
        # 本 tkinter 路径已不再持有托盘（产品托盘在 src/gui_qt），故恒为「未启动」。
        return i18n_module.tr("未启动")

    # ─── 子进程管理 ────────────────────────────────────────

    # 跨平台打开 downloads 下载目录（不存在则先创建）。
    def open_downloads_folder(self) -> None:
        downloads_path = self.downloads_dir
        if not os.path.exists(downloads_path):
            os.makedirs(downloads_path, exist_ok=True)

        try:
            if sys.platform == "win32":
                os.startfile(downloads_path)
            elif sys.platform == "darwin":
                _ = _spawn_detached(["open", downloads_path])
            else:
                _ = _spawn_detached(["xdg-open", downloads_path])
            # M-75（2026-10-21）：绝对路径进日志前一律过 mask_credentials（同文件对字体路径
            # 已是这条红线）；logs/ 按大小轮转保留多份，未脱敏的路径等于长期落盘。
            self._log(i18n_module.tr("已打开下载目录: {path}", path=mask_credentials(downloads_path)))
        except Exception as e:
            self._log(i18n_module.tr("打开目录失败: {err}", err=e), "error")

    # 打开高级设置窗口以编辑 config.ini。
    def open_advanced_settings(self) -> None:
        # 单例化：连点两次会打开两个编辑器编辑同一份 config.ini，后保存者静默覆盖先保存者。
        # 已存在且窗口仍存活时聚焦它；用 winfo_exists() 而非关闭回调置 None 判定——后者
        # 需要挂钩 WM_DELETE_WINDOW，而 winfo_exists 对标题栏 X 与保存后自毁都成立。
        existing = self._adv_settings_window
        if existing is not None:
            try:
                if existing.window.winfo_exists():
                    existing.window.lift()
                    existing.window.focus_force()
                    self._log(i18n_module.tr("高级设置窗口已打开，已为你切换到该窗口"))
                    return
            except Exception:
                # 窗口已销毁或控件失效：清掉引用，走下方新建路径
                pass
            self._adv_settings_window = None
        self._adv_settings_window = AdvancedSettingsWindow(
            self.root, self.main_config_file, self._log, tokens=self.theme_manager.tokens()
        )
        # 缩放落位放在构造之后（窗口已 update_idletasks、拿到真实宽高）：动效由宿主施加，
        # AdvancedSettingsWindow 不该知道 MotionController（与主题切换同理）。
        scale_in_window(
            self._adv_settings_window.window,
            self.motion,
            start_scale=DIALOG_START_SCALE,
            duration_ms=170,
            job_key="adv_settings",
        )

    # 判断 URL_config.ini 是否含至少一个可录制地址（注释行与空行不计）。
    def _has_room_config(self) -> bool:
        # 录制核心在空配置时会走 input() 等待键盘输入（non_interactive 默认 False，全仓仅
        # web.py 传 True）。GUI 拉起的子进程带隐藏控制台、stdin 为 CONIN$ 且永不关闭，于是
        # 「点开始录制」后既无报错也无输出、永久静默——必须在 Popen 之前拦截。
        # 判据复用 src/web_config.parse_url_config 的 enabled 字段（唯一口径，含 # 前缀语义与
        # utf-8-sig 编码）：自带 strip + startswith('#') 会因 BOM 把「房间全部注释掉」误判成
        # 有配置。改动自动跟随，不得再各写一套。
        try:
            if not os.path.isfile(self.url_config_file):
                return False
            rooms = parse_url_config(self.url_config_file)
        except OSError:
            # 读不了就放行：让录制核心自己去报错，避免这里用错误的判据挡住正常启动
            return True
        return any(bool(room.get("enabled")) and str(room.get("url", "")).strip() for room in rooms)

    # 启动录制：构造命令行拉起录制核心并接管其输出线程。
    def start_recording(self) -> None:
        # 退出收尾期间禁止启动：退出只置 _quitting 并后台停子进程，收尾线程做僵尸 ffmpeg
        # 清理（两次 taskkill 上限约 8s）期间若拉起新子进程，随后窗口销毁、GUI 退出，新进程
        # 及其 ffmpeg 全部孤儿化（在用户以为已退出的情况下继续录制）。
        if self._quitting:
            return
        if self._stopping:
            # 停止流程尚未完成，禁止在此期间启动新录制，避免竞态（双击停止/停止中误点启动）
            self._log(i18n_module.tr("停止流程进行中，暂不可启动新录制"), "warn")
            return
        if self.process is not None:
            messagebox.showwarning(i18n_module.tr("警告"), i18n_module.tr("录制已在运行中！"))
            return
        if not self._has_room_config():
            # 见 _has_room_config：空配置下子进程会卡死在 input()，此处直接给出可行动提示
            self._log(i18n_module.tr("URL_config.ini 中没有直播间地址，已取消启动录制"), "warn")
            messagebox.showwarning(
                i18n_module.tr("警告"),
                i18n_module.tr(
                    "config/URL_config.ini 中没有可录制的直播间地址。\n"
                    "请先在「直播间配置」中添加至少一个地址，再启动录制。"
                ),
            )
            return

        try:
            # 冻结（PyInstaller）模式下 sys.executable 指向 GUI exe 自身，继续用
            # [sys.executable, main.py] 会递归拉起 GUI；改调同目录的 CLI 可执行文件。
            # 源码运行模式保持原行为不变。
            if getattr(sys, "frozen", False):
                cli_name = "DouyinLiveRecorder.exe" if sys.platform == "win32" else "DouyinLiveRecorder"
                # 冻结布局：GUI 位于 _internal/，CLI exe 与其同目录（_internal 的父目录）；
                # 平铺布局下 self.script_dir 即根目录，故回退一层仅在处于 _internal 时生效。
                base_dir = self.script_dir
                if os.path.basename(os.path.normpath(base_dir)) == "_internal":
                    base_dir = os.path.dirname(base_dir)
                cli_exe = os.path.join(base_dir, cli_name)
                if not os.path.isfile(cli_exe):
                    raise FileNotFoundError(i18n_module.tr("未找到录制核心程序: {path}", path=cli_exe))
                record_cmd = [cli_exe]
            else:
                main_py = os.path.join(self.script_dir, "main.py")
                exe = sys.executable
                if sys.platform == "win32" and os.path.basename(exe).lower().startswith("pythonw"):
                    # pythonw.exe 是没有控制台的 GUI 子系统进程：CREATE_NEW_CONSOLE 对它无效，
                    # 子进程永远收不到 CTRL_BREAK，优雅停止（safe_exit 清理 ffmpeg）结构性失效，
                    # 只能整树强杀。改用同目录的 python.exe（console 子系统）启动录制核心。
                    console_exe = os.path.join(os.path.dirname(exe), "python.exe")
                    if os.path.isfile(console_exe):
                        exe = console_exe
                    else:
                        self._log(
                            i18n_module.tr("未找到 console 解释器 {path}，优雅停止将不可用", path=console_exe),
                            "warn",
                        )
                record_cmd = [exe, main_py]

            startupinfo = None
            # 经 child_process_env() 构建子进程环境：剔除 GUI 父进程标记，否则录制子进程
            # 也被判为 GUI、不写录制日志（见 src/logger.py）。
            env = child_process_env()
            if sys.platform == "win32":
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startupinfo.wShowWindow = subprocess.SW_HIDE

            creation_flags = 0
            if sys.platform == "win32":
                # CREATE_NEW_CONSOLE + SW_HIDE：隐藏控制台是 CTRL_BREAK 的送达前提；若用
                # CREATE_NO_WINDOW，safe_exit 无法触发，停止只能等 15 秒超时后整树强杀。
                # CREATE_NEW_PROCESS_GROUP 让 CTRL_BREAK 只投递给子进程组，不影响 GUI。
                creation_flags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NEW_CONSOLE

            proc = subprocess.Popen(
                record_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                cwd=self.script_dir,
                env=env,
                startupinfo=startupinfo,
                creationflags=creation_flags,
            )

            self.process = proc
            self.process_pid = proc.pid
            # 与 process_pid 同批登记映像基名（冻结态是 DouyinLiveRecorder.exe，源码态是
            # python.exe/pythonw.exe），取自 argv[0] 而非系统反查；反查只用在杀之前那次比对。
            self._child_image_name = os.path.basename(record_cmd[0]).lower()
            # 与映像名同批登记创建时间：源码态下任何 python.exe 都与录制核心同名，只有创建
            # 时间能区分「还是那个进程」与「号码被另一个同名进程接管」。取不到登记 None，
            # 比对侧按「无法判定即不拦」处理。
            self._child_creation_stamp: int | None = _win_pid_creation_stamp(proc.pid)
            self.running = True
            # 新会话开始：自增代号，使所有旧会话的在途收尾回调失效
            self._session_id += 1
            self.start_btn.configure(state=tk.DISABLED)
            self.stop_btn.configure(state=tk.NORMAL)

            # 清空上一轮的画质监控数据，避免旧的降级告警残留到本次会话
            with self._quality_lock:
                self._quality_data.clear()
            self._quality_last_displayed = {}

            self._set_status(Colors.SUCCESS, True)
            self._update_status_bar()

            # 会话代号作为参数绑定（而非线程内读 self._session_id）：并发重启时线程内读取
            # 可能已拿到新会话的代号，使旧进程的 EOF 收尾错误地作用于新会话。
            self.output_thread = threading.Thread(target=self._read_output, args=(proc, self._session_id), daemon=True)
            self.output_thread.start()

            # 弹幕监控：tail 子进程写入的 logs/danmaku_monitor.jsonl
            self._start_danmaku_tail()

            self._log("━" * 40)
            self._log(i18n_module.tr("录制进程已启动 (PID: {pid})", pid=proc.pid))
            # M-75（2026-10-21）：执行程序路径（record_cmd[0]，源码态含用户名 Home 段、
            # 可能是被代理/凭据包装的脚本路径）与工作目录同理，落日志前过脱敏。
            self._log(i18n_module.tr("执行程序: {path}", path=mask_credentials(record_cmd[0])))
            self._log(i18n_module.tr("工作目录: {path}", path=mask_credentials(self.script_dir)))
            self._log("━" * 40)

        except Exception as e:
            self._log(i18n_module.tr("启动录制失败: {err}", err=e), "error")
            messagebox.showerror(i18n_module.tr("错误"), i18n_module.tr("启动录制失败: {e}", e=e))
            # 启动失败时重置状态，允许用户重新启动
            self.process = None
            self.process_pid = None
            self.running = False
            self.start_btn.configure(state=tk.NORMAL)
            self.stop_btn.configure(state=tk.DISABLED)
            self._set_status(Colors.DANGER, False)
            self._update_status_bar()

    # 优雅停止核心：发送优雅信号 → 等待退出 → 超时整树强杀。返回是否走了优雅信号路径
    # （供日志区分「ffmpeg 已由子进程清理」与「硬杀」）。
    # **只允许由 _stop_child_once 调用**（唯一调用点）：控制台附着是进程全局状态，单飞
    # 闸门与「拿锁后复核 poll()」都在那一层；绕开即重新引入「停止/退出交叉篡改控制台
    # 状态」。本方法内部一律不加锁。
    def _send_stop_signal_and_wait(self, proc: subprocess.Popen[str]) -> bool:
        graceful_signal_sent = False
        if sys.platform == "win32":
            self._log(i18n_module.tr("正在发送 CTRL_BREAK 信号（触发子进程 safe_exit 清理 ffmpeg）..."))
            graceful_signal_sent = _send_ctrl_break_to_child(proc.pid)
            if not graceful_signal_sent:
                # 不能只 proc.terminate()：TerminateProcess 硬杀不会触发 main.py 的
                # safe_exit / atexit 兜底，其下 ffmpeg（孙进程）会孤儿化继续录制，
                # 且 wait() 会立即成功、绕过后面的 taskkill /T 兜底分支。
                # 必须用 taskkill /T 递归终止整棵进程树。
                self._log(i18n_module.tr("发送 CTRL_BREAK 失败，整树强制终止（避免 ffmpeg 孤儿化）"), "warn")
                try:
                    subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True, timeout=5)
                except Exception as e:
                    self._log(i18n_module.tr("taskkill 整树终止失败，回退 terminate: {err}", err=e))
                    proc.terminate()
        else:
            self._log(i18n_module.tr("正在发送 SIGINT 信号..."))
            try:
                os.kill(proc.pid, signal.SIGINT)
            except Exception as e:
                self._log(i18n_module.tr("发送 SIGINT 失败，回退 terminate: {err}", err=e))
                proc.terminate()

        # 先等待子进程自行清理其下所有 ffmpeg，超时再整树强杀
        terminated = False
        try:
            proc.wait(timeout=15)
            terminated = True
            if graceful_signal_sent:
                self._log(i18n_module.tr("进程已优雅退出（ffmpeg 已由子进程清理）"))
            else:
                # 硬杀路径（taskkill /T 或 terminate 兜底）：main.py 的 safe_exit
                # 没有机会运行，不能宣称"ffmpeg 已由子进程清理"
                self._log(i18n_module.tr("进程已终止（硬杀路径，ffmpeg 已随进程树终止）"))
        except subprocess.TimeoutExpired:
            self._log(i18n_module.tr("进程未能及时退出，整树强制终止..."))
        except Exception as e:
            # wait 本身的异常（OSError 等）不应让调用方线程静默死亡导致状态卡死
            self._log(i18n_module.tr("等待子进程退出异常: {err}", err=e))

        if not terminated and proc.poll() is None:
            try:
                if sys.platform == "win32":
                    # /T 递归杀掉 main.py 及其所有 ffmpeg 子进程，避免孤儿
                    subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True, timeout=5)
                else:
                    proc.kill()
                    subprocess.run(["pkill", "-P", str(proc.pid), "-x", "ffmpeg"], capture_output=True, timeout=5)
                proc.wait(timeout=5)
                self._log(i18n_module.tr("进程已强制终止"))
            except subprocess.TimeoutExpired:
                self._log(i18n_module.tr("警告：进程可能仍在运行！"), "warn")
            except Exception as e:
                self._log(i18n_module.tr("强制终止失败: {err}", err=e))
        return graceful_signal_sent

    # 登记「正在停止子进程」的在途线程。由 stop_recording / quit_application 在启动工作
    # 线程前调用，早于线程内部登记，以消除「刚点停止、线程还没跑起来」这段窗口里的漏判。
    def _register_stop_worker(self, worker: threading.Thread) -> None:
        # 已有**在途**（alive）线程时不覆盖登记：否则后来者会在 _stop_child_once 里把自己
        # 认成在途的那条，丢掉「等它完成后再收尾」的语义。已结束的残留登记直接替换。
        with self._stop_inflight_lock:
            current = self._stop_inflight
            if current is not None and current is not worker and current.is_alive():
                return
            self._stop_inflight = worker

    # 注销自己这轮停止（只清自己登记的那条，避免把下一轮的登记抹掉）。
    def _finish_stop_worker(self) -> None:
        with self._stop_inflight_lock:
            if self._stop_inflight is threading.current_thread():
                self._stop_inflight = None

    # 当前在途的停止线程（None = 没有在途）。
    def _current_stop_worker(self) -> threading.Thread | None:
        with self._stop_inflight_lock:
            worker = self._stop_inflight
        # is_alive 在锁外判：持锁做线程状态判定没有意义，且退出路径要 join 它，
        # 绝不能带着 _stop_inflight_lock 去 join（会与登记方形成锁序交叉）。
        return worker if worker is not None and worker.is_alive() else None

    # 停止子进程的唯一入口：「停止录制」与「彻底退出」都必须走这里，不得再有任何一处
    # 直接调 _send_stop_signal_and_wait（grep 判据：全文件仅本方法一个调用点）。
    def _stop_child_once(self, proc: subprocess.Popen[str]) -> None:
        # 控制台附着是**进程全局**状态：两个线程对同一 pid 交叉执行
        # FreeConsole→AttachConsole→GenerateConsoleCtrlEvent→FreeConsole 时，CTRL_BREAK
        # 可能错投或整个丢失，最坏退化成 taskkill 硬杀——子进程 main.py 的 safe_exit
        # （清理其下 ffmpeg）就没机会跑，留下孤儿 ffmpeg 继续录制。
        # 锁的持有层次（AGENTS「要么只内部加锁、要么只由调用方加锁，二选一」）：
        # **由本方法（调用方）持锁**，被调的 _send_stop_signal_and_wait 内部一律不加锁。
        worker = self._current_stop_worker()
        if worker is not None and worker is not threading.current_thread():
            # 复用正在进行的停止线程：等它跑完再收尾，而不是另起一轮控制台操作。
            self._log(i18n_module.tr("已有停止流程在途，等待其完成后再收尾（避免并发操作同一子进程控制台）"))
            worker.join(timeout=_STOP_REUSE_JOIN_SECONDS)
        with self._console_stop_lock:
            # 拿锁后必须复核进程状态：在途那轮（或另一条路径）可能已经把子进程终止。
            # 此时再发一遍 CTRL_BREAK，就是对已退出的 pid 走一次 AttachConsole + taskkill，
            # 除了把「清理成功」的日志刷脏之外没有任何作用。
            if proc.poll() is not None:
                return
            self._send_stop_signal_and_wait(proc)

    # 停止录制：发送信号优雅退出，超时则整树强杀 ffmpeg。
    def stop_recording(self) -> None:
        proc = self.process

        if proc is None:
            messagebox.showwarning(i18n_module.tr("警告"), i18n_module.tr("没有正在运行的录制进程！"))
            return

        # 进入停止流程：置位标志并禁用启动按钮，避免停止窗口内被重复触发或误启动
        self._stopping = True
        self.stop_btn.configure(state=tk.DISABLED)
        self.start_btn.configure(state=tk.DISABLED)

        self._log("━" * 40)
        self._log(i18n_module.tr("正在停止录制..."))

        # 优雅退出：让 main.py 的信号处理器自行清理其下的 ffmpeg（孙子进程）。子进程以
        # CREATE_NEW_CONSOLE 隐藏控制台 + 独立进程组启动，CTRL_BREAK 直达 → SIGBREAK →
        # safe_exit → cleanup_all_ffmpeg_processes；proc.terminate() 在 Windows 上是硬杀，
        # 会把 ffmpeg 孤儿化，仅作最后兜底。
        # 信号发送与 taskkill 兜底必须放后台：_send_ctrl_break_to_child 内含 sleep，
        # taskkill 的 timeout=5 最长阻塞 5 秒，留在 UI 线程会让界面冻结无响应。
        def _wait_and_update_ui() -> None:
            # 会话代号在启动子进程时捕获：本线程可能阻塞 15s+（wait timeout），期间用户
            # 可能已重新启动录制，届时本收尾必须整体作废。
            _session = self._session_id
            # _stopping 的复位必须在 finally：主体（ctypes 调用、taskkill、_log）任一抛异常
            # 都会逃出 daemon 线程；若只在末尾复位，标志永久停在 True，此后「开始录制」
            # 只回一句 warn 日志、再无响应。
            try:
                # 走 _stop_child_once：它是两条路径唯一允许触碰子进程控制台的入口（内部
                # 串行化 + 拿锁后复核 poll()）；直接调 _send_stop_signal_and_wait 会绕开单飞闸门。
                self._stop_child_once(proc)

                # 先复位 _stopping 再校验会话：它是 start_recording 的闸门，若在校验失败分支
                # 提前 return，标志会永久停在 True，「开始录制」静默失效。收尾整体上移到
                # finally 后该约束仍然成立。
                self._stopping = False
                if _session != self._session_id:
                    self._log(i18n_module.tr("检测到新录制会话，跳过旧会话的停止收尾"))
                    return
                self.running = False
                self.process = None
                self.process_pid = None

                # 通过事件泵路由回 UI 线程（禁止直接跨线程调用 root.after）
                self.post_ui(lambda: self._on_recording_stopped(_session))
            except Exception as e:
                # 收尾主体抛错不能把用户留在「停止中」假状态里：按钮状态由 UI 线程复位，
                # 这里只补一条带异常类型的日志（Windows 下部分超时的 str() 为空串）。
                self._log(
                    i18n_module.tr("停止流程收尾异常: {type_name}: {err}", type_name=type(e).__name__, err=e),
                    "error",
                )
                self.post_ui(lambda: self._on_recording_stopped(_session))
            finally:
                # 无论收尾成功、跳过（新会话）还是抛异常，「停止流程进行中」都必须结束
                self._stopping = False
                # 注销在途标记同样必须无条件——漏掉会让后续退出白等一次 join 预算。
                self._finish_stop_worker()

        worker = threading.Thread(target=_wait_and_update_ui, name="gui-stop-recording", daemon=True)
        # 登记必须在 start() 之前——否则「点完停止立刻点退出」存在「线程尚未跑起来、标记
        # 还是 None」的窗口，退出路径会对同一 pid 再发一遍 CTRL_BREAK。
        self._register_stop_worker(worker)
        worker.start()

    # 进程终止后在 UI 线程更新按钮状态与状态指示。
    def _on_recording_stopped(self, session_id: int | None = None) -> None:
        # session_id 非空且不等于当前会话 → 旧会话的迟到回调，直接丢弃
        if session_id is not None and session_id != self._session_id:
            return
        self._stop_danmaku_tail()
        self.start_btn.configure(state=tk.NORMAL)
        self.stop_btn.configure(state=tk.DISABLED)
        self._set_status(Colors.DANGER, False)
        self._update_status_bar()
        self._log(i18n_module.tr("录制进程已停止"))
        self._log("━" * 40)
        self._flush_log_queue()

    # 仅在会话未更替时把 running 置 False（_read_output 的 EOF 与两个 except 分支统一走这里）。
    # 典型竞态「停止录制 → 立刻再次启动」：旧进程的 EOF 晚于新会话建立到达，旧线程会把
    # **新会话**的 running 打成 False 且永不回正（只有下次 start_recording 才重置），状态
    # 刷新间隔从 3s 退化为 10s 且无任何日志。
    def _mark_session_stopped(self, session_id: int | None) -> None:
        if session_id is None or session_id == self._session_id:
            self.running = False

    # 读取子进程输出流，解析画质日志并批量入队（线程安全）。
    def _read_output(self, proc: subprocess.Popen[str], session_id: int | None = None) -> None:
        # proc 全程用局部引用，避免停止后立即重启时本线程误读新进程的 stdout（两线程抢读
        # 同一管道）。session_id 为启动时刻捕获的会话代号，供 EOF 收尾时校验会话是否更替。
        batch: list[tuple[str, str]] = []
        batch_size = 10
        # M-71：上次把批次入队的时刻（单调钟，不受系统改时间影响）。readline() 是阻塞的，
        # 因此时间兜底的检查点只能落在「取到一行之后」与「管道瞬时无数据」两处——稀疏日志
        # 的每一行到手时距上次入队必然已超时，于是等价于即时刷新。
        last_flush = time.monotonic()

        # 将缓冲的日志批次入队并标记有待刷新。
        def flush_batch() -> None:
            # 批量刷新日志队列到文本控件（只写队列，调度由 UI 线程泵负责）
            nonlocal batch, last_flush
            if batch:
                self._log_queue.put(batch)
                with self._log_queue_lock:
                    self._log_queue_has_data = True
                batch = []
            # 基准必须在「批次是否非空」之外统一推进：否则空批次滞留会把 last_flush 冻在
            # 过去，之后每一行都单独入队（成批收益被摘掉）。
            last_flush = time.monotonic()

        if proc.stdout is None:
            self._log_queue.put((session_id,))
            with self._log_queue_lock:
                self._log_queue_has_data = True
            return

        while True:
            try:
                line = cast(str, proc.stdout.readline())
                if not line:
                    if proc.poll() is not None:
                        flush_batch()
                        # 收尾统一走 _mark_session_stopped：判据必须与哨兵同源，带 session_id
                        # 交校验，否则 EOF 晚于新会话建立时会打死新会话的 running。
                        self._mark_session_stopped(session_id)
                        self._log_queue.put((session_id,))
                        with self._log_queue_lock:
                            self._log_queue_has_data = True
                        break
                    # EOF 但进程仍在（管道瞬时无数据）：短暂等待避免忙等空转
                    # M-71：这条分支同样是一个检查点——批次里已有内容而管道一直无数据时，
                    # 靠「行数阈值」永远刷不出来（此时不 break，收尾那次 flush 也等不到）。
                    if batch and time.monotonic() - last_flush >= self._LOG_BATCH_FLUSH_SECONDS:
                        flush_batch()
                    time.sleep(0.05)
                    continue

                clean_line = self.ANSI_ESCAPE_PATTERN.sub("", line.rstrip())
                self._parse_quality_log(clean_line)
                batch.append((clean_line, "info"))

                # M-71：行数阈值之外补时间兜底，稀疏日志（稳定期约 120s 一行）不得凑满 10 行
                # 才落进队列——那会让日志页空白约 20 分钟、看起来像界面冻住。
                if len(batch) >= batch_size or time.monotonic() - last_flush >= self._LOG_BATCH_FLUSH_SECONDS:
                    flush_batch()

            except (ValueError, OSError) as e:
                error_msg = str(e)
                flush_batch()
                self._log_queue.put([(i18n_module.tr("输出流已关闭: {err}", err=error_msg), "error")])
                self._log_queue.put((session_id,))
                with self._log_queue_lock:
                    self._log_queue_has_data = True
                self._mark_session_stopped(session_id)
                break
            except Exception as e:
                error_msg = str(e)
                flush_batch()
                self._log_queue.put([(i18n_module.tr("读取输出错误: {err}", err=error_msg), "error")])
                self._log_queue.put((session_id,))
                with self._log_queue_lock:
                    self._log_queue_has_data = True
                self._mark_session_stopped(session_id)
                break

        flush_batch()

    # after 自续期链的唯一重排入口。Tk 回调抛未捕获异常时，写在尾部的下一次 after 不会
    # 注册，定时链永久断裂且无自动恢复（用户视角：整页停摆、无日志）。三处周期链一律在
    # finally 里经本方法无条件重排；重排自身失败（窗口已销毁 → TclError）时返回 None，
    # 让链自然停住。
    # 取消「排了但还没触发」的一次性 after job（M-77②，2026-10-21）。after id 在整个解释器
    # 上唯一，用 self.root 取消即可，不必记「是哪只控件排的」——对话框销毁后 dialog 句柄
    # 本身已不可用，届时再想取消反而要接住 TclError。after_cancel 对「已触发 / 已取消 /
    # 窗口已销毁」的 id 都会抛，一律容错：本方法的职责只是「别再让它触发」。
    def _cancel_after_job(self, job_id: str | None) -> None:
        if not job_id:
            return
        try:
            self.root.after_cancel(job_id)
        except Exception:
            pass

    def _after_retry(self, delay_ms: int, callback: Callable[[], None]) -> str | None:
        try:
            return cast(str, self.root.after(delay_ms, callback))
        except Exception as e:
            # 只在真失败时留痕：正常停链（_finalize_quit / 队列排空）走调用方的 None 分支。
            self._log(
                i18n_module.tr(
                    "定时任务重排失败（窗口可能已销毁）: {type_name}: {err}",
                    type_name=type(e).__name__,
                    err=e,
                ),
                "warn",
            )
            return None

    # 周期性回调的异常留痕限频：一条链的故障通常是持续性的（每 1s / 每 3s 一次），逐次落
    # 日志几十秒就刷满日志页；完全静默又让编程错误不可见。同一链名 30s 内最多一条。
    # 仅 UI 线程读写（三条链都是 root.after 回调），不加锁。
    def _warn_chain(self, chain: str, error: BaseException) -> None:
        now = time.time()
        warn_at = getattr(self, "_chain_warn_at", None)
        if warn_at is None:
            # 无头桩实例（object.__new__ 跳过 __init__）没有该字典：补一份，不静默吞掉留痕。
            warn_at = {}
            self._chain_warn_at = warn_at
        if now - warn_at.get(chain, 0.0) < self._CHAIN_WARN_INTERVAL_SECONDS:
            return
        warn_at[chain] = now
        self._log(
            i18n_module.tr(
                "{chain}周期任务异常（本轮已跳过、下轮继续；{seconds}s 内不重复）: {type_name}: {err}",
                chain=chain,
                seconds=int(self._CHAIN_WARN_INTERVAL_SECONDS),
                type_name=type(error).__name__,
                err=error,
            ),
            "warn",
        )

    # 定时从日志队列批量刷新消息到日志文本框（UI 线程）。
    def _schedule_log_flush(self) -> None:
        # 续期必须落 finally：渲染中途抛错（log_text 已销毁、int(index) 解析失败等）时
        # _log_flush_job_id 若仍是旧的非 None 值，_pump_ui_events 会认为「已排期」而不再
        # 激活，日志页从此不再刷新。主体交给 _drain_log_queue，本方法只负责无条件重排。
        try:
            self._drain_log_queue()
        except Exception as e:
            # 必须补回 has_data：_drain_log_queue 一进函数就把标志清成 False，但「渲染中途
            # 抛错」不等于「队列已被消费干净」——抛错轮次弹出的 messages 随异常丢失，若链
            # 转入休眠态，日志页会停在半屏。复位后由下方 finally 照常续期，下一轮取空队列
            # 后自然再转休眠（只多一个空闲节拍）。
            # 回归锁：tests/test_gui_tail_robustness.py::test_log_flush_chain_rearms_when_render_raises。
            with self._log_queue_lock:
                self._log_queue_has_data = True
            self._warn_chain(i18n_module.tr("日志刷新"), e)
        finally:
            # 还有数据才续期，否则置 None——None 是这条链的**休眠态**（由 _pump_ui_events /
            # _log 按需唤醒），不是断链。
            with self._log_queue_lock:
                has_data = self._log_queue_has_data
            if has_data or not self._log_queue.empty():
                self._log_flush_job_id = self._after_retry(self._LOG_FLUSH_INTERVAL, self._schedule_log_flush)
            else:
                self._log_flush_job_id = None

    # 取空日志队列、渲染到文本框并处理进程结束哨兵（不排期，排期见 _schedule_log_flush）。
    def _drain_log_queue(self) -> None:
        messages: list[tuple[str, str]] = []
        process_ended = False
        ended_session_id: int | None = None
        while True:
            try:
                item = self._log_queue.get_nowait()
                if isinstance(item, list):
                    messages.extend(item)
                else:
                    # 进程结束哨兵 (session_id,)：取出会话代号交给 _process_ended 校验
                    process_ended = True
                    ended_session_id = item[0]
            except queue.Empty:
                break

        # has_data 的清除必须在「队列已取空」的无条件位置：若只在 messages 非空分支清，
        # 哨兵被单独取空且 _process_ended 提前 return 时，has_data 恒 True 而队列恒空，
        # 刷新链会永久空转。
        with self._log_queue_lock:
            self._log_queue_has_data = False

        # M-73（2026-10-21，CODE_REVIEW_2026-10-21）：哨兵处理必须落 finally。此前渲染段与
        # 哨兵处理是顺序两段、无 try/finally 隔离——渲染一抛（log_text 已销毁、index 解析
        # 失败等），异常被 _schedule_log_flush 的 except 吞掉，而 process_ended 随栈一起丢：
        # 子进程其实已经结束，开始/停止按钮与状态灯却永久停在「录制中」（没有别的路径会再
        # 送一次哨兵）。哨兵已在取队列时转存进局部变量，finally 里用的是那份副本，与
        # messages 是否渲染成功无关。
        try:
            if messages:
                self.log_text.config(state=tk.NORMAL)

                for message, level in messages:
                    timestamp = self._get_timestamp()

                    if level == "error":
                        display_text = f"[{timestamp}] [ERROR] {message}\n"
                        tag = "error"
                    elif level == "warn":
                        display_text = f"[{timestamp}] [WARN] {message}\n"
                        tag = "warn"
                    else:
                        display_text = f"[{timestamp}] {message}\n"
                        tag = TAG_NORMAL

                    self.log_text.insert(tk.END, display_text, tag)

                total_lines = int(self.log_text.index("end-1c").split(".")[0])
                if total_lines > self._MAX_LOG_LINES:
                    trim_count = total_lines - self._LOG_TRIM_TO
                    self.log_text.delete("1.0", f"{trim_count + 1}.0")

                self.log_text.see(tk.END)
                self.log_text.config(state=tk.DISABLED)
        finally:
            if process_ended:
                self._process_ended(ended_session_id)

    # 子进程自然结束后的 UI 收尾（重置状态与按钮）。
    def _process_ended(self, session_id: int | None = None) -> None:
        # session_id 非空且不等于当前会话 → 旧会话的迟到回调，直接丢弃，避免把新会话的
        # 按钮/状态灯/self.running 打回「未运行」。
        if session_id is not None and session_id != self._session_id:
            return
        # 退出收尾期间短路：EOF 哨兵仍会触发本回调，但退出线程此刻还在清理；本函数若照常
        # 重新启用 start_btn，用户可在「以为已退出」的窗口期拉起新录制并被随后销毁窗口
        # 孤儿化。退出路径的 UI 生命周期由 _finalize_quit 统一收尾。
        if self._quitting:
            return
        if self._stopping:
            # 手动停止流程进行中：生命周期由 _on_recording_stopped 统一收尾，避免重复重置 UI。
            return
        # 不在 UI 线程 join 后台线程：本回调必然运行在 UI 线程，原实现在这里 join 输出线程
        # 5 秒、_stop_danmaku_tail 再 join 弹幕尾线程 2 秒，累计约 7 秒窗口完全无响应。
        # output_thread 是 daemon，由它自己 EOF 后置哨兵；这里只重置状态。若线程仍在收尾，
        # 日志可能少最后几行，但界面保持可用。
        if self.output_thread and self.output_thread.is_alive():
            logger.debug("录制进程已结束但输出线程仍在收尾，直接重置 UI（不阻塞主线程）")
        self._stop_danmaku_tail()
        self.running = False
        self.process = None
        self.process_pid = None
        self.start_btn.configure(state=tk.NORMAL)
        self.stop_btn.configure(state=tk.DISABLED)

        self._set_status(Colors.DANGER, False)
        self._update_status_bar()

        self._log("━" * 40)
        self._log(i18n_module.tr("录制进程已结束"))
        self._log("━" * 40)

    # 线程安全地向日志队列追加一条消息（不触碰 Tk 对象）。
    def _log(self, message: str, level: str = "info") -> None:
        # 可在任意线程调用；刷新链由 UI 线程泵 _pump_ui_events 按需激活（线程安全与不触碰 Tk 见方法头）。
        self._log_queue.put([(message, level)])
        with self._log_queue_lock:
            self._log_queue_has_data = True

    # 立即（UI 线程）刷新日志队列到文本控件。
    def _flush_log_queue(self) -> None:
        if self._log_flush_job_id:
            # after_cancel 对「已触发过 / 已被取消 / 窗口已销毁」的 id 会抛 TclError；
            # 退出收尾路径上一抛就会中断后续清理。
            try:
                self.root.after_cancel(self._log_flush_job_id)
            except Exception:
                pass
            self._log_flush_job_id = None
        # 只调用 _schedule_log_flush：排期与「还有没有数据」的判定都在它的 finally 里。
        # 若在此再排一条 after 并覆盖 _log_flush_job_id，第一条 job 将无法取消，两条链各自
        # 续期、互相独立地取队列，刷新频率成倍增长。
        self._schedule_log_flush()

    # ─── 画质监控 ──────────────────────────────────────────

    # 解析日志行，提取画质降级告警与录制状态并更新监控数据。
    def _parse_quality_log(self, line: str) -> None:
        # 可在输出线程中调用（仅操作 _quality_data，不触碰 Tk 对象）。
        line = line.lstrip("\r")

        # 剥离 loguru 前缀（控制台格式 "{time} | {level} - {message}"，
        # 文件格式 "{time} | {level} | {module}:{func}:{line} - {message}"）。
        # 找到最后一个 " | " 后的 " - "，取其后内容作为 message。
        msg = line
        if " | " in line:
            pipe_idx = line.rfind(" | ")
            dash_idx = line.find(" - ", pipe_idx)
            if dash_idx > 0:
                msg = line[dash_idx + 3 :]

        patterns = _status_patterns()
        # 译稿写坏导致某条模板拼不出可用正则时，语言码变了才重算、才可能出新的 problems，
        # 故按「problems 变没变」去重，避免每行日志刷一条。
        if patterns.problems and getattr(self, "_status_pattern_problems", None) != patterns.problems:
            self._status_pattern_problems = patterns.problems
            for problem in patterns.problems:
                self._log(i18n_module.tr("画质监控状态行解析降级: {problem}", problem=problem), "warn")

        # 画质降级告警："{name} 画质降级：设置 {zh}({code}) 实际 {zh}({code})"
        m = patterns.downgrade.search(msg) if patterns.downgrade is not None else None
        if m:
            name = m.group("record_name").strip()
            set_zh, set_code = m.group("record_quality_zh"), m.group("record_quality")
            actual_zh, actual_code = m.group("actual_quality_zh"), m.group("actual_quality_code")
            with self._quality_lock:
                info = self._quality_data.setdefault(name, {})
                info.update(
                    {
                        "set_quality": set_zh,
                        "actual_quality": actual_zh,
                        "downgraded": True,
                        "alert_time": self._get_timestamp(),
                        # 数值时刻，用于「告警是否已被后续轮次取代」的时间序比较：每轮录制
                        # 启动只要仍在降级就会重打本告警，故这里等价于「续期」。
                        "alert_at": time.time(),
                        "alert_message": i18n_module.tr(
                            "设置 {set_q}({set_code}) 实际 {actual_q}({actual_code})",
                            set_q=set_zh,
                            set_code=set_code,
                            actual_q=actual_zh,
                            actual_code=actual_code,
                        ),
                        "recording": True,
                        "last_seen": time.time(),
                    }
                )
            return

        # 录制中行："{name}[{quality}] 正在录制中 {duration}"
        m = patterns.recording.match(msg) if patterns.recording is not None else None
        if m:
            name = m.group("recording_live").strip()
            quality = m.group("qa").strip()
            now = time.time()
            with self._quality_lock:
                info = self._quality_data.setdefault(name, {})
                info["recording"] = True
                info["set_quality"] = quality
                info["last_seen"] = now
                # 告警超过 _QUALITY_ALERT_TTL_SECONDS 未被续期即复位，否则一次瞬时降级会把
                # 房间永久钉成「降级」、alert_time 与 actual_quality 从此冻结。
                if _quality_alert_expired(info, now):
                    info["downgraded"] = False
                    info["alert_time"] = ""
                    info["alert_message"] = ""
                    info["alert_at"] = 0.0
                if not info.get("downgraded"):
                    info["actual_quality"] = quality
            return

        # 空态行 → 清除所有录制标记。子串表由 tr() 结果 + 原文两种形态组成（_idle_needles）：
        # 该串生产侧未过 tr()，能否被翻译取决于 builtins.print 补丁，两侧必须同样认得。
        for needle in patterns.idle_needles:
            if needle and needle in msg:
                with self._quality_lock:
                    for info in self._quality_data.values():
                        info["recording"] = False
                break

    # 在 UI 线程刷新画质监控页面与统计（仅限录制中的项）。
    def _update_quality_display(self) -> None:
        if not hasattr(self, "_quality_table"):
            return

        now = time.time()
        with self._quality_lock:
            # 清除超过 30 秒未更新的录制标记（直播已停止但未输出"没有正在录制"）
            for info in self._quality_data.values():
                # M-76①（2026-10-21）：last_seen 走本文件自定的容错口径 _as_float——原先的
                # cast(float, info.get("last_seen", 0)) 不做任何转换，脏值（None/空串/非数值）
                # 一进减法就抛 TypeError，整轮画质刷新被外层 _warn_chain 吞成一句告警、
                # 表停在旧值；cast 只是给类型检查器看的，运行期恒等于什么都不做。
                if info.get("recording") and now - _as_float(info.get("last_seen"), 0.0) > 30:
                    info["recording"] = False

            data = {name: dict(info) for name, info in self._quality_data.items() if info.get("recording")}

        # 数据未变化时跳过同步：比较前须剔除 _QUALITY_NON_DISPLAY_FIELDS，否则 last_seen
        # 心跳刷新会让比较恒不相等。DataTable.sync 本身是行级增量，这层比较再把「无变化轮」
        # 的开销降到零。
        comparable = {
            name: {k: v for k, v in info.items() if k not in _QUALITY_NON_DISPLAY_FIELDS} for name, info in data.items()
        }
        if comparable == self._quality_last_displayed:
            return
        self._quality_last_displayed = comparable

        keys = sorted(data)
        values: dict[str, tuple[str, ...]] = {}
        tags: dict[str, tuple[str, ...]] = {}
        for name in keys:
            info = data[name]
            downgraded = bool(info.get("downgraded", False))
            # 「设置画质」以 URL_config.ini 的当前画质段为准（用户切换意图即时可见）：子进程
            # 日志里的画质是本轮录制启动时的快照，直接用它渲染会把已切换的画质「重置」回旧值。
            # 仅反查表未命中（如配置行无主播名）时回退到日志值；查表前剥离「序号N」前缀。
            key = re.sub(r"^序号\d+\s+", "", name).strip()
            set_q = self._anchor_quality_map.get(key) or str(info.get("set_quality", "—"))
            # 浮层编辑器按行 key 回查当前画质，随 sync 一并刷新（消失行下方一并清缓存）
            self._quality_row_setq[name] = set_q
            actual_q = str(info.get("actual_quality", ""))
            alert_time = str(info.get("alert_time", ""))
            values[name] = (
                name,
                set_q,
                (actual_q or "—") if downgraded else i18n_module.tr("✓ 同等"),
                i18n_module.tr("⚠ 降级") if downgraded else i18n_module.tr("✓ 正常"),
                alert_time if downgraded else "—",
            )
            # 行级标记：降级行整行红字 + 浅红底（颜色由 _sync_table_tags 按 token 配置）
            tags[name] = ("downgraded",) if downgraded else (TAG_NORMAL,)
        for gone in set(self._quality_row_setq) - set(keys):
            del self._quality_row_setq[gone]
        self._highlight_changed_rows(self._quality_table, self._quality_table.sync(keys, values, tags))
        self._show_quality_placeholder(not data)

        # 更新统计
        total = len(data)
        down_count = sum(1 for info in data.values() if info.get("downgraded"))
        ok_count = total - down_count
        try:
            self._q_stat_total.configure(text=str(total))
            self._q_stat_ok.configure(text=str(ok_count))
            self._q_stat_down.configure(text=str(down_count))
        except Exception as e:
            # 不能静默 pass：控件被销毁 / 属性缺失这类持续性故障会表现为「统计数字永久停在
            # 旧值、日志零线索」，外层 _warn_chain 永远等不到。
            self._warn_chain(i18n_module.tr("画质统计刷新"), e)

    # ─── 弹幕监控（tail 边车 JSONL 文件） ──────────────────

    # 启动弹幕监控 tail 线程：清空上一轮数据后跟随 logs/danmaku_monitor.jsonl。
    def _start_danmaku_tail(self) -> None:
        self._stop_danmaku_tail()
        # 上一轮 join 超时被保留下来的线程仍在收尾时不等它（本方法跑在 UI 线程，不为收尾
        # 阻塞界面）；其停止标志已 set，最多再睡完一轮（≤1.0s）即自行退出。并存窗口记 warn。
        stale = self._danmaku_tail_thread
        if stale is not None and stale.is_alive():
            self._log(
                i18n_module.tr("上一条弹幕监控 tail 线程尚未退出（其停止标志已置位、会自行结束），本轮另起新线程"),
                "warn",
            )
        with self._danmaku_lock:
            self._danmaku_rooms.clear()
            self._danmaku_msgs.clear()
            self._danmaku_last_stats = None
            self._danmaku_stats_dirty = True
            self._danmaku_stream_dirty = True
        # 局部 Event + 作为参数传入线程：标志的生命周期与线程一一绑定，
        # 任何后续启动都碰不到上一轮那份（对比旧实现的共享 + clear()）。
        stop_event = threading.Event()
        self._danmaku_tail_stop = stop_event
        self._danmaku_tail_thread = threading.Thread(
            target=self._danmaku_tail_loop, args=(stop_event,), name="danmaku-tail", daemon=True
        )
        self._danmaku_tail_thread.start()

    # 停止 tail 线程（幂等；已显示的数据保留，下次启动录制时清空）。
    # join 只等 0.2s：本方法在 UI 线程被调用，tail 线程只做 JSONL 增量读取，超时则交给
    # daemon 线程随进程退出回收——界面响应优先。
    # join 超时时**保留**线程与停止标志（不置 None、不清除），由下一次启动重查：旧线程醒来
    # 看到的仍是「已 set」，必然退出。
    def _stop_danmaku_tail(self) -> None:
        stop_event = self._danmaku_tail_stop
        if stop_event is not None:
            stop_event.set()
        t = self._danmaku_tail_thread
        if t is not None and t is not threading.current_thread() and t.is_alive():
            t.join(timeout=0.2)
            if t.is_alive():
                # 收尾未完成：保留引用，让下一轮启动前重查（此刻丢弃引用就等于
                # 又造出一个「没人持有、也永远不会退出」的线程，正是旧缺陷）
                return
        self._danmaku_tail_thread = None
        self._danmaku_tail_stop = None

    # tail 线程主体：二进制模式增量读取 JSONL（文本模式 tell 偏移不透明、不能与文件字节数
    # 比较），解码后按行分发；处理轮转回绕，首读仅回看末尾 64KB 以免重放历史会话。
    # stop_event 由 _start_danmaku_tail 逐次创建后传入，绝不再读共享的 self._danmaku_tail_stop。
    def _danmaku_tail_loop(self, stop_event: threading.Event) -> None:
        path = os.path.join(self.app_root, "logs", "danmaku_monitor.jsonl")
        offset = 0
        partial = ""
        first_open = True
        # 最外层异常留痕的限频时刻（线程局部，无需加锁，也天然按轮次重置）。
        last_warn_at = 0.0
        while not stop_event.is_set():
            try:
                if not os.path.exists(path):
                    time.sleep(0.5)
                    continue
                size = os.path.getsize(path)
                if size < offset:
                    # 文件被轮转（变短）：从头重读
                    offset = 0
                    partial = ""
                if size == offset:
                    time.sleep(0.3)
                    continue
                with open(path, "rb") as f:
                    if first_open:
                        # 大文件仅回看末尾 64KB（跳过半个行首对齐到下一行）；
                        # 小文件从头读，不丢首行事件
                        if size > 64 * 1024:
                            f.seek(size - 64 * 1024)
                            f.readline()  # 丢弃半个行首，对齐到下一行
                        offset = f.tell()
                        first_open = False
                        if size == offset:
                            continue
                    f.seek(offset)
                    chunk = f.read()
                    offset += len(chunk)
                partial += chunk.decode("utf-8", errors="replace")
                lines = partial.split("\n")
                partial = lines.pop()
                bad_events = 0
                bad_detail = ""
                for line in lines:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        event = json.loads(line)
                    except ValueError, TypeError:
                        continue
                    if isinstance(event, dict):
                        # 防护必须落在**每条事件**上：一条脏事件冒泡到最外层时 offset 已推进
                        # 过整个 chunk，同批后续完好事件会全部丢失且零日志。坏条只废自己。
                        try:
                            self._danmaku_dispatch(event)
                        except Exception as e:
                            bad_events += 1
                            if not bad_detail:
                                # Windows 下 socket.timeout/TimeoutError 的 str() 是空串，
                                # 故带异常类型名。
                                bad_detail = f"{type(e).__name__}: {e}"
                if bad_events:
                    self._log(
                        i18n_module.tr(
                            "弹幕事件处理失败 {count} 条已跳过（同批其余事件不受影响）: {detail}",
                            count=bad_events,
                            detail=bad_detail,
                        ),
                        "warn",
                    )
            except OSError:
                # 日志被归档改名 / 句柄未就绪（已知良性路径）：等一轮再试，不刷屏。
                time.sleep(1.0)
            except Exception as e:
                # 不能静默 sleep：tail 线程每轮都抛同一个错时，界面表现为「弹幕监控长期
                # 不更新」而日志里零线索。限频 30s 留痕后继续循环（退出信号只有 stop_event）。
                now = time.time()
                if now - last_warn_at >= self._CHAIN_WARN_INTERVAL_SECONDS:
                    last_warn_at = now
                    self._log(
                        i18n_module.tr(
                            "弹幕 tail 线程本轮异常（下轮继续）: {type_name}: {err}",
                            type_name=type(e).__name__,
                            err=e,
                        ),
                        "warn",
                    )
                time.sleep(1.0)

    # 分发一条 JSONL 事件到线程安全缓冲（tail 线程调用，只写锁内数据、不触碰 Tk）。
    # conn 事件维护房间连接状态；stats 事件为统计权威来源；msg 事件进入弹幕流缓冲。
    # 数值字段一律经 _as_float/_as_int：边车 JSONL 外部可控，且首读会回放旧文件末尾
    # 64KB 的历史脏记录，null/字符串都可达。
    def _danmaku_dispatch(self, event: dict[str, Any]) -> None:
        ev = str(event.get("ev", ""))
        room = str(event.get("room", ""))
        with self._danmaku_lock:
            if ev == "conn":
                state = str(event.get("state", ""))
                if state == "started":
                    self._danmaku_rooms[room] = {
                        "platform": str(event.get("platform", "—")),
                        "connected": False,
                        "started_at": _as_float(event.get("ts")),
                        "msg_total": 0,
                        "msg_rate": 0,
                        "gift_total": 0,
                        "online": 0,
                    }
                else:
                    if state == "stopped":
                        # 房间已停止监控（URL 被移除/注释，录制线程退出）：从监控表移除，
                        # 不再显示已失效直播间及其旧弹幕数据
                        self._danmaku_rooms.pop(room, None)
                    else:
                        info = self._danmaku_rooms.get(room)
                        if info is not None:
                            info["connected"] = state == "ready"
                self._danmaku_stats_dirty = True
            elif ev == "msg":
                self._danmaku_msgs.append(event)
                self._danmaku_stream_dirty = True
            elif ev == "stats":
                info = self._danmaku_rooms.setdefault(
                    room,
                    {
                        "platform": str(event.get("platform", "—")),
                        "connected": False,
                        "started_at": 0.0,
                        "msg_total": 0,
                        "msg_rate": 0,
                        "gift_total": 0,
                        "online": 0,
                    },
                )
                info["platform"] = str(event.get("platform", info.get("platform", "—")))
                info["connected"] = bool(event.get("connected", False))
                info["msg_total"] = _as_int(event.get("msg_total", info.get("msg_total", 0)))
                info["msg_rate"] = _as_int(event.get("msg_rate", info.get("msg_rate", 0)))
                info["gift_total"] = _as_int(event.get("gift_total", info.get("gift_total", 0)))
                info["online"] = _as_int(event.get("online", info.get("online", 0)))
                self._danmaku_stats_dirty = True

    # 每秒刷新弹幕监控页（UI 线程）：统计表按脏标记重建，弹幕流按脏标记重绘。
    def _schedule_danmaku_refresh(self) -> None:
        # 续期必须落 finally：两个渲染函数都在动 Tk 控件，且时间戳字段来自外部 JSONL；
        # 一旦抛错就跳过尾部的 after，弹幕页会永久停止刷新且无任何日志。
        try:
            self._update_danmaku_display()
            self._render_danmaku_stream()
        except Exception as e:
            self._warn_chain(i18n_module.tr("弹幕监控刷新"), e)
        finally:
            self._danmaku_refresh_job_id = self._after_retry(1000, self._schedule_danmaku_refresh)

    # 在 UI 线程重建弹幕房间统计表与顶部统计（数据未变化时跳过，避免闪烁）。
    def _update_danmaku_display(self) -> None:
        if not hasattr(self, "_dm_table"):
            return
        with self._danmaku_lock:
            if not self._danmaku_stats_dirty:
                return
            self._danmaku_stats_dirty = False
            rooms_snapshot = {name: dict(info) for name, info in self._danmaku_rooms.items()}

        rows: list[dict[str, str | bool | int]] = []
        total_msgs = 0
        connected_count = 0
        for name, info in rooms_snapshot.items():
            # 数值字段统一走 _as_float/_as_int：_danmaku_rooms 也可能被旧版本/外部数据污染，
            # 这里再兜一道（同一 helper，不在本文件里出现第二套容错写法）。
            started_ts = _as_float(info.get("started_at", 0.0))
            rows.append(
                {
                    "room": name,
                    "platform": str(info.get("platform", "—")),
                    "connected": bool(info.get("connected")),
                    "msg_total": _as_int(info.get("msg_total", 0)),
                    "msg_rate": _as_int(info.get("msg_rate", 0)),
                    "gift_total": _as_int(info.get("gift_total", 0)),
                    "online": _as_int(info.get("online", 0)),
                    "started_at": time.strftime("%H:%M:%S", time.localtime(started_ts)) if started_ts else "—",
                }
            )
            total_msgs += _as_int(info.get("msg_total", 0))
            if bool(info.get("connected")):
                connected_count += 1

        if rows == self._danmaku_last_stats:
            return
        self._danmaku_last_stats = rows

        # 行级增量同步（未变化行零触碰）。断连行整行淡化为 muted——逐列着色在 Treeview
        # 下不可表达（tag 是行级的），已连接/已断开的文字语义保留。
        keys = sorted((str(row["room"]) for row in rows))
        values: dict[str, tuple[str, ...]] = {}
        tags: dict[str, tuple[str, ...]] = {}
        for row in rows:
            name = str(row["room"])
            connected = bool(row["connected"])
            values[name] = (
                name,
                str(row["platform"]),
                i18n_module.tr("已连接") if connected else i18n_module.tr("已断开"),
                str(row["msg_total"]),
                str(row["msg_rate"]),
                str(row["gift_total"]),
                str(row["online"]),
                str(row["started_at"]),
            )
            tags[name] = (TAG_NORMAL,) if connected else ("disconnected",)
        self._highlight_changed_rows(self._dm_table, self._dm_table.sync(keys, values, tags))
        self._show_danmaku_placeholder(not rows)

        # 顶部统计与筛选下拉（保持当前选择，房间列表变化时刷新选项）
        try:
            self._dm_stat_rooms.configure(text=str(len(rows)))
            self._dm_stat_connected.configure(text=str(connected_count))
            self._dm_stat_msgs.configure(text=str(total_msgs))
            current = self._dm_filter_menu.get()
            values_list = [i18n_module.tr("全部房间")] + sorted(rooms_snapshot.keys())
            self._dm_filter_menu.configure(values=values_list)
            if current not in values_list:
                self._dm_filter_menu.set(i18n_module.tr("全部房间"))
                # 菜单回退到「全部房间」时必须同步 _danmaku_filter，否则仍按已移除的旧房间
                # 名过滤——界面显示「全部房间」而弹幕流一片空白，且用户无法自愈。
                with self._danmaku_lock:
                    if self._danmaku_filter != i18n_module.tr("全部房间"):
                        self._danmaku_filter = i18n_module.tr("全部房间")
                        self._danmaku_stream_dirty = True
        except Exception as e:
            # 不能静默 pass：否则「筛选项停在已消失的房间、弹幕流一片空白」会变成零线索故障。
            self._warn_chain(i18n_module.tr("弹幕筛选刷新"), e)

    # 在 UI 线程重绘弹幕流文本框（脏标记跳过；用户上滚查看历史时不强制拉到底）。
    def _render_danmaku_stream(self) -> None:
        if not hasattr(self, "danmaku_text"):
            return
        with self._danmaku_lock:
            if not self._danmaku_stream_dirty:
                return
            self._danmaku_stream_dirty = False
            filter_value = self._danmaku_filter
            msgs = list(self._danmaku_msgs)

        try:
            at_bottom = self.danmaku_text.yview()[1] >= 0.98
        except Exception:
            at_bottom = True

        self.danmaku_text.config(state=tk.NORMAL)
        self.danmaku_text.delete("1.0", tk.END)
        shown = 0
        for m in msgs:
            room = str(m.get("room", ""))
            if filter_value != i18n_module.tr("全部房间") and room != filter_value:
                continue
            mtype = str(m.get("type", "chat"))
            # ts 为 null / 非数值时裸 float 会抛 TypeError 并断掉整条 after 链；回落 0.0
            # 显示 --:--:--。
            ts = _as_float(m.get("ts", 0.0))
            tstr = time.strftime("%H:%M:%S", time.localtime(ts)) if ts else "--:--:--"
            user = str(m.get("user", ""))
            text = str(m.get("text", ""))
            dropped = m.get("dropped")
            if mtype == "gift":
                tag, label = "gift", i18n_module.tr("[礼物] ")
            elif mtype == "superChat":
                tag, label = "superChat", "[SC] "
            else:
                tag, label = "", ""
            line = f"[{tstr}] [{room}] {label}{user}: {text}\n" if user else f"[{tstr}] [{room}] {label}{text}\n"
            # 普通聊天行的 tag 是空串：Tk 的 insert 从第 3 个位置起全是 tag 名，空串会落成
            # 名为 "" 的匿名 tag（轻则无意义，重则在部分 Tk 版本上触发 TclError）。
            if tag:
                self.danmaku_text.insert(tk.END, line, tag)
            else:
                self.danmaku_text.insert(tk.END, line)
            if dropped:
                self.danmaku_text.insert(
                    tk.END, i18n_module.tr("    （+{count} 条已省略）\n", count=dropped), "dropped"
                )
            shown += 1
        if not shown:
            self.danmaku_text.insert(tk.END, i18n_module.tr("暂无弹幕数据\n"))
        self.danmaku_text.config(state=tk.DISABLED)
        if at_bottom:
            self.danmaku_text.see(tk.END)

    # ─── 时间与状态栏 ──────────────────────────────────────

    @staticmethod
    # 返回当前本地时间的时间戳字符串。
    def _get_timestamp() -> str:
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # 刷新控制台状态文字与信息网格（间隔 / 格式 / 托盘 / 时间）。
    def _update_status_bar(self) -> None:
        try:
            check_interval, output_format, tray_status = self._get_dynamic_status_info()
            timestamp = self._get_timestamp()

            pid = self.process_pid
            if pid is not None:
                self.big_status_label.configure(text=i18n_module.tr("录制中"))
                self.big_status_sub.configure(text=i18n_module.tr("录制进程运行中 (PID: {pid})", pid=pid))
                self.sidebar_status_label.configure(text=i18n_module.tr("运行中"))
            else:
                self.big_status_label.configure(text=i18n_module.tr("待 机"))
                self.big_status_sub.configure(text=i18n_module.tr("录制进程未运行"))
                self.sidebar_status_label.configure(text=i18n_module.tr("未运行"))

            self.info_interval.configure(text=check_interval)
            self.info_format.configure(text=output_format)
            self.info_tray.configure(text=tray_status)
            self.info_time.configure(text=timestamp)
        except Exception as e:
            # 内层宽 except 若静默吞掉，状态栏会永久停在旧值而日志一条不留；走同一限频留痕。
            self._warn_chain(i18n_module.tr("状态栏刷新"), e)

    # 周期性刷新状态栏、画质显示并监控 URL 配置变化。
    def _schedule_status_refresh(self) -> None:
        # 续期必须落 finally：_update_quality_display 的控件 destroy/重建或
        # _watch_url_config 里 messagebox 的异常都会让本链静默断掉——状态灯停摆、画质页
        # 不再刷新、URL 配置外部改动不再自动重载，且没有任何人会重新排期。
        try:
            self._update_status_bar()
            self._update_quality_display()
            self._watch_url_config()
        except Exception as e:
            self._warn_chain(i18n_module.tr("状态刷新"), e)
        finally:
            interval = self._STATUS_REFRESH_INTERVAL_ACTIVE if self.running else self._STATUS_REFRESH_INTERVAL
            self._refresh_job_id = self._after_retry(interval, self._schedule_status_refresh)

    # 监控 URL_config.ini 的修改时间，变化时自动重载。
    def _watch_url_config(self) -> None:
        if not os.path.exists(self.url_config_file):
            return
        # 上一个确认框还没被应答就不再判定（理由见 __init__ 的 _url_config_prompt_open）；
        # 放在 try 之外，避免把「正在等待应答」误当成刷新链的异常。
        if self._url_config_prompt_open:
            return
        try:
            current_mtime = os.path.getmtime(self.url_config_file)
            if current_mtime == self._last_url_config_mtime:
                return
            # 不能无条件 _load_config()：mtime 变化可能来自 Web 面板/录制子进程写回，而用户
            # 正在编辑另一处。脏检查：无未保存编辑才自动重载，否则弹确认由用户决定。
            if self._has_unsaved_config_edits():
                self._url_config_prompt_open = True
                try:
                    confirmed = messagebox.askyesno(
                        i18n_module.tr("配置文件已变更"),
                        i18n_module.tr(
                            "URL_config.ini 已被外部修改，但编辑器中有未保存的更改。\n\n"
                            "点击「是」放弃未保存的更改并重新加载；\n点击「否」保留当前编辑内容（稍后可手动保存）。"
                        ),
                    )
                finally:
                    # finally 而不是 if 分支：askyesno 可能抛 TclError（窗口销毁竞态），
                    # 标志留在 True 会让「自动重载外部改动」这条功能永久停摆。
                    self._url_config_prompt_open = False
                if not confirmed:
                    # 保留用户编辑：仅把 mtime 对齐到当前，避免每轮都弹窗
                    self._last_url_config_mtime = current_mtime
                    return
            self._load_config()
        except OSError:
            pass

    # 编辑器中是否存在未保存的更改（与上次加载/保存时的基线内容比对）。
    def _has_unsaved_config_edits(self) -> bool:
        try:
            current = self.config_text.get("1.0", tk.END).rstrip("\n")
        except Exception:
            return False
        # config_text.get 在类型存根中返回 Any，显式 bool() 避免返回 Any
        return bool(current != self._config_baseline_content)

    # 记录当前编辑器内容为「已保存」基线（加载与保存后调用）。
    def _mark_config_saved(self) -> None:
        try:
            self._config_baseline_content = self.config_text.get("1.0", tk.END).rstrip("\n")
        except Exception:
            pass

    # ─── 退出 ──────────────────────────────────────────────

    # 最小化到任务栏（本 tkinter 路径已不持有系统托盘；托盘语义由 src/gui_qt 承担）。
    def minimize_to_tray(self) -> None:
        # 调用点与关闭选项仍叫「最小化到托盘」，保留这条告警，避免用户以为窗口凭空消失。
        self.root.iconify()
        self._log(i18n_module.tr("系统托盘不可用，已改为最小化到任务栏"), "warn")

    # 退出程序：确认后后台停止录制与清理，再销毁窗口（防重入）。
    def quit_application(self) -> None:
        if self._quitting:
            return

        if self.process is not None:
            if not messagebox.askokcancel(
                i18n_module.tr("退出确认"), i18n_module.tr("录制正在后台进行，确定要退出吗？")
            ):
                return

        self._quitting = True
        self._log(i18n_module.tr("正在停止录制并清理 ffmpeg 进程，请稍候..."))
        # 在后台线程完成「停止录制 + 清理残留 ffmpeg」，完成后再回主线程销毁窗口，
        # 避免窗口先被 destroy 导致清理线程被强杀、ffmpeg 残留。
        quit_worker = threading.Thread(target=self._shutdown_and_quit, name="gui-quit", daemon=True)
        # 退出链同样登记为「在途停止线程」，与 stop_recording 对称——谁先到谁登记，
        # 另一条路径就能在 _stop_child_once 里看见它。
        self._register_stop_worker(quit_worker)
        quit_worker.start()

    # 后台执行：优雅停止录制子进程并按需整树强杀与清理 ffmpeg。
    def _shutdown_and_quit(self) -> None:
        # 后台执行：优雅停止录制子进程（由其清理 ffmpeg）→ 超时整树强杀 → 兜底清理。
        # 与停止路径共用单飞入口 _stop_child_once：「停止录制」在途时退出会先复用它（join
        # 完成后收尾），拿锁后再复核 proc.poll()，不存在两线程交叉操作同一控制台。
        proc = self.process
        child_pid = proc.pid if proc is not None else None
        try:
            if proc is not None:
                self._stop_child_once(proc)

                # 退出流程无「新会话」概念，传 None 走无条件置位分支。
                self._mark_session_stopped(None)
                self.process = None
                self.process_pid = None

            # 兜底清理进程树中可能残留的 ffmpeg（显式传入已捕获的 PID，避免此处读到已被
            # 清空的 self.process_pid 导致清理失效）
            self._cleanup_zombie_ffmpeg(child_pid)
        except Exception as e:
            # 任何异常都不能阻断 UI 收尾，否则窗口无法销毁、进程无法退出
            self._log(i18n_module.tr("退出清理流程异常: {err}", err=e), "warn")
        finally:
            # 注销本轮登记（只清自己那条）；不注销会让后续停止/退出白等一次 join 预算。
            self._finish_stop_worker()

        # 通过事件泵路由回 UI 线程收尾销毁（禁止直接跨线程调用 root.after）
        self.post_ui(self._finalize_quit)

    # 在 UI 线程收尾退出：取消调度、停弹幕线程与动画并销毁窗口。
    def _finalize_quit(self) -> None:
        self._pump_active = False
        if self._ui_pump_job_id:
            try:
                self.root.after_cancel(self._ui_pump_job_id)
            except Exception:
                pass
            self._ui_pump_job_id = None

        if self._log_flush_job_id:
            # 退出收尾路径统一容错，避免一抛中断后续清理步骤
            try:
                self.root.after_cancel(self._log_flush_job_id)
            except Exception:
                pass
            self._log_flush_job_id = None

        if self._refresh_job_id:
            try:
                self.root.after_cancel(self._refresh_job_id)
            except Exception:
                pass
            self._refresh_job_id = None

        if self._danmaku_refresh_job_id:
            try:
                self.root.after_cancel(self._danmaku_refresh_job_id)
            except Exception:
                pass
            self._danmaku_refresh_job_id = None

        # M-77②（2026-10-21）：两支一次性 after 也要在这里取消——上面那四条是**自续期链**，
        # 销毁后链上的下一跳会抛 TclError 并被各自的 except 兜住；这两支只排一次、点在
        # root/dialog 之外（主题延迟重取色 / 关闭选项对话框的延迟 grab），若 root.destroy()
        # 之后才触发，抛错在窗口化构建（sys.stderr 为 None）下连一行日志都没有。
        self._cancel_after_job(getattr(self, "_canvas_bg_job_id", None))
        self._canvas_bg_job_id = None
        self._cancel_after_job(getattr(self, "_close_dialog_grab_job_id", None))
        self._close_dialog_grab_job_id = None

        self._stop_danmaku_tail()

        self._stop_status_animation()

        self.root.quit()
        self.root.destroy()

    # 清理录制子进程树及其下的 ffmpeg 残留进程（跨平台）。
    # ffmpeg 的父进程是 main.py 而非 GUI，必须按 main.py 的 PID 整树强杀。
    # 判据只看 returncode == 0：taskkill 找不到 PID 返回 128、pkill 无匹配返回 1，否则
    # 「已清理」与「其实还在录」在日志里完全同形。非 0 时把工具提示（脱敏后）落 warn。
    # 这四类 subprocess.run 一律不传 text=/encoding=：输出按控制台码页本地化，解码只用于
    # 把提示带进日志（_process_kill_hint 内 errors="replace" 兜底）。
    def _cleanup_zombie_ffmpeg(self, target_pid: int | None = None) -> None:
        if target_pid is None:
            target_pid = self.process_pid
        found = False

        try:
            # taskkill /F /T 打的是**号码**：调用点传的是停止链之前捕获的 child_pid，此刻
            # 子进程已退出、号码已进入 PID 复用池，接手者可能是任何进程，/T 还会强杀它的
            # 整棵子树。动手前先读当前映像名，只有确证不是我们启动的那个程序才收手；
            # 判据取不到时按原有无条件形态继续（见 _win_pid_image_name 注释）。
            # 用 getattr 而非直接读 self._child_image_name：本函数被不跑 __init__ 的桩实例
            # 驱动（tests/test_regression_2026_09_22_gui.py），直接访问会抛 AttributeError
            # 并被 except 吞掉，连一次 taskkill 都不发。
            if target_pid is not None:
                reused = _reused_pid_image_pair(cast(str, getattr(self, "_child_image_name", "")), target_pid)
                if reused is not None:
                    current_image, expected_image = reused
                    self._log(
                        i18n_module.tr(
                            "PID {pid} 现由 {image} 占用（录制核心映像名为 {expected}），已跳过整树强杀",
                            pid=target_pid,
                            image=current_image,
                            expected=expected_image,
                        ),
                        "warn",
                    )
                    # 置空号码即让下面两个平台分支都不再动手，并照常落到「未发现需要清理的
                    # ffmpeg 进程」那条结论；不得直接 return——那会让日志只剩一句 warn。
                    target_pid = None
                elif _reused_pid_same_image(getattr(self, "_child_creation_stamp", None), target_pid):
                    # 映像名相同但创建时间对不上 = 号码已被**同名**进程接管（源码态下录制
                    # 核心就叫 python.exe，映像名判据在这一形态上完全失效）。
                    # [2026-10-21 M-72] 本分支现在同时覆盖「创建时间读不到」：判据无法证明那个
                    # 号码还是我们启动的进程，一律按「已复用」收手。文案沿用上面那条 msgid
                    # （措辞偏保守，结论方向一致）；要精确点名「读不到」需新增 msgid
                    # 「PID {pid} 的进程创建时间读不到（权限不足或号码已被复用），已跳过整树强杀」，
                    # 本包不改 i18n/ 目录，已按 AGENTS 交回。
                    self._log(
                        i18n_module.tr(
                            "PID {pid} 的进程创建时间与录制核心不符（同映像名但已被复用），已跳过整树强杀",
                            pid=target_pid,
                        ),
                        "warn",
                    )
                    target_pid = None
            if sys.platform == "win32":
                if target_pid is not None:
                    try:
                        proc = subprocess.run(
                            ["taskkill", "/F", "/T", "/PID", str(target_pid)], capture_output=True, timeout=5
                        )
                        if proc.returncode == 0:
                            found = True
                            self._log(
                                i18n_module.tr("已通过 taskkill 清理 PID {pid} 的进程树（含 ffmpeg）", pid=target_pid)
                            )
                        else:
                            hint = _process_kill_hint(proc.stdout, proc.stderr)
                            self._log(
                                i18n_module.tr(
                                    "taskkill 未能清理 PID {pid} 的进程树（返回码 {code}）",
                                    pid=target_pid,
                                    code=proc.returncode,
                                )
                                + (i18n_module.tr("，提示: {hint}", hint=hint) if hint else ""),
                                "warn",
                            )
                    except Exception as e:
                        self._log(
                            i18n_module.tr("taskkill 执行失败: {type_name}: {err}", type_name=type(e).__name__, err=e),
                            "warn",
                        )
                # [历史注] 原此处还有一段「映像名 + PARENTPID eq GUI 自身 PID」的兜底
                # taskkill：ffmpeg 的父进程恒为 main.py，该形态结构性无法命中。「main.py
                # 已死、ffmpeg 孤儿残留」需按命令行锚定程序目录（同 StopRecording.vbs 的三层
                # 匹配），为避免误杀其它项目的 ffmpeg，本函数不做该形态，由 VBS 承担。
            else:
                if target_pid is not None:
                    try:
                        proc = subprocess.run(
                            ["pkill", "-P", str(target_pid), "-x", "ffmpeg"], capture_output=True, timeout=3
                        )
                        if proc.returncode == 0:
                            found = True
                            self._log(i18n_module.tr("已通过 pkill 清理 PID {pid} 下的 ffmpeg 进程", pid=target_pid))
                        else:
                            hint = _process_kill_hint(proc.stdout, proc.stderr)
                            self._log(
                                i18n_module.tr(
                                    "pkill 未能清理 PID {pid} 下的 ffmpeg（返回码 {code}）",
                                    pid=target_pid,
                                    code=proc.returncode,
                                )
                                + (i18n_module.tr("，提示: {hint}", hint=hint) if hint else ""),
                                "warn",
                            )
                    except Exception as e:
                        self._log(
                            i18n_module.tr("pkill 执行失败: {type_name}: {err}", type_name=type(e).__name__, err=e),
                            "warn",
                        )
            if not found:
                self._log(i18n_module.tr("未发现需要清理的 ffmpeg 进程"))
        except Exception as e:
            self._log(
                i18n_module.tr("清理 ffmpeg 进程时出错: {type_name}: {err}", type_name=type(e).__name__, err=e), "warn"
            )

    # 窗口关闭事件：弹出「最小化到托盘 / 完全退出」对话框（单例）。
    def on_closing(self) -> None:
        if self._close_dialog is not None:
            try:
                if self._close_dialog.winfo_exists():
                    self._close_dialog.focus()
                    return
            except Exception:
                pass
            self._close_dialog = None

        # tk.Toplevel（底色随主题 token；标题栏跟随系统明暗为可接受边界）
        dialog = tk.Toplevel(self.root, bg=self.theme_manager.tokens()["surface"])
        self._close_dialog = dialog
        apply_title(dialog, T("关闭选项"))
        dialog.geometry("400x230")
        dialog.resizable(False, False)
        dialog.transient(self.root)

        # 居中显示对话框
        dialog.update_idletasks()
        x = self.root.winfo_x() + (self.root.winfo_width() - dialog.winfo_width()) // 2
        y = self.root.winfo_y() + (self.root.winfo_height() - dialog.winfo_height()) // 2
        dialog.geometry(f"+{x}+{y}")

        Label(dialog, text="🎬", font=Fonts.mark(32)).pack(pady=(24, 8))
        Label(dialog, text=T("请选择关闭方式"), font=Fonts.heading()).pack()
        Label(
            dialog,
            text=T("您可以最小化到系统托盘，或完全退出程序"),
            font=Fonts.small(),
            variant="muted",
        ).pack(pady=(4, 18))

        btn_frame = Frame(dialog)
        btn_frame.pack(padx=16, pady=(0, 16))

        # M-77②（2026-10-21）：三条销毁路径统一经本函数收口，先取消尚未触发的延迟 grab 再销毁。
        # after 注册在解释器上、不随 dialog 销毁而撤销；窗口化构建（pythonw / console=False）下
        # sys.stderr 为 None，销毁后回调抛的 TclError 完全静默，故障只剩「对话框没变成模态」。
        def close_dialog() -> None:
            self._cancel_after_job(getattr(self, "_close_dialog_grab_job_id", None))
            self._close_dialog_grab_job_id = None
            dialog.destroy()

        # 最小化到托盘并关闭关闭选项对话框。
        def minimize_to_tray_and_close() -> None:
            self.minimize_to_tray()
            close_dialog()

        # 退出应用并关闭关闭选项对话框。
        def quit_and_close() -> None:
            self.quit_application()
            close_dialog()

        Button(
            btn_frame,
            text=T("📥   最小化到托盘"),
            command=minimize_to_tray_and_close,
            font=Fonts.body(bold=True),
            padding=(14, 9),
        ).pack(side=tk.LEFT, padx=(0, 10))

        Button(
            btn_frame,
            text=T("❌   完全退出"),
            command=quit_and_close,
            font=Fonts.body(bold=True),
            padding=(14, 9),
            variant="danger",
        ).pack(side=tk.LEFT)

        # 键盘快捷键
        # Escape 键关闭关闭选项对话框。
        def _on_escape(_event: object = None) -> None:
            close_dialog()

        dialog.bind("<Escape>", _on_escape)

        # 缩放落位放在 grab 之前：动效期间窗口还在变尺寸，先 grab 会让动画期间的点击被吞。
        scale_in_window(dialog, self.motion, start_scale=DIALOG_START_SCALE, duration_ms=170, job_key="close_dialog")

        # 延迟 grab，等待窗口可见
        # M-77②：id 记账（取消见 close_dialog，兜底取消见 _finalize_quit）。
        self._cancel_after_job(getattr(self, "_close_dialog_grab_job_id", None))
        self._close_dialog_grab_job_id = dialog.after(100, lambda: self._safe_dialog_grab(dialog))

    # 安全地为对话框设置模态（容错 grab_set）。
    @staticmethod
    def _safe_dialog_grab(dialog: tk.Toplevel) -> None:
        try:
            dialog.grab_set()
        except Exception:
            pass


# 顶层兜底：窗口化运行（pythonw / PyInstaller console=False 冻结 exe）下 sys.stderr 为
# None，启动期未捕获异常会被静默吞掉。这里把堆栈落盘到临时目录并尽力弹窗，保证可观测。
def _bootstrap_error_sink(exc: BaseException) -> None:
    # 置位防重复上报标记：re-raise 后触发的 excepthook 钩子据此跳过（避免双弹窗/双落盘）
    global _bootstrap_crash_reported
    _bootstrap_crash_reported = True
    tb_text = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    try:
        import tempfile

        log_path = os.path.join(tempfile.gettempdir(), "douyin_recorder_gui_error.log")
        with open(log_path, "w", encoding="utf-8") as _f:
            _f.write(tb_text)
    except Exception:
        pass
    try:
        import tkinter as _tk
        from tkinter import messagebox as _mb

        _root = _tk.Tk()
        _root.withdraw()
        _mb.showerror("GUI 启动失败", tb_text[-3000:])
    except Exception:
        pass


# 程序入口：默认转发到 src.gui_qt.app.main()（PySide6 窗口层）。
# 本文件的 tkinter 版 LiveRecorderGUI 在迁移期保留——tests/test_gui_*.py 的用例以 AST
# 静态锁或 subprocess 驱动钉在它上面，逐项迁移完成前删除会直接断掉这些回归锁。
# 退役计划见 docs/worklog/PROPOSAL_2026-10-17_gui-pyside6-redesign.md §5；
# 回退方式：把 main() 换成 `root = tk.Tk(); _legacy_main(root)`。
def main() -> None:
    from src.gui_qt.app import main as _qt_main

    _qt_main()
    return


# tkinter 版入口（迁移期保留，供回归用例与回退使用）。
def _legacy_main(root: "tk.Tk") -> None:
    app = LiveRecorderGUI(root)

    root.protocol("WM_DELETE_WINDOW", app.on_closing)

    # 主窗口构建完成 → crash sink 切运行期模式（异常只落盘不弹窗）
    _mark_gui_ready()

    # 遗留 pystray 托盘退役后不再有平台分叉，主循环统一走 mainloop()。
    root.mainloop()


if __name__ == "__main__":
    try:
        main()
    except Exception as _exc:  # 顶层兜底：窗口化运行也能看到错误
        _bootstrap_error_sink(_exc)
        raise  # 保留控制台环境的原始堆栈可见性
