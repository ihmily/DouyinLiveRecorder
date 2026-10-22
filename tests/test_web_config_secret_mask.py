# CR-08/09/10 面板配置脱敏与房间地址校验的回归锁（src/web_config.py，2026-09-21 补）。
#
# 本文件只补「零引用」的那三个点，不重复 tests/test_web_config.py 已经覆盖的
# validate_room_target 内网/换行/画质白名单表：
#   ① _looks_like_secret_value —— CR-10 的**值形态**第二道防线（键名不含凭据关键词、
#      但值本身就是凭据：钉钉/企业微信 webhook、带账密的代理地址）。
#   ② read_config_safe —— 脱敏真正落地处（节白名单 + 键名正则 + 值形态三重，
#      并把 '***' 回显给面板；掩码跳过是前端写入侧唯一防线，见 AGENTS.md）。
#   ③ _validate_room_url_target —— 抛出的 ValueError 文案会被 web_api 原样塞进
#      HTTPException(422, str(e)) 作为面板可见的 detail，故文案本身是契约的一部分
#      （报告里称「400 文案」，实测状态码为 422）。
# 全部用例驱动**真实函数**，测试内不重新实现任何判定逻辑。

import configparser
from pathlib import Path

import pytest

from src.web_config import (
    SENSITIVE_MASK,
    _looks_like_secret_value,
    _validate_room_url_target,
    is_sensitive_item,
    is_sensitive_key,
    read_config_safe,
)

# 三行解析桩：离线化，避免用例随真实 DNS 漂移（本文件只验裁决，不验 DNS）
_PUBLIC_IPS = ["114.114.114.114"]


def _stub_dns(monkeypatch: pytest.MonkeyPatch, table: dict[str, list[str] | OSError]) -> None:
    from src import web_config as wc

    def _resolve(host: str) -> list[str]:
        answer = table.get(host, _PUBLIC_IPS)
        if isinstance(answer, OSError):
            raise answer
        return list(answer)

    monkeypatch.setattr(wc, "_resolve_host_ips", _resolve)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        # 值里带 userinfo（http://user:pass@host）——键名往往只是「代理地址」
        ("http://user:pass@127.0.0.1:7890", True),
        ("http://user:pass@[::1]:8080/x", True),
        # 端点型凭据：query 里嵌 token/key/secret/pwd
        ("https://oapi.dingtalk.com/robot/send?access_token=ABC123", True),
        ("https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=deadbeef", True),
        ("https://ntfy.sh/topic?password=1", True),
        ("HTTPS://HOST/P?PASSWD=1", True),  # 大小写不敏感
        ("https://x.example/p?a=1&secret=2", True),
        # 无凭据的普通 URL：不得误伤（否则面板把公开地址渲染成不可编辑的掩码）
        ("https://day.app/MyKey124", False),  # bark 短链型 key 走**键名**白名单，不属值形态
        ("https://ntfy.sh/mytopic", False),
        ("http://127.0.0.1:7890", False),  # 无账密的代理地址由键名「代理地址」命中
        ("http://[2408:8000::1]/live.m3u8", False),
        # 非 URL 形态一律不做启发式判定（避免把普通配置误判成凭据）
        ("ABC123token", False),
        ("66c7f0f462eeedd9d1f2d46bdc10e4e2", False),
        ("", False),
        ("   ", False),
        ("ftp://host/path?key=1", True),  # scheme 不限 http/https，只要是 URL 形态
        # M-61（2026-10-21）：摘掉「必须以 scheme 开头」门后，裸写 user:pass@host 的 userinfo
        # （代理地址的常见形态）不再逃逸兜底；同侧反向：无 @ 无凭据参数的裸串仍不得误伤
        ("user:pass@127.0.0.1:7890", True),
        ("u:p@socks.example", True),
        ("plain text 123", False),
    ],
)
def test_looks_like_secret_value_table(value: str, expected: bool) -> None:
    assert _looks_like_secret_value(value) is expected


@pytest.mark.parametrize(
    ("key", "expected"),
    [
        ("tgapi令牌", True),
        ("发件人密码(授权码)", True),
        ("pushplus推送token", True),
        ("popkontv_token", True),
        ("钉钉推送接口链接", True),
        ("代理地址", True),
        # 反向例外表：数值型运维参数放行，否则面板里的 web_token_expiry 会变成改不动的掩码
        ("web_token_expiry", False),
        ("超时时间", False),
        ("cookie有效期", False),
        ("录制保存路径", False),
    ],
)
def test_is_sensitive_key_table(key: str, expected: bool) -> None:
    assert is_sensitive_key(key) is expected


def test_is_sensitive_item_covers_non_whitelisted_sections() -> None:
    # 节白名单只有 Cookie/账号密码/Authorization；[推送配置] 不在其中，
    # 全靠键名正则把 tgapi令牌 等凭据捞出来——两处判定是「或」关系，缺一不可。
    # [历史注] M-61（2026-10-21）起 推送配置 **已并入**节白名单，下面第一条因此是双命中；
    # 「仅键名侧命中且节不在白名单」的半边改由 录制设置/代理地址 锁定，两侧各有一条腿在跑
    assert is_sensitive_item("推送配置", "tgapi令牌") is True
    assert is_sensitive_item("Cookie", "dy_cookie") is True  # 仅节名命中
    assert is_sensitive_item("录制设置", "代理地址") is True  # 仅键名命中（节不在白名单）
    assert is_sensitive_item("录制设置", "视频保存格式") is False


def test_push_section_is_sensitive_by_name_now() -> None:
    # M-61（2026-10-21）：[推送配置] 节内存在键名不含凭据关键词、值形态也不像凭据的独立
    # 敏感项（钉钉@手机号是纯数字、邮箱登录账号可能为空态占位）——键名正则与值形态两道
    # 同时落空，只有节白名单能覆盖。取一个键名/值都不命中另两道的样本，单独钉节名这一道
    assert is_sensitive_item("推送配置", "钉钉@手机号") is True
    assert is_sensitive_item("推送配置", "邮箱登录账号") is True
    # 双重口径 intact：非白名单节 + 无关键词键不得被牵连
    assert is_sensitive_item("录制设置", "视频保存格式") is False


def test_read_config_safe_masks_by_section_key_and_value(tmp_path: Path) -> None:
    # 端到端：三类判定（节白名单 / 键名 / 值形态）都必须把非空敏感值替换成 SENSITIVE_MASK，
    # 且**空值原样保留**（空＝未配置，掩码会让用户以为已填）。
    cfg = tmp_path / "config.ini"
    cfg.write_text(
        "[Cookie]\n"
        "dy_cookie = ttwid=abc\n"
        "[推送配置]\n"
        "tgapi令牌 = 123456:ABC-DEF\n"
        "钉钉推送接口链接 = https://oapi.dingtalk.com/robot/send?access_token=XYZ\n"
        "钉钉@手机号 = 13800000000\n"
        "[Web]\n"
        "web_password = hunter2\n"
        "web_token_expiry = 86400\n"
        "[录制设置]\n"
        "视频保存格式 = TS\n"
        "webhook无凭据 = https://ntfy.sh/topic\n"
        "空凭据位 =\n",
        encoding="utf-8",
    )
    result = read_config_safe(cfg)
    assert result["Cookie"]["dy_cookie"] == SENSITIVE_MASK
    assert result["推送配置"]["tgapi令牌"] == SENSITIVE_MASK
    assert result["推送配置"]["钉钉推送接口链接"] == SENSITIVE_MASK
    # M-61（2026-10-21）：推送配置 进节白名单后，键名/值形态两都不命中的 钉钉@手机号 也必须掩掉
    assert result["推送配置"]["钉钉@手机号"] == SENSITIVE_MASK
    assert result["Web"]["web_password"] == SENSITIVE_MASK
    # 值形态防线不得误伤无凭据 URL；例外表不得掩掉数值型运维参数；非敏感键保持明文。
    # [历史注] webhook无凭据 原挂在 [推送配置] 下——M-61 该节整节掩码后这半边判据在此节
    # 不再可表达（节名白名单命中等义于「该节任何非空值都掩」），故挪到非白名单节，
    # 「值形态不误伤」的判据本身逐字保留
    assert result["录制设置"]["webhook无凭据"] == "https://ntfy.sh/topic"
    assert result["Web"]["web_token_expiry"] == "86400"
    assert result["录制设置"]["视频保存格式"] == "TS"
    # 空值不脱敏（写入侧靠「值 == '***' 则跳过」保护真实凭据，见 web/app.js saveConfig）
    assert result["录制设置"]["空凭据位"] == ""
    assert SENSITIVE_MASK == "***", "掩码值与前端 app.js 的 SENSITIVE_MASK 同源，改动须同步两处"


@pytest.mark.parametrize(
    ("url", "expected_substring"),
    [
        ("file:///etc/passwd?a=.flv", "协议不允许"),
        ("rtp://127.0.0.1/x?a=.flv", "协议不允许"),
        ("ftp://host/live.m3u8", "协议不允许"),
        ("https://", "缺少主机名"),
        ("http:///no-host/x", "缺少主机名"),
        ("http://127.0.0.1:8000/x?a=.flv", "禁止写入"),
        ("http://169.254.169.254/latest/meta-data/", "禁止写入"),
        ("http://100.64.0.1/x?a=.flv", "禁止写入"),  # CGNAT 非私网，靠显式网段名单
        ("http://127-0-0-1.sslip.io/x?a=.flv", "禁止写入"),  # DNS 指回环
        ("http://nowhere.example.com/x?a=.flv", "禁止写入"),  # 解析失败一律拒绝
    ],
)
def test_validate_room_url_target_rejects_with_panel_visible_wording(
    url: str, expected_substring: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    # 文案是面板可见的 detail（web_api 把 ValueError 原样塞进 HTTPException(422, str(e))），
    # 故这里既验「拒绝」也验「为什么拒绝」——只断 raises 会让用户看到空泛错误。
    _stub_dns(monkeypatch, {"127-0-0-1.sslip.io": ["127.0.0.1"], "nowhere.example.com": OSError("no DNS")})
    with pytest.raises(ValueError) as excinfo:
        _validate_room_url_target(url)
    assert expected_substring in str(excinfo.value), f"{url} 的文案缺少关键信息: {excinfo.value}"


@pytest.mark.parametrize(
    "url",
    [
        "",  # 空值放行：房间地址可为空（新增房间前的占位行）
        "   ",
        "https://live.douyin.com/745964462470",
        "live.douyin.com/745964462470",  # 省略协议 → 按 host 段校验（normalize_url 会补 https）
        "http://121.229.0.10/live/a.m3u8",  # 公网 IP 直连
    ],
)
def test_validate_room_url_target_allows_public_and_blank(url: str, monkeypatch: pytest.MonkeyPatch) -> None:
    # 反向护栏：收紧判定不得把「省略协议」「公网 IP」「空值」一起砍掉
    _stub_dns(monkeypatch, {})
    _validate_room_url_target(url)


def test_written_config_round_trips_as_unmodified(tmp_path: Path) -> None:
    # read_config_safe 只读不改盘：面板 GET 一次配置后，磁盘上的凭据必须仍是原文
    # （曾因把脱敏结果回写而把真实 token 覆盖成 '***'，见 AGENTS.md 脱敏条目）。
    cfg = tmp_path / "config.ini"
    raw = "[Cookie]\ndy_cookie = ttwid=abc\n"
    cfg.write_text(raw, encoding="utf-8")
    assert read_config_safe(cfg)["Cookie"]["dy_cookie"] == SENSITIVE_MASK
    parser = configparser.ConfigParser(interpolation=None)
    parser.read(cfg, encoding="utf-8")
    assert parser["Cookie"]["dy_cookie"] == "ttwid=abc"
