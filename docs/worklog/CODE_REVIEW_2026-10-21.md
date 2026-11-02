# 代码审查报告（CODE_REVIEW_2026-10-21）

## 1. 审查概述与背景

本报告为对 DouyinLiveRecorder 工作空间（`D:\DouyinLiveRecorder`）内全部自研源代码的一次系统性静态审查。该项目为基于 Python 3.14 的多平台（60+）直播录制工具，提供四个入口：命令行/录制引擎（根目录 `main.py`）、旧版 Tkinter GUI（`gui.py`）、新版 PySide6 GUI（`src/gui_qt/`）、Web 管理面板（`src/web_api.py` + `web/` 前端）。

**审查目标**：排查代码质量、潜在缺陷、安全漏洞与逻辑错误，逐文件记录问题并给出可执行的修复建议，为整改排期提供依据。

**审查方法**：

1. **分组并行深度通读**：按「根目录入口、平台解析、网络层、选源与录制流、调度与弹幕、录制基础设施、配置与工具、Web 服务层、桌面 GUI、UI 组件与前端、脚本与构建、测试有效性」划分为 14 个审查分组，逐文件分段通读至末行。大文件（`spider.py` 6977 行、`main.py` 5327 行、`gui.py` 4916 行、`web_api.py` 1588 行、`web/app.js` 2034 行）均按段覆盖至末行，无抽样盲区。
2. **关键结论二次实测裁定**：对全部「严重」级结论中的可机检项，使用项目 venv 的 Python **3.14.8** 执行实测复核（正则脱敏复现、URL 解析、主机白名单、内网判据、注册域判定），实测记录见附录 A。**未实测支撑的结论一律标注「（待核）」**。
3. **与前次报告的差分复核**：对 `CODE_REVIEW_2026-10-19.md` 的 5 项严重条目逐条核验现状，结果见第 7 节。

**审查性质**：全程只读，未修改任何源文件、测试或配置。

---

## 2. 审查范围与方法

### 2.1 纳入范围

| 模块组 | 主要位置 | 文件数 | 约行数 |
|---|---|---:|---:|
| 根目录入口 | `main.py`、`gui.py`、`web.py`、`i18n.py`、`msg_push.py`、`build_exe.py` | 6 | 13,333 |
| 平台解析 | `src/spider.py`、`src/platforms/`（7）、`src/proto/douyin.proto` | 9 | 8,905 |
| 网络层 | `src/async_http.py`、`sync_http.py`、`http_config.py`、`proxy.py`、`ws_client.py`、`cookie_cache.py`、`ttwid.py`、`node_install.py` | 8 | 3,170 |
| 选源与录制流 | `src/stream_select.py`、`src/stream.py` | 2 | 2,617 |
| 调度、采集与弹幕 | `src/scheduler.py`、`collector.py`、`danmaku_monitor.py`、`room.py`、`base.py`、`recorder_status.py`、`src/__init__.py` | 7 | 2,610 |
| 录制/后处理/基础设施 | `ffmpeg_install.py`、`ffmpeg_linux_download.py`、`ffmpeg_master_download.py`、`ffmpeg_proc.py`、`video_postprocess.py`、`srt_writer.py`、`log_archive.py`、`logger.py`、`startup_cleanup.py`、`notify.py` | 10 | 4,005 |
| 工具与配置 | `src/utils.py`、`config_io.py`、`config_read.py`、`config_bool.py` | 4 | 1,791 |
| Web 服务层 | `src/web_api.py`、`web_config.py`、`web_models.py`、`web_tray.py` | 4 | 3,604 |
| 桌面 GUI | `src/gui_qt/`（含 `pages/`）、`ui_kit.py`、`ui_theme.py`、`ui_scale.py`、`ui_motion.py`、`ui_fonts.py`、`ui_i18n.py` | 21 | 7,404 |
| 前端与自研 JS | `web/app.js`、`motion.js`、`index.html`、`style.css`、`src/javascript/`（4）、`StopRecording.vbs` | 9 | 5,163 |
| 脚本与构建 | `scripts/`（15 `.py` + 2 `.sh`） | 17 | 4,600 |
| 测试 | `tests/`（161 `.py` + 4 `.mjs`） | 165 | 78,782 |
| **合计** | | **267** | **131,984** |

### 2.2 排除项及理由

- `node_modules`、`vendor`、`dist`、`build`、`out`、`coverage`：按审查要求排除（当前工作区无 `dist`/`build` 产物目录）。
- `__pycache__`、`uv.lock`、`coverage.json/xml`、`DouyinLiveRecorder.egg-info`：构建缓存与自动生成产物。
- `.venv/`、`.workbuddy/`、`logs/`、`downloads/`、`ffmpeg/`、`node/`：运行环境与运行期产物。
- `.github/`（workflow、ISSUE_TEMPLATE）、`.pre-commit-config.yaml`、`.agents/skills/`：CI 配置与工具链 Skill（非运行期源码，仅在交叉核实判据时只读参考）。
- `typings/`（`.pyi`）：第三方库类型存根。
- `src/proto/douyin_pb2.py`、`src/javascript/crypto-js.min.js`：protoc 生成文件与 vendored 第三方压缩库。
- `docs/`、`i18n/*.json|yaml|po|mo`、`README*.md`、`CODE_WIKI*.md`：文档与语言资源。

### 2.3 严重度判定口径

| 级别 | 判据 |
|---|---|
| 严重 | 可远程/低权限利用的安全问题（凭据外泄、SSRF、脱敏失效、越权删除）；正常路径下的功能失效或数据丢失（漏录、产物损坏、误停录）；确定性资源耗尽；测试恒绿而无效（掩盖真实回归） |
| 中等 | 特定条件/特定配置下出错；资源泄漏与无界增长；并发竞态；安全判据强度弱于声明；门禁「假绿」风险；可观测性缺失导致排障反向 |
| 轻微 | 命名与结构、重复代码、死代码、硬编码文案、边界健壮性、可维护性 |

---

## 3. 问题统计与总体评价

| 严重程度 | 数量 | 分布 |
|---|---:|---|
| 严重 | 16 | 生产代码 13（安全 9、逻辑/数据丢失 3、功能错误 1）+ 工具脚本 1 + 测试 2 |
| 中等 | 104 | 生产代码 71、工具/构建脚本 28、测试 5 |
| 轻微 | 10 类（合并覆盖约 150 处具体位置） | 生产代码 7 类、脚本 1 类、测试 2 类 |
| **合计** | **130 项** | 严重与中等逐条列出；轻微按类别合并，每类附代表性位置与出现规模 |

**总体评价**：本轮审查显示，项目的安全防线在**覆盖面**上已相当完整——SSRF 逐跳复检、响应体上限、凭据脱敏、Zip Slip/解压炸弹防护、运行时二进制哈希钉定、Web 鉴权与同源校验、删除守卫等机制普遍存在，且多数配有回归锁；上一轮报告（`2026-10-19`）的 5 项严重条目中 4 项已真实修复（详见第 7 节）。工程纪律（注释规范、单一事实源、门禁分级）处于高位。

但本轮暴露出四个**系统性**问题，其共性是「防线已建、判据未闭环」：

1. **主机判据普遍采用字符串包含或字面量前缀，而非结构化解析。** `_match_host` 用子串包含导致 `evilweibo.com` 命中 `weibo.com/`（S-01，实测 5/5 命中）；B 站弹幕白名单未排除 `?`，使 `evil.com?.bilibili.com` 通过校验而真实连接 `evil.com`（S-06，实测）；内网判据只认字面量前缀，整数/八进制/IPv4-mapped IPv6/CGNAT 全部漏网（S-04，实测 4 类未命中）；「同域」用末两段近似注册域，`.co.kr`/`.com.cn` 下会把 Cookie 交给同公共后缀的任意主机（S-05，实测）。这四处是同一类缺陷的不同副本，应一次性统一口径。
2. **「异常即放行」的 fail-open 形态仍在多条链上并存。** 重定向已建前置校验却无逐跳校验（S-02）；安全闸已建 `security_rejected` 集合，却有一类拒绝不写集合（S-03）；备份脱敏已换容错解析器，却在「无 ini 节」与「原子写失败回退」两条上仍落明文（S-08）；node 官方校验文档不可达时零校验放行（S-12）。修好的那一版往往只覆盖了被发现的那一形态。
3. **最外层的宽泛 `except Exception` 正在制造静默的功能失效。** 抖音解析任一环节出错即丢弃整个已解析结果，房间此后每轮永久「未开播」（S-10）；播放器列表中带查询串的清晰度行被整条丢弃（S-16）；斗鱼全档失败仍返回 `is_live=True` 但不含任何流地址。这类问题的共同表现是「在播却不录，且日志无异常」，用户无法自助定位。
4. **测试总量庞大但存在成片的弱断言。** 14 个测试函数体内无任何断言、17 处 `assert_called_once()` 不带参数（S-14），用例名承诺的契约实际未被锁定；`src/spider.py` 覆盖仅 76.1%，缺口恰在取流主链路（M-100）。

---

## 4. 严重问题（16 项）

### S-01 平台分派用子串包含匹配主机，可被「后缀欺骗」域名整体劫持

- **位置**：`main.py:1580-1589`（`_match_host`，关键行 1588）；准入侧配合 `main.py:5144`
- **类型**：安全 / SSRF + 凭据外泄
- **说明**：`normalized = f"{scheme}://{host}/"`，判据为 `any(frag.lower() in normalized ...)`。宿主片段带尾斜杠时，任何以该片段**结尾**的主机名都成立；不带尾斜杠的片段（`3.cn`、`tb.cn`）则更宽松。而准入侧 `main.py:5144` 对「路径后缀为 `.flv`/`.m3u8`」无条件放行任意 host，两条叠加后攻击者可控域名即可被分派进对应平台的解析器。
- **实测裁定**（venv 3.14.8，直接复算 `_match_host` 判据）：

  | 构造 URL | 命中片段 | 判定 |
  |---|---|---|
  | `https://evilweibo.com/x.m3u8` | `weibo.com/` | **命中**（`normalized="https://evilweibo.com/"`） |
  | `https://evil-douyin.com/x.m3u8` | `douyin.com/` | **命中** |
  | `https://evil3.cn/x.m3u8` | `3.cn` | **命中** |
  | `https://evil-tb.cn/x.m3u8` | `tb.cn` | **命中** |
  | `https://evil-kugou.com/x.m3u8` | `kugou.com` | **命中** |

- **影响分析**：分派进平台解析器意味着以**带 Cookie 的平台请求头**向攻击者主机发请求（微博、抖音、酷狗、京东等均有 Cookie 配置位）。`main.py:1576-1578` 的注释只防御了「路径里出现平台名」，未防御「主机名以平台名结尾」；而 `.flv`/`.m3u8` 准入通道正是为手填自定义流设计的，攻击者只需在 `URL_config.ini`（Web 面板可写）里放一行即可触发。同类片段中 `live.shopee`、`m.miguvideo.com`、`show.lailianjie.com`、`www.picarto.tv` 等无尾斜杠形态风险更大。
- **修复建议**：判据改为 `host == frag 或 host.endswith("." + frag)`（片段统一去尾斜杠、加前导点）；并在分派前增加一道「host 必须落在 `PLATFORM_HOST` 白名单或用户显式自定义流清单」的校验。回归锁：`_match_host("weibo.com/")("https://evilweibo.com/x.m3u8") is False`。

### S-02 消息推送的 SSRF 闸门只校验首跳，重定向可直达内网并带回显

- **位置**：`msg_push.py:32-38`（`HTTPRedirectHandler` 在 handler 白名单内）、`:60-74`（`_checked_push_url`）、调用点 `:138→141`、`:182→185`、`:411→414`、`:490→493`；另有 `:351`、`:552` 两处**完全未校验**直接 `opener.open`
- **类型**：安全 / SSRF（带回显）
- **说明**：`_build_push_opener()` 显式注册了 `HTTPRedirectHandler`，会跟随 3xx；而 `_checked_push_url` 只在发起请求**前**调用一次，落地地址既不复核内网也不复核协议。
- **影响分析**：推送地址来自 `config.ini`（本模块 `:27-29` 自陈「Web 面板可写全部配置」是威胁面）。攻击者把地址设为自己的服务器并 302 到 `http://169.254.169.254/latest/meta-data/`，即可绕过「拒绝内部目标」这道闸门；ntfy 分支（`:511-515`）与钉钉/息知/Bark 分支还会把重定向后的响应体原样写进 `logs/streamget.log`（300KB 轮转、保留多份、求助时常整包上传），构成**带回显**的 SSRF，云元数据凭据可借此泄露。`:351`（Telegram）与 `:552` 两处连首跳校验都没有，破坏了「所有出站 URL 统一过检」的隐含不变量。
- **修复建议**：自定义 `HTTPRedirectHandler` 子类覆写 `redirect_request`，对每一跳的新 URL 重跑 `_checked_push_url`（含 `allow_local_targets=True` 的同一口径），非法即抛错，并限制最大跳数（如 5）；给 `:351`、`:552` 补首跳校验；响应体写日志前截断并脱敏。

### S-03 重定向安全闸的拒绝未登记，内网地址仍被交付 ffmpeg（S-04 同族残留）

- **位置**：`src/stream_select.py:979-992`（`except RedirectHopRejected`）；配合 `:1300`、`:1314` 的 `record_url` 复用分支
- **类型**：安全 / SSRF 防线被击穿
- **说明**：`_validate_stream_url` 有两条安全出口。`except _DerivedHopRejected`（`:965-978`）执行了 `security_rejected.add(url)`；而 `except RedirectHopRejected`（`:979-992`）只 `return False`，**未登记**。已核实 `:1300` 的判据为 `if record_url_str in probed and record_url_str not in security_rejected:`，即「探过但未被标记为安全拒绝」的地址会被照常 `_accept_source()` 交付。
- **影响分析**：`RedirectHopRejected` 命中（重定向落到内网）的候选，其 `probed[url]=False` 却不在 `security_rejected` 中，于是复用分支把它当作「CDN 拒绝」交付给 ffmpeg `-i`，ffmpeg 携带平台 Cookie 连内网目标。而抖音/TikTok/网易 CC 的 `record_url` 恒等于 `m3u8_url` 或 `flv_url`，该分支极易命中。这是上一轮 S-04 的**同族残留**：异常化改造已落地，但两条异常出口中只登记了一条。
- **修复建议**：在 `:979-992` 内同样 `security_rejected.add(url)`，与安全闸其它出口保持一致；回归锁两条：① 重定向落内网 + `last_resort=True` → `_validate_stream_url(...) is False`；② `m3u8_url == record_url` 且重定向落内网 → `select_source_url(...) is None`。

### S-04 内网判定只按字面量前缀，整数/八进制/IPv4-mapped/CGNAT 全部漏网

- **位置**：`src/stream_select.py:407-419`（`_PRIVATE_HOST_PATTERN`、`_IPV4_HOST_PATTERN`、`_is_derived_hop_allowed`）
- **类型**：安全 / SSRF 判据缺口
- **实测裁定**（venv 3.14.8，导入模块后直接匹配）：

  | 主机写法 | 实际指向 | 命中内网闸 |
  |---|---|---|
  | `2130706433` | 127.0.0.1（整数字面量） | **未命中** |
  | `0177.0.0.1` | 127.0.0.1（八进制） | **未命中** |
  | `::ffff:127.0.0.1` | 127.0.0.1（IPv4-mapped IPv6） | **未命中** |
  | `100.64.0.1` | CGNAT 100.64/10 | **未命中** |
  | `127.0.0.1` / `169.254.169.254` / `0.0.0.0` | — | 命中 |

- **影响分析**：被篡改/劫持的播放列表正文用上述任一写法即可让探针与 ffmpeg 访问本机或内网服务（Redis、云元数据、内网管理端）。`_IPV4_HOST_PATTERN` 虽能识别点分十进制，但只用于「IPv4 字面量返回空注册域」，未参与内网判定。
- **修复建议**：改用 `ipaddress` 模块解析：`ip_address(host)` 成功后按 `is_private/is_loopback/is_link_local/is_reserved/is_unspecified` 判定；对纯数字主机名先做整数化归一；无法解析时按「非内网」放行但记录 debug。注意保持「不做 DNS 解析」的既有取舍（注释 `:405-406`），仅把字面量判定升级为结构化判定。

### S-05 「同域」近似注册域按末两段比较，同公共后缀下会外泄 Cookie

- **位置**：`src/stream_select.py:437-458`（`_registrable_domain`、`_is_same_probe_scope`）；配合 `:466-471`（`_headers_for_derived_hop`）
- **类型**：安全 / 凭据外泄
- **实测裁定**：`_registrable_domain("a.example.co.kr") == "co.kr"`，`_registrable_domain("evil.co.kr") == "co.kr"`，`_is_same_probe_scope("https://a.example.co.kr/a.m3u8", "https://evil.co.kr/s.ts") == True`。
- **影响分析**：判为「同域」即**沿用原请求头**，也就是播放列表正文里的一行分片地址可让本机携带平台 Cookie（登录态）向同公共后缀的任意主机发 GET。`.co.kr`、`.com.cn`、`.co.uk`、`.com.br` 等双段公共后缀下均可直接触发，而本仓覆盖的 PandaTV、FlexTV 正是 `.co.kr` 域。`:438-439` 的注释只考虑了「双段主机名」的边界，未考虑公共后缀本身含两段。
- **修复建议**：引入公共后缀表（PSL，可只内置本项目涉及平台的后缀白名单）或改为「同 host 或 host 互为显式白名单子域」；无法判定时一律走 `_headers_without_cookie` 剥离分支（剥离 Cookie 只是少一次带凭据的探测，代价远小于凭据外泄）。

### S-06 B 站弹幕服务器白名单未排除 `?`，单点字符即可绕过

- **位置**：`src/platforms/bilibili.py:38-44`（`_bili_danmaku_host_allowed`）；调用点 `:129-130`
- **类型**：安全 / 凭据外泄（SESSDATA）
- **实测裁定**（venv 3.14.8）：

  | host 入参 | 白名单判定 | `urlsplit("wss://"+host).hostname` |
  |---|---|---|
  | `evil.com?.bilibili.com` | **True（放行）** | **`evil.com`** |
  | `evil.com#bilibili.com` | False | `evil.com` |
  | `evil.com%3F.bilibili.com` | True（放行但真实 host 含 `%3F`，不可利用） | `evil.com%3F.bilibili.com` |
  | `evil-bilibili.com` | False | — |
  | `evil.com.bilibili.com` | True（合法子域，符合预期） | — |

- **说明**：`:42` 只排除 `/` 与 `:`，未排除 `?` 与 `#`。`?` 之后的全部内容被 `urlsplit` 当作 query，真实连接目标是 `evil.com`。
- **影响分析**：B 站弹幕连接携带 `SESSDATA` / `DedeUserID`，一旦连接建立即外泄登录凭据，且该 host 若来自被篡改的下发，用户侧无任何感知。这是「校验了输入却未按解析器同口径校验」的典型形态。
- **修复建议**：判据改为先用 `urlsplit("wss://" + host).hostname` 取真实主机名再做后缀判定，或直接拒绝任何含 `^[a-z0-9.-]+$` 以外字符的 host；补一条以 `evil.com?.bilibili.com` 为输入的回归用例。

### S-07 凭据脱敏对 ini 行形态、短键名与 JSON 数值三类整体失效

- **位置**：`src/utils.py:1090-1100`（`_SECRET_QUERY_RE`）、`:1122`（`_SECRET_JSON_RE`）、`:1129-1141`（`mask_credentials`）
- **类型**：安全 / 凭据泄露
- **实测裁定**（venv 3.14.8，直接调用 `mask_credentials`）：

  | 输入 | 输出 | 结论 |
  |---|---|---|
  | `Authorization = Bearer abcdef123456` | 原样返回 | **逃逸**（ini 行形态 `键 = 值`） |
  | `token = abcdef123456` | 原样返回 | **逃逸** |
  | `[Cookie]\n抖音cookie = abc123` | 原样返回 | **逃逸** |
  | `sig=abcdef` | 原样返回 | **逃逸**（键名表中无 `sig`） |
  | `jwt=abcdef` | 原样返回 | **逃逸** |
  | `mysecret=abcdef` | 原样返回 | **逃逸**（小写复合边界只覆盖 `token\|key`） |
  | `{"ms_token": 12345}` | 原样返回 | **逃逸**（JSON 只匹配字符串值） |
  | `{"token": 123}` / `{"sign": 1}` | 原样返回 | **逃逸** |
  | `token=abcdef` | `token=***` | 正常 |
  | `https://x.com/?token=abcdef` | `https://x.com/?token=***` | 正常 |

- **影响分析**：`config.ini` 的 `[Cookie]`/`[Authorization]`/`[账号密码]` 节正是 `键 空格 = 空格 值` 形态，一旦配置片段随异常文本或日志输出即**明文落盘**（日志 300KB×3 份轮转常驻）。平台响应体里的 `msToken`、`expires` 常以数值下发，整段响应进日志即泄露。`src/utils.py:1134-1136` 自陈的「逐个调用点记得过码本身就是缺口」在这里被证实——缺口不止在调用点，也在判据本身。
- **修复建议**：① 形态一的 `=` 改为 `\s*=\s*`，并新增 `(?im)^\s*key\s*=\s*值` 的 ini 行兜底规则；② 键名表补 `sig`、`jwt`、`sig_` 变体，`:1084` 的 `_SECRET_LOWER_COMPOUND_BOUNDARY` 候选从 `(?:token\|key)` 扩为 `token\|key\|secret\|sign\|signature\|password\|passwd\|auth`；③ JSON 形态值段改为 `("[^"]*"\|-?\d+(?:\.\d+)?\|true\|false\|null)`；④ 补中文凭据键（密码/口令/令牌/授权码/密钥/秘钥），与 `web_config` 侧口径对齐。每条新增形态必须有配套回归用例。

### S-08 配置备份脱敏仍有两条明文落盘通道

- **位置**：`src/config_io.py:355-373`（`_redact_ini_secrets`）、`:408-419`（`backup_file` 的原子写失败回退）
- **类型**：安全 / 凭据泄露
- **说明**：上一轮 S-02（解析器 `strict=True` 遇重复键 fail-open）**已修复**（现用 `tolerant_config_parser` + 显式 warning，见 `:351-372`）。但残留两条通道：① `URL_config.ini` 实测**无任何小节**（首行即注释行），`parser.read_string` 恒抛 `MissingSectionHeaderError` → 走 `:373` 返回未脱敏原文；② `_atomic_write_text` 失败时 `:417-419` 回退 `shutil.copy2`，副本完全明文。
- **影响分析**：`backup_config/` 下两份文件共约 12 份副本常驻，而该目录正是用户打包/云同步/求助外发的高频对象。当前实现只打一条 warning，用户极难察觉自己手里是明文。
- **修复建议**：对无小节文件改用「整份按行 + `mask_credentials`」的脱敏通道而非 ConfigParser；`copy2` 回退前先按字节流做一次 `mask_credentials`；脱敏失败时除告警外给备份文件名加 `.UNMASKED` 后缀，让用户可识别。

### S-09 同步 HTTP 通道完全没有内网闸门，且重定向不复核

- **位置**：`src/sync_http.py:117-126`（`_reject_unsafe_scheme` 只校 scheme）、`:282`、`:343`；`:50`（`_HTTP_ONLY_HANDLERS` 含 `HTTPRedirectHandler`）、`:353`（落地地址只在 `abroad=True` 分支复核）
- **类型**：安全 / SSRF（潜伏）
- **说明**：异步侧那道 `internal_stream_target_reason`（`async_http.py:491`）在 `sync_req` 里不存在，因此 `http://127.0.0.1:6379/`、`http://169.254.169.254/...` 会被真实发出，并**把响应体原文当作返回值交给调用方解析**（完整 SSRF 回显）。
- **影响分析**：模块头 `:78-81` 自述「当前没有任何生产 importer」，故属**潜伏**漏洞——一旦有新代码接线 `sync_req`，即刻可利用。这类「暂时安全」的通道最危险之处在于接线者会默认它已具备与异步侧同等的防护。
- **修复建议**：复用 `async_http` 的 `internal_stream_target_reason` 作为唯一判据（禁止另写一份内网名单）；给 `HTTPRedirectHandler` 子类覆写 `redirect_request` 逐跳复核；补齐落地 scheme 复核到非 abroad 分支。在接线前，于模块头增加「本通道尚未具备内网闸门，接线前必须先补」的显式告警注释。

### S-10 抖音解析最外层宽泛异常吞掉已解析结果，房间此后永久不录

- **位置**：`src/spider.py:830`（web 入口）、`:954`（app 入口）
- **类型**：逻辑错误 / 功能性数据丢失
- **说明**：两个入口的最外层 `except Exception` 吞掉一切并返回 `{"anchor_name": ""}`。ORIGIN 注入（`:825`）之后任何一步出错，都会把**已解析好的 `room_data`（含主播名与全部流地址）**整体作废。
- **影响分析**：表现为「该房间此后每轮固定『网址内容获取失败』」，用户只能靠删掉重加恢复；日志无任何异常栈（被吞成一条通用告警），排障归因完全反向。抖音是本仓第一大平台，此缺陷的影响面按房间数线性放大。
- **修复建议**：把 `try` 范围收窄到 ORIGIN 注入那一段，失败时保留已解析的 `room_data` 原样返回（只丢弃注入结果）；顶层兜底保留但必须 `logger.exception` 输出栈。

### S-11 知乎落地页地址未校验 host，`user_id` 未编码即拼入路径

- **位置**：`src/spider.py:5653`（`live_page_url` 取自响应体 `theater_url` 直接请求）、`:5639`（`user_id` 拼进 `api.zhihu.com/people/{user_id}/profile`）
- **类型**：安全 / SSRF + 凭据外送
- **说明**：`live_page_url` 直接取自知乎 API 响应体，未做 host 白名单与内网判定，就用**已注入用户 Cookie** 的 `headers` 发起请求。同仓 XHS（`:2505-2541`）、Shopee（`:6129-6161`）已建三道闸，此处为零校验，属**同仓不一致**的缺口。
- **影响分析**：响应可控时（MITM、接口被污染）一条链接即可把登录 Cookie 递送到任意 http(s) host，含回环与云元数据地址。`user_id` 未 `quote` 还会让 `../` 改写请求路径。
- **修复建议**：复用 `_xhs_is_allowed_host` + `web_config._host_internal_reason` 作为落地页校验，不过闸即剥离 Cookie 并返回未开播；`user_id` 用 `urllib.parse.quote(..., safe="")`。

### S-12 node 安装包下载无响应体上限，官方校验不可达时零校验放行

- **位置**：`src/node_install.py:231-242`（zip 流式下载）、`:188-193`（版本页 `response.text`）、`:152-179`（TOFU 降级分支）
- **类型**：安全 / 资源耗尽 + 供应链校验降级
- **说明**：下载循环把 `Content-Length` 只交给 tqdm 当进度条，从不用于限额，也不校验实际字节数与声明值一致；`timeout=30` 是单次读写超时而非总时长，慢速滴漏不触发。TOFU 分支在取不到 nodejs.org 的 `SHASUMS256` 时（`:152-158` 仅 warning），若旁路 `.sha256` 不存在则 `:178-179` **直接把本次哈希记为基线并返回 True**。
- **影响分析**：镜像被替换或链路被劫持时可让进程持续写盘直到磁盘耗尽，污染的是 `execute_dir`（冻结产物的 `_internal/`）；更严重的是「首次下载恰好发生在官方文档不可达窗口」时，被替换的 zip 会被无条件信任并解压、前置进 PATH 后执行——攻击者只需让那次 15s 探测失败即可把校验降级归零。
- **修复建议**：下载循环内累计字节数，超过预期上限（如 1.5×Content-Length 或固定 512MB）即抛错并删除部分文件；版本页改按 `iter_content` 限长读取；官方文档不可达时**默认拒绝安装**并提示重试（或要求显式开关），把降级事件升级为 error 级并计入失败计数。

### S-13 `--snapshot` 可删除当前工作目录之外的任意目录树

- **位置**：`scripts/check_annotations.py:391-455`（`_reject_dangerous_baseline`）；触发点 `:466-467`（`shutil.rmtree(baseline)`）
- **类型**：安全 / 不可逆数据丢失
- **说明**：已核实现状：守卫拒绝文件系统根、家目录本体及第一层子目录、cwd 本体及其祖先、一份写死的系统目录清单；`:422` 对「严格位于 cwd 之下」显式放行。**cwd 之外的任意绝对路径（`--snapshot D:\OtherRepo`、`/srv/data`、`E:\backup`）全部放行**。
- **影响分析**：一个看似只读的「建立快照」动作会整树删除无关目录，且无二次确认。判定是排除式黑名单而非白名单，这是本仓反复禁止的形态（同一模式在 S-01/S-04 上已造成两处可利用缺陷）。
- **修复建议**：改为白名单正向判定——要求 `resolved` 严格位于 cwd 之下才放行，或要求目标目录为空/不存在；确需外部目录时显式 `--allow-outside` 并打印将被删除的路径与条目数要求确认。

### S-14 成片弱断言：14 个测试函数无任何判据，17 处只锁调用次数

- **位置**：`tests/test_platform_danmaku_offline.py:303/587/732/791`、`tests/test_web_tray.py:654` 等共 **14 处**；`tests/test_async_http.py:528/628/777`、`tests/test_sync_http.py:98/155/173/428/503`、`tests/test_bilibili_danmaku_info.py:412/505` 等共 **17 处** `assert_called_once()`/`assert_called()` 不带参数
- **类型**：测试有效性 / 假绿
- **说明**（已由 AST 全量扫描 + grep 计数佐证）：14 个测试函数体内无 `assert`、无 `pytest.raises`、无 `.assert_*`、也未委托同文件 helper，判据只有「没抛异常」。典型如 `test_m3u8_head_405_fallback_to_get`（`test_async_http.py:757`）只断言 `result is True` + `mock_client.get.assert_called_once()`，而它要锁的真实契约是 `async_http.py:742` 的降级 Range-GET 探针（`headers={"Range":"bytes=0-0"}`）——删掉 Range 头让探针退化为整文件下载，该用例照样绿。
- **影响分析**：用例名承诺了行为契约（`_without_ws_is_noop`、`test_cancel_is_idempotent`、`test_snapshot_is_json_serializable`），实际什么都没锁。生产实现退化为「静默做了错事但不上抛」时全部恒绿，是本仓最需要警惕的假绿形态。
- **修复建议**：no-op 类断言替身零调用（如 `ws.sent == []`）；`is_idempotent` 断言第二次 cancel 后 `after_calls` 不增长；承载语义参数的调用改用 `assert_called_once_with(...)` 或显式断言 `call_args.kwargs`（`test_async_http.py:549-550`、`:570`、`:711` 已有正确范式可照抄）。

### S-15 解析失败/过短的配置行会被判定为「已注释」，正在进行的录制被强制停止

- **位置**：`main.py:5071-5072`（`if len(line) < 18: continue`）、`:5180-5189`（行解析异常 `continue`）；配合 `:5202-5204` 的归并逻辑
- **类型**：逻辑错误 / 数据丢失
- **说明**：已核实 `:5159` 才把 URL 加入 `_seen_urls`；凡在 `:5071` 因过短 `continue`、或在 `:5189` 因解析异常 `continue` 的行，其 URL 都不在 `_seen_urls` 中。而 `:5202-5204` 的判据是「running 中的 URL 不在 `_seen_urls` 且不在 `_url_comments` → 视为已注释」，随即把它加进 `url_comments`，房间线程据此**强制停掉正在进行的录制**。
- **影响分析**：合法短链（如 `https://3.cn/xxx`）或**任何一行偶发解析失败**（如 `update_file` 写回抖动、`parse_xhs_live_url` 抛错）都会触发；用户表现为「录了一半自己停了，配置行一个字没变」，且日志里只有一条「配置行解析失败」的告警，与停录之间没有可见的因果链。
- **修复建议**：用独立的「本轮解析失败」集合记录被跳过的行，并**跳过 `:5202` 的归并**；长度阈值改为按 URL 结构判据（`urlsplit` 有 host 即有效）而非字符数；对被跳过的行打 warning 并保留上一轮状态。

### S-16 播放器列表解析对相对行与带查询串行处理错误，5 个平台产出无 host 地址

- **位置**：`src/spider.py:501-531`（`get_play_url_list`，关键行 `:524`）；调用点 `:3400`、`:3560`、`:3755`、`:4831`、`:6326`
- **类型**：逻辑错误 / 功能性失效
- **说明**：函数只绝对化 `http(s)://` 与 `//` 两种行，纯相对行（如 `1080p/index.m3u8`）原样返回，5 个调用点（PandaTV / WinkTV / TTingLive / Twitch / YouTube）未用 `urljoin` 归一化。`:524` 的兜底循环只收 `endswith("m3u8")` 的行，带查询串的相对行（`x.m3u8?token=...`）被整条丢弃。ShowRoom（`:5276`）、CHZZK（`:5741`）已用 `urljoin`，说明是已知问题但漏改 5 处。
- **影响分析**：前者的产物是无 host 的地址，ffmpeg 必失败；后者让多清晰度候选为空、上层回退单地址，用户侧表现为「画质下拉只有一项」或「在播却录不下来」。两者都不会抛异常，被装饰器吞成「未开播」。
- **修复建议**：在函数内对相对行统一 `urljoin(m3u8, line)` 返回全绝对地址；兜底判据改为 `urlparse(line).path.endswith(".m3u8")` 或正则 `\.m3u8(\?|$)`。

---

## 5. 中等问题（104 项）

> 说明：同类问题已合并，每条给出出现次数与代表性行号。

### 5.1 根目录入口（11 项）

| 编号 | 位置 | 类型 | 问题与影响 | 建议 |
|---|---|---|---|---|
| M-01 | `main.py:5137`、`:5144` | 逻辑错误 | 准入侧用 `url.split("/")[2]` 取 host（`:5137`），分派侧用 `urlsplit().hostname`（`:1585`），口径不一致。带凭据地址 `https://u:p@www.huya.com/123` 的 `url_host` 为 `u:p@www.huya.com`，`in PLATFORM_HOST` 恒假 → 判「未知链接」并在 `:5178` 自动把该行注释掉；而 `:3744`/`:3140` 明确支持带凭据地址，只有 `.flv`/`.m3u8` 形态能存活 | 统一走 `urlsplit(url).hostname or ""` |
| M-02 | `main.py:3873`、`:5216`、`:5239`、`:1117` | 潜在缺陷 | 录制状态以 `f"序号{count_variable} {anchor_name}"` 为键，`count_variable` 来自瞬时 `len(running_list)`，线程退出后递减复用 → 同名主播的两个房间算出**同名键**，`recording`/`recording_time_list` 互相覆盖，`clear_record_info` 误清另一房间状态，字幕线程误删 | 状态键改用 URL/UUID，`record_name` 仅作展示 |
| M-03 | `main.py:5216` vs `src/notify.py:318/339` | 并发缺陷 | `monitoring` 被两种语义写：主循环每轮整体重算，notify 在锁内增量递减。线程在两者之间退出时递减被抹掉 → 计数漂移直接喂给 `scheduler.set_active_count`（`:5306`），自适应并发容量被错误压低 | 去掉重算，只由退出路径增量维护 |
| M-04 | `main.py:3887`、`:5218`、`:5260-5262` | 并发缺陷 | `not_record_list` 无锁：录制线程 append，主线程读取并用切片**整体替换**（非原子），与 append 交错会丢条目 → 该房间再也不会被拉起 | 统一在 `record_state_lock` 内增删，改为按值定点移除 |
| M-05 | `main.py:4993-4997`、`:5029-5033` | 潜在缺陷 | 磁盘容量检测抛异常（网络盘离线/盘符拔出）时置 `disk_free_gb = inf`，随即命中 `elif disk_limited:` → **解除录制暂停**。磁盘实际不可用时恢复拉起 ffmpeg，全部写入失败并被计入失败样本与探针退避 | 检测失败保持上一状态，只在连续 N 次成功且空间充足时解除 |
| M-06 | `main.py:4615-4617`、`:4661-4662`、`:4070`、`:763` | 安全 | 「是否启用 https 录制」开关**全局关闭拉流侧证书校验**（`:4616` 注释自述），作用范围是所有平台而非 `:4626` 的平台豁免清单。为绕虎牙 CDN 证书问题开启后，抖音/B站/YouTube 全部拉流变成不校验证书，可被中间人劫持 | 平台豁免名单作为唯一入口，https 开关不再联动全局校验 |
| M-07 | `main.py:575-578`、`:583-589`、`:4672` | 代码质量 | 模块导入即无条件注册 SIGINT/SIGTERM/SIGBREAK 处理器（旧处理器被丢弃）、注册 3 个 atexit、覆写 `builtins.print`。`web.py`/`gui.py`/测试 `import main` 时宿主的信号处理与退出清理被静默劫持 | 收进 `install_runtime_hooks()` 由真实入口调用；注册前保存并链式调用原处理器 |
| M-08 | `main.py:1054-1056`、`:1244` | 资源/可观测性 | `Popen(stdin=PIPE, stderr=STDOUT)`：stdin 管道从未写入也从未关闭，整个录制周期（可达 6 小时）滞留句柄；stdout 未设 PIPE，ffmpeg 错误输出直接继承父 stdout，守护循环读不到任何报错，失败归因只能靠退出码 | stdin 改 `DEVNULL`；错误输出重定向到临时文件并在收尾读尾部若干行 |
| M-09 | `main.py:434-457`、`:4692-4708` | 代码质量 | 24 个主循环临时量被提升为模块级全局并在 `main()` 里用一屏 `global` 声明，任何函数都可能读到其它轮次残留值 | 改局部变量/上下文对象 |
| M-10 | `main.py:4435-4444`、`:4474-4484`、`:5309-5314` | 异常处理 | 三层 `except Exception` 把解析、网络、编程错误一并吞成一行，随后 `record_error` 把它**计入平台熔断样本**——KeyError/TypeError 被当作线路故障，触发熔断拖慢其它房间 | 顶层兜底用 `logger.exception`；只有网络/HTTP 类异常才调 `record_error` |
| M-11 | `main.py:4042`、`:4058`、`:3730-3738` | 潜在缺陷 | 海外平台/代理平台判定用 `in record_url` 整串子串匹配，URL 的 query 里出现 `www.tiktok.com`/`soop` 等字样即误判 | 统一用 `urlsplit(record_url).hostname` 做 host 后缀匹配 |

### 5.2 平台解析（8 项）

| 编号 | 位置 | 类型 | 问题与影响 | 建议 |
|---|---|---|---|---|
| M-12 | `src/spider.py:3610`、`:2841`、`:4283`、`:3774`（对照 `:3964`） | 安全 | 4 处登录/取流异常日志原样输出 `e`。登录与代理异常原文内嵌含 `user:pass@` 的代理 URL 与请求体；`login_popkontv:3964` 明确做了 `mask_credentials`，四处漏改 | 统一 `e=utils.mask_credentials(str(e))` |
| M-13 | `src/spider.py:4903-4981`（关键 `:4963`） | 逻辑错误 + 死代码 | `get_huajiao_sn` 全仓无调用点（`:5134` 走的是 app 版），却携带唯一的 `utils.replace_url(... '#'+url)` 写回逻辑：WAF/风控壳页（有响应但无 `var feed`）命中 `:4937` 的 ValueError 分支，**一次风控即永久注释掉用户房间** | 删除该函数；若保留，改用「响应可解析且字段确实为空」作失效判据 |
| M-14 | `src/spider.py:338-343` | 逻辑错误 | `_ensure_twitch_client_id` 慢路末尾 `return _cached_twitch_client_id` 无代理一致性检查（快路有），代理 B 重取失败且 TTL 未过期时会拿到代理 A 的 Client-Id，与 `_ensure_kuaishou_did`（`:291-300`）口径不一致 | 慢路末尾补一致性判定，不匹配返回 `""` |
| M-15 | `src/spider.py:2631`、`:5639`、`:2719`、`:5000`（对照 `:5635`） | 安全 | 小红书/知乎 `user_id`、bigo `room_id` 取自 URL query 未 percent 编码即拼进路径；花椒 `:5000` 的 `split("user/")[1]` 未剥子路径（知乎 `:5635` 已用 `.split("/")[0]` 修掉，花椒漏改） | 一律 `urllib.parse.quote(value, safe="")` |
| M-16 | `src/spider.py:3394`、`:3553` | 代码质量 | `raise RuntimeError(cast(object, error_code), _dig(...))` 传两个位置参数，`str(e)` 实际是 `('needXxx','msg')` 元组字面量，告警文案不可读 | 改 `RuntimeError(f"{code}: {message}")` |
| M-17 | `src/spider.py:377`（116 处调用） | 安全/资源 | `_safe_loads` 对平台响应体直接 `json.loads`，无大小上限与嵌套深度限制；被风控/恶意 CDN 返回超大或深嵌套 JSON 时一次性吃满内存并长时间占用事件循环 | 在 `_get_str_response` 后加长度（如 8MB）与深度阈值 |
| M-18 | `src/spider.py:3145-3146`、`:3236` | 空值/边界 | 前者失败时返回空 `view_url` 仍拼 `?aid=` 并以 `is_live=True` 返回，坏地址每轮白烧探针；后者 `url[-1]` 在配置为空串时抛 `IndexError`，被装饰器吞成「未开播」且无日志线索 | 空 `view_url` 即 return；改 `if url and not url.endswith("/")` |
| M-19 | `src/spider.py` 66 处 Cookie 块（代表 `:5816-5830`、`:5968-5986`）；`:5455-5473` vs `:5582-5597`；`:3010-3032` vs `:3102-3117` | 代码质量 | 66 处逐字相同的 `if cookies: headers["Cookie"]=cookies`，20+ 平台函数是同一套模板（116 处 `_warn_api_abnormal`）；另有三组同功能双份实现（畅聊/音播 `get_live_domain`、SOOP 全球区/韩国区 `get_url_list`）且**已漂移**（前者用 `urljoin` 正确，后者用 `rsplit` 前缀拼接会产出坏地址） | 抽 `_build_headers` 与统一「解析-归因-返回未开播」helper；同功能实现合并为一份 |

### 5.3 选源与录制流（7 项）

| 编号 | 位置 | 类型 | 问题与影响 | 建议 |
|---|---|---|---|---|
| M-20 | `src/stream_select.py:1166-1176`、`:1342-1349` | 潜在缺陷 | `probe_client` 仅有标注未赋初值，构造异常的捕获面是 `ValueError, TypeError, httpx.InvalidURL`；若抛 `ssl.SSLError`/`OSError`，`finally` 的 `if probe_client is not None` 触发 `UnboundLocalError`，**掩盖原始异常**并穿透房间线程 | try 前置 `probe_client = None`，或把构造异常收敛为 `except Exception` |
| M-21 | `src/stream.py:634`（对照 `:580-613`） | 潜在缺陷 | `json.loads(stream_data_raw)` 在任何 try 之外，而函数内对每条流条目做了精细的 `except (ValueError, TypeError, json.JSONDecodeError)` 保护（注释明确说「一条坏条目不得让整个房间吞成未开播」）。上游 JSON 被截断时整房被静默判为未开播，与逐条防御的设计意图自相矛盾 | 用 try 包裹，失败走 `return result` 并留 warning |
| M-22 | `src/stream.py:734`、`:464-467`、`:1077-1182` | 潜在缺陷 | 多处对平台下发结构做无防御的下标/属性访问（快手 `flv_list[0]`、抖音 `d.get(...).get(...)`、网易 `stream_list[i].get("cdn")`、YY `list(...values())[0]`），异常被 `@trace_error_decorator` 吞成「未开播」 | 统一 `isinstance(x, dict)` / `.get(k) or {}` 归一 |
| M-23 | `src/stream.py:511` vs `src/stream_select.py:283` | 逻辑错误 | h265 判定口径不一致：抖音侧认 `h265`/`hevc` 且大小写不敏感，选源侧 `_is_h265()` 只认 `codec[0] == "h265"`。`HEVC`/`H265` 地址在选源侧不被剔除，保存 FLV/纯音频时仍交付 ffmpeg 直拷 → 录制失败或产物异常 | 两处共用同一实现，大小写不敏感且同时识别 `hevc` |
| M-24 | `src/stream.py:857-859`（对照 `:875`） | 逻辑错误 | 蓝光分支的 `available_qualities` 无条件加入 `UHD`/`LD`，`max_ratio<=0` 时变成 `["OD","UHD","LD"]`，对外声称的档位与房间实际档位不符 | 两分支统一按 `room_codes`/`HUYA_CODE_ORDER` 推导 |
| M-25 | `src/stream_select.py:62-63` | 潜在缺陷 | Windows 保留名只在末尾加 `_`：`CON.txt` → `CON.txt_`，而 Windows 对 `CON` 后接任意扩展名一律拒绝，目录创建仍失败 → 录制静默失败 | 对点号前的基础名做保留名判定并改名后再拼扩展名 |
| M-26 | `src/stream.py:1038-1058`；单轮预算见 `stream_select.py:613/646/711` | 逻辑错误 / 资源 | 斗鱼 `for...else` 在全部 rate 失败后仍组装 `is_live=True` 且**不含任何流地址**的 result，上层把「开播但无地址」当待录房间空跑 ffmpeg；另单轮选源无总时长预算（节流 sleep + 401/403 复核 + 每候选 1~4 次 5s 探针），虎牙 4 条 CDN 时单房间单轮可达数十秒 | 全档失败返回 `is_live=False`；为 `select_source_url` 增加整体 deadline |

### 5.4 网络层（8 项）

| 编号 | 位置 | 类型 | 问题与影响 | 建议 |
|---|---|---|---|---|
| M-27 | `src/async_http.py:520`、`:611`、`:644`（→ `web_config.py:436`） | 并发/性能 | 逐跳复检在**事件循环线程内执行阻塞式 DNS**（`socket.getaddrinfo`），发生在 response 钩子内，即每一跳、每一次请求都在循环线程同步解析。DNS 慢/超时（可达数秒~十几秒）会冻结该房间的整个事件循环，80+ 房间下大面积卡顿 | 改 `loop.getaddrinfo()` 或 `await asyncio.to_thread(...)` 并加超时 |
| M-28 | `src/sync_http.py:307-309`、`:136-174` | 资源泄漏 | ① `stream=True` 的响应在 `redirect_url=True` 时提前 `return response.url`，响应体从未读取、连接从未 `close()`；② thread-local `requests.Session` 仅在 `atexit` 关闭，房间线程反复创建/销毁时连接池只能靠 GC 回收 | 用 `with ... as response` / `finally: response.close()`；增加按线程的 Session 回收 |
| M-29 | `src/node_install.py:260-261`、`:44`、`:381` | 安全 | 解压后把 `execute_dir/node` **前置**到 PATH，随后 `subprocess.run(["node","-v"])` 优先命中该目录；`execute_dir` 位于用户可写区，任何能在该目录放 `node.exe` 的本地主体都会被以本进程权限执行 | 校验目录 ACL 与属主；用 `shutil.which` 的绝对路径调用 |
| M-30 | `src/ws_client.py:96-107`（关键 `:102-104`） | 安全/资源 | `decompress_brotli_limited` 是**事后检测**：先把单块 4KB 输入的全部输出物化再判上限（与 zlib 在 C 层硬截断不同强度），且 `obj` 用完未 `close()`、异常路径下 decompressor 泄漏 | 缩小喂入粒度；`try/finally` 释放；残余风险同步进 AGENTS 已知风险清单 |
| M-31 | `src/async_http.py:191-206`、`:59-62`；`src/ttwid.py:215-222` | 资源泄漏 | 跨循环/临时循环创建的 `AsyncClient` 不会被真正 `aclose()`（只丢引用交 GC）；`warmup_ttwid` 用 `asyncio.run` 建的临时循环客户端在返回后即成孤儿。Windows 长跑可观测句柄与端口占用持续偏高 | 记录创建循环并在其所属循环内注册 close 回调；退出日志给出实际未关闭计数 |
| M-32 | `src/async_http.py:740`（对照 `:736-739`、`:757-765`） | 逻辑错误 | Range-GET 复核只对 `.m3u8` 生效，而注释自承「部分 CDN 对 HEAD 返回 403/404 但 GET 可拉流」，该成因对 flv/直链同样成立 → 非 m3u8 直链遇 HEAD 403/404/405 一律判不可达并降到相邻画质 | 条件改为「HEAD 非 2xx 且非明确不可达」，至少把 405/501 单独挑出进入 GET 复核 |
| M-33 | `src/sync_http.py:319`（对照 `:314-318`） | 逻辑错误 | `json_data` 仅 `dict/list` 才生效，传 `str/int/bool` 时**静默丢弃请求体退化成 GET**；json 分支始终未设 `Content-Type` | 与 async 侧对齐，对不支持形态显式 `raise ValueError`；补 `Content-Type` |
| M-34 | `src/cookie_cache.py:221-223`、`:171`（写侧 `:293` 有拷贝）；`src/http_config.py:9-20`、`:46-47` | 并发/封装 | 缓存命中路径直接返回内部字典引用，任意调用方就地修改即**污染进程级共享缓存**；`http_config` 三个模块级可变全局由主循环热更新、无锁，`set_platform_ssl_verify` 不校验平台名与取值 | 读取侧 `return dict(entry[0])` 或 `MappingProxyType`；配置改为按对象引用整体替换 |

### 5.5 调度、采集与弹幕（9 项）

| 编号 | 位置 | 类型 | 问题与影响 | 建议 |
|---|---|---|---|---|
| M-35 | `src/scheduler.py:320-326` | 逻辑错误 | 动态模式 `target = max(configured, min(max_capacity, scaled))`，配置值大于 `max_capacity` 时结果仍取配置值，绕过声明的安全上限；错误配置可瞬间放开大量并发请求 | 改为 `min(max_capacity, max(configured, scaled))` |
| M-36 | `src/scheduler.py:299`、`:411-417`；`src/room.py:135-151` | 资源 | 2 处进程级映射无容量限制：熔断器按所有历史 host 永久保留；`sec_user_id` 缓存只判失效不删除过期键。长期运行并持续增删房间时内存无界增长（24×7 场景） | 改带最大容量的 LRU/TTL；锁内周期清理；删除房间时回收熔断状态 |
| M-37 | `src/danmaku_monitor.py:630-636`、`:643-695` | 并发竞态 | stats 线程发现房间表为空后 `break`，到 `finally` 注销引用之间存在窗口；新房间此时调 `_ensure_stats_thread()` 会看到旧线程仍 `is_alive()` 而不启动，随后旧线程清空引用 → 房间永久没有周期统计 | `finally` 持锁注销后检查 `_rooms`，非空则原子创建替代线程 |
| M-38 | `src/collector.py:284-314` | 并发/资源 | 采集线程 join 超时后不检查存活便继续收尾；SRT 写线程超时后仍立即关闭其正在使用的 `SrtWriter`。卡住的线程泄漏事件循环与句柄，稍后恢复时与 `close()` 并发访问 | join 后统一检查 `is_alive()`；写线程未退出时不并发关闭其对象 |
| M-39 | `src/recorder_status.py:33`、`:59`、`:67-68`、`:181` | 数据竞争 | `main.error_count` 共 3 处读取未持写侧使用的 `max_request_lock`（其中一处错位于 `record_state_lock` 内），累计值与 `recent_errors` 分时采样可能返回相互矛盾的状态 | 在 `max_request_lock` 临界区内同时快照两个字段 |
| M-40 | `src/collector.py:387-408`、`:441-469` | 异常处理 | `_run()` 外层只有 `finally`，平台类构造、回调注入异常会直接逃出后台线程（只有 `danmaku.start()` 阶段受保护），线程带 traceback 退出而监控条目仍显示 started | 外层补 `except Exception`，记录脱敏异常并主动上报关闭状态 |
| M-41 | `src/base.py:40-47`、`src/collector.py:426-439`、`src/room.py:208-214`（对照 `room.py:102`） | 安全 | 4 处外部异常日志直接格式化原始异常对象；代理异常、请求 URL、平台 token 可能含凭据（`room.py` 脱敏了 `api` 字段却仍原样记 `e`） | 所有外部网络/平台异常先过 `mask_credentials` |
| M-42 | `src/scheduler.py:131-134`、`:179-184` | 边界 | `min_samples > window` 时样本数永远达不到阈值，熔断器永不打开；`fail_rate=0` 时即使全部成功，`0 >= 0` 也触发熔断 | `min_samples` 限制在 `1..window`；要求失败率严格大于 0 |
| M-43 | `src/room.py:75-76`、`:159-186`；`src/danmaku_monitor.py:711-719` | 逻辑错误 | 只要调用头中存在 UA 或 Cookie 任一就完全不补另一个默认头，`get_unique_id()` 又用 ttwid 直接覆盖调用方整串 Cookie → 丢失登录态或触发风控；另 `log_path` 为裸文件名时 `os.makedirs("")` 抛错被吞 → 边车输出被静默禁用 | 以 `HEADERS` 为基底合并，Cookie 解析后只替换 `ttwid` 键；仅在父目录非空时 `makedirs` |

### 5.6 录制基础设施、配置与工具（15 项）

| 编号 | 位置 | 类型 | 问题与影响 | 建议 |
|---|---|---|---|---|
| M-44 | `src/ffmpeg_install.py:368`、`ffmpeg_master_download.py:385`、`ffmpeg_linux_download.py:403` | 安全 + 并发 | 三处下载器用**固定可预测文件名**落在共享应用目录，以 `open(...,"wb")` 打开（无 `O_EXCL`/`O_NOFOLLOW`）、无跨进程锁。① 两实例并发安装时互相覆盖并在各自 `finally` 里 unlink 对方刚下载的包；② 能写该目录的本地主体可预置同名符号链接，把数百 MB 数据重定向写入任意路径 | 用 `tempfile.mkstemp(dir=...)` + `O_CREAT\|O_EXCL\|O_NOFOLLOW`；安装期加目录级文件锁 |
| M-45 | `src/ffmpeg_install.py:437-440`、`ffmpeg_master_download.py:466-468` | 数据丢失 | `rmtree(target)` 之后 `copytree`，中途失败（磁盘满/杀软占用）无任何回滚：上一次可用 ffmpeg 已删除、本次只拷一半 → `execute_dir/ffmpeg` 变空壳，程序彻底失去录制能力且下次启动重复这条路径 | 先解压到临时子目录再原子替换；`rmtree` 前校验 `bin_dir` 含必需可执行文件 |
| M-46 | `src/log_archive.py:41-46`、`:63-71`、`:280-322` | 资源 | 归档只改名从不清理，反复启停（循环监测每天数十次）让 `logs/` 无界增长；`web_console.log`（`:217`）本身无轮转，Web 后台长期运行持续增长 | 归档后按数量/总大小/保留天数裁剪；`web_console.log` 增加写入侧轮转 |
| M-47 | `src/ffmpeg_install.py:450`、`ffmpeg_master_download.py:478`、`ffmpeg_linux_download.py:443` | 逻辑 | 三处 PATH 注入口径不一致：install 用模块级常量路径（与本次 `dest_dir` 不一致时 `ffmpeg -version` 复核必然失败 → 安装成功被判失败）；master/linux 读运行时 PATH，**重复调用把同一前缀反复叠加** | 统一为「本次目标目录 + 去重后的原 PATH」 |
| M-48 | `src/ffmpeg_install.py:420`、`ffmpeg_master_download.py:455`（对照 linux `:371`） | 资源/兼容 | Windows 两处把解压落在 `%TEMP%`，Linux 侧刻意落在应用目录内；gpl 包解压后可达数百 MB，在 `/tmp` 为小 tmpfs 的容器上直接 ENOSPC | 与 Linux 侧统一落在目标目录父目录；解压前检查可用空间 |
| M-49 | `src/ffmpeg_install.py:376-389`（对照 linux `:306-359`、master `:188-234`） | 健壮性 | 官方源（默认且唯一的 Windows 自动路径）下载**完全没有重试与退避**，一次连接重置即整条安装失败；`iter_content` 无字节上限、`allow_redirects` 默认跟随 | 复用另两处已有的「重试 3 次 + 指数退避」；下载循环内累加字节数并设上限 |
| M-50 | `src/log_archive.py:285`、`src/logger.py:43` | 代码质量 | 两处手写布尔判定（`in ("1","true","yes")`、`== "1"`）绕开唯一入口 `parse_config_bool`：`DOUYIN_DISABLE_LOG_ARCHIVE=on` 不生效（pytest 环境会误改开发者真实日志）、`DLR_GUI_PARENT=TRUE` 不生效（触发轮转 PermissionError 与日志全量丢失） | 两处改 `parse_config_bool(os.environ.get(...), False)` |
| M-51 | `src/utils.py:547-548`、`:559-580` | 安全/边界 | `os.makedirs(extract_to)` 无 `exist_ok=True`，`exists` 检查与 `makedirs` 之间存在 TOCTOU；目录穿越校验只针对普通成员路径，`extractall` 不校验符号链接成员——含 `link -> /etc` 再写 `link/xxx` 的压缩包（ffmpeg/node 安装包来自外部下载源）可越过 `extract_root` | 加 `exist_ok=True`；解压前遍历 `infolist()` 拒绝 `external_attr` 含 `S_IFLNK` 的成员 |
| M-52 | `src/config_io.py:410`（对照 `utils.py:838-844`） | 编码/数据丢失 | 备份读取用 `errors="replace"`，而 `main.text_encoding = "utf-8-sig"`。config.ini 被外部编辑器存成 GBK/UTF-16 时，读出内容被 U+FFFD 永久污染后写入副本，**从该备份恢复即得到损坏配置** | 改用 `errors="surrogateescape"` 与 `remove_duplicate_lines` 同口径；解码失败退化为 `copy2` 保字节 |
| M-53 | `src/config_io.py:404-406`、`:431` | 时间/命名 | ① `datetime.now()` 为 naive 本地时间，DST/时钟回拨会生成重复时间戳；② 精度只到秒，连续两次同文件备份必然同名覆盖；③ 旋转删除按 `getmtime` 排序，时间戳乱序时会**删掉最新的那份备份** | 用 UTC + 单调序号后缀；旋转排序改为解析文件名时间戳 |
| M-54 | `src/config_read.py:60-78`（对照 `:26-27`） | 逻辑 | 手写复刻 configparser 口径，未处理**缩进续行**：含 `:`/`=` 的续行被当成独立键 → 带 cookie/长值的配置被误报重复，而「每种形态只报一次」的额度（上限 32）被假告警耗尽，真重复反被淹没 | 先判 `raw_line[0] in " \t"` 即跳过；或直接用 `parser.read_string` 统计 |
| M-55 | `src/utils.py:157`、`:353` | 编码 | 两处 `decode("utf-8")` 未设 `errors`：① 签名脚本含非 UTF-8 字节 → `UnicodeDecodeError` 穿透，整条 JS 签名链失败；② node 在 GBK locale 下回显本地化错误信息时，解码异常取代真正的 `CalledProcessError`，故障归因丢失 | 改 `errors="replace"`；node 输出先按字节过 `mask_credentials` 再解码 |
| M-56 | `src/config_io.py:230` | 空值/边界 | `if file_path == main.url_config_file` 用字符串 `==` 比较路径，调用方传 `Path` 或分隔符/大小写不同的等价路径时恒为 False → `main.ini_URL_content` 快照不随删行推进，故障恢复时用**过期快照覆盖回退**配置 | 统一 `os.path.abspath(os.path.normpath(str(...)))` 后比较，Windows 再 `.casefold()` |
| M-57 | `src/utils.py:786-789`（对照 `config_io.py:269`、`main.py:4744`） | 安全 | `chmod 0o600` 只在 `utils.update_config` 一条路径执行；`main.py:4744` 首次创建 config.ini 与 `read_config_value:269` 的缺键补写都只经 `atomic_write_text`（首次即 0644）。含明文 cookie/密码的 config.ini 在多用户 POSIX 主机上对同机任意用户可读 | `atomic_write_text` 对「目标不存在」落 0600，或启动时统一 `_harden_permissions` |
| M-58 | `src/srt_writer.py:203`、`:158`；`src/ffmpeg_proc.py:159-164`；`src/room.py:82-96` | 健壮性/安全 | ① `_fp is None` 时条目被丢弃但序号已自增 → `.srt` 块号跳号，与 `:170-173` 注释承诺相反；② 生产路径用 `assert self._t0 is not None`，`python -O` 下失效；③ 三级终止兜底只关 `proc.stdout`，`stderr`/`stdin` 句柄只增不减；④ `room.py` 的 `httpx.get(url, follow_redirects=True)` 对调用方 URL 无 scheme/host/内网校验且完整缓冲响应体（URL 可由配置/Web 面板控制） | 序号自增移入成功分支；assert 改显式判空；兜底块依次关闭三个管道；`room.py` 走与异步侧同一内网判据并改用流式读取 |

### 5.7 Web 服务层（12 项）

| 编号 | 位置 | 类型 | 问题与影响 | 建议 |
|---|---|---|---|---|
| M-59 | `src/web_api.py:435-455`（配合 `:248-249`、`:681-690`、`web_config.py:76`） | 安全/可用性 | 登录限流的 per-IP 键在「本机反向代理」部署下可被绕过（`web_trusted_proxy` 命中后改由 XFF 推导，nginx 默认透传客户端自带 XFF）→ 攻击者每请求换一个键；而全局预算**不区分来源且成功登录也不回收**，持续打错即可让所有合法用户被 429 挡在门外。`web_trusted_proxy` 本身还可经 `PUT /api/config` 写入 | per-IP 改为 peer + XFF 双计数；全局预算与「该来源是否曾成功登录」解耦；把该键纳入敏感/需 reauth 清单 |
| M-60 | `src/web_api.py:127-129`、`:131`、`:1385-1388` | 资源 | ① 请求体 1MB 上限只按 `Content-Length` 判定（注释自认 chunked 传输不拦），`Transfer-Encoding: chunked` 时 `request.json()` 无上限物化进内存；② `deque(f, maxlen=lines)` 的 maxlen 只限制保留条数，整个 streamget.log（可达数百 MB）会被逐行读完，该同步端点可耗尽 anyio 线程池（默认 40）使**整个面板**无响应 | 改为按字节累加读取；日志尾读改为 seek 到文件尾反向读并设字节上限 |
| M-61 | `src/web_api.py:1066-1070`；`web_config.py:873-879`、`:1099-1104` | 安全/信息泄露 | ① `write_quality_options` 失败时 500 的 detail 直接拼了 `app.state.config_file` 绝对路径，违反本文件自述的 MID-39 不变量（认证关闭时对局域网可见），全文同类回显仅此 1 处；② `/api/config` 脱敏漏 `[推送配置]` 的邮箱登录账号、钉钉@手机号、tg 聊天 id、ntfy 邮箱，且 `_looks_like_secret_value` 只认带 scheme 的值，`user:pass@host` 裸 userinfo 不命中 | 改固定错误码，路径只进内部日志；节白名单补 `推送配置`；值形态检测去掉「必须以 scheme 开头」限制 |
| M-62 | `src/web_config.py:1249-1250`（经 `:1256-1260` 暴露给 `web_api.py:1063`、`:1300`） | 错误处理 | `append_config_line` 丢弃 `_atomic_write_text` 的返回值、无条件 `return True`，而 `update_config_line`（`:1212`）已按 M-29 修正。走补建分支时（config.ini 缺 `language` 键、画质选项首次写入）磁盘写失败仍报成功 → `set_language` 回滚不触发，出现「本进程已切语言、config.ini 仍是旧码」的双进程不同语言形态 | `return _atomic_write_text(...)`；补一条返回 False 的回归用例 |
| M-63 | `src/web_api.py:889-903`、`:908-912` | 边界 | 读取末字节失败时 `except OSError: pass`，`_needs_newline` 保持 False → 直接追加。MIN-2242 修复的正是「末行无换行会把新房间粘到上一行、两个房间同时坏掉」，而 Windows 上录制进程正持有 `URL_config.ini` 时 sharing violation 属常态，此回退让该修复在这类情况下整条失效 | OSError 分支保守地先补一个 `\n`，或追加失败后回读校验 |
| M-64 | `src/web_api.py:1078-1244`（判据 `:1093-1095`、`:1242`） | 安全/权限 | `PUT /api/config` 对 section/key **无白名单**，只有 1 项黑名单 `_DANGEROUS_CONFIG_KEYS`（`自定义脚本执行命令`）。可写面包含 `是否录制完成后执行自定义脚本`（翻转 true 即启用用户既有脚本命令 = 黑名单被旁路一半）、`web_trusted_proxy`、`web_allowed_hosts` 等安全判定相关键 | 对 [Web] 节与安全相关键改白名单；至少把脚本开关与脚本命令一并列入危险键 |
| M-65 | `src/web_api.py:781-808`（端点）、`:658`（中间件） | 资源 | `/api/status/stream` 无并发上限、无空闲超时，`event_gen` 仅靠 `request.is_disconnected()` 退出，而它挂在 `BaseHTTPMiddleware` 之下（Starlette 在流式响应路径上 `http.disconnect` 透传历来不可靠）→ 协程与连接永不回收，可被低成本累积 | 加空闲超时与每 IP SSE 并发上限；鉴权逻辑移出 `BaseHTTPMiddleware` 改纯 ASGI 中间件 |
| M-66 | `src/web_api.py:1564-1567`、`:1495-1498`（配合 `:1466-1469`） | 安全/并发 | ① 非幂等请求在 **Origin 缺失时无条件放行**，任何非浏览器客户端可零成本驱动全部写接口；`is_origin_allowed` 里 Starlette TestClient 的哨兵 `testserver` 豁免在生产判定中同样生效（测试后门进生产）。② 单飞门的租约令牌 `fetch_since` 在**释放锁之后**才从全局读回，租约到期后两个在飞采样会读到同一个值 → 门被提前打开 | 写接口要求 `Origin` 与 `Host` 双在且一致；哨兵豁免改为仅在 pytest 环境注入；令牌在同一临界区内取出并传出 |
| M-67 | `src/web_api.py:264-281`（对照 `:366-378`）、`:1378` | 资源/响应头 | ① `_PUBLIC_BUDGET` 键集合无上限（只在最后一条超窗口时回收），持有 IPv6 的攻击者轮换源地址即可让键集合无界增长——同文件 `_DENIED_HOSTS_SEEN` 已做 64 条上限，此处漏了同一类防护；② `FileResponse(filename=os.path.basename(target))` 把磁盘文件名直接交给 Content-Disposition 且项目侧未净化（Windows 文件名规则恰好排除了引号与 CRLF 故本机不可利用，跨平台部署取决于 Starlette 实现） | 加键数上限；自行剥除 CR/LF/引号与控制字符，非 ASCII 只输出 RFC 5987 的 `filename*` 形式 |
| M-68 | `src/web_config.py:1178`、`:1204-1205`、`:1213` | 逻辑/死代码 | 行级替换只改目标节内**首个**匹配行，手工编辑产生重复键时写侧返回 True 而生效值来自另一行（「面板提示已保存、行为未变」）；`:1213` 的 `return True` 永不可达 | 匹配行数 >1 时拒绝写入并给出可行动文案；删除不可达 return |
| M-69 | `src/web_tray.py:235-239`、`:451-461`；`web.py:421-451` | 生命周期 | ① `start()` 在托盘不可用时返回 False，但此前已构造 `QApplication` 并置 `_owns_app=True` → 留下永不运行的 QApplication；`_on_exit` 在无 server 时直接 `os._exit(0)`，跳过所有 finally 清理。② `web.py` finally 链同步调用 `_shutdown_postprocess_executor()`（单个转封装任务上限 3600s）且无超时保护 → 「点了退出后卡死」 | 降级返回前复位状态；无 server 时走正常退出路径；给后处理收尾包一层超时 |
| M-70 | `web.py:151-165`、`:41-42`、`:107-108`、`:209-210` 等 6 处 | 数据丢失/可观测性 | ① `_cap_web_console_log` 先 `truncate()` 再 `write(tail)`，两步之间崩溃/断电/强杀即**整份** `web_console.log`（2MB 历史排障记录）全部丢失；② 6 处 `except Exception: pass` 完全静默，其中 `:209-210` 失败意味着后续 DEBUG/WARNING 写进被隐藏的控制台而文件里只剩 print | 改临时文件 + `os.replace()` 原子替换；静默 except 至少降级为 debug/一次性 warning |

### 5.8 桌面 GUI 与 UI 组件（13 项）

| 编号 | 位置 | 类型 | 问题与影响 | 建议 |
|---|---|---|---|---|
| M-71 | `gui.py:3741`、`:3781-3782` | 逻辑错误 | 输出线程只在 `len(batch)>=10` 或 EOF 时 `flush_batch()`，无任何超时/空闲刷新。录制核心稳定期每 120s 才输出一行状态行，攒满 10 行需约 20 分钟 → 期间日志页长时间空白，用户误判「录制已卡死」。这是正常运行路径必然出现的功能失效 | 按时间兜底刷新（距上次 flush 超过 0.5~1s 即入队） |
| M-72 | `gui.py:4671-4720`、`:4685`、`:4700`（对照 `:379-420`） | 安全/数据破坏 | 退出兜底对已捕获的 PID 无条件 `taskkill /F /T`（强杀整棵进程树）。两道复用防护可同时失效：源码运行态下 `_child_image_name` 恒为 `python.exe`，映像名判据结构性失效；`_win_pid_creation_stamp` 在权限不足/进程已不存在时返回 `None`，`_reused_pid_same_image`（`:417-418`）**返回 False 即放行**。子进程退出后 PID 进入复用池，误杀的是无关进程及其整棵子树 | 判据取不到时按「无法判定 → 不杀」处理（清理宁可漏清也不可误杀）；或改用 Job Object 绑定子进程树 |
| M-73 | `gui.py:3897-3924` | 错误处理 | `_drain_log_queue` 先渲染 messages 再处理 `process_ended` 哨兵，两段无 try/finally 隔离。渲染抛异常时哨兵已被取出但 `_process_ended` 永不执行，且异常被上层吞掉 → 开始/停止按钮与状态灯**永久停在「录制中」** | 哨兵处理放进 `finally`，或先转存为实例字段再渲染 |
| M-74 | `gui.py:2359-2379`（配合 `:1933`、`:1949`、`:1970`） | 逻辑错误 | 语言切换只做了 `retranslate_all()` 与字体/画质/弹幕刷新，未重建主题、缩放、动效三个下拉的 `values` 与 `_theme_ids_by_display` 等反查表（在 `_build_sidebar` 里按构建时语言一次生成）。切换后下拉项仍是旧语言，反查表键对不上会**静默落到默认项**（用户选「深色」实际被改成「跟随系统」） | 抽 `_rebuild_preference_menus()` 统一重建显示名与反查表 |
| M-75 | `gui.py:3351`、`:3523-3524`（对照 `:1826`）；`src/gui_qt/recorder.py:396-397` → `main_window.py:784-788`（对照 `shared.py:363`） | 安全 | 绝对路径（下载目录、录制核心路径、工作目录）未经 `mask_credentials` 直接写 `logs/gui.log`（同文件 `:1826` 对字体路径已脱敏，属同红线下的遗漏）；Qt 侧子进程 stdout 剥离 ANSI 后**原样**入日志页并落盘，录制输出会回显直播间 URL、平台签名参数、请求头，而全仓唯一的脱敏口径只用在 taskkill/pkill 提示上 | 三处 `path=` 一律包 `mask_credentials`；Qt 侧在 `clean_line` 生成处或落盘前统一过脱敏 |
| M-76 | `gui.py:4077`（对照 `:1184-1187`、`:48-52`）、`:928-933`、`:3220-3222` | 逻辑/边界 | ① `now - cast(float, info.get("last_seen", 0))` 未走本文件自定的容错口径 `_as_float`，脏值抛 TypeError 使当轮画质表整体停在旧值（同文件另两处都用了容错助手，此处是唯一漏网）；② `_editor_content()` 异常时返回基线（等于「按无改动处理」）→ 静默覆盖用户编辑；③ `_load_config` 早退分支跳过 `_mark_config_saved()` → 反复弹「有未保存更改」 | 改用 `_as_float`；异常时返回哨兵走 conflict 分支；早退分支同样调用 `_mark_config_saved()` |
| M-77 | `gui.py:1850-1858`、`:1762`、`:2249`、`:2356`、`:4849` | 潜在缺陷/资源 | ① `_settled_reqwidth` 通过 `self.root.update()` 递归进入 Tk 事件循环，窗口构建中途重入可能作用于半初始化组件；② 两处 `after` id 未保存，窗口销毁后回调仍触发，抛 TclError 后（窗口化下 stderr 为 None）完全静默 | 改 `update_idletasks()` 或多次采样；保存 after id 并在退出时 `after_cancel` |
| M-78 | `src/gui_qt/main_window.py:528-538`（唯一 `retranslate_all()` 在 `:505`） | 逻辑错误 | `_apply_language_preference()` 只调 `set_language` + `_repopulate_static_texts()`，**从未调用 `retranslate_all()`**，而 `set_text()` 是「注册 + 建时渲染」语义、`_build_ui()` 在切语言之前执行。config.ini 里 language 非 zh_CN 的用户每次启动后整窗静态文案停在 zh_CN，直到手动拨一次语言下拉才纠正；`:529` 的注释「启动期只做这一次全量重译」与实现不符 | 在 `set_language` 之后、`_repopulate_static_texts()` 之前补一次 `retranslate_all()` |
| M-79 | `src/gui_qt/recorder.py:345-353`、`:320-323`、`:384-395` | 逻辑/资源/错误处理 | ① `_shutdown_worker_body` 读 `self._process` 取 pid，若停止线程已先 `_clear_process()` 则 `child_pid=None`，`cleanup_process_tree(None)` 直接返回 → **退出路径的 ffmpeg 整树清理被静默跳过**，孤儿 ffmpeg 继续录制；② `proc is None` 分支不 emit `ended`，而 `:335-343` 的注释明确要求异常路径必须走同一出口 → UI 永久卡死（只能重启 GUI）；③ `readline()` 空但进程未退出时 20Hz 忙轮询且无上限 | 停止时把 pid 落到独立字段，退出清理优先取该字段；异常分支补 `_clear_process()` + `ended.emit()`；给忙轮询加累计等待上限后退化 `proc.wait()` |
| M-80 | `src/gui_qt/app.py:44`（配合 `:15-31`）；`main_window.py:410-422`（对照 `:568-581`）、`:759-763`、`:841-843` | 错误处理/逻辑/资源 | ① 只设 `sys.excepthook` 未设 `threading.excepthook`，四条 daemon 线程的未捕获异常在 pythonw（stderr 为 None）下被静默吞掉——正是文件头要防的「无窗口、无报错」；`_crash_sink` 在任意线程构造 `QMessageBox` 违反 Qt 线程亲和性。② 主题/缩放从 config 读出后只算 `self._palette`，从不回填下拉 `currentIndex`，重启后「界面是深色、下拉显示跟随系统」，`toggle_theme` 会与下拉错位。③ `_log_timer` 只启不停，首条日志后 200ms 定时器以 5Hz 空转到进程结束 | 补 `threading.excepthook`，弹窗经信号投回主线程；参照 `_refresh_font_menu_values()` 回填两个下拉；队列空时 `stop()` 恢复「按需激活」语义 |
| M-81 | `src/gui_qt/widgets.py:358-363`（对照 `pages/danmaku.py:295-297`）；`tray.py:26-30`、`:92`（配合 `main_window.py:1112-1115`） | 逻辑/资源 | ① `append_line` 用 `textCursor()` 的**副本** `insertText` 后不 `setTextCursor(cursor)`，Qt 视口跟随的是控件自身光标 → 日志页不自动滚到最新行（同仓弹幕页已写「光标移到末尾」的口径，两条路径不一致）。② `TrayIcon` 把主题字典引用存进 `self._tokens` 后不再更新，`apply_palette` 无托盘重着色出口 → 切主题后托盘图标色与侧栏不一致；托盘不可用时构造出的对象以主窗口为父常驻（含 QSystemTrayIcon + QMenu + 5 个 QAction），是每次启动的固定残留 | 插入后 `setTextCursor(cursor)`；加 `apply_palette()` 更新并重绘；不可用分支 `deleteLater()` |
| M-82 | `src/ui_motion.py:207-214`、`:244-257`（配合 `:176-181`、`:216-218`）；`src/ui_i18n.py:56` | 潜在缺陷/逻辑 | ① `cancel()`/`cancel_all()` **全类没有一处 `root.after_cancel()`**，`_step` 内也没有「本链是否仍有效」的守卫 → 切到 `off`、切页面、销毁窗口后旧链继续逐帧写 place/geometry，表现为动效叠加抖动、关掉动效后控件仍被拉回位移；注释提到的 `disable()` 在类中并不存在。② `ui_i18n.register()` 的去重写成 `entry[0] is ref`，而每次都新建 `weakref` 对象，`is` 恒不成立 → 登记表无界增长，`retranslate_all` 对同一控件重复回填 N 次 | 保存 after id 并真正 `after_cancel`；`_step` 首行校验 job id；去重改 `entry[0] == ref` |
| M-83 | `src/ui_fonts.py:189`、`:205-216`（配合 `:357`）；`src/ui_kit.py:306-315`、`:133-137`、`:570-578` | 异常处理/边界 | ① `sfnt_family_name` 只 try 住 `read_bytes`，`_find_table`/`_iter_table_dirs` 对 ttc 容器内偏移无长度校验，损坏/恶意构造的 `.ttf/.ttc` 抛 `struct.error` 一路冒泡到「导入字体」回调（回调也未包 try），表现为点一次没反应；② `blend()` 不校验颜色形态与 `ratio` 范围，越界会产出 8+ 字符的非法颜色串使 `tag_configure` 静默失败；③ `sync()` 直接 `values[key]`（不一致即 KeyError 中断整表同步），同一行「值变化 + 标记变化」时 `changed` 追加两次 | 解析段统一 try 并返回 `None`；复用 `ui_theme.is_valid_hex` 并夹取通道值；改 `values.get(key, ())` 与集合去重 |

### 5.9 前端、自研 JS 与 VBScript（5 项）

| 编号 | 位置 | 类型 | 问题与影响 | 建议 |
|---|---|---|---|---|
| M-84 | `web/app.js:28-36`、`:150-165` | 安全 | `_tokenStore()` 在 sessionStorage 不可用时回退 **localStorage**，bearer token（默认 24h 有效）以明文落盘并跨标签页/浏览器重启存活，关闭标签页不再失效，与 `:150-152`「关标签页即失效」的设计目标相反。XSS、恶意扩展、本机其他进程读取磁盘均可窃取 | 回退改为内存变量 + 一次性提示，或回退时强制缩短服务端 token 有效期 |
| M-85 | `StopRecording.vbs:355-357`、`:129`、`:401-411` | 安全/数据破坏 | 目录锚点 `InStr(1, s, LCase(appDir))` 是裸子串匹配，仅用 `Len(appDir) > 3` 兜底。脚本放在 `D:\dlr`、`D:\a1` 这类短目录时，`D:\dlr-backup\...`、`D:\dlrx\...` 下**其他程序**的 ffmpeg 也会被判为「锚定本程序」而 `taskkill /f` 强杀，与本文件头「宁可漏杀，不可误杀」的口径冲突；阶段 1 已用 `/t` 连带杀掉子 ffmpeg，3 秒后对可能已被连带结束的 PID 回退 `taskkill /f /pid`，期间该 PID 可能已被系统分配给无关进程 | 匹配前给 appDir 补尾部 `\` 并要求命中后下一字符为分隔符/空格/引号/串尾；回退前用 WMI 按 PID 复核 `Name='ffmpeg.exe'` 且路径仍锚定本程序 |
| M-86 | `src/javascript/liveme.js:317`、`:332`、`:376`、`:413`、`:422`、`:348`、`:374`、`:384`、`:388`、`:419`、`:421` | 代码质量/信息泄露 | 5 处未声明赋值泄漏到全局作用域（模块被 `'use strict'` 或 ESM 化即抛 ReferenceError，并发复用时互相污染）；6 处 `console.log` 保留在生产签名链里，逐次调用打印 `sKey`、`data_e`、`signParams` 与最终签名（其中还有 ANSI 彩色转义），既把签名中间态写进调用方捕获的 stdout/日志，也可能污染 `utils.run_js_async` 经 execjs 取回的产物解析 | 一律加 `const`/`let`；删除调试输出或改由环境变量控制的 debug 开关写 stderr |
| M-87 | `src/javascript/x-bogus.js:375-376`；`liveme.js:7`、`:315`、`:349` | 安全/潜在缺陷 | ① 用动态求值（`eval`）加载 `require('crypto')` 与 `require('buffer')['Buffer']`——参数是字面量暂无注入面，但属本仓明令消减的面（`haixiu.js:5-8` 已因同类理由摘除 4 处），且是静态扫描的明确红点；② `const r = ${Date.now()}${id}` 与 `const s = Rm(r)` 在**模块加载期**求值，进程长驻复用时时间戳恒为加载时刻、与实际 `_time` 偏离并触发平台侧时效性失败；`require(cryptoJSPath)` 直接 require 外部传入路径 | 改直接 `require`；把 `r`/`s` 移入 `sign()` 内现算；对 cryptoJSPath 做白名单/规范化校验 |
| M-88 | `web/app.js:1787-1816`、`:1378`、`:1391`、`:1403`、`:1815`、`:1842`、`:852-858` | 健壮性/可维护性 | ① `downloadFile` 直接 `fetch` 未加 `AbortController` + 超时（同文件 `api()` 已有 10s 封装），大文件或后端挂起时请求无限 pending；② 5 处拼 `e.message` 未做空值兜底（`e` 非 Error 时显示 `undefined`），同文件另有 4 处已写 `(e.message \|\| '')`，两套口径并存；③ `markBackendUnreachable(flag)` 只有 `if (flag)` 一个分支，形参的 false 语义不存在，后端恢复后「已断开」只能等下一轮覆盖 | 复用 `api()` 的超时封装；统一 `(e.message \|\| '')`；补 `else` 恢复分支或去掉形参 |

### 5.10 脚本、构建与打包（11 项）

| 编号 | 位置 | 类型 | 问题与影响 | 建议 |
|---|---|---|---|---|
| M-89 | `scripts/douyin_live_recorder_standalone.py:1885-1912`（对照 `src/ffmpeg_proc.py:100-135`） | 逻辑/数据丢失 | M-16 回灌不完整：`terminate_all_ffmpeg` 写 `b"q"` + `close()` 后**立即** `proc.terminate()`，中间没有任何等待；而 `_stage_budget` 分段等待（约 10s）这一级只存在于主线。Windows 下 `terminate()` 即 TerminateProcess 硬杀，「写 q 优雅收尾补写 moov」一级实际从未生效 → 停止录制时 mp4/mov 缺 moov、产物不可播放，与其自身注释声明的语义相反 | 写 q 后按预算 `proc.wait(timeout=…)` 再进入 terminate/kill 两级，与主线同形 |
| M-90 | `scripts/douyin_live_recorder_standalone.py:1448-1451`、`:2495-2527` | 假绿 | selftest 只换绑 `http_probe` 与 `_throttle_probe`，而 HLS 分支最终调用的是**真实** `http_request`（`:1449`）：`validate_stream_url` 走 Range-GET=206 后进入 `_probe_hls_segment_lite` → 对 `https://cdn.example/...` 发出真实网络请求（两轮用例各一次），直接违反文件头「离线自检、绝不发真实请求」的契约；且该请求被 `except Exception: return True` 吞掉，离线环境下自检仍打印 PASS | selftest 内同时换绑 `http_request`；该 except 在自检模式下改为显式 FAIL |
| M-91 | `scripts/check_coverage.py:142-146`、`:150-153`（对照文件头 MIN-19） | 假绿 | `_data_is_stale` 里 `data_file.stat()` 抛 OSError 返回 None、源码 `stat()` 失败 `continue`，两条都静默按「数据不陈旧」处理，与文件头「没查到一律非 0」的 fail-closed 口径相反；陈旧数据会让逐模块读数评的是已不存在的代码且照常 PASSED | stat 失败一律 `sys.exit(2)` 并给出重跑命令 |
| M-92 | `scripts/check_runtime_pins.py:277-287`；`scripts/sync_version.py:34`、`:74-105`；`scripts/report_bundle_size.py:207-214`；`scripts/check_annotations.py:489-505` | 假绿/判定面 | 4 处「导出/比对通道」不做与检查通道相同的结构校验：`emit_env()` 只校验属性存在就打印并 return 0（下游 `build_exe` 仍 fail-closed，故为纵深缺口而非直接绕过）；`sync_version` 的 `SYNC_TARGETS` 为空时 `--check` 循环零次、恒 OK 退 0；`--compare` 基线缺失只追加 `[warn]` 不影响退出码；`check_equivalence` 只遍历基线目录，**快照后新增的文件完全不参与比对** | 各通道复用 `check()` 的结构校验；空判定面退 2；比对范围改为两目录并集 |
| M-93 | `scripts/check_runtime_pins.py:76`；`check_version.py:34`、`:60`、`:123`；`check_coverage.py:505-506`；`check_annotations.py:349` | 错误处理 | 5 处门禁自身的 I/O/加载异常没有兜底（`exec_module(build_exe)`、`read_text()`、`float(cast(...))`、遍历读取等）→ 进程以 rc=1 + Traceback 结束。而 rc=1 在 CI 语义里是「代码不合格/发布链查出了问题」，真相是「门禁自己没查」，与文件头 rc=2 分级契约冲突，排障方向整体错掉 | 统一包 `try/except (OSError, ValueError, TypeError, ImportError)` → 打印「门禁自身失效」并 `sys.exit(2)` |
| M-94 | `scripts/run_gates.py:272-282`、`:375-383`；`scripts/sync_metadata.py:95-97`（对照 `check_coverage.py:282`） | 资源/健壮性 | 3 处子进程均无 `timeout`：主回路 `Popen`（mypy/black 卡住则 run_gates 永久阻塞到 job 超时）、`_module_unavailable` 的 `subprocess.run`（且未 `capture_output`，子进程输出混进门禁 stdout 污染结论）、`_run` 的 `subprocess.call`（`uv lock` 联网挂起） | 统一加 `timeout=` 与 `capture_output=True`，超时按 rc=2/3「门禁没跑成」处理 |
| M-95 | `scripts/agent_hook_guard.py:71-75`（`_DELETE_VERB_RE`）、`:259` | 安全 | 删除判定只认动词白名单，`xargs rm`、`git checkout -- .`、`git restore`、重定向截断 `> file`、`mv`、`truncate`、Python 侧发起的删除等日常形态零命中 → 守卫可被最普通的写法绕过（上一轮 S-01 的引号/尾随空格形态已修，动词覆盖面仍是同族缺口）；另排除式上下文只回看 match 前 60 字符，长命令行里 `-Exclude`/`-notmatch` 落在窗口外即被误判成删除目标 | 动词表增补 `xargs`/`checkout`/`restore`/`mv`/`truncate`/`>`；排除式段落定位改为整条 statement 先行定位 |
| M-96 | `scripts/spike_arm64_static_ffmpeg.sh:41`、`:157`、`:196`、`:212`、`:218`；`scripts/_ci_web_smoke.sh:17`、`:42` | 安全/健壮性 | ① `RELEASE_INDEX` 可由环境变量整体改指向，索引页、`.sha256/.sha512` 摘要、tarball 三者**同源取自该站点**，「校验」是自己验自己；`tar -xf` 未限制解压路径。② `_ci_web_smoke.sh` 只 `set -uo pipefail` 缺 `set -e`，中间步骤失败被静默吞掉；`pkill -f 'python web\.py'` 按命令行子串匹配，runner 上任何同名进程都会被无差别杀掉 | 摘要端点与 tarball 分源取；`tar` 加 `--no-same-owner` 并先校验顶层目录名；补 `set -e`；`pkill` 限定为本轮子树或 pid 文件 |
| M-97 | `scripts/smoke_test.py:365-419` | 安全 | `write_html_report` 把 `name/url/errors/detail` 原样拼进 HTML（`:372-384`），`errors` 含异常文本与 HTTP 响应派生内容。报告作为 CI 工件被浏览器打开时可造成 HTML/脚本注入；文件头「依赖配置可信」的假设对响应派生内容不成立 | 输出前 `html.escape()` 所有动态片段 |
| M-98 | `build_exe.py:1936-1938`、`:1942`、`:1929-1963` | 安全 | 打包冒烟向子进程注入 `DOUYIN_WEB_ALLOW_INSECURE=1`，使 Web 面板以**无认证 + 绑定 0.0.0.0** 运行最长 90s。注释称「从不真正暴露到局域网」与事实不符——绑定 0.0.0.0 即对所有网卡可达；自建/长期存活的 CI runner 上，这 90 秒窗口内任何人可读写全部配置、遍历 downloads、启停录制 | 探活完成后立即收尾；或改用 `web_host=127.0.0.1` 的配置覆盖跑冒烟 |
| M-99 | `build_exe.py:379`、`:398-401`、`:417-422`、`:1575`、`:1578-1580`、`:1335-1336`、`:854-859`、`:1140` | 安全/产物污染/健壮性 | ① 脱敏与断言只认 `CREDENTIAL_FILE_NAMES` 里硬编码的两个文件名，`config/` 下其它文件被原样复制且从不进入扫描范围（注释 `:378-379` 自陈此缺口），`:399` 的 `not item.is_file()` 还会静默跳过所有子目录；② ffmpeg/node 临时归档与解压目录建在 `RELEASE_DIR` 内且只在**成功路径**清理，失败后残留会被 `_zip_release_dir` 整包打进对外 zip；③ `_verify_gpg_artifact` 只捕 `OSError`，条目漏配 `sig_url` 时 `urlopen("")` 抛 `ValueError` 穿透并以未处理异常中断整个构建 | 改为「复制即判定」并递归处理子目录；清理移入 `finally` 或打包前增加残留断言；扩大异常捕获并在空 URL 时显式返回 |

### 5.11 测试有效性（5 项）

| 编号 | 位置 | 类型 | 问题与影响 | 建议 |
|---|---|---|---|---|
| M-100 | `src/spider.py`（`coverage.json` 读数） | 覆盖盲区 | `src/spider.py` **3577 语句 / 856 行未覆盖（76.1%）**，是全仓最大绝对缺口，集中在各平台取流主链路：`get_popkontv_stream_data`(59)、`get_shopee_stream_url`(57)、`get_pandatv_stream_data`(37)、`get_douyin_web_stream_data`(36)、`get_showroom_stream_data`(35)、`get_douyin_app_stream_data`(31)。这些是「取流失败即漏录」的核心路径，改坏字段解析或 URL 拼装不会被任何用例拦下 | 按平台补「离线契约」用例（喂固定 HTML/JSON 替身，断言 `is_live`/`m3u8_url`/`record_url`），至少覆盖每个 `get_*_stream_url/data` 的成功与 `{is_live:False}` 两分支 |
| M-101 | `src/` 全量（461 个 `except` 分支） | 覆盖盲区 | 461 个 except 分支中 **46 个的分支体首行未覆盖**（约 10%），集中点 `src/gui_qt/main_window.py` 6/17、`src/utils.py` 5/26、`src/ui_kit.py` 5/12、`src/ui_fonts.py` 4/10；`src/gui_qt/pages/danmaku.py`、`src/gui_qt/app.py` 两个文件的异常分支**完全未覆盖**（2/2）。这些多是「降级/兜底」路径，恰是最易回归且最难受监控的一类 | 按文件补「注入异常 → 断言降级结果」用例；对 2/2 全未覆盖的两个文件至少补 1 条冒烟 + 1 条异常路径 |
| M-102 | `src/gui_qt/pages/runlog.py`、`src/gui_qt/quality_monitor.py` 等 9 个模块 | 覆盖盲区 | 69 个 src 模块中 2 个被 **0 个测试文件引用**；另有 7 个仅 1 个测试文件引用（`platforms/_xbogus.py`、`web_models.py`、`startup_cleanup.py` 等）。新增 GUI 页面可零测试入库而不触发任何红灯，而逐模块覆盖闸依赖 `coverage.json`、该文件一旦陈旧即失效 | 补导入级/构造级冒烟用例；`_xbogus.py`（抖音签名算法）仅 1 处引用应优先补字段级断言 |
| M-103 | `tests/conftest.py:19`、`test_bili_live_collector.py:47`、`test_douyin_live_collector.py:84`、`test_douyu_live_collector.py:52`、`test_huya_live_collector.py:48` | 污染/共享状态 | 5 个真机双模脚本共用会话级共享目录 `tests/_out_live`（conftest 仅在 `pytest_unconfigure` 时 rmtree），清理靠「按文件名前缀删」的约定。一旦有人写了不带约定前缀的产物，或启用 `pytest-xdist`/并行会话，就会出现「文件存在但内容来自上一轮」的假绿，以及收尾 rmtree 删除他人产物的互删 | 改用 `tmp_path` 或带平台唯一前缀的子目录；清理前增加「仅删本次会话创建的文件」白名单校验 |
| M-104 | `tests/` 跨文件 73 组 / 161 处 / 约 1610 行（代表 `test_exception_log_masking.py:26`、`test_outbound_read_caps.py:33`、`test_pep758_except_form.py:19`） | 可维护性 | 跨文件重复代码块 73 组（≥10 行连续、归一化后完全一致），同文件内另有 31 组。三处各自定义了同一个 `_EXCLUDED_PARTS` 目录名单，`_PROXY_ENV_KEYS` 抄了三遍，虎牙流样本重复三处。名单类常量一旦漏改一处，就会出现「某文件被豁免扫描」的静默漏检 | 抽到 `tests/_fixtures.py` 或 conftest 的共享常量模块；数据样本抽到 `tests/golden/`（已有 `start_record_commands.json` 先例） |

---

## 6. 轻微问题（10 类，合并覆盖约 150 处）

> 同类问题在本节按类别合并，每类给出出现规模与代表性位置；逐处修复时以类为单位推进，可显著降低回归风险。

| 编号 | 类别 | 代表性位置（出现规模） | 问题与影响 | 建议 |
|---|---|---|---|---|
| L-01 | 死代码与不可达分支 | `gui.py:465-489`（`Colors` 中 20 个常量零引用）、`:813/921/986/1028`（`_disk_mtime` 四处赋值零读取）；`src/video_postprocess.py:59/161/280/349`（`pre_existed` 恒为 False、`out_path=""` 无引用）；`src/web_config.py:1213`（不可达 `return True`）；`src/proxy.py:57-84`（`proxy_url`/`user`/`password` 生产零消费点）；`src/ttwid.py:51/87/202`（`_cached_ttwid_at` 写而不读）；`src/spider.py:462-467`（`_is_safe_http_url` 仅测试引用）；`src/javascript/x-bogus.js:458-485`（`_0xb55f3e` 未引用、`debug` 空实现）；`web/app.js:852-858`（形参 false 语义不存在）；`src/gui_qt/recorder.py:412`、`main_window.py:1198`、`settings_dialog.py:115`、`pages/config.py:39`、`pages/danmaku.py:301`（6 处遗留赋值/空语句/重复 import） | 约 30 处。维护「永不消费」的状态会让后来者误以为存在某条判据（如 `_disk_mtime` 暗示存在 mtime 裁决、`proxy_url` 暗示认证代理已接通），并制造第二份事实源 | 逐类删除；确需保留的在注释中标明唯一用途 |
| L-02 | 重复代码与孪生副本 | `gui.py:2085/2157/2220/2294/2340`（异常日志模板 5+ 处）；`src/utils.py:426-495`（sync/async 两支护卫逐字重复 4 段）；`src/ui_theme.py:416-438/440-462/538-557`（三处 `map` 块同构 + 魔法数 0.18 共 6 处）；`src/ffmpeg_install.py:219/122` vs `ffmpeg_master_download.py:169/292` vs linux 侧（三处孪生副本，仅一处有等价性回归锁）；`src/gui_qt/main_window.py:934-961/963-1001` vs `settings_dialog.py:141-155/157-187`（配置冲突裁决双份，文案与基线刷新顺序已开始漂移）；`src/javascript/haixiu.js:32-479`（13 个函数近逐字重复且返回值口径不一致）；`src/spider.py:19/66 处`（见 M-19）；`src/stream_select.py:716-725` 等 6 处末位放行块 | 约 10 组 / 数百行。「改一处漏 N 处」在本仓已多次造成事故（历史提交 M-23、L-32 均手工改两遍） | 抽出公共 helper / 下沉到无环底层模块；为孪生副本补等价性回归测试 |
| L-03 | 硬编码文案与 i18n 不一致 | `gui.py:3311-3314`（`f"ts → {save_fmt}"` 硬编码且 `ts` 自指）；`src/gui_qt/recorder.py`、`danmaku_monitor.py`、`quality_monitor.py` 共 15+ 条用户可见日志硬编码中文（同包 `pages/*` 已全量走 `tr`）；`src/notify.py:234`（把 Python 常量名 `_SCRIPT_TIMEOUT_SECONDS` 当 i18n 占位符名写进 msgid，改常量名即静默打断翻译）；`i18n.py:229-234`（切语言失败时告警用切换前的语言打印） | 约 25 处。切到英文界面后运行日志仍是中文；msgid 里出现内部标识符；告警语言与目标语言不一致 | 统一改 `tr()` 并给占位符起语义名；告警改为在语言确定后补发 |
| L-04 | 编码、空值与边界健壮性 | `src/utils.py:42-45`（`is_safe_http_url` 只校 scheme 不校 netloc，`http://` 被判合法）；`src/stream.py:424-430`（`int(quality_str[0])` 只取首字符，`"10"` 被当成 1）；`src/spider.py:579/571/573`（`replace("\\","")` 破坏合法转义、两条正则缺 `re.DOTALL`）；`src/platforms/huya.py:168`、`bilibili.py:369`（颜色整数未钳制，`color<0` 产出 `#-00005`）；`src/platforms/huya.py:77/81-82`、`bilibili.py:174/178`（进房参数 `int()` 前只判真值，非数字串抛 ValueError 致「已连接 / 0 弹幕」）；`src/platforms/twitch.py:35/114-116`（`_line_buf` 无上限且 `start()` 不重置，异常流下内存无界 + 跨轮污染）；`src/ws_client.py` 相关 `start()`（5 处 `new WsClient` 前未关闭上一实例） | 约 14 处。多为「特定输入下静默失败或崩溃」，单条影响有限，但叠加后是「在播却不录」的主要来源之一 | 逐条补显式校验与钳制；`start()` 内先 `await close()` |
| L-05 | 命名与魔法数 | `src/stream.py:604`（`json.JSONDecodeError` 是 `ValueError` 子类，冗余成员）；`src/ui_theme.py`（0.18 裸写 6 处）；`src/gui_qt/main_window.py:401/557`（页标题由导航按钮文本 `split("  ")[-1]` 派生，把业务字段耦合到译文排版）；`src/platforms/_tars.py:52 vs 66-67`（扩展 tag 越界在 peek 路径与 take 路径口径不一致）；`src/spider.py:1361`、`3791-3796`（循环体内定义闭包、函数内 6 条 import） | 约 8 处。可读性风险与潜在口径漂移 | 提为具名常量；闭包与 import 提到外层 |
| L-06 | 平台协议与二进制解析 | `src/platforms/_tars.py:59-68`、`:81`、`:161-175`（文件头 CR-03 声明「一切长度都经 `_need` 消费」，实际 `_take_head`/`_skip` STRING1/`read_int` 三处无 `_need`，截断帧抛 `IndexError`/`struct.error` 而非统一 `ValueError`，被上层压成一条 debug）；`src/platforms/douyin.py:41/45-46/185-190`（凭据作废基于异常文本正则而后果是进程级 `invalidate_ttwid()`，误判代价由全部房间承担，无节流）；`src/platforms/bilibili.py:89 vs 55-56/146`（`start()` 只重置 `_close_reported`，`_session_ok`/`_auth_ok` 未重置 → 二次 start 时 host 轮换失效）；`src/platforms/bilibili.py:259-260/329`、`douyin.py:235`（畸形帧 `break`/`return` 完全静默，无日志线索）；`src/platforms/_xbogus.py:74-75/64/132`（签名 salt 用非密码学 `random` 且明文发出）、`:71-72/63`（`ms_stub` 只校长度不校 hex） | 约 10 处。协议健壮性与「静默无日志」是排障成本的主要来源 | 统一 `_need` 校验；作废加节流与 debug 留痕；补齐状态重置；salt 改用 `secrets` |
| L-07 | proto 定义 | `src/proto/douyin.proto:361`（`EpisodeChatMessage.common` 声明为 `Message`，其余消息均为 `Common`）；`:514-516`、`:535-552`（`message kk`、`message Rsp` 为联调残留，会被编译进 `douyin_pb2`）；`:258/312/364/264`（`defaultPatter`、`useRemoteClor`、`visibleToSende` 拼写错误；`TextPiece.type` 用 `bool` 承载应为枚举的类型标识） | 6 处。拼写错误改正会改变生成属性名，需同步改调用点 | 修正类型与拼写（连带改调用点）；删除调试残留 |
| L-08 | 前端、VBScript 与脚本小项 | `web/app.js:1787`（`downloadFile` 无超时，见 M-88）；`src/javascript/liveme.js:7/315/349`（加载期求值，见 M-87）；`scripts/report_bundle_size.py:207-214`、`scripts/check_annotations.py:489-505`（判定面缺口，见 M-92）；`scripts/spike_arm64_static_ffmpeg.sh`（无 `set -e` 类问题，见 M-96）；`src/ffmpeg_proc.py:159-164`（fd 兜底，见 M-58）；`src/srt_writer.py:203/158`（见 M-58） | 已在对应中等条目中说明，此处不重复计分 | 随对应条目一并整改 |
| L-09 | 测试可维护性 | `tests/` 37 个测试函数名跨文件重名共 108 处（`test_not_live` 一个名字出现 26 次）；90 个测试文件用 `read_text()`/`ast.parse`/`inspect.getsource` 对生产源码做**形态锁**断言（一次无害重构即大面积变红，长期会训练维护者用「改测试」消红）；`tests/test_check_coverage.py:547/559/571/582/598`（5 处手动 `saved=` + try/finally 而非 `monkeypatch.setattr`）；`tests/test_gui_save_atomic.py:34`（唯一未配对的 `mkdtemp`/`mkstemp`）；`tests/test_spider_platform.py:1597`（全仓唯一 `pytest.raises(Exception)`）；4 个前端入口整文件 `skipif(_NODE_BIN is None)`（无 Node 时 2694 行 `.mjs` 断言整体消失） | 约 6 类。不直接造成缺陷，但削弱「失败即回归」的信号价值 | 重命名为 `test_<platform>_<contract>`；形态锁在文件头标注；统一用 `monkeypatch`；把「有 skip 即红」判据固化为一条用例 |
| L-10 | 注释与文档口径漂移 | `src/gui_qt/main_window.py:529`（注释称「启动期只做这一次全量重译」与实现不符，见 M-78）；`src/ui_motion.py:176-181/216-218`（注释提到的 `disable()` 不存在，见 M-82）；`src/proxy.py:77-84`（注释留下「已修好」的错误陈述）；`src/srt_writer.py:170-173`（注释承诺「序号不会被凭空跳大」与实现相反，见 M-58）；`src/platforms/_tars.py` 文件头 CR-03（不变式声明未成立，见 L-06）；`build_exe.py:1936-1938`（注释称「从不真正暴露到局域网」与事实不符，见 M-98） | 6 处。「注释声明强于实现」比没有注释更危险，后来者会照声明去信任结论 | 修实现或改注释，二者必须一致；建议为「注释声明的不变式」补一条断言型用例 |

---

## 7. 与前次报告（2026-10-19）严重项的差分复核

| 上次编号 | 条目 | 现状 | 证据 |
|---|---|---|---|
| S-01 | `scripts/agent_hook_guard.py` 删除守卫可被引号、尾随空格、参数分写绕过 | **已修** | `_protected_hit`（`:249-263`）的边界集合 `_PROTECTED_TAIL_BOUNDARY` 已纳入引号与空白，注释 `:250-254` 明确记录了三种被绕过的书写形态；同族缺口 M-95（动词表覆盖面）仍存 |
| S-02 | 备份脱敏在配置重复键下 fail-open | **已修** | `config_io.py:355-372` 改用 `tolerant_config_parser`（`strict=False`），解析失败时打明确告警而非静默返回原文；注释 `:351-354` 记录了原事故形态。**残留新形态**见 S-08（无 ini 节文件、原子写失败回退 copy2） |
| S-03 | Qt GUI 退出后事件循环永不返回 | **已修** | `src/gui_qt/main_window.py:1177` 存在 `app.quit()` 调用（全目录检索 `\.quit\(\)`/`QApplication\.quit`/`app\.exit` 命中 1 处） |
| S-04 | 派生地址安全闸在末位放行与同址复用分支被翻回「可达」 | **部分修** | 已建 `_DerivedHopRejected` 内部控制流异常（`stream_select.py:430-434`）、已建 `security_rejected` 集合并在 `:1300`/`:1314` 的 record_url 复用分支前判定；但 `except RedirectHopRejected`（`:979-992`）未写入集合 → 见 S-03 |
| S-05 | Web 模式空 URL 时主循环退化为零延迟忙循环 | **已修** | `_interruptible_sleep`（`main.py:470-479`）现返回 bool（被中断返回 True），签名已就位，调用方可据此改走固定 sleep |

**结论**：上一轮 5 项严重条目 4 项已真实修复、1 项部分修复（残留同族一条，已升级为本轮 S-03）。修复质量整体较高——不是「加个 try 了事」，而是把判据本身改对了（边界集合、容错解析器、控制流异常、返回值契约）。这说明本仓的修复流程有效；本轮新发现的严重项，多数是**同一类判据在其它副本上的未闭环**，应当按「判据族」而非「单点」来整改。

---

## 8. 改进建议与修复优先级

排序依据：**风险**（可利用性 × 影响面）优先、**修复成本**次之；同一「判据族」集中整改以降低回归成本与漏改概率。

### P0 —— 判据族统一（建议 1~2 个迭代内完成）

| 顺序 | 条目 | 为什么先做 | 成本/收益 |
|---|---|---|---|
| 1 | S-01 + S-06 + S-04 + S-05（主机/内网/同域判据族） | 四处是同一缺陷的副本：都用字符串包含或字面量前缀而非结构化解析。一次性抽成 `src/net_guard.py` 的 `host_matches_platform()` / `is_internal_target()` / `same_scope()` 三个函数并全局替换，可同时消灭 4 项严重级 SSRF/凭据外泄，且回归面收敛到一处 | 成本中（需改调用点，但都是纯函数替换）/ 收益最高；每条配 2~3 条回归用例即可锁死 |
| 2 | S-07 + S-08（凭据脱敏族） | 明文凭据落盘是「一次泄露，长期有效」的问题，且本仓日志/备份会被用户整包外发。判据补齐 + 无节文件通道 + copy2 回退三条一起改 | 成本中 / 收益高；注意每条新增形态必须有回归用例（本仓已有 `test_web_config_secret_mask.py` 可扩充） |
| 3 | S-02 + S-09（出站 SSRF 族） | 推送通道可被 Web 面板写入、同步通道一旦接线即可利用。逐跳校验 handler 可复用现有 `internal_stream_target_reason` | 成本低 / 收益高 |
| 4 | S-03 | 一行 `security_rejected.add(url)`，是 S-04 同族的最后一块拼图 | 成本极低 / 收益高；建议与第 1 项同批提交 |
| 5 | S-15 + S-10 + S-16（静默失效族） | 三者表现为「在播却不录 / 录了一半自己停」，是用户感知最强、最难自助定位的一类 | 成本低~中 / 收益高（直接降低工单量） |

### P1 —— 数据完整性与生命周期（建议在 P0 之后一个迭代内完成）

| 顺序 | 条目 | 说明 | 成本/收益 |
|---|---|---|---|
| 6 | S-12、M-44、M-45、M-48、M-49 | 下载/安装的完整性与原子性：字节上限、独占创建、原子替换、重试退避。这类缺陷一旦触发会直接让程序失去录制能力 | 成本中 / 收益高 |
| 7 | M-89、M-72、M-69、M-79、M-85 | 退出与停止路径的产物完整性（mp4 moov）、误杀防护、孤儿 ffmpeg、UI 卡死出口 | 成本中 / 收益高；M-72 与 M-85 应一次改（都是「宁可漏清不可误杀」取向） |
| 8 | M-78、M-74、M-71、M-73、M-80、M-81、M-82 | GUI 语言/主题/日志/托盘的一致性与生命周期，本轮 Qt GUI 相关条目密集，建议作为一次「GUI 收敛」专项 | 成本中 / 收益中 |
| 9 | M-59~M-67（Web 安全面） | 限流绕过、请求体上限、写接口键白名单、Origin 缺失放行、SSE 断连 | 成本中 / 收益高（面板是远程可写配置的入口） |
| 10 | M-27~M-34、M-36~M-43（并发与资源） | 阻塞式 DNS、连接池泄漏、无界映射、竞态 | 成本中~高 / 收益中（长跑稳定性） |

### P2 —— 门禁假绿与测试有效性

| 顺序 | 条目 | 说明 | 成本/收益 |
|---|---|---|---|
| 11 | S-14、M-90~M-93、M-100~M-104 | 弱断言、门禁导出通道不校验、覆盖盲区。这类问题不产生用户可见缺陷，但会**让后续所有修复失去验证能力**，因此应在 P0/P1 之前「并行启动」但不必阻塞发布 | 成本低~中 / 收益中（长期） |
| 12 | M-91、M-93、M-94 | 门禁自身的 fail-closed 与超时，防止「门禁没跑成」被读成「代码不合格」 | 成本低 / 收益中 |
| 13 | L-01、L-02、L-03、L-10 | 死代码清理、重复代码抽取、注释口径对齐。可作为低风险的技术债窗口（不夹带行为变更） | 成本低 / 收益中（可维护性） |

### 8.1 流程性建议（非代码）

1. **把「判据族」写进 AGENTS.md 的已知坑**：主机匹配、内网判定、同域判定、凭据脱敏四个判据各自只保留**一个实现**，任何新增调用点必须引用而非重写。本轮 4 项严重级问题全部源于「同一判据的第二份实现比原版弱」。
2. **为「注释声明的不变式」补断言型用例**：L-10 列出的 6 处「注释强于实现」，建议逐条配一条直接断言该不变式的用例（如 `_tars` 的「截断帧必须抛 ValueError」、`srt_writer` 的「丢弃不跳号」）。
3. **门禁导出通道与检查通道同源**：`--emit-env`、`--compare`、`--check` 必须复用 `check()` 的结构校验（M-92），否则「导出成功」与「检查通过」在 CI 上不可区分。
4. **测试有效性纳入常规门禁**：把「无断言的测试函数」与「不带参数的 `assert_called_once()`」做成一条扫描用例（阈值可先设为「不得新增」），防止 S-14 这类弱断言继续累积。

---

## 9. 结论与后续行动项

### 9.1 结论

本次审查覆盖 267 个自研源文件、131,984 行代码，记录 **16 项严重、104 项中等、10 类轻微（约 150 处）**问题。

整体判断：项目的安全与工程基建是**成熟**的——上一轮 5 项严重条目 4 项已正确修复，SSRF 逐跳复检、凭据脱敏、解压防护、运行时钉定、Web 鉴权与同源校验、删除守卫等机制齐备且多数带回归锁，注释与单一事实源纪律的执行度在本轮抽查中未见明显退化。

主要风险集中在**判据的一致性**而非覆盖面的缺失：主机匹配、内网判定、同域判定、凭据脱敏四条判据各自存在「第二份更弱的实现」，本轮 9 项严重级问题中 6 项源于此。其次是**最外层宽泛异常造成的静默功能失效**（抖音解析、播放器列表、斗鱼档位），其共同表现是「在播却不录且日志无异常」，用户无法自助定位、研发难以复现。第三是**测试层的弱断言**（14 个无判据用例 + 17 处只锁调用次数），它们不会让 CI 变红，却会让上述两类修复失去验证能力。

优先处理 P0 的四个「判据族」与 P1 的「退出/安装完整性」，可在两个迭代内消除绝大部分可利用风险与用户可见故障。

### 9.2 可执行后续行动项

| # | 行动项 | 涉及条目 | 验收判据 |
|---|---|---|---|
| 1 | 建立 `src/net_guard.py`，统一主机后缀匹配、内网/保留目标判定、同域判定三个判据，全局替换 `main.py:_match_host`、`bilibili.py:_bili_danmaku_host_allowed`、`stream_select.py:_PRIVATE_HOST_PATTERN/_registrable_domain` 四处实现 | S-01、S-04、S-05、S-06 | 四个语料（`evilweibo.com`、`evil.com?.bilibili.com`、`2130706433`/`::ffff:127.0.0.1`、`co.kr` 同后缀）均有回归用例且全部拒绝 |
| 2 | `except RedirectHopRejected` 分支补 `security_rejected.add(url)` | S-03 | 「重定向落内网 + record_url 同址」场景下 `select_source_url` 返回 None |
| 3 | 补齐 `mask_credentials` 三类形态（ini 行、短键名/中文键、JSON 数值），并为 `config_io` 增加「无 ini 节」与「copy2 回退」的脱敏通道 | S-07、S-08 | `Authorization = Bearer x`、`sig=x`、`{"token":123}` 三条语料全部脱敏；`URL_config.ini` 备份副本不含明文 |
| 4 | 推送与同步出站链路增加逐跳校验（自定义 redirect handler 复用 `internal_stream_target_reason`），给 `msg_push.py:351/552` 补首跳校验 | S-02、S-09 | 302 到 `169.254.169.254` 的推送地址被拒绝且不产生响应体日志 |
| 5 | node 下载加字节上限与「官方文档不可达即拒绝安装」，安装目录 `O_EXCL` + 文件锁 | S-12、M-44 | 超限下载中断并清理；文档不可达时返回失败而非记录基线 |
| 6 | 配置行解析失败/过短不再进入「已注释」归并；抖音解析收窄 try 范围；`get_play_url_list` 统一 `urljoin` 并按 path 判定 `.m3u8` | S-15、S-10、S-16 | 「解析失败行对应的运行中房间不被停止」有回归用例；PandaTV/Twitch 等相对地址产出绝对 URL |
| 7 | 修复 standalone 的 ffmpeg 优雅退出等待；`_reused_pid_same_image` 在取不到创建时间时按「不杀」处理；VBS 目录锚点补尾分隔符 | M-89、M-72、M-85 | 停止录制后的 mp4 含 moov；短目录下不误杀他程序 ffmpeg |
| 8 | Qt GUI 启动补 `retranslate_all()`；Qt 日志链路统一过 `mask_credentials`；`recorder.py` 补 `ended.emit()` 出口 | M-78、M-75、M-79 | 非默认语言启动后静态文案与下拉一致；日志页无明文 URL/签名 |
| 9 | Web 侧：限流双计数、请求体按字节累加、写接口键白名单、Origin 缺失拒绝、`emit_env` 复用结构校验 | M-59~M-67、M-92 | 各条均有针对性用例；门禁导出通道在钉定表被改坏时非 0 退出 |
| 10 | 测试专项：为 14 个无断言用例补判据、17 处 `assert_called_once()` 补参数断言；新增「无断言测试函数」扫描用例 | S-14 | 扫描用例在修复后为 0 命中，且新增弱断言会被拦下 |
| 11 | `--snapshot` 改为白名单正向判定（要求目标在 cwd 之下或为空/不存在） | S-13 | `--snapshot <cwd 外目录>` 被拒绝且给出说明 |
| 12 | 技术债窗口：清理 L-01 死代码、抽取 L-02 重复块、对齐 L-10 的 6 处注释口径 | L-01、L-02、L-10 | 行为零变更（AST 等价性校验通过）、门禁全绿 |

---

## 附录 A：关键结论的实测裁定记录

- **环境**：项目 venv Python `3.14.8 (tags/v3.14.8, Sep 30 2026)`；一次性脚本置于仓库外（`D:\_tmp_review\`），未修改任何仓库文件。
- **复核方式**：复算 `_match_host` 判据、直接调用 `_bili_danmaku_host_allowed` 与 `mask_credentials`、导入 `src.stream_select` 后匹配 `_PRIVATE_HOST_PATTERN` 与调用 `_registrable_domain`/`_is_same_probe_scope`；另逐行核验 `main.py:5202-5204`、`stream_select.py:979-992/1300`、`config_io.py:355-373`、`check_annotations.py:391-455`、`check_runtime_pins.py:277-287`、`gui.py:4671-4720`、`gui_qt/main_window.py:528-538`、`src/gui_qt/app.py` 退出路径（`main_window.py:1177` 的 `app.quit()`）。

| 结论编号 | 实测输入 | 实测输出 | 裁定 |
|---|---|---|---|
| S-01 | `evilweibo.com` / `evil-douyin.com` / `evil3.cn` / `evil-tb.cn` / `evil-kugou.com` | 5/5 均命中平台片段（子串包含成立） | **成立** |
| S-06 | `evil.com?.bilibili.com` | 白名单 True，`urlsplit("wss://"+host).hostname == "evil.com"` | **成立**（`%3F` 形态真实 host 含 `%3F`，不可利用；`#` 形态被拒绝） |
| S-04 | `2130706433`、`0177.0.0.1`、`::ffff:127.0.0.1`、`100.64.0.1` | 均**未命中** `_PRIVATE_HOST_PATTERN` | **成立** |
| S-05 | `a.example.co.kr` vs `evil.co.kr` | 两者注册域均为 `co.kr`，`_is_same_probe_scope` 返回 True | **成立** |
| S-07 | 10 条语料（ini 行 3 条、短键名 3 条、JSON 数值 3 条、对照 1 条） | 7 条原样返回（逃逸），`token=abcdef` 与 `?token=abcdef` 正常脱敏 | **成立** |
| S-03 / S-15 | 逐行核验 `stream_select.py:979-992`（无 `security_rejected.add`）与 `main.py:5202-5204` 归并判据、`main.py:5071-5072` 的 `continue` | 与报告描述一致 | **成立**（静态核验，未做运行时复现） |
| S-13 | 逐行核验 `_reject_dangerous_baseline` 的放行路径 | cwd 之外的绝对路径落在「未命中任何拒绝规则 → 返回 None（放行）」 | **成立** |
| 前次 S-02 | 核验 `config_io.py:355-372` | 已改用 `tolerant_config_parser`，解析失败打明确告警 | **已修** |
| 前次 S-03 | 全目录检索退出调用 | `main_window.py:1177` `app.quit()` | **已修** |
| 前次 S-05 | 核验 `_interruptible_sleep` | 返回 bool、被中断返回 True（`main.py:470-479`） | **已修**（未逐调用点核验） |

> **未实测项说明**：以下结论来自逐行静态阅读，未做运行时复现，标注为「（待核）」性质，建议修复前先补一条复现用例：M-37（stats 线程竞态）、M-39（`error_count` 读取竞争）、M-31（跨循环 client 未关闭）、M-38（join 超时后并发 close）、M-27（事件循环内阻塞 DNS 的实际卡顿幅度）。
>
> **副作用说明**：实测脚本为复算 `stream_select` 判据而导入了 `main`，由此触发了一次模块级退出钩子（日志轮转归档与 ffmpeg 进程清理）。这属于运行期副作用，未改动任何源文件；如发现 `logs/` 下多出一份时间戳归档属此原因，可安全忽略。

---

*报告生成日期：2026-10-21｜审查方式：全量静态通读 + 关键结论实测｜未修改任何源文件*
