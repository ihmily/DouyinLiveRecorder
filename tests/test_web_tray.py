# tests/test_web_tray.py - src/web_tray.py 的行为锁。
#
# 该模块只在「Windows + 控制台宿主」这一组合下才被启用，测试环境里既没有真实 conhost 窗口、
# 也不允许真的往用户桌面挂一个托盘图标。补测的重点不是行数，而是四条**不能反向漂移**的边界：
#   1) 任何失败都必须静默降级（缺 PySide6 / DLL 加载失败 / 窗口调用抛异常），
#      绝不能让 Web 面板起不来——托盘只是锦上添花；
#   2) 不得真的改写宿主控制台样式：_patch_console_window 必须可在 DLL 缺失时短路；
#   3) 「退出程序」在无 uvicorn server 时走 os._exit(0)，这条隐蔽的强制退出路径
#      必须被显式锁住（否则将来有人删掉 else 分支，进程会卡在非零退出码上）；
#   4) start() 的返回值是「主线程归谁」的契约（True = 交给 Qt 事件循环）。返回 True 却
#      没把主线程交出去 = 托盘永远是死的；返回 False 却交出去 = 面板彻底失去退出入口。
#
# Mock 口径（由 pystray 迁 Qt 后重写）：PySide6 三个子模块用 sys.modules 桩替换
# （避免真建 QApplication / 真挂图标；offscreen 平台上 isSystemTrayAvailable 恒 False，
# 真 Qt 反而测不到正常路径）。Win32 DLL 句柄用 SimpleNamespace 桩替换 _get_kernel32/
# _get_user32 的返回值。生产侧「函数内 import」的 stdlib（ctypes / os）一律经
# _imported_module_shim 换 sys.modules 条目，不改模块本体。
#
# 分支地图：
#   DLL 句柄缓存的三个入口：已缓存直返 / 非 win32 早返回 / WinDLL 加载失败返 None。
#     真加载那条另断言 restype——HWND/HMENU 是指针宽度，缺省 c_int 会把 64 位句柄
#     截断成 32 位，后续窗口操作改写到错误地址（不报错，只是“托盘在但窗口没收起”）。
#   _patch_console_window：kernel32/user32 缺失→短路；hwnd=0→短路；正常→置 TOOLWINDOW
#     清 APPWINDOW 并置灰 SC_CLOSE；系统菜单拿不到→跳过置灰；窗口 API 抛异常→吞掉。
#   start：ENABLED=False→什么也不做；缺 PySide6→打一行提示后返回；系统托盘不可用→同样降级；
#     正常→建 QMenu（四项 + 一个分隔符）+ 挂图标 + 返回 True；已有 QApplication 实例时复用。
#   run_event_loop / _poll：定时器按 _WATCHDOG_INTERVAL_MS 起；stop_when 为真→quit；
#     stop_when 抛异常→绝不 quit（托盘是唯一退出入口）；request_quit 后 _poll 变成空转。
#   菜单回调：_on_show 先 ShowWindow 后 SetForegroundWindow，后者失败不得逆前者；
#     _on_hide 只 ShowWindow 不抢焦点；_on_activated 只认 Trigger/DoubleClick；
#     _on_open_browser 走 _web_url()；_on_exit 有 server 时只置 should_exit，无 server 时才
#     走 os._exit(0)；_on_about_to_quit 是循环退出的统一收尾点。
# 一个写用例时踩到的坑，记下来避免重踏：_on_exit 的 else 分支会真杀进程，任何
# 「不传 server」的用例都会把整个 pytest 会话提前终止（表现为“没报错但没汇总”）。

import ctypes
import os
import sys
import types
from pathlib import Path
from typing import Any, cast

import pytest

import src.web_tray as web_tray

# ─── Qt 替身 ──────────────────────────────────────────────
# 为什么整套替身而不是真 Qt：真 QApplication 是进程级单例、建了就拆不掉，
# 而 QSystemTrayIcon.show() 会真往用户托盘区挂图标。


class _Signal:
    # 最小信号：Qt 的 connect/emit 语义够用即可（本模块只用 connect）
    def __init__(self) -> None:
        self.slots: list[Any] = []

    def connect(self, slot: Any) -> None:
        self.slots.append(slot)

    def emit(self, *args: Any) -> None:
        for slot in list(self.slots):
            slot(*args)


class _FakeQApplication:
    _current: "_FakeQApplication | None" = None

    def __init__(self, argv: Any = None) -> None:
        self.argv = argv
        self.quit_calls = 0
        self.exec_calls = 0
        self.quit_on_last_window_closed: bool | None = None
        self.aboutToQuit = _Signal()
        _FakeQApplication._current = self

    @staticmethod
    def instance() -> "_FakeQApplication | None":
        return _FakeQApplication._current

    def setQuitOnLastWindowClosed(self, flag: bool) -> None:
        self.quit_on_last_window_closed = flag

    def quit(self) -> None:
        self.quit_calls += 1

    def exec(self) -> int:
        # 方法名与 Qt 原生 exec 对齐；替身不阻塞，返回即代表「事件循环已退出」
        self.exec_calls += 1
        return 0


class _FakeQAction:
    def __init__(self, text: str, parent: Any = None) -> None:
        self.text = text
        self.parent = parent
        self.triggered = _Signal()


class _FakeQMenu:
    def __init__(self, parent: Any = None) -> None:
        self.parent = parent
        self.actions: list[_FakeQAction] = []
        self.separators = 0

    def addAction(self, action: _FakeQAction) -> _FakeQAction:
        self.actions.append(action)
        return action

    def addSeparator(self) -> None:
        self.separators += 1


class _FakeQSystemTrayIcon:
    class ActivationReason:
        # 取值随便是几：生产侧只做相等比较，测试用它们分辨「左键 / 右键」两条分支。
        # 标 Any 是因为真 Qt 的 ActivationReason 是枚举类，而这里的替身只给 int。
        Trigger: Any = 1
        DoubleClick: Any = 2
        MiddleClick: Any = 3
        Context: Any = 4

    available = True

    def __init__(self, icon: Any = None, parent: Any = None) -> None:
        self.icon = icon
        self.parent = parent
        self.shown = 0
        self.hidden = 0
        self.tooltip: str | None = None
        self.context_menu: Any = None
        self.activated = _Signal()

    @staticmethod
    def isSystemTrayAvailable() -> bool:
        return _FakeQSystemTrayIcon.available

    def setToolTip(self, text: str) -> None:
        self.tooltip = text

    def setContextMenu(self, menu: Any) -> None:
        self.context_menu = menu

    def show(self) -> None:
        self.shown += 1

    def hide(self) -> None:
        self.hidden += 1


class _FakeQTimer:
    def __init__(self, parent: Any = None) -> None:
        self.parent = parent
        self.interval: int | None = None
        self.started = 0
        self.stopped = 0
        self.timeout = _Signal()

    def setInterval(self, ms: int) -> None:
        self.interval = ms

    def start(self) -> None:
        self.started += 1

    def stop(self) -> None:
        self.stopped += 1

    def fire(self) -> None:
        # 手动触发一次超时（替身没有事件循环，定时器不会自己响）
        self.timeout.emit()


class _FakeQColor:
    def __init__(self, *args: Any) -> None:
        self.args = args


class _FakeQPen:
    def __init__(self, *args: Any) -> None:
        self.args = args


class _FakeQPixmap:
    def __init__(self, width: int, height: int) -> None:
        self.size = (width, height)
        self.fills: list[Any] = []

    def fill(self, color: Any) -> None:
        self.fills.append(color)


class _FakeQPainter:
    class RenderHint:
        # 生产侧只取这一个枚举值；替身给个占位即可（比较的是「setRenderHint 被调用」）
        Antialiasing = 1

    instances: list["_FakeQPainter"] = []

    def __init__(self, pixmap: Any) -> None:
        self.pixmap = pixmap
        self.ops: list[tuple[str, Any]] = []
        _FakeQPainter.instances.append(self)

    def setRenderHint(self, hint: Any) -> None:
        self.ops.append(("hint", hint))

    def setPen(self, pen: Any) -> None:
        self.ops.append(("pen", pen))

    def setBrush(self, brush: Any) -> None:
        self.ops.append(("brush", brush))

    def drawRoundedRect(self, *args: Any) -> None:
        self.ops.append(("rounded", args))

    def drawEllipse(self, *args: Any) -> None:
        self.ops.append(("ellipse", args))

    def end(self) -> None:
        self.ops.append(("end", None))


class _FakeQIcon:
    def __init__(self, *args: Any) -> None:
        self.args = args
        self.null = False

    def isNull(self) -> bool:
        return self.null


def _fake_qt_modules() -> dict[str, types.ModuleType]:
    # 三个子模块 + 父包：生产侧是函数内 `from PySide6.QtXxx import ...`，
    # 命中 sys.modules 即绑定这里的替身（父包也要在，否则 import 机制会去找真包）。
    widgets = types.ModuleType("PySide6.QtWidgets")
    widgets.QApplication = _FakeQApplication  # type: ignore[attr-defined]
    widgets.QMenu = _FakeQMenu  # type: ignore[attr-defined]
    widgets.QSystemTrayIcon = _FakeQSystemTrayIcon  # type: ignore[attr-defined]
    gui = types.ModuleType("PySide6.QtGui")
    gui.QAction = _FakeQAction  # type: ignore[attr-defined]
    gui.QColor = _FakeQColor  # type: ignore[attr-defined]
    gui.QIcon = _FakeQIcon  # type: ignore[attr-defined]
    gui.QPainter = _FakeQPainter  # type: ignore[attr-defined]
    gui.QPen = _FakeQPen  # type: ignore[attr-defined]
    gui.QPixmap = _FakeQPixmap  # type: ignore[attr-defined]
    core = types.ModuleType("PySide6.QtCore")
    core.QTimer = _FakeQTimer  # type: ignore[attr-defined]
    parent = types.ModuleType("PySide6")
    parent.QtWidgets = widgets  # type: ignore[attr-defined]
    parent.QtGui = gui  # type: ignore[attr-defined]
    parent.QtCore = core  # type: ignore[attr-defined]
    return {
        "PySide6": parent,
        "PySide6.QtWidgets": widgets,
        "PySide6.QtGui": gui,
        "PySide6.QtCore": core,
    }


@pytest.fixture
def fake_qt(monkeypatch: pytest.MonkeyPatch) -> dict[str, types.ModuleType]:
    modules = _fake_qt_modules()
    for name, module in modules.items():
        monkeypatch.setitem(sys.modules, name, module)
    # 替身是类级状态（QApplication 单例、图标可用性、painter 记录）：跨用例必须清干净
    _FakeQApplication._current = None
    _FakeQSystemTrayIcon.available = True
    _FakeQPainter.instances = []
    monkeypatch.setattr(web_tray, "ENABLED", True)
    return modules


def _imported_module_shim(name: str, **overrides: Any) -> types.SimpleNamespace:
    # 本模块要替的两个 stdlib 符号都处在**函数内 import** 的位置
    # （src/web_tray.py 的 _get_kernel32/_get_user32 里 `import ctypes`、_on_exit 里 `import os`），
    # 所以 web_tray 命名空间内根本没有可替换的模块引用：仓库常规的
    # `monkeypatch.setattr(<被测模块>, "os", shim)` 在这里打不上，写成 raising=False 更糟——
    # 会落一个永不被读的模块属性，用例静默假绿。
    # 唯一真实接线点是 sys.modules 条目：函数内 `import x` 命中缓存即绑定该对象。
    # 浅拷贝保留真模块的全部符号（ctypes 的 c_void_p/c_long/c_int、os 的其余函数），
    # 只覆盖需要的那一个，于是 stdlib 模块本体在整个用例窗口内逐字不变。
    shim = types.SimpleNamespace(**vars(sys.modules[name]))
    for attr, value in overrides.items():
        setattr(shim, attr, value)
    return shim


@pytest.fixture
def reset_dll_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    # 模块级 DLL 句柄是进程级单例，跨用例残留会让「None → 加载」分支永远走不到。
    monkeypatch.setattr(web_tray, "_KERNEL32", None)
    monkeypatch.setattr(web_tray, "_USER32", None)


@pytest.fixture
def no_win32_dlls(monkeypatch: pytest.MonkeyPatch) -> None:
    # start() 会顺手改写控制台窗口样式；测试里绝不能碰到真窗口
    monkeypatch.setattr(web_tray, "_get_kernel32", lambda: None)
    monkeypatch.setattr(web_tray, "_get_user32", lambda: None)


class TestDllAccessors:
    def test_kernel32_returns_cached_handle_without_reloading(self, monkeypatch: pytest.MonkeyPatch) -> None:
        sentinel = object()
        monkeypatch.setattr(web_tray, "_KERNEL32", sentinel)
        assert web_tray._get_kernel32() is cast(Any, sentinel)

    def test_user32_returns_cached_handle_without_reloading(self, monkeypatch: pytest.MonkeyPatch) -> None:
        sentinel = object()
        monkeypatch.setattr(web_tray, "_USER32", sentinel)
        assert web_tray._get_user32() is cast(Any, sentinel)

    @pytest.mark.skipif(sys.platform != "win32", reason="Win32 DLL 仅在 Windows 可用")
    def test_real_handles_declare_pointer_width_signatures(self, reset_dll_cache: None) -> None:
        # HWND/HMENU 是指针宽度：restype 必须是 c_void_p，否则 64 位句柄被截断成 32 位，
        # 后续窗口操作会改写到错误地址。这条断言锁住声明本身，而不是「函数能返回东西」。
        kernel32 = web_tray._get_kernel32()
        assert kernel32 is not None
        assert kernel32.GetConsoleWindow.restype is ctypes.c_void_p
        user32 = web_tray._get_user32()
        assert user32 is not None
        assert user32.GetWindowLongW.restype is ctypes.c_long
        assert user32.GetSystemMenu.restype is ctypes.c_void_p
        # 第二次调用命中模块级缓存（同一对象）
        assert web_tray._get_kernel32() is kernel32
        assert web_tray._get_user32() is user32

    def test_non_windows_platform_returns_none(self, monkeypatch: pytest.MonkeyPatch, reset_dll_cache: None) -> None:
        monkeypatch.setattr(web_tray.sys, "platform", "linux")
        assert web_tray._get_kernel32() is None
        assert web_tray._get_user32() is None

    def test_dll_load_failure_returns_none(self, monkeypatch: pytest.MonkeyPatch, reset_dll_cache: None) -> None:
        if sys.platform != "win32":
            pytest.skip("仅在 Windows 下 _get_* 会真的尝试加载 DLL")

        calls: list[tuple[object, ...]] = []

        def boom(*args: object, **kwargs: object) -> None:
            calls.append(args)
            raise OSError("kernel32 unavailable")

        # 旧写法 `monkeypatch.setattr(ctypes, "WinDLL", boom)` 改的是全进程唯一的
        # ctypes 本体——替身窗口内任何其它线程/库的 WinDLL 调用都会一起炸。按 _imported_module_shim
        # 的口径走 sys.modules 条目（生产侧是函数内 import，无模块级引用可绑）。
        real_windll = ctypes.WinDLL
        monkeypatch.setitem(sys.modules, "ctypes", _imported_module_shim("ctypes", WinDLL=boom))
        assert web_tray._get_kernel32() is None
        assert web_tray._get_user32() is None
        # 反向见证两条：① 真模块本体从未被改写；② boom 确实被调用过两次——若将来生产侧把
        # import 提到模块级、sys.modules 条目不再被读到，这条会先红并给出「shim 未接上」的归因。
        assert ctypes.WinDLL is real_windll
        assert len(calls) == 2, f"shim 未接上：WinDLL 替身被调用 {len(calls)} 次（应为 kernel32+user32 各一次）"


def _recorder(sink: list[Any], label: Any, result: int) -> Any:
    # 返回「把 (label, 入参) 记进 sink 并回吐固定返回值」的可调用对象。
    # 不写成 `lambda *a: sink.append(a) or 1`：mypy 的 func-returns-value 会因
    # 「取用 list.append 的返回值」直接报错（append 恒返回 None）。
    def _call(*args: Any) -> int:
        sink.append((label, args))
        return result

    return _call


class TestConsoleWindowPatching:
    def test_missing_dll_handles_are_skipped(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(web_tray, "_get_kernel32", lambda: None)
        monkeypatch.setattr(web_tray, "_get_user32", lambda: None)
        tray = web_tray.WebConsoleTray("127.0.0.1", 8000)
        tray._patch_console_window()
        assert tray._hwnd is None

    def test_zero_hwnd_is_skipped(self, monkeypatch: pytest.MonkeyPatch) -> None:
        kernel32 = types.SimpleNamespace(GetConsoleWindow=lambda: 0)
        monkeypatch.setattr(web_tray, "_get_kernel32", lambda: kernel32)
        monkeypatch.setattr(web_tray, "_get_user32", lambda: types.SimpleNamespace())
        tray = web_tray.WebConsoleTray("127.0.0.1", 8000)
        tray._patch_console_window()
        assert tray._hwnd is None

    def test_toolwindow_style_and_close_disabled(self, monkeypatch: pytest.MonkeyPatch) -> None:
        calls: list[tuple[str, tuple[Any, ...]]] = []
        kernel32 = types.SimpleNamespace(GetConsoleWindow=lambda: 0x1234)
        user32 = types.SimpleNamespace(
            GetWindowLongW=_recorder(calls, "get", 0),
            SetWindowLongW=_recorder(calls, "set", 0),
            SetWindowPos=_recorder(calls, "pos", 1),
            GetSystemMenu=_recorder(calls, "menu", 0x99),
            EnableMenuItem=_recorder(calls, "enable", 1),
        )
        monkeypatch.setattr(web_tray, "_get_kernel32", lambda: kernel32)
        monkeypatch.setattr(web_tray, "_get_user32", lambda: user32)
        tray = web_tray.WebConsoleTray("127.0.0.1", 8000)
        tray._patch_console_window()

        assert tray._hwnd == 0x1234
        set_call = dict((name, args) for name, args in calls)["set"]
        _hwnd, idx, new_style = cast(tuple[Any, ...], set_call)
        assert idx == web_tray.GWL_EXSTYLE
        # 工具窗口位必须置上、应用窗口位必须清掉——两者缺一都会留下任务栏按钮。
        assert new_style & web_tray.WS_EX_TOOLWINDOW
        assert not new_style & web_tray.WS_EX_APPWINDOW
        enable = dict((name, args) for name, args in calls)["enable"]
        assert enable[1] == web_tray.SC_CLOSE
        assert enable[2] & web_tray.MF_GRAYED

    def test_no_system_menu_skips_graying(self, monkeypatch: pytest.MonkeyPatch) -> None:
        calls: list[tuple[str, tuple[Any, ...]]] = []
        kernel32 = types.SimpleNamespace(GetConsoleWindow=lambda: 0x1234)
        user32 = types.SimpleNamespace(
            GetWindowLongW=lambda hwnd, idx: 0,
            SetWindowLongW=lambda hwnd, idx, style: 0,
            SetWindowPos=lambda *a: 1,
            GetSystemMenu=lambda hwnd, revert: 0,
            EnableMenuItem=_recorder(calls, "enable", 1),
        )
        monkeypatch.setattr(web_tray, "_get_kernel32", lambda: kernel32)
        monkeypatch.setattr(web_tray, "_get_user32", lambda: user32)
        web_tray.WebConsoleTray("127.0.0.1", 8000)._patch_console_window()
        assert calls == []

    def test_window_api_exception_is_swallowed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        kernel32 = types.SimpleNamespace(GetConsoleWindow=lambda: 0x1234)
        user32 = types.SimpleNamespace(GetWindowLongW=lambda hwnd, idx: (_ for _ in ()).throw(OSError("denied")))
        monkeypatch.setattr(web_tray, "_get_kernel32", lambda: kernel32)
        monkeypatch.setattr(web_tray, "_get_user32", lambda: user32)
        tray = web_tray.WebConsoleTray("127.0.0.1", 8000)
        tray._patch_console_window()  # 不得抛出：托盘美化失败不能影响 Web 服务
        assert tray._hwnd == 0x1234


class TestTrayIcon:
    def test_drawn_icon_paints_all_three_shapes(self, fake_qt: dict[str, types.ModuleType]) -> None:
        icon = web_tray.WebConsoleTray._create_icon()
        assert isinstance(icon, _FakeQIcon)
        painter = _FakeQPainter.instances[-1]
        kinds = [kind for kind, _args in painter.ops]
        # 圆角底板 + 白环 + 红点，且必须以 end() 收尾（漏掉 end 会在真 Qt 上留下未结束的绘制）
        assert kinds.count("rounded") == 1
        assert kinds.count("ellipse") == 2
        assert kinds[-1] == "end"
        assert painter.pixmap.size == (64, 64)

    def test_disk_icon_wins_over_drawn(self, fake_qt: dict[str, types.ModuleType], tmp_path: Path) -> None:
        _ = (tmp_path / "icon.png").write_bytes(b"\x89PNG")
        tray = web_tray.WebConsoleTray("127.0.0.1", 8000)
        # 直接换 _resource_roots 比造 sys.frozen 更贴近「探测到文件」这一被测点
        _original = web_tray._resource_roots
        web_tray._resource_roots = lambda: [str(tmp_path)]  # type: ignore[assignment]
        try:
            assert tray._load_icon_from_disk() is not None
            assert isinstance(tray._build_icon(), _FakeQIcon)
            assert _FakeQPainter.instances == []  # 命中磁盘图标就不该再自绘
        finally:
            web_tray._resource_roots = _original  # type: ignore[assignment]

    def test_configured_icon_file_wins_over_directory_probe(
        self, fake_qt: dict[str, types.ModuleType], tmp_path: Path
    ) -> None:
        # 用户显式导入的图标必须压过约定文件名（favicon.ico/icon.ico/icon.png）：
        # 顺序反过来就是「面板上传成功、托盘还是旧图标」——本次要消掉的正是这种一半生效。
        _ = (tmp_path / "icon.ico").write_bytes(b"\x00\x00\x01\x00\x01\x00" + bytes(16))
        custom = tmp_path / "custom.ico"
        custom.write_bytes(b"\x00\x00\x01\x00\x01\x00" + bytes(16))
        tray = web_tray.WebConsoleTray("127.0.0.1", 8000, icon_file=str(custom))
        _original = web_tray._resource_roots
        web_tray._resource_roots = lambda: [str(tmp_path)]  # type: ignore[assignment]
        try:
            icon = tray._load_icon_from_disk()
            assert icon is not None
            assert cast(_FakeQIcon, icon).args == (str(custom),)
        finally:
            web_tray._resource_roots = _original  # type: ignore[assignment]

    def test_stale_icon_file_falls_back_to_directory_probe(
        self, fake_qt: dict[str, types.ModuleType], tmp_path: Path
    ) -> None:
        # 配置里记的图标被用户删了：不得留下「托盘空白」，要继续往下探
        probe = tmp_path / "icon.png"
        probe.write_bytes(b"\x89PNG")
        tray = web_tray.WebConsoleTray("127.0.0.1", 8000, icon_file=str(tmp_path / "gone.ico"))
        _original = web_tray._resource_roots
        web_tray._resource_roots = lambda: [str(tmp_path)]  # type: ignore[assignment]
        try:
            icon = tray._load_icon_from_disk()
            assert icon is not None
            assert cast(_FakeQIcon, icon).args == (str(probe),)
        finally:
            web_tray._resource_roots = _original  # type: ignore[assignment]

    def test_malformed_icon_path_is_swallowed(self, fake_qt: dict[str, types.ModuleType], tmp_path: Path) -> None:
        # 路径含 NUL 时 pathlib 是抛 ValueError 而不是返回 False：图标是本进程唯一的退出入口，
        # 一个坏路径绝不能把 start() 带崩（表现为「Web 面板起不来」）。
        tray = web_tray.WebConsoleTray("127.0.0.1", 8000, icon_file="bad\x00path.ico")
        _original = web_tray._resource_roots
        web_tray._resource_roots = lambda: [str(tmp_path)]  # type: ignore[assignment]
        try:
            assert tray._load_icon_from_disk() is None
        finally:
            web_tray._resource_roots = _original  # type: ignore[assignment]

    def test_missing_disk_icon_falls_back_to_drawn(self, fake_qt: dict[str, types.ModuleType], tmp_path: Path) -> None:
        tray = web_tray.WebConsoleTray("127.0.0.1", 8000)
        _original = web_tray._resource_roots
        web_tray._resource_roots = lambda: [str(tmp_path)]  # type: ignore[assignment]
        try:
            assert tray._load_icon_from_disk() is None
            assert isinstance(tray._build_icon(), _FakeQIcon)
        finally:
            web_tray._resource_roots = _original  # type: ignore[assignment]

    def test_resource_roots_frozen_then_source(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        # 冻结态必须同时探 _MEIPASS（onefile 解包目录）与 exe 同级目录，两条都要在，
        # 否则「用户把图标放在 exe 旁边」这唯一的手工入口就没了。
        # 假路径必须用宿主平台形态构造：_resource_roots 用 os.path.dirname 解析 exe 目录，
        # 在 Linux 上喂 Windows 风格字面量会得到空串（真实冻结态的路径本来就与宿主同形态）。
        meipass = tmp_path / "_MEIPASS"
        exe = tmp_path / "app-Web.exe"
        monkeypatch.setattr(web_tray.sys, "frozen", True, raising=False)
        monkeypatch.setattr(web_tray.sys, "_MEIPASS", str(meipass), raising=False)
        monkeypatch.setattr(web_tray.sys, "executable", str(exe), raising=False)
        roots = web_tray._resource_roots()
        assert roots[:2] == [str(meipass), str(tmp_path)]
        assert Path(roots[-1]) == Path(web_tray.__file__).resolve().parent.parent

    def test_resource_roots_source_only(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delattr(web_tray.sys, "frozen", raising=False)
        roots = web_tray._resource_roots()
        assert len(roots) == 1
        assert Path(roots[0]) == Path(web_tray.__file__).resolve().parent.parent


class TestStartStop:
    def test_disabled_platform_is_noop(self, monkeypatch: pytest.MonkeyPatch, fake_qt: dict[str, Any]) -> None:
        monkeypatch.setattr(web_tray, "ENABLED", False)
        tray = web_tray.WebConsoleTray("0.0.0.0", 8000)
        assert tray.start() is False
        assert tray.icon is None

    def test_missing_pyside6_degrades_to_message(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setattr(web_tray, "ENABLED", True)
        # 三个条目都放 None：只放父包时，若别处已 import 过子模块，sys.modules 命中会跳过父包检查
        for name in ("PySide6", "PySide6.QtGui", "PySide6.QtWidgets"):
            monkeypatch.setitem(sys.modules, name, None)
        monkeypatch.setattr(web_tray, "_get_kernel32", lambda: None)
        monkeypatch.setattr(web_tray, "_get_user32", lambda: None)
        tray = web_tray.WebConsoleTray("0.0.0.0", 8000)
        assert tray.start() is False
        assert tray.icon is None
        assert "PySide6" in capsys.readouterr().out

    def test_unavailable_tray_degrades_without_owning_main_thread(
        self, fake_qt: dict[str, Any], no_win32_dlls: None, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # 「Qt 能构造图标但挂不上去」（无交互桌面的服务会话）必须降级：
        # 返回 True 会让调用方交出主线程，而用户既看不到图标也拿不到退出入口。
        _FakeQSystemTrayIcon.available = False
        tray = web_tray.WebConsoleTray("0.0.0.0", 8000)
        assert tray.start() is False
        assert tray.icon is None
        assert "系统托盘" in capsys.readouterr().out

    def test_start_builds_menu_and_shows_icon(
        self, fake_qt: dict[str, Any], no_win32_dlls: None, capsys: pytest.CaptureFixture[str]
    ) -> None:
        server = types.SimpleNamespace(should_exit=False)
        tray = web_tray.WebConsoleTray("127.0.0.1", 8888, server=cast(Any, server))
        assert tray.start() is True

        app = cast(_FakeQApplication, tray.app)
        assert app is not None and app.exec_calls == 0
        # 托盘进程没有任何 QWidget：不关掉「最后窗口关闭即退出」，事件循环会被提前带下去
        assert app.quit_on_last_window_closed is False
        icon = cast(_FakeQSystemTrayIcon, tray.icon)
        assert icon.shown == 1
        assert "8888" in cast(str, icon.tooltip)
        menu = cast(_FakeQMenu, tray.menu)
        assert menu is not None
        assert [action.text for action in menu.actions] == [
            "显示控制台",
            "隐藏控制台",
            "打开 Web 界面",
            "退出程序",
        ]
        assert menu.separators == 1
        assert icon.context_menu is menu
        assert "已启用系统托盘" in capsys.readouterr().out
        tray.stop()

    def test_start_reuses_existing_application(self, fake_qt: dict[str, Any], no_win32_dlls: None) -> None:
        existing = _FakeQApplication([])
        tray = web_tray.WebConsoleTray("127.0.0.1", 8000)
        assert tray.start() is True
        # 复用别人的 QApplication 时不得替它 quit：那会把宿主的事件循环一起收掉
        assert tray.app is existing
        assert tray._owns_app is False
        tray.stop()
        assert existing.quit_calls == 0

    def test_stop_is_safe_when_icon_absent(self) -> None:
        tray = web_tray.WebConsoleTray("127.0.0.1", 8000)
        tray.stop()
        assert tray.icon is None

    def test_stop_hides_icon_and_quits_owned_app(self, fake_qt: dict[str, Any], no_win32_dlls: None) -> None:
        tray = web_tray.WebConsoleTray("127.0.0.1", 8000)
        assert tray.start() is True
        icon = cast(_FakeQSystemTrayIcon, tray.icon)
        app = cast(_FakeQApplication, tray.app)
        tray.stop()
        assert icon.hidden == 1
        assert tray.icon is None
        assert app.quit_calls == 1

    def test_stop_swallows_icon_hide_errors(self) -> None:
        tray = web_tray.WebConsoleTray("127.0.0.1", 8000)

        class _Angry:
            def hide(self) -> None:
                raise RuntimeError("tray already gone")

        tray.icon = cast(Any, _Angry())
        tray.stop()
        assert tray.icon is None


class TestEventLoop:
    def test_run_event_loop_starts_watchdog_and_blocks(self, fake_qt: dict[str, Any], no_win32_dlls: None) -> None:
        tray = web_tray.WebConsoleTray("127.0.0.1", 8000)
        assert tray.start() is True
        app = cast(_FakeQApplication, tray.app)
        tray.run_event_loop(stop_when=lambda: False)
        assert app.exec_calls == 1
        # 定时器即使 stop_when 恒假也必须起：它是 Ctrl+C 在事件循环期间唯一的落地点
        assert tray._timer is None  # finally 段已停并置空
        assert app.quit_calls == 0

    def test_watchdog_quits_when_stop_when_becomes_true(self, fake_qt: dict[str, Any], no_win32_dlls: None) -> None:
        tray = web_tray.WebConsoleTray("127.0.0.1", 8000)
        assert tray.start() is True
        app = cast(_FakeQApplication, tray.app)
        flags = [False, True]
        hits: list[int] = []

        def stop_when() -> bool:
            hits.append(1)
            return flags[min(len(hits) - 1, len(flags) - 1)]

        tray._poll(stop_when)
        assert app.quit_calls == 0
        tray._poll(stop_when)
        assert app.quit_calls == 1

    def test_watchdog_survives_stop_when_exception(self, fake_qt: dict[str, Any], no_win32_dlls: None) -> None:
        # 调用方抛一次性异常不得把循环打死：托盘是本进程唯一的退出入口
        tray = web_tray.WebConsoleTray("127.0.0.1", 8000)
        assert tray.start() is True
        app = cast(_FakeQApplication, tray.app)

        def boom() -> bool:
            raise RuntimeError("thread probe failed")

        tray._poll(boom)
        assert app.quit_calls == 0

    def test_watchdog_without_stop_when_never_quits(self, fake_qt: dict[str, Any], no_win32_dlls: None) -> None:
        tray = web_tray.WebConsoleTray("127.0.0.1", 8000)
        assert tray.start() is True
        app = cast(_FakeQApplication, tray.app)
        tray._poll(None)
        assert app.quit_calls == 0

    def test_request_quit_forces_loop_exit_and_freezes_watchdog(
        self, fake_qt: dict[str, Any], no_win32_dlls: None
    ) -> None:
        tray = web_tray.WebConsoleTray("127.0.0.1", 8000)
        assert tray.start() is True
        app = cast(_FakeQApplication, tray.app)
        tray.request_quit()
        assert app.quit_calls == 1
        # 已强制退出后再触发看门狗不得重复 quit（Qt 的 quit 可重入，但退出路径会走两遍）
        tray._poll(lambda: True)
        assert app.quit_calls == 1

    def test_run_event_loop_without_app_is_noop(self) -> None:
        tray = web_tray.WebConsoleTray("127.0.0.1", 8000)
        tray.run_event_loop()  # start() 未成功（或已降级）时不得抛异常


class TestMenuCallbacks:
    def test_on_show_without_hwnd_does_nothing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        calls: list[int] = []
        monkeypatch.setattr(
            web_tray, "_get_user32", lambda: types.SimpleNamespace(ShowWindow=lambda *a: calls.append(1))
        )
        tray = web_tray.WebConsoleTray("127.0.0.1", 8000)
        tray._on_show()
        assert calls == []

    def test_on_show_without_user32_does_nothing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(web_tray, "_get_user32", lambda: None)
        tray = web_tray.WebConsoleTray("127.0.0.1", 8000)
        tray._hwnd = 0x1234
        tray._on_show()

    def test_on_show_restores_and_focuses(self, monkeypatch: pytest.MonkeyPatch) -> None:
        calls: list[tuple[str, tuple[Any, ...]]] = []
        user32 = types.SimpleNamespace(
            ShowWindow=_recorder(calls, "show", 1),
            SetForegroundWindow=_recorder(calls, "fg", 1),
        )
        monkeypatch.setattr(web_tray, "_get_user32", lambda: user32)
        tray = web_tray.WebConsoleTray("127.0.0.1", 8000)
        tray._hwnd = 0x1234
        tray._on_show()
        assert calls == [("show", (0x1234, web_tray.SW_RESTORE)), ("fg", (0x1234,))]

    def test_on_show_survives_foreground_failure(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # 前台窗口切换在 Windows 上会被焦点抢占策略拒绝（返回 0 / 抛异常），
        # 此时 ShowWindow 仍须已经生效——所以异常必须只吞掉 SetForegroundWindow。
        calls: list[tuple[str, tuple[Any, ...]]] = []

        def fg(hwnd: int) -> int:
            raise OSError("foreground lock held")

        user32 = types.SimpleNamespace(ShowWindow=_recorder(calls, "show", 1), SetForegroundWindow=fg)
        monkeypatch.setattr(web_tray, "_get_user32", lambda: user32)
        tray = web_tray.WebConsoleTray("127.0.0.1", 8000)
        tray._hwnd = 0x1234
        tray._on_show()
        assert [name for name, _args in calls] == ["show"]

    def test_on_hide_hides_without_stealing_focus(self, monkeypatch: pytest.MonkeyPatch) -> None:
        calls: list[tuple[str, tuple[Any, ...]]] = []
        user32 = types.SimpleNamespace(
            ShowWindow=_recorder(calls, "show", 1),
            SetForegroundWindow=_recorder(calls, "fg", 1),
        )
        monkeypatch.setattr(web_tray, "_get_user32", lambda: user32)
        tray = web_tray.WebConsoleTray("127.0.0.1", 8000)
        tray._hwnd = 0x1234
        tray._on_hide()
        # 隐藏时去抢焦点会让刚藏起来的窗口又被前置（Windows 上表现为「点了没反应」）
        assert calls == [("show", (0x1234, web_tray.SW_HIDE))]

    def test_activated_reason_maps_to_show(self, monkeypatch: pytest.MonkeyPatch, fake_qt: dict[str, Any]) -> None:
        calls: list[int] = []
        monkeypatch.setattr(
            web_tray, "_get_user32", lambda: types.SimpleNamespace(ShowWindow=lambda *a: calls.append(1))
        )
        tray = web_tray.WebConsoleTray("127.0.0.1", 8000)
        tray._hwnd = 0x1234
        tray._on_activated(_FakeQSystemTrayIcon.ActivationReason.Trigger)
        tray._on_activated(_FakeQSystemTrayIcon.ActivationReason.DoubleClick)
        assert len(calls) == 2
        # 右键（Context）只弹菜单，不得顺手把窗口也弹出来
        tray._on_activated(_FakeQSystemTrayIcon.ActivationReason.Context)
        assert len(calls) == 2

    def test_open_browser_uses_panel_url(self, monkeypatch: pytest.MonkeyPatch) -> None:
        opened: list[str] = []
        monkeypatch.setattr(web_tray, "webbrowser", types.SimpleNamespace(open=opened.append))
        tray = web_tray.WebConsoleTray("127.0.0.1", 8000)
        tray._on_open_browser()
        assert opened == ["http://127.0.0.1:8000"]

    def test_web_url_normalizes_wildcard_and_ipv6(self) -> None:
        assert web_tray.WebConsoleTray("0.0.0.0", 8000)._web_url() == "http://127.0.0.1:8000"
        assert web_tray.WebConsoleTray("::", 8000)._web_url() == "http://127.0.0.1:8000"
        # IPv6 字面量不加方括号时，浏览器会把 ":8000" 当成地址的一部分
        assert web_tray.WebConsoleTray("::1", 8000)._web_url() == "http://[::1]:8000"
        assert web_tray.WebConsoleTray("[::1]", 8000)._web_url() == "http://[::1]:8000"
        assert web_tray.WebConsoleTray("192.168.1.7", 8000)._web_url() == "http://192.168.1.7:8000"

    def test_open_browser_swallows_failures(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def boom(url: str) -> bool:
            raise OSError("no browser")

        monkeypatch.setattr(web_tray, "webbrowser", types.SimpleNamespace(open=boom))
        tray = web_tray.WebConsoleTray("127.0.0.1", 8000)
        tray._on_open_browser()  # 不得抛出：异常穿过 Qt 事件循环等于托盘失灵

    def test_on_exit_signals_uvicorn_shutdown(self, monkeypatch: pytest.MonkeyPatch) -> None:
        server = types.SimpleNamespace(should_exit=False)
        tray = web_tray.WebConsoleTray("127.0.0.1", 8000, server=cast(Any, server))
        icon = _FakeQSystemTrayIcon()
        tray.icon = cast(Any, icon)
        # CODE_REVIEW_2026-10-27 4.3：有 server 分支必须**只**置 should_exit。os._exit 一旦也被
        # 触发，uvicorn 的优雅关闭（web.py finally 段的 ffmpeg / 连接池清理）会被整体跳过。
        # 「codes 恒空」不是假绿——同一替身机制在下面的 test_on_exit_without_server_hard_exits
        # 里断言了 codes == [0]，即函数内 `import os` 确实读到了这个 sys.modules 条目。
        codes: list[int] = []
        monkeypatch.setitem(sys.modules, "os", _imported_module_shim("os", _exit=lambda code: codes.append(code)))
        tray._on_exit()
        assert server.should_exit is True
        # 与 stop() 不同，_on_exit 只收图标而不把 self.icon 置 None：
        # 循环还在跑，提前置 None 会让随后到达的收尾错过停图标。
        assert icon.hidden == 1
        assert tray.icon is not None
        assert codes == [], f"有 server 时不得走 os._exit 强制退出: {codes}"

    def test_on_exit_without_server_hard_exits(self, monkeypatch: pytest.MonkeyPatch) -> None:
        codes: list[int] = []
        # 旧写法 `monkeypatch.setattr(os, "_exit", ...)` 改的是全进程唯一的 os 本体，
        # 同窗口内任何线程的删除/重命名/退出都会走进这个只记账的替身。生产侧 `_on_exit` 是函数内
        # `import os`，故按 _imported_module_shim 的口径换 sys.modules 条目：真 os 本体逐字不变，
        # 只有本用例窗口内的 import 绑定到替身。
        real_exit = os._exit
        monkeypatch.setitem(sys.modules, "os", _imported_module_shim("os", _exit=lambda code: codes.append(code)))
        tray = web_tray.WebConsoleTray("127.0.0.1", 8000, server=None)
        tray._on_exit()
        assert codes == [0]
        # 反向见证：真 os 本体从未被换掉（_exit 一旦泄漏进本体，退出路径会在全进程静默失效）
        assert os._exit is real_exit

    def test_on_exit_swallows_icon_hide_errors(self) -> None:
        class _Angry:
            def hide(self) -> None:
                raise RuntimeError("boom")

        # 必须传入 server：否则 _on_exit 会走 os._exit(0) 分支，直接杀掉测试进程。
        tray = web_tray.WebConsoleTray("127.0.0.1", 8000, server=cast(Any, types.SimpleNamespace(should_exit=False)))
        tray.icon = cast(Any, _Angry())
        tray._on_exit()  # 不得抛出：退出信号不能因为图标已拆而丢
        assert tray.icon is not None

    def test_about_to_quit_signals_shutdown_and_hides_icon(self) -> None:
        server = types.SimpleNamespace(should_exit=False)
        tray = web_tray.WebConsoleTray("127.0.0.1", 8000, server=cast(Any, server))
        icon = _FakeQSystemTrayIcon()
        tray.icon = cast(Any, icon)
        tray._on_about_to_quit()
        # 漏置 should_exit 的后果是 serve() 不返回，web.py 的 finally 段永远等不到
        assert server.should_exit is True
        assert icon.hidden == 1


def test_module_constants_match_win32_api() -> None:
    # 这些魔数一旦抄错，症状是「托盘在但窗口没被收起」这类极难归因的视觉 bug，
    # 且没有任何异常抛出，只能用常量断言兜住。
    source = (Path(__file__).resolve().parents[1] / "src" / "web_tray.py").read_text(encoding="utf-8")
    assert "GWL_EXSTYLE = -20" in source
    assert web_tray.SC_CLOSE == 0xF060
    assert web_tray.SW_HIDE == 0
    assert web_tray.SW_RESTORE == 9 and web_tray.SW_SHOW == 5
    assert web_tray.WS_EX_TOOLWINDOW == 0x00000080 and web_tray.WS_EX_APPWINDOW == 0x00040000
    assert web_tray.ENABLED is (sys.platform == "win32")
