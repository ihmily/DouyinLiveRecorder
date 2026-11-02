# B站移动端分享短链（b23.tv）接入回归用例
#
# 覆盖面：
#   1. 四种输入形态（标准 / 尾斜杠 / 带 query / http）归一成 https://live.bilibili.com/<房间号>，
#      且走既有 _resolve_live_bilibili_com 链路；
#   2. 短码形态（如 ZyQrgYf）经跳转解析出房间号，结果进进程内缓存——第二轮监测不再发解析请求；
#   3. 解析失败（空返回 / 非 ValueError 的意外异常）→ 返回 None 交房间线程延迟重试，未归一的原始
#      地址不得流进B站解析链路；
#   4. 纯解析函数的合法/非法形态（路径为空 / 多级目录 / 非法字符 / 全角数字），落地页房间号提取的
#      域与形态边界（视频页 / 自指短链 / 连字符拼接域一律拒绝）。
#
# spider / stream 调用替换为记录型桩（不发真实网络请求），跳转解析函数替换为异步桩并统计调用
# 次数（锁定缓存契约）。变异验证：归一化断言（spider 收到 live.bilibili.com 链接而非原始
# b23.tv 地址）与落地页数字判定（_bilibili_room_id_from_landing 放行字母段）已做改坏-还原验证。

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
    # 记录型异步桩：记录「调用名 + url 关键字实参」。除平台名外还必须能断言
    # 「归一后的桌面链接传进了 spider」——只断言平台名会漏掉「归一化没生效」这类回归。
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
    if not hasattr(main_mod, "bili_cookie"):
        monkeypatch.setattr(main_mod, "bili_cookie", "", raising=False)
    if not hasattr(main_mod, "semaphore"):
        monkeypatch.setattr(main_mod, "semaphore", threading.Semaphore(8), raising=False)
    # 短码解析缓存按用例隔离：模块级 dict 会跨用例残留，换空 dict 等价于「每例新进程」，
    # 使「缓存命中后解析桩不再被调」的断言不依赖执行顺序。
    monkeypatch.setattr(main_mod, "_B23_TV_ROOM_CACHE", {}, raising=False)
    return main_mod, calls


_B23_TV_FORMS = [
    # 四种输入形态：标准 / 尾斜杠 / 带 query / http
    "https://b23.tv/22747736",
    "https://b23.tv/22747736/",
    "https://b23.tv/22747736?share_source=COPY&is_room_feed=1",
    "http://b23.tv/22747736",
]


@pytest.mark.parametrize("url", _B23_TV_FORMS)
def test_numeric_forms_normalize_and_reuse_bilibili_flow(dispatch_env: tuple, url: str) -> None:
    main_mod, calls = dispatch_env
    result = main_mod._resolve_platform_stream(url, None, "原画")
    assert result is not None, f"{url} 应被识别，实际返回 None"
    platform, _port_info, _danmaku, _new_url = result
    assert platform == "B站直播"
    # 归一化是本功能的根契约：spider 收到的必须是桌面链接，而不是原始 b23.tv 地址
    assert ("get_bilibili_room_info", "https://live.bilibili.com/22747736") in calls


def test_short_code_resolves_then_hits_cache(dispatch_env: tuple, monkeypatch: pytest.MonkeyPatch) -> None:
    main_mod, calls = dispatch_env
    resolve_calls: list[str] = []

    async def _fake_resolve(url: str, proxy_addr: str | None) -> str:
        resolve_calls.append(url)
        return "22747736"

    monkeypatch.setattr(main_mod, "_resolve_b23_tv_room_segment", _fake_resolve)
    for _round in range(2):
        result = main_mod._resolve_platform_stream("https://b23.tv/ZyQrgYf", None, "原画")
        assert result is not None
        assert result[0] == "B站直播"
        assert ("get_bilibili_room_info", "https://live.bilibili.com/22747736") in calls
    # 两轮分派只发生一次解析请求：第二轮命中 _B23_TV_ROOM_CACHE
    assert resolve_calls == ["https://b23.tv/ZyQrgYf"]


def test_short_code_resolution_failure_is_unrecognized(dispatch_env: tuple, monkeypatch: pytest.MonkeyPatch) -> None:
    main_mod, calls = dispatch_env

    async def _fake_resolve(url: str, proxy_addr: str | None) -> str:
        raise ValueError("未获取到跳转地址")

    monkeypatch.setattr(main_mod, "_resolve_b23_tv_room_segment", _fake_resolve)
    # 返回 None = 本轮按未识别处理（房间线程延迟重试）；spider 零调用 = 未归一地址不进B站链路
    assert main_mod._resolve_platform_stream("https://b23.tv/ZyQrgYf", None, "原画") is None
    assert calls == []


def test_unexpected_resolution_error_is_unrecognized(dispatch_env: tuple, monkeypatch: pytest.MonkeyPatch) -> None:
    main_mod, calls = dispatch_env

    async def _fake_resolve(url: str, proxy_addr: str | None) -> str:
        raise RuntimeError("event loop is closed")

    monkeypatch.setattr(main_mod, "_resolve_b23_tv_room_segment", _fake_resolve)
    # 非 ValueError 的意外异常同样按未识别处理：不能向上炸穿 _resolve_platform_stream 的兜底
    assert main_mod._resolve_platform_stream("https://b23.tv/ZyQrgYf", None, "原画") is None
    assert calls == []


def test_path_segment_parses_all_supported_forms(main_mod: Any) -> None:
    for url in _B23_TV_FORMS:
        assert main_mod._b23_tv_path_segment(url) == "22747736"
    # 短码（base62）形态同样合法，交由跳转解析出房间号
    assert main_mod._b23_tv_path_segment("https://b23.tv/ZyQrgYf") == "ZyQrgYf"


@pytest.mark.parametrize(
    "url,reason",
    [
        ("https://b23.tv/", "路径为空"),
        ("https://b23.tv", "路径为空"),
        ("https://b23.tv/a/b", "多级目录"),
        ("https://b23.tv/12_34", "非法字符"),
        # 全角数字不是合法房间号/短码：isascii 收紧 isalnum 的 Unicode 宽字符误判
        ("https://b23.tv/２２７４７", "非法字符"),
    ],
)
def test_path_segment_rejects_invalid_forms(main_mod: Any, url: str, reason: str) -> None:
    with pytest.raises(ValueError, match=reason):
        main_mod._b23_tv_path_segment(url)


@pytest.mark.parametrize(
    "final_url,expected",
    [
        # 真实短链（b23.tv/ZyQrgYf）实测落地形态：桌面路径 + 分享 query
        ("https://live.bilibili.com/22747736?broadcast_type=0&is_room_feed=1&share_from=live", "22747736"),
        # 移动端落地页 /h5/ 前缀形态一并接受
        ("https://live.bilibili.com/h5/22747736", "22747736"),
        # 落地页是视频页 / 主页域 → 不是直播间，不算解析成功
        ("https://www.bilibili.com/video/BV1xx411c7mD", ""),
        # 落地页仍是短链域 → 不算解析成功（防止自指返回原地址被当成房间号）
        ("https://b23.tv/ZyQrgYf", ""),
        # 「fake-live.bilibili.com」是连字符拼接域：后缀判定必须按「.live.bilibili.com」边界，不能放行
        ("https://fake-live.bilibili.com/22747736", ""),
        # live.bilibili.com 的房间号只有纯数字形态（短号也是数字），字母段一律拒绝
        ("https://live.bilibili.com/abc", ""),
        ("https://live.bilibili.com/a/b", ""),
        ("https://live.bilibili.com/", ""),
    ],
)
def test_landing_requires_live_bilibili_host_and_digits(main_mod: Any, final_url: str, expected: str) -> None:
    assert main_mod._bilibili_room_id_from_landing(final_url) == expected
