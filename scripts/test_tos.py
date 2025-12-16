#!/usr/bin/env python3
"""
测试火山引擎 TOS bucket 可用性（使用官方 SDK）
"""

import os
import sys
import configparser

# 禁用代理（内网访问不需要代理）
os.environ.pop('http_proxy', None)
os.environ.pop('https_proxy', None)
os.environ.pop('HTTP_PROXY', None)
os.environ.pop('HTTPS_PROXY', None)

import tos

# 获取配置文件路径
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)
CONFIG_PATH = os.path.join(PROJECT_DIR, 'config', 'tos_credentials.ini')


def load_config():
    """从配置文件加载 TOS 凭证"""
    if not os.path.exists(CONFIG_PATH):
        print(f"错误: 配置文件不存在: {CONFIG_PATH}")
        sys.exit(1)

    config = configparser.ConfigParser()
    config.read(CONFIG_PATH)

    return {
        'endpoint': config.get('tos', 'endpoint'),
        'region': config.get('tos', 'region'),
        'bucket': config.get('tos', 'bucket'),
        'access_key': config.get('tos', 'access_key'),
        'secret_key': config.get('tos', 'secret_key'),
    }


def test_bucket():
    """测试 bucket 连接和基本操作"""
    cfg = load_config()

    # 创建 TOS 客户端
    client = tos.TosClientV2(
        ak=cfg['access_key'],
        sk=cfg['secret_key'],
        endpoint=cfg['endpoint'],
        region=cfg['region']
    )

    print(f"正在测试 bucket: {cfg['bucket']}")
    print(f"Endpoint: {cfg['endpoint']}")
    print("-" * 50)

    # 测试1: 检查 bucket 是否存在
    try:
        result = client.head_bucket(cfg['bucket'])
        print(f"✓ Bucket 存在且可访问 (region: {result.region})")
    except tos.exceptions.TosClientError as e:
        print(f"✗ 客户端错误: {e.message}")
        return False
    except tos.exceptions.TosServerError as e:
        print(f"✗ 服务端错误: {e.code} - {e.message}")
        return False

    # 测试2: 列出 bucket 中的对象（最多5个）
    try:
        result = client.list_objects(cfg['bucket'], max_keys=5)
        count = len(result.contents) if result.contents else 0
        print(f"✓ 列出对象成功，当前有 {count} 个对象（最多显示5个）")

        if result.contents:
            for obj in result.contents:
                print(f"  - {obj.key} ({obj.size} bytes)")
    except Exception as e:
        print(f"✗ 列出对象失败: {e}")
        return False

    # 测试3: 上传测试文件
    test_key = "test_connection.txt"
    test_content = "TOS connection test"
    try:
        client.put_object(cfg['bucket'], test_key, content=test_content)
        print(f"✓ 上传测试文件成功: {test_key}")
    except Exception as e:
        print(f"✗ 上传测试文件失败: {e}")
        return False

    # 测试4: 读取测试文件
    try:
        result = client.get_object(cfg['bucket'], test_key)
        content = result.read().decode('utf-8')
        if content == test_content:
            print(f"✓ 读取测试文件成功，内容正确")
        else:
            print(f"✗ 读取内容不匹配")
            return False
    except Exception as e:
        print(f"✗ 读取测试文件失败: {e}")
        return False

    # 测试5: 删除测试文件
    try:
        client.delete_object(cfg['bucket'], test_key)
        print(f"✓ 删除测试文件成功")
    except Exception as e:
        print(f"✗ 删除测试文件失败: {e}")
        return False

    print("-" * 50)
    print("所有测试通过！Bucket 可用。")
    return True


if __name__ == "__main__":
    test_bucket()
