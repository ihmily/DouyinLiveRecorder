---
name: platform-source-selection
description: >
  DouyinLiveRecorder 项目中平台流地址选源、探针可达性校验与画质档位映射的硬约束。
  当修改平台解析函数、选源流程、探针逻辑、画质映射或新增平台时使用此 Skill。
  触发词：select_source_url、stream_select、探针、probe、FLV-first、HLS 排除、
  画质映射、QUALITY_MAPPING、_validate_stream_url、_confirm_get_ok、
  _PROBE_BACKOFF_PLATFORMS、_FLV_FIRST_PLATFORMS、trace_error_decorator。
---

# 平台选源流程与画质映射

> **约束事实源**: `AGENTS.md`「已知坑」下的「流地址探针与可达性校验」、
> 「平台接口、签名与流地址解析」、「画质档位与选源映射」、「装饰器与平台兜底契约」。
> 本 Skill 提取高频复用内容供按需加载；约束变更以 AGENTS.md 为准。
>
> **详细内容已拆分至 `references/` 子目录**，主文件仅保留路由表与触发条件。

## 何时加载

- 修改 `src/stream_select.py`（选源/探针/可达性校验）。
- 修改 `src/stream.py`（画质映射/平台选档）。
- 修改 `src/spider.py`（平台解析函数）。
- 新增平台接入或修改已有平台的流地址解析。
- 调试流地址不可达、选源回退异常、画质档位错误。

## 路由表

| 子主题 | 文件 | 触发场景 |
| --- | --- | --- |
| 探针可达性校验与节流 | [`references/probe-reachability.md`](references/probe-reachability.md) | 修改探针逻辑、HEAD/GET 探测流程、节流/抖动、UA 一致性、退避撤销 |
| 平台专属选源约束 | [`references/platform-selection.md`](references/platform-selection.md) | 虎牙/斗鱼选源规则、FLV-first 调序、HLS 采集排除 |
| 画质档位映射 | [`references/quality-mapping.md`](references/quality-mapping.md) | 通用画质映射、蓝光子档位、虎牙选档、斗鱼本地重试链 |
| 平台解析函数返回契约 | [`references/parser-contract.md`](references/parser-contract.md) | 装饰器选择、JSON 解析兜底、`_loads_dict` 行为 |

## 验证

### 项目级门禁（由 `python scripts/run_gates.py` 统一兜底，Skill 不重复）

- `black --check`、`isort --check-only`、`mypy`（含 `--platform linux` / `--platform win32`）、`check_annotations.py`

### 本领域专项检查

1. `pytest tests/test_stream_select.py` — 全绿
2. `pytest tests/test_stream.py` — 全绿（画质映射）
3. `pytest tests/test_spider.py` — 全绿
4. `pytest tests/test_spider_hardening.py` — 全绿（裸 JSON loads 上限）
5. `pytest tests/test_platform_dispatch.py` — 全绿
6. `grep -n "_FLV_FIRST_PLATFORMS" src/stream_select.py` — 确认斗鱼不在名单中
7. `grep -n "_PROBE_BACKOFF_PLATFORMS" src/stream_select.py` — 确认仅虎牙
