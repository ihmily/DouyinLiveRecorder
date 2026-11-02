# DouyinLiveRecorder 全量源代码审查报告（CODE_REVIEW_2026-09-29）

- **审查日期**：2026-09-29
- **审查对象**：DouyinLiveRecorder 工作空间全部自有源代码（v4.4.0，基线 pyproject.toml `requires-python >= 3.14`）
- **审查维度**：代码质量、潜在缺陷、安全漏洞、逻辑错误
- **审查方式**：静态白盒审查。全部受审文件经逐行通读（长文件分段无跳读），辅以全仓危险模式检索交叉验证；所有列入本报告的问题均回源核对了对应文件、行号与原始代码片段，未凭推测立项
- **问题统计**：**严重 1 项 ｜ 中等 9 项 ｜ 轻微 38 项**

---

## 一、审查概述与背景

DouyinLiveRecorder 是一个支持 60+ 直播平台的录制工具，包含命令行（main.py）、GUI（gui.py）与 Web 管理面板（web.py + FastAPI）三种运行形态，核心链路为「配置解析 → 平台分发 → 流地址获取/选源 → ffmpeg 录制/HTTP 直下 → 弹幕采集 → 录后转码与消息推送」。

本项目安全成熟度整体较高：此前已进行过多轮带编号的安全收敛（SEV/MID/MIN/CR/WD 系列，见 docs/worklog/ 历史审查记录），Web 鉴权、SSRF 写入校验、日志脱敏、子进程 argv 化、压缩包安全解压、原子写等防线已成体系。本次全量复审的目标是：①检验既有修复是否在**所有同型链路**上对齐（重点查"修了一处、漏了另一处"的漂移）；②发现尚未被任何一轮审查覆盖的残留缺陷；③对代码质量与可维护性做整体评估。

审查中的一个重要背景事实：本仓代码注释极其详尽，大量历史决策、事故形态与"已知残留缺口"均被显式记录。本报告不把这些**已登记、已知情的设计取舍**（如 ffmpeg TOFU 哈希模型、HLS-only 平台 http 降级、Windows chmod 限制）重复计为漏洞；仅对"注释承诺与代码实际不符"或"同型链路防护未对齐"的情形立项。

---

## 二、审查范围

### 2.1 已逐行审查的自有源代码

| 分组 | 文件（根目录相对路径） |
|---|---|
| 入口与主引擎 | main.py（5455 行）、gui.py、web.py、msg_push.py、i18n.py、build_exe.py |
| 录制管线（src/） | spider.py（6885 行）、stream.py、stream_select.py、ffmpeg_proc.py、video_postprocess.py、srt_writer.py、scheduler.py、collector.py、room.py、danmaku_monitor.py、recorder_status.py |
| 基础设施（src/） | async_http.py、sync_http.py、http_config.py、utils.py、config_io.py、config_bool.py、cookie_cache.py、ttwid.py、ab_sign.py、proxy.py、log_archive.py、logger.py、ffmpeg_install.py、ffmpeg_master_download.py、node_install.py、__init__.py、base.py |
| Web 面板 | web_api.py、web_config.py、web_tray.py；web/app.js、web/index.html、web/style.css；根目录 index.html |
| 平台与弹幕协议 | platforms/ 下 bilibili.py、douyin.py、douyu.py、huya.py、twitch.py、_tars.py、_xbogus.py；ws_client.py；javascript/ 下 haixiu.js、liveme.js、migu.js、x-bogus.js |
| 构建/运维/脚本 | Dockerfile、docker-compose.yaml、StopRecording.vbs、.github/workflows/ 全部 yml；scripts/ 下全部 15 个 .py/.sh（含 douyin_live_recorder_standalone.py） |

合计约 3.5 万行产品代码，Python / JavaScript / HTML / CSS / VBS / Shell / YAML / Dockerfile 均在覆盖内。

### 2.2 明确排除项

- 第三方依赖与运行时：`.venv/`、`node/`、`ffmpeg/`、`src/javascript/crypto-js.min.js`（第三方压缩库）
- 生成产物与类型存根：`src/proto/douyin_pb2.py`（protoc 生成）、`typings/`
- 工具备份目录：`.workbuddy/`（含一份旧版全量源码备份，非工程产物）、各类 `.qoder/.trae/agents` 等工具目录
- 文档与构建产物：`docs/`、`dist/`、`build/`、`uv.lock`
- **测试代码（tests/，约 4 万行）未逐行评审**：本次以产品缺陷与安全漏洞为目标，测试代码仅作为"回归锁"被交叉引用（用于验证某项防护是否有自动化断言锁定）。建议后续单开一轮测试代码专项审查

### 2.3 方法与边界

- 长文件（main.py、spider.py、gui.py、web_api.py、web_config.py、build_exe.py、standalone 等）按段全文通读，不抽样；
- 全仓检索 `shell=True / os.system / eval / exec / pickle.load / yaml.load / verify=False / http://` 等危险模式并逐一人工判定；
- 对 ffmpeg 子进程、HTTP 重定向、压缩包解压、配置写入、Web 鉴权、子进程安装等高风险链路做了跨模块的数据流追踪；
- 本报告为**静态审查结论**，未实机动态复现；严重项 S1 与中等级各项的触发序列为代码控制流直接可读的推演结论。
- 语法说明：本仓多处出现 `except TypeError, ValueError:` 写法，经本机 CPython 3.14.7 `ast.parse` 实测与 `except (TypeError, ValueError):` 等价（PEP 758，black 26 风格），配合 pyproject `requires-python = ">=3.14"`，**不是 Python 2 旧语法、不构成缺陷**。

---

## 三、问题清单（按严重程度分类）

### 3.1 严重（Critical，1 项）

#### 【S-1】Shopee 短链跳转无落地主机白名单：配置 Cookie 可被重定向劫取，且构成带凭据的内网 SSRF

- **位置**：[src/spider.py:6033-6057](file:///d:/DouyinLiveRecorder-dev/DouyinLiveRecorder/src/spider.py#L6033-L6057)；辅助函数 [src/spider.py:112-120](file:///d:/DouyinLiveRecorder-dev/DouyinLiveRecorder/src/spider.py#L112-L120)（`_shopee_host_suffix`）
- **真实代码片段**：

```python
# 6025-6037：调用方配置的 shopee_cookie 被装入 headers
if cookies:
    headers["Cookie"] = cookies
...
# 非直链且非店铺主页：先解析重定向拿到真实 host/会话
if "live.shopee" not in url and "uid" not in url:
    url_result = await async_req(url, proxy_addr=proxy_addr, headers=headers, redirect_url=True, abroad=True)
    # 重定向失败（空响应）时保留原 URL 继续解析
    if isinstance(url_result, str) and url_result:
        url = url_result
...
# 6047-6057：落地 URL 未经任何主机校验即派生 API 主机，并带同一份 headers（含 Cookie）再请求
host_suffix = _shopee_host_suffix(url)
...
api_host = f"https://live.shopee.{host_suffix}"
...
if uid:
    json_str = await async_req(
        f"{api_host}/api/v1/shop_page/live/ongoing?uid={uid}", proxy_addr=proxy_addr, headers=headers, abroad=True
    )
```

- **问题描述**：
  1. 用户在 URL_config.ini 添加 Shopee 分享链（入口侧合法——main.py:5236 把 host 归一为 `"live.shopee."`/`".shp.ee"` 后命中 PLATFORM_HOST 白名单）。当链接是短链（如 `.shp.ee/xxx`）时，第 6034 行用 `redirect_url=True`（httpx 全程自动跟随 30x）取回**由响应方决定的**最终落地 URL，且初始请求就带着用户配置的 `shopee_cookie`。httpx 在跨源重定向时只剥离 Authorization、**不剥离显式传入的 Cookie 头**，故短链落地页一跳即可收到 Cookie。
  2. 落地 URL 被无条件信任：`_shopee_host_suffix("https://live.shopee.evil.com/x")` 的算法是"剥掉 `live.` 前缀后取首点之后的全部"，对该输入返回 `"evil.com"`，于是 `api_host = https://live.shopee.evil.com`；第 6056 行带着**同一份含 Cookie 的 headers** 向攻击者主机发起第二次请求。`https://live.shopee.evil.com/?uid=x` 这类地址甚至不需要短链——直接写入配置即可（含 `"live.shopee"` 子串，跳过第 6033 行的短链分支，直达 6047 行的后缀解析）。
  3. 全链路无主机白名单、无内网地址判定。攻击者主机亦可解析到/指向 `127.0.0.1`、`169.254.169.254` 等内网目标，形成带凭据的 SSRF（响应内容经解析链失败后会进入日志/错误分支，存在观测侧信道）。
- **对照实证（同仓已修复的同型问题）**：小红书短链路径 [src/spider.py:2335-2371](file:///d:/DouyinLiveRecorder-dev/DouyinLiveRecorder/src/spider.py#L2335-L2371)（SEV-2214）已对落地页设置两道闸——`_xhs_is_allowed_host` 域族白名单 + `web_config._host_internal_reason` 内网判定，不通过即丢弃跳转并剥离凭据。Shopee 路径是该修复**未对齐的孪生链路**。
- **影响分析**：
  - 前置条件低：受害者只需添加一个攻击者构造的 Shopee 分享链（正常添加房间操作），无需面板权限；
  - 后果：用户配置的 Shopee 登录 Cookie 被发送到攻击者可控主机（账号凭据外泄）；本机被驱动向内网/云元数据地址发起带 Cookie 的 GET（SSRF）；
  - 这是本仓"出站目标收口"体系（web_config 的 SEV-03/MID-N45 覆盖了 Web 写入口与小红书路径）尚未覆盖的一条解析器内部链路。
- **修复建议**：镜像小红书 SEV-2214 做法——对第 6034 行得到的落地 URL：① 校验 host 落在 Shopee 域族白名单（精确匹配 `live.shopee.<公开 TLD>` 及各地区站点，禁止"子串包含"判据）；② 调 `web_config._host_internal_reason` 判内网；③ 任一不通过则丢弃跳转结果、保留原始短链，并对后续请求剥离 Cookie。另建议对 `api_host` 派生结果再做一次同样的白名单断言（纵深防御）。

---

### 3.2 中等（Major，9 项）

#### 【M-1】流地址探针跟随重定向时：跨源不剥离 Cookie、不拦截内网落地

- **位置**：[src/stream_select.py:470](file:///d:/DouyinLiveRecorder-dev/DouyinLiveRecorder/src/stream_select.py#L470)、[537](file:///d:/DouyinLiveRecorder-dev/DouyinLiveRecorder/src/stream_select.py#L537)、[725](file:///d:/DouyinLiveRecorder-dev/DouyinLiveRecorder/src/stream_select.py#L725)、[759](file:///d:/DouyinLiveRecorder-dev/DouyinLiveRecorder/src/stream_select.py#L759)（同步 httpx 客户端的 GET/Range-GET/HEAD）；异步侧同型 [src/async_http.py:558](file:///d:/DouyinLiveRecorder-dev/DouyinLiveRecorder/src/async_http.py#L558)、[568-570](file:///d:/DouyinLiveRecorder-dev/DouyinLiveRecorder/src/async_http.py#L568-L570)
- **问题描述**：候选流地址在发请求前经过了 scheme 白名单与 `_internal_stream_target_reason` 内网判定，但该判定只作用于**初始 URL**。所有探针均 `follow_redirects=True`，而 30x 的 Location 由响应方（可被劫持/攻陷的 CDN 或平台接口）控制：跨源跳转时 httpx 不剥显式 Cookie，内网地址不被拦截。MID-2231 的两道闸（`_is_derived_hop_allowed`、`_headers_for_derived_hop`）只覆盖"播放列表正文解析出的派生地址（variant/分片）"，**不覆盖 HTTP 重定向跳**。
- **影响**：被篡改的流地址响应一次 302 即可：①把 B站等平台 Cookie 导向攻击者主机（凭据外泄）；②把探针引向 `127.0.0.1:6379`、云元数据端点等（SSRF 端口/服务观测，状态码与 content-type 会进入 debug 日志）；③ 内网服务若返回 200，候选被判"可达"，随后 ffmpeg 也会去拉同一内网地址。
- **修复建议**：统一重定向策略——在探针 client 上挂 `event_hooks` 或改用"禁止自动跟随 + 逐跳手工校验"，每一跳落地都过 `_is_recordable_url` + 内网判定（代理场景复用 `_internal_stream_target_reason` 的 DNS 豁免口径），跨源跳剥 Cookie；async_http.get_response_status 同改。

#### 【M-2】stream.py 虎牙 Web 解析仍用 FLV 票据裁决整条候选，HLS-only 线路被整条丢弃

- **位置**：[src/stream.py:939-953](file:///d:/DouyinLiveRecorder-dev/DouyinLiveRecorder/src/stream.py#L939-L953)
- **真实代码片段**：

```python
s_flv_anti = cdn.get("sFlvAntiCode") or ""
...
if not s_stream_name or not s_flv_anti:   # 939 行：FLV 票据为空即整条 continue
    continue
...
hls_url = ""
if s_hls_anti and s_hls_url and s_hls_suffix:   # HLS URL 仅依赖 HLS 票据
    hls_url = ...
```

- **问题描述**：同数据结构的 App 路径已在 MIN-2202 修复（[src/spider.py:1297-1323](file:///d:/DouyinLiveRecorder-dev/DouyinLiveRecorder/src/spider.py#L1297-L1323)：整条 entry 有效性只由 `sStreamName` 裁决，FLV/HLS 各自按自己票据产出），但 Web 路径仍是旧判据。当房间只下发 HLS 票据（`sHlsAntiCode` 有值、`sFlvAntiCode` 为空）或该 CDN 线路不承载 FLV 时，连 HLS 候选一并被砍。
- **影响**：该形态房间在 Web 链路下多 CDN 回退与"HLS 优先"策略失效，表现为在播却漏录/反复降级；两处同构代码口径漂移，今后任一侧修改仍会再次分叉。
- **修复建议**：与 spider.py:1302-1323 对齐——判据改为 `if not s_stream_name: continue`，`hls_url`/`flv_url` 各自按票据非空独立产出，再以"至少一路非空"作为入列条件。

#### 【M-3】多个平台请求体用字符串拼接构造 JSON，外部派生值可破坏 JSON 结构（字段污染）

- **位置**：
  - 百度 [src/spider.py:4269-4274](file:///d:/DouyinLiveRecorder-dev/DouyinLiveRecorder/src/spider.py#L4269-L4274)：`'"data":{"room_id":"' + room_id + '"...'`（room_id 取自用户 URL 正则，4260 行）；
  - 淘宝 [src/spider.py:6256](file:///d:/DouyinLiveRecorder-dev/DouyinLiveRecorder/src/spider.py#L6256)：`'{"liveId":"' + live_id + '","creatorId":null}'`（live_id 取自重定向落地页正则，网络可控）；
  - 京东 [src/spider.py:6477](file:///d:/DouyinLiveRecorder-dev/DouyinLiveRecorder/src/spider.py#L6477)、[6500](file:///d:/DouyinLiveRecorder-dev/DouyinLiveRecorder/src/spider.py#L6500)（authorId/liveId 来自落地页 query）；
  - YY [src/spider.py:1608-1614](file:///d:/DouyinLiveRecorder-dev/DouyinLiveRecorder/src/spider.py#L1608-L1614)（页面正则抠出的 cid 双处拼入）。
- **问题描述**：这些值未做 JSON 编码即拼进 JSON 字面量。值中出现 `"`、`\` 即可闭合字符串、注入/篡改任意字段（如淘宝 body 的 sign 虽随后按原文计算，签名会失效，但请求语义可被构造成畸形/污染形式）；目标主机均为官方 API，不构成 RCE，属请求完整性问题。
- **影响**：恶意房间链接或被篡改的平台落地页可让本进程发出语义被污染的官方 API 请求，造成解析失败、签名失效或字段被改写；且与仓内"外部输入须经编码"的普遍做法不一致。
- **修复建议**：改为 `dict` 构造 + `json.dumps(..., separators=(",", ":"), ensure_ascii=False)`（淘宝等需固定紧凑分隔与签名串一致时，签名也对 dump 后文本计算）；或至少对插值做 JSON 字符串转义。

#### 【M-4】check_nodejs_installed 只捕 FileNotFoundError，node 可执行档挂起/异常会穿透 import 期直接崩进程

- **位置**：[src/node_install.py:386-397](file:///d:/DouyinLiveRecorder-dev/DouyinLiveRecorder/src/node_install.py#L386-L397)；调用点 [src/__init__.py:37-39](file:///d:/DouyinLiveRecorder-dev/DouyinLiveRecorder/src/__init__.py#L37-L39)
- **真实代码片段**：

```python
try:
    result = subprocess.run(["node", "-v"], capture_output=True, timeout=15)
    version = result.stdout.strip()
    if result.returncode == 0 and version:
        return True
# 注释承诺：「其它异常也吞掉返 False」——实际只捕了 FileNotFoundError
except FileNotFoundError:
    pass
return False
```

- **问题描述**：`subprocess.run(..., timeout=15)` 在 node 挂死（杀软扫描、网络盘上的损坏可执行档等）时抛 `subprocess.TimeoutExpired`，其它 OSError（权限、杀软锁定）同样未捕。而 `check_node()` 在 `import src` 期间（`__init__.py:39`，无 try 包裹）被调用——异常直接穿透导入链，导致**整个程序启动崩溃**。代码注释明确承诺"其它异常也吞掉返 False"，属注释与实现不符。对照 ffmpeg 侧 `check_ffmpeg_installed`（ffmpeg_install.py:681-713）已正确捕获 TimeoutExpired/OSError/Exception。
- **影响**：node 可执行档存在但卡住或损坏的环境下，每次启动都以未处理异常退出，且不会进入自动安装分支（误判为"已安装"路径上的崩溃），Web/GUI/CLI 三种形态同受影响。
- **修复建议**：补 `except subprocess.TimeoutExpired` 与 `except OSError`（最终兜底 `Exception`），warning 一次后返回 False；`src/__init__.py:39` 调用点也建议包一层 best-effort try（导入期检查不应有崩溃面）。

#### 【M-5】node 安装目录损坏后新下载版本永不生效，且损坏目录验证分支未注入 PATH

- **位置**：[src/node_install.py:261-283](file:///d:/DouyinLiveRecorder-dev/DouyinLiveRecorder/src/node_install.py#L261-L283)
- **问题描述**：解压后仅当目标 `node/` 目录不存在时才 `os.rename` 为 `node`；若 `node/` 已存在但内容损坏（杀软隔离、升级中断、磁盘错误），则：① 新解压的 `node-vX...` 目录被闲置（第 262 行解压完成、266 行条件不成立），刚下载的新版本永不生效；② elif 验证分支（276-282 行）直接 `subprocess.run(["node", "-v"])`，**没有像首装分支（268 行）那样把 `execute_dir/node` 注入 PATH**，验证的是 PATH 上另一份 node（可能是损坏的那份，也可能根本不存在而抛 FileNotFoundError 穿透到外层）。
- **影响**：node 目录一次损坏即进入"每次启动重复下载约 30MB → 解压 → 验证失败 → 放弃"的循环，JS 签名功能（抖音 X-Bogus、LiveMe、嗨秀、咪咕）永久不可用且无法自愈。
- **修复建议**：采用"解压到临时目录 → 验证 `临时目录/node -v` 通过 → rmtree 旧目录 → 原子改名"的切换方式（与 ffmpeg 侧 M-7 建议同型）；两个验证分支都显式注入 PATH 后再验证。

#### 【M-6】node 新下载压缩包缺少"zip 形态"前置校验，TOFU 基准哈希可能被 HTML 挑战页污染

- **位置**：[src/node_install.py:233-262](file:///d:/DouyinLiveRecorder-dev/DouyinLiveRecorder/src/node_install.py#L233-L262)
- **问题描述**：缓存 zip 仅在 `is_valid_zip()` 为真时才做哈希记账，而**新下载完成**的包直接进入 `unzip_file`（262 行），没有同 ffmpeg_install 的"哈希前置形态闸"。当 npmmirror 返回 200 + `text/html` 挑战/错误页（同时官方 SHASUMS 不可达）时，TOFU（首次使用信任）分支会把这份 HTML 的哈希写为可信基准（127-128 行写文件亦非原子，见轻微 I-2），下次真正的 zip 反而因哈希不符被拒装。
- **影响**：窄条件（镜像投毒/挑战页 + SHASUMS 不可达）下造成 node 永久拒装，属可用性/供应链完整性缺陷；ffmpeg 侧已有同款防护（ffmpeg_install.py:313-333），node 侧未对齐。
- **修复建议**：下载落盘后、TOFU 记账与解压前统一加 `is_valid_zip(path)` 校验，非 zip 立即删包返 False。

#### 【M-7】ffmpeg 覆盖安装"先 rmtree 后 copytree"无回滚，复制失败会丢掉原本可用的安装

- **位置**：[src/ffmpeg_install.py:361-366](file:///d:/DouyinLiveRecorder-dev/DouyinLiveRecorder/src/ffmpeg_install.py#L361-L366)；同型 [src/ffmpeg_master_download.py:436-439](file:///d:/DouyinLiveRecorder-dev/DouyinLiveRecorder/src/ffmpeg_master_download.py#L436-L439)
- **问题描述**：升级流程为 `shutil.rmtree(ffmpeg目标目录)` → `shutil.copytree(bin_dir, ffmpeg/)`。中途磁盘满、权限变化、杀软拦截会使 copytree 失败，旧版本已被删除且无回滚——状态比升级前更差（此前 ffmpeg 可用）。
- **影响**：升级失败即录制能力整体丧失，需手工干预；Windows 上 rmtree 还可能因 exe 被占用而部分删除。
- **修复建议**：copytree 到同级临时目录并先验证临时副本（`临时目录/ffmpeg -version`），通过后再替换（rmtree+rename），失败保留旧目录；rename 失败时清理临时目录并告警。

#### 【M-8】配置备份脱敏失败时静默降级为明文备份，且无任何告警

- **位置**：[src/config_io.py:375-385](file:///d:/DouyinLiveRecorder-dev/DouyinLiveRecorder/src/config_io.py#L375-L385)
- **真实代码片段**：

```python
if _backup_mask_secrets():
    try:
        with open(file_path, "r", ...) as src_f:
            content = src_f.read()
        with open(backup_file_path, "w", ...) as dst_f:
            _ = dst_f.write(_redact_ini_secrets(content))
    except OSError:
        # 读不到就退回原样复制，宁可留下明文备份也不要备份缺失
        _ = shutil.copy2(file_path, backup_file_path)   # ← 明文落盘，无日志
```

- **问题描述**：CR-07 的安全承诺是"备份默认脱敏"，但读源文件抛 OSError（Windows 共享违例、杀软占用是常见情形）时直接 copy2 出一份含全部 Cookie/账号密码/授权码的明文备份，备份目录（backup_config/，6 份轮转）正是用户打包外发/云同步概率最高的目录；且整个降级过程无 warning，用户无法感知哪份是明文。另外 except 只收 OSError，写脱敏副本时的 `UnicodeError`（它是 ValueError 不是 OSError）会落到外层笼统 error，同样不会走 copy2——此分支语义也不完整。
- **影响**：明文凭据以"备份"名义长期留存并随轮转保留多份，削弱 CR-07 的凭据保护；安全控制被静默绕过是此类问题里最需避免的形态。
- **修复建议**：copy2 前必须 `logger.warning` 明示"本次备份未脱敏"及文件名；except 同时收 `OSError, UnicodeError`；或改为"脱敏失败就跳过本次备份"（下轮重试），从根上不落明文。

#### 【M-9】cookie_cache singleflight 拉取失败日志中异常原文未脱敏，可泄露签名 URL

- **位置**：[src/cookie_cache.py:344-352](file:///d:/DouyinLiveRecorder-dev/DouyinLiveRecorder/src/cookie_cache.py#L344-L352)
- **真实代码片段**：

```python
except Exception as e:
    logger.warning(
        i18n.tr("凭据拉取失败: {masked_key} - {type_name}: {e}",
                masked_key=utils.mask_credentials(key),
                type_name=type(e).__name__,
                e=e))   # ← 同文件 fetch_cookies 失败分支（192-202 行）写的是 mask_credentials(str(e))
```

- **问题描述**：key 做了脱敏，异常对象 `e` 却原样输出。httpx 异常文本通常内嵌完整请求 URL（wsAuth/signature/token 查询串、代理 userinfo），该 singleflight factory 用于 Twitch client-id、B 站 buvid3、抖音 ttwid 等拉取，异常 URL 直接进入 streamget.log（轮转保留多份）。与同文件 fetch_cookies 分支及全仓 WD-01 脱敏口径不一致。
- **影响**：带签名/鉴权参数的 URL 凭据长期落盘，日志外发即泄露。
- **修复建议**：改为 `e=utils.mask_credentials(str(e))`，与 fetch_cookies:192-202 完全同口径。

---

### 3.3 轻微（Minor，38 项）

> 以下各项均有真实代码依据，按模块分组列出；同一类问题跨文件同型的合并为一条并列出全部位置。

#### A. 录制管线（src/）

| 编号 | 位置 | 问题与建议 |
|---|---|---|
| A-1 | [spider.py:1313](file:///d:/DouyinLiveRecorder-dev/DouyinLiveRecorder/src/spider.py#L1313)、[stream.py:944](file:///d:/DouyinLiveRecorder-dev/DouyinLiveRecorder/src/stream.py#L944)、[949](file:///d:/DouyinLiveRecorder-dev/DouyinLiveRecorder/src/stream.py#L949)、[spider.py:5161](file:///d:/DouyinLiveRecorder-dev/DouyinLiveRecorder/src/spider.py#L5161) | 虎牙 App/Web 路径与 ShowRoom 候选强制把 https 降为明文 http（注释自承 https 实测 403）。URL query 内含防盗链票据，同网段可嗅探重放。属刻意取舍，建议加显式配置开关并在文档/日志注明风险。 |
| A-2 | [srt_writer.py:117-125](file:///d:/DouyinLiveRecorder-dev/DouyinLiveRecorder/src/srt_writer.py#L117-L125) | `_open_segment` 以 `"a"` 打开已存在分片同时无条件 `_index = 0`。同一 SRT 分片在**新实例**（重连后新建 DanmakuCollector/SrtWriter）追加写时块号从 1 重新开始，出现 `1..N,1,2…`，违反文件自身注释（103-111 行）声明的"块号单调不回卷"不变量（现有防护只覆盖同实例 close/reopen）。建议追加打开已存在文件时扫描末块序号续编。 |
| A-3 | [spider.py:4839-4842](file:///d:/DouyinLiveRecorder-dev/DouyinLiveRecorder/src/spider.py#L4839-L4842) | 死代码：except 分支内 4835-4838 行已 raise，4839-4842 行是逐字重复、永不可达的第二个 raise。直接删除。 |
| A-4 | [spider.py:3057](file:///d:/DouyinLiveRecorder-dev/DouyinLiveRecorder/src/spider.py#L3057)、[2510](file:///d:/DouyinLiveRecorder-dev/DouyinLiveRecorder/src/spider.py#L2510) | 空串/畸形 URL 触发 IndexError（`url[-1]`、`url.split("/")[3]`），被 `@trace_error_decorator` 统一吞成"未开播"，用户侧无任何诊断线索。建议显式判形并抛带文案的 ValueError（与 TwitCasting:4137-4138 的做法一致）。 |
| A-5 | [spider.py:5762-5794](file:///d:/DouyinLiveRecorder-dev/DouyinLiveRecorder/src/spider.py#L5762-L5794) | VV 星球 `room_id` 非空判空在首次 API 请求（5762-5763 行）**之后**（5794 行），缺 room_id 时白烧一次请求。建议判空前移。 |
| A-6 | [spider.py:4028-4033](file:///d:/DouyinLiveRecorder-dev/DouyinLiveRecorder/src/spider.py#L4028-L4033) | PopkonTV 重试逻辑里 `cast_start_date_code_int = int(...) - 1` 计算后从未传入 `fetch_data`（闭包仍用原值），注释自认"若减 1 才是正确时效值则二次确认仍会失败"。建议确认接口语义后修正或删除死变量。 |
| A-7 | [video_postprocess.py:457-458](file:///d:/DouyinLiveRecorder-dev/DouyinLiveRecorder/src/video_postprocess.py#L457-L458) | 时间字幕线程每秒 open/append/close 一次文件，慢盘/杀软下放大 IO 与失败率；另外 `text_encoding` 配成非法编码名时 `LookupError` 不被捕获，线程无告警静默死亡。建议长持句柄、周期 flush；非法编码告警一次后停写。 |
| A-8 | [video_postprocess.py:206-210](file:///d:/DouyinLiveRecorder-dev/DouyinLiveRecorder/src/video_postprocess.py#L206-L210)；同型 [notify.py:106-109](file:///d:/DouyinLiveRecorder-dev/DouyinLiveRecorder/src/notify.py#L106-L109) | 超时 `process.kill()` 之后的第二次 `communicate()` 未设超时，被杀进程若因继承句柄占住管道可无限挂住后处理/通知线程。建议加有界超时。 |
| A-9 | [stream.py:593](file:///d:/DouyinLiveRecorder-dev/DouyinLiveRecorder/src/stream.py#L593) | TikTok `sdk_params` 直接 `json.loads`，平台返回截断/脏响应时抛异常被装饰器吞成"未开播"，无线索。建议局部 try + warning 后跳过该档。 |
| A-10 | [room.py:91](file:///d:/DouyinLiveRecorder-dev/DouyinLiveRecorder/src/room.py#L91)、[179](file:///d:/DouyinLiveRecorder-dev/DouyinLiveRecorder/src/room.py#L179) | `client.get(..., follow_redirects=True)` 对用户房间 URL 的落地 host 不校验（当前调用点不传 headers/Cookie，风险潜伏）。建议预防性加域族判定，防止未来带凭据调用时变成 S-1 同型。 |
| A-11 | [spider.py:920-923](file:///d:/DouyinLiveRecorder-dev/DouyinLiveRecorder/src/spider.py#L920-L923)、[2261](file:///d:/DouyinLiveRecorder-dev/DouyinLiveRecorder/src/spider.py#L2261)、[5698-5700](file:///d:/DouyinLiveRecorder-dev/DouyinLiveRecorder/src/spider.py#L5698-L5700)、[97](file:///d:/DouyinLiveRecorder-dev/DouyinLiveRecorder/src/spider.py#L97) | 硬编码第三方访客凭据（TikTok 访客 cookie、小红书 sid、嗨秀/嗨嗨 accessToken、PopkonTV 应用凭据）。均为公开访客/应用级常量、注释也提供环境变量覆盖，但随公开仓库分发存在被平台连带风控封禁的可能。建议统一登记到"凭据轮换清单"。 |

#### B. 平台与弹幕协议

| 编号 | 位置 | 问题与建议 |
|---|---|---|
| B-1 | [platforms/twitch.py:46](file:///d:/DouyinLiveRecorder-dev/DouyinLiveRecorder/src/platforms/twitch.py#L46)、[85-92](file:///d:/DouyinLiveRecorder-dev/DouyinLiveRecorder/src/platforms/twitch.py#L85-L92) | 频道名仅 `lstrip("#").strip()`，未过滤 `\r\n`，恶意频道名可向 IRC 帧注入额外命令（CRLF 协议注入）。影响限于受害者自己的匿名 Twitch 连接。建议加白名单 `^[A-Za-z0-9_]{1,64}$`。 |
| B-2 | [javascript/migu.js:378](file:///d:/DouyinLiveRecorder-dev/DouyinLiveRecorder/src/javascript/migu.js#L378) | `` return `${inputUrl}&ddCalcu=${ddCalcu}&sv=${sv}` `` 中 ddCalcu/sv 未做字符断言与百分号编码，污染输入可插入额外 query 或截断 fragment。信任边界为官方白名单 HTTPS 接口，实际触发概率低，建议输出前断言 `^[A-Za-z0-9_=+/.-]+$` 或 encodeURIComponent 后用 URL 对象拼装。 |
| B-3 | [ws_client.py:112-122](file:///d:/DouyinLiveRecorder-dev/DouyinLiveRecorder/src/ws_client.py#L112-L122) | `SECLEVEL=1` 的宽松 TLS 上下文本为斗鱼 8506 旧套件设置，却对所有 wss 平台统一生效（携带 SESSDATA/bilibili Cookie 的 B站、抖音连接也被降级）。证书主机名校验仍开启，属纵深防御缺口。建议按主机区分，仅对 danmuproxy.douyu.com 应用。 |
| B-4 | [platforms/bilibili.py:98-118](file:///d:/DouyinLiveRecorder-dev/DouyinLiveRecorder/src/platforms/bilibili.py#L98-L118) | 多 host 回退时每个候选都是独立 WsClient，前一 host 重连耗尽时其 `_close_reason` 会立即触发 collector 的 `room_closed` → 监控面板出现一次误导性"关闭→重连"抖动。不影响实际录制。建议试探阶段静默耗尽，全部失败后再回调一次。 |
| B-5 | [ws_client.py:102-105](file:///d:/DouyinLiveRecorder-dev/DouyinLiveRecorder/src/ws_client.py#L102-L105) | brotli 限长解压为"4KB 输入分块 process 后才判断输出超限"，单块最坏可瞬时放大到数十 MiB（8MiB 广告上限内），与"先判断后膨胀"的严格限长有量级差距。需服务端病态帧才能触发。建议缩小 process 输入步长（如 1KB）。 |
| B-6 | [ws_client.py:117-119](file:///d:/DouyinLiveRecorder-dev/DouyinLiveRecorder/src/ws_client.py#L117-L119) | 跨帧文本行缓冲 `_line_buf` 只在出现 `\n` 时切分，无长度上限；对端持续发不含换行的帧可使内存跨帧无界增长（单帧受 8MiB 限制，累积不受限）。正常/被攻陷官方服务器不可达，建议设 64KiB 行上限。 |
| B-7 | [javascript/liveme.js:332-350](file:///d:/DouyinLiveRecorder-dev/DouyinLiveRecorder/src/javascript/liveme.js#L332-L350) | ① 硬编码签名密钥为前端公开常量、签名用不加盐 MD5——供应商反爬混淆设计，非本仓可修，建议文件头注明"客户端公开常量，勿当秘密管理"；② 333/347/350 行 `console.log` 把含 sKey 的拼接串打到子进程 stdout，execjs 管道虽会丢弃输出，但噪声与潜在泄露面仍在，建议删除调试输出。 |

#### C. 安装器与基础设施

| 编号 | 位置 | 问题与建议 |
|---|---|---|
| C-1 | [ffmpeg_install.py:85-88](file:///d:/DouyinLiveRecorder-dev/DouyinLiveRecorder/src/ffmpeg_install.py#L85-L88)/[375](file:///d:/DouyinLiveRecorder-dev/DouyinLiveRecorder/src/ffmpeg_install.py#L375)、[ffmpeg_master_download.py:449](file:///d:/DouyinLiveRecorder-dev/DouyinLiveRecorder/src/ffmpeg_master_download.py#L449)、[node_install.py:271](file:///d:/DouyinLiveRecorder-dev/DouyinLiveRecorder/src/node_install.py#L271)、[main.py:579-588](file:///d:/DouyinLiveRecorder-dev/DouyinLiveRecorder/main.py#L579-L588) | PATH 注入有的用导入期快照、有的用实时 `os.environ`，同仓两套口径，安装器先后执行时后者可能覆盖前者的修改。main.py 已改实时读取，建议三处安装器统一。 |
| C-2 | [ffmpeg_install.py:213-214](file:///d:/DouyinLiveRecorder-dev/DouyinLiveRecorder/src/ffmpeg_install.py#L213-L214)、[node_install.py:127-128](file:///d:/DouyinLiveRecorder-dev/DouyinLiveRecorder/src/node_install.py#L127-L128)；关联 [node_install.py:163-168](file:///d:/DouyinLiveRecorder-dev/DouyinLiveRecorder/src/node_install.py#L163-L168) | TOFU 旁路哈希文件直接 `write_text` 非原子，进程被杀可留下截断/空基准；且 node 侧读基准异常的分支 warning 后**放行**（与 ffmpeg/master 源 fail-closed 口径相反）。建议复用 `utils.atomic_write_text`，node 侧读取失败改为拒装。 |
| C-3 | [log_archive.py:179](file:///d:/DouyinLiveRecorder-dev/DouyinLiveRecorder/src/log_archive.py#L179)、[__init__.py:37](file:///d:/DouyinLiveRecorder-dev/DouyinLiveRecorder/src/__init__.py#L37)、[config_io.py:324-325](file:///d:/DouyinLiveRecorder-dev/DouyinLiveRecorder/src/config_io.py#L324-L325) | 三处环境布尔开关自造第三套字面量集合 `("1","true","yes")`，不认本仓规范支持的"是/on"等 token，用户按中文习惯设 `DOUYIN_DISABLE_LOG_ARCHIVE=是` 不生效。建议统一走 `src.config_bool.parse_config_bool`。 |
| C-4 | [ffmpeg_install.py:688](file:///d:/DouyinLiveRecorder-dev/DouyinLiveRecorder/src/ffmpeg_install.py#L688)；同型 [main.py:4550](file:///d:/DouyinLiveRecorder-dev/DouyinLiveRecorder/main.py#L4550) | `subprocess.run(..., text=True)` 未指定 `encoding/errors`，非英文 Windows 按系统 locale（GBK）解码 ffmpeg 输出，理论上存在 UnicodeDecodeError 风险（ffmpeg 版本头通常为 ASCII，未实际触发）。建议显式 `encoding="utf-8", errors="replace"`。 |
| C-5 | [node_install.py:137](file:///d:/DouyinLiveRecorder-dev/DouyinLiveRecorder/src/node_install.py#L137) | 每次版本升级都在 execute_dir 留下一个新的 `node-vX.Y.Z-*.zip.sha256`，无修剪逻辑（master 源有 `_prune_stale_master_baselines`）。建议写新删旧。 |
| C-6 | [utils.py:939-942](file:///d:/DouyinLiveRecorder-dev/DouyinLiveRecorder/src/utils.py#L939-L942) | 代理 URL 脱敏正则的凭据字符集排除 `@`，对密码含 `@` 的代理（如 `http://user:p@ss@host/`，proxy.py 用 rpartition 可以正确解析）只抹到一半，残留主机段可能泄露密码片段。建议凭据部分按 rpartition 贪婪匹配到最后一个 `@`。 |
| C-7 | [cookie_cache.py:92-101](file:///d:/DouyinLiveRecorder-dev/DouyinLiveRecorder/src/cookie_cache.py#L92-L101) | `get_cached` 只读查询仍按固定 DEFAULT_TTL（30 分钟）判活，忽略写入方传入的自定义短 TTL，可能把调用方认为已过期的凭据多返一段时间。建议 TTL 随条目存储。 |
| C-8 | [ffmpeg_install.py:87-88](file:///d:/DouyinLiveRecorder-dev/DouyinLiveRecorder/src/ffmpeg_install.py#L87-L88) | 注释称安装落点为 `execute_dir/ffmpeg/bin/ffmpeg.exe`，实际落点是 `execute_dir/ffmpeg/ffmpeg.exe`（362-366 行 copytree 目标）。陈旧注释误导排障，建议修正。 |
| C-9 | [ffmpeg_install.py:507-517](file:///d:/DouyinLiveRecorder-dev/DouyinLiveRecorder/src/ffmpeg_install.py#L507-L517)、[node_install.py:340-350](file:///d:/DouyinLiveRecorder-dev/DouyinLiveRecorder/src/node_install.py#L340-L350) | brew 安装分支的 `except subprocess.CalledProcessError` 是死分支：`subprocess.run` 未传 `check=True`，失败只返回非零 returncode、不抛该异常。建议改为判 returncode 或补 check=True。 |
| C-10 | [config_io.py:335-354](file:///d:/DouyinLiveRecorder-dev/DouyinLiveRecorder/src/config_io.py#L335-L354)、[390-400](file:///d:/DouyinLiveRecorder-dev/DouyinLiveRecorder/src/config_io.py#L390-L400) | ① 脱敏备份经 configparser 往返会丢失原注释与排版（与"行级更新保留注释"的口径不同），用户外发备份时可感知；② 轮转列表先 `os.listdir` 再逐个 `getmtime`，文件在窗口内被删会抛 OSError 并记整轮备份失败。建议 listdir 内对 getmtime 容错。 |
| C-11 | [utils.py:626-631](file:///d:/DouyinLiveRecorder-dev/DouyinLiveRecorder/src/utils.py#L626-L631)、[config_io.py:358-362](file:///d:/DouyinLiveRecorder-dev/DouyinLiveRecorder/src/config_io.py#L358-L362) | 含明文 Cookie 的 config.ini 在 Windows 上 `os.chmod(0o600)` 只切换只读位、不产生 ACL 隔离，同机其它账户仍可读。代码已注释知情，属纵深防御登记项；如需真正隔离应改用 icacls/DPAPI。 |

#### D. GUI / Web 前端 / 构建与运维

| 编号 | 位置 | 问题与建议 |
|---|---|---|
| D-1 | [web/app.js:1010-1019](file:///d:/DouyinLiveRecorder-dev/DouyinLiveRecorder/web/app.js#L1010-L1019) | 弹幕折叠计数 `m.dropped` 直接拼进 innerHTML 模板未过 `esc()`。当前后端契约该字段恒为 int，无可达注入路径，但破坏了"所有插值必转义"的不变量。建议 `esc(m.dropped)` 或 `Number(m.dropped)`。 |
| D-2 | [web/app.js:27-35](file:///d:/DouyinLiveRecorder-dev/DouyinLiveRecorder/web/app.js#L27-L35)、[144-156](file:///d:/DouyinLiveRecorder-dev/DouyinLiveRecorder/web/app.js#L144-L156) | sessionStorage 不可用时回退 localStorage，Bearer 令牌可能跨会话持久留存（XSS/共享浏览器场景扩大窗口）。属注释知情的兼容性取舍，建议回退路径缩短 TTL 或增加用户提示。 |
| D-3 | [scripts/smoke_test.py:274-328](file:///d:/DouyinLiveRecorder-dev/DouyinLiveRecorder/scripts/smoke_test.py#L274-L328) | HTML 冒烟报告把 `r["errors"]` 中的服务端响应内容与配置 `name` 未经 `html.escape` 直接拼进 HTML（CI/本地工具，非生产链路）。建议统一转义。 |
| D-4 | [scripts/patch_i18n_2026_09_12.py:23-27](file:///d:/DouyinLiveRecorder-dev/DouyinLiveRecorder/scripts/patch_i18n_2026_09_12.py#L23-L27)、[228](file:///d:/DouyinLiveRecorder-dev/DouyinLiveRecorder/scripts/patch_i18n_2026_09_12.py#L228) | 一次性补丁脚本硬编码 `D:/DouyinLiveRecorder-dev`（且指向父目录，路径本身就是错的），其它机器必失败；裸调 `python` 而非 `sys.executable`。该脚本已声明过期，建议直接删除。 |
| D-5 | [Dockerfile:21](file:///d:/DouyinLiveRecorder-dev/DouyinLiveRecorder/Dockerfile#L21)、[50](file:///d:/DouyinLiveRecorder-dev/DouyinLiveRecorder/Dockerfile#L50) | 基础镜像使用浮动标签 `python:3.14-slim-bookworm` 且 `apt-get upgrade -y` 未钉版本，构建可复现性弱（注释已用可复现性换安全补丁，属知情取舍）。建议择机按 digest 钉定基础镜像。 |
| D-6 | [.github/workflows/build-release.yml:227](file:///d:/DouyinLiveRecorder-dev/DouyinLiveRecorder/.github/workflows/build-release.yml#L227)、[413](file:///d:/DouyinLiveRecorder-dev/DouyinLiveRecorder/.github/workflows/build-release.yml#L413)、[529](file:///d:/DouyinLiveRecorder-dev/DouyinLiveRecorder/.github/workflows/build-release.yml#L529)；[ci.yml:179](file:///d:/DouyinLiveRecorder-dev/DouyinLiveRecorder/.github/workflows/ci.yml#L179)、[591](file:///d:/DouyinLiveRecorder-dev/DouyinLiveRecorder/.github/workflows/ci.yml#L591)；[trivy.yml:86](file:///d:/DouyinLiveRecorder-dev/DouyinLiveRecorder/.github/workflows/trivy.yml#L86) | 多个第三方 GitHub Action 使用浮动大版本标签（@v3/@v4 等），其中 `softprops/action-gh-release` 持 contents: write。trivy-action 已钉 SHA，建议全部第三方 Action 钉 commit SHA（发布链上的优先）。 |
| D-7 | [gui.py:2653-2708](file:///d:/DouyinLiveRecorder-dev/DouyinLiveRecorder/gui.py#L2653-L2708) | GUI 录制进程在 Popen 成功后、会话登记完成前的窗口内若抛异常，catch 块不保证终止子进程，可能留下无 UI 托管的录制进程。触发窗口极窄（Tk 回调瞬间销毁等）。建议异常路径无条件 `proc.kill()`。 |
| D-8 | [gui.py:2381-2384](file:///d:/DouyinLiveRecorder-dev/DouyinLiveRecorder/gui.py#L2381-L2384)；同型 [main.py:4803-4805](file:///d:/DouyinLiveRecorder-dev/DouyinLiveRecorder/main.py#L4803-L4805) | 自动新建空配置文件时直接 `open(path, "w")`，非原子（崩溃可留 0 字节文件，虽然两处语义本就是建空文件，影响很低）。建议复用 `atomic_write_text`。 |
| D-9 | [scripts/_ci_web_smoke.sh:44](file:///d:/DouyinLiveRecorder-dev/DouyinLiveRecorder/scripts/_ci_web_smoke.sh#L44) | 清理步骤 `pkill -f 'python web\.py'` 匹配串偏宽，共享 CI runner 上可能误杀同名进程。一次性容器内无实际风险，建议模式加项目路径锚定。 |

#### E. 主引擎注释/健壮性（不另行编号，记录备查）

- [main.py:4047](file:///d:/DouyinLiveRecorder-dev/DouyinLiveRecorder/main.py#L4047) 行内注释称 HTTPS 升级时"证书验证已在全局禁用"，与 [main.py:4089](file:///d:/DouyinLiveRecorder-dev/DouyinLiveRecorder/main.py#L4089) 实际按 `get_effective_ssl_verify(platform)` 逐平台裁决不符（注释陈旧，行为本身是文档化的设计取舍：开启 HTTPS 录制时拉流侧豁免证书、控制面恒严格）。
- [main.py:5233-5234](file:///d:/DouyinLiveRecorder-dev/DouyinLiveRecorder/main.py#L5233-L5234) `url.split("/")[2]` 对畸形 URL 可抛 IndexError，但外层逐行 try/except（5275 行）已捕获并带行内容记录，无崩溃风险，仅建议错误文案再细化。

---

## 四、已核查且值得肯定的安全与工程实践

本次审查同时验证了以下防线**真实有效**（均回源到代码，非仅看注释）：

1. **子进程注入面收敛**：全产品代码无 `shell=True / os.system / eval / pickle.load / yaml.load`；ffmpeg 一律 argv 列表启动（`-i`、`-http_proxy`、输出路径均为列表独立元素），用户自定义脚本经 `shlex.split` 且执行入口被 Web 危险键黑名单封禁；ffmpeg `-protocol_whitelist` 显式移除了 `file` 协议，流地址还有 `_is_recordable_url` 协议/控制字符/`-` 前缀注入白名单。
2. **Web 面板鉴权体系完整**：PBKDF2-HMAC-SHA256（200k 迭代、随机盐、迭代次数夹取防 CPU DoS）、256-bit Bearer + 改密全量吊销；登录限流双轨（per-IP 5 次 + 全局 40 次/300s）+ 免鉴权端点预算；Host 白名单与 Origin 白名单**两套独立判据**防 DNS 重绑定；Bearer 鉴权与 HTTP 方法无关；非幂等请求同源校验；CSP/X-Frame-Options/nosniff 齐全；非回环 + 无认证的每请求不变量与启动检查双保险；监听地址基准取自进程实际绑定而非可热改的配置值。
3. **SSRF 写入收口**：Web 房间/配置写入口统一过 ipaddress 语义判定（覆盖 inet_aton 缩写 IP、IPv6、CGNAT、云元数据、内部用途域名 + DNS 解析），scheme 白名单在 async_req/get_response_status 入口统一拦截。
4. **凭据保护**：日志全链路 `mask_credentials`（URL、异常文本、代理、房间名）；SMTP 强制 CRLF 头注入校验、STARTTLS/SMTP-over-TLS 共用 `create_default_context`（修复了历史上的 `_create_unverified_context` 问题）；配置读回显脱敏 + 敏感键空值/掩码拒绝写入 + 改认证两键强制复验口令。
5. **文件与供应链**：ZIP 解压统一过 Zip-Slip 校验 + 解压炸弹（单文件/总量/压缩比）三道闸；配置写入统一原子实现（mkstemp + fsync + os.replace + 权限回灌）；build_exe.py 对 ffmpeg/node 全部槽位 SHA256 钉定、macOS GPG 校验、发布前凭据脱敏断言；Docker 非 root 用户、NodeSource setup 脚本 SHA256 fail-closed；requirements/pyproject 对 urllib3/starlette/h2/protobuf 等记录了 CVE 驱动的下限。
6. **并发与资源治理**：ffmpeg 录制槽位 acquire 先于 Popen、看门狗（单调钟防时钟跳变、停滞/时长上限、三态产物观测区分"不可读"与"无产物"）、后处理固定容量线程池、零字节产物校验、HTTP 客户端按事件循环分桶 + 连接池收口、异步连接池登录态隔离。
7. **工程文化**：关键不变量普遍有 tests/ 回归锁（AST/行为断言），注释记录事故形态与判据，i18n 模板提取有门禁，依赖声明双写有集合一致性断言。

---

## 五、改进建议与修复优先级

### P0（立即修复，1 项）

- **S-1 Shopee 重定向凭据外泄/SSRF**：对齐小红书 SEV-2214 的落地页白名单 + 内网判定 + 跨源剥 Cookie。该链接受害者只需正常添加一个房间链接即触发，建议优先修复并补一条"恶意 Shopee 链接不向白名单外主机发送 Cookie"的回归测试。

### P1（本迭代内修复，9 项）

- M-1 探针重定向逐跳校验（stream_select 与 async_http 双侧同时改，避免再次分叉）；
- M-2 虎牙 Web 路径候选判据对齐 spider App 路径；
- M-3 四个平台 JSON 请求体改结构化构造；
- M-4 / M-5 / M-6 node 安装链三处（异常捕获、原子替换、zip 形态闸）；
- M-7 ffmpeg 安装原子切换；
- M-8 备份脱敏失败强制告警/不落明文；
- M-9 cookie 日志异常脱敏。

以上 9 项均属"同型修复已在别处落地、本处未对齐"或"注释承诺与代码不符"，修复模式在仓内均有现成参照，改动面小、回归测试可直接复用对照实现的测试。

### P2（择机迭代，38 项轻微）

- 优先处理有实际安全增益的：B-3（TLS SECLEVEL 按主机收敛）、B-1（IRC CRLF）、C-6（代理脱敏）、D-1（前端转义不变量）、D-6（Action SHA）；
- 其次是健壮性/可维护性类：A-2（SRT 块号）、A-7/A-8（句柄与超时）、C-1/C-2/C-3（安装器一致性）、D-4（删除过期脚本）；
- 剩余注释/风格/死代码类（A-3、C-8、C-9、E 组等）可结合日常重构顺手清理。

### 跨模块的长效建议

1. **建立"同型链路清单"门禁**：本次 4 个中等项（M-1/M-2/M-5/M-8）本质都是"防护在 A 链路落地、B 链路漂移"。建议把"短链重定向落地校验""候选有效性判据""安装器原子替换""备份脱敏"等抽象成共享函数后，增加"所有调用点必须经过共享函数"的 AST/ grep 门禁（仓内已有此类先例，如 check_annotations.py）。
2. **测试代码专项审查**：tests/ 约 4 万行未在本轮覆盖，建议下一轮专项检查测试中的替身/补丁是否可能掩盖生产缺陷（如 sync_http 注释里提到的 MagicMock 读替身曾导致死循环一类问题）。
3. **发布物签名**：Windows/macOS 可执行文件目前未做代码签名（build-release.yml 亦无此环节），SmartControl/Gatekeeper 会对最终用户产生拦截提示，建议纳入发布路线图。

---

## 六、总结性结论

DouyinLiveRecorder 的整体代码质量与安全水位在同类开源工具中属**明显偏高**的水平：架构分层清晰（平台分发表、纯函数命令构造、调度器/熔断器、录制状态机），历史安全问题大多经过多轮带回归锁的修复，开发者对"静默降级""凭据落日志""TOCTOU""跨事件循环资源泄漏"等隐蔽缺陷有成熟的防守方法论。本轮未发现可被远程匿名利用的 RCE、权限绕过或鉴权缺口类致命问题，Web 面板、子进程、压缩包、SMTP、Docker、CI 等高风险面均经核实防护到位。

本轮发现的问题集中在一个非常具体的形态上：**防护已在某条链路落地、但同构的孪生链路未对齐**——严重项 S-1（小红书已修、Shopee 未修）与多个中等项（虎牙 App/Web、ffmpeg/node、stream_select/async_http、cookie_cache 两个分支）均属此类。这类问题无法靠单点修复消灭，建议按 P0/P1 清单补齐后，以共享函数 + 调用点门禁的方式固化，防止未来再次分叉。38 项轻微问题以健壮性、日志诊断、安装器一致性与纵深防御加固为主，不影响当前版本的正常使用，可按 P2 排期消化。

综上：**当前版本可继续使用，但建议尽快完成 S-1 单点修复后再发布下一版本；P1 九项建议纳入最近一个迭代。**

---

## 附录：审查覆盖与核查记录

- 全部产品源码逐行通读：main.py、gui.py、web.py、msg_push.py、i18n.py、build_exe.py、src/ 全部 35 个产品模块、web/ 前端 3 文件、根 index.html、scripts/ 全部脚本、Dockerfile/compose/workflows/VBS。
- 关键发现复核方式：S-1（含 `_shopee_host_suffix` 实参推演 + 小红书对照实现双向核实）、M-1（派生跳防护边界与五个探针调用点逐一核实）、M-2（spider 1297-1323 对照）、M-3（百度/淘宝两处现场核实）、M-4/M-5（含 `src/__init__.py` 导入期调用链）、M-8/M-9（含同文件对照分支）均已回源读到原始代码行。
- 全仓危险模式检索结论：产品 Python 代码中无 `shell=True / os.system / pickle.load / yaml.load(` 命中；`verify=False` 无命中（仅注释文字）；JS 中的 `eval` 仅作用于 haixiu.js/x-bogus.js 内硬编码常量字符串与 `require()` 字面量，无外部输入流入。
- 未覆盖：tests/ 逐行评审、运行时动态 PoC、第三方库内部审计（依赖侧由 requirements 下限审计与 CI deps-audit 承担）。
