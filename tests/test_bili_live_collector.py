# -*- coding: utf-8 -*-
# 真实房间端到端验证:BilibiliDanmaku + collector 线程 → SRT 产出。
#
# 用法:python tests/test_bili_live_collector.py https://live.bilibili.com/545068  [秒数]

import asyncio
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import spider
from src.collector import DanmakuCollector
from src.platforms.bilibili import BilibiliDanmaku

URL = sys.argv[1] if len(sys.argv) > 1 else "https://live.bilibili.com/545068"
SECONDS = int(sys.argv[2]) if len(sys.argv) > 2 and not sys.argv[2].startswith("-") else 20


def main() -> None:
    info = asyncio.run(spider.get_bilibili_danmaku_info(url=URL, proxy_addr=None))
    assert isinstance(info, dict), f"弹幕信息获取失败: {info!r}"
    # 契约前置校验：确保后续下标访问不会因缺字段而 KeyError。
    # 仅 token 额外要求非空（断言语义），room_id / server_host 只需存在。
    required_keys = ("room_id", "server_host", "token")
    missing = [k for k in required_keys if k not in info]
    assert not missing and info.get("token"), f"弹幕信息缺失或无效字段: {missing} | info={info!r}"
    # token 为字符串令牌，断言非空后按 str 处理以避免 object 类型告警。
    token = info["token"]
    assert isinstance(token, str), f"token 类型异常: {type(token)!r}"
    print(f"[OK] danmaku_info: room={info['room_id']} host={info['server_host']} token_len={len(token)}")

    base_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_out_live")
    os.makedirs(base_dir, exist_ok=True)
    for f in os.listdir(base_dir):
        os.remove(os.path.join(base_dir, f))

    base = os.path.join(base_dir, "真实弹幕验证_545068")
    collector = DanmakuCollector(
        danmaku_cls=BilibiliDanmaku,
        danmaku_args=info,
        base_filename=base,
        segment_seconds=None,
    )
    collector.start()
    print(f"[OK] collector 已启动,监听 {SECONDS}s...")
    time.sleep(SECONDS)
    count = collector.message_count
    collector.stop()
    print(f"[OK] 收到弹幕消息数: {count}")

    srt_file = base + ".srt"
    if os.path.isfile(srt_file):
        with open(srt_file, encoding="utf-8") as f:
            content = f.read()
        print("=== SRT 内容(前 20 行) ===")
        print("\n".join(content.splitlines()[:20]))
        if count > 0:
            print("[PASS] 端到端:真实弹幕已写入 SRT")
        else:
            print("[WARN] 当前房间该时段无弹幕(连接正常)")
    else:
        print(f"[FAIL] SRT 未生成: {srt_file}")
        sys.exit(1)


if __name__ == "__main__":
    main()
