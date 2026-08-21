# -*- coding: utf-8 -*-
# 虎牙真实房间端到端验证:app 路径(profileRoom)取弹幕参数 → collector → SRT 产出。
#
# 用法:python tests/test_huya_live_collector.py https://www.huya.com/660000  [秒数]
# 走 get_huya_app_stream_url(OD/BD/UHD 路径),顺带验证返回的 yyid/lChannelId/lSubChannelId。

import asyncio
import os
import sys
import time
from typing import Any, cast

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import spider
from src.collector import DanmakuCollector
from src.platforms.huya import HuyaDanmaku

URL = sys.argv[1] if len(sys.argv) > 1 else "https://www.huya.com/660000"
SECONDS = int(sys.argv[2]) if len(sys.argv) > 2 and not sys.argv[2].startswith("-") else 20


def main() -> None:
    info = asyncio.run(spider.get_huya_app_stream_url(url=URL, proxy_addr=None))
    if not isinstance(info, dict) or not info.get("is_live"):
        print(f"[FAIL] 房间未开播或信息获取失败: {info!r}")
        sys.exit(1)
    danmaku_args = {
        "ayyuid": int(cast(Any, info["yyid"])),
        "topSid": int(cast(Any, info["lChannelId"])),
        "subSid": int(cast(Any, info["lSubChannelId"])),
    }
    print(f"[OK] danmaku_args: {danmaku_args}")

    base_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_out_live")
    os.makedirs(base_dir, exist_ok=True)
    for f in os.listdir(base_dir):
        os.remove(os.path.join(base_dir, f))

    base = os.path.join(base_dir, "虎牙弹幕验证_660000")
    collector = DanmakuCollector(
        danmaku_cls=HuyaDanmaku,
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
            print("[PASS] 端到端:虎牙真实弹幕已写入 SRT")
        else:
            print("[WARN] 当前房间该时段无弹幕(连接正常)")
    else:
        print(f"[FAIL] SRT 未生成: {srt_file}")
        sys.exit(1)


if __name__ == "__main__":
    main()
