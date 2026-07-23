#!/usr/bin/env python3
# -*- encoding: utf-8 -*-
# DouyinLiveRecorder 核心包初始化 - 负责直播录制的核心功能

# Author: Hmily
# GitHub: https://github.com/ihmily
# Date: 2023-2025

import os
import sys
from pathlib import Path
from .initializer import check_node

# 包路径配置
current_file_path = Path(__file__).resolve()
current_dir = current_file_path.parent
JS_SCRIPT_PATH = current_dir / 'javascript'  # JavaScript 脚本目录（用于签名算法）

# Node.js 环境配置
# execute_dir 需指向项目根目录（主脚本所在目录），Node.js 安装在根目录下的 node/ 文件夹
execute_dir = os.path.split(os.path.realpath(sys.argv[0]))[0]
node_execute_dir = Path(execute_dir) / 'node'  # Node.js 可执行文件目录
current_env_path = os.environ.get('PATH', '')
# 仅在目录存在且未添加时更新 PATH，避免污染或重复追加
node_dir_str = str(node_execute_dir)
if node_execute_dir.is_dir() and node_dir_str not in current_env_path.split(os.pathsep):
    os.environ['PATH'] = node_dir_str + os.pathsep + current_env_path

# 初始化检查 Node.js 环境
check_node()
