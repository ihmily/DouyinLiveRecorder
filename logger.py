# -*- coding: utf-8 -*-

from loguru import logger
import os, sys

script_path = os.path.split(os.path.realpath(sys.argv[0]))[0]
logger.add(
    f"{script_path}/logs/PlayURL.log",
    level="INFO",
    format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {message}",
    filter=lambda i: i["level"].name == "INFO",
    serialize=False,
    enqueue=True,
    rotation="12:00",
    retention="10 days",
)

logger.add(
    f"{script_path}/logs/DouyinLiveRecorder.log",
    level="WARNING",
    serialize=False,
    enqueue=True,
    rotation="12:00",
    retention="10 days",
)

