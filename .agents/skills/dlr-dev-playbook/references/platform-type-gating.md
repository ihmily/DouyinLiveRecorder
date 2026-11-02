# 平台专属类型的静态检查门控

处理 `ctypes.windll`、`subprocess.STARTUPINFO` 这类**只存在于 Windows typeshed** 的符号在 Linux/macOS CI 上报错的问题。

## 原理

`mypy` 是**平台感知**的：位于字面量 `if sys.platform == "win32":` 分支内的代码（或 `if sys.platform != "win32": return` 之后的代码），在检查其他平台时会被**整段跳过**。而平台专属符号只存在于 Windows typeshed，任何落在此类分支之外的引用都会让 Linux/macOS 检查失败。

典型失败特征：CI（ubuntu-latest）上 `mypy src/` 报 3-6 个错，而开发者本机 Windows 全绿：

```text
src/web_tray.py:111: error: Module has no attribute "windll"  [attr-defined]
main.py:750: error: Name "subprocess.STARTUPINFO" is not defined  [name-defined]
main.py:755: error: Module has no attribute "STARTUPINFO"  [attr-defined]
```

## 诊断流程

1. **确认错误只与平台有关**：符号名命中 Windows 专属 API（清单见下表）。同一条 `mypy` 命令 Windows 本机过、Linux/macOS CI 失败，几乎可以确定缺了 `sys.platform` 门控。
2. **检查周边代码**：在同一文件/项目里找该符号的其他用法。如果兄弟用法都包在 `if sys.platform == "win32":` 里且不报错，把出错代码改成同一写法即可——**这是最快的确认方式**，项目既有约定已经给出了正确的形状。
3. **确认出错文件是否真的在检查范围内**：`mypy <dir>/` 会顺着 import 走——被检查模块内的函数级 `import main` 会把根目录 `main.py` 一起拉进检查。先确认 import 链，别想当然以为文件不在范围内。
4. **判断用哪种修复**：仅函数体内访问了该符号，还是**类型注解**引用了它。

## 常见 Windows 专属符号（会让 Linux/macOS mypy 失败）

| 符号 | Linux/macOS 上的典型报错 |
|---|---|
| `ctypes.windll`（`.user32`、`.kernel32` …） | `Module has no attribute "windll" [attr-defined]` |
| `subprocess.STARTUPINFO` | `Name "subprocess.STARTUPINFO" is not defined [name-defined]` / `Module has no attribute "STARTUPINFO" [attr-defined]` |
| `subprocess.STARTF_USESHOWWINDOW`（及其他 `STARTF_*`） | `Module has no attribute "STARTF_USESHOWWINDOW" [attr-defined]` |
| `ctypes.wintypes`、`msvcrt`、`winreg`、`mmsystem` 等 | `Module has no attribute ...` / `Cannot find implementation or library stub` |
| `os.startfile`、带 `signal.CTRL_BREAK_EVENT` 的 `os.kill` | attribute / argument 类型错误 |

**关键事实：**

- `ctypes.windll` 与 `subprocess.STARTUPINFO` 在 typeshed 中**只存在于 win32 平台分支**。
- `sys.platform` 的**字面量**比较（`==`、`!=`、`in`）会被 mypy 与 pyright/basedpyright 按当前/配置的平台求值，不匹配的分枝整段跳过（分支内代码根本不参与类型检查）。
- 模块级 `if sys.platform == "win32": X = <win-only-symbol>` 在 Linux 上运行时安全，因为该分支根本不执行——与裸的模块级引用不同。
- 字符串注解（`"subprocess.STARTUPINFO | None"`）只推迟**运行时**求值，mypy 仍会解析并检查，躲不掉 `name-defined`。
- 像 `if system_type == "nt":` 这种对**运行时字符串**（如 `os.name`）的判断**不会**门控 mypy——它无法折叠非字面量。必须用 `sys.platform` 字面量。

## 修复模式 1 —— 仅函数体内访问：用 sys.platform 字面量门控

只用到平台 API、没有任何注解引用它时：

```python
def _patch_console_window(self) -> None:
    if sys.platform != "win32":
        return
    try:
        import ctypes
    except Exception:
        return
    user32 = ctypes.windll.user32  # 仅在 win32 下被检查
    ...
```

提前 return 不好写时，也可以直接内联包住调用点：

```python
if sys.platform == "win32":
    import ctypes
    user32 = ctypes.windll.user32
    user32.ShowWindow(hwnd, SW_RESTORE)
```

**优先用提前返回形式**（`!= "win32": return`）——diff 最小，也最贴合「仅 Windows 特性」的意图。`==` 与 `!=` 两种对 `sys.platform` 的字面量比较，mypy 与 pyright/basedpyright 都能识别。

## 修复模式 2 —— 注解引用了平台符号

像 `-> "subprocess.STARTUPINFO | None"` 这样的返回注解，**即使写成字符串也会被 mypy 解析并做类型检查**——字符串只推迟运行时查找，不推迟静态检查，照样报 `name-defined`。由于该符号在非 Windows typeshed 里**根本不存在**，它永远无法作为精确的跨平台类型被引用。

### 首选：把返回类型降级为 `object | None`

当值只是被不透明地透传时（例如 `subprocess.Popen(..., startupinfo=get_startup_info(...))`，而 typeshed 对 `startupinfo` 的类型本就很宽松），精确类型带不来任何收益。直接去掉别名，标注 `object | None`，并在**函数体**里保留 `sys.platform` 门控（模式 1），使构造过程本身仍被平台门控：

```python
def get_startup_info(system_type: str) -> object | None:
    if system_type != "nt":
        return None
    if sys.platform == "win32":
        startup_info = subprocess.STARTUPINFO()
        startup_info.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        return startup_info
    return None
```

这是**唯一**在 mypy（任意平台）与 basedpyright strict 下都干净的形式，且 diff 最小。

### 有 basedpyright 时，不要用模块级 sys.platform 条件类型别名

下面这种看似等价的写法能过 mypy，却会让 **basedpyright strict** 报 `reportInvalidTypeForm`（"Variable not allowed in type expression"）——basedpyright 把条件分支赋值当成运行时**变量**而非类型别名，不会把两个分支合并成一个别名：

```python
# mypy 干净，但 basedpyright strict 会在 _StartupInfoType 上报 reportInvalidTypeForm：
if sys.platform == "win32":
    _StartupInfoType = subprocess.STARTUPINFO
else:
    _StartupInfoType = object

def get_startup_info(system_type: str) -> _StartupInfoType | None: ...
```

补 `TypeAlias`（`_StartupInfoType: TypeAlias = ...`）**也修不好**——basedpyright 依然拒绝条件别名（还会额外报大写常量重定义）。`if TYPE_CHECKING:` 同样无效，因为 **mypy 始终把 `TYPE_CHECKING` 求值为 `True`**，在 Linux 上仍会解析 `subprocess.STARTUPINFO` 并报 `attr-defined`。basedpyright 唯一接受的别名形式是无条件的 `TYPE_CHECKING`/`TypeAlias` 模式——而这恰恰是 mypy 无法用于平台专属符号的形式。

**结论**：平台专属类型优先用 `object | None`；只有当下游消费者确实需要具体类型**且**没有强制 basedpyright 时，才考虑精确别名。

让 `object | None` 安全的前提：

- `else`/兜底必须是具体类（`object`），**绝不能是 `Any`**——basedpyright strict 会报 `Any` 泄漏（`reportUnknownMemberType` 等）。
- 函数体必须在 `sys.platform == "win32":` 字面量分支内构造该值。
- 运行时行为保持不变：非 Windows 路径仍返回 `None`。

## 不要用 `# type: ignore` 处理这类问题

`# type: ignore[name-defined]` 在 Linux 上压掉了错误，但在 Windows 上**完全没必要**，basedpyright strict 反而会在同一行报 `reportUnnecessaryTypeIgnoreComment`。也就是说这个 ignore 在任一平台上都是错的。**`sys.platform` 分支是唯一两边都干净的修法。**

## 真实案例

### 案例 1 — 托盘模块里的 ctypes.windll（`web_tray.py`）

改前：`_patch_console_window()` 与 `_on_show()` 裸引用 `ctypes.windll.user32` → Linux 上 3 个 `attr-defined`。

改后：

```python
def _patch_console_window(self) -> None:
    if sys.platform != "win32":
        return
    try:
        import ctypes
    except Exception:
        return
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    ...

def _on_show(self, _icon: "object | None" = None, _item: "object | None" = None) -> None:
    hwnd = self._hwnd
    if not hwnd:
        return
    if sys.platform == "win32":
        import ctypes
        user32 = ctypes.windll.user32
        user32.ShowWindow(hwnd, SW_RESTORE)
        ...
```

### 案例 2 — `subprocess.STARTUPINFO` 返回注解（`main.py`）

改前（3 个错：注解行 1 个 `name-defined`，函数体 2 个 `attr-defined`）：

```python
def get_startup_info(system_type: str) -> "subprocess.STARTUPINFO | None":
    if system_type == "nt":
        startup_info = subprocess.STARTUPINFO()
        startup_info.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    else:
        startup_info = None
    return startup_info
```

改后：见修复模式 2（`object | None` + 函数体内 `sys.platform` 门控 + `if system_type != "nt": return None` 提前返回）。

## 验证（强制）

mypy 必须跑两遍——一遍模拟 CI 平台，一遍用本地平台：

```bash
mypy --platform linux src/   # 或 darwin —— 模拟 CI
mypy src/                    # 本地平台（Windows 开发机上是 win32）
```

两遍都必须输出 `Success: no issues found`。另外跑 `python -m py_compile <改动文件>`。

改动涉及运行时可见的函数时，再补一个小的**行为检查**证明没有行为漂移：Windows 上 `get_startup_info("posix")` → `None`，`get_startup_info("nt")` → 带预期 flags 的对象（`dwFlags == 1`，即 `STARTF_USESHOWWINDOW`）。

行为检查优先写成 `python -c "..."` 内联；若落盘成临时脚本，或 `py_compile` / `compileall` 产生了 `__pycache__`，收尾按 SKILL.md 铁律 1 删除。

## 相关：pyright / basedpyright 严格模式注意事项

- basedpyright strict 会启用 `reportUnnecessaryTypeIgnoreComment` —— 在 Linux 上必需的 `# type: ignore` 在 Windows 上变成「不必要」。故：永不用 `type: ignore` 压平台符号，一律用 `sys.platform` 门控。
- 严格模式还启用 `reportUnknown*` 规则 —— 非 Windows 占位类型绝不写 `Any`，用 `object` 这类具体类。
- pyright/basedpyright 按运行检查的解释器解析 `sys.platform`（平台感知），因此同一套分支门控对两个工具都有效。
