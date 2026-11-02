# 平台专属选源约束

> **约束事实源**: `AGENTS.md`「已知坑」下的「平台接口、签名与流地址解析」。
> 约束变更以 AGENTS.md 为准。

## 虎牙

- **探针退避仅限虎牙**: aldirect CDN 对同路径短时间连击限流。
- **绝不可把斗鱼等加入名单**。
- **选源必须 FLV-first（`_FLV_FIRST_PLATFORMS`）**: 候选序列 FLV→HLS→record_url。
- 退避窗口 `≥ max(_PROBE_BACKOFF_SECONDS, main.delay_default + _PROBE_BACKOFF_INTERVAL_MARGIN)`。
- **不可改回固定 60s 常量**——否则快速失败记入退避后下一轮早已超出窗口。

## 斗鱼

- **绝不加入 `_FLV_FIRST_PLATFORMS`**: 游客态 FLV ~70s 被掐，必须 HLS 优先。
- 必须附带 FLV→m3u8 同 token HLS 候选（wsAuth token 对 FLV/HLS 通用，`.flv` 改 `.m3u8`）。
- 本地重试链按 `DOUYU_RATE_BY_CODE` 映射 rate，服务端钳制时经 `DOUYU_RATE_DESC` 全序本地最多回退 2 档。

## HLS 采集排除平台 vs FLV-first 调序

- **「HLS 采集排除平台」是整组剔除**: 命中的平台直接不把 HLS 候选放入序列。
- **`_FLV_FIRST_PLATFORMS` 只是调序**: FLV 排到 HLS 前、HLS 仍留作回退。
- **两种语义不可互实现**。
- 回归锁：`tests/test_stream_select.py` 的 5 个排除列用例。
