# 全仓静态代码审查报告（2026-10-27）

## 1. 概述

本次对工作区根目录下全部源代码执行了一次全面、系统的**只读静态审查**。审查背景与定位：

- 上一次全量审查为 [CODE_REVIEW_2026-10-21](docs/worklog/CODE_REVIEW_2026-10-21.md)（130 项发现），其修复日志 `CODE_REVIEW_2026-10-21_FIX.md` 显示多数 M 级项当时标记「未实施」。
- 本次审查的核心工作之一，是**逐项核对 2026-10-21 报告中的遗留项在当前工作区的真实状态**——结论是：绝大多数当时「未实施」的 M 级项实际已在工作区落地修复（修复内容带日期注释与回归测试），但未回写修复日志。本次报告将逐项给出核对结论。
- 同时对全仓做语法解析、高危模式扫描与新增缺陷排查。

**重要声明：本次审查未修改任何源文件；本报告是唯一新增文件。**

## 2. 审查范围与方法

### 2.1 范围

- 296 个项目源文件，约 145,938 行：Python 262、JavaScript 7、HTML 3、MJS 4、CSS 1、SH 4、VBS 1、Proto 1、Pyi 13。
- 排除：`node_modules`、`.venv`、`dist`、`build`、`out`、`coverage`、`.git`、第三方/锁定文件、压缩产物、`.workbuddy`、`docs`、`.qoder*`。
- 排除项说明：工作区存在约 253 个文件的未提交改动（注释体系化重构 + `.agents/skills` 合并），属进行中的其他工作包，本次只审查其**当前快照状态**，不重复评审改动过程。

### 2.2 方法

1. **语法解析**：AST 解析全部 275 个 Python 文件 —— **0 语法错误**（Python 3.14 的 PEP 758 `except A, B:` 无括号写法在 3.14 下合法，此前关于 3.13 误报的记录不影响本仓目标版本）。
2. **高危模式扫描**：`eval/exec`、`shell=True`、裸 `except: pass`、无超时 `subprocess`、`TODO`、JS `console.log`、HTML 拼接注入等。
3. **基线对照**：逐项核对 2026-10-21 报告 130 项发现 + 修复日志，用当前代码实证复核（而非凭修复日志下结论）。
4. **模块精读**：`main.py`、`gui.py`、`web.py`、`src/web_api.py`、`src/scheduler.py`、`src/collector.py`、`src/danmaku_monitor.py`、`src/ffmpeg_install.py`、`src/stream_select.py`、`src/spider.py`（关键段）、`src/ws_client.py`、`src/async_http.py`、`src/web_tray.py`、`src/web_config.py`、`src/config_read.py`、`src/utils.py`、`build_exe.py`、`scripts/*`、`web/app.js`、`src/javascript/*`、`StopRecording.vbs` 等重点模块。

## 3. 发现汇总（按严重程度）

| 严重程度 | 数量 | 说明 |
|---|---|---|
| 严重 | **0** | 无 |
| 中等 | **1** | 遗留未决（交回用户选向的设计决策） |
| 轻微 | **3** | 备案/观察项 |

### 3.1 基线核对总表（2026-10-21 报告关键项 → 当前状态）

| 编号 | 位置 | 当前状态 | 实证依据 |
|---|---|---|---|
| M-06/M-11/M-15 | main.py 全局配置 | ✅ 已修复 | 全局配置键集合收敛（main.py:4838-4846） |
| M-20/M-23/M-25 | stream_select.py | ✅ 已修复 | `probe_client` 显式初始化（:949）；`security_rejected` 集合正确填充 |
| S-03/04/05 | stream_select.py | ✅ 已修复 | Windows 保留名判定（:62-68）、`_is_h265` 单点、Range GET 探测 |
| M-35/36/42 | scheduler.py | ✅ 已修复 | `_compute_capacity` = `min(max, max(configured, scaled))`（:344-347）；熔断需 fail_rate>0 |
| M-37~40/43 | collector/danmaku_monitor/room/recorder_status | ✅ 已修复 | 线程握手、有界队列、同锁快照 |
| M-44~49 | ffmpeg_install.py | ✅ 已修复 | `swap_directories` 带回滚；下载重试+字节上限；PATH 统一前插 |
| M-54 | config_read.py | ✅ 已修复 | 续行解析容错 |
| M-60~64/67/88 | web_api.py | ✅ 已修复 | 危险配置键扩容（:318-323）；token 存 sessionStorage/内存 |
| M-66 | web_api.py Origin 头缺失放行 | ✅ 有意设计 | 默认无鉴权仅绑 loopback，已注释论证 |
| M-68 | web_config.py 重复键 | ✅ 已修复 | 写侧拒绝含重复键的写入（:1166，带 2026-10-21 注释） |
| M-69 | web_tray.py `os._exit(0)` | ⚠️ 有意设计 | 仅「无 server 对象」分支才强制退出（:466-476），注释完整；降级为轻微观察项 |
| M-70 | web.py 宽 `except Exception` | ✅ 观察通过 | 采样均有「为什么」注释与边界论证；建议维持观察 |
| M-84/85/88 | web/app.js、StopRecording.vbs | ✅ 已修复 | innerHTML 全部经 `esc()`；vbs 锚点改 `appDir + '\\'` |
| M-87 | liveme.js console.log | ❌ **仍存在** | 见 4.2 |
| M-89 | standalone 自动重装 | ✅ 不存在 | 全文无 reinstall/pip install 逻辑 |
| M-91 | check_coverage.py | ✅ 已修复 | `_data_is_stale` fail-closed |
| M-94 | run_gates.py | ✅ 已修复 | stalled（无结论超时）与 failed（代码不合格）分档，杜绝假绿（:645-659） |
| M-96 | spike_arm64_static_ffmpeg.sh | ✅ 通过 | `set -euo pipefail`、curl 带 `--max-time`、官方 sha256 校验 |
| M-97 | smoke_test.py HTML 注入 | ✅ 已修复 | 动态片段一律 `html.escape`（:365-381，含 XSS 攻击面注释） |
| M-13 | spider.py `get_huajiao_sn` | ❌ **仍存在** | 见 4.1 |
| M-30 | ws_client.py | ✅ 通过 | 协议层 ping/pong + 指数退避重连 + 健康归零窗口；回调文案强制脱敏 |
| M-32 | async_http.py HEAD | ✅ 已修复 | HEAD 失败自动 Range-GET 复核，响应体读取带上限（:685-736） |

## 4. 详细发现与影响分析

### 4.1 【中等】M-13（遗留）：`get_huajiao_sn` 死代码携带危险写回逻辑

- **位置**：`src/spider.py:4987` 起（关键分支 :4937 附近）
- **问题**：该函数全仓无调用点（真实调用走 app 版解析路径），是死代码；但它携带全仓唯一的 `utils.replace_url(..., '#' + url)` 写回逻辑。当花椒返回 WAF/风控壳页（有响应但无 `var feed`）时命中 ValueError 分支，**一次风控命中即把用户配置里的房间地址永久注释掉**。
- **为什么改判为「仍存在」**：2026-10-21 修复日志标记「未实施，交回用户选向」；CODE_WIKI 将其列入「保留项」，但**列入保留项 ≠ 风险已消除**——死代码一旦被未来改动重新接线，风险即复活。
- **影响**：低概率、高恼人度（用户房间配置被静默破坏且难排查）。
- **建议**（与前次一致，二选一）：
  1. 直接删除该函数（需同步核对两处活锁断言引用）；或
  2. 保留但改失效判据为「响应可解析且字段确实为空」，并删掉 replace_url 写回逻辑。
- **修复成本**：低（方案 1 约 30 分钟含测试核对）。

### 4.2 【轻微】liveme.js 调试输出残留（前次 M-87 部分遗留）

- **位置**：`src/javascript/liveme.js:348, 374, 384, 388, 419, 421`（6 处 `console.log`）
- **问题**：签名脚本经 Node 子进程执行，`console.log` 把 `sKey`、`signParams`（含请求参数）、最终签名 `lm_s_sign` 打到 stdout。若父进程把子进程 stdout 捕获进日志，签名素材与请求参数会扩散到日志文件。
- **缓解因素**：`sKey` 是从页面 JS 抠出的静态算法常量而非用户凭据；实际危害有限。
- **建议**：删除或按环境变量开关（如 `DEBUG` 才输出）；保留 `x-bogus.js` 现状（混淆第三方代码，`var window = null` 遮蔽是其固有形态，仅备案不整改）。

### 4.3 【轻微】web_tray.py `os._exit(0)`（前次 M-69 降级）

- **位置**：`src/web_tray.py:476`
- **现状**：仅当 `_on_exit` 在「无 server 对象」分支才强制退出；有 server 时走 uvicorn 优雅关闭。注释完整解释了为什么不在此处 quit（服务还在跑时摘掉事件循环会把清理段引到 HTTP 请求中间）。
- **建议**：维持现状；如担心回归，可补一条测试锁（断言有 server 分支不触发 `os._exit`）。

### 4.4 【轻微】宽 `except Exception` 的分布观察（前次 M-70 关联项）

- **现状**：`web.py` 等边界模块仍有多处宽捕获，但抽查均有「为什么」注释（托盘回调异常不能穿透 Qt 事件循环、清理段必须走完等），且 src 侧**实际代码中同行 `except: pass` 为 0 处**（仅 2 处注释在解释该实践的取舍），`TODO` 标记为 0。
- **建议**：不强制整改；后续重构触及对应函数时顺势收窄异常面即可。

## 5. 改进建议与修复优先级

| 优先级 | 项 | 成本 | 风险 |
|---|---|---|---|
| P1 | 4.1 `get_huajiao_sn`：删除或改失效判据（用户选向） | 低 | 低（方案 1 需核对两处断言） |
| P2 | 4.2 liveme.js 调试输出：删除或加 DEBUG 开关 | 极低 | 极低（纯日志面） |
| P3 | 4.3 补 web_tray 退出路径测试锁 | 低 | 无 |
| P3 | 4.4 维持观察，不单独排期 | — | — |

**优先级依据**：P1 是唯一有真实用户影响的遗留项（配置被静默破坏）；P2 是卫生问题；P3 为加固性质。

## 6. 全仓健康度横向结论

本轮扫描的量化结果显著优于 2026-10-21 基线：

1. **注入面**：`eval/exec` 危险使用为 0（现存仅为 Qt `exec()` 事件循环与测试内带 `noqa: S102` 的 `exec(compile())` 源码装载）；`shell=True` 仅 `scripts/run_gates.py` 受控使用（argv 优先、仅命令确需 shell 解释时退化，且有回归锁），`src/utils.py` / `src/notify.py` 对 taskkill 明令 argv 列表调用并有测试锁 `assert "shell" not in kwargs`。
2. **Web 面**：`web/app.js` 无 localStorage 存 token、innerHTML 动态字段全部转义；`smoke_test.py` 报告生成全部 escape；`web_api.py` 危险配置键黑名单持续扩容。
3. **并发/资源面**：调度器容量计算、熔断探测租约、线程握手、有界队列、同锁快照等前次 M 级项全部落地；ffmpeg 安装切换带回滚、下载带字节上限。
4. **工程纪律面**：run_gates 把「超时无结论」与「检查不通过」分档；check_coverage 数据过期 fail-closed；TODO 清零。
5. **文档同源性**：CODE_WIKI 的「保留项」清单与本报告核对结论一致（但 4.1 的风险提示仍需回写到决策记录）。

## 7. 结论与后续行动

1. **当前工作区源码质量状态：良好**。2026-10-21 报告的 130 项中，除本文 4.1/4.2 两项外均已修复或经论证收口；其中约 20 项的修复在修复日志中标记「未实施」但实际已落地——**建议把该批次修复补记进 `CODE_WIKI` 更新日志**，避免事实源与代码状态长期背离。
2. **需要用户决策**：4.1 `get_huajiao_sn` 的处置方向（删除 vs 改判据）。确认后即可实施。
3. **本次审查性质**：纯只读。除本报告外未创建、未修改任何文件；扫描用临时脚本与输出已清理。
