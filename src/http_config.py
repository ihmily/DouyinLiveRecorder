# -*- coding: utf-8 -*-
# HTTP 客户端共享运行时配置

# 控制面 SSL 证书验证开关：登录 / 取 Cookie / 推送 token / 平台 API 等非拉流请求，默认启用；
# 改写走 set_ssl_verify()。2026-10-31 grep 实测控制面开关的生产读侧为 async_http / spider / room
# （按属性直读）；stream_select / main 读的是拉流侧 get_effective_ssl_verify，不经本开关；
# sync_http 虽仍 import 但该模块自身已无生产 importer（仅测试引用）。
# 安全边界：**不与**「是否启用https录制」联动——否则一个拉流选项会放大成全站 TLS 降级
# （含登录与凭据推送）；拉流豁免只落在 stream_ssl_verify。
# [历史注] 旧实现正是 set_ssl_verify(not enable_https_recording) 的联动写法。
ssl_verify: bool = True

# 拉流侧 SSL 证书验证开关（流地址探测 / 校验 / 直下 / ffmpeg）。与「是否启用https录制」
# 联动：开启 https 录制 → 拉流豁免证书校验（避免 CDN 证书主机名不匹配阻断拉流）；关闭 → 恢复
# 严格校验。读取一律走 get_effective_ssl_verify(platform)，保证校验器 / ffmpeg / 直下三路一致。
stream_ssl_verify: bool = True

# 平台级 SSL 证书验证覆盖：键为平台标识（如「虎牙直播」），值为是否校验。
# FFmpeg 9.0 起 TLS 证书验证默认开启（8.0 预告、9.0 落地），http 录制模式下 https-only
# 流/接口同样被校验，「禁用SSL证书验证的平台」因此重新具备作用：证书异常平台（虎牙 TX CDN
# 主机名不匹配等）经此列表跳过校验。该覆盖只参与拉流侧裁决（stream_ssl_verify=True 时生效）。
ssl_verify_platform_overrides: dict[str, bool] = {}

# 「是否启用https录制」整合开关（由「是否强制启用https录制」与「是否禁用SSL证书验证」合并）：
# 开启 = https 拉流 + 拉流侧禁用证书校验；关闭 = http 拉流 + 拉流侧恢复默认校验。
# 运行时由主循环热更新；控制面 ssl_verify 不随之变化（见其处的安全边界说明）。
https_recording_enabled: bool = False


def set_ssl_verify(value: bool) -> None:
    # 控制面开关的安全敏感性与「不与 https 录制联动」的边界见模块头 ssl_verify 注释
    global ssl_verify
    ssl_verify = value


def set_stream_ssl_verify(value: bool) -> None:
    global stream_ssl_verify
    stream_ssl_verify = value


def set_https_recording(value: bool) -> None:
    # 仅联动拉流侧 stream_ssl_verify；控制面 ssl_verify 保持独立（理由见模块头）
    global https_recording_enabled
    https_recording_enabled = value
    set_stream_ssl_verify(not value)


def set_platform_ssl_verify(platform: str, value: bool) -> None:
    ssl_verify_platform_overrides[platform] = value


def get_effective_ssl_verify(platform: str | None = None) -> bool:
    # 拉流侧实际生效的开关。平台覆盖只在 stream_ssl_verify=True（http 录制）时参与裁决：
    # 命中禁用列表 → False，让证书异常平台仍可拉流；stream_ssl_verify=False 时拉流已全局豁免，
    # 平台覆盖无额外意义，一律继承 False。
    if stream_ssl_verify and platform and platform in ssl_verify_platform_overrides:
        return ssl_verify_platform_overrides[platform]
    return stream_ssl_verify
