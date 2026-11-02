# CODE_REVIEW_2026-10-21 遗留项（需人工确认）

> 本文件是 [`CODE_REVIEW_2026-10-21.md`](CODE_REVIEW_2026-10-21.md) 系列第三份：
> 报告本体（审查快照）→ [`CODE_REVIEW_2026-10-21_FIX.md`](CODE_REVIEW_2026-10-21_FIX.md)（第一轮整改留痕）
> → **本文件**（第二轮整改后仍未实施、或只完成一半、需要维护者拍板的条目）。
>
> 定位：这些条目**不是被遗忘的修复**，而是「按第 2 步要求无法唯一确定改法」或「属于专项工程/产品决策」
> 的部分。每条都写明**当前锚点、阻塞原因、需要的输入、可选方案与验收判据**，便于逐条关闭。
>
> **引用口径**：只写符号锚点（函数/类/唯一语句片段），不写易漂移的 `file:line`；确需定位时给
> 「2026-10-21 复核行号」，漂移后以符号为准（AGENTS.md「注释约定」的同一口径）。

## 0. 当前验证基线（2026-10-21 第二轮整改后）

| 项 | 读数 |
| --- | --- |
| 静态门禁 | `scripts/run_gates.py` **10/10 全绿**（black / isort / mypy 含 linux+win32 双跑 / check_annotations / compile_po --check / check_version / check_runtime_pins / check_skill_agents_consistency） |
| 单元测试 | `pytest -q --cov=src` **4922 passed / 0 failed / 16 skipped / 0 warnings** |
| 覆盖率 | `scripts/check_coverage.py` **PASSED：68 个模块全部达标** |
| 真机验证（DoD 第 2 步） | **未执行**：本机无稳定外网与活跃直播间。涉及平台解析/选源的改动需在有活房间环境跑 `python tests/test_douyin_live_collector.py --seconds 30`（或任一受影响平台），核对 PASS + 消息数/SRT 字节数 |

关闭本文件中任何一条后，必须重跑上表前三条；涉及录制链路/选源/ffmpeg 参数的还要补真机读数。

---

## 1. 总览

| 类别 | 条目 | 共同特征 |
| --- | --- | --- |
| A. 设计决策（需拍板） | M-07、M-09、M-10、M-13、M-26（后半）、M-27、M-30、M-31、M-32、M-34、M-74 | 报告只给方向，缺「唯一形态」；改错会静默改变产品行为或并发模型 |
| B. 需领域信息 | M-15、M-17、M-18（后半）、M-29（ACL 半）、M-75（Qt 半）、M-86/M-87 | 需要各平台 id 字符集、状态码语义、平台 ACL 能力、真机验签等外部事实；M-75 另需先定脱敏点 |
| C. 工程专项（工作量） | S-14（存量债务）、M-100~M-104 | 单项不是「一行补丁」，需成批补测/补判据；本轮已冻结不再增长 |
| D. 可选技术债 | L-01~L-10 | 报告与 AGENTS 均要求与行为变更**分开提交**，避免 diff 不可审 |
| E. 工程侧待决 | M-08（残留半）、`_ci_web_smoke.sh` 的 `set -e` | 已部分修复；剩余部分需先确认契约或环境能力 |
| F. 流程性建议 | 报告 §8.1 第 1 条（把「判据族」写进 AGENTS.md） | 修改项目唯一事实源，需维护者批准 |

---

## 2. A 类：设计决策

### M-07 模块导入即注册信号处理器 / atexit / 覆写 `builtins.print`

- **级别**：中等（代码质量）
- **当前锚点**：`main.py` 模块级 `signal.signal(signal.SIGINT/SIGTERM/SIGBREAK, safe_exit)`（2026-10-21 复核行 611/612/614）、三条 `atexit.register(...)`（619/620/625）、模块级 `builtins.print = translated_print`（4818）
- **现状**：任何 `import main` 的宿主（`web.py`、`gui.py`、测试）都会静默接管其信号与退出清理，并被覆写 `print`。
- **为什么未做**：报告只给方向「收进 `install_runtime_hooks()` 由真实入口调用」，但**谁调用**未定——`web.py`/`gui.py` 当前依赖这些钩子在 `import main` 时生效；改错会让 Web 面板退出时不归档日志、GUI 子进程清理失效。
- **需要的输入**：① 三个入口（`main.py`/`web.py`/`gui.py`）各自应在什么时点安装钩子；② 已存在的信号处理器是「链式调用」还是「覆盖」。
- **可选方案**：
  1. 仅 `if __name__ == "__main__":` 安装（最小），但 `web.py`/`gui.py` 需显式调用一次 `install_runtime_hooks()`；
  2. 提供 `install_runtime_hooks()` 且默认**不自动**安装，三个入口各调一次，并保存/链式调用原处理器。
- **验收判据**：`import main` 不再改变宿主信号与 `print`；三个真实入口的日志归档/ffmpeg 清理行为与现状逐条一致（现由 `tests/test_log_archive.py`、`tests/test_logger_gui_parent.py` 覆盖）。

### M-09 24 个主循环临时量被提升为模块级全局

- **级别**：中等（代码质量）
- **当前锚点**：`main.py` 模块级注释块「main() 循环临时变量（global 声明引用…）」（复核行 469 起），`main()` 内一整屏 `global` 声明
- **现状**：任何函数都可能读到其它轮次残留值；`push_message`/`start_record` 也读其中一部分。
- **为什么未做**：报告只给首尾行号，未区分「仅本轮使用」与「跨函数共享」；属大范围重构，超出最小 diff。
- **需要的输入**：逐量使用面审计（谁读、谁写、是否跨轮）。产出应是一张「符号 → 读者 → 是否需跨轮」表。
- **验收判据**：`mypy` 无 `possibly unbound`；全量 `pytest` 绿；`grep -c "^    global "` 归零或仅剩经审计确认的少数项。

### M-10 三层宽泛 `except Exception` 把编程错误喂进熔断样本

- **级别**：中等（异常处理）
- **当前锚点**：`main.py::start_record` 内的宽泛 `except Exception` 块，判据取「`except Exception` + `record_error(record_host)`」（复核行 4450/4479/4576 一带；行号会随编辑漂移，以锚点为准）
- **现状**：`KeyError`/`TypeError` 被当作线路故障计入按 host 熔断，可能拖慢同 host 其它房间。
- **为什么未做**：报告要求「只有网络/HTTP 类异常才调 `record_error`」，但**未给分类表**；自建一份会与本仓「单一事实源」纪律冲突。
- **需要的输入**：一份唯一的「网络/HTTP 异常元组」定义位置（建议放 `src/async_http.py` 或新 `src/errors.py`），三处引用同一常量。
- **验收判据**：注入 `KeyError` 不再增加 `error_count`；注入 `httpx.ConnectError`/`OSError` 仍计入；`tests/test_record_failure_feedback.py` 扩两条用例。

### M-13 死函数 `get_huajiao_sn` 携带「一次风控即永久注释房间」的写回

- **级别**：中等（逻辑 + 死代码）
- **当前锚点**：`src/spider.py::get_huajiao_sn`（复核行 5018），写回语句 `utils.replace_url(..., new="#" + url)`（5078）
- **现状**：函数全仓零调用点（仅定义），故危害不可达；但函数体仍是「WAF 壳页 → ValueError → 注释掉用户房间」的完整路径。
- **为什么未做**：报告给两个**互斥**选项（删除 / 改判据），且本仓开发手册要求「发现死代码只报告、不顺手删」。
- **需要拍板**：删除，还是保留并改用「响应可解析且字段确实为空」作失效判据。
- **若删除**：需同批删除 `tests/test_exception_log_masking.py` 与 `tests/test_spider_hardening.py` 中对它的登记行，并确认 `OVERSEAS_MIGRATED_FUNCTIONS` 之类的双向锁不引用。
- **验收判据**：`grep -rn "get_huajiao_sn"` 仅剩历史注释（或零命中）；全量 `pytest` 绿。

### M-26（后半）`select_source_url` 无单轮总时长预算

- **级别**：中等（资源）
- **当前锚点**：`src/stream_select.py::select_source_url`（复核行 1217）；文件内 `monotonic|deadline` 零命中
- **现状**：节流 sleep + 401/403 复核 + 每候选最多 4 次 5s 探针；虎牙 4 条 CDN 时单房间单轮可达数十秒。斗鱼「全档失败返回 `is_live=False`」半已修。
- **为什么未做**：**预算取值与超时行为是产品决策**——预算偏小会让慢 CDN 直接判无源 = 静默漏录。
- **需要的输入**：① 单轮预算秒数；② 超时后的行为（返回 None / 保留最后一个候选交 ffmpeg / 记 warning 后下一轮重试）。
- **不可回退的约束**：不得改变虎牙 FLV-first 的末位放行语义；不得缩短探针退避窗口（≥ 一个主循环周期）；斗鱼不得进 `_FLV_FIRST_PLATFORMS`。
- **验收判据**：构造慢探针桩，断言单轮耗时 ≤ 预算；正常 CDN 的既有选源用例全部保持绿。

### M-27 逐跳复检在事件循环线程内做阻塞 DNS

- **级别**：中等（并发/性能）
- **当前锚点**：`src/async_http.py::_build_hop_guard` 的 `_guard`（复核行 645）→ `_internal_stream_target_reason`（491）→ `web_config._host_internal_reason` 内 `socket.getaddrinfo`
- **现状**：每一跳、每一次请求都在循环线程同步解析；DNS 慢时冻结该房间整个事件循环。
- **为什么未做**：httpx 的 response 钩子是**同步签名**，不能 `await`；改成 `loop.getaddrinfo` 需在钩子内取循环并加超时，属并发模型改动。
- **不可回退的约束**：该钩子必须仍是 `_build_client` 的**唯一** response 钩子（`tests/test_regression_wp_b_netguard.py` 断言恰一支）；不得给判定结果加缓存（会拉长 DNS 重绑定窗口）；「先定罪、后读体」顺序不变。
- **验收判据**：DNS 桩延迟 2s 时，同循环其它请求不被阻塞（可用 tick 计数用例）；判据结论与现状逐条一致。

### M-30 `decompress_brotli_limited` 事后检测上限且异常路径不释放

- **级别**：中等（安全/资源）
- **当前锚点**：`src/ws_client.py::decompress_brotli_limited`（复核行 96）
- **现状**：先把单块 4KB 输入的全部输出物化再判上限；`obj` 用完未 `close()`。
- **为什么未做**：需先确认 brotli `Decompressor` 提前 `close()`/`finish()` 的语义——提前关闭可能吞掉尾部数据（弹幕丢包）。
- **需要的输入**：目标 brotli 版本的 `finish()` 契约（或一条「提前 close 后仍能取回已喂数据」的实验读数）。
- **验收判据**：构造高压缩比炸弹样本，断言内存峰值受控；正常 brotli 弹幕帧解压结果与现状逐字节相同。

### M-31（残留半）跨循环 `AsyncClient` 与 `warmup_ttwid` 临时循环客户端

- **级别**：中等（资源泄漏）
- **当前锚点**：`src/ttwid.py::warmup_ttwid` 的 `asyncio.run(get_ttwid(proxy_addr))`（复核行 219）
- **现状**：临时循环创建的客户端在 `asyncio.run` 返回后成孤儿；`async_http` 侧已做同循环 `aclose()` 与未关闭计数。
- **为什么未做**：AGENTS 明确**禁止**跨事件循环调度旧客户端的 `aclose()`；唯一可行形态是「在所属循环内、循环返回前关闭」，需改 `warmup_ttwid` 的调用结构。
- **验收判据**：`warmup_ttwid` 返回后 `async_http` 的未关闭计数不增长；`tests/test_ttwid*.py` 全绿。

### M-32 Range-GET 复核只对 `.m3u8` 生效

- **级别**：中等（逻辑）
- **当前锚点**：`src/async_http.py::get_response_status` 中 `if ".m3u8" in url.lower() and response.status_code != 200:`
- **现状**：flv/直链遇 HEAD 403/404/405 直接判不可达并降档；注释自承「部分 CDN 对 HEAD 拒绝但 GET 可拉流」对 flv 同样成立。
- **为什么未做**：需先定义「明确不可达」状态码集合（405/501 之外还有哪些）；缺集合时放宽会把真死链放行。
- **建议方案**：至少把 405/501（方法不允许类）单独纳入 GET 复核，其余状态码维持现状。
- **验收判据**：HEAD 405 + GET 200 的 flv 桩判可达；HEAD 404 的桩仍判不可达；探针仍走缓存的同一支客户端。

### M-34 缓存命中返回内部引用 / `http_config` 热更新全局无锁

- **级别**：中等（并发/封装）
- **当前锚点**：`src/cookie_cache.py::_get_cached_entry` 与三处 `return entry[0]`（复核行 101/223/235/390）；`src/http_config.py` 的 `ssl_verify_platform_overrides`（20）与 `set_platform_ssl_verify`（46）
- **为什么未做**：需先证明所有调用方（含 tests）都不就地修改返回的字典；`http_config` 的「按对象引用整体替换」需先定边界（哪些读点要求原子快照）。
- **建议方案**：取值侧 `return dict(entry[0])`（或 `MappingProxyType`）；配置改为「构造新对象后整体赋值」。
- **验收判据**：新增一条「调用方就地写不污染缓存」用例；`tests/test_cookie_cache.py`、`tests/test_http_config*.py` 全绿。

### M-74 语言切换后主题/缩放/动效下拉仍是旧语言

- **级别**：中等（逻辑）
- **当前锚点**：`gui.py` 的 `_theme_ids_by_display` / `_scale_ids_by_display` / `_motion_ids_by_display`（复核行 1999/2015/2034，构建期一次生成）；`_on_language_change`（2434）只调 `retranslate_all()` 与 `_refresh_font_menu_values()`
- **现状**：反查表键对不上时 `.get(choice, 默认)` 静默落到默认项（用户选「深色」实际被改成「跟随系统」）。
- **为什么未做**：需抽 `_rebuild_preference_menus()` 统一重建三组显示名与反查表，属 GUI 收敛专项；并要保证重建不触发选择回调（会写回配置）。
- **验收判据**：切到 en_US 后三个下拉的显示名全部为英文；逐项选择后写回的 id 与选择项一致（回归锁可读 `config.ini`）。

---

## 3. B 类：需领域信息

### M-15（残留）小红书 `user_id` / bigo `room_id` / 花椒子路径未编码或未剥子路径

- **级别**：中等（安全）
- **当前锚点**：`src/spider.py` 的 `profile_url = f"https://www.xiaohongshu.com/user/profile/{user_id}"`（复核行 2729）、bigo 的 room_id 拼接、`get_huajiao_user_info` 的 `url.split("?")[0].split("user/")[1]`（5115）
- **现状**：知乎已用 `urllib.parse.quote(..., safe="")` 修好；其余三处未动。
- **为什么未做**：各平台 id 的**合法字符集未知**——把本应保留的 `-`/`_` 一并编码可能触发平台 404，等于用安全修复制造漏录。
- **需要的输入**：三类 id 的官方字符集或实测样本（各 3~5 个真实 id 形态）。
- **验收判据**：含 `/`、`?`、`..` 的恶意 id 不再改变请求路径；给定真实样本编码前后均能正常解析。

### M-17 `_safe_loads` 的深度检查在 `json.loads` 之后

- **级别**：中等（安全/资源）
- **当前锚点**：`src/spider.py::_safe_loads`（385），长度上限 `_SAFE_LOADS_MAX_CHARS`（8M）在解析前、深度上限 `_SAFE_LOADS_MAX_DEPTH=64`（382/406）在解析后
- **现状**：小体积但超深嵌套的响应仍会让 C 扫描器吃一次（`RecursionError` 未被这里捕获）。
- **为什么未做**：正确形态需要**解析前的**深度扫描（逐字符括号计数），属新增解析器级逻辑；且要证明它不会拒绝合法深 JSON。
- **验收判据**：构造 10 万层嵌套的小报文，断言在 `json.loads` 之前被拒；既有 116 处 `_safe_loads` 调用面全绿。

### M-18（后半）SOOP 空 `view_url` 仍拼 `?aid=` 并返回 `is_live=True`

- **级别**：中等（空值/边界）
- **当前锚点**：`src/spider.py::get_sooplive_stream_data` 的 `_view_url + "?aid=" + aid_token`（两处：登录态与游客态）
- **现状**：网易侧的 `url[-1]` 越界已修；SOOP 的空 `view_url` 未动。
- **为什么未做**：需确认是否存在「先拿 view_url、后续再补流地址」的既有流程；若存在，早退会误判未开播。
- **需要的输入**：该平台解析链路的调用顺序说明或一条真实失败样本。
- **验收判据**：空 `view_url` 不再产出坏地址；正常房间的 `m3u8_url`/`record_url` 与现状逐字相同。

### M-29（ACL 半）`execute_dir/node` 前置 PATH 后的属主/ACL 校验

- **级别**：中等（安全）
- **当前锚点**：`src/node_install.py::install_nodejs_windows` 的 PATH 前置 + `subprocess.run(["node", "-v"])`；已改为 `shutil.which("node")` 取绝对路径
- **现状**：目录位于用户可写区，能写入 `node.exe` 的本地主体会被以本进程权限执行；ACL 校验未加。
- **为什么未做**：Windows 无跨平台等价实现（需 pywin32 或 ctypes 深调），属新平台层决策。
- **可选方案**：① 安装后校验 `execute_dir` 与 `node.exe` 的属主/SDDL（仅 Windows）；② 不接受本层，转而在文档中登记「安装目录必须受信」的前提。
- **验收判据**：若采用 ①，需一条「属主不符即拒绝执行」的用例；若采用 ②，需在 AGENTS.md 登记该前提。

### M-75（Qt 半）Qt 日志链路未脱敏

- **级别**：中等（安全）
- **当前锚点**：`src/gui_qt/recorder.py` 读线程的 `clean_line = ANSI_ESCAPE_PATTERN.sub("", line.rstrip())` 后直接入队（复核行 441-442）；`self._log(f"执行程序: {record_cmd[0]}")`（214）
- **现状**：Tk 侧三处路径已过 `mask_credentials`；Qt 侧无任何 `mask_credentials` 引用，录制输出会把直播间 URL、平台签名参数、请求头原样写入日志页并落盘。
- **为什么未做**（本轮核对发现的口径缺口，非报告歧义）：需先定**脱敏点**——读线程脱敏会连日志页也看不到原文（排障有时需要原文），只在落盘前脱敏则日志页仍暴露；且既有 Qt 输出链用例可能按原文断言。
- **建议**：与 Tk 侧同口径，在入队前统一过 `utils.mask_credentials`，补一条「签名参数值消失」的行为用例；若确需保留日志页原文，则「落盘前脱敏 + 页面标注」两处都做，**不得只做一处**。
- **验收判据**：录制输出含 `token=`/`wsSecret=`/`user:pass@` 时 `logs/gui.log` 中值消失；`tests/test_regression_gui_output_chain.py` 全绿。

### M-86 / M-87 `src/javascript/` 签名脚本（Liveme / X-Bogus）

- **级别**：中等（代码质量 / 信息泄露 / 潜在缺陷）
- **当前锚点**：`src/javascript/liveme.js` 的 5 处未声明赋值（`pC =`、`lm_s_key =`、`data_i =`、`signParams =`、`data =`）与 6 处 `console.log`（打印 `sKey`/`data_e`/`signParams`/最终签名，含 ANSI 转义）；模块加载期 `const r = \`${Date.now()}${id}\`` 与 `const s = Rm(r)`；`src/javascript/x-bogus.js` 的两处 `eval("require('crypto')")` / `eval("require('buffer')['Buffer']")`
- **现状**：全部保留（2026-10-21 复核：`liveme.js` 6 处 `console.log`、`x-bogus.js` 2 处动态求值）。
- **为什么未做**：① 这两个脚本是**活签名链**，任何改动都会改变签名输入/输出，必须对着真实平台实例验签（本机无稳定外网与活跃直播间）；② `src/javascript/` 的内容变更必须与 `utils._JS_SHA256_EXPECTED` **同批**重钉（`tests/test_utils.py::TestJsPinTable` 双向断言），验签失败时无法区分「改动写错」与「钉定值忘了改」；③ `const r/s` 移入 `sign()` 会改变每次调用的时间戳语义，需实测平台是否接受。
- **建议顺序**：可联网环境先录一条当前签名基线 → 改脚本（补 `const`、删调试输出、直接 `require`、`r/s` 移入 `sign()`）→ 同批重钉 sha256 → 用真实房间跑解析与拉流对比。
- **验收判据**：`grep -c "console.log" src/javascript/liveme.js` = 0（或仅 debug 开关分支写 stderr）；`grep "eval(\"require"` = 0；`tests/test_utils.py::TestJsPinTable` 绿；真实房间解析 PASS。

---

## 4. C 类：工程专项

### S-14（存量）弱断言债务清零

- **级别**：严重（部分修复）
- **当前读数**（R11 棘轮实测，2026-10-21）：**46 个测试函数体内无任何判据**（20 个文件）、**10 处参数承载语义的裸 `assert_called*`**（3 个文件）
- **已做**：R11 已从「只拦增长」改为**双向**（债务表必须等于实测，修复后不降表即红），并补了反向自证；报告点名的 Range 头契约已补显式断言。
- **为什么未清零**：逐条补判据需要理解每个用例的真实契约，属单独立项；一次性机械补 `assert True` 会制造新的假绿。
- **建议推进顺序**：与功能改动同文件时顺手补；优先 `tests/test_async_http.py`/`test_sync_http.py`/`test_bilibili_danmaku_info.py` 的报告点名项。
- **验收判据**：R11 两张表的 per-file 行数逐项降为 0；每次下降同批更新表（否则双向棘轮会红）。

### M-100 平台取流主链路覆盖率缺口

- **级别**：中等（覆盖盲区）
- **当前证据**：`coverage.json`（2026-10-20 快照，第二轮改动前）显示 `src/spider.py` 76.07%；按函数：`get_popkontv_stream_data` 3.3%、`get_showroom_stream_data` 2.8%、`get_pandatv_stream_data` 5.1%、`get_shopee_stream_url` 40.0%、`get_douyin_web_stream_data` 63.3%、`get_douyin_app_stream_data` 56.3%
- **注意**：该快照早于本轮 +386/−90 的 spider 改动，**当前真实数字需重跑 `pytest --cov=src` 才能给出**。
- **建议**：按平台补「离线契约」用例（固定 HTML/JSON 替身，断言 `is_live`/`m3u8_url`/`record_url` 与 `{is_live:False}` 两分支），先做三个近 0% 的平台。
- **验收判据**：六个函数的分支覆盖率均 ≥ 60%，`check_coverage.py` 仍 PASSED。

### M-101 `except` 分支首行未覆盖

- **级别**：中等（覆盖盲区）
- **当前证据**：461 个 `ExceptHandler` 中 47 个分支体首行未覆盖（报告 46，±1 漂移）；`src/gui_qt/app.py` 2/2、`src/gui_qt/pages/danmaku.py` 2/2 完全未覆盖
- **建议**：按文件补「注入异常 → 断言降级结果」用例；两个 2/2 的 GUI 文件先补 1 条冒烟 + 1 条异常路径。
- **验收判据**：未覆盖数降到 20 以下；新增用例均为行为断言（不得只断言「没抛异常」）。

### M-102 零引用 / 单引用模块

- **级别**：中等（覆盖盲区）
- **当前证据**：`src/gui_qt/pages/runlog.py`、`src/gui_qt/quality_monitor.py` 被 0 个测试文件引用；`platforms/_xbogus.py` 等仅 1 个（计数口径与报告略有出入）
- **建议**：补导入级/构造级冒烟；`_xbogus.py`（抖音签名算法）优先补字段级断言。
- **验收判据**：68 个模块的清单中，零引用模块为 0；单引用模块 ≤ 3 且各有理由。

### M-103 五个真机脚本共用会话级 `tests/_out_live`

- **级别**：中等（测试污染）
- **当前证据**：`tests/conftest.py` 的 `_TEST_OUT_DIRS` 与 `pytest_unconfigure` 清理；5 个 `test_*_live_collector.py` 仍写同一目录
- **建议**：改为带平台唯一前缀的子目录（或 `tmp_path`），同时保留 R7 的四条模板约束。
- **验收判据**：并行跑两个脚本互不删除对方产物；`tests/test_test_hygiene.py` 的 R7 全绿。

### M-104 测试跨文件重复块

- **级别**：中等（可维护性）
- **当前证据**：三份独立的 `_EXCLUDED_PARTS` 目录名单（`test_exception_log_masking.py` / `test_outbound_read_caps.py` / `test_pep758_except_form.py`）、`_PROXY_ENV_KEYS` 三份；「73 组重复块」无仓内扫描器可复现
- **建议**：先合并两份名单常量到 `tests/_fixtures.py`（bounded edit），再做块级去重（专项）。
- **验收判据**：名单常量只有一份；扫描类用例全绿。

---

## 5. D 类：可选技术债（L-01~L-10）

> 报告明确这类属「低风险技术债窗口」，且建议**不夹带行为变更**单独提交。本轮只顺带消除了少量已被行为修复覆盖的站点（见下）。

| 编号 | 类别 | 当前规模（2026-10-21 复核） | 本轮已顺带消除 | 剩余动作 |
| --- | --- | --- | --- | --- |
| L-01 | 死代码 | `gui.py` 19 个 `Colors` 常量零引用、`_disk_mtime` 5 处只写不读、`web_config` 不可达 `return True`（已删）、`x-bogus.js` 两个未引用对象、`settings_dialog` 重复 import 等 | 不可达 `return True` | 纯删除批次（`x-bogus.js` 需同批重钉 `_JS_SHA256_EXPECTED`） |
| L-02 | 重复代码 | `gui.py` 5 处异常日志模板；`utils` 的 sync/async 守卫已抽取；三个安装器原共享层现已内联为孪生块（由 `TestInlineInstallGuardParity` 锁定）；`haixiu.js` 13 个近重复函数 | `utils._log_guarded_exception` | 孪生副本补等价性测试；`haixiu.js` 不建议动（供应商混淆脚本） |
| L-03 | 硬编码文案 / i18n | `gui.py` 的 `ts → {save_fmt}`；`src/gui_qt/recorder.py` 等 15+ 条中文日志；`notify.py` 把常量名当占位符 | — | 改 `tr()` + 四目录登记（五处同改） |
| L-04 | 编码/空值/边界 | `bilibili` 颜色整数未钳制（负值/超 0xFFFFFF）；`huya`/`bilibili` 进房参数 `int()` 前只判真值；`twitch._line_buf` 无上限且 `start()` 不重置；5 处 `WsClient` 前不关闭旧实例 | `utils.is_safe_http_url` 补 netloc、`stream.get_quality_index` 完整解析 | 逐条补显式校验与钳制 |
| L-05 | 命名/魔法数 | `stream.py` 冗余 `json.JSONDecodeError`；`ui_theme` 0.18 仍有 10 处裸写（`_HOVER_SHADE_RATIO` 常量已加但未接线，当前是死常量）；页标题由导航按钮文本 `split("  ")[-1]` 派生 | — | 常量接线 + 去掉冗余异常成员 |
| L-06 | 协议/二进制解析 | `_tars` 三处读取绕过 `_need`（截断帧抛 `IndexError`/`struct.error`）；抖音凭据作废基于异常文本正则且无节流；`_xbogus` salt 用非密码学 `random` | — | 统一 `_need`；作废加节流；salt 改 `secrets` |
| L-07 | proto 定义 | `EpisodeChatMessage.common` 类型错误、`message kk`/`Rsp` 调试残留、4 处拼写错误 | — | **阻塞**：本环境无 protoc，且 AGENTS 禁止手改生成文件——需先解决「同代重新生成」工具链 |
| L-08 | 前端/VBS/脚本小项 | `web/app.js` 的 `downloadFile` 超时、`scripts/*` 判定面、`spike_*.sh`、`ffmpeg_proc`/`srt_writer` 小项均已随 M-84/88/96/58 修复；**剩余 `src/javascript/liveme.js` 的加载期求值与调试输出、`x-bogus.js` 的动态求值（即 M-86/M-87）** | 同左（大部分） | 见下方 M-86/M-87 条目（需真机验签） |
| L-09 | 测试可维护性 | 37 个测试函数名跨文件重名 108 处；90 个测试文件对生产源码做形态锁；5 处手写 `saved=` 恢复；1 处未配对的 `mkdtemp`；1 处 `pytest.raises(Exception)`；2 个前端入口整文件 `skipif` | — | 形态锁标注、`monkeypatch` 统一、前端「有 skip 即红」判据 |
| L-10 | 注释与实现漂移 | `ui_motion` 的 `disable()` 不存在（已随 M-82 修正）；`_tars` 文件头 CR-03 的不变式仍未成立（随 L-06 一起修）；`gui_qt/main_window.py` 启动重译注释（已随 M-78 修正） | M-78/M-82 两处 | 只剩 `_tars` 的 CR-03，须与 L-06 同批修，**不得**只改注释 |

---

## 6. E 类：工程侧待决

### M-08（残留半）成功/早退路径不清理临时 stderr 文件

- **级别**：中等（资源）
- **当前锚点**：`main.py::check_subprocess`；`_ffmpeg_stderr_path` 在 `tempfile.gettempdir()` 下按 uuid 生成，`_read_ffmpeg_stderr_tail` 读后自删——但只在 `rc != 0` 分支被调用
- **现状**：成功轮、看门狗卡死早退、被注释/停止早退都不删文件；ffmpeg 把进度写 stderr，一轮 6h 可留数 MB，逐轮累积。
- **为什么未做**：`finally` 在 `rc != 0` 读取**之前**执行，直接在那里删会让失败归因丢失尾部；需在每条 `return` 前分别清理，或重构为「尾部读取统一放在最外层 finally」。
- **建议方案**：把「读尾部 + 删除」抽成一个 helper，在每个出口调用（成功轮只删不读）；或用一个包裹整个函数体的 `try/finally` 统一收尾（改动较大但一次到位）。
- **验收判据**：连续成功录制 N 轮后临时目录无 `dlr_ffmpeg_*.log`；`rc != 0` 的尾部日志仍出现在 `streamget.log`。

### `_ci_web_smoke.sh` 缺 `set -e`

- **级别**：中等（脚本健壮性）
- **当前锚点**：`scripts/_ci_web_smoke.sh` 顶部 `set -uo pipefail`
- **现状**：中间步骤失败被静默吞掉。**pkill 误杀半已修**（不再 `pkill -f 'python web\.py'`，只清本轮进程树）。
- **为什么未做**：① 第 83-84 行需要 `python scripts/smoke_test.py ...; rc=$?` 捕获冒烟退出码，直接 `set -e` 会在捕获前中止；② 本机 `bash` 当时是 WSL 占位器，无法验证控制流改动。
- **建议方案**：加 `set -e` 的同时把该行改为 `rc=0; python ... || rc=$?`；`total=$(...)` 改为 `|| total=""`。改完在真实 bash 环境跑一次完整冒烟。
- **验收判据**：注入一个中间步骤失败（如临时改错报告路径），脚本以非 0 退出且不掩盖冒烟结论；正常路径退出码与现状一致。

---

## 7. F 类：流程性建议（需维护者批准）

报告 §8.1 的四条流程建议中，第 2、3、4 条已部分落地（会话经验、门禁导出通道、R11 棘轮）。剩余第 1 条：

- **把「判据族」写进 `AGENTS.md` 的已知坑**：主机匹配、内网判定、同域判定、凭据脱敏四个判据各自只保留**一个实现**，任何新增调用点必须引用而非重写。
- **为什么未做**：`AGENTS.md` 是项目唯一事实源，新增长期约定需维护者确认措辞与归档位置。
- **建议落点**：「已知坑」下新增一段「判据族（主机 / 内网 / 同域 / 脱敏）」，并指向 `src/stream_select.py`、`src/platforms/bilibili.py`、`src/utils.py`、`src/async_http.py` 的现有实现。
- **验收判据**：新增调用点若自带一份判据，code review 可依此条直接打回；`scripts/check_skill_agents_consistency.py` 不受影响。

---

## 8. 建议排期

| 优先级 | 条目 | 理由 |
| --- | --- | --- |
| P0 | M-08 残留、`set -e`、M-32 | 直接影响日志/临时文件与探针可用性，改动面小 |
| P1 | M-07、M-10、M-26 后半、M-31 | 影响入口生命周期、熔断判据与录制成功率；需先拍板 |
| P1 | M-15、M-18 后半、M-29 ACL、M-86/M-87 | 需平台/系统事实或真机验签，可在拿到样本/联网后逐条关闭 |
| P1 | M-75（Qt 半） | 日志链路未脱敏，属凭据落盘红线；需先定脱敏点 |
| P2 | M-27、M-30、M-34、M-74 | 并发与 GUI 收敛，建议与下一次对应专项同批 |
| P2 | M-13、M-17、M-19 | 死代码/解析器/跨平台抽取，单独立项 |
| P2 | S-14 存量、M-100~M-104 | 测试有效性，长期收益 |
| P3 | L-01~L-10（除 L-07） | 技术债窗口，必须与行为变更分开提交 |
| 阻塞 | L-07 | 需 protoc 工具链决策，当前环境无法重新生成 |

---

*整理日期：2026-10-21｜依据：第二轮整改后的工作区实测 + `CODE_REVIEW_2026-10-21.md` 原编号｜未修改任何源文件*
