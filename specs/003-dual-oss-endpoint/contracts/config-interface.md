# Configuration Interface Contract

**Branch**: `003-dual-oss-endpoint` | **Date**: 2026-01-06

## Overview

本功能不涉及API变更，仅涉及内部配置接口的扩展。

## Settings Interface

### Current Interface

```python
class Settings:
    tos_endpoint: str      # TOS端点
```

### Extended Interface

```python
class Settings:
    tos_endpoint: str       # TOS内网端点 (上传用)
    tos_s3_endpoint: str    # TOS公网端点 (签名URL用) - 新增
```

## Function Contracts

### load_tos_credentials()

**Current Behavior**:
```python
def load_tos_credentials(credentials_path: str) -> dict:
    """Returns: {access_key, secret_key, endpoint, region, bucket}"""
```

**Extended Behavior**:
```python
def load_tos_credentials(credentials_path: str) -> dict:
    """Returns: {access_key, secret_key, endpoint, s3_endpoint, region, bucket}"""
    # s3_endpoint may be empty string if not configured
```

### get_tos_client() in tos_sign.py

**Current Behavior**:
```python
def get_tos_client() -> TosClientV2:
    """Uses settings.tos_endpoint"""
```

**Extended Behavior**:
```python
def get_tos_client() -> TosClientV2:
    """
    Uses settings.tos_s3_endpoint for public URL generation.
    Falls back to settings.tos_endpoint if s3_endpoint not configured.
    Logs warning when fallback is used.
    """
```

## Error Contracts

| Condition | Error Type | Message |
|-----------|------------|---------|
| `endpoint` missing | `RuntimeError` | "TOS endpoint not configured" |
| `s3_endpoint` missing | Warning log | "s3_endpoint not configured, using endpoint for URL generation" |
| Invalid credentials | `TosServerError` | SDK error message |

## No API Changes

本功能不影响任何外部API：
- `/api/segments/{segment_id}/play` - 响应格式不变，仅URL内容使用公网域名
- 所有其他API端点 - 无变更
