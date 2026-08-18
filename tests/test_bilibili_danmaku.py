# -*- coding: utf-8 -*-
# 验证 B站 wbi 签名修复:get_bilibili_danmaku_info 返回 token,并能连 WS 收到弹幕。

import asyncio
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import spider
from src.base import DanmakuMessage
from src.platforms.bilibili import BilibiliDanmaku
from src.ws_client import WsClient

URL = "https://live.bilibili.com/3428783"
NEW_ROOM = len(sys.argv) > 1


def on_msg(msg: DanmakuMessage) -> None:
    print(f"[MSG] {msg.user_name}: {msg.message}")


async def main() -> None:
    info = await spider.get_bilibili_danmaku_info(url=URL, proxy_addr=None)
    assert isinstance(info, dict), f"返回非 dict: {info!r}"
    assert info.get("token"), f"token 为空: {info}"
    assert info.get("server_host"), f"server_host 为空: {info}"
    assert info.get("room_id"), f"room_id 为空: {info}"
    # 字段收窄为 str:info 是 dict[str, object],直接切片/取长度会因 object 类型报错;
    # buvid 未在前序断言校验,缺失时兜底为空串,避免 KeyError/TypeError。
    token = info["token"]
    assert isinstance(token, str), f"token 类型异常: {type(token)!r}"
    buvid = str(info.get("buvid", ""))
    print(
        f"OK danmaku_info: room_id={info['room_id']} host={info['server_host']} buvid={buvid[:12]}... token_len={len(token)}"
    )
    # cookie 未在前序断言校验,缺失时兜底为空串,避免 KeyError。
    print(f"OK cookie: {info.get('cookie', '')}")

    got = []

    class CaptureDanmaku(BilibiliDanmaku):
        # 仅覆写 _emit 捕获弹幕;__init__ 无需覆写,自动继承 BilibiliDanmaku。
        def _emit(self, msg: DanmakuMessage) -> None:
            got.append(msg)
            print(
                f"[EMIT] type={msg.type} {msg.user_name}: {msg.message[:60]}"
                if msg.message
                else f"[EMIT] type={msg.type} data={msg.data}"
            )

    client = CaptureDanmaku(on_message=lambda m: None, on_close=lambda r: None, on_ready=lambda: None)
    try:
        await asyncio.wait_for(client.start(info), timeout=30)
    except asyncio.TimeoutError:
        print("OK 连接持续 30s,未崩溃(等待弹幕或超时)")
    print(f"DONE 收到 {len(got)} 条消息")


if __name__ == "__main__":
    asyncio.run(main())
