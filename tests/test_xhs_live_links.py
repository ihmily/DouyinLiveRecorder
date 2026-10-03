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

import pytest

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
