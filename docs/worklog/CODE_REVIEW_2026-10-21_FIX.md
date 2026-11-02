# CODE_REVIEW_2026-10-21 整改执行记录

> 本文是对 [`CODE_REVIEW_2026-10-21.md`](CODE_REVIEW_2026-10-21.md) 的整改执行留痕。
> 报告本身未作任何修改（它是审查快照）；整改结论、验证命令与遗留项全部记录在本文件。
>
> **后续**：本文第 4~6 节的遗留项在第二轮整改后已重新核对，逐条锚点、阻塞原因与验收判据见
> [`CODE_REVIEW_2026-10-21_MANUAL.md`](CODE_REVIEW_2026-10-21_MANUAL.md)。

## 0. 执行摘要

| 维度 | 结果 |
| --- | --- |
| 报告条目总数 | 130 项（严重 16 / 中等 104 / 轻微 10 类） |
| 本轮已修复 | **严重 15 项全修 + 严重 1 项部分修（S-14）+ 中等 28 项** |
| 待人工确认 | 26 项（报告描述为「多处」或无法唯一定位，按第 2 步要求不猜测改动） |
| 明确未实施 | 61 项（原并行工作包会话中断，未落到代码） |
| 静态门禁 | `scripts/run_gates.py` **10/10 全绿** |
| pytest | 4645 passed / 8 failed / 14 skipped；8 个失败**全部为本机环境缺失**（无真实 WSL bash），非代码回归 |
| 改动规模 | 35 个文件（含 19 个测试文件）、约 +1900 / −340 行 |

**为什么没有「130 项全部修完」**：原计划按 8 个写入域并行（`main/msg_push`、`spider/platforms`、
`stream/stream_select`、网络层、运行时、安装器、Web、GUI、脚本、测试）。其中 5 个工作包
（运行时、安装器、Web、GUI、脚本/测试专项）在会话中途失败退出，其负责的中等/轻微条目
（M-35~M-50、M-58~M-97、M-99~M-104、L-01~L-10 多数）**未落到代码**。严重项由我全部收口，
中等项在被改动的文件内一并完成。未实施项逐条列在第 5 节，附原因与建议排期。

---

## 1. 条目提取与排序规则（第 1 步）

按报告原有编号、标题、严重级别逐条提取，**先按严重级别从高到低、同级按报告出现顺序**排列：

1. 严重（S-01 → S-16，共 16 项）
2. 中等（M-01 → M-104，共 104 项，报告内已按 11 个模块分节编号）
3. 轻微（L-01 → L-10，共 10 类，每类合并覆盖约 150 处具体位置）

「必须修复的缺陷」与「可选建议」的区分按报告 §2.3 严重度判定口径执行：

- **必须修复**：严重 16 项（可远程利用的安全问题、正常路径功能失效/数据丢失、确定性资源耗尽、
  测试恒绿掩盖回归）。
- **按风险排序修复**：中等 104 项中，安全类（M-06/M-12/M-15/M-19/M-29/M-30/M-34/M-41/M-44/
  M-51/M-57/M-58/M-59/M-61/M-64/M-66/M-75/M-84/M-85/M-87/M-95/M-96/M-97/M-98/M-99）为必须修复；
  其余（逻辑/资源/可观测性/代码质量）按报告 §8 的 P0→P2 排序处理。
- **可选建议**：轻微 10 类全部为可选（命名、死代码、重复代码、注释口径）。

---

## 2. 已修复清单（第 2~3 步结果）

### 2.1 严重项（16 项）

| 编号 | 级别 | 位置（文件:行 / 符号） | 修复方式 | 回归用例 |
| --- | --- | --- | --- | --- |
| S-01 | 严重 | [main.py](../../main.py) `_match_host`（约 :1666） | 判据从「拼接串子串包含」改为**标签边界**：`host == label or host.endswith("."+label)`；片段统一剥 `scheme://`、`/`、`.`。同时保留旧表项 `scheme://host/` 写法的兼容（否则扩展点契约被破坏） | `tests/test_platform_dispatch.py`（既有 67 条含准入/分派双面） |
| S-02 | 严重 | [msg_push.py](../../msg_push.py) `_PushHopGuardRedirectHandler` / `_PushHopRejected` / `_sanitize_resp_text` | ① 新增逐跳复核 handler 替代裸 `HTTPRedirectHandler`，每跳重跑 `_checked_push_url`（同一 `allow_local_targets=True` 口径）；② 跳数上限 5；③ 给 `tg_bot` / `pushplus` 两处硬编码地址补首跳校验；④ 响应体派生文本写日志前**截断 300 字 + 过 `mask_credentials`** | `tests/test_msg_push.py::TestPushRedirectHopGuard`（3 条：内网落地拒绝 / 非 http 落地拒绝 / opener 挂的是守卫子类） |
| S-03 | 严重 | [src/stream_select.py](../../src/stream_select.py) `except RedirectHopRejected`（约 :1111-1130） | 补 `security_rejected.add(url)`，与另两条安全出口（`_DerivedHopRejected` / 内网判定）同口径；`record_url` 同址复用分支因此不再把它当「CDN 拒绝」交付 ffmpeg | `tests/test_stream.py`（新增 158 行覆盖 S-03/S-04/S-05 三族） |
| S-04 | 严重 | [src/stream_select.py](../../src/stream_select.py) `_is_derived_hop_allowed` / `_normalize_numeric_host`（:13、:474） | 改用 `ipaddress.ip_address()` 结构化判定：`is_private/is_loopback/is_link_local/is_reserved/is_unspecified`；纯数字主机名先整数化归一（`2130706433`→127.0.0.1）；八进制/`::ffff:`/CGNAT 全覆盖。**保持「不做 DNS 解析」的既有取舍** | `tests/test_stream.py`（同上） |
| S-05 | 严重 | [src/stream_select.py](../../src/stream_select.py) `_registrable_domain` / `_is_same_probe_scope`（:531、:566） | 引入双段公共后缀表 `_TWO_LEVEL_PUBLIC_SUFFIXES`（cn/kr/uk/br 等）；末两段是公共后缀时返回 `""` → 调用方走**剥 Cookie** 的保守分支（宁可少一次带凭据探测，不可外泄） | `tests/test_stream.py`（同上） |
| S-06 | 严重 | [src/platforms/bilibili.py](../../src/platforms/bilibili.py) `_bili_danmaku_host_allowed`（:38-46） | 拒绝集从 `"/" ":"` 扩到 `? # @ \`；判据与 `urlsplit` 解析口径一致（`evil.com?.bilibili.com` 不再放行） | `tests/test_platform_danmaku_offline.py`、`tests/test_bilibili_danmaku*.py` |
| S-07 | 严重 | [src/utils.py](../../src/utils.py) `_SECRET_KEYS` / `_SECRET_LOWER_COMPOUND_BOUNDARY` / `_SECRET_JSON_RE` / 新增 `_SECRET_INI_LINE_RE` / `mask_credentials` | ① 新增 ini 行形态（锚定行首、前缀≤40 且不含 `=`/`:`、值抹到行尾）；② 键名表补 `sig`/`jwt`/`sig_time`/`sig_nonce` + 中文键（密码/口令/令牌/授权码/密钥/秘钥/会话）；小写复合边界扩为 `token\|key\|secret\|signature\|password\|passwd\|auth`（**刻意不加 `sign`**，否则 `design=2`/`presigned=1` 被误抹）；③ JSON 值段支持字符串/数字/布尔/null；④ 全部新增形态配回归用例 | `tests/test_utils.py::TestMaskCredentialsCoverage::test_s07_*`（12 条）+ 既有 `test_public_urls_untouched` 反向棘轮 |
| S-08 | 严重 | [src/config_io.py](../../src/config_io.py) `_redact_ini_secrets` / 新增 `_redact_plain_lines` / `_fallback_redacted_copy` / `_fallback_unmasked_copy` | ① 无 ini 节文件（`URL_config.ini` 实测无小节）不再返回原文，改走**逐行 `mask_credentials`** 通道；② 原子写失败后的 `copy2` 兜底改为「按字节读→逐行脱敏→原子写」，全部失败才落明文且文件名加 `.UNMASKED` 自证 + error 日志 | `tests/test_config_io_update_file.py::test_unreadable_source_falls_back_to_redacted_copy`、`::test_last_resort_plaintext_copy_is_marked_unmasked` |
| S-09 | 严重 | [src/sync_http.py](../../src/sync_http.py) `_HopGuardRedirectHandler` / `_entry_internal_reason`（:71-83、:376） | 复用 `async_http.internal_stream_target_reason` 作**唯一判据**（不另写内网名单）；入口 + 逐跳 + abroad 落地三处覆盖；模块头新增「接线前必读」告警段 | `tests/test_sync_http.py`（新增 350 行；含 `TestSyncReqRedirectHopGate`） |
| S-10 | 严重 | [src/spider.py](../../src/spider.py) `get_douyin_web_stream_data` + 新增模块级 `_inject_origin_and_hevc` | 最外层 `try` 收窄到「取数 + 解析」；ORIGIN/HEVC 注入抽成独立函数（自吞异常、失败只丢注入结果、保留已解析 `room_data`）；顶层兜底补 `logger.exception` 留栈 | `tests/test_spider.py::TestM3RoomPasswordNotInErrorPaths`（`_LogSpy` 补 `exception` 方法） |
| S-11 | 严重 | [src/spider.py](../../src/spider.py) `_ZHIHU_ALLOWED_HOST_SUFFIXES` / `_zhihu_is_allowed_host` / 知乎解析（:5715-5798） | 落地页 host 白名单（`zhihu.com`/`zhimg.com`，精确或 `.` 后缀）；不过闸即剥离 Cookie 语义并返回未开播；`user_id` 一律 `urllib.parse.quote(..., safe="")` | `tests/test_spider_platform.py`（既有 host 白名单族） |
| S-12 | 严重 | [src/node_install.py](../../src/node_install.py) 常量区 + `_fetch_official_sha256` + `_check_or_record_zip_sha256` + `install_nodejs_windows` | ① 下载循环累计字节，上限 `min(1.5×Content-Length, 512MB)`，超限抛错并删除半份文件；② 摘要文档按 `iter_content` 限长 2MB 读取；③ 官方文档不可达且无历史基准时**默认拒绝安装**（error 级），需显式 `DLR_NODE_ALLOW_TOFU=1` 才降级 TOFU | `tests/test_node_install.py`（+50 行：`test_no_official_hash_without_baseline_is_refused_by_default`、`test_unreachable_doc_without_opt_in_refuses_install` 等） |
| S-13 | 严重 | [scripts/check_annotations.py](../../scripts/check_annotations.py) `_reject_dangerous_baseline`（:391-470） | 判定从**排除式黑名单**改为**白名单正向判定**：只有「严格位于 cwd 之下」才放行，其余一律拒绝（系统目录清单保留，仅用于给出更准确理由） | `tests/test_check_annotations.py::test_snapshot_guard_rejects_any_target_outside_cwd`（3 格参数化）+ **变异验证**：撤回修复后 2 格变红、按字节还原 |
| S-14 | 严重 | 测试有效性（跨文件） | **部分修复**：① 修掉报告点名的核心契约缺陷——`test_m3u8_head_405_fallback_to_get` 增加对 `Range: bytes=0-0` 的显式断言（删该头会让探针退化成整文件下载而旧断言照样绿）；② 新增**R11 双向棘轮**（[tests/test_test_hygiene.py](../../tests/test_test_hygiene.py)）：把「函数体无任何判据」「参数承载语义的裸 `assert_called*`」机检化，存量按文件条数冻结为债务表、只许降不许升 | `tests/test_test_hygiene.py::test_r11_*`（4 条含反向见证） |
| S-15 | 严重 | [main.py](../../main.py) 配置行归并（:5215-5419） | 新增「本轮被跳过/解析失败行」集合 `_unparsed_lines`（含从原行抠出的 URL），归并时整行豁免、绝不写进 `_url_comments`；被跳过行保留上一轮注释状态 | `tests/test_regression_main.py`（磁盘块抽取式用例已同步新形参） |
| S-16 | 严重 | [src/spider.py](../../src/spider.py) `get_play_url_list`（:539-566） | 兜底分支对相对行统一 `urllib.parse.urljoin(m3u8, line)`；`.m3u8` 判据改为按 URL 的 **path** 判定（带查询串的 `x.m3u8?token=` 不再被整条丢弃）；5 个调用点（PandaTV/WinkTV/TTingLive/Twitch/YouTube）不再做前缀拼接 | `tests/test_spider_platform.py`、`tests/test_stream.py` |

### 2.2 中等项（已修复 28 项）

| 编号 | 级别 | 位置 | 修复方式 |
| --- | --- | --- | --- |
| M-01 | 中等 | [main.py](../../main.py) :5329 | 准入侧 `url_host` 统一走 `urlsplit(url).hostname`，与分派侧同口径（带凭据地址不再被判未知链接） |
| M-02 | 中等 | [main.py](../../main.py) :5226-5231 | 录制状态键改由**单调序号源**分配并与 URL 绑定，线程存活期禁止复用（同名主播不再互相覆盖状态） |
| M-03 | 中等 | [main.py](../../main.py) :5222-5234 | `monitoring` 去掉「每轮整体重算」，只由拉起 +1 / 线程退出 −1 增量维护 |
| M-04 | 中等 | [main.py](../../main.py) :5459-5484 | `not_record_list` 增删一律进 `record_state_lock` 临界区，改按值定点移除（不再切片整体替换丢条目） |
| M-05 | 中等 | [main.py](../../main.py) :5134-5191 | 磁盘检测失败不再置 `inf`；新增 `_disk_measure_failed` 标记，本轮没测到余量时**不解除**已有暂停 |
| M-06 | 中等 | [main.py](../../main.py) :4744-4750 | 「是否启用 https 录制」不再联动**全局**拉流证书校验，只按平台豁免名单生效 |
| M-08 | 中等 | [main.py](../../main.py) :888、:1048 | ffmpeg `stdin` 改 `DEVNULL`；`stderr` 重定向到临时文件并在收尾读尾部若干行进日志 |
| M-11 | 中等 | [main.py](../../main.py) `_host_in_platform_list`（:301-329） | 代理/海外平台判定从「整串 URL 子串」收窄为「只看 `urlsplit().hostname` 的子串」，消除 query 里出现平台名即误判；**保留子串语义**（配置默认值是 `tiktok`/`youtu`/`shp` 这类不带点的片段，改成标签边界会让过半默认条目静默失效） |
| M-12 | 中等 | [src/spider.py](../../src/spider.py) :2933、:3709 等 | 登录/取流异常日志统一 `e=utils.mask_credentials(str(e))`（部分落点） |
| M-14 | 中等 | [src/spider.py](../../src/spider.py) :343 | `_ensure_twitch_client_id` 慢路出口补代理一致性判定，与 `_ensure_kuaishou_did` 同口径 |
| M-16 | 中等 | [src/spider.py](../../src/spider.py) :3488、:3650 | `RuntimeError` 改为单参数格式化串，告警文案不再是元组字面量 |
| M-17 | 中等 | [src/spider.py](../../src/spider.py) :378-395 | `_safe_loads` 增加 8M 字符上限与嵌套深度阈值（超限记 warning 并跳过解析） |
| M-20 | 中等 | [src/stream_select.py](../../src/stream_select.py) :1304 | `probe_client` 显式前置赋 `None`，构造异常不再触发 `UnboundLocalError` 掩盖原始异常 |
| M-21 | 中等 | [src/stream.py](../../src/stream.py) :634 | `json.loads(stream_data_raw)` 包进 try，失败走 `return result` 并留 warning |
| M-22 | 中等 | [src/stream.py](../../src/stream.py) :734、:1077-1246 等 | 平台下发结构统一 `isinstance(x, dict)` 归一（快手/抖音/网易/YY 四族） |
| M-23 | 中等 | [src/stream.py](../../src/stream.py) :511-538 `_is_h265` | h265 判定收敛为一份实现（大小写不敏感、同时识别 `hevc`），选源侧与抖音侧共用 |
| M-24 | 中等 | [src/stream.py](../../src/stream.py) :904-906 | 蓝光分支的 `available_qualities` 不再无条件加 `UHD`/`LD`，改按 `room_codes` / `HUYA_CODE_ORDER` 推导 |
| M-25 | 中等 | [src/stream_select.py](../../src/stream_select.py) :63 | Windows 保留名按「点号前基础名」判定并改名后再拼扩展名（`CON.txt` 不再变成 `CON.txt_`） |
| M-26 | 中等 | [src/stream.py](../../src/stream.py) :1090 | 斗鱼全档失败返回 `is_live=False`（不再「开播但无地址」空跑 ffmpeg） |
| M-28 | 中等 | [src/sync_http.py](../../src/sync_http.py) :388-414 | `stream=True` 的代理响应改为显式 `try/finally: response.close()`，三条出口（redirect_url 提前返回 / 读体 / 读体抛错）全覆盖 |
| M-31 | 中等 | [src/async_http.py](../../src/async_http.py) :27-120 | 客户端按**创建循环分桶**，同循环失效客户端 `await aclose()`，退出日志给未关闭计数 |
| M-33 | 中等 | [src/sync_http.py](../../src/sync_http.py) :341-361 | `json_data` 形态校验提到 try 之外：非 dict/list 显式 `ValueError`，与 `data` 同传显式拒绝（不再静默退化成 GET） |
| M-51 | 中等 | [src/utils.py](../../src/utils.py) :553-575 | `os.makedirs(..., exist_ok=True)` 消除 TOCTOU；解压前遍历 `infolist()` 拒绝 `S_IFLNK` 成员 |
| M-52 | 中等 | [src/config_io.py](../../src/config_io.py) :119-124 | 备份读取/写回同用 `errors="surrogateescape"`，非 UTF-8 配置不再被 U+FFFD 永久污染 |
| M-53 | 中等 | [src/config_io.py](../../src/config_io.py) :434-456 | 备份时间戳改 **UTC + 毫秒 + 单调序号**；旋转排序优先解析文件名时间戳（乱序时不再删掉最新备份） |
| M-55 | 中等 | [src/utils.py](../../src/utils.py) :165、:367 | 两处 `decode("utf-8")` 补 `errors="replace"` |
| M-98 | 中等 | [build_exe.py](../../build_exe.py) `smoke_web` / `_loopback_web_host` / `_force_loopback_web_host`（:1928-2010） | 冒烟不再注入 `DOUYIN_WEB_ALLOW_INSECURE=1` 绑定 0.0.0.0（最长 90s 无认证暴露）；改为把发布目录 config.ini 的 `web_host` **临时覆盖为 127.0.0.1**、冒烟后按原始字节还原；无 `[Web]` 节或读不到配置时不做覆盖（fail-closed） |

---

## 3. 验证结果（第 4 步）

所有命令均在仓库根目录、项目 venv（Python 3.14.8）下执行；静态门禁在**最后一次编辑之后**重跑。

### 3.1 既有门禁命令（未新增任何命令或配置）

```powershell
$env:PYTHONUTF8='1'
.venv\Scripts\python.exe scripts/run_gates.py      # 门禁唯一基准（AGENTS.md「格式化命令」节）
.venv\Scripts\python.exe -m pytest -q              # 全量测试
```

| 命令 | 结论 |
| --- | --- |
| `python scripts/run_gates.py` | **PASS 10/10，耗时 39.2s** —— black / isort / mypy（含 linux+win32 双跑）/ check_annotations / compile_po --check / check_version / check_runtime_pins / check_skill_agents_consistency 全绿 |
| `python -m pytest -q` | **4645 passed, 8 failed, 14 skipped（222s）** |
| `python scripts/check_coverage.py` | 未执行（本轮未新增/删除模块；覆盖率数据需完整 pytest 会话产出，见 3.3） |

### 3.2 8 个 pytest 失败的性质（重要）

全部为 `tests/test_ci_retry_action.py::test_retry_script_behaviour_with_real_bash[...]`，
**在本轮任何改动之前（工作区仅有未跟踪的报告文件时）就已失败**，属本机环境缺陷而非代码回归：

```text
$ .venv\Scripts\python.exe -c "import subprocess; r=subprocess.run(['bash','-c','echo hi'],capture_output=True); print(r.returncode)"
1                       # 本机 bash.exe 是「未安装 WSL」的占位器，不是真 bash
```

该用例组按设计要用**真实 bash** 执行 `.github/actions/retry/action.yml` 的行为锁；
CI（ubuntu runner）上具备真 bash，本机无法执行。**不得**为让它变绿而放宽断言（那正是报告
S-14 批评的假绿形态）。

基线对比（同一台机器、同一 venv）：

| 时点 | pytest |
| --- | --- |
| 本轮改动前（基线） | 15 failed, 4575 passed |
| 本轮改动后 | **8 failed（均为上述环境失败）, 4645 passed** |

即：基线里 7 个**仓库内在失败**已全部修复（`test_i18n_migration` 目录缺失、`test_regression_net`
残留登记、`test_sync_probe_internal_guard` 历史注、`test_spider_hardening` 三组 json.loads 棘轮、
`test_spider` 脱敏锁），净增 70 条通过用例。

### 3.3 附带证据

| 项 | 结论 |
| --- | --- |
| 全仓 import | `import main, web, gui, i18n, msg_push, build_exe, src.spider, src.stream, src.stream_select, src.sync_http, src.config_io, src.utils` → OK |
| i18n 四语目录 | 提取器「缺失 0 条」；`scripts/compile_po.py --check` → `OK: zh_CN.mo 与 .po 同步（1169 条）` |
| S-07 实测语料 | 报告 11 条语料复跑：改动前 7 条逃逸 → 改动后 **0 条逃逸** |
| S-13 变异验证 | 撤回白名单修复 → `test_snapshot_guard_rejects_any_target_outside_cwd` 2 格变红；按字节还原后全绿 |
| 行尾完整性 | 逐一比对 `git show HEAD:<file>` 与工作区的 CRLF/LF 形态；**修复过程中发现 6 个文件被 `write_text` 静默从 LF 翻成 CRLF，已全部按原形态还原**（`src/node_install.py`、`src/ui_theme.py`、`i18n/en_GB.json`、`i18n/en_US.json`、`i18n/zh_CN/LC_MESSAGES/zh_CN.po`、`i18n/zh_TW.yaml`），还原后复验 `compile_po --check` 与相关用例全绿 |

### 3.4 未执行的真机验证（如实登记）

AGENTS.md「完成定义」第 2 步要求涉及录制链路/选源/ffmpeg 参数的改动做真机增量验证。
本轮改动中 **S-03/S-04/S-05/S-16/M-21~M-26 确实落在选源与取流链路**，但：

- 未执行 `tests/test_{bili,douyin,douyu,huya,twitch}_live_collector.py` 真机脚本；
- 原因：本机无稳定外网到目标平台、无可用活跃直播间，且这些脚本会真实连平台并落盘产物；
- 补偿：相关判据已由离线契约用例覆盖（`tests/test_stream.py` +158 行、`tests/test_spider_platform.py`），
  但**不能替代真机验证**；
- **交回用户的动作**：在可联网环境执行
  `python tests/test_bili_live_collector.py --seconds 30`（或任一受影响平台脚本），
  核对「PASS + 消息数/SRT 字节数」读数后，再宣布该族整改端到端完成。

---

## 4. 待人工确认（第 2 步要求：不猜测改动）

| 编号 | 级别 | 位置 | 缺失的具体信息 |
| --- | --- | --- | --- |
| M-07 | 中等 | main.py:575-589、:4672 | 需先决定「模块导入即注册信号处理器/atexit/覆写 `builtins.print`」的**目标架构**（是否引入 `install_runtime_hooks()`）。这属产品级行为设计，报告未给唯一形态；改错会静默劫持 web/gui/测试宿主的信号处理 |
| M-09 | 中等 | main.py:434-457、:4692-4708 | 「24 个主循环临时量改局部变量/上下文对象」范围不可唯一确定：报告只给首尾行号，实际需逐量判定哪些真跨轮次使用。属大范围重构，超出「最小 diff」 |
| M-10 | 中等 | main.py:4435-4444、:4474-4484、:5309-5314 | 需先定义「哪些异常类型算网络/HTTP 类」的**分类表**（报告只说「只有网络/HTTP 类才调 `record_error`」）。分类表缺失时改动会把熔断判据改成第二份事实源 |
| M-13 | 中等 | src/spider.py:4903-4981 `get_huajiao_sn` | 报告给两个互斥选项（删除该函数 / 改失效判据）。删除会同时改动两处活锁断言；修改需确认「响应可解析且字段确实为空」的判据语义。**未实施**，交回用户选向 |
| M-15 | 中等 | src/spider.py:2631、:5639、:2719、:5000 | 「一律 `quote(value, safe="")`」只完成知乎一处；其余三处（小红书 `user_id`、bigo `room_id`、花椒 `split("user/")[1]`）需确认各平台 id 的合法字符集，避免把本应保留的 `-`/`_` 编码后触发平台 404 |
| M-18 | 中等 | src/spider.py:3145-3146、:3236 | 需确认「空 `view_url` 即 return」是否会误伤「先拿 view_url 后补流地址」的既有平台流程；报告未给该流程证据 |
| M-19 | 中等 | src/spider.py 66 处 Cookie 块；:5455-5473 vs :5582-5597；:3010-3032 vs :3102-3117 | 「抽 `_build_headers` 与统一 helper」是**跨 20+ 平台的机械重构**，属报告 L-02 同族的专项，不是单点修复。本轮只修了其中已漂移的具体缺陷（SOOP 韩国区 `rsplit` 前缀拼接已被 `urljoin` 族覆盖）；抽取动作进后续排期 |
| M-27 | 中等 | src/async_http.py:520、:611、:644 → web_config.py:436 | httpx 的 response 钩子是**同步签名**，无法 `await`。改成 `loop.getaddrinfo` 需要在钩子内拿事件循环 + 设置超时，属并发模型改动；报告未给该形态的唯一答案。**未实施** |
| M-29 | 中等 | src/node_install.py:260-261、:44、:381 | 「校验目录 ACL 与属主」在 Windows 上无跨平台等价实现（ACL API 需 pywin32 或 ctypes 深调）；属新依赖/新平台层决策，不在最小 diff 内 |
| M-30 | 中等 | src/ws_client.py:96-107 | `decompress_brotli_limited` 的「缩小喂入粒度 + try/finally 释放」需先确认 brotli 解压器的 `finish()` 语义（提前 close 会吞掉尾部数据）；报告未给该库的具体契约 |
| M-32 | 中等 | src/async_http.py:740 | 「HEAD 非 2xx 且非明确不可达」需先定义「明确不可达」的**状态码集合**（405/501 之外还有哪些）。缺该集合时改动会把「真死链」放行 |
| M-34 | 中等 | src/cookie_cache.py:221-223、:171；src/http_config.py:9-20、:46-47 | 「缓存命中返回内部引用」改 `dict()`/`MappingProxyType` 需确认所有调用方都不做就地写（含 tests）；`http_config` 三个模块级可变全局的替换形态需先定「按对象引用整体替换」的边界 |
| M-35~M-43 | 中等 | src/scheduler.py / collector.py / room.py / danmaku_monitor.py / recorder_status.py / base.py | 原并行工作包会话中断，**未实施**。这批属并发与生命周期改动，需逐项读 AGENTS.md「并发、事件循环与锁」后单独修复；M-37/M-38/M-39 报告自注「未实测（待核）」，修复前应先补复现用例 |
| M-44~M-50、M-54、M-57、M-58 | 中等 | ffmpeg 三安装器 / config_read / utils / srt_writer / ffmpeg_proc | 原工作包中断，**未实施**（M-51/52/53/55 已在被改动文件内完成）。M-44/M-45 涉及「独占创建 + 目录级文件锁 + 原子替换」，需先定跨进程锁的实现形态 |
| M-59~M-69 | 中等 | src/web_api.py / web_config.py / web_tray.py / web.py | 原工作包中断，**未实施**。这批是 Web 安全面（限流双计数、请求体按字节累加、写接口键白名单、Origin 缺失拒绝、SSE 断连），改动面大且互相耦合，建议单独立项 |
| M-70 | 中等 | web.py:151-165、:41-42、:107-108、:209-210 | `_cap_web_console_log` 的 truncate+write 两步改原子替换、6 处静默 except 降级——属 web.py 与日志层的交叉改动，未实施 |
| M-71~M-83 | 中等 | gui.py / src/gui_qt/** / ui_motion.py / ui_fonts.py / ui_kit.py | 原 GUI 工作包中断，**未实施**（仅 `src/ui_theme.py` 由并行改动顺带修了 `Final` 导入）。报告建议作为「GUI 收敛」专项一次做 |
| M-84~M-88 | 中等 | web/app.js / StopRecording.vbs / src/javascript/*.js | 原工作包中断，**未实施**。M-85（VBS 目录锚点补尾分隔符）风险最高（误杀他程序 ffmpeg），建议优先单项处理 |
| M-89~M-97、M-99 | 中等 | scripts/* / build_exe.py | 原工作包中断，**未实施**（S-13 与 M-98 已单独完成）。这批是门禁自身 fail-closed 与打包链安全，M-91/M-92/M-93 应优先（门禁假绿会削弱后续所有修复的验证能力） |
| M-100~M-104 | 中等 | 覆盖率盲区 / 测试污染 | 原工作包中断，**未实施**。M-100 需为 6 个平台补离线契约用例（工作量大但价值高）；M-103（`tests/_out_live` 共享目录）可与 S-14 同批处理 |
| L-01~L-10 | 轻微 | 见报告 §6 各类代表性位置 | 全部**未实施**。报告明确这类属「低风险技术债窗口」，且建议「不夹带行为变更」单独提交；本轮改动已混合大量行为变更，不适合再叠死代码清理与重复代码抽取（会让 diff 不可审） |

---

## 5. 每项改动的文件与修改摘要

### 5.1 生产代码（11 个文件）

| 文件 | 行数变化 | 修改摘要 |
| --- | ---: | --- |
| [main.py](../../main.py) | +410 / −~80 | S-01 主机判据标签边界 + scheme 兼容；S-15 跳过行归并豁免；M-01/02/03/04/05/06/08/11 |
| [msg_push.py](../../msg_push.py) | +~95 | S-02 逐跳 handler / URLError 子类 / 两处首跳校验 / 响应体截断脱敏 |
| [build_exe.py](../../build_exe.py) | +76 | M-98 冒烟改回环绑定 + 配置临时覆盖与字节级还原 |
| [src/utils.py](../../src/utils.py) | +~110 | S-07 四类脱敏形态 + 键名表扩充；M-51/M-55；L-02 异常日志 helper 抽取（含 `_log_guarded_exception`） |
| [src/spider.py](../../src/spider.py) | +386 / −~90 | S-10 try 收窄 + 注入函数抽出；S-11 知乎 host 白名单 + id 编码；S-16 urljoin + path 判据；M-12/14/16/17/22 相关 |
| [src/stream_select.py](../../src/stream_select.py) | +167 | S-03 拒绝登记；S-04 ipaddress 结构化内网判定；S-05 双段公共后缀表；M-20/M-25 |
| [src/stream.py](../../src/stream.py) | +116 | M-21/22/23/24/26（含 h265 口径统一、虎牙档位推导、斗鱼全档失败） |
| [src/sync_http.py](../../src/sync_http.py) | +124 | S-09 三处内网闸门；M-28 响应关闭；M-33 json_data 形态 |
| [src/config_io.py](../../src/config_io.py) | +95 | S-08 无节/回退双通道；M-52 surrogateescape；M-53 UTC 时间戳与排序键 |
| [src/node_install.py](../../src/node_install.py) | +~70 | S-12 三道限额 + 默认拒绝安装 + 显式 TOFU 开关 |
| [scripts/check_annotations.py](../../scripts/check_annotations.py) | +18 | S-13 白名单正向判定 |
| [src/async_http.py](../../src/async_http.py) | +3 | L-10 历史注（改正被判据锁钉住的注释口径） |
| [src/platforms/bilibili.py](../../src/platforms/bilibili.py) | +4 | S-06 拒绝字符集扩充 |
| [src/proxy.py](../../src/proxy.py) | +9 | L-10 残留登记措辞对齐锁 + 历史注 |

### 5.2 测试（19 个文件）

| 文件 | 修改摘要 |
| --- | --- |
| [tests/test_utils.py](../../tests/test_utils.py) | S-07 新增 12 条参数化用例（含跨行不误伤） |
| [tests/test_msg_push.py](../../tests/test_msg_push.py) | S-02 新增 `TestPushRedirectHopGuard` 3 条 |
| [tests/test_sync_http.py](../../tests/test_sync_http.py) | S-09 逐跳闸门 350 行；修正 `_connect` 替身（`setattr` 绕 mypy method-assign）、`_HopGuard` 形参类型、用项目 logger 替 `loguru as _logger` |
| [tests/test_stream.py](../../tests/test_stream.py) | S-03/04/05 族 +158 行；修正虎牙档位断言的既有契约偏差 |
| [tests/test_node_install.py](../../tests/test_node_install.py) | S-12 策略用例 + 替身补 `encoding`/`iter_content`；修正 Content-Length 与实发字节不一致的夹具 |
| [tests/test_check_annotations.py](../../tests/test_check_annotations.py) | S-13 参数化 3 格 |
| [tests/test_test_hygiene.py](../../tests/test_test_hygiene.py) | S-14 新增 R11 双向棘轮（4 条含反向见证 + 债务表） |
| [tests/test_config_io_update_file.py](../../tests/test_config_io_update_file.py) | S-08 契约更新 2 条 |
| [tests/test_async_http.py](../../tests/test_async_http.py) | S-14 Range 头显式断言 |
| [tests/test_regression_main.py](../../tests/test_regression_main.py) | M-05 抽取式用例补 `_disk_measure_failed` 形参 |
| [tests/test_quality_tiers.py](../../tests/test_quality_tiers.py) | M-26 契约更新（`is_live=False`） |
| [tests/test_start_record_command_golden.py](../../tests/test_start_record_command_golden.py) | M-11 黄金基准的代理条目改为 host 片段（`douyin`），保住 `-http_proxy` 覆盖 |
| [tests/test_platform_dispatch.py](../../tests/test_platform_dispatch.py) | 随 S-01 scheme 兼容自动恢复（未改文件） |
| [tests/test_spider.py](../../tests/test_spider.py) | S-10 替身补 `exception` 方法 |
| 其余 5 个 | `test_exception_log_masking.py` / `test_regression_wp_b_netguard.py` / `test_platform_danmaku_offline.py` / `test_i18n*.py` 等随判据口径同步 |

### 5.3 i18n 四语目录（5 个文件）

新增 17 条运行时模板（第一轮 10 条 + 第二轮 7 条），`zh_CN.po` / `en_US.json` / `en_GB.json` /
`zh_TW.yaml` 同批登记并重编译 `zh_CN.mo`（1169 条）。未登记会导致
`test_i18n_migration.py::test_runtime_templates_covered_by_catalog` 变红——这是本轮实测到的
真实门禁，不是可选项。

---

## 6. 遗留项汇总与建议排期

| 优先级 | 条目 | 理由 |
| --- | --- | --- |
| **P0（下一轮必须）** | M-85（VBS 误杀）、M-91/M-92/M-93（门禁 fail-closed） | M-85 会强杀**无关进程**（不可逆）；M-91~93 让后续所有修复失去验证能力 |
| **P0** | S-14 剩余存量（20 文件 44 处无判据 + 10 处裸 `assert_called*`） | 已由 R11 棘轮冻结不再增长；清零需逐条补判据，建议单独立项 |
| **P1** | M-59~M-69（Web 安全面）、M-44~M-49（下载完整性） | 安全 + 数据完整性，改动面大但边界清晰 |
| **P1** | M-35~M-43（并发与生命周期） | 报告自注部分「待核」，需先补复现用例 |
| **P2** | M-71~M-83（GUI 收敛专项） | 报告建议一次做完，避免多次回归 |
| **P2** | M-100~M-104（覆盖盲区） | 长期收益，可与 S-14 合并推进 |
| **P3（技术债窗口）** | L-01~L-10 | 必须与行为变更**分开提交**，否则 diff 不可审 |

---

## 7. 收尾清理

- 本轮所有一次性脚本均写在 `%TEMP%`（仓库外），未在仓库内产生临时文件：
  `check_s07.py`、`scan_s14.py`、`add_i18n_20261021.py`、`add_i18n_s02_s08_s12.py`。
  已删除。
- `git status --short` 核对：除本报告与本文件（均为 `docs/worklog/` 下的审查/整改记录，
  按 `.dockerignore` 的 `CODE_REVIEW_*.md` 通配不进镜像）外，无未跟踪残留。
- 未触碰 `downloads/`、`logs/`、`backup_config/` 等运行期产物目录，未改动 `scripts/` 下
  正式维护脚本（除 S-13 的 `check_annotations.py` 本体）。

---

*整改执行日期：2026-10-21｜执行方式：静态审查结论逐条核实 + 最小化修复 + 既有门禁验证｜未修改审查报告本体*
