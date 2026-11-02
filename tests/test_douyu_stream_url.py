# -*- coding: utf-8 -*-
# 斗鱼录制流地址验证:get_douyu_info_data → get_douyu_stream_url(getEncryption 签名,对齐 dart)。
# 用法:python tests/test_douyu_stream_url.py [房间URL] [清晰度]

import asyncio
import os
import sys

# 本文件是手动验证脚本而非 pytest 用例（无 test_ 函数，不会被 pytest 收集）：
# 必须真实访问斗鱼接口才能验证签名链路，无法用 mock 替代。
# 故需把项目根目录插入 sys.path，使 `python tests/xxx.py` 直接运行时能 import src 包。
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import spider, stream

# 参数带默认值：不传参时用固定房间便于快速回归；传参可针对具体房间排查（风控状态与清晰度档位可能不同）。
URL = sys.argv[1] if len(sys.argv) > 1 else "https://www.douyu.com/88080"
QUALITY = sys.argv[2] if len(sys.argv) > 2 else "原画"


def main() -> None:
    # 两段式验证：先取房间信息（签名需 room_id），再换真实 FLV 地址；拆开才能区分
    # 「接口/风控失败」与「信息成功却拿不到 flv_url＝签名方案失效」。
    info = asyncio.run(spider.get_douyu_info_data(url=URL, proxy_addr=None))
    # 边界：接口异常时可能返回 None 或非 dict，此时后续 info.get 会 AttributeError，故先判型。
    if not isinstance(info, dict) or not info.get("room_id"):
        print(f"[FAIL] 房间信息获取失败: {info!r}")
        sys.exit(1)
    # 边界：未开播时签名正确也拿不到流地址，与签名失效同形，故在此步退出避免误判。
    if not info.get("is_live"):
        print("[FAIL/WARN] 房间未开播")
        sys.exit(1)
    print(f"[OK] anchor={info.get('anchor_name')} room_id={info.get('room_id')}")

    # cookies 传空串：验证无登录态是否仍能出流；只有带 cookie 才成功说明鉴权仍依赖登录态。
    port = asyncio.run(stream.get_douyu_stream_url(json_data=info, video_quality=QUALITY, cookies="", proxy_addr=None))
    # flv_url 可能是 None（解析失败）而非空串，统一归一为 str 后再做长度/前缀输出。
    flv_value = port.get("flv_url")
    flv = flv_value if isinstance(flv_value, str) else ""
    is_live = port.get("is_live")
    print(f"[OK] is_live={is_live} quality={port.get('quality')}")
    print(f"flv_url_len={len(flv)} prefix={flv[:90]}")
    # 判定必须同时要求 is_live 与 flv 非空：只有 is_live 时录制端会以空输入启动 ffmpeg 而失败。
    if is_live and flv:
        print("[PASS] 斗鱼录制流地址恢复")
    else:
        print("[FAIL] 未拿到 flv_url")
        sys.exit(1)


if __name__ == "__main__":
    main()
