# -*- encoding: utf-8 -*-
# Web 管理面板的控制台系统托盘支持（Qt / QSystemTrayIcon）。
#
# Windows 下将 web.py 的控制台窗口改为「最小化到系统托盘」，而非最小化到任务栏：
#
# - 把控制台窗口样式改为工具窗口（WS_EX_TOOLWINDOW 并去掉 WS_EX_APPWINDOW），
#   从而不生成任务栏按钮；最小化后仅在托盘可见，可直接从任务栏移除。
# - 禁用标题栏关闭按钮（通过系统菜单置灰 SC_CLOSE），避免误点关闭导致进程被终止。
# - 托盘图标菜单提供「显示控制台 / 隐藏控制台 / 打开 Web 界面 / 退出程序」；单击或双击
#   托盘图标恢复控制台窗口；「退出程序」触发 uvicorn 优雅关闭（由调用方传入的 server 控制）。
#
# 【为什么用 Qt 而非 pystray】pystray 的图标要额外依赖 Pillow，且必须跑在独立线程，
# 菜单回调因此落在托盘线程上，操作控制台窗口要跨线程调 Win32。Qt 自带 QSystemTrayIcon，
# 图标可用 QPainter 现画，回调全部落在跑事件循环的那一个线程里。
#
# 【线程模型】QApplication 只能建在主线程——本机实测在子线程执行 QApplication(sys.argv)
# 直接段错误退出（进程 exit code 139，Python 层捕获不到）。故 start() 返回 True 时调用方
# **必须**把主线程交给 run_event_loop()，uvicorn 改由调用方起的守护线程驱动（uvicorn 的
# capture_signals() 对非主线程直接跳过，信号由调用方自己接管，见 web.py::_install_sigint_shutdown）。
# 收益：菜单回调全部在主线程执行，ShowWindow 不再依赖跨线程时序假设。
#
# 控制台窗口实际由 conhost.exe（独立进程）拥有，无法跨进程子类化其 WndProc，因此**不能**
# 拦截 WM_SYSCOMMAND 改写最小化行为；本模块改用窗口样式切换 + 常驻托盘图标实现「最小化到托盘」。
#
# 【图标资源与打包后的路径处理】仓库不放二进制图标，托盘图标默认由 QPainter 现画
# （见 _create_icon），因此 PyInstaller 冻结后既不必读 sys._MEIPASS、也不必拼 exe 同级
# 目录——「图标文件没被收进包里」这个故障面根本不存在。若用户想换成自绘以外的图标，
# 把 favicon.ico / icon.ico / icon.png 放到冻结态的 exe 同级目录（或源码运行时的仓库根）
# 由 _load_icon_from_disk 按 _resource_roots() 的顺序探测。要把图标做成随包分发的资源时，
# 三处必须同改，否则现象是「开发环境有图标、打包后没有」：
#   ① build_exe.py 的 datas 登记（把文件收进 _internal）；
#   ② _ICON_FILE_NAMES（探测文件名）；
#   ③ _resource_roots()（冻结态的 _MEIPASS 与 exe 同级目录这两条根）。
# 内置默认图标在 assets/app.ico（16/24/32/48/64/128/256 七档），同时挂在 build_exe.py 三个
# EXE 的 icon= 与 datas 上。运行期优先级见 _icon_candidates：config.ini [Web] web_tray_icon
# （面板「导入图标」上传的那份）> 目录探测 > 自绘；解析逻辑统一在 src/ui_icons.py，
# 三个入口（GUI 托盘 / 本托盘 / GET /favicon.ico）共用，不各写一套。
#
from __future__ import annotations

import os
import pathlib
import sys
import webbrowser
from typing import TYPE_CHECKING, Callable, cast

import i18n

if TYPE_CHECKING:
    import ctypes

    import uvicorn
    from PySide6.QtCore import QTimer
    from PySide6.QtGui import QAction, QIcon
    from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

# 仅 Windows 下启用托盘（其他平台缺少 conhost 窗口与托盘 API）
ENABLED = sys.platform == "win32"

# Win32 API 常量（抄错即出现「托盘在但窗口没收起」的无异常视觉 bug，故由
# tests/test_web_tray.py::test_module_constants_match_win32_api 断言源码字面值）
GWL_EXSTYLE = -20
WS_EX_APPWINDOW = 0x00040000
WS_EX_TOOLWINDOW = 0x00000080
SC_CLOSE = 0xF060
MF_BYCOMMAND = 0x0000
MF_GRAYED = 0x0001
SW_HIDE = 0
SW_RESTORE = 9
# SW_SHOW 当前无调用点（显示走 SW_RESTORE），但不按「未使用」摘除：整组魔数由上面
# test_module_constants_match_win32_api 按「取值必须与 Win32 API 一致」钉住。
SW_SHOW = 5
# SetWindowPos 标志：只触发样式重评估，不动位置/尺寸/Z 序
SWP_NOMOVE = 0x0002
SWP_NOSIZE = 0x0001
SWP_NOZORDER = 0x0004
SWP_FRAMECHANGED = 0x0020

# 看门狗定时器周期（毫秒）：既决定「uvicorn 服务线程已结束」多快被看见，也保证
# exec() 阻塞期间主线程每隔这么久回到一次 Python 字节码——Qt 的 exec() 阻塞在 C 层，
# 期间 Python 的信号处理器不会被调用（Ctrl+C 只置位、无人接管），定时器回调是它唯一的落地点。
_WATCHDOG_INTERVAL_MS = 200

# 自绘托盘图标的边长（Qt 会按系统 DPI 再缩放，给足 64 以免高分屏发虚）
_ICON_SIZE = 64

# 外部图标文件的探测文件名（命中即用，见文件头「图标资源与打包后的路径处理」）
_ICON_FILE_NAMES = ("favicon.ico", "icon.ico", "icon.png")

# kernel32/user32 DLL 句柄缓存为模块级单例（与 web.py 的 WinDLL 惯例一致）：
# 不用 ctypes.windll——其函数指针缺省 restype=c_int，会把 64 位指针宽度的句柄
# （HWND/HMENU）截断为 32 位；句柄一旦截断，后续窗口操作会改写到错误地址。
_KERNEL32: "ctypes.CDLL | None" = None
_USER32: "ctypes.CDLL | None" = None


def _get_kernel32() -> "ctypes.CDLL | None":
    # 加载 kernel32 并声明 GetConsoleWindow 的返回类型，失败返回 None（调用方降级跳过）
    global _KERNEL32
    if _KERNEL32 is not None:
        return _KERNEL32
    if sys.platform != "win32":
        return None
    try:
        import ctypes

        dll = ctypes.WinDLL("kernel32", use_last_error=True)
        # HWND 是指针宽度：restype 必须显式声明为 c_void_p，否则被截断
        dll.GetConsoleWindow.restype = ctypes.c_void_p
        _KERNEL32 = dll
        return dll
    except Exception:
        return None


def _get_user32() -> "ctypes.CDLL | None":
    # 加载 user32 并声明本模块用到的全部函数签名，失败返回 None（调用方降级跳过）
    global _USER32
    if _USER32 is not None:
        return _USER32
    if sys.platform != "win32":
        return None
    try:
        import ctypes

        dll = ctypes.WinDLL("user32", use_last_error=True)
        dll.GetWindowLongW.argtypes = [ctypes.c_void_p, ctypes.c_int]
        dll.GetWindowLongW.restype = ctypes.c_long
        dll.SetWindowLongW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_long]
        dll.SetWindowLongW.restype = ctypes.c_long
        dll.SetWindowPos.argtypes = [
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_uint,
        ]
        dll.SetWindowPos.restype = ctypes.c_int
        dll.GetSystemMenu.argtypes = [ctypes.c_void_p, ctypes.c_int]
        dll.GetSystemMenu.restype = ctypes.c_void_p
        dll.EnableMenuItem.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_uint]
        dll.EnableMenuItem.restype = ctypes.c_int
        dll.ShowWindow.argtypes = [ctypes.c_void_p, ctypes.c_int]
        dll.ShowWindow.restype = ctypes.c_int
        dll.SetForegroundWindow.argtypes = [ctypes.c_void_p]
        dll.SetForegroundWindow.restype = ctypes.c_int
        _USER32 = dll
        return dll
    except Exception:
        return None


def _resource_roots() -> list[str]:
    # 外部图标的探测根目录，顺序即优先级：
    #   ① PyInstaller onefile 的解包目录 sys._MEIPASS（仅 sys.frozen 为真时存在）；
    #   ② 冻结态 exe 所在目录（onedir 模式下 _internal 与 exe 同级，手工放图标就在这层）；
    #   ③ 源码运行时的仓库根（本文件的上级目录）。
    # 不缓存、不写死绝对路径：_MEIPASS 每次构建都变，写死会让「换台机器打包」即失效。
    roots: list[str] = []
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if isinstance(meipass, str) and meipass:
            roots.append(meipass)
        roots.append(os.path.dirname(sys.executable))
    roots.append(str(pathlib.Path(__file__).resolve().parent.parent))
    return roots


class WebConsoleTray:
    # 托盘生命周期管理：start() 改写控制台窗口样式并挂上 Qt 托盘图标，
    # run_event_loop() 占用主线程跑事件循环，stop() 收起图标。
    host: str
    port: int
    server: "uvicorn.Server | None"
    app: "QApplication | None"
    icon: "QSystemTrayIcon | None"
    menu: "QMenu | None"
    show_action: "QAction | None"
    hide_action: "QAction | None"
    open_action: "QAction | None"
    exit_action: "QAction | None"
    _timer: "QTimer | None"
    _hwnd: "int | None"
    _owns_app: bool
    _forced_quit: bool

    def __init__(self, host: str, port: int, server: "uvicorn.Server | None" = None, icon_file: str = "") -> None:
        # host/port 用于托盘提示文本与「打开 Web 界面」；server 用于「退出程序」时优雅关闭 uvicorn。
        # icon_file 由 web.py 按 config.ini [Web] web_tray_icon 解析后传入（空 = 走内置 / 目录探测）：
        # 路径判定留在调用方，本类只认「已解析好的文件」，避免托盘层再读一次配置。
        self.host = host
        self.port = port
        self.server = server
        self._icon_file = icon_file
        self.app = None
        self.icon = None
        self.menu = None
        self.show_action = None
        self.hide_action = None
        self.open_action = None
        self.exit_action = None
        self._timer = None
        self._hwnd = None
        self._owns_app = False
        self._forced_quit = False

    # ─── 生命周期 ──────────────────────────────────────────

    def start(self) -> bool:
        # 挂上托盘图标。返回值是给调用方的**契约**：
        #   True  = 本模块已占用主线程，调用方必须随后调用 run_event_loop()，
        #          且不得再在主线程跑阻塞循环（uvicorn 要挪到自己的线程）；
        #   False = 已静默降级（非 Windows / 缺 PySide6 / 无系统托盘），调用方照旧在主线程跑 uvicorn。
        if not ENABLED:
            return False
        try:
            from PySide6.QtGui import QAction  # 延迟导入：避免 headless / 未装 Qt 时顶层导入失败
            from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon
        except Exception as e:  # pragma: no cover - 依赖缺失时优雅降级
            print(i18n.tr("[web] 托盘不可用（缺少 PySide6）：{e}", e=e), flush=True)
            return False

        # 2026-10-29 审查：try 只护 import 段时，QApplication/图标/菜单的构造期异常会原样穿透——
        # 调用方 web.py 对本方法无兜底（直接消费返回值），任何一处构造失败都会让面板启动整体崩掉。
        # 契约（见上方 212-215）要求「构造失败 → False 静默降级」，故构造段整体纳入同一收敛：
        # icon/menu 等引用都在 try 尾部落位到 self.*，中途失败不会留下半成品引用；已构造出的
        # QApplication 留着无害（没有事件循环即是惰性对象），无需回滚。
        try:
            # QApplication.instance() 在 PySide6 存根里返回 QCoreApplication：
            # 收仄成 QApplication 才能拿到 setQuitOnLastWindowClosed（且 self.app 的声明类型是
            # QApplication，不 cast 会让下面的赋值被 mypy 判为不兼容）。
            app = cast("QApplication | None", QApplication.instance())
            if app is None:
                # QApplication 只能在主线程构造（见文件头实测的段错误），本方法由 web.py 在主线程调用
                app = QApplication(sys.argv)
                self._owns_app = True
            # 本进程没有任何 QWidget：默认的「最后一个窗口关闭即退出」会在图标还没退出前就
            # 把事件循环带下去（表现为托盘点了没反应），托盘进程必须显式关掉这条。
            app.setQuitOnLastWindowClosed(False)
            self.app = app

            if not QSystemTrayIcon.isSystemTrayAvailable():
                # 无交互桌面的服务会话里 Qt 构造得出图标却挂不上去；此时必须降级——
                # 否则调用方交出了主线程，而用户既看不到图标也拿不到退出入口。
                print(i18n.tr("系统托盘不可用，已改为最小化到任务栏"), flush=True)
                return False

            # 改写控制台窗口样式：去任务栏按钮 + 禁用关闭按钮
            self._patch_console_window()

            icon = QSystemTrayIcon(self._build_icon(), app)
            # 托盘悬浮提示属界面文案：先查表后插值（f-string 直传不在提取器扫描面内）。
            icon.setToolTip(
                i18n.tr(
                    "Web 管理面板 - http://{url}\n点击显示控制台，最小化将收起到托盘", url=f"{self.host}:{self.port}"
                )
            )
            menu = QMenu()
            self.show_action = QAction(i18n.tr("显示控制台"), menu)
            self.hide_action = QAction(i18n.tr("隐藏控制台"), menu)
            self.open_action = QAction(i18n.tr("打开 Web 界面"), menu)
            self.exit_action = QAction(i18n.tr("退出程序"), menu)
            menu.addAction(self.show_action)
            menu.addAction(self.hide_action)
            menu.addAction(self.open_action)
            menu.addSeparator()
            menu.addAction(self.exit_action)
            # triggered 默认带 checked 形参，统一收仄成无参回调（与 src/gui_qt/tray.py 同口径），
            # 免得每个 handler 为兼容它加 *args 而让注解失真。
            self.show_action.triggered.connect(lambda _checked=False: self._on_show())
            self.hide_action.triggered.connect(lambda _checked=False: self._on_hide())
            self.open_action.triggered.connect(lambda _checked=False: self._on_open_browser())
            self.exit_action.triggered.connect(lambda _checked=False: self._on_exit())
            icon.setContextMenu(menu)
            # 左键单击 / 双击 = 显示控制台
            icon.activated.connect(self._on_activated)
            icon.show()
            self.icon = icon
            self.menu = menu
            # 事件循环退出（菜单「退出程序」/ Qt 自己接到的 Ctrl+C / 系统关机）统一在这里补收尾
            app.aboutToQuit.connect(self._on_about_to_quit)
        except Exception as e:
            print(
                i18n.tr(
                    "[web] 托盘初始化失败，已降级为无托盘模式: {type_name}: {e}",
                    type_name=type(e).__name__,
                    e=e,
                ),
                flush=True,
            )
            return False
        print("[web] 已启用系统托盘：控制台窗口不在任务栏显示，最小化后收起到托盘", flush=True)
        return True

    def run_event_loop(self, stop_when: "Callable[[], bool] | None" = None) -> None:
        # 阻塞运行 Qt 事件循环（占用调用线程，通常是主线程）；返回即表示应当收尾。
        # stop_when 为 True 时退出循环（web.py 传「uvicorn 服务线程已结束」）。
        # 未传 stop_when 时定时器照起：它是 Ctrl+C 在 exec() 期间唯一的落地点。
        if self.app is None:
            return
        from PySide6.QtCore import QTimer

        timer = QTimer(self.app)
        timer.setInterval(_WATCHDOG_INTERVAL_MS)
        timer.timeout.connect(lambda: self._poll(stop_when))
        timer.start()
        self._timer = timer
        try:
            self.app.exec()
        finally:
            timer.stop()
            self._timer = None

    def request_quit(self) -> None:
        # 强制放开事件循环（第二次 Ctrl+C 这类不再等服务线程的路径）。
        # 与菜单「退出程序」刻意不同：后者只置 server.should_exit，等看门狗看到服务线程
        # 结束再 quit，避免 HTTP 服务还在处理请求时循环先退出、web.py 直接进入 ffmpeg 清理。
        self._forced_quit = True
        if self.app is not None:
            self.app.quit()

    def stop(self) -> None:
        # 收起托盘图标（web.py 在清理段调用；可重复调用）。
        # 先隐藏再置 None：不留「图标还在、进程已走」的僵尸图标（冻结产物尤其明显）。
        if self.icon is not None:
            try:
                self.icon.hide()
            except Exception:
                pass
            self.icon = None
        self.menu = None
        if self.app is not None and self._owns_app:
            try:
                self.app.quit()
            except Exception:
                pass

    # ─── 控制台窗口样式改写（Windows） ──────────────────────

    def _patch_console_window(self) -> None:
        # 把控制台窗口改为工具窗口（无任务栏按钮），并禁用关闭按钮。
        # 失败则静默跳过，不影响 Web 服务运行；非 Windows 无 conhost 窗口，直接跳过。
        kernel32 = _get_kernel32()
        user32 = _get_user32()
        if kernel32 is None or user32 is None:
            return

        # GetConsoleWindow.restype 已声明为 c_void_p（指针宽度），返回 int 或 None
        hwnd = kernel32.GetConsoleWindow()
        if not hwnd:
            return
        self._hwnd = cast(int, hwnd)

        try:
            exstyle = cast(int, user32.GetWindowLongW(hwnd, GWL_EXSTYLE))
            new_exstyle = (exstyle | WS_EX_TOOLWINDOW) & ~WS_EX_APPWINDOW
            user32.SetWindowLongW(hwnd, GWL_EXSTYLE, new_exstyle)
            # 触发 WM_STYLECHANGED，让任务栏重新评估是否创建按钮
            user32.SetWindowPos(
                hwnd,
                None,
                0,
                0,
                0,
                0,
                SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_FRAMECHANGED,
            )

            # 置灰系统菜单的关闭项，防止误点 X 关闭整个进程
            hmenu = user32.GetSystemMenu(hwnd, False)
            if hmenu:
                user32.EnableMenuItem(hmenu, SC_CLOSE, MF_BYCOMMAND | MF_GRAYED)
        except Exception:
            pass

    # ─── 托盘图标 ──────────────────────────────────────────

    def _build_icon(self) -> "QIcon":
        # 外部图标文件优先，未命中回落到自绘（见文件头「图标资源与打包后的路径处理」）。
        # 两条路径都必须给出非空 QIcon：空图标在 Windows 托盘区是一块空白，
        # 用户既认不出这是本程序，也没法靠它唤出菜单。
        from_disk = self._load_icon_from_disk()
        if from_disk is not None:
            return from_disk
        return self._create_icon()

    def _icon_candidates(self) -> list[str]:
        # 图标探测顺序：① 导入图标（web.py 按 config.ini [Web] web_tray_icon 解析后传入）→
        # ② 目录探测（favicon.ico / icon.ico / icon.png）→ ③ 自绘（_create_icon）。
        # 导入图标必须压过约定文件名与自绘，否则用户「导入了却看不到」。
        candidates: list[str] = []
        if self._icon_file:
            candidates.append(self._icon_file)
        for root in _resource_roots():
            for name in _ICON_FILE_NAMES:
                candidates.append(str(pathlib.Path(root) / name))
        return candidates

    def _load_icon_from_disk(self) -> "QIcon | None":
        # 探测可选的外部图标；读不到或 Qt 解不出（损坏 / 不支持的格式）都返回 None 回落到
        # 自绘，不让一个坏文件把托盘变成空白。
        from PySide6.QtGui import QIcon

        try:
            for candidate in self._icon_candidates():
                if not pathlib.Path(candidate).is_file():
                    continue
                icon = QIcon(candidate)
                if not icon.isNull():
                    return icon
        except Exception:
            # 路径形态异常（含 NUL / 超长）时 is_file() 会抛而不是返回 False：
            # 托盘图标是本进程唯一的退出入口，绝不许它因一个坏路径把 start() 带崩。
            return None
        return None

    @staticmethod
    def _create_icon() -> "QIcon":
        # 自绘托盘图标（与 GUI 托盘同风格：蓝底 + 白环 + 红点录制指示）；现画而非读文件的理由见文件头。
        from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap

        pixmap = QPixmap(_ICON_SIZE, _ICON_SIZE)
        pixmap.fill(QColor(0, 0, 0, 0))
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        # 每次改画笔画刷都显式指定：QPainter 会沿用上一次的状态，漏设会让圆环与圆点互相
        # 染色（无异常，只有肉眼看得出）。
        painter.setPen(QPen(QColor(0, 0, 0, 0), 0))
        painter.setBrush(QColor(79, 109, 245, 255))
        painter.drawRoundedRect(2, 2, _ICON_SIZE - 4, _ICON_SIZE - 4, 16, 16)
        painter.setPen(QPen(QColor(255, 255, 255, 230), 3))
        painter.setBrush(QColor(0, 0, 0, 0))
        painter.drawEllipse(10, 10, _ICON_SIZE - 20, _ICON_SIZE - 20)
        painter.setPen(QPen(QColor(0, 0, 0, 0), 0))
        painter.setBrush(QColor(220, 38, 38, 255))
        dot = 18
        painter.drawEllipse((_ICON_SIZE - dot) // 2, (_ICON_SIZE - dot) // 2, dot, dot)
        painter.end()
        return QIcon(pixmap)

    # ─── 菜单回调（全部跑在事件循环所在线程） ─────────────

    def _on_activated(self, reason: "QSystemTrayIcon.ActivationReason") -> None:
        # 单击（Trigger）/ 双击（DoubleClick）都恢复控制台；右键（Context）交给上下文菜单，
        # 在这里一并处理会让右键也弹一次窗口。
        from PySide6.QtWidgets import QSystemTrayIcon

        if reason in (
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        ):
            self._on_show()

    def _on_show(self) -> None:
        self._apply_window(SW_RESTORE)

    def _on_hide(self) -> None:
        self._apply_window(SW_HIDE)

    def _apply_window(self, cmd: int) -> None:
        # 显示 / 隐藏控制台窗口（跑在事件循环线程，无「托盘线程调 ShowWindow」的跨线程假设）。
        hwnd = self._hwnd
        if not hwnd:
            return
        user32 = _get_user32()
        if user32 is None:
            return
        user32.ShowWindow(hwnd, cmd)
        # 隐藏不需要抢焦点；恢复才需要，且抢焦点失败不得逆掉上面的 ShowWindow
        if cmd == SW_HIDE:
            return
        try:
            user32.SetForegroundWindow(hwnd)
        except Exception:
            pass

    def _on_open_browser(self) -> None:
        # 打开 Web 面板：给「控制台已隐藏、又不想先恢复窗口」的场景一条直达路径。
        # 失败只提示不抛：托盘回调里冒泡出去的异常会一路穿到 Qt 事件循环。
        try:
            webbrowser.open(self._web_url())
        except Exception:
            print("[web] 打开浏览器失败，请手动访问上面给出的面板地址", flush=True)

    def _on_exit(self) -> None:
        # 退出程序：有 server 时交回 uvicorn 优雅关闭（ffmpeg / 连接池清理在 web.py 的
        # finally 段）；无 server 时（复用本类却没传服务对象）才走强制退出，否则进程会卡在
        # 「谁都不退出」的状态上。
        if self.server is not None:
            self.server.should_exit = True
        else:
            # 函数内 import os：与 tests/test_web_tray.py 的 sys.modules 替身口径一致
            import os

            os._exit(0)
        # 先收图标给即时反馈；事件循环由 run_event_loop 的看门狗在服务线程结束后退出，
        # 不能在这里 quit——服务还在跑就摘掉循环，会把 web.py 的清理段提前引到 HTTP 请求中间。
        if self.icon is not None:
            try:
                self.icon.hide()
            except Exception:
                pass

    def _on_about_to_quit(self) -> None:
        # 循环退出的统一收尾点：补置 uvicorn 的 should_exit。漏置的后果是 serve() 不返回，
        # web.py 的 finally 段（后处理线程池 / ffmpeg / 连接池）永远等不到。
        if self.server is not None:
            self.server.should_exit = True
        if self.icon is not None:
            try:
                self.icon.hide()
            except Exception:
                pass

    # ─── 内部 ──────────────────────────────────────────────

    def _poll(self, stop_when: "Callable[[], bool] | None") -> None:
        # 看门狗回调。stop_when 抛异常时绝不退出循环：托盘是本进程唯一的退出入口，
        # 因调用方一次性异常把它打死，用户就只剩任务管理器。
        if self._forced_quit or self.app is None:
            return
        if stop_when is None:
            return
        try:
            due = stop_when()
        except Exception:
            return
        if due:
            self.request_quit()

    def _web_url(self) -> str:
        # 面板地址。0.0.0.0 / :: 这类「监听全部网卡」的写法不能直接丢给浏览器，换成回环地址；
        # IPv6 字面量必须加方括号，否则端口会被当成地址的一部分。
        host = self.host
        if host in ("", "0.0.0.0", "::", "[::]"):
            host = "127.0.0.1"
        elif ":" in host and not host.startswith("["):
            host = f"[{host}]"
        return f"http://{host}:{self.port}"
