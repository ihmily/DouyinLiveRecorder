# PROPOSAL：GUI / Web 界面现代化升级与框架替换

> 状态：**待评审**（设计已定方向：GUI 走「原生 ttk + 自研 UI Kit」，分阶段推进、每阶段独立验证）
> 日期：2026-09-29
> 范围：`web/`（前端动效）、`src/web_api.py` + `web.py`（后端框架）、`gui.py`（主题与控件层）、依赖清单与打包配置
> 不在范围内：录制引擎、平台解析、调度器、弹幕、日志归档、API 契约、配置键语义、i18n 键集

---

## 1. 背景与目标

三项诉求：

1. **Web**：功能 / 页面结构 / 路由不变的前提下，增加克制的 JS 动效（滚动入场、悬停反馈、过渡、视差与轻量粒子背景），保证首屏、移动端流畅度与可访问性。
2. **GUI**：多套统一主题（至少浅色 + 深色），运行时一键切换 + 偏好持久化，对比度达标，控件 hover / selected / disabled 表现一致。
3. **框架替换**：评估 GUI 与 Web 现状瓶颈，换成更高性能方案，同时保持接口、数据结构与业务逻辑兼容。

成功标准（可机检）：

- 现有前端回归锁 `tests/frontend/*.mjs` 全绿，且新增动效专项锁。
- 24 条路由的契约（path / method / 请求字段 / 响应键 / 状态码）改造前后逐字节一致，由黄金快照锁住。
- GUI 主题每套的 token 对比度机检通过（正文 ≥ 4.5:1，大字与非文本 ≥ 3:1）。
- `import gui` 在无头 Linux CI 仍成功；`python build_exe.py --smoke` 三入口通过。

---

## 2. 现状评估（代码事实）

| 面 | 现状 | 实测 / 代码事实 |
| --- | --- | --- |
| Web 前端 | 原生 JS IIFE，无框架无构建 | `web/app.js` 1868 行、`web/style.css` 506 行、`web/index.html` 175 行；已有亮/暗主题（`body[data-theme]` + `safeGetItem` 持久化）、四语内嵌目录、SSE 轮询；**零动效** |
| Web 后端 | FastAPI + uvicorn | 24 条路由、10 个 `BaseModel`、`HTTPException` 34 处、`Query(ge/le)` 5 处、`StaticFiles` mount 1 处；**无 `Depends`、无 OpenAPI / docs 定制** |
| GUI | CustomTkinter | `gui.py` 3884 行、`ctk.*` 调用 158 处；画质/弹幕表每轮 `destroy` + 重建（AGENTS.md「已知坑」6.2 已记录闪烁与点击落空） |
| 测试耦合 | 前端 vm 沙箱、GUI 模块级导入 | `tests/frontend/test_quality_ui.mjs` 直接断言 `tbody.innerHTML` 片段；`tests/test_gui_monitor.py` 模块级 `import gui` |
| 打包 | PyInstaller | `build_exe.py` 有 `collect_data_files('customtkinter')`；AGENTS.md 记录 `pydantic_core` 4.93MB、Tcl/Tk 5.28MB 为固定成本 |

**瓶颈判断**

- Web 前端的瓶颈不是框架（原生 JS 本就快），而是**全量 `innerHTML` 重建**（日志流、房间表）——本次动效不得加重它。
- 后端 FastAPI 在本仓只剩「请求体校验 + 自动 OpenAPI」两个用途，而 OpenAPI 并未对外暴露；换来的代价是 `pydantic_core` 约 4.93MB 打包体积与冷启动开销。
- GUI 的瓶颈是 CustomTkinter 的 **Canvas 重绘控件模型**：每个 `CTkButton` / `CTkFrame` 都是带圆角的 Canvas，控件一多、一刷新就掉帧；且 CTk 没有统一的 disabled / hover 状态机制，正好与诉求 2 冲突。

---

## 3. 框架选型与理由

### 3.1 Web 后端：FastAPI → Starlette 直路由 + 自研校验层

**选型**：`src/web_api.py` 改为 `starlette.applications.Starlette` 显式路由表；新增 `src/web_models.py`（`dataclass` + 显式 `parse_*`）替换 10 个 `BaseModel`；`HTTPException` 换自有 `ApiError` + 全局 exception handler。

**理由**：

- 本仓只用到 FastAPI 的校验能力（无 `Depends`、无依赖注入、无 OpenAPI 定制），替换面收窄到「路由注册 + 请求解析 + 异常响应」三处。
- Starlette 已是 fastapi 的传递依赖，替换后依赖树更浅、运行时面更小（少一个编译型二进制，减少 CVE 暴露面）。
- 可移除 `fastapi` 与 `pydantic` 两条运行时依赖 → 打包体积下降（量级以 `scripts/report_bundle_size.py` 实跑为准，禁止估算）。
- 兼容性由**黄金快照**兜底：改造前后各抓一份「路由 path + method + 响应键集合」比对。

**备选与为什么不选**：

- 保留 FastAPI：风险最低，但不满足「替换框架」诉求，且体积与依赖面原地保留。
- Litestar / BlackSheep：性能略优，但中间件、依赖注入、异常体系要重写，收益不成比例。
- 只换 ASGI server（uvicorn → granian）：吞度略有提升，但 `web.py` 依赖 `server.should_exit` 做托盘优雅退出与 ffmpeg 清理，重写风险集中在关停路径上，收益最小。

### 3.2 Web 前端动效：原生 JS + CSS，零依赖

**选型**：新增 `web/motion.js`（IIFE，挂载 `window.__dlrMotion`），配合 `web/style.css` 的动效 token。

**理由**：现有前端就是原生 JS 无构建，引入 GSAP / three.js 会为几段过渡付出几十 KB 与首屏成本；IntersectionObserver + CSS transition + 单 canvas 粒子已能覆盖全部诉求。

### 3.3 GUI 控件层：保留 Tk 内核，CustomTkinter → `tkinter.ttk` + 自研 UI Kit

**选型**：新增 `src/ui_kit.py`（CTk 兼容工厂，签名对齐 CustomTkinter，内部映射 ttk / tk 原生控件）。

**理由**：

- ttk 由原生主题引擎绘制，创建与重绘成本比 CTk 的 Canvas 重绘低一个量级。
- `ttk.Treeview` 支持行级增量更新，从根上消灭「每轮 destroy + 重建」造成的闪烁与点击落空。
- `ttk.Style.map()` 原生支持 `hover / active / selected / disabled / readonly` 状态映射，正是诉求 2「状态表现清晰一致」的机制性答案（CTk 没有）。
- 可移除 `customtkinter` 运行时依赖，Tcl/Tk 本就在打包体积内（5.28MB），不新增运行时。`import gui` 只 import tkinter，无头 CI 不受影响。

**备选与为什么不选**：

- ttkbootstrap：同为 ttk 底座、省样式代码，但多一层依赖，且主题切换需重建 style，对比度与状态色不如自研可控。
- PySide6 / Qt：观感与性能上限最高，代价是 +50MB 体积、LGPL 合规、3884 行近乎重写、CI 无头导入风险。**已由用户确认不走此路**。
- 只加主题层不动控件：风险最小，但性能瓶颈原地保留。

### 3.4 GUI 主题层：自研 `ThemeManager`

**选型**：新增 `src/ui_theme.py`——语义 token + `ttk.Style` 主题注册 + 持久化读写 + 对比度自证函数。

**理由**：token 化后对比度可以**机检**（WCAG 相对亮度公式），多套主题由同一组语义槽位派生，避免「每套主题各写一遍颜色」的漂移。

---

## 4. 兼容性契约（改造前后必须逐字不变）

| 项 | 承诺 |
| --- | --- |
| API 契约 | 24 条路由的 path / method / 请求体字段 / 响应 JSON 键 / 状态码 / `detail` 错误结构不变（前端 `apiError()` 依赖 `detail`） |
| GUI 对外面 | `LiveRecorderGUI` / `SystemTray` / `AdvancedSettingsWindow` / `Colors` / `Fonts` / `_quality_alert_expired` 等被测直接引用的符号与签名不变 |
| 无头导入 | `import gui` 在 Linux CI 仍成功（ttk 只 import tkinter，不建窗） |
| 业务与数据结构 | `main.py` 录制链、`src/web_config.py`、调度器、弹幕、日志归档一行不动 |
| 前端 DOM | 动效只加 class / 属性，**不插入包裹元素**——`test_quality_ui.mjs` 断言 `tbody.innerHTML` 片段 |
| 配置与 i18n | config.ini 键名与布尔解析口径不变；GUI 主题键避开 `=` / `:`；新增文案同步 i18n 四目录 + `web/app.js` 五处 |

**已知会被撞到的既有门禁**（须同批改，不为门禁绿而绕过）：`tests/test_regression_2026_09_22_gates.py` 的「运行时依赖 23 条包名集合逐项相等」锁——移除 `fastapi` / `pydantic` / `customtkinter` 后该锁需同步更新，并随改动提交理由。

---

## 5. 架构设计

```
web/
  index.html      不动结构，仅给静态容器加 data-reveal / 追加 <canvas id="bg-canvas">
  style.css       新增 --motion-* token、@media (prefers-reduced-motion: reduce) 全覆盖
  app.js          不动渲染出的 HTML 结构；仅在启动末尾调用 __dlrMotion.init()
  motion.js       【新增】入场 / 悬停 / 过渡 / 视差 / 粒子，单一 rAF，统一降级闸门

src/
  web_models.py   【新增】dataclass + parse_*，422 结构对齐 FastAPI
  web_api.py      【改造】Starlette 显式路由表 + ApiError + 全局 handler
  ui_theme.py     【新增】ThemeManager（token / 多主题 / 切换 / 持久化 / 对比度自证）
  ui_kit.py       【新增】CTk 兼容工厂（ttk 映射 + Treeview 增量更新）
gui.py            【改造】逐页把 ctk.* 换成 ui_kit.*；Colors / Fonts 保留为门面
```

### 5.1 motion.js 设计要点

- **入场**：`IntersectionObserver`（threshold 0.15、`rootMargin: 0 0 -8% 0`），命中加 `.is-revealed` 并一次性 `unobserve`；错峰 `delay = min(index * 40, 240)` ms。只作用于 `index.html` 的静态节点（`[data-reveal]`、`.panel`、`.stat-card`），**动态渲染的 `tbody` 行不参与**，避免污染前端回归锁的 innerHTML 断言。
- **悬停 / 焦点**：纯 CSS `:hover` / `:focus-visible`，只动 `transform` / `opacity` / `border-color` / `box-shadow`，禁止触发布局的属性。
- **过渡**：视图切换 `opacity + translateY(6px)` 160ms；toast 进出；表格**新增行** 200ms 淡入（不重建 innerHTML）。
- **视差 + 粒子**：单 `<canvas id="bg-canvas">`（`aria-hidden="true"`、`pointer-events:none`、z-index -1）；粒子数 `clamp(18, floor(视口面积 / 22000), 64)`；DPR 上限 2；单一 rAF 循环；`document.hidden` 暂停；视口 < 768px 或 `hardwareConcurrency <= 4` 时粒子数减半。
- **可访问性闸门**：`prefers-reduced-motion: reduce` → 不创建 canvas、全部动效时长归零；不动任何 `role` / `aria-live`。
- **性能预算**：`motion.js` ≤ 8KB（未压缩）、`defer` 加载不阻塞首屏、单 rAF 实例、读写分离避免 layout thrash、`destroy()` 后无残留定时器。

### 5.2 ui_theme.py 设计要点

- 语义槽位：`surface` / `surface_alt` / `border` / `text` / `text_muted` / `primary` / `primary_hover` / `success` / `danger` / `warning` / `disabled_bg` / `disabled_fg`。
- 主题：至少 `light` / `dark` 两套，可扩展 `midnight` / `high_contrast`；经 `ttk.Style.theme_create/theme_use` 注册。
- 三态一致：`style.map()` 统一声明 `hover` / `active` / `selected` / `disabled` / `readonly` 的 background / foreground / bordercolor。
- 持久化：`config.ini [GUI] gui_theme`，经既有 `config_io` 读写（键名无 `=` / `:`）。
- 对比度自证：`contrast_ratio(fg, bg)` 实现 WCAG 相对亮度，供用例机检。

### 5.3 ui_kit.py 设计要点

- 工厂签名对齐 CTk：`Button(master, text=, command=, width=, height=, fg_color=, hover_color=, state=)` 等。
- 映射：`CTkFrame/ScrollableFrame → ttk.Frame(+Scrollbar)`、`CTkLabel → ttk.Label`、`CTkButton → ttk.Button`、`CTkEntry → ttk.Entry`、`CTkOptionMenu → ttk.Combobox`、`CTkTextbox → tk.Text`、`CTkTabview → ttk.Notebook`、监控表格 → `ttk.Treeview`（行级 `item()` 增量更新）。
- `Colors` / `Fonts` 保留为 token 门面，供外部与测试继续引用。

---

## 6. 分步迁移计划

| 阶段 | 目标 | 主要改动 | 验证 | 回滚粒度 |
| --- | --- | --- | --- | --- |
| **0 基线取证** | 拿到可比对的改造前读数 | 一次性测量脚本（跑完即删）：API P50/P95、首屏资源字节数、GUI 建窗与表格刷新耗时、`scripts/report_bundle_size.py` | 同脚本改造后复跑对比 | 无（只读） |
| **1 前端动效** | 动效四件套落地 | 新增 `web/motion.js`、`style.css` 增动效 token、`index.html` 加 canvas 与 `data-reveal` | `node --check web/motion.js`；`node --test tests/frontend/`（现有 2 个 .mjs 必须仍全绿）；新增 `tests/frontend/test_motion.mjs` | 删一个 script 标签即还原 |
| **2 后端换框架** | FastAPI → Starlette | 新增 `src/web_models.py`；`web_api.py` 改显式路由表 + `ApiError` + handler；依赖清单去 `fastapi` / `pydantic` 并跑 `sync_metadata.py` | **先抓改造前路由黄金快照**，改造后比对；`pytest tests/test_web_api.py`；新增 `tests/test_web_api_routes.py` | 逐路由回退 |
| **3 GUI 主题层** | 多主题 + 切换 + 持久化 | 新增 `src/ui_theme.py`；`gui.py` 接主题菜单与持久化 | 新增 `tests/test_ui_theme.py`：每套主题每个前景/背景 token 对的对比度机检；切换幂等；持久化读写 | 独立模块，可整体摘除 |
| **4 GUI 控件层** | CTk → ttk | 新增 `src/ui_kit.py`；按 控制台 → 画质监控 → 弹幕监控 → URL 配置 → 运行日志 → 高级设置 逐页替换 | 每批：`py_compile`（3.14）+ `node --test` 不受影响 + GUI 冒烟；表格改 Treeview 后重点验「不再闪烁、点击不落空」 | 逐页回退 |
| **5 收尾** | 依赖 / 打包 / 文档 | `requirements.txt` + `pyproject.toml` + 依赖集合回归锁；`build_exe.py` 的 `collect_data_files('customtkinter')` 与排除项；CODE_WIKI 中英更新日志；AGENTS.md 坑位 | `python scripts/run_gates.py`；`pytest`（0 警告）；`build_exe.py --smoke` | 按 commit |

**每阶段完成判据**：改动文件清单 + 门禁实测输出 + 清理结果 + 本阶段假设与回滚方式，逐阶段交付给你确认后再进入下一阶段。

---

## 7. 风险与对策

| 风险 | 对策 |
| --- | --- |
| 动效破坏前端回归锁（innerHTML 断言） | 动效只加 class，不插元素；动态渲染的表格行不参与入场；`node --test tests/frontend/` 每阶段必跑 |
| 后端换框架导致响应结构漂移 | 改造前先抓路由黄金快照，改造后逐字节比对；`detail` 结构对齐 FastAPI 422 |
| GUI 逐页替换期间半新半旧 | UI Kit 与 CTk 可共存（都是 Tk 控件树），按页切换，任一页可单独回退 |
| 移除依赖撞既有回归锁 | 同步改锁并在提交信息写明理由；不改用「绕过门禁」的方式 |
| 打包体积变化 | 只以 `scripts/report_bundle_size.py` 实跑读数为准，禁止估算 |
| 本机无 venv 导致验证不全 | 见第 8 节；在环境恢复前只交付静态可验证部分 |

---

## 8. 环境前提（当前阻塞点）

本机当前 `.venv` 不存在，`customtkinter` / `fastapi` / `pydantic` / `starlette` / `uvicorn` / `pytest` / `PIL` / `pystray` 全部 `ModuleNotFoundError`。可用能力：

- 系统 Python **3.14.7**（`py_compile`、AST 校验）— 已确认
- `tkinter` **Tk 9.0** 可用（系统 3.14）— 已确认
- Node **v22.22.2**（`node --check` / `node --test tests/frontend/`）— 已确认

**阶段 0 / 2 / 3 / 4 的 pytest 与 mypy 门禁需要你先在普通终端执行 `pip install -r requirements.txt` 恢复环境**（沙箱内批量装包有卸载后拦截的风险，按 AGENTS.md 规定交回用户执行）。阶段 1 的前端动效不依赖 Python 环境，可现在就做完并完整验证。

---

## 9. 假设（待确认）

1. 假设 OpenAPI / `/docs` 与 `/redoc` 对外无用——代码里未见任何定制与暴露配置；若你依赖交互文档，阶段 2 需保留等价替代。
2. 假设 `[GUI]` 节可作为主题持久化的落点（与现有 `[录制设置]` / `[Web]` 同构）；若你更希望落 `gui_theme.json` 之类独立文件，需同步 `.gitignore` 与 `.dockerignore`（凭据红线同族的防线）。
3. 假设「多套主题」的初始交付为 `light` / `dark` / `high_contrast` 三套；配色风格沿用现有 `Colors` 的品牌蓝 `#4F6DF5`。
4. 假设阶段 0 的基线测量脚本属于一次性产物，跑完即删（AGENTS.md 铁律 1）。
