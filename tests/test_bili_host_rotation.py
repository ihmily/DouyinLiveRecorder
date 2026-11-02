# M-13 回归锁：B站弹幕 host 轮换期间不得投「假关闭」事件。
#
# 被测生产实现：src/platforms/bilibili.py::BilibiliDanmaku 的 _report_close 闸门 + start() 的
# host 轮换循环（挂在 WsClient.on_close 上的是闸门，不是裸回调）。
#
# 失效形态（修复前）：每个候选 host 各建一个 WsClient 且都把 on_close 直挂 self._on_close
# （消费端 = src/collector.py::_on_close → hub.room_closed）。host[0] 耗尽 2 次重连即落一条
# 「房间关闭」，而 start() 随后继续试 host[1]；host[1] 连上又报 room_connected → 监控页
# 「假关闭→重连」闪烁 + 一条与事实不符的落盘；两候选都失败时同一关闭事件投两次。
# WsClient 自带的 _close_reported 是**每实例**的，挡不住跨实例重复上报。
#
# 打桩边界：只把网络层 WsClient 换成替身（真实现要打 wss:// 且要等满重连退避）；白名单过滤、
# 轮换循环、闸门判定、_on_ws_ready/_auth_ok 接线一律走生产代码——测试里没有第二套轮换逻辑，
# 删掉 _report_close 的闸门会让「中间态不上报」「成功不假关闭」两条直接变红（已实跑变异验证）。
#
# 同时锁住两条 AGENTS 红线（本项不得触碰）：弹幕 WS 不跟随系统代理（proxy 一律 None）；
# 单 host 重连预算 max_reconnect=2 / reconnect_interval=3.0 / connect_timeout=8.0 与 backup_url
# 主备通道保持原样（两套轮换机制并存是既有形态，本次只收口上报语义）。

from collections.abc import Callable
from typing import Any

import pytest

from src.platforms import bilibili

_EXHAUST_REASON = "重连超过最大次数，与服务器断开连接: stub"
_HOST_A = "a.chat.bilibili.com"
_HOST_B = "b.chat.bilibili.com"
_HOST_C = "c.chat.bilibili.com"


class _StubWs:
    # WsClient 替身：只替换「敲一个 host 的连、然后按脚本回报」这一步。
    # script：'ok' 触发 on_ready（会话建成）；'exhaust' 触发 on_close（重连耗尽）；
    # 'auth_reject' 复刻 _reject_auth 终态（先置 DanmakuBase._stopped，再上报关闭）。

    def __init__(self, **kwargs: Any) -> None:
        self.kwargs: dict[str, Any] = kwargs
        self.script: str = "exhaust"
        self.client: Any = None
        self.connect_called: int = 0
        self.closed: int = 0

    def _fire(self, name: str, *args: object) -> None:
        callback: Callable[..., object] | None = self.kwargs.get(name)
        if callable(callback):
            callback(*args)

    async def connect(self) -> None:
        self.connect_called += 1
        if self.script == "ok":
            self._fire("on_ready")
            return
        if self.script == "auth_reject":
            # 生产里 _reject_auth 置 _stopped=True 后经 WsClient.fail() 上报（MID-2245）。
            if self.client is not None:
                self.client._stopped = True
            self._fire("on_close", "进房认证被拒（AUTH_REPLY 非 0 或超时未回应）")
            return
        self._fire("on_close", _EXHAUST_REASON)

    async def send(self, data: "bytes | str") -> None:
        return None

    def send_nowait(self, data: "bytes | str") -> None:
        return None

    async def close(self) -> None:
        # WsClient.close() 的语义是「调用方主动停止」，不回调 on_close。
        self.closed += 1

    async def fail(self, reason: str = "") -> None:
        self.closed += 1
        self._fire("on_close", reason)


class _Factory:
    # 每次 WsClient(...) 构造换成一个 _StubWs，按 host 尝试顺序发放脚本结果。

    def __init__(self, scripts: list[str], client: Any, client_args: dict[str, Any]) -> None:
        self.instances: list[_StubWs] = []
        self.client_args: dict[str, Any] = client_args
        self._scripts = scripts
        self._client = client

    def __call__(self, **kwargs: Any) -> _StubWs:
        idx = len(self.instances)
        ws = _StubWs(**kwargs)
        ws.script = self._scripts[idx] if idx < len(self._scripts) else self._scripts[-1]
        ws.client = self._client
        self.instances.append(ws)
        return ws


def _noop_spawn(coro: Any) -> None:
    # 未 await 的协程必须显式 close()，否则用例结束时 GC 抛
    # RuntimeWarning: coroutine ... was never awaited（本仓 pytest 口径为 0 警告）。
    coro.close()


def _install(
    monkeypatch: pytest.MonkeyPatch, scripts: list[str], hosts: list[str]
) -> tuple[_Factory, list[str], list[int], bilibili.BilibiliDanmaku]:
    # 返回 (替身工厂, on_close 记录表, on_ready 记录表, 待 start 的弹幕客户端)。
    monkeypatch.setattr(bilibili, "spawn_danmaku_task", _noop_spawn)
    reported: list[str] = []
    connected: list[int] = []
    client = bilibili.BilibiliDanmaku(
        on_message=lambda _m: None,
        on_close=reported.append,
        on_ready=lambda: connected.append(1),
    )
    args: dict[str, Any] = {"server_host": hosts[0], "room_id": 26306423, "host_list": list(hosts)}
    factory = _Factory(scripts, client, args)
    monkeypatch.setattr(bilibili, "WsClient", factory)
    return factory, reported, connected, client


class TestHostRotationCloseGate:
    async def test_first_host_exhaustion_is_not_reported_while_candidates_remain(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # host[0] 耗尽、仍有 host[1] 未尝试 → 监控枢纽侧的 on_close 一次都不该被调。
        factory, reported, _connected, client = _install(monkeypatch, ["exhaust", "ok"], [_HOST_A, _HOST_B])
        await client.start(dict(factory.client_args))
        assert reported == [], f"host[0] 轮换中间态被当成房间关闭上报了: {reported}"

    async def test_last_host_success_reports_no_close_after_first_host_failed(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # host[1] 成功：on_close 恒空、on_ready 恰好一次，不得出现「假关闭→重连」。
        factory, reported, connected, client = _install(monkeypatch, ["exhaust", "ok"], [_HOST_A, _HOST_B])
        await client.start(dict(factory.client_args))
        assert [i.kwargs["url"] for i in factory.instances] == [
            f"wss://{_HOST_A}/sub",
            f"wss://{_HOST_B}/sub",
        ]
        assert client._session_ok is True
        assert connected == [1], f"会话就绪回调应恰好一次，实为 {connected}"
        assert reported == [], f"修复前这里是 ['重连超过最大次数…']（假关闭），实为 {reported}"

    async def test_all_hosts_exhausted_reports_exactly_once(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # 三个候选全部耗尽 → 恰好一次 room_closed（跨 WsClient 实例去重）。
        factory, reported, connected, client = _install(
            monkeypatch, ["exhaust", "exhaust", "exhaust"], [_HOST_A, _HOST_B, _HOST_C]
        )
        await client.start(dict(factory.client_args))
        assert len(factory.instances) == 3, "所有候选都应被尝试过（单 host 固定会卡死）"
        assert connected == []
        assert client._session_ok is False
        assert reported == [_EXHAUST_REASON], f"全部耗尽应恰好上报一次，实为 {reported}"

    async def test_close_callback_is_gated_even_for_single_host(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # 只有一个候选时没有「未尝试的候选」可言，耗尽就是终态 → 必须上报（闸门不得一律消音）。
        factory, reported, _connected, client = _install(monkeypatch, ["exhaust"], [_HOST_A])
        await client.start(dict(factory.client_args))
        assert reported == [_EXHAUST_REASON]

    async def test_auth_reject_is_terminal_and_still_reported(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # MID-2245 红线：_reject_auth（进房认证被拒）会置 _stopped，属终态——即便后面还有候选 host
        # 未尝试也必须上报，否则监控页永久停在「已连接 / 0 条」。闸门只压「轮换中间态」。
        factory, reported, _connected, client = _install(monkeypatch, ["auth_reject", "exhaust"], [_HOST_A, _HOST_B])
        await client.start(dict(factory.client_args))
        assert reported == ["进房认证被拒（AUTH_REPLY 非 0 或超时未回应）"], reported
        assert len(factory.instances) == 1, "认证被拒是终态，不得继续敲下一个 host"

    async def test_mid_session_exhaustion_after_successful_session_reports(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # 会话建成后再断线（生产里由该 WsClient 自己耗尽重连触发 on_close）：轮换已结束，
        # _hosts_left 必须已归零，否则这条真实关闭会被闸门吞掉（回到 MID-2245 观感）。
        factory, reported, _connected, client = _install(monkeypatch, ["ok"], [_HOST_A, _HOST_B])
        await client.start(dict(factory.client_args))
        assert reported == []
        assert client._hosts_left == 0, "轮换结束后仍留有未尝试计数，真实断连会被吞掉"

        on_close: Callable[[str], None] = factory.instances[0].kwargs["on_close"]
        on_close(_EXHAUST_REASON)
        assert reported == [_EXHAUST_REASON]
        # 同一会话的重复上报仍被去重（跨实例保护同样适用）。
        on_close("再次耗尽")
        assert reported == [_EXHAUST_REASON]

    async def test_stop_does_not_report_close(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # 调用方主动停止（采集线程收尾）走 WsClient.close()，不是「房间关闭」事件。
        factory, reported, _connected, client = _install(monkeypatch, ["ok"], [_HOST_A])
        await client.start(dict(factory.client_args))
        await client.stop()
        assert reported == []
        assert factory.instances[0].closed == 1

    async def test_early_returns_report_once(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # 两条早退路径（缺参 / 白名单全滤空）本就是终态：各上报一次，且都走同一个闸门出口。
        reported: list[str] = []
        client = bilibili.BilibiliDanmaku(on_message=lambda _m: None, on_close=reported.append)
        await client.start({"room_id": 1})
        assert reported == ["缺少 server_host/room_id"]

        reported.clear()
        monkeypatch.setattr(bilibili, "spawn_danmaku_task", _noop_spawn)
        client2 = bilibili.BilibiliDanmaku(on_message=lambda _m: None, on_close=reported.append)
        await client2.start({"server_host": "evil.example.com", "room_id": 1, "host_list": ["evil.example.com"]})
        assert reported == ["无可用弹幕服务器（host 均不在 B站官方域白名单内）"], reported
        assert client2._session_ok is False


class TestRotationCallSiteContractUnchanged:
    # 本项修复的边界：轮换节奏与代理语义一个字都不动。

    async def test_backup_url_and_reconnect_budget_unchanged(self, monkeypatch: pytest.MonkeyPatch) -> None:
        factory, _reported, _connected, client = _install(monkeypatch, ["exhaust", "exhaust"], [_HOST_A, _HOST_B])
        await client.start(dict(factory.client_args))
        first, second = factory.instances[0], factory.instances[1]
        # 备地址随下一个 host 注入，重连时才会切过去（WsClient 内部主备通道保持原样）。
        assert first.kwargs["backup_url"] == f"wss://{_HOST_B}/sub"
        assert second.kwargs["backup_url"] is None
        for ws in factory.instances:
            assert ws.kwargs["max_reconnect"] == 2
            assert ws.kwargs["reconnect_interval"] == 3.0
            assert ws.kwargs["connect_timeout"] == 8.0
            # AGENTS 红线：弹幕 WS 绝不跟随系统代理（未显式传 ⇒ WsClient 默认 proxy=None）。
            assert ws.kwargs.get("proxy", None) is None

    async def test_on_close_hook_is_the_gate_not_the_raw_callback(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # 接线锁：挂给 WsClient 的必须是闸门方法本身。裸挂 self._on_close 正是修复前的形态，
        # 该断言让「退回原写法」在结构层面也被抓住（与上面三条行为断言互为见证）。
        factory, _reported, _connected, client = _install(monkeypatch, ["exhaust"], [_HOST_A])
        await client.start(dict(factory.client_args))
        hook = factory.instances[0].kwargs["on_close"]
        assert hook == client._report_close

    async def test_on_reconnect_still_uses_base_debug_callback(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # 重连是中间态，走 DanmakuBase._on_reconnect（只记 debug、不上报关闭）——这条既有口径不得改。
        factory, _reported, _connected, client = _install(monkeypatch, ["exhaust"], [_HOST_A])
        await client.start(dict(factory.client_args))
        assert factory.instances[0].kwargs["on_reconnect"] == client._on_reconnect


class TestGateIsPerSession:
    async def test_new_session_rearms_the_once_only_flag(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # 采集器每轮新建实例，但同一实例被重启时不得被上一轮的 _close_reported 永久消音。
        factory, reported, _connected, client = _install(monkeypatch, ["exhaust"], [_HOST_A])
        await client.start(dict(factory.client_args))
        assert reported == [_EXHAUST_REASON]
        client._stopped = False
        await client.start(dict(factory.client_args))
        assert len(reported) == 2, f"第二次会话的关闭事件被上一轮标记吞掉了: {reported}"
