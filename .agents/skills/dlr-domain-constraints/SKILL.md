---
name: dlr-domain-constraints
description: >-
  DouyinLiveRecorder 录制与发布链路的领域硬约束（选源 → ffmpeg 命令构造 → 发布期运行时二进制钉定）。
  当修改平台解析函数、选源/探针流程、画质映射、ffmpeg 录制命令与容器格式映射、保存类型分支、
  build_exe.py 的运行时钉定哈希或下载源、check_runtime_pins.py 时使用此 Skill。
trigger:
  - select_source_url
  - stream_select
  - 探针
  - probe
  - FLV-first
  - HLS 排除
  - 画质映射
  - QUALITY_MAPPING
  - _validate_stream_url
  - _PROBE_BACKOFF_PLATFORMS
  - _FLV_FIRST_PLATFORMS
  - trace_error_decorator
  - ffmpeg
  - -reconnect
  - -segment_format
  - -thread_queue_size
  - _build_ffmpeg_input_args
  - _build_ffmpeg_output_args
  - _build_record_output_path
  - _run_ffmpeg_record
  - _convert_after_record
  - record_save_type
  - 容器格式
  - FLV
  - TS
  - MP4
  - M4A
  - MKV
  - _PINNED_RUNTIME_SHA256
  - --require-pinned
  - check_runtime_pins
  - ffmpeg 下载
  - node 下载
  - TOFU
  - GPG 验签
  - _is_pinned
  - _slot_is_gated
  - _RUNTIME_GPG_SIGNATURES
  - DLR_RUNTIME_SHA256
  - releases/tags
agent_created: true
---

# DLR 领域硬约束（选源 → 录制执行 → 构建发布）

## 本轮合并（2026-10-29）

本 Skill 是 2026-10-29 同类合并的归并结果。以下源能力的完整 playbook 已收编进本目录，按需加载 `references/<name>/SKILL.md`，不要把全部参考文档读进上下文：

- `js-signature-pin-byte-parity` → `references/js-signature-pin-byte-parity/SKILL.md`

被吸收源技能的 frontmatter 仅在其原子文档内作历史留存；本目录的 `name` 与路由表为准。跨组的兄弟能力引用见各参考文档内的重定向注。

## 定位

本 Skill 是 DouyinLiveRecorder **领域约束面**的单一入口，由原 `ffmpeg-command-construction`、
`platform-source-selection`、`runtime-pin-verification` 三个同构 Skill 合并而成——三者都只是
`dlr-dev-playbook/references/known-pitfalls.md` 的不同切片，frontmatter、路由表与验证模板逐字同构，
拆成三份的代价是「跨段改动要连开三份文件、验证清单被复制六遍」。合并后按链路分段路由，一次加载。

- **约束事实源仍是 `AGENTS.md`**；本 Skill 与它冲突时以 `AGENTS.md` 为准。
- 扩展论证与事故考古在 dlr-dev-playbook `references/known-pitfalls.md`；本 Skill 只做高频复用的提炼。
- 工作流（设计、测试写法、日志分诊、静态检查裁定、CI、打包流程）走 `dlr-dev-playbook`，不在本 Skill。
- **按需加载**：命中路由表后只读取对应的那一个 `references/*.md`，不要把 12 份全读进上下文。

## 三段链路与各自的硬约束

链路方向：`spider.py` 解析 → `stream_select.py` 选源/探针 → `main.py` ffmpeg 录制 → `build_exe.py` 发布。
改任一段都要意识到下游段把上游输出当契约消费。

### 段一：选源与画质映射

- **探针不用 HEAD 定罪**：CDN 对 m3u8 的 HEAD 常回 4xx 而 GET 能拉流；HEAD 非 2xx 一律回落 Range `GET bytes=0-0`。
- **末位候选只告警放行**：候选已是最后一条时，稳定拒绝也交给 ffmpeg 定夺；删掉这条会重引「探针误杀可用源」。
- **探针节流与抖动不可改成固定值**：`_PROBE_MIN_HOST_INTERVAL=0.35s` + 抖动、`_recheck_delay=0.8s+uniform(0,0.7s)` 是反风控指纹；测试侧用 autouse fixture 置 `_throttle_probe` 为 no-op，不要改生产常量。
- **`_FLV_FIRST_PLATFORMS` 只是调序**（FLV 排到 HLS 前、HLS 仍留作回退），**「HLS 采集排除平台」是整组剔除**——两种语义不可互实现。斗鱼绝不可进 FLV-first 名单（游客态 FLV ~70s 被掐），虎牙必须 FLV-first 且是唯一进探针退避名单的平台。
- **画质档位**：OD/BD/UHD/HD/SD/LD = 0..5；蓝光子档位（BD4/8/20/30）折叠到 BD 索引、靠 `BD_SUB_TIERS` 承载，**不得塞进 `QUALITY_MAPPING`**。
- **解析函数返回契约**：返回 dict 用 `trace_error_decorator`、返回 str/tuple/None 用 `trace_error_decorator_or_none`；**装饰器与 `def` 之间不得有注释**（会把装饰器绑到下一个 `def`）。JSON 解析走 `_loads_dict` 兜底、不再抛 `JSONDecodeError`。

### 段二：ffmpeg 命令构造与容器格式（F-01 收官）

禁止回退成内联复制粘贴。所有平台分支必须经过以下四个单一定义点：

1. **输入侧** `_build_ffmpeg_input_args(real_url, user_agent, tuning, headers, tls_verify, proxy_address)`——所有选项按 `-i` 锚点定位或插列表头，**禁裸数字下标**。
2. **输出路径** `_build_record_output_path(...)`——扩展名 / 分段时间戳格式 / `_%03d` / `_%02d` 全查表。
3. **执行骨架** `_run_ffmpeg_record(...)` + 录后转码 `_convert_after_record(...)`——五条保存类型分支只调这三个函数，禁各自写 try/except + check_subprocess。
4. **平台分发** `_PLATFORM_RESOLVERS`（`(匹配器, 处理函数)` 表）+ `_PlatformResolveContext`——表项顺序即优先级，**禁插 elif**。

配套硬约束：

- `-reconnect*` **必须在 `-i` 之前**且每个选项紧跟取值；写在 `-i` 之后会被划入输出组，ffmpeg 静默接受但不应用。
- **HLS 输入必须移除 `-reconnect_at_eof`**（m3u8 响应结束即 EOF，该选项让 hls demuxer 永远等不到媒体段）。
- `-thread_queue_size` **只能在 `-i` 之后**（放错侧 → `Option ... cannot be applied to input url` → 退出码 -22 → 录制 100% 失败）。
- `-segment_format` **必须经 `SEGMENT_FORMAT_BY_SUFFIX` 查表**（`.ts→mpegts` / `.flv→flv` / `.mkv→matroska` / `.mp4→mp4` / `.m4a→ipod`，音频兜底 `ipod`）；TS 分支误写 `ipod` 会让 HEVC `-c copy` 直接 `EINVAL` 退出，H.264 则不报错 exit 0 但静默损坏。
- **录制结果反馈**：`check_subprocess` 按 ffmpeg 退出码分别上报 `record_success` / `record_error`，**禁止轮末无条件 `record_success`**（稀释按 host 熔断统计）；快速失败调 `stream_select.mark_ffmpeg_reject`、成功调 `clear_ffmpeg_reject` 且**只清实际拉流成功的 FLV**。

### 段三：发布期运行时二进制（SEV-10，fail-closed）

四层防线，缺一层即视为未防线：

1. **钉定哈希**：`build_exe.py::_PINNED_RUNTIME_SHA256`（按 `<os>-<arch>` × ffmpeg/node 分列）。「已钉定」唯一判据是 `_is_pinned()` 形状 **64 位小写十六进制**，占位/空串/截断一律未钉定。**不得为让 CI 绿回填本地自算哈希**（那是固化「构建机已中毒」）。
2. **强制校验门**：`--require-pinned`（CI 因 `GITHUB_ACTIONS=true` 自动开），缺钉定即在下载前 `SystemExit`（继承 `BaseException` 吞不掉）；`slot` 是必填关键字参数，漏传会静默降级为无校验下载。
3. **静态校验脚本**：`scripts/check_runtime_pins.py`（`--strict` 由 build-release.yml prepare job 执行），表为空/缺平台/缺槽位一律 rc=2。「算满足」两档的唯一口径是 `build_exe._slot_is_gated()`：64 位十六进制官方哈希 ∨ 官方签名档（取值 `OFFICIAL_SIGNATURE_PIN` 且该槽在 `_RUNTIME_GPG_SIGNATURES` 确有登记、指纹 40 位十六进制）。**标记本身绝不构成放行**。
4. **在线来源层**（`--pin-source` / `DLR_RUNTIME_PIN_SOURCE`，build_exe 默认 `off`）：`verify` 拉官方清单只与内置表比对、永不写入；`adopt` 把在线值升格为本次判据，准入两条路（`_pin_source_is_adoptable`）：`trust=signed` 须**清单验签通过**（钉定 40 位主钥指纹，node）；`trust=advisory` 须该槽**逐条登记** `ADVISORY_ADOPT_ACK` 放行标记（[2026-11-01 用户批准] windows/linux ffmpeg——上游不发布签名，判据 = 当日官方清单值，linux 随最新月末 autobuild 标签同源解析下载直链）。**发布路径（build-release.yml）以 `--pin-source adopt` 运行**，静态表退为 off 档回退基线（windows 回退后滚动产物对旧哈希失配即 fail-closed；linux 回退 = 旧月末标签整对，版本滞后但带外可验）。未登记标记的 advisory 槽位维持「永不 adopt」——同源取哈希比对等于安全剧场，新增 advisory 槽位必须先经人工评估再登记标记，不得全局开关。在线拉取或验签失败一律回退静态表。

三类钉定互不覆盖（发布期运行时 / 运行期自动安装 TOFU / 签名脚本层 `_JS_SHA256_EXPECTED`），任何新增「远程获取并执行的代码」必须落入其中之一。

## 路由表

| 段 | 子主题 | 文件 | 触发场景 |
|---|---|---|---|
| 选源 | 探针可达性校验与节流 | [`references/source-probe-reachability.md`](references/source-probe-reachability.md) | 改探针逻辑、HEAD/GET 流程、节流抖动、UA 一致性、退避撤销 |
| 选源 | 平台专属选源约束 | [`references/source-platform-selection.md`](references/source-platform-selection.md) | 虎牙/斗鱼选源规则、FLV-first 调序、HLS 采集排除 |
| 选源 | 画质档位映射 | [`references/source-quality-mapping.md`](references/source-quality-mapping.md) | 通用画质映射、蓝光子档位、虎牙选档、斗鱼本地重试链 |
| 选源 | 平台解析函数返回契约 | [`references/source-parser-contract.md`](references/source-parser-contract.md) | 装饰器选择、JSON 解析兜底、`_loads_dict` 行为 |
| 录制 | `-reconnect*` 与 `-thread_queue_size` 位置 | [`references/ffmpeg-reconnect-constraints.md`](references/ffmpeg-reconnect-constraints.md) | 改重连参数、thread_queue_size 位置、HLS 输入处理 |
| 录制 | `-segment_format` 查表与容器格式 | [`references/ffmpeg-segment-format-lookup.md`](references/ffmpeg-segment-format-lookup.md) | 改分段格式映射、容器格式、扩展名查表 |
| 录制 | 录制结果反馈 | [`references/ffmpeg-recording-feedback.md`](references/ffmpeg-recording-feedback.md) | 改录制成功/失败上报、探针退避交互 |
| 录制 | 黄金命令比对 | [`references/ffmpeg-golden-command-comparison.md`](references/ffmpeg-golden-command-comparison.md) | 改 ffmpeg 命令构造逻辑、更新黄金基准 |
| 发布 | 官方签名档 | [`references/pin-official-signatures.md`](references/pin-official-signatures.md) | 改签名验证逻辑、GPG 验签流程 |
| 发布 | macOS 取数端点约束 | [`references/pin-macos-endpoints.md`](references/pin-macos-endpoints.md) | 改 macOS ffmpeg 下载源、evermeet 端点 |
| 发布 | Linux 取数端点约束 | [`references/pin-linux-endpoints.md`](references/pin-linux-endpoints.md) | 改 Linux ffmpeg 下载源、月末标签 |
| 发布 | 三类钉定边界与来源增删 | [`references/pin-categories.md`](references/pin-categories.md) | 新增/删除下载源、TOFU 基线、钉定分类 |

## 验证

### 项目级门禁（统一入口，Skill 不复制命令清单）

唯一入口：`python scripts/run_gates.py`（仓库根目录执行）。black/isort/mypy/check_annotations 的
命令清单以 `AGENTS.md`「格式化命令（门禁唯一基准）」为唯一事实源——本 Skill 只引用不复制
（dlr-dev-playbook 铁律 4：复制清单会制造并行事实源并在 `AGENTS.md` 更新后静默漂移）。
退出码：`0` 通过 / `1` 门禁红 / `2` 清单缺失或含写型命令 / `3` 可执行文件缺失；后两者属「没跑」，不是回归。
需要逐条命令时用 `run_gates.py --list` 现场解析。

### 命中段的专项检查（只跑命中的那一组）

**选源段**（改 `src/stream_select.py` / `src/stream.py` / `src/spider.py` / 新增平台）：

```bash
pytest tests/test_stream_select.py -v      # 选源流程
pytest tests/test_stream.py -v             # 画质映射
pytest tests/test_spider.py -v             # 平台解析函数
pytest tests/test_spider_hardening.py -v   # JSON 兜底（裸 json.loads 棘轮）
pytest tests/test_platform_dispatch.py -v  # 平台分发
```

**录制执行段**（改 `main.py` 的 ffmpeg 构造 / 保存类型分支 / 容器格式）：

```bash
pytest tests/test_ffmpeg_reconnect_args.py -v
pytest tests/test_record_container.py -v
pytest tests/test_start_record_command_golden.py -v
pytest tests/test_platform_dispatch.py -v
pytest tests/test_record_failure_feedback.py -v
```

外加两条跨平台 AST 检查（预期均输出 `OK`、退出码 0）：无 `-reconnect*` 出现在 `-i` 之后、无 `-segment_format` 裸字面量。

```bash
python -c "import sys,re; c=open('main.py',encoding='utf-8').read(); m=re.search(r'-i.*-reconnect',c,re.DOTALL); print('FAIL' if m else 'OK'); sys.exit(1 if m else 0)"
python -c "import sys,re; c=open('main.py',encoding='utf-8').read(); m=re.findall(r'-segment_format\s+\w+',c); print('FAIL' if m else 'OK'); sys.exit(1 if m else 0)"
```

**构建发布段**（改钉定哈希 / 下载源 / `check_runtime_pins.py` / 安装器 TOFU）：

```bash
python scripts/check_runtime_pins.py --strict   # rc=0
pytest tests/test_build_exe.py -v               # 钉定/签名/主机白名单/不可变标签
pytest tests/test_ffmpeg_install.py -v          # TOFU/下载源白名单
```

外加配置检查（预期均输出 `OK`）：`tests/test_build_exe.py::_ALLOWED_HOSTS` 仍存在（退役主机已移出）、全文无 `releases/latest` 路径。

### spider.py 变更的强制回归（MUST）

改动 `src/spider.py` 任一 `get_*_stream_data` / `get_*_stream_url`（含新增平台、调整返回字段、修改签名/重试/回退分支）时，
上方三个专项段（含公共的 `test_platform_dispatch.py`）**全部必须运行**，不得只跑与被改平台同名者。

**Why**：`spider.py` 的输出结构（`m3u8_url` / `flv_url` / `record_url` / `play_url_list`）直接作为 `stream_select.py`
的候选列表进入选源/探针链路；候选数量、字段可用性、URL host 形态任一变化都会穿过 `_FLV_FIRST_PLATFORMS`、
`_PROBE_BACKOFF_PLATFORMS`、`_validate_stream_url`、`_throttle_probe` 与末位放行分支走一遍新路径。故单平台改动仍需
覆盖三个横向面：平台分发、探针/选源、JSON 兜底。

**执行面**：本约束**不新增** CI 路径过滤或专属 pre-commit hook——dlr-dev-playbook `references/ci-workflow.md`
与 ci.yml 头注已定「`workflow_dispatch` 场景下 `dorny/paths-filter` 会造假绿、过滤器已整体移除」。CI 侧的真实兜底为
`test` job 的全量 `pytest --cov=src`，配合 `scripts/check_coverage.py` 的阈值与 `test_platform_dispatch.py` 的收集锁；
本 Skill 的职责是让开发者**显式确认各段都跑过**，不另立第二份门禁。

## 常见误用（Red Flags）

- 新写 ffmpeg 选项时不看 `ffmpeg -h full` 分段标题就猜 input 级 / output 级。
- 把 `-reconnect*` 追加到命令尾部（`-i` 之后）——静默失效，无报错。
- 为「省事」在保存类型分支里内联一份命令构造，绕过四个单一定义点。
- 把蓝光子档位塞进 `QUALITY_MAPPING`，或给虎牙之外的平台加探针退避。
- 删掉末位候选放行 / 401/403 原样重试，重引「探针误杀可用源」。
- 轮末无条件 `record_success`，稀释按 host 熔断统计。
- 为让 CI 绿回填本地自算的运行时哈希（固化「构建机已中毒」）。
- 把签名档标记当成放行条件（标记本身不构成放行，须在 `_RUNTIME_GPG_SIGNATURES` 登记指纹）。
- 在 Skill 或文档里复制 black/isort/mypy 命令清单（违反铁律 4）。
- 只跑全量门禁、不跑命中段的专项检查——全绿只能证明「整体没坏」，不能证明「本次改动点有对应测试覆盖」。

## 目录结构

```text
dlr-domain-constraints/
├── SKILL.md                                   # 三段链路硬约束摘要 + 路由表 + 单一验证入口
└── references/
    ├── source-probe-reachability.md           # 探针可达性、节流抖动、UA 双端一致性
    ├── source-platform-selection.md           # 虎牙/斗鱼选源、FLV-first 与 HLS 排除语义差
    ├── source-quality-mapping.md              # 画质映射、蓝光子档位、斗鱼本地重试链
    ├── source-parser-contract.md              # 装饰器契约、_loads_dict JSON 兜底
    ├── ffmpeg-reconnect-constraints.md        # -reconnect* / -thread_queue_size 位置约束
    ├── ffmpeg-segment-format-lookup.md        # -segment_format 查表与容器格式
    ├── ffmpeg-recording-feedback.md           # 录制结果反馈与探针退避交互
    ├── ffmpeg-golden-command-comparison.md    # 黄金命令基准比对
    ├── pin-official-signatures.md             # 官方签名档（槽内第二种满足方式）
    ├── pin-macos-endpoints.md                 # evermeet 版本化直链约束
    ├── pin-linux-endpoints.md                 # 月末 autobuild 不可变标签约束
    └── pin-categories.md                      # 三类钉定边界、来源增删三处同改、TOFU
```
