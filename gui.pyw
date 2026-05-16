# -*- encoding: utf-8 -*-
"""
直播录制器 GUI 界面
作者: Hmily
项目: DouyinLiveRecorder
功能: 提供图形化界面管理直播录制
"""
from __future__ import annotations

import os
import sys
import subprocess
import threading
import queue
import re
import configparser
import tkinter as tk
from tkinter import scrolledtext, messagebox, ttk
from datetime import datetime
from typing import Any

import pystray  # type: ignore[import-not-found]
from PIL import Image, ImageDraw


class SystemTray:
    """系统托盘管理器"""

    def __init__(self, gui_app: 'LiveRecorderGUI'):
        self.gui = gui_app  # 关联的主界面实例
        self.icon: pystray.Icon | None = None  # 托盘图标对象
        self.running = False  # 运行状态标志

    def create_icon_image(self) -> Image.Image:
        """创建64x64的托盘图标"""
        width = 64
        height = 64
        image = Image.new('RGB', (width, height), (70, 130, 180))  # 深蓝色背景
        dc = ImageDraw.Draw(image)

        padding = 4
        dc.ellipse(  # 绘制外层圆形
            (padding, padding, width - padding, height - padding),
            fill=(135, 206, 250)
        )

        dc.ellipse(  # 绘制中心红点
            (width // 2 - 6, height // 2 - 6, width // 2 + 6, height // 2 + 6),
            fill=(220, 20, 60)
        )

        return image

    def on_show(self, _icon: pystray.Icon | None = None) -> None:
        """显示主窗口"""
        if self.gui.root:
            self.gui.root.deiconify()
            self.gui.root.lift()

    def on_exit(self, _icon: pystray.Icon | None = None) -> None:
        """退出程序"""
        self.gui.quit_application()

    def on_minimize(self, _icon: pystray.Icon | None = None) -> None:
        """最小化到托盘"""
        if self.gui.root:
            self.gui.root.withdraw()

    def run(self) -> None:
        """启动托盘图标事件循环"""
        menu = pystray.Menu(
            pystray.MenuItem('显示主界面', self.on_show, default=True),
            pystray.MenuItem('最小化到托盘', self.on_minimize),
            pystray.MenuItem('退出程序', self.on_exit)
        )

        self.icon = pystray.Icon(
            'LiveRecorder',
            self.create_icon_image(),
            '直播录制器 - 点击显示窗口',
            menu
        )
        self.running = True
        self.icon.run()

    def stop(self) -> None:
        """停止托盘图标"""
        if self.icon and self.running:
            self.icon.stop()
            self.running = False

    def notify(self, message: str, title: str = '直播录制器') -> None:
        """显示托盘通知"""
        if self.icon:
            try:
                self.icon.notify(message, title)
            except Exception:
                pass


class AdvancedSettingsWindow:
    """高级设置窗口：编辑 config/config.ini"""

    def __init__(self, parent: tk.Toplevel | tk.Tk, config_file: str, log_callback: Any = None):
        self.config_file = config_file
        self.log_callback = log_callback

        self.window = tk.Toplevel(parent)
        self.window.title("高级设置 - config.ini")
        self.window.geometry("700x500")
        self.window.transient(parent)
        self.window.grab_set()

        self._setup_ui()
        self._load_config()

    def _setup_ui(self) -> None:
        """设置界面布局"""
        config_frame = ttk.LabelFrame(self.window, text="配置文件内容 (config/config.ini)", padding=5)
        config_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        self.config_text = scrolledtext.ScrolledText(
            config_frame, wrap=tk.WORD, font=("Consolas", 10)
        )
        self.config_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        btn_frame = ttk.Frame(self.window)
        btn_frame.pack(fill=tk.X, padx=10, pady=10)

        self.save_btn = ttk.Button(btn_frame, text="💾 保存配置", command=self.save_config, width=15)
        self.save_btn.pack(side=tk.LEFT, padx=5)

        self.cancel_btn = ttk.Button(btn_frame, text="取消", command=self.window.destroy, width=15)
        self.cancel_btn.pack(side=tk.LEFT, padx=5)

    def _load_config(self) -> None:
        """加载配置文件"""
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
        """保存配置文件"""
        try:
            _save_text_widget_to_file(self.config_text, self.config_file)
            messagebox.showinfo("成功", "配置文件已保存！")
            if self.log_callback:
                self.log_callback("高级设置配置已保存")
            self.window.destroy()
        except Exception as e:
            messagebox.showerror("错误", f"保存配置文件失败: {e}")


def _save_text_widget_to_file(text_widget: tk.Text | scrolledtext.ScrolledText, file_path: str) -> None:
    """从 Text 控件读取内容并写入文件（公共提取方法）"""
    content = text_widget.get(1.0, tk.END).rstrip('\n')
    if content and not content.endswith('\n'):
        content += '\n'
    with open(file_path, 'w', encoding='utf-8-sig') as f:
        f.write(content)


class LiveRecorderGUI:
    """直播录制 GUI 主类
    
    核心功能:
    - 管理主界面和用户交互
    - 启动/停止 main.py 录制进程
    - 显示运行日志和状态
    - 管理系统托盘
    """

    # 常量定义
    ANSI_ESCAPE_PATTERN = re.compile(r'\x1b\[[0-9;]*m')  # 用于移除ANSI颜色代码
    _MAX_LOG_LINES = 1000  # 日志最大行数
    _LOG_TRIM_TO = 800  # 裁剪后保留行数
    _LOG_FLUSH_INTERVAL = 200  # 日志刷新间隔(ms)
    _STATUS_REFRESH_INTERVAL = 10000  # 状态刷新间隔(ms)

    def __init__(self, root: tk.Tk):
        self.root = root  # 主窗口对象
        self.root.title("直播录制控制台")
        self.root.geometry("900x700")
        self.root.minsize(700, 500)

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

        self.output_thread: threading.Thread | None = None  # 读取子进程输出的线程

        self.system_tray: SystemTray | None = None
        self.tray_thread: threading.Thread | None = None

        # 配置文件监控
        self._last_url_config_mtime = 0.0
        self._refresh_job_id: str | None = None

        # 状态缓存（避免频繁读取配置）
        self._status_cache_mtime = 0.0
        self._status_cache: tuple[str, str] | None = None  # (check_interval, output_format)

        # 日志队列（用于线程间通信）
        self._log_queue: queue.Queue[list[tuple[str, str]] | None] = queue.Queue()
        self._log_flush_job_id: str | None = None
        self._log_queue_has_data = False

        self._setup_style()
        self._setup_ui()
        self._load_config()
        self._schedule_log_flush()
        self._schedule_status_refresh()

    # ─── 进程状态线程安全访问 ───────────────────────────────

    @property
    def process(self) -> subprocess.Popen[str] | None:
        with self._process_lock:
            return self._process

    @process.setter
    def process(self, value: subprocess.Popen[str] | None) -> None:
        with self._process_lock:
            self._process = value

    @property
    def process_pid(self) -> int | None:
        with self._process_lock:
            return self._process_pid

    @process_pid.setter
    def process_pid(self, value: int | None) -> None:
        with self._process_lock:
            self._process_pid = value

    @property
    def running(self) -> bool:
        with self._process_lock:
            return self._running

    @running.setter
    def running(self, value: bool) -> None:
        with self._process_lock:
            self._running = value

    # ─── UI 初始化 ─────────────────────────────────────────

    def _setup_style(self) -> None:
        """设置 ttk 样式"""
        self.style = ttk.Style()
        self.style.theme_use('clam')

        self.style.configure('Start.TButton', foreground='white', background='#4CAF50', font=('Arial', 10, 'bold'))
        self.style.map('Start.TButton', background=[('active', '#45a049')])
        self.style.configure('Stop.TButton', foreground='white', background='#f44336', font=('Arial', 10, 'bold'))
        self.style.map('Stop.TButton', background=[('active', '#da190b')])
        self.style.configure('Action.TButton', font=('Arial', 9))
        self.style.configure('Tray.TButton', foreground='white', background='#4682B4', font=('Arial', 9))
        self.style.map('Tray.TButton', background=[('active', '#5a9bd4')])
        self.style.configure('Exit.TButton', foreground='white', background='#d32f2f', font=('Arial', 9))
        self.style.map('Exit.TButton', background=[('active', '#b71c1c')])

    def _setup_ui(self) -> None:
        """设置主窗口界面"""
        top_frame = ttk.Frame(self.root, padding=10)
        top_frame.pack(fill=tk.X)

        left_btn_frame = ttk.Frame(top_frame)
        left_btn_frame.pack(side=tk.LEFT)

        self.start_btn = ttk.Button(left_btn_frame, text="🟢 开始录制", command=self.start_recording,
                                    style='Start.TButton', width=15)
        self.start_btn.grid(row=0, column=0, padx=5, pady=5)

        self.stop_btn = ttk.Button(left_btn_frame, text="🔴 停止录制", command=self.stop_recording,
                                   style='Stop.TButton', width=15, state=tk.DISABLED)
        self.stop_btn.grid(row=0, column=1, padx=5, pady=5)

        tray_btn_frame = ttk.LabelFrame(top_frame, text="托盘控制", padding=5)
        tray_btn_frame.pack(side=tk.LEFT, padx=10)

        ttk.Button(tray_btn_frame, text="📥 最小化到托盘", command=self.minimize_to_tray,
                   style='Tray.TButton', width=15).grid(row=0, column=0, padx=3, pady=3)
        ttk.Button(tray_btn_frame, text="❌ 彻底退出", command=self.quit_application,
                   style='Exit.TButton', width=15).grid(row=0, column=1, padx=3, pady=3)

        right_btn_frame = ttk.LabelFrame(top_frame, text="快捷操作", padding=5)
        right_btn_frame.pack(side=tk.RIGHT, padx=10)

        ttk.Button(right_btn_frame, text="📂 打开下载目录", command=self.open_downloads_folder,
                   style='Action.TButton', width=15).grid(row=0, column=0, padx=3, pady=3)
        ttk.Button(right_btn_frame, text="⚙️ 高级设置", command=self.open_advanced_settings,
                   style='Action.TButton', width=15).grid(row=0, column=1, padx=3, pady=3)

        status_frame = ttk.Frame(self.root)
        status_frame.pack(fill=tk.X, padx=10, pady=(0, 5))

        ttk.Label(status_frame, text="运行状态:").pack(side=tk.LEFT, padx=(0, 5))

        self.status_label = tk.Label(status_frame, text="🔴 未运行", fg="#d32f2f", font=("Arial", 10, "bold"))
        self.status_label.pack(side=tk.LEFT)

        config_frame = ttk.LabelFrame(self.root, text="URL 配置编辑区 (config/URL_config.ini)", padding=5)
        config_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        self.config_text = scrolledtext.ScrolledText(config_frame, wrap=tk.WORD, font=("Consolas", 10), height=10)
        self.config_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        hint_label = tk.Label(config_frame,
                              text="💡 格式说明: 每行一个直播链接，支持 # 开头的注释行 | 点击窗口关闭按钮（X）将最小化到系统托盘",
                              fg="gray", font=("Arial", 9))
        hint_label.pack(anchor=tk.W, padx=5)

        save_frame = ttk.Frame(self.root)
        save_frame.pack(fill=tk.X, padx=10, pady=5)

        self.save_btn = ttk.Button(save_frame, text="💾 保存 URL 配置", command=self.save_config, width=20)
        self.save_btn.pack(side=tk.LEFT, padx=5)

        self.reload_btn = ttk.Button(save_frame, text="📂 重新读取配置", command=self._load_config, width=20)
        self.reload_btn.pack(side=tk.LEFT, padx=5)

        log_frame = ttk.LabelFrame(self.root, text="运行日志 (main.py 输出)", padding=5)
        log_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        self.log_text = scrolledtext.ScrolledText(log_frame, wrap=tk.WORD, font=("Consolas", 9),
                                                   bg="#1e1e1e", fg="#00ff00", height=10, state=tk.DISABLED)
        self.log_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.log_text.tag_config("error", foreground="#ff5555")

        self.status_var = tk.StringVar()
        self._update_status_bar()
        status_bar = ttk.Label(self.root, textvariable=self.status_var, relief=tk.SUNKEN, padding=(5, 2))
        status_bar.pack(side=tk.BOTTOM, fill=tk.X)

    # ─── 配置读写 ──────────────────────────────────────────

    def _load_config(self) -> None:
        """加载 URL 配置文件"""
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
        """保存 URL 配置文件"""
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
        """获取动态状态信息，返回 (check_interval, output_format, tray_status)"""
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
        """返回托盘状态的字符串描述"""
        return "启用" if self.system_tray and self.system_tray.running else "未启动"

    # ─── 子进程管理 ────────────────────────────────────────

    def open_downloads_folder(self) -> None:
        """打开下载目录"""
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
        """打开高级设置窗口"""
        AdvancedSettingsWindow(self.root, self.main_config_file, self._log)

    def start_recording(self) -> None:
        """开始录制
        
        启动 main.py 子进程，创建独立的进程组，
        并启动线程读取子进程输出。
        """
        if self.process is not None:
            messagebox.showwarning("警告", "录制已在运行中！")
            return

        try:
            main_py = os.path.join(self.script_dir, "main.py")

            startupinfo = None
            env = os.environ.copy()
            env['PYTHONIOENCODING'] = 'utf-8'  # 确保输出编码正确
            if sys.platform == 'win32':
                # Windows 平台：隐藏控制台窗口
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startupinfo.wShowWindow = subprocess.SW_HIDE

            creation_flags = 0
            if sys.platform == 'win32':
                # 创建独立进程组，方便后续终止
                creation_flags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW

            # 启动子进程
            proc = subprocess.Popen(
                [sys.executable, main_py],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,  # 合并标准输出和错误
                text=True,
                encoding='utf-8',
                errors='replace',
                bufsize=1,  # 行缓冲
                cwd=self.script_dir,
                env=env,
                startupinfo=startupinfo,
                creationflags=creation_flags
            )

            # 更新界面状态
            self.process = proc
            self.process_pid = proc.pid
            self.running = True
            self.start_btn.state(['disabled'])
            self.stop_btn.state(['!disabled'])

            self.status_label.config(text="🟢 运行中", fg="#2e7d32")
            self._update_status_bar()

            # 启动输出读取线程
            self.output_thread = threading.Thread(target=self._read_output, daemon=True)
            self.output_thread.start()

            # 记录启动信息
            self._log("=" * 50)
            self._log(f"[{self._get_timestamp()}] 录制进程已启动 (PID: {proc.pid})")
            self._log(f"Python: {sys.executable}")
            self._log(f"工作目录: {self.script_dir}")
            self._log("=" * 50)

        except Exception as e:
            self._log(f"启动录制失败: {e}", "error")
            messagebox.showerror("错误", f"启动录制失败: {e}")

    def stop_recording(self) -> None:
        """停止录制 —— 发送终止信号后，在后台线程等待进程退出"""
        proc = self.process
        pid = self.process_pid

        if proc is None:
            messagebox.showwarning("警告", "没有正在运行的录制进程！")
            return

        self._log("=" * 50)
        self._log(f"[{self._get_timestamp()}] 正在停止录制...")

        if sys.platform == 'win32':
            self._log("正在发送终止信号...")
            proc.terminate()
        else:
            self._log("正在发送 SIGINT 信号...")
            import signal
            os.kill(proc.pid, signal.SIGINT)

        def _wait_and_update_ui() -> None:
            terminated = False
            try:
                proc.wait(timeout=3)
                terminated = True
                self._log("进程已优雅退出")
            except subprocess.TimeoutExpired:
                self._log("进程未能及时退出，尝试强制终止...")

            if not terminated and proc.poll() is None:
                try:
                    self._log("正在强制终止进程...")
                    proc.kill()
                    proc.wait(timeout=2)
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
        """进程终止后的 UI 更新回调（在 UI 线程中执行）"""
        self.start_btn.state(['!disabled'])
        self.stop_btn.state(['disabled'])
        self.status_label.config(text="🔴 未运行", fg="#d32f2f")
        self._update_status_bar()
        self._log(f"[{self._get_timestamp()}] 录制进程已停止")
        self._log("=" * 50)
        self._flush_log_queue()

    def _read_output(self) -> None:
        """读取子进程输出 — 批量写入队列，减少 UI 线程调度次数
        
        优化说明:
        - 使用批处理：每10行输出为一个批次
        - 移除 ANSI 颜色代码，保持界面显示
        - 通过队列实现线程安全通信
        """
        batch: list[tuple[str, str]] = []
        batch_size = 10

        def flush_batch() -> None:
            """内部函数：将批次写入队列"""
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
                self._log_queue.put(None)  # None表示进程结束
                self._log_queue_has_data = True
                break

            try:
                line = proc.stdout.readline()
                if not line:
                    if proc.poll() is not None:  # 检测进程是否结束
                        flush_batch()
                        self.running = False
                        self._log_queue.put(None)
                        self._log_queue_has_data = True
                        break
                    continue

                clean_line = self.ANSI_ESCAPE_PATTERN.sub('', line.rstrip())  # 移除ANSI颜色代码
                batch.append((clean_line, "info"))

                if len(batch) >= batch_size:
                    flush_batch()

            except (ValueError, OSError) as e:
                # I/O 已关闭或管道已断开
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
        """定时从队列批量刷新日志到 UI（按需调度：有数据才继续，无数据则等待下次 _log 触发）
        
        优化说明:
        - 批量处理队列中的消息，减少UI重绘
        - 按需调度定时器，空闲时不消耗资源
        - 自动裁剪日志，避免内存泄漏
        """
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
                else:
                    display_text = f"[{timestamp}] {message}\n"
                    tag = "normal"

                self.log_text.insert(tk.END, display_text, tag)

            # 使用实际 Text 控件行数判断是否需要 trim（防止内存溢出）
            total_lines = int(self.log_text.index('end-1c').split('.')[0])
            if total_lines > self._MAX_LOG_LINES:
                trim_count = total_lines - self._LOG_TRIM_TO
                self.log_text.delete('1.0', f'{trim_count + 1}.0')

            self.log_text.see(tk.END)  # 自动滚动到底部
            self.log_text.config(state=tk.DISABLED)
            self._log_queue_has_data = False

        if process_ended:
            self._process_ended()

        # 按需调度：只有仍有未处理数据时才继续调度，否则等待 _log() 重新激活
        if self._log_queue_has_data or not self._log_queue.empty():
            self._log_flush_job_id = self.root.after(self._LOG_FLUSH_INTERVAL, self._schedule_log_flush)
        else:
            self._log_flush_job_id = None

    def _process_ended(self) -> None:
        """子进程结束回调（仅在 UI 线程中调用）"""
        self.running = False
        self.process = None
        self.process_pid = None
        self.start_btn.state(['!disabled'])
        self.stop_btn.state(['disabled'])

        self.status_label.config(text="🔴 未运行", fg="#d32f2f")
        self._update_status_bar()

        self._log("=" * 50)
        self._log(f"[{self._get_timestamp()}] 录制进程已结束")
        self._log("=" * 50)

    def _log(self, message: str, level: str = "info") -> None:
        """添加日志到队列（线程安全），按需激活 _schedule_log_flush"""
        self._log_queue.put([(message, level)])
        self._log_queue_has_data = True
        if self._log_flush_job_id is None:
            self._log_flush_job_id = self.root.after(self._LOG_FLUSH_INTERVAL, self._schedule_log_flush)

    def _flush_log_queue(self) -> None:
        """立即刷新日志队列到 UI（仅在 UI 线程中调用）"""
        if self._log_flush_job_id:
            self.root.after_cancel(self._log_flush_job_id)
            self._log_flush_job_id = None
        self._schedule_log_flush()
        if self._log_queue_has_data or not self._log_queue.empty():
            self._log_flush_job_id = self.root.after(self._LOG_FLUSH_INTERVAL, self._schedule_log_flush)

    # ─── 时间与状态栏 ──────────────────────────────────────

    @staticmethod
    def _get_timestamp() -> str:
        """获取当前时间戳"""
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def _update_status_bar(self) -> None:
        """更新状态栏（动态读取配置）"""
        check_interval, output_format, tray_status = self._get_dynamic_status_info()

        pid = self.process_pid
        if pid is not None:
            status_text = f"状态：运行中 (PID: {pid}) | 循环检测: {check_interval} | 格式: {output_format} | 托盘: {tray_status}"
        else:
            status_text = f"状态：未运行 | 循环检测: {check_interval} | 格式: {output_format} | 托盘: {tray_status}"

        self.status_var.set(status_text)

    def _schedule_status_refresh(self) -> None:
        """每10秒自动刷新状态栏和监控 URL 配置文件变化"""
        self._update_status_bar()
        self._watch_url_config()
        self._refresh_job_id = self.root.after(self._STATUS_REFRESH_INTERVAL, self._schedule_status_refresh)

    def _watch_url_config(self) -> None:
        """监控 URL_config.ini 文件变化，外部修改时自动重新加载"""
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
        """最小化到托盘"""
        self.root.withdraw()
        if self.system_tray:
            self.system_tray.notify('程序已最小化到系统托盘，双击托盘图标可恢复窗口')

    def quit_application(self) -> None:
        """退出程序"""
        if self.process is not None:
            if messagebox.askokcancel("退出确认", "录制正在后台进行，确定要退出吗？"):
                self.stop_recording()
            else:
                return

        self._log("正在后台清理可能残留的 ffmpeg 进程...")
        threading.Thread(target=self._cleanup_zombie_ffmpeg, daemon=True).start()

        if self._log_flush_job_id:
            self.root.after_cancel(self._log_flush_job_id)
            self._log_flush_job_id = None

        if self._refresh_job_id:
            self.root.after_cancel(self._refresh_job_id)
            self._refresh_job_id = None

        if self.system_tray:
            self.system_tray.stop()

        self.root.quit()
        self.root.destroy()

    def _cleanup_zombie_ffmpeg(self) -> None:
        """清理当前 Python 进程的子 ffmpeg 进程（仅清理自己进程树下的，避免误杀系统 ffmpeg）
        
        安全设计:
        - 只清理父进程为当前进程的 ffmpeg
        - 避免误杀其他程序正在使用的 ffmpeg
        """
        current_pid = os.getpid()
        found = False

        try:
            if sys.platform == 'win32':
                # Windows 平台：使用 taskkill 命令按父进程ID筛选
                try:
                    subprocess.run(
                        ['taskkill', '/F', '/FI', f'IMAGENAME eq ffmpeg.exe', '/FI', f'PARENTPID eq {current_pid}'],
                        capture_output=True,
                        text=True,
                        timeout=3
                    )
                    found = True
                    self._log("已通过 taskkill 清理本进程树的 ffmpeg 进程")
                except Exception as e:
                    self._log(f"taskkill 执行失败: {e}")
            else:
                # Linux/Mac 平台：使用 pkill 命令
                try:
                    subprocess.run(
                        ['pkill', '-P', str(current_pid), '-x', 'ffmpeg'],
                        capture_output=True,
                        text=True,
                        timeout=3
                    )
                    found = True
                    self._log("已通过 pkill 清理本进程树的 ffmpeg 进程")
                except Exception as e:
                    self._log(f"pkill 执行失败: {e}")

            if not found:
                self._log("未发现需要清理的 ffmpeg 进程")
        except Exception as e:
            self._log(f"清理 ffmpeg 进程时出错: {e}")

    def on_closing(self) -> None:
        """窗口关闭事件处理
        
        显示关闭选项对话框：
        - 最小化到托盘
        - 彻底退出程序
        """
        dialog = tk.Toplevel(self.root)
        dialog.title("关闭选项")
        dialog.geometry("300x120")
        dialog.resizable(False, False)
        dialog.transient(self.root)
        dialog.grab_set()

        # 居中显示对话框
        dialog.update_idletasks()
        x = self.root.winfo_x() + (self.root.winfo_width() - dialog.winfo_width()) // 2
        y = self.root.winfo_y() + (self.root.winfo_height() - dialog.winfo_height()) // 2
        dialog.geometry(f"+{x}+{y}")

        tk.Label(dialog, text="请选择关闭方式：", font=("Arial", 11)).pack(pady=15)

        btn_frame = tk.Frame(dialog)
        btn_frame.pack(pady=10)

        def minimize_to_tray_and_close() -> None:
            self.minimize_to_tray()
            dialog.destroy()

        def quit_and_close() -> None:
            self.quit_application()
            dialog.destroy()

        tk.Button(btn_frame, text="📥 最小化到托盘", command=minimize_to_tray_and_close,
                  width=15, bg="#4682B4", fg="white", font=("Arial", 10)).grid(row=0, column=0, padx=5)

        tk.Button(btn_frame, text="❌ 彻底退出", command=quit_and_close,
                  width=15, bg="#d32f2f", fg="white", font=("Arial", 10)).grid(row=0, column=1, padx=5)


def main() -> None:
    """主函数
    
    程序执行流程:
    1. 创建主窗口
    2. 初始化 GUI 应用
    3. 启动系统托盘线程
    4. 绑定窗口关闭事件
    5. 进入主事件循环
    """
    root = tk.Tk()
    app = LiveRecorderGUI(root)

    app.system_tray = SystemTray(app)
    app.tray_thread = threading.Thread(target=app.system_tray.run, daemon=True)
    app.tray_thread.start()

    root.protocol("WM_DELETE_WINDOW", app.on_closing)
    root.mainloop()


if __name__ == "__main__":
    main()