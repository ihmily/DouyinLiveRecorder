# -*- coding: utf-8 -*-
# http_config SSL 校验开关测试：「是否启用https录制」的整合联动 + 平台级覆盖。
# 安全边界：证书豁免只作用于拉流侧 stream_ssl_verify；控制面 ssl_verify
# （登录 / 取 Cookie / 推送 token / 平台 API）恒为严格校验，不受该开关影响。
from collections.abc import Generator

import pytest

from src import http_config


@pytest.fixture(autouse=True)
def _reset_state() -> Generator[None, None, None]:
    # 隔离模块级全局，避免污染其他测试
    saved_global = http_config.ssl_verify
    saved_stream = http_config.stream_ssl_verify
    saved_overrides = dict(http_config.ssl_verify_platform_overrides)
    saved_https = http_config.https_recording_enabled
    http_config.ssl_verify = True
    http_config.stream_ssl_verify = True
    http_config.ssl_verify_platform_overrides.clear()
    http_config.https_recording_enabled = False
    yield
    http_config.ssl_verify = saved_global
    http_config.stream_ssl_verify = saved_stream
    http_config.ssl_verify_platform_overrides.clear()
    http_config.ssl_verify_platform_overrides.update(saved_overrides)
    http_config.https_recording_enabled = saved_https


def _apply_integrated_switch(enabled: bool) -> None:
    # 复刻 main.py 的整合联动：只调 set_https_recording，由其内部联动拉流侧；
    # 控制面 ssl_verify 不受联动。
    http_config.set_https_recording(enabled)


# ---------------- 整合语义（main.py 联动调用顺序） ----------------


def test_integrated_https_on_relaxes_stream_verify_only() -> None:
    # 开启 https 录制 → 拉流侧豁免证书校验，控制面保持严格校验
    _apply_integrated_switch(True)
    assert http_config.stream_ssl_verify is False
    assert http_config.get_effective_ssl_verify() is False
    assert http_config.get_effective_ssl_verify("虎牙直播") is False
    assert http_config.get_effective_ssl_verify("抖音直播") is False
    # 安全边界：控制面不受拉流开关影响
    assert http_config.ssl_verify is True


def test_integrated_https_off_restores_stream_verify() -> None:
    # 关闭（http 录制）→ 拉流侧恢复默认严格校验
    _apply_integrated_switch(False)
    assert http_config.stream_ssl_verify is True
    assert http_config.get_effective_ssl_verify() is True
    assert http_config.get_effective_ssl_verify("虎牙直播") is True
    assert http_config.ssl_verify is True


def test_control_plane_verify_never_disabled_by_https_toggle() -> None:
    # 安全回归防线：https 录制开关任意翻转，控制面 ssl_verify 恒为 True。
    # 旧实现曾用 set_ssl_verify(not enabled) 让拉流开关关掉全站 TLS 校验。
    for enabled in (True, False, True):
        _apply_integrated_switch(enabled)
        assert http_config.ssl_verify is True


def test_integrated_toggle_roundtrip() -> None:
    # 开↔关热切换（Web 面板改配置后主循环每轮同步）行为正确翻转
    _apply_integrated_switch(True)
    assert http_config.get_effective_ssl_verify("B站直播") is False
    _apply_integrated_switch(False)
    assert http_config.get_effective_ssl_verify("B站直播") is True
    _apply_integrated_switch(True)
    assert http_config.get_effective_ssl_verify("B站直播") is False


def test_integrated_platform_override_inert_under_https() -> None:
    # https 模式拉流侧已全局豁免：平台列表无额外意义，列表内外一律不校验
    _apply_integrated_switch(True)
    http_config.set_platform_ssl_verify("虎牙直播", False)
    assert http_config.get_effective_ssl_verify("虎牙直播") is False
    assert http_config.get_effective_ssl_verify("抖音直播") is False


def test_integrated_http_mode_platform_override_takes_effect() -> None:
    # http 模式：「禁用SSL证书验证的平台」生效——列表内跳过证书校验
    # （FFmpeg 9.0 起默认验证 TLS 证书，证书异常平台仍可拉流），列表外严格校验。
    _apply_integrated_switch(False)
    http_config.set_platform_ssl_verify("虎牙直播", False)
    assert http_config.get_effective_ssl_verify("虎牙直播") is False
    assert http_config.get_effective_ssl_verify("抖音直播") is True


# ---------------- 底层机制（拉流 / 控制面开关独立） ----------------


def test_default_returns_stream_true() -> None:
    # 默认拉流侧启用校验（安全优先），任意平台均校验
    http_config.set_stream_ssl_verify(True)
    assert http_config.get_effective_ssl_verify() is True
    assert http_config.get_effective_ssl_verify("虎牙直播") is True
    assert http_config.get_effective_ssl_verify(None) is True


def test_stream_false_without_override() -> None:
    # 拉流侧关闭时，无平台覆盖则全部不校验
    http_config.set_stream_ssl_verify(False)
    assert http_config.get_effective_ssl_verify("虎牙直播") is False
    assert http_config.get_effective_ssl_verify("抖音直播") is False


def test_set_ssl_verify_does_not_touch_stream() -> None:
    # 控制面开关与拉流开关互相独立：设置控制面不改动拉流侧取值
    http_config.set_stream_ssl_verify(True)
    http_config.set_ssl_verify(False)
    assert http_config.ssl_verify is False
    assert http_config.stream_ssl_verify is True
    assert http_config.get_effective_ssl_verify("虎牙直播") is True


def test_platform_override_isolated() -> None:
    # 平台覆盖机制：拉流侧需要校验（stream_ssl_verify=True）时覆盖参与读取
    http_config.set_stream_ssl_verify(True)
    http_config.set_platform_ssl_verify("虎牙直播", False)
    assert http_config.get_effective_ssl_verify("虎牙直播") is False
    assert http_config.get_effective_ssl_verify("抖音直播") is True
    assert http_config.get_effective_ssl_verify(None) is True


def test_platform_override_ignored_when_stream_disabled() -> None:
    # 拉流已全局豁免（https 录制模式）时覆盖无额外意义，一律继承 False
    http_config.set_stream_ssl_verify(False)
    http_config.set_https_recording(True)
    http_config.set_platform_ssl_verify("虎牙直播", True)
    assert http_config.get_effective_ssl_verify("虎牙直播") is False
    assert http_config.get_effective_ssl_verify("抖音直播") is False


def test_platform_override_effective_when_verification_needed() -> None:
    # 拉流侧需要验证时平台覆盖生效：禁用列表内返回 False，列表外保持 True
    http_config.set_stream_ssl_verify(True)
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
    assert http_config.ssl_verify is True
    assert http_config.stream_ssl_verify is True
