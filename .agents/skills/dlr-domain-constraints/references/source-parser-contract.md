# 平台解析函数返回契约

> **约束事实源**: `AGENTS.md`「已知坑」下的「装饰器与平台兜底契约」。
> 约束变更以 AGENTS.md 为准。

## 装饰器选择

- `trace_error_decorator`: 返回 dict 的函数，失败时回 `{"is_live": False}`。
- `trace_error_decorator_or_none`: 返回 str/tuple/None 的函数，回 None。
- **装饰器与 `def` 之间不得有注释**（会把装饰器绑到下一个 `def`）。
- 新增平台先看返回注解再选装饰器。

## JSON 解析兜底

- `_loads_dict`: 平台返回 HTML（WAF/302/Cloudflare/截断 JSON）时回 `{}` 并记 warning。
- **不再抛 JSONDecodeError**（约 40 处调用任一抛错都会被兜底装饰器吞成「未开播」）。
- 裸 `json.loads` 由棘轮锁住不得回升（`BARE_JSON_LOADS_CEILING = 1`）。
