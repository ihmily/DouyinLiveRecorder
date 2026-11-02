# PROPOSAL_2026-10-03 — Linux arm64 ffmpeg 批次：代理裁定记录与交回清单

> **文档性质**：本次「Linux arm64 ffmpeg 支持」批量改动（5 个派发单元 + 最终全分支评审）里，
> 代理在无人逐项确认的情况下**替你做出的决定**，以及**必须由你处置才能闭合**的开放项。
> 前者的价值是「判错了你可以直接推翻并复现」，后者的价值是「没有任何一条被我当作已完成」。
> **命名沿用既有 `PROPOSAL_*.md` 前缀**（`.dockerignore:55` 按名排除、`.gitignore:280` 登记为正式记录、
> `AGENTS.md`「镜像额外排除集」条目同源），不新增前缀即不触发「换前缀三处同改」。
> **事实源边界**：约束本体在 `AGENTS.md`，规格在 `PROPOSAL_2026-10-02_linux-arm64-ffmpeg.md`，
> 实现分解在 `PROPOSAL_2026-10-02_linux-arm64-ffmpeg-plan.md`，本文只记决策与待办，不复述判定逻辑。
> **取证日期**：2026-10-02 ~ 2026-10-03，Windows x64 本机。全部读数可在本文末「复现命令」一节重跑。

---

## 一、我替你做的决定（R-1 … R-17）

流程依据：SDD 的 continuous-execution 规则规定「运行中的计划不等人」——冲突、歧义、计划缺陷由控制方
以规格为权威裁定并留痕。下面每一条都是这么产生的，**没有一条是静默发生的**。

| # | 裁决 | 依据 | 判错的代价 | 落点 |
| --- | --- | --- | --- | --- |
| R-1 | 用「派发前文件快照 → 派发后逐字节 diff」替代 SDD 默认的 `BASE..HEAD` 提交区间评审包 | 用户 2026-10-02 指令「在当前状态上开工，不提交」优先于 skill | 快照若漏记某文件，评审看到的差异面偏小；由单元报告补全 | 账本 `progress.md` 抬头 |
| R-2 | 计划 Task 2/3/5 合并为一次派发（同一对文件 `src/ffmpeg_linux_download.py` ↔ `tests/test_ffmpeg_linux_download.py`） | Task 5 只是 Task 2 的重构 + 追加锁；拆三次会让同一文件被三个新鲜上下文各读一遍 | 单次派发体积大；实现者若卡住需按 rounds 再拆 | 账本 Unit A 段 |
| R-6 | **计划缺陷修正**：把 Task 4 的 Step 3（`DOWNLOAD_SOURCES`/`DOWNLOAD_MODULES` 两处登记）提前并入 Unit A | `tests/test_ffmpeg_install.py` 的白名单锁是**双向**的（`test_no_other_module_reaches_a_download_host`），按计划原顺序执行会在 Unit A 收尾留一条红锁 | 计划文本与实际派发边界不再一一对应；已在计划末尾回写 | 计划「实现期裁定回写」段 |
| R-4 | `if: "!startsWith(matrix.platform, 'linux')"` 采纳**加引号**形态 | 评审与实现者分别实测：无引号时 YAML 把行首 `!` 当 tag 指令，直接 `ParserError`；加引号后 Actions 求值语义不变 | 几乎无代价，是更安全的形态；若 GitHub 未来改变 plain scalar 解析，此处仍是可用形态 | `build-release.yml:380` + `AGENTS.md` CI 条目 |
| R-5 | 既有用例 `test_real_matrix_parser_rejects_unregistered_runner_tag` 的合成样本标签 `ubuntu-24.04-arm` → `ubuntu-24.04-arm64` | Step 2 把该标签登记进映射后，原样本必然不再是「未登记标签」，用例语义反转 | 若将来真出现 `ubuntu-24.04-arm64` 这一标签，守卫会明确变红（预期行为，非静默失效） | `tests/test_check_runtime_pins.py` |
| R-7 | `_digest_from_assets` 删掉 `.strip().lower()`：形状关 `^[0-9a-f]{64}$` **只认小写** | brief 内部自相矛盾（带 `.lower()` 的代码 vs「大写 `E*64` 应算取不到」的用例），实跑用例真红；规格 §4.2 与 `build_exe._is_pinned` 是同一条形状判据 | 上游若改发大写 digest，会被判「取不到」→ 走 TOFU 降级分支（fail-closed 且可观测，不是放行） | `src/ffmpeg_linux_download.py` |
| R-8 | `[tool.mypy].exclude` 里的裸 `"ffmpeg"` 是**路径子串**正则，使全仓 `src/ffmpeg_*`、`tests/test_ffmpeg_*` 对「不带路径的 mypy」门禁失明；本轮**不改** `pyproject.toml`，改跑「显式传参 mypy + basedpyright」代偿 | 实测：新增这两个文件前后无参 `mypy` 同为 189 source files；加入一个名字不含 `ffmpeg` 的测试文件后变 190 | 「mypy 全绿」不得当作这批文件的类型门禁证据；改 exclude 形态 = 全仓 ffmpeg 系首次进门禁、必一次性暴露存量错误 ⇒ 属独立工作包，见本文 §二.5 | `AGENTS.md`「已知坑 · 类型检查」 |
| R-9 | `_install_binaries` 由「边找边拷」改为**两趟**（先全量递归定位 `ffmpeg`/`ffprobe`、缺件即返回且 dest 侧零改动；两件齐了才 mkdir + copy + 补执行位） | 评审锁 I-1⑤ 要求「缺 `ffprobe` 不得留下半截安装」，单边形态下该锁恒假 | 计划 Task 3 的单边版文本已被证伪；**任何人复原它就静默废掉那条锁**，且 `dest/ffmpeg/` 空壳会变成「装过了」的假证据 | `AGENTS.md`「已知坑 · 构建产物」 |
| R-10 | 执行位（`chmod \| S_IXUSR`）判据判为 **Linux CI 承载**，本机不伪造 mode 断言 | 实测 Windows 宿主上 tar 成员 mode 恒回 `0o666`、chmod 后 `S_IXUSR` 不回报；删掉 `chmod` 整行 46 条用例全绿 | 合并边界若要自证需 CI 首跑读数；本机唯一合法闭合路子是加「`Path.chmod` 以含 `S_IXUSR` 掩码被调用」的行为锁（属增补，未做） | 账本 Unit A 段 |
| R-11 | `install_ffmpeg_linux()` 中「`apt update` 失败即在 apt 块内 `return False`」的早退**删掉**，改落函数末尾统一出口 | 无 root 的 Debian/Ubuntu arm64 上 `apt update` 要写 `/var/lib/apt/lists`、失败是常态，而这类机器正是本模块声明的目标人群；评审探针实测该支兜底触达次数 0→1 | 牵动两条既有用例（`tests/test_ffmpeg_install.py:304`/`:1084` 一带），二者断言已由评审逐条复验仍被真实断言；**S2 回滚时必须连同 `else:` 嵌套一起还原才等价**（规格 §九 已更正） | `src/ffmpeg_install.py:556-570` |
| R-12 | brief Step 1 第三条用例判为「名字与实现相反」的零敏感弱锁，处置为**改判据成真锁**而非删除 | 它给 `apt update` 非零，而修复 R-11 之前那条分支根本到不了接线位置 | 若按「删掉」处置，会把一条真实存在的判据连带消失；现它随 R-11 变异一起红 | `tests/test_ffmpeg_install.py` |
| R-13 | 结构锁入参名 `platform` → `platforms`（**收紧**，不是放宽） | 实现者查 `docker/build-push-action` 的 `action.yml`：只有 `platforms`，无 `platform` 键；评审独立 curl v6 复核同结论 | 无代价；原写法会让锁永假 | `tests/test_docker_publish_workflow.py` |
| R-14 | docker 第三方动作保持浮动大版本 `login-action@v3` / `setup-buildx-action@v3` / `build-push-action@v6`，**不抬版** | MIN-17 的区分线：本链触发源是维护者推的 `v*` tag（可信输入），与 `softprops/action-gh-release@v3` 同线；三个标签实测可解析。评审判为「可接受的人工闸口」 | 上游已发 v7.4.0 / v4.6.0 / v4.4.1，本链不会自动跟进；抬版只需改 3 处 `@` 后缀，结构锁不钉版本号（已用变异坐实） | `AGENTS.md` CI 条目 + 账本 |
| R-15 | 新锁对三种**语义等价**改写刻意判红（`with.tags` 写成 YAML 列表、`provenance` 写成字符串 `"false"`、`create` 命令加带值选项如 `--builder NAME`），**不放宽**，改为在测试里写明「刻意严格」 | 放宽这三种形态要引入 shell 词法之外的选项语义解析，复杂度与收益不匹配；误报方向是噪声，假绿方向才是事故 | 未来有人按等价形态重写工作流会被锁拦下并要求显式适配；已登记 `AGENTS.md` 结构锁条目 | `tests/test_docker_publish_workflow.py` 常量段与三处注释 |
| R-16 | provenance 注释的两处精度瑕疵与报告两处不实陈述，按「被证伪的事实改原文 + 一行带日期历史注」更正 | 复核者独立取证：attestation 是 index 里一支 `platform=unknown/unknown` + `artifactType` 的 manifest（mediaType 本身合法）；`mode=min` 是 BuildKit 层默认，动作对公开仓库注入 `mode=max`；`inputs.attests` 在 v6/v7 都存在 | 若不改，注释会给出一个错误的可复核判据（本仓硬禁：写了就得能被推翻） | `docker-publish.yml:107-124`/`:162-172`、`unit-6-report.md` |
| R-17 | 一处**纯注释/文档**轮次用等价性自证（`yaml.safe_load` 前后 deep-equal、变更行全为注释、12 passed）代替再派一名独立复核者 | 偏离 SDD「每轮必限定范围复核」，为省两个子代理往返 | 若那轮注释里藏了行为改动而自证没抓到，会漏过一道闸；最终全分支评审补做了同源核验，未发现问题 | 账本 Unit 6 段 |

另有两项**默认按你的指令执行、未另立裁决**：全程零 `git add`/`commit`/`stash`/`checkout`/`clean`；
`docker-compose.yaml` 的 `image: ihmily/douyin-live-recorder:latest` 按规格 §二.4 刻意未改（GHCR 发布名与
compose 拉取名不同源是分工，compose 用户走 `pull_policy: build` 就地构建，在 arm64 主机上本就成立）。

---

## 二、需要你处置（按急迫度）

### 1. 索引混提交风险（最急，且只有一句话的动作）

**现象**：本批 21 个文件（新模块、两个新测试、`docker-publish.yml`、规格/计划、i18n 五件、`AGENTS.md`、
`CODE_WIKI*`、`README*`、`.gitignore`/`.dockerignore`/`pyproject.toml`/`scripts/check_annotations.py` 等）
在**我方全程零 `git add`** 的前提下被某个外部进程持续 stage 进索引，状态呈 `A`/`AM`/`MM`。
与你原有的 82 个在途文件**同处 staged**。

**为什么不能我定**：`git restore --staged` 只动索引、不动工作区，看似安全，但它会改写**你**的暂存意图，
而我无法判断那些 stage 是谁、为何而做。

**建议动作**（三选一，告诉我编号即可）：
- ① 我把本批文件逐个 `git restore --staged` 出去，你的 staged 集合回到我介入前的形态；
- ② 你先自行处置那 82 个文件（提交或整理），本批留待其后单独成提交；
- ③ 保持现状，明确接受「一次 commit 混两批」。

**核验方式**：`git diff --cached --name-only`（本批新模块在列即未处置）。

### 2. 并行工作流仍在写同一仓库

期间观察到 `main.py`、`src/spider.py`、`StopRecording.vbs`、5 个 i18n 目录被改写，并新增未跟踪
`tests/test_douyu_url_resolution.py`；`.po` 在 03:56 被追加虎牙/斗鱼 msgid 而未重编 `.mo`
（我按其 prescribed 命令跑了 `compile_po.py`，`.mo` 属可再生派生产物）。
**影响**：并发 pytest 会放大本文 §三 的环境噪声归因难度。
**需要你定**：两批工作是否要在同一工作区继续并行；若继续，收尾门禁的归因口径要不要改成「按文件集分包跑」。

### 3. `ubuntu-24.04-arm` 的额度归属未证实

我已核实该 runner 标签**存在**（actions/runner-images README 第 26 行「Ubuntu 24.04 Arm64 / `ubuntu-24.04-arm`」），
但**是否计入本账号的免费额度没有查到官方口径**。
**你来做**：首跑 `v*` tag（或手动触发 build-release）确认；若额度不足，退化方案是矩阵保留 linux-arm64 但仅在
`workflow_dispatch` 下启用——这条**需要另行批准**，我不自行开这个口子。

### 4. GHCR 包可见性（一次性人工动作）

匿名 `docker pull` 需要把 package 设为 **public**，而 Actions 的 `GITHUB_TOKEN` 不会代为放开。
不设则 `README` 里新增的 ghcr 拉取方式对未登录用户是坏的。

### 5. 两个我刻意没开的「顺手修」工作包

- **mypy exclude 形态（R-8）**：把 `[tool.mypy].exclude` 的裸 `"ffmpeg"` 锚定成目录形态，收益是全仓
  `ffmpeg_*` 首次进 mypy 门禁，代价是**必然一次性暴露存量错误**。属独立工作包，等你决定要不要开。
  **[2026-10-03 状态更新] 已开工落地**：`"ffmpeg"` 与 `"node"`（枚举新发现的同族误伤）双双锚定为
  `(^|/)<名>/`，12 个失明文件进无参门禁、新暴露 8 处存量错误已修，语义回归锁 +
  变异验证落 `tests/test_run_gates.py`；读数与判据见 CODE_WIKI 同日条目与 AGENTS.md 改写后的对应已知坑。
- **arm64 full 包体积读数**：`AGENTS.md` 明文「体积结论只以本机实跑为准，不估算」，而本机是 Windows x64，
  产不出也跑不了 arm64 冻结产物 ⇒ 需 CI 首跑后用 `scripts/report_bundle_size.py` 取数再回填文档。

### 6. DoD #2 端到端真机验证：未执行（如实登记）

本机无法产出也无法运行 arm64 产物。已做到的替代证据：① 活体取数（API digest 与钉定值逐字相等）；
② 48 条离线行为锁 + 13 条工作流结构锁；③ 覆盖率门禁 46 模块达标。
**未做**：arm64 真机上「非 root + apt 在位使 update 失败」与「yum/apt 皆缺」两条分支的真实录制跑通、
GHCR 首推与多架构 `docker manifest inspect` 读数。**交回动作**：由你在 arm64 主机或 CI 首跑后执行，
届时按 DoD 口径写进 `CODE_WIKI.md`/`CODE_WIKI_EN.md` 更新日志。

---

## 三、门禁终态读数（最终修订之后执行）

| 命令 | 结果 |
| --- | --- |
| `python -m black --check .` | 206 files unchanged（`.superpowers/` 已登记排除，不再被扫进仓库面） |
| `python -m isort --check-only .` | rc=0，Skipped 16 files |
| `mypy`（不带路径） | Success: no issues found in 193 source files |
| `python -m mypy src/ffmpeg_linux_download.py tests/test_ffmpeg_linux_download.py tests/test_docker_publish_workflow.py` | rc=0（R-8 的显式代偿） |
| `python scripts/check_coverage.py` | **PASSED: All 46 module(s) meet coverage threshold**；新模块 `src/ffmpeg_linux_download.py` 93.8%（195 stmts / 12 miss）、`src/ffmpeg_install.py` 96.4% |
| `PYTHONUTF8=1 python scripts/compile_po.py --check` | 同步（858 条） |
| `PYTHONUTF8=1 python scripts/check_annotations.py` | 203 files，悬空引用 0，平均密度 24.3% |
| `python scripts/check_skill_agents_consistency.py` / `check_version.py` / `check_runtime_pins.py --strict` | 全 rc=0 |
| 全量 `pytest -q --cov=src` | 3957 passed / 15 skipped / **21 failed** |

**21 条失败的归因**（这是本批最需要自证清白的一处）：全部落在 6 个会真起子进程的测试文件——
`test_build_exe`、`test_ci_retry_action`、`test_notify`、`test_notify_script_guard`、
`test_regression_standalone`、`test_stop_recording_vbs`。逐族串行/单跑复验全部转绿
（105 / 71 / 41 / 17 passed），实测失败原因统一是 `OSError: [WinError 6] 句柄无效`；
本批未改动其中任何被测对象（`StopRecording.vbs` 的 `M` 属并行工作流）。
两轮全量运行的失败数与集合漂移（30 → 21），本身即环境噪声的签名而非确定性代码失败。
`AGENTS.md` 已登记同族判据（「探测子进程输出一律按字节比较」「本机全量 pytest 偶发段错误属环境噪声」）。

**未做**：`python scripts/run_gates.py` 端到端复跑（其 10 条已逐条单独跑过，见上表）。

---

## 四、复现命令

```bash
# 1. 索引混提交现状（§二.1）
git diff --cached --name-only | grep -E "ffmpeg_linux|docker-publish|PROPOSAL_2026-10-0[23]"

# 2. 发布矩阵与运行时键的同源（R-4/R-5）
python scripts/check_runtime_pins.py --strict; echo rc=$?
python -m pytest tests/test_check_runtime_pins.py -q

# 3. 运行期完整性真值表与两处 URL 副本一致性（R-7/R-9）
python -m pytest tests/test_ffmpeg_linux_download.py -q -W error
python - <<'PY'
import build_exe, src.ffmpeg_linux_download as fld
for k, key in (("linux64", "linux-x64"), ("linuxarm64", "linux-arm64")):
    d = fld._fetch_asset_digest(fld._LINUX_FFMPEG_URLS[k])
    print(k, d == build_exe._PINNED_RUNTIME_SHA256[key]["ffmpeg"], d[:12])
PY

# 4. 接线顺序与开关传参（R-11/R-12）
python -m pytest tests/test_ffmpeg_install.py -q -W error
grep -n "install_ffmpeg_linux_native" src/ffmpeg_install.py

# 5. 镜像发布链结构锁（R-13/R-14/R-15）
python -m pytest tests/test_docker_publish_workflow.py -q -W error

# 6. 环境噪声归因复核（§三）
python -m pytest tests/test_run_gates.py -q --tb=short   # 失败原因应含 WinError 6
python -m pytest tests/test_build_exe.py -q              # 串行单跑应全绿
```

## 五、留痕位置

- 账本（17 条裁决全文、修复轮逐轮读数、deferred minor、parked 项）：
  `/tmp/sdd-arm64-ffmpeg/progress.md`（工作区副本，仓库内 `.superpowers/` 已删除）
- 五份单元报告 + 五份单元评审 + 一份最终全分支评审：同目录 `unit-*.md`、`task-1-*.md`、`final-review.md`、
  `fix-wave-report.md`
- 规格与实现计划：`docs/worklog/PROPOSAL_2026-10-02_linux-arm64-ffmpeg.md`（含 §九 回滚方案）、
  `docs/worklog/PROPOSAL_2026-10-02_linux-arm64-ffmpeg-plan.md`（含「实现期裁定回写」段）
- 当日运行日志与可复用判据：`.workbuddy/memory/2026-10-03.md`、`docs/agent-reference/session-learnings.md`
