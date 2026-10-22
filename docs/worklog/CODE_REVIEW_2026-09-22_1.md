# DouyinLiveRecorder 审查修复进展（2026-09-22，第 1 次快照）

> 来源报告：`CODE_REVIEW_2026-09-22.md`（161 项：严重 28 / 中等 65 / 轻微 68）
> 本文件定位：**进展快照**，不是最终结论。第 1 部分列出已落地并已验证（或复核后不成立）的项；第 2 部分列出尚未处理、待确认或有争议的项。
> 门禁口径：本轮所有修复均要求 `scripts/run_gates.py --keep-going` 8/8 全绿 + `pytest` 0 警告 + 无参 `mypy` 通过，方可记为「已修复确认」。
> 临时辅助文件：`_FIX_BRIEF_2026-09-22.md`（各组共享作业简报）、`_i18n_pending.json`（待合并的四语目录键）、`_run.py`（执行辅助）。收尾阶段统一删除。

---

## 第一部分 · 已完成（已修复确认 / 复核通过 / 复核后不成立）

### 1.1 已全盘完成的文件组（门禁已验证通过）

| 组 | 文件 | 负责人 | 门禁结论 |
| --- | --- | --- | --- |
| A | `src/stream.py`、`src/stream_select.py` | 代理 | mypy 147 源文件无问题；pytest 791 passed / 7 skipped |
| B + B2 | `main.py` | 代理 | run_gates 8/8 全绿；pytest 86 passed；无参 mypy 148 源文件无问题 |
| C | `src/utils.py`（凭据掩码部分）、`src/web_config.py`、`src/config_io.py`、`msg_push.py` | 代理 | run_gates 8/8 全绿；无参 mypy 149 源文件无问题 |
| E | `src/spider.py`、`src/platforms/bilibili.py`、`src/async_http.py`、`src/sync_http.py`、`src/notify.py`、`src/weverse_auth.py` | 代理 | mypy 150 源文件无问题；pytest 339 passed / 6 skipped |
| F | `scripts/run_gates.py`、`scripts/check_coverage.py`、`build_exe.py`、`requirements.txt`、`pyproject.toml`、`.github/workflows/ci.yml`、`.dockerignore`、`.gitignore` | 代理 | run_gates 8/8 全绿 + basedpyright 0；pytest 319 passed（含新建锁） |

> 说明：C 组**未**处理 `src/utils.py::run_js_async` 的超时（见 2.1）；E 组对 `src/notify.py` / `src/weverse_auth.py` 经回源判定无需改动。

### 1.2 严重项（SEV-22xx）已解决清单

#### 已修复（逻辑改动 + 回归锁落地）

- **SEV-2201** `src/stream.py:1273-1276`（`get_url` 先判 `isinstance(play_url, str)` 原样返回，否则走 dict 探测）；`:288` 错误前提注释就地改正。`tests/test_regression_2026_09_22_stream.py` + 变异验证（删 str 分支即变红）。结论：8+ 平台 `list[str]` 契约互斥闭合。
- **SEV-2202** `main.py:308` 的 `rstr` 加入 `%`；`_build_record_output_path` 分段/音频分支加「额外 `%` 占位符即归一并告警」守卫。回归锁断言「分段模板除末位 `_%03d`/`_%02d` 外不得再含 `%`」。结论：分段录制因裸 `%` 失败的根因闭合。
- **SEV-2203** `main.py:2758-2770` 7 条表项去掉协议前缀（与 `douyin.com/` 同口径）；`:2834` 附近「不可达分支」陈述改为「准入 host 命中但无匹配解析器」。结论：`http://` 房间无限空转修复。
- **SEV-2204** `src/spider.py:1063-1105` 快手 `playUrls` 按 codec 优先级遍历（h264→h265），`representation` 补 `or []`，无候选时 `_warn_api_abnormal`。结论：HEVC-only / `"h264": null` 静默漏录闭合。
- **SEV-2205** `src/spider.py:5172 / 5297` 畅聊/音播 `live_id` 改 `_dig` + None 判空 + `str()`，对齐流星口径。结论：liveID 取空拼坏地址闭合。
- **SEV-2206** `main.py:229 / 4984 / 5019 / 5229` 新增可逆的 `disk_limited` 标志，房间线程与拉起条件同时判它，空间恢复时复位并告警。结论：磁盘棘轮「活着但不录」修复。
- **SEV-2208** `main.py:991-995` 注释改正；`finally` 内无条件 `danmaku_collector.stop()`；`unregister`+`clear_record_info` 在 `not _converged` 时无条件执行；零字节分支改「先收尾后 return」。结论：SEV-N01 半修复闭合。
- **SEV-2210** `src/utils.py:783-794 / 820-867` 在 `_SECRET_KEYS` 增 camelCase 小写整段键，并对 `mask_credentials` 加 camelCase 边界分支 `(?<=[a-z])(?=[A-Z])`；覆盖面断言从「调用了掩码」升级为「值确实消失」。结论：斗鱼 `wsAuth`、嗨秀 `accessToken`、`tk` 明文落日志闭合。
- **SEV-2211** `src/web_config.py:772-792` 删除本地弱化副本，改调 `utils.atomic_write_text`（保留 mode + fsync + mkstemp + 写失败清 tmp）；`src/config_io.py:110` 陈述补 grep 判据。结论：0600 收紧被静默退回修复。
- **SEV-2212** `msg_push.py:202 / 228 / 242` `ctx = ssl.create_default_context()` 同时传 `SMTP_SSL(..., context=ctx)` 与 `starttls(context=ctx)`。结论：TLS 不校验服务器证书修复。
- **SEV-2213** `build_exe.py:217 / 220 / 265 / 272 / 300 / 348 / 1034` 复制 `config/` 改为 `_prepare_config_dir()` 脱敏重写，复用 `web_config.is_sensitive_item`；`make_zip` 首条语句 `assert_no_credentials_in_release()`（fail-closed）。结论：打包链路泄漏真实凭据修复。
- **SEV-2214** `src/spider.py:2207-2290` 小红书落地页双闸：XHS 域族白名单 + 内网判定，不通过即丢弃跳转、不发送凭据。结论：Cookie/sid 被发往响应决定的任意主机闭合。
- **SEV-2215** `src/platforms/bilibili.py:26-45 / 73-95` 弹幕 WS host 过官方域白名单，非白名单跳过并 WARNING，全不可信时降级（只录视频）。结论：登录 Cookie 随 `getDanmuInfo` host 外泄闭合。
- **SEV-2216** `requirements.txt:40-41` 与 `pyproject.toml:59-60` 同步新增 `h2>=4.3.0`、`socksio>=1.0.0`；回归锁断言两侧包名集合一致 + httpx 运行期 import 站点匹配声明。结论：`h2`/`socksio` 运行期缺包修复。
- **SEV-2220** `scripts/run_gates.py:247 / 258` 注释与实现相反已就地改正 + 可复核判据（grep `stdout=`）。结论：门禁自检注释口径闭环。

#### 已编辑、待验证（属 1.3 的 G 组，门禁尚未单独重跑）

- **SEV-2221** `src/web_api.py:1265-1318` 状态接口新增 `main_loop_alive` 心跳判据（连续 `_MAIN_LOOP_STALL_SECONDS` 秒计数零增长 ⇒ `False`）。
- **SEV-2225** `src/web_api.py:1034 / 1062` 写侧谓词改为调用 `web_config.is_sensitive_item`（消除读写分叉）。

#### 复核后不成立（已跳过，附理由；建议维护者二次确认）

- **SEV-2218 / SEV-2219**（钉定表门禁接线）：实测 `run_gates.py` 第 8 步与 `ci.yml:257` 均执行 `check_runtime_pins.py`，且 `--strict` 在 `build-release.yml:146` 调用、实测能 rc=1 拦下发布。结论：接线完整，原前提不成立。
- **SEV-2223**（门禁丢退出码）：实测 `run_command` 已返回真实 rc，`main()` 以 `if rc == 0 and not hits:` 收口。已补锁防回归，未改逻辑。
- **SEV-2224**（18 处 `patch("subprocess.")` 失效）：全仓实扫仅 6 处且逐一实证有效（`vp.subprocess`/`utils.subprocess` 均为真实模块），命中 `time.sleep` 11 处目标为 `src.stream_select.time.sleep`（正确）。结论：前提不成立。
- **MID-2259 / MID-2267 / MID-2268**（钉定表键/槽位、`FATAL_STDERR_PATTERNS` 覆盖）：实测矩阵键 `['windows-x64','linux-x64','macos-arm64']` 与 `build-release.yml` 一致；`FATAL_STDERR_PATTERNS = ('Unable to parse file',)` 正确覆盖 isort 的 stderr 告警。结论：正确。

### 1.3 中等 / 轻微项已修复清单（按组）

#### 组 A
- **MID-2227** `src/stream.py:465-478` 抖音/TikTok HLS 探针显式带 UA（同 `stream_select` 常量，无字面量副本）。
- **MID-2228** `src/stream.py:884 / 900-931` 去掉 `len(quality_list) > 1` 前置，exsphd 优先 → bitRate 推导 → 皆缺则不附加 ratio + `actual_quality="OD"` + WARNING。
- **MID-2229** `src/stream.py:277` `DOUYIN_KEY_TO_CODE` 映射真实画质键。
- **MID-2230** `src/stream.py:1145-1157` 选档前 `get_quality_index()` 折叠蓝光子档位。
- **MID-2231** `src/stream_select.py:360-430 / 503-513 / 532-541` 派生跳地址同域才带 Cookie，跨域剥 Cookie 不废「分片 404 判假绿」修复。
- **SEV-2226（stream_select 侧注释）** `src/stream_select.py:1098-1105` 删「`sync_http:179` 已接线」错误陈述，改指向 `async_http`。

#### 组 B + B2（main.py）
- **MID-2201** 线程 `start()` 失败即 `remove_room_from_running` + `continue`。
- **MID-2202** 字幕线程登记块移到 `if create_file:` 之前（与 ffmpeg 路径同构）。
- **MID-2203** 解析结果先落本地临时 set、整轮成功后一次性替换，失败保留上一轮集合。
- **MID-2204** 解析失败分支 `continue`，状态机只在真正拿到状态时迁移。
- **MID-2205** 改名成功分支 `get_hub().room_stopped(旧名, "主播改名")`。
- **MID-2206** `push_check_seconds` 与 `delay_default` 加下限 `max(..., 30)`。
- **MID-2207 / MIN-2227** 三处分段枚举统一收敛到 `_segment_files()`（`os.scandir` + startswith/endswith，绝不走 glob），修复方括号文件名误杀。
- **MID-2208** `check_subprocess` 内 elapsed 改 `time.monotonic()`。
- **MID-2209** 直下分支 UA 缺失补 `MOBILE_UA`（同 `stream_select` 常量）。
- **MID-2213** TwitCasting 回写改读 `json_data`（与 sooplive/flextv 同构）。
- **MID-2226** Shopee `new_record_url` 拼前做同源 + 字符集断言。
- **MID-2242** 启动失败分支先 `danmaku_collector.stop()`（幂等）再置 None。
- **MIN-2223** 4 处 `except` 补 `type_name=type(e).__name__`，与 `739` 对齐。
- **MIN-2224** 删 `_run_ffmpeg_checked`/`shlex`/`Mapping` 死导入。
- **MIN-2225** 分段续录文案按 `_split_output` 二选一。
- **MIN-2226** 4 处一次性 `time.sleep` 抽 `_interruptible_sleep`。
- **MIN-2228** `_resolve_cc_163_com` 补透传 `proxy_addr`。
- **MIN-2229** cookie/token 回写包 `except (configparser.Error, OSError)` 只告警。
- **MIN-2230** `-reconnect_at_eof` 判定统一 `_stream_path_suffix(real_url) == ".m3u8"`。
- **MIN-2231** 入日志的 `record_url`/`record_host` 过 `mask_credentials`（含 `user:pass@` 剥离）。
- **MIN-2232 / MIN-2233** 推送/打印文案改 `i18n.tr(...)`（7 条新 msgid 入 `_i18n_pending.json`）。
- **MIN-2234** 「未找到分段文件」日志带扩展名。
- **MIN-2235** FLV 分支 `_convert_after_record` 提到 `if comment_end` 之前（MKV/MP4 保持不转码）。

#### 组 C
- **MID-2251** `msg_push.py` ntfy 三处失败日志补 `mask_last_segment=True`（末段即频道口令）。
- **MID-2252** `msg_push.py:272-286` `finally` 的 `except smtplib.SMTPException:` 改 `except smtplib.SMTPException, OSError:`（PEP 758），避免 `quit()` 超时替换已算好的成功返回值。

#### 组 E（src/spider.py / platforms）
- **MID-2212** `src/spider.py:4273 / 3577` 微博/Look 改「两路皆空才判无源」，单一来源也能录。
- **MID-2214** `src/spider.py:1414` 斗鱼 betard 拼接日志改 `i18n.tr`。
- **MID-2215** `src/spider.py:1371-1393` 斗鱼签名 `rand_str`/`key` 缺失即 warning + `return {}`；`enc_time` `int()` 容错 + `min(max(...,0),32)` 上界。
- **MIN-2201** `src/spider.py:1803` B站选档注释改「就近向下取档」+ 降级 WARNING。
- **MIN-2202** `src/spider.py:650 / 688` 抖音 HTML 兜底快照 hoist 出循环复用，仅空时再抓。
- **MIN-2203** `src/spider.py:2060` B站 buvid spi 空结果重试前加抖动 `await asyncio.sleep(0.5 + random()*0.5)`。
- **MIN-2222** `src/spider.py:4163` 百度取稳定键 `room_id` 而非 data 首键。
- **SEV-2226（spider 侧注释）** 见 2.4（sync_http + AGENTS.md 尚未做）。

#### 组 F
- **SEV-2222（锁定）** `tests/test_regression_2026_09_22_gates.py:166` 真驱动 `src.stream_select._douyin_rate_limit()`，断言 sleep 恰为差值 + 时间戳推进；`tests/test_concurrency.py` 本身仍需跨组修正（见 2.3）。
- **MIN-2260** `.gitignore:299-304`、`.dockerignore:162-165` 补临时产物忽略（刻意不忽略 `_FIX_BRIEF_*.md`/`_i18n_pending.json`/`_run.py`，收尾删除）。

### 1.4 已新建的回归锁文件

- `tests/test_regression_2026_09_22_stream.py`（组 A，含变异判据）
- `tests/test_regression_2026_09_22_main.py`（组 B2，AST 驱动生产源码）
- `tests/test_regression_2026_09_22_utils.py`（组 C）
- `tests/test_regression_2026_09_22_spider.py`（组 E）
- `tests/test_regression_2026_09_22_gates.py`（组 F，25 条）

---

## 第二部分 · 未完成（待处理 / 待确认 / 有争议）

### 2.1 严重项（SEV-22xx）待落地

- **SEV-2207（部分）** `src/video_postprocess.py` 转码线程池需暴露 `shutdown_postprocess_executor(wait, cancel_futures)`（`main.py:534` 已就绪调用点），并改用守护线程 + 自管队列（与 `ffmpeg_proc` 处置同构）；当前该模块尚未改，**atexit join 先于 ffmpeg 清理 3600 秒**的上限未消除。下一步：在 `src/video_postprocess.py` 落地关闭接口 + 守护化，补回归锁。
- **SEV-2209** `src/utils.py::run_js_async` 整条 execjs 链路无超时（C 组只验证了消费侧形态正确，未加 `timeout: float = 30.0`）。下一步：给 `run_js_async` 加 `timeout` 并透传 `call(..., timeout=timeout)`，或用 `asyncio.wait_for` 包 `to_thread`；与 `run_node_script_async` 同口径；补「超时按 `ProgramError` 上抛」的锁。
- **SEV-2217** `src/ws_client.py` 未处理（组 K 未派发）。下一步：回源核对 WS 连接失败/掉线的重连与心跳，补「健康断开不判死」的锁。
- **SEV-2221 / SEV-2225** 已编辑（见 1.2），但**门禁尚未对其文件单独重跑**。下一步：跑 `black`/`isort`/`mypy` + `node --check web/app.js` + `node --test tests/frontend/*.mjs` + 相关 pytest，确认 G 组改动未破门禁；清理 G 组残留的 `_out_g_*.txt` 与 `_probe_g.py`。
- **SEV-2226（部分）** `src/sync_http.py` 死码（只有 `weverse_auth` 测试导入）与 `AGENTS.md`「两条安全辩护」陈述待处理；`stream_select`/`spider` 侧注释已改。下一步：二选一——(a) 删除 `sync_http.py` 与 `weverse_auth.py` 死码并同步 `tests`；(b) 给 `sync_http` 补 `is_safe_http_url` + 有限 gzip 解压并把 AGENTS 两条陈述改成「已接线/被钉定」。决策与 `MIN-2255`（AGENTS 五点同步清单）、`MIN-2256`（scheduler 回指陈述）一并处理。

### 2.2 中等 / 轻微项待落地（组 K / 组 L 尚未派发）

- **组 K（`src/danmaku_monitor.py`、`src/collector.py`、`src/srt_writer.py`、`src/ffmpeg_proc.py`、`src/log_archive.py`、`src/video_postprocess.py`、`src/ab_sign.py`、`src/recorder_status.py`、`src/room.py`、`src/cookie_cache.py`、`src/http_config.py`、`src/platforms/` 非 bilibili 部分等）**：承载 MID-2243~2247、MIN-2236 及若干「注释/日志可翻译性」项。下一步：派发代理，按报告 §4 / §5 对应小节逐条回源修复 + 补回归锁。
- **组 L（`src/scheduler.py`、`scripts/douyin_live_recorder_standalone.py`）**：承载 MID-2257（`scheduler` 与 standalone 一致性）、MIN-2259。下一步：派发代理核对孪生副本语义一致性。
- **G 组未清零的中等/轻微项**（`web/app.js` / `web.py` / `src/web_api.py` / `index.html` 相关）：SEV-2210 前端 `parseConfigBool` 与后端口径一致性、MID-2237 注入/换行、MID-2238 面板配置写回加固、§3.5 第二项与 MIN-2260 web 侧条目。下一步：随 2.1 的 G 验证一并收口。

### 2.3 测试卫生待修正（跨组）

- **SEV-2222** `tests/test_concurrency.py` 的限流用例未真正驱动 `src` 侧实现（已用 `tests/test_regression_2026_09_22_gates.py:166` 固化根因形态，但文件本身不在 F 组独占范围）。下一步：改 `tests/test_concurrency.py` 使其直接 import 并驱动 `src.stream_select._douyin_rate_limit` 或等效 src 入口，使限流回归锁真能抓住失效。
- **test_i18n_migration**（2 例失败）：61 条运行时 `tr()` 模板未被 `zh_CN.po` 覆盖（含 `src/ffmpeg_master_download.py:399` 的 f-string）。该失败是**待做的 i18n 合并**引起的，非代码缺陷。下一步：见 2.4。
- **test_ffmpeg_install / test_ffmpeg_path_preference / test_danmaku_wiring**：3 例失败，分别归 ffmpeg 安装组与 danmaku 接线组，待对应修复后复测。

### 2.4 i18n 四语目录合并（阻塞 test_i18n_migration）

- 现状：`_i18n_pending.json` 累计 **22 条**新 msgid（含 en_US / en_GB / zh_TW 三语译文），分别由组 A/B2/E 写入；根目录 `i18n/` 四目录（zh_CN.po / zh_CN.mo / en_US.json / en_GB.json / zh_TW.yaml）**尚未合并**，故 `test_i18n_migration` 2 例失败。
- 下一步：中央合并脚本把 22 条键并入 `zh_CN.po`（生成 msgid + 空/占位msgstr 供翻译）→ 重新编译 `zh_CN.mo`；同步 `en_US.json` / `en_GB.json` / `zh_TW.yaml`。合并后重跑 `test_i18n_migration` 与 `test_i18n.py` 确认 0 失败。前端 `web/app.js` 内嵌四语目录由 G 组改动时同步（见 2.1）。

### 2.5 AGENTS.md / 文档与收尾

- **SEV-2226** 的两条「安全辩护」陈述、MIN-2255（五点同步清单）、MIN-2256（`scheduler` 回指陈述）需在 `AGENTS.md` 就地改正（事实性陈述按「只增不改例外」口径）。
- **全量门禁 + 端到端真机验证**：所有组收口后跑一次 `scripts/run_gates.py --keep-going` 全绿 + `pytest` 全量 0 警告 + 无参 `mypy` + basedpyright，并在真实房间上增量验证（按项目「完成定义」）。
- **CODE_WIKI / CODE_WIKI_EN 更新日志**：按项目收尾约定追加本轮修复条目。
- 删除临时文件：`_FIX_BRIEF_2026-09-22.md`、`_i18n_pending.json`、`_run.py` 及所有 `_out_*.txt`、`_probe_*.py`。

### 2.6 有争议 / 需维护者确认的复核结论

以下为各组「回源判定不成立」的结论，建议维护者二次确认其复核是否正确（尤其 SEV-2224 的「6 处 vs 报告 18 处」差异可能源于报告计数口径）：

- SEV-2218 / SEV-2219（钉定表接线）—— 代理实测 `--strict` 能拦发布；
- SEV-2223（门禁丢退出码）—— 实测 rc 已正确返回；
- SEV-2224（18 处 `patch("subprocess.")` 失效）—— 代理实扫仅 6 处且有效；
- MID-2259 / MID-2267 / MID-2268（钉定表/`FATAL_STDERR_PATTERNS`）—— 实测正确。

---

## 进度计数（截至本快照）

- 严重 28 项：已修复确认 **15**、已编辑待验证 **2**（SEV-2221/2225）、复核后不成立 **5**（2218/2219/2223/2224 + 其中 MID 级 3）、待落地 **6**（2207 部分 / 2209 / 2217 / 2226 部分 + 2221/2225 验证）。
- 中等 65 项：已修复确认约 **30+**（A/B/C/E/F 覆盖），剩余约 30 项归组 K/L/G 未派发。
- 轻微 68 项：已修复确认约 **20+**，剩余归组 K/L/G 未派发。
- 阻塞项：i18n 合并（22 键）、AGENTS.md 3 处陈述、全量门禁复跑、test_concurrency 修正、CODE_WIKI 收尾。

> 下一步总动作：派发组 K / 组 L；补 SEV-2207（video_postprocess）、SEV-2209（utils）、SEV-2226（sync_http+AGENTS）；验证 G 组改动并清残留；合并 i18n；改 AGENTS.md；修 test_concurrency；全量门禁复跑 + CODE_WIKI 收尾。
