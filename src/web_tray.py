# -*- encoding: utf-8 -*-
# Web 管理面板的控制台系统托盘支持。
#
# Windows 下将 web.py 的控制台窗口改为「最小化到系统托盘」，而非最小化到任务栏：
#
# - 把控制台窗口样式改为工具窗口（WS_EX_TOOLWINDOW 并去掉 WS_EX_APPWINDOW），
#   从而不生成任务栏按钮；最小化后仅在托盘可见，可直接从任务栏移除。
# - 禁用标题栏关闭按钮（通过系统菜单置灰 SC_CLOSE），避免误点关闭导致进程被终止。
# - 托盘图标提供「显示控制台」与「退出程序」：双击托盘图标恢复控制台窗口；
#   「退出程序」触发 uvicorn 优雅关闭（由调用方传入的 server 对象控制）。
#
# 注意：控制台窗口实际由 conhost.exe（独立进程）拥有，无法跨进程子类化其
# WndProc，因此**不能**拦截 WM_SYSCOMMAND 来改写最小化行为。本模块改用窗口
# 样式切换实现「不在任务栏显示」，配合常驻托盘图标达到「最小化到托盘」的效果。
#
from __future__ import annotations

import sys
import threading
from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    import uvicorn
    from PIL import Image
    from pystray import Icon

# 仅 Windows 下启用托盘（其他平台缺少 conhost 窗口与托盘 API）
ENABLED = sys.platform == "win32"

# Windows 常量
GWL_EXSTYLE = -20
WS_EX_APPWINDOW = 0x00040000
WS_EX_TOOLWINDOW = 0x00000080
SC_CLOSE = 0xF060
MF_BYCOMMAND = 0x0000
MF_GRAYED = 0x0001
SW_RESTORE = 9
SW_SHOW = 5
# SetWindowPos 标志
SWP_NOMOVE = 0x0002
SWP_NOSIZE = 0x0001
SWP_NOZORDER = 0x0004
SWP_FRAMECHANGED = 0x0020


class WebConsoleTray:
    # Web 控制台托盘管理器
    host: str
    port: int
    server: "uvicorn.Server | None"
    icon: "Icon | None"
    _thread: "threading.Thread | None"
    _hwnd: "int | None"

    def __init__(self, host: str, port: int, server: "uvicorn.Server | None" = None) -> None:
        # host/port 用于托盘提示文本；server 用于在「退出程序」时优雅关闭 uvicorn
        self.host = host
        self.port = port
        self.server = server
        self.icon = None
        self._thread = None
        self._hwnd = None

    def start(self) -> None:
        # 启动系统托盘（非阻塞，托盘图标运行在守护线程）
        if not ENABLED:
            return
        try:
            import pystray as _pystray  # 延迟导入：避免非 Windows / headless 环境顶层导入失败
        except Exception as e:  # pragma: no cover - 依赖缺失时优雅降级
            print(f"[web] 托盘不可用（缺少 pystray/Pillow）：{e}", flush=True)
            return

        # 改写控制台窗口样式：去任务栏按钮 + 禁用关闭按钮
        self._patch_console_window()

        menu = _pystray.Menu(
            _pystray.MenuItem("显示控制台", self._on_show, default=True),
            _pystray.MenuItem("退出程序", self._on_exit),
        )
        icon = _pystray.Icon(
            "DouyinLiveRecorderWeb",
            self._create_icon_image(),
            f"Web 管理面板 - http://{self.host}:{self.port}\n点击显示控制台，最小化将收起到托盘",
            menu,
        )
        self.icon = icon
        self._thread = threading.Thread(target=icon.run, daemon=True)
        self._thread.start()
        print("[web] 已启用系统托盘：控制台窗口不在任务栏显示，最小化后收起到托盘", flush=True)

    def stop(self) -> None:
        # 停止托盘图标（主线程在 uvicorn 关闭后调用）
        if self.icon is not None:
            try:
                self.icon.stop()
            except Exception:
                pass
            self.icon = None

    # ─── 控制台窗口样式改写（Windows） ──────────────────────

    def _patch_console_window(self) -> None:
        # 把控制台窗口改为工具窗口（无任务栏按钮），并禁用关闭按钮。
        # 失败则静默跳过，不影响 Web 服务运行。
        try:
            import ctypes
        except Exception:
            return

        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32

        hwnd = cast(int, kernel32.GetConsoleWindow())
        if not hwnd:
            return
        self._hwnd = hwnd

        try:
            exstyle = cast(int, user32.GetWindowLongW(hwnd, GWL_EXSTYLE))
            new_exstyle = (exstyle | WS_EX_TOOLWINDOW) & ~WS_EX_APPWINDOW
            user32.SetWindowLongW(hwnd, GWL_EXSTYLE, new_exstyle)
            # 触发 WM_STYLECHANGED，让任务栏重新评估是否创建按钮
            user32.SetWindowPos(
                hwnd,
                0,
                0,
                0,
                0,
                0,
                SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_FRAMECHANGED,
            )

            # 置灰系统菜单的关闭项，防止误点 X 关闭整个进程
            hmenu = cast(int, user32.GetSystemMenu(hwnd, False))
            if hmenu:
                user32.EnableMenuItem(hmenu, SC_CLOSE, MF_BYCOMMAND | MF_GRAYED)
        except Exception:
            pass

    # ─── 托盘图标 ──────────────────────────────────────────

    @staticmethod
    def _create_icon_image() -> "Image.Image":
        # 生成与 GUI 风格一致的托盘图标（蓝底白环红点）
        from PIL import Image, ImageDraw

        size = 64
        image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        dc = ImageDraw.Draw(image)
        margin = 2
        dc.rounded_rectangle(
            (margin, margin, size - margin, size - margin),
            radius=16,
            fill=(79, 109, 245, 255),
        )
        ring_margin = 10
        dc.ellipse(
            (ring_margin, ring_margin, size - ring_margin, size - ring_margin),
            outline=(255, 255, 255, 230),
            width=3,
        )
        dot = 9
        cx = size // 2
        cy = size // 2
        dc.ellipse((cx - dot, cy - dot, cx + dot, cy + dot), fill=(220, 38, 38, 255))
        return image

    # ─── 托盘菜单回调（运行在托盘线程，操作窗口需谨慎） ──────

    def _on_show(self, _icon: "object | None" = None, _item: "object | None" = None) -> None:
        # 恢复控制台窗口（允许从托盘线程调用 ShowWindow 恢复顶层窗口）
        hwnd = self._hwnd
        if not hwnd:
            return
        import ctypes

        user32 = ctypes.windll.user32
        user32.ShowWindow(hwnd, SW_RESTORE)
        try:
            user32.SetForegroundWindow(hwnd)
        except Exception:
            pass

    def _on_exit(self, _icon: "object | None" = None, _item: "object | None" = None) -> None:
        # 退出程序：触发 uvicorn 优雅关闭；无 server 时直接退出进程。
        if self.server is not None:
            self.server.should_exit = True
        else:
            import os

            os._exit(0)
        # 停止托盘图标（在本回调中调用是 pystray 的常规用法）
        if self.icon is not None:
            try:
                self.icon.stop()
            except Exception:
                pass
