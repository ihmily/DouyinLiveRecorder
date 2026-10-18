# tests/test_web_tray.py - src/web_tray.py 的行为锁。
#
# 该模块此前 0% 覆盖：它只在「Windows + 打包后的控制台」这一组合下才被启用，
# 测试环境里既没有真实 conhost 窗口、也不允许真的往用户桌面挂一个托盘图标。
# 补测的重点不是行数，而是三条**不能反向漂移**的边界：
#   1) 任何失败都必须静默降级（缺 pystray / DLL 加载失败 / 窗口调用抛异常），
#      绝不能让 Web 面板起不来——托盘只是锦上添花；
#   2) 不得真的改写宿主控制台样式：_patch_console_window 必须可在 DLL 缺失时短路；
#   3) 「退出程序」在无 uvicorn server 时走 os._exit(0)，这条隐蔽的强制退出路径
#      必须被显式锁住（否则将来有人删掉 else 分支，进程会卡在非零退出码上）。
#
# Mock 口径：pystray 用 sys.modules 桩替换（避免真实托盘）；Win32 DLL 句柄用
# SimpleNamespace 桩替换 _get_kernel32/_get_user32 的返回值，不触碰真窗口。
# 生产侧「函数内 import」的 stdlib（ctypes / os）一律经 _imported_module_shim 换 sys.modules 条目，
# 不改模块本体（MT-13 / LT-12，2026-10-18）。

# 分支地图（上边已给出三条不可反向漂移的边界，此处补“哪个用例管哪条”）：
#   DLL 句柄缓存的三个入口：已缓存直返 / 非 win32 早返回 / WinDLL 加载失败返 None。
#     真加载那条另断言 restype——HWND/HMENU 是指针宽度，缺省 c_int 会把 64 位句柄
#     截断成 32 位，后续窗口操作改写到错误地址（不报错，只是“托盘在但窗口没收起”）。
#   _patch_console_window：kernel32/user32 缺失→短路；hwnd=0→短路；正常→置 TOOLWINDOW
#     清 APPWINDOW 并置灰 SC_CLOSE；系统菜单拿不到→跳过置灰；窗口 API 抛异常→吞掉。
#   start：ENABLED=False → 什也不做；缺 pystray → 打一行提示后返回；正常 → 建菜单 +
#     守护线程跑 icon.run（必须用 sys.modules 桩替换 pystray，否则真往用户桌面挂图标）。
#   两个菜单回调：_on_show 先 ShowWindow 后 SetForegroundWindow，后者失败不得逆前者；
#     _on_exit 有 server 时只置 should_exit，无 server 时才走 os._exit(0)。
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


class _FakeIcon:
    def __init__(self, *args: object, **kwargs: object) -> None:
        self.args = args
        self.kwargs = kwargs
        self.stopped = 0
        self.run_called = 0

    def run(self) -> None:
        self.run_called += 1

    def stop(self) -> None:
        self.stopped += 1
        if self.stopped > 100:  # pragma: no cover - 防御性，永远不触发
            raise RuntimeError("unreachable")


class _FakePystray(types.ModuleType):
    def __init__(self) -> None:
        super().__init__("pystray")
        self.icons: list[_FakeIcon] = []
        self.menu_items: list[tuple[object, object, bool]] = []

    def Menu(self, *items: object) -> object:
        return ("menu", items)

    def MenuItem(self, text: str, callback: object, default: bool = False) -> object:
        self.menu_items.append((text, callback, default))
        return ("item", text, callback, default)

    def Icon(self, *args: object, **kwargs: object) -> _FakeIcon:
        icon = _FakeIcon(*args, **kwargs)
        self.icons.append(icon)
        return icon


def _imported_module_shim(name: str, **overrides: Any) -> types.SimpleNamespace:
    # MT-13 / LT-12（2026-10-18）：本模块要替的两个 stdlib 符号都处在**函数内 import** 的位置
    # （src/web_tray.py 的 _get_kernel32/_get_user32 里 `import ctypes`、_on_exit 里 `import os`），
    # 所以 web_tray 命名空间内根本没有可替换的模块引用：仓库常规的
    # `monkeypatch.setattr(<被测模块>, "os", shim)` 在这里打不上，写成 raising=False 更糟——
    # 会落一个永不被读的模块属性，用例静默假绿。生产侧配合（把 import 提到模块级）属另一回事，
    # 本轮不动生产代码。
    # 唯一真实接线点是 sys.modules 条目：函数内 `import x` 命中缓存即绑定该对象。
    # 浅拷贝保留真模块的全部符号（ctypes 的 c_void_p/c_long/c_int、os 的其余函数），
    # 只覆盖需要的那一个，于是 stdlib 模块本体在整个用例窗口内逐字不变，
    # 同窗口里其它线程/库拿到的仍是真实现（改本体的旧写法会把它们一并换掉）。
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
def fake_pystray(monkeypatch: pytest.MonkeyPatch) -> _FakePystray:
    module = _FakePystray()
    monkeypatch.setitem(sys.modules, "pystray", module)
    return module


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

        # MT-13（2026-10-18）：旧写法 `monkeypatch.setattr(ctypes, "WinDLL", boom)` 改的是全进程唯一的
        # ctypes 本体——替身窗口内任何其它线程/库的 WinDLL 调用都会一起炸。按 _imported_module_shim
        # 的口径走 sys.modules 条目（生产侧是函数内 import，无模块级引用可绑）。
        real_windll = ctypes.WinDLL
        monkeypatch.setitem(sys.modules, "ctypes", _imported_module_shim("ctypes", WinDLL=boom))
        assert web_tray._get_kernel32() is None
        assert web_tray._get_user32() is None
        # 反向见证两条：① 真模块本体从未被改写（本用例要防的正是「替身漏进全进程」）；
        # ② boom 确实被调用过两次——若将来生产侧把 import 提到模块级、sys.modules 条目不再被读到，
        # 这条会先红并给出「shim 未接上」的归因，而不是让「返回 None」被判成捕获逻辑的胜利。
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


class TestIconImage:
    def test_default_size_and_channels(self) -> None:
        try:
            import PIL  # noqa: F401  - 仅用来判定 GUI 依赖是否就位
        except ImportError:  # pragma: no cover - GUI 依赖缺失属环境限制
            pytest.skip("Pillow 未安装")
        image = web_tray.WebConsoleTray._create_icon_image()
        assert image.mode == "RGBA"
        assert image.size == (64, 64)
        # 中心是红点（录制指示），四角保持透明
        center = cast("tuple[int, ...]", image.getpixel((32, 32)))
        corner = cast("tuple[int, ...]", image.getpixel((0, 0)))
        assert center[0] > 150
        assert corner[3] == 0


class TestStartStop:
    def test_disabled_platform_is_noop(self, monkeypatch: pytest.MonkeyPatch, fake_pystray: _FakePystray) -> None:
        monkeypatch.setattr(web_tray, "ENABLED", False)
        tray = web_tray.WebConsoleTray("0.0.0.0", 8000)
        tray.start()
        assert tray.icon is None
        assert fake_pystray.icons == []

    def test_missing_pystray_degrades_to_message(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setattr(web_tray, "ENABLED", True)
        # sys.modules 里放 None 会让 import 语句直接抛 ImportError，等价于「未装 pystray」
        monkeypatch.setitem(sys.modules, "pystray", None)
        monkeypatch.setattr(web_tray, "_get_kernel32", lambda: None)
        monkeypatch.setattr(web_tray, "_get_user32", lambda: None)
        tray = web_tray.WebConsoleTray("0.0.0.0", 8000)
        tray.start()
        assert tray.icon is None
        assert "pystray" in capsys.readouterr().out

    def test_start_creates_menu_and_runs_icon_in_daemon_thread(
        self, monkeypatch: pytest.MonkeyPatch, fake_pystray: _FakePystray, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setattr(web_tray, "ENABLED", True)
        monkeypatch.setattr(web_tray, "_get_kernel32", lambda: None)
        monkeypatch.setattr(web_tray, "_get_user32", lambda: None)
        tray = web_tray.WebConsoleTray("127.0.0.1", 8888, server=None)
        tray.start()

        assert tray.icon is not None
        assert tray._thread is not None and tray._thread.daemon
        labels = [text for text, _cb, _d in fake_pystray.menu_items]
        assert labels == ["显示控制台", "退出程序"]
        # default=True 只能落在「显示控制台」上，双击托盘图标才等价于恢复窗口
        assert fake_pystray.menu_items[0][2] is True
        assert fake_pystray.menu_items[1][2] is False
        # tray.icon 的静态类型是 pystray.Icon；此处实际是 _FakeIcon（fake_pystray 换掉了模块），
        # 需显式 cast 才能取到替身记录的构造参数——不能用 Any 放宽，否则丢掉 _FakeIcon 的形状。
        tooltip = cast(_FakeIcon, tray.icon).args[2]
        assert "8888" in cast(str, tooltip)
        assert "已启用系统托盘" in capsys.readouterr().out
        tray.stop()

    def test_stop_is_safe_when_icon_absent(self) -> None:
        tray = web_tray.WebConsoleTray("127.0.0.1", 8000)
        tray.stop()
        assert tray.icon is None

    def test_stop_swallows_icon_stop_errors(self) -> None:
        tray = web_tray.WebConsoleTray("127.0.0.1", 8000)

        class _Angry:
            def stop(self) -> None:
                raise RuntimeError("tray already gone")

        tray.icon = cast(Any, _Angry())
        tray.stop()
        assert tray.icon is None


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

    def test_on_exit_signals_uvicorn_shutdown(self) -> None:
        server = types.SimpleNamespace(should_exit=False)
        tray = web_tray.WebConsoleTray("127.0.0.1", 8000, server=cast(Any, server))
        icon = _FakeIcon()
        tray.icon = cast(Any, icon)
        tray._on_exit()
        assert server.should_exit is True
        # 与 stop() 不同，_on_exit 只调 icon.stop() 而不把 self.icon 置 None：
        # 托盘线程正在自行退出，提前置 None 会让并发的 stop() 错过停图标。
        assert icon.stopped == 1
        assert tray.icon is not None

    def test_on_exit_without_server_hard_exits(self, monkeypatch: pytest.MonkeyPatch) -> None:
        codes: list[int] = []
        # LT-12（2026-10-18）：旧写法 `monkeypatch.setattr(os, "_exit", ...)` 改的是全进程唯一的 os 本体，
        # 同窗口内任何线程的删除/重命名/退出都会走进这个只记账的替身。生产侧 `_on_exit` 是函数内
        # `import os`，故按 _imported_module_shim 的口径换 sys.modules 条目：真 os 本体逐字不变，
        # 只有本用例窗口内的 import 绑定到替身。
        # [历史注] 旧注释称「_exit 不会被 harness 守护线程使用，且 monkeypatch 会还原，故不违反
        # 「不改 stdlib 本体」约定」——「会还原」只保证事后，不保证窗口内，2026-10-18 按仓库
        # 「测试编写强制约定」改正。
        real_exit = os._exit
        monkeypatch.setitem(sys.modules, "os", _imported_module_shim("os", _exit=lambda code: codes.append(code)))
        tray = web_tray.WebConsoleTray("127.0.0.1", 8000, server=None)
        tray._on_exit()
        assert codes == [0]
        # 反向见证：真 os 本体从未被换掉（_exit 一旦泄漏进本体，退出路径会在全进程静默失效）
        assert os._exit is real_exit

    def test_on_exit_swallows_icon_stop_errors(self) -> None:
        class _Angry:
            def stop(self) -> None:
                raise RuntimeError("boom")

        # 必须传入 server：否则 _on_exit 会走 os._exit(0) 分支，直接杀掉测试进程。
        tray = web_tray.WebConsoleTray("127.0.0.1", 8000, server=cast(Any, types.SimpleNamespace(should_exit=False)))
        tray.icon = cast(Any, _Angry())
        tray._on_exit()  # 不得抛出：图标已经拆了，退出信号不能因它而丢
        assert tray.icon is not None


def test_module_constants_match_win32_api() -> None:
    # 这些魔数一旦抄错，症状是「托盘在但窗口没被收起」这类极难归因的视觉 bug，
    # 且没有任何异常抛出，只能用常量断言兜住。
    source = (Path(__file__).resolve().parents[1] / "src" / "web_tray.py").read_text(encoding="utf-8")
    assert "GWL_EXSTYLE = -20" in source
    assert web_tray.SC_CLOSE == 0xF060
    assert web_tray.SW_RESTORE == 9 and web_tray.SW_SHOW == 5
    assert web_tray.WS_EX_TOOLWINDOW == 0x00000080 and web_tray.WS_EX_APPWINDOW == 0x00040000
    assert web_tray.ENABLED is (sys.platform == "win32")
