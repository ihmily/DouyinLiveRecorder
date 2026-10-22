# 代码审查报告 CODE_REVIEW_2026-09-30

| 项 | 内容 |
| --- | --- |
| 审查日期 | 2026-09-30 |
| 审查对象 | DouyinLiveRecorder 工作空间全部第一方源代码（基准提交 `046bb73` + 工作区未提交修改） |
| 审查方式 | 18 个按模块分组的逐文件深审（12 组生产代码 + 6 组测试代码，每组全文逐行读完）+ 关键发现行号级人工复核 + Mimosa 深度静态安全扫描（交叉证据） |
| 发现合计 | **严重 2 项 / 中等 51 项 / 轻微 160 项**（共 213 项，另有若干标注「待确认」需真机或环境复现） |
| 报告性质 | 静态审查结论。未做运行时验证与真机复现；影响分析基于代码路径推演，置信度已在条目中区分（多数经行号级复核证实，少数标「待确认」） |

---

## 1. 审查概述与背景

本次审查应用户要求对工作空间内全部源代码（Python、JavaScript、Node.js、HTML/CSS、CI 配置等）做全面审查，覆盖代码质量、潜在缺陷、安全漏洞与逻辑错误四类问题，排除第三方依赖目录与构建产物。

DouyinLiveRecorder 是 Python ≥ 3.14 的多平台直播录制工具（ffmpeg 拉流录制 + 弹幕采集 + Web/GUI 管理面板），核心架构为「每房间一个独立线程 + 各自 `asyncio.run()` 事件循环」。审查过程中，项目 `AGENTS.md` 已沉淀的长期约定（PEP 758 无括号 `except` 风格、`#` 行注释、探针契约、斗鱼 HLS 候选、虎牙 FLV-first、兜底装饰器契约等）均按「有意设计」处理，不计入问题，以避免把设计决策误报为缺陷。

审查分三层：

1. **逐文件深审**：18 个独立审查批次，每组附带本仓既定约定清单（防误报）与专项锚点（如 ffmpeg 参数位置约束、探针重试契约、脱敏红线），要求全文读完不得抽查。
2. **行号级复核**：对 2 项严重发现与 5 项代表性中等发现，由主审在报告成文前直接读取源码片段核实（详见第 4、5 章标注「已复核」的条目）。
3. **机扫交叉**：Mimosa 深度静态安全扫描（密封产物，scanId 与封印值见第 7 章）作为补充证据源，其原始发现全部经人工复核后归入本报告相应条目或判定为误报。

---

## 2. 审查范围

### 2.1 生产代码（约 42,000 行）

| 区域 | 文件 | 行数（约） | 结论摘要 |
| --- | --- | --- | --- |
| 根入口 | `main.py` | 5,465 | 中 1 / 轻 8 |
| GUI | `gui.py`、`src/web_tray.py`、`src/ui_theme.py` | 5,176 | 中 1 / 轻 10 |
| 平台解析 | `src/spider.py` | 7,100 | 中 2 / 轻 10 |
| Web 后端 | `web.py`、`src/web_api.py`、`src/web_models.py`、`src/web_config.py` | 3,439 | 中 3 / 轻 11 |
| 选源与调度 | `src/stream_select.py`、`src/stream.py`、`src/room.py`、`src/scheduler.py` | 3,498 | 中 2 / 轻 14 |
| 弹幕链路 | `src/danmaku_monitor.py`、`src/collector.py`、`src/ws_client.py`、`src/srt_writer.py`、`src/ttwid.py`、`src/cookie_cache.py` | 2,743 | 中 3 / 轻 11 |
| HTTP 基建 | `src/async_http.py`、`src/sync_http.py`、`src/http_config.py`、`src/proxy.py`、`src/ab_sign.py` | 2,084 | 中 4 / 轻 9 |
| 工具与配置 | `src/utils.py`、`src/config_io.py`、`src/config_bool.py`、`src/logger.py`、`src/log_archive.py`、`src/notify.py`、`msg_push.py`、`src/recorder_status.py`、`i18n.py` | 3,524 | 中 4 / 轻 10 |
| 安装与后处理 | `src/ffmpeg_install.py`、`src/ffmpeg_master_download.py`、`src/node_install.py`、`src/ffmpeg_proc.py`、`src/video_postprocess.py`、`src/base.py`、`src/__init__.py` | 2,600 | 中 6 / 轻 6 |
| 前端与签名脚本 | `web/app.js`、`web/index.html`、`web/style.css`、`index.html`（根）、`src/javascript/*.js`（4 个自研） | 4,805 | 中 1 / 轻 15 |
| 构建与门禁 | `build_exe.py`、`scripts/*.py`（12 个）、`Dockerfile`、`docker-compose.yaml`、`StopRecording.vbs`、`.github/workflows/*`、`.github/actions/retry` | 约 8,000 | 中 6 / 轻 9 |
| 独立发行版 | `scripts/douyin_live_recorder_standalone.py` | 2,261 | **严重 2** / 中 4 / 轻 11 |

另：`src/http_config.py`（63 行）审查后未发现问题；`src/ui_theme.py` 审查后未发现问题。

### 2.2 测试代码（约 56,200 行）

| 分组 | 文件数 | 结论摘要 |
| --- | --- | --- |
| tests/*.py 组 1（conftest、async_http、build_exe、config 等） | 25 | 轻 5 |
| tests/*.py 组 2（弹幕、ffmpeg、GUI 子进程驱动等） | 23 | 中 2 / 轻 6 |
| tests/*.py 组 3（i18n、日志、notify、proxy 等） | 22 | 中 3 / 轻 5 |
| tests/*.py 组 4（回归锁、spider、scheduler 等） | 26 | 轻 9 |
| tests/*.py 组 5（web_api、stream_select、test_hygiene 等） | 23 | 中 3 / 轻 3 |
| tests/frontend/*.mjs + Python 包装 | 8 | 中 6 / 轻 8 |

### 2.3 排除项

- 第三方与生成物：`typings/`（三方类型存根）、`src/proto/douyin_pb2.py`（protoc 生成，配套 `.pyi` 存根已核对引用面）、`src/javascript/crypto-js.min.js`（三方压缩库，仅做篡改专项检查：全文件模式扫描无网络外发/动态代码构造/系统能力调用，判定为标准 crypto-js 4.x UMD 构建未被改动）、`uv.lock`、`DouyinLiveRecorder.egg-info/`。
- 运行期与工具目录：`node/`、`ffmpeg/`、`downloads/`、`logs/`、`backup_config/`、`__pycache__/`、`.venv`、`.github/` 中除 workflow 与 retry 动作外的杂项。
- 数据与文档：`config/`、`i18n/` 四语目录（数据文件，未逐条审）、`docs/`、`README*`。

---

## 3. 问题统计总览

### 3.1 严重度定义

- **严重**：可被利用的安全漏洞、主流程崩溃、数据损坏或凭据长期落盘泄漏，且在现实可达路径上成立。
- **中等**：常见场景可触发的逻辑错误、竞态、资源泄漏、防线缺口（fail-open）、或测试防线实际失效（恒真/假绿），当前有缓解因素或依赖特定部署形态。
- **轻微**：代码质量、可维护性、低概率边界、展示一致性、i18n 口径等，不影响核心正确性。

### 3.2 统计矩阵

| 区域 | 严重 | 中等 | 轻微 |
| --- | --- | --- | --- |
| main.py（主循环/录制链） | 0 | 1 | 8 |
| GUI（gui/web_tray/ui_theme） | 0 | 1 | 10 |
| 平台解析（spider.py） | 0 | 2 | 10 |
| Web 后端（web.py/web_api/web_config） | 0 | 3 | 11 |
| 选源与调度 | 0 | 2 | 14 |
| 弹幕链路 | 0 | 3 | 11 |
| HTTP 基建 | 0 | 4 | 9 |
| 工具与配置 | 0 | 4 | 10 |
| 安装与后处理 | 0 | 6 | 6 |
| 前端与签名脚本 | 0 | 1 | 15 |
| 构建与门禁/CI | 0 | 6 | 9 |
| 独立发行版（standalone） | **2** | 4 | 11 |
| 测试（6 组） | 0 | 14 | 36 |
| **合计** | **2** | **51** | **160** |

生产代码与测试代码比例约为 37:14（中等），测试侧问题集中在「防线实际失效」（恒真断言、替身打到进程级本体、skip 滥用面）而非数量。

---

## 4. 严重问题（2 项，均已行号级复核）

### S-01 standalone 探针/录制链缺失 SSRF 与本地文件读取防线（孪生漂移）

- **位置**：`scripts/douyin_live_recorder_standalone.py:180-187`（opener 构造）、`:746-756`（抖音候选直收）、`:954-959`、`:1053-1057`（B站/斗鱼候选直收）、`:1456-1494`（ffmpeg 命令无 `-protocol_whitelist`）
- **类型**：安全 / 孪生漂移（SSRF + 任意本地文件读取链）
- **证据片段**（已复核）：

```python
def _build_opener(proxy: str | None) -> urllib.request.OpenerDirector:
    if proxy:
        return urllib.request.build_opener(urllib.request.ProxyHandler({"http": proxy, "https": proxy}))
    return urllib.request.build_opener(urllib.request.ProxyHandler({}))
```

```python
if isinstance(v, str) and v and "h265" not in str(k).lower():
    info_.flv_urls.append(v)          # 平台 API 候选无任何协议/主机校验
```

- **问题**：`urllib.request.build_opener(...)` 即使显式传入 `ProxyHandler`，默认 Handler 集合（含 `FileHandler`/`FTPHandler`/`DataHandler`）仍然生效——这正是主线 `AGENTS.md`「sync_http 的 opener 必须显式按协议白名单构造」条目明令禁止、且主线已于 2026-09-29 补齐同步探针内网判定的形态。独立发行版未回灌三道防线：① 探针可探测 `file://`（FileHandler 返回 200）；② 全部平台流地址候选（来自平台 API 响应，注释自认「不可信输入面」）无协议白名单、无内网/回环/云元数据主机判定（仅虎牙有 `startswith("http")` 检查）；③ ffmpeg 命令无主线 `main.py:3466` 已有的 `-protocol_whitelist`（主线 2026-09-12 审查已显式移除 file 协议）。
- **影响**：三层叠加成完整利用链——平台 API 响应被控（恶意/被劫持代理、接口投毒、MITM）时，`file:///C:/Users/<user>/...` 经 FileHandler 探针 200 → GET 复核放行 → ffmpeg 按默认协议白名单把本地媒体文件「录制」进 `downloads/`（本地数据外带）；`http://169.254.169.254/...`（云元数据）与内网 http 服务同理可被拉取落盘。末位候选「仅告警放行交 ffmpeg 定夺」的既有语义进一步保证该链必然走通。
- **修复建议**：① `_build_opener` 改为显式 Handler 白名单构造（`HTTPSHandler` 必填实参，对齐主线 `sync_http` 口径）；② `select_source_url`/`validate_stream_url` 入口加「协议 ∈ {http, https} 且主机非内网/回环/链路本地/云元数据」判定，违规候选直接丢弃；③ ffmpeg 命令补 `-protocol_whitelist`（与 `main.py:3466` 逐字对齐）；④ 补回归锁（可参照 `tests/test_regression_2026_09_29_wp_b_netguard.py` 的行为锁形态）。

### S-02 standalone 完整 ffmpeg 命令（含 Cookie 头与带 token 流地址）逐轮写入日志且无轮转

- **位置**：`scripts/douyin_live_recorder_standalone.py:1543`、`:1552`
- **类型**：安全 / 凭据长期落盘
- **证据片段**（已复核）：

```python
cmd_log = " ".join(build_ffmpeg_cmd(ffmpeg_bin, url, out_path, platform, cookies, duration, fmt))
...
logf.write(f"\n===== {time.strftime('%Y-%m-%d %H:%M:%S')} =====\n{cmd_log}\n")
```

- **问题**：`cmd_log` 含 `-headers` 实参——其中 `record_headers(platform, cookies)` 会把用户配置的平台 Cookie（抖音/B站等登录态会话凭据）拼进 header 串，流 URL 还带 wsSecret/anti_code/auth 等反盗链 token。该命令原文每次录制写入 `logs/ffmpeg.log`（append、无轮转、长期留存）。主线从不落盘完整命令（`main.py` 只记输出路径），且 `stream_select.py` 全部 URL 过 `mask_credentials`（MID-N32）。这与仓库「写入配置或日志前必须脱敏——凭据长期落盘等于泄漏」的红线直接冲突。
- **影响**：平台登录态 Cookie 明文落盘，任何能读该日志的进程/人员/同步上传动作都能获得各平台登录凭据；单文件发行版的用户群体恰是最可能被指导「把日志发出来求助」的人群。
- **修复建议**：写盘前脱敏——`-i` 值改用 `strip_query(url)`；`-headers` 值整体替换为占位符（如 `<headers:N chars>`），仅保留参数形状供排障；或对整条 `cmd_log` 过一遍等效于 `utils.mask_credentials` 的脱敏（standalone 无 src 依赖，需内置同口径实现）。

---

## 5. 中等问题（51 项，按区域详述）

> 每项给出：位置、类型、问题与影响分析、修复建议。标注「已复核」的条目为主审在成文前读取源码核实过；标注「待确认」的条目依赖特定环境/真机复现，置信度略低但机理成立。

### 5.1 main.py（1 项）

**M-01 磁盘满暂停恢复后，全部房间永久不再被拉起（状态残留击穿可逆暂停语义）** — 已复核

- 位置：`main.py:5099/5123-5133`，联动 `src/notify.py:325-333`
- 类型：逻辑错误 / 状态残留
- 问题与影响：磁盘低于阈值时置 `exit_recording=True` 使全部房间线程退出；而线程出口的 `remove_room_from_running`（`notify.py:329`）在 `exit_recording=True` 时直接跳过 `running_list` 清理（其注释把 `exit_recording` 当作「进程整体退出」，磁盘满暂停并非进程退出）。恢复分支（`elif disk_limited:`）只复位 `disk_limited`/`exit_recording` 两个标志、不清 `running_list`，而主循环拉起条件是 `url not in running_list`。结果：磁盘满事件（默认阈值仅 1GB，录制工具下并不罕见）结束后所有 URL 永久残留于 `running_list`，任何房间都不再被拉起，直到重启进程；恢复日志宣称「继续按配置拉起房间」与实际行为相反。
- 建议：恢复分支在复位标志后清空 `running_list`（或按 `seen_urls`/配置核对清理）；或将 `remove_room_from_running` 的跳过条件改为仅真进程退出信号场景。

### 5.2 GUI（1 项）

**M-02 GUI 配置保存是「弱化原子写副本」，POSIX 下会把 0600 权限还原（SEV-2211 同族）**

- 位置：`gui.py:975-998`（`_save_text_to_file`，两条保存路径共用）
- 类型：安全 / 资源（权限回退）
- 问题与影响：与 `src/utils.atomic_write_text`（唯一加固实现）相比缺 fsync、且 `os.replace` 前不保留目标文件原有 mode。`src/web_config.py` 的 SEV-2211 修复注释已把同形态缺陷定性为「每次写回把 `os.chmod(0o600)` 收紧静默还原，含全部平台口令/cookie 的配置变为同机任意本地用户可读；掉电可留 0 字节配置」。GUI 明确支持 Linux（`xdg-open` 分支），在该部署形态下保存 config.ini / URL_config.ini 即触发。
- 建议：`_save_text_to_file` 改为委托 `src.utils.atomic_write_text`（GUI 已导入 src，无导入障碍）；补「保存后权限仍为 0600」回归锁。

### 5.3 平台解析 spider.py（2 项）

**M-03 浪Live/映客/京东仍要求 FLV+HLS 双路齐备，与 MID-2212 修复口径相反**（待确认平台是否出现单路形态）

- 位置：`src/spider.py:6042`（浪Live）、`:5580`（映客）、`:6750`（京东）
- 类型：逻辑错误（MID-2212 同族残留）
- 问题与影响：本文件已在微博（4553）与 Look（3840）把「要求 FLV/HLS 双路齐备才判开播」改为「两路皆空才判无源」（`or` → `and`），但这三处仍是旧 `or` 形态。若平台出现只下发单路地址的房间，每轮被判「未开播」，表现为「在播却永久漏录」。
- 建议：与 4553/3840 定稿形态对齐改为 `and`；真机各验证一次（判定列「待确认」的原因是单路形态是否实际出现未经真机证实）。

**M-04 小红书短链解析的重定向跟随会把会话 sid 送往跳转目标**（待确认可利用性）

- 位置：`src/spider.py:2441`、`:2449-2450`
- 类型：安全 / 凭据外送（边界待确认）
- 问题与影响：SEV-2214 双闸只约束解析落地页之后的请求；而 `xhslink.com` 短链解析这一次 `async_req(redirect_url=True)` 内部 `follow_redirects=True`，httpx 跨域重定向会剥 `Cookie`/`Authorization` 但**不剥自定义头**——`xy-common-params`（内含会话 sid）会被转发到每个跳转目标。`async_http` 逐跳钩子只拦非白名单协议与内网目标，公网攻击者 host 放行。可利用性依赖链上存在开放重定向跳板。
- 建议：短链解析这一次请求剥离 `xy-common-params`（落地解析不需要 sid 鉴权），或解析后仅当域族白名单通过才在后续请求带回 sid。

### 5.4 Web 后端（3 项）

**M-05 Web API 请求体无大小上限，免鉴权端点存在内存 DoS 面**

- 位置：`src/web_api.py:125-131`（`_read_json_body`）
- 类型：资源 / 健壮性
- 问题与影响：`request.json()` 无 Content-Length 校验、无流式截断，把整个 body 缓冲进内存。`/api/login` 在鉴权白名单内，认证开启前即可达；`web_host=0.0.0.0` 部署下，超大 JSON（数百 MB～GB 级）即可造成内存暴涨/OOM。
- 建议：`_read_json_body` 先检查 `content-length` 上限（如 1 MB）超限直接 413；并对 `ConfigUpdate.value`/`RoomCreate.name` 等字段加最大长度。

**M-06 Web 密码三处空白口径不一致：设置含首尾空格的密码后认证配置永久自锁** — 已复核

- 位置：`src/web_api.py:1210-1215`（reauth 用 strip 值）对照 `:1221-1223`（哈希用未 strip 值）
- 类型：逻辑错误（可致自锁）
- 问题与影响：写入侧 `hash_web_password(value)` 基于**未 strip** 的值，复验侧把 `reauth_password` **strip 后**再校验，`login` 又用未 strip 值。用户设置首尾含空格的密码（粘贴/输入法尾随空格是常见来源）后可以正常登录，但此后所有需要 reauth 的写请求（改 `web_password`、`web_auth_enable`）永远 403——认证配置经面板永久不可改，只能手工编辑 config.ini。
- 建议：统一口径（写入前 `value = value.strip()` 再哈希，与敏感键空值守卫同源）；补回归锁「设置含首尾空格的密码后 reauth 必须成功」。

**M-07 行内注释保留启发式与 configparser 读侧口径分叉，含 ` #` 的配置值二次写入被静默污染**

- 位置：`src/web_config.py:1191-1200`
- 类型：逻辑错误 / 数据损坏
- 问题与影响：写侧把旧值中首个 ` #`/` ;` 之后的内容当行内注释并原样追加到新值后；但读取侧 `configparser`（默认不开 `inline_comment_prefixes`）把同一串当作**值的一部分**。旧值 `a #b` 更新为 `c` 后实际落盘 `c #b`——平台 Cookie、含井号 token 等凭据被静默污染，平台鉴权莫名失效且无从排查。F-23 的引号定界修复只覆盖带引号值。
- 建议：检测到「configparser 读到的完整旧值 ≠ 剥离注释后的前半段」时不再保留行内注释；或写入值统一加引号（与 F-23 配套）；至少对 `SENSITIVE_SECTIONS` 内的键禁用注释保留逻辑。补回归锁「值含 ` #` 的键二次更新后读回值等于新值」。

### 5.5 选源与调度（2 项）

**M-08 stream_select 派生跳内网闸门是独立字面量正则，漏掉十进制/十六进制/八进制 IP、IPv4-mapped IPv6、CGNAT 与云元数据主机名**

- 位置：`src/stream_select.py:381-393`（`_PRIVATE_HOST_PATTERN`，接线点 517/546/554）
- 类型：安全 / URL 校验绕过
- 问题与影响：派生跳（master playlist 变体、媒体分片）的内网判定只做字面量前缀匹配，漏掉 `http://2130706433/`（十进制 127.0.0.1）、`0x7f000001`、`0177.0.0.1`、`[::ffff:127.0.0.1]`、CGNAT `100.64.0.0/10` 及 `metadata.tencentyun.com` 等内部主机名——这些形态**无需 DNS 解析即可离线判定**，共享判定 `web_config._parse_ip_literal`/`_internal_ip_reason` 全部覆盖。虎牙候选被 `stream.py:955-960` 刻意降级为 http，网络路径上的 MITM 或被劫持 CDN 只要在播放列表正文塞一行 `#EXT-X-STREAM-INF` + 十进制 IP 变体 URL，探针即向本机/内网发 GET，构成内网存活与端口探测 oracle（跨 scope 已剥 Cookie，无凭据外泄；最终交付 ffmpeg 的 `_accept_source` 走强判定，缺口仅在探针层）。这也是全仓唯一一份独立内网名单，与「判定复用 async_http 同一份 helper、禁止另写内网名单」的既定方向相悖。
- 建议：`_is_derived_hop_allowed` 改为复用 `src.async_http.internal_stream_target_reason`；若确要保留零 DNS 的低成本路径，应抽共享的「纯字面量 + 内部主机名」判定函数供两处使用。

**M-09 room.py 三处裸构造 `AsyncClient` 跟随重定向，不在「重定向逐跳复检两个合法接线点」内**（待确认边界划分意图）

- 位置：`src/room.py:90-91`、`:173`、`:179`、`:201`、`:229`、`:275`
- 类型：安全 / 重定向跟随失控
- 问题与影响：`get_sec_user_id` 与 `get_unique_id` 跟随**用户输入的抖音短链/分享页**重定向链，既不做 `internal_stream_target_reason` 判定也不挂逐跳复检钩子。若抖音侧出现开放重定向/短链被劫持，本机按 302 链向任意目标（含内网/回环/云元数据）发 GET。ttwid Cookie 在首次重定向 GET 之后才注入、httpx 跨源重定向自动剥 Cookie，故无凭据外泄，残余为 SSRF 连接与响应内容影响解析结果。
- 建议：解析链改经 `async_http` 的 client 工厂（同一 `event_hooks` 钩子），至少对初始用户 URL 补一次 `internal_stream_target_reason` 判定；三处裸构造收敛为单一工厂。

### 5.6 弹幕链路（3 项）

**M-10 cookie_cache singleflight 拉取失败日志未脱敏异常文本（Twitch 工厂直接可达）**

- 位置：`src/cookie_cache.py:344-352`
- 类型：安全 / 凭据泄漏
- 问题与影响：`singleflight` 的 factory 异常文本未过 `mask_credentials`，与同文件 `fetch_cookies`（WD-01 注释明言异常文本常内嵌完整请求 URL 含签名/鉴权查询串，必须脱敏）口径不一致。`spider.py:342-353` 的 Twitch Client-Id 工厂直接 `await async_req(...)` 不经内部捕获，httpx/代理类异常文本会携带出口代理原串或完整请求 URL，原样落进 300KB 轮转、多份保留的日志。
- 建议：改为 `e=utils.mask_credentials(str(e))`，与 `fetch_cookies` 对齐。

**M-11 cookie_cache 等待者超时不注销在途登记；拉取者线程死亡后该 key 永久在途**

- 位置：`src/cookie_cache.py:165-177`（`fetch_cookies`）、`:322-332`（`singleflight`）
- 类型：并发 / 资源泄漏
- 问题与影响：等待者超时后不摘除自己在 `_inflight[key]`/`_generic_inflight[key]` 里的 `(loop, future)` 登记；该登记只在拉取者完成/取消时统一 pop。若拉取者线程被硬杀或永久挂起（恰是模块注释设想的「asyncio.run 被硬杀」场景），该 key 永久处于「在途」态——此后所有调用方只能走「登记等待 → 超时 → 空结果」，凭据自愈链直至进程重启被打断，且超时登记元组无界累积。
- 建议：超时分支在 `_cache_lock` 内摘除自身登记；摘除后发现列表为空时允许自己接任拉取者。

**M-12 SRT 打开失败零日志、条目静默丢弃：磁盘满/目录被删时整场弹幕字幕丢失且两条既有告警链均不触发**

- 位置：`src/srt_writer.py:106-124`（`_open_segment`）、`:193-195`（`write`）
- 类型：健壮性 / 可观测性
- 问题与影响：`_open_segment` 失败静默吞掉（零日志），`write()` 丢弃分支无计数无告警。collector.start() 的 warning 不触发（start 不再抛 OSError）、`_srt_writer_loop` 的 WD-03 聚合告警不触发（write 在此路径不抛异常）——本仓为「弹幕丢失」场景建的两条可观测链在此全部失效。
- 建议：`_open_segment` 失败记 warning；`write()` 丢弃分支复用 collector 的时间窗聚合告警或维护丢弃计数。

### 5.7 HTTP 基建（4 项）

**M-13 sync_http opener 与 abroad 落地复核只查 scheme，无内网逐跳复检**（当前无生产 importer，接线即成洞）

- 位置：`src/sync_http.py:65-79`、`:140-158`、`:352-375`
- 类型：安全 / SSRF
- 问题与影响：白名单 opener 与 abroad 分支的落地复核只做 scheme 判定；`sync_req(公网URL)` 遇 302 → `http://127.0.0.1:6379/` 或 `http://169.254.169.254/latest/meta-data/` 这类**同 scheme 内网跳转**时，`HTTPRedirectHandler` 会完整跟随并把内网响应体交给调用方。经复核本模块当前无生产 importer（仅 tests 引用），现实暴露面为零，故评中等；一旦接线即应升严重。
- 建议：接线前给两支 opener 增加自定义 `HTTPRedirectHandler`（`redirect_request` 里调 `async_http.redirect_hop_rejection_reason`），或把落地复核扩展为 scheme + 内网双判定。

**M-14 sync_http 的 HTTPError(400) 分支读响应体无上限，绕过 SEV-2226 双上限防线**

- 位置：`src/sync_http.py:394-403`
- 类型：健壮性 / OOM 向量
- 问题与影响：读侧 `_read_capped` + 解压侧 `_gunzip_capped` 双上限只覆盖成功路径；HTTPError 分支 `e.read()` 无上限——恶意/被劫持服务器返回 400 + 超大 body 即可让调用线程全量读入内存，MemoryError 属 BaseException 连外层 `except Exception` 都兜不住。
- 建议：HTTPError 同样套用 `_read_capped(e, _MAX_RESPONSE_BYTES, ...)`。

**M-15 async_http 逐跳复检钩子在事件循环内同步 getaddrinfo，DNS 故障时房间循环秒级停摆**

- 位置：`src/async_http.py:587-594`（联动 `src/web_config.py:437-441`）
- 类型：并发 / 阻塞
- 问题与影响：response 事件钩子挂在每支缓存 client 上、对每个响应（含每一跳）同步执行 `_redirect_hop_rejection_reason`；无代理且 host 非 IP 字面量时走到 `socket.getaddrinfo`——在事件循环线程内**同步阻塞**。每跳重新解析本身是登记过的反重绑定设计，但「事件循环内同步解析、无 executor offload」未在残余风险登记。DNS 故障/污染/超时环境下可达数秒，期间该房间循环内所有协程（弹幕监控、调度回写）全部停摆。
- 建议：`_guard` 改为 `await asyncio.get_running_loop().run_in_executor(None, _redirect_hop_rejection_reason, hop_url, proxy_addr)`；或登记为已知权衡并说明理由。

**M-16 sync_req 的 data/json_data 同传时两条出站分支语义相反（async_req 已把同传定为编程错误）**

- 位置：`src/sync_http.py:313-323`（代理分支 data 优先）与 `:341-347`（无代理分支 json 覆盖 data）
- 类型：逻辑不一致
- 问题与影响：同一函数内，同传时代理分支 requests 按 data 优先（json 静默丢弃），无代理分支却让 json 覆盖 data——同一调用在「配代理/不配代理」下发出的请求体不同。当前全仓无同传调用点且本模块无生产 importer，属 latent 防线缺失。
- 建议：对齐 `async_req`——入口 `data is not None and json_data is not None` 时 raise ValueError；顺带把标量 `json_data` 在无代理分支被静默丢弃（`:346-347` 只认 dict/list）一并修掉。

### 5.8 工具与配置（4 项）

**M-17 `_SECRET_HEADER_RE` 驼峰分支两个 lookbehind 互斥、恒不匹配（死代码），header 形态驼峰复合凭据键不脱敏** — 已复核

- 位置：`src/utils.py:924-934`
- 类型：安全 / 脱敏缺口
- 问题与影响：`(?<![A-Za-z0-9"'])` 这道防「`https:` 被抹」的 guard 挂在了驼峰分支上，而驼峰分支自身还有 `(?<=[a-z])`——前一处要求「前字符是小写字母」、后一处要求「前字符不是字母数字」，同一位置互斥，该分支恒死。按注释本意 guard 应加在 plain 分支。后果：请求头形态（`键: 值`）日志中，驼峰转折进凭据后缀且整段键名不在黑名单的凭据（如 `myToken: xxx`、`sessionKey: abc`）不被抹，明文进轮转日志；查询串形态 `_SECRET_QUERY_RE` 无此 guard、驼峰分支正常，两形态防护强度不一致。
- 建议：把 guard 从驼峰分支移到 plain 分支；在 `tests/test_regression_2026_09_22_utils.py` 补 header 形态驼峰复合键「值确实消失」断言。

**M-18 `replace_url` 的 `elif old in line` 是无边界子串替换，自动注释房间时误伤 ID 前缀重叠的兄弟房间** — 已复核机理

- 位置：`src/utils.py:781-791`
- 类型：逻辑错误 / 配置损坏
- 问题与影响：与函数头注释「逐行匹配整行内容，避免子串替换误伤」直接矛盾。唯一生产调用点是 `spider.py:4968`（花椒地址失效自动注释，`new="#" + url`）：当另一房间 URL 恰以本 URL 为前缀（如 `…/l/123456` 与 `…/l/1234567`，数字 ID 前缀重叠现实存在）时，长 ID 行被整行 `replace` 成 `"#" + 短URL + "7…"`——兄弟房间被静默注释掉（停止监测）。
- 建议：复用 `config_io._rewrite_line_by_match` 的段级匹配口径（按逗号切段、仅整段等于 old 才替换）；补前缀重叠行变异验证用例。

**M-19 logger 双 sink 注册部分失败时已注册 sink 的 id 被置 None 未移除，后续重复注册致同文件多句柄、轮转冲突、日志双写**

- 位置：`src/logger.py:285-293`（同型缺陷见 `:226-241` `add_file_sinks`）
- 类型：资源泄漏 / 日志双写
- 问题与影响：若 streamget sink 注册成功、playurl sink 抛 `OSError`，except 把已成功注册的 id 置 None 但不移除——句柄泄漏且 id 永久丢失。此后每次 `archive_runtime_logs(reopen_streams=True)`（Web 停止录制路径）调 `add_file_sinks()` 都会再注册一个新 streamget sink：同文件多句柄并存 → 日志行双写；Windows 上多句柄使 300KB 轮转的 `os.rename` 抛 WinError 32，正是 AGENTS「轮转永不成功、文件日志静默丢失」描述的形态。
- 建议：except 分支先检查已注册 id 则 `logger.remove(id)` 再置 None；两处同改。

**M-20 `run_node_script_async` 缺 `run_js_async` 同款外层 `wait_for` 双保险，Windows 孙进程握管道可永久挂死房间线程**

- 位置：`src/utils.py:215-247`
- 类型：并发挂死
- 问题与影响：`subprocess.run` 超时 kill 的是直接子进程，其内部超时分支的第二次 `communicate()` 无超时——node 脚本起过握住管道写端的孙进程时，`asyncio.to_thread` 线程永久挂住、协程永远 await（`run_js_async` 注释已把该形态定性为「本仓最忌的静默挂死」并因此加双层预算，此入口漏配）。单房间选源轮永不返回、不归还网络信号量，调度容量被永久吃掉一格。
- 建议：补 `await asyncio.wait_for(asyncio.to_thread(_sync_run), timeout=timeout)`，并注明外层只救 await 侧、子进程回收仍靠内层 timeout。

### 5.9 安装与后处理（6 项）

**M-21 ffmpeg TOFU 基准文件「存在但读取失败」时跳过校验继续安装（fail-open），与 master 模块 SEV-2222 定稿相矛盾** — 已复核

- 位置：`src/ffmpeg_install.py:257-262`
- 类型：安全 / fail-open
- 问题与影响：该分支前提正是「官方哈希没拿到」（TOFU 旁路基准是唯一一道完整性检查）；基准文件存在却读不出（被替换成同名目录、被 AV 锁住等）时只 warning 后 `return True`，带毒 zip 照常解压安装。`ffmpeg_master_download.py:289-314` 对同形分支已按 SEV-2222 定为「删包拒装」——master 注释里「前面还有一道官方哈希」的理由在这个降级分支内不成立。
- 建议：对齐 master 口径：读失败 → 删包拒装（至少区分「读失败」与「不存在」，前者必须 fail-closed）。

**M-22 node 新下载 zip 未经形态校验直接记账，挑战页可污染 TOFU 基准 → 真包被永久拒装**

- 位置：`src/node_install.py:239-262`
- 类型：安全 / 逻辑
- 问题与影响：`is_valid_zip` 形态校验只存在于缓存复用分支（:230）；这正是 `ffmpeg_install.py:306-314` 长注释描述、2026-09-22 已修（`TestDownloadedPayloadMustBeArchive`）的同一形态，node 侧漏改。npmmirror 返回 200+HTML 挑战页且 nodejs.org SHASUMS 恰好取不到（TOFU 降级——国内环境常态）时，HTML 的哈希被写进旁路基准；下次拿到真包反而被判「篡改」永久拒装，只能手工删 `.sha256` 文件。
- 建议：`_check_or_record_zip_sha256` 之前补 `is_valid_zip` 校验，与 ffmpeg 侧对齐。

**M-23 `check_node()` 异常面收窄致 `import src` 崩溃：node 挂起/无权限时三种入口启动即崩**

- 位置：`src/node_install.py:389-397`，触发点 `src/__init__.py:37-39`
- 类型：逻辑 / 健壮性
- 问题与影响：注释声称「其它异常也吞掉返 False」，实现只捕 `FileNotFoundError`；`TimeoutExpired`/`PermissionError` 都会穿出。`check_node()` 在 `src/__init__.py:39` 于 **import 期**被调用——异常会让 `import src` 直接失败，GUI/CLI/Web 三种入口在启动瞬间崩溃而非走「自动安装/手动提示」。对比 `check_ffmpeg_installed`（`ffmpeg_install.py:664-678`）显式接住了这两类。
- 建议：补 `except subprocess.TimeoutExpired` 与 `except OSError`（warning 后返 False），与 ffmpeg 侧同构；或修正注释。

**M-24 node 版本号取自第三方页且零格式校验即拼 URL 与本地文件名：可被降级装旧版，含 `..\` 时可越出安装目录写文件**

- 位置：`src/node_install.py:199-218`
- 类型：安全 / 纵深缺失
- 问题与影响：版本号来自 nodejs.cn 页面正则 `v.*?`，对内容零约束：① 可注入旧的真实版本号实施降级攻击（旧版本在 npmmirror 与 nodejs.org SHASUMS 两边都真实存在，哈希校验照样通过）；② 构造含 `..\` 的版本串可把 `full_file_name` 变成带路径分隔符的文件名，Windows 下可写出 `execute_dir` 之外（需该 URL 请求 200 才落盘，条件叠加但属纵深缺失）。信任链里「版本选择」由非权威第三方决定，完整性校验只能证明「是官方某个真实构建」，不能证明「是应装的版本」。
- 建议：对抓取结果强格式校验（`re.fullmatch(r"v\d+\.\d+\.\d+", version)`，不匹配即失败）；长期改从 nodejs.org 官方端点获取版本号。

**M-25 node zip 直接解压进应用根活目录，TOFU 场景可覆盖 `_internal/` 内任意文件**

- 位置：`src/node_install.py:262`
- 类型：安全 / 纵深防御
- 问题与影响：`utils.unzip_file` 的 Zip Slip 校验只防「逃出目标目录」，不防解压目标目录内部同名覆盖——TOFU 场景（nodejs.org 清单不可达 + 首次记账）下被替换的 npmmirror 包可借顶层条目覆盖应用目录内任意文件（main.py、DLL、其它脚本）。ffmpeg 两条路径都是先解压到 `TemporaryDirectory()` 再只拷 `bin/`，暴露面小得多。与 M-22/M-24 叠加时后果是任意代码执行级。
- 建议：与 ffmpeg 流程对齐——先解压到临时目录，校验顶层结构后再落位。

**M-26 导入期 `check_node()` 使 GUI 父进程与录制子进程可无锁并发安装，同一可预测 zip/基准文件竞态可写坏基准**

- 位置：`src/__init__.py:37-39`（配合 `src/node_install.py:218`、`:267`）
- 类型：并发
- 问题与影响：任何导入 src 的进程都在导入期跑 `check_node()`；node 缺失首启场景下 GUI 父进程与录制子进程（`child_process_env` 不设 `DOUYIN_SKIP_RUNTIME_CHECK`）各自触发一次无锁并发下载——可预测路径 `execute_dir/node-vX-win-x64.zip` 交错写、并发写 `.sha256` 基准、并发 rename，交错结果双方都拿到残缺包 → 基准被写坏 → 下次真包被 TOFU 判「篡改」永久拒装。
- 建议：安装路径加跨进程文件锁，或「下载到 `tempfile.mkstemp` 私有名 → 校验后原子落位」；GUI 侧可设 `DOUYIN_SKIP_RUNTIME_CHECK=1` 把安装责任交给录制子进程。

### 5.10 前端（1 项）

**M-27 语言切换会清空已渲染的配置表单，未保存编辑静默丢失**

- 位置：`web/index.html:152` + `web/app.js:591-604`、`:1532`
- 类型：逻辑错误（数据丢失）
- 问题与影响：`#config-container` 挂着 `data-i18n="loading"`，而 `loadConfig()` 只重写其 `innerHTML`、属性仍在；任何语言切换（`setLanguage` 成功/失败路径均调 `applyTranslations()`）都会把该容器 `textContent` 覆盖成「加载中...」。用户在配置页有未保存修改时切换语言，编辑内容静默丢失；点保存走 0 输入分支显示「无变更」，无报错。
- 建议：`loadConfig` 渲染成功后 `container.removeAttribute('data-i18n')`；或把初始 loading 文案放独立子元素。

### 5.11 构建与门禁 / CI（6 项）

**M-28 `check_annotations.py --snapshot` 主目录防护方向反了：仓库克隆在主目录下时快照功能恒被拒**

- 位置：`scripts/check_annotations.py:407`
- 类型：逻辑错误
- 问题与影响：`home in resolved.parents` 判的是「resolved 位于主目录**之内**」，而紧随其后的 cwd 检查用 `resolved in cwd.parents`（正确地拒绝 cwd 的**祖先**），两条相邻检查方向相反。就 `rmtree` 危害而言真正要拒的是主目录本身及其祖先；主目录下的子目录 rmtree 只删自身。Windows/Linux/macOS 最常见的「仓库克隆在用户主目录下」布局中，模式 2 `--snapshot` 对工具自己提示的合法路径一律拒绝，功能不可用（本机 `D:\DouyinLiveRecorder` 不在主目录下故未暴露）。
- 建议：改为与 cwd 检查同向：`resolved == home or resolved in home.parents`。

**M-29 一次性维护脚本 ROOT 硬编码指向另一个目录 `D:/DouyinLiveRecorder-dev`**

- 位置：`scripts/patch_i18n_2026_09_12.py:23`
- 类型：逻辑错误（写型动作打到仓库之外）
- 问题与影响：所有读写在那个路径上进行，行 228 的 `compile_po` 也以该目录为 cwd。在没有该目录的机器上运行即崩栈；若机器上恰好存在旧目录，会**静默改写另一份 checkout** 的四语目录。另用 PATH 上的 `python` 而非 `sys.executable`。
- 建议：改 `Path(__file__).resolve().parent.parent`；该一次性脚本已完成使命，按仓库清理惯例删除或归档。

**M-30 冒烟测试等待期不排空子进程 stdout 管道：日志量大时子进程写管道阻塞＝冻结态被当「存活」**（待确认触发概率）

- 位置：`build_exe.py:1485/1489`
- 类型：资源 / 健壮性
- 问题与影响：`_launch` 把 stdout+stderr 接进 PIPE，`smoke_cli`（25s）/`smoke_web`（最长 90s）/`smoke_gui`（8s）等待期间无人读管道，直到 `_finish` 的 `communicate()` 才读。子进程输出超过 OS 管道缓冲（Windows 约 64KB）即阻塞在 `write()` 上——被冻结的进程看起来仍存活，真崩溃堆栈也可能停在缓冲里延迟可见。
- 建议：等待循环改为逐行排空（另起线程或读取循环兼做超时）。

**M-31 冒烟 `expect_alive=True` 不断言存活：CLI/GUI 入口提前干净退出（rc=0）通过冒烟**

- 位置：`build_exe.py:1552`
- 类型：逻辑错误（门禁假绿面）
- 问题与影响：对「应长期运行的入口」只在 rc≠0 时判失败；进程在等待期内干净退出（rc=0）直接通过。`smoke_web` 有 HTTP 探活兜底，CLI/GUI 没有等价见证——「入口启动后立即静默退出」类回归（空配置提前 return、监控循环条件写反）在 CI 冒烟恒绿，与本仓「假绿即门禁失效」口径相悖。
- 建议：`expect_alive` 且进程提前退出时无论 rc 均判失败（或至少断言「存活至超时」）。

**M-32 `dorny/paths-filter@v4` 浮动 ref，自动运行在外部 PR 上，未按本仓 MIN-17 判据钉 SHA 或登记豁免**

- 位置：`.github/workflows/ci.yml:179`
- 类型：供应链 / 浮动 ref
- 问题与影响：本仓 MIN-17 判据是「不可信输入 × 第三方非认证动作 × 浮动 ref」需隔离或钉 SHA（issue-translator 已因此降级、trivy-action 已 SHA 钉定）。`paths-filter` 在每次 push/PR（含外部贡献者 PR）自动运行、ref 为浮动 major tag、未见钉定或豁免登记。tag 被上游接管时，外部 PR 即可让替换代码以 `contents: read` 在全仓 checkout 上运行。
- 建议：当场核对后换 40 位 commit SHA，或在 workflow 注释里显式登记接受理由。

**M-33 `softprops/action-gh-release@v3` 浮动 ref 且持有 `contents: write`——全流水线「浮动第三方 ref × 最高权限」的唯一直接组合**

- 位置：`.github/workflows/build-release.yml:227/413/529`
- 类型：供应链 / 浮动 ref
- 问题与影响：发布链三处（release-create 预建、build 直传附件、release 收尾）都用该第三方动作的浮动 major tag。tag 接管即等于发布链被接管：可改写 Release 内容/注入恶意附件，与 SEV-10 钉定体系不匹配。
- 建议：与 trivy-action 同口径换 commit SHA；至少在文件头登记接受理由与核对日期。

### 5.12 独立发行版 standalone（4 项）

**M-34 斗鱼 getH5PlayV1 表单体手工 f-string 拼接 enc_data——主线 MID-49 修复未回灌**

- 位置：`scripts/douyin_live_recorder_standalone.py:1035-1038`
- 类型：孪生漂移 / 逻辑错误
- 问题与影响：enc_data 是 base64 产物，其中 `+ / = / %` 会破坏表单字段结构（服务端截断取值 → 签名失败）；主线 `src/spider.py:1644-1653` 的 MID-49（2026-09-20）已实证并修复同一形态（改 urlencode + enc_data 缺失守卫），独立副本未回灌。斗鱼取流可能间歇性失败且被归因为「接口错误」。
- 建议：改 `urllib.parse.urlencode` 构造 body，并补 enc_data 为空时的告警跳过分支。

**M-35 探针异常消息内嵌完整 URL（含反盗链 token），外层日志绕过 strip_query 脱敏**

- 位置：`scripts/douyin_live_recorder_standalone.py:242`、`:1331-1333`
- 类型：凭据泄漏（轻）
- 问题与影响：`http_probe` 的 RuntimeError 内嵌完整 URL（含 query 中的 CDN token）；外层 catch 把 `{e}` 原样打进日志——文件内其余所有探针路径都刻意用 `strip_query(url)`，唯独异常文本绕过。虎牙 antiCode、斗鱼 auth 等 token 明文进 `logs/standalone.log`。
- 建议：`http_probe`/`http_request` 抛错只带 `strip_query(url)`；或外层只打异常类型与脱敏 URL。

**M-36 配置文件解析只捕 `configparser.Error`：GBK 编码 config.ini 启动即裸 traceback 崩溃**

- 位置：`scripts/douyin_live_recorder_standalone.py:1652-1658`
- 类型：健壮性 / 孪生差异
- 问题与影响：中文 Windows 记事本「ANSI」另存的 config.ini 是 GBK，`parser.read` 抛 `UnicodeDecodeError`（不在捕获面）——编码不对的配置文件让程序启动即崩，而非按设计「解析失败用默认配置」。主线 `src/config_io.py:79/129/200` 明确捕 `(RuntimeError, UnicodeDecodeError)` 兜底，孪生差异未被登记。
- 建议：`except (configparser.Error, UnicodeDecodeError, OSError)`，告警后走默认值。

**M-37 Windows 上 `terminate()` 即硬杀，「宽限收尾」注释不成立：Ctrl+C 竞态截断 mp4（主线 ffmpeg_proc 三级终止未回灌）**

- 位置：`scripts/douyin_live_recorder_standalone.py:1505-1530`
- 类型：逻辑 / 孪生漂移
- 问题与影响：注释声称 terminate 后「留给 ffmpeg 自行收尾（flush 缓冲并写 mp4 moov box）」，但 Windows 上 `Popen.terminate()` 就是 `TerminateProcess` 硬杀，不存在宽限语义——三级终止在主力平台退化为立即 kill。主线 `src/ffmpeg_proc.py:109-139` 已演进为「Windows 写 `q` 到 stdin / POSIX 发 SIGINT → wait → terminate → kill」；独立副本未回灌且 Popen 未开 `stdin=PIPE`。Ctrl+C 时控制台事件已同时送达 ffmpeg（正在写 trailer），主线程毫秒级进入 stop() 直接硬杀——mp4 缺 moov 不可播放，恰是注释声称要避免的后果。
- 建议：对齐 `ffmpeg_proc.py` 语义（stdin=PIPE + `q`/SIGINT + 宽限 + terminate/kill）。

### 5.13 测试代码（14 项）

**T-M-01 平台列表解析用例只测测试内复刻的推导式，生产回归不可能使其变红（自证恒真）**

- 位置：`tests/test_http_config.py:153`
- 类型：断言恒真
- 问题与影响：被断言的解析逻辑是测试内自写的推导式，与任何生产代码零关联——「平台列表解析容错」的覆盖信号是虚假的，解析被改坏它仍绿。
- 建议：删除该用例（解析容错已由 `test_danmaku_platform_strip.py` 的行为锁覆盖），或改为驱动真实解析点。

**T-M-02 gui 子进程驱动四文件中 test_gui_wrap_hints 漏注入 PYTHONUTF8/PYTHONIOENCODING：中文 Windows 下 stdin 中文被 GBK 误解码（M-31① 同族漏改）**

- 位置：`tests/test_gui_wrap_hints.py:150`
- 类型：替身/环境漂移
- 问题与影响：父进程以 UTF-8 写含中文的 stdin，子进程在中文 Windows（ACP=936）按 cp936 读——UTF-8 中文被误解码成乱码或直接 `UnicodeDecodeError`。「中文长提示自适应折行」用例实际验证乱码折行或崩溃；CI（Linux UTF-8）恒绿，构成「CI 绿、本机语义漂移」盲区。兄弟文件 M-31① 修复时已完整记录该形态，本文件漏改。
- 建议：补与兄弟文件相同的 `_child_env()`（注入两变量、不写回本进程）传入 `subprocess.run(env=...)`。

**T-M-03 `test_proxy.py::test_linux_get_proxy_info_https` 只断 `isinstance(ip, str)`（字段本就是 str），永不失败**

- 位置：`tests/test_proxy.py:149`
- 类型：恒真断言
- 问题与影响：对「https_proxy 的 host/port 解析」零保护——解析改成返回空 ProxyInfo 或解析错主机名都照样绿。
- 建议：改 `assert (info.ip, info.port) == ("proxy.test", "9090")` 或删除。

**T-M-04 `test_main_fixes` 四个类未打 DNS 桩：`_validate_stream_url` 对非字面量主机做真实 getaddrinfo，无 DNS 环境「判可达」用例集体假红**

- 位置：`tests/test_main_fixes.py:339-448`（TestHuyaReferer/TestFlvGetConfirm/TestGetConfirmRetry/TestSelectSourceUrlLastResort）
- 类型：真实网络依赖
- 问题与影响：同文件 `TestSelectSourceUrl` 已用 autouse `_stub_dns_public` 打桩并写明理由，这四个类没打——离线/hermetic 环境下解析失败一律定罪「主机名无法解析」→ 返回 False，把「本机有没有 DNS」当成了被测行为。
- 建议：统一挂与 `TestSelectSourceUrl` 相同的 autouse DNS 桩。

**T-M-05 `test_main_fixes` 约 10 处 `patch("src.stream_select.time.sleep"/"httpx.Client"/"logger.warning")` 打在进程级共享本体上（M-27/MID-66 同族违例）**

- 位置：`tests/test_main_fixes.py:369` 等
- 类型：替身作用域过宽
- 问题与影响：窗口内全进程 `time.sleep`/`httpx.Client`/loguru 输出被替换；同文件 220/231/239 等行已有合规形态 `patch("src.stream_select.time")`，两种写法并存。AGENTS R1 明文点名该形态「不覆盖 ≠ 合规」。
- 建议：统一改 shim 形态或收窄桩（参照 `test_sync_probe_internal_guard.py:90` 的 `_recheck_delay` 收窄做法）。

**T-M-06 `test_ttwid.py:218` 改写 stdlib configparser 模块本体（shim 形态可行未用，机检名单盲区）**

- 位置：`tests/test_ttwid.py:218`
- 类型：monkeypatch 目标错误
- 问题与影响：`ttwid_module.configparser` 就是全进程唯一的 stdlib 模块本体，该写法与 R1 明令禁止的 `monkeypatch.setattr(main.time, "sleep", ...)` 同形同害，只是 configparser 不在 `_MUTABLE_MODULE_NAMES` 名单里机检不报。
- 建议：改 shim 形态；把 configparser 增补进 R1 名单。

**T-M-07 `test_web_tray.py:128` 改写 stdlib ctypes.WinDLL 本体，无 shim、无例外登记、无自辩**

- 位置：`tests/test_web_tray.py:128`
- 类型：monkeypatch 目标错误
- 问题与影响：因 `web_tray` 函数内 `import ctypes` shim 确实不可行，但既无自辩注释也未登记进 `_SANCTIONED` 例外表，属约定外的裸改；机检永久沉默。
- 建议：把 `ctypes.WinDLL` 获取提为模块级可注入点，或登记例外并附理由。

**T-M-08 前端 motion 沙箱桩把 appendChild 写反，destroy 的 DOM 摘除分支在沙箱永不可达，「移除 canvas」只锁内部标志**

- 位置：`tests/frontend/test_motion.mjs:45-46`（关联 `:159-166`）
- 类型：断言 mock 而非行为
- 问题与影响：`appendChild(c) { this.parentNode = this; ... }` 应为 `c.parentNode = this`；`motion.js` 清理路径 `canvas.parentNode.removeChild(...)` 在沙箱恒不执行，把 DOM 摘除逻辑整体删掉该用例仍全绿。
- 建议：修正桩方向，补「canvas 已从 body 摘除」可观测断言。

**T-M-09 前端测试沙箱缺 sessionStorage：`_tokenStore` 主路径零覆盖，token/主题/语言持久化全部锁在 localStorage 回退分支**

- 位置：`tests/frontend/test_quality_ui.mjs:169-189`、`tests/frontend/test_auth_reauth.mjs:167-188`
- 类型：替身漂移
- 问题与影响：`app.js:35-44` 的 `_tokenStore()` 优先 sessionStorage，`typeof` 守卫使缺失静默走降级——正常浏览器的主分支（含 try/catch 回退顺序）在前端测试中零覆盖，该分支自身坏掉测试全绿。
- 建议：注入与 localStorage 同构的 sessionStorage 桩锁主路径；保留一个不注入的用例专锁回退分支。

**T-M-10 MID-2238 裸 storage 文本锁存在 `window.localStorage` 旁路，隐私模式不变量无行为备份**

- 位置：`tests/frontend/test_regression_2026_09_22_gates.mjs:787-806`
- 类型：文本锁反模式（M-26 同族）
- 问题与影响：负向先行 `(?<![\w.])` 把 `window.localStorage` 排除出命中，而裸 `window.localStorage` 在隐私模式下同样抛异常；白名单状态机按函数声明形态判定，改箭头函数即失配。该文本锁是 MID-2238 不变量的唯一防线。
- 建议：补行为锁（注入「访问即抛」的 storage 桩，断言 init 不中断）；文本锁正则同时命中 `window.` 前缀形态。

**T-M-11 MID-2253 行级扫描门禁不自证：多行调用/换导入形态即静默归零，offenders==[] 恒过**

- 位置：`tests/frontend/test_regression_2026_09_22_gates.mjs:722-750`
- 类型：文本锁反模式 + 门禁不自证
- 问题与影响：只处理「同一行同时含 `i18n.tr(` 与中文串」的行，Python 括号续行把中文实参写到下一行即完全逃逸；`from i18n import tr` 使匹配归零；没有「至少匹配到 N 处」的前提自证——「tr 模板掺中文常量值」回归可从任一逃逸形态进入而不红。
- 建议：扫描前断言至少命中 N 处 `i18n.tr(`；根治改 Python AST 侧扫描。

**T-M-12 「回前台恢复日志/弹幕轮询」生产分支在沙箱中零覆盖（querySelector 桩恒 null）**

- 位置：`tests/frontend/test_regression_2026_09_22_gates.mjs:226`、`:670-676`（关联 `web/app.js:2045-2049`）
- 类型：替身漂移
- 问题与影响：可见侧恢复分支依赖 `document.querySelector('.view:not(.hidden)')`，桩对该选择器恒返 null，分支被静默跳过——SEV-2227/WD-10 的「回到前台立即恢复轮询」没有行为锁，该分支退化时相关用例全绿（文件内已自述该桩缺口）。
- 建议：让桩按 hidden 类返回单个元素，补「隐藏→回前台恢复且不双链」用例。

**T-M-13 三个前端测试包装未核对 node 侧 skipped 计数：`{skip: true}` 全链路假绿**

- 位置：`tests/test_frontend_quality_ui.py:174-178`、`tests/test_frontend_regression_gates.py:40-44`、`tests/frontend/test_auth_reauth.py:37-44`
- 类型：skip 滥用面
- 问题与影响：只有 `test_motion.py:51-52` 判了 `summary.get("skipped", 0) == 0`（M-2264 同族静默消失形态），其余三个包装缺这条；CI 的「Gate frontend tests not skipped」只 grep pytest 级 skip，node 内部 skip 不可见——掩码写入侧防线等断言可被静默标 skip 而全链路仍绿。
- 建议：三个包装各补 `assert summary.get("skipped", 0) == 0`。

**T-M-14 `test_stream_select.py` 等 6 处 `patch("src.stream_select.time.sleep")` 改 stdlib time 本体（同文件已有合规形态并存）**

- 位置：`tests/test_stream_select.py:633`（另 699、1033、1045、1058、1268）
- 类型：深路径 patch 改 stdlib 本体
- 问题与影响：AGENTS R1 点名「不覆盖 ≠ 合规」形态；patch 窗口内全进程 `time.sleep`（含 loguru enqueue 线程）被替换。
- 建议：统一改同文件已有的 `patch("src.stream_select.time")` 形态或收窄桩。

---

## 6. 轻微问题（160 项，按区域列表）

> 逐条给出：位置、类型、问题与简要修复建议。多项同源/同族的合并为一行并列出全部位置。

### 6.1 main.py（8 项）

| # | 位置 | 类型 | 问题与建议 |
| --- | --- | --- | --- |
| 1 | main.py:4518-4524 | 并发/响应性 | 轮末等待逐秒唤醒只查 `recording_enabled`，不查 `exit_recording`/`url_comments`，与其余等待点 `_interruptible_sleep` 口径不一致；改用 `_interruptible_sleep(x, record_url)` |
| 2 | main.py:4176-4180 | 逻辑错误 | h265 FLV→TS 兜底用「real_url 与 flv_url 全等」判定，但比较发生在 http/https 方案改写之后，发生过升级/降级即恒失配，HEVC 被静默装进 FLV 容器；改为直接对 `port_info["flv_url"]` 查 codec 参数 |
| 3 | main.py:3779-3784 | 熔断统计盲区 | `_resolve_platform_stream` 返回 None（handler 抛错被收编）的路径不记 `record_error`，按 host 背压与错误退避全部失效；区分「host 不在白名单」与「已识别平台解析抛错」两种 None 来源，后者补样本 |
| 4 | main.py:4820-4835 | 初始化时序 | 空配置/EOF 轮 `continue` 跳过 first_run 块，Web 模式冷启动未加房间时 `adjust_loop`（调度容量重算）延迟启动；把 first_run 启动移到 `while True` 之前 |
| 5 | main.py:4550-4561 | 健壮性/约定 | `ffmpeg -version` 用裸 `logger.error(e)`（违反异常日志约定）且 `text=True` 未指定 encoding，GBK 严格解码异常会穿出使启动线程无声死亡；补 `encoding="utf-8", errors="replace"` 与 i18n 模板 |
| 6 | main.py:3545-3572 | 信息暴露 | 平台 Cookie 与代理凭据经 `-headers`/`-http_proxy` 进入 ffmpeg 子进程命令行，本机同会话进程可读（外挂 ffmpeg 架构固有限制，非新引入）；至少在 AGENTS「已知坑」登记该暴露面，长期评估经 stdin 喂参 |
| 7 | main.py:525-536/540-550 | 退出健壮性 | safe_exit 排空后处理线程池（`cancel_futures=False`，单任务上限 3600s）期间二次 Ctrl+C 无法中断，最坏挂住数十分钟；给 drain 加总时限后转 `cancel_futures=True` |
| 8 | main.py:766-769、1348、4504 | i18n | `print_colored` 三处文案未走 `i18n.tr()`（提取器盲区），非中文语言恒显示简中；比照 MIN-2233 收口并补四语条目 |

### 6.2 GUI（10 项）

| # | 位置 | 类型 | 问题与建议 |
| --- | --- | --- | --- |
| 1 | gui.py:3541-3567 | 逻辑 | `_log_queue_has_data` 仅在有消息时复位，哨兵独占轮次后日志刷新链 200ms 永久空转；复位移出 `if messages:` |
| 2 | gui.py:3348-3349 | 注释矛盾 | `_stopping` 复位注释称「已上移 finally」但 try 内仍保留一份；删 try 内复位并修正注释 |
| 3 | gui.py:3736-3742、3995-4000 | 渲染时序 | `_quality_last_displayed`/`_danmaku_last_stats` 先记账后重建，重建抛 TclError 后同数据永不重绘；记账挪到重建成功之后 |
| 4 | gui.py:3169-3178 | 健壮性 | start_recording 异常路径无条件丢弃 `self.process`，Popen 已成功时子进程孤儿化且 GUI 无法再停止；先判进程存活再决定保留或收尾 |
| 5 | gui.py:1419-1421 | 资源 | status_pill/_sidebar_dot 占位控件被重建覆盖后成孤儿，每次启动泄漏 2 个不渲染控件；占位前 destroy 或用类型注解替代 |
| 6 | gui.py:2451-2454、2922、2925 等 | i18n | messagebox 文案 tr 口径不一致（MIN-2247 只在高级设置窗口落实），英文界面部分对话框仍为简中；补进四语目录并统一 tr |
| 7 | gui.py:192 | 死代码 | 导入的 `find_room_url_by_anchor_name` 全文件无调用点；删除 |
| 8 | src/web_tray.py:159 | i18n | 托盘成功提示裸简中 print，同函数 140 行已走 tr；统一口径 |
| 9 | src/web_tray.py:252-259 | 健壮性 | 兜底退出 `os._exit(0)` 跳过 atexit 链与流 flush（atexit 承担日志归档）；至少先 flush 再退出 |
| 10 | gui.py:4105-4106、4027 | 可观测性 | 周期链内部 `except Exception: pass` 使外层 `_warn_chain` 失明，状态栏/统计卡静默停更零日志；改为经 `_warn_chain` 限频留痕（TclError 可单独静默） |

### 6.3 平台解析 spider.py（10 项）

| # | 位置 | 类型 | 问题与建议 |
| --- | --- | --- | --- |
| 1 | spider.py:335-338、360-364 | 缓存一致性 | Twitch Client-Id 快路缺出口一致性判据、TTL 失败分支未清 `_cached_twitch_client_id_proxy`，与 M-8 修复的 did/buvid 不同构；补齐同构逻辑或注释说明刻意不做 |
| 2 | spider.py:4983-4990 | 死代码 | 花椒 except 分支内不可达的逐字重复 `raise`（MID-2223 合并残留）；删除 |
| 3 | spider.py:5910-5912、5942 | 健壮性 | vvxqiu 的 roomId 判空在两次请求之后，缺 roomId 每轮白烧两次必败请求；守卫提前到首跳之前 |
| 4 | spider.py:2622-2624 | 逻辑错误 | bigo 补名分支 `url.split("/")[3]` 对短 URL 抛 IndexError；改 urlparse 判段数 |
| 5 | spider.py:5008-5009 | 逻辑错误 | 花椒 user_info 以 `"user"` 判分支却按 `"user/"` 切分，直调可 IndexError；判据与切分统一 |
| 6 | spider.py:1703、3358、3996、4416、4603、5249、5383、6471、7037 等 | 安全（非 SSRF） | 房间 ID/参数未编码拼进查询串或手工拼 JSON 体（目标 host 固定不可达内网，最坏请求被拒）；查询串统一 `urlencode/quote`，JSON 体改 `json.dumps`（Look:3809 是正确范式），`room_id=` 系取值先切 `&` |
| 7 | spider.py:1897、1900、1964、1986、5452 | 健壮性 | B站/AcFun 残留 5 处直接下标与 itemgetter 排序键，字段缺失时 KeyError/TypeError 被装饰器吞成「未开播」缺归因；改 `.get`+`_dig` 链与 `_warn_api_abnormal` |
| 8 | spider.py:1834-1835 | 契约漂移 | h5 标题注释声称调用方 `or ""` 兜底，实际未兜、None 透传（main 侧当前容忍）；调用点补 `or ""` 或修正注释 |
| 9 | spider.py:2850-2853、2517+2529-2536 | 逻辑错误 | BJNICK/host_nickname 缺失时 None 拼成 `"None-xxx"` 或以 `{"anchor_name": None, "is_live": True}` 返回，污染熔断样本；对齐 M-9 口径显式判 None 回 "" |
| 10 | spider.py:2587 | 逻辑错误 | bigo og:url 以 `&amp;h=` 切分，未转义 `&h=` 形态失配；取值前先做 HTML 反转义或双形态兼容 |

### 6.4 Web 后端（11 项）

| # | 位置 | 类型 | 问题与建议 |
| --- | --- | --- | --- |
| 1 | web_api.py:975-977 + web_config.py:114-118 | 校验缺口 | toggle 启用注释行时把原文不经 `validate_room_target` 直接写回，「URL_config.ini 唯一写入口校验」对这条路径不成立（手工埋入的内网/元数据行可绕 SSRF 校验进录制链）；启用分支对 content 重新校验 |
| 2 | web_config.py:1290-1292 | 逻辑错误 | `is_hashed_web_password` 仅按 `pbkdf2_sha256$` 前缀判定，恰以此开头的明文密码被当哈希存储，登录永久失败；补完整形态校验（4 段结构 + b64 可解码 + 迭代数为整数） |
| 3 | web_config.py:1032-1033 | 测试哨兵泄漏 | 生产环境 Origin host=`testserver`（无显式端口）无条件放行同源判定；哨兵豁免改测试上下文门控 |
| 4 | web.py:128 | 资源泄漏 | `logs/web_console.log` append 打开后永不轮转永不截断，长期运行无上界；进入后台模式时超阈值轮转或启动截断 |
| 5 | web_api.py:269-271 | 性能/放大面 | 免鉴权端点每请求在锁内做 O(键数) 全表清理，多 IP 源可放大成本；改惰性分片清理或键数硬上限 |
| 6 | web_api.py:681-682/702-705 | 并发竞态 | 登录限流 check-then-append 非原子，并发突刺约 2× 超预算；门禁阶段乐观占位、验证成功再回退 |
| 7 | web_config.py:779/795-798 | 注释失真 | update_room_quality 注释声称 `_config_write_lock` 防 GUI/Web 并发丢写，实际读在锁外且锁是进程内 RLock（跨进程无效）；修正注释并把读移进锁内 |
| 8 | web_api.py:1235-1239/1503-1527 | 缓存残差（待确认） | mtime+size 等长同刻外部改写可致认证视图滞留「关闭」（fail-open 方向，NTFS 基本不触发）；鉴权依赖键额外比对内容摘要 |
| 9 | web_config.py:1070-1083 | 脱敏缺口 | 值形态正则漏 `pass=`/`sign=`/`sig=`/`signature=` 等查询键；补词根或对 URL 形态值默认脱敏 |
| 10 | web.py:304 | 设计局限（待确认） | 面板仅支持明文 HTTP，`0.0.0.0` 部署下凭据局域网明文传输；README/设置页明示「非回环部署必须置于 TLS 反代之后」或增加可选 ssl_keyfile/certfile |
| 11 | web_api.py:520-521 | 死代码 | `app.state.web_cfg` 写入后全仓无读取点，易被误当「当前配置」消费（恰是 SEV-N03 要消灭的形态）；删除或改注释为「仅供诊断」 |

### 6.5 选源与调度（14 项）

| # | 位置 | 类型 | 问题与建议 |
| --- | --- | --- | --- |
| 1 | stream_select.py:824-841 | 逻辑 | HEAD 401/403 + 流媒体 content-type 绕过「重试一次再定罪」直达分片探测的保守放行，多烧一轮失败样本；401/403 先走 Range-GET 重试定罪路径 |
| 2 | stream_select.py:846-875 | 健壮性 | m3u8 Range-GET 重试循环只对状态码重试，网络异常直接穿透判死，与 `_confirm_get_ok` 异常重试语义不一致；循环体内补异常重试 |
| 3 | stream_select.py:1315-1317 | 逻辑/日志 | h265 record_url 告警无条件打印「无 HLS/FLV 备选」（usable 非空时不实）且不走 i18n；文案按事实分叉并登记模板 |
| 4 | stream_select.py:1018-1019 | 约定违反 | 三参 getattr 读 main 已声明模块属性（`hls_collection_enabled` 等），mypy 类型检查静默失效；直接访问或 cast 收窄 |
| 5 | stream_select.py:146-148 | 健壮性 | shopee origin 对无 scheme URL 产出畸形 Origin 头；用 urlsplit 取 scheme://netloc，缺 scheme 跳过注入 |
| 6 | stream_select.py:849、576 | 资源 | 探针 Range-GET/分片 GET 非流式读全响应体，CDN 无视 Range 时内存不可控；改 `client.stream` 或加字节上限 |
| 7 | stream.py:687 | 逻辑 | TikTok 降级基准硬编码 `4`，SD 档回退方向与抖音分支相反；按目标列表长度判定 |
| 8 | stream.py:594-611 | 健壮性 | TikTok 单条目畸形 sdk_params（坏 JSON/非数字/异常 resolution）使整房间判未开播；per-entry try/except continue |
| 9 | stream.py:1204 | 健壮性 | 网易空 cdn 字典 `list(...)[0]` IndexError → 整房间判「未开播」而非可诊断告警；空字典走「无流地址」契约 + warning |
| 10 | stream.py:1269-1281 | 逻辑（待确认） | spec=True 时 record_url 与展示的 m3u8/flv 字段语义分叉，选源记录与面板展示可能对不上；确认语义后统一或注释写明 |
| 11 | stream.py:872-874 | 逻辑 | 虎牙蓝光分支 available_qualities 无条件追加 UHD/LD、永不含 BD/HD/SD，与旧档位分支口径不一致（仅展示失真）；统一用 room_codes 口径 |
| 12 | room.py:94 | 健壮性 | sec_user_id 正则要求尾随 `&`，成为末参数时解析失败（抖音参数顺序调整即全体主页短链解析失败）；改 `(?:&|$)` 或 parse_qs |
| 13 | room.py:97、282 | 健壮性 | room_id 用 rsplit 脆弱提取（无路径段/末尾斜杠时取到垃圾值）；web_rid 缺失经 `cast(str, ...)` 掩盖返回 None；改 urlsplit 取 path 并显式判空 |
| 14 | scheduler.py:383-389 | 并发 | `set_recording_limit` 无锁 check-then-act，与同类配置入口口径不一，热更新竞态窗口内字段与信号量容量瞬态不一致；对齐「锁内写字段、锁外 set_value」 |

### 6.6 弹幕链路（11 项）

| # | 位置 | 类型 | 问题与建议 |
| --- | --- | --- | --- |
| 1 | collector.py:424-428 | 逻辑 | `except asyncio.CancelledError, RuntimeError` 过宽，平台 start() 内部 RuntimeError 与「正常停止」混为一类静默吞掉；收窄为仅在停止态吞 |
| 2 | collector.py:249-254 | 逻辑 | stop() 未启动/已回滚时也无条件上报 room_closed，产生孤儿/重复 closed 事件；挪进 `_started` 分支 |
| 3 | ttwid.py:188-192 | 逻辑/竞态 | 配置分支 `return _cached_ttwid` 可能递出其它出口刚写入的值，违反本模块 MIN-2220「镜像不参与判定」不变量；改 `return cfg`（一行修复） |
| 4 | ttwid.py:164-167、237-240 | 凭据（低可达） | 异常文本未过 mask_credentials；与 WD-01 对齐补脱敏 |
| 5 | ws_client.py:249-260 | 凭据（待确认） | 毒消息日志是文件头约定之外的第三个异常文本出口，未脱敏；统一补 `mask_credentials(str(e))` 并更新文件头约定 |
| 6 | ws_client.py:403-408 | 资源（待确认） | `_pending` 在途发送任务停止时不取消，loop.close 后可刷「Task was destroyed」噪声（MIN-23 同族，start 任务已处理、send 任务漏了）；`loop.stop()` 前逐一 cancel |
| 7 | srt_writer.py:51-52 | 注入边界（待确认） | U+2028/U+2029/U+0085/NUL 不在清洗范围（主流播放器按 \n 切块，可利用性低）；低优先级追加替换 |
| 8 | cookie_cache.py:92-101、148-150 | 代码质量 | `get_cached`/快路返回缓存内部 dict 引用，调用方写入会污染全进程共享缓存；返回浅拷贝或注明只读契约 |
| 9 | cookie_cache.py:58、92-101 | 代码质量 | `get_cached` 硬编码 DEFAULT_TTL 与写入侧自定义 ttl 脱节、注释把写入时刻写成 expire_ts、当前 0 调用方；统一 ttl 口径并修注释 |
| 10 | danmaku_monitor.py:713-721 | 逻辑 | close_file 忽略 `submit("close")` 返回值，队列满时 close 指令被丢仍报成功（归档链以为关好了，改名仍会 PermissionError）；检查返回值走超时同路径告警 |
| 11 | danmaku_monitor.py:392-401 | 逻辑（低概率） | 房间停止后在途消息经隐式注册分支复活「未知」平台幻影条目且无人再清理；隐式注册仅限从未注册过的房间或给复活条目加存活上界 |

### 6.7 HTTP 基建（9 项）

| # | 位置 | 类型 | 问题与建议 |
| --- | --- | --- | --- |
| 1 | async_http.py:353-363 | 安全分层 | async_req 入口只查 scheme，内网判定只能靠响应后钩子，与 get_response_status 的建连前判定不对称（当前调用点 host 均为常量，残余面低）；入口追加一次 `_internal_stream_target_reason` |
| 2 | async_http.py:687-711 | 健壮性 | 非 m3u8 源 HEAD 返回 204/206 等 2xx-非-200 被误判不可达；改 `200 <= status < 300` 判可达 |
| 3 | sync_http.py:346-347 | 逻辑 | 标量 json_data 在无代理分支被静默丢弃（与代理分支不一致）；见 M-16 一并修 |
| 4 | sync_http.py:382-387 | 健壮性 | gzip 值比较大小写敏感、不认 x-gzip，失败塌成空串难归因；`.strip().lower() in ("gzip","x-gzip")` |
| 5 | proxy.py:59-68 | 凭据处理 | proxy_url 拼接 user/password 未 URL 编码，含 `@ : / #` 的合法密码解析层即错位（当前无生产消费点）；`quote(..., safe="")` |
| 6 | ab_sign.py:413、421、433 | 移植疑点（待确认） | `b[51]`/`b[56]`/`b[69]` 死赋值不被读取，若上游 JS 确实消费这些字节则存在移植保真疑点；与上游逐字节比对后补「保留以对齐结构」注释或删除 |
| 7 | sync_http.py:262-273 | 资源 | `_gunzip_capped` 超限路径 GzipFile 未显式关闭（CPython 引用计数下无实际泄漏）；改 with 语句 |
| 8 | async_http.py:97-101、142 | 行为漂移 | client 缓存键不含 timeout，首建者的 timeout 固化为 client 级默认，未来漏传 per-request timeout 的调用点会静默继承；`_build_client` 不传 client 级 timeout 或加注释硬约定 |
| 9 | sync_http.py:168-184 | 并发/串号 | 线程级 Session 持久 cookie jar 跨请求自动携带（MID-22 同型，当前无生产 importer）；接线时为 cookie 类调用提供独占 Session 分支 |

### 6.8 工具与配置（10 项 + 1 待确认）

| # | 位置 | 类型 | 问题与建议 |
| --- | --- | --- | --- |
| 1 | utils.py:596-638 | 锁契约 | `update_config` 不自持锁也未注明「调用方须持 file_update_lock」（当前 5 个调用点恰好都持锁，属幸存非设计保证）；`config.write` 未捕 `configparser.Error`（键名含 `=`/`:` 时穿透）；补注释或惰性取锁 + 捕获降级 |
| 2 | recorder_status.py:82 | 约定违反 | 三参 getattr 访问已声明的 `main.process_start_time`，类型检查静默失效；改直接访问 |
| 3 | recorder_status.py:234-236、config_io.py:80-82 | 约定违反 | 异常日志模板缺 `{type_name}`，违反「异常日志必带异常类型」硬约定；模板补字段（msgid 变更同步四语目录） |
| 4 | recorder_status.py:180、182 | i18n | 控制台状态行两处硬编码简中未经 tr()，与同行其余字段口径不一；补进 tr 并登记 msgid |
| 5 | config_io.py:335-354 | 备份保真 | 脱敏备份经 configparser 重序列化丢全部注释/[DEFAULT] 段、键名小写化；改逐行扫描只替换敏感值，或注明「备份不含注释」 |
| 6 | config_io.py:79 | 健壮性 | `update_file` 读侧只捕 `(RuntimeError, UnicodeDecodeError)` 漏 `OSError`，与同模块 `update_anchor_name` 口径不一，URL_config 被占用时自愈路径不生效；except 元组补 OSError |
| 7 | log_archive.py:127-149 | 瞬时窗口 | 关闭 std 流到重建之间并发 print 落在已关闭对象上抛 ValueError（毫秒级窗口）；先替换引用为 devnull 再关闭，或注明接受 |
| 8 | config_io.py:180-184 | 配置行格式 | 主播名含逗号未被 clean_name 清洗，写入逗号分隔配置行破坏段结构（无注入面）；clean_name 或入口处把 `,/，` 替换掉 |
| 9 | config_io.py:390-402 | 竞态误报 | 备份轮转 listdir 与逐个 getmtime 之间文件消失时 FileNotFoundError 被记成「备份失败」且本轮不再重试；getmtime 单独 try 或改用文件名时间戳排序 |
| 10 | notify.py:83 | 脱敏/规范 | 推送失败异常经 `print_colored` 裸 `{e}` 输出，未过 mask、无 type_name；改 logger.warning + i18n 模板同仓口径 |
| 11 | recorder_status.py:36-67 | 容错（待确认） | 快照条目首元素非 datetime 时 AttributeError/TypeError 穿透 `except (RuntimeError, IndexError)` 到 Web API 层（当前写入点受控）；扩捕获元组或 isinstance 判别 |

### 6.9 安装与后处理（6 项）

| # | 位置 | 类型 | 问题与建议 |
| --- | --- | --- | --- |
| 1 | ffmpeg_install.py:79/368、node_install.py:47/268 | 逻辑 | PATH 注入用模块导入期快照整体覆盖，与 master 模块实时取值口径不一致（当前时序难触发，调整导入顺序即成真回归）；统一改安装时点实时读取 |
| 2 | ffmpeg_install.py:291-382 | 资源泄漏 | 下载中断残留半截 `ffmpeg_official_temp.zip` 不清理（master 模块已处理，MIN-2266⑤）；except 分支补 unlink |
| 3 | ffmpeg_install.py:510-523 | 逻辑 | yum 超时落 `except Exception`，`is_RHS` 保持 True 不回退 apt；补 `TimeoutExpired` 分支置 False |
| 4 | ffmpeg_master_download.py:343-344 | 完整性语义 | 首次 TOFU 记账写盘失败仅 warning 后继续，此后每次安装退化为无基准首次信任且无持续提醒；升级为可操作提示或记账失败拒装 |
| 5 | node_install.py:285-287 | 脱敏约定 | 泛化 except 打印异常原文，requests 异常内嵌未脱敏 URL（当前 URL 均无凭据，实害零）；异常文本过 mask_credentials |
| 6 | video_postprocess.py:202-204 | 健壮性 | 后处理 ffmpeg 未显式 `stdin=subprocess.DEVNULL`（继承父进程 stdin，与主链 stdin=PIPE 不一致）；补 DEVNULL |

### 6.10 前端与签名脚本（15 项）

| # | 位置 | 类型 | 问题与建议 |
| --- | --- | --- | --- |
| 1 | app.js:1243、1787 | 竞态 | loadRooms/loadFiles 多入口并发无代次比对，旧响应可乱序覆盖新渲染（自愈）；加与 makePollChain 同型代次比对 |
| 2 | app.js:1676、1505、1582 | 口径不一致 | 掩码跳过判定三处 trim 用法不统一，带空格掩码可能被当新值提交（后端另有 400 兜底）；三处统一 `String(x).trim() === SENSITIVE_MASK` |
| 3 | app.js:1030-1031 | 交互缺陷 | 日志面板每 5s 强制滚底，用户上滚排障被拽回；复用弹幕流 nearBottom 判定 |
| 4 | app.js:2044-2050 | 逻辑/注释不符 | 回前台恢复分支日志首拍延迟 5s，非注释宣称的「立即补拉」；恢复分支先 `loadLogs()` 再 `startLogsPolling()` |
| 5 | app.js:190-192 | 凭据暴露面（待确认） | apiError 将原始响应体全文写 console.warn（MID-39 设计取舍，仅本机可读）；可对 rawBody 过同源脱敏规则 |
| 6 | app.js:1404、1415、1833、1840 | 注释漂移 | window.toggleRoom 等 4 个全局导出已无内联调用方（表格已改事件委托）；改局部函数或修正头注释 |
| 7 | app.js:1469-1477 | 待确认 | `httpsRecordingEnabled` 键缺失按 false 回退，方向未与后端缺省核对；与 http_config 缺省值对齐 |
| 8 | index.html（根）:211、250 | 健壮性 | SRI/CDN 失败时 Hls/flvjs 未定义，点击播放抛裸 ReferenceError 无提示；播放前判 `typeof` 给出加载失败提示 |
| 9 | index.html（根）:166-171 | 输入处理 | http 强制升 https，不支持 TLS 的源直接播放失败且提示无归因；失败提示回显实际协议便于判断 |
| 10 | liveme.js:317、332、373、406、415 | globalThis 污染 | 5 处未声明赋值成隐式全局（含通用名 data/signParams；execjs 每次新进程，当前无实害）；补 let/const（同批重算钉定哈希） |
| 11 | liveme.js:348 等 6 处 | 输出面噪声 | 签名中间值 console.log 落 stdout，干扰 execjs 输出解析；降噪为 stderr 或删除（同批重算哈希） |
| 12 | liveme.js:7、315 | 待确认 | lm_s_ts/lm_s_str 模块加载期固化，依赖「每次新进程」前提（已核实成立）；求值移入 sign() 内或钉住前提注释 |
| 13 | x-bogus.js:70/375、haixiu.js:5-8 | 已知特征 | 上游混淆产物：JSVMP 隐式全局 u、eval 求值常量/js-md5 标准 require 形态；输入均不进 eval，文件钉定不可改，记录供知悉 |
| 14 | haixiu.js:517-519、liveme.js:349 | 接口健壮性 | `require(cryptoJSPath)` 路径来自调用实参（当前 Python 侧传固定相对路径）；写死或校验 basename |
| 15 | migu.js:378、235、244 | 边界 | `&` 拼接对含 `#` 入参与重复 ddCalcu 无防御；两处 fetch 无超时（外层 30s 兜底）；追加前判 `parsedUrl.search`，fetch 加 AbortSignal.timeout |

### 6.11 构建与门禁 / CI（9 项）

| # | 位置 | 类型 | 问题与建议 |
| --- | --- | --- | --- |
| 1 | ci.yml:598 | 供应链（已登记取舍） | codecov-action@v7 浮动 ref 消费 CODECOV_TOKEN（MIN-2263 已限权、文件头有登记）；随维护顺手 SHA 钉定 |
| 2 | build_exe.py:1545 | 逻辑 | 冒烟 benign 白名单按整段输出子串判定，一次良性堆栈豁免全部 FATAL_MARKERS；按行分组判定或注释写明粒度限制 |
| 3 | build_exe.py:344-350 | 安全/健壮性 | `_prepare_config_dir` 把 config/ 下未知文件名文件原样带进发布目录，凭据「不产生/拦住」双闸对它们均不生效；复制前过敏感内容扫描或改显式白名单 |
| 4 | build_exe.py:276 vs 300-315 | 注释与行为不符 | `_sanitized_config_text` 注释称「保留注释」，实际 configparser 往返丢光注释，发布模板失去使用说明；改注释或改逐行保留式脱敏 |
| 5 | check_coverage.py:220-221 | 报错文案 | 债务基线违规文案方向与不变量相反（当前 COVERAGE_DEBT 为空不可达）；更正文案 |
| 6 | patch_i18n_2026_09_12.py:228-233 | 逻辑错误 | compile_po 失败被吞、恒 return 0，与自身注释矛盾；`return res.returncode`（连同 M-29 一并处理后按一次性脚本处置） |
| 7 | run_gates.py:280-287 | 健壮性（待确认） | stderr 逐行转发 EOF 依赖孙进程关管道，未来门禁若派生后台进程会挂死（当前六条门禁不触发）；可选加整体超时并在「格式化命令」登记约束 |
| 8 | build_exe.py:1428-1430 | 健壮性 | `_clean_stale_release_zips` 的 `unlink()` 未捕 OSError，Windows 句柄占用时 --dual 第一步即崩；捕 OSError 告警后继续（后续互异校验可兜住） |
| 9 | build-release.yml:213/490/498 | 纵深防御 | version 字符串未做格式校验即插入 run: 与 gh 参数（来源为仓库内容非外部事件，非可利用注入）；prepare 提取后加一行正则校验再写 output |

### 6.12 独立发行版 standalone（11 项）

| # | 位置 | 类型 | 问题与建议 |
| --- | --- | --- | --- |
| 1 | standalone:1437、1491、1583 | 注释失真/漂移 | 「标志集与 main.py 一致」已失真（主线现有 -protocol_whitelist/-fflags/-thread_queue_size 等）；.m3u8 query 判据两侧行为已分叉且本侧未登记；改写注释为差异清单并对齐判据 |
| 2 | standalone:206-211 | 边界 | 响应头 charset 外部可控，非法编码名抛 LookupError 致整请求误判失败；decode 外再捕 LookupError 回退 utf-8 |
| 3 | standalone:969-976、994 | 资源/DoS | 斗鱼 enc_time 服务端可控且无上限，异常大值使房间线程长时间纯 CPU 空转；设上限（如 >64 告警拒绝） |
| 4 | standalone:1351-1355 | 逻辑 | record_url 与 m3u8/flv 候选重复不去重，同 URL 双探针白烧 CDN 连接预算；保序去重 |
| 5 | standalone:1446、1546 | 边界 | `0 < duration < 1` 被 int() 截断为 0 产出 `-t 0` 零帧输出；`max(1, int(duration))` 或显式告警钳 1 |
| 6 | standalone:467-476、627-629、651-653 | 死代码 | set_value/set_record_limit/states 生产路径零调用（调容原语未接线）；注释登记「容量为启动期定值」或删除 |
| 7 | standalone:1665、1682、1689 | 孪生差异 | 布尔解析 `startswith("是"/"否")` 与主线 config_bool token 集不同，共用配置时语义静默漂移；移植 parse_config_bool（零依赖纯函数） |
| 8 | standalone:1864-1867、2239-2242 | 逻辑 | URL 列表不去重，重复行双线程录同房（主线 dict.fromkeys 保序去重）；同口径去重 |
| 9 | standalone:1417-1418 | 隐私 | Apple Silicon 让位 print 输出系统 ffmpeg 绝对路径（含用户名）未脱敏（主线同点过 mask）；只打印 basename |
| 10 | standalone:2158-2159、2189 | 文档矛盾 | RUN_STEPS 示例 `--config config.ini` 与「仓库自带 config/config.ini」路径矛盾，照抄则配置（含 Cookie）静默不生效；示例改为正确路径或对显式 --config 缺失告警 |
| 11 | standalone:1817-1823 | 边界 | anchor 名无长度上限（极长昵称在 MAX_PATH 下致 ffmpeg 打开失败）；remove_emoji=False 路径不清洗 `\x00-\x1f` 控制字符；anchor 同样截断 + ILLEGAL_CHARS_PATTERN 扩字符集 |

### 6.13 测试代码（36 项）

**组 1（5 项）**

| # | 位置 | 类型 | 问题与建议 |
| --- | --- | --- | --- |
| 1 | test_anchor_rename.py:70-78 | 注释与断言矛盾 | 三处注释称「注释行整行跳过」，断言（与生产一致）锁的是「保留 # 前缀但更新名字段」；按实际契约更正注释 |
| 2 | test_bilibili_danmaku.py:41-42 | 凭据未脱敏 | 手跑真机脚本整串 print 真实运行时 Cookie 未过 mask_credentials（输出常被复制进工单/文档）；改 mask 或只打长度 |
| 3 | test_concurrency_rate_limit.py:126-139 | 时序断言脆弱 | 两条 `elapsed < 0.05` 上界断言高负载机器可能无回归假红；放宽余量或改计数式判据 |
| 4 | test_cookie_cache.py:255-259 | 挂死风险 | 裸 `t.join()` 无 timeout，singleflight 回归成死锁时挂住整个 pytest 会话；改 `join(timeout=15)` + 存活断言 |
| 5 | test_cookie_cache.py:206 | 注释错置 | 解释 patch 目标的关键注释落在嵌套函数 return 之后的死代码位置；删除（外层已有同义注释） |

**组 2（6 项）**

| # | 位置 | 类型 | 问题与建议 |
| --- | --- | --- | --- |
| 1 | test_ffmpeg_install.py:85 | 注释与实现不符 | MASTER_CALLS 注释称「由 _no_real_egress 逐用例清空」但 fixture 未清空且全文件无断言消费（埋雷的注释性契约）；兑现或更正注释 |
| 2 | test_douyin_url_resolution.py:74 | patch 目标不当 | `patch("src.room.httpx.AsyncClient")` 落在共享 httpx 模块本体而非 src.room 命名空间 shim（窗口短风险低）；改 shim 形态统一口径 |
| 3 | test_douyu_danmaku.py:1 | 可维护性 | 手动真机脚本以 test_* 命名被 pytest 导入（0 用例），缺同族说明头、处于 R7 盲区；补说明头或改名移出收集面 |
| 4 | test_douyu_stream_url.py:11 | 注释失真 | 「不会被 pytest 收集」不准确——收集期仍会被导入，只是不产用例；按「收集期会被导入但模块级须零副作用」更正 |
| 5 | test_danmaku_monitor.py:60 等 | 资源卫生 | 带 log_path 的 Hub 用例后不 close_file，每用例遗留 2 条守护线程至会话结束；加 autouse fixture 统一收尾 |
| 6 | test_ffmpeg_path_preference.py:87 | 潜在偶发（待确认） | 全局 loguru 临时 sink + `captured == []`/`len==1` 精确计数，理论上受窗口期并发日志干扰；加模块过滤或在注释钉住前提 |

**组 3（5 项）**

| # | 位置 | 类型 | 问题与建议 |
| --- | --- | --- | --- |
| 1 | test_node_install.py:311/333/384/424/585 | 替身作用域过宽 | `platform.machine`/`Path.write_text`/`Path.unlink`/`distro.id` 打在共享对象上（窄桩+自动还原，风险低）；可统一 shim 形态 |
| 2 | test_quality_tiers.py:16 | 收集期副作用（待确认） | 模块级 `import main` 在收集期执行重初始化，与 test_main_fixes 记录的 WinError 规避口径不一致；改 module-scope fixture 形态 |
| 3 | test_platform_danmaku_offline.py:405-410 | 状态还原缺口 | 手工 `MonkeyPatch` 的 `undo()` 不在 finally（目标为局部实例，无全局污染）；改 `MonkeyPatch.context()` |
| 4 | test_machine_validation_fixes.py:152-155 | 过期注释 | 「用 monkeypatch 改常量」与「改不了」自相矛盾（早期方案残留）；按「更正考古」口径压缩为现状 + [历史注] |
| 5 | test_logger_gui_parent.py:22-31 等 3 文件 | 状态还原缺口（待确认） | reload src.logger 后模块级路径态指向已删 tmp，teardown 未复位（当前无消费面实害）；teardown 再 reload 一次或登记边界 |

**组 4（9 项）**

| # | 位置 | 类型 | 问题与建议 |
| --- | --- | --- | --- |
| 1 | test_spider.py:190-193 | 断言弱锁 | HTML 兜底用例只断言「返回 dict 不抛异常」，解析成败均绿；补正向断言（status==2 或 anchor_name 非空） |
| 2 | test_regression_2026_09_22_spider.py:409-410 | 复制粘贴残留 | 同一 record_url 断言连续重复两次；删一行或改为本意字段 |
| 3 | test_spider_fixes.py:38-39 等十余处 | 注释重复 | 相邻注释行逐字成对/三连重复（机械合并残留）；合并保留一份 |
| 4 | test_spider_platform.py:1357/1364 | 命名失配 | `test_short_username_raises` 等名字声称 raises、实际断言返回 None（契约已改、名字未改）；改名为 returns_none |
| 5 | test_spider_platform.py:106-118 | 冗余替身 | patch 与手工 save/restore 双重托管同一全局，`old` 取值时机已晚（恒为 ""）；删手工层 |
| 6 | test_regression_2026_09_22_infra.py:115-121 | 线程内断言 | 写盘线程里的 assert 失败只杀死线程，主线程靠下游断言间接失败（报错与根因脱节）；改 failed 标志由主线程断言 |
| 7 | test_regression_2026_09_22_infra.py:525-556、danmaku.py:135 | 真实等待偏长 | 后台线程真睡 10s/回归路径等 20s，全量尾部耗时；改可注入短时长保持相对关系 |
| 8 | test_regression_2026_09_22_main.py:129-178 等 3 文件 | 跨文件复制 | `_four_catalogs`/`_assert_registered`/`_assert_translation_parity` 三份逐字拷贝，加强一处漏两处；抽共享 helper |
| 9 | test_srt_timeline_anchor.py:23 | 会话级全局修改 | 导入期 `sys.path.insert(0, 仓库根)`，pytest 下无增益且改变会话解析顺序；删除 |

**组 5（3 项）**

| # | 位置 | 类型 | 问题与建议 |
| --- | --- | --- | --- |
| 1 | test_stream.py:365-370 | 断言弱化 | 降级用例值域含请求档本身，注释「确实发生了降级」与断言不符（降级链回归不变红）；断言收窄或注释改齐 |
| 2 | test_web_config_locks.py:18-22 | 文档过时 | 「'***' 后端放行」的已知残留已被 `test_web_api` 的 400 锁证伪，注释未更正（按「被证伪改正」例外处理）；压缩为现状 + [历史注] |
| 3 | test_web_tray.py:347 | 改 stdlib 本体（自辩/盲区） | `setattr(os, "_exit")` 有自辩注释但处 R1 ast.Name 机检盲区，建议登记 `_SANCTIONED` 例外表（同族 builtins.open 备案） |

**组 6 前端测试（8 项）**

| # | 位置 | 类型 | 问题与建议 |
| --- | --- | --- | --- |
| 1 | 四个包装（如 test_frontend_quality_ui.py:178） | 恒真断言 | `summary["tests"] >= summary["pass"]` 数学恒真无防护力；改 `pass+fail+skipped == tests` |
| 2 | test_auth_reauth.mjs:274-276 | 文本锁旁路 | 裸 prompt 负向锁漏行首 `prompt(` 与 `globalThis.prompt(`（有行为备份）；正则改 `(?:^|[^.\w])prompt\s*\(` 并纳入 globalThis 形态 |
| 3 | test_regression_2026_09_22_gates.mjs:433-441 | 文本锁旁路 | `!s.engine_alive` 锁可被 `!== true` 等绕过（行为用例已兜底，仅冗余）；负向集扩为 `/!\s*s\.engine_alive\b|!==\s*true/` |
| 4 | test_regression_2026_09_22_gates.mjs:854-862 | 文本锁单形态无备份 | downloadFile `res.statusText` 锁可解构绕过且无行为用例兜底；补行为用例 |
| 5 | test_regression_2026_09_22_gates.mjs:359-374 | 钉缺席型文本锁（待确认） | SEV-2221 撤销组四条 doesNotMatch：死路径换名复活不报警（文件内有完整 justification）；可改对返回 dict 键集合做正向白名单断言 |
| 6 | test_regression_2026_09_22_gates.mjs:866-883 | 冗余弱断言 | MID-2241 源码锁与行为锁并存，879 行 `\w+` 版弱于 911 行守卫版；收窄为结构索引断言 |
| 7 | test_quality_ui.mjs:106-108 | 可维护性 | 「应用启动」段注释连写两遍；删一行 |
| 8 | test_frontend_quality_ui.py:51 | skip 面过宽（待确认） | 模块级 skipif 连带 skip 两条不需 node 的用例（CI 有 node，实际影响限于无 node 开发机）；拆分或各自显式 skipif |

---

## 7. Mimosa 深度安全扫描结果与人工复核

按密封产物纪律如实记录如下（不据此得出「项目安全/无风险」结论）。

### 7.1 扫描元信息

| 项 | 值 |
| --- | --- |
| scanId | `scan-2026-09-30T02-25-56.161Z-3255898c38d0` |
| 封印 digest | `sha256:5350da9801cb55f4496a36cda16f1c034a2572ea8c8f0a7e93fa57965b1d78a1` |
| 产物目录 | `C:\Users\58421\.mimosa\security-scans\project-2e8ec8b804a942c813ba0df7\scan-2026-09-30T02-25-56.161Z-3255898c38d0\` |
| 深度 / 证据边界 | deep / `static_only_no_runtime_execution`（纯静态，未执行目标项目） |
| 运行状态 | **inconclusive**（覆盖度 partial；threatModel 阶段未完整覆盖——entry points/principals 观测为 0；validation 阶段 investigated=0，即 41 条发现**未经扫描器验证**，均为原始静态发现） |
| 选取面 | 198/198 文件解析成功（按扫描器选样策略，未覆盖全仓 100+ 测试文件与部分源文件） |
| finding 数 | 41（0 条业务逻辑候选） |
| 依赖侧 | 摘要报告匹配 1 个包 / 1 条离线 advisory，但密封产物未给出包名与编号（待查证；本仓 CI 已有 `deps-audit` job 按 OSV 审计 `requirements.txt`，且 starlette/urllib3/h2/protobuf 下限已按历次审计抬升） |

### 7.2 机扫发现与人工复核结论

| 机扫类别（HIGH/LOW） | 数量 | 人工复核结论 |
| --- | --- | --- |
| HIGH · 命令注入（run_gates.py:268；haixiu.js:518；liveme.js:349） | 3 | run_gates.py:268 为固定门禁命令起子进程（`sys.executable -m black/...`），命令与参数均为代码内常量，无外部不可信输入拼接，**不成立**。haixiu.js:518 / liveme.js:349 的 `require(cryptoJSPath)` 路径来自调用实参——与人工发现 J-组轻 14 一致：当前 Python 侧传固定相对路径，无可利用面，作为**接口加固项**收录（写死或校验 basename）。 |
| HIGH · 硬编码凭据（spider.py:4774；5846；5848） | 3 | 4774 为 Twitch 公共 Web 客户端 ClientId（非机密、公开于其 Web 源码，且带 env/config 覆盖入口）；5846/5848 为平台内置公共访问 token（PopkonTV/WinkTV 类），均带 env/config 覆盖入口与失效告警——与 AGENTS 既定设计一致，判定为**平台公共客户端标识而非机密泄漏**，接受为设计内取值。 |
| HIGH · 路径穿越（build_exe.py:880/1135；gui.py:987/2853/4472；main.py:729/4804/4826；config_io.py:381；ffmpeg_install.py:301；ffmpeg_master_download.py:206；log_archive.py:104；node_install.py:247） | 11 | 逐点复核：路径来源均为本地可信配置/固定目录/进程自身产物（config 目录、日志归档改名目标、发布目录），无外部不可信输入直达路径拼接的实例；build_exe 的 zip 解包另有 realpath 前缀校验 + 文件名白名单 + `tarfile filter="data"` 双层防护（人工 L 组核实）。**静态模式误报为主**。node_install.py:247 的真实问题不在路径穿越而在版本号未校验（本报告 M-24，人工评级中等）。 |
| HIGH · SSRF（build_exe.py:801/877；ffmpeg_install.py:152/291；node_install.py:99/239；sync_http.py:23） | 7 | build_exe/ffmpeg_install/node_install 的出站下载端点全部落在 `DOWNLOAD_SOURCES` 白名单 + SHA256/TOFU 校验体系内，主链 fail-closed（人工 I/L 组核实）；真实问题在白名单体系内的两个缺口：node 版本号无格式校验（M-24）与 TOFU 基准读失败 fail-open（M-21）。sync_http.py:23 与人工发现 M-13 一致（opener 无内网复检，当前无生产 importer）。机扫**未覆盖 standalone 的完整 SSRF/file:// 链**（S-01），该最重发现由人工深审找出。 |
| LOW · 不安全随机数（main.py×4；spider.py×3；stream_select.py×2；ab_sign.py；_xbogus.py×2；twitch.py；utils.py；ws_client.py） | 17 | 逐点核对均为非安全用途（请求序列号、UA 指纹、探针抖动、测试样例值）；Web 会话 token 用 `secrets.token_urlsafe(32)`（256-bit，人工 D 组核实），无一处把 `random` 用于凭据/令牌生成。**无需处置**。 |

**复核小结**：41 条机扫发现中，0 条直接构成新的人工未见的可利用漏洞；2 条指向了与人工发现重合的真实薄弱点（node 版本校验、sync_http 内网复检）；其余为模式匹配误报或设计内取值。机扫选取面有限（198 文件、threatModel 未建全、validation 未执行），其 inconclusive 状态与「未覆盖 standalone」的事实再次说明：机扫只能作为交叉证据，不能替代本次人工深审的结论。

---

## 8. 改进建议与修复优先级

### P0（立即修复——安全红线与数据损坏）

1. **S-01 / S-02（standalone）**：独立发行版补齐三道防线（opener 白名单、候选内网/协议判定、`-protocol_whitelist`）并实现命令日志脱敏。若短期不修，应在 README 与文件头明确标注该发行版的安全边界弱于主线，暂停对外分发。
2. **M-17（脱敏死分支）**：`_SECRET_HEADER_RE` 驼峰分支修复 + 「值确实消失」回归锁——这是写入侧凭据脱敏红线的实质缺口。
3. **M-06 / M-07（Web 认证与配置值）**：密码空白口径统一（自锁）、行内注释保留逻辑修正（配置值静默污染）。
4. **M-18 / M-01**：`replace_url` 子串误伤（兄弟房间被静默禁用）、磁盘满恢复后永不拉起（功能性数据状态损坏）。
5. **M-02（GUI 原子写）**：POSIX 部署下凭据权限回退，一行委托 `atomic_write_text` 即可消除。

### P1（短期——防线缺口与安装链）

1. **M-21 ~ M-26（安装链六项）**：node/ffmpeg 完整性体系的三处 fail-open/纵深缺口与导入期并发竞态；统一按 master 模块 SEV-2222 口径收口。
2. **M-05 / M-13 / M-14（HTTP 面上界）**：请求体上限；sync_http 内网复检与 HTTPError 上限（接线前修，避免「接线即成洞」）。
3. **M-08 / M-09（探针与解析的 SSRF 残余面）**：内网判定统一到共享 helper；room.py 裸客户端收敛。
4. **M-10 ~ M-12、M-19、M-20（弹幕/日志/挂死）**：凭据脱敏口径补齐、在途登记注销、SRT 静默丢失可观测性、sink 泄漏、wait_for 双保险。
5. **M-28 ~ M-33（构建与 CI）**：check_annotations 方向修正、一次性脚本处置、冒烟假绿面、CI 第三方动作 SHA 钉定（发布链 `softprops` 三处优先）。
6. **T-M-01 ~ T-M-14（测试防线）**：恒真断言清除、进程级替身 shim 化、前端三个包装补 skipped 校验、DNS 桩补齐——先恢复测试防线的真实性，再谈覆盖率。
7. **M-03 / M-04 / M-34 ~ M-37（平台解析与 standalone 中等）**：真机验证后修复（M-03 需先确认平台是否出现单路形态）。

### P2（随批处理——轻微项）

- 按模块顺手修复：i18n 补录类（main.py 8.8、gui 6.6、recorder_status 6.8-3/4）、死代码清理（gui.py:192、spider.py:4983、web_api.py:520、standalone 调容原语）、注释与实现不符类（M-31 同族、gui._stopping、test_web_config_locks 过时注释）、健壮性小项（room.py 正则、stream.py 单条目容错、gzip 大小写等）。
- 建议以「每个模块一次小批量 PR」推进，避免跨模块大 diff；涉及 i18n msgid 变更的批次须同批维护四语目录并重编 .mo（提取器三类盲区需手工补录）。
- 登记类：main.py 的「ffmpeg 命令行凭据暴露面」写入 AGENTS「已知坑」，防止后人重复发现。

### 流程性建议

1. **孪生文件治理**：standalone 的 2 严重 + 4 中等 + 2 项轻微全部源于「主线修复未回灌」。建议在 `AGENTS.md` 增加硬约定：主线安全/正确性修复涉及 `sync_http` opener、`-protocol_whitelist`、`ffmpeg_proc` 终止链、`config_bool`、MID-49 类签名修复时，必须同步核对 standalone 并在提交信息中写明「已核对/已回灌/刻意不回灌及原因」（现有 9 格矩阵锁只覆盖 PATH 让位判据一项）。
2. **机扫位**：Mimosa 扫描 validation 阶段未执行（investigated=0），41 条发现均未验证——建议后续扫描配置验证阶段，或在流程上明确「机扫发现须经人工复核才能进入修复队列」。
3. **测试卫生机检扩面**：R1 的 `_MUTABLE_MODULE_NAMES` 补 `configparser`；`_SANCTIONED` 登记表补 `test_web_tray.py` 的 ctypes 条目——把本次发现的两个机检盲区纳入门禁。

---

## 9. 总结性结论

1. **总体评价**：本项目代码库的工程质量显著高于同类工具的平均水平——关键安全设计（Web 密码 PBKDF2 + 恒时比较、token 256-bit、SSRF 多层判定、完整性校验 fail-closed 主链、SRT 注入清洗、锁定体系与停止握手契约）在主线代码中普遍到位且有回归锁护持；测试套件大量使用行为锁与反假绿自检，18 个审查批次均确认「无真实凭据硬编码、无 `patch.dict(os.environ)`、无 MUTATION 残留」。
2. **最重的结构性风险集中在两个点**：其一，**独立发行版（standalone）与主线孪生漂移**——主线 2026-09-12/09-20/09-29 三轮安全修复（协议白名单、内网判定、斗鱼签名 POST、ffmpeg 三级终止）均未回灌，叠加命令日志凭据明文落盘，形成本次仅有的两项「严重」；其二，**防线的「写入侧一致性」**——脱敏正则的死分支、Web 密码空白口径、配置值注释保留逻辑，都属于「防线存在但实现口径分叉」形态，靠常规测试难以暴露，需要在修复时同步补「值确实消失/读回一致」类断言。
3. **测试侧无严重项但有一个系统性信号**：14 项中等测试问题中过半是「替身打到进程级共享本体」与「文本锁可绕过/不自证」两类既有已知形态的复发（R1 名单盲区、M-26 同族）——建议按第 8 章流程性建议扩机检名单，把这类形态从「靠审查发现」转为「靠门禁拦截」。
4. **机扫与人工的关系**：Mimosa 深扫的 41 条原始发现经逐条复核后，无一构成人工未见的可利用漏洞，但其中 2 条与人工发现重合并提供了交叉印证；其 inconclusive 状态与有限选取面说明机扫当前只能作为交叉证据源。本次报告的安全结论以人工深审为准。
5. **置信度与后续动作**：213 项发现中，2 项严重与 6 项代表性中等已经行号级人工复核证实；其余条目均基于实读代码，机理成立但影响评级含推断成分，标「待确认」的 10 余项需要真机或特定环境复现后再定级。建议按第 8 章优先级推进修复：P0 五组先行（预计小批量即可完成），P1 以「安装链接口」「HTTP 面上界」「测试防线恢复」三个工作包组织，standalone 建议单独立项做一次「回灌对齐」专项。
6. **本报告的边界**：静态审查未运行任何用例、未做真机录制验证；对平台接口行为（如 M-03 的单路形态是否存在）、部署形态（如 M-05 的 0.0.0.0 暴露面）的判断均标注了前提。完成定义中的「端到端真机验证」不适用于本报告（纯文档产出），后续修复涉及的录制链路/选源改动仍须按 AGENTS「完成定义」执行真机验证并回写验证记录。

---

*审查方法与分组明细：18 个独立审查批次的完整原始发现（含逐条代码片段与锚点核对结论）留存于会话记录；本报告为汇总口径，行号以 2026-09-30 工作区状态为准。*
