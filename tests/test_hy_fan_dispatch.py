# 虎牙移动端分享短链（hy.fan）接入回归。
#
# 覆盖面：
#   1. 四种输入形态（标准 / 尾斜杠 / 带 query / http）归一成 https://www.huya.com/<房间号>，
#      并确认走的是既有 _resolve_huya_com 链路；
#   2. 短码形态（如 JbmwoV）经跳转解析出房间段且结果进进程内缓存——第二轮监测不再发解析请求
#      （不缓存等于每 30s+ 白发一次 301 跟随）；
#   3. 解析失败（空返回 / 非 ValueError 的意外异常）→ 返回 None 交房间线程延迟重试，
#      且未归一的原始地址绝不能流进虎牙解析链路；
#   4. 纯解析函数的合法形态与非法形态（路径为空 / 多级目录 / 非法字符 / 全角数字）。
#
# 所有 spider / stream 调用替换为记录型桩（不发真实网络请求）；跳转解析函数整体替换为异步桩并
# 统计调用次数（锁定缓存契约）。变异验证记录：归一化断言（spider 收到 www.huya.com 链接而非
# 原始 hy.fan 地址）已按轮次做改坏-还原验证。

import sys
import threading
from pathlib import Path
from typing import Any

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def main_mod() -> Any:
    # 与 test_platform_dispatch 一致：导入前把 sys.argv[0] 钉到 main.py，
    # 否则 _app_root() 解析出的配置/日志目录会落到别处。
    old_argv = sys.argv[:]
    sys.argv = [str(_REPO_ROOT / "main.py")]
    try:
        import main

        return main
    finally:
        sys.argv = old_argv


class _RecordingShim:
    # 记录型异步桩：记录「调用名 + url 关键字实参」。除平台名外还必须能断言「归一后的桌面
    # 链接传进了 spider」——只断言平台名会漏掉「归一化没生效」这类回归。
    def __init__(self, sink: list) -> None:
        self._sink = sink

    def __getattr__(self, name: str) -> object:
        async def _fake(*args: Any, **kwargs: Any) -> object:
            self._sink.append((name, kwargs.get("url", "")))
            return {}

        return _fake


@pytest.fixture
def dispatch_env(main_mod: Any, monkeypatch: pytest.MonkeyPatch) -> tuple[Any, list]:
    calls: list[tuple[str, str]] = []
    monkeypatch.setattr(main_mod, "spider", _RecordingShim(calls), raising=False)
    monkeypatch.setattr(main_mod, "stream", _RecordingShim(calls), raising=False)
    # main() 运行期才赋值的全局量：import 期不存在，需补齐否则 NameError（同 test_platform_dispatch）
    if not hasattr(main_mod, "hy_cookie"):
        monkeypatch.setattr(main_mod, "hy_cookie", "", raising=False)
    if not hasattr(main_mod, "semaphore"):
        monkeypatch.setattr(main_mod, "semaphore", threading.Semaphore(8), raising=False)
    # 短码解析缓存按用例隔离：模块级 dict 会跨用例残留，换成空 dict 等价于「每例新进程」，
    # 让「缓存命中后解析桩不再被调」的断言不依赖用例执行顺序。
    monkeypatch.setattr(main_mod, "_HY_FAN_ROOM_CACHE", {}, raising=False)
    return main_mod, calls


_HY_FAN_FORMS = [
    # 用户要求覆盖的四种输入形态：标准 / 尾斜杠 / 带 query / http
    "https://hy.fan/30764624",
    "https://hy.fan/30764624/",
    "https://hy.fan/30764624?source=android&from=cpy",
    "http://hy.fan/30764624",
]


@pytest.mark.parametrize("url", _HY_FAN_FORMS)
def test_numeric_forms_normalize_and_reuse_huya_flow(dispatch_env: tuple, url: str) -> None:
    main_mod, calls = dispatch_env
    result = main_mod._resolve_platform_stream(url, None, "原画")
    assert result is not None, f"{url} 应被识别，实际返回 None"
    platform, _port_info, _danmaku, _new_url = result
    assert platform == "虎牙直播"
    # 归一化是本功能的根契约：spider 收到的必须是桌面链接，而不是原始 hy.fan 地址
    assert ("get_huya_stream_data", "https://www.huya.com/30764624") in calls


def test_short_code_resolves_then_hits_cache(dispatch_env: tuple, monkeypatch: pytest.MonkeyPatch) -> None:
    main_mod, calls = dispatch_env
    resolve_calls: list[str] = []

    async def _fake_resolve(url: str, proxy_addr: str | None) -> str:
        resolve_calls.append(url)
        return "30764624"

    monkeypatch.setattr(main_mod, "_resolve_hy_fan_room_segment", _fake_resolve)
    for _round in range(2):
        result = main_mod._resolve_platform_stream("https://hy.fan/JbmwoV", None, "原画")
        assert result is not None
        assert result[0] == "虎牙直播"
        assert ("get_huya_stream_data", "https://www.huya.com/30764624") in calls
    # 两轮分派只发生一次解析请求：第二轮命中 _HY_FAN_ROOM_CACHE
    assert resolve_calls == ["https://hy.fan/JbmwoV"]


def test_short_code_resolution_failure_is_unrecognized(dispatch_env: tuple, monkeypatch: pytest.MonkeyPatch) -> None:
    main_mod, calls = dispatch_env

    async def _fake_resolve(url: str, proxy_addr: str | None) -> str:
        raise ValueError("未获取到跳转地址")

    monkeypatch.setattr(main_mod, "_resolve_hy_fan_room_segment", _fake_resolve)
    # 返回 None = 本轮按未识别处理（房间线程延迟重试）；spider 零调用 = 未归一地址不进虎牙链路
    assert main_mod._resolve_platform_stream("https://hy.fan/JbmwoV", None, "原画") is None
    assert calls == []


def test_unexpected_resolution_error_is_unrecognized(dispatch_env: tuple, monkeypatch: pytest.MonkeyPatch) -> None:
    main_mod, calls = dispatch_env

    async def _fake_resolve(url: str, proxy_addr: str | None) -> str:
        raise RuntimeError("event loop is closed")

    monkeypatch.setattr(main_mod, "_resolve_hy_fan_room_segment", _fake_resolve)
    # 非 ValueError 的意外异常同样按未识别处理：不能向上炸穿 _resolve_platform_stream 的兜底
    assert main_mod._resolve_platform_stream("https://hy.fan/JbmwoV", None, "原画") is None
    assert calls == []


def test_letter_landing_keeps_letter_room_id(dispatch_env: tuple, monkeypatch: pytest.MonkeyPatch) -> None:
    main_mod, calls = dispatch_env

    async def _fake_resolve(url: str, proxy_addr: str | None) -> str:
        return "kaerlol"

    monkeypatch.setattr(main_mod, "_resolve_hy_fan_room_segment", _fake_resolve)
    # 落地页是主播自定义字母号时归一为 www.huya.com/<字母号>：
    # 下游 app 路径已有 ProfileRoom 反查数字房间号的链路，这里不做二次解析
    result = main_mod._resolve_platform_stream("https://hy.fan/Zzz999", None, "原画")
    assert result is not None
    assert ("get_huya_stream_data", "https://www.huya.com/kaerlol") in calls


def test_path_segment_parses_all_supported_forms(main_mod: Any) -> None:
    for url in _HY_FAN_FORMS:
        assert main_mod._hy_fan_path_segment(url) == "30764624"
    # 短码（base62）形态同样合法
    assert main_mod._hy_fan_path_segment("https://hy.fan/JbmwoV") == "JbmwoV"


@pytest.mark.parametrize(
    "url,reason",
    [
        ("https://hy.fan/", "路径为空"),
        ("https://hy.fan", "路径为空"),
        ("https://hy.fan/a/b", "多级目录"),
        ("https://hy.fan/12_34", "非法字符"),
        # 全角数字不是合法房间号：isascii 收紧 isalnum 的 Unicode 宽字符误判
        ("https://hy.fan/３０７６４", "非法字符"),
    ],
)
def test_path_segment_rejects_invalid_forms(main_mod: Any, url: str, reason: str) -> None:
    with pytest.raises(ValueError, match=reason):
        main_mod._hy_fan_path_segment(url)


@pytest.mark.parametrize(
    "final_url,expected",
    [
        ("https://www.huya.com/30764624?source=android&from=cpy", "30764624"),
        ("https://m.huya.com/30764624", "30764624"),
        ("https://www.huya.com/kaerlol", "kaerlol"),
        # 落地页仍是短链域 → 不算解析成功（防止自指返回原地址被当成房间段）
        ("https://hy.fan/JbmwoV", ""),
        # 「evil-huya.com」是连字符拼接域：后缀判定必须按「.huya.com」边界，不能放行
        ("https://evil-huya.com/123456", ""),
        ("https://www.huya.com/a/b", ""),
        ("https://www.huya.com/", ""),
    ],
)
def test_landing_segment_requires_huya_host(main_mod: Any, final_url: str, expected: str) -> None:
    assert main_mod._huya_room_segment_from_landing(final_url) == expected
