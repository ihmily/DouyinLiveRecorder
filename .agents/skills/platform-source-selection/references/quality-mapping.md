# 画质档位映射

> **约束事实源**: `AGENTS.md`「已知坑」下的「画质档位与选源映射」。
> 约束变更以 AGENTS.md 为准。

## 通用映射

- OD=0, BD=1, UHD=2, HD=3, SD=4, LD=5。
- 蓝光子档位（BD4/8/20/30）必须折叠到 BD 索引，**不得塞进 `QUALITY_MAPPING`**。
- 细粒度靠 `BD_SUB_TIERS` 承载。
- 中文映射须含蓝光4M/8M/20M/30M，新增须同步四处：
  `get_quality_code` / `web_config.QUALITY_KEYWORD` / `main.py` 白名单 / `web/index.html`。

## 虎牙选档

- `ratio_val` 由 `bitRate` 上限推导（`HUYA_FIXED_TIERS`）。
- exsphd 档位表存在时优先取 ≤ 上限的 ratio。
- 请求档不可用时就近向下降级，无任何更低档时不附加 ratio 按原画(OD)拉流。
- **绝不可抛异常或返回空流地址**，保持 `is_live=True` 契约交由上层重试。

## 斗鱼本地重试链

- 按 `DOUYU_RATE_BY_CODE` 映射 rate。
- 服务端钳制时经 `DOUYU_RATE_DESC` 全序本地最多回退 2 档重试。
- 全部失败时明确告警「已无更低档位」并保持 `is_live=True`。
