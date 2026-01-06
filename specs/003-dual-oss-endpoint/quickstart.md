# Quickstart: VOD/OSS双端点配置

**Branch**: `003-dual-oss-endpoint` | **Date**: 2026-01-06

## Prerequisites

- Python >= 3.10
- 火山引擎TOS SDK (`tos` package)
- 已配置的 `config/tos_credentials.ini`

## TOS Endpoint Naming Convention

**重要**: 火山引擎TOS端点命名规则
- `*.volces.com` = **公网**端点
- `*.ivolces.com` = **内网**端点（带 `i`）

## Configuration

### 完整配置（推荐）

```ini
# config/tos_credentials.ini
[TOS]
endpoint = tos-cn-beijing.ivolces.com       # 内网端点 (带i) - 用于上传
s3_endpoint = tos-cn-beijing.volces.com     # 公网端点 (不带i) - 用于播放URL
region = cn-beijing
bucket = your-bucket
access_key = your-access-key
secret_key = your-secret-key
```

### 向后兼容配置

```ini
# config/tos_credentials.ini (旧配置仍可工作，但上传走公网)
[TOS]
endpoint = tos-cn-beijing.volces.com
# s3_endpoint 未配置时自动回退使用 endpoint
region = cn-beijing
bucket = your-bucket
access_key = your-access-key
secret_key = your-secret-key
```

## Verification

### 1. 验证上传走内网

```bash
# 运行录制，观察日志确认使用内网端点
uv run main.py

# 预期日志:
# DEBUG - TOS client initialized for bucket: your-bucket
# DEBUG - Upload success: /path/to/file.ts -> tos://your-bucket/...
```

### 2. 验证播放URL走公网

```bash
# 启动VOD服务
cd vod-player/backend
uv run uvicorn app.main:app --reload

# 请求播放URL
curl http://localhost:8000/api/segments/1/play

# 预期响应中的URL应包含公网域名 (不带i):
# "url": "https://tos-cn-beijing.volces.com/your-bucket/..."
```

### 3. 验证向后兼容

```bash
# 移除 s3_endpoint 配置项，重启VOD服务
# 预期: 服务正常启动，日志显示警告:
# WARNING - s3_endpoint not configured, using endpoint for URL generation
```

## Troubleshooting

| 问题 | 可能原因 | 解决方案 |
|------|----------|----------|
| 上传失败 | 内网端点不可达 | 确认机器在火山云内网环境，使用 `*.ivolces.com` 端点 |
| 上传慢 | 使用了公网端点上传 | 将 `endpoint` 改为内网端点 (`*.ivolces.com`) |
| 播放URL无法访问 | 使用了内网端点生成URL | 将 `s3_endpoint` 改为公网端点 (`*.volces.com`) |
| 启动失败 | 配置格式错误 | 检查 INI 文件语法 |
| 端点混淆 | 内网/公网端点搞反 | 记住：带 `i` 是内网，不带 `i` 是公网 |

## Files Changed

| File | Change Type | Description |
|------|-------------|-------------|
| `vod-player/backend/app/config.py` | Modified | 新增 `tos_s3_endpoint` 字段和加载逻辑 |
| `vod-player/backend/app/services/tos_sign.py` | Modified | 使用 `s3_endpoint` 生成签名URL |
