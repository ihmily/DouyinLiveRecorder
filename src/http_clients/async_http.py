# -*- coding: utf-8 -*-
import httpx
from typing import Dict, Any
from .. import utils
from ..logger import logger

OptionalStr = str | None
OptionalDict = Dict[str, Any] | None

# 全局连接池配置，提高 HTTP 请求性能
_httpx_limits = httpx.Limits(max_connections=100, max_keepalive_connections=20)

async def async_req(
        url: str,
        proxy_addr: OptionalStr = None,
        headers: OptionalDict = None,
        data: dict | str | bytes | None = None,
        json_data: dict | list | None = None,
        timeout: int = 20,
        redirect_url: bool = False,
        return_cookies: bool = False,
        include_cookies: bool = False,
        abroad: bool = False,
        content_encoding: str = 'utf-8',
        verify: bool = False,
        http2: bool = True
) -> str | dict | tuple:
    if headers is None:
        headers = {}
    try:
        proxy_addr = utils.handle_proxy_addr(proxy_addr)
        async with httpx.AsyncClient(
            proxy=proxy_addr,
            timeout=timeout,
            verify=verify,
            http2=http2,
            limits=_httpx_limits
        ) as client:
            if data or json_data:
                if isinstance(data, (bytes, bytearray, memoryview)):
                    # 将 memoryview 转换为 bytes
                    content_data = bytes(data)
                    response = await client.post(url, content=content_data, json=json_data, headers=headers)
                elif isinstance(data, str):
                    response = await client.post(url, content=data, json=json_data, headers=headers)
                else:
                    # data 是 dict 或 None
                    response = await client.post(url, data=data, json=json_data, headers=headers)
            else:
                response = await client.get(url, headers=headers, follow_redirects=True)

        if redirect_url:
            return str(response.url)
        elif return_cookies:
            cookies_dict = {name: value for name, value in response.cookies.items()}
            return (response.text, cookies_dict) if include_cookies else cookies_dict
        else:
            resp_str = response.text
    except Exception as e:
        resp_str = str(e)

    return resp_str


async def get_response_status(url: str, proxy_addr: OptionalStr = None, headers: OptionalDict = None,
                              timeout: int = 10, abroad: bool = False, verify: bool = False, http2=False) -> bool:

    try:
        proxy_addr = utils.handle_proxy_addr(proxy_addr)
        async with httpx.AsyncClient(
            proxy=proxy_addr,
            timeout=timeout,
            verify=verify,
            http2=http2,
            limits=_httpx_limits
        ) as client:
            response = await client.head(url, headers=headers, follow_redirects=True)
            return response.status_code == 200
    except Exception as e:
        logger.debug(e)
    return False
