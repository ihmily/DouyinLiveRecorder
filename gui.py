# -*- encoding: utf-8 -*-
# 直播录制器 GUI 界面（基于 CustomTkinter 的现代化重构）
# 本模块为图形界面主入口：构建系统托盘（pystray，含 macOS 主线程模型）、
# 主窗口及五个页面（控制台 / 画质监控 / 弹幕监控 / URL 配置 / 运行日志），管理子进程
# 录制生命周期、跨线程日志队列与 UI 事件泵、画质降级监控、弹幕监控（tail 边车
# JSONL 文件）以及优雅退出清理。
# 对外主要类：LiveRecorderGUI（主界面）、SystemTray（托盘管理器）、
# AdvancedSettingsWindow（config.ini 编辑器）、Colors / Fonts（主题与字体）。
from __future__ import annotations

import configparser
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
from collections import deque
from collections.abc import Callable
from datetime import datetime
from tkinter import messagebox
from typing import TYPE_CHECKING, Any, Literal, TypeAlias, cast, final

import customtkinter as ctk
from PIL import Image, ImageDraw

# i18n 多语言：GUI 侧边栏语言菜单即时热切换（i18n.set_language 重载翻译目录，
# 本进程后续 print/日志输出即时换语言）；config 写回经 web_config.update_config_line
# （与 Web 面板同款行级更新，保留注释）。GUI 自身界面文案为静态中文，不随切换重绘。
import i18n as i18n_module
from src.web_config import update_config_line

# tkinter 的 pack/grid/configure/after 等副作用方法在 typeshed 中被类型化为返回
# 非 None（如配置字典、网格信息或计时器 id），实际调用仅为产生副作用。本文件统一
# 关闭 reportUnusedCallResult，避免对大量纯副作用调用误报「结果未使用」。
# pyright: reportUnusedCallResult=none
# LiveRecorderGUI 的若干实例组件仅在 _build_* 方法中初始化，而 _build_* 均在 __init__
# 经 self._setup_ui() 调用、运行期必然已赋值；类型检查器无法跨方法调用证明，故关闭
# reportUninitializedInstanceVariable（类体已做非可选类型声明，确保 .configure 等方法可类型检查）。
# pyright: reportUninitializedInstanceVariable=none


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
            import ctypes

            _k32 = ctypes.windll.kernel32
            _k32.SetConsoleOutputCP(65001)
            _k32.SetConsoleCP(65001)
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
# pystray 延迟导入至 SystemTray.run() 内部，避免 headless 环境顶层导入失败

if TYPE_CHECKING:
    import pystray

    # pystray 无类型存根，Icon 推断为 Any。用 TypeAlias 别名避免在类型表达式里直接写
    # 模块属性 `pystray.Icon`（会触发 reportInvalidTypeForm），同时让 mypy 将其识别为类型别名
    # 而非变量（否则 `PystrayIcon | None` 会报 “not valid as a type” 并级联到所有属性访问）。
    PystrayIcon: TypeAlias = pystray.Icon
else:
    # 运行期占位：仅用于注解，不作为值使用。
    PystrayIcon: TypeAlias = object


# ─── 现代化色彩系统（浅色 / 深色双主题） ──────────────────


# 主题色值常量集合（浅色 / 深色双主题统一色板）。
@final
class Colors:
    # 品牌主色
    PRIMARY = "#4F6DF5"
    PRIMARY_HOVER = "#3D5BE0"
    PRIMARY_SOFT_LIGHT = "#E8EDFE"
    PRIMARY_SOFT_DARK = "#232B45"
    # 语义色
    SUCCESS = "#16A34A"
    SUCCESS_HOVER = "#15803D"
    DANGER = "#DC2626"
    DANGER_HOVER = "#B91C1C"
    WARNING = "#D97706"
    # 中性色（深色模式自动映射）
    BG_LIGHT = "#F4F6FB"
    BG_DARK = "#0F1117"
    CARD_LIGHT = "#FFFFFF"
    CARD_DARK = "#171A23"
    SIDEBAR_LIGHT = "#FFFFFF"
    SIDEBAR_DARK = "#12151D"
    BORDER_LIGHT = "#E5E8F0"
    BORDER_DARK = "#262B3A"
    TEXT_LIGHT = "#1E293B"
    TEXT_DARK = "#E2E8F0"
    MUTED_LIGHT = "#64748B"
    MUTED_DARK = "#8B93A7"
    # 日志终端（两种主题下均保持深色终端风格）
    TERMINAL_BG = "#0D1117"
    TERMINAL_FG = "#7DA7FF"
    TERMINAL_ERROR = "#F85149"
    TERMINAL_WARN = "#D29922"
    TERMINAL_SELECT = "#1F3A5F"


# ─── 字体系统（CustomTkinter 自动处理 DPI 缩放） ───────────

_FONT_FAMILY = "Microsoft YaHei UI"
_MONO_FAMILY = "Cascadia Code"


# 字体工厂：按需创建并缓存复用的 CustomTkinter 字体对象。
@final
class Fonts:
    # 常用字体配置（惰性创建，避免在 Tk 初始化前调用失败）
    _cache: dict[str, ctk.CTkFont] = {}

    # 按 size/weight/family 获取（并缓存）CTkFont 字体对象。
    @classmethod
    def get(cls, size: int, weight: Literal["normal", "bold"] = "normal", family: str = _FONT_FAMILY) -> ctk.CTkFont:
        key = f"{family}_{size}_{weight}"
        if key not in cls._cache:
            cls._cache[key] = ctk.CTkFont(family=family, size=size, weight=weight)
        return cls._cache[key]

    # 获取小号（12px）字体，bold 控制是否加粗。
    @classmethod
    # 返回小号（12px）字体，bold 可控制是否加粗。
    def small(cls, bold: bool = False) -> ctk.CTkFont:
        return cls.get(12, "bold" if bold else "normal")

    # 获取正文（13px）字体，bold 控制是否加粗。
    @classmethod
    # 返回正文（13px）字体，bold 可控制是否加粗。
    def body(cls, bold: bool = False) -> ctk.CTkFont:
        return cls.get(13, "bold" if bold else "normal")

    # 获取标题（15px）字体，默认加粗。
    @classmethod
    # 返回标题（15px）字体，默认加粗。
    def heading(cls, bold: bool = True) -> ctk.CTkFont:
        return cls.get(15, "bold" if bold else "normal")

    # 获取大标题（20px 加粗）字体。
    @classmethod
    # 返回大标题（20px 加粗）字体。
    def title(cls) -> ctk.CTkFont:
        return cls.get(20, "bold")

    # 获取大号状态（26px 加粗）字体。
    @classmethod
    # 返回大号状态（26px 加粗）字体。
    def big_status(cls) -> ctk.CTkFont:
        return cls.get(26, "bold")

    # 获取等宽字体描述元组（字体名, 11）。
    @classmethod
    # 返回等宽字体描述元组（字体名, 11）。
    def mono(cls) -> tuple[str, int]:
        return (_MONO_FAMILY, 11)


# 将 #RRGGBB 十六进制颜色字符串解析为 (R, G, B) 整数元组。
def _hex_to_rgb(color: str) -> tuple[int, int, int]:
    # 将 #RRGGBB 转为 RGB 元组
    color = color.lstrip("#")
    return (int(color[0:2], 16), int(color[2:4], 16), int(color[4:6], 16))


# 按给定比例混合两种十六进制颜色，用于状态点呼吸动画。
def _mix(color_a: str, color_b: str, ratio: float) -> str:
    # 按 ratio 混合两种颜色（0 = A，1 = B），用于呼吸灯动画
    ra, ga, ba = _hex_to_rgb(color_a)
    rb, gb, bb = _hex_to_rgb(color_b)
    r = round(ra + (rb - ra) * ratio)
    g = round(ga + (gb - ga) * ratio)
    b = round(ba + (bb - ba) * ratio)
    return f"#{r:02X}{g:02X}{b:02X}"


# 系统托盘管理器：构建菜单图标、处理托盘交互与跨平台运行模型。
@final
class SystemTray:
    # 系统托盘管理器

    # 初始化系统托盘管理器（持有 GUI 引用、运行状态与 macOS detached 标志）。
    def __init__(self, gui_app: "LiveRecorderGUI"):
        # 初始化系统托盘管理器
        self.gui = gui_app
        self.icon: "PystrayIcon | None" = None
        self.running = False
        # 是否以 macOS run_detached()（非阻塞、仅注册状态栏图标）模式运行；
        # 该模式下 stop() 前需先主动隐藏图标（详见 stop() 注释）。
        self.detached = False

    # 绘制并返回托盘图标位图（圆角矩形 + 白色圆环 + 录制红点）。
    def create_icon_image(self) -> Image.Image:
        # 创建现代化托盘图标
        size = 64
        image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        dc = ImageDraw.Draw(image)

        # 圆角矩形背景
        margin = 2
        dc.rounded_rectangle((margin, margin, size - margin, size - margin), radius=16, fill=(79, 109, 245, 255))

        # 白色圆环
        ring_margin = 10
        dc.ellipse(
            (ring_margin, ring_margin, size - ring_margin, size - ring_margin), outline=(255, 255, 255, 230), width=3
        )

        # 中心录制圆点
        dot_size = 9
        cx = size // 2
        cy = size // 2
        dc.ellipse((cx - dot_size, cy - dot_size, cx + dot_size, cy + dot_size), fill=(220, 38, 38, 255))

        # 提前加载像素数据，避免 ImageDraw 惰性图像在 pystray 保存时触发重入加载崩溃
        image.load()

        # 强制在当前线程（主线程）完成 PIL 插件/编码器的初始化，并预热 pystray 的
        # darwin 后端实际会走的「缩放 + LANCZOS + PNG 序列化」代码路径。
        # 背景：pystray 的 darwin 后端在 icon.run() 内部 spawn 的后台线程里对图标
        # 做 resize(状态栏尺寸) + PNG 序列化（_assert_image -> Image.save('png') ->
        # PIL/_encode_tile）。PIL 的惰性插件/编码器初始化在 PyInstaller 冻结环境下
        # 并非线程安全，从非主线程首次触发会触发原生崩溃（见 CI faulthandler 堆栈），
        # 且该原生崩溃无法被 Python try/except 捕获，直接导致 GUI 进程退出、冒烟失败。
        # 这里把 pystray 实际会走的缩放+PNG 路径提前在主线程跑一遍，确保后台线程复用
        # 已加载的编码器，不再触发首次初始化的竞态。
        try:
            Image.preinit()
            Image.init()
            # 模拟 pystray._assert_image 的 resize(状态栏约 22x22) + PNG 保存。
            # 用 thumbnail（内部同样走 resize + LANCZOS）代替 resize：Pillow 存根的
            # resize.size 形参为 tuple|list|NumpyArray，未装 numpy 时 NumpyArray 无法
            # 解析为 Unknown 会触发 reportUnknownMemberType，thumbnail 签名则完全可解析。
            thumb = image.copy()
            thumb.thumbnail((22, 22), Image.Resampling.LANCZOS)
            _buf = io.BytesIO()
            thumb.save(_buf, "PNG")
        except Exception:
            pass
        return image

    # 托盘菜单「显示主界面」回调：路由到 UI 线程恢复窗口。
    def on_show(self, _icon: "PystrayIcon | None" = None) -> None:
        # 托盘菜单：显示主窗口（pystray 回调运行在托盘线程，Tk 操作必须路由回 UI 线程）
        self.gui.post_ui(self._do_show)

    # 在 UI 线程中恢复并显示主窗口（deiconify + lift）。
    def _do_show(self) -> None:
        # 在 UI 线程中恢复窗口
        self.gui.root.deiconify()
        self.gui.root.lift()

    # 托盘菜单「退出程序」回调：路由到 UI 线程执行退出。
    def on_exit(self, _icon: "PystrayIcon | None" = None) -> None:
        # 托盘菜单：退出程序（路由回 UI 线程，避免跨线程弹窗/操作 Tk）
        self.gui.post_ui(self.gui.quit_application)

    # 托盘菜单「最小化到托盘」回调：路由到 UI 线程隐藏窗口。
    def on_minimize(self, _icon: "PystrayIcon | None" = None) -> None:
        # 托盘菜单：最小化到托盘（路由回 UI 线程）
        self.gui.post_ui(self.gui.root.withdraw)

    # 构造 pystray 图标与菜单（延迟导入 pystray 以兼容 headless）。
    def _build_icon(self) -> "PystrayIcon":
        # 构造 pystray Icon（菜单 + 图标位图）。
        import pystray  # 延迟导入：避免 headless 环境在模块顶层即失败

        menu = pystray.Menu(
            pystray.MenuItem("显示主界面", self.on_show, default=True),
            pystray.MenuItem("最小化到托盘", self.on_minimize),
            pystray.MenuItem("退出程序", self.on_exit),
        )
        return pystray.Icon("LiveRecorder", self.create_icon_image(), "LiveRecorder - click to show", menu)

    # 托盘不可用时优雅降级，避免 GUI 进程因崩溃堆栈退出。
    def _degrade(self, exc: BaseException) -> None:
        # 无系统托盘（headless / 无显示 / 库缺失）时优雅降级，
        # 避免崩溃堆栈导致整个 GUI 进程退出（冒烟测试会据此判定失败）。
        self.running = False
        self.icon = None
        try:
            print(f"[tray] 系统托盘启动失败，已忽略：{exc}", file=sys.stderr)
        except Exception:
            pass

    # 在后台线程启动托盘图标（Windows / Linux 阻塞运行，macOS 禁用）。
    def run(self) -> None:
        # 启动系统托盘图标（阻塞运行；Windows / Linux 专用，由后台线程调用）。
        # 注意：macOS 禁止走本方法 —— pystray darwin 后端的 icon.run() 会以
        # NSApplication.run() 接管「主线程」事件循环，与 Tk mainloop 互斥
        # （Tcl/Tk 在 macOS 只能运行于主线程，否则抛
        #  "RuntimeError: Calling Tcl from different apartment"）。
        # macOS 请使用 run_detached()。
        try:
            icon = self._build_icon()
            self.icon = icon
            self.running = True
            icon.run()
        except Exception as exc:
            self._degrade(exc)

    # macOS 主线程非阻塞启动托盘（仅注册状态栏图标，不接管事件循环）。
    def run_detached(self) -> None:
        # macOS 专用：在「主线程」调用（进入 Tk mainloop 之前），非阻塞。
        # pystray darwin 后端的 run_detached() 只做 _mark_ready()（注册状态栏图标），
        # 不启动 NSApplication.run()；状态栏点击/菜单事件由 Tk 的 Cocoa 事件循环
        # 代为分发（两者共享 NSApplication.sharedApplication()）。这样主线程留给
        # Tk mainloop，同时满足 macOS 上 Tcl/Tk 与 AppKit 都必须在主线程的双重约束。
        try:
            icon = self._build_icon()
            # 在主线程预先渲染并缓存 NSImage（pystray 内部 _icon_image）：
            # run_detached() 触发的 setup 线程会调用 _show() -> _assert_image()
            # 对图标做 resize + PNG 序列化（PIL/_encode_tile）。该原生编码在
            # PyInstaller 冻结环境从非主线程首次触发会原生崩溃，且无法被 Python
            # 异常捕获。此处先在主线程执行一次 _assert_image 把图像缓存下来，
            # setup 线程命中缓存直接返回，从根本上消除后台线程崩溃。
            # 若环境无系统托盘（headless），_assert_image 抛 ObjC 异常，
            # 则跳过 run_detached()，托盘优雅降级、GUI 进程继续存活。
            icon._assert_image()
            # 标记图标已有效：阻止 setup 线程里 visible=True 触发 _update_icon()
            # 把刚缓存的 _icon_image 清空后在后台线程重新 PNG 编码（否则上面的
            # 主线程预热就会被绕过，冻结环境的原生崩溃风险回归）。
            icon._icon_valid = True
            self.icon = icon
            self.detached = True
            self.running = True
            icon.run_detached()
        except Exception as exc:
            self._degrade(exc)

    # 停止系统托盘并移除状态栏图标（全平台容错，detached 先隐藏）。
    def stop(self) -> None:
        # 停止系统托盘（stop() 可能由 UI 线程调用，全程容错）。
        # macOS detached 模式下 pystray _run() 的 finally（移除状态栏项）不会执行，
        # 需先主动隐藏图标再 stop。
        if self.icon and self.running:
            if self.detached:
                try:
                    self.icon.visible = False
                except Exception:
                    pass
            try:
                self.icon.stop()
            except Exception:
                pass
            self.running = False

    # 发送系统通知（仅在托盘图标可用时）。
    def notify(self, message: str, title: str = "直播录制器") -> None:
        # 显示系统通知
        if self.icon:
            try:
                self.icon.notify(message, title)
            except Exception:
                pass


# 高级设置窗口：以文本形式编辑并保存 config/config.ini。
@final
class AdvancedSettingsWindow:
    # 高级设置窗口：编辑 config/config.ini

    # 初始化高级设置窗口（构建 UI、加载配置并延迟安全 grab）。
    def __init__(self, parent: ctk.CTk, config_file: str, log_callback: Callable[[str], None] | None = None):
        # 初始化高级设置窗口
        self.config_file = config_file
        self.log_callback = log_callback

        self.window = ctk.CTkToplevel(parent)
        self.window.title("高级设置 - config.ini")
        self.window.geometry("780x560")
        self.window.minsize(560, 400)
        self.window.transient(parent)

        self._setup_ui()
        self._load_config()

        # 延迟 grab，等待窗口可见，避免 Windows 下 grab_set 报错
        self.window.after(100, self._safe_grab)

    # 安全地为窗口设置模态（容错 grab_set，避免 Windows 报错）。
    def _safe_grab(self) -> None:
        # 安全地设置模态
        try:
            self.window.grab_set()
        except Exception:
            pass

    # 构建高级设置窗口 UI（标题栏、编辑器、保存 / 取消按钮）。
    def _setup_ui(self) -> None:
        # 顶部标题栏
        header = ctk.CTkFrame(self.window, fg_color=Colors.PRIMARY, corner_radius=0, height=52)
        header.pack(fill=tk.X)
        header.pack_propagate(False)
        ctk.CTkLabel(header, text="⚙  高级设置", text_color="#FFFFFF", font=Fonts.heading()).pack(
            side=tk.LEFT, padx=20, pady=12
        )

        # 内容区域
        content = ctk.CTkFrame(self.window, fg_color="transparent")
        content.pack(fill=tk.BOTH, expand=True, padx=16, pady=(16, 0))

        ctk.CTkLabel(content, text="📄 配置文件内容 (config/config.ini)", font=Fonts.body(), anchor=tk.W).pack(
            fill=tk.X, pady=(0, 8)
        )

        # 编辑器（等宽字体）
        self.config_text = ctk.CTkTextbox(
            content, wrap="none", font=Fonts.mono(), corner_radius=10, border_width=1, activate_scrollbars=True
        )
        self.config_text.pack(fill=tk.BOTH, expand=True)

        # 底部按钮
        btn_frame = ctk.CTkFrame(self.window, fg_color="transparent")
        btn_frame.pack(fill=tk.X, padx=16, pady=16)

        ctk.CTkButton(
            btn_frame,
            text="取消",
            command=self.window.destroy,
            fg_color="transparent",
            border_width=1,
            text_color=(Colors.TEXT_LIGHT, Colors.TEXT_DARK),
            border_color=(Colors.BORDER_LIGHT, Colors.BORDER_DARK),
            hover_color=(Colors.BG_LIGHT, Colors.BG_DARK),
            font=Fonts.body(),
            width=110,
            height=36,
            corner_radius=8,
        ).pack(side=tk.RIGHT, padx=(8, 0))

        ctk.CTkButton(
            btn_frame,
            text="💾  保存配置",
            command=self.save_config,
            fg_color=Colors.PRIMARY,
            hover_color=Colors.PRIMARY_HOVER,
            text_color="#FFFFFF",
            font=Fonts.body(bold=True),
            width=130,
            height=36,
            corner_radius=8,
        ).pack(side=tk.RIGHT)

    # 加载 config.ini 内容到编辑器（文件不存在时提示新建）。
    def _load_config(self) -> None:
        # 加载 config.ini 到编辑器
        try:
            with open(self.config_file, "r", encoding="utf-8-sig") as f:
                content = f.read()
            self.config_text.delete("1.0", tk.END)
            self.config_text.insert("1.0", content)
        except FileNotFoundError:
            self.config_text.delete("1.0", tk.END)
            self.config_text.insert("1.0", "# 配置文件不存在，请新建")
        except Exception as e:
            messagebox.showerror("错误", f"加载配置文件失败: {e}")

    # 保存编辑器内容到 config.ini 并提示成功、关闭窗口。
    def save_config(self) -> None:
        # 保存编辑器内容到 config.ini
        try:
            # pyrefly: ignore [bad-argument-type]
            _save_text_widget_to_file(self.config_text, self.config_file)
            messagebox.showinfo("成功", "配置文件已保存！")
            if self.log_callback:
                self.log_callback("高级设置配置已保存")
            self.window.destroy()
        except Exception as e:
            messagebox.showerror("错误", f"保存配置文件失败: {e}")


# 将文本控件内容保存为文件（UTF-8-SIG，自动补末尾换行）。
def _save_text_widget_to_file(text_widget: ctk.CTkTextbox, file_path: str) -> None:
    # 从文本控件读取内容并写入文件
    content = text_widget.get("1.0", tk.END).rstrip("\n")
    if content and not content.endswith("\n"):
        content += "\n"
    with open(file_path, "w", encoding="utf-8-sig") as f:
        f.write(content)


# 向指定 PID 的子进程发送 CTRL_BREAK 信号（仅 Windows），返回是否成功。
def _send_ctrl_break_to_child(pid: int) -> bool:
    # 向拥有独立控制台的子进程发送 CTRL_BREAK（仅 Windows），返回是否成功。
    # 为什么不能用 proc.send_signal(CTRL_BREAK_EVENT)：
    #   - 子进程无控制台（CREATE_NO_WINDOW）时，事件永远送达不到；
    #   - 子进程共享父控制台（仅 CREATE_NEW_PROCESS_GROUP）时，事件会
    #     连同 GUI 进程一起杀死（实测：调用方进程收到 STATUS_CONTROL_C_EXIT）。
    # 正确做法（已实测验证）：临时挂接到子进程控制台，注册一个吞掉事件的
    # 回调保护自身，再向该控制台所有进程广播 CTRL_BREAK，最后还原。
    # 子进程需以 CREATE_NEW_CONSOLE | CREATE_NEW_PROCESS_GROUP 启动
    # （CREATE_NEW_PROCESS_GROUP 会屏蔽 CTRL_C，所以必须发 CTRL_BREAK）。
    if sys.platform != "win32":
        return False
    import ctypes

    k32 = ctypes.windll.kernel32
    had_console = bool(cast(int, k32.GetConsoleWindow()))
    handler_routine = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_ulong)

    # 控制台 Ctrl 事件回调：返回 True 表示事件已处理，保护 GUI 不被终止。
    def _ignore(_ctrl_type: int) -> bool:
        return True  # 声明事件已处理，避免 GUI 自身被 CTRL_BREAK 终止

    cb = handler_routine(_ignore)
    k32.FreeConsole()
    if not cast(bool, k32.AttachConsole(pid)):
        if had_console:
            k32.AttachConsole(0xFFFFFFFF)  # ATTACH_PARENT_PROCESS 恢复
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
        if had_console:
            k32.AttachConsole(0xFFFFFFFF)


# 直播录制 GUI 主类：整合界面、子进程录制、日志队列与画质监控。
@final
class LiveRecorderGUI:
    # 直播录制 GUI 主类

    # 常量定义
    ANSI_ESCAPE_PATTERN = re.compile(r"\x1b\[[0-9;]*m")
    # 画质降级告警："{name} 画质降级：设置 {zh}({code}) 实际 {zh}({code})"
    QUALITY_DOWNGRADE_PATTERN = re.compile(r"(.+?) 画质降级：设置 (.+?)\((.+?)\) 实际 (.+?)\((.+?)\)")
    # 录制中行："{name}[{quality}] 正在录制中 {duration}"
    RECORDING_LINE_PATTERN = re.compile(r"^(.+?)\[(.+?)\] 正在录制中")
    _MAX_LOG_LINES = 1000
    _LOG_TRIM_TO = 800
    _LOG_FLUSH_INTERVAL = 200
    _STATUS_REFRESH_INTERVAL = 10000  # 未录制时的刷新间隔（毫秒）
    _STATUS_REFRESH_INTERVAL_ACTIVE = 3000  # 有录制直播间时的刷新间隔（毫秒）

    # 由构建方法（_build_*）初始化的实例组件声明，供类型检查器识别。
    # customtkinter 无类型存根，CTkFrame 推断为 Unknown；改用有 typeshed 存根的
    # tkinter.Frame 作为具体声明类型（运行时 CTkFrame 同样可赋值）。
    sidebar: "tk.Frame"

    # 以下实例组件仅在 _build_* 方法中初始化，而 _build_* 均在 __init__ 中被
    # self._setup_ui() 调用，运行期必然已初始化。此处仅做类型声明（供 .configure
    # 等方法类型检查），其「未初始化」告警由文件顶部 reportUninitializedInstanceVariable=none 关闭。
    _sidebar_dot_item: int
    _big_dot: tk.Canvas
    _big_dot_item: int
    sidebar_status_label: ctk.CTkLabel
    appearance_menu: ctk.CTkOptionMenu
    language_menu: ctk.CTkOptionMenu
    big_status_label: ctk.CTkLabel
    big_status_sub: ctk.CTkLabel
    info_interval: ctk.CTkLabel
    info_format: ctk.CTkLabel
    info_tray: ctk.CTkLabel
    info_time: ctk.CTkLabel
    start_btn: ctk.CTkButton
    stop_btn: ctk.CTkButton
    config_text: ctk.CTkTextbox
    reload_btn: ctk.CTkButton
    save_btn: ctk.CTkButton
    log_text: tk.Text
    _q_stat_total: ctk.CTkLabel
    _q_stat_ok: ctk.CTkLabel
    _q_stat_down: ctk.CTkLabel
    _quality_scroll: ctk.CTkScrollableFrame
    _dm_stat_rooms: ctk.CTkLabel
    _dm_stat_connected: ctk.CTkLabel
    _dm_stat_msgs: ctk.CTkLabel
    _dm_scroll: ctk.CTkScrollableFrame
    _dm_filter_menu: ctk.CTkOptionMenu
    danmaku_text: tk.Text

    # 初始化 GUI 主窗口、路径配置、状态与所有后台调度。
    def __init__(self, root: ctk.CTk):
        # 初始化 GUI 主窗口及所有组件
        self.root = root
        self.root.title("直播录制控制台")
        self.root.geometry("1120x740")
        self.root.minsize(920, 620)

        # 外观模式：跟随系统
        ctk.set_appearance_mode("system")

        # status_pill 由 _build_header 重建并布局；此处先以有类型的占位实例初始化，
        # 消除 reportUninitializedInstanceVariable（未打包的 Frame 不会渲染）。
        self.status_pill: tk.Frame = tk.Frame(self.root)
        # _sidebar_dot 等同理：构建方法重建并打包，此处以有类型占位实例初始化。
        self._sidebar_dot: tk.Canvas = tk.Canvas(self.status_pill)

        # 路径配置
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

        # 进程状态（线程安全访问）
        self._process_lock = threading.Lock()
        self._process: subprocess.Popen[str] | None = None
        self._process_pid: int | None = None
        self._running = False
        self._stopping = False  # 停止进行中标志：阻塞启动/重复停止，消除停止竞态窗口

        self.output_thread: threading.Thread | None = None

        self.system_tray: SystemTray | None = None
        self.tray_thread: threading.Thread | None = None

        # 配置文件监控
        self._last_url_config_mtime = 0.0
        self._refresh_job_id: str | None = None

        # 状态缓存（避免频繁读取配置）
        self._status_cache_mtime = 0.0
        self._status_cache: tuple[str, str] | None = None

        # 日志队列（用于线程间通信）
        self._log_queue: queue.Queue[list[tuple[str, str]] | None] = queue.Queue()
        self._log_flush_job_id: str | None = None
        self._log_queue_has_data = False
        self._log_queue_lock = threading.Lock()  # 保护 _log_queue_has_data 跨线程访问

        # 画质监控数据（线程安全：_quality_lock 保护 _quality_data）
        # {name: {set_quality, actual_quality, downgraded, alert_time, alert_message, recording, last_seen}}
        self._quality_lock = threading.Lock()
        self._quality_data: dict[str, dict[str, str | bool | float]] = {}
        self._quality_last_displayed: dict[str, dict[str, str | bool | float]] = {}

        # 弹幕监控数据（线程安全：_danmaku_lock 保护以下字段）
        # _danmaku_rooms: {room: {platform/connected/started_at/msg_total/msg_rate/gift_total/online}}
        # _danmaku_msgs: 近期消息环形缓冲（tail 线程追加，UI 线程渲染，最多 300 条）
        self._danmaku_lock = threading.Lock()
        self._danmaku_rooms: dict[str, dict[str, str | bool | int | float]] = {}
        self._danmaku_msgs: deque[dict[str, Any]] = deque(maxlen=300)
        self._danmaku_filter = "全部房间"
        self._danmaku_stats_dirty = True  # 统计表是否有变化待重绘
        self._danmaku_stream_dirty = True  # 弹幕流是否有新消息待重绘
        # 仅缓存上次渲染的 rows 用于比较去重（见 _update_danmaku_display），值不含 float
        self._danmaku_last_stats: list[dict[str, str | bool | int]] | None = None
        self._danmaku_tail_thread: threading.Thread | None = None
        self._danmaku_tail_stop = threading.Event()
        self._danmaku_refresh_job_id: str | None = None

        # UI 线程事件队列：后台线程一律通过 post_ui 投递回调，
        # 由 _pump_ui_events 在 UI 线程执行。tkinter 不是线程安全的，
        # 后台线程直接调 root.after/createcommand 会随机崩溃
        # （RuntimeError: main thread is not in main loop）。
        self._ui_event_queue: queue.Queue[tuple[Callable[..., None], tuple[object, ...]]] = queue.Queue()
        self._pump_active = True
        self._ui_pump_job_id: str | None = None

        # 状态指示器动画
        self._status_animating = False
        self._status_anim_index = 0
        self._status_anim_timer: str | None = None

        # 页面导航
        self._nav_buttons: dict[str, ctk.CTkButton] = {}
        self._pages: dict[str, ctk.CTkFrame] = {}
        self._current_page = ""

        # 退出/对话框防重入标志
        self._quitting = False
        self._close_dialog: ctk.CTkToplevel | None = None

        self.sidebar = self._build_sidebar()
        self._setup_ui()
        self._load_config()
        self._schedule_log_flush()
        self._schedule_status_refresh()
        self._danmaku_refresh_job_id = self.root.after(1000, self._schedule_danmaku_refresh)
        self._ui_pump_job_id = self.root.after(100, self._pump_ui_events)

    # ─── UI 线程事件泵（线程安全调度） ──────────────────────

    # 从任意线程安全地调度回调到 UI 线程执行（仅入队，不触碰 Tk）。
    def post_ui(self, callback: Callable[..., None], *args: object) -> None:
        # 从任意线程安全地调度回调到 UI 线程执行（只写队列，不触碰 Tk）
        self._ui_event_queue.put((callback, args))

    # UI 线程事件泵：执行后台投递的回调并激活日志刷新链。
    def _pump_ui_events(self) -> None:
        # UI 线程泵：执行后台线程投递的回调，并激活日志刷新链
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
                # 记录回调异常便于排查，避免静默吞掉 UI 回调 bug
                self._log("UI 事件回调执行异常（详见控制台）", "error")
                import traceback

                traceback.print_exc()

        if not self._pump_active:
            return

        # 后台线程只往日志队列放数据，由这里在 UI 线程按需激活刷新链
        with self._log_queue_lock:
            has_data = self._log_queue_has_data
        if has_data and self._log_flush_job_id is None:
            self._log_flush_job_id = self.root.after(self._LOG_FLUSH_INTERVAL, self._schedule_log_flush)

        self._ui_pump_job_id = self.root.after(100, self._pump_ui_events)

    # ─── 进程状态线程安全访问 ───────────────────────────────

    @property
    # 线程安全地读取当前子进程对象。
    def process(self) -> subprocess.Popen[str] | None:
        # 获取子进程对象（线程安全）
        with self._process_lock:
            return self._process

    # 设置当前子进程对象（线程安全）。
    @process.setter
    # 线程安全地设置子进程对象。
    def process(self, value: subprocess.Popen[str] | None) -> None:
        # 设置子进程对象（线程安全）
        with self._process_lock:
            self._process = value

    # 读取当前子进程 PID（线程安全）。
    @property
    # 线程安全地读取子进程 PID。
    def process_pid(self) -> int | None:
        # 获取子进程 PID
        with self._process_lock:
            return self._process_pid

    # 设置当前子进程 PID（线程安全）。
    @process_pid.setter
    # 线程安全地设置子进程 PID。
    def process_pid(self, value: int | None) -> None:
        # 设置子进程 PID
        with self._process_lock:
            self._process_pid = value

    # 读取录制运行状态（线程安全）。
    @property
    # 线程安全地读取录制运行状态。
    def running(self) -> bool:
        # 获取运行状态
        with self._process_lock:
            return self._running

    # 设置录制运行状态（线程安全）。
    @running.setter
    # 线程安全地设置录制运行状态。
    def running(self, value: bool) -> None:
        # 设置运行状态
        with self._process_lock:
            self._running = value

    # ─── UI 初始化 ─────────────────────────────────────────

    # 构建主布局（左侧导航栏 + 右侧内容区）并展示默认页。
    def _setup_ui(self) -> None:
        # 主布局：左侧导航栏 + 右侧内容区（grid）
        self.root.grid_columnconfigure(0, minsize=230, weight=0)
        self.root.grid_columnconfigure(1, weight=1)
        self.root.grid_rowconfigure(0, weight=1)

        self._build_content()
        self._show_page("dashboard")

    # 构建左侧导航栏（品牌、状态胶囊、导航按钮、外观与退出）。
    def _build_sidebar(self) -> "tk.Frame":
        # 构建左侧导航栏
        # mypy 不加载 typings/customtkinter 存根，ctk.CTkFrame(...) 推断为 Any；
        # 按本模块约定（CTkFrame 实为 tkinter.Frame 子类）cast 为 tk.Frame，
        # 既给 mypy 具体返回类型消除 no-any-return，也保持基于存根的 basedpyright 0/0/0。
        sidebar = cast(
            "tk.Frame",
            ctk.CTkFrame(
                self.root, corner_radius=0, fg_color=(Colors.SIDEBAR_LIGHT, Colors.SIDEBAR_DARK), border_width=0
            ),
        )
        sidebar.grid(row=0, column=0, sticky="nsew")
        sidebar.grid_propagate(False)

        # 品牌区
        brand = ctk.CTkFrame(sidebar, fg_color="transparent")
        brand.pack(fill=tk.X, padx=20, pady=(24, 6))
        ctk.CTkLabel(brand, text="🎬", font=ctk.CTkFont(size=30)).pack(side=tk.LEFT)
        brand_text = ctk.CTkFrame(brand, fg_color="transparent")
        brand_text.pack(side=tk.LEFT, padx=(10, 0))
        ctk.CTkLabel(
            brand_text, text="直播录制", font=Fonts.title(), text_color=(Colors.TEXT_LIGHT, Colors.TEXT_DARK)
        ).pack(anchor=tk.W)
        ctk.CTkLabel(
            brand_text,
            text="DouyinLiveRecorder",
            font=Fonts.small(),
            text_color=(Colors.MUTED_LIGHT, Colors.MUTED_DARK),
        ).pack(anchor=tk.W)

        # 状态胶囊
        self.status_pill = ctk.CTkFrame(
            sidebar,
            corner_radius=20,
            height=38,
            fg_color=(Colors.BG_LIGHT, Colors.BG_DARK),
            border_width=1,
            border_color=(Colors.BORDER_LIGHT, Colors.BORDER_DARK),
        )
        self.status_pill.pack(fill=tk.X, padx=16, pady=(14, 6))
        self.status_pill.pack_propagate(False)

        self._sidebar_dot = tk.Canvas(self.status_pill, width=12, height=12, highlightthickness=0, bd=0)
        self._sidebar_dot.pack(side=tk.LEFT, padx=(14, 8))
        self._sidebar_dot_item = self._sidebar_dot.create_oval(1, 1, 11, 11, fill=Colors.DANGER, outline="")
        self._sync_dot_bg()

        self.sidebar_status_label = ctk.CTkLabel(
            self.status_pill,
            text="未运行",
            font=Fonts.body(bold=True),
            text_color=(Colors.TEXT_LIGHT, Colors.TEXT_DARK),
        )
        self.sidebar_status_label.pack(side=tk.LEFT)

        # 导航按钮
        nav = ctk.CTkFrame(sidebar, fg_color="transparent")
        nav.pack(fill=tk.X, padx=12, pady=(18, 0))

        self._add_nav_button(nav, "dashboard", "📊   控制台")
        self._add_nav_button(nav, "quality", "🎯   画质监控")
        self._add_nav_button(nav, "danmaku", "💬   弹幕监控")
        self._add_nav_button(nav, "config", "📝   URL 配置")
        self._add_nav_button(nav, "logs", "📋   运行日志")

        # 底部区域
        bottom = ctk.CTkFrame(sidebar, fg_color="transparent")
        bottom.pack(side=tk.BOTTOM, fill=tk.X, padx=12, pady=16)

        # 外观切换
        ctk.CTkLabel(
            bottom, text="外观模式", font=Fonts.small(), text_color=(Colors.MUTED_LIGHT, Colors.MUTED_DARK), anchor=tk.W
        ).pack(fill=tk.X, padx=6, pady=(0, 4))
        self.appearance_menu = ctk.CTkOptionMenu(
            bottom,
            values=["跟随系统", "浅色", "深色"],
            command=self._on_appearance_change,
            font=Fonts.body(),
            corner_radius=8,
            height=34,
            fg_color=(Colors.BG_LIGHT, Colors.BG_DARK),
            button_color=("#D6DAE5", "#2A3040"),
            button_hover_color=("#C3C9D8", "#343B4E"),
            text_color=(Colors.TEXT_LIGHT, Colors.TEXT_DARK),
            dropdown_fg_color=(Colors.CARD_LIGHT, Colors.CARD_DARK),
            dropdown_text_color=(Colors.TEXT_LIGHT, Colors.TEXT_DARK),
            dropdown_hover_color=(Colors.PRIMARY_SOFT_LIGHT, Colors.PRIMARY_SOFT_DARK),
        )
        self.appearance_menu.pack(fill=tk.X, padx=2, pady=(0, 12))
        self.appearance_menu.set("跟随系统")

        # 语言切换：显示名 → 语言码映射；选择即热切换本进程翻译目录并写回 config.ini
        ctk.CTkLabel(
            bottom,
            text="语言 Language",
            font=Fonts.small(),
            text_color=(Colors.MUTED_LIGHT, Colors.MUTED_DARK),
            anchor=tk.W,
        ).pack(fill=tk.X, padx=6, pady=(0, 4))
        self._language_names: dict[str, str] = {
            code: name.split(" (")[0] if " (" in name else name
            for code, name in i18n_module.available_languages().items()
        }
        self.language_menu = ctk.CTkOptionMenu(
            bottom,
            values=list(self._language_names.values()),
            command=self._on_language_change,
            font=Fonts.body(),
            corner_radius=8,
            height=34,
            fg_color=(Colors.BG_LIGHT, Colors.BG_DARK),
            button_color=("#D6DAE5", "#2A3040"),
            button_hover_color=("#C3C9D8", "#343B4E"),
            text_color=(Colors.TEXT_LIGHT, Colors.TEXT_DARK),
            dropdown_fg_color=(Colors.CARD_LIGHT, Colors.CARD_DARK),
            dropdown_text_color=(Colors.TEXT_LIGHT, Colors.TEXT_DARK),
            dropdown_hover_color=(Colors.PRIMARY_SOFT_LIGHT, Colors.PRIMARY_SOFT_DARK),
        )
        self.language_menu.pack(fill=tk.X, padx=2, pady=(0, 12))
        # 初始值：读 config.ini 的语言键（缺失/非法回退默认），同步到 i18n
        try:
            _cfg = configparser.ConfigParser(interpolation=None)
            _cfg.read(self.main_config_file, encoding="utf-8-sig")
            _raw_lang = _cfg.get("录制设置", "language(zh_cn/en)", fallback="") if _cfg.has_section("录制设置") else ""
        except Exception:
            _raw_lang = ""
        _norm_lang = i18n_module.normalize_language(_raw_lang)
        _ = i18n_module.set_language(_norm_lang)
        self.language_menu.set(self._language_names.get(_norm_lang, self._language_names[i18n_module.DEFAULT_LANGUAGE]))

        ctk.CTkButton(
            bottom,
            text="📥   最小化到托盘",
            command=self.minimize_to_tray,
            font=Fonts.body(),
            height=38,
            corner_radius=8,
            fg_color="transparent",
            text_color=(Colors.TEXT_LIGHT, Colors.TEXT_DARK),
            border_width=1,
            border_color=(Colors.BORDER_LIGHT, Colors.BORDER_DARK),
            hover_color=(Colors.BG_LIGHT, Colors.BG_DARK),
            anchor=tk.W,
        ).pack(fill=tk.X, pady=(0, 8))

        ctk.CTkButton(
            bottom,
            text="❌   彻底退出",
            command=self.quit_application,
            font=Fonts.body(bold=True),
            height=38,
            corner_radius=8,
            fg_color=Colors.DANGER,
            hover_color=Colors.DANGER_HOVER,
            text_color="#FFFFFF",
            anchor=tk.W,
        ).pack(fill=tk.X)

        return sidebar

    # 向侧边栏添加一项导航按钮并绑定页面切换回调。
    def _add_nav_button(self, parent: ctk.CTkFrame, page_id: str, text: str) -> None:
        # 添加侧边栏导航按钮
        btn = ctk.CTkButton(
            parent,
            text=text,
            command=lambda: self._show_page(page_id),
            font=Fonts.body(),
            height=42,
            corner_radius=8,
            fg_color="transparent",
            text_color=(Colors.MUTED_LIGHT, Colors.MUTED_DARK),
            hover_color=(Colors.BG_LIGHT, Colors.BG_DARK),
            anchor=tk.W,
        )
        btn.pack(fill=tk.X, pady=2)
        self._nav_buttons[page_id] = btn

    # 切换至指定页面并高亮对应的导航按钮。
    def _show_page(self, page_id: str) -> None:
        # 切换到指定页面并高亮对应导航按钮
        if page_id not in self._pages:
            return
        self._current_page = page_id
        self._pages[page_id].tkraise()
        for pid, btn in self._nav_buttons.items():
            if pid == page_id:
                btn.configure(
                    fg_color=(Colors.PRIMARY_SOFT_LIGHT, Colors.PRIMARY_SOFT_DARK),
                    text_color=(Colors.PRIMARY, "#9DB1FF"),
                    font=Fonts.body(bold=True),
                )
            else:
                btn.configure(
                    fg_color="transparent", text_color=(Colors.MUTED_LIGHT, Colors.MUTED_DARK), font=Fonts.body()
                )

    # 切换浅色 / 深色 / 系统外观模式并同步自绘控件颜色。
    def _on_appearance_change(self, choice: str) -> None:
        # 切换外观模式
        mapping = {"跟随系统": "system", "浅色": "light", "深色": "dark"}
        ctk.set_appearance_mode(mapping.get(choice, "system"))
        # 主题切换后同步自绘控件颜色（Canvas 不随主题自动变化）
        self.root.after(50, self._sync_canvas_bg)

    # 语言菜单选择回调：即时热切换翻译目录并持久化到 config.ini。
    def _on_language_change(self, choice: str) -> None:
        # 显示名 → 语言码（SUPPORTED_LANGUAGES 的显示名去掉英文括注部分即菜单值）
        code_by_name = {name: code for code, name in self._language_names.items()}
        lang_code = code_by_name.get(choice, i18n_module.DEFAULT_LANGUAGE)
        _ = i18n_module.set_language(lang_code)
        # 写回 config.ini（行级更新保留注释；失败仅告警，不影响内存态切换）
        try:
            if not update_config_line(self.main_config_file, "录制设置", "language(zh_cn/en)", lang_code):
                self._log(f"语言切换成功（{lang_code}），但配置写回失败：未找到 language 配置行", "warning")
            else:
                self._log(f"语言已切换: {lang_code}（录制子进程重启后同步生效）")
        except Exception as e:
            self._log(f"语言切换成功（{lang_code}），但配置写回失败: {e}", "warning")

    # 主题切换后同步所有自绘 Canvas（状态圆点）背景色。
    def _sync_canvas_bg(self) -> None:
        # 同步所有自绘 Canvas 的背景色（主题切换后调用）
        self._sync_dot_bg()
        self._sync_big_dot_bg()

    # 同步侧边栏状态圆点的画布背景色（Canvas 不随主题自动变化）。
    def _sync_dot_bg(self) -> None:
        # 同步状态圆点画布背景色（Canvas 不随主题自动变化）
        try:
            mode = ctk.get_appearance_mode().lower()
            bg = Colors.BG_DARK if mode == "dark" else Colors.BG_LIGHT
            self._sidebar_dot.configure(bg=bg)
        except Exception:
            pass

    # 构建右侧内容区并叠放四个页面（tkraise 切换）。
    def _build_content(self) -> None:
        # 构建右侧内容区（三个页面叠放，tkraise 切换）
        container = ctk.CTkFrame(self.root, fg_color=(Colors.BG_LIGHT, Colors.BG_DARK))
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

    # 创建带可选标题的圆角卡片容器，返回卡片 Frame。
    def _create_card(self, parent: ctk.CTkFrame, title: str = "") -> ctk.CTkFrame:
        # 创建圆角卡片容器
        card = ctk.CTkFrame(
            parent,
            corner_radius=12,
            fg_color=(Colors.CARD_LIGHT, Colors.CARD_DARK),
            border_width=1,
            border_color=(Colors.BORDER_LIGHT, Colors.BORDER_DARK),
        )
        if title:
            header = ctk.CTkFrame(card, fg_color="transparent", height=46)
            header.pack(fill=tk.X)
            header.pack_propagate(False)
            ctk.CTkLabel(
                header, text=title, font=Fonts.body(bold=True), text_color=(Colors.TEXT_LIGHT, Colors.TEXT_DARK)
            ).pack(side=tk.LEFT, padx=18, pady=12)
        return card

    # ─── 页面：控制台 ───────────────────────────────────────

    # 构建控制台页：状态总览、录制控制与快捷操作卡片。
    def _build_dashboard_page(self, parent: ctk.CTkFrame) -> ctk.CTkFrame:
        # 控制台页面：大状态卡片 + 录制控制 + 快捷操作
        page = ctk.CTkFrame(parent, fg_color="transparent")
        page.grid_columnconfigure(0, weight=1)
        page.grid_rowconfigure(0, weight=0)
        page.grid_rowconfigure(1, weight=0)
        page.grid_rowconfigure(2, weight=1)

        # ── 状态总览卡片 ──
        status_card = self._create_card(page)
        status_card.grid(row=0, column=0, sticky="ew", pady=(0, 14))
        status_card.grid_columnconfigure(1, weight=1)

        # 左侧大圆点（呼吸动画）
        dot_wrap = ctk.CTkFrame(status_card, fg_color="transparent", width=90, height=90)
        dot_wrap.grid(row=0, column=0, padx=(20, 6), pady=22)
        dot_wrap.grid_propagate(False)
        self._big_dot = tk.Canvas(dot_wrap, width=64, height=64, highlightthickness=0, bd=0)
        self._big_dot.place(relx=0.5, rely=0.5, anchor=tk.CENTER)
        self._big_dot_item = self._big_dot.create_oval(8, 8, 56, 56, fill=Colors.DANGER, outline="")
        self._sync_big_dot_bg()

        # 中间：状态文字
        mid = ctk.CTkFrame(status_card, fg_color="transparent")
        mid.grid(row=0, column=1, sticky="w", pady=18)
        self.big_status_label = ctk.CTkLabel(
            mid, text="待 机", font=Fonts.big_status(), text_color=(Colors.TEXT_LIGHT, Colors.TEXT_DARK)
        )
        self.big_status_label.pack(anchor=tk.W)
        self.big_status_sub = ctk.CTkLabel(
            mid, text="录制进程未运行", font=Fonts.body(), text_color=(Colors.MUTED_LIGHT, Colors.MUTED_DARK)
        )
        self.big_status_sub.pack(anchor=tk.W, pady=(2, 0))

        # 右侧：信息网格（2 列 x 2 行）
        info = ctk.CTkFrame(status_card, fg_color="transparent")
        info.grid(row=0, column=2, padx=24, pady=18, sticky="e")

        self.info_interval = self._add_info_item(info, "循环检测", "-", 0, 0)
        self.info_format = self._add_info_item(info, "输出格式", "-", 0, 1)
        self.info_tray = self._add_info_item(info, "系统托盘", "-", 1, 0)
        self.info_time = self._add_info_item(info, "当前时间", "-", 1, 1)

        # ── 录制控制卡片 ──
        ctrl_card = self._create_card(page, "录制控制")
        ctrl_card.grid(row=1, column=0, sticky="ew", pady=(0, 14))

        ctrl_body = ctk.CTkFrame(ctrl_card, fg_color="transparent")
        ctrl_body.pack(fill=tk.X, padx=18, pady=(0, 16))

        self.start_btn = ctk.CTkButton(
            ctrl_body,
            text="▶   开始录制",
            command=self.start_recording,
            font=Fonts.heading(),
            height=48,
            corner_radius=10,
            fg_color=Colors.SUCCESS,
            hover_color=Colors.SUCCESS_HOVER,
            text_color="#FFFFFF",
            width=200,
        )
        self.start_btn.pack(side=tk.LEFT, padx=(0, 12))

        self.stop_btn = ctk.CTkButton(
            ctrl_body,
            text="⏹   停止录制",
            command=self.stop_recording,
            font=Fonts.heading(),
            height=48,
            corner_radius=10,
            fg_color=Colors.DANGER,
            hover_color=Colors.DANGER_HOVER,
            text_color="#FFFFFF",
            width=200,
            state=tk.DISABLED,
        )
        self.stop_btn.pack(side=tk.LEFT)

        ctk.CTkLabel(
            ctrl_body,
            text="启动后将调用 main.py 循环监测 URL 配置中的直播间并自动录制",
            font=Fonts.small(),
            text_color=(Colors.MUTED_LIGHT, Colors.MUTED_DARK),
        ).pack(side=tk.LEFT, padx=20)

        # ── 快捷操作卡片 ──
        quick_card = self._create_card(page, "快捷操作")
        quick_card.grid(row=2, column=0, sticky="new")

        quick_body = ctk.CTkFrame(quick_card, fg_color="transparent")
        quick_body.pack(fill=tk.X, padx=18, pady=(0, 16))

        ctk.CTkButton(
            quick_body,
            text="📂   打开下载目录",
            command=self.open_downloads_folder,
            font=Fonts.body(),
            height=40,
            corner_radius=8,
            width=170,
            fg_color=(Colors.BG_LIGHT, Colors.BG_DARK),
            text_color=(Colors.TEXT_LIGHT, Colors.TEXT_DARK),
            border_width=1,
            border_color=(Colors.BORDER_LIGHT, Colors.BORDER_DARK),
            hover_color=(Colors.BORDER_LIGHT, Colors.BORDER_DARK),
        ).pack(side=tk.LEFT, padx=(0, 10))

        ctk.CTkButton(
            quick_body,
            text="⚙   高级设置",
            command=self.open_advanced_settings,
            font=Fonts.body(),
            height=40,
            corner_radius=8,
            width=150,
            fg_color=(Colors.BG_LIGHT, Colors.BG_DARK),
            text_color=(Colors.TEXT_LIGHT, Colors.TEXT_DARK),
            border_width=1,
            border_color=(Colors.BORDER_LIGHT, Colors.BORDER_DARK),
            hover_color=(Colors.BORDER_LIGHT, Colors.BORDER_DARK),
        ).pack(side=tk.LEFT)

        return page

    # 在状态卡片添加一项信息（标签 + 值），返回值标签以便后续更新。
    def _add_info_item(self, parent: ctk.CTkFrame, label: str, value: str, row: int, col: int) -> ctk.CTkLabel:
        # 在状态卡片中添加一个信息项，返回值标签便于后续更新
        box = ctk.CTkFrame(parent, fg_color="transparent")
        box.grid(row=row, column=col, padx=16, pady=6, sticky="w")
        ctk.CTkLabel(box, text=label, font=Fonts.small(), text_color=(Colors.MUTED_LIGHT, Colors.MUTED_DARK)).pack(
            anchor=tk.W
        )
        val = ctk.CTkLabel(
            box, text=value, font=Fonts.body(bold=True), text_color=(Colors.TEXT_LIGHT, Colors.TEXT_DARK)
        )
        val.pack(anchor=tk.W)
        return val

    # 同步控制台大状态圆点的画布背景色（Canvas 不随主题自动变化）。
    def _sync_big_dot_bg(self) -> None:
        # 同步大圆点画布背景（Canvas 不随主题自动变化）
        try:
            mode = ctk.get_appearance_mode().lower()
            bg = Colors.CARD_DARK if mode == "dark" else Colors.CARD_LIGHT
            self._big_dot.configure(bg=bg)
        except Exception:
            pass

    # ─── 页面：URL 配置 ─────────────────────────────────────

    # 构建 URL 配置编辑页（文本编辑器 + 重新读取 / 保存按钮）。
    def _build_config_page(self, parent: ctk.CTkFrame) -> ctk.CTkFrame:
        # URL 配置编辑页面
        page = ctk.CTkFrame(parent, fg_color="transparent")
        page.grid_columnconfigure(0, weight=1)
        page.grid_rowconfigure(0, weight=1)

        card = self._create_card(page, "📝  URL 配置编辑区 (config/URL_config.ini)")
        card.grid(row=0, column=0, sticky="nsew")

        # 编辑器
        editor_wrap = ctk.CTkFrame(card, fg_color="transparent")
        editor_wrap.pack(fill=tk.BOTH, expand=True, padx=14, pady=(0, 6))

        self.config_text = ctk.CTkTextbox(
            editor_wrap,
            wrap="none",
            font=Fonts.mono(),
            corner_radius=10,
            border_width=1,
            border_color=(Colors.BORDER_LIGHT, Colors.BORDER_DARK),
            activate_scrollbars=True,
        )
        self.config_text.pack(fill=tk.BOTH, expand=True)

        # 提示
        ctk.CTkLabel(
            card,
            text="每行一个直播链接，支持 # 开头的注释行  │  外部修改文件后将自动重新加载  │  点击窗口关闭按钮将最小化到系统托盘",
            font=Fonts.small(),
            text_color=(Colors.MUTED_LIGHT, Colors.MUTED_DARK),
            anchor=tk.W,
        ).pack(fill=tk.X, padx=18, pady=(4, 4))

        # 操作按钮
        btn_row = ctk.CTkFrame(card, fg_color="transparent")
        btn_row.pack(fill=tk.X, padx=14, pady=(4, 14))

        self.reload_btn = ctk.CTkButton(
            btn_row,
            text="🔄   重新读取",
            command=self._load_config,
            font=Fonts.body(),
            height=38,
            corner_radius=8,
            width=140,
            fg_color="transparent",
            text_color=(Colors.TEXT_LIGHT, Colors.TEXT_DARK),
            border_width=1,
            border_color=(Colors.BORDER_LIGHT, Colors.BORDER_DARK),
            hover_color=(Colors.BG_LIGHT, Colors.BG_DARK),
        )
        self.reload_btn.pack(side=tk.RIGHT, padx=(8, 0))

        self.save_btn = ctk.CTkButton(
            btn_row,
            text="💾   保存 URL 配置",
            command=self.save_config,
            font=Fonts.body(bold=True),
            height=38,
            corner_radius=8,
            width=160,
            fg_color=Colors.PRIMARY,
            hover_color=Colors.PRIMARY_HOVER,
            text_color="#FFFFFF",
        )
        self.save_btn.pack(side=tk.RIGHT)

        return page

    # ─── 页面：运行日志 ─────────────────────────────────────

    # 构建运行日志页（终端风格文本框 + 清空日志按钮）。
    def _build_logs_page(self, parent: ctk.CTkFrame) -> ctk.CTkFrame:
        # 运行日志页面（终端风格）
        page = ctk.CTkFrame(parent, fg_color="transparent")
        page.grid_columnconfigure(0, weight=1)
        page.grid_rowconfigure(0, weight=1)

        card = self._create_card(page, "📋  运行日志 (main.py 输出)")
        card.grid(row=0, column=0, sticky="nsew")

        # 终端容器
        term_wrap = ctk.CTkFrame(card, fg_color=Colors.TERMINAL_BG, corner_radius=10)
        term_wrap.pack(fill=tk.BOTH, expand=True, padx=14, pady=(0, 6))

        self.log_text = tk.Text(
            term_wrap,
            wrap=tk.WORD,
            font=Fonts.mono(),
            bg=Colors.TERMINAL_BG,
            fg=Colors.TERMINAL_FG,
            insertbackground="#FFFFFF",
            relief=tk.FLAT,
            bd=0,
            padx=12,
            pady=10,
            state=tk.DISABLED,
            selectbackground=Colors.TERMINAL_SELECT,
            selectforeground="#FFFFFF",
        )
        scrollbar = ctk.CTkScrollbar(
            term_wrap,
            command=cast("Callable[..., None]", self.log_text.yview),
            fg_color=Colors.TERMINAL_BG,
            button_color="#30363D",
            button_hover_color="#484F58",
        )
        self.log_text.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y, padx=(0, 4), pady=4)
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.log_text.tag_config("error", foreground=Colors.TERMINAL_ERROR)
        self.log_text.tag_config("warn", foreground=Colors.TERMINAL_WARN)

        # 底部操作栏
        btn_row = ctk.CTkFrame(card, fg_color="transparent")
        btn_row.pack(fill=tk.X, padx=14, pady=(4, 14))

        ctk.CTkButton(
            btn_row,
            text="🗑   清空日志",
            command=self._clear_log,
            font=Fonts.body(),
            height=36,
            corner_radius=8,
            width=130,
            fg_color="transparent",
            text_color=(Colors.TEXT_LIGHT, Colors.TEXT_DARK),
            border_width=1,
            border_color=(Colors.BORDER_LIGHT, Colors.BORDER_DARK),
            hover_color=(Colors.BG_LIGHT, Colors.BG_DARK),
        ).pack(side=tk.RIGHT)

        ctk.CTkLabel(
            btn_row,
            text="日志超过 1000 行将自动截断",
            font=Fonts.small(),
            text_color=(Colors.MUTED_LIGHT, Colors.MUTED_DARK),
        ).pack(side=tk.LEFT, padx=6)

        return page

    # ─── 页面：画质监控 ─────────────────────────────────────

    # 构建画质监控页（统计卡片 + 实时详情列表）。
    def _build_quality_page(self, parent: ctk.CTkFrame) -> ctk.CTkFrame:
        # 画质监控页面：检测各直播间实际画质是否与设置一致
        page = ctk.CTkFrame(parent, fg_color="transparent")
        page.grid_columnconfigure(0, weight=1)
        page.grid_rowconfigure(1, weight=1)

        # 统计卡片
        summary_card = self._create_card(page)
        summary_card.grid(row=0, column=0, sticky="ew", pady=(0, 14))

        summary_body = ctk.CTkFrame(summary_card, fg_color="transparent")
        summary_body.pack(fill=tk.X, padx=18, pady=16)
        summary_body.grid_columnconfigure((0, 1, 2), weight=1)

        self._q_stat_total = self._add_stat_item(summary_body, "录制中", "0", 0, Colors.PRIMARY)
        self._q_stat_ok = self._add_stat_item(summary_body, "画质正常", "0", 1, Colors.SUCCESS)
        self._q_stat_down = self._add_stat_item(summary_body, "画质降级", "0", 2, Colors.DANGER)

        # 详情卡片
        detail_card = self._create_card(page, "🎯  画质监控（实时检测实际画质是否与设置一致）")
        detail_card.grid(row=1, column=0, sticky="nsew")

        inner = ctk.CTkFrame(detail_card, fg_color="transparent")
        inner.pack(fill=tk.BOTH, expand=True, padx=14, pady=(0, 14))

        self._quality_scroll = ctk.CTkScrollableFrame(inner, fg_color="transparent")
        self._quality_scroll.pack(fill=tk.BOTH, expand=True)

        # 初始空状态
        ctk.CTkLabel(
            self._quality_scroll,
            text="暂无录制中的直播间\n\n启动录制后，将自动检测各直播间的实际画质是否与设置一致",
            font=Fonts.body(),
            text_color=(Colors.MUTED_LIGHT, Colors.MUTED_DARK),
            justify=tk.CENTER,
        ).pack(pady=60)

        return page

    # 在统计卡片添加一项统计（标签 + 值），返回值标签（画质/弹幕监控页共用）。
    def _add_stat_item(self, parent: ctk.CTkFrame, label: str, value: str, col: int, color: str) -> ctk.CTkLabel:
        # 在统计卡片中添加一个统计项，返回值标签便于后续更新
        box = ctk.CTkFrame(parent, fg_color="transparent")
        box.grid(row=0, column=col, padx=10, pady=4, sticky="ew")
        box.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(box, text=label, font=Fonts.small(), text_color=(Colors.MUTED_LIGHT, Colors.MUTED_DARK)).pack(
            anchor=tk.CENTER
        )
        val = ctk.CTkLabel(box, text=value, font=Fonts.title(), text_color=color)
        val.pack(anchor=tk.CENTER, pady=(2, 0))
        return val

    # 添加画质监控详情表的表头行（主播 / 设置 / 实际 / 状态 / 时间）。
    def _add_quality_header_row(self) -> None:
        # 添加画质监控表头行
        header = ctk.CTkFrame(self._quality_scroll, fg_color="transparent", height=28)
        header.pack(fill=tk.X, pady=(0, 2))
        header.pack_propagate(False)
        header.grid_columnconfigure(0, weight=3)
        header.grid_columnconfigure(1, weight=1)
        header.grid_columnconfigure(2, weight=1)
        header.grid_columnconfigure(3, weight=1)
        header.grid_columnconfigure(4, weight=2)
        for col, text in enumerate(["主播名称", "设置画质", "实际画质", "状态", "告警时间"]):
            ctk.CTkLabel(
                header,
                text=text,
                font=Fonts.small(bold=True),
                text_color=(Colors.MUTED_LIGHT, Colors.MUTED_DARK),
                anchor=tk.W,
            ).grid(row=0, column=col, sticky=tk.W, padx=6, pady=4)

    # 添加一行画质监控数据（按降级状态着色显示）。
    def _add_quality_data_row(self, name: str, info: dict[str, str | bool | float]) -> None:
        # 添加一行画质监控数据
        downgraded = bool(info.get("downgraded", False))
        # info 值为 str | bool | float 联合，而 CTkLabel.text 仅接受 str，统一转字符串展示
        set_q = str(info.get("set_quality", "—"))
        actual_q = str(info.get("actual_quality", ""))
        alert_time = str(info.get("alert_time", ""))

        if downgraded:
            actual_display = actual_q or "—"
            status_text = "⚠ 降级"
            status_color = Colors.DANGER
            actual_color = Colors.DANGER
            row_fg: str | tuple[str, str] = ("#FEF2F2", "#2A1518")
        else:
            actual_display = "✓ 同等"
            status_text = "✓ 正常"
            status_color = Colors.SUCCESS
            actual_color = Colors.SUCCESS
            row_fg = "transparent"

        row = ctk.CTkFrame(self._quality_scroll, fg_color=row_fg, corner_radius=6, height=34)
        row.pack(fill=tk.X, pady=1)
        row.pack_propagate(False)
        row.grid_columnconfigure(0, weight=3)
        row.grid_columnconfigure(1, weight=1)
        row.grid_columnconfigure(2, weight=1)
        row.grid_columnconfigure(3, weight=1)
        row.grid_columnconfigure(4, weight=2)

        ctk.CTkLabel(
            row, text=name, font=Fonts.body(), text_color=(Colors.TEXT_LIGHT, Colors.TEXT_DARK), anchor=tk.W
        ).grid(row=0, column=0, sticky=tk.W, padx=6, pady=5)
        ctk.CTkLabel(
            row, text=set_q, font=Fonts.body(), text_color=(Colors.TEXT_LIGHT, Colors.TEXT_DARK), anchor=tk.W
        ).grid(row=0, column=1, sticky=tk.W, padx=4, pady=5)
        ctk.CTkLabel(
            row, text=actual_display, font=Fonts.body(bold=downgraded), text_color=actual_color, anchor=tk.W
        ).grid(row=0, column=2, sticky=tk.W, padx=4, pady=5)
        ctk.CTkLabel(row, text=status_text, font=Fonts.body(bold=True), text_color=status_color, anchor=tk.W).grid(
            row=0, column=3, sticky=tk.W, padx=4, pady=5
        )
        ctk.CTkLabel(
            row,
            text=alert_time if downgraded else "—",
            font=Fonts.small(),
            text_color=(Colors.MUTED_LIGHT, Colors.MUTED_DARK),
            anchor=tk.W,
        ).grid(row=0, column=4, sticky=tk.W, padx=4, pady=5)

    # ─── 页面：弹幕监控 ─────────────────────────────────────

    # 构建弹幕监控页（统计卡片 + 房间明细表 + 终端风格实时弹幕流）。
    def _build_danmaku_page(self, parent: ctk.CTkFrame) -> ctk.CTkFrame:
        # 弹幕监控页面：数据来自 tail 线程解析 logs/danmaku_monitor.jsonl
        page = ctk.CTkFrame(parent, fg_color="transparent")
        page.grid_columnconfigure(0, weight=1)
        page.grid_rowconfigure(0, weight=0)
        page.grid_rowconfigure(1, weight=0)
        page.grid_rowconfigure(2, weight=1)

        # 统计卡片
        summary_card = self._create_card(page)
        summary_card.grid(row=0, column=0, sticky="ew", pady=(0, 14))

        summary_body = ctk.CTkFrame(summary_card, fg_color="transparent")
        summary_body.pack(fill=tk.X, padx=18, pady=16)
        summary_body.grid_columnconfigure((0, 1, 2), weight=1)

        self._dm_stat_rooms = self._add_stat_item(summary_body, "监控房间", "0", 0, Colors.PRIMARY)
        self._dm_stat_connected = self._add_stat_item(summary_body, "已连接", "0", 1, Colors.SUCCESS)
        self._dm_stat_msgs = self._add_stat_item(summary_body, "累计弹幕", "0", 2, Colors.PRIMARY)

        # 房间明细卡片
        detail_card = self._create_card(page, "💬  弹幕房间（连接状态 / 累计弹幕 / 速率 / 礼物）")
        detail_card.grid(row=1, column=0, sticky="ew", pady=(0, 14))

        inner = ctk.CTkFrame(detail_card, fg_color="transparent")
        inner.pack(fill=tk.BOTH, expand=True, padx=14, pady=(0, 14))

        self._dm_scroll = ctk.CTkScrollableFrame(inner, fg_color="transparent", height=150)
        self._dm_scroll.pack(fill=tk.BOTH, expand=True)

        ctk.CTkLabel(
            self._dm_scroll,
            text="暂无弹幕监控数据\n\n启动录制并在 config.ini 开启「是否弹幕监控(是/否)」后，"
            "支持弹幕的平台（斗鱼/B站/虎牙/抖音/Twitch）将显示实时弹幕",
            font=Fonts.body(),
            text_color=(Colors.MUTED_LIGHT, Colors.MUTED_DARK),
            justify=tk.CENTER,
        ).pack(pady=30)

        # 实时弹幕流卡片
        stream_card = self._create_card(page, "📋  实时弹幕")
        stream_card.grid(row=2, column=0, sticky="nsew")

        stream_inner = ctk.CTkFrame(stream_card, fg_color="transparent")
        stream_inner.pack(fill=tk.BOTH, expand=True, padx=14, pady=(0, 14))

        # 工具栏：房间筛选 + 清空
        toolbar = ctk.CTkFrame(stream_inner, fg_color="transparent")
        toolbar.pack(fill=tk.X, pady=(0, 8))

        self._dm_filter_menu = ctk.CTkOptionMenu(
            toolbar,
            values=["全部房间"],
            command=self._on_danmaku_filter_change,
            font=Fonts.small(),
            corner_radius=8,
            height=30,
            width=200,
            fg_color=(Colors.BG_LIGHT, Colors.BG_DARK),
            button_color=("#D6DAE5", "#2A3040"),
            button_hover_color=("#C3C9D8", "#343B4E"),
            text_color=(Colors.TEXT_LIGHT, Colors.TEXT_DARK),
            dropdown_fg_color=(Colors.CARD_LIGHT, Colors.CARD_DARK),
            dropdown_text_color=(Colors.TEXT_LIGHT, Colors.TEXT_DARK),
            dropdown_hover_color=(Colors.PRIMARY_SOFT_LIGHT, Colors.PRIMARY_SOFT_DARK),
        )
        self._dm_filter_menu.pack(side=tk.LEFT)
        self._dm_filter_menu.set("全部房间")

        ctk.CTkButton(
            toolbar,
            text="🗑   清空",
            command=self._clear_danmaku,
            font=Fonts.small(),
            height=30,
            corner_radius=8,
            width=90,
            fg_color="transparent",
            text_color=(Colors.TEXT_LIGHT, Colors.TEXT_DARK),
            border_width=1,
            border_color=(Colors.BORDER_LIGHT, Colors.BORDER_DARK),
            hover_color=(Colors.BG_LIGHT, Colors.BG_DARK),
        ).pack(side=tk.RIGHT)

        ctk.CTkLabel(
            toolbar,
            text="高频房间弹幕按每秒 10 条采样展示，统计计数始终精确",
            font=Fonts.small(),
            text_color=(Colors.MUTED_LIGHT, Colors.MUTED_DARK),
        ).pack(side=tk.RIGHT, padx=(0, 12))

        # 终端容器
        term_wrap = ctk.CTkFrame(stream_inner, fg_color=Colors.TERMINAL_BG, corner_radius=10)
        term_wrap.pack(fill=tk.BOTH, expand=True)

        self.danmaku_text = tk.Text(
            term_wrap,
            wrap=tk.WORD,
            font=Fonts.mono(),
            bg=Colors.TERMINAL_BG,
            fg=Colors.TERMINAL_FG,
            insertbackground="#FFFFFF",
            relief=tk.FLAT,
            bd=0,
            padx=12,
            pady=10,
            state=tk.DISABLED,
            selectbackground=Colors.TERMINAL_SELECT,
            selectforeground="#FFFFFF",
        )
        dm_scrollbar = ctk.CTkScrollbar(
            term_wrap,
            command=cast("Callable[..., None]", self.danmaku_text.yview),
            fg_color=Colors.TERMINAL_BG,
            button_color="#30363D",
            button_hover_color="#484F58",
        )
        self.danmaku_text.configure(yscrollcommand=dm_scrollbar.set)
        dm_scrollbar.pack(side=tk.RIGHT, fill=tk.Y, padx=(0, 4), pady=4)
        self.danmaku_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # 弹幕类型着色：普通弹幕用默认前景，礼物黄色，SC 粉色，采样折叠灰斜体
        self.danmaku_text.tag_config("gift", foreground=Colors.TERMINAL_WARN)
        self.danmaku_text.tag_config("superChat", foreground="#DB61A2")
        self.danmaku_text.tag_config("dropped", foreground="#8B949E", font=(_MONO_FAMILY, 10, "italic"))

        return page

    # 添加弹幕房间明细表的表头行（房间/平台/状态/累计/速率/礼物/在线/开始时间）。
    def _add_danmaku_header_row(self) -> None:
        header = ctk.CTkFrame(self._dm_scroll, fg_color="transparent", height=28)
        header.pack(fill=tk.X, pady=(0, 2))
        header.pack_propagate(False)
        weights = [3, 2, 1, 1, 1, 1, 1, 2]
        for col, w in enumerate(weights):
            header.grid_columnconfigure(col, weight=w)
        for col, text in enumerate(["房间", "平台", "状态", "累计弹幕", "速率(条/分)", "礼物", "在线", "开始时间"]):
            ctk.CTkLabel(
                header,
                text=text,
                font=Fonts.small(bold=True),
                text_color=(Colors.MUTED_LIGHT, Colors.MUTED_DARK),
                anchor=tk.W,
            ).grid(row=0, column=col, sticky=tk.W, padx=6, pady=4)

    # 添加一行弹幕房间数据（断开连接的行整行淡化）。
    def _add_danmaku_data_row(self, name: str, info: dict[str, str | bool | int]) -> None:
        connected = bool(info.get("connected", False))
        weights = [3, 2, 1, 1, 1, 1, 1, 2]

        row = ctk.CTkFrame(
            self._dm_scroll,
            fg_color="transparent" if connected else ("#F8FAFC", "#1C2029"),
            corner_radius=6,
            height=32,
        )
        row.pack(fill=tk.X, pady=1)
        row.pack_propagate(False)
        for col, w in enumerate(weights):
            row.grid_columnconfigure(col, weight=w)

        normal_color = (Colors.TEXT_LIGHT, Colors.TEXT_DARK) if connected else (Colors.MUTED_LIGHT, Colors.MUTED_DARK)
        cells: list[tuple[str, str | bool | int | float, str, bool]] = [
            ("房间", name, "normal", True),
            ("平台", str(info.get("platform", "—")), "normal", False),
            ("状态", "已连接" if connected else "已断开", "status", False),
            ("累计弹幕", str(info.get("msg_total", 0)), "normal", False),
            ("速率(条/分)", str(info.get("msg_rate", 0)), "normal", False),
            ("礼物", str(info.get("gift_total", 0)), "normal", False),
            ("在线", str(info.get("online", 0)), "normal", False),
            ("开始时间", str(info.get("started_at", "—")), "muted", False),
        ]
        for col, (_label, value, kind, bold) in enumerate(cells):
            if kind == "status":
                color: str | tuple[str, str] = Colors.SUCCESS if connected else Colors.DANGER
            elif kind == "muted":
                color = (Colors.MUTED_LIGHT, Colors.MUTED_DARK)
            else:
                color = normal_color
            ctk.CTkLabel(
                row,
                text=str(value),
                font=Fonts.body(bold=bold),
                text_color=color,
                anchor=tk.W,
            ).grid(row=0, column=col, sticky=tk.W, padx=6, pady=4)

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
        # 清空日志显示
        self.log_text.config(state=tk.NORMAL)
        self.log_text.delete("1.0", tk.END)
        self.log_text.config(state=tk.DISABLED)

    # ─── 状态指示器动画 ─────────────────────────────────────

    # 启动大状态圆点的呼吸式动画（若未在运行）。
    def _start_status_animation(self) -> None:
        # 启动状态指示器呼吸动画
        if self._status_animating:
            return
        self._status_animating = True
        self._status_anim_index = 0
        self._animate_status_dot()

    # 停止状态指示器动画并取消定时回调。
    def _stop_status_animation(self) -> None:
        # 停止状态指示器动画
        self._status_animating = False
        if self._status_anim_timer is not None:
            try:
                self.root.after_cancel(self._status_anim_timer)
            except Exception:
                pass
            self._status_anim_timer = None

    # 状态圆点呼吸动画的单帧回调（大小 + 亮度往返渐变）。
    def _animate_status_dot(self) -> None:
        # 状态指示器动画帧回调（呼吸式脉冲：大小 + 亮度）
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
        # 设置状态指示器状态（idle/recording）
        self._sync_dot_bg()
        self._sync_big_dot_bg()
        if running:
            self._sidebar_dot.itemconfig(self._sidebar_dot_item, fill=Colors.SUCCESS)
            self._start_status_animation()
        else:
            self._stop_status_animation()
            try:
                self._big_dot.coords(self._big_dot_item, 8, 8, 56, 56)
                self._big_dot.itemconfig(self._big_dot_item, fill=color)
            except Exception:
                pass
            self._sidebar_dot.itemconfig(self._sidebar_dot_item, fill=color)
        self._update_status_bar()

    # ─── 配置读写 ──────────────────────────────────────────

    # 加载 URL_config.ini 到编辑器，并跳过无变化的重载。
    def _load_config(self) -> None:
        # 加载 URL 配置文件
        config_dir = os.path.dirname(self.url_config_file)
        os.makedirs(config_dir, exist_ok=True)

        if not os.path.exists(self.url_config_file):
            with open(self.url_config_file, "w", encoding="utf-8-sig") as f:
                f.write("")

        try:
            with open(self.url_config_file, "r", encoding="utf-8-sig") as f:
                content = f.read()

            current_content = self.config_text.get("1.0", tk.END).rstrip("\n")
            # 两侧统一去掉尾部换行再比较，否则文件末尾换行会导致比较永远失败
            if content.rstrip("\n") == current_content:
                self._last_url_config_mtime = os.path.getmtime(self.url_config_file)
                return

            self.config_text.delete("1.0", tk.END)
            self.config_text.insert("1.0", content)
            self._last_url_config_mtime = os.path.getmtime(self.url_config_file)
        except Exception as e:
            self._log(f"加载配置文件失败: {e}", "error")

    # 将编辑器中的 URL 配置写入 URL_config.ini 并提示。
    def save_config(self) -> None:
        # 保存 URL 配置文件
        try:
            _save_text_widget_to_file(self.config_text, self.url_config_file)
            self._last_url_config_mtime = os.path.getmtime(self.url_config_file)
            self._log("URL 配置已保存")
            messagebox.showinfo("成功", "URL 配置已保存成功！")
        except Exception as e:
            self._log(f"保存配置文件失败: {e}", "error")
            messagebox.showerror("错误", f"保存配置文件失败: {e}")

    # ─── 状态信息 ──────────────────────────────────────────

    # 从 config.ini 读取循环间隔 / 输出格式与托盘状态（带缓存）。
    def _get_dynamic_status_info(self) -> tuple[str, str, str]:
        # 获取动态状态信息，返回 (check_interval, output_format, tray_status)
        check_interval = "120秒"
        output_format = "ts → mp4"

        if not os.path.exists(self.main_config_file):
            return check_interval, output_format, self._tray_status_str()

        try:
            file_mtime = os.path.getmtime(self.main_config_file)
            if self._status_cache is not None and file_mtime == self._status_cache_mtime:
                ci, ofmt = self._status_cache
                return ci, ofmt, self._tray_status_str()

            config = configparser.ConfigParser()

            # mypy 不允许直接给方法 optionxform 赋值（"Cannot assign to a method"），
            # 用 setattr 绕过该误报；保持 key 原样（不转小写）以匹配中文配置节名。
            # 用 setattr 绕过 mypy "Cannot assign to a method" 误报；
            # lambda 显式标注 (str) -> str 以同时满足 basedpyright 的 reportUnknownLambdaType。
            # 配置项键名保持原样（不转小写），以匹配中文配置节名。
            def _preserve_case(optionstr: str) -> str:
                return optionstr

            setattr(config, "optionxform", _preserve_case)
            config.read(self.main_config_file, encoding="utf-8-sig")

            if "录制设置" in config:
                interval = config["录制设置"].get("循环时间(秒)", "120")
                check_interval = f"{interval}秒"

                fmt = config["录制设置"].get("录制完成后自动转为mp4格式", "否")
                if fmt == "是":
                    output_format = "ts → mp4"
                else:
                    save_fmt = config["录制设置"].get("视频保存格式ts|mkv|flv|mp4|mp3音频|m4a音频", "ts")
                    output_format = f"ts → {save_fmt}"

            self._status_cache = (check_interval, output_format)
            self._status_cache_mtime = file_mtime

        except Exception:
            pass

        return check_interval, output_format, self._tray_status_str()

    # 返回系统托盘是否启用的中文状态字符串。
    def _tray_status_str(self) -> str:
        # 返回托盘状态的字符串描述
        return "启用" if self.system_tray and self.system_tray.running else "未启动"

    # ─── 子进程管理 ────────────────────────────────────────

    # 跨平台打开 downloads 下载目录（不存在则先创建）。
    def open_downloads_folder(self) -> None:
        # 打开下载目录
        downloads_path = self.downloads_dir
        if not os.path.exists(downloads_path):
            os.makedirs(downloads_path, exist_ok=True)

        try:
            if sys.platform == "win32":
                os.startfile(downloads_path)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", downloads_path])
            else:
                subprocess.Popen(["xdg-open", downloads_path])
            self._log(f"已打开下载目录: {downloads_path}")
        except Exception as e:
            self._log(f"打开目录失败: {e}", "error")

    # 打开高级设置窗口以编辑 config.ini。
    def open_advanced_settings(self) -> None:
        # 打开高级设置窗口
        AdvancedSettingsWindow(self.root, self.main_config_file, self._log)

    # 启动录制：构造命令行拉起录制核心并接管其输出线程。
    def start_recording(self) -> None:
        # 开始录制
        if self._stopping:
            # 停止流程尚未完成，禁止在此期间启动新录制，避免竞态（双击停止/停止中误点启动）
            self._log("停止流程进行中，暂不可启动新录制", "warn")
            return
        if self.process is not None:
            messagebox.showwarning("警告", "录制已在运行中！")
            return

        try:
            # 冻结（PyInstaller 打包）模式下 sys.executable 指向 GUI exe 自身，
            # 若继续用 [sys.executable, main.py] 会递归拉起 GUI；
            # 改为直接调用同目录下的 CLI 可执行文件 DouyinLiveRecorder(.exe)。
            # 源码运行模式保持原行为不变。
            if getattr(sys, "frozen", False):
                cli_name = "DouyinLiveRecorder.exe" if sys.platform == "win32" else "DouyinLiveRecorder"
                # 冻结布局：GUI 自身位于 _internal/，CLI exe 与 GUI exe 同目录（_internal 的父目录）。
                # 平铺布局下 self.script_dir 即根目录，故向上回退一层仅在处于 _internal 时生效。
                base_dir = self.script_dir
                if os.path.basename(os.path.normpath(base_dir)) == "_internal":
                    base_dir = os.path.dirname(base_dir)
                cli_exe = os.path.join(base_dir, cli_name)
                if not os.path.isfile(cli_exe):
                    raise FileNotFoundError(f"未找到录制核心程序: {cli_exe}")
                record_cmd = [cli_exe]
            else:
                main_py = os.path.join(self.script_dir, "main.py")
                exe = sys.executable
                if sys.platform == "win32" and os.path.basename(exe).lower().startswith("pythonw"):
                    # pythonw.exe 是 GUI 子系统进程、没有控制台：CREATE_NEW_CONSOLE
                    # 对其无效，子进程将永远收不到 CTRL_BREAK（SIGBREAK），
                    # 优雅停止（safe_exit 清理 ffmpeg）结构性失效，只能整树强杀。
                    # 必须改用同目录的 python.exe（console 子系统）启动录制核心。
                    console_exe = os.path.join(os.path.dirname(exe), "python.exe")
                    if os.path.isfile(console_exe):
                        exe = console_exe
                    else:
                        self._log(f"未找到 console 解释器 {console_exe}，优雅停止将不可用", "warn")
                record_cmd = [exe, main_py]

            startupinfo = None
            env = os.environ.copy()
            env["PYTHONIOENCODING"] = "utf-8"
            if sys.platform == "win32":
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startupinfo.wShowWindow = subprocess.SW_HIDE

            creation_flags = 0
            if sys.platform == "win32":
                # CREATE_NEW_CONSOLE + SW_HIDE：给子进程一个隐藏控制台。
                # 若用 CREATE_NO_WINDOW，子进程没有控制台，CTRL_BREAK_EVENT
                # 永远送达不了，main.py 的 safe_exit 无法触发，停止录制只能
                # 等 15 秒超时后整树强杀。CREATE_NEW_PROCESS_GROUP 使
                # CTRL_BREAK 只投递给子进程组，不影响 GUI 自身。
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
            self.running = True
            self.start_btn.configure(state=tk.DISABLED)
            self.stop_btn.configure(state=tk.NORMAL)

            # 清空上一轮的画质监控数据，避免旧的降级告警残留到本次会话
            with self._quality_lock:
                self._quality_data.clear()
            self._quality_last_displayed = {}

            self._set_status(Colors.SUCCESS, True)
            self._update_status_bar()

            self.output_thread = threading.Thread(target=self._read_output, args=(proc,), daemon=True)
            self.output_thread.start()

            # 弹幕监控：tail 子进程写入的 logs/danmaku_monitor.jsonl
            self._start_danmaku_tail()

            self._log("━" * 40)
            self._log(f"录制进程已启动 (PID: {proc.pid})")
            self._log(f"执行程序: {record_cmd[0]}")
            self._log(f"工作目录: {self.script_dir}")
            self._log("━" * 40)

        except Exception as e:
            self._log(f"启动录制失败: {e}", "error")
            messagebox.showerror("错误", f"启动录制失败: {e}")
            # 启动失败时重置状态，允许用户重新启动
            self.process = None
            self.process_pid = None
            self.running = False
            self.start_btn.configure(state=tk.NORMAL)
            self.stop_btn.configure(state=tk.DISABLED)
            self._set_status(Colors.DANGER, False)
            self._update_status_bar()

    # 停止录制：发送信号优雅退出，超时则整树强杀 ffmpeg。
    def stop_recording(self) -> None:
        # 停止录制
        proc = self.process

        if proc is None:
            messagebox.showwarning("警告", "没有正在运行的录制进程！")
            return

        # 进入停止流程：置位标志并禁用启动按钮，避免停止窗口内被重复触发或误启动
        self._stopping = True
        self.stop_btn.configure(state=tk.DISABLED)
        self.start_btn.configure(state=tk.DISABLED)

        self._log("━" * 40)
        self._log("正在停止录制...")

        # 优雅退出：让 main.py 的信号处理器自行清理其下的 ffmpeg（孙子进程）。
        # 子进程启动时使用 CREATE_NEW_CONSOLE 隐藏控制台 + 独立进程组，
        # 因此 CTRL_BREAK_EVENT 能送达 main.py → SIGBREAK → safe_exit →
        # cleanup_all_ffmpeg_processes。proc.terminate() 在 Windows 上是
        # TerminateProcess 硬杀，会把 ffmpeg 孤儿化，仅作最后兜底。
        graceful_signal_sent = False
        if sys.platform == "win32":
            self._log("正在发送 CTRL_BREAK 信号（触发子进程 safe_exit 清理 ffmpeg）...")
            graceful_signal_sent = _send_ctrl_break_to_child(proc.pid)
            if not graceful_signal_sent:
                # 不能只 proc.terminate()：TerminateProcess 硬杀不会触发 main.py 的
                # safe_exit / atexit 兜底，其下 ffmpeg（孙进程）会孤儿化继续录制，
                # 且 wait() 会立即成功、绕过后面的 taskkill /T 兜底分支。
                # 必须用 taskkill /T 递归终止整棵进程树。
                self._log("发送 CTRL_BREAK 失败，整树强制终止（避免 ffmpeg 孤儿化）", "warn")
                try:
                    subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True, timeout=5)
                except Exception as e:
                    self._log(f"taskkill 整树终止失败，回退 terminate: {e}")
                    proc.terminate()
        else:
            self._log("正在发送 SIGINT 信号...")
            try:
                os.kill(proc.pid, signal.SIGINT)
            except Exception as e:
                self._log(f"发送 SIGINT 失败，回退 terminate: {e}")
                proc.terminate()

        # 后台等待子进程退出并清理，完成后路由 UI 线程更新。
        def _wait_and_update_ui() -> None:
            # 先等待子进程自行清理其下所有 ffmpeg，超时再整树强杀
            terminated = False
            try:
                proc.wait(timeout=15)
                terminated = True
                if graceful_signal_sent:
                    self._log("进程已优雅退出（ffmpeg 已由子进程清理）")
                else:
                    # 硬杀路径（taskkill /T 或 terminate 兜底）：main.py 的 safe_exit
                    # 没有机会运行，不能宣称"ffmpeg 已由子进程清理"
                    self._log("进程已终止（硬杀路径，ffmpeg 已随进程树终止）")
            except subprocess.TimeoutExpired:
                self._log("进程未能及时退出，整树强制终止...")
            except Exception as e:
                # wait 本身的异常（OSError 等）不应让线程静默死亡导致 _stopping 卡死
                self._log(f"等待子进程退出异常: {e}")

            if not terminated and proc.poll() is None:
                try:
                    if sys.platform == "win32":
                        # /T 递归杀掉 main.py 及其所有 ffmpeg 子进程，避免孤儿
                        subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True, timeout=5)
                    else:
                        proc.kill()
                        subprocess.run(["pkill", "-P", str(proc.pid), "-x", "ffmpeg"], capture_output=True, timeout=5)
                    proc.wait(timeout=5)
                    self._log("进程已强制终止")
                except subprocess.TimeoutExpired:
                    self._log("警告：进程可能仍在运行！")
                except Exception as e:
                    self._log(f"强制终止失败: {e}")

            self.running = False
            self.process = None
            self.process_pid = None
            self._stopping = False

            # 通过事件泵路由回 UI 线程（禁止直接跨线程调用 root.after）
            self.post_ui(self._on_recording_stopped)

        threading.Thread(target=_wait_and_update_ui, daemon=True).start()

    # 进程终止后在 UI 线程更新按钮状态与状态指示。
    def _on_recording_stopped(self) -> None:
        # 进程终止后的 UI 更新回调（在 UI 线程中执行）
        self._stop_danmaku_tail()
        self.start_btn.configure(state=tk.NORMAL)
        self.stop_btn.configure(state=tk.DISABLED)
        self._set_status(Colors.DANGER, False)
        self._update_status_bar()
        self._log("录制进程已停止")
        self._log("━" * 40)
        self._flush_log_queue()

    # 读取子进程输出流，解析画质日志并批量入队（线程安全）。
    def _read_output(self, proc: subprocess.Popen[str]) -> None:
        # 读取子进程输出。proc 由调用方显式传入并全程使用局部引用，
        # 避免停止后立即重启时本线程误读新进程的 stdout（两线程抢读同一管道）。
        batch: list[tuple[str, str]] = []
        batch_size = 10

        # 将缓冲的日志批次入队并标记有待刷新。
        def flush_batch() -> None:
            # 批量刷新日志队列到文本控件（只写队列，调度由 UI 线程泵负责）
            nonlocal batch
            if batch:
                self._log_queue.put(batch)
                with self._log_queue_lock:
                    self._log_queue_has_data = True
                batch = []

        if proc.stdout is None:
            self._log_queue.put(None)
            with self._log_queue_lock:
                self._log_queue_has_data = True
            return

        while True:
            try:
                line = cast(str, proc.stdout.readline())
                if not line:
                    if proc.poll() is not None:
                        flush_batch()
                        self.running = False
                        self._log_queue.put(None)
                        with self._log_queue_lock:
                            self._log_queue_has_data = True
                        break
                    # EOF 但进程仍在（管道瞬时无数据）：短暂等待避免忙等空转
                    time.sleep(0.05)
                    continue

                clean_line = self.ANSI_ESCAPE_PATTERN.sub("", line.rstrip())
                self._parse_quality_log(clean_line)
                batch.append((clean_line, "info"))

                if len(batch) >= batch_size:
                    flush_batch()

            except (ValueError, OSError) as e:
                error_msg = str(e)
                flush_batch()
                self._log_queue.put([(f"输出流已关闭: {error_msg}", "error")])
                self._log_queue.put(None)
                with self._log_queue_lock:
                    self._log_queue_has_data = True
                self.running = False
                break
            except Exception as e:
                error_msg = str(e)
                flush_batch()
                self._log_queue.put([(f"读取输出错误: {error_msg}", "error")])
                self._log_queue.put(None)
                with self._log_queue_lock:
                    self._log_queue_has_data = True
                self.running = False
                break

        flush_batch()

    # 定时从日志队列批量刷新消息到日志文本框（UI 线程）。
    def _schedule_log_flush(self) -> None:
        # 定时从队列批量刷新日志到 UI
        messages: list[tuple[str, str]] = []
        process_ended = False
        while True:
            try:
                item = self._log_queue.get_nowait()
                if item is None:
                    process_ended = True
                else:
                    messages.extend(item)
            except queue.Empty:
                break

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
                    tag = "normal"

                self.log_text.insert(tk.END, display_text, tag)

            total_lines = int(self.log_text.index("end-1c").split(".")[0])
            if total_lines > self._MAX_LOG_LINES:
                trim_count = total_lines - self._LOG_TRIM_TO
                self.log_text.delete("1.0", f"{trim_count + 1}.0")

            self.log_text.see(tk.END)
            self.log_text.config(state=tk.DISABLED)
            with self._log_queue_lock:
                self._log_queue_has_data = False

        if process_ended:
            self._process_ended()

        with self._log_queue_lock:
            has_data = self._log_queue_has_data
        if has_data or not self._log_queue.empty():
            self._log_flush_job_id = self.root.after(self._LOG_FLUSH_INTERVAL, self._schedule_log_flush)
        else:
            self._log_flush_job_id = None

    # 子进程自然结束后的 UI 收尾（重置状态与按钮）。
    def _process_ended(self) -> None:
        # 子进程结束回调（仅在 UI 线程中调用）
        # 等待输出线程收尾，确保所有日志都被读取到 UI 后再重置状态
        if self._stopping:
            # 手动停止流程进行中，生命周期由其（_on_recording_stopped）统一收尾，避免重复重置 UI
            return
        if self.output_thread and self.output_thread.is_alive():
            self.output_thread.join(timeout=5)
        self._stop_danmaku_tail()
        self.running = False
        self.process = None
        self.process_pid = None
        self.start_btn.configure(state=tk.NORMAL)
        self.stop_btn.configure(state=tk.DISABLED)

        self._set_status(Colors.DANGER, False)
        self._update_status_bar()

        self._log("━" * 40)
        self._log("录制进程已结束")
        self._log("━" * 40)

    # 线程安全地向日志队列追加一条消息（不触碰 Tk 对象）。
    def _log(self, message: str, level: str = "info") -> None:
        # 添加日志到队列（线程安全）。本方法不触碰任何 Tk 对象，
        # 可在任意线程调用；刷新链由 UI 线程泵 _pump_ui_events 按需激活。
        self._log_queue.put([(message, level)])
        with self._log_queue_lock:
            self._log_queue_has_data = True

    # 立即（UI 线程）刷新日志队列到文本控件。
    def _flush_log_queue(self) -> None:
        # 立即刷新日志队列到 UI（仅在 UI 线程中调用）
        if self._log_flush_job_id:
            self.root.after_cancel(self._log_flush_job_id)
            self._log_flush_job_id = None
        self._schedule_log_flush()
        with self._log_queue_lock:
            has_data = self._log_queue_has_data
        if has_data or not self._log_queue.empty():
            self._log_flush_job_id = self.root.after(self._LOG_FLUSH_INTERVAL, self._schedule_log_flush)

    # ─── 画质监控 ──────────────────────────────────────────

    # 解析日志行，提取画质降级告警与录制状态并更新监控数据。
    def _parse_quality_log(self, line: str) -> None:
        # 解析子进程日志行，提取画质降级告警和录制状态信息。
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

        # 画质降级告警："{name} 画质降级：设置 {zh}({code}) 实际 {zh}({code})"
        m = self.QUALITY_DOWNGRADE_PATTERN.search(msg)
        if m:
            name = m.group(1).strip()
            set_zh, set_code = m.group(2), m.group(3)
            actual_zh, actual_code = m.group(4), m.group(5)
            with self._quality_lock:
                info = self._quality_data.setdefault(name, {})
                info.update(
                    {
                        "set_quality": set_zh,
                        "actual_quality": actual_zh,
                        "downgraded": True,
                        "alert_time": self._get_timestamp(),
                        "alert_message": f"设置 {set_zh}({set_code}) 实际 {actual_zh}({actual_code})",
                        "recording": True,
                        "last_seen": time.time(),
                    }
                )
            return

        # 录制中行："{name}[{quality}] 正在录制中 {duration}"
        m = self.RECORDING_LINE_PATTERN.match(msg)
        if m:
            name = m.group(1).strip()
            quality = m.group(2).strip()
            with self._quality_lock:
                info = self._quality_data.setdefault(name, {})
                info["recording"] = True
                info["set_quality"] = quality
                info["last_seen"] = time.time()
                # 未检测到降级告警时，认为实际画质与设置一致
                if not info.get("downgraded"):
                    info["actual_quality"] = quality
            return

        # "没有正在录制" → 清除所有录制标记
        if "没有正在录制" in msg or "没有正在监测和录制的直播" in msg:
            with self._quality_lock:
                for info in self._quality_data.values():
                    info["recording"] = False

    # 在 UI 线程刷新画质监控页面与统计（仅限录制中的项）。
    def _update_quality_display(self) -> None:
        # 更新画质监控页面显示（仅在 UI 线程中调用）
        if not hasattr(self, "_quality_scroll"):
            return

        now = time.time()
        with self._quality_lock:
            # 清除超过 30 秒未更新的录制标记（直播已停止但未输出"没有正在录制"）
            for info in self._quality_data.values():
                if info.get("recording") and now - cast(float, info.get("last_seen", 0)) > 30:
                    info["recording"] = False

            data = {name: dict(info) for name, info in self._quality_data.items() if info.get("recording")}

        # 数据未变化时跳过重建，避免闪烁
        if data == self._quality_last_displayed:
            return
        self._quality_last_displayed = data

        # 清除旧行
        for widget in self._quality_scroll.winfo_children():
            widget.destroy()

        if not data:
            ctk.CTkLabel(
                self._quality_scroll,
                text="暂无录制中的直播间\n\n启动录制后，将自动检测各直播间的实际画质是否与设置一致",
                font=Fonts.body(),
                text_color=(Colors.MUTED_LIGHT, Colors.MUTED_DARK),
                justify=tk.CENTER,
            ).pack(pady=60)
        else:
            # 表头 + 数据行
            self._add_quality_header_row()
            for name, info in sorted(data.items()):
                self._add_quality_data_row(name, info)

        # 更新统计
        total = len(data)
        down_count = sum(1 for info in data.values() if info.get("downgraded"))
        ok_count = total - down_count
        try:
            self._q_stat_total.configure(text=str(total))
            self._q_stat_ok.configure(text=str(ok_count))
            self._q_stat_down.configure(text=str(down_count))
        except Exception:
            pass

    # ─── 弹幕监控（tail 边车 JSONL 文件） ──────────────────

    # 启动弹幕监控 tail 线程：清空上一轮数据后跟随 logs/danmaku_monitor.jsonl。
    def _start_danmaku_tail(self) -> None:
        self._stop_danmaku_tail()
        with self._danmaku_lock:
            self._danmaku_rooms.clear()
            self._danmaku_msgs.clear()
            self._danmaku_last_stats = None
            self._danmaku_stats_dirty = True
            self._danmaku_stream_dirty = True
        self._danmaku_tail_stop.clear()
        self._danmaku_tail_thread = threading.Thread(target=self._danmaku_tail_loop, name="danmaku-tail", daemon=True)
        self._danmaku_tail_thread.start()

    # 停止 tail 线程（幂等；已显示的数据保留，下次启动录制时清空）。
    def _stop_danmaku_tail(self) -> None:
        self._danmaku_tail_stop.set()
        t = self._danmaku_tail_thread
        if t is not None and t is not threading.current_thread() and t.is_alive():
            t.join(timeout=2)
        self._danmaku_tail_thread = None

    # tail 线程主体：二进制模式增量读取 JSONL（文本模式 tell 偏移不透明、不能与
    # 文件字节数比较），解码后按行分发事件；处理轮转回绕，首读仅回看末尾 64KB
    # 以免重放历史会话。
    def _danmaku_tail_loop(self) -> None:
        path = os.path.join(self.app_root, "logs", "danmaku_monitor.jsonl")
        offset = 0
        partial = ""
        first_open = True
        while not self._danmaku_tail_stop.is_set():
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
                for line in lines:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        event = json.loads(line)
                    except (ValueError, TypeError):
                        continue
                    if isinstance(event, dict):
                        self._danmaku_dispatch(event)
            except OSError:
                time.sleep(1.0)
            except Exception:
                time.sleep(1.0)

    # 分发一条 JSONL 事件到线程安全缓冲（tail 线程调用，只写锁内数据、不触碰 Tk）。
    # conn 事件维护房间连接状态；stats 事件为统计权威来源；msg 事件进入弹幕流缓冲。
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
                        "started_at": float(event.get("ts", 0.0)),
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
                info["msg_total"] = int(event.get("msg_total", info.get("msg_total", 0)))
                info["msg_rate"] = int(event.get("msg_rate", info.get("msg_rate", 0)))
                info["gift_total"] = int(event.get("gift_total", info.get("gift_total", 0)))
                info["online"] = int(event.get("online", info.get("online", 0)))
                self._danmaku_stats_dirty = True

    # 每秒刷新弹幕监控页（UI 线程）：统计表按脏标记重建，弹幕流按脏标记重绘。
    def _schedule_danmaku_refresh(self) -> None:
        self._update_danmaku_display()
        self._render_danmaku_stream()
        self._danmaku_refresh_job_id = self.root.after(1000, self._schedule_danmaku_refresh)

    # 在 UI 线程重建弹幕房间统计表与顶部统计（数据未变化时跳过，避免闪烁）。
    def _update_danmaku_display(self) -> None:
        if not hasattr(self, "_dm_scroll"):
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
            started_ts = float(info.get("started_at", 0.0))
            rows.append(
                {
                    "room": name,
                    "platform": str(info.get("platform", "—")),
                    "connected": bool(info.get("connected")),
                    "msg_total": int(info.get("msg_total", 0)),
                    "msg_rate": int(info.get("msg_rate", 0)),
                    "gift_total": int(info.get("gift_total", 0)),
                    "online": int(info.get("online", 0)),
                    "started_at": time.strftime("%H:%M:%S", time.localtime(started_ts)) if started_ts else "—",
                }
            )
            total_msgs += int(info.get("msg_total", 0))
            if bool(info.get("connected")):
                connected_count += 1

        if rows == self._danmaku_last_stats:
            return
        self._danmaku_last_stats = rows

        for widget in self._dm_scroll.winfo_children():
            widget.destroy()

        if not rows:
            ctk.CTkLabel(
                self._dm_scroll,
                text="暂无弹幕监控数据\n\n启动录制并在 config.ini 开启「是否弹幕监控(是/否)」后，"
                "支持弹幕的平台（斗鱼/B站/虎牙/抖音/Twitch）将显示实时弹幕",
                font=Fonts.body(),
                text_color=(Colors.MUTED_LIGHT, Colors.MUTED_DARK),
                justify=tk.CENTER,
            ).pack(pady=30)
        else:
            self._add_danmaku_header_row()
            for row in sorted(rows, key=lambda r: str(r["room"])):
                self._add_danmaku_data_row(str(row["room"]), row)

        # 顶部统计与筛选下拉（保持当前选择，房间列表变化时刷新选项）
        try:
            self._dm_stat_rooms.configure(text=str(len(rows)))
            self._dm_stat_connected.configure(text=str(connected_count))
            self._dm_stat_msgs.configure(text=str(total_msgs))
            current = self._dm_filter_menu.get()
            values = ["全部房间"] + sorted(rooms_snapshot.keys())
            self._dm_filter_menu.configure(values=values)
            if current not in values:
                self._dm_filter_menu.set("全部房间")
        except Exception:
            pass

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
            if filter_value != "全部房间" and room != filter_value:
                continue
            mtype = str(m.get("type", "chat"))
            ts = float(m.get("ts", 0.0))
            tstr = time.strftime("%H:%M:%S", time.localtime(ts)) if ts else "--:--:--"
            user = str(m.get("user", ""))
            text = str(m.get("text", ""))
            dropped = m.get("dropped")
            if mtype == "gift":
                tag, label = "gift", "[礼物] "
            elif mtype == "superChat":
                tag, label = "superChat", "[SC] "
            else:
                tag, label = "", ""
            line = f"[{tstr}] [{room}] {label}{user}: {text}\n" if user else f"[{tstr}] [{room}] {label}{text}\n"
            self.danmaku_text.insert(tk.END, line, tag)
            if dropped:
                self.danmaku_text.insert(tk.END, f"    （+{dropped} 条已省略）\n", "dropped")
            shown += 1
        if not shown:
            self.danmaku_text.insert(tk.END, "暂无弹幕数据\n")
        self.danmaku_text.config(state=tk.DISABLED)
        if at_bottom:
            self.danmaku_text.see(tk.END)

    # ─── 时间与状态栏 ──────────────────────────────────────

    @staticmethod
    # 返回当前本地时间的时间戳字符串。
    def _get_timestamp() -> str:
        # 获取当前时间戳
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # 刷新控制台状态文字与信息网格（间隔 / 格式 / 托盘 / 时间）。
    def _update_status_bar(self) -> None:
        # 更新状态显示（动态读取配置）
        try:
            check_interval, output_format, tray_status = self._get_dynamic_status_info()
            timestamp = self._get_timestamp()

            pid = self.process_pid
            if pid is not None:
                self.big_status_label.configure(text="录制中")
                self.big_status_sub.configure(text=f"录制进程运行中 (PID: {pid})")
                self.sidebar_status_label.configure(text="运行中")
            else:
                self.big_status_label.configure(text="待 机")
                self.big_status_sub.configure(text="录制进程未运行")
                self.sidebar_status_label.configure(text="未运行")

            self.info_interval.configure(text=check_interval)
            self.info_format.configure(text=output_format)
            self.info_tray.configure(text=tray_status)
            self.info_time.configure(text=timestamp)
        except Exception:
            pass

    # 周期性刷新状态栏、画质显示并监控 URL 配置变化。
    def _schedule_status_refresh(self) -> None:
        # 动态刷新状态：有录制时每3秒刷新，否则每10秒
        self._update_status_bar()
        self._update_quality_display()
        self._watch_url_config()
        interval = self._STATUS_REFRESH_INTERVAL_ACTIVE if self.running else self._STATUS_REFRESH_INTERVAL
        self._refresh_job_id = self.root.after(interval, self._schedule_status_refresh)

    # 监控 URL_config.ini 的修改时间，变化时自动重载。
    def _watch_url_config(self) -> None:
        # 监控 URL_config.ini 文件变化，外部修改时自动重新加载
        if not os.path.exists(self.url_config_file):
            return
        try:
            current_mtime = os.path.getmtime(self.url_config_file)
            if current_mtime != self._last_url_config_mtime:
                self._load_config()
        except OSError:
            pass

    # ─── 托盘与退出 ────────────────────────────────────────

    # 最小化到系统托盘（无托盘时降级为任务栏最小化）。
    def minimize_to_tray(self) -> None:
        # 最小化到托盘；托盘不可用（如 Linux 无 X11）时降级为普通最小化，避免窗口无法恢复
        if self.system_tray and self.system_tray.running:
            self.root.withdraw()
            self.system_tray.notify("程序已最小化到系统托盘，双击托盘图标可恢复窗口")
        else:
            self.root.iconify()
            self._log("系统托盘不可用，已改为最小化到任务栏", "warn")

    # 退出程序：确认后后台停止录制与清理，再销毁窗口（防重入）。
    def quit_application(self) -> None:
        # 退出程序（防重入：双击/托盘+按钮同时触发只执行一次）
        if self._quitting:
            return

        if self.process is not None:
            if not messagebox.askokcancel("退出确认", "录制正在后台进行，确定要退出吗？"):
                return

        self._quitting = True
        self._log("正在停止录制并清理 ffmpeg 进程，请稍候...")
        # 在后台线程完成「停止录制 + 清理残留 ffmpeg」，完成后再回主线程销毁窗口，
        # 避免窗口先被 destroy 导致清理线程被强杀、ffmpeg 残留。
        threading.Thread(target=self._shutdown_and_quit, daemon=True).start()

    # 后台执行：优雅停止录制子进程并按需整树强杀与清理 ffmpeg。
    def _shutdown_and_quit(self) -> None:
        # 后台执行：优雅停止录制子进程（由其清理 ffmpeg）→ 超时整树强杀 → 兜底清理。
        # 与停止路径保持同一策略：CTRL_BREAK 失败时不能只 proc.terminate()——
        # TerminateProcess 硬杀不触发 main.py 的 safe_exit，且 wait() 立即成功会绕过
        # taskkill /T 兜底分支，导致 ffmpeg 孤儿化继续录制。
        proc = self.process
        child_pid = proc.pid if proc is not None else None
        try:
            if proc is not None:
                if sys.platform == "win32":
                    if not _send_ctrl_break_to_child(proc.pid):
                        self._log("发送 CTRL_BREAK 失败，整树强制终止（避免 ffmpeg 孤儿化）", "warn")
                        try:
                            subprocess.run(
                                ["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True, timeout=5
                            )
                        except Exception as e:
                            self._log(f"taskkill 整树终止失败，回退 terminate: {e}")
                            proc.terminate()
                else:
                    try:
                        os.kill(proc.pid, signal.SIGINT)
                    except Exception as e:
                        self._log(f"发送 SIGINT 失败，回退 terminate: {e}")
                        proc.terminate()

                try:
                    proc.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    # main.py 未能自行退出，整树强杀（含其下所有 ffmpeg，避免孤儿）
                    try:
                        if sys.platform == "win32":
                            subprocess.run(
                                ["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True, timeout=5
                            )
                        else:
                            proc.kill()
                            subprocess.run(
                                ["pkill", "-P", str(proc.pid), "-x", "ffmpeg"], capture_output=True, timeout=5
                            )
                        proc.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        self._log("警告：进程可能仍在运行！", "warn")
                    except Exception as e:
                        self._log(f"强制终止失败: {e}")
                except Exception as e:
                    # proc.wait 本身的异常（OSError 等）不能中断收尾流程，
                    # 否则 _finalize_quit 永不执行、窗口无法销毁
                    self._log(f"等待子进程退出异常: {e}")

                self.running = False
                self.process = None
                self.process_pid = None

            # 兜底清理进程树中可能残留的 ffmpeg（显式传入已捕获的 PID，
            # 避免此处读到已被清空的 self.process_pid 导致清理失效）
            self._cleanup_zombie_ffmpeg(child_pid)
        except Exception as e:
            # 任何异常都不能阻断 UI 收尾，否则窗口无法销毁、进程无法退出
            self._log(f"退出清理流程异常: {e}", "warn")

        # 通过事件泵路由回 UI 线程收尾销毁（禁止直接跨线程调用 root.after）
        self.post_ui(self._finalize_quit)

    # 在 UI 线程收尾退出：取消调度、停托盘并销毁窗口。
    def _finalize_quit(self) -> None:
        # 退出收尾（必须在 UI 线程执行）
        self._pump_active = False
        if self._ui_pump_job_id:
            try:
                self.root.after_cancel(self._ui_pump_job_id)
            except Exception:
                pass
            self._ui_pump_job_id = None

        if self._log_flush_job_id:
            self.root.after_cancel(self._log_flush_job_id)
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

        self._stop_danmaku_tail()

        self._stop_status_animation()

        if self.system_tray:
            self.system_tray.stop()

        self.root.quit()
        self.root.destroy()

    # 清理录制子进程树及其下的 ffmpeg 残留进程（跨平台）。
    def _cleanup_zombie_ffmpeg(self, target_pid: int | None = None) -> None:
        # 清理录制子进程（main.py）及其下的 ffmpeg 进程。
        # 注意：ffmpeg 的父进程是 main.py，不是 GUI 自身，
        # 因此必须用 main.py 的 PID 整树强杀；按 GUI 自身 PID 过滤会匹配不到任何 ffmpeg。
        if target_pid is None:
            target_pid = self.process_pid
        found = False

        try:
            if sys.platform == "win32":
                if target_pid is not None:
                    try:
                        subprocess.run(
                            ["taskkill", "/F", "/T", "/PID", str(target_pid)], capture_output=True, timeout=5
                        )
                        found = True
                        self._log(f"已通过 taskkill 清理 PID {target_pid} 的进程树（含 ffmpeg）")
                    except Exception as e:
                        self._log(f"taskkill 执行失败: {e}")
                # 兜底：按镜像名清理 GUI 直接派生的 ffmpeg（极少出现）
                try:
                    subprocess.run(
                        ["taskkill", "/F", "/FI", "IMAGENAME eq ffmpeg.exe", "/FI", f"PARENTPID eq {os.getpid()}"],
                        capture_output=True,
                        timeout=3,
                    )
                except Exception:
                    pass
            else:
                if target_pid is not None:
                    try:
                        subprocess.run(["pkill", "-P", str(target_pid), "-x", "ffmpeg"], capture_output=True, timeout=3)
                        found = True
                        self._log(f"已通过 pkill 清理 PID {target_pid} 下的 ffmpeg 进程")
                    except Exception as e:
                        self._log(f"pkill 执行失败: {e}")
                try:
                    subprocess.run(["pkill", "-P", str(os.getpid()), "-x", "ffmpeg"], capture_output=True, timeout=3)
                except Exception:
                    pass

            if not found:
                self._log("未发现需要清理的 ffmpeg 进程")
        except Exception as e:
            self._log(f"清理 ffmpeg 进程时出错: {e}")

    # 窗口关闭事件：弹出「最小化到托盘 / 完全退出」对话框（单例）。
    def on_closing(self) -> None:
        # 窗口关闭事件处理，显示关闭选项对话框（单例：重复点击只保留一个）
        if self._close_dialog is not None:
            try:
                if self._close_dialog.winfo_exists():
                    self._close_dialog.focus()
                    return
            except Exception:
                pass
            self._close_dialog = None

        dialog = ctk.CTkToplevel(self.root)
        self._close_dialog = dialog
        dialog.title("关闭选项")
        dialog.geometry("400x230")
        dialog.resizable(False, False)
        dialog.transient(self.root)

        # 居中显示对话框
        dialog.update_idletasks()
        x = self.root.winfo_x() + (self.root.winfo_width() - dialog.winfo_width()) // 2
        y = self.root.winfo_y() + (self.root.winfo_height() - dialog.winfo_height()) // 2
        dialog.geometry(f"+{x}+{y}")

        ctk.CTkLabel(dialog, text="🎬", font=ctk.CTkFont(size=32)).pack(pady=(24, 8))
        ctk.CTkLabel(dialog, text="请选择关闭方式", font=Fonts.heading()).pack()
        ctk.CTkLabel(
            dialog,
            text="您可以最小化到系统托盘，或完全退出程序",
            font=Fonts.small(),
            text_color=(Colors.MUTED_LIGHT, Colors.MUTED_DARK),
        ).pack(pady=(4, 18))

        btn_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        btn_frame.pack(padx=16, pady=(0, 16))

        # 最小化到托盘并关闭关闭选项对话框。
        def minimize_to_tray_and_close() -> None:
            # 最小化到托盘并关闭对话框
            self.minimize_to_tray()
            dialog.destroy()

        # 退出应用并关闭关闭选项对话框。
        def quit_and_close() -> None:
            # 退出应用并关闭对话框
            self.quit_application()
            dialog.destroy()

        ctk.CTkButton(
            btn_frame,
            text="📥   最小化到托盘",
            command=minimize_to_tray_and_close,
            width=160,
            height=40,
            corner_radius=8,
            fg_color=Colors.PRIMARY,
            hover_color=Colors.PRIMARY_HOVER,
            text_color="#FFFFFF",
            font=Fonts.body(bold=True),
        ).pack(side=tk.LEFT, padx=(0, 10))

        ctk.CTkButton(
            btn_frame,
            text="❌   完全退出",
            command=quit_and_close,
            width=140,
            height=40,
            corner_radius=8,
            fg_color=Colors.DANGER,
            hover_color=Colors.DANGER_HOVER,
            text_color="#FFFFFF",
            font=Fonts.body(bold=True),
        ).pack(side=tk.LEFT)

        # 键盘快捷键
        # Escape 键关闭关闭选项对话框。
        def _on_escape(_event: object = None) -> None:
            dialog.destroy()

        dialog.bind("<Escape>", _on_escape)

        # 延迟 grab，等待窗口可见
        dialog.after(100, lambda: self._safe_dialog_grab(dialog))

    # 安全地为对话框设置模态（容错 grab_set）。
    @staticmethod
    # 安全地为对话框设置模态（容错 grab_set）。
    def _safe_dialog_grab(dialog: ctk.CTkToplevel) -> None:
        # 安全地设置模态
        try:
            dialog.grab_set()
        except Exception:
            pass


# 程序入口：初始化主窗口与系统托盘，并按平台进入主事件循环。
def main() -> None:
    # 主函数
    ctk.set_appearance_mode("system")
    ctk.set_default_color_theme("blue")

    root = ctk.CTk()
    app = LiveRecorderGUI(root)

    tray = SystemTray(app)
    app.system_tray = tray

    root.protocol("WM_DELETE_WINDOW", app.on_closing)

    if sys.platform == "darwin":
        # macOS 双重主线程约束：
        #  1) Tcl/Tk 只能在主线程运行，否则抛
        #     "RuntimeError: Calling Tcl from different apartment"；
        #  2) pystray 的 NSStatusItem 受 AppKit 主线程限制，且 icon.run() 会以
        #     NSApplication.run() 接管主线程事件循环，与 Tk mainloop 互斥。
        # 解法：托盘用 run_detached()（仅在主线程注册状态栏图标，不启动独立
        # 事件循环，事件由 Tk 的 Cocoa 循环分发），随后主线程进入 Tk mainloop。
        app.tray_thread = None
        tray.run_detached()  # 非阻塞；headless 时内部优雅降级
        root.mainloop()
    else:
        app.tray_thread = threading.Thread(target=tray.run, daemon=True)
        app.tray_thread.start()
        root.mainloop()


if __name__ == "__main__":
    main()
