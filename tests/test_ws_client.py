# WsClient 断连后悬挂引用与后台发送任务回归（CODE_REVIEW_2026-09-20 的 MIN-12 / MIN-13）。
#
# 全部离线：websockets.connect 被替换为假上下文管理器，不发任何真实网络请求。
#
#   ① MIN-12：connect() 末尾的 `self._ws` 清理块是不可达死代码（四条出口全是
#      break/continue），导致重连退避期间 `_ws` 仍指向**已关闭**连接，而 send()/
#      send_nowait() 只判 `is None` → 进房包与心跳全打在死连接上，异常被吞成一条 debug，
#      表现为「重连成功却再也不推弹幕」且无线索。现由 try/finally 摘引用 + 发送前判活。
#   ② MIN-13：send_nowait 原为裸 asyncio.ensure_future —— 无强引用（asyncio 只弱引用
#      任务）、异常无人取走、_send_lock 被占时无界堆积。现走 base.spawn_danmaku_task
#      + _pending 集合 + 上限。
#
# 2026-09-22 追加（CODE_REVIEW_2026-09-22）：
#   ③ SEV-2217：on_close / on_reconnect 的文案必须已脱敏——websockets 的 InvalidProxy
#      文本自带代理原串（含 user:pass@host），而 reason 会一路进轮转日志与监控枢纽。
#   ④ MID-2232：重连计数不得「连上即重置」，否则「握手成功即被断开」的形态让
#      max_reconnect 永不耗尽、on_close 永不上报，且每 ~5s 连击平台。

import asyncio
import contextlib
import types
from typing import Any, cast

import pytest

import src.ws_client as ws_client_module
from src.ws_client import WsClient


class _ClosedState:
    # 模拟 websockets 的 State 枚举成员（只用到 .name）
    name = "CLOSED"


class _OpenState:
    name = "OPEN"


class _FakeWs:
    # 假底层连接：按脚本决定「抛异常退出」或「正常空流退出」，并记录 send/close 调用。
    def __init__(self, raise_on_iter: bool) -> None:
        self._raise_on_iter = raise_on_iter
        self.sent: list[Any] = []
        self.closed = 0
        self.state: Any = _OpenState()

    async def send(self, data: Any) -> None:
        self.sent.append(data)

    async def close(self) -> None:
        self.closed += 1
        self.state = _ClosedState()

    def __aiter__(self) -> "_FakeWs":
        return self

    async def __anext__(self) -> bytes:
        if self._raise_on_iter:
            raise ConnectionResetError("peer reset")
        # 空流：模拟对端正常关闭（onDone）后 async for 自然结束
        raise StopAsyncIteration


class _FakeCtx:
    def __init__(self, ws: _FakeWs) -> None:
        self._ws = ws

    async def __aenter__(self) -> _FakeWs:
        return self._ws

    async def __aexit__(self, *exc: Any) -> None:
        # `async with` 负责关闭：真实现里退出即已 close，故 _ws 悬挂时指向的是死连接
        await self._ws.close()


def _install_fake_connect(monkeypatch: pytest.MonkeyPatch, raise_on_iter: bool) -> _FakeWs:
    ws = _FakeWs(raise_on_iter)

    def _fake_connect(*args: Any, **kwargs: Any) -> _FakeCtx:
        return _FakeCtx(ws)

    # MID-66：setattr 到 websockets 模块本体等于全进程换掉 connect（同会话其它用例的真实
    # 连接会吃到假实现），须走浅拷贝替身只替换 ws_client 命名空间里的全局名。
    _ws_shim = types.SimpleNamespace(**vars(ws_client_module.websockets))
    _ws_shim.connect = _fake_connect
    monkeypatch.setattr(ws_client_module, "websockets", _ws_shim)
    return ws


def _make_client(on_reconnect: Any = None) -> WsClient:
    return WsClient(
        url="ws://example.invalid/ws",
        on_message=lambda _d: None,
        on_reconnect=on_reconnect,
        heartbeat_interval=1000.0,  # 心跳不参与本文件断言，压到最大避免干扰
        max_reconnect=1,
        reconnect_interval=30.0,  # 退避足够长：on_reconnect 观察点必然落在 sleep 期间
    )


@pytest.mark.parametrize("raise_on_iter", [True, False], ids=["异常断开", "正常空流"])
async def test_ws_reference_cleared_before_reconnect_backoff(
    monkeypatch: pytest.MonkeyPatch, raise_on_iter: bool
) -> None:
    # 观察点设在 on_reconnect 回调内：它恰好在「进入 await asyncio.sleep(退避) 之前」被调用。
    # 旧实现此刻 self._ws 仍指向刚被关闭的连接（清理块不可达）→ 断言失败。
    observed: list[Any] = []

    def _on_reconnect(reason: str) -> None:
        observed.append(reason)

    _install_fake_connect(monkeypatch, raise_on_iter)
    client = _make_client(on_reconnect=_on_reconnect)
    # 第一轮退避后第二轮会耗尽 max_reconnect → on_close → 退出；用 close 回调终止等待
    closed: list[str] = []
    client._on_close = lambda reason: closed.append(reason)

    task = asyncio.create_task(client.connect())
    for _ in range(200):
        if observed:
            break
        await asyncio.sleep(0.01)
    assert observed, "未进入重连分支，观察点未命中"
    # 关键断言：退避等待期间不得保留已关闭连接的引用
    assert client._ws is None, f"重连退避期间 _ws 仍悬挂: {client._ws!r}"
    # 死连接上不该再有任何写入
    assert client._pending == set()

    await client.close()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


async def test_send_nowait_keeps_strong_task_reference(monkeypatch: pytest.MonkeyPatch) -> None:
    # MIN-13：任务必须被 self._pending 强引用持有，并在完成后自动回收
    _install_fake_connect(monkeypatch, raise_on_iter=False)
    client = _make_client()
    ws = _FakeWs(raise_on_iter=False)
    cast(Any, client)._ws = ws

    client.send_nowait(b"join-room")
    assert len(client._pending) == 1, "send_nowait 未持任务强引用（裸 ensure_future）"
    task = next(iter(client._pending))
    assert asyncio.isfuture(task)
    await asyncio.sleep(0.05)
    assert ws.sent == [b"join-room"]
    assert client._pending == set(), "完成的任务未被 done_callback 回收"


async def test_send_nowait_bounded_when_backlog_full(monkeypatch: pytest.MonkeyPatch) -> None:
    # _send_lock 被长期占住时，在途任务不得无界堆积：触顶即丢弃并告警
    _install_fake_connect(monkeypatch, raise_on_iter=False)
    monkeypatch.setattr(ws_client_module, "_MAX_PENDING_SENDS", 1)
    client = _make_client()
    ws = _FakeWs(raise_on_iter=False)
    cast(Any, client)._ws = ws

    blocker = asyncio.Event()

    async def _blocked_send(_data: Any) -> None:
        await blocker.wait()

    cast(Any, client).send = _blocked_send
    client.send_nowait(b"first")
    client.send_nowait(b"second")
    assert len(client._pending) == 1, "堆积上限未生效，任务数继续无界增长"
    blocker.set()
    await asyncio.sleep(0.05)
    assert client._pending == set()


async def test_send_skips_connection_that_is_not_open(monkeypatch: pytest.MonkeyPatch) -> None:
    # MIN-12 第二道防线：state 非 OPEN 时不得写入（send / send_nowait 两条口）
    _install_fake_connect(monkeypatch, raise_on_iter=False)
    client = _make_client()
    ws = _FakeWs(raise_on_iter=False)
    ws.state = _ClosedState()
    cast(Any, client)._ws = ws

    client.send_nowait(b"heartbeat")
    await client.send(b"heartbeat")
    await asyncio.sleep(0.05)
    assert ws.sent == []


async def test_send_still_works_without_state_attribute(monkeypatch: pytest.MonkeyPatch) -> None:
    # 兼容性：既有各平台/用例的 ws 桩没有 state 属性，判活须乐观放行（否则弹幕全哑）
    _install_fake_connect(monkeypatch, raise_on_iter=False)
    client = _make_client()

    class _Legacy:
        def __init__(self) -> None:
            self.sent: list[Any] = []

        async def send(self, data: Any) -> None:
            self.sent.append(data)

        async def close(self) -> None:
            return None

    ws = _Legacy()
    cast(Any, client)._ws = ws
    client.send_nowait(b"enter")
    await asyncio.sleep(0.05)
    assert ws.sent == [b"enter"]


# ---------------------------------------------------------------------------
# 2026-09-22 追加：SEV-2217（回调文案脱敏）与 MID-2232（重连计数「连上即重置」）
# ---------------------------------------------------------------------------


class _FlappingWs:
    # 「连上即断」的底层连接替身：__anext__ 立刻抛错，且**不投任何应用层帧**。
    # 真实形态：房间结束 / 被踢 / 鉴权软拒绝 / B站 uid 用错的 1006 硬断连——
    # TCP + WS 握手全部成功，随后服务端立即关连接（旧实现正是在这里把计数归零）。
    def __init__(self, exc: BaseException | None = None) -> None:
        self.state: Any = _OpenState()
        self.closed = 0
        self._exc = exc or ConnectionResetError("peer reset")

    async def send(self, data: Any) -> None:
        return None

    async def close(self) -> None:
        self.closed += 1
        self.state = _ClosedState()

    def __aiter__(self) -> "_FlappingWs":
        return self

    async def __anext__(self) -> bytes:
        raise self._exc


class _FrameThenDropWs(_FlappingWs):
    # 每轮先投 frames 个应用层帧再断开：代表「这条连接真在推弹幕」的健康会话，
    # 是 MID-2232 判据 ①（收到应用层帧即算健康）的唯一触发方式。
    def __init__(self, frames: int = 1, exc: BaseException | None = None) -> None:
        super().__init__(exc)
        self._frames = frames

    async def __anext__(self) -> bytes:
        if self._frames > 0:
            self._frames -= 1
            return b"\x00"
        return await super().__anext__()


def _install_connect_factory(monkeypatch: pytest.MonkeyPatch, make_ws: Any) -> None:
    # 与 _install_fake_connect 同一 MID-66 口径（浅拷贝替身只换 ws_client 命名空间里的
    # 全局名，不 patch websockets 模块本体），区别是**每次重连新建一支**假连接：
    # 断连类用例必须让每一轮都拿到全新的帧计数，复用同一支会让第二轮失去帧。
    shim = types.SimpleNamespace(**vars(ws_client_module.websockets))
    shim.connect = lambda *args, **kwargs: _FakeCtx(make_ws())
    monkeypatch.setattr(ws_client_module, "websockets", shim)


async def test_flapping_handshake_exhausts_reconnect_and_reports_close_once(monkeypatch: pytest.MonkeyPatch) -> None:
    # MID-2232 主锁：连上即断时 max_reconnect 必须真的被耗尽，并**只**回调一次 on_close。
    # 旧实现 `self._reconnect_count = 0  # 连上即重置` 让计数每轮从 1 加起、下一轮又归零，
    # 于是本用例的 connect() 永不返回（wait_for 超时），监控页停留在「已连接 / 0 条」。
    reconnects: list[str] = []
    closes: list[str] = []
    _install_connect_factory(monkeypatch, lambda: _FlappingWs())
    client = WsClient(
        url="ws://example.invalid/ws",
        on_message=lambda _d: None,
        on_reconnect=reconnects.append,
        on_close=closes.append,
        heartbeat_interval=1000.0,
        max_reconnect=2,
        reconnect_interval=0.01,
    )

    await asyncio.wait_for(client.connect(), timeout=15.0)

    assert len(reconnects) == 2, f"重连计数被握手成功重置，on_reconnect 次数异常: {len(reconnects)}"
    assert len(closes) == 1, "重连耗尽后必须恰好上报一次关闭"
    assert "重连超过最大次数" in closes[0]
    assert client._reconnect_count == 3


async def test_application_frame_resets_reconnect_count(monkeypatch: pytest.MonkeyPatch) -> None:
    # MID-2232 的反向锁（防止矫枉过正成「永不重置」）：本轮收到过应用层帧即算健康会话，
    # 计数须归零——否则一条跑了一整天的长连接最后只要抖两下就会被历史累计误判成耗尽。
    reconnects: list[str] = []
    closes: list[str] = []
    _install_connect_factory(monkeypatch, lambda: _FrameThenDropWs(frames=1))
    client = WsClient(
        url="ws://example.invalid/ws",
        on_message=lambda _d: None,
        on_reconnect=reconnects.append,
        on_close=closes.append,
        heartbeat_interval=1000.0,
        max_reconnect=1,  # 若不重置，第二轮就耗尽 → on_reconnect 只会到 1 次
        reconnect_interval=0.01,
    )

    task = asyncio.create_task(client.connect())
    try:
        deadline = asyncio.get_running_loop().time() + 15.0
        while len(reconnects) < 3 and asyncio.get_running_loop().time() < deadline:
            await asyncio.sleep(0.01)
    finally:
        await client.close()
        with contextlib.suppress(asyncio.CancelledError):
            await asyncio.wait_for(task, timeout=15.0)

    assert len(reconnects) >= 3, f"收到应用层帧的连接未重置重连计数: {reconnects}"
    assert closes == [], f"健康连接被判成耗尽: {closes}"


async def test_reconnect_and_close_reasons_have_no_proxy_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    # SEV-2217 锁：websockets 的 InvalidProxy 文本自带代理原串（含 user:pass@host），
    # 而 reason 会进 collector 的 debug 日志与监控枢纽 → 交出前必须过 mask_credentials。
    # 断言的是「凭据值消失」，不是「调用了掩码函数」。
    password = "DanmakuProxyPw9"
    exc = ConnectionResetError(f"http://proxyuser:{password}@10.0.0.1:8080 isn't a valid proxy: refused")
    reconnects: list[str] = []
    closes: list[str] = []
    _install_connect_factory(monkeypatch, lambda: _FlappingWs(exc))
    client = WsClient(
        url="ws://example.invalid/ws",
        on_message=lambda _d: None,
        on_reconnect=reconnects.append,
        on_close=closes.append,
        heartbeat_interval=1000.0,
        max_reconnect=1,
        reconnect_interval=0.01,
    )

    await asyncio.wait_for(client.connect(), timeout=15.0)

    assert len(reconnects) == 1 and len(closes) == 1, f"未走到两条回调出口: {reconnects} / {closes}"
    for text in reconnects + closes:
        assert password not in text, f"回调文案含代理口令: {text}"
        assert "proxyuser" not in text, f"回调文案含代理账号: {text}"
        assert "***@" in text, f"凭据未走掩码分支（文案疑似被截断而非脱敏）: {text}"
        # 文案仍须可读：脱敏不能把归因信息一起抹掉
        assert "isn't a valid proxy" in text
    assert "重连超过最大次数" in closes[0]
