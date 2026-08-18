# -*- coding: utf-8 -*-
# http_config SSL 校验开关测试：全局默认 + 平台级覆盖的隔离与优先级
import pytest

from src import http_config


@pytest.fixture(autouse=True)
def _reset_state():
    # 隔离模块级全局，避免污染其他测试
    saved_global = http_config.ssl_verify
    saved_overrides = dict(http_config.ssl_verify_platform_overrides)
    http_config.ssl_verify = True
    http_config.ssl_verify_platform_overrides.clear()
    yield
    http_config.ssl_verify = saved_global
    http_config.ssl_verify_platform_overrides.clear()
    http_config.ssl_verify_platform_overrides.update(saved_overrides)


def test_default_returns_global_true():
    # 默认全局启用校验（安全优先），任意平台均校验
    http_config.set_ssl_verify(True)
    assert http_config.get_effective_ssl_verify() is True
    assert http_config.get_effective_ssl_verify("虎牙直播") is True
    assert http_config.get_effective_ssl_verify(None) is True


def test_global_false_without_override():
    # 全局关闭时，无平台覆盖则全部不校验
    http_config.set_ssl_verify(False)
    assert http_config.get_effective_ssl_verify("虎牙直播") is False
    assert http_config.get_effective_ssl_verify("抖音直播") is False


def test_platform_override_isolated():
    # 仅虎牙可选关闭，不影响其他平台与全局默认
    http_config.set_ssl_verify(True)
    http_config.set_platform_ssl_verify("虎牙直播", False)
    assert http_config.get_effective_ssl_verify("虎牙直播") is False
    assert http_config.get_effective_ssl_verify("抖音直播") is True
    assert http_config.get_effective_ssl_verify(None) is True


def test_platform_override_beats_global():
    # 平台覆盖优先于全局：全局关、虎牙开 → 虎牙仍校验
    http_config.set_ssl_verify(False)
    http_config.set_platform_ssl_verify("虎牙直播", True)
    assert http_config.get_effective_ssl_verify("虎牙直播") is True
    assert http_config.get_effective_ssl_verify("抖音直播") is False


def test_multiple_platform_overrides_isolated():
    # 通用平台列表：多个平台可独立关闭，互不干扰，且不影响全局与其他平台
    http_config.set_ssl_verify(True)
    http_config.set_platform_ssl_verify("虎牙直播", False)
    http_config.set_platform_ssl_verify("B站直播", False)
    assert http_config.get_effective_ssl_verify("虎牙直播") is False
    assert http_config.get_effective_ssl_verify("B站直播") is False
    assert http_config.get_effective_ssl_verify("抖音直播") is True
    assert http_config.get_effective_ssl_verify(None) is True


def test_platform_list_parsing_isolated():
    # 模拟 main.py 的逗号分隔解析：空格/空项应被忽略，仅有效平台生效
    raw = " 虎牙直播 , B站直播 ,,  "
    platforms = {p.strip() for p in raw.split(",") if p.strip()}
    assert platforms == {"虎牙直播", "B站直播"}
    http_config.set_ssl_verify(True)
    for p in platforms:
        http_config.set_platform_ssl_verify(p, False)
    assert http_config.get_effective_ssl_verify("虎牙直播") is False
    assert http_config.get_effective_ssl_verify("B站直播") is False
    assert http_config.get_effective_ssl_verify("抖音直播") is True
