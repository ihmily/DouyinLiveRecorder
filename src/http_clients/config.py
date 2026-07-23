# -*- coding: utf-8 -*-
# HTTP 客户端共享运行时配置

# SSL 证书验证全局开关
# 默认禁用（False）以兼容历史行为，运行时由主配置统一覆盖。
# 由 async_http / sync_http 在发起请求时按属性读取，故修改需通过 set_ssl_verify()。
ssl_verify: bool = False


def set_ssl_verify(value: bool) -> None:
    # 由主配置统一设置 SSL 证书验证开关
    global ssl_verify
    ssl_verify = bool(value)
