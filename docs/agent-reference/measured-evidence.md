# 实测数据与证据明细（自 AGENTS.md「已知坑」外迁的纯参考段）

> 2026-09-20 自 [`AGENTS.md`](../../AGENTS.md)「已知坑（避免回归）」外迁。
> **外迁判据**：只搬「一次性实测读数 / 采样表 / 提速倍数口径」这类参考证据——本文件不含任何祈使式约定；
> 「必须怎样、不得怎样」的约束全部留在根文件。根文件仍是长期约定的唯一事实源，本文件只是其明细，不另立版本。
> 每条下方的小标题即根文件里指向它的链接锚点，改名须同步两侧。

## 探针客户端复用作用域

实测（本地 HTTP/1.1，60 次）：仅构造+关闭 Client **6.7 ms**、新建 Client+单次探针 15.9 ms、复用 Client+单次探针 0.77 ms，故「每轮一支」已拿到大部分收益。**并发连接峰值实测（4 条同 host 候选、每条 HEAD+Range-GET）**：原实现 4 条连接 / 峰值 1 / 70.88 ms，当前 P1 **1 条连接 / 峰值 1 / 12.78 ms**——候选是串行校验的，复用不会抬高瞬时连接数，反而净减少新建连接数；据此「P1 加重虎牙连接预算消耗」的疑虑已证伪。

## 禁止关掉探针客户端keepalive

另注意口径：原实现的 `with httpx.Client(...)` 内 HEAD 与 Range-GET **已经**复用同一条连接（每候选 1 条连接，不是每请求 1 条），故复用的真实提速约 **5.5×**（70.88→12.78 ms），而非「每请求新建」基准给出的 36× 上界。

实测 `httpx.Limits(max_keepalive_connections=0)` 会让连接数从 1 涨到 **8**、耗时从 12.78 ms 退回 **72.99 ms**（等价于每次请求新建连接）。

## 虎牙选档ratio

实测 huya.com/chuhe（bitRate=30000）七档 ffmpeg 采样验证：原画 2560x1440\@60 / 蓝光30M\~8M 均 1920x1080\@60 / 蓝光4M 1920x1080\@30 / 超清 1280x720\@30 / 流畅 800x450\@24。

## 斗鱼本地重试链

实测 douyu.com/3168536：请求 rate=8200 被钳到下发 rate=4（蓝光4M `_4000.flv`），请求 rate=1 被钳到 rate=2。

## isort 静默跳文件

2026-09-20 实测（本机 Windows / GBK 语言环境，isort 9.0.1，命令 `python -m isort --check-only --profile black --line-length 120 .`）：
不带 `PYTHONUTF8` 时 **rc=0**，stderr 同时出现 **17 条** `UserWarning: Unable to parse file …: 'gbk' codec can't encode character`，
被跳过的文件为 `main.py`、`gui.py`、`web.py`、`build_exe.py`、`src/spider.py`、`src/stream_select.py`、
`src/config_io.py`、`src/notify.py`、`src/async_http.py`、`scripts/douyin_live_recorder_standalone.py`、
`scripts/smoke_test.py` 与 `tests/` 下 6 个（`test_config_bool.py`、`test_config_io_readonly.py`、
`test_http_config.py`、`test_i18n_migration.py`、`test_record_container.py`、`test_web_api.py`）。
抛错点在 `isort/core.py:479` 的 **encode**（不是 decode）。同一命令加 `PYTHONUTF8=1` 后
**0 条**该告警——门禁覆盖面恢复为全量：本轮仓库内自有 .py 共 **131** 个（根 6 + src 43 +
scripts 11 + tests 71，不含 `typings/` 的 14 个 `.pyi` 存根），其中 17 个此前处于「未检查」状态。
（报告 MID-63 记为 16 个 / 5 个测试文件；本轮实测集合为 17 个 / 6 个测试文件，另含
`src/async_http.py` 与 `scripts/` 下 2 个。计数随并行改动漂移，以 `grep -c "Unable to parse file"` 现测为准。）

2026-09-21 复测（同一台 Windows / `locale.getpreferredencoding(False) == cp936`，isort 9.0.1，
门禁参数 `--check-only --profile black --line-length 120 .`）：不带 `PYTHONUTF8` 时 **rc=0**、
stderr **18 条** `Unable to parse file`；带 `PYTHONUTF8=1` 时 **rc=0、stderr 完全为空（0 条）**。
较 09-20 基线多出的 1 个是 `src/collector.py`（其间并行改动新增的中文注释文件）。
逐文件清单：`build_exe.py`、`gui.py`、`main.py`、`web.py`、
`src/async_http.py`、`src/collector.py`、`src/config_io.py`、`src/notify.py`、`src/spider.py`、
`src/stream_select.py`、`scripts/douyin_live_recorder_standalone.py`、`scripts/smoke_test.py`、
`tests/test_config_bool.py`、`tests/test_config_io_readonly.py`、`tests/test_http_config.py`、
`tests/test_i18n_migration.py`、`tests/test_record_container.py`、`tests/test_web_api.py`。
同轮附带发现：`scripts/run_gates.py` 自身在 cp936 下会因转发 black 成功行的 `✨` 抛
`UnicodeEncodeError` 而崩溃（rc=1、无门禁结论），已由其 `ensure_utf8_streams()` 修复——
即 `PYTHONUTF8=1` 必须同时覆盖**子进程**与**转发输出的父进程**，只设一侧仍会失效。

## pip-audit 本地审计读数

2026-09-21 于 Windows 10 / 中文 locale（cp936）本地实测，工具版本 `pip-audit 2.10.1`，
装在仓库外的临时 venv 中（项目 venv 未被写入任何包，`requirements.txt` / `pyproject` 亦未新增条目）。

| 调用形态 | 不带 `PYTHONUTF8` | 带 `PYTHONUTF8=1` |
| --- | --- | --- |
| `-r requirements.txt`（解析全部传递依赖） | `UnicodeDecodeError: 'gbk' codec can't decode byte 0xa1 in position 112`，rc=1 | `No known vulnerabilities found`，rc=0 |
| `-r requirements.txt --no-deps`（只看声明的 21 条下限） | 同上崩溃 | 无漏洞，rc=0 |
| `--path .venv/Lib/site-packages`（项目实际安装态，只读） | 不适用（不经清单解析） | 无漏洞，rc=0 |

崩溃点是 `pip_requirements_parser.auto_decode()` → `locale.getpreferredencoding(False)`，
即解码发生在**读清单文件**阶段、早于任何 OSV 查询，故报错形态与「发现漏洞」毫无关系。
本轮三种形态的结论一致：现有下限（`starlette>=1.3.1`、`urllib3>=2.7.0`、`requests>=2.34.2`、
`python-multipart>=0.0.32`、`protobuf>=6.33.5,<8`）对 2026-09-21 的 OSV 数据均为干净集合。
注：`--venv` 不是 2.10.1 的合法参数（实测 `unrecognized arguments`），审计已安装环境走 `--path`。

## Node 24 / FFmpeg 9.0 版本基线详情

Node 运行时以 24.19.0 实测为准（全部 JS 签名脚本 + migu.js 通过），Dockerfile 随之安装 Node 24 LTS。FFmpeg 以 9.0 为基线，9.0 移除的 CLI 参数清单：`-vsync` / `-top` / `-qphist` / `-filter_complex_script` / `-adrift_threshold`。录制命令中的冗余 `-v verbose` 已删除（被 `-loglevel error` 覆盖）。

## egg-info 腐化实例

2026-09-18 对账时发现 `DouyinLiveRecorder.egg-info` 仍停留在 4.1.0 快照：`PKG-INFO` 版本 4.1.0（pyproject 已 4.3.0）、`requires.txt` 仍是 `websockets>=12.0` 与无上限的 `protobuf>=6.31.1`、`SOURCES.txt` 缺 30+ 文件。

## Dockerfile ARG 旧门禁失效形态

旧 `scripts/check_version.py` 只正则匹配「有没有 `version="${APP_VERSION}"` 这个字面」，顺序颠倒照样判 DYNAMIC——即门禁对 ARG 声明在使用点之后的失效永久失明。

## 运行时上游完整性产物实测（evermeet / johnvansickle / BtbN / gyan）

2026-09-22 实测三家上游不公布 SHA256：evermeet 只提供「追加 `/sig` 取 GPG 签名」、johnvansickle 只提供 `*.md5`。按「不得凭本地下载结果填写」的硬约束，宁可让发布链继续红在这 4 个槽位上（这是预期，不是回归）。

2026-09-26 复测与逐条取数命令（读数时刻即核对时刻——滚动别名下次运行会变，回填钉定值前须重跑）：

| 探针 | 读数 |
| --- | --- |
| `curl -sSL https://evermeet.ca/ffmpeg/getrelease/zip/sig` | 200，`application/pgp-signature`，594 B，**二进制** OpenPGP 包（非 armor）；重定向落点 `e.deolaha.ca:4242/pub/ffmpeg/ffmpeg-9.0.2.zip.sig`（当前滚动指向 ffmpeg 9.0.2，与 gyan 同代次） |
| `curl -sS "https://keys.openpgp.org/pks/lookup?op=get&search=0x476C4B611A660874"` | 200，`application/pgp-keys`，4060 B，UID `static FFmpeg binaries (signing key) <ffmpeg@evermeet.c…>`，服务端回显指纹分组 `20F6 EA3E 0CFD 6B4C 5344 7A73 476C 4B61 1A66 0874` ≡ `build_exe._RUNTIME_GPG_SIGNATURES` 的钉定值（**独立于 evermeet 通道的第二渠道印证**，指纹不再只是 TOFU-of-key 单渠道） |
| `curl -sS https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz.md5` | 200，`7fa72b652e19bf84c9461e332ea1cdf3  ffmpeg-release-amd64-static.tar.xz`（与 09-22 记录逐字相同）；同路径 `.sha256` → **404**；产物 `Content-Length` amd64 `41,888,096` / arm64 `19,337,412` |
| `curl -sS https://api.github.com/repos/BtbN/FFmpeg-Builds/releases/latest` | tag `latest`；`ffmpeg-n9.0-latest-linux64-gpl-9.0.tar.xz` = 150,998,508 B / `sha256:87de09009b85f61d452f5edcc702885c2ac7cb5f2016b30bd273b454df87eb9a`；`ffmpeg-n9.0-latest-linuxarm64-gpl-9.0.tar.xz` = 127,417,700 B / `sha256:30774c8ff65512d1700c4d552d4bfed30a9924576b38aab8e4deb9c744597d61`（Linux 两槽的钉定值即取自此 `assets[].digest`） |
| BtbN 归档成员布局 | 对 asset 做 `Accept: application/octet-stream` + `Range: bytes=0-4000000` 的前缀取回后 `tar -tJf`：顶层 `ffmpeg-n9.0-latest-linux64-gpl-9.0/`，可执行件位于 **`bin/ffmpeg`、`bin/ffprobe`**（与 johnvansickle 的平铺布局不同，故解压走递归按名查） |

**2026-09-27 复测**（起因：发布链红在 Linux ffmpeg 的 SHA256 校验处，钉定值当天即失配）：

| 探针 | 读数 |
| --- | --- |
| `curl -sS https://api.github.com/repos/BtbN/FFmpeg-Builds/releases/latest` | tag `latest` 的 `published_at` = **2026-09-26T13:22:38Z**（当日重发）；`ffmpeg-n9.0-latest-linux64-gpl-9.0.tar.xz` = 150,999,836 B / `sha256:0cfb214610c711681bd76861edd51b1c5e1aaa223c9a86b944cdb1869cabd7d9`；`ffmpeg-n9.0-latest-linuxarm64-gpl-9.0.tar.xz` = 127,395,868 B / `sha256:f2fe35e97ed20f5d189d933128cab78e513f9586a0b70effc92ce8b374cb8577`——与上表 09-26 记录的 `87de0900…` / `30774c8f…` 均不相等，即滚动别名下钉定必然漂移 |
| `curl -sS "https://api.github.com/repos/BtbN/FFmpeg-Builds/releases?per_page=100&page=1"` | 全库仅 **38 条** release：日更 `autobuild-*` 只留最近约两周（2026-09-13~09-26 共 15 条），**月末**标签长期保留（可回溯到 `autobuild-2024-10-31-12-59`）→ 钉 URL 只能钉月末标签 |
| `curl -sS https://api.github.com/repos/BtbN/FFmpeg-Builds/releases/tags/autobuild-2026-08-31-13-27` | `ffmpeg-n9.0.1-11-ge47273f4d9-linux64-gpl-9.0.tar.xz` = 126,600,656 B / `sha256:182c1b509720e939bb47bfb47dc29cc0c298640401128e3dce8627d10707eb5a`；`ffmpeg-n9.0.1-11-ge47273f4d9-linuxarm64-gpl-9.0.tar.xz` = 108,761,296 B / `sha256:e2dd447c8a47849c5812d87e54a47b20ae0f3603d38989440f4a5fe1af8755b1`（Linux 两槽现钉此标签；另有 `checksums.sha256` 资产可作二次核对） |
| `curl -sSL https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip.sha256` | 仍 `60f467265b1e312373dbcd92200c2618a74850f98d3d078e94296bb3fa2047ba`（windows-x64 钉定未漂移） |
| `curl -sS https://nodejs.org/dist/index.json` | 首个 `lts` 项仍 `v24.21.0`（Krypton，2026-09-07）→ node × 5 槽钉定未漂移 |

本机网络边界（决定可复现范围）：`github.com/.../releases/download/...` 直链在本机 `Connection was reset`（`http=000`），只有 `api.github.com` 的 octet-stream 通道可用；因此「按来源表 URL 全量下载并比对钉定值」这最后一步只能由 GitHub runner 首次实跑验证，本机只能验到 asset 存在、大小、digest 与前缀成员布局。

## 虎牙 FLV-first 冷启动采样

依据：2026-08-28/29 三轮真机两房间复现——虎牙 HLS 三条 CDN 线路（hs/tx/al）冷启动探针假绿（探针 200/206、ffmpeg 打开即 403，返回码 3436169992），TX/AL 次轮探针也稳定 403；FLV 每轮稳定可用（最长连录 6 分钟）。

## 虎牙探针退避窗口实测

实测虎牙 880214（2026-08-28）：重试 7 轮仅 2 轮侥幸录上，两轮日志中「CDN 探针退避中」告警**一次都没出现**。

## ffmpeg reconnect 事故形态实测

**另一形态（2026-09-11 事故）**：09-10 把这三个选项移到 `-i` 之前时丢失了 `-reconnect_streamed` / `-reconnect_at_eof` 的布尔值 `1`，ffmpeg 把下一个选项名当作值——`Unable to parse "reconnect_streamed" option value "-reconnect_at_eof" as boolean` → Invalid argument，**输入未打开即退出（-22）**，真实录制 100% 复现；而 `-reconnect_delay_max 60` 因带着值幸免。

`ffmpeg -report` 实测特征：连续 `Will reconnect at <size> in N second(s), error=End of file`，1/3/7/15/31s 指数退避、`-reconnect_delay_max 60` 只限单次延迟上限、重连无次数上限、永不放弃。

生产事故形态（2026-09-11 凌晨实测）：抖音/斗鱼房间（HLS 优先选源）仅产出弹幕 SRT、视频零字节、ffmpeg 常驻不退出（`-loglevel error` 下零输出零报错，`check_subprocess` 只看到进程存活）——"只录到字幕没录到视频"即为该故障；虎牙（`_FLV_FIRST_PLATFORMS` + HLS 排除列表）不受影响。**对照实验**：同命令加 `-t 10` 限时，60s 仍不退出且零字节产物；仅去掉该选项后 10s 录制 9MB 正常退出。

## ffmpeg per-file 选项归属实测

上游 ffmpeg 已把该选项从 `(input/output)` 收窄为 **`(output)` 专属**——`doc/ffmpeg.texi` 对照：6.1 / 7.1 / 8.0 / 9.0.2 均标 `(input/output)`、master 标 `(output)`；本机 master 构建 `N-126755-g52f05ac780-20260922` 的 `ffmpeg -h full` 把它列在 **"Advanced per-file options (output-only)"** 段。

A/B 读数（golden 产出的真实参数向量 × 本地 HLS/FLV 源）：选项在 `-i` 前 rc=4294967274 且零字节，在 `-i` 后 rc=0、275420 字节。

## 布尔配置写入 true 或 false 的漂移实测

实测把 `config.ini` 批量改成 `true/false` 后 8 项生效值漂移，其中最严重的是
`是否跳过代理检测 = true` 被判为 `False` → `global_proxy=False` → TikTok/SOOP/PandaTV/WinkTV/
Flextv/PopkonTV/Twitch/LiveMe/Faceit 共 9 个海外平台的解析分支全部走 `else`（只打印「网络异常」、
`port_info` 为空）→ **100% 无法录制**；其余漂移项覆盖保存目录层级（产物落 `downloads/<平台>/` 而非
`<主播>/`）、分段录制关闭、弹幕 SRT 不再产出、https 拉流降级为 http。

## 性能优化与修复变更记录

近期性能优化与修复的完整变更记录见 `CODE_WIKI.md` / `CODE_WIKI_EN.md` 的「更新日志 / Changelog」。2026-08-28/29 的 P1~P5 性能优化（探针客户端复用 / `requests.Session` 线程级复用 / 主循环 set 去重 / 调度器增量计数 / 正则提常量）、探针退避窗口对齐主循环、录制成功清除退避、虎牙 FLV-first、Web 模式 loguru 控制台 sink 重建，均已逐条落地为 AGENTS.md 约定与「录制结果反馈约定」「并发与线程模型」章节。

## 本机全量 pytest 偶发段错误

征兆是进度到 34% 前后（`test_log_archive` / 弹幕监控频段）崩在 `loguru._handler._queued_writer` → `_terminate_file` 的 `os.rename`——Windows 上多测试共享日志文件时轮转改名撞上未关闭句柄（`PermissionError WinError 32`），叠加 `enqueue=True` 的后台 writer 在 teardown 后写已关闭 sink。属环境噪声：单跑 `pytest tests/test_log_archive.py` 稳定 14 passed，跨版本改动前亦出现过。判读结果时若看到 `Segmentation fault`，先重跑并单独跑崩溃点所在文件，不要据此认定代码回归；同时优先清理 `logs/` 与 `.venv/Lib/site-packages/pytest/logs/` 下的残留日志句柄。

## 并行分组代码审查分工口径

2026-09-19 沉淀：把「审查全量源码」拆成 6~7 个模块组并行深读时，必须在每个子任务的 prompt 里写明本项目的刻意约定白名单（`#` 行注释不用 docstring、`except A, B:` 为 PEP 758 风格、line-length 120、四语 i18n、弹幕与视频链路解耦等），否则子代理会把刻意风格大面积误报为问题。同时要求每条结论附 `文件:行号` + 逐字符原文片段（≤12 行）+ 置信度，并在汇总前逐条回源复核严重项——这一步能筛掉「凭常识推测项目存在某问题」的臆测条目（本次实测：子代理给出的 14 项疑似问题经复核确认均不成立，已单列「已核实但不构成问题」章节）。

## 产物体积大头读数

2026-09-24 定稿口径（`scripts/report_bundle_size.py` 本机实跑，PyInstaller onedir 产物）：`python314.dll` 6.47MB、`libcrypto`/`libssl` 合计 7.22MB（HTTPS）、`pydantic_core` 4.93MB（FastAPI）、Tcl/Tk 5.28MB（GUI），四项合计约 24MB。

[历史注] 其中 `pydantic_core` 一项随 2026-09-29 阶段2 移除 fastapi/pydantic 后不再是固定成本，「合计约 24MB」随之失效；本节留存的是当时的原始读数，新读数由 `scripts/report_bundle_size.py` 本机复测后追加。

2026-10-03 阶段5 复测（同口径，`build_exe.py --smoke --no-zip --no-runtime` 产物，Windows x64，Tk 9.0 / Python 3.14.7；此为阶段0 缺失的**改造后总基线**，此前 dist 一直为空无可比总数）：**总计 91.81 MB / 224 个文件**。按包聚合大头：根目录 4 个 exe 32.28MB、numpy（.libs+包本体）26.29MB、`python314.dll` 6.48MB、`libcrypto-3.dll` 5.74MB、`tcl90.dll`+`tcl9tk90.dll` 5.28MB（Tcl/Tk）、PIL 2.52MB、`libssl-3.dll` 1.25MB、Crypto 1.54MB；`--strict` 式泄漏检查「开发/测试工具链泄漏：未发现」。customtkinter 摘除后产物内**零 CTk 条目**（`_internal/` 逐项核对）；venv 中 fastapi/pydantic 残留未卸载（用户终端动作），但零 import 未进包，读数不受影响。

2026-10-17 GUI 迁移 PySide6 复测（同口径，`build_exe.py --no-zip --no-runtime` 产物，Windows x64 / Python 3.14.8 / PyInstaller 6.x）：**总计 192.46 MB / 370 个文件 → 剪除 Qt 死重后 153.21 MB / 359 个文件**（较 2026-10-03 基线 +61.4MB，落在方案接受的 +50~70MB 区间）。PySide6 聚合 93.24MB/145 文件 → 53.99MB/134 文件；剪除明细（39.25MB，`build_exe.QT_BLOAT_FILES` 11 项）：`opengl32sw.dll` 19.68MB（Mesa 软件 GL，hook 无条件收）、`Qt6Quick` 6.44 + `Qt6Qml` 5.14 + `Qt6QmlModels` 0.97 + `Qt6QmlMeta` 0.15 + `Qt6QmlWorkerScript` 0.08（链入口 = platforminputcontexts 的 `qtvirtualkeyboardplugin.dll`，一并剪）、`Qt6Pdf` 4.41 + `imageformats/qpdf.dll`（本仓不渲染 PDF）、`Qt6OpenGL` 1.90、`Qt6VirtualKeyboard` 0.40。判据：对 `_internal/PySide6/` 全部 dll/pyd 做链接依赖扫描，剪除项零反向引用、删除后无未解析导入；冻结 GUI exe 实跑 9s 存活且窗口标题正常。`Qt6Network`+`QtNetwork.pyd`（约 2.7MB）被 tls 插件链接、刻意保留；Tcl/Tk 5.28MB 仍在（gui.py 顶层 `import tkinter`——迁移期旧版 LiveRecorderGUI 与崩溃兜底弹窗仍保留在本模块，旧版退役后可再评估）。`--strict` 式泄漏检查「未发现」。

## 打包与镜像体积读数（2026-10-17 追加，从根文件外迁）

PySide6 轮子本机解压尺寸 **647.56MB**（`pip show` 口径，镜像默认不装它的直接原因）；`build_exe.py` 打包面记录的两个数：轮子内含 **194MB 的 `Qt6WebEngineCore`**（故禁止 `collect_all('PySide6')`），hook 收完再剪的 Qt 死重清单 **11 项 / 39.25MB**（明细见上一节 2026-10-17 复测段）。compose 的 `gui` 服务与发布链的 slim 镜像差异即由这组读数决定：只跑 `main.py`/`web.py` 的镜像在屏蔽 PySide6 后导入链完整（本机以元路径拦截器实测）。

## 门禁扫描面的文件计数读数（2026-10-17 追加，从根文件外迁）

抬 `black_version` 常量前的同判据实测：**black 26.5.1 与 26.10.1 各跑一次全量 `--check`，两版结论逐字相同**（这才是「抬值只消除版本差、不改变判定」的判据）。当时的文件计数随仓库文件数变动，不是常量：2026-10-17 上午 239 files unchanged → 同日新增 3 个 `tests/*.py` 后 242 → 再加 2 个后 **244 files would be left unchanged**；无参 `mypy` 同期 `241 source files` → **243 source files**（mypy 计 Python 模块数、black 计被扫文件数，两个口径互不相等，引用时不得混用）。

## GUI 右边框裁切的几何读数（2026-10-17 追加，从根文件外迁）

本机实测（默认档、简中）：长提示标签初始 `wraplength=0` 时单行需求宽 **725~820px**；`root.winfo_reqwidth()` 实测 **1248 > geometry 1120**（赤字从内容列右缘开始被裁）；把几何临时压到档位最小宽后读到的内容收缩地板为 **1108~1151px**（随语言/字体变化）；若直接把 `minsize` 抬到需求宽则锁死在 **1389px**，用户再也拖不窄。判据本体（迭代到稳定再读、只抬到地板、clamp 到 `SCREEN_FILL_CEILING`）留在根文件。

## `sync_http` 线程级 Session 复用的收益读数（2026-10-17 追加，从根文件外迁）

改回每次新建 Session 时，单次出站多出「一次 TCP + 一次 TLS 握手」，本机实测 **11.9ms → 1.47ms（约 8×）**。根文件只保留「必须线程级复用」这条约束与该读数的指针；另记该模块当前无生产 importer（`sync_req` 调用点现只剩 tests/），故「已经吃到这个收益」的表述不得再写。
## 门禁工具版本与 exclude 锚定的历史读数（2026-10-17 追加，从根文件外迁）

**版本面历次对齐读数**（根文件条目：「本地门禁可外推的前提」）：2026-09-30 全量核查 black 26.5.1 / mypy 2.3.1 / pytest 9.1.1 与 CI 同值，isort 本机 9.0.2 对 CI 钉定 9.0.1 差一个补丁位；2026-10-03 经用户批准把 CI 的 `mypy_version` 抬到 2.4.0 与本机同值；2026-10-04 经用户批准把 `isort_version` 抬到 9.0.2 与本机同值；2026-10-17 经用户批准把 CI 的 `black_version` 抬到 26.10.1 与本机同值，并把 `.pre-commit-config.yaml` 的 black / isort 两个 mirror rev 对齐到同一组值。抬 `black_version` 前用 26.5.1 与 26.10.1 各跑一次全量 `black --check`，两版结论逐字相同；同日 `.pre-commit` rev 的存在性经 GitHub API `refs/tags/26.10.1`、`refs/tags/9.0.2` 逐个核实（均 HTTP 200），`pre-commit validate-config` OK，但本机 clone 被代理拦住，所以「钩子真的装起来跑一遍」仍未经验证。

**`[tool.mypy].exclude` 裸名→锚定修复的前后读数**（根文件条目：「exclude 的运行时二进制目录条目必须写目录段锚定形态」）：裸 `"ffmpeg"` 使 `src/ffmpeg_*` 与 `tests/test_ffmpeg_*` 共 10 个文件、裸 `"node"` 使 `src/node_install.py`/`tests/test_node_install.py` 对无参 mypy 失明。锚定修复实测：无参 `mypy` 读数 193→205 source files（+12 恰为逐文件枚举集合），新暴露 8 处存量错误当场修复——4 处恒回 False 的 `__exit__` 由 `-> bool` 改 `-> None`（falsy 语义不变，bool 标注触发 `[exit-return]`）、4 处「lambda 消费 `list.append` 返回值」改嵌套 def（`[func-returns-value]`）；本机 venv mypy 2.4.0 与 CI 钉定 2.3.1（`pip install --target` 临时目录交叉验证）各跑一遍均 `Success: no issues found in 205 source files`。
[历史注] 修复前的判据形态：新增 `src/ffmpeg_linux_download.py` 前后无参 mypy 同为 189 source files、加一个不含 ffmpeg 的测试文件后为 190；当时的代偿口径「显式传参 `python -m mypy src/ffmpeg_<x>.py tests/test_ffmpeg_<x>.py` + basedpyright」随本次锚定一并退役，「mypy 全绿不得当作 ffmpeg 系文件类型门禁证据」的禁令同步失效。

## 与根文件的分工

- 根文件保留条目的**约束与结论**并就地链接本文件对应小节；本文件只保留**支撑该结论的原始读数**，一字未改。
- 新增同类证据段沿用同一判据：句中不得出现「必须 / 禁止 / 不得 / 须」这类祈使式约束才可外迁。
