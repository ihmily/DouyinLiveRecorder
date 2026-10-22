# -*- coding: utf-8 -*-
# src/platforms/douyin.py 测试：抖音弹幕链路「凭据被平台拒绝 → 作废进程级缓存」的接线
# （MID-33 的弹幕侧半边）。
#
# 契约（三条，缺一不可）：
#   ① WS 握手被服务端以 HTTP 200 拒绝（抖音对失效 ttwid 的实测形态：不返回 4xx，而是 200 +
#      不升级协议）时必须触发 src.ttwid.invalidate_ttwid()，使下一轮重新获取，而不是等
#      cookie_cache 的 30 分钟 TTL 自然过期；
#   ② 网络类失败（超时 / 连接被拒 / DNS）与 4xx/5xx 不得触发作废——重复拉 ttwid 本身就是风控
#      触发源（见 src/room.py 的并发去重锁注释），误判会把断网放大成打主页接口；
#   ③ 只有「本轮 cookie 来自 get_ttwid() 动态获取」才判定；用户自填的录制 cookie 不走该缓存，
#      作废它既无效又多余。
#
# 打桩边界：只替换网络层（WsClient）与凭据取用（get_ttwid），判定正则、标志位、回调链全部走
# 真实代码——删掉 _note_ttwid_refusal 或其调用点即红（test_refusal_clears_real_ttwid_cache
# 更是不打桩 invalidate，直接断言真实缓存被清）。

from typing import Any, Callable

import pytest

from src import ttwid as ttwid_module
from src.platforms import douyin as douyin_module

# websockets 17.1 对非 101 应答的异常文案（读库 exceptions.py 核对，legacy 同文案），
# 而 WsClient 只把 str(e) 透传给回调 —— 这正是判定只能按状态码文本做的原因。
_HTTP200_REFUSAL = "server rejected WebSocket connection: HTTP 200"
_TIMEOUT_TEXT = "timed out during opening handshake"
_HTTP403_TEXT = "server rejected WebSocket connection: HTTP 403"


class _StubWsClient:
    # WsClient 替身：只替换「建立连接并回调」这一步，构造参数原样收下供断言；
    # connect() 按 script 依次触发对应回调，模拟真实的重连/耗尽上报节奏。

    instances: list["_StubWsClient"] = []

    def __init__(self, **kwargs: Any) -> None:
        self.kwargs: dict[str, Any] = kwargs
        self.script: list[tuple[str, str]] = []
        _StubWsClient.instances.append(self)

    # 安装替身并返回类级实例表；同时把动态取凭据换成常量。
    @staticmethod
    def install(monkeypatch: pytest.MonkeyPatch, ttwid_value: str = "ttwid=dynamic") -> None:
        _StubWsClient.instances = []

        async def _fake_get_ttwid(proxy_addr: Any = None) -> str:
            return ttwid_value

        monkeypatch.setattr(douyin_module, "get_ttwid", _fake_get_ttwid)
        monkeypatch.setattr(douyin_module, "WsClient", _StubWsClient)

    # 本替身收到的回调：on_reconnect / on_close（键名与 WsClient 构造参数一致）。
    def _callback(self, kind: str) -> "Callable[..., object] | None":
        value: Any = self.kwargs.get(kind)
        return value if callable(value) else None

    async def connect(self) -> None:
        for kind, text in self.script:
            cb = self._callback(kind)
            if cb is not None:
                cb(text)

    async def close(self) -> None:
        return None


def _revoke_recorder(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    # 把 invalidate_ttwid 换成计数器（多数用例只关心「有没有被调用、调用几次」）。
    calls: list[int] = []
    monkeypatch.setattr(douyin_module, "invalidate_ttwid", lambda *a, **k: calls.append(1))
    return calls


class TestTtwidRefusalWiring:
    # 握手拒绝 → invalidate_ttwid 的核心接线矩阵。

    @pytest.mark.parametrize(
        "script_text,should_revoke",
        [
            (_HTTP200_REFUSAL, True),  # 失效 ttwid 的实测形态（经 on_reconnect 上报）
            (f"重连超过最大次数，与服务器断开连接: {_HTTP200_REFUSAL}", True),  # 经 on_close 上报
            (_HTTP403_TEXT, False),  # 4xx 不是「凭据被作废」
            (_TIMEOUT_TEXT, False),  # 网络类失败不得触发作废
        ],
    )
    async def test_refusal_pattern_decides_invalidate(
        self, monkeypatch: pytest.MonkeyPatch, script_text: str, should_revoke: bool
    ) -> None:
        _StubWsClient.install(monkeypatch)
        revoked = _revoke_recorder(monkeypatch)
        reported: list[str] = []

        client = douyin_module.DouyinDanmaku(on_close=reported.append)
        # cookie 缺省 → 走 get_ttwid 动态路径（判定①与③的前置条件）
        await client.start({"room_id": "123456", "user_id": "789"})
        ws = _StubWsClient.instances[0]
        ws.script = [("on_reconnect", script_text), ("on_close", script_text)]
        await ws.connect()

        assert (len(revoked) == 1) is should_revoke, f"{script_text!r} 的作废判定不符: {revoked}"
        # 上层关闭事件必须原样送达（包装回调不得吞掉 on_close，否则监控页丢房间关闭事件）
        assert reported == [script_text]

    async def test_repeated_refusal_invalidates_only_once(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # 一轮会话内最多 5 次重连都带同一拒绝文案：缓存只需清一次（幂等，且避免反复去动下层
        # singleflight / cookie 缓存）。
        _StubWsClient.install(monkeypatch)
        revoked = _revoke_recorder(monkeypatch)
        client = douyin_module.DouyinDanmaku()
        await client.start({"room_id": "1", "user_id": "2"})
        ws = _StubWsClient.instances[0]
        ws.script = [("on_reconnect", _HTTP200_REFUSAL)] * 5
        await ws.connect()
        assert len(revoked) == 1

    async def test_user_supplied_cookie_does_not_revoke_shared_cache(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # 判定③：录制 cookie 由 main 传入时不走 ttwid 进程级缓存，作废它毫无意义，
        # 反而会让下一轮（可能确实需要自动获取）白打一次主页接口。
        _StubWsClient.install(monkeypatch)
        revoked = _revoke_recorder(monkeypatch)
        client = douyin_module.DouyinDanmaku()
        await client.start({"room_id": "1", "user_id": "2", "cookie": "ttwid=user-provided"})
        ws = _StubWsClient.instances[0]
        ws.script = [("on_close", _HTTP200_REFUSAL)]
        await ws.connect()
        assert revoked == []
        # 且握手头用的就是用户那支 cookie
        assert ws.kwargs["headers"]["Cookie"] == "ttwid=user-provided"

    async def test_refusal_clears_real_ttwid_cache(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # 端到端不变量（**不**打桩 invalidate）：真实进程级缓存里的失效 ttwid 必须被清空，
        # 否则「下一轮重新获取」根本不成立 —— 这正是 MID-33 的全部目的。
        _StubWsClient.install(monkeypatch)
        saved_value, saved_at = ttwid_module._cached_ttwid, ttwid_module._cached_ttwid_at
        try:
            _ = ttwid_module._cache_ttwid("ttwid=revoked-by-platform")
            client = douyin_module.DouyinDanmaku()
            await client.start({"room_id": "1", "user_id": "2"})
            ws = _StubWsClient.instances[0]
            ws.script = [("on_close", f"重连超过最大次数，与服务器断开连接: {_HTTP200_REFUSAL}")]
            await ws.connect()
            assert ttwid_module._cached_ttwid == "", "握手被拒后模块全局 ttwid 仍在，下一轮会继续复用废凭据"
        finally:
            ttwid_module._cached_ttwid, ttwid_module._cached_ttwid_at = saved_value, saved_at

    async def test_flag_unset_when_dynamic_fetch_returns_empty(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # get_ttwid 返回空串（拉取失败）时不得置位「本轮在用 ttwid」：此时握手被拒与缓存无关，
        # 清缓存只会掩盖「压根没拿到凭据」这一真实成因。
        _StubWsClient.install(monkeypatch, ttwid_value="")
        revoked = _revoke_recorder(monkeypatch)
        client = douyin_module.DouyinDanmaku()
        await client.start({"room_id": "1", "user_id": "2"})
        ws = _StubWsClient.instances[0]
        ws.script = [("on_close", _HTTP200_REFUSAL)]
        await ws.connect()
        assert revoked == []
        assert client._ttwid_in_use is False


class TestHandshakeRefusalPredicate:
    # 判定函数的边界：只认「状态码恰为 200」，且须容忍 WsClient 的前缀文案。

    @pytest.mark.parametrize(
        "text,expected",
        [
            (_HTTP200_REFUSAL, True),
            ("proxy rejected connection: HTTP 200", True),
            ("server rejected WebSocket connection: HTTP 2000", False),
            ("server rejected WebSocket connection: HTTP 1200", False),
            ("status code: 200", True),
            ("", False),
            ("缺少 room_id", False),
        ],
    )
    def test_predicate(self, text: str, expected: bool) -> None:
        assert douyin_module._is_http200_handshake_refusal(text) is expected


class TestRoomIdContractUnchanged:
    # 接线不得改变既有契约：缺 room_id 仍直接上报关闭、且不建立连接。

    async def test_missing_room_id_closes_without_connect(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _StubWsClient.install(monkeypatch)
        reported: list[str] = []
        client = douyin_module.DouyinDanmaku(on_close=reported.append)
        await client.start({"user_id": "1"})
        assert reported == ["缺少 room_id"]
        assert _StubWsClient.instances == []
