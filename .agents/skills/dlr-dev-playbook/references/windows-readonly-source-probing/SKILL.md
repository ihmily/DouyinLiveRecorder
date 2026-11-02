---
name: windows-readonly-source-probing
description: Windows + Git Bash 下做只读取证（跑门禁取退出码、AST/文本扫描、定点 pytest、写一次性探针）时的失败形态与安全替换配方。当出现 python -c 报 SyntaxError unterminated string literal、bash 报 unexpected EOF while looking for matching `、管道后 $? 把门禁读数全读成 0、探针样例被仓库 PreToolUse 删除面守卫拦下、ast.dump 子串匹配判出大量假阳、或定点 pytest 顺手产出 .coverage / .pytest_cache 残留时使用此 Skill。仅限只读取证与读数核对，不覆盖写入型重构与批量文本替换。
---

# Windows 只读取证配方

## 适用范围

- 只做**取证与读数**：跑检查命令取真实退出码、写一次性扫描探针、跑定点测试子集。
- 不推翻所在仓库既有的「优先不落盘」默认（若存在）。第 2 节的落盘形态**只在触发条件成立时**使用。
- 与「哪个命令答哪类问题」正交：本 Skill 讲工具层与判据本身会怎样骗人，不讲判据选型。

## 1. 退出码：绝不用管道后的 `$?`

失败形态：`<cmd> | tail -20` 之后 `$?` 取到的是 `tail` 的 rc。红的那条恰好会被读成 0——门禁全绿是假象。

安全形态（逐条门禁各取一次 rc，读数与结论一起进回复）：

```bash
PYTHONUTF8=1 python -m black --check --line-length 120 --target-version py314 . > "$TEMP/g-black.log" 2>&1
echo "black rc=$?"
tail -20 "$TEMP/g-black.log"
```

- 日志落 `$TEMP`，不落仓库根。
- 确实需要管道且要左侧 rc 时才用 `set -o pipefail`；优先重定向形态（`pipefail` 在不同 shell 下语义不一致）。
- 汇报格式写成 `<name> rc=N`，每个读数附「取数时刻 + 可复跑命令」——并发会话在改盘时，只有带时刻的读数能被复核。

## 2. 含转义内容的探针：先判触发条件

三类失败都出自工具层吃掉转义，不是被测代码的问题：

| 症状 | 根因 |
| --- | --- |
| `SyntaxError: unterminated string literal`（`python -c` 里的 `replace('\', '/')` 形态） | 反斜杠在参数传递层被折叠 |
| `/usr/bin/bash: eval: line N: unexpected EOF while looking for matching ``'` | 命令串里的反引号被当命令替换 |
| 多行 `python -c "…"` 报 rc=2 或 rc=127 且**零输出** | 引号参数内的换行被压平成一行 |

**触发条件**（满足任一条才落盘，否则维持内联，别为了「看起来稳」造文件）：内容含反斜杠转义序列 / 含反引号 / 是多行体。

安全形态三档，按序退让：

```bash
cat > "$TEMP/probe.py" <<'PY'
print("ok")
PY
.venv/Scripts/python.exe "$TEMP/probe.py"
```

1. **引号 heredoc**（`<<'PY'`）。体内**仍不得写反斜杠转义**——需要换行用 `chr(10)`、需要反斜杠用 `chr(92)`；终止符必须独占一行，所以别把 `;` 拼在尾部语句里。
2. **Write 工具直写 `%TEMP%`**：内容按字面落盘，转义最不易变形；但工作区外写入在部分权限档会被拒，被拒即退回第 1 档。
3. **仓库内 `_tmp_*.py`**（最后手段）：会被 black / isort 收编，**跑门禁前**就得删，不是跑完再删——先删再跑，否则第一条红就是自己的杂散文件。

收尾：`rm -f <逐个显式路径>`。不要为此 `mkdir` 到 `%TEMP%`，不要写递归或无过滤删除。

## 3. 路径归一：`as_posix()`，不用 `replace`

第 2 节表里第一条 SyntaxError 就是这个写法最先炸。

```python
from pathlib import Path

root = Path(".").resolve().as_posix()
```

- Git Bash 的 `/tmp` 与 Windows 解释器的 `/tmp` **不是同一目录**：bash 重定向落到 `C:\Users\<user>\AppData\Local\Temp`，而 Windows 侧 Python 把 `/tmp/x` 解析成 `C:\tmp\x`。
- 症状形状：工具 rc=0 却「没产出」。判据用 `cygpath -w /tmp/x` 复算真实路径，别先怀疑工具没跑。
- 跨 bash 与 Windows 解释器传文件：先 `cygpath -w` 取绝对 Windows 路径，再以 argv 传进去，别在脚本里硬编码 `/tmp`。

## 4. AST 判定：按节点身份，不按 dump 子串

失败形态：判「`open()` 是否漏 close」时在 `ast.dump()` 文本里搜 `id='open'`。`with open(...)` 和裸 `open(...)` 两份 dump **完全同形**，正常写法会被全量报成泄漏。

实测（venv 3.14，两份样本各含一次 `open`）：子串 `id='open'` 命中数 `with` 形态 = 1、裸形态 = 1（无法区分）；改按节点身份 + 祖先上溯，`with` 形态 0 处、裸形态 1 处。

```python
import ast


def unmanaged_open_calls(src: str) -> int:
    tree = ast.parse(src)
    parent = {c: n for n in ast.walk(tree) for c in ast.iter_child_nodes(n)}
    leaks = 0
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "open":
            cur, inside = node, False
            while cur in parent:
                cur = parent[cur]
                if isinstance(cur, ast.withitem):
                    inside = True
                    break
            leaks += 0 if inside else 1
    return leaks
```

- 推广口径：dump 子串只配用于「整棵树里存在/不存在某节点类型」这一级；凡判据涉及「这个节点在不在那个结构里面」，一律走父节点链。
- 反向例外：判「注释/逻辑等价性」用 `ast.dump()` 全量比对是另一个合法用途，但它对 `except A, B:` 与 `except (A, B):` 这类 **AST 相同** 的改写完全隐形——那需要额外 grep 计数。
- 语法/AST 检查一律用仓库 venv 的解释器；低一个次版本的 Python 会对本仓的无括号 `except` 写法误报语法错误。

## 5. 定点 pytest：不留覆盖率与缓存

```bash
.venv/Scripts/python.exe -m pytest -p no:cacheprovider --no-cov tests/test_<module>.py
```

- 三个易踩点：
  1. 必须用仓库 venv 解释器——系统 Python 缺包会在**收集期**就 rc=2，形状与「测试挂了」不同但极易误判成代码回归。
  2. `-p no:cacheprovider` 防 `.pytest_cache/`，`--no-cov` 防根目录 `.coverage`。实测这两个开关下重跑，`.pytest_cache` 与 `.coverage` 的 mtime **逐位不变**。
  3. 后果不止脏 diff：新鲜度类门禁比的就是数据文件 mtime vs 源码 mtime，一次多余的 `.coverage` 写入足以让下一轮评审拿到「数据陈旧」红。
- 从 Bash 直跑 pytest 时，起子进程的用例可能报 `OSError: [WinError 6]`（继承已关闭的 stdin）。「整文件红、单条 `-k` 绿」优先按环境伪影判，别当回归查。
- 需要覆盖率读数但不想改仓库数据文件：`COVERAGE_FILE` 指到 `%TEMP%` 再跑。

## 6. 探针样例里的删除动词字面量

**条件**：仅当所在仓库装了按正则扫整条命令串的删除面守卫（典型 token：`rm` 的递归+强制开关组合、`git clean` 带 `-f`）。这类守卫不区分「这只是样例」和「真要执行」，所以取证样例里的字面量同样会被拦。

做法：

- 样例改写成**不含删除动词**的形态——要指代该 token 时拆成拼接（`"R" + "m"`）或纯文字描述。
- 要验证守卫本身的行为，走守卫自带的自测入口（如 `--self-test`）或它的离线用例，不要靠真实命令串触发。
- 别因为被拦就绕钩（加 `|| true` 之类）；判定逻辑本身可疑时，把现象交回用户。
- 分层要记清：仓库守卫与 CLI 权限分类器是**两层**拦截，后者还会拦多主机 URL 枚举、`python -c` 里的删除循环、故意 `sleep` 等待——被拦时先分清是哪一层，别把权限档的拒绝写成「工具坏了」。

## 收尾自查

- `git status --porcelain` 无本轮新增未跟踪残留。
- 未被创建/改动：`.coverage`、`.pytest_cache/`、`__pycache__/`、仓库根 `_tmp_*.py`。
- 运行期产物目录与他人的在途改动一律不动；发现预期外条目先上报，不擅自还原。
- 每个读数带「时刻 + 复跑命令」；做不到的部分明确写「未执行 + 原因」，不宣称取证完成。
