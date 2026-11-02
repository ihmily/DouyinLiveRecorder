# 回归用例：抖音弹幕 WS 握手的 signature 参数不做 URL 编码。
#
# 契约依据：上游 dart simple_live_core 以 `var url = "$uri&signature=$sign";` 原样拼接，服务端不按
# form-urlencoded 把 '+' 解成空格；本端若 percent-encode 会成为唯一异类指纹，反而可能触发风控。
# 改编码须同步改本用例与该结论（known-pitfalls.md「抖音弹幕 signature 保持不编码」）。

import asyncio
from unittest.mock import MagicMock

import pytest

from src.platforms import douyin as douyin_mod
from src.platforms._xbogus import XBOGUS_ALPHABET, danmaku_signature


def test_signature_uses_xbogus_alphabet_only() -> None:
    # 签名字符集 = XBogus 自定义字符表 + base64 填充 '='；表内含 '+' 与 '/'，正是不编码会「看起来像 bug」之处。
    sign = danmaku_signature("7383573503129258802", "7383588170770138661")
    assert sign, "签名不应为空"
    assert set(sign) <= set(XBOGUS_ALPHABET) | {"="}
    assert "%" not in sign, "签名本身不应含百分号（编码应发生在调用方，而非生成侧）"
    # 32 位 md5 hex 输入 -> 12 字节载荷 -> 自定义 base64 恒为 16 字符
    assert len(sign) == 16


def test_signature_charset_can_contain_url_sensitive_chars() -> None:
    # 上游若换成 URL-safe 表，本用例转红以提醒重新评估，而不是让结论悄悄失效。
    assert "+" in XBOGUS_ALPHABET or "/" in XBOGUS_ALPHABET


def test_ws_url_appends_signature_verbatim(monkeypatch: pytest.MonkeyPatch) -> None:
    # 端到端（至 WsClient 构造处）：url 以 `&signature=<原文>` 结尾，不得出现 %2B / %2F 形态。
    captured: dict[str, object] = {}

    class _FakeWsClient:
        def __init__(self, url: str, **kwargs: object) -> None:
            captured["url"] = url
            captured["backup_url"] = kwargs.get("backup_url", "")

        async def connect(self) -> None:
            return None

    monkeypatch.setattr(douyin_mod, "WsClient", _FakeWsClient)

    client = douyin_mod.DouyinDanmaku(on_message=None, on_close=None, on_ready=None)
    asyncio.run(client.start({"room_id": "123456789", "user_id": "987654321", "cookie": "ttwid=1"}))

    url = str(captured["url"])
    assert "&signature=" in url
    raw_sign = url.split("&signature=", 1)[1]
    assert raw_sign, "signature 不应为空"
    assert set(raw_sign) <= set(XBOGUS_ALPHABET) | {"="}
    # 与上游一致：原样拼接，没有 percent-encoding
    assert "%2B" not in raw_sign and "%2F" not in raw_sign
    # 备用域名替换仍生效（与上游 replaceAll 对齐）
    assert "webcast100-ws-web-lf" in str(captured["backup_url"])


def test_start_without_room_id_calls_on_close() -> None:
    # 缺 room_id 时不抛异常而回调 on_close：这是签名/WS 构造的前置守卫
    closed: list[str] = []
    client = douyin_mod.DouyinDanmaku(on_message=MagicMock(), on_close=closed.append, on_ready=None)
    asyncio.run(client.start({"room_id": "", "user_id": "1", "cookie": "ttwid=1"}))
    assert closed
