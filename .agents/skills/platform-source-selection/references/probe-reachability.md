# 探针可达性校验与节流

> **约束事实源**: `AGENTS.md`「已知坑」下的「流地址探针与可达性校验」。
> 约束变更以 AGENTS.md 为准。

## 探测方法

- CDN 对 m3u8 的 `HEAD` 常回 4xx（含 404）而 `GET` 能拉流。
- **统一流程**: HEAD 非 2xx → Range `GET bytes=0-0` 探测（200/206 判可达）。
- **不要只覆盖 400/401/403/405**。
- 同步/异步校验器的 proxy/verify/UA 三者必须一致（否则境外平台直连误判不可达）。

## GET 复核容错

- 401/403 **先原样重试一次**再定罪。
- 候选已是末位（无 record_url 备选）时稳定拒绝也仅告警放行、交由 ffmpeg 定夺。
- **删重试或末位放行会重引「探针误杀可用源」**。
- m3u8 Range-GET 探针 401/403 同样先隔 `_GET_RECHECK_INTERVAL` 重试。
- HLS 为唯一候选或 FLV 为 h265 不可用时传 `last_resort=True`。

## 末位候选放行

- `_validate_stream_url` 的 text/html 分支与尾部非 200 分支对 `last_resort=True` 必须仅告警放行。
- 斗鱼 hw CDN HEAD 回 405+text/html，ffmpeg 实际 GET 正常。

## 探针节流/抖动

- 同 host 节流: `_throttle_probe`，`_PROBE_MIN_HOST_INTERVAL=0.35s` + 抖动。
- 重试抖动: `_recheck_delay`，`0.8s + uniform(0, 0.7s)`。
- **消除机器人节奏指纹**；改为固定值或移除会重引风控误伤。
- 测试侧 autouse fixture 置 `_throttle_probe` 为 no-op。

## UA 双端一致性

- `main.py` ffmpeg 默认移动 UA ≡ `stream_select.MOBILE_UA`。
- `room.HEADERS` 的 UA 参与 X-Bogus 签名。
- 改字符串须同步四处：`MOBILE_UA` / `main.py ffmpeg 默认 UA` / `room.HEADERS` / B站 H5 UA。
- 全库基准（2026-08）：桌面 Chrome/141、Edg/141、Firefox/148、移动 `Android 14; Pixel 8` Chrome/141。

## 录制成功须撤销探针退避

- `clear_ffmpeg_reject(url, platform)` 与 `mark_ffmpeg_reject` 对称。
- 只清实际拉流成功的 FLV，HLS 退避不顺带清。
- 共用同一白名单与退避键。
