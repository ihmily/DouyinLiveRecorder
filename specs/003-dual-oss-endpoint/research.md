# Research: VOD/OSS双端点配置

**Branch**: `003-dual-oss-endpoint` | **Date**: 2026-01-06

## Current Implementation Analysis

### TOS Endpoint Naming Convention

**火山引擎TOS端点命名规则**:
- `*.volces.com` = **公网**端点
- `*.ivolces.com` = **内网**端点（带 `i`）

### Configuration Status (PROBLEM IDENTIFIED)

| Config Item | Location | Current Value | Actual Type | Intended Use | Status |
|-------------|----------|---------------|-------------|--------------|--------|
| `endpoint` | `tos_credentials.ini:3` | `tos-cn-beijing.volces.com` | **公网** (不带i) | 上传(应内网) | ❌ 错误 |
| `s3_endpoint` | `tos_credentials.ini:4` | `tos-s3-cn-beijing.ivolces.com` | **内网** (带i) | VOD URL(应公网) | ❌ 错误 |

**Finding**: 当前配置值与用途**完全相反**！配置文件注释写的是"内网"，但实际 `tos-cn-beijing.volces.com` 是公网端点。

**Decision**:
1. 配置文件结构正确，无需修改
2. 配置**值**需要修正为正确的端点

### Upload Path Analysis (PPL - `uv run main.py`)

| Component | File | Line | Endpoint Used | Code Status | Config Status |
|-----------|------|------|---------------|-------------|---------------|
| TOSUploader | `src/storage/tos_uploader.py` | 69-74 | `endpoint` 配置项 | ✅ 代码正确 | ❌ 值是公网 |
| Proxy清除 | `src/storage/tos_uploader.py` | 65-67 | N/A | ✅ 正确 | N/A |

**Decision**:
- 代码逻辑正确：使用 `endpoint` 配置项进行上传
- 配置值错误：当前 `endpoint` 值是公网，应改为内网 (`*.ivolces.com`)

### VOD Service Analysis

| Component | File | Line | Endpoint Used | Status |
|-----------|------|------|---------------|--------|
| Settings类 | `vod-player/backend/app/config.py` | 14-38 | 只有 `tos_endpoint` | ❌ 缺失 `tos_s3_endpoint` |
| load_tos_credentials | `vod-player/backend/app/config.py` | 59-76 | 只读取 `endpoint` | ❌ 未读取 `s3_endpoint` |
| get_tos_client | `vod-player/backend/app/services/tos_sign.py` | 26-41 | 使用 `settings.tos_endpoint` | ❌ 应使用公网端点 |

**Decision**: VOD服务配置加载和URL生成需要修改以支持公网端点。

## Required Changes Summary

### Change 1: Config Loading (config.py)

**Rationale**: 需要读取 `s3_endpoint` 配置项并提供给VOD服务

**Scope**:
- `Settings` 类新增 `tos_s3_endpoint` 字段
- `load_tos_credentials()` 读取 `s3_endpoint`
- `get_settings()` 填充 `tos_s3_endpoint`

**Backward Compatibility**: 当 `s3_endpoint` 未配置时，回退使用 `endpoint` 并记录警告

### Change 2: Presigned URL Generation (tos_sign.py)

**Rationale**: 生成的URL必须使用公网可访问的端点

**Options Evaluated**:

| Option | Approach | Pros | Cons |
|--------|----------|------|------|
| A | 创建使用s3_endpoint的TOS客户端 | 简单直接，SDK保证签名正确 | 需验证TOS SDK是否支持s3_endpoint格式 |
| B | 生成URL后替换域名 | 保持现有客户端逻辑 | 签名可能与域名绑定，替换后失效 |
| C | 使用boto3+s3_endpoint | S3兼容性好 | 引入新依赖，复杂度增加 |

**Decision**: 选择 **Option A** - 创建使用公网端点的TOS客户端

**Technical Verification Needed**: 确认火山引擎TOS SDK的 `pre_signed_url()` 方法支持使用 `s3_endpoint` 格式的端点

## Changes Summary

### Code Changes Required

| Component | Status | Change Needed |
|-----------|--------|---------------|
| `vod-player/backend/app/config.py` | ❌ 需修改 | 读取 `s3_endpoint` 配置 |
| `vod-player/backend/app/services/tos_sign.py` | ❌ 需修改 | 使用公网端点生成URL |

### Code - No Changes Required

| Component | Status | Reason |
|-----------|--------|--------|
| `tos_credentials.ini` 结构 | ✅ 正确 | 已有 `endpoint` 和 `s3_endpoint` 字段 |
| `src/storage/tos_uploader.py` | ✅ 正确 | 代码逻辑正确，使用 `endpoint` 配置项 |

### Configuration Value Changes Required (User Action)

```ini
# 当前错误配置:
endpoint = tos-cn-beijing.volces.com       # 公网 - 错！
s3_endpoint = tos-s3-cn-beijing.ivolces.com # 内网 - 错！

# 正确配置:
endpoint = tos-cn-beijing.ivolces.com       # 内网 (带i) - 用于上传
s3_endpoint = tos-cn-beijing.volces.com     # 公网 (不带i) - 用于VOD URL
```

## Technical Verification: TOS SDK Endpoint Compatibility

### Question: TOS SDK是否支持任意端点URL？

**火山引擎TOS端点类型**:
- `tos-cn-beijing.volces.com` - TOS原生SDK公网端点
- `tos-cn-beijing.ivolces.com` - TOS原生SDK内网端点
- `tos-s3-cn-beijing.volces.com` - S3兼容公网端点
- `tos-s3-cn-beijing.ivolces.com` - S3兼容内网端点

**Finding**: TOS SDK的 `TosClientV2` 支持传入任意端点URL。预签名URL使用传入的端点构建URL域名。

**Conclusion**: 可以使用TOS原生公网端点 `tos-cn-beijing.volces.com` 生成公网可访问的签名URL。

## Alternatives Considered

### 不使用s3_endpoint，直接替换URL域名

**Rejected Because**: TOS的预签名URL签名可能包含Host信息，简单替换域名可能导致签名验证失败。即使当前版本可行，未来SDK升级可能破坏此行为。

### 使用boto3代替TOS SDK

**Rejected Because**:
1. 引入额外依赖
2. 需要维护两套SDK代码
3. TOS SDK已能满足需求
