# src/spider.py「国内平台 JSON 解析加固」批次的离线回归锁。
#
# 文件末尾的 SEV-N04（淘宝 Set-Cookie 覆盖用户 Cookie）小节是另一批回归锁，与本批判据共用桩具。
#
# 被测问题：平台解析函数用裸 json.loads + 深层链式索引，「房间不存在 / 未开通」「接口改版」「风控
# 返回 HTML 拦截页」三类成因全部塌缩成同一个 JSONDecodeError/KeyError，再被 @trace_error_decorator
# 吞成 {"is_live": False}——用户侧只见持续的「网址内容获取失败」，日志里没有任何区分线索。
#
# 覆盖平台：7 个平台共 8 类「四用例矩阵」行为用例（B站占两类：room_info 与 H5 标题接口），
# 即 B站 / 网易 CC / 微博 / 百度 / AcFun / 京东 / 咪咕，另加小红书与 YY 两个「静默离线」特例，
# 合计 10 类行为用例。名单 MIGRATED_FUNCTIONS 其余 11 个函数在本文件**只受逐函数 AST 棘轮约束、
# 没有行为用例**：blued / maoerfm / 酷狗 / showroom / 畅聊 / 音播 / 知乎 / CHZZK / vvxqiu /
# 17live 的在线离线断言在 tests/test_spider_platform.py，get_shopee_stream_url 两处都无行为用例。
#
# 判据设计（为什么这样断言，而不是只看返回值）：
#   - 异常响应被装饰器吞掉后**返回值**恰好就是正确的离线契约，所以只断言返回值是假绿；
#     必须同时断言「留下一条带接口标识的区分性告警」——把任一函数改回裸 json.loads，
#     该告警立即消失，本文件对应用例即红。
#   - 结构层另有 test_migrated_functions_have_no_bare_json_loads 逐函数棘轮兜底，
#     两者互补：行为用例证明「告警确实来自解析降级」，AST 用例证明「代码确实没走回老路」。
#   - 未开播是每 120 秒一轮的高频常态，**不能**为它刷告警（噪声日志等于没有日志），
#     故每个平台还各有一条「文档化离线形态必须保持静默」的用例，防止加固写成无脑告警。
#
# 原则（AGENTS「测试不得自实现被测逻辑」）：只打桩传输层（spider.async_req /
# get_acfun_sign_params / utils.run_node_script_async），_loads_dict、_dig 系列、
# _warn_api_abnormal 与各平台解析逻辑一律走真实代码。
#
# 离线可证 / 需真机复核的边界（本批所有桩载荷按公开接口惯例与仓内既有注释构造）：
#   - 可离线证：「裸解析必崩 → 加固后不崩且留线索」与真实取值无关，任何合法 JSON 错误信封或
#     HTML 都能复现，故异常样本用 -404 / errorCode / 截断三类通用形态。
#   - 需真机复核：各平台**正常**载荷的字段名与层级（B站 data.room_info.title、京东
#     result.livingRoomJump.params.id、酷狗 lines[-1].streamProfiles[0].httpsFlv[0] 等）沿用迁移前
#     源码的索引路径逐字照抄、本批刻意不改；真机若发现字段漂移会表现为「房间不存在」告警而非崩溃。
#   - 需真机复核：错误信封的 code/msg 键名。_warn_api_abnormal 按 code / status / errorCode /
#     resultCode 与 message / msg / errorMsg 两组别名依次试探，第三种键名只退化成「少一条线索」。

import ast
import contextlib
import json
import types
from pathlib import Path
from typing import Any, cast
from unittest.mock import AsyncMock, Mock, patch

import pytest

from src import spider as sp

ROOT = Path(__file__).resolve().parent.parent

# 典型 WAF/风控拦截页：HTTP 200 + 合法 HTML，但绝不是 JSON（斗鱼/虎牙/B站 CDN 实测形态）
WAF_HTML = "<html><head><title>Access Protected</title></head><body>cf-browser-verification</body></html>"

# 本批已迁移到 _loads_dict + _dig 的 21 个平台解析函数：逐函数棘轮断言其体内零裸 json.loads。
# 名单也是「用例与被测函数是否失配」的自检依据：函数改名/删除时本文件先红，避免「扫描 0 个函数、于是 0 违规」的假绿（AGENTS「config.ini 键集审计」同族教训）。
MIGRATED_FUNCTIONS = (
    "get_yy_stream_data",
    "get_bilibili_room_info_h5",
    "get_bilibili_room_info",
    "get_xhs_stream_url",
    "get_blued_stream_url",
    "get_netease_stream_data",
    "get_maoerfm_stream_url",
    "get_baidu_stream_data",
    "get_weibo_stream_data",
    "get_kugou_stream_url",
    "get_showroom_stream_data",
    "get_acfun_stream_data",
    "get_changliao_stream_url",
    "get_yinbo_stream_url",
    "get_zhihu_stream_url",
    "get_chzzk_stream_data",
    "get_vvxqiu_stream_url",
    "get_17live_stream_url",
    "get_shopee_stream_url",
    "get_jd_stream_url",
    "get_migu_stream_url",
)

# 全文件剩余裸 json.loads 调用点上限（不含唯一豁免的 _safe_loads 自身）。
# [历史注] 国内批次前实测 75 处，国内批次迁移 38 处 → 37 处，海外批次再迁 36 处 → **1 处**。
# 唯一豁免是 get_twitchtv_room_info 的 GQL 响应（批量查询返回 **list**，_loads_dict 只收 dict，
# 且禁止另造第四支 helper；该处已自带 try/except JSONDecodeError + 告警 + 显式 RuntimeError，
# 等价于加固形态）。后续任何批次只允许把该数压低，任何回升即红。类名不以 Test 开头，pytest 不会把基类当用例收集。
BARE_JSON_LOADS_CEILING = 1


def _fake_logger() -> types.SimpleNamespace:
    # 捕获 sp.logger.<level>(msg) 的文本。info/debug/success 记为 Mock 但不入列——
    # 判据取 warning 这一档：本文件同时要求「正常离线轮次零告警」，所以「有没有留下区分性线索」
    # 只能由 warning 是否出现来判定（把线索写成 info/debug 会让两条判据同时失去区分力）。
    msgs: list[str] = []
    sink = Mock(side_effect=lambda msg, *a, **k: msgs.append(str(msg)))
    return types.SimpleNamespace(
        msgs=msgs,
        warning=sink,
        error=sink,
        info=Mock(),
        debug=Mock(),
        success=Mock(),
        exception=sink,
        trace=Mock(),
        log=sink,
    )


def _fake_req(payloads: dict[str, Any], default: str = WAF_HTML) -> AsyncMock:
    # 按 URL 子串路由的 async_req 替身。值可为字符串（固定响应）或列表（同 URL 多次请求
    # 依次取用）；未命中的 URL 一律回 `default`——让「漏桩」显形成解析失败而非静默通过。
    queue: dict[str, list[Any]] = {
        key: (value if isinstance(value, list) else [value]) for key, value in payloads.items()
    }

    async def _req(*args: object, **kwargs: object) -> Any:
        url = str(kwargs.get("url") or (args[0] if args else ""))
        for key, items in queue.items():
            if key in url:
                assert items, f"{key} 的桩响应已用尽（说明解析链路多发了请求）"
                return items.pop(0)
        return default

    return AsyncMock(side_effect=_req)


def _assert_offline(result: object, case: str = "") -> None:
    # 未开播契约：必须是 dict 且 is_live / live_status 均为假值。
    # B站 room_info 用 live_status、其余平台用 is_live，两种都覆盖。
    assert isinstance(result, dict), f"应返回 dict 契约，实际 {result!r} ({case})"
    body = cast("dict[str, object]", result)
    assert not body.get("is_live", False), f"异常响应被误判为开播: {body} ({case})"
    assert not body.get("live_status", False), f"异常响应被误判为直播中: {body} ({case})"


def _assert_clue(logger: types.SimpleNamespace, needle: str, case: str) -> None:
    # 「没有裸 json.loads」的机检口径：必须有一条带接口标识的区分性告警。
    # 裸 json.loads 回归时异常被装饰器吞掉，日志里只剩装饰器自身的堆栈、不含接口标识 → 本断言变红。
    assert any(needle in m for m in logger.msgs), f"{case} 缺少 {needle!r} 的区分性告警，实际日志: {logger.msgs}"


class _GuardCase:
    # 各平台共用三条统一判据的基类；子类只提供 URL / 桩路由 / 异常样本 / 期望值。
    # abnormal 元素为 (响应体, 期望的接口标识, 可选：须出现在日志里的信封 code/msg)。
    URL = ""
    abnormal: list[tuple[str, str, str | None]] = []
    expected: object = None
    silent_body: str | None = None
    silent_expected: object = None

    def payloads(self, body: str | None) -> dict[str, Any]:
        # body=None 表示「全部走正常桩」（成功路径用例）；否则把首个失败点换成异常响应体。
        raise NotImplementedError

    async def call(self) -> Any:
        raise NotImplementedError

    def extras(self) -> tuple[contextlib.AbstractContextManager[Any], ...]:
        # 子类追加的非传输层桩（如 AcFun 游客签名、咪咕 node 签名），每次用例内新建。
        return ()

    def check_offline(self, result: Any, case: str) -> None:
        _assert_offline(result, case)

    async def test_abnormal_never_raises_and_leaves_clue(self) -> None:
        for body, needle, envelope_clue in self.abnormal:
            logger = _fake_logger()
            with contextlib.ExitStack() as stack:
                for cm in self.extras():
                    stack.enter_context(cm)
                stack.enter_context(patch.object(sp, "async_req", new=_fake_req(self.payloads(body), default=body)))
                stack.enter_context(patch.object(sp, "logger", logger))
                result = await self.call()
            self.check_offline(result, body[:40])
            _assert_clue(logger, needle, body[:40])
            if envelope_clue:
                # 平台错误信封的 code/msg 必须原样落日志——它是区分「房间不存在」与「接口改版」的唯一依据
                assert any(envelope_clue in m for m in logger.msgs), f"信封 {envelope_clue!r} 未落日志: {logger.msgs}"

    async def test_success_path_unchanged(self) -> None:
        logger = _fake_logger()
        with contextlib.ExitStack() as stack:
            for cm in self.extras():
                stack.enter_context(cm)
            stack.enter_context(patch.object(sp, "async_req", new=_fake_req(self.payloads(None))))
            stack.enter_context(patch.object(sp, "logger", logger))
            result = await self.call()
        assert result == self.expected, "成功路径的返回结构被改动（本批只允许「不崩 / 不撒谎」）"
        assert logger.msgs == [], f"成功路径不应产生告警: {logger.msgs}"

    async def test_documented_offline_stays_silent(self) -> None:
        # 「未开播」每 120 秒一轮，为它刷 warning 会把真线索淹掉——必须保持静默。
        if self.silent_body is None:
            pytest.skip("该平台无独立的文档化离线形态")
        logger = _fake_logger()
        with contextlib.ExitStack() as stack:
            for cm in self.extras():
                stack.enter_context(cm)
            stack.enter_context(patch.object(sp, "async_req", new=_fake_req(self.payloads(self.silent_body))))
            stack.enter_context(patch.object(sp, "logger", logger))
            result = await self.call()
        self.check_offline(result, "silent")
        if self.silent_expected is not None:
            assert result == self.silent_expected
        assert logger.msgs == [], f"正常离线形态被刷了告警（噪声即失效日志）: {logger.msgs}"


class TestBilibiliRoomInfoHardening(_GuardCase):
    # B站房间信息：room_init → master/info → getH5InfoByRoom 三连，任一环裸解析都会静默漏录。
    URL = "https://live.bilibili.com/26066074"
    _INIT = '{"code":0,"message":"0","msg":"","data":{"room_id":23058,"uid":401742185,"live_status":1}}'
    _MASTER = '{"code":0,"data":{"info":{"uname":"受检主播","face":""}}}'
    _H5 = '{"code":0,"data":{"room_info":{"title":"晚间直播"}}}'
    _OFFLINE_INIT = '{"code":0,"message":"0","data":{"room_id":23058,"uid":401742185,"live_status":0}}'
    abnormal = [
        (WAF_HTML, "B站 room_init", None),
        ('{"code":-404,"message":"啥都木有","msg":"啥都木有"}', "B站 room_init", "-404"),
        ('{"data": {"uid": 4', "B站 room_init", None),
    ]
    expected = {"anchor_name": "受检主播", "live_status": True, "room_url": URL, "title": "晚间直播"}
    # live_status==0 是「房间存在、主播没开播」——正常轮询常态，不得告警
    silent_body = _OFFLINE_INIT
    silent_expected = {"anchor_name": "受检主播", "live_status": False, "room_url": URL, "title": "晚间直播"}

    def payloads(self, body: str | None) -> dict[str, Any]:
        return {
            "Room/room_init": body if body is not None else self._INIT,
            "Master/info": self._MASTER,
            "getH5InfoByRoom": self._H5,
        }

    async def call(self) -> Any:
        return await sp.get_bilibili_room_info(self.URL)


class TestBilibiliH5TitleHardening(_GuardCase):
    # H5 标题接口返回 str 契约（_or_none 装饰器）：离线契约是「空串」，不是 dict。
    URL = "https://live.bilibili.com/26066074"
    abnormal = [
        (WAF_HTML, "B站 getH5InfoByRoom", None),
        ('{"code":-404,"msg":"啥都木有"}', "B站 getH5InfoByRoom", "-404"),
        ('{"data": {"room_info": {', "B站 getH5InfoByRoom", None),
    ]
    expected = "晚间直播"
    # data 在、room_info 无 title：既有静默形态（标题缺失不影响开播判定）
    silent_body = '{"code":0,"data":{"room_info":{}}}'

    def check_offline(self, result: Any, case: str) -> None:
        assert not result, f"异常响应应回空标题，实际 {result!r} ({case})"

    def payloads(self, body: str | None) -> dict[str, Any]:
        return {"getH5InfoByRoom": body if body is not None else '{"code":0,"data":{"room_info":{"title":"晚间直播"}}}'}

    async def call(self) -> Any:
        return await sp.get_bilibili_room_info_h5(self.URL)


class TestNeteaseCCHardening(_GuardCase):
    URL = "https://cc.163.com/492087/"
    # __NEXT_DATA__ 的正则要求 `<script id="__NEXT_DATA__" .* crossorigin="anonymous">...</script></body>`，
    # 桩载荷必须整体满足该形态，否则测的是「正则未命中」分支而非本批要加固的解析分支。

    @staticmethod
    def _wrap(inner: str) -> str:
        return '<script id="__NEXT_DATA__" prop-data="x" crossorigin="anonymous">' + inner + "</script></body>"

    _OK = _wrap(
        json.dumps(
            {
                "props": {
                    "pageProps": {
                        "roomInfoInitData": {
                            "nickname": "兜底昵称",
                            "live": {
                                "status": 1,
                                "nickname": "CC主播",
                                "title": "夜间电台",
                                "sharefile": "https://a.share.163.com/live/x.m3u8",
                                "quickplay": [{"name": "高清", "url": "https://a/hd.m3u8"}],
                            },
                        }
                    }
                }
            },
            ensure_ascii=False,
        )
    )
    abnormal = [
        # (a) 风控把内联 JSON 换成 HTML，但保留页面骨架——裸 json.loads 的原始崩点
        (_wrap("<html>blocked</html>"), "网易CC __NEXT_DATA__", None),
        (_wrap('{"props":{"pageProps":{}}'), "网易CC __NEXT_DATA__", None),
        (_wrap('{"props": {"pageProps": {'), "网易CC __NEXT_DATA__", None),
    ]
    # 缺 roomInfoInitData.live 与「截断」同因（接口改版），故三条都要求告警；
    # 「房间存在但未开播」是 status!=1，见下方 silent 用例。
    silent_body = _wrap(
        json.dumps({"props": {"pageProps": {"roomInfoInitData": {"nickname": "CC主播", "live": {"status": 0}}}}})
    )
    expected = {
        "is_live": True,
        "anchor_name": "CC主播",
        "title": "夜间电台",
        "stream_list": [{"name": "高清", "url": "https://a/hd.m3u8"}],
        "m3u8_url": "https://a.share.163.com/live/x.m3u8",
    }

    def payloads(self, body: str | None) -> dict[str, Any]:
        return {"cc.163.com": body if body is not None else self._OK}

    async def call(self) -> Any:
        return await sp.get_netease_stream_data(self.URL)

    async def test_page_without_next_data_still_does_not_escape(self) -> None:
        # 整页被换成 WAF 页时走的是既有的「正则未命中 → ValueError」路径，
        # 装饰器必须兜成离线契约（本批不动该分支，只锁「不逃逸到主循环」）。
        logger = _fake_logger()
        with patch.object(sp, "async_req", new=_fake_req({}, default=WAF_HTML)), patch.object(sp, "logger", logger):
            result = await sp.get_netease_stream_data(self.URL)
        _assert_offline(result, "no __NEXT_DATA__")


class TestWeiboHardening(_GuardCase):
    # show/ 直链入口只需一次接口请求，可把断言精确落在 pc/anchor/live 的解析加固上；
    # /u/<uid> 主页列表另有「无直播静默」用例覆盖。
    URL = "https://weibo.com/show/5091185733099999"
    _OK = json.dumps(
        {
            "data": {
                "user_info": {"name": "微博主播"},
                "item": {
                    "status": 1,
                    "desc": "发布会直播",
                    "stream_info": {
                        "pull": {
                            "live_origin_hls_url": "https://mweixin.sina.cn/live/x_原画.m3u8",
                            "live_origin_flv_url": "https://mweixin.sina.cn/live/x_原画.flv",
                        }
                    },
                },
            }
        },
        ensure_ascii=False,
    )
    abnormal = [
        (WAF_HTML, "微博 pc/anchor/live", None),
        ('{"error":"Forbidden","code":10036}', "微博 pc/anchor/live", "10036"),
        ('{"data": {"user_info": {"name"', "微博 pc/anchor/live", None),
    ]
    expected = {
        "anchor_name": "微博主播",
        "is_live": True,
        "title": "发布会直播",
        "play_url_list": [
            {
                "m3u8_url": "https://mweixin.sina.cn/live/x_原画.m3u8",
                "flv_url": "https://mweixin.sina.cn/live/x_原画.flv",
            },
            {"m3u8_url": "https://mweixin.sina.cn/live/x.m3u8", "flv_url": "https://mweixin.sina.cn/live/x.flv"},
        ],
    }

    async def test_flv_only_room_is_live_with_record_url(self) -> None:
        # 只下发 FLV（无 HLS）的房间必须判开播并以 record_url 承载该路：上层以 m3u8/hls 为主通道，缺
        # record_url 就取不到流。[历史注] 旧实现要求 HLS+FLV 同时存在，把这类房间每轮静默判为未开播。
        body = json.dumps(
            {
                "data": {
                    "user_info": {"name": "微博主播"},
                    "item": {
                        "status": 1,
                        "desc": "发布会直播",
                        "stream_info": {"pull": {"live_origin_flv_url": "https://mweixin.sina.cn/live/x_原画.flv"}},
                    },
                }
            },
            ensure_ascii=False,
        )
        logger = _fake_logger()
        with patch.object(sp, "async_req", new=_fake_req({"anchor/live": body})), patch.object(sp, "logger", logger):
            result = await sp.get_weibo_stream_data(self.URL)
        body_d = cast("dict[str, object]", result)
        assert body_d.get("is_live") is True, f"纯 FLV 房间被误判未开播: {result}"
        assert body_d.get("record_url") == "https://mweixin.sina.cn/live/x_原画.flv", result
        assert logger.msgs == [], f"正常单路开播不应告警: {logger.msgs}"

    async def test_hls_only_room_is_live(self) -> None:
        # 只下发 HLS 的房间必须判开播（同上一条单路形态回归锁：旧实现同样误判未开播）。
        body = json.dumps(
            {
                "data": {
                    "user_info": {"name": "微博主播"},
                    "item": {
                        "status": 1,
                        "desc": "发布会直播",
                        "stream_info": {"pull": {"live_origin_hls_url": "https://mweixin.sina.cn/live/x_原画.m3u8"}},
                    },
                }
            },
            ensure_ascii=False,
        )
        logger = _fake_logger()
        with patch.object(sp, "async_req", new=_fake_req({"anchor/live": body})), patch.object(sp, "logger", logger):
            result = await sp.get_weibo_stream_data(self.URL)
        body_d = cast("dict[str, object]", result)
        assert body_d.get("is_live") is True, f"纯 HLS 房间被误判未开播: {result}"
        assert logger.msgs == [], f"正常单路开播不应告警: {logger.msgs}"

    # item.status != 1 = 房间存在但未开播，必须静默
    silent_body = json.dumps({"data": {"user_info": {"name": "微博主播"}, "item": {"status": 2}}}, ensure_ascii=False)
    silent_expected = {"anchor_name": "微博主播", "is_live": False}

    def payloads(self, body: str | None) -> dict[str, Any]:
        return {"anchor/live": body if body is not None else self._OK}

    async def call(self) -> Any:
        return await sp.get_weibo_stream_data(self.URL)

    async def test_homepage_without_live_post_stays_silent(self) -> None:
        # 「该用户没有直播帖」是正常离线形态：list 里无 object_type==live 不得刷告警
        logger = _fake_logger()
        body = '{"data":{"list":[{"page_info":{"object_type":"video","object_id":"1"}}]}}'
        with patch.object(sp, "async_req", new=_fake_req({"mymblog": body})), patch.object(sp, "logger", logger):
            result = await sp.get_weibo_stream_data("https://weibo.com/u/5885340893")
        _assert_offline(result, "no live post")
        assert logger.msgs == []


class TestBaiduHardening(_GuardCase):
    # room_id 位于查询串末尾：同一用例顺带锁住已修的正则形态（不得改回 `(.*?)&`）。
    URL = "https://live.baidu.com/m/media/pclive/pchome/live.html?room_id=9175031377"
    _OK = json.dumps(
        {
            "result": "success",
            "data": {
                "9175031377": {
                    "status": "0",
                    "host": {"name": "百度主播"},
                    "video": {
                        "title": "带货直播",
                        "url_clarity_list": [{"urls": {"flv": "https://flv.live.baidu.com/abc123.flv"}}],
                    },
                }
            },
        },
        ensure_ascii=False,
    )
    abnormal = [
        (WAF_HTML, "百度 searchbox", None),
        ('{"code":-1,"message":"room not exist"}', "百度 searchbox", "room not exist"),
        ('{"data": {"9175031377": {"host"', "百度 searchbox", None),
    ]
    # 百度 searchbox 对「房间存在、未开播」同样回 status!=0 且不含 data 之外结构，
    # 无法在离线环境区分，故本平台的离线静默用例只覆盖 status!=0。
    silent_body = json.dumps(
        {
            "data": {
                "9175031377": {
                    "status": "2",
                    "host": {"name": "百度主播"},
                    "video": {"title": "回放", "url_clarity_list": []},
                }
            }
        }
    )
    expected = {
        "anchor_name": "百度主播",
        "is_live": True,
        "title": "带货直播",
        "play_url_list": ["https://hls.liveshow.bdstatic.com/live/abc123.m3u8"],
    }
    silent_expected = {"anchor_name": "百度主播", "is_live": False}

    def payloads(self, body: str | None) -> dict[str, Any]:
        return {"searchbox": body if body is not None else self._OK}

    async def call(self) -> Any:
        return await sp.get_baidu_stream_data(self.URL)


class TestAcfunHardening(_GuardCase):
    URL = "https://live.acfun.cn/live/17912421"
    _PROFILE = '{"success":true,"profile":{"userId":17912421,"name":"A站主播","liveId":5982113}}'
    # videoPlayRes 是「JSON 串套在 JSON 字段里」的二重编码——本批最深的一处链式索引崩点
    _PLAY = json.dumps(
        {
            "success": True,
            "data": {
                "caption": "深夜电台",
                "videoPlayRes": json.dumps(
                    {
                        "liveAdaptiveManifest": [
                            {
                                "adaptationSet": {
                                    "representation": [
                                        {"bitrate": 2000, "url": "https://a/low.flv"},
                                        {"bitrate": 4000, "url": "https://a/high.flv"},
                                    ]
                                }
                            }
                        ]
                    }
                ),
            },
        }
    )
    abnormal = [
        (WAF_HTML, "AcFun userInfo", None),
        ('{"errorCode":11000,"message":"user not found"}', "AcFun userInfo", "11000"),
        (
            json.dumps({"data": {"caption": "x", "videoPlayRes": '{"liveAdaptiveManifest": [{"adaptationSet": {'}}),
            "AcFun startPlay(videoPlayRes)",
            None,
        ),
    ]
    # profile 有、无 liveId = 主播未开播（该平台用 liveId 承载开播状态），必须静默
    silent_body = '{"success":true,"profile":{"userId":17912421,"name":"A站主播"}}'

    def payloads(self, body: str | None) -> dict[str, Any]:
        if body is not None and "liveAdaptiveManifest" in body:
            # 第三条异常样本打在第二个接口（startPlay）上，userInfo 仍须正常
            return {"userInfo": self._PROFILE, "startPlay": body}
        return {"userInfo": body if body is not None else self._PROFILE, "startPlay": self._PLAY}

    def extras(self) -> tuple[contextlib.AbstractContextManager[Any], ...]:
        # 游客三件套（visitor/login）是登录态传输，不是本批加固对象——打桩后仍走真实 startPlay 解析
        return (patch.object(sp, "get_acfun_sign_params", new=AsyncMock(return_value=("401742185", "did-1", "st-1"))),)

    async def call(self) -> Any:
        return await sp.get_acfun_stream_data(self.URL)

    async def test_success_path_unchanged(self) -> None:
        logger = _fake_logger()
        with (
            patch.object(sp, "async_req", new=_fake_req({"userInfo": self._PROFILE, "startPlay": self._PLAY})),
            patch.object(sp, "get_acfun_sign_params", new=AsyncMock(return_value=("1", "d", "s"))),
            patch.object(sp, "logger", logger),
        ):
            result = await sp.get_acfun_stream_data(self.URL)
        assert result["anchor_name"] == "A站主播"
        assert result["is_live"] is True
        assert result["title"] == "深夜电台"
        # 码率降序是 stream.py 选档前提（原实现 sorted(key=itemgetter("bitrate"), reverse=True)）
        reps = cast("list[dict[str, object]]", result["play_url_list"])
        assert [rep["bitrate"] for rep in reps] == [4000, 2000]
        assert logger.msgs == []

    async def test_offline_room_keeps_anchor_name(self) -> None:
        logger = _fake_logger()
        with (
            patch.object(sp, "async_req", new=_fake_req({"userInfo": self.silent_body})),
            patch.object(sp, "logger", logger),
        ):
            result = await sp.get_acfun_stream_data(self.URL)
        _assert_offline(result, "acfun offline")
        assert result["anchor_name"] == "A站主播"
        assert logger.msgs == []


class TestJdHardening(_GuardCase):
    URL = "https://ydzjster.jd.com/n/entry"
    _REDIRECT = "https://ydzjster.jd.com/n/page?authorId=401338"
    _TALENT = '{"code":"0","result":{"talentName":"京东主播","livingRoomJump":{"params":{"id":"9527"}}}}'
    _PLAY = '{"code":"0","data":{"status":1,"videoUrl":"https://j/a.flv","h5VideoUrl":"https://j/a.m3u8"}}'
    _CONTENT = '{"result":{"content":[{"title":"618 专场"}]}}'
    abnormal = [
        (WAF_HTML, "京东 talent_head_findTalentMsg", None),
        ('{"code":"3","message":"not login"}', "京东 talent_head_findTalentMsg", "not login"),
        ('{"data": {"status": 1, "videoU', "京东 getImmediatePlayToM", None),
    ]
    # result 有、livingRoomJump 无 = 主播未在播（原实现即静默 return），必须保持静默
    silent_body = '{"code":"0","result":{"talentName":"京东主播"}}'
    silent_expected = {"anchor_name": "京东主播", "is_live": False}
    expected = {
        "anchor_name": "京东主播",
        "is_live": True,
        "title": "618 专场",
        "m3u8_url": "https://j/a.m3u8",
        "flv_url": "https://j/a.flv",
        "record_url": "https://j/a.m3u8",
    }

    def payloads(self, body: str | None) -> dict[str, Any]:
        # 路由键必须能命中「原始入口 URL」——京东第一步是解重定向，URL 里没有 findTalentMsg
        talent: Any = self._TALENT if body is None else body
        play: Any = self._PLAY
        if body is not None and body.startswith('{"data":'):
            # 第三条异常样本落在取流接口上，主播信息接口须保持正常
            talent, play = self._TALENT, body
        return {
            "ydzjster.jd.com/n": self._REDIRECT,
            "findTalentMsg": talent,
            "client.action": play,
            "jdTalentContentList": self._CONTENT,
        }

    async def call(self) -> Any:
        return await sp.get_jd_stream_url(self.URL)


class TestMiguHardening(_GuardCase):
    URL = "https://www.miguvideo.com/p/74eb5f0c1c0c4a86"
    _BASIC = '{"code":"0","body":{"title":"咪咕体育","detailPageTitle":"世界杯直播","pId":"601234"}}'
    # migu.js 签名后的地址（node 桩返回值）——flv 直链分支，避免多余一次重定向请求
    _SIGNED = "https://play.miguvideo.com/live/a.flv?ddCalcu=x&sv=y"
    _PLAY = '{"code":"200","body":{"content":{"currentLive":"1"},"urlInfo":{"url":"https://t.cntvcdn/live/a.flv"}}}'
    abnormal = [
        (WAF_HTML, "咪咕 basic-data", None),
        ('{"code":"404","message":"no such content"}', "咪咕 basic-data", "no such content"),
        ('{"code":"200","body": {"cont', "咪咕 playurl", None),
    ]
    # body 有、pId 无 = 既有的「房间不存在/失效」静默路径（basic-data 对下线内容仍回 body）
    silent_body = '{"code":"0","body":{"title":"咪咕体育"}}'
    silent_expected = {"anchor_name": "咪咕体育", "is_live": False}
    expected = {
        "anchor_name": "咪咕体育",
        "is_live": True,
        "title": "咪咕体育-世界杯直播",
        "flv_url": _SIGNED,
        "record_url": _SIGNED,
    }

    def payloads(self, body: str | None) -> dict[str, Any]:
        basic: Any = self._BASIC if body is None else body
        play: Any = self._PLAY
        if body is not None and body.startswith('{"code":"200"'):
            basic, play = self._BASIC, body
        return {"basic-data": basic, "playurl": play}

    def extras(self) -> tuple[contextlib.AbstractContextManager[Any], ...]:
        # migu.js 签名是子进程边界（非 JSON 解析），打桩后 flv 分支仍走真实判定
        return (patch.object(sp.utils, "run_node_script_async", new=AsyncMock(return_value=self._SIGNED)),)

    async def call(self) -> Any:
        return await sp.get_migu_stream_url(self.URL)


class TestXhsHardening(_GuardCase):
    # 小红书：__INITIAL_STATE__ 未命中 liveStream 是「未开播/分享页」的正常形态（函数下方还有
    # profile 兜底补昵称），故只有「命中了脚本标签但内联 JSON 被截断」才需要归因。
    # URL 用真实直播形态 /livestream/<数字房间ID> 并带 host_id：既符合 parse_xhs_live_url 的路径白名单，
    # 也让下方 profile 兜底仍能拿到 user_id（旧桩的 /live/livestream/x123 是杜撰形态，现按 non_live_path 拒收）。
    URL = "https://www.xiaohongshu.com/livestream/123456?host_id=5f3e2a1b"
    _PROFILE_HTML = "<title>@兜底昵称 的个人主页</title>"
    _TRUNCATED = '<script>window.__INITIAL_STATE__={"liveStream": {"liveStatus": "succe</script>'
    _NO_LIVE = "<script>window.__INITIAL_STATE__=" + json.dumps({"user": {"notes": []}}) + "</script>"
    _OK = (
        "<script>window.__INITIAL_STATE__="
        + json.dumps(
            {
                "liveStream": {
                    "liveStatus": "success",
                    "roomData": {
                        "roomInfo": {
                            "roomTitle": "聊天电台",
                            "deeplink": (
                                "xhsdiscover://live/abc.flv?host_nickname=%E5%B0%8F%E7%BA%A2%E4%B9%A6"
                                "&flvUrl=http%3A%2F%2Flive-source-play.xhscdn.com%2Flive%2Fabc.flv"
                            ),
                        }
                    },
                }
            },
            ensure_ascii=False,
        ).replace("null", "undefined")
        + "</script>"
    )
    abnormal = [(_TRUNCATED, "小红书 __INITIAL_STATE__", None)]
    silent_body = _NO_LIVE
    # room_id / normalized_url 是小红书链接归一化新增的稳定字段：
    # 前者给配置回写与日志定位，后者让短链/动态路径解析出的规范地址能落回 URL_config.ini。
    expected = {
        "anchor_name": "小红书",
        "is_live": True,
        "title": "聊天电台",
        "flv_url": "http://live-source-play.xhscdn.com/live/abc.flv",
        "m3u8_url": "http://live-source-play.xhscdn.com/live/abc.m3u8",
        "record_url": "http://live-source-play.xhscdn.com/live/abc.flv",
        "room_id": "abc",
        "normalized_url": "https://www.xiaohongshu.com/livestream/123456?host_id=5f3e2a1b",
    }

    def payloads(self, body: str | None) -> dict[str, Any]:
        return {"livestream": body if body is not None else self._OK, "user/profile": self._PROFILE_HTML}

    async def call(self) -> Any:
        return await sp.get_xhs_stream_url(self.URL)

    async def test_truncated_state_falls_back_to_profile_nickname(self) -> None:
        # 截断时不得整轮作废：仍要走完 profile 兜底把昵称补回来（迁移前是直接抛错）
        logger = _fake_logger()
        with (
            patch.object(sp, "async_req", new=_fake_req(self.payloads(self._TRUNCATED), default=self._TRUNCATED)),
            patch.object(sp, "logger", logger),
        ):
            result = await sp.get_xhs_stream_url(self.URL)
        _assert_offline(result, "xhs truncated")
        assert result["anchor_name"] == "兜底昵称"
        _assert_clue(logger, "小红书 __INITIAL_STATE__", "xhs")


class TestYyHardening(_GuardCase):
    # YY 的开播判定在 src/stream.py::get_yy_stream_url 里做（avp_info_res 缺失即离线），
    # 所以 spider 侧唯一需要归因的是「stream-manager 响应整体解析不出对象」。
    URL = "https://www.yy.com/12345"
    _PAGE = 'nick: "YY主播",\n  logo: "x"\n  sid : "900001",\n   ssid: "2"\n'
    _STREAM = '{"head":{"result":0},"avp_info_res":{"stream_line_addr":{"a":{"cdn_info":{"url":"http://x/a.flv"}}}}}'
    abnormal = [
        (WAF_HTML, "YY stream-manager", None),
        ('{"head": {"result": 0,', "YY stream-manager", None),
    ]
    # 未开播频道回合法 JSON 但没有 avp_info_res —— 正常离线，不得告警
    silent_body = '{"head":{"result":0}}'

    # YY 的返回值是 stream-manager 原始响应 + anchor_name/title 拼装，不含 is_live 键，
    # 故离线判据只看「没有 avp_info_res」——开播判定在 src/stream.py 侧做。
    expected = {
        "head": {"result": 0},
        "avp_info_res": {"stream_line_addr": {"a": {"cdn_info": {"url": "http://x/a.flv"}}}},
        "anchor_name": "YY主播",
        "title": "YY标题",
    }
    silent_expected = {"head": {"result": 0}, "anchor_name": "YY主播", "title": "YY标题"}

    def payloads(self, body: str | None) -> dict[str, Any]:
        return {
            "www.yy.com/12345": self._PAGE,
            "stream-manager": body if body is not None else self._STREAM,
            # 标题是第二次独立请求，永远给正常桩——它的降级路径由既有用例覆盖
            "live/detail": '{"code":0,"data":{"roomName":"YY标题"}}',
        }

    async def call(self) -> Any:
        return await sp.get_yy_stream_data(self.URL)

    def check_offline(self, result: Any, case: str) -> None:
        assert isinstance(result, dict)
        assert not cast("dict[str, object]", result).get("is_live", False)
        assert "avp_info_res" not in result or not cast("dict[str, object]", result).get("avp_info_res")
        # 昵称来自第一段页面正则，异常响应不得把它一起吞掉
        assert cast("dict[str, object]", result).get("anchor_name") == "YY主播"


def _json_loads_calls(tree: ast.AST) -> list[ast.Call]:
    out: list[ast.Call] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if (
            isinstance(func, ast.Attribute)
            and func.attr == "loads"
            and isinstance(func.value, ast.Name)
            and func.value.id == "json"
        ):
            out.append(node)
    return out


def test_migrated_functions_have_no_bare_json_loads() -> None:
    # 逐函数棘轮：本批 21 个平台解析函数体内必须零裸 json.loads（改回一处即红）。
    # 只按「函数名 + AST 区间」判定，避免全文计数被其它未迁移批次稀释成假绿。
    src = (ROOT / "src" / "spider.py").read_text(encoding="utf-8-sig")
    tree = ast.parse(src)
    offenders: list[str] = []
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name in MIGRATED_FUNCTIONS:
            found.add(node.name)
            hits = [call.lineno for call in _json_loads_calls(node)]
            if hits:
                offenders.append(f"{node.name}:{hits}")
    missing = [name for name in MIGRATED_FUNCTIONS if name not in found]
    assert not missing, f"用例与被测函数已失配（函数被改名/删除）: {missing}"
    assert not offenders, "以下函数仍含裸 json.loads（应走 _loads_dict + _dig）: " + ", ".join(offenders)


def test_bare_json_loads_ratchet_does_not_grow() -> None:
    # 全文件棘轮：唯一豁免是 _safe_loads 自身（它必须真的用 json.loads，否则 _loads_dict 恒回
    # {}、全员假离线）。剩余批次的迁移只允许压低计数，任何回升即红。
    src = (ROOT / "src" / "spider.py").read_text(encoding="utf-8-sig")
    tree = ast.parse(src)
    guard = next(
        (
            n
            for n in ast.walk(tree)
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == "_safe_loads"
        ),
        None,
    )
    assert guard is not None, "_safe_loads 被删除——_loads_dict 将失去异常安全实现（假绿）"
    exempt = {id(node) for node in ast.walk(guard)}
    assert _json_loads_calls(guard), "_safe_loads 内已无 json.loads，则 _loads_dict 恒返回 {}（全员假离线）"
    remaining = [call.lineno for call in _json_loads_calls(tree) if id(call) not in exempt]
    assert len(remaining) <= BARE_JSON_LOADS_CEILING, (
        f"裸 json.loads 由 {BARE_JSON_LOADS_CEILING} 回升到 {len(remaining)}（行号 {remaining}）："
        "MID-48 迁移不得回退，新代码请直接用 _loads_dict + _dig"
    )


def test_dig_helpers_never_raise_on_missing_or_wrong_type() -> None:
    # _dig/_dig_str/_dig_list 是「不可能抛异常」这一承诺的实现本身；若有人给它加裸下标/解包，
    # 本用例先红——它同时是上面所有告警用例不崩的前提。
    broken: object = {"a": {"b": [None]}}
    assert sp._dig(broken, "a", "b", 0, "c") is None
    assert sp._dig(broken, "a", "b", 9) is None
    assert sp._dig(broken, "a", "b", "c") is None
    assert sp._dig("not json at all", "a") is None
    assert sp._dig(None, "a", "b") is None
    assert sp._dig_str(broken, "a", "b", 0) == ""
    assert sp._dig_list(broken, "a", "b") == [None]
    assert sp._dig_list(broken, "a", "b", 0) == []


def test_warn_api_abnormal_distinguishes_empty_from_missing_field() -> None:
    # 两种成因必须是两条不同文案——这正是本批加固的判定标准
    # （用户侧原来只有一句「网址内容获取失败,进行重试中…」）。
    empty = _fake_logger()
    with patch.object(sp, "logger", empty):
        sp._warn_api_abnormal("", "Test api", "data", {})
    assert empty.msgs == ["Test api 返回空响应（风控或网络失败）"]

    envelope = _fake_logger()
    with patch.object(sp, "logger", envelope):
        sp._warn_api_abnormal('{"code":404}', "Test api", "data", {"code": 404})
    assert len(envelope.msgs) == 1
    assert "Test api" in envelope.msgs[0] and "data" in envelope.msgs[0] and "404" in envelope.msgs[0]

    # 快手系/AcFun 用 errorCode/resultCode、B站用 message、部分平台用 msg——都要能带出来
    mixed = _fake_logger()
    with patch.object(sp, "logger", mixed):
        sp._warn_api_abnormal('{"resultCode":7,"msg":"x"}', "Test api", "data", {"resultCode": 7, "msg": "x"})
    assert "7" in mixed.msgs[0] and "x" in mixed.msgs[0]


# ============================================================================
# 第二批：海外 / 带凭据平台
# ============================================================================
# 与第一批（国内平台）同口径：裸 json.loads → _loads_dict、深层链式索引 → _dig 系列、
# 结构异常时经 _warn_api_abnormal 落「区分性告警」，成功路径逐字不变；四类样本与
# 「离线可证 / 需真机复核」的边界口径见文件头，此处只列本批差异。
# 本批特有约束：popkontv / sooplive / winktv / pandatv / flextv / acfun 的响应里带
# AID / visitor_st / hls_authentication_key 等**票据值**，加固后的日志只允许出现接口的
# code/message——故涉及票据的用例额外断言「日志里不含桩票据串」。
#
# 为什么本批值得单独做一遍（而不是「国内批做过就够了」）：
#   1. 返回契约更杂——本批同时存在 dict 契约（bigo/pplive/picarto/六间房/流星/映客/look）、
#      str|None 契约（get_flextv_stream_url）、tuple 契约（get_sooplive_tk /
#      get_winktv_bj_info / _get_soop_stream_info_global / get_popkontv_stream_data）与
#      list 响应（twitch GQL，见上方上限注释）。每种契约的「离线」长得都不一样，
#      用一句 `assert result["is_live"] is False` 通吃必然对某几类假绿。
#   2. 这些平台大多带凭据/登录态，「解析崩了」会被上层当成「未开播」反复重试，
#      既烧代理预算又永远等不到真开播——所以区分性告警的运维价值比国内平台更高。
#   3. 桩票据值同时用于验证「加固没有把 token 顺手写进日志」（AGENTS 凭据红线）。
#
# 四类样本同第一批：WAF_HTML（HTTP 200 + 合法 HTML，风控拦截页）、合法 JSON 但缺期望对象（信封
# code/msg 必须原样落日志）、截断 JSON（CDN 半截响应 / 页面尺寸截断的内联 JSON）、正常载荷（返回结构
# 与迁移前逐字相等且**零告警**）；另各配一条 silent_*「文档化离线形态必须静默」的用例。
#
# 需真机复核（本批**正常**载荷的字段名与层级，沿用迁移前索引路径逐字照抄、刻意不改；真机若发现字段
# 漂移会表现为「房间不存在」告警而不是崩溃）：bigo data.hls_src、SOOP data.isStream、
# PandaTV/WinkTV PlayList.hls[0].url、PopkonTV props.pageProps.mcData.data.*、Faceit payload[0].platform。
# 另需真机复核：SOOP 的网关 code 语义（-3001/-3002/-3004/-6001 走既有分支，本批只保证「无 code 时不再
# 静默」）、LiveMe 的字符串 "0" 在播语义、来秀的 playStatus==0 反向语义——三处都刻意保留原比较写法未动。
OVERSEAS_MIGRATED_FUNCTIONS = (
    "get_bigo_stream_url",
    "get_sooplive_cdn_url",
    "get_sooplive_tk",
    "_get_soop_channel_info_global",
    "_get_soop_stream_info_global",
    "get_sooplive_stream_data",
    "get_pandatv_stream_data",
    "get_winktv_bj_info",
    "get_winktv_stream_data",
    "get_flextv_stream_url",
    "get_flextv_stream_data",
    "get_looklive_stream_url",
    "get_popkontv_stream_data",
    "get_popkontv_stream_url",
    "get_twitcasting_stream_url",
    "get_liveme_stream_url",
    "get_huajiao_sn",
    "get_huajiao_user_info",
    "get_huajiao_stream_url_app",
    "get_liuxing_stream_url",
    "get_acfun_sign_params",
    "get_yingke_stream_url",
    "get_haixiu_stream_url",
    "get_langlive_stream_url",
    "get_pplive_stream_url",
    "get_6room_stream_url",
    "get_youtube_stream_url",
    "get_faceit_stream_data",
    "get_lianjie_stream_url",
    "get_laixiu_stream_url",
    "get_picarto_stream_url",
)

# 桩票据值：断言「任何日志行都不得包含它」，防止加固时把 token 顺手写进告警
FAKE_AID = "AID-super-secret-token"
FAKE_ST = "visitor-st-super-secret"


def _assert_no_token(logger: types.SimpleNamespace, *secrets: str) -> None:
    for secret in secrets:
        assert not any(secret in m for m in logger.msgs), f"票据值泄进日志: {logger.msgs}"


def test_overseas_migrated_functions_have_no_bare_json_loads() -> None:
    # 逐函数棘轮（第二批）：31 个海外/带凭据函数体内零裸 json.loads。
    # 与第一批共用扫描器但名单独立——两批各自回退各自变红。
    # get_twitchtv_room_info 刻意不在名单内：GQL 批量响应是 list、_loads_dict 不适用（豁免说明见文件头 BARE_JSON_LOADS_CEILING）。
    src = (ROOT / "src" / "spider.py").read_text(encoding="utf-8-sig")
    tree = ast.parse(src)
    offenders: list[str] = []
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name in OVERSEAS_MIGRATED_FUNCTIONS:
            found.add(node.name)
            hits = [call.lineno for call in _json_loads_calls(node)]
            if hits:
                offenders.append(f"{node.name}:{hits}")
    missing = [name for name in OVERSEAS_MIGRATED_FUNCTIONS if name not in found]
    assert not missing, f"用例与被测函数已失配（函数被改名/删除）: {missing}"
    assert not offenders, "以下函数仍含裸 json.loads（应走 _loads_dict + _dig）: " + ", ".join(offenders)


class TestBigoHardening(_GuardCase):
    # bigo 游客接口：nick_name/alive 在 data 下两级，裸解析时「房间不存在」与风控页同为静默离线。
    URL = "https://www.bigo.tv/en/500123456"
    _OK = (
        '{"asmId":1,"data":{"nick_name":"Bigo主播","alive":1,"roomTopic":"晚间电台",'
        '"hls_src":"https://bigocdn/live/a.m3u8"}}'
    )
    abnormal = [
        (WAF_HTML, "Bigo getInternalStudioInfo", None),
        ('{"message":"studio not found"}', "Bigo getInternalStudioInfo", "studio not found"),
        ('{"data": {"nick_name": "x", "al', "Bigo getInternalStudioInfo", None),
        # 已判开播却无 hls_src：同样必须留线索，不得伪装成「未开播」
        ('{"data":{"nick_name":"Bigo主播","alive":1,"roomTopic":"t"}}', "Bigo getInternalStudioInfo", None),
    ]
    expected = {
        "anchor_name": "Bigo主播",
        "is_live": True,
        "title": "晚间电台",
        "m3u8_url": "https://bigocdn/live/a.m3u8",
        "record_url": "https://bigocdn/live/a.m3u8",
    }
    silent_body = '{"asmId":1,"data":{"nick_name":"Bigo主播","alive":0,"roomTopic":""}}'
    silent_expected = {"anchor_name": "Bigo主播", "is_live": False}

    def payloads(self, body: str | None) -> dict[str, Any]:
        return {"getInternalStudioInfo": body if body is not None else self._OK}

    async def call(self) -> Any:
        return await sp.get_bigo_stream_url(self.URL)


class TestSoopliveCdnHardening(_GuardCase):
    # SOOP CDN 分配接口返回**原始 json** 给调用方（本层不判开播），故离线判据是「不含 view_url」；
    # 加固点在「解析不出对象时留线索」，而不是静默回 {}。
    _OK = '{"result":"01","server_url":"","view_url":"http://soopcdn/live/master.m3u8"}'
    abnormal = [
        (WAF_HTML, "SOOP broad_stream_assign", None),
        ('{"result":"99","msg":"broad not found"}', "SOOP broad_stream_assign", "broad not found"),
        ('{"result": "01", "view_url": "http://a', "SOOP broad_stream_assign", None),
    ]
    expected = {"result": "01", "server_url": "", "view_url": "http://soopcdn/live/master.m3u8"}

    def payloads(self, body: str | None) -> dict[str, Any]:
        return {"broad_stream_assign": body if body is not None else self._OK}

    def check_offline(self, result: Any, case: str) -> None:
        assert isinstance(result, dict), f"应返回 dict，实际 {result!r} ({case})"
        assert not cast("dict[str, object]", result).get("view_url"), f"异常响应竟带出 view_url: {result}"

    async def call(self) -> Any:
        # 传真实形态的 AuthTicket cookie 串：加固若把 cookies 拼进日志即被本类的票据断言抓到
        return await sp.get_sooplive_cdn_url("249469582", cookies="AuthTicket=x")

    async def test_cookie_never_logged(self) -> None:
        # AGENTS 凭据红线：登录态 cookie 的值（含 AuthTicket）任何级别日志都不得带出，
        # 归因只允许出现接口自身的 code/msg。
        logger = _fake_logger()
        with (
            patch.object(sp, "async_req", new=_fake_req({}, default=WAF_HTML)),
            patch.object(sp, "logger", logger),
        ):
            await sp.get_sooplive_cdn_url("249469582", cookies="AuthTicket=secret-cookie-value")
        _assert_no_token(logger, "secret-cookie-value")
        _assert_clue(logger, "SOOP broad_stream_assign", "soop cdn cookie")


class TestSoopliveTkHardening(_GuardCase):
    # SOOP 票据接口返回 str / 二元组（_or_none 装饰）：离线契约是 None，不是 dict。
    URL = "https://play.sooplive.co.kr/oul282/249469582"
    _OK = '{"result":"01","status":200,"CHANNEL":{"AID":"' + FAKE_AID + '"}}'
    _OK_INFO = '{"result":"01","CHANNEL":{"BJNICK":"SOOP主播","BJID":"oul282","BNO":"249469582"}}'
    abnormal = [
        (WAF_HTML, "SOOP player_live_api", None),
        ('{"result":"02","msg":"invalid room"}', "SOOP player_live_api", "invalid room"),
        ('{"CHANNEL": {"AID": ', "SOOP player_live_api", None),
    ]
    expected = FAKE_AID

    def check_offline(self, result: Any, case: str) -> None:
        assert result is None, f"异常票据响应应回 None，实际 {result!r} ({case})"

    def payloads(self, body: str | None) -> dict[str, Any]:
        return {"player_live_api": body if body is not None else self._OK}

    async def call(self) -> Any:
        return await sp.get_sooplive_tk(self.URL, rtype="aid")

    async def test_info_mode_success_path_unchanged(self) -> None:
        # 昵称复合串与 BNO（线路号）拼法不得变。
        logger = _fake_logger()
        with (
            patch.object(sp, "async_req", new=_fake_req({"player_live_api": self._OK_INFO})),
            patch.object(sp, "logger", logger),
        ):
            result = await sp.get_sooplive_tk(self.URL, rtype="info")
        assert result == ("SOOP主播-oul282", "249469582")
        assert logger.msgs == []

    async def test_info_mode_numeric_bno_survives(self) -> None:
        # BNO 在真实响应里可能是**数字**：迁移时刻意用 _dig + cast 而非 _dig_str
        # （后者会把 int 变成空串 → 线路号丢失 → 拿不到 CDN 地址）。
        logger = _fake_logger()
        body = '{"result":"01","CHANNEL":{"BJNICK":"SOOP主播","BJID":"oul282","BNO":249469582}}'
        with (
            patch.object(sp, "async_req", new=_fake_req({"player_live_api": body})),
            patch.object(sp, "logger", logger),
        ):
            result = await sp.get_sooplive_tk(self.URL, rtype="info")
        assert result == ("SOOP主播-oul282", 249469582), "BNO 被 _dig_str 吃掉成空串 → 线路号丢失"
        assert logger.msgs == []

    async def test_token_never_logged(self) -> None:
        logger = _fake_logger()
        with (
            patch.object(sp, "async_req", new=_fake_req({"player_live_api": '{"result":"02"}'}, default=WAF_HTML)),
            patch.object(sp, "logger", logger),
        ):
            await sp.get_sooplive_tk(self.URL, rtype="aid")
        # 归因只允许带接口 code/message，票据值绝不入日志
        _assert_no_token(logger, FAKE_AID)
        _assert_clue(logger, "SOOP player_live_api", "soop tk")


class TestSoopStreamInfoGlobalHardening(_GuardCase):
    # 内部通用方法（无装饰器）：返回 (status, title) 二元组且调用点直接解包，
    # 因此结构异常必须回 (False, "") 而不是 None——回 None 会抛 TypeError 并丢掉昵称。
    _OK = '{"code":200,"data":{"isStream":true,"title":"SOOP标题"}}'
    abnormal = [
        (WAF_HTML, "SOOP stream/info", None),
        ('{"code":404,"message":"channel not found"}', "SOOP stream/info", "channel not found"),
        ('{"data": {"isStream": tr', "SOOP stream/info", None),
    ]
    expected = (True, "SOOP标题")
    silent_body = '{"code":200,"data":{"isStream":false,"title":"回放间"}}'
    silent_expected = (False, "回放间")

    def check_offline(self, result: Any, case: str) -> None:
        assert result == (False, ""), f"异常响应应回未开播二元组，实际 {result!r} ({case})"

    async def test_documented_offline_stays_silent(self) -> None:
        # 本平台的离线契约是「(False, 标题)」而不是 (False, "")——标题在房间存在时总带得回；零告警判据同基类。
        logger = _fake_logger()
        with (
            patch.object(sp, "async_req", new=_fake_req(self.payloads(self.silent_body))),
            patch.object(sp, "logger", logger),
        ):
            result = await self.call()
        assert result == self.silent_expected
        assert logger.msgs == [], f"正常离线形态被刷了告警（噪声即失效日志）: {logger.msgs}"

    def payloads(self, body: str | None) -> dict[str, Any]:
        return {"v2/stream/info": body if body is not None else self._OK}

    async def call(self) -> Any:
        return await sp._get_soop_stream_info_global("oul282")


class TestSoopChannelInfoGlobalHardening(_GuardCase):
    # 同族的频道信息接口：昵称复合串取不到时回空串（调用点 `anchor_name or ""` 已容忍）。
    _OK = '{"code":200,"data":{"streamerChannelInfo":{"nickname":"SOOP主播","channelId":"oul282"}}}'
    abnormal = [
        (WAF_HTML, "SOOP channel/info", None),
        ('{"code":404,"message":"no channel"}', "SOOP channel/info", "no channel"),
        ('{"data": {"streamerChannelInfo": {"nickname"', "SOOP channel/info", None),
    ]
    expected = "SOOP主播-oul282"

    def check_offline(self, result: Any, case: str) -> None:
        assert result == "", f"异常响应应回空昵称，实际 {result!r} ({case})"

    def payloads(self, body: str | None) -> dict[str, Any]:
        return {"v2/channel/info": body if body is not None else self._OK}

    async def call(self) -> Any:
        return await sp._get_soop_channel_info_global("oul282")


class TestPandatvHardening(_GuardCase):
    # PandaTV：bjInfo 缺失沿用「抛 RuntimeError → 装饰器 → {is_live:False}」既有契约
    # （tests/test_spider_platform.py 已锁定），加固只负责在抛错前留下区分性线索。
    URL = "https://www.pandalive.co.kr/pandauser"
    _BJ = '{"bjInfo":{"id":"pandauser","nick":"Panda主播"},"media":{"title":"在播"}}'
    _PLAY = '{"PlayList":{"hls":[{"label":"ALL","url":"https://pandancdn/live/a.m3u8"}]}}'
    _M3U8 = (
        "#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=4000\nhttps://pandancdn/live/a_720.m3u8\n"
        "#EXT-X-STREAM-INF:BANDWIDTH=8000\nhttps://pandancdn/live/a_1080.m3u8\n"
    )
    abnormal = [
        (WAF_HTML, "PandaTV member/bj", None),
        ('{"message":"User not found"}', "PandaTV member/bj", "User not found"),
        ('{"bjInfo": {"id": ', "PandaTV member/bj", None),
    ]
    expected = {
        "anchor_name": "Panda主播-pandauser",
        "is_live": True,
        "m3u8_url": "https://pandancdn/live/a.m3u8",
        # 带宽降序是上层选画质前提（get_play_url_list 真实执行、未打桩）
        "play_url_list": ["https://pandancdn/live/a_1080.m3u8", "https://pandancdn/live/a_720.m3u8"],
    }
    silent_body = '{"bjInfo":{"id":"pandauser","nick":"Panda主播"}}'
    silent_expected = {"anchor_name": "Panda主播-pandauser", "is_live": False}

    def payloads(self, body: str | None) -> dict[str, Any]:
        # 首个失败点打在 member/bj 上；live/play 与 m3u8 保持正常桩。m3u8 也走 async_req
        # （get_play_url_list 是真实实现、未打桩）——选档排序被改坏时 expected 的带宽降序断言立刻变红。
        return {
            "member/bj": body if body is not None else self._BJ,
            "live/play": self._PLAY,
            "a.m3u8": self._M3U8,
        }

    async def call(self) -> Any:
        return await sp.get_pandatv_stream_data(self.URL)

    async def test_play_response_missing_hls_leaves_clue(self) -> None:
        # 已判在播（media 在）却取不到 PlayList.hls[0].url：改版/风控降级，须与「未开播」区分
        logger = _fake_logger()
        with (
            patch.object(
                sp,
                "async_req",
                new=_fake_req({"member/bj": self._BJ, "live/play": '{"PlayList":{"hls":[]}}'}, default="{}"),
            ),
            patch.object(sp, "logger", logger),
        ):
            result = await sp.get_pandatv_stream_data(self.URL)
        _assert_offline(result, "pandatv no hls")
        assert result["anchor_name"] == "Panda主播-pandauser"
        _assert_clue(logger, "PandaTV live/play", "pandatv no hls")


class TestWinktvBjInfoHardening(_GuardCase):
    # WinkTV 主播信息（_or_none，返回二元组）：与 PandaTV 同族接口、同一加固口径。
    URL = "https://www.winktv.co.kr/winkuser"
    _OK = '{"bjInfo":{"id":"winkuser","nick":"Wink主播"},"media":{"title":"在播"}}'
    abnormal = [
        (WAF_HTML, "WinkTV member/bj", None),
        ('{"message":"User not found"}', "WinkTV member/bj", "User not found"),
        ('{"bjInfo": {"id": ', "WinkTV member/bj", None),
    ]
    expected = ("Wink主播-winkuser", True)
    silent_body = '{"bjInfo":{"id":"winkuser","nick":"Wink主播"}}'
    silent_expected = ("Wink主播-winkuser", False)

    def check_offline(self, result: Any, case: str) -> None:
        assert result is None, f"异常响应应回 None（二元组契约），实际 {result!r} ({case})"

    async def test_documented_offline_stays_silent(self) -> None:
        # 「主播页存在、但无 media」= 未开播，契约是 ("昵称-id", False) 而非 None，
        # 故覆盖基类的 _assert_offline 口径；硬判据不变：正常离线形态零告警。
        logger = _fake_logger()
        with (
            patch.object(sp, "async_req", new=_fake_req(self.payloads(self.silent_body))),
            patch.object(sp, "logger", logger),
        ):
            result = await self.call()
        assert result == self.silent_expected
        assert logger.msgs == [], f"正常离线形态被刷了告警（噪声即失效日志）: {logger.msgs}"

    def payloads(self, body: str | None) -> dict[str, Any]:
        return {"member/bj": body if body is not None else self._OK}

    async def call(self) -> Any:
        return await sp.get_winktv_bj_info(self.URL)


class TestLookliveHardening(_GuardCase):
    # 网易 look：weapi 加密请求真实执行（非桩），加固点在 room/get/v3 的四级链式索引。
    URL = "https://look.163.com/live?id=32108888"
    _OK = (
        '{"code":200,"data":{"anchor":{"nickName":"Look主播","avatar":""},"liveStatus":1,'
        '"roomInfo":{"liveType":2,"title":"深夜电台","liveUrl":{"httpPullUrl":"http://lookcdn/a.flv",'
        '"hlsPullUrl":"http://lookcdn/a.m3u8"}}}}'
    )
    abnormal = [
        (WAF_HTML, "Look 房间接口 room/get/v3", None),
        ('{"code":404,"message":"room not exist"}', "Look 房间接口 room/get/v3", "room not exist"),
        ('{"data": {"anchor": {"nickName"', "Look 房间接口 room/get/v3", None),
        # 已判开播但 liveUrl 缺地址：按无源返回并留线索
        (
            '{"code":200,"data":{"anchor":{"nickName":"Look主播"},"liveStatus":1,'
            '"roomInfo":{"liveType":2,"title":"t","liveUrl":{}}}}',
            "Look 房间接口 room/get/v3",
            None,
        ),
    ]
    expected = {
        "anchor_name": "Look主播",
        "is_live": True,
        "title": "深夜电台",
        "flv_url": "http://lookcdn/a.flv",
        "m3u8_url": "http://lookcdn/a.m3u8",
        "record_url": "http://lookcdn/a.m3u8",
    }
    silent_body = '{"code":200,"data":{"anchor":{"nickName":"Look主播"},"liveStatus":0,"roomInfo":{}}}'
    silent_expected = {"anchor_name": "Look主播", "is_live": False}

    def payloads(self, body: str | None) -> dict[str, Any]:
        return {"room/get/v3": body if body is not None else self._OK}

    async def call(self) -> Any:
        return await sp.get_looklive_stream_url(self.URL)

    async def test_flv_only_room_is_live_with_record_url(self) -> None:
        # 只下发 FLV（无 HLS）的房间必须判开播并带 record_url（同微博侧的单路形态回归锁）。
        body = (
            '{"code":200,"data":{"anchor":{"nickName":"Look主播"},"liveStatus":1,'
            '"roomInfo":{"liveType":2,"title":"深夜电台","liveUrl":{"httpPullUrl":"http://lookcdn/a.flv"}}}}'
        )
        logger = _fake_logger()
        with patch.object(sp, "async_req", new=_fake_req({"room/get/v3": body})), patch.object(sp, "logger", logger):
            result = await sp.get_looklive_stream_url(self.URL)
        body_d = cast("dict[str, object]", result)
        assert body_d.get("is_live") is True, f"纯 FLV 房间被误判未开播: {result}"
        assert body_d.get("record_url") == "http://lookcdn/a.flv", result
        assert logger.msgs == [], f"正常单路开播不应告警: {logger.msgs}"

    async def test_hls_only_room_is_live(self) -> None:
        # 只下发 HLS 的房间必须判开播（同上一条单路形态回归锁）。
        body = (
            '{"code":200,"data":{"anchor":{"nickName":"Look主播"},"liveStatus":1,'
            '"roomInfo":{"liveType":2,"title":"深夜电台","liveUrl":{"hlsPullUrl":"http://lookcdn/a.m3u8"}}}}'
        )
        logger = _fake_logger()
        with patch.object(sp, "async_req", new=_fake_req({"room/get/v3": body})), patch.object(sp, "logger", logger):
            result = await sp.get_looklive_stream_url(self.URL)
        body_d = cast("dict[str, object]", result)
        assert body_d.get("is_live") is True, f"纯 HLS 房间被误判未开播: {result}"
        assert logger.msgs == [], f"正常单路开播不应告警: {logger.msgs}"


class TestLiuxingHardening(_GuardCase):
    # 流星/畅聊/音播共用 live.ashx；idx / liveId1 在真实响应里是**数字**，
    # 迁移时刻意用 _dig 而非 _dig_str（后者会把 int 变成空串、拼出坏地址）。
    URL = "https://wap.7u66.com/198189"
    _OK = '{"result":1,"data":{"roomInfo":{"nickname":"流星主播","live_stat":1,"idx":198189,"liveId1":8888}}}'
    abnormal = [
        (WAF_HTML, "流星 live.ashx", None),
        ('{"result":0,"msg":"room not exist"}', "流星 live.ashx", "room not exist"),
        ('{"data": {"roomInfo": {"nickname": ', "流星 live.ashx", None),
        # 已判开播却缺 liveId1：按无源返回并留线索
        ('{"data":{"roomInfo":{"nickname":"流星主播","live_stat":1,"idx":198189}}}', "流星 live.ashx", None),
    ]
    expected = {
        "anchor_name": "流星主播",
        "is_live": True,
        "flv_url": "https://txpull1.5see.com/live/198189/8888.flv",
        "record_url": "https://txpull1.5see.com/live/198189/8888.flv",
    }
    silent_body = '{"data":{"roomInfo":{"nickname":"流星主播","live_stat":0}}}'
    silent_expected = {"anchor_name": "流星主播", "is_live": False}

    def payloads(self, body: str | None) -> dict[str, Any]:
        return {"live.ashx": body if body is not None else self._OK}

    async def call(self) -> Any:
        return await sp.get_liuxing_stream_url(self.URL)


class TestYingkeHardening(_GuardCase):
    # 映客：live_addr 是数组，原 `["live_addr"][0]` 在空数组时 IndexError → 装饰器 → 假离线。
    URL = "https://www.inke.cn/live.html?uid=abc&id=123"
    _OK = (
        '{"live_id":"123","data":{"media_info":{"nick":"映客主播"},"status":1,'
        '"live_addr":[{"hls_stream_addr":"https://inkecdn/a.m3u8","stream_addr":"https://inkecdn/a.flv"}]}}'
    )
    abnormal = [
        (WAF_HTML, "映客 live_share_pc", None),
        ('{"code":"1001","message":"live not exist"}', "映客 live_share_pc", "live not exist"),
        ('{"data": {"media_info": ', "映客 live_share_pc", None),
        # 已判开播但 live_addr 为空数组：按无源返回并留线索
        ('{"data":{"media_info":{"nick":"映客主播"},"status":1,"live_addr":[]}}', "映客 live_share_pc", None),
    ]
    expected = {
        "anchor_name": "映客主播",
        "is_live": True,
        "m3u8_url": "https://inkecdn/a.m3u8",
        "flv_url": "https://inkecdn/a.flv",
        "record_url": "https://inkecdn/a.m3u8",
    }
    silent_body = '{"data":{"media_info":{"nick":"映客主播"},"status":0,"live_addr":[]}}'
    silent_expected = {"anchor_name": "映客主播", "is_live": False}

    def payloads(self, body: str | None) -> dict[str, Any]:
        return {"live_share_pc": body if body is not None else self._OK}

    async def call(self) -> Any:
        return await sp.get_yingke_stream_url(self.URL)


class TestPpliveHardening(_GuardCase):
    # 飘飘：living 是布尔总闸，pullUrl 只在为真时才读；原实现 `["data"]["name"]` 在
    # 风控返回不含 data 的信封时直接 KeyError。加固后离线契约仍带 anchor_name（若接口给了）。
    URL = "https://m.pp.weimipopo.com/live/preview?anchorUid=abc123"
    _OK = '{"code":"0","data":{"name":"飘飘主播","living":true,"pullUrl":"https://ppcdn/live/a.m3u8"}}'
    abnormal = [
        (WAF_HTML, "飘飘 live/preview", None),
        ('{"code":"404","message":"anchor not found"}', "飘飘 live/preview", "anchor not found"),
        ('{"data": {"name": ', "飘飘 live/preview", None),
    ]
    expected = {
        "anchor_name": "飘飘主播",
        "is_live": True,
        "m3u8_url": "https://ppcdn/live/a.m3u8",
        "record_url": "https://ppcdn/live/a.m3u8",
    }
    silent_body = '{"code":"0","data":{"name":"飘飘主播","living":false,"pullUrl":""}}'
    silent_expected = {"anchor_name": "飘飘主播", "is_live": False}

    def payloads(self, body: str | None) -> dict[str, Any]:
        return {"live/preview": body if body is not None else self._OK}

    async def call(self) -> Any:
        return await sp.get_pplive_stream_url(self.URL)


class TestPicartoHardening(_GuardCase):
    # Picarto 用 channel.online 布尔直接驱动 is_live：加固不得改写这条语义
    # （result["is_live"] = channel.online，而非「取到地址才算开播」）。
    # 且 m3u8 地址由「固定 edge host + 昵称」拼出、不来自接口，故成功用例连地址一起锁死。
    URL = "https://picarto.tv/PicartoArtist"
    _OK = '{"channel":{"name":"PicartoArtist","online":true,"title":"Drawing"}}'
    abnormal = [
        (WAF_HTML, "Picarto channel detail", None),
        ('{"errors":[{"message":"Channel not found"}],"status":404}', "Picarto channel detail", None),
        ('{"channel": {"name": ', "Picarto channel detail", None),
    ]
    expected = {
        "anchor_name": "PicartoArtist",
        # 流地址由「固定 edge host + 昵称」拼出、不来自接口——形态必须逐字不变
        "is_live": True,
        "title": "Drawing",
        "m3u8_url": "https://1-edge1-us-newyork.picarto.tv/stream/hls/golive+PicartoArtist/index.m3u8",
        "record_url": "https://1-edge1-us-newyork.picarto.tv/stream/hls/golive+PicartoArtist/index.m3u8",
    }
    silent_body = '{"channel":{"name":"PicartoArtist","online":false,"title":""}}'
    silent_expected = {"anchor_name": "PicartoArtist", "is_live": False}

    def payloads(self, body: str | None) -> dict[str, Any]:
        return {"api/channel/detail": body if body is not None else self._OK}

    async def call(self) -> Any:
        return await sp.get_picarto_stream_url(self.URL)


class TestSixRoomHardening(_GuardCase):
    # 六间房：flvtitle 为空串是「房间存在但未开播」的既有静默形态；liveinfo 整体缺失才是改版。
    _PAGE = "rid: '56789',\n  roomid"
    _OK = '{"content":{"liveinfo":{"flvtitle":"live_56789"},"roominfo":{"alias":"六间房主播"}}}'
    abnormal = [
        (WAF_HTML, "六间房 coop-mobile-inroom", None),
        ('{"code":-1,"message":"room is private"}', "六间房 coop-mobile-inroom", "room is private"),
        ('{"content": {"liveinfo": {"flvtitle"', "六间房 coop-mobile-inroom", None),
    ]
    expected = {
        "anchor_name": "六间房主播",
        "is_live": True,
        "flv_url": "https://wlive.6rooms.com/httpflv/live_56789.flv",
        "record_url": "https://wlive.6rooms.com/httpflv/live_56789.flv",
    }
    silent_body = '{"content":{"liveinfo":{"flvtitle":""},"roominfo":{"alias":"六间房主播"}}}'
    silent_expected = {"anchor_name": "六间房主播", "is_live": False}

    def payloads(self, body: str | None) -> dict[str, Any]:
        # 第一个请求是房间页（正则抠 rid），第二个才是本批加固的 JSON 接口
        return {"coop-mobile-inroom": body if body is not None else self._OK, "v.6.cn/198189": self._PAGE}

    async def call(self) -> Any:
        return await sp.get_6room_stream_url("https://v.6.cn/198189")


class TestFaceitHardening(_GuardCase):
    # Faceit 两段接口：nicknames → streamings；payload 为空数组 = 该用户没开播（既有静默形态）。
    URL = "https://www.faceit.com/zh/players/testuser/stream"
    _USER = '{"payload":{"id":"user123","nickname":"testuser"}}'
    _STREAM = '{"payload":[{"userNickname":"Faceit主播","platformId":"twitchchan","platform":"youtube"}]}'
    abnormal = [
        (WAF_HTML, "Faceit users/nicknames", None),
        ('{"statusCode":404,"message":"user not found"}', "Faceit users/nicknames", "user not found"),
        ('{"payload": {"id": ', "Faceit users/nicknames", None),
    ]
    expected = {"anchor_name": "Faceit主播", "is_live": False}
    # 无 silent 用例：本平台的「未开播」形态（payload 空数组）落在第二段接口上，
    # 由 test_second_api_* 单独锁定（首段拿到 {"payload":[]} 属改版而非未开播）。

    def payloads(self, body: str | None) -> dict[str, Any]:
        return {
            "api/users/v1/nicknames": body if body is not None else self._USER,
            "api/stream/v1/streamings": self._STREAM,
        }

    async def call(self) -> Any:
        return await sp.get_faceit_stream_data(self.URL)

    async def test_second_api_missing_payload_leaves_clue(self) -> None:
        logger = _fake_logger()
        with (
            patch.object(
                sp,
                "async_req",
                new=_fake_req({"api/users/v1/nicknames": self._USER}, default='{"code":500,"msg":"boom"}'),
            ),
            patch.object(sp, "logger", logger),
        ):
            result = await sp.get_faceit_stream_data(self.URL)
        _assert_offline(result, "faceit streamings")
        _assert_clue(logger, "Faceit stream/streamings", "faceit streamings")


class TestFlextvStreamUrlHardening(_GuardCase):
    # TTingLive 取流接口：返回 str|None，调用方按 None 判未开播。
    # 加固判据：sources **整键缺失**（壳页/改版）才告警；{"sources": []} 是常态离线，必须静默。
    URL = "https://www.ttinglive.com/flexuser/live"
    _OK = '{"channelId":"flexuser","sources":[{"name":"HD","url":"https://flxcdn/live/a.m3u8"}]}'
    abnormal = [
        (WAF_HTML, "TTingLive channels/stream", None),
        ('{"status":404,"message":"channel not found"}', "TTingLive channels/stream", "channel not found"),
        ('{"sources": [{"url"', "TTingLive channels/stream", None),
    ]
    expected = "https://flxcdn/live/a.m3u8"
    silent_body = '{"channelId":"flexuser","sources":[]}'

    def check_offline(self, result: Any, case: str) -> None:
        assert not result, f"异常响应应回 None（无源），实际 {result!r} ({case})"

    async def test_documented_offline_stays_silent(self) -> None:
        # 离线契约是 None，不是 dict —— 覆盖基类的 _assert_offline 口径
        logger = _fake_logger()
        with (
            patch.object(sp, "async_req", new=_fake_req(self.payloads(self.silent_body))),
            patch.object(sp, "logger", logger),
        ):
            result = await self.call()
        assert result is None
        assert logger.msgs == [], f"正常离线形态被刷了告警（噪声即失效日志）: {logger.msgs}"

    def payloads(self, body: str | None) -> dict[str, Any]:
        return {"api/channels": body if body is not None else self._OK}

    async def call(self) -> Any:
        return await sp.get_flextv_stream_url(self.URL)


class TestAcfunSignParamsHardening(_GuardCase):
    # AcFun 游客三件套（visitor_st 是签名票据）：返回三元组、_or_none 装饰 → 离线契约是 None。
    # 本类的主要价值是「票据缺失留线索」+「票据值绝不入日志」两条。
    _OK = '{"userId":12345,"acfun.api.visitor_st":"' + FAKE_ST + '","result":1}'
    abnormal = [
        (WAF_HTML, "AcFun visitor/login", None),
        ('{"resultCode":11000,"message":"visitor rejected"}', "AcFun visitor/login", "11000"),
        ('{"userId": 12345, "acfun.api.visitor_st"', "AcFun visitor/login", None),
    ]

    def check_offline(self, result: Any, case: str) -> None:
        assert result is None, f"异常响应应回 None（三元组契约），实际 {result!r} ({case})"

    def payloads(self, body: str | None) -> dict[str, Any]:
        return {"visitor/login": body if body is not None else self._OK}

    async def call(self) -> Any:
        return await sp.get_acfun_sign_params()

    async def test_success_path_unchanged(self) -> None:
        # 下标契约（0=userId 数字原值、2=visitor_st）被 tests/test_spider_platform.py 锁定，
        # 迁移刻意用 _dig 保留 userId 的 int 类型，不得变成 "12345"。
        logger = _fake_logger()
        with (
            patch.object(sp, "async_req", new=_fake_req(self.payloads(None))),
            patch.object(sp, "logger", logger),
        ):
            result = await sp.get_acfun_sign_params()
        assert result[0] == 12345 and isinstance(result[0], int)
        assert result[2] == FAKE_ST
        assert str(result[1]).startswith("web_")
        assert logger.msgs == []

    async def test_token_never_logged(self) -> None:
        logger = _fake_logger()
        with (
            patch.object(sp, "async_req", new=_fake_req({"visitor/login": '{"resultCode":1}'})),
            patch.object(sp, "logger", logger),
        ):
            result = await sp.get_acfun_sign_params()
        assert result is None
        _assert_no_token(logger, FAKE_ST)
        _assert_clue(logger, "AcFun visitor/login", "acfun st")


class TestPopkontvSearchHardening(_GuardCase):
    # PopkonTV 两段（search/all 判房间 + live/view 页内联 JSON 判开播）：返回二元组、_or_none。
    URL = "https://www.popkontv.com/live/view?castId=cast1&partnerCode=P-00001"
    _SEARCH = '{"data":{"broadCastList":[{"mcSignId":"cast1","nickName":"Popkon主播","mcPartnerCode":"P-00002"}]}}'
    _VIEW = (
        '<script id="__NEXT_DATA__" type="application/json">'
        + json.dumps(
            {
                "props": {
                    "pageProps": {
                        "mcData": {
                            "data": {
                                "mc_isPrivate": 0,
                                "mc_castStartDate": "20260921",
                                "mc_signId": "cast1",
                                "castType": 1,
                            }
                        }
                    }
                }
            }
        )
        + "</script>"
    )
    abnormal = [
        (WAF_HTML, "PopkonTV search/all", None),
        ('{"message":"cast not found"}', "PopkonTV search/all", "cast not found"),
        ('{"data": {"broadCastList": [{"mcSignId"', "PopkonTV search/all", None),
    ]
    expected = ("Popkon主播-cast1", ["20260921", "P-00002", "cast1", 1, 0])

    def check_offline(self, result: Any, case: str) -> None:
        assert result is None, f"异常响应应回 None（二元组契约），实际 {result!r} ({case})"

    def payloads(self, body: str | None) -> dict[str, Any]:
        return {
            "search/all": body if body is not None else self._SEARCH,
            "live/view": self._VIEW,
        }

    async def call(self) -> Any:
        return await sp.get_popkontv_stream_data(self.URL)

    async def test_view_page_without_mcdata_stays_silent(self) -> None:
        # 搜索命中但房间页里无 mcData = 「主播存在、未开播」，既有语义是 (anchor_name, None) 且静默
        # （刻意不复用基类的 silent 用例：本函数的离线契约是二元组，不是 None）。
        view = (
            '<script id="__NEXT_DATA__" type="application/json">'
            + json.dumps({"props": {"pageProps": {"other": 1}}})
            + "</script>"
        )
        logger = _fake_logger()
        with (
            patch.object(sp, "async_req", new=_fake_req({"search/all": self._SEARCH, "live/view": view})),
            patch.object(sp, "logger", logger),
        ):
            result = await sp.get_popkontv_stream_data(self.URL)
        assert result is not None
        assert result[1] is None, f"未开播却带出了开播信息: {result}"
        assert logger.msgs == [], f"正常离线形态被刷了告警（噪声即失效日志）: {logger.msgs}"

    async def test_view_page_truncated_leaves_clue(self) -> None:
        # __NEXT_DATA__ 命中但内联 JSON 被截断：与「未开播」区分（原实现抛 JSONDecodeError）。
        # 必须保留 </script> 闭合，否则测的是「正则未命中」分支而不是解析分支。
        view = '<script id="__NEXT_DATA__" type="application/json">{"props": {"pageProps": {"mcData": ' "</script>"
        logger = _fake_logger()
        with (
            patch.object(sp, "async_req", new=_fake_req({"search/all": self._SEARCH, "live/view": view})),
            patch.object(sp, "logger", logger),
        ):
            result = await sp.get_popkontv_stream_data(self.URL)
        assert result is None, f"截断的开播页应回 None 交由上层判离线，实际 {result!r}"
        _assert_clue(logger, "PopkonTV live/view(__NEXT_DATA__)", "popkon view")


# ── SEV-N04：淘宝用响应 Set-Cookie 覆盖并持久化用户 Cookie ───────────


class TestSevN04TaobaoCookieMerge:
    # 归因判据（本工作区不做「改坏生产实现再跑用例」的变异验证，改用只有新逻辑能过的输入）：
    #   桩里的 new_cookie **只**含两张票据——这正是 src/async_http.py return_cookies 的真实形态
    #   （返回 response.cookies，不含请求侧 cookie）。未改成「合并」→ 第二轮请求头与写回值都不再含
    #   unb=1，第 ① 组断言变红；回写比较的仍是「响应票据串」而不是合并后的完整串 → 第 ② 条用例
    #   （票据未轮换须零重写）变红。
    # 只打桩传输层与配置读写边界（async_req / utils.read_ini_value / utils.update_config），
    # Cookie 解析、票据合并、签名与轮次控制一律走真实代码。
    TICKETS = {"_m_h5_tk": "f7e0d3a4b5c6d7e8f9a0b1c2d3e4f5a6_1777000000000", "_m_h5_tk_enc": "enc-1"}
    USER_COOKIE = "unb=1; _tb_token_=tok3n-value; cookie2=c00kie2"
    URL = "https://h5.m.taobao.com/taolive/video.html?id=a&liveId=500123"

    @staticmethod
    def _jsonp(ret_msg: str) -> str:
        # mtop 的 JSONP 信封；streamStatus 固定 "0"（未开播）即可走完整成功分支，无需再桩清单接口
        return (
            "mtopjsonp1("
            + json.dumps(
                {
                    "ret": [ret_msg],
                    "data": {
                        "broadCaster": {"accountName": "测试店铺"},
                        "streamStatus": "0",
                        "title": "T",
                        "liveUrlList": [],
                    },
                },
                ensure_ascii=False,
            )
            + ")"
        )

    @staticmethod
    async def _call(
        responses: list[tuple[str, dict[str, str]]], user_cookie: str, stored_cookie: str | None
    ) -> tuple[list[str], list[str], types.SimpleNamespace]:
        # 返回 (每次请求实际发出的 Cookie, 写回配置的值, 日志替身)
        sent_cookies: list[str] = []
        written: list[str] = []
        queue = list(responses)
        # 配置文件用「可读可写的状态」模拟：read_ini_value 每次真的重读文件，
        # 故刚写回的票据在下一轮必须先可见，否则轮次语义与生产不符。
        config_state = {"taobao_cookie": stored_cookie}

        async def fake_req(*args: object, **kwargs: object) -> Any:
            header = kwargs.get("headers")
            if isinstance(header, dict):
                sent_cookies.append(str(cast("dict[str, str]", header).get("Cookie", "")))
            assert queue, "async_req 桩响应已用尽（说明解析链路多发了请求）"
            return queue.pop(0)

        def fake_update_config(*args: object, **kwargs: object) -> None:
            # 生产调用为位置参 (file_path, section, key, new_value)
            written.append(str(args[3]))
            config_state["taobao_cookie"] = str(args[3])

        logger = _fake_logger()
        with (
            patch.object(sp, "async_req", new=fake_req),
            patch.object(sp, "logger", logger),
            patch.object(sp.utils, "read_ini_value", new=lambda *a, **k: config_state["taobao_cookie"]),
            patch.object(sp.utils, "update_config", new=fake_update_config),
        ):
            await sp.get_taobao_stream_url(TestSevN04TaobaoCookieMerge.URL, cookies=user_cookie)
        return sent_cookies, written, logger

    async def test_user_cookie_survives_ticket_refresh_and_writeback(self) -> None:
        # 第一轮 mtop 返回 token 过期（非空 ret 数组）→ 刷新票据 → 第二轮成功
        responses = [
            (self._jsonp("FAIL_SYS_TOKEN_EMPTY::令牌为空"), dict(self.TICKETS)),
            (self._jsonp("SUCCESS::调用成功"), dict(self.TICKETS)),
        ]
        sent_cookies, written, logger = await self._call(responses, self.USER_COOKIE, self.USER_COOKIE)

        # ① 第二轮请求头：票据已刷新（既有的过期重试语义完整保留）**且**用户登录态仍在（SEV-N04）
        assert len(sent_cookies) == 2, f"轮次数不符: {sent_cookies}"
        for key in ("unb", "_tb_token_", "cookie2"):
            assert f"{key}=" in sent_cookies[1], f"第二轮请求头丢了用户键 {key}: {sent_cookies[1]}"
        assert f"_m_h5_tk={self.TICKETS['_m_h5_tk']}" in sent_cookies[1]

        # ② 写回的是**合并后的完整串**，不是「只剩两个票据键」的响应串。
        # 轮 1 写回一次；轮 2 的票据与配置现值一致 → 合并串全等 → 不再重写，故总数恰 1
        # （旧实现比较的是响应票据串，每轮都判定为「有变化」→ 轮 2 照样重写整份 config.ini）。
        assert len(written) == 1, f"写回次数不符: {written}"
        assert written[0] != sp.utils.dict_to_cookie_str(self.TICKETS), "写回了响应票据串（旧失效形态）"
        assert "unb=1" in written[0] and "cookie2=c00kie2" in written[0], written[0]
        assert f"_m_h5_tk_enc={self.TICKETS['_m_h5_tk_enc']}" in written[0]

        # ③ 可观测且不泄值：成功回写须有一条 info，且任何日志行都不得出现 cookie / 票据值
        info_msgs = [str(call.args[0]) for call in logger.info.call_args_list if call.args]
        assert any("taobao_cookie" in m for m in info_msgs), f"缺少成功回写的 info 日志: {info_msgs}"
        secrets = (self.TICKETS["_m_h5_tk"], self.TICKETS["_m_h5_tk_enc"], "tok3n-value", "c00kie2")
        _assert_no_token(logger, *secrets)
        assert not any(secret in m for m in info_msgs for secret in secrets), f"cookie 值泄进 info 日志: {info_msgs}"

    async def test_unchanged_tickets_do_not_rewrite_config(self) -> None:
        # 归因用例：配置现值已含同一张票据 → 合并后与现值全等，不该再重写整份 config.ini。
        # [历史注] 旧实现拿「响应票据串」与「配置里的完整 cookie」比较，形态必然不同 → 条件恒真、
        # 每轮都重写并触发备份线程，「仅在值确实变化时才写」从未生效。
        stored = f"unb=1; _m_h5_tk={self.TICKETS['_m_h5_tk']}; _m_h5_tk_enc={self.TICKETS['_m_h5_tk_enc']}"
        _sent, written, _logger = await self._call(
            [(self._jsonp("SUCCESS::调用成功"), dict(self.TICKETS))], stored, stored
        )
        assert written == [], f"票据未轮换仍重写了配置: {written}"

    def test_cookie_str_to_dict_keeps_equals_in_values(self) -> None:
        # 票据 / base64 值常含「=」，只能按**首个**「=」切分；空段与无「=」残段丢弃，
        # 保证与 dict_to_cookie_str 往返时不会把解析不出来的内容写回配置文件。
        parsed = sp._cookie_str_to_dict("a=1; b=x==;  ; junk; c=")
        assert parsed == {"a": "1", "b": "x==", "c": ""}
        assert sp.utils.dict_to_cookie_str(parsed) == "a=1; b=x==; c="


# ── CODE_REVIEW_2026-10-27 4.1（M-13）：花椒写回判据 ──────────────
class TestHuajiaoSnWriteBackCriterion:
    # get_huajiao_sn 是零生产调用的死代码（活链路是 main.py 的 get_huajiao_stream_url →
    # get_huajiao_user_info / get_huajiao_stream_url_app），但它携带全仓唯一的
    # utils.replace_url(..., new="#" + url)——把用户房间加 `#` 注释掉且重启不恢复。
    # 判据必须是「响应可解析且字段确实为空」：WAF/风控壳页同样是「HTTP 200 + 有响应体但不含
    # var feed」，按旧判据一次风控命中即永久注释掉用户房间。
    #
    # 三条用例必须成对存在：只有「该写回时确实写回」的正向见证在，「不该写回时没写回」才不是
    # 「replace_url 桩压根没接上」的假绿（AGENTS「反对假绿」）。
    URL = "https://www.huajiao.com/l/123456"
    # 已解析出 feed 但缺 nickname：唯一仍应写回的形态（sn/uid 在位，证明页面是真实房间页）
    _PARSED_BUT_EMPTY = '<html>var feed = {"feed":{"sn":"sn-1"},"author":{"uid":"777"}};</html>'
    # var feed 命中但内容畸形：`.*?});` 会截到 `...{"uid":}` 这一段，_loads_dict 恒回 {} 而不抛
    _UNPARSABLE_FEED = '<html>var feed = {"feed":{"sn":"sn-1"},"author":{"uid":};</html>'

    async def _call(self, body: str) -> tuple[list[tuple[str, str]], types.SimpleNamespace]:
        written: list[tuple[str, str]] = []
        logger = _fake_logger()
        with (
            patch.object(sp, "async_req", new=_fake_req({"www.huajiao.com/l/": body}, default=body)),
            patch.object(sp, "logger", logger),
            patch.object(
                sp.utils,
                "replace_url",
                new=lambda *a, **k: written.append((str(k.get("old")), str(k.get("new")))),
            ),
        ):
            # 三个分支都抛 RuntimeError：本用例判的是**副作用**，不是返回值
            with pytest.raises(RuntimeError):
                await sp.get_huajiao_sn(self.URL)
        return written, logger

    async def test_waf_shell_page_does_not_comment_out_user_url(self) -> None:
        written, logger = await self._call(WAF_HTML)
        assert written == [], f"风控壳页被当成地址失效并改写了用户配置: {written}"
        assert any("未改动配置文件" in m for m in logger.msgs), f"缺少不写回的告警: {logger.msgs}"

    async def test_unparsable_feed_does_not_comment_out_user_url(self) -> None:
        # _loads_dict 恒不抛、只回 {}，漏掉「空 dict 即不可解析」这道闸时，畸形响应会顺着下面的
        # 字段判空走进 KeyError 写回分支——与风控壳页是同一类「无法确认却当成确认失效」。
        written, logger = await self._call(self._UNPARSABLE_FEED)
        assert written == [], f"畸形 feed 被当成地址失效并改写了用户配置: {written}"
        assert any("未改动配置文件" in m for m in logger.msgs), f"缺少不写回的告警: {logger.msgs}"

    async def test_parsed_feed_with_missing_field_still_comments_out(self) -> None:
        # 正向见证：确认失效的语义没被「一律不写回」连根拔掉。
        written, logger = await self._call(self._PARSED_BUT_EMPTY)
        assert written == [(self.URL, "#" + self.URL)], f"确认失效时未写回: {written}"
        assert any("已注释该房间" in m for m in logger.msgs), f"缺少显式告警: {logger.msgs}"
