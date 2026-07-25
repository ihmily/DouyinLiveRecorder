#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 日志配置模块 - 基于 Loguru，控制台彩色输出 + 日志文件轮转存储

import sys
import configparser
from pathlib import Path
from loguru import logger

# 移除默认处理器
logger.remove()

# 控制台日志格式（彩色）
custom_format = "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level: <8}</level> - <level>{message}</level>"

# 添加控制台输出（无论是否启用日志文件，控制台输出始终保留）
logger.add(
    sink=sys.stderr,
    format=custom_format,
    level="DEBUG",
    colorize=True,
    enqueue=True
)

# 使用模块文件所在目录而非 sys.argv[0]，避免被导入时定位错误
script_path = str(Path(__file__).resolve().parent.parent)

# 读取配置：是否将日志导出到 logs 文件夹
# 注意：logger.py 在 main.py 读取配置之前即被导入（通过 src.utils 传递引入），
# 因此这里直接用 configparser 读取 config.ini，避免依赖 main.py 的执行顺序
# 默认启用日志文件，以保持向后兼容行为
_log_to_file: bool = True
try:
    _cfg_parser = configparser.RawConfigParser()
    _cfg_parser.read(f'{script_path}/config/config.ini', encoding='utf-8-sig')
    _log_to_file = _cfg_parser.get('录制设置', '是否启用日志文件(是/否)').strip() != '否'
except (configparser.NoSectionError, configparser.NoOptionError):
    # 配置项缺失时保持默认启用（向后兼容）
    pass
except Exception:
    # 任何读取异常都不应影响日志模块初始化
    pass

if _log_to_file:
    # DEBUG 级别日志文件（排除 INFO）
    logger.add(
        f"{script_path}/logs/streamget.log",
        level="DEBUG",
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} - {message}",
        filter=lambda i: i["level"].name != "INFO",
        serialize=False,
        enqueue=True,
        retention=3,
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
        retention=3,
        rotation="300 KB",
        encoding='utf-8'
    )
