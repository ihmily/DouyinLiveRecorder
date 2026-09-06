# -*- coding: utf-8 -*-
# HTTP 客户端共享运行时配置

# SSL 证书验证全局开关
# 默认启用（True，安全优先）。已整合进「是否启用https录制」：开启 https 录制时由
# main.py 置 False（禁用证书验证，保证 https 拉流不被 CDN 证书问题阻断），关闭时
# 置 True（http 拉流，恢复默认严格校验）。由 async_http / sync_http 在发起请求时
# 按属性读取，故修改需通过 set_ssl_verify()。
ssl_verify: bool = True

# 平台级 SSL 证书验证覆盖。键为平台标识（如「虎牙直播」），值为是否校验。
# FFmpeg 9.0 起 TLS 证书验证默认开启（8.0 预告、9.0 落地），http 录制模式下
# https-only 流/接口也会被默认校验证书——「禁用SSL证书验证的平台」因此重新具备
# 实际作用：证书异常平台（虎牙 TX CDN 主机名不匹配等）经此列表跳过校验。
# 读取一律走 get_effective_ssl_verify(platform)，保证校验器 / ffmpeg /
# 直下三路一致。
ssl_verify_platform_overrides: dict[str, bool] = {}

# 「是否启用https录制」整合开关（合并原「是否强制启用https录制」与
# 「是否禁用SSL证书验证(是/否)」）：开启 = https 拉流 + 禁用 SSL 证书验证；
# 关闭 = http 拉流 + 恢复默认证书校验。运行时由主循环热更新。
https_recording_enabled: bool = False


def set_ssl_verify(value: bool) -> None:
    # 由主配置统一设置 SSL 证书验证开关
    global ssl_verify
    ssl_verify = value


def set_https_recording(value: bool) -> None:
    # 由主配置统一设置「是否启用https录制」（整合开关）。
    # 注意：全局 ssl_verify 由 main.py 显式联动设置（set_ssl_verify(not value)），
    # 此处仅更新门控标志，保持两者可独立测试。
    global https_recording_enabled
    https_recording_enabled = value


def set_platform_ssl_verify(platform: str, value: bool) -> None:
    # 设置某平台的 SSL 证书验证覆盖（True=校验 / False=跳过校验）。
    ssl_verify_platform_overrides[platform] = value


def get_effective_ssl_verify(platform: str | None = None) -> bool:
    # 返回某平台实际应使用的 SSL 校验开关。
    # 「禁用SSL证书验证的平台」仅在 SSL 证书需要验证时才生效——即全局开关
    # ssl_verify=True（http 录制模式，恢复默认严格校验）时平台覆盖参与读取：
    #   - ssl_verify=True 且平台在禁用列表 → False（该平台跳过证书校验，
    #     FFmpeg 9.0 默认验证 TLS 证书后，证书异常平台仍可拉流）；
    #   - ssl_verify=False（https 录制模式，全局已禁用校验）→ 平台覆盖无
    #     额外意义，一律继承全局值 False。
    if ssl_verify and platform and platform in ssl_verify_platform_overrides:
        return ssl_verify_platform_overrides[platform]
    return ssl_verify
