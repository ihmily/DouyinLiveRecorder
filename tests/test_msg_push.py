# Tests for msg_push.py 批次5修复 - 凭证脱敏与钉钉载荷回归测试.

from typing import cast
from unittest.mock import patch

from msg_push import _mask_secret, _mask_url, dingtalk


class TestMaskSecret:
    def test_short_secret_fully_masked(self) -> None:
        # 5-6 位短密钥此前只遮 1-2 位，形同虚设
        assert _mask_secret("abc12") == "****"
        assert _mask_secret("abc123") == "****"

    def test_long_secret_keeps_edges(self) -> None:
        assert _mask_secret("abcdefgh") == "ab****gh"

    def test_empty_secret(self) -> None:
        assert _mask_secret("") == ""


class TestMaskUrl:
    def test_bark_short_key_masked(self) -> None:
        # 8 位 Bark key 此前因长度 <=12 漏遮蔽，凭证落盘日志
        masked = _mask_url("https://api.day.app/AbCd1234")
        assert "AbCd1234" not in masked

    def test_telegram_bot_token_masked(self) -> None:
        masked = _mask_url("https://api.telegram.org/bot123456:AAABCDEFGH/sendMessage")
        assert "123456:AAABCDEFGH" not in masked
        assert "bot****" in masked

    def test_query_token_dropped(self) -> None:
        masked = _mask_url("https://oapi.dingtalk.com/robot/send?access_token=SECRETTOKEN")
        assert "SECRETTOKEN" not in masked

    def test_normal_url_unchanged(self) -> None:
        masked = _mask_url("https://example.com/api/status")
        assert masked == "https://example.com/api/status"


class FakeResponse:
    def __init__(self, body: bytes) -> None:
        self.body = body

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def read(self) -> bytes:
        return self.body


class TestDingtalk:
    def test_at_mobiles_omitted_when_number_none(self) -> None:
        captured: dict[str, object] = {}

        def fake_open(req: object, timeout: int = 10) -> FakeResponse:
            captured["data"] = getattr(req, "data")
            return FakeResponse(b'{"errcode": 0}')

        with patch("msg_push.opener.open", side_effect=fake_open):
            result = dingtalk("https://oapi.dingtalk.com/robot/send?access_token=x", "hi", number=None)
        assert result["success"]
        import json

        payload = json.loads(cast(bytes, captured["data"]).decode("utf-8"))
        assert "atMobiles" not in payload["at"]

    def test_at_mobiles_included_when_number_given(self) -> None:
        captured: dict[str, object] = {}

        def fake_open(req: object, timeout: int = 10) -> FakeResponse:
            captured["data"] = getattr(req, "data")
            return FakeResponse(b'{"errcode": 0}')

        with patch("msg_push.opener.open", side_effect=fake_open):
            result = dingtalk("https://oapi.dingtalk.com/robot/send?access_token=x", "hi", number="13800000000")
        assert result["success"]
        import json

        payload = json.loads(cast(bytes, captured["data"]).decode("utf-8"))
        assert payload["at"]["atMobiles"] == ["13800000000"]
        assert payload["at"]["isAtAll"] is False
