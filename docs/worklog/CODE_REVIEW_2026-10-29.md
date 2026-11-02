# 全仓静态代码审查报告（2026-10-29）

> 审查执行时间：2026-10-29 20:40 ~ 21:40（本机时钟，Windows 10.0.26300 / x64）
> 审查对象工作区：`D:\DouyinLiveRecorder`，分支 `main`，HEAD = `6fb8918`
> **声明：本次审查全程只读，未修改、未创建、未删除任何源文件；本报告是本次审查新增的唯一文件。**

---

## 1. 审查概述与背景

### 1.1 触发背景

上一轮全仓审查为 [CODE_REVIEW_2026-10-27](docs/worklog/CODE_REVIEW_2026-10-27.md)（0 严重 / 1 中等 / 3 轻微）。本轮除按用户要求对全部源代码做一次系统性静态审查外，还承担两项核对任务：

1. 核对 2026-10-27 报告的两项遗留（`get_huajiao_sn` 死代码写回、`liveme.js` 调试打印）在当前工作区的真实状态；
2. 评估 2026-10-29 当天进入仓库的一次**大规模 stash 冲突提交**及其后续「冲突解决」对代码资产的影响。

### 1.2 本轮最重要的背景事实（决定了多数发现的成因）

审查开始时的实测结论，必须先于任何逐文件结论被理解：

- **HEAD 提交态是损坏的。** 提交 `34bd33e`（docs(ci,skills): CI 改为仅手动触发…）把一次未解决的 `git stash pop` 冲突整体提交，HEAD 内含 **899 个冲突块 / 102 个跟踪文件**（复跑判据：`git grep -c '^<<<<<<< ' HEAD`），其中 **94/262 个 `.py` 无法 AST 解析**（`src/`、根入口、`scripts/`、`tests/` 全覆盖），`pyproject.toml`、`web/index.html`、`AGENTS.md` 亦在其中。也就是说，任何人从 `main` 克隆或触发 CI，拿到的都是不可运行的代码。
- **工作区在审查窗口内被并发解决。** 审查开始后数分钟内，一个并发的解决工作包把冲突标记清零：`git grep -c '^<<<<<<< '` → 0，262/262 `.py` 可解析，`git diff --stat` = 102 files / +318 / −126480（**未提交**）。解决方式是折叠 HEAD 内重复副本、取单侧内容——因此本轮审查的实质风险面从「重复代码」转移到「**是否取对了单侧**」。
- **审查期间仓库仍在变动。** 本报告写作时工作区已变为 110 个未提交改动；审查期内至少有 4 项发现被并发工作包就地修复（见 §7）。**本报告所有结论均绑定其标注的实测时刻与复跑判据**，读者复核时应先跑 §8.3 的判据清单。

### 1.3 本轮结论摘要

| 严重程度 | 数量 | 其中由「冲突提交 + 解决」直接或间接导致 |
| --- | --- | --- |
| **严重** | **7** | 5 |
| **中等** | **35**（同族合并后） | 12 |
| **轻微** | **14**（同族合并后） | 6 |

其中 4 条中等项落在**测试与门禁自证面**（§4.5）：AGENTS.md 已用事故记录钉死过的三条测试纪律（平台分支不得靠 `skipif` 让 CI 跳过、禁改 stdlib 模块本体、`importorskip` 必须探测子模块并显式 `exc_type`）在当前仓库仍有违例点位，意味着部分防线在 Linux CI 上从不执行或可中断整轮收集。

总体判断：**当前工作区代码的静态健康度显著优于 HEAD 提交态**（语法、类型、格式、依赖元数据、钉定链、注入面均有机检证据），但存在 **1 组「事实源与代码互相说谎」的问题**（钉定哈希失配、文档承诺的降级防线不存在、注释宣称的回归锁指向已删文件），以及 **1 组真实功能缺陷**（Web 面板渲染降级、Windows 优雅退出链不可达、推送凭据明文落盘）。前者必须在下次提交前处置，后者应按优先级排期修复。

---

## 2. 审查范围与方法

### 2.1 范围（工作区快照，21:40 实测）

仓库跟踪文件 434 个 / 204,105 行。按代码口径拆分：

| 区域 | 文件数 | 行数 | 审查方式 |
| --- | --- | --- | --- |
| 根入口 `main.py` `gui.py` `build_exe.py` `web.py` `i18n.py` `msg_push.py` + 根 `index.html` | 8 | 15,317 | 逐行精读（2 个代理分文件通读） |
| `src/` 顶层 | 43 | 29,812 | 逐行精读（5 个代理按子系统分区） |
| `src/gui_qt/`（含 `pages/`） | 17 | 4,875 | 逐行精读 |
| `src/platforms/` + `src/proto/`（除生成物） | 11 | 2,243 | 逐行精读 |
| `src/javascript/`（除 `crypto-js.min.js`） | 4 | 1,930 | 精读签名/输出面 + 全文件判据扫描 |
| `web/`（`app.js` `index.html` `style.css` `motion.js`） | 4 | 3,246 | 逐行精读 |
| `scripts/` | 17 | 8,309 | 逐行精读（含 2 个 `.sh`） |
| `tests/` | 164 | 73,550 | 模式扫描全覆盖 + 22 个关键文件逐行精读 |
| `tests/frontend/` | 7 | 4,418 | 结构核对 + 用例存在性核对 |
| `typings/` 手写存根 | 12 | 256 | 逐文件核对 |
| CI/构建/配置（`.github/**` `pyproject.toml` `requirements.txt` `Dockerfile` `docker-compose.yaml` `.gitignore` `.dockerignore` `.gitattributes` `.pre-commit-config.yaml` `config/*.ini` `StopRecording.vbs`） | 约 25 | 约 3,300 | 逐行精读 + 一致性对账 |

**排除项**（与用户要求一致）：`node_modules`/`vendor` 不存在；`.venv`、`build`、`dist`、`coverage`、`.git`、`ffmpeg/`、`node/`、`downloads/`、`logs/`、`backup_config/`、`DouyinLiveRecorder.egg-info/`、`coverage.xml`/`coverage.json`/`uv.lock`、`.workbuddy/`（约 1,000+ 个基线快照副本文件，与主干内容重复）、`src/javascript/crypto-js.min.js`（第三方压缩库）、`src/proto/douyin_pb2.py`（protoc 生成物，仅核与其 `.pyi` 存根的同步性）、`i18n/*.po|mo|json|yaml` 正文（仅做键集合与抽样命中对账）、`docs/**` 与 `*.md`（仅做同源性核对，不做代码质量评审）。

### 2.2 方法

1. **语法/结构层**：venv Python 3.14.9 对 262 个 `.py` 全量 `ast.parse`；AST 判据扫描（模块级/类内同名重复定义、`except→pass`、`open()` 未入 `with`、危险调用、无超时子进程、生产 `assert`、未使用 import）。
2. **只读门禁实跑**（取真实退出码，不用管道后的 `$?`）：`black --check`、`isort --check-only`、`mypy` ×3 平台、`check_annotations.py`、`compile_po.py --check`、`check_version.py`、`check_runtime_pins.py`、`check_skill_agents_consistency.py`、`sync_metadata.py --check`；定点 pytest 子集（不产覆盖率文件、禁 cacheprovider）。
3. **高危模式横向扫描**：`eval/exec/pickle/yaml.load/shell=True/os.system/verify=False/innerHTML/localStorage/TODO-FIXME/console.log`；凭据形态扫描（`config/config.ini` 全敏感键值形态）。
4. **同源性对账**：`pyproject ↔ requirements ↔ uv.lock ↔ egg-info`、`.gitignore ↔ .dockerignore ↔ pyproject 排除清单 ↔ agent_hook_guard.PROTECTED_RUNTIME_DIRS`、代码注释里的回归锁路径与用例名逐一存在性校验、`.mjs ↔ ci.yml node-id 清单` 双向差集。
5. **按子系统分区逐行精读**：16 个只读审查代理并行分区（每区 2k~11k 行），统一作业简报固化「本项目刻意设计白名单」以避免把 AGENTS.md 已钉死的约定当缺陷。
6. **主控复核（关键纪律）**：所有进入本报告的高严重度断言，均由主控方独立复跑判据后定级。**3 条子代理断言被推翻并降级**（见 §7.2），另有 2 条因并发修复而失效。

### 2.3 工具版本口径

本机 black 26.10.1 / isort 9.0.2 / mypy 2.4.0 / pytest 9.1.1 / CPython 3.14.9。`ci.yml` 的 `black_version`/`isort_version`/`mypy_version`/`pytest_version` 常量由 CI 侧声明，本轮未联网核对，故本报告的门禁结论按 AGENTS.md 口径记为**「本地口径，未经 CI 同版本验证」**。

---

## 3. 严重问题（S 组）

### S-01 HEAD 提交态含 899 个未解决冲突块，仓库主干代码不可运行

- **位置**：102 个跟踪文件；块数前列 `build_exe.py`(65) · `main.py`(56) · `scripts/douyin_live_recorder_standalone.py`(54) · `gui.py`(49) · `src/config_io.py`/`src/collector.py`/`src/async_http.py`(各 31) · `pyproject.toml`(5) · `web/index.html`(4) · `AGENTS.md`(16)
- **类别**：缺陷 / 构建产物可用性 · **严重程度：严重** · **复核：主控已实证**
- **证据**：`git grep -c '^<<<<<<< ' HEAD` → blocks=899, files=102；AST 全量解析 HEAD 工作树快照时 `PY ok=168 broken=94`；`git log -S'<<<<<<< Updated upstream' -- main.py` → 引入点 `34bd33e`；`git status` 当时为空（即已提交）；`f93c504`（克隆基线）实测 0 块。
- **影响**：从 `main` 克隆/CI 取码即 `SyntaxError`；`pyproject.toml` 不可解析导致 `pip install`、`mypy`、`pytest`、`build_exe` 全线失效；发布链任何一次触发都会在 `static`/`test` job 之前断掉。这是本轮唯一的「产物级」故障。
- **修复建议**：把当前工作区的解决结果**尽快落为一个显式提交**，提交前逐条完成 §4 的 M-01/M-02/M-04 资产回收核对（解决已发生的语义损失不可自动恢复）；提交信息中写明「本提交修复 `34bd33e` 误提交的冲突块」。不得用 `git revert 34bd33e` 代替——那会连同该提交中有效的 CI/Skill 精简一并回退。

### S-02 `liveme.js` 内容与 `_JS_SHA256_EXPECTED` 钉定值失配，触发假「篡改」告警并在严格模式拒执行

- **位置**：`src/javascript/liveme.js:348,374,384,388,419,421`（6 处 `console.log`）；`src/utils.py:84`（钉定值）与 `src/utils.py:105-129`（`_check_js_hash`）
- **类别**：安全 / 缺陷（完整性校验面） · **严重程度：严重** · **复核：主控已实证**
- **证据**：实测盘上字节 SHA256 = `7fad3e96f646f118…`，钉定值 = `0ee11b8f775d519c…`，**match=False**（其余 4 个 `.js` 全部相等）；`utils.py:82-84` 注释明确该钉定值是「2026-10-28 按 CODE_REVIEW_2026-10-27 4.2 删除 liveme.js 内 6 处调试打印」后重算的；`git show f93c504:src/javascript/liveme.js` 内 `console.log` 计数 = 0，而 HEAD 与工作区 = 6 → **冲突提交把 `25d6f68` 的清理整体回退，解决时未复原**。
- **影响**：① 每个进程首次编译该脚本即打一条「SHA256 与钉定值不符…请核查文件是否被篡改」的 **假篡改告警**，把完整性防线变成噪声源；② 设 `DLR_JS_STRICT_HASH=1`（加固/CI 场景）时 `utils.py:121-125` 直接 `RuntimeError` → **LiveMe 平台整体不可用**；③ `sKey`、`signParams`、最终签名重新写入 node 子进程 stdout（2026-10-27 报告 4.2 的原始问题原样回归）。
- **修复建议**：从 `f93c504`（或 `25d6f68`）取回 `liveme.js` 工作副本，**不得反向改钉定值去迁就盘上内容**；同时落 S-02 的配套用例（即 M-10，已随本次修复闭合）。
- **修复成本**：极低（一次文件还原 + 一次哈希复跑）。
- **✅ 处置状态（2026-10-29 21:58 回写）**：已按上述建议执行 `git show f93c504:src/javascript/liveme.js` 的**字节级还原**（16,177 B、纯 CRLF 429 行、`console.log` 0 处），SHA256 现与钉定值逐字相等（`0ee11b8f775d519c…`）。接入链复跑实测：默认态返回完整 14 键 dict 且**不再打篡改告警**；`DLR_JS_STRICT_HASH=1` 态同样正常产出签名（原为 `RuntimeError` → 被兜成「未开播」）。还原前后 `black/isort/mypy ×3 平台/check_annotations` 全绿。真实 LiveMe 房间的联网验证**未执行**（本机无外网验证条件，且本次改动为「删调试打印」的纯日志面，签名算法逐字未动）。

### S-03 `web/index.html` 文件头残留孤立闭合标签，面板落入 quirks 模式

- **位置**：`web/index.html:1-3`
- **类别**：缺陷（合并解决残留） · **严重程度：严重** · **复核：主控已实证（字节级）**
- **证据**：首 60 字节实测 `b'</body>\n</body>\n'` 之后才是 `<!DOCTYPE html>`；全文件 `</body>`×2、`</html>`×2、`<!DOCTYPE`×1（`HEAD` 侧为 3 份重复副本折叠，正文本身与基线逐字节等价）。该文件经 `src/web_api.py` 的 `GET /` FileResponse 与 `/web` StaticFiles(html=True) 双路下发。
- **影响**：HTML5 初始插入模式的首个 token 非 DOCTYPE 即置 **force-quirks**，后续 `<!DOCTYPE html>` 被忽略 → 面板以非标准模式渲染（AGENTS.md 明令的 `table-layout: fixed` 定宽契约、盒模型、`dvh`/`env(safe-area-inset-*)` 等基础约束不再按标准模式保证），`<html lang>` 属性一并失效。`tests/frontend/*.mjs` 三个用例虽读取该文件，但**无任何用例断言文档头部结构**（实测 `git grep DOCTYPE -- tests/` 无相关命中），故该缺陷对全部门禁隐形。
- **修复建议**：删除 L1-L2 两行；并补一条结构锁（断言 `web/index.html` 首个非空 token 为 `<!DOCTYPE html>` 且 `</body>`/`</html>` 各恰一次）。
- **✅ 处置状态（22:15 复核回写）**：已由并发解决包在工作区修复（`web/index.html` 现首行即 `<!DOCTYPE html>`、`</body>` 恰 1 次，mtime 22:08:43），并新增 `tests/test_web_index_structure.py` 三条结构锁（`test_first_non_empty_token_is_doctype` / `test_document_has_single_closing_pair` / `test_html_element_declares_language`），实测 `3 passed`。该锁的判据是「首个非空 token 必须是 DOCTYPE」，而残片形态的首 token 是 `</body>` → 具备判红能力（按判据推导，未真跑残片形态，因本轮不得改动源文件）。

### S-04 `web_config.read_web_config` 用 strict 解析器且无守护：配置含重复键时面板对**每个请求**返回 500

- **位置**：`src/web_config.py:829-832`（另 `:672`、`:1122` 同形态）；消费点 `src/web_api.py:591`（`auth_middleware`）与 `src/web_api.py:1603`（`_read_web_config_cached`，其 `try` 只包住 `os.stat`）
- **类别**：缺陷 / 安全（可用性） · **严重程度：严重** · **复核：主控已实证（实测异常）**
- **证据**：对含重复键的临时 ini 实测 `read_web_config()` → `DuplicateOptionError: option 'web_port' in section 'Web' already exists`；AST 判据实测 `read_quality_options`/`read_config_safe` 函数体内**无任何 try**、`read_web_config` 的 `parser.read` 也不在任何 try 内；`config_read.tolerant_config_parser` 对同一文件可正常读出。
- **影响**：`config.ini` 任一节出现重复键（AGENTS.md 记录了 2026-10-17 实测发生过一次）即让**认证中间件在每一个请求上抛异常**——含 `/web` 静态页与 `/health`，面板整体打不开，用户无法经面板自救；更关键的是 AGENTS.md「配置键名、布尔口径与 SSL 验证」节明文写着这 3 处「重复键下它们**按各自 `except` 静默降级、不构成崩口**」，事实源给出了与代码相反的保证，会让后续复核直接跳过这里。
- **修复建议**：`read_web_config`/`read_quality_options`/`read_config_safe` 改用 `config_read.tolerant_config_parser`（或按同源口径补 `except (OSError, configparser.Error)` + `warn_duplicate_options`）；**同批改写 AGENTS.md 该句**为真实状态。
- **修复成本**：低（三处读取点 + 一句文档），风险低（容错层已是既有资产且有回归锁）。

### S-05 三处自建 `httpx.AsyncClient` 绕过 AGENTS 钉定的「两个合法接线点」，逐跳内网复检与响应体上限双双缺位

- **位置**：`src/room.py:150-151`、`src/room.py:256-262`、`src/spider.py:4026`
- **类别**：安全（SSRF + 无界读） · **严重程度：严重** · **复核：主控已实证**
- **证据**：`git grep -n 'httpx.AsyncClient(' -- src/ main.py` 实测 4 处，除 `src/async_http.py:76`（受管工厂）外全部为上述三处自建；`grep -c event_hooks src/room.py` = 0；`src/room.py:142/250` 的 `_outbound_target_reason` 只在**发第一个请求之前**判初始 URL，`follow_redirects=True` 之后的跳数不再复检；`client.get(...)` 无 `_bounded_response_read` 等价上限。`src/room.py:268` 还把落地 `redirect_url` 直接插进异常文本（未过 `mask_credentials`）。
- **影响**：AGENTS.md「重定向逐跳复检只有两个合法接线点，**新增第三处自建客户端即视为漏防**」在此成立：公网短链 302 → `http://127.0.0.1:6379` / `http://169.254.169.244/` 会被跟随并把响应体读回；超大/gzip 响应可放大内存。同时该形态绕开了 `tests/test_outbound_read_caps.py` 的读取点台账。
- **修复建议**：三支改走 `async_http._build_client`（或至少挂同一份 `response` 钩子 + `_bounded_response_read`），新读点登记进台账；`:268` 的 URL 过脱敏。
- **修复成本**：中（涉及 B 站/抖音两条链路的 UA/代理参数迁移），但属防线闭合，优先级应排前。

### S-06 Windows 录制进程的「优雅退出（写 `q`）」在生产形态下整条不可达

- **位置**：`src/ffmpeg_proc.py:106-119`（判据 `if proc.stdin:`）与 `:166-172`（末级关管道兜底）；接线点 `main.py:1123-1127`
- **类别**：缺陷 / 逻辑（可达性） · **严重程度：严重** · **复核：主控已实证（不可达性实测；产物后果为推定）**
- **证据**：`main.py:1125` 为 `stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL`；本机实测该形态下 `Popen.stdin/.stdout/.stderr` **三者均为 None**（`stdin= None stdout= None stderr= None`）→ `_QUIT_VIA_STDIN` 分支与末级 `for pipe in (...)` 均为空操作，停止流程直接落 `terminate()`（TerminateProcess）→ `kill()`。`ffmpeg_proc.py:105` 注释仍把「Windows 写 q 到 stdin」描述为现行两平台机制；`tests/test_ffmpeg_proc.py` 用**自带管道的假 Popen** 驱动这些分支，正是 AGENTS 点名的「只查定义与 connect 不作数」自我掩盖形态。
- **影响**：`record_save_type` 为 mp4/mkv/m4a 时，正在写的分段被硬杀 → 缺 moov/索引、产物不可播（默认 ts 不受影响）；`main.py:1121` 的注释给出的理由是「PIPE 从未写入也从未关闭，整个录制周期滞留句柄」——该理由与 `ffmpeg_proc` 的关闭段可以共存，说明是接线遗漏而非刻意设计。
- **修复建议**：录制 Popen 恢复 `stdin=subprocess.PIPE`，并在既有 unregister/收尾段显式 `close()`（`ffmpeg_proc.py:166-172` 已有该动作）；补一条**接线锁**断言「main.py 录制 Popen 的 stdin 非 DEVNULL」，同时改正 `:105`/`main.py:1121` 两处注释。
- **修复成本**：低-中；**必须先做一次真机验证**（mp4 档停止录制后产物是否可播），不得只凭单测判定完成。

### S-07 推送渠道凭据以明文进入轮转日志，且既有脱敏棘轮对该模块全盲

- **位置**：`msg_push.py:137-160`（`_mask_url`）；`:225,266,372,382,437,499,597,642`（8 处 `e=e` 未脱敏）
- **类别**：安全（凭据落盘） · **严重程度：严重** · **复核：主控已实证**
- **证据**：本机实测 `_mask_url('https://user:secretpw@hooks.example.com/services/foo/bar')` **逐字原样返回**，同入参 `utils.mask_credentials` 返回 `https://***@hooks.example.com/...`；`grep -n 'e=e,' msg_push.py` 实测 8 处；`tests/test_exception_log_masking.py` 的 `_OUTBOUND_MARK` 只认 `urlopen(`/`build_opener(` 等形态，按其自带判据实测 msg_push 命中站点 = 0（棘轮看不见该模块）。
- **影响**：自托管 ntfy/bark 反代常以 basic-auth URL 形态填写，失败分支把口令明文写进 `logs/streamget.log`，而 logs 按大小轮转 + `retention` 多份保留 = **凭据长期落盘**，直接触到 AGENTS.md「凭据与敏感配置红线」。Bark/Server酱/ntfy 的密钥还恒在 URL 末段，`mask_credentials` 对「路径即凭据」形态本就无效（实测原样返回）。
- **修复建议**：`_mask_url` 成功分支也过一次 `mask_credentials`（或先剥 netloc userinfo）；`_OUTBOUND_MARK` 增补 `opener.open(`，为 6 个渠道函数补登记并把异常文本改为「只留 `type_name` + 路径末段擦除」；`tests/TestMaskCredentialsCoverage` 需加「值确实消失」断言（AGENTS 关键约定 #11 口径）。

---

## 4. 中等问题（M 组，同族已合并）

> 表中「复核」列：`主`=主控独立实证；`区`=分区代理实证、主控抽样印证；`待`=待确认（缺一次取证）。

### 4.1 「冲突提交 + 解决」造成的资产损失族

| 编号 | 位置 | 问题 | 影响 | 建议 | 复核 |
| --- | --- | --- | --- | --- | --- |
| **M-01** | `AGENTS.md:90`、`pyproject.toml:54`、`main.py`（15 处：193/271/778/983/1097/1113/1225/2444/2558/3018/3270/3361/3567/3865/4174）、`src/utils.py:440,1034,1098`、`src/scheduler.py:528`、`src/spider.py:1411`、`src/web_config.py:805`、`msg_push.py:306,392`、`scripts/douyin_live_recorder_standalone.py:16,2043`、`tests/`（9 处）等 | **46 处指向 `6fb8918` 已删除的 `tests/test_regression_2026_09_22_*.py` 等 16 个文件的活引用**；实测 HEAD 侧 `main.py` 已是短名 15 处、工作区被**回退成旧名 15 处** | 违反 AGENTS 关键约定 #12「修复类注释必须附可复核判据」；按注释找不到锁 → 后人判定「该行为无回归保护」而误改 | 纯注释批量改回短名（被引**用例名实测全部存在**于新名文件，只换路径）；CODE_WIKI 双份的 4 处为历史记录、改名文件头 3 处为自述，不在本项范围 | 主 |
| **M-02** | `AGENTS.md`（工作区 197 行版） | **4 条「不得回退」硬约束既不在根文件、也不在任何 references**：GUI 过渡动效不得用 `place_forget` 收尾 / `StopRecording.vbs` 必须 UTF-16 LE / `build_exe.QT_BLOAT_FILES` 剪除清单 / `GET /favicon.ico` 回 404 而非空 200 + `no-cache`。实测 `HEAD:AGENTS.md` 各命中 1~2 次、工作区与 `.agents/skills/*/references/` 全为 0 | 唯一事实源失去约束本体（「双落空」）；叠加 M-04 后 `place_forget` 那条已是文本+测试双失 | 按瘦版口径把这 4 条补进 `known-pitfalls.md`/`build-details.md`，根文件加路由行 | 主 |
| **M-03** | `i18n.py:1-13`、`src/utils.py:1`、`src/platforms/douyu.py:1`、`src/ttwid.py:166`、`scripts/run_gates.py:527`、`src/web_api.py:332,346,1232,556-558`、`tests/test_regression_gui_output_chain.py:1`、`tests/test_decorator_contract.py:3` | **注释资产被解决侧裁掉或截断**：i18n 模块头 14 行总览丢失（`f93c504` 首行为 `# -*- coding: utf-8 -*-`，工作区首行已是 `import builtins`）；`utils.py` 丢 shebang/编码声明 2 行；`douyu.py` 把尾注抬成文件首行（同句在 `:189` 已有一份）；`ttwid.py:166` 残留「（ + ）」空引用括号；`web_api.py` 三处分节标题主语被裁 | 违反「修改注释只增不改」；模块契约（加载优先级、热切换口径）不再自述；按锚点检索落空 | 从 `f93c504`/`git show 6fb8918` 回植头部块，补齐 4 处断句 | 主 |
| **M-04** | `tests/test_gui_qt_units.py` | **2 条行为锁在解决中丢失**：`test_recorder_log_messages_route_through_tr`、`test_recorder_path_logging_masks_credentials`（全仓实测已无该函数名），而生产实现健在 | S-01 族中唯一「测试防线净丢失」项：录制输出线程的 i18n/脱敏两条锁归零 | 从 `f93c504` 回植这 2 条 | 主 |
| **M-05** | `.agents/skills/{ffmpeg-command-construction,platform-source-selection,runtime-pin-verification}/`、`scripts/check_skill_agents_consistency.py:232-247,258-260` | 三个已被 `29468b2` 合并进 `dlr-domain-constraints` 并删除的旧 Skill 目录**随坏提交回流**（旧 references 与新侧逐字节相同）；AGENTS 表只列 4 项、磁盘 7 项，而核对脚本对「目录→表」方向**只 WARN 且 rc=0** | 「第二套事实源」复活；同源锁在真实漂移面前不自证（违 AGENTS「告警即失败」同回路判定） | 删 3 个旧目录；把该项升为 error/rc≠0（或按 AGENTS 记「刻意保留 + 理由」） | 主 |
| **M-06** | `src/config_io.py:288-297`、`build_exe.py:382-419` | **缺键补写/脱敏模板均走 `parser.write()` 整文件序列化，销毁 `config.ini` 全部注释行**：实测输入 175 行 / 11 行注释 → 输出 165 行 / 0 行注释；`build_exe.py:383` 注释却写「保留注释与节结构」 | 用户手写的 `# xxx(是/否)` 说明随首次新增键补写被清空；分发给用户的脱敏模板失去全部选项文档 | 两条路径都改走行级插入（复用 `web_config.update_or_append_config_line` 形态），或如实改正注释 | 主 |
| **M-07** | `src/config_io.py:263-308` | 补写幂等锁只覆盖「同一 parser 两轮」：写侧持 `main.file_update_lock`（进程内 Lock），GUI 父进程/录制子进程/`web_config._config_write_lock` 是**不同进程的锁**，写前不重读、不比 mtime | 两个持不同快照的写者并发时后写者用旧快照整份覆盖，用户刚改的键被静默回退（重复键只是该形态被容错层接住的那一半） | 补写前比 `st_mtime`，不一致先重读；补「两个不同快照依次补写同一文件」用例 | 区 |

### 4.2 门禁自证与文档-代码矛盾族

| 编号 | 位置 | 问题 | 影响 | 建议 | 复核 |
| --- | --- | --- | --- | --- | --- |
| **M-08** | `.github/workflows/ci.yml:367` vs `requirements.txt` | deps-audit「下限条数」守卫 `assert len(out) >= 20`，用 ci.yml 自己的正则实测命中 **18** | 该 job 是 `ci-summary`（唯一 required check）的 `needs` 之一 → **一旦触发必红**，且红的是「守卫自己失效」，与真实漏洞不可区分 | 改为「条数 == `pyproject [project].dependencies` 条数」（取数即随增删同步），或降到 18 并写明口径来源 | 主 |
| **M-09** | `.github/workflows/ci.yml:82-89` vs `.agents/skills/dlr-dev-playbook/references/ci-workflow.md:11,21` | 文档称「[2026-10-24 修订] 恢复 `pull_request` 自动触发」且要求 ci-summary 的 required 勾选必须保持；workflow 实际 `on:` 只有 `workflow_dispatch` | PR 上不产生任何 CI 运行；两条同时成立时合并被 pending 卡死或被人工摘钩绕过——「门禁把关 PR」这一前提为假 | 二选一并同步另一侧（补 `pull_request: branches:[main]`，或改文档为「仅手动触发 + 分支保护不得勾 ci-summary」） | 主 |
| **M-10** | `src/utils.py:77-87` + `tests/test_utils.py::TestJsPinTable` | 第③类钉定面只锁「表键集合 == 目录 `.js` 集合」，**无任何用例比对盘上字节哈希**：S-02 失配状态下 `pytest tests/test_utils.py -k JsPinTable` 实测 5 passed | 内容漂移对 black/isort/mypy/pytest 四面全隐形——钉定自证只到「有没有登记」，不到「登记值对不对」 | 增一条「逐文件 `sha256(read_bytes())` 与表值相等」用例（即 S-02 的回归锁） | **✅ 已闭合（21:58）**：新增 `tests/test_utils.py::TestJsPinTable::test_pinned_bytes_match_the_table`；先对未修复态跑 → 精准判红并点名 `liveme.js`（变异验证实证），还原后 6 passed；`tests/test_utils.py` 全量 120 passed / 2 skipped |
| **M-11** | `scripts/sync_version.py:86` | 注释声称的回归锁 `tests/test_sync_version.py` **在全仓不存在**，且无任何测试引用 `sync_version`/`SYNC_TARGETS` | `--check`「判定面为空→rc=2」这一 M-92 定稿行为无任何用例锁定，注释给出虚假判据（违关键约定 #12） | 补离线用例，或如实改写为「待办 + 为何未做」 | 主 |
| **M-12** | `scripts/compile_po.py:135-136` | `reconfigure(encoding="utf-8")` 未显式给 `errors="replace"`；同仓 8 处同类站点均带（`main.py:50,66`、`gui.py:445,461`、`build_exe.py:2270`、`scripts/run_gates.py`、`agent_hook_guard.py:222`、`check_skill_agents_consistency.py:159`、`standalone:90`） | AGENTS「任何 `reconfigure` 显式给 `errors`」为硬约束；中文 Windows 下把错误处理器重置为 strict，i18n 三件套门禁可能因一条 emoji/中文行崩掉进程 | 两处补 `errors="replace"` | 主 |
| **M-13** | `scripts/agent_hook_guard.py:384`（`re.search(r"-\w*[dx]", statement)`）与 `:29-31,701-705,743-746` | ① R-WIPE-SCOPE 把只读预览 `--dry-run` 判成递归强删（实测正则对 `--dry-run` 命中），诱导使用者加 `\|\| true` 绕过守卫；② 模块头承诺「脚本自身异常一律放行」，但判定段只捕 `(OSError, ValueError)`，其余异常以 rc=1 结束——与「仅 `--self-test` 失败」的退出码语义撞车 | Hook 故障被伪装成代码不合格 / 误拦训练用户绕钩 | 判 d/x 前先排除 `-n/--dry-run`；判定段兜底 `except Exception` → 打 stderr 后 return 0 | 主（①正则实测；②静态核对，待一次真触发） |
| **M-14** | `scripts/run_gates.py:619-623` vs `:700-702`；`:34` vs `:541-560,707-709` | ① `--only black` 排障仍会无条件跑全量 `pytest -q` 兜底（无 `--only` 早退），与 help 的收窄语义不符；② 文件头承诺「门禁子进程超时无结论→rc=2 汇总」，pytest 兜底超时却走 rc=1（注释自认） | 排障等待翻倍；「门禁没跑成」两类出口分档不一致，指错方向 | `--only` 生效时跳过兜底并打印说明；兜底超时并入 stalled→2 | 区 |
| **M-15** | 门禁读数落后于事实源（6 处）：`ci.yml:554` 与 `.coveragerc-concurrency:5` 写 `fail_under = 50`（事实源 `pyproject.toml:336` = 60）、`trivy.yml:49` 写「pip 装 21 条依赖」（实测 18）、`ci.yml:868`/`build-release.yml:290` 仍称 GUI 为 `tkinter/pystray`（已迁 `src/gui_qt`）、`ci.yml:6-7,676` 仍称 FastAPI（阶段2 已移除） | 审查/排障时把「谁在把门」误导成另一套口径 | 一次纯注释波次改到当前取值，pystray/tkinter 两处留一行 `[历史注]` | 区 |
| **M-16** | `build_exe.py:2205-2206` + `:2130-2155`；`tests/` 对 `_loopback_web_host` 零覆盖 | Web 冒烟的「回环覆盖」`with` 体只有 `_launch(exe)` 一行，退出即按原字节还原 → 冻结 exe 真正读 `config.ini` 时覆盖早已失效；现网仅因基线模板 `web_host = 127.0.0.1` 侥幸不炸 | 该防线确定性空转；本机若按 README 把 `web_host` 设为 `0.0.0.0`，脱敏模板原样保留该值 → 冒烟以「拒绝启动」失败，而防线看起来仍在生效 | `with` 扩到包住整个探活循环与 `_finish`，并补「覆盖窗口内读到 127.0.0.1」行为锁 | 区 |

### 4.3 安全与凭据族（S 组之外的中危）

| 编号 | 位置 | 问题 | 影响 | 建议 | 复核 |
| --- | --- | --- | --- | --- | --- |
| **M-17** | `src/utils.py:1108`（`_SECRET_QUERY_RE`）及 `mask_credentials` 实现 | 只认字面 `=`，**百分号编码形态漏抹**：实测 `…%3Ftoken%3DSECRETVALUE…` 与 `t%3DSECRET3` 原样返回 | 平台回跳参数（`backurl`/`redirect_uri`）内嵌的 token/signature 明文进 `logs/`（轮转多份 = 长期落盘），「一律脱敏」防线在该形态可绕过 | 先 `unquote` 一轮再套五类正则（或补 `%3D\|%3d` 值段判据），`TestMaskCredentialsCoverage` 补「编码形态值确实消失」断言 | 主 |
| **M-18** | `src/sync_http.py:421-457`（对照 `:9-12` 与 `:88-94`） | 模块头声明闸门接了三处，但 requests（代理）分支由 urllib3 自行跟随重定向，`_HopGuardRedirectHandler` 只挂在 urllib 侧 opener；落地 `response.url` 从不过 `_redirect_hop_rejection_reason`。`tests/test_sync_http.py::TestSyncReqRedirectHopGate` 全部走直连路径 | 「同步通道与异步侧同等防护」的结论对代理分支不成立；接线者最易默认该前提（现无生产 importer，故暂不兑现现实暴露） | 代理分支按 `response.history + response.url` 逐跳复核，或在模块头显式登记缺口 + 补替身形态行为锁 | 区 |
| **M-19** | `src/spider.py:2594,2626-2648`（对照 Shopee `:6278`） | 注释与测试名均声称「落地页被拒即丢弃跳转并**剥离 Cookie / xy-common-params**」，但两条拒绝分支只 `logger.warning`，后续 `async_req(url, headers=headers)` 仍带注入的 Cookie 与 `sid`；姊妹实现 Shopee 有 `headers.pop("Cookie", None)` | AGENTS「响应决定 URL 的落地页一律双闸」只做了一半；`test_external_redirect_drops_cookie_and_common_params` 只断言「不对 evil host 发请求」，把「剥离」这一半掩盖成假绿 | 两个拒绝分支补 `headers.pop(...)`；用例补「第二次请求 headers 不含 Cookie」断言 | 区 |
| **M-20** | `src/node_install.py:219-224`、`:279,290-326`、`:48,344` | ① TOFU 基准文件**读不出来就 `warning + return True` 放行安装**，而 `ffmpeg_install.py:601-621` 的注释明确写着两侧已「统一收紧，不再有口径分叉」（该处 `return False`）；`read_text(encoding="ascii")` 只捕 `OSError`，`UnicodeDecodeError` 会穿出；② M-44 落盘纪律（唯一临时名 / 独占创建 / 目录锁）完全未接入 node 链，可预测文件名 + 裸 `open(...,"wb")` + 「已存在且是有效 zip 即复用」；③ M-47 已定性撤除的「导入期 PATH 快照 + 无去重前置」在 node 链原样保留 | 本地主体把基准文件改成不可读字节即可让唯一一道完整性检查静默失效；user-writable 目录里的符号链接劫持/互覆盖窗口比 ffmpeg 链宽 | node 侧对齐 ffmpeg 三链：并捕 `(OSError, UnicodeDecodeError)` → `return False` 并给「删除 `hash_file` 后重试」指引；复用同一内联 guard 块改造落盘段；PATH 前置改实时快照 | 主（①行与注释矛盾实测） |
| **M-21** | `src/ffmpeg_master_download.py:485`、`src/ffmpeg_install.py:695` | ① `total = int(response.headers.get("Content-Length", 0))` 抛的 `ValueError` 不被该函数三个 except 接（只接 HTTPError/IntegrityError/RequestException+ConnectionError+OSError），入口 `:766` 也只捕 `(FfmpegDownloadError, OSError)` → 穿出「失败一律返回 False 不抛」的契约；② 清理性 `zip_file_path.unlink()` 裸调，杀软瞬时占用会把**已成功的安装**改判为失败（同函数末尾本就有 `_discard_official_zip` 的宽容形态） | 劣化/被劫持 CDN 回一条非数字 Content-Length 即把「装不上 ffmpeg」升级成启动期崩溃 | ①两处 `int()` 前归零或并捕 `ValueError`；②改用 `_discard_official_zip` | 主（调用顺序静态闭合；未真机注入畸形头） |
| **M-22** | `src/ffmpeg_install.py:213-233`（同一内联块逐字复制三份：`ffmpeg_linux_download.py:175-195`、`ffmpeg_master_download.py:176-196`） | `install_lock` 的「同进程重入」守卫键是 `realpath`、**不含线程标识**，且 `yield True` 发生在 `with _HELD_LOCKS_GUARD:` 之内 | 第二个安装线程会命中「同进程重入」被无声放行，且 RLock 被跨挂起持有、阻塞同进程其它线程进任何 `install_lock`；当前接线为启动期顺序执行（注释自认），属未来改动的门没关严。三份逐字内联块本身也是 12 个 8 行等值块的跨文件重复（实测） | 守卫键改 `(thread_ident, realpath)`，或把 guard 的 `with` 收到判定之后；重复块抽为单点实现 | 区（结构推演） |
| **M-23** | `.dockerignore:85-93`、`.gitignore:61`；`git ls-files .zcode` / `config/URL_config.ini`；`Dockerfile:147` | ① `coverage.xml` 只在 `.gitignore`、不在 `.dockerignore`，而本地实存 645 KB、`COPY . ./` 会把它打进对外镜像（全仓文件路径清单外泄）；② `.zcode/config.json` **已被跟踪**且四处排除清单均未登记；③ `config/URL_config.ini` 处于跟踪态 → `.gitignore:217` 的忽略意图完全失效（`git check-ignore` 默认含 index 判定 rc=1） | 「漏一处即误入镜像 / 未跟踪目录 / 工具误扫描」的既有约定出现三个破口；③ 使「本地填入真实观看清单后一次顺手提交即进历史」成为可达路径，而 AGENTS 只给了 `config.ini` 一份「已跟踪脱敏基线」豁免 | ①补一行 `coverage.xml`；②`.zcode/` 同批登记五处并把已跟踪副本从索引摘掉（**该动作属 git 变更，交回用户执行**）；③`git rm --cached config/URL_config.ini` 或在 AGENTS 并列登记豁免并写明不得写真实值 | 主 |

### 4.4 功能正确性族（录制链 / Web / GUI）

| 编号 | 位置 | 问题 | 影响 | 建议 | 复核 |
| --- | --- | --- | --- | --- | --- |
| **M-24** | `src/stream.py:510-516,552-565`；`:865,919`；`:1085-1094` | ① 抖音「探针失败向相邻档回退」把 **FLV 侧已钳过的 `flv_idx`** 当作回退基准再钳给 HLS 侧（`:557→:561`），正是 AGENTS「选档一律保留原始请求索引 + 双列表各自钳制」明令禁止的形态（TikTok 分支 `:710` 已按 `fallback_base = quality_index` 修好，抖音漏改；`test_tiktok_hls_quality_index.py` 只钉主选档未钉回退段）；② 虎牙 `available_ratios` 推导字面量 `(30000,20000,8000,4000,2000,500)` 缺同文件正向表里的 `HD=1000`/`SD=800`；③ 斗鱼「全档失败」现返回 `is_live=False`，而 `known-pitfalls.md:60` 仍写「全部失败保持 `is_live=True`」 | ① FLV 档数少于请求档时 HLS 落回 OD（「选流畅实拉原画」），且 `actual_quality` 回采高档使降级告警永不触发；② 无 `exsphd` 而有 `bitRate` 的房间请求高清/标清恒被多降一级到流畅；③ 文档反向，下一轮按文档复核的人会把它改回去、重开「开播但无地址、每轮空跑一路 ffmpeg」的旧缺口 | ①回退基准改原始 `quality_index` + 补不等长列表回归锁；②推导集合改由 `HUYA_RATIO_BY_CODE.values()` 派生；③把该行文档改为与代码同事实（附用例名） | 主（①②行号实读；③两侧文本实测） |
| **M-25** | `main.py:1118,1123,1132-1134`、`:5436-5442 + 4877-4881 + 5501`、`:1620-1638`、`:4322-4332 + 760-847` | ① ffmpeg stderr 临时文件的父进程句柄只在 Popen **成功之后**关闭，`Popen` 抛 OSError 的路径永不关闭（全文再无第二次 close）；② `_room_seq_in_use` 登记的是 `threading.current_thread()`（即跑 `main()` 的引擎线程），`:5439` 的 `is_alive()` 判据恒真，注释描述的「收尾线程自行 pop」机制不存在，且 `except RuntimeError` 启动失败路径不 pop → 序号条目无界增长；③ 主播改名递归重命名不判目标存在（目录侧有 `_merge_anchor_directory` 守卫，文件侧无）；④ 强制直下分支只拼 `_00.flv`、不读 `split_video_by_time`、`direct_download_stream` 无时长/停摆守卫，而 `:4330` 注释称「与视频分支同构」 | ① 80+ 房间长跑每轮泄漏 1 个 fd + 1 个临时文件；② 序号语义退化 + dict 无界；③ POSIX 上 `os.rename` 原地替换 → **用户既有录制被静默销毁**（Windows 抛 FileExistsError 只告警，两端行为相反）；④ shopee/花椒在开启分段时不产生分段、单文件可无上限增长 | ①`finally` 统一 close + discard；②登记真实房间线程句柄、失败分支补 pop、注释锚点改正；③两个 rename 前判存在并告警（与目录侧同口径）；④直下分支至少打一条「不支持分段，已按单文件录制」告警并改正注释 | 主（①③④行号实读；②实读） |
| **M-26** | `src/web_api.py:1072-1077`；`src/web_config.py:1166-1180,1267-1271` | ① `PUT /api/rooms/quality` 无条件 `return {"ok": True, "changed": changed}`，而 `update_room_quality` 的 `False` 同时表示「已是目标画质」与「原子写失败」，前端 `web/app.js:1511` 完全忽略 `changed` 恒弹成功 toast；② `update_config_line` 新增的「重复键即拒绝」与「键不存在」「原子写失败」共用同一 `False` 出口，`update_or_append_config_line` 于是对**已含重复键的文件走追加**、再落第三条重复行并回报 True | ① 只读/占用/磁盘满时假成功（同函数族 `update_room`、`update_quality_options` 已按「写后重解析裁决」修好，唯独此处漏改）；② 损坏态被放大且调用方拿到假成功 | ①与 `update_room` 同口径：写后重解析确认已变，失败走 500 + 内部日志 code；②`update_config_line` 改三态信号（找到并写入 / 键确不存在 / 拒绝或失败），后两者不得走 append | 主 |
| **M-27** | `gui.py:2484-2487(+839-852)`、`:2135-2148(+1852-1870)`、`:3652-3654(+4840-4845)`、`:1982/2068/2422-2435` | ① 高级设置窗口未注册 `WM_DELETE_WINDOW`，用户点 X 关闭后 `_sync_theme_extras` 在死控件上 `restyle` 抛 TclError，令换主题/换缩放的后半段整体落空；② 选「系统默认」字体时不清 `_font_file_pref`，重启后导入的私有字体重新压过用户选择；③ POSIX 停止链 `proc.kill()` 之后才 `pkill -P <pid>`，父进程一死 ffmpeg 即被 init 收养，兜底清理结构性打空；④ `界面主题` 标签用裸 `tr()` 不经 `T()` 登记、主题/缩放/动效下拉 values 在 `set_language` 前定型且 `_on_language_change` 从不重建 | ①「切完主题一半没变」；②字体选择跨会话不可靠；③Linux/macOS 孤儿 ffmpeg 继续录制；④语言热切换后这三只下拉与标签停留旧语言且无法自愈 | ①判活或补 `WM_DELETE_WINDOW→_close`；②`family==""` 时同批写空 `gui_font_file`；③POSIX 改按进程组回收（`start_new_session`+`killpg`）或保存 ffmpeg PID 清单；④改 `T()` + 在重译段补一次设置菜单重建 | 主（①②④行号实读；③实测 kill 在 pkill 之前） |
| **M-28** | `src/ui_motion.py:87-94`；`src/gui_qt/{widgets.py:113-141,194-230}`,`main_window.py`；`src/ui_theme.py:220-222 + 10 处裸写`；`src/ui_fonts.py:49` | ① macOS `reduceMotion` 判定只看 `returncode`，用户显式「开启动画」（返回 0）被误判为「关闭动画」→ 动效被无条件压成 off 且只落一条日志；② 动效铁律①「系统关闭动画优先」与 `gui_motion` 偏好的全部生产引用都在**已退居遗留的 `gui.py`** 里，`gui.py:4995 main()` 已转发 `src.gui_qt.app.main()` → Qt 层完全未接线，`StatusDot`/`Toast` 无降级开关；③ `_HOVER_SHADE_RATIO` 提为常量后**未接线**（10 处仍裸写 0.18，注释自述「唯一取值点」）；④ `REJECTED_FONT_SUFFIXES` 定义后全仓零引用 | ①②合起来使「关闭系统动画的用户仍看到动效 / 开动画的用户动效被误关」两种方向都可能错，偏好项对实际窗口成孤儿；③④给出「已收敛」的假信号，改常量无效 | ①解析 stdout，仅 `1/true/YES` 判关闭；②Qt 侧读 `effective_motion`，off 档不排帧直接落终态，并把偏好项补进 Qt 窗口；③完成替换或删常量并改正注释；④在导入入口按该常量给专属文案或删除 | 主（③④实测引用计数） |
| **M-29** | `src/gui_qt/widgets.py:101-106,119,184,244,249,344`、`main_window.py:222,316`、`pages/{dashboard.py:55,danmaku.py:135,config.py:39,quality.py:165-166}`、`theme.py:51,213,372-381` | ① 8 处 `setPointSize` 不吃缩放档位（缩放只进 `Palette.px()` 的 QSS 通道，而控件级 `setFont` 优先于全局 QSS，代理用 offscreen 探针实测 sizeHint 14px→27px），85%/150% 档下视觉层次反转；② 6 处硬编码十六进制配色（`QColor("#c0392b")`、`_GIFT_COLOR="#d7757"`…）违反「设计令牌唯一事实源」，其中 `_GIFT_COLOR`/`_DIM_COLOR` 与主题 `_DARK["accent"]`/`_LIGHT["terminal_dim"]` 取同一字面量；③ `theme.py:213` 注释写「26 键」而事实源 `TOKEN_KEYS` 实测 25 键 | ①缩放档位落地不完整（AGENTS「缩放必须即时生效」的 Qt 半边失守）；②token 调整时不跟随，出现「同一状态两种色」；③读数误导 | ①字号统一经 Palette 派生；②兜底走 `theme.palette(...)` 现取，danmaku 三个色值增设语义键承载；③改正读数或改成「键集合见 `TOKEN_KEYS`」 | 区（①为代理 offscreen 实测） |
| **M-30** | `src/platforms/bilibili.py:310-314,228-233,308`；`src/platforms/douyin.py:100,106`；`douyu.py:53`；`huya.py:45`；`twitch.py:48,35,114-116`；`src/platforms/__init__.py:3-9`；`src/ui_i18n.py:93-121` | ① B站 AUTH 失败把服务端响应体整体写进一条日志、未截断（同文件 `:345` 对 item 已 `repr(item[:64])`，`ws_client.py:45` 单帧上限 8MB → 一条日志可 MB 级，把真实线索挤出轮转保留窗口）；② buvid 失效动作被 `except Exception: pass` 零线索吞掉，废 buvid 留进程缓存 → 永久 0 弹幕且无归因；③ 事件时文案未过 `tr()`：2 条 msgid **四目录已有真译文却恒不查表**（成死条目），5 处 `on_close` 原因串既未 tr 也未入目录（提取器看不见实参位 → 报「0 缺失」假绿）；④ `twitch._line_buf` 跨帧拼接无字节上限；⑤ 平台包 `__init__` 全量 eager re-export（实测 `from src.platforms import douyu` 拉起 24 个模块），抵消「按需导入避免循环」的既定意图；⑥ `retranslate_all` 收尾整体覆盖 `_ENTRIES`，回填窗口内新登记条目被丢弃 | 日志洪水 / 自愈链静默失效 / 非中文界面恒中文 / 内存单调增长 / import 期依赖缺失即全平台弹幕不可用 | ①`reply` 截断（复用 `msg_push._sanitize_resp_text` 思路）；②分两段 try + 落 debug；③2 处补 `tr()`（键已在，零目录改动）、5 处按「产生点包 tr」并五处同批登记；④加 `_LINE_BUF_LIMIT`；⑤改 PEP 562 惰性导出；⑥收尾改按 `(ref,mode)` 增删 | 区（③④⑤实测计数与行为） |
| **M-31** | `main.py:584,1458,1477,1795,2312,2374,2415,2462,2527,2674,2695,3148,4574,4850,5185`；`src/stream.py:1032`；`web.py:212,301-303`；`src/spider.py:4313` | ① 15 处用户可见文案绕过 `i18n.tr()`（AST 判据 + 目录命中双校验；`en_US.json` 实测已有真英文译文），本文件 `:4274-4278` 已自述「裸串必须包 tr()」；`stream.py:1032` 与 `web.py` 4 条同族；② PopkonTV `raise RuntimeError("…", status_msg)` 传两个位置实参 → `str(e)` 退化成元组字面量进日志（同函数 `:4289` 已修好，此处漏改） | 非简中界面恒中文；限流/未知 statusCd 时唯一可读线索不可解析 | ①统一改 `i18n.tr(常量模板, **kw)`；并给 `test_i18n_migration.py` 加一条「`logger.*`/`print_colored` 首参为 CJK 常量串即判红」棘轮（现四条不变量只抓带 FormattedValue 的 f-string）；②改单串模板形态 | 主（①实读 + 目录实测；②实测行） |

---

### 4.5 测试与门禁自证族

| 编号 | 位置 | 问题 | 影响 | 建议 | 复核 |
| --- | --- | --- | --- | --- | --- |
| **M-32** | `tests/test_video_postprocess_paths.py:142`、`tests/test_web_tray.py:312` 与 `:333-334`、`tests/test_frontend_quality_ui.py:249,258` | **Windows 专属分支的用例用 `skipif(sys.platform != "win32")` / 函数内 `pytest.skip()` 让 CI 静默跳过**（CI 全部 job 跑 ubuntu）。这正是 AGENTS.md「平台专属分支的测试不得靠 `skipif` 让 CI 跳过」点名的失效形态；`test_video_postprocess_paths.py:149` 的注释还把「用例本身已由 skipif 保证只在 win32 运行」当作正确做法 | 三条防线在合并边界从不被执行：①「隐藏控制台的 `STARTUPINFO` 确实被构造」；② `GetConsoleWindow/GetSystemMenu` 的 `restype` 必须是 `c_void_p`（错则 64 位句柄被截成 32 位，窗口操作改写到错误地址）；③「GBK 本地化 `tasklist` 输出不得让存活探针抛 `TypeError`」（MID-64 记过的崩形态） | 按本仓既有范式把平台判定抽成模块级常量（如 `_QUIT_VIA_STDIN = os.name == "nt"`）或 `types.SimpleNamespace(**vars(sys))` 的 sys shim，用 `monkeypatch` 强制走进 win32 分支，使 Windows 路径在 Linux CI 上真跑（参照 `tests/test_gui_stop_exit_singleflight.py`） | 主 |
| **M-33** | `tests/test_gui_legacy_guards.py:97,114,130,155`、`tests/test_i18n.py:364,370`、`tests/test_regression_root_entries.py:218`、`tests/test_web_tray.py:328` | **8 处 `monkeypatch.setattr(sys, "platform", …)` 裸改全进程唯一的 `sys` 本体**（`web_tray.sys` 亦是同一对象）；而 `tests/test_regression_gui.py:38-39` 自己写明「直接改 `gui.sys` 的属性会波及全进程（AGENTS「patch stdlib 模块本体」条）」，`tests/test_gui_legacy_guards.py:17` 却又把这写法规定为本文件推荐手法 | patch 窗口内其它在途线程与库（loguru、弹幕边车、Qt、harness）读到的 `sys.platform` 被整体翻转——AGENTS M-27/L-18 记录的正是「单文件恒绿、整包跑红」这一形态；两份测试文件对同一纪律口径相反，后续改动无所适从 | 一律改 `shim = types.SimpleNamespace(**vars(sys))` + `monkeypatch.setattr(<被测模块>, "sys", shim)`；并把该口径与 `test_test_hygiene.py` 的 R1 豁免说明同批对齐（当前 8 处与文档互相矛盾） | 主 |
| **M-34** | `tests/test_regression_gui.py:33-35`、`tests/test_danmaku_monitor.py:425` | `pytest.importorskip("gui", reason=…)` **既只探测顶层包名、又未显式 `exc_type=ImportError`**（同仓 5 个 Qt 用例已按 2026-10-18 定稿形态写「探测 `PySide6.QtWidgets` + `exc_type=ImportError`」，`test_gui_qt_units.py:28` 注释即为此据） | `gui` 导入链经 `src.gui_qt.app` → `PySide6.QtWidgets`，缺系统库时抛的是原生 `ImportError`，而 pytest ≥ 9.1 的 `exc_type` 缺省已改成 `ModuleNotFoundError` → 该行拦不住，**模块级那处以 collection error 中断整轮 pytest**（AGENTS 记录的实测形态：4337 collected / 2 errors → rc=2，其余用例一条没跑、覆盖率 xml 与逐模块门禁全部拿不到数据） | 改为先 `pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError, reason=…)` 再取 `gui`；两处同批 | 主 |
| **M-35** | `tests/test_ffmpeg_install.py:1924`；`tests/` 24 处「`：` 前空槽」的掏空节标题 + `test_regression_gates.py:18,190,277,425` 双段空分隔 + `test_regression_gates.py:1`/`test_proto_runtime_compat.py:1` 首行退化为裸 `#`；`tests/conftest.py:129-131` vs `:19`；`tests/test_i18n_catalog_coverage.py:33` | ① 注释引用的类 `tests/test_ffmpeg_path_preference.py::TestTwinEquivalence` **不存在**（实测 0 命中；AGENTS 正文点名的真实锚点是同文件模块级 `test_twin_agrees_on_every_criterion_combination`）；② 一批分节标题主语被冲突解决掏空，审查编号 ↔ 锁的对应关系断链；③ `conftest.py` 声称「`tests/_out_e2e/` 条目**有意保留**」，而 `_TEST_OUT_DIRS` 实为 `("_out_live",)`；④ 白名单以 `file:line`（`src/ui_i18n.py:34`）作键，与 AGENTS「锚点不写行号」冲突，上方增删一行即造出假红 | ①「孪生判据两处同改」的唯一人读入口指向不存在的类，按名核对会误判「锁缺失」；②③④ 均属误导后人的事实性陈述或脆弱键 | ①改指真实函数名；②补回段落名（无编号时写行为不变量短语），给两个裸 `#` 首行补模块标题；③改正为「已不再清理 `_out_e2e`（写入方已迁 `tmp_path`）」；④白名单改按 `(文件, 函数/语句锚点)` | 主（①③④实测；②计数实测 24 处） |

---

## 5. 轻微问题（L 组，同族已合并）

| 编号 | 位置 | 问题 | 建议 | 复核 |
| --- | --- | --- | --- | --- |
| **L-01** | `src/gui_qt/recorder.py:373-393` + `shared.py:432-441` | 退出收尾对「已确认终止」的 PID 再发一发 `taskkill /F /T`，恒返回 128 → 每次正常退出留一条「清理失败」伪告警；父亡后 `/T` 亦无法触达孙进程（与 `:353-357` 自己置 `_cleanup_target_pid=None` 的判据相反） | 按 `proc.poll() is not None` 决定是否调 `cleanup_process_tree` | 区 |
| **L-02** | `src/gui_qt/main_window.py:945-946,998-1004` | 「取列表引用→重绑空表」与跨线程 `append` 之间有丢单窗口；`_pending_log_lines` 无上限 | 同锁内交换或改 `queue.Queue`，并设缓冲上限 | 区 |
| **L-03** | `src/gui_qt/pages/danmaku.py:158-167,255-302` + `main_window.py:971-977` | 弹幕页每秒 `clear()` + 最多 300 次 `insertHtml` 全量重绘，不判当前页可见；`apply_palette` 因三个色值恒定（`:37-39`）再重绘一次纯属浪费并清空用户选区 | 仅在当前页可见时 refresh；`apply_palette` 空实现该页 | 区 |
| **L-04** | `src/gui_qt/main_window.py:1100-1118,1140-1162` | 保存路径的模态框无重入守卫，可能与状态链的冲突框叠两层（同文案、语义不同） | `_url_conflict_asked` 提升为「任一模态裁决进行中」统一守卫 | 区 |
| **L-05** | `src/gui_qt/main_window.py:1235-1242` | POSIX 分支 `Popen(["open"/"xdg-open", path])` 不回收，每次点击留一个僵尸 | 改 `subprocess.run(..., timeout=)` 或 daemon 线程收割 | 区 |
| **L-06** | `src/gui_qt/main_window.py:749-762` + `src/ui_icons.py:125-131,175-193` | 图标导入把整份文件读进内存后才查体积（注释承诺「先挡体积才不会把 100MB 读进来」在 GUI 侧不成立），且随后二次读盘、二次校验，存在 TOCTOU | 入口先 `os.path.getsize` 早退，复用同一份字节走 `install_icon_bytes` | 区 |
| **L-07** | `src/web_api.py:1459-1463` | `upload_icon` 成功响应把 `config/icons/` 落盘**绝对路径**回给客户端，与本文件自立不变量「绝对路径只进内部日志、不进对外 detail」（`:332-335`）冲突；前端只消费 `code` | `path` 改相对形态或删键 | 区 |
| **L-08** | `src/web_api.py:1064-1067`；`web/app.js:2205-2216,304-309,373/379,2131-2153,1617` | ① 画质 422 死分支（前面 `validate_room_target` 已含逐字同判据并先抛，注释却称「保留以给本端点文案」）；② `showAuthWarning` 注释称横幅随登录页隐去但代码无摘除路径；③ `fmtTime` 固定 `toLocaleString('zh-CN')` 不随语言；④ `var t = e.target` 遮蔽 I18N 取值函数 `t()`；⑤ 内嵌字典 `rooms.qualityAddBtn`/`config.loadFailed` 无任何取键路径（死键，五处同步维护面）；⑥ `container.innerHTML = html \|\| t('config.none')` 是本文件「动态字段一律 esc」不变量的唯一例外（现值静态、不可利用） | ①删死分支或把文案接进 validate 抛点；②改正注释或补摘除；③按当前语言取 locale；④改名 `el`；⑤删键（四套同批）或接上；⑥补 `esc()` | 区 |
| **L-09** | `src/sync_http.py:259-264`；`src/cookie_cache.py:171,222-223,390`；`src/ttwid.py:59,185,197-212` | 备案性「引用别名/只增不减」：公开 `session()` 出口绕过本模块闸门与上限体系（现无 importer）；`get_cached/fetch_cookies/singleflight` 返回缓存内部可变对象（现消费点只读）；`_ttwid_scopes` 只增不减 | 在模块头写明「返回值只读」契约或命中路径返回浅拷贝；`session()` 接线时登记进读取点台账 | 区 |
| **L-10** | `main.py:3289`；`:352 vs 5130-5134`；`:459,467,603,604,609`；`:4620`；`:4819,4821`；`:4923-4925`；`:1115-1116` | ① `www.plive.kr` 只登记在分派侧片段、不在 `PLATFORM_HOST`（77 项）→ 该形态被判「未知链接」注释掉，表项给人已支持错觉；`test_platform_dispatch.py` 只锁单向不变式；② `video_save_type_list` 同字面量两份、模块级那份永不生效；③ `host_id`/`new_url`/`_atexit_result_*` 声明后全仓零读取；④ `check_ffmpeg_existence` 的 `subprocess.run(["ffmpeg","-version"])` 无 timeout（位于入口 FFmpeg 网关）；⑤ 系统代理打印未过 `mask_credentials`（违「一律」口径，现值不含凭据）、异常文本未包 tr；⑥ 读 URL 配置失败的 except 分支不 `continue`，同一轮连撞两次；⑦ stderr 回退分支注释称「继承父 stdout」，实际 stdout 亦为 DEVNULL（比注释描述差一档） | ①补进 `PLATFORM_HOST` 或摘片段，并给反向不变式加锁；②删重赋值；③摘死声明；④补 `timeout=30` + 走既有降级；⑤套 `mask_credentials`；⑥补 continue；⑦改正注释 | 主（①②③④⑥行号实读） |
| **L-11** | `build_exe.py:485`；`msg_push.py:358` | 生产代码 `assert`（`-O` 下消失）：①「无从校验」的前置判据变 no-op；②`assert smtp_obj is not None` 后紧接 `smtp_obj.login(...)`，被优化掉时退化为 AttributeError | 改显式判断 + 可读错误出口 | 主 |
| **L-12** | `src/proto/douyin_pb2.pyi:18`；`src/platforms/huya.py:168`；`src/room.py:177,194-195,284,316`；`src/room.py:120-130,45,113-115` | ① 存根 `messagesList: list` 无元素类型，`msg.method`/`msg.payload` 走 Any（AGENTS 要求新增字段引用同步补存根）；② 虎牙 `iFontColor` 由外部帧取，可产出超 6 位十六进制色串（现无消费点）；③ 抖音主页判定用子串正则（`evil-douyin.com/user/x` 亦命中）、`sec_uid` 兜底段未收窄字符即直插 query/path；④ `get_xbogus` 零生产调用且其头合并口径是 M-43 已否掉的「整组替换」形态，`_cached_ttwid` 只写不读 | ①补第 4 个消息类或参数化 `list[PushMessage]`；②`& 0xFFFFFF` 收窄；③改 hostname 精确/`.` 后缀 + 统一 `[\w\-]+`；④按「删符号前先 grep 调用点」处置或改走 `_merge_default_headers` | 区 |
| **L-13** | `README.md`/`README_EN.md`（无 v4.6.0 段）、`docs/agent-reference/project-structure.md`（仍在 102 个改动文件内） | 文档更新日志最新段停在 v4.5.0，而 `pyproject=4.6.0`、CODE_WIKI 已有 5 条 v4.6.0-dev 段；`check_version.py` 不覆盖 README，故不构成机检红 | 4.6.0 正式发布时补段，或在收尾明确豁免 | 主 |
| **L-14** | `DouyinLiveRecorder.spec:50-57`；`src/spider.py:2798-2801` | ① 本地生成物 spec 内含本机绝对路径（`*.spec` 已被 gitignore 兜住，未跟踪）；② Bigo 开播分支同一对键赋值两次（`result["m3u8_url"]=…` 紧跟 `result |= {...}`）——值相同故行为不变，形态是「两侧都留」的产物 | ①收尾清理即可；②删重复两行 | 区 |

---

## 6. 逐文件问题索引（满足「逐文件记录」要求）

> 只列有发现的文件；同族合并项以编号回指。

| 文件 | 发现编号 |
| --- | --- |
| `main.py` | S-01, S-06, M-01, M-25, M-31, L-10 |
| `gui.py` | S-01, M-27, M-28（铁律引用位）, L-… |
| `web.py` | S-01, M-31 |
| `build_exe.py` | S-01, M-06, M-16, L-11, L-14 |
| `i18n.py` | S-01, M-03 |
| `msg_push.py` | S-01, S-07, M-01, L-11 |
| `src/utils.py` | S-01, S-02（钉定表）, M-01, M-03, M-10, M-17 |
| `src/spider.py` | S-01, S-05, M-01, M-19, M-31, L-…（含 6 处轻微：`4313` 双实参、`:4993-5084` 死代码备案、`4718-4735` 酷狗出口调反、`5979-6011` vvxqiu 判空滞后、`:6246-6273` 双闸三份实现、`341-345` Twitch 缓存清理两支） |
| `src/room.py` | S-05, L-12 |
| `src/stream.py` | M-24, M-31 |
| `src/stream_select.py` | L-…（探针客户端构造降级捕获面窄于注释，`1300-1317`）, 另 `collector.py:250-255 vs 611-619` 的 `room_closed` 双投（待确认） |
| `src/web_api.py` | S-04（消费点）, M-26, M-03, L-07, L-08 |
| `src/web_config.py` | S-04, M-01, M-26 |
| `src/web_tray.py` | S-01, 中危一项待确认：`start()` 仅包护 import 段，图标/菜单构造异常会穿透崩掉面板启动（`216-274` + `web.py:390`） |
| `src/config_io.py` | S-01, M-01, M-06, M-07, 及注释锚点降级族（`MIN/SEV/MID…` 工单号 16→1） |
| `src/config_read.py` / `src/config_bool.py` | M-07（口径核对通过）、`config_bool.py:1-12` 自述与 `config.ini` 实态（`true/false` 30 条、`是/否` 0 条）不符 |
| `src/ffmpeg_proc.py` | S-06, M-…（`:176,207` 异常日志缺 type_name） |
| `src/node_install.py` | M-20 |
| `src/ffmpeg_install.py` / `src/ffmpeg_master_download.py` / `src/ffmpeg_linux_download.py` | M-21, M-22（含 12 个 8 行等值块的跨文件重复） |
| `src/scheduler.py` | S-01, M-01 |
| `src/async_http.py` / `src/sync_http.py` | S-01, M-18（另 `async_http.py:698-710` 瞬时 DNS 失败被归因成「疑似被篡改」告警） |
| `src/ttwid.py` / `src/cookie_cache.py` / `src/proxy.py` / `src/http_config.py` | M-03（断裂注释）, L-09 |
| `src/log_archive.py` / `src/logger.py` | 仅绑定流不对称一项：`log_archive.py:153-158,205-206`（只有一条标准流绑定 web_console.log 时被无条件改道且不恢复） |
| `src/collector.py` / `src/danmaku_monitor.py` / `src/srt_writer.py` / `src/ws_client.py` / `src/base.py` / `src/__init__.py` | 冲突解决质量核实通过（顶层定义零缺失、引用零悬空）；仅 `collector.py` 双投待确认 |
| `src/platforms/*` | M-30, L-12 |
| `src/gui_qt/*` | M-29, L-01, L-02, L-03, L-04, L-05, L-06 |
| `src/ui_kit.py` / `ui_theme.py` / `ui_scale.py` / `ui_motion.py` / `ui_fonts.py` / `ui_icons.py` | M-28, M-29, L-06 |
| `src/javascript/liveme.js` | S-02 |
| `src/javascript/{migu,x-bogus,haixiu}.js` | 钉定值与字节哈希逐字相符；`x-bogus.js:375` 的 `eval("require('crypto')")` 属混淆固有形态，仅备案 |
| `src/proto/douyin_pb2.pyi` | L-12 |
| `web/app.js` | L-08, M-26（消费 `changed` 恒弹成功）；敏感判定与后端两处口径漂移（`URL_VALUE_RE` 仍留 scheme 门、节名比对未 casefold） |
| `web/index.html` | S-03（正文与基线逐字节等价，无结构/脚本误删） |
| `web/style.css` / `web/motion.js` | 未发现缺陷（reduced-motion 双闸门、粒子/DPR 封顶、拆链完整） |
| `scripts/douyin_live_recorder_standalone.py` | S-01, M-01, M-24（孪生漂移：斗鱼房号 `re.search(r"rid=(\d+)")` 未回灌主线 `[?&]rid=` 锚定与「首个非空路径段」口径；h265 解析期按键名剔除与主线「只认 URL `codec` 参数」不一致且未登记「刻意差异」） |
| `scripts/check_skill_agents_consistency.py` | M-05 |
| `scripts/compile_po.py` | M-12 |
| `scripts/run_gates.py` | S-01, M-03, M-14 |
| `scripts/agent_hook_guard.py` | M-13 |
| `scripts/smoke_test.py` | 标量畸形（`expected_status` 为字符串）在 `:231-235` 抛 TypeError → rc=1（应 rc=2）；`:207` 用默认 handler 集 `build_opener`；`:260,278` `resp.read()` 无上限 |
| `scripts/sync_version.py` | M-11 |
| `scripts/{check_annotations,check_coverage,check_runtime_pins,check_version,report_bundle_size,sync_metadata,extract_i18n_strings}.py` | 除 `sync_metadata.py:68,90`、`check_workflow_constants.py:35`、`check_annotations.py:526-527` 的「纯读路径 `read_text` 无兜底、不可读时以 rc=1+栈冒充代码不合格」这一同族分级破口外未发现缺陷 |
| `tests/`（164 个 `.py`） | M-04（2 条锁丢失）, M-01（9 处交叉引用）, **M-32**（`test_video_postprocess_paths.py`、`test_web_tray.py`、`test_frontend_quality_ui.py`）, **M-33**（`test_gui_legacy_guards.py`、`test_i18n.py`、`test_regression_root_entries.py`、`test_web_tray.py`）, **M-34**（`test_regression_gui.py`、`test_danmaku_monitor.py`）, **M-35**（`test_ffmpeg_install.py`、`conftest.py`、`test_i18n_catalog_coverage.py`、24 处节标题）, `test_regression_gui.py:31` 死常量 `PENDING_GUI_JSON`、`test_run_gates.py:100-111` 读子进程输出用 `text=True` 无显式 encoding（与同仓 3 处的 `encoding="utf-8"` 口径不一）、`test_danmaku_platform_strip.py:99-109` 把行为锁的基准挂在 `config.ini` 模板条目数上。正向确认：R1/R2/R3/R6/R8/R9/R10/R11 八条卫生判据全部与例外表**双向相等**、变异标记残留 0、空 `parametrize`/无条件 skip/`assert True` 均 0、`doesNotMatch` 式源码文本锁 0、10 个同源门禁判据复用本仓自有函数实测全部判绿 |
| `tests/frontend/` | 旧名 `test_regression_2026_09_22_gates.mjs` 残留一度使 `test_ci_frontend_registration` 判红（审查期内已被并发包删除，复跑 5 passed） |
| `pyproject.toml` / `requirements.txt` / `config/config.ini` / `config/URL_config.ini` | S-01, M-01, M-23, L-10 相关；`[project].dependencies` 与 `requirements.txt` 包名集合 18==18 双向差集为空；基线模板凭据键全为空值、`web_host = 127.0.0.1` |
| `.github/workflows/*` + `.github/actions/retry` | M-08, M-09, M-15；正向确认：`if: "!startsWith(...)"` 引号写法正确、内联重试 0 处、`retry` 复合动作 17 处、actions v7 一致、`trivy-action` 40 位 SHA 钉定、`docker-publish.yml` 的 `secrets.*` 恰为 `{GITHUB_TOKEN}` |
| `.dockerignore` / `.gitignore` / `.gitattributes` / `.pre-commit-config.yaml` | M-23, M-15；`.pre-commit` 只跑裸 mypy、缺 AGENTS 基准的平台双跑（应补两个 `language: system` 入口，或在文件头写明双跑由 `run_gates`/CI 承担） |
| `Dockerfile` / `docker-compose.yaml` | M-16（`TZ` 经 `.env` 覆盖的承诺在整条链上无接线，`environment` 硬编 `TZ=Asia/Shanghai`）；正向：`ARG` 早于 `LABEL`、`INSTALL_GUI` 两阶段同改、`security_opt: no-new-privileges`、NodeSource 脚本先落盘校验 sha256 再执行 |
| `StopRecording.vbs` | 未发现缺陷（实测 UTF-16 LE BOM `fffe`、全 CRLF、无裸 `Exec(`、三层匹配与终止顺序在位） |
| `AGENTS.md` / `.agents/skills/**` | M-01, M-02, M-05；`ci-workflow.md:11,21` 与 `ci.yml` 矛盾（M-09）；`static-check-adjudication.md` 被 AGENTS 路由指向却不含 typings 存根处置正文（瘦版压缩时把约束本体丢掉） |

---

## 7. 结论性核对

### 7.1 上一轮（2026-10-27）遗留项核对

| 上轮项 | 当前真实状态 | 依据 |
| --- | --- | --- |
| 4.1 `get_huajiao_sn` 死代码携带写回 | **已按「方案 2」处置**：写回判据收紧为「空响应不写回、`ValueError` 移出该分支由 `except Exception` 承接」，且函数仍是零生产调用（活链路为 `main.get_huajiao_stream_url`，`tests/test_spider_hardening.py:1706` 明确登记其为死代码） | `src/spider.py:5005-5066` 实读 |
| 4.2 `liveme.js` 6 处调试打印 | **回归 → 本轮已再次修复**：清理提交 `25d6f68` 被 `34bd33e` 的冲突提交整体回退（即 S-02），本次审查已于 21:58 从 `f93c504` 字节级还原并复跑验证（`console.log` 0、钉定值匹配、默认/严格两态签名均正常） | blob/sha256/祖先关系实测 + 还原后复跑 |
| 4.3 `web_tray.py` `os._exit(0)` | 维持有意设计（仅「无 server」分支）；本轮新增一条相邻防线缺口（见 §6 `src/web_tray.py` 行） | 分区精读 |
| 4.4 宽 `except Exception` 观察 | 维持观察；本轮实测生产代码「`except X:` 体仅为 `pass` 且 ±4 行无注释」59 处，其中 `gui.py` 17、`main.py` 7 —— 建议后续重构触及对应函数时补一句归因，不单独排期 | AST 判据实测 |

### 7.2 子代理断言被主控推翻（方法学透明）

| 子代理断言 | 主控复核实测 | 处理 |
| --- | --- | --- |
| 「`tests/test_ui_kit.py` 丢失 18 条用例」 | 以 `f93c504`（干净基线）为参照做 AST 用例名集合差：**0 丢失**（`test_slide_in_offsets_then_restores_grid_manager` 等 3 条均在原位；`grep -c 'def test_'` 基线 32 = 工作区 32） | 未采纳；丢失项修正为 `test_gui_qt_units.py` 的 2 条（M-04） |
| 「`tests/test_web_tray.py` 35 行模块头注释被整段删除」 | 头部注释实际在位（工作区首 12 行与基线一致）；当时 `check_annotations` rc=1 报的密度违规，在同一并发包后续改动中消失（复跑 rc=0，实测 `comment_density` 15.84% > 13.0%） | 不作为发现；仅保留 §7.3 的「审查期内变化」记录 |
| 「AGENTS『三处同改』第 ③ 项指向的 `_ALLOWED_HOSTS` 在 `build_exe.py` 中不存在 → 引用错误」 | 当前 Skill 文本已写作 `tests/test_build_exe.py::_ALLOWED_HOSTS`（限定正确）；工作区 AGENTS.md 未出现该符号 | 不采纳 |
| 「`main.py` 模块级重复定义 3 项（含 `enable_https_recording`）」 | 声明与初始化分离 + 热更新重赋值的既有形态（`:327` 注解声明、`:4738` 模块级读取、`:4979` 函数内热更新），非缺陷 | 不采纳 |

### 7.3 审查期内被并发工作包修复的项（不再计入本轮清单）

| 项 | 修复时刻（实测） | 复跑判据 |
| --- | --- | --- |
| 三条带占位符的 `tr()` 模板未登记四目录（曾使 `test_i18n_migration.py::test_runtime_templates_covered_by_catalog` 当场红，21:02 实测 FAIL） | 21:03 起补齐 | 21:3x 复跑 `tests/test_i18n_migration.py tests/test_i18n_catalog_coverage.py` → 9 passed |
| `zh_CN.mo` 与 `.po` 不同步（曾实测 `compile_po.py --check` rc=1） | 同上批 | 复跑 rc=0 |
| `tests/frontend/test_regression_2026_09_22_gates.mjs` 残留使 `test_every_frontend_mjs_is_registered` 判红 | 21:0x 删除 | 复跑 → 5 passed |
| `check_annotations.py` 的注释密度违规 | 并发改动中消除 | 复跑 rc=0 |
| **S-03** `web/index.html` 头部孤立闭合标签（quirks 模式） | 22:08 由并发包修复，并新增 `tests/test_web_index_structure.py` 三条结构锁 | 复跑该锁 → `3 passed`；盘上首行即 `<!DOCTYPE html>`、`</body>` 恰 1 次 |
| `CODE_WIKI.md` / `CODE_WIKI_EN.md` 文档 H1 之上的头部重复块（35 行 / 49 行，含 4 组重复条目标题） | 22:20 由本会话按用户指令清理 | 逐行断言「被删非空行在正文仍存在」PASS（唯一例外是那条仍带去日期化前文件名的 `验证` bullet，正文有去日期化同句、读数未丢）；两文件首行即各自 H1、`###` 级重复标题归零、纯 LF 形态不变、`check_version.py` rc=0 |

### 7.4 全仓健康度横向结论

1. **注入与危险原语面**：`eval(`/`exec(`/`pickle`/`yaml.load`/`os.system` 在生产代码实测 **0 处**（唯一命中为 Qt `exec()` 事件循环、测试内带 `noqa` 的 `exec(compile(...))` 源码装载、`x-bogus.js` 混淆固有 `eval("require('crypto')")`、`typings/execjs/*.pyi` 的方法声明）；`shell=True` 仅 `run_gates.py` 受控退化形态且 argv 优先，`notify.py`/`utils.py` 对 `taskkill` 明令 argv 列表并带 `assert "shell" not in kwargs` 锁。
2. **凭据面**：`config/config.ini` 基线模板全敏感键为空值、`web_host = 127.0.0.1`，`config/URL_config.ini` 15 行均为注释 → **未发现真实凭据入库**；camelCase 凭据键（`accessToken`/`wsAuth`/`tk` 等）已在 `utils._SECRET_KEYS`。剩余凭据问题集中在 S-07 / M-17 两条日志侧防线。
3. **反序列化/外部数据**：`_tars.py` 手写解码器具备统边界 + size 拒收 + 无推进抛错，三类残留异常由 `tests/test_tars_frames.py:154` 显式钉为已知残留且证明「无挂死、游标不越界」；protobuf 畸形帧只丢包。
4. **并发/资源**：调度器容量计算、熔断探针租约、`collector.stop()` 与 `_run()` 的握手顺序、`_shutdown` 的 `asyncio.wait_for`、`ws_client` 的 `proxy=None`、模块级 `asyncio.Lock()` 单例 0 处、跨 await 凭据锁为 `RLock` —— AGENTS 点名的硬约束逐条实读命中，未见回归。真实资源问题集中在 M-25①（fd）、M-21②（unlink）、M-22（锁重入语义）、M-30④（无上限缓冲）。
5. **静态门禁面**：`mypy`（无参）+ `mypy --platform linux` + `mypy --platform win32`、`black`、`isort`（`Unable to parse file` 0 处）、`check_version`、`check_runtime_pins`（含 `--strict`）、`sync_metadata --check`、`check_annotations`（悬空符号引用 0 处）当前全绿；**定点 pytest 994 passed / 3 skipped / 1 failed**（唯一红为当时残留的 `.mjs` 登记，已由并发包修复）。
6. **文档同源性**：本轮暴露的最大治理问题是「事实源与代码互相说谎」——S-01（HEAD 提交态）、S-02（钉定表注释 vs 盘上内容）、S-04（AGENTS 的「静默降级」表述 vs 实测异常）、M-01（注释里的回归锁路径）、M-02（AGENTS 约束本体丢失）。这类问题的共同后果是**门禁全绿但防线不成立**，优先级应高于纯代码风格项。

---

## 8. 改进建议与修复优先级

### 8.1 优先级矩阵（按「风险 × 修复成本」排序）

| 优先级 | 项 | 风险若不动 | 修复成本 | 说明 |
| --- | --- | --- | --- | --- |
| **P0（阻断，须在下一次提交前完成）** | S-01 的**显式收尾提交** + S-02（还原 `liveme.js`）+ S-03（删 2 行 HTML 头）+ M-01（悬空引用 46 处）+ M-02/M-03/M-04（约束文本、模块头、2 条锁回植） | 主干不可运行、完整性防线变噪声、面板渲染降级、回归锁追溯链断裂 | 低（合计约 1~2 小时，其中 S-02/M-01/M-04 是「取回正确一侧」的机械动作） | 全部属 S-01 的直接余波；与正在进行的并发解决包合并落地最省事 |
| **P1（高危缺陷，建议本批一并修）** | S-04（`read_web_config` 走容错层 + 改正 AGENTS 那句）、S-06（stdin 接线 + 真机验证 mp4 停止产物）、S-07 + M-17（脱敏两处 + 棘轮判据补 `opener.open(`）、M-26（画质写假成功 / `update_or_append` 三态）、**M-34**（两处 `importorskip` 漏改，可中断整轮收集） | 面板整体打不开；录制产物不可播；凭据长期落盘；只读/占用态假成功；**一条收集错误即可让全量 pytest 与覆盖率门禁同时拿不到数据** | 低-中（M-34 两行改动；S-04/M-26 低-中；S-06 需一次真机） | S-04 是「配置损坏 → 无法经面板自救」的放大器，实际性价比最高的一修；M-34 属 AGENTS 有事故记录的同型缺口，改动面极小 |
| **P2（防线与门禁自证）** | S-05（三处自建客户端收敛到受管工厂 + 读点台账）、M-10（JS 钉定字节对账用例）、M-05 + M-13（Skill 同源升 error、hook 误拦与 fail-open 覆盖）、M-08/M-09（CI 条数守卫与触发器-文档矛盾）、M-12（`compile_po` 的 `errors=`）、M-23（三处 ignore/跟踪态破口）、M-16（冒烟回环覆盖窗口）、**M-32/M-33**（平台分支 `skipif` 与 `sys.platform` 裸改，共 12 处）、**M-35** | 漏防点位可被 SSRF/无界读利用；守卫自身失效被当成「漏洞」；PR 无 CI；镜像多带覆盖率报告；**Windows 侧三条防线在 CI 上静默消失**、注释锚点断链 | 中 | M-23 的 ②③ 含 `git rm --cached` 类操作，**属仓库状态变更，须由用户执行** |
| **P3（质量与可读性）** | M-24/M-25/M-27/M-28/M-29/M-30/M-31 中的功能正确性项、M-14/M-18/M-19/M-20/M-21/M-22、全部 L 组 | 画质降级链、GUI 观感/字体/动效、日志可读性、少量泄漏面 | 低→中（多可随重构顺势做） | 建议按「动到哪条链就补哪条锁」推进，不单独造大 diff |

### 8.2 流程性建议（防同类问题再生）

1. **把「冲突标记」做成硬门禁**：现无任何检查拦截 `^<<<<<<< ` 进入提交。建议新增一条只读门禁（或并入 `check_annotations.py`/pre-commit），判据为「跟踪文件中不得出现 `<<<<<<< `/`>>>>>>> ` 整行」，并让 `run_gates.py` 消费；S-01 这一族问题此后无法入库。
2. **钉定/锁类资产必须比对「值」而非「存在」**：M-10（JS 字节哈希）、M-11（注释引用的用例名）、M-01（回归锁路径）三个不同子系统犯同一错误——只断言「登记了」而不比对「登记值 == 实际」。建议按 §4 各项补齐。
3. **AGENTS.md 外迁时做「关键词双向对账」**：M-02 的根因是外迁后路由指向不含内容的文档。建议把 `scripts/check_skill_agents_consistency.py` 从「表格↔目录」扩到「外迁章节的锚点关键词必须在目标文件命中」，并将该项判红。
4. **解决冲突后必须复跑「同源锁族」**：本轮 4 个红点（i18n 目录、`.mjs` 登记、注释密度、`.mo` 同步）全部由同源锁族抓出，且全部在并发包内部被修——说明「解决即收尾门禁」的顺序不可省。建议把 `scripts/run_gates.py` + `pytest tests/test_i18n*.py tests/test_ci_frontend_registration.py` 固认为冲突解决的验收动作。

### 8.3 可复跑判据清单（供开发与运维复核）

```bash
# 1) 提交态与快照的冲突标记对比（HEAD 应为 899/102；工作区应为 0）
git grep -c '^<<<<<<< ' HEAD | awk -F: '{s+=$NF; n++} END{print "blocks="s, "files="n}'
git grep -c '^<<<<<<< ' | awk -F: '{s+=$NF} END{print "worktree blocks=" s+0}'

# 2) 语法可达性（venv 3.14，应 262/262）
PYTHONUTF8=1 .venv/Scripts/python.exe -c "import ast,pathlib;S={'.venv','node','ffmpeg','build','dist','__pycache__','.workbuddy','node_modules','.git'};b=[p for p in pathlib.Path('.').rglob('*.py') if not set(p.parts)&S and not (lambda t: (ast.parse(t) or True) is None)]"

# 3) 钉定表 vs 盘上字节（应 5/5 match）
PYTHONUTF8=1 .venv/Scripts/python.exe -c "import sys,hashlib,pathlib;sys.path.insert(0,'.');from src import utils;[print(n,hashlib.sha256((pathlib.Path('src/javascript')/n).read_bytes()).hexdigest()==e) for n,e in sorted(utils._JS_SHA256_EXPECTED.items())]"

# 4) 悬空回归锁引用（应为 0；当前 46）
git grep -nE 'test_regression_2026_(09_22|09_29|10_18|10_21)_[a-z_]+\.py' -- . | grep -v '^CODE_WIKI'

# 5) 面板重复键崩口（应不抛；当前抛 DuplicateOptionError）
PYTHONUTF8=1 .venv/Scripts/python.exe -c "import sys,tempfile,pathlib;sys.path.insert(0,'.');from src import web_config;p=pathlib.Path(tempfile.gettempdir())/'d.ini';p.write_text('[Web]\nweb_port=8080\nweb_port=9090\n');print(web_config.read_web_config(str(p)))"

# 6) Windows 优雅退出可达性（应 True；当前 False）
PYTHONUTF8=1 .venv/Scripts/python.exe -c "import subprocess;p=subprocess.Popen(['cmd','/c','exit 0'],stdin=subprocess.DEVNULL);p.wait();print('q 可写:',p.stdin is not None)"

# 7) 同源门禁（当前全绿；deps-audit 守卫需按 M-08 用 18 条判定）
PYTHONUTF8=1 .venv/Scripts/python.exe scripts/check_annotations.py
PYTHONUTF8=1 .venv/Scripts/python.exe scripts/compile_po.py --check
PYTHONUTF8=1 .venv/Scripts/python.exe scripts/check_skill_agents_consistency.py
PYTHONUTF8=1 .venv/Scripts/python.exe -m pytest -q -p no:cacheprovider --no-cov tests/test_ci_frontend_registration.py tests/test_i18n_migration.py
```

---

## 9. 总结与后续行动项

**结论**：本轮审查未发现「逻辑写错」意义上的大面积缺陷——录制链、选源探针、弹幕握手、调度器、容器格式映射、运行时二进制钉定与在线来源层三态、发布矩阵与多架构镜像合成等 AGENTS 钉定项，经逐行核对**均成立**，注入面与凭据入库面干净。真实风险高度集中在一次冲突提交引发的**状态性劣化**（S-01/S-02/S-03/M-01/M-02/M-04）与**文档承诺强于代码实现**的四个点位（S-04/S-06/S-07/M-06）。这类问题的共同特征是「所有既有门禁都绿」，因此整改必须与 §8.2 的三条自证增强同批落地，否则同类劣化还会再发生。

**行动项（建议按序执行）**

1. 【P0】完成并提交冲突解决：~~还原 `liveme.js`（S-02，已于 21:58 完成并配套新增 M-10 的字节对账锁）~~、~~删除 `web/index.html:1-2`（S-03，22:08 已修复并补 `tests/test_web_index_structure.py` 结构锁）~~、`read_web_config` 三处接容错层并改正 AGENTS 表述（S-04）、批量回改 46 处回归锁路径（M-01）、回植 `i18n.py`/`src/utils.py` 模块头与 2 条 Qt 用例（M-03/M-04）、把丢失的 4 条硬约束补进 references（M-02）、删除 3 个回流 Skill 目录并把一致性检查升为判红（M-05）。
2. 【P1】修 S-06（`stdin=subprocess.PIPE` + 收尾 close + 接线锁），**并做一次真实 URL 的 mp4 档停止录制验证**；修 S-07 + M-17（`_mask_url` 过 `mask_credentials`、8 处异常文本脱敏、棘轮判据补形态并补断言）；修 M-26（画质写回三态与假成功）；修 M-34（两处 `importorskip` 补子模块探测 + `exc_type=ImportError`）。
3. 【P2】收敛 S-05 三处自建客户端；补 M-10 的 JS 字节对账用例；修 M-08/M-09（CI 条数守卫、触发器与文档同源）；修 M-12/M-13/M-16/M-23；把 M-32 的 5 处 `skipif`/函数内 skip 改为「模块级常量 + shim 强制走分支」形态、M-33 的 8 处 `sys.platform` 裸改改为被测模块命名空间的 sys shim、修 M-35 的锚点与脆弱键；`.zcode/`、`config/URL_config.ini` 的索引摘除交回用户决定。
4. 【P3】按 §5/§4 逐条随重构消化；`main.py: create_app`（949 行）、`main.py: start_record`（796 行 / 14 层嵌套）、`main.py: main`（722 行）三个超长函数是本仓可读性与改动风险的主要聚集点，建议在下一条新功能落地前先做「纯拆分」重构并补行为基线用例（全仓超长函数 25 个、深嵌套 ≥6 层 28 个、≥9 形参 9 个，实测读数见 §2.2 方法 1）。
5. 【未执行项声明】本轮为纯静态审查：① 未跑全量 `pytest`（AGENTS 口径下会产 `.coverage`/触发 safe-delete 护栏，只跑了 994+ 条定点用例）；② 未做任何真机录制验证（S-06、M-24、M-25③、M-30①、`SOOP cookie` 等 5 项的后果判定为静态推定，标注为「待确认」，需真实 URL 增量验证后方可宣布修复完成）；③ 未联网核对 CI 实跑与工具版本同值性，门禁结论按「本地口径」记录。上述三项应作为 P1/P2 整改的验收前置动作。

---

## 附录 A：方法与覆盖的诚实边界

- **逐行精读覆盖**：根入口 8 个文件、`src/` 顶层 43 个、`src/gui_qt/` 17 个、`src/platforms/` 8 个、`src/proto/`（存根）、`web/` 4 个、`scripts/` 17 个（含 2 个 `.sh`）、`src/javascript/` 4 个、`tests/` 15 个文件全文 + 9 个文件的区间精读、CI/配置文件约 25 个 —— 合计约 175 个文件被完整读毕。
- **模式扫描覆盖**：全部 262 个 `.py`（AST 判据 + 结构度量 + 重复块检测）+ 全部跟踪文件（`git grep` 判据）；`tests/` 面另复用本仓自有判据函数（R1/R2/R3/R6/R8/R9/R10/R11）做全仓扫描，命中含 0 均记入 §6。
- **未逐行精读**：`tests/` 其余约 140 个测试文件（约 6.6 万行）仅由判据扫描与同源锁实跑覆盖；`i18n/*` 目录正文仅做键集合与抽样命中对账；`uv.lock` 仅取根包节点。
- **并发限制**：审查全程工作区被另一个解决包持续修改（起始 102 个未提交改动 → 定稿时 110 个），故 §7.3 单独登记「审查期内已被修复」的 4 项；本报告行号一律以各条目标注的实测时刻为准，复核先跑 §8.3 判据清单。
