# 全仓静态代码审查报告（2026-10-30）

> 审查执行时间：2026-10-30 15:46 起至 2026-10-31 凌晨收尾（本机时钟，Windows 10.0.26300 x64 / Git Bash）
> 审查对象工作区：`D:\DouyinLiveRecorder`，分支 `main`，HEAD = `664a026`
> **声明：本次审查全程只读，未修改、未创建、未删除任何源文件；本报告是本次审查新增的唯一仓库文件（快照复比 PASS，见 §8.3 判据 10）。**
> 报告放置说明：沿用本仓既有惯例落 `docs/worklog/`（与 CODE_REVIEW_2026-09-30/10-02/10-29 等历轮同目录），文件名取委托当日日期。

## 1. 审查概述与背景

### 1.1 触发背景

用户要求对当前工作区全部源代码（Python / JavaScript / 其他语言）执行全面、系统的只读静态审查：四维度（代码质量、潜在缺陷、安全漏洞、逻辑错误与死代码）、逐文件记录、按严重程度分组、产出本报告。附加核对任务：上一轮（`CODE_REVIEW_2026-10-29.md`）的整改已随 `664a026` 入库，本轮须逐条复核其遗留项（§7.1）。

### 1.2 本轮最重要的背景事实（决定了多数发现的成因）

以下均为实测，取数时刻 2026-10-30 15:46（快照）与当日各判据实跑时刻：

1. **HEAD 与工作区均无冲突块**：`git grep -c '^<<<<<<< '` 对 HEAD 与工作树均空（rc=1、0 命中）。上一轮 S-01（HEAD 含 899 冲突块）已由 `664a026` 终结——本轮**不存在**冲突解决语境，全部发现都来自对当前干净主干代码的直读。
2. **工作区全程零漂移**：起始 `git status --porcelain` 0 条；审查中期与收尾两次快照复比 `changed=0 removed=0 added=0` PASS。无并发工作包，§7.3 因此为空。
3. **全部跟踪 `.py` 可解析**：快照 AST ok=270 / broken=0；判据探针 258/258（排除目录口径不同）。上轮「94 个文件无法解析」的形态已不存在。
4. **静态门禁面实测全绿**（真实退出码，缓存外置 `%TEMP%`，仓库零写入）：check_annotations / compile_po --check / check_version / check_runtime_pins / check_skill_agents_consistency / check_coverage / check_workflow_constants 全 rc=0；black 26.10.1、isort 9.0.2（Unable to parse 0 处）、mypy 2.4.0 三跑（本机 / --platform linux / --platform win32，各 258 文件 0 问题）、basedpyright 1.40.2（0 error / 0 warning）；定点 pytest 同源锁族 14 passed；JS 钉定对账 5/5。四个工具版本与 `ci.yml` consts 逐一同值（black 26.10.1 / isort 9.0.2 / mypy 2.4.0 / pytest 9.1.1，本地 pip show 实测），但**未经 CI 实跑验证**（CI 现为仅手动触发）。
5. **上一轮 P0/P1 整改基本落地**：S-04/S-06/S-07/M-08/M-09/M-10/M-12/M-13/M-26/M-34 等经本轮复跑判据确认已修（§7.1）；残留为 S-05（三处直建 AsyncClient，P2 待办，本轮 M-04）、M-23（两个跟踪态破口）、M-24（standalone 孪生漂移）、M-32/M-33（12 处平台 skip 形态）与 5 处悬空回归锁引用。

### 1.3 本轮结论摘要

| 严重程度 | 数量 | 说明 |
| --- | --- | --- |
| 严重 | **0** | 无凭据明文入库、无注入面回归、无「门禁全绿但主干不可用」形态 |
| 中等（同族合并后） | **17** | M-01～M-17，其中 4 条集中在独立发行副本 standalone（防线漂移未回灌），3 条集中在打包/发布面 |
| 轻微（同族合并后） | **16 族** | L-01～L-16，以空值边界残余、注释失真、死代码、结构度量为主 |

**总体判断**：主干健康度良好——录制链、选源探针、弹幕协议、调度器、Web 鉴权与掩码棘轮、运行时钉定等 AGENTS 钉定防线经逐行核对均成立（§7.4）。本轮真正的风险画像与上轮不同：**没有状态性劣化，剩下的全部是「防线覆盖缺口」**——同一道防线在主线已修，但它的三个「镜像面」没跟上：独立发行副本 standalone（M-13/M-14/M-24）、安装器三胞胎中的 node 侧（M-11）、以及 mask_credentials 的键名判据面对真实基线键（M-10）。这类问题的共同特征是「主线判据正确、旁路面漏改」，修复成本全部为低（单点小改），建议一批收口。最需要先动的一条是 M-08（`web_tray_icon` → 免鉴权 `GET /favicon.ico` 任意文件读链），它把「配置值绝不外泄」的掩码棘轮整个绕开。

## 2. 审查范围与方法

### 2.1 范围（快照实测 2026-10-30 15:46）

| 区域 | 文件数 | 行数 | 审查方式 |
| --- | --- | --- | --- |
| 根目录（入口/构建/配置） | 26 | 23075 | 逐行精读（main.py/gui.py/build_exe.py/StopRecording.vbs 等 7 文件专区代理，其余主控直审） |
| `src/` 顶层 | 43 | 29939 | 逐行精读，按职责切 6 区 |
| `src/gui_qt/` | 17 | 4881 | 逐行精读 |
| `src/platforms/` | 8 | 1627 | 逐行精读 + 协议对账 |
| `src/proto/` | 4 | 745 | 存根/生成物同步性核对 |
| `src/javascript/` | 5 | 1928 | 签名/输出面精读（crypto-js.min.js 正文排除）+ 钉定对账 |
| `web/` | 4 | 3244 | 逐行精读 |
| `scripts/` | 18 | 8397 | 逐行精读 |
| `tests/` + `tests/frontend/` | 172 | 78512 | 判据扫描全覆盖 + 关键文件抽读 4 个（4380 行）+ frontend 专区代理全读 |
| `typings/` | 12 | 256 | 逐文件核对 |
| `.github/` + 根配置 | 20 | 2863 | 逐行精读 + 同源对账 |
| `config/` | 2 | 190 | 逐行精读（脱敏基线核对） |

**排除项**（不读正文）：`.venv`、`build`、`dist`、`coverage*`（`.coverage`/`coverage.xml`/`coverage.json` 为覆盖率产物，虽被跟踪但只作读数来源）、`.git`、`ffmpeg/`、`node/`、`downloads/`、`logs/`、`backup_config/`、`recordings/`、`DouyinLiveRecorder.egg-info/`（生成物）、`uv.lock`（派生消费方）、`.workbuddy/`、`.zcode/`（本地工具目录）、`docs/**` 与根 `*.md` 正文（只做同源性核对）、`i18n/*` 目录正文（只做键集合与锁族对账）、`src/javascript/crypto-js.min.js` 正文（第三方压缩库，仅钉定对账）、`src/proto/douyin_pb2.py`（protoc 生成物，只核 gencode 标注与 `.pyi` 同步）。

### 2.2 方法

1. **语法/结构层**：Python 3.14.9（venv）对全部跟踪 `.py` 做 `ast.parse`（0 失败）；AST 判据扫描（`ast_probe.py`，阈值：超长函数 ≥200 行、嵌套 ≥6 层、形参 ≥9 个）——命中只作线索、逐条实读裁决（核销台账见 §7.2）。
2. **只读门禁实跑**（真实退出码，`命令 >"$LOG" 2>&1; echo rc=$?` 口径；mypy 缓存外置 `%TEMP%` 保持仓库零写入）：§1.2 第 4 条全清单。
3. **高危模式横向扫描**（生产面 grep）：`eval(`、`exec(`、`pickle`、`yaml.load(`、`os.system`、`shell=True`、`md5|sha1`、`verify=False`、硬编码凭据字面量——除 Qt 事件循环 `.exec()`、`x-bogus.js` 白名单 `eval`、`run_gates.py` 受控退化形态外**全部 0 命中**。
4. **同源性对账**：pyproject ↔ requirements ↔ ci.yml consts ↔ .pre-commit rev（逐值相同）；JS 钉定表 5/5；`.gitignore` ↔ `.dockerignore` ↔ `PROTECTED_RUNTIME_DIRS` ↔ pyproject 各 exclude（括号形态完好）；悬空回归锁引用普查（46 → 5，见 §7.1）。
5. **分区逐行精读**：13 个只读子代理（Z1 main.py / Z2 gui.py / Z3 spider.py / Z4 根杂项 / Z5 Web 后端 / Z6 选源录制链 / Z7 网络与配置 / Z8 调度与安装器 / Z9 UI 与 Qt / Z10 平台·协议·JS / Z11 Web 前端 + frontend 测试 / Z12 scripts / T1 tests 判据+抽读），每区 2k–11k 行，统一作业简报（只读硬约束 + 17 条刻意设计白名单 + 严重度口径 + 回传格式），并发上限实测 2。
6. **主控复核（关键纪律）**：全部 17 条中等断言由主控逐条独立复跑（实读代码 + 只读探针，见各条目）；被推翻/收回的断言登记 §7.2，无静默删除。

### 2.3 工具版本口径

Python 3.14.9（venv）；black 26.10.1、isort 9.0.2、mypy 2.4.0、pytest 9.1.1（与 `ci.yml` consts 逐一同值，本地 pip 实测）；basedpyright 1.40.2（本地补充门禁，CI 不跑）。CI 现为仅手动触发，上述同值性为**本地口径核对，未经 CI 实跑验证**。

## 3. 严重问题（S 组）

**本轮 0 条。**

三条曾考虑升格「严重」的路径，均被前置条件拦住，记录裁决理由防止后轮重复争论：

- **M-08（`web_tray_icon` → 免鉴权 favicon 任意文件读）**：链路四环全部实读成立，但利用需（a）已有合法会话（bearer 只发给知道口令的人），或（b）用户显式把面板暴露到非回环地址**且**关闭认证（`web.py` C1 闸门会拒绝 `0.0.0.0`+无认证启动，`docker-compose` 默认绑 `127.0.0.1`）。默认安装形态不可达，故定中等、列修复优先级首位（§8.1 P0）。
- **M-13（standalone 探针异常把带 token 流地址写入日志）**：影响面限定在独立发行副本且需 CDN 异常/被劫持前提，不构成默认路径上的凭据泄露；但与 AGENTS「写入日志前必须脱敏」红线直接相悖，修复成本极低。
- **M-11（node 安装器 TOFU fail-open）**：需「官方清单不可达 ∧ 本地基准损坏 ∧ CDN 被替换」三重叠加，且 node 二进制落 `node/bin` 后仍受钉定表结构门禁（`check_runtime_pins.py`）间接约束；fail-closed 兄弟实现（ffmpeg 三链）已存在，对齐即可。

## 4. 中等问题（M 组，同族已合并）

> 每条均含：位置（行号来自实读）、证据、影响、建议、修复成本、主控复核方式与处置状态。本轮为只读审查，处置状态一律为「未修」，供整改轮回写。

### M-01 线程启动失败回滚漏收 `_room_seq_in_use`，序号永久跳过且登记表无界累积

- **位置**：`main.py:5440-5453`（登记）、`main.py:5517-5530`（回滚）、`main.py:5496-5504`（正常清理点）
- **证据**：`_room_seq_in_use[_room_seq] = threading.current_thread()`（:5445，登记值是**主调度线程**、恒 alive）；`except RuntimeError` 分支（:5519-5530）只做 `create_var.pop` + `remove_room_from_running`，**无** `_room_seq_in_use.pop(_room_seq, None)`；该 pop 全文件唯一出现在 :5504（`_room_thread_target` 的 finally），而 start 失败时该线程从未运行，finally 永不执行。
- **影响**：每次 `Thread.start()` 抛 RuntimeError（线程数打满时可达）即永久烧掉一个录制名序号，并在 dict 里留下一条恒 alive 的条目——7×24 常驻进程下慢速无界增长。另 :5442 的 `is_alive()` 判定因登记值恒为主线程而**空转**（真实清理机制只剩线程退出 pop 一道），:4881 注释写「见 start_record 的 finally」与实际锚点不符。
- **建议**：RuntimeError 分支补 `_room_seq_in_use.pop(_room_seq, None)`（`record_state_lock` 内）；顺带修正 :4881 注释锚点。
- **修复成本**：极低（1 行 + 注释）。
- **主控复核**：实读三段代码确认；「登记值恒为主线程 → is_alive 恒真」由 :5445 与 :5509 的执行顺序直接推出。

### M-02 AcFun 用裸 `itemgetter("bitrate")` 排序，缺键即整轮静默「未开播」

- **位置**：`src/spider.py:5510`（对照同文件已修判据 :2002-2008 与 :450-452 注释）
- **证据**：`play_url_list = sorted(play_url_list, key=itemgetter("bitrate"), reverse=True)`；同文件 B站分支自我约束「排序键同样收口：取不到的元素按 0 排到最后，而不是让整轮解析抛 KeyError」并统一走 `_qn_sort_key`——AcFun 同形态漏改，:5496 注释还把裸 itemgetter 写成既有契约。
- **影响**：`representation` 任一元素缺 `bitrate`（风控降级响应）时，已确认开播的取流整轮被 `trace_error_decorator` 吞成 `{"is_live": False}`，无 `_warn` 归因，表现为「AcFun 某房间永远未开播」且难排查。
- **建议**：复用 `_qn_sort_key` 同款容错排序键（取不到按 0）。
- **修复成本**：极低。
- **主控复核**：实读 :5495-5512 与 :450-452/:2002-2008 对照，确认。

### M-03 B站 `url_info` 的 host/extra 用 `.get(key, "")` 收窄，显式 null 时拼接抛 TypeError 被吞成「未开播」

- **位置**：`src/spider.py:2036-2038`
- **证据**：`host = cast(str, url_info_list[0].get("host", ""))`、`extra = ...get("extra", "")`、`m3u8_url = host + base_url + extra`。`.get` 缺省只挡「缺键」，不挡「键存在但值为 null」——同函数 :1992-1993 自称「本段不能用裸下标/裸 itemgetter」，:1219-1221（快手）注释承认显式 null 形态真实存在。
- **影响**：url_info[0] 任一字段为 null 时 `str + None` 抛 TypeError，整轮解析静默归因为未开播，绕过本函数其余位置统一的 `_dig_str`/`_warn_api_abnormal` 归因口径。
- **建议**：两处改 `_dig_str(url_info_list[0], "host")`（缺键与 null 均回空串）。
- **修复成本**：极低。
- **主控复核**：实读 :2030-2042 及上下文判据注释，确认。

### M-04 三处直建 `httpx.AsyncClient` 绕过统一出站管线，逐跳内网复检缺位（上轮 S-05 残留）

- **位置**：`src/room.py:150-151、:256-262`、`src/spider.py:4024-4059`（对照合法接线点 `src/async_http.py:65-77` `_build_client`）
- **证据**：三处均为 `async with httpx.AsyncClient(proxy=..., timeout=..., verify=http_config.ssl_verify)` + `follow_redirects=True`，无 `event_hooks`；`_build_client` 恒挂 `_build_hop_guard` 逐跳复检。初始 URL 侧 `_outbound_target_reason` 前置闸门在 room.py 已接线（:95-107），但「公网短链 → 302 → 内网/元数据」的跳转落点不被复检——内外闸门不对称。spider.py :4048-4059 的 `mask_credentials` 补丁正是直建点需逐项手补防线的例证。
- **影响**：SSRF 防线的「不建连」语义在这三条链上退化为「响应不外流」（钩子在响应头到达后才触发）；上轮已判 P2 待办，本轮确认仍未收敛。
- **建议**：三处收敛到 `async_req`/`_build_client` 接线（或最小化地挂同一 `event_hooks`），使「逐跳复检只有两个合法接线点」的口径闭环；同批补结构锁。
- **修复成本**：低-中（三处改写 + 回归锁）。
- **主控复核**：grep 定位 + 实读两区代理回传证据，确认三处行号与形态。

### M-05 `smoke_web` 回环覆盖的 with 窗口只包住 `_launch`，还原先于子进程读配置，机制当前为同字节空转

- **位置**：`build_exe.py:2205-2206`（with 作用域）、`:2151-2155`（还原）、`:2158-2186`（`_force_loopback_web_host`）
- **证据**：`with _loopback_web_host():\n    proc = _launch(exe)`——finally 的 `cfg.write_bytes(original)` 在 spawn 后毫秒级执行，而冻结 exe 经解释器启动 + `import main` 后才读配置（秒级之后）。当前模板 `web_host = 127.0.0.1` 使补丁字节恒等（空转）；若模板改回 `0.0.0.0`：无认证时子进程读还原值 → C1 闸门拒绝 → 冒烟恒红（fail-closed，可见失败）；有认证时冒烟实际测的是 `0.0.0.0`+认证，与 :2199-2201 注释承诺「显式覆盖为回环地址…验证真实启动路径」不符。
- **影响**：该机制对冻结子进程从未生效过；注释承诺与实现相反（文档-代码说谎族）。
- **建议**：把 with 扩到整个探活循环（至少 `_finish` 之后），并以「模板已 127.0.0.1」为前提重审是否保留该机制；补一条「patched != original 时子进程确实读到补丁值」的用例锁。
- **修复成本**：低。
- **主控复核**：实读 with 作用域与还原时序，确认；「子进程读配置晚于还原」为代码结构推断（spawn→解释器启动→import 链路），未真机复现，标注待确认。

### M-06 `_sanitized_config_text` 声称「保留注释与节结构」，configparser 往返实测丢弃全部注释

- **位置**：`build_exe.py:382-419`（实现）、`:383`（承诺）、`:2160-2161`（同文件自证「往返会丢注释」）
- **证据**：函数头注释「把 config.ini 文本按『敏感键置空』重写为可分发模板，**保留注释与节结构**」；实现为 configparser `read_string` → 按 sections/items 重建 `lines`——注释不在 parser 模型内，输出 0 注释（分区代理只读探针实测：源 175 行/11 条注释 → 输出 164 行/0 条）。同文件 :2160-2161 在另一处明确写着「按行操作而非 configparser 往返：往返会丢注释、把键名小写化」。
- **影响**：发布 zip 里的 `config/config.ini` 成为无注释裸模板，用户失去每个中文键名的内嵌说明；注释承诺与实现相反，误导维护者以为无需处理。
- **建议**：改按行重写（沿 `_force_loopback_web_host` 的行级手法，仅对命中敏感判定的行置空值），或改注释为「不保留注释」并接受现状；按 AGENTS「修改注释只增不改」，优先选前者。
- **修复成本**：低-中（行级重写需保敏感判定逐行语义，同批补用例锁）。
- **主控复核**：实读 :382-419 与 :2160-2161，确认「承诺 vs 实现」矛盾；注释丢弃由 configparser 模型直接推出。

### M-07 签名档分支无条件打印「官方签名核验通过」，本地路径验签被跳过后仍打出通过日志

- **位置**：`build_exe.py:1407-1416`、`:936-979`（`_verify_official_signature`/`_skip_or_fail`）
- **证据**：:1412 调用 `_verify_official_signature(dest, slot, desc)` **不接收返回值**（返回值在 `_verify_gpg_artifact` :949 被丢弃）；本地路径（非发布、非 strict）下 gpg 缺失/签名取不到时 `_skip_or_fail` 打 `[warn] 签名核验跳过` 后 `return False` 不抛（:970-971）；控制流落到 :1416 无条件打印 `[build] {desc} 官方签名核验通过（{slot}），实测 SHA256=...`。:1413-1414 注释自述该行是「事后审计线索（发布产物版本异常时唯一的可比对记录）」。
- **影响**：本地构建日志出现「核验跳过」与「核验通过」两行自相矛盾；审计线索失真。发布路径不受影响（该情形 SystemExit）。
- **建议**：让 `_verify_official_signature` 返回 bool 并在 :1412 接收，False 时打印「未通过/未核验（产物不得发布）」。
- **修复成本**：极低。
- **主控复核**：实读 :936-979 与 :1398-1419 控制流，确认。

### M-08 `web_tray_icon` 可经配置写任意绝对路径，免鉴权 `GET /favicon.ico` 直接回读——掩码棘轮被整条绕开的任意文件读链

- **位置**：`src/web_api.py:319-324`（`_DANGEROUS_CONFIG_KEYS` 不含该键）、`:1475-1488`（favicon 路由）、`src/ui_icons.py:196-211`（`resolve_icon_path`）
- **证据**：四道写守卫（危险键黑名单 / 敏感空值与掩码 / reauth / web_host）全部不覆盖 `web_tray_icon`；favicon 路由自述「免鉴权（中间件白名单已放行）」，`resolved = current_icon_path(...)` 后直接 `FileResponse(str(resolved))`；`resolve_icon_path` 对绝对路径只做 `candidate.is_file()`——**无扩展名约束、无目录沙箱、无内容校验**（ICO 魔数校验只在 upload/install 路径）。
- **影响**：持 bearer 会话者可 PUT 任意文件路径再经 `/favicon.ico` 读取原文——包括**未脱敏的 raw config.ini**（全部 Cookie/口令），GET /api/config 读侧的 `'***'` 掩码与写侧 400 拦截对本链路同时失效。认证关闭的实例上该键可被任何能访问端口者写入（默认 web_host=127.0.0.1 限定本机；暴露形态见 §3 裁决）。
- **建议**：①把 `web_tray_icon` 列入 `_DANGEROUS_CONFIG_KEYS`（或要求 reauth）；②favicon 读取侧对 resolved 文件复跑 `probe_ico_sizes` 魔数校验，非 ICO 即 404。两道同批落地。
- **修复成本**：低（黑名单 +1 行、读取侧复用既有校验函数）。
- **主控复核**：四守卫逐条实读 + `resolve_icon_path` 实读，链路四环全部确认；定级裁决见 §3。

### M-09 `toggle_room` 对缩进注释行 enable 假成功（写回仍是注释却报 `enabled: true`），disable 还写出双注释

- **位置**：`src/web_api.py:1037-1052`
- **证据**：`content = old_raw.lstrip("#").strip()`——`old_raw="  # https://x"` 时 `lstrip("#")` 剥不动前导空格，`content` 仍以 `#` 开头；enable 分支 `new_raw = content` 写回后仍为注释行；:1049 的写后验证只比 `raw_line == new_raw` 文本相等，不判语义 enabled，于是返回 `{"ok": True, "enabled": True}`。同文件 `_rewrite_quality_field`（:737-746）用 `^(\s*#\s*)` 明确承认缩进注释行真实存在。disable 分支则写出 `# # url` 双注释。
- **影响**：手编辑产生的缩进注释房间点「启用」回 200/true 但永不录制；用户以为已启用，实际房间静默消失在轮询之外。
- **建议**：对齐 `_rewrite_quality_field` 的前缀解析（`re.sub(r"^\s*#\s*", "", old_raw)`），写后验证改为「重解析出的 enabled == req.enable」。
- **修复成本**：极低。
- **主控复核**：实读 :1027-1053 并手工推演两种取值，确认。

### M-10 `mask_credentials` 的 ini 行形态漏掉基线模板真实键「发件人密码(授权码)」

- **位置**：`src/utils.py:1157-1187`（`_SECRET_INI_LINE_RE`）
- **证据**：主控独立复跑探针——`mask_credentials('发件人密码(授权码) = SMTP_SECRET_PASS')` **原样返回**（LEAK）；同节 `tgapi令牌`/`pushplus推送token`、`[账号密码]` 节 `sooplive密码`、`web_password`、`xhs_session_sid` 均正常掩码。判据要求凭据词后紧跟 `\s*=`，而该键为「密码(授权码) =」（词后有括号尾缀）。次要实例：`partner_code`（占位性质 P-00001）与「bark推送接口链接」的**路径段型** key（`https://api.day.app/<key>/…`）均不过通用掩码——后者当前由 `msg_push._mask_url(mask_last_segment=True)` 在消费点补掩（Z4 已核 8 处日志点全包装），但任何**新**消费点若只依赖 `mask_credentials` 即漏。
- **影响**：该 SMTP 授权码键（`main.py:5052` 读取）出现在任何过码日志路径时明文落盘——log 侧唯一防线的文档化覆盖面（:1157 注释自称覆盖 Cookie/Authorization/账号密码）对基线模板自带的键失效。
- **建议**：`_SECRET_INI_LINE_RE` 的键名判据允许「凭据词 + 非 `=:` 字符尾缀」，或按整段键名建 ini 专用 alternation；同批补 `tests/test_utils.py` 掩码覆盖语料（含「发件人密码(授权码)」与 bark 路径段型 URL）。
- **修复成本**：极低（一处正则 + 语料）。
- **主控复核**：主控用 venv 解释器独立复跑 10 样本探针，命中与代理回传一致。

### M-11 node 安装器 TOFU 基准读取失败 fail-open，与 ffmpeg 三链的 fail-closed 裁决不一致

- **位置**：`src/node_install.py:219-224`（对照 `src/ffmpeg_install.py:601-621`、`src/ffmpeg_master_download.py:621-652`、`src/ffmpeg_linux_download.py:533-544`）
- **证据**：`except OSError as e: logger.warning("读取 SHA256 缓存失败，跳过校验: …"); return True`——基准文件存在但读不出即放行安装；且 :221 `read_text(encoding="ascii")` 未并捕 UnicodeDecodeError（会穿到外层 except 被归成泛化「安装失败」）。三条 ffmpeg 链同分支已按 SEV-2222/L-44 统一收紧为「删包 + 拒装 + 自救指引」，node 侧同形分支漏改。
- **影响**：「官方清单不可达 ∧ 基准损坏 ∧ 镜像被替换」叠加时，唯一一道完整性检查静默失效，被替换的 node 二进制经 PATH 前置被执行（JS 签名脚本运行时）。
- **建议**：对齐 ffmpeg 侧改法——并捕 `(OSError, UnicodeDecodeError)`、读不出即删包返 False 并带「删除 {hash_file} 后重试」指引。
- **修复成本**：极低（照抄姊妹实现）。
- **主控复核**：实读 :213-232 确认 fail-open 形态；姊妹链对照片段由分区代理逐字比对。

### M-12 两条「官方哈希小文档」读取无字节上限（node 侧 S-12② 已修同族未收敛）

- **位置**：`src/ffmpeg_install.py:484-486`（`response.text` 整份物化 gyan.dev .sha256 文档）、`src/ffmpeg_linux_download.py:435`（`response.json()` 整份物化 GitHub API 应答）
- **证据**：`node_install.py:113-121` 的 `_read_small_document_capped` 已按上轮 S-12② 加上限，注释点名「被投毒的超大响应整份物化进内存」；这两处同族读取无 cap（下载**主链路**均有 512MiB 上限，唯独文档链没有）。
- **影响**：TLS 已被拦截/恶意代理前提下，64 字节端点回 GB 级 200 响应可在启动期耗尽内存。属防御纵深缺口而非直接绕过。
- **建议**：两处复用/对齐 `_read_small_document_capped` 判据，超限按「取不到官方哈希」既有降级口径处理。
- **修复成本**：极低。
- **主控复核**：实读两处 + node 侧对照，确认。

### M-13 standalone 探针异常路径把带签名 token 的完整流地址明文写进日志

- **位置**：`scripts/douyin_live_recorder_standalone.py:279、:300`（异常构造）、`:1674`（落日志）
- **证据**：`raise RuntimeError(f"探针失败: {type(e).__name__}: {e} | url={url}")`（:300，url 原文内嵌）；:1674 `warn(f"流地址校验异常(判定不可达): {strip_query(url)} - …: {e}")`——前缀做了 strip_query，但 `{e}` 里已内嵌完整 url（含 wsSecret/anti_code 等 query token）。同文件 :1866 对「-i 的带 token 流地址」的自我定罪口径与 AGENTS「写入日志前必须脱敏」红线均指向此处应为掩码；主线同路径一律过 `utils.mask_credentials`（`src/stream_select.py:654`、`src/sync_http.py:168`）。
- **影响**：CDN 超时/连接重置（常见）时 token 落入控制台与 `logs/standalone.log`。standalone 是对外分发的独立发行副本，影响面=全部 standalone 用户。
- **建议**：`http_probe`/`http_request` 的 RuntimeError 改嵌 `strip_query(url)`（与 `_fetch_json` :532 一致），或 catch 侧对 `e` 过一层脱敏再落日志。
- **修复成本**：极低。
- **主控复核**：实读 :255-300 与 :1674 传播链，确认。

### M-14 standalone `http_request` 响应体无上限读取，主线 8MB 上限未回灌且未登记刻意差异

- **位置**：`scripts/douyin_live_recorder_standalone.py:262`（对照主线 `src/sync_http.py` / `src/async_http.py` 的 `_MAX_RESPONSE_BYTES = 8*1024*1024`）
- **证据**：`raw = resp.read()` 无任何 cap；消费面 `_probe_hls_segment_lite`（:1474/:1498）拉取 CDN 控制的播放列表正文，本文件 :348-354 自我定级为「不可信输入面」。白名单 #12 要求副本差异「核对是否登记」——`docs/agent-reference/session-learnings.md` 与 known-pitfalls 均无此条，属**未登记漂移**（`scripts/smoke_test.py:41` 上轮已补同值上限并点名主线索量）。
- **影响**：被劫持/异常源可把长跑进程内存打爆。
- **建议**：`http_request` 补块读累计上限（对齐主线 8MB），并在副本头注释登记差异已收敛。
- **修复成本**：极低。
- **主控复核**：实读 :255-266，确认无 cap；主线 cap 常量存在。

### M-15 `MODULE_THRESHOLDS` 两条登记阈值（50）低于全局下限（60），绕过本文件自设的债务治理通道

- **位置**：`scripts/check_coverage.py:57-63`（表）、`:71`（`GLOBAL_FLOOR = 60.0`）、`:56`（治理承诺）、`tests/test_check_coverage.py:120-127`（回归锁只钉总闸）
- **证据**：`"src/spider.py": 50`、`"src/proxy.py": 50`；:56 明文「要放宽必须走 COVERAGE_DEBT / GATE_EXEMPT_MODULES」，而 COVERAGE_DEBT 为空、条目须 tracker+review_by。2026-10-24 GLOBAL_FLOOR 50→60 后这两条静默变成「无 tracker/无到期/不受条数上限约束的债务基线」。实测当前覆盖率 spider 77.1%、proxy 84.8%，暂无实际放宽生效，但这两份**最重要的文件**从此可在 50~60 区间回归而不触发逐模块闸。
- **影响**：为白名单记账化开先例；逐模块闸对 spider/proxy 弱于其余全部模块。
- **建议**：两条登记抬到 ≥60（实测余量充足），并给登记表补「阈值 ≥ GLOBAL_FLOOR 或走债务表」的机检断言。
- **修复成本**：极低。
- **主控复核**：实读 :52-71 与回归锁断言范围，确认。

### M-16 六份 issue 模板的「搜索历史 issue」链接指向**上游** `ihmily/DouyinLiveRecorder`

- **位置**：`.github/ISSUE_TEMPLATE/bug.yml:15`、`bug_en.yml:15`、`feature.yml:15`、`feature_en.yml:15`、`question.yml:15`、`question_en.yml:15`
- **证据**：六处 URL 均为 `https://github.com/ihmily/DouyinLiveRecorder/issues?q=is%3Aissue`。2026-10-04 的归属统一改定（Dockerfile LABEL/compose image/README Releases/CODE_WIKI/Codecov slug → y123ao6）未覆盖 issue 模板；上游原作者署名按既定口径保留在 README「上游项目」行与 main.py 版权头，但「提 issue 前先搜哪里」是功能性路由，不是署名。
- **影响**：用户按提示把检索与报告导向上游仓库，本仓收不到对应反馈；与既定归属方向矛盾。
- **建议**：六处改指 `y123ao6/DouyinLiveRecorder/issues`（可保留一行「上游项目」说明）。
- **修复成本**：极低。
- **主控复核**：grep 全部模板 URL 逐条确认（主控直审区发现）。

### M-17 `get_haixiu_stream_url` 硬编码两段默认 accessToken，与同仓 JS 侧「占位化」口径相左（性质待用户裁定）

- **位置**：`src/spider.py:5911-5920`（对照 `src/javascript/haixiu.js:531-533` 已把同类 accessToken 占位化）
- **证据**：两串双重 URL 编码的 token 作为 env/config 均未配置时的兜底值写死在源码；:5911-5913 注释自称「凭据」「接口鉴权关键，改动会导致 401」。
- **影响**：若系站方公开 app 级 token（上游项目既有默认值）仅缺来源说明；若为会话凭据则属运行时凭据入库。本仓 JS 侧已把同类值占位化，两侧口径不一致。
- **建议**：交用户裁定——（a）补一行来源说明（站方公开 token、上游继承）并维持现状；或（b）外移 config/env 必填、缺省时给出「配置 accessToken」的明确报错。**不得静默删除**（会直接打断该平台解析）。
- **修复成本**：（a）极低；（b）低。
- **主控复核**：实读 :5896-5932 确认硬编码与注释原文；性质判定需平台侧知识，标注待用户裁定。

## 5. 轻微问题（L 组，同族已合并）

> 每族给计数、代表位置与一句话建议；主控对其中安全相邻项（L-01②、L-11 部分）做过实读抽查。

### L-01 spider 解析空值/边界残余族（5 型 12 处）

`src/spider.py:1245-1248`（`codec_key` 用循环变量，循环走完恒为 "h265"，归因字段名失真）、`:3458/:3580/:3838`（`_dig` 缺键回 None 时主播名落成字面量 "None-None"）、`:5981`（VV星球 roomId 缺失仍先发一次 `roomId=None` 请求，判空晚于请求）、`:2411-2417/:5713-5732`（`urlparse().hostname` 无 ValueError 防护，畸形 authority 穿透——孪生实现 `_shopee_is_allowed_host` :152-161 已防护）、`:858-875`（捕获不可能发生的 `JSONDecodeError` 的死防御分支，误导读者以为该处有解析防线）。建议：随下次触碰逐点补判空/对齐 Shopee 写法。

### L-02 用户可控数据未编码直拼请求族（2 型约 20 处）

JSON 请求体字符串拼接 5 处（`spider.py:6506、:4536` 等淘宝/百度/京东，id 含 `"` 即结构破坏）；URL 路径段/查询参数未 percent 编码族（`spider.py:2203、:1833、:5442、:4128-4135` 等约 15 处，段内含 `&`/`#` 即参数走私或截断；仓内 Shopee :6307-6310、知乎 :5758-5760 已是 quote 形态）。建议：查询位一律 `urllib.parse.quote(x, safe="")`、请求体用 `json.dumps`。无 SSRF 外溢（host 恒平台域）。

### L-03 死代码/死赋值/恒真族（9 处）

`main.py` 54 处 `platform = "未知平台"` 中 51 处被无条件覆盖（:1744 为代表）、`host_id` 死全局（:459/:4835）；`src/web_api.py:1254-1256` reauth 回退分支不可达（与 :37-39 不变量注释矛盾）；`src/room.py:44-45/:110-116` `_cached_ttwid` 镜像变量零读取点（spider.py:81/:176-178 同型）；`src/recorder_status.py:86-87/:234` `start_display_time` 零生产读取点且注释失真；`src/async_http.py:742` 恒真条件；`src/stream.py:710` TikTok 回退基准硬编码 `< 4` 与抖音判界口径不一致；`src/gui_qt/settings_dialog.py:115/:132-137` 不可达 except 死防御。建议：删除或加一行「为何保留」注。

### L-04 子进程无 timeout 残余（3 处）

`main.py:4623`（`ffmpeg -version`，挂起即阻塞入口）、`build_exe.py:303`（PyInstaller）、`:2063`（taskkill）。探针其余候选经逐处核销为多行续行/`communicate(timeout=)`/fire-and-forget 形态（Z2/Z9/Z12 卫生扫描）。建议：各补宽松上限。

### L-05 Popen 失败路径的 stderr 临时文件泄漏

`main.py:1117-1132、:1368-1383`：`_ffmpeg_stderr_file` 在 Popen 抛错（ffmpeg 二进制缺失等）时未 close、`_discard_ffmpeg_stderr` 未执行——成功路径 :1135-1137 与 finally 均不覆盖该异常路径，%TEMP% 每次失败残留一个 0 字节 `dlr_ffmpeg_*.log`（句柄由 CPython 引用计数兜底，磁盘文件不清理）。建议：finally 对「process is None」分支补 close + discard。

### L-06 `URL_config.ini` 新建走裸 `open(..., "w")`，权限口径与 config.ini 不一致

`main.py:4916`（对照 :4890-4893 对 config.ini 的「原子写 0600 vs umask 0644」收紧原则）。该文件可含 `user:pass@` 自定义流地址，Linux/Docker 下新建时全局可读。建议：改 `utils.atomic_write_text` 同口径。

### L-07 注释/文档与实现失真族（11 处）

`tests/test_regression_gates.py:458-459`（skip 理由称 config.ini「被 gitignore」——实为已跟踪基线模板）；`src/video_postprocess.py:22-26`（头注释称 `segment_video` 已投线程池，实际为 main.py:148-149 登记的刻意死代码）；`web/motion.js:24-31`（`prefersReduced` 头注释与降级方向相反）；`web/app.js:104-124`（敏感判定注释称「与后端同口径」，实际残留 scheme 门 + 节名大小写两处分叉）；`docker-compose.yaml:109-111`（「强烈建议同时设认证」与 web.py C1 闸门的**强制**语义不一致，照做会重启循环——同文件 :120-123 已是正确口径）；`tests/frontend/test_auth_reauth.py:37-39`（下限注释 13 条 vs 实数 14）；`.coveragerc-concurrency:5`（头部注释写全局阈值 50，pyproject 2026-10-24 起为 60）；`main.py:4881`（注释锚点指向 start_record finally，实际在 `_room_thread_target` finally，见 M-01）；`src/http_config.py:5`（「由 async_http / sync_http / spider 读取」——sync_http 已无生产 importer）；`scripts/compile_po.py`（纯读路径缺 rc=2 兜底，坏 .po 以 rc=1 裸栈收场，违反自身 :152-153 退出码契约）；`src/config_io.py:385-386`（ImportError 分支静默返回未脱敏原文，违背同函数 :373「必须显式告警」自述）。建议：按「修改注释只增不改」逐处补正。

### L-08 gui.py 专项（3 项）

`:4078-4083` loguru 前缀剥离 `rfind(" | ")` 在主播名含 " | " 时失配，该房间从画质监控表消失且无降级日志；`:2709-2711` URL 配置页文案承诺「点关闭即最小化到托盘」，实际弹对话框且 tkinter 路径无托盘（:4656-4659 恒告警）；10 处 except-pass 无 ±4 行归因（:956/:2473/:2500/:2678/:3209/:3228/:3250/:4634/:4650/:4876，逐处复核均为噪声级，白名单 #4 观察项备案）。建议：前两项随触碰修正；后者下次重构补归因注释。

### L-09 结构度量族（阈值：函数 ≥200 行、嵌套 ≥6 层、形参 ≥9 个）

超长函数 15 个（探针实测）：`main.py::start_record`（796 行）、`check_subprocess`（478）、`main`（722）、`src/web_api.py::create_app`（958）、`update_config`（181）、`src/stream_select.py::_validate_stream_url`（280，9 形参）、`select_source_url`（275）、`src/sync_http.py::sync_req`（205，10 形参）、`src/spider.py` 4 个 150+ 行（get_bilibili_danmaku_info 218 / get_xhs_stream_url 203 / get_taobao_stream_url 193 / get_shopee_stream_url 180）、`gui.py::__init__`（203）、`src/gui_qt/theme.py::build_stylesheet`（静态 QSS 模板，核销为刻意形态）等；深嵌套 ≥6 层 30 处、≥9 形参 10 处（msg_push send_email/bark/ntfy 10/11/13 形参）。建议：维持上轮口径——不单独造大 diff，随重构顺势拆分；XHS/Shopee/知乎三处同构「短链落地页双闸校验」优先抽公共 helper。

### L-10 web 前端稳健性族（3 项）

`web/app.js:241-257` `api()` 超时只护到响应头，`resp.text()` 无界（头回体挂起则该轮询链静默停摆——`downloadFile` 同形态是 :1898-1900 登记的刻意放行，api() 无此说明）；`:1115-1153` 日志/弹幕两条轮询链失败无退避（与状态链 `SSE_BACKOFF_STEPS` 口径分叉，后端宕机时 2s/5s 节拍无限重试）；`:1734-1835` `saveConfig` 无代次防护（保存中途切视图重进会让旧 input 快照继续提交，最终收敛到服务端真值、无配置损坏）。建议：clearTimeout 移到 body 读取后；退避抽成 makePollChain 可选能力；保存循环加 `configChain.isCurrent` 复核。

### L-11 安装器/门禁/脚本边角（11 项）

`src/collector.py:255-264` stop() 对从未注册的房间上报无主 conn/closed 事件（违反本文件 :180 自述）；`src/node_install.py:48/:344` PATH 注入用导入期快照（ffmpeg 侧 `prepend_to_path_env` 已收口同族）；`src/ffmpeg_master_download.py:863-865` `__main__` 自测块丢弃 ok 响应不关闭；`scripts/check_coverage.py:314`、`scripts/sync_metadata.py:129/:164` 子进程未设 `stdin=DEVNULL`（run_gates.py:311-313 已实证同族 WinError 6 防线）；`scripts/spike_arm64_static_ffmpeg.sh:278` set -e 下命令替换失败静默中止、丢验收诊断出口；`scripts/check_version.py:60` 版本锚点只匹配带注解形态；`src/config_io.py:45` `update_file` 注解 `str | None` 但全部出口恒返回 str；`src/utils.py:359` `run_node_script_async` 用默认线程池与 :207-214 自有池论证不一致且无注；`src/stream_select.py:988-1017` m3u8 Range-GET 循环异常不重试（与 `_confirm_get_ok` 「偶发超时重试一次」口径不一致，同网络抖动下 FLV 有重试、HLS 没有）；`scripts/run_gates.py:152/:171` 参数名拼写 `agants_path`（应为 agents_path，文件内自洽无功能影响）；`scripts/douyin_live_recorder_standalone.py` 上轮 M-24 的孪生漂移仍未回灌登记（`:1202` rid 正则与主线 :1590 锚定形态、`:948` h265 剔除口径差异——10-29 已列 P3，此处备案现状）。

### L-12 Qt/UI 边角（3 项）

`src/gui_qt/shared.py:330-332` `SetConsoleCtrlHandler` 返回值未检查，注册失败时 CTRL_BREAK 广播可命中 GUI 自身；`src/gui_qt/pages/danmaku.py:200-258` 房间移除后筛选复位不触发弹幕流重绘，旧房间消息残留显示；`src/ui_motion.py:83` 与 `main.py:57` 全仓仅存的两处 `ctypes.windll` 惯例漂移（AGENTS「统一走 `ctypes.WinDLL`」；`src/ui_kit.py`/`web.py` 已迁移）。建议：第一处检查返回值；第三处随触碰迁移。

### L-13 tests 全量 suite 拖慢项（1 族）

`tests/test_regression_infra.py:661-664、:699-703` 两条用例含 10s + 3s 真实睡眠（全 tests/ 仅有的 >1s 真实睡眠；fake 终止时长只需超过被收窄的 1.0s 预算）。降到 2s 量级可提速全量 suite 约 10s 且语义不变。

### L-14 typings/execjs 存根与 PyExecJS 1.5.1 漂移（4 签名 + 1 备案）

`typings/execjs/__init__.pyi:27/:28/:30/:20`（`get()` 缺参、`get_from_environment` 多参、`runtimes()` 返回类型、构造器参数序——同包 `_runtimes.pyi` 经核与上游逐字一致，本文件未同步）；`:24` `compile` 返回 `ExternalRuntime`（上游为 Context，存根头自述的刻意简化，备案）。主运行时 exejs 1.0.1 自带 py.typed，PyExecJS 仅回退分支，今天不受影响；但存根是 mypy 裁定面，失配会误拒/误放。建议：对齐 `_runtimes.pyi`。

### L-15 `_tars.py` STRING4 分支未过 `_need`，截断帧抛 struct.error（残留登记的第 4 处同族）

`src/platforms/_tars.py:84`（探针实测 `TarsInputStream(b'\x17\x00')._skip(7)` 抛 struct.error）；`tests/test_tars_frames.py:20-23` 登记只列 3 处。平台侧 `except Exception` 吸收、无挂死（C5 口径不变），但「畸形帧降级为 ValueError」的统一承诺在此未兑现且登记未含它。建议：补 `self._need(4)` 或把该位置补进登记与用例。

### L-16 CI 与杂项（5 项）

`ci.yml:567-576、:769-782` 「Gate pytest warnings summary」**二次全量跑 pytest**（第一次带覆盖率运行的输出已含 warnings summary，可直接 tee 复用）——test job（timeout 25min）最重路径的运行时长与 flake 暴露面双倍；`.github/actions/retry` 与各 job 结构、Secrets 最小化、provenance=false 等均核销无发现；`StopRecording.vbs:438-440` killTree 分支 WMI 失败回退 taskkill 无身份复核（killTree=False 分支 :449 已补 M-85 复核，同文件内口径不一）；根 `index.html:164-169/:210/:248` 独立播放器页 httpToHttps 强制升级弄坏局域网纯 HTTP 流、CDN 失败时点击播放抛未捕获 ReferenceError（上游遗留形态，页面自我定位为本地双击使用）；`DouyinLiveRecorder.spec:53-57` 提交态 icon 为生成机绝对路径（build_exe.py 自动生成物，正常路径每次重生成，备案）；`src/stream_select.py:479-506` 派生跳离线闸门与 web_config 判据未共用同一份（`_aton_part` 为第二份 inet_aton 模拟——残余面已在 `async_http.py:618-621` 登记，建议改调 `web_config.offline_internal_reason` 删除副本）。

## 6. 逐文件问题索引

> 「L-xx/M-xx」为条目编号；「备案」= 核销/观察项。区域顺序与 §2.1 相同。

| 文件 | 条目 |
| --- | --- |
| `main.py` | M-01、L-03、L-04、L-05、L-06、L-07（:4881 锚点）、L-09、L-12（windll） |
| `gui.py` | L-08（3 项）、L-09 |
| `build_exe.py` | M-05、M-06、M-07、L-04 |
| `StopRecording.vbs` | L-16（killTree 身份复核） |
| `DouyinLiveRecorder.spec` | L-16（icon 绝对路径，备案） |
| `i18n.py` / `web.py` / `msg_push.py` | 无发现（S-07 修复面经 Z4 复核完好；web.py 的 open/WinDLL/闸门均核销） |
| `index.html`（根） | L-16（https 强升/CDN） |
| `src/spider.py` | M-02、M-03、M-04、M-17、L-01（5 型）、L-02（2 型）、L-03（_cached_ttwid 同型）、L-09 |
| `src/room.py` | M-04、L-03 |
| `src/stream_select.py` | M-04（间接判据面）、L-11（Range-GET）、L-16（aton 第二实现）、L-09 |
| `src/stream.py` | L-03（TikTok `<4`） |
| `src/utils.py` | M-10、L-11（to_thread 池注） |
| `src/async_http.py` | L-03（恒真条件） |
| `src/sync_http.py` | L-09（sync_req 结构）、备案（except-pass ×2 归因距离） |
| `src/ws_client.py` / `src/proxy.py` / `src/cookie_cache.py` / `src/ttwid.py` / `src/http_config.py` | 无发现（cookie 缓存纯内存、brotli 限长接线、退避封顶均核销；http_config.py:5 见 L-07） |
| `src/config_io.py` | L-07（ImportError 静默）、L-11（update_file 注解） |
| `src/config_read.py` / `src/config_bool.py` | 无发现 |
| `src/web_api.py` | M-08、M-09、L-03（reauth 死分支）、L-07（无）、L-09（create_app/update_config）、备案（except-pass :493） |
| `src/web_config.py` | 无发现（容错解析器/三态写回/掩码棘轮经 Z5 全面核对完好；深嵌套备案） |
| `src/web_models.py` | 无发现 |
| `src/web_tray.py` | 无发现（`os._exit` 白名单 #3） |
| `src/recorder_status.py` | L-03、L-07（:86-87 注释） |
| `src/srt_writer.py` | 无发现（open 形态为受管生命周期，Z6 核销） |
| `src/video_postprocess.py` | L-07（头注释） |
| `src/collector.py` | L-11（无主事件） |
| `src/scheduler.py` / `src/danmaku_monitor.py` / `src/notify.py` / `src/logger.py` / `src/log_archive.py` / `src/startup_cleanup.py` / `src/base.py` / `src/__init__.py` | 无发现（调度器容量/租约/握手、danmaku fd、notify shlex+超时、logger 轮转竞态、归档锁逐项核销） |
| `src/node_install.py` | M-11、L-11（PATH 快照） |
| `src/ffmpeg_install.py` | M-12、L-09（深嵌套备案） |
| `src/ffmpeg_master_download.py` | L-11（`__main__` 泄漏） |
| `src/ffmpeg_linux_download.py` | M-12 |
| `src/ffmpeg_proc.py` | 无发现（三级回退链完整，Z8 实读核销） |
| `src/ui_motion.py` | L-12（windll） |
| `src/gui_qt/shared.py` | L-12（SetConsoleCtrlHandler） |
| `src/gui_qt/pages/danmaku.py` | L-12（筛选复位） |
| `src/gui_qt/settings_dialog.py` | L-03（死防御） |
| `src/gui_qt/` 其余（app/main_window/recorder/theme/tray/widgets/quality_monitor 等） | 无发现（线程纪律 5 信号、QTimer 归属、29 处 connect 一次性、QSS/富文本注入面 0、契约逐字段对齐均核销） |
| `src/ui_fonts.py` / `src/ui_i18n.py` / `src/ui_icons.py` / `src/ui_kit.py` / `src/ui_scale.py` / `src/ui_theme.py` | 无发现（except-pass 形态均在白名单 #4/#17 口径内核销） |
| `src/platforms/_tars.py` | L-15 |
| `src/platforms/` 其余 7 文件 | 无发现（WS 生命周期/畸形包容错/注册表=平台清单一致性核销） |
| `src/proto/` | 无发现（gencode 4.25.3 与 protobuf<8 约束一致，.pyi round-trip 通过） |
| `typings/execjs/` | L-14 |
| `src/javascript/*.js`（4 个非压缩脚本） | 无发现（console 调试残留 0、契约与调用侧全对齐、钉定 5/5） |
| `web/app.js` | L-07（敏感判定注释）、L-10（3 项） |
| `web/index.html` / `web/style.css` / `web/motion.js` | L-07（motion 注释）、无发现（XSS 面：innerHTML 11 处全转义、内联事件 0） |
| `scripts/agent_hook_guard.py` | 无发现（括号枚举完好、fail-open 语义闭合） |
| `scripts/run_gates.py` | L-11（agants_path 拼写） |
| `scripts/check_coverage.py` | M-15、L-11（stdin=DEVNULL） |
| `scripts/compile_po.py` | L-07（rc 契约） |
| `scripts/sync_metadata.py` | L-11（stdin=DEVNULL） |
| `scripts/check_version.py` | L-11（锚点形态） |
| `scripts/douyin_live_recorder_standalone.py` | M-13、M-14、L-11（M-24 漂移备案） |
| `scripts/spike_arm64_static_ffmpeg.sh` | L-11（set -e 静默中止） |
| `scripts/_ci_web_smoke.sh` / `scripts/smoke_test.py` / `scripts/check_runtime_pins.py` / `scripts/check_workflow_constants.py` / `scripts/check_skill_agents_consistency.py` / `scripts/check_annotations.py` / `scripts/extract_i18n_strings.py` / `scripts/report_bundle_size.py` / `scripts/sync_version.py` | 无发现（退出码透传 0/1/2、钉定三态、常量一致性逐项核销） |
| `tests/test_regression_gates.py` | L-07（skip 理由）、L-13 的锁内文件核对（无悬空锁） |
| `tests/test_regression_infra.py` | L-13（10s+3s 睡眠） |
| `tests/test_utils.py` / `tests/test_agent_hook_guard.py` / `tests/test_test_hygiene.py` | 无发现（钉定 4 锁、括号形态锁、R1-R11 双向机检全部有效） |
| `tests/frontend/`（4 mjs + 2 py 包装） | L-07（auth_reauth 计数）、登记面/断言质量/选择器同源无发现 |
| `tests/` 其余约 160 文件 | 仅由 11 项判据扫描覆盖（结果见 T1 卫生扫描：M-32/M-33 现状备案、恒真断言 0、全局状态泄漏 0） |
| `.github/workflows/ci.yml` | L-16（warnings 双跑） |
| `.github/workflows/build-release.yml` / `docker-publish.yml` / `trivy.yml` / `issue-translator.yml` / `.github/actions/retry/action.yml` | 无发现（凭据最小化、SHA 钉定、QUARANTINE 语义、fail-fast 语义逐项核销） |
| `.github/ISSUE_TEMPLATE/*.yml`（6 文件） | M-16 |
| `pyproject.toml` / `requirements.txt` / `Dockerfile` / `docker-compose.yaml` | L-07（compose :109-111）；依赖清单/镜像/卷挂载同源对账无发现 |
| `.gitignore` / `.dockerignore` / `.gitattributes` / `.pre-commit-config.yaml` / `pyrightconfig.json` / `.coveragerc-concurrency` | L-07（coveragerc 50→60）；同源锁族其余核对无发现 |
| `config/config.ini` / `config/URL_config.ini` | 无发现（基线模板全敏感键空值、web_host=127.0.0.1；URL_config 15 行全注释；跟踪态破口见 §7.1 M-23） |

## 7. 结论性核对

### 7.1 上一轮（2026-10-29）遗留项核对

| 上轮项 | 当前真实状态 | 依据（本轮实测） |
| --- | --- | --- |
| S-01 HEAD 899 冲突块 | **已终结**：提交 `664a026` 完成解决收口 | `git grep -c '^<<<<<<< ' HEAD` 0 命中；AST 0 失败 |
| S-02 liveme.js 钉定失配 | **已修** | 钉定对账 5/5 True（utils._JS_SHA256_EXPECTED vs 盘上字节） |
| S-03 index.html 孤立闭合标签 | **已修** | 盘上首行 `<!DOCTYPE html>`、`</body>` 恰 1 处（:207） |
| S-04 read_web_config strict 崩口 | **已修** | `src/web_config.py:30-31` 读取侧统一容错解析器（strict=False）注释与实现一致 |
| S-05 三处自建 AsyncClient | **未收敛（P2 待办仍开）** → 本轮 M-04 | room.py:150/:256、spider.py:4026 三处形态原样 |
| S-06 Windows 优雅退出不可达 | **已修** | `main.py:1128` stdin=PIPE；`ffmpeg_proc` 写 q→close→terminate→kill 三级回退链经 Z8 实读无洞；main.py 六条退出路径均 unregister |
| S-07 推送凭据明文入日志 | **已修** | msg_push `_mask_url`/`mask_credentials` 在位，8 处 logger 全部包装（Z4 逐处核对） |
| M-01 悬空回归锁引用 46 处 | **46 → 5**：3 处为 tests 文件头注释旧名（`tests/test_regression_gui.py:1`、`test_regression_gui_output_chain.py:1`、`test_regression_postprocess.py:1`），2 处在 `.agents/` 技能文档（`comment-refactor-at-scale/.../SKILL.md:121` 示例命令、`dlr-dev-playbook/references/known-pitfalls.md:29` 指向已改名的锁文件，同句引用的 `test_sync_probe_internal_guard.py` 实存） | 本轮 grep 实测 |
| M-02/M-03/M-05（约束文本/模块头/Skill 同源） | M-05 已修（check_skill_agents_consistency 为 CI static 步骤，本地 rc=0）；M-02/M-03 未逐项复核 | 门禁实跑 |
| M-04 两条 Qt 用例回植 | **已修** | `test_gui_qt_settings_dialog.py:20-22`、`test_gui_qt_units.py:33-40` 均带 `exc_type=ImportError` |
| M-08 CI 下限条数守卫 | **已修** | `ci.yml:367-371` 改为与 pyproject 依赖数相等断言 |
| M-09 触发器与文档矛盾 | **已修** | ci.yml 全文改 workflow_dispatch-only，历史注完整 |
| M-10 JS 字节对账用例 | **已修** | `tests/test_utils.py` 钉定 4 锁（键集合/双向盘表/字节级），5/5 实测 |
| M-12 compile_po `errors=` | **已修** | `scripts/compile_po.py:137-138` |
| M-13 hook 误拦与 fail-open 覆盖 | **已修** | `agent_hook_guard.py:757-762` fail-open 语义闭合（Z12 核销） |
| M-16 冒烟回环覆盖窗口 | 未逐项复核 | — |
| M-23 `.zcode/`、`URL_config.ini` 跟踪态 | **未处置（交回用户的两项原样）** | `git ls-files` 命中 `.zcode/config.json`（内容为无害的插件开关，但属本地工具配置）与 `config/URL_config.ini`（当前 15 行全注释；一旦用户本地填入真实地址，`git add .` 即会带凭据入库） |
| M-24 standalone 孪生漂移 | **仍存在且未登记**（P3 待办原样） | Z12 对照实测（rid 正则、h265 剔除口径） |
| M-26 画质写回假成功 | **已修** | `update_or_append_config_line` 三态 + `change_room_quality` 写后重解析裁决；「写失败但返回成功」形态实测 0 残留（Z5） |
| M-32/M-33 平台 skip 与 sys.platform 形态（12 处） | **维持原形态（P2 待办）** | T1 全量扫描逐点定位（8 处 monkeypatch + 5 处 skipif） |
| M-34 两处 importorskip 漏改 | **已修** | 见 M-04 行 |

### 7.2 被推翻/收回的断言（方法学透明）

| 断言 | 主控复核实测 | 处理 |
| --- | --- | --- |
| 主控侧初判「根 `index.html` 无生产消费方，属孤儿死文件」 | Z4 读其文件头（:16-18「本地双击打开的独立播放器」）与 `.dockerignore:126` 的刻意排除项——该页是有自我定位的独立辅助页，非孤儿 | **收回**；仅保留 L-16 的功能性问题（https 强升/CDN） |
| AST 探针「main.py 10+ 处疑似未用 import」 | Z1 逐个核销：`get_status`/`_validate_stream_url`/`_run_ffmpeg_checked` 为 :111-152 注释登记的再导出形态（tests 消费），**真未用 import 0 处** | 探针命中不采纳（核销台账的一部分） |
| AST 探针「main.py 2 处 subprocess 无 timeout」 | 实测 1 真 1 误报（Popen 无 timeout 形参属 API 不适用） | 采纳为 L-04 的 main.py:4623 单点 |
| AST 探针「42 处 except-pass 无归因」 | 逐处分区核销后需升级 0 处：全部为白名单 #4 形态（有归因/不改返回值/清理路径）；仅 gui.py 10 处、web_api 1 处、sync_http/cookie_cache/utils 若干处保留「补归因注释」备案（L-08/L-07） | 观察项备案 |
| Z5 子代理对 M-08 的「中等」定级 | 主控评估升格「严重」后否决——利用前置（合法会话或显式非回环暴露）拦住默认形态 | 维持中等，裁决理由记 §3；修复优先级列 P0 首位 |
| Z10 越界项「spider.py 硬编码 accessToken 属运行时凭据入库」 | 主控实读确认硬编码存在，但性质（站方公开 app token vs 会话凭据）无法静态判定，且上游继承 + 可外部覆盖 | 采纳为 M-17，标注「待用户裁定」，不预设为泄露 |

### 7.3 审查期内被并发工作包修复的项

**无。** 审查全程工作区 0 未提交改动，快照两次复比 PASS（§8.3 判据 10）；无并发包。

### 7.4 全仓健康度横向结论

1. **注入与危险原语面**：`eval(`/`exec(`/`pickle`/`yaml.load(`/`os.system` 在生产 Python 代码实测 **0 处**（命中仅 Qt `.exec()` 事件循环、`x-bogus.js` 白名单 `eval`、typings 声明）；`shell=True` 仅 `run_gates.py` 受控退化形态且 argv 优先链闭合；`notify.py`/`utils.py` 对 taskkill 明令 argv 列表并带禁止性注释；前端 `innerHTML` 11 处全经 `esc()`/`textContent`、内联事件 0、QSS/富文本注入面 0（M-23 的 `dropped` 亦有行为锁）。**与上轮同结论：注入面干净。**
2. **凭据面**：`config/config.ini` 基线模板全敏感键为空值、`web_host = 127.0.0.1`；`config/URL_config.ini` 跟踪态 15 行全注释；硬编码凭据字面量扫描 0 命中（M-17 的 haixiu token 为唯一待裁定项）。剩余风险全部在**日志侧覆盖缺口**：M-10（发件人密码(授权码) 键）、M-13（standalone 异常路径）。
3. **反序列化/外部数据**：`_tars` 手写解码器已知残留 3 类登记仍成立、本轮补报第 4 处同族（L-15，均无挂死/越界）；protobuf 畸形帧只丢包；brotli 限长解压接线于消费点、裸解压 0 处；响应体上限在主线全读点 0 旁路（缺口集中在 standalone 与两条文档链，M-12/M-14）。
4. **并发与资源**：模块级 `asyncio.Lock/Queue/Semaphore` 单例 0 处（唯一 `ws_client.py:188` 为实例属性级）；跨 await 凭据锁为 `RLock`；调度器容量钳制/租约/握手、collector stop 幂等、`_shutdown` 的 `wait_for` 逐项实读成立；GUI 两套（Tk/Qt）跨线程 UI 交互均经队列/信号，直触控件 0 处。真实资源问题仅 M-01（序号登记表）与 L-05（stderr 临时文件），量级小。
5. **静态门禁面**：§1.2 第 4 条全清单 rc=0；工具版本与 CI consts 同值（本地口径）。**但**门禁自证有两处弱化点：M-15（逐模块阈值登记失治）与 L-16（warnings 门禁二次全量跑的冗余形态）。
6. **文档同源性**：本轮「事实源与代码互相说谎」族收敛到 11 处轻微（L-07）+ 3 处中等（M-05/M-06/M-07 全在打包面）——较上轮（S-01/S-02/S-04 级）显著收敛，剩余形态全部是「注释承诺强于实现」的小范围失真，无结构性说谎。

## 8. 改进建议与修复优先级

### 8.1 优先级矩阵（按「风险 × 修复成本」排序）

| 优先级 | 项 | 风险若不动 | 修复成本 | 说明 |
| --- | --- | --- | --- | --- |
| **P0（本批先修）** | M-08（web_tray_icon 文件读链）+ M-09（toggle_room 假成功）+ M-10（发件人密码(授权码) 掩码缺口）+ M-13/M-14（standalone 两处） | 掩码棘轮被绕开的面板文件读链；「已启用」假象；SMTP 授权码与流地址 token 落盘 | 全部极低（正则 +1 键、黑名单 +1 行、读取侧复用既有校验、异常文本改 strip_query、响应体加 cap） | 五条全是单点小改；M-08 建议两道防线同批落地并补回归锁 |
| **P1（高危缺陷，随批修）** | M-01（序号回滚）、M-02/M-03（AcFun/B站解析静默失败）、M-11/M-12（安装器完整性）、M-05/M-06/M-07（打包/发布面） | 7×24 慢速泄漏；平台「永远未开播」难排查；被替换二进制可装；发布模板失文档、审计行失真 | 低（M-06 需行级重写+用例锁，中低） | M-02/M-03 是用户可感知的解析质量问题，回归锁须覆盖「缺键/null 两种降级形态」 |
| **P2（防线与治理）** | M-04（三处 AsyncClient 收敛，上轮 S-05）、M-15（阈值登记 ≥GLOBAL_FLOOR 机检）、M-16（issue 模板链接）、M-17（haixiu token 裁定）、M-23/M-32/M-33/M-24（上轮遗留） | SSRF「不建连」语义缺口；spider/proxy 在 50~60 区间回归不报；用户导向上游仓库 | 低-中（M-04 需三处改写+结构锁） | M-17 与 M-23 的两个子项是**用户决定项**，先裁定再动 |
| **P3（质量与可读性）** | L-01～L-16 全部；超长函数拆分（start_record/create_app/_validate_stream_url 三处优先） | 可读性/维护成本/少量资源泄漏 | 低→中（多可随重构顺势做） | 维持上轮口径：动到哪条链补哪条锁，不单独造大 diff |

### 8.2 流程性建议（防同类问题再生）

1. **「主线修、镜像面漏改」的机检**：本轮 4 条中等（M-11/M-12/M-13/M-14）全部是「同一防线主线已修、standalone/node 侧未回灌」。建议把 standalone 纳入既有的同源机检面：对 `scripts/douyin_live_recorder_standalone.py` 与主线做关键防线特征差集（响应体 cap 常量、mask 调用点计数、探针异常文本形态），差集变化即判红或强制在副本头登记。node_install 对 ffmpeg 三链的同型分支同理（可先做成 tests 内的结构断言而非独立工具）。
2. **「注释承诺」必须有行为锁**：M-05/M-06 的共同形态是函数头声称 X（「显式覆盖为回环地址」「保留注释」），实现为非 X。建议约定：凡注释含「保留/覆盖/必须」等承诺词的打包/发布函数，须有断言该承诺的用例（对 `_sanitized_config_text` 补「输出含注释」用例即可同时修 M-06 与防回归）。
3. **MODULE_THRESHOLDS 登记约束入机检**：给 `check_coverage.py` 补「登记阈值 ≥ GLOBAL_FLOOR，否则必须在 COVERAGE_DEBT」的自检断言（M-15 的建议 ②），防止下一次抬总闸再次静默制造债务基线。
4. **新日志行引入 URL 的统一审查点**：M-13 的根因是异常消息拼 URL 的 helper 被两处复用。建议在 `check_annotations.py`（或独立判据）里加一条「`raise`/`logger` 文本含 `url={url}` 或 `{e}` 且函数签名含 url 参数」的提示级扫描，命中人工复核——误报可接受，漏报不可接受。

### 8.3 可复跑判据清单（供开发与运维复核）

```bash
# 1) 冲突块（期望 0；实测 0）
git grep -c '^<<<<<<< ' HEAD; git grep -c '^<<<<<<< '

# 2) 同源锁族门禁（期望全部 rc=0；实测 0）
PYTHONUTF8=1 .venv/Scripts/python.exe scripts/check_annotations.py; echo $?
PYTHONUTF8=1 .venv/Scripts/python.exe scripts/compile_po.py --check; echo $?
PYTHONUTF8=1 .venv/Scripts/python.exe scripts/check_version.py; echo $?
PYTHONUTF8=1 .venv/Scripts/python.exe scripts/check_runtime_pins.py; echo $?
PYTHONUTF8=1 .venv/Scripts/python.exe scripts/check_skill_agents_consistency.py; echo $?
PYTHONUTF8=1 .venv/Scripts/python.exe scripts/check_coverage.py; echo $?
PYTHONUTF8=1 .venv/Scripts/python.exe scripts/check_workflow_constants.py; echo $?

# 3) black / isort / mypy 三跑 / basedpyright（期望全 rc=0；实测 0/0/0×3/0e0w）
PYTHONUTF8=1 .venv/Scripts/python.exe -m black --check --line-length 120 --target-version py314 .; echo $?
PYTHONUTF8=1 .venv/Scripts/python.exe -m isort --check-only --profile black --line-length 120 .; echo $?
PYTHONUTF8=1 .venv/Scripts/python.exe -m mypy; PYTHONUTF8=1 .venv/Scripts/python.exe -m mypy --platform linux; PYTHONUTF8=1 .venv/Scripts/python.exe -m mypy --platform win32
basedpyright

# 4) JS 钉定对账（期望 5/5 True；实测 5/5）
PYTHONUTF8=1 .venv/Scripts/python.exe -c "import sys,hashlib,pathlib;sys.path.insert(0,'.');from src import utils;[print(n,hashlib.sha256((pathlib.Path('src/javascript')/n).read_bytes()).hexdigest()==e) for n,e in sorted(utils._JS_SHA256_EXPECTED.items())]"

# 5) 同源锁族定点 pytest（期望全 passed；实测 14 passed）
PYTHONUTF8=1 .venv/Scripts/python.exe -m pytest -q -p no:cacheprovider --no-cov tests/test_i18n_migration.py tests/test_i18n_catalog_coverage.py tests/test_ci_frontend_registration.py

# 6) M-10 掩码缺口探针（期望修复后输出含 ***；本轮实测原样返回）
PYTHONUTF8=1 .venv/Scripts/python.exe -c "import sys;sys.path.insert(0,'.');from src.utils import mask_credentials;print(mask_credentials('发件人密码(授权码) = X'))"

# 7) 悬空回归锁引用（期望 0；本轮实测 5，明细见 §7.1）
git grep -nE 'test_regression_2026_(09_22|09_29|10_18|10_21)_[a-z_]+\.py' -- . ':(exclude)CODE_WIKI.md' ':(exclude)CODE_WIKI_EN.md' ':(exclude)docs/changelog/*' ':(exclude).agents'

# 8) M-15 阈值治理（期望无 <GLOBAL_FLOOR 的登记项；实测 2 条：spider.py/proxy.py = 50）
PYTHONUTF8=1 .venv/Scripts/python.exe -c "import sys;sys.path.insert(0,'scripts');import check_coverage as c;print({k:v for k,v in c.MODULE_THRESHOLDS.items() if v < c.GLOBAL_FLOOR})"

# 9) M-16 上游链接（期望 0；实测 6）
grep -rn "ihmily/DouyinLiveRecorder/issues" .github/ISSUE_TEMPLATE/

# 10) 只读自证（期望 CHANGED=0 REMOVED=0 ADDED=报告 PASS；收尾实测 PASS）
.venv/Scripts/python.exe .agents/skills/code-review-lifecycle/scripts/repo_review_snapshot.py verify \
  --manifest "%TEMP%/dlr-review-snapshot-20261030T154623Z/manifest.json" \
  --allow-added docs/worklog/CODE_REVIEW_2026-10-30.md
```

## 9. 总结与后续行动项

**结论**：本轮未发现严重级问题——上轮的冲突态劣化已全部收口，注入面、凭据入库面、并发模型、钉定防线与掩码棘轮主体经逐行核对全部成立。剩余风险高度集中在一种形态：**同一道防线的「镜像面」未随主线收敛**（standalone 副本、node 安装器、mask 键名判据、打包冒烟注释），外加两条 Web 写路径的条件性假成功/绕过（M-08/M-09）。这类问题的修复成本全部为低，且相互独立、可并行整改；完成 P0+P1 后，本仓的静态质量面预计回到「无已知中等项」状态。

**行动项（建议按序执行）**

1. 【P0】修 M-08（`web_tray_icon` 入危险键 + favicon 读取侧魔数校验）、M-09（toggle_room 前缀解析 + 语义验证）、M-10（`_SECRET_INI_LINE_RE` 尾缀 + 掩码语料）、M-13/M-14（standalone 异常脱敏 + 响应体 cap），各带回归锁；同批跑一次全量 pytest 确认无连带。
2. 【P1】修 M-01/M-02/M-03/M-05/M-06/M-07/M-11/M-12；其中 M-06 需行级重写 `_sanitized_config_text` 并补「输出含注释」用例，M-05 修后须以「模板临时改 0.0.0.0」验证子进程真读到补丁值（涉及打包链，完成定义第 2 条的真机验证不可豁免）。
3. 【P2】收敛 M-04 三处直建客户端并补结构锁；M-15 抬登记值 + 自检断言；M-16 六处模板链接；M-17 与 M-23（`.zcode/config.json` 摘除、`URL_config.ini` 索引摘除）三项**先交用户裁定**再动；上轮遗留 M-32/M-33/M-24 按既定方案继续。
4. 【P3】L 组按 §5 逐条随重构消化；三个超长函数（`start_record`/`create_app`/`_validate_stream_url`）在下一条新功能落地前先做纯拆分。
5. 【未执行项声明】① 未跑全量 pytest（只跑 14 条同源锁族定点用例：只读边界下避免覆盖率产物与 `.pytest_cache`；全量结论留给整改轮）；② 未做任何真机/真实 URL 验证（M-05 的子进程读配置时序、M-08 的端到端文件读、M-09 的真实面板操作为静态推定+代码结构实证，标注待确认）；③ 未联网核对 CI 实跑（CI 仅手动触发），门禁结论为本地口径、工具版本已与 consts 逐值核对；④ `CODE_WIKI.md`/`CODE_WIKI_EN.md` 更新日志未追加本次审查（只读边界：本报告是唯一新增仓库文件，日志条目建议随 P0 整改批一并落库）。以上四项分别是 P0/P1 整改的验收前置动作。

---

## 附录 A：方法与覆盖的诚实边界

- **逐行精读覆盖**：13 个分区代理合计完整实读约 68,000 行——根入口 7 文件（main/gui/build_exe/vbs/spec/i18n/msg_push/web/index.html）、`src/` 顶层 43 文件、`src/gui_qt/` 17 文件、`src/platforms/` 8 文件（liveme/haixiu 中段混淆体只扫不精读）、`src/proto/`（gencode 标注 + `.pyi` 抽查）、`src/javascript/` 4 脚本（x-bogus/migu 全行，crypto-js 排除）、`web/` 4 文件、`scripts/` 17 文件、`typings/` 12 文件、CI/构建/配置 20 文件、`tests/` 关键 4 文件（4380 行）+ frontend 6 文件。主控另直审 `.github/` 全部 6 份 workflow/action + 根配置 8 份 + config 模板。
- **模式扫描覆盖**：全部 258 个 `.py`（AST 判据 + 结构度量）+ 生产面危险原语 grep + tests 11 项判据全量扫描（含 3 个 AST 探针）+ 全部跟踪文件悬空引用普查。
- **未逐行精读**：`tests/` 约 160 个测试文件（约 7 万行）仅由判据扫描与锁族实跑覆盖；`douyin.proto` 逐行（字段级抽查 12+）；liveme/haixiu 中段第三方混淆体；`i18n/*` 目录正文（键集合经 14 条锁族用例覆盖）；`coverage.xml`（只作 M-15 读数来源）。
- **行号基准**：全部行号以 2026-10-30 快照（HEAD `664a026`、工作区 0 改动）实测为准；审查期内无并发改动（两次快照复比 PASS），行号不存在漂移风险；复核请先跑 §8.3 判据 10 确认工作区仍与基线一致。
- **审查限制**：并发上限实测 2（首次 3 并发触发 user concurrency limit，Z2 首派失败后重派成功，无覆盖缺口）；子代理回传的 20 条上限使个别分区（spider/gui）的低价值观察被同族合并，未丢失中等以上信息。
