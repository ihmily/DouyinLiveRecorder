#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import sys
import time
import configparser
import requests
from loguru import logger
import traceback
from datetime import datetime

# 配置日志输出
logger.remove()
logger.add(sys.stderr, level="INFO")
logger.add("upload_logs/monitor_{time}.log", rotation="1 day", retention="7 days", level="DEBUG")
script_path = os.path.split(os.path.realpath(sys.argv[0]))[0]
config_file = f'{script_path}/config/config.ini'
url_config_file = f'{script_path}/config/URL_config.ini'
device_file = f'{script_path}/.device_id.txt'
downloads_dir = f'{script_path}/downloads'

# 确保必要的目录存在
os.makedirs("upload_logs", exist_ok=True)
os.makedirs("downloads", exist_ok=True)
os.makedirs("config", exist_ok=True)

# 读取设备ID
try:
    with open(device_file, 'r', encoding='utf-8') as f:
        device_id = f.read().strip()
except FileNotFoundError:
    # 如果设备ID文件不存在，生成一个随机ID
    import uuid
    device_id = str(uuid.uuid4())
    with open(device_file, 'w', encoding='utf-8') as f:
        f.write(device_id)
    logger.info(f"生成新设备ID: {device_id}")

# 文件大小监控字典
file_size_history = {}  # 格式: {文件路径: [大小历史记录]}
processed_files = set()  # 已处理的文件集合

def read_config():
    """读取主配置文件"""
    try:
        rcp = configparser.RawConfigParser()
        rcp.read(config_file, encoding='utf-8-sig')
        
        config = {
            'server_url': rcp.get('工作节点设置', 'server_url'),
            'api_key': rcp.get('工作节点设置', 'api_key'),
            'retry_times': int(rcp.get('工作节点设置', 'retry_times')),
            'retry_interval': int(rcp.get('工作节点设置', 'retry_interval')),
            'scan_interval': int(rcp.get('工作节点设置', 'scan_interval', fallback=5)),  # 默认60秒
        }
        
        return config
    except Exception as e:
        logger.error(f"读取配置文件出错: {str(e)}")
        return {
            'server_url': 'http://example.com',
            'api_key': '',
            'retry_times': 3,
            'retry_interval': 5,
            'scan_interval': 60
        }

def read_url_config():
    """读取URL配置文件，返回主播名称和URL的映射"""
    try:
        url_config = {}
        with open(url_config_file, 'r', encoding='utf-8-sig') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('['):  # 跳过空行和ini格式的header
                    continue

                try:
                    parts = line.split(',')
                    if len(parts) >= 3:
                        quality, url, streamer_info = parts[0], parts[1], parts[2]
                        # 从"主播: xxx"中提取主播名称
                        streamer_name = streamer_info.split(':', 1)[1].strip() if ':' in streamer_info else streamer_info.strip()
                        url_config[streamer_name] = url
                        logger.debug(f"已加载主播配置(CSV格式): {streamer_name} -> {url}")
                except Exception as e:
                    logger.warning(f"解析配置行出错: {line}, 错误: {str(e)}")
        
        return url_config
    except Exception as e:
        logger.error(f"读取URL配置文件出错: {str(e)}")
        return {}

def upload_file(file_path, server_url, api_key, record_name, record_url, file_type, max_retries=3, retry_interval=5):
    """上传文件到服务器
    
    Args:
        file_path: 文件路径
        server_url: 服务器URL
        api_key: API密钥
        record_name: 录制名称
        record_url: 录制URL
        file_type: 文件类型
        max_retries: 最大重试次数
        retry_interval: 重试间隔(秒)
        
    Returns:
        bool: 是否上传成功
    """
    if not os.path.exists(file_path):
        logger.error(f"文件不存在: {file_path}")
        return False
    
    file_size = os.path.getsize(file_path) / (1024 * 1024)  # 转换为MB
    file_name = os.path.basename(file_path)
    
    logger.info(f"开始上传文件 {file_name} ({file_size:.2f}MB)")

    headers = {
        'Authorization': f'Bearer {api_key}',
    }

    data = {
        'record_name': record_name,
        'record_url': record_url,
        'file_type': file_type,
        'device_id': device_id,
    }
    
    for attempt in range(max_retries):
        try:
            with open(file_path, 'rb') as f:
                files = {'file': (file_name, f, 'application/octet-stream')}
                response = requests.post(
                    f"{server_url}/api/upload",
                    headers=headers,
                    files=files,
                    data=data,
                    timeout=300  # 设置5分钟超时
                )
            
            if response.status_code in (200, 201):
                logger.info(f"文件 {file_name} 上传成功!")
                return True
            else:
                logger.error(f"上传失败，状态码: {response.status_code}, 响应: {response.text}")
        except Exception as e:
            logger.error(f"上传过程中出错: {str(e)}")
            logger.error(traceback.format_exc())
        
        if attempt < max_retries - 1:
            logger.info(f"将在 {retry_interval} 秒后重试... ({attempt + 1}/{max_retries})")
            time.sleep(retry_interval)
    
    logger.error(f"文件 {file_name} 上传失败，已达到最大重试次数")
    return False

def scan_and_process_videos():
    """扫描下载目录并处理视频文件，支持递归扫描嵌套目录"""
    try:
        config = read_config()
        streamer_config = read_url_config()
        
        if not streamer_config:
            logger.warning("未找到有效的主播配置，跳过此次扫描")
            return

        # 递归扫描下载目录中的所有文件
        for root, dirs, files in os.walk(downloads_dir):
            for filename in files:
                file_path = os.path.join(root, filename)
                
                # 跳过已处理的文件
                if file_path in processed_files:
                    continue
                
                # 检查文件是否与任何主播匹配
                matched_streamer = None
                for streamer_name in streamer_config:
                    if filename.startswith(streamer_name):
                        matched_streamer = streamer_name
                        break
                
                if matched_streamer is None:
                    continue  # 没有匹配的主播，跳过此文件
                
                # 更新文件大小历史
                current_size = os.path.getsize(file_path)
                if file_path not in file_size_history:
                    file_size_history[file_path] = []
                file_size_history[file_path].append(current_size)
                
                # 保留最近3次的记录
                if len(file_size_history[file_path]) > 3:
                    file_size_history[file_path] = file_size_history[file_path][-3:]
                
                # 检查文件大小是否稳定（连续3次相同）
                size_history = file_size_history[file_path]
                if len(size_history) == 3 and size_history[0] == size_history[1] == size_history[2] and size_history[0] > 0:
                    logger.info(f"文件 {filename} 大小稳定，准备上传")
                    
                    # 获取文件类型（后缀名）
                    file_type = os.path.splitext(filename)[1][1:].upper()
                    record_url = streamer_config[matched_streamer]
                    
                    # 上传文件
                    if upload_file(
                        file_path,
                        config['server_url'],
                        config['api_key'],
                        matched_streamer,  # 使用主播名称作为录制名称
                        record_url,
                        file_type,
                        max_retries=config['retry_times'],
                        retry_interval=config['retry_interval']
                    ):
                        # 上传成功，将文件标记为已处理
                        processed_files.add(file_path)
                        # 移除文件大小历史记录
                        file_size_history.pop(file_path, None)
                        logger.info(f"文件 {filename} 处理完成")
    
    except Exception as e:
        logger.error(f"扫描处理文件时出错: {str(e)}")
        logger.error(traceback.format_exc())

def monitor_loop():
    """持续监控视频文件的主循环"""
    config = read_config()
    scan_interval = config.get('scan_interval', 5)
    
    logger.info(f"启动视频监控服务，扫描间隔: {scan_interval}秒")
    
    while True:
        try:
            scan_and_process_videos()
            time.sleep(scan_interval)
        except KeyboardInterrupt:
            logger.info("收到中断信号，停止监控服务")
            break
        except Exception as e:
            logger.error(f"监控循环发生错误: {str(e)}")
            logger.error(traceback.format_exc())
            # 发生错误后等待一段时间再继续
            time.sleep(10)

def main():
    """主函数"""
    try:
        # 启动监控循环
        monitor_loop()
        
        return 0
    except Exception as e:
        logger.error(f"程序运行出错: {str(e)}")
        logger.error(traceback.format_exc())
        return 1

if __name__ == "__main__":
    sys.exit(main()) 