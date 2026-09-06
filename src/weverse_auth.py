#!/usr/bin/env python3
# -*- encoding: utf-8 -*-
# Weverse 平台认证模块 - 负责 Token 刷新功能

import os
import uuid
from typing import cast

import requests

# Weverse 网页客户端公开的应用密钥（非用户凭据）；官方更换时无需改码，
# 通过环境变量 DOUYIN_WEVERSE_APP_SECRET 即可覆盖
_DEFAULT_APP_SECRET = "5419526f1c624b38b10787e5c10b2a7a"


def _app_secret() -> str:
    # 客户端密钥：优先读环境变量覆盖，未设置时用内置默认值
    return os.environ.get("DOUYIN_WEVERSE_APP_SECRET") or _DEFAULT_APP_SECRET


def refresh_weverse_token(refresh_token: str | None) -> tuple[str | None, str | None]:
    # 刷新 Weverse 访问令牌
    if not refresh_token:
        return None, None

    refresh_url = "https://accountapi.weverse.io/api/v1/token/refresh"

    headers: dict[str, str] = {
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36",
        "Origin": "https://weverse.io",
        "Referer": "https://weverse.io/",
        "X-ACC-SERVICE-ID": "weverse",
        "X-ACC-APP-SECRET": _app_secret(),
        "X-ACC-TRACE-ID": str(uuid.uuid4()),
    }

    payload: dict[str, str | None] = {"refreshToken": refresh_token}

    try:
        response = requests.post(refresh_url, json=payload, headers=headers, timeout=10)
        if response.status_code == 200:
            data: dict[str, object] = cast("dict[str, object]", response.json())
            new_access_token: str | None = cast("str | None", data.get("accessToken"))
            new_refresh_token: str | None = cast("str | None", data.get("refreshToken"))
            return new_access_token, new_refresh_token
        else:
            return None, None
    except Exception:
        return None, None
