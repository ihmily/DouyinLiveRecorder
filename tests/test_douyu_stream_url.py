# -*- coding: utf-8 -*-
# 斗鱼录制流地址验证:get_douyu_info_data → get_douyu_stream_url(新签名,对齐 dart)。
#
# 验证录制侧被 get_token_js 卡住的问题是否已由 getEncryption 签名方案恢复。
# 用法:python tests/test_douyu_stream_url.py [房间URL] [清晰度]

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import spider, stream

URL = sys.argv[1] if len(sys.argv) > 1 else "https://www.douyu.com/88080"
QUALITY = sys.argv[2] if len(sys.argv) > 2 else "原画"


def main() -> None:
    info = asyncio.run(spider.get_douyu_info_data(url=URL, proxy_addr=None))
    if not isinstance(info, dict) or not info.get("room_id"):
        print(f"[FAIL] 房间信息获取失败: {info!r}")
        sys.exit(1)
    if not info.get("is_live"):
        print("[FAIL/WARN] 房间未开播")
        sys.exit(1)
    print(f"[OK] anchor={info.get('anchor_name')} room_id={info.get('room_id')}")

    port = asyncio.run(stream.get_douyu_stream_url(json_data=info, video_quality=QUALITY, cookies="", proxy_addr=None))
    flv = port.get("flv_url") or ""
    is_live = port.get("is_live")
    print(f"[OK] is_live={is_live} quality={port.get('quality')}")
    print(f"flv_url_len={len(flv)} prefix={flv[:90]}")
    if is_live and flv:
        print("[PASS] 斗鱼录制流地址恢复")
    else:
        print("[FAIL] 未拿到 flv_url")
        sys.exit(1)


if __name__ == "__main__":
    main()
