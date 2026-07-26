# Web 管理面板设计

- **日期**: 2026-07-23
- **项目**: DouyinLiveRecorder
- **作者**: 协作产出（用户 + 助手）
- **状态**: 已确认，待实施

## 1. 背景与目标

DouyinLiveRecorder 当前提供命令行模式 (`main.py`) 和桌面 GUI 模式 (`gui.py`，基于 CustomTkinter)，另有独立的 M3U8 播放器页面 (`index.html`)。核心录制引擎是一个基于 FFmpeg 的多平台（60+）直播录制器，配置以 `config.ini`（录制/推送/Cookie 等节）+ `URL_config.ini`（直播间地址列表）两个文本文件为唯一真相源，主循环每轮热加载这些文件。

本设计为项目新增 **Web 管理面板**：通过浏览器远程查看录制状态、管理直播间地址、编辑配置、浏览/下载录制文件。目标是补齐“无 GUI 依赖、可远程访问、Docker 友好”的运维入口，与现有 `main.py` / `gui.py` 并列，互不干扰。

### 非目标

- 不重构 `main.py` 为类（避免大改动风险）。
- 不替代 `gui.py`；GUI 与 Web 并存。
- 不实现录制引擎本身的重写，复用全部现有平台逻辑。
- 不做用户体系/多租户；认证仅单密码登录。

## 2. 需求确认

| 维度 | 决策 |
|------|------|
| 功能范围 | 状态监控仪表盘 + 直播间地址管理 + 录制配置编辑 + 录制文件浏览（四项全要） |
| 集成架构 | 新独立入口 `web.py`（方案 A：重构 `main()` + 导入驱动） |
| 认证 | 可选密码登录（config.ini 开关控制） |
| 前端技术栈 | FastAPI + 原生 HTML/CSS/JS（零构建步骤） |

## 3. 架构

### 3.1 总体结构

```
web.py (新入口)
  ├── import main                      # 触发配置初始化/FFmpeg 检查，不进入主循环
  ├── 启动 main.main() 于守护线程       # 录制引擎
  ├── 创建 src.web_api.create_app()    # FastAPI 应用
  └── uvicorn.run(app, host, port)     # 主线程 HTTP 服务

src/web_api.py (新)
  ├── create_app(config) -> FastAPI
  ├── 认证中间件（可选）
  ├── REST 路由 (/api/*)
  └── 挂载 web/ 静态资源

web/ (新目录, 前端资源)
  ├── index.html   # 单页应用，标签页导航
  ├── app.js       # 前端逻辑（fetch + SSE）
  └── style.css    # 浅色/深色双主题
```

### 3.2 数据流

前端 → FastAPI API → 读/写 `config.ini` / `URL_config.ini` → `main.py` 主循环每轮热加载这些文件（已有逻辑，line 2141 重读 config；URL_config 每轮解析）→ 自动检测新增/注释/删除的 URL 并启停录制线程 → 状态变化反映到全局变量 → API 在 `record_state_lock` 下读取全局变量返回前端。

**关键洞察**：`main.py` 的主循环已内置配置热加载。Web 面板的“增删改查”只需编辑这两个文件，录制引擎会自动同步，无需额外的 IPC/事件机制。

### 3.3 状态访问

`main.py` 已有的全局状态（均受 `record_state_lock` 保护）：
- `recording: set` — 正在录制的直播间名集合
- `monitoring: int` — 正在监测的数量
- `running_list: list` — 正在运行的 URL 列表
- `recording_time_list: dict` — `{record_name: [start_time, quality]}`
- `error_count: int` — 当前错误计数

新增 `main.get_status()` 访问器在锁内一次性快照上述变量，供 API 调用，避免 API 直接触碰裸全局变量。

## 4. `main.py` 改动（最小化、安全）

仅以下改动，保持 `gui.py` 与命令行模式完全不变：

1. **包装主循环为 `main()` 函数**：将现有 `while True:` 循环（约 line 2133–2420，含配置读取与录制线程调度）整体包进 `def main() -> None:`，并在文件末尾加 `if __name__ == "__main__": main()` 守卫。函数内逻辑不变。
2. **新增 `get_status() -> dict`**：在 `record_state_lock` 下读取 `recording`/`monitoring`/`running_list`/`recording_time_list`/`error_count`，结合 `utils.check_disk_capacity()` 与启动时间，返回结构化状态快照。
3. **`input()` 非交互守卫**：当 `URL_config.ini` 为空时，原代码会 `input(...)` 阻塞。改为 `if sys.stdin.isatty(): input(...)`，非交互（web 模式）时跳过并继续循环，让 Web API 可后续添加 URL。
4. **暴露录制控制函数**：`start_record` 等已为模块级函数，`web.py` 可直接通过 `main.start_record` 调用。但默认走“编辑文件→主循环自动调度”路径，仅在需要立即生效时考虑直接调用（作为优化，非必需）。

文件级初始化代码（line 2066–2081 的 FFmpeg 检查、备份线程启动、去重等）保持在模块顶层，`import main` 时执行一次，作为录制引擎的就绪准备。

## 5. API 设计

所有 `/api/*` 路由（除 `/api/login`）在认证开启时要求 `Authorization: Bearer <token>` 头。

| 方法 | 路径 | 功能 | 请求/响应要点 |
|------|------|------|---------------|
| POST | `/api/login` | 密码登录 | req: `{password}` → resp: `{token, expires_in}` |
| GET  | `/api/status` | 状态快照 | resp: 监测数/录制数/录制列表(名/开始时间/画质/时长)/错误数/磁盘剩余/运行时间/版本 |
| GET  | `/api/status/stream` | SSE 实时状态 | `text/event-stream`，每 2s 推送一次 status JSON |
| GET  | `/api/rooms` | 列出直播间 | 解析 `URL_config.ini`，返回 `[{url, quality, name, enabled, recording}]` |
| POST | `/api/rooms` | 添加直播间 | req: `{url, quality?, name?}` → 追加一行到 URL_config.ini |
| PUT  | `/api/rooms` | 修改直播间 | req: `{old_url, url, quality, name}` → 用 `update_file` 替换该行 |
| DELETE | `/api/rooms` | 删除直播间 | query `?url=` → 用 `delete_line` 删除 |
| POST | `/api/rooms/toggle` | 启用/禁用 | req: `{url, enable}` → 注释/取消注释该行 |
| GET  | `/api/config` | 读取配置 | 返回 config.ini 各节键值；`Cookie`/`账号密码`/`Authorization` 中 value 非空时返回 `"***"` 脱敏 |
| PUT  | `/api/config` | 更新单个配置项 | req: `{section, key, value}` → `utils.update_config`。前端“保存”按钮对变更项逐个调用本接口（非批量） |
| GET  | `/api/files` | 浏览文件 | query `?path=`（相对 downloads 根）→ 返回子目录/文件列表（名/大小/类型/mtime） |
| GET  | `/api/files/download` | 下载文件 | query `?path=` → `FileResponse`；路径校验必须落在 downloads 内 |
| GET  | `/api/logs` | 读取日志 | query `?lines=200` → 返回日志文件末尾 N 行 |

### 5.1 URL_config.ini 解析/编辑规则（对齐 main.py）

- 行格式：`[画质,]URL[,主播: 名称]`，或 `#` 前缀表示注释（禁用）。
- 解析时复用 `main.py` 现有逻辑（split by `,`/`，`，识别画质关键词、`主播:` 前缀）。
- 编辑统一用 `main.update_file` / `main.delete_line`（已加 `file_update_lock`），与主循环并发安全。
- 添加：去重检查。去重前对 URL 做规范化（若不含 `://` 则补 `https://`，并去除 query string 中与 main.py `CLEAN_URL_HOST_LIST` 一致的部分），同 URL 已存在则返回 409。

## 6. 前端设计

### 6.1 页面结构

单页应用，顶部标签页导航 + 主内容区：

- **登录页**（认证开启且未登录时）：密码输入框 → POST `/api/login` → 存 token 到 localStorage。
- **仪表盘**：4 个状态卡片（监测数 / 录制数 / 错误数 / 磁盘剩余）+ 录制中列表表格（名称/画质/已录时长/开始时间）+ 实时日志流面板。用 `EventSource` 订阅 `/api/status/stream` 每 2s 刷新卡片与列表。
- **直播间管理**：顶部“添加”表单（URL + 画质下拉 + 名称）+ 表格列出所有直播间（URL/画质/名称/启用开关/编辑/删除）。增删改通过 fetch 调对应 API，操作后刷新列表。
- **配置**：分组表单（录制设置 / 推送配置 / Cookie / 账号密码 / Authorization），从 `/api/config` 加载，敏感字段以密码框显示，底部“保存”批量 PUT。
- **文件浏览**：以 `downloads/` 为根的列表视图，点击目录进入，点击文件显示信息 + 下载链接。显示大小/修改时间。

### 6.2 主题与品牌一致性

- 浅色/深色双主题，右上角切换按钮，存 localStorage。
- 配色对齐 `gui.py` 的 `Colors` 类：主色 `#4F6DF5`、成功 `#16A34A`、危险 `#DC2626`、警告 `#D97706`；浅色背景 `#F4F6FB`，深色 `#0F1117`。
- 终端日志区沿用 `#0D1117` 背景 + `#7DA7FF` 文本，错误红/警告黄。

### 6.3 交互细节

- 所有写操作显示 loading + toast 反馈。
- SSE 断连自动重连（EventSource 原生），重连后立即拉一次 `/api/status`。
- 删除/禁用直播间前确认对话框。

## 7. 认证（可选）

### 7.1 配置

`config.ini` 新增 `[Web]` 节：

```ini
[Web]
web_host = 0.0.0.0
web_port = 8000
web_auth_enable = false
web_password =
web_token_expiry = 86400
```

### 7.2 流程

- `web_auth_enable = false`：所有 API 直接放行（本地/内网场景）。
- `web_auth_enable = true`：
  - 未带有效 token 的 `/api/*` 请求（除 `/api/login`）返回 `401 Unauthorized`。
  - 前端跳登录页 → `POST /api/login {password}` → 比对 `web_password`（明文存配置，由用户自行保管）→ 成功则生成随机 token（`secrets.token_urlsafe(32)`），存内存字典 `{token: expiry_time}`，返回 `{token, expires_in}`。
  - 前端存 `localStorage['dlr_token']`，后续请求带 `Authorization: Bearer <token>`。
  - token 过期后清除；登录时清理已过期 token。
- 内存字典 + 简单比对即可，不做哈希/盐（单用户工具，YAGNI）。

## 8. 依赖

新增到 `requirements.txt` 与 `pyproject.toml`：

```
fastapi>=0.115.0
uvicorn[standard]>=0.30.0
python-multipart>=0.0.9
```

（`python-multipart` 用于表单/文件下载场景的兼容；FastAPI 的 `FileResponse` 不强依赖它，但保留以备未来表单上传。）

## 9. 边界与错误处理

- **路径穿越防护**：`/api/files` 与 `/api/files/download` 解析 `path` 参数后，用 `os.path.realpath` 解析，再校验 `os.path.commonpath([resolved, downloads_root]) == downloads_root`，否则 400。
- **并发写配置**：所有 config/URL_config 写入走 `main.update_config` / `main.update_file` / `main.delete_line`，复用现有 `file_update_lock`，避免与主循环并发损坏。
- **SSE 稳定性**：客户端 EventSource 断连自动重连；服务端生成器捕获异常并关闭。
- **引擎隔离**：录制引擎在守护线程运行，异常被 `main.py` 内部 `try/except` 捕获并记录，不影响 Web 服务进程。
- **空 URL_config 启动**：非交互模式下跳过 `input()`，主循环继续，等待 Web API 写入 URL。
- **认证关闭时的提示**：仪表盘不显示登录入口；前端根据 `/api/status` 是否 401 决定是否跳登录。

## 10. Docker / 部署

- `Dockerfile`：无需改基础镜像；`web.py` 与 `main.py` 共用同一镜像，启动命令 `python web.py`。
- `docker-compose.yaml`：新增 `ports: ["8000:8000"]`；默认 `command: python web.py`。若需切回命令行/GUI 模式，注释说明改 command 为 `python main.py` / `python gui.py`。
- 环境变量无新增。

## 11. 测试

`tests/test_web_api.py`，用 FastAPI `TestClient`（不启动真实 uvicorn，不启动真实录制引擎）：

- **rooms CRUD**：mock `URL_config.ini` 为临时文件，测添加/修改/删除/启用禁用/重复添加 409。
- **config 读写**：测 `/api/config` 返回结构与脱敏；`/api/config` PUT 写入后回读一致。
- **files 路径穿越**：测 `?path=../../etc/passwd` 返回 400；正常路径返回列表。
- **auth 流程**：开启认证时未带 token → 401；`/api/login` 错误密码 → 401；正确密码 → 200 + token；带 token 访问 → 200。
- **status**：mock `main.get_status` 返回固定值，测 `/api/status` 结构。

不测实际录制（依赖网络与平台），状态用 mock 注入。

## 12. 文件清单

| 文件 | 操作 | 说明 |
|------|------|------|
| `web.py` | 新增 | Web 模式入口 |
| `src/web_api.py` | 新增 | FastAPI 应用、路由、认证 |
| `web/index.html` | 新增 | 前端单页 |
| `web/app.js` | 新增 | 前端逻辑 |
| `web/style.css` | 新增 | 样式（浅/深主题） |
| `main.py` | 修改 | 包装 `main()` + `get_status()` + input 守卫 |
| `config/config.ini` | 修改 | 新增 `[Web]` 节 |
| `requirements.txt` | 修改 | 加 fastapi/uvicorn/python-multipart |
| `pyproject.toml` | 修改 | 同上依赖 |
| `Dockerfile` | 修改 | （可选）默认入口或文档说明 |
| `docker-compose.yaml` | 修改 | 暴露 8000 端口 |
| `tests/test_web_api.py` | 新增 | API 测试 |
| `README.md` | 修改 | 新增 Web 模式使用说明（小节） |

## 13. 开放问题（已解决，记录决策）

- **是否需要实时控制录制启停（绕过文件热加载）？** 否。文件热加载已足够（主循环每轮重读），保持单一真相源，避免双路径状态不一致。`toggle`/`add`/`delete` 通过编辑文件实现，延迟 ≤ `delay_default` 秒（默认 300s，可配置更低）。
- **认证密码是否哈希？** 否，明文存 config.ini（与现有 Cookie/密码同等敏感度），由用户保管配置文件权限。
- **是否支持多用户？** 否，单密码登录，YAGNI。
