# -*- coding: utf-8 -*-
# 同步 HTTP 客户端模块 - 提供同步 HTTP 请求功能

import gzip
import urllib.parse
import urllib.error
import requests
import ssl
import json
import urllib.request
from ..logger import logger

# 禁用代理的处理器（本地请求不使用代理）
no_proxy_handler = urllib.request.ProxyHandler({})

# SSL 上下文配置（禁用证书验证）
ssl_context = ssl.create_default_context()
ssl_context.check_hostname = False
ssl_context.verify_mode = ssl.CERT_NONE

# 构建自定义 URL  opener（使用禁用代理和 SSL 上下文）
opener = urllib.request.build_opener(no_proxy_handler, urllib.request.HTTPSHandler(context=ssl_context))

OptionalStr = str | None
OptionalDict = dict | None


def sync_req(
        url: str,
        proxy_addr: OptionalStr = None,
        headers: OptionalDict = None,
        data: dict | bytes | None = None,
        json_data: dict | list | None = None,
        timeout: int = 20,
        redirect_url: bool = False,
        abroad: bool = False,
        content_encoding: str = 'utf-8'
) -> str:
    # 同步 HTTP 请求函数，支持 GET/POST、代理、重定向、gzip 解压等功能
    if headers is None:
        headers = {}
    try:
        if proxy_addr:
            # 使用代理的请求
            proxies = {
                'http': proxy_addr,
                'https': proxy_addr
            }
            if data or json_data:
                # POST 请求（带代理）
                response = requests.post(
                    url, data=data, json=json_data, headers=headers, proxies=proxies, timeout=timeout,
                    verify=False
                )
            else:
                # GET 请求（带代理）
                response = requests.get(url, headers=headers, proxies=proxies, timeout=timeout, verify=False)
            if redirect_url:
                return response.url
            resp_str = response.text
        else:
            # 不使用代理的请求
            # 处理请求数据编码
            if data and not isinstance(data, bytes):
                if isinstance(data, dict):
                    # dict 类型转换为 URL 编码
                    data = urllib.parse.urlencode(data).encode(content_encoding)
                else:
                    # 其他类型转换为字符串再编码
                    data = str(data).encode(content_encoding)
            if json_data and isinstance(json_data, (dict, list)):
                # JSON 数据编码
                data = json.dumps(json_data).encode(content_encoding)

            # 创建请求对象
            req = urllib.request.Request(url, data=data, headers=headers)

            try:
                if abroad:
                    # 海外请求（使用 SSL 上下文）
                    response = urllib.request.urlopen(req, timeout=timeout, context=ssl_context)
                else:
                    # 本地请求（使用自定义 opener）
                    response = opener.open(req, timeout=timeout)
                if redirect_url:
                    return response.url
                
                # 处理响应编码和 gzip 解压
                resp_encoding = response.info().get('Content-Encoding')
                try:
                    if resp_encoding == 'gzip':
                        # gzip 解压
                        resp_bytes = gzip.decompress(response.read())
                        resp_str = resp_bytes.decode(content_encoding)
                    else:
                        # 普通解码
                        resp_str = response.read().decode(content_encoding)
                finally:
                    response.close()

            except urllib.error.HTTPError as e:
                # HTTP 错误处理
                if e.code == 400:
                    resp_str = e.read().decode(content_encoding)
                else:
                    raise
            except urllib.error.URLError as e:
                # URL 错误记录日志
                logger.warning(f"URL Error: {e}")
                raise
            except Exception as e:
                # 其他错误记录日志
                logger.error(f"An error occurred: {e}")
                raise

    except Exception as e:
        resp_str = str(e)

    return resp_str
