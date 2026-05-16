#!/usr/bin/env python3
# -*- encoding: utf-8 -*-
"""
DouyinLiveRecorder 核心包初始化

该包负责直播录制的核心功能，包括：
- 直播数据获取 (spider)
- 直播流解析 (stream)
- 房间信息解析 (room)
- 签名算法 (ab_sign)
- 代理检测 (proxy)
- 工具函数 (utils)
- 日志配置 (logger)
- 初始化 (initializer)

Author: Hmily
GitHub: https://github.com/ihmily
Date: 2023-2025
"""
import os
import sys
from pathlib import Path
from .initializer import check_node

# 包路径配置
current_file_path = Path(__file__).resolve()
current_dir = current_file_path.parent
JS_SCRIPT_PATH = current_dir / 'javascript'  # JavaScript 脚本目录（用于签名算法）

# Node.js 环境配置
execute_dir = os.path.split(os.path.realpath(sys.argv[0]))[0]
node_execute_dir = Path(execute_dir) / 'node'  # Node.js 可执行文件目录
current_env_path = os.environ.get('PATH', '')
os.environ['PATH'] = str(node_execute_dir) + os.pathsep + current_env_path

# 初始化检查 Node.js 环境
check_node()
