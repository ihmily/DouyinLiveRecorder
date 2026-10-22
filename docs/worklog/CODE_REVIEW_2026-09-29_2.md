# 全量源代码审查报告（CODE_REVIEW_2026-09-29_2）

- **审查日期**：2026-09-29
- **审查对象**：DouyinLiveRecorder 工作空间（`d:\DouyinLiveRecorder`）当前工作区全部自有源代码
- **审查方式**：逐文件人工通读 + 多代理并行只读审查 + 关键证据人工复核（复读源码 / grep / 运行时取证）
- **报告文件**：`docs/worklog/CODE_REVIEW_2026-09-29_2.md`（同日已有 `CODE_REVIEW_2026-09-29.md`，按命名规则顺延为 `_2`）
- **审查约束**：全程只读，未修改、未创建除本报告外的任何文件；未对网络与平台做真机请求

---

## 一、审查概述与背景

DouyinLiveRecorder 是一个支持 60+ 国内外直播平台的录制工具，包含 CLI 主程序（`main.py`）、Tkinter 桌面 GUI（`gui.py`）、Starlette Web 管理面板（`web.py` + `src/web_api.py` + `web/` 静态前端）、平台解析与弹幕采集层（`src/`）、打包脚本（`build_exe.py`）及约 100 个测试文件。

本次审查应要求对工作空间内**全部自有源代码**进行一次覆盖式安全与质量审查，目标是发现：安全漏洞、真实逻辑缺陷、并发与资源管理问题、跨平台兼容性问题、测试假绿/污染，以及可维护性风险，并为修复排序提供证据。

### 审查范围

| 区域 | 文件数 | 代表性文件（实际行数） |
|---|---:|---|
| 根目录入口 | 8 | [main.py](file:///d:/DouyinLiveRecorder/main.py)（5455）、[gui.py](file:///d:/DouyinLiveRecorder/gui.py)（4065）、[build_exe.py](file:///d:/DouyinLiveRecorder/build_exe.py)（1546）、[msg_push.py](file:///d:/DouyinLiveRecorder/msg_push.py)（575）、[i18n.py](file:///d:/DouyinLiveRecorder/i18n.py)（406）、[StopRecording.vbs](file:///d:/DouyinLiveRecorder/StopRecording.vbs)（422）、[web.py](file:///d:/DouyinLiveRecorder/web.py)（325）、[index.html](file:///d:/DouyinLiveRecorder/index.html)（279） |
| `src/` 核心模块 | 31 | [spider.py](file:///d:/DouyinLiveRecorder/src/spider.py)（6885）、[web_api.py](file:///d:/DouyinLiveRecorder/src/web_api.py)（1582）、[web_config.py](file:///d:/DouyinLiveRecorder/src/web_config.py)（1155）、[stream_select.py](file:///d:/DouyinLiveRecorder/src/stream_select.py)（1148）、[stream.py](file:///d:/DouyinLiveRecorder/src/stream.py)（1120）、[utils.py](file:///d:/DouyinLiveRecorder/src/utils.py)（845）等 |
| `src/platforms/` | 7 自有 + 1 生成 | douyin/bilibili/douyu/huya/twitch、`_tars.py`、`_xbogus.py` |
| `src/javascript/` | 4 自有 | haixiu/liveme/migu/x-bogus（`crypto-js.min.js` 为第三方，未审） |
| `web/` 前端 | 4 | app.js（1868）、motion.js、index.html、style.css |
| `scripts/` | 14 | standalone、run_gates、check_*、smoke_test、CI shell 等 |
| `tests/` | 105 | 约 5.1 万行 Python 与 Node 测试 |
| 合计 | 约 170 个文件 | 生产代码约 4 万行 + 测试约 5.1 万行 |

**明确排除**：第三方依赖（`.venv`/site-packages）、`uv.lock`、构建产物、`src/proto/douyin_pb2.py`（protoc 生成）、`src/javascript/crypto-js.min.js`、文档（`docs/`、`README*`）、CI 配置（仅在核对接线时只读引用）。

### 方法与可信度控制

1. 主入口与全部 `src/` 核心文件逐行通读；`gui.py`、`spider.py`、`tests/`、`scripts/`、前端等大文件由独立审查代理逐行通读并给出**文件绝对路径 + 起止行号 + 代码原文摘录**。
2. 对全部「严重」与绝大多数「中等」发现，审查负责人均**复读源码二次核验**；一条测试严重项以 `pytest --collect-only` 实际运行取证（20.55 秒、退出码 5）；一条 i18n 缺陷以 Python 3.14 实际复现。
3. 无法在当前环境实证、依赖外部条件的结论一律标注「待核实」，不做断言式表述。
4. 已系统性排除假阳性：无括号多异常写法 `except A, B:` 经实测确认为 Python 3.14 PEP 758 合法语法（`pyproject.toml` 声明 `requires-python = ">=3.14"`），全仓此类写法均不计为缺陷。

---

## 二、问题汇总

| 严重程度 | 数量 | 说明 |
|---|---:|---|
| 严重 | 2 | 1 个可导致凭据外泄/内网请求的服务端校验缺口；1 个确定性污染全量测试收集的真机脚本 |
| 中等 | 32 个编号 / 34 个独立问题 | 安全收口缺口 7、真实逻辑缺陷 10、GUI/前端 6、测试假绿与污染 8、脚本 2（M-31、M-32 两个编号各含 2 个子项） |
| 轻微 | 59 | 第五节表格 51 行（部分行归并多条同组问题）+ 测试侧归并 8 条；纵深防御、健壮性、跨平台、可访问性、死代码类 |
| **合计** | **约 95 个独立问题** | 按编号去重后的估算口径；归并项均在条目中列明子项 |

整体判断：**工程安全基线在同类开源项目中属上游水平**——生产侧无 `shell=True`/`eval`/`pickle`/`verify=False`，Web 面板具备 PBKDF2 口令哈希、Bearer 令牌、登录限流、Host/Origin 双名单、SSRF 写入校验、危险键黑名单、安全响应头等成体系防护；下载链有 SHA256/GPG fail-closed 校验；ffmpeg 调用全部参数化。主要风险集中在**一条与已修复的小红书同型但漏修的 Shopee 短链链路**、**少量响应决定 URL 的重定向收口**、**个别凭据日志脱敏缺口**，以及**测试体系中 3 处确凿的假绿/污染**。

---

## 三、严重问题（2 项）

### S-1　Shopee 短链重定向落地页未校验 host：Cookie 外泄 + 内网 SSRF

- **位置**：[src/spider.py L6033-L6057](file:///d:/DouyinLiveRecorder/src/spider.py#L6033-L6057)、[L6100-L6102](file:///d:/DouyinLiveRecorder/src/spider.py#L6100-L6102)；后缀切分 [L112-L120](file:///d:/DouyinLiveRecorder/src/spider.py#L112-L120)
- **已核验代码**：

```python
# L6033-6037：短链（.shp.ee 等）的重定向结果直接替换 url，无任何 host 校验
if "live.shopee" not in url and "uid" not in url:
    url_result = await async_req(url, proxy_addr=proxy_addr, headers=headers, redirect_url=True, abroad=True)
    # 重定向失败（空响应）时保留原 URL 继续解析，避免后续 split 越界
    if isinstance(url_result, str) and url_result:
        url = url_result
...
host_suffix = _shopee_host_suffix(url)          # 裸字符串切分
api_host = f"https://live.shopee.{host_suffix}"  # 落地页 host 决定后续 API 域名
...
# L6056-6057 / L6100-6102：对攻击者可控的 api_host 发新请求，headers 中带用户 Cookie
json_str = await async_req(f"{api_host}/api/v1/shop_page/live/ongoing?uid={uid}", ..., headers=headers, ...)
```

- **问题与影响**：
  1. 重定向落地页完全由响应决定，代码未做域族白名单与内网判定。`_shopee_host_suffix` 基于字符串切分而非 `urlparse().hostname`，恶意落地页 `https://live.shopee.evil.com/...` 会得到 `api_host=https://live.shopee.evil.com`；`https://live.shopee.sg@127.0.0.1/...` 形态则把 userinfo 原样保留，实际连接 127.0.0.1（该绕过已经 Python 实测成立）。
  2. 跳转后的二次请求重新携带含 `Cookie` 的 `headers`（[L6026-L6027](file:///d:/DouyinLiveRecorder/src/spider.py#L6026-L6027)），可把用户 Shopee 登录态送至任意主机；无 Cookie 时同样构成对内网/回环/云元数据地址（169.254.169.254 等）的服务端请求。
  3. **同型漏洞已在小红书链路修复并定级 SEV-2214**：[L2262-L2275](file:///d:/DouyinLiveRecorder/src/spider.py#L2262-L2275) 与 [L2334-L2370](file:///d:/DouyinLiveRecorder/src/spider.py#L2334-L2370) 采用「域族后缀白名单（精确/子域）+ `web_config._host_internal_reason` 内网判定」双闸；Shopee 是同一信任边界上唯一漏修的解析器。
- **前置条件**：受害者添加攻击者构造（或短链域名被劫持）的 Shopee 分享链接。准入白名单（`main.py` PLATFORM_HOST 含 `.shp.ee`）只校验短链宿主，无法约束跳转落地页。
- **修复建议**：直接复用小红书模式——落地页必须同时通过 Shopee 域族白名单（用 `urlparse().hostname()` 做精确或 `.` 后缀判定，拒绝含 `@` 的 host）与 `_host_internal_reason` 内网判定；任一不过则丢弃跳转、保留原始 URL 且后续请求剥离 Cookie。

### S-2　`test_twitch_live_collector.py` 无 `__main__` 守卫：pytest 收集期即连真机、阻塞 20 秒、清空目录、可杀掉整个测试会话

- **位置**：[tests/test_twitch_live_collector.py L19-L83](file:///d:/DouyinLiveRecorder/tests/test_twitch_live_collector.py#L19-L83)（执行体全部位于模块级，无守卫）
- **已核验事实**：
  1. `pyproject.toml` 配置 `python_files = ["test_*.py"]`、`testpaths = ["tests"]`，该文件在**收集阶段被 import**，模块级语句随即执行：真实 Twitch IRC 连接（[L53](file:///d:/DouyinLiveRecorder/tests/test_twitch_live_collector.py#L53)）、`time.sleep(20)`（[L57](file:///d:/DouyinLiveRecorder/tests/test_twitch_live_collector.py#L57)）、清空 `tests/_out_live`（[L42-L43](file:///d:/DouyinLiveRecorder/tests/test_twitch_live_collector.py#L42-L43)）、失败路径 `sys.exit(1)`（[L31](file:///d:/DouyinLiveRecorder/tests/test_twitch_live_collector.py#L31)、[L79](file:///d:/DouyinLiveRecorder/tests/test_twitch_live_collector.py#L79)）。
  2. 同目录 4 个兄弟真机脚本（bili/douyin/douyu/huya_live_collector）**全部**有 `if __name__ == "__main__":` 守卫（grep 实证），本文件是唯一漏网者。
  3. 运行时取证：`python -m pytest tests/test_twitch_live_collector.py --collect-only -q` 实际耗时 **20.55 秒**、`no tests collected`、退出码 5——证明收集期确实执行了完整真机流程。
- **影响**：任何全量 pytest 运行（含 CI 收集阶段）都被确定性附加 20 秒真机延迟；离线/CI 环境连接失败走 `sys.exit(1)` 可直接终止收集；收集期还会删除其它真机脚本的产物目录。
- **修复建议**：把 L19 起的执行体整体移入 `def main()` 并加 `if __name__ == "__main__": main()`，与其余 4 个 live collector 同构。

---

## 四、中等问题（32 项）

### A. 安全收口缺口（7 项）

#### M-1　流地址探针对 HTTP 重定向不做逐跳内网复检（SSRF 绕过）

- **位置**：[src/async_http.py L535-L570](file:///d:/DouyinLiveRecorder/src/async_http.py#L535-L570)；校验函数 [L471-L505](file:///d:/DouyinLiveRecorder/src/async_http.py#L471-L505)
- **证据**：内网/保留目标判定只作用于**初始 URL**（L535-546），而 HEAD 与兜底 Range-GET 均 `follow_redirects=True`（L558、L569），httpx 跟随 3xx 时不再经过该校验。被攻陷或被 MITM 的平台响应可先返回公网 URL（通过校验）再 302 到 `http://127.0.0.1:6379/`、`http://169.254.169.254/`，探针照样访问内网，并把跳转后响应的 status_code/content-type 写入 debug 日志（内网端口观测口）。`async_req` 各分支同样全线跟随重定向。
- **修复建议**：用 `event_hooks={"response": ...}` 对每一跳 `response.url` 复用 `_internal_stream_target_reason` 复检，命中即停止跟随并判失败。DNS 重绑定窗口（校验与连接之间）无法在本层消除，建议注释登记为残余风险。

#### M-2　`sync_req` 缺少 URL scheme 白名单，`file://` 可读本地文件

- **位置**：[src/sync_http.py L274-L304](file:///d:/DouyinLiveRecorder/src/sync_http.py#L274-L304)
- **证据**：全函数无 `utils.is_safe_http_url` 入口（async 侧在 [async_http.py L348-L355](file:///d:/DouyinLiveRecorder/src/async_http.py) 有该防线），urllib opener 默认注册 FileHandler，`sync_req("file:///etc/passwd")` 会把本地文件作为响应体返回；默认重定向处理器也不限制 `http→file` 跨 scheme 跳转。已核实该模块**当前无生产调用方**（仅测试引用），属潜在缺口，但作为公开 API 接线即暴露。
- **修复建议**：函数入口与 async 侧对齐 scheme 白名单；构造 opener 时显式剔除 FileHandler/FTPHandler。

#### M-3　PandaTV/WinkTV 私有房密码 `pwd` 随原始 URL 写入异常日志

- **位置**：[src/spider.py L3195-L3201](file:///d:/DouyinLiveRecorder/src/spider.py#L3195-L3201)、[L3357-L3364](file:///d:/DouyinLiveRecorder/src/spider.py#L3357-L3364)
- **证据**：`raise RuntimeError(f"{url} ...")` 中 `url` 含 `?pwd=房间密码`（pwd 在 [utils.py](file:///d:/DouyinLiveRecorder/src/utils.py) 的脱敏键名表内），而 `@trace_error_decorator` 落日志时不过脱敏，受限私有房触发即把密码明文写入轮转日志文件。同类「原始 URL 直接进异常消息」还见于 spider.py L637/L822（抖音）、L4138（TwitCasting）、L4364（微博），敏感度较低但同口径。
- **修复建议**：所有进 raise/日志的 URL 统一过 `utils.mask_credentials(url)`，或在装饰器落日志前统一脱敏。

#### M-4　`login_popkontv` 异常文本未脱敏，可泄露代理账号密码

- **位置**：[src/spider.py L3757-L3782](file:///d:/DouyinLiveRecorder/src/spider.py#L3757-L3782)
- **证据**：这是全文件唯一绕过 `async_req` 的生产 httpx 请求；宽 `except Exception as e: logger.error(...{e}...)` 把代理连接类异常原文落日志。`async_req` 已在 [async_http.py L452-L466](file:///d:/DouyinLiveRecorder/src/async_http.py) 专门对异常文本脱敏（httpx/urllib3 异常必然内嵌含 `user:pass@` 的代理 URL），此处漏网。
- **修复建议**：`e=utils.mask_credentials(str(e))`，与 async_req 同口径。

#### M-5　录后自定义脚本命令原文（可能含凭据）写入日志；超时后第二次 `communicate()` 无超时

- **位置**：[src/notify.py L104-L143](file:///d:/DouyinLiveRecorder/src/notify.py#L104-L143)
- **证据**：超时、无执行权限、OSError、ValueError 四条分支都把**整条命令原文**记入 `logs/`（L110-116、L124-143）。用户脚本常内嵌 rclone token、curl 的 Authorization、数据库口令。另 L108-109 超时 `process.kill()` 只杀直接子进程，孙进程继承管道句柄时第二次无超时的 `communicate()` 可永久挂住录后钩子线程。
- **修复建议**：日志中的 command/e 过 `utils.mask_credentials`；第二次 communicate 加超时，POSIX 用 `start_new_session`+`killpg`、Windows 用 `taskkill /T` 杀进程树。

#### M-6　StopRecording.vbs 按通用脚本名匹配 python 进程，可误杀无关进程树

- **位置**：[StopRecording.vbs L309-L324](file:///d:/DouyinLiveRecorder/StopRecording.vbs#L309-L324)（终止动作 `taskkill /f /t /pid` 在 [L386](file:///d:/DouyinLiveRecorder/StopRecording.vbs#L386)）
- **证据（已核验）**：在整条命令行任意位置子串匹配 `main.py|gui.py|web.py`，前一字符为 `\`、`/`、空格或引号即判定为本录制器进程。`python D:\其它项目\main.py`、`python some_tool.py --config main.py` 均命中，随后强制连带杀整个进程树；确认框「仅结束本程序相关进程」的承诺在该情形下不成立。
- **修复建议**：把入口脚本路径与程序安装目录（appDir）或 venv/可执行文件路径锚定；至少在确认文案中披露该匹配面。

#### M-7　migu.js 运行时下载并实例化未做内容钉定的远端 WASM（已知情的架构性残余风险）

- **位置**：[src/javascript/migu.js L240-L253](file:///d:/DouyinLiveRecorder/src/javascript/migu.js#L240-L253)；护栏 [L42-L93](file:///d:/DouyinLiveRecorder/src/javascript/migu.js#L42-L93)
- **证据**：被 SHA256 钉定的只有胶水脚本（且默认仅告警，`DLR_JS_STRICT_HASH=1` 才阻断），真正执行签名算法的 wasm 本体与版本号均取自远端。现有 https + 主机白名单 + 魔数/版本/体积/导出表校验挡不住同域精细投毒；wasm 无 fs/net 导入，影响上限为签名进程的 CPU/内存（外层 30s 超时）。文件注释已书面知情并定性为「等价执行远端字节码」。
- **修复建议**：中期对 wasm 做跟版 SRI（下载后比对固定 hash 再 instantiate），或把咪咕签名移出录制进程到低权沙箱；短期给 fetch 加 `AbortSignal.timeout()`。

### B. 真实逻辑缺陷（10 项）

#### M-8　快手 did / B站 buvid 进程级缓存快路不判 proxy，跨代理出口串用设备指纹

- **位置**：[src/spider.py L212-L241](file:///d:/DouyinLiveRecorder/src/spider.py#L212-L241)（快路）、[L2180-L2211](file:///d:/DouyinLiveRecorder/src/spider.py#L2180-L2211)
- **证据**：下层 singleflight 键含 proxy、写入侧也记录了 `_cached_*_proxy`，但模块全局快路只判非空 + TTL。代理 A 获取的 did/buvid3 在 TTL 内被代理 B 的房间直接复用——与 [ttwid.py L60-L113](file:///d:/DouyinLiveRecorder/src/ttwid.py) MIN-2220 已修的是同一个 bug，此处两份缓存仍是旧形态，会提高风控概率、导致弹幕 AUTH 软拒绝。
- **修复建议**：快路增加 proxy 一致性判定，不匹配则下沉到按 proxy 分桶的 singleflight。

#### M-9　`anchor_name` 可为 `None` 并向下游蔓延，`clean_name(None)` 崩溃

- **位置**：[src/spider.py L640](file:///d:/DouyinLiveRecorder/src/spider.py#L640)、[L825](file:///d:/DouyinLiveRecorder/src/spider.py#L825)、[L1082-L1084](file:///d:/DouyinLiveRecorder/src/spider.py#L1082-L1084)、[L1278](file:///d:/DouyinLiveRecorder/src/spider.py#L1278)；崩溃点 [src/stream_select.py L58-L59](file:///d:/DouyinLiveRecorder/src/stream_select.py#L58-L59)
- **证据（已核验）**：`dict.get("nickname")`/`.get("nick")` 只挡键缺失，平台显式返回 `"nickname": null` 时结果为 None 并入结果 dict；`clean_name` 首行 `input_text.strip()` 对 None 抛 AttributeError（`main.py:3822` 调用），整轮解析被外层 except 兜成「获取失败」。文件内新代码已统一用 `_dig_str`，这四处是漏网点（网易 CC L3086-L3091 同型）。
- **修复建议**：四处统一改 `_dig_str(...)` 或 `v if isinstance(v, str) else ""`。

#### M-10　TwitCasting 受限房登录回退分支不可达（异常类型不匹配）

- **位置**：[src/spider.py L4144-L4154](file:///d:/DouyinLiveRecorder/src/spider.py#L4144-L4154) 与 [L4184-L4201](file:///d:/DouyinLiveRecorder/src/spider.py#L4184-L4201)
- **证据**：解析失败显式 `raise ValueError("Failed to parse page data")`，而回退登录只 `except AttributeError`——该异常在 try 块内不存在抛出路径，注释承诺的「解析失败→登录重试」自愈逻辑是死分支，页面结构变化时直接判未开播。
- **修复建议**：改为 `except (AttributeError, ValueError):` 并补回归测试。

#### M-11　TikTok 仅有 HLS（或 HLS 档位更多）时，用户选择的画质被强制钳回首档

- **位置**：[src/stream.py L652-L658](file:///d:/DouyinLiveRecorder/src/stream.py#L652-L658)（已核验）
- **证据**：

```python
video_quality, quality_index = get_quality_index(video_quality)
quality_index = min(quality_index, len(flv_url_list) - 1) if flv_url_list else 0   # 先被 FLV 列表钳
m3u8_quality_index = min(quality_index, len(m3u8_url_list) - 1) if m3u8_url_list else 0  # 复用了被钳后的值
```

HLS-only 房间 `quality_index` 被无条件置 0，用户选任何档位都拉 OD 最高档；`actual_quality` 回采 OD 后降级告警永不触发——「选流畅实拉原画」且无提示，浪费带宽。同文件抖音分支（L524-527）两个列表独立钳制，可对照。
- **修复建议**：保留原始索引，HLS 与 FLV 分别基于原始值钳制。

#### M-12　弹幕平台列表分割后未做 `strip`，含空格输入时弹幕功能静默失效

- **位置**：[main.py L4947-L4950](file:///d:/DouyinLiveRecorder/main.py#L4947-L4950)；匹配点 [main.py L1120](file:///d:/DouyinLiveRecorder/main.py#L1120)（已核验）
- **证据**：`danmaku_platforms = danmaku_platforms_str.replace("，", ",").split(",")` 无 `strip()`，而同文件 HLS 排除列表（L4853-4857）有 strip。用户在面板/GUI 输入常见的 `"斗鱼直播, B站直播"` 会产生 `" B站直播"`，`platform in danmaku_platforms` 恒不命中，该平台弹幕被静默关闭。
- **修复建议**：与 HLS 列表同口径改为列表推导 `[p.strip() for p in ... if p.strip()]`。

#### M-13　B站弹幕多 host 轮换时，首个 host 重连耗尽即上报「房间关闭」假事件

- **位置**：[src/platforms/bilibili.py L98-L118](file:///d:/DouyinLiveRecorder/src/platforms/bilibili.py#L98-L118)（已核验）；关闭回调在 ws_client / collector 侧
- **证据**：每个候选 host 各建一个 `WsClient` 且共享 `on_close=self._on_close`。host[0] 耗尽 2 次重连时，关闭回调（`hub.room_closed`，原因「重连超过最大次数」）先发出，而 `start()` 随后继续尝试 host[1]；host[1] 成功后又报已连接。监控页出现「假关闭→重连」闪烁与误导性落盘，且一次性保护是每实例的，挡不住跨实例重复上报。代码同时传了 `backup_url`，两套轮换机制重复。
- **修复建议**：把 host 轮换下沉到单个 WsClient 内部（与 backup_url 合并），或给关闭回调加「仍有候选 host 未尝试则不上报」闸门，全部失败后只回调一次。

#### M-14　GUI 画质监控页正则全部硬编码中文，切换非中文语言后功能静默失效

- **位置**：[gui.py L1109](file:///d:/DouyinLiveRecorder/gui.py#L1109)、[L1115](file:///d:/DouyinLiveRecorder/gui.py#L1115)、[L3310-L3314](file:///d:/DouyinLiveRecorder/gui.py#L3310-L3314)（已核验）
- **证据**：`画质降级：设置 … 实际 …`、`正在录制中`、`没有正在录制` 等模式串硬编码中文，而被解析的子进程输出全部经 `i18n.tr` 翻译（降级告警源 [main.py L4120-L4130](file:///d:/DouyinLiveRecorder/main.py#L4120-L4130)，状态行源 `src/recorder_status.py`）。用户经 GUI 语言菜单选英文并重启录制后，录制中行、降级告警、空态清除全部匹配失败，画质监控页静默停摆。
- **修复建议**：不要以自然语言作为协议——子进程对这些状态输出稳定的结构化标记（固定 tag/JSON 行），GUI 按标记解析；或启动子进程时固定其输出语言。

#### M-15　弹幕监控 `after` 自续期链无异常防护，一次转换异常即导致整页永久停止刷新

- **位置**：[gui.py L3519-L3522](file:///d:/DouyinLiveRecorder/gui.py#L3519-L3522)（续期注册在回调尾部）；异常点 [L3609-L3615](file:///d:/DouyinLiveRecorder/gui.py#L3609-L3615)
- **证据**：Tkinter `after` 回调抛出未捕获异常时，尾部的下一次 `after` 不会注册，定时链永久断裂且无自动恢复。触发源真实存在：`float(m.get("ts", 0.0))` 遇 `null` 抛 TypeError（文件头注释 L59-61 记录过该事故；启动时还会回放旧 JSONL 末尾 64KB，历史脏记录可达），锁外控件重建遇 TclError 同理。同型结构还见于状态刷新（L3667-L3672）与日志 flush（L3132-L3184）。
- **修复建议**：续期移入 `try/finally` 无条件重排；ts 等字段做 None/非数值容错。

#### M-16　「停止录制」与「彻底退出」可并发操作同一子进程，交叉篡改进程级控制台状态

- **位置**：[gui.py L3730-L3744](file:///d:/DouyinLiveRecorder/gui.py#L3730-L3744)（退出不检查停止中状态）；停止线程 [L2993-L3035](file:///d:/DouyinLiveRecorder/gui.py#L2993-L3035)；控制台附着 [L1087-L1100](file:///d:/DouyinLiveRecorder/gui.py#L1087-L1100)
- **证据**：停止流程后台最长运行 15 秒，期间托盘/侧栏「退出」仍可用，两个线程会对同一 pid 交叉执行 `FreeConsole→AttachConsole→GenerateConsoleCtrlEvent→FreeConsole`（控制台附着是进程全局状态），CTRL_BREAK 可能错投/丢失，最坏退化为 taskkill 硬杀，失去子进程 safe_exit 优雅清理 ffmpeg 的机会。
- **修复建议**：用单飞锁串行化停止与退出（退出时复用正在进行的停止线程，完成后再收尾）。

#### M-17　GUI tail 线程一条事件的类型转换异常会丢弃同批后续所有事件并静默卡顿

- **位置**：[gui.py L3451-L3464](file:///d:/DouyinLiveRecorder/gui.py#L3451-L3464)；转换点 [L3478](file:///d:/DouyinLiveRecorder/gui.py#L3478)、[L3512-L3515](file:///d:/DouyinLiveRecorder/gui.py#L3512-L3515)
- **证据**：`json.loads` 单独有防护，但 `_danmaku_dispatch` 内 `float()/int()` 无逐事件防护；一条 stats/conn 脏事件从 for 循环抛到最外层 `except Exception: time.sleep(1.0)`，offset 已推进，同 chunk 后续完好事件全部丢失且无任何日志。
- **修复建议**：try/except 下沉到每条事件（坏条 continue），最外层异常至少 warning 留痕。

### C. Web/入口/i18n（6 项）

#### M-18　Web 安全拒绝启动发生在隐藏控制台之后，拒绝信息用户完全看不到

- **位置**：[web.py L199-L218](file:///d:/DouyinLiveRecorder/web.py#L199-L218)（已核验）
- **证据**：`web_show_console=false` 时 L200 已隐藏窗口并重定向 stdout/stderr 到日志文件，L211-218 的「未启用认证不允许监听非回环地址」拒绝文案与 `sys.exit(1)` 才执行。用户看到的是「控制台一闪、面板起不来」，必须翻日志才能知道是安全拦截；与 L204-206 注释自称的「拒绝即零副作用退出」矛盾。
- **修复建议**：把不变量检查整体上移到 `_enter_background_mode` 之前。

#### M-19　`i18n.tr()` 注释承诺「永不抛」，但 AttributeError/TypeError 未捕获

- **位置**：[i18n.py L397-L406](file:///d:/DouyinLiveRecorder/i18n.py#L397-L406)（已核验）
- **证据**：两层 except 仅列 `KeyError, IndexError, ValueError`。Python 3.14.7 实测：`tr("{x.y}", x=None)` 抛 AttributeError、`tr("{x:d}", x=None)` 抛 TypeError。tr 大量用于 except 分支，译者目录写出此类占位符且值为 None 时二次异常会顶掉原始异常。
- **修复建议**：两层 except 均扩为 `(KeyError, IndexError, ValueError, AttributeError, TypeError)`。

#### M-20　（待核实）冻结环境下 `_should_translate` 的路径前缀判定可能对所有 print 失效

- **位置**：[i18n.py L189-L197](file:///d:/DouyinLiveRecorder/i18n.py#L189-L197)、[L370-L375](file:///d:/DouyinLiveRecorder/i18n.py#L370-L375)
- **证据与待核实点**：`builtins.print` 被替换为 translated_print 后是否翻译取决于调用栈 `co_filename` 是否以源码目录为前缀；PyInstaller 冻结后 PYZ 内 code 对象通常保留**构建机**源码路径，与运行期 `_MEIPASS` 不构成前缀关系，可能导致打包版所有 print 输出不翻译（同文件 locale_path 有专门冻结探测、此处没有，增加了疑点）。未做打包实测，标待核实。另 `startswith` 未加分隔符边界（`DouyinLiveRecorderX` 同级目录误判）。
- **修复建议**：冻结环境把 `sys._MEIPASS`/exe 目录纳入允许根并补 `os.sep` 边界；用 PyInstaller 实包切 en_US 验证。

#### M-21　前端三条轮询链存在「停止在途请求→立即重启」竞态，可产生无法回收的重复定时器链

- **位置**：[web/app.js L735-L786](file:///d:/DouyinLiveRecorder/web/app.js#L735-L786)（SSE）、[L959-L976](file:///d:/DouyinLiveRecorder/web/app.js#L959-L976)（日志）、[L981-L998](file:///d:/DouyinLiveRecorder/web/app.js#L981-L998)（弹幕）
- **证据**：停止函数只能取消已排期的定时器，取消不了在途 fetch；在途请求落地后仅检查布尔标志即重新排期。快速切换标签页/视图使旧请求落地后再挂一条轮询链，模块只跟踪一个 timer id，旧链失联并持续发请求（状态接口超时最长 10 秒，触发窗口真实存在），直到下次完整 stop 才自愈。
- **修复建议**：引入单调递增 generation token，在途回调比对代次；或重启时 `AbortController.abort()` 在途请求。

#### M-22　修改认证配置用 `window.prompt` 明文采集复验口令，且该口令被附加到本次保存的后续所有 PUT

- **位置**：[web/app.js L1498-L1540](file:///d:/DouyinLiveRecorder/web/app.js#L1498-L1540)
- **证据**：prompt 输入框明文回显（面板唯一非 password 形态的口令采集）；`authReauth` 是循环外变量，一旦在认证两行被赋值，之后每个有改动的普通配置键 PUT 体都带 `reauth_password`，扩大口令暴露面（代理日志/浏览器扩展可记录）。
- **修复建议**：用 `type="password"` 自定义小弹窗；reauth 仅在待提交集合含两个认证键时随对应请求携带一次。

#### M-23　弹幕折叠计数 `m.dropped` 未经转义直接拼进 innerHTML

- **位置**：[web/app.js L1016](file:///d:/DouyinLiveRecorder/web/app.js#L1016)
- **证据**：同函数 user/room/text 全部过 `esc()`，唯独 dropped 裸插值。后端当前写 int（[danmaku_monitor.py L554-L557](file:///d:/DouyinLiveRecorder/src/danmaku_monitor.py)），现网不可利用，但违反该文件自定义的「拼接路径一律转义」不变量，契约一变即存储型注入点。
- **修复建议**：`parseInt(m.dropped, 10)` 或过 `esc()`。

### D. 测试假绿与污染（7 项）

#### M-24　`test_danmaku_monitor.py` tail 用例把停止信号发到了错误的 Event，目标行为实际未验证

- **位置**：[tests/test_danmaku_monitor.py L526](file:///d:/DouyinLiveRecorder/tests/test_danmaku_monitor.py#L526)、[L553-L554](file:///d:/DouyinLiveRecorder/tests/test_danmaku_monitor.py#L553-L554)（已核验）
- **证据**：线程以匿名 `threading.Event()` 启动（生产签名 `_danmaku_tail_loop(self, stop_event)` 只认传入的 Event，[gui.py L3416-L3421](file:///d:/DouyinLiveRecorder/gui.py#L3416-L3421)），用例末尾 set 的却是另一个 `stub._danmaku_tail_stop`，`join(timeout=3)` 必然等满且无 `assert not t.is_alive()`——守护线程残留至进程退出，「轮转后能停」从未被验证。
- **修复建议**：保存传入的 Event 引用并对它 set，join 后断言线程已退出。

#### M-25　`test_huya_danmaku.py` 直接赋值 `spider.async_req` 且不还原，污染整个 pytest 进程

- **位置**：[tests/test_huya_danmaku.py L91-L104](file:///d:/DouyinLiveRecorder/tests/test_huya_danmaku.py#L91-L104)（已核验 L95）
- **证据**：`spider.async_req = fake_async_req` 无 monkeypatch/undo。假协程签名仅 `(url, proxy_addr, headers)`，同会话后续任何带 `data=` 的 spider 调用都会 TypeError 或拿到虎牙固定 JSON。同仓其余用例统一用 monkeypatch/setattr shim。
- **修复建议**：改用 `monkeypatch.setattr(spider, "async_req", fake)`。

#### M-26　前端门禁「后端不得强复验」锁已成假绿：生产代码已实现强复验，用例钉死旧字面量空过

- **位置**：[tests/frontend/test_regression_2026_09_22_gates.mjs L707-L727](file:///d:/DouyinLiveRecorder/tests/frontend/test_regression_2026_09_22_gates.mjs#L707-L727)（已核验）
- **证据**：两条 `doesNotMatch` 钉的是旧形状 `verify_web_password(_reauth, _stored)` 与旧文案「修改认证配置需复验当前口令」；生产实现（[src/web_api.py L1205-L1214](file:///d:/DouyinLiveRecorder/src/web_api.py#L1205-L1214)）的实际形状是 `verify_web_password(_reauth, _stored_pwd)`、文案是「修改 Web 认证配置必须复验…」，两个断言因字面不一致而**空洞成立**。Python 侧 `test_regression_2026_09_22_web_g.py` 锁的恰是相反新契约，两侧互相矛盾。实测 `node --test` 32/32 全绿——安全边界锁给出错误信心。
- **修复建议**：删除该条过期用例或改为与新契约一致的正向行为锁（行为已由 Python E2E 覆盖）。

#### M-27　4 处用例直接 patch 进程全局 `os.remove`/`os.rename`，窗口内影响其他线程

- **位置**：[tests/test_config_io_backup.py L39](file:///d:/DouyinLiveRecorder/tests/test_config_io_backup.py#L39)、[L66](file:///d:/DouyinLiveRecorder/tests/test_config_io_backup.py#L66)；[tests/test_log_archive.py L109](file:///d:/DouyinLiveRecorder/tests/test_log_archive.py#L109)；[tests/test_anchor_rename.py L254](file:///d:/DouyinLiveRecorder/tests/test_anchor_rename.py#L254)
- **证据**：monkeypatch 解析到的是全进程唯一 os 模块本体，而非被测模块命名空间；窗口内 loguru/其他后台线程的删除/重命名被替换（其中 L39 的替身把删除变 no-op）。仓库 AGENTS 约定为「浅拷贝 shim 后替换模块命名空间」。
- **修复建议**：统一按 shim 约定 patch 被测模块自己的 os 引用。

#### M-28　`tests/frontend/test_motion.mjs`（5 个用例）缺少 Python 包装，不进任何 CI 门禁

- **位置**：[tests/frontend/test_motion.mjs](file:///d:/DouyinLiveRecorder/tests/frontend/test_motion.mjs)；CI 入口 [.github/workflows/ci.yml L540-L567](file:///d:/DouyinLiveRecorder/.github/workflows/ci.yml#L540-L567)（只点名另两个 mjs 的包装）
- **证据**：全仓 grep 确认无任何 .py 引用 test_motion.mjs；node `--test` 指定文件不会发现同级其他文件。motion.js 的降级/清理回归锁在正常 CI 中从不执行。
- **修复建议**：新增与 test_quality_ui 同构的包装并加入 CI node-id。

#### M-29　心跳超时用例无法区分「超时分支」与「外部 stop」，删掉超时特性仍全绿

- **位置**：[tests/test_machine_validation_fixes.py L56-L134](file:///d:/DouyinLiveRecorder/tests/test_machine_validation_fixes.py#L56-L134)（核心断言 L130-131）
- **证据**：用例末尾无条件 `await client.close()` 本身就会产生一次 ws.close()，断言仅 `len(close_called) >= 1`——即使删除生产侧 wait_for 超时分支（[ws_client.py L415-L452](file:///d:/DouyinLiveRecorder/src/ws_client.py)），外部关闭也恰好满足断言。未断言第一次 close 的来源/时刻，也未捕获「心跳回调超时」warning。
- **修复建议**：记录每次 close 的时刻与来源，断言第一次 close 发生在超时点且早于主动停止，并断言 warning 文本。

#### M-30　`test_notify.py` 用字面量 `python` 起子进程，只提供 python3 的环境必失败

- **位置**：[tests/test_notify.py L50](file:///d:/DouyinLiveRecorder/tests/test_notify.py#L50)、[L61](file:///d:/DouyinLiveRecorder/tests/test_notify.py#L61)、[L82](file:///d:/DouyinLiveRecorder/tests/test_notify.py#L82)
- **证据**：生产 `run_script` 以 shell=False 在 PATH 查找 `python`；Linux/CI 镜像常只有 `python3`，正常完成与超时两个用例随即失败（本机 Windows 有 python 故单跑必绿）。同仓 test_run_gates.py 已有解释器换绑的成熟做法。
- **修复建议**：命令改用 `sys.executable`。

#### M-31　两处环境依赖型测试隐患（待核实/潜伏）

1. [tests/test_gui_monitor.py L71-L84](file:///d:/DouyinLiveRecorder/tests/test_gui_monitor.py#L71-L84)：子进程按 UTF-8 解码但未注入 `PYTHONUTF8=1/PYTHONIOENCODING`，在无该环境变量的中文 Windows（ACP=936）上可抛 UnicodeDecodeError（当前 shell 恰好有 UTF-8 环境故不触发，已核）。
2. [tests/test_danmaku_monitor.py L426](file:///d:/DouyinLiveRecorder/tests/test_danmaku_monitor.py#L426)：`import gui` 在收集期即把 `DLR_GUI_PARENT=1` 注入整个会话（[gui.py L171-L174](file:///d:/DouyinLiveRecorder/gui.py#L171-L174)），与「禁止在 pytest 进程内 import gui」的既有约定（test_gui_monitor 改走子进程的理由）冲突，目前靠下游用例各自防御兜住。
- **修复建议**：子进程统一注入 UTF-8 环境；把 import gui 移入子进程或加 autouse fixture 成对还原环境变量。

### E. 脚本（2 项）

#### M-32　两个维护脚本的错误处理缺陷

1. **sync_metadata.py：uv 不存在时友好降级分支不可达**——[scripts/sync_metadata.py L94-L99](file:///d:/DouyinLiveRecorder/scripts/sync_metadata.py#L94-L99)（已核验）：PATH 无 uv 时 `subprocess.run(["uv", ...])` 直接抛 FileNotFoundError 而非返回非零码，else 分支 WARN 永远走不到，且其后不依赖 uv 的 egg-info 重建也不会执行。修：`shutil.which("uv")` 先探测或 try/except OSError。
2. **smoke_test.py：配置类型畸形时抛栈 rc=1，破坏文件头承诺的 rc=2 语义**——[scripts/smoke_test.py L124-L133](file:///d:/DouyinLiveRecorder/scripts/smoke_test.py#L124-L133)：headers 写成字符串/数组、checks 写成 dict 时 `.items()` 抛 AttributeError，main 无捕获；[_ci_web_smoke.sh L85-L108](file:///d:/DouyinLiveRecorder/scripts/_ci_web_smoke.sh#L85-L108) 依赖 rc=2 区分「面板故障（可重试）」与「配置问题」，rc=1 会触发无谓网络重试。修：load_config 做类型校验，不符走 rc=2。

---

## 五、轻微问题（47 项，分组列举）

> 以下均为已定位到行的真实问题；表中「位置」为可点击链接。影响有限或当前不可达的项已注明。

### F. `main.py` 与平台解析层（8 项）

| # | 位置 | 问题 | 建议 |
|---|---|---|---|
| 1 | [main.py L1800-L1804 等约 40 处](file:///d:/DouyinLiveRecorder/main.py#L1800-L1804) | 每个 `_resolve_*` 函数内 `platform = "未知平台"` 紧接被平台名覆盖，恒为死赋值（复制粘贴残留） | 删除首行死赋值 |
| 2 | [main.py L294](file:///d:/DouyinLiveRecorder/main.py#L294) | 注释「冻结后指向 _internal/」与 `_app_root()` 实际返回 exe 同级目录相反 | 更正注释 |
| 3 | [main.py L1484-L1501](file:///d:/DouyinLiveRecorder/main.py#L1484-L1501) | 以 `"python" in script_command` 子串判定参数风格，命令任意位置含 python 即走 python 风格；且 `record_name`/路径含 `"` 会破坏拼接命令（用户自有命令，自伤面） | 改用更明确的配置开关或 shlex 列表拼接 |
| 4 | [main.py L4547-L4561](file:///d:/DouyinLiveRecorder/main.py#L4547-L4561) | `subprocess.run(["ffmpeg","-version"], check=True)` 仅捕获 CalledProcessError/FileNotFoundError，其他 OSError 子类（PermissionError 等）会冒泡中断启动 | 补 `except OSError` |
| 5 | [src/spider.py L4825-L4842](file:///d:/DouyinLiveRecorder/src/spider.py#L4825-L4842) | `get_huajiao_sn` except 块内同一 `raise RuntimeError(...) from e` 重复两遍，后者不可达 | 删除后 4 行 |
| 6 | [src/spider.py L4269-L4274、L6256、L6477、L6500、L6518、L1608-L1616](file:///d:/DouyinLiveRecorder/src/spider.py#L4269-L4274) | 多处 JSON 请求体字符串拼接，URL 派生值未转义（同主机参数污染；Look 直播已正确用 json.dumps） | 构造 dict 交 json= 编码 |
| 7 | [src/spider.py L3057、L2509、L5099、L1149、L4859、L5762、L5920](file:///d:/DouyinLiveRecorder/src/spider.py#L3057) | 一组未防护的 URL 切分：空串 `url[-1]` IndexError、`split("/")[3]` 越界、room_id 带 `&` 冗余参数、None 被格式化成 `roomId=None` 发请求等 | 统一经 `get_params`/安全提取助手并先判空 |
| 8 | [src/spider.py L978-L982、L3203、L3366、L4047、L631、L816、L3938、L1803、L1892](file:///d:/DouyinLiveRecorder/src/spider.py#L978-L982) | TikTok 每轮无条件 sleep 1s；两处多参数 `RuntimeError(a, b)` 日志呈现为 tuple；多处裸 `int()`/裸下标在异常响应下被装饰器吞成「未开播」 | 仅重试时 sleep；单字符串拼接；.get + 归因 |

### G. 内置凭据与平台兼容（3 项）

| # | 位置 | 问题 | 建议 |
|---|---|---|---|
| 9 | [src/spider.py L920-L923](file:///d:/DouyinLiveRecorder/src/spider.py#L920-L923) | 内置 TikTok 游客 cookie 第三段时间戳约为 2025-10-24，**已过期**，默认安装必失败（有专属告警但属确定性失效缺省值） | 确认失效后改空串 + 强制配置提示 |
| 10 | [src/spider.py L97、L2261、L5698-L5700、L6789、L1537](file:///d:/DouyinLiveRecorder/src/spider.py#L97) | PopkonTV 应用凭据、XHS 共享 sid、嗨秀 token、来秀盐、斗鱼游客 did 等硬编码（多为公开客户端常量，均有 env/config 覆盖） | 文档中登记为「公开常量/可过期游客凭据」 |
| 11 | [src/spider.py L1313-L1314、L2413、L2675、L2890、L5160、L6698-L6705](file:///d:/DouyinLiveRecorder/src/spider.py#L1313-L1314) | 多条 CDN 链路强制降级明文 http（平台 403 后的兼容取舍，注释已登记）；咪咕签名后重定向地址未做 host 校验即作录制地址（待核实） | 定期复测平台 https 支持；重定向地址复用白名单/内网判定 |

### H. 网络层与下载安装器（9 项）

| # | 位置 | 问题 | 建议 |
|---|---|---|---|
| 12 | [src/sync_http.py L308-L317](file:///d:/DouyinLiveRecorder/src/sync_http.py#L308-L317) | HTTP 400 分支 `e.read()` 无上限、不走解压限流，可绕开本模块两道响应体 OOM 防护（模块当前无生产调用方） | 走 capped read |
| 13 | [src/sync_http.py L238-L272](file:///d:/DouyinLiveRecorder/src/sync_http.py#L238-L272) | data 与 json 同传时代理/直连两分支行为相反且静默（async 侧显式报错） | 同传即 ValueError |
| 14 | [src/cookie_cache.py L344-L352](file:///d:/DouyinLiveRecorder/src/cookie_cache.py#L344-L352) | singleflight 失败日志异常文本未脱敏（key 已脱敏，e 未脱敏；现 factory 均自吞异常，潜伏） | `mask_credentials(str(e))` |
| 15 | [src/cookie_cache.py L92-L101、L78-L83](file:///d:/DouyinLiveRecorder/src/cookie_cache.py#L92-L101) | get_cached 恒按 DEFAULT_TTL 判过期、忽略写入方自定义 ttl（当前无调用方传非默认值）；缓存键未剥 URL fragment，同域仅 fragment 不同会去重失效 | 条目存 ttl；先剥 `#` 再去 query |
| 16 | [src/utils.py L150-L168](file:///d:/DouyinLiveRecorder/src/utils.py#L150-L168) | JS 编译缓存仅按 mtime 命中即返回，不再读盘/不做 SHA256 钉定；mtime 粗粒度或保留 mtime 的同步可使被篡改脚本跳过校验（需有脚本写权限） | 命中时廉价复算哈希 |
| 17 | [src/utils.py L393-L399](file:///d:/DouyinLiveRecorder/src/utils.py#L393-L399) | `is_valid_zip` 内重复 `import zipfile`（模块级已导入，死代码） | 删除局部 import |
| 18 | [src/config_io.py L377-L388](file:///d:/DouyinLiveRecorder/src/config_io.py#L377-L388) | 备份文件先按 umask（常 0644）创建、写完才 chmod 0600，存在本地其他用户可读窗口；脱敏失败回退的明文副本同此（多用户 POSIX 机器） | `os.open(..., 0o600)` 先建后写 |
| 19 | [src/ffmpeg_install.py L291-L304、L350-L363、L377-L381](file:///d:/DouyinLiveRecorder/src/ffmpeg_install.py#L291-L304)；[src/node_install.py L239-L250、L266-L283、L199-L215、L285-L287](file:///d:/DouyinLiveRecorder/src/node_install.py#L266-L283) | 1KB 分块统一 30s 读超时易在慢速链路失败（master 下载器已改 64KB+(15,30)+重试，这两条未对齐）；官方源解压校验失败残留几百 MB 临时 zip；node「目录已存在」分支验证前未前置 PATH；版本号未做 `v\d+\.\d+\.\d+` 白名单即拼 URL；安装异常 `{e}` 可能含代理凭据（待核实） | 分别对齐 master 下载器；finally 清理；前置 PATH/绝对路径；正则白名单；异常脱敏 |
| 20 | [src/ffmpeg_master_download.py L213-L241、L396-L401](file:///d:/DouyinLiveRecorder/src/ffmpeg_master_download.py#L213-L241) | 下载/安装异常日志 `{e}` 未过脱敏（同上代理凭据族） | 统一过 mask_credentials |

### I. ffmpeg 进程与录后处理（4 项）

| # | 位置 | 问题 | 建议 |
|---|---|---|---|
| 21 | [src/ffmpeg_proc.py L115-L131](file:///d:/DouyinLiveRecorder/src/ffmpeg_proc.py#L115-L131) | Windows 优雅停止路径 `stdin.write(b"q")/flush()` 无超时，ffmpeg 卡死不读管道时理论上永久阻塞、后续 terminate/kill 到不了（待核实窄竞态） | 写操作放守护线程 + 短 join 超时 |
| 22 | [src/video_postprocess.py L201-L213](file:///d:/DouyinLiveRecorder/src/video_postprocess.py#L201-L213) | 转码超时 kill 后第二次 `communicate()` 无超时，不可中断 IO 下永久占住后处理线程池 worker | 加有限超时，超时放弃读取 |
| 23 | [src/srt_writer.py L150-L157](file:///d:/DouyinLiveRecorder/src/srt_writer.py#L150-L157) | 严重迟到的弹幕时间戳（`seg < 当前片`）会回开旧分片写入，造成条目跨文件乱序（需写盘停顿接近一个分片时长，极端） | 迟到消息写当前片或丢弃计数 |
| 24 | [src/ws_client.py L112-L122](file:///d:/DouyinLiveRecorder/src/ws_client.py#L112-L122) | `DEFAULT:@SECLEVEL=1` 宽松 SSL 上下文默认用于**所有**平台 wss（仅放宽套件强度、仍校验证书，非证书绕过） | 收窄到确需的平台（斗鱼） |

### J. 弹幕平台层与自有 JS（10 项）

| # | 位置 | 问题 | 建议 |
|---|---|---|---|
| 25 | [src/platforms/bilibili.py L284-L295](file:///d:/DouyinLiveRecorder/src/platforms/bilibili.py#L284-L295) | 解压失败/超 8MiB 分支完全静默 `return`，与同文件其余处保留异常线索的口径不一致 | 补 debug 日志 |
| 26 | [src/platforms/bilibili.py L187-L196](file:///d:/DouyinLiveRecorder/src/platforms/bilibili.py#L187-L196) | `_reject_auth` 是全链路唯一裸 `asyncio.ensure_future`（无强引用、异常无人取），其余派发点已统一 `spawn_danmaku_task` | 改用 spawn_danmaku_task |
| 27 | [src/platforms/twitch.py L35、L117-L119](file:///d:/DouyinLiveRecorder/src/platforms/twitch.py#L35) | `_line_buf` 半行缓冲在重连后不清空，断线切在半行中间时污染新连接首条消息（至多丢一条） | `_on_ws_ready` 中重置缓冲 |
| 28 | [src/platforms/_tars.py L66-L75、L90-L92、L168-L183](file:///d:/DouyinLiveRecorder/src/platforms/_tars.py#L66-L75) | 扩展 tag/STRING4/各整数宽度读取点未统一走 `_need` 边界校验，截断帧抛裸 IndexError/struct.error 而非约定的 ValueError（唯一调用方有宽 except，无崩溃） | 统一先 `_need(n)` |
| 29 | [src/platforms/bilibili.py L324-L334](file:///d:/DouyinLiveRecorder/src/platforms/bilibili.py#L324-L334)、[huya.py L168](file:///d:/DouyinLiveRecorder/src/platforms/huya.py#L168) | 弹幕颜色未做 24 位收窄，超范围值会拼出非法 CSS 颜色（现行协议均为 24 位正值，疑似不可达，待核实） | `& 0xFFFFFF` 后格式化 |
| 30 | [src/javascript/haixiu.js L5-L8](file:///d:/DouyinLiveRecorder/src/javascript/haixiu.js#L5-L8)、[x-bogus.js L375-L376](file:///d:/DouyinLiveRecorder/src/javascript/x-bogus.js#L375-L376) | `eval(常量字符串)`——实参为写死字面量且脚本经哈希钉定，无注入路径，但持续触发静态扫描告警 | 直接引用变量/文件头声明豁免 |
| 31 | [src/javascript/liveme.js L332、L348](file:///d:/DouyinLiveRecorder/src/javascript/liveme.js#L332) | 硬编码客户端签名密钥（厂商公开内置，无法通过隐藏根治）；`console.log` 输出含密钥的签名素材，execjs ProgramError 时可能进日志 | 补注释说明；删除调试日志 |
| 32 | [src/javascript/liveme.js L317-L415](file:///d:/DouyinLiveRecorder/src/javascript/liveme.js#L317)、[x-bogus.js L9](file:///d:/DouyinLiveRecorder/src/javascript/x-bogus.js#L9) | 非严格模式隐式全局赋值（当前一子进程一签名无污染） | 补声明或 "use strict"（混淆 VM 需回归） |
| 33 | [src/javascript/migu.js L124、L235、L244](file:///d:/DouyinLiveRecorder/src/javascript/migu.js#L124) | 三次 fetch 无进程内超时/AbortSignal（外层 subprocess 30s 强杀是外边界） | 加 AbortSignal.timeout |
| 34 | [src/stream.py L1247-L1256](file:///d:/DouyinLiveRecorder/src/stream.py#L1247-L1256) | 通用 get_stream_url 中 play_url_list 元素为 None/非 dict 时 `.get()` 抛 AttributeError 被装饰器吞成「未开播」（TikTok 分支已过滤，通用入口未过滤） | isinstance 收窄 |

### K. GUI 与前端（8 项）

| # | 位置 | 问题 | 建议 |
|---|---|---|---|
| 35 | [gui.py L338-L339](file:///d:/DouyinLiveRecorder/gui.py#L338-L339) | 字体族硬编码 Microsoft YaHei UI / Cascadia Code，macOS/Linux 静默回退 | 按平台候选族 + 字体探测 |
| 36 | [gui.py L473-L483](file:///d:/DouyinLiveRecorder/gui.py#L473-L483) | 折行防抖的 `after_cancel` 裸调未做 TclError 防护（其余 6 处均已包 try） | 同口径包 try |
| 37 | [gui.py L3644-L3664、L3461-L3464](file:///d:/DouyinLiveRecorder/gui.py#L3644-L3664) | 状态栏刷新/tail 循环的周期性异常被 `except Exception: pass/sleep` 完全静默，编程错误不可见 | 限频 warning 留痕 |
| 38 | [gui.py L3103-L3105](file:///d:/DouyinLiveRecorder/gui.py#L3103-L3105) | 子进程 stdout 上屏前仅剥 ANSI，未二次脱敏（上游现状已 102 处脱敏，属纵深防御；待核实） | 入队前过 mask_credentials |
| 39 | [gui.py L3371-L3409](file:///d:/DouyinLiveRecorder/gui.py#L3371-L3409) | 停止后立即重启录制，旧 tail 线程 join 仅 0.2s，最长 1s 内可向新会话缓冲注入旧事件（已 warn 留痕，可自愈） | 代次 token 或分段多等一轮 |
| 40 | [gui.py L2861-L2902](file:///d:/DouyinLiveRecorder/gui.py#L2861-L2902) | Popen 成功后若 UI 步骤抛异常，except 清空引用但不终止已在跑的录制子进程，成孤儿且按钮无法再控（触发罕见） | 异常分支先终止该 pid |
| 41 | [web/app.js L714-L724、L1493-L1545](file:///d:/DouyinLiveRecorder/web/app.js#L714-L724) | 登录成功后口令仍留 DOM（隐藏视图）；登录/保存按钮无在途防重入，双击产生多个有效 token/交织 PUT | 清空口令框 + autocomplete；in-flight 禁按钮 |
| 42 | [web/app.js L260-L265](file:///d:/DouyinLiveRecorder/web/app.js#L260-L265) | `fmtTime` 硬编码 `zh-CN` 区域格式，英文界面下时间仍按中文区域呈现（疑似 i18n 漏网，待产品确认） | 跟随当前语言 |

### L. 前端无障碍与健壮性（5 项）

| # | 位置 | 问题 | 建议 |
|---|---|---|---|
| 43 | [web/app.js L1161-L1162](file:///d:/DouyinLiveRecorder/web/app.js#L1161-L1162)；[web/style.css L226-L231](file:///d:/DouyinLiveRecorder/web/style.css#L226-L231) | 房间开关 checkbox 0 尺寸且无 aria-label，键盘焦点不可见 | 加 aria-label + 滑块焦点环 |
| 44 | [web/index.html L39、L114、L118](file:///d:/DouyinLiveRecorder/web/index.html#L39)；[web/app.js L1424-L1428](file:///d:/DouyinLiveRecorder/web/app.js#L1424-L1428) | 多处输入仅有 placeholder 无 label；动态配置行 label 未与 input 关联 | aria-label 或 for/id |
| 45 | [web/index.html L175、L54](file:///d:/DouyinLiveRecorder/web/index.html#L175) | toast 与引擎告警横幅无 aria-live/role，辅助技术不播报关键反馈 | role=status/alert |
| 46 | [web/motion.js L24-L31、L187-L199](file:///d:/DouyinLiveRecorder/web/motion.js#L24-L31) | 注释称缺 matchMedia 时降级为关闭动效，实际 `return false`（开启）；rAF 缺失回退 `setTimeout(loop)` 无延迟成忙轮询且 destroy 清不掉 timeout | return true；回退传 1000/30 并在 destroy 清 |
| 47 | [index.html L212、L250、L239-L244、L14-L16、L166-L171](file:///d:/DouyinLiveRecorder/index.html#L212) | CDN 脚本未加载时播放抛未捕获 ReferenceError 无提示；原生 HLS 无 onerror、flv play() 未接 catch；Google Fonts CSS 无 SRI（两个 JS 已实测 SRI 匹配）；播放地址判定大小写敏感/子串匹配且无条件 http→https | 加组件守卫与回调；CSS SRI 或自托管；路径名小写判定 |

### M. 其余（补充 4 项）

| # | 位置 | 问题 | 建议 |
|---|---|---|---|
| 48 | [src/web_tray.py L252-L259](file:///d:/DouyinLiveRecorder/src/web_tray.py#L252-L259) | 托盘「退出」无 server 分支 `os._exit(0)` 跳过 atexit，ffmpeg 不清理（生产入口恒传 server，仅测试可达） | 无 server 也走清理链 |
| 49 | [msg_push.py L189、L79、L130、L348、L411、L492](file:///d:/DouyinLiveRecorder/msg_push.py#L189) | 多地址/收件人列表只换全角逗号，不 strip/不过滤空项，尾逗号或空格产生脏条目，单条 SMTP 拒绝使整批失败；[L239-L252](file:///d:/DouyinLiveRecorder/msg_push.py#L239-L252) STARTTLS 不支持时告警后仍明文提交邮箱授权码（fail-open）；[L25-L26](file:///d:/DouyinLiveRecorder/msg_push.py#L25-L26) opener 默认含 file/ftp 处理器且跟随跨主机重定向（管理员自配，盲 SSRF）；[L532-L575](file:///d:/DouyinLiveRecorder/msg_push.py#L532-L575) 残留手工调试死代码块 | strip+过滤空项；明文认证改为显式开关；scheme 白名单；删死代码 |
| 50 | [scripts/check_annotations.py L518、L537](file:///d:/DouyinLiveRecorder/scripts/check_annotations.py#L518) | `--baseline` 等价性校验把违规条数直接当退出码，违规数为 256 倍数时 POSIX 回绕为 0（门禁假绿） | 统一 `1 if ... else 0` |
| 51 | [scripts/patch_i18n_2026_09_12.py L23、L228-L233](file:///d:/DouyinLiveRecorder/scripts/patch_i18n_2026_09_12.py#L23)；[build_exe.py L948-L955](file:///d:/DouyinLiveRecorder/build_exe.py#L948-L955)；[scripts/run_gates.py L268-L278](file:///d:/DouyinLiveRecorder/scripts/run_gates.py#L268-L278)；[_ci_web_smoke.sh L44](file:///d:/DouyinLiveRecorder/scripts/_ci_web_smoke.sh#L44)；[smoke_test.py L281-L291](file:///d:/DouyinLiveRecorder/scripts/smoke_test.py#L281-L291) | 硬编码开发者本机绝对路径 `D:/DouyinLiveRecorder-dev`；声称透传 compile_po 退出码实际恒 0 且裸用 "python"；Node zip 在 Windows 分支裸 extractall（ffmpeg 侧有 realpath 越界防护，两侧不对称）；门禁 shell=True 执行仓内命令（可信但信任边界靠评审）；兜底 `pkill -f 'python web\.py'` 匹配面宽；HTML 报告插值未 html.escape | 分别改 `__file__` 推导/透传退出码与 sys.executable/统一解压防护/注释固化评审约束/收紧 pkill/转义 |

> 注：本表编号 1-51，其中第 8、19、49、51 项各含多条同组子项；表后「N. 测试侧其余轻微项」另归并 8 条。合计轻微独立问题约 59 个，与第二节汇总口径一致。

### N. 测试侧其余轻微项（归并）

- [tests/test_anchor_rename.py L59-L65](file:///d:/DouyinLiveRecorder/tests/test_anchor_rename.py#L59-L65)：docstring 声称注释行改名后「整行激活」，断言锁的却是「保留单层 #」（注释意图与断言相反，易误导）。
- [tests/test_bili_live_collector.py L43-L44](file:///d:/DouyinLiveRecorder/tests/test_bili_live_collector.py#L43-L44)、[test_huya_live_collector.py L47-L48](file:///d:/DouyinLiveRecorder/tests/test_huya_live_collector.py#L47-L48)：真机脚本清空 `_out_live` 无平台前缀过滤且不判目录，混入子目录会抛错、并行验证互删（手工脚本，影响小）。
- [tests/test_cookie_cache.py L237-L259](file:///d:/DouyinLiveRecorder/tests/test_cookie_cache.py#L237-L259)：4 方 Barrier/join 无超时，worker 异常会令整个 pytest 挂死。
- 深路径 patch 族：[test_stream_select.py L604、L670、L1004、L1029、L1239](file:///d:/DouyinLiveRecorder/tests/test_stream_select.py#L604)（`patch("src.stream_select.time.sleep")` 等改的是全进程 time 模块）、[test_regression_2026_09_22_utils.py L640](file:///d:/DouyinLiveRecorder/tests/test_regression_2026_09_22_utils.py#L640)（裸 patch builtins.open）、[test_regression_2026_09_22_net.py L723-L756](file:///d:/DouyinLiveRecorder/tests/test_regression_2026_09_22_net.py#L723)（字符串形式 patch httpx.AsyncClient）——仓库卫生门禁 R1 已知悉但未覆盖这些形态。
- [tests/test_notify.py L21](file:///d:/DouyinLiveRecorder/tests/test_notify.py#L21)、[test_srt_timeline_anchor.py L23](file:///d:/DouyinLiveRecorder/tests/test_srt_timeline_anchor.py#L23)：模块级 `sys.path.insert` 不回收（冗余导入路径）。
- 时序脆弱：[test_scheduler.py L57-L93](file:///d:/DouyinLiveRecorder/tests/test_scheduler.py#L57-L93) cooldown=0.05 + 2× 余量的真实 sleep；[test_regression_2026_09_22_infra.py L533-L573](file:///d:/DouyinLiveRecorder/tests/test_regression_2026_09_22_infra.py) 工作线程真实 sleep 10s+3s；[test_record_watchdog.py L331-L354](file:///d:/DouyinLiveRecorder/tests/test_record_watchdog.py#L331-L354) 硬编码 `/tmp/out.ts`（跨平台隐患，现行路径有父目录豁免巧合不致误判）。
- [tests/test_platform_danmaku_offline.py L405-L410](file:///d:/DouyinLiveRecorder/tests/test_platform_danmaku_offline.py#L405-L410)：monkey patch 的 undo 位于断言之后，失败路径泄漏（理论窗口）。
- [tests/test_machine_validation_fixes.py L196-L203](file:///d:/DouyinLiveRecorder/tests/test_machine_validation_fixes.py#L196-L203)：「三处调用都超时」用 `text.count("超时") >= 3` 聚合计数，无法归因到具体入口，单个入口少记/重复记都可能过线。
- [web/app.js 对应前端测试](file:///d:/DouyinLiveRecorder/tests/frontend)：localStorage 回退导致会话持久化（[app.js L27-L35、L144-L156](file:///d:/DouyinLiveRecorder/web/app.js#L27-L35)，代码注释已知情接受，仅作风险记录）。

---

## 六、已核查确认的安全亮点（不计为问题）

本次专项核查确认以下高风险面**已做对**，供维护者避免回归：

1. **ffmpeg 与外部命令**：生产侧全部 argv 列表调用、无 `shell=True`（全仓 grep 实证；仅 `run_gates.py` 对仓内受评审命令使用且有写命令拦截）；无 `eval/exec/os.system/pickle/yaml.load`（自有 JS 的 eval 实参均为常量）。
2. **ffmpeg 协议面收敛**：`-protocol_whitelist` 已移除 file，仅留 rtmp/crypto/http/https/tcp/tls/udp/rtp/httpproxy（[main.py L3467-L3473](file:///d:/DouyinLiveRecorder/main.py#L3467-L3473)）。
3. **Web 鉴权体系**：PBKDF2-HMAC-SHA256（200k 迭代）口令哈希、256-bit Bearer 令牌、滑动窗口登录限流（per-IP 5/300s + 全局 40/300s）、免鉴权端点 per-IP 预算、Host 白名单（防 DNS 重绑定）与 Origin 双名单（含端口）、非幂等同源校验、危险配置键黑名单（含大小写归一）、敏感项掩码与写侧三重拒绝、认证两键修改强制复验口令（[web_api.py L1205-L1214](file:///d:/DouyinLiveRecorder/src/web_api.py#L1205-L1214)）、非回环绑定每请求不变量、CSP/nosniff/DENY 响应头、文件接口 realpath 越界校验。
4. **SSRF 写入侧防护**：房间地址/推送/代理/SMTP 四写入口共用 `_check_url_target` 内核，覆盖 scheme 白名单、inet_aton 缩写 IP、CGNAT、IPv6、云元数据 IP、内部用途域名与 DNS 解析双道判定（[web_config.py L229-L653](file:///d:/DouyinLiveRecorder/src/web_config.py#L229-L653)）；小红书短链落地页双闸修复完整（S-1 的现成参照）。
5. **下载完整性**：ffmpeg/node 发行包先取官方 SHA256 再安装、不符 fail-closed；ffmpeg master 构建 GPG `--status-fd` + 40 位指纹集合验签；zip 手工解包含 Zip Slip 与解压炸弹（单文件 4GB/累计 8GB/100x）防护。
6. **凭据卫生**：录制 URL 全链路 15 个文件、102 处 `mask_credentials` 调用；日志按房间名 ContextVar 关联；TLS 默认严格校验，证书豁免分控制面/拉流面并按平台生效。
7. **并发与状态治理**：录制槽位在 Popen 前获取并在 finally 无条件释放；看门狗使用单调钟免疫时钟跳变、停滞观测区分「目录不可读/确实无产物」三态；弹幕采集器异常路径幂等 stop；配置热加载采用「新解析器整体替换 + 局部集合原子换位」避免半写污染。
8. **工程纪律**：大量修复带有回归锁与设计决策注释；存在 `run_gates.py` 统一门禁、覆盖率门槛、注释等价性检查与 i18n 字符串提取门禁。

---

## 七、改进建议与修复优先级

### P0（建议立即修复，1-2 个 PR）

1. **S-1**：镜像 SEV-2214 为 Shopee 落地页补白名单 + 内网双闸，并把 `_shopee_host_suffix` 改为基于 `urlparse().hostname`。
2. **S-2**：给 test_twitch_live_collector.py 补 `__main__` 守卫，恢复全量测试收集的确定性与 CI 速度。
3. **M-26/M-24/M-29**：修正或删除三处假绿/失效测试（强复验文本锁、tail 停止信号、心跳超时归因），安全类假绿优先。

### P1（近期排期，安全收口与数据正确性）

4. M-1/M-2：重定向逐跳内网复检；sync_req scheme 白名单。
5. M-3/M-4/M-5：凭据日志脱敏收口（pwd、代理异常、自定义脚本命令），可与「装饰器统一脱敏」的既有待办合并。
6. M-11/M-12/M-13：三个直接影响录制/弹幕正确性的逻辑缺陷（TikTok HLS 画质、弹幕平台 strip、B站假关闭）。
7. M-18/M-19：web.py 检查顺序上移；tr() 异常元组补全（改动极小）。

### P2（常规迭代）

8. M-8/M-9/M-10：spider 缓存键按 proxy 分桶、`_dig_str` 收口 None、TwitCasting 回退分支。
9. M-14/M-15/M-16/M-17：GUI 一组健壮性修复（结构化状态标记优先于正则补丁）。
10. M-21/M-22/M-23 + 轻微 43-47：前端轮询代次、口令采集与无障碍/健壮性批次。
11. M-25/M-27/M-28/M-30/M-31：测试卫生批次（monkeypatch 还原、shim 约定、motion 包装入 CI、解释器换绑、UTF-8 环境）。
12. M-32 与轻微脚本项：维护脚本退出码/硬编码路径/解压对称/转义批次。

### P3（跟踪与知情决策）

13. M-7（migu wasm SRI/沙箱）、M-20（打包后 i18n 实测）、M-6（VBS 锚定收紧）、轻微项中所有标「待核实」的条目，经实测/抓包确认后再定方案。
14. 轻微项中的死代码、过期内置凭据、SECLEVEL 收窄、a11y 等可结合周边改动顺手清理。

### 流程性建议

- 安全类文本锁（mjs/Python 正则锁源码）改为**行为锁**：本次 M-26 证明「钉旧字面量」在契约反转时会静默失效，行为断言不会。
- 新增「平台返回 URL」的统一收口：当前小红书/Shopee/async 探针/咪咕各写一份判定，建议抽成共享的「重定向/落地页校验」助手，新平台接入强制走它。
- 真机脚本（`*_live_collector.py`）纳入模板与 lint 检查：必须有 `__main__` 守卫、必须有平台前缀清理。
- 日志脱敏前移：在 loguru patcher 层对所有入日志文本统一过 `mask_credentials`（代码注释中已列为治本待办），可一次消除 M-3/M-4/M-5 及同类零散缺口。

---

## 八、总结性结论

DouyinLiveRecorder 的代码库呈现出**高密度修复历史与较强的安全工程意识**：关键信任边界（Web 鉴权、SSRF 写入校验、下载验签、ffmpeg 参数化、凭据脱敏）均有系统化设计与回归测试，生产代码中未发现可直接远程利用的命令注入、反序列化或证书校验关闭类漏洞。

本次审查发现的最高优先级问题是 **Shopee 短链链路一处与已修复小红书漏洞同型的漏修（S-1）**——它把「响应决定 URL」直接用于带 Cookie 的二次请求，建议按 P0 立即闭合；其次是**测试体系中 1 个确定性收集污染（S-2）与 3 处确凿假绿**，它们不会直接伤害用户，但会使安全回归网失真，应与 S-1 同批修复。其余 32 项中等问题以重定向收口、凭据日志、录制正确性与 GUI 健壮性为主，均有明确的修复路径与仓内可直接复用的既有模式；47 项轻微问题可按 P2/P3 批次消化。

整体评估：**在修复 S-1/S-2 与 P1 安全收口项后，代码库可达对外发布所需的安全与可靠性水准**；报告中所有问题均附文件、行号与证据，「待核实」项已显式标注，建议修复时按编号回写本报告对应条目并补回归锁。

---

## 附录：审查与核查记录

- **直接通读**：main.py 全部、web_api.py 全部、web_config.py 全部、web.py/i18n.py/msg_push.py 关键路径，以及所有引用到的证据行。
- **并行只读审查（均附 file:line + 原文摘录）**：gui.py、spider.py、src 其余 31 个模块、platforms/JS、web 前端、scripts、tests 全量。
- **人工复核（抽样 + 全部严重项）**：S-1（含 `_shopee_host_suffix` 与 XHS 修复对照）、S-2（含兄弟脚本 grep 与 collect-only 实测）、M-1/M-5/M-11/M-12/M-13/M-14/M-15/M-18/M-19/M-24/M-25/M-26/M-32 及 StopRecording.vbs、clean_name、notify 等证据行，均与源码一致。
- **运行时取证**：Python 3.14.7 下 PEP 758 语法确认；`i18n.tr("{x.y}", x=None)` 抛 AttributeError 复现；`pytest tests/test_twitch_live_collector.py --collect-only` 20.55s/退出码 5；根 index.html 两个 CDN SRI 哈希实测 MATCH。
- **未做的事（局限）**：未对任何平台发起真实网络请求；未运行完整测试套件；未做 PyInstaller 打包验证（M-20 待核实）；未动态验证 migu wasm 与咪咕重定向（M-7/L-9 待核实）；标注「待核实」的代理异常回显、Windows 管道阻塞等依赖特定环境的结论未实证。
