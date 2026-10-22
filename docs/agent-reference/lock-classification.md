# 锁的可重入性分类快照

> 自 [`AGENTS.md`](../../AGENTS.md)「已知坑」外迁的纯参考段。
> **外迁判据**：行号快照是某一时点的实测读数，随代码改动必然漂移；
> 根文件保留「改动前必须重新 `grep` 定义行确认」的约束，本文件只提供快照参考。

## 当前实测分类（2026-09-21 快照）

**改动前必须重新 `grep` 定义行确认**，不得凭本清单推断。

### 非重入（`threading.Lock`）

- `web_api._tokens_lock`(:81)
- `web_api._web_cfg_cache_lock`(:83)
- `web_api._rooms_config_lock`(:109)
- `web_api._status_lock`(:133)
- `main.record_state_lock`(:301)
- `cookie_cache._cache_lock`(:62)
- `stream_select._probe_throttle_lock` / `_probe_backoff_lock`
- `async_http._client_cache_lock`
- `log_archive._archive_lock`
- `danmaku_monitor._sidecar_lock` / `_hub_lock`
- `sync_http._all_sessions_lock`
- `utils._js_compile_lock`
- `main._postprocess_executor_lock`

### 刻意重入（`threading.RLock`）

以下**允许**外层已持再内层自持：

- `main.file_update_lock`(:298)
- `web_config._config_write_lock`(:796)
- `ttwid._ttwid_lock`(:63)
- `utils._utils_local_write_lock`(:527)

## 注意

`_cache_lock` 这个名字在仓内不唯一（`cookie_cache._cache_lock` 为 Lock、`web_api` 的是 `_web_cfg_cache_lock`），引用时必须带模块名。
