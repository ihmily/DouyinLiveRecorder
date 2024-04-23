# -*- coding: utf-8 -*-

from loguru import logger

logger.add(
    "./logs/PlayURL.log",
    level="INFO",
    format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {message}",
    filter=lambda i: i["level"].name == "INFO",
    serialize=False,
    enqueue=True,
    rotation="12:00",
    retention="10 days",
)

logger.add(
    "./logs/DouyinLiveRecorder.log",
    level="WARNING",
    serialize=False,
    enqueue=True,
    rotation="12:00",
    retention="10 days",
)

