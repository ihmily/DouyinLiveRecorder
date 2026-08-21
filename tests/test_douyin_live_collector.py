# -*- coding: utf-8 -*-
# 抖音真实房间端到端验证:web 路径取 room_id → collector(DouyinDanmaku) → SRT 产出。
#
# 用法:python tests/test_douyin_live_collector.py [房间URL] [秒数] [cookie(可选)]
# 与 main.py web 路径一致:get_douyin_web_stream_data → id_str 作为 room_id,
# 随机 12 位 user_id,cookie 复用录制 cookie(默认空)。

import os
import random
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import spider
from src.collector import DanmakuCollector
from src.platforms.douyin import DouyinDanmaku
from src.ttwid import get_ttwid

URL = sys.argv[1] if len(sys.argv) > 1 else "https://live.douyin.com/699394970561"
SECONDS = int(sys.argv[2]) if len(sys.argv) > 2 and not sys.argv[2].startswith("-") else 25


def resolve_cookie() -> str:
    # cookie 解析:命令行参数 > config 抖音cookie(与 main.py 一致) > 动态获取 ttwid。
    if len(sys.argv) > 3 and sys.argv[3]:
        return sys.argv[3]
    from configparser import ConfigParser

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    cfg = ConfigParser()
    cfg.read(os.path.join(root, "config", "config.ini"), encoding="utf-8-sig")
    ck = cfg.get("Cookie", "抖音cookie", raw=True, fallback="").strip()
    if ck:
        return ck
    import asyncio

    try:
        return asyncio.run(get_ttwid())
    except Exception as e:  # 获取失败时置空，与 douyin.py 兜底行为一致
        print(f"[WARN] 动态获取 ttwid 失败: {type(e).__name__}: {e}")
        return ""


def main() -> None:
    import asyncio

    cookie = resolve_cookie()
    room_data = asyncio.run(spider.get_douyin_web_stream_data(url=URL, proxy_addr=None, cookies=cookie))
    if not isinstance(room_data, dict) or not room_data.get("id_str"):
        print(f"[FAIL] 房间信息获取失败: {str(room_data)[:200]}")
        sys.exit(1)
    status = room_data.get("status")
    print(f"[OK] anchor={room_data.get('anchor_name')} status={status} id_str={room_data.get('id_str')}")
    if status != 2:
        print(f"[FAIL/WARN] 房间未开播(status={status}),无法验证弹幕")
        sys.exit(1)

    danmaku_args = {
        "room_id": str(room_data.get("id_str")),
        "user_id": str(random.randint(10**11, 10**12 - 1)),
        "cookie": cookie,
    }
    print(f"[OK] danmaku_args: room_id={danmaku_args['room_id']} user_id={danmaku_args['user_id']}")

    base_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_out_live")
    os.makedirs(base_dir, exist_ok=True)
    for f in os.listdir(base_dir):
        if f.startswith("Douyin弹幕验证"):
            os.remove(os.path.join(base_dir, f))

    base = os.path.join(base_dir, "Douyin弹幕验证_699394970561")
    collector = DanmakuCollector(
        danmaku_cls=DouyinDanmaku,
        danmaku_args=danmaku_args,
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
        with open(srt_file, encoding="utf-8") as fh:
            content = fh.read()
        print("=== SRT 内容(前 20 行) ===")
        print("\n".join(content.splitlines()[:20]))
        if count > 0:
            print("[PASS] 端到端:抖音真实弹幕已写入 SRT")
        else:
            print("[WARN] 当前房间该时段无弹幕(连接可能正常)")
    else:
        print(f"[FAIL] SRT 未生成: {srt_file}")
        sys.exit(1)


if __name__ == "__main__":
    main()
