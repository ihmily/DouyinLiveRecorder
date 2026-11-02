# tests/test_platform_danmaku_offline.py - 斗鱼 / B站 / Twitch 三个弹幕客户端的**离线**行为锁。
#
# 与真机探针（tests/test_douyu_danmaku.py、tests/test_bilibili_danmaku.py）互补：探针无网即失效，
# 本文件用构造帧驱动 decode_message，锁住历史上真出过问题的分支：
#   - 斗鱼：粘包推进必须按「整帧 = full_len + 4」，错位 4 字节会让第二帧起全部丢失；
#   - 斗鱼：only_fans 默认 False，普通观众弹幕不得被静默丢弃；
#   - B站：AUTH_REPLY(code!=0) 与「8 秒无回应」两种软拒绝都必须主动断开并失效 buvid 缓存；
#   - B站 MI-01：protover 2/3 的解压必须走限长入口（解压炸弹面）；
#   - Twitch MI-21：WebSocket 帧边界是消息不是行，跨帧半行必须缓冲后拼回；
#   - Twitch：color 标签可选（未设色观众不得被丢弃）、纯黑回退白。
#
# Mock 口径：只替换各平台模块内的 WsClient / spawn_danmaku_task 全局引用，事件循环保留真实
# asyncio（用短超时，不 sleep 真实 8 秒）。

import asyncio
import json
import struct
import zlib
from pathlib import Path
from typing import Any, cast

import brotli
import pytest

import src.platforms.bilibili as bilibili
import src.platforms.douyu as douyu
import src.platforms.twitch as twitch
from src.base import DanmakuMessageType

# 三个平台的「收包 → 解帧 → 分发」三段式同构于 DanmakuBase，故按「平台 × 阶段」而非缺陷编号组织。
#
# 阶段一「帧边界」：三种传输的假定完全不同。
#   斗鱼：二进制帧，长度域值 = 帧总长 - 4（协议定义如此），粘包推进必须按 full_len + 4；漏掉这
#     4 字节会让第二帧起点错位、长度域读出垃圾值后截断 break（高热度直播间必然粘包）。
#   B站：16 字节大头序帧头 [包长][头长][protover][op][seq]，包长含头自身。
#   Twitch：IRC 文本，但 WebSocket 边界是「消息」不是「行」，必须自做跨帧行缓冲（MI-21）；
#     本文件用「一条完整行切两半投递」直接验证。
#
# 阶段二「载荷解码」：
#   斗鱼 STT：@= 键值、// 分段、@A/@S 转义；转义必须先于分列，否则含斜杠的值会被误切成多字段。
#   B站：protover 1/2/3 三条解压路径都走限长入口（MI-01）——高压缩比会把几百 KB 帧展开成
#     GB 级对象，而本进程同时还在跑录制。
#
# 阶段三「业务分发」：异常帧不得外溢（只记一条带帧头 hex 的 debug），毒消息带崩连接会退化成
# 重连风暴。
#
# 三个容易被改错的行为契约：
#   1) 斗鱼 only_fans 默认 False——写成 True 会让普通观众弹幕静默丢弃，且无开关可关。
#   2) B站进房包的 uid 必须是观众自身 uid（匿名 0）；传主播 uid 会被 AUTH 后硬断连（1006）。
#   3) B站看门狗与 _auth_ok 成对：每次新连接都要清零 _auth_ok，否则重连后看门狗误判「已认证」而永
#      不兜底。
#
# Mock 口径：各平台模块内的 WsClient 换为 FakeWs（只看连接参数与发出的帧），spawn_danmaku_task
# 换为记录器或 _noop_spawn；后者必须 close() 传入的协程，否则未 await 的协程在 GC 时抛
# RuntimeWarning，打爆本仓「0 警告」门禁。


class FakeWs:
    # WsClient 的最小替身：记录发出的帧，不触碰网络。
    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs
        self.sent: list[bytes | str] = []
        self.nowait: list[bytes | str] = []
        self.closed = 0
        self.fail_reasons: list[str] = []
        self.connect_called = 0

    async def connect(self) -> None:
        self.connect_called += 1

    async def send(self, data: "bytes | str") -> None:
        self.sent.append(data)

    def send_nowait(self, data: "bytes | str") -> None:
        self.nowait.append(data)

    async def close(self) -> None:
        self.closed += 1

    async def fail(self, reason: str = "") -> None:
        # 认证被拒改走 WsClient.fail() 而不是 close()——close() 的两条
        # `if self._stopped: break` 出口都不回调 on_close，会让弹幕监控页把该房间
        # 永久停在「已连接 / 0 条」。替身必须实现同一个出口，否则测的是不存在的方法。
        self.closed += 1
        self.fail_reasons.append(reason)


class WsFactory:
    # 把每次 WsClient(...) 构造都换成 FakeWs，便于断言连接参数。
    # 用工厂而不是直接替成单例：B站会按 host_list 逐个建连，“建了几次、
    # 每次 URL 是什么”本身就是被测行为（单 host 固定会卡死）。
    def __init__(self, on_connect: Any = None) -> None:
        self.instances: list[FakeWs] = []
        self._on_connect = on_connect

    def __call__(self, **kwargs: Any) -> FakeWs:
        ws = FakeWs(**kwargs)
        if self._on_connect is not None:
            self._on_connect(ws)
        self.instances.append(ws)
        return ws


def _noop_spawn(_coro: Any) -> None:
    # 未 await 的协程必须显式 close()，否则用例结束时 GC 会抛
    # RuntimeWarning: coroutine ... was never awaited（本仓 pytest 门禁为「0 警告」）。
    _coro.close()


def _collect(target: list[Any]) -> Any:
    # 把 on_message 回调闭包成「追加到列表」：所有分发类断言都靠它把发射出去的
    # DanmakuMessage 拿回来。不用 unittest.mock.Mock 是为了断言能写到字段粒度
    # （user_name / color / type），而不是只数「被调了几次」。
    def _cb(msg: Any) -> None:
        target.append(msg)

    return _cb


# ─── 斗鱼 ────────────────────────────────────────────────────


def _douyu_frame(body: str) -> bytes:
    # 只负责把字符串装进一个合法帧（与被测 _serialize 保持独立），这样验证的是
    # 「推进步长 = full_len + 4」这条约定本身，而不是自洽地跑循环。
    body_b = body.encode("utf-8")
    total = 4 + 4 + len(body_b) + 1
    return struct.pack("<II", total, total) + struct.pack("<HBB", 689, 0, 0) + body_b + b"\x00"


# 下面的测试类按「平台 → 阶段」排，同一阶段在三个平台上的失败形态完全不同，
# 所以不能用一组参数化用例笼统盖过：
#   TestDouyuFraming / TestDouyuDispatch / TestDouyuLifecycle
#   TestBilibiliFraming / TestBilibiliMessages / TestBilibiliLifecycle
#   TestTwitchDecoding / TestTwitchLifecycle
# 「Lifecycle」三个类只验「连接参数与发送序列」，不验任何网络行为：那部分属于
# WsClient（见 tests/test_ws_client.py），在这里重测只会把两个模块的回归绑在一起。


class TestDouyuFraming:
    def test_serialize_matches_protocol_layout(self) -> None:
        frame = douyu.DouyuDanmaku._serialize("type@=mrkl/")
        body = b"type@=mrkl/"
        total = 4 + 4 + len(body) + 1
        assert frame[:8] == struct.pack("<II", total, total)
        assert frame[8:12] == struct.pack("<HBB", douyu.CLIENT_SEND_TO_SERVER, 0, 0)
        assert frame[12:-1] == body
        assert frame[-1:] == b"\x00"

    def test_stt_to_obj_variants(self) -> None:
        parse = douyu.DouyuDanmaku._stt_to_obj
        assert parse("type@=chatmsg/nn@=alice/txt@=hi") == {"type": "chatmsg", "nn": "alice", "txt": "hi"}
        assert parse("a@=1//b@=2") == [{"a": "1"}, {"b": "2"}]
        # 值里真含 @ 时下发前已转义成 @A，反转义后不应再被当成键值分隔符
        assert parse("k@=a@Ab") == {"k": "a@b"}
        assert parse("x@A=y") == {"x": "y"}
        assert parse("plain") == "plain"
        # 值里的 @S 会被还原成字面斜杠，而斜杠正是字段分隔符——因此含 @S 的值会被
        # 递归解成嵌套结构（与 dart 一致）。这条记住的是“转义先于分列”的语义。
        assert parse("k@=v@Snn@=w") == {"k": {"nn": "w"}}

    def test_unescape_order_matters(self) -> None:
        # @S→/ 与 @A→@ 的先后不能交换，否则 "@AS" 会被二次转义成 "@@" 之外的错值
        assert douyu.DouyuDanmaku._unescape("@S@A") == "/@"

    def test_decode_message_ignores_text_frames(self) -> None:
        got: list[Any] = []
        client = douyu.DouyuDanmaku(on_message=_collect(got))
        client.decode_message("type@=chatmsg/nn@=a/txt@=b/")
        assert got == []

    def test_decode_message_handles_sticky_packets(self) -> None:
        # 两帧拼接投递时第二帧必须也被解出（推进步长含首长度域自身 4 字节）
        got: list[Any] = []
        client = douyu.DouyuDanmaku(on_message=_collect(got))
        data = _douyu_frame("type@=chatmsg/nn@=alice/txt@=first/") + _douyu_frame("type@=chatmsg/nn@=bob/txt@=second/")
        client.decode_message(data)
        assert [m.user_name for m in got] == ["alice", "bob"]

    def test_decode_message_stops_at_truncated_frame(self) -> None:
        got: list[Any] = []
        client = douyu.DouyuDanmaku(on_message=_collect(got))
        good = _douyu_frame("type@=chatmsg/nn@=a/txt@=ok/")
        client.decode_message(good + b"\x0a\x00\x00\x00" + b"short")
        assert len(got) == 1

    def test_decode_message_negative_body_is_skipped(self) -> None:
        # full_len <= 9 → body_len < 0：跳过该帧而不是崩，仍要继续推进
        got: list[Any] = []
        client = douyu.DouyuDanmaku(on_message=_collect(got))
        # 正常帧的 full_len 永远 >= 9（= 4+4+body+1），本分支是对外送脏数据的防御。
        # 按协议约定帧总长 = full_len + 4，故脏帧必须恰好占 9 字节才能把下一帧对齐。
        tiny = struct.pack("<II", 5, 5) + b"\x00"
        client.decode_message(tiny + _douyu_frame("type@=chatmsg/nn@=z/txt@=ok/"))
        assert [m.user_name for m in got] == ["z"]

    def test_decode_message_swallows_frame_errors(self, monkeypatch: pytest.MonkeyPatch) -> None:
        got: list[Any] = []
        client = douyu.DouyuDanmaku(on_message=_collect(got))
        logs: list[str] = []
        monkeypatch.setattr(douyu.logger, "debug", lambda msg, *a, **k: logs.append(str(msg)))
        monkeypatch.setattr(
            douyu.DouyuDanmaku, "_stt_to_obj", staticmethod(lambda s: (_ for _ in ()).throw(ValueError("bad")))
        )
        client.decode_message(_douyu_frame("type@=chatmsg/"))
        assert got == []
        assert any("帧解析异常" in m for m in logs)


class TestDouyuDispatch:
    def test_chat_message_color_lookup_and_fallback(self) -> None:
        got: list[Any] = []
        client = douyu.DouyuDanmaku(on_message=_collect(got))
        client._dispatch(
            [
                {"type": "chatmsg", "nn": "u1", "txt": "t1", "col": "2"},
                {"type": "chatmsg", "nn": "u2", "txt": "t2", "col": "999"},
            ]
        )
        assert [m.color for m in got] == ["#1E87F0", "#FFFFFF"]
        assert [m.type for m in got] == [DanmakuMessageType.CHAT, DanmakuMessageType.CHAT]

    def test_bad_color_value_falls_back_to_default(self) -> None:
        got: list[Any] = []
        client = douyu.DouyuDanmaku(on_message=_collect(got))
        client._dispatch({"type": "chatmsg", "nn": "u", "txt": "t", "col": object()})
        assert got[0].color == "#FFFFFF"

    def test_only_fans_filter_is_opt_in(self) -> None:
        # 默认不过滤——把默认值改回 True 会在这里变红。
        got: list[Any] = []
        default_client = douyu.DouyuDanmaku(on_message=_collect(got))
        default_client._dispatch({"type": "chatmsg", "nn": "guest", "txt": "hi", "if": "0"})
        assert [m.user_name for m in got] == ["guest"]

        fans_only: list[Any] = []
        douyu.DouyuDanmaku(on_message=_collect(fans_only), only_fans=True)._dispatch(
            {"type": "chatmsg", "nn": "guest", "txt": "hi", "if": "0"}
        )
        assert fans_only == []

    def test_non_dict_and_other_types_are_ignored(self) -> None:
        got: list[Any] = []
        client = douyu.DouyuDanmaku(on_message=_collect(got))
        client._dispatch(["scalar", {"type": "uenter", "nn": "x"}, {"nomsg": 1}])
        assert got == []


class TestDouyuLifecycle:
    # 生命周期类只验「连接参数 + 发送序列 + 停机标志」：
    #   start 要同对两种入参形态（dict / 裸字符串）——main 与 Web 面板送进来的形状不同；
    #   缺 room_id 必须走 on_close 而不是抛异常（否则一个坏配置会抬走整条采集线）；
    #   stop 必须置 _stopped 并 close，否则房间下线后 WsClient 的重连循环还在跑。
    async def test_start_from_dict_builds_client(self, monkeypatch: pytest.MonkeyPatch) -> None:
        factory = WsFactory()
        monkeypatch.setattr(douyu, "WsClient", factory)
        client = douyu.DouyuDanmaku()
        await client.start({"room_id": "3125893"})
        assert client._room_id == "3125893"
        assert factory.instances[0].kwargs["url"] == douyu.SERVER_URL
        assert factory.instances[0].connect_called == 1

    async def test_start_from_plain_string(self, monkeypatch: pytest.MonkeyPatch) -> None:
        factory = WsFactory()
        monkeypatch.setattr(douyu, "WsClient", factory)
        client = douyu.DouyuDanmaku()
        await client.start("888")
        assert client._room_id == "888"

    async def test_start_without_room_id_closes(self) -> None:
        reasons: list[str] = []
        client = douyu.DouyuDanmaku(on_close=reasons.append)
        await client.start({"room_id": ""})
        assert reasons == ["缺少 room_id"]

    def test_ws_ready_triggers_join_room(self, monkeypatch: pytest.MonkeyPatch) -> None:
        spawned: list[Any] = []
        monkeypatch.setattr(douyu, "spawn_danmaku_task", spawned.append)
        ready: list[int] = []
        client = douyu.DouyuDanmaku(on_ready=lambda: ready.append(1))
        client._ws = cast(Any, FakeWs())
        client._room_id = "1"
        client._on_ws_ready()
        assert ready == [1]
        assert len(spawned) == 1
        spawned[0].close()

    async def test_join_room_and_heartbeat_send_expected_frames(self) -> None:
        ws = FakeWs()
        client = douyu.DouyuDanmaku()
        client._ws = cast(Any, ws)
        client._room_id = "42"
        await client._join_room()
        # 斗鱼走二进制帧（WsClient.send 的入参型是 bytes | str），按帧头 12B + 尾 0x00 取回正文
        bodies = [cast(bytes, d)[12:-1].decode() for d in ws.sent[:2]]
        assert bodies == [
            "type@=loginreq/roomid@=42/",
            "type@=joingroup/rid@=42/gid@=-9999/",
        ]
        await client.heartbeat()
        assert cast(bytes, ws.sent[-1])[12:-1].decode() == "type@=mrkl/"

    async def test_join_room_without_ws_is_noop(self) -> None:
        client = douyu.DouyuDanmaku()
        await client._join_room()
        await client.heartbeat()
        await client.stop()

    async def test_stop_closes_connection(self, monkeypatch: pytest.MonkeyPatch) -> None:
        factory = WsFactory()
        monkeypatch.setattr(douyu, "WsClient", factory)
        client = douyu.DouyuDanmaku()
        await client.start("1")
        await client.stop()
        assert client._stopped is True
        assert factory.instances[0].closed == 1


# ─── B站 ─────────────────────────────────────────────────────


def _bili_frame(body: bytes, proto_ver: int, operation: int) -> bytes:
    # 大端序 16B 帧头 [包长][头长][protover][op][seq]；包长含头自身，这一点与斗鱼
    # 的「长度域 = 帧总长 - 4」恰好相反，所以下面 decode_message 的截断判定不能照搬。
    return struct.pack(">IHHII", len(body) + 16, 16, proto_ver, operation, 1) + body


class TestBilibiliFraming:
    # 粘包、短包、非法长度三条都要分开测：它们对应 decode_message 里的三个不同
    # break/continue 出口。合并成一条「不崩」用例就丢掉了区分能力：一旦哪天
    # 三个出口里的一个被改坏，其余两个仍会过，表现为「偶发性丢弹幕」而无法定位。
    def test_encode_header_layout(self) -> None:
        frame = bilibili.BilibiliDanmaku._encode("hello", action=7)
        total, header_len, proto, op, seq = struct.unpack(">IHHII", frame[:16])
        assert (header_len, proto, op, seq) == (16, 0, 7, 1)
        assert total == 16 + len(b"hello")
        assert frame[16:] == b"hello"

    def test_decode_message_ignores_text_frames(self) -> None:
        got: list[Any] = []
        client = bilibili.BilibiliDanmaku(on_message=_collect(got))
        client.decode_message('{"cmd":"x"}')
        assert got == []

    def test_decode_message_loops_over_sticky_packets(self) -> None:
        got: list[Any] = []
        client = bilibili.BilibiliDanmaku(on_message=_collect(got))
        data = _bili_frame(struct.pack(">I", 100), 0, 3) + _bili_frame(struct.pack(">I", 250), 0, 3)
        client.decode_message(data)
        assert [m.data for m in got] == [100, 250]

    def test_decode_message_breaks_on_short_or_bogus_length(self) -> None:
        got: list[Any] = []
        client = bilibili.BilibiliDanmaku(on_message=_collect(got))
        client.decode_message(struct.pack(">IHHII", 4, 16, 0, 3, 1))
        assert got == []
        client.decode_message(b"012345678901")  # 不足 16 字节头
        assert got == []

    def test_decode_message_logs_frame_errors(self, monkeypatch: pytest.MonkeyPatch) -> None:
        logs: list[str] = []
        monkeypatch.setattr(bilibili.logger, "debug", lambda msg, *a, **k: logs.append(str(msg)))
        client = bilibili.BilibiliDanmaku()
        monkeypatch.setattr(client, "_decode_packet", lambda frame: (_ for _ in ()).throw(ValueError("bad")))
        client.decode_message(_bili_frame(b"{}", 0, 5))
        assert any("帧解析异常" in m for m in logs)

    def test_decode_packet_rejects_short_frames(self) -> None:
        got: list[Any] = []
        client = bilibili.BilibiliDanmaku(on_message=_collect(got))
        client._decode_packet(b"tiny")
        assert got == []

    def test_online_reply_is_emitted(self) -> None:
        got: list[Any] = []
        client = bilibili.BilibiliDanmaku(on_message=_collect(got))
        client._decode_packet(_bili_frame(struct.pack(">I", 4321), 0, 3))
        assert got[0].type is DanmakuMessageType.ONLINE
        assert got[0].data == 4321

    def test_online_reply_without_body_is_dropped(self) -> None:
        got: list[Any] = []
        client = bilibili.BilibiliDanmaku(on_message=_collect(got))
        client._decode_packet(_bili_frame(b"", 0, 3))
        assert got == []

    def test_auth_reply_zero_clears_watchdog(self) -> None:
        client = bilibili.BilibiliDanmaku()
        client._decode_packet(_bili_frame(json.dumps({"code": 0}).encode(), 0, 8))
        assert client._auth_ok is True

    @pytest.mark.parametrize("body", [b'{"code": -100}', b"not-json"])
    def test_auth_reply_rejection_disconnects(self, body: bytes) -> None:
        # 软拒绝（code!=0 / 非法回应）必须主动断开，否则表现为「已连接但 0 弹幕」
        client = bilibili.BilibiliDanmaku()
        client._ws = cast(Any, FakeWs())
        rejected: list[int] = []
        monkey = pytest.MonkeyPatch()
        monkey.setattr(client, "_reject_auth", lambda: rejected.append(1))
        client._decode_packet(_bili_frame(body, 0, 8))
        assert rejected == [1]
        assert client._auth_ok is False
        monkey.undo()

    def test_unknown_operation_code_is_ignored(self) -> None:
        got: list[Any] = []
        client = bilibili.BilibiliDanmaku(on_message=_collect(got))
        client._decode_packet(_bili_frame(b"{}", 0, 99))
        assert got == []

    @pytest.mark.parametrize("proto_ver", [1, 2, 3])
    def test_decompression_paths(self, proto_ver: int) -> None:
        payload = b'{"cmd":"DANMU_MSG","info":[[0,1,2,16711680],"\xe4\xbd\xa0",["9","tom"]]}'
        if proto_ver == 2:
            body = zlib.compress(payload)
        elif proto_ver == 3:
            body = brotli.compress(payload)
        else:
            body = payload
        got: list[Any] = []
        client = bilibili.BilibiliDanmaku(on_message=_collect(got))
        client._decode_packet(_bili_frame(body, proto_ver, 5))
        assert len(got) == 1
        assert got[0].user_name == "tom"
        assert got[0].color == "#FF0000"

    def test_undecompressible_payload_is_dropped(self) -> None:
        got: list[Any] = []
        client = bilibili.BilibiliDanmaku(on_message=_collect(got))
        client._decode_packet(_bili_frame(b"\x00\x01\x02garbage", 2, 5))
        assert got == []

    def test_malformed_json_item_is_logged_and_skipped(self, monkeypatch: pytest.MonkeyPatch) -> None:
        logs: list[str] = []
        monkeypatch.setattr(bilibili.logger, "debug", lambda msg, *a, **k: logs.append(str(msg)))
        got: list[Any] = []
        client = bilibili.BilibiliDanmaku(on_message=_collect(got))
        client._decode_packet(_bili_frame(b"{oops}\x1f{also bad}", 1, 5))
        assert got == []
        assert any("消息解析异常" in m for m in logs)


class TestBilibiliMessages:
    # 单条 JSON 弹幕的四种残缺形态（info 不是列表 / 长度不够 / 颜色不可转 /
    # user_info 太短）都必须「不 emit 也不抛」：抛出去会被 WsClient 当成毒消息
    # 计入重连风暴，误 emit 则会在字幕里留下空行。
    def test_danmu_msg_without_info_list_is_ignored(self) -> None:
        got: list[Any] = []
        client = bilibili.BilibiliDanmaku(on_message=_collect(got))
        client._parse_message({"cmd": "DANMU_MSG", "info": "nope"})
        client._parse_message({"cmd": "DANMU_MSG", "info": [1, 2]})
        assert got == []

    def test_danmu_msg_bad_color_falls_back(self) -> None:
        got: list[Any] = []
        client = bilibili.BilibiliDanmaku(on_message=_collect(got))
        client._parse_message({"cmd": "DANMU_MSG", "info": [[0, 1, 2, "not-int"], "hi", [7, "bob"]]})
        assert got[0].color == "#FFFFFF"

    def test_danmu_msg_short_user_info_is_ignored(self) -> None:
        got: list[Any] = []
        client = bilibili.BilibiliDanmaku(on_message=_collect(got))
        client._parse_message({"cmd": "DANMU_MSG", "info": [[0, 1, 2, 0], "hi", ["only-one"]]})
        assert got == []

    def test_super_chat_is_emitted(self) -> None:
        got: list[Any] = []
        client = bilibili.BilibiliDanmaku(on_message=_collect(got))
        client._parse_message({"cmd": "SUPER_CHAT_MESSAGE", "data": {"message": "yo", "user_info": {"uname": "rich"}}})
        assert got[0].type is DanmakuMessageType.SUPER_CHAT
        assert got[0].user_name == "rich"

    def test_super_chat_without_data_is_ignored(self) -> None:
        got: list[Any] = []
        client = bilibili.BilibiliDanmaku(on_message=_collect(got))
        client._parse_message({"cmd": "SUPER_CHAT_MESSAGE", "data": {}})
        assert got == []

    def test_unrelated_command_is_ignored(self) -> None:
        got: list[Any] = []
        client = bilibili.BilibiliDanmaku(on_message=_collect(got))
        client._parse_message({"cmd": "LIVE", "data": {}})
        assert got == []


class TestBilibiliLifecycle:
    async def test_missing_params_closes(self) -> None:
        reasons: list[str] = []
        client = bilibili.BilibiliDanmaku(on_close=reasons.append)
        await client.start({"room_id": 1})
        assert reasons == ["缺少 server_host/room_id"]

    async def test_every_host_is_attempted_until_list_exhausted(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # 单 host 固定会卡死：所有候选地址都连不上时要轮流试完才能退出循环。
        # 用官方域形态的 host（该白名单只放行 B站官方域族；非白名单 host 会被跳过而非尝试）。
        factory = WsFactory()
        monkeypatch.setattr(bilibili, "WsClient", factory)
        client = bilibili.BilibiliDanmaku()
        await client.start(
            {
                "server_host": "a.chat.bilibili.com",
                "room_id": 1,
                "host_list": ["a.chat.bilibili.com", "b.chat.bilibili.com"],
            }
        )
        assert [i.kwargs["url"] for i in factory.instances] == [
            "wss://a.chat.bilibili.com/sub",
            "wss://b.chat.bilibili.com/sub",
        ]
        assert client._session_ok is False
        # 备地址随下一个 host 注入，重连时才会切过去
        assert factory.instances[0].kwargs["backup_url"] == "wss://b.chat.bilibili.com/sub"
        assert factory.instances[1].kwargs["backup_url"] is None

    async def test_loop_breaks_as_soon_as_session_is_ok(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # 第一条 host 就建成会话时不得再去敲后面的 host（否则一次成功会多打 N 次握手）。
        # 另外：「host_list 全空 + server_host 非空」时 server_host 会被插回首位，
        # 仍能建连（_AUTH_TIMEOUT 分支之外的另一条兼容性）。
        factory = WsFactory()
        monkeypatch.setattr(bilibili, "WsClient", factory)
        monkeypatch.setattr(bilibili, "spawn_danmaku_task", _noop_spawn)
        client = bilibili.BilibiliDanmaku()

        original_connect = FakeWs.connect

        async def connect_then_ready(self: FakeWs) -> None:
            await original_connect(self)
            cast(Any, self.kwargs["on_ready"])()

        monkeypatch.setattr(FakeWs, "connect", connect_then_ready)
        await client.start({"server_host": "a.chat.bilibili.com", "room_id": 1, "host_list": [""]})
        assert [i.kwargs["url"] for i in factory.instances] == ["wss://a.chat.bilibili.com/sub"]
        assert client._session_ok is True
        assert client._auth_ok is False

    async def test_stopped_client_stops_trying(self, monkeypatch: pytest.MonkeyPatch) -> None:
        factory = WsFactory()
        monkeypatch.setattr(bilibili, "WsClient", factory)
        client = bilibili.BilibiliDanmaku()
        client._stopped = True
        await client.start({"server_host": "a", "room_id": 1})
        assert factory.instances == []

    def test_ws_ready_resets_auth_flag(self, monkeypatch: pytest.MonkeyPatch) -> None:
        spawned: list[Any] = []
        monkeypatch.setattr(bilibili, "spawn_danmaku_task", spawned.append)
        client = bilibili.BilibiliDanmaku()
        client._auth_ok = True
        ready: list[int] = []
        client._on_ready = lambda: ready.append(1)
        client._on_ws_ready()
        # 重连必须重新过 AUTH，否则看门狗会被上一轮的 _auth_ok 永久屏蔽
        assert client._auth_ok is False
        assert client._session_ok is True
        assert ready == [1]
        spawned[0].close()

    async def test_join_room_derives_viewer_uid_and_sends_auth(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(bilibili, "spawn_danmaku_task", _noop_spawn)
        ws = FakeWs()
        client = bilibili.BilibiliDanmaku()
        client._ws = cast(Any, ws)
        client._args = {
            "cookie": "buvid3=x; DedeUserID=12345; SESSDATA=y",
            "room_id": "9527",
            "token": "TK",
            "buvid": "BV",
        }
        await client._join_room()
        frame = cast(bytes, ws.sent[0])
        body = json.loads(frame[16:].decode())
        assert body["uid"] == 12345
        assert body["roomid"] == 9527
        assert body["key"] == "TK"
        assert body["buvid"] == "BV"

    async def test_join_room_anonymous_uid_zero(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # 传主播 uid 会被弹幕服务器硬断连（1006），匿名必须是 0 —— 这条不能退化成取 args["uid"]
        monkeypatch.setattr(bilibili, "spawn_danmaku_task", _noop_spawn)
        ws = FakeWs()
        client = bilibili.BilibiliDanmaku()
        client._ws = cast(Any, ws)
        client._args = {"room_id": 1, "uid": 777}
        await client._join_room()
        assert json.loads(cast(bytes, ws.sent[0])[16:].decode())["uid"] == 0

    async def test_join_room_without_ws_is_noop(self) -> None:
        await bilibili.BilibiliDanmaku()._join_room()

    async def test_auth_watchdog_fires_when_not_authenticated(self, monkeypatch: pytest.MonkeyPatch) -> None:
        ws = FakeWs()
        client = bilibili.BilibiliDanmaku()
        client._ws = cast(Any, ws)
        monkeypatch.setattr(bilibili.BilibiliDanmaku, "_AUTH_TIMEOUT", 0.01)
        rejected: list[int] = []
        monkeypatch.setattr(client, "_reject_auth", lambda: rejected.append(1))
        await client._auth_watchdog(cast(Any, ws))
        assert rejected == [1]

    async def test_auth_watchdog_is_cancelled_by_success_or_host_switch(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(bilibili.BilibiliDanmaku, "_AUTH_TIMEOUT", 0.01)
        ws = FakeWs()
        client = bilibili.BilibiliDanmaku()
        client._ws = cast(Any, ws)
        rejected: list[int] = []
        monkeypatch.setattr(client, "_reject_auth", lambda: rejected.append(1))
        client._auth_ok = True
        await client._auth_watchdog(cast(Any, ws))
        assert rejected == []
        client._auth_ok = False
        client._stopped = True
        await client._auth_watchdog(cast(Any, ws))
        assert rejected == []
        client._stopped = False
        client._ws = cast(Any, FakeWs())  # 已切到下一条 host，旧看门狗作废
        await client._auth_watchdog(cast(Any, ws))
        assert rejected == []

    async def test_reject_auth_closes_ws_and_invalidates_buvid(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import src.spider as spider

        ws = FakeWs()
        client = bilibili.BilibiliDanmaku()
        client._ws = cast(Any, ws)
        invalidated: list[int] = []
        monkeypatch.setattr(spider, "invalidate_bili_buvid_cache", lambda: invalidated.append(1))
        # _reject_auth 用 ensure_future 发关停任务（它总是跑在收包循环里），
        # 因此本用例必须是 async，否则 3.14 下 get_event_loop 会直接报错。
        client._reject_auth()
        await asyncio.sleep(0)
        assert client._stopped is True
        assert invalidated == [1]
        assert ws.closed == 1
        # 只断言 closed 会把「退回 close()」这一实现放过去（它同样让 closed 计数 +1），
        # 而监控页残留「已连接 / 0 条」正是该要消灭的形态——必须断言走的是带上报的 fail()。
        assert ws.fail_reasons and ws.fail_reasons[0], "认证被拒未走 WsClient.fail()，on_close 不会上报"

    async def test_reject_auth_survives_buvid_invalidation_failure(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # 缓存失效只是“顺手优化”，失败不得把断开流程带崩——它已经在退出路径上。
        import src.spider as spider

        def boom() -> None:
            raise RuntimeError("cache lock lost")

        monkeypatch.setattr(spider, "invalidate_bili_buvid_cache", boom)
        client = bilibili.BilibiliDanmaku()
        client._reject_auth()
        await asyncio.sleep(0)
        assert client._stopped is True

    async def test_heartbeat_and_stop(self) -> None:
        ws = FakeWs()
        client = bilibili.BilibiliDanmaku()
        client._ws = cast(Any, ws)
        await client.heartbeat()
        assert struct.unpack(">IHHII", cast(bytes, ws.sent[0])[:16])[3] == 2
        await client.stop()
        assert client._stopped is True and ws.closed == 1
        await bilibili.BilibiliDanmaku().heartbeat()
        await bilibili.BilibiliDanmaku().stop()

    def test_header_constant_is_shared(self) -> None:
        source = (Path(__file__).resolve().parents[1] / "src" / "platforms" / "bilibili.py").read_text(encoding="utf-8")
        assert "HEADER_LEN = 16" in source
        assert bilibili.HEADER_LEN == 16


# ─── Twitch ──────────────────────────────────────────────────

TWITCH_PRIVMSG = (
    "@badge-info=;color=#123456;display-name=alice;emotes=;tmi-sent-ts=1:"
    "#chan :alice!alice@alice.tmi.twitch.tv PRIVMSG #chan :hello world"
)


class TestTwitchDecoding:
    # IRC 文本侧的四条色彩分支：带色 / color= 为空 / 纯黑 / 非法 hex。
    # 后三条共同指向同一个出口 #FFFFFF，但根因完全不同：未设色是合法输入，
    # 非法 hex 是上游异常，纯黑是「看得见的白才算可用」的显示约束。
    def test_privmsg_with_color_is_emitted(self) -> None:
        got: list[Any] = []
        client = twitch.TwitchDanmaku(on_message=_collect(got))
        client.decode_message(TWITCH_PRIVMSG + "\r\n")
        assert got[0].user_name == "alice"
        assert got[0].message == "hello world"
        assert got[0].color == "#123456"
        assert got[0].type is DanmakuMessageType.CHAT

    def test_missing_color_tag_still_emits(self) -> None:
        # 观众未设色时下发 "color=;"，三标签齐活的旧实现会把整条弹幕丢掉
        got: list[Any] = []
        client = twitch.TwitchDanmaku(on_message=_collect(got))
        client.decode_message("@color=;display-name=bob; :bob!bob@bob.tmi.twitch.tv PRIVMSG #c :plain\r\n")
        assert [m.user_name for m in got] == ["bob"]
        assert got[0].color == "#FFFFFF"

    def test_black_color_falls_back_to_white(self) -> None:
        got: list[Any] = []
        client = twitch.TwitchDanmaku(on_message=_collect(got))
        client.decode_message("@color=#000000;display-name=ink; :ink!ink@ink.tmi.twitch.tv PRIVMSG #c :dark\r\n")
        assert got[0].color == "#FFFFFF"

    def test_invalid_hex_color_falls_back_to_white(self) -> None:
        got: list[Any] = []
        client = twitch.TwitchDanmaku(on_message=_collect(got))
        client.decode_message("@color=#gggggg;display-name=bad; :b!b@b.tmi.twitch.tv PRIVMSG #c :x\r\n")
        assert got[0].color == "#FFFFFF"

    def test_bytes_frames_are_decoded(self) -> None:
        got: list[Any] = []
        client = twitch.TwitchDanmaku(on_message=_collect(got))
        client.decode_message((TWITCH_PRIVMSG + "\r\n").encode("utf-8"))
        assert got[0].user_name == "alice"

    def test_half_line_is_buffered_until_next_frame(self) -> None:
        # MI-21 回归锁：一条 IRC 消息被切成两帧时，弹幕不得丢失。
        got: list[Any] = []
        client = twitch.TwitchDanmaku(on_message=_collect(got))
        line = TWITCH_PRIVMSG + "\r\n"
        client.decode_message(line[:40])
        assert got == []
        client.decode_message(line[40:])
        assert [m.message for m in got] == ["hello world"]

    def test_ping_is_answered_with_pong(self) -> None:
        ws = FakeWs()
        client = twitch.TwitchDanmaku()
        client._ws = cast(Any, ws)
        client.decode_message("PING :tmi.twitch.tv\r\n")
        assert ws.nowait == ["PONG :tmi.twitch.tv"]

    def test_ping_without_ws_is_ignored(self) -> None:
        client = twitch.TwitchDanmaku()
        client.decode_message("PING :tmi.twitch.tv\r\n")

    def test_non_privmsg_lines_are_ignored(self) -> None:
        got: list[Any] = []
        client = twitch.TwitchDanmaku(on_message=_collect(got))
        client.decode_message(":tmi.twitch.tv 001 justinfan :Welcome\r\nNOTICE #c :hi\r\n")
        assert got == []


class TestTwitchLifecycle:
    async def test_start_from_dict_uses_explicit_proxy(self, monkeypatch: pytest.MonkeyPatch) -> None:
        factory = WsFactory()
        monkeypatch.setattr(twitch, "WsClient", factory)
        client = twitch.TwitchDanmaku()
        await client.start({"channel": "#abc", "proxy": "http://127.0.0.1:7890"})
        assert client._channel == "abc"
        kwargs = factory.instances[0].kwargs
        assert kwargs["proxy"] == "http://127.0.0.1:7890"
        assert kwargs["url"] == twitch.SERVER_URL

    async def test_start_from_string_falls_back_to_system_proxy(self, monkeypatch: pytest.MonkeyPatch) -> None:
        factory = WsFactory()
        monkeypatch.setattr(twitch, "WsClient", factory)
        monkeypatch.setattr(twitch, "handle_proxy_addr", lambda p: None if p in (None, "") else str(p))
        monkeypatch.setenv("https_proxy", "http://127.0.0.1:10808")
        client = twitch.TwitchDanmaku()
        await client.start("chan")
        assert factory.instances[0].kwargs["proxy"] == "http://127.0.0.1:10808"

    async def test_start_without_proxy_connects_directly(self, monkeypatch: pytest.MonkeyPatch) -> None:
        factory = WsFactory()
        monkeypatch.setattr(twitch, "WsClient", factory)
        monkeypatch.setattr(twitch, "handle_proxy_addr", lambda p: None)
        for key in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY"):
            monkeypatch.delenv(key, raising=False)
        client = twitch.TwitchDanmaku()
        await client.start("chan")
        assert factory.instances[0].kwargs["proxy"] is None

    async def test_missing_channel_closes(self) -> None:
        reasons: list[str] = []
        client = twitch.TwitchDanmaku(on_close=reasons.append)
        await client.start({"channel": "   "})
        assert reasons == ["缺少 channel"]

    def test_join_room_sends_irc_handshake(self) -> None:
        ws = FakeWs()
        client = twitch.TwitchDanmaku()
        client._ws = cast(Any, ws)
        client._channel = "abc"
        client._on_ws_ready()
        lines = [str(x) for x in ws.nowait]
        assert lines[0].startswith("CAP REQ :")
        assert lines[1] == "PASS SCHMOOPIIE"
        assert lines[2].startswith("NICK justinfan")
        assert lines[-1] == "JOIN #abc"

    def test_join_room_without_ws_is_noop(self) -> None:
        twitch.TwitchDanmaku()._join_room()

    async def test_heartbeat_and_stop(self) -> None:
        ws = FakeWs()
        client = twitch.TwitchDanmaku()
        client._ws = cast(Any, ws)
        await client.heartbeat()
        assert ws.sent == ["PONG :tmi.twitch.tv"]
        await client.stop()
        assert ws.closed == 1
        bare = twitch.TwitchDanmaku()
        await bare.heartbeat()
        await bare.stop()
