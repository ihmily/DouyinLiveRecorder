# -*- coding: utf-8 -*-
import gzip
import urllib.parse
import urllib.error
import requests
import ssl
import json
import urllib.request
from ..logger import logger

no_proxy_handler = urllib.request.ProxyHandler({})
ssl_context = ssl.create_default_context()
ssl_context.check_hostname = False
ssl_context.verify_mode = ssl.CERT_NONE
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
    if headers is None:
        headers = {}
    try:
        if proxy_addr:
            proxies = {
                'http': proxy_addr,
                'https': proxy_addr
            }
            if data or json_data:
                response = requests.post(
                    url, data=data, json=json_data, headers=headers, proxies=proxies, timeout=timeout,
                    verify=False
                )
            else:
                response = requests.get(url, headers=headers, proxies=proxies, timeout=timeout, verify=False)
            if redirect_url:
                return response.url
            resp_str = response.text
        else:
            if data and not isinstance(data, bytes):
                if isinstance(data, dict):
                    data = urllib.parse.urlencode(data).encode(content_encoding)
                else:
                    data = str(data).encode(content_encoding)
            if json_data and isinstance(json_data, (dict, list)):
                data = json.dumps(json_data).encode(content_encoding)

            req = urllib.request.Request(url, data=data, headers=headers)

            try:
                if abroad:
                    response = urllib.request.urlopen(req, timeout=timeout, context=ssl_context)
                else:
                    response = opener.open(req, timeout=timeout)
                if redirect_url:
                    return response.url
                resp_encoding = response.info().get('Content-Encoding')
                try:
                    if resp_encoding == 'gzip':
                        resp_bytes = gzip.decompress(response.read())
                        resp_str = resp_bytes.decode(content_encoding)
                    else:
                        resp_str = response.read().decode(content_encoding)
                finally:
                    response.close()

            except urllib.error.HTTPError as e:
                if e.code == 400:
                    resp_str = e.read().decode(content_encoding)
                else:
                    raise
            except urllib.error.URLError as e:
                logger.warning(f"URL Error: {e}")
                raise
            except Exception as e:
                logger.error(f"An error occurred: {e}")
                raise

    except Exception as e:
        resp_str = str(e)

    return resp_str
