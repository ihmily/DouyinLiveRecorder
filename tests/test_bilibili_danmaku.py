# -*- coding: utf-8 -*-
# B站 wbi 签名修复的串联锁：get_bilibili_danmaku_info 返回 token，并能连 WS 收到弹幕。
#
# 本文件原是「只有 main()、没有任何 test_ 函数」的
# 真机脚本——pytest 收集到 0 用例，token / server_host / WS 存活三条断言永不自动执行、可静默腐烂，
# 而文件名仍在向读者 advertise「B站弹幕已验证」。照 tests/test_bili_e2e.py（ ②）的形态改造：
# 主体拆成**离线收集型**用例，只打桩网络层（spider.async_req 的四端点 + bilibili.WsClient），
# 「info 解析链 → start 建连 → 进房包 → AUTH_REPLY → 弹幕分发」整条串联走真实代码；真机通道留在
# `if __name__ == "__main__"` 之后（`python tests/test_bilibili_danmaku.py [房间URL] [存活秒数]`），
# 按 AGENTS「live collector 双模模板」补齐守卫（执行体全在守卫之下、模块级零副作用、argv 两步式）。
# 分工（不另建第二份字段级断言）：test_bilibili_danmaku_info.py 锁 spi 端点 URL、buvid 来源优先级、
# 看门狗三态等字段/分支；test_platform_danmaku_offline.py 锁三平台帧编解码；本文件锁上面那条串联，
# 并钉住：_reject_auth 的关停协程必须经 spawn_danmaku_task 投递，异常有人回收、不留孤儿 future。
# 判据（改完复跑，两条都必须成立）：
#   PYTHONUTF8=1 python -m pytest tests/test_bilibili_danmaku.py --collect-only -q   # collected >= 1 且秒级
#   PYTHONUTF8=1 python -m pytest tests/test_bilibili_danmaku.py -q                  # 全绿 0 警告且**不联网**

import asyncio
import json
import os
import sys
from typing import Any, cast

import pytest
from loguru import logger

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import spider
from src.base import DanmakuMessage
from src.platforms import bilibili
from src.platforms.bilibili import BilibiliDanmaku

# 这里刻意不导入 main：本模块只需 src.spider / src.platforms.bilibili（离线用例把网络层整段桩住），
# 而 import main 会把「进程退出时清理 ffmpeg」的 atexit 钩子带进 pytest 会话，收尾时对已关闭的
# stderr 刷一长串 loguru "Logging error"。[历史注 2026-10-19] 原文件在此还 `import main`。

URL = "https://live.bilibili.com/3428783"
# NEW_ROOM 只记录「是否带命令行参数」，本文件从未读取；房间覆盖由真机段的 LIVE_URL 承担
# （见 _LIVE_URL_RAW），内置房间 URL 仍是默认值。
# [历史注 2026-10-19] 原注释称此处「恒 False」，与 `len(sys.argv) > 1` 的事实不符，已改正。
NEW_ROOM = len(sys.argv) > 1

# ── 离线用例的固定响应（wbi 签名链需要 nav 的两枚 key，取 32 位 hex 形态即可，不参与断言）──
_STUB_IMG_KEY = "abcdefghijklmnopqrstuvwxyz012345"
_STUB_SUB_KEY = "0123456789abcdefghijklmnopqrstuv"
_STUB_SHORT_ROOM = "462"
_STUB_REAL_ROOM = 763679
_STUB_TOKEN = "CHAIN-TOKEN-123"
_STUB_BUVID = "chain-buvid3"
_STUB_HOST = "broadcastlv.chat.bilibili.com"


def _stub_danmaku_req(hits: list[str]) -> Any:
    # 按 URL 子串把四个端点路由到固定响应；hits 同时是「替身真被走到」的反向见证
    # （装错命名空间就会去起真网络，hits 保持为空而用例仍绿——那是本仓明令禁止的假绿形态）。
    async def _req(url: str, *args: Any, **kwargs: Any) -> str:
        if "room_init" in url:
            hits.append("room_init")
            return json.dumps({"code": 0, "data": {"room_id": _STUB_REAL_ROOM, "uid": 296732}})
        if "/nav" in url:
            hits.append("nav")
            return json.dumps(
                {
                    "code": 0,
                    "data": {
                        "wbi_img": {
                            "img_url": f"https://i0.hdslb.com/bfs/wbi/{_STUB_IMG_KEY}.png",
                            "sub_url": f"https://i0.hdslb.com/bfs/wbi/{_STUB_SUB_KEY}.png",
                        }
                    },
                }
            )
        if "finger/sp" in url:
            hits.append("spi")
            return json.dumps({"code": 0, "data": {"b_3": _STUB_BUVID, "buvid": _STUB_BUVID}})
        if "getDanmuInfo" in url:
            hits.append("getDanmuInfo")
            return json.dumps(
                {
                    "code": 0,
                    "data": {
                        "token": _STUB_TOKEN,
                        "host_list": [{"host": _STUB_HOST, "port": 2243, "ws_port": 2244, "wss_port": 443}],
                    },
                }
            )
        hits.append(f"unexpected:{url}")
        return ""

    return _req


class _ChainFakeWs:
    # WsClient 的最小替身：连接参数照单收下、发出的帧留档，绝不触网。
    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs
        self.sent: list[bytes | str] = []
        self.closed = 0
        self.fail_reasons: list[str] = []

    async def connect(self) -> None:
        # 真机上「连上」之后的唯一下一步是 on_ready（→ _on_ws_ready → 发进房包），这里当场回调它，
        # 让 start() 的 host 轮换按「首个候选即建成会话」break——与真机顺序一致。
        on_ready = self.kwargs.get("on_ready")
        if callable(on_ready):
            cast(Any, on_ready)()

    async def send(self, data: "bytes | str") -> None:
        self.sent.append(data)

    async def close(self) -> None:
        self.closed += 1

    async def fail(self, reason: str = "") -> None:
        # 与 src/ws_client.py:WsClient.fail 同形（该要求被拒侧走这条带上报的出口）。
        self.closed += 1
        self.fail_reasons.append(reason)


class _WsFactory:
    # 替身工厂：bilibili.WsClient 每次被构造都留一个实例供断言（轮换几个 host 就有几个实例）。
    def __init__(self) -> None:
        self.instances: list[_ChainFakeWs] = []

    def __call__(self, **kwargs: Any) -> _ChainFakeWs:
        ws = _ChainFakeWs(**kwargs)
        self.instances.append(ws)
        return ws


def _auth_reply_frame(code: int) -> bytes:
    # 用生产编码器造一条 AUTH_REPLY（operation=8）真帧：喂给 decode_message 才走到认证分支。
    return BilibiliDanmaku._encode(json.dumps({"code": code}), action=8)


def _danmu_frame(text: str, user: str) -> bytes:
    # 一条 DANMU_MSG（operation=5、protover=0 明文）真帧，结构对齐线上 info 数组。
    # info[0][3] = 16711680 是十进制颜色（#FF0000），下游必须换算成十六进制串。
    body = json.dumps(
        {
            "cmd": "DANMU_MSG",
            "info": [[0, 1, 25, 16711680, 1, "A", 0, 0], text, [0, user, 12345678, 0, 0, 0, 0], [0, 0]],
        },
        ensure_ascii=False,
    )
    return BilibiliDanmaku._encode(body, action=5)


async def test_danmaku_info_to_ws_chain_delivers_message(monkeypatch: pytest.MonkeyPatch) -> None:
    # 本文件的立身之本：一条用例跑完「拿参数 → 建连 → 进房 → 认证 → 出弹幕」，
    # 任何一环断掉（info 字段改名、进房包不再带 token、AUTH_REPLY 分支被删、分发链换了回调）都会红。
    hits: list[str] = []
    monkeypatch.setattr(spider, "async_req", _stub_danmaku_req(hits))

    info = await spider.get_bilibili_danmaku_info(url=f"https://live.bilibili.com/{_STUB_SHORT_ROOM}")
    assert isinstance(info, dict), f"弹幕参数获取失败: {info!r}"
    assert info.get("token") == _STUB_TOKEN, f"token 未来自 getDanmuInfo: {info!r}"
    assert info.get("server_host") == _STUB_HOST
    assert info.get("room_id") == _STUB_REAL_ROOM, "短号未经 room_init 还原成真实房间号"
    assert info.get("buvid") == _STUB_BUVID
    assert hits, "async_req 替身未被调用：网络层没被桩住，本用例的观察点失效（假绿）"

    # 看门狗/进房两条后台协程经 spawn_danmaku_task 投递；这里包一层「委托真实实现 + 记账」，
    # 既保留真实异常落盘语义，又能在用例末尾断言「没有留下 pending 任务」。
    spawned: list["asyncio.Task[None]"] = []
    real_spawn = bilibili.spawn_danmaku_task

    def _record_spawn(coro: Any) -> "asyncio.Task[None]":
        task = cast(Any, real_spawn)(coro)
        spawned.append(task)
        return cast("asyncio.Task[None]", task)

    monkeypatch.setattr(bilibili, "spawn_danmaku_task", _record_spawn)

    factory = _WsFactory()
    monkeypatch.setattr(bilibili, "WsClient", factory)
    # 真实 8s 看门狗单测不可等：压到 0.01s，让它在用例内自己跑完收尾（不压的话它会一直 pending）。
    monkeypatch.setattr(BilibiliDanmaku, "_AUTH_TIMEOUT", 0.01)

    got: list[DanmakuMessage] = []
    closed: list[str] = []
    client = BilibiliDanmaku(on_message=got.append, on_close=closed.append, on_ready=lambda: None)
    await client.start(dict(info))

    assert [ws.kwargs["url"] for ws in factory.instances] == [f"wss://{_STUB_HOST}/sub"]
    ws = factory.instances[0]
    await asyncio.sleep(0)  # 让 on_ready 里投递的 _join_room 跑起来
    assert ws.sent, "进房包未发出：WS 连通后的第一步就断了"
    join_body = json.loads(cast(bytes, ws.sent[0])[16:].decode("utf-8"))
    # 进房包必须带着 info 里那枚 token —— 「拿到的参数真的交给了 WS」正是本用例相对字段级锁的增量。
    assert join_body["key"] == _STUB_TOKEN
    assert join_body["roomid"] == _STUB_REAL_ROOM
    assert join_body["buvid"] == _STUB_BUVID
    # 观众 uid 匿名必须是 0（传主播 uid 会被弹幕服务器在 AUTH 后硬断连，见 test_bilibili_danmaku_info.py）
    assert join_body["uid"] == 0

    client.decode_message(_auth_reply_frame(0))
    assert client._auth_ok is True
    await asyncio.sleep(0.05)  # 看门狗醒来时应已看到 _auth_ok=True，据此静默返回、不断开

    client.decode_message(_danmu_frame("链路弹幕", "链路用户"))
    assert len(got) == 1, f"弹幕未分发: {got!r}"
    assert got[0].message == "链路弹幕"
    assert got[0].user_name == "链路用户"
    assert got[0].color == "#FF0000", "info[0][3] 的颜色十进制未换算成十六进制串"

    assert client._stopped is False
    assert closed == [], f"健康链路不得上报关闭: {closed}"
    assert spawned and all(task.done() for task in spawned), "后台协程留下 pending 任务（用例结束时无人回收）"


async def test_reject_auth_dispatches_through_spawned_task(monkeypatch: pytest.MonkeyPatch) -> None:
    # ①：_reject_auth 的关停协程必须经 spawn_danmaku_task 投递（带异常落盘的托管调度），
    # 不得退回裸 asyncio.ensure_future——那种写法下 fail() 的异常只在任务被 GC 时以
    # "Task exception was never retrieved" 打到 stderr，现场零日志（审查已在 _on_ws_ready
    # 一侧把同一形态立为禁止）。投递替身换成记账器后，退回裸 ensure_future 一条都记不到。
    recorded: list[Any] = []

    def _record(coro: Any) -> None:
        # 替身不真起任务，但必须 close() 传入的协程：未 await 的协程在 GC 时抛 RuntimeWarning，
        # 会打爆本仓「pytest 0 警告」门禁（同 tests/test_platform_danmaku_offline.py::_noop_spawn）。
        recorded.append(coro)
        coro.close()

    monkeypatch.setattr(bilibili, "spawn_danmaku_task", _record)
    invalidated: list[int] = []
    monkeypatch.setattr(spider, "invalidate_bili_buvid_cache", lambda: invalidated.append(1))

    ws = _ChainFakeWs()
    client = BilibiliDanmaku(on_message=lambda _m: None, on_close=lambda _r: None)
    client._ws = cast(Any, ws)

    client._reject_auth()

    assert client._stopped is True
    assert len(recorded) == 1, f"关停协程未经 spawn_danmaku_task 投递（退回裸 ensure_future？）: {recorded!r}"
    assert recorded[0].cr_code.co_name == "fail", "投递的不是 WsClient.fail()，MID-2245 的上报链被换掉了"
    # 缓存失效与投递相互独立：投出去的是协程，失效钩子必须在同步路径上就已完成
    assert invalidated == [1]


async def test_reject_auth_close_failure_is_reclaimed_and_logged(monkeypatch: pytest.MonkeyPatch) -> None:
    # ②：关闭协程自己抛错时必须「被回收并留痕」，而不是成为无人认领的孤儿 future。
    # 这里刻意**不**打桩 spawn_danmaku_task，走 src/base.py 的真实托管：其完成回调按既有的
    # 「[弹幕]后台协程异常: {type_name}: {exc}」模板落一条 warning（既有键，四语目录已登记，不新造
    # msgid）。退回裸 ensure_future 时这条 warning 不会出现，本用例即红。
    class _BoomWs:
        async def fail(self, reason: str = "") -> None:
            raise RuntimeError("close-boom")

    monkeypatch.setattr(spider, "invalidate_bili_buvid_cache", lambda: None)
    client = BilibiliDanmaku(on_message=lambda _m: None, on_close=lambda _r: None)
    client._ws = cast(Any, _BoomWs())

    lines: list[str] = []
    handler_id = logger.add(lambda message: lines.append(str(message)), level="WARNING")
    try:
        client._reject_auth()
        for _ in range(3):  # 让出几轮，把投递出去的关停协程与它的完成回调都跑到
            await asyncio.sleep(0)
    finally:
        logger.remove(handler_id)

    assert lines, "未捕获到任何日志，本用例的观察点失效（假绿）"
    assert any(
        "[弹幕]后台协程异常" in text and "RuntimeError" in text and "close-boom" in text for text in lines
    ), f"关停协程的异常未被托管回收（应经 spawn_danmaku_task 落一条 warning）: {lines!r}"


# ── 真机通道：仅在 `python tests/test_bilibili_danmaku.py [房间URL] [存活秒数]` 下执行 ──
# 双模式守卫：上面三条离线用例之外，本段一行都不执行（导入期零副作用、无裸 int(sys.argv[...]) 转换），
# 因此 `pytest tests/test_bilibili_danmaku.py` 既不会连外网也不会因没有活房间而变红。
_LIVE_URL_RAW = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("-") else ""
# 房间 URL 只认 http(s) 形态：pytest 一次点多个文件时 argv[1] 是下一个测试文件的路径，不能当 URL 用。
LIVE_URL = _LIVE_URL_RAW if _LIVE_URL_RAW.startswith("http") else URL
# 存活秒数走「先取原文、再判是否数值」两步式（AGENTS 双模模板③：单行式会放行下一个测试文件的
# 路径参数，int(路径) 当场 ValueError 让本模块收集 ERROR，2026-09-30 实测）
_SECONDS_RAW = sys.argv[2] if len(sys.argv) > 2 and not sys.argv[2].startswith("-") else ""
LIVE_SECONDS = float(int(_SECONDS_RAW)) if _SECONDS_RAW.isdigit() else 30.0


def on_msg(msg: DanmakuMessage) -> None:
    print(f"[MSG] {msg.user_name}: {msg.message}")


async def _live_probe(url: str, seconds: float) -> None:
    # 原 main() 主体逐条保留真机断言：token / server_host / room_id 必须拿得到，WS 撑满存活窗口不崩。
    info = await spider.get_bilibili_danmaku_info(url=url, proxy_addr=None)
    assert isinstance(info, dict), f"返回非 dict: {info!r}"
    assert info.get("token"), f"token 为空: {info}"
    assert info.get("server_host"), f"server_host 为空: {info}"
    assert info.get("room_id"), f"room_id 为空: {info}"
    # 字段收窄为 str：info 是 dict[str, object]，直接切片/取长度会因 object 类型报错；
    # buvid 未在前序断言校验，缺失时兜底为空串，避免 KeyError/TypeError。
    token = info["token"]
    assert isinstance(token, str), f"token 类型异常: {type(token)!r}"
    buvid = str(info.get("buvid", ""))
    print(
        f"OK danmaku_info: room_id={info['room_id']} host={info['server_host']} buvid={buvid[:12]}... token_len={len(token)}"
    )
    # cookie 未在前序断言校验，缺失时兜底为空串，避免 KeyError。
    print(f"OK cookie: {info.get('cookie', '')}")

    got: list[DanmakuMessage] = []

    class CaptureDanmaku(BilibiliDanmaku):
        # 仅覆写 _emit 捕获弹幕；__init__ 无需覆写，自动继承 BilibiliDanmaku。
        def _emit(self, msg: DanmakuMessage) -> None:
            got.append(msg)
            print(
                f"[EMIT] type={msg.type} {msg.user_name}: {msg.message[:60]}"
                if msg.message
                else f"[EMIT] type={msg.type} data={msg.data}"
            )

    client = CaptureDanmaku(on_message=lambda m: None, on_close=lambda r: None, on_ready=lambda: None)
    # 存活探针：验证 wbi 签名修复后能拿到 token、成功建连 WS 并持续收弹幕不崩溃；超时即视为
    # 连接稳定（等待弹幕或正常保活），不判失败。时长可经 argv[2] 覆盖（默认 30s，见 LIVE_SECONDS）。
    try:
        await asyncio.wait_for(client.start(info), timeout=seconds)
    except asyncio.TimeoutError:
        print(f"OK 连接持续 {seconds:.0f}s,未崩溃(等待弹幕或超时)")
    print(f"DONE 收到 {len(got)} 条消息")


def _live_main() -> None:
    # 人工通道入口（不进 pytest：模块里没有任何 test_* 调用它）。
    # [历史注 2026-10-19] 原名 main，与当时的 `import main`（项目入口模块）同名相冲，该改造时改名。
    asyncio.run(_live_probe(LIVE_URL, LIVE_SECONDS))


if __name__ == "__main__":
    _live_main()
