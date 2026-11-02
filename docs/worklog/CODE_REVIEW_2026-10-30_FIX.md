# CODE_REVIEW_2026-10-30 未修复项清单（整改批遗留）

> 生成：2026-10-31，整改会话收口时点。整改批主体（P0 五条 + P1 八条 + P2 三条 + L 组可定位项）已落地并经门禁全绿，已修复项见 `CODE_WIKI.md` / `CODE_WIKI_EN.md` 更新日志 2026-10-31 条目，本文件不重复。
> 基线：整改批落地后的工作区（55 个跟踪文件修改、未提交）。
> 每项含：来源条目、精确位置、未修原因、交回动作、复验判据。登记口径与源报告一致（行号为整改批落地后实测，源报告行号仅在上游无改动时相同）。

## 1. 待用户裁定（整改批内未动）

| 项 | 位置 | 状态与交回动作 |
| --- | --- | --- |
| **M-17** haixiu/haihai 硬编码默认 accessToken | `src/spider.py:5922-5926`（`_read_haixiu_token_override` 兜底两段双重 URL 编码值） | 报告明示「交用户裁定、不得静默删除」。整改批经提问提交三个选项（a 补来源说明维持现状 / b 外移 config+env 必填 / c 暂不处理），**未获答复**，维持现状。裁定后动作：选 a 则在缺省值上方补一行来源说明；选 b 则删硬编码、缺省时抛「请配置 accessToken」明确报错（涉平台解析，需真实 URL 验证嗨秀/来嗨两分支） |
| **M-23** `.zcode/config.json` 与 `config/URL_config.ini` 跟踪态 | `git ls-files` 命中两文件（URL_config 当前 15 行全注释；.zcode 为本地工具配置） | 报告 §9.3「先交用户裁定再动」。同一提问未获答复，维持跟踪态。**风险**：URL_config 一旦本地填入真实流地址（可含 `user:pass@`/token），`git add .` 即带凭据入库。裁定后动作：`git rm --cached <两文件>`（本地保留）+ CODE_WIKI 登记说明 |

## 2. 待人工确认（无法唯一定位 / 缺核对基准）

| 项 | 位置 | 缺失信息与复验判据 |
| --- | --- | --- |
| **L-03 残留**：TikTok 回退基准硬编码 `< 4` | `src/stream.py:710`：`fallback_base = quality_index + 1 if quality_index < 4 else max(quality_index - 1, 0)` | 报告称「与抖音判界口径不一致」但未给出抖音分支对齐基准的具体定义，无法唯一确定修复形态。需先确认抖音侧判界（`main.py`/`spider.py` 画质分档判据）后再改；改动属选源回退语义，须真实 URL 验证（DoD 第 2 步） |
| **L-14④** execjs 构造器参数序 | `typings/execjs/__init__.pyi:20`：`ExternalRuntime.__init__(self, name, runtime, code)` | 本地 venv 未安装 PyExecJS（主运行时 exejs 1.0.1 自带 py.typed、PyExecJS 仅回退分支），无源码可核对上游签名。复验判据：取得 PyExecJS 1.5.1 源码后对齐 `__init__` 参数序；`get`/`get_from_environment`/`runtimes` 三签名已于整改批对齐 `_runtimes.pyi` |

## 3. 暂缓（有明确理由，位点已固定）

| 项 | 位置 | 未修原因 | 交回动作 |
| --- | --- | --- | --- |
| **L-02 全族**（A 类 JSON 请求体拼接 6 处 + B 类 URL 未编码 38 处，另 8 处服务端值次级位点） | A 类：`spider.py:1772-1776`（YY cid×2）、`:4563`（百度）、`:6546`（淘宝）、`:6737/:6758/:6776`（京东）；B 类报告锚点：`:1862/:1833`（B站）、`:2203`（B站弹幕）、`:5471`（AcFun userId）、`:4157/:4164`（popkon anchor_id/partner_code）；其余 34 处主位点完整清单已逐条核验登记于整改会话记录（探查代理按行号+变量名+来源函数输出，截至 HEAD 整改后状态） | 修复 = `json.dumps` 重写请求体 / `urllib.parse.quote(x, safe="")` 包插值——全部属「改变线上请求字节形态」，DoD 第 2 步真机验证不可豁免且本会话无外网条件；报告定级轻微、无 SSRF 外溢（host 恒平台域） | 下一批按「A 类优先（结构性破坏风险）→ B 类按平台分组」逐点落地，每组以真实 URL 增量验证；已知正确形态参照 `:6310`、`:5760-5761`（quote）与 `:741` 等 `urlencode(params)` 查询形态 |
| **L-04③** PyInstaller 子进程无 timeout | `build_exe.py:303`：`_ = subprocess.run(cmd, check=True, cwd=PROJECT_ROOT)` | 整改批三次尝试补 `timeout=3600` 均被 Mimosa PreToolUse 钩子对该行既有形态误判「命令注入」拦截（实为 argv 列表、无 shell 参与）；不动该行则钩子不触发 | **请用户手工补**：该行加 `timeout=3600`（PyInstaller 正常分钟级，上限放宽到小时级）；同批可把 `cmd` 内联或加注释说明 argv 形态以消除钩子误判源 |
| **L-08②** URL 配置页文案承诺失实 | `gui.py:2709-2711`：文案「点击窗口关闭按钮将最小化到系统托盘」，实际弹确认对话框且 tkinter 路径无托盘（`:4656-4659` 恒告警） | 修正 msgid 需同步 gui i18n 四语目录（新键入库 + `.mo` 重编译），超出整改批最小 diff 口径 | 随下次 gui 触碰改文案为「弹出退出确认」并四目录同改；或实现真正的最小化到托盘（行为改造，另立任务） |
| **L-08③** 10 处 except-pass 无 ±4 行归因 | `gui.py:956/:2473/:2500/:2678/:3209/:3228/:3250/:4634/:4650/:4876` | 报告自身口径「后者下次重构补归因注释」（逐处复核均为噪声级、白名单 #4 观察项） | 下次 gui 重构逐处补归因注释 |
| **L-09** 结构度量族 | 超长函数 15 个（`main.py::start_record` 796 行、`src/web_api.py::create_app` 958 行、`_validate_stream_url` 280 行等）、深嵌套 ≥6 层 30 处、≥9 形参 10 处 | 报告口径「不单独造大 diff，随重构顺势拆分」；与本批「不做额外重构」约束一致 | 下一条新功能落地前先对 `start_record`/`create_app`/`_validate_stream_url` 三处做纯拆分；XHS/Shopee/知乎三处同构「短链落地页双闸校验」优先抽公共 helper |
| **L-10** web 前端稳健性三项 | `web/app.js:241-257`（api() 超时只护到响应头，clearTimeout 应移到 body 读取后）、`:1115-1153`（日志/弹幕轮询无退避，与 SSE_BACKOFF_STEPS 口径分叉）、`:1734-1835`（saveConfig 无 configChain.isCurrent 复核） | 前端行为变更需浏览器联调验证（`tests/frontend/*.mjs` 无这三条路径的既有覆盖） | 随下次前端批次落地并补 `.mjs` 用例（新增 `.mjs` 须走登记 + `.py` 包装双文件结构） |
| **L-11 残留** spike 脚本 set -e 静默中止 | `scripts/spike_arm64_static_ffmpeg.sh:278`：`OTOOM_LINES="$("$FFMPEG_BIN" ... && otool -L ...)"` | 整改批 L-11 实际落地九项，本项为收口时复核发现的第十项（报告原文定位，整改批漏列） | `set -e` 下命令替换失败会静默中止、丢验收诊断出口；改为显式 `if ! OTOOM_LINES="$(...)"` 分支保诊断输出后中止 |
| **L-16① 残留** stream_select 第二份 inet_aton 模拟 | `src/stream_select.py:428`（`_aton_part`）、`:454`（消费点）；残余面已在 `src/async_http.py:618-621` 登记 | 删除副本需把派生跳离线闸门改调 `web_config.offline_internal_reason` 统一判据——安全判定面合并，需真机验证派生跳行为等价 | 随下次选源链触碰改调统一判据并删 `_aton_part`，变异验证（改坏 web_config 判据确认选源闸转红） |
| **L-16②** ci.yml warnings 门禁二次全量跑 | `.github/workflows/ci.yml:567-576、:769-782` | CI 现为仅手动触发，无法本地验证 workflow 改动；test job 最重路径改 tee 复用属 CI 链行为变更 | 下次手动触发 CI 时同批改（第一次带覆盖率的 pytest 输出直接 tee 供 Gate 步骤 grep），验证以手动触发实跑为准 |
| **L-16③** 根 index.html | `index.html:164-169/:210/:248`（httpToHttps 强升弄坏局域网纯 HTTP 流、CDN 失败点击播放抛未捕获 ReferenceError） | 上游遗留形态，页面自我定位为「本地双击打开的独立播放器」（`.dockerignore:126` 刻意排除），整改批判定为备案级 | 若要修：强升改为「仅 https 页面来源时升级」+ CDN 失败兜底提示；属独立小任务 |
| **L-12①** SetConsoleCtrlHandler 返回值未检查 | `src/gui_qt/shared.py:330-332` | 注册失败时 CTRL_BREAK 广播可命中 GUI 自身；Qt 行为变更无真机验证面 | 补返回值检查 + 失败告警日志；随 Qt 批次真机验证 |
| **L-12②** 房间移除后筛选复位不触发弹幕流重绘 | `src/gui_qt/pages/danmaku.py:200-258` | 同上（旧房间消息残留显示，属交互语义变更） | 随 Qt 批次落地并真机验证重绘时序 |

## 4. 备案项（报告自身已定备案，不构成未修缺口）

| 项 | 位置 | 说明 |
| --- | --- | --- |
| DouyinLiveRecorder.spec icon 为生成机绝对路径 | `DouyinLiveRecorder.spec:53-57` | build_exe 自动生成物，正常路径每次重生成 |
| standalone 孪生漂移（上轮 M-24） | `scripts/douyin_live_recorder_standalone.py:1202`（rid 正则）、`:948`（h265 剔除口径） | 上轮已列 P3 待办；机检面 `tests/test_regression_standalone.py` 在位 |
| 上轮遗留 M-32/M-33（12 处平台 skip 与 sys.platform 形态） | 8 处 monkeypatch + 5 处 skipif（T1 全量扫描定位） | 报告 §9.3「按既定方案继续」，维持 P2 待办原状 |
| 报告 §7.1 悬空回归锁引用余量 5 处 | 3 处 tests 文件头注释旧名 + 2 处 `.agents/` 技能文档 | 报告判定为无害旧名/文档引用，未列入本批修复面 |

## 5. 未执行验证（DoD 第 2 步交回，非代码缺口）

| 对象 | 未执行内容 | 交回动作 |
| --- | --- | --- |
| M-02 / M-03 / L-01 | 平台解析容错路径的真实 URL 增量验证（AcFun、B站、PandaTV、WinkTV、TTingLive、VV星球、XHS、知乎） | 请用户有活房间时以 `tests/test_{bili,douyin,...}_live_collector.py` 人工通道跑；容错路径成功路径字节不变，风险面为「降级归因是否按预期落日志」 |
| M-05 | 「模板临时改 0.0.0.0」验证冻结子进程确实读到补丁值（`build_exe.py --smoke` 全链） | 需打包环境；补丁窗口已扩到探活循环（结构锁在位），真机时序待验 |
| M-08 / M-09 | 面板端到端（写 web_tray_icon 被拒、favicon 非 ICO 404、缩进注释行启用真翻转） | TestClient 单测已覆盖三面（`tests/test_web_api.py`），真实浏览器操作未做 |

## 6. 复核口径

- 本文件行号基于整改批落地后的工作区实测（2026-10-31）；后续改动请先 `git status` 确认基线。
- 每项复验用「位点 + 判据」即可独立复核；判据里标注的既有测试（如 `tests/test_regression_standalone.py`）为护栏，不是本项的修复证明。
- 关闭任一项时请同步：本文件删行 + `CODE_WIKI.md`/`CODE_WIKI_EN.md` 更新日志追加 + `.workbuddy` 当日记录。
