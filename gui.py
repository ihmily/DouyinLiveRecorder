# -*- encoding: utf-8 -*-
import os
import sys
import subprocess
import threading
import locale
import re
import tkinter as tk
from tkinter import scrolledtext, messagebox, ttk
from datetime import datetime

import pystray
from PIL import Image, ImageDraw


class SystemTray:
    """系统托盘管理器"""

    def __init__(self, gui_app):
        self.gui = gui_app
        self.icon = None
        self.running = False

    def create_icon_image(self):
        """动态创建托盘图标"""
        width = 64
        height = 64
        image = Image.new('RGB', (width, height), (70, 130, 180))
        dc = ImageDraw.Draw(image)

        padding = 4
        dc.ellipse(
            (padding, padding, width - padding, height - padding),
            fill=(135, 206, 250)
        )

        dc.ellipse(
            (width // 2 - 6, height // 2 - 6, width // 2 + 6, height // 2 + 6),
            fill=(220, 20, 60)
        )

        return image

    def on_show(self, icon=None):
        """显示主窗口"""
        if self.gui.root:
            self.gui.root.deiconify()
            self.gui.root.lift()

    def on_exit(self, icon=None):
        """退出程序"""
        self.gui.quit_application()

    def on_minimize(self, icon=None):
        """最小化到托盘"""
        if self.gui.root:
            self.gui.root.withdraw()

    def run(self):
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
        self.icon.on_activate = self.on_show
        self.icon.run()

    def stop(self):
        """停止托盘图标"""
        if self.icon and self.running:
            self.icon.stop()
            self.running = False

    def notify(self, message, title='直播录制器'):
        """显示托盘通知"""
        if self.icon:
            try:
                self.icon.notify(message, title)
            except Exception:
                pass


class AdvancedSettingsWindow:
    """高级设置窗口：编辑 config/config.ini"""

    def __init__(self, parent, config_file, log_callback=None):
        self.config_file = config_file
        self.log_callback = log_callback

        self.window = tk.Toplevel(parent)
        self.window.title("高级设置 - config.ini")
        self.window.geometry("700x500")
        self.window.transient(parent)
        self.window.grab_set()

        self._setup_ui()
        self._load_config()

    def _setup_ui(self):
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

    def _load_config(self):
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

    def save_config(self):
        """保存配置文件"""
        try:
            content = self.config_text.get(1.0, tk.END).rstrip('\n')
            if content and not content.endswith('\n'):
                content += '\n'

            with open(self.config_file, 'w', encoding='utf-8-sig') as f:
                f.write(content)

            messagebox.showinfo("成功", "配置文件已保存！")
            if self.log_callback:
                self.log_callback("高级设置配置已保存")
            self.window.destroy()
        except Exception as e:
            messagebox.showerror("错误", f"保存配置文件失败: {e}")


class LiveRecorderGUI:
    """直播录制 GUI 主类"""

    ANSI_ESCAPE_PATTERN = re.compile(r'\x1b\[[0-9;]*m')

    def __init__(self, root):
        self.root = root
        self.root.title("直播录制控制台")
        self.root.geometry("900x700")
        self.root.resizable(False, False)

        self.script_dir = os.path.dirname(os.path.abspath(__file__))
        self.url_config_file = os.path.join(self.script_dir, "config", "URL_config.ini")
        self.main_config_file = os.path.join(self.script_dir, "config", "config.ini")
        self.downloads_dir = os.path.join(self.script_dir, "downloads")

        self.process = None
        self.process_pid = None
        self.output_thread = None
        self.running = False

        self.system_tray = None
        self.tray_thread = None

        self._setup_style()
        self._setup_ui()
        self._load_config()

    def _setup_style(self):
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

    def _setup_ui(self):
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
        self.save_btn.pack()

        log_frame = ttk.LabelFrame(self.root, text="运行日志 (main.py 输出)", padding=5)
        log_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        self.log_text = scrolledtext.ScrolledText(log_frame, wrap=tk.WORD, font=("Consolas", 9),
                                                   bg="#1e1e1e", fg="#00ff00", height=10)
        self.log_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        self.status_var = tk.StringVar()
        self.status_var.set("就绪 | 循环检测: 120秒 | 格式: ts → mp4 | 托盘: 启用")
        status_bar = ttk.Label(self.root, textvariable=self.status_var, relief=tk.SUNKEN, padding=(5, 2))
        status_bar.pack(side=tk.BOTTOM, fill=tk.X)

    def _load_config(self):
        """加载 URL 配置文件"""
        config_dir = os.path.dirname(self.url_config_file)
        os.makedirs(config_dir, exist_ok=True)

        if not os.path.exists(self.url_config_file):
            with open(self.url_config_file, 'w', encoding='utf-8-sig') as f:
                f.write("")

        try:
            with open(self.url_config_file, 'r', encoding='utf-8-sig') as f:
                content = f.read()
            self.config_text.delete(1.0, tk.END)
            self.config_text.insert(1.0, content)
            self._log("配置文件已加载")
        except Exception as e:
            self._log(f"加载配置文件失败: {e}", "error")

    def save_config(self):
        """保存 URL 配置文件"""
        try:
            content = self.config_text.get(1.0, tk.END).rstrip('\n')
            if content and not content.endswith('\n'):
                content += '\n'

            with open(self.url_config_file, 'w', encoding='utf-8-sig') as f:
                f.write(content)
            self._log("URL 配置已保存")
            messagebox.showinfo("成功", "URL 配置已保存成功！")
        except Exception as e:
            self._log(f"保存配置文件失败: {e}", "error")
            messagebox.showerror("错误", f"保存配置文件失败: {e}")

    def open_downloads_folder(self):
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

    def open_advanced_settings(self):
        """打开高级设置窗口"""
        AdvancedSettingsWindow(self.root, self.main_config_file, self._log)

    def start_recording(self):
        """开始录制"""
        if self.process is not None:
            messagebox.showwarning("警告", "录制已在运行中！")
            return

        try:
            if sys.platform == 'win32':
                python_exe = os.path.join(self.script_dir, "venv", "Scripts", "python.exe")
                if not os.path.exists(python_exe):
                    python_exe = sys.executable
            else:
                python_exe = sys.executable

            main_py = os.path.join(self.script_dir, "main.py")

            self.process = subprocess.Popen(
                [python_exe, main_py],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding=locale.getpreferredencoding(False),
                errors='replace',
                bufsize=1,
                cwd=self.script_dir
            )

            self.process_pid = self.process.pid
            self.running = True
            self.start_btn.state(['disabled'])
            self.stop_btn.state(['!disabled'])

            self.status_label.config(text="🟢 运行中", fg="#2e7d32")
            self._update_status_bar()

            self.output_thread = threading.Thread(target=self._read_output, daemon=True)
            self.output_thread.start()

            self._log("=" * 50)
            self._log(f"[{self._get_timestamp()}] 录制进程已启动")
            self._log(f"Python: {python_exe}")
            self._log(f"工作目录: {self.script_dir}")
            self._log("=" * 50)

        except Exception as e:
            self._log(f"启动录制失败: {e}", "error")
            messagebox.showerror("错误", f"启动录制失败: {e}")

    def stop_recording(self):
        """停止录制"""
        if self.process is None:
            messagebox.showwarning("警告", "没有正在运行的录制进程！")
            return

        try:
            self._log("=" * 50)
            self._log(f"[{self._get_timestamp()}] 正在停止录制...")

            self.process.terminate()

            try:
                self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self._log("进程已强制终止")

            self.running = False
            self.process = None
            self.process_pid = None

            self.start_btn.state(['!disabled'])
            self.stop_btn.state(['disabled'])

            self.status_label.config(text="🔴 未运行", fg="#d32f2f")
            self._update_status_bar()

            self._log(f"[{self._get_timestamp()}] 录制进程已停止")
            self._log("=" * 50)

        except Exception as e:
            self._log(f"停止录制失败: {e}", "error")
            messagebox.showerror("错误", f"停止录制失败: {e}")

    def _read_output(self):
        """读取子进程输出"""
        while self.running and self.process:
            try:
                line = self.process.stdout.readline()
                if not line:
                    if self.process.poll() is not None:
                        self.root.after(0, self._process_ended)
                        break
                    continue

                clean_line = self.ANSI_ESCAPE_PATTERN.sub('', line.rstrip())
                self.root.after(0, lambda l=clean_line: self._log(l))

            except Exception as e:
                error_msg = str(e)
                self.root.after(0, lambda: self._log(f"读取输出错误: {error_msg}", "error"))
                break

    def _process_ended(self):
        """子进程结束回调"""
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

    def _log(self, message, level="info"):
        """添加日志"""
        timestamp = self._get_timestamp()

        if level == "error":
            display_text = f"[{timestamp}] [ERROR] {message}\n"
            tag = "error"
        else:
            display_text = f"[{timestamp}] {message}\n"
            tag = "normal"

        self.log_text.insert(tk.END, display_text, tag)
        self.log_text.see(tk.END)
        self.log_text.tag_config("error", foreground="#ff5555")

    def _get_timestamp(self):
        """获取当前时间戳"""
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def _update_status_bar(self):
        """更新状态栏"""
        tray_status = "启用" if self.system_tray and self.system_tray.running else "未启动"
        if self.process_pid is not None:
            status_text = f"状态：运行中 (PID: {self.process_pid}) | 循环检测: 120秒 | 格式: ts → mp4 | 托盘: {tray_status}"
        else:
            status_text = f"状态：未运行 | 循环检测: 120秒 | 格式: ts → mp4 | 托盘: {tray_status}"
        self.status_var.set(status_text)

    def minimize_to_tray(self):
        """最小化到托盘"""
        self.root.withdraw()
        if self.system_tray:
            self.system_tray.notify('程序已最小化到系统托盘，双击托盘图标可恢复窗口')

    def quit_application(self):
        """退出程序"""
        if self.process is not None:
            if messagebox.askokcancel("退出确认", "录制正在后台进行，确定要退出吗？"):
                self.stop_recording()
            else:
                return

        if self.system_tray:
            self.system_tray.stop()

        self.root.quit()
        self.root.destroy()
        sys.exit(0)

    def on_closing(self):
        """窗口关闭事件处理"""
        dialog = tk.Toplevel(self.root)
        dialog.title("关闭选项")
        dialog.geometry("300x120")
        dialog.resizable(False, False)
        dialog.transient(self.root)
        dialog.grab_set()

        dialog.update_idletasks()
        x = self.root.winfo_x() + (self.root.winfo_width() - dialog.winfo_width()) // 2
        y = self.root.winfo_y() + (self.root.winfo_height() - dialog.winfo_height()) // 2
        dialog.geometry(f"+{x}+{y}")

        tk.Label(dialog, text="请选择关闭方式：", font=("Arial", 11)).pack(pady=15)

        btn_frame = tk.Frame(dialog)
        btn_frame.pack(pady=10)

        def minimize_to_tray_and_close():
            self.minimize_to_tray()
            dialog.destroy()

        def quit_and_close():
            dialog.destroy()
            self.quit_application()

        tk.Button(btn_frame, text="📥 最小化到托盘", command=minimize_to_tray_and_close,
                  width=15, bg="#4682B4", fg="white", font=("Arial", 10)).grid(row=0, column=0, padx=5)

        tk.Button(btn_frame, text="❌ 彻底退出", command=quit_and_close,
                  width=15, bg="#d32f2f", fg="white", font=("Arial", 10)).grid(row=0, column=1, padx=5)


def main():
    """主函数"""
    root = tk.Tk()
    app = LiveRecorderGUI(root)

    app.system_tray = SystemTray(app)
    app.tray_thread = threading.Thread(target=app.system_tray.run, daemon=True)
    app.tray_thread.start()

    app._update_status_bar()
    root.protocol("WM_DELETE_WINDOW", app.on_closing)
    root.mainloop()


if __name__ == "__main__":
    main()
