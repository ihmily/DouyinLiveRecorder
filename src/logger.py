#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 日志配置模块 - 基于 Loguru，控制台彩色输出 + 日志文件轮转存储

import os
import sys
from loguru import logger

# 移除默认处理器
logger.remove()

# 控制台日志格式（彩色）
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

# DEBUG 级别日志文件（排除 INFO）
logger.add(
    f"{script_path}/logs/streamget.log",
    level="DEBUG",
    format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} - {message}",
    filter=lambda i: i["level"].name != "INFO",
    serialize=False,
    enqueue=True,
    retention=1,
    rotation="300 KB",
    encoding='utf-8'
)

# INFO 级别日志文件（直播流 URL 等）
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
