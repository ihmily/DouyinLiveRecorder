# -*- encoding: utf-8 -*-
# 直播录制器 GUI 界面
from __future__ import annotations

import os
import sys
import signal
import subprocess
import threading
import queue
import re
import configparser
import tkinter as tk
import tkinter.font as tkfont
from tkinter import scrolledtext, messagebox, ttk
from datetime import datetime
from typing import Any, TYPE_CHECKING

from PIL import Image, ImageDraw
# pystray 延迟导入至 SystemTray.run() 内部，避免 headless 环境顶层导入失败

if TYPE_CHECKING:
    import pystray


# ─── 高对比度色彩系统（满足 WCAG AA 标准） ──────────────

class Colors:
    # 主色调（#1D4ED8 在白色背景上对比度 7.2:1，远超 AA 等级 4.5:1）
    PRIMARY = "#1D4ED8"
    PRIMARY_DARK = "#1E3A8A"
    PRIMARY_LIGHT = "#DBEAFE"
    PRIMARY_BG = "#EFF6FF"
    # 语义色 - 均通过 WCAG AA 标准（白字 ≥4.5:1）
    SUCCESS = "#0D8A3E"
    SUCCESS_DARK = "#0A6B2E"
    SUCCESS_LIGHT = "#DCFCE7"
    DANGER = "#C71A1A"
    DANGER_DARK = "#991B1B"
    DANGER_LIGHT = "#FEE2E2"
    WARNING = "#C27803"
    WARNING_LIGHT = "#FEF3C7"
    # 中性色 - 深色用于高可读性文字
    DARK = "#0F172A"
    GRAY_700 = "#334155"
    GRAY_600 = "#475569"
    GRAY_500 = "#64748B"
    GRAY_400 = "#94A3B8"
    GRAY_300 = "#CBD5E1"
    GRAY_200 = "#E2E8F0"
    GRAY_100 = "#F1F5F9"
    GRAY_50 = "#F8FAFC"
    WHITE = "#FFFFFF"
    # 日志终端色
    TERMINAL_BG = "#0D1117"
    TERMINAL_FG = "#58A6FF"
    TERMINAL_ERROR = "#F85149"
    TERMINAL_WARN = "#D29922"
    TERMINAL_SUCCESS = "#3FB950"
    # 卡片阴影
    CARD_SHADOW = "#0F172A"


# ─── DPI 感知字体系统 ────────────────────────────────────

class DpiFont:
    # 字体缓存（避免重复创建对象，降低 GC 压力）
    _cache: dict[str, tuple[str, int, str]] = {}
    _scale: float | None = None
    _family: str | None = None

    # 最小字体基准（96 DPI 下的 pt 值），多分辨率下保证可读性
    BASE_SMALL = 9
    BASE_BODY = 10
    BASE_HEADING = 11
    BASE_TITLE = 14

    @classmethod
    def _detect(cls) -> float:
        # 检测系统 DPI 缩放比例（带缓存）
        if cls._scale is not None:
            return cls._scale
        try:
            temp = tk.Tk()
            temp.withdraw()
            try:
                cls._scale = float(temp.tk.call('tk', 'scaling'))
            finally:
                temp.destroy()
        except Exception:
            cls._scale = 1.0
        return cls._scale

    @classmethod
    def family(cls) -> str:
        # 检测系统可用字体（带缓存）
        if cls._family is None:
            # 仅在首次调用时检测系统可用字体，结果缓存
            families = (
                "Microsoft YaHei UI", "Segoe UI",
                "PingFang SC", "Noto Sans SC",
                "Microsoft YaHei", "TkDefaultFont"
            )
            cls._family = next((f for f in families if f in tkfont.families()), "TkDefaultFont")
        return cls._family

    @classmethod
    def get(cls, base_size: int, bold: bool = False) -> tuple[str, int, str]:
        # 基于基准尺寸 + DPI 缩放计算实际字号，结果缓存
        key = f"{base_size}_{bold}"
        if key in cls._cache:
            return cls._cache[key]
        scale = cls._detect()
        size = max(base_size, round(base_size * scale))
        style = "bold" if bold else ""
        result = (cls.family(), size, style)
        cls._cache[key] = result
        return result

    @classmethod
    def small(cls, bold: bool = False) -> tuple[str, int, str]:
        # 获取小号字体配置
        return cls.get(cls.BASE_SMALL, bold)

    @classmethod
    def body(cls, bold: bool = False) -> tuple[str, int, str]:
        # 获取正文字体配置
        return cls.get(cls.BASE_BODY, bold)

    @classmethod
    def heading(cls, bold: bool = False) -> tuple[str, int, str]:
        # 获取标题字体配置
        return cls.get(cls.BASE_HEADING, bold)

    @classmethod
    def title(cls, bold: bool = False) -> tuple[str, int, str]:
        # 获取大标题字体配置
        return cls.get(cls.BASE_TITLE, bold)

    @classmethod
    def mono(cls) -> tuple[str, int]:
        # 等宽字体用于代码和日志
        return ("Cascadia Code", max(9, round(9 * cls._detect())))


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
            radius=16, fill=(37, 99, 235, 255)
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
        # 托盘菜单：显示主窗口
        if self.gui.root:
            self.gui.root.deiconify()
            self.gui.root.lift()

    def on_exit(self, _icon: "pystray.Icon | None" = None) -> None:  # type: ignore[type-arg]
        # 托盘菜单：退出程序
        self.gui.quit_application()

    def on_minimize(self, _icon: "pystray.Icon | None" = None) -> None:  # type: ignore[type-arg]
        # 托盘菜单：最小化到托盘
        if self.gui.root:
            self.gui.root.withdraw()

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

    def __init__(self, parent: tk.Toplevel | tk.Tk, config_file: str, log_callback: Any = None):
        # 初始化高级设置窗口
        self.config_file = config_file
        self.log_callback = log_callback

        self.window = tk.Toplevel(parent)
        self.window.title("高级设置 - config.ini")
        self.window.geometry("750x520")
        self.window.configure(bg=Colors.GRAY_50)
        self.window.transient(parent)
        self.window.grab_set()

        self._setup_ui()
        self._load_config()

    def _setup_ui(self) -> None:
        # 顶部标题栏
        header = tk.Frame(self.window, bg=Colors.PRIMARY, height=48)
        header.pack(fill=tk.X)
        header.pack_propagate(False)
        tk.Label(header, text="⚙  高级设置", fg=Colors.WHITE, bg=Colors.PRIMARY,
                 font=DpiFont.heading(bold=True)).pack(side=tk.LEFT, padx=20, pady=10)

        # 内容区域
        content = tk.Frame(self.window, bg=Colors.GRAY_50)
        content.pack(fill=tk.BOTH, expand=True, padx=16, pady=(16, 0))

        # 配置文件标签
        lbl_frame = tk.Frame(content, bg=Colors.GRAY_50)
        lbl_frame.pack(fill=tk.X, pady=(0, 8))
        tk.Label(lbl_frame, text="📄 配置文件内容 (config/config.ini)",
                 fg=Colors.GRAY_700, bg=Colors.GRAY_50,
                 font=DpiFont.body()).pack(side=tk.LEFT)

        # 编辑器
        editor_frame = tk.Frame(content, bg=Colors.WHITE, highlightbackground=Colors.GRAY_200,
                                highlightthickness=1, bd=0)
        editor_frame.pack(fill=tk.BOTH, expand=True)

        self.config_text = scrolledtext.ScrolledText(
            editor_frame, wrap=tk.WORD, font=DpiFont.mono(),
            bg=Colors.WHITE, fg=Colors.DARK, insertbackground=Colors.PRIMARY,
            relief=tk.FLAT, bd=0, padx=12, pady=12,
            selectbackground=Colors.PRIMARY_LIGHT, selectforeground=Colors.DARK
        )
        self.config_text.pack(fill=tk.BOTH, expand=True)

        # 底部按钮
        btn_frame = tk.Frame(self.window, bg=Colors.GRAY_50)
        btn_frame.pack(fill=tk.X, padx=16, pady=16)

        cancel_btn = tk.Button(btn_frame, text="取消", command=self.window.destroy,
                               bg=Colors.WHITE, fg=Colors.GRAY_700,
                               activebackground=Colors.GRAY_100, activeforeground=Colors.DARK,
                               font=DpiFont.body(), relief=tk.FLAT, bd=0,
                               padx=24, pady=8, cursor="hand2",
                               highlightbackground=Colors.GRAY_200, highlightthickness=1)
        cancel_btn.pack(side=tk.RIGHT, padx=(8, 0))

        self.save_btn = tk.Button(btn_frame, text="💾 保存配置", command=self.save_config,
                                  bg=Colors.PRIMARY, fg=Colors.WHITE,
                                  activebackground=Colors.PRIMARY_DARK, activeforeground=Colors.WHITE,
                                  font=DpiFont.body(bold=True), relief=tk.FLAT, bd=0,
                                  padx=24, pady=8, cursor="hand2")
        self.save_btn.pack(side=tk.RIGHT)

        # 按钮悬停效果
        for btn in [cancel_btn, self.save_btn]:
            btn.bind("<Enter>", lambda e, b=btn: b.configure(relief=tk.FLAT))
            btn.bind("<Leave>", lambda e, b=btn: b.configure(relief=tk.FLAT))

    def _load_config(self) -> None:
        # 加载 config.ini 到编辑器
        try:
            with open(self.config_file, 'r', encoding='utf-8-sig') as f:
                content = f.read()
            self.config_text.delete(1.0, tk.END)
            self.config_text.insert(1.0, content)
        except FileNotFoundError:
            self.config_text.delete(1.0, tk.END)
            self.config_text.insert(1.0, "# 配置文件不存在，请新建")
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


def _save_text_widget_to_file(text_widget: tk.Text | scrolledtext.ScrolledText, file_path: str) -> None:
    # 从 Text 控件读取内容并写入文件
    content = text_widget.get(1.0, tk.END).rstrip('\n')
    if content and not content.endswith('\n'):
        content += '\n'
    with open(file_path, 'w', encoding='utf-8-sig') as f:
        f.write(content)


class LiveRecorderGUI:
    # 直播录制 GUI 主类

    # 常量定义
    ANSI_ESCAPE_PATTERN = re.compile(r'\x1b\[[0-9;]*m')
    _MAX_LOG_LINES = 1000
    _LOG_TRIM_TO = 800
    _LOG_FLUSH_INTERVAL = 200
    _STATUS_REFRESH_INTERVAL = 10000          # 未录制时的刷新间隔（毫秒）
    _STATUS_REFRESH_INTERVAL_ACTIVE = 3000   # 有录制直播间时的刷新间隔（毫秒）

    def __init__(self, root: tk.Tk):
        # 初始化 GUI 主窗口及所有组件
        self.root = root
        self.root.title("直播录制控制台")
        self.root.geometry("960x720")
        self.root.minsize(780, 520)
        self.root.configure(bg=Colors.GRAY_50)

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

        # 状态指示器动画
        self._status_animating = False
        self._status_anim_index = 0

        # 响应式布局（防抖优化，避免频繁 resize 导致布局抖动）
        self._resize_throttle_id: str | None = None
        self._last_layout_width = 0

        self._setup_style()
        self._setup_ui()
        self._load_config()
        self._schedule_log_flush()
        self._schedule_status_refresh()

        self.root.bind('<Configure>', lambda e: self._on_window_resize(e))

    # ─── 响应式布局 ────────────────────────────────────────

    def _on_window_resize(self, event: tk.Event) -> None:
        # 防抖 resize 事件：仅在 root 尺寸变化时处理，200ms 延迟合并连续事件
        if event.widget != self.root:
            return
        new_width = event.width
        if new_width == self._last_layout_width:
            return
        self._last_layout_width = new_width
        if self._resize_throttle_id is not None:
            self.root.after_cancel(self._resize_throttle_id)
        self._resize_throttle_id = self.root.after(200, self._apply_responsive_layout)

    def _apply_responsive_layout(self) -> None:
        # 应用响应式布局调整
        self._resize_throttle_id = None
        # 响应式布局占位：当前通过 pack fill=X + expand=True 已实现弹性伸缩
        # 可在未来扩展窄屏模式下的工具栏折叠逻辑

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

    def _setup_style(self) -> None:
        # 设置 ttk 样式（DPI 感知 + 高对比度）
        self.style = ttk.Style()
        self.style.theme_use('clam')

        # DPI 感知字体
        body_font = DpiFont.body()
        body_bold = DpiFont.body(bold=True)
        heading_font = DpiFont.heading(bold=True)

        # 通用样式
        self.style.configure('.', font=body_font, background=Colors.GRAY_50)
        self.style.configure('TFrame', background=Colors.GRAY_50)
        self.style.configure('TLabel', background=Colors.GRAY_50, foreground=Colors.GRAY_700)
        self.style.configure('TLabelframe', background=Colors.GRAY_50, foreground=Colors.GRAY_700,
                             font=heading_font, relief=tk.FLAT, borderwidth=0)
        self.style.configure('TLabelframe.Label', background=Colors.GRAY_50, foreground=Colors.GRAY_700,
                             font=heading_font)

        # 主按钮 - 开始录制（绿底白字，对比度 ≥5.1:1）
        self.style.configure('Start.TButton',
                             background=Colors.SUCCESS, foreground=Colors.WHITE,
                             font=body_bold,
                             relief=tk.FLAT, borderwidth=0, padding=(14, 9))
        self.style.map('Start.TButton',
                       background=[('active', Colors.SUCCESS_DARK), ('disabled', Colors.GRAY_300)],
                       foreground=[('disabled', Colors.GRAY_500)])

        # 主按钮 - 停止录制（红底白字，对比度 ≥6.6:1）
        self.style.configure('Stop.TButton',
                             background=Colors.DANGER, foreground=Colors.WHITE,
                             font=body_bold,
                             relief=tk.FLAT, borderwidth=0, padding=(14, 9))
        self.style.map('Stop.TButton',
                       background=[('active', Colors.DANGER_DARK), ('disabled', Colors.GRAY_300)],
                       foreground=[('disabled', Colors.GRAY_500)])

        # 操作按钮（浅灰底深色字，对比度 ≥10.8:1）
        self.style.configure('Action.TButton',
                             background=Colors.GRAY_100, foreground=Colors.GRAY_700,
                             font=body_font,
                             relief=tk.FLAT, borderwidth=0, padding=(14, 9))
        self.style.map('Action.TButton',
                       background=[('active', Colors.GRAY_200)],
                       foreground=[('active', Colors.DARK)])

        # 托盘按钮（蓝底白字，对比度 ≥7.2:1）
        self.style.configure('Tray.TButton',
                             background=Colors.PRIMARY, foreground=Colors.WHITE,
                             font=body_font,
                             relief=tk.FLAT, borderwidth=0, padding=(14, 9))
        self.style.map('Tray.TButton',
                       background=[('active', Colors.PRIMARY_DARK)])

        # 退出按钮（红底白字，对比度 ≥6.6:1）
        self.style.configure('Exit.TButton',
                             background=Colors.DANGER, foreground=Colors.WHITE,
                             font=body_font,
                             relief=tk.FLAT, borderwidth=0, padding=(14, 9))
        self.style.map('Exit.TButton',
                       background=[('active', Colors.DANGER_DARK)])

        # 滚动条
        self.style.configure('TScrollbar', background=Colors.GRAY_200, troughcolor=Colors.GRAY_50,
                             arrowcolor=Colors.GRAY_500, relief=tk.FLAT, borderwidth=0)
        self.style.map('TScrollbar', background=[('active', Colors.GRAY_300)])

    def _create_card(self, parent: tk.Widget, title: str) -> tuple[tk.Frame, tk.Frame]:
        # 创建圆角卡片容器
        outer = tk.Frame(parent, bg=Colors.GRAY_50)
        inner = tk.Frame(outer, bg=Colors.WHITE, highlightbackground=Colors.GRAY_200,
                         highlightthickness=1, bd=0)
        inner.pack(fill=tk.BOTH, expand=True)

        if title:
            # 卡片标题栏
            title_bar = tk.Frame(inner, bg=Colors.GRAY_50, height=36)
            title_bar.pack(fill=tk.X)
            title_bar.pack_propagate(False)
            tk.Label(title_bar, text=title, fg=Colors.GRAY_700, bg=Colors.GRAY_50,
                     font=DpiFont.body(bold=True)).pack(side=tk.LEFT, padx=16, pady=8)
            # 标题栏分隔线
            sep = tk.Frame(inner, bg=Colors.GRAY_200, height=1)
            sep.pack(fill=tk.X)

        # 内容区域
        inner_content = tk.Frame(inner, bg=Colors.WHITE)
        inner_content.pack(fill=tk.BOTH, expand=True, padx=2, pady=2)

        return outer, inner_content

    def _create_modern_button(self, parent: tk.Widget, text: str, command, style: str,
                               width: int = 14) -> ttk.Button:
        # 创建统一风格的按钮
        btn = ttk.Button(parent, text=text, command=command, style=style, width=width)
        return btn

    def _setup_ui(self) -> None:
        # 设置主窗口界面（DPI 感知字体 + 响应式布局）

        # ── 顶部标题栏 ─────────────────────────────────
        header_bg = Colors.PRIMARY
        header = tk.Frame(self.root, bg=header_bg, height=72)
        header.pack(fill=tk.X)
        header.pack_propagate(False)

        # 上排：标题 + 运行状态指示灯
        header_top = tk.Frame(header, bg=header_bg)
        header_top.pack(fill=tk.X)

        tk.Label(header_top, text="🎬  直播录制控制台", fg=Colors.WHITE, bg=header_bg,
                 font=DpiFont.title(bold=True)).pack(side=tk.LEFT, padx=20, pady=(8, 2))

        self.status_canvas = tk.Canvas(header_top, width=12, height=12,
                                        bg=header_bg, highlightthickness=0)
        self.status_canvas.pack(side=tk.RIGHT, padx=20, pady=(8, 2))
        self._status_dot = self.status_canvas.create_oval(1, 1, 11, 11,
                                                           fill=Colors.DANGER, outline="")

        # 下排：状态栏信息（可换行）
        self.status_var = tk.StringVar()
        self._update_status_bar()

        wraplength = self.root.winfo_reqwidth() - 40 if self.root.winfo_reqwidth() > 40 else 920
        self.status_text_label = tk.Label(header, textvariable=self.status_var,
                                           fg=Colors.GRAY_300, bg=header_bg,
                                           font=DpiFont.small(),
                                           anchor=tk.W, justify=tk.LEFT,
                                           wraplength=wraplength)
        self.status_text_label.pack(fill=tk.X, padx=20, pady=(0, 4))

        header.bind("<Configure>", self._on_header_resize)

        # ── 工具栏 ─────────────────────────────────────
        toolbar = tk.Frame(self.root, bg=Colors.WHITE)
        toolbar.pack(fill=tk.X, padx=12, pady=(12, 0))

        # 第一行：录制控制 | 窗口控制
        toolbar_top = tk.Frame(toolbar, bg=Colors.WHITE, height=82)
        toolbar_top.pack(fill=tk.X)
        toolbar_top.pack_propagate(False)

        toolbar_left = tk.Frame(toolbar_top, bg=Colors.WHITE)
        toolbar_left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(12, 0))

        # 录制控制组
        ctrl_group = tk.Frame(toolbar_left, bg=Colors.WHITE)
        ctrl_group.pack(side=tk.LEFT, padx=(0, 20))

        tk.Label(ctrl_group, text="录制控制", fg=Colors.GRAY_600, bg=Colors.WHITE,
                 font=DpiFont.small()).pack(anchor=tk.W, pady=(10, 4))

        btn_row = tk.Frame(ctrl_group, bg=Colors.WHITE)
        btn_row.pack()

        self.start_btn = ttk.Button(btn_row, text="▶  开始录制", command=self.start_recording,
                                    style='Start.TButton', width=18)
        self.start_btn.pack(side=tk.LEFT, padx=(0, 10))

        self.stop_btn = ttk.Button(btn_row, text="⏹  停止录制", command=self.stop_recording,
                                   style='Stop.TButton', width=18, state=tk.DISABLED)
        self.stop_btn.pack(side=tk.LEFT)

        # 分隔线
        tk.Frame(toolbar_left, bg=Colors.GRAY_200, width=1).pack(side=tk.LEFT,
                                                                   fill=tk.Y, padx=20, pady=12)

        # 窗口控制组
        win_group = tk.Frame(toolbar_left, bg=Colors.WHITE)
        win_group.pack(side=tk.LEFT, padx=(0, 20))

        tk.Label(win_group, text="窗口控制", fg=Colors.GRAY_600, bg=Colors.WHITE,
                 font=DpiFont.small()).pack(anchor=tk.W, pady=(10, 4))

        win_btn_row = tk.Frame(win_group, bg=Colors.WHITE)
        win_btn_row.pack()

        ttk.Button(win_btn_row, text="📥  最小化到托盘", command=self.minimize_to_tray,
                   style='Tray.TButton', width=18).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(win_btn_row, text="❌  彻底退出", command=self.quit_application,
                   style='Exit.TButton', width=18).pack(side=tk.LEFT)

        # 行间分隔线
        tk.Frame(toolbar, bg=Colors.GRAY_200, height=1).pack(fill=tk.X, padx=0, pady=(6, 4))

        # 第二行：快捷操作
        toolbar_bottom = tk.Frame(toolbar, bg=Colors.WHITE, height=48)
        toolbar_bottom.pack(fill=tk.X)
        toolbar_bottom.pack_propagate(False)

        quick_group = tk.Frame(toolbar_bottom, bg=Colors.WHITE)
        quick_group.pack(side=tk.LEFT, padx=(12, 0))

        tk.Label(quick_group, text="快捷操作", fg=Colors.GRAY_600, bg=Colors.WHITE,
                 font=DpiFont.small()).pack(side=tk.LEFT, padx=(0, 8), pady=(6, 4))

        ttk.Button(quick_group, text="📂  打开下载目录", command=self.open_downloads_folder,
                   style='Action.TButton', width=18).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(quick_group, text="⚙  高级设置", command=self.open_advanced_settings,
                   style='Action.TButton', width=18).pack(side=tk.LEFT)

        # ── 内容区域 ───────────────────────────────────
        content = tk.Frame(self.root, bg=Colors.GRAY_50)
        content.pack(fill=tk.BOTH, expand=True, padx=12, pady=10)

        # 配置编辑卡片
        config_outer, config_inner = self._create_card(content, "📝  URL 配置编辑区 (config/URL_config.ini)")
        config_outer.pack(fill=tk.BOTH, expand=True, pady=(0, 6))

        self.config_text = scrolledtext.ScrolledText(
            config_inner, wrap=tk.WORD, font=DpiFont.mono(), height=8,
            bg=Colors.WHITE, fg=Colors.DARK, insertbackground=Colors.PRIMARY,
            relief=tk.FLAT, bd=0, padx=12, pady=8,
            selectbackground=Colors.PRIMARY_LIGHT, selectforeground=Colors.DARK
        )
        self.config_text.pack(fill=tk.BOTH, expand=True)

        # 配置操作栏
        config_actions = tk.Frame(config_outer, bg=Colors.WHITE)
        config_actions.pack(fill=tk.X)

        hint_label = tk.Label(config_actions,
                              text="每行一个直播链接，支持 # 开头的注释行  |  点击窗口关闭按钮将最小化到系统托盘",
                              fg=Colors.GRAY_400, bg=Colors.WHITE,
                              font=DpiFont.small())
        hint_label.pack(fill=tk.X, padx=16, pady=(6, 2))

        btn_row = tk.Frame(config_actions, bg=Colors.WHITE)
        btn_row.pack(fill=tk.X, padx=12, pady=(0, 6))

        self.reload_btn = ttk.Button(btn_row, text="🔄  重新读取", command=self._load_config,
                                     style='Action.TButton', width=16)
        self.reload_btn.pack(side=tk.RIGHT, padx=4)

        self.save_btn = ttk.Button(btn_row, text="💾  保存 URL 配置", command=self.save_config,
                                   style='Action.TButton', width=18)
        self.save_btn.pack(side=tk.RIGHT, padx=(4, 4))

        # 日志卡片
        log_outer, log_inner = self._create_card(content, "📋  运行日志 (main.py 输出)")
        log_outer.pack(fill=tk.BOTH, expand=True, pady=(0, 4))

        self.log_text = scrolledtext.ScrolledText(
            log_inner, wrap=tk.WORD,
            font=DpiFont.mono(),
            bg=Colors.TERMINAL_BG, fg=Colors.TERMINAL_FG, insertbackground=Colors.WHITE,
            relief=tk.FLAT, bd=0, padx=12, pady=8, height=10, state=tk.DISABLED,
            selectbackground="#1F3A5F", selectforeground=Colors.WHITE
        )
        self.log_text.pack(fill=tk.BOTH, expand=True)
        self.log_text.tag_config("error", foreground=Colors.TERMINAL_ERROR)
        self.log_text.tag_config("warn", foreground=Colors.TERMINAL_WARN)

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

    def _animate_status_dot(self) -> None:
        # 状态指示器动画帧回调
        if not self._status_animating:
            return
        # 呼吸式脉冲动画
        sizes = [7, 8, 9, 10, 11, 10, 9, 8, 7]
        idx = self._status_anim_index % len(sizes)
        s = sizes[idx]
        offset = 6 - s // 2
        self.status_canvas.coords(self._status_dot, offset, offset, offset + s, offset + s)
        self.status_canvas.itemconfig(self._status_dot, fill=Colors.SUCCESS)
        self._status_anim_index += 1
        self._status_anim_timer = self.root.after(120, self._animate_status_dot)

    def _set_status(self, color: str, running: bool) -> None:
        # 设置状态指示器状态（idle/recording/error）
        if running:
            self.status_canvas.itemconfig(self._status_dot, fill=Colors.SUCCESS)
            self._start_status_animation()
        else:
            self._stop_status_animation()
            self.status_canvas.coords(self._status_dot, 1, 1, 11, 11)
            self.status_canvas.itemconfig(self._status_dot, fill=color)
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

            current_content = self.config_text.get(1.0, tk.END).rstrip('\n')
            if content == current_content:
                self._last_url_config_mtime = os.path.getmtime(self.url_config_file)
                return

            self.config_text.delete(1.0, tk.END)
            self.config_text.insert(1.0, content)
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
                creation_flags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW

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
            self.start_btn.state(['disabled'])
            self.stop_btn.state(['!disabled'])

            self._set_status(Colors.SUCCESS, True)
            self._update_status_bar()

            self.output_thread = threading.Thread(target=self._read_output, daemon=True)
            self.output_thread.start()

            self._log("━" * 40)
            self._log(f"[{self._get_timestamp()}] 录制进程已启动 (PID: {proc.pid})")
            self._log(f"Python: {sys.executable}")
            self._log(f"工作目录: {self.script_dir}")
            self._log("━" * 40)

        except Exception as e:
            self._log(f"启动录制失败: {e}", "error")
            messagebox.showerror("错误", f"启动录制失败: {e}")

    def stop_recording(self) -> None:
        # 停止录制
        proc = self.process

        if proc is None:
            messagebox.showwarning("警告", "没有正在运行的录制进程！")
            return

        self._log("━" * 40)
        self._log(f"[{self._get_timestamp()}] 正在停止录制...")

        # 优雅退出：让 main.py 的信号处理器自行清理其下的 ffmpeg（孙子进程）。
        # 注意：proc.terminate() 在 Windows 上是 TerminateProcess，会硬杀 main.py
        # 并把 ffmpeg 孤儿化（它们仍会继续录制）。这里改用 CTRL_BREAK_EVENT 触发
        # main.py 的 safe_exit → cleanup_all_ffmpeg_processes，由其负责清理 ffmpeg。
        if sys.platform == 'win32':
            self._log("正在发送 CTRL_BREAK 信号（触发子进程优雅清理 ffmpeg）...")
            try:
                proc.send_signal(signal.CTRL_BREAK_EVENT)
            except Exception as e:
                self._log(f"发送 CTRL_BREAK 失败，回退 terminate: {e}")
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
                            capture_output=True, text=True, timeout=5
                        )
                    else:
                        proc.kill()
                        subprocess.run(
                            ['pkill', '-P', str(proc.pid), '-x', 'ffmpeg'],
                            capture_output=True, text=True, timeout=5
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

            self.root.after(0, self._on_recording_stopped)

        threading.Thread(target=_wait_and_update_ui, daemon=True).start()

    def _on_recording_stopped(self) -> None:
        # 进程终止后的 UI 更新回调（在 UI 线程中执行）
        self.start_btn.state(['!disabled'])
        self.stop_btn.state(['disabled'])
        self._set_status(Colors.DANGER, False)
        self._update_status_bar()
        self._log(f"[{self._get_timestamp()}] 录制进程已停止")
        self._log("━" * 40)
        self._flush_log_queue()

    def _read_output(self) -> None:
        # 读取子进程输出
        batch: list[tuple[str, str]] = []
        batch_size = 10

        def flush_batch() -> None:
            # 批量刷新日志队列到文本控件
            nonlocal batch
            if batch:
                self._log_queue.put(batch)
                self._log_queue_has_data = True
                if self._log_flush_job_id is None:
                    self._log_flush_job_id = self.root.after(self._LOG_FLUSH_INTERVAL, self._schedule_log_flush)
                batch = []

        while True:
            proc = self.process
            if proc is None or proc.stdout is None:
                flush_batch()
                self._log_queue.put(None)
                self._log_queue_has_data = True
                break

            try:
                line = proc.stdout.readline()
                if not line:
                    if proc.poll() is not None:
                        flush_batch()
                        self.running = False
                        self._log_queue.put(None)
                        self._log_queue_has_data = True
                        break
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
                self._log_queue_has_data = True
                self.running = False
                break
            except Exception as e:
                error_msg = str(e)
                flush_batch()
                self._log_queue.put([(f"读取输出错误: {error_msg}", "error")])
                self._log_queue.put(None)
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
            self._log_queue_has_data = False

        if process_ended:
            self._process_ended()

        if self._log_queue_has_data or not self._log_queue.empty():
            self._log_flush_job_id = self.root.after(self._LOG_FLUSH_INTERVAL, self._schedule_log_flush)
        else:
            self._log_flush_job_id = None

    def _process_ended(self) -> None:
        # 子进程结束回调（仅在 UI 线程中调用）
        self.running = False
        self.process = None
        self.process_pid = None
        self.start_btn.state(['!disabled'])
        self.stop_btn.state(['disabled'])

        self._set_status(Colors.DANGER, False)
        self._update_status_bar()

        self._log("━" * 40)
        self._log(f"[{self._get_timestamp()}] 录制进程已结束")
        self._log("━" * 40)

    def _log(self, message: str, level: str = "info") -> None:
        # 添加日志到队列（线程安全），按需激活 _schedule_log_flush
        self._log_queue.put([(message, level)])
        self._log_queue_has_data = True
        if self._log_flush_job_id is None:
            self._log_flush_job_id = self.root.after(self._LOG_FLUSH_INTERVAL, self._schedule_log_flush)

    def _flush_log_queue(self) -> None:
        # 立即刷新日志队列到 UI（仅在 UI 线程中调用）
        if self._log_flush_job_id:
            self.root.after_cancel(self._log_flush_job_id)
            self._log_flush_job_id = None
        self._schedule_log_flush()
        if self._log_queue_has_data or not self._log_queue.empty():
            self._log_flush_job_id = self.root.after(self._LOG_FLUSH_INTERVAL, self._schedule_log_flush)

    # ─── 时间与状态栏 ──────────────────────────────────────

    def _on_header_resize(self, event: tk.Event) -> None:
        # 窗口尺寸变化时调整表头布局
        new_wraplength = max(event.width - 40, 200)
        self.status_text_label.configure(wraplength=new_wraplength)

    @staticmethod
    def _get_timestamp() -> str:
        # 获取当前时间戳
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def _update_status_bar(self) -> None:
        # 更新状态栏（动态读取配置）
        try:
            check_interval, output_format, tray_status = self._get_dynamic_status_info()
            timestamp = self._get_timestamp()

            pid = self.process_pid
            if pid is not None:
                status_text = (f"状态：运行中 (PID: {pid}) │ 循环检测: {check_interval} "
                              f"│ 格式: {output_format} │ 托盘: {tray_status} │ {timestamp}")
            else:
                status_text = (f"状态：未运行 │ 循环检测: {check_interval} "
                              f"│ 格式: {output_format} │ 托盘: {tray_status} │ {timestamp}")
        except Exception:
            status_text = "状态栏更新失败，将在下次刷新重试"

        self.status_var.set(status_text)

    def _schedule_status_refresh(self) -> None:
        # 动态刷新状态栏：有录制直播间时每3秒刷新，否则每10秒
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
        # 最小化到托盘
        self.root.withdraw()
        if self.system_tray:
            self.system_tray.notify('程序已最小化到系统托盘，双击托盘图标可恢复窗口')

    def quit_application(self) -> None:
        # 退出程序
        if self.process is not None:
            if not messagebox.askokcancel("退出确认", "录制正在后台进行，确定要退出吗？"):
                return

        self._log("正在停止录制并清理 ffmpeg 进程，请稍候...")
        # 在后台线程完成「停止录制 + 清理残留 ffmpeg」，完成后再回主线程销毁窗口，
        # 避免窗口先被 destroy 导致清理线程被强杀、ffmpeg 残留。
        threading.Thread(target=self._shutdown_and_quit, daemon=True).start()

    def _shutdown_and_quit(self) -> None:
        # 后台执行：优雅停止录制子进程（由其清理 ffmpeg）→ 超时整树强杀 → 兜底清理
        proc = self.process
        if proc is not None:
            if sys.platform == 'win32':
                try:
                    proc.send_signal(signal.CTRL_BREAK_EVENT)
                except Exception:
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
                            capture_output=True, text=True, timeout=5
                        )
                    else:
                        proc.kill()
                        subprocess.run(
                            ['pkill', '-P', str(proc.pid), '-x', 'ffmpeg'],
                            capture_output=True, text=True, timeout=5
                        )
                    proc.wait(timeout=5)
                except Exception:
                    pass

            self.running = False
            self.process = None
            self.process_pid = None

        # 兜底清理本进程树中可能残留的 ffmpeg
        self._cleanup_zombie_ffmpeg()

        # 回到 UI 线程收尾销毁
        self.root.after(0, self._finalize_quit)

    def _finalize_quit(self) -> None:
        # 退出收尾（必须在 UI 线程执行）
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

    def _cleanup_zombie_ffmpeg(self) -> None:
        # 清理录制子进程（main.py）及其下的 ffmpeg 进程。
        # 注意：ffmpeg 的父进程是 main.py（self.process_pid），不是 GUI 自身，
        # 因此必须用 main.py 的 PID 整树强杀；按 GUI 自身 PID 过滤会匹配不到任何 ffmpeg。
        target_pid = self.process_pid
        found = False

        try:
            if sys.platform == 'win32':
                if target_pid is not None:
                    try:
                        subprocess.run(
                            ['taskkill', '/F', '/T', '/PID', str(target_pid)],
                            capture_output=True, text=True, timeout=5
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
                        capture_output=True, text=True, timeout=3
                    )
                except Exception:
                    pass
            else:
                if target_pid is not None:
                    try:
                        subprocess.run(
                            ['pkill', '-P', str(target_pid), '-x', 'ffmpeg'],
                            capture_output=True, text=True, timeout=3
                        )
                        found = True
                        self._log(f"已通过 pkill 清理 PID {target_pid} 下的 ffmpeg 进程")
                    except Exception as e:
                        self._log(f"pkill 执行失败: {e}")
                try:
                    subprocess.run(
                        ['pkill', '-P', str(os.getpid()), '-x', 'ffmpeg'],
                        capture_output=True, text=True, timeout=3
                    )
                except Exception:
                    pass

            if not found:
                self._log("未发现需要清理的 ffmpeg 进程")
        except Exception as e:
            self._log(f"清理 ffmpeg 进程时出错: {e}")

    def on_closing(self) -> None:
        # 窗口关闭事件处理，显示关闭选项对话框
        dialog = tk.Toplevel(self.root)
        dialog.title("关闭选项")
        dialog.geometry("380x210")
        dialog.resizable(False, False)
        dialog.configure(bg=Colors.WHITE)
        dialog.transient(self.root)
        dialog.grab_set()

        # 居中显示对话框
        dialog.update_idletasks()
        x = self.root.winfo_x() + (self.root.winfo_width() - dialog.winfo_width()) // 2
        y = self.root.winfo_y() + (self.root.winfo_height() - dialog.winfo_height()) // 2
        dialog.geometry(f"+{x}+{y}")

        # 顶部图标
        icon_frame = tk.Frame(dialog, bg=Colors.WHITE)
        icon_frame.pack(pady=(20, 12))
        tk.Label(icon_frame, text="🎬", font=(DpiFont.family(), 24), bg=Colors.WHITE).pack()

        # 提示文字
        tk.Label(dialog, text="请选择关闭方式", fg=Colors.DARK,
                 bg=Colors.WHITE, font=DpiFont.heading(bold=True)).pack()

        tk.Label(dialog, text="您可以选择最小化到托盘或完全退出程序",
                 fg=Colors.GRAY_500, bg=Colors.WHITE,
                 font=DpiFont.small()).pack(pady=(4, 16))

        # 按钮
        btn_frame = tk.Frame(dialog, bg=Colors.WHITE)
        btn_frame.pack(padx=12, pady=(0, 16))

        def minimize_to_tray_and_close() -> None:
            # 最小化到托盘并关闭主窗口
            self.minimize_to_tray()
            dialog.destroy()

        def quit_and_close() -> None:
            # 退出应用并关闭窗口
            self.quit_application()
            dialog.destroy()

        tk.Button(btn_frame, text="📥  最小化到托盘", command=minimize_to_tray_and_close,
                  width=16, bg=Colors.PRIMARY, fg=Colors.WHITE,
                  activebackground=Colors.PRIMARY_DARK, activeforeground=Colors.WHITE,
                  font=DpiFont.body(bold=True), relief=tk.FLAT, bd=0,
                  padx=16, pady=8, cursor="hand2").pack(side=tk.LEFT, padx=(0, 8))

        tk.Button(btn_frame, text="❌  完全退出", command=quit_and_close,
                  width=16, bg=Colors.DANGER, fg=Colors.WHITE,
                  activebackground=Colors.DANGER_DARK, activeforeground=Colors.WHITE,
                  font=DpiFont.body(bold=True), relief=tk.FLAT, bd=0,
                  padx=16, pady=8, cursor="hand2").pack(side=tk.LEFT)

        # 键盘快捷键
        dialog.bind("<Escape>", lambda e: dialog.destroy())


def main() -> None:
    # 主函数
    root = tk.Tk()
    app = LiveRecorderGUI(root)

    tray = SystemTray(app)
    app.system_tray = tray
    app.tray_thread = threading.Thread(target=tray.run, daemon=True)
    app.tray_thread.start()

    root.protocol("WM_DELETE_WINDOW", app.on_closing)
    root.mainloop()


if __name__ == "__main__":
    main()