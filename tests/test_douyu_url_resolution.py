# 斗鱼链接房间号提取回归用例（移动端 m.douyu.com 接入）
#
# 覆盖四种输入形态与两类失败形态，并锁定「提取结果可直接喂给既有斗鱼流程」：
#   1. 房间号直接跟在路径后   https://m.douyu.com/8751648
#   2. 带尾斜杠               https://m.douyu.com/8751648/
#   3. 带查询参数             https://m.douyu.com/8751648?dyshid=... 与 ?rid=8751648
#   4. http 版本链接          http://m.douyu.com/8751648
# 失败形态：路径里没有房间号、房间号还原结果非数字（二者都必须明确报错而不是静默空转）。
#
# 判据选择：断言「betard 请求 URL 逐字等于 https://www.douyu.com/betard/8751648」而非只看
# anchor_name——尾斜杠形态的旧缺陷正是「房间号带 / 被拼进 betard 路径」，只看结果会被兜底掩盖。

import json
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from src import spider

ROOM_ID = "8751648"

# （URL, 预期房间号候选）。四种形态都必须归一到纯数字房间号，且不含尾斜杠 / query / fragment
_PATH_CASES = [
    ("https://m.douyu.com/8751648", ROOM_ID),
    ("https://m.douyu.com/8751648/", ROOM_ID),
    ("https://m.douyu.com/8751648?dyshid=0-96003918aa5365bc6dcb4933000316p1&dyshci=181", ROOM_ID),
    ("https://m.douyu.com/8751648?rid=8751648", ROOM_ID),
    ("http://m.douyu.com/8751648", ROOM_ID),
    ("http://m.douyu.com/8751648/", ROOM_ID),
    ("https://m.douyu.com/8751648#/live", ROOM_ID),
    # 多段路径只认首段：整段拼接会把 /extra 带进 betard 路径（旧正则同型缺陷）
    ("https://m.douyu.com/8751648/extra", ROOM_ID),
    # www 侧形态不受本次改动影响，一并钉住防止回归
    ("https://www.douyu.com/8751648", ROOM_ID),
    ("https://www.douyu.com/8751648/", ROOM_ID),
    # 无 scheme 输入：准入侧会补 https://，提取函数按同一规则自补，不得把主机名当房间号
    ("m.douyu.com/8751648", ROOM_ID),
]

# 路径里没有房间号的形态：必须抛明确错误，而不是拿空串去请求 betard
_MISSING_CASES = [
    "https://m.douyu.com/",
    "https://m.douyu.com",
    "http://www.douyu.com/",
    "https://www.douyu.com",
]


def _mobile_html(rid: str = ROOM_ID) -> str:
    # 移动端房间页：真实页面把房间信息放在 id="vike_pageContext" 的 JSON 脚本里，
    # 解析链靠它把字母号/短链还原成数字 rid（见 spider.get_douyu_info_data）
    context = json.dumps(
        {"pageProps": {"room": {"roomInfo": {"roomInfo": {"rid": rid, "nickname": "锚名"}}}}},
        ensure_ascii=False,
    )
    return f'<html><head><script id="vike_pageContext" type="application/json">{context}</script></head></html>'


def _betard_json() -> str:
    # betard 响应：show_status=1 + videoLoop=0 才判真开播（轮播/回放不得被当作直播）
    return json.dumps(
        {
            "room": {
                "nickname": "锚名",
                "videoLoop": 0,
                "show_status": 1,
                "room_name": "标题&nbsp;直播",
                "room_id": int(ROOM_ID),
            }
        },
        ensure_ascii=False,
    )


@pytest.mark.parametrize("url,expected", _PATH_CASES)
def test_extract_room_id_covers_all_url_forms(url: str, expected: str) -> None:
    assert spider.extract_douyu_room_id(url) == expected


@pytest.mark.parametrize("url", _MISSING_CASES)
def test_extract_room_id_raises_when_missing(url: str) -> None:
    # 错误消息必须带脱敏后的链接：用户按此定位是哪条配置写错了
    with pytest.raises(ValueError, match="房间号"):
        spider.extract_douyu_room_id(url)


def test_missing_room_id_message_carries_masked_url() -> None:
    # 链接可带 token 类查询参数，入错误消息前必须过 mask_credentials
    # （斗鱼分享链常挂 wsAuth / token，日志按 300KB 轮转保留多份，明文入日志即凭据持久化）
    with pytest.raises(ValueError) as excinfo:
        spider.extract_douyu_room_id("https://m.douyu.com/?dyshid=0-abc&token=supersecretvalue")
    message = str(excinfo.value)
    assert "m.douyu.com" in message
    assert "supersecretvalue" not in message


def test_rid_param_is_anchored() -> None:
    # 旧实现 "rid=(.*?)(?=&|$)" 未锚定参数边界：?xyzrid=999 会被误命中成房间号
    assert spider.extract_douyu_rid_param("https://m.douyu.com/8751648?xyzrid=999") == ""
    assert spider.extract_douyu_rid_param("https://m.douyu.com/8751648?rid=8751648") == ROOM_ID
    assert spider.extract_douyu_rid_param("https://m.douyu.com/8751648?a=1&rid=8751648&b=2") == ROOM_ID
    assert spider.extract_douyu_rid_param("https://m.douyu.com/8751648") == ""


@pytest.mark.asyncio
@pytest.mark.parametrize("url", [case[0] for case in _PATH_CASES if "://" in case[0]])
async def test_mobile_url_reuses_existing_douyu_pipeline(url: str) -> None:
    # 核心契约：移动端链接复用既有斗鱼流程，最终请求的 betard 地址与 www 形态逐字一致
    requested: list[str] = []

    # 形参必须叫 url：生产侧恒以关键字 `async_req(url=..., proxy_addr=..., headers=...)` 调用
    async def _fake_req(url: str, **_kwargs: Any) -> str:
        requested.append(url)
        return _betard_json() if "betard" in url else _mobile_html()

    with patch("src.spider.async_req", new_callable=AsyncMock, side_effect=_fake_req):
        result = await spider.get_douyu_info_data(url)

    assert result["is_live"] is True
    assert result["anchor_name"] == "锚名"
    # 尾斜杠 / query / fragment 都不得被带进 betard 路径
    assert requested[-1] == f"https://www.douyu.com/betard/{ROOM_ID}"


@pytest.mark.asyncio
async def test_non_numeric_resolved_rid_raises() -> None:
    # betard / getH5PlayV1 只认数字 rid：还原产物非数字时必须在还原出口报错，
    # 而不是拼出一个必然拿不到 room 的 URL（旧实现会把它伪装成「房间不存在」）
    async def _fake_req(url: str, **_kwargs: Any) -> str:
        return _betard_json() if "betard" in url else _mobile_html(rid="字母号")

    # get_douyu_info_data 带 trace_error_decorator：异常会被吞成 {"is_live": False}。
    # 故直接测未装饰本体（functools.wraps 保留的 __wrapped__），再单独锁装饰后的兜底结果——
    # 两条合起来才是「抛得出来 + 不穿透主循环」的完整契约。
    raw = getattr(spider.get_douyu_info_data, "__wrapped__")
    with patch("src.spider.async_req", new_callable=AsyncMock, side_effect=_fake_req):
        with pytest.raises(ValueError, match="非数字"):
            await raw("https://m.douyu.com/字母号")
        assert await spider.get_douyu_info_data("https://m.douyu.com/字母号") == {"is_live": False}


@pytest.mark.asyncio
async def test_non_numeric_rid_param_falls_back_to_page_resolution() -> None:
    # ?rid=abc 不是数字时不得直拼 betard（旧行为必失败且无提示），要走页面还原
    requested: list[str] = []

    async def _fake_req(url: str, **_kwargs: Any) -> str:
        requested.append(url)
        return _betard_json() if "betard" in url else _mobile_html()

    with patch("src.spider.async_req", new_callable=AsyncMock, side_effect=_fake_req):
        result = await spider.get_douyu_info_data("https://m.douyu.com/8751648?rid=abc")

    assert requested[0] == f"https://m.douyu.com/{ROOM_ID}"
    assert requested[-1] == f"https://www.douyu.com/betard/{ROOM_ID}"
    assert result["is_live"] is True
