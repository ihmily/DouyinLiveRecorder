# Tests for src/weverse_auth.py module - Weverse 认证模块.
# 中文：本文件验证 Weverse 刷新令牌接口 refresh_weverse_token 的边界与契约——
# None/空令牌直接短路、网络/HTTP 异常统一兜底 (None, None)、请求体/URL/超时契约正确；
# 并验证客户端密钥 _app_secret 支持环境变量覆盖（批次5修复：去硬编码）。
# Mock 设计：全程 patch src.weverse_auth.requests.post 隔离真实网络；密钥覆盖用例用
# monkeypatch.setenv/delenv 操作环境变量（遵循 AGENTS.md 约定，禁用 patch.dict(os.environ)）。

from unittest.mock import MagicMock, patch

import pytest

from src.weverse_auth import refresh_weverse_token


class TestRefreshWeverseToken:
    # Test Weverse token 刷新.

    def test_none_token_returns_none(self) -> None:
        # None refresh_token 返回 (None, None).
        access, refresh = refresh_weverse_token(None)
        assert access is None
        assert refresh is None

    def test_empty_token_returns_none(self) -> None:
        # 空字符串 refresh_token 返回 (None, None).
        access, refresh = refresh_weverse_token("")
        assert access is None
        assert refresh is None

    @patch("src.weverse_auth.requests.post")
    def test_successful_refresh(self, mock_post: MagicMock) -> None:
        # 成功刷新 token.
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "accessToken": "new_access_token_123",
            "refreshToken": "new_refresh_token_456",
        }
        mock_post.return_value = mock_response

        access, refresh = refresh_weverse_token("old_refresh_token")
        assert access == "new_access_token_123"
        assert refresh == "new_refresh_token_456"
        mock_post.assert_called_once()

    @patch("src.weverse_auth.requests.post")
    def test_non_200_returns_none(self, mock_post: MagicMock) -> None:
        # 非 200 状态码返回 (None, None).
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_post.return_value = mock_response

        access, refresh = refresh_weverse_token("expired_token")
        assert access is None
        assert refresh is None

    @patch("src.weverse_auth.requests.post")
    def test_exception_returns_none(self, mock_post: MagicMock) -> None:
        # 网络异常返回 (None, None).
        mock_post.side_effect = Exception("connection timeout")

        access, refresh = refresh_weverse_token("some_token")
        assert access is None
        assert refresh is None

    @patch("src.weverse_auth.requests.post")
    def test_correct_api_url(self, mock_post: MagicMock) -> None:
        # 调用正确的 API 地址.
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"accessToken": "a", "refreshToken": "r"}
        mock_post.return_value = mock_response

        refresh_weverse_token("token")
        call_args = mock_post.call_args
        assert "accountapi.weverse.io" in call_args.args[0]
        assert call_args.kwargs["json"] == {"refreshToken": "token"}
        assert call_args.kwargs["timeout"] == 10


class TestAppSecret:
    # 客户端密钥支持环境变量覆盖（批次5修复：硬编码密钥改为可覆盖）.

    # 默认密钥：未设环境变量时回退内置常量，长度须 >= 20（安全基线，防止误配极短密钥）。
    def test_default_secret(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from src.weverse_auth import _app_secret

        monkeypatch.delenv("DOUYIN_WEVERSE_APP_SECRET", raising=False)
        assert len(_app_secret()) >= 20

    def test_env_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from src.weverse_auth import _app_secret

        monkeypatch.setenv("DOUYIN_WEVERSE_APP_SECRET", "custom-secret")
        assert _app_secret() == "custom-secret"
