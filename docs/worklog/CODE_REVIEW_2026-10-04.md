# 代码审查报告 CODE_REVIEW_2026-10-04

> **审查对象**: DouyinLiveRecorder 工作空间全部源代码（Python / JavaScript / Node.js / HTML / CSS / VBS / Bash / CI 工作流 / 容器与打包配置），排除第三方依赖目录与构建产物。
> **审查日期**: 2026-10-04　**基线**: worktree `DouyinLiveRecorder` detached HEAD `bf43acc`（与 main 同点），`git status --short` 为空。
> **问题总量**: **93 项 —— 严重 7 / 中等 47 / 轻微 39**（其中 15 项由主审查者本机执行取证、3 项由 GitHub 公开 API 取证）。
> **上一次全仓审查**: [CODE_REVIEW_2026-10-02.md](CODE_REVIEW_2026-10-02.md)（严重 2 / 中等 17 / 轻微 47）。
> **落点说明**: 按仓库既有惯例落在 `docs/worklog/`（该目录自 2026-09 起为审查/提案记录的实际存放地）。注意 MR-40 记录了「`.dockerignore` 的审查记录排除集已失效」——本文件落在该目录下同样会进对外镜像，该条已列入 P0。

---

## 1. 审查概述与背景

本次审查由用户发起，要求对工作空间内全部源代码进行全面审查，覆盖 Python、JavaScript、Node.js 等所有语言的源文件，排除第三方依赖目录（`node_modules`）与构建产物（`dist`/`build`），重点排查**代码质量、潜在缺陷、安全漏洞与逻辑错误**，逐文件记录问题（文件路径、行号、问题类型、修复建议），并按严重程度分类产出正式报告。

与 2026-10-02 轮次的衔接：该轮的 P0 五项与其后的整改批次已随提交 `72ef4c2`（2026-10-03）落地。本轮在 `bf43acc` 基线上复核了上轮 66 项中落在本轮覆盖面上的全部条目，结论为：**41 项已修**（含上轮两项严重 SR-01/SR-02 的修法本体）、**12 项修法存在缺口或引入新问题**（本轮编号：SR-01、SR-02 承上轮 SR-01；MR-01、MR-13 承上轮 M-03；MR-07、MR-08 承上轮 SR-02；MR-17 承 L-30；MR-27 承 L-21；MR-37 承 L-44；MR-40、MR-41、MR-42 承 M-16/M-17/M-18 与 L-45~L-47，详见第 3.3 节）、其余为上轮 P1/P2 遗留，按既有惯例不再重复罗列。

本轮的总体判断：

1. **产品侧不存在「防线缺失」型漏洞，但有两处「防线可被绕过」型严重问题**（SR-01/SR-02，集中在 `src/stream_select.py` 的 m3u8 派生地址闸门：安全拒绝的返回值被上层保守兜底重新翻成「可达」，且闸门自身的取样面可被播放列表正文排布规避）。两者都是上轮 SR-01 整改的**未闭合部分**，修复面仍很小。
2. **10-03/10-04 的新增代码引入了两处确定性失效**：小红书短链配置回写会让该房间在录完一轮后永久失联直到重启进程（SR-04，新平台接入的第一条链路）；界面语言在 `set_language` 之前定型，使非中文语言下弹幕实时流恒空（MR-30，其既有自愈分支的前置条件恰好不成立）。
3. **质量门禁自身的完整性出现两类严重退化**（源于本轮新增的覆盖面）：`check_skill_agents_consistency.py` 依赖一个被 `.gitignore` 忽略、从未入库的本地目录，导致 `static` job 与 pre-commit 在干净检出上必红（SR-06，**远端 CI 实测已红**）；`docker-publish.yml` 因 `workflow_dispatch` 发版路径用 `GITHUB_TOKEN` 推 tag 而**从未触发过**（SR-07，**远端实测 `total_count = 0`**），对外承诺的 GHCR 多架构镜像长期不存在且无任何告警。
4. **凭据脱敏仍是「开放集合」问题**：上轮 M-01 的四键缺口已修并经我复测确认，但同一族在四处重新出现——Twitch `sig=`（MR-02）、Cookie 头未登记键名（MR-03）、`msg_push` 五渠道异常原文与 `_mask_url` 的 netloc（MR-04）、standalone 探针异常文本（MR-08）。上轮提出的「矩阵表驱动用例」结构性建议未落地，其代价在本轮可量化为 4 条同源条目。
5. **工具侧信号本轮不干净，但必须区分噪声与缺陷**：`run_gates.py` 10 项中 1 项硬失败（即 SR-06）；全量 `pytest` 读数 **21 failed / 4074 passed / 14 skipped**，经我三组对照实验判定**这 21 条全部为环境×pytest fd 捕获交互的噪声、非代码回归**（复现矩阵见第 7.2 节），同时该现象暴露了一个真实防御缺口（MR-47：`run_gates.run_command` 对不可复制的 stdio 句柄零保护）。`basedpyright` 为 0 error/0 warning，但进程退出码 3 且与判定面无关（MR-46）。

## 2. 审查范围

### 2.1 审查面度量（本机 `wc`/Python 实测，读数时刻 2026-10-04）

| 区域 | 文件数 | 行数 | 深审方式 |
| --- | ---: | ---: | --- |
| 根入口 Python（`main.py` 5,904 / `gui.py` 4,496 / `build_exe.py` 1,740 / `msg_push.py` 577 / `i18n.py` 415 / `web.py` 357） | 6 | 13,489 | 逐文件深审 |
| `src/` Python（49 个文件，最大单体 `src/spider.py` 7,340） | 48 | 27,994 | 逐文件深审（分 6 个工作包） |
| `src/javascript/` 签名脚本（`x-bogus.js` 564 / `haixiu.js` 535 / `liveme.js` 425 / `migu.js` 393） | 4 | 1,917 | 逐行 + 钉定值实测对账 |
| `web/` 前端 + 根 `index.html` + `StopRecording.vbs` | 6 | 4,469 | 逐行 + Node 侧核对 |
| `scripts/`（2,695 行独立发行版孪生副本 + 15 个维护/门禁工具） | 19 | 7,777 | 逐文件深审（**本轮首次覆盖**） |
| `.github/`（5 个工作流 + `actions/retry` + ISSUE_TEMPLATE/PR 模板） | 13 | 2,406 | 逐步骤核查 + 远端运行历史比对（**本轮首次覆盖**） |
| 容器/打包/忽略清单/依赖（`Dockerfile`、`docker-compose.yaml`、`pyproject.toml`、`requirements.txt`、`.dockerignore`、`.gitignore`、`.pre-commit-config.yaml`、`.coveragerc-concurrency`、`config/config.ini`） | 9 | 1,598 | 逐项同源比对（**本轮首次覆盖**） |
| **生产 + 工程面小计** | **105** | **59,650** | — |
| `tests/`（140 个 Python 用例文件 + 4 份 `tests/frontend/*.mjs`） | 144 | 61,673 | 风险模式抽查（假绿/文本锁/作用域时序/平台可达） |
| `i18n/` 四套目录（`.po`/`.mo`/`en_US.json`/`en_GB.json`/`zh_TW.yaml`） | 4 | 6,779 | 键集与占位符实测对账 |
| **合计审查面** | **253** | **128,102** | — |

### 2.2 本轮首次覆盖的清单（上轮 2.1 范围表未含）

`scripts/` 维护与门禁工具链（除孪生副本）、`.github/workflows` 全部工作流与 `actions/retry` 复合动作、`Dockerfile`/`docker-compose.yaml`/`.dockerignore`/`.gitignore`/`.pre-commit-config.yaml`/`pyproject.toml`/`requirements.txt`、`src/platforms/` 平台适配层 8 个文件、`src/javascript/` 签名脚本层逐行、`msg_push.py`（577 行推送渠道）、`tests/frontend/*.mjs` 前端用例本体、`src/ui_kit.py`/`src/ui_theme.py`/`src/ui_i18n.py`（10-03/10-04 UI 现代化阶段 4/5 与界面 i18n 新代码）、`src/ffmpeg_linux_download.py`、`src/startup_cleanup.py`。

### 2.3 排除项

- 第三方与生成物：`node_modules/`（本仓无）、`.venv/`、`node/`、`ffmpeg/`、`dist/`、`build/`、`typings/` 手写存根、`src/proto/douyin_pb2.py`（protoc 生成，仅核其 `.pyi` 契约与消费点）、`src/javascript/crypto-js.min.js`（vendored 压缩库，**不审其内部实现**；但其钉定与执行面在问题清单内，见 MR-36）。
- 运行期产物目录：`downloads/`、`recordings/`、`logs/`、`backup_config/`、`tests/_out_live/`。
- 文档：`*.md` 正文不审，仅核其**与代码/配置的同源一致性**（AGENTS.md、CODE_WIKI 更新日志、README 配置块）。
- `docs/qgraphflow/` 生成物、`uv.lock`（派生产物，只核 `sync_metadata.py --check` 的判定面）。

### 2.4 审查方法与工具

1. **十七个并行只读深审工作包**，按互不重叠的文件集合分派：`main.py`、`src/spider.py`、`gui.py`、Web 面板后端、Web 前端、构建/安装链、选源与调度、HTTP 基建、弹幕与 SRT 链路、`src/platforms/`、签名 JS、standalone 孪生副本、配置/通知基建、UI 层与 i18n、CI 与容器、`scripts/`、tests 抽查。每包 brief 均包含：AGENTS.md 与上轮报告的必读要求、**本项目刻意约定白名单**（PEP 758 无括号多异常、禁 docstring 与中文 `#` 注释、`i18n.tr` 形参模板、探针节流与 `_PROBE_BACKOFF_PLATFORMS`/`_FLV_FIRST_PLATFORMS` 口径、三类钉定与 TOFU 边界、GUI 颜色不进工厂、`sync_http` 无 importer 的已知状态、平台匿名票据已裁断、不提议新增依赖/不加 `# type: ignore` 等 13 条，按包定制），以及「位置/类型/证据/影响/修复建议/严重度/待确认」的强制输出格式。此分工口径出自 AGENTS.md「并行分组代码审查分工口径」。
2. **主审查者逐条复核**（本报告所有行号与读数以此为准）：全部「严重」条目与安全相关「中等」条目由我重新 Read 对应行区间确认；**15 项以本机执行取证**——`mask_credentials` 键覆盖与 Cookie 头分段、`_SECRET_KEYS` 成员判定、`cscript` 对双 BOM VBS 的容忍性、`basedpyright` 退出码对照实验、签名脚本 SHA256 与钉定表逐文件对账、asyncio 停止时序对 `task.cancelled()` 的影响、`subprocess.Popen.__exit__` 源码、`_reject_dangerous_baseline` 探针、i18n 四目录键数与 `全部房间` 实际译文、`_redact_ini_secrets` 对真实 `URL_config.ini` 的两个出口、httpx `Client._redirect_headers` 的 Cookie 剥离、11 个门禁步骤的逐项 PASS/FAIL、全量 pytest 失败归因三组对照、以及「回归锁」注释指针的存在性核对。
3. **远端事实核验**：经 GitHub 公开 API 取 `actions/workflows/docker-publish.yml/runs`（`total_count = 0`）与 `actions/runs` 最近 12 条运行结论（SR-06、SR-07、MR-44 的证据）。本机无 `gh` CLI（`gh: No such file or directory`），故未取 job 级日志——凡依赖 job 内部细节的判断均标「待确认」并给出维护者一键核对方法。
4. **工具交叉**：`scripts/run_gates.py`（10 项）、`basedpyright`、全量 `pytest --cov=src` + `scripts/check_coverage.py`，读数见第 7 章。
5. **定级纪律**：沿用仓库既有严重度定义（第 3.1 节）。工作包给出的 2 条「严重」自评被我**下调**（双 BOM VBS → LR-30；crypto-js 执行期不校验 → MR-36），理由与实测读数就地写明；同时把上轮定级偏保守的同型条目（standalone 凭据外送，上轮 M-03 定中等）按本报告定义**上调**为 SR-05，口径差异在第 3.3 节说明。

## 3. 问题统计总览

### 3.1 严重度定义（沿用 AGENTS.md 与上轮报告）

| 严重度 | 判据 |
| --- | --- |
| 严重 | 可被现实威胁模型利用的安全漏洞（SSRF 击穿自身防线、凭据经可控路径外送），或核心功能/核心交付确定性失效，或**质量门禁自身在合并边界上确定性失效** |
| 中等 | 有真实影响的缺陷：脱敏缺口、并发丢写/竞态、资源泄漏、内存无界、确定性误判、孪生漂移致功能反转、门禁假绿/漏判；通常需特定配置、平台、语言或时序触发 |
| 轻微 | 防御纵深缺口、可观测性不足、契约与注释漂移、死代码、边缘输入崩溃、一致性与工程卫生；当前无实锤泄漏或崩溃路径 |

### 3.2 统计矩阵（按问题落点文件归属，跨文件缺陷只计一次）

| 区域 | 严重 | 中等 | 轻微 | 小计 |
| --- | ---: | ---: | ---: | ---: |
| 主控 `main.py` | 2 | 2 | 7 | 11 |
| 选源/调度（`stream_select`/`stream`/`scheduler`） | 2 | 3 | 0 | 5 |
| 平台解析（`spider`/`room`/`proxy`） | 0 | 3 | 6 | 9 |
| HTTP 与客户端基建（`async_http`/`cookie_cache`） | 0 | 3 | 0 | 3 |
| 弹幕与 SRT（`collector`/`ws_client`/`srt_writer`/`danmaku_monitor`/`platforms/`） | 0 | 5 | 6 | 11 |
| Web 面板后端（`web_api`/`web_config`/`web_tray`/`recorder_status`/`web.py`/`log_archive`） | 0 | 8 | 2 | 10 |
| 前端与 Node（`web/app.js`/`motion.js`/根 `index.html`） | 0 | 2 | 4 | 6 |
| GUI 与 UI/i18n 层（`gui`/`ui_kit`/`ui_theme`/`ui_i18n`/`i18n.py`/目录） | 0 | 3 | 4 | 7 |
| 构建/安装/签名脚本/VBS（`build_exe`/`ffmpeg_*`/`node_install`/`src/javascript`） | 0 | 4 | 3 | 7 |
| 配置/通知/推送（`utils`/`config_io`/`notify`/`msg_push`） | 0 | 4 | 0 | 4 |
| 独立发行版 standalone 孪生 | 1 | 5 | 0 | 6 |
| CI 工作流/容器/忽略清单/依赖声明 | 1 | 2 | 1 | 4 |
| `scripts/` 维护与门禁工具 | 1 | 3 | 2 | 6 |
| `tests/` | 0 | 0 | 4 | 4 |
| **合计** | **7** | **47** | **39** | **93** |

### 3.3 与 2026-10-02 轮次的衔接

- **已修且经我复测**（41 项）：M-01（四键入表，实测已抹）、M-02、M-03 本体、M-05、M-06、M-07、M-09、M-11、M-12、M-13 主路径、M-14、M-15、L-01~L-06、L-07~L-12、L-14~L-16、L-18~L-20、L-22~L-36、L-38~L-40、L-42、L-43、L-46、L-47；SR-02 本体（`_HopGuardRedirectHandler` 已挂进 opener）；工作区杂散文件 `markdown-DX-TNHnc.js` 已删除。
- **修法存在缺口或引入新问题**（本轮新开条目）：上轮 SR-01 → **SR-01 + SR-02**（上层末位放行/同址复用重新交付 + 取样面可规避）；M-03 → **MR-01**（落地页被拒后未剥凭据）与 **MR-13**（`_match_host` 无尾斜杠片段仍中缀匹配）；上轮 SR-02 → **MR-07**（逐跳不剥跨域 Cookie）与 **MR-08**（异常文本未去 query）；M-16 → **MR-40**（写 `q` 实为 no-op）；M-17 → **MR-41**（缺节流/重试/按播放列表记退避）；M-18/L-45/L-46/L-47 → **MR-42**（五条回灌零回归锁，致假修复全绿逃逸）；L-21 → **MR-27**（新判据恒取异常分支，我用 asyncio 实验坐实）；L-44 → **MR-37**（node 侧仍 fail-open，且 `tests/test_node_install.py:224` 注释已失真）；L-30 → **MR-17**（只挡声明了 Content-Length 的请求，chunked 绕过）。**M-04 的残余未单独计数**：成功写点已持锁（`src/spider.py:314-317`、`:368-371`、`:2388-2391`），但 `_ensure_kuaishou_did` 的 TTL 清空与末尾 return（`:322-330`）仍在锁外——该残余面窄（需多代理冷启动交错）且本轮我未逐行复测，修复时按上轮建议整段收进 `_kuaishou_did_lock` 即可。
- **上轮三条结构性建议的落地情况**：建议①「脱敏键集矩阵化用例」**未落地** → 同源缺口以 MR-02/MR-03/MR-04/MR-08 四条复现；建议②「standalone 回灌清单机检」**未落地** → MR-42 记录了直接后果；建议③「『内存有界』承诺与实现对齐」部分落地（M-09 已修），但修法带来次生偏差（LR-18 字节量级低报）。
- **定级口径差异的说明**：上轮把「恶意分享链接使平台 Cookie 递送到攻击者 host」（M-03）与「standalone 未复检重定向逐跳」（SR-02）分别定中等/严重。本轮 SR-05 与上轮 M-03 是同一缺陷类在未回灌副本上的实例，按本报告 3.1 定义（凭据经可控路径外送）取**严重**；MR-01 是 M-03 在主线修法的残余，为与上轮保持可比性取**中等**并列入 P0 首位。

## 4. 严重问题（7 项）

### SR-01 m3u8 派生地址被安全闸拒绝后，仍经「末位放行」与「同址复用」两条路径交给 `ffmpeg -i`（上轮 SR-01 未闭合部分）

- **位置**: `src/stream_select.py:852-859`、`881-888`（`_validate_stream_url` 的 HLS 末位放行）、`1346-1358`（`select_source_url` 的 `record_url` 同址复用）；被绕过的判定在 `:542`（变体跳）与 `:572`（分片跳）
- **类型**: 安全 / SSRF 击穿自身防线（已行级复核）
- **描述**: 上轮把两处 `return True` 改成了 `return False`，但 `_probe_hls_segment` 的返回类型是 `bool`，调用方无法区分「安全闸确定性拒绝」与「可达性存疑、应交 ffmpeg 定夺」。于是末位候选分支把这条 False 又翻回 `return True`；`select_source_url` 的复用分支更与末位资格无关——只要 `record_url` 与本轮已探的 m3u8 同址（抖音/TikTok/网易 CC 的 `record_url = m3u8_url or flv_url` 恒成立），即便上一轮探针因内网分片判失败，仍照常 `_accept_source(record_url_str, "record_url")` 交付。`_accept_source` 只复核播放列表 URL 本身（公网），拦不住正文里的内网目标。
- **证据**: `:572` 注释「SR-01：与变体派生跳同判据——安全闸拒绝判候选失败，不得维持可达」后跟 `return False`；`:852-859` `if last_resort: logger.warning(... "HLS 媒体分片不可达；已无备选源，仍交由 ffmpeg 尝试" ...) → return True`；`:1351-1358` `if not probed[record_url_str]: logger.warning(... "与本轮已探候选同址，复用结论并交由 ffmpeg 拉流")` → `accepted = _accept_source(record_url_str, "record_url")`。同函数 `:574-578` 的 `except RedirectHopRejected: raise` 分支注释（WP-J）已自我写明「在内网落地目标面前，维持可达就等于把内网地址交给 ffmpeg」——被绕过的正是该条自述。既有锁 `tests/test_regression_stream.py:417-444` 三条只断到 `_probe_hls_segment` 的返回值，**未断到交付结果**，因此「用例全绿」与「缺陷存在」并存。
- **影响**: 被劫持/MITM 的播放列表（虎牙/斗鱼地址在本仓被刻意降级为 http，MITM 现实可行）正文写 `http://127.0.0.1:6379/x.ts` 或云元数据地址时，该列表仍会被选中并交给 `ffmpeg -i`；ffmpeg 按正文连内网，并对同一输入复用平台 Cookie。日志同时给出与行为相反的「已丢弃（不交给 ffmpeg -i）」，使排障归因反向。
- **修复建议**: `_probe_hls_segment` 的安全拒绝改为抛专用内部控制流异常（照 `RedirectHopRejected` 先例，如 `_DerivedHopRejected`），在 `_validate_stream_url` 中排在 `except Exception` 之前且**不受 `last_resort` 影响**；`select_source_url` 增设 `security_rejected: set[str]`，在 `:1351` 复用分支与 `:1362` 之前判定不交付。回归锁两条行为断言：①「正文含内网分片的播放列表 + `last_resort=True` → `_validate_stream_url(...) is False`」；②「`m3u8_url == record_url` 且正文含内网分片 → `select_source_url(...) is None`」；并保留 `test_hls_segment_404_last_resort_released`（分片 404 属可达性、仍应放行）。

### SR-02 派生地址闸门的取样面仅为「末行 + 媒体后缀」，播放列表正文排布即可整体规避；注释判定用未 strip 的行

- **位置**: `src/stream_select.py:552-560`（分片取样与 `is_media`）、`525-530`（变体只取最高带宽一条）
- **类型**: 安全 / SSRF + 零日志静默退化（已行级复核）
- **描述**: 分片层只取 `media_lines[-1]`，且该行不以 `.ts/.mp4/.m4s` 结尾时直接 `return True`（维持列表可达）；变体层只探最高带宽的一档。播放列表正文是外部可控输入，行数、行序、后缀都由对方决定，因此**无需借助末位候选**就能让闸门整体失明。另 `:552` 的列表推导用**未 strip** 的 `ln.startswith("#")` 判注释，缩进注释行（如 `"  #EXT-X-ENDLIST"`）会被当成分片行，同样落到 `:560` 的保守放行。
- **证据**: `:552` `media_lines = [ln.strip() for ln in text.splitlines() if ln.strip() and not ln.startswith("#")]`；`:555` `seg_line = media_lines[-1]`；`:556-557` `is_media = seg_line.endswith((".ts", ".mp4", ".m4s")) or any(ext + "?" in seg_line for ext in (".ts", ".mp4", ".m4s"))`；`:559-560` `if not is_media: return True  # 非标准分片行……保守放行`。
- **影响**: 攻击列表把内网/元数据地址（如 `http://169.254.169.254/latest/meta-data/`）放在首行或写成无媒体后缀形态、末行放正常公网分片，即可让候选判可达并交付；与 SR-01 叠加后，闸门在「构造型列表」面前实际不成立。该路径全程零日志（`:560` 分支不打任何告警），排障时看不到「分片层被跳过」。
- **修复建议**: `:552` 的注释判据改为对 strip 后的行判定；在 `:552` 之后对**全部**派生地址（分片行与 `:488` 变体集合）逐个跑 `_is_derived_hop_allowed`——纯字符串判定、零 I/O，任一行不合规即判候选失败；可达性探测仍按现状只取样一条（末行/最高带宽档）。回归锁两条：「首行为内网 `.ts`、末行为公网分片 → 判 False 且客户端调用记录不含内网 host」「无后缀的内网行 → 判 False」。

### SR-03 强制直下路径完全绕过选源闸门，并由此产生 AGENTS 点名的「第三处自建客户端」

- **位置**: `main.py:4642-4716`（消费点）、`main.py:736-833`（`direct_download_stream` 的出站客户端）
- **类型**: 安全 / SSRF + 契约违背（已行级复核）
- **描述**: 录制链唯一的「交付前内网/形态闸门」只装在 ffmpeg 路径（`stream_select._accept_source`）。直下分支下载的是 `port_info.get("flv_url")` 而**非**经选源复核的 `real_url`；默认 HLS 优先排序下 shopee 的 m3u8 候选先探先选中，`flv_url` 连探针都不发。我在 `:4643`→`:4715` 区间 grep `recordable|internal|hop|_accept_source|select_source|is_safe` **零命中**，`direct_download_stream` 头部（`:736-766`）只有 headers/UA/`httpx.Client(...)`。该客户端 `follow_redirects=True` 且无 `event_hooks`——按 AGENTS「重定向逐跳复检只有两个合法接线点，新增第三处自建客户端即视为漏防」，这既是初始 URL 未判定、也是逐跳未判定。
- **证据**: `:4642` `flv_url = port_info.get("flv_url")`；`:4715-4716` `download_success = direct_download_stream(flv_url, save_file_path, ...)`；`:762-765` `with httpx.Client(timeout=30, verify=_http_config.get_effective_ssl_verify(platform), headers=headers) as client: with client.stream("GET", source_url, headers=headers, follow_redirects=True) as response:`。
- **影响**: 平台接口被劫持/MITM 下发 `flv_url = http://127.0.0.1:6379/x.flv` 时，探针层判失败并选用别的候选，房间线程仍会把该内网地址交给 httpx GET（带平台 Referer/UA/Cookie）并把响应体写进录制产物——即「内网端口观测 + 内网响应外带到文件」。我已读 httpx 0.28.1 `Client._redirect_headers` 源码，其末行无条件 `headers.pop("Cookie", None)`，故跨站重定向不构成凭据外送，风险落在 SSRF 读与产物污染。ffmpeg 路径同输入受保护，两条路径口径不一致本身即缺陷。触发面限于强制直下的两个平台（shopee / 花椒直播）。
- **修复建议**: `:4643` 的守卫追加一次落地复核并**复用选源侧同一份判据**：`_is_recordable_url(flv_url)` 且 `internal_stream_target_reason(flv_url, proxy_address) is None`，不通过则走 `:4758` 的「未找到 FLV 直播流」分支并补一条告警；更彻底的形态是只允许下载 `real_url`。同批给该客户端挂 `async_http.build_sync_hop_guard`（或在注释中把它登记为第三处接线点并写明残余）。回归锁：`tests/test_main_direct_download.py` 断言注入内网 `flv_url` 时 `direct_download_stream` 调用计数为 0。

### SR-04 小红书短链回写沿用 Shopee 的 `not_record_list` 通道，前缀清理永不匹配 → 该房间录完一轮后永久失联

- **位置**: `main.py:4254-4262`（登记）、`5823-5827`（清理）、`5769-5771`（跳过判定）
- **类型**: 逻辑错误 / 核心功能确定性失效（10-04 新增链路，已逐处行级复核）
- **描述**: `_resolve_xhslink_com` 把解析出的**长链**经 `new_record_url` 通道回写配置，同时 `not_record_list.append(new_record_url)`；而房间线程出口的清理判据是 `_args[0][1]`（**短链**）的 `split("?", 1)[0] + "?"` 前缀。短链与长链无公共前缀，条目因此永不摘除，主循环 `if url_tuple[1] in not_record_list: continue` 从此恒跳过改写后的长链。
- **证据**: `:4259` `not_record_list.append(new_record_url)`；`:5823-5827` `_not_record_prefix = _args[0][1].split("?", 1)[0] + "?"` → `not_record_list[:] = [u for u in not_record_list if not u.startswith(_not_record_prefix)]`；`:5769` `if url_tuple[1] in not_record_list: continue`。`:5811-5821` 的 H-5 注释写明该前缀判据成立的前提是「Shopee 的 `new_record_url = record_url.split("?")[0] + "?<uid>"`，与 `record_url` 同 base」——小红书不满足该前提，`_build_shopee_record_url`（`:3134-3156`）才提供同源保证。
- **影响**: 用户在 `URL_config.ini` 填最常见的 `https://xhslink.com/o/<短码>` 形态时：首轮解析成功、配置被改写为 `www.xiaohongshu.com/livestream/...` 长链；短链线程退出并「清理」，长链永久留在跳过表 → **该房间在当前这轮录完后不再被拉起，直到重启进程**，且全程零日志。属现实使用路径的确定性功能失效，而非概率性缺陷。
- **修复建议**: 最小改动是在 `:4259` 只对「与 `record_url` 同 base」的规范化地址登记跳过（`if new_record_url.split("?", 1)[0] == record_url.split("?", 1)[0]:`），小红书短链改走「回写但不进跳过表」；或把登记改为 `(record_url, new_record_url)` 成对、清理按 `record_url` 等值精确移除（顺带消除前缀近似误伤这一既有隐患）。回归锁（`tests/test_xhs_live_links.py`）：以短链跑一轮 `start_record`，断言 `need_update_line_list` 有回写项**且** `not_record_list` 不含与 `record_url` 不同源的条目；再在 `main` 命名空间驱动线程 finally 形态，断言退出后 `not_record_list` 为空。

### SR-05 独立发行版仍是「整串子串」平台路由且无 host 准入，主线 M-03 修复未回灌 → 凭据外送与带凭据内网 GET

- **位置**: `scripts/douyin_live_recorder_standalone.py:1265-1293`（路由）、`985-1001`（`resolve_huya` 带 Cookie 原样请求用户 URL）、`2140-2151`（`load_urls` 无准入）
- **类型**: 孪生漂移 / 凭据外送（已行级复核）
- **描述**: `PLATFORM_RULES` 的模式为 `huya\.com`/`douyu\.com`/`live\.bilibili\.com` 等，匹配方式是 `re.search(pattern, url, re.I)`——对**整串 URL** 做子串匹配；`load_urls()` 只做 `line.split(",")[0]`，没有主线 `PLATFORM_HOST` 的准入判定，resolver 入口也没有主机自校验。主线在 2026-10-02 的 M-03 整改中已把匹配对象收窄为 `scheme://host/` 归一串并加了准入。
- **证据**: `:1267` `(r"huya\.com", "虎牙直播", resolve_huya)`；`:1279` `if re.search(pattern, url, re.I):`；`:994` `headers["Cookie"] = cookies` → `:1001` `html = _fetch_html(url, headers=headers, timeout=15, proxy=proxy)`。主线对照 `main.py:1730-1739`（`_match_host` 归一 hostname）、`main.py:5678`（`PLATFORM_HOST` 准入）、`main.py:1989`（huya 入口 host 自校验）。AGENTS「主线安全/正确性修复必须核对 standalone 孪生副本」明列此类必须回灌。
- **影响**: 在独立发行版（随仓库与镜像分发）的 `URL_config.ini` 里写 `https://evil.com/www.huya.com/660002`，即把用户配置的虎牙 Cookie 原样发往 `evil.com`（逐次发生，与开播与否无关）；写 `http://127.0.0.1:6379/?huya.com` 则向内网发起带 Cookie 的 GET 并读取响应。与上轮 M-03 同型；定级理由见第 3.3 节口径说明。
- **修复建议**: `platform_of`/`dispatch` 一律按 `urlsplit(url).hostname` 归一后做「精确等于或 `.` 后缀」判定（抄主线 `_match_host` 的归一串写法，两侧注释互相点名）；`load_urls` 增加与主线 `PLATFORM_HOST` 同集合的准入名单，未命中行跳过并告警；`resolve_huya` 入口补主线 `:1989` 那条自校验。孪生锁（`tests/test_regression_standalone.py`）：打桩 `_fetch_html`，断言 `https://evil.com/www.huya.com/1` 返回「不支持的平台」且 `_fetch_html` 零调用；再加 AST 结构锁断言副本源码中不存在 `re.search(pattern, url` 形态。

### SR-06 Skill 一致性门禁依赖被 gitignore 的本地目录，`static` job 与 pre-commit 在干净检出上确定性失败（本机复现 + 远端实测已红）

- **位置**: `scripts/check_skill_agents_consistency.py:170-172`；接线于 `.github/workflows/ci.yml:317-318`（`static` job 普通步骤，无 `continue-on-error`）与 `.pre-commit-config.yaml:99-104`（`always_run: true`）；资产侧 `.gitignore:292`、`.dockerignore:25`
- **类型**: 门禁自证 / 合并边界确定性失效
- **描述**: 脚本把「`.agents/skills` 不存在」判为 rc=2「门禁本身失效」，但 `.agents/` 是本地工具目录、被 ignore 且**从未被 git 跟踪**，任何干净检出必然缺失该目录；`static` 又是 required check `ci-summary`（`ci.yml:900-913`）的 `needs` 之一。
- **证据（三段独立取证）**: ① 本机 `python scripts/run_gates.py` → 第 10 项 `[FAIL] rc=2`，前 9 项全 PASS（含 `mypy` 与 `mypy --platform linux`/`win32` 三平台双跑）；② `git ls-files .agents` 空、`git ls-tree --name-only HEAD` 顶层无 `.agents`、`git log --all -- .agents` 无历史，而维护者主检出 `D:/DouyinLiveRecorder/.agents/skills` 实有 5 个目录 → 维护者本机绿、干净检出必红；③ **远端实测**：我经公开 API 取 `actions/runs`，`CI`（push, main, 2026-10-03T02:05:33Z，即引入该门禁的 `72ef4c2` 之后）结论为 **failure**。此外 `run_gates.py:490-507` 在第 10 项红后 `return 1`，而 `gate_pytest_warnings_summary()` 排在 `:513` 之后 → **任一条门禁红就使 pytest 0-警告兜底根本不执行**。
- **影响**: 每次命中 python 路径过滤的 CI 全链红、本地提交被 pre-commit 阻断；AGENTS.md:248 又把它列为「格式化命令（门禁唯一基准）」第 10 条，于是「完成定义第 1 条」在干净检出上永不可满足。长期红的 required check 会诱导加 `|| true`（真假绿）或习惯性忽略红（真回归被放行），两者都摧毁其余 9 项门禁的信号价值；本项同时是 AGENTS「门禁本身失效」档的实例。
- **修复建议**: 按仓库既有先例把「资产不在仓库面」降为显式 SKIP——打印 `SKIP: .agents/ 属 .gitignore/.dockerignore 忽略的本地工具目录，本检出不含该资产`（CI 侧补 `::notice::`）并退 0，判据本体保留在装有 Skill 的本机（先例：`tests/test_agent_hook_guard.py:297`「资产缺失时 skip 而非伪绿」、`tests/test_ci_frontend_registration.py` 的 node 缺失 skip）。若维护者判定 CI 必须真的执行该锁，则须把 `.agents/skills/` 纳入跟踪（先例 `.gitignore:38` 的 `!DouyinLiveRecorder.egg-info/`）——属 ignore 同源约定变更，按 AGENTS「风险控制（前置）」交回用户决定。**两条路都要补回归锁**：在 `tmp_path` 造「有 AGENTS.md、无 `.agents`」的面，断言新行为（SKIP → 0），并反向断言「表格条目指向不存在路径」仍 rc=1（不被新 SKIP 一并吞掉）。

### SR-07 多架构镜像发布链从未触发：`workflow_dispatch` 路径的 tag 由 `GITHUB_TOKEN` 推送，不产生 workflow 事件

- **位置**: `.github/workflows/build-release.yml:208-226`（`env: GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}` + `git push origin "$TAG"`）↔ `.github/workflows/docker-publish.yml:35-38`（只由 `push: tags: v*` 触发）
- **类型**: 核心交付确定性缺失（远端实测）
- **描述**: 本仓 Release 全部由 `workflow_dispatch` + `create_release` 产生，其 tag 在 job 内用 `GITHUB_TOKEN` 推送；GitHub 明确规定由 `GITHUB_TOKEN` 创建的 push 不会生成新的 workflow 运行，于是镜像链的入口事件永不发生。AGENTS 明令不得为「方便重跑」给 `docker-publish` 加回 `workflow_dispatch`/`schedule`（该定稿我未质疑），问题在于**触发前提自始不成立**。
- **证据**: 我经公开 API 取 `actions/workflows/docker-publish.yml/runs` → **`total_count = 0`**（该工作流自创建起一次都没有运行过）；`actions/runs` 最近 12 条里 `Build & Release` 全部为 `workflow_dispatch` 事件；`docker-publish.yml:70-75` 的 `prepare` 对非 tag 引用显式 `exit 1`，故也无法靠 dispatch 补建。
- **影响**: README/部署文档对外的 `ghcr.io/…:latest` 与 `:vX.Y.Z` 实际不存在，`docker-compose` 使用者只能本地构建；整个后果**无任何红或 warning**——`Build & Release` 每次绿、Trivy 也在跑，唯独镜像链静默缺席；同时 Trivy 的扫描对象因此是「本地临时构建」而非对外发布物，削弱了「advisory-only 镜像层审查」这条既定防线的实际覆盖面。
- **修复建议**: 保持 `docker-publish` 的触发面不动，改为把「本版本无镜像」变成可见事实：① 在 `build-release.yml:571-579` 的 `Write job summary` 与 Release 正文里，当 `github.event_name == 'workflow_dispatch'` 时显式打 `::warning::`（说明 dispatch 发版不级联触发 Docker Publish、本版本无 GHCR 镜像）；② AGENTS「多架构镜像只走原生双 runner」条目补一句触发前提「镜像链只认**人工推送**的 tag」；③ 需要镜像时的操作路径写进 README 发布流程（维护者本地 `git push origin vX.Y.Z`，由首次推送方产生事件）。验证：Actions 的 `Docker Publish` 页应为 0 次运行，任一 Release 页无容器附件。

## 5. 中等问题（47 项）

### 5.1 凭据外送与脱敏（8 项）

**MR-01 小红书落地页被判不可信后未剥离凭据，仍以带 sid 的头二次请求短链（AGENTS「双闸」缺最后一半）**
- **位置**: `src/spider.py:2674-2688`（两个拒绝分支）、`2703-2704`（复用同一份 headers 再请求）；同文件正解在 Shopee 侧 `:6464-6470`
- **描述**: 落地页未过白名单或命中内网判定时，两分支只 `logger.warning` 后落空，既不 `return` 也不剥头；`url` 保持原短链，`:2704` 又用同一份含 `xy-common-params`（内嵌 `sid=`，构造点 `:2629`）与可选 `Cookie`（`:2633`）的 headers 请求，httpx 逐跳跟随后再次抵达被拒主机。`:2703` 注释「走到这里 url 已保证落在 XHS 白名单域内」在该形态下为假。
- **影响**: 一条恶意/失效 xhslink 分享链接即可把 `xhs_session_sid`（用户自配时即其私有会话标识）递送到攻击者指定 host。我读了 httpx 0.28.1 `Client._redirect_headers`——末行**无条件** `headers.pop("Cookie", None)`，故用户 Cookie 目前靠依赖实现细节挡住（跨版本可变，不是本仓显式防线），而自定义头 `xy-common-params` 确定外送；被拒页面正文还会继续被当 `__INITIAL_STATE__` 解析，可左右 `anchor_name`/`room_id`。
- **修复建议**: 两分支置 `landing_untrusted = True`，请求前统一 `headers.pop("Cookie", None)` + `headers.pop("xy-common-params", None)`（或按 `:2672` 形态直接返回 error）；改正 `:2703` 注释。回归锁（`tests/test_xhs_live_links.py`）：打桩 `spider.async_req` 捕获两次调用的 headers，断言落地页被拒后第二次调用不含 `Cookie`/`xy-common-params`。

**MR-02 Twitch usher 播放签名参数名 `sig=` 不在脱敏黑名单，完整可拉流直链进轮转日志**
- **位置**: 产生点 `src/spider.py:5059-5066`；判定表 `src/utils.py:869-931`（`_SECRET_KEYS`）
- **描述**（**我实测**）: usher 地址把 PlaybackAccessToken 的签名以 `sig=` 拼进 m3u8 直链，而 `_SECRET_KEYS` 有 `sign`/`signature`、无 `sig`。实测 `mask_credentials("...?sig=ABC123SECRET&t=1234&token=XYZ")` → `sig=ABC123SECRET` 原样返回、同串 `token=***`；`'sig' in _SECRET_KEYS` 为 False。
- **影响**: `stream_select.py` 的候选校验日志（`:451/:536/:675/:695/:711/:720`）一律过 `mask_credentials` 后写 `logs/streamget.log`（300 KB 轮转、保留多份）→ Twitch 每轮选源都把可用拉流签名写进日志。与已修的 SEV-2210（`wsAuth`）、关键约定 #11 完全同型。
- **修复建议**: `_SECRET_KEYS` 增 `"sig"`（整段小写键，与 `sign` 无左边界冲突），并在 `tests/test_utils.py::TestMaskCredentialsCoverage` 加「值确实消失」断言 + 一条 `sig`/`signature` 共存样例防互相切碎。

**MR-03 Cookie 头形态的逐段兜底只对黑名单内键名成立，未登记 Cookie 名整值明文（M-01 修法缺口）**
- **位置**: `src/utils.py:989-999`（`_SECRET_HEADER_RE` 值字符集 `[^,;\r\n"']+`）与 `:869-931`
- **描述**（**我实测**）: 头形态的值在首个 `;` 截断，Cookie 头只有第一段整段抹除；其后各段依赖 query 形态的**封闭黑名单**逐段兜底。实测 `Cookie: SESSDATA=abc123SESS; bili_jct=xyz789JCT; DedeUserID=12345` → `Cookie: ***; bili_jct=*** DedeUserID=12345`；`buvid3`/`ntic` 同样整值保留。
- **影响**: `[Cookie] B站cookie` 的真实形态就是 `SESSDATA=…; DedeUserID=…; buvid3=…; buvid4=…; ntic=…`，任何把该串写进日志的路径（异常文本、诊断打印、代理串）都会保留除 SESSDATA 外的全部身份标识。上轮建议①「平台 Cookie 全键清单 × 形态」矩阵用例未落地，`tests/test_utils.py:550-561` 的 Cookie 多段用例恰好只喂四个**已登记**键名，把该残余写成了「已闭合」。
- **修复建议**: 首选把 `Cookie`/`Set-Cookie` 两个头的值字符集去掉 `;`（整串一次抹完，告警文案写明「Cookie 头整段遮蔽」）；或按矩阵补 `dedeuserid`/`buvid3`/`buvid4`/`ntic`/`bili_ct` 入表，并把用例改为「四个值逐一断言消失」。

**MR-04 `msg_push` 五个渠道的失败分支把异常原文 `{e}` 直落日志，且 `_mask_url` 原样保留 netloc 的 userinfo**
- **位置**: `msg_push.py:110-122`、`153-162`、`321-331`、`382-391`、`477-486`；`_mask_url` 返回行 `:70`；`_mask_secret` `:31-37`
- **描述**: 每个分支都准备了 `masked_api=_mask_url(api)`，却又把 `e=e` 原文塞进同一条 msgid；而 `urllib`/`http.client` 在**发起网络之前**抛的两类畸形配置异常，其消息文本自带完整 URL 或整条 path。`_mask_url` 只处理 path、丢弃 query，`urlunsplit((scheme, netloc, masked_path, "", ""))` 的 netloc 未处理，而 netloc 合法含 `user:pass@host`。
- **影响**: 工作包在本机 CPython 3.14.8 实跑得到 `ValueError: unknown url type: 'oapi.dingtalk.com/robot/send?access_token=…'` 与 `InvalidURL: URL can't contain control characters. '/bot123456:AAH…  /sendMessage'`（我复核判据成立）；`_mask_url("https://user:Tok3nP4ss@bark.example.com/abcdefgh", mask_last_segment=True)` 保留口令。触发条件是用户从地址栏截断复制、或 token 里带入空格——高频人工失误形态且每轮复现，后果是钉钉 `access_token`、Server酱 sendkey、Bark device key、TG bot token 明文进 `streamget.log`（轮转多份）与 `web_console.log`（不轮转）。附带：`bark`/`xizhi`/`pushplus` 的 `success`/`error` 列表放的是未脱敏原址（`:372/:383/:510/:521`），当前只因唯一消费方 `src/notify.py:79-80` 只取 `len()` 而未外泄，属一步之遥的脆弱契约。`_mask_secret` 对 7-8 位凭据保留 4/7 与 4/8 位，全遮阈值 6 偏低。
- **修复建议**: 五处 `e=` 实参改 `utils.mask_credentials(str(e))`（与 `notify.py:160`、`utils.py:334` 同口径）；`_mask_url` 的 netloc 先过 `mask_credentials`（与 `utils.py:1006` 的 `_PROXY_CREDENTIAL_RE` 互点名，不要写第四份实现）；返回值改放脱敏形态或只放计数；`_mask_secret` 阈值抬到 12。回归锁进 `tests/test_msg_push.py`（`TestBarkFailureLogMasking` 已是正确的「断言真实日志行」形态）：以 `side_effect=ValueError("…access_token=SECRETTOKEN")` 断言捕获行不含 `SECRETTOKEN`。

**MR-05 掩码 `'***'` 的跳过判据前后端都是精确等值，部分编辑会把真实凭据覆盖成 `***abc`**
- **位置**: `web/app.js:1676`（`if (newVal === SENSITIVE_MASK) continue;`）与 `:1678`（清空确认只判 `!newVal.trim()`）；后端孪生半边 `src/web_api.py:1229`（`elif value.strip() == SENSITIVE_MASK:`）
- **描述**（**我读码确认两侧形态**）: 用户在已脱敏的输入框里直接续写（不先全选删除）时值形如 `***abc`：既不过掩码跳过、也不弹「清空确认」，`newVal !== oldVal` 故提交；后端同样只拒精确 `'***'`，两侧一起放行。
- **影响**: 真实 Cookie/token 被掩码前缀覆盖，而下次 `loadConfig` 后端又重新脱敏成 `***` → 界面看不出任何异常，用户只能在录制失败时发现；`backup_config/` 副本本身已脱敏，无回滚路径（AGENTS 凭据红线所防的正是该形态，MID-37 的残余面）。
- **修复建议**: 前端在 `:1677` 之后加「掩码行的新值仍以掩码开头即判误编辑」并拒提交；渲染侧给 `data-masked="1"` 的 input 绑 `focus` 首次聚焦清空，使「输入即替换」成为默认交互；后端补孪生判据 `value.startswith(SENSITIVE_MASK)`。回归锁：`tests/frontend/test_quality_ui.mjs`（MID-37 段旁）置值为 `***abc` 后点保存，断言该键无 PUT 且出现拒存状态行。

**MR-06 删除房间把 URL 放进 DELETE 查询串，面板访问日志把含鉴权参数的房间地址明文落盘**
- **位置**: `web/app.js:1418`（`api('/api/rooms?url=' + encodeURIComponent(url), { method:'DELETE' })`）；同文件其余写操作一律走 body（对照 `:1430`）；`web.py:307` 未关 uvicorn access log；`web.py:114-117` 后台模式把 stdout/stderr 重定向进 `logs/web_console.log`
- **描述**: 房间 URL 可自带鉴权参数（AGENTS 小红书条明写 `xsec_token` 是页面鉴权参数、且短链规范地址会回写配置），请求行含 query，access log 按请求行原样记录，绕过 `utils.mask_credentials`。`web/app.js:191` 的 `console.warn` 还把同一 path 原文再送进浏览器控制台一次。
- **影响**: 在面板里删除/重试任一携带 token 的房间链接，凭据即进 `web_console.log`（运行期不轮转）并随停止录制归档，同机任意可读 `logs/` 的进程即可取走——与 AGENTS「写入配置或日志前必须脱敏」红线冲突。**待确认**：落盘形态未实测（只读纪律、未起面板）。验证法：起面板后对含 `xsec_token` 的 URL 发 DELETE，再 `grep -c "xsec_token" logs/web_console.log`。
- **修复建议**: `:1418` 改 body 形态（与后端 `DELETE /api/rooms` 路由同批改，`_route` 适配器已在用 `_read_json_body`）；`apiError` 的 warn 实参先 `path.split('?')[0]`。回归锁 `.mjs`：断言 `deleteRoom` 的请求 path 不含 `url=`、body 含 url，并保留一条「其它端点允许带 query」的反向边界，防止把保护扩成全面禁 query。

**MR-07 独立发行版的重定向逐跳复检不剥跨域 Cookie，与同文件的分片层口径自相矛盾**
- **位置**: `scripts/douyin_live_recorder_standalone.py:210-234`（`_HopGuardRedirectHandler.redirect_request`）、`256-308`、`1517-1559`
- **描述**: 该 handler 只判「协议 + 内网」，放行即调 `super().redirect_request()`；stdlib 该函数只剥 `content-length`/`content-type`（我已按 `CONTENT_HEADERS = ("content-length","content-type")` 复核），`Cookie` 原样带到下一跳。副本在**播放列表正文派生跳**上是有同域裁决并剥 Cookie 的（`_headers_for_derived_hop_lite`，`:1420-1423`），HTTP 重定向这条同为「响应决定地址」的路径却完全不做。
- **影响**: 被劫持/投毒的 CDN 对探针回 `Location: https://attacker.tld/x.flv`（公网、非内网，守卫放行）时，抖音/B站/虎牙 Cookie 随跳转请求外泄；副本自己登记的威胁模型（虎牙/斗鱼候选刻意降级 http、MITM 现实可行）覆盖这条。主线 httpx 侧同样不剥，故本条不是纯孪生漂移而是**副本内两层不一致**。
- **修复建议**: `redirect_request` 内比较 `urlsplit(newurl).hostname` 与 `req.origin_req_host`，跨域（按 `_is_same_probe_scope_lite` 的近注册域口径）时先 `req.remove_header("Cookie")` 再交给 super；判据与 `_headers_for_derived_hop_lite` 共用同一函数、注释互点名。孪生锁（`TestRedirectHopGuard`）：`Request(url, headers={"Cookie": "SESSDATA=x"})` 302 到**另一个公网域**后，返回的新请求头不含 `Cookie`，而同域跳转仍保留。

**MR-08 独立发行版探针异常文本把带 token 的完整 URL 与重定向落地地址原样落日志**
- **位置**: `scripts/douyin_live_recorder_standalone.py:287`、`:308`、`:224`；消费点 `:1652-1655`、`:1545`
- **描述**: `http_request`/`http_probe` 的网络层失败异常串里挂的是**未去 query 的** `url={url}`，而 `validate_stream_url`/`_confirm_get_ok` 捕获后又把 `{e}` 整条写进日志；同一函数的正常分支一律用 `strip_query(url)`，只有异常分支漏。主线同位置一律 `utils.mask_credentials(...)`（对照 `src/async_http.py:561`）。
- **影响**: 虎牙 `wsSecret/wsTime`、斗鱼 `wsAuth/t`、B站 `deadline/sign` 等拉流凭据以及被拒重定向的落地全文落 `logs/standalone.log`（其轮转已在本轮复核中确认落地为单代 `.1`，仍是多份保留）；触发条件是探针网络层异常（超时/DNS/连接拒绝），弱网下每次失败轮都打一条。
- **修复建议**: 两处 `raise` 的 `url=` 与 handler 消息里的 `newurl` 一律改 `strip_query(...)`；孪生锁在 `TestFfmpegCommandLogMasking` 同族加一条——打桩 `SA._build_opener` 令 `open()` 抛 `URLError`，走 `validate_stream_url("http://cdn.example/a.flv?wsAuth=SECRETTOKEN")`，断言捕获日志行不含 `SECRETTOKEN`。

### 5.2 选源 / 分派 / 平台解析正确性（6 项）

**MR-09 派生跳内网判定是全仓第二份名单，口径窄于 `async_http`（违 AGENTS「禁止在 stream_select 另写 urlparse/内网名单」）**
- **位置**: `src/stream_select.py:396-408`（`_PRIVATE_HOST_PATTERN`），对照同文件 `:776`/`:1250` 用的是 `internal_stream_target_reason`
- **描述/影响**（**我复核其判据**）: 只做点分十进制前缀匹配，实测 `http://100.64.0.0/`、`http://2130706433/`、`http://0177.0.0.1/`、`http://metadata.google.internal/` 的 hostname 均不命中 → 这些形态的派生地址被**真正发出请求**（`_is_derived_hop_allowed` 是派生跳唯一的「建连前」判定，逐跳钩子在响应头已收到之后才触发，属已登记残余）。内网端口观测已经发生，只是结论事后被钩子判失败，同时两份名单必然漂移。
- **修复建议**: 保留「不做 DNS」的刻意设计，但把字面量判定收口到同一份实现——`:407-408` 改为先 `web_config._parse_ip_literal(host)`、非 None 时调 `web_config._host_internal_reason(host)`；非字面量主机仍只用正则拦 `localhost`/内部用途域名后缀。回归锁：`tests/test_regression_stream.py::TestDerivedHopScope::test_derived_hop_allowlist` 增 CGNAT、十进制、八进制、`metadata.google.internal` 四条 `is False`，并断言非字面量公网域名仍 True 且零 `getaddrinfo`。

**MR-10 `_is_same_probe_scope` 用「末两段」近似注册域 → 公共后缀下跨组织仍携带登录态 Cookie**
- **位置**: `src/stream_select.py:411-432`
- **描述/影响**: `_registrable_domain` 取 host 末两段，`.co.uk`/`.com.cn`/`.co.jp` 等公共后缀下两个互不相关的组织得到同一个值，于是被 MID-2231 认定为「跨域」的派生跳被判「同域」、保留用户 Cookie——正是 `:386-392` 注释声称已消除的凭据外泄面。现有锁 `test_different_registrable_domain` 只覆盖两段主机形态。
- **修复建议**: `:429-432` 改为「同 host 或派生 host 是列表 host 的严格子域」（`derived_host == base_host or derived_host.endswith("." + base_host)`），跨此判定一律走 `_headers_without_cookie`（探测行为不变、仍发请求，只是不带凭据，不会废掉 `test_hls_segment_404_rejects_playlist` 锁住的探测能力）。回归锁：`_is_same_probe_scope("https://cdn.example.co.uk/a.m3u8", "https://evil.co.uk/b.ts") is False` + 「跨后缀派生跳 headers 不含 cookie」行为锁。

**MR-11 `_validate_stream_url` 违反自身「异常绝不穿透」契约：入口判定的 38 行落在 `try` 之外**
- **位置**: `src/stream_select.py:749`（契约声明）、`776-813`（未保护区段）、`819`（`try` 起点）
- **描述**（**我复核其判据**）: `:776` 的 `internal_stream_target_reason`、`:793` 的 `get_record_headers`、`:813` 的 `_throttle_probe` 都在 try 之前。`urlsplit("http://[oops/x.m3u8")` 抛 `ValueError: Invalid IPv6 URL`；`rule=="origin"`（shopee）且 `live_url` 为空时 `:150` 的 `key, value = rule.split(":", 1)` 抛 `ValueError: not enough values to unpack`。
- **影响**: 平台接口（被劫持/MITM）下发一个 host 含 `[` 的字符串即让异常穿透 `_validate_stream_url` → 穿透 `select_source_url`（`:1215`/`:1390` 的 try 只有 finally）→ 房间线程外层「直播录制出错」并 `record_error(host)` 计入熔断样本，**本轮其余候选一次都不探**；与同函数 `:343-349` 已捕 ValueError 的 `_is_recordable_url` 优雅降级口径自相矛盾。
- **修复建议**: `:776` 之前先做形态判定（`if not _is_recordable_url(url): return False`），或把 `:776-813` 并入 `:819` 的 try（该段尚未建客户端，`finally` 语义不变）；`get_record_headers:149-151` 改为先判 `":" in rule`。回归锁：`tests/test_sync_probe_internal_guard.py` 断言 `_validate_stream_url("http://[oops/x.m3u8", last_resort=True)` 返回 False 且不抛；`tests/test_stream_select.py` 断言 `get_record_headers("shopee", "")` 不抛。

**MR-12 SOOP 取流：CDN 分配接口未回 `view_url` 时仍置 `is_live=True` 并交出无 scheme 的坏地址**
- **位置**: `src/spider.py:3313-3322`（登录路径）、`3381-3384`（公开房路径）
- **描述**: `get_sooplive_cdn_url` 对 HTML 拦截页/截断体回 `{}`（其自身注释 `:3028-3029` 称该接口「常返回 HTML 拦截页」），调用点直接 `.get("view_url", "")` 后拼 `"?aid=" + 票据`，无判空即写 `is_live: True`。
- **影响**: 该形态下 `anchor_name` 非空 → main 按「解析成功轮即上报成功样本」把本轮记成**成功**并进入录制链，而候选地址无 scheme、被 `async_http` 的 scheme 白名单每轮拒绝（每轮一条 warning）、永远录不上；熔断统计看不出线路已坏，与「虎牙选档不得返回空流地址」「已判开播却无源须按无源返回」的既有口径相反。
- **修复建议**: `:3314`/`:3382` 之后加 `if not _view_url: _warn_api_abnormal(...); return _result`（保持 `is_live` False），与同函数 `:3376-3379` 的 `broad_no`/`hls_authentication_key` 判空同形。回归锁（`tests/test_spider_platforms.py`）：令 `get_sooplive_cdn_url` 返回 `{}`，断言 `is_live is False` 且 `m3u8_url` 键不存在。

**MR-13 平台分派仍有 11 条无尾斜杠片段做中缀匹配，自定义流地址可被平台解析器劫持（M-03 修法不完整）**
- **位置**: `main.py:1720-1741`（`_match_host`）、`:3465-3476`（片段清单）、`:3477`（自定义流排在表尾）
- **描述**: `:1738` 把待匹配串归一为 `scheme://host/`，但片段无尾斜杠时仍是任意位置子串，既无域边界也无后缀锚定；`:1721-1729` 注释「按 hostname 归一后 fragment 只能与真实 host 匹配」不成立。
- **影响**（**我复核其复算**）: `https://s3.cn-north-1.amazonaws.com.cn/bucket/live.m3u8` 被京东片段 `3.cn` 命中、`https://webtb.cn/x.flv` 被淘宝片段 `tb.cn` 命中 → 该房间被路由到完全无关的平台解析器（恒判未开播、日志把平台名写成「京东直播」误导排障），并把该平台的**用户 Cookie 发往该任意 host**（M-03 同型，只是暴露面收窄到 11 条片段）。`s3.<region>.<provider>` 是真实存在的 m3u8 宿主命名形态。
- **修复建议**: 判定改 `host == frag or host.endswith("." + frag)`（`live.shopee` 这类 TLD 可变特例改判前缀），并把 `:3477` 的自定义流表项前移到平台表之前，或在 `_resolve_platform_stream` 里先按 `_stream_path_suffix` 短路。回归锁：`tests/test_platform_dispatch.py` 参数化两条必须落 `_resolve_custom_stream`，并对全部 `PLATFORM_HOST` 合法 host 复算「仍被原片段命中」不回归。

**MR-14 轮末「录后 30s 快检」的判据恒真：`count_time` 在判定前被就地重赋，退避被无差别覆盖**
- **位置**: `main.py:4873`（重赋）、`4895-4905`（判定与覆盖）、`:3941-3982`（`started` 语义）、`:4609-4612`（注释）
- **描述**（**我读码确认**）: `:4873` 在录制分支刚结束时把 `count_time` 重置为「现在」，`:4902` 的 `time.time() - count_time` 因此恒≈0、`< 60` 恒真；而 `record_finished` 由 `started`（=「未抛 OSError」，`check_subprocess` 对 rc≠0 与停滞终止一律返回 False）置位，失败轮同样进入快检。`:4609-4612` 注释「ffmpeg 子进程自然结束（rc==0 / 被注释退出）」与实际语义不符。
- **影响**: 任何跑完一轮 ffmpeg 尝试的房间（含 CDN 403 秒退）等待被改写为 30s，既丢掉 `delay_default`（默认 120s）也丢掉 `:4895-4896` 的「瞬时错误太多 +60s」退避 → 坏线路房间以约 4 倍频率重撞平台接口（风控放大），长录结束后的空转轮同样每 30s 撞一次。`tests/` 全仓 grep `count_time`/`record_finished` 零命中，无任何用例覆盖。
- **修复建议**: 删除 `:4873` 的重赋（保留轮初 `:4054` 基准），使 `< 60` 恢复「本轮耗时不足一分钟才快检」的原意；`record_finished` 的置位条件由 `if started:` 改为「本轮自然结束且 rc==0」（让 `_run_ffmpeg_record` 返回 `(started, comment_end, natural_ok)`）。回归锁：`tests/test_record_watchdog.py` 注入「rc≠0 秒退」与「error_window 已满」两态，断言轮末 `x` 取 `num+60` 而非 30。

### 5.3 HTTP 客户端复用与请求体上限（4 项）

**MR-15 出站响应体没有字节上限：唯一上限防线装在零 importer 的 `sync_http`，活代码 `async_req` 直接取 `response.text`**
- **位置**: `src/async_http.py:439-449`（判定面 `:446`）；对照 `src/sync_http.py:236-243`（`_MAX_RESPONSE_BYTES` = 8 MiB / `_MAX_DECOMPRESSED_BYTES` = 32 MiB + `_read_capped`）
- **描述**: `sync_http.py:240` 注释写明「与 `async_req` 的失败语义一致，不新增契约」——失败语义确实一致，**上限本身在异步侧不存在**；httpx 透明解压 gzip/deflate/br/zstd 且无字节上界，`spider.py` 有 100+ 个 `async_req` 调用点。
- **影响**: 一条被 MITM/劫持/恶意的平台响应（几十 KB 的 gzip 套娃）即可在任一房间线程内物化无界内存；80+ 房间与 Web/GUI 同进程时后果是整进程 OOM 而非单房间失败。与已定级的 SEV-2226（同步侧同型，已修）、M-08（brotli）同族，唯独活代码这一侧没吃到收口。
- **修复建议**: ①把两个常量与取值口径提升到 `src/http_config.py` 作为单一事实源（本包内、零依赖、两侧都 import，禁止第二份数字）；②`async_req` 的取文本改 `client.build_request(...) → client.send(req, stream=True)` + `async for chunk in response.aiter_bytes()` 累计判上限（`aiter_bytes` 已是解压后字节，正对应第二道），超限走既有 `_failure_result` 空值契约（**不得**改返回契约）并记一条脱敏 warning。回归锁（`tests/test_async_http.py`）：MockTransport 回 40 MiB 解压体，断言返回 `""`（含 `redirect_url=True`/`return_cookies=True` 两支）且日志含「上限」；另断言 `src/http_config` 与 `src/sync_http` 的常量是同一对象（防再分叉）。

**MR-16 `return_cookies=True` 与跟随重定向组合时，302 跳下发的登录 Cookie 被静默丢弃（MIN-2218 引入）**
- **位置**: `src/async_http.py:391`、`442-444`
- **描述**: `:443` 只取**最终响应**的 `response.cookies`；httpx 0.28.1 把每一跳的 `Set-Cookie` 存进客户端 jar，最终 `Response.cookies` 仅含落地跳自己下发的 cookie。「POST 登录 → 302 带 Set-Cookie → 200」这一最常见形态里票据落在 302 跳，返回给调用方的是 `{}`。MIN-2218 之前三条 POST 分支不跟随重定向（响应就是那个 302），该链原本成立。
- **影响**: 调用点是三个登录/取 token POST（`spider.py:2976`、`:3771`、`:4482`）与一处 `include_cookies=True`（`:6738`）；`cookie_cache.py:205` 与 spider 侧一律按「登录失败」处理并进入下一轮重试，日志只显示空 cookie、不显示「cookie 在上一跳」。**待确认**：三个接口中哪些实际以 302 下发票据需真机核对一次。
- **修复建议**: 仅当 `owned_client` 为真且 `response.cookies` 为空时回落本调用独占客户端的 jar（`dict(response.cookies) or dict(client.cookies)`），**缓存客户端绝不得读 jar**（否则破 MID-22 的账号隔离），注释写明为何只在独占客户端回落。回归锁：MockTransport 造「302 带 Set-Cookie → 200 不带」，断言 `return_cookies=True` 非空；再加一条「走缓存客户端时绝不返回 jar 内容」的负向锁。

**MR-17 `_read_json_body` 的 1 MiB 上限对 chunked 传输完全失效，且 `/api/login` 免鉴权即可读体**
- **位置**: `src/web_api.py:133-145`（我读码确认判据与注释）、`:168`（调用点）、`:601-612`（鉴权白名单含 `/api/login`）
- **描述**: 上轮 L-30 的修法只挡「声明了超大 `Content-Length`」的请求；无 `Content-Length`（`Transfer-Encoding: chunked`）时直接 `await request.json()` 全量物化。`:137-138` 注释声称「逐字节读入后的上限由 Starlette 的流式读取与调用方超时兜底」——该上界在本机 starlette 1.7.0 上不存在（`Request.body()` 是无上限的 `chunks.append(...)` 累积）。
- **影响**: 认证**关闭**（出厂默认）时局域网任一主机可单请求无限增长内存；认证**开启**时同样可达——`/api/login` 在中间件白名单内、带 body 模型，请求体在进入口令校验前就被完整读入，且该路径既不受 Bearer 保护、也不在 `_PUBLIC_BUDGET_PATHS`（`:273`）的限流面内。慢速 chunked 还能长期占住连接与协程。
- **修复建议**: 把「按声明值拒绝」换成「边读边封顶」——`async for chunk in request.stream()` 累加，超过 `_JSON_BODY_MAX_BYTES` 立即 `raise HTTPException(413, ...)`，并改正 `:137-138` 的错误承诺。回归锁：`tests/test_web_api.py` 增 chunked 用例（`httpx` 以 `content=` 传生成器 + `Transfer-Encoding: chunked`）断言 413；同时补一条 `Content-Length` 超限的 413 用例——现 `grep -rn "413|content-length" tests/` 零命中，说明 L-30 整条修复无任何用例，按 AGENTS「新增安全不变量类用例必做变异验证」应补。

**MR-18 `_key_line_pattern` 的 `lru_cache` 以请求方可控的任意字符串为键**
- **位置**: `src/web_config.py:1139-1144`；消费点 `:1171`（在判定该行是否存在**之前**就先编译）
- **描述/影响**: 缓存注释的前提是「配置文件键数量」，但 `key` 来自 `PUT /api/config` 实参（`web_api.py:1089` 只 strip、不限长度、不校验字符集），于是恶意键名也会进 LRU 常驻 128 份编译后正则，每请求各付一次 `re.escape`+`re.compile`，每条可达 1 MiB（受 MR-17 的体积面约束）。属低频、量级有限的慢性放大，不是崩溃级。
- **修复建议**: 在进入 `update_config_line` 前对 `key`/`section` 施加长度与字符集闸门（如 `len(key) > 120` 或含 `\x00-\x1f` 即 422），或把缓存改为「只缓存真实存在于 `config.ini` 的键集合」。回归锁：断言超长 key 的 PUT 回 422 且 `web_config._key_line_pattern.cache_info().currsize` 不增长。

### 5.4 并发、资源与内存界（6 项）

**MR-19 在途拉取登记无属主、无租约，等待者超时后不摘除自己的条目 → 该 key 永久失效 + 全仓唯一无界登记表**
- **位置**: `src/cookie_cache.py:160-164`、`168-177`（超时分支）、`212-219`/`232-235`（仅此两条出口 pop）
- **描述**（**我读码确认**）: `_inflight[key] = []` 只表示「有人在拉」，不记属主循环、不记租约时刻。拉取者被硬切（`collector._run` 有界排水后 `loop.close()`、任务仍 pending 即销毁）时两条出口都不执行，key 永久留在表内；此后每次调用都走等待者分支，等 `timeout + _INFLIGHT_WAIT_MARGIN` 返回空，且**每一次都往列表里追加一个永不摘除的 `(loop, waiter)`**（超时分支不做删除）。
- **影响**: 一次拉取者异常死亡即把该 (url/proxy) key 永久封死——`src/ttwid.py:203` 走 `singleflight`，表现为抖音该出口**永远拿不到 ttwid**（正是「HTTP 200 + 空 body」那族观感），且每轮每房间白等 15s；同时 `_inflight[key]`/`_generic_inflight[key]` 随重试线性增长（含已关闭循环的 future 引用）。`:71-72` 注释只交代了「等待者不永久挂起」，未覆盖「登记表不再有人认领」。
- **修复建议**: 登记属主与租约（`_inflight[key] = (loop, time.monotonic(), [])`），`key in _inflight` 时先判 `owner_loop.is_closed()` 或租约超期即视为无主、由本次调用接管为拉取者；等待者超时分支在 `with _cache_lock:` 内摘除自己那条。手法直接照 AGENTS 的 `PlatformBreaker._PROBE_LEASE_SECONDS` 先例。回归锁：构造「拉取者登记后 loop 被直接 close」的交错，断言第二次调用真的发起新拉取（`calls == 2`）且超时不增大表长。

**MR-20 状态快照的租约重臂在挂死盘上每分钟泄一条永不返回的线程**
- **位置**: `src/web_api.py:1521-1540`（租约常量 `:354-356`）
- **描述**（**我读码确认**）: `_status_worker` 跑在不可取消的 `asyncio.to_thread` 里；`:1527` 的判据只看时间（`_status_inflight and (now - _status_inflight_since) < _STATUS_INFLIGHT_LEASE`），卡死线程根本不进 `finally`（`:1505` 只清当前租约），于是每 60s 稳定新增一条；`:1537` 的 `wait_for` 超时只解除 await、不回收线程。
- **影响**: 触发条件为录制盘是 UNC/网络盘/已挂起的可移动盘且 `utils.check_disk_capacity → shutil.disk_usage` 永不返回（MID-34 注释自列场景，无需任何开关）。默认 executor（`max_workers=min(32, cpu+4)`）约 30 分钟被占满，同循环内其它 `asyncio.to_thread` 消费者（含 `src/utils.py:216`/`:251` 两个 seam）全部排队——与 `:351` 承诺的「把『慢』限制在数据新鲜度上而非可用性上」相反。**待确认**：可在不挂真盘的前提下用替身 + `SimpleNamespace` 假单调钟验证线程数（按 AGENTS 不得直接替 stdlib）。
- **修复建议**: 重臂条件加并发上限——模块级 `_status_hung_workers` 计数（`_status_worker` 进入 +1、`finally` -1），仅当计数 < 2 时才允许过期租约重新派发，否则继续回陈旧快照；注释写明「租约换来自愈，代价是有界线程」。回归锁：把 `_read_engine_status` 打成永不返回，推进假时钟，断言实际进入次数 ≤ 2（现无该锁）。

**MR-21 config.ini / URL_config.ini 写盘失败被上报为成功（MIN-2243 家族的漏网面）**
- **位置**: `src/web_config.py:1215-1216`、`806-807`（丢弃返回值后 `return True`）；消费点 `src/web_api.py:1274-1277`、`1074-1076`、`1051-1052`；底层 `src/utils.py:556-558`/`573-579`（**我实测**失败路径 `logger.warning` + `return False`）
- **描述**: web_config 三个写入点都不接 `_atomic_write_text` 的返回值；端点侧 `if not ok: 404` 因此只能表达「键不存在」，表达不了「没落盘」。房间侧（`update_room`/`delete_room`）已按 MIN-2243 用「负信号 + 重解析裁决」补齐，config.ini 侧与画质侧从未补。本模块注释自己就写明「返回值为 bool：上层只关心是否落盘（旧实现靠异常传播，**调用点均未接返回值**）」（`web_config.py:823-824`）。
- **影响**: 触发条件为目录只读/磁盘满/Windows 杀软占用（不需要用户开任何开关，认证关闭时局域网可达）。后果是 `PUT /api/config`、`PUT /api/rooms/qualities`、`PUT /api/rooms/quality` 全回 `{"ok": true}`、面板显示「已保存」而文件字节未变——用户以为凭据/画质/开关已生效，与 MIN-2243 修掉的形态逐字相同。仅日志里有一条 `写入配置文件失败（已保留原文件）` warning 留痕。
- **修复建议**: 三处改 `return _atomic_write_text(...)`；端点侧区分 404（键不存在）与新稳定机器码（如 `config_write_failed`，走 `_log_internal_error` 口径），或按房间侧同款「重解析裁决」。回归锁：`monkeypatch.setattr(web_config, "_atomic_write_text", lambda *a, **k: False)` 后 `PUT /api/config` 必须非 2xx（同族用例已在 `tests/test_config_io_update_file.py:170/224`，可直接照搬；现 `grep -rn "atomic_write" tests/test_web_config.py` 只有 no-leftover-tmp 一条）。

**MR-22 `utils.update_config` 的锁已补齐，但 `atomic_write_text` 的非 OSError 出口仍泄漏 fd 与半写临时文件（内容是含凭据的整份配置）**
- **位置**: `src/utils.py:554-581`（`mkstemp` 取 fd/tmp 于 try 之外，`:573` 捕获集为 `except OSError as e`）
- **描述/影响**: `os.fdopen(fd, "w", encoding=..., errors=...)` 遇非法编码名抛 `LookupError`（fd 不关、tmp 不删）；`f.write(text)` 遇 lone surrogate + strict codec 抛 `UnicodeEncodeError`（tmp 文件留在目录、fd 由 with 关闭），两者都绕过 `return False` 契约直接抛给调用方。触发概率低（`main.text_encoding` 恒为 `"utf-8-sig"`、读侧 `config_io.py:341` 有 `errors="replace"`），但一旦命中，产物是 `config/` 目录里一份内容为**完整新配置**（含 `[Cookie]`/`[账号密码]` 明文）的 `<name>.<random>.tmp` 常驻文件，而 `config/` 也是用户打包上传求助的目录；fd 泄漏在长期运行的守护线程里会累积。`main.py:2383` 等调用方捕获集是 `(configparser.Error, OSError)`，接不到该异常，会一路穿到房间线程外层。
- **修复建议**: `:573` 之后补一支 `except Exception as e:`，执行同样的 `os.remove(tmp)` + warning + `return False`（告警文案复用 `:557`/`:574` 既有 msgid，不新增模板）；`os.fdopen` 用嵌套 try 在失败时 `os.close(fd)`。回归锁进 `tests/test_utils.py::TestAtomicWriteTextDurability`：以 monkeypatch 令 `_replace` 抛 `UnicodeEncodeError`，断言 `list(parent.glob("*.tmp")) == []` 且返回 False。

**MR-23 归档窗口内 `sys.stdout/stderr` 指向已关闭对象，其它线程的 `print()` 抛 ValueError**
- **位置**: `src/log_archive.py:127-149`
- **描述**: 顺序是「`stream.flush()` + `stream.close()`」→「`os.rename`」→ 最后才 `_rebind_web_console()`；close→rebind 之间 `sys.stdout` 仍是那个已关闭的 TextIOWrapper（`print()` 在调用时才查 `sys.stdout`）。MID-2258 只修了「改名后重开失败 → 永久黑洞」这一支，成功支的瞬态窗口没管。
- **影响**: 触发条件为 Web 面板点「停止录制」（`toggle_recording` → `archive_runtime_logs(reopen_streams=True)`，`web_api.py:840-842`）且此刻录制线程正在打印。后果是窗口内其它线程的一次 `print()` 抛 `ValueError: I/O operation on closed file`，被上层宽 except 吞成一条无归因错误日志（`recorder_status.display_info` 还会因此触发一轮指数退避）；窗口长度取决于盘速（网络盘可达数十毫秒）。
- **修复建议**: 在 `:128` 的关闭循环之前先做一次「让位」——`sys.stdout = sys.stderr = open(os.devnull, "w", encoding="utf-8")`（失败则跳过，语义与 `_rebind_web_console` 既有的黑洞回退同源），再 flush+close 真实句柄、改名、`_rebind_web_console(path)`。回归锁：`tests/test_log_archive.py` 新增用例——绑一个可记录 close 状态的假流到 `sys.stdout`，在 rename seam 打桩并断言「桩被调用时 `sys.stdout` 已不是那个已关闭对象」。

**MR-24 Windows 侧代理信息构造在 try 之外使 `ValueError` 逃出，且 `_is_proxy_enabled_windows` 未随 L-17 一起收口**
- **位置**: `src/proxy.py:239-262`（构造点 `:262`）、`264-278`（enabled 判定）；消费点 `main.py:5159-5165`
- **描述**: `:262` 的 `ProxyInfo(...)` 位于 `:239-259` 的 try/except **之后**：注册表 `ProxyServer` 存「无端口的主机名/裸 IPv4」（`proxy.example.com`、`http=10.0.0.1`）时 `_split_host_port` 回 `port=""`，`__post_init__` 抛 `ValueError("IP or port cannot be empty")` 直接逃出 `get_proxy_info()`——MIN-2233③ 专为「裸 IPv6 无端口」开了放行分支，同形态的 v4/域名却仍走 raise。`_is_proxy_enabled_windows` 又只判 `ProxyEnable == 1`，不校验 `ProxyServer` 能否解析出 ip+port，L-17 的修法只落在 Linux 侧（`_is_proxy_enabled_linux` 已复用解析，`:293-303`）。
- **影响**: 一次畸形注册表值使系统代理信息整块丢失，`global_proxy=True` 却无任何地址读数（MIN-20①/L-17 记过的「显示有代理、实际直连」归因带偏形态）；`ProxyEnable=1` + `ProxyServer` 为空时 main 打印 `System Proxy: http://:`。`tests/test_proxy.py` 对两个 Windows 分支**零覆盖**（全文件无 `winreg` 替身），Linux CI 上一条都没跑过——属 AGENTS「平台专属分支不得靠 skipif 让 CI 跳过」的反面实例。
- **修复建议**: ①把 `:262` 的构造并入 try（或独立 try）捕 `ValueError` → `logger.warning`（带 `type_name`）→ 返回空 `ProxyInfo()`，注释写明与 Linux 侧 `if ip and port` 守卫同口径；②`_is_proxy_enabled_windows` 改「ProxyEnable=1 **且** ProxyServer 能解析出 ip+port」，与 `_get_proxy_info_windows` 共用同一次解析（不得各解析一遍）；③回归锁按 AGENTS 用 `sys.modules`/monkeypatch 注入 `winreg` 替身让 Windows 分支在 Linux CI 真跑，覆盖「ProxyServer 无端口」「ProxyEnable=1 但 ProxyServer 为空」两格。

### 5.5 弹幕链路与平台适配层（5 项）

**MR-25 停止后弹幕回调仍进监控枢纽，把已 `room_stopped` 的房间重登记成永久幽灵行**
- **位置**: `src/collector.py:537-548`（`_on_message`/`_on_ready` 不判 `_stop_called`/`_stop_event`）；重登记落点 `src/danmaku_monitor.py:402-405`
- **描述**（**我读码确认**）: `room_message` 对未知房间走 `state = self._default_state("未知"); self._rooms[room] = state`，而 `room_connected`/`room_closed` 都有 `if state is not None` 守卫——唯独消息路径会重插；`stop()` 在第一行就已投 `room_closed`（`:263`）。
- **影响**: 采集线程未被回收（MR-26）或消息恰在 `main.py:5838` 的 `room_stopped` 之后送达时，监控页重新出现一行「平台=未知」的房间、携带旧弹幕计数且永不消失（`WsClient.close()` 之后不再回报 on_close）——正是 AGENTS「弹幕监控房间须随录制线程退出而移除」要消灭的回归形态。
- **修复建议**: `_on_message`/`_on_ready` 顶部加 `if self._stop_called or self._stop_event.is_set(): return`（早退即不投枢纽、不入 SRT 队列），`_on_close` 保留（幂等由 `_close_reported` 保证）。回归锁：`stop()` 后再调 `_on_message`，断言 `hub.snapshot()` 的 rooms 不含该房间且 `msg_total` 不增。

**MR-26 采集线程 join 超时完全静默，而同函数对 SRT 写线程超时有告警**
- **位置**: `src/collector.py:301-302`（对照 `:320-329`）
- **描述/影响**: `self._join_thread(self._thread, timeout)` 之后不查 `is_alive()`；线程未退出时其事件循环、`WsClient` 连接、平台 SDK 句柄与 `_shutdown_task` 一并滞留到进程结束（daemon 线程），一条日志都没有。这是 MR-25「枢纽幽灵房间」与句柄累积的唯一上游触发器，叠加后表现为长跑进程里房间数持续增长的线程与 socket，而 `streamget.log` 无任何线索可归因；`_join_thread`（`:237-251`）还把 join 的 `RuntimeError` 记成 debug，进一步压低可见性。
- **修复建议**: `:302` 之后补 `if self._thread.is_alive(): logger.warning(...)`，观测值复用 `_SRT_SHUTDOWN_JOIN_TIMEOUT` 的「常量非文案」口径。回归锁：注入 `start()` 永不返回且 `stop()` 挂住的替身，`caplog` 断言出现该 warning（现有 `test_stop_signal_not_dropped_*` 只覆盖「退出」侧）。

**MR-27 L-21 的新判据恒取「异常」分支：设计内的停止路径被报成「运行异常」**
- **位置**: `src/collector.py:431-452`（判据 `:443`），投递点 `:363-370`（`_shutdown` 的 cancel → `sleep(0)` → `loop.stop()`）
- **描述**（**我用项目 Python 独立复现**）: `:438` 捕获的 `RuntimeError` 在停止路径上就是 `Event loop stopped before Future completed.`，该异常的定义即「future 未完成」，因此 `self._start_task.cancelled()` 必为 False、else 分支恒命中。我的实验读数：`RAISED: RuntimeError Event loop stopped before Future completed.` / `task.done()= False task.cancelled()= False`（清理链含 await 的形态，与各平台 `connect()` 的解链一致——`ws_client.py:217` 的 `async with __aexit__`、`:275-289` 的 `finally: await hb_task`）。`:441-442` 注释声称的「被取消（`_shutdown` 路径）吞掉」在这条路径上从不成立。
- **影响**: 凡 `_start_task` 在 `loop.stop()` 时尚未自行结束（`danmaku.stop()` 超时分支必然、平台清理链含 await 的取消中常见），每次「停止录制」就落一条 `[弹幕采集]… 运行异常,不影响录制` warning，与 `:344-346` 的「stop() 超时」告警叠加成双条；而 L-21 真正要抓的平台侧 `RuntimeError` 混在同一文案里无法区分，归因价值反转为噪音。既有 MIN-23 用例 `tests/test_collector.py:61-80` 的 `_FinallyChainDanmaku` 的 finally 里**没有 await**，恰好落在「取消一轮内完成」的形态，因此抓不到。
- **修复建议**: 判据改为本轮是否由停止触发——`if self._stop_called:` 视为设计内路径吞掉，仅 else 补 warning；`_stop_called` 且任务未 done 时改记 debug。回归锁：把 `_FinallyChainDanmaku.start()` 的 finally 改成 `await asyncio.sleep(0.05)`，`caplog` 断言 `stop()` 后无 `运行异常` warning；另一用例不触发 stop 而在 `start()` 内抛 `RuntimeError`，仍须出 warning。

**MR-28 B站 host 轮换闸门吞掉「会话期内」的终态断连，`room_closed` 永久缺失**
- **位置**: `src/platforms/bilibili.py:79-91`（判据 `:80`）、`129-159`（登记 `:134`、连接 `:153`、归零 `:159`）
- **描述**（**我读码确认顺序**）: 闸门「仍有候选 host 未尝试」只在会话尚未建成时成立。一旦 host[0] 建成会话后连接死亡且 WsClient 自身重连耗尽，`_report_close` 是在 `await self._ws.connect()` **内部**被调用的，此刻 `_hosts_left` 仍是 `len(hosts)-1 ≥ 1` → 该终态断连被降级为 `_on_reconnect`（debug），`hub.room_closed()` 永不发出；`connect()` 返回后又因 `_session_ok` 恒真而 break，`:159` 的归零发生在判定**之后**。`:156-158` 注释自己写明「会话期间若真发生重连耗尽就是终态，必须照常上报」。
- **影响**: B站 `getDanmuInfo` 正常返回 2 个以上 host（`spider.py:2418-2425` 原样透传 host_list，本层是唯一闸门），故 `idx=0` 即命中。表现为主播端/B站侧断连后采集线程静默退出、监控页整段录制期间显示「已连接」，唯一线索是一行 debug——即 MID-2245 要消灭的观感换了触发点。
- **修复建议**: 在 `_on_ws_ready`（`:161-171`）里会话建成时即置 `self._hosts_left = 0`（一次成功建连之后任何关闭都是终态），`:159` 的归零保留作幂等。回归锁：把 `tests/test_bili_host_rotation.py` 的 `_StubWs.connect` 改成「fire on_ready → 等一个可注入事件 → 才 fire on_close 并返回」，让 on_close 落在 `connect()` **仍挂起**时，断言 `reported == [reason]`（现有 `test_mid_session_exhaustion_after_successful_session_reports` 只在 `start()` 返回后手工调 on_close，结构上表达不了该时序，因此对本缺陷全盲）。

**MR-29 `_auth_watchdog` 的作废判据在同一 WsClient 内部重连时失效，可把健康连接误判为认证被拒**
- **位置**: `src/platforms/bilibili.py:199-219`（作废判据 `:211`、ready 重置 `:166`、再挂看门狗 `:171`/`:199`）；对照 `src/ws_client.py:236-244`（每次握手成功都重放 `on_ready`，不换实例）
- **描述**（**我读码确认两侧**）: 注释称看门狗以「连接实例」区分新旧会话，但 WsClient 的内部重连**不换实例**，于是同一实例上每轮重连都再挂一支看门狗、旧那支的 `self._ws is not ws` 恒假、永不作废，且 `_on_ws_ready` 每轮把 `_auth_ok` 重置为 False。
- **影响**: 触发条件为距上一支看门狗到期不足 8s 时发生重连、且新连接的 AUTH_REPLY 晚于**旧**看门狗截止点。命中时 `_reject_auth()` 误判：置 `_stopped`、断开健康会话（本段弹幕全丢、采集线程随 `start()` 返回而退出）、打出误导性的「进房认证 8 秒无回应」warning，并无谓作废 spider 侧 buvid 缓存（`spider.py:2392-2394` 的下层代理上下文缓存一并清，下一轮重走获取链）。现有锁 `tests/test_platform_danmaku_offline.py:607` 只覆盖「切 host」这一支。
- **修复建议**: 加一枚 `_join_epoch` 计数（`_on_ws_ready` 自增），`_join_room` 捕获发送时的 epoch 传给 `_auth_watchdog(ws, epoch)`，判定改 `if self._ws is not ws or self._join_epoch != epoch: return`；或在 `_on_ws_ready` 里取消上一支看门狗任务（保存 `spawn_danmaku_task` 返回值）。回归锁：同一 WsClient 实例上连挂两支看门狗、令第二支的 `_auth_ok` 在其截止之后才为 True，断言不出现 `_reject_auth`（替身记录 `fail()` 调用次数）。

### 5.6 GUI / UI 控件层 / i18n（3 项）

**MR-30 启动期语言在 `set_language` 之前定型：非中文语言下弹幕实时流恒空，且既有自愈分支的前置条件不成立**
- **位置**: `gui.py:1602`（哨兵定型）↔ `1639`（`_build_sidebar`）↔ `1846`（`set_language`）；比较点 `:4032`；下拉初值 `:2596`；未触发的自愈分支 `:3995-4007`
- **描述**（**我实测目录键 + 读码**）: `__init__` 第 1602 行 `self._danmaku_filter = i18n_module.tr("全部房间")` 早于 `_build_sidebar()`（1639）内的 `set_language`（1846），按导入默认的 zh_CN 定型；`_build_danmaku_page` 随后（2596）用**已切换后的语言**设下拉初值。我实测 `i18n/en_US.json` 与 `en_GB.json` 都有 `全部房间 → "All Rooms"`、`zh_TW.yaml` 有对应条目 → `:4032` 的 `filter_value != tr("全部房间")` 恒真且 `room != filter_value` 恒真 → 每条消息 `continue`。**自愈路径不触发**（我读了 `:3995-4007`）：`current` 已是 "All Rooms"、恰在 `values_list` 首项，故 `if current not in values_list` 为假、不会同步 `_danmaku_filter`。
- **影响**: 配置语言为 en_US/en_GB/zh_TW（含英文系统的默认解析）时 GUI 首启即进入该态：房间统计正常但「实时弹幕」恒显示「暂无弹幕数据」，直到用户手动重选筛选下拉（`:2648`）或切换一次语言（`:1944`）。zh_CN 下恒等、不显现，故 conftest 恒等钉定的单测与中文环境全测都漏。同型 `_quality_default_label`（`:1591`）因 `:2450`/`:2479` 两侧同语而自洽，仅显示层错语言。AGENTS 关键约定 #16 只要求 `_setup_ui` 末尾回填**控件标签**，未覆盖**非控件哨兵属性**——文档口径需补一句。
- **修复建议**: 把语言解析 + `set_language`（现 `:1834-1846`）抽成 `_resolve_initial_language()`，在 `__init__` 顶部（早于 `:1591`）调用一次；`_build_sidebar` 只读已生效语言填初值。回归锁（`tests/test_gui_language_retranslate.py`）：钉 `set_language("en_US")` 后构造，断言 `_danmaku_filter == i18n.tr("全部房间")`，并驱动 `_render_danmaku_stream` 注入一条 msg 事件后断言文本含该消息行、不含「暂无弹幕数据」。**变异验证锚点**须取「钩子处唯一」的多行块（单行锚点会命中 `__init__` 里的同名赋值，而桩实例跳过 `__init__`，变异会静默不生效）。

**MR-31 `retranslate_all` 无逐条异常隔离：打开并关闭过一次「高级设置」后，每轮语言切换的回填被整体中断**
- **位置**: `src/ui_i18n.py:71-95`（循环 `:84-92`、剪枝 `:93-94`）；触发面 `gui.py:804`（`apply_title(self.window, T("高级设置 - config.ini"))`）与 `gui.py:2893-2907`（实例长期持有、关闭只 destroy、以 `winfo_exists()` 判活）
- **描述**（**我读码确认循环体无 try**）: 回填循环对每个控件直接调 `title()/heading()/configure()`，任何一条抛 `TclError` 即整轮中断；`_ENTRIES[:] = alive` 在循环之后，中断时既不剪枝也不继续回填。`AdvancedSettingsWindow` 的 Python 对象仍存活（gui 从不置 None），弱引用不清理、Tcl 窗口已销毁 → 每轮回填都在该条抛错。`registered_count()`（`:64-68`）按存活过滤，因此该缺陷对现有测试不可见（见 LR-36）。
- **影响**: 该条之后的登记控件不再回填；且 `gui.py:1941-1951` 把「`retranslate_all()` → 哨兵重置 → 动态面刷新 → 托盘 `rebuild_menu()`」合并在**同一个 try**（config 写回另起 try 符合「两段独立 try」下位要求，但违 AGENTS #16「每步独立 try」），于是抛出后 `_quality_default_label`/`_danmaku_filter` 重置、四个 `_update_*` 与 `tray.rebuild_menu()` 全部跳过，只剩一条「界面重译失败」warning——AGENTS 要求的四步序列实际不执行、界面长期中英混语且不随下次切换自愈。
- **修复建议**: 循环内逐条 `try/except tk.TclError`，except 分支用 `winfo_exists()` 判定并当轮剪枝；`_ENTRIES[:] = alive` 移进 `finally`；返回「实际应用条数」并在有失败时落一条带 `type_name` 的 warning。同批把 `gui.py:1941-1951` 拆成 per-step try（至少 retranslate / 哨兵+动态刷新 / 托盘三段各落一条告警）。回归锁：假控件序列 `[w1, w_boom(抛 TclError), w2]`，断言不抛、w2 被回填、第二次调用时 w_boom 已剪枝；再一条 monkeypatch `ui_i18n.retranslate_all` 抛异常、断言 `_danmaku_filter` 仍被重设为当前语言 `tr("全部房间")` 且 `system_tray.rebuild_menu` 仍被调用。

**MR-32 `ui_theme.load/save_theme_preference` 遇非 UTF-8 的 config.ini 抛 `UnicodeDecodeError`，违背「主题绝不能阻断 GUI 启动」**
- **位置**: `src/ui_theme.py:219-240`（except 子句 `:226`，我读到的原文是 `except OSError, configparser.Error:`）；调用面 `gui.py:1495`（无 try）
- **描述**: `configparser.read()` 内部只吞 `OSError`，非 UTF-8 字节流抛的是 `UnicodeDecodeError`（`ValueError` 子类），直接穿透；`save_theme_preference` 经 `update_or_append_config_line` 同样穿透。
- **影响**: 中文 Windows 用户用记事本「另存为 ANSI」保存过 `config.ini`（本仓写入侧一律 `utf-8-sig`，读取侧未防）→ GUI 在启动阶段崩退，崩点是主题读取、报错文案与「主题」毫无关系，排查成本极高。同文件 `detect_system_appearance` 的 Windows 分支（`:157-169`）也只捕 `OSError`，`int(value)` 在 `AppsUseLightTheme` 被 GPO 写成 REG_SZ/REG_BINARY 时抛 ValueError/TypeError 穿透（本条一并修复）。
- **修复建议**: `:226` 改 `except OSError, configparser.Error, UnicodeDecodeError:`，注释补一句「`configparser.read` 不吞 `UnicodeDecodeError`」的判据；save 侧同样包一层并返回 False；`:167` 改 `except OSError, ValueError, TypeError:`。回归锁：`tests/test_ui_theme.py::TestPreferencePersistence` 增 `test_non_utf8_file_is_unset`（写 GBK 字节后断言读到 `""`、save 返 False、不得抛）与假 `winreg` 返回非 DWORD 时 `detect_system_appearance()` 回 `"light"` 不抛。

### 5.7 Web 面板后端（3 项）

**MR-33 M-10 残留：认证开启 + 通配绑定下面板连 `/api/login` 都 403，且该形态无告警、无行动指引**
- **位置**: `src/web_api.py:593-600`、`:1593-1609`；`src/web_config.py:1040-1060`；`web.py:244-254`
- **描述**: 通配绑定（`0.0.0.0`/`::`）时 `is_origin_allowed` 末尾只剩 `is_loopback_bind_host(host)` 一条出路，非回环 IP 的 Origin 恒判否（M-10 已知的 fail-closed）。上轮选了「修文档」一侧：`web_config.py:79-84` 与 `web.py:251-253` 都补了说明，但只覆盖 `DOUYIN_WEB_ALLOW_INSECURE` 的**无认证**分支；「认证开启 + 绑 `0.0.0.0`」这一完全合法的远程部署形态既不打警告，403 的 detail 又是一串未翻译英文（`"cross-origin request denied"` 不属稳定机器码白名单），用户拿不到任何线索。
- **影响**: 触发条件为 `web_auth_enable=true` 且 `web_host=0.0.0.0`（远程部署常见组合，无需开任何例外开关）；后果是登录页直接 403、面板彻底不可用，而解锁唯一途径是手工登记 `web_allowed_hosts`——这项写入本身也被 403。**待确认**：是否属维护者刻意保留的行为姿态。
- **修复建议**: ①给这条 403 换成稳定机器码 + 一条 tr 过的 `message`，在「Origin 端口==实际绑定端口、但 host 是非回环 IP 且 bind_host 为通配」时点名 `web_allowed_hosts`；②`web.py` 在认证开启且绑定非回环时也打印同一段登记提示。回归锁：`tests/test_web_api.py` 断言 `bind_host="0.0.0.0"` + `web_auth_enable=true` + `Origin: http://192.168.1.5:8000` 的 `POST /api/login` 响应体含 `web_allowed_hosts` 字样与机器码键。

**MR-34 `web_tray` 的用户可见文案全部硬编码中文；`_on_exit` 的 `os._exit(0)` 分支绕过 atexit 链**
- **位置**: `src/web_tray.py:146-159`、`:252-259`
- **描述**: 本模块已 `import i18n` 但只在 `:140` 一处用 `tr()`；托盘菜单项（`"显示控制台"`/`"退出程序"`）、图标 tooltip 与两条 `print` 播报都是裸中文常量，`set_language("en_US")` 后仍原样显示。`_on_exit` 在 `server is None` 时走 `os._exit(0)`，该调用不经 atexit。
- **影响**: 文案侧=非简中语言下托盘区为简中，与关键约定 #16 的接线口径不符；且 `extract_i18n_strings.py` 不认 `pystray.MenuItem`，属 AGENTS #14 提取器盲点的又一形态（门禁看不见）。`os._exit` 侧=当前不可达（`web.py:314` 恒传 `server=server`），但一旦有人复用本类而不传 server，就退化成「托盘点退出 → ffmpeg 残留 + 日志不归档」。
- **修复建议**: `:147/:148/:153/:159` 改 `i18n.tr(...)` 并把四条目 + `web/app.js` 内嵌目录同批登记（托盘文案是构建期定型，需随语言切换重建菜单或至少在 `start()` 时按当前语言取值）；`:256-259` 的无 server 分支改 `raise SystemExit(0)`（走解释器正常退出 → atexit 生效），或在注释写明「本类要求调用方必须传 server」并删掉该分支。

**MR-35 422/400 的用户可见文案只改了一半：`web_models` 与 `web_config` 抛的中文串仍直出**
- **位置**: `src/web_api.py:84-85`（承诺）、`:173`、`:874`、`:934`、`:1038`、`:1069`、`:1260`
- **描述**: `bf43acc` 把端点里内联的中文字面量逐条包了 `i18n_module.tr()`，但 `raise HTTPException(422, str(exc))` 这几类的消息来自 `src/web_models.py`（`_as_str`/`_require_dict`）与 `src/web_config.py`（`_reject_newline`/`_check_url_target`/`validate_room_target`），从未进目录，前端 `apiError` 原样显示 detail。
- **影响**: 触发条件为面板语言设为 en_US/en_GB/zh_TW 且提交非法 body/房间地址/含换行的值（任意写接口误用即可）；后果是英文界面弹出简中句子，与本文件头注释的承诺不符。`extract_i18n_strings.py` 与 `test_runtime_templates_covered_by_catalog` 只认 `tr()` 调用首参，看不见这类「未包 tr 的字面量」——关键约定 #14 盲点的又一形态。
- **修复建议**: 端点侧把 `detail=str(exc)` 改为 `detail=i18n_module.tr(str(exc))`（目录缺条目时 `tr()` 恒等返回，安全），或在 web_models/web_config 的模板位包 `tr()` 并把相关 msgid 同批登记四目录 + `web/app.js`。回归锁：`tests/test_i18n_migration.py` 增枚举——本包 `HTTPException(4\d\d, str\(` 命中数设为只降不升的棘轮上限。

### 5.8 构建 / 安装 / 签名脚本（4 项）

**MR-36 第③类钉定对「真正被执行的那份库」fail-open，且其表值与检出字节失配**
- **位置**: `src/utils.py:119-172`、`236-249`（两个校验入口都只算**被执行脚本本体**）↔ `src/javascript/haixiu.js:517-519`、`liveme.js:348-350`（`require(cryptoJSPath)` 从磁盘路径加载）↔ 调用点 `src/spider.py:5103`、`:6095` 以字符串实参传入路径；钉定表 `src/utils.py:85-100`
- **描述**（**我实测**）: `_check_js_hash` 只在 `get_compiled_js(js_path)`（`utils.py:168`）与 `run_node_script_async(script_path)`（`:239`）里被调用；`crypto-js.min.js` 的路径从不经 `open(...,'rb')` + 哈希，因此该条目只对「键集双向相等」用例可见、对执行面是装饰性的。同批实测：对 5 个 `.js` 逐一计算工作区字节 sha256 与表值比对——`haixiu.js`/`liveme.js`/`migu.js`/`x-bogus.js` **MATCH**，`crypto-js.min.js` **MISMATCH**（工作区 `e0b059455ee6…`/60821 B vs 表值 `9d13c4dba10b…` = git blob 60820 B 的 LF 形态），仓库无 `.gitattributes`、本机 `core.autocrlf=true`。`tests/test_utils.py:800-835` 三条用例只锁「表 == 硬编码集」「表里的键都有文件」「盘上 `*.js` == 表键集」，**没有任何一条比对实际哈希**（`CODE_WIKI.md:1845` 已自认该盲区）。
- **影响**: 本机执行面——替换该文件即在本机 node 进程内执行任意代码，可读走 `sign()` 的全部入参（含 `spider.py:6086-6090` 的 `accessToken`/`tku`/`c`）、可读同目录其它文件、可出网，默认形态连一条告警都不会打；`DLR_JS_STRICT_HASH=1` 同样拦不住（它压根不进校验路径）。录制失败面——被改坏的库产出错误签名，表现为海秀/LiveMe 全量解析失败，正是 `utils.py:67-69` 自述要防的「极难归因」形态。第二半后果：一旦按建议纳入执行期校验，Windows 用户会得到**永久**的「疑被篡改」告警、strict 模式直接拒签，而 Linux CI 因不转换行反而全绿。
- **修复建议**: ①新增 `.gitattributes` 一行 `src/javascript/*.js -text`（只对被钉定/被执行的这 5 个文件取消换行转换，不动其它目录，避免与本仓 CRLF/LF 混存现状互撞），使「检出字节 == blob 字节」在所有主机成立；②Python 侧在 `run_js_async` 进入 `_sync_call` 之前遍历 `args` 中的 `str` 实参，`os.path.realpath` 归一后凡落在 `JS_SCRIPT_PATH` 内且扩展名为 `.js` 者读字节并 `_check_js_hash`（strict 下拒执行）；③JS 侧同步收窄——`sign()` 入口校验 `cryptoJSPath` 的 basename 恰为 `crypto-js.min.js`，不符即 `throw`；④补 `tests/test_utils.py::test_pinned_sha256_matches_on_disk_bytes` 与 `test_js_require_target_is_hash_checked`（`monkeypatch.setenv` 置 strict + 篡改副本，断言抛错且 `execjs.compile` 从未被调用，证明「校验先于执行」）。**定级说明**：工作包自评「严重」被我下调为中等——触发前提是攻击者已能改写安装目录内文件（本机执行面），不属本仓自述的远端平台/CDN 威胁模型；但字节失配与「无哈希比对用例」是本机实测事实，属必须补的完整性缺口。

**MR-37 TOFU「基准存在但读不出」在 node 侧仍 fail-open，且 ffmpeg/node 两支对 `UnicodeDecodeError` 失明（L-44 半修）**
- **位置**: `src/node_install.py:164-169`（我读码确认 `except OSError as e:` → warning → `return True`）、`src/ffmpeg_install.py:276-301`（只捕 `OSError`）；对照已收紧的 `src/ffmpeg_linux_download.py:251-279`（`:268` 并捕 `(OSError, UnicodeDecodeError)`）与 `src/ffmpeg_master_download.py:295-315`
- **描述**: 两支都用 `read_text(encoding="ascii")`，基准文件被外部转成 UTF-8 时抛的是 `UnicodeDecodeError`（`ValueError` 子类、非 `OSError`），两支接不住；Linux 孪生在 `:258-267` 专门写长注释说明「必须并捕」，这两处没有。`tests/test_node_install.py:217-222` 把放行钉成期望行为，`:224` 注释仍称「与 ffmpeg 侧同一口径」——该句已被同批改动证伪。
- **影响**: 运行期安装链。node 侧：「官方清单不可达 ∧ 基准不可读 ∧ CDN 投毒」→ 未校验二进制被解压进 `execute_dir/node` 并被 PATH 命中执行；ffmpeg 侧：非 ASCII 基准使异常穿出 `_check_or_record_zip_sha256` → 落到 `download_ffmpeg_official` 的宽 except（`:419-421`），既不打印「请删除该基准后重试」的行动指引，**也不删 zip**（删包只在 `:367-372` 的 False 分支）→ 下次运行 `is_valid_zip` 通过、重下被跳过、再次抛同一异常，永久不自愈且 `execute_dir` 长期挂一个 ~70 MB 残包。发布链不受影响（走钉定哈希/签名档）。
- **修复建议**: 两支 except 改 `(OSError, UnicodeDecodeError)`；node 侧改 fail-closed（error + 删包 + `return False`），与 `ffmpeg_install.py:288-301` 同形态；同批把 `tests/test_node_install.py:217` 的预期改为 False、删掉 `:224` 失真注释、补一条非 ASCII 基准用例（对齐 `test_non_ascii_baseline_refuses_without_raising`）。

**MR-38 Linux 直下在「官方 digest 已通过」时不写 TOFU 基准，与模块自称的第二道防线矛盾**
- **位置**: `src/ffmpeg_linux_download.py:221-235`（对照 `:248-250` 的自述）
- **描述**: `_verify_archive` 的官方分支只 `logger.debug` 后 `return True`，从不写 `_baseline_path`；而两个孪生模块在权威通过时同样记账（`ffmpeg_install.py:266-267`、`node_install.py:154-155`，注释理由为「这样将来某次取不到官方文档时手上仍有一份可比对的基准」）。`hash_file = _baseline_path(...)` 直到 `:236` 才取、只在降级分支使用。
- **影响**: 常态（API 可达）永远不留基准 → 一旦落入「API 限流/403 取不到 digest」那一格：`master_allowed=False` 直接拒装（fail-closed，可接受）；`master_allowed=True` 则**每次**都是首次记账、拿当次下载的字节自证，即 AGENTS「为什么 TOFU 不足以作为唯一防线：首次安装那一次没有任何可比对的期望值」所述窗口在每台机器上反复重开。发布链无关。
- **修复建议**: 在 `:234` 之后补 `_baseline_path(dest_dir, source_url).write_text(current, encoding="ascii")` + `_prune_stale_baselines(...)`，记账失败只 warning、不改判定。回归锁扩一条：digest 命中且 `master_allowed=False` 时 `_ffmpeg_linux*.tar.xz.sha256` 恰存在 1 份且等于实算值（与 `test_no_digest_and_switch_off_refuses` 的「拒装不留基准」不冲突，注释写明两处区别）。

**MR-39 发布目录凭据闸门只覆盖两个已知名，`config/` 下其它文件原样进对外 zip**
- **位置**: `build_exe.py:344-350`（复制侧，我读码确认 `if item.name in known or not item.is_file(): continue` → `shutil.copy2`）↔ `:353-397`（闸门侧只读 `URL_config.ini`(`:367`) 与 `config.ini`(`:378`)）↔ `:273`（`CREDENTIAL_FILE_NAMES`）
- **描述**: 「不产生」一侧按名脱敏重写两个文件，「产生了就拦住」一侧也只比对这两份的内容；构建机 `config/` 里的旁支（`config.ini.bak`、`URL_config.ini.local`、手抄 cookies）既不脱敏也不扫描即进对外 zip。该函数注释自述要防的正是「继 `.gitignore` 与 `.dockerignore` 之后的第三条外发通道」。
- **影响**: 主要打**本地/手工 `--dual` 构建**（维护机通常已填真实 Cookie/代理/面板口令）；CI 干净检出不可达（我实测仓库 `config/` 仅 `config.ini` + `URL_config.ini` 两份）。后果是凭据经 `make_zip` 进入公开发行包。
- **修复建议**: 闸门改为遍历 `RELEASE_DIR/config` 下**全部**文件（或 `*.ini`/`*.txt`/`*.json`）跑同一 `_looks_like_secret_value` + 源值比对；复制侧「其余文件」分支改白名单，命中 `*config*`/`*cookie*`/`*.bak` 形态即 `SystemExit`。回归锁：在 tmp 的 `PROJECT_ROOT/config/` 放一份含真实 token 的 `config.ini.bak`，跑 `_prepare_config_dir()` + `assert_no_credentials_in_release()` 必须 `SystemExit(1)`（现 `tests/test_build_exe.py:1182` 把该断言整体 monkeypatch 掉，须新增独立用例而非依赖它）。

### 5.9 独立发行版孪生（3 项）

**MR-40 终止链的「写 q」一级实为 no-op：`text=True` 下 `write(b"q")` 抛 TypeError 被吞（M-16 假回灌）**
- **位置**: `scripts/douyin_live_recorder_standalone.py:1896-1915`（我读到 `:1899 proc.stdin.write(b"q")` 与 `:1901-1904 except Exception: pass`）↔ `:1986-1993`（我读到 `text=True,`）
- **描述**: 副本 Popen 用 `text=True`，`proc.stdin` 因此是 `TextIOWrapper`，写字节必抛 `TypeError: write() argument must be str, not bytes`，恰又被本意是「ffmpeg 卡死时不得阻塞清理」的宽 except 完全吞掉 → q 一个字节都发不出去，随后立即 `terminate()`。主线是二进制 stdin（`main.py:1121` 未开 text 模式）、一级后有 `proc.wait(budget/3)`、并有 `_QUIT_VIA_STDIN = os.name == "nt"` 平台门控（`src/ffmpeg_proc.py:56`、`:141-146`），副本三者皆无。
- **影响**: M-16 声称的回灌不成立——Windows 下每次 Ctrl+C/停止仍是 TerminateProcess 硬杀，mp4 缺 moov、产物不可播，**逐次发生**；而 `:1884-1888` 注释已把它登记为「已回灌」，后续审查与协作者会被这条陈述误导（比「没修」更糟）。
- **修复建议**: 去掉 `run_ffmpeg` Popen 的 `text=True`（`stdout=DEVNULL`、`stderr=logf`，去掉后行为不变），或把写入改 `proc.stdin.write("q")`；补 `_QUIT_VIA_STDIN` 门控 + 一级后有界 wait，两侧注释互相点名 `src/ffmpeg_proc.py`。孪生锁（`tests/test_regression_standalone.py` 新建 `TestTerminateChain`）：用 `_FakePopen(stdin=io.TextIOWrapper(...))` 断言写进 stdin 的确实是 `b"q"`/`"q"`，并把 `run_ffmpeg` 的 Popen 关键字集合钉成不含 `text=True`（按 AGENTS 在 Linux CI 上用 monkeypatch 强制走 Windows 支路）。

**MR-41 HLS 分片探测缺「节流 / 401-403 重试 / 按播放列表 URL 记退避」三项（M-17 修法有缺口）**
- **位置**: `scripts/douyin_live_recorder_standalone.py:1498-1513`（对照同文件 `:1585` 有 `_throttle_probe`、`:1546-1548` 有复核重试）；主线 `src/stream_select.py:590-593`、`:626-634`
- **描述/影响**: 主线分片请求前有 `_throttle_probe(seg_url)`、外层 `for attempt in range(2)` 且 401/403 时 `sleep(_recheck_delay())` 重试一次、命中 401/403 还 `_mark_probe_reject(playlist_url, platform)`（MIN-02：键必须是播放列表 URL）。副本单次 Range-GET 拿到 4xx/5xx 就 `return False` 定罪，也不写退避表，末态结论只打 debug。后果：虎牙 hw 系 HLS 的分片 host 与列表 host 不同（主线注释 hw3a…→f19c…livehwc4），多房间并发时副本对边缘 host 造成毫秒级连击（AGENTS「探针节流/抖动不得移除」正防此）；偶发单次 403 即把可用 HLS 候选判死，斗鱼 HLS-first 下回退到 ~70s 被掐的 FLV；分片持续被拒不记退避 → 下一轮照样全额重探、继续烧虎牙连接预算。
- **修复建议**: `:1498-1513` 改 `for attempt in range(2)`，逐 attempt 前 `_throttle_probe(seg_url)`、401/403 时 `_mark_probe_reject(播放列表 URL, platform)` 并 `time.sleep(_recheck_delay())` 后重试，其余码直接定罪；末态告警由 debug 升 warn。孪生锁两条：①「分片首探 403、二探 206 → 候选必须判可达（证明重试存在）」；②「403 定罪后 `SA._probe_reject_until` 里出现的是**播放列表 URL** 的 `strip_query` 键」。

**MR-42 本轮五条回灌（M-16/M-18/L-45/L-46/L-47）在 `tests/` 下零回归锁，上轮建议的「回灌清单机检」未落地**
- **位置**: `scripts/douyin_live_recorder_standalone.py:128-140`、`1658-1663`、`1879-1926`、`2019-2033`、`2081-2085` ↔ `tests/test_regression_standalone.py:301-517`
- **描述/影响**: 孪生锁文件本轮补了 SR-02（`TestRedirectHopGuard`）与 M-17（`TestHlsSegmentProbeLite`）两条行为锁，但其余五条一个都没有——`grep` 全 `tests/` 对 `terminate_all_ffmpeg`、`_rotate_log_if_needed`、`_h265_copy_format_supported_standalone`、`SA.parse_config_bool`、`SA.load_settings` 均 0 命中（`_TRUE_TOKENS` 只被 `tests/test_config_bool.py:21` 锁主线那份，副本无人比对）。**MR-40 那个「写了 `b"q"` 但一个字节都发不出去」的假修复正是从这里逃逸的**：CI 全绿、注释声称已回灌，缺陷逐次发生在用户机上；同类漂移以后仍会静默重演。
- **修复建议**: 在 `tests/test_regression_standalone.py` 增加 ①判据集合等价锁（`SA._TRUE_TOKENS == src.config_bool.TRUE_TOKENS` 等，可照抄 `tests/test_ffmpeg_install.py:895` 的「开关解析未走统一入口即红」形态）；②上轮第 364 行建议的「主线防线编号 → standalone 对应符号存在性」AST 结构清单（缺符号即红）；③MR-40/41 与第 6.3 节各条对应的行为锁。

### 5.10 CI / 容器 / 门禁工具（5 项）

**MR-43 `.dockerignore` 的审查/文档排除集已因文档搬家整体失效：2.38 MB 内部记录（含维护者本机路径）进对外镜像**
- **位置**: `.dockerignore:46-59`（裸模式 `CODE_REVIEW_*.md`/`DIAGNOSIS_*.md`/`PERF_REVIEW_*.md`/`PROPOSAL_*.md`；同段唯一带目录的模式是 `docs/changelog/`）、`Dockerfile:114` 的 `COPY . ./`
- **描述**（**我实测**）: dockerignore 的模式按官方语义**上下文根锚定**（裸 `CODE_REVIEW_*.md` 只匹配根目录，不像 gitignore 可跨层），而我实测根目录已无这些文件（`ls CODE_REVIEW_*.md` → No such file），它们已全部搬到 `docs/worklog/`、`docs/agent-reference/`、`docs/qgraphflow/`（`git ls-files docs` = 32 份，其中同类审查/提案 19 份）。`find docs -type f -not -path 'docs/changelog/*'` → 28 个文件 / 2,382,965 B；`docs/agent-reference/session-learnings.md:25,34-38,46,52-53` 含维护者本机家目录（`C:\Users\<用户名>`）形态的绝对路径。同族漏项：已跟踪的 `.zcodeignore` 在两份 ignore 里都无对应规则（`grep -n zcode .dockerignore .gitignore` 零命中）。
- **影响**: 每次 `docker build`/`docker-publish`/Trivy 构建；公开镜像含维护者本机目录、会话记忆、审查记录与提案（AGENTS 红线只保证「无真实凭据」，不含这些内容），体积 +2.4 MB，并使 AGENTS「镜像额外排除集」条目变成自证失效的摆设。**本报告自身落在 `docs/worklog/`，同样会被打进镜像**——这是把本项列进 P0 的直接原因。
- **修复建议**: 运行期无任何 `docs/` 消费点（全仓仅 `src/spider.py:113` 的注释引用），`.dockerignore` 直接加 `docs/`（或逐条 `docs/worklog/`、`docs/agent-reference/`、`docs/qgraphflow/`）；四条通配改 `**/CODE_REVIEW_*.md` 等锚定形态以覆盖未来再搬家；同批补 `.zcodeignore` 规则；并同步 AGENTS 该条目与 `tests/test_build_exe.py:1365-1372` 的清单（该锁只钉 `build_exe.py`/`StopRecording.vbs`/`*.jsonl` 三项，需新增 `docs/` 断言 + 一条「模式含 `*` 且目标实际位于子目录则必须写成 `**/` 形态」的行为锁）。

**MR-44 路径过滤漏登记 5 个「会改变门禁结论」的文件；`ci-summary` 又把 skipped 一律视为通过**
- **位置**: `.github/workflows/ci.yml:178-208`（`python` 过滤组）、`:919-921`（`contains(needs.*.result, 'failure')`）、`:91-92`（dispatch 声明）、`:880`（vbs 的 dispatch 逃生门）
- **描述与影响**（**我远端实测**）: 两半同源——①`python` 组收了 21 项却漏 `.gitignore`、`.dockerignore`、`AGENTS.md`、`.pre-commit-config.yaml`、`config/config.ini`，而这五个恰是多条回归锁的输入（`tests/test_build_exe.py:1356-1385` 读两份 ignore、`tests/test_agent_hook_guard.py:50` 读 `.gitignore`、`tests/test_pre_commit_config.py:55-62` 用 `run_gates.extract_gate_commands(AGENTS.md)` 与 pre-commit 双向钉、`tests/test_regression_gates.py:479` 读 `config/config.ini`），单改这些文件时 `static`/`test` 整体 skip、锁一次都不执行；②`ci-summary` 只把 `failure`/`cancelled` 判红，我经公开 API 看到一次 docs-only push（`1a44079`「docs: 更新 README…」，2026-10-03T02:25:09Z）的 `CI` 结论为 **success**——该次改动不命中过滤、8 个门禁 job 全部 skipped，required check 因此绿。另 `ci.yml:91` 把 `workflow_dispatch` 的用途写成「不改代码复跑全部门禁」，但 v4 的 `paths-filter` 对 dispatch 落到 `getChangedFilesFromGit`、base/head 均归一成默认分支 → 只比对最后一次提交，门禁跑不跑取决于最后一次提交碰没碰到 python 路径（同文件 `:880` 已为 vbs 补逃生门、其余 7 个 job 未补，可作反证）。
- **修复建议**: ①`python` 组补这五条路径（与 AGENTS「路径过滤已把 `uv.lock`/`egg-info` 纳入 python 组」同一口径，属既有先例补登记，不新建并行清单）；②照 `:880` 形态给其余 7 个重活 job 补 `github.event_name == 'workflow_dispatch' ||`；③给 `ci-summary` 加一条「全部门禁 job 皆 skipped 即 `::error::`」防线（与 MID-2264 同口径）；④`dorny/paths-filter@v4` 是「是否执行门禁」的单点且为浮动第三方 ref，按 MIN-17 应钉 SHA——**落笔前须由维护者当场核实该 SHA，不得凭记忆填**。

**MR-45 `agent_hook_guard.py` 用 `"find"` **子串**旁路整条删除判定；同族门禁假绿两处**
- **位置**: `scripts/agent_hook_guard.py:259-263`（我读码确认）；同族 `scripts/check_skill_agents_consistency.py:240-262`、`scripts/report_bundle_size.py:199-225`
- **描述与影响**: ①`if "find" in statement.lower() and not _FIND_DELETE_RE.search(statement): continue` 写在删除动词判定**之后**，因此任何语句只要文本里出现 `find` 这四个字母（目录名 `findings`、路径 `search_find/`、注释）就跳过该条语句的**全部**删除规则（R-CLEAN-SCOPE / R-WIPE-SCOPE）；工作包探针实测 `rm -rf logs` 拦、`rm -rf logs findings` 与 `Remove-Item -Recurse -Force logs, findings` **放行**，同批 `rm -rf .`/`git clean -fdx` 仍拦（差异只由该支路造成）。AGENTS 把「清理范围越界」的唯一自动化拦截点放在这一站，命中即不可逆删除被放行且无提示；既有锁 `tests/test_agent_hook_guard.py::test_cleanup_reaching_protected_dirs_is_blocked` 只用 `rm -rf ./logs` 形态，看不见它。②`check_skill_agents_consistency.py` 的「目录有、表格未登记」方向只进 `warnings` 且 `return 0`，还被「SKILL.md 正文含『约束事实源』+『AGENTS.md』」这一关键词条件二次过滤（不含即完全忽略），`child_fm`/`total_issues` 算完不用 → AGENTS 要求的「逐行相等」单向失守，恰在最需要报警的方向 rc 仍 0（违反本仓「告警即失败」推广口径）。③`report_bundle_size.py` 只有「目录不存在」退 2，目录存在但为空时 `file_count=0`、`leaks=[]` → 打「未发现（✅）」并 `return 0`，**`--strict` 也只查 `leaks` 非空**，且 `grep` 证实该脚本零回归锁 → 体积与工具链泄漏双门禁可空转报绿（`check_coverage.py:349-362` 的「files 为空即 rc=2」是同一仓库内的正面样板）。
- **修复建议**: ①find 旁路只对「本条语句的删除动词就是 `find`」生效（把子串换成 `_DELETE_VERB_RE` 已有的词边界形态 `\bfind\b`，或按动词逐个判定），`_FIND_DELETE_RE` 不动；②该方向改判 `errors`，判定形态照 `tests/test_ci_frontend_registration.py` 的「双向差集 + 空遍历面 fail-closed」重写；③加 `file_count == 0 → rc=2` 的 fail-closed 前置，`DEFAULT_RELEASE` 改 `ROOT / "dist" / "DouyinLiveRecorder"` 与其它脚本的 ROOT 锚定口径一致。回归锁各一条（①参数化补两格并保留 AGENTS 两条收尾清理命令的放行断言；②tmp 面「多一个未登记目录」断言 rc==1；③空目录断言 `main()==2`）。

**MR-46 `basedpyright` 本地门禁的退出码与判定面不一致：0 error/0 warning 却 rc=3**
- **位置**: `pyproject.toml:348-353`（`venvPath = "."`、`venv = ".venv"`）↔ 本机实跑
- **描述**（**我实测**）: 全仓跑输出 `0 errors, 0 warnings, 0 notes`，但首行为 `venv .venv subdirectory not found in venv path <workspace>`、进程 **rc=3**。对照实验：工作区外含 1 error + 1 note 的探针文件 → rc=1，故 3 与该 venv 配置缺失绑定、而非类型判定失败。`.venv` 被 `.gitignore` 忽略、本机依赖实际装在外部 managed venv（`sys.prefix` 不在工作区内）。
- **影响**: AGENTS 把 basedpyright 列为本地补充门禁（要求 0 error/0 warning）、DoD 第 1 条要「basedpyright 本地核一次」——在非维护机/干净 worktree 上该命令永远非零，读数不可复现；且其第三方 import 的解析面是否完整未被自证（`ignore_missing_imports` 之外，本配置段的 venv 指向失效意味着类型解析回退路径未经确认）。属「门禁依赖本机资产」家族，与 SR-06 同源判据。
- **修复建议**: 在 AGENTS 的 basedpyright 专节写明「无工作区 `.venv` 时预期 rc=3，判定准以 `0 errors, 0 warnings` 文本为准」，或让门禁入口在检测不到 `.venv` 时打印显式 SKIP 提示（与 MR-45① 同手法）；不在配置里写死机器专属绝对路径（该取舍有注释理由，维持不变）。

**MR-47 `run_gates.run_command` 对不可复制的 stdio 句柄零防御，整个门禁运行器崩在栈上而非给出「本项无结论」**
- **位置**: `scripts/run_gates.py:268-278`（`Popen` 无 `try/except OSError`），与 `:261-263` 的既有防御注释同族
- **描述**（**我实测**，见第 7.2 节三组对照）: 该函数已为 stdin 显式接 `DEVNULL` 并注明理由（「管道/IDE harness 下父进程 stdin 可能已关闭，子进程碰它即抛 `OSError WinError 6`」），但 `stdout` 仍是**继承**（`:246-251` 注释自述这是刻意设计，代价是 stdout 盲区）；当宿主（pytest 的 fd 级捕获、无控制台冻结进程、IDE harness）提供的 stdout 句柄不可 `DuplicateHandle` 时，`subprocess` 在 `_make_inheritable` 阶段即抛 `OSError: [WinError 6] 句柄无效`，`main()` 无捕获 → 运行器崩在栈上，**其余 9 条门禁一条都不出结论**。
- **影响**: 全量 pytest 本轮 21 条失败即同一根因（测试侧同源形态，见 7.2 定性）；门禁运行器本身在 CI 之外的宿主上会把「工具故障」伪装成「代码不合格」（或反之直接崩掉，无结论），与 AGENTS「Hook 坏掉不能演变成 agent 什么都做不了」同族的 fail-open 理念相悖。
- **修复建议**: `:268` 的 `Popen` 外层捕 `OSError`，打印「本项未取得结论（stdio 句柄不可复制）+ 建议改用普通终端复跑」并返回 `rc=2` 语义（与 `check_coverage` 无数据即 rc=2、`check_runtime_pins` 结构缺失 rc=2 同档），**不得**退成 0。回归锁：`tests/test_run_gates.py` 注入使 `Popen` 抛 `OSError` 的替身，断言 `run_command` 返回非 0、stderr 点名「未取得结论」且**不向上抛**。

## 6. 轻微问题（39 项）

> 表格每行即「逐文件记录」的一条：位置给出可直接跳转的 `file:line`；同一行内并列的多个位置属**同一失效机制**，不另立编号。「待确认」行附可执行验证方法。

### 6.1 `main.py`（7 项）

| 编号 | 位置 | 类型 | 描述与修复建议 |
| --- | --- | --- | --- |
| LR-01 | main.py:4708-4713（对照已修的 1201-1205） | 资源泄漏 | L-02 只修一半：直下分支字幕线程 `start()` 仍未包 try，`create_var[subs_thread_name]` 的键含 `%y%m%d_%H%M%S`、每轮不同 → 线程数打满时失败一次就永久多挂一条 dict 条目 + Thread 对象（Web/GUI 常驻模式最敏感）。改成与 1201-1205 逐字同构的 `try/except RuntimeError: create_var.pop(...); raise`；回归锁打桩 `threading.Thread.start` 抛错后断言无 `subs_` 前缀残留 |
| LR-02 | main.py:1620、5252、5728、5889、5165 | 可观测性 | L-03 只修一半：4 处异常日志仍是 `err=err`/`e=e` 单值形态——`:5252` 与 `:5032` 用同一 msgid 却是两种实参（后者 `err=f"{type(e).__name__}: {e}"`），`:5889` 是主循环最外层兜底（最常被走到），`:5165` 是裸 `print("An unexpected error occurred:", err)`。Windows 下 `socket.timeout`/`TimeoutError` 的 `str()` 为空 → 打出无语义行。按 `:5032` 先例把类型并入实参（不新增四语词条）；回归锁一条 AST 扫描「`except ... as X` 后首个 `logger.*` 调用必含 `type(...).__name__`」 |
| LR-03 | main.py:1512、1531、1836、2395、2460、2502、2551、2618、2769、2791、3263、4568（另 5195、5535） | i18n | 12 处用户可见 logger 串未经 `i18n.tr()`：loguru sink 不经 `builtins.print` 包装（`i18n.py:363-382` 只翻译 print 路径），故裸字面量在非简中语言原样输出。其中 `:4568` 与 9 条「错误信息: 网络异常…」**译文已在目录里**（我复核 `zh_CN.po:985-986` 有 `FLV is not supported for h265 codec…` 的 msgstr）→ 属「译文已备、查表没调」。一律包 `i18n.tr("原串")`（无占位符、模板保持字面量、不新增 msgid）；改后跑 `PYTHONUTF8=1 python scripts/compile_po.py --check` + `tests/test_i18n_migration.py`，改前 `grep -rn "use TS format instead" tests/` 核对按原文匹配的用例并同步为 `tr()` 后形态 |
| LR-04 | main.py:5104-5124（调用点 `:5115`） | 并发 | config.ini 的两个写入方分属两把锁：房间线程 cookie/token 回写走 `utils.update_config` → `main.file_update_lock`（M-11 已修），而 `_sync_ssl_disable_platforms` 经 `web_config.update_config_line` 持 `web_config._config_write_lock`（`web_config.py:1150/1164`）。两者都是「整文件读 → 改 → `os.replace`」，锁域不同即互不互斥 → 用户改「禁用SSL证书验证的平台」那一轮与某房间 cookie 刷新交错时互相覆盖（下一轮可自愈，持久损害有限）。把 `:5115` 包进 `with file_update_lock:`（顺序统一 `file_update_lock` → `_config_write_lock`，二者皆 RLock、无反向嵌套即无 ABBA）；长期让 config.ini 只剩一把写锁。回归锁断言两侧取到同一把锁对象 |
| LR-05 | main.py:1120-1122（配合 `web.py:117`、`:129-130`） | 脱敏 | `stderr=subprocess.STDOUT` 使 ffmpeg 自身报错直接写父进程 stdout，不经任何掩码环节；本文件对**等价路径**（print/logger 里的 `real_url`/`source_url`）一律要求先过 `mask_credentials`（MID-28/M-02），子进程输出是漏网面。`-loglevel error` 下 ffmpeg 仍会打印输入文件名，`wsSecret`/`txSecret`/`signature` 形态凭据可落 `logs/web_console.log`（运行期不轮转、仅停止时归档）。改 `stdout=DEVNULL`（保持 MID-N01 不引入 PIPE 背压的口径），失败分支打印已脱敏的 `-i` 实参（`:1578` 已取到 `_stream_url`）。**待确认**：验证法——Web 后台模式录一条必然失败的 http 地址后 `grep -a "wsSecret" logs/web_console.log` |
| LR-06 | main.py:552-555（对照 `:571`、`:4980`） | 异常处理 | 信号处理器注册早于 `color_obj`、`i18n` 等模块级名字绑定 → 导入期按 Ctrl+C 时 handler 内 NameError（无清理损失，仅堆栈噪音、且会盖掉真实导入错误的归因）。把 handler 内依赖改为惰性取用，或把注册点后移到绑定之后 |
| LR-07 | main.py:5361 | 输入校验 | `danmaku_split_time` 未夹下界，允许 0/负值 → `SrtWriter` 退化为单文件模式，与 `{seg:03d}` 分段命名（`_000.srt ↔ _000.ts`）的对应关系断裂。按 MID-2206 同款口径加 `> 0` 下界并告警回默认 |

### 6.2 平台解析与 HTTP 基建（6 项）

| 编号 | 位置 | 类型 | 描述与修复建议 |
| --- | --- | --- | --- |
| LR-08 | src/spider.py:1247-1316、5141-5230、224-253、197-201 | 死代码/契约漂移 | 三条死代码链：`get_kuaishou_stream_data2`（`_ensure_kuaishou_did` 的唯一消费点）与 `get_huajiao_sn` 只有 tests 引用、`invalidate_kuaishou_did_cache`/`invalidate_twitch_client_id_cache` 除定义外零调用（B站那条有真实调用点 `platforms/bilibili.py:235`）。后果：`:197-201` 注释声称「提供 invalidate_* 钩子供凭据被拒时主动失效」对快手/Twitch 不成立，只能等 `_CREDENTIAL_TTL` 自然过期、期间每轮复用被拒值；M-8/M-04/MID-33 三轮加固落在运行期不可达的链路上，任何「该缓存已生效」的表述都失真（同 `sync_http` 的口径禁令）。由维护者选 (a) 删除并同步 `tests/test_spider_platform.py` 与 `test_spider_hardening.py::OVERSEAS_MIGRATED_FUNCTIONS`，或 (b) 在函数头注明「生产无调用点、仅测试锚定」并改正 `:197-201`。回归锁：AST 扫「三个 `invalidate_*` 要么都有生产调用点、要么清单里写明零接线」 |
| LR-09 | src/spider.py:7274-7276、4190-4195、4651-4654、4840-4843 | 正则 | 四处都以「键名 + `=`」裸串搜索，未像同文件 `:1576` `[?&]rid=([^&;#]*)` 那样锚定参数边界；`:7274` 的 lookahead 还只收 `&|$`、缺 `#`。实测 `?shareRoomId=AAA&roomId=BBB` 会命中 `shareRoomId=` 里的 `roomId=` 并捕获 `AAA`；`?mycastId=`/`?xroom_id=` 同形；`?roomId=123#frag` 把片段当房间号 → 录错房或该房永久解析失败、用户只看到「房间不存在」这类误导（上轮 L-11 同族，当时只修了 room.py）。四处统一 `r"[?&](?:roomId|anchorId)=([^&#]*)"` 形态；回归锁对各平台加「前缀同名键 + 串尾参数 + 带 fragment」三形态参数化用例 |
| LR-10 | src/spider.py:4660-4665、6932、6955、6973-6974、6711 | 输入校验 | 抠自用户 URL 或重定向落地页的 id 以字符串拼接进 `body`/`data` 的 **JSON 字面量**，值中含 `"` 或 `}` 即改变结构（同文件 Shopee 侧 `:6504` 已按「urlencode/quote 后再拼」收口）。恶意分享链接可在百度/京东/淘宝三处请求体里注入或覆盖字段，多数表现为签名校验失败 → 静默未开播，最坏取到与目标房间不同的地址。四处改 `json.dumps({...})` 构造内层 body、外层仍走 `urlencode`；回归锁以 `room_id='a","x":1}'` 形态断言 `json.loads` 后内层键集合不变、值逐字等于输入 |
| LR-11 | src/spider.py:2551、2695-2696、2782-2784 | 输入校验/契约漂移 | `link_info["user_id"]` 在 live 形态取的是 `parse_qs` **解码后**的 `host_id`（不是 `_XHS_PROFILE_PATH_RE` 的 `[A-Za-z0-9_-]+` 捕获组），随后原样插入 profile URL 并带 Cookie 请求。实测 `parse_qs("host_id=%2e%2e%2f%2e%2e%2f%40evil.com%2fx")` → `'../../@evil.com/x'`，即 `%2e%2e` 会还原成 `..` 进 `user_id`——违反 AGENTS 小红书硬约束②（点段与 `%2e%2e` 不进规范 URL）。`normalized_url` 侧经 `urlencode` 是安全的，profile 侧没有。修：`:2782` 前加 `re.fullmatch(r"[A-Za-z0-9_-]{1,64}", user_id or "")` 门禁（与 `:2482` 同源、不新写第二份判据）或 `quote(safe='')`；回归锁断言 `?host_id=../../x` 形态下第二次 `async_req` 的路径仍是 `/user/profile/` 且不含 `..` |
| LR-12 | src/spider.py:2026-2028、2049、5692 | 异常处理/输入校验 | 深层索引仍以 `itemgetter`/裸下标取键（B站 `current_qn`、AcFun `bitrate`、`stream_data["base_url"]`），与 MID-48「取不到字段不得静默变空、须留线索」口径不一致：单条 codec/representation 缺键即 KeyError、`base_url` 显式为 null 时 `cast(str, …)` 不做运行时转换 → `host + None` TypeError；三者都被 `@trace_error_decorator` 吞成「未开播」，且发生在已成功取到流地址之后、把整路录制作废。key 改 `_dig` 容错或先判缺键归因后按无源返回（与同函数 `:2016/:2020/:2024` 的 `if not …: return None` 同形）；注入「缺 `current_qn`」「`base_url` 为 null」两种响应断言返回 None 且有 warning。**待确认**：现网是否下发缺键条目需真机核对 |
| LR-13 | src/room.py:85-91、176-184（另 `:206`、`:233-235` 复用同一客户端） | SSRF/契约漂移 | 两处裸建 `httpx.AsyncClient(..., follow_redirects=True)`（经 `async with`，不经 `async_http._build_client`），既无逐跳复检钩子、入口也不调 `is_safe_http_url`/`internal_stream_target_reason` → 正是 AGENTS「重定向逐跳复检只有两个合法接线点，新增第三处自建客户端即视为漏防」所指的漏防面。2026-09-30 审查 M-09 报的「三处」已随 L-13 删 `get_live_room_id` 收敛为**两处**，问题本体未修（本条只提供新行号与收敛后的计数）。改走 `async_http._build_client(...)` + `finally: _release_client`（该工厂是「每支客户端都带钩子」结构锁的唯一来源），或最低成本在入口判一次 `redirect_hop_rejection_reason` 并在注释写明残余；回归锁 AST 结构锁「`src/room.py` 内 `httpx.AsyncClient(` 命中数为 0」+ MockTransport「302 到 `169.254.169.254` 时取不到该跳响应」 |

### 6.3 弹幕链路与平台适配层（6 项）

| 编号 | 位置 | 类型 | 描述与修复建议 |
| --- | --- | --- | --- |
| LR-14 | src/ws_client.py:80-91（对照 `:102-113`） | 输入校验/可观测性 | `decompress_limited` 用 `zlib.decompressobj(wbits=31)` 解一次后不查 `needs_input`/`unconsumed_tail`/`unused_data`：截断的 gzip 流返回「已解出的部分」且不报错、多成员（concat 两个 gzip）只取第一成员；brotli 侧却显式 `if not obj.is_finished(): raise`。后果：帧被链路截断或上游改用分卷 gzip 时，调用方（`platforms/douyin.py:233`）拿到半个 protobuf payload，`ParseFromString` 可能解析出前几条、余下整段静默丢失 → 「弹幕少一截且零日志」。**待确认**：现网是否存在分卷/截断形态（用 `gzip.compress(x)*2` 喂本函数看 `unused_data` 是否非空）。修：补 `not obj.eof → raise ValueError`，与 brotli 同口径 |
| LR-15 | src/ws_client.py:459-462 | 异常处理/可观测性 | `_on_heartbeat()` **同步回调**抛错时 `except Exception: pass` 无任何留痕（同函数协程分支的超时、发送失败、`ws.close()` 失败各有 warning/debug，只这一条没有）；心跳协程「构造包阶段」抛错（`json.dumps` 遇非法字段、编码函数异常、`self._ws` 属性缺失）正落此处、永久静默。注释声称「下一轮心跳或 ping 超时会暴露故障」在异常恒定复发（同一构造路径）时不成立 → 表现为服务端因缺心跳在 N 分钟后踢下线、只能靠重连日志反推。修：按 `_poison_count` 同款节流补一条 debug，并复用目录既有「{where} 异常(忽略)」模板族（`collector.py:245-251` 同款 msgid），避免新增文案触发 `test_runtime_templates_covered_by_catalog` 硬门禁 |
| LR-16 | src/srt_writer.py:216-218（对照 `:178`、`_close_locked :220-231`） | 异常处理/内存界 | 写/flush 失败**不置 `_fp = None`**（`:216-218` 无 try 包裹，置 None 只发生在 `_close_locked`），于是 `:178` 的「句柄缺失才按 `_OPEN_RETRY_INTERVAL` 重试」永不触发 → WD-03 声称的「本片剩余时间自愈」只覆盖打开失败；失败文本滞留 TextIOWrapper/BufferedWriter 缓冲（flush 失败时 CPython 保留未写出字节并随后续写入扩容），既不经 `_srt_queue` 的 10000 条上界计数、也永不落盘。边车侧对同一形态是明确「关闭并弹出句柄、下一条重开」（`danmaku_monitor.py:84-96`）。修：写/flush 包 `except OSError: self._close_locked(); self._last_open_error = type(e).__name__; raise`，把后续交给已有节流重试（无需新机制）。**定级说明**：若判定磁盘满常态发生可升中等，本轮按触发条件稀缺留轻微 |
| LR-17 | src/collector.py:204 | i18n | L-24 只做了一半：`_rollback_start(room_registered=True, close_reason="采集线程启动失败")` 的实参仍是裸简中（同批 `:263` 与 `danmaku_monitor.py:362-366` 均已过 `tr`）。我实测 `采集线程启动失败` 在 `en_US.json`/`en_GB.json`（各 1033 键）里**只作为长模板的子串存在、无独立 msgid**，故 `tr()` 也无从命中；该串也不在提取器可见面（实参是变量名而非 `tr()` 调用），属关键约定 #14 的又一形态。修：`:204` 改 `close_reason=i18n.tr("采集线程启动失败")`，四目录同批登记并重编 `.mo`（走数据面 reason，不需动 `web/app.js`）；回归锁：目录覆盖不变量 + 「`_rollback_start` 传出的 reason 等于 `tr()` 后形态」行为锁 |
| LR-18 | src/collector.py:27-42；src/danmaku_monitor.py:40-47 | 契约与注释漂移 | 「内存有界」的字节量级按**字符**估算：M-09 的修法是 `[:_DANMAKU_TEXT_LIMIT]`（2000 字符）截断，注释据此推「单条 ≈ UTF-8 中文 6 KB、队列最坏 ≈ 数十 MB」。CPython PEP 393 下含 astral 平面（emoji）的 str 按 UCS-4 存储 = 4 字节/字符，两字段 ≈16 KB/条、10000 条 ≈160 MB；边车队列 20000 条同口径 ≈ 数百 MB（`json.dumps` 还临时生成一份等量 str）。结论（有界）成立、量级低报 3~8 倍，按「数十 MB」设的容量/告警阈值会低估一个数量级。修：改按字节口径截断（`encode("utf-8","ignore")[:N].decode(...)`、常量改名并注明按字节）或只把两处数字改正并写明口径；回归锁 `sum(len(s.encode()) for s in item) <= 上限` |
| LR-19 | platforms/_tars.py:77-124、169-183；platforms/twitch.py:35、113-119；platforms/huya.py:144-176；platforms/bilibili.py:34-39；platforms/douyin.py:228-252 | 输入校验/凭据 | 同一「外部可控字节未过完整校验」机制的五处：①`_skip` 的 STRING1 直接 `self._data[self._pos]`（截断帧抛 `IndexError` 而非模块契约声明的 `ValueError`，实测 `TarsInputStream(b"\x06").read_int(0)`）、`read_int` 的 INT1/2/4/8 走 `self._pos += k` 未经 `_advance`、LIST/MAP 负 `n` 放行后 `range(负)` 空转使游标停错位置（虎牙可产出乱码昵称/内容而非整帧丢弃，脏数据仍会过 `_sanitize_srt_text`、不破坏 SRT 结构）；②Twitch 跨帧 `_line_buf` 无长度上限、`start()` 不清零（残留半行拼进新连接首条）；③huya `_decode_chat` 不做空昵称/空内容过滤（异常 uri 下可产出 `: ` 空字幕块，抖音/B站侧有守卫）；④B站弹幕 WS 凭据白名单含 `bilivideo.com`/`bilivideo.cn`/`hdslb.com`（视频/图片 CDN，从不作为 `getDanmuInfo` 的 WS host 出现，真实形态是 `*.chat.bilibili.com`），而连接携带用户登录 Cookie → 可达面宽一个数量级且 `:32-33` 注释「覆盖实际会出现的域」不实；⑤抖音 `decode_message` 忽略 `PushFrame.payloadEncoding`（proto 有该字段、全仓零消费）无条件走 gzip，帧级解码失败只 debug，且各平台 decode 内层吞异常使 `ws_client` 的「毒消息」warning 聚合**永不触发**。修：`_need(1)/_need(4)` 后再取长度 + 负 size 抛错 + `_advance` 收口；`_line_buf` 加 `_MAX_LINE_BYTES`（4096 级）并在 `start()` 复位；huya 加同款空字段过滤；白名单删三项、改正注释（`tests/test_regression_spider.py:291-301` 未钉这三个 CDN 后缀，收紧不撞锁）；按 `payloadEncoding` 分流 + 连续 N 帧失败升 warning 一次。**待确认**：`getDanmuInfo` 的 host_list 是否曾出现 `chat.bilibili.com` 之外的子树、线上是否恒为 gzip，各需真机一次比对 |

### 6.4 Web 面板后端与前端（6 项）

| 编号 | 位置 | 类型 | 描述与修复建议 |
| --- | --- | --- | --- |
| LR-20 | src/web_api.py:1108-1117、1185-1188、1247-1250 | 死代码/契约漂移 | 两处 `current_cfg is None` 兜底恒不可达（`:1109` 外层条件已无条件赋值，None 分支进入条件是其真子集）；更麻烦的是 `:1249` 的兜底基准用 `_read_web_config_cached`，与 `:1110-1116` 写下的「口令/认证守卫**不得**用该缓存」直接对立 → 后来者按「这里会兜底」把 `:1109` 元组收窄时，MID-2241 复验会静默改用缓存判定，正中文档写明的失效形态。修：`:1249` 改 `read_web_config(...)`，并给两处 None 分支加一次性判定或注明确定性来源；回归锁「认证开启、缓存说 auth=false 而磁盘说 true 时写 `web_auth_enable=false` 必须 403/要求 reauth」 |
| LR-21 | src/recorder_status.py:113-118 | 可观测性 | 守护线程内层再抛异常即整线程静默终止：`display_info` 的 except 分支里调用 `_get_get_error_line(e)`/`logger.error` 自身不再受保护（概率极低，故未单列中等）；`log_archive.py` 归档失败仅告警的路径与之同族。修：把收尾动作各自包一层 `except Exception` 并落带 `type_name` 的 debug；回归锁：注入使 `logger.error` 抛错的替身，断言线程仍存活一轮以上 |
| LR-22 | web/app.js:181-194（消费点 `:229`、`:749`、`:1008`；映射缺口见 `:900`、`:1154`） | 契约漂移 | 后端稳定机器码 detail 恒优先于调用方传入的本地化文案：`apiError` 取 `detail || fallback`，而 `web_api.py:312-317`、`:600` 刻意把 `status_unavailable`/`room_delete_failed`/`room_update_failed`/`logs_unavailable`/`host_not_allowed`/`rate_limited`/`unauthorized`/`insecure_bind_disabled`/`cross-origin request denied` 定义为**不经 tr 的机器码**（`tests/test_web_api.py:1458` 钉着「机器码不得被翻译」）。全文件只映射了 `status_unavailable`/`danmaku_unavailable` 两个 → 被主机白名单挡住、被 per-IP 预算限流、跨源调用、写盘失败这四种情形下四语界面显示裸英文 snake_case，用户既不知发生什么也无处着手，「按稳定机器码分支」这条既有契约名存实亡。修：`apiError` 前加 `MACHINE_CODE_KEYS` 映射表（命中换 `t(...)`、未命中的本地化文案照旧透传），四套内嵌目录同批补键（面板点分键不进后端四目录）；回归锁 `.mjs` 以 403 + `detail: 'host_not_allowed'` 断言 `login-error` 文本为当前语言译文且不含下划线码 |
| LR-23 | web/app.js:1656-1666（按钮绑定 `:1968`；口令窗禁用见 `:1623`、`:1648`；对照 `toggleRecording:1003`） | 竞态 | `saveConfig` 无重入保护：每步 `await api()` 都让出执行权，第二次点击并起第二条串行提交链，两条链共用同一份 `configBackup` 与同一批 DOM 节点，且 `querySelectorAll` 返回**静态** NodeList（第二条链持第一轮节点引用）→ 同一键 PUT 两次、「已保存 N 项」计数翻倍、第一轮已成功写入的行被标成 `.row-failed` 红行（恰好制造 MIN-2239 想消除的「界面与磁盘对不上账」的相反形态）。修：入口 `if (saveRunning) return; saveRunning = true;` + `finally` 恢复，或与 `toggleRecording` 统一为「入口即 disabled、出口恢复」；回归锁连续两次 `clickSave` 后断言 `putBodies(ctx).length === 1`（`test_auth_reauth.mjs` 已有 `config-save-btn.disabled` 断言形态可复用） |
| LR-24 | web/app.js:2003、2011、2017、2024（`t()` 定义见 `:581`，全文件 60+ 处调用） | 可观测性 | 四个事件委托回调首行 `var t = e.target` **遮蔽**了模块级 i18n 函数 `t()`。当前四个函数体内恰好都没调 `t()`，一旦新增任何文案（例如给删除按钮加确认提示）就运行时抛 `t is not a function`，且异常发生在委托回调里、被浏览器吞成一条控制台错误、界面无反馈、整条委托静默失效（开关/删除/下载按钮点了没反应）。属防御纵深缺口。修：四处统一改名 `target`（与 `:1963` 的 `var btn = ...` 风格一致）；回归锁：静态断言 `/(function|=>)[\s\S]{0,120}var t = e\.target/` 命中数必须为 0，并反向锁「委托回调内出现 `t(` 调用即红」 |
| LR-25 | web/motion.js:65-76、`:127`；index.html（仓库根）:14-16 | 性能/契约漂移 | 两类「既有口径未对齐」：①`resize` 直接绑在 window 上，函数体每次都改 `canvas.width/height`（该赋值即丢弃并重分配整块 backing store）并 `spawnParticles(...)` 重建最多 64 个粒子——AGENTS 对 GUI 侧同类形态（`<Configure>` 同步写 wraplength 致 Tk idle 队列永不排空）已定「真防抖 + 迟滞」唯一正确形态，web 侧这条属同一失效家族（拖窗口、跨 DPI 显示器拖动、滚动条出现/消失都会连发几十次）；②根 `index.html` 同页 hls.js/flv.js 已按「钉版本 ≠ 钉内容，必须补 SRI」写下 `integrity` 并由 `tests/frontend/test_regression_gates.mjs:927-953` 逐个 script 标签机检，但 `fonts.googleapis.com/css2?...` 那条外链未钉版、未 SRI、无版本号，且 CSS 不在该锁枚举范围内（样式可被外链 CSS 注入任意选择器覆盖页面文字；离线时字体请求持续失败但 `font-family` 有 Arial 兜底、功能不受损）。修：①`onResize` 150ms 防抖 + `destroy()` 清 timer（`removeEventListener` 第三参须与 add 一致）；②推荐直接删这三行外链（本页样式全内联），或改指带版本号的固定产物 + `integrity`，并把那条锁的枚举面从 `<script src>` 扩到 `<link href^="http">`。信息级两处：`prefersReduced()` 只在 `init` 采样一次（运行中改系统设置不会停掉已在跑的 canvas，CSS 侧媒体查询会跟、canvas 侧不跟）；`flvPlayer.play()` 未接 rejection（自动播放被拒时控制台一条 Uncaught，界面无影响） |

### 6.5 GUI / UI 控件层 / i18n（4 项）

| 编号 | 位置 | 类型 | 描述与修复建议 |
| --- | --- | --- | --- |
| LR-26 | gui.py:2863-2864（回传 `:2812`/`:2818`/`:2861`，落点 `:4086`） | i18n | `_tray_status_str` 返回裸 `"启用"`/`"未启动"` 未经 `tr()`，属关键约定 #14「按名/非 tr 调用位」提取盲区。**我实测目录里其实已有译文**（`en_US.json`/`en_GB.json`：`启用 → Enabled`、`未启动 → Not started`；`zh_TW.yaml` 有对应条目）→ 一行修复、**无需补词条**（工作包原标注「需 grep 确认」，我已确认存在）。改 `return i18n_module.tr("启用") if ... else i18n_module.tr("未启动")`；回归锁：钉 en_US 断言 `_tray_status_str()` 返回英文 + `tests/test_i18n_migration.py` 目录覆盖不变量 |
| LR-27 | gui.py:4070-4089（兜底 `:4088-4089`） | 异常处理/可观测性 | `_update_status_bar` 整个方法体（含 `_get_dynamic_status_info` 与 6 处 `configure`）包在一个 try 里、`except Exception: pass` 零日志——与同文件 `_schedule_status_refresh` 走 `_warn_chain` 限频留痕的机制脱钩（异常没逃出内层 pass，外层根本看不到）。后果是状态灯/间隔/时间停摆且无任何线索。修：缩小为 `except tk.TclError: return`（销毁竞态静默）+ `except Exception as e: self._warn_chain(i18n_module.tr("状态栏刷新"), e)`；回归锁：注入使 `info_*` configure 抛非 TclError 异常，断言队列里出现一条留痕 |
| LR-28 | src/ui_kit.py:120-136（缓存键 `:71-72`；调用面 `gui.py:1883-1885`、`ui_kit.Button:117`） | 契约漂移/资源 | `font_style` 派生样式名 `DLRF<n>.<base>` 的缓存键只有 (base 样式名, 字体键)，而 `style.configure(name, font=...)` 的 `-font` 写进的是**调用当时激活的 ttk 主题**选项库（tkinter `theme_settings` 文档串即「临时切到该主题再落 settings」），本仓 `_build_ttk_settings()` 不含任何 font 键 → `ThemeManager.apply()` 切到另一个 `dlr-*` 主题后该样式名在新主题库里没有任何条目、缓存又永不失效、configure 再也不会补上字体。后果：任一主题切换（含侧栏选「跟随系统」触发 `detect_system_appearance()`）后整个 GUI 的按钮文字退回系统默认字号（13/15px 档位与 bold 全丢），切回原主题才恢复，无异常无日志。修：缓存键加主题维度 `(theme_id, base, font_key)`（`theme_id` 取 `ttk.Style(widget).theme_use()`），或 `apply()` 成功后清空 `_FONT_STYLE_CACHE` 由调用方重设 style；更彻底是把 font 一并登记进 `_build_ttk_settings()` 的变体样式、彻底不走派生名。**待确认**（本包禁起 Tk）：`apply('dlr-dark') → font_style(...) → apply('dlr-light')` 后 `style.configure(n)` 是否仍含 `font`——CI 已具备 xvfb，可直接写真窗用例 |
| LR-29 | i18n.py:145-152；i18n/ 四目录；config/config.ini:159-161 | 契约与注释漂移/目录卫生 | 三处「注释读数与实测不符」合并（**我实测**）：①`has_catalog` 的成本论证仍写「各约 680 条」，而四目录动态键各 **1033**、`.mo` 头 N = 1034（与 `compile_po.py --check` 自报一致、符合「N == 键数+1」口径）→ 读数 +52% 过期，而它是该节唯一成本判据；②目录相对代码「只增不减」：AST 全仓（非 tests）679 个字面 `tr()/T()` msgid **全部命中目录**（正向无缺口，gui 的 66 处 `T()` 也已登记，`web/app.js` 内嵌四套各 127 键彼此一致），但反向 354 键无字面调用点、其中 36 对是同前缀的陈旧模板（`{e}`→`{type_name}: {e}` 一类改文案留下的旧键），且 `[build] 压缩包已生成：{zip_path}（{zip_path_2} MB）` 全仓零 `zip_path_2` 实参（违反「`*_2` 只在代码真传 `xxx_2=` 才合法」；`grep` 我实跑为空）；③`config/config.ini:159-161` 的 `gui_theme = light` 与 `ui_theme.py:221-223` 及该节行注释声明的「留空跟随系统」矛盾（`ui_theme.py` 内的口径冲突需维护者裁决）。修：①读数改述为「各约 1000 条」并附取数命令；②`extract_i18n_strings.py` 增反向对账（目录键 − 代码字面 msgid − f-string 派生模板 = 孤儿清单，先输出待删清单、非空即报数），删或改 `zip_path_2` 条目；③模板/README 与代码注释统一到一处（若「新装默认浅色」是有意决策，就改正 `ui_theme` 的理由句并删行注释里的「留空跟随系统」误导） |

### 6.6 构建 / 签名脚本 / VBS（3 项）

| 编号 | 位置 | 类型 | 描述与修复建议 |
| --- | --- | --- | --- |
| LR-30 | StopRecording.vbs:1（文件字节 0-3）；tests/test_stop_recording_vbs.py:41-48 | 编码约定/回归锁失明 | 双 BOM：我实测首 8 字节为 `ff fe ff fe 27 00 2a 00`，而上一版 `870dee4` 是 `ff fe 27 00 2a 00`（单 BOM）→ 10-03 批次整文件重写时以 `utf-16-le` 解码（不剥 BOM）再以 `utf-16` 编码写回所致，脚本正文首字符是 U+FEFF 而非注释符 `'`。**我用 cscript 实测**：临时目录里单/双 BOM 两份最小脚本均 rc=0 且正常输出 → 运行期不失效，工作包「严重（触发即整脚本失效）」自评被我下调。真问题是违反 AGENTS「必须 UTF-16 LE 带 BOM」且编码锁对这一形态完全失明：`_vbs_text()` 只断 `raw[:2] == b"\xff\xfe"` + `decode("utf-16-le").startswith("\ufeff")` + `return text[1:]`，单/双 BOM 两种文件都满足；行为用例又只在抽出的函数体上跑、永不触第 1 行（`_drive()` 自己写 scratch 用的 `b"\xff\xfe" + script.encode("utf-16-le")` 恰是正确的单 BOM 形态）。修：重写为单 BOM；锁改 `raw.decode("utf-16")`（BOM 消费式）后断 `not text.startswith("\ufeff")` 且 `text.startswith("'")`，并加 `assert raw[:4] != b"\xff\xfe\xff\xfe"`；行为锁补一格用 `cscript //nologo` 跑「真文件前 3 行 + `WScript.Echo`」断言 rc==0 |
| LR-31 | src/ffmpeg_master_download.py:114-127 ↔ 136-144 | 逻辑错误/死代码 | `_probe` 发 `Range: bytes=0-0`，`_looks_like_html` 却 `next(response.iter_content(512), b"")` 后按 `first.lstrip()[:64].lower()` 的两个 `startswith` 判定：服务端遵守 Range（206、1 字节）时首块最多 1 字节、两个 `startswith` 恒 False，注释自称「比只看 Content-Type 更稳」在该形态下名不副实。漏判后果仅是把「octet-stream 标注 + Range 支持」的挑战页放行到 `_stream_download`，随后 `is_valid_zip`（`:405`）仍能拒装 → 不构成安全缺口，但注释所声称的第二道探测从不生效（真实可达的只有 fyhub 那种 200 + 整页 HTML）。修：探针改 `Range: bytes=0-511`，或 `len(first) < 16 and status_code == 206` 时回落到 Content-Type 判定并在注释写明退化；回归锁桩「206 + 首字节 `b"<"`」断言现实现判 False、改后判 True（锁住「嗅探真吃到多字节」） |
| LR-32 | src/node_install.py:200-219（对照 `:67`、`:75-79`、`:157-163`）；AGENTS.md 行号锚点 | 注入/路径/文档漂移 | 从 nodejs.cn 页面抠出的版本号未过形状关即同时拼进出站 URL（`:216`）与本地文件名（`:219`）：`:200` 的 `re.search(".../node/(v.*?)/node-(v.*?)-x64.msi", ...)` group 用 `.*?` 未限字符集，`_normalize_node_version` 只做 strip 与补 `v`；`full_file_name = url.rsplit("/", maxsplit=1)[-1]` 挡掉了 `/`，但 Windows 上 pathlib 认 `\`，含反斜杠的抓取结果可让写盘位置落到 `execute_dir` 之外，而官方清单查不到该文件名时只降级 TOFU 继续（`:157-163`）、并不拒绝。同文件对「摘要」已有 `_SHA256_RE` 严格形状关（`:67`），对「版本」没有。修：`_normalize_node_version` 内加 `^v\d+\.\d+\.\d+$` 形状关（不符返回 `""`，调用点 `:201-203` 已有「取不到即 False」出口）+ `full_file_name` 追加一次 `Path(...).name` 归一并断言仍等于原值；回归锁 `_normalize_node_version(r"v1.2\..\..\evil") == ""` 与「该页面形态下 `install_nodejs_windows` 返 False 且不调 `requests.get` 下载」。**待确认**：pathlib 对反斜杠的实际行为需本机一次 `python -c` 观察。信息级：AGENTS 把 `install_ffmpeg_linux_native` 的实参位钉为 `src/ffmpeg_install.py:583`，当前实参在 `:594`（行号漂移、判据不变），宜把 AGENTS 措辞改为「函数体内调用直下入口的那一处」以免每轮追行号 |

### 6.7 `scripts/` 与 CI 工程一致性（3 项）

| 编号 | 位置 | 类型 | 描述与修复建议 |
| --- | --- | --- | --- |
| LR-33 | scripts/compile_po.py:132-139、`:61-65` | 编码/假绿 | `reconfigure(encoding="utf-8")` 未显式给 `errors=`，违 AGENTS「MID-63 ③ 任何 `reconfigure` 显式给 `errors`」（同仓 `run_gates.ensure_utf8_streams`、`agent_hook_guard.ensure_utf8_streams`、`check_skill_agents_consistency.ensure_utf8_streams` 三处均写 `errors="replace"`，本文件是唯一例外），且门内条件只看 `sys.stdout.encoding`（stdout 已 UTF-8 而 stderr 仍 cp936 时 stderr 得不到修正，`:136-137` 在同一 if 内）。另 `:61-65` 重复 msgid 只 print WARNING、条目照旧被覆盖、rc 不受影响，而 `--check` 用**同一份**解析器重算再逐字节比对 → 自洽通过，`.mo` 与译者意图已不同；`msgid_plural`/`msgstr[` 在本解析器里不被识别、续行还会错并入 msgid（现 `zh_CN.po` 实测 0 处，属「新增条目即失守」）。修：两处补 `errors="replace"` + 逐流判断；重复 msgid 升 rc=2（与同文件缺头部退 2 同档）或至少计入 `--check` 失败；解析器遇 `msgid_plural`/`msgstr[` 前缀行明确报错。回归锁：`tests/test_i18n.py` 两格 + 一条源码级判据「本文件不再出现不带 `errors=` 的 `reconfigure(`」。**待确认**：需在中文 Windows + pytest 捕获态实跑取证 |
| LR-34 | scripts/smoke_test.py:82-91、`:231-235`、`:464` | 退出码/规范冲突 | `expected_status` 写成字符串或 `null` 时在 `run_check` 比较前抛 TypeError，而 main 的 try 只包 `load_config` → 工作包本机实跑读数 **rc=1**；消费侧 `_ci_web_smoke.sh:85-111` 原样透传、`ci.yml:670-682` 该 retry 调用点 `fail_fast_codes: "2"` + `attempts: "2"` → 配置写坏被读成「面板接口挂了」而白跑一整轮面板冷启动 + 退避（正是 AGENTS M-32② 要消灭的错判方向），且崩溃发生在 `print_console`/报告写出之前，`logs/web-smoke-report.json` 缺失、只剩上传步骤的 `if-no-files-found: warn`，排障线索反而更少。**规范冲突须先裁决**：`:82-88` 注释明写「`timeout`/`expected_status` 这类标量刻意不做强制转换、不在这里偷改口径」，因此这是 AGENTS 的 rc=2 契约与脚本自身设计声明之间的**矛盾**，不是单纯疏漏。建议：加类型校验但**不做转换**（`expected_status` → `(int,)`、`timeout` → `(int, float)`、`method`/`url`/`path`/`name` → `(str,)`；显式 `null` 与缺键等价放行并回退默认），校验点仍唯一在 `load_config`、`main()` 的 except 元组不得缩窄；同时把注释与 AGENTS 统一到一处。回归锁：`tests/test_scripts_error_paths.py::TestSmokeConfigMalformed` 参数表补两格（字符串/null → `rc == 2` 且 stderr 点名「期望 JSON number」） |
| LR-35 | build-release.yml:243-253、`:180-186`、`:268-269`、`:373-386`；ci.yml:873-894、`:885-891`、`:159-160`、`:348-354`、`:638-648`、`:566-575`、`:741-754`；.pre-commit-config.yaml:12-13、`:31-33`、`:41-43` | 权限/一致性/供应链 | 同一「CI 统一策略未彻底落实」族的六处（逐处一行）：①`build` 与 `release-create` job 无条件 `contents: write`，而「仅构建不发布」路径只用 `upload-artifact`——同一 job 内要执行 `build_exe.py --smoke --dual`，即下载并**运行**约 300 MB 第三方 ffmpeg/node，且 `actions/checkout@v7` 未设 `persist-credentials: false`（token 落进 `.git/config`、每个 run 步骤进程都看得到 `GITHUB_TOKEN`）；正面样板是 `docker-publish.yml:84-86/141-143/184-186`。→ job 级降 read、三处上传步骤（`:232-240`、`:420-432`、`:539-550`）用 step 级 `permissions: contents: write`。②`vbs-behavior-test` 是全文件唯一不走统一口径的重活 job：硬编码 `python-version: '3.14'`（绕过 consts 单点）、`pip install pytest` 不钉版本、无 `PYTHONUTF8=1`、安装不套 `./.github/actions/retry`；我远端看到的那次 CI failure 含该 job 红（**待确认**红因需一次 job 日志定性，其依赖面只需 stdlib+pytest+cscript）。→ 四项按统一策略改齐。③pre-commit 的 black/isort 钉 `25.9.0`/`6.1.0`、`default_language_version: python: python3`，CI consts 是 `26.5.1`/`9.0.1` → 两套格式化裁决器（AGENTS「本地可外推的前提是版本逐一同值」不成立），叠加 3.13 无法解析 PEP 758 无括号形态，低代工具对全库语法安全性不可断言；`tests/test_pre_commit_config.py` 只钉 entry/id、不钉 `rev`。→ 抬 rev 到同值 + 钉 `python3.14` + 加比对锁；`ci.yml:888`/`build-release.yml:104` 的字面量解释器版本改取 consts 输出。④`pip-audit` 未钉版本（同 job 已为四个工具钉死，理由正是「防代码未改动却 CI 变红」），而它是唯一**阻断型**安全门禁、其 OSV 判定行为与退出码语义随版本变化 → consts 增 `pip_audit_version`（须当场核实、不得凭记忆填）。⑤`codecov/codecov-action@v7` 是浮动第三方主版本、运行期取到 `secrets.CODECOV_TOKEN`，fork PR 被 `available` 挡住但**同仓库分支 PR 与 push 会真实执行** → 按 MIN-17 钉 SHA，或定位为可选能力（未配置 token 就直接删该步并把结论写进 AGENTS）。⑥两处「告警即失败」兜底步骤以 `python -m pytest -q 2>/dev/null \|\| true` **二次全量**跑：rc 与 stderr 全丢、收集期崩溃也判绿（判定面为空）、第二次不在 `xvfb-run` 下故真窗用例整体 skip（与第一次覆盖面不同）、时间翻倍而 `test` job 上限 25 分钟 → 改为第一次 `tee pytest-out.txt`（`set -o pipefail` 保留 rc）、兜底只 grep 该文件，`concurrency-test` 同批改 |

### 6.8 `tests/`（4 项）

| 编号 | 位置 | 类型 | 描述与修复建议 |
| --- | --- | --- | --- |
| LR-36 | tests/test_ui_i18n.py:63-77（断言 `:75`、`:76`；被测清理点在 src/ui_i18n.py:94、观测面 `:64-68`）；tests/test_agent_hook_guard.py:218-229（`:229`）；tests/test_xhs_live_links.py:644-651 ↔ :748-751 | 假绿 | 三条「声明有锁、实际无区分力」（我逐条读码确认）：①`assert ui_i18n.retranslate_all() >= 0` 恒真，而同文件 `:66` 的注释自己就写着「断言计数恰好回落 1 而不是 `>= 0`：后者对『不清理』也成立，等于没锁」——而 `registered_count()`（`src/ui_i18n.py:64-68`）按存活过滤，把真正的清理语句 `_ENTRIES[:] = alive`（`:94`）删掉后本文件 5 条用例仍全绿，头注声明的「死亡引用清理」变异敏感点是假证据；②`assert b"--no-cache-dir" not in proc.stderr` 里那个 token 在喂入的命令 `pip install --force-reinstall -r requirements.txt` 中**根本不存在**（`--no-cache-dir` 只出现在 `:86` 的另一条参数化命令里）→ 无论 Hook 是否回显命令原文都恒真，而生产侧 `scripts/agent_hook_guard.py:454` 确实是 `print(f"[{rule}] {reason}", ...)`，一旦有人把 command 拼进 reason 就抓不到（该文件 `:97` 注释自己也说过「拦截规则一旦过宽，代理会绕过 Hook 而不是修规则」）；③端到端接线用例把 `select_source_url` 桩成恒回 `http://live-source-play.xhscdn.com/live/abc.flv`，末行断言命令里含同一主机名，而 deeplink 的 `flvUrl` 本身也是该主机（`:353`）→ 两侧同字面、断的是替身自证。修：①加 autouse fixture 快照/还原 `_ENTRIES`，改断「连续 register→del→retranslate 两轮后内部列表不再增长」（或新增 `pending_entry_count()` 观测未剪枝条目），`:75` 换成「死条目不计入 applied」实断言；②按实际输入喂一条含伪凭据的命令并断言 `SECRET*` 与 `requirements.txt` 都不在 stderr；③改记录型替身（捕获实参 + 回一个替身专属主机），同时钉「谁被调用」与「用谁的返回值」 |
| LR-37 | tests/test_xhs_live_links.py:517-530；tests/test_test_hygiene.py:65、:188 | 环境污染/平台可达 | 本仓凡在 fixture 内 `import main` 的文件一律 `scope="module"`（`test_b23_tv_dispatch.py:28`、`test_hy_fan_dispatch.py:26`、`test_platform_dispatch.py:22`、`test_record_container.py:27`、`test_main_fixes.py:28` 五处一致），目的是让 `main` 导入期的 stdio 策略改写发生在 conftest 守卫取基线**之前**；本文件新建时漏了 scope → 工作包实测 `python -m pytest tests/test_xhs_live_links.py -q -s -p no:cacheprovider` 得 **75 passed, 1 error**（ERROR 源自 `tests/conftest.py:127` `_guard_stdio_encoding_policy` 报 `sys.stdout: ('utf-8','surrogateescape') -> ('utf-8','replace')`），即该文件**不能**按取证口径单文件独立运行（整包绿只因另有模块级 `import main` 在收集期先跑；`tests/` 内另有 5 处 `builtins` 级替身属同一族、R1 结构上看不见——`setattr(builtins, "open"/"__import__", ...)` 的首参是 `ast.Name` 且 `builtins` 不在名单内，已用 `_module_body_mutation_calls` 实跑证明返回 `[]`）。修：改 `@pytest.fixture(scope="module")`；`tests/test_test_hygiene.py` 把 `builtins` 加入 `_MUTABLE_MODULE_NAMES` 并把对象形态判据放宽到「`ast.Name` 命中名单」，另加一条「fixture 体内 `import main` 者必须 module scope」的机检；把 5 处 `builtins` 替身逐处改窄为被测模块命名空间替身 |
| LR-38 | src/utils.py:910、:950；main.py:4452 | 回归锁缺失 | 三处生产注释给出的「回归锁/复核判据」用例名在 `tests/` 中不存在（**我实测**：`grep -rn "def test_camelcase_compound_keys_value_disappears" tests/` 为空，实际用例是 `tests/test_regression_utils.py:93 TestCamelCaseCredentialLeak::test_compound_keys_value_disappears`；`grep -rn "def test_record_ua_uses_single_source" tests/` 为空，真实锁在 `tests/test_regression_main.py:1135` 的 `assert main.MOBILE_UA == stream_select.MOBILE_UA`）。不变量本身另有锁，坏的是**指针**——按注释定位会得到「该修复无锁」的错误结论并重复补锁（关键约定 #12）。另注意措辞不统一：本仓「复核判据/静态锁」两种写法游离在 `grep "回归锁：tests/"` 的既有复核面之外。修：两处注释按真实 `文件::类::用例` 改正并统一前缀；把「`tests/…::符号` 是否能在目标文件解析出来」挂进 `scripts/check_annotations.py` 的常驻符号可达性检查 |
| LR-39 | tests/conftest.py:22-31、:133-147；tests/test_ui_kit.py:190-192、:220、:251、:280 | 环境污染/平台可达 | 两处「声明与实现不符」：①测试会话内 `import main` 把进程级 loguru 文件 sink 与 atexit 钩子带进 pytest，`pytest_unconfigure` 只 rmtree 输出目录、不摘 sink → 工作包实测 `tests/test_main_fixes.py` 得 `29 passed` 之后仍打两例 `Logging error in Loguru Handler #1 … ValueError: I/O operation on closed file`，同时真实 `logs/streamget.log`/`PlayURL.log` 被创建（与「测试产物一律走 `tmp_path`」相反，属会话级共享目录）。任何门禁都不看会话尾部 stderr（warnings summary 只 grep stdout、silent-skip 只 grep isort stderr），但它会把「导入 main 的用例」伪装成崩溃源。②`tests/test_ui_kit.py` 头注声明「真窗用例（无显示环境 skip）」，但本文件没有任何 skip 路径——三个 `TestRealWindowWidgets` 用例直接 `root = tk.Tk()`，无头主机上是硬 ERROR 而非 skip（对照 `tests/test_ui_theme.py:276-281` 与 `tests/test_gui_wrap_hints.py:160-163` 的既有正确形态）；CI 绿靠 `xvfb` + 一条 Tk 预检这一外部条件，不属用例自证。修：①在 `pytest_unconfigure`（或 autouse session fixture 末端）`logger.remove()` 并还原 stdio，或给 `src/logger.py` 增「测试宿主」判据跳过文件 sink；②复用 `test_ui_theme.py` 的 `tk_root` fixture（类级 `try/except tk.TclError → pytest.skip`），保留 ci.yml 预检作为「CI 上真的执行过」的第二道防线 |

### 6.9 工作包提出、但本轮未计入清单的候选（须逐行复测后再定级）

为保证「清单内每一条都有主审查者读码或执行取证」这一口径，以下 5 条由工作包给出、我未逐行复测的候选**不进入计数**，但记录在此以免随报告丢失——它们的定位与判据均已给出，复测成本很低：

| 候选 | 位置 | 判据摘要 | 复测方法 |
| --- | --- | --- | --- |
| standalone h265 在**解析层**按键名无条件剔除，架空 L-45 的选源层门控 | `scripts/douyin_live_recorder_standalone.py:936-940` ↔ `:1658-1663`、`:1684-1690` | 解析层按 `flv_pull_url` 的**字典键名**剔掉 `*H265*`，选源层却按 **URL 子串 `h265`** 判定 → mp4/ts 输出下门控无候选可放行，抖音 HEVC 原画房静默降到 h264 次优档；主线是「解析层保留、选源层按容器放行」（`src/stream.py:535-549`、`src/stream_select.py:318-321`） | 读码比对两层判据 + 造一条 `flv_urls=["http://x/FULL_H265.flv"]`、`record_format="ts"` 的替身用例看候选是否进探针 |
| standalone 斗鱼房间号正则未锚定 `[?&]`（主线 10-03 定稿的 `extract_douyu_rid_param` 未回灌） | `scripts/douyin_live_recorder_standalone.py:1192-1198` | `re.search(r"rid=(\d+)")` 无左界，`?from_share_rid=111` 会覆盖路径首段的正确房间号 → 录错房或判「房间不存在」；AGENTS 已把该洞写进主线定稿理由 | `python -c` 复算 `?parent_rid=111` 形态下 `rid` 取值 |
| standalone 协议白名单三处口径不一致（探针/选源拒 rtmp，ffmpeg 白名单与主线放行 rtmp/rtmps） | `scripts/douyin_live_recorder_standalone.py:467-468` ↔ `:1814-1815`、`:1963-1964`；主线 `src/stream_select.py:324-326` | 当前四个解析器不产 rtmp 候选故暂无触发；一旦回灌斗鱼 rtmp 拼接或支持自定义流地址，合法协议会被丢弃循环当攻击面处理 | 断言 `SA._untrusted_stream_target_reason("rtmp://…")` 与主线 `_is_recordable_url` 同结论 |
| `StopRecording.vbs` 的 python 主进程判定只认 `APP_DIR_KEY`、不认脚本所在目录（上轮 L-41 修法的新漏杀方向） | `StopRecording.vbs:317-339`（对照 `:354-358` 的 ffmpeg 分支用 `appDir`）、文件头 `:21-25` | 源码方式安装在改名目录（`D:\tools\live-rec\`）时 python 主进程不命中、ffmpeg 侧却命中 → 只杀孙进程、主进程下一轮重拉，正是文件头声称已消除的竞态；「已知残余」只记了误杀方向 | 以 `_drive()` 注入 `appDir` 与 `D:\tools\live-rec\main.py` 命令行形态跑一次判定 |
| `web_config._read_ini_pairs` 之外，`config_io._safe_int` 仍接受全角数字 | `src/config_io.py:304`（捕获集 `TypeError, ValueError` 接不到 `int('１２')`） | 工作包实测 11 条非法输入均已回默认，唯全角数字仍通过；与 AGENTS 小红书条「不得用 `\d+` 因会放行全角数字」同族 | `python -c` 复算 `_safe_int('１２', 7)` |

## 7. 工具侧客观证据

### 7.1 门禁与静态检查读数（2026-10-04，本机 worktree）

| 命令 | 结果 | 判读 |
| --- | --- | --- |
| `python scripts/run_gates.py` | **9 项 PASS / 1 项 FAIL**，耗时 40.4 s，rc=1 | 逐项：black `[PASS] 4.2s`、isort `[PASS] 1.2s`、`mypy` `[PASS] 11.1s`、`mypy --platform linux` `[PASS] 10.0s`、`mypy --platform win32` `[PASS] 9.6s`、`check_annotations.py` `[PASS] 3.7s`、`compile_po.py --check` `[PASS] 0.1s`、`check_version.py` `[PASS] 0.1s`、`check_runtime_pins.py` `[PASS] 0.2s`、`check_skill_agents_consistency.py` **`[FAIL] rc=2`** → 即 SR-06，且该项红导致 pytest 兜底未执行 |
| `basedpyright`（不传路径） | `0 errors, 0 warnings, 0 notes`，进程 **rc=3** | 与判定面无关的退出码，根因是 `venvPath/venv` 指向不存在的 `.venv`（MR-46） |
| `python -m pytest -q --cov=src -p no:cacheprovider` | **21 failed / 4074 passed / 14 skipped**，161.09 s，rc=1 | 全部为「派生子进程 + 继承 stdio」形态，非代码回归，判读见 7.2 |
| `python scripts/check_coverage.py` | **48 个模块全部达标**，1 项显式豁免（`src/proto/douyin_pb2.py` 8.7%，protoc 生成物），rc=0 | 最低读数：`src/platforms/douyin.py` 63.3%、`src/spider.py` 75.5→75.7%、`src/ws_client.py` 78.9%、`src/ui_kit.py` 77.9%（均高于各自阈值） |

### 7.2 21 条 pytest 失败的定性（三组对照实验，我本人执行）

失败清单集中在三个文件：`tests/test_build_exe.py::test_smoke_script_exit_codes_on_empty_config`（4 参数）、`tests/test_ci_retry_action.py::test_retry_script_behaviour_with_real_bash`（8 参数）、`tests/test_run_gates.py`（6）与 `tests/test_regression_gates.py`（2），**全部**是「用 `subprocess` 派生真实子进程（bash / `sys.executable`）并继承 stdio」的用例。

| # | 实验 | 读数 | 结论 |
| --- | --- | --- | --- |
| 1 | 裸 shell 里 `subprocess.Popen([...], stdin=DEVNULL, stderr=PIPE, shell=True)`，并直接 `DuplicateHandle` fd 1 | `fd1 handle 5332`、`dup ok 288`、`popen ok hi` | 脱离 pytest 时该操作**完全正常** → 缺陷不在生产/工具代码的调用形态 |
| 2 | 全量：`pytest -q --cov=src` | 21 failed，栈尾统一为 `subprocess.py:1431 _make_inheritable → OSError: [WinError 6] 句柄无效` | 失败发生在 pytest 的 fd 级捕获句柄不可被 `DuplicateHandle` |
| 3 | 单文件 + 关闭捕获：`pytest tests/test_run_gates.py::test_run_command_propagates_nonzero_rc -q -s` | **1 passed in 2.38 s** | `-s` 下同一用例即绿 |
| 4 | 单文件、默认捕获、无 cov：`pytest tests/test_run_gates.py -q` | **1 failed, 42 passed, 1 skipped** | 与全量的 6 条红不一致 → **非确定性**，取决于当时捕获句柄状态 |

**裁断**：本轮 21 条失败属「环境 × pytest 捕获交互」噪声，**不得**当作代码回归计入问题清单（AGENTS 只登记了 exit 139 段错误与 harness safe-delete 两类本机噪声，未登记这一形态，属文档缺口；已由本节与 MR-46/MR-47 承接）。它同时暴露一个真实防御缺口：`scripts/run_gates.py:268` 的 `run_command` 对不可复制的 stdio 句柄零保护——无 `try/except OSError`，在该形态下整个门禁运行器直接崩在栈上而非给出「本项无结论」，与其 `:261-263` 注释自述的「管道/IDE harness 下 stdin 可能已关闭 → WinError 6」是同一失效族（当时只处理了 stdin 一支，`stdout=None` 继承这支没管）。建议：`Popen` 外层捕 `OSError` 并落一条 rc=2 语义的「门禁未取得结论」而非 traceback → 已计为 **MR-47**，列入 P1。

## 8. 改进建议与修复优先级

### 8.1 P0（本批应立即修，改动面小、风险收益比最高）

1. **SR-01 + SR-02**（`stream_select.py`）：安全拒绝改走专用内部控制流异常、不受 `last_resort`/同址复用影响；派生跳判定覆盖**全部**正文行而非末行；三条行为锁（交付面断言，不是 `_probe_hls_segment` 返回值）。
2. **SR-05 + MR-07 + MR-08 + MR-40/41/42**（standalone）：一次回灌批次统一处理，并按 AGENTS 在提交说明登记「已核对 / 已回灌 / 刻意不回灌及原因」；同批落地「主线防线编号 → 符号存在性」机检，否则下一次假回灌仍会全绿逃逸。
3. **SR-04**（`main.py` xhs 回写）：`not_record_list` 登记条件与 `record_url` 同 base 对齐，或改精确配对移除；`tests/test_xhs_live_links.py` 加行为锁。
4. **SR-06**（门禁）：Skill 一致性脚本在 `.agents/` 缺失时改 SKIP → rc=0（照 `tests/test_agent_hook_guard.py:297` 先例），或按 `!DouyinLiveRecorder.egg-info/` 先例把 Skill 纳入跟踪（**须用户批准 ignore 同源约定变更**）；两条路都补一条「干净检出不误红」的回归锁。
5. **MR-43**（`.dockerignore`）：加 `docs/` 并把四条通配改成 `**/` 形态——**本报告自身正落在 `docs/worklog/` 下**，在修好之前每次镜像构建都会把审查记录与本文件打进对外产物。
6. **MR-01 ~ MR-06**（凭据）：`sig` 入 `_SECRET_KEYS`；Cookie 头整段遮蔽；`msg_push` 五处 `e=` 过码 + `_mask_url` 的 netloc；前端/后端掩码前缀双侧拒收；DELETE 改 body。
7. **MR-36 第一步**：新增 `.gitattributes` 的 `src/javascript/*.js -text` + 一条「实算哈希 == 表值」用例（先让漂移可见，再谈执行期校验）。

### 8.2 P1（中等项，按风险排序）

- **防线一致性优先**：MR-09（派生跳内网名单并回单一事实源）、MR-10（同公共后缀注册域剥 Cookie）、MR-11（`_validate_stream_url` 契约违背，远端可触发穿透）、MR-13（`_match_host` 域边界 + 自定义流表项前移）、MR-15（异步侧响应体上限）、MR-17（chunked 请求体封顶）。
- **功能正确性**：MR-12（SOOP 空 `view_url` 早退）、MR-14（`count_time` 重赋）、MR-25/26/27（枢纽幽灵房间、join 静默、停止路径误报）、MR-28/29（B站轮换与看门狗两处时序）、MR-30（GUI 启动期语言定型）、MR-31（`retranslate_all` 逐条隔离 + 四步 try 拆分）、MR-32（主题读取不得崩 GUI）。
- **完整性与自证**：MR-37（TOFU fail-closed 与 `UnicodeDecodeError` 并捕）、MR-38（digest 通过时也记账）、MR-39（凭据闸门遍历全部文件）、MR-45（`find` 子串旁路 + Skill 单向锁 + `report_bundle_size` 空转）、MR-21/MR-23（写盘失败被上报为成功、归档窗口内的 stdio 让位）、MR-25 与 LR-16（枢纽幽灵房间、`srt_writer` 自愈不闭合）、**MR-47**（`run_gates.run_command` 的 `OSError` 防御，见 7.2 末段）与 **MR-46**（basedpyright 退出码口径，见 7.1）。
- **需维护者裁决后才动**：MR-33（认证 + 通配绑定的 403 是修行为还是修文档）、MR-35（422/400 中文直出——涉及是否扩 `tr()` 覆盖面）、MR-32 关联的 `gui_theme` 默认值、LR-34 的 rc 契约冲突、SR-06 的第二方案（纳入跟踪）。

### 8.3 P2（轻微项与结构性建议）

- **结构性建议 1｜脱敏键集矩阵化**：`_SECRET_KEYS` 是开放集合，本轮 MR-02/MR-03/MR-04/MR-08 四条同源复现即是其代价。建议以「平台 Cookie 全键清单 × 形态（query / header / Cookie 头 / userinfo 代理串）」矩阵表驱动用例替代逐案补键，并把「反向核对：登记表键名」扩为「登记表 ⊇ 各平台实测 Cookie 键集」。
- **结构性建议 2｜交付面而非返回值**：SR-01 的教训是——**安全不变量的回归锁必须断在交付结果上**（谁被交给 `ffmpeg -i`/`httpx`），断在中间函数返回值上会给出假信心。建议对选源/直下/探针三条链路各补一条「候选是否进入执行器」的行为锁（LR-36③ 的替身自证是同一毛病的测试侧形态）。
- **结构性建议 3｜「干净检出可运行」自证**：SR-06、MR-43、MR-44、LR-35② 全部属「门禁/CI 依赖维护者本机条件」。建议增加一个 `ci-clean-check` job：在**新建的临时工作目录**里从 `git archive HEAD` 出一份纯净树，跑 `scripts/run_gates.py --list` 的全部 `--check` 命令并断言 rc=0（或按 SKIP 语义明确放行），把「资产缺失即 SKIP、不得伪红伪绿」变成机检。
- **结构性建议 4｜`_2`/孤儿条目/指针的反向对账**：LR-29、LR-38 均属「只增不减 + 指针失效」。把孤儿 msgid 与 `tests/…::符号` 可解析性一起纳入 `extract_i18n_strings.py` / `check_annotations.py` 的常驻检查，比逐轮人工回查更省。
- **工作区卫生**：`patch_i18n_2026_09_12.py`（硬编码 `D:/DouyinLiveRecorder-dev` 且全为写路径）建议由用户判定后退役；`.zcodeignore` 已跟踪但两份 ignore 清单无对应规则。

## 9. 总结性结论

本轮对约 **5.97 万行**生产与工程面代码（另含 6.17 万行测试代码与 6.8 千行 i18n 目录）完成了逐文件深审，覆盖五个上轮未纳入的子系统面（`scripts/` 工具链、CI 工作流与容器、`src/platforms/`、签名脚本层、`msg_push.py`），共产出 **93 项**发现（严重 7 / 中等 47 / 轻微 39，另有 5 条候选因未逐行复测未计入，见第 6.9 节；其中 15 项结论由主审查者本机执行取证、3 项由 GitHub 公开 API 取证）。

**整体评价**：该项目的防御密度与可追溯性显著高于同规模项目——历史修复普遍带可复核判据与回归锁编号，凭据哈希（PBKDF2 + 随机盐 + `compare_digest` + 迭代次数上下界钳制，我逐处读码确认）、原子写原语与快照回滚、发布链 fail-closed 钉定、镜像与 ignore 清单的多处同源、探针节流与熔断租约等核心防线经本轮核查**全部成立**；`run_gates` 与 mypy 三平台双跑全绿、覆盖率 48 模块全部达标。

**三类值得警惕的模式**，比单点缺陷更有决策价值：

1. **「修了但没闭合」**——本轮 7 项严重里有 3 项（SR-01/SR-02/SR-05 的孪生面）与上轮整改同源：分支返回值修对了，上层兜底语义与取样面没跟上；主线修对了，副本没回灌；注释还把未生效的修复登记成「已回灌」（MR-40 是最典型的一例——`b"q"` 一个字节都发不出去而 CI 全绿）。其共同成因是**锁断在中层返回值上、而不是断在交付结果上**，以及**回灌无清单机检**。
2. **「门禁自证缺口」**——SR-06（干净检出必红、已实测远端 CI failure）、SR-07（镜像链从未运行、已实测 `total_count = 0`）、MR-44（一次 docs-only push 在执行零门禁的情况下把 required check 判绿）、MR-45/LR-33/LR-34（`find` 子串旁路、`report_bundle_size` 空遍历面报绿、`smoke_test` rc 语义与 AGENTS 冲突）、LR-36（三条恒真/替身自证式断言）。门禁变红会被立刻看见，**门禁不执行与假绿不会**，后者对长期代码质量的侵蚀更大。
3. **「开放集合型防线」**——脱敏键黑名单与「哪些 URL 可带凭据」两处，每接入一个新平台/每改一次文案就会补一批条目，本轮四条同源复现即其结果；矩阵化用例（8.3 建议 1）与把判据收口到单一实现（`_host_in_family`、`http_config` 上限常量）是治本方向。

**修复推进建议**：按第 8 章顺序，P0 七组（选源两严重、standalone 回灌批次、小红书回写、Skill 门禁、`.dockerignore`、凭据五处、钉定可见性）改动面均小、应在本批落地并各带回归锁；P1 按「防线一致性 → 功能正确性 → 完整性自证」三组排布；需维护者裁决的五项（`gui_theme` 默认、认证 + 通配绑定的行为姿态、422 文案覆盖面、`expected_status` rc 契约、是否纳入跟踪 `.agents/`）已在 8.2 单列，未擅自改口径。**第 4、5 章所列位置即为后续验证的核对清单**；所有标注「待确认」的条目均附了可执行的验证方法，修复前应先完成验证。

## 附录 A. 工作包 → 条目映射与逐文件覆盖清单

> 用途：核对「某文件的发现是否全部收录」与追溯每条结论的来源包。ID 后带 `✔` 表示主审查者对**行号与判据**做过独立读码或执行取证，其余条目由工作包给出、我复核了行号回读要求但按成本仅抽查判据。

| 工作包 | 覆盖文件（行数） | 产出条目 |
| --- | --- | --- |
| pkg-main | `main.py`(5,904) | SR-03、SR-04 ✔、LR-01~LR-07（LR-01/02/03/04 部分 ✔） |
| pkg-spider | `src/spider.py`(7,340) | MR-01 ✔、MR-12、LR-08~LR-12、3.3 节 M-04 残余说明 |
| pkg-httpinfra | `async_http`(764)、`sync_http`(430)、`http_config`(63)、`proxy`(303)、`room`(261)、`ab_sign`(547) | MR-15、MR-16、MR-24、LR-13；另 `ab_sign`/`get_xbogus` 零 importer 却未如 `sync_http` 那样如实登记（工作包提出、未逐行复测 → 按 6.9 口径不计入） |
| pkg-streamselect | `stream_select`(1,411)、`stream`(1,317)、`scheduler`(540) | SR-01 ✔、SR-02 ✔、MR-09 ✔、MR-10、MR-11、MR-13 ✔、MR-14 ✔ |
| pkg-danmaku | `collector`(610)、`ws_client`(492)、`danmaku_monitor`(804)、`srt_writer`(253)、`ttwid`(243)、`cookie_cache`(408)、`base`(114)、`src/__init__.py`(104) | MR-19 ✔、MR-25 ✔、MR-26、MR-27 ✔（含实验）、LR-14~LR-18 ✔（LR-17/18 实测/读码） |
| pkg-platforms | `src/platforms/*`(1,659) | MR-28 ✔、MR-29 ✔、LR-19 ✔ |
| pkg-webapi | `web_api`(1,633)、`web_config`(1,319)、`web_models`(192)、`web_tray`(265)、`recorder_status`(247)、`web.py`(357)、`log_archive`(224) | MR-17 ✔、MR-18、MR-20 ✔、MR-21 ✔、MR-23、MR-33、MR-34、MR-35、LR-20、LR-21、SR-06 交叉印证 |
| pkg-frontend | `web/app.js`(2,089)、`web/index.html`(201)、`web/style.css`(600)、`web/motion.js`(223)、根 `index.html`(279)、`_ci_web_smoke.sh`(111)、`tests/frontend/*.mjs`(2,345) | MR-05 ✔、MR-06 ✔、LR-22~LR-25、`.mjs` 登记核对（无缺口）✔、XSS 面核对（干净）✔ |
| pkg-gui | `gui.py`(4,496) | MR-30 ✔、MR-31 ✔、LR-26 ✔、LR-27 ✔、3.3 节 M-14/L-38/L-39/L-40 复核 ✔ |
| pkg-ui18n | `ui_kit`(406)、`ui_theme`(611)、`ui_i18n`(95)、`i18n.py`(415)、四套目录 | MR-31 ✔、MR-32 ✔、LR-28、LR-29 ✔（键数/译文/`zip_path_2` 实测） |
| pkg-utils | `utils`(1,023)、`config_io`(446)、`config_bool`(54)、`notify`(346)、`logger`(305)、`video_postprocess`(506)、`msg_push`(577)、`startup_cleanup`(229) | MR-02 ✔、MR-03 ✔、MR-04、MR-22、LR-38 相关 ✔；M-01/M-11/M-12/M-13/L-32~L-36 复核 ✔ |
| pkg-build | `build_exe`(1,740)、`ffmpeg_install`(740)、`ffmpeg_linux_download`(476)、`ffmpeg_master_download`(479)、`ffmpeg_proc`(311)、`node_install`(422)、`StopRecording.vbs`(499) | MR-37 ✔、MR-38、MR-39 ✔、LR-30 ✔（cscript 实验）、LR-31、LR-32 |
| pkg-jsig | `migu.js`(393)、`haixiu.js`(535)、`liveme.js`(425)、`x-bogus.js`(564) | MR-36 ✔（哈希/键集实测对账）；另 6.9 节未计数项；`x-bogus.js` 零调用点死脚本仍占钉定槽（工作包提出、未逐行复测 → 按 6.9 口径不计入） |
| pkg-standalone | `scripts/douyin_live_recorder_standalone.py`(2,695) 与主线逐点对照 | SR-05 ✔、MR-07 ✔、MR-08、MR-40 ✔、MR-41、MR-42；6.9 节 3 条未计数候选 |
| pkg-ci | 5 个工作流(1,979)、`Dockerfile`(133)、`docker-compose.yaml`(147)、`.dockerignore`、`.gitignore`、`.pre-commit-config.yaml`、`pyproject.toml`(385)、`requirements.txt` | SR-06 ✔、SR-07 ✔（远端实测）、MR-43 ✔、MR-44、MR-46、LR-35；门禁步骤总表 |
| pkg-scripts | `scripts/` 其余 15 个工具(4,649) | SR-06 复现 ✔、MR-45 ✔（两处探针实测）、MR-47、LR-33、LR-34；门禁自证总表 |
| pkg-tests | `tests/`(140 py + 4 mjs) | LR-36 ✔、LR-37、LR-38 ✔、LR-39；R1~R8 机检盲区表 |

## 附录 B. 主审查者本机取证清单（命令 → 读数，全部 2026-10-04）

| # | 取证动作 | 读数（摘要） |
| --- | --- | --- |
| 1 | `python scripts/run_gates.py` | 9 PASS / 1 FAIL（第 10 项 rc=2），40.4 s，rc=1 |
| 2 | `basedpyright`（全仓，不传路径） | `0 errors, 0 warnings, 0 notes`，rc=3；首行 venv 缺失提示 |
| 3 | `basedpyright probe_bad.py`（工作区外，1 error + 1 note） | rc=1 → 证明 3 与类型判定无关 |
| 4 | `python -m pytest -q --cov=src -p no:cacheprovider` | 21 failed / 4074 passed / 14 skipped，161.09 s |
| 5 | `pytest <单文件> -q` 与 `-q -s` 与裸 `Popen` 三组对照 | 1 failed 42 passed / 1 passed / `dup ok`+`popen ok` → 环境噪声判定 |
| 6 | `python scripts/check_coverage.py` | 48 模块达标、1 豁免，rc=0 |
| 7 | `mask_credentials` query/Cookie 头/代理串实测 | `sig=ABC123SECRET` 与 `DedeUserID`/`buvid3`/`ntic` 明文；`SESSDATA`/`bili_jct`/`token` 已抹 |
| 8 | `_SECRET_KEYS` 成员判定 | `sig` False；`sign`/`signature`/`sessdata`/`bili_jct`/`sessionid_ss`/`sid_tt` True |
| 9 | `cscript //nologo` 单 BOM vs 双 BOM | 两者均 rc=0 且输出 `OK` → 双 BOM 不致命 |
| 10 | `python -c` 读 `StopRecording.vbs` 字节 + `git show 870dee4:` 对照 | 工作区 `ff fe ff fe 27 00…`，旧版 `ff fe 27 00…` |
| 11 | `hashlib.sha256` 逐文件 vs `_JS_SHA256_EXPECTED`，`git cat-file blob` 对照 | 4 MATCH / crypto-js.min.js MISMATCH（60,821 B vs 60,820 B）；无 `.gitattributes` |
| 12 | asyncio 停止时序复现（cancel → `sleep(0)` → `loop.stop()`） | 抛 `Event loop stopped before Future completed`；`task.done()=False`、`cancelled()=False` |
| 13 | `inspect.getsource(subprocess.Popen.__exit__)` | 非 KeyboardInterrupt 分支为无超时 `self.wait()` |
| 14 | `check_annotations._reject_dangerous_baseline` 探针 | 工作区子目录 → 「拒绝：位于用户主目录内」；`D:/tmp/base` → None |
| 15 | i18n 四目录键数 + `en_US.json` 词条 + `zip_path_2` grep | 各 1033 键、`.mo` 头 N=1034；`全部房间 → "All Rooms"`；`zip_path_2` 代码零命中 |
| 16 | `config_io._redact_ini_secrets`（隔离加载，真实 `URL_config.ini`） | 854 B/15 行 → 产物 **0 字节**；含未注释行 → 原样返回、明文 token 保留 |
| 17 | 公开 API `…/actions/workflows/docker-publish.yml/runs` 与 `…/actions/runs` | 前者 `total_count = 0`；后者含 CI run（2026-10-03T02:05:33Z **failure**、02:25:09Z docs-only **success**） |
| 18 | `git ls-files .agents` / `git ls-tree HEAD` / `git log --all -- .agents` / `gh` 可用性 | 三者皆空（从未跟踪）；`gh: No such file or directory`（故未取 job 日志） |

---

*审查方法与工具口径详见第 2.4 节；全部行号以 2026-10-04 工作区状态（`bf43acc`）为准。带「待确认」标记的条目不得在未验证前当作已证事实引用；第 6.9 节 5 条候选未计入总数，引用时须先复测。*
