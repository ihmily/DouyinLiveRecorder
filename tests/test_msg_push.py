# 凭证脱敏与钉钉载荷回归。
# 守护三类行为：(1) _mask_secret/_mask_url 不再因「长度门槛」漏遮蔽（短密钥、8 位 Bark key、
# Telegram bot token 此前会落入日志）；(2) 钉钉载荷按 number 是否存在决定带不带 atMobiles；
# (3) MID-58：「密钥即路径末段」的渠道（Bark / Server酱 / 息知）无条件遮蔽末段，不按 day.app
# 主机名白名单——自建 / 反代 Bark 的 device key 同样不得进轮转日志。
# Mock 设计：钉钉用例 patch msg_push.opener.open（urllib 层）拦截真实 HTTP，捕获请求体后断言
# JSON 载荷；Bark 用例另挂 loguru sink，断言**实际写进日志的那一行**不含明文 key（只测
# _mask_url 会漏掉「调用点忘传参数」）。

from collections.abc import Callable
from typing import cast
from unittest.mock import patch

from loguru import logger

from msg_push import _mask_secret, _mask_url, bark, dingtalk


# 守护 _mask_secret 的长度分档策略：短凭证整串遮蔽、长凭证保留首尾各 2 位。
# 保留首尾的目的是让运维能在日志里区分「这是哪个凭据」，同时不足以被还原。
class TestMaskSecret:
    def test_short_secret_fully_masked(self) -> None:
        # 5-6 位短密钥此前只遮 1-2 位，形同虚设
        assert _mask_secret("abc12") == "****"
        assert _mask_secret("abc123") == "****"

    # 8 位及以上走「保留首尾各 2 位」：既保留可辨识度，又不足以反推原文。
    def test_long_secret_keeps_edges(self) -> None:
        assert _mask_secret("abcdefgh") == "ab****gh"

    # 边界：空串必须原样返回 ""，不能产出 "****"——否则日志里会把「未配置」
    # 误显示成「已配置但被隐藏」，排查方向被带偏。
    def test_empty_secret(self) -> None:
        assert _mask_secret("") == ""


# 守护 _mask_url 对不同 URL 形态的处理：路径段凭证、query 凭证、以及普通 URL 不被误伤。
class TestMaskUrl:
    def test_bark_short_key_masked(self) -> None:
        # 8 位 Bark key 此前因长度 <=12 漏遮蔽，凭证落盘日志
        masked = _mask_url("https://api.day.app/AbCd1234", mask_last_segment=True)
        assert "AbCd1234" not in masked

    # MID-58 回归锁：Bark 的密钥位置是「路径最后一段」，与主机名无关。旧实现靠
    # hostname.endswith("day.app") 白名单命中，自建 / 反代 Bark 的密钥因此整串明文进轮转日志
    # （拿到即可向用户手机无限推送）；现由调用方按渠道声明 mask_last_segment。
    def test_self_hosted_bark_key_masked(self) -> None:
        masked = _mask_url("https://bark.example.com/AbCdEfGh", mask_last_segment=True)
        assert "AbCdEfGh" not in masked
        assert masked == "https://bark.example.com/****"

    # 反向护栏：不声明「末段即密钥」的渠道行为不变——钉钉/Telegram/状态接口的
    # 路径段（robot、status）是定位信息，全遮会让日志失去排查价值。
    def test_other_channels_keep_short_path_segments(self) -> None:
        assert _mask_url("https://oapi.dingtalk.com/robot/send") == "https://oapi.dingtalk.com/robot/send"
        assert _mask_url("https://example.com/api/status") == "https://example.com/api/status"

    # 多级路径只遮最后一段：Server酱 sctapi 形态 <SCT 长密钥>.send 本就命中长密钥规则，
    # 这里断言「前面的路径段仍保留」，确认遮蔽范围没有扩大到整条 path。
    def test_only_last_segment_masked(self) -> None:
        masked = _mask_url("https://host/push/v1/AbCdEfGh", mask_last_segment=True)
        assert masked == "https://host/push/v1/****"

    def test_telegram_bot_token_masked(self) -> None:
        masked = _mask_url("https://api.telegram.org/bot123456:AAABCDEFGH/sendMessage")
        assert "123456:AAABCDEFGH" not in masked
        assert "bot****" in masked

    # query 串里的 access_token 整段丢弃而非部分遮蔽：token 无「保留首尾」的价值，
    # 留任何片段都可能被拼凑还原。
    def test_query_token_dropped(self) -> None:
        masked = _mask_url("https://oapi.dingtalk.com/robot/send?access_token=SECRETTOKEN")
        assert "SECRETTOKEN" not in masked

    # 反向护栏：脱敏不能过度。普通 URL 必须原样保留，否则日志里所有地址都变成
    # 无法定位的掩码，出问题时失去排查价值。
    def test_normal_url_unchanged(self) -> None:
        masked = _mask_url("https://example.com/api/status")
        assert masked == "https://example.com/api/status"


# MID-58 端到端锁：真正写日志的是 bark() 的失败分支，只测 _mask_url 的话，
# 调用点漏传 mask_last_segment 依然会把明文 key 写进 logs/streamget.log。
class TestBarkFailureLogMasking:
    def test_bark_failure_log_masks_self_hosted_key(self) -> None:
        captured: list[str] = []
        sink_id = logger.add(lambda message: captured.append(str(message)), level="WARNING")
        try:
            with patch("msg_push.opener.open", side_effect=_fail_response(b'{"code": 500, "message": "nope"}')):
                result = bark("https://bark.example.com/AbCdEfGh", "title", "content")
        finally:
            logger.remove(sink_id)
        assert result["success"] == []
        assert result["error"] == ["https://bark.example.com/AbCdEfGh"]
        joined = "".join(captured)
        assert "AbCdEfGh" not in joined
        assert "bark.example.com/****" in joined

    def test_bark_failure_log_masks_official_key(self) -> None:
        captured: list[str] = []
        sink_id = logger.add(lambda message: captured.append(str(message)), level="WARNING")
        try:
            with patch("msg_push.opener.open", side_effect=_fail_response(b'{"code": 500}')):
                bark("https://api.day.app/AbCd1234", "title", "content")
        finally:
            logger.remove(sink_id)
        assert "AbCd1234" not in "".join(captured)


# 最小 urllib 响应桩：仅实现 read() 返回预设 body，供 opener.open 的 side_effect 包装返回，
# 使 patch 能捕获请求体又无需真实网络。
class FakeResponse:
    def __init__(self, body: bytes) -> None:
        self.body = body

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def read(self) -> bytes:
        return self.body


# opener.open 的替身工厂：返回预设响应体（业务失败），使推送走「失败 + 写日志」分支。
# 定义在 FakeResponse 之后——本文件未启用 future annotations，签名里的类必须先存在。
# 签名用 ... 是因为真实调用点为 opener.open(req, timeout=N)，位置/关键字参数都在变。
def _fail_response(body: bytes) -> Callable[..., FakeResponse]:
    def fake_open(req: object, timeout: int = 10) -> FakeResponse:
        return FakeResponse(body)

    return fake_open


# 守护钉钉机器人载荷的 @ 人字段构造：number 的有无决定是否携带 atMobiles。
# 这两个用例覆盖真实回归——早期实现无条件写 atMobiles，导致未配置手机号时
# 钉钉侧收到空 @ 列表而报错，推送整体失败。
class TestDingtalk:
    # number=None 时不 @任何人：钉钉载荷的 at 对象不得含 atMobiles（静默推送）。
    def test_at_mobiles_omitted_when_number_none(self) -> None:
        captured: dict[str, object] = {}

        # 从 Request 对象上取 data（即待发送的请求体）留存，随后在用例里解析断言；
        # 返回 errcode=0 的伪造响应，使 dingtalk 走「成功」分支。
        def fake_open(req: object, timeout: int = 10) -> FakeResponse:
            captured["data"] = getattr(req, "data")
            return FakeResponse(b'{"errcode": 0}')

        with patch("msg_push.opener.open", side_effect=fake_open):
            result = dingtalk("https://oapi.dingtalk.com/robot/send?access_token=x", "hi", number=None)
        # 钉钉的成败不能只看 HTTP 状态码：接口恒返回 200，业务失败体现在 errcode!=0，
        # 故 success 字段是唯一可信判据。
        assert result["success"]
        import json

        payload = json.loads(cast(bytes, captured["data"]).decode("utf-8"))
        assert "atMobiles" not in payload["at"]

    # number 给出时按手机号 @人：atMobiles 须为 [number]，且 isAtAll 为 False（非全员）。
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
