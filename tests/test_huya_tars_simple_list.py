# -*- coding: utf-8 -*-
# 虎牙 Tars SIMPLE_LIST 长度字段回归测试。
#
# 背景: _tars.py 曾把 Tars 字节数组 SIMPLE_LIST 的长度写成/读成**固定 4 字节 int32**，
# 而官方 Tars(以及可正常收弹幕的 dart_simple_live tars_dart)把长度编码为
# **自描述整数域**(头字节 BYTE/SHORT/INT/LONG + 对应 1/2/4/8 字节)。
# 这导致: join 注册报文的 iCmdData 长度被服务端读成 0(zero 注册,无推送)，
# 推送报文的长度也读错(弹幕全丢)。
#
# 本测试的断言**独立于生产实现**:
# - 解码: 喂官方编码(服务端实际格式)的弹幕推送 hex,断言能解出 nick/content/uri
#  (修复前必失败: uri=0, nick=None, content 空)。
# - 编码: 断言 join 输出符合官方布局(长度域含头字节),并用独立解析器回读语义。
#
# 用法: .venv/bin/python tests/test_huya_tars_simple_list.py

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.platforms._tars import TarsInputStream  # noqa: E402

# 官方编码的一条弹幕推送(WSCmd iCmdType=7 -> HYPushMessage uri=1400 -> HYMessage)。
# 由 tars_dart 语义手工构造: Bytearray 长度均按"头+变宽值"布局,非固定4字节。
# 内含: nick="测试用户", content="你好呀", fontColor=0xFFFFFF。
OFFICIAL_CHAT_PUSH = bytes.fromhex(
    "0007"
    "1d00002d"  # SIMPLE_LIST tag1 + 元素类型头 + 长度(头00 + 值2d=45)
    "0c"  # HYPushMessage.pushType=0
    "110578"  # HYPushMessage.uri tag1 SHORT = 1400
    "2d000025"  # HYPushMessage.msg tag2 SIMPLE_LIST + 元素头 + 长度(00 25=37)
    "0a"  # HYMessage.userInfo tag0 STRUCT_BEGIN
    "013039"  # HYSender.uid tag0 SHORT = 12345
    "260c"
    "e6b58be8af95e794a8e688b7"  # HYSender.nickName tag2 STRING1 = "测试用户"
    "0b"  # HYSender STRUCT_END
    "3609"
    "e4bda0e5a5bde59180"  # HYMessage.content tag3 STRING1 = "你好呀"
    "6a"  # HYMessage.bulletFormat tag6 STRUCT_BEGIN
    "0200ffffff"  # HYBulletFormat.fontColor tag0 INT = 0xFFFFFF
    "0b"  # HYBulletFormat STRUCT_END
)

# 同上,但 bulletFormat(tag6) 内含 LIST(tag6, size=1) —— 覆盖 LIST 的 size 用
# 自描述整数域(00 01)的回归: 若按固定 4 字节读 size,后面会错位解析出 type 15 抛异常。
# nick="测试用户", content="你好呀", fontColor=0x00FF00(绿色, INT 值 0000ff00)。
OFFICIAL_CHAT_PUSH_WITH_LIST = bytes.fromhex(
    "0007"
    "1d000032"  # SIMPLE_LIST tag1 + 元素头 + 长度(00 32=50)
    "0c"  # pushType=0
    "110578"  # uri=1400
    "2d00002a"  # msg tag2 + 元素头 + 长度(00 2a=42)
    "0a"
    "013039"
    "260c"
    "e6b58be8af95e794a8e688b7"
    "0b"  # userInfo: uid=12345, nick="测试用户"
    "3609"
    "e4bda0e5a5bde59180"  # content="你好呀"
    "6a"  # bulletFormat STRUCT_BEGIN
    "020000ff00"  # fontColor tag0 INT(4字节) = 0x00FF00
    "690001"
    "0001"  # LIST tag6: 头69 + size(00 01=1) + 元素(00 01: tag0 int=1)
    "0b"  # bulletFormat STRUCT_END
)


# 独立官方语义解析器(模仿 tars_dart "字段=头+值/长度自描述域"),用于编码回归判读。
def official_join_parse(bs: bytes) -> dict:
    p = [0]

    def head() -> tuple:
        b = bs[p[0]]
        p[0] += 1
        return b & 0xF, (b >> 4) & 0xF

    def read_value(typ: int) -> int:
        if typ == 12:
            return 0
        w = {0: 1, 1: 2, 2: 4, 3: 8}[typ]
        v = int.from_bytes(bs[p[0] : p[0] + w], "big", signed=True)
        p[0] += w
        return v

    def skip(typ: int) -> None:
        if typ == 0:
            p[0] += 1
        elif typ == 1:
            p[0] += 2
        elif typ in (2, 4):
            p[0] += 4
        elif typ in (3, 5):
            p[0] += 8
        elif typ == 6:
            n = bs[p[0]]
            p[0] += 1 + n
        elif typ == 7:
            n = int.from_bytes(bs[p[0] : p[0] + 4], "big")
            p[0] += 4 + n
        elif typ == 13:
            head()  # 元素类型头
            lt, _ = head()  # 长度域头
            p[0] += read_value(lt)
        elif typ == 10:
            while True:
                t, _ = head()
                if t == 11:
                    break
                skip(t)

    out: dict[str, bytes | int] = {}
    while p[0] < len(bs):
        b = bs[p[0]]
        typ, tag = b & 0xF, (b >> 4) & 0xF
        if typ == 11:
            break
        t, tg = head()
        if tg > 1:
            skip(t)
            continue
        if t == 13:
            head()  # 元素类型头
            lt, _ = head()  # 长度域头
            n = read_value(lt)
            out["icmddata"] = bs[p[0] : p[0] + n]
            p[0] += n
        elif t in (0, 1, 2, 3):
            out["icmdtype"] = read_value(t)
    return out


def test_decode_official_chat_push() -> None:
    # 官方编码的弹幕推送走生产 HuyaDanmaku.decode_message 能解出 nick/content/uri。
    #
    #    HYMessage 是平铺字段(tag0=userInfo, tag3=内容)，此处喂完整外层帧验证生产解码,
    #    曾因 _decode_chat 多包一层 read_struct(0,...) 而全部读空。
    from src.base import DanmakuMessageType
    from src.platforms.huya import HuyaDanmaku

    got: list = []
    inst = HuyaDanmaku(on_message=got.append, on_close=lambda m: None, on_ready=lambda: None)
    inst.decode_message(OFFICIAL_CHAT_PUSH)  # 完整外层 WSCmd 推送帧

    assert len(got) == 1, got
    m = got[0]
    assert m.type == DanmakuMessageType.CHAT
    assert m.user_name == "测试用户"
    assert m.message == "你好呀"
    assert m.color == "#FFFFFF"
    print("[PASS] 官方编码弹幕推送过生产 decode_message: nick/content/color 全部正确")


def test_decode_official_chat_push_with_list() -> None:
    # bulletFormat 内含 LIST(size=自描述整数域) 的弹幕推送也能正确解码。
    #
    #    防回归: _skip 曾把 LIST/MAP 的 size 读成固定 int32, 真实数据错位后解析出
    #    type 15 抛异常被吞。修复为 read_int(0) 后此帧应解出 nick/content/color。
    from src.base import DanmakuMessageType
    from src.platforms.huya import HuyaDanmaku

    got: list = []
    inst = HuyaDanmaku(on_message=got.append, on_close=lambda m: None, on_ready=lambda: None)
    inst.decode_message(OFFICIAL_CHAT_PUSH_WITH_LIST)

    assert len(got) == 1, got
    m = got[0]
    assert m.type == DanmakuMessageType.CHAT
    assert m.user_name == "测试用户"
    assert m.message == "你好呀"
    assert m.color == "#00FF00"
    print("[PASS] 含 LIST 的弹幕推送过生产 decode_message: nick/content/color 全部正确")


def test_encode_join_official_layout() -> None:
    # join 输出符合官方布局(长度域含头字节),且被独立官方语义解析器判读为合法注册。
    from src.platforms.huya import HuyaDanmaku

    inst = HuyaDanmaku()
    inst._args = {"ayyuid": 1486578378, "topSid": 1346609715, "subSid": 1346609715}
    data = inst._make_join_data()

    # 长度域布局标记: 外层 SIMPLE_LIST(1d) + 元素类型头(00) + 长度头 INT(02) + 长度(00000017=23)
    assert bytes.fromhex("1d000200000017") in data, data.hex()

    r = official_join_parse(data)
    assert r.get("icmdtype") == 1, r
    assert len(r.get("icmddata", b"")) == 23, r  # WSRegisterReq 载荷 23 字节
    print("[PASS] join 编码布局与官方语义回读: iCmdType=1, iCmdData=23 字节")


if __name__ == "__main__":
    test_decode_official_chat_push()
    test_decode_official_chat_push_with_list()
    test_encode_join_official_layout()
    print("test_huya_tars_simple_list.py: all passed")
