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
from datetime import datetime

# 确保项目根在 sys.path
_script_dir = os.path.dirname(os.path.realpath(__file__))
if _script_dir not in sys.path:
    sys.path.insert(0, _script_dir)


def _enter_background_mode(logs_dir: str, host: str, port: int) -> None:
    # 进入后台运行模式：隐藏控制台窗口，将输出重定向到日志文件。
    # Windows 下隐藏控制台窗口（SW_HIDE）；其他平台仅重定向输出。
    # 日志写入 logs/web_console.log，可通过 Web 面板或任务管理器管理程序。
    log_path = os.path.join(logs_dir, "web_console.log")

    # 重定向前先向控制台输出提示（窗口即将隐藏）
    print("[web] 进入后台运行模式，控制台窗口将隐藏")
    print(f"[web] 日志文件: {log_path}")
    print(f"[web] 访问地址: http://{host}:{port}")
    sys.stdout.flush()

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
            hwnd = ctypes.windll.kernel32.GetConsoleWindow()
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
    host = web_cfg["web_host"]
    port = web_cfg["web_port"]

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
    main._recorder_thread = recorder_thread  # 供 get_status() 检测存活（I6）
    print(f"[web] 录制引擎已在守护线程启动 (tid={recorder_thread.ident})")

    app = create_app(
        config_file=config_file,
        url_config_file=url_config_file,
        downloads_root=downloads_root,
        logs_dir=logs_dir,
    )

    print(f"[web] Web 管理面板启动中: http://{host}:{port}")
    print(f"[web] 认证: {'开启' if web_cfg['web_auth_enable'] else '关闭'}")
    # 不安全默认值告警（C1）：监听 0.0.0.0 且未启用认证时，局域网内任何人均可访问。
    if not web_cfg["web_auth_enable"] and str(host) == "0.0.0.0":
        print("[web] ⚠️ 警告: Web 面板监听 0.0.0.0 且未启用认证，局域网内任何人均可访问。")
        print("      建议在 config.ini [Web] 节设置 web_auth_enable = true 并配置 web_password，")
        print("      或将 web_host 改为 127.0.0.1 仅限本机访问。")
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
