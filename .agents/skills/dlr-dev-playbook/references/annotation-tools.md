# 注释检查工具详情

> 跑 `scripts/check_annotations.py` 或排查注释相关盲点时才需要读本节。
> 唯一事实源仍是 `AGENTS.md`；本文件展开工具命令表、排除项与盲点。

## 命令速查

| 命令 | 用途 |
| --- | --- |
| `python scripts/check_annotations.py` | 规范检查（禁 docstring、密度阈值、模块头） |
| `python scripts/check_annotations.py --snapshot DIR` | 建立基线快照 |
| `python scripts/check_annotations.py --baseline DIR` | 与基线比对，证明「只改了注释、未改逻辑」 |
| `python scripts/check_annotations.py --min-density N` | 自定义密度阈值（默认 13.0） |

## 等价性校验

- Python 比对 `ast.dump` 全量序列化；JS/CSS/HTML 剥离注释后比对有效代码行。注释与空行不参与。密度检查只对 Python 生效；前端注释按各自语言惯例。

## 排除项

`douyin_pb2.py`（protoc 生成）、`douyin_live_recorder_standalone.py`（历史遗留），以及 `__pycache__/node/ffmpeg/.venv/build/dist` 等目录。

## 三个盲点（工具发现不了，须另行检查）

1. **`except A, B:` 与 `except (A, B):` AST 完全相同**——无括号被改写成带括号不会被校验发现，`grep -c 'except [A-Za-z_][A-Za-z0-9_.]*, [A-Za-z_]' <file>` 核对。
2. **注释缩进错误不影响 AST**，只有 `black --check` 能发现——必须与 black 配套。
3. **换行符形态变化对两者完全隐形**：`ast.parse` 把 `\r\n` 与 `\n` 视为同一行尾，black 按文件首个行尾为准。本仓 CRLF/LF 混存（`main.py`/`src/web_api.py`/`gui.py`/`i18n.py` 等纯 CRLF，部分 `tests/*.py` 纯 LF），整文件 `Path.write_text()` 重写会静默转 LF。判据（改任何文件前后各跑一次，两侧「原本为 0 的那项」必须仍为 0）：`python -c "import pathlib;b=pathlib.Path(f).read_bytes();print(b.count(b'\r\n'), b.count(b'\n')-b.count(b'\r\n'))"`。连带后果：按原文匹配 `\n\n` 的断言遇纯 CRLF 源文件恒不匹配（前端 MIN-2241 曾因此长期红，锚点已改 `\r?\n\r?\n`）。
