#!/usr/bin/env python3
# -*- encoding: utf-8 -*-
# DouyinLiveRecorder Web 管理面板入口
#
# 启动方式: python web.py
# 浏览器访问: http://localhost:8000
#
# 与 main.py 共用同一录制引擎（通过 import main 触发初始化），
# 在守护线程运行 main.main()，主线程运行 uvicorn。
import os
import sys
import threading
import asyncio
from datetime import datetime
from typing import cast

# 确保项目根在 sys.path
_script_dir = os.path.dirname(os.path.realpath(__file__))
if _script_dir not in sys.path:
    sys.path.insert(0, _script_dir)

# 中文 Windows 控制台（尤其 PyInstaller 冻结后）stdout 默认 GBK 编码，
# 打印中文/emoji 会出现乱码，emoji（如警告符 ⚠）还会抛 UnicodeEncodeError 崩溃。
# 统一改为 UTF-8 输出，并把控制台代码页切到 65001，保证冻结后中文正常显示。
def _reconfigure_stream(stream: object) -> None:
    # 用 getattr 探测 reconfigure 是否存在（避免 isinstance 依赖具体类型、
    # 也避免将 Any 传入 hasattr），仅当为可调用时才执行。
    reconfigure = getattr(stream, "reconfigure", None)
    if callable(reconfigure):
        try:
            _ = reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def _fix_encoding():
    _streams: list[object] = [getattr(sys, "stdout", None), getattr(sys, "stderr", None)]
    for _s in _streams:
        if _s is not None:
            _reconfigure_stream(_s)
    if sys.platform == "win32":
        try:
            import ctypes
            _k32 = ctypes.windll.kernel32
            _k32.SetConsoleOutputCP(65001)
            _k32.SetConsoleCP(65001)
        except Exception:
            pass


_fix_encoding()


def _enter_background_mode(logs_dir: str, host: str, port: int) -> None:
    # 进入后台运行模式：隐藏控制台窗口，将输出重定向到日志文件。
    # Windows 下隐藏控制台窗口（SW_HIDE）；其他平台仅重定向输出。
    # 日志写入 logs/web_console.log，可通过 Web 面板或任务管理器管理程序。
    log_path = os.path.join(logs_dir, "web_console.log")

    # 重定向前先向控制台输出提示（窗口即将隐藏）
    print("[web] 进入后台运行模式，控制台窗口将隐藏")
    print(f"[web] 日志文件: {log_path}")
    print(f"[web] 访问地址: http://{host}:{port}")
    _flush = getattr(sys.stdout, "flush", None)
    if callable(_flush):
        _ = _flush()

    # 重定向输出到日志文件（buffering=1 行缓冲，确保日志实时写入）
    log_stream = open(log_path, 'a', encoding='utf-8', buffering=1)
    sys.stdout = log_stream
    sys.stderr = log_stream

    ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"\n{'=' * 60}")
    print(f"[{ts}] Web 管理面板进入后台运行模式")
    print(f"控制台窗口已隐藏，访问地址: http://{host}:{port}")
    print(f"日志文件: {log_path}")
    print("如需恢复控制台显示，请在 config.ini 设置 web_show_console = true 后重启")
    print(f"{'=' * 60}\n")

    # Windows: 隐藏控制台窗口（SW_HIDE = 0）
    if sys.platform == 'win32':
        try:
            import ctypes
            hwnd: int = cast(int, ctypes.windll.kernel32.GetConsoleWindow())
            if hwnd:
                ctypes.windll.user32.ShowWindow(hwnd, 0)
        except Exception:
            pass


def main() -> None:
    # 启动 Web 管理面板：录制引擎（守护线程）+ uvicorn HTTP 服务。
    # 导入 main 模块：触发模块级初始化（FFmpeg 检查、配置读取、备份线程等），
    # 但不进入主循环（因 main() 已被包装为函数）。
    import main
    from src.web_api import create_app
    from src.web_config import read_web_config
    import uvicorn

    config_file = main.config_file
    url_config_file = main.url_config_file
    downloads_root = main.default_path
    logs_dir = os.path.join(main.script_path, "logs")
    os.makedirs(logs_dir, exist_ok=True)

    # 读取 Web 配置（提前读取以便决定是否隐藏控制台）
    web_cfg = read_web_config(config_file)
    host: str = cast(str, web_cfg["web_host"])
    port: int = cast(int, web_cfg["web_port"])

    # 后台模式：隐藏控制台窗口并重定向日志到文件
    if not web_cfg["web_show_console"]:
        _enter_background_mode(logs_dir, host, port)

    # 在守护线程启动录制引擎
    recorder_thread = threading.Thread(
        target=main.main,
        name="recorder-engine",
        daemon=True,
        # non_interactive=True：URL_config 为空时跳过 input() 阻塞，避免守护线程在非交互环境下 EOFError 崩溃
        kwargs={"non_interactive": True},
    )
    recorder_thread.start()
    setattr(main, "_recorder_thread", recorder_thread)  # 供 get_status() 检测存活（I6）
    print(f"[web] 录制引擎已在守护线程启动 (tid={recorder_thread.ident})")

    app = create_app(
        config_file=config_file,
        url_config_file=url_config_file,
        downloads_root=downloads_root,
        logs_dir=logs_dir,
    )

    # uvicorn Server 实例（而非 uvicorn.run）：便于托盘「退出程序」通过设置
    # server.should_exit 触发优雅关闭，而非强制结束进程（避免 ffmpeg 残留）。
    server = uvicorn.Server(uvicorn.Config(app, host=host, port=port, log_level="info"))

    # 系统托盘：Windows 下将控制台窗口改为「最小化到托盘」而非任务栏。
    tray = None
    if web_cfg.get("web_minimize_to_tray", True):
        from src.web_tray import WebConsoleTray
        tray = WebConsoleTray(host=host, port=port, server=server)
        tray.start()

    print(f"[web] Web 管理面板启动中: http://{host}:{port}")
    print(f"[web] 认证: {'开启' if web_cfg['web_auth_enable'] else '关闭'}")
    # 不安全默认值告警（C1）：监听 0.0.0.0 且未启用认证时，局域网内任何人均可访问。
    if not web_cfg["web_auth_enable"] and host == "0.0.0.0":
        print("[web] ⚠️ 警告: Web 面板监听 0.0.0.0 且未启用认证，局域网内任何人均可访问。")
        print("      建议在 config.ini [Web] 节设置 web_auth_enable = true 并配置 web_password，")
        print("      或将 web_host 改为 127.0.0.1 仅限本机访问。")

    # 阻塞运行；托盘「退出程序」或 Ctrl+C 会将 should_exit 置真，serve() 优雅返回。
    # server.serve() 为 async 协程，必须用 asyncio.run 驱动事件循环真正运行，
    # 否则仅生成一个被丢弃的协程对象，Web 服务不会启动。
    asyncio.run(server.serve())

    # 优雅关闭：serve() 返回后趁解释器尚存活主动清理，避免依赖 atexit 在模块部分卸载后才清理。
    # 主动终止 ffmpeg 子进程，杜绝退出后残留孤儿进程。
    try:
        main.cleanup_all_ffmpeg_processes()
    except Exception as e:
        print(f"[web] 清理 ffmpeg 进程失败: {e}")
    try:
        from src.http_clients.async_http import close_all_clients_sync
        close_all_clients_sync()
    except Exception as e:
        print(f"[web] 清理 HTTP 连接池失败: {e}")

    # serve() 已返回（优雅关闭），收起托盘图标，进程随后正常退出。
    if tray is not None:
        tray.stop()


if __name__ == "__main__":
    main()
