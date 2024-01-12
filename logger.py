import os

from loguru import logger

log_path = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "logs/DouyinLiveRecorder.log"
)
# 每天日志自动分文件
logger.add(log_path, rotation="12:00")