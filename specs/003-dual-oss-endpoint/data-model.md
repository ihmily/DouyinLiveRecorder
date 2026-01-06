# Data Model: VOD/OSS双端点配置

**Branch**: `003-dual-oss-endpoint` | **Date**: 2026-01-06

## Overview

本功能主要涉及配置数据的扩展，不涉及持久化数据模型变更。

## Configuration Model Changes

### Settings Class Extension

```python
# vod-player/backend/app/config.py

class Settings(BaseSettings):
    # ... existing fields ...

    # TOS (Volcano Engine Object Storage)
    # 端点命名: *.volces.com=公网, *.ivolces.com=内网(带i)
    tos_access_key: str = ""
    tos_secret_key: str = ""
    tos_endpoint: str = ""          # 内网端点 (上传用) - 应为 *.ivolces.com
    tos_s3_endpoint: str = ""       # 新增: 公网端点 (签名URL用) - 应为 *.volces.com
    tos_region: str = ""
    tos_bucket: str = ""
```

### TOS Endpoint Naming Convention

**火山引擎TOS端点命名规则**:
- `*.volces.com` = **公网**端点
- `*.ivolces.com` = **内网**端点（带 `i`）

### Configuration File Structure (Values Need Correction)

```ini
# config/tos_credentials.ini (正确配置)
[TOS]
endpoint = tos-cn-beijing.ivolces.com       # 内网端点 (带i) - 用于上传
s3_endpoint = tos-cn-beijing.volces.com     # 公网端点 (不带i) - 用于VOD URL
region = cn-beijing
bucket = ql-live
access_key = <key>
secret_key = <secret>
```

**注意**: 当前配置文件中的值是错误的（内网/公网颠倒），需要修正。

## Entity Relationships

```
┌─────────────────────┐     reads      ┌──────────────────────┐
│  tos_credentials.ini │ ─────────────> │  load_tos_credentials │
│  - endpoint          │                │  - returns dict       │
│  - s3_endpoint       │                └──────────┬───────────┘
│  - region            │                           │
│  - bucket            │                           │ populates
│  - access_key        │                           v
│  - secret_key        │                ┌──────────────────────┐
└─────────────────────┘                │     Settings          │
                                       │  - tos_endpoint       │
                                       │  - tos_s3_endpoint    │◄── 新增
                                       │  - tos_region         │
                                       │  - tos_bucket         │
                                       └──────────┬───────────┘
                                                  │
                        ┌─────────────────────────┼─────────────────────────┐
                        │                         │                         │
                        v                         v                         v
              ┌─────────────────┐      ┌─────────────────┐      ┌─────────────────┐
              │  TOSUploader    │      │  tos_sign.py    │      │  Fallback Logic │
              │  uses: endpoint │      │  uses: s3_endpoint│     │  s3 → endpoint  │
              │  (内网上传)      │      │  (公网签名URL)   │      │  + warning log  │
              └─────────────────┘      └─────────────────┘      └─────────────────┘
```

## Validation Rules

1. **endpoint**: Required. Must be a valid TOS endpoint URL
2. **s3_endpoint**: Optional. When missing, fallback to `endpoint` with warning
3. **region**: Required. Must match endpoint region (e.g., `cn-beijing`)
4. **bucket**: Required. Must be accessible with provided credentials

## State Transitions

N/A - This feature does not introduce new stateful entities.

## Backward Compatibility

| Scenario | Config State | Behavior |
|----------|--------------|----------|
| Full config | Both endpoints present | Upload uses `endpoint`, VOD uses `s3_endpoint` |
| Legacy config | Only `endpoint` | Both use `endpoint`, warning logged |
| Invalid config | Missing required fields | Startup error with clear message |
