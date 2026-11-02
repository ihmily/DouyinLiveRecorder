# 刻意设计白名单（派发时代理必读）

## 使用规则

1. 白名单只豁免「本项目有意为之」的形态，**不豁免已知缺陷**。
2. 每条豁免都必须能在仓内找到出处（AGENTS.md 章节、测试锚点、源码注释、历史审查报告）。出处与代码现状矛盾时，**按缺陷报**，并同时指出「文档承诺与实现不符」。
3. 代理不得自行新增豁免；拿不准的写成「观察（疑似刻意设计，出处待核）」，由主控仲裁。
4. 命中的条目只能记「观察」，不得作为 S/M；要判缺陷，必须先引用出处并证明代码违反了它。

## 清单

| # | 形态 | 为什么不是缺陷 | 权威出处 |
| --- | --- | --- | --- |
| 1 | `except A, B:` 无括号 | Python 3.14 的 PEP 758 合法写法，不是 Python 2 语法 | `AGENTS.md`「代码风格 / except 多异常写法」；`dlr-dev-playbook` 铁律 2 |
| 2 | `main.py` 里同名变量在模块级注解声明、函数内再次赋值 | 声明与初始化分离 + 热更新重赋值，不是重复定义 | `CODE_REVIEW_2026-10-29.md` §7.2（`enable_https_recording`） |
| 3 | `src/web_tray.py` 的 `os._exit(0)` | 仅用于「没有可关的 server」分支，绕过 Qt 清理是刻意选择 | `CODE_REVIEW_2026-10-29.md` §7.1 4.3 |
| 4 | `except X: pass` 且 ±4 行内有归因注释 | 仓内 59 处此类形态，属观察项；只有「无注释 + 吞掉异常改变返回值」才升级 | `CODE_REVIEW_2026-10-29.md` §7.1 4.4 |
| 5 | 未开播轮次静默；`trace_error_decorator` 把异常吞成 `{"is_live": False}` | 多数平台解析函数返回含 `is_live` 的 dict，静默是「正常轮次不刷屏」的既定契约；返回 str/tuple/None 的函数应改用 `trace_error_decorator_or_none` | `src/utils.py::_make_trace_error_guard` 注释；`CODE_WIKI`/历史审查记录 |
| 6 | LiveMe 的 `status == "0"`（字符串）、来秀 `playStatus == 0` 的反向语义 | 平台协议差异，比较写法刻意保留 | `tests/test_spider_hardening.py` 的对照注释 |
| 7 | JS 钉定默认只告警、`DLR_JS_STRICT_HASH=1` 才拒绝；`x-bogus.js` 里 `eval("require('crypto')")` | 双档是刻意设计（默认不打断用户，加固场景可收紧）；`eval` 是混淆脚本固有形态 | `src/utils.py::_check_js_hash`；`dlr-domain-constraints/references/js-signature-pin-byte-parity/SKILL.md` |
| 8 | `src/javascript/*.js` 被 `.gitattributes` 钉成 `-text`，行尾不归一 | 钉定表对**原始字节**求 SHA256，任何行尾归一都会翻表 | `.gitattributes`；`src/utils.py::_JS_SHA256_EXPECTED` |
| 9 | 每房间一线程、每轮 `asyncio.run`，配 `semaphore` 限流 | 仓内既定并发模型；`run_js_async` 等把阻塞段丢线程池，避免冻结房间事件循环 | `src/utils.py::run_js_async` 注释；`AGENTS.md` 并发约束（详见 `dlr-dev-playbook/references/concurrency-model.md`） |
| 10 | `run_node_script_async` 用自管 `Popen + communicate(timeout)`，不用 `subprocess.run`；脚本经 stdin 交给 node | `subprocess.run` 超时分支会二次 `communicate()` 永久等待；先读字节再校验再把同一份字节交 node，消除 TOCTOU | `src/utils.py::run_node_script_async` 注释；`tests/test_utils.py` 的结构锁 |
| 11 | `scripts/` 下维护脚本「零生产 import 方」 | 消费方多在 `.github/workflows/*.yml`、`.pre-commit-config.yaml`、`Dockerfile`、`build_exe.py`、`AGENTS.md` 门禁清单 | `docs/agent-reference/session-learnings.md`（2026-10-20 孤儿扫描条目） |
| 12 | `scripts/douyin_live_recorder_standalone.py` 与主线存在差异 | 独立发行副本有刻意差异与回灌清单；差异要核对是否登记，不能一律当缺陷 | `docs/agent-reference/session-learnings.md`（2026-09-30 standalone 条目）；报告 §6 |
| 13 | `config/config.ini` 被跟踪且敏感键为空；`config/URL_config.ini` 不跟踪 | 前者是脱敏基线模板（空值是预期），后者是运行时文件 | `AGENTS.md`「凭据与敏感配置红线」；报告 §2.1/§7.4 |
| 14 | `src/proto/douyin_pb2.py`、`typings/**` 的存根 | protoc 生成物与手写存根，只核同步性，不按手写代码评质量 | 报告 §2.1 排除项 |
| 15 | `tests/frontend/*.mjs` + 同名 `.py` 包装的双文件结构；R9 例外表里的零收集文件 | 前端用例用 Node 内置 `node:test`，`.py` 只做包装；零收集有登记理由 | `AGENTS.md`「测试」；`tests/test_test_hygiene.py` 的 `_R9_ZERO_COLLECTION_SANCTIONED` |
| 16 | `.workbuddy/`、`uv.lock`、`DouyinLiveRecorder.egg-info/`、`coverage*` 不读正文 | 基线快照副本/派生生成物/覆盖率产物，与主干重复或可再生成 | 报告 §2.1 排除项 |

## 白名单之外的常见误报（仍需主控复核）

- `mypy`/`basedpyright` 对平台专属符号（`ctypes.windll`、`subprocess.STARTUPINFO`）的告警报错，可能是平台目标不匹配，不是代码缺陷。
- `ast.dump` 子串匹配、`grep` 关键字判据的命中，可能是注释或混淆脚本里的字面量。
- 注释里写的回归锁路径过期，是**缺陷**（悬空引用），不属白名单。
- 文档承诺「某防线存在」但代码没有，是**缺陷**（事实源与代码互相说谎），不属白名单。
