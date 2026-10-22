# DouyinLiveRecorder 全量源代码审查报告（2026-09-21）

| 项目 | 内容 |
| --- | --- |
| 报告编号 | CODE_REVIEW_2026-09-21 |
| 被审对象 | `D:\DouyinLiveRecorder-dev`（DouyinLiveRecorder v4.3.0，工作树状态，本目录非 git 仓库） |
| 审查日期 | 2026-09-21 |
| 审查方式 | 14 个互不重叠的模块分组并行深读 + 主会话逐条回源复核 + 只读命令实测取证 |
| 覆盖语言 | Python（3.14）、JavaScript（浏览器端 / Node 签名脚本）、CSS、HTML、YAML（CI/compose）、Shell、VBScript、TOML、Dockerfile |
| 问题总数 | 严重 6 项、中等 74 项、轻微 50 项（合计 130 项） |
| 编号约定 | 本轮编号用 `SEV-Nxx` / `MID-Nxx` / `MIN-Nxx`（`-N` = New），与 `CODE_REVIEW_2026-09-20.md` 的 `SEV-xx`/`MID-xx`/`MIN-xx` 及代码内 `CR-xx`/`F-xx`/`H-xx`/`WD-xx`/`MI-xx`/`补-0x` 标注**互不复用**，便于 grep 区分轮次 |

---

## 一、审查概述与背景

### 1.1 背景

本项目在 2026-09-18 与 2026-09-20 完成过两轮全量源码审查。第二轮的 106 项结论（10 严重 / 69 中等 / 24 轻微 + 6 项补扫）已于 2026-09-20 至 2026-09-21 全量落地修复，修复点在源码注释中以原编号标注（实测计数：`src/` 与根目录入口中 `MID-` 出现 254 次、`SEV-` 45 次、`MIN-` 43 次）。

因此本轮审查的定位不是重复上一轮，而是承担三项任务：

1. **发现新缺陷**：覆盖上一轮未深读的模块（`gui.py` 全文、`src/web_config.py` 全文、`scripts/` 门禁脚本、`tests/` 测试可信度、`src/javascript/` 签名脚本、`web/` 前端）。
2. **识别「半修复」**：上一轮修复由并行子代理按文件分工实施，本轮重点排查「只改一条分支 / 漏一个调用点 / 副本未同步 / 注释声称的事实与代码不符」这一类残留形态。实践结果：74 项中等里有 **9 项**直接以「×× 半修」标注（MID-N08 / N19 / N34 / N43 / N47 / N51 / N58 / N59 / N68），另有 MID-N01 / N20 / N26 / N30 / N44 / N46 等属同族但未加标签——半修复是本轮中等结论的主要增量来源。
3. **回归核查**：抽样复核上一轮严重项的修复是否仍然成立（附录 A）。

### 1.2 审查目标

按用户要求，对全部自研源文件（不含第三方依赖与构建产物）做四维审查：

- **正确性**：逻辑错误、边界条件、控制流漏口、状态一致性、跨模块契约漂移。
- **健壮性**：异常吞没、资源生命周期（进程 / 句柄 / 线程 / 连接 / 文件）、无界增长、降级路径。
- **安全性**：认证与授权、SSRF、路径遍历、注入、凭据泄漏与脱敏、供应链与发布链完整性。
- **可验证性**：门禁与测试是否真能抓住回归（本仓历史已多次出现「门禁全绿但什么都没查」的失效形态，见 MID-63 / MIN-19 / MID-68）。

### 1.3 审查方法

按 `AGENTS.md`「并行分组代码审查的分工口径（2026-09-19 沉淀）」执行：

1. **分组与所有权**：按调用链与文件所有权切成 14 组，组间文件**严格不重叠**（`main.py` 4,906 行与 `src/spider.py` 6,407 行各按行区间拆为 2～3 段；只读审查无写冲突）。每组 prompt 完整注入本项目**刻意约定白名单**（`#` 行注释禁 docstring、PEP 758 无括号 `except`、行宽 120、探针退避白名单仅虎牙、跨循环不建 `aclose()` 协程、四类「钉定/校验」互不覆盖、四语 i18n 目录 + 前端内嵌目录五处同步等），以免把刻意风格误报为问题。
2. **证据要求**：每条结论必须附 `文件:行号` + 逐字符原文片段（≤12 行）+ 影响推演 + 修复方向 + 置信度；凭据类内容一律脱敏。
3. **回源复核**：主会话对 **6/6 严重项**与约 60% 的中等项逐条读回源码核对，并用只读命令实测取证（见 2.3）。
4. **筛除臆测**：按 AGENTS 口径剔除「凭常识推测本仓存在某问题」的条目（第九章），并对需真机 / 需外部响应才能定论者统一**降置信度而非删除**。

### 1.4 结果统计

| 严重度 | 数量 | 主要分布 |
| --- | --- | --- |
| 严重（P0） | 6 | 录制链资源泄漏、凭据生命周期、面板认证不变量、代理地址归一、GUI 跨语言解析 |
| 中等（P1） | 74 | 录制主链路 15 / 平台解析 15 / 构建·CI·门禁与测试可信度 13 / 网络层与凭据 6 / 选源画质 5 / 基础设施 5 / 弹幕字幕 5 / Web 面板 4 / 前端 3 / GUI 3 |
| 轻微（P2） | 50 | 平台解析与网络层 20 / 配置·弹幕·GUI·前端 20 / 构建·CI·门禁与仓库卫生 10 |

| 横向特征 | 计数（统计口径见下） |
| --- | --- |
| 条目内显式标注「×× 半修」（上一轮修复只做了一半） | 中等 9 条 + 轻微 4 条 |
| 条目正文指出「注释 / 文档陈述与代码不符」 | 11 处（集中在中等段） |
| 涉及凭据 / 认证 / SSRF / 注入 / 脱敏的安全面 | 21 项（含 6 项严重中的 3 项） |
| 缺回归锁，或现有回归锁看不见该失效形态（6.3 表逐条列出待补 17 处） | 17 项 |
| 需真机或外部响应形态才能确认（已降置信度） | 12 项 |

**结论取向**：本轮未见「架构级」缺陷——`AGENTS.md` 沉淀的并发模型、探针语义、四类单一定义点、发布链钉定等硬约束在代码中逐条成立（第九章列出已核实项）。问题集中在三类：**控制流收尾漏口**（异常/早退路径未复用同一收尾）、**同源多点写入缺少单一事实源**（配置键表、Cookie 转发表、token 集合、画质档位映射），以及**门禁谓词的覆盖面**（只认一种写法即全绿）。这三类决定了第六章的修复优先级排序。

---

## 二、审查范围

### 2.1 覆盖清单

| 分组 | 文件 | 行数 | 覆盖程度 |
| --- | --- | --- | --- |
| G1 | `main.py:1-1500`（`_fix_encoding`、`safe_exit`、`direct_download_stream`、`check_subprocess`、产物/磁盘判定、主播名改名合并） | 4,906（全文件） | 全文 |
| G2 | `main.py:1500-4906`（52 个平台 resolver 与分发表、ffmpeg 四类单一定义点、`start_record`、`main()` 热加载） | — | 全文 |
| G3–G5 | `src/spider.py`（分 3 段：1–2100 / 2100–4400 / 4400–6407，60+ 平台解析与登录） | 6,407 | 全文 |
| G6 | `src/stream_select.py`（1,141）+ `src/stream.py`（1,200） | 2,341 | 全文 |
| G7 | `src/async_http.py`、`src/sync_http.py`、`src/cookie_cache.py`、`src/proxy.py`、`src/http_config.py`、`src/ttwid.py`、`src/weverse_auth.py`、`src/ws_client.py`、`src/base.py`、`src/platforms/_xbogus.py`、`src/platforms/_tars.py` | ≈5,900 | 全文 |
| G8 | `src/web_api.py`（1,160）、`src/web_config.py`、`src/web_tray.py`、`web.py`、`src/recorder_status.py`、`src/notify.py` | ≈4,300 | 全文 |
| G9 | `src/collector.py`、`src/danmaku_monitor.py`、`src/srt_writer.py`、`src/__init__.py`、`src/platforms/{__init__,bilibili,douyin,douyu,huya,twitch}.py`、`src/proto/__init__.py` | ≈4,300 | 全文 |
| G10 | `gui.py`（3,696）、`i18n.py`、`msg_push.py` | ≈4,900 | 全文 |
| G11 | `src/utils.py`、`src/config_io.py`、`src/config_bool.py`、`src/logger.py`、`src/log_archive.py`、`src/scheduler.py`、`src/ffmpeg_proc.py`、`src/ffmpeg_install.py`、`src/node_install.py`、`src/video_postprocess.py` | ≈6,400 | 全文 |
| G12 | `web/app.js`（1,567）、`web/index.html`、`web/style.css`、根 `index.html`、`src/javascript/{haixiu,liveme,migu,x-bogus}.js` | 5,118 | 全文 |
| G13 | `build_exe.py`、`Dockerfile`、`docker-compose.yaml`、`pyproject.toml`、`requirements.txt`、`.github/workflows/*`、`.github/actions/retry/action.yml`、`scripts/*`、`StopRecording.vbs` | ≈6,400 | 全文 |
| G14 | `tests/`（85 个 `.py` + `tests/frontend/test_quality_ui.mjs`）、`scripts/douyin_live_recorder_standalone.py` | 26,639 + 2,058 | 全文（可信度专项） |

统计口径：生产 Python 65 个文件 / 36,969 行；测试 85 个 Python 文件 / 26,639 行；前端与签名 JS/HTML/CSS 5,118 行；构建、CI、脚本与 VBS 约 2,239 行（不含 `i18n/` 目录数据文件）。

### 2.2 明确排除项

- **第三方与 vendored**：`.venv/`、`node/`、`ffmpeg/`、`node_modules/`、`src/javascript/crypto-js.min.js`（vendored，60,819 字节）、`typings/` 存根、`src/proto/douyin_pb2.py`（protoc 生成，标注 DO NOT EDIT；仅审查其 `.pyi` 存根完整性与运行期兼容约定）。
- **构建产物与运行期数据**：`build/`、`dist/`、`DouyinLiveRecorder.egg-info/`、`__pycache__/`、`downloads/`、`logs/`、`backup_config/`；`config/` 仅作只读取证与脱敏比对（含真实凭据，且已被 `.gitignore` 忽略）。
- **生成物与会话产物**：`docs/qgraphflow/**`（生成架构图 HTML，786 KB）、`.workbuddy/`（其内 `tmp/i18n_param_migration_backup/` 留有整份源码旧副本，已登记为 MIN-N50①）。
- **文档类**：`README*.md`、`CODE_WIKI*.md`、`CODE_REVIEW_*.md`、`AGENTS.md` 仅在「陈述与代码是否一致」维度引用，不作为代码审查对象。

### 2.3 验证证据（本轮实测）

| 取证动作（全部只读） | 结果 | 对应条目 |
| --- | --- | --- |
| `httpx.Client(proxy='127.0.0.1:7890')` / `proxy=''`（venv httpx 0.28.1） | 均抛 `ValueError: Unknown scheme for proxy URL`；`proxy=None` OK | SEV-N05 |
| `httpx.Headers({'cookie':..,'Cookie':..}).multi_items()` | 返回**两条** `cookie` 头，httpx 不去重 | MID-N28 |
| `grep -rn 心跳回调超时 i18n/` | 四语目录 + `.mo` **0 命中**（该告警未登记） | MID-N40 |
| `grep -c 'patch("<stdlib>.'`（tests/） | `patch("subprocess.Popen")` ×3、`patch("subprocess.run")` ×3、`patch("<mod>.time.sleep")` ×11 | MID-N68 |
| `is_sensitive_item("Web","web_host")` / `("Web","web_auth_enable")` | 均 `False`（即 `web_host` 可经 `PUT /api/config` 明文改写、无敏感项守卫） | SEV-N03 |
| `grep -n 'video_save_type_list'` 对照 `'音频' not in save_type` | 合法值集同时含 `MP3音频`/`MP3` 与 `M4A音频`/`M4A`，而两道门按子串「音频」判定 | MID-N10 |
| `grep -n url=src/stream_select.py` | 同文件 `mask_credentials` 24 处 vs 裸传 5 处 | MID-N32 |
| 只读 `node --check`（G12） | 4 个签名脚本 + `web/app.js` 全部语法通过 | 第九章 |
| `python scripts/run_gates.py --list`（G13） | 输出 8 条命令，与 `AGENTS.md`「格式化命令」块逐字一致 | 第九章 |

## 三、严重问题（P0，6 项）

### SEV-N01 ｜ `check_subprocess` 收尾存在三处漏口：零字节早退、异常路径回收条件过窄、异常路径不停弹幕采集器

- **位置**：`main.py:1257-1267`（早退）、`main.py:1195-1210`（finally）、`main.py:1219-1221`（采集器停止）、`main.py:1354-1359`（正常出口收尾）
- **证据**：

```python
        _produced_bytes = _record_output_bytes(save_file_path, _split_output)
        if 0 <= _produced_bytes < _MIN_VALID_RECORD_BYTES:
            ...
            record_error(host_of(record_url))
            return False                      # ← 跳过 1354-1358 的全部收尾
    finally:
        _rec_sem.release()
        if process is not None and not _converged and process.poll() is None:
            _ = _terminate_ffmpeg_process(process)
            unregister_ffmpeg_process(process)
            clear_record_info(record_name, record_url)
```

- **机理**：函数体内唯一无条件执行 `recording.discard` + `recording_time_list.pop` + `unregister_ffmpeg_process` 的位置在 1354-1358，而零字节分支在其之前 `return False`。`finally` 的回收被 `process.poll() is None`（进程仍存活）这一条件挡住——零字节轮里 ffmpeg 已**自然退出**，`poll()` 非 None，故三个动作全部不执行。同一条件在异常路径上同样漏：`_terminate_ffmpeg_process` 才需要「进程还活着」，而 `unregister` 与 `clear_record_info` 恰恰在「进程已退出但抛错」时最需要执行，三者共用一个条件把 MID-12 要修的漏口留下一半。此外 `danmaku_collector.stop()` 位于 `try/finally` **之外**（1220），`try` 内任何抛错（`main.py:1076` 的 `Thread.start()` 是 MID-12 自承可达的 `can't start new thread` 点）都会绕过它。
- **影响**：
  - `src/ffmpeg_proc.py:25` 的 `_ffmpeg_processes` 是只增列表（仅 `cleanup_all_ffmpeg_processes` 会 `clear()`），每个滞留 `Popen` 仍持有 `stdin=subprocess.PIPE` 的写端句柄 → CR-06 所描述的「零字节坏线路每约 2 分钟重撞」闭环下，对象与句柄数线性累积到数千。
  - `recording` 幽灵条目使面板/CLI 恒显「录制中」、`main.py:4594` 的磁盘满退出判定（`if not recording:`）恒假、`main.py:3468` 的「等待直播」提示被吞——正是 MID-01 / MID-12 已两次确认要消灭的后果形态。
  - 泄漏的采集线程继续向同一 `base_filename` 写 SRT，下一轮再起第二路 → `_000.srt` 被两路交错覆盖（叠加 MID-N48 / MID-N49 时块号还会复位）。
- **修复**：把 1354-1358 提为 `try/finally` 的无条件收尾（`_converged` 语义只保留给 terminate 一项）；`finally` 中把 `_terminate_ffmpeg_process` 单独保留 `poll() is None` 判定，`unregister_ffmpeg_process` + `clear_record_info` 在 `not _converged` 时无条件执行；`danmaku_collector.stop()` 一并移入 `finally`（`DanmakuCollector.stop()` 已有 `_stop_called` 幂等保护）。
- **回归锁**：`tests/test_record_watchdog.py` 现对 stall / 放弃槽位 / 异常三种出口都断言 `main.recording == set()`，唯独零字节路径没有——补该断言，并新增「零字节轮后 `_ffmpeg_processes` 长度不增长」与「抛错轮 `collector.stop()` 被调用一次」两条。
- **置信度**：高（控制流静态可判定；同函数 stall 分支正是照此显式收尾，说明该义务为作者已知）。

### SEV-N02 ｜ PopkonTV 刷新出的 token 落盘时自带 `Bearer ` 前缀，读回后再拼一次 → 双前缀，凭据复用彻底失效

- **位置**：`src/spider.py:3730`（写回值）、`src/spider.py:3654-3655`（读回拼接）、`main.py:2017-2023`（配置写回）、`main.py:4526`（配置读回）
- **证据**：

```python
# src/spider.py:3729-3730
                headers["Authorization"] = f"Bearer {new_access_token}"
                new_token = f"Bearer {new_access_token}"          # ← 落盘值自带前缀
# 下一轮：main.py:4526 读出 → main.py:2011 作为 access_token 传入 →
# src/spider.py:3654-3655
                headers["Authorization"] = f"Bearer {access_token}"   # ← 二次拼接
```

- **机理**：`result["new_token"]`（`src/spider.py:3775`）被 `main.py` 原样写入 `[Authorization] popkontv_token`，而请求头构造处对入参无条件补 `Bearer `。全仓 grep 确认**没有**任何 `startswith("Bearer ")` 判重，也没有读取侧剥前缀。
- **影响**：写回的凭据必然被服务端拒绝（`src/spider.py:3700` 注明的 HTTP 400 / `statusCd: E5000` 形态），于是**每个检测轮次（默认 120 秒）都重跑一次 `login_popkontv`**——明文账号密码 POST + 自建 AsyncClient + `[Authorization]` 节写回并触发备份线程；`len(new_access_token) == 640` 的长度校验形同虚设。持续重复登录是账号侧风控 / 改密保护的典型触发源，且该平台在双前缀状态下永远无法复用凭据。
- **修复**：落盘与请求头二选一。推荐 `new_token = new_access_token`（存裸值，请求处继续补前缀），并在 `src/spider.py:3655` 加 `access_token.removeprefix("Bearer ").strip()` 归一以自愈已被写坏的存量配置；在 `config/config.ini` 与 README 模板处注明该项存裸 token。
- **回归锁**：新增用例断言「`login` → `new_token` → 以该值再次调用时 `Authorization` 恰含一个 `Bearer `」。
- **置信度**：高（纯字符串流向，两端均可静态确定）。

### SEV-N03 ｜ 面板「非回环监听 + 无认证」不变量可被两步写请求旁路：判定基准 `web_host` 自身可经 API 改写

- **位置**：`src/web_api.py:799-807`（写侧守卫）、`src/web_api.py:1144-1152`（每请求中间件判定）、`src/web_api.py:850-851`（缓存失效）、`src/web_config.py:670-680`（回环判定）
- **证据**：

```python
            if key_norm == "web_auth_enable" and not _target_enabled:
                if not is_loopback_bind_host(str(cast(object, current_cfg.get("web_host", "")) or "")):
                    if not _insecure_bind_allowed():
                        raise HTTPException(403, "非回环监听地址（web_host）下不允许关闭 Web 认证：…")
# 1152（中间件每请求判定，同一基准）
    return not is_loopback_bind_host(str(cast(object, cfg.get("web_host", "")) or ""))
```

- **机理**：两处判定读的都是**配置文件里的 `web_host`**，而不是进程实际绑定地址；`web_host` 本身可经同一个 `PUT /api/config` 写入（实测 `is_sensitive_item("Web","web_host") == False`，且不在 `_DANGEROUS_CONFIG_KEYS = {"自定义脚本执行命令"}` 内，`src/web_api.py:850` 还专门为其失效缓存）。序列：① 写 `web_host=127.0.0.1`（合法、无守卫）→ ② 写 `web_auth_enable=false`（此时 `current_cfg["web_host"]` 已是回环，403 检查通过）。
- **影响**：进程仍监听启动时绑定的 `0.0.0.0`，但此后每请求判定认为「回环」，面板变成**无认证 + 全网卡可达且永不自动恢复**（直到下次重启，而 Docker 部署常长期不重启）。SEV-04 建立的这道防线被完整旁路，连带使 `src/web_api.py:764-766` 倚重的「改密吊销全部 token」泄露兜底失效——拿到 token 的一方可**永久**去掉认证。普通用户场景同样存在：手工把 `web_host` 改回 `127.0.0.1` 想「先关认证再改回来」，中间态即为全网卡无认证。
- **修复**：`create_app` 接收真实绑定地址并存 `app.state.bind_host`（`web.py` 已知 `host`），`src/web_api.py:799` 与 `1144-1152` 一律以**实际监听地址**判定；同时对 `web_host` 的写入施加与 `web_auth_enable` 同强度的目标态校验（新值与真实绑定不一致、且认证处于关闭或即将关闭时拒绝），并把 `web_host` 纳入「写入需二次确认」的受限键集合。
- **回归锁**：`tests/test_web_api.py` 补「先写 `web_host=127.0.0.1` 再写 `web_auth_enable=false` 必须 403」的两步序列用例（现有 SEV-04 用例只测单步）。
- **置信度**：高（守卫分支、缓存失效点与 `web_host` 可写性均已回源确认；未实跑 HTTP 端到端）。

### SEV-N04 ｜ 淘宝：用响应 `Set-Cookie` 整体覆盖用户 Cookie 并持久化回写 config.ini，登录态被静默销毁

- **位置**：`src/spider.py:5892-5905`（覆盖与回写）、初值 `src/spider.py:5809-5817`、来源 `src/async_http.py:291-294`
- **证据**：

```python
        if new_cookie and "_m_h5_tk" in new_cookie:
            new_cookie_str = utils.dict_to_cookie_str(new_cookie)   # 只含响应 Set-Cookie 的两个票据键
            headers["Cookie"] = new_cookie_str                       # ← 覆盖，而非合并进用户 cookie
            ...
                if _old_cookie != new_cookie_str:
                    with _main.file_update_lock:
                        utils.update_config(_cfg_path, "Cookie", "taobao_cookie", new_cookie_str)
```

- **机理**：`async_req(return_cookies=True)` 返回的是 `response.cookies`（`src/async_http.py:293`），**不含请求侧 cookie**；`dict_to_cookie_str` 仅序列化它。WD-18 为修「token 过期时第二轮复现首轮失败」，把该赋值提到了 `ret` 判定之外无条件执行，于是任何一次带 `_m_h5_tk` 的响应都会把 `headers["Cookie"]` 整体替换成「只剩两个票据键」的串，并把这一份写回配置文件。
- **影响**：用户配置的 `taobao_cookie`（登录态 `unb` / `_tb_token_` / `cookie2` 等）在任意一轮 token 轮换后被丢弃并**持久化**，重启也回不来；需登录的淘宝房间此后恒为游客态失败。`CODE_WIKI.md:5013` 记录的「已改为显式 + info 日志」在回路里并不成立——成功路径无任何日志，仅 `except (ImportError, OSError)` 的 debug。与面板侧 MID-37「敏感项不得被静默覆盖」的口径直接冲突。
- **修复**：把现有 `headers["Cookie"]` 解析为 dict，仅更新 `_m_h5_tk` / `_m_h5_tk_enc` 两键后再序列化；回写前比较「合并后的完整串」而非响应串；成功回写补一条不含值的 `logger.info`，使该行为可观测。
- **回归锁**：`tests/test_spider_hardening.py` 增「用户 cookie 含 `unb=1`、响应只带 `_m_h5_tk` → 出请求头与写回值均须仍含 `unb=1`」。
- **置信度**：高（代码路径确定；触发频率取决于 mtop 是否每轮下发 `Set-Cookie`，属常态）。

### SEV-N05 ｜ `select_source_url` 的代理地址未经 `handle_proxy_addr` 归一即交给 `httpx.Client(proxy=…)`：开代理时选源每轮抛穿，该平台永不录制

- **位置**：`src/stream_select.py:989-993`、`src/stream_select.py:652`（另一处构造）；来源链 `main.py:4394-4395` → `main.py:3316` → `main.py:3656`
- **证据**：

```python
    probe_client = httpx.Client(
        timeout=_PROBE_TIMEOUT_SECONDS,
        proxy=proxy_addr,                       # ← 配置原文，未归一；且构造在 try 之前，finally 不覆盖
        verify=_http_config.get_effective_ssl_verify(platform),
    )
```

```
实测（venv httpx 0.28.1）：
  Client(proxy='127.0.0.1:7890') -> ValueError: Unknown scheme for proxy URL
  Client(proxy='')               -> ValueError: Unknown scheme for proxy URL
  Client(proxy=None)             -> OK
```

- **机理**：`main.py:4395` 为 `proxy_addr = None if not use_proxy else proxy_addr_bak`，`proxy_addr_bak` 即配置项 `代理地址` 原文——`src/utils.py:787-788` 明确记载该项**允许裸 `ip:port` 写法**（由 `handle_proxy_addr` 才补前缀）。全仓 grep 确认 `src/stream_select.py` 是唯一不经归一的出站 HTTP 面（`async_http:255/365`、`sync_http:179`、`room:87/175/266`、`weverse_auth:54`、`twitch:53/58` 均已归一）。
- **影响**：两种配置形态必然触发——① 开启「是否启用代理ip」且填裸 `ip:port`；② 开启但 `代理地址` 留空（`""` 同样抛）。此时解析阶段（走已归一的 `async_http`）正常成功、选源每轮 `ValueError`，房间**永不进入录制链**，并持续向按 host 的熔断器投失败样本（极端情况会把用户配置里的地址自动注释掉）。
- **修复**：在两处 `httpx.Client(...)` 之前 `proxy_addr = utils.handle_proxy_addr(proxy_addr)`；并把构造移进 `try`（或按 `_validate_stream_url` 的 `owns_client` 语义做归属保护），使构造失败降级为「本轮校验不可用」而非抛穿。
- **回归锁**：`tests/test_stream_select.py` 增「`proxy_addr='127.0.0.1:7890'` 与 `''` 两种入参下 `select_source_url` 不抛 ValueError，且探针确实走代理」。
- **置信度**：高（抛型已实测；调用链与归一缺失均已回源确认）。

### SEV-N06 ｜ GUI 的日志解析把简中文案写死在正则与子串判定里：切到任一非 zh_CN 语言后画质监控与录制状态静默失效

- **位置**：`gui.py:879`、`gui.py:891`、`gui.py:2982`（消费侧）；生产侧 `src/recorder_status.py:201/227`、`main.py:3689`
- **证据**：

```python
    QUALITY_DOWNGRADE_PATTERN = re.compile(r"(.+?) 画质降级：设置 (.+?)\((.+?)\) 实际 (.+?)\((.+?)\)")
    RECORDING_LINE_PATTERN = re.compile(r"^(.+)\[([^\]]+)\] 正在录制中")
        if "没有正在录制" in msg or "没有正在监测和录制的直播" in msg:
```

```
i18n/en_US.json:295  "{record_name} 画质降级：…"        ->  "{record_name} quality downgraded: set …"
i18n/en_US.json:296  "{recording_live}[{qa}] 正在录制中 …"  ->  "… recording in progress …"
i18n/zh_TW.yaml:231  "正在录制中"                      ->  "正在錄製中"
```

- **机理**：录制子进程按 `config.ini` 的 `language` 经 `i18n.tr()` 输出日志（AGENTS「形参日志必须走 `i18n.tr`」），GUI 却用**未参与翻译的**中文原文做正则与 `in` 判定。`language` 留空时 `resolve_language` 会探测系统语言（本机为空即可能得 `en_US`），用户也可在 GUI 语言菜单切换；任一非 zh_CN 形态下三条模式全部永不命中。
- **影响**：GUI 画质监控表永久显示「暂无」；画质降级告警完全丢失（而降级正是本仓最需要用户可见的静默行为）；「没有正在录制」→ 清除录制标记的分支失效（UI 层 `recording` 标记残留）。全程无任何报错或线索，属「功能整块静默失效」。
- **修复**：优先改**契约**而非改解析——让子进程对这些 UI 消费行输出机器可读前缀（如 `#DLRQ|<name>|<set_code>|<actual_code>`），GUI 只解析该前缀（与语言彻底解耦）；短期方案是 GUI 侧按四语目录构造同一模板的**译文集合**（四份 pattern）取并集匹配，并在语言切换菜单提示「画质/弹幕监控依赖子进程日志，切换后需重启录制」。
- **回归锁**：`tests/test_gui_monitor.py` 增「`i18n` 切至 `en_US` / `zh_TW` 后喂入译文行仍须解析出降级与录制中状态」（现有用例只喂中文原文，属自证）。
- **置信度**：高（目录译文与 GUI pattern 均已回源核对）。

## 四、中等问题（P1，74 项）

> 每条给出：位置 → 机理 → 影响 / 影响面 → 修复方向 → 置信度。**「×× 半修」**表示上一轮该编号的修复只做了一半。

### 4.1 录制主链路与房间线程（`main.py`）— MID-N01 … MID-N15

**MID-N01 ｜ MID-02 的第二判据是死代码：ffmpeg 未开 `stdout=PIPE`，`_ffmpeg_reported_output_failure` 恒返回 False**
`main.py:1010-1012` 的 `Popen` 为 `stdin=PIPE, stderr=subprocess.STDOUT` 且**从未**设 `stdout=PIPE`，故 `main.py:884-886` 的 `stream = proc.stdout; if stream is None: return False` 恒真 → `main.py:1342-1344` 的 `_output_side_failure` 退化为只剩「输出父目录不存在」一条，`_FFMPEG_OUTPUT_FAILURE_MARKERS`（`main.py:869-876`）六个标记全为死代码，`main.py:888` 注释「管道里只剩已缓冲的 error 行」描述的管道并不存在。后果：输出目录被删/只读挂载导致 ffmpeg 秒退时，一条**健康**流地址仍被记进虎牙探针退避（约 190 秒）并投失败样本——即 MID-02 声称消灭的污染原样存在。全仓无任何测试引用该函数。修复：要么承认判据 ② 不可得、删除调用并把判据 ① 补强为「快速失败 + 产物为 0 字节」；要么改 `stdout=PIPE` 并在守护循环内边读边丢（必须消费，否则管道写满会卡死 ffmpeg，反而更糟）。同步改注释。置信度：高。

**MID-N02 ｜ 产物字节数求和与分段转码用未转义的主播名/标题拼 glob 模式，含方括号时保护静默失效**
`main.py:937-953`（`_record_output_bytes`）与 `main.py:1278-1282` 把 `base_stem` 直接当 `pathlib` 的**模式**串。`src/stream_select.py:59-76` 的 `clean_name` 过滤集剔除了 `*`、`?` 但**不含 `[` `]`**，而 `[LIVE]`、`[18+]`、`[官方]` 是 twitch / youtube / 海外标题常见形态 → 该片段被解释为字符类，模式再也匹配不到真实文件。后果双向：① `found=False` → 返回 `-1` → `0 <= _produced_bytes` 恒假，CR-06 的零字节保护对这些房间完全不生效（与 MID-05 修掉的「恒返回 -1」同一后果）；② TS + `converts_to_mp4` 的分段转码静默零提交且无「未找到」告警。修复：改 `os.scandir` + `name.startswith(base_stem + "_")` + `_SEG_INDEX_RE` 纯字符串判定，两处共用一个 `_iter_segment_paths()`。置信度：高（`rstr` 字符集与 pathlib 模式语义均静态可判；具体标题形态未实测）。

**MID-N03 ｜ 录后转码线程池从不 `shutdown`、队列无界：进程退出被转码积压阻塞，日志归档与 ffmpeg 收尾一并推后**
`main.py:803-839` 只有惰性创建与 `submit`，全仓无 `shutdown` / `cancel_futures` 调用点，也无队列上限。`ThreadPoolExecutor` 工作线程非 daemon 且在解释器收尾阶段被 join → 队列里所有待转码任务会在退出时**跑完**（每条单 ffmpeg 最长 600 秒，见 `main.py:806` 注释）。`archive_runtime_logs` 与 `cleanup_all_ffmpeg_processes` 因此被推后，用户强杀进程即丢掉收尾日志。修复：在 `safe_exit` 与 atexit 链最前注册 `shutdown(wait=False, cancel_futures=True)`（非分段的最后一轮做有界等待），并用 `BoundedSemaphore` 给提交侧加软上限（超限告警丢弃转码任务而非排队）。置信度：中（退出顺序为 CPython 实现约定，未本机计时）。

**MID-N04 ｜ 停滞看门狗在「产物文件始终未出现」时永不触发，且注释承诺的兜底在非分段形态下不存在**
`main.py:1122-1143`：`os.path.getsize` 抛 `OSError` 即 `return ""`，于是 `_stall_last_size` 恒为 -1，而判定又要求 `_stall_last_size >= 0`。注释称「交给时长上限阈值兜底」，但 `main.py:1106` 是 `_record_limit_seconds = max_record_seconds if _split_output else 0`——非分段时上限恒为 0。后果：ffmpeg 打开输入后迟迟不创建输出（或输出文件/目录被外部删除）时该房间一直持有 `recording_semaphore` 槽位；分段模式则完全只靠 6 小时上限。修复：`except OSError` 分支改为「`_stall_last_size == -1 且 now - _proc_started_at > _RECORD_STALL_SECONDS` 即判停滞」；并让 `max_record_seconds` 在非分段形态也参与兜底（命中按正常收尾而非失败）。缓解因素：输入侧带 `-rw_timeout`（15 / 50 秒），真正无限挂起少见。置信度：中。

**MID-N05 ｜ `_rename_prefixed_entries` 未处理「目标已存在」，与目录级合并语义不一致，改名半途永久停留旧名**
`main.py:1429-1440` 对标题子目录（`{标题}_{主播}`）与前缀文件用裸 `os.rename`，而顶层 `rename_anchor_directory` 对目标已存在专门走 `_merge_anchor_directory`（`main.py:1377-1382`）。主播改回曾用名（B站 / 抖音常见）时 `FileExistsError` / `ENOTEMPTY` → 被 `except OSError` 降级为一条告警 → 该条目永久停留在旧名，且配置已更新、下一轮不再重试。修复：目录分支复用 `_merge_anchor_directory`；文件分支在目标存在时加 `_N` 后缀或明确告警提示需手工整理。置信度：高。

**MID-N06 ｜ `direct_download_stream` 的 finally 以 `_downloaded == 0` 判定「本函数创建了文件」，`open()` 失败时会删除用户既有产物**
`main.py:739-746` 的注释写的是「仅在 open 已创建文件但一个字节都没写时删除」，判据却是 `_downloaded == 0`。目标为只读文件时 `open(save_path,"wb")` 抛 `PermissionError`，函数从未创建也未截断该文件，`finally` 仍会 `os.remove`。Linux / Docker 下 `os.remove` 只看**目录**写权限，故会真删掉既有录像（Windows 靠只读属性挡住，属平台侥幸）。修复：显式 `_created` 标志（`open` 成功后置 True），`finally` 改判 `if _created and _downloaded == 0`。置信度：中（控制流确定；删除成功依赖 unlink 语义，未实测）。

**MID-N07 ｜ `_app_root()` 非冻结分支取 `sys.argv[0]` 目录：console-script 入口会把配置定位到 `<venv>/Scripts` 并创建空配置**
`main.py:277-291` 返回 `os.path.split(os.path.realpath(sys.argv[0]))[0]`，而同文件 `_read_version_from_pyproject`（`main.py:190`）用 `Path(__file__).parent`——同一模块内两种根目录口径自相矛盾。经 `[project.scripts]`（`douyin-recorder = "main:main"`）安装时 `sys.argv[0]` 是 `<venv>/Scripts/douyin-recorder.exe`，于是 `config_file` 指向 `.venv/Scripts/config/config.ini`；`main.py:4333` 见文件不存在会**创建空 config.ini**，随后缺键补写把默认值填满 → 用户项目根的真实配置被静默忽略、`URL_config.ini` 读不到，表现为「配置全空 / 没有直播间」，并在 venv 里留下垃圾配置。`AGENTS.md`「入口点」表把这三个命令列为正式入口，故非纯理论路径。修复：非冻结分支以 `__file__` 为锚；`src/logger.py::_app_root` 同形态须两处同改。置信度：中（launcher 语义为 setuptools 既定行为，本机以 `python main.py` 为准未实测）。

**MID-N08 ｜ 8 条 resolver 表项写死 `https://` 前缀，白名单准入的 `http://` 地址永久空转（MID-04 半修）**
`main.py:2740-2745`、`main.py:2751`（tiktok / kuaishou / huya / douyu / yy / bilibili / blued 七条整项，加 `main.py:2748` 的 `https://www.xiaohongshu.com/` 片段）。`_match_host`（`main.py:1469-1474`）是整串子串查找，而准入 `main.py:4715-4731` 只补 `://` 缺失的协议、不限协议；故 `http://www.huya.com/123` 能过白名单却落不到任何 resolver → `_resolve_unrecognized` → 睡一轮再试，永不录制、白占监控位，且不投 `record_error` 故调度器也不察觉。`main.py:2815` 的「不可达分支（main() 已按平台白名单过滤）」注释与代码不符。MID-04 本轮为同一失效模式修掉了 xhslink / tlclw / taobao 三处，这 8 处漏改。修复：表项一律去掉协议前缀（与 MID-04 同口径），或在 `_resolve_platform_stream` 入口做一次 scheme 归一；删改 2815 的陈述。置信度：高。

**MID-N09 ｜ `#` + 空格形态的注释行使 `url_comments` 的键与 `record_url` 永不相等，停录只剩单一兜底**
`main.py:4659-4661`：`line = line.lstrip("#")` 只去井号不去其后空格，于是 `url_comments` 里的键是 `" https://live.douyin.com/x"`；而 `src/web_api.py:640`、`src/web_api.py:690` 面板「禁用直播间」写的正是 `"# " + content`。读取侧 `src/web_config.py:118` 与 `src/web_api.py:689` 都做了 `.lstrip("#").strip()`，**只有 main.py 没有**。后果：解析前的「已被注释」快退出（`main.py:3352`）、`check_subprocess` 每秒的注释检查（`main.py:985`）、停滞分支检查（`main.py:1174`）、`clear_record_info` 的 running_list 回收全部恒不命中；停录目前仅靠 `main.py:4778-4780` 的 `running_snapshot` 兜底，而该兜底与文件解析同在 `main.py:4617` 的大 `try` 内——`open(url_config_file)` 被编辑器占用抛错即整段跳过，禁用完全失效。修复：`line = line.lstrip("#").strip()`，并与 web 侧口径写进同一条互指注释。置信度：高。

**MID-N10 ｜ only_flv 平台 + MP3/M4A 音频设置时 `recording` 从不登记，磁盘满退出判定与时间字幕同时失真**
`main.py:3670-3678` 把 `recording.add` 收进 `if not only_flv_record:`（SEV-09 的修复），但分支链第一个 `if` 是音频分支（`main.py:3744` `if only_audio_record or any(i in record_save_type for i in ["MP3","M4A"])`），它先于 `elif only_flv_record:`（`main.py:3789`）命中且自身不做任何登记。shopee / 花椒直播 + 裸 `MP3`/`M4A` 保存类型（实测 `main.py:4578` 白名单同时接受带「音频」与不带的两种写法）时 ffmpeg 正常起，而 `recording` / `recording_time_list` 恒空 → ① 面板与 CLI 恒显未录制、时长画质为空；② `main.py:4594` 的 `if not recording:` 恒真，磁盘满时立即 `sys.exit(-1)` / 引擎 return，正在写盘的文件被硬杀且无录后处理；③ 开「生成时间字幕」时 `generate_subtitles` 因 `record_name not in recording` 立刻退出，静默无 SRT。同源问题：`main.py:1030` 与 `main.py:1058` 两道门按 `"音频" not in save_type` 判定，裸 `MP3`/`M4A` 被当视频 → 纯音频录制仍启动弹幕 WebSocket 与时间字幕线程。修复：抽 `_is_audio_save_type()` 唯一入口，三处（含 SEV-09 守卫）一并复用。置信度：高。

**MID-N11 ｜ `folder_by_time` 用 `now[:10]` 截断 `%y%m%d_%H%M%S` 时间戳，每 10 分钟新建一个目录**
`main.py:3570` 生成 13 字符的 `%y%m%d_%H%M%S`（如 `260921_153700`），`main.py:3588` / `main.py:3593` 取 `[:10]` 得 `260921_153`（日期 + 时 + 分钟十位）。分段名另有 `%Y-%m-%d_%H-%M-%S`（`_SEGMENT_NOW_FORMAT_BY_SAVE_TYPE`），两者互相矛盾可佐证意图；`tests/test_anchor_rename.py:208` 造的日期目录是 `260102`。后果：开「保存文件夹以时间区分」的用户每房间每天多约 144 个目录，`rename_anchor_directory` / `_rename_prefixed_entries` 的递归扫描成本与磁盘碎片同步放大；叠加 `folder_by_title` 时目录名更可预测地错乱。修复：引入独立 `time_folder = today().strftime("%Y-%m-%d")` 供两处使用，勿从文件名时间戳切片。置信度：高。

**MID-N12 ｜ 失败录制轮也置 `record_finished=True`，且 `count_time` 被就地刷新 → 30 秒快检吞掉「瞬时错误太多 +60 秒」退避**
`_run_ffmpeg_record`（`main.py:3218-3243`）的 `started` 只表示「没抛 OSError」，rc != 0 的失败轮同样返回 True，故 `main.py:3781-3785` / `3957` / `3989` 的 `record_finished = True` 与注释所称「rc==0 自然结束」不符（直下路径只在 `download_success` 时置位，`main.py:3881-3882`，与注释所称「对齐」相反）。同时 `count_time` 在 `main.py:4001` 刚刷新过，`main.py:4027-4029` 的 `time.time() - count_time < 60` 恒真 → `x = 30`，把 `main.py:4020-4021` 刚加的 +60 秒退避整笔抹掉。后果：ffmpeg 快速失败（CDN 403 秒退）的房间以约 30 秒节奏重撞「解析 + 探针 + 拉流」，请求率约为设定值（默认 120 秒）的 4～5 倍，方向正与「快速失败记入探针退避以少撞坏线路」的设计相反，直到按 host 熔断开启才被压住。修复：让 `check_subprocess` / `_run_ffmpeg_record` 回传成败，仅成功轮置位；`x = 30` 收敛为 `if sum(error_window) < 5: x = 30`；快检基准改用轮起始时刻。置信度：高（代码判定明确；放大倍数量级未实测）。

**MID-N13 ｜ 拉流 Cookie 转发表与 resolver 实际使用的 cookie 变量不同源，缺 25+ 平台**
`main.py:3528-3554` 的 `platform_cookie` 内联字典只有 23 个键，而 `main()` 每轮读取并交给 resolver 的还有 `twitch_cookie` / `chzzk_cookie` / `youtube_cookie` / `acfun_cookie` / `huajiao_cookie` / `zhihu_cookie` / `taobao_cookie` / `migu_cookie` / `shopee_cookie` / `faceit_cookie` 等。未列入的平台向校验探针与 ffmpeg `-headers` 下发 `cookie=""`，与解析阶段请求指纹不一致 → 需登录 / 会员态的流（粉丝专属、地区限制）表现为「探针可用却拉不到」或整轮放弃。新增 Cookie 键时也无任何机制提醒同步第二处。修复：抽 `platform → cookie 变量` 模块级表（与 `_PLATFORM_RESOLVERS` 同源维护）+ 静态断言用例「resolver 用到的每个 `*_cookie` 必在该表内」。置信度：中（缺项为事实；各 CDN 是否真校验 cookie 未实测）。

**MID-N14 ｜ 录后处理未收敛到统一出口：直下路径完全绕过转码与自定义脚本，FLV 中断轮不转 mp4，并存在第 6 个输出命名点**
① `main.py:3798-3799` 直下分支自行拼 `f"{anchor_name}_{title_in_name}{now}_00.flv"`，成为 `_build_record_output_path` 之外的第 6 个命名点（`_00` 后缀与时间戳格式各写一份，改表即漂移）；② 该分支不调 `_convert_after_record`、也不传 `custom_script`，故 shopee / 花椒用户的「录制完成转 mp4」「录后执行自定义脚本」静默不生效；③ `main.py:3960-3964` 的 FLV 分支 `_convert_after_record` 位于 `if comment_end: return` **之后**，被注释/停止中断的 FLV 成品不转码，而 TS 分支（`main.py:3990-3999`）刻意补了这一步——两类型口径相反。修复：`filename` 由 `_build_record_output_path(..., "FLV", split_video_by_time=False)` 取 basename；直下收尾统一走 `_convert_after_record` 并把 `custom_script` 交给同一出口；FLV 分支与 TS 同构。置信度：高。

**MID-N15 ｜ 轮末等待只被 `recording_enabled` 打断，注释/退出最坏等满整周期**
`main.py:4037-4045` 的 `while x:` 只判 `if not recording_enabled: break`，而循环顶的三个退出条件是 `exit_recording` / `recording_enabled` / `record_url in url_comments`（`main.py:3341-3355`），三者只镜像了第二个；`check_subprocess:985` 与 `main.py:3521` 的等待守卫都已是多条件同构写法。后果：URL 被注释或 Ctrl+C 后，空闲房间仍睡 `delay_default(+60)` 秒才退出，Web 面板这段时间内监控数与线程数不回落，磁盘满收尾同样被拖长。与 MID-N09 叠加时更难察觉。修复：补齐 `or exit_recording or record_url in url_comments`。置信度：高。

### 4.2 平台解析、签名与流地址（`src/spider.py`）— MID-N16 … MID-N30

**MID-N16 ｜ B站 `getRoomPlayInfo` 回退把 `stream` 当 list 索引：一旦触发必然 KeyError，成死回退且伪装为「未开播」**
`src/spider.py:1743-1760`：`stream_list = _playurl.get("stream", [])` 后 `stream_list[0].get("format", [])`。该端点（`src/spider.py:1721` 的 `xlive/web-room/v2/index/getRoomPlayInfo`）的 `playurl.stream` 是按协议键控的对象（`flv` / `hls` / `audi`，每值才是数组），`dict[0]` 抛 `KeyError: 0` → 被 `@trace_error_decorator` 吞成 `{"is_live": False}`；同时 `src/stream.py:1066` 只判 `if not play_url_data`（非空 dict 判不住）。这也是全函数唯一保留裸下标 + 裸 `itemgetter` 的路径，与 MID-48 / WD-19「深层链式索引一律 `_dig`」口径相反。修复：按 `flv` / `hls` 取协议再下钻 `format/codec`，全程 `_dig*`；`stream.py` 侧把判空收紧为 `if not pd.get("url")`。置信度：高（索引形态与端点已核对；接口当前响应形状未实测）。

**MID-N17 ｜ 抖音 `hevc_flv_url` 提取无编码/档位判别却无条件打 `codec=h265`，可能把非原画 H.264 档当原画**
`src/spider.py:435-452`（`_DOUYIN_HEVC_FLV_PATTERN` 只按 `stream-<数字>.flv` 取第一个命中）+ `src/spider.py:561-563`（无 codec 参数即拼 `codec=h265`）。抖音页面内联的 `flv_pull_url`（H.264，含 BD/UHD/SD 各档）同为 `stream-*.flv` 形态且出现在同一段 HTML；`src/stream.py:488-490` 用它无条件替换用户所选原画 FLV。后果双向：① 非原画档被当原画录（`actual_quality` 仍报 OD，静默降质）；② 真 H.264 地址被贴 h265 标记后由 `src/stream_select.py:1043` 以「h265 无法 copy」跳过，反而丢掉可用候选。修复：只接受带 `codec=h265` / `hevc` 标记或就近 JSON 键含 `VCodec=h265` 的地址，并排除已出现在 `flv_pull_url` 值集合中的 URL。置信度：中（缺陷面代码可证，页面同时含哪些 `stream-*.flv` 未实测）。

**MID-N18 ｜ `anchor_name` 取 `.get(...)` 未收敛为 str / 与 `is_live=True` 同时下发空值：把「已取到流地址」的成功轮判成失败（7+ 处）**
`src/spider.py:641`、`810`、`1060`、`1225`（`.get("nickname")` / `.get("nick")` 对显式 `null` 返回 None）；另有 SOOP web、小红书、猫耳三处 `is_live=True` 同时下发空/None 昵称（`src/spider.py:2199-2218`、`2536-2538`、`2573-2577`、`2986-3006`）。`main.py:3392` 以 `not port_info.get("anchor_name")` 作「内容获取失败」硬判据 → 打印失败、整轮丢弃（含已解析出的流地址）、并 `record_error(record_host)`（`main.py:3400`）持续污染按 host 的熔断样本，最坏触发房间地址被自动注释。本文件 `_dig_str`（`src/spider.py:355-360`）注释已明确「主播名只接受 str」，这四处绕开了该口径；MID-48 注释「调用点 `anchor_name or ""` 已容忍」只成立到类型层面。修复：统一 `_dig_str(...)` 或 `... or ""`；无昵称时用平台稳定标识（`bj_id` / `room_id` / 占位串）而非空串。置信度：高。

**MID-N19 ｜ 凭据缓存回填不在锁内，且两个 `invalidate_*` 钩子零生产调用点（MID-33 半修）**
`src/spider.py:237-246` / `277-286`：singleflight 拿到结果后直接写模块全局 `_cached_kuaishou_did*` / `_cached_twitch_client_id*`，不与 `_kuaishou_did_lock` / `_twitch_client_id_lock` 同步；`invalidate_kuaishou_did_cache()` / `invalidate_twitch_client_id_cache()` 全仓 grep 仅 `tests/test_spider_platforms.py:629-630` 调用，无任何生产调用点。后果：被拒值可在失效之后被在途调用者连同**新时间戳**写回、再撑 30 分钟；MID-33 注释宣称的「凭据被拒时主动失效（镜像 `invalidate_bili_buvid_cache`）」对这两个凭据只完成了一半，实际只剩 TTL 兜底。修复：回填时在锁内比对 ts / proxy（或记世代号）；把两个钩子接到各自的「凭据被拒」分支，或删除注释里未兑现的承诺。置信度：高（零调用点可机检；竞态为时序推断）。

**MID-N20 ｜ MID-41 只改了 app 版：web 版仍裸下标 `["origin"]["main"]`，且注释与代码互斥**
`src/spider.py:731-733` 仍是 `cast(dict, cast(dict, parsed_data["origin"])["main"])`，而 app 版（`src/spider.py:873-875`）已改 `.get("main") or {}`，其注释还称「现与同文件姊妹实现 `get_douyin_web_stream_data` 对齐」。抖音残缺响应（`origin` 在而 `main` 缺失 / null）时 `KeyError` 落到 `src/spider.py:753` 的 `except Exception` → 返回 `{"anchor_name": ""}`，**同轮已解析出的 hls / flv 与 hevc_flv_url 一并丢弃**，房间持续「内容获取失败」。修复：web 版同样 `.get("main") or {}`，并在 `origin_url_list` 为空时跳过注入。置信度：高。

**MID-N21 ｜ buvid 缓存的「代理归属」被消费者改写，MID-40 的失效钩子清错键（半条自愈链仍未闭环）**
`src/spider.py:2044-2045` 在**缓存命中**路径也执行 `_bili_buvid_cached_proxy = proxy_addr or ""`，把「值产生时的代理」改写成了「当前消费者所用代理」；随后 `src/platforms/bilibili.py:155` 的无参 `invalidate_bili_buvid_cache()`（`src/spider.py:1889-1908`）按漂移后的 proxy 组键失效，清掉的是从未写入过的键。后果：被弹幕服务器拒绝的 buvid 仍留在真实键（拉取者代理）里到 TTL 过期，下一轮 singleflight 命中又喂回同一份被拒值——正是 MID-40 声称已修的形态，混合代理（部分房间走代理）下可达。修复：只在实际拉取成功的分支写 `_bili_buvid_cached*`；或失效时同时清 `""` 与记录值两个键。置信度：高（代码可证；跨代理交织未实测）。

**MID-N22 ｜ SOOP：`view_url` 缺失仍拼 `?aid=<票据>`，非法地址带着 `is_live=True` 下传**
`src/spider.py:2444-2447` 归因（`_warn_api_abnormal`）后不拦截直接 `return json_data`（可能为 `{}`），`src/spider.py:2719-2726` 随后 `"" + "?aid=" + aid_token` → 相对形态伪 URL 且 `is_live: True`。后果：绕过 `main.py` 的 `if not real_url: continue`（值非空），ffmpeg 拿到 `?aid=…` 直接秒退 → 被 `_FFMPEG_FAST_FAIL_SECONDS` 判为「CDN 快速失败」记进探针退避并 `record_error(host)`；同时 aid 票据出现在畸形 URL 里（该参数不在 `utils._SECRET_KEYS`，见 MIN-N09）。修复：`view_url` 为空即 `return result`（保留已取到的主播名）或抛错交装饰器；禁止空串参与拼接。置信度：高。

**MID-N23 ｜ PopkonTV 主播名两段顺序在两条路径里相反，触发每轮「假改名」+ 目录与配置反复写回**
`src/spider.py:3578-3583` 为 `f"{mc_name}-{anchor_id}"`（search 命中 `mcPartnerCode`），`src/spider.py:3594-3599` 为 `f"{anchor_id}-{mc_name}"`（回落 notices 路径）。同一房间的 `anchor_name` 形态取决于接口是否带出该字段 → `main.py:3418-3441` 的「主播名自动同步」把它当改名，反复 `rename_anchor_directory` + `update_anchor_name` 写 `URL_config.ini`，产物散在两个目录；与仓内其余平台统一的 `昵称-ID` 形态（SOOP / PandaTV / WinkTV / flextv）也不一致。修复：两条路径统一顺序，`mc_name` 为空时用固定占位。置信度：高。

**MID-N24 ｜ TwitCasting「解析失败即登录」兜底已成死代码（异常类型不匹配）**
`src/spider.py:3872-3882` 的 `get_data` 在任一正则未命中时 `raise ValueError("Failed to parse page data")`，而 `src/spider.py:3910-3929` 只 `except AttributeError`（注释称「正则 group 落在 None 上抛 AttributeError 即视为需登录」——该 None 已在 `get_data` 内被转成 ValueError）。后果：受限 / 粉丝限定房间不再自动登录，只能靠用户在 URL 手加 `?login=true`；实际表现为持续「未开播」。修复：`except (AttributeError, ValueError)`，或在 `get_data` 里用可区分类型（如 `LookupError`）标记「页面结构不合预期 → 值得尝试登录」。置信度：高。

**MID-N25 ｜ 微博第二组候选用 `split("_")[0]` 造档位地址，把签名 query 一起切掉；非原画档全落在它上面**
`src/spider.py:4127-4130`：`{"m3u8_url": m3u8_url.split("_")[0] + ".m3u8", "flv_url": flv_url.split("_")[0] + ".flv"}`。`split("_")[0]` 从**整条 URL 的第一个下划线**截断，`?wsSecret=…&wsTime=…` 一并丢失（`wssecret` 正是 `utils._SECRET_KEYS` 里的键，说明确属凭据）；地址无下划线时产出 `xxx.m3u8.m3u8`。`src/stream.py` 的 `_pad_list` 又把列表补到 6 位（复制末元素）。后果：用户选「蓝光 / 超清 / 高清 / 标清 / 流畅」任一档（索引 ≥ 1）拿到的都是已去签名地址 → 探针与 ffmpeg 稳定 403，微博除原画外永远录不上；该处注释「两组都进 play_url_list 由上层按可达性校验」与实际（按索引取一条）不符。修复：只替换 path 并保留 query（`urlsplit` → `path.rsplit("_",1)[0]` → `urlunsplit`）；无下划线时不产出第二候选。置信度：中高。

**MID-N26 ｜ SOOP 两处本地 m3u8 带宽映射缺长度守卫，`zip` 错位会选错画质（注释自称已对齐）**
`src/spider.py:2684-2696`（KR `get_url_list`）与 `src/spider.py:2598-2606`（web 侧）用 `zip(bandwidth_list, play_url_list)` 建映射，而共享实现 `src/spider.py:482` 的 `get_play_url_list` 有 `len(bandwidth_list) == len(play_url_list)` 守卫、理由写明「避免错位映射选错画质」。KR 侧只收 `auth_playlist` 前缀行，一旦平台新增 / 改名变体行即两列表长度不等 → 高带宽号配到低清晰度 URI，`reverse=True` 排序后把低档当 1080p 用（静默降质）。`src/spider.py:2694` 注释却称「此处对齐」。修复：补同一守卫（不等时保留原序），或两处直接改调 `get_play_url_list`。置信度：高。

**MID-N27 ｜ 四个海外平台的账号登录无跨线程去重 / 租约，多房间同账号并发重登**
`src/spider.py:2361`（sooplive）、`3124`（flextv）、`3471`（popkontv）、`3786`（twitcasting）。凭据去重只对 ttwid / 快手 did / Twitch client-id 经 `cookie_cache.singleflight` 做了（`src/spider.py:201-286` 注释明写理由「避免多线程并发时重复拉取触发风控」），账号密码登录这一面完全没有——N 个房间同一轮各发一次登录。后果：单会话服务端（SOOP / Popkon 一类）互相顶掉 cookie → 写回 last-writer-wins → 下一轮旧 cookie 被判失效再登一次，形成稳定循环；账号侧易触发风控 / 改密保护。修复：以 `(platform, username, proxy)` 为键走 singleflight + 结果租约，并让同轮后续房间复用新 cookie。置信度：中（缺口本身确定，真实顶号行为需真机核对）。

**MID-N28 ｜ `get_acfun_sign_params` 同时下发 `cookie` 与 `Cookie` 两个头（httpx 不去重），用户 cookie 与游客 `_did` 互相屏蔽**
`src/spider.py:4830-4837` 用小写 `"cookie": f"_did={did};"`，随后 `if cookies: headers["Cookie"] = cookies`。实测 `httpx.Headers({...}).multi_items()` → `[('cookie','_did=...'), ('cookie','<用户 cookie>')]`，两条头都会发出。RFC 6265 要求单条，CDN / nginx 常只取其一 → 本函数注释自述的「缺失会致 startPlay 返回 401」形态复现（`_did` 与 `did` 查询参数不再配对，或用户 cookie 被忽略），且被 `trace_error_decorator_or_none` 吞成 None。修复：单键拼接 `headers["cookie"] = f"_did={did};{cookies or ''}"`，不再写 `headers["Cookie"]`；同型大小写混用需一并 grep 收敛。置信度：高（双头行为已实测；服务端取舍行为未实测）。

**MID-N29 ｜ VV星球开播判定仅凭「响应非空且不含 `Not Found`」：风控 / HTML 页被误判在播并投成功样本**
`src/spider.py:5406-5419`。`async_req` 对任意 HTTP 状态都返回 `response.text`（无 `raise_for_status`），既不看状态码也不看内容形态。劫持门户 / CDN 5xx 页 / 风控挑战页（非空、不含 "Not Found"）→ `is_live=True`；若昵称接口正常则 `anchor_name` 非空，`main.py:3392` 判「解析成功」→ 上报 `record_success` **污染按 host 熔断统计**，同时每轮拉起必然失败的 ffmpeg。修复：加内容校验（`#EXTM3U` / `#EXTINF`），并改用 HEAD 或 Range 探测而非整份拉取。置信度：高。

**MID-N30 ｜ `get_huajiao_sn` 是零生产调用的死代码，却保留「注释掉用户 URL」的写回副作用（CODE_WIKI 声称已改为显式告警）**
`src/spider.py:4456-4517`，副作用在 `src/spider.py:4513`：`utils.replace_url(".../URL_config.ini", old=url, new="#" + url)`。全仓 grep 只有 `tests/test_spider_hardening.py:835` 按名字列出该函数；`CODE_WIKI.md:5012` 称此类写回已「改为显式 + warning 日志」，但现分支只 `raise RuntimeError`、无 warning → 半修复。风险：一个「静默改写用户配置」的路径长期无人执行、无人真机验证，花椒改版时极易被当成兜底复用，一接上即按解析失败注释用户房间。修复：删除该函数与测试名条目；若保留则写回前补 `logger.warning` 并在函数上方注明无调用点。置信度：高。

### 4.3 选源、画质档位与探针（`src/stream_select.py`、`src/stream.py`）— MID-N31 … MID-N35

**MID-N31 ｜ h265 判定口径三套并存：`_is_h265` 精确匹配 `h265`，而写侧值可能是 `hevc`**
`src/stream_select.py:319-321`（`codec[0] == "h265"`）与 `main.py:3740`（同精确匹配）；而 `src/stream.py:555-557` 写的是 `url_value + "?codec=" + v_codec`（`v_codec = sdk_params["VCodec"]`），`src/stream.py:485` 自己的判据却是 `"h265" in m3u8_codec.lower() or "hevc" in m3u8_codec.lower()`。后果：`codec=hevc` 形态的 HEVC 源不被候选序列剔除、也不触发 main.py 的 FLV→TS 切换 → HEVC 直接 `-c copy` 进 FLV/MP4，正是 `_is_h265` 注释声称要防的「伪装成普通 FLV 通过全部校验」。修复：`_is_h265` 收敛为 `(codec[0] or "").lower() in ("h265","hevc")` 并与 `main.py:3740` 复用同一入口（`AGENTS.md`「hevc_flv_url 必须带 codec=h265 标记」条须同步更新为同一集合）。置信度：中高（口径分叉确定；线上取值域未实测）。

**MID-N32 ｜ HLS 分片探测与同源回退的 5 处日志未过 `mask_credentials`，带 token 的签名直链明文落轮转日志**
`src/stream_select.py:447-454`、`464-471`、`475-481`、`494-500`、`1085` 直传 `url=playlist_url` / `url=seg_url` / `url=same_origin`，而同文件另有 24 处一律 `url=utils.mask_credentials(...)`（实测 grep 计数）。斗鱼 `wsAuth`、抖音 `signature` 就挂在这些 query 上；`logs/streamget.log` 按 300 KB 轮转保留多份并可能被归档 / 外发。修复：这 5 处实参统一包 `utils.mask_credentials(...)`（占位符名不动，不动四语目录）。置信度：高。

**MID-N33 ｜ TikTok 无 FLV 候选时 `quality_index` 被 FLV 侧钳成 0：请求画质静默失效，且「还有更低档」判定用硬编码 4**
`src/stream.py:608-612`：`quality_index = min(quality_index, len(flv_url_list) - 1) if flv_url_list else 0` → MID-16 注释自述「只下发 hls 路时 flv 侧是一串 `{"url": ""}`」被过滤为空列表后索引恒 0，`m3u8_quality_index = min(0, ...)` 恒取**最高码率档**；抖音分支（`src/stream.py:478-479`）是对两列各自钳制，TikTok 未沿用。`src/stream.py:625` 又用 `quality_index < 4` 而非 `len(list)-1` 判定是否还有更低档。后果：请求「流畅 / 标清」的 TikTok 房间实录原画，`actual_quality` 回采 OD 使 `is_downgrade("LD","OD")` 恒假 → 无降级告警，面板只显示 OD。修复：保留未钳制的 `wanted` 索引供 HLS 用；`fallback_index` 改按列表长度。置信度：高。

**MID-N34 ｜ 虎牙旧档位（超清 / 高清 / 标清 / 流畅）在防盗链缺 `&exsphd=` 时整块跳过：不拼 ratio 却把 `actual_quality` 写成请求档（MID-13 / 14 半修）**
`src/stream.py:766-768` 先置 `actual_quality = video_quality`，档位推导弹在 `src/stream.py:816-840` 的 `elif len(quality_list) > 1 and video_quality not in ["OD","BD"]`，而 `quality_list = first_anti.split("&exsphd=")` 无该字段时长度为 1 → 整个 elif 不进入：既不推导 ratio（实为原画拉流）、不告警，`available_qualities` 也保持 None。BD 子档位分支同场景会用 `gameLiveInfo.bitRate` 推导（`src/stream.py:777-778`），两分支口径分叉。后果：「URL 挂着原画、面板显示按超清录」的静默降级被完全伪装——正是 MID-14 立论要消灭的形态。修复：条件放开为 `video_quality not in ("OD","BD")`，无 exsphd 时与 BD 分支同源（bitRate 推导 + `huya_code_for_ratio`）并保留降级告警。置信度：高（代码路径）/ 中（线上 exsphd 缺失频率）。

**MID-N35 ｜ 抖音 / TikTok 画质预检的 `get_response_status` 不带 UA 与录制请求头，与探针 / ffmpeg 三级口径矛盾**
`src/stream.py:495`、`src/stream.py:622` 调用时只传 `url` / `proxy` / `platform`，而 `src/async_http.py:345-348` 明确「UA 仍由调用方经 headers 下发」（`AGENTS.md` 要求同步 / 异步校验器的 proxy / verify / UA 三者一致）。预检遂以 `python-httpx` 默认 UA 出网，CDN 偶发 403 即判不可达 → 走相邻档降级（`src/stream.py:499-515`、`624-631`），用户静默丢失请求画质；随后 `select_source_url` 用 `MOBILE_UA` 又能探通，两级校验结论互相矛盾。修复：预检传 `get_record_user_agent(platform) or MOBILE_UA` + `get_record_headers(...)`。置信度：中高。

### 4.4 HTTP 客户端、代理与凭据生命周期 — MID-N36 … MID-N41

**MID-N36 ｜ `sync_req` 直连分支的响应体解压与读取均无上限（MI-01 只修了 WS 侧）**
`src/sync_http.py:241-248` 裸 `gzip.decompress(_resp.read())`。`src/ws_client.py::decompress_limited`（MI-01）的立论正是「1000:1 压缩比可把几百 KB 展开成 GB 级对象」，同一形态在同步 HTTP 出口保留至今；代理分支（requests 自动解压）同样不设限。影响面：约 125 处 `sync_req` 调用点（即所有平台解析）的响应体外部可控，单个畸形响应即可打爆与录制主流程同进程的内存。修复：直连分支复用 `decompress_limited`（或下沉到公共模块）并对 `_resp.read()` 加字节上限；代理分支改 `stream=True` + `iter_content` 累计计数。置信度：高。

**MID-N37 ｜ 单标签代理主机名被 `ProxyDetector` 拒绝，却已先把 `global_proxy` 置 True：海外平台按「有代理」分支实际直连**
`src/proxy.py:63-67` 的 `domain_pattern` 要求至少一个点，故 `HTTP_PROXY=http://corp-proxy:3128`、compose 服务名 `squid:8080`、注册表 `ProxyServer=proxy:8080`（企业 NetBIOS 名，本仓常见部署）全部抛 `ValueError`；`_get_proxy_info_linux`（`src/proxy.py:202-214`）无 try，Windows 侧 `return ProxyInfo(...)` 在 try 之外。`main.py:4275-4277` 先 `global_proxy = pd.is_proxy_enabled()`（已 True）再取地址，异常被 `main.py:4281` 的 `except Exception` 降成一行 `print`。后果：50+ 处 `if global_proxy or proxy_address:` 分支（如 `main.py:2139`、`2171`）以 `proxy_addr=None` 执行真实直连请求——在必须经代理出网的部署下 TikTok / Twitch / Popkon 等海外平台解析全败，唯一线索是那行 print。与已记录的「布尔漂移致 9 个海外平台 100% 无法录制」同一失效形态。修复：放行单标签主机名（`^[a-zA-Z0-9][a-zA-Z0-9\-_]{0,62}$`），或校验失败时返回空 `ProxyInfo()` 并把 `global_proxy` 回退 False——`_is_proxy_enabled_*` 与 `_get_proxy_info_*` 必须成对成立。置信度：高（抛型已实测）。

**MID-N38 ｜ `_fetch_ttwid` 返回模块全局而非本次拉取结果：失败被伪装成成功并被缓存，且跨代理串用凭据**
`src/ttwid.py:102-123`：拉取失败或响应无 ttwid 时不写缓存，函数结尾仍 `return _cached_ttwid`（与其自身第 103 行注释「失败返回空字符串」相反）→ 返回的可能是另一代理作用域刚写入的值。后果：① 对 `singleflight` 呈现为非空成功，按 TTL 缓存 30 分钟、本轮不再重试；② 直连房间复用代理出口下发的 ttwid（IP 相关性凭据串用），正是本模块要消除的「200 + 空响应体」风控形态。`tests/test_ttwid.py` 只在手工清空 `_cached_ttwid` 的前提下断言返回 `""`，未覆盖该路径。修复：返回本次局部变量（未取到即 `""`），由 `get_ttwid` 再以该值写全局。置信度：高。

**MID-N39 ｜ cookie 世代号是全局单计数：单键失效会连坐丢弃所有在途结果，反而放大重复请求**
`src/cookie_cache.py:69`（单一 `_cache_generation`）、`223-226` / `364-370`（写回仅比对「世代是否变过」）、`378-411`（`invalidate()` / `invalidate_generic(key)` / `clear()` 三处都整体 +1）。B 站弹幕 AUTH 被拒（`_reject_auth` / `_auth_watchdog` 每轮可触发）经 `invalidate_generic` 递增世代 → 同期在途的抖音 ttwid / 快手 did / 首页 cookie 拉取结果全部**静默**不落缓存，下一轮重新请求同一批主页——恰好放大本模块存在的理由（重复请求触发风控）。修复：改为按键世代 `dict[str, int]`（或 cookie / generic 各一份计数），并在丢弃时记一条 debug；只有 `clear()` 允许整体递增。置信度：中高。

**MID-N40 ｜ 心跳超时日志改用别名 `_log` + f-string：i18n 形参日志门禁对该调用点完全失明，且该串未入四语目录**
`src/ws_client.py:371-376`：`from loguru import logger as _log` + `_log.warning(f"[ws_client] 心跳回调超时 ({...:.0f}s),…")`。`tests/test_i18n_migration.py:129-132` 的判据是 `node.func.value.id == "logger"`，`_log` 不匹配（实测 grep：全仓 `from loguru import` 的其余 14 处都叫 `logger`）；`grep -rn 心跳回调超时 i18n/` 四语目录 + `.mo` **0 命中**。后果：① en_US / en_GB / zh_TW 下该告警恒为中文原文；② 「换个别名即可绕过门禁」这条路径无人守（MID-68 同族盲区的新形态）。修复：改用模块级 `logger` + `i18n.tr(模板, seconds=...)` 并同步四目录 + `compile_po.py`；把门禁谓词扩为「callee 名为 `logger` 或以 `_log` / `loguru` 结尾的 Name」并加自检用例（防门禁自身假绿）。置信度：高。

**MID-N41 ｜ `_session()` 注释宣称「sync_req 的必经路径」，直连分支实际走 urllib：线程级连接复用只在配代理时生效**
`src/sync_http.py:97-105`（注释）对照 `src/sync_http.py:203-235`：无代理时走 `_get_opener(ssl_verify).open(req, ...)`，`abroad=True` 分支更直接用 `urllib.request.urlopen`，均不经过 `_session()`。后果双向：① 默认（不配代理）部署下直连路径每轮每次请求重做 TCP+TLS，80+ 房间时是可观的连接 / FD churn（`AGENTS.md` 记的实测口径是 8× 退化）；② `AGENTS.md`「`requests.Session` 必须线程级复用（约 125 个调用点）」与 `urllib3>=2.7.0` 显式下限的立论（「本仓全部同步出站 HTTP 都穿过它」）在默认配置下并不成立，会误导后续改动与安全评估。修复：直连分支也走 `_session()`（配 `trust_env=False` 保留「不吃系统代理」语义），或明确声明直连刻意用 urllib 并同步修正注释与 `AGENTS.md` 表述。置信度：高。

### 4.5 Web 面板、配置写入与房间接口（`src/web_api.py`、`src/web_config.py`）— MID-N42 … MID-N45

**MID-N42 ｜ Origin 同源判定复用为 Host 头设计的宽松名单：任意 IP 字面量、无点主机名放行，且忽略端口**
`src/web_api.py:1119-1141` 把 Origin 的 netloc 交给 `src/web_config.py:695-715` 的 `is_host_allowed`，其第 ②③ 条放行「任何 IP 字面量」与「任何不含点的单标签名」，且 `_strip_host_port`（`src/web_config.py:270-280`）丢弃端口。于是 `http://192.168.1.47/`（局域网任意设备页面）、`http://localhost:3000/`（本机任意 dev server）都判为「同源」；FastAPI 不校验请求 Content-Type，`text/plain` + JSON 正文属 simple request 可免预检送达。影响：认证关闭（**出厂默认**）时同源校验是写接口唯一防线，故本机任意网页或局域网任意设备页面可静默改配置、加房间、启停录制。修复：为 Origin 单列判定——host 与端口都须等于 `web_host:web_port`（或在 `web_allowed_hosts` 显式登记的 host:port），不复用 IP / 无点宽松规则；Host 头那条保持现状。置信度：高（代码路径确定，未实跑浏览器行为）。

**MID-N43 ｜ `update_room_quality` 的读-改-写不在锁内（H-6 半修），且跨进程本就不互斥**
`src/web_config.py:579-599`：`path.open(...).readlines()` 与整段重算都在 `with _config_write_lock:` **之外**，锁只包住最后的 `_atomic_write_text`；注释却写「无锁时两次 read-modify-write 交错会丢失一次变更」。两次并发调用仍可用同一旧快照互相覆盖并都回报 `changed: true`。另外 `_config_write_lock` 是进程内 RLock，而 `gui.py:1868`（GUI）与录制 / Web 是两个进程，跨进程不互斥；同一文件另由 `config_io.update_file` 经 `main.file_update_lock` 保护——两把锁保护同一文件。修复：整段 RMW 移进锁内；跨进程改用具名文件锁（`msvcrt.locking` / `fcntl`）或与 `file_update_lock` 合并为同一把；至少先更正注释以免后人误以为已闭合。置信度：高。

**MID-N44 ｜ `update_room` / `toggle_room` 丢弃 `update_file` 返回值并恒回 `ok:true`（SEV-05 只修了删除路径）**
`src/web_api.py:642-651` 与 `691-697`：`_ = _main.update_file(...)` 后无条件 `replaced = True` / `return {"ok": True, ...}`，而 `src/config_io.py:64` 在读失败、内容为空、`_atomic_write_text` 返回 False（Windows 目标被占用 / 只读）时**返回 old_str 即静默 no-op**。`delete_room`（`src/web_api.py:669-674`）已按 SEV-05 加了「重解析复核」，这两个端点没有。后果：停用 / 改写房间失败时面板提示成功，该房间继续录制并占盘占并发槽，故障不可观测——与 SEV-05 完全同形。修复：与 `delete_room` 同口径，持锁重新 `parse_url_config` 复核目标行的 `enabled` / URL 是否已变成期望值，失败走 `_log_internal_error` + 500。置信度：高。

**MID-N45 ｜ 推送 / SMTP / 代理 URL 类配置键零校验：与 SEV-03 同一信任边界的第二条 SSRF 出口**
`src/web_api.py:106-107` 的 `_DANGEROUS_CONFIG_KEYS` 只含「自定义脚本执行命令」；`PUT /api/config`（`src/web_api.py:753-852`）对值只做 `_reject_newline`，无 scheme 与目标网段判定。而 `钉钉/微信/bark推送接口链接`、`ntfy推送地址`、`smtp邮件服务器`、`代理地址` 会被 `msg_push.py:97/133/329/408` 用 urllib opener 直接请求，且 `api.replace("，", ",").split(",")` 支持**逗号分隔多目标**；房间 URL 那套 `_host_internal_reason`（http/https 限定 + 内网 / 元数据拦截）完全没有覆盖到这里。这些全局量在 `main.py:4487-4505` 的热重载循环内每轮重读 → 无需重启即可让服务端向 `http://127.0.0.1:6379/`、`http://169.254.169.254/` 发起带可控 JSON 正文的 POST（内网探测），或把推送地址改成攻击者主机从而外泄房间名与直播间地址。修复：这些键复用 `_validate_room_url_target` 同款 scheme + 内网收口，并列入「写入需二次确认」的受限集合；`smtp邮件服务器` 按主机名判定。置信度：高（写入口与 sink 均已回源；非 http scheme 能否命中未实测，不计入本条）。

### 4.6 弹幕采集、监控枢纽与 SRT 写入 — MID-N46 … MID-N50

**MID-N46 ｜ `room_message` 的惰性建房会「复活」已被 `room_stopped` 移除的房间，重新引入旧房间残留**
`src/danmaku_monitor.py:350-359` 对未知房间无条件 `_default_state("未知")` 建条目。全仓 grep 确认 `room_message` 唯一生产者是 `collector._on_message` 且必然在 `room_started` 之后调用，故该分支没有正当消费者，只会在「房间已 `room_stopped` 弹出、采集线程仍在收尾或已泄漏（见 SEV-N01）」时命中 → 与 `AGENTS.md` 第 8 条要消灭的「已失效直播间永久残留」同形（GUI 侧 `_danmaku_dispatch` 的 `setdefault` 同样会把行加回来），且平台名退化为「未知」、`started_at` 被重置，而 `_stats_thread` 可能已 break 使该行永不刷新。修复：未知房间丢弃或仅记 debug；若需容错 `room_started` 失败，用「本线程已 stop 过的房间集合」门控。置信度：高。

**MID-N47 ｜ 抖音 `WebcastRoomUserSeqMessage` 被 `pass` 丢弃，与模块头自述矛盾且在线人数恒 0（WD-20 半修）**
`src/platforms/douyin.py:247-252` 的 `elif method == METHOD_ONLINE: pass  # 在线人数不进 SRT` 理由不成立——`src/collector.py:449-451` 在 SRT 分支**之前**就把全部类型转发给监控枢纽（SRT 过滤已在采集器完成）。`src/platforms/douyin.py:8` 的模块头声明该消息 → 在线人数(ONLINE)，实现里却从未 `_emit`，正是 WD-20（B站 / 虎牙 `data` 透传）要修的同一表现。修复：解出 `RoomUserSeqMessage` 并 `_emit(ONLINE, data=int(seq.total))`，同步补 `src/proto/douyin_pb2.pyi` 存根字段（`AGENTS.md` protoc 存根约定）。置信度：高。

**MID-N48 ｜ `SrtWriter.close()` 非终止：迟到写会重开已关闭文件并使块号从 1 复位**
`src/srt_writer.py:106-118`（`_open_segment` 复位 `_index` / `_last_end`）与 `153-159`（`_fp is None` 即按 10 秒节流重试，初值 0.0 使首次立即重试）。`close()` 只置 `_fp=None`、无 `_closed` 标志。当 `src/collector.py:233-236` 的 sentinel 因队列满投不进、`join(3s)` 超时后 `close()` 已执行，写线程随后每条都会**立即重开**同一 `.srt` 续写 → 同一文件内出现两套重复块号与非单调时间轴（MIN-24① 要守的不变量在 close 之后仍可破），且 `stop()` 那条「尾部弹幕可能未落盘」告警在此形态下反而失真。修复：`close()` 置 `_closed`，`write()` 首行早返回；重开路径保留 `_index` / `_last_end`。置信度：中高。

**MID-N49 ｜ 写失败（磁盘满）后 `_fp` 不清空，WD-03 的节流自愈永不触发**
`src/srt_writer.py:180-182` 的 `_fp.write()` / `flush()` 抛 `OSError` 时句柄保持非 None，而自愈分支（`src/srt_writer.py:153`）只认 `self._fp is None`；`src/collector.py:423-438` 的 `except Exception` 只计数不重置句柄。后果：磁盘满 → 用户清理空间后，本片剩余弹幕仍永久丢失，必须等到下一个分片边界（默认 1800 秒）才恢复，与该文件「瞬时故障恢复后需要自愈」的注释目标相反。修复：写 / flush 抛 `OSError` 时 `_close_locked()` 置空句柄，交给既有 10 秒节流重试；同步修正 `src/srt_writer.py:154` 注释为覆盖「open 失败 / 写失败 / 已 close」三态。置信度：中高。

**MID-N50 ｜ `_reject_auth` 用裸 `asyncio.ensure_future`，与本文件 `spawn_danmaku_task` 约定相反（弱引用可被 GC）**
`src/platforms/bilibili.py:148-157`：`asyncio.ensure_future(self._ws.close())`。同文件 `src/platforms/bilibili.py:93`、`122` 已按 2026-09-12 审查改用 `spawn_danmaku_task`，理由（asyncio 只弱引用任务、异常无人取走）在此完全适用，这里是该约定唯一的漏点。后果：进房被拒后若采集线程随即收尾，弱引用关闭任务可能在 `ws.close()` 前被 GC → 连接与 buvid 拒绝信号双双丢失、缓存失效却永不重连；异常形态退化为 stderr 一行 `Task exception was never retrieved`。修复：改 `spawn_danmaku_task(self._ws.close())`（`stop()` / `_shutdown` 路径已有超时保护）。置信度：高。

### 4.7 GUI 与 i18n / 推送（`gui.py`、`msg_push.py`）— MID-N51 … MID-N53

**MID-N51 ｜ WD-21 半修：`_read_output` 的正常 EOF 主路径仍裸写 `self.running = False`**
`gui.py:2758-2761` 对照同函数两条 except 路径（`gui.py:2783`、`gui.py:2792`）已改 `self._mark_session_stopped(session_id)`，而 `gui.py:2720-2728` 的注释明写「三处收尾直接写 `self.running = False` 却没做校验」。出现频率最高的 EOF 主路径漏改 → 「停止 → 立刻再启动」竞态下旧线程把**新会话**的 `running` 打成 False，刷新间隔从 3 秒退化为 10 秒，且不产生任何日志（WD-21 自述的幽灵故障原样复现）。修复：该行改为 `self._mark_session_stopped(session_id)`。置信度：高。

**MID-N52 ｜ `start_recording` 的 except 分支可孤儿化已启动的录制子进程**
`gui.py:2514-2569`：`subprocess.Popen(record_cmd, ...)` 之后的若干步（线程 `start`、`_start_danmaku_tail`、`_log`）都在同一 `try` 内，任一抛错（如 `can't start new thread`）时 except 只重置 UI 并 `self.process = None`，不回杀 `proc`。已带隐藏控制台运行的录制核心无人认领、无法从 GUI 停止，孤儿 ffmpeg 持续拉流写盘；`_cleanup_zombie_ffmpeg` 因 target_pid 已清空只打「未发现」。修复：except 中若 `proc` 已绑定则走 `_send_stop_signal_and_wait` / `taskkill /T` 清理路径。置信度：高（路径确定，触发概率低但后果重）。

**MID-N53 ｜ URL 配置页保存缺少「写前重读磁盘」核对，与 MID-55 的 config.ini 口径不对称**
`gui.py:2288-2304` 的 `save_config()` 直接 `_save_text_widget_to_file(...)`，不比对磁盘快照；外部变更检测只靠 3～10 秒一轮的 `_watch_url_config`。而 `gui.py:756-776`（config.ini 页）已按 MID-55 实现 `_config_change_verdict`。后果：录制引擎刚写回（自动注释坏 URL / 画质段）而 watcher 尚未跑到的窗口内点「保存」，编辑器旧快照整文件覆盖、丢失更新。修复：保存前重读磁盘与基线比对，dirty 则弹确认（与 config.ini 页同构）。置信度：高。

### 4.8 基础设施：安装器、配置 I/O、日志、后处理 — MID-N54 … MID-N58

**MID-N54 ｜ `check_nodejs_installed` 只捕 `FileNotFoundError`：node 卡住 / 权限异常会让 `import src` 在启动期硬崩溃**
`src/node_install.py:275-286` 对照 `src/ffmpeg_install.py:514-546`（后者完整覆盖 `TimeoutExpired` / `OSError` / `Exception` 三档并各带告警）。`subprocess.run(["node","-v"], timeout=15)` 在 node 存在但卡住时抛 `TimeoutExpired`，命中目录 / 无执行位 / exec format 时抛 `OSError`，`check_node()`（`src/node_install.py:288-292`）与调用方 `src/__init__.py:39-41` 都没有 try。后果：该调用位于 `src/` **包导入期** → 任何一次超时 / 权限异常直接让 `import src`（进而 `main.py` / `gui.py` / `web.py`）崩在启动阶段，且发生在文件日志链路建立之前。`src/__init__.py:36-38` 的注释正是要避免「子进程管道偶发失败导致导入崩溃」，但兜底只加在开关上、没加在函数里。修复：与 ffmpeg 版对齐补三档 except（返 False 触发自动安装），并在 `src/__init__.py` 外层加 `except Exception` 记 warning 后继续。置信度：高。

**MID-N55 ｜ 缺键补写与 `update_config` 都以「内存解析器整份 dump」为唯一内容源：抹掉 config.ini 全部注释，并可回滚他人写入**
`src/utils.py:543-578`（`update_config`）与 `src/config_io.py:256-287`（`read_config_value` 的缺键写回）都是 `config.read(...)` → 改一键 → `config.write(buf)` → 原子写。实测 `configparser` 的 `write()` 丢弃全部整行注释（带 `# doc` 的文本 read→write 后注释为 0），写回前也不重读磁盘。触发点分两类：① `src/utils.py` 这份是**运行期常态**——SOOP / Flextv / Popkon / TwitCasting（`main.py:1824/1963/2018/2057`）与淘宝（`src/spider.py:5904`）每次 cookie / token 刷新都会重写整份 config.ini；② `src/config_io.py` 这份在升级到带新键的版本后首启触发，且调用方传入的可能是热加载替换前的旧 parser（MID-09 靠整体重绑 `main.config` 实现，查找与取锁之间可被替换），此时会静默回滚窗口内 Web 面板与其它写入方的落盘结果。README 文档化的配置注释块因此变成裸键值（`_sync_ssl_disable_platforms` / `update_config_line` 特意实现的「保留注释」在这条路径上失效）。另：`update_config` 自身不持锁，靠调用点自觉 `with file_update_lock`（本机 5 处调用点均正确，但 `web_config._config_write_lock` 是另一把锁，新调用点漏一次即失去互斥）。修复：写回前持 `file_update_lock` 重读磁盘，仅对被改的单个键走行级追加 / 替换（复用 `web_config.update_config_line` / `append_config_line`）；并把持锁下沉进 `update_config` 内部（`file_update_lock` 是 RLock 可重入）。置信度：高（注释丢失已实测）。

**MID-N56 ｜ 蓝奏云兜底安装的 ffmpeg 落点与 `ffmpeg_path` / PATH 注入不一致；zip 内容可直接覆盖 `config/`**
`src/ffmpeg_install.py:377-381`：蓝奏云分支把归档直接解到 `execute_dir` 根，随后注入 PATH 的却是 `execute_dir/ffmpeg`（可能不存在）；官方源分支经 `copytree(bin_dir, execute_dir/ffmpeg)` 平铺，故 `main.py:520-522` 的 PATH 前置对它有效。自检只因 Windows `CreateProcess` 额外搜索「exe 所在目录 / CWD」而偶然通过。后果：CWD ≠ 项目根（服务化拉起、从别处启动）时自检假失败；成功时产物散落应用根目录、下次启动不被 PATH 命中；zip 内若含 `config/...` 会直接覆盖用户配置（`unzip_file` 只拦逃出 `extract_to` 的路径）。另 `src/ffmpeg_install.py:46` 注释称产物在 `ffmpeg/bin/ffmpeg.exe`，与实际平铺不符。修复：蓝奏云分支同样先解到临时目录、定位含 `ffmpeg.exe` 的目录后 `copytree` 进 `ffmpeg_path`，并改正注释。置信度：中高（zip 内部布局未实拉验证）。

**MID-N57 ｜ 配置备份的脱敏少一道判据：`_looks_like_secret_value` 未被复用（CR-10 双口径只落一道）**
`src/config_io.py:335-354` 只按键名 / 节判敏感（`is_sensitive_item(section, key)`），而面板侧 `src/web_config.py:775-779` 在 CR-10 已升级为「键名 / 节命中 **或** 值本身形如凭据」。凭据键名滞后于平台命名时，真实凭据会按 CR-07 的设计保留 6 份副本常驻 `backup_config/`——该目录正是用户最易整体打包 / 云同步外发的位置。修复：`if value.strip() and (is_sensitive_item(...) or _looks_like_secret_value(value))`（与 `web_config` 同源导入，勿再复制一份判据）。置信度：高（当前工作副本实测「仅值形态命中」为 0 条，故属潜在面而非已发生泄露）。

**MID-N58 ｜ `remove_duplicate_lines` 缺 `newline=""`：每次启动把 `URL_config.ini` 整文件 CRLF→LF 并吃掉行首尾空白（MI-11 半修）**
`src/utils.py:595-617`：读侧走 universal newlines（`\r\n`→`\n`）、键取 `line.strip()`、写侧统一 `"\n"`；该函数由 `main.py:4320-4321` 在每次 `main()` 启动时无条件调用。同族缺陷 MI-11 已在 `config_io.update_file` / `delete_line` / `update_anchor_name` 三处补 `newline=""`，`src/utils.py:687` 的 `replace_url` 也补了并注明理由，唯独这里漏了。后果：以 VCS 管理 `URL_config.ini` 的用户每次启动产生全文件 diff；与 SEV-05 依赖的「保留各行原始行尾」口径分叉。修复：`open(..., newline="")` + 键用 `rstrip("\r\n")` 去重、值原样写回（含原 eol），无变更时跳过写盘。置信度：高。

### 4.9 前端（`web/app.js`、`web/index.html`）— MID-N59 … MID-N61

**MID-N59 ｜ 标签页隐藏后状态轮询永不恢复：`stopSSE()` 置的停止标志又被恢复判定读回（WD-10 半修）**
`web/app.js:1518-1529`：隐藏时 `stopSSE()`，回到前台 `if (!sseStopped) startSSE();`；而 `web/app.js:684-685` 的 `stopSSE()` 内部就写 `sseStopped = true`，只有 `startSSE`（`web/app.js:653`）才置 false → 恢复分支恒不成立。弹幕轮询按 `.view` 可见性判断、没有这个缺陷，形成不对称。后果：用户最小化 / 切走标签页一次再切回来，仪表盘 `/api/status` 与录制列表**永久停在最后一次数据**且无任何提示——正是 `web/app.js:1516-1517` 注释宣称要解决的「陈旧数据」场景；只有再点一次 tab 才恢复。修复：引入与停止标志分离的「上次是否在轮询」意图位（`sseWanted`），隐藏时只 `clearTimeout` 不改 `sseStopped`，可见时按意图位恢复；补 `visibilitychange` 前端用例（现有用例未覆盖）。置信度：高。

**MID-N60 ｜ `#config-container` 带 `data-i18n`：切换语言会把整张动态配置表单替换成占位文本，未保存编辑全丢**
`web/index.html:135` `<div id="config-container" data-i18n="loading">加载中...</div>`，而 `web/app.js:509-513` 的 `applyTranslations()` 对每个 `[data-i18n]` 节点执行 `textContent = t(key)`；该容器是 `loadConfig()` 全部 `input` 的父节点（`web/app.js:1192`、`1237`、`1256`），语言下拉的 change 处理器（`web/app.js:550`）会调用它。后果：用户在「配置」页改到一半点顶栏切换语言 → 表单被替换成「加载中…」文本，未保存编辑全部丢失且页面看起来像卡死；此时点「保存配置」会因取到 0 个 input 而 toast「无变更」，用户以为已保存。修复：去掉容器上的 `data-i18n`，把首屏占位改成子节点 `<div class="config-hint" data-i18n="loading">…</div>`（仍满足「HTML 无未入目录中文」门禁）；或语言切换后按当前视图重跑 `loadConfig()`。置信度：高。

**MID-N61 ｜ 主题 / 语言读写裸用 `localStorage`：存储被禁用时前端初始化整体中断（与本文件 `_tokenStore` 的既有结论自相矛盾）**
`web/app.js:1413`、`1424`、`537-538`、`542`、`550`。`web/app.js:34-45` 的注释已经认定「Safari 无痕 / 禁用站点数据会把 storage 访问变成抛异常」并为 token 做了 `_tokenStore()` 兜底，主题与语言却没有；`initTheme()` 是 `DOMContentLoaded` 回调的第一条语句（`web/app.js:1430-1431`）。后果：禁用站点数据的浏览器里 `initTheme()` 抛出 → 回调整体中断 → tab 切换 / 保存 / 登录 / 事件委托一个都没绑定、启动引导也不执行，面板呈「可见但全失效」的死页面（不是降级，是硬崩）。`initLanguage` 的 `.then` 抛出后其 `.catch` 再次直连 `localStorage` → 二次抛出，`applyTranslations()` 永不执行。修复：新增同族 `prefStore()`（try/catch 包裹 get/set，失败静默返回默认值），四处改用它。置信度：高。

### 4.10 构建、CI、门禁脚本与测试可信度 — MID-N62 … MID-N74

**MID-N62 ｜ `build_exe.py` 把 `config/*.ini`（含凭据）整目录复制进发布产物：分发链只补了镜像那一半**
`build_exe.py:202-207` 的 `shutil.copytree(cfg_src, cfg_dst, dirs_exist_ok=True)` 无任何裁剪，而镜像侧有 `.dockerignore` 的 `config/config.ini` / `config/URL_config.ini` 两道。后果：维护者按 `AGENTS.md`「构建命令」在本地跑 `python build_exe.py` / `--dual` 时，生成的 zip 内含本机 Cookie / 代理 / Web 密码，随后手工分发即外泄（`v*` tag 触发的官方发布链是干净 checkout，不受影响，故风险面是「本地构建后手工分发」）。修复：`ignore=shutil.ignore_patterns("config.ini","URL_config.ini")`，或只复制模板文件并打印被排除清单。置信度：高。

**MID-N63 ｜ `workflow_dispatch` 手动复跑会被 paths-filter 全量跳过，而 `ci-summary`（唯一 required check）判绿**
`.github/workflows/ci.yml:187,282,363,395,517,557,618` 七个重 job 的 `if` 无条件依赖 `contains(fromJSON(needs.setup.outputs.filters), 'python')`，无 dispatch 例外；`ci-summary`（`:683-691`）的失败集合只含 `failure` / `cancelled`，注释还明确「skipped 视为通过」。后果：dispatch 时 `paths-filter` 无 PR base、只能与上一提交比对，「不改代码复跑全部门禁」（本文件 `:77` 自述目的）会得到 required check 全绿而 black / isort / mypy / pytest / 打包冒烟一条未跑。修复：每处改 `if: github.event_name == 'workflow_dispatch' || contains(...)`；或让 `ci-summary` 在 dispatch 下把「全 skipped」判失败。置信度：中高。

**MID-N64 ｜ 冒烟工具「0 条检查」仍退 0，`_ci_web_smoke.sh` 直接把它当结论**
`scripts/smoke_test.py:80-82`（`typed.get("checks", [])`）+ `scripts/smoke_test.py:367-372`（`sys.exit(1 if failed else 0)`，注释自认「零检查也会退出 0」）；`scripts/_ci_web_smoke.sh:85-88` 直接采信 rc。2026-09-12 的 6.7 只加固了「顶层类型非法」一半，`{"checks": []}`、键名误写为 `check`、配置文件被清空都落到 `checks=[]`。后果：CI Web 冒烟只剩 `/health` 就绪轮询，接口断言归零却 rc=0——正是本仓「无数据即失败」（MIN-19 / `check_runtime_pins.py` rc=2）明令禁止的形态。修复：`load_config` 对 `not checks` 抛 `ValueError`（走既有 rc=2），或 `main()` 在 `total == 0` 时 `sys.exit(2)`。置信度：高。

**MID-N65 ｜ `--dual` 的 full 版无「产物齐全」自检：ffmpeg 可能零落盘仍报成功并进入对外分发 zip**
`build_exe.py:451-512`：三分支里外层 `break` 无条件在 `iterdir()` 首个条目后生效（顺序不保证），而分支结束一律 `return True`、`download_runtime_binaries` 又忽略返回值。上游 zip / tar 顶层结构一变（多一个 LICENSE、`bin/` 改名）即一个文件都不复制。后果：对外分发的 full zip 可以「解压即用」名义缺 ffmpeg / ffprobe 且全程无告警（冒烟跑在 lite 目录之前，抓不到）；钉定哈希只证明字节一致，不证明解出了可执行文件。修复：三分支收尾统一断言 `ffmpeg[.exe]` 与 `ffprobe` 均为文件，否则 `SystemExit`；Linux 分支把 `break` 改为「未命中则 `continue`」。置信度：高（今日未爆是因为上游 tarball 恰好只有一个顶层目录）。

**MID-N66 ｜ `scripts/extract_i18n_strings.py` 被 `AGENTS.md` 列为「i18n 三件套门禁」之一，却恒 `return 0`**
`scripts/extract_i18n_strings.py:170-192`：缺失清单、`[不一致]` 四目录键差异都只 `print`，末尾无条件 `return 0`。后果：该门禁不具备任何拦截能力；「`color_obj.print_colored` / `messagebox` 提取器扫不到、只能靠对账」这条防线（`AGENTS.md` 2026-09-18 定稿）也因此不会让 CI 或本地回路变红——本轮 MIN-N33 那 5 条漏登记文案正是它本该拦下的形态。修复：`missing` 非空或存在 `[不一致]` 时返回 1（保留 2 = 目录文件读不到）；若刻意只做人读工具，须在文件头与 `AGENTS.md` 改写「门禁」措辞以免被误当防线。置信度：高。

**MID-N67 ｜ `scripts/patch_i18n_2026_09_12.py`：绝对路径写死 + 注释宣称透传 rc 实际恒 0，且属应清理的一次性脚本残留**
`scripts/patch_i18n_2026_09_12.py:23`（`ROOT = Path("D:/DouyinLiveRecorder-dev")`）与 `:228-233`（`print("compile_po returncode:", ...)` 后 `return 0`）。后果：该脚本在他机 / CI 上会把 `append_po()` 写错目标或直接崩溃却对外报「已同步」；`.mo` 编译失败时四语目录与 `.mo` 静默分叉（幸有 `compile_po.py --check` 兜住 CI）。`subprocess.run(["python", ...])` 未用 `sys.executable`。同时它属 `AGENTS.md`「测试收尾清理临时脚本」口径下不得留在 `scripts/` 的残留物（该条目要求：只有需长期复用的排查工具才进 `scripts/`）。修复：`return res.returncode`、`ROOT = Path(__file__).resolve().parent.parent`、`[sys.executable, ...]`，或按收尾约定删除并由 `check_version` / i18n 用例接管。置信度：高。

**MID-N68 ｜ 测试卫生门禁 R1 看不见 `patch("a.b.c")` 字符串形态，仓内 17 处仍替换 stdlib 模块本体（MID-66 半修）**
`tests/test_test_hygiene.py:106-114` 的注释写「`patch("a.b.c")` 的字符串形态不参与本规则……而这类写法在本仓未使用」——实测为假：`patch("subprocess.Popen")` 3 处（`tests/test_main_fixes.py:173,179,185`）、`patch("subprocess.run")` 3 处（`tests/test_spider_fixes.py:97,118,147`）、`patch("<mod>.time.sleep")` 11 处（`tests/test_main_fixes.py` 5 + `tests/test_stream_select.py` 6）。`mock.patch` 解析后对 stdlib 模块 setattr，与 R1 禁止的 `setattr(main.time,"sleep",...)` 完全同效（`src.stream_select.time` 就是 stdlib `time` 本体）。影响：全进程 stdlib 被换，harness 守护线程的 `subprocess.run`、loguru、coverage 同吃替身——`AGENTS.md` 记载的 `SAFE_DELETE_BULK_GUARD_ERROR` 正是该形态；且门禁给出「已防 MID-66」的假保证。修复：R1 增扫 `patch` / `patch.object` 的字符串目标（末段属性属 stdlib / 三方模块名即计违规），并把上述调用改成 `SimpleNamespace` 替身（`AGENTS.md` 已给出标准写法）。置信度：高。

**MID-N69 ｜ 本地门禁入口 `run_gates.run_command` 及其 UTF-8 / env 前缀路径零覆盖（`AGENTS.md` 已点名待补）**
`tests/test_run_gates.py:9` 明确把 `run_command` 排除在被测面外（实测 grep：`run_command|ensure_utf8|split_env_prefix|extract_gate_env|FATAL_STDERR` 在该文件 0 命中）。而被排除的恰是 MID-63 与「`PYTHONUTF8` 必须同时覆盖子进程和转发输出的父进程」两条已定稿防线：`ensure_utf8_streams`（black 通过时那行 `All done! ✨ 🍰 ✨` 曾让 cp936 下的转发抛 `UnicodeEncodeError` 直接炸掉门禁进程）、`split_env_prefix` / `extract_gate_env`（`PYTHONUTF8=1` → 子进程环境）、`FATAL_STDERR_PATTERNS` 的「rc=0 仍判失败」。后果：门禁工具退化成「rc=0 就绿」或转发输出即崩时，pytest 全绿无人报警。修复：用一条真子进程命令（打印 emoji + `Unable to parse file`）覆盖 hits / env / 崩溃三点。置信度：高。

**MID-N70 ｜ 「`.m3u8` 判定必须 `lower()`」这条已修致命坑没有任何回归锁**
`tests/test_ffmpeg_reconnect_args.py:98-107` 的守卫只要求 `ast.If` 的 test 里含 `.m3u8` 字面 + body 有 `Delete`，故 `if ".m3u8" in url:` 与 `if ".m3u8" in url.lower():` 同样通过；`tests/test_start_record_command_golden.py:134-135` 的黄金用例也只有小写形态。后果：把 `main.py:3166` 的 `.lower()` 删掉（即 2026-09-12 修掉的「大写 `.M3U8` → 播放列表 EOF 无限重连、零字节、进程不退出」）→ 门禁与 20 个黄金用例全绿。修复：断言 `node.test` 里出现 `.lower()`，或大小写各一条黄金用例。置信度：高。

**MID-N71 ｜ 黄金快照只冻结命令列表、丢弃 `platform` / `danmaku_args`，弹幕接线的现形态失防**
`tests/test_start_record_command_golden.py:328-340`：`check_subprocess` 替身 `cap.commands.append(list(ffmpeg_command))` 收下 `platform` / `danmaku_args` 即丢；`tests/test_danmaku_wiring.py` 全部直接调 `check_subprocess`，不经 `start_record` 分支。后果：任一保存类型分支把 `record_danmaku_args`（或 `platform`）漏传成 None → 该类型的弹幕 / SRT 静默不产出，`run_gates` + 20 例黄金全绿（`AGENTS.md`「接线点」约定的现形态无锁）。修复：`_Cap` 记 `{command, platform, danmaku_args, save_type}` 并 `GOLDEN_REGEN=1` 重生成。置信度：高。

**MID-N72 ｜ 「凭据绝不入日志」用例的假 logger 不收 `info` / `debug`，与断言文案「任何级别」不符**
`tests/test_spider_hardening.py:88-103` 的桩只把 `warning/error/exception/log` 汇入 `msgs`（`info=Mock(), debug=Mock(), success=Mock()`），而 `tests/test_spider_hardening.py:857-859` 的注释声明「登录态 cookie 的值任何级别日志都不得带出」。后果：`logger.debug("... cookie=%s", cookie)` 类回归全绿；而 `logs/streamget.log` 收 DEBUG 且轮转留多份 = 凭据长期落盘，这正是凭据红线的实际漏口（`src/logger.py` 的分档即 INFO→`PlayURL.log`、其余→`streamget.log`）。修复：`info` / `debug` / `success` 也接同一 sink（归因断言仍只看 warning 档）。置信度：高。

**MID-N73 ｜ `config_bool` 的 Python 与前端 JS token 集合无交叉锁（`AGENTS.md`「五处同源」里唯一没锁的一处）**
`tests/test_config_bool.py:36-43` 与 `tests/frontend/test_quality_ui.mjs:415-423` 各自硬编码同一串列表，没有任何用例把 `src/config_bool.TRUE_TOKENS` 与 `web/app.js` 的 `CONFIG_TRUE_TOKENS` 键集对齐。`AGENTS.md`「布尔配置统一解析口径」明确要求「改任一侧须同步另一侧」，而 i18n 四目录键集反而有锁。后果：只改一侧（例如 Python 认 `enable` 而前端不认）→ 面板显示与引擎生效值相反，全部测试仍绿。修复：`.mjs` 已能用 `node:vm` 求值出 `CONFIG_TRUE_TOKENS`，导出其键与 `python -c` 读到的 frozenset 比较（或 py 侧正则扫 `app.js` 键集）。置信度：高。

**MID-N74 ｜ standalone 单文件版与 `src/` / `main.py` 的五项行为漂移，其中配置读取与探针退避为功能性缺失**
`scripts/douyin_live_recorder_standalone.py` 刻意不 import `src/`（`AGENTS.md` 已记其 `PlatformBreaker` 副本**不等价**为刻意，本条不含该项），但以下漂移未在册：
① `:1485-1500` / `:1533-1568` 读的配置键名与 `config/config.ini` 实际键**不匹配**（`是否启用代理` vs `是否使用代理ip(是/否)`、`视频保存路径` vs `直播保存路径(不填则默认)` 等 5+ 处，4 个 cookie 键还读错节），且布尔只认 `startswith("是")`——文件头 usage 明写 `--config config/config.ini`，用户设的代理 / 路径 / 格式 / cookie 全部静默走默认（与 2026-09-17 记录的「布尔漂移致海外平台 100% 无法录制」同一失效形态）；
② `:1673-1686` 缺「ffmpeg 快速失败 → 探针退避」闭环（`_mark_probe_reject` 只在探针路径调用），违反 `AGENTS.md`「录制结果反馈约定」硬要求，虎牙 aldirect 实测形态下每轮重撞死线路；
③ `:1208` 的 m3u8 判定无 `.lower()`（同文件 `:1363`、`:1456` 已按小写判定，即 MID-N70 描述的同族失效）；
④ `:1255-1258` 探针异常直接判不可达（`src/stream_select.py:809-816` 的末位放行未回灌），另缺 `_probe_hls_segment`（HLS 分片层探测）与 `_is_recordable_url`（MID-19 形态白名单）两个整体能力；
⑤ `:1319` / `:1428-1452` 的 ffmpeg 标志集缺 `-thread_queue_size` / `-probesize` / `-analyzeduration` / `-bufsize` / `-max_muxing_queue_size` / `-fflags +discardcorrupt` / `-protocol_whitelist` / `-hide_banner`，注释却自称「标志集与原工程 `main.py` 一致」。
修复：按 `AGENTS.md`「两处同改」口径逐条回灌，或把注释与文件头 usage 降级为「配置键集与标志集为子集，差异如下」，并对 ①②补机检（键名与 `config/config.ini` 交叉断言）。置信度：高（①⑤已逐项比对）。

## 五、轻微问题（P2，50 项）

> 触发面窄、需特定平台响应形态、或属可观测性 / 命名一致性问题。位置与片段由各分组审查提供；本章按「一处一条」保留，便于逐条核修与后续 grep 对账。

### 5.1 平台解析与网络层（MIN-N01 … MIN-N20）

| 编号 | 位置 | 问题 | 影响 | 修复方向 |
| --- | --- | --- | --- | --- |
| MIN-N01 | `src/spider.py:1506-1524` | YY 把远端 HTML 正则抠出的 `cid` 字符串直接拼进 JSON 请求体（非 `json.dumps`） | 页面改版 / 被注入时 `"` `}` 可提前闭合结构，改写 `client_type` / `h265` / `gear` 或让请求整体非法且无因 | `re.fullmatch(r"\d{1,32}", cid)` + dict + `json.dumps` |
| MIN-N02 | `src/spider.py:1349-1356` | 斗鱼签名迭代次数 `enc_time` 取自远端 JSON 且无上限（`bool` 亦满足 `isinstance(int)`） | 异常 / 被劫持响应可长时间霸占该房间事件循环，同线程其它协程停摆且无日志 | `max(0, min(int(v), 10))`，越界告警按 0 处理 |
| MIN-N03 | `src/spider.py:1647-1654` | B站房间信息失败日志直传 `url=`，未过 `mask_credentials`（同函数兄弟路径都过） | 带临时票据的房间 URL 明文进 300 KB 轮转日志，违反脱敏红线 | `url=utils.mask_credentials(url)`，`e` 一并脱敏 |
| MIN-N04 | `src/spider.py:1418-1424` | 斗鱼 betard 告警用字符串拼接作 `logger.warning` 首参 | 落 MID-68 收紧后的门禁盲区：永不进四语目录，非中文语言恒为原文 | 改 `i18n.tr(常量模板, rid=..., reason=...)` 并登记四目录 |
| MIN-N05 | `src/spider.py:404-421` | `_is_safe_http_url` 注释称「允许 webcal/ws(s)」，而 `utils._SAFE_URL_SCHEMES` 无 webcal | 该封装虽零调用，但注释是后续接线者判断边界的依据 | 删 webcal 或改为「以 `utils._SAFE_URL_SCHEMES` 为唯一事实源」 |
| MIN-N06 | `src/spider.py:963-991` | TikTok：SIGI_STATE 标签在但内容被截断时 `_loads_dict` 回 `{}` 并立即返回，绕过自身 3 次重试与内置 cookie 告警 | `{}` 与「确实无数据」不可区分，过期游客 cookie 的典型形态落进静默路径 | 解析为空则 `continue` 计入重试，耗尽后再告警抛错 |
| MIN-N07 | `src/spider.py:2925-2927`、`3045-3047`、`3307-3308`、`4278-4279` | `f"{_dig(...)}-{...}"` 未判 None，渲染成 `None-123` | 目录 / 文件名出现 `None` 字面量，并触发一次假「改名」同步 | 统一 `_dig_str` + 占位串，数值字段先 `str()` 再判空 |
| MIN-N08 | `src/spider.py:2857-2866` | 千度热播三条正则均硬依赖 `\r\n`（CRLF） | 页面经 CDN 归一为 LF 或被压缩即永久「未开播」，无任何线索 | 行尾改 `\r?\n`，失配补 `_warn_api_abnormal` |
| MIN-N09 | `src/spider.py:2439-2440`、`2721` | SOOP CDN 分配接口硬编码 `http://`；`aid` 票据未进 `utils._SECRET_KEYS` | 明文取得 CDN 反盗链票据并可被路径上的代理 / 落盘日志看到 | 端点改 https（按「禁用SSL证书验证的平台」口径登记）+ `aid` 入黑名单 |
| MIN-N10 | `src/spider.py:2255-2266`、`2296-2299` | bigo `split("&amp;h=")[-1]` 未命中时把整条 URL 当房间号；兜底 URL 按 `split("/")[3]` 取段 | `siteId` 传垃圾值，与「房间不存在」不可区分；短链形态取错段 | 用 `partition` 显式判命中；复用已解析的 `web_url` |
| MIN-N11 | `src/spider.py:4762-4771` | ShowRoom `room_id = url.split("room_id=")[-1]` 未剥尾部 query | `room_id=123&...` 时 API 收到畸形参数，永久判未开播且归因指向改版 | 改用现成的 `get_params(url, "room_id")` |
| MIN-N12 | `src/spider.py:4804-4813`、`5256-5258` | 对 `get_play_url_list` 结果无条件前缀拼接（helper 契约明确可能返回绝对地址）；showroom 侧未先剥 `?` | master 清单改绝对 URI 即拼出 `https://host/https://host/…`，全候选校验失败整轮放弃 | 统一 `urllib.parse.urljoin(base.split("?")[0], i)` |
| MIN-N13 | `src/spider.py:5696-5716` | Shopee：`session_id` 为 None 仍请求 `/api/v1/session/None` 并 `logger.error` 提示「地址失效」 | 未开播被提示成「换地址」，误导排障；每轮多发一次注定失败的请求 | `if not session_id: return result`，`result` 侧再判空 |
| MIN-N14 | `src/spider.py:5649-5669` + `112-120` | Shopee API host 后缀取自重定向落点且无站点白名单；`_shopee_host_suffix` 用 `split("/")[2]` 取 host | `shp.ee` 短链落点由第三方决定，可越出 Shopee 站点集合并注入拉流地址（SEV-06 的残留边界） | 后缀枚举白名单校验，不匹配即按未开播返回 |
| MIN-N15 | `src/spider.py:6095` | Faceit `re.findall(...)[0]` 裸下标（本段其余处均 `re.search` + 判空抛错） | URL 形态变化即 IndexError，被装饰器伪装成「未开播」且缺区分性线索 | 改 `re.search` + 判空抛 ValueError |
| MIN-N16 | `src/spider.py:6214-6224`、`5277-5283` | 咪咕 JS 失败与嗨秀 token 读取失败均为宽泛 `except Exception`，无 `from e`、无日志；错误文案未写完（「…check if the Node.js environment」） | 签名脚本哈希校验失败（MID-62 面）与「node 未装」不可分辨；用户配的覆盖 token 被静默当作未设置 | 补 `logger.warning(tr(..., type_name=..., err=...))` + `raise ... from e`，补全文案 |
| MIN-N17 | `src/spider.py:6283-6288` | 连接直播用 `replace("?", ".flv?")` 造地址，无 `?` 时退化、多个 `?` 时误替换 query | 两路地址退化为一路且无扩展名，上层 HLS/FLV 判定与 `-segment_format` 选择失去依据 | `urlsplit` / `urlunsplit` 分别处理 path 与 query |
| MIN-N18 | `src/stream_select.py:150-156` + 调用点 `:617` | `get_record_headers` 形参 `live_url` 在选源内部传的是**候选流地址**（main 侧传房间 URL）；`rule=="origin"` 且 live_url 为空时 `split(":",1)` 解包 ValueError，且该调用点在 `try` 之外 | shopee 的 origin 两端不同（违反「探针与 ffmpeg 用同一请求头」）；空值形态抛穿 | 为 `select_source_url` / `_validate_stream_url` 增传房间 URL；改 `elif rule and ":" in rule:` |
| MIN-N19 | `src/stream.py:1121-1124` | 网易CC `list(flv_url_list.keys())[0]` 对空 `cdn` 无判空（同函数对 `sorted_keys` 有判空并选择透传上游） | 异常被装饰器吞成 `{"is_live": False}`，表现为「明明在播却持续漏录」 | 空 cdn 时 `return json_data`，与该函数「不伪造 is_live」口径一致 |
| MIN-N20 | `src/proxy.py:24-37`、`75`、`202-214` | `proxy_url` / `user` / `password` 零生产调用点（MIN-20③ 半修）；`proxy_url` 强制 `http://` 丢掉 socks 方案；`all_proxy` / `ftp_proxy` 也参与 `is_proxy_enabled` 判定 | 认证代理与 SOCKS 系统代理不可用；该属性含凭据，一旦被日志引用即泄漏（当前无调用点，属潜在面） | 保留 scheme 字段驱动 `proxy_url`；把 `proxy_url` 接进 `main.py` 代理装配处，或明确标注仅测试用 |

### 5.2 配置 I/O、弹幕字幕、GUI 与前端（MIN-N21 … MIN-N40）

| 编号 | 位置 | 问题 | 影响 | 修复方向 |
| --- | --- | --- | --- | --- |
| MIN-N21 | `src/platforms/_tars.py:67-76`、`88-118` | CR-03 边界硬化半修：`_skip`（STRING1/STRING4/SIMPLE_LIST）与 `_take_head`（tag==15 扩展字节）仍裸索引；LIST/MAP 只判上界不判负 | 截断帧抛 `IndexError`（实测 `b'\x06'`）而非可捕获的 `ValueError`，畸形虎牙弹幕归因混乱 | 长度消费前补 `self._need(1/4)`；改判 `if not 0 <= n <= len(self._data)` |
| MIN-N22 | `src/ttwid.py:13-15`、`61-63` | H-2 重构后 `_ttwid_lock` 已无任何生产 acquire 点，但模块头注释、`AGENTS.md` 第 7 条与 `tests/test_concurrency.py::test_ttwid_module_pattern` 仍按「跨 await 持有的凭据去重锁」描述 | 后续读者会据注释以为 ttwid 仍由锁保护并为其新增持锁代码，重新引入跨房间阻塞；回归锁保护的是不再生效的机制 | 删除该锁与头注释，用例改断言「`get_ttwid` 走 singleflight、锁内零 await」，同步 `AGENTS.md` |
| MIN-N23 | `src/async_http.py:170-212` | `close_all_clients_sync` 丢弃 loop 引用后无条件 `await client.aclose()`，正是 2026-09-04 决策列举的第三种禁行形态；而本仓循环全在房间线程，主线程 atexit 通常无可用循环 | `src/async_http.py:121` 与 `AGENTS.md` 承诺的「进程级收尾由 close_all_clients_sync 负责」不成立；若某线程退出时确有非运行循环（`collector.py:300-302` 有 `set_event_loop` 先例），会以被禁方式执行并吐一串被吞掉的 RuntimeError | 按 `loop is get_running_loop() and not loop.is_closed()` 过滤，其余只丢引用；同步修正注释与 `AGENTS.md` 说法 |
| MIN-N24 | `src/web_config.py:603-615` | 本模块自带的 `_atomic_write_text` 缺 `src/utils.py:464` 版已加固的三件事（写后 `flush+fsync`、`replace` 后 fsync 父目录、`tempfile.mkstemp` 唯一命名），临时名仅带 `os.getpid()` | 掉电 / 内核崩溃时可留下「新目录项 + 未落盘数据页」的 0 字节配置——写的正是含凭据的 `config.ini` 与 `URL_config.ini`（MID-57 半修）；同进程多线程并发时可撞名 | 删本地副本，三处调用改走 `utils.atomic_write_text`（utils 在依赖链最底层，不构成循环导入） |
| MIN-N25 | `src/web_api.py:611-612` | `add_room` 直接 `open(..., "a")` 追加，不补末行换行；而 `web_config.append_config_line:896` 对同一场景显式处理 | 手工编辑留下的无末行换行文件会让新房间与原末行粘成一行：原最后一间静默消失、新房间也不命中，面板仍回 `ok:true`（已核对 `utf-8-sig` 追加不写 BOM，故无 BOM 类问题） | 追加前读末字节判断补 `\n`，或改走持锁 RMW |
| MIN-N26 | `src/web_config.py:641` 对照 `src/web_api.py:770` | `[Web]` 节名判定口径两侧不一致：读取侧 `parser.has_section("Web")` 精确匹配，写入侧守卫 `section.strip().lower()=="web"` 不敏感 | 写成 `[web]` / `[WEB]` 时 `read_web_config` 整体回退默认（认证关、密码空、绑定 127.0.0.1），而写侧仍能命中该行并回报成功；`SENSITIVE_SECTIONS` 节名精确匹配同理 | 按 `optionxform` 同口径先做节名归一（或读到多个 `web*` 节时告警），两侧复用同一归一化 |
| MIN-N27 | `src/web_api.py:186-260`、`web.py:280` | 写接口无长度上限（模型无 `max_length`，`validate_config_target` 只挡换行），`uvicorn.Config` 无 `limit_concurrency` / body 上限 | 一次写入数十 MB 即让磁盘上配置永久膨胀，录制引擎每个检测周期都付出该解析代价（认证关闭时零门槛） | `key/section/value` 与房间字段加 `max_length`；拒绝超长单行值；设 `limit_concurrency` |
| MIN-N28 | `src/danmaku_monitor.py:28-32`、`414-424` | `_RECENT_BUFFER_SIZE=500` 为**全局**缓冲，而 `_STREAM_SAMPLE_PER_SEC=10` 是按房间；80 房间满采样即 800 条/秒（约 0.6 秒窗口），前端固定 2 秒轮询 | 高并发下 Web 弹幕大面积缺失且**无任何可见信号**（客户端只见 `last_seq` 前跳），`truncated` 只表示「本次命中 >200 条」不表示空洞——违背本模块「丢弃必须可观测」口径（WD-02 / MID-25）。GUI 走 JSONL tail 不受影响 | 游标落后于最旧保留条目时回 `lost` 字段；或让容量随房间数 × 采样率 × 轮询周期伸缩 |
| MIN-N29 | `src/platforms/douyin.py:201-206` + `src/ttwid.py:169-180` | 多房间同轮各调 `invalidate_ttwid()`，既不做「缓存里仍是这支凭据」的 CAS，也无跨轮冷却 | A 拉到新值后 B 的 invalidate 又清掉 → 各房间串行各拉一次抖音主页，恰构成本模块注释自己点名的风控触发源；签名类故障被误判为 200 拒绝时放大为每轮 N 次 | `invalidate_ttwid(expected_value=...)` 加值比较 + 进程级最小失效间隔（如 60s） |
| MIN-N30 | `src/platforms/__init__.py:3-9` + `src/__init__.py:59-74` | 包 `__init__` 顶层急切 re-export 五个平台类，而 `bilibili.py:16` 顶层 `import brotli`、`douyin.py:30` 顶层 `import douyin_pb2` | `src/__init__.py` 注释宣称的「按需惰性」只到包导入层为止：只录抖音的房间也要一次性拉起 brotli / protobuf / websockets；单个可选重依赖缺失时 `main.py:1051` 的 except 会把**所有**平台的弹幕一起静默打成 debug 级失败（与 `AGENTS.md`「依赖缺失表现为收集期 ModuleNotFoundError、极易误判」同族）。生产代码无任何地方需要这五个名字（已 grep） | 改 PEP 562 `__getattr__` 惰性导出（保留 `__all__`），或直接删 re-export |
| MIN-N31 | `src/srt_writer.py:51-52` | `_sanitize_srt_text` 只挡 `\r` / `\n` / `-->`，未覆盖 Python `str.splitlines()` 认可的 `\v \f \x1c-\x1e \x85 \u2028 \u2029` | 下游若用 `splitlines()` / 逐行正则解析 SRT（转码、清洗、二次导入），块结构与时间轴可被外部输入截断（ffmpeg/subrip 主路径不受影响，故轻微） | 同一「替换而非删除」口径下并入这些码点（或过滤 `Cc/Cf/Zl/Zp`），并扩现有注入回归用例 |
| MIN-N32 | `src/platforms/bilibili.py:59-81` + `src/ws_client.py:279-280` | 多 host 轮转时每支 `WsClient` 重连耗尽都触发同一个 `on_close` | 面板 / JSONL 出现 `closed`→`ready` 抖动，`_seq` 与统计被无意义推高，排查时误判「连上过又掉了」（base.py:89-97 的 `_on_reconnect` 正是为消除这类假事件而设，但 host 轮转这一层未纳入） | 非末位 host 传 `on_close=self._on_reconnect`（或 None），仅末位耗尽时上报 |
| MIN-N33 | `gui.py:783`、`1860-1862`、`1871`、`2454`、`2459-2462` | 5 条 `messagebox` 文案未登记四语目录（实测逐条 grep 0 命中），且 GUI 用「录制已在运行中！」而目录登记的是不带「！」版本 | 目录对账长期假绿；带/不带叹号两个版本键文漂移不可达（同窗口期其它框语都已登记，唯独这批漏网）——正是 `extract_i18n_strings` 扫不到 `messagebox` 的实际后果（MID-N66） | 五处源串补登四目录并重编译 `.mo`；统一叹号形态 |
| MIN-N34 | `msg_push.py:122-158` | `xizhi` 函数自称支持 Server酱，却按 `resp_data.get("code") == 200` 判成功；sctapi 成功响应为 `code:0`（且错误字段是 `message` 非 `msg`），只有息知回 200 | 配 Server酱的用户每次**成功**推送都被计入 error 并打「微信推送失败」告警，求助时误导排障方向 | 判据放宽为 `code in (200, 0)` 或按 host 分渠道判定，注释同步 |
| MIN-N35 | `web/app.js:631-641`、`web/index.html:33` | 登录成功后不清空 `#login-password`（全文件对该 input 只读不写），也无 `autocomplete="off"` | 面板**全局访问密码**（非短效 bearer）长期驻留在只是被 `.hidden` 隐藏的 DOM 里；借设备 / 远程调试 / 任何 DOM 读取即可拿到，bearer 过期后它还能直接换回有效 token | 成功分支加 `$('login-password').value=''`，input 补 `autocomplete="off"` |
| MIN-N36 | `web/app.js:923-926` + `src/danmaku_monitor.py:213`、`460-462` | 前端 `dmLastSeq` 只增不减，而服务端 `_seq` 是进程内计数器（重启归零） | 不重载页面的重连（登出再登录、服务重启后回面板）表现为弹幕区一直「暂无数据」而房间表正常——极易误判为「平台不再推弹幕」的静默失败 | `if (lastSeq < dmLastSeq) { dmLastSeq=0; dmMessages=[]; }`，或在 `showLogin()` 里清零游标与缓冲 |
| MIN-N37 | `web/app.js:677-683`（调用点 `:662`） | `markBackendUnreachable` 把「已断开」写进 `#danmaku-stream`（弹幕视图元素），仪表盘自身无反馈，且无复位路径 | ① 仪表盘断连时用户看不到任何提示，与注释「把已断开状态显式呈现给用户」相反；② 一次瞬时失败会在弹幕页留下与弹幕无关的陈旧文案 | 在 `dashboard-view` 内增设专用提示位（或复用 `#engine-warning` 显隐）并成对写 true/false；勿跨视图写 DOM |
| MIN-N38 | `src/javascript/liveme.js:348`、`371`、`381`、`385`、`412`、`414`；隐式全局 `317`、`332`、`373`、`406`、`415` | 每次签名把**含内嵌密钥的派生串**与全量入参 `console.log` 到 stdout；5 处无声明赋值（隐式全局） | 当前不泄漏只因 `exejs` 取「最后一行非空输出」解析结果，而本仓另一条 JS 执行入口 `utils.run_node_script_async` 返回**整段 stdout**（`src/utils.py:185`）——一旦 liveme 改走该路径（migu 即是），解析结果立即被污染成密钥文本，且 `trace_error_decorator` 兜底记 `str(e)` 时可能把它带进轮转日志；隐式全局使任何加严（`'use strict'`）直接 ReferenceError | 删除 6 条 `console.log`（或置于 `process.env.DLR_JS_DEBUG` 之后），5 处补 `const/let` |
| MIN-N39 | `src/javascript/haixiu.js:532-539`、`511-520` | 尾部注释留有成套真实形态入参（含疑似 `accessToken`），且 `bnu` / `bn` 引用 Node 下不存在的 jQuery `$` | 与已计数的 补-03 / 补-04 同类，但这是**有调用点的在用文件**（`src/spider.py:5319`），随源码对外分发；`bnu`/`bn` 一旦被复用即抛 ReferenceError | 样例值改 `<REDACTED>`、删除或重写死代码；改后须同步 `utils._JS_SHA256_EXPECTED["haixiu.js"]`（否则 `DLR_JS_STRICT_HASH=1` 部署拒绝执行） |
| MIN-N40 | `index.html:18-19`、`158-163`、`231-236` | 根 `index.html`：CDN 脚本无 `integrity` / `crossorigin`；`httpToHttps()` 无条件强改；原生 HLS 分支 `play().catch(()=>{})` 静默 | 版本已钉但内容未钉（CDN 劫毒 / 换包不可察觉）；纯 http 流被改写后播放失败且报错指向流本身。该页不经面板路由（`src/web_api.py:1001-1003` 服务的是 `web/index.html`），风险限于用户本地打开，故轻微 | 两个 `script` 补 SRI + crossorigin；改写失败后回退原地址重试；`video` 加 `error` 监听给提示 |

### 5.3 构建、CI、门禁与仓库卫生（MIN-N41 … MIN-N50）

| 编号 | 位置 | 问题 | 影响 | 修复方向 |
| --- | --- | --- | --- | --- |
| MIN-N41 | `src/video_postprocess.py:242-270`、`:146` | MIN-04 的「超时放大 + 半成品清理」只落在 `converts_mp4`：`converts_m4a` / `segment_video` 仍固定 600 秒（音频是 `aac` 重编码，长分段可超），三个 except 分支都不清理半截产物 | 产物目录同时留下可用源文件与打不开的半成品，用户按文件名挑选时可拿到不可播文件 | 统一 `_convert_timeout(..., re_encoding=...)`；按「启动前取 `out_pre_existed`」口径调 `_discard_partial_output` |
| MIN-N42 | `src/config_io.py:74-94` | `update_file` 读失败只捕 `(RuntimeError, UnicodeDecodeError)`，同模块 `delete_line:205` / `update_anchor_name:132` 都捕 `OSError` | 文件被占用（Windows 共享冲突）/ 被换走时异常直接穿出，既不进「用初始内容恢复」的降级分支，也让房间线程本轮以异常收场 | 补 `OSError` 并与另两处措辞对齐 |
| MIN-N43 | `src/log_archive.py:119-131` + `src/logger.py:181,196` | 归档后文件名脱离 loguru `retention=3` 管辖（`retention` 只清同基准名的轮转副本），无数量 / 总量 / 时间上限 | 长期运行（每日多次启停）用户 `logs/` 单向增长，每次最多 4 个、单个可达 300 KB；`AGENTS.md` 第 8 条只定义了命名冲突追加 `_N`，未定义回收 | 归档目录内按「同前缀保留最近 N 份」best-effort 轮转（失败仅告警，绝不中断停止流程），并在 `AGENTS.md` 补该口径 |
| MIN-N44 | `src/ffmpeg_proc.py:28-35`、`187-223` | 并行清理总预算 `_CLEANUP_WAIT_SECONDS=45` 不随进程数放大，而组内是**串行**、单进程默认 timeout=30 → K>12 必然超预算 | 预算耗尽后函数返回、atexit 继续走完，解释器退出切断仍持有进程的 daemon worker → Windows 下 ffmpeg 成为孤儿持续拉流写盘；「已放弃等待」不只是日志措辞 | `worker_count` 按进程数放大，或预算改 `max(45, ceil(K/8)*30)`；atexit 路径额外 join 一小段；未清 PID 落一条 ERROR 提示手工清理 |
| MIN-N45 | `build_exe.py:621-663` | 冒烟判定 `expect_alive=True` 只在「非零退出」时报错，进程 0.5 秒内以 rc=0 退出即打「通过」；`smoke_cli` 注释承诺「确认进入监控循环」但无任何输出断言（Web 有 HTTP 探活，CLI/GUI 没有） | 入口脚本被改成「打印帮助 / 版本号后正常退出」这类回归，三平台发布链全绿 | `_finish` 增 `if expect_alive and not still_running: raise`；`smoke_cli` 断言输出含启动横幅 / 监控关键字之一 |
| MIN-N46 | `scripts/check_annotations.py:219-257`、`405` | `stats` 为空（`--root` 传错、目录整体被 `EXCLUDE_DIRS` 吃掉）时 problems=0 → rc=0；`find_docstrings()` 遇 `SyntaxError` 返回 `[]`，该文件 docstring 检查静默失效 | 与同仓 MIN-19「无数据即 rc=2，不得退回 WARN」口径不一致；CI 的 `Check annotation conventions` 在扫描面塌缩时不会变红 | `if not stats: return 2` 并打印下一步命令；`SyntaxError` 记为一条 problem |
| MIN-N47 | `scripts/check_version.py:49-54` | main.py 硬编码判据只认 `version: str = "v?\d…"` 一种拼写 | 看不见 `version = "4.3.0"`（去注解）、`__version__ = "…"`、`VERSION: str = "…"` 等等价硬编码 → 版本号单一事实源门禁对这类回退永久失明（MID-68 同族：判据只覆盖一种形态） | 改 AST 扫描顶层赋值：目标名属 `{version,__version__,VERSION,APP_VERSION}` 且值为 `ast.Constant(str)` 即判 HARDCODED |
| MIN-N48 | `build_exe.py:79-83` + `main.py:177-197` | 冻结产物的版本回退链两个来源都不存在：打包链从不 `pip install .`（无 dist-info），回退分支读的 `pyproject.toml` 又不在 spec `datas` 内 | `exe` 启动横幅与 Web 面板标题显示 `v0.0.0`（Docker 不受影响，`pyproject.toml` 随 `COPY . ./` 进 `/app`）——版本单一事实源约定在打包面的漏洞 | `datas` 增 `('pyproject.toml', '.')`，或打包期写 `_version.py`；须真机跑一次 exe 确认横幅 |
| MIN-N49 | `.github/workflows/trivy.yml:23-31`、`issue-translator.yml:31-33`、`ci.yml:234-245`、`scripts/_ci_web_smoke.sh:51` | 四条命名 / 覆盖细节：① 两个 workflow 缺 `timeout-minutes`（`ci.yml` 顶部统一策略要求每个 job 都有）；② trivy 的 SARIF 上传在 fork PR 下 token 只读必 403，出现与代码无关的红 check；③ 兜底步骤名为「Gate isort/black silent-skip warnings」却只重跑 isort（且 `\|\| true` 吞掉 isort 自身 rc）；④ 脚本注释引用了不存在的 `build_exe._ensure_url_config`（实际 `_prepare_url_config`） | 定时 / PR 触发的镜像构建可挂满 6 小时；读者会以为 black 也有第二道「静默跳文件」网（实际只有 `PYTHONUTF8` step env 一道） | 补 `timeout-minutes`；SARIF 步骤加 `if:` 排除 fork；同步跑 black 的等价扫描或改步骤名并在 `AGENTS.md` 同步措辞；修正函数名 |
| MIN-N50 | `.workbuddy/tmp/i18n_param_migration_backup/`、`main.py:3612-3621`、`main.py:4417`、`main.py:4766-4776` | 四条低优先观察：① `.workbuddy/tmp` 下留有整份源码旧副本（`main.py` 177 KB、`spider.py` 274 KB 等），与 `AGENTS.md`「一次性脚本 / 备份不得留在仓库」口径相悖；② `real_url.replace("https://","http://")` 会连带替换 query 内出现的同串（应为前缀替换）；③ `delay_default = _safe_int(...,120)` 无下限（相邻 `split_time` / `max_record_seconds` 都做了归一），填 0 时 `while x:` 一次都不睡，多房间零间隔刷接口；④ 用户在 URL 里写 `\|` 时 `replace_words[0]` 会被截断并写坏该行（`rstr` 只过滤文件名不过滤 `record_url`） | ①污染工作树并可能被误当作项目组成部分；②当前各平台流地址未内嵌 scheme，属潜伏形态；③风控放大；④坏行 | ①按收尾清单确认清理（本机 Git Bash 无 coreutils，用 PowerShell 或交回用户）；②改前缀替换；③加下限（如 `max(10, ...)`）；④对 `record_url` 做同 `clean_name` 级别的字符集校验 |

---

## 六、改进建议与修复优先级

### 6.1 优先级批次

| 批次 | 条目 | 判据 | 建议落地方式 |
| --- | --- | --- | --- |
| **第 1 批（立即，安全与凭据面）** | SEV-N02、SEV-N03、SEV-N04、MID-N32、MID-N42、MID-N45、MID-N57、MIN-N39 | 凭据被销毁 / 外泄、认证防线可旁路、SSRF 第二出口 | 单文件改动为主，可并行；SEV-N03 需同时改 `create_app` 签名与 `web.py` 调用点（跨文件，交一个代理） |
| **第 2 批（录制功能可用性）** | SEV-N05、MID-N08、MID-N10、MID-N12、MID-N22、MID-N25、MID-N33、MID-N34、MID-N37、MID-N18 | 「该平台 / 该档位永久录不上」或「请求率被放大」 | 按文件分 4 个批次：`main.py`（N08/N10/N12）、`stream_select.py`+`stream.py`（N31/N33/N34/N35）、`spider.py`（N18/N22/N25/N30） |
| **第 3 批（资源生命周期与收尾一致性）** | SEV-N01、MID-N01、MID-N03、MID-N04、MID-N05、MID-N06、MID-N15、MID-N46、MID-N48、MID-N49、MID-N50、MID-N52、MIN-N43、MIN-N44 | 句柄 / 线程 / 进程 / 文件泄漏，退出与停止路径不可靠 | 建议**一个代理串行**改 `main.py` 收尾簇（SEV-N01 + MID-N01 + MID-N04 + MID-N15 同属 `check_subprocess` / 房间线程等待，并改会互相冲突） |
| **第 4 批（同源多点缺单一事实源）** | MID-N13、MID-N14、MID-N55、MID-N58、MID-N73、MIN-N24、MIN-N26 | 「五处同源里少锁的那一处」是本仓反复出现的失效模式 | 每项都要跨 Python / JS / 配置文件，须留到最后单独一轮收口（翻译目录、哈希钉表、文档同源同理） |
| **第 5 批（门禁与测试可信度）** | MID-N63…MID-N74（含 MID-N66 提取器恒 0、MID-N68 卫生 R1、MID-N70/N71/N72/N73 缺锁）、MIN-N45…N48 | 不修则后续任何改动都失去回归保护；且第 1–4 批的修复本身要靠这些锁兜住 | **建议紧随第 1、2 批之后**（先补锁再改代码，否则修完仍无防回归能力）；`standalone`（MID-N74）单独一批 |
| **第 6 批（观感与可观测性）** | SEV-N06 的 GUI 侧短期方案、MID-N59、MID-N60、MID-N61、MIN-N27…N38、MIN-N40 | 用户可感知但不阻断功能 | 可与第 4、5 批并行（前端文件独占） |

### 6.2 需要先改约定 / 文档、再改代码的四处

1. **SEV-N06（GUI 日志解析）**：若采纳「机器可读前缀」方案，须先在 `AGENTS.md` 新增一节定义 `#DLRQ|` 契约与四语目录的关系，再改 `src/recorder_status.py` + `main.py` + `gui.py` 三处——否则下一轮审查会把「GUI 按前缀解析」当成未记录行为。
2. **MID-N41（`requests.Session` 复用范围）**：`AGENTS.md` 现表述为「全部同步出站 HTTP 都穿过它」，与直连走 urllib 的事实不符；`urllib3>=2.7.0` 显式下限的理由也系于此。须先更正约定（或改代码使陈述成立），否则「抬下限」的安全结论会被后续审查质疑。
3. **MID-N55（配置写回必须保留注释）**：`AGENTS.md`「配置键审计」与「缺键补写」两条目前把「整份 dump 后原子写」当作硬化后的正确形态。若接受「注释必须保留」为硬约束，应先写进 `AGENTS.md`，再改 `utils.update_config` 与 `config_io.read_config_value` 两处。
4. **MIN-N22（`_ttwid_lock`）**：`AGENTS.md`「锁的强制约定」与「可重入性判定」两处把它列为跨 await 持有的凭据去重锁。删除该锁须同时改文档，否则文档与代码将反向分叉（AGENTS 第 7 条自身要求「改一处须同步另一处」）。

### 6.3 回归锁补齐清单（与本章条目一一对应）

| 待补锁 | 建议位置 | 断言要点 |
| --- | --- | --- |
| SEV-N01 | `tests/test_record_watchdog.py` | 零字节轮后 `recording == set()` 且 `len(_ffmpeg_processes)` 不增长；抛错轮 `collector.stop()` 恰一次 |
| SEV-N02 | 新建 `tests/test_spider_platforms.py` 用例 | 落盘值不含 `Bearer `；读回后 `Authorization` 恰一个前缀 |
| SEV-N03 | `tests/test_web_api.py` | 两步序列（改 `web_host` → 关认证）必须 403；判定读实际绑定地址而非配置值 |
| SEV-N04 | `tests/test_spider_hardening.py` | 响应只带 `_m_h5_tk` 时，出请求头与写回值均保留用户其它 cookie 键 |
| SEV-N05 | `tests/test_stream_select.py` | 裸 `ip:port` 与 `""` 两种入参不抛 ValueError 且探针走代理 |
| SEV-N06 | `tests/test_gui_monitor.py` | `en_US` / `zh_TW` 译文行仍须解析出降级与录制中 |
| MID-N08 | `tests/test_platform_dispatch.py` | 每条 `_match_host` 表项的 fragment 不含 `://`（或对 `http://` 与 `https://` 双形态均可命中） |
| MID-N09 | 新建或并入 `tests/test_main_fixes.py` | `# <url>` 形态写回后，房间线程须判为已注释 |
| MID-N10 | `tests/test_main_fixes.py` | shopee + `MP3` 保存类型时 `recording` 非空 |
| MID-N12 | `tests/test_record_failure_feedback.py` | 失败轮不得触发 30 秒快检；`+60s` 退避不得被覆盖 |
| MID-N32 | `tests/test_stream_select.py` | 五条 HLS 探测日志的 `url=` 实参必须经 `mask_credentials`（可 AST/正则机检） |
| MID-N68 | `tests/test_test_hygiene.py` | R1 扩扫 `patch()` 字符串目标 + 正 / 反向自检用例 |
| MID-N69 | `tests/test_run_gates.py` | `run_command` 的 env 前缀、`FATAL_STDERR_PATTERNS` 判失败、emoji 转发不崩 |
| MID-N70 | `tests/test_ffmpeg_reconnect_args.py` | 断言 `.lower()` 在 test 表达式内（或大小写双黄金用例） |
| MID-N71 | `tests/test_start_record_command_golden.py` | `_Cap` 记 `platform` / `danmaku_args` 并入快照 |
| MID-N73 | `tests/frontend/test_quality_ui.mjs` + `tests/test_config_bool.py` | Python frozenset 与 `app.js` 键集交叉相等 |
| MID-N74 | 新建 `tests/test_standalone_config_keys.py` | standalone 读取的键集合 ⊆ `config/config.ini` 实际键（归一化大小写后比对） |

---

## 七、门禁与测试可信度专项结论

本轮把「门禁是否真的在查」作为独立维度，结论如下：

1. **八处同源排除清单与 21 条依赖对账仍然成立**（G13 实测：`requirements.txt` ↔ `[project.dependencies]` 逐项等值、含 `urllib3>=2.7.0`；`protobuf` 上限未删；八处排除清单 19 个目录逐条对齐、两处 coverage omit 对称差为空）。
2. **`PYTHONUTF8=1` 的三处覆盖（门禁块 / `run_gates` / `ci.yml` step env + 兜底步骤）均在位**，MID-63 那一族的「本地绿、CI 绿、两边都没查」形态未复现；但**该入口自身无回归锁**（MID-N69），且 CI 的兜底步骤名与实际覆盖面不符（MIN-N49③）。
3. **新增的门禁失明形态共 7 处**，全部属「谓词只认一种写法」这一老问题的变体：`patch()` 字符串形态（MID-N68）、`logger` 别名（MID-N40）、`.lower()` 存在性（MID-N70）、`version: str =` 拼写（MIN-N47）、拼接式日志首参（MIN-N04）、`extract_i18n_strings` 恒 0（MID-N66）、`check_annotations` 零文件退 0（MIN-N46）。**共性建议**：每条门禁谓词都配一个「正 / 反向自检用例」（仓内已有先例 `test_gate_predicate_sees_concatenated_fstring`），并把「扫描面为空即 rc=2」统一为跨脚本约定。
4. **测试可信度整体好于上一轮**：`patch.dict(os.environ)` 全仓 0 处、宽泛 `filterwarnings` 0 处且 R2 带自检、10 个「无 assert」用例的判据都落在带断言的 helper 里、参数化列表无空跑、前端用例用 `node:vm` 求值真实函数而非自实现、UA 与探针语义常量与 `src/` 逐字一致。真正的漏洞集中在 MID-N68 / N70 / N71 / N72 / N73 五条「锁存在但看不见该形态」。
5. **`ci-summary` 仍是唯一的 required check 判定口径**，但 dispatch 复跑会被路径过滤整体旁路（MID-N63），这是本轮唯一能让「全部门禁绿灯 + 一条未跑」同时成立的 CI 形态，建议与第 5 批一并处置。

---

## 八、逐文件定位索引

| 文件 | 严重 | 中等 | 轻微 |
| --- | --- | --- | --- |
| `main.py` | SEV-N01、SEV-N05（消费侧）、SEV-N02 / SEV-N04（写回侧） | N01–N15（全 15 项） | MIN-N50（②③④） |
| `src/spider.py` | SEV-N02、SEV-N04 | N16–N30（全 15 项） | MIN-N01…N17 |
| `src/stream_select.py` | SEV-N05 | N31、N32、N35、N74②③④ | MIN-N18、N28、N31 |
| `src/stream.py` | — | N31、N33、N34、N35 | MIN-N19 |
| `src/sync_http.py` / `async_http.py` / `proxy.py` / `ttwid.py` / `cookie_cache.py` / `ws_client.py` | — | N36–N41 | MIN-N20…N23 |
| `src/platforms/*`（`bilibili` / `douyin` / `_tars` / `_xbogus` / `__init__`） | — | N50 | MIN-N21、N29、N30、N32 |
| `src/collector.py` / `danmaku_monitor.py` / `srt_writer.py` | （SEV-N01 的采集器侧后果） | N46、N47、N48、N49 | MIN-N28、N31 |
| `src/web_api.py` / `web_config.py` / `web.py` | SEV-N03 | N42、N43、N44、N45 | MIN-N24…N27、N35…N37 |
| `src/utils.py` / `config_io.py` / `logger.py` / `log_archive.py` / `ffmpeg_proc.py` / `ffmpeg_install.py` / `node_install.py` / `video_postprocess.py` | — | N54、N55、N56、N57、N58 | MIN-N41…N44 |
| `gui.py` | SEV-N06 | N51、N52、N53 | MIN-N33 |
| `msg_push.py` / `i18n.py` | — | — | MIN-N34 |
| `web/app.js` / `web/index.html` / `index.html` | — | N59、N60、N61 | MIN-N35…N37、N40 |
| `src/javascript/{liveme,haixiu}.js` | — | — | MIN-N38、N39 |
| `build_exe.py` | — | N62、N65 | MIN-N45、N48 |
| `.github/workflows/*`、`scripts/_ci_web_smoke.sh` | — | N63 | MIN-N49 |
| `scripts/smoke_test.py` / `extract_i18n_strings.py` / `patch_i18n_2026_09_12.py` / `check_annotations.py` / `check_version.py` | — | N64、N66、N67 | MIN-N46、N47 |
| `tests/` | — | N68…N73 | — |
| `scripts/douyin_live_recorder_standalone.py` | — | N74 | — |
| 仓库卫生（`.workbuddy/tmp`） | — | — | MIN-N50① |

---

## 九、已回源复核、确认**不构成问题**的实现（供后续审查者复用）

以下条目在分组深读中被提出或被主动核查，经回源确认为**本项目的正确或刻意设计**，不得作为缺陷上报：

1. **录制并发槽纪律**：`recording_semaphore` 在 `Popen` 之前 acquire、`release` 在 `finally` 且恰好一次；放弃等待分支在 `try` 之前 return，不会凭空释放；`_rec_sem` 本地别名正确规避了 `main.py:4328` 重绑定造成的 acquire/release 跨对象。
2. **ffmpeg 输入侧三条致命坑全部守住**：`-reconnect*` 三项均带取值且全在 `-i` 之前；`.m3u8` 判定已 `lower()`（`main.py` 侧）；`-headers` 按 `-i` 锚点插入、`-tls_verify` 仅 https 注入。五条保存类型分支的输出参数 / 路径 / 执行骨架全部走四个单一定义点，`-segment_format` 零裸字面量（含 `.mp3` 已补键）。
3. **平台分发表 52 条与 `PLATFORM_HOST` 逐项对账无漏项**（MID-04 三处已修），表头优先级与注释一致；命令以 argv 列表 `Popen`，无 `shell=True`，主播名 / 标题经 `clean_name`（含控制字符、`&`、保留设备名）过滤，无注入面。
4. **主循环去重容器均为 set**、`discard` 取代整表重建、`dict.fromkeys` 保序去重；CR-02 的行级 try 保证坏行不中断整轮；`_room_thread_target` 的 finally 四件清理齐备、键已改 uuid 片段。
5. **探针语义全套守住**：`_throttle_probe` / `_recheck_delay` 抖动与锁粒度（锁内计算、锁外 sleep、预约时刻无漂移）、退避窗口与主循环周期联动、mark/clear 键与 `-i` 逐字对称、HEAD 非 2xx → Range GET 全覆盖（含 404）、401/403 重试一次、末位放行含 `text/html` 与异常分支、候选序列去重与 h265 剔除、`_is_recordable_url` 三态。
6. **画质档位约定守住**：蓝光子档位折叠、虎牙 ratio 数值命名与就近降级 tie-break、斗鱼 2 档本地回退且保持 `is_live=True` 契约、`_pick_master_variant` 取最高 BANDWIDTH 及其保守回退。
7. **装饰器与返回契约**：`spider.py` 内返回 dict 用 `trace_error_decorator`、返回 str/tuple/None 用 `_or_none` 且调用点显式判空后解包（MID-44 / SEV-07 闭环）；`@decorator` 全部紧贴 `def`；`_read_haixiu_token_override` 无装饰器（CR-12 闭合）。MID-48 加固在三个行段覆盖完整，全仓裸 `json.loads` 余 1 处（Twitch GQL 数组响应，符合棘轮 `BARE_JSON_LOADS_CEILING = 1`）。
8. **并发与锁**：无模块级 `asyncio.Lock()` 单例、无跨循环 `aclose()` 协程、`_get_client` 临界区零 await；`ResizableSemaphore` 容量 / 已持有分离、`set_value` 收缩不回收、允许 0；`PlatformBreaker` 的 `_probing` 在 open 态恒 False、租约重授予只在 half-open 生效、熔断计数增量维护且 `import time` 在顶层；`web_api` 的四把 `threading.Lock` 全链路同序、未见反向持锁（`_purge_expired_tokens` 自死锁教训已落地）。
9. **面板安全面的既有强度**：token 用 `secrets.token_urlsafe(32)` + `compare_digest` + 精确吊销 + 改密清表；PBKDF2 盐随机 / 200k 迭代 / 上下界钳制；登录端点为同步 def（线程池）+ IP 与全局双预算限流；路径遍历用 `realpath` + `commonpath` 逐条目复核并跳过悬空链接、`FileResponse` 恒 attachment；`run_script` 用 `shlex.split` 无 shell，唯一 RCE 落点「自定义脚本执行命令」已黑名单且 `casefold` 与行匹配同强度；CSP / nosniff / X-Frame-Options 在放行与拒绝两路均加；无 CORS 放行。
10. **发布链三层防线均在位**：`_PINNED_RUNTIME_SHA256` 按形状判「已钉定」（占位 `UNVERIFIED_PIN` 一律算未钉，发布链在官方值填入前必然红是**预期**）；`--require-pinned` 在下载前 `SystemExit`；`_download_file(slot=...)` 已改必填关键字参数；`check_runtime_pins.py` 表空 / 缺槽一律 rc=2 且 `--emit-env` 不伪造「已钉定」。
11. **`StopRecording.vbs`**：实测为 UTF-16 LE（`FF FE` BOM）+ CRLF；三层进程匹配（专属 exe → python 命令行 token 整名匹配 → ffmpeg 父进程 / 路径锚定）、`appDir` 深度守卫、只认字面量 `-y`、先主进程后 ffmpeg 全部落地。
12. **Dockerfile / compose**：`ARG APP_VERSION` 先于 `LABEL`（`check_version.py` 的行序断言含续写回溯与注释跳过）；NodeSource 脚本先 SHA256 校验后执行、`sha256sum -c` 双空格写法正确；`pull_policy: build` 已去掉 `:latest` 回退；`127.0.0.1:8000` + `no-new-privileges`。
13. **供应链与注入面**：无 `pull_request_target`；无不可信上下文进 `run`；retry 复合动作经 env 传命令（不二次展开）、`set -euo pipefail` 语义正确；`ci-summary.needs` 覆盖全部 8 个 job，无被静默旁路者。
14. **前端 XSS 与脱敏**：全部 13 处 `innerHTML` 的动态成分均过 `esc()`（属性位含 `"` / `'` 双引号转义），`toast` / `login-error` / `#log-stream` / 无认证横幅一律 `textContent`，无 `href` / `window.open` / `document.write` 消费外部值；token 只经 `Authorization: Bearer`、从不进 query；掩码五套正则与 `src/web_config.py` 逐字等价；`parseConfigBool` token 集合与 Python 侧逐项一致且用 `hasOwnProperty` 规避原型链；四套内嵌目录实测各 119 键且键集逐一相等；`#rooms-view .data-table` 的 `table-layout:fixed` 定宽与省略约束与定稿逐条吻合。
15. **弹幕链既有不变量守住**：`collector.stop()` / `_run()` 的反向序握手（穷举交错成立）、MID-23 有界轮询、MIN-23 的 `_start_task` 引用与有界排水、三处队列有界性、`_outstanding` 与入队同临界区、协议解码边界（B站 `packet_len<16`、斗鱼整帧推进、`_tars._need`）、SRT 分片命名与 `_%03d` / `_%02d` 剥离、`proxy=None` 未被破坏（仅 Twitch 显式传代理）、MI-01 三处 WS 解压全部限长。

---

## 十、总结性结论

1. **整体评价**：本项目的架构约束与「已知坑」体系是有效的——`AGENTS.md` 沉淀的并发模型、探针语义、四类单一定义点、发布链钉定、门禁 UTF-8 覆盖在代码中逐条成立（第九章 15 组核实项），本轮**未发现架构级缺陷**，也未发现注入 / 路径遍历 / 反序列化等传统高危面的可用利用链。
2. **主要风险集中在三处**：
   - **异常与早退路径不复用同一收尾**（SEV-N01、MID-N01、MID-N04、MID-N52 等）：正常出口被反复加固，而 `return` / `raise` / EOF 三类旁路仍有漏口，后果是句柄 / 线程 / 状态条目泄漏与「面板显示成功但实际失败」。
   - **同源信息散写多点、缺单一事实源**（MID-N08、N13、N14、N31、N55、N73、MIN-N24、N26）：resolver 表项、Cookie 转发表、h265 谓词、原子写实现、布尔 token 集合各存在 2～3 份副本，改一处漏其余——这也是「半修复」反复出现的结构性成因。
   - **门禁与回归锁的覆盖面**（MID-N66、N68、N69、N70、N71、N72、N73，MIN-N46、N47）：本仓已把「只发告警但退出码 0」判为失败，这是正确的方向；但多数谓词仍是「只认一种写法」，导致同一族失效以新形态复现。
3. **安全侧必须优先处置三项**：SEV-N03（认证不变量可两步旁路）、SEV-N04（用户凭据被静默销毁并持久化）、MID-N45（推送/代理 URL 键构成第二条 SSRF 出口）。三者共同点是**上一轮为房间 URL 与凭据建立的收口口径没有覆盖到「配置写入面」**——建议把「写入侧校验 + 复核回报 + 脱敏落盘」三项作为 `[Web]` / `[推送配置]` 类键的统一模板。
4. **不建议做的事**（与本轮部分低置信建议相反，理由已在第九章与 `AGENTS.md` 记录）：为「保险」关掉探针客户端 keepalive；把 standalone 副本的 `PlatformBreaker` 强行对齐（刻意不等价）；为兼容 <3.14 给 `except` 加括号；用 `filterwarnings` / 捕获异常跳过 的方式让 isort 静默跳过、`deps-audit` 报错、i18n 三件套「变绿」；把 `_PINNED_RUNTIME_SHA256` 回填本地自算哈希以求 CI 变绿。
5. **完成定义**：本轮全部结论均按 `AGENTS.md`「完成定义」验收——第 1、2、5 批落地后须跑真实 URL 增量验证（至少一个受影响平台），并把结果写进回复；仅单测绿不视为验证过。

---

## 附录 A ｜ 上一轮（2026-09-20）严重项回归核查

复核口径：**只复核与本轮发现直接相关的修复面**（读回代码确认修复仍在位），未做全量重跑，也未重新验证需真机的部分。

| 原编号 | 修复现状 | 本轮相关发现 |
| --- | --- | --- |
| SEV-01 并发信号量容量/可用数混用 | 在位（`ResizableSemaphore` 容量与 `_used` 分离、`recompute` 用 `capacity`）；standalone 副本已同步且两处互相点名 | 无 |
| SEV-02 / SEV-03 房间写入校验与内网拦截 | 在位（`format_url_line` 下沉校验、`_stream_path_suffix` 只看 path 使准入与分派同判据） | 但**同信任边界另有第二条出口未经同类收口**：MID-N45（推送/代理 URL 键） |
| SEV-04 认证可被单个写请求热关闭 | **可被两步旁路** | SEV-N03（判定基准 `web_host` 自身可写） |
| SEV-05 删除房间在 CRLF 上静默失效 | 删除路径已改为「持锁重解析复核」 | 同族的 update / toggle 两个端点仍恒回 `ok:true`：MID-N44 |
| SEV-06 Shopee 站点后缀解析 | 已修（`_shopee_host_suffix`），但落点 host 仍无站点白名单 | MIN-N14 |
| SEV-07 登录函数兜底契约错配 | 在位（`_or_none` + 调用点显式判空后解包） | 无 |
| SEV-08 看门狗停滞判据基准 | 已按 `_stall_since` 修正 | 但「产物文件从未出现」形态仍判不出：MID-N04 |
| SEV-09 `only_flv` 缺 `flv_url` 未清状态 | 已修（登记下移到确认拿到 flv_url 之后） | 该守卫与音频分支先后的新形态：MID-N10 |
| SEV-10 发布链运行时钉定为空 | 三层防线结构完整（占位值即红是预期），`slot=` 必填、`check_runtime_pins.py` rc=2 均落地 | full 版「解出的产物是否齐全」仍无自检：MID-N65 |
| MID-33 凭据主动失效链 | B 站 buvid、抖音 ttwid 已接（抖音侧 2026-09-21 刚补 HTTP 200 拒绝分支） | 快手 did / Twitch client-id 两个钩子仍零生产调用点：MID-N19；buvid 失效清错键：MID-N21 |
| MID-63 `PYTHONUTF8` 三处覆盖 | 在位（`run_gates` 解析 env 前缀 + `ensure_utf8_streams` + `ci.yml` step env + 兜底步骤） | 该入口自身无回归锁：MID-N69；i18n 三件套之一恒 rc=0：MID-N66 |
| MIN-19 无数据即 rc=2 | `check_coverage.py` / `check_runtime_pins.py` 在位 | 同族另有两处仍退 0：MID-N64（smoke_test）、MIN-N46（check_annotations） |
| CR-12 装饰器契约 | 已逐条对齐（含 `@decorator` 紧贴 `def` 的排查手法） | 无新违例 |
| 上一轮各编号的「只改一半」残留（显式对应） | 见右列逐项映射 | WD-18（淘宝 cookie 赋值提到判定外）→ SEV-N04；花椒「注释掉用户 URL」的写回（CODE_WIKI.md:5012 声称已改显式告警）→ MID-N30；WD-20（在线人数 `data` 透传）→ MID-N47；WD-21 → MID-N51；MI-01（解压限长）→ MID-N36；MI-11（行尾保真）→ MID-N58；H-6（画质写回锁）→ MID-N43；MID-41（抖音 origin 裸下标）→ MID-N20；MID-48（`_dig` 加固）→ MID-N16 / N26 / N29；MID-57（原子写 fsync）→ MIN-N24；MID-04（表项协议前缀）→ MID-N08；MID-13 / MID-14（虎牙档位）→ MID-N34；MIN-04（超时与半成品清理）→ MIN-N41；MIN-20③（`proxy_url`）→ MIN-N20；CR-03（TARS 边界）→ MIN-N21；CR-10（脱敏双判据）→ MID-N57 |

## 附录 B ｜ 审查限制与方法说明

1. **未执行真机录制验证**：本轮为纯静态 + 只读取证。涉及「平台是否真的这样下发」「CDN 是否真的校验该头」的结论（MID-N17、N27、N31、N34、N35、MIN-N13、N14 等）一律标注为需真机核对，并在 6.1 中归入靠后批次。
2. **未执行变异验证**：本工作区的 action 分类器会拦下「临时改坏生产实现再跑用例」的形态（见 `.workbuddy/memory/2026-09-21.md`），故本轮缺锁判定全部以**结构论证 + grep 实测覆盖面**给出，未做删实现验红。落地补锁时应按 `AGENTS.md`「测试不得自实现被测逻辑」口径做归因用例。
3. **子代理结论已按 AGENTS 口径筛除臆测**：第九章 15 组为「提出后经回源确认不成立或属刻意设计」的条目；另有约 20 条因与代码内既有编号注释重复、或与「末位放行 / 退避白名单 / 探针客户端作用域 / standalone 不等价」等定稿结论冲突而未计入统计。
4. **置信度含义**：高 = 静态可判定或已实测；中 = 结论依赖外部响应形态 / 时序窗口，代码侧已核对但需真机；低 = 仅结构可疑，本章未收录低置信条目（一律降级为「观察」或在 5.3 合并登记）。
5. **凭据处置**：报告中出现的 URL / token / cookie 一律为**脱敏后的形态或占位样例**，未复制 `config/config.ini`、`config/URL_config.ini` 或 `logs/` 中的任何真实凭据；MIN-N39 对 `haixiu.js` 注释中的疑似真实素材只描述形态、不转录取值。
6. **工作树快照限制**：本目录非 git 仓库，无 `git diff` 可依赖，故本轮未对「修复引入的回归」做基线对比，仅以代码内既有编号注释 + `AGENTS.md` 约定作为回归基准；如需精确 diff，建议先做树快照（见用户级记忆「Parallel fix-agent granularity」）。

---

## 附录 C ｜ 修复执行期的新增发现与落地状态（补-N，2026-09-21 下午）

> 本附录登记**修复过程中新暴露**的问题与状态，**不并入**第一~五章的统计口径（严重 6 / 中等 74 / 轻微 50 不变），编号另起 `补-N0x`，与上一轮报告的「补-0x」不冲突。

### 补-N01 ｜ `direct_download_stream` 的 `httpx.Client` **完全不接代理**（与 SEV-N05 同族但语义不同）

- **位置**：`main.py:677-679`（`direct_download_stream` 内）
- **证据**：

```python
            with httpx.Client(
                timeout=30, verify=_http_config.get_effective_ssl_verify(platform), headers=headers
            ) as client:
```

- **机理与区别**：SEV-N05 是「取了代理原文但没归一」，本条是**根本没传 `proxy=`**。因此配置了「是否启用代理ip / 系统代理」的部署下，shopee、花椒直播 等强制直下平台（`only_flv_platform_list`，`main.py:3671`）会用直连 socket 去拉流，而同一房间的**解析与选源**却走代理——三条链路（解析 / 校验探针 / 直下写盘）的出网路径不一致。
- **影响**：在「必须经代理才能访问海外 CDN」的网络里，直下平台 100% 拉不到流；表现为 `请求直播流失败: … - 状态码: …` 或连接异常，而解析侧日志显示正常，归因极易跑偏。属可用性缺陷，非安全问题。
- **修复**：与 SEV-N05 同一口径——`proxy=utils.handle_proxy_addr(proxy_address)`（该函数作用域内需把 `proxy_address` 透传进来，目前未作为参数传入，是**需要改 `main.py` 录制链入口签名**的跨函数改动）；并让「解析 / 探针 / 直下」三处的出网路径在注释里互相点名。
- **归属**：`main.py`（修复执行期由另一会话认领，本会话未写入）。

### 补-N02 ｜ `AGENTS.md` 宜新增的三条长期约定（修复期沉淀，待文档负责人落笔）

1. 「任何 `httpx.Client` / `AsyncClient` 构造前，`proxy` 实参必须先经 `utils.handle_proxy_addr`，且只允许在构造之前归一」——本轮 `src/stream_select.py:668-669`、`:1007` 两处即按此口径修，缺该约定则新出站面会第三次重犯。
2. 「凭据落盘值与请求头 scheme 前缀二选一，读取侧必须归一」——SEV-N02 的根因是 `popkontv_token` 落盘带 `Bearer `、请求处再拼一次。
3. 「响应 `Set-Cookie` 只能**合并**进 Cookie 头，禁止整体替换后再持久化」——SEV-N04 的根因，且与 MID-37「敏感项不得被静默覆盖」是同一条红线的两侧。

### 补-N03 ｜ 落地状态快照（截至本会话最后一次核验）

| 项 | 状态 | 复核方式 |
| --- | --- | --- |
| SEV-N02 / SEV-N04 / SEV-N03 / MID-N42 / MID-N45 / MID-N32 / MID-N57 / MIN-N39 | **已修 + 已补回归锁** | 逐条 grep 源码标注 + 目标测试文件实跑（含 6 条归因用例、2 条门禁自检用例） |
| SEV-N05 | **已修 + 7 条回归锁** | `pytest tests/test_stream_select.py` 72 passed；修复前快照跑同一 AST 判据命中 `[652, 989]`、修复后 `[]` |
| 门禁 | 本轮曾达成 `mypy` + `mypy --platform linux` + basedpyright 三面全绿；其后因**并发会话在制品**再次转红 | 见补-N04 |
| 其余第 2~6 批 | 未由本会话处理（`main.py` 簇已被并发认领） | `diff -rq /tmp/dlr-snap-20260921` 归属核对 |

### 补-N04 ｜ 执行期观察：并发会话把 MID-N01 停在「半落地」状态

`main.py:866-867` 已按 MID-N01 删除 `_FFMPEG_OUTPUT_FAILURE_MARKERS` 与 `_ffmpeg_reported_output_failure()`，但 `main.py:1346` 的**调用点未同步移除** → 此刻 `mypy` 报 `Name "_ffmpeg_reported_output_failure" is not defined`、`tests/test_record_failure_feedback.py` 3 条失败。运行期亦非零风险：`_output_side_failure = (not os.path.isdir(...)) and (_ffmpeg_reported_output_failure(proc))` 在「输出父目录不存在」这一支会真抛 `NameError`（`and` 短路只在目录存在时保护它）。

这正是本报告 1.1 节与第十章第 2 点描述的失效模式——**「改一处漏调用点」在修复过程中自我复现**。本报告已在 4.4 节（MID-N41 的「签名/判定改造须 grep 全部调用点」）与 `AGENTS.md`「把『调用方持锁』改成『内部自持锁』」条目反复登记同一教训；建议后续把「删除模块级函数/常量」单独列为必须 grep 的门禁动作（可加进 `scripts/run_gates.py` 的回路或 `check_annotations.py`）。

> 本会话**未代改** `main.py`（该文件由并发会话认领，代改会造成互相覆盖）。
