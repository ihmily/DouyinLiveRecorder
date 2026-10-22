# 生成模块 douyin_pb2 的类型存根。
# 原文件由 protoc 生成（DO NOT EDIT），消息类经 _builder 动态注入，
# 类型检查器（mypy/basedpyright）看不到 PushFrame/Response/ChatMessage 等属性。
# 此存根仅声明被 douyin.py 实际引用的 3 个消息类，继承 Message 即可获得
# SerializeToString/ParseFromString 等标准方法。
from typing import Any

from google.protobuf.message import Message

DESCRIPTOR: object

class PushFrame(Message):
    payloadType: str
    payload: bytes
    logId: int

class Response(Message):
    messagesList: list
    cursor: str
    fetchInterval: int
    now: int
    internalExt: str
    fetchType: int
    heartbeatDuration: int
    needAck: bool
    pushServer: str
    liveCursor: str
    historyNoMore: bool

class ChatMessage(Message):
    content: str
    eventTime: int
    user: Any
