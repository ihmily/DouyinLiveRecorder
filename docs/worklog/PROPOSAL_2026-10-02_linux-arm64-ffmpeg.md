# PROPOSAL_2026-10-02 — Linux arm64（aarch64）ffmpeg 支持：设计与审批记录

> **文档性质**：本次改动的**已获批规格**（三个范围项已由用户逐条批准，见「二、决策记录」）。
> 实现计划由本规格派生；长期约束本体仍写回 `AGENTS.md`，本文不复制判定逻辑、不复制门禁命令清单。
> **事实源边界**：钉定值事实源是 `build_exe.py`；`AGENTS.md` 是约束唯一事实源；本文只记现状取证、
> 边界划分、已批准改动与回滚方案。
> **取证日期**：2026-10-02，Windows x64 本机 + 直接外网请求。凡未在本机实跑的结论一律标「未核实」。

## 一、背景：三面现状（先坐实「已经有什么」）

| 面 | 现状 | 证据 |
| --- | --- | --- |
| 发布链取数与钉定 | **linux-arm64 已完整就绪**：BtbN `linuxarm64-gpl-9.0.tar.xz` 月末标签 URL、ffmpeg+node 双槽 SHA256 均已钉定 | `build_exe.py:1013`（URL）、`:513`（钉定）、`:427`（`RELEASE_RUNTIME_KEYS` 含该键） |
| 解包与取件 | 递归按名取 `ffmpeg`/`ffprobe`，不写死 `bin/`；缺件 `SystemExit` | `build_exe.py:1067` `_extract_linux_ffmpeg_binaries` |
| **谁去构建它** | ❌ 发布矩阵只有 `windows-latest` / `ubuntu-latest` / `macos-latest`，**没有任何 runner 产出 linux-arm64 产物**，Release 里从不出现该包 | `build-release.yml:258-262`；`check_runtime_pins.py:56` 注释已预留「若加入 linux-arm64 须同步映射」 |
| 运行期自动安装 Linux | 只走 `yum` → `apt` 包管理器链；无直接下载路径（无 root / 仓库无 ffmpeg 时只能「请手动安装」） | `ffmpeg_install.py:516-566` |
| 运行期直接下载器 | `ffmpeg_master_download.py` **仅 Windows**：master 滚动别名 + 纯 TOFU + 只认 zip 与 `bin/ffmpeg.exe` | 该文件 `:91-95`（`_windows_arch`）、`:431`（找 `ffmpeg.exe`） |
| Docker | `Dockerfile` 的 ffmpeg 走 `apt-get install ffmpeg`（天然随架构原生，arm64 可用），但**仓库当前没有任何镜像发布工作流**（历史上 `docker-image.yml` 已被删除） | `Dockerfile:82-83`；`ls .github/workflows/` 只剩 build-release/ci/issue-translator/trivy；删除记录见 `git log --diff-filter=D` |

结论：这次要补的不是「下载源」，而是**三件事**——谁构建 arm64 包、运行期能不能自己拿到已校验的原生二进制、镜像是否真发得出 arm64 层。

## 二、决策记录（2026-10-02 用户批准）

1. **范围**（多选）：发布链产出 arm64 包 + 运行期下载支持 Linux 原生 + Docker 镜像 arm64 可用。三项**全做**。
2. **运行期完整性口径**：选「官方哈希优先 + 降级 TOFU」——不是纯 TOFU。
3. **运行期实现落点**：选**方案 A**（新建 `src/ffmpeg_linux_download.py`）。
   - 否掉的 B：把 tar.xz 塞进 `ffmpeg_master_download.py`。该模块的既有语义是「master 滚动别名 + 只有 TOFU 一档」，
     把「不可变标签 + 官方 digest」混进去会让同一模块内两个完整性档互相打脸，其头注释的既有论证随之失效。
   - 否掉的 C：内联进 `install_ffmpeg_linux()`。约 250 行下载/校验逻辑落在包管理器分支旁边，该文件已 700+ 行，职责纠缠。
4. **`docker-compose.yaml` 的镜像名**：**不改**（仍 `ihmily/douyin-live-recorder:latest`，属上游命名空间）。本次只新增 GHCR 发布链。
5. **镜像发布触发**：**仅 `push: tags: v*`** 推 `latest` + 版本 tag。不留 `workflow_dispatch` 推 tag 的口子——
   手动触发若也能覆盖 `latest`，等于把「不可变发布物」变成可反复改写的别名。

## 三、S1 发布链产出 linux-aarch64 包

### 3.1 可行性核实

`ubuntu-24.04-arm` 标签**存在**（actions/runner-images README 第 26 行「Ubuntu 24.04 Arm64 / `ubuntu-24.04-arm`」；
`ubuntu-26.04-arm` 亦存在）。取本仓沿用 `ubuntu-latest` 的同代际口径，选 **`ubuntu-24.04-arm`**。
**未核实**：该标签是否计入本账号的免费额度（官方页未见定价口径）→ 由首次 CI 实跑裁定，见「八、交回用户的验证项」。

### 3.2 改动点（四处同批，缺一即门禁红）

| # | 文件 | 改动 | 为什么必须同批 |
| --- | --- | --- | --- |
| 1 | `.github/workflows/build-release.yml` | 矩阵 `include` 追加 `- os: ubuntu-24.04-arm` + `platform: linux-arm64`（**位置插在 `ubuntu-latest` 之后、`macos-latest` 之前**） | `check_runtime_pins._runtime_matrix_keys()` 按 `os:` 行出现顺序返回键列表，而 `tests/test_check_runtime_pins.py::test_workflow_matrix_and_test_constant_stay_in_sync` 断言**与 `_MATRIX_KEYS` 逐序相等**（不是集合比较），插入位置即契约 |
| 2 | 同上 | 两个 `if: matrix.platform == 'linux'` 步骤（`:298` Install ffmpeg + xvfb、`:368` Build executables + smoke test）改为 `startsWith(matrix.platform, 'linux')`；`if: matrix.platform != 'linux'`（`:374`）改为 `!startsWith(matrix.platform, 'linux')` | 否则 arm64 job 不装 xvfb、不走 `xvfb-run` 分支，GUI 冒烟在无头 arm64 上必红；而通用分支给它 `tee build_exe.log` 又会让它失去 xvfb |
| 3 | `scripts/check_runtime_pins.py` | `RUNNER_TO_RUNTIME_KEY` 补 `"ubuntu-24.04-arm": "linux-arm64"`；并把上方「三平台 / windows-latest·ubuntu-latest 为 x64」注释改为四平台实况 | 未登记的 runner 标签走 `sys.exit(2)`（该函数 `:96-103`），属「门禁本身失效」档，会把发布链在 prepare 直接断掉 |
| 4 | `build-release.yml` 的 `Verify artifact completeness` | `-lt 6` → `-lt 8`，错误文案改「期望 8 个：windows/linux/linux-arm64/macos × lite/full」；同文件头部与 `release` job 内「3 平台 ×2」注释同步 | 4 平台 ×（lite+full）= 8；`find artifacts -name '*.zip'` 现在数的是 Release 附件，漏改等于「残缺 Release 照发」 |

另外两处**只改注释、不改行为**：`build-release.yml` 头部「三平台可执行文件构建」标题段、
`build_exe.py:425-427` 上方「与 build-release.yml 的三平台矩阵同源」措辞（矩阵已变四平台）。

### 3.3 产物名与体积

`build_exe.py:1398` 用 `platform.machine().lower()`，arm64 Linux 上实际取值是 **`aarch64`**，故产物名为
`DouyinLiveRecorder-v<版本>-linux-aarch64-{lite,full}.zip`（与 AGENTS.md「产物名示例一律写 machine() 实际取值」同口径，
不写成 `arm64`）。full 包内置 ffmpeg 归档实测 108,761,296 B（`build_exe.py:997` 已记录），
**合计体积不估算**：落地后按 `scripts/report_bundle_size.py` 对本机产物复测，arm64 侧只能在 CI 首跑后取读数。

### 3.4 数据流（arm64 job）

`prepare --emit-env` 透传全表钉定 → build job 在 arm runner 上解析出 `runtime_slot_key()=="linux-arm64"`
→ `_ffmpeg_source_url()` 命中 arm64 条目（**不走**「回落同族 x64」那条 warning）→ `_download_file(..., slot="ffmpeg")`
按 `--require-pinned` 校验 64 位十六进制 → `_extract_linux_ffmpeg_binaries()` 取件 → `--smoke` 三入口
→ `Upload to GitHub Release`（`dist/*-lite.zip` + `dist/*-full.zip` 通配，无需改动）。

## 四、S2 运行期 Linux 原生 ffmpeg（新模块 `src/ffmpeg_linux_download.py`）

### 4.1 完整性判据的真值表（这是本模块的唯一裁决面）

| 官方 digest | `FFMPEG_MASTER_ALLOWED` | 结果 | 日志档位 |
| --- | --- | --- | --- |
| 取到且匹配 | 任意 | **安装** | debug（成功） |
| 取到但不匹配 | 任意 | **拒装**、删包、返回 False | error（可能被替换，指引人工核对） |
| 取不到 | 假（默认） | **拒装**、返回 False，提示可显式开启 TOFU 降级 | error（默认路径必须已校验） |
| 取不到 | 真 | 走 TOFU：有基准则比对（不符即拒装），无基准则首次记账并安装 | warning（首次记账，与 Windows 侧同口径） |

三条不变量：
- **默认路径必须带校验**。TOFU 降级仍由 `FFMPEG_MASTER_ALLOWED` 这**同一个**开关控制（不新增第二个开关），
  但该开关**不由本模块自己读环境变量**：`ffmpeg_install` 会 import 本模块，反向 import
  `_master_source_allowed()` 将构成循环导入。定形为**调用方传参**——
  `install_ffmpeg_linux_native(..., master_allowed=_master_source_allowed())`，
  判据实现留在 `ffmpeg_install` 单点（Windows 分支用的也是它）。
  已校验直下**不受该开关门控**：它满足 `AGENTS.md`「三类钉定/校验」② 的准入判据（有官方公布哈希），
  而 TOFU 不满足——二者门控强度不能相同。
- **基准存在却读不出 → 拒装**（沿用 SEV-2222 的收紧结论，与 `ffmpeg_master_download._tofu_verify_or_record` 一致，不得回退成 warning）。
- **形态先于哈希**：先判拿到的到底是不是 `.tar.xz`，再算哈希，最后解压（对齐 `download_ffmpeg_official` 的 MID-59 判序）。

digest 的权威性依据（实测 2026-10-02）：`api.github.com/repos/BtbN/FFmpeg-Builds/releases/tags/autobuild-2026-08-31-13-27`
回 `assets[].digest = "sha256:<64hex>"`（该标签的 `linuxarm64-gpl.tar.xz` 读数 `b65dfcc9…`）。
它与产物**同为 GitHub 通道**，故与 gyan.dev 的 `.sha256` 文档同级——属**同源一致性校验而非来源认证**
（MIN-2258 同一措辞，不得写成「已认证来源」）；比 gyan 强的那半是 URL 里的标签不可变，期望值不会随上游重发漂移。

### 4.2 模块契约

- `_linux_arch() -> str`：`platform.machine()` 字面量分流，`arm64`/`aarch64` → `"linuxarm64"`，其余一律 `"linux64"`
  （保守判据与 `_windows_arch()` 同构：架构信息不可信时宁可装能跑的 x64）。
- `_LINUX_FFMPEG_URLS: dict[str, str]`：**按 arch 一条完整 URL**，值是 `build_exe._FFMPEG_DOWNLOAD_URLS` 的同一条字面量。
  物理上必然有两份（冻结 exe 里 import 不到根目录 build 脚本），故由回归锁比对两边逐字相等（见「六、测试与门禁」T-5），
  不在本文维护第三份副本。
- `_api_release_url(asset_url) -> str`：**从 URL 反解** `repo` 与 `tag`，拼出
  `https://api.github.com/repos/<repo>/releases/tags/<tag>`。不新增第二个 URL 常量，也就不可能出现
  「下载走新标签、取 digest 走旧标签」的半拉子形态。反解失败（URL 形态不符）→ 返回 ""，按「digest 取不到」处理。
- `_fetch_asset_digest(asset_url) -> str`：带 `Accept: application/vnd.github+json`、连接/读取超时分离、
  只认 `status==200` 且 `Content-Type` 非 html；按 asset `name`（URL basename）匹配取 `digest`，剥 `sha256:` 前缀后
  必须过 `^[0-9a-f]{64}$` 形状关（形状非法与取不到同级，同 `build_exe._is_pinned` 的判据风格）；
  **任何异常一律回 ""**，不得穿出（本模块整体「失败不抛」）。403 速率限制归入「取不到」，
  因为本模块的正确降级路径已经为此设计。
- `install_ffmpeg_linux_native(dest_dir: str, arch: str | None = None, *, master_allowed: bool = False) -> bool`：
  取 digest → 流式下载到 `dest_dir` 下临时 `.tar.xz`（连接/读取超时**在本模块自持常量**，
  量级与 `ffmpeg_master_download` 一致但不跨模块引它的私有常量——那会把 Windows 语义模块的内部细节
  变成第二个耦合点；分块写盘保持内存恒定）→ 形态校验 → 按 4.1 真值表校验（`master_allowed` 只作用于
  「digest 取不到」那一档）→ `tarfile.open(..., "r:xz")` +
  `extractall(filter="data")`（MI-26 同源：**显式传 filter**，不依赖解释器默认值）→ **递归按名**找
  `ffmpeg`/`ffprobe`（不写死 `<顶层>/bin/`，与 `_extract_linux_ffmpeg_binaries` 同一判据；缺件即失败不静默出空目录）
  → 平铺拷到 `ffmpeg_path`（`execute_dir/ffmpeg/`，与 L-42 更正后的实际布局一致）→ `chmod 0o755`
  → PATH 前置 + `ffmpeg -version` 复核 `returncode==0` 才 True → `finally` 删临时归档。
- TOFU 基准文件：`_ffmpeg_linux.<asset_stem>.sha256`。资产名进文件名，换标签即换基准，
  不会出现「新标签的产物被旧标签的基准判成篡改」；同前缀陈旧基准按 `_prune_stale_master_baselines` 的做法修剪。
  前缀与 `_ffmpeg_official*`（Windows 官方）、`_ffmpeg_master*` 互不污染。
- **不改动** `download_ffmpeg_official` / `install_ffmpeg_windows` / `_windows_arch` 的行为；Windows 侧一行不动。

### 4.3 接线

`install_ffmpeg_linux()`（`ffmpeg_install.py:516`）在 yum、apt 两条路径**都失败之后**、
打印「请手动安装」之前调用 `install_ffmpeg_linux_native(execute_dir, master_allowed=_master_source_allowed())`，
成功即 `return True`。
包管理器仍是首选（apt/yum 天然给原生 arm64，且带发行版自己的签名链），新路径只在「拿不到包管理器」时兜底——
这条顺序不得颠倒。`should_prepend_bundled_ffmpeg_dir()`（W6）**不涉及本次改动**：Linux 分支恒 True，
判据只在 `sys.platform == "darwin"` 才生效。

## 五、S3 Docker 多架构发布（GHCR，新工作流）

### 5.1 `.github/workflows/docker-publish.yml`

- 触发：仅 `push: tags: ["v*"]`。
- `permissions: contents: read`（job 级按需 `packages: write`）；**不引入任何新 secret**，
  登录凭据用自动注入的 `GITHUB_TOKEN`。
- 两个原生构建 job（**不走 QEMU**）：`docker-build-amd64`（`ubuntu-latest`）与
  `docker-build-arm64`（`ubuntu-24.04-arm`），各 `--platform linux/<arch>` 构建并 `--push`
  一个**分架构临时 tag**（`ghcr.io/<owner>/<repo>:vX.Y.Z-amd64` / `-arm64`）。
  工具链定形：`docker/login-action` + `docker/setup-buildx-action` + `docker/build-push-action`
  （`outputs: type=registry`，**不**用 `type=oci`/`type=tar`），merge 需要的东西只有一个——
  各架构的 manifest digest，一律取 build-push-action 的 `steps.<id>.outputs.digest`
  （`docker/metadata-action` 只用它拼 tag，不当 digest 来源）。**不采用单 job QEMU 双平台一次成型**：
  本镜像构建期要 `apt install ffmpeg/nodejs` + `pip install -r requirements.txt`，
  在 QEMU 下模拟 aarch64 是**整层重活**（`trivy.yml:51` 已注明完整 docker build 是全仓最重的一次外网动作）。
- 一个 merge job：`needs` 两个构建 job，用 `docker/setup-buildx-action` 后跑原生
  `docker buildx imagetools create -t <repo>:vX.Y.Z -t <repo>:latest <amd64 digest> <arm64 digest>`
  合成 `linux/amd64,linux/arm64` 清单（**digest 引用不依赖分架构 tag 长期存在**；
  两个构建 job 必须把 `steps.build.outputs.digest` 提升为 **job 级 `outputs:`**，
  否则 `needs.*.outputs.digest` 取到空串、合成步骤报无效引用而构建本身全绿）。
- 镜像内版本仍经 `--build-arg APP_VERSION` 注入（`AGENTS.md`「版本号同步」+ MIN-14 的 ARG 行序约束不变）。
- `concurrency`：`cancel-in-progress: false`（与 build-release.yml 同一条「发布类不允许半途取消」理由）。
- 网络安装重试：凡新工作流里的 apt/pip 安装步骤一律走 `.github/actions/retry` 复合动作，
  **不得**再内联 `for i in 1 2 3` 之类重试循环（AGENTS.md「CI / workflow 约定」）。
- 第三方动作 ref 口径**定为浮动大版本标签**（`docker/login-action@v3`、`docker/setup-buildx-action@v3`、
  `docker/build-push-action@v6`；合成清单用 `docker buildx imagetools create` 原生命令，不引第三个动作）。
  判据来自 MIN-17 的区分线：
  本工作流的触发源是维护者推的 `v*` tag（可信输入），与 `build-release.yml` 用
  `softprops/action-gh-release@v3` 同一条线；`trivy-action` 的 SHA 钉定先例属「cron 无人值守 +
  外部可读输入」那一侧，不外推到 tag 触发的发布链。
  **实现时须实测确认这几个大版本标签是当前存在的版本**（本条是口径决定，不是取值核实）。

### 5.2 已知边界（写进本文，不得在别处淡化）

- GHCR 匿名 `docker pull` 需要包可见性为 **public**，而可见性是**仓库设置层面**的一次性人工动作，
  Actions 的 `GITHUB_TOKEN` 不会替你把它设为 public。**未核实**（本机无推送权限）→ 交回用户。
- `docker-compose.yaml` 不改名，故本仓发布的 GHCR 镜像与 compose 默认拉取名**不同源**：
  用 compose 起 arm64 的用户走的是 `pull_policy: build` 就地构建路径（MIN-18 的既有约定），
  那条路径在 arm64 主机上本来就能构建成功。这是刻意留下的分工，不是缺口。

## 六、测试与门禁（每项给「删掉生产实现会不会红」的自评）

| # | 测试 | 锁什么 | 新建/修改 |
| --- | --- | --- | --- |
| T-1 | `tests/test_ffmpeg_linux_download.py` | 4.1 真值表四格逐一（digest 匹配/不符/取不到×开关两侧）、`_linux_arch()` 分流矩阵、`_api_release_url` 反解（含形态不符→""）、digest 形状非法→拒装、tar.xz 递归取件+缺件失败、执行位、基准读不出→拒装 | 新建（与模块同名，按 `AGENTS.md`「测试」约定） |
| T-2 | 同上 | **失败不抛**：给 `_fetch_asset_digest` 与下载函数注入畸形返回，断言顶层入口恒回 `bool` | 新建 |
| T-3 | `tests/test_ffmpeg_install.py` | `DOWNLOAD_SOURCES` 加 `api.github.com`（值=`官方哈希`+「与产物同平台异服务、URL 标签不可变」理由）、`github.com` 条目的完整性方式与理由改写；`DOWNLOAD_MODULES` 加 `src.ffmpeg_linux_download` | 修改（两处缺一即锁红是 AGENTS.md #10 硬规则） |
| T-4 | `tests/test_ffmpeg_install.py` | `install_ffmpeg_linux()` 的调用顺序锁：包管理器成功时**不得**触达直下路径；两条都失败才触达（行为锁，不是正则钉源码字面量——M-26 禁令） | 修改 |
| T-5 | `tests/test_build_exe.py`（或新文件，就近原则） | `_LINUX_FFMPEG_URLS` 与 `build_exe._FFMPEG_DOWNLOAD_URLS` 的 linux 两条**逐字相等**（`importlib` 文件加载，先例 `check_runtime_pins._load_build_exe`）；防「运行期取旧标签、发布链取新标签」漂移 | 新建 |
| T-6 | `tests/test_check_runtime_pins.py` | `_MATRIX_KEYS` 补 `"linux-arm64"`（插在 `linux-x64` 后、`macos-arm64` 前，与矩阵 `os:` 行序一致）；`test_real_matrix_parser_reads_workflow_runner_tags` 的合成样本不变 | 修改 |
| T-7 | `tests/test_build_exe.py` | `_ALLOWED_HOSTS` **不动**（`github.com` 已在；运行期侧的 `api.github.com` 属 T-3 的 `DOWNLOAD_SOURCES`，两者是不同的锁，不得混用） | 只复核 |
| T-8 | `tests/test_docker_publish_workflow.py` | 结构锁：触发只有 `tags: v*`；两个构建 job 的 runner 与 `--platform` 一一对应；merge job `needs` 二者；无 `secrets.` 引用（凭据必须走 GITHUB_TOKEN）；`cancel-in-progress: false` | 新建 |
| T-9 | 全量门禁 | `python scripts/run_gates.py` + `pytest` + `scripts/check_coverage.py`（口径取 `AGENTS.md`「格式化命令」，本文不重述参数）；涉平台分支 → `mypy --platform linux` 增跑 | 收尾 |

**变异验证**：T-1/T-2/T-5 属新增安全不变量类（完整性真值表 + 两处副本一致性），**必做**；
按 `AGENTS.md`「变异验证…当轮还原」用「内存备份→改写→跑→按字节还原」的单进程手法，
改动行带 `MUTATION-<短id>` 标记并在当轮清掉（R8 全仓扫描兜底）。

**孪生副本**：`scripts/douyin_live_recorder_standalone.py` 已 grep 复核，**无 ffmpeg 安装/下载链**
（只有 `should_prepend_bundled_ffmpeg_dir` 同名判据）→ 本次运行期改动**刻意不回灌**，提交说明按
`AGENTS.md` 要求写明「已核对 / 刻意不回灌及原因」。实现时再 grep 一次 `install_ffmpeg`，若结论变了则回灌。

## 七、文档同步（DoD 第 4 步，中英双份）

- `AGENTS.md`：
  1. 「CI / workflow 约定」的发布矩阵条目补「四平台，runner 标签↔运行时键映射由 `check_runtime_pins.py` 单点登记」；
  2. 「已知坑 · 构建产物」新增一条：运行期 Linux 直下的 URL 与 `build_exe._FFMPEG_DOWNLOAD_URLS` 是两份物理副本，
     一致性靠 T-5 的回归锁，改一处必须同步另一处；
  3. 「三类钉定/校验互不覆盖」表格下补一句 `api.github.com` digest 属「同源一致性校验」而非来源认证。
- `CODE_WIKI.md` / `CODE_WIKI_EN.md` 更新日志各追加本次变更（含 S1/S2/S3 与真机验证结论）。
- `README.md` / `README_EN.md`：发布产物清单加 `linux-aarch64`，Docker 章节加 `ghcr.io` 拉取方式。
- `.dockerignore` / `.gitignore` 同源核对：已实测**无需改动**——`.dockerignore:55` 的 `PROPOSAL_*.md`
  是无分隔符的按名模式（对任意层级生效，同目录的 `PROPOSAL_2026-09-22_binary-trust-policy.md` 即先例），
  `.gitignore:280` 已写明该前缀属正式记录、刻意不忽略。本次沿用前缀，故 AGENTS.md「镜像额外排除集」条目不动。
- i18n：新日志文案一律 `i18n.tr(模板, **kw)`，模板补进 `zh_CN.po`/`en_US.json`/`en_GB.json`/`zh_TW.yaml`
  四目录并重编 `.mo`（`test_runtime_templates_covered_by_catalog` 是硬门禁，漏补当场红）。

## 八、交回用户的验证项（代理权限/环境之外）

1. **arm64 runner 是否计入免费额度**：首次 `v*` tag 或手动跑 build-release 才知道；若配额不足，
   退化方案是矩阵保留 linux-arm64 但仅在 `workflow_dispatch` 下启用（需另行批准）。
2. **GHCR 包可见性设为 public**：一次性人工动作（Actions 不会代为放开）。
3. **端到端真机验证（DoD 第 2 步）**：本机 Windows x64 无法产出也无法运行 arm64 冻结产物；
   能做到的替代是①`tests/test_ffmpeg_linux_download.py` 全绿 + ②CI 首跑的 arm64 job 冒烟读数 +
   ③一次真实 arm64 容器内录制跑通。③ 由用户在 arm64 主机执行，届时按 DoD 口径记「未执行 + 原因」。

## 九、回滚方案

三段互相独立，任一段可单独回退且不留半拉子状态：
- S1 回滚 = 删矩阵新增的 `- os: ubuntu-24.04-arm` + `platform: linux-arm64` 条目（一律按 `os` 标签点名、**不按序号**定位：
  它与 `AGENTS.md`「CI / workflow 约定」·「发布矩阵为四平台」条目所述「插在 `ubuntu-latest` 之后」同一口径）
  + `RUNNER_TO_RUNTIME_KEY` 对应条目 + 两个 `if:` 条件与 `-lt 8` 还原；
  钉定表里的 `linux-arm64` 段**保留**（`check_runtime_pins` 对矩阵外键只告警，不拦发布）。
  [历史注] 本条原写「删矩阵第 4 项」（把「第 4 个平台」误当成 `matrix.include` 的项序）；2026-10-03 评审核实
  `build-release.yml:258-265` 后更正——arm 条目排在 `macos-latest` **之前**，照原字面执行会删错平台（macOS）。
- S2 回滚 = 新模块整体删除 + `install_ffmpeg_linux()` 去掉那一行调用 + T-3/T-4/T-5 还原，**并且必须一并还原
  「`apt update` 非零即在 apt 块内 `return False`」的早退与 `apt install` 的 `else:` 嵌套**——接线轮把该早退删掉了
  （改落函数末尾统一出口），只删那行调用会留下「update 失败仍经过兜底」的行为差，不等于回到改动前形态。
  Windows/macOS 路径从未被改动，无连带影响。
  [历史注] 本条原写「S2 回滚 = 新模块整体删除 + `install_ffmpeg_linux()` 去掉那一行调用 + T-3/T-4/T-5 还原」，
  2026-10-03 由接线修复轮（Unit B Fix round 2，评审 Important-1）证伪后按实况更正。
- S3 回滚 = 删 `docker-publish.yml` 一个文件；compose 与 Dockerfile 未动，镜像构建语义回到「本地自构建」。
