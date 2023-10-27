import _thread
import binascii
import gzip
import json
import logging
import re
import time
import requests
import os
import websocket
import urllib
from protobuf_inspector.types import StandardParser
from google.protobuf import json_format
from dy_pb2 import PushFrame
from dy_pb2 import Response
from dy_pb2 import MatchAgainstScoreMessage
from dy_pb2 import LikeMessage
from dy_pb2 import MemberMessage
from dy_pb2 import GiftMessage
from dy_pb2 import ChatMessage
from dy_pb2 import SocialMessage
from dy_pb2 import RoomUserSeqMessage
from dy_pb2 import UpdateFanTicketMessage
from dy_pb2 import CommonTextMessage
from dy_pb2 import ProductChangeMessage


class DouyinLiveAPI:
    liveRoomId = None
    ttwid = None
    liveRoomId = ''
    logger = None

    def setup_logger(self):
        logger = logging.getLogger('直播间: %s' % str(self.liveRoomId))
        logger.setLevel(logging.INFO)
        # 创建一个handler，用于写入日志文件
        if not os.path.exists("./log"):
            os.makedirs("./log")
        fh = logging.FileHandler(f"./log/{self.liveRoomId}.log", encoding="utf-8-sig", mode="a")
        fh.setLevel(logging.INFO)
        # 定义handler的输出格式
        formatter = logging.Formatter('%(asctime)s - %(message)s')
        fh.setFormatter(formatter)
        # 给logger添加handler
        logger.addHandler(fh)
        self.logger = logger

    def record_live_room(self, url):
        h = {
            'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9',
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/107.0.0.0 Safari/537.36',
            'cookie': '__ac_nonce=0638733a400869171be51',
        }
        res = requests.get(url=url, headers=h)

        data = res.cookies.get_dict()
        self.ttwid = data['ttwid']
        res = res.text
        res = re.search(r'roomId\\":\\"(\d+)\\"', res)
        res = res.group(1)
        self.liveRoomId = res
        self.setup_logger()
        self.wssServerStart()

    def onMessage(self, ws: websocket.WebSocketApp, message: bytes):
        wssPackage = PushFrame()
        wssPackage.ParseFromString(message)
        logId = wssPackage.logId
        decompressed = gzip.decompress(wssPackage.payload)
        payloadPackage = Response()
        payloadPackage.ParseFromString(decompressed)
        # 发送ack包
        if payloadPackage.needAck:
            self.sendAck(ws, logId, payloadPackage.internalExt)
        for msg in payloadPackage.messagesList:
            if msg.method == 'WebcastMatchAgainstScoreMessage':
                self.unPackMatchAgainstScoreMessage(msg.payload)
                continue

            if msg.method == 'WebcastLikeMessage':
                self.unPackWebcastLikeMessage(msg.payload)
                continue

            if msg.method == 'WebcastMemberMessage':
                self.unPackWebcastMemberMessage(msg.payload)
                continue
            if msg.method == 'WebcastGiftMessage':
                self.unPackWebcastGiftMessage(msg.payload)
                continue
            if msg.method == 'WebcastChatMessage':
                self.unPackWebcastChatMessage(msg.payload)
                continue

            if msg.method == 'WebcastSocialMessage':
                self.unPackWebcastSocialMessage(msg.payload)
                continue

            if msg.method == 'WebcastRoomUserSeqMessage':
                self.unPackWebcastRoomUserSeqMessage(msg.payload)
                continue

            if msg.method == 'WebcastUpdateFanTicketMessage':
                self.unPackWebcastUpdateFanTicketMessage(msg.payload)
                continue

            if msg.method == 'WebcastCommonTextMessage':
                self.unPackWebcastCommonTextMessage(msg.payload)
                continue
            if msg.method == 'WebcastProductChangeMessage':
                self.WebcastProductChangeMessage(msg.payload)
                continue

            self.logger.info('[onMessage] [⌛️方法' + msg.method + '等待解析～] [房间Id：' + self.liveRoomId + ']')


    def unPackWebcastCommonTextMessage(self, data):
        commonTextMessage = CommonTextMessage()
        commonTextMessage.ParseFromString(data)
        data = json_format.MessageToDict(commonTextMessage, preserving_proto_field_name=True)
        log = json.dumps(data, ensure_ascii=False)
        self.logger.info('[unPackWebcastCommonTextMessage] [] [房间Id：' + self.liveRoomId + '] ｜ ' + log)
        return data

    def WebcastProductChangeMessage(self, data):
        commonTextMessage = ProductChangeMessage()
        commonTextMessage.ParseFromString(data)
        data = json_format.MessageToDict(commonTextMessage, preserving_proto_field_name=True)
        log = json.dumps(data, ensure_ascii=False)
        self.logger.info('[WebcastProductChangeMessage] [] [房间Id：' + self.liveRoomId + '] ｜ ' + log)


    def unPackWebcastUpdateFanTicketMessage(self, data):
        updateFanTicketMessage = UpdateFanTicketMessage()
        updateFanTicketMessage.ParseFromString(data)
        data = json_format.MessageToDict(updateFanTicketMessage, preserving_proto_field_name=True)
        log = json.dumps(data, ensure_ascii=False)
        self.logger.info('[unPackWebcastUpdateFanTicketMessage] [] [房间Id：' + self.liveRoomId + '] ｜ ' + log)
        return data


    def unPackWebcastRoomUserSeqMessage(self, data):
        roomUserSeqMessage = RoomUserSeqMessage()
        roomUserSeqMessage.ParseFromString(data)
        data = json_format.MessageToDict(roomUserSeqMessage, preserving_proto_field_name=True)
        log = json.dumps(data, ensure_ascii=False)
        self.logger.info('[unPackWebcastRoomUserSeqMessage] [] [房间Id：' + self.liveRoomId + '] ｜ ' + log)
        return data


    def unPackWebcastSocialMessage(self, data):
        socialMessage = SocialMessage()
        socialMessage.ParseFromString(data)
        data = json_format.MessageToDict(socialMessage, preserving_proto_field_name=True)
        log = json.dumps(data, ensure_ascii=False)
        self.logger.info('[unPackWebcastSocialMessage] [➕直播间关注消息] [房间Id：' + self.liveRoomId + '] ｜ ' + log)
        return data


    # 普通消息
    def unPackWebcastChatMessage(self, data):
        chatMessage = ChatMessage()
        chatMessage.ParseFromString(data)
        data = json_format.MessageToDict(chatMessage, preserving_proto_field_name=True)
        # self.logger.info('[unPackWebcastChatMessage] [📧直播间弹幕消息] [房间Id：' + liveRoomId + '] ｜ ' + data['content'])
        self.logger.info('[unPackWebcastChatMessage] [📧直播间弹幕消息] [房间Id：' + self.liveRoomId + '] ｜ ' + data)
        return data


    # 礼物消息
    def unPackWebcastGiftMessage(self, data):
        giftMessage = GiftMessage()
        giftMessage.ParseFromString(data)
        data = json_format.MessageToDict(giftMessage, preserving_proto_field_name=True)
        log = json.dumps(data, ensure_ascii=False)
        # self.logger.info('[unPackWebcastGiftMessage] [🎁直播间礼物消息] [房间Id：' + self.liveRoomId + '] ｜ ' + log)
        return data


    # xx成员进入直播间消息
    def unPackWebcastMemberMessage(self, data):
        memberMessage = MemberMessage()
        memberMessage.ParseFromString(data)
        data = json_format.MessageToDict(memberMessage, preserving_proto_field_name=True)
        log = json.dumps(data, ensure_ascii=False)
        # self.logger.info('[unPackWebcastMemberMessage] [🚹🚺直播间成员加入消息] [房间Id：' + self.liveRoomId + '] ｜ ' + log)
        return data


    # 点赞
    def unPackWebcastLikeMessage(self, data):
        likeMessage = LikeMessage()
        likeMessage.ParseFromString(data)
        data = json_format.MessageToDict(likeMessage, preserving_proto_field_name=True)
        log = json.dumps(data, ensure_ascii=False)
        # self.logger.info('[unPackWebcastLikeMessage] [👍直播间点赞消息] [房间Id：' + self.liveRoomId + '] ｜ ' + log)
        return data


    # 解析WebcastMatchAgainstScoreMessage消息包体
    def unPackMatchAgainstScoreMessage(self, data):
        matchAgainstScoreMessage = MatchAgainstScoreMessage()
        matchAgainstScoreMessage.ParseFromString(data)
        data = json_format.MessageToDict(matchAgainstScoreMessage, preserving_proto_field_name=True)
        log = json.dumps(data, ensure_ascii=False)
        # self.logger.info('[unPackMatchAgainstScoreMessage] [🤷不知道是啥的消息] [房间Id：' + self.liveRoomId + '] ｜ ' + log)
        return data


    # 发送Ack请求
    def sendAck(self, ws, logId, internalExt):
        obj = PushFrame()
        obj.payloadType = 'ack'
        obj.logId = logId
        obj.payloadType = internalExt
        data = obj.SerializeToString()
        ws.send(data, websocket.ABNF.OPCODE_BINARY)
        # self.logger.info('[sendAck] [🌟发送Ack] [房间Id：' + self.liveRoomId + ']')


    def onError(self, ws, error):
        self.logger.error('[onError] [webSocket Error事件] [房间Id：' + self.liveRoomId + ']')

    def onClose(self, ws, a, b):
        self.logger.info('[onClose] [webSocket Close事件] [房间Id：' + self.liveRoomId + ']')


    def onOpen(self, ws):
        _thread.start_new_thread(self.ping, (ws,))
        self.logger.info('[onOpen] [webSocket Open事件] [房间Id：' + self.liveRoomId + ']')


    # 发送ping心跳包
    def ping(self, ws):
        while True:
            obj = PushFrame()
            obj.payloadType = 'hb'
            data = obj.SerializeToString()
            ws.send(data, websocket.ABNF.OPCODE_BINARY)
            # self.logger.info('[ping] [💗发送ping心跳] [房间Id：' + self.liveRoomId + ']')
            time.sleep(10)


    def wssServerStart(self):
        websocket.enableTrace(False)
        webSocketUrl = 'wss://webcast3-ws-web-lq.douyin.com/webcast/im/push/v2/?app_name=douyin_web&version_code=180800&webcast_sdk_version=1.3.0&update_version_code=1.3.0&compress=gzip&internal_ext=internal_src:dim|wss_push_room_id:'+self.liveRoomId+'|wss_push_did:7188358506633528844|dim_log_id:20230521093022204E5B327EF20D5CDFC6|fetch_time:1684632622323|seq:1|wss_info:0-1684632622323-0-0|wrds_kvs:WebcastRoomRankMessage-1684632106402346965_WebcastRoomStatsMessage-1684632616357153318&cursor=t-1684632622323_r-1_d-1_u-1_h-1&host=https://live.douyin.com&aid=6383&live_id=1&did_rule=3&debug=false&maxCacheMessageNumber=20&endpoint=live_pc&support_wrds=1&im_path=/webcast/im/fetch/&user_unique_id=7188358506633528844&device_platform=web&cookie_enabled=true&screen_width=1440&screen_height=900&browser_language=zh&browser_platform=MacIntel&browser_name=Mozilla&browser_version=5.0%20(Macintosh;%20Intel%20Mac%20OS%20X%2010_15_7)%20AppleWebKit/537.36%20(KHTML,%20like%20Gecko)%20Chrome/113.0.0.0%20Safari/537.36&browser_online=true&tz_name=Asia/Shanghai&identity=audience&room_id='+self.liveRoomId+'&heartbeatDuration=0&signature=00000000'
        h = {
            'cookie': 'ttwid='+self.ttwid,
            'user-agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36',
        }
        # 创建一个长连接
        ws = websocket.WebSocketApp(
            webSocketUrl, on_message=self.onMessage, on_error=self.onError, on_close=self.onClose,
            on_open=self.onOpen,
            header=h
        )
        ws.run_forever()

