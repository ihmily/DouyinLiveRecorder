# 静态检查结论的实测裁定

用于判定「某个静态检查/审查结论到底成不成立」。核心原则：**不采信任何静态推断的语法结论，用项目解释器实测裁定**。

## 适用与排除

- **适用**：代码审查代理、静态扫描工具或真人 reviewer 报告「`except A, B:` 是 Python 2 语法，模块无法导入」这类结论；或任何需要判定「这段代码到底有没有语法/类型错误」的场合。
- **不适用**：真有 Traceback 的运行时异常（走 systematic-debugging）。

## 通用裁定流程

不管被质疑的是什么结论，都按这四步走：

**Step 1 — 用项目解释器实测**（不要用 PATH 上的 `python`，用仓库自己的解释器）：

```bash
.venv/Scripts/python.exe -V                       # 确认真实版本
.venv/Scripts/python.exe -c "import compileall; print(compileall.compile_dir('src', quiet=1))"
```

**Step 2 — 处置**

- 编译/检查通过 → 判定为**假阳性**，直接剔除，**不要「顺手修一下」**。
- 编译/检查失败 → 才是真问题，按报错行号继续。

**Step 3 — 清理裁定残留（强制）**

`compileall.compile_dir` 会在被编译目录里生成 `__pycache__/*.pyc`；为反证另写的最小复现脚本（如 `_pep758_repro.py`）同样属于临时文件。裁定结束后按 SKILL.md 铁律 1 删除：`rm -f <复现脚本>` 并清掉本次产生的 `__pycache__`，最后 `git status --porcelain` 确认无预期外新增。项目已 gitignore 的 `__pycache__` 本身无害，但**新出现**的一次性脚本必须归零。

**Step 4 — 反向提醒**

确认是假阳性后，提醒自己**不要**按错误结论去改代码——在本仓，把无括号写法改成带括号反而过不了 `black --check`。

## 高发案例：PEP 758 无括号多异常

### 根因

`except A, B:`（多异常不带括号）是 **PEP 758** 正式语法，**Python 3.14 起合法**：

```python
# 3.14+ 合法（PEP 758）
except configparser.NoSectionError, configparser.NoOptionError:
# 3.13 及以下：SyntaxError: multiple exception types must be parenthesized
```

多数模型的训练语料以 3.13 及以下为主，会把无括号写法**误判成 Python 2 语法**。这是高复发率的假阳性——同一批分域审查代理中，往往只有部分代理踩坑、另一部分正确排除，**这本身就是「该结论不可采信」的信号**。

### 本仓处置口径

- 用上面的 Step 1 实测裁定。编译通过即为假阳性，剔除结论，不改代码。
- **在本仓不要**把无括号写法改成带括号：`black 26.x` 稳定风格会把能放进一行的 `except (A, B):` 改写回无括号形式，加括号反而过不了 `black --check`。
- `AGENTS.md` 的「except 多异常写法（PEP 758）」条目是权威说明；测试侧同样要求新代码写 `except A, B:`（见 `testing-conventions.md` 第 9 节）。

### 已知盲点

`except A, B:` 与 `except (A, B):` 的 **AST 完全相同**，所以「注释/逻辑等价性校验」（`ast.dump` 全量比对）**发现不了**无括号写法被改成带括号。必须额外 grep 计数核对：

```bash
grep -c 'except [A-Za-z_][A-Za-z0-9_.]*, [A-Za-z_]' <file>
```

## 同类结论的处理提示

- **平台专属符号报错**（`attr-defined` / `name-defined`）不是假阳性，要用 `sys.platform` 门控真修 → `platform-type-gating.md`。
- **lint 结论**（ruff 的 F401/E741）一般是真的，要修；但 **E402**（import 前初始化 config/logging）在本仓是**有意**的，不要动。
- 无论哪一类，最终都要回到 SKILL.md「统一验证门禁」跑一遍 `python scripts/run_gates.py` 收口。
