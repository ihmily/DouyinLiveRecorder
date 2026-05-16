#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
日志配置模块

使用 Loguru 库配置项目日志系统，包括：
- 控制台彩色输出到 stderr
- 日志文件分级存储（DEBUG 和 INFO 级别
- 日志文件自动轮转和压缩

日志分级：
- streamget.log: DEBUG 记录调试信息（除 INFO 级别
- PlayURL.log: 仅记录 INFO 级别信息

Author: Hmily
GitHub: https://github.com/ihmily
Date: 2023-2025
"""
import os
import sys
from loguru import logger

# 移除默认的日志处理器
logger.remove()

# 控制台日志格式：彩色输出
custom_format = "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level: <8}</level> - <level>{message}</level>"

# 添加控制台输出
logger.add(
    sink=sys.stderr,
    format=custom_format,
    level="DEBUG",
    colorize=True,
    enqueue=True
)

script_path = os.path.split(os.path.realpath(sys.argv[0]))[0]

# DEBUG 级别日志文件：记录调试信息（排除 INFO 级别
logger.add(
    f"{script_path}/logs/streamget.log",
    level="DEBUG",
    format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} - {message}",
    filter=lambda i: i["level"].name != "INFO",
    serialize=False,
    enqueue=True,
    retention=1,  # 保留 1 个文件
    rotation="300 KB",  # 单文件 300KB 后轮转
    encoding='utf-8'
)

# INFO 级别日志文件：仅记录 INFO 级别信息（直播流 URL 等
logger.add(
    f"{script_path}/logs/PlayURL.log",
    level="INFO",
    format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {message}",
    filter=lambda i: i["level"].name == "INFO",
    serialize=False,
    enqueue=True,
    retention=1,
    rotation="300 KB",
    encoding='utf-8'
)
