#!/usr/bin/env python3
# -*- encoding: utf-8 -*-
# DouyinLiveRecorder 核心包初始化 - 负责直播录制的核心功能

# Author: Hmily
# GitHub: https://github.com/ihmily
# Date: 2023-2025

import os
from pathlib import Path

from .node_install import check_node

# 包路径配置
current_file_path = Path(__file__).resolve()
current_dir = current_file_path.parent
JS_SCRIPT_PATH = current_dir / "javascript"  # JavaScript 脚本目录（用于签名算法）

# Node.js 环境配置
# execute_dir 需指向项目根目录（主脚本所在目录），Node.js 安装在根目录下的 node/ 文件夹
# 冻结后资源统一在 _internal/，故用 src.logger.script_path（即 _app_root() 的结果）统一收敛，
# 复用 logger 已导出的公开符号，避免跨模块引用私有符号 _app_root
from .logger import script_path

execute_dir = script_path
node_execute_dir = Path(execute_dir) / "node"  # Node.js 可执行文件目录
current_env_path = os.environ.get("PATH", "")
# 仅在目录存在且未添加时更新 PATH，避免污染或重复追加
node_dir_str = str(node_execute_dir)
if node_execute_dir.is_dir() and node_dir_str not in current_env_path.split(os.pathsep):
    os.environ["PATH"] = node_dir_str + os.pathsep + current_env_path

# 导入期运行时检查开关：测试/CI/静态工具导入 src 包时不应触发 node 子进程检查
# 或自动安装副作用（受限环境下子进程管道偶发失败还会导致导入崩溃）。
# 生产运行不设置该变量，行为不变。
if os.environ.get("DOUYIN_SKIP_RUNTIME_CHECK", "").strip().lower() not in ("1", "true", "yes"):
    # 初始化检查 Node.js 环境（仅为副作用：缺失则自动安装，返回值此处无需处理）
    _ = check_node()
