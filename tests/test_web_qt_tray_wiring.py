# tests/test_web_qt_tray_wiring.py - web.py 里「Qt 托盘占用主线程」那两条接线的行为锁。
#
# 为什么单独成文件：`src/web_tray.py` 的托盘本体由 tests/test_web_tray.py 用 Qt 替身覆盖，
# 而「uvicorn 挪到守护线程」「Ctrl+C 改由本进程接管」这两条是 **web.py 侧**的接线——
# 它们不在托盘模块里，托盘单测永远看不见，却又决定了主线程归谁：
#   · `_serve_forever` 写错（比如忘了 asyncio.run）→ 服务根本不启动，而托盘照常显示；
#   · `_install_sigint_shutdown` 漏装或没置 should_exit → Ctrl+C 后 serve() 不返回，
#     web.py 的 finally 清理段（后处理线程池 / ffmpeg / 连接池）永远等不到，
#     用户视角是「托盘点了退出没反应」，只能靠任务管理器。
#
# Mock 口径：不真起 uvicorn、不把信号处理器留在进程里（装完取回 handler 直接调用，
# finally 段还原原 handler）——真装会在整个会话内改掉 Ctrl+C 行为，属进程级副作用。

import ast
import signal
import types
from pathlib import Path
from typing import Any, cast

import pytest

import web


class _FakeTray:
    def __init__(self) -> None:
        self.force_quits = 0

    def request_quit(self) -> None:
        self.force_quits += 1


def test_serve_forever_drives_uvicorn_through_asyncio(monkeypatch: pytest.MonkeyPatch) -> None:
    # Qt 托盘模式下 uvicorn 在守护线程里跑：线程体必须真的用 asyncio.run 驱动 serve()，
    # 只调 serve() 会得到一个从未被 await 的协程对象，服务静默不启动。
    calls: list[Any] = []
    server = types.SimpleNamespace(serve=lambda: "coro-object")
    monkeypatch.setattr(web, "asyncio", types.SimpleNamespace(run=lambda coro: calls.append(coro)))
    web._serve_forever(cast(Any, server))
    assert calls == ["coro-object"]


def test_sigint_handler_signals_uvicorn_then_forces_quit_on_second_press() -> None:
    server = types.SimpleNamespace(should_exit=False)
    tray = _FakeTray()
    original = signal.getsignal(signal.SIGINT)
    try:
        web._install_sigint_shutdown(server, tray)  # type: ignore[arg-type]
        handler = signal.getsignal(signal.SIGINT)
        assert callable(handler), "未装上 SIGINT handler（Qt 模式下 Ctrl+C 无人接管）"
        handler(signal.SIGINT, None)
        # 第一次：只置 should_exit，事件循环交给看门狗在服务线程结束后退出
        assert server.should_exit is True
        assert tray.force_quits == 0
        # 第二次：不再等服务线程，直接放开事件循环
        handler(signal.SIGINT, None)
        assert tray.force_quits == 1
    finally:
        signal.signal(signal.SIGINT, original)


def test_main_branches_on_tray_ownership() -> None:
    # 结构锁：main() 必须按 start() 的返回值分两条路——Qt 托盘占用主线程时把主线程交给
    # run_event_loop()，降级时照旧在主线程 asyncio.run(server.serve())。
    # 任一条缺失都会让「主线程归谁」的契约落空（托盘永远死 / 或面板失去退出入口），
    # 而功能用例（服务起得来）根本测不出这类接线错误。
    tree = ast.parse(Path(str(web.__file__)).read_text(encoding="utf-8"))
    fn = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "main")
    loop_calls = [
        node
        for node in ast.walk(fn)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "run_event_loop"
    ]
    serve_calls = [
        node
        for node in ast.walk(fn)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "run"
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "asyncio"
    ]
    assert loop_calls, "main() 里找不到 tray.run_event_loop() 调用（Qt 托盘模式下主线程无处可交）"
    assert serve_calls, "main() 里找不到 asyncio.run(...) 调用（降级路径下服务不会被驱动）"
