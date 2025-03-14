# -*- coding: utf-8 -*-

import os
import sys

custom_format = "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level: <8}</level> - <level>{message}</level>"
os.environ["LOGURU_FORMAT"] = custom_format
from loguru import logger

script_path = os.path.split(os.path.realpath(sys.argv[0]))[0]

logger.add(
    f"{script_path}/logs/streamget.log",
    level="DEBUG",
    format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} - {message}",
    # filter=False, #lambda i: i["level"].name != "DEBUG",
    serialize=False,
    enqueue=True,
    retention=3,
    rotation="50000 KB",
    encoding='utf-8'
)

logger.add(
    f"{script_path}/logs/PlayURL.log",
    level="DEBUG",
    format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {message}",
    filter=lambda i: i["level"].name == "ERROR",
    serialize=False,
    enqueue=True,
    retention=3,
    rotation="10000 KB",
    encoding='utf-8'
)
