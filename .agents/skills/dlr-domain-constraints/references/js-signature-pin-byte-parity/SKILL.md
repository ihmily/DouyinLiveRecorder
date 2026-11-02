---
name: js-signature-pin-byte-parity
description: 'DouyinLiveRecorder 签名脚本钉定（第③类）的字节级对账与还原 playbook。当修改或清理 src/javascript/*.js、出现「SHA256 与钉定值不符」告警、设置 DLR_JS_STRICT_HASH=1、平台突然表现为「未开播」且无堆栈、怀疑 git 冲突回退或行尾归一改了脚本字节、需要补或验证 JsPinTable 字节对账锁时使用。涵盖逐文件 sha256(read_bytes()) 对账、git show + write_bytes 字节级还原、新锁先证红后转绿、默认态与严格态复跑，以及 trace_error_decorator 把 RuntimeError 伪装成 {"is_live": False} 的核对。'
---

# 签名脚本钉定：字节对账与还原

## 定位与边界

本 Skill 是 DouyinLiveRecorder **第③类钉定面（签名脚本层）** 的取证与修复执行手册：

- 事实源：`src/utils.py::_JS_SHA256_EXPECTED` 对 `src/javascript/*.js` 的**原始字节**摘要。
- 边界声明（三类钉定互不覆盖）见 `../pin-categories.md`；本 Skill 不复制门禁清单。
- 发布期运行时二进制（ffmpeg/node）与运行期 TOFU 安装不在此范围，走 `dlr-domain-constraints`。
- 约束本体仍在项目 `AGENTS.md`；冲突时以 `AGENTS.md` 为准。

## 何时触发

- 修改、清理、重排 `src/javascript/*.js`（含只改注释、只删调试打印）。
- 运行期出现「签名脚本 X 的 SHA256 与钉定值不符」告警。
- 设置或准备设置 `DLR_JS_STRICT_HASH=1`。
- 某平台（如 LiveMe）突然表现为「主播未开播」，日志无堆栈、无异常。
- 怀疑 stash 冲突解决、行尾归一（`.gitattributes`/pre-commit）、编辑器保存改了脚本字节。
- 需要新增或复核 `tests/test_utils.py::TestJsPinTable` 的字节对账锁。

## P0 取证：全表对账，只看字节

禁止只看报警的那一份；必须对全表逐文件核对。仓库根目录用项目 venv 执行：

```python
import hashlib
from pathlib import Path
from src.utils import _JS_SHA256_EXPECTED

js_dir = Path("src/javascript")
for name, expected in sorted(_JS_SHA256_EXPECTED.items()):
    p = js_dir / name
    raw = p.read_bytes()
    actual = hashlib.sha256(raw).hexdigest()
    print(name, "MATCH" if actual == expected else "MISMATCH", len(raw), "B",
          "CRLF", raw.count(b"\r\n"), "LF", raw.count(b"\n"), "console.log", raw.count(b"console.log"))
```

判定口径：

- **MATCH 唯一判据**是 `sha256(read_bytes()) == 表值`；文件存在、键集相等、字节数看起来正常都不算。
- 同时记录字节数 / CRLF / 裸 LF / `console.log` 次数，用于区分「行尾漂移」与「内容回退」。
- `get_compiled_js` 按 `(路径, mtime)` 缓存；同进程内改盘后若 mtime 未变可能读到旧编译产物，复核请用新进程。

## P1 归因：三种情形，处置完全不同

| 情形 | 判据 | 处置 |
| --- | --- | --- |
| 有意修改脚本 | 改动可归因到本轮编辑；表值对应旧内容 | **同批重算表值**，在表项注释注明来源版本/日期；再跑锁与两态复跑 |
| 无意改动 | 表值在历史 blob 可达；盘上内容是被回退的旧副本 / 行尾被归一 / 尾字节被追加 | **字节级还原，不改表** |
| 无法判定 | 表值与盘上内容都无法归因 | 停机交回用户，不猜、不改表、不覆盖文件 |

硬规则：**不得反向改表值去迁就盘上内容**。把「被回退的旧副本」写成新基线，等于把篡改面洗白成合法状态。

## P2 还原：git show + write_bytes

`.gitattributes` 对 `src/javascript/*.js` 钉了 `-text`（双向禁 eol 转换），任何手工编辑、`read_text()`/`write_text()`、行尾归一都会改变字节并翻表。

1. 找候选提交并**先验摘要**：

```bash
git log --oneline --all -- src/javascript/liveme.js
git show <ref>:src/javascript/liveme.js | sha256sum   # 必须等于表值
```

2. 用 Python 取同一份字节并写回，避免文本层转换：

```python
import hashlib
import subprocess
from pathlib import Path

from src.utils import _JS_SHA256_EXPECTED

ref, rel = "<已验证的提交>", "src/javascript/liveme.js"
raw = subprocess.run(["git", "show", f"{ref}:{rel}"], check=True, stdout=subprocess.PIPE).stdout
assert hashlib.sha256(raw).hexdigest() == _JS_SHA256_EXPECTED[Path(rel).name]
Path(rel).write_bytes(raw)
```

3. 写回后四项终态核对：字节数、SHA256、CRLF/裸 LF 计数、`console.log` 计数。恢复后 `git status` 会显示该文件被修改，这是预期；**不要自动提交**，把状态交回用户。

不要用「改动失败 → 顺着盘上版本改表」收尾；也不要用 `git checkout` 覆盖工作区里尚未确认的并发改动。

## P3 回归锁：先证红，再转绿

现有 `TestJsPinTable` 的三把锁只覆盖「登记面」：

- `test_dead_scripts_are_unpinned`：键集；
- `test_pinned_scripts_exist`：表里的键都有文件；
- `test_every_executable_js_is_pinned`：目录 `*.js` 与表键**双向相等**。

它们不比对实际字节，因此内容漂移时 pytest 仍全绿。值面锁是：

```python
import hashlib
from pathlib import Path

import src.utils as utils_module


def test_pinned_bytes_match_the_table(self) -> None:
    js_dir = Path(__file__).resolve().parents[1] / "src" / "javascript"
    stale: list[str] = []
    for name, expected in sorted(utils_module._JS_SHA256_EXPECTED.items()):
        actual = hashlib.sha256((js_dir / name).read_bytes()).hexdigest()
        if actual != expected:
            stale.append(f"{name}: 期望 {expected} 实际 {actual}")
    assert not stale, "签名脚本内容与钉定值不符……" + "; ".join(stale)
```

新增或改写该锁时**必须先在未修复态跑一次**：

- 期望结果：只点名真正失配的文件（其余文件不误报），并给出期望/实际摘要；
- 再修复，同一用例转绿；
- 没有这次「先红」证据，就无法区分「锁生效」与「锁没接上」。

## P4 运行期两态复跑

用项目自己的 loader（项目 venv，且 node/execjs 可用），**绝对路径**（生产写法 `f"{JS_SCRIPT_PATH}/liveme.js"`）：

```python
import asyncio
from src import JS_SCRIPT_PATH, utils

async def main():
    return await utils.run_js_async(
        f"{JS_SCRIPT_PATH}/liveme.js", "sign", "<room_id>", f"{JS_SCRIPT_PATH}/crypto-js.min.js"
    )

print(asyncio.run(main()))
```

- **默认态**：应无「与钉定值不符」告警；返回含 `lm_s_sign`（32 位十六进制）的 dict。
- **严格态**：进程启动前设 `DLR_JS_STRICT_HASH=1`（接受 `1`/`true`/`yes`，大小写不敏感）。钉定匹配时应正常返回签名；失配时 `_check_js_hash` 抛 `RuntimeError`。未登记脚本只告警、不拒绝。
- **必须核对装饰器伪装**：`trace_error_decorator` 会把异常吞成 `{"is_live": False}`。若只调用被装饰的 `spider.get_liveme_stream_url` 并看 `is_live`，严格态拒执行会被误读成「主播未开播」。核对方式：直接调 `run_js_async`，或同时检查日志里的 `RuntimeError`。
- 探针必须用绝对路径：`require` 按 CWD 解析，相对路径会报 `Cannot find module 'src/javascript/crypto-js.min.js'`，把「路径写错」误判成「签名链坏了」。

## 完成判据

1. 全表逐文件 MATCH（不是只看本次改动的那一份）。
2. 值面锁先红后绿；红态输出点名失配文件。
3. 默认态与严格态都能产出签名；默认态无假告警。
4. 门禁走项目唯一入口 `python scripts/run_gates.py`；命令清单以 `AGENTS.md`「格式化命令」为唯一事实源，本 Skill 不复制。
5. 涉及真实平台解析时，按 `AGENTS.md` 完成定义第 2 步跑真实 URL；未执行就记 `SKIP(原因)` 并交回用户，**不得宣布完成**。

## 常见误用（Red Flags）

- 反向改表值迁就盘上内容，把被回退的旧副本变成新基线。
- 只核对报警的那一个文件，不证明其余脚本仍匹配。
- 用文本编辑器 / `read_text()` + `write_text()` / 行尾归一「还原」脚本。
- pytest 全绿就宣布修好（缺值面锁时全绿没有意义）。
- 严格态只看调用方 `is_live`，忽略 `trace_error_decorator` 的伪装。
- 探针用相对路径，把 `require` 解析失败误报成签名链故障。
- 在 bash 里用内联 `python -c` 写含反斜杠/引号的探针；应写到 `%TEMP%` 下的临时脚本执行，用完删除。

## 资源

- `references/incident-2026-10-29.md`：liveme.js 钉定失配事故的完整读数、因果链、修复与验证留痕、工具坑。
