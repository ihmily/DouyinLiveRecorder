# 代码审查报告 CODE_REVIEW_2026-10-02

> **审查对象**: DouyinLiveRecorder 工作空间全部源代码（Python / JavaScript / Node.js / HTML / CSS / VBS / CI 配置），排除第三方依赖目录（`node_modules`）与构建产物（`dist` / `build`）。
> **审查日期**: 2026-10-02　**基线**: main 分支工作区（含未提交改动）
> **问题总量**: 66 项 —— **严重 2 / 中等 17 / 轻微 47**（另含 3 项不计入清单的信息级记录，见第 7 章）
> **上一次全仓审查**: [CODE_REVIEW_2026-09-30.md](CODE_REVIEW_2026-09-30.md)（严重 2 / 中等 51 / 轻微 160，P0 批次已修复）

---

## 1. 审查概述与背景

本次审查由用户发起，要求对本工作空间内全部源代码进行全面审查，重点排查**代码质量、潜在缺陷、安全漏洞与逻辑错误**，逐文件记录问题（注明文件路径、行号、问题类型与修复建议），并按严重程度（严重/中等/轻微）分类产出正式报告。

与 2026-09-30 全仓审查的衔接关系：该轮报告的严重 2 项（S-01/S-02，standalone 孪生漂移）与 P0 六项已于当日修复并带回归锁；本轮审查在此基线上进行，因此本轮发现的「standalone 孪生漂移」类问题（SR-02、M-15/16/17）全部属于**主线 9 月中下旬之后新增防线未回灌独立发行版**的新实例，而非旧问题复发。

本轮审查的总体判断：

1. **未发现「防线缺失」型严重漏洞**。两项严重问题均为「防线已建但接线错位」（SR-01）或「主线防线未回灌孪生副本」（SR-02），修复面都很小（分别为两处分支返回值与一个重定向复检 handler）。
2. **凭据脱敏防线存在实测可复现的键型缺口**（M-01）：`mask_credentials` 对 B 站最高价值凭据键 `SESSDATA`/`bili_jct` 与抖音键 `sessionid_ss`/`sid_tt` 原样放行，属 AGENTS.md 关键约定 #11（camelCase 家族）之后又一同源缺口，本轮以实际执行验证。
3. 工具侧信号干净：`basedpyright` 0 error / 0 warning / 0 notes，与既有门禁基线一致；Mimosa 深度安全扫描 40 项原始告警经逐类裁断后**零新增确认漏洞**（裁断过程见第 7 章）。
4. 测试代码抽查健康：无 MUTATION 标记残留、无真实形态凭据、`tmp_path` 纪律良好、未发现「掩盖真实 bug」的过宽 mock 或恒真断言。

## 2. 审查范围

### 2.1 生产代码（逐文件深审，约 44,000 行）

| 区域 | 文件（行数） |
| --- | --- |
| 主控 | `main.py`（5,479） |
| 平台解析 | `src/spider.py`（7,100）、`src/room.py`（301）、`src/ab_sign.py`（547） |
| 选源/调度/HTTP | `src/stream.py`（1,301）、`src/stream_select.py`（1,403）、`src/scheduler.py`（540）、`src/async_http.py`（749）、`src/sync_http.py`（430）、`src/http_config.py`（63）、`src/proxy.py`（295） |
| 弹幕链路 | `src/collector.py`（583）、`src/ws_client.py`（486）、`src/srt_writer.py`（230）、`src/danmaku_monitor.py`（796）、`src/ttwid.py`（240）、`src/cookie_cache.py`（408）、`src/base.py`（116）、`src/proto/`（仅手写文件） |
| Web 面板 | `src/web_api.py`（1,593）、`src/web_config.py`（1,311）、`src/web_models.py`（191）、`src/web_tray.py`（265）、`src/recorder_status.py`（240）、`web.py`（354）、`web/app.js`（2,089）、`web/index.html`（201）、`web/style.css` |
| 工具/配置/通知 | `src/utils.py`（1,003）、`src/config_io.py`（415）、`src/config_bool.py`（54）、`src/notify.py`（346）、`src/logger.py`（293）、`src/log_archive.py`（224）、`i18n.py`（415）、`src/video_postprocess.py`（499） |
| GUI/构建/安装 | `gui.py`（4,530）、`src/ui_theme.py`（385）、`build_exe.py`（1,740）、`src/ffmpeg_install.py`（688）、`src/ffmpeg_master_download.py`（478）、`src/ffmpeg_proc.py`（311）、`src/node_install.py`（404）、`StopRecording.vbs` |
| 独立发行版 | `scripts/douyin_live_recorder_standalone.py`（2,458，与主线逐点对照） |

### 2.2 测试代码（风险模式抽查）

`tests/`（约 3,690 个用例）按风险模式全仓 grep + 可疑文件精读：变异标记残留、真实形态凭据、`tmp_path` 纪律、过宽 mock、恒真断言、吞断言的 `try/except`、裸 `time.sleep` 同步依赖。结论：无新增高危发现（详见 6.8 节）。

### 2.3 排除项

- 第三方/生成物：`node_modules`、`dist`、`build`、`typings/` 存根、`src/proto/douyin_pb2.py`（protoc 生成）及 `.pyi`。
- 第三方压缩件：`src/javascript/crypto-js.min.js`（vendored 库，不可审阅源形态）。
- 未跟踪杂散文件：`markdown-DX-TNHnc.js`（VSCode Markdown 语法定义 JSON 的压缩产物，疑似误落仓库根目录；不参与审查计数，**建议删除**，见 8.3）。

### 2.4 审查方法与工具

1. **八个并行深审工作包**：按上表区域分工，逐文件全文阅读，交叉验证调用点、下游实现与历史注释声称。
2. **行级复核**（审查者亲自验证）：SR-01/SR-02 全部代码证据逐行读过；M-01 以项目 venv 实际执行验证（`SESSDATA=abc123&bili_jct=xyz789` 样例原样返回，值未抹除）；M-06 以 `httpx.InvalidURL.__mro__` 实测确认直继 `Exception`；M-10 的两处代码读数逐行核对。
3. **工具交叉**：`basedpyright`（0 error / 0 warning / 0 notes）；Mimosa 深度安全扫描（静态、密封产物，扫描与裁断详见第 7 章）。
4. **约定基线**：AGENTS.md 所列项目刻意约定（PEP 758 无括号多异常、中文 `#` 注释、`i18n.tr` 模板口径、容错性宽 `except` 设计等）不计为问题；「异常吞噬不留上下文」「用户可见文案缺 i18n」「凭据未脱敏」等仍按约定视为缺陷。

## 3. 问题统计总览

### 3.1 严重度定义

| 严重度 | 判据 |
| --- | --- |
| 严重 | 可被现实威胁模型利用的安全漏洞（SSRF 击穿自身防线、凭据经可控路径外送），或核心功能确定性失效 |
| 中等 | 有真实影响的缺陷：凭据脱敏缺口（实测）、并发丢写/竞态、资源泄漏、确定性误判、孪生漂移致功能反转；但需特定配置或时序触发 |
| 轻微 | 防御纵深缺口、可观测性不足、契约/注释与实现漂移、死代码、边缘输入崩溃；当前无实锤泄漏或崩溃路径 |

### 3.2 统计矩阵

| 区域 | 严重 | 中等 | 轻微 | 小计 |
| --- | ---: | ---: | ---: | ---: |
| main.py | 0 | 1 | 6 | 7 |
| 平台解析（spider/room/ab_sign） | 0 | 3 | 7 | 10 |
| 选源/调度/HTTP 基建 | 1 | 2 | 4 | 7 |
| 弹幕链路 | 0 | 2 | 7 | 9 |
| Web 面板 | 0 | 1 | 7 | 8 |
| 工具/配置/通知基建 | 0 | 3 | 6 | 9 |
| GUI/构建/安装链 | 0 | 2 | 7 | 9 |
| 独立发行版 standalone | 1 | 3 | 3 | 7 |
| tests/ | 0 | 0 | 0 | 0 |
| **合计** | **2** | **17** | **47** | **66** |

### 3.3 与上次全仓审查（2026-09-30）的衔接

- M-01（`mask_credentials` 键型缺口）是 AGENTS.md 关键约定 #11 已知缺口家族的延续（`accessToken`/`wsAuth`/`tk` camelCase 事件同源），本轮首次实测到 **B 站/抖音主会话键**整体逃逸。
- M-11（`update_config` 无锁读改写）与已修的 MID-29（URL_config.ini 侧丢写）同族，属加锁范围漏网。
- SR-02、M-15/16/17 是 S-01/S-02 整改后**主线新增防线未回灌**的新孪生漂移：主线 2026-09-30 补的重定向逐跳复检、分片级探测、`config_bool` 口径均未进 standalone。
- 上轮遗留的 P1/P2 项本轮不再重复罗列，修复时以上轮报告清单为准。

## 4. 严重问题（2 项）

### SR-01 m3u8 正文派生地址被安全闸拒绝后仍维持候选「可达」，内网目标经播放列表交给 ffmpeg

- **位置**: `src/stream_select.py:532-539`（master 变体派生跳）、`561-568`（媒体分片派生跳）
- **类型**: 安全 / SSRF 击穿自身防线（已行级复核）
- **描述**: `_probe_hls_segment` 对正文派生地址（变体列表/分片）执行 `_is_derived_hop_allowed` 校验（MID-2231：形态合规 + 非内网目标）。命中拒绝时，代码只打告警「已丢弃（不交给 ffmpeg -i）」随即 `return True` —— **维持该 m3u8 候选可达**。而 `_validate_stream_url` 据此判候选可达，`_accept_source` 只复查播放列表 URL 本身（公网，必过），被劫持/被 MITM 的播放列表最终被选中交给 `ffmpeg -i`；ffmpeg 按列表正文连接内网目标（如 `http://127.0.0.1:6379/`、云元数据地址），并对同输入复用自定义请求头（含平台 Cookie）。
- **代码证据**: 两分支形态一致 —— `if not _is_derived_hop_allowed(variant_url): logger.warning(...); return True`。同函数 `except RedirectHopRejected: raise` 分支（:570-574）的注释（WP-J）自我写明：**「在内网落地目标面前，维持可达就等于把内网地址交给 ffmpeg（调用方末位候选还会 return True 放行）」**——安全拒绝分支做的恰是该注释禁止的事。对照实验：十进制 IP 形态（`http://2130706433/`）因 `_PRIVATE_HOST_PATTERN` 不认而放行到实际请求，被客户端级逐跳钩子（`build_sync_hook` → `_ipv4_from_aton`）拦下、候选判失败——即**本已被逐跳闸门拦截的攻击形态，改由列表正文携带时反而成功落 ffmpeg**。
- **影响**: 在项目自身威胁模型内（m3u8 正文属外部可控输入；虎牙/斗鱼地址刻意降级为 http，MITM 现实可行），内网 SSRF 与凭据转发防线被自身闸门击穿；日志给出与行为相反的「已丢弃」误导线索，排障归因反向。
- **修复建议**: 两个 `return True` 改为 `return False`（候选判失败、回退下一候选），与 `RedirectHopRejected` 分支同收敛；补一条行为锁（构造正文含内网分片地址的播放列表，断言候选不被选中）。

### SR-02 standalone 探针 opener 自动跟随重定向且逐跳不复检，主线 SSRF 防线未回灌（孪生漂移）

- **位置**: `scripts/douyin_live_recorder_standalone.py:192`（`_HTTP_ONLY_HANDLERS` 含 `HTTPRedirectHandler`），配合 `:1511-1520`（`_untrusted_stream_target_reason` 仅判初始候选）、`:229/:263/:1364`（`http_probe`/`http_request`/`_confirm_get_ok`）、`:1458-1476`（末位候选告警放行）
- **类型**: 安全 / SSRF + 孪生漂移（已行级复核）
- **描述**: standalone 的 S-01 整改补齐了「显式协议白名单 opener」与「初始候选 URL 内网判定」，但 opener 白名单仍含 `urllib.request.HTTPRedirectHandler` —— 探针会**自动跟随重定向且每跳不复检**。公网候选 302 到 `http://127.0.0.1:6379/` 或云元数据地址时，逐跳判定缺失；末位候选的「告警放行交 ffmpeg」路径再把该地址交给录制。主线同层防线是 `src/stream_select.py` 探针客户端挂 `build_sync_hop_guard`（每跳含落地跳均判内网/协议，命中即断，2026-09-30 补齐并带回归锁 `tests/test_sync_probe_internal_guard.py`），未回灌 standalone。文件头注释只登记了「DNS 重绑定窗口」这一残余缺口，**重定向逐跳复检是未登记的第二类缺口**；孪生锁 `TestUntrustedStreamTargetGuard` 只测直接候选 URL，CI 抓不到。
- **代码证据**: `_HTTP_ONLY_HANDLERS` 元组第 4 项为 `urllib.request.HTTPRedirectHandler`（:192），`_build_opener` 直接以其构造 opener；全文件无自定义重定向 handler。
- **影响**: 独立发行版（随仓库分发的产物）上，被劫持/投毒的平台接口可借「公网候选 → 重定向内网」让探针成为内网扫描器，并经末位候选放行让 ffmpeg 把内网响应录进产物——S-01 整改在重定向维度上形同未设防。
- **修复建议**: 自定义 `HTTPRedirectHandler` 子类，在每次跳转前复用 `_untrusted_stream_target_reason(newurl)` 复检，不通过即抛错断链；与主线 hop-guard 判据注释互点名；孪生锁补一条「重定向到内网」行为锁。

## 5. 中等问题（17 项）

### 5.1 凭据与脱敏（2 项）

**M-01 `mask_credentials` 对 B 站/抖音主会话键整体逃逸（实测复现）**
- **位置**: `src/utils.py:857-1003`（`_SECRET_KEYS` + `_SECRET_QUERY_RE`/`_SECRET_HEADER_RE`）
- **描述**: B 站主凭据键 `SESSDATA`、`bili_jct` 与抖音 Cookie 键 `sessionid_ss`、`sid_tt` 不在黑名单；query 形态实测原样返回。header/Cookie 形态下 `_SECRET_HEADER_RE` 的值字符集 `[^,;\r\n"']+` 在首个 `;` 截断，只抹第一段（`Cookie: SESSDATA=abc; bili_jct=xyz` 中 `bili_jct` 全值裸奔）；`sessionid_ss`/`sid_tt` 因交替式要求紧随 `=` 而不命中（对照组 `wsAuth`/`access_token`/`passport_csrf_token` 均正确抹除）。
- **影响**: `mask_credentials` 是日志脱敏唯一防线（logs 轮转保留多份）；B 站会话凭据与 CSRF token 一旦经任何现网/未来调用点（异常文本、诊断日志、代理串）落入日志即长期明文。
- **修复建议**: 按关键约定 #11 同批补四个整段小写键入 `_SECRET_KEYS`，并在 `TestMaskCredentialsCoverage` 加「值确实消失」断言；Cookie 头形态允许值内含 `;` 或逐段二次过码。

**M-02 main.py 主循环解析段 6 处 URL/配置行未脱敏落盘**
- **位置**: `main.py:3806-3810`、`5357-5363`、`5293-5296`、`5183-5186`、`5250-5253`、`5302-5308`
- **描述**: `获取失败的地址是:{url_data}`（print 原始三元组）、`url_tuple[1]`（新增/传入地址 print）、`origin_line.strip()`（print_colored）、及 3 处 `logger.warning/error`（删除重复配置行失败、配置行解析失败）均直写原文。后三处进 `streamget.log`（300KB 轮转、保留多份）；print 三处进控制台与 Web 后台模式 `web_console.log`（不轮转）。
- **影响**: 与本文件 MIN-2231/MID-28 已修点完全同类——自定义流地址含 `https://u:p@host/x.m3u8` 形态时凭据明文持久落盘；主循环解析段是脱敏漏网面。
- **修复建议**: 上述各点的 `url_data`/`url_tuple[1]`/`origin_line`/`line` 实参一律先过 `utils.mask_credentials()`。

### 5.2 平台解析（3 项）

**M-03 小红书入口子串路由，落地页白名单校验之前即以带凭据头请求任意 host**
- **位置**: `src/spider.py:2449-2492`（`get_xhs_stream_url`），配合 `main.py:1676-1680`（`_match_host` 子串匹配）、`main.py:3075`（分发表）
- **描述**: 平台分发与函数内入口判定均为子串匹配（`"xhslink.com" in url`），`https://attacker.com/xhslink.com/x` 会路由进 XHS 解析，并在 :2450/:2492 **直接以带 `xy-common-params`（含会话 sid）+ 用户 Cookie 的 headers 请求该任意 host**——发生在 :2460 落地页白名单校验之前；:2491 注释「走到这里 url 已保证落在 XHS 白名单域内」在此形态下不成立。同文件 Shopee 侧已用入口白名单堵同型问题（S-1）。
- **影响**: 一条恶意分享链接即可把 XHS sid 与用户 Cookie 递送到攻击者 host，并可对内网发起带凭据 GET（异步逐跳钩子在响应头已收到后才触发，拦不住首跳凭据外送）；tiktok/kuaishou/huya 等直接抓取原始 URL 的平台同型，仅外泄面收窄为各平台 Cookie。
- **修复建议**: 解析函数入口先对 `urlparse(url).hostname` 做域族白名单校验（对齐 `_shopee_is_allowed_host` 判据）；分发侧 `_match_host` 改按解析出的 host 判定。

**M-04 平台凭据缓存三元组锁外写，singleflight 并发返回可产生值与出口记录错配**
- **位置**: `src/spider.py:310-313`、`317-325`（`_ensure_kuaishou_did`）、`357-359`（`_ensure_twitch_client_id`）、`2318-2325`（`_bili_buvid_cached`）
- **描述**: 「值/ts/proxy 记录」三元组在**锁外**写全局（失效钩子 `invalidate_*` 却持锁）；两个不同代理的 singleflight 桶并发返回时写交错可产生「值与出口记录错配」（proxy=A 的房间拿到 proxy=B 拉取的 did）。读侧 `_take_cached_*`（:263-269、:2105-2117）同样无锁读三元组。
- **影响**: 快手 did 与出口 IP 绑定，错配即复活 M-8 注释描述的跨出口串用症状（间歇「200+空 body」风控）；多代理多房间冷启动下低概率触发，触发后难以归因。
- **修复建议**: 三处写点收进各自 `_kuaishou_did_lock`/`_twitch_client_id_lock`/`_bili_buvid_lock` 临界区（临界区零 await，符合本文件 H-2 口径）。

**M-05 popkontv `is_private` 判型脆弱，开播房间可能恒判未开播（待确认）**
- **位置**: `src/spider.py:4078`；伴生死代码 `:4168-4171`（`cast_start_date_code_int` 计算后未使用，注释已自认）
- **描述**: `int(cast(str, is_private)) != 0`：若 `mc_isPrivate` 以 JSON 布尔下发，`int(str(True))` 抛 `ValueError` 被 `@trace_error_decorator` 吞成 `{"is_live": False}`，开播房间恒判未开播。
- **影响**: 取决于 API 字段类型；若确为字符串/数字则无实际影响。**验证方法**: 真机抓一次 popkontv `live/view` 页 `__NEXT_DATA__` 看 `mc_isPrivate` 类型。
- **修复建议**: 改 `_dig(...)` 结果按真值判定而非 `int(str(...))`；顺带清理 :4168 死代码。

### 5.3 选源与 HTTP 基建（2 项）

**M-06 共享探针客户端构造异常集漏 `httpx.InvalidURL`，畸形代理配置每轮抛穿房间线程**
- **位置**: `src/stream_select.py:1206`
- **描述**: 只捕 `except ValueError, TypeError:`；本环境 httpx 0.28.1 实测 `InvalidURL` 直继 `Exception`（MRO：`InvalidURL → Exception`，非 ValueError 子类）。用户把代理写成裸 IPv6（`::1:8080`，`handle_proxy_addr` 补全后构造期即抛 InvalidURL）即逃出 `select_source_url`，落入房间线程外层「直播录制出错」+ `record_error`，每轮复现。同文件 `_validate_stream_url` 自建分支（:828-829）构造在宽 except 内，两处口径不一致。
- **影响**: 特定畸形代理配置使全部房间永远无法录制且持续污染熔断统计；重开 SEV-N05 注释自述已修的「选源每轮抛穿」链。
- **修复建议**: 构造点异常集纳入 `httpx.InvalidURL`（或宽到 `Exception`）→ `probe_client = None` 走既有自建降级路径。

**M-07 async_http 缺包误判分支包住整个请求路径，真 RuntimeError 被误报为缺依赖**
- **位置**: `src/async_http.py:450-459`
- **描述**: `except (ImportError, ModuleNotFoundError, RuntimeError)` 包住整个请求路径而非仅客户端构造：请求在途时任何真 `RuntimeError`（anyio 取消作用域错乱、房间线程退出竞态的 `Event loop is closed` 等）都进 `_log_dependency_missing`，以 warning 报「缺少可选依赖…请 pip install httpx[http2,socks]」（module 为空时模板出现空缺省名）。
- **影响**: 真实运行时故障被系统性误报为缺包，误导排障且告警噪音升级。
- **修复建议**: 仅当 `_missing_dependency_name(e)` 非空才走缺包分支，否则落通用 `except Exception` 分支。

### 5.4 弹幕链路（2 项）

**M-08 brotli 解压无输出上限，「总内存收敛」注释失实**
- **位置**: `src/ws_client.py:97-108`（`decompress_brotli_limited`），消费点 `src/platforms/bilibili.py:332`
- **描述**: 注释声称「分块粒度决定单步膨胀上界，把总内存收敛到 limit + 单块膨胀量」（MI-01），但 `brotli.Decompressor.process()` 无输出上限参数，`out += obj.process(...)` 先把该块全部输出物化后才检查 `len(out) > limit`；brotli 复制链允许极小输入膨胀出 MB~GB 级输出（gzip 路径走 zlib `max_length` 在 C 层硬截断，是真上限）。帧本身限 8MiB，解压放大面未闭合。
- **影响**: 恶意/异常服务端（正是 MI-01 声明的威胁模型）用一个 ≤8MiB 的 brotli 帧即可在录制进程内造成远超 8MiB 的瞬时内存尖峰。
- **修复建议**: 至少修正注释失实声明并标注 brotli 为「事后检测」；根治需换支持输出上限的 brotli 绑定或对 brotli 帧单独收紧 `_MAX_FRAME_BYTES`。

**M-09 弹幕文本无长度上限，「按条数封顶」的内存界在超大消息面前名不副实**
- **位置**: `src/collector.py:30`、`:538`；`src/danmaku_monitor.py:701`；上游 `src/ws_client.py`（单帧解压后 ≤8MiB）
- **描述**: SRT 队列 10000 条、边车队列 20000 行、`_recent` 500 条均只按**条数**封顶（collector.py:30 的注释自己把界建立在「约 80 字节量级」假设上）；消息链路上游只限单帧 8MiB，`message`/`user_name` 均未截断，边车侧还对全文 `json.dumps` 再入队。
- **影响**: 一条 8MiB 批量帧可解析出大量大文本消息，队列满载时最坏内存上界为「条数上限 × 8MiB」（理论 GB 级），「保证内存有界而不是静默增长到 OOM」的承诺失效。
- **修复建议**: `_on_message` 入队前对 `user_name`/`message` 统一截断（如 2000 字符），SRT 与监控流共用该口径。

### 5.5 Web 面板（1 项）

**M-10 0.0.0.0 通配绑定下 Origin 同源判定把面板自身写流量一并 403，远程部署「读得到、写不了」**
- **位置**: `src/web_config.py:1043-1052`（`_is_same_origin`）+ `src/web_api.py:571-578`（非幂等请求 403，闸在白名单分支之前，`/api/login` 同样被拦）
- **描述**: `bind_host` 为 `0.0.0.0` 时被 `_WILDCARD_BIND_HOSTS` 跳过比对，随后 `is_loopback_bind_host(LAN_IP)` 为假 → 判否；浏览器对同源 POST 也带 Origin（`http://192.168.1.5:8000`），故面板自身页面发起的登录/写配置/增删房间全部 403。`tests/test_web_config.py:285` 已把该判定锁成预期（刻意），但与两处承诺直接矛盾：`WEB_DEFAULTS` 注释（web_config.py:77-79）称「仅在以域名（而非 IP）访问时才需要 web_allowed_hosts」；`web.py:244-251` 的无认证警告明文列出「增删改直播间/启停录制」为该部署的可用能力。
- **影响**: fail-closed（非安全洞），但 `DOUYIN_WEB_ALLOW_INSECURE=1` 或开认证绑 0.0.0.0 的远程部署面板不可写；解锁唯一途径是手工编辑 config.ini 登记 `web_allowed_hosts`——而这项写入本身也被 403。
- **修复建议**: 交维护者裁决「修行为还是修文档」：让 `_is_same_origin` 信任浏览器不可伪造的 `Sec-Fetch-Site: same-origin` 承诺（跨站页面无法伪造该头，非浏览器客户端本就无凭据可 CSRF），或最低限度修正 web.py 警告文本与 `WEB_DEFAULTS` 注释、明确要求登记 `web_allowed_hosts`。

### 5.6 工具与配置基建（3 项）

**M-11 `utils.update_config` 对 config.ini 无锁读改写，并发回写互相覆盖**
- **位置**: `src/utils.py:600-642`；并发调用点 `main.py:2043/2202/2267/2321`、`src/spider.py:6552`
- **描述**: 「整文件读 → 改单键 → 原子写回」**不持任何锁**；同类写回 `config_io.read_config_value` 的缺键补写明确持 `main.file_update_lock`（config_io.py:237）。两个房间线程并发回写各自基于同一份旧快照，`os.replace` 保证文件不损坏但后写者覆盖前写者的单键改动。
- **影响**: 某平台的 cookie/token 刷新静默丢失，属 MID-29 已修的同族丢写形态（URL_config.ini 侧已加锁，此处漏网）。
- **修复建议**: 复用 `_url_config_write_lock()` 同款惰性手法取 `main.file_update_lock`（取不到退本地锁）。

**M-12 `config_io.update_file` 读取异常集漏 `OSError`，与 MIN-2243 依赖的契约不符**
- **位置**: `src/config_io.py:63`
- **描述**: 只捕 `except (RuntimeError, UnicodeDecodeError):`；`open()` 的 `FileNotFoundError`/`PermissionError`（Windows 杀软扫描、只读挂载）直接外抛。同文件 `update_anchor_name`（:113）与 `delete_line`（:184）均捕 `OSError`；`web_api.py:930` 的 MIN-2243 注释明确依赖「update_file 失败时返回 old_str」契约。
- **影响**: Web 编辑房间端点以裸 500 收场而非按设计「负信号 + 重解析裁决」；主循环侧落入通用 except，行为与同族两函数不一致。
- **修复建议**: 把 `OSError` 加入该 except 元组（读失败无需快照恢复，`return old_str` 即可）。

**M-13 `logger.add_file_sinks` 两 sink 共享一个 `except OSError`，第二个失败时第一个句柄 id 被一并丢弃**
- **位置**: `src/logger.py:226-240`、`:285-293`
- **描述**: 若 `_add_playurl_sink()` 抛错，已注册成功的 streamget sink 的 handler id 被一并置 `None`，该 sink 从此无法经 `remove_file_sinks()` 关闭。
- **影响**: Windows 下 `streamget.log` 的归档改名永久 `PermissionError`（有告警不致命），日志归档链路对该文件失效。
- **修复建议**: 逐个 try/except 注册：第二个失败时先 `logger.remove(第一个 id)` 或只保留第一个 id。

### 5.7 GUI 与安装链（2 项）

**M-14 GUI「彻底退出」收尾窗口期「开始录制」未被禁用，可孤儿化新录制进程**
- **位置**: `gui.py:3059-3077`（`quit_application`）、`3577-3607`（`_process_ended`）、`4230`（`_cleanup_zombie_ffmpeg` 收尾）
- **描述**: 退出只置 `_quitting=True` 并后台停子进程；子进程被杀后 EOF 哨兵经 `_drain_log_queue` 触发 `_process_ended`，该函数**不检查 `_quitting`**，把 `process=None` 并重新启用 `start_btn`（:3599）；退出线程此刻还在 `_cleanup_zombie_ffmpeg`（两次 taskkill 超时上限约 8s）。
- **影响**: 用户在该窗口点「开始录制」会拉起新录制子进程，随后 `_finalize_quit` 销毁窗口、GUI 进程退出——新录制进程及其 ffmpeg 全部孤儿化，在用户以为已退出的情况下继续录制。
- **修复建议**: `start_recording` 入口增加 `if self._quitting: return`（或退出确认后禁用 start 按钮、`_process_ended` 对 `_quitting` 短路）。

**M-15 `check_nodejs_installed` 异常集漏 `TimeoutExpired`/`OSError`，且在 `import src` 导入期调用**
- **位置**: `src/node_install.py:386-397`；导入期接线 `src/__init__.py:37-39`
- **描述**: 只捕 `FileNotFoundError`，`node -v` 卡死（杀软扫描、残缺安装）抛 `subprocess.TimeoutExpired`、二进制损坏抛 `OSError` 都直接穿出；注释却声称「其它异常也吞掉返 False」。该函数经 `check_node()` 在 **import src 导入期**被调用（仅测试开关豁免、无 try 包裹）。同族场景 `check_ffmpeg_installed`（`src/ffmpeg_install.py:649-681`）已做同款硬化并留注释。
- **影响**: PATH 命中一个卡死/损坏的 node 时，CLI/GUI/Web 三入口启动直接崩溃，仅裸 traceback。
- **修复建议**: 补 `except subprocess.TimeoutExpired`（warning 后返回 False）与 `except OSError` 分支，对齐 ffmpeg 侧口径。

### 5.8 独立发行版 standalone 孪生漂移（3 项）

**M-16 ffmpeg 终止链缺「stdin 写 q」一级，Windows 下 mp4 必然截断不可播**
- **位置**: `scripts/douyin_live_recorder_standalone.py:1783`（Popen 未接 `stdin=PIPE`）、`:1699-1724`（`terminate_all_ffmpeg` 只有 terminate→wait(3s)→kill）
- **描述**: 主线三级终止链（`src/ffmpeg_proc.py:109` 先写 `q` 到 stdin / POSIX 发 SIGINT，再 terminate/kill；`main.py:1104` `stdin=subprocess.PIPE`）未回灌。Windows 下 `proc.terminate()` 即 TerminateProcess 硬杀，:1713 的 3 秒宽限毫无作用；:1700-1703 注释自己描述的「moov 缺失、不可播放」形态在 Windows 的 mp4 输出上必然复现。
- **影响**: standalone 下 Ctrl+C/停止产生的 mp4（及部分 ts）录制文件截断不可播，逐次发生。
- **修复建议**: Popen 加 `stdin=PIPE` 并在终止链最前增加「写 q + close stdin」一级。

**M-17 HLS 候选「播放列表 200」即判可用，缺分片级探测与快速失败退避闭环**
- **位置**: `scripts/douyin_live_recorder_standalone.py:1439-1464`（m3u8 分支）、`:2008-2010`（`rc != 0` 只记失败）
- **描述**: 主线有分片级探测（`_probe_hls_segment`，2026-09-13 斗鱼 hw 事故「列表 200 ≠ 可录制」的整改）与「ffmpeg 快速失败(≤20s) → mark_ffmpeg_reject 记退避」闭环（AGENTS 录制结果反馈约定），均未回灌。
- **影响**: 播放列表 200 但分片不可达的 HLS 假绿候选每轮被重复选中（HLS-first 下 FLV 备选永不回退），对斗鱼等平台陷入逐轮 parse+probe+ffmpeg 失败循环。
- **修复建议**: 补分片 Range GET 探测；rc≠0 且快速失败时对白名单平台（仅虎牙）调 `_mark_probe_reject`。

**M-18 布尔配置解析为前缀判断，`true/false` 取值静默反向生效**
- **位置**: `scripts/douyin_live_recorder_standalone.py:1862`、`:1879`、`:1886`
- **描述**: `startswith("是")` / `not startswith("否")` 前缀判断，主线 `src/config_bool.py` 统一 token 集（true/false、1/0、yes/no、on/off、t/f）未回灌；且三处内部自相矛盾——`是否启用代理 = true` 判「关」（静默直连）、`是否去除表情 = false` 判「开」。这正是主线 2026-09-17 P0（true/false 批量改写致 8 项配置漂移）修掉的形态，AGENTS 亦把 config_bool 列为必核对孪生项。
- **影响**: 从主线迁移或经 Web 面板写入非「是/否」取值的 config.ini 在 standalone 下静默按相反语义生效；代理场景直接裸连。
- **修复建议**: 把 `TRUE_TOKENS/FALSE_TOKENS + parse_config_bool`（约 20 行，零依赖）移植进 standalone 三处读取点。

## 6. 轻微问题（47 项）

### 6.1 main.py（6 项）

| 编号 | 位置 | 类型 | 描述与修复建议 |
| --- | --- | --- | --- |
| L-01 | main.py:4533-4539 | 并发一致性 | 房间线程轮末等待只查 `not recording_enabled`，不查 `exit_recording` 与 `url_comments`，与 disable_record 等待（三条件）及 `_interruptible_sleep` 口径不一；URL 被注释后线程最长滞留一个循环周期。改用 `_interruptible_sleep(x, record_url)` 并补条件 |
| L-02 | main.py:1179-1182、4334-4339 | 资源泄漏 | 线程 `start()` 抛 `RuntimeError: can't start new thread` 时 target 未运行、finally 清理不执行，`create_var` 条目缓慢累积。start 包 try，失败 `pop(key, None)` 并告警 |
| L-03 | main.py:1619、1625、1647、2426、3668、4574 | 异常上下文 | 6 处异常日志缺 `{type_name}`（4574 为裸 `logger.error(e)`），超时类异常 `str()` 为空时无法归因。补 `type_name=type(e).__name__`，4574 改 i18n.tr 模板 |
| L-04 | main.py:3967-3991 | 功能一致性（待确认） | `platform_cookie` 映射缺 `shopee`/`花椒直播`（唯二强制直下平台）及 20+ 平台，探针/ffmpeg 头/直下均不带 Cookie。验证方法：配 cookie 后抓包比对请求头；确认后补键 |
| L-05 | main.py:228、276、483+5332 | 死代码 | `pre_max_request`、模块级 `record_danmaku_args`、`seen_urls` 全局均零有效引用（grep 实证），注释声称的用途与实际不符。删除或标注保留原因 |
| L-06 | main.py:5287、5458、5461 | 逻辑 | `url_tuples_list` 仅在 try 尾部清空，异常轮后旧条目残留叠加下一轮；后果限于单轮幽灵拉起、可自愈。清空移到每轮解析开始处 |

### 6.2 平台解析 spider.py / room.py（7 项）

| 编号 | 位置 | 类型 | 描述与修复建议 |
| --- | --- | --- | --- |
| L-07 | src/room.py:106、241 | 凭据脱敏 | `get_sec_user_id`/`get_unique_id` 重新包装 `RuntimeError(f"An error occurred: {e}")` 未过 `mask_credentials`；`InvalidURL`/`TooManyRedirects` 等异常 str 内嵌完整 URL（可能带 token 参数）。包装前过码 |
| L-08 | src/spider.py:1767-1768 vs 1834 | 注释矛盾 | 注释声称「调用方以 `or ""` 兜底」，全仓唯一调用点没有；h5 失败时 `title=None` 入 dict。当前调用点容忍，属契约漂移。1834 行补 `or ""` 或改正注释 |
| L-09 | src/spider.py:4987-4990 | 死代码 | `get_huajiao_sn` except 分支内 raise 之后还有逐字重复的 raise，永不可达。删除重复 4 行 |
| L-10 | src/spider.py:645-646 | 吞异常零日志 | `_extract_room_data_from_html` 末尾裸 `except Exception: return {}`，意外 TypeError/KeyError 零痕迹，与「真离线」不可区分。补一条 `logger.debug` |
| L-11 | src/room.py:94 | 逻辑（待确认） | `sec_user_id=([\w_\-]+)&` 要求参数后紧跟 `&`，位于 query 末尾则匹配失败、该房每轮永久失败。lookahead 改 `(?=&|#|$)`（与同文件 rid=/mcid= 已修写法一致） |
| L-12 | src/spider.py:335-338 | 一致性 | twitch client_id 快路只判非空+TTL，不比对已记录出口，与快手/B站「出口一致性」口径不一（Client-Id 非出口绑定，影响有限）。补一行 proxy 比对 |
| L-13 | src/room.py:245-290 | 死代码 | `get_live_room_id` 全仓无生产调用点，且键缺失时 `cast(str, ...)` 返回 None 与 `-> str` 注解矛盾。删除或返回 `""` 并同步签名 |

### 6.3 选源 / 调度 / HTTP 基建（4 项）

| 编号 | 位置 | 类型 | 描述与修复建议 |
| --- | --- | --- | --- |
| L-14 | src/stream.py:608、624 | 健壮性 | TikTok 分支 `json.loads(sdk_params_raw)` 与 `resolution.split("x")` 在逐条目循环内无保护，单条脏数据穿透整个候选构建、被装饰器吞成未开播。循环体内单条 try/except 跳过并留 debug |
| L-15 | src/stream.py:1218 | 逻辑 | 网易CC `list(flv_url_list.keys())[0]` 在 cdn 映射为空 dict 时 IndexError → 可录房间判离线。空 dict 时跳过 flv 选择回退 m3u8 |
| L-16 | src/stream_select.py:1299、1301、1333、1337 | i18n | 四条用户可见 `logger.warning` 为裸英文字面量未经 `i18n.tr`，与本文件其余日志口径不符。登记四语目录 + `web/app.js` 后改 tr |
| L-17 | src/proxy.py:281-295 | 逻辑不一致 | `_get_proxy_info_linux` 要求解析出 ip+port，`_is_proxy_enabled_linux` 只判非空；无端口代理写法重现 MIN-20①「显示有代理、实际直连」归因带偏。后者复用 `_split_host_port` 结果作判定 |

### 6.4 弹幕链路（7 项）

| 编号 | 位置 | 类型 | 描述与修复建议 |
| --- | --- | --- | --- |
| L-18 | src/srt_writer.py:118-124、166-172 | 可观测性 | `_open_segment` 捕 OSError 后仅置 `_fp=None`，节流重试失败零日志——SRT 目录被删/磁盘满时弹幕永久全丢且静默，与 WD-03「自愈」目标矛盾。重试失败补 `logger.warning`（带 type_name 与路径） |
| L-19 | src/srt_writer.py:51-52 | 安全加固 | `_sanitize_srt_text` 未覆盖 U+2028/U+2029、U+0085、`\x0b`/`\x0c`、NUL 与超长字段；按 Unicode 行界切分的解析器仍是绕过面。清洗集对齐 `clean_name` 控制字符口径 |
| L-20 | src/base.py:34-42 | 死代码/注释矛盾 | `timestamp_ms` 注释声称「由 DanmakuCollector 收到时注入」，全仓无写入无读取。删除或注明预留 |
| L-21 | src/collector.py:424-428 | 异常吞没 | `except asyncio.CancelledError, RuntimeError: pass` 把平台 `danmaku.start()` 内部冒出的真 RuntimeError 一律归为「正常停止」。改为检查 `_start_task.cancelled()`，非取消的 RuntimeError 补 warning/debug |
| L-22 | src/ttwid.py:189-192 | 窄竞态 | 配置分支 `_cache_ttwid(cfg, proxy_addr)` 后 `return _cached_ttwid` 返回全局镜像，并发下可能返回别的出口的值，与本文件 MIN-2220 自封的不变量矛盾。改 `return cfg` |
| L-23 | src/danmaku_monitor.py:718-721 | 逻辑 | `close_file()` 忽略 `writer.submit("close", path)` 返回值，队列满时 close 指令被静默丢弃、句柄未关而函数「成功」返回。返回 False 时按 drain 超时同语义抛 `TimeoutError` |
| L-24 | src/ws_client.py:327、331；src/collector.py:195、253；src/danmaku_monitor.py:362 | i18n | 用户可见 reason 文案（连接已关闭/重连超限/采集停止/房间已停止监控）未走 `i18n.tr`，非中文语言下面板混入简中。统一经 tr 并补四目录 + `web/app.js` |

### 6.5 Web 面板（7 项）

| 编号 | 位置 | 类型 | 描述与修复建议 |
| --- | --- | --- | --- |
| L-25 | src/web_config.py:779-799 | 并发/注释矛盾 | `update_room_quality` 文件读取在 `_config_write_lock` 之外，注释声称的「防 read-modify-write 交错丢变更」不成立（真实暴露面是 GUI/Web 跨进程）。读移入锁内或改正注释 |
| L-26 | src/recorder_status.py:232-236 | 异常上下文 | 异常日志缺 `{type_name}`，违反 AGENTS 硬要求；web.py:337 同类点位已按口径修过。模板补 `{type_name}` |
| L-27 | src/web_models.py:53 | 注释错误 | 注释引用不存在的符号 `web_api._read_json`（实为 `_read_json_body`），grep 取证断链。改正 |
| L-28 | src/web_api.py:521 | 死代码 | `setattr(app.state, "web_cfg", web_cfg)` 只写不读且即刻陈旧。删除该 setattr 与配套读取 |
| L-29 | src/web_api.py:898-944 | 逻辑缺口 | PUT /api/rooms 不查重新 URL 是否与其它房间重复（POST 有 409 查重），成功后配置出现重复 URL 行、删除/画质操作命中不确定。锁内查重回 409 |
| L-30 | src/web_api.py:125-131 | DoS（待确认） | `_read_json_body` 无请求体大小上限，认证关闭（出厂默认）时局域网任一主机可单请求超大 JSON 耗内存。解析前按 Content-Length 拒绝超限（如 1MB）。验证：起面板后 `curl -d @2GB` 观察内存 |
| L-31 | src/recorder_status.py:82 | 约定 | 三参 `getattr(main, "process_start_time", None)` 违反「模块级已声明属性直接访问」禁令（同文件对 `main.scheduler` 已是正确形态）。改直接访问 |

### 6.6 工具 / 配置 / 通知基建（6 项）

| 编号 | 位置 | 类型 | 描述与修复建议 |
| --- | --- | --- | --- |
| L-32 | src/utils.py:329-333、348-351 | 脱敏防线缺口 | `_make_trace_error_guard` 记录 `str(e)` 不过 `mask_credentials`（76 处平台解析的中心异常漏斗）；现网 raise 点已手工过码故无实锤，属待确认防线缺口。两支 wrapper 的 error_info 拼接处过码 |
| L-33 | src/config_io.py:312-338 | 注释失实 | `_redact_ini_secrets` 注释称「节名与键名保留」，实际 optionxform 小写化、ConfigParser 重写不保留注释与空行，脱敏备份是归一化产物。更正注释或改逐行文本处理 |
| L-34 | src/config_io.py:365 | 非原子写 | `backup_file` 脱敏分支 `open(..., "w")` 直写备份，中途崩溃留半份备份进 6 份轮转、可能恰被用户选来恢复。改走 `utils.atomic_write_text` |
| L-35 | src/config_io.py:284-299 | 逻辑 | `_safe_int`/`_safe_float` 接受 `1_0`、`nan`、`inf` 静默通过；用户误填 `nan` 时磁盘满保护静默失效（比较恒 False）。转换后加 `math.isfinite` 校验，非法告警回默认 |
| L-36 | src/video_postprocess.py:207-210 | 资源泄漏 | 超时分支 `kill()` 后第二次 `communicate()` **不带超时**（notify.py M-5 修复正是为该形态加的防线，此处未对齐）；触发即永久挂住后处理线程且无日志。对齐 notify 口径 `communicate(timeout=10)` |
| L-37 | src/logger.py（注册路径，同 M-13 根因） | 防线退化 | 与 M-13 同根的另一半：`remove_file_sinks` 对已置 None 的 id 无自愈提示。随 M-13 一并处理 |

### 6.7 GUI / 构建 / 安装链（7 项）

| 编号 | 位置 | 类型 | 描述与修复建议 |
| --- | --- | --- | --- |
| L-38 | gui.py:113-122（关键行 120） | 异常吞没/注释矛盾 | `_install_crash_sink` 弹窗路径引用 `i18n_module.tr`，但 sink 在业务 import 之前安装；导入期崩溃（恰是设计目标场景）时 NameError 被吞、弹窗静默失效，与 :119/:141 两段注释互相矛盾。标题改字面量或 `globals().get("i18n_module")` 条件取用 |
| L-39 | gui.py:3570-3571（配合 3518-3526） | 资源空转 | `_drain_log_queue` 只在 messages 非空分支清 `_log_queue_has_data`；哨兵被单独取空且 `_process_ended` 提前 return 时刷新链以 200ms 间隔永久空转。`has_data=False` 移到「队列已取空」的无条件位置 |
| L-40 | gui.py:4321-4340、4359-4366 | 死代码 | `_cleanup_zombie_ffmpeg` 兜底过滤器结构性无法命中（Windows PARENTPID/POSIX pkill -P 都只匹配 GUI 直接派生 ffmpeg，而 ffmpeg 父进程恒为 main.py），给「有第二道网」假象。删除或改按映像名+命令行锚定 |
| L-41 | StopRecording.vbs:294-325、44 | 进程误杀面 | `IsRecorderPython` 对任意命令行含 `main.py|gui.py|web.py` 的 python.exe 命中并整树强杀，其他项目的 `python D:\别的项目\main.py` 会被误杀；文件头「已知残余」只声明了漏杀形态。命中入口名后追加「路径位于 appDir 之下」二次确认（复核既有回归锁） |
| L-42 | src/ffmpeg_install.py:80-81 | 注释漂移 | 注释称可执行文件位于 `execute_dir/ffmpeg/bin/`，实际 copytree 平铺为 `execute_dir/ffmpeg/ffmpeg.exe`（PATH 注入与实际一致）。改正注释 |
| L-43 | src/ffmpeg_install.py:487；src/node_install.py:344 | 不可达分支 | 两处 `except subprocess.CalledProcessError` 不可达：`subprocess.run(..., capture_output=True, timeout=...)` 未传 `check=True` 永不抛。删除该 except 或改捕 OSError |
| L-44 | src/ffmpeg_install.py:257-262；src/node_install.py:163-168 | 完整性缺口（待确认） | TOFU 降级分支在「基准存在但读取失败」时 warning 后 return True 放行安装（fail-open），与 `ffmpeg_master_download.py:289-314` 对同形态定性 SEV-2222 收紧为拒装的口径不一致。触发需「官方文档不可达 ∧ 基准损坏 ∧ CDN 投毒」三重叠加，属防御纵深缺口。**改动前先跑 `pytest tests/test_ffmpeg_install.py` 确认现行为是否被锁**；对齐 SEV-2222 口径 |

### 6.8 独立发行版 standalone（3 项）与 tests/ 抽查结论

| 编号 | 位置 | 类型 | 描述与修复建议 |
| --- | --- | --- | --- |
| L-45 | scripts/douyin_live_recorder_standalone.py:1507-1510 | 孪生漂移/功能 | h265 候选无条件剔除；主线 2026-10-01 已按保存格式放行（TS/MKV/MP4 可直拷 HEVC，回归锁在 `tests/test_stream_select.py`）。standalone 在 mp4/ts 输出下白白丢弃 h265-only 房间可用源。加同判据格式门控 |
| L-46 | scripts/douyin_live_recorder_standalone.py:1852-1855 | 健壮性 | `load_settings` 只捕 `configparser.Error`；ANSI/GBK 编码 config.ini（旧版记事本默认）抛 `UnicodeDecodeError` 启动即崩。同文件 `load_urls`（:1915）已用 `errors="replace"`，两侧不一致。并入 except 降级为默认配置并告警 |
| L-47 | scripts/douyin_live_recorder_standalone.py:134、1742-1746 | 运维 | `logs/standalone.log` 与 `logs/ffmpeg.log` 无上限 append（S-02 只解决了凭据明文，无轮转这一半仍在）；长跑数周可占满磁盘。按体积阈值做单代 `rename .1` 轮转 |

**tests/ 抽查结论（无新增问题计数）**: ① `grep -rn "MUTATION-" tests/ src/ main.py` 零命中，变异验证改动全部还原（R8 机检面有效）；② 全仓未扫出真实形态 token，standalone 孪生锁用明显假值；③ 抽查的临时文件全部落 `tmp_path`（live_collector 五脚本按约定用 `tests/_out_live`）；④ 未发现「patch 掉被测函数本身」的过宽 mock 与吞断言形态，250 处 `setattr` 均符合被测模块命名空间 shim 约定；⑤ `time.sleep` 均为「下界保证」型等待，无裸同步依赖。

## 7. Mimosa 深度安全扫描交叉证据与裁断

- **扫描元数据**: 引擎 Mimosa（静态、`static_only_no_runtime_execution` 边界）；扫描 ID `scan-2026-10-01T18-57-00.175Z-21bb8f2f1ff5`；密封标识 `sha256:e4b90cd15ea9e676ae70696de65818e696da0ef5fecca29951f8bec52afa02b8`；深度 deep；产物含 `findings.json`/`coverage.json`/`seal.json`。
- **原始结果**: 40 项告警（HIGH 25 / LOW 15），运行状态 **inconclusive**（部分分析阶段未完整覆盖），业务逻辑投研候选 0 项。依赖摘要：扫描 104 包，离线情报匹配 1 包。
- **逐类裁断**（审查者逐条定位代码核实，非照单收录）:

| 告警类 | 数量 | 裁断 |
| --- | ---: | --- |
| 命令注入 HIGH | 3 | `scripts/run_gates.py:268` 的 `shell=True` 为开发期门禁工具、输入是仓库自身文档解析出的命令行（`NAME=value cmd` 形态需要 shell 语义），属**受控输入，信息级**（见下方记录③）；`src/javascript/haixiu.js:518`、`liveme.js:349` 为签名脚本内字符串拼接的形态误报，浏览器/Node 沙箱内无进程派生面，**误报** |
| 硬编码凭据 HIGH | 3 | `src/spider.py:4774` 是从 API 响应读取 `token` 字段（`_access.get("value")`），**误报**；`src/spider.py:5846`、`:5848` 为海秀/LiveMe 平台内置**匿名访问票据**（URL 编码的不透明串，任何访客浏览器同持，非用户凭据），带 env/config.ini 覆盖通道、注释明示「改动会导致 401」，**信息级**（记录②） |
| 不安全随机数 LOW | 14 | 全部为签名脚本 nonce、设备 ID、探针节流抖动等**非安全用途**随机（无会话/凭据生成场景）；`ab_sign.py` 随机前缀按 F-19 刻意使用真随机并带回退开关。**误报/接受** |
| 路径穿越 HIGH | 11 | 全部为内部路径拼接（构建产物目录、日志归档、备份文件），路径分量来自常量或用户自身配置，无外部攻击者可控输入进入路径分量。**误报** |
| SSRF HIGH | 7 | `build_exe.py`/`ffmpeg_install.py`/`node_install.py` 的下载 URL 均为**钉定常量**且受 `_ALLOWED_HOSTS` 主机白名单 + SHA256 钉定（fail-closed）+ 官方签名档三重补偿控制；`sync_http.py:23` 为 opener 构造层（当前无生产 importer）。**接受性风险（补偿控制完备）** |

- **裁断结论**: 40 项原始告警中 **0 项构成新增确认漏洞**；3 项降为信息级记录：
  - ① `scripts/run_gates.py:268` 使用 `shell=True`——输入面是仓库自身 AGENTS.md 门禁块，属受控输入；如需进一步收紧可改 argv 列表 + 环境变量注入，非必须。
  - ② `src/spider.py:5846/5848` 平台匿名票据硬编码——属平台前端公开匿名态复刻，建议在注释中补充「匿名票据、非凭据」定性以免后续审计反复误报。
  - ③ 依赖离线情报匹配 1 包：与 AGENTS.md「安全下限」节既有结论一致（下限抬升策略已覆盖），无新增行动项。

## 8. 改进建议与修复优先级

### 8.1 P0（建议本批立即修复，改动面小、风险收益比最高）

1. **SR-01**：`stream_select.py` 两处 `return True` → `return False` + 行为锁（内网分片正文候选不得被选中）。
2. **SR-02**：standalone 重定向逐跳复检 handler + 孪生锁补「重定向到内网」行为锁。
3. **M-01**：`_SECRET_KEYS` 补 `sessdata`/`bili_jct`/`sessionid_ss`/`sid_tt` 四键 + 「值确实消失」断言。
4. **M-02**：main.py 6 处 URL/配置行实参过 `mask_credentials`。
5. **M-15**：`check_nodejs_installed` 补 `TimeoutExpired`/`OSError`（三入口启动崩溃防线）。

### 8.2 P1（中等项，按风险排序）

- **M-03**（XHS 入口白名单）、**M-04**（凭据缓存加锁）、**M-11**（`update_config` 加锁）、**M-12**（`update_file` OSError 契约）——四项均为小改动、消除真实丢写/外泄面。
- **M-16/M-17/M-18**（standalone 终止链、HLS 探测、布尔口径）——随下次 standalone 回灌批次一并处理，回灌时按 AGENTS「主线修复必须核对 standalone 孪生副本」约定在提交说明登记。
- **M-06/M-07**（异常集收窄）、**M-08/M-09**（内存界）、**M-10**（交维护者裁决行为 vs 文档）、**M-13**（sink 注册隔离）、**M-14**（GUI 退出竞态）、**M-05**（真机确认后修）。

### 8.3 P2（轻微项）

- 随对应文件触碰面顺手收敛；建议先做 **L-44**（TOFU fail-open 与 SEV-2222 口径对齐，先确认回归锁归属）与 **L-41**（StopRecording.vbs 误杀面）两项防御纵深缺口。
- **结构性建议**：
  1. **脱敏键型完备性测试化**：`mask_credentials` 的键黑名单是开放集合问题，建议以「平台 Cookie 全键清单 × 形态（query/header/Cookie 头）」矩阵表驱动用例替代逐案补键（M-01/L-07/L-32 同根）。
  2. **standalone 回灌清单机检**：孪生锁目前只覆盖直接候选 URL；建议在 `tests/test_regression_2026_09_22_standalone.py` 增加「主线防线编号 → standalone 对应符号存在性」结构清单，防止本次 SR-02/M-16/17/18 类漂移再次静默发生。
  3. **「内存有界」承诺与实现对齐**：凡注释声称有界（M-08/M-09），实现须按字节上界或删承诺改述为「事后检测」。
- **工作区卫生**：删除未跟踪杂散文件 `markdown-DX-TNHnc.js`（VSCode Markdown 语法文件，疑似误落仓库根目录）。

## 9. 总结性结论

本轮对 DouyinLiveRecorder 工作空间约 44,000 行生产代码、2,458 行独立发行版与测试代码风险面完成了逐文件深审，共产出 66 项发现（严重 2 / 中等 17 / 轻微 47），并完成 Mimosa 深扫 40 项原始告警的逐类裁断（0 项新增确认漏洞）与 basedpyright 静态检查交叉验证（全绿）。

整体工程质量评价：该项目防御密度与注释可追溯性显著高于同类规模项目——历史修复普遍带可复核判据与回归锁编号，原子写原语、Zip Slip 双防护、发布链 fail-closed 钉定、Web 面板认证不变量等核心防线经本轮核查全部成立。两项严重问题均属「防线接线/回灌缺口」而非「防线缺失」：SR-01 是保守回退语义被错误套用到安全拒绝分支的一处分支返回值错位，SR-02 是主线新防线未回灌独立发行版的孪生漂移，修复成本都很低。中等问题集中在三条主线上：**凭据脱敏防线的键型完备性**（M-01 实测复现 + M-02/L-07/L-32 同族）、**共享状态加锁范围漏网**（M-04/M-11/M-12）、**「注释声称的保证」与实现漂移**（M-08/M-10/M-13 及多项轻微）。测试代码抽查未发现掩盖性缺陷，MUTATION 纪律与 tmp_path 纪律执行良好。

建议按第 8 章优先级推进：P0 五项（两严重 + 两脱敏 + 启动崩溃防线）改动面小、应在本批落地并各带回归锁；standalone 三项随回灌批次统一处理；结构性建议（脱敏矩阵测试、孪生回灌机检、内存界承诺对齐）可防止本轮三类问题复发。修复完成前，第 4、5 章所列位置即为后续验证的核对清单。

---

*审查方法与工具口径详见第 2.4 节；所有行号以 2026-10-02 工作区状态为准。带「待确认」标记的条目（M-05、L-04、L-11、L-30、L-44）附验证方法，修复前应先完成验证。*
