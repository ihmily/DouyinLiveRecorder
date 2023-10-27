import logging
import os
import re
import sys
import time

from dy import dy

url_config_file = './config/URL_config.ini'
encoding = 'utf-8-sig'
if __name__ == '__main__':
    LOG_FORMAT = "%(asctime)s - %(levelname)s - %(message)s"
    logging.basicConfig(level=logging.DEBUG, format=LOG_FORMAT)

    # 获取命令行参数
    arguments = sys.argv
    url = arguments[1]
    name = arguments[2]
    re_datatime = time.strftime('%Y-%m-%d %H:%M:%S')
    filepath = f"/Users/ginhoor/Downloads/Source/Comments/{name}_{re_datatime}.log"
    dy.parseLiveRoomUrl(url, filepath)
