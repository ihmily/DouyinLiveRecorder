# 凭证脱敏与钉钉载荷回归。
# 守护三类行为：(1) _mask_secret/_mask_url 不再因「长度门槛」漏遮蔽（短密钥、8 位 Bark key、
# Telegram bot token 此前会落入日志）；(2) 钉钉载荷按 number 是否存在决定带不带 atMobiles；
# (3) ：「密钥即路径末段」的渠道（Bark / Server酱 / 息知）无条件遮蔽末段，不按 day.app
# 主机名白名单——自建 / 反代 Bark 的 device key 同样不得进轮转日志。
# Mock 设计：钉钉用例 patch msg_push.opener.open（urllib 层）拦截真实 HTTP，捕获请求体后断言
# JSON 载荷；Bark 用例另挂 loguru sink，断言**实际写进日志的那一行**不含明文 key（只测
# _mask_url 会漏掉「调用点忘传参数」）。

from collections.abc import Callable
from typing import cast
from unittest.mock import patch

import pytest
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

    # Bark 的密钥位置是「路径最后一段」，与主机名无关。旧实现靠
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

    # S-07：netloc 里的 basic-auth userinfo 此前原样带出，
    # 自托管反代的口令因此明文进轮转日志；只剥 userinfo，主机与路径保持可读。
    def test_userinfo_stripped_from_netloc(self) -> None:
        masked = _mask_url("https://user:secretpw@hooks.example.com/services/foo/bar")
        assert "secretpw" not in masked
        assert masked == "https://***@hooks.example.com/services/foo/bar"


# 端到端锁：真正写日志的是 bark() 的失败分支，只测 _mask_url 的话，
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

    # S-07 第二半：脱敏只做地址不够——出站异常文本里同样可能带完整 URL（urllib 的 URLError 会把
    # 请求地址拼进 str(e)），失败分支若直传 e=e 则口令经轮转日志长期落盘。此处让 opener 直接抛
    # 带凭据的异常，断言**实际写进日志的那一行**已抹除口令。
    def test_bark_failure_log_masks_exception_url_credentials(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # 准入校验会先按 DNS 判 host（本机离线时 bark.example.com 直接判「无法解析」），
        # 这里把校验替成恒等，专门覆盖「出站异常文本」这一段。
        monkeypatch.setattr("msg_push._checked_push_url", lambda url: url)
        captured: list[str] = []
        sink_id = logger.add(lambda message: captured.append(str(message)), level="WARNING")
        try:
            with patch(
                "msg_push.opener.open",
                side_effect=OSError("connection refused: https://user:secretpw@bark.example.com/AbCdEfGh"),
            ):
                result = bark("https://bark.example.com/AbCdEfGh", "title", "content")
        finally:
            logger.remove(sink_id)
        assert result["success"] == []
        joined = "".join(captured)
        assert "secretpw" not in joined
        assert "OSError" in joined


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


# ------------------------------------------------------------------------------------
# 重置向必须逐跳复核，不能只校验首跳。
# 攻击模型：推送地址设为攻击者服务器 → 它 302 到 http://169.254.169.254/latest/meta-data/ →
# 首跳校验通过、落地地址是内网，响应体再经 errmsg/msg 字段写进日志（带回显 SSRF）。
# 两条互补判据：① 处理器本身拒绝内网落地；② opener 上挂的确实是该守卫子类（裸 handler 不得回归）。
class TestPushRedirectHopGuard:
    @staticmethod
    def _handler() -> object:
        import msg_push

        return msg_push._PushHopGuardRedirectHandler()

    def test_internal_landing_is_rejected(self) -> None:
        # 判据口径与首跳**完全相同**（_checked_push_url，allow_local_targets=True）：
        # 云元数据/内部 DNS 名必须拒绝；回环与私网按该既有裁决放行（自建 ntfy/Bark 反代
        # 跑在本机或局域网是合规配置，拦掉会把真实用户的推送打哑）。
        import urllib.error
        import urllib.request
        from http.client import HTTPMessage
        from io import BytesIO

        handler = self._handler()
        req = urllib.request.Request("https://attacker.example/notify")
        with pytest.raises(urllib.error.URLError):
            handler.redirect_request(  # type: ignore[attr-defined]
                req, BytesIO(b""), 302, "Found", HTTPMessage(), "http://169.254.169.254/latest/meta-data/"
            )

    def test_non_http_landing_is_rejected(self) -> None:
        import urllib.error
        import urllib.request
        from http.client import HTTPMessage
        from io import BytesIO

        handler = self._handler()
        req = urllib.request.Request("https://attacker.example/notify")
        with pytest.raises(urllib.error.URLError):
            handler.redirect_request(req, BytesIO(b""), 302, "Found", HTTPMessage(), "file:///etc/passwd")  # type: ignore[attr-defined]

    def test_opener_registers_the_guard_not_the_bare_handler(self) -> None:
        # 结构锁：白名单里替换成裸 HTTPRedirectHandler 会让上面的两条行为锁整体失效，
        # 而行为锁本身看不到「处理器被换掉」。故按类型钉一次。
        import urllib.request

        import msg_push

        handlers = cast("list[object]", getattr(msg_push.opener, "handlers"))
        assert not any(
            type(h) is urllib.request.HTTPRedirectHandler for h in handlers
        ), "opener 上仍挂着裸 HTTPRedirectHandler（逐跳闸门被摘掉）"
        assert any(type(h).__name__ == "_PushHopGuardRedirectHandler" for h in handlers)
