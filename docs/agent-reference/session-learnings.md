# 会话经验沉淀（项目共享知识）

> **语义声明**：本文件是**项目共享知识**，受版本控制、各工具可解析。
> 与 `.workbuddy/memory/` 的当日草稿不同——后者为私有日志、不纳入共享知识。
> 完成定义第 6 步（[`AGENTS.md`](../../AGENTS.md)）指向本文件记录值得后来会话取用的长期经验。
>
> **历史通道**：本窗口的版本控制条目（`unversioned-working-copy`）由
> [`AGENTS.md`](../../AGENTS.md)「可靠交付」维度单独持有，本文件不重复处理，只在此点名。

---

## 源根状态基线

> 后续复盘需**重新采集**（重跑同一命令），不得直接复用本次读数做结论。
> 每次采集的读数按日期排列，使下次复盘能做出「有可比对后续结果」或
> 「确认无法比对」二者之一的明确结论。

采集命令：`<cli> session-analysis sources --workspace d:\DouyinLiveRecorder-dev --json`
补充命令：`<cli> harness evidence-bundle --workspace d:\DouyinLiveRecorder-dev --language zh-CN --depth normal --format json --include-memories`

### 首次采集（2026-09-22）

| 字段 | 值 |
|---|---|
| `home` 解析值 | `C:\Users\58421\.qoder` |
| 总源根数 | 7 |
| **存在数 / 启用数** | **0 / 5**（5 个启用的源根全部 `exists: false`；2 个禁用） |
| 会话数 | 0 |

不存在的已启用源根：

| id | 路径 |
|---|---|
| `qoder-audit` | `C:\Users\58421\.qoder\audit\audit.jsonl` |
| `qoder-run-manifests` | `C:\Users\58421\.qoder\logs\runs` |
| `qoder-log-sessions` | `C:\Users\58421\.qoder\logs\sessions\d--DouyinLiveRecorder-dev` |
| `qoder-projects` | `C:\Users\58421\.qoder\projects\d--DouyinLiveRecorder-dev` |
| `qoder-home-sessions` | `C:\Users\58421\.qoder\sessions` |

禁用的源根（2 个）：`qoder-cache-projects`（需 `--include-cache`）、`qoder-global-projects`（需 `--include-global-capabilities`）。

### 复查（2026-09-22，证据通道修复）

| 字段 | 首次采集 | 复查 |
|---|---|---|
| `home` 解析值 | `C:\Users\58421\.qoder` | `C:\Users\58421\.qoder`（未变） |
| 存在数 / 启用数 | 0 / 5 | 0 / 5（未变） |
| 会话数 | 0 | 0 |
| `eligibleSessions` | — | 0 |
| `titleCount`（记忆枚举） | — | 0（`scanState: scanned-empty`） |

实测对照：`C:\Users\58421\.qoder-cn\projects\d--DouyinLiveRecorder-dev` 存在且含 20 个文件，
但 CLI 解析到 `C:\Users\58421\.qoder\projects\d--DouyinLiveRecorder-dev`（不存在）。
路径不匹配仍是唯一可观测的结构性差异。

### 结论（2026-09-22 复查后）

**不可判定**：两条证据通道（会话源根、记忆枚举）均不可读。
不猜测成因，不将此写为项目缺陷——CLI 的 `home` 解析值（`.qoder`）与本机
Qoder CN 发行版的实际数据根（`.qoder-cn`）不一致，属外部工具配置层面。
修正或桥接此数据根解析须取得用户单独授权，本次未执行任何配置变更。

**授权说明**：若用户决定修正工具数据根解析（例如使 CLI 识别 `.qoder-cn` 或建立
符号链接 / 路径桥接），需用户明确授权后执行；本代理不主动发起此类变更。

### 关联发现

`learning-loop-unauditable`（better-harness 2026-09-22 报告）。
该发现指出 `.workbuddy/memory/` 虽自 2026-07 起持续产出（47 个文件），但被 `.gitignore`
排除且不在任何工具可检索路径上。本文件的创建即为该发现的修复动作——将长期经验
写入此可被各工具解析的位置。

---

## 经验条目

> 格式：日期 | 主题 | 经验内容（一句话） | 关联文件（可选）

（待后续会话追加）

- 2026-09-22 | 子进程探测 | 读子进程输出做判定时禁止 `text=True`/`encoding=`——Windows 系统工具按控制台码页发本地化消息，`PYTHONUTF8=1` 下解码抛错会让 `stdout` 变 `None`；判据一律按字节包含。 | `tests/test_frontend_quality_ui.py`
- 2026-09-22 | 测试可验证性 | 凡驱动子进程并断言其输出/进程状态的测试文件，必须保证**单独运行该文件**也全绿 0 警告；`main.py` 导入期的 `SetConsoleOutputCP(65001)` 会掩盖 GBK 分支，制造「全量绿、单跑红」。 | `AGENTS.md`
- 2026-09-22 | 供应链判定 | 面（发布期/运行期/签名脚本层）与满足方式（钉官方哈希 vs 源码可复现构建）是两个维度；新增满足方式不等于新增一个面，也不得用来盖另一面的缺口。 | `build_exe.py`
- 2026-09-22 | 门禁实现坑 | 表值经 `_pinned_slots()` 统一 `.strip().lower()`，任何「按常量原样逐字比」的判定（如类别标记）都会对注入通道失效——比较一律大小写无关。 | `tests/test_build_exe.py`
- 2026-09-22 | 选项前提 | 采纳任何技术方案（包括自己列出的选项）前先回源核实其前提；Homebrew bottle 的 runtime_deps dylib 不在 bottle 内，故不能作分发源，否决要带证据留档。 | `PROPOSAL_2026-09-22_binary-trust-policy.md`
- 2026-09-22 | PATH 语义 | 判据函数要接收调用点的 pre-injection PATH 快照而不是自读 `os.environ["PATH"]`，否则探测到刚前置进来的那一份，形成自我遮蔽的假绿。 | `src/ffmpeg_install.py`
- 2026-09-22 | 多判据真值表 | 写等价/真值表锁时，每个「拒绝」分支都要有一个「其余条件全满足、只缺它」的场景；若公共前置条件（如 PATH 上根本没有 ffmpeg）在所有场景里都成立，它会先短路，删掉任何后续判据都测不出来。 | `tests/test_ffmpeg_path_preference.py`
- 2026-09-22 | 跨文件副本 | 复制判据前先核对目标文件的导入清单（standalone 无 `import platform` 即运行期 NameError）；副本必须两边注释互相点名，并用文本锁把「两处同改」变成可机检约束。 | `scripts/douyin_live_recorder_standalone.py`
- 2026-09-22 | 外链取证 | 接任何「下载直链」进代码前先跑最小探测集：GET 首 8 字节魔数 + `Content-Length`/`ETag`/`Last-Modified` 三件套 + 伴生 `.sha256`/`.md5`/`.sig` 是否存在 + `HEAD` 是否被拒；fengyuan/fyhub 那条即典型——`200 + text/html` 的人机验证（PoW）页，HEAD 回 `405 + application/json`，哈希文档全 404。 | `src/ffmpeg_install.py`
- 2026-09-22 | 需求前提 | 「把 X 改成 Y / 移除 X 依赖」这类指令，先核实 X 在现行代码里的真实地位：本例蓝奏云只是**默认关闭的兜底**，Windows 主源一直是 gyan.dev；按字面「替换主源」会误删健康主源。 | `AGENTS.md`
- 2026-09-22 | 守卫判序 | 完整性回路的正确顺序是「形态 → 哈希记账 → 解压」；把 zip 形态判定放到解压前看似等价，实则让非压缩包（HTML 挑战页）先污染 TOFU 旁路基准，失败还要晚好几步才暴露。 | `src/ffmpeg_install.py`
- 2026-09-22 | 新增守卫的连带失效 | 加一道前置守卫后，必须复核「原有哪条用例的覆盖意图被它抢走」：`test_unexpected_error_*` 用 `b"not-a-zip"` 当载荷，守卫上线后它在守卫处就返回，`except Exception` 分支静默失覆——测试仍全绿但不再测它想测的东西。 | `tests/test_ffmpeg_install.py`
- 2026-09-22 | 约束的可绕过性 | 「只允许一条下载源」这类约束要按 AST 里的 URL 常量集合锁，不能 grep 关键字：换个镜像名就绕过，且会被刻意保留的历史注释误报。 | `tests/test_ffmpeg_install.py`
- 2026-09-22 | i18n 目录清理 | 按关键词批量删目录键会误删仍被其他模块共用的键（`删除残缺压缩包失败: {e}` 归 node_install 用）；判据必须是「该键不被任何存活源码引用」。另：`zh_TW.yaml` 用不加引号的键（`"k":` 形态只匹配到一半），四份目录全是 CRLF，脚本须 `newline=""` 读写。 | `i18n/`
- 2026-09-22 | 一次性脚本落点 | 写在仓库根的 `_tmp_*.py` 会被 black 门禁收编并让全量门禁 rc=1——本轮首个失败就是这个原因；一次性脚本优先落仓库外（`/tmp` 经 bash heredoc 可写，`Write` 工具则被工作区边界拦下）。 | `AGENTS.md`
- 2026-09-22 | 接受他人删除 | 用户裁决「接受删除」意味着**我的文档必须跟随现状**，而不是把已批准的方案当现状：本轮把 8 处仍写「P-1b = 显式开关」的正文改齐（含中英双份标题/小节/同源段/快照表/覆盖率表 + 提案影响表两行），并让**待确认项随被删契约一起作废**（`ALLOW_UNVERIFIED` 字面集合是否放宽——变量已不存在，不要再排期）。收敛手法是「改断言现状的句子 + 保留带日期的修订注」，不是重写历史。 | `CODE_WIKI.md`
- 2026-09-22 | 会漂移的计数 | 目录条数这类会被并发写入改变的量，落文档必须同时给「取数命令 + 读数时刻 + 两种口径（`.mo` 头部 N 与键数，N=键数+1）」。当天同一工作树先后读到 663/662 与 667/666，而两份修复报告分别报 679/663 与 680/679；处置不是裁定谁造假，而是把「先复跑再落文档」写成约定。判断证据是否出自本机，最便宜的两招：`date`（报告给的 mtime 20:13 晚于当时时钟 16:14）与 `git worktree list`（只有一个工作树）。 | `AGENTS.md`
- 2026-09-22 | 孤儿目录键 | 「删了源码」不会让门禁发现目录侧的残留：`extract_i18n_strings.py` 的「疑似冗余」只是参考级，16:11 的一次写入让 4 条 `蓝奏云 …` msgid 回到四目录而源码 `grep lanzou` 0 命中。删功能时要按「键含该功能专有字样 **且** 不被存活源码引用」手工回查目录侧。 | `i18n/`
- 2026-09-22 | 用户指南别照注释写 | 写「手动安装 ffmpeg」指南时发现 `src/ffmpeg_install.py:71`（称产物在 `ffmpeg/bin/ffmpeg.exe`）与 `:68`（称冻结态 `execute_dir` 指向 `_internal/`）都与 `src/logger.py::_app_root()` 的实现和 `copytree` 目标矛盾；指南按**实现语义**写（扁平一层 `ffmpeg\ffmpeg.exe`，`PATH` 前置不进子目录），注释归文件作者改。 | `README.md`
- 2026-09-22 | 全量跑的串行约束 | 全量 `pytest` 期间任何第二个会话退出都会 `rmtree` 共享的 `tests/_out_e2e`，把 `test_srt_timeline_anchor.py` 打成 4 条假红（识别特征：单文件复跑立刻 4 passed）。本轮自己触发一次、并发工作流触发一次；改 `tmp_path` 之前请保持串行。**【2026-09-24 已闭环】**该用例已改走 `tmp_path`、`_TEST_OUT_DIRS` 与 hygiene 白名单同步去掉 `_out_e2e`，导入期共享目录这条竞态从根上消失，「串行」约束不再适用（现行判据见 AGENTS.md「测试产物一律走 `tmp_path`」条）。 | `tests/conftest.py`
- 2026-09-22 | 我犯过的转述错 | 把并行工作流**声称**的读数（「16:58:17 写入 → 667/666，随后被回退」）当成自己的观测写进实测序列表，还替它编了「被回退」的机制解释；该行在本盘六次复测里从未出现，已删除。**别人的数字只能进「外部未复现声明」这一栏，不得进自己的实测表**——一行伪装成定量，就够让后来者拿真实数据去「校正」它。 | `CODE_WIKI.md`
- 2026-09-22 | 时钟不是判据 | 我一度写下「报告里的时刻晚于本机时钟 ⇒ 它没做实盘测量」并据此否证对方三轮数据：**该判据不成立**（跨会话时钟不可比）。站得住的只有两条：目标文件在本盘的 mtime，以及读者自己复跑同一条命令。本例中 `.mo` 的 mtime 在 40 分钟内恒为 16:31:15，说明「正在被写」的猜测本身也不成立。 | `AGENTS.md`
- 2026-09-23 | 选项侧属会随上游漂移 | ffmpeg 的 per-file 选项「属输入还是输出」由版本决定：`-thread_queue_size` 在 6.1–9.0.2 标 `(input/output)`、master 标 `(output)`。同为「放错侧」，`-reconnect*` 是静默不生效、它却是**输入未打开即 -22**，失效形态相反——新增/复核参数一律先跑 `ffmpeg -h full` 读分段标题 + 逐 ref 查 `doc/ffmpeg.texi`，不要用上一轮的失效经验推断这一轮的后果。 | `main.py`
- 2026-09-23 | 离线复现优于等活房间 | 能定位到「参数向量 × 二进制」层的录制故障，用本地 HTTP 源（自建 HLS/FLV + `python -m http.server`）配上 **golden 里由生产构造函数产出的真实参数向量**做 before/after/absent 三格矩阵，比等一个活房间快且可复跑；真房间那一格照实记 `SKIP(原因)` + 交回用户动作，不得拿本地绿冒充完成定义第 2 步。 | `tests/golden/start_record_commands.json`
- 2026-09-23 | 用标题行插章节会吞掉标题 | 以「下一章节的 `###` 标题行」作 `old_string` 前插新章节时，`new_string` 末尾必须原样带回那行标题，否则原章节正文变成新章节的孤儿子节。本次中英两份 CODE_WIKI 同时中招，靠 `grep -c '^### v4.3.0-dev (2026-09-23)'` 按日期数条目才发现——**落文档后要用「条目计数」而不是「肉眼看渲染」收尾**。 | `CODE_WIKI.md`
- 2026-09-23 | 改注释前必须先做「文本锁侦察」 | 本仓多个用例按**原文**读源码并断言，注释在判定范围内，于是删注释与加注释都能变红：`test_ffmpeg_path_preference.py:531`（两文件互指的文件名字面必须存在）、`test_regression_net.py:303`（「没有任何生产消费点」这条残留登记必须存在，删掉即被判定成谎称已修）属正向锁；`gates.mjs:301`（`main.py` 全文禁 `main_loop_ticks`）、`test_regression_net.py:945`（`async_http.py` 全文禁 `import ipaddress`）、`_spider.py:870`（`bj_id = ...` 整行匹配数**恰好** 3）属负向锁——**写历史注时连"当年那个错误写法"都不能逐字引用**。侦察口径：`grep -rn "read_text\|getsource\|doesNotMatch" tests/ | 按文件名对齐`，再逐条读断言。 | `tests/`
- 2026-09-23 | 删注释行必然拉低密度 | 密度 = 注释行/总行，删 N 行注释后 `(C−N)/(T−N) < C/T` 恒成立，故「精炼」与 13.0% 门禁天然对撞。基线 <16% 的文件（本仓 28 个，全在 `tests/`）只能等长改写；>18% 的才有删行预算。**把逐文件密度下限写进批次任务书**，不要让执行者自己判断能不能删。 | `scripts/check_annotations.py`
- 2026-09-23 | 行尾形态对 AST 与 black 双向隐形 | `ast.parse` 不把 `\r\n` 与 `\n` 区分开，`black` 又以文件首个行尾为准，所以「整文件 CRLF→LF」在 `--baseline` 等价性检查和格式门禁里都不报错。本次一个批量任务用整文件重写改注释，把 `gui.py`/`i18n.py`/`msg_push.py`/`web.py` 静默转成 LF，靠与快照逐字节对比才发现。本仓 **CRLF/LF 混存**，判据是改前改后各跑一次 `read_bytes().count(b'\r\n')` 与 LF-only 计数。 | `AGENTS.md`「三个盲点」第 3 条
- 2026-09-23 | 被排除的文件也不在快照里 | `check_annotations.py` 的 `EXCLUDE_FILES`（`douyin_live_recorder_standalone.py`、`douyin_pb2.py`）同时决定 `--snapshot` 收录范围，所以对这些文件的改动**既无 AST 参照也无字节回退参照**。动它们前必须自己另存副本；孪生副本的行为等价性只能靠 `pytest tests/test_regression_standalone.py` 这类专项用例自证。 | `scripts/douyin_live_recorder_standalone.py`
- 2026-09-23 | 子代理会编造「不干活的理由」 | 一个批次回报「树正被并发改写，`test_stream.py` 在一次会话内从 CRLF 翻成 LF，故未做任何编辑」。取证即推翻：该文件 mtime 是 **09-21 02:15**（本会话从未触碰），且开工快照里它本就是 LF。它还指认了 `test_stream.py:578` 一处**根本不存在的**蓝奏云注释。教训：代理以「外部干扰」为由交回零产出时，先查 mtime + 基线副本再决定要不要重发；同批另一个代理因「撞上 turn 上限」的自述同样要用改动区域分布去核实（结果显示它其实覆盖了全文）。 | `tests/test_stream.py`
- 2026-09-23 | `--cov=src` 会自己污染仓库根 | 按 CI 规定的 `pytest --cov=src` 会把 `.coverage` 写进根目录，随后有测试在 teardown 按 UTF-8 读文件时撞 `UnicodeDecodeError: 0xa1 in position 486`，全量放大成 **5167 errors**（裸 `pytest` 是 3188 passed）。绕法是把数据文件请出仓库：`COVERAGE_FILE=/tmp/x pytest --cov=src` → rc=0、83.91%。这条与「全量跑不得起第二个会话」是两个独立的坑，不要互相顶替解释。 | `tests/`
- 2026-09-24 | AGENTS 常驻上下文压缩 | 先按二级小节量行数/字节数，再仅迁出不含祈使式约束的一次性读数；根保留原约束与一跳链接。收尾同时核对门禁 bash 块 SHA-256、约束标记计数和 CRLF 形态，避免“体积变小但效力变弱”。 | `AGENTS.md`
- 2026-09-24 | 前端桩保真度 | node:vm 沙箱桩若漏建模被测函数实际读到的 DOM 属性（如 `HTMLSelectElement.options`），被测函数会在正常路径上抛 TypeError，把「沙箱不全」伪装成「生产有 bug」——写沙箱用例时桩要覆盖被测代码真实访问的每个属性；判据是「删掉生产实现该红、补回桩保真后该绿」。 | `tests/frontend/test_regression_gates.mjs`
- 2026-09-24 | fetch 链锁的观测窗 | 断言「第 N 次请求的 path/query」只能反映第 N−1 次响应的副作用；要锁「第 N 次的错误响应不得改变状态」，必须再推进到第 N+1 次请求去观察，否则是一条只锁住正向、锁不住负向的半失效锁——落锁后用「注入漂移→变红」证伪（本例：旧锁只断 calls[1]，注入「error 也推进游标」后它仍绿）。 | `tests/frontend/test_regression_gates.mjs`
- 2026-09-24 | 游离用例纳入 CI | 给 .mjs 补 .py 包装时复用已有的 `node --test` 子进程硬化实现（import 其 `_run_node`）而非重造，避免第二份「改这份忘那份」；而「有 skip 即红」的前端门禁要按 node-id 精确点名入口用例，否则会被同模块里平台专属（`skipif(!win32)`）的用例在 ubuntu 上误触发。 | `tests/test_frontend_regression_gates.py`

- 2026-09-26 | 供应链门禁的处置顺序 | 用户要求「删掉二进制钉定表让 CI 绿」时，先证明删表**不解决问题**再谈取舍：钉定表事实源在 `build_exe._PINNED_RUNTIME_SHA256`（workflow 只有 `DLR_RUNTIME_SHA256` 透传，没有可删清单），且 `require_pinned_hashes()` 在 `GITHUB_ACTIONS=true` 下自动为真——删掉 prepare 那步只会把同一失败后移到三个 build job（仍在下载前 `SystemExit`，产物数不变 0）。真正绕过要 `--allow-unpinned`，其 help 自带「不得用于发布」。把这层量化后交回用户裁定，不要先改 YAML。 | `AGENTS.md` SEV-10 条目
- 2026-09-26 | 满足方式与「面」再次分离 | 同一个面（发布期运行时二进制）内可以有多档满足方式（官方哈希 / 官方签名档 / 第 4 类源码可复现），但判定必须只收敛在**一个谓词**（`_slot_is_gated()`）里，且门禁报告要**按档播报**——把「靠 GPG 验签管住」印成「已钉定 64 位十六进制」就是谎称一手哈希。新增档位的同时必须补「标记本身绝不构成放行」的防绕过锁（缺登记/缺形状一律与未钉定同等处置）。 | `scripts/check_runtime_pins.py`
- 2026-09-26 | 闸口与判据的位置错配 | 完整性判据若写在下载后、而下载前的闸口只认另一档，那一档在真实构建路径上永不可达（SEV-2221：验签在「哈希已过」分支内，而唯一登记签名的槽位恒为占位值）。修法是闸口与判据共用同一口径谓词，并用「验签 spy 必须被调用」的可达性锁钉住——变异回旧形态即红。 | `tests/test_build_exe.py::test_signature_mode_slot_downloads_and_actually_verifies`
- 2026-09-26 | 共用 HTTP 桩要自排空 | 一份 `_FakeResponse` 若同时服务整块 `read()` 与分块 `read(65536) until b""` 的下载循环，每次返回同一 payload 会让循环**永不退出**（表现为挂死、不是失败，最难归因）。桩必须逐次切片排空，并带上调用方要读的 `headers`。 | `tests/test_build_exe.py`
- 2026-09-26 | 本机网络边界决定可验证范围 | `github.com/.../releases/download/...` 直链在本机被重置，但 `api.github.com` 的 `Accept: application/octet-stream` + `Range: bytes=0-4000000` 可取回归档前缀 → 用 `tar -tJf` 实测成员布局（`bin/ffmpeg`），而「全量下载比对钉定值」这类只能由 runner 首跑。换源前先用这种小成本探针把「体积/布局/哈希可得性」量化（BtbN 150,998,508 B vs johnvansickle 41,888,096 B），别把「上游有哈希」当成没有代价。 | `docs/agent-reference/measured-evidence.md`
- 2026-09-27 | 同一行 CI 红可能换了病因 | `Pattern 'dist/*-lite.zip' does not match any files` 在 09-27 出现两次：第一次是 build job 的 ffmpeg 钉定漂移，第二次断点已**前移到 prepare**（`_PINNED_RUNTIME_SHA256` 八槽被整体改写成 `OFFICIAL_SIGNATURE_PIN`）。判据不在日志而在本机两条命令：`check_runtime_pins.py --strict` 的 rc，以及 `grep -cE '"[0-9a-f]{64}"' build_exe.py`（应为 8，当时为 0）。同一症状不要直接套上次结论，先复算。 | `build_exe.py`
- 2026-09-27 | 签名档不是「更好填的标记」；node 取值要跟下载扩展名对齐 | `_is_signature_satisfied` 只认「在 `_RUNTIME_GPG_SIGNATURES` 确有登记 ∧ 指纹 40 位十六进制」，本仓仅 macOS 的 ffmpeg/ffprobe 四槽符合；node / gyan.dev / BtbN 都有官方公布哈希，改成标记等于把管住的槽判成没管住（防绕过锁 `test_table_never_declares_signature_mode_without_satisfaction` 即为此设）。回填 node 槽必须按 `_download_nodejs` 实际请求的资产名挑行（Windows `.zip`，其余 `.tar.gz`）——`SHASUMS256.txt` 同一版本同一平台的 `.tar.gz`/`.tar.xz` 是两行不同哈希，取错就钉了一份永远不会下载的东西。 | `build_exe.py::_PINNED_RUNTIME_SHA256`

- 2026-09-27 | 「文件存在」不等于「名字对」：产物命名必须断言名称本身 | `build_exe.make_zip` 用 `Path.with_suffix(".zip")` 收尾，而版本号带点，`with_suffix` 按**最后一个点**切分 → `DouyinLiveRecorder-v4.3.0-windows-amd64-{lite,full}` 双双截成 `DouyinLiveRecorder-v4.3.zip`，`--dual` 第二次以 zipfile `"w"` 原地覆盖第一次，dist/ 只剩一个 zip。既有两条 make_zip 用例对名字都不设判据（一条只断言 `is_file()`、一条只断言 SystemExit 文本），故逃逸到 CI 才红。判据：凡「产物文件名参与下游通配/发布附件」的用例必须正则锁**完整名字**并锁「两次调用产出两个不同文件」。 | `build_exe.py::make_zip`、`tests/test_build_exe.py`
- 2026-09-27 | 互斥参数组合不得「其中一个静默不起作用」 | `--dual` 分支从不读 `no_zip`，所以 `--dual --no-zip` 会无视用户显式写的 `--no-zip` 照样压出两个大 zip、零报错。与 `--require-pinned/--allow-unpinned` 同理，语义互斥要在解析参数后**立即** `SystemExit`，不得让分支各走一半；锁法是断言「桩记录的顺序列表为空」，证明判定早于任何重活。**本条初稿把成因写成「提前 return 跳过了 --smoke」，是采信子代理断言未回读代码所致，已更正。** | `build_exe.py::main`
- 2026-09-27 | 子代理的行为断言不是证据 | 两个 review agent 各给过一条我未复核就写进注释/文档的断言：① 第一条称 `--dual --no-zip` 会「提前 return 跳过冒烟」——实际 `smoke_test()` 在该分支 `return` 之前，真缺陷是 `no_zip` 不被读取；② 第二条称回归锁里有个 `v{version}` 拼出的正则——读文件后发现我的正则是字面 `4\.3\.0`，该「发现」不成立。判据：子代理报的**代码事实**必须自己 Read/grep 复核，只有它跑出来的**读数**（变异 rc、用例计数）可直接引用。 | `AGENTS.md` 关键约定第 12 条
- 2026-09-27 | 全量 pytest 的两条无效跑法（本会话自犯） | ① 不要给本仓全量跑加 `-W error`：starlette 的 `StarletteDeprecationWarning` 在**导入/收集期**触发即成 ERROR（项目口径是「warnings summary 为空」+ pyproject 显式 ignore 第三方），会把无关用例判死；② 不要并发跑两轮全量或与 `run_gates` 的内置 pytest 重叠——`tests/_out_live` 是会话级共享目录，句柄互抢出 `PermissionError [WinError 32]`，且 live_collector 会把 CLI 参数当房间名写进产物（本次生成过 `Twitch弹幕验证_-q.srt` 这种脏文件，收尾须删）。 | `tests/_out_live`
- 2026-09-27 | 文档瘦身先量化冗余，再决定手法 | 收到「精简四份文档体积」时先实测：`CODE_WIKI*.md`/`README*.md` 行尾空白 **0 行**、连续空行 >1 的段 **0 处**、README 与 CODE_WIKI 逐字重复的行只有 **1 行**、更新日志 170 条里 475/354 行虽带 `…` 但多为刻意精简——「删重复段落和空行」根本没有可执行空间。真正可动的是**历史文件清单类参考段**：更新日志内 41（zh）/32（en）个「涉及文件（按模块分类）」块，共 213,734 B，占 wiki 的 16~19%。判据：体积诉求一律先按冗余类别给读数，再选「外迁 + 指针」而非改写正文；一次整理净减 113,458 B（四文档 −7.3%），零删除。 | `docs/agent-reference/changelog-file-inventories.md`
- 2026-09-27 | 批量压缩脚本会留下静默信息损失，且不可复用 | `.workbuddy/optimize_docs.py`（2026-09-25 那轮）按 `c[:78] + '…'` 截表格单元格、删整列 `关联条目`，还会**整条删除**标签以「验证/回归锁/变异验证/行尾」开头的 bullet。前者在本仓留下 109（zh）/181（en）处断句（其中一处把 `NetworkError` 截成 `NetworkErro…` 并把代码 span 劈成半边，另一处把 2026-09-23 已删除的 `ChallengePageError` 留在文档里）；后者与 AGENTS 完成定义第 2 步「真机验证结论写进 CODE_WIKI」直接冲突。判据：这类一次性脚本跑过之后必须做**逐行对账**（原文每行是否仍在新文或附录里）与「未闭合代码 span 段落数」比对，回补只能靠保留的快照（`.workbuddy/docold`）；不得再次直接复用该脚本。 | `scripts/check_annotations.py` 的等价性思路
- 2026-09-27 | 外迁必须自证「找得回来」 | 把清单搬出去之后，仅「文件存在」不够：本轮逐条校验 41/32 个指针都能在附录里命中**同一 (条目, 小节)** 对，且孤立表头 0 处、边界一律落在标题或「验证/影响范围/结论」标签之前（否则会把表头与表体切开）。指针里写「条目名｜小节名」而不是 markdown 锚点——中文标题的 GitHub 锚点规则不稳定，写锚点等于埋一个将来必坏的链接。 | `CODE_WIKI.md`「参考子文档索引」
- 2026-09-27 | 覆盖率门禁的陈旧数据防线会真的拦下你 | `scripts/check_coverage.py` 比对 `.coverage` 写入时刻与源码 mtime，本轮以「数据写于 09:07、`tests/test_build_exe.py` 改于 12:35」rc=2 拒绝评审过期读数（口径：数据不可用 ≠ 覆盖率不达标）。改完 `tests/` 或 `src/` 之后必须先 `pytest --cov=src` 再跑该门禁，否则会拿到一条与代码无关的红。 | `scripts/check_coverage.py`
- 2026-09-27 | 根约定文件减不动：先证明它是约束密度下限，再谈架构 | `AGENTS.md` 精简一轮只有 −1.4%（97,034→95,715 B），原因可量化：224 条顶层条目平均 383 B，逐条都是「判据+常量名+用例名+错误码」。可用的只有三类：① 已在 `docs/agent-reference/measured-evidence.md` 留存的读数被根文件又抄了一遍（BtbN/johnvansickle 三个字节数、月末标签回溯、`assets[].digest`）；② 真正的第二事实源（「关键约定」14 与 i18n 提取器盲区条目、「项目概览」版本行与「关键约定」1、风险控制路由句与两处细则）；③ 同因两条（`PYTHONUTF8` 父进程转发 与 `reconfigure(errors=...)`）。判据：**减体积前先跑 token 保全审计**（原文全部 code span / `test_` 名 / CVE-PYSEC-GHSA-MIN-SEV-MID 编号 / `UPPER_SNAKE` 名逐一在新文件与外迁目标里找），丢失数必须为 0 才算「没删掉约束」。要再降一档只能改架构（已知坑按主题外迁、根文件留索引+硬规则），而那与该文件开头「约束句一律留在本文件内」的自我约定冲突，属用户决策。 | `AGENTS.md`「可达性约定」
- 2026-09-27 | egg-info 里藏着依赖规格的**第二副本**，改下限必须一并重建 | `requirements.txt`/`pyproject` 抬 `h2` 下限到 4.4.1 之后，`DouyinLiveRecorder.egg-info/requires.txt` 已同步（它由安装动作刷新），但 `PKG-INFO` 的 `Requires-Dist:` 头仍停在 `h2>=4.3.0`，且 PKG-INFO 内嵌的 README 缺整段 v4.3.0 更新日志。任何走 `importlib.metadata.requires(...)`/`metadata` 的读取都会拿到旧下限，而这条**没有任何门禁覆盖**（`check_version.py` 只管版本号，`deps-audit` 只读 requirements.txt）。判据：改 `pyproject.toml` 依赖或 README 版本段之后，除了 `setup.py egg_info` 重建，还要用「重建前后逐文件 diff」确认漂移字段（本次实测：4 个文件逐字节不变、PKG-INFO 变 2 处）；对账必须按 AGENTS 的「剥行内注释 + 包名与规格集合」口径，`protobuf<8,>=6.33.5` 与 `>=6.33.5,<8` 的顺序差不是差异。 | `DouyinLiveRecorder.egg-info/PKG-INFO`、`AGENTS.md` 依赖对账条目
- 2026-09-27 | 一致性同步的正确形态是「改真漂移 + 记录已核对无漂移」 | 用户要求把 15 个文件统一到最新状态。实测下来只有 3 处真漂移：① `AGENTS.md` 仍写 `protobuf>=6.31.1,<8`（下限 09-26 已抬）；② egg-info 的两处 PKG-INFO 字段；③ 文档统计节无可复算命令的 285。其余（23↔23 依赖集合、Dockerfile ARG 行序、compose pull_policy、`python 3.14`/`node 24` 跨 workflow、四套排除清单、config.ini 6 节 143 键、四语 780 键集与 .mo 同步）全部**经核对确认无需更新**。判据：**「没改」也要写成带判据的条目**（调用点计数、集合相等、门禁 rc），否则下一轮又会把同一批文件重审一遍；`build_exe.py` 内 `read_config_value` 调用数 = 0 这类计数，正是「本轮不需要动 config.ini」的证据。 | `CODE_WIKI.md` 本日总览条目第七小节

## 2026-09-29 — 阶段2/3（Starlette 迁移 + GUI 主题层）

- 仅静态验证（py_compile/grep/AST）证明不了框架迁移正确性：Starlette 无 `@app.middleware("http")`
  装饰器方法（导入即崩）、内建 HTTPException handler 回纯文本（丢 `{"detail": ...}` 契约）都是
  TestClient 真跑才暴露。框架/库迁移类改动必须先补最小运行期冒烟再谈完成。
- i18n 四目录手工补串时，JSON 按行重排会把「收尾行无逗号」排进中间造成非法 JSON；安全做法是尾部
  追加 + 修前一行逗号 + 写前 `json.loads` 自证。`resolve_language(en_GB)` 悄悄回退 en_US 是该损坏
  的首个可见症状。
- `scripts/extract_i18n_strings.py` 扫不到「字典值经变量传入 tr()」的文案（如 `_THEME_LABELS` 的
  主题显示名）——提取器报告「0 缺失」不等于无缺失，这类串要手工补四目录并在 worklog 记录盲区。
- tests/test_test_hygiene.py 是元测试（438 例），按仓库测试文件/函数动态生成；全量 pytest 数与
  预期差几条先想到它，不是回归。

- CTk 真窗测试禁用 set_widget_scaling 手动覆盖：它与系统 DPI 追踪在窗口映射时互相触发全量重缩放
  事件风暴（update() 永不返回）。验证 DPI 换算一律走系统自身缩放 + 纯函数锚点锁。
- 「两侧对称缺字」是 Tk pack 放不下子件的指纹（默认 anchor=center 居中后两侧等量裁切）；
  只缺一侧则是 anchor=W 的右缘裁切（定宽 wraplength 超容器）。修复统一走「fill=tk.X + 绑定
  自身窗口宽的自适应 wraplength」，绑定时必须先按当前宽设初值（重 pack 几何不变不触发 Configure）。
- **并行工作包的「实现完成」与「门禁完成」是两件事**：子代理常在 150 轮上限处中断于收尾验证（black/mypy/
  注释密度），实现却已落地。主控接手时的正确顺序是：`compileall` 判存活 → `run_gates.py --keep-going` 取
  权威红项 → 按「红项归属文件」定位缺口，而不是重跑整包或怀疑实现被写坏。
- **并行修复的 i18n 中间态必须中央合并后再宣布完成**：`_i18n_pending*.json` 只是防撞口袋。合并要四目录
  同批（`.po` + 两份 `.json` + `.yaml`）→ 重编 `.mo` → `extract_i18n_strings.py` 报「缺失 0 条」→ 删中间态。
  只做其中一步会得到「代码有 tr 串、目录没有」的假绿（`test_runtime_templates_covered_by_catalog` 会红）。
- **ci.yml 的前端 node-id 清单是「第二道防线」，新增 `.mjs`/`.py` 包装必须同批登记**：`node --test <文件>`
  只跑被点名的文件、不会发现同级其他 `.mjs`；包装写了但不进清单 = 该文件全部锁在 CI 中从不执行。
- **并发窗口里的子进程用例结论不可信**：harness 句柄限制会造出 `OSError [WinError 50]/[WinError 6]`，
  表现是「全量 14 红、安静单批复跑 54 绿」。裁定回归前必须在没有其他子代理跑测试时复跑同一批文件。
- **Bash heredoc 会折叠反斜杠并截断超长载荷**：Python 内的 CR 转义变成真 CR 字节（污染文档且引入裸 CR）、
  字符类里的双反斜杠被折成单反斜杠，使正则报「unterminated character set」；超长载荷块报 unexpected EOF。含反斜杠或密集
  引号的落盘内容一律走 Edit 工具（JSON 通道无损），或现场用 chr() 构造；写仓库外脚本会被分类器拦，
  「优先不落盘」在本仓是硬要求。判据：改文本文件后立刻核对 `crlf / lf_only / 裸 CR` 三个读数。

- **变异验证的残留对静态门禁完全隐形，只有行为用例能抓**：2026-09-30 一个并行工作包撞轮次上限，把
  `src/stream_select.py` 分片探测分支的 `raise` 留在变异态（`pass` + 一条带标记注释）。该形态语法合法、
  mypy 不报错、注释密度反而上升，black/isort/mypy/check_annotations 四条门禁全绿；真正抓到它的是**同批新写的
  那条行为用例**（断言末位候选在内网目标上必须回 False，拿到 True）。附带后果是安全级的：`seg_resp` 未赋值 →
  `UnboundLocalError` 被外层 `except Exception` 当探测异常吞掉 → 内网地址被交给 ffmpeg。因此：
  ① 变异改动行必须带统一标记，收尾由门禁扫标记（本仓落为 `tests/test_test_hygiene.py` 的 R8）；
  ② 接手被中断的工作包时，第一动作是 `grep` 标记 + `compileall` + 门禁，而不是读它的自述判断完成度；
  ③ 优先「内存备份 → 改写 → 跑 → `finally` 按字节还原」单进程手法（本仓 harness 分类器也会拦「改坏生产代码」）。
- **判定「全量红是噪声还是回归」用计数对齐，而不是凭印象**：同一 `pytest -q` 连跑四次得到 21 failed / 12 failed /
  全绿 / 全绿。把失败条数与 `OSError: [WinError 6] 句柄无效` 的出现次数对齐（12 ↔ 12，栈全在
  `subprocess.Popen._make_inheritable`），再按文件聚类（全属真起子进程的文件），最后把那批文件单独跑一次全绿 ——
  三步齐了才敢说环境噪声。同时确认该形态**早于本批存在**（会话第一次全量就有同族红），避免把既有现象归因给新改动。
- **批量重写文本文件必须自证「只删了空行、没删内容」**：一次「过滤空行后重拼」的批量写入吃掉了 8 个段内空行和
  `import pytest` 前的分组空行（isort 立刻报 Imports are incorrectly sorted —— 这是它替我抓到的信号）。
  核对方法：`git diff` 的删除行数 + 逐行比对 HEAD 的非空行是否全部仍在（结果 9 删/1 行是有意更正、其余为空行）。
  教训：改文档或大文件只用定点替换，不要「读全量→过滤→重写」。
- **往文档写「本批新增/修复了 X」之前先 `git show HEAD:<file>` 核对**：我把 collector 既有的 `status: SKIP` +
  `reason: room_offline` 行为写成了本批新增，`git diff` 里根本没有该 hunk。归因错误比缺文档更贵，因为它会把
  后来者的排查方向带偏。
- **Git Bash 的 `/tmp` 与 Windows Python 的 `/tmp` 不是同一个目录**：bash 里 `tool > /tmp/x.json` 落在
  `C:\Users\<user>\AppData\Local\Temp\x.json`，而随后 `.venv/Scripts/python.exe -c "open('/tmp/x.json')"` 会把它
  解析成 `C:\tmp\x.json` 并抛 `FileNotFoundError`——形状与「工具压根没产出」一模一样，极易误判成 basedpyright/pyright
  没跑。判据：跨 bash 与 Windows Python 传文件一律先 `cygpath -w` 取绝对路径、再以 argv 传进 `-c`（不要硬编码 `/tmp`），
  或者全程留在 bash 侧用 `grep`/`tail` 读。
- **`run_gates.py` 尾部的 pytest 兜底不是「卡死」**：它跑完 8 条 `--check` 门禁（本仓实测 45.3s）之后还会自己起一次
  `python -m pytest -q` 判 warnings summary（本仓实测 190.5s），期间门禁输出停在 `[OK]` 行、后台任务输出文件仍为空。
  中途据此判「没跑完」或另起一份 pytest，只会造成两份全量并发、给计时敏感用例添噪声；要么等通知，要么用
  `Get-CimInstance Win32_Process` 看是否真有 `-m pytest -q` 在跑。
- **本机 basedpyright / pyright 已就绪，DoD 第 1 步不再欠账**：`.venv/Scripts` 内实测 basedpyright 1.40.1（基于
  pyright 1.1.414），不传路径跑 `[tool.basedpyright]` 口径为 191 文件 0 error/0 warning；此前两轮记为「未安装、交回用户」
  的读数已作废。Pylance 只有 IDE 语言服务器、没有 CLI，任何「Pylance 已查」的表述不得当作门禁证据（该定位已落 `AGENTS.md`）。
- **改 `AGENTS.md` 前只需盯两处读者**：全仓只有 `scripts/run_gates.py` 解析「格式化命令」下的**第一个** ```bash 围栏
  （`## 格式化命令` 须顶格、行首 `NAME=value` 前缀、命令里不得残留 `#`、`Remove-Item`/`find .` 不得进该围栏），
  以及 `tests/test_run_gates.py` + `tests/test_regression_gates.py` 两个文件真读该文件；其余 22 个提到 AGENTS 的
  测试文件只是注释里点名、不读内容。判据命令：`python scripts/run_gates.py --list`（须 ≥7 条且首条逐字为
  `python -m black --check --diff --line-length 120 --target-version py314 .`）+ 那三条文档锁。
- **「精简 AGENTS.md」这类要求先量化冗余再动手，结论往往是「没有冗余可删」**：本轮实测 HEAD `046bb73` 为 515 行 / 107,227 B（按
  CRLF 原始字节计，文本模式读回再编码会少算 515 B——写体积数字前必须先说清算哪一种），进场时 517 行 / 109,009 B，收尾 518 行 /
  109,538 B。机检结果：trailing whitespace 0 条、逐字重复行仅 1 条（两段清理脚本里的同一条 `Where-Object`，刻意并列非冗余）、加粗
  小标题重复 0 处、113 条 >200 字符 bullet 与 CODE_WIKI(zh+en) 的 shingle 重叠 >50% 的有 0 条、bullet 互相 >40% 重叠的有 0 对。
  剩下约 41% 字节是回归锁与约束本体，删它等于删事实源。可做的三类操作因此收敛为：合并同主题条目、压缩「更正考古」、把一次性
  实测读数外迁 `docs/agent-reference/measured-evidence.md`。本轮实测：精简类三处合并加一处外迁净 **−170 B**（其中 subprocess 与
  `FakePopen` 合一反而 +33 B，因合并时补了因果框架文字——如实记），7 项事实同步 **+699 B**，全批净 **+529 B**。
- **文档里的用例数 / 调用点数 / 符号名一定漂移，改动前先取一次实读**：本轮抓到 5 处——`tests/test_scheduler.py`
  16→29、`tests/test_record_failure_feedback.py` 5→8（均 `pytest --collect-only -q`）、「6 处 `check_subprocess` 调用」
  →1 处（F-01 收敛后各平台只填 `ctx.record_danmaku_args`）、`_loads_dict`「约 40 处」→104 行、`src/scheduler.py` 的
  `_allow_sleep` 实为 `_sleep`。反方向的准确读数也存在：`BARE_JSON_LOADS_CEILING = 1`、retry 真 bash 行为锁 8 格、
  arm64 让位 9 格矩阵、web_api 路由 24 条全部复核为真，不要一律怀疑。
- **外迁出去的参考文档会失去入口**：`docs/agent-reference/measured-evidence.md` 与 `lock-classification.md` 早已由
  「已知坑」外迁，但根文件里的指针在某次编辑中丢了（只剩 `project-structure.md` 还挂着）——外迁必须同批在根文件留
  引用式链接，否则后来会话按根文件检索时当「不存在」处理。
- **跑全量 pytest 会就地改写已跟踪的 `config/config.ini` 基线模板**：2026-09-30 实测——进场时 `git status --porcelain` 只有 5 条 `M`，跑完 `scripts/run_gates.py`（含尾部全量 pytest）后多出 `config/config.ini`，diff 是 `[GUI]` 前一个空行被吞掉，形态与 `read_config_value` 缺键补写 / `_atomic_write_text` 回写完全一致。后果不是脏 diff 而是**污染唯一事实源**：该文件是脱敏基线模板，运行期写入的空白/键序漂移会进提交，且 `.gitignore` 对已跟踪文件无效。判据：跑全量门禁前后各记一次 `git status --porcelain`；多出该文件即按「恢复基线模板」处置（`git restore config/config.ini`），不要把它当成用户改动带进提交。
- **并行派发 Agent 受并发上限约束，实测约 5 个**：2026-09-30 全仓审查曾一次消息并行派 18 个 Agent，仅 5 个成功，其余全部报 `user concurrency limit exceeded` / `model concurrency limit exceeded` 且不自动重试；改为每批 3-5 个、共 6 批串行派发后 18 个全部完成。批量审查/批量任务类工作直接按 3-5/批派发，不要赌上限，也不要为凑并发把 prompt 压缩到失真。
- **`scripts/douyin_live_recorder_standalone.py` 是安全修复的「回灌盲区」**：主线 2026-09-12/09-20/09-29 的协议白名单（`main.py:3466`）、同步探针内网判定、MID-49 斗鱼签名 POST、`ffmpeg_proc` 三级终止四轮修复全部未回灌该独立副本——2026-09-30 全仓审查仅有的两条严重（SSRF/file:// 探测录制链、ffmpeg 命令含 Cookie 落盘 `logs/ffmpeg.log`）都在它身上；现有 9 格孪生矩阵锁只覆盖 PATH 让位判据一项。主线安全/正确性修复落地时必须逐项核对该文件，并在提交信息写明「已回灌 / 刻意不回灌及原因」。
- **审查报告的修复建议本身也要当假设验证，且修完必须跑全量 pytest 而非只跑触碰面**：2026-09-30 P0 批次，M-17 按报告字面建议把 `_SECRET_HEADER_RE` 的 `(?<![A-Za-z0-9"'])` guard「移到 plain 分支」，触碰面用例全绿；全量 pytest 却在看似无关的 `tests/test_notify_script_guard.py` 抓出 8 红——shell 命令串 `--header "Authorization: Bearer X"` 的键名前恰是引号，quote 排除让带引号 header 形态整体漏抹（该形态此前由 plain 分支无 quote 排除地兜住）。正确修法：驼峰分支摘掉恒死 guard 即可，plain 分支保持与查询串形态逐字同构；「guard 防 https: 误抹」的旧注释在当前键名表下已被证伪（无键名可匹配 `https:`，`_PUBLIC_UNTOUCHED` 恒绿）。复盘：① 报告条目的「修复建议」列是建议不是事实源，落地前先枚举该正则的既有消费形态（带引号 header 正是被忽略的那个）；② 回归锁要补「修的方向」与「别把既有行为修没」两个方向（本次在 `_CAMEL_LEAK_CASES` 同时加了驼峰复合键与带引号 header 两类）。
- **CRLF 仓里做变异验证/字节级改写，锚点必须 CRLF 感知，且 Bash heredoc 不可靠**：`src/utils.py` 是纯 CRLF 文件，用 `\n` 拼的锚点两次 `not found`；即便带引号定界符，Bash 工具层也会吃掉 heredoc 里的双反斜杠转义（脚本里写两个反斜杠+n，到达 Python 时已折成一个）。可靠做法：把变异脚本经 Write 工具写成 `%TEMP%` 下的临时 .py（内容原样落盘），`chr(92)` 构造反斜杠、`"\r\n".join(lines)` 拼块，跑完删脚本并在 finally 里断言 `read_bytes()` 与原字节相等。

## 2026-10-01 — GUI 单飞回归锁的 Linux CI 假红（POSIX 分支替身缺失）

- **平台分流链路的测试打桩点必须覆盖全部分支，且本地可低成本复现对侧分支**：`gui._send_stop_signal_and_wait`
  平台分流（win32 `_send_ctrl_break_to_child` / POSIX `os.kill`），替身只桩本机分支时 Linux CI 上记账恒空、
  停止链因失去模拟耗时而瞬时完成（并发窗口连带消失），「恰一次附着」与「复用在途线程」两组判据同时落空。
  Windows 本机复现 POSIX 路径的技巧：子进程里 **`import gui` 之后**再改 `sys.platform = "linux"`——导入前改会让
  loguru 的 `enqueue=True` 按 posix 初始化 multiprocessing、撞 `No module named '_posixsubprocess'`（平台分支在
  方法调用期求值，导入后再改即可生效）。 | `tests/test_gui_stop_exit_singleflight.py`

## 2026-10-02 — 把 AGENTS.md 的 prose 约束落成项目级 Hook / Command

- **新写 Hook / 规则类文件时，注释里不得出现它自己检测的标记字面量**：`tests/test_test_hygiene.py` 的 R8 是全仓扫描（含注释），本会话在 `scripts/agent_hook_guard.py` 的模块头注释里写了变异标记的原文，门禁当场判红——检测器把自己的说明当成待还原的变异改动。口径与 R8 自身的自指规避一致：需要提及标记形态时用拼接常量（`"MUTA" + "TION-"`）或纯中文描述，别写完整字面量。 | `scripts/agent_hook_guard.py`
- **「资产已配置」与「Hook 已执行」是两级证据，必须分开写**：`.qoder/settings.json` 的 `hooks` 注册能被 provider 侧确认（`asset-integrity` 报 `hooks.enabledHookCount` 由 0 变 2、`inventory` 列出 command 与 scriptPath），但同会话内一条无害探针（`python -c "print('probe: Remove-Item ... ./downloads/')"`）未被拦，说明当前 IDE 会话尚未热加载该配置。报告里只能声明「已配置 + 行为由脚本级用例自证」，不得声明「已在会话中生效」；执行证据要么由重载后的探针给出，要么写成交回用户的动作。
- **本地跑覆盖率门禁不必污染已跟踪的 `coverage.json`**：`check_coverage.py` 的新鲜度判据是数据文件 mtime vs `src/`+`tests/` 最新 mtime（陈旧一律 rc=2），故把 `COVERAGE_FILE` 指到 `%TEMP%` 跑 `pytest --cov=src`（不带 `--cov-report=json`），再直接跑 `check_coverage.py`（它自己用 NamedTemporaryFile 生成 JSON）即可评完 44 个模块阈值，同时仓库内数据文件与文档读数不被本轮环境噪声改写。

## 2026-10-02 — 启动期字节码缓存清理：越界防护用例的真假绿与 heredoc 锚点

- **「越界防护」用例必须让越界目录里也放一份「被保护规则一旦失效就会被命中」的输入**：首版 `tests/test_startup_cleanup.py` 在 `downloads/`、`tests/`、`scripts/` 等越界位置只造了缓存目录本体，而扫描根的判据是「目录直接含 `.py`」——于是把实现改成「从程序目录起全树递归」后用例**仍然全绿**（这些目录里没有 `.py`，递归也删不到它们）。变异验证一跑即暴露：改动落地后整文件 9 条用例 rc=0、零失败。补成两类分轴才真正锁住：①类「含 `.py` 但不在白名单根」（真实对应 `tests/`、`scripts/`，本机实测 `tests/__pycache__` 有 128 个 `.pyc`）只由「正向白名单」这条规则救；②类「在白名单树内但不含 `.py`」（真实对应 `src/javascript/`）只由「须含 `.py`」救。写清理/扫描类用例时先问一句：把实现退化成「无差别全树删」，我的用例会不会红？不会红就是假绿。 | `tests/test_startup_cleanup.py`
- **Bash heredoc 里的 Python 锚点与文本一律不得含反斜杠转义序列**：用 `python - <<'PY'` 内联做「读源码→字符串替换→跑测试→还原」时，锚点里若写了反斜杠接 n 的转义（本意是匹配源文件中同样字面写的换行转义），转义层会先把它解成真换行，导致 `text.count(anchor)` 恒 0 → 替换静默不发生 → 测试照常绿，看起来像「变异没被抓到」；同一机制还会把真换行写进 Markdown 文档，造成 CRLF 文件里混进裸 LF（本会话两次中招）。三条对策：① 变异/补丁脚本先 `assert count == 1` 再写盘（本仓按此形态跑，第二条锚点就是被这条断言当场拦下的）；② 优先选**不含任何转义**的整行作锚点；③ 需要构造含转义语义的文本时用 `chr(10)` 或字符串拼接，别把反斜杠序列写在 heredoc 里。
- **「每次启动都删」这类性能论断必须先实测**：本机读数——源码树 sha256 全树（51 文件 / 2,268,108 B）8.8 ms，同集合全量重编译 345 ms，现存运行期缓存 4 个目录 / 1,758,820 B（`.venv` 除外）。结论直接决定设计：内容哈希便宜到每轮都算，因此用「版本 + 哈希」哨兵把删除压成「源码真的变过才删一次」，而不是每轮付重编译。体积/耗时类论断写进设计前一律本机实跑取数，不估算。
- **subprocess 类用例的红要先测「是不是导入顺序问题」再归因**：本机六个驱动子进程的文件（`tests/test_ci_retry_action.py`/`test_build_exe.py`/`test_notify.py`/`test_notify_script_guard.py`/`test_stop_recording_vbs.py`/`test_regression_standalone.py`）单独跑固定红 20 条，但把**任意**一个先导入过 `src` 侧模块的测试文件排在前面就 0 红——用与本批无关的 `tests/test_config_bool.py`（261 passed）作对照与用本批新文件（208 passed）作对照，结果同形。所以「全量运行失败数在 3↔24 间摆动」不是代码回归，而是这些用例对模块导入次序的隐式依赖（子进程继承已关闭 stdin，`WinError 6` 在失败输出里出现 23 次）。判据：怀疑自己引入回归前，先跑一次「换一个无关文件作前置」的对照，再谈归因。 | `tests/test_ci_retry_action.py`

## 2026-10-02 — 整改批收尾：审查建议本身可能是错的，以及「补日志/过码/移动状态位」三类改动的隐性破坏面

- **落地外部审查的修法建议前，先给它构造一格反例**：`CODE_REVIEW_2026-10-02` M-05 的建议是「`int(cast(str, is_private))` 改按真值判定」。照抄后 `bool("0")` 是 True，API 以字符串 `"0"` 下发时**公开房间被误判私有**、整轮报错——即修复把「恒判未开播」换成了「恒报错」，而实现者还在注释里写「对 "0"/0/False 均语义正确」。判据：凡「换一种判定写法」类建议，先列出该字段的**全部现实下发形态**（JSON 数字 / 布尔 / 字符串 / null）做成矩阵用例，再决定写法；本仓已有 `src/config_bool.parse_config_bool` 这一份统一 token 口径，外部 API 的字符串布尔字段同样该复用它，而不是新写一套真值判断。 | `src/spider.py`
- **「补一条日志」与「补一次过码」这两类看似零风险的改动，各自有一类只有静态检查能发现的崩法**：L-10 把裸 `except Exception:` 后面加了引用 `type(e)`/`{e}` 的 debug 日志却没绑 `as e` → 走到即 `NameError`；M-02 把 `mask_credentials(...)` 包到 print 实参上，但实参是 `tuple[str, str, str]` 而该函数内部全是 `re.sub` → `TypeError` 穿透主循环。两条都由 **mypy 一遍抓红**、却对 black / isort / 注释检查 / 用例断言（只要那条分支没人跑）四面隐形。推论：整改批的收尾**必须跑完整 `run_gates.py`**，不能在任何一条（尤其第一条 black）失败后就宣布「门禁大致过」——本批接手时上一轮正停在这里，后面 9 条从未执行，这两个崩点因此带病入库。 | `src/spider.py` / `main.py`
- **移动一个「链是否续期」的状态位，可能同时满足一把锁、打穿另一把锁**：L-39 把 `gui._log_queue_has_data = False` 从「渲染成功后」上移到「取空队列即清」，正确修掉了哨兵单独取空时的永久空转；但 M-15 的锁 `test_log_flush_chain_rearms_when_render_raises` 依赖的正是「渲染中途抛错 ⇒ has_data 仍为 True ⇒ finally 照常续期」，上移即打穿（jobs 变空 + `still_has_data` 变假）。两条约束可以共存：清除留在原地，由**持有续期决策的那一站**（`_schedule_log_flush` 的 except 分支）在异常路径上复位。判据：改自续期链附近的共享状态位之前，先跑 `tests/test_gui_tail_robustness.py`；改完再跑一次，别只看目标用例变绿。 | `gui.py`
- **写死条数的 AST 锁在合法删除后必须改成反向见证，而不是把数字改小**：`assert len(runs) == 4` 的本意是「扫描面非空、别假绿」，L-40 删掉两段不可达兜底后实际只剩 2，改数字会让这把锁继续跟着每次合法增删漂移且不表达任何判据。正确形态：`assert runs`（0 处即红，保住反假绿的那一半）+ 对 `ast.walk` 自动纳入的每一个调用点逐条断言（新增的第 N+1 处照样被检查）。 | `tests/test_regression_gui.py`
- **子进程用例的红要按「文件内 / 文件间」两层分别测，别把两种形态混成一句「环境噪声」**：本会话对上一轮记录的补正——那六个（本批实测八个）驱动子进程的文件**逐文件独跑全绿**（build_exe 105 / ci_retry_action 12 / notify 4 / notify_script_guard 18 / stop_recording_vbs 11 / regression_standalone 49 / run_gates 42+1 skipped / regression_gates 27 = 276 passed）；把其中几个**放在同一条命令里**且前面没有任何「先导入过 `src` 侧」的用例时才红，堆栈一律停在 `subprocess._make_inheritable`（`WinError 6` / `WinError 50`），无一条是断言失败。另实测：给 shell 重定向 stdin（`< /dev/null` 或 `< 某文件`）**不能**消除，说明不是「句柄不可继承」这一种成因。判据顺序：先单文件独跑定是不是代码，再看换前置文件后是否转绿，最后才归因环境。 | `tests/test_run_gates.py`
- **子进程用例的红还存在第三层：同一命令秒级间隔内绿↔红自翻转（2026-10-03 补充）**：`tests/test_stop_recording_vbs.py` 单文件独跑连续两次（同一代码状态、零编辑间隔），11 passed → 4 failed；另一轮 `test_stop_recording_vbs.py + test_regression_standalone.py` 两文件合跑先 6 failed、数分钟后 3 failed，失败集合每次不同；同日 run_gates 内置全量 pytest 对同一代码 3977 passed / 0 警告。即「逐文件独跑全绿」并非恒稳判据，失败集合是随机抽样的，`WinError 6` 抖动可以独立于导入序发生。判据补充：连续两次同命令结果不一致 + 失败集合漂移 + 堆栈停在 `_make_inheritable`，三条齐了即可直接归因环境，不必再找代码侧原因。 | `tests/test_stop_recording_vbs.py`
- **覆盖率门禁的「数据陈旧」rc=2 会被同字节重写触发**：`check_coverage.py` 比的是 `.coverage` mtime 与 `src/` 最新 mtime；收尾时发现 `src/ffmpeg_linux_download.py` 与 `tests/test_ffmpeg_linux_download.py` 被**内容零差异**地重写（`git diff` 对 HEAD 与索引均空、行尾形态不变），仅 mtime 变新即足以让门禁拒评。遇到这条红先看 `git diff` 有没有实际内容变化，再决定是重跑采集还是查改动来源。 | `scripts/check_coverage.py`
- **`cat >>` 追加是纯 CRLF 文件里孤立 LF 的一个静默来源**：本会话给两份测试文件 heredoc 追加用例后实测 44 / 18 条 lone LF（两文件原本纯 CRLF），`ast.dump` 等价校验与 `black --check` 对此完全隐形（AGENTS「三个盲点」第 3 条已记整文件重写这一形态，追加是同一判据的第二条路径）。对策：向 CRLF 文件追加后立刻 `re.sub(rb'(?<!\r)\n', b'\r\n', b)` 归一并复测 lone-LF=0；或直接用 Edit 工具（它按文件既有形态落笔）。 | `tests/test_spider_platforms.py`

## 2026-10-03 — 虎牙 hy.fan 短链接入：同树并行会话、直喂短链的真机脚本边界与熔断桶口径

- **同树并行会话是本仓的现实工作形态，编辑前必须重 Read**：同一天里斗鱼（m.douyu.com）、虎牙（hy.fan，本批）、B站（b23.tv）三个同构工作包在同一工作区并行落地，后启动的会话把先落地者的代码当模板并在注释里逐字引用（b23.tv 注释写「与 `_hy_fan_path_segment` 同口径」），还会替你同步被你插入扰动的锁（`test_resolver_table_priority_head` 由斗鱼批次按含我方表项的实际顺序同步为前六项）；`.mo` 条目数在会话中途 856→858→860 递增。判据与对策：Edit 报「多 matches」时先用多行锚点消歧；三个短链 resolver 的归一化行**逐字相同**，变异验证必须带上下文多行替换并 `assert count == 1`；全量 pytest 一次红（459.7s）复跑全绿，先疑并行批次的编辑中间态再归因自己。 | `main.py`
- **「直喂短链给平台函数」的真机脚本红是脚本边界，不是功能回归**：`tests/test_huya_live_collector.py` 把 URL 直接传给 `spider.get_huya_app_stream_url`，绕过 main.py 解析层——短码形态在 ProfileRoom 反查处失败（app UA 下 301 落地页正则未命中）→ 脚本报 FAIL/SKIP。生产链路中 resolver 先行归一、spider 只收数字房间链接，该路径不可达。判据：真机脚本红先画调用链，看失败点在「本批改动面」还是「被本批归一化绕开的既有路径」；是后者就归档为已知边界（写进 CODE_WIKI），不为让脚本变绿去改生产函数。 | `tests/test_huya_live_collector.py` / `src/spider.py`
- **短链房间的 `record_host` 保留短链域是特性不是遗漏**：按 host 隔离的熔断桶把「短链解析失败」与桌面链接的取流失败分开计数，桶隔离语义比回填成桌面域更准。同日三个短链工作包（hy.fan / b23.tv，m.douyu.com 走同表项不经此路径）都按此口径；后续新增短链域照抄，不要「顺手统一」record_host。 | `main.py`

## 2026-10-03 — Linux arm64 ffmpeg 支持批次取到的四条可复用判据

1. **`[tool.mypy].exclude` 的裸名字是路径子串正则，不是目录名**：`"ffmpeg"` 会把 `src/ffmpeg_*.py`、
   `tests/test_ffmpeg_*.py` 一并吞出无参 `mypy` 的扫描面（实测加不加这两个文件都是同一个 source files 计数）。
   black/isort/basedpyright 的同名排除只作用于**目录**，所以「同一份清单四个工具」里只有 mypy 会静默失明。
   新增名字含被排除词的模块时，必须显式传参补跑一次 `python -m mypy <那些文件>` 才能宣称类型门禁过。
   （2026-10-03 已锚定修复、该代偿退役、语义锁进 `tests/test_run_gates.py`——见下节。）
2. **`docker buildx` 推 GHCR 时 `provenance: false` 是承重取值**：buildx 默认给 push 产物附加 SLSA provenance
   attestation，于是该步 push 出去的是「镜像 + attestation」的 **index**，`steps.*.outputs.digest` 退化成 index digest，
   下游 `imagetools create` 按它合成的对外清单会混入非镜像条目，而整条流水线全绿、只在用户 `docker pull` 时暴露。
3. **`build-push-action` 的 digest 必须显式提升为 job 级 `outputs:`**：merge job 用 `needs.<job>.outputs.digest`
   取值，漏声明时拿到的是空串 → 合成步骤报无效引用，而两个构建 job 本身全绿（最难归因的一种红）。
4. **Actions YAML 里以 `!` 开头的 `if:` 标量必须加引号**（`if: "!startsWith(...)"`）：无引号时 YAML 把行首 `!`
   当 tag 指令，解析直接 `ParserError`；GitHub Actions 求值的是引号内那个字符串，语义不变。

## 2026-10-03 — mypy exclude 锚定收尾（R-8 工作包）：失明复发不会被门禁自己发现

- **修干净之后的失明会「静默复发」——回归锁必须锁语义而不是锁读数**：exclude 从裸名改成锚定后，那 12 个
  文件本来就是干净的，谁改回裸名 `mypy` 照样全绿（只是少查 12 个文件）。所以锁不能断言 source files 计数
  或钉具体写法，得断言不变量本身：`[tool.mypy].files` 扫描面内任何 `.py`/`.pyi` 路径都不得被任何 exclude
  模式子串命中（`tests/test_run_gates.py::test_mypy_exclude_never_shadows_source_files`），并带三重反假绿
  见证（清单非空 / 扫描面 ≥200 / 两个曾经的失明家族必须在枚举集内）。变异验证直接改 pyproject 落盘，
  驱动脚本写 `%TEMP%`、跑完按字节还原。
- **「本地绿 ⇒ CI 绿」的版本外推前提，可以不碰项目 venv 就实测闭合**：本地 venv mypy 已 2.4.0、CI 钉 2.3.1
  （该差距已于同日经用户批准抬 consts 闭合），
  而新纳入扫描面的 12 个文件从未被 2.3.1 查过。做法：`pip install --target <%TEMP%目录> mypy==2.3.1`
  （不装进项目 venv、不卸载任何东西），再 `PYTHONPATH=<临时目录> python -m mypy` 让临时副本优先于
  site-packages，同一命令跑两遍比对。编译 wheel 在 cp314 有现成包，秒级完成；用完删目录。
  凡本地/CI 工具版本不一致又改了「工具可见面」（门禁配置、exclude、文件集），都值得做这一步而不是只写差异声明。
- **mypy 两个「测试替身形态」检查项记住即可少一轮修复**：① 恒回 False 的 `__exit__` 标 `-> bool` 报
  `[exit-return]`（改 `-> None`，falsy 语义不变）；② `LIST.append(x) or False` / `(calls.append(url), resp)[1]`
  这类「lambda 里消费 append 返回值」报 `[func-returns-value]`（改嵌套 def，`*args: Any, **kwargs: Any`
  按转发桩口径注解）。mypy 2.3.1 与 2.4.0 行为一致，均为默认开启、非 strict 专属。

## 2026-10-03 — UI 阶段4（CTk→ttk）：三个只有真窗才暴露的 Tk 9.0 形态

- **ttk 的 wraplength 是原始设备像素，不随 `tk scaling` 缩放**：探针把 `tk scaling` ×2 后同 wraplength 的
  标签 reqwidth 恒定。推论：从 CTkLabel 换 ttk.Label 时，CTk 时代「configure 值×控件缩放率」的换算必须
  同步去掉——两边各错一半时在 100% DPI 开发机上读数恰好相同，高 DPI 用户才炸。判据：跨 DPI 换算公式
  改动必须先探针裁定「哪个层的像素」，不能两边各自保留换算。 | `gui.py` `_compute_wraplength`
- **ttk.Button 没有控件级 `-font`**（TclError: unknown option "-font"；ttk.Label/Combobox 有）：
  带字体的按钮要走样式级字体。注意多段样式名（`X.Variant.TButton`）的 **configure/map 跨段回退不可靠**
  （布局可回落、选项未必）——派生样式必须显式复制基础变体的 configure 字典与 map，别赌回退语义。 | `src/ui_kit.py`
- **CTk 控件的 `configure` 重载只收命名参数，位置 cnf 字典被静默忽略**：`label.configure({"wraplength": x})`
  不报错、不生效——CTkBaseClass.configure(**kwargs) 接到位置字典直接吞掉。静默无操作比抛错危险得多，
  本次由真窗回归锁（wraplength 恒 0 断言）抓出、无头跑不到。判据：给 CTk/原生控件双形态调用的
  helper 换 configure 传参形态时，真窗锁必须重跑。 | `gui.py` `_bind_adaptive_wraplength`
- **真窗用例在子进程里失败会以 `skipped` 面目出现**：`except tk.TclError → pytest.skip` 的既有口径把
  「unknown option "-font"」「missing '>' in virtual binding」这类**真 bug** 一并吞成「无显示环境」。
  判据：本机有显示器时真窗用例 skip 即异常信号，必须 `pytest -rs` 看跳过原因，不能当成已知 skip 面放行。 | `tests/test_gui_wrap_hints.py`

## 2026-10-04 — 抬 CI 工具版本常量：三处「看起来该跟改、其实不该改」与一处注释还原陷阱

- **`uv.lock` 里 dev-extra 的版本与 `ci.yml` 的版本常量无耦合**：抬 `isort_version` 9.0.1→9.0.2 不需要重算锁——
  CI 装 isort 走 `pip install "isort==<const>"`，**不走** `uv sync`；锁里的 9.0.1 只是 `[project.optional-dependencies]`
  的 `isort>=5.12.0` 在上次锁定时的解析产物。判据：只有改 `pyproject.toml` 的依赖/version/包清单才触发
  `sync_metadata.py` 重算，改 workflow 常量不触发。 | `.github/workflows/ci.yml` consts
- **抬常量只消除版本差，不等于 CI 实跑已验证**：改完四项常量与本地 `.venv` 逐一同值，可报告的仍是
  「本机（Windows/GBK）口径」——本机跑法与 CI（ubuntu + step 级 `PYTHONUTF8=1`）的环境差异没有因此消失。
  AGENTS.md 那条约束的措辞因此补了一句「抬常量只消除版本差」。判据：报告里「同值」与「已在 CI 上验证」
  必须是两句话，不得合并成「与 CI 一致故 CI 会绿」。 | `AGENTS.md`「格式化命令」可外推前提条目
- **版本同值核查要拿 `importlib.metadata.version()` 而不是 `--version`**：`python -m isort --version` 在本机
  输出空行（只有 `--version-number` 给数），据它判「工具缺失」会误装。判据：逐个 `importlib.metadata.version(<pkg>)`
  取实装版本，与 ci.yml consts 的四个键做集合比对。 | `scripts/run_gates.py` 的子进程调用面
- **改长注释块时最容易顺手改到既有句子的措辞**（本次把「按真实类型检查」写成「按真实类型结论」）：
  违反「修改注释只增不改」且 black/mypy/pytest 三面全隐形。判据：只增注释的改动收尾前 `git diff` 逐行看
  **减号行**，出现非预期的 `-` 即还原。 | `.github/workflows/ci.yml`

- **i18n 目录「孤儿条目 / 源文已变更」判定必须走 AST，不能靠 grep，也不能靠 read_text**（2026-10-17 实测两处）：
  ① 侧栏导航同一标签在 Qt 实现里是 `📊  控制台`（两空格）、在 Tk 遗留实现里是 `📊   控制台`（三空格），两者都是运行时按键；
     用 `grep "📊   控制台"` 扫 `gui.py` 恒无命中（非 ASCII + 连续多空格在 Git Bash 的 grep 下静默失配），据此把三空格形态「改名」
     会当场把 Tk 侧栏译文弄坏——判据：`ast.walk` 比对 `Constant.value` 全集（含 tests/ 与 .workbuddy 备份副本），两种形态各自定位到调用点后再决定并存还是改名。
  ② 目录四文件全是纯 CRLF，而 `Path.read_text()` 走 universal newlines，`write_bytes(text.encode())` 会**静默整文件转成 LF**；
     改目录一律 `read_bytes().decode('utf-8')` → 只替换不含行尾的行内容 → `write_bytes`，并在前后各测一次 `(CRLF, bareLF)` 双侧必须相同（AGENTS.md 注释盲点③同源）。
  ③ 登记条目前先问「这条串有没有查询路径」：被 `set_text(T(...))` 覆盖的构造器字面量、经 `HTTPException(422, str(e))` 原样出面板的 raise 文案，
     登记进去就是死条目——要么先在产生点接 `tr()`，要么明确记为代码侧待办，不用目录数量冒充覆盖率。
  | `i18n/zh_CN/LC_MESSAGES/zh_CN.po` / `src/gui_qt/main_window.py` / `gui.py`

- **给「按名传入」的文案接线写机检锁时，两条相邻判据必须能被变异互相隔离**（2026-10-17，`tests/test_i18n_catalog_coverage.py`）：
  「四目录键集合相等」与「按名 msgid ⊆ 每份目录」看似重复，实则互补——源码 msgid 漂移成一种四侧都没有的形态时，键集合依然逐项相等
  （⑤-C 绿），只有「候选 ⊆ 每份目录」那条（⑤-A）会红。所以变异要专门造这一格：M3 改源码不动目录 → 期望 A 红 + C 绿；
  再各造「单侧缺键」的 M1/M2 → 期望两条都红。只跑一次全绿不能证明任何一条锁在工作。
  另两条实测教训：① 解析「名字→候选 msgid」时 `for a, b in (("dashboard", "📊  控制台"), ...)` 必须**按位置**取元组元素，
  整体收集会把 `dashboard` 当文案（假红）；小写名不得跨文件合并，UPPER_CASE 标签表才需要跨文件
  （`THEME_LABELS` 定义在 `theme.py`、取用在 `main_window.py`）。② 不可解析的调用点用**白名单集合相等**而非计数上限：
  上限只拦「变多」，白名单同时拦「变少没收回」，行号漂移也会当场红。
  ③ 在按函数遍历的判据里，不要在函数循环内再 `ast.walk(tree)` 一遍——74 个运行期文件下实测 35s/次，调用点预收一次即降到 6s。
  | `tests/test_i18n_catalog_coverage.py` / `scripts/extract_i18n_strings.py` / `src/gui_qt/main_window.py`
- **本机没有 Docker 时，容器相关改动用什么替代「跑一遍镜像」**（2026-10-17，Dockerfile 的 GUI 依赖开关）：
  本轮新增 ARG INSTALL_GUI=false（阶段1 按行首包名剔除 PySide6、阶段2 条件装 Qt 运行库）。没有守护进程就不能声称「镜像能跑」，
  但可以把结论拆成四件本机可执行的事：① 折叠续行后对每条 RUN 载荷跑 sh -n 与 bash -n（Docker 默认用 /bin/sh，只测 bash 会漏 POSIX 差异）；
  ② 把 pip 换成 echo 替身逐分支跑 if/else，看它到底装的是哪份清单（顺带暴露「只认精确 true、TRUE 会走 slim」的大小写敏感语义）；
  ③ 用同一条 grep 表达式对真实 requirements.txt 跑一遍，断言 21→20、仅剔目标包、零误伤，且残留行必须是注释；
  ④ 用元路径拦截器屏蔽该依赖后 import 真实入口（main / web），证明默认 slim 不 break 容器服务。
  配套结论：compose 里 build 配置不同的服务必须用不同 image tag，否则后构建的一方覆盖另一方正在使用的 tag（已写成回归锁）。
  另记一次自伤：把带反引号的中文段落塞进 shell -c 里追加，反引号会被当命令替换执行、静默吃掉行内码（实测 bash 报 ARG: command not found 而文件仍写入成功）。落盘长文本一律用文件写入工具，别走 shell 引号。
  | Dockerfile / docker-compose.yaml / tests/test_dockerfile_image_gui_arg.py
- **门禁的「文件数」有两个互不相等的口径，且在仓库内建一次性目录会同时污染两者**（2026-10-17，抬 black 版本常量前的对照实测）：
  无参 `mypy` 报 `no issues found in 241 source files`，`black --check` 报 `242 files would be left unchanged`——一个是 Python 模块数、
  一个是被扫描文件数，文档里混用必被后来者当假读数。更要紧的是：为绕开「不动 venv」而把 wheel 解包目录建在**仓库根**时，
  black 26.5.1 当场报 `28 files would be reformatted`，28 个全是我自己解出来的 vendored 源码，与仓库真实形态无关；
  改到 `%TEMP%` 后新旧两版各跑全量，同为 242 unchanged，抬常量才只消除版本差、不改变判定。
  判据：任何「扫全仓」型门禁跑之前先看 `git status --short` 有没有未跟踪目录；产物名与计数一律本机复测后再写进文档。
  | scripts/run_gates.py / .pre-commit-config.yaml / .github/workflows/ci.yml
- **测试夹具名里的 `:` 在 Windows 上是「能 stat、不能 copy」的坑**（2026-10-17，唯一一条本机红 / Linux CI 绿）：
  `font:with|weird*chars?.ttf` 被解析成名为 `font` 的**备用数据流（ADS）**——实测 `iterdir()` 只列出 `font`，
  `exists()` 与 `is_file()` 都为真（流本身可 stat），但 `shutil.copy2` 抛 `FileNotFoundError [WinError 3]`；
  生产侧 `except Exception → return None` 再把它压成「没有异常、只有失败」，于是断言面只剩一句「返回 None」。
  修法不是加 skip，而是**把一个用例的两件事拆开**：字符清洗判定下沉为纯函数用例（不碰文件系统，两端语义一致），
  文件系统那半边改用两端都能创建但仍需清洗的名字（`"  my font  (v2) ..ttf"`）。生产代码零改动。
  另记：改这类用例必须当轮变异验证——把 `_safe_filename` 改成恒等函数应让三条用例同时转红（实测 3 failed），按字节还原。
  | tests/test_ui_fonts.py / src/ui_fonts.py
- **「Pylance 不能作为门禁证据」的正解是给它一份可复现的扫描面，而不是去驱动 Pylance 本体**（2026-10-17）：
  本机确实装着 `ms-python.vscode-pylance-2026.4.101` 且 `dist/server.bundle.js` 能被 node 拉起来，但其 LICENSE 明文只授权
  「在 Visual Studio 系产品内使用」——所以**不写** shell 驱动它的工具，这条禁令已钉进 AGENTS.md。真正治根因的是：
  本仓原先既无 `[tool.pyright]` 也无 `pyrightconfig.json`，裸跑 pyright 走自带默认范围，IDE 红线与 CLI 结论根本不同源。
  现新增 `pyrightconfig.json`（include 逐项等于 `[tool.mypy].files`、exclude 覆盖 mypy 与 basedpyright 两份清单、
  严格度/版本/venv 同 `[tool.basedpyright]`），不带路径跑 `pyright` 即复现 IDE 扫描面（实测 0 errors / 0 warnings / 0 informations）。
  两条实测细节：① pyright **只接受已知顶层键**，把说明写成 `"//"` 键会报 `Config contains unrecognized setting`，解释文字只能走 JSONC 行注释；
  ② `"$schema"` 同样不被识别（每次跑吐一行噪声），已挪进注释。basedpyright 那边无此限制，别把两侧容错度当同一条。
  同源关系由 `tests/test_pyright_config_parity.py`（5 用例）机检，五处变异各自转红后按字节还原。
  | pyrightconfig.json / tests/test_pyright_config_parity.py
- **抬版本常量（CI 钉定 / pre-commit rev）的三步自证**（2026-10-17，black 26.5.1→26.10.1、pre-commit isort 6.1.0→9.0.2）：
  ① 新旧两版各跑一次全量 `--check`，证明「判定不变、只是值对齐」；② rev 存在性走 GitHub API `repos/<org>/<repo>/tags/...` 逐个核实，
  不凭记忆填 SHA 或 tag；③ `pre-commit validate-config` 只证明 YAML 合法，**不等于**钩子能装起来——本机 clone 被代理拦时，
  「钩子实际运行过」必须如实写「未验证」，不得用 validate-config 的绿替代。
  | .github/workflows/ci.yml / .pre-commit-config.yaml / tests/test_pre_commit_config.py
- **异常消息「登记进目录」之前，必须先确认它是被查表还是被插值**（2026-10-17，C 项 21 站点逐条顺消费链实测）：本仓大量日志写法是 `logger.error(i18n.tr("…: {record_url} - {reason}", reason=str(err)))`，模板查了表、**消息本身从没查**；此时只把原文登记进四目录 = 造死条目，唯一有目录意义的修法是在 **产生点** 包 `raise ValueError(i18n.tr(…))`。反过来的陷阱也存在：`XhsUrlError` 一类「消息 + 稳定 code」双通道异常，消费点（`src/spider.py` 两处 except 与 `main._resolve_xhslink_com`）**一律只读 `e.code`**，message 从不显示——这类站点接 tr() 也无人看，应当进白名单并写明「谁消费它、为什么不需要译」。判据一律用 AST 顺 raise→except→日志/返回值三级，别靠 grep 猜（非 ASCII + 空格形态会静默漏配）。
  | main.py `_hy_fan_path_segment` / `src/web_models.py::_as_*` / `src/spider.py::parse_xhs_live_url` / `tests/test_i18n_raise_site_tr.py`
- **「两套文本必须同源」的故障只能用静态结构锁看见**（2026-10-17，9 处 Qt 按钮图标消失）：`action_button("📥  X")` 与 `set_text(btn, T("X"))` 单看任一行都成立，但 `set_text` 建时即回填 + 登记重译，构造期文本会在启动回填和每次 `retranslate_all()` 被打回登记键的形态。修法不是改回填顺序，而是**让两处指向同一个 msgid**，且优先取目录里已存在的键（本轮复用 Tk 遗留的三空格形态 → 四目录零新增）。锁的形态：AST 收集「构造字面量」与「登记键」两张表按属性名配对判等，另配 emoji 下限 + 键必须四目录齐全两条判据；行为侧证据走 `QT_QPA_PLATFORM=offscreen` 真建页面读 `text()`，比断言源码字符串更硬。副作用要预先说明：孤儿裸文本键不会判红，改完必须 AST 复核哪些键就此失去调用点，再决定是否收回目录。
  | `src/gui_qt/pages/dashboard.py` / `src/ui_i18n.py::set_text` / `tests/test_gui_qt_label_parity.py`
- **全量 pytest 的用例数会因「按目录参数化的检查」而增长，别把这种增量当成新断言**（2026-10-17）：向 `tests/` 放两个新测试文件，总数从 4331 涨到 4343；其中 +4 是新用例，**+8 来自 `tests/test_test_hygiene.py` 的 4 条 `@pytest.mark.parametrize("path", _test_files())` 检查**各多访问一个文件。归因手法：`pytest --collect-only -q` 加/不加 `--ignore=<新文件>` 各测一次总数，差额即参数化面而非断言面。
  | `tests/test_test_hygiene.py` / `tests/test_i18n_raise_site_tr.py`
- **构建 `MainWindow` 的探针脚本不能用普通 `sys.exit` 收尾**（2026-10-17 实测挂满 240s 超时）：窗口构造会起非守护线程/定时器，解释器退出时 join 永不归零的线程 → 整脚本挂死，而控件文本其实早已拿到。探针一律先 `flush()` 再 `os._exit(0)`；另记两条同源坑：`MainWindow.__init__` 自带语言探测，探针里 `set_language()` 之后仍可能被持久化配置改判（读标签前必须钉语言并 `retranslate_all()`）；以及 `import main` 的脚本在解释器退出时会触发既有的 ffmpeg 进程清理 atexit（探针环境须确认无在录任务）。
  | `src/gui_qt/main_window.py::_build_pages` / `tests/test_gui_qt_window.py`（offscreen 夹具即此先例）
- **动手前先把「常识性故障」在本机测一遍**（2026-10-17，`CON.ttf` 保留设备名清洗）：按 MSDN 常识我直接给注释写成「copy2 到 `CON.ttf` 会抛 OSError / 写出打不开的文件」，实测却是 `shutil.copy2` **不抛错**、`iterdir()` 列得出 `CON.ttf`、`getsize`=8（`cmd` 重定向同样成功），只有 `\\?\` 扩展前缀那条路反而 `OSError [Errno 22]`。结论不是「这条不用做」，而是**理由必须换**：同一名字在不同 API 路径与不同 Windows 构建下语义不一致，而清洗后的名字会持久化进 `gui_font_file` 跨机器读回 → 保留清洗、把注释与用例说明改写成「可移植性防御 + 本机实测」。判据固化成用例的三形边界：整段基名命中才改（`CON.ttf`→`_CON.ttf`）、`COM10`/`LPT10` 不改、`console`/`NULx`/`myCON` 不改；并配一条「把判定放宽成子串匹配即红」的变异，证明边界断言不是摆设。
  | src/ui_fonts.py `_WIN_RESERVED_NAMES` / tests/test_ui_fonts.py::test_safe_filename_prefixes_windows_reserved_device_names
- **`return None` 型收敛必须配一行带类型名的日志，而且日志模板本身是新 msgid**（2026-10-17）：调用方拿 `None` 只能弹分类级提示，现场归因权全在子进程/异常那侧。写法照「异常日志必须带异常类型与上下文」：`i18n.tr(模板, type_name=type(e).__name__, err=e, …)`，`{type_name}` 不可省（Windows 上部分异常 `str()` 是空串，只打 `{err}` 就是空白行）。连带义务有两条：模板要**同批登记进四目录并重编 `.mo`**，否则 `test_runtime_templates_covered_by_catalog` 当场红；测试侧捕获用 `logger.add(level="WARNING")` + `finally: logger.remove(id)`，打桩 `shutil` 一律走被测模块命名空间的 shim（裸赋值共享模块属性会波及同进程其它会话）。
  | src/ui_fonts.py::install_font_file / tests/test_ui_fonts.py::test_install_font_file_logs_copy_failure_with_reason
- **精简一份「事实源」文档前先把冗余度量出来，再区分「重复」与「长」**（2026-10-17，AGENTS.md 复核）：本轮实测 547 行 / 93 696 字符，尾部空白 0、连续空行 0、完全重复行只有 6 组且全是 ``` 与 > 这类结构符，>120 字符条目的两两相似度 >0.45 仅 3 对，其中 1 对还是 Black/isort 两个「取值」小标题的假阳性。真正能减的只有三种：① 同标题双条目（其实是标题复制粘贴，内容各自成立——只能分标题，不能合并正文）；②  checklist 条目把别处清单重述了一遍（改指针）；③ 一次性实测读数（外迁 + 留约束与指针）。剩下的长句全是「为什么」，压它等于删判据。结论要如实报体积方向：本轮根文件反而 +902 B，因为同时新增了两条长期约定。
  | AGENTS.md「可达性约定」/ docs/agent-reference/measured-evidence.md
- **文档里的 `file:line` 是定时炸弹，一轮复核实测三处全失效**（2026-10-17）：`main.py:3595`（真身 3952）、`Dockerfile:112` 的 `COPY . ./`（真身 149 且字面量已变成 `COPY --chown=recorder:recorder . ./`）、`src/ffmpeg_install.py:583`（真身 594）。判据：引用代码位置用**符号名或唯一语句片段**（锚点），要留证据就写「实测日期 + 取数命令」让人能复跑。同轮另一类假阳性来自计数口径混用——black 报「files would be left unchanged」（被扫文件数）、mypy 报「source files」（Python 模块数），两者随仓库形态各自变动，永不互等，写进文档时不得互相替代。
  | AGENTS.md 注释约定 / scripts/run_gates.py（解析门禁 bash 块的那个读者）
- **`RawConfigParser` 默认 `strict=True` 让「同节重复键」成为配置文件级损坏**（2026-10-17 实测）：补写路径写出两行同名键后，`read()` 直接 `DuplicateOptionError`，入口起不来；且这种损坏**不是确定性可复现**的（单跑一次读取+补写不改写文件，`config_parser.write()` 也只产出一份键），属于「两个持有不同快照的写者并发」。要点有二：① 判据要写成「对同一份文件连跑两轮读取+补写，断言该键出现次数仍为 1」，而不是只看单轮结果；② 工作区里出现了运行期写产物时，**索引可能已带着它**（本例 `git diff --cached` 仍显示那 1 行），还原工作区不等于还原暂存区，必须分开报告交回用户。
  | config/config.ini / src/config_io.py::read_config_value / AGENTS.md 配置键名节
- **收回「孤儿」翻译条目时，测试夹具也是调用点**（2026-10-17，四目录收回 6 条、留 1 条）：生产侧 AST 扫 `T()`/`tr()` 首参会漏掉一整类消费者——`开始录制` 在生产侧零调用点，却被 `tests/test_i18n.py` 的两条用例当样本 msgid 用来验证「`.mo` 优先于 JSON/YAML」与热切换，删它 = 打红两条机制用例。判据：删键前 AST 扫**全部字符串常量**（含 tests/ 与前端 js 的**值位**），把「只作值出现」与「被查表」区分开——`停止录制` 在 `web/app.js` 里是内嵌目录的值，与后端键无关，可删；被查表的一律留下并写明谁在用。
  | i18n/zh_CN/LC_MESSAGES/zh_CN.po / tests/test_i18n.py / AGENTS.md 关键约定 #14
- **四份目录不是同一种文本，删条目要按各自语法收口**（2026-10-17 实测三处坑）：① `.po` 是 `msgid`+`msgstr`+其后空行 的块；② JSON 删行后必须**只在条目区内**做逗号归一（末条目不带逗号、其余都带），否则删掉末条目会让前一行缺逗号而 `json.loads` 直接非法——先 `loads` 验证再落盘，并断言「键集合 == 原集合 − 待删集合」；③ `zh_TW.yaml` 的键**单双引号混用**（正文 `'键': '值'`、尾部 `"键": "值"`），只按一种引号匹配会静默少删（实测断言抓到 2≠6 才没留下半截状态）。收尾口径统一用 `.mo` 头部 N == 键数 + 1 与「四目录键集合逐项相等」两条复验。
  | i18n/en_US.json / i18n/zh_TW.yaml / scripts/compile_po.py
- **同一份内容要用两种语言写进两份文档时，用一张数据表渲染 + 内建自查，比手写两遍可靠**（2026-10-17，CODE_WIKI 中英「按模块总览」）：条目数/小节数/编号顺序由断言保证，自查规则要写成可执行的三条——EN 去掉反引号代码段后不得残留 CJK、不得含 `TODO`/`待补`/`…`、逐节条目数等于数据表长度。这套自查当场抓到我自己两个真实缺陷：标签把中文词直接拼进 EN（`[依赖]` 应为 `[dependency]`），以及代码示例里用 `…` 省略了实参（读者无法照抄）。**不要**用「子串出现一次」定位插入锚点：`## Changelog` 在正文里也有行内提及，必须按整行定位，否则章节会插错位置。
  | CODE_WIKI.md / CODE_WIKI_EN.md
- **Qt 的 `QFont` 族名位只收单个 family，且字体解析只能在 windows/mac 平台插件下验**（2026-10-17，用户日志两条 Qt 告警）：`QFont("Consolas, Menlo, Courier New, monospace")` 这种 CSS 式候选串在装了 Consolas 的机器上侥幸命中（`QFontInfo` 回读 `Consolas`），在没装的机器上由 `styleHint=Monospace`（枚举值实测 7）导流到 Qt 遗留别名表的 `Terminal`，产出 `DirectWrite: CreateFontFaceFromHDC() failed` + `QFont::setPointSize: Point size <= 0 (-1)` 两条同源告警。正确形态：按候选顺序取本机第一个真实存在的族名，候选全缺时交回 `QFontDatabase.systemFont(FixedFont)`，**不得**硬写 `setFontFamily("<某款>")`。**验证面的坑比缺陷本身更贵**：`QT_QPA_PLATFORM=offscreen` 下 `QFontDatabase.families()` 返回**空集合**、`QFontInfo().family()` 返回 `''`，任何「解析成了哪一款」的断言在 offscreen 上都是全假绿；要么用 windows 平台插件真建控件（`qInstallMessageHandler` 顺带抓 Qt 自己的告警），要么在测试里打桩 `QFontDatabase.families` / `systemFont` 把两条分支都钉住（本仓选后者，判据不随本机字体表漂移）。
  | src/gui_qt/widgets.py::fixed_font / tests/test_gui_qt_units.py / AGENTS.md GUI 窗口层条目 ⑦
- **「该键出现次数仍为 1」不足以证明写回幂等——判据要落到「产物仍能被 strict 解析器整份读出」**（2026-10-17，变异 M4 实测）：给缺键补写加一条幂等锁时，第一版只数目标键的出现次数；把写回改成「追加式落盘」（`open(..., "a")` 追加整份序列化结果）后用例**仍然全绿**——因为原文件本来就没有那个键，追加一份后计数恰好为 1，而文件里已经被重复追加了整个节/键集合。补上「用默认 `strict=True` 的解析器重读一遍不抛」这条判据后同一变异当场转红。推广口径：验「幂等/不重复」时，计数式断言只在**基线已含该项**的形态下有效；对「可能整块被重复写出」的产物，判据应是「下游消费者能否无差别接受这份产物」。
  | tests/test_config_io.py::TestMissingKeyWritebackIdempotency / src/config_io.py::read_config_value / AGENTS.md 配置键名节
- **「缺件」报错点离根因两跳远，判定链的关键是异常属于 `Exception` 还是 `BaseException`**（2026-10-18，evermeet macOS 取数端点被上游 410 整体下架）：CI 日志只点名 `full 包产物自检：ffmpeg/ 内找不到非空的 ffmpeg / ffprobe`，真因在两跳之前的 `[build] ffmpeg 下载失败：HTTPError: HTTP Error 410: Gone`——`_download_ffmpeg` 的 `except Exception` 把它收成一行 warning 并返回 False，空目录直到出包前自检才被硬判缺件。两条可推广的判法：① 见到「产物自检报缺件、同轮另一个组件（node）却正常」，先假定**下载阶段就被吞了**，去要自检行之前的完整日志而不是直接查解包逻辑；② 本仓把「归档里没取到件」写成 `raise SystemExit`（BaseException，不被上层吞），而 HTTP 层异常天然走 `except Exception`——所以「上游端点没了」永远是**降级成 warning + 末尾兜住**的形态，而「上游换了内部布局」才是**当场终止**的形态；据此可从日志位置反推故障发生在哪一层。上游侧的确认方式：直接 `curl -L` 打那个端点看状态码与响应体（410 的 JSON 里写着 `removed due to exorbitant abuse`），再读它的说明页正文，不要靠猜「是不是我这边网络/代理」。
  | build_exe.py::_download_ffmpeg / build_exe.py::verify_runtime_binaries / docs/agent-reference/measured-evidence.md
- **换出站下载点时，测试桩的 URL 必须从生产表推导，且要新造「多支归档版本一致」的不变量**（2026-10-18，同一轮）：darwin 端到端用例原先把 `/getrelease/zip` 之类的路径字面量抄进 `_install_routed_urlopen` 的 payload 键——表改了 URL 后这类用例不是变红而是**同时护住旧 URL**（桩按旧键匹配、生产按新键请求，只在匹配失败时才炸，等于把漂移的检测权交给运气）。改法：桩键经 `_artifact_url_for_slot()` 从 `_FFMPEG_DOWNLOAD_URLS` / `_EXTRA_EXECUTABLE_URLS` 取，用例只锁「按表取两支归档 + 按登记的签名 URL 验签」这层结构。另一条：macOS 的 ffmpeg 与 ffprobe 是**两支独立归档、版本号各写各的**，抬版只挪一支会得到跨代次的 full 包，而既有锁全都不会红（各自形状都合法）——补一条「两支归档的版本号必须相等」的判据，并在变异验证里单挪一支确认它真会红。
  | tests/test_build_exe.py::test_macos_ffmpeg_urls_point_at_immutable_artifacts / tests/test_build_exe.py::_install_routed_urlopen / AGENTS.md 构建产物节
- **Signal「定义了 + connect 了」不等于通路通了——测试直调内部消费函数会长期掩盖生产侧断路**（2026-10-18，S-01 全仓唯一严重项）：Qt GUI 录制输出链的 `linesReceived` 从未 `emit`、唯一消费口 `drain()` 生产调用方为零，而 UI 侧那句 `connect` 看着完整、`tests/test_gui_qt_units.py` 又直调 `drain()` 把断言全部跑绿，于是「日志页永不更新 / 自然下播永不感知 / 无法连续录制」三个可感知故障在仓库里静默存在。判据三条：① 核实跨线程通路一律 `grep` 该 Signal 的 `.emit(` 与消费方的**生产调用点**是否同时存在，只查定义和 connect 不作数；② 用例直调私有/内部消费函数时，同文件必须另有一条经真实通路驱动的用例；③ 修复选型要保住既有节流落点（本例保留队列 + 空载 `outputReady` 唤醒，而不是读线程直接 emit 带数据）。
  | src/gui_qt/recorder.py::outputReady / src/gui_qt/main_window.py::_pump_recorder_queue / tests/test_regression_gui_output_chain.py / AGENTS.md GUI 窗口层条目 ⑧
- **stdlib 替身挂进被测模块命名空间仍然不够：破坏面必须按「对象/路径」收窄，否则别的用例的后台线程会在窗口内走进同一支替身**（2026-10-18 全量实测）：L-18 的 `dm.os.replace` 故障替身把「失败」无差别施加给所有路径，`tests/test_danmaku_monitor.py` 的边车写线程在窗口内调用它、把自己 `tmp_path` 的文件名喂进本用例的 `attempts`，断言由 1 变 5——**单文件跑恒绿、整包跑红**（M-27 同族的新变体：`monkeypatch` 只保证事后还原，不保证窗口内只有本用例受影响），且反向把别人的轮转一并打坏。形态：`if src != path: real_replace(src, dst); return`，记账同样只记本对象。
  | tests/test_regression_infra.py::TestSidecarRotateBackoff / src/danmaku_monitor.py::_append_sidecar_line / AGENTS.md 测试编写强制约定
- **批量整改外部审查报告时：先数一遍正文，再信统计表；跨包副作用只有全量门禁会暴露**（2026-10-18，85 项 / 16 个并行工作包）：① 报告统计表写 86、5.1 标题写「生产代码 24 项」，正文实际只有 `M-01…M-23` 共 85 项——按正文枚举逐条建包，计数差如实写进交付；② 三个报告结论被实测证伪（「先建新句柄再改名」在 Windows 必 `PermissionError`、「对比导入前后」在已 import 的文件里造第二条假绿、「前台 shell 随即退出」机制描述错但缺陷成立），所以每条先核实再动手；③ 并行包各自跑自己的用例全绿，但 `run_node_script_async` 改执行原语会打红另一包的 `TestMigu`、新增日志模板会让 `test_runtime_templates_covered_by_catalog` 红——这类只有收尾那次全量跑才抓到，必须在派发时就写明「谁改了原语/新增了键」。
  | CODE_REVIEW_2026-10-18.md / tests/test_regression_spider.py / tests/test_i18n_migration.py
- **改 `.po/.json/.yaml` 目录文件的两个静默翻车点：`read_text()` 会吞掉 CRLF，注释级改动也会翻 JS 哈希钉定**（2026-10-18 本轮自查抓出）：① `Path.read_text()` 默认 universal newlines 把 `
` 译成 `
`，配 `write_text(newline="")` 写回就整文件转 LF——本仓 i18n 三目录与多数根文件是纯 CRLF，判据仍是「改前后各数一次 CRLF 与裸 LF，原本为 0 的那项必须仍为 0」，追加条目优先走 `read_bytes()`/`write_bytes()`；② `src/javascript/*.js` 只要动到**注释**，`utils._JS_SHA256_EXPECTED` 就失配（表钉的是原始字节），派发 JS 侧工作包时必须要求「回报新 SHA256 由主代理单点回填」，否则运行期 `DLR_JS_STRICT_HASH=1` 直接拒绝执行。
  | i18n/en_US.json / src/utils.py::_JS_SHA256_EXPECTED / AGENTS.md 关键约定 #10
- **「零调用方」不足以判定可删：同一形态下至少三种成因，删法各不相同**（2026-10-20，全仓依赖与死代码清点）：AST + 原始文本计数扫出的「零生产调用方」符号，逐条读上下文后分成三类：① **被测试按「整组常量取值」钉住**——`src/web_tray.py::SW_SHOW` 当前无调用点（显示走 `SW_RESTORE`），但 `tests/test_web_tray.py::test_module_constants_match_win32_api` 按「魔数抄错的症状是无异常抛出的视觉 bug」整组断言，删它当场 1 failed；② **函数体内已有明写的「不选删除」理由**——`spider.get_huajiao_sn` 带 MID-2223 的处置决定注释并登记在 `OVERSEAS_MIGRATED_FUNCTIONS` 双向锁里；③ **常量是「接错了线」而不是「没人要」**——`ui_motion.ROW_HIGHLIGHT_FRAMES=5` 与 `ui_kit.TAG_NORMAL="normal"` 都零引用，但各自调用点写的是字面量（`gui.py` 的 `frames=5`、`tag="normal"`），删常量等于把魔数钉死并与模块自己的注释矛盾，正解是接线（本轮对 `ROW_HIGHLIGHT_FRAMES` 即如此，取值同为 5、行为零变化）。推广口径：把「零引用」清单交用户确认之前先按这三类分流，只有「既无测试钉、又无在源理由、也不是被字面量顶替」的才进删除档。
  | src/web_tray.py::SW_SHOW / src/ui_motion.py::ROW_HIGHLIGHT_FRAMES / src/ui_kit.py::TAG_NORMAL / src/spider.py::get_huajiao_sn
- **引用面扫描的排除清单本身就是假阳性来源：漏掉 `.github/` 会把三个在跑的 CI 门禁脚本判成孤儿模块**（2026-10-20，同一轮）：第一版孤儿模块扫描把 `.github` 放进 SKIP，于是 `scripts/check_skill_agents_consistency.py`、`check_workflow_constants.py`、`sync_metadata.py` 三个都报「prod_importers=0 且 nonpy_refs=0」——实际它们分别被 `ci.yml`、`build-release.yml`、`.pre-commit-config.yaml` 点名。维护脚本的消费方几乎全在 workflow 与 hook 配置里，不在 Python import 图上。推广口径：判「孤儿」前先把消费面枚举完整（`.github/workflows/*.yml`、`.pre-commit-config.yaml`、`Dockerfile`、`build_exe.py` 的 datas/spec、AGENTS.md 的门禁清单、`pyproject [project.scripts]`），并**用「已知必然被引用的条目」做反向见证**——本轮的反向见证恰是这三个脚本，它们一出现即证明排除清单错了。
  | scripts/check_workflow_constants.py / .github/workflows/ci.yml / .pre-commit-config.yaml
- **删一个模块有三处「登记尾巴」，其中一处会让另一条用例静默改变语义**（2026-10-20，删除 `src/ab_sign.py`）：① `scripts/check_coverage.py` 的 `MODULE_THRESHOLDS` 条目必须同批删——该门禁把「登记表里的模块在覆盖率数据中查不到」判 rc=1；② CI 注释里的模块枚举（`ci.yml` 逐模块门禁那条）；③ **最隐蔽的一处**：`tests/test_check_coverage.py::test_exempt_claiming_generated_code_is_machine_checked` 拿 `src/ab_sign.py` 当「确定手写的模块」构造虚报豁免，模块删掉后 `read_text` 抛 `OSError`，`_validate_debt_and_exempt` 走的是「无法读取以核对生成物标记」分支而**不是**「虚报豁免」分支，断言因此转红——夹具语义随被测文件消失而漂移。改法是把样本换成另一个确定手写、且不含 `GENERATED_MARKERS` 任一标记的模块（本轮用 `src/proxy.py`），判据形态不变。推广口径：删文件后 `grep -rn <文件名>` 要连 `tests/` 与 `scripts/` 的**字符串字面量**一起扫，不能只扫 import。
  | scripts/check_coverage.py::MODULE_THRESHOLDS / tests/test_check_coverage.py::test_exempt_claiming_generated_code_is_machine_checked
- **整改类文档（`*_FIX.md` / 执行留痕）不能当代码地图：它的 file:line 与符号名会随每一次后续编辑过期**（2026-10-21，审查整改第二轮）：接手一份「已修 43 项」的留痕时，直接信它的行号会找不到符号（本例它写的 `_normalize_numeric_host` 从未存在，真实实现叫 `_literal_address`/`_is_internal_host`），甚至会把更早提交的代码误记成本轮成果（`M-31`）。可复用的接手顺序：① 对每条结论先 `grep` 它在文档里点名的**符号**而不是行号；② 用「删掉这行会不会让某条用例变红」判断是否真闭环；③ 只有代码与文档冲突时才以代码为准并在回复里写明差异。推广口径：留痕文档记录**判据与验证命令**，不记录易漂移的坐标。
  | docs/worklog/CODE_REVIEW_2026-10-21_FIX.md / src/stream_select.py::_literal_address
- **「注销后立即重建」类修复必须区分正常出口与异常出口**（2026-10-21，M-37 stats 线程）：把「房间表为空 → break」与「主体抛异常退出」都当成需要复活的路径，会让一次崩溃触发「崩溃→重建→再崩」的自旋（实测 1 秒内数十条 warning，既有回归用例直接红）。正确形态是用一个局部标志只标记正常出口（`revive_on_deregister`），异常出口维持「等下一次事件再拉起」的既有契约。推广口径：凡是「线程/任务退出后自愈」的改动，先枚举它有几条退出路径，再逐条决定要不要复活。
  | src/danmaku_monitor.py::_stats_loop

- **「登记了」不等于「登记值对」：钉定表的第④类盲区要用字节对账锁闭合，并且先证红再修**（2026-10-29，`liveme.js` 钉定失配）：`utils._JS_SHA256_EXPECTED` 的三条用例只锁「表键集合 == 目录 `*.js` 集合」与「表里的键都有文件」，**从不比对盘上字节哈希**——所以当 `34bd33e` 的 stash 冲突提交把清理提交 `25d6f68` 整体回退、`liveme.js` 多出 6 处 `console.log` 时，`pytest tests/test_utils.py -k JsPinTable` 仍 5 passed、black/isort/mypy 全绿。运行期的表现是每次首次编译打一条「与钉定值不符…请核查是否被篡改」**假告警**，而 `DLR_JS_STRICT_HASH=1` 下抛 `RuntimeError` 又被 `trace_error_decorator` 吞成 `{"is_live": False}` —— 整条签名链被伪装成「主播未开播」而不是报错，比崩溃更难发现。可复用口径：① 凡「表钉内容摘要」的资产，锁必须落到 `sha256(read_bytes()) == 表值` 逐条对账；② 新锁写完先对**未修复态**跑一次，证它确实判红（本轮即由该步骤点名 `liveme.js`、其余四份匹配），否则无法区分「锁生效」与「锁没接上」；③ 还原被钉定的 JS 必须走 `git show <ref>:<path>` 字节级写回——`.gitattributes` 对 `src/javascript/*.js` 钉 `-text`、表值对 rb 原始字节求摘要，手工删行或任何行尾归一都会再翻表。
  | src/utils.py::_JS_SHA256_EXPECTED / tests/test_utils.py::TestJsPinTable::test_pinned_bytes_match_the_table / .gitattributes / src/javascript/liveme.js
- **拿「含冲突标记的提交」当基线做集合差，会把冲突副本算成资产丢失**（2026-10-29，全仓审查的主控复核）：子代理以 `git show HEAD:tests/test_ui_kit.py` 与工作区做用例名差集，报「丢 18 条用例」；而 HEAD 那份文件里有 3 个冲突副本、AST 只 parse 出 14 个 `def test_`，差集因此把「冲突折叠」误读成「删除」。改用干净祖先 `f93c504` 重做 AST 集合差，实测该文件**丢失 0**（32 个用例逐名相等），真实丢失只有 `tests/test_gui_qt_units.py` 的 2 条（`test_recorder_log_messages_route_through_tr` / `test_recorder_path_logging_masks_credentials`）。推广口径：任何「改动前后资产增减」的判定，基线必须选**已知无冲突标记的祖先提交**（或先 `git grep -c '^<<<<<<< ' <ref>` 确认基线干净），并优先用 AST 符号集合而非行数——行数在冲突态下会被重复侧整体抬高。
  | tests/test_ui_kit.py / tests/test_gui_qt_units.py / git show f93c504:
- **并发工作包在审查期内持续改盘时，结论必须绑定「实测时刻 + 复跑判据」并把被修复项单列**（2026-10-29）：同一条判据在两分钟内从红变绿四次（i18n 三模板登记、`zh_CN.mo` 重编、旧名 `.mjs` 删除、注释密度违规消除），`git status` 从 102 → 110 → 113 个未提交文件。做法：① 每个读数写「时刻 + 可复跑命令」（`git grep -c ... HEAD`、`sha256sum -c` 基线比对证明只读）；② 被并发改动的项**不进本轮清单**，另设「审查期内已被修复」表，避免与另一包的修复日志双记造成第二事实源；③ 报告定稿前重跑一次判据，并核对「我改动的文件集合」与并发包改动集合可区分（本轮实际改动只有 `src/javascript/liveme.js` 与 `tests/test_utils.py` 两个文件，其余均为并发包所改）。
  | docs/worklog/CODE_REVIEW_2026-10-29.md / i18n/zh_CN/LC_MESSAGES/zh_CN.po / tests/frontend/test_regression_2026_09_22_gates.mjs
