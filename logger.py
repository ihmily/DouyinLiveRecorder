# -*- coding: utf-8 -*-

from loguru import logger

# 每天日志自动分文件
logger.add("./logs/DouyinLiveRecorder.log", rotation="12:00")
