# README 更新日志归档（简体中文卷）

> 本卷由 `README.md` 的「更新日志」于 2026-09-28 整卷迁出，条目正文逐字保留；根文档只留当前发布周期条目 + 本卷指针。
> 收录 19 条历史发布说明（2024-07-13 ~ 2026-09-15：2026-09-28 整卷迁出的 17 条 + 2026-10-18 续迁的 v4.2.0 / v4.1.0 两条）；2026-10-31 增补 v4.5.0 / v4.4.0 / v4.3.0 三条，本卷合计 22 条。
> 回补口径：上一轮文档粗剪脚本把部分句子截成行尾 `…` 的半句，本卷按 `.workbuddy/docold`（2026-09-25 基线）对残句做**逐行前缀匹配**回补，共回补 120 行（唯一匹配失败 0 行、有歧义 0 行保持原样）。
> 刻意**不做**的事：不复活历史上被有意删除的条目，不回填已外迁到 `docs/agent-reference/changelog-file-inventories.md` 的文件清单块——整块回填会撤销那些有意的整理，故只补残句。
> 归档卷不参与镜像构建产物，运行时不读取；根文档入口：[README.md](../../README.md)。

## 目录索引

| 版本条目 | 日期 |
| --- | --- |
| v4.5.0 (2026-10-02 ~ 2026-10-17) — GUI 窗口层迁移 PySide6、移动端/短链平台接入、Linux arm64 与 GHCR 多架构镜像（2026-10-31 迁入） | 2026-10-17 |
| v4.4.0 (2026-09-29 ~ 2026-10-01) — Web 面板 FastAPI → Starlette 迁移、Web 前端与安全整改（2026-10-31 迁入） | 2026-10-01 |
| v4.3.0 (2026-09-16 ~ 2026-09-27) — ffmpeg master 录制失败 P0 修复、发布链与元数据同步（2026-10-31 迁入） | 2026-09-27 |
| v4.2.0 / v4.1.0 (2026-09-10 ~ 2026-09-15) — 2026-10-18 续迁的两条历史发布说明（见卷内 2026-10-18 迁入标记） | 2026-09-15 |
| v4.0.9.4 (2026-09-03 ~ 2026-09-06) — HLS 采集排除平台列表 / 画质选项增删与行内切换 / P0 分段容器错配修复 / 打包缺陷修复 / 全仓注释补齐与元数据同源同步 | 2026-09-03 |
| v4.0.9.3 (2026-09-02) — 代码审查 20 项问题全量修复（cookie 缓存并发去重 singleflight 重写 / Web 非 ASCII 密码登录崩溃 / 探针异常留痕与节流自清理 / 64 位 ctypes 句柄截断 / 连接资源生命周期）+ mypy 全仓类型清零（tests / gui_legacy / scripts / standalone） | 2026-09-02 |
| v4.0.9.2 (2026-08-28 ~ 2026-08-30) — Web 面板录制手动控制 / 虎牙·斗鱼蓝光细粒度画质档位 / 停止录制流程日志归档 / 性能审查优化落地（P1~P5）/ 探针退避窗口自愈与虎牙 FLV-first / Web 后台日志 sink 重建 / GUI 父进程日志句柄隔离 | 2026-08-28 |
| v4.0.9.1 (2026-08-27 ~ 2026-08-28) — 高并发调度加固 / 本地化系统修复 / 编译与熔断门禁修复 / CI 工作流优化与重试收敛 | 2026-08-27 |
| v4.0.9 (2026-08-23 ~ 2026-08-24) — 高并发多平台录制调度优化 / 录制反馈闭环 / 并发双模式 / Python 3.14 升级与语言键迁移 / 四语本地化目录统一与英式美式分流 / 类型与 CI 质量门禁修复 | 2026-08-23 |
| v4.0.8.3 (2026-08-19 ~ 2026-08-22) — 主播名自动更新 / SSL 配置整合 / 四语国际化 / FFmpeg9·Node24 兼容 / 类型安全加固 / start_record 复杂度治理 / 窗口化崩溃加固 / 类型检查缺陷修复 | 2026-08-19 |
| v4.0.8.2 (2026-08-16 ~ 2026-08-18) — 录制/弹幕/国际化/类型检查 系列修复 | 2026-08-16 |
| v4.0.8.1 (2026-08-01 ~ 2026-08-09) — 注释规范 / 冒烟测试 / GUI 优雅退出 / 校验修复 整合 | 2026-08-01 |
| v4.0.8 (2026-07-30) — Web 面板 / 画质监控 / 代理与类型修复 | 2026-07-30 |
| v4.0.7 (2025-10-24) | 2025-10-24 |
| v4.0.6 (2025-01-27) | 2025-01-27 |
| v4.0.5 (2024-11-30) | 2024-11-30 |
| v4.0.4 (2024-10-30) | 2024-10-30 |
| v4.0.3 (2024-10-05) | 2024-10-05 |
| v4.0.2 (2024-09-28) | 2024-09-28 |
| v4.0.1 (2024-09-03) | 2024-09-03 |
| v4.0.0 (2024-07-13) | 2024-07-13 |

## 归档条目

### 迁入：v4.5.0 / v4.4.0 / v4.3.0（2026-10-31 自 README.md 逐字迁入）

> 迁入范围：`README.md`「更新日志」中的 v4.5.0 / v4.4.0 / v4.3.0 三个发布条目；正文逐字保留，未改写。

### v4.5.0 (2026-10-02 ~ 2026-10-17) — GUI 窗口层迁移 PySide6（Qt6）与界面现代化阶段4~6 收尾 / 移动端与短链平台接入（b23.tv / m.douyu.com / hy.fan / 小红书四类归一）/ Linux arm64 ffmpeg 与 GHCR 多架构镜像 / 启动期字节码缓存清理与发布链在线来源层 / config.ini 重复键容错读取层与 i18n 三批机检 / 全工作区代码审查与两轮元数据对账

> 本版本（v4.5.0，2026-10-02 ~ 10-17）是一次「GUI 全面现代化 + 平台接入扩张」周期：① **窗口层由 tkinter/ttk 迁到 PySide6（Qt6）**，新增 `src/gui_qt/`，令牌与 QSS 单一事实源、控制器层可离屏单测，打包侧靠 `QT_BLOAT_FILES` 剪除 Qt 死重；② **界面现代化阶段4~6 收尾**（CTk → ttk、`customtkinter` 摘除、字号 / 缩放 / 动效）；③ **平台接入扩张**（三类移动端短链 + 小红书四类链接归一，Linux arm64 与 GHCR 多架构补齐）；④ **config.ini 同节重复键不再整份失效**（新增 `src/config_read.py`）。**存在破坏性变更（GUI 实现与依赖面）**，见下方专节。详细根因与验证见 [CODE_WIKI.md](../../CODE_WIKI.md)。

**✨ 新增功能 / 改进**
- **GUI 窗口层迁移 PySide6（Qt6）**：新增 `src/gui_qt/`（16 文件 4189 行，含 `pages/` 五页），`gui.py:main()` 委托 `src.gui_qt.app.main()`（tkinter 实现留作 `_legacy_main()`；[历史注] 该回退实现已于 2026-10-31 完全移除）。令牌与 QSS 单一事实源在 `theme.py`，线程模型换轨 Qt Signal/Slot + `QTimer`；控制器层无 Qt 布局代码，`QT_QPA_PLATFORM=offscreen` 即可离屏单测。
- **界面现代化阶段6（字号 / 缩放 / 动效）**：新增 `src/ui_scale.py`（语义字号七档 caption 10 → display 28、间距栅格、缩放档位、小屏自动降档）与 `src/ui_motion.py`（off/subtle/full，系统「关闭动画」优先）。缩放只改字号与间距，点值按 `factor ** 0.6` 温和增益（等宽再乘 0.9）。
- **GUI 视觉语言改版（品牌蓝 → 暖赭橙）**：`src/ui_theme.py` light/dark 两表换 16 个槽位，`gui.py` 的 `Colors` 同批换值；主色 `#B5573A`（白字 4.78；原型 `#C96442` 实测 3.90 不达 AA），深色 hover `#A8502F`。`high_contrast`、`TERMINAL_*` 与语义色槽未动。
- **GUI 自选字体**：新增 `src/ui_fonts.py`（SFNT name 表解析 + GDI 私有字体注册，拒收 woff2）；切族在同一 `configure` 完成、不重建控件树。可用性判据是让 Tk 解析一次并与缺失族名的兜底结果比对（`AddFontResourceExW(FR_PRIVATE)` 成功但 `tkfont.families()` 列不到私有字体）。
- **GUI 静态标签接入 i18n**：新增 `src/ui_i18n.py`（`T()` + `retranslate_all` + `apply_title`），静态标签 54 处、运行时串约 60 处接线，语言切换整窗回填不重建；`src/web_api.py` 27 处展示类文案经 `tr()`（稳定机器码 detail 不翻）。
- **移动端与短链平台接入**：B站 `b23.tv`（纯数字直取 + 短码 302 跟随）、斗鱼 `m.douyu.com`（白名单 + 房间号归一）、虎牙 `hy.fan`（新 resolver + 301 跳转归一）、小红书 `parse_xhs_live_url`（`/livestream/<房间ID>` / 动态路径 / `xhslink` / 分享参数四类）。归一后复用既有取流链，`record_host` 仍取短链域以便熔断分桶计数。
- **Linux arm64（aarch64）ffmpeg 三段落地**：发布矩阵新增 `ubuntu-24.04-arm`（四平台 × lite/full = 8 zip）；新增 `src/ffmpeg_linux_download.py`（官方 digest 优先、TOFU 降级、两趟安装）作无 root 兜底；新增 `docker-publish.yml`，原生双 runner 各出一架构层并按 digest 合成 manifest（仅 `v*` tag）。
- **启动期字节码缓存清理**：新增 `src/startup_cleanup.py`——正向白名单扫描根、基线 = `sha256(相对路径 + 字节)` + 版本号、落 `logs/.pyc_stamp`，只在源码或版本变过时回收一次（默认开，可关）。
- **发布链运行时钉定「在线来源层」**：`build_exe.py` 新增三态开关 `DLR_RUNTIME_PIN_SOURCE`（off/verify/adopt，默认 off 不发请求）；`adopt` 仅对「清单独立认证」（`trust=signed` 且验签通过）开放，在线值须过 64 位小写十六进制形状关。`_PINNED_RUNTIME_SHA256` 未改，默认行为与引入前一致。

**🐛 修复的问题**
- **config.ini 同节重复键让整份配置失效**：`[录制设置]` 同名键落两行时 `RawConfigParser()`（strict 默认 True）抛 `DuplicateOptionError`，一个键都读不出（`import main` 即崩、GUI 每 10s 报错）。新增 `src/config_read.py`（`tolerant_config_parser` / `find_duplicate_options` / `warn_duplicate_options`），接线 10 处读取点，缺键补写保持幂等。
- **Qt 等宽字体族名告警**：`QFont` 族名位只收单个 family，`QFont("Consolas, Menlo, Courier New, monospace")` 在未装 Consolas 的机器按 `styleHint=Monospace`（枚举 7）落进 `Terminal`，打出 `CreateFontFaceFromHDC() failed` 与 `setPointSize(-1)`。新增 `fixed_font()` 按候选取本机首个命中族名。
- **`src/ui_fonts.py` 两处缺陷**：① 复制失败被 `except Exception: return None` 吞掉且零日志 → 先落带 `{type_name}` / `{err}` 的 warning；② `_safe_filename` 不处理 Windows 保留设备名（`CON`/`PRN`/`AUX`/`NUL`/`COM1-9`/`LPT1-9`），按首个点之前的基名大小写不敏感比对并加 `_` 前缀。
- **GUI 右边框裁切**：三条长提示初始 `wraplength=0` 把 `winfo_reqwidth()` 撑到 1248 > geometry 1120，而 grid 对「需求宽 > 分配宽」是裁切而非收缩。修法三段：抬首窗几何消首帧赤字、压到档位最小宽读出「收缩地板」后只抬 `minsize` 到地板、尺寸 clamp 到 `SCREEN_FILL_CEILING`。
- **小红书离线轮拿不到主播名**：改读 `liveStream.roomData.hostInfo.nickName`（实测 `liveStatus="end"` 时仍存在）；旧实现只在开播态抠 `roomInfo.deeplink`，等待开播的每一轮都误判失败，取不到时用 `小红书_<room_id>` 兜底。
- **斗鱼房间号提取两个边界洞**：旧正则未锚定参数边界（`?xyzrid=123` 误命中）且把尾斜杠与后续路径带进房间号（`/8751648/`）。改走 `urlsplit` 在解析层剥掉 scheme / 尾斜杠 / query / fragment；错误提示为 `i18n.tr` 常量模板且链接先过 `mask_credentials()`。
- **`CODE_REVIEW_2026-10-02` 整改收尾**：补 L-04（`shopee` / `花椒直播` 缺 `platform_cookie` 映射）与 L-05（删模块级死全局）；修正整改自引入的 4 类缺陷——`except Exception:` 仍引用 `type(e)` 的 `NameError`、`mask_credentials` 收 tuple 的 `TypeError`、日志刷新链复位点，以及裸真值把 `"0"` 误判私有（改走 `parse_config_bool`）。
- **i18n 三处**：Qt 侧栏 5 条「按名 `tr()`」msgid 缺失（Qt 用两空格形态、目录只有三空格形态）→ 四目录各 +5 条并存；9 处 Qt 按钮图标被 `set_text` 打回裸文本 → 构造标签与 `T()` 同 msgid、复用既有键（零新增）；21 处中文 raise 文案在产生点接 `tr()`（去重 16 条 msgid）。
- **签名脚本钉定表尾字节漂移**：pre-commit 的 `end-of-file-fixer` 给 `src/javascript/` 下 4 份脚本各追加换行，而 `_check_js_hash` 按原始字节求 SHA256，四条全失配；按拍板重算钉定表（`migu.js` 本就带尾换行，未动）。

**⚠️ 破坏性变更 / 行为变化**
- **`customtkinter` 整体摘除（阶段4~5）**：控件层 CTk → ttk，新增 `src/ui_kit.py`（六个兼容工厂 + `DataTable`），配色由 `ui_theme` 注册的 ttk 变体派生、「界面主题」成为唯一明暗入口；`CTkToplevel` → `tk.Toplevel`、`CTkFont` → 负数点值 `tkfont.Font`，存根删除。兼容契约逐字保持（`import gui` 无头导入、录制链一行不动）。
- **GUI 窗口层换轨 PySide6**：`gui.py:main()` 委托 `src.gui_qt.app.main()`，tkinter 实现留作 `_legacy_main()`（[历史注] 已于 2026-10-31 完全移除）；`packages` 增列 `src.gui_qt` 与 `src.gui_qt.pages`（显式 packages 不递归发现，漏列会让 `douyin-recorder-gui` 入口 `ModuleNotFoundError`）。
- **镜像默认不装 GUI 依赖**：`Dockerfile` 新增 `ARG INSTALL_GUI=false`——阶段1 按行首剔除 `pyside6` 后再装，阶段2 仅 true 时补 Qt 运行库；依据是「PySide6 解压 647.56MB，屏蔽后 `import main` / `import web` 仍成功」。过滤只在镜像侧，compose 的 `gui` 服务另用 `:latest-gui` tag。
- **`[tool.mypy].exclude` 目录名锚定**：该字段是路径子串正则，裸 `"ffmpeg"` / `"node"` 曾把 12 个文件（`src/ffmpeg_*`、`tests/test_ffmpeg_*`、`node_install`）排除在无参 mypy 门禁外；改 `(^|/)ffmpeg/` 与 `(^|/)node/` 后首次进门禁并暴露 8 处存量标注错误（已修）。
- **CI 真窗用例由 skip 转为真实执行**：test job 的 pytest 改 `xvfb-run -a` 包裹并加装 xvfb，另加「Tk 开显示」兜底步骤（xvfb 失效当场红，防真窗用例静默消失）。

**📦 依赖变更**
- **运行时依赖新增 `PySide6>=6.12.0`**：随窗口层迁移加入（摘除 `customtkinter` 后 20 条 → 21 条），下界 6.12 为实测支持 Python 3.14.8 的最小版；`uv.lock` 与 egg-info 经 `sync_metadata.py` 重生成。`pystray` / `Pillow` 保留（Web 托盘 `src/web_tray.py` 仍走 pystray）。
- **移除 `customtkinter`**：`requirements.txt`、`pyproject.toml`（运行时清单 + `.[gui]`）、`typings/customtkinter/` 同批摘除；`build_exe.py` 移除 `collect_data_files('customtkinter')`，excludes 条目按防御口径保留。
- **dev extra 新增 `pre-commit>=3.6.0`**（配套 `.pre-commit-config.yaml`）；属 dev extra、不入 `requirements.txt`，运行时依赖仍 21 条。
- **CI 工具版本常量对齐本地实装**：`isort_version` 9.0.2、`black_version` 26.10.1，`.pre-commit-config.yaml` 两个 mirror rev → 26.10.1 / 9.0.2，使「本地 venv / CI / 提交钩子」同值；抬值前两版 black 各跑一次全量 `--check`（判定不变），新 rev 逐个经 GitHub API 核实。

**🛠️ 仓库维护与文档**
- **界面现代化阶段4~6 收尾**：CTk → ttk 控件层、依赖摘除与打包清理、体积基线补齐（91.81MB / 224 文件）、xvfb 常态化，以及字号 / 缩放 / 动效。
- **i18n 机检三批**：新增 `tests/test_i18n_catalog_coverage.py`（按名调用点 msgid 四目录齐全 / 白名单集合相等 / 键集合逐项相等）、`test_i18n_raise_site_tr.py`、`test_gui_qt_label_parity.py`；`extract_i18n_strings.py` 认识 `T(...)`。四目录键数 1110 → 1127（期间收回 6 条孤儿键）。
- **门禁与 CI**：typecheck 补 `mypy --platform win32`；新增 `pyrightconfig.json`（include 等于 `[tool.mypy].files`、exclude 覆盖两份清单），使不带路径跑 `pyright` 复现 IDE 扫描面；新增 `tests/test_ci_frontend_registration.py`（`.mjs` ↔ ci.yml 清单双向差集）与 Hook 执行体 `scripts/agent_hook_guard.py` + `/dlr-dod`。
- **代码审查与元数据对账**：`CODE_REVIEW_2026-10-02.md`（8 工作包深审，严重 2 / 中等 18 / 轻微 47 = 67；报告矩阵原记 17 / 66 已按枚举更正）；两轮元数据同源对账（取值零改动）；`AGENTS.md` 69 项机检、6 处断言按实测改正、3 处 `file:line` 改锚点。
- **CODE_WIKI 双语新增「按模块分类的改动总览」**（11 个小节，同一张数据表渲染）；Linux arm64 与四平台矩阵同步进双语 README 的产物清单与 GHCR 拉取说明。

**🧪 测试与验证**
- 全量 `pytest` **4365 passed / 14 skipped / 0 failed、warnings 空**；`run_gates.py` **10/10 全绿 rc=0**（black 246 文件、无参 mypy 245 文件 + linux/win32 双跑）。
- 覆盖率总 **83.10%**，`check_coverage.py` **69 模块全达标**（`src/config_read.py` 98%）；basedpyright 与裸跑 `pyright` 均 0 errors / 0 warnings。
- 打包体积 **153.21MB / 359 文件**；`QT_BLOAT_FILES` 11 项 / 39.25MB 在 COLLECT 后按文件名剪除（excludes 管不到 hook 收的 DLL），冻结 GUI exe 实跑 9s 存活。
- 真机：虎牙 660000（2 条 / 206 B）、B站 545068（33 / 2642 B）、b23.tv 22747736（18 / 1402 B）均 PASS；`hy.fan/JbmwoV` 真实 301 解析到 `www.huya.com/30764624`（在播，该时段无弹幕记 WARN）；小红书 570480456678837366 解析 OK（`liveStatus=end`）；斗鱼 `m.douyu.com/5526219` 完整取流链返回 `flv_url` / `m3u8_url` / `record_url`。
- GUI 真窗：主题 ×4 / 缩放 ×5 / 动效 ×4 / 五页面 / 对话框 / 高级设置全 `ALL_OK`，85% / 100% / 150% 三档截图复核（「按钮内边距不跟随」「侧栏底部溢出」「页面滑入后消失」三缺陷即在此发现）。

### v4.4.0 (2026-09-29 ~ 2026-10-01) — Web 面板 FastAPI → Starlette 迁移（移除 fastapi/pydantic，24 条路由契约逐字保留）/ Web 前端动效层与移动端适配 / GUI 主题层（阶段3）与长文案自适应折行根除 DPI 卡死 / 抖音原画 HEVC 房「无可用源」死锁根治与 h265 候选按保存格式放行 / 两轮全量代码审查与 P0 修复（standalone SSRF 三道防线、ffmpeg 命令日志脱敏等）/ i18n 盲区补录 / 依赖与文档多轮对账

> 本版本（v4.4.0，2026-09-29 ~ 10-01）为一次「UI 现代化 + 全量审查修复」周期。四点最值得注意：① **Web 后端从 FastAPI 迁移到 Starlette 直接驱动**——自研路由适配器与零依赖校验层，24 条路由契约与全部安全不变量逐字保留，运行时依赖 23 → 21；② **两轮全量代码审查**（`CODE_REVIEW_2026-09-29_2` 31 编号全落地 + `CODE_REVIEW_2026-09-30` 严重 2 / 中等 51 / 轻微 160、P0 已修）清掉 standalone 独立发行版的 SSRF/本地文件读取链、ffmpeg 命令凭据明文落盘等一批静默失效形态；③ **抖音原画 HEVC 房死锁根治**——主播在播却每轮「本轮无可用源」永不录制的死锁（hevc 替换、h265 候选剔除、HLS 静默丢弃三规则叠加）已修复，h265 候选按保存格式（TS/MKV/MP4）放行直拷并新增零源观测告警；④ **GUI 主题层（阶段3）** 与 **Web 前端动效层（阶段1）** 落地，GUI 长文案自适应折行根除两侧裁切与 DPI 重缩放卡死。**存在破坏性变更（依赖面）**，见下方专节。详细根因与验证见 [CODE_WIKI.md](../../CODE_WIKI.md)。

**✨ 新增功能 / 改进**
- **GUI 主题层（阶段3）**：新增 `src/ui_theme.py`（零显示依赖、可无头 import）——13 个语义槽位 × 三套主题（浅色 / 深色 / 高对比度），侧边栏「界面主题」菜单运行时切换并持久化到 `config.ini [GUI] gui_theme`；WCAG 对比度机检（正文 4.5 / 非文本与禁用 3.0）由 `tests/test_ui_theme.py`（34 用例）持续回归。
- **Web 前端动效层（阶段1）**：新增 `web/motion.js`（零依赖 IIFE，挂载 `window.__dlrMotion`）——滚动入场（IntersectionObserver 错峰）/ 视差粒子（数量按视口自适应、低核设备减半）/ `prefers-reduced-motion` 全降级 / 页面隐藏暂停 / `destroy()` 无残留定时器；`web/index.html` + `web/style.css` 接线；`tests/frontend/test_motion.mjs` 5 用例（node:test 沙箱，零 npm 依赖）。
- **Web 后端自研适配层**（随迁移新增）：`src/web_models.py`（9 个纯标准库 dataclass 请求模型，替代 pydantic）+ `src/web_api.py::_route` 路由适配器（JSON body 解析 / Query 上下界夹取 / 同步端点线程池派发 / JSONResponse 包装），24 个路由处理器函数体零改动。
- **`retry` 复合动作新增 `fail_fast_codes` 入参（按退出码分档）**：不传时既有 16 个调用点行为逐字不变；web smoke 调用点传 `"2"`，配置类错误立即失败不进入退避——不得为了流水线变绿退 0 或降级 warning。
- **两道新测试防线**：R7 真机脚本模板 AST 门禁（`__main__` 守卫 / 收集期零副作用 / argv 两步守卫 / 按平台前缀清理，5 个 live_collector 同批加固）；R8 全仓 `MUTATION-` 残留扫描（变异验证未还原即判红，配套三条硬约束写回 AGENTS.md）。
- **新增动态路由契约锁** `tests/test_web_api_routes.py`（24 条 method/path 精确集合 + `/web` 挂载点），取代被敏感门禁拦截的静态基线 JSON。
- **h265 候选按保存格式放行（TS/MKV/MP4 可直拷 HEVC）+ HLS 静默丢弃的零源观测告警**：`_h265_copy_format_supported()` 按 main 热更新的 `video_save_type` 判定容器能否直拷 HEVC——TS/MKV/MP4 放行（h265 主候选进常规探针序列）、FLV（HEVC-in-FLV 属 Enhanced-FLV 扩展）/MP3/M4A/域外取值保守剔除；main.py 的 h265→TS 强制块加同一口径守卫（保存格式已是 TS/MKV/MP4 时不再接管、不再打「use TS format instead」告警）。m3u8 候选被 HLS 配置（全局开关/排除平台）整组静默剔除且本轮最终无可用源时，新增点名成因、候选条数与恢复开关指引的观测告警——补上此前唯一「零日志」的选源成因；选中源的健康轮不打。

**🐛 修复的问题**
- **抖音原画 HEVC 房「本轮无可用源」死锁根治**：主播在播却每轮跳过录制，状态行累计错误数恒 0（选源失败轮不计错误样本，纯看状态行会误判正常）。根因是三条各自成立的规则叠加——原画请求且接口下发 `hevc_flv_url` 时 h265 FLV **替换** h264 成为唯一 FLV 候选；`select_source_url` 把一切 `codec=h265` 候选在探针前剔除；HLS 采集关闭时 h264 m3u8 组被静默剔除、record_url（`.m3u8`）被联动禁用——过滤后零可用候选。修复：hevc 替换发生前把被替换的 h264 原画地址存入 `flv_url_list`（HLS 关闭/不可达时落到该备选；与 hevc 地址逐字相同或自带 `codec=h265` 标记的条目不收）。真机验证 hevc 原画在播房：HLS 关闭态选中 h264 FLV 备选（修复前该形态恒「本轮无可用源」）→ `E2E_RESULT: CURED`。
- **standalone 独立发行版孪生漂移（严重 2 项）**：① 探针/录制链 SSRF 与本地文件读取链（默认 `build_opener` 注册 FileHandler + 候选无协议/内网判定 + ffmpeg 缺 `-protocol_whitelist` 三层叠加，`file://` 与云元数据地址可被「探测→放行→录制落盘」完整走通）——补显式 Handler 白名单、`_untrusted_stream_target_reason` 内网判定（含 `2130706433`/`0x7f000001` 等缩写形态）与两处 `-protocol_whitelist`；② 完整 ffmpeg 命令（含 Cookie 头与带 token 流地址）逐轮明文落 `logs/ffmpeg.log`——写入前经 `_mask_ffmpeg_cmd_for_log` 脱敏。
- **P0 六项**：磁盘满暂停期退出的房间不再永久残留 `running_list`（空间恢复后全部房间不再拉起的根因）；GUI 保存配置改真原子写（POSIX 下不再把 0600 收紧还原成 umask 权限）；Web 口令 strip 三处统一（首尾带空格的口令不再认证自锁 403）；`update_config_line` 移除无引号值行内注释回落启发式（含 ` #` 的配置值不再被静默污染）；header 形态驼峰凭据（`myToken:`/`sessionKey:` 等）恢复脱敏；`replace_url` 改段级精确匹配（URL 前缀重叠的兄弟房间行不再被「地址失效自动注释」整行误伤）。
- **全量审查修复 31 编号**：Shopee 短链落地页双闸（域族白名单 + 内网判定，不可信即丢弃跳转、剥离 Cookie）；异步 HTTP **逐跳**重定向内网复检；`sync_req` scheme 白名单 opener（不再注册 file/ftp/data handler）；PandaTV/WinkTV 等平台进日志的原始 URL 一律脱敏；快手 did / B站 buvid 跨代理出口不再串用设备指纹；`anchor_name` 为 None 不再崩掉整轮解析；TikTok HLS-only 房间「选流畅实拉原画」且无降级提示的选档缺陷；B站弹幕 host 轮换「假关闭」吞真实断连；Web 认证拒绝文案不再被 stdio 重定向吞掉；`tr()` 二次异常不再顶掉原始异常；前端 reauth 口令改掩码弹窗、三条轮询链代次令牌防失联定时器；GUI 状态行匹配串按语言惰性重算、`after` 自续期链 `try/finally` 防永久断裂、「停止录制/彻底退出」共用单飞入口、tail 线程逐事件容错；真机脚本收集期真连平台/清空输出目录的会话污染（`pytest --collect-only` 20.55 秒 → 0.81 秒）。
- **同步探针内网收口**：同步探针此前连初始 URL 的内网/回环/云元数据判定都没有（协议形态白名单挡得住 `file://`、挡不住 `http://127.0.0.1:6379`）——`_probe_client()` 单点工厂 + 发请求前初始判定 + `RedirectHopRejected` 收敛；实测公网 HLS 走通、`127.0.0.1:6379`/`169.254.169.254`/`10.0.0.5`/CGNAT 全拒（末位候选也不放行）。
- **GUI 长文案两侧裁切与 DPI 卡死（同根因两批修复）**：`_bind_adaptive_wraplength` 自适应折行根除 pack 两侧对称裁切（5 处同形态一并修复）；随后把 `<Configure>` 同步追写改为「真防抖（风暴安静 120ms 才结算）+ 迟滞（|Δ| ≤ max(12, 2%) 不写）+ TclError 竞态守护」，根除与 CTk DPI 重缩放递归互泵的事件风暴（整窗卡死 / 文字高频闪烁 / 元素渲染不完整）。
- **Web 面板移动端适配**：顶栏两行化（固定 56px → min-height + ≤768px 换行）、`viewport-fit=cover` + `env(safe-area-inset-*)` 安全区适配、`100dvh` 动态视口、三张数据表窄屏面板内横向滚动——消除 iPhone 16 Pro Max / Pixel 10 上的顶栏裁切与整页横向滚动。
- **i18n 盲区补录**：提取器三类盲区（`print_colored` / `messagebox` / 推送正文）的用户可见文案全部 tr 化，四语目录登记 16 条新词条并重编 `.mo`；zh_TW 顺带去重 7 条重复键，四目录键集恢复严格一致（808 键；10-01 随 h265 零源观测告警词条再登记 1 条，终态 809 键）。

**⚠️ 破坏性变更 / 行为变化**
- **移除 `fastapi` / `pydantic` 运行时依赖**（明细见下方「依赖变更」）：Web 面板的 24 条路由、请求/响应形态、安全头与鉴权中间件行为不变；内部请求模型改 `.parse()` 读取，对外部使用方无 API 面变化。仅在面板之外直接 import 这两个包的自定义部署需要自行调整。

**📦 依赖变更**
- **运行时依赖 23 → 21 条**：删除 `fastapi>=0.140.0` 与 `pydantic>=2.13.4`；`requirements.txt` 与 `pyproject.toml [project.dependencies]` 包名集合逐项相等（回归锁 `tests/test_regression_gates.py`），`uv.lock` 与 `DouyinLiveRecorder.egg-info` 经 `scripts/sync_metadata.py` 重建（二包零残留）。
- **`urllib3` 声明下限 2.7.0 → 2.8.0**：CI `deps-audit`「下限复核」实测旧下限自身落在 CVE-2026-97687 / CVE-2026-97688 / CVE-2026-97689 受影响段（修复版本均为 2.8.0）；`requirements.txt` 与 `pyproject.toml [project.dependencies]` 同步抬升（仍 21 条、包名集合不变），`uv.lock` 与 `DouyinLiveRecorder.egg-info` 经 `sync_metadata.py` 重建；本机 venv 已装 2.8.0，解析集合不变。
- **CI typecheck job 补装固定版本 `pytest==9.1.1`**：`tests/` 的类型检查不再半盲（fixture 与 `pytest.fail()` 的 `NoReturn` 恢复可见）。
- **文档依赖口径修复**：双语 README「安装开发依赖」pip 行由 5 条（缺 `pytest-cov`，照此装出的环境跑不了覆盖率门禁）改为 `pip install .[dev]` 单源形态（指向 `[project.optional-dependencies].dev` 六条）。

**🛠️ 仓库维护与文档**
- **两轮全量代码审查**：`docs/worklog/CODE_REVIEW_2026-09-29_2.md`（31 编号按 P0+P1+P2 全落地）与根目录 `CODE_REVIEW_2026-09-30.md`（18 批逐文件深审约 42,000 行生产代码 + 56,200 行测试，严重 2 / 中等 51 / 轻微 160，Mimosa 深扫交叉证据）；P0 已落地，P1/P2 待后续批次，standalone「回灌对齐」建议单独立项。
- **`AGENTS.md` 多轮对账与精简**：7 项事实同步（用例数 / 符号名 / 调用点数等旧读数更正）+ 信息保真精简 19 处（110,287 → 108,469 字节；门禁 bash 块与全部章节标题逐字未动，三道文档锁 73 passed / 1 skipped 不变）+ 三条门禁口径修正（质量门禁判定改为引用「格式化命令（门禁唯一基准）」一节、`pyright`/Pylance 定位厘清为非门禁、新增「本地门禁可外推前提：工具版本须与 `ci.yml` 钉定值同值」）；stop-hook 凭据风险提示经核查为误报后按建议把红线措辞显式化。
- **元数据对账**：15 个文件对照 `pyproject.toml` 全量核对（版本 4.4.0 / 21 条依赖 / 镜像与服务名 / 端口与挂载 / 打包参数），唯一漂移即上述 README dev-deps 行；`pyproject` `filterwarnings` 两条注释归因由「fastapi testclient」更正为 `starlette.testclient` 本体。
- **两处测试面修复（无生产代码改动）**：`test_gui_stop_exit_singleflight` 在 Linux CI 的 4 条假红系测试替身只桩 win32 信号分支（POSIX 走 `os.kill`），按「stdlib 替身走被测模块命名空间 shim」口径补打桩后，伪造 `sys.platform` 本地复现 POSIX 路径、四场景 25 项判据全过；`test_notify` 超时用例的墙钟余量改由生产常量推导（`taskkill /F /PID` 实测稳定 2.5~3.1s，1s 超时 + ~3s 恰撞 4.0s 手拍余量的机器态误报根除）。

**🧪 测试与验证**
- 全量 `pytest` **3721 passed / 14 skipped / 0 failed / 0 警告**（2026-10-01 终态实测；14 条 skip 均为平台条件性：符号链接特权缺失、Windows chmod 只读位语义、SIGKILL POSIX 形态、h2 已装致缺依赖分支不可达等）。
- 覆盖率 44 模块全部达阈（总 84.9%，coverage.json 实测）；basedpyright 0 error / 0 warning；`run_gates.py` 8/8 全绿。
- 真机验证（09-29 ~ 09-30）：抖音 PASS（59 条 / SRT 4518 字节）、B站 PASS（9 条 / 678 字节）、虎牙 WARN（连接正常、该时段无弹幕）、Twitch WARN、斗鱼 SKIP(房间未开播，解析链正常)、TikTok SKIP(无出境网络)；standalone `--dry-run` 虎牙真实在播房间 PASS（S-01/S-02 增量验证）；公网 HLS 分片探针走通且四类内网目标全拒。GUI 目视项、斗鱼/TikTok 活房间复跑、打包体积复测等交回动作见 [CODE_WIKI.md](../../CODE_WIKI.md)。
- 真机验证（10-01，抖音 hevc 原画在播房「央视网快看」）三态全 PASS：HLS 关 + TS 保存格式 → h265 FLV 主候选被放行并选中（codec=h265 实测探针通过）；HLS 关 + FLV → 落到 h264 原画备选（codec=h264）；摘除备选 → 返回 None 且零源观测告警实弹打出。

### v4.3.0 (2026-09-16 ~ 2026-09-27) — P0 修复 ffmpeg master 构建下录制 100% 失败（`-thread_queue_size` 被上游收窄为输出专属选项）/ 布尔配置解析口径统一（`true/false` 致 8 项配置静默失效、9 个海外平台无法录制）/ 两轮全量代码审查（62 + 106 项分级修复）/ 供应链加固（官方哈希优先 + GPG 验签 + 删除蓝奏云兜底）/ 发布链四处故障修复（**对外分发的 lite 包一度从未真正存在**）/ Apple Silicon 的 ffmpeg PATH 让位策略 / 日志房间关联字段与 `/health` 探活端点 / 构建产物体积 −21.6% / 覆盖率 73.28% → 82.03%（专项）与 83.91%（09-27 终态）

> 本版本（v4.3.0，2026-09-16 ~ 09-27）为一次以「正确性 + 供应链安全」为主线的收敛周期。四处最值得注意：① **P0**：ffmpeg master 构建把 `-thread_queue_size` 收窄为输出专属选项，我们仍放在 `-i` 之前，导致该构建下**每一次录制都以 `-22 (EINVAL)` 退出、零字节产物**；② **布尔配置解析口径统一**：`config.ini` 写 `true/false` 曾被判为无效并**静默**回落硬编码兜底值（无告警无日志），实测致 8 项配置生效值漂移，其中最严重的一项使 9 个海外平台 100% 无法录制，现已统一为「`是/否` 与 `true/false`/`1/0`/`yes/no`/`on/off` 等价」；③ **两轮全量代码审查**（09-19 的 62 项：严重 12 / 中等 22 / 轻微 28；09-21 的 `CODE_REVIEW_2026-09-20` 106 项：严重 10 / 中等 70 / 轻微 26）把 SSRF、面板接管、凭据明文落盘、弹幕线程死循环等一批静默失效形态一次性清掉；④ **发布链四处故障**（09-26 ~ 09-27），其中最影响用户的一条是：`make_zip` 用 `Path.with_suffix(".zip")` 收尾，而版本号本身带点，lite 与 full 算出同一个附件名，第二次以覆盖模式原地截断第一次，**某次 Release 实际只留下一个既无平台也无变体标识的包，精简版从未分发出去**。**存在破坏性变更**，见下方专节。详细根因与验证见 [CODE_WIKI.md](../../CODE_WIKI.md)。

**🐛 修复的问题**
- **P0：ffmpeg master 构建下录制 100% 失败**：`-thread_queue_size` 被上游收窄为 muxer 专属选项，置于 `-i` 之前时 ffmpeg 以 `Option thread_queue_size … cannot be applied to input url … Error opening input files: Invalid argument`（返回码 -22）退出；与房间 / 平台 / CDN 无关，该构建下每次录制都失败。
- **P0：布尔配置解析口径统一**：散落四处的解析（原 `!= "否"` / `== "是"` / 前端 `=== '是'`）统一到 `src/config_bool.py::parse_config_bool`；修复后 `global_proxy` 不再被错误置 False，TikTok / SOOP / PandaTV / WinkTV / Flextv / PopkonTV / Twitch / LiveMe / Faceit 等 9 个海外平台恢复解析。
- **全量代码审查 62 项（09-19）**：GUI 空配置启动静默卡死；配置行多一个逗号致其后所有房间永久不录；Tars 解码缺边界校验致弹幕线程死循环；斗鱼弹幕被静默过滤（已修复项回归）；ffmpeg 挂起永久占用并发槽；零字节产物被判成功并撤销线路退避；`config.ini` 含凭据被明文复制到 `backup_config/`；Web 面板可被自身接口接管或锁死；房间 URL 零协议校验 → 盲 SSRF；脱敏黑名单漏掉「凭据嵌在值里」的 URL 型键；安装与打包链路零完整性校验。
- **`CODE_REVIEW_2026-09-20` 全轮落地 106 项（09-21）**：并发信号量把「可用许可数」当容量（网络并发上限实质失控）；`PUT /api/rooms` 绕过房间入口校验；内网地址拦截用字符串前缀黑名单（实测 7 条放行 5 条）；面板认证可被单个写请求热关闭、大小写变体绕过口令哈希 / 防自锁 / token 吊销；CRLF 配置下删除房间永久静默失效却回报 `{"ok": true}`；Shopee 站点后缀解析拼出非法域名；兜底装饰器与返回契约错配（故障伪装「未开播」）；录制看门狗「停滞」判据基准用错（容忍窗口实际只有 30 秒）；`only_flv` 分支缺 `flv_url` 致时间字幕线程死循环写盘；发布链运行时二进制哈希钉定表为空。
- **发布链与供应链**：macOS arm64 的 full 包**静默不含 ffmpeg**（上游无该产物，下载点已修复）；Windows 运行期 ffmpeg 主源经实测确认健康（gyan.dev 带 `.sha256` 文档，与发布期钉定互证）；官方 SHA256 钉定值回填 6/10 槽。
- **测试卫生（09-23）**：一处跨文件补丁泄漏（漏掉的 `undo()`）让同会话后续用例发出真实网络请求，造成 13 条失败里 11 条「全量红、单跑绿」的假失败。
- **P0：构建脚本污染测试会话（09-23）**：`build_exe._ensure_utf8_streams()` 裸 `reconfigure` 破坏 pytest 的 fd 捕获，表现为「GUI 启动失败」弹窗与无关用例被判 FAILED/ERROR（九个 CI job 全为 ubuntu，恒绿不复现）。
- **发布链四处故障（09-26 ~ 09-27，对外产物受影响）**：① 钉定表八个槽位被误改成「官方签名档」标记，`check_runtime_pins.py --strict` 在 prepare 阶段即 rc=1，发布根本走不到构建（已按官方通道回填哈希）；② Linux 内置 ffmpeg 的钉定值取自 BtbN 的滚动 `latest` 别名，上游同日重发同名资产即换 digest，发布链当天红在 SHA256 校验（改钉**月末不可变 release 标签** `autobuild-2026-08-31-13-27`，URL 与 digest 双不可变）；③ **lite 精简包从未真正分发出去**：`make_zip` 以 `Path.with_suffix(".zip")` 收尾，而版本号 `4.3.0` 自带点，`DouyinLiveRecorder-v4.3.0-windows-amd64-lite` 与 `-full` 被截成同一个 `DouyinLiveRecorder-v4.3.zip`，第二次以覆盖模式原地截断第一次且不报错，Release 附件里只剩一个既无平台也无变体标识的包；④ 任一平台构建失败时，预建的 Release 记录会以**空 Release** 留在仓库里。
- **元数据第二副本漂移（09-27）**：`DouyinLiveRecorder.egg-info/PKG-INFO` 的 `Requires-Dist: h2` 仍停在旧下限 `>=4.3.0`（清单早已抬到 `>=4.4.1` 却从未传播进元数据），内嵌 README 亦缺整段 v4.3.0 更新日志；重建修正。

**✨ 新增功能 / 改进**
- **日志房间关联字段 `extra[room]`**：`src/logger.py` 新增 `ROOM_FIELD` / `set_room_context()` / `get_room_context()`（内部 `ContextVar` + patcher），多房间交织日志可按房间切出。
- **Web 面板 `/health` 探活端点**：`GET /health` 返回 `{"status": "ok", "version": …}`，并把内置冒烟工具 `scripts/smoke_test.py` 接通为 CI 可执行的真实 HTTP 探活。
- **W6：Apple Silicon 的 ffmpeg PATH 让位策略**：darwin + arm64 且系统 PATH 上另有原生 ffmpeg 时，不再无条件前置包内那份 x86_64 构建（需经 Rosetta 转译），五条判据全部成立才让位；其余平台逐字不变。
- **运行时二进制完整性**：`build_exe.py` 新增 `_PINNED_RUNTIME_SHA256` 钉定表 + `--require-pinned`，配套 `scripts/check_runtime_pins.py`（结构模式进门禁 / `--strict` 进发布 prepare / `--emit-env` 供 CI 注入）；运行期首装改为「官方公布哈希优先」，发布期增加 GPG 验签与 full 包产物自检。
- **构建产物体积优化（09-24）**：排除 `PIL._avif`、`pydantic.v1.mypy`（拖入整个 mypy）、uvicorn 可选实现、`i18n/*.po` 等运行期不可达模块 + zip `compresslevel=9`，lite 产物 **82.77MB → 64.88MB（−21.6%）**、zip **54.84MB → 42.19MB（−23.1%）**，并新增 `scripts/report_bundle_size.py` 度量脚本。
- **新增五类门禁**：`PYTHONUTF8=1` + 「告警即失败」（消灭 GBK locale 下 isort 静默跳文件且 rc=0）、装饰器契约 AST 锁、测试卫生 AST 锁（R1–R4 / R6「手工 MonkeyPatch 必须配对 undo」）、前端目录一致性锁（`data-i18n*` 键与四语内嵌目录逐一比对）、`deps-audit` job 与覆盖率无数据硬失败。
- **动态并发下限下调**：`ConcurrencyScheduler` 的 `min_capacity` 默认值 8 → 1。
- **内置 ffmpeg 的上游与满足口径（09-26 ~ 09-27）**：Linux 两架构换源 BtbN 的 GPL 完整版资产（按 `<os>-<arch>` 运行时键分列），取数端点固定为月末不可变标签；macOS 两槽走**官方 GPG 签名档**（evermeet 不公布 SHA256，验签即该槽唯一判据，带外钉完整 40 位主钥指纹）。哈希钉定与验签两条防线互不替代。
- **`release-guard`：残缺即不发布（09-27）**：构建未全绿时用 `gh release delete` 回收预建的空/残缺 Release（默认不删 tag，修好后重跑工作流即可重新发布），并留 `::warning::`；上传步骤的 `fail_on_unmatched_files` 刻意不放宽，因为那条红是产物缺失的唯一可见信号。
- **`--dual` 双产物的两道新校验（09-27）**：出包前先清 `dist/` 里上一轮残留的 `DouyinLiveRecorder-v*.zip`（复用工作区的构建机不会把旧包一起扫进附件）；出包后必须确认 lite 与 full 两个产物路径互不相同且都已真实落件，否则当场终止。
- **CI 的 typecheck job 现在装固定版本 `pytest==9.1.1`（09-26）**：此前只装 `requirements.txt + mypy`，`tests/` 里所有 `pytest.*` 都按 `Any` 检查，fixture 与 `pytest.fail()` 的 `NoReturn` 全部失效，等于半个盲区。
- **文档体积整理（09-27，零信息删除）**：`CODE_WIKI*.md` 更新日志里 73 个历史「涉及文件（按模块分类）」清单块逐字外迁到 `docs/agent-reference/changelog-file-inventories{,-en}.md`（wiki 本体 zh −12.3% / en −5.0%），同时补回上一轮批量压缩静默用 `…` 截断的 109（zh）/ 181（en）处表格原文；`README.md` / `README_EN.md` 刻意不压缩（面向使用者的发布说明不做退化）。

**⚠️ 破坏性变更 / 行为变化**
- **Windows 运行期删除蓝奏云 ffmpeg 兜底**：自动安装只剩主源一条路（实测该直链为带人机验证的 HTML 页、伴生哈希文档全 404，不可用）；自动安装失败时改为给出明确的手动安装指引。**Windows 用户若原先依赖该兜底，需按 README 的「Windows 手动安装 ffmpeg」章节自行放置二进制。**
- **Apple Silicon 不再无条件前置包内 ffmpeg 目录**：已用 Homebrew 装原生 arm64 ffmpeg 的用户，录制子进程会改用系统那份（版本 / 编译选项可能不同）。
- **动态并发下限 8 → 1**：低负载场景下的网络并发额度不再被抬到 8。
- **布尔配置写法语义变化**：此前写 `true/false`、`1/0` 等被**静默忽略**（回落到兜底值）的键，升级后按其字面生效 —— 若你的配置依赖旧的错误兜底值，升级后生效值会改变，请在升级后核对 8 项相关配置。
- **运行时依赖 20 → 23 条**：新增显式声明 `urllib3>=2.7.0`（CVE-2026-44431）、`h2>=4.4.1`（PYSEC-2026-3628）与 `socksio>=1.0.0`（httpx 的 http2 / SOCKS 运行期依赖），`starlette` 下限 `>=0.49.1` → **`>=1.3.1`**（CVE-2026-48710 与 PYSEC-2026-2280/2281/248/249），`protobuf` 保持 `<8` 上限（gencode 兼容护栏）。
- **构建期**：`build-release.yml` prepare 以 `check_runtime_pins.py --strict` 拦下未钉定的运行时二进制。
- **`build_exe.py --dual --no-zip` 现在直接报错退出**：`--dual` 分支此前从不读 `no_zip`，即用户显式写的 `--no-zip` 被静默无视、照样压出两个大 zip。矛盾参数组合改为 fail-fast，不再让其中一个参数不起作用。
- **发布附件名恢复平台与变体标识，请改用新附件**：重新发布后 Windows / Linux / macOS 的附件名形如 `DouyinLiveRecorder-v4.3.0-<os>-<arch>-lite.zip` 与 `-full.zip`；此前形如 `DouyinLiveRecorder-v4.3.zip`（无平台段、无变体段）的附件属上述缺陷产物，其内容是完整版，精简版从未存在过。
- **Linux 完整版（full）体积显著增大**：换源 BtbN 后内置 ffmpeg 资产（未压缩口径）为 linux64 ≈126.6 MB / linuxarm64 ≈108.8 MB，而原 johnvansickle amd64 静态构建 ≈41.9 MB。选择 `lite` 包可保持小体积（运行期按需自动下载）。

**🛠️ 仓库维护与质量门禁**
- **测试覆盖率专项（09-21）**：`src/` 覆盖率 **73.28% → 82.03%**（仅动 `tests/`，产品代码零改动），并引入分层白名单（表默认空 + 到期即失败）。
- **四语目录持续补全与核验**：594 → **780 条**，四个目录键集逐条一致、无空值；`.mo` 随变更重编译。
- **元数据同源同步**：`AGENTS.md` 依赖条数与下限口径、`CODE_WIKI*.md` 依赖表（16 → 23 条）、`DouyinLiveRecorder.egg-info` 重建、`.dockerignore` 补 `_probe_*.py`、`config/config.ini` 补 `[Cookie] ttwid`。
- **类型存根与注释治理**：`typings/execjs/` 7 个 `.pyi` 补齐注解、两个抽象基类存根去 `six`（改 `metaclass=ABCMeta`）；全仓多批注释精炼（含 68 文件一轮），`scripts/check_annotations.py` 新增第三盲点（换行符形态）。
- **清理已删除模块残留**：`src/weverse_auth.py` / `tests/test_weverse_auth.py`（2026-09-23 删除）在目录树、依赖注释与四语目录中的 3 条孤儿译文一并清除。
- **跨文件一致性同步（09-27）**：`requirements.txt` ↔ `pyproject.toml [project.dependencies]` 23 ↔ 23 包名集合逐项相等、三组 extras 相等；`python_build = 3.14` 与 `node_version = 24` 在 `ci.yml` / `build-release.yml` 同值；14 个本地工具目录 + 6 个运行期产物目录在 `.gitignore` / `.dockerignore` / `pyproject` 各工具排除表 / `.coveragerc-concurrency` 四套清单中无缺项；本轮实际修订仅一处——`websockets>=14.0` 被截断的行内注释按同源文本补全（规格未动）。
- **`AGENTS.md` 体积整理（09-27）**：把已在 `docs/agent-reference/measured-evidence.md` 留存的读数改为指针、合并三处真重复，97,034 → 95,715 B（−1.4%）；同时以「token 保全审计」自证未丢约束（用例名 / 错误码 / 常量与环境变量名丢失数均为 0）。

**🧪 测试与验证**
- 全量 `pytest` **3240 passed / 14 skipped / 0 failed**（09-27 本机两轮实测，其中一轮带 `--cov=src`）。原先记述为「本机 Windows 恒红」的 `test_symlinked_system_hit_inside_bundled_dir_keeps_prepending` 现已改为按主机能力显式跳过（`symlink not permitted on this host`），计入上述 14 skipped，不再是失败项。
- `black --check .` **169 files unchanged**；`isort --check-only .` 无重排；无参数 `mypy` **158 files 0 issues**（追加 `mypy --platform linux` 亦 0）；`basedpyright`（standard）**0 errors / 0 warnings / 0 notes**。
- 覆盖率：`src/` 总覆盖率 **83.91%**，`scripts/check_coverage.py` **42 个模块全部达标**（`src/proto/douyin_pb2.py` 为 protoc 生成物，显式豁免）。
- `node --test tests/frontend/*.mjs` 通过；`scripts/check_version.py` 与 `scripts/check_runtime_pins.py` 均 rc=0；`scripts/compile_po.py --check` 报 `zh_CN.mo` 与 `.po` 同步（781 条）。


### v4.0.9.4 (2026-09-03 ~ 2026-09-06) — HLS 采集排除平台列表 / 画质选项增删与行内切换 / P0 分段容器错配修复 / 打包缺陷修复 / 全仓注释补齐与元数据同源同步

> 本期（v4.0.9.4，2026-09-03 ~ 09-06）为多项一致性与质量收尾批次。新增 HLS 采集排除平台列表配置、画质选项用户可增删 + GUI/WEB 行内切换画质；修复两处高危问题——抖音原画 HEVC 因分段容器错配无法录制（P0）、`async_http` 跨循环协程告警导致 pytest 波动告警；修复 `pyproject.toml` 打包缺陷（子包未声明致 `pip install .` 发行包残缺）。同时完成全仓中文注释补齐（41 文件 / +1370 行）、八文件元数据同源同步、四语本地化目录补齐（516→521）。**无破坏性变更**（运行时语义全部保持；PEP 758 无括号 except 写法仅影响 <3.14，本仓下限即 3.14，属既定约定非回退）。详细根因与验证见 [CODE_WIKI.md](../../CODE_WIKI.md)。

**✨ 新增功能**
- **HLS 采集排除平台列表**：新增配置项 `HLS采集排除平台(逗号分隔)`——命中平台无视「是否启用HLS采集」开关、恒按 FLV 采集；列表外平台保持 HLS 优先。支持中英文逗号分隔、每轮热更新。
- **画质选项可增删 + 行内切换画质**：画质选项从引擎白名单固定 10 档改为用户自选子集（落 `config.ini` [录制设置] 自定义画质选项）；GUI 画质监控新增「切换画质」菜单、WEB 新增 `PUT /api/rooms/quality` 端点，选非默认画质按「画质,直播间地址」写回、下一轮循环生效，选择「默认画质」移除画质段回落全局默认。
- **单文件整合版迁移至 `scripts/`**：`douyin_live_recorder_standalone.py` 自根目录迁入 `scripts/`，运行命令加 `scripts/` 前缀，并修复迁移后 ffmpeg 定位逻辑（依次探测脚本同级 → 仓库根 → PATH）。

**🐛 修复的问题**
- **P0 分段录制容器错配**：抖音原画 HEVC 因 TS+分段分支 `-segment_format` 误用 `ipod` 容器，`-c copy` 直接 `AVERROR(EINVAL)` 退出（Windows 退出码 4294967274）；H.264 则静默产出「MP4 内容 + .ts 扩展名」损坏文件。将「输出扩展名 → 内层容器」映射收敛为模块级常量 `SEGMENT_FORMAT_BY_SUFFIX`，新增 `tests/test_record_container.py` 固化断言；另修复 `src/spider.py` 的 `hevc_flv_url` 漏拼 `&codec=h265` 致 h265 判定漏判。
- **flaky 告警根治**：`src/async_http.py` 删除跨循环 `run_coroutine_threadsafe(client.aclose(), ...)` 调度分支（根因：旧循环已停未关时协程永不 await、GC 报 "never awaited"）；`pyproject.toml` 显式过滤第三方 starlette/anyio 弃用告警，pytest 全量 0 警告门禁定稿。
- **GUI 画质切换三缺陷**：键格式不匹配（序号前缀导致反查表 miss）、持久化丢失（写回后编辑器仍持旧快照被整文件覆盖）、显示重置（表格取自子进程旧日志值）——切换后剥离序号前缀查表、写回后同步编辑器快照、显示以配置文件为准。
- **打包缺陷修复**：`pyproject.toml` 的 `[tool.setuptools].packages` 由 `["src"]` 改为 `["src", "src.platforms", "src.proto"]`，修复 `pip install .` 发行包缺失 `src/platforms`（各平台弹幕采集器）与 `src/proto`（抖音 protobuf）的运行时 `ModuleNotFoundError`。

**🛠️ 仓库维护与质量门禁**
- **全仓中文注释补齐**：41 文件 / +1370 行（平均密度 7.6%→20.4%），AST 等价性校验证逻辑零改动；新增 `scripts/check_annotations.py`（注释规范 + AST 等价性校验，三模式）接入 `ci.yml` 的 `static` job。
- **八文件元数据同源同步**：以 `pyproject.toml` 为单一事实源，修正 `AGENTS.md` / `docker-compose.yaml` / `requirements.txt` / `Dockerfile` / `.gitignore` / `.dockerignore` / `.coveragerc-concurrency` 的版本、路径、目录清单与依赖漂移。
- **四语本地化目录补齐**：经 `extract_i18n_strings.py` 补入 5 条缺失串，四目录键集合重一致（各 521 条），`zh_CN.mo` 重编译（`--check` 字节级同步通过）。
- **测试残留自清理**：`tests/conftest.py` 新增 `pytest_unconfigure` 钩子，会话结束自动删除 `tests/_out_live` / `tests/_out_e2e`。

**🧪 测试与验证**
- 全量 `pytest` **858 passed / 2 skipped / 0 warnings**；`pytest tests/test_i18n.py` 34 passed（四目录键集合一致性）。
- `mypy` / `basedpyright`（0 error / 0 warning）/ `black --check` / `isort --check` / `scripts/check_annotations.py` 全绿；`scripts/extract_i18n_strings.py` 缺失 0 条；`scripts/compile_po.py --check` 与 `.po` 同步（522 条）；`scripts/check_version.py` PASS。

### v4.0.9.3 (2026-09-02) — 代码审查 20 项问题全量修复（cookie 缓存并发去重 singleflight 重写 / Web 非 ASCII 密码登录崩溃 / 探针异常留痕与节流自清理 / 64 位 ctypes 句柄截断 / 连接资源生命周期）+ mypy 全仓类型清零（tests / gui_legacy / scripts / standalone）

> 本版本为《代码检查报告》20 项审查问题的全量闭环批次，并完成 mypy 静态类型检查全仓清零（102 个源文件 0 报错，首次覆盖 CI 口径之外的 tests / gui_legacy / scripts 与单文件整合版 standalone）。两项高优先级修复：① cookie 缓存并发去重按 singleflight 模式重写——原实现跨 `await` 持有线程亲和的 `threading.RLock`，同事件循环内的并发协程全部可重入该锁、互斥完全失效，多协程照样并发请求同一网址（恰是本模块要消除的风控触发源）；② Web 面板历史明文密码兼容路径对非 ASCII 密码直接抛 `TypeError`（`hmac.compare_digest` 不支持含中文的 str 比较，`/api/login` 直接 500）。中优先级八项覆盖 Web API 写入口径、备份守护线程紧循环、探针异常留痕与节流字典无界增长、64 位句柄截断、装饰器兜底值类型、HTTP 连接泄漏、重复实现收敛与 Session 生命周期；低优先级八项为冗余与风格清理。**无破坏性变更**（cookie 缓存 TTL / 失败不缓存 / 探针退避与节流 / Web API 路由契约等运行时语义全部保持）。详细根因与验证见 [CODE_WIKI.md](../../CODE_WIKI.md)。

**🍪 Cookie 缓存并发去重重写（高危修复）**
- **根因**：`fetch_cookies` 原实现跨 `await` 持有 `threading.RLock`——RLock 是线程亲和锁，同一事件循环内的并发协程属于同一线程、全部可重入该锁，互斥完全失效，多协程会并发请求同一网址（恰是本模块要消除的风控触发源）。
- **singleflight 重写**：`threading.Lock` 只保护「缓存字典 + 在途登记表 `_inflight`」的同步读写（**锁内绝无 await**）；抢到拉取权的协程负责拉取一次，同循环等待者登记 future 复用同一份结果，跨循环等待者经 `loop.call_soon_threadsafe` 交付（future 非线程安全，禁止跨线程直接 `set_result`）。
- **健壮性**：拉取协程被取消（房间停止/进程退出）时在 `BaseException` 分支立即摘除登记并给等待者交付空结果；等待者带 `timeout + 5s` 余量超时兜底（防拉取线程异常死亡导致永久挂起）；失败不缓存、TTL 失效、`fetcher` 透传等既有语义全部保留。
- 效果：同平台多房间并发时对同一域名不再重复请求访客 cookie，风控触发概率进一步降低。

**🔐 Web 面板与系统托盘缺陷修复（高危 / 中高 / 中）**
- **非 ASCII 明文密码登录 500**：`verify_web_password` 历史明文兼容路径改为 `hmac.compare_digest` 的 UTF-8 bytes 比较（str 比较不支持非 ASCII，历史明文密码含中文时 `/api/login` 直接 500）；PBKDF2 分支顺带删除冗余 `binascii.Error` 捕获（其为 `ValueError` 子类）与未用导入。
- **Web API 写入口径统一**：`PUT /api/rooms` 写入行改用 `normalize_url`——原写入未归一化 URL，与 add/delete/toggle 三处查重口径不一致，PUT 写回的行下一轮可能再也匹配不到。
- **64 位 ctypes 句柄截断**：`web_tray.py` 改用 `ctypes.WinDLL` + 全量 `argtypes`/`restype` 显式声明（`GetConsoleWindow.restype = c_void_p`），修复 64 位下 HWND/HMENU 被默认 `c_int` 截断；模块级 `_KERNEL32`/`_USER32` 单例缓存（写法对齐 `web.py` 惯例）。

**🛡️ 守护线程与探针健壮性（中）**
- **备份守护紧循环**：`config_io.py` 的 `time.sleep(600)` 移出 `try`——原异常分支不等待，check_md5/backup 持续失败时退化成紧循环空转、疯狂刷日志并空耗 CPU。
- **探针异常留痕与复核语义**：`stream_select.py` 的 `_confirm_get_ok` 补 `logger.debug`（含异常类型 + attempt 序号，不再静默吞异常），attempt 0 异常按「重试一次再定罪」隔 `_recheck_delay()` 后重试、两次均异常才放弃复核（HEAD 结论维持通过）。
- **节流字典自清理**：`_throttle_probe` 写入时顺带剔除空闲超过 `_PROBE_MIN_HOST_INTERVAL × 10` 的旧 host，`_probe_last_seen` 不再只增不删（对照 `_probe_backoff` 的过期清理策略，60+ 平台长跑防无界增长）；`mark_ffmpeg_reject`/`clear_ffmpeg_reject` 纯转发包装合并为模块级别名，另抽取 `_is_h265()` 消除两处重复判定。
- **弹幕边车留痕**：`danmaku_monitor.py` 的 `_write_line` 写失败分支补 `logger.debug`，与本模块「异常全吞但必须留痕」约定一致，边车数据不再无迹丢弃。
- **取消信号不再被吞**：`ws_client.py` 心跳任务回收的 `except asyncio.CancelledError, Exception:` 拆分——`CancelledError` 仅吞 hb_task 自身按预期被取消的情形，本协程被取消时原样上抛。

**♻️ 资源管理与兜底类型（中）**
- **装饰器兜底值类型**：`utils.py` 装饰器共用实现收敛为 `_make_trace_error_guard(func, fallback)`，新增 `trace_error_decorator_or_none`（出错返回 `None`），错误日志同时标注函数名与兜底值类型。
- **消除「错误伪装成正常结果」**：`spider.py` 5 个返回 str/tuple 的函数（`get_bilibili_room_info_h5` / `login_sooplive` / `get_sooplive_tk` / `get_winktv_bj_info` / `login_flextv`）由统一 dict 兜底切换至 `None` 兜底——旧实现中 `login_flextv` 失败返回的 dict 曾被 `if new_cookies` 误判为登录成功。
- **重复实现收敛**：`node_install.py` 与 `ffmpeg_install.py` 各自逐字重复的 `unzip_file()` 收敛至 `src/utils.py` 单一实现（含 Zip Slip 校验）；`node_install.py` 两处 `requests.get` 改 `with` 管理关闭连接。
- **Session 生命周期**：`sync_http.py` 新增 `WeakSet` 登记线程级 Session、`close_session()`（当前线程显式释放）与 `close_all_sessions()`（`atexit` 注册，进程退出统一优雅关闭全部连接池）。

**🧹 风格约定 / 环境修复（低）**
- **PEP 758 except 写法定稿**：实测 black 26.x 稳定风格就是无括号形式 `except A, B:`（加括号反而过不了格式门禁），采用报告备选方案并在 `AGENTS.md`「代码风格 → Black」显式记录约定（由 `requires-python >= 3.14` 下限保证语法合法）。
- **venv 幽灵问题修复**：`.venv` 中 editable 安装原指向另一 checkout（`D:\DouyinLiveRecorder-coding`），`pip install -e .` 重装后 `import src.*` 确认解析到本工作区，消除「改了 A 目录、测试跑的是 B 目录」的问题。

**🧹 mypy 全仓清零**
- `tests/test_quality_tiers.py`：5 处 `mock.await_args.args[1]` 前补 `assert mock.await_args is not None`（typeshed 将 `await_args` 声明为 Optional，运行时保证非空但 mypy 无法收窄）。
- `gui_legacy.py`：4 处——悬停效果 lambda 改具名闭包工厂、`command` 参数补 `str | Callable[[], Any]` 注解、`optionxform` 改具名函数 + `setattr` 绕过（对齐 `gui.py` 惯例）、补 `collections.abc.Callable` 导入。
- `scripts/extract_i18n_strings.py`：动态 `getattr` 结果用 `cast` 收敛（`warn_return_any` 门禁），移除已无用的 `type: ignore`。
- **单文件整合版（standalone）**：`douyin_live_recorder_standalone.py` 4 处告警清零——`json.loads` 返回值 `cast`、`_douyu_sign` 补 `isinstance(sign, dict)` 守卫（非 dict 直接返回 `None`，杜绝运行时崩溃）、新增 `PlatformResolver` Protocol 使 `PLATFORM_RULES` 分派表支持 `proxy=`/`cookies=` 关键字调用；导入清理移除未用的 `Callable`。

**🧪 测试与验证**
- `tests/test_cookie_cache.py` 加强：`test_same_loop_reentrant_no_deadlock` 同时断言「并发 gather 5 协程只拉取一次」（旧 RLock 实现下该断言必失败——正是本次修复的目标行为）；26 用例全过。`tests/test_spider_platform.py` 4 个固化旧 dict 兜底行为的断言同步改为 `is None`。
- 全量 `pytest` **806 passed / 2 skipped / 0 failed**；`mypy` 全仓口径（src + tests + 全部入口 + build_exe + scripts）**102 source files 0 issues**（CI 口径 39 文件、报告口径 44 文件、含 tests 94 文件均全绿）；basedpyright errorCount=0 / warningCount=0；black 105 files unchanged；isort 全部合规；compileall 0 语法错误。
- web_tray 实测：`WinDLL` 加载成功、窗口改写链路无异常（headless 下 `GetConsoleWindow` 返回空、按预期跳过）。

### v4.0.9.2 (2026-08-28 ~ 2026-08-30) — Web 面板录制手动控制 / 虎牙·斗鱼蓝光细粒度画质档位 / 停止录制流程日志归档 / 性能审查优化落地（P1~P5）/ 探针退避窗口自愈与虎牙 FLV-first / Web 后台日志 sink 重建 / GUI 父进程日志句柄隔离

> 本版本沿「可控性、画质粒度、高并发性能、可运维性」四条主线：Web 面板移除启动自动录制、新增「开始/停止录制」手动控制（全局开关 + 录制主链 7 处中断点 + ffmpeg 分级优雅终止）；虎牙/斗鱼支持蓝光细粒度档位（蓝光4M/8M/20M/30M 的选档 → 拉流 → 不可用就近降级全链路）；性能审查落地 P1~P5 五项优化（80 房间选源探针耗时 12.7s → 1.15s），并经三轮真机验证根治虎牙冷启动「探针假绿 → ffmpeg 403」死循环（退避窗口对齐主循环 + 录制成功清除退避 + 虎牙 FLV-first）与 Web 后台模式日志写向被隐藏窗口的问题；08-30 起停止录制流程统一把四个运行日志按时间戳改名归档（冲突递增、缺失跳过、句柄先行关闭），GUI 父进程与录制子进程日志句柄隔离根治 `streamget.log` 轮转 WinError 32（录制日志全量静默丢失），i18n 四语目录补齐至 516 条并重编译 `zh_CN.mo`。**无破坏性变更**（配置项与运行时语义完全兼容；虎牙选源顺序反转为 FLV-first、斗鱼保持 HLS-first，属行为变更）。详细根因与验证见 [CODE_WIKI.md](../../CODE_WIKI.md)。

**🎥 Web 面板录制手动控制（新增功能）**
- 全局开关 `main.recording_enabled`（默认 True，CLI/GUI 直跑完全不受影响）：Web 启动录制引擎前先置 False，面板默认**不再自动录制**；点「开始录制」后主循环按 URL 配置逐个拉起房间，配置热加载、并发调度器、弹幕监控全程保持运行。
- 录制主链注入 **7 处中断点**：ffmpeg 轮询（1s 周期）、直下下载 chunk 级、房间线程入口、直下失败判定排除、循环等待期打断、主循环拉起新线程前、线程退出 finally 兜底（`remove_room_from_running` 幂等清理运行列表，保证重新开始后房间能再次拉起）。
- 新增 `POST /api/recording/toggle` 切换端点（处于既有 Bearer 认证中间件覆盖内）与状态快照 `recording_enabled` 字段；前端新增「开始/停止录制」按钮与运行状态标签，仪表盘 2s 轮询持续同步真实态（按钮防重复点击、引擎存活联动禁用）。
- **停止语义为主动分级优雅终止**：轮询命中开关关闭即按「stdin 写 'q'（写完文件尾，TS/FLV/分段不损坏）→ terminate → kill」三级升级（总窗口 30s），进程 wait 回收、注册表注销，无孤儿 ffmpeg；停止中断不计入错误样本（防止误触按 host 熔断与错误背压降容）。
- `recording_enabled` 为会话级运行时开关、不持久化：重启后面板回到停止态，避免从后门重新引入「启动即自动录制」。

**🎚️ 虎牙/斗鱼蓝光细粒度画质档位（新增功能）**
- 画质代码层扩展：`QUALITY_LEVEL` / `QUALITY_MAPPING_BIT` / `QUALITY_CODE_TO_ZH` 由 6 项扩为 10 项（新增 `BD30`/`BD20`/`BD8`/`BD4`）并新增 `BD_SUB_TIERS` 冻结集合；`get_quality_index` 将蓝光子档位折叠到 `BD` 槽位，抖音/TikTok 等按数字 0–5 选档平台的语义完全不变。
- 虎牙：新增 `HUYA_FIXED_TIERS`（ratio 即码率上限 kbps，直接拼在 FLV/HLS URL query 上选档、流地址路径不变）；`exsphd` 档位表优先、`gameLiveInfo.bitRate` 兜底推导可用档；请求档不可用时**就近向下降级**并明确告警（含请求档/房间上限/实际档），无任何更低档时按原画拉流、链路不中断。
- 斗鱼：新增 `DOUYU_RATE_BY_CODE` / `DOUYU_RATE_TO_CODE` / `DOUYU_RATE_DESC`；请求档被限制（如游客态原画被拒）时按全序**本地最多回退 2 档重试**；服务端「就近钳制」的真实档位经 `rate` 字段回采（实测请求 rate=8200 无此档被钳到 rate=4 → 蓝光4M）。斗鱼无 20M/30M 档，选择时按蓝光8M 请求。
- Web 面板画质下拉新增 蓝光30M/20M/8M/4M 四个选项；真机 ffprobe 采样确认各档分辨率/帧率与档位表一致（原画 2560×1440@60、蓝光30M~8M 1920×1080@60、蓝光4M 1080p30、超清 720p30、流畅 450p24）。

**📼 停止录制流程日志归档（新增功能）**
- 触发点两处：Web 面板「停止录制」**即时归档**（进程继续运行，归档后立即重建日志句柄，录制引擎与 Web 服务日志写入不受影响）；进程退出全路径——CLI Ctrl+C / GUI 停止按钮（CTRL_BREAK）/ 控制台关闭 / 磁盘满 / 未捕获异常 / Web 托盘退出——经 `main.py` 的 atexit 统一归档（注册先于两个清理钩子，atexit LIFO 保证归档最后执行，把 ffmpeg 清理等收尾日志一并收进归档文件）。
- 归档规则：四个运行日志（`streamget.log` / `PlayURL.log` / `danmaku_monitor.jsonl` / `web_console.log`）按「原名_YYYYMMDD_HHMMSS.扩展名」改名（时间戳取停止操作发生时刻）；目标冲突自动追加 `_1`/`_2` 序号不覆盖、文件缺失跳过、单文件改名失败仅告警，**绝不中断停止录制流程**；归档后日志写入链路立即恢复，下次录制生成全新同名文件。
- 句柄安全（Windows 下句柄未关 rename 必抛 WinError 32）：loguru 文件 sink 经 `remove()` 先 flush 异步队列再关句柄；弹幕监控边车经 `close_file()` 关闭、下一条事件自动重开；`web_console.log` 关闭改名后重建并重新接管 `sys.stdout/stderr` 与控制台 sink（仅 Web 后台模式绑定；历史遗留未绑定文件仅改名，绝不劫持当前 stdout）。
- 安全守卫：GUI 父进程（`DLR_GUI_PARENT=1`）与测试进程（`DOUYIN_DISABLE_LOG_ARCHIVE=1`）一律早返回，不改名录制子进程正在写或开发者工作副本中的真实日志。

**⚡ 性能优化（审查落地 P1~P5）**
- **P1 探针客户端整轮复用**：`select_source_url` 全部候选共用一支 `httpx.Client`（`finally` 关闭，UA/Referer/Cookie 改逐请求下发）；80 房间 × 10 探针的每轮选源耗时 **12.7s → 1.15s**，并发连接峰值反而 4 → 1。刻意不做全局客户端缓存（虎牙 CDN 按连接预算限流，常驻 keepalive 会与 ffmpeg 拉流争抢预算），并实测证明**禁止为保险关 keepalive**（反而 8 连接 / 72.99ms，收益全退）。
- **P2 `requests.Session` 线程级复用**：`sync_http` 经 `threading.local` 每线程一支 Session（125 个调用点全部受益），实测单请求 11.9ms → 1.47ms。
- **P3 主循环去重容器 set 化**：`url_comments` / `line_list` / `url_line_list` 由 list 改 set（成员检测 O(N²) → O(1)），`url_comments.discard` 取代每行整表重建。
- **P4 调度器计数增量**：熔断窗口与全局错误窗口改增量维护（O(1) 替代持锁下 O(40) 全量求和），缩短锁持有时间。
- **P5 高频正则提模块级常量**：表情模式（约 400 字符）、URL 片段、HLS 带宽、抖音 HEVC 等 5 处函数内 `re.compile` 上提为模块级常量；`update_config_line` 按 key 编译的正则经 `functools.lru_cache` 缓存。

**🐛 问题修复（真机验证衍生）**
- **探针退避窗口自愈（虎牙假绿死循环根因）**：原固定 60s 退避窗口小于主循环默认 120s 间隔——快速失败记入退避后下一轮 T+124s 才到、早已过期，历史日志中「CDN 探针退避中」告警从未出现；改为 `_probe_backoff_window() = max(60s, 循环间隔 + 70s)`，覆盖「单轮等待 = 间隔 + ±5s 抖动 + 错误窗口满 5 次再 +60s」的最坏节奏。
- **录制成功撤销探针退避**：新增 `clear_ffmpeg_reject()` 与失败侧 `mark_ffmpeg_reject` 配对——已恢复的线路不再被窗口内继续跳过、白白回退到次优线路。
- **虎牙选源反转为 FLV-first**：三轮真机实证 HLS 三条 CDN（hs/tx/al）冷启动探针假绿（探针 200/206、ffmpeg 打开即 403），FLV 每轮稳定可用（最长连录 6 分钟）——虎牙候选顺序改为 FLV → HLS → record_url，冷启动假绿损失约 2 分钟 → 0（斗鱼绝不加入，其游客态 FLV 约 70 秒被 CDN 掐断必须 HLS-first）；h265 候选在构建统一候选序列时即剔除，不再白烧探针。真机对比：修复前 5 次秒退、12 分钟才稳定 → 修复后 1 次秒退、2 分钟即稳定。
- **Web 后台模式日志 sink 重建**：loguru 的 sink 在 `add()` 时绑定具体对象、不随 `sys.stderr` 重定向而变——不重建则 DEBUG/WARNING 全部写向被 SW_HIDE 隐藏的控制台，`web_console.log` 只剩 print 输出（实测曾据此把「探针假绿」误判成「校验未执行」）；`logger.py` 新增 `rebind_console_sink()`，`web.py` 后台模式重定向后重建 sink，并补 `sys.stderr is None` 判空（pythonw / 冻结 exe 导入期静默崩溃根治）。
- **Web 录制控制双轮审查修复**：前端状态标签选择器缺陷（容器实为 class 却用 `#id` 选择器、状态永不切换，P1）等 3 处。
- **GUI 父进程日志句柄隔离**：GUI 进程（经 `src.web_config → src/__init__ → src.logger` 导入链初始化文件 sink）与录制子进程双开 `streamget.log`，任一方到达 300 KB 轮转阈值都要先改名，对方句柄未关即抛 `PermissionError: [WinError 32]`——轮转永不成功、录制子进程的文件日志自此全量静默丢失（实测卡在 300031 字节、GUI 面板被 Logging error 刷屏）；`src/logger.py` 新增 `DLR_GUI_PARENT` 环境标记（GUI 进程只写本进程独占的 `gui.log`，绝不创建录制日志文件）与 `child_process_env()`（拉起录制子进程的 env 剔除标记并固定 UTF-8 输出），`gui.py` 在导入任何 src 模块**之前**设置标记；仅 GUI 模式受影响，CLI / Web 单进程录制行为不变。
- **类型修复**：`src/stream.py` 补全 `HuyaGameLiveInfo` TypedDict 的 `bitRate: int` 字段声明并移除 `# type: ignore`（新版 mypy 对未声明键退化类型报 `call-overload`），运行时语义零变化，`mypy src/` 恢复全绿。

**🔧 CI / 工程维护**
- **i18n 四语目录补齐（507 → 516 条）**：日志归档功能引入的 9 条新日志串补入 `zh_CN.po` / `en_US.json` / `en_GB.json` / `zh_TW.yaml`（繁体按既有语汇转换：日志→日誌、文件→檔案、归档→歸檔、句柄→控制代碼），`zh_CN.po` 新增「日志归档模块」分节并重编译 `zh_CN.mo`（`--check` 字节级同步）；提取器复扫缺失 0 条、四语键集一致断言通过。
- **仓库元数据同源清单同步**：九配置文件（`AGENTS.md` / `docker-compose.yaml` / `requirements.txt` / `Dockerfile` / `.gitignore` / `.dockerignore` / `.coveragerc-concurrency` / `pyproject.toml` / `uv.lock`）一致性审计——依赖三处一致（20=20）、`uv lock --check` 同步、Dockerfile（python:3.14-slim + Node 24）≡ CI（python_build=3.14 / node_version=24）、版本链 `check_version.py` 全过；修复 2 处漂移：`.v2c/`（video2code 插件生成目录）补入 `.gitignore` / `.dockerignore` / pyproject 五处工具排除列表 / `.coveragerc-concurrency` / AGENTS 规范清单共 9 个同步点；`.mypy_cache/` 补入 `.dockerignore`（此前 `COPY . .` 构建上下文会误送）。

**🧪 测试与验证**
- 日志归档专项：新增 `tests/test_log_archive.py`（14 用例：改名格式正则锁定、`_N` 序号去重不覆盖、缺失全跳过、单文件改名失败不中断整批、GUI/测试进程双守卫、`reopen_streams` 双态语义、web_console 绑定句柄轮转、hub `close_file` 后惰性重开、sink remove→add 往返幂等、main.py 归档 atexit 注册顺序静态锁）；`test_web_api.py` 增「停止录制触发归档」用例；`tests/conftest.py` 增设 `DOUYIN_DISABLE_LOG_ARCHIVE=1`（pytest 退出并非停止录制事件，不改名开发者真实日志）。
- 新增 `tests/test_quality_tiers.py`（29 用例：子档位映射/索引折叠/虎牙就近降级/斗鱼重试链）、`tests/test_logger_console_sink.py`（3 用例：跟随当前 stderr / 替换而非追加 / None 静默）；`test_stream_select.py` 新增客户端整轮复用与逐请求头、退避窗口覆盖主循环周期、成功清除退避、虎牙 FLV-first 与斗鱼保持 HLS-first 用例；`test_record_failure_feedback.py` 增「停止录制中断不采样」用例；`test_web_api.py` 增录制开关端点用例。
- 全量 `pytest` **806 passed / 2 skipped**（0 警告；较 08-29 新增 15 用例）；black / isort / `compile_po.py --check` / `mypy src/`（Windows + Linux 双平台，`stream.py:609` 已随 bitRate 声明修复）/ `uv lock --check` / `check_version.py` 全绿。类型门禁存 1 处已知遗留（`test_quality_tiers.py` 的 basedpyright 5 处 `await_args` Optional 访问），不影响运行时。
- 三轮真机验证（虎牙 880214 / chuhe、斗鱼 3168536）：退避告警首次出现、FLV 稳定连录 6 分钟、`web_console.log` 恢复完整 DEBUG/WARNING；斗鱼 rate 钳制与回采行为实测吻合；Windows 真机 loguru 链路黑盒验证 `remove → rename → re-add` 归档可行（旧文件内容完整、新同名文件立即重建）。

### v4.0.9.1 (2026-08-27 ~ 2026-08-28) — 高并发调度加固 / 本地化系统修复 / 编译与熔断门禁修复 / CI 工作流优化与重试收敛

> 本版本为 4.0.9 调度体系的审查修复与加固批次，并收尾本地化子系统：全量质量门禁 + 并行代码审查发现并修复多个高危/中危缺陷，i18n 目录经全仓 AST 扫描全量补全至 496 条、解除 i18n 模块语法阻塞并重新编译 `zh_CN.mo`；08-28 追加 CI 工作流优化（重试收敛为复合动作）、PEP 758 格式化随 black 26 落地与仓库元数据八文件同步。**无破坏性变更**（配置项与运行时语义完全兼容）。详细根因与验证见 [CODE_WIKI.md](../../CODE_WIKI.md)。

**✨ 新增功能**
- **Web 配置行级追加 API**：`web_config.py` 新增 `append_config_line(config_file, section, key, value)`，在键/节缺失时按行级文本风格补建（与既有 `update_config_line` 互补），便于缺键配置的安全写入。
- **语言切换写回降级**：`web_api.py` 的 `PUT /api/language` 写回在行级替换失败时自动调用 `append_config_line` 节末追加补建，历史 config.ini 缺 `language` 键时不再恒 500。
- **i18n 四目录全量补全（288 → 496 条）**：AST 扫描全仓运行时 `print()`/`logger.*()` 常量串（47 文件、355 串），新增 204+ 条翻译（并发调度日志、流地址校验全套消息、B站 buvid 认证链、弹幕采集/监控、七渠道推送失败分支、ffmpeg/Node.js 安装、配置读写等）；四语键集完全一致，重编译 `zh_CN.mo`（`--check` 字节级同步）。
- **CI 网络安装重试复合动作（`.github/actions/retry`）**：新增复合动作统一包装 pip / apt / choco / brew 网络安装命令的线性退避重试（`command` / `label` / `attempts` / `backoff` 可参数化），取代两份 workflow 共 13 处几乎相同的内联重试脚本（ci.yml 9 处 + build-release.yml 4 处）——重试策略唯一事实源为 action.yml 一处，调整一处全局生效；经成功/失败双路径模拟验证。

**🐛 问题修复**
- **i18n 本地化系统阻断（高危）**：`i18n.py`（3 处）与 `scripts/compile_po.py`（1 处）的 Python 2 风格 `except A, B:`（含一例三异常逗号）多异常写法改为 `except (A, B):`，解除 Python 3 硬 `SyntaxError`——此前 `i18n` 无法 `import`、`.mo` 无法编译、CLI/GUI/Web 本地化整体失效；修复后受管 3.13 与 3.14 运行时均合法，并重新编译 `zh_CN.mo`（496 条，`--check` 字节级同步）。
- **CI black 门禁（PEP 758 格式化）**：上述 4 处元组括号随后按 black 26.5.1（`target-version=['py314']`，CI 与本地同版本）的 PEP 758 规范化统一为免括号形式（`except A, B:` 与 `except (A, B):` 在 3.14 下完全等价、语义零变化），CI `black --check` 恢复绿色；**此 4 处今后由 black 维护，勿手工改括号**。
- **编译同步门禁恒真（P1）**：`scripts/compile_po.py` 的 `write_mo()` 改为纯内存产出（去除写盘副作用），落盘决策上移至调用方，`--check` 不再「先落盘再读回自比」（此前恒真），改为真实比对已提交 `.mo`；`ci.yml` 的 paths-filter 新增 `i18n/**`，纯翻译变更也会触发 static 门禁。
- **熔断探针租约自愈（高危）**：根治 `PlatformBreaker` half-open 探针泄漏——探针轮以 `continue` 结束且不上报样本时 `_probing` 标志永不复位、该 host 永久熔断直到进程重启；新增探针租约（`_PROBE_LEASE_SECONDS = 60s`）超时自动重新授予，实现自愈。
- **调度成功采样缺口（中危）**：`start_record` 解析成功分支补报 `record_success(record_host)`（与失败分支对称），half-open 探针房间长录期间同 host 其余房间不再持续饿死。
- **直下路径熔断采样缺口（P1）**：`main.py` 直下下载分支「非 200 / 网络异常」失败原在函数内部消化为 `False`、调用方不上报样本，坏线路绕开按 host 熔断被无限重撞；新增 `record_error(record_host)` 补报（被注释/退出标志的中断不计样本）。
- **调度器线程安全 + 类型/日志**：`ConcurrencyScheduler` 配置字段加锁（单次加锁快照 + 锁内写入），消除主线程与 `adjust_loop` 守护线程间理论竞态；`notify.py` 三参 `getattr(main,"scheduler")` 改直接属性访问消除 mypy 假绿、`run_script` 三处裸 `logger.error(e)` 补异常类型与命令上下文。
- **直下日志缺失修复**：`main.py` 的 `direct_download_stream` 非 200 分支补请求 URL、异常分支补 `{type(e).__name__}`（Windows 超时类 `str()` 为空）；`async_http.py` 两处裸 `logger.debug(e)` 规范为带 URL/类型的格式。
- **弹幕参数每轮重置恢复**：`main.py` 内层监测循环顶部恢复 `record_danmaku_args = None`（此前重构合并了轮内重置点）。
- **损坏 YAML 目录致 500**：`_load_yaml_catalog()` 补捕获 `yaml.YAMLError`（非 OSError/ValueError 子类），降级跳过到下一格式。
- **ISSUE_TEMPLATE 版本缺失**：`.github/ISSUE_TEMPLATE` 四个模板 Python 版本下拉补 `Python 3.14`。
- **i18n 提取器两处噪声源**：`scripts/extract_i18n_strings.py` 的 `is_valuable()` 改以花括号块之外的残渣判定（纯占位符模板如 `{color}{text}` 不再误报为缺失）、po 头部空 `msgid ""` 比对前剔除（消除四语一致性「少 1」假阳性）；修正后重跑确认四语目录零缺失（318 条有价值串全在库、各 496 条）。

**🎨 体验优化**
- **前端硬编码中文入翻译字典**：`web/app.js` 约十处硬编码中文字符串改走内嵌四语字典 `t()`（录制/弹幕空态、截断提示、开关/操作 toast、配置/文件列表空态、进入/下载按钮等），英文/繁体界面不再显示简体中文。
- **GUI 崩溃弹窗去重**：`gui.py` 顶层异常不再双弹窗/日志双份堆栈，`_bootstrap_error_sink` 置位标记后 re-raise 触发的 excepthook 据此跳过。

**🔧 CI / 工程维护**
- **CI 工作流优化（ci.yml 重写，job 与门禁语义不变）**：`actions/checkout` v5→v7、`setup-python` v6→v7（与 build-release.yml 对齐消除版本漂移）；apt 安装补强化参数（`DEBIAN_FRONTEND=noninteractive` + `Acquire::Retries=3` + `--no-install-recommends`，更抗网络抖动）；macOS `brew trust aws/tap` 拆为独立幂等步骤、`HOMEBREW_*` 变量改命令内 `export`；头注释补 job 拓扑图与「止于验证、不含部署」职责边界。
- **仓库元数据八文件同步**：requirements.txt / Dockerfile 过时的 `src/danmaku/` 路径注释修正为实际模块位置；`.dockerignore` 补 16 个排除项（本地工具目录 / `uv.lock` / `scripts/` / 双语文档等，镜像上下文瘦身）；`.gitignore` 补 `.mimosa/` 等；pyproject 清理死目录；docker-compose 示例版本对齐 `4.0.9.1`；`AGENTS.md` 模块计数 39→41 并新增 CI/workflow 约定小节。

**🧪 测试与验证**
- 新增 `tests/test_record_failure_feedback.py`（5 → 7 用例）、`tests/test_web_api.py` 缺键补建/边界用例；`test_scheduler.py` 探针租约自愈（15 → 16）、`test_i18n.py` 损坏 YAML 降级并适配 `write_mo()` 新签名。
- 全量 `pytest` **744 passed / 2 skipped**；black / isort / mypy（Windows + Linux 双平台）/ basedpyright 全绿；`compile_po.py --check` 字节级同步、提取器零缺失；两 workflow YAML 结构断言（needs 链 / retry 调用计数 / action 版本计数）通过。

### v4.0.9 (2026-08-23 ~ 2026-08-24) — 高并发多平台录制调度优化 / 录制反馈闭环 / 并发双模式 / Python 3.14 升级与语言键迁移 / 四语本地化目录统一与英式美式分流 / 类型与 CI 质量门禁修复

> 本批改动聚焦高并发（80+ 任务）多平台录制的调度中枢治理、录制侧反馈闭环与 Python 3.14 基线升级。详细根因与验证见 [CODE_WIKI.md](../../CODE_WIKI.md)。

**🚀 高并发调度中枢（新增 src/scheduler.py）**
- 引入 `ResizableSemaphore`（运行期可重置容量）、`PlatformBreaker`（按 host 熔断器，closed→open→half-open 状态机）、`ConcurrencyScheduler`（自适应全局并发容量，默认下限 8 / 上限 128，错误率高时温和降容、永不低于安全下限）、`host_of(url)`。
- 取代旧「全局固定 3 槽信号量 + 单向错误率压制」模型，支持 80+ 任务跨多平台录制、降低排队延迟；单平台接口抖动被隔离降级，不再连锁拖垮全局。
- 仅在 `main.py` / `notify.py` 固定接线点接入，未改写 50+ 平台分派/录制函数，向后兼容；新增配置项「最大同时录制数(0=不限制)」（默认 0=不限制）。

**🔁 录制结果反馈闭环（虎牙 403 死循环根治）**
- 修复录制侧反馈缺失：`check_subprocess` 此前按退出码既不上报失败样本、轮末还无条件上报成功，导致按 host 熔断统计被稀释、永不触发，虎牙房间无限重撞「探针 200 → ffmpeg 403」死线路。
- 现按退出码上报成功/失败样本（按 host）；ffmpeg 快速失败（CDN 拒绝签名）触发 `mark_ffmpeg_reject` 探针退避（60 秒），下一轮改试下一 CDN 候选而非重试同一坏线路（退避白名单仅限虎牙）。
- 控制台状态行改为显示调度器实时并发容量（`_live_network_capacity`），不再误显配置值。

**⚙️ 网络并发双模式（动态调速 / 固定并发）**
- 在自适应容量基础上新增「固定并发」模式：「最大同时录制数(0=不限制)」兼作模式开关——=0 启用动态调速（随活跃任务数自适应、下限 8/上限 128），≠0 忽略动态调速器、容量恒为「同一时间访问网络的线程数」（热更新即时生效、最小 1 槽）。
- 按 host 平台熔断与模式正交，两种模式下均生效；同时录制上限仍由 `scheduler.set_recording_limit` 管控，不受模式切换影响。

**🐍 Python 3.14 升级 + 语言配置键迁移（综合维护）**
- 项目基线由 Python 3.10 提升至 `>=3.14`（`pyproject.toml` / `Dockerfile` / CI 全链路）；修复 `async_http.py` 在 3.14 下 `asyncio.get_event_loop()` 不再隐式创建事件循环的兼容问题。
- `config.ini` 语言键 `language(zh_cn/en)` 统一迁移为 `language`：留空跟随系统语言、非法值回退 en_US、GUI/Web 面板免重启热切换、启动自动迁移旧键。
- 修复 14 个源文件共 21 处 Python 2 风格 `except A, B:` 残留语法，使项目在 Python 3 下可导入/可测试；全量 `pytest` **714 passed / 2 skipped / 0 warnings**，black/isort/mypy/basedpyright 全绿。

**🌐 四语本地化目录统一与英式/美式英语分流**
- 统一 zh_CN.po / en_US.json / en_GB.json / zh_TW.yaml 四份目录为同一 288 条 key 集合（原 282 条 + 补齐 build_exe.py 的 6 条打包/冒烟常量串）。
- 修正 en_US 内部混用的英式拼写（统一为美式 minimizes/minimized/canceled）；en_GB 原是 en_US 克隆，改写为真正英式（minimise/minimises/minimised/cancelled），仅在 4 条拼写相关条目上与 en_US 不同。
- 重新编译 zh_CN.po → zh_CN.mo（compile_po.py --check 确认字节级同步），不影响任何运行时逻辑。

**🧪 类型检查 / CI 质量门禁修复**
- 修复 CI `mypy src/` 两处报错：`i18n.py` 的 `ctypes.WinDLL` 平台门控（`sys.platform != "win32"` 早返回，双端干净）、`src/recorder_status.py` 三参 `getattr` 改为直接属性访问（消除 `no-any-return` 泄漏）。
- 修复 CI `pytest` 在 C/POSIX locale 下 `detect_system_language()` 回退路径未过滤 `("C","POSIX")` 导致断言失败；测试中 4 处 `patch.dict(os.environ)` 改为 `monkeypatch.setenv/delenv`（遵循 AGENTS.md 强制规约，规避 Windows 32767 字符上限溢出）。
- 修复 `src/config_io.py` 的 `read_config_value()` 在 Python 3.14 下含分隔符键 `write()` 抛 `InvalidWriteError` 的写回崩溃（内存完整序列化成功后才落盘，坏键回滚）。
- 全仓 black 26.5.1 + `target-version=['py314']` 重排（剥除 PEP 758 `except (A, B):` 括号），本地 dev venv 升级至 3.14.7；四大门禁在 3.14 环境全绿。

**📦 构建 / 依赖 / 平台适配**
- 版本号 `4.0.8.3` → `4.0.9`（唯一事实源）；`requires-python` 升 `>=3.14`、classifiers 收敛为仅 3.14；新增 `PyYAML>=6.0.3` 依赖（i18n 的 zh_TW.yaml 支持）。
- `Dockerfile` 基础镜像升 `python:3.14-slim-bookworm`、Node.js 源 `setup_22.x` → `setup_24.x`；CI 矩阵同步升 3.14。
- `src/spider.py` 咪咕 `get_migu_stream_url()` 现采用重写版 `migu.js` 输出带 `ddCalcu`/`sv` 参数的完整地址（移除本地过期固定 `sv=10010`）；FFmpeg 下载源 `wweb.lanzouv.com` → `wwasx.lanzout.com` 切换。

### v4.0.8.3 (2026-08-19 ~ 2026-08-22) — 主播名自动更新 / SSL 配置整合 / 四语国际化 / FFmpeg9·Node24 兼容 / 类型安全加固 / start_record 复杂度治理 / 窗口化崩溃加固 / 类型检查缺陷修复

> 本版本在 4.0.8.2 系列修复基础上补齐多项新增能力与底层兼容，并以 mypy / basedpyright / pytest(0 warnings) / black / isort 五工具门禁全绿收口。详细根因与验证见 [CODE_WIKI.md](../../CODE_WIKI.md)。

**👤 主播名自动更新（新增功能）**
- `URL_config.ini` 每次解析到最新主播名时，若与配置不同则自动回写配置文件；主播改名时同步重命名以其命名的录制文件夹及内部全部相关文件（TS/FLV/弹幕 SRT/字幕等同前缀产物），保证路径引用完整。
- 新增 `src/config_io.py:update_anchor_name` + `main.py:rename_anchor_directory`；改名只发生在该房间未录制时（先文件系统、后配置文件，全部成功才切换本轮使用名）；配置开关 `是否自动更新主播名(是/否)`（默认「是」，支持热加载），跳过自定义流地址与空白昵称。

**🔒 SSL / HTTPS 配置整合**
- 旧「是否强制启用https录制」+「是否禁用SSL证书验证(是/否)」合并为单一「是否启用https录制」：开启 = https 拉流 + 跳过证书校验，关闭 = http 拉流 + 默认严格校验。旧键只读迁移写回、不重建。
- 主循环每轮热同步 `set_https_recording` / `set_ssl_verify`；关闭时 `https://`→`http://`（TikTok/YouTube 等 https-only 海外平台保持原样，避免必然拉流失败）。
- 平台级覆盖 `禁用SSL证书验证的平台(逗号分隔)` 仅在 http 模式（需要证书校验时）生效；启动时自动追加必需平台（虎牙直播/B站直播），只追加不移除用户手填项。

**🌐 国际化四语重构 + 即时切换**
- `i18n.py` 重构：多格式目录加载（gettext `.mo` → `<lang>.json` → `<lang>.yaml`）、`SUPPORTED_LANGUAGES`（zh_CN/en_US/en_GB/zh_TW）、`normalize_language()` 别名归一、`set_language()` 热切换（无需重启）。
- zh_CN 目录补全至 282 条；新增 en_US/en_GB/zh_TW 三语翻译；Web 顶栏 + GUI 侧边栏语言选择器即时切换并持久化（Web 经 `GET/PUT /api/language`）；不再依赖 `LANG`/`LANGUAGE` 环境变量。zh_TW 需 PyYAML（缺失仅损失该格式）。

**⚙️ FFmpeg 9.0 / Node 24 兼容基线**
- 全库 ffmpeg 命令核查对齐 FFmpeg 9.0（2026-08-04 发布，TLS 证书验证默认开启），移除已废弃 CLI 参数与死参数 `-v verbose`；`-tls_verify 0` 统一经 `get_effective_ssl_verify` 裁决。
- `src/javascript/migu.js` 全量重写：适配咪咕播放器 mgprtcl.wasm 接口变更（导入函数 3→12、导出名重排、加密因子改由接口下发），修复旧脚本任何 Node 版本下实例化即 `LinkError` 的致命问题；输出完整签名地址（旧版仅输出 ddCalcu 值）。Dockerfile Node 源升级至 24.x LTS。

**🧪 类型安全加固（五工具全绿）**
- mypy tests/ 由 435 errors → 0（自动注解约 420 处 + 人工修复约 60 处真实类型问题）；basedpyright tests/ 0 errors / 0 warnings / 0 notes；pytest **699 passed / 2 skipped / 0 warnings**；black / isort 全项目通过。
- 新增测试覆盖：语言 API 5 个、i18n 新功能 10 个、SSL 平台自动追加 3 个、SSL 新语义 2 个、migu 输出契约 1 个、主播名自动更新 21 个。

**🧹 start_record 复杂度治理（代码质量）**
- `main.py:start_record`（原约 1600 行）的平台分派 if/elif 链（52 平台分支）抽取为独立模块级函数 `_resolve_platform_stream`，录制执行链控制流未动；消除 19 个被掩盖的 `possibly unbound`（移除恒真冗余 `if real_url:` 包装、清理失效 cast、修复 `record_name` 绑定），同时修复「录制链不得嵌套于条件内」反模式。basedpyright 原「过于复杂」错误消除。

**🧩 类型检查缺陷修复（代码质量）**
- `i18n.py`：`import yaml` 加 `# type: ignore[import-untyped]` 忽略可选依赖缺失存根提示（保留「缺失仅损失 YAML 格式」的运行时降级语义，符合 AGENTS.md 约定）；降级分支 `yaml = None` 改为 `yaml: Any | None = None` 显式注解。
- `gui.py`：`messagebox` 由属性式 `_tk.messagebox` 改为显式 `from tkinter import messagebox as _mb` 导入（两处崩溃弹窗），消除 `reportAttributeAccessIssue`；线程钩子 `_thread_dump` 对 `args.exc_value` 为 `None` 时新增 `if args.exc_value is None: return` 守卫，消除 `BaseException | None` 不兼容报错。
- 验证：`mypy i18n.py` → `Success: no issues found`；`basedpyright gui.py` → 0 errors / 0 warnings / 0 notes；`black --check` / `isort --check-only` 通过；运行时行为不变。

**🪟 窗口化运行崩溃可观测性加固（缺陷修复）**
- 修复 `pythonw.exe`（及 `console=False` 冻结 exe）启动 GUI 时**完全无窗口、无任何报错**的问题：根因为 `src/logger.py` 在导入期 `logger.add(sink=sys.stderr, ...)` 遇 `sys.stderr=None` 抛 `TypeError: Cannot log to objects of type 'NoneType'`，于导入链上静默退出。**已加 `sys.stderr is not None` 守卫**，无控制台环境跳过控制台 sink、由 `logs/streamget.log`、`PlayURL.log` 文件 sink 兜底。
- `gui.py` 顶部新增 `_install_crash_sink()`：在**所有风险导入之前**装 `sys.excepthook` / `threading.excepthook`，将未捕获异常（含导入期失败）完整堆栈写入 `%TEMP%/douyin_recorder_gui_error.log` 并尽力弹错误框，根治窗口化静默死亡；UI 回调异常分支改用程序内「运行日志」队列，`__main__` 包 `try/except` 保留控制台原始堆栈。
- 验证：模拟 `sys.stderr=None` 下 `import src.logger` 成功、注册 2 个文件 sink、不抛 `TypeError`；`py_compile` 与 `black --check` 均通过。

**📚 架构文档更新**
- `CODE_WIKI.md` 补全弹幕采集子系统（基类/采集器/5 平台客户端/监控枢纽/SRT/WS/访客 Cookie 缓存/protobuf）、`src/platforms` 与 `src/proto` 模块说明、模块依赖图与设计模式；版本号更正为 4.0.8.3（对齐 `pyproject.toml` 唯一事实源）。

### v4.0.8.2 (2026-08-16 ~ 2026-08-18) — 录制/弹幕/国际化/类型检查 系列修复

> 本批改动集中解决了多个历史遗留的「能跑但录制/弹幕经常失败」类问题，并通过真机实测闭环验证。下分模块概述，详细根因与验证见 [CODE_WIKI.md](../../CODE_WIKI.md)。

**🎯 录制引擎核心修复（影响所有平台）**
- **致命结构 Bug**：录制主链曾被嵌套在 `if headers:` 条件内，导致抖音/斗鱼等无专属请求头的平台**从未真正录制**（仅显示"正在直播中"）。已修复——条件仅控制请求头插入，录制链无条件执行。
- **斗鱼崩溃修复**：`select_source_url` 返回空时不再触发 `UnboundLocalError`（标题变量未绑定），直接告警并等待下一轮；末位候选的 content-type 拒绝与 m3u8 Range-GET 偶发 403 现均支持「重试一次再定罪 / 末位告警放行」，根治斗鱼 HLS 假红与 FLV ~70 秒被 CDN 掐断。
- **流地址校验三层降风控**：新增「探针节流 + 重试抖动 + 被拒后退避（仅虎牙）」机制，消除 CDN 按机器人节奏指纹识别导致的 403 失败循环；校验器与 ffmpeg 双端 User-Agent 现已**一字不差**对齐（指纹自洽，防校验假红/假绿）。
- **HTTPS/SSL 配置整合**：`是否启用https录制`（合并原 `是否强制启用https录制` 与 `是否禁用SSL证书验证(是/否)`）——开启 = https 拉流 + 跳过证书校验，关闭 = http 拉流 + 默认证书校验。对「虎牙直播」平台跳过协议转换（其 `*.hls.huya.com` 仅 http 可用）；TikTok/YouTube 等 https-only 海外平台在关闭时保持 https 原样，避免必然的拉流失败。

**🐯 虎牙专项（多 CDN 选源 + Referer 纠偏）**
- 改为**枚举全部 CDN 候选**（HS/HW/TX/AL），不再固定取首位或固定 TX 优先；统一降为 `http://` 并保留原始防盗链参数，由 `select_source_url` 逐条可达性校验择优，动态规避任意离线线路。
- **Referer 规则已移除**：实测虎牙 CDN 现已反向校验——**带 Referer 一律 403，不携带 Referer 时 HS 线路才 200**。历史上注入的 Referer 规则反成录制失败元凶，已清除。
- App 路径（`get_huya_app_stream_url`）TX 选中时与 `record_url` 一致地做 `tars_mp→huya_webh5`/`bhct→bgct` 参数替换，根治「priority 选源后 TX 仍带原始 `tars_mp` 导致秒级断流」的回归。

**📺 B站弹幕认证链闭环**
- 修复 spi 端点拼写（`/finger/sp` → `/finger/spi`，少写结尾 `i` 导致 200+空 body）；buvid 获取链新增 `www.bilibili.com` 首页 Set-Cookie 备取路径，并区分真实 buvid 与随机 UUID 兜底（标记 `is_fallback`）。
- 弹幕进房包**观众 uid 误传主播 uid** 导致 AUTH 软拒绝（连接保持、0 弹幕）已修复；`_decode_packet` 显式校验 operation=8 回应的 code，非 0 时告警+断开+失效 buvid 缓存（避免被拒 UUID 死循环），并新增 8 秒静默拒绝看门狗兜底。
- 弹幕三元组（OD/BD/UHD app 路径）返回补全，消除原静默跳过。

**🌐 国际化机制修复**
- 补齐缺失的 `zh_CN.mo` 编译产物并随仓库分发；`init_gettext` 改为显式 `languages=["zh_CN"]` 加载，**不再依赖 `LANG`/`LANGUAGE` 环境变量**（Windows 普遍未设置）。中文环境下英文提示（如「IP banned」）现已正确翻译。

**🍪 访客 Cookie 统一缓存**
- 新增 `src/cookie_cache.py`：以「归一化网址 + 代理」为 key 的进程级共享缓存，抖音 ttwid、快手 did 等通用访客 cookie 跨模块/跨房间复用同一份，**杜绝同网址重复拉取触发风控**。

**🧩 架构与质量**
- `main.py` 拆分 6 类功能至 `src/` 子模块（ffmpeg_proc / video_postprocess / stream_select / notify / recorder_status / config_io），经 re-export 保持兼容；弹幕子包 `src/danmaku/*` 扁平化至 `src/`；注释规范落地：全量 `"""` docstring 转为 `#` 行注释。
- 配置健壮性：`config.ini` 不可写时 `import main` 阶段不再崩溃（读回 best-effort）；旧键兼容仅读取不写回；备份旋转删除改为 best-effort。
- 全库 UA 统一升级至 2026 基准（Chrome/141、Firefox/148、移动端 Android 14 Chrome/141），消除过旧指纹。

**🛡️ 平台兼容与运行健壮性**
- **跨事件循环锁误判风控根治**（`src/async_http.py`）：模块级单例 `asyncio.Lock()` 在首个 room 的 `asyncio.run()` 循环惰性绑定后，后续 room 起新循环再次 `await` 会抛 `bound to a different event loop`，被 `async_req` 吞掉返回空串、被 `spider.py` 误判「风控空响应」并级联回退 HTML 抓取失败。现改为随**当前事件循环**缓存/重建 `(lock, loop)` 二元组（与 `_client_cache` 机制一致），`tests/test_async_http.py` 新增 `TestGetClientLock` 锁定该行为。
- **空白异常日志收口**：`async_req` / `_close_all_clients` 及跨循环旧 client 关闭处原为 `logger.debug(e)`，Windows 下异常 `str()` 为空时打出空白日志、无法定位；全部改为带 `type(e).__name__`（必要时含 URL）。
- **平台兼容修复**：`web.py` 的 ctypes 3.13+ 兼容（`windll` 已移除）+ 64 位 `HWND` 截断导致控制台窗口隐藏失败，改用 `ctypes.WinDLL` 并显式声明 `argtypes`/`restype`；`main.py` 修复 PATH 拼接覆盖后续追加/重复插入（改用实时 `os.environ["PATH"]` 并去重）；`msg_push.py` 修复 `tg_bot` 未绑定变量（`NameError` 崩溃）与 Telegram 业务失败（`{"ok": false}`）漏检，成功标识改为 chat_id。

**🧪 静态检查 / CI 加固**
- mypy / basedpyright 在 `src/` 与 `main.py` 全面清零（含 spider.py / sync_http.py / web_api.py `_FAILED_LOGINS` 补全 `deque` 类型参数消除 10 处级联告警）；`main.py` 的 `get_startup_info()` 改为返回 `object | None`（`sys.platform == "win32"` 门控保留）以根治 Windows 专属 typeshed 符号跨平台 `TYPE_CHECKING` 别名误报；`gui.py` / `build_exe.py` / `web.py` / `msg_push.py` 同期 basedpyright 0/0/0、mypy 通过。
- 脚本健壮性：`scripts/check_coverage.py` 修复全局覆盖率 < 50% 时门禁被跳过、临时文件残留、`subprocess.run` 缺 `encoding`（Windows 非 UTF-8 locale 崩溃）；`scripts/smoke_test.py` 修复 Windows GBK 控制台 `UnicodeEncodeError` 崩溃与常量重定义、失败标记改 ASCII、新增 `_safe_print` 容错。
- CI `lint` job 运行 Python 由 3.12 升到 3.13（与 `target-version` 最高值对齐，消除 AST 安全校验告警噪声），`black --check .` 格式违规已手工修复。
- 全量测试约 635 passed / 2 skipped（排除已知沙箱删除保护项）。

### v4.0.8.1 (2026-08-01 ~ 2026-08-09) — 注释规范 / 冒烟测试 / GUI 优雅退出 / 校验修复 整合

- 模块/函数说明统一使用 `#` 行注释，不再使用三引号 `"""` 文档字符串。
- 全量审查通过：`compileall` / `black`(行宽120) / `isort` / `mypy`(src/) / `pytest` 全绿（417 passed，无回归；08-01 增量 78 passed，`ruff` 亦通过）；修复 black 格式违规 2 处。
- ⚠️ **构建 Bug 修复（`pyproject.toml`）**：`email="ihmily@github"` 非合法 IDN 邮箱，新版 setuptools 拒绝构建、`pip install .` 必失败；已改为 `ihmily@users.noreply.github.com`（CI 裸装未触发，**本地开发必踩**）。

**新增 Web/接口冒烟测试工具**
- `scripts/smoke_test.py`（**零依赖、配置驱动**）：支持 GET/POST、`base_url` 拼接、期望状态码、文本/JSON 断言；输出控制台/JSON/HTML 报告；失败退出码非 0。默认用例 `scripts/smoke_web.json` 探活 Web 面板 `http://127.0.0.1:8000`。

**GUI 停止录制优雅退出加固**
- **根因**：`pythonw.exe` 启 GUI 时 `sys.executable` 指向无控制台的 pythonw，其拉起的录制子进程也无控制台 → `AttachConsole` 必失败、CTRL_BREAK 结构性不可达；现检测到 pythonw 时改用同目录 `python.exe`（console 子系统）启录制核心。**打包版（CLI exe `console=True`）不受影响**。
- CTRL_BREAK 失败改 `taskkill /F /T /PID` 整树终止（连同 ffmpeg 清理），日志如实区分「优雅退出」与「硬杀路径」。
- 实测：pythonw 父进程复现后 `AttachConsole` 成功、`SIGBREAK` 处理器触发（`signum=21`）；另 Python 3.13 的 `time.sleep()` 不被 CTRL_BREAK 唤醒（走 pending-call 机制），因 `main.py` 录制主循环无长 sleep（≤5s），15 秒窗口内 `safe_exit` 必执行清理。
- ⚠️ **遗留（未改）**：旧 `gui_legacy.py` 用 `CREATE_NO_WINDOW` 启子进程，`send_signal(CTRL_BREAK_EVENT)` 静默无效，优雅停止从未生效（每次等 15 秒超时强杀）；**建议迁移到 gui.py**。

**流地址校验修复（HLS/代理/日志）**
- 空白日志收口：`get_response_status` 异常日志现带 URL 与异常类型（如 `ConnectTimeout`/`TimeoutError`），消除 Windows 下 `socket.timeout` 的 `str()` 为空只打空白。
- m3u8 误判修复：HEAD 探测范围从 `400/401/403/405` 扩至**含 404 的所有非 2xx**；对 `.m3u8` 一律补 `Range: bytes=0-0` GET 探测（200/206 即判可达），避免可用 HLS 源被误回退 FLV。
- `_validate_stream_url` 新增 `verify` 参数沿用全局 SSL 开关，所有失败路径记 warning（URL + 异常类型/状态码/content-type）。
- `select_source_url` 新增 `proxy_addr` 并透传三处校验，修复 TikTok 等需代理平台直连校验超时误判不可达。

**抖音录制增强**
- 支持 5 种 URL 格式：网页/App 直播间、抖音号拼接（含 VR）、App/网页端主播主页。
- 主播主页（格式 5）直接提取 `sec_user_id` 跳重复下载，请求数 4→3；主页类链接现正确透传 `proxy_addr`/`cookies`（修复静默丢失）；新增 `sec_user_id → 抖音号` 进程级缓存（30 分钟 TTL）。
- CDN 对 HEAD 返 4xx 时补 `Range` GET 探测；`web/enter` 偶发 `status_code=10002` 首次失败后静默重试一次，跳过约 1MB HTML 兜底抓取；删除死代码 `get_douyin_stream_data`。

### v4.0.8 (2026-07-30) — Web 面板 / 画质监控 / 代理与类型修复

- **新增 Web 管理面板**（`web.py`+`src/web_api.py`+`src/web_config.py`+`web/`）：仪表盘、直播间管理、配置编辑、SSE 日志推送。
- **新增 GUI 画质监控**：实时检测实际画质是否匹配设置，覆盖抖音/TikTok/快手/虎牙/斗鱼/B站/网易CC 七平台。
- **配置项新增**：`web_show_console`（后台隐藏运行）、SSL 证书验证全局开关（config.ini）、日志文件开关。
- **连接优化**：HTTP 客户端按 (代理, verify, http2) 维度复用连接池；代理检测从联网探测改为读本地系统代理配置。
- **缺陷修复**：`trace_error_decorator` 同步装饰器误用于 71 个异步函数致错误捕获失效；`asyncio.run()` 致 httpx 跨事件循环复用问题；多个 IndexError/KeyError/类型错误。
- **凭据清理**：硬编码过期凭据改自动获取（抖音 ttwid、快手 did、Twitch Client-Id 等）。
- **构建/依赖**：Dockerfile 升 Node.js 22 LTS、非 root 运行；新增 `pydantic>=2.0.0` 依赖声明；全项目类型检查（Pyright/Pyrefly/basedpyright）清理。

### v4.0.7 (2025-10-24)

- 修复抖音风控无法获取数据问题
- 新增 soop.com 录制支持
- 修复 bigo 录制

### v4.0.6 (2025-01-27)

- 新增淘宝、京东、faceit 直播录制
- 修复小红书直播流录制以及转码问题
- 修复畅聊、VV星球、flexTV 直播录制
- 修复批量微信直播推送
- 新增 email 发送 ssl 和 port 配置
- 新增强制转 h264 配置
- 更新 ffmpeg 版本
- 重构包为异步函数！

### v4.0.5 (2024-11-30)

- 新增 shopee、youtube 直播录制
- 新增支持自定义 m3u8、flv 地址录制
- 新增自定义执行脚本，支持 python、bat、bash 等
- 修复 YY 直播、花椒直播和小红书直播录制
- 修复 b 站标题获取错误
- 修复 log 日志错误

### v4.0.4 (2024-10-30)

- 新增嗨秀直播、vv星球直播、17Live、浪Live、SOOP、畅聊直播、飘飘直播、六间房直播、乐嗨直播、花猫直播等 10 个平台直播录制
- 修复小红书直播录制，支持小红书作者主页地址录制直播
- 新增支持 ntfy 消息推送，以及新增支持批量推送多个地址
- 修复 Liveme 直播录制、twitch 直播录制
- 新增 Windows 平台一键停止录制 VB 脚本程序

### v4.0.3 (2024-10-05)

- 新增邮箱和 Bark 推送
- 新增直播注释停止录制
- 优化分段录制
- 重构部分代码

### v4.0.2 (2024-09-28)

- 新增知乎直播、CHZZK 直播录制
- 修复音播直播录制

### v4.0.1 (2024-09-03)

- 新增抖音双屏录制、音播直播录制
- 修复 PandaTV、bigo 直播录制

### v4.0.0 (2024-07-13)

- 新增映客直播录制

---

> 以下条目由根文档滚动归档迁入（2026-10-18），内容与迁入前逐字一致。

### v4.2.0 (2026-09-12 ~ 2026-09-15) — 代码审查全量修复（~120 项·安全/并发/平台）+ 斗鱼「只出 SRT 无视频」根因定位与 HLS 分片层假绿探针 + 选源加固 + start_record 命令构造/平台分派单一定义点重构 + 仓库元数据同源同步与四语本地化一致性修复 + mypy 门禁扩面（范围下沉 `[tool.mypy].files`）与 6 处类型缺陷修复 + Linux CI 只读用例修复

> 本版本（v4.2.0，2026-09-12 ~ 09-15）为一次覆盖安全、并发、平台层与门禁的综合性修复与加固周期。核心修复：① 定位并修复斗鱼等平台「仅生成弹幕 SRT、无视频文件」——HLS 播放列表层恒返 200，但边缘节点媒体分片全 404，ffmpeg 零媒体段产出；弹幕链路仅依赖 `room_id` 与视频解耦，故 SRT 照常写出。新增 HLS 分片层探针 `_probe_hls_segment`（把「列表 200」与「可录制」解耦）与三方向选源加固（配置兜底 / 观测增强 / 同源 FLV 候选回退）。② 收敛 `start_record` 五路 ffmpeg 命令构造为单一定义点、平台分派由 53 层 `elif` 改为分发表驱动，行为零差异（黄金快照 + 分派快照逐字节/逐项比对）。③ 完成 `CODE_REVIEW_FIX_1`（F-01~F-25，22 项落地 + 3 项暂缓）与 09-12 代码审查全量修复（约 120 项：SHA256 钉定、原子写、解压炸弹防护、singleflight 并发、斗鱼粘包 / B站看门狗 / Shopee 等平台修复）。④ 仓库元数据（pyproject 排除目录 / .gitignore / .dockerignore / AGENTS.md）同源同步，并修复 en_GB 目录 21 条误填繁体中文，四语目录重校准至 594 条一致。⑤ mypy 门禁范围下沉到 `pyproject.toml [tool.mypy].files` 单一事实源（`src/` → 全量代码含根入口 / `build_exe.py` / `scripts` / `tests`），并修复 6 处此前长期逃逸的类型缺陷——其中 `gui.py` 子进程自然结束后的 UI 收尾路径**必抛 `NameError`**（除该收尾路径外无功能行为改动）；另修复 Linux CI 上「只读配置」用例因原子写 `os.replace` 只校验目录权限而失效的问题。**无破坏性变更**（运行时语义全部保持）。详细根因与验证见 [CODE_WIKI.md](../../CODE_WIKI.md)。

**🐛 修复的问题**
- **斗鱼「只出 SRT、无视频」根因定位 + HLS 分片层假绿探针**：HLS 播放列表层恒返 200，但媒体分片落在另一边缘节点且全 404 → ffmpeg 拉到零媒体段、零字节产出；弹幕链路仅依赖 `room_id` 与视频解耦，SRT 照常写出。新增 `_probe_hls_segment()`（列表层 GET → 跟随 master 变体 → 对**末行分片**发 `Range bytes=0-0` 探测；分片 4xx/5xx 明确拒→不可达的「假绿」，200/206→可达；解析不出分片时**保守放行**），接入 `_validate_stream_url`，把「列表 200」与「可录制」解耦。
- **选源加固（配置兜底 / 观测增强 / 同源候选）**：`_hls_selection_config()`（经 `getattr(main, "hls_collection_enabled"/"hls_collection_exclude_platforms", 默认)` 读取，默认可达、容忍逗号字符串、缺失/类型异常不再 `AttributeError` 中断选源）；`_same_origin_flv()`（按 `?` 前路径比对、`.m3u8`↔`.flv` 互认，识别同 token FLV 供 HLS 分片全死后回退）；`_log_source_choice()`（「选源结论」单行日志，覆盖回退/命中/无可用源三路径）。
- **代码审查全量修复（09-12，约 120 项）**：H-1 SHA256 钉定（`ffmpeg_install`/`node_install` `_sha256_of_file`/`_check_or_record_zip_sha256`，蓝奏云 `FFMPEG_LANZOU_SHA256`）；C-1 Web 黑名单绕过（`req.key.strip()` + `_DANGEROUS_CONFIG_KEYS_FOLDED`）；utils 解压炸弹防护（单文件 4GB / 累计 8GB / 压缩比 100x）；H-2 singleflight 隔离锁内 await + GUI 6.2 全修（SMTP 头注入 `_reject_smtp_newline`、会话代号、画质表去重）；URL scheme 白名单 `is_safe_http_url`、JS/子进程走 `run_js_async`/`run_node_script_async`；C-2 斗鱼粘包 `offset+=full_len+4`；C-3 only_fans=False；H-4 B站看门狗 `spawn_danmaku_task(self._auth_watchdog(self._ws))`；H-5 Shopee 清除路径 finally `_not_record_prefix`；H-3 `websockets>=14.0`；H-6 原子写（`config_io._atomic_write_text` + `web_config._config_write_lock`）；standalone 两级终止（terminate→wait(3s)→kill）；6 处 ffmpeg 路径补 `record_finished=True` 触发 30s 快检；`data={}` 视为有效请求体。
- **CODE_REVIEW_FIX_1 批量修复（F-01~F-25）**：main.py F-02 移除死 import（`converts_m4a`/`segment_video` 函数保留于 `video_postprocess.py`）、F-03 直下流 `finally` 仅当零字节才清理残留；gui.py F-04~F-09 会话代号闭环 / 画质表去重 / crash sink 禁 `import src` / 本地原子写（不 import `src.config_io` 以免触发 GUI 进程内 main 初始化）；msg_push.py F-24 ntfy 真实推送加守卫；spider.py F-10 `_read_tiktok_guest_cookie` 须插在 `@trace_error_decorator` 之上（往「@decorator+def」间插代码会劫持装饰器归属）、F-11 多参 print 改 logger 拼接、F-19 ab_sign 默认真随机；web_config.py F-23 行内注释引号优先 + 原子写；utils.py F-16 `read_ini_value` 不写回 + F-25 JS 签名脚本哈希钉定（`_JS_SHA256_EXPECTED`，7 脚本，默认告警、`DLR_JS_STRICT_HASH=1` 拒绝）。
- **F-13 抖音 signature 保持不编码**：对照上游 `dart_simple_live` 确认其直接字符串拼接、不 `encodeComponent`，与本仓逐字一致；贸然加 `quote()` 会让本端成为全网唯一异类指纹。用 `tests/test_douyin_signature_encoding.py`（4 例）锁定「原样拼接、无百分号编码」契约。
- **F-12 sync_http SSL 作用域收窄**：`CERT_NONE` 上下文与 opener 由 import 期常驻改为惰性构造；新增 `sync_req(..., ssl_verify=None)` 单次覆盖（透传 urllib 与 requests 两路径）。修正原风险描述——`sync_req` 调用点全部位于 `src/spider.py`，生产链路无任何 `set_ssl_verify(False)`，CERT_NONE 路径在生产不可达。
- **check_annotations 违规修复**：`tests/test_start_record_command_golden.py` 的 `class _Cap:` 三引号 docstring 改为 `#` 行注释（符合「禁 docstring」约束）；并修一处 `main.py` 只监测不录制分支误写 `main.recording_enabled`（模块级 `main` 是入口函数非模块对象，必抛 `AttributeError`）。
- **mypy 门禁扩面 + 6 处类型缺陷修复（09-15）**：起于 CI typecheck 的 3 个报错，进而发现门禁只覆盖 `src/`，根目录入口与 `tests/` 从未被检查。修复：`src/platforms/huya.py` 补 `import i18n`（原 `except` 分支调用 `i18n.tr()` 却漏导入，帧解析异常时抛 `NameError` 掩盖真因）；`src/async_http.py` `_get_client` 复用分支改为在临界区内直接保存 `reused` 实例以完成类型收窄；`src/spider.py` liveme `lm_s_sign` 补 `str()`（`sign_data` 为 `dict[str, object]`）；`gui.py` 3 处——补 `from src.logger import child_process_env, logger`、`_has_unsaved_config_edits` 返回 `bool(...)`，以及**子进程自然结束后的 UI 收尾路径必抛 `NameError`**（`_process_ended(session_id)` 的 `session_id` 未定义）：修复未简单删参数（那会丢掉「丢弃旧会话迟到回调」的保护），而是把日志队列结束哨兵由裸 `None` 改为携带会话代号 `(session_id,)`，UI 线程取出后交 `_process_ended` 校验。
- **Linux CI 只读用例修复（09-15，仅测试与文档改动）**：`test_read_config_value_missing_key_readonly_ok` 原用 `cfg.chmod(0o444)` 制造「不可写」，但 `read_config_value` 的写回已改为 `_atomic_write_text`（同目录临时文件 + `os.replace`）——`os.replace` 只校验目标**所在目录**的写权限、与目标文件权限位无关（root 还会整体绕过权限位），故 Linux 上写回照样成功；而 Windows 的目标文件只读属性会让 `replace` 直接失败，于是「本地 Windows 过、Linux CI 挂」。改为 `monkeypatch.setattr(config_io.os, "replace", _deny_replace)` 仅对目标配置路径抛 `PermissionError`、其余调用透传，跨平台稳定复现「写回被拒 → 记 warning + 返回默认值 + 原文件不被写入」降级分支；`AGENTS.md` 同步新增「只读用例不得只靠 `chmod`」约定，并区分 `config_io`（原子写）与 `utils.update_config`（直写）两种写回路径的用例写法。

**✨ 新增功能 / 改进**
- **start_record 命令构造与平台分派单一定义点（F-01）**：五路内联 `command=[]` 收敛为模块级 `_build_ffmpeg_output_args` / `_build_ffmpeg_input_args` / `_build_record_output_path` / `_ffmpeg_network_tuning`，容器映射全查 `SEGMENT_FORMAT_BY_SUFFIX`（零裸字面量）；`_resolve_platform_stream` 的 53 层 `elif` 改为 `_PLATFORM_RESOLVERS` 分发表（52 个平台各抽 `_resolve_<host>()`，共享 `_PlatformResolveContext`），新平台接入 = 追加一个处理函数 + 一条表项。附带修正两处行为漂移（TS 非分段无条件转 MP4、准备提示打印非分段文件名）。
- **JS 签名脚本哈希钉定（F-25）**：`get_compiled_js` 读原始字节比对 `_JS_SHA256_EXPECTED` 基线，默认告警不阻断、`DLR_JS_STRICT_HASH=1` 拒绝执行，收敛签名脚本被篡改的运行期面。
- **F-14 protobuf 兼容护栏**：本环境无 protoc，不重新生成 `douyin_pb2.py`（生成物 DO NOT EDIT）；改为 CI 前置 `tests/test_proto_runtime_compat.py` 断言「声明区间含上限 / runtime 满足区间 / runtime 不早于 gencode / 可 import 且 PushFrame 往返正常」，升到 8.x 立即变红提示先用同代 protoc 重新生成。
- **mypy 门禁范围下沉为单一事实源（09-15）**：`pyproject.toml [tool.mypy].files` 固化为 `src` + 根入口（main / gui / web / i18n / msg_push）+ `build_exe.py` + `scripts` + `tests`；`ci.yml` typecheck 由 `mypy src/` 改为**无参数 `mypy`**，本地与 CI 跑同一条命令（显式传参会覆盖 `files`，只能排障收窄用，门禁结论以无参跑法为准）。同步补齐 `tests/` 15 处已漂移注解（含 `test_start_record_command_golden.py` 12 处缺注解、generator fixture 返回类型 `Iterator`→`Generator`、type ignore 需同时压制 mypy `assignment` 与 basedpyright `method-assign` 两种码）。

**🛠️ 仓库维护与质量门禁**
- **pyproject 排除目录同源补全**：`logs`/`backup_config` 原先只进部分工具——现已补齐到 black `.exclude`、isort `extend_skip`、mypy `exclude`、basedpyright `exclude`、coverage `omit`，五处统一「运行期产物目录（与 .gitignore/.dockerignore 同源维护）」注释。`.coveragerc-concurrency` 的 omit 一并对齐。
- **.gitignore / .dockerignore 通配化**：移除已不存在的 `PERF_REVIEW_2026-08-28.md` 等逐文件名条目，改为 `PERF_REVIEW_*.md`/`CODE_REVIEW_*.md`/`DIAGNOSIS_*.md` 三组通配；.dockerignore 新增 `*.jsonl`。AGENTS.md 补 `.gitignore`/`.dockerignore` 两个条目与 `logs/`/`downloads/`/`backup_config/` 运行期目录、根文档 `CODE_REVIEW_FIX_1.md`。
- **四语本地化一致性修复**：修复 `i18n/en_GB.json` 21 条值误填繁体中文（弹幕解析异常 7 条 + ffmpeg/Node 安装 SHA256 提示 14 条），按「en_GB 与 en_US 差异仅限拼写」回填英式英语；复核 `zh_CN(.mo)`/`en_US`/`en_GB`/`zh_TW` 四目录均 **594 条**键集两两零差异，en_US/en_GB 无中文残留、zh_TW 无未译；`zh_CN.mo` 重编译（595 条），`scripts/compile_po.py --check` 字节级同步通过。
- **仓库元数据同步**：`AGENTS.md` / `docker-compose.yaml` 示例版本 `4.1.0`→`4.2.0`；`config/config.ini` 在 `[Cookie]` 节新增 `tiktok_guest_cookie = `（F-10 配置覆盖键槽）；requirements.txt 与 pyproject 依赖逐条核对一致（含 `protobuf>=6.31.1,<8` 上限与 `websockets>=14.0`）。

**🧪 测试与验证**
- 全量 `pytest` **974 passed / 2 skipped / 0 failed**（909→929→944→974 递增）；前端 `node --test tests/frontend/*.mjs` 6 passed；`tests/test_stream_select.py` 新增 15 例（分片探针 + 加固）、`tests/test_platform_dispatch.py` 16 例、`test_douyin_signature_encoding.py` 4 例、黄金快照 `test_start_record_command_golden.py` 20 例。
- `black --check --line-length 120 --target-version py314 .` 134 文件全绿；`isort --check-only` 全绿；`scripts/check_annotations.py` 0 违规（平均密度 22.1%）；`scripts/compile_po.py --check` 同步；`scripts/extract_i18n_strings.py` 运行时缺失 0 条；`scripts/check_version.py` PASS；mypy/basedpyright 改动文件 0 error。
- 09-15 门禁扩面后：无参数 `mypy` **115 files 0 问题**（覆盖 src + 根入口 + `build_exe.py` + `scripts` + `tests`）；`pytest -q` 仍为 **974 passed / 2 skipped**；`pytest tests/test_config_io_readonly.py` 15 passed（CI 976 collected 一致）；Linux CI 由 1 failed / 975 passed 恢复全绿。

### v4.1.0 (2026-09-10 ~ 2026-09-11) — P0 修复 ffmpeg `-reconnect*` 缺值与 HLS 无限重连（直播只出字幕无视频）/ 代码审查 28 项修复 / 遗留 8+4 项推进 / i18n 形参日志 242 处全量迁移 / Web 面板窄视口修复 / 四语本地化补全

> 本版本（v4.1.0，2026-09-10 ~ 09-11）修复两处 P0 录制链路缺陷：① ffmpeg `-reconnect*` 选项移入 `-i` 之前时丢失布尔值 `1`，真实录制输入未打开即退出（返回码 -22）；② `-reconnect_at_eof 1` 对 HLS(m3u8) 输入在**播放列表层无限重连**，hls demuxer 永远拉不到媒体段——直播表现为「只产出了弹幕 SRT、无视频文件」。同期推进代码审查 28 项修复、遗留 8+4 项（hls.js 钉版 / TLS 拆流 / 音频容器对齐 / `gui_legacy.py` 删除 / 弹幕落盘移出事件循环 / i18n `tr()` 接口等）、242 处形参日志 f-string → `i18n.tr` 全量迁移、Web 面板窄视口错位修复，并完成八文件元数据同源同步与四语本地化补全（521 → 539 → 544 键）。**无破坏性变更**（录制/弹幕/网络/推送运行时语义全部保持）。详细根因与验证见 [CODE_WIKI.md](../../CODE_WIKI.md)。

**🐛 修复的问题**
- **P0 ffmpeg `-reconnect*` 缺值 → 录制启动即 -22（EINVAL）**：09-10 审查重构把 `-reconnect_delay_max 60 / -reconnect_streamed / -reconnect_at_eof` 从 `-i` 之后移至之前时，后两个选项的布尔值 `1` 丢失，ffmpeg 把下一个选项名当作取值（`Unable to parse ... as boolean`）、输入未打开即退出；`-reconnect_delay_max 60` 因带值幸免。已在 `main.py` 补回取值，并同步修正 `_FFMPEG_ERRNO_HINTS[-22]` 文案（容器错配之外新增「输入选项解析失败」成因）。
- **P0 HLS(m3u8) 输入禁用 `-reconnect_at_eof` → 直播只出字幕无视频**：m3u8 播放列表文件本身的 HTTP 响应结束即 EOF，该选项令 http 层在列表下载完处无限重连（实测特征：连续 `Will reconnect at <size> in N second(s), error=End of file`，1/3/7/15/31s 指数退避、无次数上限），hls demuxer 永远停在「待列表」阶段、一个媒体段都拉不到——ffmpeg 常驻不退出、视频零字节（`-loglevel error` 下无任何报错）。**受影响的正是抖音/斗鱼等 HLS 优先选源的房间**（虎牙走 FLV-first 不受影响）。修复：m3u8 输入在命令构造处移除该参数对（`main.py` 与 `scripts/douyin_live_recorder_standalone.py` 三处定义点同步），FLV 输入保留（CDN 掐断长连接时在 EOF 处重连续写同一文件）。对照实验：同命令加 `-t 10` 限时 60s 仍不退出且零字节产物；去掉该选项后 10s 录制 9MB 正常退出。
- **代码审查 28 项修复（2026-09-10）**：ffmpeg 命令 `-reconnect*` 确立「位于 `-i` 之前且每个选项紧跟取值」；录制信号量先于 `Popen` 获取、启动段纳入 `try/finally` 防槽位泄漏；`process.wait(timeout=30)` 超时补 `kill()` 兜底；弹幕 SRT 文本注入转义（`_sanitize_srt_text`：`\n`→空格、`-->`→`->`，杜绝伪造时间轴）；弹幕采集器 `stop()/_run()` 握手顺序与 `_shutdown` 限时（防线程与 SRT 句柄双泄漏）；敏感配置掩码（`web_config.py` 键名正则 + `web/app.js` 密码框 + `utils.mask_credentials`）；探针末位候选放行语义对齐；`data={}` 空字典视为有效请求体；`src/ttwid.py` 非阻塞失败改串行重取；覆盖率门禁「模块查不到」改判失败等。
- **Web 面板直播间列表窄视口错位**：`table-layout: fixed` + 地址/名称列单行省略（悬停可见全 URL）+ ≤768px 横向滚动兜底，消除窄窗/高 DPI 下表头竖排、按钮溢出卡片、长 URL 折行三种错位。

**✨ 新增功能**
- **i18n `tr()` 形参接口 + 242 处全量迁移**：`i18n.tr(template, **kw)` 先查表再插值——修复 f-string 在查表**之前**完成插值、目录里含占位符键永远匹配不上、翻译静默退化为原文的根因；27 个文件 242 处形参日志改写为 `tr()`，四语目录占位符同步统一（键集 539 → 544）。
- **Web API 鉴权加固**：中间件统一注入 `X-Content-Type-Options: nosniff` / `X-Frame-Options: DENY`；新增公开端点 `GET /api/auth/status` 暴露认证开关与警告文案。
- **hls.js 钉版 1.7.2**：`index.html` 的 `hls.js@latest` 钉到具体版本（jsdelivr CDN 供应链风险收敛，与 flv.js 钉版惯例对齐）。

**🛠️ 仓库维护与质量门禁**
- **遗留 8+4 项推进**：8 项决策类全部实施——hls.js 钉版、`http_config` TLS 校验拆「拉流专用 / 控制面通用」两路径、纯音频平台扩展名/容器/编码三方对齐（`.m4a`+aac+ipod / `.ts`+aac+mpegts）、notify 脚本 300s 超时 `kill` 兜底、Web 鉴权模型文档化、删除 `gui_legacy.py`、弹幕 SRT 落盘移出事件循环（`queue.SimpleQueue` + 独立写盘线程）、i18n `tr()` 接口；4 项真机验证类保守实施并补桩测试（`spider._safe_loads`JSON 安全解析 + URL scheme 白名单、`ws_client` 心跳超时兜底、`proxy` IPv6 字面量、`video_postprocess` 超时分类型告警）。
- **元数据同源同步**：`uv.lock` 项目版本对齐 4.1.0（73 包依赖图未动）、`DouyinLiveRecorder.egg-info` 重新生成、`AGENTS.md` / `docker-compose.yaml` 等八文件版本与依赖核对无漂移、`scripts/check_version.py` PASS。
- **四语本地化补全**：经 `extract_i18n_strings.py` 补入修复期新增串，四目录键集合完全一致（各 544 条），`zh_CN.mo` 重编译（545 条含头部空 msgid，`--check` 字节级同步通过）。

**🧪 测试与验证**
- 全量 `pytest` **907 passed / 2 skipped / 0 warnings**（870 → 899 → 902 → 907 递增）；`tests/test_ffmpeg_reconnect_args.py` 新增第三个不变量类（AST 断言 m3u8 守卫存在于 main.py + standalone 全部定义点）。
- `scripts/extract_i18n_strings.py` 缺失 0 条、四语目录零差异；`scripts/compile_po.py --check` 与 `.po` 同步（545 条）；`mypy` / `basedpyright` 0 error；`black --check` / `isort --check-only` / `scripts/check_annotations.py` / `scripts/check_version.py` 全绿。

### 更早的更新日志（已归档）

17 条 2024-07-13 ~ 2026-09-06（v4.0.0 ~ v4.0.9.4）的发布说明条目已于 2026-09-28 逐字迁出至 [release-notes-history-zh.md](release-notes-history-zh.md)；该卷同时按 `.workbuddy/docold` 基线回补了上一轮粗剪留下的行尾 `…` / 句中截断（口径见其卷首）。
迁出原因：仅「更新日志」一节就占本文件 33.2% 的字符数（21,181 / 63,742）。根文档只保留最近正式发布 + 本指针，正文才恢复可读。[2026-10-01 更正：收录 v4.4.0 起为四个（v4.4.0/v4.3.0/v4.2.0/v4.1.0），原口径为「最近三个」]
[2026-10-31 更新：v4.5.0 / v4.4.0 / v4.3.0 已迁入本卷；根文档只保留 v4.6.0 概要 + 本指针。]

## 💬 有问题或者需求可以向我提 Issue，欢迎 Star 与 Fork

[![Star History Chart](https://api.star-history.com/svg?repos=y123ao6/DouyinLiveRecorder&type=Timeline)](https://star-history.com/#y123ao6/DouyinLiveRecorder&Timeline)
