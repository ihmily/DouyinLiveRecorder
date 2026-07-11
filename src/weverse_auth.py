#!/usr/bin/env python3
# -*- encoding: utf-8 -*-
# Weverse 平台认证模块 - 负责 Token 刷新功能

import requests
import uuid


def refresh_weverse_token(refresh_token):
    # 刷新 Weverse 访问令牌
    if not refresh_token:
        return None, None

    refresh_url = "https://accountapi.weverse.io/api/v1/token/refresh"
    
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Origin": "https://weverse.io",
        "Referer": "https://weverse.io/",
        "X-ACC-SERVICE-ID": "weverse",
        "X-ACC-APP-SECRET": "5419526f1c624b38b10787e5c10b2a7a",
        "X-ACC-TRACE-ID": str(uuid.uuid4())
    }

    payload = {"refreshToken": refresh_token}

    try:
        response = requests.post(refresh_url, json=payload, headers=headers)
        if response.status_code == 200:
            data = response.json()
            new_access_token = data.get("accessToken")
            new_refresh_token = data.get("refreshToken")
            return new_access_token, new_refresh_token
        else:
            return None, None
    except Exception:
        return None, None
