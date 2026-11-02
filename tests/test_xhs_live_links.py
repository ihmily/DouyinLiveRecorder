# 小红书链接统一解析契约的专项测试（PROPOSAL_2026-10-04 Task 1）。
#
# 覆盖的是**纯解析**这一层：`spider.parse_xhs_live_url` 不发网络请求、不读配置，
# 因此本文件不需要 mock async_req / 凭据；短链解重定向与取流链融合留给后续任务。
#
# 断言方式一律是「字面量期望值 ↔ 解析输出」对照：期望的规范化 URL 全部手写常量，
# 测试自身不实现任何路径切分/取参逻辑（AGENTS.md「测试不得自实现解析逻辑」），
# 否则实现与测试犯同一个错时会互相掩护成假绿。
#
# 四类受支持形态（AGENTS 登记口径一致）：
#   1) 标准直播  https://www.xiaohongshu.com/livestream/<数字房间ID>
#   2) 动态段直播 https://www.xiaohongshu.com/livestream/<动态段>/<数字房间ID>
#   3) 分享短链  https://xhslink.com/o/<短码>（本任务只做结构识别，不解重定向）
#   4) 作者主页  https://www.xiaohongshu.com/user/profile/<用户ID>（既有监控兼容）

import json
from typing import Any
from unittest.mock import patch

import pytest

from src import spider as sp
from src.spider import XhsUrlError, parse_xhs_live_url

# 用户给出的真实房间号形态：18 位纯数字，用来锁「room_id 必须按原样整段取出」。
LIVE_ROOM_ID = "570480456678837366"
# 动态路径段（分享出去的直播页会带一段随机前缀），规范化时保留原样、不折叠。
LIVE_DYNAMIC_SEGMENT = "dynpathj5ajT8rr"
SHORT_CODE = "4NnyJghfl4P"


def _rejected(url: str) -> XhsUrlError:
    # 断言该地址被拒绝，并返回结构化异常（供错误类别与脱敏用例比对）。
    with pytest.raises(XhsUrlError) as excinfo:
        parse_xhs_live_url(url)
    error = excinfo.value
    message = str(error).strip()
    # 「信息清晰」的最低门槛：非空且点名小红书，避免调用方只拿到一个空 ValueError
    assert message, f"拒绝 {url} 时没有给出任何错误信息"
    assert "小红书" in message
    return error


# ---------------------------------------------------------------------------
# 1) 四类形态的识别与 room_id / user_id 提取
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("url", "kind", "room_id", "user_id", "normalized_url"),
    [
        (
            f"https://www.xiaohongshu.com/livestream/{LIVE_ROOM_ID}",
            "live",
            LIVE_ROOM_ID,
            "",
            f"https://www.xiaohongshu.com/livestream/{LIVE_ROOM_ID}",
        ),
        (
            f"https://www.xiaohongshu.com/livestream/{LIVE_DYNAMIC_SEGMENT}/{LIVE_ROOM_ID}",
            "live",
            LIVE_ROOM_ID,
            "",
            # 合法动态路径保持原样：删掉动态段后页面未必可访问，故不能擅自折叠
            f"https://www.xiaohongshu.com/livestream/{LIVE_DYNAMIC_SEGMENT}/{LIVE_ROOM_ID}",
        ),
        (
            f"https://xhslink.com/o/{SHORT_CODE}",
            "short",
            "",  # 短码里没有房间号，房间号只能等解重定向后从落地页拿
            "",
            f"https://xhslink.com/o/{SHORT_CODE}",
        ),
        (
            "https://www.xiaohongshu.com/user/profile/5f3e2a1b000000000100abcd",
            "profile",
            "",
            "5f3e2a1b000000000100abcd",
            "https://www.xiaohongshu.com/user/profile/5f3e2a1b000000000100abcd",
        ),
    ],
)
def test_parse_xhs_live_url_shapes(url: str, kind: str, room_id: str, user_id: str, normalized_url: str) -> None:
    info = parse_xhs_live_url(url)
    assert info["kind"] == kind
    assert info["room_id"] == room_id
    assert info["user_id"] == user_id
    assert info["normalized_url"] == normalized_url


def test_parse_result_keys_are_strings() -> None:
    # 返回结构是 dict[str, str]：调用方（分派/配置回写）按 str 取值，混入 None 会在
    # 拼监控名时炸在别处
    info = parse_xhs_live_url(f"https://www.xiaohongshu.com/livestream/{LIVE_ROOM_ID}")
    assert set(info) >= {"kind", "normalized_url", "room_id", "user_id"}
    assert all(isinstance(value, str) for value in info.values())


def test_xhs_url_error_is_value_error() -> None:
    # 继承 ValueError：既有调用点按「ValueError = 输入不合格」处理，不需要改判定
    assert issubclass(XhsUrlError, ValueError)


# ---------------------------------------------------------------------------
# 2) 分享参数归一化：只留 host_id / xsec_token / xsec_source
# ---------------------------------------------------------------------------


def test_share_params_are_whitelisted_and_reordered() -> None:
    # 分享出去的链接带一串统计参数；只保留参与取流/主页兜底的三项，并按固定顺序重建，
    # 这样同一房间的规范地址在配置回写后不会逐轮漂移
    url = (
        f"https://www.xiaohongshu.com/livestream/{LIVE_ROOM_ID}"
        "?xsec_token=XYZtoken123&timestamp=1700000000&share_source=copy_link"
        "&share_id=abcdef&host_id=5f3e2a1b000000000100abcd&xsec_source=app"
    )
    info = parse_xhs_live_url(url)
    assert info["normalized_url"] == (
        f"https://www.xiaohongshu.com/livestream/{LIVE_ROOM_ID}"
        "?host_id=5f3e2a1b000000000100abcd&xsec_token=XYZtoken123&xsec_source=app"
    )
    # 主播兜底沿用既有口径：直播链接没走 /user/profile/ 时拿 host_id 当 user_id
    assert info["user_id"] == "5f3e2a1b000000000100abcd"


def test_share_params_drop_tracking_and_fragment() -> None:
    url = (
        f"https://www.xiaohongshu.com/livestream/{LIVE_ROOM_ID}"
        "?timestamp=1700000000&share_source=copy_link&share_id=abcdef&type=99"
        "#/livestream/whatever"
    )
    normalized = parse_xhs_live_url(url)["normalized_url"]
    for dropped in ("timestamp", "share_source", "share_id", "type", "#"):
        assert dropped not in normalized
    # 没有白名单参数时不应留下一个空的 "?"
    assert normalized == f"https://www.xiaohongshu.com/livestream/{LIVE_ROOM_ID}"


def test_blank_whitelisted_param_is_dropped() -> None:
    # 空值不保留：xsec_token= 既不参与取流，也会让规范地址带上无意义的空尾巴
    url = f"https://www.xiaohongshu.com/livestream/{LIVE_ROOM_ID}?xsec_token=&host_id=abc"
    assert parse_xhs_live_url(url)["normalized_url"] == (
        f"https://www.xiaohongshu.com/livestream/{LIVE_ROOM_ID}?host_id=abc"
    )


# ---------------------------------------------------------------------------
# 3) scheme 归一与尾斜杠
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("url", "normalized_url"),
    [
        # http 输入统一升 https：XHS 页面只在 https 下发 xsec_token
        (
            f"http://www.xiaohongshu.com/livestream/{LIVE_ROOM_ID}/",
            f"https://www.xiaohongshu.com/livestream/{LIVE_ROOM_ID}",
        ),
        (
            f"http://www.xiaohongshu.com/livestream/{LIVE_DYNAMIC_SEGMENT}/{LIVE_ROOM_ID}/",
            f"https://www.xiaohongshu.com/livestream/{LIVE_DYNAMIC_SEGMENT}/{LIVE_ROOM_ID}",
        ),
        (f"http://xhslink.com/o/{SHORT_CODE}/", f"https://xhslink.com/o/{SHORT_CODE}"),
        (
            "http://www.xiaohongshu.com/user/profile/abc123/",
            "https://www.xiaohongshu.com/user/profile/abc123",
        ),
    ],
)
def test_http_is_upgraded_and_trailing_slash_trimmed(url: str, normalized_url: str) -> None:
    assert parse_xhs_live_url(url)["normalized_url"] == normalized_url


def test_default_port_is_accepted_and_removed_from_normalized_url() -> None:
    # 默认端口（http:80 / https:443）视为同一地址，规范化结果不得继续携带端口
    https_info = parse_xhs_live_url(f"https://www.xiaohongshu.com:443/livestream/{LIVE_ROOM_ID}")
    http_info = parse_xhs_live_url(f"http://www.xiaohongshu.com:80/livestream/{LIVE_ROOM_ID}")
    expected = f"https://www.xiaohongshu.com/livestream/{LIVE_ROOM_ID}"
    assert https_info["normalized_url"] == expected
    assert http_info["normalized_url"] == expected


# ---------------------------------------------------------------------------
# 4) 非法输入：host / 路径 / 端口 / userinfo / 畸形
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "url",
    [
        "https://evil.com/livestream/570480456678837366",
        # 后缀伪装：裸 endswith 判定会放行这两条
        "https://www.xiaohongshu.com.evil.com/livestream/570480456678837366",
        "https://evil-xiaohongshu.com/livestream/570480456678837366",
        # 尾部点：hostname 归一化后仍是另一个域
        "https://www.xiaohongshu.com./livestream/570480456678837366",
        # 路径伪装：合法域名只出现在 query/path 里，真正请求的 host 是外站
        "https://evil.com/redirect?to=https://www.xiaohongshu.com/livestream/570480456678837366",
        "https://evil.com/https://www.xiaohongshu.com/livestream/570480456678837366",
        # userinfo 形态的 host 伪装：@ 之前都算用户信息，真正 host 是 evil.com
        "https://www.xiaohongshu.com@evil.com/livestream/570480456678837366",
        # 短链域同样只认精确主机
        "https://xhslink.com.evil.com/o/4NnyJghfl4P",
    ],
)
def test_unsupported_host_is_rejected(url: str) -> None:
    _rejected(url)


@pytest.mark.parametrize(
    "url",
    [
        # 笔记/发现页不是直播间也不是主页，不能拿去取流
        "https://www.xiaohongshu.com/explore/6748c2d0000000001a01b3d9",
        "https://www.xiaohongshu.com/discovery/item/6748c2d0000000001a01b3d9",
        "https://www.xiaohongshu.com/",
        # /livestream 下挂了不认识的子路径形态（动态段只允许一段）
        f"https://www.xiaohongshu.com/livestream/a/b/{LIVE_ROOM_ID}",
        "https://xhslink.com/m/4NnyJghfl4P",
        "https://xhslink.com/",
        "https://xhslink.com/o/..",
        "https://xhslink.com/o/%2e%2e",
        "https://www.xiaohongshu.com/user/profile/..",
        "https://www.xiaohongshu.com/user/profile/%2e%2e",
    ],
)
def test_non_live_path_is_rejected(url: str) -> None:
    _rejected(url)


@pytest.mark.parametrize(
    "url",
    [
        "https://www.xiaohongshu.com/livestream/",
        "https://www.xiaohongshu.com/livestream",
        "https://www.xiaohongshu.com/livestream/dynpathj5ajT8rr/",
    ],
)
def test_missing_room_id_is_rejected(url: str) -> None:
    _rejected(url)


@pytest.mark.parametrize(
    "url",
    [
        "https://www.xiaohongshu.com/livestream/570480456678837366abc",
        "https://www.xiaohongshu.com/livestream/5704804566788373-66",
        "https://www.xiaohongshu.com/livestream/5704804566.78837366",
        "https://www.xiaohongshu.com/livestream/dynpathj5ajT8rr/570480456678837366x",
        "https://www.xiaohongshu.com/livestream/５７０４８０４５６６７８８３７３６６",
        "https://www.xiaohongshu.com/livestream/./570480456678837366",
        "https://www.xiaohongshu.com/livestream/../570480456678837366",
        "https://www.xiaohongshu.com/livestream/%2e%2e/570480456678837366",
    ],
)
def test_non_numeric_room_id_is_rejected(url: str) -> None:
    _rejected(url)


@pytest.mark.parametrize(
    "url",
    [
        # userinfo：即便 host 正确，带凭据的 URL 也不是用户手填的合法形态
        f"https://user:pass@www.xiaohongshu.com/livestream/{LIVE_ROOM_ID}",
        f"https://user@www.xiaohongshu.com/livestream/{LIVE_ROOM_ID}",
        f"https://@www.xiaohongshu.com/livestream/{LIVE_ROOM_ID}",
        # 非默认端口：XHS 官方页面只在默认端口提供服务，带端口一律视为可疑
        f"https://www.xiaohongshu.com:8443/livestream/{LIVE_ROOM_ID}",
        f"http://www.xiaohongshu.com:8080/livestream/{LIVE_ROOM_ID}",
        f"https://xhslink.com:8443/o/{SHORT_CODE}",
    ],
)
def test_userinfo_and_custom_port_are_rejected(url: str) -> None:
    _rejected(url)


@pytest.mark.parametrize(
    "url",
    [
        "",
        "   ",
        # 缺协议：urlparse 会把它整段当 path，不能当合法直播链接放行
        f"www.xiaohongshu.com/livestream/{LIVE_ROOM_ID}",
        "ftp://www.xiaohongshu.com/livestream/570480456678837366",
        "javascript:alert(1)",
        # 畸形 IPv6 字面量：urlparse 在此抛 ValueError，必须转成 XhsUrlError
        "https://[::1/livestream/570480456678837366",
        f"https://www.xiaohongshu.com:port/livestream/{LIVE_ROOM_ID}",
    ],
)
def test_malformed_url_is_rejected(url: str) -> None:
    _rejected(url)


def test_error_messages_distinguish_categories() -> None:
    # 错误分类必须由稳定 code 表达，不能靠消息里不同的 path 值制造「整句不相等」的假绿
    host_error = _rejected("https://evil.com/livestream/570480456678837366")
    path_error = _rejected("https://www.xiaohongshu.com/explore/6748c2d0000000001a01b3d9")
    room_error = _rejected("https://www.xiaohongshu.com/livestream/")
    short_error = _rejected("https://xhslink.com/not-live/4NnyJghfl4P")
    assert host_error.code == "host"
    assert path_error.code == "non_live_path"
    assert room_error.code == "room_id"
    assert short_error.code == "short_path"
    assert "房间 ID 缺失或非数字" in str(room_error)


def test_error_does_not_expose_raw_url_path_or_query_token() -> None:
    url = "https://www.xiaohongshu.com/explore/SECRET_path?xsec_token=SECRET_token_ABC123"
    error = _rejected(url)
    message = str(error)
    assert error.code == "non_live_path"
    assert url not in message
    assert "SECRET_path" not in message
    assert "SECRET_token_ABC123" not in message


def test_parse_is_idempotent() -> None:
    # 幂等：同一输入反复解析结果一致（无缓存/无副作用），配置回写靠这一点才不会逐轮漂移
    url = f"https://www.xiaohongshu.com/livestream/{LIVE_ROOM_ID}?timestamp=1"
    assert parse_xhs_live_url(url) == parse_xhs_live_url(url)


# ---------------------------------------------------------------------------
# 5) 与既有取流链的融合（get_xhs_stream_url）
# ---------------------------------------------------------------------------

_LIVE_ROOM_URL = f"https://www.xiaohongshu.com/livestream/{LIVE_ROOM_ID}"
_DYNAMIC_ROOM_URL = f"https://www.xiaohongshu.com/livestream/{LIVE_DYNAMIC_SEGMENT}/{LIVE_ROOM_ID}"
_SHORT_URL = f"https://xhslink.com/o/{SHORT_CODE}"


def _page(live_status: str, nickname: str = "测试主播", title: str = "直播中") -> str:
    # 构造与真实页面同构的内联状态：liveStream.roomData 同时给 hostInfo 与 roomInfo。
    # 真实页面在 liveStatus="end" 时仍带 hostInfo.nickName（2026-10-04 活体取证），
    # 旧实现只读 roomInfo.deeplink，因此标准链接开不出可监控作业。
    state = {
        "liveStream": {
            "liveStatus": live_status,
            "roomData": {
                "hostInfo": {"nickName": nickname},
                "roomInfo": {"roomTitle": title},
            },
        }
    }
    return "<script>window.__INITIAL_STATE__=" + json.dumps(state, ensure_ascii=False) + "</script>"


def _page_with_deeplink() -> str:
    # 开播态的完整形态：roomInfo.deeplink 带签名 flvUrl，取流走既有链路。
    deeplink = (
        "xhslink://live?flvUrl=http%3A%2F%2Flive-source-play.xhscdn.com%2Flive%2Fabc123.flv"
        "&host_nickname=%E6%B5%8B%E8%AF%95%E4%B8%BB%E6%92%AD"
    )
    state = {
        "liveStream": {
            "liveStatus": "success",
            "roomData": {
                "hostInfo": {"nickName": "测试主播"},
                "roomInfo": {"roomTitle": "直播中", "deeplink": deeplink},
            },
        }
    }
    return "<script>window.__INITIAL_STATE__=" + json.dumps(state, ensure_ascii=False) + "</script>"


class _RecordingAsyncReq:
    # 记录型 async_req 替身：按 URL 子串分发响应；redirect_url=True 走落地页分支。
    # 用类而非「函数挂属性」：mypy 对函数对象属性赋值报 attr-defined，类属性是干净写法。
    def __init__(self, payloads: dict[str, str]) -> None:
        self.payloads = payloads
        self.sent: list[dict[str, Any]] = []

    async def __call__(self, url: str, *args: Any, **kwargs: Any) -> str:
        self.sent.append(
            {"url": url, "headers": kwargs.get("headers") or {}, "redirect": bool(kwargs.get("redirect_url"))}
        )
        for fragment, body in self.payloads.items():
            if fragment in url:
                return body
        return ""


def _fake_async_req(payloads: dict[str, str]) -> _RecordingAsyncReq:
    return _RecordingAsyncReq(payloads)


@pytest.mark.asyncio
async def test_standard_live_link_yields_room_id_and_anchor(monkeypatch: pytest.MonkeyPatch) -> None:
    # 标准直播链接：主播名取 hostInfo.nickName，room_id 取自统一解析器，
    # 即便 liveStatus 不是 success 也要能建立可监控作业（否则首轮判「网址内容获取失败」）
    fake = _fake_async_req({_LIVE_ROOM_URL: _page("end")})
    with patch.object(sp, "async_req", new=fake):
        result = await sp.get_xhs_stream_url(_LIVE_ROOM_URL)
    assert result["anchor_name"] == "测试主播"
    assert result["is_live"] is False
    assert result["room_id"] == LIVE_ROOM_ID
    assert result["normalized_url"] == _LIVE_ROOM_URL


@pytest.mark.asyncio
async def test_dynamic_path_link_is_preserved_and_resolves(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _fake_async_req({LIVE_DYNAMIC_SEGMENT: _page("end")})
    with patch.object(sp, "async_req", new=fake):
        result = await sp.get_xhs_stream_url(_DYNAMIC_ROOM_URL)
    assert result["room_id"] == LIVE_ROOM_ID
    # 动态段必须原样保留：删掉后页面未必可访问
    assert result["normalized_url"] == _DYNAMIC_ROOM_URL


@pytest.mark.asyncio
async def test_share_params_are_stripped_before_page_request(monkeypatch: pytest.MonkeyPatch) -> None:
    url = f"{_LIVE_ROOM_URL}?timestamp=1700000000&share_source=copy_link&xsec_token=XYZ&xsec_source=pc_feed"
    fake = _fake_async_req({LIVE_ROOM_ID: _page("end")})
    with patch.object(sp, "async_req", new=fake):
        result = await sp.get_xhs_stream_url(url)
    page_urls = [item["url"] for item in fake.sent if not item["redirect"]]
    assert page_urls, "未发起房间页请求"
    assert all("timestamp" not in u and "share_source" not in u for u in page_urls), page_urls
    assert all("xsec_token=XYZ" in u for u in page_urls), f"鉴权参数必须保留: {page_urls}"


@pytest.mark.asyncio
async def test_live_success_still_builds_stream_urls(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _fake_async_req({LIVE_ROOM_ID: _page_with_deeplink()})
    with patch.object(sp, "async_req", new=fake):
        result = await sp.get_xhs_stream_url(_LIVE_ROOM_URL)
    assert result["is_live"] is True
    assert result["record_url"] == "http://live-source-play.xhscdn.com/live/abc123.flv"
    assert result["m3u8_url"] == "http://live-source-play.xhscdn.com/live/abc123.m3u8"
    assert result["anchor_name"] == "测试主播"
    assert result["room_id"] == "abc123"


@pytest.mark.asyncio
async def test_short_link_resolves_landing_room_id(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _fake_async_req({_SHORT_URL: _DYNAMIC_ROOM_URL, LIVE_DYNAMIC_SEGMENT: _page("end")})
    with patch.object(sp, "async_req", new=fake):
        result = await sp.get_xhs_stream_url(_SHORT_URL)
    assert result["room_id"] == LIVE_ROOM_ID
    assert result["normalized_url"] == _DYNAMIC_ROOM_URL


@pytest.mark.asyncio
async def test_short_link_redirect_to_note_page_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    note = "https://www.xiaohongshu.com/explore/6748c2d0000000001a01b3d9"
    fake = _fake_async_req({_SHORT_URL: note})
    with patch.object(sp, "async_req", new=fake):
        result = await sp.get_xhs_stream_url(_SHORT_URL)
    assert result["is_live"] is False
    assert result["error"] == "non_live_path"
    # 落地页被判非直播后不得再对**它**发起带凭据的页面请求
    assert not any(note in item["url"] for item in fake.sent), fake.sent


@pytest.mark.asyncio
async def test_short_link_redirect_failure_is_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _req(url: str, *args: Any, **kwargs: Any) -> str:
        return ""

    with patch.object(sp, "async_req", new=_req):
        result = await sp.get_xhs_stream_url(_SHORT_URL)
    assert result["is_live"] is False
    assert result["error"] == "short_redirect"


@pytest.mark.asyncio
async def test_external_landing_still_keeps_credentials_contained(monkeypatch: pytest.MonkeyPatch) -> None:
    # SEV-2214 的安全不变量在新解析器下必须仍成立：跳到外站时不得请求该外站
    fake = _fake_async_req({_SHORT_URL: "https://evil.example.com/steal"})
    with patch.object(sp, "async_req", new=fake):
        await sp.get_xhs_stream_url(_SHORT_URL, cookies="SESSDATA=SECRET")
    assert not any("evil.example.com" in item["url"] for item in fake.sent), fake.sent


@pytest.mark.asyncio
async def test_non_live_link_returns_error_without_request(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _fake_async_req({})
    with patch.object(sp, "async_req", new=fake):
        result = await sp.get_xhs_stream_url("https://www.xiaohongshu.com/explore/6748c2d0000000001a01b3d9")
    assert result["error"] == "non_live_path"
    assert result["is_live"] is False
    assert fake.sent == [], "非法链接不得发出任何请求"


@pytest.mark.asyncio
async def test_room_id_fallback_name_when_nickname_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    # 页面既没给 nickName、链接也没有 host_id 时，用房间 ID 兜底成稳定监控名，
    # 避免 start_record 因空 anchor_name 判「网址内容获取失败」并把该房间打回重试
    fake = _fake_async_req({LIVE_ROOM_ID: _page("end", nickname="")})
    with patch.object(sp, "async_req", new=fake):
        result = await sp.get_xhs_stream_url(_LIVE_ROOM_URL)
    assert result["anchor_name"] == f"小红书_{LIVE_ROOM_ID}"


@pytest.mark.asyncio
async def test_profile_link_keeps_profile_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    # 保留作者主页监控兼容：直播页离线后仍回抓 profile 标题取昵称
    profile_html = "<title>@老主播 的个人主页</title>"
    fake = _fake_async_req({"livestream": _page("end", nickname=""), "user/profile": profile_html})
    with patch.object(sp, "async_req", new=fake):
        result = await sp.get_xhs_stream_url("https://www.xiaohongshu.com/user/profile/5f3e2a1b")
    assert result["anchor_name"] == "老主播"
    assert result["is_live"] is False


# ---------------------------------------------------------------------------
# 6) 分派侧接线：_resolve_xhslink_com 的错误提示与规范 URL 回写
# ---------------------------------------------------------------------------

# 这些 msgid 必须走 i18n.tr 常量模板：提取器只认 logger.<method>(i18n.tr(常量), …)，
# 裸字面量/拼接会让非中文环境回落简体并漏进四语目录（回归锁见 test_i18n_migration）。
_XHS_DISPATCH_MSGIDS = ("小红书链接解析失败，本轮按未识别处理: {record_url} - {code}",)


@pytest.fixture
def main_mod() -> Any:
    import sys
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent
    old_argv = sys.argv[:]
    sys.argv = [str(root / "main.py")]
    try:
        import main as _main

        return _main
    finally:
        sys.argv = old_argv


def _prime_resolver(main: Any, monkeypatch: pytest.MonkeyPatch, port_info: dict[str, Any]) -> None:
    import threading

    monkeypatch.setattr(main, "semaphore", threading.Semaphore(8), raising=False)
    monkeypatch.setattr(main, "xhs_cookie", "", raising=False)

    async def _fake_stream_url(*args: object, **kwargs: object) -> dict[str, object]:
        return dict(port_info)

    monkeypatch.setattr(main.spider, "get_xhs_stream_url", _fake_stream_url)


def test_resolver_reports_parse_error_and_marks_unrecognized(main_mod: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    _prime_resolver(
        main_mod,
        monkeypatch,
        {"anchor_name": "", "is_live": False, "error": "non_live_path"},
    )
    msgs: list[str] = []
    monkeypatch.setattr(main_mod.logger, "warning", lambda msg, *a, **k: msgs.append(str(msg)))
    ctx = main_mod._PlatformResolveContext("https://www.xiaohongshu.com/explore/1", None, "原画")
    main_mod._resolve_xhslink_com(ctx)
    assert ctx.unrecognized is True, "解析失败必须落未识别，否则调用方会按未开播空转"
    assert any("non_live_path" in m for m in msgs), msgs


def test_resolver_writes_normalized_url_back(main_mod: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    normalized = "https://www.xiaohongshu.com/livestream/570480456678837366?host_id=abc"
    _prime_resolver(
        main_mod,
        monkeypatch,
        {"anchor_name": "主播", "is_live": False, "room_id": "570480456678837366", "normalized_url": normalized},
    )
    ctx = main_mod._PlatformResolveContext("https://xhslink.com/o/4NnyJghfl4P", None, "原画")
    main_mod._resolve_xhslink_com(ctx)
    assert ctx.new_record_url == normalized, "短链解析出的规范地址必须回写，避免每轮重复解跳转"
    assert ctx.unrecognized is False


def test_resolver_keeps_empty_new_record_url_without_normalized_field(
    main_mod: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    # 解析器未给出规范地址（老数据/异常形态）时不得凭空造值：回写空串即维持原链接
    _prime_resolver(main_mod, monkeypatch, {"anchor_name": "主播", "is_live": False})
    ctx = main_mod._PlatformResolveContext("https://www.xiaohongshu.com/user/profile/abc", None, "原画")
    main_mod._resolve_xhslink_com(ctx)
    assert ctx.new_record_url == ""


def test_xhs_dispatch_warnings_use_translated_templates() -> None:
    # 静态锁：新增的小红书告警必须是 i18n.tr(常量模板) 首参，否则四语目录漏项
    import ast
    from pathlib import Path

    tree = ast.parse((Path(__file__).resolve().parent.parent / "main.py").read_text(encoding="utf-8"))
    found: set[str] = set()
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and getattr(node.func, "attr", "") == "warning" and node.args):
            continue
        first = node.args[0]
        if (
            isinstance(first, ast.Call)
            and isinstance(first.func, ast.Attribute)
            and first.func.attr == "tr"
            and first.args
            and isinstance(first.args[0], ast.Constant)
            and isinstance(first.args[0].value, str)
        ):
            found.add(first.args[0].value)
    for msgid in _XHS_DISPATCH_MSGIDS:
        assert msgid in found, f"未找到 i18n.tr 模板: {msgid}"


# ---------------------------------------------------------------------------
# 7) 录制启动集成：小红书链接必须能真正建起录制作业
# ---------------------------------------------------------------------------


def test_xhs_link_creates_and_starts_recording_job(
    main_mod: Any, monkeypatch: pytest.MonkeyPatch, tmp_path: Any
) -> None:
    # 端到端接线证明：用户填的直播链接 → 分派到小红书 → 拿到主播名与房间 ID → 选中流 →
    # 拉起 check_subprocess。桩掉网络与选源，断言「作业真的被创建并启动」而不是只解析成功。
    import threading

    room_url = f"https://www.xiaohongshu.com/livestream/{LIVE_ROOM_ID}"
    page = _page("end", nickname="测试主播")
    fake = _fake_async_req({LIVE_ROOM_ID: page})
    monkeypatch.setattr(sp, "async_req", fake)
    monkeypatch.setattr(main_mod, "xhs_cookie", "", raising=False)
    monkeypatch.setattr(main_mod.spider, "async_req", fake)
    monkeypatch.setattr(main_mod, "semaphore", threading.Semaphore(8), raising=False)

    commands: list[list[str]] = []
    updates: list[str] = []

    def _check(
        record_name: str,
        record_url: str,
        ffmpeg_command: list[str],
        record_save_type: str,
        custom_script: str,
        platform: str | None = None,
        danmaku_args: dict[str, Any] | None = None,
    ) -> bool:
        commands.append(list(ffmpeg_command))
        updates.append(record_url)
        return True  # comment_end=True → start_record 干净退出，不进入真实录制循环

    # start_record 靠 exit_recording 收敛：_check 返回 True 即「注释退出」，本例用 main 命名空间里的
    # time 替身把轮末等待的第一次 sleep 变成「置退出标志」（见下方 time_shim），未开播轮也能确定跑完一轮。
    monkeypatch.setattr(main_mod, "check_subprocess", _check)
    monkeypatch.setattr(main_mod, "record_success", lambda *a, **k: None)
    monkeypatch.setattr(main_mod, "record_error", lambda *a, **k: None)
    monkeypatch.setattr(
        main_mod, "select_source_url", lambda *a, **k: "http://live-source-play.xhscdn.com/live/abc.flv"
    )
    monkeypatch.setattr(main_mod, "get_record_headers", lambda *a, **k: None)
    monkeypatch.setattr(main_mod, "get_record_user_agent", lambda *a, **k: None)
    monkeypatch.setattr(main_mod, "converts_mp4", lambda *a, **k: None)
    monkeypatch.setattr(main_mod, "generate_subtitles", lambda *a, **k: None)

    # plain 是 start_record 单轮运行所需的全部模块全局（与 test_record_watchdog 的
    # _prime_start_record / test_start_record_command_golden 的 _setup_case 同一组键）。
    # 逐项列全而不是「setattr 兜底补齐」：缺一个键就会在几十行之后以 NameError 崩在别处，
    # 定位成本远高于这里的冗长。
    plain: dict[str, Any] = {
        "exit_recording": False,
        "recording_enabled": True,
        "recording": set(),
        "recording_time_list": {},
        "record_state_lock": threading.Lock(),
        "need_update_line_list": [],
        "not_record_list": [],
        "error_window": [],
        "url_comments": set(),
        "running_list": [],
        "monitoring": 0,
        "scheduler": None,
        "auto_update_anchor_name": False,
        "show_url": False,
        "live_status_push": False,
        "begin_show_push": False,
        "over_show_push": False,
        "over_push_message_text": "",
        "begin_push_message_text": "",
        "disable_record": False,
        "push_check_seconds": 0,
        "create_time_file": False,
        "converts_to_mp4": False,
        "delete_origin_file": False,
        "custom_script": "",
        "video_save_path": "",
        "folder_by_author": False,
        "folder_by_time": False,
        "folder_by_title": False,
        "filename_by_title": False,
        "default_path": str(tmp_path),
        "enable_https_recording": False,
        "loop_time": False,
        "delay_default": 0,
        "video_save_type": "FLV",
        "split_video_by_time": False,
        "split_time": "600",
        "proxy_addr": "",
        "proxy_addr_bak": "",
        "enable_proxy_platform_list": [],
        "extra_enable_proxy_platform_list": [],
        "OVERSEAS_PLATFORM_HOST": [],
        "color_obj": __import__("unittest.mock", fromlist=["MagicMock"]).MagicMock(),
    }
    for name, value in plain.items():
        monkeypatch.setattr(main_mod, name, value, raising=False)
    for cookie in (
        "dy_cookie",
        "tiktok_cookie",
        "ks_cookie",
        "hy_cookie",
        "douyu_cookie",
        "shopee_cookie",
        "huajiao_cookie",
    ):
        monkeypatch.setattr(main_mod, cookie, "", raising=False)

    # start_record 的内层 while True 靠「轮末 delay_default 等待」再回首部判 exit_recording 收敛；
    # delay_default=0 时它会零耗时空转、测试挂死。用 main 命名空间里的 time 替身把第一次 sleep
    # 变成「置退出标志」，既不真睡、又能确定性地跑完恰好一轮（只改 main 的引用，不动 stdlib 本体；
    # 与 tests/test_record_watchdog.py 的 _Clock 同思路）。
    import time as _time_mod
    import types

    def _sleep_and_stop(_seconds: float) -> None:
        setattr(main_mod, "exit_recording", True)

    time_shim = types.SimpleNamespace(**{k: getattr(_time_mod, k) for k in dir(_time_mod) if not k.startswith("_")})
    time_shim.sleep = _sleep_and_stop
    monkeypatch.setattr(main_mod, "time", time_shim)

    main_mod.start_record(("原画", room_url, ""))

    # 未开播轮次不该起 ffmpeg，但仍必须完成解析：主播名来自 hostInfo.nickName，
    # 空 anchor_name 会被 start_record 判成「网址内容获取失败」并每轮重试
    assert commands == [], "未开播不得启动 ffmpeg"
    assert updates == [], "未开播不得进入录制调用"
    # 监控作业确实建起来了：need_update_line_list 里是「原链接|规范链接,主播: 测试主播」，
    # 空主播名会让这一行退化成无意义的配置回写
    assert main_mod.need_update_line_list, "未开播也必须登记监控作业"
    assert "测试主播" in main_mod.need_update_line_list[0], main_mod.need_update_line_list

    # 同一链接在开播态下必须真正起录制：把 liveStatus 换成 success 再跑一轮
    monkeypatch.setattr(main_mod, "exit_recording", False)
    live_page = _page_with_deeplink()
    live_fake = _fake_async_req({LIVE_ROOM_ID: live_page})
    monkeypatch.setattr(sp, "async_req", live_fake)
    monkeypatch.setattr(main_mod.spider, "async_req", live_fake)
    main_mod.start_record(("原画", room_url, ""))

    assert commands, "开播后必须拉起录制子进程"
    assert any("live-source-play.xhscdn.com" in arg for arg in commands[0]), commands[0]
