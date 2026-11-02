# 判据配方（只读取证）

> 通用 shell/Windows 转义与退出码问题另见 `dlr-dev-playbook/references/windows-readonly-source-probing/SKILL.md`；本文只保留与本流水线直接相关的判据。门禁命令清单的唯一事实源是 `AGENTS.md`「格式化命令」，这里不复制。

## 1. 只读基线：snapshot / verify

```bash
# 仓库根执行；默认输出到 %TEMP%，脚本拒绝写入仓库
.venv/Scripts/python.exe <skill>/scripts/repo_review_snapshot.py snapshot

# 收尾复比；报告是唯一允许新增的文件
.venv/Scripts/python.exe <skill>/scripts/repo_review_snapshot.py verify \
  --manifest "$TEMP/dlr-review-snapshot-<ts>/manifest.json" \
  --allow-added docs/worklog/CODE_REVIEW_<date>.md
echo "verify rc=$?"
```

- rc=0 = PASS（无 changed / removed / 未允许的 added）；rc=2 = DRIFT；rc=1 = 脚本或 git 错误。
- `changed` 不等于「我改了」：并发包也会让文件变。逐条归属，写进报告 §7.3 或「我的改动集合」。
- 错误形态：把基线目录建在仓库内，收尾时它自己成为未跟踪文件，只读声明失效。

## 2. 冲突块普查（HEAD 与工作区）

```bash
# 总块数 / 文件数（路径含空格时 awk 按最后一个冒号切分仍成立）
git grep -c '^<<<<<<< ' HEAD | awk -F: '{s+=$NF; n++} END{print "HEAD blocks="s, "files="n}'
git grep -c '^<<<<<<< ' | awk -F: '{s+=$NF} END{print "worktree blocks="s+0}'
```

- `git grep -c` 无命中时 rc=1 且无输出；不要把它当命令失败。
- 只统计**跟踪文件**；未跟踪文件里的冲突标记不在结果内。
- 错误形态：逐文件 `git show` 循环统计，慢且容易漏；一次 `git grep` 足够。

## 3. 干净基线确认

```bash
git grep -c '^<<<<<<< ' <ref>
echo "ref rc=$?"   # rc=1 = 无冲突块，可作为资产基线
```

若 ref 也有冲突块，继续向祖先回溯，直到 rc=1；在报告头部写明该 ref 与选择理由。

## 4. 资产增减：AST 符号集合，不比行数

单文件（最常用：怀疑某测试文件丢了用例）：

```bash
git show <clean-ref>:tests/test_ui_kit.py > "$TEMP/base_test_ui_kit.py"
.venv/Scripts/python.exe - "$TEMP/base_test_ui_kit.py" tests/test_ui_kit.py <<'PY'
import ast, sys

def names(path):
    with open(path, encoding="utf-8-sig", errors="replace") as fh:
        tree = ast.parse(fh.read(), filename=path)
    return {n.name for n in ast.walk(tree)
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))}

base, work = names(sys.argv[1]), names(sys.argv[2])
print("missing:", sorted(base - work))
print("added:", sorted(work - base))
print("base:", len(base), "work:", len(work))
PY
```

仓库级：对每个 `.py` 重复上述比较，或 `git archive <ref> | tar -x -C "$TEMP/<dir>"` 后在临时树与工作区之间比对。

- **必须**用已知无冲突块的 ref；用 HEAD 会把冲突副本里的重复 `def` 算成「基线更多」。
- 行数不可作判据：冲突态会整体抬高行数；注释/格式化也会改变行数而符号不变。
- 错误形态：`grep -c 'def test_'` 当集合差——冲突副本也计行，且改名/参数化会误判。

## 5. 门禁真实退出码

```bash
PYTHONUTF8=1 .venv/Scripts/python.exe scripts/run_gates.py > "$TEMP/gates.log" 2>&1
echo "gates rc=$?"
tail -40 "$TEMP/gates.log"
```

- 取 rc 的通用形态与「为什么不能用管道后的 `$?`」见 `dlr-dev-playbook/references/windows-readonly-source-probing/SKILL.md` §1，此处只登记 DLR 的门禁入口与版本记录口径。
- 审查期只跑与发现相关的单项门禁时同样逐条记录；本地工具版本与 `ci.yml` 常量未联网核对时，报告写「本地口径，未经 CI 同版本验证」。

## 6. 定点 pytest（不产覆盖率文件）

```bash
.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider --no-cov \
  tests/test_i18n_migration.py tests/test_ci_frontend_registration.py
echo "pytest rc=$?"
```

- 两个开关的**存在理由**（防 `.pytest_cache` / 防根目录 `.coverage`，以及覆盖率类门禁比 mtime 会被一次多余写入拒评）见 `dlr-dev-playbook/references/windows-readonly-source-probing/SKILL.md` §5，此处不复述。
- DLR 侧只需记三件事：解释器一律 `.venv/Scripts/python.exe`（系统 Python 缺 brotli/yaml，收集期直接 rc=2）；`--no-cov` 依赖 dev 组的 pytest-cov；不跑全量，全量留给整改轮。
- 定点子集的通过**不能**替代全量结论；报告 §9 要写「未跑全量 + 原因」。

## 7. 签名脚本钉定对账

```bash
.venv/Scripts/python.exe -c "import hashlib, pathlib; from src.utils import _JS_SHA256_EXPECTED as T; d=pathlib.Path('src/javascript'); [print(n, hashlib.sha256((d/n).read_bytes()).hexdigest()==e) for n,e in sorted(T.items())]"
```

- 期望 5/5 `True`；失配先看 `dlr-domain-constraints/references/js-signature-pin-byte-parity/SKILL.md`（字节级还原、严格态复跑、锁的变异验证）。
- 不得反向改钉定值去迁就盘上内容；那会把「被篡改」洗成「合法」。

## 8. 悬空回归锁引用

```bash
git grep -nE 'test_regression_2026_(09_22|09_29|10_18|10_21)_[a-z_]+\.py' -- . \
  ':(exclude)CODE_WIKI.md' ':(exclude)CODE_WIKI_EN.md' ':(exclude)docs/changelog/*'
```

- 命中即「注释/文档指向已改名或不存在的锁」；报告里给文件名与符号，不抄旧行号。
- 文档历史条目里的旧名是语义本体，排除后仅剩活引用。

## 9. 同源锁族（历史 4 个红点全由它们抓出）

```bash
.venv/Scripts/python.exe scripts/check_annotations.py > "$TEMP/ann.log" 2>&1; echo "annotations rc=$?"
.venv/Scripts/python.exe scripts/compile_po.py --check > "$TEMP/po.log" 2>&1; echo "po rc=$?"
.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider --no-cov \
  tests/test_i18n_migration.py tests/test_i18n_catalog_coverage.py \
  tests/test_ci_frontend_registration.py
```

- 冲突解决后必须跑这一组；它们分别覆盖：注释锚点/密度、`.po ↔ .mo ↔ .json/.yaml` 键集合、`.mjs ↔ ci.yml` 登记。
- 命中 0 处也要在报告里写「实测 0 处」，不要用沉默代替覆盖。

## 10. 临时探针与路径

- 三类形态（`/tmp` 与 Windows 解释器不同目录、含转义探针的落盘退让、收尾逐个显式删除）一律见 `dlr-dev-playbook/references/windows-readonly-source-probing/SKILL.md` §2/§3，此处不复述。
- DLR 专属两点：`scripts/repo_review_snapshot.py` 不传 `--out` 时自行落 `%TEMP%` 且**拒绝写入仓库**，所以基线目录不用手拼路径；收尾清理范围受 `AGENTS.md`「测试收尾清理临时脚本」约束——只删本次任务产生的脚本与输出，`downloads/` `recordings/` `logs/` `backup_config/` 运行期产物与仓库 `scripts/` 一律不动。
- 守卫会按路径里的 `scripts/` 字面量误拦用户级目录的清理命令（`CODE_REVIEW_2026-10-29.md` M-13 同型）；被拦时列出残留路径交回用户，**不得绕钩**。
