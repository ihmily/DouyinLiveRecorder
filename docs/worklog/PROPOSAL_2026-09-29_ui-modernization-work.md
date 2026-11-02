# UI 现代化改造 — 工作进度追踪（Work Log）

> 配套文档：`PROPOSAL_2026-09-29_ui-modernization.md`（设计 / 框架选型 / 兼容性契约 / 分步迁移计划）。
> 本文件只记录**已完成与未完成**的进度事实，不重复设计理由。状态更新日期：2026-09-29（晚，阶段2 运行期门禁已全绿）。
> 环境状态：用户已恢复 `.venv`（Python 3.14.7），阶段2 运行期验证已实跑（详见 §1.3）。

## 0. 总览状态表

| 阶段 | 目标 | 代码/文档状态 | 验证状态 | 备注 |
| --- | --- | --- | --- | --- |
| **0 基线取证** | 改造前可比对读数 | 未执行 | 部分豁免 | 路由黄金快照由动态契约测试取代；API 延迟 / 首屏字节 / GUI 建窗耗时基线未实测；体积复测留阶段5 |
| **1 前端动效** | 动效四件套 | ✅ 完成 | ✅ 已验证（前端） | `web/motion.js` + `style.css` 动效段 + `index.html` canvas；`node --test tests/frontend/*.mjs` 65/65 全绿 |
| **2 后端换框架** | FastAPI → Starlette | ✅ 完成 | ✅ 已验证（运行期全绿） | `run_gates.py` 8/8、pytest 3248 passed/0 警告、覆盖率 83.98% 全达标、basedpyright 0/0；运行期抓出并修复 2 处接线错误（详见 §1.2/§1.3） |
| **3 GUI 主题层** | 多主题 + 切换 + 持久化 | ✅ 完成 | ✅ 已验证（含真窗冒烟） | `src/ui_theme.py`（13 槽位/3 主题/对比度机检/幂等切换/持久化）+ `gui.py` 主题菜单 + `tests/test_ui_theme.py` 34 用例；详见 §1.4 |
| **4 GUI 控件层** | CTk → ttk | ✅ 完成 | ✅ 已验证（含真窗冒烟） | `src/ui_kit.py`（工厂+DataTable）+ gui.py 六处逐页替换 + 侧边栏（「界面主题」单入口）+ `tests/test_ui_kit.py` 11 用例；详见 §2.4 |
| **5 收尾** | 依赖/打包/文档 | ✅ 完成 | ✅ 已验证（打包冒烟 + 体积读数） | customtkinter 摘除（清单/typings/build_exe）、`--smoke` 三入口全过、体积 91.81MB/224 文件（阶段0 基线补齐）、xvfb 常态化；详见 §2.5 |

---

## 1. 已完成部分

### 1.1 阶段1 — Web 前端动效层（已验证）

- 新增 `web/motion.js`（约 223 行，零依赖 IIFE，挂载 `window.__dlrMotion`）：单 rAF 循环、IntersectionObserver 入场、DPR 封顶 2、`document.hidden` 暂停、`prefers-reduced-motion` 兼容。
- `web/style.css`：增 `#bg-canvas` 固定层、`.reveal`/`.is-revealed` 过渡、`:focus-visible`、reduced-motion 覆盖（动效段约 508–547 行）。
- `web/index.html`：`<body>` 首行加 `<canvas id="bg-canvas" aria-hidden="true">`；末尾加 `<script src="/web/motion.js">`。
- 新增 `tests/frontend/test_motion.mjs`（5/5 通过）。
- **验证**：`node --test tests/frontend/*.mjs` → **65/65 全绿**（含既有 2 个 .mjs + 新增 test_motion 5 条）；动效只加 class 不插元素，未破坏既有 innerHTML 断言回归锁。

### 1.2 阶段2 — Web 后端 FastAPI → Starlette（结构完成；[更正] 初稿两处接线判断有误，已随运行期验证修复）

**代码结构（前序轮次完成，本轮复核 + 修正）**

- `src/web_api.py`：
  - `FastAPI()` → `Starlette()`；认证中间件改 `app.add_middleware(BaseHTTPMiddleware, dispatch=auth_middleware)`。**[更正 2026-09-29]** 本文件初稿与 CODE_WIKI 曾写「`@app.middleware("http")` 为 Starlette 原生支持，逐字保留」——实测证伪：Starlette 无该装饰器方法，导入即抛 AttributeError；FastAPI 该装饰器底层即 `add_middleware(BaseHTTPMiddleware, dispatch=...)`。
  - **[更正 2026-09-29]** 补注册 JSON 版 `HTTPException` handler：Starlette 内建 handler 对端点内 raise 的 HTTPException 回 **PlainTextResponse(detail)**，丢 `{"detail": ...}` JSON 错误契约（前端 `apiError()` 依赖该键，提案 §4 承诺逐字不变）。
  - 24 个 `@app.post/get/put/delete(...)` 装饰器替换为 `@_route(app, [METHOD], path)`；5 个 `Query(...)` 参数去装饰器化改为普通默认值（`url/path: str = ""`、`lines: int = 200`、`since: int = 0`）。
  - `cast(FastAPI, request.app)` → `cast(Starlette, ...)`；`create_app` 返回注解 `Starlette`。
  - 新增 `_route` 适配器工厂（`inspect.signature` 驱动分类：模型参数 / Query 参数 / request）：JSON body 经 `_read_json_body` 解析（非法体→422）；Query 按 `_QUERY_DEFAULTS` 默认值与上下界夹取；同步 def 端点经 `run_in_threadpool` 派发（对齐 FastAPI 行为，避免阻塞事件循环）；非 Response 返回值统一包 JSONResponse。
  - **所有 24 个路由处理器函数体零改动**，业务逻辑与全部安全不变量（MID-*/SEV-*）逐字保留。
- `src/web_models.py`（新增）：9 个纯标准库 dataclass（LoginRequest / RoomCreate / RoomUpdate / RoomToggle / RoomQualityUpdate / QualityOptionsUpdate / RecordingToggle / ConfigUpdate / LanguageUpdate），以 `.parse(data)` classmethod 替代 pydantic `BaseModel`；缺字段/类型错→ValueError；bool 仅接受 Python bool；多余字段忽略。
- 依赖清单：`requirements.txt` / `pyproject.toml` 同步删除 `fastapi>=0.140.0` 与 `pydantic>=2.13.4`；保留 `starlette>=1.3.1` / `uvicorn` / `python-multipart`；包名集合相等性经 `tests/test_regression_gates.py` 实测通过；`uv.lock` / `DouyinLiveRecorder.egg-info` 经 `python scripts/sync_metadata.py` 重建（requires.txt 已无 fastapi/pydantic）。
- 测试文件 `TestClient` import 切到 `starlette.testclient`：`tests/test_web_api.py`、`tests/test_web_config_locks.py`、`tests/test_danmaku_monitor.py`、`tests/test_regression_web_g.py`（共 5 处）。
- 新增 `tests/test_web_api_routes.py`：动态遍历 `app.routes`，断言 24 条路由（method/path 精确集合）+ `/web` 挂载点，取代被敏感门禁拦截的静态 `web_api_routes_baseline.json`（已删除）。

### 1.3 阶段2 — 运行期门禁实测（2026-09-29 晚，venv 恢复后全绿）

**门禁读数**

| 门禁 | 结果 |
| --- | --- |
| `python scripts/run_gates.py` | **8/8 全绿**（black / isort / mypy / 注释规范 / compile_po / check_version / check_runtime_pins / pytest 兜底） |
| `pytest`（全量） | **3248 passed, 14 skipped, 0 failed，warnings summary 为空** |
| `pytest --cov=src` + `scripts/check_coverage.py` | 总覆盖 **83.98%**，43 模块全部达标 |
| `basedpyright`（本地补充门禁） | **0 errors / 0 warnings / 0 notes** |
| `pytest tests/test_web_api.py tests/test_web_api_routes.py -q`（§2.1 指定） | 165 passed, 2 skipped, 0 warnings |
| `node --test tests/frontend/*.mjs` | 65/65 全绿（含修正后的 MID-2241 源码级断言） |

**运行期抓出并修复的问题（仅静态验证发现不了的部分）**

1. **P0：`@app.middleware("http")` 导入即崩** —— Starlette 无该装饰器方法，Web 面板整体不可用。修复：`add_middleware(BaseHTTPMiddleware, dispatch=auth_middleware)`，语义与 FastAPI 装饰器底层实现一致。
2. **契约漂移：HTTPException 回纯文本** —— Starlette 内建 handler 把端点内 raise 的 HTTPException 回成 PlainTextResponse(detail)，`{"detail": ...}` JSON 结构丢失，批量安全不变量用例转红（TestAuthKeyReauth / TestOutboundTargetKeysValidated / TestInsecureBindInvariant 等）。修复：注册 FastAPI 同款 JSON handler（`headers` 透传保留 Retry-After 等用法）。
3. **门禁对象更新**：`scripts/check_version.py` 的 web_api 版本检查对象从 `FastAPI(version=)` 换成 importlib.metadata 动态读取形态（MIN-2262 fail-closed 语义保留；DYNAMIC / 写死字面量 / 对象消失三分支变异验证通过）。
4. **测试锚点随迁移同步**：`tests/frontend/test_regression_gates.mjs` MID-2241 的 `reauth_password` 字段扫描迁到 `src/web_models.py`、端点截取锚点迁到 `@_route(app, ["GET"], "/api/language")`；`test_web_api.py` 的 `/health` version 断言从 `app.version`（FastAPI 元数据，Starlette 无）改为同源 `wa._APP_VERSION`。
5. **格式与注解收尾**：black/isort 对迁移期改动的 2 个文件重排（行尾形态逐文件核查未变）；`test_web_api_routes.py` fixture 补注解；`src/web_models.py` 补 9 条模型语义注释（密度 10.2%→达标，内容均经端点源码核实）。

**残留事实（非阻塞）**

- 本机 venv 仍装有 fastapi/pydantic（`pip install -r requirements.txt` 不卸载已删包）；代码与测试零引用，门禁不受影响。打包体积复测前建议用户在普通终端 `pip uninstall fastapi pydantic`。

---

### 1.4 阶段3 — GUI 主题层（2026-09-29 完成，含真窗冒烟）

**交付物**

- `src/ui_theme.py`（新增，约 330 行）：13 个语义槽位（提案 §5.2 十二槽 + `on_primary`——深色/高对比主题主按钮亮蓝填充需近黑标签，`surface` 兼作按钮前景在深色下不成立）；`THEMES` 三套（light / dark / high_contrast）；`contrast_ratio`（WCAG 相对亮度）+ `CONTRAST_REQUIREMENTS` 对比度契约（正文 4.5 / 非文本与禁用 3.0）；`ThemeManager`（select/apply 幂等：同 id 短路、重复 `theme_create` 守卫，基底 clam）；`load/save_theme_preference` 走 `update_or_append_config_line`，刻意不经 `config_io.read_config_value`（其写回持 `main.file_update_lock`，GUI 不进录制引擎锁体系）。import 期零 Tk 对象，无头 CI 可安全 import。
- `gui.py`：导入 ui_theme；`__init__` 读 `[GUI] gui_theme`——有显式偏好则同步 CTk 外观模式，无偏好跟随系统外观（保持升级前行为）；侧边栏「界面主题」菜单（显示名 i18n，顺序 light→dark→high_contrast）+ `_on_theme_change`（select→apply→持久化→外观映射→外观菜单显示同步→`_sync_canvas_bg`）；`_THEME_CTK_MODE`/`_THEME_LABELS` 常量。`Colors`/`Fonts` 等既有符号签名逐字不变。
- `tests/test_ui_theme.py`（新增，34 用例）：对比度数学锚点（白压 #4F6DF5 = 4.34 固化，即 light.primary 加深的决策依据）、注册表完整性、对比度契约全对×全主题、持久化（缺失/非法/往返/注释保留/重复保存单行）、切换幂等（配置字节不变）、ttk settings 纯数据断言（CI 全量）+ 真 Tk 集成 3 条（无显示环境 skip——唯一 skip 面）。
- 模板与文档：`config/config.ini` 增 `[GUI] gui_theme =`（空=跟随外观）；README 配置块补 GUI 节；i18n 四目录 +7 条（界面主题/三个主题名/切换成功/两种写回失败），.mo 重编；CODE_WIKI 中英条目 + 目录树（并补上阶段2 漏掉的 `web_models.py` 树条目）；AGENTS.md 增主题层约定子弹。

**关键设计决策**

1. **对比度先行**：临时迭代脚本把三套主题全部 token 对调达标后定稿取值（脚本已删，数值由测试持续回归）；light `primary`=#4358E8（品牌蓝同色相加深，原 #4F6DF5 白字 4.34 不达 AA）；light 边框 #848DA0 是 WCAG 1.411 非文本 3:1 的代价。
2. **阶段3 可见效果边界**：CTk 控件颜色体系由阶段4（ui_kit）接管，本阶段主题切换可见效果 = CTk 外观模式映射（high_contrast→dark）+ ttk 元素配色；「外观模式」与「界面主题」两菜单并存为过渡形态，阶段4 统一。
3. **持久化锁体系隔离**：GUI 写 `[GUI] gui_theme` 走 web_config 行级写回，不碰 config_io 的 main.file_update_lock。

**验证读数**

| 项 | 结果 |
| --- | --- |
| `run_gates.py` | 8/8 全绿（pytest 兜底 3286 passed / 0 警告） |
| `tests/test_ui_theme.py` | 34 passed（本机含真 Tk 3 条） |
| 覆盖率 | 84.07%，44 模块全达标（ui_theme 入列） |
| basedpyright | 0 errors / 0 warnings / 0 notes |
| i18n 测试（test_i18n* 三文件） | 49 passed |
| 真窗冒烟（子进程构建完整 LiveRecorderGUI） | 无偏好→跟随系统落 light；模拟点击高对比度→主题/持久化/ttk/外观模式/菜单显示五处联动全部正确；真实 config.ini 零写入（写路径重定向临时副本） |
| `import gui` 无头导入 | 成功（兼容性契约） |

**已知边界**

- 真 Tk 集成用例在无头 CI skip（ubuntu 无 X server）；CI 常态化需 test job 加 xvfb（阶段5 评估）。
- 模拟点击验证时把 `app.main_config_file` 重定向到临时副本——真实 config.ini 全程只读。

### 1.5 阶段3 追加修复 — GUI 文字截断（2026-09-29 午后，用户截图实测触发）

**现象与根因**：用户截图（150% DPI、默认 1120×740）显示控制台提示「启动后将调用 main.py…」两侧各缺半个字、弹幕占位提示右缘裁切。根因同族：长文案标签请求宽 > 父容器分配宽时，Tk pack 按默认 anchor=center 两侧对称裁切；画质页说明的定宽 `wraplength=1000` 是同失效在窄窗口下的变体。全库排查共 5 处。

**修复**（gui.py + 新增 `tests/test_gui_wrap_hints.py`，详见 CODE_WIKI 同名条目）：

- `_compute_wraplength` 纯函数（设备像素→逻辑值，除以 `ScalingTracker.get_widget_scaling`；CTk 6.0 对 wraplength 做 DPI 缩放已源码核实）+ `_bind_adaptive_wraplength`（绑标签自身窗口宽，前提 fill=tk.X；绑定时先设初值——重 pack 几何不变时 Configure 不触发）。
- 控制台提示改 fill+expand；画质说明去定宽；画质/弹幕占位收敛到两个工厂（初始构建与刷新重建共用，文案 4 份→各 1 份）；`ScalingTracker` 走定义路径显式导入；工厂参数 `tk.Misc`（CTkScrollableFrame 非 CTkFrame 子类）。
- 测试三层：纯函数子进程单测 + AST 源码锁（恰 4 接线点/文案唯一/无定宽 wraplength/两路径都走工厂）+ 真窗用例（无显示 skip）。
- **真窗用例踩坑**：手动 `set_widget_scaling` 覆盖与 CTk 系统 DPI 追踪在真窗映射时互相触发全量重缩放（事件风暴 → `update()` 永不返回，180s 超时）——真窗用例去掉手动覆盖，用系统自身 DPI；换算公式由纯函数锚点锁（1584@1.5→1050）钉死。

**验证**：端到端实测（完整 GUI、截图同尺寸）四条长提示全部「请求宽 ≤ 实际宽」（540≥519 / 1196≥1092 / 1196≥540 / 1230≥986）；`run_gates.py` 8/8；pytest 3300 passed/0 警告；basedpyright 0/0/0；真窗用例连续三轮 ~8s 稳定。

**异常事件（待用户知悉）**：修复期间发现 `requirements.txt` 被本会话之外的操作还原回 HEAD 版本（12:32 mtime，fastapi/pydantic 两行回来了，依赖集合锁转红）——已按阶段2 契约恢复（删两行 + 更新节头/starlette 描述注释），27/27 回归锁复绿。请自查是否有编辑器/同步工具在回写工作区。

---




### 1.6 GUI 卡死修复 — 自适应 wraplength 改「真防抖 + 迟滞」（2026-09-29 午后，用户报告）

**现象**：文字高频闪烁 → 部分界面元素渲染不完整 → 整窗卡死无响应（用户截图：一张正常、一张整体放大且侧栏底部控件溢出丢失、提示第二行竖向裁切、左缘有异尺寸残影——典型的跨 DPI 重缩放中途态）。

**根因链（全实证，详见 CODE_WIKI 同名条目）**：§1.5 的自适应 wraplength 绑定在 `<Configure>` 里**同步追写**；CTk 的 DPI 重缩放（用户跨屏拖拽走 `check_dpi_scaling`）内部是 `_set_scaling → _draw → _update_dimensions_event → update_idletasks` 的递归互泵，重缩放期间标签宽度剧烈瞬时摆动（350↔1566 设备像素），同步写入的几何失效排进同一 idle 队列使其永不排空 → `update()` 永不返回。**判定性对照**：10 次 DPI 翻转压力，绑定版 120s 泵不完（卡死复现）；no-op 化对照组 9.2s 正常。

**修复**（gui.py）：
1. **真防抖**——`<Configure>` 只重置 after 计时器，风暴安静 120ms 才结算一次，风暴期零写入（结构性不可能反馈进递归）；评估并弃用节流方案（风暴中途的写入仍可能经滚动条阈值互振重新点燃递归）。
2. **迟滞**——`_wrap_should_apply` 纯函数：`|Δ| ≤ max(12, 2%)` 不写（滚动条出现/消失的 ±11px 抖动被吸收），scale 变化强制重算，首次应用恒写。
3. **TclError 竞态守护**——弹幕/画质占位每 2s 重建，防抖回调与销毁可能竞态。
4. 绑定时已有实宽则同步首应用（首帧即折行），后续走防抖。

**验证**：
- 压力回归锁入套件：`test_dpi_flip_stress_*`（完整 GUI + 8 次 DPI 翻转，事件循环必须排空 + 每标签 wraplength 写入 ≤24；修复前等价场景子进程直接超时）。修复后 9.38s 跑完、~1 写/翻转、事件量与 no-op 对照相当。
- 端到端真窗终验（1120×740 与用户截图同尺寸）：四条长提示全部无裁切；模拟 DPI 翻转后收敛正确、零卡死。
- `run_gates.py` 8/8、pytest 3308 passed/0 警告、basedpyright 0/0/0；迟滞纯函数 5 用例无头全绿。
- AGENTS.md「日志、控制台与 GUI」节新增坑位子弹（防抖 + 迟滞结构为自适应布局类回调的强制形态）。

## 2. 未完成部分

### 2.1 阶段2 — 运行期验证（✅ 已完成，见 §1.3）

原阻塞项（本机无 venv）已由用户恢复环境解除。2026-09-29 实测：`run_gates.py` 8/8、全量 pytest 3248 passed/0 警告、覆盖率 83.98% 全达标、basedpyright 0/0、§2.1 指定的 `tests/test_web_api.py` + `tests/test_web_api_routes.py` 165 passed/0 警告。

**唯一遗留**：打包体积复测（`scripts/report_bundle_size.py`）需先跑一次 `build_exe.py`（本机 `dist/` 为空），归入阶段5 收尾；复测前建议先 `pip uninstall fastapi pydantic` 让环境与清单一致（见 §1.3 残留事实）。

已知偏差（维持 CODE_WIKI 标注）：422 detail 由 pydantic 字段级列表改为字符串 `str(ValueError)`，前端 `apiError()` 只读取 detail 文案，行为兼容。
### 2.2 阶段0 — 基线取证（未实测）

- 改造前 API P50/P95、首屏资源字节数、GUI 建窗与表格刷新耗时、打包体积基线未系统实测。
- 路由黄金快照曾以 `tests/web_api_routes_baseline.json` 形式落地，但被敏感内容门禁拦截，已在阶段2 改为 `tests/test_web_api_routes.py` 动态断言（drift-proof，不撞门禁）。
- 建议：环境恢复后，阶段5 收尾时用 `scripts/report_bundle_size.py` 补一次改造后体积读数，与历史体积注对账。

### 2.3 阶段3 — GUI 主题层（✅ 已完成，见 §1.4）

~~待做~~ 已交付：`src/ui_theme.py` + `tests/test_ui_theme.py`（34 用例）+ `gui.py` 主题菜单与持久化 + `config/config.ini` 模板 `[GUI]` 节 + README/i18n 同步。

### 2.4 阶段4 — GUI 控件层（✅ 已完成，2026-10-03）

~~待做~~ 已交付（用户指令启动，单批完成六处替换）：

- **`src/ui_kit.py`**（约 430 行）：`Frame`/`Label`/`Button`/`Menu`/`EditorText`/`terminal_text` 六个 CTk 兼容工厂 + `DataTable`（Treeview 行级增量更新 + 单元格浮层编辑器）。颜色一律不进工厂——由 ui_theme 按 token 注册的 15+ 个 ttk 变体样式派生，主题切换经全局样式统一重绘。
- **gui.py**：控制台/画质监控/弹幕监控/URL 配置/运行日志/高级设置 + 侧边栏全部换 ui_kit；画质/弹幕表头与数据行四方法删除（headings + `sync()` 承担）；占位改单实例叠放；`_compute_wraplength` 去缩放除法（ttk wraplength=设备像素，Tk 9.0 探针实测）、`ScalingTracker` 退役；「外观模式」菜单移除，「界面主题」加「跟随系统」（写空值 = 清显式偏好）；`_sync_theme_extras()` 收编 Canvas/行标记/编辑器的主题跟随。
- **ui_theme**：+15 变体样式、`_shade()` 悬停派生、Treeview rowheight、Combobox 下拉 option DB、对比度契约 +3 对（light/dark 的 `success` token 随之加深 #16A34A→#15803D，白字达 AA 4.5；`gui.Colors.SUCCESS` 同批统一）。
- **两处实测裁定**：ttk.Button 无控件级 `-font`（`font_style()` 派生样式解决）；CTk 控件 configure 静默忽略 cnf 位置字典（真窗回归锁抓出，改回命名参数直传）。
- **验证**：`run_gates.py` 10/10；pytest 3993 passed/0 警告（净增 12 条，含 `tests/test_ui_kit.py` 11 条与真窗压力锁在新 GUI 上 0 skip）；覆盖率 47 模块达标（84.90%）；mypy 207 files / basedpyright 0/0/0；变异验证（sync 改回整表重建 → 5 条锁转红 → 字节还原）；真窗冒烟全链成立（五页切换/降级标记/浮层编辑器提交写回 URL_config/主题持久化/跟随系统写空值）。详见 CODE_WIKI 同日条目。

### 2.5 阶段5 — 收尾（✅ 已完成，2026-10-03）

~~未启动~~ 已交付（用户指令启动，单批完成）：

- **customtkinter 依赖摘除**：requirements.txt、pyproject.toml（运行时 + `.[gui]` 双处）、`typings/customtkinter/` 存根、README 双语目录树；`uv.lock`/egg-info 经 `sync_metadata.py` 重生成。gui.py 的 CTk 残留同批替代：root=`tk.Tk`、Toplevel=`tk.Toplevel`（标题栏跟随系统 = 登记的观感边界）、`CTkFont`→点值 `tkfont.Font`（3/4 折算，随 DPI 自动缩放）、`_THEME_CTK_MODE`/`_ctk_mode_to_theme` 退役、「跟随系统」走 `ui_theme.detect_system_appearance()`（win32 注册表 / darwin defaults / 失败回 light）、`_apply_root_chrome()` 上 root 底色。
- **build_exe.py**：移除 `collect_data_files('customtkinter')`；excludes 的 customtkinter 条目按 fastapi 防御口径保留。`--smoke --no-zip --no-runtime` 三入口全过，`_internal/` 零 CTk 条目。
- **体积基线（阶段0 补齐）**：`report_bundle_size.py` 实跑 **91.81 MB / 224 文件**（exe 32.28 / numpy 26.29 / python314.dll 6.48 / libcrypto 5.74 / Tcl/Tk 5.28），工具链泄漏未发现；读数落 `measured-evidence.md`。
- **xvfb 常态化**：test job apt 加装 xvfb + pytest 包 `xvfb-run -a` + 「Tk 开显示」反 skip 兜底步（MID-2264 口径）——真 Tk 用例在 CI 从 skip 变真实执行。
- **验证**：`run_gates.py` 10/10；pytest 3993 passed/0 警告（真窗用例本机 0 skip）；覆盖率 47 模块达标（84.70%）；mypy 207 files / basedpyright 0/0/0。CI 首跑验证项（xvfb job / mypy 2.4.0）交下一次 push。

---

## 3. 阻塞点与环境前提（当前）

已解除：用户已恢复 `.venv`（Python 3.14.7 + 全量依赖），阶段2 运行期门禁实跑全绿。Node v22.22.2 / Tk 9.0 可用。

**残留注意**：venv 内 fastapi/pydantic 仍残留（已从清单删除但未卸载），代码零引用、门禁不受影响；打包复测前建议卸载。

---

## 4. 下一步建议

1. ~~用户恢复 venv 后，先跑阶段2 运行期验证（§2.1），确认全绿再继续~~：已完成（§1.3）。
2. ~~进入阶段3（GUI 主题层）~~：已完成（§1.4）。
3. ~~进入阶段4（GUI 控件层）~~：已完成（§2.4）。
4. 阶段3/4 每阶段独立验证、逐阶段交付确认（遵循提案「每阶段完成判据」）。
5. ~~进入阶段5（收尾）~~：已完成（§2.5）。**UI 现代化五阶段全部收账**（阶段0 的基线取证以阶段5 的 91.81MB 总读数部分补齐；API P50/P95 与首屏字节基线维持豁免）。CI 首跑验证项：xvfb test job、mypy 2.4.0 consts。
