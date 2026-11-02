# PROPOSAL_2026-09-22 — 二进制供应链信任策略：改动提案与审批记录

> **文档性质**：待审批 / 部分已获批实施的生产代码改动提案。命名前缀 `PROPOSAL_*.md` 已在
> `.dockerignore`（排除进镜像）、`.gitignore`（登记为正式记录、刻意不忽略）与 `AGENTS.md`
> 「镜像额外排除集」条目三处同改（2026-09-22）。
> **事实源边界**：本文只记「已核实的现状 + 已批准/待批准的改动 + 回滚方案」；
> 长期约束本体仍以 `AGENTS.md`「三类钉定/校验互不覆盖」条目为准，本文不复制判定逻辑。
> **取证日期**：2026-09-22，全部结论来自本机直接请求或仓库内代码，标注为「实测」；
> 未实测项显式标为「未核实」。

## 一、背景：三面信任现状（评审结论）

| 面 | 来源与校验 | 信任强度 | 状态 |
| --- | --- | --- | --- |
| 发布期 windows | gyan.dev `.sha256`（滚动别名与版本化包两端点互证，ffmpeg 9.0.2）→ 已钉定 | 传输认证 + 人工核值 | 已钉定；上游不公布签名 → 验签**显式跳过** |
| 发布期 macOS | evermeet：不公布任何哈希，仅「追加 `/sig` 取 GPG 签名」 | 可升为**来源认证** | 本轮起加验签（P-2）；SHA256 槽位仍占位 |
| 发布期 linux | johnvansickle：只有 `*.md5`（实测 200） | MD5 不配作完整性根 | 保持 `UNVERIFIED_PIN`，`--strict` 继续拦发布 |
| 运行期 ffmpeg（**仅 Windows 分支**） | 官方滚动 URL + TOFU 旁路 `.sha256`（代码自评「等同目录权限」）；失败回落蓝奏云镜像（分享码硬编码） | 原先**首次安装零校验** | 本轮改：官方文档优先（P-1）+ 镜像显式开关（P-1b）；**同日 P-1b 作废——蓝奏云分支与 `FFMPEG_LANZOU_*` 已整体删除，Windows 只剩 gyan.dev 一条自动路径**（见 P-1b 小节抬头） |
| 运行期 ffmpeg（macOS / Linux 分支） | `install_ffmpeg_mac()` 走 `brew install ffmpeg`、`install_ffmpeg_linux()` 走 yum/apt（`src/ffmpeg_install.py:575/:594`） | 包管理器自身的分发链 | **本轮未动**（信任模型不同，不属 P-1 范围） |
| 运行期 node | Windows 抓 `nodejs.cn` 版本 + 从 npmmirror 下载 + TOFU | 镜像 + TOFU | 本轮改：哈希一律以 `nodejs.org/dist/<v>/SHASUMS256.txt` 为准（P-1） |
| 签名脚本层 | `utils._JS_SHA256_EXPECTED` 钉 5 个 `.js`，MID-62 已消 check-then-use | 部分覆盖 | 远程 `mgprtcl.wasm` **仍无钉定**（P-4，待批） |

核心判断：**发布链已是 fail-closed，真正的薄弱点在运行期** —— TOFU 把「首次安装」这一最高危窗口
完全交给无校验通过，且镜像兜底默认开启。本轮改动优先关闭这一窗口。

## 二、已批准并已实施（2026-09-22）

### P-1 运行期首次安装改为「官方公布哈希优先」

- `src/ffmpeg_install.py`：`_parse_official_sha256`(:117 严格 fullmatch，防上游/WAF 的 200+HTML 挑战页被当成期望值)、
  `_fetch_official_sha256`(:130)、判定入口 `_check_or_record_zip_sha256`(:206) —— 权威优先，
  不符即**拒绝安装并删包**；权威通过则顺手压过旁路基准；取不到官方文档才走 TOFU，且**必记 warning**。
  **实测形态**：文档端点回 **303** 重定向到 `packages/ffmpeg-<ver>-essentials_build.zip.sha256` 才给裸摘要，
  故必须保持 `allow_redirects=True`；改 HEAD 或禁重定向会**静默永久降级 TOFU**，已加静态回归锁。
- `src/node_install.py`：`_normalize_node_version`(:75)、`_parse_shasums256`(:85 按文件名字段**逐字相等**，
  不用子串匹配，否则会命中同名前缀的其它包)、`_fetch_official_sha256`(:97)；npmmirror 仅作加速通道，
  缓存命中路径同样过权威校验(:254)。
- **不采用**「把哈希常量钉进代码」：下载的是滚动地址，常量会在上游发新版后永久拒装（历史坑 MID-59 的成因）。

### P-1b 蓝奏云兜底改为显式开启

> **[2026-09-22 同日作废] 本小节整体已被后续改动推翻**：蓝奏云兜底不再「显式开启」，而是
> **连同 `_lanzou_fallback_enabled()` / `_install_ffmpeg_lanzou()` / `get_lanzou_download_link()`
> 与三个 `FFMPEG_LANZOU_*` 环境变量一起整体删除**，Windows 运行期只剩 gyan.dev 一条自动路径。
> 起因是本轮之后有人提出把运行期源改为某镜像直链，实测该直链回 `200 + text/html` 的人机验证页
> 且无任何官方哈希文档（详见 `CODE_WIKI.md` / `CODE_WIKI_EN.md` 同日条目
> 「Windows 运行期 ffmpeg 源收敛」）；据此判定「第二条无可信来源的 Windows 源」这一形态本身不该存在，
> 而非继续给它加开关。保留本节原文仅作审批留痕；现行约束以 `AGENTS.md`「三类钉定/校验」② 条目为准。

- `_lanzou_fallback_enabled()`：读 `FFMPEG_LANZOU_ENABLED`，默认 **0=关**；解析走 `config_bool.parse_config_bool`。
- 关闭时的日志固定包含可操作指令（设 `FFMPEG_LANZOU_ENABLED=1`），两处触发点共用单一渲染点，避免文案漂移成死路。
- `FFMPEG_LANZOU_SHA256` / `FFMPEG_LANZOU_ALLOW_UNVERIFIED` 的名字与「默认拒绝」方向不变（用户契约）。
  接受写法按 AGENTS.md 第 9 条统一到 `是/true/t/yes/y/on/1`（原名与默认拒绝方向不变）。
  **审批结论（2026-09-22）：维持该宽松解析，不收紧**——只认 `1/true/yes` 会与第 9 条的统一识别集合冲突，
  而真正的风险面（默认拒绝、须显式开镜像）没有变化。

### P-2 发布期官方 GPG 验签（引入 gnupg）

- `build_exe.py`：`_RUNTIME_GPG_SIGNATURES`（按运行时键分列，带外钉**完整 40 位主钥指纹**而非 key id）、
  `_run_gpg`（输出按字节、不开 `text=True`）、`_verify_gpg_artifact`（判据取 `--status-fd` 的
  GOODSIG+VALIDSIG，且**签名钥匙须属于该主钥/子钥集合**——VALIDSIG 报子钥指纹，逐字比主钥会假红）、
  接线在 `_download_file` 的「SHA256 已过」分支之后。
- `.github/workflows/build-release.yml`：macOS 增加 `Install gnupg (macOS)`（走 `.github/actions/retry`）
  与一步 `gpg --version` 可用性上报。发布路径 `require_pinned_hashes()` 为真时 **gpg 缺失即终止构建**，不降级放行。
- 未登记签名的槽位**一次网络/进程都不碰**（显式跳过，不是「试一下失败后放行」）。
- 指纹取自上游自身文档，属 **TOFU-of-key**；要再上一格需第二渠道核对（见第六节遗留项）。

### P-5 full 包产物自检（把「静默缺组件」这条通道堵掉）

- `build_exe.py`：`_find_runtime_binary`（递归 + 拒绝 0 字节）、`_probe_runnable`（真跑 `-version`，
  覆盖「macOS 缺 dylib 闭包」与「无 Rosetta」两种在包里但跑不动的形态）、`verify_runtime_binaries`、
  在 `download_runtime_binaries` 末尾处置：发布路径缺件 → `SystemExit`；本地 → 明确「不得用于发布」。
- 动机即本轮 macOS arm64 缺陷的三层隐身结构（拼出来的 URL + 宽泛 except + 无人校验产物）。

## 三、影响范围

| 维度 | 影响 |
| --- | --- |
| 分发面 | full zip 的 ffmpeg/node 校验链多两道（验签、产物自检）；macOS 包内容不变（同一份 evermeet x86_64 构建） |
| 运行面 | 首次安装多一次 ≤15s 的哈希文档请求（失败即降级，不阻塞安装主流程）；蓝奏云兜底**默认关闭**是行为变更，可能影响官方源不可达地区的自动安装成功率。**[2026-09-22 修订]** 该兜底已在同日后续改动中**整体删除**，所以这一维度的实际影响比本行原述更强：官方源不可达时 Windows 用户**不再有任何自动回落**，只剩手动安装提示 |
| CI | macOS job 多装 gnupg；`--strict` 语义不变（linux/macOS 的 ffmpeg 槽位仍未钉定，发布链继续红） |
| 用户契约 | ~~新增 `FFMPEG_LANZOU_ENABLED`；`ALLOW_UNVERIFIED` 接受写法放宽（见上）~~ **[2026-09-22 同日作废]** 三个 `FFMPEG_LANZOU_*` 变量随兜底整体删除，本行描述的新增/放宽均未成为最终形态。运行期 Windows 用户契约的净变化改为：**不再有镜像兜底**，官方源失败即给手动安装与删基准提示；新增任何第二源前必须先满足 ② 的「上游公布哈希」判据（已写入 `AGENTS.md`） |
| i18n | 新增 11 条 msgid，已同步四语目录并重编译 `.mo`（该轮读数 675 条）。[2026-09-22 追注] **不要把这一行当现行值**：同日目录被多次并发改写，条数随时刻变化（16:05 读到 N=663/键 662，16:14 读到 N=667/键 666）。现行读数与取数命令请就地复跑 `struct.unpack('<6I', open('i18n/zh_CN/LC_MESSAGES/zh_CN.mo','rb').read()[:24])[2]` + `scripts/compile_po.py --check` + `scripts/extract_i18n_strings.py`，判据见 `AGENTS.md`「四语目录条目数的权威口径」 |
| 测试 | 安装器两面 113 → 188 项；`tests/test_build_exe.py` 25 → 37 项；新增 `tests/test_check_runtime_pins.py` 11 项、`tests/test_ffmpeg_path_preference.py` 13 项；全量 **2487 passed / 12 skipped / 0 failed / 0 警告** |

## 四、回滚方案

| 项 | 回滚动作 | 残留风险 |
| --- | --- | --- |
| P-1 | revert `src/ffmpeg_install.py` / `src/node_install.py` 两文件的本轮改动 → 回到 TOFU | 无数据迁移；已写下的旁路基准文件仍可被旧逻辑读 |
| P-1b | ~~把 `_lanzou_fallback_enabled()` 默认值改回 `True`（一行）即恢复旧兜底行为~~ **[2026-09-22 同日失效：该函数与整条蓝奏云路径已删除]** 如确需恢复镜像兜底，须按 `AGENTS.md` ② 的判据先解决「无可信哈希来源」，不得只把代码回滚了事 | 用户已习惯「需显式开关」时会产生工单 |
| P-2 | 删 `build-release.yml` 的 `Install gnupg (macOS)` + 清空 `_RUNTIME_GPG_SIGNATURES` 即完全停用（配置为空 = 显式跳过，SHA256 钉定不受影响） | 停用后 macOS 回到「仅哈希钉定」，发布链仍被 `--strict` 拦 |
| P-5 | 把 `download_runtime_binaries` 末尾的处置块改回只打印（保留自检函数） | 缺件包重新可能被发布 |
| 整体 | 本轮改动全部落在 5 个文件（`build_exe.py`、两个 install 模块、`build-release.yml`、i18n 四目录）且**不触录制链路**，可用一次 revert 整体回退 | 回退后需重跑 `scripts/compile_po.py` 以还原 `.mo` |

## 五、P-3 排期：macOS arm64 原生 ffmpeg（未实施，待批）

### 关键事实（先纠正本文一处前提）

- **前提纠正**：本文与先前的评审口述一度把「运行期自动安装」当作只有 Windows 分支——**不成立**。
  `src/ffmpeg_install.py:575` `install_ffmpeg_mac()` 已在 macOS 上 `brew install ffmpeg`，
  `:594` `install_ffmpeg_linux()` 走 yum/apt。所以「arm64 用户用包管理器拿原生 ffmpeg」**代码里今天已通**，
  缺的是文档引导与「full 包里的 Intel 构建会不会遮蔽系统原生二进制」。
- `main.py:517-522` 把 `execute_dir/ffmpeg` **前置**进 `PATH`，而所有调用点用裸 `"ffmpeg"`
  （`main.py:3105`、`src/video_postprocess.py:185`）→ 包内没有 ffmpeg 时会自动落到系统安装。
- CI 只有 3 个 runner（`windows-latest` / `ubuntu-latest` / `macos-latest`，`macos-latest` = arm64），
  而 `RELEASE_RUNTIME_KEYS` 有 5 个键 → 走自源码构建路线时 `macos-x64` **根本没有构建方**，
  `check_runtime_pins.py --strict` 的「五键全覆盖」要求需一并重定（否则新增口径永远红）。
- **Rosetta 是到期项而非稳态**：Apple 开发者新闻（2026-09-01）称 macOS 27 为最后支持 Rosetta 的大版本
  （Intel-only 应用此后不再在 Apple Silicon 上运行）。〔来源：developer.apple.com/news，**建议维护者复核**〕
- **许可**：`--enable-gpl`（libx264/x265）时「这些部分一旦被使用，GPL 适用于整个 FFmpeg」
  （ffmpeg.org/legal，已核实）。今天分发的 gyan/evermeet 本就是 GPL 构建，**静态链不新增义务**；
  变化在于分发者从上游变成本项目 → 需自带 GPL 声明与源码获取途径（当前 `LICENSE` 为纯 MIT、README 无该段）。
- 现状三平台产物**均未签名/未公证**（workflow 已向用户声明）→ 自构建 arm64 的 Gatekeeper 待遇与现状同级，
  不是新阻塞；ad-hoc `codesign -s -` 只保证本机可执行、不可公证。

### 路线判定

| 路线 | 结论 |
| --- | --- |
| A CI 内自源码构建静态 arm64 | **可行但需先改口径**：自构建没有上游公布值，且「构建机中毒被固化成基线」的风险同样成立 → **禁止**把 CI 自算哈希塞进 `_PINNED_RUNTIME_SHA256`；须新增**第 4 类「源码可复现构建」**（闸口从「产物哈希」改为「源码 tarball 官方校验值/GPG + 构建配方哈希 + build provenance 附件」），并让 `_is_pinned()` 认识该新状态、把 AGENTS.md「三类互不覆盖」扩为四类 |
| B dylib 闭包 + `install_name_tool` | **否决，且无值得做的场景**：evermeet 已是自包含构建（x86_64 侧无闭包可收）；bottle 侧 11 个 runtime_deps 的 dylib 在别的 formulae 里，搬进包要逐个改 install name → **改 Mach-O 即破坏既有签名**（连上游签名一起失效）、`openssl@3` 的 CA 路径按前缀编译（改路径即证书失效）、`@rpath`/minos 造成「新系统编译的跑不了旧系统」。等价收益靠 brew 一行就能拿到 |
| C 维持 Rosetta | 可过渡，**但到期**（见上）。主链路 `-c copy`（`main.py:2992/3014`）下 Rosetta 开销基本不可见；只有 `converts_to_h264` 重编码（`src/video_postprocess.py:189`）与 `libmp3lame`（`main.py:2866`）明显吃亏。〔Rosetta 下 x86 SIMD/AVX2 的翻译性能倍率**未能核实一手来源**，故不给倍数〕 |

### 工作项与工时

| # | 工作项 | 改动面 | 验收 | 风险 | 人日 |
| --- | --- | --- | --- | --- | --- |
| **W1（前置决策）** | 新增第 4 类完整性口径「源码可复现构建」+ GPL 分发表态 | `AGENTS.md`（三类→四类）、`build_exe.py`（`_is_pinned` / `_unpinned_action` / `RELEASE_RUNTIME_KEYS`）、`scripts/check_runtime_pins.py` | 新状态**不被**判为已钉定；缺证据仍 rc=1/2；`tests/test_build_exe.py` 锁住 | 判定一放宽即假绿；node 槽语义须同步 | 1 |
| W2 | spike：macos-latest 上静态构建 arm64 ffmpeg/ffprobe | **脚本已备** `scripts/spike_arm64_static_ffmpeg.sh`（原定「一次性脚本写在仓库外」；改判：它要交给维护者在 mac 上跑、W3 也会复用，按 AGENTS.md 归入 `scripts/` 的长期复用工具，**产物仍落 `${TMPDIR:-/tmp}` 不进仓库**） | `lipo -archs` = arm64；`otool -L` 只剩系统库；libx264/libmp3lame/https/hls 齐；1s 真实转码通过 | 耗时/磁盘；`--disable-autodetect` 漏配会造成**假自包含**；官方 `.sha256` 端点形态未实测（取不到即 rc=2） | 2（脚本 0 / mac 实跑 2） |
| W3 | 固化进发布链（替换现 `brew install ffmpeg` 步骤，保留 retry 复合动作） | `.github/workflows/build-release.yml` | 三平台产物齐、`--require-pinned` 仍生效、job 不超时 | `timeout-minutes: 90` 与 matrix/版本钉定约定需同步（估算净增 ~30 min，**未实测**） | 1.5 |
| W4 | 证据链：源码 tarball 验签 + build provenance + Release 说明 | `build-release.yml`、`build_exe.py` | 无 attestation 即发布失败 | 第三方动作 ref 口径（MIN-17） | 1.5 |
| W5 | 许可声明落地 | `LICENSE` / 新增 `THIRD_PARTY_NOTICES.md`、`README*.md` | 中英同源 + 门禁 | 法务口径需维护者确认 | 0.5 |
| W6 | 止血（不依赖路线 A） | `README*.md`、macOS 分支注释、PATH 优先级说明 | 明确「arm64 已装原生 ffmpeg 时不被 Intel 构建遮蔽」的策略 | 改 PATH 优先级会牵动 Windows 语义 | 0.5 |
| W7 | 回归锁 + 文档同源 | `tests/test_build_exe.py`、`CODE_WIKI*.md` | 门禁全绿 | — | 0.5 |

**合计**：路线 A 全程 ≈ **7.5 人日**；只做 C + W6 ≈ **1 人日**。

### W1 已批准并落地（2026-09-22）

口径落地，**不含**任何 arm64 自构建步骤（W2 起仍需单独批准）。落地形态与本文先前「三类→四类」的说法
做了一次纠正：**面（①②③）与满足方式是两个维度**——第 4 类不是第四个「面」，它是发布期 ① 的
第二种满足方式（用于「CI 自源码构建、上游本就没有公布值」的产物），不得拿它去覆盖 ② ③ 的缺口。

| 项 | 内容 |
| --- | --- |
| 判定入口 | `build_exe._slot_is_gated()` = 「已钉定的官方哈希」∨「三件证据齐备的第 4 类」；`scripts/check_runtime_pins.py` 改为调它，**不再自己判形状**（避免两份口径） |
| 三件证据 | `_SOURCE_BUILD_EVIDENCE = {运行时键: {槽位: {source_sha256, recipe_sha256, provenance_ref}}}`，两条哈希须 64 位十六进制、ref 非空。**当前表为空**（无产物走该类），因此 `--strict` 照旧拦 |
| 防绕闸 ①  | 只有标记、证据不齐 → 与「未钉定」同等处置（`SOURCE-BUILD-PROVENANCE` 比 64 位十六进制更容易填） |
| 防绕闸 ②  | 声明第 4 类的槽位**不得走下载路径**：`_unpinned_action(..., declared_source_build=True)` 在**发布与本地两侧一律终止**，本地也不例外（否则换个标记就拿到免检）；该判定看**合并 `DLR_RUNTIME_SHA256` 后的实际取值**，不看内置表 |
| 闸口范围 | `--strict` 只对**发布矩阵真正构建的运行时键**要求满足；矩阵外保留键（`macos-x64` / `linux-arm64`，无 runner 产出）未钉定时**只告警且必须打印**，静默省略等于谎称全覆盖 |
| 实测纠正 | 新增用例抓到一个真缺陷：`_pinned_slots()` 会把取值 `.strip().lower()`，而标记常量是大写——按原样逐字比会让**注入式标记逃过拒下载判定**。已改为大小写无关比较（`_is_source_build_marker`）并由 `test_env_injected_marker_also_refuses_download` 锁死 |
| 回归锁 | `tests/test_check_runtime_pins.py` 11 项（矩阵内必红 / 矩阵外必打印 / 标记无证据不放行 / 证据形态四种破坏 / 缺槽位与空表 rc=2 / `emit_env` 同源）；`tests/test_build_exe.py` +12 项（判据真值表 7 例、拒下载两侧、注入通道、反向「已钉定仍可正常下载并验签」）。变异验证：把满足判据降为「认标记即放行」+取消矩阵内外分流 → **9 条变红**，已复原 |
| 文档 | `AGENTS.md`「三类钉定/校验互不覆盖」条目补第 4 类与其三条硬边界，并写明「面与满足方式是两个维度」 |

**建议顺序（2026-09-22 终态）**：W1 ✅ 已落地 → **W6 ✅ 已落地**（判据 `should_prepend_bundled_ffmpeg_dir` + README 引导）→ W2/W3/W4（路线 A 本体）
与 W5（GPL 声明，需法务口径）仍待单独批准。

### W6 已批准并落地（2026-09-22）：Apple Silicon 的 PATH 让位策略

| 项 | 内容 |
| --- | --- |
| 判据 | `src/ffmpeg_install.should_prepend_bundled_ffmpeg_dir()` 为**唯一事实源**；`main.py` 保留原「重复插入跳过」守卫 + 一次调用，策略不内联 |
| 五条同时成立才让位 | `sys.platform == "darwin"` ∧ `platform.machine() == "arm64"` ∧ 包内 `ffmpeg/` 存在 ∧ **注入前** PATH 快照另有 ffmpeg ∧ 那份 realpath 不在包内目录里；缺一即维持现状前置 |
| 关键实现点 | 探测用调用点快照（自读 `os.environ["PATH"]` 会探到刚前置进来的那份 → 让位永不发生）；自我遮蔽按 realpath 归一排除（否则日志承诺原生 arm64 而实为 x86_64） |
| 刻意漏判方向 | 解释器自身被 Rosetta 转译时 `platform.machine()` 报 `x86_64` → 不让位（架构信息不可信时不改用系统那份）；Windows / Linux / Intel Mac **逐字不变** |
| 可观测与文案 | 3 条 `i18n.tr` debug，四语目录同步、`.mo` 678 条；`README.md` / `README_EN.md` 各一条「Apple Silicon 用的是哪份 ffmpeg」FAQ（自查：`ffmpeg -version`、`which ffmpeg`、`logs/streamget.log`；注明 Docker 不受影响） |
| 回归锁 | `tests/test_ffmpeg_path_preference.py` 13 项（含 3 条 main.py 接线 AST 锁）；变异验证：非 darwin 分支改恒 False → 2 条红；拆掉自我遮蔽检测 → 2 条红；均复原 |
| **未验证边界** | 本机 Windows，darwin+arm64 让位分支**未在真机执行**；已实测的是「非 darwin 恒前置」（`import main` 后 PATH 头部仍是包内 `ffmpeg`）。发版前需在 Apple Silicon 上跑一次 README 自查并回填 |

## 六、验收标准（可复跑）

1. `python scripts/run_gates.py` → 8/8（已达成）；`basedpyright` 0/0/0（已达成）。
2. `pytest` 全量 0 failed / 0 警告（已达成：2487 passed / 12 skipped）；`check_coverage.py` 6/6（已达成，总 82.27%）；`mypy` 与 `mypy --platform linux` 各 146 文件 0 issue。
3. 变异验证：权威判定族 5 个变异点、开关族 5 个、node 权威来源族 5 个全部变红（子代理报告 16/16）；
   本轮 `build_exe` 侧 2 个变异点（去掉「签名者属于钉定钥匙」判据、去掉产物自检处置）各自变红后已复原。
4. **CI 首跑即 P-2 的真实验收**（本机不装 gpg、也不下载 300MB）：需在 macOS runner 上观察
   `evermeet ... GPG 签名核验通过` 是否出现；若报「取不到签名文件」说明 `/sig` 约定与实际不符，
   届时按第六节 R-2 处置而不是静默放宽。

## 七、待批 / 遗留（需负责人决策）

| 编号 | 事项 | 建议 |
| --- | --- | --- |
| P-3 | macOS arm64 **原生** ffmpeg 路线 | 排期见第五节；先批 W1（第 4 类口径），W6 止血建议立即做 |
| P-4 | 远程 `mgprtcl.wasm` 无钉定（AGENTS.md 三类中的第三类缺口，MID-62 遗留） | 需定：与 `.js` 同表钉，还是并入「发布期」面 |
| R-1 | linux ffmpeg 上游只有 MD5 → 该槽位**永远无法**按现口径钉定 | 决策：换源 / 自构建 / 显式接受 MD5 并写明降级理由（不得静默放宽形状判定） |
| R-2 | evermeet 指纹属 TOFU-of-key；`/sig` 端点行为未实测 | 从第二渠道核对指纹；CI 首跑作为端点验证 |
| R-3 | 未做真机 `--dual` 全量构建（约 300MB 下载）与真机自动安装 | 发版前在维护者机器跑一次，并把结果写回本文 |
| R-4 | `PERF_REVIEW_*.md` 在 `.gitignore` 里被当临时文档忽略，与 `CODE_REVIEW_*` / `DIAGNOSIS_*` 的「正式记录」定位不一致 | 单独一次口径统一，勿与本轮混做 |
| ~~R-5~~ | ~~standalone 与主程序的 PATH 策略不一致~~ **已处理（2026-09-22）**：选「对齐」而非「声明差异」——`scripts/douyin_live_recorder_standalone.py` 新增**同名同语义孪生判据** `should_prepend_bundled_ffmpeg_dir()`，`find_ffmpeg()` 不再无条件优先包内；两边注释互相点名，等价性由 9 格矩阵锁 | 后续改判据必须两处同改（同 `src/scheduler.py` 副本先例），已由 `test_both_copies_cross_reference_each_other` 把「互相点名」本身锁住 |
