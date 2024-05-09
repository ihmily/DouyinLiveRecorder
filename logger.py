# -*- coding: utf-8 -*-

import os
import sys

from loguru import logger

script_path = os.path.split(os.path.realpath(sys.argv[0]))[0]
logger.add(
    f"{script_path}/logs/PlayURL.log",
    level="INFO",
    format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {message}",
    filter=lambda i: i["level"].name == "INFO",
    serialize=False,
    enqueue=True,
    retention=1,
    rotation="300 KB",
)

logger.add(
    f"{script_path}/logs/DouyinLiveRecorder.log",
    level="WARNING",
    serialize=False,
    enqueue=True,
    retention=1,
    rotation="100 KB",
)
