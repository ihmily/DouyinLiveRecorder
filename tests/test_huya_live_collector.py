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

# 虎牙弹幕走私有二进制/JSON 混合协议,需先经 get_huya_app_stream_url 取流地址,
# 再解析出 yyid/频道/子频道三元组才能进房;纯 web 页无法直连弹幕,故本脚本走 app 路径。
URL = sys.argv[1] if len(sys.argv) > 1 else "https://www.huya.com/660000"
SECONDS = int(sys.argv[2]) if len(sys.argv) > 2 and not sys.argv[2].startswith("-") else 20


def main() -> None:
    info = asyncio.run(spider.get_huya_app_stream_url(url=URL, proxy_addr=None))
    # is_live 为 False(未开播)或 info 非 dict(接口风控/解析失败)都直接退出,
    # 二者均不同于「已进房但无弹幕」,失败语义必须区分,避免误判为连接故障。
    if not isinstance(info, dict) or not info.get("is_live"):
        print(f"[FAIL] 房间未开播或信息获取失败: {info!r}")
        sys.exit(1)
    # 虎牙 app 弹幕三参数：ayyuid=用户yyid、topSid=频道id(lChannelId)、subSid=子频道id
    # (lSubChannelId)，均由 get_huya_app_stream_url 解析返回；cast→int 把宽松类型收窄为协议所需 int。
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
    # SECONDS=20 覆盖虎牙 app 弹幕握手(注册 + 进房 + 心跳保活);其握手含设备指纹
    # 校验,比纯 WS 略重,时长不足会卡在进房阶段导致收不到弹幕。stop() 在计数后触发落盘。
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
        # SRT 已生成而 count==0 视为连接正常但冷场;未生成才判 [FAIL] 退出,
        # 不可把「无弹幕」与「连接失败」混为一谈。
        if count > 0:
            print("[PASS] 端到端:虎牙真实弹幕已写入 SRT")
        else:
            print("[WARN] 当前房间该时段无弹幕(连接正常)")
    else:
        print(f"[FAIL] SRT 未生成: {srt_file}")
        sys.exit(1)


if __name__ == "__main__":
    main()
