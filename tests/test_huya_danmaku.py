# 虎牙弹幕离线测试(不依赖直播间/网络)。
#
# 覆盖：_tars.write_int 的 int64 分支（超 int32 写 INT8、边界值仍写 INT4）回读一致；
# get_huya_app_stream_url 从 profileRoom 响应解析出弹幕所需的
# yyid/lChannelId/lSubChannelId（OD/BD/UHD 录制路径据此补填）。
#
# 用法: .venv/bin/python tests/test_huya_danmaku.py

import asyncio
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from typing import Any, cast

from src import spider  # noqa: E402
from src.platforms._tars import TarsInputStream, TarsOutputStream  # noqa: E402

# 与线上 profileRoom 返回结构对齐(字段名采集自 2026-08 真实响应)
PROFILEROOM_SAMPLE = {
    "status": 200,
    "data": {
        "stream": {
            "baseSteamInfoList": [
                {
                    "lChannelId": 1346609715,
                    "lSubChannelId": 1346609715,
                    "sCdnType": "TX",
                    "sStreamName": "st-v-260814-0138",
                    "sFlvUrl": "https://liveapi-hsy.tx.com/edge",
                    "sFlvAntiCode": "wsSecret=abc&ctype=tars_mp&fs=bhct",
                    "sHlsUrl": "https://liveapi-hsy.tx.com/edge",
                    "sHlsAntiCode": "wsSecret=abc",
                },
                {
                    "lChannelId": 1346609715,
                    "lSubChannelId": 1346609715,
                    "sCdnType": "HW",
                    "sStreamName": "st-v-260814-0138",
                    "sFlvUrl": "https://hwcdn.huya.com/src",
                    "sFlvAntiCode": "wsSecret=abc",
                    "sHlsUrl": "https://hwcdn.huya.com/src",
                    "sHlsAntiCode": "wsSecret=abc",
                },
            ]
        },
        "liveStatus": "ON",
        "profileInfo": {"uid": 1346609715, "yyid": 1486578378, "nick": "虎牙英雄联盟赛事"},
        "liveData": {"yyid": 1486578378, "uid": 1346609715, "introduction": "测试直播间"},
        "chTopId": 1346609715,
        "subChId": 1346609715,
        "realLiveStatus": "ON",
    },
}


def test_int64_branch() -> None:
    # write_int 对超 int32 的值写 INT8; 边界值与 int32 内仍写 INT4; 0 写 ZERO_TAG。
    oos = TarsOutputStream()
    oos.write_int(0, 0)  # ZERO_TAG
    oos.write_int(2147483647, 1)  # int32 上边界 -> INT4
    oos.write_int(-2147483648, 2)  # int32 下边界 -> INT4
    oos.write_int(2147483648, 3)  # 超上界 -> INT8
    oos.write_int(-2147483649, 4)  # 超下界 -> INT8
    oos.write_int(5000000000, 5)  # ayyuid/uid 级大数 -> INT8

    buf = oos.to_bytes()
    ins = TarsInputStream(buf)
    assert ins.read_int(0) == 0
    assert ins.read_int(1) == 2147483647
    assert ins.read_int(2) == -2147483648
    assert ins.read_int(3) == 2147483648
    assert ins.read_int(4) == -2147483649
    assert ins.read_int(5) == 5000000000


def test_join_data_ayyuid_overflow() -> None:
    # 真实超 int32 的 ayyuid 也能用 _make_join_data 编码,不抛 struct.error。
    from src.platforms.huya import HuyaDanmaku

    inst = HuyaDanmaku()
    inst._args = {"ayyuid": 5000000000, "topSid": 1346609715, "subSid": 1346609715}
    data = inst._make_join_data()
    assert isinstance(data, bytes) and len(data) > 0


def test_profileRoom_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    # get_huya_app_stream_url 返回的 dict 含弹幕所需三元组, 与 web 路径字段一致。
    requested: list[str] = []

    async def fake_async_req(
        url: str,
        proxy_addr: Any = None,
        headers: Any = None,
        data: Any = None,
        json_data: Any = None,
        timeout: int = 20,
        redirect_url: bool = False,
        return_cookies: bool = False,
        include_cookies: bool = False,
        abroad: bool = False,
        content_encoding: str = "utf-8",
        verify: bool | None = None,
        http2: bool = True,
    ) -> str:
        # 形参必须与 src/async_http.py::async_req 逐项对齐：残缺签名会让带
        # data=/json_data=/timeout= 的 spider 调用落到替身时抛 TypeError。
        # 数值型 roomid 不触发 html 抓取, 直接返回 profileRoom JSON
        requested.append(url)
        return json.dumps(PROFILEROOM_SAMPLE)

    # 必须经 monkeypatch.setattr 逐属性登记还原：裸赋值不还原会让同进程后续用例拿到
    # 这只固定 JSON 替身（单独跑绿、整包跑红）。
    monkeypatch.setattr(spider, "async_req", fake_async_req)
    result = asyncio.run(
        spider.get_huya_app_stream_url(
            url="https://www.huya.com/660000",
            proxy_addr=None,
            cookies=None,
        )
    )
    # 替身确实被走到（否则上面的断言全在测真实网络，CI 离线时只会以另一种方式红）
    assert any("do=profileRoom" in u for u in requested), f"未请求 profileRoom 接口: {requested}"

    assert result["is_live"] is True
    assert result["yyid"] == 1486578378
    assert result["lChannelId"] == 1346609715
    assert result["lSubChannelId"] == 1346609715
    # 可作为弹幕 join 参数(与 huya.py _args 键一致)
    args = {
        "ayyuid": int(cast(Any, result["yyid"])),
        "topSid": int(cast(Any, result["lChannelId"])),
        "subSid": int(cast(Any, result["lSubChannelId"])),
    }
    assert args["ayyuid"] == 1486578378
    assert args["topSid"] == 1346609715
    assert args["subSid"] == 1346609715
    # 录制字段不受影响（虎牙防盗链统一降为 http，https 实测 403）
    assert str(result["flv_url"]).startswith("http://")
    assert "m3u8_url" in result


if __name__ == "__main__":
    test_int64_branch()
    test_join_data_ayyuid_overflow()
    # 脚本形态无 fixture：MonkeyPatch.context() 退出即逐属性 undo
    # （R6：手工 MonkeyPatch 实例必须配对还原）。
    with pytest.MonkeyPatch.context() as _mp:
        test_profileRoom_fields(_mp)
    print("test_huya_danmaku.py: all passed")
