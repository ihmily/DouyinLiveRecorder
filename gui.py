# -*- encoding: utf-8 -*-
# 直播录制器 GUI 界面（基于 CustomTkinter 的现代化重构）
from __future__ import annotations

import os
import sys
import time
import signal
import subprocess
import threading
import queue
import re
import configparser
import tkinter as tk
from tkinter import messagebox
from datetime import datetime
from typing import Any

import customtkinter as ctk
from PIL import Image, ImageDraw
# pystray 延迟导入至 SystemTray.run() 内部，避免 headless 环境顶层导入失败


# ─── 现代化色彩系统（浅色 / 深色双主题） ──────────────────

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


class Fonts:
    # 常用字体配置（惰性创建，避免在 Tk 初始化前调用失败）
    _cache: dict[str, ctk.CTkFont] = {}

    @classmethod
    def get(cls, size: int, weight: str = "normal", family: str = _FONT_FAMILY) -> ctk.CTkFont:
        key = f"{family}_{size}_{weight}"
        if key not in cls._cache:
            cls._cache[key] = ctk.CTkFont(family=family, size=size, weight=weight)
        return cls._cache[key]

    @classmethod
    def small(cls, bold: bool = False) -> ctk.CTkFont:
        return cls.get(12, "bold" if bold else "normal")

    @classmethod
    def body(cls, bold: bool = False) -> ctk.CTkFont:
        return cls.get(13, "bold" if bold else "normal")

    @classmethod
    def heading(cls, bold: bool = True) -> ctk.CTkFont:
        return cls.get(15, "bold" if bold else "normal")

    @classmethod
    def title(cls) -> ctk.CTkFont:
        return cls.get(20, "bold")

    @classmethod
    def big_status(cls) -> ctk.CTkFont:
        return cls.get(26, "bold")

    @classmethod
    def mono(cls) -> tuple[str, int]:
        return (_MONO_FAMILY, 11)


def _hex_to_rgb(color: str) -> tuple[int, int, int]:
    # 将 #RRGGBB 转为 RGB 元组
    color = color.lstrip('#')
    return tuple(int(color[i:i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def _mix(color_a: str, color_b: str, ratio: float) -> str:
    # 按 ratio 混合两种颜色（0 = A，1 = B），用于呼吸灯动画
    ra, ga, ba = _hex_to_rgb(color_a)
    rb, gb, bb = _hex_to_rgb(color_b)
    r = round(ra + (rb - ra) * ratio)
    g = round(ga + (gb - ga) * ratio)
    b = round(ba + (bb - ba) * ratio)
    return f"#{r:02X}{g:02X}{b:02X}"


class SystemTray:
    # 系统托盘管理器

    def __init__(self, gui_app: 'LiveRecorderGUI'):
        # 初始化系统托盘管理器
        self.gui = gui_app
        self.icon: "pystray.Icon | None" = None  # type: ignore[type-arg]
        self.running = False

    def create_icon_image(self) -> Image.Image:
        # 创建现代化托盘图标
        size = 64
        image = Image.new('RGBA', (size, size), (0, 0, 0, 0))
        dc = ImageDraw.Draw(image)

        # 圆角矩形背景
        margin = 2
        dc.rounded_rectangle(
            (margin, margin, size - margin, size - margin),
            radius=16, fill=(79, 109, 245, 255)
        )

        # 白色圆环
        ring_margin = 10
        dc.ellipse(
            (ring_margin, ring_margin, size - ring_margin, size - ring_margin),
            outline=(255, 255, 255, 230), width=3
        )

        # 中心录制圆点
        dot_size = 9
        cx = size // 2
        cy = size // 2
        dc.ellipse(
            (cx - dot_size, cy - dot_size, cx + dot_size, cy + dot_size),
            fill=(220, 38, 38, 255)
        )

        return image

    def on_show(self, _icon: "pystray.Icon | None" = None) -> None:  # type: ignore[type-arg]
        # 托盘菜单：显示主窗口（pystray 回调运行在托盘线程，Tk 操作必须路由回 UI 线程）
        self.gui.post_ui(self._do_show)

    def _do_show(self) -> None:
        # 在 UI 线程中恢复窗口
        self.gui.root.deiconify()
        self.gui.root.lift()

    def on_exit(self, _icon: "pystray.Icon | None" = None) -> None:  # type: ignore[type-arg]
        # 托盘菜单：退出程序（路由回 UI 线程，避免跨线程弹窗/操作 Tk）
        self.gui.post_ui(self.gui.quit_application)

    def on_minimize(self, _icon: "pystray.Icon | None" = None) -> None:  # type: ignore[type-arg]
        # 托盘菜单：最小化到托盘（路由回 UI 线程）
        self.gui.post_ui(self.gui.root.withdraw)

    def run(self) -> None:
        # 启动系统托盘图标（阻塞运行）
        import pystray  # 延迟导入：避免 headless 环境在模块顶层即失败
        menu = pystray.Menu(
            pystray.MenuItem('显示主界面', self.on_show, default=True),
            pystray.MenuItem('最小化到托盘', self.on_minimize),
            pystray.MenuItem('退出程序', self.on_exit)
        )

        icon = pystray.Icon(
            'LiveRecorder',
            self.create_icon_image(),
            'LiveRecorder - click to show',
            menu
        )
        self.icon = icon
        self.running = True
        icon.run()

    def stop(self) -> None:
        # 停止系统托盘
        if self.icon and self.running:
            self.icon.stop()
            self.running = False

    def notify(self, message: str, title: str = '直播录制器') -> None:
        # 显示系统通知
        if self.icon:
            try:
                self.icon.notify(message, title)
            except Exception:
                pass


class AdvancedSettingsWindow:
    # 高级设置窗口：编辑 config/config.ini

    def __init__(self, parent: ctk.CTk, config_file: str, log_callback: Any = None):
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

    def _safe_grab(self) -> None:
        # 安全地设置模态
        try:
            self.window.grab_set()
        except Exception:
            pass

    def _setup_ui(self) -> None:
        # 顶部标题栏
        header = ctk.CTkFrame(self.window, fg_color=Colors.PRIMARY, corner_radius=0, height=52)
        header.pack(fill=tk.X)
        header.pack_propagate(False)
        ctk.CTkLabel(header, text="⚙  高级设置", text_color="#FFFFFF",
                     font=Fonts.heading()).pack(side=tk.LEFT, padx=20, pady=12)

        # 内容区域
        content = ctk.CTkFrame(self.window, fg_color="transparent")
        content.pack(fill=tk.BOTH, expand=True, padx=16, pady=(16, 0))

        ctk.CTkLabel(content, text="📄 配置文件内容 (config/config.ini)",
                     font=Fonts.body(), anchor=tk.W).pack(fill=tk.X, pady=(0, 8))

        # 编辑器（等宽字体）
        self.config_text = ctk.CTkTextbox(
            content, wrap="none", font=Fonts.mono(),
            corner_radius=10, border_width=1,
            activate_scrollbars=True
        )
        self.config_text.pack(fill=tk.BOTH, expand=True)

        # 底部按钮
        btn_frame = ctk.CTkFrame(self.window, fg_color="transparent")
        btn_frame.pack(fill=tk.X, padx=16, pady=16)

        ctk.CTkButton(btn_frame, text="取消", command=self.window.destroy,
                      fg_color="transparent", border_width=1,
                      text_color=(Colors.TEXT_LIGHT, Colors.TEXT_DARK),
                      border_color=(Colors.BORDER_LIGHT, Colors.BORDER_DARK),
                      hover_color=(Colors.BG_LIGHT, Colors.BG_DARK),
                      font=Fonts.body(), width=110, height=36,
                      corner_radius=8).pack(side=tk.RIGHT, padx=(8, 0))

        ctk.CTkButton(btn_frame, text="💾  保存配置", command=self.save_config,
                      fg_color=Colors.PRIMARY, hover_color=Colors.PRIMARY_HOVER,
                      text_color="#FFFFFF", font=Fonts.body(bold=True),
                      width=130, height=36, corner_radius=8).pack(side=tk.RIGHT)

    def _load_config(self) -> None:
        # 加载 config.ini 到编辑器
        try:
            with open(self.config_file, 'r', encoding='utf-8-sig') as f:
                content = f.read()
            self.config_text.delete("1.0", tk.END)
            self.config_text.insert("1.0", content)
        except FileNotFoundError:
            self.config_text.delete("1.0", tk.END)
            self.config_text.insert("1.0", "# 配置文件不存在，请新建")
        except Exception as e:
            messagebox.showerror("错误", f"加载配置文件失败: {e}")

    def save_config(self) -> None:
        # 保存编辑器内容到 config.ini
        try:
            _save_text_widget_to_file(self.config_text, self.config_file)
            messagebox.showinfo("成功", "配置文件已保存！")
            if self.log_callback:
                self.log_callback("高级设置配置已保存")
            self.window.destroy()
        except Exception as e:
            messagebox.showerror("错误", f"保存配置文件失败: {e}")


def _save_text_widget_to_file(text_widget: Any, file_path: str) -> None:
    # 从文本控件读取内容并写入文件
    content = text_widget.get("1.0", tk.END).rstrip('\n')
    if content and not content.endswith('\n'):
        content += '\n'
    with open(file_path, 'w', encoding='utf-8-sig') as f:
        f.write(content)


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
    if sys.platform != 'win32':
        return False
    import ctypes
    k32 = ctypes.windll.kernel32
    had_console = bool(k32.GetConsoleWindow())
    handler_routine = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_ulong)

    def _ignore(_ctrl_type: int) -> bool:
        return True  # 声明事件已处理，避免 GUI 自身被 CTRL_BREAK 终止

    cb = handler_routine(_ignore)
    k32.FreeConsole()
    if not k32.AttachConsole(pid):
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


class LiveRecorderGUI:
    # 直播录制 GUI 主类

    # 常量定义
    ANSI_ESCAPE_PATTERN = re.compile(r'\x1b\[[0-9;]*m')
    _MAX_LOG_LINES = 1000
    _LOG_TRIM_TO = 800
    _LOG_FLUSH_INTERVAL = 200
    _STATUS_REFRESH_INTERVAL = 10000          # 未录制时的刷新间隔（毫秒）
    _STATUS_REFRESH_INTERVAL_ACTIVE = 3000   # 有录制直播间时的刷新间隔（毫秒）

    def __init__(self, root: ctk.CTk):
        # 初始化 GUI 主窗口及所有组件
        self.root = root
        self.root.title("直播录制控制台")
        self.root.geometry("1120x740")
        self.root.minsize(920, 620)

        # 外观模式：跟随系统
        ctk.set_appearance_mode("system")

        # 路径配置
        self.script_dir = os.path.dirname(os.path.abspath(__file__))
        self.url_config_file = os.path.join(self.script_dir, "config", "URL_config.ini")
        self.main_config_file = os.path.join(self.script_dir, "config", "config.ini")
        self.downloads_dir = os.path.join(self.script_dir, "downloads")

        # 进程状态（线程安全访问）
        self._process_lock = threading.Lock()
        self._process: subprocess.Popen[str] | None = None
        self._process_pid: int | None = None
        self._running = False

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

        # UI 线程事件队列：后台线程一律通过 post_ui 投递回调，
        # 由 _pump_ui_events 在 UI 线程执行。tkinter 不是线程安全的，
        # 后台线程直接调 root.after/createcommand 会随机崩溃
        # （RuntimeError: main thread is not in main loop）。
        self._ui_event_queue: queue.Queue[tuple[Any, tuple[Any, ...]]] = queue.Queue()
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

        self._setup_ui()
        self._load_config()
        self._schedule_log_flush()
        self._schedule_status_refresh()
        self._ui_pump_job_id = self.root.after(100, self._pump_ui_events)

    # ─── UI 线程事件泵（线程安全调度） ──────────────────────

    def post_ui(self, callback: Any, *args: Any) -> None:
        # 从任意线程安全地调度回调到 UI 线程执行（只写队列，不触碰 Tk）
        self._ui_event_queue.put((callback, args))

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
                pass

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
    def process(self) -> subprocess.Popen[str] | None:
        # 获取子进程对象（线程安全）
        with self._process_lock:
            return self._process

    @process.setter
    def process(self, value: subprocess.Popen[str] | None) -> None:
        # 设置子进程对象（线程安全）
        with self._process_lock:
            self._process = value

    @property
    def process_pid(self) -> int | None:
        # 获取子进程 PID
        with self._process_lock:
            return self._process_pid

    @process_pid.setter
    def process_pid(self, value: int | None) -> None:
        # 设置子进程 PID
        with self._process_lock:
            self._process_pid = value

    @property
    def running(self) -> bool:
        # 获取运行状态
        with self._process_lock:
            return self._running

    @running.setter
    def running(self, value: bool) -> None:
        # 设置运行状态
        with self._process_lock:
            self._running = value

    # ─── UI 初始化 ─────────────────────────────────────────

    def _setup_ui(self) -> None:
        # 主布局：左侧导航栏 + 右侧内容区（grid）
        self.root.grid_columnconfigure(0, minsize=230, weight=0)
        self.root.grid_columnconfigure(1, weight=1)
        self.root.grid_rowconfigure(0, weight=1)

        self._build_sidebar()
        self._build_content()
        self._show_page("dashboard")

    def _build_sidebar(self) -> None:
        # 构建左侧导航栏
        sidebar = ctk.CTkFrame(
            self.root, corner_radius=0,
            fg_color=(Colors.SIDEBAR_LIGHT, Colors.SIDEBAR_DARK),
            border_width=0
        )
        sidebar.grid(row=0, column=0, sticky="nsew")
        sidebar.grid_propagate(False)
        self.sidebar = sidebar

        # 品牌区
        brand = ctk.CTkFrame(sidebar, fg_color="transparent")
        brand.pack(fill=tk.X, padx=20, pady=(24, 6))
        ctk.CTkLabel(brand, text="🎬", font=ctk.CTkFont(size=30)).pack(side=tk.LEFT)
        brand_text = ctk.CTkFrame(brand, fg_color="transparent")
        brand_text.pack(side=tk.LEFT, padx=(10, 0))
        ctk.CTkLabel(brand_text, text="直播录制", font=Fonts.title(),
                     text_color=(Colors.TEXT_LIGHT, Colors.TEXT_DARK)).pack(anchor=tk.W)
        ctk.CTkLabel(brand_text, text="DouyinLiveRecorder", font=Fonts.small(),
                     text_color=(Colors.MUTED_LIGHT, Colors.MUTED_DARK)).pack(anchor=tk.W)

        # 状态胶囊
        self.status_pill = ctk.CTkFrame(
            sidebar, corner_radius=20, height=38,
            fg_color=(Colors.BG_LIGHT, Colors.BG_DARK),
            border_width=1,
            border_color=(Colors.BORDER_LIGHT, Colors.BORDER_DARK)
        )
        self.status_pill.pack(fill=tk.X, padx=16, pady=(14, 6))
        self.status_pill.pack_propagate(False)

        self._sidebar_dot = tk.Canvas(
            self.status_pill, width=12, height=12,
            highlightthickness=0, bd=0
        )
        self._sidebar_dot.pack(side=tk.LEFT, padx=(14, 8))
        self._sidebar_dot_item = self._sidebar_dot.create_oval(
            1, 1, 11, 11, fill=Colors.DANGER, outline=""
        )
        self._sync_dot_bg()

        self.sidebar_status_label = ctk.CTkLabel(
            self.status_pill, text="未运行", font=Fonts.body(bold=True),
            text_color=(Colors.TEXT_LIGHT, Colors.TEXT_DARK)
        )
        self.sidebar_status_label.pack(side=tk.LEFT)

        # 导航按钮
        nav = ctk.CTkFrame(sidebar, fg_color="transparent")
        nav.pack(fill=tk.X, padx=12, pady=(18, 0))

        self._add_nav_button(nav, "dashboard", "📊   控制台")
        self._add_nav_button(nav, "config", "📝   URL 配置")
        self._add_nav_button(nav, "logs", "📋   运行日志")

        # 底部区域
        bottom = ctk.CTkFrame(sidebar, fg_color="transparent")
        bottom.pack(side=tk.BOTTOM, fill=tk.X, padx=12, pady=16)

        # 外观切换
        ctk.CTkLabel(bottom, text="外观模式", font=Fonts.small(),
                     text_color=(Colors.MUTED_LIGHT, Colors.MUTED_DARK),
                     anchor=tk.W).pack(fill=tk.X, padx=6, pady=(0, 4))
        self.appearance_menu = ctk.CTkOptionMenu(
            bottom, values=["跟随系统", "浅色", "深色"],
            command=self._on_appearance_change,
            font=Fonts.body(), corner_radius=8, height=34,
            fg_color=(Colors.BG_LIGHT, Colors.BG_DARK),
            button_color=("#D6DAE5", "#2A3040"),
            button_hover_color=("#C3C9D8", "#343B4E"),
            text_color=(Colors.TEXT_LIGHT, Colors.TEXT_DARK),
            dropdown_fg_color=(Colors.CARD_LIGHT, Colors.CARD_DARK),
            dropdown_text_color=(Colors.TEXT_LIGHT, Colors.TEXT_DARK),
            dropdown_hover_color=(Colors.PRIMARY_SOFT_LIGHT, Colors.PRIMARY_SOFT_DARK)
        )
        self.appearance_menu.pack(fill=tk.X, padx=2, pady=(0, 12))
        self.appearance_menu.set("跟随系统")

        ctk.CTkButton(
            bottom, text="📥   最小化到托盘", command=self.minimize_to_tray,
            font=Fonts.body(), height=38, corner_radius=8,
            fg_color="transparent",
            text_color=(Colors.TEXT_LIGHT, Colors.TEXT_DARK),
            border_width=1,
            border_color=(Colors.BORDER_LIGHT, Colors.BORDER_DARK),
            hover_color=(Colors.BG_LIGHT, Colors.BG_DARK),
            anchor=tk.W
        ).pack(fill=tk.X, pady=(0, 8))

        ctk.CTkButton(
            bottom, text="❌   彻底退出", command=self.quit_application,
            font=Fonts.body(bold=True), height=38, corner_radius=8,
            fg_color=Colors.DANGER, hover_color=Colors.DANGER_HOVER,
            text_color="#FFFFFF", anchor=tk.W
        ).pack(fill=tk.X)

    def _add_nav_button(self, parent: ctk.CTkFrame, page_id: str, text: str) -> None:
        # 添加侧边栏导航按钮
        btn = ctk.CTkButton(
            parent, text=text, command=lambda: self._show_page(page_id),
            font=Fonts.body(), height=42, corner_radius=8,
            fg_color="transparent",
            text_color=(Colors.MUTED_LIGHT, Colors.MUTED_DARK),
            hover_color=(Colors.BG_LIGHT, Colors.BG_DARK),
            anchor=tk.W
        )
        btn.pack(fill=tk.X, pady=2)
        self._nav_buttons[page_id] = btn

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
                    font=Fonts.body(bold=True)
                )
            else:
                btn.configure(
                    fg_color="transparent",
                    text_color=(Colors.MUTED_LIGHT, Colors.MUTED_DARK),
                    font=Fonts.body()
                )

    def _on_appearance_change(self, choice: str) -> None:
        # 切换外观模式
        mapping = {"跟随系统": "system", "浅色": "light", "深色": "dark"}
        ctk.set_appearance_mode(mapping.get(choice, "system"))
        # 主题切换后同步自绘控件颜色（Canvas 不随主题自动变化）
        self.root.after(50, self._sync_canvas_bg)

    def _sync_canvas_bg(self) -> None:
        # 同步所有自绘 Canvas 的背景色（主题切换后调用）
        self._sync_dot_bg()
        self._sync_big_dot_bg()

    def _sync_dot_bg(self) -> None:
        # 同步状态圆点画布背景色（Canvas 不随主题自动变化）
        try:
            mode = ctk.get_appearance_mode().lower()
            bg = Colors.BG_DARK if mode == "dark" else Colors.BG_LIGHT
            self._sidebar_dot.configure(bg=bg)
        except Exception:
            pass

    def _build_content(self) -> None:
        # 构建右侧内容区（三个页面叠放，tkraise 切换）
        container = ctk.CTkFrame(self.root, fg_color=(Colors.BG_LIGHT, Colors.BG_DARK))
        container.grid(row=0, column=1, sticky="nsew")
        container.grid_columnconfigure(0, weight=1)
        container.grid_rowconfigure(0, weight=1)

        self._pages["dashboard"] = self._build_dashboard_page(container)
        self._pages["config"] = self._build_config_page(container)
        self._pages["logs"] = self._build_logs_page(container)

        for page in self._pages.values():
            page.grid(row=0, column=0, sticky="nsew", padx=20, pady=20)

    def _create_card(self, parent: ctk.CTkFrame, title: str = "") -> ctk.CTkFrame:
        # 创建圆角卡片容器
        card = ctk.CTkFrame(
            parent, corner_radius=12,
            fg_color=(Colors.CARD_LIGHT, Colors.CARD_DARK),
            border_width=1,
            border_color=(Colors.BORDER_LIGHT, Colors.BORDER_DARK)
        )
        if title:
            header = ctk.CTkFrame(card, fg_color="transparent", height=46)
            header.pack(fill=tk.X)
            header.pack_propagate(False)
            ctk.CTkLabel(header, text=title, font=Fonts.body(bold=True),
                         text_color=(Colors.TEXT_LIGHT, Colors.TEXT_DARK)
                         ).pack(side=tk.LEFT, padx=18, pady=12)
        return card

    # ─── 页面：控制台 ───────────────────────────────────────

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
        self._big_dot = tk.Canvas(dot_wrap, width=64, height=64,
                                  highlightthickness=0, bd=0)
        self._big_dot.place(relx=0.5, rely=0.5, anchor=tk.CENTER)
        self._big_dot_item = self._big_dot.create_oval(8, 8, 56, 56,
                                                       fill=Colors.DANGER, outline="")
        self._sync_big_dot_bg()

        # 中间：状态文字
        mid = ctk.CTkFrame(status_card, fg_color="transparent")
        mid.grid(row=0, column=1, sticky="w", pady=18)
        self.big_status_label = ctk.CTkLabel(mid, text="待 机", font=Fonts.big_status(),
                                             text_color=(Colors.TEXT_LIGHT, Colors.TEXT_DARK))
        self.big_status_label.pack(anchor=tk.W)
        self.big_status_sub = ctk.CTkLabel(mid, text="录制进程未运行",
                                           font=Fonts.body(),
                                           text_color=(Colors.MUTED_LIGHT, Colors.MUTED_DARK))
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
            ctrl_body, text="▶   开始录制", command=self.start_recording,
            font=Fonts.heading(), height=48, corner_radius=10,
            fg_color=Colors.SUCCESS, hover_color=Colors.SUCCESS_HOVER,
            text_color="#FFFFFF", width=200
        )
        self.start_btn.pack(side=tk.LEFT, padx=(0, 12))

        self.stop_btn = ctk.CTkButton(
            ctrl_body, text="⏹   停止录制", command=self.stop_recording,
            font=Fonts.heading(), height=48, corner_radius=10,
            fg_color=Colors.DANGER, hover_color=Colors.DANGER_HOVER,
            text_color="#FFFFFF", width=200, state=tk.DISABLED
        )
        self.stop_btn.pack(side=tk.LEFT)

        ctk.CTkLabel(
            ctrl_body,
            text="启动后将调用 main.py 循环监测 URL 配置中的直播间并自动录制",
            font=Fonts.small(),
            text_color=(Colors.MUTED_LIGHT, Colors.MUTED_DARK)
        ).pack(side=tk.LEFT, padx=20)

        # ── 快捷操作卡片 ──
        quick_card = self._create_card(page, "快捷操作")
        quick_card.grid(row=2, column=0, sticky="new")

        quick_body = ctk.CTkFrame(quick_card, fg_color="transparent")
        quick_body.pack(fill=tk.X, padx=18, pady=(0, 16))

        ctk.CTkButton(
            quick_body, text="📂   打开下载目录", command=self.open_downloads_folder,
            font=Fonts.body(), height=40, corner_radius=8, width=170,
            fg_color=(Colors.BG_LIGHT, Colors.BG_DARK),
            text_color=(Colors.TEXT_LIGHT, Colors.TEXT_DARK),
            border_width=1,
            border_color=(Colors.BORDER_LIGHT, Colors.BORDER_DARK),
            hover_color=(Colors.BORDER_LIGHT, Colors.BORDER_DARK)
        ).pack(side=tk.LEFT, padx=(0, 10))

        ctk.CTkButton(
            quick_body, text="⚙   高级设置", command=self.open_advanced_settings,
            font=Fonts.body(), height=40, corner_radius=8, width=150,
            fg_color=(Colors.BG_LIGHT, Colors.BG_DARK),
            text_color=(Colors.TEXT_LIGHT, Colors.TEXT_DARK),
            border_width=1,
            border_color=(Colors.BORDER_LIGHT, Colors.BORDER_DARK),
            hover_color=(Colors.BORDER_LIGHT, Colors.BORDER_DARK)
        ).pack(side=tk.LEFT)

        return page

    def _add_info_item(self, parent: ctk.CTkFrame, label: str, value: str,
                       row: int, col: int) -> ctk.CTkLabel:
        # 在状态卡片中添加一个信息项，返回值标签便于后续更新
        box = ctk.CTkFrame(parent, fg_color="transparent")
        box.grid(row=row, column=col, padx=16, pady=6, sticky="w")
        ctk.CTkLabel(box, text=label, font=Fonts.small(),
                     text_color=(Colors.MUTED_LIGHT, Colors.MUTED_DARK)).pack(anchor=tk.W)
        val = ctk.CTkLabel(box, text=value, font=Fonts.body(bold=True),
                           text_color=(Colors.TEXT_LIGHT, Colors.TEXT_DARK))
        val.pack(anchor=tk.W)
        return val

    def _sync_big_dot_bg(self) -> None:
        # 同步大圆点画布背景（Canvas 不随主题自动变化）
        try:
            mode = ctk.get_appearance_mode().lower()
            bg = Colors.CARD_DARK if mode == "dark" else Colors.CARD_LIGHT
            self._big_dot.configure(bg=bg)
        except Exception:
            pass

    # ─── 页面：URL 配置 ─────────────────────────────────────

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
            editor_wrap, wrap="none", font=Fonts.mono(),
            corner_radius=10, border_width=1,
            border_color=(Colors.BORDER_LIGHT, Colors.BORDER_DARK),
            activate_scrollbars=True
        )
        self.config_text.pack(fill=tk.BOTH, expand=True)

        # 提示
        ctk.CTkLabel(
            card,
            text="每行一个直播链接，支持 # 开头的注释行  │  外部修改文件后将自动重新加载  │  点击窗口关闭按钮将最小化到系统托盘",
            font=Fonts.small(),
            text_color=(Colors.MUTED_LIGHT, Colors.MUTED_DARK),
            anchor=tk.W
        ).pack(fill=tk.X, padx=18, pady=(4, 4))

        # 操作按钮
        btn_row = ctk.CTkFrame(card, fg_color="transparent")
        btn_row.pack(fill=tk.X, padx=14, pady=(4, 14))

        self.reload_btn = ctk.CTkButton(
            btn_row, text="🔄   重新读取", command=self._load_config,
            font=Fonts.body(), height=38, corner_radius=8, width=140,
            fg_color="transparent",
            text_color=(Colors.TEXT_LIGHT, Colors.TEXT_DARK),
            border_width=1,
            border_color=(Colors.BORDER_LIGHT, Colors.BORDER_DARK),
            hover_color=(Colors.BG_LIGHT, Colors.BG_DARK)
        )
        self.reload_btn.pack(side=tk.RIGHT, padx=(8, 0))

        self.save_btn = ctk.CTkButton(
            btn_row, text="💾   保存 URL 配置", command=self.save_config,
            font=Fonts.body(bold=True), height=38, corner_radius=8, width=160,
            fg_color=Colors.PRIMARY, hover_color=Colors.PRIMARY_HOVER,
            text_color="#FFFFFF"
        )
        self.save_btn.pack(side=tk.RIGHT)

        return page

    # ─── 页面：运行日志 ─────────────────────────────────────

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
            term_wrap, wrap=tk.WORD,
            font=Fonts.mono(),
            bg=Colors.TERMINAL_BG, fg=Colors.TERMINAL_FG,
            insertbackground="#FFFFFF",
            relief=tk.FLAT, bd=0, padx=12, pady=10,
            state=tk.DISABLED,
            selectbackground=Colors.TERMINAL_SELECT, selectforeground="#FFFFFF"
        )
        scrollbar = ctk.CTkScrollbar(term_wrap, command=self.log_text.yview,
                                     fg_color=Colors.TERMINAL_BG,
                                     button_color="#30363D",
                                     button_hover_color="#484F58")
        self.log_text.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y, padx=(0, 4), pady=4)
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.log_text.tag_config("error", foreground=Colors.TERMINAL_ERROR)
        self.log_text.tag_config("warn", foreground=Colors.TERMINAL_WARN)

        # 底部操作栏
        btn_row = ctk.CTkFrame(card, fg_color="transparent")
        btn_row.pack(fill=tk.X, padx=14, pady=(4, 14))

        ctk.CTkButton(
            btn_row, text="🗑   清空日志", command=self._clear_log,
            font=Fonts.body(), height=36, corner_radius=8, width=130,
            fg_color="transparent",
            text_color=(Colors.TEXT_LIGHT, Colors.TEXT_DARK),
            border_width=1,
            border_color=(Colors.BORDER_LIGHT, Colors.BORDER_DARK),
            hover_color=(Colors.BG_LIGHT, Colors.BG_DARK)
        ).pack(side=tk.RIGHT)

        ctk.CTkLabel(
            btn_row, text="日志超过 1000 行将自动截断",
            font=Fonts.small(),
            text_color=(Colors.MUTED_LIGHT, Colors.MUTED_DARK)
        ).pack(side=tk.LEFT, padx=6)

        return page

    def _clear_log(self) -> None:
        # 清空日志显示
        self.log_text.config(state=tk.NORMAL)
        self.log_text.delete("1.0", tk.END)
        self.log_text.config(state=tk.DISABLED)

    # ─── 状态指示器动画 ─────────────────────────────────────

    def _start_status_animation(self) -> None:
        # 启动状态指示器呼吸动画
        if self._status_animating:
            return
        self._status_animating = True
        self._status_anim_index = 0
        self._animate_status_dot()

    def _stop_status_animation(self) -> None:
        # 停止状态指示器动画
        self._status_animating = False
        if self._status_anim_timer is not None:
            try:
                self.root.after_cancel(self._status_anim_timer)
            except Exception:
                pass
            self._status_anim_timer = None

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

    def _load_config(self) -> None:
        # 加载 URL 配置文件
        config_dir = os.path.dirname(self.url_config_file)
        os.makedirs(config_dir, exist_ok=True)

        if not os.path.exists(self.url_config_file):
            with open(self.url_config_file, 'w', encoding='utf-8-sig') as f:
                f.write("")

        try:
            with open(self.url_config_file, 'r', encoding='utf-8-sig') as f:
                content = f.read()

            current_content = self.config_text.get("1.0", tk.END).rstrip('\n')
            # 两侧统一去掉尾部换行再比较，否则文件末尾换行会导致比较永远失败
            if content.rstrip('\n') == current_content:
                self._last_url_config_mtime = os.path.getmtime(self.url_config_file)
                return

            self.config_text.delete("1.0", tk.END)
            self.config_text.insert("1.0", content)
            self._last_url_config_mtime = os.path.getmtime(self.url_config_file)
        except Exception as e:
            self._log(f"加载配置文件失败: {e}", "error")

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
            config.optionxform = lambda optionstr: optionstr
            config.read(self.main_config_file, encoding='utf-8-sig')

            if '录制设置' in config:
                interval = config['录制设置'].get('循环时间(秒)', '120')
                check_interval = f"{interval}秒"

                fmt = config['录制设置'].get('录制完成后自动转为mp4格式', '否')
                if fmt == '是':
                    output_format = "ts → mp4"
                else:
                    save_fmt = config['录制设置'].get('视频保存格式ts|mkv|flv|mp4|mp3音频|m4a音频', 'ts')
                    output_format = f"ts → {save_fmt}"

            self._status_cache = (check_interval, output_format)
            self._status_cache_mtime = file_mtime

        except Exception:
            pass

        return check_interval, output_format, self._tray_status_str()

    def _tray_status_str(self) -> str:
        # 返回托盘状态的字符串描述
        return "启用" if self.system_tray and self.system_tray.running else "未启动"

    # ─── 子进程管理 ────────────────────────────────────────

    def open_downloads_folder(self) -> None:
        # 打开下载目录
        downloads_path = self.downloads_dir
        if not os.path.exists(downloads_path):
            os.makedirs(downloads_path, exist_ok=True)

        try:
            if sys.platform == 'win32':
                os.startfile(downloads_path)
            elif sys.platform == 'darwin':
                subprocess.Popen(['open', downloads_path])
            else:
                subprocess.Popen(['xdg-open', downloads_path])
            self._log(f"已打开下载目录: {downloads_path}")
        except Exception as e:
            self._log(f"打开目录失败: {e}", "error")

    def open_advanced_settings(self) -> None:
        # 打开高级设置窗口
        AdvancedSettingsWindow(self.root, self.main_config_file, self._log)

    def start_recording(self) -> None:
        # 开始录制
        if self.process is not None:
            messagebox.showwarning("警告", "录制已在运行中！")
            return

        try:
            main_py = os.path.join(self.script_dir, "main.py")

            startupinfo = None
            env = os.environ.copy()
            env['PYTHONIOENCODING'] = 'utf-8'
            if sys.platform == 'win32':
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startupinfo.wShowWindow = subprocess.SW_HIDE

            creation_flags = 0
            if sys.platform == 'win32':
                # CREATE_NEW_CONSOLE + SW_HIDE：给子进程一个隐藏控制台。
                # 若用 CREATE_NO_WINDOW，子进程没有控制台，CTRL_BREAK_EVENT
                # 永远送达不了，main.py 的 safe_exit 无法触发，停止录制只能
                # 等 15 秒超时后整树强杀。CREATE_NEW_PROCESS_GROUP 使
                # CTRL_BREAK 只投递给子进程组，不影响 GUI 自身。
                creation_flags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NEW_CONSOLE

            proc = subprocess.Popen(
                [sys.executable, main_py],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding='utf-8',
                errors='replace',
                bufsize=1,
                cwd=self.script_dir,
                env=env,
                startupinfo=startupinfo,
                creationflags=creation_flags
            )

            self.process = proc
            self.process_pid = proc.pid
            self.running = True
            self.start_btn.configure(state=tk.DISABLED)
            self.stop_btn.configure(state=tk.NORMAL)

            self._set_status(Colors.SUCCESS, True)
            self._update_status_bar()

            self.output_thread = threading.Thread(target=self._read_output, args=(proc,), daemon=True)
            self.output_thread.start()

            self._log("━" * 40)
            self._log(f"录制进程已启动 (PID: {proc.pid})")
            self._log(f"Python: {sys.executable}")
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
            self._set_status(Colors.ERROR, False)
            self._update_status_bar()

    def stop_recording(self) -> None:
        # 停止录制
        proc = self.process

        if proc is None:
            messagebox.showwarning("警告", "没有正在运行的录制进程！")
            return

        self._log("━" * 40)
        self._log("正在停止录制...")

        # 防止等待线程完成前用户重复点击停止按钮
        self.stop_btn.configure(state=tk.DISABLED)

        # 优雅退出：让 main.py 的信号处理器自行清理其下的 ffmpeg（孙子进程）。
        # 子进程启动时使用 CREATE_NEW_CONSOLE 隐藏控制台 + 独立进程组，
        # 因此 CTRL_BREAK_EVENT 能送达 main.py → SIGBREAK → safe_exit →
        # cleanup_all_ffmpeg_processes。proc.terminate() 在 Windows 上是
        # TerminateProcess 硬杀，会把 ffmpeg 孤儿化，仅作兜底。
        if sys.platform == 'win32':
            self._log("正在发送 CTRL_BREAK 信号（触发子进程 safe_exit 清理 ffmpeg）...")
            if not _send_ctrl_break_to_child(proc.pid):
                self._log("发送 CTRL_BREAK 失败，回退 terminate", "warn")
                proc.terminate()
        else:
            self._log("正在发送 SIGINT 信号...")
            try:
                os.kill(proc.pid, signal.SIGINT)
            except Exception as e:
                self._log(f"发送 SIGINT 失败，回退 terminate: {e}")
                proc.terminate()

        def _wait_and_update_ui() -> None:
            # 先等待子进程自行清理其下所有 ffmpeg，超时再整树强杀
            terminated = False
            try:
                proc.wait(timeout=15)
                terminated = True
                self._log("进程已优雅退出（ffmpeg 已由子进程清理）")
            except subprocess.TimeoutExpired:
                self._log("进程未能及时退出，整树强制终止...")

            if not terminated and proc.poll() is None:
                try:
                    if sys.platform == 'win32':
                        # /T 递归杀掉 main.py 及其所有 ffmpeg 子进程，避免孤儿
                        subprocess.run(
                            ['taskkill', '/F', '/T', '/PID', str(proc.pid)],
                            capture_output=True, timeout=5
                        )
                    else:
                        proc.kill()
                        subprocess.run(
                            ['pkill', '-P', str(proc.pid), '-x', 'ffmpeg'],
                            capture_output=True, timeout=5
                        )
                    proc.wait(timeout=5)
                    self._log("进程已强制终止")
                except subprocess.TimeoutExpired:
                    self._log("警告：进程可能仍在运行！")
                except Exception as e:
                    self._log(f"强制终止失败: {e}")

            self.running = False
            self.process = None
            self.process_pid = None

            # 通过事件泵路由回 UI 线程（禁止直接跨线程调用 root.after）
            self.post_ui(self._on_recording_stopped)

        threading.Thread(target=_wait_and_update_ui, daemon=True).start()

    def _on_recording_stopped(self) -> None:
        # 进程终止后的 UI 更新回调（在 UI 线程中执行）
        self.start_btn.configure(state=tk.NORMAL)
        self.stop_btn.configure(state=tk.DISABLED)
        self._set_status(Colors.DANGER, False)
        self._update_status_bar()
        self._log("录制进程已停止")
        self._log("━" * 40)
        self._flush_log_queue()

    def _read_output(self, proc: subprocess.Popen[str]) -> None:
        # 读取子进程输出。proc 由调用方显式传入并全程使用局部引用，
        # 避免停止后立即重启时本线程误读新进程的 stdout（两线程抢读同一管道）。
        batch: list[tuple[str, str]] = []
        batch_size = 10

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
                line = proc.stdout.readline()
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

                clean_line = self.ANSI_ESCAPE_PATTERN.sub('', line.rstrip())
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

            total_lines = int(self.log_text.index('end-1c').split('.')[0])
            if total_lines > self._MAX_LOG_LINES:
                trim_count = total_lines - self._LOG_TRIM_TO
                self.log_text.delete('1.0', f'{trim_count + 1}.0')

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

    def _process_ended(self) -> None:
        # 子进程结束回调（仅在 UI 线程中调用）
        # 等待输出线程收尾，确保所有日志都被读取到 UI 后再重置状态
        if self.output_thread and self.output_thread.is_alive():
            self.output_thread.join(timeout=5)
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

    def _log(self, message: str, level: str = "info") -> None:
        # 添加日志到队列（线程安全）。本方法不触碰任何 Tk 对象，
        # 可在任意线程调用；刷新链由 UI 线程泵 _pump_ui_events 按需激活。
        self._log_queue.put([(message, level)])
        with self._log_queue_lock:
            self._log_queue_has_data = True

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

    # ─── 时间与状态栏 ──────────────────────────────────────

    @staticmethod
    def _get_timestamp() -> str:
        # 获取当前时间戳
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

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

    def _schedule_status_refresh(self) -> None:
        # 动态刷新状态：有录制时每3秒刷新，否则每10秒
        self._update_status_bar()
        self._watch_url_config()
        interval = self._STATUS_REFRESH_INTERVAL_ACTIVE if self.running else self._STATUS_REFRESH_INTERVAL
        self._refresh_job_id = self.root.after(interval, self._schedule_status_refresh)

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

    def minimize_to_tray(self) -> None:
        # 最小化到托盘；托盘不可用（如 Linux 无 X11）时降级为普通最小化，避免窗口无法恢复
        if self.system_tray and self.system_tray.running:
            self.root.withdraw()
            self.system_tray.notify('程序已最小化到系统托盘，双击托盘图标可恢复窗口')
        else:
            self.root.iconify()
            self._log("系统托盘不可用，已改为最小化到任务栏", "warn")

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

    def _shutdown_and_quit(self) -> None:
        # 后台执行：优雅停止录制子进程（由其清理 ffmpeg）→ 超时整树强杀 → 兜底清理
        proc = self.process
        child_pid = proc.pid if proc is not None else None
        if proc is not None:
            if sys.platform == 'win32':
                if not _send_ctrl_break_to_child(proc.pid):
                    proc.terminate()
            else:
                try:
                    os.kill(proc.pid, signal.SIGINT)
                except Exception:
                    proc.terminate()

            try:
                proc.wait(timeout=15)
            except subprocess.TimeoutExpired:
                # main.py 未能自行退出，整树强杀（含其下所有 ffmpeg，避免孤儿）
                try:
                    if sys.platform == 'win32':
                        subprocess.run(
                            ['taskkill', '/F', '/T', '/PID', str(proc.pid)],
                            capture_output=True, timeout=5
                        )
                    else:
                        proc.kill()
                        subprocess.run(
                            ['pkill', '-P', str(proc.pid), '-x', 'ffmpeg'],
                            capture_output=True, timeout=5
                        )
                    proc.wait(timeout=5)
                except Exception:
                    pass

            self.running = False
            self.process = None
            self.process_pid = None

        # 兜底清理进程树中可能残留的 ffmpeg（显式传入已捕获的 PID，
        # 避免此处读到已被清空的 self.process_pid 导致清理失效）
        self._cleanup_zombie_ffmpeg(child_pid)

        # 通过事件泵路由回 UI 线程收尾销毁（禁止直接跨线程调用 root.after）
        self.post_ui(self._finalize_quit)

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
            self.root.after_cancel(self._refresh_job_id)
            self._refresh_job_id = None

        self._stop_status_animation()

        if self.system_tray:
            self.system_tray.stop()

        self.root.quit()
        self.root.destroy()

    def _cleanup_zombie_ffmpeg(self, target_pid: int | None = None) -> None:
        # 清理录制子进程（main.py）及其下的 ffmpeg 进程。
        # 注意：ffmpeg 的父进程是 main.py，不是 GUI 自身，
        # 因此必须用 main.py 的 PID 整树强杀；按 GUI 自身 PID 过滤会匹配不到任何 ffmpeg。
        if target_pid is None:
            target_pid = self.process_pid
        found = False

        try:
            if sys.platform == 'win32':
                if target_pid is not None:
                    try:
                        subprocess.run(
                            ['taskkill', '/F', '/T', '/PID', str(target_pid)],
                            capture_output=True, timeout=5
                        )
                        found = True
                        self._log(f"已通过 taskkill 清理 PID {target_pid} 的进程树（含 ffmpeg）")
                    except Exception as e:
                        self._log(f"taskkill 执行失败: {e}")
                # 兜底：按镜像名清理 GUI 直接派生的 ffmpeg（极少出现）
                try:
                    subprocess.run(
                        ['taskkill', '/F', '/FI', 'IMAGENAME eq ffmpeg.exe',
                         '/FI', f'PARENTPID eq {os.getpid()}'],
                        capture_output=True, timeout=3
                    )
                except Exception:
                    pass
            else:
                if target_pid is not None:
                    try:
                        subprocess.run(
                            ['pkill', '-P', str(target_pid), '-x', 'ffmpeg'],
                            capture_output=True, timeout=3
                        )
                        found = True
                        self._log(f"已通过 pkill 清理 PID {target_pid} 下的 ffmpeg 进程")
                    except Exception as e:
                        self._log(f"pkill 执行失败: {e}")
                try:
                    subprocess.run(
                        ['pkill', '-P', str(os.getpid()), '-x', 'ffmpeg'],
                        capture_output=True, timeout=3
                    )
                except Exception:
                    pass

            if not found:
                self._log("未发现需要清理的 ffmpeg 进程")
        except Exception as e:
            self._log(f"清理 ffmpeg 进程时出错: {e}")

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
        ctk.CTkLabel(dialog, text="请选择关闭方式",
                     font=Fonts.heading()).pack()
        ctk.CTkLabel(dialog, text="您可以最小化到系统托盘，或完全退出程序",
                     font=Fonts.small(),
                     text_color=(Colors.MUTED_LIGHT, Colors.MUTED_DARK)).pack(pady=(4, 18))

        btn_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        btn_frame.pack(padx=16, pady=(0, 16))

        def minimize_to_tray_and_close() -> None:
            # 最小化到托盘并关闭对话框
            self.minimize_to_tray()
            dialog.destroy()

        def quit_and_close() -> None:
            # 退出应用并关闭对话框
            self.quit_application()
            dialog.destroy()

        ctk.CTkButton(btn_frame, text="📥   最小化到托盘", command=minimize_to_tray_and_close,
                      width=160, height=40, corner_radius=8,
                      fg_color=Colors.PRIMARY, hover_color=Colors.PRIMARY_HOVER,
                      text_color="#FFFFFF",
                      font=Fonts.body(bold=True)).pack(side=tk.LEFT, padx=(0, 10))

        ctk.CTkButton(btn_frame, text="❌   完全退出", command=quit_and_close,
                      width=140, height=40, corner_radius=8,
                      fg_color=Colors.DANGER, hover_color=Colors.DANGER_HOVER,
                      text_color="#FFFFFF",
                      font=Fonts.body(bold=True)).pack(side=tk.LEFT)

        # 键盘快捷键
        dialog.bind("<Escape>", lambda e: dialog.destroy())

        # 延迟 grab，等待窗口可见
        dialog.after(100, lambda: self._safe_dialog_grab(dialog))

    @staticmethod
    def _safe_dialog_grab(dialog: ctk.CTkToplevel) -> None:
        # 安全地设置模态
        try:
            dialog.grab_set()
        except Exception:
            pass


def main() -> None:
    # 主函数
    ctk.set_appearance_mode("system")
    ctk.set_default_color_theme("blue")

    root = ctk.CTk()
    app = LiveRecorderGUI(root)

    tray = SystemTray(app)
    app.system_tray = tray
    app.tray_thread = threading.Thread(target=tray.run, daemon=True)
    app.tray_thread.start()

    root.protocol("WM_DELETE_WINDOW", app.on_closing)
    root.mainloop()


if __name__ == "__main__":
    main()
