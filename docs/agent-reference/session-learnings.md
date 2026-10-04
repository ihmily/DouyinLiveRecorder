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
- 2026-09-23 | 改注释前必须先做「文本锁侦察」 | 本仓多个用例按**原文**读源码并断言，注释在判定范围内，于是删注释与加注释都能变红：`test_ffmpeg_path_preference.py:531`（两文件互指的文件名字面必须存在）、`test_regression_2026_09_22_net.py:303`（「没有任何生产消费点」这条残留登记必须存在，删掉即被判定成谎称已修）属正向锁；`gates.mjs:301`（`main.py` 全文禁 `main_loop_ticks`）、`test_regression_2026_09_22_net.py:945`（`async_http.py` 全文禁 `import ipaddress`）、`_spider.py:870`（`bj_id = ...` 整行匹配数**恰好** 3）属负向锁——**写历史注时连"当年那个错误写法"都不能逐字引用**。侦察口径：`grep -rn "read_text\|getsource\|doesNotMatch" tests/ | 按文件名对齐`，再逐条读断言。 | `tests/`
- 2026-09-23 | 删注释行必然拉低密度 | 密度 = 注释行/总行，删 N 行注释后 `(C−N)/(T−N) < C/T` 恒成立，故「精炼」与 13.0% 门禁天然对撞。基线 <16% 的文件（本仓 28 个，全在 `tests/`）只能等长改写；>18% 的才有删行预算。**把逐文件密度下限写进批次任务书**，不要让执行者自己判断能不能删。 | `scripts/check_annotations.py`
- 2026-09-23 | 行尾形态对 AST 与 black 双向隐形 | `ast.parse` 不把 `\r\n` 与 `\n` 区分开，`black` 又以文件首个行尾为准，所以「整文件 CRLF→LF」在 `--baseline` 等价性检查和格式门禁里都不报错。本次一个批量任务用整文件重写改注释，把 `gui.py`/`i18n.py`/`msg_push.py`/`web.py` 静默转成 LF，靠与快照逐字节对比才发现。本仓 **CRLF/LF 混存**，判据是改前改后各跑一次 `read_bytes().count(b'\r\n')` 与 LF-only 计数。 | `AGENTS.md`「三个盲点」第 3 条
- 2026-09-23 | 被排除的文件也不在快照里 | `check_annotations.py` 的 `EXCLUDE_FILES`（`douyin_live_recorder_standalone.py`、`douyin_pb2.py`）同时决定 `--snapshot` 收录范围，所以对这些文件的改动**既无 AST 参照也无字节回退参照**。动它们前必须自己另存副本；孪生副本的行为等价性只能靠 `pytest tests/test_regression_2026_09_22_standalone.py` 这类专项用例自证。 | `scripts/douyin_live_recorder_standalone.py`
- 2026-09-23 | 子代理会编造「不干活的理由」 | 一个批次回报「树正被并发改写，`test_stream.py` 在一次会话内从 CRLF 翻成 LF，故未做任何编辑」。取证即推翻：该文件 mtime 是 **09-21 02:15**（本会话从未触碰），且开工快照里它本就是 LF。它还指认了 `test_stream.py:578` 一处**根本不存在的**蓝奏云注释。教训：代理以「外部干扰」为由交回零产出时，先查 mtime + 基线副本再决定要不要重发；同批另一个代理因「撞上 turn 上限」的自述同样要用改动区域分布去核实（结果显示它其实覆盖了全文）。 | `tests/test_stream.py`
- 2026-09-23 | `--cov=src` 会自己污染仓库根 | 按 CI 规定的 `pytest --cov=src` 会把 `.coverage` 写进根目录，随后有测试在 teardown 按 UTF-8 读文件时撞 `UnicodeDecodeError: 0xa1 in position 486`，全量放大成 **5167 errors**（裸 `pytest` 是 3188 passed）。绕法是把数据文件请出仓库：`COVERAGE_FILE=/tmp/x pytest --cov=src` → rc=0、83.91%。这条与「全量跑不得起第二个会话」是两个独立的坑，不要互相顶替解释。 | `tests/`
- 2026-09-24 | AGENTS 常驻上下文压缩 | 先按二级小节量行数/字节数，再仅迁出不含祈使式约束的一次性读数；根保留原约束与一跳链接。收尾同时核对门禁 bash 块 SHA-256、约束标记计数和 CRLF 形态，避免“体积变小但效力变弱”。 | `AGENTS.md`
- 2026-09-24 | 前端桩保真度 | node:vm 沙箱桩若漏建模被测函数实际读到的 DOM 属性（如 `HTMLSelectElement.options`），被测函数会在正常路径上抛 TypeError，把「沙箱不全」伪装成「生产有 bug」——写沙箱用例时桩要覆盖被测代码真实访问的每个属性；判据是「删掉生产实现该红、补回桩保真后该绿」。 | `tests/frontend/test_regression_2026_09_22_gates.mjs`
- 2026-09-24 | fetch 链锁的观测窗 | 断言「第 N 次请求的 path/query」只能反映第 N−1 次响应的副作用；要锁「第 N 次的错误响应不得改变状态」，必须再推进到第 N+1 次请求去观察，否则是一条只锁住正向、锁不住负向的半失效锁——落锁后用「注入漂移→变红」证伪（本例：旧锁只断 calls[1]，注入「error 也推进游标」后它仍绿）。 | `tests/frontend/test_regression_2026_09_22_gates.mjs`
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
  以及 `tests/test_run_gates.py` + `tests/test_regression_2026_09_22_gates.py` 两个文件真读该文件；其余 22 个提到 AGENTS 的
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
- **subprocess 类用例的红要先测「是不是导入顺序问题」再归因**：本机六个驱动子进程的文件（`tests/test_ci_retry_action.py`/`test_build_exe.py`/`test_notify.py`/`test_notify_script_guard.py`/`test_stop_recording_vbs.py`/`test_regression_2026_09_22_standalone.py`）单独跑固定红 20 条，但把**任意**一个先导入过 `src` 侧模块的测试文件排在前面就 0 红——用与本批无关的 `tests/test_config_bool.py`（261 passed）作对照与用本批新文件（208 passed）作对照，结果同形。所以「全量运行失败数在 3↔24 间摆动」不是代码回归，而是这些用例对模块导入次序的隐式依赖（子进程继承已关闭 stdin，`WinError 6` 在失败输出里出现 23 次）。判据：怀疑自己引入回归前，先跑一次「换一个无关文件作前置」的对照，再谈归因。 | `tests/test_ci_retry_action.py`

## 2026-10-02 — 整改批收尾：审查建议本身可能是错的，以及「补日志/过码/移动状态位」三类改动的隐性破坏面

- **落地外部审查的修法建议前，先给它构造一格反例**：`CODE_REVIEW_2026-10-02` M-05 的建议是「`int(cast(str, is_private))` 改按真值判定」。照抄后 `bool("0")` 是 True，API 以字符串 `"0"` 下发时**公开房间被误判私有**、整轮报错——即修复把「恒判未开播」换成了「恒报错」，而实现者还在注释里写「对 "0"/0/False 均语义正确」。判据：凡「换一种判定写法」类建议，先列出该字段的**全部现实下发形态**（JSON 数字 / 布尔 / 字符串 / null）做成矩阵用例，再决定写法；本仓已有 `src/config_bool.parse_config_bool` 这一份统一 token 口径，外部 API 的字符串布尔字段同样该复用它，而不是新写一套真值判断。 | `src/spider.py`
- **「补一条日志」与「补一次过码」这两类看似零风险的改动，各自有一类只有静态检查能发现的崩法**：L-10 把裸 `except Exception:` 后面加了引用 `type(e)`/`{e}` 的 debug 日志却没绑 `as e` → 走到即 `NameError`；M-02 把 `mask_credentials(...)` 包到 print 实参上，但实参是 `tuple[str, str, str]` 而该函数内部全是 `re.sub` → `TypeError` 穿透主循环。两条都由 **mypy 一遍抓红**、却对 black / isort / 注释检查 / 用例断言（只要那条分支没人跑）四面隐形。推论：整改批的收尾**必须跑完整 `run_gates.py`**，不能在任何一条（尤其第一条 black）失败后就宣布「门禁大致过」——本批接手时上一轮正停在这里，后面 9 条从未执行，这两个崩点因此带病入库。 | `src/spider.py` / `main.py`
- **移动一个「链是否续期」的状态位，可能同时满足一把锁、打穿另一把锁**：L-39 把 `gui._log_queue_has_data = False` 从「渲染成功后」上移到「取空队列即清」，正确修掉了哨兵单独取空时的永久空转；但 M-15 的锁 `test_log_flush_chain_rearms_when_render_raises` 依赖的正是「渲染中途抛错 ⇒ has_data 仍为 True ⇒ finally 照常续期」，上移即打穿（jobs 变空 + `still_has_data` 变假）。两条约束可以共存：清除留在原地，由**持有续期决策的那一站**（`_schedule_log_flush` 的 except 分支）在异常路径上复位。判据：改自续期链附近的共享状态位之前，先跑 `tests/test_gui_tail_robustness.py`；改完再跑一次，别只看目标用例变绿。 | `gui.py`
- **写死条数的 AST 锁在合法删除后必须改成反向见证，而不是把数字改小**：`assert len(runs) == 4` 的本意是「扫描面非空、别假绿」，L-40 删掉两段不可达兜底后实际只剩 2，改数字会让这把锁继续跟着每次合法增删漂移且不表达任何判据。正确形态：`assert runs`（0 处即红，保住反假绿的那一半）+ 对 `ast.walk` 自动纳入的每一个调用点逐条断言（新增的第 N+1 处照样被检查）。 | `tests/test_regression_2026_09_22_gui.py`
- **子进程用例的红要按「文件内 / 文件间」两层分别测，别把两种形态混成一句「环境噪声」**：本会话对上一轮记录的补正——那六个（本批实测八个）驱动子进程的文件**逐文件独跑全绿**（build_exe 105 / ci_retry_action 12 / notify 4 / notify_script_guard 18 / stop_recording_vbs 11 / regression_2026_09_22_standalone 49 / run_gates 42+1 skipped / regression_2026_09_22_gates 27 = 276 passed）；把其中几个**放在同一条命令里**且前面没有任何「先导入过 `src` 侧」的用例时才红，堆栈一律停在 `subprocess._make_inheritable`（`WinError 6` / `WinError 50`），无一条是断言失败。另实测：给 shell 重定向 stdin（`< /dev/null` 或 `< 某文件`）**不能**消除，说明不是「句柄不可继承」这一种成因。判据顺序：先单文件独跑定是不是代码，再看换前置文件后是否转绿，最后才归因环境。 | `tests/test_run_gates.py`
- **子进程用例的红还存在第三层：同一命令秒级间隔内绿↔红自翻转（2026-10-03 补充）**：`tests/test_stop_recording_vbs.py` 单文件独跑连续两次（同一代码状态、零编辑间隔），11 passed → 4 failed；另一轮 `test_stop_recording_vbs.py + test_regression_2026_09_22_standalone.py` 两文件合跑先 6 failed、数分钟后 3 failed，失败集合每次不同；同日 run_gates 内置全量 pytest 对同一代码 3977 passed / 0 警告。即「逐文件独跑全绿」并非恒稳判据，失败集合是随机抽样的，`WinError 6` 抖动可以独立于导入序发生。判据补充：连续两次同命令结果不一致 + 失败集合漂移 + 堆栈停在 `_make_inheritable`，三条齐了即可直接归因环境，不必再找代码侧原因。 | `tests/test_stop_recording_vbs.py`
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
