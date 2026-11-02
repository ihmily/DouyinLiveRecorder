# AGENTS.md / 技能审阅：指令冲突、歧义与摩擦清单

> 审阅日期：2026-09-17
> 审阅对象：`AGENTS.md`（798 行）、`.github/workflows/ci.yml`（相关段）、`pyproject.toml`（工具配置）、
> 用户级技能 5 个（`~/.workbuddy/skills/`：archify / brainstorming / karpathy-guidelines / vercel-react-view-transitions / vibe）
> 方法：全文阅读 + 交叉引用核对 + 与 CI 真实命令、`pyproject.toml`、源码现状做事实比对

---

## 0. 结论速览

| # | 位置 | 类别 | 一句话结论 | 处置 |
| --- | --- | --- | --- | --- |
| F-1 | AGENTS.md:41-56 ↔ :672 | **直接冲突** | `except (A,B):` 是否被 black 强制去括号，文件给出两个相反事实 | 改 |
| F-2 | AGENTS.md:662 ↔ :750-761 | **直接冲突** | 异常日志该写 f-string 还是 `i18n.tr()` 模板 | 改 |
| F-3 | AGENTS.md:443,446-449 ↔ :695 ↔ ci.yml:232-233 | **冲突 + 陈旧** | mypy 门禁跑法三套口径，且 CI 注释已过期 | 改 |
| F-4 | AGENTS.md:281 ↔ :440-442 ↔ :672 | **三处不一致** | black/isort 命令形态三种，且「line-length 不继承」与自身声明矛盾 | 改 |
| F-5 | AGENTS.md:281,695 vs ci.yml | **隐形门禁** | basedpyright 声明必过，但无命令、无 CI job | 改 |
| F-6 | AGENTS.md:420-425 ↔ :262-265 | **意外摩擦** | venv 修复「须由用户执行」与「代理可绕代理跑 pip」并存，无中间档 | 改 |
| F-7 | AGENTS.md 全文 | **空缺** | 没有「完成定义 / 收尾」章节——CODE_WIKI 更新日志、每日日志、真机验证都不在文件里 | 补 |
| F-8 | AGENTS.md:652 | **空缺** | i18n 四目录规则漏了 `web/app.js` 内嵌目录 | 补 |
| F-9 | AGENTS.md:552-557 ↔ :636；:13 ↔ :588；:80 ↔ :595 | **重叠** | 多条约定双份存在且已出现程度不同的漂移 | 收敛 |
| F-10 | AGENTS.md:88-89 + src/spider.py:48-49 | **规则外溢** | 「注释只增不改」被用到文档自身与事实性注释，固化了 F-1 的错误说法 | 改 |
| F-11 | AGENTS.md:299-300 | **过重无豁免** | 新增用例必须「变异验证」，小改动也被拉到全流程成本 | 改 |
| F-12 | `brainstorming/SKILL.md`:12-14 | **摩擦（技能）** | HARD-GATE 覆盖「任何修改行为」，与你的批量连续推进节奏正面冲突 | 改 |
| F-13 | `karpathy-guidelines/SKILL.md`:17-20 | **摩擦（技能）** | 「unclear → stop → ask」无阈值，缺少「先查文档」前置 | 改 |
| F-14 | `vibe/SKILL.md`:91-100 | **摩擦（技能）** | 硬停止显式覆盖主机的「continue until done」 | 隔离 |
| F-15 | AGENTS.md:330-333,451-454 | **环境不可用** | 依赖 `rm` / `find` 的命令在本机 Git Bash 无 coreutils 下不可执行 | 改 |
| F-16 | AGENTS.md:640 | **陈旧引用** | `gui_legacy.py` 当前工作区不存在 | 确认/删 |

**不应改动的部分**（有意设立的保障，建议保持原样）：见第 3 节。

---

## 1. 逐条详情

### F-1 ｜ `except (A, B):` 是否被 black 禁止 —— 同一文件给出两个相反事实 ★最高优先级

**位置 A**：`AGENTS.md:41-45`

> - **except 多异常写法（PEP 758，2026-09-02 定稿）**: 本仓统一写 `except A, B:`（不带括号），
>   不写 `except (A, B):`——这不是风格偏好而是 black 26.x 稳定风格的强制要求：`black --check`
>   会把能放进一行的 `except (A, B):` 改写回无括号形式，加了括号反而过不了格式门禁。

**位置 B**：`AGENTS.md:46-56`（自我更正）

> - **2026-09-12 实测更正（保留上方约定，仅修正其理由）**：「black 会把 `except (A, B):`
>   改写回无括号」这一说法**与实测不符**——对 `except (ValueError, TypeError) as e:` 跑
>   `black --check` 返回 rc=0（unchanged）…… 两种写法 black 均接受，统一写无括号是**本项目风格约定**……

**位置 C**：`AGENTS.md:672`（又回到 A 的旧结论）

> Python 3.14 经 PEP 758 原生支持无括号的多异常捕获，而 black 在 `target-version = ['py314']` 下
> 会**主动去掉** `except (A, B):` 的括号……② 不要把无括号写法"修回"加括号，否则违反 black 门禁
> （black 会再次去括号，且 `black --check` 判违规）。

**冲突性质**：B 已用实测证伪 A/C 的事实前提，但 A/C 未被标记为作废，仍以「硬约束」语气陈述。
同一文件同时存在「black 会去括号」和「black 不会去括号」。

**对行为的影响**

1. 读到 A/C 的代理会把「括号 → 无括号」当成**过门禁的必要动作**，从而批量改写存量代码，产生与功能无关的大 diff（B 明确禁止这种批量改动）。
2. 读到 B 的代理会认为括号写法合法 → 与 1 相反的行为。同一仓库两种结果。
3. 更糟的外溢已发生：`src/spider.py:48-49` 依据 A 的口径写了
   `# 严禁改成 `except (A, B):`，否则会被误判为需要回溯兼容并破坏 3.14 语义。`
   —— 这句本身是被 B 证伪的错误说法，却作为「防回归注释」固化在源码里（见 F-10）。
4. 存量计数也已漂移：B 称「现存 9 处带括号写法」，实际扫描为
   `src/config_io.py` 4、`src/spider.py` 1（另 1 处命中是注释）、`gui.py` 2、`main.py` 1、
   `scripts/douyin_live_recorder_standalone.py` 7、`scripts/smoke_test.py` 1、`scripts/check_annotations.py` 1（后两处疑似 pattern 字符串）。
   硬编码计数作为约定的一部分，本身就会持续腐化。

**建议改法**：删除 A 的错误断言、把 C 的同一条并回来，只保留一条不含错误前提的条文。

替换 `AGENTS.md:41-56` 整段为：

```md
- **except 多异常写法（2026-09-12 定稿）**: 本仓统一写 `except A, B:`（不带括号，PEP 758，
  依赖 Python ≥3.14，与 `requires-python = ">=3.14"` 一致）。
  - **性质：风格约定，不是格式门禁强制。** 2026-09-12 实测 `black --check` 对
    `except (ValueError, TypeError) as e:` 返回 rc=0（unchanged），两种写法均可通过。
    故**不得**以「过门禁」为由批量增删括号。
  - 新增/修改代码写无括号；**存量带括号写法不要为对齐而批量改动**，
    可随相关功能改动顺手统一。
  - **不要**为「兼容 <3.14」而加括号——本仓不支持 3.13 及以下；语法/编译检查一律用项目 venv 的 Python 3.14。
  - 外部审查若建议「统一为 `except (A, B):`」，与本约定相反，不予采纳
    （CODE_REVIEW_FIX_1 的 F-08 已澄清为非问题）。
```

并把 `AGENTS.md:672` 首条改为同一口径（该条另一半价值——「语法/编译检查一律用项目 venv 的 Python 3.14」
是真的有用的硬约束，予以保留；只替换括号部分）：

```md
- **PEP 758：`except A, B:`** **在 3.14 合法，语法/静态检查一律用项目 venv 的 Python 3.14**：
  Python 3.14 经 PEP 758 原生支持无括号的多异常捕获（两种写法 black 均接受，
  详见「代码风格」章节）。用 Python 3.13 或更早做 `compileall` / `py_compile` 会把全树误报为
  `SyntaxError: multiple exception types must be parenthesized`（实测：3.14 两种写法都通过、3.13 只有加括号通过）。
```

同时修正 `src/spider.py:48-49`（唯一受益于 F-10 的解释性注释例外条款）：

```python
#   - 本文件使用 Python 3.14 的 PEP 758 异常语法 `except A, B:`（不带括号），这是语法特性
#     而非笔误；两种写法 black 均接受，本项目统一写无括号（2026-09-12 定稿）。
```

---

### F-2 ｜ 异常日志格式：f-string 约定已被 i18n 迁移取代，但未标注作废

**位置 A**：`AGENTS.md:662`

> 凡 `except Exception as e:` 的日志一律写成 `f"<动作>: {url} - {type(e).__name__}: {e}"`
> （`src/async_http.py` 的 `async_req` 已按此修正）。

**位置 B**：`AGENTS.md:750-761`（2026-09-10 i18n 迁移）

> **形参日志必须走 `i18n.tr(模板, **kw)`，禁止再用 f-string**……全仓 242 处形参日志因此
> 「有翻译但用不上」。

**冲突性质**：A 要求的字面形式（f-string）正是 B 明令禁止的写法。A 的「为什么」（Windows 下
`socket.timeout` 的 `str()` 为空导致空白日志）仍然有效，但「怎么写」已经过期。

**对行为的影响**：新增 `except` 分支时，代理必须在两条互斥指令中选一条。选 A → 翻译静默失效
（且 `tests/test_i18n_migration.py` 第 ① 项「无遗留有价值 logger/print f-string」可能变红）；
选 B → 违反 A 的字面规定。二者都合理的局面会让代理停下来确认。

**建议改法**：保留 A 的动机，把写法迁移到 B。

```md
- **异常日志必须带异常类型与上下文**：Windows 下 `socket.timeout` / `TimeoutError` 的 `str()`
  **为空字符串**，只写 `{e}` 会打出空白行，排查时完全失去线索。
  自 2026-09-10 i18n 迁移后写法为（**禁止再写 f-string**，详见「形参日志必须走 i18n.tr」条目）：

  `logger.debug(tr("<动作>: {masked_url} - {type_name}: {err}", masked_url=utils.mask_credentials(url), type_name=type(e).__name__, err=e))`

  硬性要求不变：必须带 `{type_name}`、`{masked_url}`（凭据一律经 `utils.mask_credentials()`）；
  流地址校验失败还须额外输出 `status_code` 与 `content-type`，**禁止静默吞异常**。
```

---

### F-3 ｜ mypy 门禁跑法：三套口径，且 CI 注释已过期

**位置 A**：`AGENTS.md:443` + `:446-449`

> ```bash
> mypy
> ```
> **`mypy` 不带路径参数**：检查范围由 `pyproject.toml [tool.mypy].files` 定义……
> 显式传参（如 `mypy src/`）会**覆盖**该配置而只查 src/……**门禁结果以无参数跑法为准**（2026-09-15 定稿）。

**位置 B**：`AGENTS.md:695`（平台符号门控条目）

> 验证必须双跑：`mypy src/` + `mypy --platform linux src/` 两次全绿才算过。

**位置 C**：`.github/workflows/ci.yml:232-233` 注释仍写旧的双跑命令，而 `ci.yml:268-270` 实际跑 `mypy`。

**冲突性质**：B 要求的命令形式正是 A 明确说「覆盖 [tool.mypy].files、只能排障用」的形式；
C 的注释还停留在旧实践。三者并列时无法判断「平台符号改动到底以哪条为准」。

**对行为的影响**

1. 按 B 执行 → 只查 `src/`，根目录入口漏检（正是 A 记录的 gui.py `logger`/`session_id` 逃逸事故）。
2. 因 B 写死在「平台门控」这种高风险条目里，代理倾向于宁可信其有 → 退化为低覆盖门禁。
3. C 过期注释会把执行清单拉回旧口径。

**建议改法**：保留双跑语义，去掉路径收窄（这样既保持全量范围，又保留 Linux 平台等价性）。

`AGENTS.md:695` 结尾句改为：

```md
验证必须双跑且**均不带路径参数**（保证范围仍是 `pyproject [tool.mypy].files` 全量）：
`mypy` + `mypy --platform linux`，两次全绿才算过。
```

`ci.yml:232-233` 注释同步为：

```yaml
  # ubuntu runner 默认即为 linux 平台，等价于本地双跑门禁中的 `mypy --platform linux`
  # （AGENTS.md 平台符号门控约定；两条命令均不带路径参数，范围取 [tool.mypy].files）。
```

---

### F-4 ｜ black / isort 命令形态三套并存

**位置 A**：`AGENTS.md:281`（tests 门禁）

> `pytest`（0 警告）、`black --check tests/`、`isort --check-only tests/`、`mypy tests/`、`basedpyright tests/`

**位置 B**：`AGENTS.md:440-442`（格式化命令）

> ```bash
> black .
> isort .
> mypy
> ```

**位置 C**：`AGENTS.md:672`

> 附带一条：black 的 `line-length` **不会从** `pyproject.toml` **继承到命令行**，门禁必须显式传参——
> `python -m black --check --line-length 120 --target-version py314 <paths>` ……

**冲突性质**：A、B 都直接/间接依赖 pyproject 里的 `[tool.black]`；C 断言它不生效，要求显式传参。
而本文件 `:33-37` 自身声明 black 的全部关键配置（`line-length = 120`、`target-version`、`exclude`）
就写在 `pyproject.toml`；`ci.yml:203-205` 的注释也自承
「排除目录仍由 pyproject `[tool.black].exclude` / `[tool.isort].extend_skip` 声明，此处无需重复传参」
——即承认 **exclude 会继承**，这一自相矛盾的粒度进一步削弱了 C 的前提。

**对行为的影响**

1. 按 A/B 执行时若 C 的前提为真，则按 88 列判定 → 全仓大面积「待格式化」假红；
   代理可能据此执行 `black .` 全仓重写，产出与本仓库风格相反的巨型 diff。
2. 即使 C 为真，A/B 两处仍处于「未显式传参」的违规状态，属于文档内的自违规。
3. 三种命令并存让「本地过、CI 挂」这类排查没有统一基准。

> 注：`line-length` 是否真不继承，本次环境无可用 black 可执行文件未能实测（见第 4 节待核实项）。
> 但**无论该前提真假**，都应当只保留一种命令写法。

**建议改法**：在「格式化命令」章节固化唯一门禁命令块，把 A 改为引用它。

替换 `AGENTS.md:438-444`：

````md
## 格式化命令（门禁唯一基准，与 `ci.yml` 静态检查 job 逐字一致）

```bash
# 全仓（门禁口径；也可换成任意 <paths> 子集做收窄排障）
python -m black --check --diff --line-length 120 --target-version py314 .
python -m isort --check-only --diff --profile black --line-length 120 .
mypy                      # 不带路径参数，范围取 pyproject [tool.mypy].files
mypy --platform linux     # 平台符号门控改动时增跑（同样不带路径）
python scripts/check_annotations.py
python scripts/compile_po.py --check
python scripts/check_version.py
```

- **一律显式传参**（`--line-length 120 --target-version py314` / `--profile black`）：
  CI 固定工具版本且有跨站 patches-filter 分支，显式写全可避免本地配置飘移造成
  「本地过、CI 挂」；**排除目录不需要传**，由 `pyproject [tool.black].exclude` /
  `[tool.isort].extend_skip` 继承。
- `black .` / `isort .`（不带 `--check`）是写操作，仅用于纠格式，不在门禁回路里使用。
````

并把 `AGENTS.md:281` 的 black/isort/mypy 三项改为：

```md
- **tests/ 质量门禁（2026-08 起全绿，须保持）**: `pytest`（0 警告）+「格式化命令」章节的
  black / isort / mypy 三条（同样加 `--check` 与显式参数，路径换成 `tests/`），
  + `basedpyright tests/`（0 error/0 warning，本地门禁，CI 不跑——见下）。
```

---

### F-5 ｜ basedpyright：声明必过、没有命令、CI 不跑（隐形门禁）

**位置**：`AGENTS.md:281`（列为须保持的门禁）、`AGENTS.md:404/407/410`（排除列表同步点）、
`AGENTS.md:506/695`（提到报错码与 strict 行为）；`ci.yml` 全文无任何 basedpyright 步骤。

**对行为的影响**

1. 无权威命令 + 无 CI → 实际执行范围、是否 strict、`--outputjson` 阈值全靠临场判断。
2. 「0 error/0 warning」的门槛很容易产生长尾：notice/hint 级别的 strict 规则在 CI 不可复现，
   代理可能花大量时间清理不会被 CI 校验的告警（自我加戏），也可能直接跳过（漏干活）。
3. 与 mypy 结论冲突时无裁决规则（`:695` 已出现 Windows 下必要、Linux 下 `reportUnnecessaryTypeIgnoreComment` 的双向场景）。

**建议改法**：新增一小节，把它明确定位为「本地补充门禁」。

```md
### basedpyright（本地门禁，CI 不跑）

- 命令：`basedpyright`（不传路径，范围取 `pyproject [tool.basedpyright]`）；
  要求 **0 error / 0 warning**。
- 与 mypy 分工：mypy 是跨平台 CI 门禁（`python_version = 3.14`）；basedpyright 是本地严格度补充。
- **裁决规则**：CI 跑的是 mypy（Linux runner）。Linux 下才出现、Windows 下不出现的
  basedpyright 结论以 Linux 为准；反之同理——不要在 Windows 本地用
  `# type: ignore` 换取两边都静默（会触发 `reportUnnecessaryTypeIgnoreComment`）。
- mypy 与 basedpyright 报错码不同（同一问题两个 code），ignore 注释需按各自 code 填写。
```

---

### F-6 ｜ venv / 依赖修复只能「由用户在普通终端执行」—— 缺少中间档，且与另一条并存

**位置 A**：`AGENTS.md:420-425`

> 修复须由用户在普通终端执行 `pip install --ignore-installed --no-deps -r requirements.txt`……

**位置 B**：`AGENTS.md:262-265`

> 先核对 `pip list` 与 `requirements.txt` 的差异……pip 走本地代理被拒时用
> `HTTP_PROXY="" HTTPS_PROXY="" pip install --proxy "" <pkg>` 绕过。

**冲突性质**：同一文件的依赖章节既给出了「代理自己跑 pip 装单个包」的做法，又在
**同一症状（venv 缺/坏依赖）**上规定「必须交回用户」，且没有给出「哪些程度可以自己做」的判据。

**对行为的影响**：代理在遇到第 3 类症状（单包目录破损、`cannot import name 'x' from 'y' (unknown location)`）
时，为了避免违反 A，会选择停下来把整件事交回给你 —— 而这恰恰有成熟且已被验证的
**代理侧安全手段**（wheel 直解，不经过 pip 卸载阶段，不会二次清空目录）。

**建议改法**：改成三级处置，把已验证的自救手段写进 AGENTS.md。

```md
- **venv 依赖修复分级处置**（关键：不要在本环境的沙箱里跑会写 `site-packages` 的批量 pip）
  - **一级（代理自行处理，首选）**：单/少数包目录破损（典型症状
    `ImportError: cannot import name 'x' from 'y' (unknown location)`、`pip check` 查不出、
    目录只剩 `__pycache__`）——用 **wheel 直解**，绕开 pip 卸载阶段：
    `pip download --no-deps -d <tmpdir> <pkg>` → Python 内
    `zipfile.ZipFile(wheel).extractall(site_packages)`（提取后再核对 `.dist-info` 是否落地）。
  - **二级（代理可试）**：常规补装且仅需单个小包 → `HTTP_PROXY="" HTTPS_PROXY="" pip install --proxy "" <pkg>`；
    安装过程中若被沙箱拦截，立即转三级（不要重试 —— 拦截发生在卸载/写入之后，重试会加重破损）。
  - **三级（交回用户）**：批量重装（`-r requirements.txt --force-reinstall` 等）必须由用户在
    普通终端执行 `--ignore-installed --no-deps`；这是 sandbox 失败成本高、需要人工兜底的场景。
  - **破损检测三查法**：① 目标目录递归数 `.py`/`.pyd` 为 0 即破损；
    ② 目录整体消失（`importlib.metadata.distributions()` 扫不到）→ 逐个 import 实测；
    ③ `dist-info/RECORD` 对账仅作辅助（曾返回 0 缺失仍破损）。
```

> 说明：工作区记忆里已沉淀这套做法（含「被清空的包无 RECORD，`--force-reinstall` 会报
> `uninstall-no-record-file`，只能用 `--ignore-installed`」的细节），AGENTS.md 尚未收录 ——
> 属于典型的「记忆里有、唯一的权威文件里没有」。

---

### F-7 ｜ 空缺：没有「完成定义 / 收尾」章节 ★对「工作不完整」影响最大

**位置**：AGENTS.md 全文无对应章节。唯一线索是 `:719`（「变更记录见 CODE_WIKI」），
但那是**结果归档位置**的指引，不是**何时必须更新**的义务。

你实际执行的收尾标准目前只存在于工作区记忆里：

> 工作节奏：……门禁全绿 + 端到端真机验证才算完成。收尾：更新 CODE_WIKI 更新日志 + 每日日志。
> 近期动态：每次改动后同步更新 CODE_WIKI.md / CODE_WIKI_EN.md 更新日志章节（固定收尾动作）。

**对行为的影响**：只被 AGENTS.md 约束的代理会把「代码改完 + pytest 全绿」当成完成，
**必然落下**你视为固定动作的部分（中英 CODE_WIKI 更新日志、每日记忆日志、真机 URL 增量验证），
也就是你感知到的「活干了一半」。这条也属于「保障措施意外缺位」而非「摩擦」。

**建议改法**：新增章节（建议放在「格式化命令」之后、「并发与线程模型」之前）。

```md
## 完成定义（Definition of Done）

代码通过门禁 ≠ 完成。改动落地后按序执行，任一条不满足即为未完成：

1. **门禁全绿**：`pytest`（0 警告）+「格式化命令」章节四条 + `scripts/check_annotations.py`
   + `scripts/check_coverage.py`；CI 之外的 `basedpyright`（本地）同步核一次。
2. **端到端真机验证**：涉及录制链路 / 选源 / ffmpeg 参数的改动，必须用真实 URL 增量跑一次
   （至少一个受影响平台），并把验证结果写进回复；**只有单测绿不算验证过**。
3. **回归锁**：动到有「回归锁」标注的行为时，确认对应用例存在且覆盖到该行为；缺则补。
4. **文档同源**：`CODE_WIKI.md` / `CODE_WIKI_EN.md` 的「更新日志 / Changelog」追加本次变更条目
   （改为中英双份同步）；新增长期约定同时写回本文件对应章节，不要只留在临时笔记或对话里。
5. **日志**：当日 `.workbuddy/memory/YYYY-MM-DD.md` 追加一条（只写有长期价值的部分）。

**豁免**：纯文档 / 注释改动可只做 1（注释类）+ 4 + 5；只改动测试且不涉及生产行为时免 2。
```

---

### F-8 ｜ i18n 四目录规则漏掉前端内嵌目录

**位置**：`AGENTS.md:652`（四目录 + compile_po + extract）、`AGENTS.md:750-768`（tr 模板约定）。

工作区记忆里有但 AGENTS.md 没有的一条：

> web/app.js 独立内嵌四语目录，改前端四处都加；改完必跑 `node --test tests/frontend/*.mjs` + `node --check web/app.js`。

**对行为的影响**：新增/修改 i18n 串时，后端四目录会同步、`web/app.js` 的内嵌目录会漏 →
Web 面板显示未翻译或取不到字串，属于典型的「看起来全绿、交付不完整」。

**建议改法**：在 `:652` 末尾追加：

```md
- **`web/app.js` 另有内嵌的四语目录**（与 i18n 目录同 key 集合，键集合不一致时前端渲染缺串）：
  新增/修改串须同步五处（四份目录 + `web/app.js`），改完必跑
  `node --check web/app.js` + `node --test tests/frontend/`。
```

---

### F-9 ｜ 重叠：同一约定双份存在，且已出现漂移

| 约定 | 位置 1 | 位置 2 | 漂移情况 |
| --- | --- | --- | --- |
| `clear_ffmpeg_reject` 成功清退避 | `:552-557` | `:636` | 两份近重复；`:556` 的「勿把清除逻辑写成只删 mark 不删 clear」只存在于其中一份 |
| 版本号单一事实源 | `:13` | `:588` | 措辞不同、同步成本高 |
| 禁用 docstring | `:80-82` | `:595` | 重复；`:595` 多了「已 100% 满足」的现状陈述 |
| 探针退避窗口 / 虎牙白名单 | `:630`、`:634`、`:630` + `:542` | 分散 | 同一组内多处复述 |

**对行为的影响**：改一处漏一处是中长期风险；已发生的漂移（clear_ffmpeg_reject 的那句）
证明风险已经在兑现 —— 读到不同位置的代理会得到粗细不同的要求。

**建议改法**：每类保留一处「唯一事实源」 + 其余改为指针，例如 `:636` 整条改为：

```md
- **`clear_ffmpeg_reject` 成功清退避**：见「录制结果反馈约定」章节同名条目（本文件不重复维护）。
```

---

### F-10 ｜ 「注释/约定只增不改」规则被外溢到 AGENTS.md 自身与事实性注释

**位置**：`AGENTS.md:88-89`

> 修改注释时**只增不改**：不得删除或重写已有注释（避免丢失历史上下文），需要修正时在其下方补充。

这条对**解释性注释**是很好的保障（历史上下文不该丢），但它有两个外溢后果：

1. 用于 AGENTS.md 自身时，产生了 F-1 这种结构：**错误原文保持原样 + 下方追加更正**。
   错误陈述没有被降权，搜索/跳读会命中错误版本。
2. 用于**事实性断言**时，会阻止纠正错误 —— `src/spider.py:48-49` 的
   「严禁改成 `except (A, B):` … 会破坏 3.14 语义」正是被 F-1 的位置 B 证伪过的说法。

**建议改法**：保留规则，补充两类例外。

```md
- 修改注释时**只增不改**：不得删除或重写已有的**解释性**注释（避免丢失历史上下文），
  需要修正时在其下方补充。若因此产生相邻重复注释，需合并。
- **例外（允许就地纠正）**：① 事实性错误（已被实测证伪的陈述、错误的命令行/patch 目标）——
  就地改正并把旧结论压缩为一行带日期的历史注；
  ② AGENTS.md 自身被证伪的条目——不得追加「更正」保留错误原文，
  直接改正文，并在末尾保留 `[YYYY-MM-DD 修订：旧结论 X 已被实测推翻]` 一行。
```

---

### F-11 ｜ 测试要求过重且无豁免档

**位置**：`AGENTS.md:299-300`

> 新建用例须与被测模块同名……并用变异验证（临时改坏被测代码，确认测试变红）证明用例真能抓回归

叠加 `:283`（pytest 0 警告 + 四工具门禁）与 `:289`（逐模块覆盖率 `check_coverage.py`），
任何新增/修改测试都会被拉到全流程成本。

**建议改法**：加豁免档，避免「改一行就被拉满全套流程」。

```md
- 创建/更新测试: 按「源码分析 → Mock 配置 → 验证执行」标准化流程编写；新建用例须与被测模块同名。
  **变异验证的适用范围**（不要一律执行）：
  - 必做：新增**安全不变量**类用例（如 F-01 重构后的黄金快照、`-reconnect*`/`-segment_format` 回归锁）；
  - 免做：仅调整既有断言、或新增「被测逻辑已被现有用例完整覆盖」的平凡用例；
  - 判据不变：**删掉生产实现就会失败**（禁止自实现被测逻辑，见「测试不得自实现被测逻辑（假绿）」条目）。
```

---

### F-12 ｜ 技能 `brainstorming`：HARD-GATE 与你的工作节奏正面冲突 ★摩擦最大

**位置**：`~/.workbuddy/skills/brainstorming/SKILL.md:3-14`

> description: "You MUST use this before any creative work - creating features, building components,
> adding functionality, **or modifying behavior**."
> `<HARD-GATE>`：Do NOT … write any code … until you have presented a design and the user has approved it.
> **This applies to EVERY project regardless of perceived simplicity.**

外加 `:29-31`（设计写 `docs/superpowers/specs/` —— 本仓库不存在该目录）、
`:32`（必须再 invoke writing-plans）、`:126-131`（写完还要再等一轮查阅批准）。

**为什么与你的节奏冲突**：你的既定流程是
「按 P5→P4→… 一批改动 → 一次审批（『需要』/『开始落地』）→ 连续推进到全部完成 → 真机验证」。
而该技能在 description 层面就把「修改行为」纳入必过设计门，且要求**每个 section 逐段批准**。
于是连一个单行修复、一次缺陷修补，也会被拦下要求先出设计文档再出计划文档。

**建议改法**（改技能 description 与 HARD-GATE，把已批准计划与仓库既有约定作为豁免）：

```md
description: "Use before net-new creative work — new features, new components/subsystems, new UI surface,
or product-level behavior design. Do NOT use for bug fixes, refactors, or work already specified by an
approved plan or by the repo's AGENTS.md / CODE_WIKI conventions."
```

```md
<HARD-GATE>
Do NOT write code or invoke implementation skills until a design is presented and approved —
for tasks in scope (see Trigger below).
Out of scope (proceed directly): bug fixes, regression repairs, refactors, config/format changes,
and any work whose requirements are already frozen in an approved plan or pinned in AGENTS.md /
CODE_WIKI.md. A one-line "here is what I will change" note is enough for those.
</HARD-GATE>
```

并把设计文档落盘路径改为「仓库既有约定优先，默认 `<repo>/docs/`」；在本仓库这种已有 AGENTS.md/CODE_WIKI 的场景中，通常直接跳过该步骤。

---

### F-13 ｜ 技能 `karpathy-guidelines`：默认「stop and ask」缺阈值

**位置**：`~/.workbuddy/skills/karpathy-guidelines/SKILL.md:17-20`

> If uncertain, ask. / If multiple interpretations exist, present them - don't pick silently. /
> **If something is unclear, stop. Name what's confusing. Ask.**

这条本身是好纪律，但没有「先做信息检索」的前置，也没有「问的成本 vs 收益」阈值。
在本仓这种「为什么要这样」注释密度很高（stream_select ≈35%）的项目里，
绝大多数 unclear 其实能在 AGENTS.md / CODE_WIKI / 既有测试里查到答案。

**建议改法**：在 §1 下加一段本仓适配：

```md
## 1b. Doubt resolution order (this repo)

Before stopping to ask, consume the local sources of truth in this order:
1. `AGENTS.md`（含「已知坑」章节，绝大多数反直觉行为的答案在此）
2. `CODE_WIKI.md` / `CODE_WIKI_EN.md`
3. 对应 `tests/test_<module>.py` 与其中的「回归锁」用例
4. 该模块的模块头注释

Only stop and ask when at least one holds:
- The decision is **irreversible or externally visible** (delete files, force-push, change a public interface).
- It needs **information only the user has** (credentials, target room/platform, intended product semantics).
- Two documented sources contradict each other.

Otherwise: pick the best-supported option, implement, and **state the assumption plus where to revert**
in the final reply. Silent guessing is still forbidden — the change is that the default becomes
"research → decide → disclose", not "research → stop".
```

---

### F-14 ｜ 技能 `vibe`：硬停止显式覆盖主机自主规则

**位置**：`~/.workbuddy/skills/vibe/SKILL.md:91-100`

> This is a hard runtime boundary, not a suggestion. **It overrides ordinary host autonomy rules
> such as "continue until done."** A detailed original request is not approval of the frozen requirement…
> After a hard stop, do not perform equivalent manual work outside governed re-entry…

该技能安装完整（`apps/vgo-cli/src/vgo_cli/main.py`、`protocols/*.md` 均在），也就是说它是**可运行**的。
一旦被加载，冻结需求 → 冻结计划 → 阶段清理共三次硬停，且每次都必须构造 host-decision JSON 才能继续。

**与本项目的契合度**：你的录制类工作依赖「改一点 → 真机跑 → 看日志 → 再改」的高频迭代，
迭代粒度经常小于一个「阶段」。进入 vibe 后，每一次硬停都会把已有势能打断，
而 AGENTS.md 的 F-01 条目已经把「四个单一定义点、禁止回退成内联复制粘贴」定为硬约束，两者叠加会形成双重锁定。

**建议改法**：不需要改技能本体，在 AGENTS.md 加一条路由隔离即可（比改第三方技能更稳）：

```md
## 流程编排技能的使用边界

- 本仓库的日常改动（缺陷修复、性能优化、真机验证迭代、重构）**不进入**治理式运行时类技能
  （如 `vibe`）——其需求/计划冻结与阶段硬停会打断「改一点 → 真机跑 → 再改」的迭代节奏。
- 只有当次会话里用户显式要求「进 vibe / $vibe / 走治理流程」时才加载它。
- 确需治理式执行时，先由用户确认 run 范围与 artifact root
  （不得把 vibe 安装目录当作产物根目录）。
```

---

### F-15 ｜ 依赖 `rm` / `find` 的命令在本机不可执行

**位置**：`AGENTS.md:330-333`（「用 shell `rm` 预清测试输出目录后重跑」）、`AGENTS.md:451-454`
（`find . -name "*.isorted" -delete`）。

Windows 无 coreutils（`ls`/`rm`/`find`/`head` 均不可用），两条命令照抄会直接失败。

**建议改法**：给出两套等价写法并限定范围。

```md
- **isort 收尾必须清理 `.isorted` 备份残留**（残留会被引擎扫描并被误提交）：
  Windows PowerShell：
  `Get-ChildItem -Recurse -Filter *.isorted | Where-Object FullName -notmatch '\\(\.venv|node_modules)\\' | Remove-Item -Force`
  POSIX：`find . -name "*.isorted" -delete`（本机 Git Bash 无 coreutils，用 PowerShell 版本）。
  匹配必须是 `*.isorted` —— `*.py.isorted` 匹配不到 `*.pyi.isorted`，会静默漏删并误提交。
```

同时把 `:333` 的清理范围收紧，避免误删运行期产物（也与「个人文件删除需二次确认」的安全策略保持一致）：

```md
… 用 PowerShell 删除 `tests/` 下由用例生成的临时输出目录（`tmp_path` 之外的 pytest 残留）后重跑即可验证；
**不要**删除 `downloads/` / `logs/` / `backup_config/` 等运行期产物目录。
```

---

### F-16 ｜ 陈旧引用：`gui_legacy.py`

**位置**：`AGENTS.md:640`

> `gui_legacy.py` 不导入 src、无互锁问题。

当前工作区根目录未找到该文件（可能已删除或未跟踪）。需要确认：若已删除，删除该句避免代理去
找一个不存在的文件；若仍在某处被生成/引用，补一句路径说明。

---

## 2. 建议的落地批次

| 批次 | 内容 | 风险 |
| --- | --- | --- |
| **A（纯文档）** | F-1（含 `src/spider.py:48-49`）、F-2、F-3（含 `ci.yml` 注释）、F-4、F-9、F-16 | 无运行期影响 |
| **B（补空缺）** | F-7 新增「完成定义」章节、F-8 i18n 前端、F-5 basedpyright 小节、F-6 依赖分级、F-15 命令 | 无运行期影响 |
| **C（技能）** | F-12 / F-13 改 `~/.workbuddy/skills/`；F-14 在 AGENTS.md 加路由隔离 | 影响其他会话的代理行为，建议先看 diff |

---

## 3. 有意设立的保障 —— 建议**保持原样**（不必改）

这些条目表面像摩擦，实际是有事故背书的防线，改动会引入回归：

| 条目 | 为什么保留 |
| --- | --- |
| `real_url` 为空必须跳过录制链（`:624`） | 防止 None 流入 ffmpeg 参数层；历史上已致崩溃 |
| `-reconnect*` 位置 / 布尔值 / m3u8 丢弃（`:674`） | 三起 P0 事故，且 failure mode 全是静默的 |
| 探针 GET 复核容错语义不简化（`:620`）、末位候选放行（`:626`） | 简化即重新引入「探针误杀可用源」 |
| 虎牙探针退避白名单不扩大（`:630`）、退避窗口 ≥ 主循环周期（`:634`） | 闭环恒不成立时假绿死循环 |
| 弹幕 WS `proxy=None`（`:616`）、GUI 父进程日志句柄（`:640`） | 平台级改即断连 / 日志全量静默丢失 |
| protobuf 上限不可删（`:796`）、`sync_req` SSL 惰性构造（`:792`） | 升级时序 / 全局降级面 |
| 敏感配置双重判定、前端掩码不回写（`:682`） | 凭据明文泄漏防线 |
| 测试不得自实现被测逻辑（`:684`）、翻译恒等映射 fixture 不可删（`:763-768`） | 防假绿 |

---

## 5. 落地状态（2026-09-17 执行)

**已落地 14 / 16 项**（F-3 的第 4 节待核实项已在本节末尾核实）：

| # | 状态 | 落点 |
| --- | --- | --- |
| F-1 | 已落地 | AGENTS.md 代码风格章节合并为唯一条文；已知坑 PEP 758 条目同口径化；`src/spider.py` 模块头注释更正 |
| F-2 | 已落地 | 异常日志条目改为 `i18n.tr()` 模板写法，保留「必须带类型名 + 掩码 URL」 |
| F-3 | 已落地 | 双跑改为 `mypy` + `mypy --platform linux`（均无路径）；`ci.yml:232-233` 注释同步 |
| F-4 | 已落地 | 新增「格式化命令（门禁唯一基准）」章节；tests/ 门禁改为引用该节 |
| F-5 | 已落地 | 新增「basedpyright（本地补充门禁，CI 不跑）」小节 |
| F-6 | 已落地 | 依赖条目改为三级处置 + 破损检测三查法，并在依赖缺失排查处加指针 |
| F-7 | 已落地 | 新增「完成定义（Definition of Done）」章节 |
| F-8 | 已落地 | i18n 条目补 `web/app.js` 内嵌四语目录与前端校验命令 |
| F-9 | 已落地 | `clear_ffmpeg_reject` 去重为指针；版本源 / docstring 禁令加同源指向 |
| F-10 | 已落地 | 「只增不改」增加事实性错误的就地纠正例外条款 |
| F-11 | 已落地 | 变异验证增加「必做 / 免做」适用范围 |
| F-12 | 已落地 | `brainstorming` description 收窄 + HARD-GATE 豁免清单 + 设计文档尊重仓库约定 |
| F-13 | 已落地 | `karpathy-guidelines` 新增 §1b 疑惑消解顺序 |
| F-14 | 已落地 | AGENTS.md 新增「流程编排技能的使用边界」章节（隔离 vibe / brainstorming 类流程） |
| F-15 | 已落地 | `.isorted` 清理与测试临时目录预清补 PowerShell 等价式并收紧范围 |
| F-16 | 已落地 | 删除 `gui_legacy.py` 陈旧引用（该文件已于 v4.1.0-dev / 2026-09-10 删除） |

### 落地过程中发现并顺带处理的既有缺陷（不在原清单内）

1. **black `line-length` 继承性核实为「会继承」**：用 venv 的 black 26.5.1 做对照实验——
   含 100 列调用行的探针不带参数跑 `black --check` 为 unchanged，加 `--line-length 88` 才报错，
   证明 `pyproject [tool.black].line-length = 120` 生效。AGENTS.md 旧断言为假，已删除并改写为
   「显式传参是为与 CI 逐字对齐、防止本地配置漂移」。
2. **`web.py` 漏了平台符号早返回**：`_get_kernel32` / `_get_user32` 直接引用 `ctypes.WinDLL`，
   导致新口径的 `mypy --platform linux` 报 4 个错（`attr-defined` / `no-any-return`）。
   已按 AGENTS.md 既有约定补 `if sys.platform != "win32": return None`——非 Windows 下原本也是走到
   `except Exception: return None`，**行为等价，无运行期语义变化**。

### 验证结果

- `black --check`（135 文件）/ `isort --check-only` / `mypy` / `mypy --platform linux`：全绿
- `scripts/check_annotations.py` / `compile_po.py --check` / `check_version.py`：全绿
- `pytest`：974 passed、2 skipped、**0 警告**
- `CODE_WIKI.md` / `CODE_WIKI_EN.md` 更新日志已追加本次条目（中英双份）

---

## 4. 待核实项（本次未能实测）

1. **`black` 的 `line-length` 是否真的不从 `pyproject.toml` 继承**（`AGENTS.md:672` 与
   `ci.yml:203-205` 的断言）。本机无可用 black 可执行文件，未实测。
   但 `:33-37` 自身声明配置写在 pyproject，且同段承认 exclude 会继承，故该断言至少**表述需修正**。
   核实命令：`python -m black --check --diff --line-length 88 <repo>/src/stream_select.py`
   —— 若报「将按 88 列重排」则说明继承未生效；若 unchanged 且该文件存在 >88 列的行，则继承生效。
2. **带括号 except 的准确存量计数**（`:48` 称 9 处）：当前扫描命中的文件见 F-1 第 4 点，
   其中 `scripts/check_annotations.py` / `scripts/smoke_test.py` 的命中疑似 pattern 字符串，
   需人工确认后再决定是否在文档中写死计数（建议**不再写死**）。
