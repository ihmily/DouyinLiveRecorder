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

# 确保项目根在 sys.path
_script_dir = os.path.dirname(os.path.realpath(__file__))
if _script_dir not in sys.path:
    sys.path.insert(0, _script_dir)


def main() -> None:
    """启动 Web 管理面板：录制引擎（守护线程）+ uvicorn HTTP 服务。"""
    # 导入 main 模块：触发模块级初始化（FFmpeg 检查、配置读取、备份线程等），
    # 但不进入主循环（因 main() 已被包装为函数）。
    import main
    from src.web_api import create_app
    from src.web_config import read_web_config
    import uvicorn

    # 在守护线程启动录制引擎
    recorder_thread = threading.Thread(target=main.main, name="recorder-engine", daemon=True)
    recorder_thread.start()
    print(f"[web] 录制引擎已在守护线程启动 (tid={recorder_thread.ident})")

    # 读取 Web 配置
    config_file = main.config_file
    url_config_file = main.url_config_file
    downloads_root = main.default_path
    logs_dir = os.path.join(main.script_path, "logs")
    os.makedirs(logs_dir, exist_ok=True)

    web_cfg = read_web_config(config_file)
    host = web_cfg["web_host"]
    port = web_cfg["web_port"]

    app = create_app(
        config_file=config_file,
        url_config_file=url_config_file,
        downloads_root=downloads_root,
        logs_dir=logs_dir,
    )

    print(f"[web] Web 管理面板启动中: http://{host}:{port}")
    print(f"[web] 认证: {'开启' if web_cfg['web_auth_enable'] else '关闭'}")
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
