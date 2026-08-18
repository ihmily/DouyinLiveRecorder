# -*- coding: utf-8 -*-
# HTTP 客户端共享运行时配置

# SSL 证书验证全局开关
# 默认启用（True，安全优先）。运行时由主配置统一覆盖（见 main.py 的 set_ssl_verify）。
# 由 async_http / sync_http 在发起请求时按属性读取，故修改需通过 set_ssl_verify()。
ssl_verify: bool = True

# 平台级 SSL 证书验证覆盖（可选关闭）。键为平台标识（如「虎牙直播」），值为是否校验。
# 默认空：所有平台沿用全局 ssl_verify（安全优先）。仅当某平台 CDN 存在证书主机名不匹配等
# 不可调和问题、且用户显式开启时才写入（属安全降级，默认不写）。
# 读取一律走 get_effective_ssl_verify(platform)，保证校验器 / ffmpeg / 直下三路一致。
ssl_verify_platform_overrides: dict[str, bool] = {}


def set_ssl_verify(value: bool) -> None:
    # 由主配置统一设置 SSL 证书验证开关
    global ssl_verify
    ssl_verify = value


def set_platform_ssl_verify(platform: str, value: bool) -> None:
    # 设置某平台的 SSL 证书验证覆盖（如虎牙 TX CDN 边缘节点证书主机名不匹配时可选关闭）
    ssl_verify_platform_overrides[platform] = value


def get_effective_ssl_verify(platform: str | None = None) -> bool:
    # 返回某平台实际应使用的 SSL 校验开关：平台有覆盖取覆盖值，否则取全局默认（True，安全优先）
    if platform and platform in ssl_verify_platform_overrides:
        return ssl_verify_platform_overrides[platform]
    return ssl_verify
