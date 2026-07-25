import json
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.stream import bitrate_to_quality, QUALITY_LEVEL, code_to_zh, is_downgrade


def test_bitrate_to_quality():
    assert bitrate_to_quality(99999) == "OD"
    assert bitrate_to_quality(4000) == "BD"
    assert bitrate_to_quality(3500) == "BD"
    assert bitrate_to_quality(2000) == "UHD"
    assert bitrate_to_quality(1500) == "UHD"
    assert bitrate_to_quality(1000) == "HD"
    assert bitrate_to_quality(800) == "SD"
    assert bitrate_to_quality(600) == "LD"
    assert bitrate_to_quality(300) == "LD"
    assert bitrate_to_quality(0) == "OD"  # 0 或未知回退原画


def test_code_to_zh():
    assert code_to_zh("OD") == "原画"
    assert code_to_zh("BD") == "蓝光"
    assert code_to_zh("UHD") == "超清"
    assert code_to_zh("HD") == "高清"
    assert code_to_zh("SD") == "标清"
    assert code_to_zh("LD") == "流畅"
    assert code_to_zh("UNKNOWN") == "UNKNOWN"


def test_is_downgrade():
    # 等级值越大画质越低；actual 等级值 > 请求等级值 = 降级
    assert is_downgrade("UHD", "HD") is True   # 请求超清 实际高清 = 降级
    assert is_downgrade("UHD", "UHD") is False  # 一致
    assert is_downgrade("HD", "UHD") is False   # 实际更高，不告警
    assert is_downgrade("OD", "HD") is True     # 请求原画 实际高清 = 降级
    assert is_downgrade(None, "HD") is False    # actual 为 None（无法确定）不告警
    assert is_downgrade("UHD", None) is False   # 请求为 None 不告警


import asyncio
from src.stream import get_douyin_stream_url


def _douyin_json_full():
    """抖音全档位测试数据：flv_pull_url / hls_pull_url_map 的 key 是画质名。"""
    return {
        "anchor_name": "测试主播",
        "status": 2,
        "stream_url": {
            "flv_pull_url": {"ORIGIN": "http://flv/origin", "UHD": "http://flv/uhd", "HD": "http://flv/hd"},
            "hls_pull_url_map": {"ORIGIN": "http://hls/origin", "UHD": "http://hls/uhd", "HD": "http://hls/hd"},
        }
    }


def _douyin_json_single():
    """抖音仅原画一档：应降级到 OD 并标记 actual_quality。"""
    return {
        "anchor_name": "测试主播",
        "status": 2,
        "stream_url": {
            "flv_pull_url": {"ORIGIN": "http://flv/origin"},
            "hls_pull_url_map": {"ORIGIN": "http://hls/origin"},
        }
    }


def test_douyin_actual_quality_match():
    """请求 UHD 且平台提供 UHD → actual_quality == UHD。"""
    # mock get_response_status 返回 True 避免真实网络请求
    import src.stream as stream_mod
    orig = stream_mod.get_response_status
    async def _ok(**kw): return True
    stream_mod.get_response_status = _ok
    try:
        result = asyncio.run(get_douyin_stream_url(_douyin_json_full(), "UHD"))
    finally:
        stream_mod.get_response_status = orig
    assert result["actual_quality"] == "UHD"
    assert result["quality"] == "UHD"  # 请求值回显
    assert "OD" in result["available_qualities"]


def test_douyin_actual_quality_downgrade():
    """请求 UHD 但平台仅提供 OD → actual_quality == OD（请求未满足）。

    注：按 QUALITY_LEVEL 契约 OD(0) 画质高于 UHD(1)，is_downgrade 应为 False
    （actual 更高不告警）；此处 actual_quality != 请求值即表明请求未满足。
    """
    import src.stream as stream_mod
    orig = stream_mod.get_response_status
    async def _ok(**kw): return True
    stream_mod.get_response_status = _ok
    try:
        result = asyncio.run(get_douyin_stream_url(_douyin_json_single(), "UHD"))
    finally:
        stream_mod.get_response_status = orig
    assert result["actual_quality"] == "OD"
    assert result["actual_quality"] != "UHD"  # 请求 UHD 未被满足
    assert is_downgrade("UHD", result["actual_quality"]) is False  # OD 画质更高，按契约非降级


from src.stream import get_netease_stream_url


def _netease_json_full():
    return {
        "is_live": True, "anchor_name": "网易主播", "title": "测试",
        "m3u8_url": "http://m3u8/default",
        "stream_list": {"resolution": {
            "blueray": {"cdn": {"cdn1": "http://flv/blueray"}},
            "ultra": {"cdn": {"cdn1": "http://flv/ultra"}},
            "high": {"cdn": {"cdn1": "http://flv/high"}},
        }}
    }


def _netease_json_single():
    return {
        "is_live": True, "anchor_name": "网易主播", "title": "测试",
        "m3u8_url": "http://m3u8/default",
        "stream_list": {"resolution": {"blueray": {"cdn": {"cdn1": "http://flv/blueray"}}}}
    }


def test_netease_actual_quality_match():
    result = asyncio.run(get_netease_stream_url(_netease_json_full(), "UHD"))
    assert result["actual_quality"] == "UHD"  # ultra → UHD
    assert result["quality"] == "UHD"


def test_netease_actual_quality_downgrade():
    """请求 UHD 但仅 blueray(OD) → actual_quality == OD（请求未满足）。

    注：blueray 映射为 OD（原画/蓝光，画质最高），按 QUALITY_LEVEL 契约
    OD(0) 高于 UHD(1)，is_downgrade 为 False（actual 更高不告警）。
    """
    result = asyncio.run(get_netease_stream_url(_netease_json_single(), "UHD"))
    assert result["actual_quality"] == "OD"
    assert result["actual_quality"] != "UHD"  # 请求 UHD 未被满足
    assert is_downgrade("UHD", result["actual_quality"]) is False  # OD 画质更高，按契约非降级


from src.stream import get_huya_stream_url


def _huya_json_full():
    """虎牙全档位：exsphd 含4个 ratio。"""
    return {
        "data": [{"gameLiveInfo": {"nick": "虎牙主播", "introduction": "标题"},
                  "gameStreamInfoList": [{
                      "sFlvUrl": "http://flv", "sStreamName": "stream", "sFlvUrlSuffix": "flv",
                      "sHlsUrl": "http://hls", "sHlsUrlSuffix": "m3u8",
                      "sFlvAntiCode": "wsSecret=xxx&ctype=huya_web&exsphd=264_4000,264_2000,264_1000,264_800"
                  }]}]
    }


def _huya_json_partial():
    """虎牙仅2档：请求 LD 应降级到最低可用档。"""
    return {
        "data": [{"gameLiveInfo": {"nick": "虎牙主播", "introduction": "标题"},
                  "gameStreamInfoList": [{
                      "sFlvUrl": "http://flv", "sStreamName": "stream", "sFlvUrlSuffix": "flv",
                      "sHlsUrl": "http://hls", "sHlsUrlSuffix": "m3u8",
                      "sFlvAntiCode": "wsSecret=xxx&ctype=huya_web&exsphd=264_4000,264_2000"
                  }]}]
    }


def test_huya_actual_quality_match():
    result = asyncio.run(get_huya_stream_url(_huya_json_full(), "HD"))
    assert result["actual_quality"] == "HD"
    assert result["is_live"] is True


def test_huya_actual_quality_downgrade():
    """请求 LD 但仅 UHD/HD 两档 → 降级到 HD（最低可用）。

    注：HD(2) 画质高于 LD(4)，按 QUALITY_LEVEL 契约 actual 更高不告警，
    is_downgrade 为 False；此处 actual_quality != 请求值即表明请求未满足。
    """
    result = asyncio.run(get_huya_stream_url(_huya_json_partial(), "LD"))
    assert result["actual_quality"] == "HD"
    assert result["actual_quality"] != "LD"  # 请求 LD 未被满足
    assert is_downgrade("LD", result["actual_quality"]) is False  # HD 画质更高，按契约非降级


from src.stream import get_douyu_stream_url


def _douyu_json():
    return {"is_live": True, "anchor_name": "斗鱼主播", "room_id": 12345}


def test_douyu_actual_quality_from_rate():
    """平台下发 rate=3（UHD）→ actual_quality == UHD。"""
    import src.stream as stream_mod
    async def _fake_douyu_data(rid, rate, **kw):
        return {"data": {"rtmp_url": "http://flv", "rtmp_live": "live.flv?rate=3", "rate": 3}}
    orig = stream_mod.get_douyu_stream_data
    stream_mod.get_douyu_stream_data = _fake_douyu_data
    try:
        result = asyncio.run(get_douyu_stream_url(_douyu_json(), "UHD", cookies=""))
    finally:
        stream_mod.get_douyu_stream_data = orig
    assert result["actual_quality"] == "UHD"


def test_douyu_actual_quality_downgrade():
    """请求 UHD(rate=3) 但平台下发 rate=0(OD) → 请求未满足。

    注：OD(0) 画质高于 UHD(1)，按 QUALITY_LEVEL 契约 actual 更高不告警，
    is_downgrade 为 False；此处 actual_quality != 请求值即表明请求未满足。
    """
    import src.stream as stream_mod
    async def _fake_douyu_data(rid, rate, **kw):
        return {"data": {"rtmp_url": "http://flv", "rtmp_live": "live.flv", "rate": 0}}
    orig = stream_mod.get_douyu_stream_data
    stream_mod.get_douyu_stream_data = _fake_douyu_data
    try:
        result = asyncio.run(get_douyu_stream_url(_douyu_json(), "UHD", cookies=""))
    finally:
        stream_mod.get_douyu_stream_data = orig
    assert result["actual_quality"] == "OD"
    assert result["actual_quality"] != "UHD"  # 请求 UHD 未被满足
    assert is_downgrade("UHD", result["actual_quality"]) is False  # OD 画质更高，按契约非降级


from src.stream import get_kuaishou_stream_url, get_tiktok_stream_url


def _kuaishou_json_flv_bitrate():
    return {
        "type": 2, "is_live": True, "anchor_name": "快手主播",
        "flv_url_list": [{"url": "http://flv/2000", "bitrate": 2000}, {"url": "http://flv/1000", "bitrate": 1000}]
    }


def test_kuaishou_actual_quality_from_bitrate():
    """请求 UHD，flv_list 含 bitrate 2000(UHD) → actual_quality == UHD。"""
    result = asyncio.run(get_kuaishou_stream_url(_kuaishou_json_flv_bitrate(), "UHD"))
    assert result.get("actual_quality") == "UHD"


def test_kuaishou_actual_quality_downgrade():
    """请求 LD 但最高码率仅 1000(HD) → actual_quality == HD（请求未满足）。

    注：HD(2) 画质高于 LD(4)，按 QUALITY_LEVEL 契约 actual 更高不告警，
    is_downgrade 为 False；此处 actual_quality != 请求值即表明请求未满足。
    """
    result = asyncio.run(get_kuaishou_stream_url({
        "type": 2, "is_live": True, "anchor_name": "快手主播",
        "flv_url_list": [{"url": "http://flv/1000", "bitrate": 1000}]
    }, "LD"))
    assert result.get("actual_quality") == "HD"
    assert result.get("actual_quality") != "LD"  # 请求 LD 未被满足
    assert is_downgrade("LD", result["actual_quality"]) is False  # actual 更高，非降级


def _tiktok_json_full():
    return {
        "LiveRoom": {"liveRoomUserInfo": {"user": {"nickname": "TT", "uniqueId": "1", "status": 2},
                     "liveRoom": {"title": "t", "streamData": {"pull_data": {"stream_data": json.dumps({
                         "data": {"flv": {"main": {"flv": "http://flv/uhd", "sdk_params": json.dumps({"vbitrate": 2000, "resolution": "1920x1080", "VCodec": "h264"})}},
                         "hls": {"main": {"hls": "http://hls/uhd", "sdk_params": json.dumps({"vbitrate": 2000, "resolution": "1920x1080", "VCodec": "h264"})}}
                     }})}}}}}}


def test_tiktok_actual_quality_from_vbitrate():
    """TikTok play_list 项含 vbitrate 2000 → actual_quality == UHD。"""
    import src.stream as stream_mod
    async def _ok(**kw): return True
    orig = stream_mod.get_response_status
    stream_mod.get_response_status = _ok
    try:
        result = asyncio.run(get_tiktok_stream_url(_tiktok_json_full(), "UHD"))
    finally:
        stream_mod.get_response_status = orig
    assert result.get("actual_quality") == "UHD"


from src.stream import get_bilibili_stream_url


def _bili_json():
    return {"anchor_name": "B站主播", "live_status": 1, "room_url": "https://live.bilibili.com/123", "title": "B站直播"}


def test_bili_actual_quality_from_qn():
    """spider 返回 current_qn=250(UHD) → actual_quality == UHD。"""
    import src.stream as stream_mod
    async def _fake_bili_data(url, **kw):
        return {"url": "http://m3u8/uhd", "current_qn": "250", "accept_qn": ["10000", "400", "250"]}
    orig = stream_mod.get_bilibili_stream_data
    stream_mod.get_bilibili_stream_data = _fake_bili_data
    try:
        result = asyncio.run(get_bilibili_stream_url(_bili_json(), "UHD"))
    finally:
        stream_mod.get_bilibili_stream_data = orig
    assert result["actual_quality"] == "UHD"
    assert "UHD" in result["available_qualities"]


def test_bili_actual_quality_downgrade():
    """请求 UHD(250) 但 spider 返回 current_qn=80(LD) → 真正降级。

    注：LD(4) 画质低于 UHD(1)，按 QUALITY_LEVEL 契约 actual 等级值 > 请求等级值，
    is_downgrade 为 True（真正降级）。
    """
    import src.stream as stream_mod
    async def _fake_bili_data(url, **kw):
        return {"url": "http://m3u8/ld", "current_qn": "80", "accept_qn": ["10000", "80"]}
    orig = stream_mod.get_bilibili_stream_data
    stream_mod.get_bilibili_stream_data = _fake_bili_data
    try:
        result = asyncio.run(get_bilibili_stream_url(_bili_json(), "UHD"))
    finally:
        stream_mod.get_bilibili_stream_data = orig
    assert result["actual_quality"] == "LD"
    assert is_downgrade("UHD", result["actual_quality"]) is True  # actual 更低，真正降级


def test_get_status_returns_actual_quality():
    """get_status 返回的 recording 项含 actual_quality 字段。"""
    # main.py 在模块导入时即读取由 sys.argv[0] 推导出的 config/URL_config.ini。
    # 在 `python -m pytest` 下 sys.argv[0] 指向 pytest 的 __main__.py，导致路径解析失败。
    # 将其指向项目根的 main.py，使配置路径解析到 /workspace/config/。
    import pathlib
    sys.argv[0] = str(pathlib.Path(__file__).resolve().parent.parent / "main.py")
    import main
    # 临时设置 recording_time_list
    import datetime
    old = dict(main.recording_time_list)
    main.recording_time_list.clear()
    main.recording.add("序号1 测试主播")
    main.recording_time_list["序号1 测试主播"] = [datetime.datetime.now(), "超清", "高清"]
    try:
        s = main.get_status()
        assert len(s["recording"]) == 1
        rec = s["recording"][0]
        assert rec["quality"] == "超清"
        assert rec["actual_quality"] == "高清"
    finally:
        main.recording.discard("序号1 测试主播")
        main.recording_time_list.clear()
        main.recording_time_list.update(old)
