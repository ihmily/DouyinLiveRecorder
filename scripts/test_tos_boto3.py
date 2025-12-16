#!/usr/bin/env python3
"""
测试火山引擎 TOS bucket 可用性（使用 boto3 S3 兼容接口）
"""

import os
import sys
import configparser

# 禁用代理（内网访问不需要代理）
os.environ.pop('http_proxy', None)
os.environ.pop('https_proxy', None)
os.environ.pop('HTTP_PROXY', None)
os.environ.pop('HTTPS_PROXY', None)

import boto3
from botocore.config import Config

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
        's3_endpoint': config.get('tos', 's3_endpoint'),
        'region': config.get('tos', 'region'),
        'bucket': config.get('tos', 'bucket'),
        'access_key': config.get('tos', 'access_key'),
        'secret_key': config.get('tos', 'secret_key'),
    }


def test_bucket():
    """测试 bucket 连接和基本操作"""
    cfg = load_config()
    endpoint = f"https://{cfg['s3_endpoint']}"

    # 创建 S3 客户端 - 使用 virtual host style
    s3_client = boto3.client(
        's3',
        endpoint_url=endpoint,
        aws_access_key_id=cfg['access_key'],
        aws_secret_access_key=cfg['secret_key'],
        region_name=cfg['region'],
        config=Config(
            s3={'addressing_style': 'virtual'},
            signature_version='s3v4'
        )
    )

    print(f"正在测试 bucket: {cfg['bucket']}")
    print(f"Endpoint: {endpoint}")
    print("-" * 50)

    # 测试1: 检查 bucket 是否存在
    try:
        s3_client.head_bucket(Bucket=cfg['bucket'])
        print("✓ Bucket 存在且可访问")
    except Exception as e:
        print(f"✗ Bucket 访问失败: {e}")
        return False

    # 测试2: 列出 bucket 中的对象（最多5个）
    try:
        response = s3_client.list_objects_v2(Bucket=cfg['bucket'], MaxKeys=5)
        count = response.get('KeyCount', 0)
        print(f"✓ 列出对象成功，当前有 {count} 个对象（最多显示5个）")

        if 'Contents' in response:
            for obj in response['Contents']:
                print(f"  - {obj['Key']} ({obj['Size']} bytes)")
    except Exception as e:
        print(f"✗ 列出对象失败: {e}")
        return False

    # 测试3: 上传测试文件
    test_key = "test_connection_boto3.txt"
    test_content = "TOS connection test via boto3"
    try:
        s3_client.put_object(
            Bucket=cfg['bucket'],
            Key=test_key,
            Body=test_content.encode('utf-8')
        )
        print(f"✓ 上传测试文件成功: {test_key}")
    except Exception as e:
        print(f"✗ 上传测试文件失败: {e}")
        return False

    # 测试4: 读取测试文件
    try:
        response = s3_client.get_object(Bucket=cfg['bucket'], Key=test_key)
        content = response['Body'].read().decode('utf-8')
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
        s3_client.delete_object(Bucket=cfg['bucket'], Key=test_key)
        print(f"✓ 删除测试文件成功")
    except Exception as e:
        print(f"✗ 删除测试文件失败: {e}")
        return False

    print("-" * 50)
    print("所有测试通过！Bucket 可用（boto3）。")
    return True


if __name__ == "__main__":
    test_bucket()
