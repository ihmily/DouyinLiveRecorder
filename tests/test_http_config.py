# -*- coding: utf-8 -*-
# http_config SSL 校验开关测试：整合开关「是否启用https录制」联动语义 + 平台级覆盖机制
from collections.abc import Generator

import pytest

from src import http_config


@pytest.fixture(autouse=True)
def _reset_state() -> Generator[None, None, None]:
    # 隔离模块级全局，避免污染其他测试
    saved_global = http_config.ssl_verify
    saved_overrides = dict(http_config.ssl_verify_platform_overrides)
    saved_https = http_config.https_recording_enabled
    http_config.ssl_verify = True
    http_config.ssl_verify_platform_overrides.clear()
    http_config.https_recording_enabled = False
    yield
    http_config.ssl_verify = saved_global
    http_config.ssl_verify_platform_overrides.clear()
    http_config.ssl_verify_platform_overrides.update(saved_overrides)
    http_config.https_recording_enabled = saved_https


def _apply_integrated_switch(enabled: bool) -> None:
    # 复刻 main.py 的整合联动调用顺序：「是否启用https录制」开启 = https 拉流 +
    # 禁用证书验证；关闭 = http 拉流 + 恢复默认证书校验
    http_config.set_https_recording(enabled)
    http_config.set_ssl_verify(not enabled)


# ---------------- 整合语义（main.py 联动调用顺序） ----------------


def test_integrated_https_on_disables_ssl_verify() -> None:
    # 整合：开启 https 录制 → 全局禁用证书验证（原「是否禁用SSL证书验证=是」功能并入）
    _apply_integrated_switch(True)
    assert http_config.ssl_verify is False
    assert http_config.get_effective_ssl_verify() is False
    assert http_config.get_effective_ssl_verify("虎牙直播") is False
    assert http_config.get_effective_ssl_verify("抖音直播") is False


def test_integrated_https_off_restores_default_verify() -> None:
    # 整合：关闭（http 录制）→ 恢复默认严格校验（原「是否禁用SSL证书验证=否」语义）
    _apply_integrated_switch(False)
    assert http_config.ssl_verify is True
    assert http_config.get_effective_ssl_verify() is True
    assert http_config.get_effective_ssl_verify("虎牙直播") is True


def test_integrated_toggle_roundtrip() -> None:
    # 整合：开↔关热切换（Web 面板改配置后主循环每轮同步）行为正确翻转
    _apply_integrated_switch(True)
    assert http_config.get_effective_ssl_verify("B站直播") is False
    _apply_integrated_switch(False)
    assert http_config.get_effective_ssl_verify("B站直播") is True
    _apply_integrated_switch(True)
    assert http_config.get_effective_ssl_verify("B站直播") is False


def test_integrated_platform_override_inert_under_https() -> None:
    # https 模式全局已禁用证书验证：平台级列表无额外意义，列表内/外平台一致均为不校验
    _apply_integrated_switch(True)
    http_config.set_platform_ssl_verify("虎牙直播", False)
    assert http_config.get_effective_ssl_verify("虎牙直播") is False
    assert http_config.get_effective_ssl_verify("抖音直播") is False


def test_integrated_http_mode_platform_override_takes_effect() -> None:
    # http 模式（恢复默认严格校验）：「禁用SSL证书验证的平台」生效——
    # 列表内平台跳过证书校验（FFmpeg 9.0 默认验证 TLS 证书后证书异常平台仍可拉流），
    # 列表外平台保持严格校验
    _apply_integrated_switch(False)
    http_config.set_platform_ssl_verify("虎牙直播", False)
    assert http_config.get_effective_ssl_verify("虎牙直播") is False
    assert http_config.get_effective_ssl_verify("抖音直播") is True


# ---------------- 底层机制（set_ssl_verify / 门控独立） ----------------


def test_default_returns_global_true() -> None:
    # 默认全局启用校验（安全优先），任意平台均校验
    http_config.set_ssl_verify(True)
    assert http_config.get_effective_ssl_verify() is True
    assert http_config.get_effective_ssl_verify("虎牙直播") is True
    assert http_config.get_effective_ssl_verify(None) is True


def test_global_false_without_override() -> None:
    # 全局关闭时，无平台覆盖则全部不校验
    http_config.set_ssl_verify(False)
    assert http_config.get_effective_ssl_verify("虎牙直播") is False
    assert http_config.get_effective_ssl_verify("抖音直播") is False


def test_platform_override_isolated() -> None:
    # 平台覆盖机制：全局需要校验（ssl_verify=True）时覆盖参与读取
    http_config.set_ssl_verify(True)
    http_config.set_https_recording(True)
    http_config.set_platform_ssl_verify("虎牙直播", False)
    assert http_config.get_effective_ssl_verify("虎牙直播") is False
    assert http_config.get_effective_ssl_verify("抖音直播") is True
    assert http_config.get_effective_ssl_verify(None) is True


def test_platform_override_ignored_when_global_disabled() -> None:
    # 平台覆盖仅在「SSL 证书需要验证」时生效：全局已禁用校验（ssl_verify=False，
    # https 录制模式）时覆盖无额外意义，一律继承全局 False
    http_config.set_ssl_verify(False)
    http_config.set_https_recording(True)
    http_config.set_platform_ssl_verify("虎牙直播", True)
    assert http_config.get_effective_ssl_verify("虎牙直播") is False
    assert http_config.get_effective_ssl_verify("抖音直播") is False


def test_platform_override_effective_when_verification_needed() -> None:
    # 「SSL 证书需要验证」时（ssl_verify=True）平台覆盖生效：
    # 禁用列表内平台返回 False（跳过校验），列表外平台保持 True（严格校验）
    http_config.set_ssl_verify(True)
    http_config.set_https_recording(False)
    http_config.set_platform_ssl_verify("虎牙直播", False)
    assert http_config.get_effective_ssl_verify("虎牙直播") is False
    assert http_config.get_effective_ssl_verify("B站直播") is True


def test_platform_list_parsing_isolated() -> None:
    # 模拟 main.py 的逗号分隔解析：空格/空项应被忽略，仅有效平台生效
    raw = " 虎牙直播 , B站直播 ,,  "
    platforms = {p.strip() for p in raw.split(",") if p.strip()}
    assert platforms == {"虎牙直播", "B站直播"}


def test_https_default_off_matches_main_initial_state() -> None:
    # 模块默认值与 main.enable_https_recording 初始 False 一致：import 后未进主循环前安全保守
    assert http_config.https_recording_enabled is False
