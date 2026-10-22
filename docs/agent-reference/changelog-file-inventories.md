# 更新日志外迁清单（CODE_WIKI.md 附录）

> 本文件收 CODE_WIKI.md 更新日志里「涉及文件（按模块分类）」一类的历史文件清单，逐字搬移、未作改写。
> 原条目处保留小节标题，并以一行指针指向这里；条目名与小节名即指针里标注的定位。
> 生成于 2026-09-27 的文档体积整理（源文档同日压缩前后对照见 .workbuddy/docold）。


## v4.3.0-dev (2026-09-26) — CI typecheck 门禁补装固定版本 pytest，并修掉 `tests/test_proto_runtime_compat.py` 的 `[return]` 误报：消除「本机绿、CI 红」的检查面漂移（纯 CI / 测试改动，零运行期变更）


### 涉及文件（按模块分类）

- **模块：`tests/test_proto_runtime_compat.py`（F-14 protobuf 护栏用例）** — 辅助函数 `_declared_protobuf_specifier()` 收尾的 `pytest.fail(...)` 改为 `raise AssertionError(...)`：`raise` 是天然 `NoReturn`，与「环境里是否装了 pytest」无关，两种口径结论一致；未在其后补不可达语句（basedpyright 会报 `reportUnreachable`）。同文件 `_satisfies()` 末尾有 `return True`，其 `pytest.fail` 不受影响，保留未动。
- **模块：`.github/workflows/ci.yml`（typecheck job）** — ① setup 的 `outputs` 增 `pytest_version`；② consts 步骤声明 `pytest_version=9.1.1`（与 black / isort / mypy 同口径固定版本，防「代码未改动却 CI 变红」）；③ Install dependencies 改为 `pip install -r requirements.txt "mypy==2.3.1" "pytest==9.1.1"`，label 同步为「requirements + mypy + pytest」，并加注「为什么必须装 + 为什么钉版本」。只装 `pytest` 即够：全仓 99 个测试文件仅 import `pytest` 与 `from pytest import MonkeyPatch`，无 `pytest_asyncio` / `pytest_mock` / `pytest_cov` 导入（缺它们由 `ignore_missing_imports` 兜住）。
- **模块：`AGENTS.md`（已知坑）** — 「类型检查、注释与静态门禁」新增一条：typecheck job 必须装 pytest，否则 `tests/` 半盲；辅助函数走不到终点时一律 `raise AssertionError(...)`，不要依赖 `pytest.fail()` 的返回类型。附 `mypy --no-site-packages` 复现手法，以及「该模式下 `src/` 多出的 `no-any-return` 是噪声」的判据。


## v4.3.0-dev (2026-09-26) — 仓库元数据与文档同源同步：依赖表 / 目录树 / egg-info / 忽略清单对齐，清理已删除模块 `weverse_auth` 的残留记载（纯元数据与文档改动，零运行期代码变更）


### 涉及文件（按模块分类）

- **模块：`AGENTS.md`** — 「依赖管理」运行时依赖条数 `21 条 → 23 条`（两处），并补注 `h2`/`socksio` 的补入时点；安全下限条目里的 `starlette>=1.0.1` 更正为 `>=1.3.1`（1.0.1 自身仍落在 PYSEC-2026-2280/2281/248/249 受影响段，2026-09-21 已二次抬升）。
- **模块：`README.md` / `README_EN.md`** — 项目结构树删除 `src/weverse_auth.py`，补入此前遗漏的 `src/ffmpeg_master_download.py`（中英同步）。
- **模块：`CODE_WIKI.md` / `CODE_WIKI_EN.md`** — ① 依赖关系表由 16 条补齐到 23 条（补 `urllib3` / `h2` / `socksio` / `websockets` / `protobuf` / `brotli` / `PyYAML`，`starlette` 下限 `0.49.1 → 1.3.1`，删除空行占位）；② 目录树与测试清单去掉 `weverse_auth.py` / `test_weverse_auth.py` 两处残留；③ 「注 1」由现状陈述改为带日期的 `[历史注]`（保留「勿加 pip 上的 weverse 包」结论，因其拉入无法编译的 pycrypto）。历史更新日志条目（记录当时事实）一律未改。
- **模块：`DouyinLiveRecorder.egg-info`（构建产物，未入库）** — 经 setuptools `egg_info` 重建：`requires.txt` 补齐 `h2>=4.4.1` / `socksio>=1.0.0`，`SOURCES.txt` ；`PKG-INFO` 版本保持 `4.3.0`。
- **模块：`requirements.txt` / `pyproject.toml`（依赖清单两侧同源）** — `h2` 下限 `>=4.3.0` → **`>=4.4.1`**：CI `deps-audit` 的「下限复核」步（逐条把 `>=X` 钉成 `==X` 再 `--no-deps` 审计）报出 `h2 4.3.0` 命中 **PYSEC-2026-3628 / GHSA-6hr6-w5qg-qmwg**（重复 Host 头 → 请求走私），OSV 区间 `introduced=0` / `fixed=4.4.1`；4.3.0 只修了同源的 PYSEC-2026-1435，故**旧下限自身落在受影响段**——与 starlette、protobuf 完全同形态，解析模式（只审区间内最新版）对此全瞎。本机现装与 `uv.lock` 均已是 4.4.1，抬下限不改变解析集合；同步更新两侧清单、`egg-info`、`CODE_WIKI*.md` 依赖表与 README 双侧更新日志。
- **模块：`.dockerignore`** — 补入 `_probe_*.py`（与 `.gitignore` 同源维护；此前只排了 `_out_*.txt`）。
- **模块：`config/config.ini`（本地运行期配置，已 gitignore）** — 补入 `[Cookie]` 段的 `ttwid`（`src/ttwid.py` 的 `_CONFIG_TTWID_KEY` 与 README 均已声明、本地缺键）；写入保留 UTF-8 BOM 与 LF 行尾。
- **模块：`i18n/`（四语目录）** — 完整性核对：`scripts/extract_i18n_strings.py` 全量扫描 533 条有价值串 + 三个盲区（`print_colored` / `messagebox` / 推送模板）补扫，缺失均为 0；四目录键集一致、无空值。清理：删除 3 条 Weverse token 刷新相关孤儿条目（对应 `src/weverse_auth.py` 已于 2026-09-23 删除、全仓无代码再产出），四目录**同进同退**后均为 **780 条**；随后 `scripts/compile_po.py` 重编 `zh_CN.mo`（781 条含头部 / 110585 字节）。


## v4.3.0-dev (2026-09-24) — 构建产物体积优化：定位并排除运行期不可达模块 + zip 压缩级别 9，lite 产物 82.77MB → 64.88MB（−21.6%）、zip 54.84MB → 42.19MB（−23.1%）


### 涉及文件（按模块分类）

- **模块：`build_exe.py`（打包侧）** — 新增模块级常量 `BLOAT_EXCLUDES`（逐项附实测体积 + 不可达理由 + Pillow 容错依据）
- **模块：`scripts/report_bundle_size.py`（新增）** — 产物体积度量：总量 / 按包聚合 / 最大单文件 / dev 工具链泄漏检测…
- **模块：`tests/`（回归锁）** — `test_build_exe.py` 新增 5 条：排除清单不得命中生产代码真实导入（AST 收集 import 名…
- **模块：`AGENTS.md`** — 「构建命令」下新增「产物体积门禁」小节：度量入口、排除入口与准入条件、四项不可删的固定成本、`strip` / `upx` 两条已评估未采纳方案的理由。


## v4.3.0-dev (2026-09-24) — 前端回归锁修复 + 纳入 CI：`test_regression_2026_09_22_gates.mjs` 两条红锁定位为测试侧失效、补 `.py` 包装入 pytest/CI 回路（零生产代码改动）


### 涉及文件（按模块分类）

- **模块：`tests/frontend/`（`web/app.js` 沙箱回归锁）** — 修改 `test_regression_2026_09_22_gates.mjs`（纯 LF）3 处：
  - MIN-2241「`/` 路由反向锁」：正则 `async def index\(\)[\s\S]*?\n\n` 要求连续两个裸 LF…
  - `makeElement` DOM 桩补 `options: []`：SEV-2228 后半「danmaku_unavailable 不得推进增量游标」报 `since=0` 而非 `since=7`
  - SEV-2228 后半断言由 2 轮升级为 3 轮（success → error → 再请求）
- 随 test job 的全量 pytest 被收集。
- **模块：`.github/workflows/ci.yml`（test job 前端门禁）** — 改「Gate frontend tests not skipped」步骤：纳入新模块…
- **模块：文档 / 长期经验（`AGENTS.md` + `docs/agent-reference/session-learnings.md`）** — `AGENTS.md`「盲点 3」把 MIN-2241 的「现例（恒红）」按「更正被证伪的事实性陈述」例外就地纠正为 `[2026-09-24 修订：已改 \r?\n\r?\n]`


## v4.3.0-dev (2026-09-24) — `src/` 四文件注释精简：选源探针 / SRT 字幕 / 同步 HTTP / ttwid 凭据缓存「砍推导留结论 + 相邻复述改交叉指向」（纯注释改动，零逻辑变更）


### 涉及文件（按模块分类）

- **模块：选源 / 探针子系统（`src/stream_select.py`）** — 修改 1 个文件，净删 11 行注释：
  - 函数头长块「砍推导留结论」：`_probe_hls_segment`（19→15…
  - `select_source_url` 内 SEV-N05 两段重排：proxy 归一段（含 `async_http:255/365`、`room:92/176/268`、`spider:3495` 对照与 `[历史注] sync_http:179` 证伪、`grep` 复核命令）与「整轮共用 Client + 构造失败收敛为 `probe_client=None`」段（① ② ③ 三条理由、`_mark_probe_reject` 不误记、不新增 tr 模板须同步四语目录的约束全留）。
  - 相邻复述改交叉指向：`_validate_stream_url` 体内的「同 host 探针节流」与「末位放行 ≠ ffmpeg 不可拉流」两处不再复述根因…
  - **就地纠正 1 处被证伪陈述**：Range-GET 重试注释原写「隔 `_GET_RECHECK_INTERVAL` 重试」
- **模块：弹幕子系统 / SRT 字幕（`src/srt_writer.py`）** — 修改 1 个文件，净删 5 行注释：
  - `write()` 内 MIN-2236③ 的「块号回卷」推导（4→2）改为指向 `_open_segment`（该处终态判定仍是唯一事实源）
  - MIN-24①「节流重试开片必须早于生成条目」6→5（`_index=0` / `_last_end=None` 清零时序、SRT 块序号递增规范、「本片首条从 1 开始」两种前置结果保留）
- **模块：同步 HTTP 客户端（`src/sync_http.py`）** — 修改 1 个文件，净删 10 行注释：
  - 模块头「安全边界」与「调用面」两段内部重排合一（23→17）：F-12 惰性构造理由、`grep -rn "sync_http\|sync_req(" …` 取证命令与三类命中、`src/weverse_auth.py`（2026-09-23 已删除）、`[历史注]`「sync_req 调用点全部位于 `src/spider.py`」的证伪记录（SEV-2226）、CERT_NONE 生产不可达、保留本体的两点理由（F-12 不变量 + `tests/test_sync_http.py` 回归锁）全部在场。
  - SEV-2226 响应体上限段 17→13：① 压缩态按块读 / ② 解压产出两道上限缺一不可的理由、`MemoryError` 属 `BaseException` 故兜底兜不住、「80+ 房间与 Web 面板同进程」、取值口径与「宁可放宽不误杀」、超限抛 `ValueError` 后落「空响应 = 未开播/疑似风控」的链路保留。
  - 代理分支「已知残留缺口」（`response.text` 不经两道上限保护、两种补法的代价、2026-09-23 只收口 urllib 路径）7→6…
  - 孤立注释 `# 同步 HTTP 客户端模块 - 提供同步 HTTP 请求功能`（原漂在 import 段之后）上移为文件首行模块头…
- **模块：抖音凭据缓存（`src/ttwid.py`）** — 修改 1 个文件，净删 4 行注释：
  - `_ttwid_lock`（H-2 + 必须是 `RLock` 不得退回 `threading.Lock` / `asyncio.Lock` 单例 + `tests/test_concurrency.py::test_ttwid_module_pattern` 类型锁）、`get_ttwid` 的 H-2 原实现块、`invalidate_ttwid` 的 MIN-2220「刻意整体清空而非逐桶」块各压 1–2 行…
  - `_cache_ttwid` 不再复述「镜像不参与判定」的理由链…
- **同时校准本文档模块详解 §12**：`src/sync_http.py` 小节原称「按 SSL 验证开关预构建 insecure / secure 两个 opener」


## v4.3.0-dev (2026-09-24) — 全仓注释优化：根/构建文档 3 处事实纠错 + 多子系统多层「更正考古」压缩（纯注释改动，零逻辑变更）


### 涉及文件（按模块分类）

- **依赖清单 / 构建配置（事实纠错 + 压缩）**：
  - `requirements.txt` — 修正 3 处被证伪陈述（已与代码回源核对）：(1) `requests` 用途旧注「spider / 各平台页面抓取 / Weverse 认证直连」→ 实测 `src/spider.py` 走 httpx 异步面（`async_http`）、`src/weverse_auth.py` 已于 2026-09-23 删除…
  - `pyproject.toml` — 修正与上同源的 `urllib3` 被推翻陈述（两文件口径统一）
- **Windows 停止脚本（编码保真 + 压缩）**：
  - `StopRecording.vbs` — 全程 UTF-16 LE + BOM + CRLF 字节级保真（该文件头明确警告须 UTF-16 LE…
- **前端独立播放器**：
  - 保留「钉版本 ≠ 钉内容 / 不经 CSP/nosniff / fail-closed / crossorigin 前提 / sha384 双 CDN 比对 / 升级须重算」全部要点。
- **弹幕子系统（`src/` 压缩 / 去重）**：
  - `src/base.py` — `DanmakuBase.__init__` 复述注释 2→1 行。
  - `src/collector.py` — `DanmakuCollector.__init__` 参数复述 5→3 行，保留 `write_srt` / `monitor` / `only_fans` 非显然语义。
  - `src/danmaku_monitor.py` — 去重 `suspend/resume_monitor_writes` 与 `close_monitor_file` 的「不经 `get_hub()` 初始化」复述…
  - `src/cookie_cache.py`（LF）— 删模块头「跨模块调用方式」段末的冗余总结句（与背景段重复）。
  - `src/config_bool.py`（LF）— 压缩头注释背景段与零依赖 / 循环导入理由段（22→19）
- **并发 / HTTP（`src/`）**：
  - `src/async_http.py` — 删 `get_response_status` 内对函数签名的逐字重抄（漂移型噪音）
  - `src/http_config.py` — 压缩 `get_effective_ssl_verify` 真值表（7→4），保留 FFmpeg 9.0 默认校验与 http / https 模式裁决。
  - `src/ffmpeg_proc.py` — 压缩 MID-32「修复之二」（ThreadPoolExecutor 非守护线程在 atexit 链路的死锁推导，6→4）。
- **ffmpeg 安装子系统（`src/`）**：
  - `src/ffmpeg_install.py`（LF）— 压缩 `install_ffmpeg_windows` 架构分流（9→6）、`install_ffmpeg_linux` 的 F-17 + MIN-24④ 多层考古（9→7）、MID-59（11→9）三段…
  - `src/ffmpeg_master_download.py`（LF）— 压缩模块头「正确下载方式 ①-⑤」为概览并指向各函数（13→8），保留 SEV-2222 等 ID 与具体名词。
  - `src/log_archive.py` — 压缩 `_web_console_rebind_pending` 推导段（7→5），保留 MID-2258 devnull 黑洞 / `_streams_bound_to()` 不匹配 / 每轮重试 / `_archive_lock` 全部事实。
- **审计后有意未改动（参考级「为什么」或密度近门禁）**：`i18n.py`、`msg_push.py`、`web.py`（根级）与 `src/config_io.py` —— 均为高价值单层「为什么」注释…


## v4.3.0-dev (2026-09-24) — `src/` 注释精简：`recorder_status.py`、`room.py` 砍推导留结论 + 去代码复述（纯注释改动，零逻辑变更）


### 涉及文件（按模块分类）

- **模块：`src/recorder_status.py`（录制状态快照与控制台展示）** — 修改 1 个文件，净删 2 行注释（3 处块收紧）：
  - `get_status()` 的 MI-10 块：4→3 行…
  - `display_info` 节拍头 MID-31：把「根因」从句并入括号，措辞收紧。
  - 循环末尾的 finally 退避注释：4→3 行…
- **模块：`src/room.py`（抖音房间解析 / X-Bogus / sec_user_id）** — 修改 1 个文件，净删 4 行注释（3 处块收紧）：
  - `get_xbogus()` 的「2026-09-12 审查 6.3」块：4→3 行，压缩推导句式，保留 `execjs.compile` → `utils.run_js_async` 迁移理由与 `(路径, mtime)` 缓存事实。
  - `get_sec_user_id()` 的「6.3 verify」块：4→3 行，保留 `http_config.ssl_verify` 三处 AsyncClient 一致性判据与 `sec_user_id / unique_id / web_rid` 链路。
  - `get_unique_id()` 的 MID-2246 降级日志块：7→5 行…
- **点名但有意不改**：`src/scheduler.py` —— `AGENTS.md` 注释质量参照，注释均为承重的并发语义 / 副本同步锚点，按「只增不改」保留原样。


## v4.3.0-dev (2026-09-24) — `src/stream.py` 注释精简：13 处冗长/多层「更正考古」块「砍推导留结论」（纯注释改动，零逻辑变更）


### 涉及文件（按模块分类）

- **模块：`src/stream.py`（直播流地址获取 / 画质选档降级）** — 修改 1 个文件，压缩 13 处注释块：
  - 常量表头：`DOUYIN_KEY_TO_CODE`（MID-2229…
  - 工具函数：`_pad_list`（MI-02 + 2026-09-12 审查 6.5 的 min_length 5→6 考古并入 `[历史注]`）、`_probe_headers`（MID-2227…
  - `get_douyin_stream_url`：内 `_sort_quality_items` 的 MID-2229 段（字面量版只认 ORIGIN/OD/BD/UHD/HD/SD/LD、真实键全落默认 99）。
  - `get_tiktok_stream_url`：`_pad_list` 段（MI-02）、MID-16 段（保留 `AttributeError` 与 `{"url": "", ...}` 形态）、MID-15 段（① ② ③ 三条后果与「HLS 探针一次都不发」硬语义全留）。
  - `get_kuaishou_stream_url`：MIN-06 段（数字画质两表错位、`"2"` 在通用表 UHD(2000) / 码率表 BD30(30000) 对比、`tests/test_stream.py` 与 standalone 点名保留）。
  - `get_huya_stream_url`：MID-13 段（exsphd 集合语义、`labels=[...]` / `reversed(findall(264_\d+))` / `HUYA_RATIO_TO_CODE` 全留）、MID-2228 段（`len(quality_list) > 1` 条件与三段裁决链）。
  - `get_douyu_stream_url`：MID-68 段（`ast.BinOp` vs `JoinedStr`、`err_detail` 预求值口径）。
  - `get_stream_url`：内 `get_url` 的 MID-20 + SEV-2201 段（`AttributeError: 'str' object has no attribute 'get'` 全文、`SOOP/PandaTV/WinkTV/TTingLive/TwitCasting/Twitch/百度直播/ShowRoom` 平台清单逐字保留）。


## v4.3.0-dev (2026-09-24) — `src/` 四文件注释精简：去重「函数头 vs 行内」复述与 `proxy.py` scheme 同源叙述（纯注释改动，零逻辑变更）


### 涉及文件（按模块分类）

- **模块：`src/notify.py`（通知与录制状态钩子）** — 密度 26.4% → 24.6%，净删 5 行注释：
  - `run_script()`：将「2026-09-12 审查 6.1」块从 11 行压到 8 行——逐字保留 posix=True/False 的实测拆分差异（`posix=False` 会把外层双引号当字面字符…
  - `record_error()` / `record_success()`：删除行内注释首句（「线程安全地记录一次…追加 1/0 到滑动窗口」
- **模块：`src/proxy.py`（系统代理检测）** — 密度 35.6% → 34.9%，净删 3 行注释：
  - `_split_scheme()` / `_get_proxy_info_linux()`：「socks5://… 被静默改写成 HTTP 代理语义」这条因果在文件内出现 4 次…
- **模块：`src/logger.py`（日志配置）** — 密度 35.2% 不变、净 0 行：全文件几乎都是带完整因果链的参考级「为什么」注释（GUI 双开句柄致轮转 WinError 32 与录制日志全量丢失、房间 ContextVar + patcher、`configure(extra=...)` 默认值不可删的 KeyError 后果等）
- **模块：`src/node_install.py`（Node.js 自动安装）** — **未改动**：完整性模型（P-1 权威哈希取自 nodejs.org、npmmirror 只加速）、CR-11 残缺 zip、ARM 架构识别等注释均已是最优单层「为什么」


## v4.3.0-dev (2026-09-24) — 类型存根补齐：`typings/execjs/` 7 个 `.pyi` 消除 mypy `disallow_untyped_defs` 报错（IDE 单独打开不再报 `no-untyped-def`）


### 涉及文件（按模块分类）

- **模块：`typings/execjs/`（第三方 PyExecJS 类型存根）** — 修改 7 个 `.pyi`：
  - `_runtimes.pyi`：`register(name: str, runtime: Any) -> None`、`get(name: str | None = ...) -> Any`；模块变量 `_runtimes: dict[str, Any]`。
  - `_exceptions.pyi`：`ProcessExitedWithNonZeroStatus.__init__(status: int, stdout: str, stderr: str)`。
  - `_abstract_runtime.pyi`：`exec_ -> str` / `eval -> Any` / `compile -> AbstractRuntimeContext` / `is_available -> bool`
  - `_abstract_runtime_context.pyi`：`exec_ -> str` / `eval -> Any` / `call(name: str, *args: Any) -> Any` / `is_available -> bool`；新增 `from typing import Any`。
  - `__main__.pyi`：`PrintRuntimes.__init__` 与 `__call__` 补全参数与 `-> None`；新增 `from typing import Any`。
  - `_pyv8runtime.pyi`：`Context.__init__(source: str | None = ...)`、`convert(cls, obj: Any)`。
  - `_external_runtime.pyi`：`ExternalRuntime.__init__(name: str, command: list[str], runner_source: str, encoding: str = ..., tempfile: bool = ...)`、`Context.__init__(runtime: ExternalRuntime, source/cwd: str = ..., tempfile: Any = ...)`、`Context.is_available -> bool`。
- **扫描后确认无需改动**：`typings/customtkinter/__init__.pyi`、`typings/pystray/__init__.pyi`（两包全部函数均已带完整参数/返回值注解…


## v4.3.0-dev (2026-09-22) — 元数据同源同步 + 全量质量门禁跑批 + 四语目录核验（本轮零产品代码改动）


### 一、按模块分类的改动

| 模块路径 | 变更类型 | 变更内容 | 验证方式 |
| --- | --- | --- | --- |
| `DouyinLiveRecorder.egg-info/` | **元数据重建** | 经 setuptools `egg_info` 重新生成，消除与 `pyproject.toml` 的两条漂移：`requires.txt` / `PKG-INFO` 的 `starlette` 下限 `1.0.1 → 1.3.1`、`protobuf` 下限 `6.31.1 → 6.33.5`（上限 `<8` 保持，F-14）；`SOURCES.txt` 补入本轮新增的 6 个测试文件（`test_config_io_update_file` / `test_node_install` / `test_platform_danmaku_offline` / `test_spider_hardening` / `test_video_postprocess_paths` / `test_web_tray`）；版本仍为 4.3.0，`PKG-INFO` 行数 1401 未变 | `scripts/check_version.py` PASS；`pyproject [project.dependencies]` / `requirements.txt` / `requires.txt` 三方 21 条逐一对齐（唯一差异是 setuptools 把 `protobuf>=6.33.5,<8` 规范化为 `protobuf<8,>=6.33.5`，非实质差异） |
| `config/config.ini` | 配置键补齐 | `[Web]` 节补 `web_allowed_hosts`。该键由 MID-36（DNS 重绑定防线）引入、此前只存在于 `src/web_config.py::WEB_DEFAULTS`，未写盘、未见于任何配置文档——新用户拿不到、且依赖「缺键补写」路径才会出现 | configparser 解析通过（BOM 保留）；`[Web]` 键由 8 个增至 9 个 |
| `README.md` / `README_EN.md` | 文档同步 | `[Web]` 配置块补 `web_allowed_hosts` 及中英说明（何时需要填、不填的后果）… | 两份 README 段落逐条对应 |
| `CODE_WIKI.md` / `CODE_WIKI_EN.md` | 文档同步 | Web 配置表补 `web_allowed_hosts` 行，写明 `src/web_config.py::is_host_allowed` 的真实判定口径（IP 字面量与无点号单标签名天然放行，多级域名必须显式登记；`web_host` 绑到 `0.0.0.0`/`::` 时不入名单） | 回源核对 `is_host_allowed` 源码后落笔 |
| `.gitignore` / `.dockerignore` / `pyproject.toml`（`[tool.black]`、`[tool.isort]`、`[tool.mypy]`、`[tool.coverage.run]`、`[tool.basedpyright]` 五段）/ `.coveragerc-concurrency` | **同源清单补齐** | 补入 `.qoder-credits/`——第三方编码代理的产物目录，是当时唯一「既不在 Git 忽略里、又会进 Docker 构建上下文、还会被工具扫描」的根级目录。八处清单同步后，与既有 14 个本地工具目录口径一致 | `black --check .` / `isort --check-only .` 均 rc=0；逐 token 比对八份清单无遗漏… |
| `AGENTS.md` | 防回归条目 | 「类型检查、注释与静态门禁」新增 2 条：① **删除模块级函数/常量前必须 grep 全部调用点**（附 `and` 短路让 `NameError` 延迟爆炸的机理）；② **转发型测试桩的 `*args`/`**kwargs` 一律注解 `Any`**（写 `object` 时只有 basedpyright 报 `reportArgumentType`，mypy 不报） | 条目触发源均为本轮实测发现 |
| `i18n/zh_CN/LC_MESSAGES/zh_CN.mo` | 重新编译 | 664 条（含 gettext 头部空 msgid）、85 544 字节；编译前后 `--check` 均 PASS，说明 .po 与 .mo 本就同步，重编译未产生内容增量 | `scripts/compile_po.py --check` |


## v4.3.0-dev (2026-09-21) — 工作区改动全量台账（按模块）：`CODE_REVIEW_2026-09-21` 修复轮 + 覆盖率专项


### 批次 B：按模块分类的已落地改动

| 模块路径 | 报告 ID | 变更内容 | 配套测试 |
| --- | --- | --- | --- |
| `src/spider.py` | **SEV-N02** | PopkonTV 刷新出的 token 落盘时已自带 `Bearer ` 前缀，读回后再拼一次造成双前缀、凭据复用失效；写入侧归一… | `tests/test_spider_platforms.py` |
| `src/spider.py` | **SEV-N04** | 淘宝用响应 `Set-Cookie` 整体覆盖用户 Cookie 并持久化回写 `config.ini`，登录态被静默销毁… | `tests/test_spider_hardening.py` |
| `src/spider.py` | MID-48（09-20 报告项，本日内/海外批次执行） | 平台解析层「裸取 JSON + 装饰器兜底」范式收敛：`_loads_dict` 替代裸 `json.loads`，深层链式索引改走 `_dig` 安全下钻（WAF/拦截页返 HTML 时不再抛 `JSONDecodeError`） | 沿用既有 spider 用例 |
| `src/web_api.py` | **SEV-N03** | 面板「非回环监听 + 无认证」不变量可被两步 PUT 旁路（判定基准 `web_host` 自身可经 API 改写）。改为安全判定统一取 `_guard_bind_host(app, …)` = **进程实际绑定地址**，403 文案收敛到 `_insecure_bind_detail(action, bind_host)` | `tests/test_web_api.py` |
| `src/web_api.py` | MID-N42 | Origin 与 Host 是**两套名单**：Host 沿用 `web_config.is_host_allowed`，Origin 单独判定；且端口与地址同判（`web_port` 同样是可经 API 改写的配置值） | `tests/test_web_api.py`、`tests/test_web_config.py` |
| `web.py` | **SEV-N03**（同项） | 启动时把**本进程实际要绑定的**地址与端口传给 app 状态，作为安全判定的唯一来源（不再回读配置值）… | 同 `tests/test_web_api.py` |
| `src/web_config.py` | MID-N45 | 新增「出站目标」收口层：推送接口链接 / ntfy 地址 / 代理地址 / SMTP 等白名单内 URL 类键一律过校验；抽共用内核 `_validate_room_url_target`，并新增 `allow_local_targets` 豁免（仅放行回环 + RFC1918/ULA 的「用户自己网络」）；破例通道**没有**复用 `DOUYIN_WEB_ALLOW_INSECURE` | `tests/test_web_config.py` |
| `src/stream_select.py` | MID-N32 | 播放列表 / 分片 / 同源 FLV 回退地址均为带签名参数的直链，其探测日志此前未脱敏；本文件内探测日志统一过脱敏… | `tests/test_stream_select.py` |
| `src/config_io.py` | MID-N57 | 备份脱敏此前只接 `is_sensitive_item` 一道判据，未叠 Web 面板侧的「节白名单 + 键名正则」口径，存在漏脱敏面；现为双重判据… | `tests/test_config_io_backup.py` |
| `src/javascript/haixiu.js` | MIN-N39 | 尾部注释里的真实形态抓包样例改为 `<REDACTED>` 占位；删除引用 jQuery `$` 的 `bnu` / `bn` 死代码（**仅注释/死代码级改动，签名链路 `bsq→pf→as→brm→cls→pt` 未动**） | 由 `check_runtime_pins.py` / `_JS_SHA256_EXPECTED` 覆盖 |
| `src/utils.py` | MIN-N39 | `_JS_SHA256_EXPECTED` 中 `haixiu.js` 与 `migu.js` 两条钉定值重算（旧值 `e8f13f4a…` / `01bf22bd…` 作废）；表注释改为「5 条即在用全部脚本」并记录实测依据 | 同 `tests/test_utils.py` |
| `CODE_REVIEW_2026-09-21.md` | — | **新增文档**（540 行全量源码审查报告，含 P0 6 项 / P1 74 项分组），是本批次的输入源… | 不适用 |


## v4.3.0-dev (2026-09-21) — CODE_REVIEW_2026-09-20 全轮修复落地：严重 10 项 + 中等/轻微按主题成批 + 五类新门禁


### 九、按模块分类的全量改动清单（新增 / 修改 / 删除 + 文件路径）

**统计口径**：以 2026-09-20 22:15 的工作区快照为基线逐文件比对，含无扩展名文件（`Dockerfile`）与点文件
（`.gitignore` / `.dockerignore`，二者基线未快照、按实际编辑计入）。合计 **修改 91 个文件、新增 19 个、删除 2 个**。
其中 80 个由基线快照直接 diff 得出；另 11 个基线未快照（4 份翻译目录 + 2 份 README + 2 份
`docs/agent-reference/` 外迁文档 + `.gitignore` + `.dockerignore`）按内容证据计入，其行数不在本表维护。
表中 `+x/-y` 为 unified diff 的新增/删除行数（`StopRecording.vbs` 源文件是 UTF-16 LE，行数量级不代表语义改动量）。
「关联条目」列的编号指向 `CODE_REVIEW_2026-09-20.md`；`—` 表示该文件的改动是上述条目的连带同步，无独立编号。

##### 9.1 录制主编排与房间线程（CLI 入口）

| 路径 | 类型 | 改动要点 |
| --- | --- | --- |
| `main.py` | 修改 `+555/-138` | 看门狗停滞判据由「进程起跑时刻」改为「最后一次字节增长时刻」（新增 `_stall_since`），单次录制时长上限提为可配置 `max_record_seconds` 且分段关闭时不生效、到点后走与 `rc==0` 同一条收尾（转码 + 成功样本 + 撤销退避）；`only_flv` 分支把 `recording` 登记与字幕线程启动下移到 `flv_url` 校验通过之后并在未命中分支 `clear_record_info`；等待录制槽放弃分支补状态清理；输出目录创建失败即跳过本轮、且输出侧启动失败不再判成 CDN 快速失败；`http_record_list` 的 `"migu"` 改 `"咪咕直播"`；`PLATFORM_HOST` 无表项域名处置；`_record_output_bytes` 由 `save_file_path` 推导真实扩展名并复用 `_\d+\.` 正则（不再硬编码 `.ts`、兼容 4 位序号）；直下路径 `_downloaded >= _MIN_VALID_RECORD_BYTES` 才算成功；`check_subprocess` 的收尾形态不再读热更新全局而是随命令模板推导；`config.read()` 每轮 `clear()` 后重读；`_sync_ssl_disable_platforms` 进主循环按值变化重跑；`split_time` 走 `_safe_int`；`finally` 增「进程存活则 terminate + unregister + clear_record_info」统一收敛；`room_stopped` 从 `while True` 体内移到线程退出 finally；`create_var` 键改生命周期无关且 pop 前校验线程身份；强制直下收尾改走 `clear_record_info`；流地址日志 7 处过 `mask_credentials`；`_match_stream_suffix` 由子串包含改为按 path 扩展名判定（新增 `_stream_path_suffix`）；`delete_line` 返回值落地为「未删即告警」 |

##### 9.2 并发调度与运行状态

| 路径 | 类型 | 改动要点 |
| --- | --- | --- |
| `src/scheduler.py` | 修改 `+97/-28` | `ResizableSemaphore` 拆 `_capacity`（上限，只由 `set_value` 改）与 `_used`（已持有，只由 acquire/release 改），新增 `capacity` 属性、`value` 语义保持「剩余许可」；`recompute()` 改与 `capacity` 比较，杜绝「有持有者时每轮补满可用数」；`PlatformBreaker` 加 `_probe_seq` + 探针归属（按 `Thread` 对象身份），陈旧探针回报不再驱动 half-open 迁移，租约自愈原样保留；补 standalone 副本回指注释 |
| `src/recorder_status.py` | 修改 `+44/-4` | `_live_network_capacity()` 改读 `capacity`（此前显示的是空闲槽数）；`display_info` 的 `sleep` 移出 try、`sys.stdout is None` 显式早退、异常按连续失败次数退避（封顶 300s），消除无控制台/句柄关闭态下的 100% CPU 忙等 |
| `scripts/douyin_live_recorder_standalone.py` | 修改 `+41/-10` | 并发实现副本同步 `capacity`/`used` 拆分（SEV-01 残留形态），并写明「两份 `PlatformBreaker` 方法数不等价（9 vs 5）」 |

##### 9.3 HTTP 客户端、代理与凭据

| 路径 | 类型 | 改动要点 |
| --- | --- | --- |
| `src/async_http.py` | 修改 `+152/-57` | `_client_cache` 键加入事件循环维度（`(proxy, verify, http2, loop)`），只逐出属于当前循环的条目并按 `loop.is_closed()` 惰性清扫（此前每个请求都在逐出他房间存活客户端 → 全量重建 + 套接字泄漏）；登录/取 Cookie 类调用与共享 jar 隔离；`get_response_status` 新增 `platform` 形参、`verify` 缺省取 `get_effective_ssl_verify(platform)`；跨循环仍**不创建** `aclose()` 协程 |
| `src/sync_http.py` | 修改 `+17/-0` | `sync_req` 入口统一 `handle_proxy_addr`（裸 `ip:port` 代理此前只被异步侧兼容）… |
| `src/proxy.py` | 修改 `+88/-33` | IPv6 括号形态 `rsplit(":", 1)` + `[]` 特判（原实现必抛 `ValueError`、`__post_init__` 校验整块是死代码）；Linux 同时读大小写环境变量并补 `all_proxy`；保留代理凭据 |
| `src/weverse_auth.py` | 修改 `+23/-5` | 改走 `sync_http.sync_req(..., proxy_addr=...)`（拿回线程级 Session 复用、代理与 SSL 策略），失败响应体过 `mask_credentials` |
| `src/ttwid.py` | 修改 `+65/-7` | 进程级 ttwid 记录获取时刻并按 `cookie_cache.DEFAULT_TTL` 判定；新增 `invalidate_ttwid()`（同时清三层… |
| `src/cookie_cache.py` | 修改 `+12/-1` | `singleflight` 补齐 `fetch_cookies` 才有的世代比对，使 `invalidate_generic` 有真实语义… |

##### 9.4 选源、探针与画质档位

| 路径 | 类型 | 改动要点 |
| --- | --- | --- |
| `src/stream_select.py` | 修改 `+186/-43` | `record_url` 通道同受 `hls_effective_enabled` 约束（「HLS 采集排除=零探针」语义闭环）并复用已探结论（不再对同一地址二探烧连接预算）；末位放行前过 `_is_recordable_url`（scheme 白名单 http/https/rtmp/rtmps + netloc 非空 + 拒绝前导 `-`/空白），畸形值不参与放行；分片退避键改记播放列表 URL；master playlist 按 `BANDWIDTH` 选最高变体探测；MID-17 经复核**不改实现**并在 `_PROBE_BACKOFF_PLATFORMS` 处写明不采纳理由 |
| `src/stream.py` | 修改 `+190/-47` | 虎牙旧档分支废掉「位置式 zip 贴标签」，改由 `HUYA_RATIO_BY_CODE` 值驱动并把 `8000/2000/500` 与 `1000/250` 就近映射、表外值按数值取档且 `ratio != target` 即告警；TikTok 不再把 m3u8 塞进 `flv_url`、`_pad_list` 后统一过滤 `None`/空 url；`get_stream_url` 补 `@trace_error_decorator`、按 `url/play_url/m3u8_url/flv_url` 顺序取值、`play_url.get(key)`；B 站 `qn→code` 反向表显式优先高档并过滤表外 qn；快手数字画质先经 `get_quality_index` 解析再查 bitrate |

##### 9.5 平台接口解析与签名

| 路径 | 类型 | 改动要点 |
| --- | --- | --- |
| `src/spider.py` | 修改 `+1385/-458` | `_shopee_host_suffix` 先剥 `live.` 再取首点后缀并合并退化 if/else；`login_popkontv` / `login_twitcasting` 改 `_or_none` 且调用点判空后解包、写 Cookie 前 `isinstance str`；B 站 buvid 失效同时清 `cookie_cache` 泛型键；抖音 APP 路径 ORIGIN/codec 改取刚解析的 `parsed_data`；花椒 `encode=h264` 与 `h264_url` 自洽；淘宝 `broadCaster` 取 `accountName`/`nick`；WinkTV 判空后解包；百度/PopkonTV 正则收 `(?=&\ | $)`；TikTok 内置游客 cookie 过期时定向告警；SOOP 相对清单改 `urljoin`；斗鱼 betard/B 站 playUrl/Twitch GQL 走 `_loads_dict` + 判空、POST 体改 dict 交统一编码、`enc_data` 缺失零请求；小红书 `sid` 加 env→config→内置三级覆盖；Twitch `browser_version` 与 UA 同源、`os_version` 交编码层；kuaishou did / twitch client-id 加时刻与 TTL + 失效钩子；**MID-48 全量收口**：裸 `json.loads` 78 → 2（唯一豁免 `get_twitchtv_room_info`），统一 `_loads_dict` + `_dig/_dig_str/_dig_list` + `_warn_api_abnormal` | SEV-06/07，MID-33/40…50 |
| `src/platforms/douyin.py` | 修改 `+62/-3` | 「WS 握手被 HTTP 200 拒绝」分支调 `invalidate_ttwid()`（只认 200、单次会话一次），使凭据被作废后无需重启即重取… |
| `src/javascript/migu.js` | 修改 `+209/-44` | 删除「malloc 前一次性缓存堆视图」，改 `heapU8()/heapU32()` 每次从 `memory.buffer` 重建（越界写抛错而非静默 no-op）；`UTF8ToString` 走 `TextDecoder('utf-8')`、长度参数统一 UTF-8 字节长；空 `ddCalcu` 哨兵；wasm/manifest 拉取处写明信任边界并加 https-only、精确主机白名单、manifest 形态与 wasm magic/尺寸守卫 |
| `src/javascript/laixiu.js` | **删除** | 无调用方死代码（逻辑已在 `src/spider.py` 以 Python 重写），且 `CryptoJS = require(...)` 是隐式全局… |
| `src/javascript/taobao-sign.js` | **删除** | 无调用方死代码，且注释残留结构完整的真实抓包入参（会话令牌形态值）… |

##### 9.6 弹幕链路与产物收尾

| 路径 | 类型 | 改动要点 |
| --- | --- | --- |
| `src/collector.py` | 修改 `+161/-14` | 在「loop 已发布但未 running」窗口做 ≤0.5s 有界等待 + `run_until_complete` 前二次复查停止事件（两条相反顺序保证原样保留）；sentinel 改 `put_nowait`、`queue.Full` 时置停止事件让写线程自检退出、join(3s) 且 sentinel 失败绝不阻断 `srt.close()`（此前会卡死在 `finally: _rec_sem.release()` 之前泄漏录制槽）；`_shutdown` 先 `cancel()` 再让取消传播后 `loop.stop()`，消除 pending Task |
| `src/danmaku_monitor.py` | 修改 `+258/-52` | 边车落盘移交进程级单写线程（有界队列 + 丢弃计数 + `flush()`），全局锁内只完成统计与 payload 构造，慢盘不再串停所有房间事件循环… |
| `src/ws_client.py` | 修改 `+74/-13` | 重连进入 `continue` 前显式 `self._ws = None`（原清理块不可达）并按 `state is OPEN` 判活；`send_nowait` 改 `spawn_danmaku_task` + `_pending` 强引用 + 堆积上限 64 |
| `src/srt_writer.py` | 修改 `+17/-7` | 重试开片的 `_index`/`_last_end` 复位移到行生成之前，消除同一 `.srt` 内重复序号与非单调时间轴；注入清洗与片内钳制不变… |
| `src/ffmpeg_proc.py` | 修改 `+102/-19` | `as_completed` + `f.result(timeout)` 死代码改为总预算 `wait`（并把 `ThreadPoolExecutor` 换成 ≤8 守护线程组——非守护 worker 会在解释器 finalization 时被 join，只改 `wait` 仍挂 atexit）；stdin 写完即关；三段超时按剩余预算分配（不再出现 `timeout//3 == 0` 直接 terminate 丢 MP4 moov）；未确认清理显式告警 |
| `src/video_postprocess.py` | 修改 `+77/-6` | 超时/失败分支删除本次生成的半成品 mp4 并明确「已保留源文件」；重编码超时按源体积线性放大（1.5s/MB，下限 600s、上限 3600s）… |

##### 9.7 配置读写、脱敏与原子写

| 路径 | 类型 | 改动要点 |
| --- | --- | --- |
| `src/config_io.py` | 修改 `+25/-10` | `delete_line` 两侧 `rstrip("\r\n")` 后比较（修复 MI-11 引入的 CRLF 恒不匹配、Windows 必然静默失效），并返回 bool；未命中不落盘、可观测性交回调用方 |
| `src/utils.py` | 修改 `+256/-43` | `mask_credentials` 补齐头形态（`Cookie:`/`Authorization:`）、JSON 体（`"access_token": …`）与 cookie/sid_guard/ttwid 族键，并识别无 scheme 的 `user:pass@host`；`replace_url`/`remove_duplicate_lines` 改持 `file_update_lock` + 原子写、回退分支先 `clear()`；`atomic_write_text` 加 `fsync`（replace 前）与 mkstemp 唯一 tmp 名并保留原文件 mode；`run_node_script_async` 消除 check-then-use；`_JS_SHA256_EXPECTED` 同步（migu.js 新哈希 + 两个死脚本条目移除）；6 处 f-string 日志改 `i18n.tr` |

##### 9.8 Web 管理面板（后端 + 前端）

| 路径 | 类型 | 改动要点 |
| --- | --- | --- |
| `src/web_api.py` | 修改 `+428/-66` | `PUT /api/rooms` 显式校验 + 校验下沉（见 `web_config`）；Web 节全部判定统一 `key_norm`（大小写变体不再绕过哈希化/防清空/token 吊销），认证降级在 `web_host` 非回环时拒绝，鉴权中间件每请求重跑不变量；Host 允许名单 + Origin 用服务端主机重建；阻塞 IO（磁盘容量、整文件读写、日志归档、目录 stat）移入 `asyncio.to_thread` 并给 `get_status` 加 `wait_for` + `stale` 标记；口令校验/哈希升级写盘走线程池、迭代次数设上限、限流键改用连接层地址且仅对可信代理剥 XFF + 全局失败预算；对外错误改固定 error code、细节只进日志；敏感项拒绝空值与字面 `'***'`；`PUT /api/language` 先切换再落盘**生效码**并在写失败时回滚内存态；删除/改写房间按 `delete_line` 返回值 + 重解析复核决定 200/500 |
| `src/web_config.py` | 修改 `+300/-26` | 内网拦截由前缀黑名单改 `ipaddress` 语义判定（loopback/private/link-local/reserved/multicast + CGNAT `100.64.0.0/10` + 元数据 IP + 基准测试/IETF 保留段），并支持 `inet_aton` 缩写形态（十进制/八进制/短写）解析与 **DNS 解析后逐地址复核**、无法解析即拒绝；画质白名单上移到公共 `validate_room_target`，校验下沉进唯一写入口 `format_url_line` |
| `web.py` | 修改 `+25/-2` | 非回环 + 无认证的启动瞬间判定改为与中间件同源的可复用检查… |
| `web/app.js` | 修改 `+137/-24` | 掩码项渲染打 `data-masked` 标记，清空提交须显式确认、服务端 400 走专门文案；`setLogoutVisible()` 让 `/api/logout` 在登录后真正可达（`showLogin` 收起）；`api()` 解析 JSON 只取 `detail`，非 JSON 不回显原文（避免绝对路径进 toast）；新增 `SENSITIVE_MASK` 与后端同源 |
| `web/index.html` | 修改 `+3/-3` | 主题/语言控件的硬编码中文 `title` 改走 `data-i18n-title`；两处表头回退文案入目录… |
| `web/style.css` | 修改 `+3/-0` | 仅新增 `.hint-masked` 提示样式；`#rooms-view` 的 `table-layout: fixed` 与定宽规则未动… |

##### 9.9 GUI / i18n / 推送

| 路径 | 类型 | 改动要点 |
| --- | --- | --- |
| `gui.py` | 修改 `+289/-53` | `URL_config.ini` 读取改 `utf-8-sig` 并与 `parse_url_config` 同判据（BOM 不再绕过 CR-01 挂死守卫）；语言菜单以 `unique_display_names()` 消歧（en_US 可选）并按 `set_language` 返回的生效码回写与提示；画质监控降级条目带 `alert_at` 并按时间戳复位；高级设置保存前重读盘比对基线 + mtime 监听 + 冲突确认；`_stopping` 复位进 `finally` |
| `i18n.py` | 修改 `+56/-7` | `set_language` 走 `has_catalog`/`resolve_language` 口径并返回**实际生效**语言码；新增 `unique_display_names()` |
| `msg_push.py` | 修改 `+23/-8` | Bark 类渠道把「路径末段即密钥」作为通则遮蔽（去掉 `day.app` 主机白名单），自建/反代服务器短 key 不再明文进轮转日志… |
| `i18n/zh_CN/LC_MESSAGES/zh_CN.po` + `.mo` | 修改（`.mo` 重编译） | 本轮累计新增 26 条 msgid（MID-68 转换 + 各模块新告警 + GUI 弹窗），`.mo` 头部 N=**664**（含头部空 msgid）、有效条目 **663**；`compile_po.py --check` 与 `extract_i18n_strings.py`（缺失 0）均绿 |
| `i18n/en_US.json` / `en_GB.json` / `zh_TW.yaml` | 修改 | 与 `.po` 同步至各 **663** 键，占位符集合逐条一致（避免 `zh_TW` 曾因 `{message_2}` 与调用方 `message=` 不一致导致推送整条崩） |
| `README.md` / `README_EN.md` | 修改 | 移除已删除 JS 脚本的目录树条目并修正树形字符 |

##### 9.10 打包、安装器与发布链

| 路径 | 类型 | 改动要点 |
| --- | --- | --- |
| `build_exe.py` | 修改 `+169/-34` | `_PINNED_RUNTIME_SHA256` 改按 `<os>-<arch>` 运行时键 × `ffmpeg`/`node` 槽位分列；`_is_pinned()` 以「64 位小写十六进制」形状为唯一判据；新增 `--require-pinned`/`--allow-unpinned`（CI 下自动开启）且缺钉定在**下载之前** `SystemExit`；`DLR_RUNTIME_SHA256` 环境通道；`_download_file(slot=)` 改必填关键字参数（消除 macOS/Linux 漏传导致的静默无校验下载） |
| `src/ffmpeg_install.py` | 修改 `+87/-16` | 官方源 ToFU 旁路文件按构建标识（Last-Modified/ETag/Content-Length）命名，上游换构建不再造成「官方源 + 蓝奏云双拒」死路；拒绝时给出「删除 <path> 后重试」的具体路径；就地纠正被证伪的 yum→apt 注释并让回退真正发生 |
| `StopRecording.vbs` | 修改 `+296/-10` | 补三个 pip 启动器映像名（此前主进程完全不被匹配 → 只杀 ffmpeg 留下复活源）；shim 判定改词边界 + 首 token basename（不再整条命令行子串定罪误杀编辑器/pytest 进程）；静默模式改为遍历比对 `-y` 取值。文件仍为 UTF-16 LE + BOM + 全 CRLF（按原始字节复核） |

##### 9.11 维护脚本与门禁

| 路径 | 类型 | 改动要点 |
| --- | --- | --- |
| `scripts/check_runtime_pins.py` | **新增** `189L` | 钉定表结构校验（缺平台/缺槽位/占位值 → rc=2）、`--strict`（发布闸口 rc=1）、`--emit-env`（把钉定表作为 JSON 供 CI 透传） |
| `scripts/run_gates.py` | 修改 `+133/-11` | 解析 AGENTS 门禁块行首 `NAME=value` 前缀并注入子进程环境；`GATE_CHILD_ENV` 默认 `PYTHONUTF8=1`；`FATAL_STDERR_PATTERNS` 把「只告警、rc 仍为 0」的形态判失败；`ensure_utf8_streams()` 修 cp936 下转发 black 成功行 `✨` 崩溃 |
| `scripts/check_coverage.py` | 修改 `+54/-2` | 「无数据」由 WARN 改为 rc=2 硬失败并打印下一步命令（区分「没跑测试」与「覆盖率不达标」）… |
| `scripts/check_version.py` | 修改 `+55/-1` | 新增「`ARG` 声明行必须早于使用所在**指令起始行**」行序断言（续写回溯、注释行跳过）… |
| `scripts/check_annotations.py` / `scripts/extract_i18n_strings.py` | 修改 `+2/-1`（各） | 移除对已删除 `gui_legacy.py` 的引用 |

##### 9.12 CI、容器与依赖清单

| 路径 | 类型 | 改动要点 |
| --- | --- | --- |
| `.github/workflows/ci.yml` | 修改 `+117/-6` | black/isort 步骤 step 级 `PYTHONUTF8=1` 并与 AGENTS 块逐字对齐；新增 `Gate isort/black silent-skip warnings` 兜底步骤；新增 `deps-audit` job（`pip-audit -r requirements.txt`，两条审计步骤各带 UTF-8）并计入 `ci-summary.needs`；清 `gui_legacy.py` 引用 |
| `.github/workflows/build-release.yml` | 修改 `+32/-2` | prepare 跑 `check_runtime_pins.py --strict` 并以 `--emit-env` 把钉定表透传为 `DLR_RUNTIME_SHA256`；build 命令显式 `--require-pinned` |
| `.github/workflows/trivy.yml` | 修改 `+15/-4` | `checkout` 升 v7、分支过滤去模板残留、镜像名改本地构建标签、`--build-arg APP_VERSION` 从 pyproject 读出后… |
| `.github/workflows/issue-translator.yml` | 修改 `+29/-5` | 降级为仅 `workflow_dispatch` + 顶层 `permissions: contents: read / issues: write`，文件头写明恢复自动的前置条件（当场核对的 40 位 SHA + 降权 + 记录时间） |
| `Dockerfile` | 修改 `+10/-6` | `ARG APP_VERSION` 上移到 `LABEL version=` 之前（此前 `--build-arg` 完全不生效且无构建期报错）… |
| `docker-compose.yaml` | 修改 `+7/-0` | 锚点内 `pull_policy: build`，去掉「未 build 直接 up 会去 registry 拉同名 `:latest`」的回退… |
| `requirements.txt` / `pyproject.toml` | 修改 `+19/-2` / `+13/-2` | `starlette` 下限抬到受影响段之上、新增显式 `urllib3>=2.7.0`；两份清单一一对应 **21/21**（`tomllib` 对账零差异），`protobuf>=…,<8` 上限保留 |
| `.gitignore` / `.dockerignore` | 修改 | 同步补 `coverage.json`（`--cov-report=json` 产物） |

##### 9.13 测试（新增 18 个文件 + 修改 29 个）

| 路径 | 类型 | 覆盖内容 |
| --- | --- | --- |
| `tests/test_record_watchdog.py` | **新增** `589L` | 45s 写入空档不杀 / 11min 杀、时长上限轮按成功收尾、分段关闭时上限不生效、放弃槽位与异常穿透后的状态收敛、无 `flv_url` 时 `recording` 为空且无存活字幕线程、直下体积门槛 |
| `tests/test_scheduler.py` | 修改 `+299/-0` | 有持有者时 `recompute` 不放大可用数、真实峰值并发 ≤ 容量、超额 `release` 不造许可、缩容保留已持有、探针归属/租约… |
| `tests/test_recorder_status.py` | **新增** `228L` | 控制台容量显示读 `capacity`、异常轮不忙等（注入失败 stdout + 假 sleep 计次）… |
| `tests/test_spider_hardening.py` | **新增** `1517L` | 52 个平台函数的四类载荷用例、凭据不入日志断言、`BARE_JSON_LOADS_CEILING` 棘轮与按函数名零裸 loads 扫描… |
| `tests/test_decorator_contract.py` | 修改 `+2/-2` | 全仓 AST 锁：返回注解 ↔ 兜底装饰器配对、`@decorator` 紧贴 `def`… |
| `tests/test_web_config.py` / `test_web_api.py` | 修改 `+241/-0` / `+830/-16` | 内网变体表驱动、PUT/POST 裁决一致、大小写变体三守卫、Host 允许名单、限流键与迭代上限、掩码/空值 400、CRLF 删除夹具… |
| `tests/test_web_config_locks.py` / `test_web_config_secret_mask.py` | **新增** `163L` / `185L` | 400 文案与「值未被覆写」复核、`_looks_like_secret_value` + `_validate_room_url_target` 真函数表… |
| `tests/test_stream.py` / `test_stream_select.py` / `test_quality_tiers.py` | 修改 `+317/-24` / `+263/-0` / `+6/-3` | 虎牙值驱动档位与顺序无关性、TikTok 零 HLS 探针（含 record_url）、URL 形态白名单、退避键、变体选择、B 站反向表… |
| `tests/test_collector.py` / `test_danmaku_monitor.py` / `test_ws_client.py` / `test_srt_writer.py` / `test_ffmpeg_proc.py` / `test_video_postprocess.py` / `test_cookie_cache.py` / `test_douyin_danmaku.py` / `test_ttwid.py` | 新增/修改 | 反向序握手不回归 + 丢信号窗口、锁内不落盘、重连后 `_ws` 判活、SRT 序号单调、清理总预算、超时删产物、世代比对、ttwid 失效与 TTL… |
| `tests/test_async_http.py` / `test_sync_http.py` / `test_proxy.py` / `test_utils.py` / `test_config_io.py` / `test_weverse_auth.py` | 新增/修改 | 多循环不互相逐出且同循环复用、代理地址归一、IPv6/大写环境变量/凭据保留、脱敏九类样本与公共 URL 不误伤、fsync 调用次序、CRLF `delete_line` |
| `tests/test_gui_monitor.py` / `test_i18n.py` / `test_msg_push.py` / `test_ffmpeg_install.py` / `test_stop_recording_vbs.py` | **新增** | BOM 判据、生效语言、Bark 自建主机遮蔽、旁路轮换、VBS 映像名/词边界/静默判据 + UTF-16 原始字节… |
| `tests/test_frontend_quality_ui.py` + `tests/frontend/test_quality_ui.mjs` | 修改 `+171/-9` / `+405/-19` | 进程组超时兜杀 + 结果真解析断言；登出入口可见、掩码确认、错误 detail 解析、四语目录与 `data-i18n` 键集机械门禁（27 用例）… |
| `tests/test_i18n_migration.py` | 修改 `+102/-27` | 门禁判据由「首参是 JoinedStr」收紧为「首参子树含 FormattedValue」，`tr()` 实参位不递归（约定②），并加自检用例防门禁自身假绿… |
| `tests/test_test_hygiene.py` | **新增** `273L` | AST 扫描 tests/：禁止改 stdlib 模块本体、禁止宽泛 `filterwarnings` 等四类形态（R1…R4，含正负自检）… |
| `tests/test_ab_sign.py` / `tests/test_record_failure_feedback.py` / `tests/test_start_record_command_golden.py` / `tests/test_bilibili_danmaku_info.py` / `tests/test_only_fans_defaults.py` / `tests/test_tars_frames.py` / `tests/test_platform_dispatch.py` / `tests/test_record_container.py` / `tests/test_spider_fixes.py` / `tests/test_spider.py` / `tests/test_machine_validation_fixes.py` | 修改 | SM3 标准 KAT 与冻结时间确定性、shim 化 stdlib patch、`capacity` 桩与直下体积口径、AsyncMock 去 ignore、跨层默认值、畸形帧边界、`PLATFORM_HOST` 全覆盖、分段扩展名推导、Shopee 三 TLD |

##### 9.14 文档与元数据

| 路径 | 类型 | 改动要点 |
| --- | --- | --- |
| `AGENTS.md` | 修改 `+235/-7` | 新增/纠正 20+ 处长期约定：门禁 UTF-8 与「告警即失败」、`deps-audit`（含本地复现要带 `PYTHONUTF8=1`）、SEV-10 三层防线与「三类钉定互不覆盖」、standalone 副本同步、`Dockerfile` ARG 行序、`check_coverage` rc=2、MIN-17 ref 判据、compose 不回落 `:latest`、非重入锁清单纠正（`file_update_lock` 实为 RLock，判据以定义行为准）、i18n 形参日志新判据、spider JSON 取用纪律与棘轮 |
| `CODE_WIKI.md` / `CODE_WIKI_EN.md` | 修改（两份，**行数不在此维护**——该数字自我引用，每追加一节就会漂移，同 AGENTS「计数不在本文件维护」的口径）… | 本轮更新日志条目（中英成对）：严重项表、按主题批次、新门禁、安全面、接缝收尾、验证结论、MID-48 与 CI 本地等价验证，以及本节的模块级全量清单… |
| `docs/agent-reference/measured-evidence.md` | 修改 | 新增 `isort 静默跳文件`（18 个）与 `pip-audit 本地审计读数` 两个证据段… |
| `docs/agent-reference/project-structure.md` | 修改 | 目录树补 `scripts/check_runtime_pins.py` 与 `trivy.yml` |
| `DouyinLiveRecorder.egg-info/` | 重新生成 | `PKG-INFO` 版本 4.3.0、`requires.txt` 与两份清单三方对齐（含 `urllib3`）… |
| `.workbuddy/memory/2026-09-21.md` | 修改 | 当日收尾记录：接缝判据、MID-48 收口、CI 本地验证与 Actions 待跑清单… |

##### 9.15 删除项与影响面汇总

| 删除对象 | 路径 | 影响与后续 |
| --- | --- | --- |
| 死签名脚本 | `src/javascript/laixiu.js`、`src/javascript/taobao-sign.js` | 无调用方；`_JS_SHA256_EXPECTED` 两条目同批移除，`src/javascript/` 现为 5 个被钉定脚本；README / CODE_WIKI 目录树条目一并清理 |
| 旧「位置式」虎牙档位推断 | `src/stream.py`（`labels = ["UHD","HD","SD","LD"]` + 位置 zip） | 由值驱动映射取代；固化错误语义的 `test_legacy_uhd_via_exsphd_labels` 断言同步改为 `(2000, BD8)`… |
| 旧「子串包含」流后缀判定 | `main.py::_match_stream_suffix` | 改按 path 扩展名比较（`_stream_path_suffix`），`?a=.flv` 之类尾部查询参数不再能把任意 URL 送进自定义流分支… |
| 旧「非 UTF-8 即静默跳过」门禁 | `scripts/run_gates.py`、`ci.yml` | 现带 `PYTHONUTF8=1` 且把 `Unable to parse file` 判失败；Linux 默认 UTF-8，故 CI 侧仍须靠本地这一环自… |

`basedpyright` 0/0、`check_coverage.py` PASSED（总 73.28%、`spider.py` 68.4%）、前端 `node --test` 27 passed、
翻译目录四份各 **663** 条（`.mo` 头部 N=664）。


## v4.2.0-dev (2026-09-14) — 仓库元数据与忽略规则同源同步 + 四语本地化目录一致性修复


### 一、按模块分类的落地项

- **pyproject.toml**（排除目录同源补全）：`logs` 原先只进了 black 的 exclude，isort / mypy / basedpyright / coverage 四处漏配；
  `backup_config` 更是只存在于两份 ignore 文件、五处工具排除列表全无。现已按同一口径补齐：
  - `[tool.black].exclude`：新增 `backup_config`（`logs` / `downloads` 已有）
  - `[tool.isort].extend_skip`：新增 `logs`、`backup_config`
  - `[tool.mypy].exclude`：新增 `logs`、`backup_config`
  - `[tool.basedpyright].exclude`：新增 `**/logs`、`**/backup_config`
  - `[tool.coverage.run].omit`：新增 `*/downloads/*`、`*/logs/*`、`*/backup_config/*`
  - 五处均加了「运行期产物目录（与 .gitignore/.dockerignore 同源维护）」注释，避免下次再漏。

- **.coveragerc-concurrency**（与 pyproject coverage omit 对齐）：`omit` 补齐 `*/downloads/*`、`*/logs/*`、`*/backup_config/*`。
  该文件与 pyproject 的 coverage omit 是同一份口径的两处副本，此前同样只覆盖了 `node` / `ffmpeg`。

- **.gitignore**（清理失效条目）：「临时/过程性文档」段落原按具体文件名列举 `PERF_REVIEW_2026-08-28.md`
  （连同 `CODE_CHANGES.md` / `TRAE_AGENT_CODE_WIKI.md`），这三个文件在工作区中已全部不存在，逐文件名维护会持续腐化。
  现改为 `PERF_REVIEW_*.md` 通配，并补注释明确 `CODE_WIKI*.md` / `CODE_REVIEW_FIX_1.md` / `DIAGNOSIS_*.md`
  属**正式文档、随仓库分发**，不得加进 .gitignore。

- **.dockerignore**（同上 + 覆盖新增文档）：「文档」段落同样移除已不存在的 `bili_danmuku_proxy.md` / `danmaku_check.md` /
  `todo.md` / `PERF_REVIEW_2026-08-28.md`，改为 `PERF_REVIEW_*.md` / `CODE_REVIEW_*.md` / `DIAGNOSIS_*.md` 三组通配，
  新增同类根目录文档自动落入排除、无需再改本文件；临时文件段补 `*.jsonl`（`logs/danmaku_monitor.jsonl` 等运行日志）。

- **Dockerfile**：`COPY --chown=recorder:recorder . ./` 上方的「不进镜像」清单原先逐项列举且与实际 .dockerignore 已不同步，
  改写为按 .dockerignore 的四类分组口径描述（测试与工具 / 文档 / 运行期产物 / 平台二进制与本地脚本）

- **docker-compose.yaml**：头部注释补充两条事实——① 仓库内不含 `.env`（已被 .gitignore 忽略），首次使用需自建；
  ② 卷挂载的四个宿主机目录（`config` / `downloads` / `logs` / `backup_config`）首次 `docker compose up` 时由 Docker 自动创建，
  四者均已在 .gitignore 与 .dockerignore 中忽略，容器侧同名目录由 Dockerfile 的 `mkdir -p logs downloads backup_config` 预建。
  版本号示例 `APP_VERSION=4.2.0` 与 pyproject 的 `[project].version` 一致，未变更。

- **AGENTS.md**：
  - 「项目结构」补 `.gitignore` / `.dockerignore` 两个文件条目；补三个运行期目录 `logs/`（含 `streamget.log` / `PlayURL.log` /
    `danmaku_monitor.jsonl` / `web_console.log`）、`downloads/`、 `backup_config/`；根目录文档补 `CODE_REVIEW_FIX_1.md`。
  - 「CI / workflow 约定 → dockerignore / gitignore 同源约定」条目扩展：把 `downloads/` / `logs/` / `backup_config/`
    纳入须同步维护的清单，记录本轮补齐的四处工具排除，并写明审查记录类文档走 .dockerignore 通配、但不得进 .gitignore。

- **requirements.txt**：**无变更**。逐条核对 20 个运行时依赖与 `pyproject.toml [project.dependencies]` 完全一致
  （含 `protobuf>=6.31.1,<8` 的 F-14 上限与 `websockets>=14.0` 下界），无需同步。

- **config/config.ini**：**无变更**。以 AST 扫描代码中的配置读取键与 ini 实际键做比对，差异项经核对均为
  configparser `optionxform` 的大小写不敏感匹配（`是否使用SMTP服务SSL加密` ↔ `是否使用smtp服务ssl加密` 等）
  或已合并的历史键（`是否强制启用https录制` / `是否禁用SSL证书验证(是/否)` / `虎牙是否禁用SSL证书验证(是/否)`），
  F-10 的 `tiktok_guest_cookie` 键位亦已就位。


## v4.2.0-dev (2026-09-13) — 斗鱼直播「只出 SRT、无视频」根因定位 + HLS 分片层假绿探针 + 选源加固（配置兜底 / 观测增强 / 同源候选）


### 一、按模块分类

- **src/stream_select.py（分片层探针，源于上一轮、本轮稳定化）**：
  - `_probe_hls_segment()`：列表层 GET → 跟随 master 变体 → 对**末行分片**发 `Range bytes=0-0` 探测…
  - 接入 `_validate_stream_url`：HEAD 非 2xx 与 Range-GET 200 两条路径在判定可达前均调用分片层探针，把「列表 200」与「可录制」解耦。

- **src/stream_select.py（选源加固，本轮新增三函数）**：
  - `_hls_selection_config()`（配置兜底）：经 `getattr(main, "hls_collection_enabled" / "hls_collection_exclude_platforms", 默认值)` 读取…
  - `_same_origin_flv(hls_url, flv_candidates)`（同源候选）：按 `?` 前路径比对、并把 `.m3u8`↔`.flv` 互认，识别与 HLS 同 token 的 FLV 候选，供 HLS 分片全死后回退。
  - `_log_source_choice(platform, kind, url)`（观测增强）：单行日志 `选源结论: platform={platform} 采用 {kind} 源: {url}`
  - `select_source_url`：直接读 `main.hls_collection_enabled`/`main.hls_collection_exclude_platforms` 改为 `_hls_selection_config()`

- **tests/test_stream_select.py（测试）**：
  - 修复 2 处既有失败：分片探针引入额外 GET，原 `get_calls == 2/1` 断言改为 `== 3/2`；fake 响应补 `.text`、fake client 补 `close()`。
  - 新增 5 例分片探针测试：`test_hls_segment_404_rejects_playlist` / `test_hls_segment_200_stays_reachable` / `test_hls_segment_404_last_resort_released` / `test_hls_empty_media_playlist_conservative_pass` / `test_select_source_url_falls_back_to_flv_when_hls_segments_dead`。
  - 新增 10 例加固测试：`_same_origin_flv` 匹配/None/忽略 query 三组 + `test_select_source_url_logs_same_origin_flv_fallback` / `test_select_source_url_logs_choice_on_pick` / `test_select_source_url_logs_no_usable_source` / `test_hls_selection_config_defaults_on_missing_globals` / `test_hls_selection_config_normalizes_comma_string` / `test_hls_selection_config_ignores_invalid_type` / `test_select_source_url_survives_missing_hls_config`。

- **tests/test_start_record_command_golden.py（注释规范修复）**：
  - 修复 `scripts/check_annotations.py` 报告的 1 处既有违规：`class _Cap:` 的三引号 docstring 改为类上方 `#` 行注释（语义不变…

- **i18n 四语目录（≥8 条新串）**：
  - `i18n/zh_CN/LC_MESSAGES/zh_CN.po` 追加两段（2026-09-13，分片探针 5 串 + 选源加固 3 串），随后 `python scripts/compile_po.py` 重编译 `zh_CN.mo`（字节级门禁通过）。
  - `i18n/en_US.json` / `i18n/en_GB.json` 各追加 8 键（分片探针 + 加固）

- **DIAGNOSIS_DOUYU_NO_VIDEO_2026-09-13.md（新增诊断报告）**：完整记录问题概述、视频/弹幕解耦结构、排查时间线与证据、根本原因、修复方案（源修复 / 测试 / i18n / 加固 / 注释违规）、诊断思路、验证、经验教训与参考。


## v4.2.0-dev (2026-09-13) — CODE_REVIEW_FIX_1 遗留项批量修复（22 项完成 + 3 项暂缓）+ 仓库元数据同步


### 一、按模块分类的落地项（FIX_1）

- **main.py**：F-02 移除死 import `converts_m4a`/`segment_video`（函数保留于 `src/video_postprocess.py`
- **gui.py**（F-04~F-07/F-09）：会话代号 `_session_id` 自增与 `_read_output`/`_wait_and_update_ui`/`_process_ended`/`_on_recording_stopped` 校验闭环…
- **msg_push.py**（F-24）：ntfy 测试调用在未注释路径下会发真实推送…
- **src/ffmpeg_install.py / scripts/node_install.py**（F-17/H-1）：新增 `_sha256_of_file` + `_check_or_record_zip_sha256`（trust-on-first-use）
- **src/web_api.py**（F-20）：SSE 端点占用面修复（同上）；list_files 悬空/逃出 root 符号链接崩溃与信息泄露已复核。
- **web/app.js**（F-21）：独立内嵌四语目录（zh_CN/en_US/en_GB/zh_TW）四处同步加译，改完必跑 `node --test tests/frontend/*.mjs`（6 用例）与 `node --check web/app.js`。
- **web.py**（F-22）：`/api/status/stream` 保留并修复（同上）。
- **src/web_config.py**（F-23）：行内注释引号优先（引号包裹值按闭合引号后切分，无引号回落 `" #"`/`" ;"` 启发式）；新增 `_config_write_lock` 原子写（H-6）。
- **src/utils.py**（F-16/F-25）：`read_ini_value(file_path, section, key) -> str|None`（不写回）
- **src/spider.py**（F-10/F-11/F-19）：`_read_tiktok_guest_cookie` 须在装饰器 `@trace_error_decorator` 之上插入（往「@decorator + def」之间插代码会劫持装饰器归属…
- **src/sync_http.py**（F-12）：SSL 白名单需平台域名清单，暂缓。
- **requirements.txt / pyproject.toml**（F-14 可落地部分）：`protobuf` 加 `<8` 上限（douyin_pb2 为 protoc 25.x 产物…


## v4.1.0-dev (2026-09-10) — 代码审查 28 项修复 + 仓库元数据同源同步 + 四语本地化补全（521 → 539 条）


### 一、代码审查修复（按模块）

- **`main.py`**：
  - ffmpeg 命令行 `-reconnect_delay_max 60 / -reconnect_streamed / -reconnect_at_eof` 由 `-i` **之后**移至 `-i` **之前**：`-reconnect*` 是输入级选项…
  - `_rec_sem.acquire()` 由 `Popen` **之后**移至**之前**…
  - `process.wait(timeout=30)` 的 `except Exception: pass` 改为 `except subprocess.TimeoutExpired:` 后 `kill()` + 重新 `wait()`
- **`src/ffmpeg_proc.py`**：`_cleanup_single_ffmpeg_process` / `cleanup_all_ffmpeg_processes` 增加返回值判定——终止失败时告警并仅清理 `poll() is None` 的条目…
- **`src/stream_select.py`**：异常分支改为 `if last_resort: warning; return True`，与上方稳定拒收的 `last_resort` 放行语义对齐。
- **`src/web_config.py`**：新增 `is_sensitive_key()` / `is_sensitive_item()`（正则 `令牌|密码|授权码|token|secret|passwd|password|api[_-]?key`
- **`web/app.js`**：新增 `isSensitiveField(section,key)` JS 侧等价实现…
- **`src/collector.py`**：缓存 `self._cls_name`
- **`src/srt_writer.py`**：新增 `_sanitize_srt_text()`（`\r\n→空格`、`-->→->`）
- **`src/spider.py`**：新增 `import os` 与 `_read_haixiu_token_override(is_haixiu)`
- **`src/ttwid.py`**：非阻塞获取失败时改阻塞式重新获取（串行接管），而非在锁外自行抓取，避免并发重复拉取。
- **`src/async_http.py` / `src/sync_http.py`**：请求体判定 `if data or json_data:` 改为 `if data is not None or json_data is not None:`（空 dict 应被视为有效请求体…
- **`src/danmaku_monitor.py`**：`setdefault` 改显式 `get` + 按需创建（避免每条消息都求值默认参数工厂，去噪）。
- **`src/cookie_cache.py` / `src/async_http.py`**：日志统一经 `utils.mask_credentials()` 脱敏。
- **`src/utils.py`**：新增 `mask_credentials(text)`
- **`scripts/check_coverage.py`**：`missing_modules` 由告警改为 `return 1`（门禁不再「假绿」）。
- **`scripts/smoke_test.py`**：`load_config` 对非法顶层结构抛 `ValueError`；`main()` 捕获 `(OSError, ValueError)` → `sys.exit(2)`。
- **`scripts/compile_po.py`**：`import os`，写入改临时文件 + `os.replace` 原子替换（避免中途失败留截断 `.mo`）。
- **`scripts/check_version.py`**：`strip_v` 由 `lstrip("v")` 改 `removeprefix("v")`（避免误删如 `ver` 前缀）。
- **`tests/`**：
  - `test_concurrency_rate_limit.py` 整体重写：驱动真实 `src.ttwid.get_ttwid()`（8 线程断言 `_fetch_ttwid` 仅调用一次）+ `src.stream_select._throttle_probe()`
  - `test_record_container.py`：`_segment_format_nodes(path=_MAIN_PATH)` 增加 `path` 形参；新增 `TestSegmentFormatSecondDefinitionPoint` 覆盖 `src/video_postprocess.py`。
  - `test_danmaku_wiring.py`：`monkeypatch.setattr(main.time, "sleep", ...)` 改 `SimpleNamespace` 垫片仅覆盖 `sleep`（避免污染全局 `time` 模块）。
  - `test_async_http.py`：补 `call_args.kwargs["data"]`/`["content"]` 断言。
  - 删除 `tests/test_utils.py.isorted`（isort 残留）。


## v4.1.0-dev (2026-09-10) — 遗留 8+4 项推进 + uv.lock 对齐 4.1.0（v4.1.0 第二批）


### 一、决策类 8 项推进（按模块）

- **`index.html`**：`hls.js@latest` → 钉版 `hls.js@1.7.2`（jsdelivr CDN 供应链风险；与同文件 `flv.js@1.6.2` 钉版惯例对齐）。
- **`src/http_config.py` + `main.py`**：TLS 校验拆为拉流专用（`get_effective_ssl_verify`）和控制面通用（`ssl_verify`）两条路径…
- **`main.py`**：音频分支 `SEGMENT_FORMAT_BY_SUFFIX` 与扩展名/编码器三方对齐——纯音频平台（猫耳FM/Look 等）保存类型含 m4a 时输出 `.m4a` + aac + ipod…
- **`src/notify.py`**：`run_script` 改用 `communicate(timeout=_SCRIPT_TIMEOUT_SECONDS=300.0)` + 超时后 `process.kill()` + 二次 `communicate()` 回收管道…
- **`src/web_api.py`**：鉴权模型强化三项真实改进——① 中间件统一加 `X-Content-Type-Options: nosniff` + `X-Frame-Options: DENY`（放行/拒绝两条路径均带…
- **`gui_legacy.py` 删除 + 元数据同步**：删除根目录 `gui_legacy.py`（与 `gui.py` 功能重复且遗留 `CREATE_NO_WINDOW` 启动子进程导致 `send_signal(CTRL_BREAK_EVENT)` 永远无效的 bug）
- **`src/collector.py`**：弹幕 SRT 落盘从事件循环线程解耦——`_on_message` 仅做 O(1) 入队 `queue.SimpleQueue`
- **`i18n.py` + 18 处调用站**：新增 `tr(template, **kwargs)` 助手——先 `_tr(template)` 查表…

> **预存 200+ 形参日志**仍用 f-string 形式（属历史遗留，非本批范围），不替换目录键；待后续「全部 i18n 形参迁移」专项工作推进。


### 二、真机验证 4 项保守实施（按模块）

- **`src/spider.py`**：新增 `_safe_loads(text) -> Optional[dict]` 异常安全解析（捕获 `JSONDecodeError` 记 warning 后回 None）
- **`src/ws_client.py`**：`_heartbeat_loop` 加 `asyncio.wait_for` 兜底（超时 = `heartbeat_interval + 1.0`）
- **`src/proxy.py`**：`ProxyInfo.__post_init__` 接受 IPv6 字面量——`[::1]:8080` 形如 Windows 注册表 `ProxyServer` 的常见 IPv6 配置…
- **`src/video_postprocess.py`**：`segment_video` / `converts_mp4` / `converts_m4a` 三个 `_run_ffmpeg_checked` 调用者分别新增 `except subprocess.TimeoutExpired as e:` 独立分支并按「转封装超时 / 转码超时 / 抽音频超时」分类告警…
- **`tests/test_machine_validation_fixes.py` 新增 7 项**：① `_safe_loads` 合法/非 dict/损坏 JSON 路径…


## v4.0.9.4-dev (2026-09-06) — 仓库元数据八文件同源同步 + 四语本地化目录补齐（516 → 521 条）+ 本期改动总览（按模块分类）


### 三、本期代码改动总览（按模块分类，2026-09-02 ~ 09-06）

- **`main.py`**：新增全局 `hls_collection_exclude_platforms` 与主循环解析（支持中英文逗号分隔、每轮热更新）
- **`src/stream_select.py`**：`select_source_url` 新增有效开关 `hls_effective_enabled = main.hls_collection_enabled and not hls_excluded`（命中排除列表时 HLS 候选整组剔除、不进序列）。
- **`src/spider.py`**：`extract_douyin_hevc_flv_url()` 返回前补 `&codec=h265`（已带则原样返回），修复下游 `_is_h265()` 与 h265 兜底判定漏判。
- **`src/async_http.py`**：删除跨循环 `run_coroutine_threadsafe(client.aclose(), ...)` 调度分支（根治 flaky 告警「FakeAsyncClient.aclose was never awaited」）。
- **`src/web_config.py`**：新增 `BUILTIN_QUALITIES`（对齐 `stream_select.get_quality_code`
- **`src/web_api.py`**：新增 `GET /api/rooms/qualities` 与 `PUT /api/rooms/qualities`（选项增删）、`PUT /api/rooms/quality` + `RoomQualityUpdate`（按房间切换画质…
- **`gui.py`**：新增 `_refresh_quality_context` / `_anchor_url_map` / `_anchor_quality_map` / `_quality_menu_values` / `_on_room_quality_change`
- **`web/index.html` / `web/app.js` / `web/style.css`**：画质下拉改为后端驱动的可增删选项（chips 面板）、房间列表画质列改为行内下拉 + 事件委托、新增三语/四语文案、`.data-table select` 样式。
- **`scripts/`**：`douyin_live_recorder_standalone.py` 自根目录迁入并修 `find_ffmpeg()`（脚本同级 → 仓库根 → PATH 三级探测）
- **`tests/`**：新增 `test_record_container.py`（13 用例…
- **全仓注释补齐**（2026-09-03）：41 文件 / +1370 行，经 `ast.dump` 等价性校验证明零逻辑改动。


## v4.0.9.4-dev (2026-09-06) — GUI 画质切换持久化修复 + WEB 端按房间切换画质完整链路 + 前后端单元测试补齐


### 改动清单

- `gui.py`：
  - `_on_room_quality_change`：查表前加 `re.sub(r"^序号\d+\s+", "", anchor_name)` 剥离序号前缀…
  - 新增实例字段 `_anchor_quality_map`（主播名 → 配置行当前画质），`_refresh_quality_context` 同步构建（与反查表同来自 `parse_url_config`）；
  - `_add_quality_data_row`：「设置画质」列改以 `_anchor_quality_map` 为准（查表前同样剥离序号前缀）
- `src/web_api.py`：
  - 导入追加 `update_room_quality`；
  - 新增 `RoomQualityUpdate(BaseModel)`（`url: str` + `quality: str | None`，空/None 等价移除画质段）；
  - 新增 `PUT /api/rooms/quality`：参数经 `validate_room_target` 走换行注入防护 + 白名单校验（仅放行 `BUILTIN_QUALITIES`
- `web/app.js`：
  - `buildRoomQualitySelect(url, current)`：构造行内画质下拉（选项 = 默认画质 + `qualityOptions` + 当前值兜底追加防止显示错位）
  - `loadRooms`：画质列从纯文本 `<td>` 改为调用 `buildRoomQualitySelect`；
  - 事件委托 `rooms-tbody` 新增 `select[data-action="quality"]` change 分支，转发 `changeRoomQuality(url, value)`；
  - 新增 `changeRoomQuality(url, quality)`：`PUT /api/rooms/quality`，成功 toast 后 `loadRooms()` 回拉刷新，失败 toast + 回拉恢复真值（不残留用户误选）；
  - `showView('rooms')`：`loadRooms()` 改为 `loadQualityOptions().finally(loadRooms)`，保证下拉选项在渲染前就绪；
  - 三语文案补齐（`toast.qualityChanged` / `toast.qualityReset` / `toast.qualityChangeFailed`），API 契约注释更新。
- `web/style.css`：新增 `.data-table select` 紧凑样式（`padding: 4px 6px / font-size: 12px / max-width: 110px`），与表单 `.inline-form select` 区分。
- `tests/test_web_api.py`（既有 `TestRoomQualityApi` 基础上扩展至 8 用例）：
  - `test_change_quality_requires_auth`：无 Bearer token 的 PUT 必须 401；
  - `test_change_quality_on_disabled_room_preserves_comment`：已注释房间（`# 超清,...`）切换画质成功、`#` 前缀原样保留、房间保持禁用态、列表可见新画质；
  - `test_quality_visible_in_room_list_after_change`：PUT 后 GET /api/rooms 立即返回新画质、相邻房间行不受影响；
  - `test_change_quality_matches_schemeless_url`：URL 归一化匹配（不带 scheme 的地址也能命中已规范化写入的配置行）；
  - `test_empty_string_quality_resets_to_default`：`quality: ""` 与 `null` 等价，均移除画质段恢复默认。
- `tests/frontend/test_quality_ui.mjs`（新文件，Node 内置 `node:test` + `node:vm` 沙箱，零 npm 依赖）：
  - 用 DOM/fetch 桩加载 app.js（IIFE 加载期零副作用）
  - 6 用例：沙箱冒烟 / 下拉渲染（选项构成 + 选中态 + URL 转义 + 行结构）/ change 委托请求契约 / 空值序列化为 null / 失败回拉恢复真值 / 四语文案行为级断言；
  - 变异验证：临时删掉 `buildRoomQualitySelect` 的 `esc(url)` 后断言正确变红，证明测试真能抓回归。
- `tests/test_frontend_quality_ui.py`（新文件）：pytest 包装，子进程 `node --test`，Node 缺失时 skip（环境限制口径）。


## v4.0.9.4-dev (2026-09-06) — WEB/GUI 端画质选项可增删 + 画质监控行内切换画质


### 改动清单

- `src/web_config.py`：
  - 引入 `BUILTIN_QUALITIES` 元组（与 `stream_select.get_quality_code` 的画质代码映射对齐），同时把历史别名 `QUALITY_KEYWORDS` 指向同一元组，避免两处并列维护；
  - 新增画质选项落盘位置常量 `QUALITY_OPTIONS_SECTION = "录制设置"` / `QUALITY_OPTIONS_KEY = "自定义画质选项(逗号分隔)"`；
  - `_split_multi_value` / `normalize_quality_options` / `read_quality_options` / `write_quality_options`：选项读写只允许内置档位（白名单外的名称会被静默回退成「原画」
  - `update_room_quality`：按 URL 定位 URL_config.ini 中的配置行…
  - `find_room_url_by_anchor_name`：按主播名反查直播间地址（GUI 画质切换写回 URL_config.ini 需要 URL），先精确匹配再子串兜底；未命中返回空串。
- `src/web_api.py`：
  - 新增 `GET /api/rooms/qualities`（返回 `{options, builtin}`，builtin 一并返回以便前端「添加画质」候选列表不必再硬编码档位名）；
  - 新增 `PUT /api/rooms/qualities` body `{options: [...]}`：写入前经 `validate_config_target` 走换行注入防护…
- `web/index.html`：直播间设置模块移除硬编码的画质 `<option>` 列表…
- `web/style.css`：新增 `.quality-options` / `.quality-panel` / `.quality-chips` / `.quality-chip` / `.quality-add-row` / `.quality-hint` 等样式…
- `web/app.js`：模块状态新增 `qualityOptions` / `qualityBuiltin`
- `gui.py`：
  - 导入追加 `parse_url_config` / `read_quality_options` / `update_room_quality`（`find_room_url_by_anchor_name` 备用）；
  - 新增实例字段 `_quality_options`（菜单可选项）/ `_quality_default_label = "默认画质"`（首项=回落）/ `_anchor_url_map`（主播名→URL 反查表…
  - 新增 `_refresh_quality_context`：读 `config.ini` 拿选项 + 解析 `URL_config.ini` 建反查表…
  - 新增 `_quality_menu_values`（菜单展示列表：默认画质 + 用户选项 + 当前画质兜底，防止画质被从选项中移除后菜单显示值错位到首项）；
  - 新增 `_on_room_quality_change`（用户切换触发：选「默认画质」= 移除画质段回落…
  - 画质监控详情表头行新增「切换画质」列；`_add_quality_data_row` 新增第 6 列 `CTkOptionMenu`（沿用 `appearance_menu` 的浅色/深色双主题色板）；列权重 2；
  - 画质页底部新增 wraplength 提示文案，说明「切换后下一轮循环生效」与「选择默认画质移除画质段」的语义。
- `tests/test_web_config.py`（新增 3 类）：`TestQualityOptions`（normalize 过滤非法/空/重复…
- `tests/test_web_api.py`（新增 `TestQualityOptionsEndpoints`）：GET 缺省返内置全集、PUT 持久化到 config.ini 且再次 GET 回读到同样列表、PUT 自动剔除白名单外的档位、PUT 换行注入 422。
- `README.md` / `README_EN.md`：本批改动在用户面上是「下拉从固定列表改为自选 + 监控行可切换画质」


## v4.0.9.4-dev (2026-09-05) — HLS 采集排除平台列表：命中平台无视 HLS 开关、恒走 FLV 采集


### 改动清单

- `main.py`：
  - 模块级新增全局 `hls_collection_exclude_platforms: list[str] = []`（紧邻 `hls_collection_enabled`），并加入 `main()` 的 `global` 声明；
  - `main()` 主循环在读取「是否启用HLS采集(是/否)」之后读取「录制设置 / HLS采集排除平台(逗号分隔)」（默认空）
- `src/stream_select.py`（`select_source_url`）：
  - 新增有效开关计算：`hls_excluded = platform in main.hls_collection_exclude_platforms`
  - 候选序列构建（`hls_seq`）由 `main.hls_collection_enabled` 改用 `hls_effective_enabled`：排除平台 HLS 候选**整组剔除、不进入序列**（与 `_FLV_FIRST_PLATFORMS` 仅调序、保留 HLS 回退的语义刻意不同）
  - 「HLS 源存在但 HLS 采集关闭且无回退」告警分支同样改用有效开关…
- `tests/test_stream_select.py`：新增 5 个用例——排除平台恒选 FLV（HLS 探针零发出）、FLV 校验失败不回退 HLS（HLS 从未被探测）、仅剩 HLS 源时告警返回 None（断言告警指向排除列表）、列表外平台行为不变（含 FLV-first 平台对照）、排除平台 h265-FLV 不切换 HLS。
- `README.md` / `README_EN.md`：配置示例新增「HLS采集排除平台(逗号分隔)」键及说明…
- `CODE_WIKI.md` / `CODE_WIKI_EN.md`：`[录制设置]` 配置表新增该键条目；`select_source_url()` 功能描述补充排除列表行为。


## v4.0.9.4-dev (2026-09-04) — P0 修复：分段录制容器错配导致抖音原画 HEVC 无法录制（返回码 4294967274）


### 改动清单

- `main.py`：新增模块级常量 `SEGMENT_FORMAT_BY_SUFFIX`（`.ts→mpegts` / `.flv→flv` / `.mkv→matroska` / `.mp4→mp4` / `.m4a→ipod`）
- `main.py`：新增 `_FFMPEG_ERRNO_HINTS` + `_describe_return_code()`
- `src/spider.py`：`extract_douyin_hevc_flv_url()` 返回前补 `&codec=h265`（已带 codec 参数时原样返回）。
- `tests/test_record_container.py`（新增 13 用例）：映射表内容断言、TS≠ipod / M4A≠mpegts 双向回归、AST 扫描断言「5 处取值全部来自查表、禁止裸字面量」、查表键已注册、音频兜底为 ipod、`hevc_flv_url` 补标记且 `_is_h265()` 可识别、退出码归一化。
- `AGENTS.md`：已知坑新增 2 条（分段容器映射 + `hevc_flv_url` 必须带 codec 标记）。

- 全量 `pytest -q`：**823 passed, 2 skipped，0 warnings**（修复前基线 808 passed）；
- `black --check`（123 文件）/ `isort --check-only` / `mypy`（3 个改动文件）/ `scripts/check_annotations.py`（平均密度 21.2%）全通过；
- 复现脚本已清理，未残留临时文件。

**同步与遗留**：

- 运行目录 `D:\DouyinLiveRecorder`（与开发仓 `D:\DouyinLiveRecorder-dev` 分离）已同步**最小修复**（`main.py` 两处容器取值 + `src/spider.py` 的 codec 标记）
- 已录历史 TS 文件需在修复后按魔数（首字节 `0x47`）复核，H.264 房间的历史产物可能为真 MP4。


## v4.0.9.4-dev (2026-09-04) — 修复 flaky 告警「FakeAsyncClient.aclose was never awaited」+ AGENTS.md pytest 0 警告门禁口径定稿


### 改动清单

- `src/async_http.py`：删除跨循环 `run_coroutine_threadsafe` 调度分支，改为不创建协程，注释完整记录三个不可行方案的实测结论（勿回退）。
- `tests/test_async_http_lock.py`：`test_concurrent_threads_no_cross_loop_error` 移除 `@pytest.mark.filterwarnings("ignore::RuntimeWarning")`（拦不住 GC 延迟触发的告警、只会掩盖回归…
- `pyproject.toml`：`[tool.pytest.ini_options].filterwarnings` 新增 starlette testclient import 期 `anyio.abc.BlockingPortal` 弃用提示的过滤（与既有 httpx 弃用提示同样定性：第三方、附来源注释）。
- `AGENTS.md`：新增「pytest『0 警告』口径」条目（summary 为空、项目自身告警与可过滤第三方告警的区分、禁止用过滤掩盖项目告警、协程类告警须修根因）

- `tests/test_async_http_lock.py` 连续重跑 30 + 20 轮：0 告警、0 `Task was destroyed`、无秒级阻塞（修复前 15 轮中 8 轮出现告警）；
- 全量 `pytest -q`：**808 passed, 2 skipped，0 warnings**（warnings summary 恒为 0，含新过滤的第三方告警）；
- `black --check` / `isort --check-only` / `mypy`（含 `--platform linux`）/ `basedpyright`（0 error/0 warning）/ `scripts/check_annotations.py` 全通过。


## v4.0.9.4-dev (2026-09-03) — 全仓中文注释补齐（41 文件 / +1370 行）+ 注释检查工具 scripts/check_annotations.py 建立并接入 CI


### 涉及文件（按模块分类）

- **核心源码**：`src/spider.py`（5.0% → 14.6%，四轮处理，新增 519 行注释）、`src/stream.py`、`src/ffmpeg_install.py`、`src/node_install.py`、`msg_push.py`
- **测试**：`tests/` 下 33 个文件（含 `test_spider_platform.py` 5.8% → 15.5%、`test_danmaku_monitor.py` 10.4% → 15.6%、`test_cookie_cache.py` 6.0% → 16.4% 等）
- **脚本**：`scripts/smoke_test.py`
- **前端**：`web/app.js`（补 IIFE 架构总览 / API 契约 / 轮询定时器清理 / esc() 转义要点）、`web/index.html`、`web/style.css`
- **新增**：`scripts/check_annotations.py`
- **CI / 文档**：`.github/workflows/ci.yml`（`static` job 新增步骤）、`AGENTS.md`（新增「注释约定」与「注释检查工具」两节）、`CODE_WIKI.md` / `CODE_WIKI_EN.md`（本条目）

**关键设计：AST 等价性校验**

本项目**非 git 仓库**（无 HEAD 作基准）

**改动说明**：

- **修复 CI 既有 YAML 隐患**：`static` job 中 `Check version consistency` 等步骤为 6 空格缩进…
- **子协作方越界改动的处置**：第四轮 `src/spider.py` 处理中…


## v4.0.9.3-dev (2026-09-02) — 单文件整合版 (standalone) 类型标注修复（mypy：4 处报错清零）


### 涉及文件（按模块分类）

**一、类型标注修复（修改内容）— `douyin_live_recorder_standalone.py`**

- L265 `_fetch_json`：返回值 `json.loads(resp.text)` 被 mypy 判为 `Any`（声明 `dict[str, Any]`）→ 改为 `cast(dict[str, Any], json.loads(resp.text))`。
- L751 `_douyu_sign`：返回值 `json.loads(out.stdout.strip())` 被判为 `Any`（声明 `dict[str, str] | None`）→ 先 `isinstance(sign, dict)` 守卫（非 dict 直接返回 `None`）
- L853 `dispatch`：`fn(url, proxy=proxy, cookies=cookies)` 关键字调用被 mypy 报「Unexpected keyword argument "proxy"/"cookies"」——根因为 `PLATFORM_RULES` 用 `Callable[[str, str | None, str], StreamInfo]`
- `typing` 导入：`from typing import Any, Callable` → `from typing import Any, Protocol, cast`（移除已无引用的 `Callable`）。


## v4.0.9.2-dev (2026-08-29) — 全量工作树改动总览（按模块分类）：97 文件 / +10659 −3138，覆盖 2026-08-23 ~ 08-29 全部未提交变更


### 涉及文件（按模块分类）

**一、并发调度与录制引擎核心（新增功能 + 修改内容）— `src/scheduler.py`（新增）/ `main.py` / `src/notify.py` / `src/recorder_status.py`**

- `src/scheduler.py`（**新增文件…
- `main.py`（+922/−796…
- `src/notify.py`（+39/−30）：`record_error`/`record_success` 增 `key` 形参并委托 scheduler（按 key 熔断 + 全局背压）
- `src/recorder_status.py`（+20/−2）：状态 JSON 增 `recording_enabled` 字段…
- **删除项**：旧 `adjust_max_request` 的 `threading.Semaphore` 重建逻辑、`check_subprocess` 轮末无条件 `record_success`、main.py 模块级 `threading.Semaphore(1)`。

**二、选源与流地址校验（修改内容）— `src/stream_select.py` / `src/stream.py`**

- `src/stream_select.py`（+260/−131）：① 统一候选序列——HLS/FLV/record_url 三类地址并入单一有序序列逐候选校验（虎牙经 `_FLV_FIRST_PLATFORMS` 反转为 FLV-first）
- `src/stream.py`（+202/−18）：蓝光细粒度档位专项——`QUALITY_MAPPING_BIT`/`QUALITY_LEVEL`/`QUALITY_CODE_TO_ZH` 扩为 10 项、新增 `BD_SUB_TIERS`/`HUYA_FIXED_TIERS`/`HUYA_RATIO_TO_CODE`/`DOUYU_RATE_BY_CODE`/`DOUYU_RATE_TO_CODE`/`DOUYU_RATE_DESC`、`get_quality_index` 子档位折叠到 BD、`get_huya_stream_url` 按 ratio 选档 + 就近降级、`get_douyu_stream_url` rate 重试链（最多回退 2 档）+ `rate` 字段回采真实档位。
- **删除项**：旧 `DOUYU video_quality_options`/`rate_to_code` 两表、旧「FLV 为 h265 → 立即重试整组 HLS」插入式回退、`sv=10010` 本地拼接（见三）。

**三、平台解析与 JS 签名（修改内容）— `src/spider.py` / `src/javascript/migu.js`（重写）/ `src/platforms/bilibili.py` / `src/platforms/douyu.py`**

- `src/javascript/migu.js`（+159/−74…
- `src/spider.py`（+18/−12）：`_BANDWIDTH_PATTERN`/`_DOUYIN_HEVC_FLV_PATTERN` 提为模块级预编译正则…
- `src/platforms/bilibili.py` / `src/platforms/douyu.py`：弹幕颜色解析 `except` 逗号化（PEP 758 机械重排）。

**四、HTTP 与网络层（修改内容）— `src/async_http.py` / `src/sync_http.py` / `src/http_config.py` / `src/ws_client.py` / `src/ttwid.py` / `src/collector.py`**

- `src/async_http.py`（+15/−2）：`close_all_clients_sync` 适配 Python 3.14——`asyncio.get_event_loop()` 无循环时捕获 `RuntimeError` 走引用清理兜底…
- `src/sync_http.py`（+21/−2）：`_session()` 经 `threading.local()` 线程级复用 `requests.Session`（约 125 处 `sync_req` 调用点全走此路径，实测单请求 11.9ms→1.47ms）。
- `src/http_config.py`（+14/−9）：FFmpeg 9.0 起 TLS 证书默认校验——「禁用SSL证书验证的平台」覆盖恢复实际作用…
- `src/ws_client.py` / `src/ttwid.py` / `src/collector.py`：PEP 758 格式化（弹幕 WS `proxy=None` 直连约定未变）。

**五、配置、日志与工具（修改内容）— `src/config_io.py` / `src/web_config.py` / `src/logger.py` / `src/ffmpeg_install.py` / `src/utils.py`**

- `src/config_io.py`（+17/−2）：`read_config_value` 缺省值写回改为「内存 `StringIO` 完整序列化成功后才落盘」
- `src/web_config.py`（+50/−6）：`update_config_line` 键匹配改大小写不敏感（`_key_line_pattern` 经 `lru_cache(128)` 预编译）
- `src/logger.py`（+35/−3）：`sys.stderr is None` 判空守卫（pythonw/`console=False` 冻结 exe 导入期静默崩溃根治）
- `src/ffmpeg_install.py`（+8/−8）：蓝奏云 FFmpeg 下载源域名切换 `wweb.lanzouv.com` → `wwasx.lanzout.com`（Origin/Referer/接口与提取密码同步）。
- `src/utils.py`（+23/−18）：`_EMOJI_PATTERN` 提为模块级预编译（`remove_emojis` 每调用省去约 400 字符模式重编译）。

**六、Web 面板（新增功能 + 修改内容）— `src/web_api.py` / `web.py` / `web/index.html` / `web/app.js` / `web/style.css`**

- `src/web_api.py`（+49）：新增 `POST /api/recording/toggle`（录制全局开关切换）与 `GET/PUT /api/language`（语言查询/热切换：归一化校验 → `update_config_line` 写回、失败降级 `append_config_line` 补建 → `set_language` 热切换）
- `web.py`（+15/−2）：引擎线程启动前置 `main.recording_enabled = False`（Web 默认不自动录制）
- `web/index.html`（+54/−41）：新增「录制控制」区（状态双子 span + 开始/停止按钮）与顶栏语言选择器…
- `web/app.js`（+323/−45）：新增前端 i18n 字典 `I18N`（约 230 行…
- `web/style.css`（+41/−1）：录制控制区样式（主色开始/红色停止/禁用态）。

**七、GUI（新增功能 + 修改内容）— `gui.py`（+173/−7）**

- 崩溃可观测：新增 `_install_crash_sink()`（`sys.excepthook` + `threading.excepthook` 落盘到临时目录并尽力弹窗…
- 语言菜单：侧边栏新增「语言 Language」`CTkOptionMenu`
- UI 回调异常由 `traceback.print_exc()`（`sys.stderr is None` 时二次崩溃）改为程序内日志。

**八、i18n 本地化体系（新增功能 + 修改内容）— `i18n.py`（重写）/ `i18n/en_US.json`（新增）/ `i18n/en_GB.json`（新增）/ `i18n/zh_TW.yaml`（新增）/ `i18n/zh_CN.po|.mo` / `scripts/extract_i18n_strings.py`（新增）/ `scripts/compile_po.py`**

- `i18n.py`（+270/−31）：重写为多格式引擎——按语言依次探测 gettext `.mo` → `<lang>.json` → `<lang>.yaml`
- 翻译目录：新增 `i18n/en_US.json`、`i18n/en_GB.json`（美式/英式拼写分流）、`i18n/zh_TW.yaml`
- 新增 `scripts/extract_i18n_strings.py`（166 行）：AST 扫描 print 常量串 + logger f-string 模板底稿…
- `scripts/compile_po.py`：纯 Python po→mo 编译修正（此前自身语法错误致 `.mo` 从未落盘）；`scripts/check_coverage.py` 微调。

**九、构建 / CI / 依赖 / 仓库元数据（修改内容 + 新增）— `pyproject.toml` / `requirements.txt` / `uv.lock` / `Dockerfile` / `docker-compose.yaml` / `build_exe.py` / `.github/*` / `.coveragerc-concurrency`（新增）/ `.dockerignore` / `.gitignore`**

- `pyproject.toml`：版本 `4.0.8.3` → `4.0.9.2`
- `requirements.txt`：新增 `PyYAML>=6.0.3`（与 pyproject 下界一致）；弹幕依赖注释路径订正（`src/danmaku/` → `src/` 实际布局）。
- `uv.lock`：随 3.14 基线重锁（净 −963 行…
- `Dockerfile`：基础镜像 `python:3.13-slim` → `python:3.14-slim`；Node.js `setup_22.x` → `setup_24.x`（24 LTS，实测全部 JS 签名脚本 + migu.js 重写版通过）。
- `docker-compose.yaml`：版本示例注释同步 4.0.9.2。
- `build_exe.py`：PEP 758 格式化（打包冒烟判定语义未变）。
- `.github/workflows/ci.yml`：重构为 setup + static/typecheck/test/concurrency-test/integration-verify/build-verify/ci-summary 拓扑（每 job 显式 timeout、ci-summary 唯一 required check）
- `.github/workflows/build-release.yml`：`python_build` 3.12→3.14…
- 新增 `.github/actions/retry/action.yml`（线性退避 ×3 复合动作…
- 新增 `.coveragerc-concurrency`（并发测试专用覆盖率配置…
- **删除项**：两 workflow 内 13 处内联 `for i in 1 2 3` 重试循环、build-release.yml 调试步骤。

**十、测试（新增 4 文件 + 修改 30 文件）— `tests/`**

- 新增：`tests/test_scheduler.py`（192 行…
- 修改（代表）：`tests/test_stream_select.py`（+215：统一候选序列/末位放行/退避跨轮命中/非白名单无操作）、`tests/test_i18n.py`（+234：四目录一致性/平台门控/C-POSIX 过滤/monkeypatch 规约化）、`tests/test_config_io_readonly.py`（+134：StringIO 预序列化/坏键回滚）、`tests/test_web_api.py`（+133：语言端点/录制开关端点）、`tests/test_spider_platform.py`、`tests/test_main_fixes.py`、`tests/test_concurrency.py`（锁类型断言同步）等。
- 全套件当前状态：`pytest` **786 passed, 2 skipped**（`tests/test_twitch_live_collector.py` 因沙箱回收站护栏需隔离运行，属环境限制非回归）。

**十一、文档与审查产物（新增 + 修改）— `AGENTS.md` / `README.md` / `CODE_WIKI.md` / `CODE_WIKI_EN.md`（新增）/ `README_EN.md`（新增）/ `PERF_REVIEW_2026-08-28.md`（未跟踪）**

- `AGENTS.md`（+270）：沉淀「并发与线程模型」（调度中枢/录制结果反馈/锁约定）与「已知坑」十余条防回归约定（弹幕 `proxy=None`、探针容错语义、虎牙退避与 FLV-first、UA 双端一致、PEP 758、3.14 破坏性变更、i18n 多格式、configparser 分隔符等）。
- `README.md`（+303）：3.14 基线、i18n、Web 录制控制等用户文档更新；新增 `README_EN.md` 英文版、`CODE_WIKI_EN.md` 英文架构文档（与本文档结构镜像）。
- `CODE_WIKI.md` / `CODE_WIKI_EN.md`：更新日志自 2026-08-23 起新增十余条分功能条目 + 本总览条目（中英同步）。
- `PERF_REVIEW_2026-08-28.md`（未跟踪…
- 勘误：早前「Web 面板录制手动控制」条目提及的 `docs/web-recording-control-changelog.md` 与 `docs/security-triage-2026-08-29.md` 未保留在当前工作树中…

**改动说明**：

- **改动类型的完整口径**：新增功能（scheduler、Web 录制控制、画质细档位、i18n 体系、GUI 崩溃兜底/语言菜单、retry 复合动作、社区模板、三份英文/双语文档、4 个新测试文件）
- **三条主线互相独立又彼此衔接**：并发调度（谁允许发起网络请求）→ 录制反馈（结果回灌熔断统计）→ 探针退避（坏线路短期拉黑）
- **Python 3.14 迁移贯穿全部模块**：`asyncio.get_event_loop` RuntimeError 兜底、`configparser.InvalidWriteError` 预序列化防御、PEP 758 全仓格式化（black py314 强制风格…
- 本总览与分条目互补：分条目讲「为什么、怎么做」，本条目讲「改了哪些文件、归在哪个模块」；文件行号以分条目记载为准（本条目不重复）。


## v4.0.9.2-dev (2026-08-29) — 虎牙/斗鱼画质档位专项（细粒度蓝光档位枚举 + 用户选档录制 + 不可用降级回退 + 全平台兼容）


### 涉及文件（按模块分类）

**一、画质代码与档位表（新增功能 — 枚举/标识/降级判定）— `src/stream.py`**

- 模块顶部新增 `from loguru import logger`（选档降级日志用）。
- `QUALITY_MAPPING_BIT`（L203）：在基础 6 项上追加 `BD30:30000`/`BD20:20000`/`BD8:8000`/`BD4:4000`（码率上限 kbps）。
- `QUALITY_LEVEL`（L214）：扩展为 `OD/BD(0) > BD30(1) > BD20(2) > BD8(3) > BD4(4) > UHD(5) > HD(6) > SD(7) > LD(8)`，数值越大画质越低，供 `is_downgrade` 判定降级方向。
- `QUALITY_CODE_TO_ZH`（L222）：追加 `BD30→蓝光30M`/`BD20→蓝光20M`/`BD8→蓝光8M`/`BD4→蓝光4M`。
- `BD_SUB_TIERS`（L232）：`frozenset({"BD30","BD20","BD8","BD4"})`，蓝光子档位集合（不参与通用索引映射）。
- 注释块补实测数据（L236-247）：虎牙 chuhe 房间 `bitRate=30000` 下各 ratio 实测分辨率/帧率（原画 2560×1440@60fps、蓝光30M/20M/8M 均 1920×1080@60fps、蓝光4M 1920×1080@30fps、超清 1280×720@30fps、流畅 800×450@24fps）。
- `HUYA_FIXED_TIERS`（L248）：`(("BD30",30000),("BD20",20000),("BD8",8000),("BD4",4000))`；`HUYA_RATIO_TO_CODE`（L250）：ratio 字符串→代码回采表。
- 斗鱼档位表（L268-293）：`DOUYU_RATE_BY_CODE`（请求代码→rate…
- `get_quality_index`（L335）：蓝光子档位折叠到 `BD` 槽位（`if quality_str in BD_SUB_TIERS: quality_str = "BD"`）

**二、虎牙选档实现（修改内容 — 细粒度档位 + 就近降级）— `src/stream.py::get_huya_stream_url`**

- 解析 `gameLiveInfo.bitRate` 为 `max_ratio`（含 `except TypeError, ValueError` 容错——py314 PEP 758 合法形式）
- 请求档在 `BD_SUB_TIERS` 时（L~627）：取 `HUYA_FIXED_TIERS` 固定 `target_ratio`

**三、斗鱼选档实现（修改内容 — rate 映射 + 被限制降级重试链）— `src/stream.py::get_douyu_stream_url`**

- 原 `video_quality_options`/`rate_to_code` 两表删除…
- 降级链（L~765）：按 `order = ["0", *DOUYU_RATE_DESC]` 全序…
- `actual_quality` 改经 `DOUYU_RATE_TO_CODE.get(actual_rate, ...)` 回采服务端真实下发档（`rate` 字段反映就近钳制，如 8200→4→BD4）。

**四、中文名映射与配置/接入白名单（修改内容）**

- `src/stream_select.py::get_quality_code`（L57）：`quality_zh_to_en` 扩展为 10 项，新增 `蓝光30M/20M/8M/4M → BD30/BD20/BD8/BD4`；未知画质仍回退 `OD`。
- `src/web_config.py::QUALITY_KEYWORDS`（L21）：元组由 6 项扩展为 10 项（含蓝光细档位），与 main.py 白名单对齐。
- `main.py`（L2955）：单条 URL 配置解析的画质白名单由 6 项扩展为 10 项，非法值回退「原画」（其余解析逻辑不变）。

**五、Web 面板下拉选项（修改内容）— `web/index.html`**

- `room-quality` 下拉新增 `蓝光30M`/`蓝光20M`/`蓝光8M`/`蓝光4M` 四个 `<option>`（紧邻「蓝光」之后）

**六、测试（新增 + 修改）**

- `tests/test_quality_tiers.py`（**新增文件…
- `tests/test_stream.py`：`test_quality_mapping_keys_match_level_keys`/`test_quality_mapping_keys_match_bit_keys`/`test_quality_code_to_zh_keys_match_mapping_keys` 由「集合相等」改为「基础集 ⊆ 扩展集 且 `BD_SUB_TIERS` == 扩展集 − 基础集」

**改动说明**：

- **蓝光子档位不污染通用索引**：抖音/TikTok 等按数字 0–5 选档平台仍只识别 OD/BD/UHD/HD/SD/LD…
- **虎牙 ratio 即码率上限**：实测确认 ratio 拼于 FLV/HLS URL query 选档、各 CDN 线路共享同一防盗链参数、流地址路径不变（与历史 `sFlvAntiCode` 解析行为一致）。
- **斗鱼服务端自带就近钳制是主降级路径、本地重试链是补充**：斗鱼请求不存在的档位多数被服务端静默钳制到更低档（`rate` 字段回采）
- **降级语义对齐 `QUALITY_LEVEL`**：`is_downgrade(actual, requested)` 按等级数值方向判定（如 `BD8`(3) > `BD4`(4) 为真降级）


## v4.0.9.2-dev (2026-08-29) — Web 面板录制手动控制（全局开关 + 7 处中断点 + 开始/停止按钮）+ 双轮审查修复 + 端到端冒烟与提交门禁分诊


### 涉及文件（按模块分类）

**一、录制主链全局开关 — `main.py`**

- 新增模块级 `recording_enabled: bool = True`（L210）

**二、运行列表清理 — `src/notify.py`**

- 新增 `remove_room_from_running(record_url)`（L153）：线程退出时从 `running_list` 幂等移除（成员检查前置、仅在真正移除时递减 `monitoring`、与 `clear_record_info` 共用 `record_state_lock`）

**三、Web API 与状态暴露 — `src/web_api.py` + `src/recorder_status.py`**

- `web_api.py` 新增 `POST /api/recording/toggle`（L249-258）：请求体 `{"enable": bool}`
- `recorder_status.py` 状态 JSON 追加 `"recording_enabled": main.recording_enabled`（L109）：前端页面刷新/重连后经 2s 轮询恢复按钮真实态（与 `engine_alive` 正交）。

**四、Web 面板入口 — `web.py`**

- 引擎线程启动**前**置 `main.recording_enabled = False`（L188-189…

**五、前端 — `web/index.html` + `web/app.js` + `web/style.css`**

- `index.html`（L39-46）新增「录制控制」区：状态指示（`录制运行中`/`录制已停止` 双子 span + `hidden` 切换）+ 开始/停止按钮…
- `app.js` 新增 `renderRecordingControl`（按钮互斥启用/禁用、`engine_alive` 联动、状态标签切换）与 `toggleRecording`（POST toggle → 成功 toast → 状态回拉独立 try/catch…
- `style.css`（L248-275）新增控制区样式：主色开始按钮/红色停止按钮/禁用态（透明度 + 禁用鼠标事件），与既有卡片风格一致。

**六、测试（新增 + 修改）**

- `tests/test_web_api.py`：新增 `TestRecordingToggle`（2 例——无认证 401、开关翻转写入真实模块属性）。
- `tests/test_record_failure_feedback.py`（**新增文件**）：`test_check_subprocess_interrupts_when_recording_disabled` 验证 `recording_enabled=False` 时 ffmpeg 轮询循环中断、优雅终止恰好调用一次、不记任何成功/失败样本…

**七、文档（新增）**

- `docs/web-recording-control-changelog.md`（**新增**）：特性改动汇总——需求背景、设计方案（全局开关 + 多入口中断）、关键设计决策（含「停止语义为主动分级优雅终止」的表述更正）、集成点、测试验证、已知限制、后续计划 5 项闭环（提交/审查/冒烟/持久化评估/单房间开关决策）。
- `docs/security-triage-2026-08-29.md`（**新增**）：Mimosa L3 提交门禁 44 条告警逐条分诊——SSRF（硬编码官方下载源）/路径穿越（固定常量路径 + `clean_name` 既有净化防线 `main.rstr` 含 `/ \ : .`）/命令注入（PyExecJS 内普通 JS 运算）/硬编码凭据（平台公开客户端 token）/弱随机数（非加密抖动）
- `CODE_WIKI.md` / `CODE_WIKI_EN.md`：更新日志新增本条目（中英同步）。

**改动说明**：

- **停止语义是主动分级优雅终止…
- **错误统计隔离是熔断体系的前提**：停止期间的中断不计 `record_error` 样本…
- **`recording_enabled` 不持久化（后续计划条目 4 评估结论）**：持久化 `True` 会使面板重启后自动恢复录制…
- **单房间开关维持延后（条目 5）**：与已知限制 #1 决策一致——Web 场景「全部录制/全部停止」为最常见需求…
- **7 处中断点均为提前返回模式**：不改变正常流程路径…


## v4.0.9.2-dev (2026-08-28) — 性能审查优化落地（P1~P5 + 探针客户端复用 + 退避窗口自愈 + Web 日志 sink 重建 + 虎牙 FLV-first）


### 涉及文件（按模块分类）

**一、流地址探针与选源（性能 P1 + 修复一/四）— `src/stream_select.py`**

- **P1 探针客户端复用**：`select_source_url` 整轮候选共用一支 `httpx.Client`（`finally` 关闭…
- **修复一 退避窗口对齐主循环**：新增 `_PROBE_BACKOFF_INTERVAL_MARGIN = 70.0`
- **修复四 虎牙 FLV-first**：新增 `_FLV_FIRST_PLATFORMS = ("虎牙直播",)`（**斗鱼绝不加入**…

**二、录制主链（修复二）— `main.py`**

- `check_subprocess` 成功分支（解析 `ffmpeg_command` 的 `-i` 后地址）调用 `clear_ffmpeg_reject(...)`

**三、并发调度（性能 P4）— `src/scheduler.py`**

- `import time` 提至模块顶层（`_now` / `_sleep` 不再函数内 import）

**四、同步 HTTP（性能 P2）— `src/sync_http.py`**

- 新增 `_thread_local = threading.local()` 与 `_session()`（线程局部复用 `requests.Session`

**五、工具 / 解析 / 配置（性能 P5）**

- `src/utils.py`：`remove_emojis` 的 ~400 字符表情模式提为模块级常量 `_EMOJI_PATTERN`（每次调用不再重复 `re.compile`）。
- `src/stream_select.py`：`contains_url` 模式提为模块级常量 `_URL_PATTERN`。
- `src/spider.py`：新增 `_BANDWIDTH_PATTERN` / `_DOUYIN_HEVC_FLV_PATTERN`，替换 4 处函数内 `re.compile`（`spider.py:178/202/1844/1918`）。
- `src/web_config.py`：`update_config_line` 的「按 key 编译正则」改 `functools.lru_cache(maxsize=128)`（`web_config.py:228`）。

**六、主循环去重（性能 P3）— `main.py`**

- `url_comments` / `line_list` / `url_line_list` 由 list 改 `set`

**七、日志（修复三）— `src/logger.py` + `web.py`**

- `src/logger.py`：新增模块级 `_console_sink_id` 捕获 `logger.add` 返回值（第 36/58 行）
- `web.py`：`_enter_background_mode`（`web.py:103`）在把 `sys.stdout/stderr` 重定向到 `logs/web_console.log` 并 `SW_HIDE` 隐藏控制台窗口**之后**…

**八、测试（新增 + 修改）**

- `tests/test_stream_select.py`：3 处客户端替身的 `head` / `stream` 补 `headers` 形参…
- `tests/test_sync_http.py`：4 个代理用例 patch 目标由 `src.sync_http.requests` 改为 `src.sync_http._session`。
- `tests/test_logger_console_sink.py`（**新增**，3 例）：跟随当前 stderr / 替换而非追加 / `None` 时静默（断言前须 `logger.complete()` 排空 `enqueue=True` 异步队列）。

**九、文档（本条目）**

- `CODE_WIKI.md` / `CODE_WIKI_EN.md`：更新日志新增本条目（中英同步）。
- `PERF_REVIEW_2026-08-28.md`（**新增**）：性能审查报告（瓶颈清单 P1~P7、本地基准实测、三轮真机验证结论、三处误判口径校正）。
- `AGENTS.md`：补 6 条防回归约定（探针客户端复用作用域 = 单次选源、禁止为保险关 keepalive、退避窗口须 ≥ 主循环周期、录制成功清除退避、Web 后台重建 sink、虎牙 FLV-first 且斗鱼不加入）。

**改动说明**：

- **P1 真实提速约 5.5× 而非 36×**：原实现 `with httpx.Client(...)` 内 HEAD 与 Range-GET 已复用同一条连接（每候选 1 条…
- **「headers 未透传」不是缺陷**：httpx `_merge_headers` 是「合并」非「替换」
- **退避窗口失配是真因**：固定 60s < 120s 循环间隔…
- **并发连接峰值实测恒为 1**：候选串行校验…
- **虎牙 FLV-first 收益**：三轮真机（880214 / chuhe 等）实证 HLS 三条 CDN（hs/tx/al）冷启动探针假绿（探针 200/206、ffmpeg 打开即 403…


## v4.0.9.1-dev (2026-08-28) — CI 工作流优化与网络安装重试收敛（retry 复合动作）+ PEP 758 格式化随 black 26 落地 + i18n 提取器修正 + 仓库元数据八文件同步


### 涉及文件（按模块分类）

**一、CI / GitHub Actions（新增功能 + 修改内容）**

- `.github/actions/retry/action.yml`（**新增**）：复合动作 `retry`——网络安装命令统一重试包装。
- `.github/workflows/ci.yml`（重写，job 结构与门禁语义不变）：
  - `actions/checkout` v5→v7、`actions/setup-python` v6→v7（经 WebSearch 确认 v7 均为当前最新大版本，与 build-release.yml 对齐，消除两份工作流 action 版本漂移）；
  - 9 处内联重试脚本（pip ×5 / apt ×3 / build-verify 依赖 ×1，各约 12 行）替换为 retry 复合动作调用（apt 退避保持原 10s）；
  - apt 安装对齐 build-release.yml 强化参数：`DEBIAN_FRONTEND=noninteractive`（防交互卡死）+ `Acquire::Retries=3`（apt 自身网络重试）+ `--no-install-recommends`（更快更省盘）；
  - 头注释补 job 拓扑图（setup 六路并行 → ci-summary 汇总）与「本工作流止于验证、不含部署」职责边界…
- `.github/workflows/build-release.yml`：4 处内联重试脚本（choco / apt / brew / pip）替换为 retry 复合动作（退避值与原脚本逐一一致：系统包管理器 15s、pip 10s）

**二、国际化模块（修改内容——格式 + 维护工具）**

- `i18n.py` + `scripts/compile_po.py`：同日早前条目把 4 处 `except` 改为元组括号后…
- `scripts/extract_i18n_strings.py`（**两处缺陷修正，本条目首次录入目录树与 §8 维护流程**）：
  - `is_valuable()` 重构：旧逻辑剥花括号后查字母…
  - `load_catalog_keys()`：po 头部空 `msgid ""` 剔除后再比对——JSON/YAML 目录设计上不含它（运行时加载亦会 pop）
  - 修正后重跑：运行时有价值串 318 条全部在库、缺失 0、四语目录键集一致（各 496 条）——确认今晨全量补全后源码未引入新可翻译串（此后仅改过 except 语法与 workflow YAML）。

**三、仓库元数据八文件同步（修改内容）**

- `requirements.txt` / `Dockerfile`：注释中 4 处引用**不存在的 `src/danmaku/` 路径**修正为实际位置（`src/ws_client.py` / `src/proto/douyin_pb2.py` / `src/platforms/bilibili.py` / collector 工厂链）——弹幕模块实际分布在 src/ 根、platforms/、proto/…
- `.dockerignore`：补 16 个排除项——`.mimosa/` 与 7 个本地工具目录（`.qoder/`、`.agents/`、`.pnpm-store/`、`.dsh-validation/`、`.ego-browser-test/`、`.plugin-src/`、`.tmp-dps-extract/`、`pytest-cache-files-*/`
- `.gitignore`：补 `.mimosa/`（此前 pyproject 的 black/isort/mypy/coverage 四处均排除它，git status 却持续显示 `?? .mimosa/` 未跟踪）与 `pytest-cache-files-*/` 防御条目。
- `pyproject.toml`：basedpyright exclude 清理 2 个已删除的死目录（`pytest-cache-files-g1bpkgza` / `pytest-cache-files-wt8ppn27`）
- `docker-compose.yaml`：`.env` 示例版本号 `4.0.8.3` → `4.0.9.1`（对齐 pyproject 当前版本）。
- `AGENTS.md`：模块计数 39 → 41（实测 src 根 31 + platforms 8 + proto 2）
- `.coveragerc-concurrency`：逐项核对与 pyproject `[tool.coverage.*]` 完全一致（source / omit / exclude_lines 同值…

**四、文档（本条目）**

- `CODE_WIKI.md` / `CODE_WIKI_EN.md`：目录树补 `.github/actions/retry/`、`scripts/extract_i18n_strings.py`、`scripts/check_coverage.py`、`uv.lock`（并清理 `.coveragerc-concurrency` 重复条目）

**改动说明**：

- **PEP 758 往返的澄清**：同日早前条目把 4 处 `except` 改为元组括号（当时判定「对 ≥3.13 最稳妥」）
- **重试收敛的动机**：两份 workflow 原共 13 处几乎相同的 12 行内联重试循环…
- **macOS brew 步骤拆分**：`brew trust aws/tap` 幂等且带 `|| true` 兜底…
- **.mimosa/ 的三层同步**：pyproject 四处排除均含它、.gitignore 却未忽略…
- **镜像排除 scripts/ 的依据**：grep 验证根目录全部入口脚本与 `src/**` 对 `scripts/` 零引用…


## v4.0.9.1-dev (2026-08-27) — i18n 本地化系统修复（Python 2 风格 `except` 多异常 → 元组括号）+ zh_CN.mo 重编译


### 涉及文件（按模块分类）

**一、国际化模块（修改内容）**

- `i18n.py`：三处 `except` 多异常逗号写法改为元组括号（行为不变）：
  - `i18n.py:202` `except OSError, ValueError:` → `except (OSError, ValueError):`；
  - `i18n.py:218` `except OSError, ValueError, yaml.YAMLError:` → `except (OSError, ValueError, yaml.YAMLError):`（三异常逗号写法在任意 Python 版本均非法，是真正的致命点）；
  - `i18n.py:320` `except ValueError, AttributeError:` → `except (ValueError, AttributeError):`。
  - 修复后 `py_compile` 通过、`import i18n` 正常（`_load_translations(locale_path, 'zh_CN')` 可加载 496 条）。
- `scripts/compile_po.py`：`scripts/compile_po.py:128` `except AttributeError, OSError:` → `except (AttributeError, OSError):`。修复后编译脚本可正常执行。

**二、构建产物（重新生成）**

- `i18n/zh_CN/LC_MESSAGES/zh_CN.mo`：语法修复后执行 `python scripts/compile_po.py` 重新生成（与当前 `zh_CN.po` 对齐，496 条含 gettext 头，`--check` 字节级同步）。

**改动说明**：

- **为何是阻断性缺陷**：首轮「全量补全」的 `zh_CN.mo` 实际从未成功落盘（编译脚本自身无法被 Python 解析）。
- **对首轮「PEP 758 合法 / 未改动」评估的订正**：同日二轮复查条目声称「全仓 16 处 `except A, B:` 在 3.14 下合法、未改动」。
- **§8 翻译文件表条目数**：同步由 492 更新为 496（对齐当前 `.po`/`.mo` 实际 496 条）。


## v4.0.9.1-dev (2026-08-27) — 二轮复查修复（compile_po --check 恒真 + 直下失败采样缺口 + i18n/Web 缺口补全）


### 涉及文件（按模块分类）

**一、构建 / CI / 社区模板（修改内容 + 删除项）**

- `scripts/compile_po.py`：
  - **`write_mo()` 改为纯内存产出**（去除 `path.write_bytes()` 写盘副作用与 `path` 参数）：原先 `main()` 在 `--check` 分支之前无条件调用 `write_mo(entries, MO_PATH)` 把新编译结果写盘覆盖 `.mo`
  - **落盘决策上移至调用方**：非 check 模式在打印成功消息前显式 `MO_PATH.write_bytes(fresh)`；`--check` 模式全程不触碰磁盘，真实比对已提交的 `.mo`；
  - 头部用法注释补「零副作用不写盘」语义说明。
- `.github/workflows/ci.yml`：paths-filter 的 `python` 过滤器新增 `- 'i18n/**'` 并同步修正注释——此前 static job（含 compile_po --check）不随纯翻译变更触发…
- `.github/workflows/build-release.yml`：删除 release job 末尾残留的无用步骤 "Debug inputs"（tag 路径下仅产生无意义输出）。
- `.github/ISSUE_TEMPLATE/bug.yml` / `bug_en.yml` / `question.yml` / `question_en.yml`：Python 版本下拉补 `- Python 3.14` 选项（项目要求 ≥3.14…

**二、录制主链（修改内容）**

- `main.py`：
  - **直下路径失败样本补报**（`start_record` 直下分支）：`if download_success:` 记成功样本之后新增 `elif record_url not in url_comments and not exit_recording: record_error(record_host)`——`direct_download_stream` 的「非 200」（CDN 拒绝…
  - **弹幕参数每轮重置恢复**：内层监测循环顶部（`exit_recording` 检查前）补 `record_danmaku_args = None`（AGENTS.md「每轮重置为 None」约定…
  - **两处日志规范化**：`direct_download_stream` 非 200 分支补请求 URL 上下文、异常分支补 `{type(e).__name__}`（Windows 下超时类异常 `str()` 为空串，裸打无线索）。
- `src/async_http.py`（存量清理）：`_close_all_clients()` 与 `async_req()` 主异常分支的两处裸 `logger.debug(e)` 规范为 `f"<动作>: {url} - {type(e).__name__}: {e}"` 格式（对齐同文件 `get_response_status` 已有范例…

**三、Web 配置与 API（新增功能 + 修改内容）**

- `src/web_config.py`：新增 `append_config_line(config_file, section, key, value)`——缺键补建的行级追加（`update_config_line` 只做替换、键或节缺失时返回 False）。
- `src/web_api.py`：`PUT /api/language` 写回降级链路——行级替换失败（历史 config.ini 无 `language` 键、Web 先于引擎首轮读配置启动的窗口）时调用 `append_config_line` 节末追加补建…

**四、Web 前端（修改内容）**

- `web/app.js`：约十处硬编码中文字符串改走内嵌四语字典 `t()`（与文件其余部分风格一致地包 `esc()`）——录制表空态 `empty.noRecording`、弹幕流空态 `danmaku.noData`、截断提示 `danmaku.truncated`、开关 toast `toast.enabled/disabled`、操作失败 `toast.opFailed`、配置页空态 `config.none` 与加载失败 `loadFailed`、文件列表空态 `files.emptyDir` 与进入/下载按钮 `rooms.enter/rooms.download`、下载失败 `toast.downloadFailed`。

**五、测试（新增功能 + 修改内容）**

- `tests/test_record_failure_feedback.py`：新增 `_FakeStreamResponse` / `_FakeHttpClient` httpx 流式替身（`__exit__` 返回类型标注 `None` 规避 mypy `exit-return`）
- `tests/test_web_api.py`：新增 `test_put_language_missing_key_appends_and_succeeds`（配置无 `[录制设置]`/`language` 键时 PUT 不再 500 且补建正确、不影响已有 `[Web]` 节）、`test_append_config_line_edge_cases`（目标节存在且夹注释 / 目标节为最后一节且文件无尾换行 / 节缺失三种形态）
- `tests/test_i18n.py`：`test_po_and_mo_in_sync` 适配 `write_mo()` 新签名（去 path 参数，取返回值直接比对），移除随之冗余的 `tempfile` 导入。

**六、文档（修改内容）**

- `CODE_WIKI.md` / `CODE_WIKI_EN.md`（本条目）：目录树 tests 注释更新（test_record_failure_feedback 7 用例、compile_po 零副作用）

**改动说明**：

- **为何 --check 必须零副作用**：校验逻辑的本质是「工作区产物 ↔ 已提交工件」的一致性检查…
- **直下路径样本分支的条件设计**：`record_url not in url_comments and not exit_recording` 用于区分「真失败」与「人为中断」——中断轮线程即将退出、不应向熔断器注入噪声样本…
- **PEP 758 澄清**（对未来评审重要）：Python 3.14 起 `except A, B:` 与 `except (A, B):` 完全等价（PEP 758 允许省略异常元组括号）
- **append_config_line 的边界处理**：经新增边界用例发现并修复一处初版缺陷——源文件末行无换行符时…


## v4.0.9.1-dev (2026-08-27) — 代码审查修复（熔断探针租约自愈 + 调度成功采样）+ 调度器线程安全加固 + i18n 四目录全量补全（288 → 492 条）


### 涉及文件（按模块分类）

**一、并发调度模块（新增功能 + 修改内容）**

- `src/scheduler.py`：
  - **新增探针租约**（修复高危缺陷）：模块常量 `_PROBE_LEASE_SECONDS = 60.0`
  - **配置字段加锁**（线程安全加固）：`_compute_capacity()` 改为单次加锁快照全部可变输入（模式/配置/活跃数/错误窗口…
  - **`host_of()` 注释修正**：原注释称「去端口/自定义直链退回路径本身」与实现不符（实现保留端口、仅返回 host、坏 URL 统一归 `"unknown"` 共享熔断 key）
- `main.py`：`start_record` 解析成功分支（`port_info["anchor_name"]` 非空）新增 `record_success(record_host)`——与解析失败分支的 `record_error` 对称。
- `src/notify.py`：
  - `record_error` / `record_success` 中三参 `getattr(main, "scheduler", None)` 改为直接访问 `main.scheduler`（AGENTS.md 禁令：三参 getattr 返回 `Any`
  - `run_script` 三处裸 `logger.error(e)` 补齐「动作 + 对象 + 异常类型」（`PermissionError`/`OSError`/`ValueError` 分支均带 `command` 与 `type(e).__name__`）。

**二、国际化模块（修改内容）**

- `i18n.py`：`_load_yaml_catalog()` 的 `except` 补 `yaml.YAMLError`（ParserError/ScannerError 非 OSError/ValueError 子类…
- `i18n/zh_CN/LC_MESSAGES/zh_CN.po`：新增 204 条（288 → 492）
- `i18n/en_US.json` / `i18n/en_GB.json` / `i18n/zh_TW.yaml`：同步追加 204 条（各 288 → 492）

**三、GUI 模块（修改内容）**

- `gui.py`：新增 `_bootstrap_crash_reported` 模块级标记——`_bootstrap_error_sink` 处理 `main()` 顶层异常并置位后…

**四、测试（新增功能）**

- `tests/test_scheduler.py`：新增 `test_platform_breaker_probe_lease_regrants_after_timeout`（探针租约超时重授予 → 新探针成功上报 → closed 的自愈全链路）
- `tests/test_i18n.py`：新增 `test_load_yaml_catalog_corrupted_returns_none`（损坏 YAML 返回 None 降级，不抛异常）。

**五、文档（修改内容）**

- `AGENTS.md`：版本号 4.0.8.3 → 4.0.9.1（对齐 `pyproject.toml` 唯一事实源）
- `CODE_WIKI.md` / `CODE_WIKI_EN.md`（本条目）：第 8 节翻译文件表条目数 282 → 492、覆盖范围更新…

**改动说明**：

- **探针租约与成功采样的关系**：两者互补——解析成功采样让「探针轮正常流转」的场景即时闭环（探针房间未开播时每轮 `record_success` 使熔断器恢复 closed）
- **加锁对行为的零影响**：锁内快照/写入与锁释放后 `recompute()` 的顺序保证无嵌套持锁（`Lock` 不可重入）
- **i18n 补全方法论**：以 AST 静态提取（`print()` 全部常量参数 + `logger.debug/info/warning/error/...` 首参常量与 f-string 模板还原）为权威基线…


## v4.0.9-dev (2026-08-24) — CI pytest 失败修复：C/POSIX 语言环境检测与 monkeypatch 规约


### 涉及文件

- 修改 `i18n.py`：`detect_system_language()` 函数的 `locale.getlocale()` 回退路径新增 C/POSIX 过滤——`current = locale.getlocale()[0]` 返回值经 `current.upper() not in ("C", "POSIX")` 判断后才返回…
- 修改 `tests/test_i18n.py`：
  - `TestDetectSystemLanguage._env_without_locale_vars` 重构为 `_clear_locale_vars(monkeypatch)`，使用 `monkeypatch.delenv(var, raising=False)` 逐一删除 locale 相关环境变量；
  - 4 处 `patch.dict(os.environ, ..., clear=True)` 替换为 `monkeypatch.setenv/delenv`；
  - 新增 `test_c_locale_from_getlocale_ignored` 回归测试：patch `locale.getlocale` 返回 `("C", None)`，验证 `detect_system_language()` 返回 `None`（不依赖真实环境变量）；
  - 修正 pytest 收集时 `sys.argv` 参数解析冲突：`SECONDS = int(sys.argv[2]) if len(sys.argv) > 2 and not sys.argv[2].startswith("-") else N`（避免 pytest `-q` 参数导致 `int('-q')` 崩溃）。

**改动说明**：

- **C/POSIX 过滤统一**：`detect_system_language()` 有两条路径获取语言——环境变量（`LANGUAGE`/`LC_ALL`/`LC_MESSAGES`/`LANG`）和 `locale.getlocale()`。
- **monkeypatch 规约**：`patch.dict(os.environ, clear=True)` 对 `os.environ` 做整体快照（`original = in_dict.copy()`）
- **PEP 758 格式化**：black 26.5.1（CI 固定版本）在 `target-version = ['py314']` 下自动剥离 `except (A, B):` 的括号。


## v4.0.9-dev (2026-08-24) — CI mypy 双错误修复（ctypes.WinDLL 平台门控 + 三参 getattr Any 泄漏）


### 涉及文件

- 修改 `i18n.py`：`_windows_ui_language()` 函数体首行增加 `if sys.platform != "win32": return None` 平台门控。
- 修改 `src/recorder_status.py`：`_live_network_capacity()` 中 `getattr(main, "scheduler", None)` 改为直接属性访问 `main.scheduler`。
- 修改 `tests/test_i18n.py`：新增 `TestWindowsUiLanguagePlatformGate` 两个用例——① 非 win32 平台门控直接返回 None（不依赖 ctypes 异常兜底）

**改动说明**：

- 平台门控采用「函数体首行早返回」而非调用点包裹：函数自带平台契约（注释本就声明「非 Windows 返回 None」）
- 刻意不用 `# type: ignore[attr-defined]`：该注释在 Linux CI 下必要、Windows 本地下多余…
- 刻意不用 `cast(ConcurrencyScheduler | None, getattr(...))`：cast 放弃检查且掩盖「属性已声明、本可直接访问」的事实。


## v4.0.9-dev (2026-08-24) — 高并发多平台录制调度与资源管理优化（自适应并发 + 按平台熔断降级）


### 涉及文件

- 新增 `src/scheduler.py`：调度核心模块，含 `ResizableSemaphore` / `PlatformBreaker` / `ConcurrencyScheduler` / `host_of`。
- 修改 `src/notify.py`：`record_error` / `record_success` 增加 `key` 形参并委托 `scheduler` 按 key 计入错误预算…
- 修改 `main.py`：引入 `ConcurrencyScheduler` / `ResizableSemaphore` / `host_of`
- 新增 `tests/test_scheduler.py`：12 个单元测试，覆盖信号量调容、熔断器状态机、自适应容量缩放/下限、按 key 隔离、录制并发软上限。
- 修复 14 个源文件共 21 处 Python 2 风格 `except A, B:` 语法错误（`build_exe.py`、`gui.py`、`i18n.py`、`scripts/check_coverage.py`、`scripts/compile_po.py`、`src/collector.py`、`src/config_io.py`、`src/recorder_status.py`、`src/spider.py`(2)、`src/ttwid.py`、`src/web_config.py`、`src/ws_client.py`、`src/platforms/bilibili.py`、`src/platforms/douyu.py`）

**改动说明**：

- **`ResizableSemaphore`**：实现上下文管理器协议的信号量…
- **`PlatformBreaker`**：按 key 的熔断器…
- **`ConcurrencyScheduler`**：调度中枢。
- **`host_of(url)`**：取 URL 主机名（小写、去端口/路径/查询）作为熔断 key；自定义 flv/m3u8 直链退回路径本身。
- **`notify.py` 接线**：`record_error(key=None)` / `record_success(key=None)` 在更新 `main.error_window` / `error_count` 之外…
- **`main.py` 接线**：
  - 全局变量由 `semaphore: threading.Semaphore = threading.Semaphore(1)` 改为 `scheduler: ConcurrencyScheduler | None`（None 占位）、`semaphore: ResizableSemaphore`、`recording_semaphore: ResizableSemaphore`。
  - `main()` 中首次初始化 `scheduler = ConcurrencyScheduler(configured_limit=max_request)`
  - `start_record`：`record_host = host_of(record_url)`（并在 `while True` 顶部、try 之前预置 `record_host = ""` 以消除 possibly unbound）
  - `check_subprocess`：将 `while process.poll() is None:` 录制循环包入 `recording_semaphore` 的 `acquire()` / `release()`（try/finally），实现可选的同时 ffmpeg 录制数上限治理。
- **测试补充**：`tests/test_scheduler.py` 共 12 用例（含修正两处测试前提：① `ResizableSemaphore(0)` 合法表示暂停态…


## v4.0.9-dev (2026-08-24) — 四语本地化目录统一与英式/美式英语分流 + 打包脚本串补齐 + zh_CN.mo 重编译


### 涉及文件

- 修改 `i18n/zh_CN/LC_MESSAGES/zh_CN.po`：追加 6 条 build/smoke 常量串、更新 PO-Revision-Date 至 2026-08-24、刷新头部注释。
- 修改 `i18n/en_US.json`：补齐 6 条新串；全量统一为美式拼写（消除 minimise/minimised/cancelled 等英式残留）。
- 修改 `i18n/en_GB.json`：补齐 6 条新串；改写为真正英式拼写（minimise/minimises/minimised/cancelled），与 en_US 仅在 4 条拼写敏感条目存在差集。
- 修改 `i18n/zh_TW.yaml`：补齐 6 条新串（简→繁转换，如 跳过→跳過、开始下载运行时二进制→開始下載執行時二進位檔）。
- 重新生成 `i18n/zh_CN/LC_MESSAGES/zh_CN.mo`（28,697 字节）并校验与 .po 同步。

**改动说明**：

- **四语 key 集合一致性**：以源码常量串为权威基准…
- **打包脚本串补齐**：build_exe.py 经 i18n 翻译路径输出、属用户可感知的打包信息…
- **美式/英式分流**：en_US 原内部不一致（混合 minimise、cancelled 等英式）


## v4.0.9-dev (2026-08-23) — 录制结果反馈调度器 + 探针退避标记（虎牙 403 死循环根治）


### 涉及文件

- 修改 `main.py`：`check_subprocess` 新增 `_proc_started_at = time.time()` 进程启动时刻…
- 修改 `src/stream_select.py`：新增公开入口 `mark_ffmpeg_reject(url, platform)`（委托 `_mark_probe_reject`）
- 修改 `src/recorder_status.py`：新增 `_live_network_capacity()` 取调度器实时容量（`scheduler.network_semaphore.value`）
- 新增 `tests/test_record_failure_feedback.py`：5 个单元测试，覆盖成功样本/快速失败+退避标记/慢速失败不标记/缺 -i 入参安全/容量回退。
- 修改 `tests/test_stream_select.py`：新增 `test_mark_ffmpeg_reject_marks_backoff`（退避跨轮新 token 命中 + 非白名单平台无操作）。
- 修改 `AGENTS.md`：新增「录制结果反馈约定」小节（失败样本/快速失败探针退避/轮末禁止无条件成功/容量显示实时值/回归测试要求）。

**改动说明**：

- **失败样本上报**：`check_subprocess` 在 `return_code` 分支处（`streamget.log` 退出码分支）：
  - 成功（rc==0，主播下线）：按房间 host 记一次成功样本，与录制失败分支配对，维持 error_window 真实错误率；
  - 失败（rc!=0，CDN 拒绝）：记一次失败样本驱动按 host 熔断与全局背压。
- **快速失败探针退避**：`time.time() - _proc_started_at <= _FFMPEG_FAST_FAIL_SECONDS`（20 秒）为快速失败（输入打开被 CDN 拒绝的签名…
- **慢速失败豁免**：`-reconnect_delay_max 60` 耗尽（>60s）属拉流中断/重连耗尽…
- **异常入参兜底**：`ffmpeg_command` 缺 `-i`（异常入参）时 `except ValueError` 捕获，仅记失败样本、跳过退避标记。
- **容量显示**：`_live_network_capacity()` 取 `scheduler.network_semaphore.value`（调度器就绪时）
- **直下路径对齐**：`direct_download_stream` 成功路径补 `record_success(record_host)`，与 ffmpeg 路径语义对齐（失败已在 except 分支有 `record_error`）。


## v4.0.9-dev (2026-08-23) — 网络并发双模式（动态调速 / 固定并发）


### 涉及文件

- 修改 `src/scheduler.py`：`ConcurrencyScheduler` 新增 `_dynamic_mode` 字段与 `set_dynamic_mode(enabled: bool)` / `dynamic_mode` 属性…
- 修改 `main.py`：热重载循环在 `scheduler.set_recording_limit(...)` 后追加 `scheduler.set_dynamic_mode(new_recording_limit == 0)`
- 新增 `tests/test_scheduler.py` 3 个用例：`test_scheduler_fixed_mode_pins_capacity_to_configured_limit`（固定容量不随任务数涨、往返切换恢复动态）、`test_scheduler_fixed_mode_ignores_error_backpressure`（固定模式忽略错误背压）、`test_scheduler_fixed_mode_guarantees_min_one_slot`（固定模式热更新即时生效 + 非法值兜底 1）。
- 修改 `AGENTS.md`：并发模型章节更新模式语义（`set_dynamic_mode` 接入、双模式分支、per-key 熔断与模式正交、15 个调度用例）。

**改动说明**：

- **模式语义**：「最大同时录制数(0为不限制)」=0 时启用动态调速（网络容量随活跃任务数自适应、下限 8 / 上限 128…
- **同时录制上限语义不变**：仍由 `scheduler.set_recording_limit(...)` 管控 ffmpeg 并发数，不受并发模式切换影响。
- **调度器 `adjust_loop` 在固定模式下为重算 no-op**（`recompute()` 发现容量未变时不触发改动、不调用 `set_value`），故可安全复用同一守护循环。
- **日志**：`set_dynamic_mode` 首次播报或模式切换时输出 `并发模式: 动态调速（网络容量随活跃任务数自适应，当前 <n>，下限 <min>，上限 <max>）` / `并发模式: 固定（忽略动态调速器，网络容量固定为 <n>，来源: 配置「同一时间访问网络的线程数」）`

## v4.3.0-dev (2026-09-27) — 本日改动按模块分类总览：发布链四处修复 + finding 4/5/6 + 四文档体积整理 + AGENTS 精简 + 元数据一致性同步

### 本日改动按模块分类总览（新增 / 修改 / 删除 + 文件路径）

> 本块由 wiki 同名条目的指针引出，收路径级明细；wiki 侧只保留模块摘要表。行尾形态：`build_exe.py` / `AGENTS.md` / 两份 wiki / 两份附录纯 CRLF，`tests/test_build_exe.py` 纯 LF（改动前后一致）。

#### 一、打包与发布链（`build_exe.py`）

- **修改**：`make_zip()` 产物名改为整体 f-string 拼接（禁 `Path.with_suffix(".zip")`）；新增「`zip_path.parent` 必须仍是 `DIST_DIR`」结构性守卫；`--dual` 分支接住两个返回值并在末行打印实际产物名；`_FFMPEG_DOWNLOAD_URLS` 的 Linux 两槽由滚动 `releases/latest` 改钉月末标签 `autobuild-2026-08-31-13-27`，`_PINNED_RUNTIME_SHA256` 的 linux-x64 / linux-arm64 同步为 `182c1b50…` / `e2dd447c…`；八槽被误改成 `OFFICIAL_SIGNATURE_PIN` 的部分按官方通道回填哈希。
- **新增函数**：`_clean_stale_release_zips()` 与 `_drop_stale_release_zips()`（出包前清 `dist/` 内 `{APP_NAME}-v*.zip` 陈旧产物并打印被删清单）、`_assert_dual_zips_are_two_files()`（两个返回路径必须互异且均已落件，否则 `SystemExit`）。
- **新增参数校验**：`--dual` 与 `--no-zip` 互斥并 fail-fast（`--dual` 分支从不读 `no_zip`）。
- **删除项**：无。未删任何函数、下载源或平台分支；`--dual` 仍产出 lite + full 两个 zip。

#### 二、CI 与发布工作流（`.github/workflows/build-release.yml`）

- **新增 job**：`release-guard`（`needs: [prepare, build]` + `if: always() && 发版路径 && needs.build.result != 'success'`）用 `gh release delete` 回收 `release-create` 预建的空/残缺 Release，默认不删 tag，并留 `::warning::`。
- **新增步骤**：`Verify dist contains both lite & full zips`（`shopt -s nullglob` 计数，缺失即 `exit 1`）；`fail_on_unmatched_files: true` 刻意不放宽。
- **并行改动备案**：该文件本日 08:14 由本会话之外的改动加入 `| tee build_exe.log` 与产物清单步骤（27,171 → 27,812 B），本会话未触碰该文件；`pipefail` 下 `tee` 不吞 `SystemExit` 已复核。

#### 三、测试（`tests/test_build_exe.py`，单文件 100 → 105 passed）

- **新增用例（9 条函数 / 含参数化共 10 个断言单元）**：`test_make_zip_name_keeps_dotted_version_and_variant_suffix`（`-lite` / `-full` 参数化）、`test_dual_suffixes_do_not_collide_on_one_zip`、`test_make_zip_refuses_name_containing_path_separator`（`version` 与 `suffix` 两个入参位各测一次，用 `'/'` 而非 `os.sep`）、`test_dual_and_no_zip_are_mutually_exclusive`（断言 `order == []`）、`test_dual_build_prunes_stale_zips_before_first_zip`、`test_no_zip_build_keeps_existing_dist_zips`、`test_dual_build_aborts_when_both_variants_land_on_one_zip`、`test_dual_build_aborts_when_a_variant_zip_is_missing`、`test_clean_stale_release_zips_only_touches_own_artifacts`。
- **桩改造**：`_stub_build_steps()` 的 `make_zip` 桩由常量 `Path("stub.zip")` 改为按 `suffix` 产出不同名字并真实写字节，且把 `build_exe.DIST_DIR` 改指 `tmp_path`（否则测试会真删仓库 `dist/` 下的用户产物）。
- **注释更正**：截断事故段的产物名示例 `windows-x64` → `windows-amd64`；「上方两条既有用例只断言文件存在」改为按用例点名的精确判据。

#### 四、根约定与文档

- `AGENTS.md`（修改）：`make_zip` 条目补 ④⑤ 两条同族判据与 9 个回归锁名；F-14 protobuf 条形的声明区间由 `>=6.31.1,<8` 更正为 `>=6.33.5,<8`（下限已于 2026-09-26 抬升，旧文属被证伪的事实性陈述）；体积精简 −1.4%（读数指针化 + 三处真重复合并 + `PYTHONUTF8` 与 `errors="replace"` 两条同因条目合并），97,034 → 95,715 B。
- `CODE_WIKI.md` / `CODE_WIKI_EN.md`（新增条目）：`^### v` 计数由本日 09:22 的 169 升至 **173 = 173**（发布链三处故障各 1 条、finding 4/5/6 + 四文档整理 1 条、`AGENTS.md` 精简 1 条、本总览 1 条）。
- `CODE_WIKI*.md`（结构整理）：更新日志内 73 个「涉及文件（按模块分类）」历史清单块外迁至本附录（zh 41 / en 32，213,734 B），原处保留小节标题 + 一行指针；按 `.workbuddy/docold` 唯一前缀匹配补回被 `…` 截断的表格单元格 109（zh）/ 181（en）处（+18,439 / +33,117 B）；「文档统计与索引」改为「取数命令 + 读数时刻」口径并新增「参考子文档索引」小节；`CODE_WIKI_EN.md` 两个 bash 代码块内 9 行中文注释补英文；「打包与发布」第 4 步「冒烟测试跑在 lite 版本上」按 MID-2254 的顺序改动更正，同行陈旧的 `ChallengePageError`（2026-09-23 已按 MIN-2267 删除）改回真实异常类。
- `README.md` / `README_EN.md`：本轮一致性审计中**未改动**（104,040 / 123,017 B 逐字节与整理前相同）；随后同日执行「版本条目同步」时补入 09-26 ~ 09-27 变更，现为 109,648 / 129,644 B（五小节条目数中英相等：🐛 9 / ✨ 12 / ⚠️ 9 / 🛠️ 7 / 🧪 4）。实测其行尾空白 0 行、连续空行 >1 的段 0 处、与 wiki 逐字重复仅 1 行，无历史清单块可外迁，更新日志不做压缩。

#### 五、新增参考子文档与本机记录

- `docs/agent-reference/changelog-file-inventories.md`（新增，130,064 B）与 `docs/agent-reference/changelog-file-inventories-en.md`（新增，98,458 B）：承接上述 73 个历史清单块与本块，纯 CRLF。
- `docs/agent-reference/session-learnings.md`（追加 2026-09-27 经验 6 条：产物命名必须断言名称本身、互斥参数不得静默、子代理断言须自证、外迁定位完整性、覆盖率陈旧数据防线、根约定文件的约束密度下限）。
- `.workbuddy/memory/2026-09-27.md`（追加三段会话日志；本机缓存目录，已被 `.gitignore` 与全部工具排除清单忽略）。

#### 六、构建产物元数据（`DouyinLiveRecorder.egg-info/`）

- **重建**（`.gitignore` 与 `.dockerignore` 均忽略，属本地产物）：按 `AGENTS.md` 记载的 `python -c "import sys; sys.argv=['setup.py','egg_info','--egg-base','.']; from setuptools import setup; setup()"` 重生成。
- **修掉两处真实漂移**：`PKG-INFO` 的 `Requires-Dist: h2` 由 `>=4.3.0` 更正为 `>=4.4.1`（2026-09-26 抬下限后从未传播进元数据）；`PKG-INFO` 内嵌 README 补齐此前缺失的 v4.3.0 更新日志段。
- **未漂移字段**：`requires.txt` / `entry_points.txt` / `top_level.txt` / `dependency_links.txt` 与重建前逐字节相同（三个 console_scripts 入口不变）；`Version: 4.3.0` 与 `importlib.metadata.version('DouyinLiveRecorder')` 实测一致。

#### 七、经核对确认「无需更新」的项（附判据）

- `requirements.txt`（**唯一被修改的一行**：L95 行内注释补全，规格未动）：原注释断在「…additional_headers/proxy 参数为 14.0+ API，」——行尾注释无法续到下一行，属真截断（同文件其余 9 个以逗号结尾的是可续行的整行注释）。按 `pyproject.toml` 里 websockets 的同源注释补全为「12/13.x 时 `connect()` 直接 TypeError 且被重连循环吞掉，弹幕永远连不上」。改后复核：23 条运行时依赖不变、与 `pyproject.toml` 包名集合仍逐项相等、文件保持纯 LF（108 行）、`tests/test_regression_2026_09_22_gates.py` 25 passed。
- `pyproject.toml [project.dependencies]`：未改动，23 条与 `requirements.txt` 集合相等；`[dev]` / `[build]` / `[gui]` 三组 extras 亦相等。
- `Dockerfile`：无硬编码版本；`ARG APP_VERSION` 声明先于 `LABEL` 使用点（`check_version.py` 断言行序）；Node 来源 `setup_24.x` 带 SHA256 钉定。
- `docker-compose.yaml`：`APP_VERSION: "${APP_VERSION}"` 经 `.env` 注入，`pull_policy: build` 守住不拉远端 `:latest`；工作区当前无 `.env`，文件头注释已说明未设时 `LABEL version` 为空，属预期而非缺陷。
- 跨 workflow 版本常量：`python_build = 3.14` 与 `node_version = 24` 在 `ci.yml` / `build-release.yml` 同值；`black==26.5.1` / `isort==9.0.1` / `mypy==2.3.1` / `pytest==9.1.1` 与 `.venv` 实装版本一致。
- 排除清单同源：14 个本地工具目录 + 6 个运行期产物目录在 `.gitignore`、`.dockerignore`、`pyproject [tool.coverage.run].omit`、`.coveragerc-concurrency`、`[tool.basedpyright].exclude`、`[tool.black].exclude`、`[tool.isort].extend_skip` 中均无缺项。
- `config/config.ini` 与 `config/URL_config.ini`：**未改动**。6 节 143 键；今日改动零新增配置面（`build_exe.py` 内 `read_config_value` / `read_config_bool` 调用数为 0）。两文件含凭据、被 `.gitignore` 忽略且不入镜像，本轮未写入、未复制、未外传，本记录亦不含任何真实取值。
- 四语目录（`zh_CN.po` / `zh_CN.mo` / `en_US.json` / `en_GB.json` / `zh_TW.yaml`）：**未改动**。780 / 780 / 780 / 780 键集相等（`tests/test_i18n.py::TestMultiFormatCatalogs::test_catalogs_share_same_keyset` 通过）；`compile_po.py --check` 报「与 .po 同步（781 条）」；`extract_i18n_strings.py` 报「缺失 0 条」。今日新增文案全部是 `build_exe.py` 的 `[build][FATAL]` 控制台输出——该文件从不调用 `i18n.tr`（打包期开发者通道，先于任何语言解析），刻意不入目录；提取器的三条盲区路径（`print_colored` / `messagebox.*` / 推送正文）在被改文件里实测出现次数均为 0。
