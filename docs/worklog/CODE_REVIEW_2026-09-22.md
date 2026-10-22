# DouyinLiveRecorder 全量源代码审查报告（2026-09-22）

| 项目 | 内容 |
| --- | --- |
| 报告编号 | CODE_REVIEW_2026-09-22 |
| 被审对象 | `D:\DouyinLiveRecorder-dev`（DouyinLiveRecorder v4.3.0，工作树快照） |
| 审查日期 | 2026-09-22 |
| 审查方式 | 14 个互不重叠的模块分组并行深读 + 主会话逐条回源复核 + **基线 diff 增量审计** + 只读命令实测取证 |
| 覆盖语言 | Python（3.14）、JavaScript（浏览器端 / Node 签名脚本）、CSS、HTML、YAML（CI / compose）、Shell、VBScript、TOML、Dockerfile、INI、Gettext（po/mo） |
| 问题总数 | 严重 **28** 项、中等 **65** 项、轻微 **68** 项（合计 **161** 项）；其中若干行为同源合并条目，行内共含 2～6 个子项 |
| 编号约定 | 本轮编号 `SEV-22xx` / `MID-22xx` / `MIN-22xx`（`22` = 审查日期），与 `CODE_REVIEW_2026-09-20.md` 的 `SEV-xx`/`MID-xx`/`MIN-xx`、`CODE_REVIEW_2026-09-21.md` 的 `SEV-Nxx`/`MID-Nxx`/`MIN-Nxx`、以及代码内 `CR-xx`/`F-xx`/`H-xx`/`WD-xx`/`MI-xx`/`P-x`/`W-x`/`R-x`/`补-xx` 标注**互不复用**，便于 grep 区分轮次 |

---

## 一、审查概述与背景

### 1.1 背景

本项目在 2026-09-18、2026-09-20、2026-09-21 完成过三轮全量源码审查，累计结论 260 余项，其中第三轮（`SEV-N` 系列）的严重项已部分落地（详见附录 A 的逐项回归核查）。因此本轮的定位不是重复既有结论，而是承担四项任务：

1. **发现新缺陷**：覆盖上一轮之后新写入的代码、以及上一轮因分组边界未深读的接缝。
2. **识别「半修复」**：本仓由并行子代理按文件分工实施修复，历史上反复出现「只改一条分支 / 漏一个调用点 / 孪生副本未同步 / 注释声称的事实与代码不符」四类残留形态。本轮这仍是中等结论的主要来源。
3. **回归核查**：逐条复核上一轮 6 项严重结论的落地状态（附录 A）。结论是 **5 项在位、1 项（`SEV-N06`）至今未落地且在本轮发现新的同族实例**。
4. **审查「基线之后的增量」**：本工作目录在 2026-09-22 13:10:27 有一次真实提交（`51c2193 baseline: initial workspace snapshot`），而 13:10 之后又写入了约 1,739 行实质内容（`git diff --ignore-cr-at-eol` 口径，已剔除纯行尾噪声）。**这部分代码从未被任何一轮审查覆盖**，且集中在「运行期下载并执行外部二进制」这一危害半径最大的链路上。本轮把它作为独立取证线（见 1.3 第 4 步与第三章 `SEV-2201`/`SEV-2202`）。

一个必须先说明的总量事实：本轮 14 个分组与主会话增量审计**均在 `scripts/run_gates.py` 8 条门禁全绿、`pytest` 告警摘要为空的前提下**得出 19 项严重结论。换言之，本报告的多数内容不是「门禁没修」，而是「门禁看不见」——这与 `AGENTS.md` 反复登记的「绿但什么都没查」母题同族，第六章据此给出结构性建议。

### 1.2 审查目标

按用户要求，对全部自研源文件（不含第三方依赖与构建产物）做四维审查：

- **正确性**：逻辑错误、边界条件、控制流漏口、状态一致性、**跨模块类型契约**、跨副本语义一致性。
- **健壮性**：异常吞没、资源生命周期（进程 / 句柄 / 线程 / 连接 / 文件 / 信号量）、无界增长、超时预算缺失、降级路径。
- **安全性**：认证与授权、凭据外泄与脱敏、SSRF 与跨域 Cookie 边界、注入、路径遍历、供应链与发布链完整性、TLS 校验。
- **可验证性**：门禁与回归锁是否真能抓住回归、测试是否自实现被测逻辑、注释与文档陈述是否与代码一致。

### 1.3 审查方法

按 `AGENTS.md`「并行分组代码审查的分工口径（2026-09-19 沉淀）」执行，并针对本轮条件做两项加强：

1. **分组与所有权**：按调用链与文件所有权切成 14 组，组间文件**严格不重叠**（`main.py` 4,925 行与 `src/spider.py` 6,470 行各按行区间拆为 3 段；只读审查，无写冲突）。每组 prompt 完整注入本项目**刻意约定白名单**（`#` 行注释禁 docstring、PEP 758 无括号 `except`、行宽 120、探针退避白名单仅虎牙、虎牙 FLV-first 与斗鱼 HLS-first、跨循环不建 `aclose()` 协程、四类「钉定/校验」互不覆盖、`_loads_dict` 返回 `{}` 不抛、standalone 为刻意副本、四语目录 + 前端内嵌目录五处同步等），以免把刻意风格误报为问题。
2. **证据要求**：每条结论必须附 `文件:行号` + 逐字符原文片段（≤12 行）+ 影响推演 + 修复方向 + 置信度；凭据类内容一律脱敏或仅描述形态。
3. **回源复核（主会话逐条执行，非抽样）**：本轮对**全部 19 项严重结论**与约 70% 的中等结论逐条读回源码核对；其中 6 项做了**可执行的定量实测**（见 2.3），而不是仅静态判读。复核中筛除了子代理给出的 1 处排版占位片段（`danmaku_monitor.py:548-554`，主会话已回源取真文本后才纳入）与若干与既有定稿冲突的推断。
4. **基线 diff 增量审计**：主会话独立执行 `git diff --ignore-cr-at-eol 51c2193`，逐文件核对 13:10 之后新增的生产代码（`src/ffmpeg_master_download.py` 全新 402 行、`src/ffmpeg_install.py` 384 行改写、`build_exe.py` / `scripts/run_gates.py` / `scripts/check_runtime_pins.py` / `.github/workflows/ci.yml` 各自的新增段），并核对这些新增文件是否已被登记为可测试、可覆盖、可钉定的对象。分组子代理不知道该 diff 的存在，故该线为纯增量产出。
5. **交叉印证**：三条独立结论在不同分组各自得出、随后由主会话合并为一条上报——`mask_credentials` 的 camelCase 绕过（前端 / 平台 / 选源三组分别命中）、Windows 第二条 ffmpeg 下载源（增量审计与构建组各自命中）、转码线程池与 `check_subprocess` 收尾链（录制组与基础设施组各自命中）。跨组同判的条目一律标为高置信。
6. **筛除臆测**：第九章登记「提出后经回源确认不成立或属刻意设计」的条目，供后续审查者复用为基线；需真机 / 需外部响应形态才能定论者统一**降置信度而非删除**，并标注为需用户补跑的动作。

### 1.4 结果统计

| 严重度 | 数量 | 分组分布（与第三～五章的小节一一对应） |
| --- | --- | --- |
| 严重（P0） | 28 | 录制链与平台解析正确性 9（§3.1）/ 凭据·TLS·SSRF·注入·供应链 8（§3.2）/ 运行期下载源 1（§3.3）/ 门禁与测试可信度 8（§3.4）/ Web 面板可用性 2（§3.5） |
| 中等（P1） | 65 | 录制主链与房间线程 9 / 平台解析与签名 17 / 选源与画质档位 5 / 并发与凭据生命周期 2 / 面板与配置写入与前端 8 / 弹幕与字幕 6 / GUI 与 i18n 与推送 6 / 构建·CI·门禁与测试可信度 12 |
| 轻微（P2） | 68 | 平台解析与网络层 22 / 录制链与 ffmpeg 与字幕 14 / 面板与配置写入与前端 10 / GUI 与推送 6 / i18n 目录与构建与仓库卫生 16 |
| **合计** | **161** | 其中若干行为同源合并条目，行内含 2～6 个子项 |

| 横向特征 | 计数（统计口径见附录 B） |
| --- | --- |
| **本轮经可执行命令实测复现**的结论 | **7 项**：主会话实测 4 项（`SEV-2202` ffmpeg 模板、`SEV-2210` 掩码绕过、`SEV-2212` TLS context、`SEV-2216` h2/socksio 缺失）+ 分组本机实测 3 项（`MID-2207` glob 失配、`MID-2221` 双 Cookie 头、`MIN-2227` `fnmatch.translate`）；命令与读数见 2.3 |
| 两个及以上独立取证线得出同一结论（交叉印证后合并） | 5 组：`SEV-2202`（两个录制组）、`SEV-2210`（选源组 + 平台组 + 主会话）、`MID-2209`/`MID-2227`（网络层组 + 选源组的同一约定缺口）、`SEV-2218`（增量审计 + 构建组）、`SEV-2219`（增量审计 + 构建组） |
| 正文写明属「半修 / 漏改 / 只在一条分支落地」 | 严重 2 项（`SEV-2203`、`SEV-2208`）+ 中等 10 项（`MID-2209`、`2213`、`2218`、`2223`、`2225`、`2227`、`2235`、`2239`、`2249`、`2253`）+ 轻微 5 项（`MIN-2226`、`2227`、`2234`、`2235`、`2259`） |
| 「注释 / 文档陈述与代码不符」（含把未做的写成已做） | 19 处，其中 **3 处位于 `AGENTS.md` 自身**（`SEV-2226` 的两条安全辩护、`MIN-2255` 的五点同步清单、`MIN-2256` 的 scheduler 回指陈述），另 3 处属**门禁自检注释自述与实现相反**（`SEV-2220`、`SEV-2225`、`MIN-2257`） |
| 涉及凭据 / TLS / SSRF / 注入 / 脱敏 / 供应链的安全面 | 严重 **10 项**（§3.2 全部 8 项 + `SEV-2218` + `SEV-2222`）；中等与轻微侧未单设类别列，可按各行「影响」栏检索 `mask_credentials`／凭据／Cookie／TLS／SSRF／钉定 复核 |
| 缺回归锁，或现有回归锁**看不见该失效形态** | 23 项（6.3 表逐条列出待补 21 处，含 5 处「锁只断言调用形状」） |
| 需真机或外部响应形态才能定论（已降置信度、列入待用户补跑动作） | 14 项，集中在 `SEV-2204`、`SEV-2205`、`MID-2208`、`MID-2211`、`MID-2212`、`MID-2222`、`MID-2226`、`MIN-2201`、`MIN-2202`、`MIN-2204`、`MIN-2208`～`MIN-2212`、`MIN-2230` |
| 基线提交（13:10）之后新写入、此前从未被任何一轮审查覆盖的代码 | 约 1,739 行实质内容（含 402 行全新模块）→ 产出 `SEV-2218`、`SEV-2222`、`SEV-2208` 三项严重与 `MID-2259`、`MIN-2267`、`MIN-2268` 三条轻微 |

**一句话结论**：28 项严重里有 **12 项属于「门禁与测试查不到的类别」**——§3.4 的 8 项（门禁自身丢退出码、锁只断言调用形状、替身丢实参、被锁对象搬了家）、§3.1 的 2 项半修复、§3.3 的 1 项「锁看不见被锁之物」，以及 §3.5 的 1 项假绿面板——而非新增架构缺陷。项目的架构约束仍然有效：探针语义、ffmpeg 四类单一定义点、并发信号量配平与 `Popen` 前 acquire、发布链钉定的形状判定、装饰器与返回契约、路径穿越与 argv 注入面、凭据入日志的既有脱敏链，在本轮逐条复核下均未复现问题（第九章 24 组）。

---

## 二、审查范围

### 2.1 覆盖清单

统计口径为 `wc -l`（不含空行裁剪），第三方可读性说明见 2.2。

| 区域 | 文件数 | 行数 | 覆盖 |
| --- | --- | --- | --- |
| 根目录 Python（`main.py` 4,925 / `gui.py` 3,696 / `build_exe.py` 1,165 / `msg_push.py` 531 / `i18n.py` 402 / `web.py` 325） | 6 | 11,044 | 全文，`main.py` 拆 3 组按行区间覆盖 |
| `src/` Python（含 `src/platforms/`、`src/proto/`；`src/spider.py` 6,470 拆 3 组，`src/stream.py` 1,200 与 `src/stream_select.py` 1,193 一组） | 44 | 22,732 | 全文 |
| `scripts/` Python（含 2,097 行的 `douyin_live_recorder_standalone.py` 孪生副本 + 10 个门禁/维护脚本） | 11 | 4,874 | 全文 |
| 自研 JavaScript（`web/app.js` 1,567；`src/javascript/` 的 `x-bogus.js` 563 / `haixiu.js` 534 / `liveme.js` 425 / `migu.js` 393） | 5 | 3,482 | 全文（`crypto-js.min.js` 为 vendored，排除） |
| 前端样式与页面（`web/style.css` 426 / `web/index.html` 160 / 根 `index.html` 271） | 3 | 857 | 全文 |
| 测试面（`tests/*.py` 94 文件 33,869 行 + `tests/frontend/*.mjs` 775 行） | 95 | 34,644 | 可信度专项审计（第七章），并逐条核对回归锁与被测实现的关系 |
| 部署与 CI 即代码（`Dockerfile` / `docker-compose.yaml` / `pyproject.toml` / `requirements.txt` 共 761 行；`.github/workflows/*.yml` 与 `.github/actions/retry` 共 1,782 行；`.gitignore` / `.dockerignore`） | 12+ | ≈3,300 | 全文 |
| i18n 目录（`zh_CN.po` / `zh_CN.mo` / `en_US.json` / `en_GB.json` / `zh_TW.yaml`） | 5 | — | 键集与占位符集合一致性、与代码内 `tr()` 模板的对账 |
| 其它自研源（`StopRecording.vbs`，UTF-16 LE 37,804 字节；`scripts/spike_arm64_static_ffmpeg.sh`；`typings/*.pyi` 手写存根；`src/proto/douyin_pb2.pyi`） | 18 | — | 全文（`douyin_pb2.py` 为 protoc 生成，按 AGENTS 不深读，仅核对存根覆盖面） |

**基线之后的增量（本轮新增覆盖）**：`src/ffmpeg_master_download.py`（402 行，全新且此前未跟踪）、`src/ffmpeg_install.py`（384 行改写）、`scripts/run_gates.py`（47 行）、`scripts/check_runtime_pins.py`（17 行）、`build_exe.py`（18 行）、`scripts/douyin_live_recorder_standalone.py`（41 行）、`.github/workflows/ci.yml`（33 行新增两条门禁步骤）、`main.py`（13 行，W6 的 Apple Silicon 让位判据接线）、`tests/test_build_exe.py` / `tests/test_ffmpeg_install.py` / 两个新增测试文件。

### 2.2 明确排除项

- **第三方依赖与运行时**：`.venv/`、`node/`、`ffmpeg/`、`node_modules`、`src/javascript/crypto-js.min.js`（vendored 压缩产物）、`uv.lock`、`DouyinLiveRecorder.egg-info/`。
- **构建与运行期产物**：`dist/`、`build/`、`__pycache__/`、`*.pyc`、`.coverage`、`coverage.json`、`downloads/`、`logs/`、`backup_config/`、`recordings/`、`.pytest_cache/`、`.mypy_cache/`、`.isorted` 残留。
- **本地工具目录**：`.mimosa/`、`.qoder/`、`.qoder-credits/`、`.agents/`、`.v2c/`、`.workbuddy/`、`.codebuddy/`、`.pnpm-store/`、`.npm-cache/`（其中 `.workbuddy/memory/` 与 `docs/agent-reference/` 仅作为「文档陈述」核对对象，不作为源码审查对象）。
- **正式文档与记录**：`README*.md`、`CODE_WIKI*.md`、`AGENTS.md`、既往 `CODE_REVIEW_*.md`、`PROPOSAL_*.md`——不作为缺陷计数对象，但**其陈述与代码是否一致**在本轮计入结论（1.4 表第 4 行）。
- **凭据文件内容**：`config/config.ini` 与 `config/URL_config.ini` 已按项目约定被 `.gitignore` 与 `.dockerignore` 双向排除，本轮**只读取键名/节名**用于配置键审计，未复制任何真实凭据值；报告中出现的全部 URL / token / cookie 均为合成占位样例或脱敏形态。

### 2.3 验证证据（本轮实测）

按 `AGENTS.md`「完成定义」第 2 步的判定口径列明：本轮为**纯静态 + 只读取证 + 本机离线命令实测**，未执行任何真机录制验证（详见附录 B 第 1 条）。

| # | 命令 / 取证方式 | 读数时刻 | 结论 |
| --- | --- | --- | --- |
| 1 | `PYTHONUTF8=1 python scripts/run_gates.py --keep-going` | 2026-09-22 21:5x | **8/8 全绿（28.1s）** + 附带 `[pytest warnings summary 兜底] PASS (183.4s)`。即本章全部 24 项严重结论是在门禁全绿状态下取得的。 |
| 2 | `python scripts/check_runtime_pins.py` | 同上 | rc=0；报 2 个矩阵内槽位 + 2 个矩阵外键未钉定（按设计本地放行、`--strict` 才拦）。用于确认 `SEV-2209` 的「验签不可达」不是表空导致。 |
| 3 | 用 `src/utils.py` 的真实 `_SECRET_KEYS`/`_SECRET_QUERY_RE` 对合成查询串做 `re.sub`（不 `import src.utils`，避免触发日志 sink） | 2026-09-22 22:0x | `accessToken=SECRET…`、`wsAuth=SECRET…`、`tk=TKVAL` **原样保留**；`access_token`、`token`、`ws_secret` 被抹成 `***`。→ `SEV-2203` 定量成立。 |
| 4 | 在本机 venv（CPython 3.14.7）读 `ssl`/`smtplib`：`_create_stdlib_context is _create_unverified_context`、所得 context 的 `verify_mode`、`SMTP_SSL.__init__` 与 `SMTP.starttls` 源码 | 同上 | 同一对象；`verify_mode == 0`（CERT_NONE）、`check_hostname is False`；两条路径均回落该 context。→ `SEV-2205` 定量成立。 |
| 5 | 用仓内自带 `ffmpeg/ffmpeg.exe`（`n9.0.1-11-ge47273f4d9`）在 `%TEMP%` 离线实测 `-f segment` 模板（`-f lavfi` 源，不触网、不写仓库目录） | 2026-09-22 22:11 | 含 `%` 的模板与含孤立 `%d` 的模板**一律失败**；干净模板与非分段形态**均成功**。→ `SEV-2202` 定量成立。 |
| 6 | `grep -rn "_douyin_rate_limit\|douyin_min_interval" tests/`；`tests/test_concurrency.py` 的 import 清单 | 2026-09-22 22:0x | 仅命中该文件**一条注释**；该文件不 import 任何 `src.*`。→ `SEV-2222` 成立。 |
| 7 | `grep -c 'patch("subprocess\.' tests/*.py` 等字符串形态统计 | 同上 | 18 处，分布于 `test_main_fixes.py`、`test_spider_fixes.py`（另有 `patch("src.stream_select.time.sleep")` 13 处）。→ `SEV-2224` 成立。 |
| 8 | `grep -rn "exit_recording\s*="`（全仓） | 同上 | 仅 2 处赋值、**无复位点**。→ `SEV-2212` 成立。 |
| 9 | 逐行读 `main.py:986-1000` 与 `1218-1245` | 同上 | 注释声明「stop() 移入 finally」，finally 内实际无该调用（真身在 1237-1239）。→ `SEV-2213` 成立。 |
| 10 | `grep -n '_match_host("https\?://' main.py` + `_match_host` 定义 + 准入段 4730-4746 | 同上 | 7 条表项钉死 scheme、matcher 为纯子串 `find`、准入仅在无 `://` 时补 https。→ `SEV-2216` 成立。 |
| 11 | `python -m mypy src/ffmpeg_master_download.py`；`[tool.mypy].files` 清单；`check_coverage.MODULE_THRESHOLDS` 键表 | 同上 | 新模块**在** mypy 范围内且通过；但 `tests/` 内对该模块**零引用**，且逐模块覆盖率表只枚举 6 个模块（按表遍历，不扫 `src/`）→ `MID-2230` 成立。 |
| 12 | 配置键只读核对：`grep -c` 于 `config/config.ini` | 同上 | `[Cookie]` 1、`tiktok_guest_cookie` 1、`xhs_session_sid` **0** → `MID-2213` 的「每轮一条 warning」成立。 |

## 三、严重问题（P0，28 项）

> 判定口径：**用户可见的功能失效 / 数据或凭据外泄 / 发布链可分发不可信产物 / 门禁在失效形态上自证全绿**。
> 四项标「已实测」的结论（`SEV-2202`、`SEV-2210`、`SEV-2212`、`SEV-2216`）附带 2.3 节的复现命令与读数，属本轮证据等级最高的一类。

### 3.1 录制链与平台解析的正确性（9 项）

#### SEV-2201 ｜ `play_url_list` 的元素类型契约互斥：8 个以上平台每轮必抛并被吞成「未开播」

- **位置**：`src/spider.py:3965`（写入侧，同型 `2614`/`2726`/`2776`/`2952`/`3117`/`3314`/`4059`/`4393`）× `src/stream.py:1174-1181`（读取侧）× `main.py:2073` 等调用点
- **证据**（写入侧，`TwitCasting`）：

```python
        sorted_streams = sorted(streams.items(), key=lambda item: quality_order.get(item[0], 99))
        play_url_list = [url for _, url in sorted_streams]
        result |= {"title": live_title, "is_live": True, "play_url_list": play_url_list}
```

- **证据**（读取侧，MID-20 之后）：

```python
        play_url = play_url_list[selected_quality]
        if key:
            return str(play_url.get(cast(str, key), "") or "")
        for probe_key in _PLAY_URL_KEY_ORDER:
            value = play_url.get(probe_key, "")
```

- **机理**：写入侧产出 `list[str]`，读取侧无条件对元素调 `.get()`。`_pad_list`（`src/stream.py:404-418`）只做「以末元素补齐」，**不做任何类型包装**；`get_stream_url` 挂 `@trace_error_decorator`（`1139`），于是 `AttributeError: 'str' object has no attribute 'get'` 被兜成 `{"is_live": False}`。调用点一律 `spec=False` ⇒ `get_url(None)` ⇒ 必进探测循环 ⇒ 必抛。受影响平台：SOOP 两条路径、PandaTV、WinkTV、TTingLive 的 HLS 路径、TwitCasting、Twitch、百度直播、ShowRoom。
- **影响**：这些房间**在播也永远录不上**，用户侧只看到「未开播」，`streamget.log` 每轮一条 error。为何三面门禁全绿（已逐一核对）：`tests/test_stream.py` 全部用例只喂 dict 元素（`972`/`1003`/`1019`/`1051`/`1068`），`tests/test_spider_hardening.py:1083` 反而把 `list[str]` **钉成契约**，`tests/test_platform_dispatch.py:55` 把 `main.stream` 整体换成记录桩——这条跨模块接缝无任何测试。`src/stream.py:266-270` 的注释「通用平台的 play_url_list 每项是一『画质 → 地址字典』」是错误前提。
- **修复**：`get_url` 内先判 `isinstance(play_url, str)` → 无 key 时原样返回，仅 dict 项走 `_PLAY_URL_KEY_ORDER` 探测；补一条 `play_url_list=["https://x/a.m3u8"]` 的接缝用例并做变异验证（删掉 str 分支即变红）；同时改正 `266-270` 的前提陈述。**注意不要反过来把 8 个平台改成产出 dict**——写入侧契约已被测试钉死，改读取侧是一处收口、改写入侧是八处。
- **置信度**：高（四级证据全部实读）｜ **类别**：正确性

#### SEV-2202 ｜ 主播名/标题里的裸 `%` 直通 ffmpeg 分段模板：分段录制必然失败，且被归因成 CDN 故障（已实测）

- **位置**：`main.py:294`（过滤集）→ `main.py:3061-3071`（模板拼装）→ 消费方 `-f segment`；误导归因在 `main.py:1340`、`1364-1367`
- **证据**：

```python
rstr: str = r"[\/\\\:\*\？?\"\<\>\|&#.。,， ~！· ]"  # 文件名字符过滤正则
```

  该字符集刻意排除了 `& | < > * ? " : / .` 等元字符，**但不含 `%`**；分段分支随后把整串当 ffmpeg 文件名模板：

```python
        return f"{full_path}/{anchor_name}_{title_in_name}{seg_now}_%03d.{extension}"
```

- **实测**（用仓内自带 `ffmpeg/ffmpeg.exe`，版本 `n9.0.1-11-ge47273f4d9`，`-f lavfi` 离线源，产物落 `%TEMP%`）：

```
FAIL | 含 % 的分段模板（主播50%折扣_2026-09-22_11-22-33_%03d.ts）
FAIL | 含孤立 %d 的模板（A_%d_%03d.ts）
OK   | 干净分段模板（对照）
OK   | 非分段形态含 %（对照）
```

- **影响**：凡主播名或标题含 `%`（「50%折扣」「100%」「进度99%」极常见）且开启分段录制（`config.ini` 默认为「是」），该房间**每一轮都录不上**。后果是三重误导：ffmpeg 秒退 `rc=-22` → `_describe_return_code` 解释成「容器/编码不匹配或输入选项解析失败」（方向全错）→ 因产物父目录存在，MID-02 的「输出侧 IO 失败」豁免不生效 → 落进 `_FFMPEG_FAST_FAIL_SECONDS` 的「CDN 快速失败」判定 → `mark_ffmpeg_reject` 把**健康线路**记进探针退避、`record_error(host)` 累积推向按 host 的熔断，殃及同平台其它房间。用户视角是「一开分段就录不上，关掉分段就好」。`CODE_REVIEW_2026-09-21.md:658` 的「主播名/标题经 `clean_name` 过滤，无注入面」结论对本条不成立——这是**格式串注入**，不是 shell 注入。
- **修复**：把 `%` 加进 `rstr`（与 `*`/`?` 同类：下游被当模式解释），并在 `_build_record_output_path` 的分段与音频两个分支加守卫「base 段出现额外 `%` 占位符即归一并告警」；回归锁直接断言「分段模板除末位 `_%03d`/`_%02d` 外不得再含 `%`」。
- **置信度**：高（本机 ffmpeg 实跑复现）｜ **类别**：正确性

#### SEV-2203 ｜ `http://` 形态的房间地址能过准入白名单、却永远落不到任何解析器上（MID-04 七处同类表项只修了一处）

- **位置**：`main.py:2758-2770`（表项）× `main.py:1488-1492`（matcher）× `main.py:4733` 与 `4746`（准入侧）
- **证据**：

```python
    (_match_host("https://www.tiktok.com/"), _resolve_tiktok_com),
    (_match_host("https://live.kuaishou.com/"), _resolve_live_kuaishou_com),
    (_match_host("https://www.huya.com/"), _resolve_huya_com),
    (_match_host("https://www.douyu.com/"), _resolve_douyu_com),
```

  实测该形态共 **7 条**表项钉死 scheme；而 matcher 是纯子串匹配 `any(url.find(frag) > -1 ...)`，准入侧只在 URL **完全没有** `://` 时才补 `https://`：

```python
                    url = "https://" + url if "://" not in url else url
                    url_host = url.split("/")[2]
```

- **影响**：用户写 `http://www.douyu.com/9422371`、`http://live.bilibili.com/123` 时，`url_host` 命中 `PLATFORM_HOST` → 起房间线程 → 7 条钉死 https 的表项全部不命中 → 落 `_resolve_unrecognized` → `sleep(max(30, delay_default)) + continue` 无限空转，每轮一条 error、永不录制、还占着一个监控位。这与 2026-09-20 `MID-04` 为 xhslink 修掉的是**完全同一形态**（`2765-2768` 的注释原文即「会被准入却落不到解析器上、无限空转」），其余 7 条未同步；同一份表里 `douyin.com/`、`kugou.com/` 不带 scheme，也证明「scheme 无关匹配」才是本意。它同时使 `main.py:2834` 的注释「不可达分支（main() 已按平台白名单过滤）」成为假陈述。
- **修复**：7 条表项去掉协议前缀（与 `douyin.com/` 同口径），或让 matcher 先剥 scheme 再比对；把 `2834` 的「不可达」改成「准入 host 命中但无匹配解析器」；在 `tests/test_platform_dispatch.py` 补一条「`PLATFORM_HOST` 每项在剥协议后仍被某表项命中」的锁。
- **置信度**：高（表项计数、matcher 语义、准入行为均已实测）｜ **类别**：正确性

#### SEV-2204 ｜ 快手 `playUrls` 只认 `h264` 键：纯 h265 房间被静默判「未开播」，`"h264": null` 形态抛 TypeError

- **位置**：`src/spider.py:1063-1081`
- **证据**：

```python
        if isinstance(play_urls_obj, dict) and "h264" in play_urls_obj:
            h264 = cast(dict[str, object], cast(dict[str, object], play_urls_obj)["h264"])
            if "adaptationSet" not in h264:
                return result
            adaptation = cast(dict[str, object], h264["adaptationSet"])
            play_url_list = adaptation.get("representation")
        else:
            # TODO: Old version which not working at 20241128, could be removed if not working confirmed
            play_urls_list = cast(list[object], play_urls_obj) if isinstance(play_urls_obj, list) else []
```

- **机理与影响**：两种真实形态漏录且**完全静默**——① `playUrls` 是 dict 但只含 `h265`（HEVC-only 房间，本仓其它平台明确支持 h265 选流）时落入 `else` 那条代码自认「20241128 已失效、基本不会命中」的死分支 → `[]` → `is_live` 保持 False、零日志；② `"h264": null`（键在值为空，快手常见降级形态）时 `"adaptationSet" not in None` 抛 `TypeError`，被兜底装饰器吞成未开播。附带一条不对称：`1073` 的 `adaptation.get("representation")` 缺 `or []`（`else` 分支的 `1081` 有 `, []`），可把 `flv_url_list=None` 与 `is_live=True` 一起返回。
- **修复**：按 codec 优先级遍历 `play_urls_obj` 中实际存在的键（h264 优先、缺失取 h265），取前 `isinstance(h264, dict)`；`representation` 补 `or []`；整条链拿不到候选时补一条 `_warn_api_abnormal`。
- **置信度**：高（机制）/ 中（现网 HEVC-only 房间占比需真机核对）｜ **类别**：正确性

#### SEV-2205 ｜ 畅聊/音播的 `liveID` 走 `_dig_str` 且不判空：`is_live=True` 却交出 `{domain}/.flv` 坏地址

- **位置**：`src/spider.py:5015-5023`（畅聊）、`src/spider.py:5134-5142`（音播，逐字同形）
- **证据**：

```python
        live_id = _dig_str(room_info, "liveID")
        flv_url = f"{flv_domain}/{live_id}.flv"
        m3u8_url = f"{hls_domain}/{live_id}.m3u8"
        result |= {"is_live": True, "m3u8_url": m3u8_url, "flv_url": flv_url, "record_url": flv_url}
```

- **机理与影响**：同一 `live.ashx` 接口族的孪生实现（流星 `4744-4754`）明确写了「刻意不用 `_dig_str`（那会把 int 变成空串、拼出坏地址）」并对 `idx`/`liveId1` 双判空；`tests/test_spider_hardening.py:1192-1195` 更实测记录该接口 `roomInfo` 的数值字段**在真实响应里是数字**。`liveID` 为 int 或缺失时此处返回 `""`，却仍无条件置 `is_live=True` 并交出只有域名的地址 → 两路候选全部校验失败 → `real_url` 为空，该房间每轮多烧「域名页 + 两次探针」且永远录不上，日志只显示「流地址校验失败」，看不出根因是 `liveID` 取空。属 `MID-48` 加固的半落地（只补了域名归因、漏了同链的 `liveID`）。
- **修复**：对齐流星口径——`live_id = _dig(room_info, "liveID")`，`if live_id is None: _warn_api_abnormal(...); return result`，拼地址用 `str(live_id)`。
- **置信度**：高（判空缺失与孪生不一致为纯代码事实）/ 中（`liveID` 实际类型需真机）｜ **类别**：正确性

#### SEV-2206 ｜ `exit_recording` 是单向棘轮：磁盘恢复后录制引擎「活着但永不录制」，且置位当刻零日志

- **位置**：`main.py:4613-4634`（唯一置位点）；实测全仓赋值仅 `489`（`safe_exit`）与 `4614` 两处，**无任何 `= False` 复位点**
- **证据**：

```python
        if disk_free_gb < disk_space_limit:
            exit_recording = True
            if not recording:
                logger.warning(
                    i18n.tr(
                        "Disk space remaining is below {disk_space_limit} GB."
```

- **机理与影响**：告警被 `if not recording:` 包住 → **置位当刻（通常仍有房间在录）不打印任何提示**。房间线程在 `973`/`707` 见到标志即 return，`recording` 排空；此后只要有一轮 `disk_free_gb >= disk_space_limit`（用户删掉或移走一批录像即发生），`4635-4816` 的拉起条件 `not exit_recording` 恒假，而 `return`/`sys.exit` 分支又永不走到 → Web 模式下引擎线程继续存活、主循环每 3 秒空转：面板数字不变、状态正常、**再也不产出任何文件**，全程零告警。已在 `running_list` 里的 URL 因 `src/notify.py:201` 的 `if main.exit_recording ... : return` 永不摘除。这正是 `4623-4630` 注释想避免的形态，只是换了触发条件。
- **修复**：不要用 `exit_recording` 承载「磁盘限流」语义——新增 `disk_limited` 标志（房间线程与拉起条件同时判它），在空间恢复时复位并打「空间已恢复，继续录制」；若坚持复用，至少置位当刻无条件打一条 warning，并补 `else: exit_recording = False`（`safe_exit` 自身会 `sys.exit`，复位不影响 Ctrl+C 语义）。
- **置信度**：高 ｜ **类别**：正确性

#### SEV-2207 ｜ 录后转码线程池的 `atexit` join 排在三个已注册清理钩子**之前**：退出链路最长可挂 3600 秒

- **位置**：`src/video_postprocess.py:31`（`_MAX_CONVERT_TIMEOUT = 3600`）、`:46`（惰性建池）、`main.py:508-512`（三个 atexit 注册）；实测全仓对该池 `shutdown(` **零调用点**
- **证据**：

```python
_atexit_result_0 = atexit.register(archive_runtime_logs, reopen_streams=False)
_atexit_result_1 = atexit.register(cleanup_all_ffmpeg_processes)
```

- **机理与影响**：`ThreadPoolExecutor` 的 worker 是**非守护**线程，而 `concurrent.futures.thread._python_exit` 在**首个 worker 创建时**才 `atexit.register`——即晚于上面三个注册。atexit 为 LIFO，故 `_python_exit`（`work_queue.put(None)` 后逐个 `t.join()`）**先于** ffmpeg 清理与日志归档执行，转码任务的上限是 3600 秒。后果：磁盘满退出 / 未捕获异常 / Web 托盘退出这三条不经 `safe_exit` 的路径上，**录制中的 ffmpeg 子进程在最长 1 小时内不被终止、继续拉流写盘，四个运行日志永不归档**——直接违反 `AGENTS.md` 关键约定 8 的「归档必须先于两个 cleanup 注册」契约。信号退出路径虽已先杀 ffmpeg，进程仍卡在 join 里不退出。转码 ffmpeg 也未 `register_ffmpeg_process`，注册表管不到它。
- **修复**：在 `main()` 退出路径显式 `_postprocess_executor.shutdown(wait=False, cancel_futures=True)`；把归档/清理挂到更早触发的钩子，或改用守护线程 + 自管队列（与 `MID-32` 对 `ffmpeg_proc` 的处置同构）；`_run_ffmpeg_checked` 在检测到 `exit_recording` 时提前 kill 子进程。**本仓已在 `src/ffmpeg_proc.py:184` 的注释里写下同一教训**（「`shutdown(wait=True)` 是第二个无界点，故改用显式分组守护线程」），转码池是该已知失效形态的未处理残留。
- **置信度**：高（CPython 稳定语义 + grep 证实零 shutdown）｜ **类别**：正确性

#### SEV-2208 ｜ 上一轮 `SEV-N01` 半修：注释声明「`stop()` 移入 finally」，实际未移

- **位置**：`main.py:991-995`（声明）/ `1218-1227`（finally 全体）/ `1237-1239`（`stop()` 真身）
- **证据**（注释）：

```python
    # SEV-N01 修复（2026-09-21，CODE_REVIEW_2026-09-21）：弹幕采集器的声明一并提到 try 之前，
    # 且其 stop() 移入 finally——原声明/停止都在 try/finally 之外，try 内任一处抛错
    # （现实形态为 Thread.start 的 can't start new thread）即绕过停止，泄漏的采集线程继续向
    # 同一 base_filename 写 SRT，下一轮再起第二路交错覆盖。DanmakuCollector.stop() 自带
    # _stop_called 幂等，重复调用安全。
```

- **证据**（`finally` 的实际全部内容）：

```python
        if process is not None and not _converged and process.poll() is None:
            _ = _terminate_ffmpeg_process(process)
            unregister_ffmpeg_process(process)
            clear_record_info(record_name, record_url)
```

- **机理与影响**：`danmaku_collector.stop()` 位于 `try/finally` **之后**（`1237-1239`）。于是注释自己举的现实形态——`1074` 的 `Thread.start()` 抛 `can't start new thread`（发生在 `1045` `collector.start()` 之后）——异常穿出 try 时采集器仍不被停止：泄漏线程继续写 `_000.srt`，下一轮起第二路交错覆盖。声明上移那一半确实做了（`994`）。同一 try/finally 里 `SEV-N01` 另两处漏口亦未落地：① `1275-1284` 零字节分支 `return False` 早于 `1373-1377` 的 `recording.discard` + `unregister` → `_ffmpeg_processes` 只增不清，约每 2 分钟多留一个仍持 `stdin=PIPE` 写端句柄的 Popen；② finally 把三个动作与 `terminate` 共用 `process.poll() is None` 条件，「进程已自然退出 + 守护段抛错」时全不执行，留下幽灵 `recording` 条目——进而使 `4613` 的 `if not recording:` 恒假、面板恒显录制中。**本条最危险之处在于注释把未做的写成已做**：后续审查若信任注释就会跳过这里（本轮确有一个分组正是在其「已核实不构成问题」清单里按该注释把此项判为已修，主会话读回源码后推翻）。
- **修复**：`finally` 内无条件 `if danmaku_collector is not None: danmaku_collector.stop()`；`_terminate_ffmpeg_process` 单独保留 `poll() is None` 判定，`unregister` + `clear_record_info` 在 `not _converged` 时无条件执行；零字节分支改「先收尾后 return」；同步修正 `991-995` 措辞。
- **置信度**：高（逐行读回）｜ **类别**：健壮性

#### SEV-2209 ｜ `run_js_async` 整条 execjs 链路无任何超时：node 卡死会把房间永久楔死并占住网络信号量

- **位置**：`src/utils.py:147-153`；消费点 `src/spider.py:4428`（LiveMe）、`5329`（嗨秀）、抖音 X-Bogus 路径；对照同文件 `156` 的姊妹函数与 `src/spider.py:6281`
- **证据**：

```python
async def run_js_async(js_path: str, func_name: str, *args: object) -> object:
    def _sync_call() -> object:
        return cast(object, getattr(get_compiled_js(js_path), "call")(func_name, *args))

    return await asyncio.to_thread(_sync_call)
```

  姊妹入口却有预算：`async def run_node_script_async(script_path: str, *args: str, timeout: float = 30.0)`（migu 走这条并显式传 `timeout=30`）。
- **机理与影响**：两个分组各自独立核实依赖侧——`execjs` 的 `Context.call(..., timeout=None)` → `_execute(..., timeout=None)` → `subprocess.run(cmd, ..., timeout=None)`，即**全链无超时**。`asyncio.to_thread` 投出的工作线程也不可取消。房间线程以 `asyncio.run(...)` 逐轮驱动，一旦卡在 `await run_js_async` 则该轮永不返回：房间不再进入下一轮、不再检查「已被注释 / 停止录制」、无任何日志线索。更重的一层是**全局**的：调用侧形态为 `with semaphore: asyncio.run(spider.get_liveme_stream_url(...))`（`main.py:2194`/`2389`/`2503`），挂死期间**网络信号量不归还**，固定并发模式下 N 个房间卡死即全程序停止取流。触发条件不苛刻：node 冷启动被杀软/磁盘 stall 卡住、或 `x-bogus.js` 这类 JS-VM 在异常输入下空转。2026-09-12 审查 6.3 把这两处由同步改异步以「不冻结事件循环」，但只有同轮的 migu 路径拿到 `timeout=30`——超时预算从「阻塞事件循环」变成了「无限等待」，属半修。
- **修复**：给 `run_js_async` 增加 `timeout: float = 30.0` 并沿 `call(..., timeout=timeout)` 透传（PyExecJS 与 exejs 两侧都有该形参），或用 `asyncio.wait_for` 包裹 `to_thread`；超时按 `ProgramError` 上抛交现有装饰器兜底；与 `run_node_script_async` 同口径。
- **置信度**：高（机制链逐级核实）｜ **类别**：健壮性

### 3.2 安全：凭据、TLS、SSRF、注入、供应链（8 项）

#### SEV-2210 ｜ `mask_credentials()` 对 camelCase 复合凭据键整体失效：斗鱼 `wsAuth`、嗨秀 `accessToken`、`tk` 明文落轮转日志（已实测）

- **位置**：`src/utils.py:757-781`（`_SECRET_KEYS` + `_SECRET_QUERY_RE`）；受害日志点 `src/stream_select.py` 20+ 处、`src/async_http.py:310-317`、`src/spider.py:5334-5343`
- **证据**：

```python
_SECRET_QUERY_RE = re.compile(r"(?i)((?<![A-Za-z0-9])(?:" + _SECRET_KEY_ALT + r")=)[^&\s\"']+")
```

- **实测**（从 `src/utils.py` 抽出真实 `_SECRET_KEYS`/`_SECRET_KEY_ALT`/`_SECRET_QUERY_RE` 后代入执行，合成值）：

```
LEAK https://…?accessToken=SECRETAAA&_=1          # 未抹
LEAK https://…?wsAuth=SECRETAAA&tk=TKVAL          # 未抹
ok   https://…?access_token=***&token=***         # 正常
```

- **机理**：黑名单里有裸 `auth`/`token`/`access_token`，但 `(?<![A-Za-z0-9])` 前顾把「字母紧跟」的 camelCase 复合键全部排除（`accessToken` 的 `token` 前是字母 `s`）；`ws_secret`/`ms_token` 因带下划线反被覆盖，**恰好掩盖了这个缺口**。三个分组独立命中同一根因（选源组的 `wsAuth`/`tk`、平台组的 `accessToken`/`msToken`/`verifyFp`、主会话复测）。
- **影响**：斗鱼 `getH5PlayV1` 下发的 FLV/m3u8 一律挂 `wsAuth`，于是**每个斗鱼房间每轮选源**都把可用的完整拉流直链写进 `logs/streamget.log`（WARNING 级，300KB 轮转保留多份、停止录制还经 `archive_runtime_logs` 改名归档）与 `PlayURL.log`；拿到日志即可直接拉流或外发。嗨秀侧真正外泄的不是随仓库分发的内置 token，而是用户经 `[Cookie] haixiu_access_token` 配置的**私有轮换凭据**——那正是该覆盖入口存在的理由。门禁与注释共同构成假绿：`tests/test_stream_select.py:1319-1348` 只断言「`url=` 必须包 `mask_credentials`」这一**调用形状**，`tests/test_utils.py::TestMaskCredentialsCoverage` 的覆盖面表有 `wsSecret`/`txSecret`/`signature` 却没有 `wsAuth`。
- **修复**：`_SECRET_KEYS` 增加 `wsauth`/`tk`/`accesstoken`/`mstoken`/`verifyfp`/`idtoken`/`refreshtoken`（长名优先排序已自动生效），并把覆盖面断言从「调用了掩码」升级为「**值确实消失**」；建议同时给 `mask_credentials` 加一条 camelCase 边界分支（`(?<=[a-z])(?=[A-Z])`），否则下一个新平台会第三次重犯。
- **置信度**：高（本机实跑复现）｜ **类别**：安全

#### SEV-2211 ｜ 面板的配置写入用弱化副本 `_atomic_write_text`：`config.ini` 的 0600 收紧被静默退回 umask 默认（并丢失 fsync）

- **位置**：`src/web_config.py:771-784`（副本本体，调用点 `767`/`1167`/`1204`）对照 `src/utils.py:485-512`（完整版）与 `src/config_io.py:109-113`（薄封装）
- **证据**（面板侧副本全文）：

```python
def _atomic_write_text(path: Path, text: str) -> None:
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    with tmp.open("w", encoding=TEXT_ENCODING, newline="") as f:
        _ = f.write(text)
    try:
        os.replace(tmp, path)
```

  而 `utils` 版在 `replace` 前做了：`orig_mode = stat.S_IMODE(os.stat(path_str).st_mode)` → `tempfile.mkstemp` → `flush` + `_fsync_file` → `os.chmod(tmp, orig_mode)`，其注释明写「CR-07 对 config.ini 的 0600 收紧可能被 umask 0644 静默放宽」。
- **影响**：`os.replace` 后目标继承临时文件的模式，`tmp.open("w")` 按 umask 建文件（POSIX 通常 0644），于是 `PUT /api/config`（改 `web_password`、改任何 Cookie 类键）**每写一次就把 `utils.update_config` 的 `os.chmod(path, 0o600)` 还原一次**——含全部平台账号口令/cookie 的 `config.ini` 在同机多用户 / Linux 宿主 / 容器内变为任意本地用户可读。另外两项加固同时被绕过：无 fsync（`MID-57`），掉电可留下「新目录项 + 空数据页」的 0 字节配置；`f.write` 自身抛 `OSError`（磁盘满）时异常穿出 `with`、跳过 unlink，永久残留 `config.ini.<pid>.tmp`。`config_io.py:110` 注释声称「实现已下沉到 `src.utils.atomic_write_text`（唯一实现）」——对 `config_io` 成立，但 `web_config` 仍持有第二份完整实现，**这正是本仓反复登记「同源信息散写多点 → 半修复」结构性成因的最新实例**。Windows 上 `chmod` 仅影响只读位，故本地主平台看不出差异，属典型「本地绿、容器里漏」。
- **修复**：删除 `web_config` 的本地副本、改调 `utils.atomic_write_text`（实测 `web_config` 目前只依赖 stdlib + `src.config_bool`，若为避免依赖链则至少把「mode 回灌 + fsync + `mkstemp` + 写失败清 tmp」四点补齐），并让 `config_io` 的「唯一实现」陈述与代码一致。
- **置信度**：高 ｜ **类别**：安全

#### SEV-2212 ｜ `send_email` 的 TLS 会话完全不校验服务器证书：邮箱授权码可在「已加密但未认证」链路上被取走（已实测）

- **位置**：`msg_push.py:207-225`（`SMTP_SSL` 与 `starttls` 两条路径均不传 `context`）
- **证据**：

```python
            smtp_obj = smtplib.SMTP_SSL(email_host, port, timeout=10)
```
```python
                _ = smtp_obj.ehlo()
                _ = smtp_obj.starttls()
                _ = smtp_obj.ehlo()
```

- **实测**（本机 venv，CPython 3.14.7）：

```
stdlib is unverified ctx: True
verify_mode: 0  check_hostname: False
SMTP_SSL default ctx: True      # SMTP_SSL.__init__ 回落 _create_stdlib_context
starttls default ctx: True      # SMTP.starttls 同样回落
```

- **影响**：不传 `context` 时 smtplib 回落到 `ssl._create_stdlib_context()`，而它**就是** `ssl._create_unverified_context`——`cert_reqs=CERT_NONE`、`check_hostname=False`。攻击者只要在用户到 `smtp_host` 的链路上呈递任意自签证书即可解密整段会话，拿到 `login_email`/`email_pass`（邮箱授权码等同口令）以及通知正文里的房间地址。`open_ssl=True` 是函数默认值，即 465 端口这条**默认**分支同样不设防。`MI-24` 只处理了「非 SSL 分支明文」，而 STARTTLS 升级不带校验是同一件事的另一面。故障形态完全静默：推送成功、日志无异常。
- **修复**：`ctx = ssl.create_default_context()`，同时传给 `SMTP_SSL(..., context=ctx)` 与 `smtp_obj.starttls(context=ctx)`——**两条都要改**（本仓 `F-12` 已记载「只改一条即出现口径分叉」）；确需放行自签时走显式配置项并 `logger.warning`，不要默默放宽。
- **置信度**：高（stdlib 默认值实测 + 调用形态静态可判）｜ **类别**：安全

#### SEV-2213 ｜ 本地打包把 `config/config.ini`（真实凭据）整目录复制进对外分发的 zip

- **位置**：`build_exe.py:202-207`（复制）+ `build_exe.py:875-883`（压缩，无任何过滤）
- **证据**：

```python
    cfg_src = PROJECT_ROOT / "config"
    if cfg_src.is_dir():
        cfg_dst = RELEASE_DIR / "config"
        _ = shutil.copytree(cfg_src, cfg_dst, dirs_exist_ok=True)
        print(f"[build] 已复制 config/ -> {cfg_dst}")
```
```python
    zip_path = Path(shutil.make_archive(str(zip_base), "zip", DIST_DIR, APP_NAME))
```

- **影响**：`AGENTS.md`「凭据与敏感配置红线」把 `.gitignore` 与 `.dockerignore` 两道外发通道都堵了，但**打包链路是第三条外发通道且完全没有排除**：`python build_exe.py`（README 与 AGENTS 记录的标准本地命令）之后，`make_zip` 把发布目录整棵树压缩，`config/` 原样入包。含 Cookie / 代理 / Web 口令的 `config.ini` 与含房间列表及内嵌 query 凭据的 `URL_config.ini` 会随 zip 分发给下载者或在内网互传。CI 侥幸安全（checkout 里没有 `config/`），但**在 CI 机器上跑过一次录制的目录**同样中招。危害等级与同文件「ffmpeg/node 缺哈希即终止构建」的严肃程度完全不成比例——前者保护的是维护者的账号，后者保护的是用户的机器。
- **修复**：`copy_external_binaries` 只复制脱敏模板（按 README 默认块生成，或逐键剔除落入 `web_config` 敏感键正则的项），`URL_config.ini` 一律像 `_prepare_url_config()` 那样重写为注释样例；并在 `make_zip` 前**断言发布目录内不存在这两份文件**（存在即非零退出），与 `.dockerignore` 口径同源。
- **置信度**：高 ｜ **类别**：安全

#### SEV-2214 ｜ 小红书：解析重定向落地页后，把用户 Cookie 与会话 `sid` 发往响应决定的任意主机

- **位置**：`src/spider.py:2154-2174`
- **证据**：

```python
        "xy-common-params": "platform=iOS&sid=" + _read_xhs_sid(),
    }
    if cookies:
        headers["Cookie"] = cookies

    if "xhslink.com" in url:
        url_result = await async_req(url, proxy_addr=proxy_addr, headers=headers, redirect_url=True)
        if isinstance(url_result, str):
            url = url_result
```

  随后第 `2174` 行用**同一份 headers** 对新的 `url` 再发一次请求。
- **影响**：`url` 被**响应决定的**重定向地址整体替换，其后无任何 host 判定（`utils.is_safe_http_url` 只约束 scheme）。短链的跳转目标由分享链接的制造者选择，而本项目的房间地址正是用户从互联网粘贴进 `URL_config.ini` 的——一条恶意 xhslink 链接即可让录制器向任意 http(s) host:port 递送用户登录 Cookie 与 `xy-common-params` 会话凭据；同一请求还会解析落地页 HTML 的 `__INITIAL_STATE__`，被解析内容亦由攻击者控制。既是凭据外泄也是内网 SSRF。
- **修复**：跳转后校验落地页 host 落在 XHS 域名白名单（`xiaohongshu.com`/`xhslink.com`/`xhscdn.com`）内，否则丢弃跳转结果或剥掉 `Cookie`/`xy-common-params` 再请求；与本文件 `_shopee_host_suffix` 的「重建到固定 host」做法对齐。
- **置信度**：高 ｜ **类别**：安全

#### SEV-2215 ｜ B站弹幕 WS 的连接主机完全取自远端 `getDanmuInfo`，用户登录 Cookie 随之发往任意主机

- **位置**：`src/platforms/bilibili.py:66-79`；上游 `src/spider.py:2102-2109`、`2121`
- **证据**：

```python
            self._ws = WsClient(
                url=f"wss://{host}/sub",
                backup_url=f"wss://{backup}/sub" if backup else None,
                ...
                headers={"cookie": cookie} if cookie else None,
```

- **影响**：五个弹幕平台里**只有 B站的握手目标是远端可写的**（huya/douyu/twitch/douyin 的 `SERVER_URL` 均为硬编码常量，grep 可证）。`hosts` 来自 `self._args["host_list"]`，其生产链路是远端 JSON 字段 `h.get("host")` 原样入列；`cookie` 即用户的 `bili_cookie`（SESSDATA/bili_jct）。因此任何能影响一次 `getDanmuInfo` 响应主体的角色（上游被投毒、或用户设置「是否禁用SSL证书验证」后链路上任意一跳可改写响应）都能把用户凭据定向到自己的 `wss://` 主机；`host` 未做字符校验，`evil.com:443/x?` 这类值连路径都能改。属典型「其它四个平台天然没有这个面」的半覆盖缺口。
- **修复**：连接前按主机名白名单过滤（`.bilibili.com` / `.bilibililive.com`，并拒绝含 `/ ? @ ` 与空格的值），不在白名单的 host 既不连接也不带 `cookie` 头；过滤放在**消费侧** `bilibili.py`，避免其它调用方绕过。
- **置信度**：高 ｜ **类别**：安全

#### SEV-2216 ｜ `async_req` 把 ImportError 级的环境/依赖故障吞成空响应：本机实测 `h2` 缺失即全部平台静默不可解析，而 SOCKS 代理是声明性必现缺口

- **位置**：`src/async_http.py:253`（`http2: bool = True` 默认）、`:267` 与 `:66-72`（构造 `AsyncClient`）、`:301-323`（`except Exception` → `""`）；`src/web_config.py:546-548`（放行 socks）、`requirements.txt:24`
- **证据**：

```python
    return httpx.AsyncClient(
        proxy=proxy_addr,
        timeout=timeout,
        verify=verify,
        http2=http2,
        limits=_httpx_limits,
    )
```
```python
    except Exception as e:
        ...
        logger.debug(
            i18n.tr("async_req 请求失败: {masked_url} - {type_name}: {e}", ...)
```

- **实测**（本工作区 venv）：

```
h2 FAIL ModuleNotFoundError        socksio FAIL ModuleNotFoundError
AsyncClient(http2=True) RAISES ImportError: Using http2=True, but the 'h2' package is not installed.
socks5 client RAISES ImportError: Using SOCKS proxy, but the 'socksio' package is not installed.
requirements.txt:24  httpx[http2]>=0.28.1        pyproject/requirements 内 grep socks -> 零命中
```

- **影响**：`_acquire_client` 的调用点落在外层 `try` 内（已核对行号），其 `except Exception` 把 `ImportError` 归一成 `return ""`、只留一条 **DEBUG** 级日志。两类触发路径：① **声明性缺口**——`web_config._PROXY_SCHEMES` 明确放行 `socks4/socks4a/socks5/socks5h` 且注释警告「不得收紧成只允许 http/https」，但 `socksio` / `python-socks` **既不在 `requirements.txt` 也不在 `pyproject [project.dependencies]`**，故任何配置 SOCKS 代理的用户 124+ 处 `async_req` 全部空响应 → spider 判成「HTTP 200 + 空响应体 = 疑似风控」→ 该平台 100% 无法录制，而日志里只有一句 debug。② **运维触发**——`AGENTS.md`「venv 依赖修复分级处置」的三级命令 `pip install --ignore-installed --no-deps -r requirements.txt` 因 `--no-deps` **不会物化 `httpx[http2]` extra**，照该文档执行恢复后即得到本工作区当前的状态：`h2` 缺失 → 因为 `async_req` 默认 `http2=True`，**全部平台解析静默失败**。由于单测全部打桩网络层、门禁不含真实请求，这一状态在 8/8 全绿下完全不可见。
- **修复**：① 把 `socksio` 写进两份清单（或将 `_PROXY_SCHEMES` 收窄到实际支持的集合，两处口径同源）；② `async_req` 对 `ImportError`/`ModuleNotFoundError`/`httpx` 的 `UsageError`/`ValueError` **升为 warning 且每进程每种根因只报一次**（这是配置/环境错误，不是风控信号，绝不可与空响应同形）；③ `http2=True` 首次 `ImportError` 后把模块级开关置 False 并降级重跑；④ 建议加一条启动自检：探测 `h2`/`socksio` 是否可用并在缺位时明确告警——本仓「依赖缺失表现为收集期 ImportError」的既有经验条目应据此更新。
- **置信度**：高（两条失败均已本机实测）｜ **类别**：安全（可用性 + 静默降级）

#### SEV-2217 ｜ 弹幕 WS 的 `str(e)` 原样交给 `on_close`/`on_reconnect`：代理凭据（`user:pass@host`）落进轮转日志

- **位置**：`src/ws_client.py:267-281` 与 `:282-296`；消费端 `src/collector.py:489-499`
- **证据**：

```python
            except Exception as e:
                self._ws = None
                if self._stopped:
                    break
                self._reconnect_count += 1
                if self._reconnect_count <= self.max_reconnect:
                    if self._on_reconnect:
                        self._on_reconnect(str(e))
```
```python
                if self._on_close:
                    self._on_close(f"重连超过最大次数，与服务器断开连接: {e}")
```

- **机理与影响**：websockets 17 的异常文本自带代理原串（`.venv/.../websockets/exceptions.py:202-203`：`return f"{self.proxy} isn't a valid proxy: {self.msg}"`），而 `collector._on_close` 把 `reason` 直接 `logger.debug` 并写进监控枢纽，全程无 `mask_credentials`。这与 `WD-01` 已在 `async_req`/`sync_req`/`cookie_cache` 三处修掉的是同一形态，**本文件是唯一漏网的出口**。触发条件是「代理带凭据 + 代理侧报错」：`_PROXY_SCHEMES` 允许含 userinfo 的形态，且 `src/platforms/twitch.py:51-58` 在无显式代理时还会 `urllib.request.getproxies()` 取系统代理（macOS/Linux 的 `http_proxy` 常带 `user:pass@`）。凭据因此进 `logs/streamget.log`（300KB 轮转保留多份 = 长期落盘）并显示到 Web/GUI 监控页。
- **修复**：`WsClient` 把异常文本交给回调前先 `reason = utils.mask_credentials(str(e))`；或在 `collector._on_close` 兜一道并约定「回调文案必须已脱敏」。
- **置信度**：中（上游异常文本形态已 grep 到实现；仅代理报错时显现）｜ **类别**：安全

### 3.3 发布链与供应链（1 项）

#### SEV-2218 ｜ Windows 运行期新增第二条 ffmpeg 自动下载源（BtbN master，仅 TOFU），违背同日定稿的 AGENTS 红线；而守护该红线的回归锁看不见它

- **位置**：`src/ffmpeg_install.py:394-425`（架构分流）+ 全新未跟踪模块 `src/ffmpeg_master_download.py`（402 行）；锁在 `tests/test_ffmpeg_install.py:601-616`
- **证据**（新增源与准入判据自相矛盾）：

```python
def _candidate_urls(arch: str) -> list[str]:
    base = f"ffmpeg-master-latest-{arch}-gpl.zip"
    return [
        f"https://fyhub.cn/FFmpeg/latest/{base}",
        f"https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/{base}",
    ]
```

  该模块头第 17-28 行自证：「fyhub.cn 对这两个直链返回『下载验证』HTML 页…其 .sha256 文档也返回 404」「由于这类滚动构建无权威哈希文档，完整性只能走 TOFU（首次信任）缓存」。
- **冲突条款（唯一事实源）**：`AGENTS.md`「构建产物、依赖与运行时基线」②：「**Windows 运行期只有 gyan.dev 一条自动路径**——蓝奏云个人网盘兜底…已于 2026-09-22 **整体删除**，**新增任何第二条 Windows 下载源前必须先满足本条②的『官方公布哈希』判据**，否则等于把 P-1 换来的安全性退回下一行。」master 源恰恰**不满足**该判据，却是**默认开启**（无 env 门控、无确认）。
- **影响**：① 可达性上这不是稀有分支——代码注释自陈的动机就是「国内访问 gyan.dev 慢/被阻」，于是对目标受众而言**弱校验路径是常走路径**；下载产物被 `os.environ["PATH"]` 前置并以子进程方式执行（`ffmpeg_master_download.py:371-379`），危害半径是全部 Windows 用户。② TOFU 基准是与产物**同目录的旁路文件**，首次下载即把当次哈希记为可信基准（`:269`），因此「最危险的首次安装」那一次没有任何可比对期望值——攻击者先到先得即永久合法；而 `AGENTS.md` 对 P-1 的表述正是「把 TOFU 当默认路径等于最危险的首次安装没有任何校验」。③ **回归锁结构性失明**：`test_module_exposes_exactly_one_download_url` 只 `ast.parse` `src/ffmpeg_install.py` 一个文件、取其 `http*` 常量，新源在**另一个模块**，故恒绿；该用例注释（`:596-598`）却声称「按 URL 常量集合而非 lanzou 字样判定，换成任意别的镜像名也拦得住」。④ 同一文件模块头 `44-50` 行仍写着「现在 Windows 只有 gyan.dev 一条自动路径，失败即给出手动安装提示」，与 `392-440` 的实现直接互斥。⑤ `_candidate_urls` 把**个人镜像** `fyhub.cn` 排在权威上游 GitHub 之前，一旦该镜像哪天真的直出文件，就会优先于上游被使用。
- **修复**：三选一，但必须由维护者决策而非审查侧放宽——(a) 把 master 路径改为显式开启（沿用被删蓝奏云那套开关语义：默认关、开启必须 warning 落盘）；(b) 为其接回「官方公布哈希」判据（BtbN 的 `latest` 别名无可核对公布值则不得作为默认自动源）；(c) 保持现状但把 AGENTS ② 与 `ffmpeg_install.py:44-50` 的陈述改成与实现一致。无论何种处置，都须把 GitHub 排在任何镜像之前，并把锁的判定范围从「单文件 AST」扩成「运行期可达的全部下载常量集合」（可遍历 `src/` 下所有模块的 `http*` 字面量并对照白名单）。
- **置信度**：高（两个独立取证线同判；条款与代码均可逐字核对）｜ **类别**：安全（供应链）

### 3.4 门禁与测试可信度（8 项）

> 本节是本报告的重心所在：以下每一条都发生在**门禁全绿**的前提下。

#### SEV-2219 ｜ `run_gates.py` 的 pytest 兜底丢弃退出码、吞掉 stderr：整套测试崩溃或未跑也报「门禁全绿」

- **位置**：`scripts/run_gates.py:336-353`（判据）与 `:443-455`（消费）；同形态见今日 `.github/workflows/ci.yml` 新增的两条 `Gate pytest warnings summary` 步骤
- **证据**：

```python
    proc = subprocess.Popen(
        [sys.executable, "-m", "pytest", "-q"],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        ...
    _ = proc.wait()
    dur = time.monotonic() - t0
    if "= warnings summary =" in out:
        return False, f"pytest warnings summary 非空 ({dur:.1f}s)"
    return True, f"pytest warnings summary 为空 ({dur:.1f}s)"
```

- **影响**：`proc.wait()` 的返回码被丢弃、stderr 被 `DEVNULL` 吞掉，判定只看 stdout 里有没有那行标题。pytest `rc=4`（用法错误 / 插件缺失）、`rc=5`（`tests/` 改名 → no tests ran）、`rc=2/3`（收集期 ImportError、内部错误）时输出里没有 warnings summary，于是返回 `True`，`main()` 打印 `[PASS] pytest warnings summary 为空` 并以 **0** 退出——而 pytest 根本没跑或全红。`run_gates.py` 是 `AGENTS.md`「完成定义」第 1 步的本地唯一入口，且 pytest **不在**「格式化命令」门禁块里（脚本 `442` 行注释自陈这一点），所以这里是本地回路上**唯一**一次跑测试。CI 侧新加的两条孪生步骤用 `set -euo pipefail` + `$(python -m pytest -q 2>/dev/null || true)`，`|| true` 与丢弃 stderr 造成同样的失败开放（本仓已记录「全量 pytest 偶发段错误 exit 139」与 `tests/_out_e2e` rmtree 竞态，两者都会让重跑崩在半路而 summary 缺失）。
- **修复**：取回退出码分层判定——`rc == 0` 再查 warnings；`rc in (1,2)` FAIL 并附 rc；`rc in (4,5)` 按「门禁本身没跑」返回 rc=2（与 `MIN-19` 口径一致）。CI 两步改为先断言 rc==0 再 grep，且不要 `2>/dev/null`；并发步骤的 3 个文件清单与上方步骤合并成一份事实源（当前是硬编码副本）。
- **置信度**：高 ｜ **类别**：可验证性

#### SEV-2220 ｜ 新增的 `test_official_failure_is_final` 走真实网络并具备破坏工作树能力，而它守护的锁看不见它要防的东西

- **位置**：`tests/test_ffmpeg_install.py:601-607`（用例）、`:609-616`（AST 锁）、`:25`（hermetic 约定）；关联 `src/ffmpeg_master_download.py:182-228`、`:345-379`
- **证据**：

```python
    def test_official_failure_is_final(self, monkeypatch: pytest.MonkeyPatch) -> None:
        calls: list[str] = []
        monkeypatch.setattr(
            ffmpeg_install, "install_ffmpeg_official_windows", lambda: calls.append("official") or False
        )
        assert ffmpeg_install.install_ffmpeg_windows() is False
        assert calls == ["official"], "官方源失败后不得再有第二条下载尝试"
```
```python
    def test_module_exposes_exactly_one_download_url(self) -> None:
        source = (Path(__file__).resolve().parents[1] / "src" / "ffmpeg_install.py").read_text(encoding="utf-8")
```

- **机理（三条独立缺陷叠加在同一条用例上）**：① 该文件第 25 行的 hermetic 约定是「所有 `requests.get/post` 都被替换成替身」，但**实测该文件无任何 `autouse` fixture**，约定靠每条用例手工 `monkeypatch.setattr(ffmpeg_install, "requests", ...)` 维持；本用例只 patch 了一个函数，而新代码接着调 `download_ffmpeg_master`，后者用的是 **`src.ffmpeg_master_download` 自己的 `requests`** —— 拦不住。② 在有外网的 runner 上，该用例会真下 ~190 MB 到 `execute_dir`（= `script_path` = `_app_root()` = 仓库根），写 `_ffmpeg_master.win64.<build_id>.zip.sha256` 基准，`shutil.rmtree(execute_dir/ffmpeg)` 后 copytree，并**永久改写进程级 `os.environ["PATH"]`**（`ffmpeg_master_download.py:374`，无还原）泄漏给后续用例；Linux CI 上装的是 win64 zip，`ffmpeg -version` 必失败 → 返回 False → `assert ... is False` **恰好通过**。即「绿色，但已破坏检出目录」。③ `609-616` 的 AST 锁只解析一个文件，新源在另一个模块，恒绿，而其注释（`:596-598`）声称该判据能拦住「任意别的镜像名」。
- **诚实边界**：本机**未执行**该用例——若执行且网络可用，就会触发②的 rmtree 分支（属破坏性动作）。判据是静态的：stub 目标与被调对象的模块归属不一致，加上 `autouse` 缺失，已由 grep 确证。网络被阻时探测失败会提前返回 False，这解释了本会话为何能在该用例存在的情况下全绿跑完整套。
- **修复**：先修 `SEV-2218`（该源是否该存在），再补结构防线——① 给本文件加 autouse fixture，把 `src.ffmpeg_master_download.requests`（及任何未来新下载模块的出站层）一并桩掉，并把「测试内不发真实网络请求」从注释升级为机检；② AST 锁改为遍历 `src/` 下所有模块的 `http*` 字面量并与白名单比对；③ `assert calls == [...]` 之外断言「无第二条源的**函数**被调用」，而不是只记录自己认识的那一个函数名。
- **置信度**：高（①②③均为代码事实；②的破坏后果为条件性）｜ **类别**：可验证性

#### SEV-2221 ｜ P-2 官方 GPG 验签层在真实构建路径上永不可达：装了 gnupg、写了登记表、跑了一次都没有

- **位置**：`build_exe.py:602-611`（唯一调用点）配合 `:456-470`（签名登记表）与 `:281-290`（钉定值）
- **证据**：

```python
    if _is_pinned(expected):
        if expected != actual:
            raise SystemExit(...)
        print(f"[build] {dest.name} SHA256 校验通过（{slot or dest.name}）")
        # 签名核验只在**哈希已过**之后做：对一份连内容都没核过的产物验签没有意义。
        _verify_official_signature(dest, slot, desc)
    else:
        # 仅本地路径可达（发布路径已在下载前终止）：打出实际哈希，供人工核对官方值后钉定
        print(f"[build][warn] {desc} 未钉定 SHA256，请核对官方值后填入 _PINNED_RUNTIME_SHA256：{actual}")
```

- **影响**：`_RUNTIME_GPG_SIGNATURES` **只登记** `macos-x64/ffmpeg` 与 `macos-arm64/ffmpeg` 两格，而实测这两格在 `_PINNED_RUNTIME_SHA256` 里的取值正是 `UNVERIFIED_PIN` → `_is_pinned()` 按形状判未钉定 → 发布路径在下载**之前** `SystemExit`，本地路径走 `else` 只打印哈希。也就是说 `_verify_official_signature()` / `_verify_gpg_artifact()` 在两条路径上都不会被调用，`AGENTS.md`「钉定之后还须过官方 GPG 验签…gpg 缺失即终止构建，不得降级放行」与 `build-release.yml` 专门安装的 gnupg 步骤全部是空转。讽刺之处在于：**evermeet 恰恰是「不公布 SHA256、只公布 `/sig` 签名」的那家**——唯一能用验签补上缺口的槽位，被「必须先过哈希」的顺序永久挡死；而 `448-450` 行注释自己就写着签名是**独立于哈希**的信任通道。
- **修复**：把验签从 `_is_pinned` 分支里提出来，改为「槽位在 `_RUNTIME_GPG_SIGNATURES` 中登记 → 无论哈希是否钉定都验签」（本地路径同样验，失败即终止）；并补一条用**出厂表**驱动 `_download_file` 的回归用例，锁「注册了签名的槽位必然触发验签」——否则本条会在下一次改动中第三次复现。
- **置信度**：高 ｜ **类别**：可验证性

#### SEV-2222 ｜ master 源的 TOFU 判定在「读不到基准」时失败开放：基准存在却读不出，仍继续安装未校验的二进制

- **位置**：`src/ffmpeg_master_download.py:242-250`（失败开放分支）；对照 `src/ffmpeg_install.py:222-252`（②类的正确降级形态）
- **证据**：

```python
    if hash_file.exists():
        try:
            expected = hash_file.read_text(encoding="ascii").strip().lower()
        except OSError as e:
            logger.warning(i18n.tr("读取 ffmpeg master SHA256 缓存失败，跳过校验: {e}", e=e))
            return
```

- **机理与影响**：`hash_file.exists()` 为真表示**本机已有一份可信基准**，此时读不出来（编码损坏、目录权限变更、被杀软隔离、读到 0 字节）本应等价于「不可信 → 拒装」，实现却是 `return`——调用方 `download_ffmpeg_master` 把 `None` 当作校验通过，继续解压并 `shutil.copytree` 到 `execute_dir/ffmpeg`、前置进 `PATH`、随后以子进程执行。这正是本仓反复明令禁止的「用捕获异常后跳过让它变绿」形态（`MID-63` 之于 isort、`MID-68` 之于 i18n 门禁、`MIN-19` 之于 coverage，同一族）。它与 `SEV-2218` 是**两个可分别修复的缺陷**：`SEV-2218` 管「这条源该不该存在」，本条管「既然存在，它的唯一一道完整性检查可以在磁盘状态下静默失效」。另注：首次记账那一路（`:269-270`）也只用 `logger.debug`，而 `ffmpeg_install.py:250-252` 的同类降级按要求用 warning——两处严重度口径在同一天的两份实现里就不一致。
- **修复**：读基准失败即 `raise IntegrityError(...)`（与同函数的哈希不符分支同样删除产物并拒绝安装）；首次记账升级为 warning 并写明「本次安装无可比对期望值」；把「exists 但不可读 = 拒装」写进 `AGENTS.md` ② 类判据，避免下一个下载模块重抄这段。
- **置信度**：高（控制流直接可读）｜ **类别**：安全

#### SEV-2223 ｜ 全仓唯一「重新实现被测逻辑」的测试文件仍在计数，且它是抖音限流器的唯一「覆盖」

- **位置**：`tests/test_concurrency.py:21-56`、`69-94`、`128-170`
- **证据**：

```python
    def test_lock_prevents_duplicate_fetch(self) -> None:
        fetch_count = 0
        lock = threading.Lock()
        cached: str | None = None

        def get_credential() -> str:
            nonlocal fetch_count, cached
            if cached:
                return cached
            if not lock.acquire(blocking=False):
```

- **影响**：实测该文件的 import 清单只有 `asyncio`/`threading`/`time`/`unittest.mock`/`pytest`——**不引用任何 `src.*`**。把 `src/ttwid.get_ttwid()`、`src/cookie_cache`、以及 `src/stream_select.py:1183-1193` 的 `_douyin_rate_limit` **整个删除**，本文件 5 条用例仍全绿。`grep -rn "_douyin_rate_limit\|douyin_min_interval" tests/` 除该文件一条**注释**外零命中，即该限流器（`main.py:1541` 生产在用、`douyin_min_interval` 默认 3.0s）实际无任何真实断言。删掉 `with main.douyin_rate_lock:` 或把其中的 `time.sleep` 改成 no-op 后，80+ 房间并发 hammer 抖音 API 触发风控（表现为「明明在播却持续漏录」），测试面毫无反应。`test_lock_is_threading_lock` 还是恒真式（`isinstance(threading.Lock(), type(threading.Lock()))`）。真实版本已由 `tests/test_concurrency_rate_limit.py` 承担（`AGENTS.md`「测试不得自实现被测逻辑」条目点名的就是它），本文件属**被取代后遗留却仍在门禁计数**。
- **修复**：删除 `TestThreadSafeCredential`/`TestRateLimit`/`test_shared_credential_single_source`/`test_lock_is_threading_lock`（`test_ttwid_module_pattern` 保留，它是唯一驱动真实模块的一条）；把速率限制改写成驱动真实 `src.stream_select._douyin_rate_limit()`（只打桩 `main.douyin_*` 三个全局与 `time.sleep` shim）并断言「第二次调用确实 sleep ≥ `douyin_min_interval`」；在 `tests/test_test_hygiene.py` 增一条规则「用例内不得定义与生产同名的锁/缓存/限流实现」。
- **置信度**：高 ｜ **类别**：可验证性

#### SEV-2224 ｜ 黄金快照的 `check_subprocess` 替身收下 `platform` / `danmaku_args` 却只记录命令：保存类型分支漏传弹幕参数无人能拦

- **位置**：`tests/test_start_record_command_golden.py:328-340`（替身）与 `:396-399`（导出面）
- **证据**：

```python
    def _check(
        record_name: str, record_url: str, ffmpeg_command: list[str], record_save_type: str,
        custom_script: str, platform: str | None = None, danmaku_args: dict[str, Any] | None = None,
    ) -> bool:
        cap.commands.append(list(ffmpeg_command))
        return True
```

- **影响**：把 `main.py:3790` / `3964` / `3996` 三处 `_run_ffmpeg_record(...)` 调用中任意一处的实参改成 `None`（即 `_run_ffmpeg_record(..., platform, None)`），`main._run_ffmpeg_record` 便以 `danmaku_args=None` 调 `check_subprocess` → 该保存类型下走 `main.py:1026` 的「弹幕跳过」分支，**该房间从此只出视频不出 SRT**。20 例黄金全绿（命令字节未变）；`tests/test_danmaku_wiring.py` 全部直接调 `check_subprocess`、不经 `start_record` 分支，也拦不到。**该缺口已由 `CODE_REVIEW_2026-09-21.md:482` 以高置信登记，至今未落地**（属本轮「上一轮结论未执行」的最重一条）。附带一条同源缺陷：`_setup_case` 里 `get_effective_ssl_verify` 的 patch 被缩进进 `for ck in _COOKIE_GLOBALS:` 循环体内，依赖 cookie 清单非空才生效。
- **修复**：`_Cap` 记录 `{"command": ..., "platform": platform, "danmaku_args": danmaku_args, "save_type": record_save_type}` 并 `GOLDEN_REGEN=1` 重生成基准；把 ssl patch 移出循环体。
- **置信度**：高 ｜ **类别**：可验证性

#### SEV-2225 ｜ 18 处用例仍整体改写 stdlib 模块本体，而禁止它的卫生门禁看不见字符串形态 patch（其注释还声称「本仓未使用」）

- **位置**：`tests/test_main_fixes.py:172-176`、`290`；`tests/test_spider_fixes.py:83-101`；`tests/test_stream_select.py:995-1005`；判据缺陷在 `tests/test_test_hygiene.py:100-120`
- **证据**：

```python
        with patch("subprocess.Popen", return_value=FakeProcess(returncode=0, out=b"ok output")) as mock_popen:
            out = main_mod._run_ffmpeg_checked(["ffmpeg", "-version"])
```
```python
            # MI-15 后 spider 不再直接 import subprocess（已改用 utils.run_node_script_async），
            # 改打标准库模块本身：与原先打 sp.subprocess.run 语义等价（同一模块对象），
```

- **影响**：`patch("subprocess.Popen")` / `patch("subprocess.run")` 的替换目标是**全进程唯一的 stdlib 模块对象**，`with` 窗口内同进程的 harness safe-delete 守卫线程、loguru enqueue 线程、coverage 全部拿到假实现——`AGENTS.md`「patch `main.py` 的 subprocess 必须替换 main 的全局引用」点名的正是这一形态及其症状 `SAFE_DELETE_BULK_GUARD_ERROR`。实测该形态共 18 处（另有 `patch("src.stream_select.time.sleep")` 13 处，把全进程 `time.sleep` 换成 MagicMock，使退避/节流类断言的时序前提被这些用例自己破坏）。`test_spider_fixes.py:94-96` 的注释还为它作了「语义等价」的论证——**等价于被测面、不等价于影响面**。而卫生门禁的 `_is_setter` 只认 `setattr`/`patch.object`，字符串形态一律放过，其注释「本仓未使用」已与现网相反。
- **修复**：三处统一改成仓内既有范式（`shim = types.SimpleNamespace(**vars(subprocess)); shim.Popen = ...; monkeypatch.setattr(<module_under_test>, "subprocess", shim)`，见 `tests/test_record_failure_feedback.py:59-84`）；`time.sleep` 同理走模块命名空间 shim；删掉 `test_spider_fixes.py:94-96` 的错误论证注释；R1 增判字符串形态（按 `.` 逐段解析，末段属 stdlib 模块名且首段不是被测模块即违规），并把「违规见证 + 合规反向见证」补到 R4。
- **置信度**：高（计数与门禁判据均实测）｜ **类别**：可验证性

#### SEV-2226 ｜ `src/sync_http.py` 整模块在生产链路中不被导入，而 `AGENTS.md` 的两条安全辩护都以它为前提

- **位置**：`src/sync_http.py:43-48`（自述）；`AGENTS.md`「依赖管理」urllib3 条、「已知坑」F-12 条；`src/stream_select.py:1004`
- **证据**：

```python
# 调用面核实（2026-09-14，修正 2026-09-12 审查的风险描述；2026-09-22 修订：调用点计数已漂移，删除具体数字）：
# sync_req 调用点**全部位于 src/spider.py**（平台解析 / 流地址获取），
```

- **实测**：`grep -rn "sync_req(" `（排除 `.venv`/`.workbuddy`）只命中 `src/sync_http.py` 的定义与 `tests/test_sync_http.py` 的 27 处；`src/spider.py:69` 导入的是 `from .async_http import async_req`，全文不 import `sync_http`；`sync_http` 的唯一真实 importer 是 `src/weverse_auth.py:10`（且用的是 `session()`），而 `refresh_weverse_token` 自身零生产调用点、全仓无 weverse 平台分派；`close_session()` 同样零调用点。**注释今天刚被编辑过（去掉漂移的计数），但「全部位于 src/spider.py」这一核心陈述原样保留。**
- **影响**：本轮网络层审查的最高优先级目标（TLS 双闸是否漏一侧、代理是否绕过 `handle_proxy_addr`、`redirect_url` 语义）**全部落在一个永不被导入的模块上**，其真实风险为零，而文档给出的风险画像恰好相反：① `AGENTS.md` F-12 把它写成事实基准；②「依赖管理」用同一前提为 `urllib3>=2.7.0` 的显式声明辩护（真实活跃的 requests/urllib3 路径是 `src/ffmpeg_install.py`、`src/node_install.py`、以及今天新加的 `src/ffmpeg_master_download.py`）；③ `src/stream_select.py:1004` 把 `sync_http:179` 列为已接线的出站面。按 `AGENTS.md` 自己的「被证伪的事实性陈述必须就地改正、不得保留错误版本」口径，三处都属应改正项。附带两条**只存在于死码里、改回活码即生效**的缺陷：`sync_req` 未接 `is_safe_http_url`（`async_req:237` 与 `get_response_status:352` 都接了），其 urllib 分支经 `build_opener` 默认带 `FileHandler`，`file://` 可读本地文件；以及无上限解压 `gzip.decompress(_resp.read())`，与 `ws_client.decompress_limited`（`MI-01`，8 MiB 上限）口径相反。`tests/test_sync_http.py` 的 27 条用例因此是在为一个不被链接的模块提供「已加固」的错觉。
- **修复**：二选一并写回 `AGENTS.md`——(a) 删除 `sync_http.py` 与 `weverse_auth.py`（连同各自回归锁与 F-12/urllib3/stream_select 三处陈述一并改正，按口径保留一行带日期的历史注）；(b) 若保留待接线，则在 `sync_req` 入口补 `is_safe_http_url` + 限流解压，并把文档陈述改成「当前无生产调用点」。同时把 `sync_req` 的「F-12 两侧同传 ssl_verify」这一既有不变量的检查改挂到真实的出站层（`async_http`）上。
- **置信度**：高（调用图 grep 实测）｜ **类别**：可验证性

### 3.5 Web 面板可用性（2 项）

#### SEV-2227 ｜ 页面隐藏一次后仪表盘轮询永不自愈：`!sseStopped` 读的是刚被 `stopSSE()` 置位的标记

- **位置**：`web/app.js:1518-1529`（配合 `:684-690`、`:78`、`:653`）
- **证据**：

```javascript
        document.addEventListener('visibilitychange', function () {
            if (document.hidden) {
                stopSSE();
                stopDanmakuPolling();
            } else {
                if (!sseStopped) startSSE();
```
```python
    function stopSSE() {
        sseStopped = true;
```

- **影响**：`stopSSE()` 无条件写 `sseStopped = true`，所以 `else` 分支的 `if (!sseStopped)` **恒为假**——`/api/status` 轮询在第一次「切走标签页 / 最小化窗口」之后再也不会恢复，直到用户手点一次 tab。用户回到面板看到的是最后一次成功采样的数据：已录时长不再增长、监测数冻结、`#engine-warning`（引擎死亡横幅）永不出现、`recording_enabled` 与实际态脱节。同一处理器的弹幕分支用的是视图 id 判定（正确写法），恰好证明这里是笔误而非设计；`WD-10` 注释自陈的目的「回到前台立即恢复并补拉一次，避免用户看到陈旧数据」完全未达成。
- **修复**：把「是否应当运行」与「当前是否已停」解耦——新增 `sseWanted`（`startSSE` 置真、`showLogin`/登出置假），`hidden` 时只 `clearTimeout` 不改 `sseWanted`；恢复分支按 `if (sseWanted && 当前视图是 dashboard) startSSE()`。补一条前端 `.mjs` 用例：`visibilitychange` 两轮后断言 `/api/status` 请求计数继续增长。
- **置信度**：高 ｜ **类别**：正确性

#### SEV-2228 ｜ `GET /api/status` 以 HTTP 200 返回 `{"error":"status_unavailable"}` 被渲染成「引擎正常 / 无录制 / 无错误」的假绿面板

- **位置**：`web/app.js:693-703`、`742-756`；后端 `src/web_api.py:1146`、`1179`
- **证据**：

```python
        snapshot = _read_engine_status()
        except Exception as e:
            _log_internal_error(_STATUS_ERROR_CODE, e)
            return {"error": _STATUS_ERROR_CODE}
```
```javascript
        var enabled = s.recording_enabled === true;
        var engineAlive = s.engine_alive !== false;
```

- **影响**：采样失败时返回 `{"error": ...}` 且 HTTP 状态仍是 200，于是 `api()` 的 `!resp.ok` 与轮询的 `.catch` 都不会触发；`renderStatus` 不检查 `error`，而 `engine_alive !== false` 对 `undefined` 求值为**真** → 告警横幅隐藏、「开始录制」按钮**可点**、`recording` 缺省显示「暂无录制」、四张卡片全是 `-`。运维看到的是「一切正常、只是没人在录」，真实情况是引擎状态完全取不到。同一族的还有 `stale:true`（`MID-34` 专门发明的陈旧标记，前端未消费）与 `/api/danmaku` 的 `error:"danmaku_unavailable"`——后者更糟：`rooms:[]` 会点亮 `#danmaku-hint`，把后端故障提示成「请去配置里开启弹幕监控」。
- **修复**：`renderStatus` 首行判 `if (s && s.error) { 显示「状态不可用」专用文案并禁用两个录制按钮; return; }`；`stale === true` 时在仪表盘加「数据滞后」角标；`renderDanmaku` 对 `data.error` 走独立文案、不点亮 `danmaku.hint`。
- **置信度**：高 ｜ **类别**：可验证性

## 四、中等问题（P1，65 项）

> 表内「位置」为当前工作树行号；「影响」为后果要点，凡与第三章同族但**落点不同**的条目均独立计数，完全重复者已在第三章合并（合并说明见 `MID-2211`、`MID-2227`、`MID-2233` 的括注）。

### 4.1 录制主链路与房间线程（`main.py`）— MID-2201 … MID-2209

| 编号 | 位置 | 问题 | 影响 | 修复方向 | 置信度 |
| --- | --- | --- | --- | --- | --- |
| MID-2201 | `main.py:4824-4827` + `4891-4899` | `running_list.append` 与 `monitoring += 1` 发生在 `Thread.start()` **之前**，而清理只在线程 `finally` | `start()` 抛 `can't start new thread`（本仓已把它当现实可达点）后该 URL 被 `4816` 的 `not in running_list` 永久拦死直到重启；`monitoring` 与 `set_active_count` 长期虚报一个活跃房间，抬高自适应容量 | start 失败即 `remove_room_from_running` + `create_var.pop` + 明确告警后 `continue`；或改为「start 成功后再登记」 | 高 |
| MID-2202 | `main.py:3850-3859`（对照 `3695-3697`） | 直下分支的字幕线程在 `recording.add` **之前**启动，与自身 SEV-09 注释「与 ffmpeg 路径时序对齐」相反（ffmpeg 路径是先登记再起线程） | `generate_subtitles` 是「先写一条 SRT 块再判 `record_name in main.recording`」，子线程抢到锁即判为未录制并退出 → 产物只有 1 个块而录像继续数小时，**无告警** | 把登记块整体移到 `if create_file:` 之前（与 ffmpeg 路径同构），并改正注释 | 中 |
| MID-2203 | `main.py:4636-4650` + `4907-4912` | 主循环每轮先把 `url_comments`/`line_list`/`url_line_list` 重绑为空集再逐步重建，异常直接落外层 except 且**不回填** | `url_comments` 是房间线程、`check_subprocess`、`direct_download_stream`、`clear_record_info` 判「用户已禁用该房间」的唯一依据；解析中途抛错则整轮为空 → 被注释/删除的房间继续录制、`monitoring` 不再递减。正常路径也有毫秒级窗口 | 解析到本地临时 set、整轮成功后一次性替换（与 MID-09 对 `config` 的手法相同）；失败分支保留上一轮集合 | 中 |
| MID-2204 | `main.py:3411-3419` + `3486-3524` | 解析失败分支不 `continue`，控制流落到推送状态机；`start_pushed = False` 的复位与 `over_show_push` 同级 | 抖音「HTTP 200 + 空响应体」风控或网络抖动一轮 → 锁存被复位 → 下一轮成功即**重复发一条开播推送**（默认配置下 N 次抖动 = N+1 条推送）；`over_show_push=是` 时还会出现「已结束→正在直播中」的假告警对 | 失败分支末尾 `continue`，或加 `parse_failed` 标志使状态机只在真正拿到状态时迁移 | 高 |
| MID-2205 | `main.py:4079-4083`（对照 `3460-3465`） | 主播改名后 `room_state["name"]` 被覆盖成新名，旧 `record_name` 再没有任何地方传给 `room_stopped` | 弹幕枢纽 `_rooms` 里旧名条目永久残留（面板挂着「已失效直播间」及其旧统计直到重启），正是 AGENTS「弹幕监控房间须随录制线程退出而移除」条目要防的形态 | 改名成功分支同时 `get_hub().room_stopped(旧名, "主播改名")`；或 `room_state` 累积本线程注册过的全部名字、出口逐个清理 | 中 |
| MID-2206 | `main.py:3538-3544` + `4532` | 「只监测不录制」的等待按 `push_check_seconds` 逐秒倒数，而该值 `_safe_int` 只对**非数字**回退默认，`0`/负值是合法整数原样生效 | 填 0 即 `while` 一次不进、`continue` 又跳过轮末等待 → 整轮（熔断预检 + 网络解析 + `record_success` 采样）无间隔重复，多房间同平台时满速刷接口，正是本仓按节奏识别风控最怕的形态 | 与 `split_time`/`max_record_seconds` 同口径设下限（`max(..., 30)`）；`delay_default` 一并加下限 | 高 |
| MID-2207 | `main.py:932-941` + `1135-1145` + `1171-1182` | MID-N02 登记的 glob 失配（`rstr` 保留 `[` `]`，pathlib 当字符类）**叠加** MID-N04 新增的 `size < 0` 停滞判据 | 求和恒 `-1` → 走停滞分支，而 `_stall_since` 因增长路径永不达 → 健康分段录制**满 10 分钟即被终止** + `record_error(host)` 投假失败样本，且不转码、不清退避。该组已本机实测 `glob("主播[A组]_..._*.ts")` 返回空而文件确实存在 | 三处求和/匹配统一不走模式串：`iterdir()` + `name.startswith(base_stem + "_")` + 序号正则；并区分「观测失败」与「从未有产物」 | 高（已实测） |
| MID-2208 | `main.py:1003`、`1095-1097`、`1114-1115`、`1137`、`1151`、`1364` | 看门狗停滞、ffmpeg 快速失败、单次录制时长上限三套 elapsed 判据全用 `time.time()`，而全仓其余计时（调度器、凭据缓存、采集器、进程清理）一律 `time.monotonic()` | 时钟正向跳变（开机首次 NTP 校正、虚拟机快照恢复、改时区）→ 以「正常收尾」名义误切断录制（`record_success` 掩盖之）、或误判停滞并投假失败样本；反向跳变则让两个判据永不触发，CR-05 的「挂起 ffmpeg 恒持槽位」回归 | `check_subprocess` 内 elapsed 全改 monotonic（展示用时间戳保留挂钟），并补「把 `main.time.time` 桩成向前跳 7 小时」的回归锁 | 中 |
| MID-2209 | `main.py:667`（声明）+ `679-684` | 直下路径的 UA：`get_record_user_agent` 只对虎牙/B站返回值，而强制直下平台是 `["shopee","花椒直播"]` → 恒 None → httpx 发默认 `python-httpx/<ver>`；函数头注释却声称「请求头/cookie/UA 与 ffmpeg 录制路径保持一致」 | 「UA 双端一字不差」约定（探针与 ffmpeg 客户端指纹须一致）的第三端不一致；CDN 按 UA 风控时表现为 `请求直播流失败: … 状态码 403`，且直下不经 `select_source_url`，退避/换线路机制帮不上（代理侧缺口已由上轮 `补-N01` 登记，此处不重复计） | `headers["User-Agent"] = ua or MOBILE_UA`（从 `stream_select` import 同一常量，勿再抄字面量），并加静态锁断言该处必含 UA | 高（不一致）/中（CDN 反应） |

### 4.2 平台解析、签名与流地址（`src/spider.py`）— MID-2210 … MID-2226

| 编号 | 位置 | 问题 | 影响 | 修复方向 | 置信度 |
| --- | --- | --- | --- | --- | --- |
| MID-2210 | `spider.py:2711-2721` | `get_sooplive_tk` 挂 `_or_none` 可返回 None，aid 结果未判型即 `+ "?aid=" + cast(str, aid_token)`（`cast` 不做运行时转换） | aid 失败而 info 成功（风控按参数/节奏部分放行）时 `TypeError`，已取到的主播名与线路号一并丢失、被吞成未开播；同函数 `_info` 与游客路径都判了空 → 口径不一致 | 显式 `isinstance(aid_token, str)` 判空后再拼，且放在 CDN 分配请求之前以免白跑 | 高 |
| MID-2211 | `spider.py:2731-2732` + `2755-2759` | 注释称「-3002/-3004 都触发登录流程」，代码里 -3004 只复用既有 cookie、`fetch_data` 内无「票据被拒→登录重试」回退 | `[Cookie] sooplive_cookie` 过期后每轮拿同一份坏 cookie 失败，配置里的账号密码**永不被使用**，用户只能手工删项。（与 `SEV-2218` 同族但独立落点） | -3004 改为「先复用、仍失败则 `handle_login()` 一次并重试」，注释与实现收敛 | 中 |
| MID-2212 | `spider.py:3194`、`3707-3709`、同族待核 `3095` | 用 urllib 时代的 `"HTTP Error 400: Bad Request"` **文本**判风控/凭据失效，而 `async_req` 只返回 `response.text`、不 `raise_for_status`、失败回 `""` | 判据恒假：TTingLive 出口 IP 被封不再给「请更换代理」的可自助提示；PopkonTV 的 token 刷新只剩 body 内 `statusCd":"E5000` 一条（服务端若只用状态码表达即永不刷新凭据），而注释声称两者皆可 | 给 `async_req` 增加状态回传（或这三个调用点改走能拿状态码的接口），按 400/403 判定；或确认响应体确含该串后把注释改成实测结论 | 中 |
| MID-2213 | `main.py:2073-2082` × `spider.py:3967` × `stream.py:1164` | TwitCasting 回写读的是 `port_info.get("new_cookies")`，而 `get_stream_url` 在真正取到流时**新建** dict、不含该键 | 恰好在房间在播（唯一需要该会话 cookie 的场景）永不落盘 → 每 30-120s 重跑一次 `login_twitcasting` 明文账密 POST，放大风控/锁号风险，日志无异常。同函数群的 SOOP/Flextv 读的是 `json_data`，属漏改 | 改读 `json_data`（与 sooplive/flextv 同构）或让 `get_stream_url` 透传凭据类键；补「在播 + 登录成功 → 写入被调用一次」的锁 | 高（两独立分组同判） |
| MID-2214 | `spider.py:728-733` | `parsed_data["origin"]["main"]` 双层裸下标，而同函数 `694-719` 与姊妹函数 `873-875` 均已 `.get("main") or {}` | `origin` 存在但无 `main`（抖音 pull_data 已出现 `full`/`sdk` 变体）时 KeyError 被最外层吞成 `{"anchor_name": ""}` → **已完整解析好的 room_data 连同流地址一起作废**，此后每轮固定「网址内容获取失败」，抖音房间永久不录 | 与 `873-875` 同写法，结果为空时跳过 ORIGIN 注入 | 高 |
| MID-2215 | `spider.py:1530-1539` | YY `_loads_dict` 为空时只 `_warn_api_abnormal` 不 `return`，继续返回只含 anchor_name 的 dict | main.py 以 `anchor_name` 非空判「解析成功」并 `record_success` → YY 被风控的**每一轮都记成成功样本**，`PlatformBreaker` 失败阈值永不达、坏线路被无限重撞（AGENTS 明确禁止的形态） | 空响应分支按快手形态显式返回未开播 | 高 |
| MID-2216 | `spider.py:1725-1742` | WD-19 把 B站判定写成 `if json_data.get("code") not in (0, None)`，而 `None` 恰是「空 body / 响应不是 JSON（风控页）」经 `_loads_dict` 归一后的形态 | 最需要线索的那一类被划到「正常」侧 → `data_obj={}`、`live_status!=0`、`stream_list=[]` → 整轮**零日志**，WD-19 想消灭的「与主播没开播不可区分」在非 -352 的风控形态上依然存在 | `code is not None and code != 0` 才告警返回；`json_data` 整体为空时另落一条 `_warn_api_abnormal` | 高 |
| MID-2217 | `spider.py:1009-1017` | 注释称「用 print 而非 logger」而代码是 `logger.error`；且该 except 分支**不可达**（`async_req` 内部吞尽异常返回 `""`，见 `async_http.py:301-323`） | 网络抖动的真实走向是 `html_str=""` → 正则失配 → `ValueError` → 被下一层捕获并打印「Failed to parse JSON data」，**把网络/风控成因说成解析成因**，那条真正的抓取线索永不出现。同型死 except 另见 `1932-1948`（「room_init 失败」告警永不触发） | 删死 try/except，改对 `_get_str_response` 结果显式判空并落归因日志；修正注释 | 高 |
| MID-2218 | `spider.py:2128-2143` + `utils.py:418-423` | `_read_xhs_sid` 读 `[Cookie] xhs_session_sid`，但该键从未注册进 `config.ini` 与 README 模板 | 实测本机 `config.ini` 中 `[Cookie]`=1、`tiktok_guest_cookie`=1、`xhs_session_sid`=**0**，而 `read_ini_value` 对「节在键不在」发 `logger.warning`（MI-19 有意为之）→ 每个小红书房间每 ~120s 刷一条 warning，正踩 AGENTS「正常轮次刻意保持静默」；内置 sid 的 epoch 为 2024-07-28 却缺 MID-46 型「用了内置缺省且失败」告警（MID-50a 只补了覆盖入口，半条修复） | 把键补进 `config.ini` 与 README/README_EN 模板，或改走 `has_option` 语义的静默读取；镜像 TikTok 的失败告警 | 高（实测） |
| MID-2219 | `spider.py:1641-1655` | WD-19 新增的这条日志 `url={url}` 未过 `mask_credentials`（同文件 1016/1034/1048/1154 四处都过了） | 违反「URL/代理一律脱敏」红线；`logs/` 轮转保留多份 = 用户粘贴的带 token 查询参数长期落盘 | 改 `url=utils.mask_credentials(url)` | 高 |
| MID-2220 | `spider.py:5890-5898` | `_m_h5_tk` 用 `;` 锚定正则提取，而同一函数新写的写入侧 `dict_to_cookie_str` 是 `"; ".join(...)`、**不追加尾随分隔符**；同段上方刚新增边界正确的 `_cookie_str_to_dict`，读侧却未跟上 | 用户从浏览器复制的 cookie 若 `_m_h5_tk` 位于末位（无终止 `;`）：`if "_m_h5_tk" in cookie` 判真但 `findall` 命中 0 → `sign` 保持 `""` → mtop 必拒；合并回写后仍末位 → **两轮都签不上**，而收尾判定 `_m_h5_tk in Cookie` 又为真，于是静默返回未开播、连 WD-18 的 cookie 提示都不出 | 改用 `_cookie_str_to_dict(cookie_str).get("_m_h5_tk", "")`，取不到即视为无票据走既有换票分支；收尾判定同样用解析后的键集合 | 中 |
| MID-2221 | `spider.py:4842-4849` | 同一 headers 字典里并存 `"cookie"`（游客 `_did`）与 `"Cookie"`（用户透传）两个大小写键，httpx 不做大小写去重 | 该组用 `httpx.Client().build_request(...).headers.raw` **实测**请求里出现两条 header；RFC 6265 §5.4 要求 UA 不得发送多个 Cookie 头，取首个还是合并由各边缘节点自决 → 注释承诺的「调用方透传 cookie 时优先采用」不成立，用户配置的 `acfun_cookie` 可能被整体丢弃，部分 WAF 还会因重复 Cookie 回 400。全文件 5 处 `"cookie":` 字面量，**只有此处混用** | 统一为单键并合并（`headers["Cookie"] = f"_did={did}; {cookies}"`）；禁止同字典内两种大小写同名头 | 高 |
| MID-2222 | `spider.py:4816-4820`、`5268-5270`（对照 `469-479`、`2601`） | `get_play_url_list` 已被放宽为可返回绝对地址（`https://`/`http://`/`//host` 三类都收），但 ShowRoom/CHZZK 两个调用方仍假定全部相对路径做前缀拼接 | 绝对条目被拼成 `https://host/path/https://cdn/x.m3u8` 坏候选 → 多清晰度列表整体报废（画质下拉只剩一项或选档后校验失败）。同文件的 SOOP 已在 MID-47 改用 `urljoin` 并注释记录过同类事故 | 两处改 `urllib.parse.urljoin(m3u8_url, i)`（与 SOOP 一致），并在 helper 注释写明「返回值可能混合绝对/相对」 | 中 |
| MID-2223 | `spider.py:4468-4529` | ① `get_huajiao_sn` 零生产调用点（main.py 花椒只调 `get_huajiao_stream_url`，无反射调用）；② 其「瞬时网络故障」判据 `isinstance(e, (httpx.HTTPError, ...))` **恒假**（`async_req` 已把传输层异常吞成 `""`，故障到此处已是「页面没有 feed 数据」） | 注释宣称的「确认失效时把该 URL 注释掉」实际永不发生（死码掩盖）；而 2026-09-12 审查 6.3 那次加固**本身无效**——一旦被接线就是「断网一次即永久注释掉用户房间、重启不恢复」。另外该元组里 `httpx.TimeoutException ⊂ httpx.HTTPError`，第二判别项冗余 | 要么删除该函数与其写回分支（并同步 hardening 清单），要么改为「`_get_str_response(...) == ""` → 不写回」使网络故障与内容失效真正可分 | 高 |
| MID-2224 | `spider.py:5163-5165` | 知乎 `people/` 切分未剥 query 与子路径 | 分享链接普遍带 `?ivt=`，也存在 `/people/<id>/activities` 形态 → 拼出 `https://api.zhihu.com/people/xxx?ivt=abc/profile?...`（query 被截在 path 之前）→ 接口回错误 → 归因成「缺 drama.living_theater」并按未开播返回，把排障方向带偏成「接口改版」。本文件其余处均先 `split("?")[0]` 或用 `_safe_extract_id` | `url.split("?")[0].split("people/")[1].split("/")[0]`，取不到时显式抛 ValueError | 中 |
| MID-2225 | `spider.py:4662-4666`、`6053-6058`（对照 `5664`） | `async_req(redirect_url=True)` 的契约是成功 `str(response.url)`、失败 `""`，而三处用 `if isinstance(url_result, str)` 判型——空串也是 str，`else` 兜底分支**永不执行** | 花椒：网络抖动后 `url` 被置空串，「落到首页 = 短链失效」判定不成立，转而用空 relateid 请求，最终与真短链失效压成同一条未开播；京东：注释「否则保留原 URL 继续解析」与实际相反，原 URL 被空串覆盖后正则失配。三处同一语义、只有 Shopee 判了空串 | 两处补 `and url_result`；京东同时把 else 改成真正的失败回退或删不可达分支并修正注释 | 高 |
| MID-2226 | `main.py:2543-2544` + `3475-3480` | Shopee 回写的 `new_record_url`（`?` 之后整段来自接口，`session_uid` 是响应值）未做结构校验即拼进 `URL_config.ini` 的待更新行 | `|` 正是主循环解析该行的分隔符（`4787`）、`,`/`，` 是字段分隔符（`4682-4709`）、`\n` 是行分隔符。含 `|` 的 uid 会截断写回的地址（该房间此后每轮解析失败）；含换行则**往配置文件追加任意新行**（新房间地址下一轮被当作正常配置拉起）。`anchor_name` 有 `clean_name` 兜、URL 全程无校验；同仓 `web_config.update_room_quality` 已对换行注入显式 ValueError，此处是漏掉的兄弟路径 | 拼前对 `new_record_url` 做同源 + 字符集断言（`[A-Za-z0-9_\-&=%./:]`），否则丢弃 uid 段退回原 `record_url`；或 append 前统一过滤 `|,\r\n` | 中 |

### 4.3 选源、画质档位与探针 — MID-2227 … MID-2231

| 编号 | 位置 | 问题 | 影响 | 修复方向 | 置信度 |
| --- | --- | --- | --- | --- | --- |
| MID-2227 | `stream.py:491-498`、`614-631`（× `async_http.py:345-348`、`:367`） | 抖音/TikTok 的 HLS 可用性探针裸调 `get_response_status(url=…, proxy=…, platform=…)`，`headers` 全程 None、缓存 client 也不带默认头 → 出网 UA 为 `python-httpx/0.28.1`；而同步孪生校验器显式补 UA（`stream_select.py:629`） | 违反「同步/异步校验器的 proxy / verify / UA 三者必须一致」与「UA 双端一字不差」；CDN 按 UA 拒探针（403/405）→ `ok=False` → 抖音向相邻档回退、TikTok 直接判不可达，而 ffmpeg 用移动 UA 实际能录原画 → **静默降画质且 `actual_quality` 被回写成新选中档、无降级告警**。MID-26 只合流了 verify，UA 这一半仍缺（本条与 §4.1 的 MID-2209 是同一约定的两个不同探针落点，故各自计数） | 两个调用点显式传 `headers={"User-Agent": get_record_user_agent(platform) or MOBILE_UA}`（勿另立字面量），并加断言「两个调用点都带 UA」的回归锁 | 高 |
| MID-2228 | `stream.py:816-826`（对照 `766-780`） | 虎牙档位裁决只有两个入口：`video_quality in BD_SUB_TIERS` 与 `elif len(quality_list) > 1 and video_quality not in ["OD","BD"]`。当 `sFlvAntiCode` 不含 `&exsphd=`（`quality_list` 长度 1）且请求 HD/SD/LD 时**两个分支都进不去** | `ratio_val` 保持初值 `""` → FLV/HLS 不挂 `&ratio=`（同文件 `275` 实测注：不加 ratio 即原画），而 `actual_quality` 仍是请求档 → `main.py:3704` 的 `_is_downgrade` 恒 False → **零告警、面板显示按「高清」录制、产物是原画**（选「流畅」省流量的用户拿到最高码率文件）。`main.py:1624` 的分流决定了 HD/SD/LD 恰好全部落在这个缺口里；MID-13/14 只统一了「有 exsphd」的口径 | 去掉 `len(quality_list) > 1` 前置条件、与 BD 分支共用「exsphd 优先 → bitRate 推导 → 都缺则不附加 ratio 但 `actual_quality="OD"` 并 WARNING」的同一条链 | 高 |
| MID-2229 | `stream.py:460-463`、`469-470`（消费侧 `main.py:3700-3703`） | 抖音接口 `flv_pull_url`/`hls_pull_url_map` 的真实键是 `FULL_HD1`/`HD1`/`SD1`/`SD2`（本仓自己的 fixtures 可证），而 `order` 表与 `QUALITY_LEVEL` 用的是 `OD/BD/UHD/HD/SD/LD`；`_norm_code` 只折叠 `ORIGIN` | `order.get(...)` 对全部真实档位返回 99 → 注释承诺的「按画质等级降序排序」退化为保持上游插入序；`actual_quality` 常是非画质代码的 `"FULL_HD1"` → `_is_downgrade` 在 None 分支直接 return False，**抖音的画质降级永远不会出告警**，面板「实际画质」列显示裸英文键。上游哪天改序就静默错档且无信号——这正是本仓为虎牙/斗鱼建 `*_RATIO_TO_CODE` 回采表要防的形态，唯独抖音侧缺一张 | 补 `DOUYIN_KEY_TO_CODE` 映射并在 `_norm_code` 查表；未知键记 WARNING 并回退按码率/分辨率判定 | 高 |
| MID-2230 | `stream.py:1060-1062` | B站 `video_quality_options.get((video_quality or "OD").upper(), "10000")` 未折叠蓝光子档位 | `record_quality` 可取 `BD30/BD20/BD8/BD4`（`BUILTIN_QUALITIES` 与 `web/index.html` 下拉都注册了四档，AGENTS「蓝光子档位」条要求同步四处），四档全部 miss 字典 → 落到默认 `"10000"` 即**请求原画**（比用户选的更高）；`actual_quality` 回采为 `"OD"`、`is_downgrade("BD4","OD")` 为 False → 无任何告警，面板显示「设置 蓝光4M / 实际 原画」，产物体积翻倍。该默认值还兜住任何未来新增/拼错的代码，静默方向恒为「最高档」 | 选档前先 `get_quality_index()`（该函数正是为折叠子档位而生的唯一入口）折叠，并对未知代码加 WARNING | 高 |
| MID-2231 | `stream_select.py:428-435`、`445`、`464` | `_probe_hls_segment` 对**响应正文派生**的 `variant_url`/`seg_url` 发第二跳请求（`urljoin` 对绝对 URL 会整体丢弃 base），而 `headers` 含 `get_record_headers(platform, url, cookies=…)` 注入的用户 Cookie | httpx 只在**重定向跨源**时剥 Cookie（`_client.py:565-569`），对「新起的第二跳请求」不做任何处理 → 一个被劫持/作恶的 m3u8 即可让本机带着用户登录态向任意 http(s) host:port 发 GET（凭据外泄 + 内网 SSRF）。scheme 侧已被 httpx 白名单挡住，缺的正是 host 这一维——`_is_recordable_url` 只作用于交给 ffmpeg 的候选，从未作用于响应派生地址 | 对 `variant_url`/`seg_url` 增加与 playlist 同 host（或同注册域）的校验，不同 host 时剥掉 cookie 头并按保守分支返回 True；顺手把 `_is_recordable_url` 也套上 | 中 |

### 4.4 并发、事件循环与凭据生命周期 — MID-2232 … MID-2233

| 编号 | 位置 | 问题 | 影响 | 修复方向 | 置信度 |
| --- | --- | --- | --- | --- | --- |
| MID-2232 | `ws_client.py:200-206` 与 `282-296` | 握手成功即 `self._reconnect_count = 0`（「连上即重置」），而计数只在 `else`（正常关闭但未 stop）分支累加 | 只要 TCP/WS 握手能成功而服务端随后立刻关连接（房间结束、被踢、鉴权软拒绝、B站 `uid=主播uid` 的 1006 硬断连），每轮从 1 加起、下一轮又归零，`max_reconnect` **永不耗尽** → 文件头声明的「耗尽则回调 on_close 后返回」契约失效，`on_close` 不上报、采集器与监控页以为「还在连」（与 AGENTS「弹幕监控房间残留」同族症状）；`bilibili.py:66-81` 的多 host failover 因计数重置而在第一个 host 上无限循环；每 ~5s 一次握手 + 进房包 + 心跳/看门狗任务反复创建，属对平台的持续连击且退避恒为最小档 | 只在连接「存活足够久」（首次收到应用层帧，或 `monotonic() - connected_at > 2×reconnect_interval`）后重置计数；`_auth_watchdog` 不覆盖此环 | 高 |
| MID-2233 | `proxy.py:75`、`41-46`、`102-111`、`31-37` | 四条同源缺陷：① `_is_proxy_enabled_linux()` 把 `ftp_proxy` 也算「系统代理已启用」；② `_get_proxy_info_linux()` 先 `split("://",1)[1]` 剥掉原协议，而 `proxy_url` 恒补 `http://` → `all_proxy=socks5://…` 被静默改写成 HTTP 代理语义；③ 裸 IPv6（`::1`）取到空端口后**先命中 `raise ValueError`**，注释承诺的「交给 `__post_init__` 的裸 IPv6 分支放行」那段在 `if self.ip and self.port:` 门内、对该输入永不可达（AGENTS 定义的「源码注释中的事实性错误」）；④ `ProxyInfo.proxy_url`/`user`/`password` 在 `main.py` 与 `src/` 内**零消费点** | ① 只设 `ftp_proxy` 的机器 `global_proxy=True`，把 9 个海外平台推进「走代理」分支，但实际传给 `async_req` 的是配置里的 `proxy_address`（可能为空）→ 直连境外域名 → 全平台「网络异常」，而日志显示「有代理」；② 与③是解析层静默错值；④ 使 `MIN-20③` 声称修好的「认证代理无法还原完整地址」**实际仍未修**——凭据被解析后丢弃 | `_LINUX_PROXY_ENV_NAMES` 去掉 `ftp_proxy`；`__post_init__` 允许「裸 IPv6 + 空端口」；让调用方使用含凭据、保留原 scheme 的 `proxy_url` 作为兜底，否则删除该三字段并把 MIN-20③ 标注为未落地 | 高 |

### 4.5 Web 面板、配置写入与前端 — MID-2234 … MID-2241

| 编号 | 位置 | 问题 | 影响 | 修复方向 | 置信度 |
| --- | --- | --- | --- | --- | --- |
| MID-2234 | `web_api.py:544-548`；`web_config.py:72`、`1051` | `web_token_expiry` 无上下界钳制，且它因 `expiry` 命中豁免正则而**不受敏感键守卫** | `PUT /api/config {"section":"Web","key":"web_token_expiry","value":"0"}` 落盘后每次登录得到的令牌 `exp = now + 0`，中间件判 `exp > time.time()` 立即为假 → 所有 `/api/*`（含再次 PUT 修正自身）一律 401，用户只能手工编辑 config.ini 恢复——与头注释 ⑤「禁止清空密码（防自锁）」是同一防线却漏了这个键。反向写超大值则令牌永不过期且 `_tokens` 只增不减（内存无界），泄露的 bearer 成为永久凭据 | 对该键做目标态夹取（如 `[60, 7*86400]`），写成模块常量 + 回归锁，与 `_PBKDF2_MAX_ITERATIONS` 同等对待 | 高 |
| MID-2235 | `web_config.py:135-138`（对照 `main.py:4702-4709`） | `parse_url_config` 的 3+ 段分支把首段当画质、次段当 URL，而 main.py 的规则是「首段是 URL → 第二段起全是主播名」；写入口 `format_url_line` 只挡换行、不挡逗号 | 该组用 `format_url_line('https://live.douyin.com/123', None, 'A,B')` 写入再回读**实测**得到 `{'url': 'https://主播: A', 'quality': '原画', 'name': 'B'}`，全角逗号同样触发（`'小明，欢迎收看'`），而中文主播名带 `，` 极常见。录制端正常、面板端 `GET /api/rooms` 显示一条假房间，`DELETE`/`PUT quality`/`update_room_quality` 全部按规范化 URL 精确匹配 → 404/False，**房间在面板里既改不了也删不掉**；`find_room_url_by_anchor_name` 返回假 URL 还会让 GUI 报「未在 URL_config.ini 中找到」 | `else` 分支先判 `_is_url(parts[0])` 与 main.py 同规则；并在 `validate_room_target`/`format_url_line` 拒绝含 `,`/`，` 的 name | 高 |
| MID-2236 | `web_config.py:1076-1078`（读）× `web_api.py:929-937`（写） | 读侧脱敏判据是 `is_sensitive_item(section,key) or _looks_like_secret_value(value)`，写侧两道拒绝（空值 / 掩码）的谓词**只有** `is_sensitive_item` | 任何「键名不含凭据关键词、但值形如凭据」而被读侧掩码的键，面板回显 `***` 后，直接打 `PUT /api/config`（或不跳过掩码的旧前端）提交 `***` 即被服务端**接受**，真实凭据被字面 `***` 覆盖，且 `backup_config/` 副本同已脱敏无从恢复——`web_api.py:931-935` 注释声称该缺口已由后端关死，谓词却窄了一档（本条与 §4.5 前端侧的 `MIN-2246` 为同一处、由两个分组独立命中，此处为正式计数条目） | 写侧判据与读侧同源（`or _looks_like_secret_value(旧值)`），或把两判据合成一个函数供读/写/备份三处共用 | 中 |
| MID-2237 | `web/app.js:660-663`、`677-683` | 后端不可达的提示写进**弹幕视图**的元素 `#danmaku-stream`，而调用点是仪表盘轮询的 `.catch`；`markBackendUnreachable(false)` 全仓零调用点 | 后果双向失真：正在看的仪表盘完全无提示（配合 `SEV-2228` 用户以为后端健康）；用户切到弹幕视图后，即使弹幕轮询本身正常，首帧也被这条残留「已断开」占据，只能靠下一次 `dmRenderStream()` 覆盖 | 提示目标改到仪表盘内元素（新增 `#status-warning` 条），并在 `renderStatus` 成功分支调用复位 | 高 |
| MID-2238 | `web/app.js:1412-1417`（调用点 `1430-1432`、`537-543`） | `localStorage` 裸访问未走 try/catch，而 `MI-27` 已在本文件写下结论「Safari 无痕模式与『禁用站点数据』会把 storage 访问变成抛异常」并只为 token 建了 `_tokenStore()` 兜底 | `initTheme()` 是 `DOMContentLoaded` 回调的**第一条语句**，抛异常即中断整个回调：五个 tab、登录/登出按钮、事件委托、启动引导的监听器**一个都不注册**，面板退化成静态页且无任何错误提示 | 抽 `safeGetItem/safeSetItem`（内部 try/catch），theme/lang 全走它，两个 init 各自 try/catch 保证后续绑定不被前序失败带走 | 高 |
| MID-2239 | `web/app.js:546-556`（后端 `src/web_api.py:1005-1018`） | `PUT /api/language` 的响应契约（`language`/`fallback`/`notice`）整体未消费，`.then()` 形参被丢掉、恒按请求值本地切换 | 后端刻意改为「先 `set_language()` 拿**生效码**、按生效码落盘、再把 `language/fallback/notice` 回给调用方」，注释明写「前端据此更新，不得再按请求值回写」。典型场景：PyYAML 缺失使 `zh_TW.yaml` 装载不到 → 用户选繁體中文，后端实际生效并落盘 `en_US`，前端仍把 UI 切成内嵌 zh_TW 并写 `dlr_lang=zh_TW`，回退说明一次都不显示——正是 `MID-52` 要消灭的「面板与录制进程各说一种语言」，只是换了方向 | `then(function (res) { currentLang = (res && res.language) || target; ...; if (res && res.fallback) toast(res.notice, 'info'); })`，并把 `dlr_lang` 写成生效码 | 高 |
| MID-2240 | `web/app.js:611-614`、`651-673`（说明见 `web/index.html:39`） | `loadLogs()` 唯一调用点在 `showView('dashboard')`，`startSSE` 的轮询体内只有 `/api/status` + `renderStatus` | 面板标题为「实时日志」的区域内容停留在进入视图那一刻的 100 行；结合 `SEV-2227`，切走再回来连这一次都不会重取。**面板上唯一能看到平台报错原文与风控线索的地方长期陈旧**，误导排障方向（与 AGENTS「排查一律先看 logs/streamget.log」的动机相悖） | 在 poll 体内按同一节拍（或每 N 轮）调 `loadLogs()`，并在可见性恢复分支补一次；或把文案改成「最近日志（点此刷新）」并加手动按钮 | 高 |
| MID-2241 | `web/app.js:1255-1288`；`web_api.py:846-848` 与 `:118` | `[Web] web_auth_enable` / `web_password` 不在 `_DANGEROUS_CONFIG_KEYS`（实测该集合只有 `自定义脚本执行命令` 一项），走的是与 `循环时间(秒)` 完全相同的普通写入通道，前后端都无二次确认 | 一次 `PUT /api/config` 即可关掉认证（回环监听下 SEV-04 的守卫不拦）或改写口令（连带 `_tokens.clear()` 踢掉全部在线会话）。前端对删除房间、清空掩码凭据都弹 `confirm()`，对这两项零确认。持有（或曾持有）bearer 的一方——被窃取的 token、被扩展注入的页面、肩窥到的 token——能把「需要凭据的面板」降级成「本机任意进程可操控的面板」，**且该降级在 token 吊销后依然留存** | 这两键单独走一次 `confirm()` + 要求在当前会话复验口令（`POST /api/login` 通过再发 PUT）；后端可对这两键要求请求体携带复验字段 | 中 |

### 4.6 弹幕采集、监控枢纽与字幕 — MID-2242 … MID-2247

| 编号 | 位置 | 问题 | 影响 | 修复方向 | 置信度 |
| --- | --- | --- | --- | --- | --- |
| MID-2242 | `main.py:1035-1050` × `src/collector.py:146-169` | `check_subprocess` 的启动失败分支把 `danmaku_collector = None`，丢掉**半启动**对象的唯一引用 | `DanmakuCollector.start()` 非原子：`_started=True` → `self._srt.start()`（**已打开 `{base}_000.srt` 句柄**）→ 起 srt_writer 线程 → `hub.room_started()` → 起采集线程；任一步抛错（`can't start new thread` 是 AGENTS 自陈的现实形态）后 finally 与尾收 `stop()` 再也拿不到它：SRT 句柄永不 `close()`（Windows 上该文件在 GC 前无法改名，会打挂 `rename_anchor_directory`）、srt_writer 守护线程在 `get(timeout=0.5)` 上空转整个进程生命周期、采集线程若已起则继续向同一 `base_filename` 写 SRT。即使不置空，`stop()` 对「`Thread.start()` 抛错的线程对象」会先抛 `RuntimeError: cannot join thread before it is started` 从而跳过末尾 `self._srt.close()`。（与 `SEV-2208` 同族但落点不同：那条是 finally 缺 stop，本条是 except 分支主动丢弃引用） | except 里先 `danmaku_collector.stop()`（幂等）再置 None；`start()` 内部对各 `Thread.start()` 加 try 自回滚；`stop()` 用 `ident is not None` 或 try 包住 join | 高 |
| MID-2243 | `src/danmaku_monitor.py:623-635` + `:67-72`（调用点 `web_api.py:637-644`） | 边车 `close_file()` 的 `drain()` 等的是「已入队指令处理完」，但 close 之后入队的 line 指令会经惰性重开（`files.get(path)` 为 None → `open(path,"a")`）**在 drain 返回那一刻重新打开同一文件** | Web 面板「停止录制」是 `recording_enabled=False` 之后**同步**调 `archive_runtime_logs()`，而房间线程最快 1 秒、弹幕采集器最慢一整个 `delay_default=120s` 轮次才退出 → 归档时刻必然还有事件在推。结果 Windows 下 `_rename_one("danmaku_monitor.jsonl")` 抛 PermissionError、只留一条 warning，该文件在这条路径上**基本永不归档**（体积只按 `_ROTATE_BYTES` 轮转到 `.1`，一代之后无限增长）；Linux 下 rename 成功但**后续事件继续写进已归档的文件名**（fd 跟着 inode 走）。AGENTS「改名前须先关句柄」不变量在边车侧漏配 | 加短暂「归档窗口」抑制位（`close_file()` 置 `_suspend_sidecar_writes`，改名完成后清除并惰性重开）；或改名成功后再补一次 close，不把「是否重开」交给调度时序 | 高 |
| MID-2244 | `src/platforms/twitch.py:35`、`117-119` | 跨帧行缓冲 `_line_buf` **无长度上限**，且 `_on_ws_ready`/`stop()`/`decode_message` 都没有重置点（grep 证实只在 35/117/119 出现） | `MI-21` 把「丢半行」换成「攒半行」却没设上界：单帧虽有 `_MAX_FRAME_BYTES = 8MiB`，一个持续不含 `\n` 的对端会让缓冲随帧数线性增长，长录数小时即成内存放大点；另一半是跨会话污染——重连后旧连接残留的半行会被拼到新连接第一条消息前面，那一行必然解析失败，且这条路径连 debug 都没有（bilibili/douyu/huya 均有帧解析异常日志） | 给 `_line_buf` 加上限（超限丢弃并 debug 一条），并在 `_on_ws_ready` 里清空 | 高 |
| MID-2245 | `src/platforms/bilibili.py:148-157` → `src/ws_client.py:282-286` → `src/collector.py:478-500` | `_reject_auth()` 复用 `WsClient.close()`，而 close 先置 `self._stopped = True`；`connect()` 的正常关闭分支 `if self._stopped: break` 直接 break，**不调 `self._on_close`** | `_on_ready` 已调过 `hub.room_connected()`，配对的 `room_closed()` 只在 `_on_close` 里发 → buvid 软拒绝与 8 秒看门狗超时这两条「已知的静默零弹幕」形态被主动断开后，Web 弹幕监控一直显示该房间「已连接」且消息数为 0，直到录制结束才由 `room_stopped` 收走。恰好复现 AGENTS 记录的那类「连接就绪但 0 弹幕且无线索」观感，只是换了触发点 | `WsClient` 暴露 `fail(reason)`（置 `_stopped` 后仍回调 `on_close(reason)`）；或 `_reject_auth` 里显式调一次 `self._on_close("进房认证被拒")` | 高 |
| MID-2246 | `src/room.py:204-217` | `get_unique_id()` 主路径异常被 `except Exception: pass` 整段吞没，**零日志** | 主路径（iesdouyin JSON 接口）失败时异常类型、状态码、响应长度全部丢失，随后走的 HTML 兜底按 AGENTS 记录「已是 JS 反爬壳页、正则通常失效」，于是用户只看到上层一句「网址内容获取失败」，而根因（证书/代理/DNS/风控 200+空 body/JSON 改版）无任何落盘线索——与 AGENTS「异常日志必须带异常类型与上下文、禁止静默吞异常」直接冲突。抖音主页类链接（`www.douyin.com/user/<sec_uid>`）全部经此路径 | 至少 `logger.debug(tr("抖音 unique_id 接口失败(转 HTML 兜底): {type_name}: {e} - {masked_url}", ...))`，新增模板同步四语目录并重编译 `.mo` | 高 |
| MID-2247 | `src/ws_client.py:372-376` | 全仓唯一的「别名 logger + f-string」组合：`from loguru import logger as _log` 后 `_log.warning(f"...{x:.0f}s...")`；而门禁判据是 `node.func.value.id == "logger"`（`tests/test_i18n_migration.py:128-133`） | 双重后果：① 带插值的 f-string 在查目录前完成插值，该文案永远无法翻译；② 不变量① 与③ 都看不见它 → 门禁自证「全绿」，且该串也不在四语目录里（`extract_i18n_strings.py` 只认 `logger.*` 首参）。实测 `grep "as _log\|as log\b"` 全仓仅此一处，即这是**i18n 门禁在 MID-68「首参子树」之外的第二个已知盲区（别名形态）**，而它位于五个平台弹幕共用的 WS 层 | 本文件顶部已 `from .logger import logger`，直接用 `logger.warning(i18n.tr(模板, seconds=...))` 并同步四目录；把不变量① 的判定放宽为「被调对象的解析名绑定到 loguru logger（含 `*_log` 与模块属性形态）」，或加一条「不得给 logger 起别名」的 AST 检查 | 高（两分组同判） |

### 4.7 GUI、i18n 与推送 — MID-2248 … MID-2253

| 编号 | 位置 | 问题 | 影响 | 修复方向 | 置信度 |
| --- | --- | --- | --- | --- | --- |
| MID-2248 | `i18n.py:145-151`、`272-276`、`300-323` | `has_catalog()` 只判断文件存在、**不判断能否加载**，而 `set_language` 的 `_effective_language` 唯一判据就是它 | PyYAML 缺失时 `_load_yaml_catalog` 直接 `return None` → `_build_translator` 返回恒等映射，但 `_current_language` 仍是 `zh_TW`。这正是该函数注释（`290-296`）自己点名的两个动机场景之一。用户可见后果：GUI 选「繁體中文」时 `effective == lang_code` 故 `gui.py:1399` 的回退告警**不触发**，日志打「语言已切换: zh_TW」并写回 config.ini，而界面与子进程输出全是简体原文，零告警。损坏的 `.mo` 同理 | 判据换成「`_load_translations(dir, lang)` 返回非空 dict」，`has_catalog`/`_effective_language`/`resolve_language` 共用同一函数；补一条 `PyYAML is None` 的日志（现该降级完全静默） | 高 |
| MID-2249 | `gui.py:2754-2764`（对照 `2726-2728`、`2783`、`2792`） | `WD-21` 的两个 except 分支已改用 `_mark_session_stopped(session_id)`，**自然 EOF 这条最常走的路径仍裸写 `self.running = False`** | 旧会话线程在「停止 → 立即再启动」竞态中把**新会话**的 `running` 打成 False；`_process_ended` 会因会话代号不符丢弃哨兵并把按钮复位，但 `running` 无法回正（只有下一次 `start_recording` 才重置），表现为状态刷新间隔从 3s 退化为 10s、状态栏与呼吸灯按「未运行」口径刷新，日志无线索。`grep -rn "_mark_session_stopped\|_read_output\|WD-21" tests/*.py` 实测 **0 命中**，即该不变量目前无锁 | 该行改 `_mark_session_stopped(session_id)`；补「session_id 已过期 + readline 返回空 + poll 非 None → 断言 running 仍为 True」的用例 | 高 |
| MID-2250 | `gui.py:3046-3056`、`3064-3069`、`3079` | 弹幕 tail 线程**复用同一个** `self._danmaku_tail_stop` Event：`_stop_danmaku_tail` 只 `join(timeout=0.2)` 后无条件把引用置 None，调用方紧接着 `clear()` 同一个 Event | 循环条件是 `while not self._danmaku_tail_stop.is_set()`；若旧线程此刻卡在 `time.sleep(0.5)`/`sleep(0.3)`/一次 `f.read()`（`logs/danmaku_monitor.jsonl` 被归档改名时 `except OSError: sleep(1.0)` 会卡整 1 秒，远超 0.2s 预算），它醒来看到的已是 False → **永不退出**且无人持有引用。每「停止→启动」一次就可能多留一条 tail 线程，各自维护独立 `offset` 读同一文件 → 同一批事件被多次 `_danmaku_dispatch`，房间累计弹幕/礼物计数成倍虚增、弹幕流区重复行，随重启次数单调恶化，全程无日志 | 每次启动创建**局部** Event 随闭包传入；join 超时则保留引用并在下次 start 前重查，绝不复用可被 `clear()` 的共享标志 | 高 |
| MID-2251 | `msg_push.py:116`、`155`、`243`、`246`、`289`、`351`、`443`、`482`；`web.py:311`、`317` | 推送/清理的 10 处异常日志只带 `{e}`、不带 `type_name` | AGENTS 把 `{type_name}` 列为硬要求，理由是 Windows 下 `socket.timeout`/`TimeoutError` 的 `str()` 为空；本机实测 `str(TimeoutError())==''`、`str(socket.timeout())==''`，且超时经 urllib 包装后为 `'<urlopen error >'` → 「钉钉推送失败 … 错误信息:<urlopen error >」这类行既看不出是 DNS、TLS 校验失败还是超时。同文件 `226-233` 与 `gui.py:2360-2364` 都写对了，说明是遗漏而非取舍。用户侧表现为「配了推送但收不到，日志里只有一串空白」 | 10 处统一 `错误信息: {type_name}: {e}` + `type_name=type(e).__name__`；按仓库约定改模板名须同改 kwarg 名，并同步四份目录 + `compile_po.py` | 高 |
| MID-2252 | `gui.py:2288-2304`（对照同文件 `756-777`） | `AdvancedSettingsWindow.save_config` 已按 `MID-55` 在写回前重读磁盘并走 `_config_change_verdict` 裁决，**URL 页这条整文件写回路径没有同款复核** | 唯一防线是 `_watch_url_config` 的 3-10 秒 mtime 轮询，且用户答「否」时会主动把基线对齐到当前以止吵。而录制子进程运行期**确实在写** `URL_config.ini`（`main.py:4674` 回写主播名、`4748/4754` 归一 URL、`4771` 把无法识别/风控的房间整行注释掉）→ 用户点一次「保存」即把刚被自动注释的坏房间重新启用（表现为「停不掉的房间又回来继续刷错误」）、刚归一的地址退回带 `?modal_id=` 的长链。`_on_room_quality_change` 的读-改-写只受**进程内** `_config_write_lock` 保护，跨进程同样只剩原子替换 | `save_config` 落盘前先 `_read_config_snapshot` 与基线比对，不一致即复用 `_config_change_verdict` 的 conflict 弹窗；`_on_room_quality_change` 同理想复用 | 高 |
| MID-2253 | `gui.py:879`、`891`、`2982`；新实例 `web.py:297` | **上一轮 `SEV-N06` 复核结论：未落地**（`grep -rn "DLRQ\|#DLR"` 全仓 0 命中，三条简中 pattern 原样在位、无机器可读前缀机制）；同族新实例——`web.py` 把中文常量值插进已翻译模板 | 实测两条清标记 key 在 en_US/en_GB/zh_TW 均**不含** `没有正在录制` 子串 → 非 zh_CN 语言下三条判定全部恒假：画质监控表永久「暂无」、降级告警整块丢失、`recording` 标记不清（`gui.py:2982` 的 `if "没有正在录制" in msg` 中 `msg` 取自 `gui.py:2917-2931` 的日志正文，而该正文由 `main.py` 经 `i18n.tr()` 按当前语言发出）。新实例：`tr()` 只翻译模板、不翻译插值后的实参，故 en_US 下 Web 启动横幅输出 `Authentication: 开启`——同一「模板已本地化、值未本地化」缺陷族在 Web 入口复现。（`gui.py:2341` 的 `"录制设置" in config` 是 ini **节名**、不随语言变，**不是**问题） | 实参改 `tr("开启")/tr("关闭")` 后传入（四目录补 key + 重编 `.mo`）；`SEV-N06` 本体按报告建议在 `AGENTS.md` 先定义 `#DLRQ\|` 前缀契约，再同改 `recorder_status.py`/`main.py`/`gui.py` | 高 |

### 4.8 构建、CI、门禁与测试可信度 — MID-2254 … MID-2265

| 编号 | 位置 | 问题 | 影响 | 修复方向 | 置信度 |
| --- | --- | --- | --- | --- | --- |
| MID-2254 | `build_exe.py:1144-1159` | `full` zip 在 `smoke_test()` **之后**才压缩（`lite` 先压缩故干净） | 冒烟以 `cwd=RELEASE_DIR` 连跑 CLI 25s / Web 90s / GUI 8s，`src/logger.py` 会在 `script_path/logs/` 落 `streamget.log`、`PlayURL.log`、`web_console.log`，「缺键补写」还可能改写包内 config.ini → 用户解压即见 runner 的绝对路径/用户名与告警堆栈（信息外泄），且随包带一个非空 `logs/`。AGENTS 把 `logs/`、`backup_config/` 列为「不得入镜像」的同一条口径在 zip 侧无人守 | 压缩与冒烟解耦（先 make_zip 再 smoke，或 smoke 跑独立临时副本）；`make_zip` 前删 `logs/`、`backup_config/`、`downloads/`、`__pycache__/`；发布产物清单加 `unzip -l` 断言不含 `logs/` | 高 |
| MID-2255 | `.dockerignore:115`、`116`、`155` | 行内 `#` 不是注释（只有**行首** `#` 才是），三条模式变成永不匹配的长串 | 实测三行为 `build_exe.py             # 仅本地 / CI 打包脚本…`、`StopRecording.vbs        # Windows 停止录制脚本…`、`*.jsonl   # 运行日志…` → 等价于「没写」：65KB 打包脚本、37KB UTF-16 的 Windows 脚本、仓库内任何散落 `*.jsonl` 都经 `COPY . ./` 进镜像。它**伪装成「已经排除了」**，人工核对极易漏，正是 AGENTS 反复登记「漏一处即误入镜像」的形态。另 `:141` 的 `i18n/**/compile_po.py` 是空规则（真身在 `scripts/`，已被整目录排除） | 注释移到独立行；删失效的空规则；补一条断言「`.dockerignore` 每行都不含 ` # ` 形态」的用例 | 中（解析语义与 Docker 文档一致，本轮未实跑 `docker build`） |
| MID-2256 | `scripts/check_annotations.py:60-74` | `EXCLUDE_DIRS` 自称「与 `.gitignore`/pyproject 同源」，实测落后 13 项（缺 `.mimosa`/`.qoder`/`.qoder-credits`/`.agents`/`.pnpm-store`/`.npm-cache`/`.dsh-validation`/`.ego-browser-test`/`.plugin-src`/`.tmp-dps-extract`/`.v2c`/`backup_config`/`recordings`，`typings` 亦未排除） | ① 本地 `run_gates.py` 会把第三方工具目录里的 `.py` 按 13% 密度/模块头规则判红（CI 全新 checkout 看不到，典型「本地红、CI 绿」）；② 更值得注意——`check_dangling_symbols()` 用同一份清单聚合 `global_bound`，任何第三方目录里的同名绑定都会让「被删符号的残留调用点」被判为「全仓有绑定」而**漏报**，即门禁 teeth 被静默削弱。当前这些目录实测 0 个 `.py`，属潜伏缺口 | 把三处已同源的清单抽成一份可被脚本读取的事实源，或脚本内补齐并加一条与 pyproject exclude 的键集对比用例（仿 `test_ffmpeg_path_preference` 的跨文件同源锁） | 高 |
| MID-2257 | `scripts/douyin_live_recorder_standalone.py:509-525` 对照 `src/scheduler.py:198-213` | standalone 的 `PlatformBreaker` half-open 分支**无条件**把任何回报当探针结果，缺 `_probing`/`_probe_owner`/`_probe_seq` 门控（AST 复算副本仍 5 方法 vs src 9 方法） | 熔断转 half-open 后，一条在熔断前就已放行、此刻才收尾的普通轮次 `record_success` 会直接 `clear()` 样本窗口并置 closed → 坏 CDN 立刻重新拿到全部房间流量（正是 MIN-22 要修的形态）；租约重授予后的陈旧探针同样能关掉新探针。次级差异：副本 `_push` 用 `list.pop(0)`（持锁 O(n)）而 src 用 deque 增量扣减。`AGENTS.md:1287-1295` 只登记了「缺四个方法」的结构差异，**低估了由此产生的行为差** | 按「逐方法 diff 后显式决定」回灌 `_grant_probe`/`_end_probe` + 探针归属字段并在两处注释互相点名；同时把行为差补进 AGENTS 条目 | 高（两分组同判） |
| MID-2258 | `src/log_archive.py:76-84` 与 `90-114` | `_archive_web_console` 已在改名前 close 掉流，而 `_rebind_web_console` 在重开失败时只 `logger.warning` + `return` | `sys.stdout`/`sys.stderr` 此后**永久停在已关闭对象上**，且 `rebind_console_sink()` 未被调用（旧 sink 仍绑死对象），本进程剩余生命周期所有 `print()` 抛 `ValueError: I/O operation on closed file`；`display_info` 侧只表现为连续失败退避到 300 秒，用户看到「状态面板卡住不动」，唯一线索是一条只进 `streamget.log` 的 warning。触发需「改名成功但重开失败」（备份/杀软短暂占用、logs 目录改只读、句柄耗尽） | 失败分支也接上输出链路：回退 `open(os.devnull,"w")`（或置 None 让 logger 判空早退接管），并一律调 `rebind_console_sink()`；重开支持下一轮归档重试 | 中 |
| MID-2259 | `scripts/check_coverage.py:50-57` + `:188`；`tests/` 全库 | 逐模块覆盖率门禁**只遍历硬编码的 6 模块表**（`spider`/`stream`/`utils`/`ttwid`/`ab_sign`/`proxy`），不按 `src/` 扫描；而今天新增的 402 行下载模块 `src/ffmpeg_master_download.py` 在 `tests/` 内**零引用**（grep `download_ffmpeg_master`/`ffmpeg_master_download` 0 命中） | 任何新 `src/*.py` 模块自动豁免覆盖率门禁 → 「门禁查不到新增的高危面」。该模块做的事是下载外部二进制、写盘、`rmtree` 目录、前置 PATH 并执行。`MIN-19` 的「模块查不到按失败处理」只覆盖表内条目的**数据缺失**，不覆盖「压根没登记」这一形态 | `check_coverage.py` 改为「遍历 `src/` 全部模块，未登记阈值者按全局 floor 判定或显式列白名单」；并为本模块补最低限度的下载/解压/失败路径用例（含「读基准失败必须拒装」的锁，对应 `SEV-2222`） | 高 |
| MID-2260 | `tests/test_check_runtime_pins.py:65-69` 对照 `scripts/check_runtime_pins.py:78-97` | `_runtime_matrix_keys` 被 **autouse fixture 整体桩掉**，本文件没有任何用例驱动真实现 | `check(strict=...)` 的「矩阵内/矩阵外」分流全靠它。把该函数的 `sys.exit(2)` 改成 `return []`（解析不出来就当没有平台），所有未钉定槽位都落进 `unpinned_offmatrix` 只告警，`--strict` 对一张全占位的表返回 0 → `build-release.yml` 的 prepare job 放行、full zip 无校验打进对外分发包（`SEV-10` 的原始危害）。当前用例对此全绿，因为它们眼中的矩阵是自己造的 | 补一条不套该 fixture 的用例：`_WORKFLOW` 指向 tmp 下三份 fixture（正常三平台 / 含未登记标签 / 无 `- os:` 行），断言 3 键 / SystemExit(2) / SystemExit(2)；再加一条「真 workflow 解析结果 == _MATRIX_KEYS」的同源锁 | 高 |
| MID-2261 | `scripts/check_coverage.py`（`grep -rln "check_coverage" tests/` **无任何命中**） | 8 条门禁里唯一「零回归锁」的一个 | 把 `MODULE_THRESHOLDS` 清空、或把 `missing_modules` 判定改回「只告警」，`rc` 仍为 0 并打印 `PASSED: All 0 module(s) meet coverage threshold`——AGENTS「测试不得自实现被测逻辑」条目与 `MIN-19` 记录的正是这句话的两次历史形态，而 `ci.yml` 把它作为 required 链路一环。同理 `_find_module_coverage` 第③步若改回「按纯文件名匹配」，`src/utils.py` 的阈值会被 `tests/utils.py` 顶替（2026-09-12 审查 6.7 的原始缺陷） | 新增 `tests/test_check_coverage.py`（`spec_from_file_location` 加载，与 `test_run_gates.py` 同法）：表非空且键存在于 `src/`、喂 `files={}` 断言 rc=2、喂只含 `tests/utils.py` 的报告断言 rc=1、一条 rc=0 正例 | 高 |
| MID-2262 | `tests/test_decorator_contract.py:44-61`、`100-113` | 全仓 AST 门禁依赖字符串常量 `DEC_DICT`/`DEC_NONE`，但**没有「扫到了多少」的见证**；两个 `except …: continue` 让读不到/解不开的文件静默出局 | 把 `src/utils.py` 的两个装饰器改名（含全部 50+ 调用点、含本文件顶注），`hit` 恒空 → `violations == []` → 门禁绿，而 CR-12 的「装饰器绑到下一个 def」与「返回契约错配」两条防线同时消失（表现为 haixiu/looklive 一类平台异常不再计入熔断样本、popkontv 元组解包被二次吞没）。同仓已有正确范式可抄：`test_test_hygiene.py:268-273`、`test_record_container.py:100-105`、`test_platform_dispatch.py:275` 都留了命中数见证 | 断言前加 `n_decorated >= 40` 与 `len(files) > 100`；`except` 改为记入 `unscanned` 后断言其为空 | 高 |
| MID-2263 | `tests/frontend/test_quality_ui.mjs:415-423`（对照 `src/config_bool.py:30-31`、`web/app.js:1162-1163`） | 名为「`parseConfigBool` 与后端 `src/config_bool.py` 同口径」的用例，断言基准是**测试内联的字面量清单**，既非 `TRUE_TOKENS` 也非 `CONFIG_TRUE_TOKENS`；`tests/test_config_bool.py:36-64` 的参数化表同样是自抄一份 | 从 `src/config_bool.py::TRUE_TOKENS` 删掉 `"on"`（后端 `parse_config_bool("on", False)` 回落 default，面板仍显示为「是」）**两侧都绿**。AGENTS「保持同集合（改任一侧须同步另一侧）」这条跨语言不变量实际只靠人记 | 由包装层先把 `TRUE_TOKENS/FALSE_TOKENS` 序列化为 JSON 传给 node、`.mjs` 用它驱动断言；或在 `.mjs` 里正则抠出 `CONFIG_*_TOKENS` 键集合与传入的 Python 集合做 `deepEqual` | 高 |
| MID-2264 | `.github/workflows/ci.yml:148-156` 与 `392-436`；`tests/test_frontend_quality_ui.py:51`；`tests/test_stop_recording_vbs.py:167,178,192,201` | `test` job（ubuntu）不装 Node（`setup-node` 只在另两个 job），故 ci.yml 注释承诺的「改 web/app.js 须由 test job 触发 `.mjs` 锁」只成立于 runner 镜像恰好自带 node；VBS 的 4 条 `cscript` 行为锁在 CI 六条 ubuntu job 上**永不执行**；而 `skip` 与 `pass` 在 `ci-summary` 里不可区分 | 一旦镜像不附带 node 或换 self-hosted，`test_frontend_quality_ui.py` 整模块 skip → 面板侧 27 条断言（含 `saveConfig` 跳过 `'***'` 这条写入侧防线、画质 PUT 契约、四语 toast）全部消失而汇总仍绿。`test_frontend_quality_ui.py:171-178` 对「node 在但收集到 0 用例」有锁，对「node 不在」没有任何反向锁 | 给 `test` job 加 `actions/setup-node@v7`（与 `node_version` 常量同源），并加兜底步骤断言不存在该模块的 skip；或在 `ci-summary` 显式核对「前端锁已执行」 | 中（「镜像自带 node 时仍会执行」一环未实盘核对） |
| MID-2265 | `src/ab_sign.py:536-546` × `scripts/check_coverage.py:55`（`"src/ab_sign.py": 95`）× `tests/test_ab_sign.py:44-46` | 546 行的 A-Bogus 全链**无任何生产调用点**（`ab_sign(` 在 `src/`/`main.py`/`web.py`/`gui.py`/`scripts/` 内除定义外零命中），却被要求 ≥95% 覆盖率（全表最高，高于 spider/stream/utils）；抖音实际用的是 `_xbogus.py` 与 `x-bogus.js` | ① 门禁统计把预算花在无调用方的代码上，并给人「A-Bogus 已被保护」的错觉；② 若抖音把 web 接口从 X-Bogus 切到 A-Bogus，接线者拿到的是一份**从未与真实服务端对过一次**的实现（SM3 本体该组用 OpenSSL 独立核对为标准值，但 `generate_rc4_bb_str` 的字段布局/时间戳语义无任何外部裁判），静默产出错误签名的排查成本极高；③ 新加的符号可达性检查查不到这种形态（名字有绑定，只是没人引用）。`tests/test_ab_sign.py:44-46` 关于 `src/__init__.py` 再导出的注释也已失效 | 要么删模块 + 用例 + 表项（含 `ci.yml` 的模块清单），要么在模块头写明「当前无生产调用点，等待接线」并把地板降到与死码相称的值；同时修掉失效注释 | 高 |

## 五、轻微问题（P2，68 项）

> 计入口径：能在无人察觉的情况下劣化行为、或使后续改动踩坑的缺陷。纯风格问题不计（本仓风格已由 black/isort/mypy/basedpyright/`check_annotations` 五面门禁覆盖，见第七章）。相近条目已合并成行，行内列出全部落点。

### 5.1 平台解析与网络层（MIN-2201 … MIN-2222）

| 编号 | 位置 | 问题与影响 | 修复方向 | 置信度 |
| --- | --- | --- | --- | --- |
| MIN-2201 | `spider.py:1203-1211` | 虎牙字母房间号反查：正则 `'ProfileRoom":(.*?),"sPrivateHost'` 无值前引号锚点、取值后不判 `isdigit()`，而**孪生副本**（`standalone:705/781-789`）用了 `"ProfileRoom":` 带引号锚点且判 `isdigit()`。若页面为 `"ProfileRoom":"6030242"` 则捕获值含引号 → `roomid=%226030242%22` → 所有字母号虎牙房间静默按未开播；URL 以 `/` 结尾时 `room_id` 为空串仍照发请求 | 取回后 `re.sub(r"\D","",...)` 或判 `isdigit()`，非数字/空串早抛「请使用数字房间号链接」；两副本同改并互相点名 | 中 |
| MIN-2202 | `spider.py:1236-1245` | 候选条目以 `stream_name and flv_anti_code` 为「整条 entry 有效」的判据，但 HLS 地址只依赖 `sHlsUrl`+`sHlsAntiCode` → 房间只下发 HLS 票据（或 AL 线路未承载 FLV）时**连 HLS 候选都被砍掉**，全部线路如此则落到「在播但零候选」，与虎牙 FLV-first + HLS 回退的设计意图相悖 | 判据改 `if not stream_name: continue`，append 时按各自票据非空分别写入 flv/m3u8 | 中 |
| MIN-2203 | `spider.py:1414-1424` | 全仓唯一一条用字符串**拼接**做首参的形参日志（`logger.warning("Douyu betard abnormal for rid=" + str(rid) + ": " + reason)`）：既进不了 `zh_CN.po` 也进不了四语目录——`extract_i18n_strings.py` 与 `test_i18n_migration` 的判据都只看 `JoinedStr` 子树，故属 `MID-68` 收紧后的**第三种逃逸形态**（BinOp 拼接）。中文语言下面板中英混排且无法翻译 | 改 `logger.warning(tr("斗鱼 betard 响应异常: rid={rid} reason={reason}", ...))` 并把两条 reason 文案登记进四目录 | 高 |
| MIN-2204 | `spider.py:1344-1356` | 斗鱼签名三处零日志降级（`rand_str`/`key`/`enc_time` 非预期类型即取空串/0），`enc_time` 若以字符串 `"2"` 下发就退化为 0 次迭代 → 产出的 `auth` 必被拒而调用方只见「无流」；反向 `enc_time` 是响应驱动且**未设上界**，异常大的数值会在房间事件循环里跑无上限 md5 链（阻塞同循环的弹幕协程） | `int(...)` 容错解析 + `min(..., 32)` 上界；三字段任一缺失即 warning 并 `return {}`（`1466` 已对 `enc_data` 这么做，另三个漏了） | 中 |
| MIN-2205 | `spider.py:1763-1769` | B站选档注释写「请求档位不存在时回退到**最高**可用清晰度」，实际 `min(映射值, qn_count-1)` 在档位不够时落到的是**最低**可用档（房间只有 [10000,80]、请求蓝光 400 → 取 80 流畅）；且无降级告警（虎牙/斗鱼分支都有就近降级告警，B站没有） | 改注释为「就近向下取档」，或按 `current_qn <= 请求值` 就近选择并在降级时 WARNING，与 `get_huya_stream_url` 口径对齐 | 高 |
| MIN-2206 | `spider.py:661-683` | 抖音 HTML 兜底成功后，`682` 又对**同一 url** 再发一次请求只为取 `hevc_flv_url` → 被风控（200+空 body）是每个抖音房间的常态，等于每轮多下载约 1 MB 页面，正是 `646-648` 注释想「省去」的开销；两次抓取之间页面可能变化，导致 ORIGIN 与 hevc 地址来自不同快照 | 把兜底已得的 `html_str` 提到循环外复用，仅在其为空时再抓一次 | 高 |
| MIN-2207 | `spider.py:2000-2015` | B站 buvid 的 spi「重试一次」两次请求**零间隔**连击同一路径（对 CDN 探针有 `_throttle_probe`，对 spi 没有），且 `2015` 的 `except` 分支（含两条 debug/warning 日志）在风控主形态下永不执行（`async_req` 与 `_loads_dict` 都不抛）；未走 per-key 去重，多房间冷启动各自连击两次 | 空结果时按 `_recheck_delay` 的抖动口径 `await asyncio.sleep(0.5 + random()*0.5)` 再重试，「两跳皆空」落一条 warning 取代永不执行的 except | 高 |
| MIN-2208 | `spider.py:4131-4135`、`3450-3454` | 微博/Look 把「FLV 与 HLS **同时**存在」当作开播必要条件（`if not m3u8_url or not flv_url`），与上层 `stream_select.py:944-966` 的「hls/flv/record_url 三通道各自可空、按可用性回退」整套设计相反 → 单路房间（微博近年主推 HLS）每轮判未开播，而「未开播」轮次按约定刻意静默，用户与日志都看不到线索；归因文案还写「风控降级或字段改名」，把方向带偏 | 改 `if not m3u8_url and not flv_url:` 才判无源，否则只写实际拿到的那一路（`record_url = flv_url or m3u8_url`） | 中 |
| MIN-2209 | `spider.py:4031-4035` | 百度直播把 `data` 的**首个键**当房间对象（靠 JSON 插入顺序）→ 接口新增任何排在前面的同级键（`errmsg`/`hasNext` 等）后 `data` 成标量：`anchor_name` 空 + `status != "0"` → `is_live=False` 且**零告警**（`data_dict` 非空，绕过了 `4025` 的归因分支），接口改版完全不可见 | 遍历 `values()` 取第一个「是 dict 且含 `status` 或 `host`」的值；都不满足则 `_warn_api_abnormal` 后再按未开播返回 | 中 |
| MIN-2210 | `spider.py:2466-2469`（同型 `2571-2572`、`2643-2644`） | SOOP `bj_id` 段数启发式对 `https://www.sooplive.co.kr/play/<bj>` 形态（5 段）命中 `<6` 分支 → 取到字面量 `"play"` → 拼出 `.../live/play/master.m3u8`，该形态永久解析失败；同一条启发式在三处各自复制（改一处漏两处） | 用 `urlparse(url).path` 段列表显式判定（首段是 `play`/`channel`/`live` 则取其后一段），抽成 `_soop_bj_id_from_url()` 供三处复用 | 中 |
| MIN-2211 | `spider.py:5726-5738`、`5688` | `session_id` 为 None 时仍请求 `/api/v1/session/None`（白发一次请求），随后每轮（默认 120s）输出一条 **ERROR** 叫用户「更换房间地址」——而地址没问题，只是没开播，正踩「正常轮次刻意静默，否则 warning 淹掉真线索」的口径 | `5726` 之前 `if not session_id: return result`（必要时一条 debug 归因）；`logger.error` 只在「确认拉到会话但无 data」时用 | 中 |
| MIN-2212 | `spider.py:6346-6351` | 连接直播：`flv_url = https_url.replace("?", ".flv?")` 完全依赖 URL 含 `?`；`videoUrl` 不带查询串时三个地址字段同指原始无扩展路径 → `stream_select` 无从判容器、ffmpeg 每轮失败，而 `is_live=True` 使这一轮被记成**成功解析样本**（AGENTS「解析成功轮即上报成功样本」），熔断统计看不出该线路已坏 | `if "?" not in https_url:` 归因后按未开播返回；或按有无 `?` 分支选择 `.flv?`/`.flv` 拼接 | 中 |
| MIN-2213 | `spider.py:6157-6159` | Faceit 昵称提取用裸 `re.findall(...)[0]`，用户粘贴不带 `/stream` 的玩家资料页即 IndexError（被兜成未开播但日志是一行 `IndexError … in get_faceit_stream_data`），与本文件其它 12 处统一的 `if not m: raise ValueError("Failed to find …")` 可读线索不同，也未被 MID-48 批次覆盖 | 与同批口径一致：先取列表、空则 `raise ValueError("Failed to extract faceit nickname from URL")` | 高 |
| MIN-2214 | `spider.py:5983-5984` | 淘宝 SUCCESS 分支仍 `json_data["data"]` 裸索引（本区间内 MID-48 口径唯一残留）；且 `ret_msg == ["SUCCESS::调用成功"]` 写死了 `::调用成功` 后缀 | `_dig(json_data,"data")` + `isinstance` 判定，缺则归因后返回；比较改 `startswith("SUCCESS")` | 中 |
| MIN-2215 | `spider.py:4811-4815` | ShowRoom 命中 `hls_all` 但 `url` 为空时 `is_live` 已在 `4798` 无条件置 True，返回 `{is_live: True, m3u8_url: ""}`（无 play_url_list/record_url），与同批「已判开播却拿不到任何线路 → 归因 + `is_live=False`」自相矛盾（`4805-4809` 那条只在整个列表为空时生效）→ 坏候选进选源、每轮白烧探针 | `result["m3u8_url"] = m3u8_url` 移进 `if m3u8_url:`；循环走完仍无有效清单时复用 `4806-4809` 告警并回 `is_live=False` | 高 |
| MIN-2216 | `spider.py:2414-2416`、`2438-2440` 等 24 处 | `abroad=True` 实际被 `async_http.py:230-231` 显式丢弃（`_ = (abroad, content_encoding)`，注释写明仅为与 `sync_req` 签名兼容），但 24 处注释把「境外必须走代理」归因于 `abroad=True` → 诱导「删掉 `proxy_addr` 只留 abroad 仍能走代理」的错误改动，或排障时盯错参数 | 这些注释改述为「代理由 `proxy_addr` 透传；`abroad` 仅为签名兼容位」，不新增运行时代码 | 高 |
| MIN-2217 | `async_http.py:170-181`、`191-207` | `close_all_clients_sync` 在 atexit/信号上下文对**他线程循环**创建的客户端 `await client.aclose()`——正是 `:110-121` 与 AGENTS `2026-09-04` 条目判定为禁止的形态；当前不炸是因为 httpcore 立刻抛 RuntimeError 被逐条 `except Exception` 吞掉，即该清理**事实上是 no-op**，但 `await` 无超时，若实现改为等待他循环的 `anyio.Event` 就会在退出路径上无限阻塞。且 3.14 下主线程 `get_event_loop()` 通常直接抛 RuntimeError，函数真实行为只剩 `_client_cache.clear()`，与 `:184-187` 注释描述不符 | 缓存值加 owner 线程字段，只对 `current_thread() is owner` 者 `await aclose()`；或简化为「清引用 + GC」并改掉注释，别再宣称会释放连接池 | 中 |
| MIN-2218 | `async_http.py:271-285` | POST 三条分支都不带 `follow_redirects`（httpx 默认 False），GET 带 `follow_redirects=True`；`sync_req` 的两条孪生路径（requests 默认跟随、urllib 有 RedirectHandler）都跟随 → 异步 POST 遇 301/302 只拿到重定向页，不判状态码即返回 → `_loads_dict` 得 `{}` → 归因成「空响应/风控」。另 `content=` 与 `json=` 同传时 httpx 静默丢弃 `json_data`（与 urllib 分支「json 覆盖 data」方向相反，现无调用点同传，属 latent） | POST 也显式 `follow_redirects=True`（或写明刻意不跟随并在 3xx 返回空串 + warning）；`data` 与 `json_data` 同传时显式报错 | 高 |
| MIN-2219 | `async_http.py:352-354`（对照 `web_config.py:571-601`） | `get_response_status` 的 url 是**平台响应里解出的流地址**（外部可控），但只做 scheme 白名单、不做内网目标判定 → 被攻陷/被 MITM 的解析响应可让进程对 `http://127.0.0.1:6379/`、`http://169.254.169.254/` 发 HEAD + Range-GET，且 debug 日志回显 `status_code` 与 `content-type`，构成内网端口探测的小观测口。同仓推送侧已有 `_check_url_target(..., allow_local_targets=...)` 拒绝链路本地/云元数据/CGNAT，**两处口径不一致即缺口本身** | 复用 `_host_internal_reason` 判据（或下沉到 `utils` 与 `is_safe_http_url` 同层），默认拒绝内网/元数据目标，留显式 env 开关 | 中 |
| MIN-2220 | `ttwid.py:137-143`、`155-158` | 第 60 行的 `_ttwid_scopes` 与第 155 行的 singleflight key 都刻意**按代理分列**，但最外层快路（`141-143`）完全不看 `proxy_addr` → 首个成功出口的 ttwid 被所有其它出口在 TTL 内复用。抖音 ttwid 与出口 IP 强相关，表现为间歇性「200 + 空响应体」，而 `_ttwid_in_use` 作废链会把它误判成「凭据被拒」并连带清掉其它出口的正常值——分层键设计与最外层短路互相抵消 | 快路改按 `_cached_ttwid_by_proxy: dict[str, tuple[str, float]]` 取（键 `proxy_addr or ""`），三层 invalidate 逻辑不变 | 中 |
| MIN-2221 | `async_http.py:38-40`、`188-190`（对照 `main.py:486-502`） | `_client_cache_lock` 是**非重入** `threading.Lock`，而 `safe_exit` 是跑在主线程的 SIGINT/SIGTERM 回调、其中调 `close_all_clients_sync()` 取同一把锁；主线程自身也可能正持该锁（启动期 `warmup_ttwid` → `asyncio.run(get_ttwid())` → `async_req`）→ 信号落在临界区即**同线程自死锁**，表现为「Ctrl+C 后进程既不退出也不报错」。窗口只有几条 dict 操作、概率极低，但属 AGENTS「同一把非重入锁被嵌套持有」判定形态，且 mypy/basedpyright 均发现不了 | `close_all_clients_sync` 改 `RLock`；或信号处理器里只置标志、交 atexit，不在 handler 内取锁 | 中 |
| MIN-2222 | `ttwid.py:122`、`189`；`proxy.py:181` | 三处异常日志把 `e` 直接塞进 `{e}` 而无 `{type_name}`：Windows 下 `socket.timeout` 的 `str()` 为空 → 日志出现「自动获取抖音 ttwid 失败: 」空白尾巴（与 `MID-2251` 同族但不同文件/不同所有者，故独立计数，便于分批落地） | 三处补 `type_name=type(e).__name__`，模板与四语目录同步（参照既有 `{type_name}: {e}` 键名） | 高 |

### 5.2 录制链、ffmpeg 与字幕（MIN-2223 … MIN-2236）

| 编号 | 位置 | 问题与影响 | 修复方向 | 置信度 |
| --- | --- | --- | --- | --- |
| MIN-2223 | `main.py:1046-1049`、`1649-1650`、`1676-1677`、`1762-1763` | 4 处 `except Exception as e` 只写 `{e}` 缺 `type_name`；`asyncio.TimeoutError` 的 `str()` 恰为 `"()"`、`socket.timeout` 为空串 → 日志退化成「[B站直播]弹幕信息获取失败: 」。弹幕参数提取失败是 SRT 缺失的**唯一征兆** | 统一 `tr("[{cls}]…: {type_name}: {e}", type_name=type(e).__name__, e=e)`，与 `739` 已有写法对齐；四目录同步 | 高 |
| MIN-2224 | `main.py:162-173`、`90`、`99` | 死导入 `_run_ffmpeg_checked`（grep 全文仅命中 import 行）、`shlex`、`Mapping`，而紧接其上的注释正是「导入了却不用会让后来者误以为链路已接通」的 F-15 清理理由——自相矛盾。black/isort/mypy/basedpyright 默认均不报，故会长期存活 | 删三行；若为测试 patch 目标而保留，须在注释里写明理由与实际调用点 | 高 |
| MIN-2225 | `main.py:1110-1123` × `1099-1107` | 「达到单次录制时长上限（{limit}），结束本轮并**分段续录**」未参与 `_split_output` 判定，而 MID-N04 已把上限扩展到非分段形态 → 用户关闭分段时下一轮产出的是另一个独立文件。按此文案去分段目录找 `_001` 的排查会走空，且与 `1106` 注释语义不一致 | 按 `_split_output` 二选一措辞（两条 msgid 同步四目录），或改成不含「分段」的中性说法 | 高 |
| MIN-2226 | `main.py:3582`、`3628`、`3387`、`3397` | 四处一次性 `time.sleep` 绕过本文件已确立的「可打断等待」口径（`disable_record` 分支与轮末 x 循环都已改成逐秒 tick 三条件判定）→ Web 面板点「停止录制」后，处于这些分支的房间线程最坏继续滞留 `delay_default+5` 秒（熔断退避/无法识别地址分支为 `max(30, delay_default)`），期间监控数与线程数不回落，注释掉的坏地址迟迟不释放监控位 | 抽 `_interruptible_sleep(seconds)`（逐秒 tick + 三条件），四处统一调用 | 高 |
| MIN-2227 | `main.py:3278-3285` 与 `1296-1298` | 录后转码与 TS 收尾两处用**未转义的 stems** 做 `Path.glob`：`rstr` 排掉了 `* ?` 但**方括号是合法文件名且未被清洗**。该组本机实测 `fnmatch.translate('主播[超]清250922_183000_*')` 译成字符类，真实文件 `主播[超]清…_000.flv` **不匹配** → 分段 + 转 MP4 时 glob 返回空，只剩一条「未找到分段文件」告警，用户的 MP4 永不产出且看不出原因。同一 glob 写法在两处逐字重复（兄弟漏改） | 两处共用 `os.scandir` + `startswith(base_stem + "_")` + `endswith("." + ext)` 的纯字符串判定（或 `glob.escape`）；与 `MID-2207` 一次改完 | 高 |
| MIN-2228 | `main.py:1868-1870` | `_resolve_cc_163_com` 是**全表 53 个解析器里唯一不把 `proxy_address` 透传给 spider` 的一个**（`get_netease_stream_data` 签名接受 `proxy_addr`）→ 用户把 `cc.163.com` 写进「使用代理的平台」后页面/接口直连、而探针（`3573`）与 ffmpeg `-http_proxy`（`3675`）走代理，网络受限环境下表现为「明明配了代理仍取不到网址内容」，日志归因完全看不出是没走代理 | 补 `proxy_addr=proxy_address`；若刻意不走代理须加注释说明理由 | 中 |
| MIN-2229 | `main.py:2828-2838` | `_resolve_platform_stream` 对 `handler(ctx)` 不做隔离，而四个 cookie/token 回写点走整文件重写的 `utils.update_config`（其 `config.write(buf)` 未包异常；`config.ini` 含分隔符键名时 Python 3.14 抛 `InvalidWriteError`）→ **流地址已拿到**却整轮丢弃，落 `4026` except 并 `record_error(record_host)`，把一次本地写盘失败计入按 host 的熔断样本（与 MID-02 专门消灭的形态同族、换触发点）。另此处「不可达分支」的陈述已被 `SEV-2203` 证伪 | cookie/token 回写包 `except (configparser.Error, OSError)` 只告警（回写是缓存优化，不该影响本轮录制）；给 `handler(ctx)` 加一层 except | 中 |
| MIN-2230 | `main.py:3185-3187`（对照 `2729-2734`） | 摘除 `-reconnect_at_eof` 的判定用整串子串 `".m3u8" in real_url.lower()`，而 `SEV-03` 已确立「流地址键归属必须按 `_stream_path_suffix(url)` 只看 path」→ FLV 地址的 query 里带 `.m3u8`（CDN 回源路径参数形态）会被误判为 HLS 而丢掉 EOF 重连（正是斗鱼游客态 FLV ~70s 被掐的既有缓解）；反向（HLS path 不带 `.m3u8`）则保留该参数、复现 09-11 的零字节挂起。两个方向都静默 | 统一 `_stream_path_suffix(real_url) == ".m3u8"`；standalone 同口径（见 `MIN-2241`） | 中 |
| MIN-2231 | `main.py:2749`、`3380-3386` | 入日志的 `record_url`/`record_host` 未过 `mask_credentials`；`src/scheduler.py:500-512` 的 `host_of` 只在 `/ ? #` 处截断、**不剥 `user:pass@`** → 自定义流地址写成 `https://u:p@host/x.m3u8` 时凭据进 `PlayURL.log`/`streamget.log`。附带：凭据出现在熔断 key 里，等于同一 host 因凭据不同被拆成多个桶，削弱按 host 的熔断统计 | 两处改过 `mask_credentials`；更彻底的做法是在 `src/logger.py` 注册 patcher 统一过码，把「记得加」变成结构性保证 | 中 |
| MIN-2232 | `main.py:3490-3498`、`3512` | 两条**推给用户 IM 的正文**是裸字面量赋值 + `str.replace` 模板，既不经 `tr()` 也不是 `print`/`logger` 首参 → 提取器扫不到；实测 `grep -rn "直播间状态更新" i18n/` **零命中**，即 `language=en_US/en_GB/zh_TW` 下推送仍是简体中文。属 AGENTS「提取器扫不到彩色输出/对话框，新增文案须手工同步四目录」清单的**又一处漏网** | 改 `tr("直播间状态更新：{name} 直播已结束！时间：{time}", ...)` 并手工登记四目录 + 重编 `.mo`；把该形态补进 AGENTS 的同一条清单 | 高 |
| MIN-2233 | `main.py:3507-3508`、`3722`（消费于 `3819`/`3958`/`3990`）、`3938-3941`、`4768-4770` | 自然语言被提到变量里再 `print`/`print_colored`：`test_i18n_migration` 不变量① 只看实参子树（实参是 `Name`），而 `extract_i18n_strings.py` 的 `is_valuable` 明确把 `{rec_info}/{filename}` 这类纯占位符放行 → 双重盲区。实测 `i18n/zh_CN.po` 中 `正在直播中`/`准备开始录制视频`/`直播录制出错`/`本行包含未知链接` **各 0 命中**，而**音频孪生串**（`3779-3783` 用了 `tr()`）在目录里——同一条状态提示音频可翻译、三条视频路径不可翻译 | 三处改 `print(tr(模板, **kw))`，`rec_info` 只保留原始字段、在打印点插值；`print_colored` 两支改「常量模板 + tr 预格式化后整体传入」并手工补四目录 | 高 |
| MIN-2234 | `main.py:3285-3293` | 「未找到分段 FLV 文件，跳过转换」被 TS/MKV/MP4 路径复用（`_convert_after_record` 同时服务 TS 中断收尾与 FLV 录完），日志说 FLV 而 `seg_pattern` 实参里明明是 `..._*.ts` → 排查被引向「FLV 平台/直下路径」这一错误方向；注释还把它讲成「同一语义复用键」，与自己给出的证据互相矛盾 | 改成不带容器名的「未找到分段文件（{extension}），跳过转换」并四目录同步；或按 extension 选已有键、保持日志与模式一致 | 高 |
| MIN-2235 | `main.py:3265-3277` × `3974-3983` × `4006-4018` | `_convert_after_record` 的头注释自称「F-01 三条路径统一出口」，但 FLV 分支是 `if comment_end: return` **之后**才调它，而 TS 分支刻意在 `comment_end` 内补了一次（注释说明是为对齐口径）→ FLV + 「停止录制/URL 被注释」= 已录内容永久留在 `.flv`，用户开了「录制完成后自动转为 mp4」也拿不到 MP4 且无任何告警。属 F-01 统一化只在 TS 一侧落地的半修 | FLV 分支把 `_convert_after_record(...)` 提到 `if comment_end` 之前（或在 comment_end 分支同样调用后再 return）；MKV/MP4 已是成品容器，保持不调用并在注释写明 | 高 |
| MIN-2236 | `video_postprocess.py:288-304`、`src/main.py:1061-1074`；`ffmpeg_proc.py:207-230`；`srt_writer.py:106-118`；`danmaku_monitor.py:548-554`；`video_postprocess.py:242-270`/`114-158` | 六条基础设施残留：① `generate_subtitles` 全函数无 try/except 且**全仓不装 `threading.excepthook`**（grep 仅 `gui.py` 命中）→ 磁盘满/目录被改名/路径过长时线程静默死掉，traceback 只落 stderr 而被 `display_info` 的 `\033[2J` 清屏刷掉，房间仍显示「正在录制」；② `cleanup_all_ffmpeg_processes` 复核用 `p.poll()` 而非与告警同一事实，`_CLEANUP_WAIT_SECONDS=45` < 单进程 `timeout=30` × 分组串行的预算，把「正在终止」误报成「未能终止」并把死对象永久留在注册表——与其自身 `214-215` 注释「未确认 ≠ 未终止」正好矛盾；③ `SrtWriter.close()` 之后写线程可经节流重开以追加模式重开同一文件并把 `_index` 归 0 → 块号回绕与非单调时间轴（违反 MIN-24① 自己确立的不变量），且该句柄在写线程退出前无人关闭；④ stats 线程 `is_alive()` 判活与 `break` 之间存在微秒级退出竞态，而 `_ensure_stats_thread` 唯一调用点是 `room_started` → 房间表非空时 stats 可**永久停摆**（`msg_rate`/`online` 冻结）且无线索，下一次新房间前不自愈；⑤⑥ `converts_m4a`/`segment_video` 未纳入 MIN-04 的半成品清理、`segment_video` 还缺 `-n`（命名已存在时 ffmpeg 会问 Overwrite、无 stdin → 走满 600 秒超时才被 kill，正是 2026-09-12 审查 6.1 在 `converts_mp4` 上修掉的形态），二者生产零调用但仍是包内公开函数且有测试引用 | ① 写盘段加 `except OSError` + 按时间窗聚合的 warning（带 `type_name` 与产物路径）并仿 SrtWriter 节流重开；② 复核改用 `tracked` 的 `event.is_set()` 与告警同一事实；③ 加 `_closed` 终态位，close 后一律拒绝再开句柄；④ 线程退出前持锁自注销 `self._stats_thread = None`，或 `room_message` 也调 `_ensure_stats_thread`；⑤⑥ 把 `_discard_partial_output` 与 `-n` 下沉进 `_run_ffmpeg_checked`，或在文件头标注「启用前须先补 MIN-04 清理」 | 高（①②⑤⑥）/中（③④需特定交错） |

### 5.3 面板、配置写入与前端（MIN-2237 … MIN-2246）

| 编号 | 位置 | 问题与影响 | 修复方向 | 置信度 |
| --- | --- | --- | --- | --- |
| MIN-2237 | `web/app.js:72-75`（对照 `src/web_config.py:1054-1063`） | `isSensitiveField` 把 `expiry\|timeout\|有效期\|过期` 例外表提到**最前**短路，而后端 `is_sensitive_item` 的例外只作用于键名分支、不作用于节白名单 → `[Cookie] 抖音cookie有效期` 这类键后端脱敏、前端判非敏感并渲染成明文 `text` 输入框（值仍是掩码，凭据未泄，但用户会误读成「这项没被保护」）。AGENTS 要求两侧「同集合 + 同顺序」，属潜在分叉 | 前端改 `if (SENSITIVE_SECTIONS[section]) return true; if (NOT_SECRET_KEY_RE.test(key)) return false; return SENSITIVE_KEY_RE.test(key);` 与后端逐字对齐 | 高 |
| MIN-2238 | `web/app.js:1367`、`1380` | `downloadFile` 绕开 `api()`（要 blob）也绕开了 MID-39 的 `apiError` detail 解析，用 `res.statusText` 抛错——现代浏览器对服务端 reason phrase 恒为空串（HTTP/2 直接丢弃）→ toast 渲染成「下载失败: 」，用户既不知是权限、路径还是文件被删，也拿不到可报障信息。同文件 `toggleRecording`/`saveConfig` 都有可读文案，唯独此路径漏配 | 把 detail 提取抽成 `parseErrorDetail(text, status, fallback)` 复用，`!res.ok` 时先 `res.text()` 过一次再抛 | 高 |
| MIN-2239 | `web/app.js:1253`（注释）与 `1280-1301` | `saveConfig` 首个失败即 `return`，跳过头注释专门要防的「半份配置落盘更难排查」的善后：后续行**保持用户刚输入的值、无任何未保存标记**，`configBackup` 停留在保存前快照。用户看到「配置页仍是我填的样子」极可能直接切走 → 生效配置与界面显示长期不一致（例如分段时长写进去了、认证开关没写进去） | `return` 前也执行一次 `loadConfig()`（或给失败/未提交的行加 `row-failed` 类与行内提示），并保留一条常驻「本次已应用 n 项，第 m 项失败，剩余未提交」状态行 | 高 |
| MIN-2240 | `web/app.js:37-45`（结论注释在 `116-117`） | `_tokenStore()` 在 sessionStorage 不可用时回退 localStorage，而注释写「token 不再持久化到磁盘，关闭标签页即失效」；且 `setToken('')` 只清当前首选存储 → 日后 sessionStorage 恢复可用时 `getToken()` 只读它，磁盘上那份旧 bearer **既读不到也清不掉**（服务端 `_purge_expired_tokens` 会废弃，但浏览器里明文副本长期在）。前端测试环境恰好只注入 localStorage，即回退路径正是被测路径 | 写入时记录实际落地的存储名、`setToken('')` 对两个存储都 `removeItem`；或把「sessionStorage 不可用时退化为磁盘持久化」写成显式已接受的权衡 | 中 |
| MIN-2241 | 根 `index.html:14-19`（判据 `src/web_api.py:1108-1113`、`.dockerignore:117-118`、`build_exe.py:79-96`） | 该文件**未被任何链路服务**（`create_app` 只挂 `web/index.html` 与 `/web`；打包 `datas` 不含它；dockerignore 排除），却仍是引入无 `integrity`/`crossorigin` 的 jsDelivr 脚本（hls.js 1.7.2 / flv.js 1.6.2，钉版本 ≠ 钉内容）的活跃文件，且不经过 `web_api.py:472-485` 的 CSP 中间件。用户若按 README 顺手双击本地文件打开，等于在没有 CSP、没有 nosniff、没有同源判定的环境里执行远端脚本，页面还把用户输入的流地址直接喂给 hls.js/flv.js | 二选一：① 移到 `docs/` 或 `tools/` 并在 README 注明「本地手动打开的调试播放器，与面板无关」+ 补 `integrity`；② 确认无人用则删除（须同步 `.dockerignore` 该行与项目结构文档）。另 `standalone` 侧 `.m3u8` 未 lower 的孪生漂移见 `MIN-2247` | 高 |
| MIN-2242 | `web_api.py:686-687`（对照 `web_config.py:1195-1197`） | `add_room` 直接 `open(..., "a")` 前不补末行换行，而同仓写入者 `append_config_line` 专门写了「末行无尾换行时先补一个」→ 若 `URL_config.ini` 末行无 `\n`（编辑器删掉尾回车、或 `delete_line` 后本就无尾换行），新房间会粘到上一条之后变成 `https://…111https://…222`，**两个房间同时坏掉**，端点仍回 `{"ok": true}` | 追加前先读末字节（或在持锁段 `readlines()` 后统一走 `_atomic_write_text`，与 `update_room_quality` 同一手法） | 高 |
| MIN-2243 | `web_api.py:717-722`、`766-771` | `SEV-05` 的「删除不得谎报成功」只补在 `delete_room`；`update_room`/`toggle_room` 仍把 `update_file` 的返回值丢掉并无条件 `{"ok": True}`——而 `update_file` 的契约是「失败时返回 `old_str`」（`config_io.py:96`/`100-101`）→ 日志/配置目录只读、文件被占用或磁盘满时面板提示「已切换/已启用」而文件字节未变，房间仍按旧状态录制（占并发槽与磁盘） | 按 `update_file(...) != new_str`（或重解析核对目标行）判失败，走 `_log_internal_error` + 500，与 `delete_room` 同口径；更彻底是让 `update_file` 返回 bool 并统一三个调用点 | 高 |
| MIN-2244 | `utils.py:610-620` | `remove_duplicate_lines` 两处 `open` 都缺 `newline=""`：universal newlines 把 CRLF 读成 LF、写回又是 `\n` → `main.py:4340` **每次引擎启动无条件**把 `URL_config.ini` 的行尾全量改写，使 `config_io.delete_line` 的 MI-11 修复（「写回走 `newline=""` 不做翻译」）被这条旁路整体抵消；同时 `line.strip()` 丢掉行首缩进并按 strip 后内容去重（`url` 与 `url ` 视为同一行而**静默删掉一条**）；异常分支用 `encoding=None`（宿主 locale）读、按 utf-8-sig 写，UTF-16/GBK 文件会被静默转成乱码后再原子落盘，房间配置不可逆损坏 | 两处 `open` 加 `newline=""`、按原行尾逐行回写（保留原行不 strip，仅用于去重键）、失败回退分支同样显式指定编码而非 locale | 高 |
| MIN-2245 | `web_api.py:577-585`（缓存实现 `1212-1226`） | 免鉴权端点 `/api/auth/status` 仍每请求 `read_web_config` 全量解析 config.ini，而 WD-06 的 mtime+size 缓存只对中间件生效；`/api/login` 与 `/api/config` 也各有一份未缓存的全量读。`Host` 校验放行任意 IP 字面量与无点单标签名（`web_config.py:876-879`）→ 能访问端口即可低成本把读盘放大为磁盘 IO 压力（这正是 WD-06 加缓存的理由） | 数据端点统一走 `_read_web_config_cached`（写侧已有 `_invalidate_web_cfg_cache` 兜底），并给免鉴权端点加与登录限流同型的 per-IP 预算 | 中 |
| MIN-2246 | `web_api.py:15`；`web_config.py:1066-1068` | 两处注释与实际相反：① 头注释 ⑦ 写「写接口需 Bearer；**读接口**/静态资源放行」，实际开启认证后 `/api/config`、`/api/logs`、`/api/files`、`/api/rooms` 等读接口同样必须持 Bearer（中间件白名单与 method 无关）——按注释评估泄露面会得出与实际相反的结论；② `read_config_safe` 注释写「写入仍用 `utils.update_config`」，而 `PUT /api/config` 实际走 `update_config_line` + `web_config` 自己的原子写（`utils.update_config` 只由引擎侧 cookie 刷新使用）——**这条错误陈述正是 `SEV-2211`（mode 回灌缺失）能被漏掉的直接原因**：按注释去查 `utils.atomic_write_text` 会以为加固已生效 | ① 改写成「非白名单路径一律需 Bearer，白名单 = …」的枚举式表述；② 改为「写入走本模块 `update_config_line`（行级）；`utils.update_config` 只用于引擎侧 cookie 刷新」 | 高 |

### 5.4 GUI 与推送（MIN-2247 … MIN-2252）

| 编号 | 位置 | 问题与影响 | 修复方向 | 置信度 |
| --- | --- | --- | --- | --- |
| MIN-2247 | `gui.py:783`、`2301`、`2454`、`2459`、`2639`、`3403`；`web.py:231-242` | 该组用 AST 抽 `messagebox.*` 常量实参 × 四目录核对：22 条实参里 16 条四语齐备，**6 条正文四目录 0 命中**；`web.py` 的 `_insecure_msg`（305 字符，「无认证 + 非回环」的严重安全警告）同样 0 命中。英文用户在「彻底退出」「没有直播间地址」「拒绝启动后的破例放行警告」这些最需要看得懂的界面上只拿到中文；`_insecure_msg` 还经 `logger.warning` 落盘，loguru 侧无 tr 包装，即使补进目录那一份也不翻译 | 6 条正文 + `_insecure_msg` 补进四份目录并重编 `.mo`；logger 那一路改 `logger.warning(i18n.tr(_insecure_msg))`（无占位符即可直接查表） | 高 |
| MIN-2248 | `gui.py:726-753`（调度）、`685-708`（`_load_config`）、`659`/`786`（销毁点） | `AdvancedSettingsWindow` 一个 `after_cancel` 都没有（实测 `grep -n "after_cancel" gui.py` 只命中主窗口 5 个 job）。`root.after` 注册在解释器而非控件上，「取消 → destroy」之后已排期的回调照样跑：`_watch_config_file` 若此刻发现磁盘变了且编辑器无改动 → `_load_config()` → `self.config_text.delete(...)` 抛 `TclError` → 被 `except Exception` 兜成 `messagebox.showerror("错误", f"加载配置文件失败: {e}")`，在录制主窗口之上弹出一个**没有父窗口、文案完全误导**的错误框 | destroy 前保存并 `after_cancel` 该 job id；或 `_watch_config_file` 开头 `if not self.window.winfo_exists(): return`（同文件 `2408` 已有此手法） | 中 |
| MIN-2249 | `gui.py:3496-3505`、`3528-3529` | `_cleanup_zombie_ffmpeg` 的 `subprocess.run(["taskkill", ...])` 不判 `returncode` 即宣布「已清理」（taskkill 找不到 PID 返回 128 并把提示写进 stdout，而 `capture_output` 收到的内容被完全丢弃）；POSIX 的 `pkill` 同形（无匹配 rc=1）。连带 `if not found: "未发现需要清理的 ffmpeg 进程"` 在 win32 上**永不可达**。于是「GUI 说已清理」与「其实没杀掉（权限不足/PID 已换/taskkill 被策略禁用）」两种状态在日志里不可区分——而这正是本函数存在的唯一目的 | 取 `.returncode`，仅 `rc == 0` 才记「已清理」，否则把 stdout 提示脱敏后附上；`found` 反映真实结果 | 高 |
| MIN-2250 | `gui.py:201-207`、`840-868` | ① 用 `ctypes.windll`（AGENTS「Python 版本」条要求新代码统一 `ctypes.WinDLL`，`web.py` 正是范本）且 `GetConsoleWindow` 未声明 `restype=c_void_p`——默认 `c_int` 会截断 HWND，当前只用于 `bool()` 尚不致错，但其余调用同样无 argtypes；② 恢复控制台用 `ATTACH_PARENT_PROCESS(0xFFFFFFFF)`：从 cmd/PowerShell 直接起 GUI 时恰好是同一控制台，但 GUI 自己拥有控制台时（`start` 派生、explorer 双击带控制台的 exe、计划任务）父进程无控制台 → 恢复失败且无告警，此后本进程 loguru 控制台 sink 与 `print` 全写向无效句柄，用户视角是「停止一次录制后 GUI 终端再也看不到日志」 | 换 `ctypes.WinDLL("kernel32", use_last_error=True)` 并按 `web.py` 声明 argtypes/restype；恢复前先保存原始句柄，`AttachConsole` 回不去时改 `AllocConsole` + 重配流，失败时带 `GetLastError` 落一条 warning | 中 |
| MIN-2251 | `msg_push.py:417-423`、`433-439`、`442-444` | ntfy 三处失败日志仍传 `_mask_url(_api)`，而钉钉/Bark/微信三处已按 `MID-58` 改为 `_mask_url(api, mask_last_segment=True)`（该处注释即「主机名从来不是判据——密钥的位置才是」）。ntfy 恰恰是**路径末段就是频道口令**的渠道（`https://ntfy.sh/<topic>`，匿名订阅者读到 topic 即可收通知、也可抢先发假消息）→ topic 明文进 `streamget.log`（轮转保留多份、求助时通常整包上传） | 三处统一加 `mask_last_segment=True`；或声明一份「渠道 → 末段是否敏感」常量表，避免逐个漏 | 高 |
| MIN-2252 | `msg_push.py:248-254` | `send_email` 的 `finally` 只吞 `smtplib.SMTPException`，但 `SMTP.quit()` 内部 `docmd("QUIT")` 等 221 响应、socket 带 `timeout=10`，服务端不回 221 让 recv 超时即抛 `socket.timeout`（`TimeoutError`/`OSError` 子类，**不是** `SMTPException`）→ 在 finally 里抛出会**替换掉** try 块已算好的成功返回值：邮件其实已发出，上层 `push_message` 却拿到未捕获异常、既无成功清单也无失败清单，用户表现为「重复收到同一封开播通知」 | `except (smtplib.SMTPException, OSError): pass`（PEP 758 下无 `as` 可不带括号），或整体兜住并 `logger.debug` 说明「会话未优雅关闭，连接已丢弃」 | 中 |

### 5.5 i18n 目录、构建与仓库卫生（MIN-2253 … MIN-2268）

| 编号 | 位置 | 问题与影响 | 修复方向 | 置信度 |
| --- | --- | --- | --- | --- |
| MIN-2253 | `i18n.py:387-402`（`tr` 降级路径）；`tests/test_i18n_migration.py:169` | 三道锁分别覆盖「模板占位符 == kwargs」与「运行时模板 ⊆ zh_CN 目录键」，**没有任何一条**比较 en_US/en_GB/zh_TW **译文内部**的占位符集合。AGENTS 记载的 `zh_TW.yaml` `{msg_2}` 生产事故当时是推送整条崩溃（loud），`MI-23` 改成回退原文后同类漂移只会表现为「繁体用户看到的仍是简体」，与「该 key 本来没译」完全同形。该组按四目录 × 全量条目实测当前 **0 漂移**（即现在无 bug），但下一次目录手改无任何东西会拦 | 在 `test_catalogs_share_same_keyset` 旁加一条：逐 key 比较 `set(re.findall(r"\{([^{}]*)\}", msgid))` 与四份译文，非空即列出 `file:key`（纯静态、无需运行 GUI） | 高 |
| MIN-2254 | `i18n.py:254-268` | `init_gettext()` 实测生产代码**零调用**（只命中定义与 `tests/test_i18n.py`），而它返回**绑死在 `locale_name` 上**的 gettext 函数、不随 `set_language()` 重读 `_tr`——恰好是本模块「热切换」契约的反面；其 `bindtextdomain`/`textdomain` 还是进程级全局副作用，会经 `gui.py` 的 env 传染录制子进程树（`265-267` 注释自己就记载过这类污染的危害）。保留一个「看起来能用、用了就静默失去热切换」的公开函数，是下一个改动踩坑的最短路径 | 删除（连同 `test_init_gettext_returns_callable`）；若必须保留兼容面，改名并在注释首行写明「不随 set_language 生效，禁止用于业务路径」 | 高 |
| MIN-2255 | `pyproject.toml:134-170`（black exclude）、`172-200`（isort extend_skip）对照 `233`（mypy `"typings"`）、`334`（basedpyright `"**/typings"`） | `typings/`（customtkinter/execjs/pystray 共 15+ 个 `.pyi` 第三方存根）被 black/isort 扫描，却在 mypy/basedpyright 中被排除。AGENTS 把「black exclude / isort extend_skip / mypy exclude / basedpyright exclude / coverage omit」列为必须逐处同步的**五个点**，本项缺两个，且 black 的 `include = '\.pyi?$'` 会连 `.pyi` 一起查 | black exclude 加 `\| typings`、isort extend_skip 加 `"typings"`，与另三处对齐 | 高 |
| MIN-2256 | `AGENTS.md:1289-1292` 对照 `src/scheduler.py:24-34`、`55`、`131` | `AGENTS.md` 关于「`src/scheduler.py` 侧尚无回指注释（待该文件负责人补）」的陈述已被证伪——实测该文件现有 4 处指向 standalone 的点名。`AGENTS.md` 被定位为「长期约定的唯一事实源」且是代理动手前必读，失真会让后来者误判「防线还没建」而重复补注释（无意义 diff），或反过来认为副本同步义务是单向的、跳过逐方法 diff（正是它想防的单边修改）。按该文件自己的 2026-09-17 例外条款，被证伪的条目应**就地改正**并保留一行带日期修订注 | 正文改成「两处已互相点名（`grep -n standalone src/scheduler.py` = 4）」，并把核对口径改成可机检的命中数而非写死陈述 | 高 |
| MIN-2257 | `scripts/patch_i18n_2026_09_12.py:231-237` + `245-252` | 一次性补丁脚本（自述已耗尽）注释写「returncode 非零透传给上层（CI 可见）」而实现是 `return 0`；且用裸 `["python", "scripts/compile_po.py"]` 而非 `sys.executable`——AGENTS 硬约束「语法/编译检查一律使用项目 venv 的 Python 3.14」，Windows 上裸 `python` 可能是 py launcher 的 3.13。`.mo` 编译失败时脚本报成功，四语目录与 `.mo` 静默分叉（只靠 `compile_po.py --check` 事后拦）。该文件本身仍留在 `[tool.mypy].files` 的 `scripts` 面内被长期检查，按 AGENTS「测试收尾清理临时脚本」口径属残留物 | 三选一但必须让陈述与实现一致：`return res.returncode` + `[sys.executable, ...]`；或按收尾约定删除该脚本（成果已在四份目录与 CODE_WIKI 落档，审计留痕不需要可执行副本） | 高 |
| MIN-2258 | `src/ffmpeg_install.py:115-118`、`148-151`、`287` | 把「与产物同主机、同一 HTTPS 通道取回的哈希文档」称作**独立信任根**：`_fetch_official_sha256(url + DOC_SUFFIX)` 的 `url` 就是产物所在的 `www.gyan.dev`，期望值与实际文件同源，主机/CDN 被替换时两者一并被换、校验归零。这与同层 `node_install.py:34-42`（文档取 nodejs.org、产物走 npmmirror，「镜像只加速不背书」）以及 `build_exe.py:446-450`（同问题的正确自述）相互矛盾，会让后来者以为 Windows 运行期已具备来源认证 | 陈述降级为「同源一致性校验（防传输截断/缓存污染），不构成来源认证」，并在 AGENTS 三类钉定条目里注明「gyan.dev 无签名可用」对应的残余风险与可接受理由；若要真加固，可核对 gyan.dev 与 `build_exe` 已钉定的 `windows-x64/ffmpeg` 哈希是否同代，把发布面官方值作为第二通道 | 高（机制）/中（是否属有意接受） |
| MIN-2259 | `scripts/douyin_live_recorder_standalone.py:1209` 对照同文件 `1399-1405` 与 `main.py:3185` | 副本的 `validate_stream_url` 判 `.m3u8` **大小写敏感**，而同文件命令构造两处已在 2026-09-12 审查改成 `.lower()` 并写明「大小写敏感致 HLS 挂起回归」→ 上游下发 `.M3U8` 时该 URL 落进非 m3u8 分支：走 content-type 启发式 + `_confirm_get_ok`，而 m3u8 在多家 CDN 上 HEAD 恒回 4xx，命中 AGENTS 记录的「探针误杀可用源」分支，非末位候选直接被拒、整轮回退或放弃。主程序侧不受影响，属**副本独有的行为漂移** | 与命令构造统一为 `".m3u8" in url.lower()`（两处共用一个小写化局部变量更佳）；`--selftest` 补一条 `.M3U8` 用例锁判定 | 中 |
| MIN-2260 | `scripts/smoke_test.py:70-86`、`367-372`（消费点 `scripts/_ci_web_smoke.sh:85-88` → `ci.yml`） | 「零检查项」退 0：`load_config` 对 dict 形态取 `typed.get("checks", [])`，把键写成 `check`/`targets`、或 `checks` 整段被清空都是「合法但空」，脚本 0 断言、退 0，`_ci_web_smoke.sh` 原样透传 rc，CI 的「Web panel smoke test」步骤报成功。当前 `smoke_web.json` 确有 2 条检查，但面板真起不来时只有就绪等待那条 curl 能发现；一旦 `web_host`/端口口径改动使 `/health` 探针仍过而接口断言整段消失，门禁就查了个空气 | `main()` 里 `if not checks: sys.exit(2)`；`load_config` 要求 `"checks"` 键存在（缺键即 ValueError）；`_ci_web_smoke.sh` 侧断言报告 JSON 的 `summary.total > 0` | 高 |
| MIN-2261 | `scripts/check_coverage.py:80-85` | `MIN-19` 把「无数据」升级成 rc=2 是对的，但**只判数据文件是否存在**：「有数据且是上上周的」仍是通过路径（本工作区就同时存在 `.coverage` 与 `coverage.json` 两份历史产物）。删掉一批用例、或把某模块整体改名后（`_find_module_coverage` 的第②步后缀匹配还可能拿同名新路径顶替），只要旧数据里那 6 个路径的百分比还在就照报 PASSED。CI 里 rc 由前一步 `pytest --cov=src` 保证，故受害面是**本地 DoD 回路** | 加新鲜度断言：数据文件 mtime 早于 `src/`、`tests/` 下最新 `.py` 即 rc=2 并提示重跑 `pytest --cov=src`；可选再核对 coverage JSON 的 `timestamp` | 高 |
| MIN-2262 | `scripts/check_version.py:189-195`（同形 `57-68` 的 Dockerfile 分支、`135-148` 的 po 分支） | 「检查对象消失」被判成 `[OK]`：`extract_webapi_version()` 只在匹配到 `FastAPI(... version=...)` 时产出结论，正则未命中即返回 None 并打印 `[OK] ...（跳过）` → 「把 `version=` 从 `FastAPI(...)` 里删掉」「把 LABEL 的 version 行整块删掉」这两种最省事的破坏都让门禁更绿。对照 `sync_version.py::check_all` 已按 2026-09-12 审查 6.7 修成「正则失配即判失败」——**同一仓内两条检查口径不一致** | None 分支进 `errors`（或要求 `--allow-absent` 才放行），与 `check_all` 的「先判命中再判等」同构；Dockerfile 分支同口径 | 高 |
| MIN-2263 | `.github/workflows/ci.yml:398-399`（job env）与 `476-482`（消费点） | `CODECOV_TOKEN` 被放进 **job 级** env，而它只被 `Upload coverage to Codecov` 一步消费（那一步已单独写了 `token: ${{ secrets.CODECOV_TOKEN }}`）→ 该 secret 被注入「执行仓库测试代码 + pip 安装的第三方包」的整个进程树：任何用例、conftest、被 `pip install -r requirements.txt` 拉进来的包都能从 `os.environ` 读到并外发。fork PR 下 GitHub 不注入 secrets，所以同仓 push/PR（含被投毒的依赖，见 `deps-audit` 存在的原因）才是这条的暴露面 | 删掉 job 级 `env`，改步骤级传参（ci.yml 里 macOS brew 已是「消费点局部传参」的既有口径）；条件表达式若受 step-level `if` 的 secrets 可用性限制，用 `vars`/outputs 过渡 | 中 |
| MIN-2264 | `.github/workflows/trivy.yml:25-36`、`43-52` | trivy 的 job 既无 `timeout-minutes`（`ci.yml` 顶部已把「每个 job 显式 timeout」列为统一策略）、也没有 `retry` 包装，而它偏偏做本仓最重的一次外网动作（完整 `docker build` + trivy 扫层），周一 cron 卡死即白烧额度。另一半更值得写进报告：trivy-action 的 `exit-code` 未设（默认 0），CRITICAL/HIGH 公告只进 Security 标签页、job 恒绿；又因 `ci-summary` 不含本 workflow，任何人把它当「镜像漏洞门禁」都是误读（真正的清单门禁是 `ci.yml` 的 `deps-audit`） | 补 `timeout-minutes: 30`；要当门禁就显式 `exit-code: 1` 并在文件头写明与 `deps-audit` 的分工，只当信息就在本文件与 AGENTS 注明「advisory only，不作 required check」 | 高 |
| MIN-2265 | `tests/test_start_record_command_golden.py:38`、`402-407`、`421-423` | 黄金基准的再生开关把「非空字符串」当「真」：`_REGEN = bool(os.environ.get("GOLDEN_REGEN"))`，于是 shell/CI 里导出 `GOLDEN_REGEN=0`、`=false`、`=off` 任取一值即 20 条比对全部走 `return` 判通过，并在 session 末尾**用当前实现覆盖 `tests/golden/start_record_commands.json`**——此后任何命令行错位（例如 `-segment_format` 两值再被互换，正是 09-04 的 P0 形态）都成为新的「基准」。且没有任何用例断言基准形状（键数、每条 command 非空且含 `-i`），「被重写成一堆空列表」也不会单独变红 | 判定改 `os.environ.get("GOLDEN_REGEN","").strip().lower() in ("1","true","yes")`（与 `src/config_bool.py` 同集合，别再造第三套布尔口径）；加 `test_golden_snapshot_shape_is_sane` 断言条数与非空命令含 `-i` | 高 |
| MIN-2266 | `src/utils.py:99-106`；`tests/test_utils.py:759-775`；`tests/test_bili_e2e.py`；`tests/test_sync_http.py:20-35`；`tests/conftest.py:52-70` | 五条测试/钉定卫生问题合并：① JS 钉定的「未登记即放行」方向没有对账锁——`_check_js_hash` 首行 `if not expected: return`，两个分组独立指出用例只锁「表里的键都有文件」与「表 == 硬编码 5 项」，缺「目录里每个 `.js` 都在表里」→ 新增（或被投放）第 6 个签名脚本时静默不校验而门禁全绿（AGENTS 第③类钉定面悄悄缩小）；② `tests/test_bili_e2e.py` 实测 `test_` 函数数为 0，全部逻辑在 `main()` 里靠 `__main__` 守卫，而它**是离线用例**（自己 `struct.pack` 造 B站帧），与 AGENTS 允许「手动 + 需活房间」的 5 个 live_collector 不同类 → 帧协议→`_decode_packet`→collector→SrtWriter 的端到端串联无任何自动执行，断言可无人运行地腐烂，而文件存在继续向读者 advertise「e2e 已验证」；③ `TestGetOpener` 两条用例都只 `assert opener is not None`，把 `_get_opener` 两个分支合并成恒返回 insecure opener 也同时绿（所幸同文件 `334-344` 用对象同一性锁住了真正裁决，故属噪音用例 + 误导性命名而非唯一防线缺失）；④ `conftest` 的凭据缓存隔离 autouse fixture 用 `except Exception: return` 静默放弃重置 → `src.spider` 一旦 import 期异常或被摘出 `sys.modules`，四模块级 `_cached_*` 与紧随其后的 `_ttwid._cached_ttwid` **全部不重置且不报错**，去重类用例退化为跨用例命中旧值（H-2 要消灭的形态，只是从「没清」变成「清了一半且静默」）；⑤ `download_ffmpeg_master` 的头注释承诺「失败一律返回 False（不抛）」，而 `_stream_download` 只捕 `requests` 系异常，`open(zip_path,"wb")` 的 `OSError`（磁盘满/无权限/路径失效）会穿出 `except FfmpegDownloadError` → 传到 `install_ffmpeg_windows()` → 启动期 `check_ffmpeg()` | ① 补 `test_every_executable_js_is_pinned`（`glob("*.js") <= set(_JS_SHA256_EXPECTED)`，两侧相等）+ 未登记分支加 warning；② 把 `main()` 拆成 `test_bili_frame_to_srt_end_to_end(tmp_path)`（不再碰 `_out_e2e`），保留 `python <file>` 直跑入口调用该函数；③ 删两条或改 `is _opener_secure`/`is _opener_insecure` + `verify_mode` 断言；④ 改 `except ImportError: raise`（收集期真错就该红）或把 import 提到 fixture 顶部不做容错；⑤ 契约与实现对齐：`_stream_download` 外层再包 `except OSError` 归一为 `NetworkError`，或删去「不抛」承诺 | 高 |
| MIN-2267 | `src/ffmpeg_master_download.py:63-71`、`54-57`、`107-116`、`110`、`233-239`、`396` | 新模块的六条小缺陷合并：`ChallengePageError` 定义后**全仓零引用**（死码，探测路径改用字符串状态返回，该异常类是设计中途改向的残留）；`_PROBE_TIMEOUT = 20` 与紧邻注释「探测挑战页只需 1 字节；给短超时，失败即换源，不值得久等」不符（两候选串行 = 启动期最多阻塞 40 秒）；`_looks_like_html` 的 `except Exception: return False` 把**读失败**判成「不是 HTML」→ 探针误报 `ok`；首次 TOFU 记账只用 `logger.debug`（`:270`）而 `ffmpeg_install.py:250-252` 的同类降级按要求用 warning，同一天两份实现严重度口径不一致；TOFU 基准文件按 `build_id` 分文件、**永不修剪** → 程序目录无界增长（每次上游发新构建就多一个）；`import os` 在模块头与 `__main__` 块各一次。另 `download_ffmpeg_master` 的 `shutil.rmtree(target)` 在 copytree **之前**删除既有 `ffmpeg/` 目录（与 `ffmpeg_install.py:356-360` 同形，非新发明，但副本各一份意味着收口要改两处） | 删 `ChallengePageError`；`_PROBE_TIMEOUT` 降到 3-5s 或改注释；`_looks_like_html` 的 except 分支返回 True（读不通即不可信）；首次记账升 warning 并写明「本次安装无可比对期望值」；写新基准时删除同前缀旧文件（保留 1 份）；合并重复 import；把「先删旧目录再复制」下沉成两份共用的一个函数 | 高 |
| MIN-2268 | 仓库状态（`git status` 实测） | 本轮取证时 `src/ffmpeg_master_download.py`（402 行，被 `src/ffmpeg_install.py:29` **模块级硬 import**，并经 `main.py:121` 进入主链）、`tests/test_ffmpeg_path_preference.py`、`tests/test_check_runtime_pins.py`、`scripts/spike_arm64_static_ffmpeg.sh` 四文件仍**未被 git 跟踪**。若此刻以 `git commit -am`（只提交已跟踪文件的修改）提交并推送，新克隆与 CI 会在 import 链上直接 `ModuleNotFoundError`，而本地一切正常——典型「本地绿、CI 红」 | 提交前 `git add` 这四个文件并核对 `.dockerignore`/打包 `datas` 是否需要相应条目（`src/` 不被排除 → 新模块会进镜像，须确认这是期望）；`scripts/spike_*.sh` 已在 `PROPOSAL` 与 `CODE_WIKI` 里论证为长期复用工具，按 AGENTS 口径不属一次性脚本，可保留 | 高（当前状态事实） |

## 六、改进建议与修复优先级

### 6.1 优先级批次

排序依据：**用户可见失效 > 凭据外泄 > 发布链可分发不可信产物 > 门禁假绿 > 静默降级 > 归因线索 > 文档与卫生**。同批内文件互不重叠，可按 `AGENTS.md`「并行分组修复」口径并行派发（单代理 ≤10 项、文件集互斥）。

| 批次 | 内容 | 项数 | 前置 / 依赖 | 验收判据 |
| --- | --- | --- | --- | --- |
| **第 0 批（提交前动作，阻塞一切）** | `MIN-2268`（四个新文件未 `git add`，模块级硬 import 会让新克隆 `ModuleNotFoundError`）；`SEV-2216` 的 `socksio` 声明与 `h2` 可用性自检 | 2 | 无 | `git status --short` 无未跟踪源文件；`python -c "import h2, socksio"` 通过或在缺位时产出 warning |
| **第 1 批（正在发生的用户可见失效）** | `SEV-2201` 类型契约、`SEV-2202` `%` 模板、`SEV-2203` http:// 落不到解析器、`SEV-2204`/`SEV-2205` 静默漏录、`SEV-2206` 磁盘棘轮、`SEV-2227`/`SEV-2228` 面板不可用与假绿 | 8 | 无 | 每条按 6.3 补锁后 `pytest` 全绿 0 警告；**并跑真实 URL**（至少抖音/斗鱼各一，含一个开分段录制的房间） |
| **第 2 批（凭据与 TLS 外泄面）** | `SEV-2210` 掩码 camelCase、`SEV-2211` 弱化原子写、`SEV-2212` SMTP 不校验证书、`SEV-2213` 打包带凭据、`SEV-2214` XHS 跳转、`SEV-2215` B站 WS 远端 host、`SEV-2217` 代理凭据入日志 | 7 | 无 | 覆盖面断言从「调用了掩码」升级为「值确实消失」；`PUT /api/config` 后 `config.ini` 的 mode 仍为 0600（POSIX 侧断言）；发布目录断言不含 `config/` |
| **第 3 批（门禁假绿，决定后续所有批次的可信度）** | `SEV-2219` 丢退出码、`SEV-2220` 测试走真实网络、`SEV-2222` TOFU 失败开放、`SEV-2223`~`SEV-2226` 四条测试/文档可信度、`MID-2260`~`MID-2265` 六条锁缺口 | 12 | 第 0 批 | 每条都有「违规见证 + 合规反向见证 + 扫描根非空见证」三件套；`run_gates.py` 在故意制造收集错误时必须 rc≠0 |
| **第 4 批（供应链，需维护者决策）** | `SEV-2218` Windows 第二条下载源、`SEV-2221` GPG 验签不可达 | 2 | **须先由维护者在 6.4 的三个处置中选一** | 决策写进 `PROPOSAL_2026-09-22_binary-trust-policy.md` 并同步 `AGENTS.md`；锁的判定范围扩到「运行期可达的全部下载常量集合」 |
| **第 5 批（录制链健壮性）** | `SEV-2207` 线程池 atexit 次序、`SEV-2208` SEV-N01 收尾、`SEV-2209` JS 无超时、`MID-2201`~`MID-2209` | 12 | 第 1 批（共用 `check_subprocess` 改动面，勿并行） | `tests/test_record_failure_feedback.py`、`test_ffmpeg_reconnect_args.py`、`test_record_container.py` 全绿；退出路径实测「归档先于清理完成」 |
| **第 6 批（静默降级与归因）** | `MID-2210`~`MID-2226` 中未随第 1~2 批落地的条目、`MID-2242`~`MID-2247`、`MIN-2201`~`MIN-2222` | ≈40 | 各批之后 | 「未开播/已下播」正常轮次仍刻意静默（`test_documented_offline_stays_silent` 必须保持绿）——**新增告警前先判定该轮次是否属正常轮次** |
| **第 7 批（i18n 与文档同源）** | `MID-2248`~`MID-2253`、`MIN-2232`~`MIN-2233`、`MIN-2247`~`MIN-2254`、6.2 全部 | ≈20 | 最后做（触到四份目录与 `.mo`） | `extract_i18n_strings.py` 报 0 缺失；`compile_po.py --check` 绿；写进文档的条数按 AGENTS 口径给「命令 + 时刻 + 两种口径」 |

### 6.2 必须先改约定 / 文档、再改代码的六处

`AGENTS.md` 是本仓长期约定的唯一事实源，以下改动若不同步写回该文件，下一轮改动必然重犯：

1. **`SEV-2218` 的条款冲突**：现行条款写「Windows 运行期只有 gyan.dev 一条自动路径，新增第二条须先满足官方公布哈希判据」。代码已引入不满足该判据的默认源。**先由维护者决定改条款还是改代码**，两者一致后再落实现；无论何种处置，`src/ffmpeg_install.py:44-50` 的模块头陈述必须与实现相符。
2. **`SEV-2226` 的两条安全辩护**：F-12 条目「`sync_req` 调用点全部位于 `src/spider.py`」与「依赖管理」用同一前提为 `urllib3>=2.7.0` 辩护，实测该模块生产不可达。按 AGENTS 自身的「被证伪的事实性陈述必须就地改正、不得保留错误版本 + 追加更正」口径改正文并保留一行 `[YYYY-MM-DD 修订：旧结论 X 已被推翻]`。
3. **新增「下载源白名单」约定**：把「任何新的出站二进制/脚本下载点，必须登记进一份可机检的白名单常量，且门禁按该名单反查全仓 `http*` 字面量」写成硬约定。本轮 `SEV-2218`、`SEV-2220`、`MIN-2266`① 三个形态的共同成因就是「锁按文件而非按可达面」。
4. **新增「脱敏键表」约定**：`_SECRET_KEYS` 采用**黑名单 + 左边界断言**，天然漏 camelCase（`SEV-2210`）。应写明：新接入平台时若其凭据参数是 camelCase，必须同步该表并在 `TestMaskCredentialsCoverage` 增加「值必须消失」的断言；建议同时引入 camelCase 边界分支，把「记得加」变成结构保证。
5. **新增「注释不得声明未做的修复」自检口径**：本轮 3 条（`SEV-2208` 说 stop 已进 finally、`SEV-2220` 的 hermetic 约定、`SEV-2225` 的「本仓未使用」）都是**注释自述与代码相反**误导了后续判断。建议在「完成定义」第 4 步加一句：修复类注释必须附可复核判据（grep 命令或断言名），否则不得写「已修」。
6. **`补-N02` 遗留的三条约定仍未落笔**（代理归一只在构造前、凭据落盘值与 scheme 前缀二选一、`Set-Cookie` 只能合并不整体替换）：本轮 `SEV-2214`、`MID-2221` 表明这三条正是当前缺陷的直接成因，应优先写回。

### 6.3 回归锁补齐清单

| # | 待锁行为 | 建议锁形态 | 关联条目 |
| --- | --- | --- | --- |
| 1 | `get_url` 对 `list[str]` 与 `list[dict]` 两种元素都不抛 | 接缝用例 + 变异验证（删 str 分支即红） | `SEV-2201` |
| 2 | 分段模板除末位序号占位符外不含 `%` | AST/正则断言扫 `_build_record_output_path` 全部分支 | `SEV-2202` |
| 3 | `PLATFORM_HOST` 每项在**剥去 scheme 后**仍被某解析器命中 | 表驱动静态锁 | `SEV-2203` |
| 4 | 播放中房间不得被判未开播（h265-only / `null` 值 / `liveID` 为 int） | fixtures 覆盖三种响应形态 | `SEV-2204`、`SEV-2205` |
| 5 | 磁盘恢复后 `exit_recording`/限流标志必须可复位 | 行为用例（置位→恢复→断言重新拉起） | `SEV-2206` |
| 6 | 退出路径顺序：归档先于 ffmpeg 清理、且不被线程池 join 阻塞 | 注册次序静态锁 + 桩任务计时 | `SEV-2207` |
| 7 | `check_subprocess` 的 finally 必含采集器 stop、零字节分支必先收尾后 return | AST 锁（仿 `test_ffmpeg_reconnect_args.py`） | `SEV-2208`、`MID-2242` |
| 8 | JS/execjs 调用链必须有超时预算 | 断言 `run_js_async` 签名含 `timeout` 且调用点传值 | `SEV-2209` |
| 9 | 掩码：断言**凭据值从输出中消失**，而非「调用了 `mask_credentials`」 | 参数化覆盖面表补 `wsAuth`/`tk`/`accessToken`/`msToken`/`verifyFp` | `SEV-2210`、`MID-2219`、`MIN-2231` |
| 10 | `config.ini` 每次写回后 mode 不变、且 fsync 被调用 | 用 `tmp_path` + `os.stat` 断言；三处原子写共用同一实现的静态锁 | `SEV-2211` |
| 11 | SMTP 两条路径均传入 `context=` 且 `check_hostname` 为真 | 桩 `smtplib` 捕获 kwargs | `SEV-2212` |
| 12 | 发布目录内不得存在 `config/`、`logs/` | `make_zip` 前置断言 + `unzip -l` 检查 | `SEV-2213`、`MID-2254` |
| 13 | 跳转/响应派生地址跨 host 时不得携带 Cookie | 桩 http transport 断言第二跳无 `cookie` 头 | `SEV-2214`、`SEV-2215`、`MID-2231` |
| 14 | `ImportError` 级环境故障不得归一为空响应 | 断言缺 `h2`/缺 socks 依赖时产出 warning 且非 `""` | `SEV-2216` |
| 15 | 回调文案必须已脱敏 | 断言 `on_close`/`on_reconnect` 实参不含 `user:pass@` | `SEV-2217` |
| 16 | 「注册了签名的槽位必然触发验签」 | 用出厂表驱动 `_download_file` 的行为锁 | `SEV-2221` |
| 17 | `run_gates`：pytest 未跑/崩溃时必须非零退出 | 桩 pytest 返回 rc=4/5 两例 | `SEV-2219` |
| 18 | 测试 hermetic：任何出站层都被 autouse fixture 桩掉 | 反向锁（真发请求即红）+ `.mjs`/VBS 的 skip 可见性 | `SEV-2220`、`MID-2264` |
| 19 | 黄金快照须记录 `platform`/`danmaku_args`；`GOLDEN_REGEN` 只认显式真值 | 扩展快照字段 + 基准形状断言 | `SEV-2224`、`MIN-2265` |
| 20 | 卫生门禁 R1 须能识别字符串形态 patch；并禁止「测试内自实现同名锁/限流」 | 违规 + 合规双向见证 | `SEV-2223`、`SEV-2225` |
| 21 | 跨文件同源锁：排除目录清单、下载源白名单、UA 常量、布尔 token 集合 | 键集对比用例（仿 `test_ffmpeg_path_preference.py`） | `MID-2256`、`MIN-2255`、`MID-2263` |

### 6.4 结构性建议（消除本报告的成因，而非只消除症状）

1. **给「可达的下载/执行面」建立单一登记表**。本轮三条严重（`SEV-2218`、`SEV-2221`、`SEV-2222`）的共同成因是「下载源散落在多个模块、而所有锁都按文件与常量名设防」。建议一份 `DOWNLOAD_SOURCES` 表（键 = 运行时/槽位，值 = URL 白名单 + 完整性方式 ∈ {官方哈希, 官方签名, 第4类, TOFU} + 默认开关），`check_runtime_pins.py` 与测试都从该表反查全仓，使「新增一条源」无法只改一处。
2. **把「唯一实现」的宣称变成可检的事实**。`config_io` 注释称 `utils.atomic_write_text` 是唯一实现，而 `web_config` 仍有第二份（`SEV-2211`）；`_pad_list`/`clean_name`/`should_prepend_bundled_ffmpeg_dir` 的孪生副本已由 `AGENTS` 用互点名 + 9 格矩阵锁住，是**本仓已验证有效的做法**——建议对「原子写、glob 匹配、m3u8 判定、UA 常量、bj_id 解析」这五处同样加跨文件等价锁。
3. **门禁的默认失败方向应是「没查 → 红」**。`SEV-2219`、`MID-2261`、`MID-2262`、`MIN-2260`、`MIN-2261`、`MIN-2262` 六个形态都是「谓词拿不到输入时返回通过」。建议在 `AGENTS.md` 把「任何门禁脚本，凡存在『解析不到对象即视为合规』的分支，一律必须补一条命中数见证」写成硬约定，并让 `run_gates.py` 汇总时打印每条门禁的**扫描对象数量**（当前只打印 PASS/耗时，读者无法判断覆盖面）。
4. **前端与录制端之间的字符串契约需要一层机器可读协议**。`SEV-N06` 三轮未落地、`SEV-2228`/`MID-2240`/`MID-2239` 的假绿，共同点是「面板靠解析文本/猜测后端语义」。建议后端状态与日志一律携带**结构化字段**（如 `status="unavailable"`、`engine_alive`、画质降级事件用 `#DLRQ|` 前缀键），前端只按字段判、永不按自然语言子串判。
5. **`async_req` 的返回契约应区分「无内容」与「发不出去」**。`SEV-2216`、`MID-2212`、`MIN-2225` 的共同根因是失败被归一成 `""`，而 `""` 又被上游解读成「风控/未开播」。建议返回 `(content, error_kind)` 或让调用方显式声明失败语义；至少把 `ImportError`/`UsageError`/超时/DNS/TLS 五类与「200 空 body」区分开。

---

## 七、门禁与测试可信度专项结论

1. **门禁基线**：`PYTHONUTF8=1 python scripts/run_gates.py --keep-going` 于本轮取得 **8/8 全绿（28.1s）**，其附带的 pytest 告警摘要兜底亦 PASS（183.4s，0 条）。**本章的前提是：以上全部 28 项严重结论都是在该绿色状态下取得的。**
2. **逐门禁可见性评估**：

| 门禁 | 能查什么 | **查不到什么（本轮实证）** |
| --- | --- | --- |
| black / isort（含 `PYTHONUTF8=1` 与 silent-skip 判失败） | 格式、导入序、静默跳文件 | 语义完全无关：`SEV-2201`~`SEV-2205` 全部能通过 |
| mypy（不带路径，`[tool.mypy].files` 全量）+ `--platform linux` | 类型、未绑定名、Any 泄漏 | `play_url_list` 被 `cast` 为 `list[dict[str,str]]` 而**实际装 str**（`SEV-2201`）；`cast` 不做运行时检查是设计，但意味着 cast 密集区的契约完全无守护 |
| `check_annotations.py`（注释密度 + 符号可达性） | docstring、密度、被删符号的残留调用点 | 被 `cast`/`getattr`/动态引用掩盖的契约错配；其排除表落后 13 项目录（`MID-2256`），且第三方目录同名绑定会**削弱**可达性判定 |
| `compile_po.py --check` / `check_version.py` / `check_runtime_pins.py` | `.po`↔`.mo` 同步、版本动态化、钉定表结构 | 「运行时新增模板未落目录」只由 `test_i18n_migration` 不变量③ 兜；`check_version` 把「检查对象消失」判 `[OK]`（`MIN-2262`）；`check_runtime_pins` 的矩阵解析在测试里被 autouse 整体桩掉（`MID-2260`） |
| `run_gates.py` 自身 | 逐字执行「格式化命令」清单 | **不检查 pytest 是否真的跑了**（`SEV-2219`）；不打印各门禁的扫描对象数，覆盖面不可自证 |
| `pytest` + 逐模块覆盖率 | 单元行为 | ① 402 行的新下载模块**零引用**且自动豁免覆盖率门禁（`MID-2259`）；② 8 个平台的解析结果与流层取值之间的**接缝**无测试（`SEV-2201`）；③ 覆盖率表只列 6 个模块且**无回归锁**（`MID-2261`） |
| `basedpyright`（本地补充，CI 不跑） | 未绑定、可能为假、冗余 ignore | 与 mypy 同受 `cast` 遮蔽；且不在 CI 回路，漂移只在本地可见 |
| CI 新增的两条「warnings summary 即失败」 | 告警出现但 rc=0 | 该步自身的失败（`|| true` + `2>/dev/null`）——见 `SEV-2219` |
| 前端 `.mjs` 锁 / VBS 行为锁 | 面板 DOM 行为、脚本进程匹配 | **在 CI 上可能整体 skip 而与 pass 不可区分**（`MID-2264`）；掩码用例只断言调用形状（`SEV-2210`） |

3. **「测试自实现被测逻辑」仍存在活违例**：`tests/test_concurrency.py` 是本仓明令禁止形态的当前实例（`SEV-2222`），且其取代者 `test_concurrency_rate_limit.py` 已存在——即该文件是「被取代后遗留却仍在计数」。卫生门禁 R1/R2/R3 有双向见证（值得肯定），但对字符串形态 patch 与「测试内定义同名锁/限流」两条规则**不判**（`SEV-2225`）。
4. **值得保留并推广的做法**（本轮实测确认有效）：`test_run_gates.py` 的正反两例 + 真实子进程驱动；`test_ffmpeg_reconnect_args.py` 与 `test_record_container.py` 的 AST 语义锁 + 命中数见证；`test_spider_hardening.py` 的双向棘轮（`BARE_JSON_LOADS_CEILING` 与「`_safe_loads` 内仍有 `json.loads`」）；`test_concurrency_rate_limit.py` 只打桩网络层、驱动真实限流与去重；`test_ffmpeg_path_preference.py` 的 9 格判据矩阵（每条「不让位」判据都配「只缺它」的格子）；`test_srt_writer.py` 的真实 `-->` 注入断言。**这些是 6.3 那 21 条锁应当长成的样子，直接照抄即可。**
5. **本轮的一个方法论提醒**：某分组在其「已核实不构成问题」清单中，按 `main.py:991` 的注释把 `SEV-N01` 判为已修，而主会话读回源码后推翻（`SEV-2208`）。**修复类注释不可作为回归判据**，只可作为线索。

---

## 八、逐文件定位索引

| 文件 | 严重 | 中等 | 轻微 |
| --- | --- | --- | --- |
| `main.py` | `SEV-2202`、`SEV-2203`、`SEV-2206`、`SEV-2208` | `MID-2201`～`MID-2209`、`MID-2213`、`MID-2226`、`MID-2242` | `MIN-2223`～`MIN-2235`、`MIN-2242`～`MIN-2243` |
| `src/stream.py` | `SEV-2201`（读取侧） | `MID-2227`～`MID-2230` | — |
| `src/stream_select.py` | `SEV-2201`（消费侧）、`SEV-2210`（受害日志点） | `MID-2231` | `MIN-2208`、`MIN-2219` |
| `src/spider.py` | `SEV-2201`（写入侧）、`SEV-2204`、`SEV-2205`、`SEV-2210`、`SEV-2214` | `MID-2210`～`MID-2226`、`MID-2245`（上游） | `MIN-2201`～`MIN-2216`、`MIN-2218`、`MIN-2224` |
| `src/utils.py` | `SEV-2210`（根因）、`SEV-2216`（execjs 侧） | `SEV-2209` 根因、`MID-2245` | `MIN-2244`、`MIN-2266`、`MIN-2267` |
| `src/async_http.py` | `SEV-2216` | `MID-2227`（探针侧） | `MIN-2217`～`MIN-2221` |
| `src/ws_client.py` | `SEV-2217` | `MID-2232`、`MID-2247` | — |
| `src/sync_http.py`、`src/proxy.py`、`src/ttwid.py`、`src/cookie_cache.py`、`src/http_config.py`、`src/weverse_auth.py`、`src/ab_sign.py` | `SEV-2226`（sync_http 死码） | `MID-2233`、`MID-2265` | `MIN-2220`～`MIN-2222` |
| `src/scheduler.py`、`scripts/douyin_live_recorder_standalone.py` | — | `MID-2257` | `MIN-2256`、`MIN-2259` |
| `src/collector.py`、`src/danmaku_monitor.py`、`src/srt_writer.py`、`src/ffmpeg_proc.py`、`src/log_archive.py`、`src/video_postprocess.py`、`src/recorder_status.py`、`src/notify.py` | `SEV-2207`、`SEV-2209` | `MID-2243`～`MID-2246`、`MID-2247` | `MIN-2236` |
| `src/platforms/`（`bilibili`、`douyin`、`douyu`、`huya`、`twitch`、`_xbogus`、`_tars`）、`src/proto/` | `SEV-2215` | `MID-2244`、`MID-2245` | `MIN-2210`（twitch 侧）、`MIN-2266` |
| `src/web_api.py`、`src/web_config.py`、`src/config_io.py`、`src/config_bool.py`、`src/logger.py` | `SEV-2211`、`SEV-2228`（后端侧） | `MID-2234`～`MID-2236`、`MID-2241` | `MIN-2238`～`MIN-2246` |
| `web/app.js`、`web/index.html`、`web/style.css`、根 `index.html` | `SEV-2227`、`SEV-2228` | `MID-2237`～`MID-2241` | `MIN-2237`～`MIN-2241` |
| `gui.py`、`web.py`、`msg_push.py`、`i18n.py` | `SEV-2212` | `MID-2248`～`MID-2253` | `MIN-2247`～`MIN-2254` |
| `src/ffmpeg_install.py`、`src/ffmpeg_master_download.py`、`src/node_install.py` | `SEV-2218`、`SEV-2222` | `MID-2258`、`MID-2259` | `MIN-2258`、`MIN-2267`、`MIN-2268` |
| `build_exe.py`、`scripts/*.py`、`.github/**`、`Dockerfile`、`docker-compose.yaml`、`pyproject.toml`、`requirements.txt`、`.dockerignore`、`StopRecording.vbs` | `SEV-2213`、`SEV-2219`～`SEV-2222` | `MID-2254`～`MID-2256`、`MID-2260`～`MID-2264` | `MIN-2255`～`MIN-2262`、`MIN-2263`、`MIN-2264` |
| `tests/**`（含 `tests/frontend/`） | `SEV-2220`、`SEV-2223`～`SEV-2225` | `MID-2260`～`MID-2265` | `MIN-2265`～`MIN-2266` |
| `AGENTS.md`（仅计陈述失真） | — | — | `MIN-2255`、`MIN-2256`（连带 `SEV-2226` 的两条辩护） |

---

## 九、已回源复核、确认**不构成问题**的实现（供后续审查者复用）

以下条目在分组深读中被提出、经回源确认为本项目的正确或刻意设计，**不得作为缺陷上报**（本轮新增部分与 `CODE_REVIEW_2026-09-21.md` 第九章合并使用）：

1. **ffmpeg 输入侧四条致命坑全部仍在位**：`-reconnect*` 三项均带取值且全在 `-i` 之前；`.m3u8` 判定已 `lower()`；`-headers` 按 `-i` 锚点插入；`-tls_verify`/`-http_proxy` 仅在对应形态注入；`-protocol_whitelist` 不含 `file`/`concat`。五条保存类型分支的输出参数/路径/执行骨架全部经四个单一定义点，`-segment_format` 零裸字面量。
2. **录制并发槽纪律**：`recording_semaphore` 在 `Popen` 之前 acquire、`finally` 恰好 release 一次；`acquire` 成功到进入 `try` 之间只有 3 条不可能抛错的赋值；放弃等待分支的 return 位于 `try` 之前，不会凭空释放。全仓 51 个 `with semaphore:` 持有者均为 `_resolve_*` 叶子函数，无 resolver 互调、无嵌套自死锁。
3. **探针语义全套守住**：`_throttle_probe` 与 `_recheck_delay` 的锁内计算/锁外 sleep/预约无漂移、退避窗口与主循环周期联动、mark/clear 键与 `-i` 逐字对称、HEAD 非 2xx → Range GET 全覆盖（含 404）、401/403 重试一次、末位放行含 `text/html` 与异常分支、候选序列去重与 h265 剔除后判末位、`_is_recordable_url` 三态。
4. **代理归一**：`async_req:255`、`get_response_status:365`、`sync_req:179`、`weverse_auth:54`、`platforms/twitch.py`、`room.py` 三处、`spider.py` 全部先过 `handle_proxy_addr`；`stream_select.py:667`/`:1007` 两处 `httpx.Client` 构造均已归一（`SEV-N05` 无残留半边）。
5. **画质档位既有约定守住**：蓝光子档位折叠进 `BD`、虎牙 ratio 数值命名与就近降级 tie-break、斗鱼 2 档本地回退且保持 `is_live=True` 契约、`_pick_master_variant` 取最高 BANDWIDTH 及其保守回退、`DOUYU_RATE_TO_CODE` 多对一取最高档属既定口径。
6. **装饰器与返回契约**：`_loads_dict` 回 `{}`、`_warn_api_abnormal` 只告警不上抛、平台解析失败回 `{"is_live": False}` 均为刻意设计；`@decorator` 与 `def` 全部相邻（CR-12 两处实例已修且注释保留）；返回 str/tuple 者一律 `_or_none` 且调用点显式判空后解包；全仓裸 `json.loads` 余 1 处（Twitch GQL 数组响应），符合棘轮。
7. **并发与锁**：无模块级 `asyncio.Lock()`；无跨循环 `aclose()` 协程；`ResizableSemaphore` 容量与已持有分离、收缩不回收、允许 0；`PlatformBreaker` 的 src 实现有探针租约 + `_probe_seq`/`_probe_owner` 双门控、熔断计数增量维护、`import time` 在顶层；`web_api` 四把锁全链路同序、无嵌套自死锁；`main.file_update_lock` 实测为 `RLock`（AGENTS 的可重入性判定口径正确）。
8. **面板安全面既有强度（本轮逐条复核未发现新旁路）**：token 用 `secrets.token_urlsafe(32)` + `compare_digest` + 精确吊销 + 改密清表；PBKDF2 盐随机/200k 迭代/上下界钳制；登录端点为同步 def（走线程池）+ IP 与全局双预算限流；路径遍历用 `realpath` + `commonpath` 逐条目复核并跳过悬空链接、`FileResponse` 恒 attachment；`run_script` 用 `shlex.split` 无 shell 且唯一 RCE 落点已黑名单；CSP/nosniff/X-Frame-Options 在放行与拒绝两路均加；无 CORS 放行；免鉴权名单为**精确等值**匹配（无法用 `/api/login/../config` 命中）；监听地址判定基准只能来自进程（`SEV-N03` 修复在位），两步旁路搜索未发现新出口。
9. **前端 XSS 与脱敏回环**：`app.js` 全部 13 处 `innerHTML` 的动态成分均过 `esc()`（覆盖 `& < > " '`，属性位与文本位两种上下文均安全），未转义的只有 `int()` 产出的计数与本文件字面量；`toast`/`login-error`/`#log-stream`/无认证横幅一律 `textContent`；token 只走 `Authorization: Bearer`、从不进 query；`saveConfig` 是**唯一**的 `PUT /api/config` 出口，`'***'` 无条件跳过、`data-masked` 判定覆盖后端两条脱敏来源；四套内嵌目录键集经 `test_quality_ui.mjs` 机检相等；`#rooms-view .data-table` 的 `table-layout:fixed` 定宽与省略约束逐条吻合且未新增列。
10. **定时器与缓冲上界**：`toastTimer`/`sseSource`/`dmTimer` 均先 clear 再启动、两个视图入口成对调用 stop；`dmMessages` 有 300 条截断；`api()` 带 10s AbortController 与 2/5/10/30s 退避；`_probe_backoff`/`_probe_last_seen`/`_breakers`/`_rooms`/`create_var`/`_ffmpeg_processes`/边车队列均有界或可回收。
11. **弹幕链既有不变量守住**：`collector.stop()` 与 `_run()` 的反向序握手、`_shutdown` 的 `wait_for` 限时、WD-02 有界队列 + 丢弃计数、协议解码边界（B站 `packet_len<16`、斗鱼整帧推进、`_tars._need`/`_assert_progress`、LIST/MAP 伪造尺寸早拒）、SRT 分片命名与 `_%03d`/`_%02d` 剥离、`proxy=None` 未被破坏（Twitch 显式传代理是注明的范围例外）、MI-01 三处 WS 解压全部限长；`_sanitize_srt_text` 覆盖面完整（落进 SRT 的外部字段只有 `user_name`/`message` 且均已清洗，礼物/SC/medal 文案提前 return 不进字幕）。
12. **签名与凭据的边界**：抖音弹幕 `signature` 不 `quote()`（上游一致、回归锁在位）；`_xbogus` 的 `XBOGUS_ALPHABET` 实测 64 字符无重复、定长 16 输出；`ab_sign` 的 SM3 经独立实现三条 KAT 逐字符核对为标准值（该组自陈「静态读码时曾疑 `c=`/`g=` 漏折叠，实测证明其判读错误」）；`_loads_dict`/`_warn_api_abnormal` 只回显 `code`/`status`/`msg`，`AID`/`BNO`/`BJID`/`visitor_st`/`hls_authentication_key`/`mcData`/`sec_key` 均不入日志，且用例侧有「token 不得出现在任何一条日志里」的断言；网易 weapi 的双层 AES-CBC + RSA（明文反转、`zfill(256)`、`secrets.choice` 生成 key、每请求新生成）与标准方案逐条吻合。
13. **发布链三层防线仍在位**：`_is_pinned` 只看形状（占位/大写/截断一律未钉定）、`_slot_is_gated` 为唯一判定入口且 `check_runtime_pins.py` 调它而非自判、`--require-pinned` 在下载前 `SystemExit`、`slot=` 为必填关键字参数、第 4 类「光有标记不满足 + 声明即拒下载（两侧都终止）+ 环境变量注入同样生效」均有 AST/行为锁；macOS/Linux ffmpeg 槽位保持占位属约定内状态，不作为问题。
14. **`StopRecording.vbs`**：实测前 2 字节 `FF FE`、整体 UTF-16 LE 解码正常、未被 `.gitignore` 的 `*.vbs` 吞掉（否定规则生效）；三层进程匹配完好、`appDir` 深度守卫、只认字面量 `-y`。残余偏差（工作树与 HEAD 均为 LF-only 而 AGENTS 配方含 CRLF 转换）属下次重编码时补回，不计缺陷。
15. **`_app_root()`/`sys.modules["main"]` 别名/`signal.signal` 主线程注册**：`import main` 时 `sys.modules["main"]` 在模块体执行前已绑定，守卫不会把 web/gui 进程里的 `main` 指错；信号注册均在主线程，不触发 `ValueError`。
16. **`_rename_prefixed_entries` 的 POSIX `os.rename` 覆盖语义**：初判为「静默毁历史录像」，细算后不成立——目标名含录制起始秒时间戳，冲突需同主播同秒，实际不可达；目录级冲突由 `ENOTEMPTY` 抛错并被告警捕获。
17. **`_resolve_custom_stream` 每轮随机 UUID 主播名**：是为阻断主播名自动同步死循环，录制期阻塞在 `check_subprocess` 内、每轮只建一个目录，非无界增长。
18. **`if global_proxy or proxy_address:` 才取流（9 个海外平台）与「以 `anchor_name` 为空判取址失败」**：均为 `AGENTS.md` 已登记的既定语义。
19. **「额外使用代理录制的平台」在全局代理关闭时仍用 `proxy_addr_bak`**：键名即「额外**使用代理**录制」，属按平台覆盖全局开关的设计，非漏洞。
20. **`get_cached` 硬编 `DEFAULT_TTL`、且返回缓存 dict 原引用**：实测现无调用方覆盖 `ttl=`、亦无消费者改写返回的 cookie 字典，只记为潜在 API 风险，不作缺陷。
21. **UA 双端一字不差**：`main.py:3655-3657` 的默认移动 UA 与 `stream_select.MOBILE_UA` 经逐字符比对相等；版本基准（Chrome/141、Edg/141、Firefox/148、Android 14 Pixel 8）在各请求头中一致；`_TWITCH_WEB_UA`/`browser_version` 派生自同一常量（MID-50b 在位）。
22. **文件名注入面**：`clean_name` 的 `rstr` 覆盖 `/ \ : . ? * " < > | & #` 等，`.` 与 `。` 均在集内故 `..` → `__` → strip → 「空白昵称」，无目录穿越、无 Windows 尾点/尾空格形态；保留设备名与 60 字符截断顺序正确。**唯一例外是 `%`，见 `SEV-2202`（它是格式串注入而非 shell 注入）。**
23. **`migu.js` 与 Python 侧的 argv 契约**：`process.argv[2]` 与 `run_node_script_async(["node", "-", *args])` 的下标实测一致；非零退出经 `check=True` 收敛为 `ProgramError`，不泄漏 `CalledProcessError.cmd`；`Object.fromEntries(searchParams)` 走 `CreateDataProperty`，`__proto__=` 不触发 setter，无原型污染；`liveme.js`/`haixiu.js` 的 `sign()` 出参键集合与 spider 侧 `pop`/`cast` 逐一对应。
24. **本轮主动筛除的臆测**（记录以免下一轮重复提出）：斗鱼 `DOUYU_RATE_TO_CODE` 的 `SD/LD` 只有 1 次尝试（已是最低档）；`_same_origin_flv` 在虎牙恒返回 None（主机名与后缀均不同源）；`config.ini` 的 `[Cookie]` 读取有 try/except 兜底；`buvid3` 的 debug 日志属设备标识而非会话凭据；`web/app.js` 的 `window.loadFiles` 等看似未引用实为事件委托里的裸全局调用，**不是**死代码；`showView` 首屏 `#dashboard-view` 未带 `hidden`（登录前一瞬闪现，`showLogin` 会 hideAll）；`configBackup` 在保存失败后变陈旧（重复保存幂等，无数据损坏）。

---

## 十、总结性结论

1. **架构层面未见劣化，缺陷集中在「接缝」与「自证」两处**。`AGENTS.md` 沉淀的并发模型、探针语义、四类单一定义点、发布链钉定、门禁 UTF-8 覆盖在代码中逐条成立（第九章 24 组）。本轮 28 项严重没有一项是「设计错」，但其中 **12 项是「验证体系以为已经管住、实际管不到」**——这是本仓当前最主要的风险形态。
2. **最高优先级是三件事**：① `SEV-2201`（8 个以上平台目前在播也永远录不上，且写入侧契约被测试钉死，必须改读取侧）；② `SEV-2202`（主播名含 `%` 时开分段录制 100% 失败，并把健康线路推进退避与熔断，本机 ffmpeg 已复现）；③ `SEV-2216`（`h2`/`socksio` 缺失时全部平台解析静默失败，且 `AGENTS.md` 自己的 venv 恢复命令就会造出该状态——本工作区当前正处于这一状态）。三者都会以「主播没开播 / 网络异常」的假象掩盖，用户与日志都看不出根因。
3. **安全侧必须优先处置的六项**：`SEV-2210`（脱敏黑名单被 camelCase 绕过，斗鱼完整拉流直链与嗨秀私有凭据长期落盘）、`SEV-2211`（面板每次写配置都把 `config.ini` 权限退回 umask）、`SEV-2212`（邮件推送的 TLS 完全不校验服务器证书，授权码可被 MITM）、`SEV-2213`（本地打包把真实凭据复制进对外 zip）、`SEV-2214`/`SEV-2215`（两条「响应决定目标主机 + 携带用户凭据」的外泄链）。共同点是**上一轮为「房间 URL」建立的收口口径没有覆盖到「响应派生地址」与「写盘/打包面」**——建议按 6.2 第 3、4 条把「可达的下载/执行面/外发面」登记成单一事实源。
4. **`SEV-N06` 三轮未闭环，且本轮在其同族又发现新实例（`MID-2253`）**。它不是「难修」，而是「需要先定义一个跨模块的机器可读契约」（6.4 第 4 条）。建议本轮起把它从「代码待办」提升为「约定先行」：`AGENTS.md` 定义前缀/字段协议 → `recorder_status.py`/`main.py`/`gui.py`/`web/app.js` 同批改 → 补锁。若继续留在「已知未修」清单里，下一轮审查还会再报一次。
5. **不建议做的事**（与本轮部分低置信建议相反，理由已在第九章与 `AGENTS.md` 记录）：为「保险」关掉探针客户端 keepalive；把 standalone 副本强行对齐成同一实现（刻意不等价，但**语义漂移须登记**，见 `MID-2257`）；为兼容 <3.14 给 `except` 加括号；用 `filterwarnings`/捕获异常跳过的任何方式让 isort 静默跳过、`deps-audit` 报错、i18n 三件套或本轮的 `SEV-2219`/`SEV-2222`「变绿」；把 `_PINNED_RUNTIME_SHA256` 回填本地自算哈希以求 CI 变绿；把抖音/快手等平台的响应派生地址直接交给第二跳请求「因为省了一次解析」。
6. **完成定义**：本报告第 1、2、5 批落地后必须按 `AGENTS.md` 第 2 步跑真实 URL 增量验证（至少一个受影响平台，附脚本名/脱敏 URL/PASS-WARN-FAIL/消息数或 SRT 字节数），并把结论写进 `CODE_WIKI.md` 与 `CODE_WIKI_EN.md` 的更新日志条目；**仅单测绿不视为验证过**。**本报告的落地前置（尚未执行，待授权）**：6.2 那六处须先由维护者定稿并写回 `AGENTS.md` 与 `CODE_WIKI*.md` 更新日志（DoD 第 4、6 步）——其中 C-1～C-3 属产品取舍，审查侧不代为决定；本报告未修改任何生产代码、配置或既有文档。

---

## 附录 A ｜ 上一轮（2026-09-21）严重项回归核查

复核口径：只读回代码确认修复是否**仍在位**，未做全量重跑，也未重新验证需真机的部分。

| 原编号 | 修复现状 | 本轮相关发现 |
| --- | --- | --- |
| SEV-N01 `check_subprocess` 收尾三处漏口 | **半落地**：采集器声明已提到 try 之前，但注释声称的「`stop()` 移入 finally」未做；零字节早退与 finally 条件过窄两处仍未落地 | `SEV-2208`（含「注释把未做的写成已做」）、`MID-2242` |
| SEV-N02 PopkonTV `Bearer` 双前缀 | **在位**：写入侧回裸 token、读取侧 `removeprefix` 后统一补前缀，三面断言（落盘无前缀 / 请求头恰一次 / 存量脏值自愈） | 无 |
| SEV-N03 「非回环 + 无认证」不变量可被两步旁路 | **在位**：监听地址判定基准只来自进程（`app.state.bind_host/port`），`web_host` 不再是判据；本轮专门搜索其它「判定基准可被受控 API 改写」的出口，未发现新旁路（`web_allowed_hosts` 可写但改它本身要先过同源+Host 判定，不构成闭环） | 相邻新面：`MID-2234`（`web_token_expiry` 无上下界可自锁）、`MID-2241`（关认证无二次确认） |
| SEV-N04 淘宝 `Set-Cookie` 整体覆盖用户 Cookie | **在位**：改为按 `_TAOBAO_TICKET_KEYS` 白名单**合并**；`5925` 行的旧表述已加「已被证伪」修订注 | 但**同类信任边界另有一处未收口**：`SEV-2214`（跳转目标 host 不受限）、`MID-2221`（AcFun 双 Cookie 头使「透传优先」不成立） |
| SEV-N05 `select_source_url` 代理未归一 | **在位**：`:667` 与 `:1007` 两处 `httpx.Client` 构造均先过 `handle_proxy_addr`，7 条回归锁在位 | 同族新面：`MID-2209`（直下腿 UA）、`MID-2228`（cc.163 唯一未透传 `proxy_addr` 的解析器） |
| **SEV-N06 GUI 把简中文案写死在日志解析判据里** | **未落地**：全仓无任何落地注释、无机器可读前缀机制，三条 pattern 原样在位 | `MID-2253`（状态复核 + 同族新实例 `web.py:297` 把中文常量值插进已翻译模板） |
| 上一轮各编号的「只改一半」残留（本轮显式对应） | 见右列 | MID-N44（update/toggle 恒回 ok）→ `MIN-2243` 仍未修；MID-N47（WD-21 半修）→ `MID-2249` 确认仍在且无锁；MID-N57（脱敏双判据）→ `MID-2236` 读写侧仍不同源；MID-N68（黄金替身丢实参）→ `SEV-2224` 未落地；MID-N69（`run_gates` 入口无锁）→ 部分落地，但新增 warnings 兜底自身丢 rc（`SEV-2219`）；MID-N70（i18n 三件套之一恒 rc=0）→ 已由 `MIN-2257` 的护栏部分收敛（但注释仍自称透传）；MID-N22/N23/N24/N25/N26/N27/N18 → 本轮逐一复核**状态未变**，不重复计数 |

## 附录 B ｜ 审查限制与方法说明

1. **未执行真机录制验证**：本轮为纯静态 + 只读取证 + 本机离线命令实测。凡涉及「平台是否真的这样下发」「CDN 是否真的拒绝该 UA/该头」的结论（`SEV-2204`、`SEV-2205`、`MID-2208`、`MID-2211`、`MID-2212`、`MID-2222`、`MID-2226`、`MIN-2201`、`MIN-2202`、`MIN-2204`、`MIN-2208`～`MIN-2212`、`MIN-2230`）一律标注需真机核对并归入靠后批次。
2. **刻意未执行的一条用例**：`SEV-2208` 的判据来自静态核对（stub 目标与被调对象的模块归属不一致、该测试文件无 autouse fixture），**主会话没有实际运行它**——因为在网络可用的机器上它可能真删并替换工作树内的 `ffmpeg/` 目录。这是本报告的诚实边界：结论是代码事实，破坏后果是条件性推演，需用户在隔离副本里复现或由补锁后验证。
3. **未执行变异验证**：本轮为只读审查，未临时改坏生产实现来验红。6.3 那 21 条「待补锁」的判定以**结构论证 + grep 实测覆盖面**给出；落地补锁时须按 `AGENTS.md`「测试不得自实现被测逻辑」口径做归因用例。
4. **置信度含义**：高 = 静态可判定或已本机实测；中 = 结论依赖外部响应形态/时序窗口，代码侧已核对但需真机；低 = 仅结构可疑，**本章未收录低置信条目**（一律降级为「观察」或在 §5 合并登记）。
5. **凭据处置**：报告中出现的 URL / token / cookie 一律为**合成占位样例或脱敏后形态**（实测一律使用 `FAKESECRET`/`SECRETAAA` 之类合成值），未复制 `config/config.ini`、`config/URL_config.ini` 或 `logs/` 中的任何真实凭据；配置键审计只读取键名/节名。
6. **子代理结论的筛除与纠偏**：§1.4 所列「交叉印证 5 组」为多路同判后合并；另有约 25 条因与代码内既有编号注释重复、或与「末位放行 / 退避白名单 / standalone 刻意不等价 / 三类钉定」等定稿结论冲突而未计入统计。筛除中还纠正了两处子代理自身的取证瑕疵：一处把代码片段写成「排版占位」（已回源取真文本后纳入）、一处依据 `main.py` 的注释把 `SEV-N01` 判为已修（读回源码后推翻，即 `SEV-2208`）。
7. **工作树快照与 diff 可用性**：上一轮报告称「本目录非 git 仓库」，本轮实测**该陈述已失效**——存在单一提交 `51c2193 baseline: initial workspace snapshot`（2026-09-22 13:10:27）。因此本轮**首次可做基线 diff**（1.3 第 4 步），据此识别出约 1,739 行未被任何一轮审查覆盖的新增代码。建议后续每轮审查开始即记录基线号，并把「diff 增量审计」固化为并行分组之外的第 15 条取证线。
8. **取证期产生的临时物**：为实测 `SEV-2202` 在 `%TEMP%` 建有一次性产物目录（`dlr-segtest`，位于仓库外，不入库）；审查过程的发现清单草稿位于 `%TEMP%\dlr-review-0922-self.md`（仓库外）。本报告落地修复时应按 `AGENTS.md`「测试收尾清理临时脚本」核对仓库内无未跟踪的一次性脚本。

## 附录 C ｜ 需维护者 / 用户决策的事项（本报告不代为处置）

| # | 事项 | 可选处置 | 为什么不能由审查侧决定 |
| --- | --- | --- | --- |
| C-1 | Windows 运行期第二条 ffmpeg 源（`SEV-2218`）与 `AGENTS.md` 同日条款冲突 | (a) 改代码为显式开启；(b) 接回官方公布哈希判据；(c) 改条款并登记残余风险 | 属「可用性 vs 供应链强度」的产品取舍，且 `AGENTS.md` 明确「须由维护者决策而非代理放宽判定」 |
| C-2 | 个人镜像 fyhub 排在权威上游 GitHub 之前（`SEV-2218` 子项） | 至少调整为 GitHub 在前 | 若确有「GitHub 不可达而镜像可达」的真实用户场景，需维护者给出证据 |
| C-3 | `socksio` 入运行时清单 vs `_PROXY_SCHEMES` 收窄到 http/https（`SEV-2216`） | 二选一，两处口径同源 | 影响镜像体积与既有用户配置的兼容性 |
| C-4 | 四个未跟踪文件是否随下一次提交入库（`MIN-2268`） | `git add` 后提交；或回退 `src/ffmpeg_install.py` 的模块级硬 import | 涉及本次未提交工作的归属，须由作者确认 |
| C-5 | 本轮请用户补跑的动作 | ① 在有外网的隔离副本执行一次 `pytest tests/test_ffmpeg_install.py::TestWindowsInstallSingleSource -v` 以确认 `SEV-2208` 的破坏后果；② 在任一**开启分段录制**且主播名含 `%` 的房间跑 `tests/test_douyin_live_collector.py` 同形态的真实 URL 以复核 `SEV-2202`；③ 若现网确有 HEVC-only 快手房间，回填 `SEV-2204` 的判定 | 均需活房间或真机 ffmpeg 行为，本审查环境不具备 |
