# DouyinLiveRecorder 专属分支

主 `SKILL.md` 的 8 阶段流程在本仓**逐阶段照用**；本文件只补该仓专属的事实源、分区表与判据入口，不复述流程本身。

## 何时加载本文件

仓库根存在 `AGENTS.md` + `pyproject.toml` + `scripts/run_gates.py`，且用户要求全仓只读静态审查时。其他仓库不要用本文件的分区表与门禁名。

## 本仓的事实源交接（不得在此建第二份）

| 需要的东西 | 去处 |
| --- | --- |
| 项目约束本体、门禁命令基准 | 仓库根 `AGENTS.md`（唯一事实源） |
| 跑门禁 | `python scripts/run_gates.py`（它运行时解析 AGENTS.md「格式化命令」，此处不复制参数） |
| 测试编写约定 / 已知坑 / 静态检查裁定 | 项目 Skill `dlr-dev-playbook` 的 `references/*.md` |
| 选源、ffmpeg 命令构造、运行时二进制钉定 | 项目 Skill `dlr-domain-constraints` |
| `src/javascript/*.js` 签名脚本字节对账与还原 | `dlr-domain-constraints/references/js-signature-pin-byte-parity/SKILL.md`（本流程只把它当一条判据来源，不重复建设） |
| 工具层配方（rc 取值、转义被吃、`/tmp` 路径、AST 按节点判定、pytest 残留、删除动词） | `dlr-dev-playbook/references/windows-readonly-source-probing/SKILL.md` |
| 报告出来后逐条整改 | 本组 `references/code-review-remediation/SKILL.md` |

## P0 基线：用本仓专属脚本

主流程阶段 1 的 `review_scope.py` 给范围表与漂移复比；本仓另有一个更宽的取证快照，两者分工：

```bash
# 仓库根执行；输出默认落 %TEMP%，脚本自身拒绝写入仓库
.venv/Scripts/python.exe <本 Skill 目录>/scripts/repo_review_snapshot.py snapshot
# 收尾复比：报告是唯一允许新增的文件
.venv/Scripts/python.exe <本 Skill 目录>/scripts/repo_review_snapshot.py verify \
  --manifest <snapshot 打印的路径> --allow-added docs/worklog/CODE_REVIEW_<date>.md
```

POSIX 侧换成 `.venv/bin/python`。产物 `manifest.json`（逐跟踪文件 sha256）+ `facts.json`（HEAD 与工作区冲突块计数、AST 解析失败清单、分区文件与行数、工作区状态）——`facts.json` 就是 P1 分区表的取数来源。

出现 `changed` 时逐条归属（自己的 / 并发包的），不可静默放过。

## P0 基线 ref 的历史坑

本仓 HEAD 曾一次提交整份未解决的 `git stash pop` 冲突（`34bd33e`：899 个冲突块 / 102 个跟踪文件，94 个 `.py` 无法 AST 解析）。所以：

1. 先 `git grep -c '^<<<<<<< ' HEAD`，非 0 就**禁止**拿 HEAD 做资产差集基线。
2. 取最近一个冲突普查为空的祖先提交（历史实例 `f93c504`），并在报告里写明选择理由。
3. `verify` 报告 changed 时注意 `.workbuddy/`、`skills-premerge-backup/` 这类 gitignore 目录不参与跟踪，需要单独枚举确认。

## P1 分区表（本仓默认边界）

| 区域 | 默认边界 | 精读方式 |
| --- | --- | --- |
| 根入口 | `main.py` `gui.py` `web.py` `build_exe.py` `i18n.py` `msg_push.py` + 根 `index.html` | 逐行精读，按 2k–11k 行切给多个代理 |
| `src/` 顶层 | 除 `gui_qt/` `platforms/` `proto/` `javascript/` 的子目录 | 按职责分 4–6 区 |
| `src/gui_qt/` | 含 `pages/` | 逐行精读 |
| `src/platforms/` + `src/proto/` | 生成物只核存根同步性 | 逐行精读 + 存根对账 |
| `src/javascript/` | 排除 `crypto-js.min.js` 正文 | 精读签名/输出面 + 钉定对账 |
| `web/` | `app.js` `index.html` `style.css` `motion.js` | 逐行精读 |
| `scripts/` | 含 `.sh`、standalone 副本 | 逐行精读 |
| `tests/` | 模式扫描全覆盖 + 关键文件逐行 | 判据扫描 + 抽读 |
| `typings/` | 手写存根 | 逐文件核对 |
| CI/构建/配置 | `.github/**` `pyproject.toml` `requirements.txt` `Dockerfile` `docker-compose.yaml` ignore/attributes、`config/*.ini`、`StopRecording.vbs` | 逐行精读 + 同源对账 |

默认排除（必须写进报告，不得默认省略）：`.venv`、`build`、`dist`、`coverage*`、`.git`、`ffmpeg/`、`node/`、`downloads/`、`logs/`、`backup_config/`、`DouyinLiveRecorder.egg-info/`、`uv.lock`、`.workbuddy/`、`node_modules/vendor`、第三方压缩库正文、protoc 生成物正文、`i18n/*` 目录正文（只做键集合与抽样对账）、`docs/**` 与 `*.md`（只做同源性核对）。

超长单文件的实测切点先例：`src/spider.py` 全 21317 行 → L1–L11000 与 L11000–末尾两个代理。

## P2 派发

- 简报用主流程 `references/brief-template.md`，白名单填 `references/dlr-design-whitelist.md`（缺它代理会把 AGENTS 钉死的约定报成缺陷）。
- 并发上限实测约 5：每批 3–5 个，超出报 concurrency limit 且**不自动重试**。
- 代理的探针允许，但必须落 `%TEMP%`，不得写仓库。

## P5 门禁与同源锁族

```bash
PYTHONUTF8=1 .venv/Scripts/python.exe scripts/run_gates.py > "$TEMP/gates.log" 2>&1
echo "gates rc=$?"
```

冲突解决后必跑的四个同源锁（历史 4 个红点全由它们抓出，逐条判据见 `references/dlr-measurement-recipes.md` §9）：`tests/test_i18n*.py`、`tests/test_ci_frontend_registration.py`、`scripts/check_annotations.py`、`scripts/compile_po.py --check`。

`basedpyright` 是本仓 mypy 的**裁定工具**（CI 不跑）：只在某一平台出现的结论以与 CI 一致的 Linux 侧为准，别把它当第三条门禁。

## P6 报告

- 落盘路径惯例 `docs/worklog/CODE_REVIEW_YYYY-MM-DD.md`（沿用主流程 `references/report-outline.md` 骨架，本仓不另设模板）。
- 同名已存在时先读，再决定更新或 `_2` 后缀，不覆盖他人报告。
- 只读审查收口时，若报告里有需要修的条目，末尾指向本组 `references/code-review-remediation/SKILL.md`。
- 按 `AGENTS.md`「完成定义」判定本次豁免：纯报告产出通常只适用「文档同步」与「当日 `.workbuddy/memory/` 日志」两条。
