# DouyinLiveRecorder 全量源代码审查报告

- **报告日期**：2026-09-20
- **审查对象**：`D:\DouyinLiveRecorder-dev`
- **版本基线**：4.3.0（唯一事实源 `pyproject.toml`，`scripts/check_version.py` 实测通过）
- **运行环境**：Python 3.14.7（项目 venv）/ Node.js v24.21.0 / Windows 10 (10.0.26200) x64
- **审查方式**：静态源码通读（分组并行、非抽样）+ 严重/中等条目**逐条回源复核** + 关键论断**可执行探针实测** + 全部门禁实跑
- **结论摘要**：正文登记 **103 项**（**严重 10 / 中等 69 / 轻微 24**），附录 D 本地补扫再增 **3 项**（中等 1 / 轻微 2），**合计 106 项**（严重 10 / 中等 70 / 轻微 26）。补扫原登记的 **补-01**（门禁入口脚本自身未过 black）与 **补-06**（`AGENTS.md` 链接/锚点缺陷）已于 20:48 复核时确认**由作者就地修复**，改标「已消解」并从统计中剔除（取证与消解过程保留在 D.2/D.7，口径见 D.8）。上一轮（2026-09-18）12 项严重缺陷**无一回归**，但其中 **4 项（CR-07/08/09/11）仅部分闭合**；本轮 SEV-02/03/04/05/10 即为其残留或旁路。

---

## 一、审查概述与背景

### 1.1 背景

DouyinLiveRecorder 是覆盖 60+ 直播平台的一体化工具，以三种形态分发：CLI（`main.py`）、桌面 GUI（`gui.py`，customtkinter + pystray）、Web 管理面板（`web.py` + FastAPI + 原生 JS）。主运行链路为：

配置热加载（`config/config.ini`、`config/URL_config.ini`）→ 房间线程分派（`_PLATFORM_RESOLVERS`，52 个解析器）→ 平台接口解析（`src/spider.py`、`src/platforms/*`、`src/javascript/*.js` 经 Node 签名）→ 选源与可达性探针（`src/stream_select.py`）→ FFmpeg 子进程录制（`main.py::check_subprocess`）→ 录后转封装（`src/video_postprocess.py`）→ 并发调度与按 host 熔断（`src/scheduler.py`）。旁路包括**弹幕采集链**（WebSocket → protobuf/Tars/IRC → SRT 落盘）与**面板控制链**（HTTP → 行级配置写回）。

该架构决定三个高风险面：① **不可信输入边界**（平台返回的 JSON/HTML、直播二进制帧、用户与面板提交的 URL/配置）；② **长生命周期进程的资源治理**（每房间一线程一事件循环、子进程、有界队列、跨线程锁）；③ **凭据处理面**（Cookie/Token/SMTP 授权码/Webhook，以及自动安装器与远程 WASM 下载的第三方二进制）。

### 1.2 审查目标

按要求覆盖工作区全部**自有**源文件（Python / JavaScript / HTML / CSS / VBScript / YAML / TOML / Dockerfile / GitHub Actions），逐文件记录问题、所在路径与修复建议，排查五类缺陷：代码质量、潜在缺陷（空值/越界/竞态/资源泄漏）、安全漏洞（注入/穿越/凭据泄露/SSRF/XSS/鉴权/供应链）、逻辑错误（分支绑定错误、默认值漂移、判定口径错误）、可靠性与可观测性。

### 1.3 审查方法

1. **范围确立**：枚举全部源文件并剔除第三方依赖与构建产物，形成可核对的覆盖率基准（见 2.1，**146 个文件 / 56,543 行**）。
2. **分组并行通读**：按运行链路划为 7 个模块组（`main.py`；选源与录制层；平台解析与签名层；并发与弹幕层；Web 面板；GUI/i18n/推送/安装器；JS/打包/CI/测试），每组**全文分段通读**，要求每条结论附 `文件:行号`、逐字符原文片段（≤12 行）与置信度。
3. **逐条回源复核 + 可执行探针**：全部 **10 项严重**条目由复核环节重新打开原文核对可达性与触发链；中等条目中标注「实测」者已由复核环节以真实函数或对照实验复现，其余中等/轻微条目依据分组审查者的全文通读结论，并逐条附带可定位的 `文件:行号` 与原文片段以便复核。凡可脱离网络验证的判断，一律以实跑取代推测。本轮实测结论：
   - `_shopee_host_suffix()` → 拼出 `https://live.shopee.shopee.sg` 等非法域名（SEV-06）；
   - `_validate_room_url_target()` 9 条载荷 → 7 条应拦者中 **5 条放行**（SEV-03）；
   - `delete_line()` CRLF/LF A/B 对照 → CRLF 永删不掉、LF 正常（SEV-05）；
   - `mask_credentials()` 9 条样本 → `cookie=`/`sid_guard=`/`ttwid=`/`Authorization:`/JSON 体 **全部未脱敏**（MID-29）；
   - i18n 门禁用例 AST 复算 → 门禁可见 347 处、**10 处含占位符的真实违规逃逸**（MID-67）；
   - 语言下拉折叠逻辑复算 → `'English'` 反查恒得 `en_GB`（MID-52）；
   - `'\ufeff#a'.strip().startswith('#')` → **False**，证实 GUI 空配置判据被 BOM 绕过（MID-50）。
4. **约定对齐**：严格尊重本项目既定约定（`#` 行注释不用 docstring、`except A, B:` 为 PEP 758 风格、line-length 120、四语 i18n 同源、探针节流/退避/虎牙 FLV-first、`-reconnect*` 位置与 m3u8 特例、跨循环不创建 `aclose` 协程、`requests.Session` 线程级复用等），不将刻意设计登记为问题；相关核对结论单列第九章供后续审查者复用。
5. **补充证据源**：另执行 Qoder 云端全仓库安全扫描（异步任务，链接见附录 C），其结论不并入本表、仅作交叉参考。

### 1.4 结果统计

| 严重程度 | 数量 | 判定口径 |
|---|---|---|
| **严重** | 10 | 默认配置/常规输入下即导致录制失败或产物损坏、面板可被接管、凭据明文落盘，或安全防线实质失效 |
| **中等** | 69 | 特定但现实可达条件下功能失效、资源/状态泄漏、并发约束失守、静默降级不可观测、门禁假绿 |
| **轻微** | 24 | 口径不齐、误导性注释/文案、防御纵深缺失、可维护性与配置卫生 |
| **合计** | **103** | — |

> 本表与下表的分组分布仅统计**第三至五节正文**条目（103 项）。附录 D 本地补扫另计 **3 项**（中等 1：补-05；轻微 2：补-03、补-04），全报告合计 **106 项**（严重 10 / 中等 70 / 轻微 26）；附录 D 的 补-01、补-06 已在定稿前由作者修复、消解不计入，统计口径见 D.8。

按审查分组分布（与第三/四/五节的小节划分一致，每项只计入一组）：

| 审查分组 | 严重 | 中等 | 轻微 | 小计 |
|---|---|---|---|---|
| 录制主链路与产物判定（`main.py` / 状态 / 收尾） | 2 | 15（MID-01…12、30…32） | 4 | 21 |
| 选源与流地址（`stream_select.py` / `stream.py`） | 0 | 8（MID-13…20） | 4 | 12 |
| 并发·网络·弹幕·资源治理 | 1 | 9（MID-21…29） | 4 | 14 |
| 凭据与 Web 面板安全面 | 4（SEV-02…05） | 7（MID-33…39） | 0 | 11 |
| 平台解析与签名层（`spider.py` / `platforms`） | 2 | 11（MID-40…50） | 2 | 15 |
| GUI·i18n·推送·安装器 | 0 | 10（MID-51…60） | 1 | 11 |
| JS / 打包 / CI / 门禁与测试可信度 | 1（SEV-10） | 9（MID-61…69） | 8 | 18 |
| 约定与文档漂移 | 0 | 0 | 1 | 1 |
| **合计** | **10** | **69** | **24** | **103** |

> 条目数多于上一轮（62 项）并非质量下降，而是：① 新增 64 个测试文件与 CI/Docker 的**测试可信度**专项；② 上一轮的修复自身引入了若干**新失配点**（CR-09 新校验器的旁路、CR-05 看门狗的判据基准）；③ 复核口径更严——无法给出具体触发路径的推测一律未登记。

---

## 二、审查范围

### 2.1 覆盖清单

| # | 模块组 | 主要文件 | 文件数 | 行数 | 深度 |
|---|---|---|---|---|---|
| 1 | CLI 主入口与录制编排 | `main.py`（1–4481 行逐块通读） | 1 | 4,481 | 全文 |
| 2 | 根入口与打包 | `gui.py`、`web.py`、`i18n.py`、`msg_push.py`、`build_exe.py` | 5 | 5,309 | 全文 |
| 3 | 选源与录制层 | `src/stream_select.py`、`stream.py`、`ffmpeg_proc.py`、`video_postprocess.py`、`recorder_status.py` | 5 | 2,830 | 全文 |
| 4 | 平台解析层 | `src/spider.py`（5,480 行全文）、`room.py`、`ab_sign.py`、`ttwid.py`、`cookie_cache.py`、`weverse_auth.py` | 6 | 6,709 | 全文 |
| 5 | 平台专属与弹幕协议 | `src/platforms/*`（douyin/douyu/huya/bilibili/twitch/`_xbogus`/`_tars`） | 8 | 1,544 | 全文 |
| 6 | 并发·网络·状态 | `scheduler.py`、`async_http.py`、`sync_http.py`、`http_config.py`、`proxy.py`、`collector.py`、`danmaku_monitor.py`、`ws_client.py`、`srt_writer.py`、`notify.py`、`logger.py`、`utils.py`、`base.py`、`__init__.py` | 14 | 4,585 | 全文 |
| 7 | Web 面板后端 | `src/web_api.py`、`web_config.py`、`web_tray.py` | 3 | 1,749 | 全文 |
| 8 | Web 面板前端 | `web/app.js`、`web/index.html`、`web/style.css`、根 `index.html` | 4 | 2,308 | 全文 |
| 9 | 配置读写与运行期文件 | `src/config_io.py`、`config_bool.py`、`log_archive.py` | 3 | 603 | 全文 |
| 10 | 客户端 JS 签名脚本 | `src/javascript/*`（migu/x-bogus/haixiu/liveme/…） | 7 | 1,868 | 全文（`crypto-js.min.js` 为第三方压缩产物，仅核哈希） |
| 11 | 安装器 | `src/ffmpeg_install.py`、`node_install.py` | 2 | 775 | 全文 |
| 12 | 维护脚本 | `scripts/*.py`（10 个） | 10 | 3,919 | 全文（standalone 2,027 行按历史产物口径抽样核对本仓一致性） |
| 13 | 测试 | `tests/*.py`（62）+ `tests/frontend/*.mjs`（1） | 64 | 16,906 | 可信度专项（第七章） |
| 14 | 构建·CI·容器 | `Dockerfile`、`docker-compose.yaml`、`pyproject.toml`、`requirements.txt`、`.github/workflows/*`（4）、`.github/actions/retry/action.yml`、`StopRecording.vbs`、`.gitignore`、`.dockerignore` | 11 | 3,070 | 全文 |
| | **合计** | | **146** | **56,543** | |

### 2.2 明确排除项

`.venv/`（含 basedpyright、nodejs_wheel 等第三方包）、`node/`、`ffmpeg/`（自动下载的运行时二进制）、site-packages 内的任何第三方库、`src/javascript/crypto-js.min.js`（第三方压缩产物）、`DouyinLiveRecorder.egg-info/`、`build/`、`dist/`、`__pycache__`/`*.pyc`、`logs/`、`downloads/`、`backup_config/`、`.mypy_cache/`、`.pytest_cache/`、本地工具目录（`.workbuddy/`、`.mimosa/`、`.v2c/`、`.codebuddy/`）、`typings/`（第三方库存根）；`src/proto/douyin_pb2.py`（protoc 生成、标注 DO NOT EDIT，仅核对 `.pyi` 存根与引用字段一致性）。`config/config.ini` 与 `config/URL_config.ini` 仅作为**运行期数据**读取其行尾/编码/BOM 等事实特征（用于 SEV-05、MID-50 的判定），不纳入源码缺陷登记。

### 2.3 验证证据（本轮实跑结果）

| 验证项 | 命令 / 方式 | 结果 |
|---|---|---|
| 单元/集成测试（全量） | `pytest -q` | 首两次运行在 ~28% 处**挂死**（MID-63）；排除该用例后 **1041 passed, 2 skipped（49.82s），0 failed，warnings summary 为空** |
| 前端用例 | `node --test tests/frontend/test_quality_ui.mjs` | **9 passed**（133ms；与 MID-63 构成对照） |
| 格式门禁 | `python -m black --check --line-length 120 --target-version py314 .` | 18:4x 快照：136 files unchanged，**通过**。20:2x 新增 `scripts/run_gates.py` 后该步一度转为**失败**（补-01）；20:48 复跑 **139 files unchanged / rc=0**，补-01 已消解 |
| 导入排序门禁 | `python -m isort --check-only --profile black --line-length 120 .` | rc=0 **但静默跳过 16 个自有文件**（MID-62）；20:2x 起经新入口 `scripts/run_gates.py` 执行同样跳过 16 个且不判失败（补-02），20:48 复跑仍为 **16 条 `Unable to parse file` + rc=0**，未消解 |
| 类型门禁 | `mypy`（无路径参数） | **no issues found in 117 source files** |
| 类型门禁（平台双跑） | `mypy --platform linux` | **no issues found in 117 source files** |
| 本地严格门禁 | `basedpyright`（无路径参数） | **0 errors, 0 warnings, 0 notes** |
| 注释规范 | `python scripts/check_annotations.py` | 通过；平均密度 22.8%，最低 13.2%（阈值 13.0%） |
| 翻译同步 | `python scripts/compile_po.py --check` | `.mo` 与 `.po` 同步，**636 条**（含头部空 msgid，目录条目 635） |
| 待翻译串 | `python scripts/extract_i18n_strings.py` | 运行时 420 条、`zh_CN.po` 635 条，**缺失 0 条** |
| 版本动态化 | `python scripts/check_version.py` | **PASS**（Dockerfile 为字面引用，但存在 LABEL 顺序缺陷，MIN-14） |
| 覆盖率门禁 | `python scripts/check_coverage.py` | **未能出具结论**：单独调用时 `coverage json` 无数据可读（MIN-19） |
| 依赖清单一致性 | 脚本化剥行内注释后比对 | `requirements.txt` 20 条 == `pyproject` 20 条，**零差异**；`protobuf>=6.31.1,<8` 上限仍在（F-14 满足），已装 7.36.1 |
| JS 完整性钉定 | 逐文件 SHA256 对 `_JS_SHA256_EXPECTED` | **7/7 匹配**，无 stale |
| RCE/注入基线 | `grep shell=True / os.system / eval / exec / pickle / yaml.load` | 自有代码 **0 命中**；解压走真实路径校验 + `tarfile filter="data"` |
| CI 门禁掩盖 | `grep continue-on-error .github/` | **0 处** |
| PEP 758 非法形 | 全仓 `except A, B as e:` 扫描 | **0 处**；`@decorator` 与 `def` 间插注释扫描 **0 处** |
| 类型抑制与死代码 | `grep type: ignore`（11 处，均带具体 code，无平台符号类违禁用法）、`# noqa`（**0** 处）、`TODO/FIXME`（**2** 处） | 无违禁抑制 |

---

## 三、严重问题（P0，10 项）

### SEV-01 ｜ 并发信号量把「可用许可数」当作「容量」，每轮重算向上补满 → 网络并发上限实质失控

- **位置**：`src/scheduler.py:69-89`（`release`/`set_value`/`value`）、`src/scheduler.py:279-283`（`recompute`）
- **原文**：
```python
    def release(self) -> None:
        with self._cond:
            self._capacity += 1          # 语义是「可用许可数」
            self._cond.notify()
    def set_value(self, new_value: int) -> None:
        new_value = max(0, int(new_value))
        with self._cond:
            delta = new_value - self._capacity
            self._capacity = new_value   # 绝对赋值：把可用数直接抬到目标值
```
```python
        new_cap = self._compute_capacity()
        if new_cap != self._network_semaphore.value:   # value == 可用数，不是容量
            self._network_semaphore.set_value(new_cap)
```
- **详细说明与影响**：`acquire` 递减、`release` 递增同一字段，故 `_capacity` 表示**剩余许可**；而 `recompute()` 拿它与目标容量比较并无条件赋值。设目标 T=12、12 个房间各持 1 槽（可用=0），`adjust_loop` 每 5s 以及主循环每轮的 `set_active_count()`（`main.py:4458`）都触发 recompute：`0 != 12` → 可用数被抬回 12，而旧持有者仍在持有 → **实际并发 24**；只要存在排队者，每轮净增 T，直至受房间线程数封顶。错误率背压的 `target*0.6` 降容在下一轮被补满抵消；固定并发模式（`最大同时录制数` 非 0）下 `_compute_capacity()` 恒返回 `configured`，但只要有人持槽就被反复补满，「同一时间访问网络的线程数」形同不存在。
  这正是该调度器所要取代的旧模型（80 房间挤 3 槽）的**反向故障**：并发无界 → 多房间对同一 CDN 毫秒级连击 → 触发风控 403/超时，方向与「探针节流/抖动」「虎牙连接预算限流」两条既有防御完全相反，且会以「偶发 403」形态被误判为平台问题。
- **改进建议**：拆为 `_capacity`（上限）+ `_used`（已持有）：`acquire` 判 `_used + 1 > _capacity`、`release` 置 `_used -= 1`、`set_value` 仅改 `_capacity` 并按 `capacity - used` 与等待者数 `notify`；`recompute()` 比较 `semaphore.capacity`；`src/recorder_status.py::_live_network_capacity()` 同步改用 capacity（当前读 `.value`，控制台显示的是**空闲槽数**而非容量，亦属误导）。
- **验证方式**：新增「持有 N 个许可后触发 recompute，实际并发仍 ≤ T」用例。现有 `tests/test_scheduler.py`（16 用例）均在无持有者场景断言 `.value`，**结构上抓不到本缺陷**。
- **置信度**：高（纯代码推演即可闭合）。

### SEV-02 ｜ `PUT /api/rooms` 完全绕过房间入口校验，SSRF 与任意 scheme 防线在此失效

- **位置**：`src/web_api.py:444-449`
- **原文**：
```python
    @app.put("/api/rooms")
    async def update_room(req: RoomUpdate) -> dict[str, object]:
        old_url = normalize_url(req.old_url)
        new_line = format_url_line(normalize_url(req.url), req.quality, req.name)
```
- **详细说明与影响**：`POST /api/rooms`（`:427`）与 `PUT /api/rooms/quality`（`:516`）都调用 `validate_room_target`（换行 + CR-09 协议/内网校验），画质另有 `BUILTIN_QUALITIES` 白名单；**只有 PUT 三样都不做**，`format_url_line` 仅挡换行。攻击序列：`PUT /api/rooms {old_url:<已有房间>, url:"http://127.0.0.1:8000/x?a=.flv"}` → 落盘 `URL_config.ini` → `main.py` 分派末项 `_match_stream_suffix(".m3u8", ".flv")` 以**子串包含**命中 → `_resolve_custom_stream` 将原始 URL 送进 ffmpeg `-i`；成败可经 `GET /api/logs` 回读（即 CR-09 注释自述的侧信道）。`normalize_url` 仅在缺 `://` 时补协议，故 `file://`、`rtp://` 亦原样通过；`quality` 不受白名单约束，可写入永不生效的档位。实测确认：CR-09 新增校验器本身拦得住两条标准载荷，但这条**第二条写入口**未接线，等价于防线可被同组接口绕过。
- **改进建议**：`update_room` 起手即 `validate_room_target(req.url, req.quality, req.name)`，画质复用 `change_room_quality` 的白名单；更彻底的是把校验**下沉进 `format_url_line`**（唯一写入口），使「新增/改写」不可能再次分叉；补用例断言「PUT 与 POST 对同一载荷裁决一致」。
- **置信度**：高（调用点缺失可直接读出，攻击链已回源核对）。

### SEV-03 ｜ 内网地址拦截为「字符串前缀黑名单」，多形态地址可绕（实测 7 条中 5 条放行）

- **位置**：`src/web_config.py:219-243`
- **原文**：
```python
    if host.startswith("127.") or host.startswith("169.254.") or host.startswith("0."):
        _blocked = True
    elif host.startswith("10.") or host.startswith("192.168."):
        _blocked = True
    elif ":" in host and not parsed.port:      # 带端口的 IPv6 使整个分支被跳过
```
- **详细说明与影响**：以真实函数实跑（载荷均以 `?x=.m3u8` 结尾以命中自定义流分支）：

  | 载荷 | 期望 | 实测 |
  |---|---|---|
  | `http://127.0.0.1:8080/…?a=.flv` | 拒绝 | REJECTED |
  | `http://169.254.169.254/latest/meta-data/?x=.m3u8` | 拒绝 | REJECTED |
  | `http://2130706433/x?a=.flv`（=127.0.0.1 十进制） | 拒绝 | **ALLOWED** |
  | `http://0177.0.0.1/x?a=.flv`（八进制） | 拒绝 | **ALLOWED** |
  | `http://[fe80::1]:8080/x?a=.flv`（带端口 IPv6） | 拒绝 | **ALLOWED** |
  | `http://100.64.0.1/x?a=.flv`（CGNAT 100.64/10） | 拒绝 | **ALLOWED** |
  | `http://100.100.100.200/latest/meta-data/?x=.m3u8`（阿里云元数据） | 拒绝 | **ALLOWED** |

  即整数/八进制/十六进制 IPv4、完整写法 IPv6、CGNAT 与**非 AWS 云厂商元数据端点**全部穿透；解析到内网的域名（`metadata.google.internal`、`127-0-0-1.sslip.io`）亦不在拦截范围。SEV-02 的缺失接线把绕过成本降为一次 HTTP 请求。
- **改进建议**：改用 `ipaddress` 语义判定（`is_loopback/is_private/is_link_local/is_reserved/is_multicast`），并对 host 先 `socket.getaddrinfo` 解析、校验**全部** A/AAAA 结果，无法解析即拒绝；显式补 `100.64.0.0/10`、`100.100.100.200`、`metadata.*` 域名；把 `_match_stream_suffix` 由子串包含改为按 path 扩展名判定（CR-09 建议项，至今未落地）；注释中写明「DNS 重绑定无法由本层挡住」。
- **置信度**：高（实跑）。

### SEV-04 ｜ 面板认证可被单个写请求热关闭；大小写变体同时绕过口令哈希、防自锁与 token 吊销

- **位置**：`src/web_api.py:578/582/591/601/612`、`web.py:207`
- **原文**：
```python
        if key.casefold() in _DANGEROUS_CONFIG_KEYS_FOLDED:          # 危险键黑名单：已归一
            raise HTTPException(403, "该配置项不允许通过 Web 修改")
        if section == "Web" and key in ("web_auth_enable", "web_password"):   # 未归一
        ...
        if section == "Web" and key == "web_password" and value.strip():     # 未归一
            if not is_hashed_web_password(value):
                value = hash_web_password(value)
```
- **详细说明与影响**：同一函数内对危险键刻意 `casefold()`（注释：判定须与行匹配的 IGNORECASE 同等强度），但 CR-08 的防锁死/防清空、口令哈希化、改密吊销 token 三处守卫**全部大小写敏感**。`configparser` 的 option 本就大小写不敏感，故写入 `WEB_PASSWORD` 命中同一配置行、却跳过全部三项守卫：① 明文密码落盘（违反 CR-07 与口令存储约定）；② 既有 token 不吊销（「改密踢人」这一泄露兜底失效）；③ 认证关闭（出厂默认 `web_auth_enable = false`）时写入攻击者掌握的密码、再以 `WEB_AUTH_ENABLE` 绕过目标态判定打开认证 → **面板接管**，并踢掉全部在线会话。
  叠加面：`web.py:207` 的「非回环 + 无认证」防护只在**启动瞬间**评估一次，而鉴权中间件每请求重读 `web_auth_enable`。于是一个 `0.0.0.0` + 已开认证的部署，任何持有 token 者提交一次 `key=web_auth_enable, value=false` 即可在**不重启**的情况下变成「无认证 + 全网卡监听」，`/api/config`、`/api/logs`、`/api/files`、房间写入随之全开。
- **改进建议**：入口处一次归一 `key_norm = key.strip().lower()`，Web 节全部判定（敏感键/白名单/哈希/吊销）统一使用；把「认证降级」视为敏感变更——`web_auth_enable` 置 false 且 `web_host` 非回环时要求显式二次确认或直接拒绝；中间件每请求重跑同一不变量；补大小写变体裁决一致性用例。
- **置信度**：高。

### SEV-05 ｜ 删除房间在 CRLF 配置上永久静默失效，却回报 `{"ok": true}`（Windows 主平台必然发生）

- **位置**：`src/config_io.py:197-214`（比较侧）、`src/web_api.py:480-486`（调用侧，返回值被丢弃）
- **原文**：
```python
            # MI-11：补 newline=""…否则 del_line == txt_line 会与（CRLF 结尾）字符串失配
            with open(file_path, "r", encoding=main.text_encoding, newline="") as f:
                lines = f.readlines()
            ...
            if del_line == txt_line and (delete_all or not deleted_one):
            ...
        if not deleted_one:
            return
```
```python
                    _main.delete_line(cast(str, app.state.url_config_file), cast(str, r["raw_line"]))
                    return {"ok": True}
```
- **详细说明与影响**：两个调用方传入的行都经 universal newlines 归一为 `\n` 结尾——`web_api.py:484` 直接用 `parse_url_config()` 的 `raw_line`（`web_config.py:100` 打开时未带 `newline=""`），`main.py:4258/4321` 的 `origin_line` 同理；而 `delete_line` 按 MI-11 改用 `newline=""` 读原文，文件行是 `...\r\n`，整行精确比较**恒不成立**。A/B 实测（内容相同、仅行尾不同）：

  | 文件行尾 | 删除后目标行是否仍在 |
  |---|---|
  | CRLF（工作区实际形态：`URL_config.ini` 14/14、`config.ini` 150/150 行均为 CRLF） | **仍在（删除失败）** |
  | LF | 已删除 |

  后果：① 面板点「删除」提示成功、列表刷新后房间仍在并继续录制、继续占盘与并发槽；② 录制主循环的重复行清理退化为永久 no-op（重复 URL 每轮重复起线程）；③ `delete_line` 无返回值、调用方无条件 `return {"ok": True}`，故障完全不可观测。`grep delete_line tests/*.py` **零命中**（无回归锁），且 CI 在 Linux 跑、天然 LF，门禁结构上不可能发现。注意 `main()` 启动时 `remove_duplicate_lines` 会把文件重写为 LF，故故障呈「首次启动前、或配置被记事本/编辑器改回 CRLF 后必现」的间歇形态，极易被误判为偶发。
- **改进建议**：`delete_line` 内做行尾归一匹配（两侧 `rstrip("\r\n")` 后比较）并返回 bool；`delete_room`/`update_room`/`toggle` 以真实返回值决定 200/500，成功前重新 `parse_url_config` 复核目标 URL 已不在列表中；补 CRLF 用例（`newline=""` 写 `\r\n` 文件 + 传 `\n` 行）。
- **置信度**：高（A/B 实测复现）。

### SEV-06 ｜ Shopee 站点后缀解析错误，拼出非法域名 → 该平台所有分享链接永久解析失败

- **位置**：`src/spider.py:106-112`（消费点 `:4858`）
- **原文**：
```python
def _shopee_host_suffix(url: str) -> str:
    host = url.split("/")[2]
    parts = host.split(".", maxsplit=1)
    return parts[-1] if len(parts) > 1 and parts[-1] else "com"
```
- **详细说明与影响**：函数意图（见其注释与自身写死的 Referer 形态）是「去掉 `live.` 首段后取完整 TLD」，但 `split(".", maxsplit=1)[-1]` 只切掉第一个点前的内容。以真实函数实跑：

  | 用户粘贴的 URL | 返回值 | 拼出的 api_host |
  |---|---|---|
  | `https://live.shopee.sg/share?from=live&session=******` | `shopee.sg` | `https://live.shopee.**shopee.sg**` |
  | `https://live.shopee.co.id/live/123` | `shopee.co.id` | `https://live.shopee.**shopee.co.id**` |
  | `https://live.shopee.com.my/foo` | `shopee.com.my` | `https://live.shopee.**shopee.com.my**` |
  | `https://shopee.co.id/live`（无 `live.` 前缀，**不被路由**） | `co.id` | 正确 |

  而准入与分派键恰为 `live.shopee`（`main.py:2573` `_match_host("live.shopee", "shp.ee/")`；`PLATFORM_HOST` 第 590/613 行为 `live.shopee.`），即**唯一可达的输入形态全部命中错误分支**。结果：请求不存在的 host → `async_req` 返回 `""` → `json.loads("")` 抛错 → `@trace_error_decorator` 兜成 `{"is_live": False}`，表现为「Shopee 永远未开播」，日志无有效线索。附带：`src/spider.py:4848-4856` 的 `if "live.shopee" in url: … else: …` 两分支已完全相同（MI-16 统一后遗留空壳）；现有用例 `tests/test_spider_fixes.py:186` 用的是不被路由的形态，故回归网漏过。
- **改进建议**：`host = re.sub(r"^live\.", "", host)` 后再 `split(".", 1)[-1]`（`live.shopee.co.id → co.id`、`live.shopee.sg → sg`）；补两条真实形态单测；合并退化的 if/else。
- **置信度**：高（函数实跑 + 路由键回源）。

### SEV-07 ｜ 两个登录函数的兜底装饰器与返回契约错配，故障伪装为「未开播」且用户可动作的提示被吞

- **位置**：`src/spider.py:3024`（`login_popkontv`，调用点 `:3248`）、`src/spider.py:3292`（`login_twitcasting`，调用点 `:3400/3419`）
- **原文**：
```python
@trace_error_decorator
async def login_popkontv(...) -> tuple[str, str]:
...
@trace_error_decorator
async def login_twitcasting(...) -> OptionalStr:
```
- **详细说明与影响**：`trace_error_decorator` 失败时返回 `{"is_live": False}`（`src/utils.py:276`），只适用于**返回 dict** 的平台函数；本仓已按 CR-12 把二元组的 `get_popkontv_stream_data`、三元组的 `get_acfun_sign_params` 改为 `trace_error_decorator_or_none`，同族 `login_sooplive:2064`/`login_flextv:2723` 也已是 `_or_none` 写法——**唯独这两个 `login_*` 漏改**。
  - PopkonTV：`new_access_token, new_partner_code = await login_popkontv(...)` 解包 dict → `ValueError: not enough values to unpack (expected 2, got 1)` → 被上层装饰器二次吞掉；函数内 `raise Exception("popkontv login failed, please reconfigure the correct account…")` 的三条路径（E4010 / HTTPStatusError / 网络异常）全部转 dict，**「账号密码错误」这一用户可自助修复的提示彻底丢失**。
  - TwitCasting：`cs_session_id` 抠取与首次抓页都在内层 try 之外，抛错即被转成 dict；调用方判空写的是 `if not new_cookie: raise RuntimeError("TwitCasting login failed…")`——**dict 恒为真**，于是执行 `headers["Cookie"] = new_cookie`（`:3413`），把 dict 当 Cookie 头交给 httpx → TypeError → 又被外层装饰器吞 → 需登录房间在风控/改版时表现为静默「未开播」。
- **改进建议**：两处改 `@trace_error_decorator_or_none`；调用点显式判空后再解包/赋值，写 Cookie 前 `isinstance(new_cookie, str)` 断言；把「返回注解 ↔ 装饰器」配对校验做成 AST 回归锁（CR-12 建议 ④ 至今未落地，见 MID-68）。
- **置信度**：高。

### SEV-08 ｜ 录制看门狗「停滞」判据基准用错：容忍窗口实际只有 30 秒，可自愈的瞬时断流被判死

- **位置**：`main.py:983-1003`（判据）、`main.py:751-755`（阈值与注释）
- **原文**：
```python
        _stall_last_probe = time.time()
        _stall_last_size = -1
            ...
            if size > _stall_last_size:
                _stall_last_size = size
                return False
            if _stall_last_size >= 0 and now - _proc_started_at > _RECORD_STALL_SECONDS:
                logger.warning(i18n.tr("[{record_name}] 输出文件连续 {minutes} 分钟无增长，判定为停滞并终止", ...))
                return True
```
- **详细说明与影响**：`_stall_last_size` 只在**观测到增长时**更新，而判据是 `now - _proc_started_at > 600`——用的是**进程起跑时刻**，不是「最后一次增长时刻」；采样间隔 `_RECORD_STALL_PROBE_INTERVAL = 30.0`。于是非分段录制满 10 分钟后，**任意一次相邻 30s 采样之间字节数不变即立刻杀进程**，与日志宣称的「连续 10 分钟无增长」及 `:751` 注释「远长于任何正常直播时长，避免误杀」都不符。
  合法无增长窗口在本仓真实存在：FLV 输入刻意保留 `-reconnect*`（`-reconnect_delay_max 60` 允许最长 60s 指数退避重连，1/3/7/15/31s），期间**一个字节都不写**；主播暂停推流、CDN 短抖同理。误杀代价链：`main.py:1007-1016` 走 `record_error(host_of(record_url))` → 健康线路被计入按 host 的熔断失败样本（window=40 / fail_rate=0.5，多房间同 host 足以触发熔断）→ 且不走 `rc==0` 分支，TS 的 `converts_to_mp4` 与 `clear_ffmpeg_reject` 双双跳过。分段模式下 `getsize` 恒 OSError → 停滞判据整体不生效，只剩 6h 总时长上限（MID-07），两形态行为互不一致。
- **改进建议**：维护 `_stall_since`（每次观测到增长即刷新），判据改 `now - _stall_since > _RECORD_STALL_SECONDS`；`_stall_last_size < 0` 时以 `_proc_started_at` 初始化；补「写入空档 45s 不得被杀、空档 11min 必须被杀」双用例（`tests/` 当前对 `_RECORD_STALL_SECONDS`/`_MAX_RECORD_SECONDS`/`_watchdog_hit` **零引用**）。
- **置信度**：高。

### SEV-09 ｜ `only_flv` 分支缺 `flv_url` 时未清理录制状态：时间字幕线程进入永久死循环写盘

- **位置**：`main.py:3414-3431`（无条件登记）、`:3534-3553`（先启字幕线程）、`:3596-3616`（未命中分支只 debug）
- **原文**：
```python
                                if create_time_file:
                                    def _subtitle_thread_target_direct() -> None:
                                        try:
                                            generate_subtitles(record_name, subs_file_path)
                                        finally:
                                            ...
                                    create_var[subs_thread_name].start()      # 先启动
                                try:
                                    flv_url = port_info.get("flv_url")
                                    if isinstance(flv_url, str) and flv_url:
                                        ...
                                    else:
                                        logger.debug("未找到FLV直播流，跳过录制")   # 不清理
```
- **详细说明与影响**：`recording.add(record_name)`（`:3414`）与 `recording_time_list[record_name]`（`:3428`）在分支判定之前无条件执行；`else` 分支（shopee/花椒只回了 m3u8、或接口未下发 `flv_url`）既不调 `clear_record_info` 也不 `discard`。而 `src/video_postprocess.py::generate_subtitles` 是 `while True` + 每秒 `open(..., "a")` 追加一条 SRT，**唯一退出条件是 `record_name not in main.recording`**。
  触发路径：勾选「生成时间字幕文件」（本机 `config.ini` 即为「是」）+ 录制 shopee/花椒 + 该轮未返回 `flv_url`（游客态、下播瞬间、接口结构变更）→ 字幕线程每秒写一行、永不停止，房间线程每轮（默认 120s）再启一个 → 线程数与 `.srt` 无界增长；同时 `recording` 幽灵条目造成 MID-01 列出的三类后果。
- **改进建议**：`recording.add` 下移到确认存在可录流之后；至少在 `else` 分支调 `clear_record_info(record_name, record_url)`；并把字幕线程启动挪到 `flv_url` 校验通过之后，与 ffmpeg 路径「先起 ffmpeg 再起字幕」的顺序对齐。补用例：无 `flv_url` 时 `recording` 为空且**无存活字幕线程**。
- **置信度**：高。

### SEV-10 ｜ 发布链路的运行时二进制哈希钉定表为空，未校验的第三方二进制默认进入分发产物

- **位置**：`build_exe.py:219`（空表）、`build_exe.py:262-268`（未钉定仅告警并继续）
- **原文**：
```python
_PINNED_RUNTIME_SHA256: dict[str, str] = {}
...
        expected = _pinned_hashes().get(dest.name, "")
        if expected:
            if expected != actual:
                raise SystemExit(...)
        else:
            print(f"[build][warn] {desc} 未钉定 SHA256，请核对官方值后加入 _PINNED_RUNTIME_SHA256：{actual}")
```
- **详细说明与影响**：CR-11 把「下载 → 解压 → 打进发布包无校验」列为供应链风险并加了校验框架，但默认表为空、`DLR_RUNTIME_SHA256` 未设时**打 warn 后继续**。`.github/workflows/build-release.yml` 以 `--dual` 从 nodejs.org / gyan.dev / johnvansickle.com 拉取的 ffmpeg + node（约 300MB）经此路径直接进入对外分发的 full zip：构建机或上游 CDN 被污染即随发布包扩散到终端用户机器，而这些二进制以子进程方式执行。运行时侧（`src/ffmpeg_install.py`、`node_install.py`）亦为自写 ToFU 基线（MID-58）。本项即上一轮 CR-11「部分修复」的残留，本轮确认其**默认 fail-open** 语义未变。
- **改进建议**：发布路径改为 **fail-closed**——`build_exe.py` 增 `--require-pinned`（CI 默认开启），缺钉定即 `SystemExit`；在 build-release.yml 的 prepare 步骤注入 `DLR_RUNTIME_SHA256` 并按平台分列；把钉定值纳入版本同步校验范围。
- **置信度**：高（危害前提为构建机/CDN 被污染，属纵深防御）。

---
## 四、中等问题（P1，69 项）

> 每项给出位置、影响与建议。标「实测」者为本轮以真实函数或对照实验复现；其余为回源核对可达性。

### 4.1 录制主链路与产物判定（`main.py`）— MID-01 … MID-12

- **MID-01 等待录制槽的放弃分支不清理录制状态**（`main.py:877-886`）。`return True` 前无 `clear_record_info`/`recording.discard`，而登记早在 `:3414` 完成；对照同函数 `:1017-1019` 的「被注释/停止」分支显式清理，可判定为遗漏而非设计。后果：面板与 CLI 永久显示幻影「录制中」；`main.py:4222` 磁盘满退出判定 `if not recording:` 恒假 → 已置 `exit_recording` 却永不 `sys.exit`、主循环空转；`:3236` 的「等待直播…」提示永久消失；调用方把 `True` 一律解读为「录制中断」，TS 分支因此对从未创建的输出路径提交一次注定失败的转码。**建议**：与 `:1017` 分支同构补齐，或让 `_run_ffmpeg_record` 区分「未启动即放弃」与「录制中中断」两种返回语义。**置信度：高**。
- **MID-02 输出目录创建失败后仍启动 ffmpeg，本地 IO 错误被归因成 CDN 快速失败**（`main.py:3362-3368`）。`os.makedirs` 抛错仅 `logger.error`、无 `continue`/`return`，录制链继续 `Popen`；ffmpeg 打不开输出即秒退（`rc != 0`）→ 落入 `:1154` 的 `_FFMPEG_FAST_FAIL_SECONDS(20)` 判定 → `mark_ffmpeg_reject(健康流地址)` + `record_error(record_host)` → 好线路进退避、按 host 熔断计数被污染，每轮重复，用户只看到「网络异常」类日志。**建议**：目录失败直接 `continue`；并把「输出侧启动失败」从快速失败归因中剥离（按退出码/stderr 特征区分）。**置信度：高**。
- **MID-03 `http_record_list` 写 `"migu"`，与 resolver 回写的 `platform = "咪咕直播"` 不匹配**（`main.py:3383` vs `:2421`，实测 grep）。列表第二项为死项，咪咕「强制走 http 拉流」的既有语义失效；同文件 `only_flv_platform_list = ["shopee", "花椒直播"]`（`:3456`）用全名，证明此处是字符串写错。**建议**：改 `"咪咕直播"`，并加断言型用例把「平台名字面量」与 `_PLATFORM_RESOLVERS` 回写的 `platform` 交叉校验，防止再次漂移。**置信度：高**。
- **MID-04 `PLATFORM_HOST` 两项无对应 resolver，`_resolve_unrecognized` 的「不可达分支」注释被证伪**（`main.py:528` `www.redelight.cn`、`:567` `huodong.m.taobao.com`、`:2514-2523`、`:2596` 注释）。准入按 `url_host in PLATFORM_HOST` **精确 host** 匹配（`:4333`），分派表按**子串**匹配（`_match_host("tb.cn","tbzb.taobao.com")`），两项无任何表项命中。用户按 README/面板配置这两类地址时，房间线程每轮走 `_resolve_unrecognized` → 一条 error → `sleep(max(30, delay_default))` → 无限空转：永不录制、永不注释、且不记 `record_error`（熔断/背压统计完全看不到它），白占监控位并持续污染日志。**建议**：补表项或从白名单摘除，并把「`PLATFORM_HOST` 每项必被某匹配片段命中」写成回归用例（归属 `tests/test_platform_dispatch.py`）。**置信度：高（实测 grep）**。
- **MID-05 `_record_output_bytes` 分段分支硬编码 `.ts`，非 TS 分段的零字节判据静默失效**（`main.py:836-847`，实测核对）。`seg_dir.glob(f"{base_stem}_???.ts")` 对分段 FLV/MKV/MP4/音频恒不命中 → 返回 `-1` → `:1079` 的 `0 <= _produced_bytes < _MIN_VALID_RECORD_BYTES` 不成立 → CR-06 修复的「零字节不得记成功、不得撤销线路退避」闭环在所有非 TS 分段形态上原样缺失，而 FLV 分段恰是虎牙/斗鱼的常见形态。另 `???` 只匹配 3 位，序号超 999 段被漏计（同文件 `:3046` 已有 `_\d+\.` 正则可复用）。**建议**：由 `save_file_path` 推导实际扩展名并复用该正则，或让函数接收 `extension` 形参。**置信度：高**。
- **MID-06 直下路径「HTTP 200 + 空响应体」判成功并删除产物**（`main.py:694-712`）。`_downloaded == 0` 时 `finally` 删掉 0 字节文件，但函数仍走成功分支返回 `True` → 调用方打印「直播录制完成」、置 `record_finished=True` 并 `record_success(record_host)`。这正是 CR-06 在 ffmpeg 路径专门修掉的形态，在直下路径（shopee/花椒）仍存，且坏线路不记任何失败样本。**建议**：成功分支加 `_downloaded >= _MIN_VALID_RECORD_BYTES` 判定，不足返回 False 并由调用方走 `record_error`，与 `:1078` 口径统一。**置信度：高**。
- **MID-07 6 小时总时长上限把正常长直播判为挂起：伪失败样本 + 跳过 mp4 转码 + 不清退避**（`main.py:752`、`:974-1016`，实测核对）。24 小时轮播/官方电台类房间（B站/斗鱼/抖音的 CCTV 型直播间）在本工具典型使用场景内，超过 6h 是常态而非异常；默认分段关闭时单文件长录是用户显式选择。该上限每 6 小时制造：① `record_error(host)`——健康线路的失败样本，多房间同 host 时直接把 `PlatformBreaker`（window=40 / fail_rate=0.5）推向 open；② 绕过 `:1089` 的 `converts_to_mp4 and save_type == "TS"` 转码分支（FLV 分支 `:3658` 会转，两保存类型口径不一致），用户「录后转 mp4」设置对这类录像静默不执行；③ 绕过 `clear_ffmpeg_reject`，此前记入的退避无法被这次成功录制撤销。日志文案「判定为挂起」还会把排查方向引向并不存在的挂起。**建议**：总时长上限改为可配置（或分段关闭时不生效）；该分支收尾与 `rc==0` 路径共用（补转码 + 记成功样本）；文案改为「达到单次录制时长上限，分段续录」。**置信度：高**。
- **MID-08 `check_subprocess` 读运行期热更新的全局 `split_video_by_time` 决定产物校验与转码策略**（`main.py:1078/1089`、`:926`、`:3696`）。`ffmpeg_command` 是录制开始时按当时取值拼死的（builder 收形参，正确），但收尾读的是**模块全局**，而主循环每 3s 热加载 config（`:4079`）。录制中途在面板/编辑器切换「分段录制是否开启」：关→开时按分段模式 glob → 恒返回 -1 → 零字节保护静默失效；开→关时对含 `%03d` 的字面路径提交转码（必然失败），反向情形则对目录中 `base_stem_???.ts` 历史残留批量转码。`:926` 的 `danmaku_split_time` 同理会破坏 `_000.srt ↔ _000.ts` 对应不变量（AGENTS 分段命名约定）。**建议**：把该值作为 `check_subprocess` 显式形参，或就地由 `"%d" in save_file_path` 推导，使其与命令模板天然一致。**置信度：中**（机制确定，需热更新窗口）。
- **MID-09 `config.read()` 是合并语义，被删除的键在内存里永久保留旧值**（`main.py:3998`，实测 grep：全仓无 `config.clear()`）。`RawConfigParser.read()` 不清空既有 section/option，故每轮「热加载」实为增量合并。用户手删某键（`HLS采集排除平台`、某个 cookie 等）后内存旧值继续生效，`read_config_value` 的缺键补写自愈永不触发（`has_option` 恒真）；`:3918` 的旧键兼容分支因 `has_option` 恒真而永久重复打印迁移提示。**建议**：每轮 `config.clear()` 后再 read，或 read 到新解析器后原子替换。**置信度：高**。
- **MID-10 「禁用SSL证书验证的平台」仅在模块 import 期生效，主循环热更新遗漏**（`main.py:3914-3922` vs `:4080`）。热加载重读了 `enable_https_recording` 并调 `set_https_recording`，却从不重跑 `_sync_ssl_disable_platforms` / `set_platform_ssl_verify`。运行期增删豁免平台必须重启进程，而相邻的 HLS 开关、https 开关都热生效，用户无从区分；录制启动后新出现证书异常的平台也不会被自动追加（而该「启动时自动追加」正是本仓第 8 条既定行为，实际只覆盖进程首启）。**建议**：在主循环按「配置值变化时」重跑（幂等、只追加不移除）。**置信度：高**。
- **MID-11 `split_time` 未做数值归一，脏配置直接进 ffmpeg 命令行**（`main.py:4086`）。相邻的时间类配置都做了归一（`:4058/4067/4068` 用 `_safe_int`，`:4101` 弹幕分片用 `_safe_float`），唯独此项只 `str()`。用户写成空值（面板清空输入框即可产出）或非数字 → 命令里出现 `-segment_time ""` / `-segment_time abc`，ffmpeg 以 -22 退出；因该错误在进程启动阶段秒退，还会被 `:1154` 判成「CDN 快速失败」并给好线路记探针退避（与 MID-02 同类归因错误）。**建议**：`split_time = str(_safe_int(read_config_value(...), 1800))`。**置信度：高**。
- **MID-12 `check_subprocess` 缺「非预期异常 → 统一回收」出口：孤儿 ffmpeg + 同目录双路录制 + 注册表泄漏**（`main.py:887-1040`、`:3011`、`:3705`）。`try` 的 `finally` 只归还信号量，不 terminate/unregister、不 `clear_record_info`。`Popen` 成功后仍存在未被包装的抛错点——最现实的是 `:954-957` 的 `Thread.start()`（80+ 房间 × 各自弹幕/asyncio 线程环境下 `RuntimeError: can't start new thread` 可达）。异常穿透 `check_subprocess` → `_run_ffmpeg_record` 只 `except OSError` → 落到 `start_record` 内层 `except Exception`：记日志、`record_error`、睡一轮后**再次起录**。此时上一路 ffmpeg 仍在拉流写盘且无人守护（不进 `while process.poll() is None`，用户点停止/注释都杀不到它；进程注册表也永不注销），随后又拉起第二路写同一目录。**建议**：`check_subprocess` 加 `except BaseException`，或在 `finally` 内判「进程已建且 `poll() is None` → terminate + unregister + `clear_record_info`」，使异常路径与早退路径同样收敛子进程与录制状态。**置信度：中**。

### 4.2 选源与流地址层（`src/stream_select.py`、`src/stream.py`）— MID-13 … MID-20

- **MID-13 虎牙旧档位按 exsphd 出现顺序「位置式」贴标签，请求超清可实拉蓝光8M**（`src/stream.py:733-741`，实测核对）。`labels = ["UHD","HD","SD","LD"]` 与 `re.findall(r"(?<=264_)\d+", quality_list[1])[::-1]` 做 `zip`，完全不看数值语义；而同文件 `HUYA_FIXED_TIERS`/`HUYA_RATIO_TO_CODE`（BD 分支所用）明确 `8000=蓝光8M`、`2000=超清`、`500=流畅`。BD 分支把 exsphd 当**集合**、本分支当**有序序列**，同一字符串两种互斥解释。以现有用例的升序输入推演即得 `UHD→8000`；若线上 exsphd 为降序则方向整体反转。且 `actual_quality` 被回写成请求值 → `is_downgrade` 恒 False → 面板与日志均无告警，产物码率长期与用户设置不符。现有用例 `test_legacy_uhd_via_exsphd_labels` 恰好固化了错误语义。**建议**：废掉位置式 zip，改为「ratio 数值 → 档位」表驱动（复用 `HUYA_RATIO_TO_CODE`，必要时补 1000/250），无可解释 ratio 时按 BD 分支口径不附加 ratio 走原画并告警；同步修正该用例断言。**置信度：高**。
- **MID-14 虎牙降级后 ratio→档位回采未命中时静默回落请求档，把「降级」伪装成「按请求录」**（`src/stream.py:700`）。`HUYA_RATIO_TO_CODE` 仅登记 6 个 ratio，而 `available_ratios` 直接取 exsphd 全量（可能是 12000/6000/1000/250 等表外值）；`chosen` 落在表外时 `actual_quality` 回落**请求档**，URL 却挂着明显更低的 ratio → `is_downgrade` 恒 False，静默画质劣化既无告警也不在面板体现。`else` 分支（无更低档 → 不附加 ratio、`actual_quality="OD"`）是正确的，可作对照。**建议**：未命中时按数值区间就近取档，并把「告警」与「能否回采代码」解耦（`ratio_val != target` 即告警）。**置信度：高**。
- **MID-15 TikTok 把 m3u8 写进 `flv_url` 字段，绕过「HLS 采集排除」语义并造成重复探测**（`src/stream.py:576-583`，实测核对）。`"flv_url": m3u8_url or flv_url` 使 `select_source_url` 的 `hls_candidates` 与 `flv_candidates` 含同一地址（去重只在组内）→ ① 同一轮被连续校验两次（多烧一次列表 GET + 一次分片 Range-GET）；② 第二次以 `is_hls=False` 身份参与序列，打出假的「HLS 校验失败，回退 FLV」并把 HLS 源记成 `FLV 源`（正是 `_log_source_choice` 声称要消除的观测歧义）；③ 最关键：`hls_effective_enabled` 为 False（全局关闭或命中「HLS采集排除平台」）时 HLS 组被整组剔除，但该 m3u8 仍留在 FLV 组被探测、选用，与该配置项「HLS 探针一次都不发」的硬语义直接冲突（2026-09-05 定稿条目）。**建议**：`"flv_url": flv_url`；「无 FLV 时以 HLS 顶上」交由 `record_url` 通道承担，不要在字段语义上撒谎。**置信度：高**。
- **MID-16 TikTok 仅有 HLS 源时 `flv_dict` 为 `None`，`AttributeError` 被装饰器伪装成「未开播」**（`src/stream.py:546/554/569`）。`_pad_list([])` 返回 `[None]*6`（新列表、非空即真），`if flv_url_list else {"url": ""}` 的兜底进不去 → `flv_dict = None` → `.get("url")` 抛错。`:538` 只挡了「flv 与 m3u8 同时为空」，故「flv 空、hls 有值」可直达此处（`get_video_quality_url` 只在 `vbitrate != 0 and resolution` 时追加元素，TikTok 只下发 hls 路即返回 `[]`）。日志只有一行函数名+行号，与真因无关联。同函数 `:572/573` 都写了判空，反证这两行是漏写。**建议**：先过滤 None 再索引，或统一 `flv_url_list[i] or {"url": ""}`。**置信度：高**。
- **MID-17 探针「401/403 记退避 → 重试成功判定可用」的路径不撤销退避**（`src/stream_select.py:579`、`:637-641`、`:467`）。`_mark_probe_reject` 一见 401/403 即无条件记入，而该函数下方正是本仓刻意保留的「偶发 403 先重试一次再定罪」语义；重试通过后函数返回 True 并选用该源，**退避条目不清**。唯一撤销通道是 `main.py:1132` 的 `clear_ffmpeg_reject`，条件为「ffmpeg 退出码 0 且产物达标」，于是「本轮选上了但录制没走到 rc==0」的常见情形（主播中途下线、被注释/停止提前 return、rc==0 但产物过小）都会把退避留满窗口（默认 `120 + 70 = 190s`）。窗口内该 host 候选被零探针跳过 → 非末位直接回退，斗鱼即退回游客态 FLV（约 70s 被 CDN 掐断），正是 AGENTS 标注绝不可回归的形态。**建议**：把「判定可用即撤销」补进 `_validate_stream_url` 的三条 True 返回路径，或改为「首次记时间戳、重试通过即撤销」的单点实现。**置信度：中**。
- **MID-18 `record_url` 通道绕过「HLS 候选整组剔除」，并与序列重复探测同一地址**（`src/stream_select.py:874/915-918/962-975`，实测核对 gating 逻辑）。(a) 抖音（`stream.py:473`）、TikTok（`:584`）、网易CC（`:1008`）的 `record_url` 本身就是 m3u8；当平台命中「HLS采集排除平台」或全局关闭 HLS 且 FLV 存在（`has_fallback=True`）时，`hls_seq` 被整组剔除、FLV 校验失败（或 FLV 为 h265 被剔除）后落到 `record_url`，仍会对 `.m3u8` 照发 HEAD/Range-GET/分片探测，且 `last_resort=True` 拒绝也放行——与「整组剔除、HLS 探针一次都不发」的定稿语义矛盾，也与 `_is_h265(record_url)` 只告警不拦截后的「切 HLS」语义相悖。(b) 虎牙（`stream.py:804`）与斗鱼的 `record_url` 与序列内候选逐字相同，首探失败原因非 401/403 时同一地址在选源结束前被完整再探一次，正面消耗该 CDN 连接预算——正是退避机制要消除的行为。现有 5 个「排除列」用例全部写 `"record_url": ""`，**结构上发现不了 (a)**。**建议**：`record_url` 分支同受 `hls_effective_enabled` 约束；进分支前复用已探结论；补「`record_url` 为 m3u8 时 HLS 探针零发出」断言。**置信度：高**。
- **MID-19 末位候选「异常也放行」不校验 URL 形态，畸形/非 http 值直达 ffmpeg `-i`**（`src/stream_select.py:722`）。`last_resort` 的放行语义只针对「网络/CDN 拒绝」，但它对**任何**异常成立，包括 `UnsupportedProtocol`（非 http/https）、`InvalidURL`（含空格/控制字符）、`MissingSchema`（平台 JSON 给出 `/path/x.m3u8` 这类相对路径）。实测核对 `select_source_url` 与 `_as_str_list` 仅判 `isinstance(str) and bool(...)`，无任何 scheme/绝对 URL 校验；`main.py::_build_ffmpeg_input_args` 按 `-i` 锚点插入原值。于是一条远端可控（平台接口被劫持/MITM）的 `file:///…`、`concat:…` 或以 `-` 开头的串会被当作「探针异常但末位可用」交给 ffmpeg：前者把本地文件读进录制产物（信息泄露），后者是 ffmpeg 选项注入（argv 列表形式无 shell 注入，但 ffmpeg 自身选项仍有写文件/改协议能力）。注意 `rtmp://` 是合法用例（斗鱼 rtmp 拼接），故不能简单要求 http(s)。**建议**：`select_source_url` 返回前统一过 `urlsplit` 白名单（`http/https/rtmp/rtmps` + `netloc` 非空 + 不以 `-` 开头），不合规告警丢弃且不参与末位放行。**置信度：中**。
- **MID-20 `get_stream_url` 是本层唯一无兜底装饰器的平台入口，且未传 `extra_key` 时把整份 dict 当流地址返回**（`src/stream.py:1012-1050`，实测核对）。(a) `key` 为 None 时返回整个 `play_url_list[i]` 字典（现有用例已把该行为写成期望值），而 `main.py:1624/1684/1726/1759` 的 `spec=True` 调用恰好不传 `hls_extra_key` → `record_url` 是 dict → `stream_select` 的 `isinstance(str)` 与 `_as_str_list` **静默丢弃**，真实地址若只存在于该 dict 内即表现为「解析成功但无任何流地址」；(b) 实测本文件共 8 处 `@trace_error_decorator`，`:1012` 的 `get_stream_url` 定义行上方**无任何装饰器**：`play_url[key]` 的 KeyError 会穿透到 `main.py` 通用 except 并 `record_error(host)` 计入按 host 的熔断样本——AGENTS 2026-09-19 条目明确指出这与其他平台「安静重试一轮」不等价，严重时会自动注释用户房间。**建议**：`get_url` 按 `url/play_url/m3u8_url/flv_url` 顺序探测取值、取不到返回 `""`；补 `@trace_error_decorator`（返回 dict，契约匹配）；`play_url[key]` 改 `.get(key, "")`。**置信度：中**。

### 4.3 并发、网络、弹幕与资源治理 — MID-21 … MID-32

- **MID-21 `_client_cache` 的键不含事件循环，多房间/逐轮互相逐出存活客户端**（`src/async_http.py:26/42/48-61/91-98`，实测核对）。「复用 Client 以真正发挥 keepalive 作用」的承诺与实现相反：A 房间写入 `(clientA, loopA)`，B 房间（不同循环、同 key）发现 `client_loop is not current_loop` → **把 A 正在使用的条目 pop 掉**并自建，A 下一请求又逐出 B → 每个 HTTP 请求都新建 AsyncClient（重做 TCP+TLS 握手）；被逐出的实例仍持活连接，且按既定策略不创建 `aclose` 协程、也不在进程级 `close_all_clients_sync` 覆盖范围内（已脱离缓存），只能等 socket finalizer。同一房间每轮 `asyncio.run()` 换循环本身也是永久 miss。**建议**：key 增加循环维度（或改用 `contextvars`/挂在 loop 上），只逐出属于自己循环的条目，并按 `loop.is_closed()` 惰性清扫。**注意**：不要退回「跨循环 await aclose」或 `run_coroutine_threadsafe`——2026-09-04 的决策依然成立，本项只修 key。**置信度：高**。
- **MID-22 共享 AsyncClient 的 cookie jar 跨房间/跨账号累积**（`src/async_http.py:83-89`；`return_cookies=True` 调用点 `src/spider.py:2097/2749/3332/5016`、`src/cookie_cache.py:188`）。httpx 明确「使用 Client 时响应 Set-Cookie 会持久化到 Client 并在后续同域请求自动带上」，而该缓存按 `(proxy, verify, http2)` 共享，即全部无代理请求共用一支 jar：A 账号登录得到的 session cookie 会被 B 账号/其它房间的请求自动附带，并与调用方显式传入的 `Cookie` 头并存。这与本仓「客户端跨候选复用时业务头必须逐请求下发，否则互相污染」的既有结论精神冲突，构成登录串号与风控指纹异常。**建议**：登录/取 Cookie 类调用不走缓存客户端；或给 key 增加「允许会话状态 / 无状态」维度。**置信度：中高**。
- **MID-23 `collector.stop()` 在「loop 已发布但尚未 running」的窗口丢停止信号**（`src/collector.py:156-164`、`:200-233`，实测核对反向序握手语义）。本仓刻意的两条相反顺序保证只覆盖「`_loop` 是否已发布」这一维，但 `stop()` 额外要求 `loop.is_running()`：`_run` 在 `:200` 发布 `_loop`、`:207` 读到未置位、继续构造平台客户端（`:220-230`）；此间 `stop()` 置位并读到非 None 的 `_loop`，但 `run_until_complete` 尚未开始 → `is_running()` 为 False → 整段 `call_soon_threadsafe` 被跳过、信号永久丢失 → `join(8)` 超时，采集线程 + 已 close 的 SrtWriter + 监控房间条目（`room_stopped` 要到线程退出才发）全部滞留。窗口仅毫秒级，但「刚开播就秒退/快速失败/立即停止录制」正是最容易命中的路径。**建议**：不动两条相反顺序；在「未 running 且未 closed」时有界等待（≤0.5s 轮询）后再投递，或进入 `run_until_complete` 前追加一次 `_stop_event` 复查（二次检查不破坏原保证）。**置信度：中高**。
- **MID-24 `collector.stop()` 用阻塞 `put` 投 sentinel，慢盘下挂死房间线程并在 try 内路径泄漏录制槽**（`src/collector.py:167-171`，实测核对）。`_srt_queue` 是 `maxsize` 有界队列（`:99`），生产侧 `:314-321` **刻意**用 `put_nowait` + 丢弃计数（注释：阻塞入队会卡住 ws_recv），而 `stop()` 的 `self._srt_queue.put(None)` 无超时无兜底：写线程卡在 `srt.write()` 的阻塞 `flush()`（网络盘掉线/USB 拔除/磁盘满）且队列已满时**无限阻塞**。`SrtWriter.close()` 为此专设 `_CLOSE_LOCK_TIMEOUT`，sentinel 这一步却没有。后果分级（已核对调用点顺序）：`main.py:1009/1023` 两条 try 内路径此时在 `finally: _rec_sem.release()` **之前**卡死 → 录制并发槽泄漏、后续录制饿死（正是 AGENTS 槽位泄漏条目要防的形态）；`:1044` 的收尾路径已释放槽位，但房间线程仍永不返回、`recording` 状态不清。**建议**：`put_nowait` + `queue.Full` 时置停止事件由写线程自检退出（其 `get(timeout=…)` 循环检查该事件），随后仍 `join(timeout=3.0)`；sentinel 失败绝不阻断 `srt.close()`。**置信度：高**。
- **MID-25 弹幕枢纽在全局锁内做磁盘 `write+flush`，把各房间事件循环串到慢盘上**（`src/danmaku_monitor.py:147-175 → 277-292 → 380-398`；调用点 `src/collector.py:295-302`）。`room_message` 跑在**采集线程的事件循环上**，`_emit_message → _write_line` 在全局 `_lock` 内 open/write/flush。采样上限每房间 10 条/秒，80 房间即最高 800 次带 flush 的串行落盘/秒；任一次 flush 被慢盘拖住，所有房间的 ws 收包/心跳协程一起停摆（协议层 ping 超时 → 断连 → 重连风暴），Web 快照 `snapshot()` 也抢同一把锁。这与 collector 侧「SRT 写盘必须挪到独立线程，否则阻塞 ws_recv」的自述理由直接矛盾——弹幕监控走的却是同步落盘。**建议**：锁内只完成统计 + payload 构造，写盘交进程级单写线程队列（与 SRT 同构、有界 + 丢弃计数）；`_stats_loop` 批量写同样入队。**置信度：高**。
- **MID-26 流地址探针走控制面 SSL 策略，与 ffmpeg / `stream_select` 不一致 → 校验假红、画质被误降**（`src/async_http.py:267-268`；调用点 `src/stream.py:445`、`:558`）。两处传的是**流地址**却未传 `verify`，于是落到 `http_config.ssl_verify`（生产恒 True、严格校验）；而同用途的 `stream_select.py:538`、`main.py:665` 用 `get_effective_ssl_verify(platform)`，ffmpeg 的 `-tls_verify` 也按后者。当「是否启用https录制」开启（流侧 `ssl_verify=False`）或平台命中「禁用SSL证书验证的平台」（虎牙 TX CDN 主机名不匹配正是该名单的立论）时，探针必然 SSL 报错 → 判不可达 → `stream.py` 走相邻档降级/放弃，而 ffmpeg 实际能录上原画。这正是 AGENTS 反复警告的「探针与 ffmpeg 客户端指纹必须一致」。**建议**：`get_response_status` 增 `platform` 形参并默认 `verify=get_effective_ssl_verify(platform)`，两处调用点传入 platform。**置信度：高**。
- **MID-27 `sync_req` 不做 `handle_proxy_addr`，裸 `ip:port` 代理配置只对异步侧生效**（`src/sync_http.py:166-182`；对照 `src/async_http.py:193/270`、`src/room.py:87/175/266`、`src/spider.py:3048`、`src/platforms/twitch.py:53/58`，实测 grep）。配置项「代理地址」由 `read_config_value` 原样读入（`main.py:4044`），`handle_proxy_addr` 存在的理由正是兼容用户写 `127.0.0.1:7890`；异步侧全部补了 `http://` 前缀，而同步侧约 125 个调用点把裸值直接交给 requests → `InvalidSchema`/`InvalidURL` 被外层 except 吞成空串，或静默不走代理。表现即「同一平台开代理后 sync 解析全失败、async 正常」，且失败伪装成空响应（本仓列为最难归因的形态）。**建议**：`sync_req` 入口统一归一（与 async 同址同语义）。**置信度：高**。
- **MID-28 `mask_credentials` 存在结构性覆盖缺口，且 `main.py` 全仓 0 处调用**（`src/utils.py:578-593`；缺口点 `main.py:669/697`（直下失败日志打裸流地址）、`main.py:3437-3450`（`PlayURL.log` 源地址）、`src/stream_select.py:379/407/422/958`、`src/weverse_auth.py:60`）。以 9 条样本实跑：URL query 的 `signature=`/`wsSecret=`/`txSecret=` 与 scheme 内 `user:pass@` **能**脱敏；但 `cookie=`、`sid_guard=`、`ttwid=`、`Authorization: Bearer …`、JSON 体 `"access_token": "…"` **全部原样保留**。根因：两条正则都要求字面 `=`，故头形态与 JSON 形态永不匹配；键黑名单缺 `cookie/set-cookie/ttwid/sid_guard/sessionid/verifyfingerprint`；`_PROXY_CREDENTIAL_RE` 依赖 `://`，无 scheme 的 `user:pass@host:port` 不识别。实测各文件调用次数：`stream_select` 21、`async_http` 8、`cookie_cache` 6、`sync_http` 5、`spider` 4、`utils` 1、**`main.py` 0**——带签名参数的真实拉流地址因此明文进 300KB 轮转、保留多份的日志文件。**建议**：① 键黑名单与头/JSON 形态补齐；② `main.py` 的两条路径过码；③ 治本做法是在 `src/logger.py` 注册 loguru `patcher` 对 record 文本统一过一遍，把「逐个调用点记得加」变成结构性保证。**置信度：高（实跑）**。
- **MID-29 `replace_url` / `remove_duplicate_lines` 非原子、未持 `file_update_lock` 重写 `URL_config.ini`**（`src/utils.py:548-560`、`:482-497`；调用点 `src/spider.py:3910`（花椒地址失效自动注释）、`main.py:3979`，实测核对）。H-6/WD-15 已把该文件的读-改-写收敛到 `config_io`（持锁 + 同目录 tmp + `os.replace`），但花椒这条路径走 `utils.replace_url`：既无锁也非原子。与主循环热加载 / Web 原子写并发时：① truncate 窗口内主循环读到空/半写文件 → 房间被误判为「配置里已删除」；② Windows 上目标被 `open("w")` 持句柄会让对端 `os.replace` 抛 PermissionError → 原子写降级为「已保留原文件」，该次注释/画质变更丢失；③ 两写方交错时后写者整体回退先写者改动。另 `remove_duplicate_lines` 的 `UnicodeDecodeError` 回退分支未清空首轮已读的 `unique_lines`，两种解码结果混在同一 OrderedDict，可把误解码出的乱码键写回文件。**建议**：两处改走 `atomic_write_text` 并包 `main.file_update_lock`（或下沉 `config_io`，与 `update_anchor_name` 同型）；回退分支先 `clear()`。**置信度：高**。
- **MID-30 `room_stopped` 位于 `while True` 之内，每轮检测都弹出监控房间并写假 `stopped` 事件**（`main.py:3065`/`:3752-3764`、`src/danmaku_monitor.py:119-138`，实测核对缩进层级）。`finally` 与其 `try` 同为 8 空格缩进、位于 `:3065` 的 `while True:` **体内**，即每轮执行，而注释与 AGENTS 都把它描述为「房间线程退出时移除」的钩子。后果：GUI `_danmaku_dispatch` 收 `state=="stopped"` 即 pop 房间行、Web 快照随房间消失 → 监控页只在「正在录制这段时间」显示房间，轮询间隙行被移除，下轮开播才由 `room_started` 重新注册并**清零统计**；「开播→下播→再开播」每个循环都向 JSONL 边车写一条假「房间已停止监控」。删掉该清理会回归「已失效房间永久残留」，故不能简单移除。**建议**：把该清理移到 `_room_thread_target` 的 finally（该处已在做 `create_var.pop` / `remove_room_from_running`，语义正是线程退出），或把 try 包在整个 `while True` 外层、finally 只挂一次。**置信度：高**。
- **MID-31 `display_info` 异常路径无 sleep：无控制台环境下守护线程 100% CPU 忙等并刷满日志**（`src/recorder_status.py:135-207`，实测核对）。整个循环唯一的 `time.sleep(5)` 位于 `sys.stdout.flush()` **之后**、try 内部，`except Exception` 分支只 `logger.error` 无退避。AGENTS「无控制台环境」条目明确 `pythonw.exe` 与 `console=False` 冻结 exe 下 `sys.stdout is None`，而 `main.py:4470` **无条件**启动该线程 → 每轮 `AttributeError` → 立即重来 → 单核跑满 + `streamget.log` 秒级灌满，并与录制线程抢 GIL。第二形态：Web 后台模式下 `sys.stdout` 指向 `logs/web_console.log`，日志归档改名/关句柄窗口内 `flush()` 抛 `ValueError: I/O operation on closed file`，同样紧循环。**建议**：`sleep` 移到 try 之外（或 `finally`）；开头补 `if sys.stdout is None: time.sleep(5); continue`；except 内按连续失败次数退避。**置信度：高**。
- **MID-32 `cleanup_all_ffmpeg_processes` 的 `f.result(timeout=10)` 是空操作，一个卡死即可永久挂住退出链路**（`src/ffmpeg_proc.py:133-140`，实测核对）。`as_completed(futures)` 未传 `timeout`，它本身无限阻塞直到某 future 完成；能进循环体的 future 必然已完成，故那 10 秒上限永不触发——是死代码。真正的无界点在 worker 内：Windows 分支 `proc.stdin.write(b"q")` / `flush()` 无任何超时（ffmpeg 已卡死且不读 stdin、管道缓冲满时永久阻塞）；三段 `proc.wait(timeout=timeout//3)` 尚可，但 `timeout < 3` 时算出 0，等于跳过优雅退出直接 `terminate()`，MP4 会丢 moov。外层 `with ThreadPoolExecutor` 退出即 `shutdown(wait=True)`，而本函数由 atexit / Web「停止录制」调用 → 进程退出或停止请求永久挂住（`StopRecording.vbs` 在 AGENTS 中被定性为「仅进程卡死时的最后手段」，正是为这类形态准备）。**建议**：改 `concurrent.futures.wait(futures, timeout=总预算)`（或 `as_completed(..., timeout=)`）并把 `TimeoutError` 记为「未确认清理」；stdin 写完立即 close 且不假定回音；按剩余预算收敛三段均分。**置信度：高**。

---
### 4.4 凭据生命周期与 Web 面板安全面 — MID-33 … MID-39

- **MID-33 进程级凭据全局变量无 TTL，`cookie_cache` 的 30 分钟自愈对它们完全失效**（`src/ttwid.py:106`、`src/spider.py:153`、`:190`）。`get_ttwid` / `_ensure_kuaishou_did` / `_ensure_twitch_client_id` 都以「模块全局非空即返回」为第一优先级，而该全局一旦写入**永不清除**；`cookie_cache.DEFAULT_TTL = 30*60`（注释明说为「录制进程可能连续运行数天」的自愈平衡）在这些键上根本不参与判定。ttwid 被抖音作废后（风控常见），进程不重启即再也不重新获取，表现为抖音解析长期「HTTP 200 + 空 body」。`room.py:148-154` 的 `sec_uid→抖音号` 缓存是唯一正确按 TTL 判定的，三者与它不一致。**建议**：去掉这三层模块全局（或写入时刻并读时比对 TTL），让 `singleflight` 成为唯一缓存层；同时提供「凭据被平台拒绝 → 失效」入口（与 `invalidate_bili_buvid_cache` 同形）。**置信度：高**。
- **MID-34 `async def` 端点内的同步磁盘 IO、跨线程锁与日志归档，单个慢请求即停摆整个面板**（`src/web_api.py:333/368/403/408/437/456/481/495/527/539/554/559/607/648-690/707`）。`get_status()` 内部持 `record_state_lock`、`max_request_lock` 并调 `utils.check_disk_capacity → shutil.disk_usage`——录制 UNC/网络盘/可移动盘挂起时该调用可达数十秒，而它被 `async def` 直接调用，期间 `/api/*`（含前端 2s 轮询与 SSE）全无响应；所有房间/配置写接口在事件循环里做整文件 read + `os.replace` 并争夺主循环同样持有的 `file_update_lock`；`toggle_recording(False)` 同步跑 `archive_runtime_logs`（关 loguru 队列 + 四文件改名）；`list_files` 对目录逐项 `realpath`+`os.stat`。这不是「并发慢」而是「串行停摆」。**建议**：上述路径统一 `await asyncio.to_thread(...)`（或改回 `def` 端点交给 FastAPI 线程池）；磁盘容量改带 TTL 的后台缓存；`get_status` 外层加 `asyncio.wait_for`，超时返回陈旧快照并附 `stale:true`。**置信度：高**。
- **MID-35 登录口令校验在事件循环内执行、且限流键可被伪造：面板级 CPU DoS 与不受限在线爆破**（`src/web_config.py:689`、`src/web_api.py:309`、`:98`）。PBKDF2-HMAC-SHA256 200k 迭代（约 150ms CPU/次）连同其前的同步 `read_web_config`、首次登录的 `hash_web_password` + `update_config_line`（持 `file_update_lock` 改盘）全在事件循环线程执行，期间面板其余请求全部排队；`int(iters_s)` 取自配置值、无上界，成本可被进一步放大。限流键 `_get_client_ip` 取 `request.client.host`，而 uvicorn 默认 `proxy_headers=True` 且 `--forwarded-allow-ips` 含 `127.0.0.1`，会在中间件之前就用**请求头里的 XFF 最左值**覆盖 `scope["client"]` → 本机反代（把面板包成 HTTPS 的常见部署）下该值即攻击者可控、且不在 `trusted` 集合内 → 函数原样返回伪造值，`_FAILED_LOGINS` 的 5 次/300s 窗口对每请求换一个键，**在线爆破完全不受限**，审计与封禁同时失效。反向场景：Docker 端口映射把所有连接的 `client.host` 收敛为网关地址，5 次失败即把所有真实用户锁在登录页外（锁定 DoS）。**建议**：口令校验与哈希升级写盘走 `run_in_threadpool`；`iters_s` 设上限（≤1e6）并不低于 `_PBKDF2_ITERATIONS`；限流键改用不受改写影响的连接层地址，仅当直连对端确属 `web_trusted_proxy` 时按可信链从右往左剥 XFF，并叠加与 IP 无关的全局失败预算。**置信度：高（CPU 面）/ 中（XFF 改写属 uvicorn 既有默认，未实跑反代链路）**。
- **MID-36 同源判定基于客户端可控的 `Host` 头，DNS 重绑定可同时穿透 SOP 与 CSRF 校验**（`src/web_api.py:769-776`）。`return origin in (f"http://{host}", f"https://{host}")`，`host` 取自 `Host` 头。攻击者把自身域名 TTL=0 的 A 记录指向 `127.0.0.1`，用户浏览器访问 `http://attacker.tld:8000/` 时 `Origin` 与 `Host` 同为该值 → 判定通过，随后所有写接口（含关闭认证、提交内网房间地址）对攻击者页面完全可用——这正是 SEV-02/03 的无认证投递通道。另：无 `Origin` 一律放行虽避开了 curl 误伤，但也让任何非浏览器路径失去这道判定。**建议**：维护 `allowed_hosts`（回环 + 显式配置值）并在 `web_api`/`web.py` 两侧拒绝其他 `Host`；辅以 `Sec-Fetch-Site: same-origin` 判定；SEV-04 的「非回环必须认证」升级为每请求判定后该面显著收窄。**置信度：中**。
- **MID-37 `saveConfig` 只挡「原样提交 `***`」，不挡「清空后提交」，掩码凭据可被静默覆写为空**（`web/app.js:1167`）。`configBackup` 存的就是 `'***'`，用户全选删除后提交 `''`（≠ `'***'`、≠ `oldVal`）→ `PUT /api/config value=""` → 真实 cookie/token 被空串覆盖，无确认、无回滚提示（`backup_config` 副本默认也已按 CR-07 脱敏）。仅 `web_password` 有服务端守卫（且大小写变体可绕，见 SEV-04）。**建议**：渲染时对掩码字段加 `data-masked="1"`，对 `oldVal === '***'` 的项要求非空或显式「清空确认」；后端对 `is_sensitive_item` 命中的键在 `value.strip()` 为空时返回 400（与 `web_password` 同口径）。**置信度：高**。
- **MID-38 登出入口永久隐藏，服务端 bearer 吊销能力不可达**（`web/index.html:24`、绑定 `web/app.js:1336`，实测 grep）。`#logout-btn` 带 `class="hidden"`（`style.css:107` 为 `display:none!important`），全仓**仅一处 `addEventListener`、无任何代码移除该 class**；`showView`/`showLogin` 也只动视图与其他元素。于是 WD-09 专门补的 `/api/logout`（注释明确「泄露的 token 无法单独吊销，只能改全局密码」）在 UI 上无入口。token 存 sessionStorage 不构成缓解：同标签页内的 XSS、本地进程、共享机器可直接复用，泄露后最长 86400s 全程有效。**建议**：登录成功/`showView` 时 `classList.remove('hidden')`、`showLogin` 加回；为「无登出入口 + 24h 有效期」补一条前端用例锁定（现有 `.mjs` 用例已有 DOM 桩，成本极低）。**置信度：高**。
- **MID-39 内部异常字符串原文回显并直接弹成 toast（绝对路径与 OS 细节，认证关闭时对局域网可见）**（`src/web_api.py:706`，同类 `:340`、`:723`）。日志归档流程会 `logger.remove()` + 改名，Windows 下句柄/共享冲突常见，此时 `str(e)` 形如 `[Errno 13] Permission denied: 'D:\…\logs\streamget.log'`，经 `{"detail": …}` 落到前端 `api()` 的 `throw new Error(text)`（`app.js:165`）→ toast 原样显示整段 JSON 与安装绝对路径（`/api/status`、`/api/danmaku` 的 `error` 字段同理）。**建议**：对外返回固定 error code + 短提示、细节只写日志；前端统一解析 JSON 后取 `detail` 展示，而非把响应体当消息。**置信度：高**。

### 4.5 平台解析与签名层 — MID-40 … MID-50

- **MID-40 B 站兜底 buvid 被 AUTH 拒绝后仍在 30 分钟内反复复用，自愈链断**（`src/spider.py:1651-1656`、`:1816`、`src/cookie_cache.py:357`）。弹幕侧 `_reject_auth()`（`src/platforms/bilibili.py:148`）→ `invalidate_bili_buvid_cache()` 只清模块全局 `_bili_buvid_cached`，**未清承载它的通用缓存**：`_cache_singleflight(key=f"bili_buvid3|{proxy}", cache_falsy=True)` 已把 `(随机UUID, True)` 存进 `_generic_cache`，TTL 30 分钟 → 下一轮见全局为空、走 singleflight → **命中同一份被拒 UUID** → 再次软拒绝，循环到 TTL 自然过期。AGENTS「被拒后下一轮重新获取」与该函数上方注释的承诺均不成立。另外 `singleflight` 缺 `fetch_cookies` 才有的世代比对（`cookie_cache.py:223-226` vs `357-359`），`invalidate_generic()` 全仓零调用点。**建议**：失效函数同时 `invalidate_generic(f"bili_buvid3|{proxy}")`（把 proxy 作形参传入）；给 `singleflight` 补世代比对，与 `fetch_cookies` 对齐。**置信度：高**。
- **MID-41 抖音 APP 路径的 ORIGIN 候选取自 `pull_data` 而非刚解析的候选，原画地址被丢 / codec 标注错位**（`src/spider.py:707` 对照 `:588`）。`json_str` 在 `pull_datas` 非空时取自 `pull_datas[key]["stream_data"]`，但随后 `parsed_data` 只用作 `"origin" in …` 的门禁，真正拼 ORIGIN 的 hls/flv 与 `sdk_params.VCodec` 全部来自**另一个来源** `live_core_sdk_data.pull_data.stream_data`。现代 app 响应只有 `pull_datas` 而无 `pull_data` → `stream_data == ""` → 整段注入被跳过 → 候选里没有 ORIGIN（原画）；两者都存在时又会把 `pull_data` 的 codec 标到 `pull_datas` 的地址上（**codec 标注错位，直接影响 `_is_h265` 判定与 `-c copy` 安全性**）。同文件姊妹实现 `:588-591` 用的是 `parsed_data["origin"]["main"]`，即本处为复制粘贴漂移。**建议**：与 web 实现对齐（`origin_url_list = parsed_data["origin"]["main"]`），删除 `pull_data2` 二次解析。**置信度：中高**。
- **MID-42 花椒 substream 请求 `encode=h265` 却消费 `h264_url`**（`src/spider.py:4048-4060`，函数头注释 `:4009` 自述「取 h264_url」）。请求参数与消费字段的编码器不一致，两种后果都不利：① 服务端按 `encode` 只填匹配字段 → `KeyError` → 装饰器伪装未开播（花椒整平台静默不可录）；② 服务端把 HEVC 地址塞进 `h264_url` 返回 → 地址上**没有 `codec=h265` 标记**，而 `stream_select._is_h265()` 只认该查询参数（AGENTS 硬约定），HEVC 流被当 H.264 直接 `-c copy` 进容器 → 静默损坏产物。**建议**：抓包后二选一（请求 h264 配 `h264_url`，或请求 h265 并消费 `h265_url` 且补 `&codec=h265`）；同时把 `json_data["data"]` 改为判空取值。**置信度：中**（错配本身确定，具体后果取决于服务端实现）。
- **MID-43 淘宝把 `broadCaster` 对象当主播名字符串，下游 `clean_name()` 必抛且误记成功样本**（`src/spider.py:5069`）。mtop `mediaplatform.live.livedetail` 的 `data.broadCaster` 是对象（`accountName`/`nick`/`headPic`…），`cast(str, ...)` 只关掉 mypy 的 `no-any-return`，运行时仍是 dict → `main.py:3161` 的 `anchor_name` → `:3179` `clean_name(anchor_name)` → `stream_select.py:61` 的 `input_text.strip()` 抛 `AttributeError: 'dict' object has no attribute 'strip'`；且 `record_success(record_host)` 在 `clean_name` **之前**已上报（`main.py:3174`），熔断统计把这轮记成成功，故障更难察觉。**建议**：取具体字段（`accountName`/`nick`），非 str 结果回退 `""`；补「`broadCaster` 为 dict 时不得抛错」的回归锁。**置信度：中**。
- **MID-44 `get_winktv_bj_info` 结果未判空即解包，违反本仓 CR-12 约定**（`src/spider.py:2697`）。被调方是 `@trace_error_decorator_or_none`（`:2634`），visitor 接口风控/HTML 拦截页时返回 `None` → 解包 `TypeError` → 被 `get_winktv_stream_data` 自己的装饰器二次吞 → 与「真未开播」不可区分，且 `anchor_name` 永不再上报。同仓 `get_popkontv_stream_data:3189-3192`、`get_acfun_sign_params:4217-4222` 都已按「显式判空后再解包」修过，此处漏改。**建议**：`_bj = await get_winktv_bj_info(...)` → `if not _bj: return {"anchor_name": "", "is_live": False}` 后解包。**置信度：高**。
- **MID-45 正则要求查询参数后必须有 `&`，末位参数形态永久解析失败（MI-17 同类未收口）**（`src/spider.py:3482` 百度 `room_id=(.*?)&`、`:3101` PopkonTV `mcid=(.*?)&`）。`https://live.baidu.com/m/media/pclive/pchome/live.html?room_id=9175031377`、`https://www.popkontv.com/channel/notices?mcid=XXXX` 这类参数位于**串尾**的分享链接（用户手工删参数、平台生成的短分享链）匹配失败 → `ValueError` → 装饰器 → 永久「未开播」。同文件已修的两处用的正是带 `$` 的写法（`:1213` `rid=(.*?)(?=&|$)`、`:3103` `castId=(.*?)(?=&|$)`），MI-17（`:2990` 注释）也已按 `[^&?#]+` 收口过一次。**建议**：两处统一 `(?=&|#|$)` 或字符类终止，或改用 `get_params(url, "room_id")`（`parse_qs` 天然正确处理末位参数）。**置信度：高**。
- **MID-46 TikTok 内置游客 cookie 已过期约 11 个月，默认安装路径无任何指向性提示**（`src/spider.py:777`）。该串第三段 `1761302831` 按 epoch 解为 **2025-10-24**，当前为 2026-09-20；函数注释自述「内置游客 cookie 会随时间失效」，F-10 因此加了 env/config 覆盖入口——但**未配置覆盖的默认路径**（`[Cookie] tiktok_guest_cookie` 为空）拿到的就是过期凭据，解析必拿不到 `SIGI_STATE`，且失败被 `@trace_error_decorator` 伪装成「未开播」，用户不知道该去配什么。**建议**：解析失败且使用的是内置缺省时，明确告警「TikTok 游客 cookie 可能已过期，请配置 `[Cookie] tiktok_guest_cookie`」；或改为经 `cookie_cache.fetch_cookies("https://www.tiktok.com/")` 动态取访客 cookie（与 `ttwid`/快手 `did` 同口径）。**置信度：中**。
- **MID-47 SOOP 全球版把相对清单行拼成缺 `/` 的地址，且该串会顶掉 `record_url`**（`src/spider.py:2272`）。`url_prefix = "/".join(m3u8.split("/")[0:3])`（**无尾斜杠**），而其自身注释明说处理的是「m3u8 内相对路径」行 → 相对行 `1080/index.m3u8` 拼成 `https://global-media.sooplive.com1080/index.m3u8`；若行本身是绝对地址又会被前缀污染。姊妹实现 `:2355` 用的是 `m3u8.rsplit("/", 1)[0] + "/"`，即同文件复制粘贴漂移。消费链：`get_sooplive_stream_data` → `main.py:1624` `stream.get_stream_url(..., spec=True)` → `stream.py:1049-1050` `record_url = play_url_list[档位]`，损坏串直接成为 record_url（`_pad_list` 以末元素补齐，任何档位都命中它）。**建议**：改用 `urljoin(m3u8, line)`（同时正确处理相对/绝对/带参三形态），并与 `:340` 的长度守卫口径统一。**置信度：高**。
- **MID-48 关键平台路径仍用裸 `json.loads` + 深层链式索引，`_loads_dict` 加固未覆盖（系统性）**（`src/spider.py:1229/1238/1284` 等；实测全文件计数：裸 `json.loads(` **84** 处 vs `_loads_dict`/`_safe_loads` 调用 **27** 处）。斗鱼 betard 对不存在/被封房间返回不含 `room` 的 JSON，或对 `m.douyu.com` 返回 WAF 挑战页，`json.loads` 与四级链式索引任一失败都被 `@trace_error_decorator` 收成 `{"is_live": False}` → 表现为「房间不存在」而实际是接口/风控异常，用户侧只见持续「网址内容获取失败」，且日志无区分线索。CR-12 的建议 ①「批量迁移剩余裸 `json.loads`」至今未做。同类：`src/spider.py:1456`（B站旧 `playUrl` 分支裸取 `json_data["code"]`，绕过已建好的「-352 一眼可见」告警路径，且其下两条相邻注释互相矛盾）、`:3705`（Twitch GQL 的 `errors` 非空数组穿过守卫后 KeyError；`_ensure_twitch_client_id` 返回 `""` 时仍照发 `Client-Id: ""`，制造「必然失败但无日志」的组合）。**建议**：统一 `_loads_dict` + `.get()` 链，并在 `room` 缺失时显式告警区分两种成因；迁移可按平台分批，优先高流量国内平台。**置信度：中高**。
- **MID-49 手工拼接请求体/参数，绕过编码层**（`src/spider.py:1272` 斗鱼取流 POST 体）。`enc_data` 原样插入 f-string：值中出现 `&`/`=`/`+`/`%`（base64 序列化后的典型字符）会直接改变表单字段结构、服务端解析到的 `enc_data` 被截断；若接口 `error==0` 但缺 `enc_data`，body 变成字面量 `enc_data=None`，斗鱼返回 error 而非「凭据缺失」，被伪装成「无流」。**建议**：`urllib.parse.urlencode({...})` 或直接给 `async_req(data=dict)`（dict 分支已存在于 `src/async_http.py:205`），`enc_data` 缺失时显式返回 `{}` 走「签名参数缺失」告警。**置信度：中**。
- **MID-50 两处「写死的外部会话/参数」缺覆盖入口或与 UA 自相矛盾**（`src/spider.py:1888`、`:3772` 对照 `:3726`）。小红书 `xy-common-params` 的 `sid=session.17***…` 前 10 位为 epoch（**2024-07-28**，约两年前会话），而本仓对完全同形态的 TikTok 游客 cookie（F-10）与嗨秀 accessToken（CR-12）都补了「env → config.ini → 内置缺省」三级覆盖入口，此处**没有**——一旦 XHS 校验 sid 时效，平台侧坏掉只能等发版改代码。Twitch usher 查询串声明 `browser_version=124.0` 而同一请求 UA 为 `rv:148.0 … Firefox/148.0`，`os_version` 还写成 URL 编码的 `NT%2010.0`（经 urlencode 会二次编码成 `NT%252010.0`）——违反 AGENTS「UA 与派生参数同源、禁止回落 Firefox≤127 等过旧指纹」。**建议**：按 `_read_tiktok_guest_cookie`/`_read_haixiu_token_override` 既有模式为 XHS 加覆盖入口；`browser_version` 与 UA 取同一模块级常量，`os_version` 交 `urlencode` 处理。**置信度：中**。

---
### 4.6 GUI、i18n、推送与安装器 — MID-51 … MID-60

- **MID-51 GUI 以 `utf-8`（非 `utf-8-sig`）读带 BOM 的 `URL_config.ini` → CR-01 的 `input()` 挂死守卫被绕过**（`gui.py:2227`，实测）。全仓所有写入方都用 `utf-8-sig`（`main.text_encoding`、`web_config.TEXT_ENCODING`、`utils.atomic_write_text` 默认值、GUI 自身的 `_save_text_widget_to_file`），故文件必带 BOM，而本行是唯一用裸 `utf-8` 的读取点，首行变成 `'\ufeff# …'`。实测 `'\ufeff#a'.strip().startswith('#')` → **False**：对「所有房间都被注释掉」（暂停录制的常规做法）的配置返回 True。用户点「开始录制」→ 子进程（按 `utf-8-sig` 正确读到空）走 `main.py` 的 `input()` 分支，`CREATE_NEW_CONSOLE` 隐藏控制台、stdin 为 `CONIN$` 且永不关闭 → GUI 侧无输出、无报错、永久静默，**正是 CR-01 注释声称已防住的故障形态**。**建议**：改 `encoding="utf-8-sig"`；并把「行是否有效」的判据抽成与 `web_config.parse_url_config` 共用的实现，消除两处解析口径漂移。**置信度：高（实跑）**。
- **MID-52 `set_language` 绕过 `has_catalog`/`resolve_language`：目录缺失时退化为中文恒等映射，GUI/Web 与录制子进程语言分裂**（`i18n.py:289`；调用点 `gui.py:1194`、`src/web_api.py:634-645`）。`resolve_language`（`:158-170`）规定「无目录 → FALLBACK_LANGUAGE(en_US)」，`main.py:4074` 每轮也按它重解析；但两个直接切换入口只做 `is_recognized_language` + `normalize_language`。触发例：PyYAML 缺失（本仓列为**可选依赖**）时用户选「繁體中文」，或发行包漏装 `en_GB.json`——此时 `_build_translator` 返回 `lambda text: text`（中文原文），`get_language()` 仍回报 `"zh_TW"`，同一份 config.ini 写入 `language = zh_TW` 后**录制子进程落到 en_US**：同一部署两个进程两种语言；且 `set_language` 恒返 True，`gui.py:1200` 据此打印「语言已切换」这一虚假成功。**建议**：`set_language` 内先 `has_catalog` 判定，缺目录按 `resolve_language` 口径回退并返回 False（或返回实际生效语言码），调用方据此提示；GUI/Web 侧统一先 `resolve_language` 再 `set_language`。**置信度：高**。
- **MID-53 GUI 语言下拉把 `English (US)`/`English (UK)` 折成同一显示值 → `en_US` 永远选不到**（`gui.py:1081`、反查 `:1192`，实测复算）。剥括注后得 `{'en_US': 'English', 'en_GB': 'English'}`，反查表因后写覆盖前写得 `{'English': 'en_GB'}`；`values=` 还给 CTkOptionMenu 塞进两个同名项。用户任点一项 English 都写回 `language = en_GB`，en_US 无法从 GUI 选择（Web 面板可以，两端口径也不一致）。**建议**：保留完整显示名或直接以语言码作为菜单值；`_language_names` 改为「码 → 唯一显示名」并加重复即报错的断言，补静态用例。**置信度：高（复算）**。
- **MID-54 画质监控的 `downgraded` 标志只置位不清零，一次瞬时降级把房间永久钉成「⚠ 降级」**（`gui.py:2741`）。`画质降级` 日志（`main.py:3423-3427`）只在每次录制启动时打一条，而 `正在录制中` 行（`src/recorder_status.py:194`）由状态线程周期刷屏；告警一旦入表，后续所有录制行都因 `if not info.get("downgraded")` 跳过更新，`downgraded`/`alert_time`/`actual_quality` 三值再也不会变。用户按提示切到可用档位、下一轮以正确画质录上之后，页面仍显示旧降级时间与旧实际画质——恰是该页唯一的诊断价值。`start_recording` 只在整会话启动时清一次（`:2330`）。**建议**：给降级条目带生效轮次/时间戳，同 name 的录制行 quality 等于设置档且时间戳晚于 `alert_time` 超过一个循环周期时复位；用时间戳先后而非布尔跳过来防误清。**置信度：中高**。
- **MID-55 GUI 高级设置窗口以打开时的整文件快照无条件覆盖 `config.ini`，无 mtime/内容基线校验**（`gui.py:610`、快照点 `:582`；对照 URL 页已有的脏检查 `:3107-3139`）。`AdvancedSettingsWindow.__init__` 取一次 `_load_config()` 快照，`save_config()` 直接整文件写回。窗口长时间打开期间，录制进程可能刚写入 `[Cookie] sooplive_cookie / flextv_cookie / popkontv_token`（`main.py:1617/1756/1811/1850`）、`[录制设置] 禁用ssl证书验证的平台`（`:3902`）或缺键补写（`config_io.read_config_value`）——用户点「保存配置」即把这些凭据/键全部回滚。GUI 与录制是两个进程，`main.file_update_lock` / `web_config._config_write_lock` 只在各自进程内生效，跨进程仅剩「原子替换不会半写」这一条保护，丢失更新无法避免。URL 配置页做了基线校验而 config 页没有，属**同域防护不对称**。**建议**：`save_config` 前重读盘比对快照、不一致弹确认（可复用 `_has_unsaved_config_edits` 机制）；给 `config.ini` 补与 URL 页等价的 mtime 监听。`send_email`/推送类改动亦应走同一入口。**置信度：高**。
- **MID-56 `_wait_and_update_ui` 未用 try/finally 复位 `_stopping` → 「开始录制」永久失效**（`gui.py:2453`、置位点 `:2435`、闸门 `:2241`）。`_stopping` 只有该函数体末尾一处复位，而 `_send_stop_signal_and_wait` 的异常（`_send_ctrl_break_to_child` 内 ctypes 调用、`self._log` 之外的任何意外）会直接逃出 daemon 线程，只留下 `threading.excepthook` 落盘的一行堆栈。此后闸门恒真，用户看到的是「点开始录制只有一句 warn 日志」，且 `_stopping` 无任何 UI 呈现。MI-08 注释本身承认「`_stopping` 复位必须早于会话校验，否则此后开始录制静默失效」，却没把复位放进 finally。**建议**：`try: 收尾主体 finally: self._stopping = False`，或 except 分支复位并 `post_ui` 刷新状态。**置信度：中高**。
- **MID-57 原子写只 `os.replace` 不 fsync：掉电/内核崩溃后 `URL_config.ini` 仍可被替换成 0 字节**（`src/config_io.py:112` → `src/utils.py:413-420`，同类 `src/web_config.py:402`）。WD-15 的立论是「进程被杀/掉电/磁盘满时不再把配置截成空文件」，但 `close()` 只把数据交给内核页缓存，随后 `os.replace` 修改目录项，两者落盘顺序无保证（ext4 ordered-mode 只是常见情况，XFS/NTFS 不保证），可出现「新目录项 + 空/半截数据页」，恰是本次修复要消灭的形态；也没有 `os.sync()`/目录 fsync，rename 自身亦非耐久。**建议**：`f.flush(); os.fsync(f.fileno())` 后再 replace，replace 后对父目录 fsync（Windows 不可得则跳过）。**置信度：中**。
- **MID-58 推送失败日志把自建 Bark 服务器的 device key 原样写进轮转日志**（`msg_push.py:56`，实测核对）。Bark 密钥是路径末段，短于 12 字符时**只能靠 `day.app` 主机名白名单**命中：实测 `https://api.day.app/MyKey124/` → `https://api.day.app/****`，而 `https://bark.example.com/AbCdEfGh` → **原样保留**。自建/反代 Bark 用户一旦推送失败，含明文 key 的地址进 `logs/streamget.log`（300KB 轮转留多份、求助时通常整包上传）；拿到该 key 即可向用户手机无限推送通知。同函数其余渠道（钉钉/Server酱/TG/PushPlus）均已脱敏。**建议**：把「密钥即路径末段」作为通则——对 push/bark 类渠道无条件遮蔽最后一段（或引入渠道枚举），不按主机名白名单；补用例断言 `bark.example.com/<8字符>` 必须被遮蔽。**置信度：高**。
- **MID-59 ffmpeg 官方源 ToFU 旁路文件不随版本轮转 → 上游换构建后自动安装永久死路**（`src/ffmpeg_install.py:69`、`:125`、`:306-315`）。gyan.dev 的 `ffmpeg-release-essentials.zip` 是滚动 URL，构建一变 SHA 即变，而旁路文件（`_ffmpeg_official.zip.sha256`）与 zip 名都固定 → 首次记录后**第二次自动安装必然不等** → `download_ffmpeg_official` 返 False → 转蓝奏云 → 蓝奏云在既无 `FFMPEG_LANZOU_SHA256` 也无 `FFMPEG_LANZOU_ALLOW_UNVERIFIED` 时同样默认拒绝 → 用户只剩「Please manually install ffmpeg」，而排查线索只在 `logger.error` 一行里。模块注释承认 ToFU，但未承认这条**组合死路**。附带：TOFU 基线与 zip 同目录（`execute_dir`），能写该目录者可同时替换产物与旁路文件，校验强度实际等同目录权限。**建议**：旁路文件按构建标识命名（附 Last-Modified/Content-Length 或 gzip 内版本串），或「不一致时降级为 warning + 询问式重记录」；蓝奏云拒绝时明确提示「官方源哈希过期，请删除 <path>」。**置信度：中高**。
- **MID-60 `StopRecording.vbs` 对 pip 启动器形态双向失准，且静默模式判据过松**（`StopRecording.vbs:152`（WMI 映像名枚举）、`:210`（`InStr(1, s, ENTRY_SHIM_KEY)`）、`:51`（`silentMode = Arguments.Count > 0`））。① **漏杀**：`[project.scripts]` 入口实测为 `douyin-recorder.exe`/`-gui.exe`/`-web.exe`（独立映像名，launcher 内嵌解释器、无同名 python.exe 子进程），不在 `Name=` 枚举内 → 录制主进程完全不被匹配；其 ffmpeg 孙进程因 `recorderList.Exists(parentPid)` 为假，只能靠 `IsPathAnchored(exePath)` 命中 → 结果「ffmpeg 被杀、主进程存活并下一轮重新拉起」，正是文件头第 3 点声称已消除的竞态窗口。② **误杀**：`ENTRY_SHIM_KEY` 为裸子串匹配，整条命令行（含解释器路径）出现 `douyin-recorder` 即定罪——venv 目录恰叫该名时，其中任意 python 进程（编辑器 LSP、pytest）都会被 `taskkill /f /t` 整树杀掉；这与同函数 2026-09-12 对 `APP_DIR_KEY` 改用 `ContainsAtWordBoundary` 的严格度自相矛盾，也违反本仓「刻意不按项目目录匹配以免误杀编辑器进程」的既定约定。③ 静默模式不看取值，`cscript //nologo StopRecording.vbs /?` 之类误调用即跳过确认框直接强杀。（注：实测该文件确为 **UTF-16 LE + `FF FE` BOM + 全 CRLF**，与约定一致，编码不是问题。）**建议**：查询串补三个 `douyin-recorder*.exe` 映像名；shim 判定走 `ContainsAtWordBoundary` 且限定为命令行首个 token 的 basename；静默改为遍历比对 `-y` 取值。**置信度：高**。

### 4.7 客户端 JS、门禁、测试可信度与 CI — MID-61 … MID-69

- **MID-61 `migu.js` 在 malloc 前一次性缓存 WASM 内存视图，堆增长即静默产出空签名**（`src/javascript/migu.js:124-125`，写入点 `:161-176`）。Emscripten 约定：`malloc` 触发 `memory.grow` 时 `memory.buffer` 被替换，旧 `Uint8Array/Uint32Array` 视图随即 detach（长度归 0）。脚本在**所有 malloc 之前**捕获 `memory_p/memory_h`，之后 `stringToUTF8`（`:63-66` 写 `memory_p[...]`）与 `UTF8ToString` 全部作用在失效视图上——写是静默 no-op、读返回 0 → `ddCalcu` 成空串（`&ddCalcu=&sv=…`）→ 签名 403。是否触发取决于 mgprtcl.wasm 的 initial<maximum 且本次签名请求是否扩容，本环境无法实测。同类口径：`UTF8ToString`（`:70-78`）实为逐字节 Latin-1 解码，与 `stringToUTF8` 的 UTF-8 编码不对称，仅当产物恒为 ASCII 时安全。**建议**：每次 malloc 后重取视图（或在两函数内即时从 `exports.m.buffer` 构造）；读取改 `TextDecoder('utf-8')` 或注明「输出恒 ASCII」。**置信度：中**。
- **MID-62 远程 WASM 与胶水脚本的完整性信任边界不一致，且哈希校验存在 TOCTOU**（`src/javascript/migu.js:106-120`、`src/utils.py:151-161`）。实际被执行的签名逻辑是每次从 CDN 拉取的 `mgprtcl.wasm`，`playerVersion` 与 URL 都由远程 JSON 决定；`_JS_SHA256_EXPECTED` 只钉住 `migu.js` 胶水层，**钉不住被执行的 wasm**——上游/CDN 被投毒即等价于在签名进程内执行任意 wasm。另一侧 `run_node_script_async` 先 `open().read()` 校验哈希，再 `subprocess.run(["node", script_path])` 让 node **独立二次读取**该文件，check-then-use 非原子（具备写权限者可在两步之间换内容）。**建议**：对 wasm 做版本/哈希钉定（不可行时在注释中明确标注信任边界）；脚本内容一次读入后经 stdin 传给 node。（正面结论：7 个 JS 文件与钉定表 **7/7 匹配**，无 stale。）**置信度：高（代码事实）/ 中（危害前提）**。
- **MID-63 isort 门禁在 GBK 语言环境下静默跳过 16 个自有文件且 rc=0（门禁假绿）**（实测，非代码缺陷）。`python -m isort --check-only --profile black --line-length 120 .` 返回 0，但 stderr 有 16 条 `UserWarning: Unable to parse file <X> due to 'gbk' codec can't encode character`，被跳过者包含 **`main.py`、`gui.py`、`web.py`、`build_exe.py`、`src/spider.py`、`src/stream_select.py`、`src/config_io.py`、`src/notify.py`** 及 5 个测试文件；定位到的抛错点为 `isort/core.py:479` 的 `UnicodeEncodeError`（是 **encode** 而非 decode），同一命令加 `PYTHONUTF8=1` 后**零告警**。影响：Windows 中文环境下本地 isort 门禁对核心源码根本不生效，而 CI 在 Linux 跑 → 呈现「本地过、CI 也过，但两侧都没查」的盲区。**建议**：门禁命令与 CI 统一 `PYTHONUTF8=1`（或 `-X utf8`），并把「isort 有 UserWarning」判为失败（`-W error::UserWarning`）；本条同时说明「只显式传参」不足以保证门禁等价性。**置信度：高（实测）**。
- **MID-64 全量 `pytest` 在本机挂死于前端包装用例，用例内 `timeout=300` 未能兜住**（`tests/test_frontend_quality_ui.py:22-30`，实测）。事实链：① `-q` 全量运行在 ~28% 处连续 15 分钟零输出；② `-v` 定位到 `test_frontend_quality_ui` 后再次停住，累计 >7 分钟**未触发用例内声明的 `timeout=300`**；③ 同一条 `subprocess.run([node, "--test", <file>], capture_output=True, timeout=300, cwd=…)` 在 pytest 之外执行 **0.2s、rc=0**；④ 直接 `node --test tests/frontend/test_quality_ui.mjs` 稳定 **9 passed / 133ms**；⑤ 排除该包装用例后全量 **1041 passed, 2 skipped / 49.82s、0 警告**。结论：包装层在 pytest 捕获环境下不可靠，且 `subprocess.run(timeout=)` 在该形态不构成有效上界（`node --test` 会派生 worker 子进程，超时仅杀直接子进程、随后的收尾 `communicate()` 仍可能被孙进程持有的管道阻塞）。AGENTS 记录的「本机偶发 Segmentation fault（34% 前后）」很可能属同一症状簇的另一种表现。**建议**：包装用例改 `stdin=subprocess.DEVNULL` + `start_new_session=True` + 显式杀进程树；或把前端用例移出 Python 套件、在 CI 作为独立 step 运行（与「Node 缺失时 skip」口径并存）；并为 CI 的 pytest 增加全局 `--timeout` 插件兜底。**置信度：高（实测）**。
- **MID-65 用例使用被明令禁止的宽泛 `filterwarnings("ignore::RuntimeWarning")`**（`tests/test_bilibili_danmaku_info.py:98`，实测 grep 全仓唯一一处）。本仓「pytest 0 警告口径」明文禁止此类过滤、要求修根因（并记录 `test_async_http_lock.py` 曾移除该过滤作回归守卫）；该用例正以 `patch("src.spider.async_req", side_effect=fake_req)`（普通 Mock 返回协程）驱动 async 路径，最易产生 `coroutine was never awaited` 的 RuntimeWarning，而此类告警由 GC 延迟触发、`filterwarnings` 本就拦不住。**建议**：改 `AsyncMock` / `side_effect` 返回 awaitable 并移除 ignore，用回归锁确认根因消除。**置信度：高**。
- **MID-66 用例通过 `main.<stdlib模块>` 就地改写 stdlib / 第三方模块本体，违反仓内测试约定**（`tests/test_record_failure_feedback.py:81/283/302`、`tests/test_start_record_command_golden.py:253-256/270/273`，实测 grep 共 10 处）。`monkeypatch.setattr(main.time, "sleep"/"time"/"strftime"/"localtime", …)` 改的是 stdlib `time` **模块本体**，即全进程生效——本仓「测试不得自实现被测逻辑」条目点名禁止该写法并要求 `SimpleNamespace(**vars(time))` 浅拷贝后 `setattr(main, "time", shim)`；同一文件的 `subprocess` 恰恰用了正确 shim 法（`:62-64/82`），自相矛盾。`time.time` 被恒置 `1_000_000.0`、`httpx.Client` 被整体替换期间，任何并发线程（loguru enqueue、harness 守护线程、coverage）都会吃到假实现（`main.datetime`、`main.os.makedirs` 同理）。**建议**：一律浅拷贝 shim；并加一条静态用例扫描 `setattr(main\.(time|os|datetime|subprocess|httpx), …)` 形态作回归锁。**置信度：高**。
- **MID-67 SM3「known hash」用例只断言长度、不断言标准摘要值（假绿）**（`tests/test_ab_sign.py:125-130`，实测读取）。注释写「SM3('abc') 的已知标准值」，断言却是 `isinstance(str) and len(result) == 64`——任何错误但输出 64 位 hex 的实现都能通过，违反「删掉生产实现就会失败」判据（对照 `tests/test_spider.py:355` 的 md5 KAT 才是正确写法）。同类：`tests/test_ab_sign.py:268-274` 的 `test_deterministic` 名为确定性、实际只断言非空 str，且注释已承认未冻结时间。**建议**：补 SM3 标准 KAT（GB/T 32905 的 `"abc"` 与另一条），确定性用例冻结时间后逐字节比较或改名去掉误导。**置信度：高**。
- **MID-68 i18n 形参日志门禁用例存在结构性盲区，10 处真实违规正从盲区漏过**（门禁 `tests/test_i18n_migration.py:79-81`；违规点实测 AST 复算得 **10** 处：`main.py:3051/3132/3424/3570/4223`、`src/stream.py:865/871`、`src/platforms/bilibili.py:137`、`src/sync_http.py:254`、`src/utils.py:508`）。门禁用例只判 `isinstance(arg, ast.JoinedStr)`——即 f-string 必须是**直接实参**；而 `logger.warning(f"A" + (f"B" if x else "") + f"C")` 的实参是 `ast.BinOp`，门禁看不见。按此复算：门禁可见 347 处、**10 处含占位符的真实违规逃逸**。后果正是本仓立此约定要防的：带占位符的 msgid 在查目录前已完成插值，四语目录永不命中、翻译静默退化为原文（`src/stream.py:863-873` 的斗鱼降级告警即高频日志，切到 en/zh_TW 后仍是中文且无法登记）。**建议**：门禁改为「首参子树中存在含 `FormattedValue` 的 JoinedStr 即违规」；并按约定把这 10 处改为 `i18n.tr(模板, **kw)`、用 `scripts/extract_i18n_strings.py` 补四语目录。**置信度：高（实测）**。
- **MID-69 上一轮修复项普遍缺回归锁，腐烂只能靠人眼发现**（实测 grep）。`tests/` 内对以下符号**零引用**：`_RECORD_STALL_SECONDS` / `_MAX_RECORD_SECONDS` / `_watchdog_hit`（CR-05/06）、`only_fans`（CR-04 跨层默认值）、`_need(` / `bad tars`（CR-03 畸形帧）、`_looks_like_secret_value` / `_validate_room_url_target` / 400 文案（CR-08/09/10）、`delete_line`（SEV-05）、`decorator_list`（CR-12 装饰器契约 AST 锁）。这与「回归锁 + 变异验证」口径存在成规模缺口，也是本轮 SEV-02/03/05 能在「已修复」项旁边长出旁路的直接原因——**修了实现、没锁行为**。**建议**：按第六节优先级表补齐，SEV 级修复优先做变异验证（临时改坏生产实现确认用例变红）；纯断言调整类改动可按 AGENTS 2026-09-17 条款免做变异验证。

---
## 五、轻微问题（P2，24 项）

- **MIN-01 `create_var` 房间线程键可与存活线程重名**（`main.py:4415/4445`）。键 `thread_{monitoring}` 由 `len(running_list)` 推导并随房间退出回落，新房间可复用已存活线程的键 → 覆盖注册，旧线程退出时 pop 掉**别人的**条目。当前该字典只写/只 pop、无遍历方（已 grep 确认），暂无功能故障，但与注释宣称的「防无界增长」相反，且任何「按 `create_var` 枚举房间线程」的后续改动都会立刻踩坑。建议改用生命周期无关的唯一键，pop 时校验 `get(key) is current_thread()`。**置信度：高（当前影响有限）**。
- **MIN-02 `_probe_hls_segment` 把分片拒绝记到永不命中的退避键**（`src/stream_select.py:414-418`）。`_probe_backoff_key` 为 `scheme://host/path`，此处传的是**分片 URL**（`…/_6000.ts`），而查询侧（`:554`）用的是播放列表 URL，且分片取自列表末行、每轮滑动 → 写入条目永不被读到，只被自身过期清理回收。「分片被拒 → 下轮跳过该线路探针」在分片层完全没落地（返回值路径正确，属静默失效的退避记录）。建议改记 `playlist_url`，或删除该行并注释「分片层不参与退避」。**置信度：高**。
- **MIN-03 master playlist 只探「首个变体」，与 ffmpeg 实际选用的变体可能不同**（`src/stream_select.py:353-360`）。过滤 `#` 行时把 `#EXT-X-STREAM-INF:BANDWIDTH=…` 一并丢弃，只能按位置取 `lines[0]`；HLS 规范不要求变体按带宽降序（不少生成器升序列出，最低档在前），ffmpeg hls demuxer 又按自身码率策略挑档 → 可能只证明了**最低档**分片可取而实际拉最高档，正是 2026-09-13 斗鱼 hw「列表 200、分片 404」假绿事故要防的那类偏差，只是从列表层挪到了变体层；反向情形（首变体不可用而高档可用）则误杀可用源，幸有 `last_resort` 兜一半。**建议**：解析 `BANDWIDTH`（`src/spider.py` 已有模块级 `_BANDWIDTH_PATTERN`）并探测带宽最高变体。**置信度：中**。
- **MIN-04 `converts_mp4` 超时杀进程后残留半成品 `.mp4`，产物库出现「看似完整」的坏文件**（`src/video_postprocess.py:47-52`）。`TimeoutExpired` 分支 `kill()` 后 raise，目标 mp4 已写到一半（重编码路径无 `-movflags +faststart`，被杀后 **moov 缺失、完全不可播**），而 `is_original_delete` 分支未走到 → 源 ts 保留，用户目录同时留下「能录不能播的 ts + 一个大小可观、打不开的 mp4」；`-n` 保证下次同名直接覆盖，但没有任何重试会再来一次。默认 `timeout=600` 对 1800s 分段的 libx264 重编码在中低端机上常不够。**建议**：超时/失败分支删除本次生成的输出（仅当它是本次产物且存在）并明确提示「已保留源文件」；重编码超时按源文件体积/时长线性放大或用 `-preset ultrafast`。**置信度：高**。
- **MIN-05 B 站 `qn→代码` 反向映射被 SD/LD 同值 80 覆盖，标清永远回采成流畅**（`src/stream.py:954-962`）。`video_quality_options` 中 SD 与 LD 都是 `"80"`，`qn_to_code = {v: k for k, v in …}` 后写覆盖前写 → `qn_to_code["80"] == "LD"`；B 站下发 `current_qn=80` 时 `actual_quality` 恒为「流畅」，`is_downgrade("SD","LD")` 因此打出**不存在的降级告警**（等级 7→8）。另 `accept_qn` 常含表外值（20000/401/30000），`qn_to_code.get(str(q), str(q))` 会把裸数字塞进 `available_qualities`，与画质下拉的 `BUILTIN_QUALITIES` 白名单口径不一致。**建议**：SD/LD 用不同 qn（无独立标清档时把 SD 并入 LD 或映射 64）；反向表按「一对多优先返回更高档」显式构造；表外 qn 走 `code_to_zh` 兜底。**置信度：高**。
- **MIN-06 快手按数字画质索引 `QUALITY_MAPPING_BIT` 位置取值，与通用索引错位（潜伏）**（`src/stream.py:618`）。`QUALITY_MAPPING` 位置序为 `OD,BD,UHD,HD,SD,LD`，而 `QUALITY_MAPPING_BIT` 因插入蓝光子档位变为 `OD,BD,BD30,BD20,BD8,BD4,UHD,HD,SD,LD`：同一数字在两表指向不同档（`2` 在通用语义是 UHD、在此是 BD30/30000kbps），且 `result["quality"]` 被改写成 `"BD30"`。当前 `main.py:3080` 一律先过 `get_quality_code`（只认中文名），录制链送不进数字，属**潜伏**缺陷；但 `get_quality_index` 的数字分支（AGENTS 明文保留 0–5 语义）、`tests/test_stream.py` 与 `scripts/…standalone.py` 都以数字画质为入参，任何新增「按数字选档」入口一接上就会错。**建议**：数字先经 `QUALITY_MAPPING` 解成代码再查 bitrate 表，或为两表各配 `idx→code` 显式序列常量。**置信度：高（不可达已注明）**。
- **MIN-07 强制直下分支的录制状态清理走裸 `discard`+`pop` 而非 `clear_record_info`**（`main.py:3611-3615`）。与 SEV-09/MID-01 同族：绕过了 `clear_record_info` 中「URL 已注释时同步移出 `running_list` 并递减 `monitoring`」这一步，监控计数在异常收尾路径上可能不回落。**建议**：统一走 `clear_record_info`，把状态清理收敛到单一入口。**置信度：中**。
- **MIN-08 `weverse_auth` 绕过统一 HTTP 入口，失败响应体未经脱敏且不支持代理**（`src/weverse_auth.py:44/60`）。① 用 `requests` 直连：既不走 `src/sync_http._session()`（丢线程级连接复用，与 AGENTS 该条目相悖），也不接受 `proxy_addr`——Weverse 是必须海外网络的平台，本仓其它海外平台一律 `abroad=True`/透传代理，此处是唯一例外；② 不受 `http_config` 的 SSL 策略约束；③ MI-22 新增的 `body=response.text[:200]` 未过 `utils.mask_credentials()`。当前 Weverse 错误体多为纯错误码，风险低，属**口径不齐**。**建议**：改 `sync_http.sync_req(..., proxy_addr=...)`，body 过码。**置信度：中**。
- **MIN-09 若干异常吞没点缺异常类型线索**（如 `src/stream.py:676`、`src/collector.py:161-163`、`src/danmaku_monitor.py:245-246`、`src/ffmpeg_proc.py:139`）。多数为刻意降级（弹幕监控不得影响录制、清理失败不得阻断退出），但少数 `except Exception: pass` / `logger.debug(e)` 未带 `type(e).__name__` 与上下文，与本仓「异常日志必须带异常类型与上下文、禁止裸 `logger.xxx(e)`」的硬约定不完全一致（Windows 下 `socket.timeout`/`TimeoutError` 的 `str()` 为空，只写 `{e}` 会打出空白行）。**建议**：这几处补 `type_name`/`masked_url` 关键字实参；确属「吞没即正确」的加一行注释说明吞没后果。**置信度：中**。
- **MIN-10 前端内嵌四语目录与后端目录需五处同改，本轮核对一致但无机械保障**（实测：`web/app.js` 内 `zh_CN/en_US/en_GB/zh_TW` 各 **112** 键，三向差集为空，所有 `t('...')` 引用键均存在；后端四目录各 635 条、零占位符差异、零空译文）。AGENTS 已把「新增/修改翻译串须同步五处」写成硬约定，但前后端目录**互不相干**且无跨端一致性用例（`scripts/extract_i18n_strings.py` 只扫后端）。**建议**：加一条用例断言「`web/index.html` 中所有 `data-i18n` 键 ∈ 前端四语目录键集合」，把「靠人眼记得同步」变成机械保障。**置信度：高**。
- **MIN-11 `remove_duplicate_lines` 的编码回退分支残留首轮解码结果**（`src/utils.py:482-497`，与 MID-29 同函数、成因不同）。`unique_lines` 在 `UnicodeDecodeError` 后未清空即继续按系统编码读，两轮的键混在同一 OrderedDict → 可把首轮产生的 U+FFFD 乱码键写回文件。**建议**：回退分支先 `unique_lines.clear()`。**置信度：高**。
- **MIN-12 `ws_client.connect()` 末尾的 `self._ws` 清理块不可达，`_ws` 悬挂已关闭连接**（`src/ws_client.py:228-264`、`:267-269`，实测结构核对）。上方 try/except/else 四条出口全部是 `break`/`continue`，循环顶部再进 `async with websockets.connect(...)`，该块永不执行。于是断线后、重连退避 `await asyncio.sleep(...)` 期间（最长 base×16×1.3 ≈ 上百秒）`self._ws` 仍指向上一条已关闭连接，而 `send()`/`send_nowait()` 只判 `is None` → 进房包/心跳全打在死连接上，异常被吞成一条 debug，表现为「重连后不再推弹幕」且无明确线索。**建议**：把 `self._ws = None` 移到进入 `continue` 之前（close 已由 `async with` 负责），或发送前按 `state is OPEN` 判活。**置信度：高**。

- **MIN-13 `send_nowait` 裸 `ensure_future` 且不持任务引用、异常不可见**（`src/ws_client.py:292-296`，对照 `src/base.py:47-64`）。`base.py` 的注释已把这条坑写死（「裸 `asyncio.ensure_future` 的异常仅在任务被 GC 时打印到 stderr，进房协程抛异常将完全无日志地静默死亡」）并提供 `spawn_danmaku_task`，而弹幕客户端最核心的进房/心跳发送口仍是裸调用：任务无强引用（asyncio 只持弱引用，属文档化的丢失风险），`_send_lock` 竞争时多个发送任务无界堆积、无人回收。**建议**：改 `spawn_danmaku_task` + `_pending: set` 保引用（`add_done_callback(discard)`）并设堆积上限。**置信度：中高**。
- **MIN-14 `Dockerfile` 的 `version` 标签在 `ARG APP_VERSION` 声明之前使用，实际恒为空**（`Dockerfile:47-50` vs `:58`，实测）。Docker 按行做变量替换，`LABEL version="${APP_VERSION}"` 求值时该 ARG 尚未声明 → 标签固化为空串，`--build-arg APP_VERSION=4.3.0` 不生效。而 `scripts/check_version.py:63` 只正则匹配到字面 `version="${APP_VERSION}"` 即判 DYNAMIC 通过——**门禁恰好检不出这个顺序错误**，与第 1 条版本约定「Dockerfile 经 APP_VERSION 动态注入」的表述不符。**建议**：`ARG APP_VERSION` 上移到 LABEL 之前，并让 check_version 断言「声明行号早于使用行号」。**置信度：高**。
- **MIN-15 维护脚本与 CI 仍引用已删除的 `gui_legacy.py`（3 处）**（`scripts/check_annotations.py:76`、`scripts/extract_i18n_strings.py:29`、`.github/workflows/ci.yml:162`，实测 grep）。该文件已于 2026-09-10 删除。三处均无害（`extract` 有 `if not path.exists(): continue` 兜底、paths-filter 匹配不到文件），但属同源约定漂移，会让后来者误以为该入口仍存在。**建议**：一并移除。**置信度：高**。
- **MIN-16 `trivy.yml` 的 `actions/checkout@v4` 偏离全仓 v7 基线，并带模板残留**（`.github/workflows/trivy.yml:30`、`:10`、`:34/39`，实测）。`ci.yml`/`build-release.yml` 均为 v7（符合约定），唯此文件落回 v4；另有异常分支名 `[ "main", "保护" ]` 与占位镜像名 `docker.io/my-organization/my-app`。`aquasecurity/trivy-action` 已按 commit SHA 钉定（良好）。**建议**：升 v7 并清理占位符/分支名。**置信度：高**。
- **MIN-17 `issue-translator.yml` 用浮动标签的第三方动作处理不可信 issue 内容，且未声明最小权限**（`.github/workflows/issue-translator.yml:2-12`）。触发源是任意外部贡献者的 issue/评论正文；`usthe/issues-translate-action@v2.7` 以浮动 semver 标签引用（非 SHA 钉定，同 major 可推送新代码），且 job 无 `permissions:` 收敛，继承默认。属「不可信输入 + 浮动 ref + 未降权」的复合面（该动作仅在 public repo 的 issue 事件下运行，故暂列轻微）。**建议**：钉 SHA + 显式 `permissions: { issues: write, contents: read }`。**置信度：中高**。
- **MIN-18 `docker-compose.yaml:28` 以 `:latest` 作为可拉取回退镜像**：虽有本地 `build:`，但未 build 直接 `up` 会拉取上游 `:latest`（版本漂移/可能非本项目产物），对可复现部署不利；端口映射已收敛为 `127.0.0.1:8000:8000` + `no-new-privileges:true`（良好），Dockerfile 亦为非 root（`USER recorder`）+ `HEALTHCHECK` + NodeSource 脚本 `sha256sum -c` 校验 + base 镜像钉 `python:3.14-slim-bookworm`。**建议**：`pull_policy: build` 或钉版本标签。**置信度：中**。
- **MIN-19 `scripts/check_coverage.py` 在「无 coverage 数据」时仅 WARN，不区分「忘记跑测试」与「覆盖率不达标」**（实测：单独调用输出 `WARN: coverage json exited with code 1` + `ERROR: failed to read coverage json report`）。本仓曾专门把「模块查不到」由告警改为失败以消除 `PASSED: All 0 module(s)` 假绿；数据文件缺失这一路径仍非硬失败，留下「本地没跑 `--cov` 却以为过闸」的空间。**建议**：无数据即 `SystemExit` 并提示先执行 `pytest --cov=src`。**置信度：高**。
- **MIN-20 `proxy.py`：IPv6 括号形态解析必抛 `ValueError`；Linux 只读小写环境变量；代理凭据被丢弃**（`src/proxy.py:110-117`、`:141-158`、`:43-47`）。① 注册表 `ProxyServer = "[::1]:8080"` 经 `split(":", 1)` 得 ip=`"["`、port=`":1]:8080"` → `__post_init__` 抛 `ValueError("Port must be a digit…")`，而 `__post_init__` 里特意为 `[xxxx]` 形态放行的分支实际永远收不到合法输入（整块校验是死的）；异常被 `main.py:3938` 外层吞成一行 print，`global_proxy` 仍为 True 而 `proxy_addr` 未取到。② Linux 只读 `http_proxy/https_proxy/ftp_proxy`，漏 `HTTP_PROXY/HTTPS_PROXY/ALL_PROXY`（requests、curl 与多数工具都认大写）→ 检测为「无代理」而实际有。③ `split("@", 1)[1]` 把 `user:pass@` 抹掉后 `ProxyInfo` 只留 ip/port，认证代理无法还原完整地址。**建议**：解析改 `rsplit(":", 1)` + `[]` 特判；`os.getenv(k) or os.getenv(k.upper())` 并补 `all_proxy`；`ProxyInfo` 增 `user/password`（或保留原始串）。**置信度：高**。
- **MIN-21 `atomic_write_text` 的 tmp 名只含 pid；`web_config` 另用一把同名约定的写锁；且不保留原文件权限**（`src/utils.py:415`、`src/web_config.py:403`）。同进程两线程写同一目标时 tmp 同名，`open(tmp,"w")` 互相截断 → `os.replace` 可把半写内容替换上去。当前 config.ini/URL_config.ini 写方都持 `main.file_update_lock`（web_api 各端点显式包了）故暂不可达，但 `web_config._atomic_write_text` 走的是**另一把** `_config_write_lock`，任何只走该锁的新写入点都会立刻变成同 tmp 竞态。另：本函数不 chmod，POSIX 下 `os.replace` 会把 `utils.py:456` / `config_io.py:347` 设过的 `0600` 换成 temp 的 umask 模式（通常 0644）——CR-07 的权限收紧可被任一非 `update_config` 的整文件重写静默抹掉（Windows 上 `os.chmod` 仅影响只读位，无碍）。**建议**：`tempfile.mkstemp(dir=父目录)` 或名字加 `threading.get_ident()`；两把写锁收敛为一把；写前捕获原 mode 或写后 `chmod`。**置信度：高（机制确定，当前不可达已注明）**。
- **MIN-22 `PlatformBreaker` 探针无代数标记：租约重授予后，旧探针的回报会替新探针复位状态机**（`src/scheduler.py:140-149`、`:171-179`）。租约本身是刻意设计（防永久熔断，回归锁 `test_platform_breaker_probe_lease_regrants_after_timeout` 须保留），但 `_probing` 是布尔而非「当前探针标识」。交错：T 授予探针#1（解析慢、多轮超时 → 70s 后才 record）；T+60 租约过期授予探针#2；T+70 探针#1 的 `record()` 命中 half-open 分支 → `success=True` 即 `state="closed"`、`_samples.clear()`、`_probing=False`，把探针#2 的在途状态一并复位。另外 half-open 分支无法区分「探针回报」与「转态前已放行、仍在途的普通轮次回报」，一个在途成功轮即可清窗口 + 关闭熔断。影响为过度放行 1~2 个探针、不会误熔断，属可容忍偏差但削弱冷却语义。**建议**：加 `_probe_seq` 自增，`allow()` 时带回、仅接受与当前 seq 匹配的回报做 half-open 迁移；非探针样本只入窗口不改状态。**置信度：中高**。
- **MIN-23 `_shutdown` 直接 `loop.stop()`，`danmaku.start()` 任务以 pending 态被 close**（`src/collector.py:174-193`、`:244-256`）。`await danmaku.stop()` 已按本仓约定用 `asyncio.wait_for(_SHUTDOWN_TIMEOUT_SECONDS)` 限时（该保证正确、勿改），但 `start()` 协程从 `ws.close()` 返回还需若干轮事件循环；`loop.stop()` 立刻掐断 → `run_until_complete` 抛 RuntimeError（被 `except RuntimeError: pass` 吞掉，符合预期），而 `danmaku.start(...)` 的 Task 仍 pending，`loop.close()` 时由 `Task.__del__` 向 stderr 打「Task was destroyed but it is pending」，并让平台 `start()` 里 `finally` 的清理链（如 buvid/连接副作用）永不执行。多房间停止录制时该输出会集中刷屏 `web_console.log`。**建议**：保存任务引用，`_shutdown` 内先 `task.cancel()` 再 `await asyncio.sleep(0)` 让取消传播，最后 `loop.stop()`。**置信度：中**。
- **MIN-24 注释/文案与实现不符的零散点（不影响功能，但会误导排查）**：① `src/srt_writer.py:158-175` 重试开片在 `line` 已按递增 `_index` 生成之后无条件 `_index = 0`、`_last_end = None`，同一 `.srt` 内可出现重复序号与非单调时间轴（SRT 规范要求块序号递增；注入清洗与片内钳制两项既有保证不受影响）；② `src/spider.py:1466` 与 `:1469` 两条相邻注释对「是否跳过 `d1--cn-gotcha`」互相矛盾（代码取前者）；③ `src/spider.py:2201` `get_soop_headers` 注释承诺「两次请求头一致」，实际每次调用新生成 `client-id`、两个调用方各取一个（`:2220`/`:2236`），第三入口 `:2306` 更是不带 client-id；④ `src/ffmpeg_install.py:384-389` 注释称「yum 失败会自然落到 apt 分支」，但 `is_RHS` 只在 `FileNotFoundError` 分支置 False，故「yum 存在但 install 失败」（RHEL 系无 EPEL 的常态）直接落到「请手动安装」——属被证伪的事实性陈述，按本仓「注释例外①」应就地纠正而非追加；⑤ **`AGENTS.md:1063` 把 `main.file_update_lock` 列为「非重入锁」，而 `main.py:296` 的定义是 `threading.RLock`**（注释明确说明可重入的理由），据此推理会把 `src/web_api.py:480/526`「外层持锁再调内层自持同锁」这一**安全**写法判成自死锁，也可能诱导有人把它「改回 Lock 以符合文档」；真正的非重入锁是 `record_state_lock`（`main.py:299`）与 `web_api._tokens_lock`（`:69`）。建议该条移出 `file_update_lock`，并改为「引用源码定义行判定」而非列举。**置信度：高**。

---

## 六、修复优先级与实施顺序建议

### 6.1 优先级批次

| 批次 | 目标 | 条目 | 预估改动面 | 建议验证方式 |
|---|---|---|---|---|
| **P0-a 安全面收口**（建议 1 个迭代内完成） | 关掉可被外部输入的接管/绕过链 | SEV-02、SEV-03、SEV-04、SEV-05、MID-36、MID-37 | `web_api.py` 3 处接线 + `web_config.py` 1 个函数重写 + `app.js` 掩码提交 | TestClient 用例（含大小写变体、CRLF 夹具、`PUT` 与 `POST` 裁决一致性） |
| **P0-b 录制可用性** | 修「必然失败/必然误杀」 | SEV-06、SEV-07、SEV-08、SEV-09、MID-02、MID-03、MID-04 | `spider.py` 2 处 + `main.py` 5 处（均为局部改动） | 纯函数单测（Shopee 三类 TLD）+ 装饰器契约 AST 锁 + 看门狗双用例（45s 不杀 / 11min 杀） |
| **P0-c 并发与资源治理** | 恢复并发约束的语义 | SEV-01、MID-21、MID-24、MID-25 | `scheduler.py` 信号量重写（约 30 行）+ `collector.py`/`danmaku_monitor.py` 各 1 处 | 新增「有持有者时 recompute 不放大并发」用例；80 房间压测观察实际并发 |
| **P0-d 发布链与状态清理** | fail-closed + 不留幽灵状态 | SEV-10、MID-01 | `build_exe.py`（`--require-pinned` + CI 注入）+ `main.py` 1 处 | CI 干跑断言缺钉定即 fail；`recording` 为空断言 |
| **P1-a 静默失效与假绿清除** | 让故障可观测、让门禁可信 | MID-05、MID-06、MID-07、MID-13、MID-14、MID-17、MID-18、MID-28、MID-40、MID-45、MID-51、MID-63、MID-64、MID-68 | 分散 | 每项配回归锁（见 6.3）；门禁侧以「有告警即失败」为准 |
| **P1-b 并发时序与生命周期** | 消除丢信号/串号/无 TTL | MID-22、MID-23、MID-26、MID-30、MID-31、MID-32、MID-33、MID-35 | `async_http.py`、`collector.py`、`stream_select.py`、`ttwid.py`、`web_api.py` | 并发用例（多房间同 key）、SSL 策略一致性断言、面板响应性冒烟 |
| **P1-c 数据耐久与写回** | 防丢失更新与半写 | MID-55、MID-56、MID-57、MID-29、MID-11 | `gui.py`、`utils.py`、`config_io.py`、`sync_http.py` | CRLF/并发写夹具；掉电语义按 fsync 断言（可用 mock 校验调用序列） |
| **P1-d 平台解析批量加固** | 收敛 CR-12 范式 | MID-41、MID-42、MID-43、MID-44、MID-46、MID-47、MID-48、MID-49、MID-50 | `spider.py`（约 20 个函数） | 按平台分批；每批以 `_loads_dict` 迁移 + fixture 化返回体 |
| **P1-e 安装与运维链路** | 消除死路与误杀 | MID-58、MID-59、MID-60、MID-61、MID-62 | `msg_push.py`、`ffmpeg_install.py`、`StopRecording.vbs`、`migu.js` | 哈希过期场景手工回归；VBS 可用「ping.exe 改名伪装」的既有静默模式实弹验证 |
| **P2** | 文案/口径/纵深 | 第 5 节全部 24 项 + MIN-24 文档纠正 | 零散 | 纯文档/注释改动按 AGENTS「完成定义」豁免条款执行 |

### 6.2 需要「先改文档/约定」再改代码的两处

1. **`AGENTS.md:1063` 非重入锁清单纠正**（MIN-24 ⑤）：该条直接指导并发审查，错误会批量产出假 P0。应改为「`_tokens_lock` / `record_state_lock` / `web_api._cache_lock` 为非重入；`file_update_lock`、`web_config._config_write_lock` 为刻意 RLock」，并要求判据引用定义行。
2. **门禁口径补两条**（MID-63、MID-68）：「isort/black 必须带 `PYTHONUTF8=1`，且 stderr 有 `UserWarning` 即失败」；「i18n 门禁用例的判据从『首参是 JoinedStr』改为『首参子树含 FormattedValue』」。二者都应写回 `AGENTS.md`「格式化命令」与「关键约定」章节，避免只留在本报告里。

### 6.3 回归锁补齐清单（与 MID-69 对应）

| 修复 | 建议的锁 | 归属测试文件 |
|---|---|---|
| SEV-01 并发上限 | 持有者存在时 `recompute()` 不放大可用数；`value` 语义单测 | `tests/test_scheduler.py` |
| SEV-02/03 SSRF | `PUT` 与 `POST` 对同一载荷裁决一致；`ipaddress` 变体表驱动（十进制/八进制/IPv6 带端口/CGNAT） | `tests/test_web_api.py`、`tests/test_web_config.py` |
| SEV-04 认证 | 大小写变体下「哈希化 / 防清空 / 吊销 token」三项均生效 | `tests/test_web_api.py` |
| SEV-05 / MID-05 | CRLF 夹具下的 `delete_line`；非 TS 分段的 `_record_output_bytes` | `tests/test_config_io.py`、`tests/test_record_container.py` |
| SEV-06/07 | Shopee 三 TLD 纯函数用例；`login_*` 装饰器契约 AST 锁 | `tests/test_spider_fixes.py`、新增 `tests/test_decorator_contract.py` |
| SEV-08/09 | 看门狗双用例（45s 不杀 / 11min 杀）；无 `flv_url` 时 `recording` 为空且无存活字幕线程 | 新增 `tests/test_record_watchdog.py` |
| MID-63/64/68 | 门禁自身：`isort` 告警即失败；`logger` 实参子树含占位符即违规 | `ci.yml`、`tests/test_i18n_migration.py` |

---

## 七、门禁与测试可信度专项结论

1. **可见结论**：black（136 文件无差异）、mypy 双跑（各 117 文件 0 问题）、basedpyright（0/0/0）、`check_annotations.py`（平均密度 22.8%）、`compile_po.py --check`（636 条同步）、`check_version.py`（PASS）、`extract_i18n_strings.py`（缺失 0）、前端 `node --test`（9 passed）、排除挂死用例后的 `pytest`（**1041 passed / 2 skipped / 0 警告**）——**本轮登记的问题无一能被现有门禁发现**，这本身就是最重要的结论。
2. **门禁假绿两处**：isort 在 GBK 语言环境下静默跳过 16 个自有文件（含 `main.py`/`gui.py`/`web.py`/`src/spider.py`）且 rc=0（MID-63）；i18n 形参日志门禁用例对 `BinOp` 包装的 f-string 不可见，10 处违规长期漏网（MID-68）。
3. **套件可靠性一处**：全量 `pytest` 在本机不可完成，用例内 `timeout=300` 未构成有效上界（MID-64）。前端用例本身质量良好（`node:vm` 沙箱 + DOM/fetch 桩 + 真实事件委托链路，零 npm 依赖），问题只在 Python 包装层。
4. **测试写法违规三处**：`filterwarnings("ignore::RuntimeWarning")`（MID-65）、就地改写 stdlib 模块本体 10 处（MID-66）、`assert` 名不副实的假绿（MID-67）。三者都属本仓已明文禁止或已有正确示范的形态，宜一次性清理并加静态防回归。
5. **值得肯定的实现**（实测确认，非问题）：`tests/` 与被测模块同名一一对应、`conftest.py` 冻结翻译为恒等映射且禁删、`test_ffmpeg_reconnect_args.py` 的三不变量 AST 锁、`test_record_container.py` 的「查表而非字面量」AST 锁、`test_start_record_command_golden.py` 的字节级黄金快照（20 用例覆盖 5 条保存路径）、`test_platform_dispatch.py` 的表结构/优先级锁、`test_async_http_lock.py` 移除宽泛过滤作回归守卫。**这些锁正是本报告多数中等项无法升级严重的原因。**
6. **覆盖率**：`scripts/check_coverage.py` 本轮未能出具逐模块结论（见 MIN-19），建议连同 P1-a 一起补跑并附数据。

---
## 八、逐文件定位索引

> 下表按「条目正文中出现的文件（含跨文件引用）」统计，用于按文件检索；**每项的主位置仍以第三/四/五节中该条目首行的 `文件:行号` 为准**。

| 文件 | 关联条目 |
|---|---|
| `main.py` | SEV-01, SEV-02, SEV-05, SEV-06, SEV-08, SEV-09, MID-01 … MID-12, MID-17, MID-19, MID-20, MID-24, MID-26, MID-28 … MID-31, MID-43, MID-47, MID-51 … MID-55, MID-63, MID-68, MIN-01, MIN-07, MIN-20 |
| `src/spider.py` | SEV-06, SEV-07, MID-22, MID-27, MID-29, MID-33, MID-40 … MID-50, MIN-03, MIN-24 |
| `src/stream.py` | MID-13 … MID-16, MID-18, MID-20, MID-26, MID-47, MID-68, MIN-05, MIN-06, MIN-09 |
| `src/stream_select.py` | MID-17 … MID-19, MID-26, MID-28, MID-43, MIN-02, MIN-03 |
| `src/web_api.py` | SEV-02, SEV-04, SEV-05, MID-34 … MID-36, MID-39, MID-52 |
| `src/web_config.py` | SEV-03, SEV-05, MID-35, MID-57, MIN-21 |
| `src/async_http.py` | MID-21, MID-22, MID-26, MID-27, MID-49 |
| `src/collector.py` | MID-23 … MID-25, MIN-09, MIN-23 |
| `src/utils.py` | SEV-07, MID-28, MID-29, MID-57, MID-62, MIN-11, MIN-21 |
| `gui.py` | MID-51 … MID-56, MID-63 |
| `src/scheduler.py` | SEV-01, MIN-22 |
| `src/recorder_status.py` | SEV-01, MID-31, MID-54 |
| `src/danmaku_monitor.py` | MID-25, MID-30, MIN-09 |
| `src/config_io.py` | SEV-05, MID-57, MIN-21 |
| `src/ffmpeg_proc.py` / `src/video_postprocess.py` | MID-32, MIN-09 ／ SEV-09, MIN-04 |
| `src/ws_client.py` | MIN-12, MIN-13 |
| `src/cookie_cache.py` | MID-22, MID-40 |
| `src/proxy.py` / `src/sync_http.py` / `src/ttwid.py` / `src/room.py` / `src/weverse_auth.py` / `src/base.py` / `src/srt_writer.py` | MID-27, MID-33, MID-48 ／ MID-27, MID-68 ／ MID-33 ／ MID-27, MID-33 ／ MIN-08 ／ MIN-13 ／ MIN-24 |
| `web/app.js` / `web/index.html` / `web/style.css` / `web.py` | MID-37, MID-38, MID-39, MIN-10 ／ MID-38, MIN-10 ／ MID-38 ／ SEV-04, MID-36, MID-63 |
| `src/javascript/migu.js` | MID-61, MID-62 |
| `src/platforms/bilibili.py` | MID-40, MID-68（另 `huya.py`/`douyu.py`/`twitch.py`/`_tars.py`/`_xbogus.py` 经核对**无新增缺陷**） |
| `build_exe.py` / `Dockerfile` / `docker-compose.yaml` | SEV-10, MID-63 ／ MIN-14 ／ MIN-18 |
| `src/ffmpeg_install.py` / `src/node_install.py` | SEV-10, MID-59, MIN-24 ／ SEV-10, MID-59 |
| `msg_push.py` / `i18n.py` | MID-58 ／ MID-52 |
| `StopRecording.vbs` | MID-60（编码 UTF-16 LE/BOM/CRLF 实测合规） |
| `.github/workflows/ci.yml` / `build-release.yml` / `trivy.yml` / `issue-translator.yml` | MIN-15, MID-63 ／ SEV-10, MIN-16 ／ MIN-16 ／ MIN-17 |
| `scripts/check_annotations.py` / `extract_i18n_strings.py` / `check_version.py` / `check_coverage.py` | MIN-15 ／ MIN-10, MIN-15 ／ MIN-14 ／ MIN-19 |
| `tests/`（可信度专项） | MID-64 … MID-69（涉及 `test_frontend_quality_ui.py`、`test_bilibili_danmaku_info.py`、`test_record_failure_feedback.py`、`test_start_record_command_golden.py`、`test_ab_sign.py`、`test_i18n_migration.py`、`test_scheduler.py`） |
| `AGENTS.md`（约定与代码漂移） | MIN-24 ⑤、6.2 第 1 项 |

---

## 九、已回源复核、确认**不构成问题**的实现（供后续审查者复用）

> 本节按 AGENTS.md「并行分组代码审查的分工口径」要求单列，用于阻止同一批「刻意设计」在后续审查中被反复误报。

**约定与风格类**：`#` 行注释、全仓 0 处 docstring（`check_annotations.py` 实测通过）；`except A, B:` 无括号的 PEP 758 写法（实测 `except A, B as e:` 为 0 处）；中文注释；line-length 120；`mypy` 无参跑 + `--platform linux` 双跑；平台符号以 `sys.platform` 字面量早返回门控、未使用被禁止的 `# type: ignore`（现存 11 处均带具体 code，属可选依赖 `execjs`/`websockets` 的正常存根缺位场景）。

**录制与选源链**：`-reconnect*` 全部位于 `-i` 之前且逐项紧跟取值；`.m3u8`（已按 `lower()`）判定后 `del` 摘除 `-reconnect_at_eof` 参数对；`-headers`/`-tls_verify`/`-http_proxy` 一律按 `-i` 锚点插入、无裸数字下标；`-segment_format` 5 处取值全部查 `SEGMENT_FORMAT_BY_SUFFIX`、无字面量；`-protocol_whitelist` 已剔除 `file`；ffmpeg 以 argv 列表启动、不经 shell，`real_url` 无法造成命令注入。录制槽 `acquire` 严格在 `Popen` 之前、`try/finally` 覆盖注册与弹幕启动段且恒归还；`_rec_sem` 在函数入口一次性捕获以规避主循环 rebind 竞态。网络槽与录制槽**无嵌套持有序**，不存在反向死锁。

**探针与退避语义**：`_throttle_probe` 的「锁内算 wait、锁外 sleep、`now+wait` 预约登记」构成正确的同 host FIFO 排队并带 3.5s 空闲回收；`_recheck_delay` 基准+抖动、`_confirm_get_ok`「401/403 重试一次再定罪 + 末位仅告警放行 + 异常不推翻 HEAD」、HEAD 非 2xx → Range `bytes=0-0` 判 200/206、末位 content-type/非 200 也放行——均与定稿一致；`_probe_backoff`/`_probe_last_seen` 的读写全部在各自 `threading.Lock` 内（清理用 list-comp 先物化再 pop）；`mark_ffmpeg_reject`/`clear_ffmpeg_reject` 与 `_mark/_clear_probe_reject` 共用同一白名单与键（唯一缺口见 MID-17）；`_probe_backoff_window()` ≥ 一个主循环周期的约束保持；探针客户端「每轮一支、`finally` 无条件 close、`owns_client` 精确区分自建/复用」**刻意不做全局缓存**符合连接预算结论；`clean_name` 的控制字符/Windows 保留名/按字符数截断，`get_record_headers` 的 origin 推导与 `rule.split(":",1)` 均正确。虎牙 FLV-first、斗鱼同 token 的 `.flv→.m3u8` 候选（`partition("?")` 保 query）、`_FLV_FIRST_PLATFORMS` 与「HLS 采集排除=整组剔除」的两种语义分立、蓝光子档位折叠到 `BD` 索引（`BD_SUB_TIERS`）——**均未回归**。

**并发与调度**：无模块级 `asyncio.Lock()`；凭据锁为 `threading.RLock`；`close_all_clients_sync` 与 `_get_client` 的「跨循环不创建 `aclose` 协程」保持；协程内一律 `get_running_loop()`；`PlatformBreaker._fail_count` 与 `_push_sample` 的增量维护严格同步（含 `clear()` 归零）；`ConcurrencyScheduler` 无「调用方持锁 + 被调方自持同锁」自死锁（`set_active_count`/`set_configured_limit`/`set_dynamic_mode` 均在释放 `_lock` 后才 `recompute()`）；无锁序倒置；`_probing` 租约存在（代数标记问题记 MIN-22）；`ResizableSemaphore` 允许容量 0（暂停态）语义正确。`_room_thread_target` 的 `finally` 清理、`start_record` 的 `record_host=""` 预置、`scheduler.allow()` 预检位于 `while True` 顶部——均符合约定。

**配置、日志与收尾**：`_atomic_write_text` 系（同目录 tmp + `os.replace`）、读方只见旧/新完整内容；`read_config_value` 的「内存 `StringIO` 全量序列化成功后才落盘 + 捕获 `(OSError, configparser.Error)` 降级 + 回滚内存键」硬化正确应对 3.14 的 `InvalidWriteError`；`_rewrite_line_by_match` 的段级匹配（半/全角逗号、strip 比对、先排除 `主播:` 段）确可消除 URL 前缀重叠误伤；`update_room_quality` 保留 `#` 前缀/`主播:` 字段/URL 原文且对换行注入 `ValueError`；`config_bool` 与 `format_config_bool` 的「是/否」补写口径自洽、识别集合与 `web/app.js` 的 `CONFIG_*_TOKENS` 逐项一致；`log_archive` 的「先关句柄再改名」「`web_console.log` 改名后立即重建并 `rebind_console_sink()`」「GUI 父进程/测试进程早返回」全部正确。

**面板安全控制（实跑 TestClient 与静态核对）**：鉴权中间件对全部路由「白名单放行 + 其余要求 Bearer」，`/api/config`、`/api/status`、`/api/logs`、`/api/files`、`/docs`、`/openapi.json`、`//api/...`、`/web/../api/config` 在开启认证时一律 401（**无漏挂、无归一化旁路**）；Starlette 1.6 静态挂载对 `%2e%2e` 返回 404，无目录泄露；口令为 PBKDF2-HMAC-SHA256 + 16B 随机盐 + 200k 迭代，比较全程 `hmac.compare_digest`，token 为 `secrets.token_urlsafe(32)`；下载/列目录走 `os.path.realpath` + `commonpath` 前缀判定（`/app/downloads_evil` 不会被判在 `/app/downloads` 内）、悬空符号链接跳过、`FileResponse` 恒带 `attachment`；敏感键判定为「节白名单 + 键名正则 + 值形态（`_looks_like_secret_value`）」三重，`[推送配置]` 29 个键与 `web_password` 逐条命中、反向例外只放行数值型运维参数，前后端两份正则逐字符一致；`_reject_newline` 覆盖 URL/画质/主播名/配置值，`i18n` 语言写回经 `is_recognized_language`+`normalize_language`（返回值只出自固定集合）；`_DANGEROUS_CONFIG_KEYS_FOLDED` 用 `casefold` 与行匹配同强度，且 `RawConfigParser` 无插值 → 「自定义脚本执行命令」被封即无其它 RCE 落点；写接口 `_rooms_config_lock` + `file_update_lock`（后者为 RLock，故嵌套自持**安全**）序列化读改写窗口；无状态变更型 GET、无 CORS 放行；面板所有动态文本经 `esc()` 或 `textContent`/`createTextNode`，CSP `default-src 'self'` + `nosniff` + `X-Frame-Options: DENY` 在放行与拒绝两条路径均附加；`Dockerfile` 非 root + `HEALTHCHECK` + NodeSource 脚本 `sha256sum -c` + base 钉 `python:3.14-slim-bookworm`，`docker-compose` 端口默认 `127.0.0.1:8000:8000` + `no-new-privileges:true`；重试全部经 `.github/actions/retry`（无内联 `for i in 1 2 3`）、`python_build=3.14`/`node_version=24` 跨 workflow 同值、coverage 用 `exclude_also`。**以上不构成问题，勿在后续审查中重复登记。**

**弹幕链路**：`collector.stop()` 与采集线程的**相反序**握手（`stop()` 先 set 再读 `_loop`、`_run()` 先发布 `_loop` 再查 `_stop_event`）未被「顺手修」——本报告 MID-23 只在**不改动这两条保证**的前提下提修复建议；`_shutdown` 的 `asyncio.wait_for` 限时保持；弹幕 WS 显式 `proxy=None` 保持；帧大小与解压膨胀上限（`_MAX_FRAME_BYTES`/`decompress_limited`/`decompress_brotli_limited`）正确；`_sanitize_srt_text` 覆盖 `\r\n` 与 `-->`、片内 `end` 钳制正确；B 站 buvid 链序（进程缓存→登录 cookie→spi→首页 Set-Cookie→UUID 兜底并标 `is_fallback`）与 AUTH_REPLY code 校验 + 看门狗实现一致；`douyu` 粘包推进 `offset += full_len + 4` 与长度域自洽。

**曾被怀疑、经实测排除的三项**（记录以免重复排查）：① `generate_subtitles` 以 `encoding="utf-8-sig"` 追加写会否每条插一次 BOM —— 实测两段连续追加输出仅 **1 个 BOM**（CPython `TextIOWrapper` 在可 seek 的追加模式且位置非 0 时跳过 BOM），实现正确；② `web/app.js` 四套内嵌目录键集合 —— 实测各 **112** 键、三向差集为空；③ 四语后端目录条目数 —— 以 `.mo` 头部 `N=636`（目录条目 635）为权威口径实测，与 JSON/YAML 键数、`extract_i18n_strings.py` 自报值五路一致（与 AGENTS 2026-09-20 那条「不要按新增条数推算」的告诫一致）。

---

## 十、结论

1. **工程基线是健康的**。全部门禁（black / mypy 双跑 / basedpyright / 注释规范 / `.mo` 同步 / 版本动态化 / 前端用例）与排除挂死用例后的 **1041 passed、0 警告**共同表明：该仓库在风格、类型、翻译同步与测试广度上处于良好状态，且上一轮 12 项严重缺陷**无一回归**、`@decorator` 夹注释与 PEP 758 非法形两类形态**全仓零命中**。本轮问题的性质因此集中在「**修复引入的新失配**」与「**语义正确但判据/接线遗漏**」两类，而非普遍性的粗放。（口径注：审查窗口内 black 曾因新增的 `scripts/run_gates.py` 短暂转红，20:48 复跑已恢复 `139 files unchanged`，故记为已消解、不计入统计；这恰好反证作者对门禁红线的响应是分钟级的。）
2. **但「门禁全绿」不等于「行为正确」**。本轮 10 项严重问题**全部**发生在现有门禁完全覆盖不到的位置：并发信号量的字段语义（SEV-01）、写入口不对称（SEV-02）、地址黑名单缺 IP 语义（SEV-03）、大小写归一不彻底（SEV-04）、行尾约定与调用侧不一致（SEV-05，Windows 必然触发）、纯函数边界（SEV-06）、装饰器契约漏配（SEV-07）、看门狗判据基准（SEV-08）、状态登记与清理的次序（SEV-09）、发布链 fail-open（SEV-10）。其中 5 项（SEV-02/03/04/05/10）正是上一轮「部分修复」项的残留或旁路——**修了实现、没锁行为、也没扫旁路**，这是本报告最重要的过程性结论。
3. **安全面收敛优先级最高**。面板默认无认证 + 仅回环绑定，风险主要来自「一旦暴露或被本地页面/进程触达」的放大链：SEV-02 + SEV-03 + MID-36 三者叠加即可从同机/浏览器上下文取得房间写入并驱动内网请求，SEV-04 则允许持有单个 token 者把面板整体降权。建议先完成 6.1 的 **P0-a**，并以 `ipaddress` 语义与统一 `key_norm` 作结构性修复，而非再补一条前缀规则。
4. **可靠性上最需要立刻处理的是「静默失效」**：SEV-05（删除房间静默失败并谎报成功）、MID-05（零字节保护在非 TS 分段上静默失效）、MID-28（脱敏在 4 类形态上静默不生效）、MID-68（i18n 门禁用例看不见真实违规）、MID-63（isort 看不见 16 个核心文件）。它们共同的特征是**不报错**，因此排查成本远高于崩溃类缺陷；修复时应一并补上「未命中即失败/告警」的返回约定（MID-69 的回归锁清单）。
5. **测试可信度需一次专项清理**：三处被明令禁止或名不副实的写法（MID-65/66/67）、一处使本机无法完成全量验证的包装层（MID-64）、以及成规模的回归锁缺口（MID-69）。鉴于本仓「删掉生产实现就该失败」的判据已写在 AGENTS 中，建议把该判据机械化（AST 扫描 + 变异抽样）而非依赖人工自觉。
6. **建议的处理顺序**：P0-a/b/c/d 四批（约对应 17 项）在一个迭代内完成并补齐对应回归锁；P1 各批按「静默失效优先、平台解析可分批」推进；P2 与文档纠正（含 `AGENTS.md:1063` 的锁清单）随相关改动顺带完成。所有涉及录制链路/选源/ffmpeg 参数/平台解析的改动，按本仓「完成定义」须以真实 URL 抽样回归——**本报告不含真机验证结论**，SEV-08/09、MID-13/18/42/46/47 在合并前尤需一次实机确认。
7. **总体判断**：代码库可维护性良好、防御意识明确（大量带日期的「为什么」注释与刻意约定是稀缺资产），但**跨入口对称性、字段语义与默认值口径**是当前系统性弱点。按第六节批次执行后，建议下一轮把审查重心转向：`tests/` 的判据机械化、Web 面板写入口的「单一收口 + 声明式白名单」重构、以及录制状态机（`recording` / `recording_time_list` / `running_list` / `create_var`）的**单一所有权**改造——本报告 4.1 与 4.3 组内多数条目都源于这四者的多写入点。

---

## 附录 A ｜ 上一轮（2026-09-18）严重项回归核查

| 项 | 判定 | 当前证据（本轮实测/回源） | 残留 |
|---|---|---|---|
| CR-01 GUI 子进程 `input()` 挂死 | **已修复（但守卫可被绕过）** | `gui.py:2218-2236` `_has_room_config()` 前置拦截 + `main.py:4013-4020` `except EOFError` → sleep+continue | 「运行中途清空 `URL_config.ini`」仍可达 `input()`；且 BOM 读取缺陷使拦截失效（MID-51） |
| CR-02 一行 3+ 逗号中断整轮解析 | **已修复** | `main.py:4286-4304` 四分支解包（`quality, url, name = split_line` 已消失）+ `:4360-4371` 单行异常 `continue` | 无 |
| CR-03 Tars 长度字段无边界 | **已修复** | `src/platforms/_tars.py:37-49` `_need/_advance/_assert_progress`，消费点 `:90-98/209-212/230-245`，容器 size 上限 `:104-113` | 无畸形帧回归锁（MID-69） |
| CR-04 `only_fans` 三层默认值不兼容 | **已修复** | `src/__init__.py:87`、`src/collector.py:59/228-229`、`src/platforms/douyu.py:37` 统一为 `None`（不覆盖） | 跨层默认值回归锁缺失 |
| CR-05 ffmpeg 无看门狗 | **已修复（引入新缺陷）** | `main.py:752-755/970-1016`、槽位 `finally: _rec_sem.release()` | 停滞判据基准错 → **SEV-08**；6h 上限副作用 → MID-07；无常量级回归锁 |
| CR-06 零字节产物记成功 | **已修复（默认形态）** | `main.py:1073-1088` + `_MIN_VALID_RECORD_BYTES`，`clear_ffmpeg_reject` 仅在体积达标后执行 | 非 TS 分段恒返回 -1 → **MID-05**；直下路径未覆盖 → MID-06 |
| CR-07 凭据明文落盘 + 备份扩散 | **部分修复** | `config_io.py:314-349` 备份默认脱敏 + `chmod 0600`；`utils.py:453-458` 写后 chmod | `atomic_write_text` 不含 chmod，POSIX 下 0600 可被任一重写路径抹掉（MIN-21）；凭据与录制参数仍同文件 |
| CR-08 面板认证可被自身接口关闭/改写 | **部分修复** | `web_api.py:578-594` 目标态双向判定（防自锁已闭合） | 接管链仍完整可达且大小写可绕 → **SEV-04**；建议的「`web_*` 写键白名单」未做（现为单键黑名单） |
| CR-09 房间 URL 无校验（盲 SSRF） | **部分修复** | `web_config.py:201-252` `_validate_room_url_target` + `web_api.py:427/516` 接线；实测 `127.0.0.1`/`169.254.169.254`/`file://` 均被拒 | `PUT /api/rooms` 未接线 → **SEV-02**；多形态可绕 → **SEV-03**；`_match_stream_suffix` 仍为子串包含 |
| CR-10 脱敏为键名黑名单，漏 URL 型凭据 | **已修复** | `web_config.py:467-520` 键名 + 值形态双条件；`web/app.js:48-53` 前后端同源；实测 5 个「凭据嵌在值里」的键均命中 | `mask_credentials` 对头/JSON 形态仍不脱敏（MID-28） |
| CR-11 安装器与打包无完整性校验 | **部分修复** | Zip Slip/`filter="data"`/蓝奏云默认拒装/明文 `http` 终点拒装（`ffmpeg_install.py:285-320`、`build_exe.py:309/346-387`） | 钉定表为空 → **SEV-10**；运行时官方源与 Node 仍 ToFU，且基线不轮转 → MID-59 |
| CR-12 裸取 JSON + 装饰器吞异常 | **具体缺陷已修复，范式未治理** | `_safe_loads`（`spider.py:243-259`）；装饰器错配 4 处已修（`:4496-4521/2968/3079/4161`）；实测「注释夹在 `@decorator` 与 `def` 之间」**0 处** | `login_popkontv`/`login_twitcasting` 新发现错配 → **SEV-07**；裸 `json.loads` 仍 **84** 处 → MID-48；AST 契约锁未做 → MID-69 |

**两项指定复查**：① `@decorator` 与 `def` 之间插注释——全仓扫描 **0 处**，未回归；② `except A, B as e:`（PEP 758 无括号 + `as`，语法错误）——全仓 `*.py` 扫描 **0 处**，`main.py`/`src/web_config.py` 并以 venv Python 3.14 `compile` 通过。

## 附录 B ｜ 审查限制

1. **未执行录制链路**：全部结论来自静态通读、纯函数实跑与门禁实跑；未使用真实直播间 URL 做端到端验证，故平台侧「接口当前实际返回形态」类判断（MID-41/42/43/46）标注为中置信度，须在真机回归中定档。
2. **无法在 Windows 验证 macOS 分支**：`gui.py` 的 pystray/Tk 主线程约定、`_assert_image()` 预热与 `_icon_valid` 置位（AGENTS 明确「复现需 macOS 冻结构建」）仅做静态与 CI 核对。
3. **反代/DNS 重绑定链路未实跑**：MID-35 的 uvicorn `proxy_headers` 改写行为、MID-36 的重绑定利用路径均以 stdlib/上游文档与代码事实推定。
4. **远程 WASM 扩容行为未实测**：MID-61 是否触发取决于 `mgprtcl.wasm` 的 `initial<maximum` 且本次签名是否扩容，离线环境不可判定。
5. **逐模块覆盖率未出具**：`scripts/check_coverage.py` 需前序 `pytest --cov` 数据（MIN-19），本轮未运行该组合。

## 附录 C ｜ 云端安全扫描（交叉证据源）

本报告正文结论**全部来自本地源码证据**，不依赖云端扫描。按要求另执行了 Qoder 全仓库云端安全扫描（异步任务）：

- 报告链接：<https://qoder.com.cn/security-code-scan/reports/1002440/1021445>
- 项目 ID：`1002440` ｜ 任务 ID：`1021445` ｜ 任务名：`manual@20260920-185024`
- 该扫描在云端持续运行，请稍后经链接查看结果。**注意**：本次扫描范围为整个工作区，包含 `config/config.ini`（含非空的 Cookie / Authorization / `web_password` 取值），如需上传后继续使用这些凭据，建议评估是否轮换。

---

## 附录 D ｜ 本地补扫：硬编码凭据穷举、依赖已知漏洞对照与门禁继承

> 因云端安全报告受登录态限制无法由本会话读取，经用户确认改为本地补扫两类云端扫描器最擅长、而第三至五节未系统覆盖的项：**① 自有源码内的硬编码凭据 / 高熵常量**，**② 依赖版本与公开漏洞公告的对照**。补扫过程中另得若干顺带结论（新门禁入口点的 black/isort 状态、此前编号时漏并的 JS 组条目、`AGENTS.md` 与外迁文档的链接可达性），一并登记为 `补-01 … 补-06`。**本附录最终计入 3 项**（补-03 / 补-04 / 补-05）：补-01、补-06 经 20:48 复核已消解，补-02 为 MID-62 的追补证据、不单计。
> 按 AGENTS.md「文档与审查记录里不得出现真实凭据」，本附录所有取值均已脱敏。

### D.1 补扫方法与覆盖面

- 工具：一次性脚本置于 `%TEMP%`（不入库），扫描自有源码 `.py/.js/.mjs/.css/.html/.vbs/.yml/.yaml/.toml/.json` 共 **195 个文件**，显式排除 `.venv/`、`node/`、`ffmpeg/`、`logs/`、`downloads/`、本地工具目录，**并排除 `config/`**（运行时凭据文件，不属源码审查范围）。
- 判据三条：① 变量名含 `secret|token|key|pwd|password|salt|appid|client_id|api_key|auth|bearer|cookie|aes|des|iv` 且赋值为字符串字面量；② 香农熵 ≥ 3.2 或长度 ≥ 24 的字符串字面量；③ 已知凭据签名形态（`AKIA…`、`-----BEGIN PRIVATE KEY-----`、`ghp_…`、`xox…-`、JWT 头 `eyJ…\.`）。

**结果：14 处候选，逐条定伪后无新增真实凭据泄漏。** 两条重点候选判定如下（记为已核实不构成问题）：

| 候选 | 位置 | 定性与判定 |
|---|---|---|
| `_DEFAULT_APP_SECRET = "5419****************7a"` | `src/weverse_auth.py:16` | **不构成问题**：Weverse 网页客户端的**公开应用标识**（非用户凭据），且已按本仓口径提供三级覆盖——`os.environ["DOUYIN_WEVERSE_APP_SECRET"] or _DEFAULT_APP_SECRET`（`:20`），注释亦写明「官方更换时无需改码」。与 MID-46（TikTok 过期游客 cookie）的区别正在此：那条既无过期告警、默认路径直接失效 |
| 32 位 hex 串集合 | `src/utils.py:79-84` | **不构成问题**：`_JS_SHA256_EXPECTED` 是 JS 签名脚本的**完整性钉定表**（实测 7/7 与磁盘一致），属防护资产而非凭据 |

其余 12 处均为配置键名/平台 API 路径/测试桩（如 `QUALITY_OPTIONS_KEY = 自定义画质选项(逗号分隔)`、`liveRoomUserInfo = TikTok…` 为 URL 片段、`tests/` 内的 `abc…45` 假密钥），全部排除。

### D.2 补-01 ｜ 新增的门禁入口脚本自身未过 black，按其运行即首跑即红 —— **已消解，不计入统计**

- **Severity**: ~~中等~~ → **已消解（20:48 复核）**
- **消解取证**：`scripts/run_gates.py` mtime 已推进至 `2026-09-20 20:44:38`（本条于 20:2x 观测、20:3x 定稿，其后作者自行格式化）。20:48 复跑：
```
$ .venv/Scripts/python.exe -m black --check --line-length 120 --target-version py314 scripts/run_gates.py
1 file would be left unchanged.                              → rc=0
$ .venv/Scripts/python.exe -m black --check --line-length 120 --target-version py314 .
139 files would be left unchanged.                           → rc=0
```
  全仓 black 恢复通过，DoD 第 1 步重新可达，故本条**不计入统计**；下文保留原始观测记录以备审计（该缺陷存在约 20 分钟，属真实窗口，只是已在本报告定稿前被关闭）。
- **位置**：`scripts/run_gates.py`（2026-09-20 新增，AGENTS.md「格式化命令 · 本地一次性触发点」与「完成定义」第 1 步的事实入口）
- **实测**：
```
$ .venv/Scripts/python.exe -m black --check --line-length 120 --target-version py314 scripts/run_gates.py
would reformat scripts
un_gates.py            → rc=1
$ python scripts/run_gates.py --keep-going      → rc=1（7 项中 1 项失败，用时 19.1s）
  [FAIL] python -m black --check --diff --line-length 120 --target-version py314 .
```
- **说明与影响**：唯一未过 black 的自有文件正是**门禁执行器本身**。它未被纳入 `.venv`/排除清单，故全仓 `black --check .` 直接失败——意味着 CI 的 `Static Checks` job 在任何拉到该文件的分支上都会红，而失败原因与被审查的改动无关；同时 DoD 第 1 步「跑 `run_gates.py` 直到全绿」对**任何**改动都不可达成，使用者容易因此养成「忽略 black 失败」的习惯，恰与本仓「门禁不可掩盖」的取向相反。**修复**：`black scripts/run_gates.py` 一次即可；并建议在该文件合入前跑一次自身门禁（`run_gates.py --only black`）作为提交前自检。
- **置信度**：高（实跑）。

### D.3 补-02 ｜ MID-62 的 isort 盲区随新入口点原样继承

`run_gates.py` 按 AGENTS.md 逐字执行命令（其设计如此，正确），因此同样**不设置** UTF-8 模式：本次实测该次运行在 `[2/7] isort` 步骤仍输出 **16 条** `UserWarning: Unable to parse file …due to 'gbk' codec …`（含 `main.py`、`gui.py`、`web.py`、`build_exe.py`、`src/spider.py`、`src/stream_select.py`），且该步骤**未判失败**。结论：MID-62 的修复必须落在「命令文本 + 执行环境」层——在 `AGENTS.md`「格式化命令」里给 isort/black 两条加 `PYTHONUTF8=1` 前缀，或在 `run_gates.py` 内对子进程统一注入 `env["PYTHONUTF8"]="1"` 并把 stderr 出现 `Unable to parse file` 判为失败；只改执行器而不同步本节，会留下两份口径。**置信度：高（实跑）**。

### D.4 补-03 ｜ JS 签名脚本中两个文件已无任何调用点（死代码），且其一带有隐式全局

- **位置**：`src/javascript/laixiu.js`（33 行）、`src/javascript/taobao-sign.js`（78 行）
- **实测**：全仓 `*.py` 内出现这两个文件名的位置**只有** `src/utils.py:79/82` 的钉定表；来秀逻辑已在 `src/spider.py` 内以纯 Python `calculate_sign` 重写，淘宝签名无入口。`laixiu.js:26-29` 另有隐式全局：
```js
function sign(cryptoJSPath) {
    CryptoJS = require(cryptoJSPath);   // 无 var/let/const → 隐式全局
    return calculateSign();
}
```
- **说明与影响**：两份死代码连同钉定哈希一起长期留在仓库与 `_JS_SHA256_EXPECTED` 中：读代码者会误以为存在两条可用的签名链路；若将来有人经 execjs 载入 `laixiu.js`（非严格模式），其裸赋值将污染全局 `CryptoJS`。钉定表也因此在每次脚本变更时多两处无意义的更新点。**建议**：确认无用后连同 `_JS_SHA256_EXPECTED` 两条目一并删除；若保留则给 `CryptoJS` 加声明并在文件头注明「当前无调用点」。**置信度：高（实测 grep）**。
- **备注**：本条与 补-04 出自 JS 组审查结论，此前我在把 7 份分组结果并入统一编号时被遗漏，现按原文证据补登（不改变第三至五节既有编号）。

### D.5 补-04 ｜ 死代码文件的注释中留有疑似真实抓包样本（脱敏后记录）

- **位置**：`src/javascript/taobao-sign.js:76-77`
- **原文（取值已按本仓凭据红线改写）**：
```js
// 正确sign值：<32位hex>
// var sg =sign('<32位hex token>&<13位毫秒时间戳>&<数字id>&{"componentKey":"wp_pc_shop_basic_info",
//              "params":"{\"memberId\":\"b2b-<18位数字>a\"}"}')
```
- **说明与影响**：与 补-03 同源——该文件无人调用，但注释里保留了一组结构完整的真实请求入参（账号标识 + 时间戳 + 32 位会话令牌形态值），本仓分发的是仓库与二进制，随源码一并外发即把他人（或抓包者）的会话素材公开。属可一并清理的敏感残留，而非运行时漏洞。**建议**：随 补-03 一起删除该文件；若保留作为算法留档，则把示例入参替换为全零/占位值。**置信度：高（代码事实）/ 中（该样本是否仍有效未验证）**。

### D.6 补-05 ｜ 依赖仅有下限，声明区间覆盖已知受影响版本（当前安装值不受影响）

对照 2026 年公开公告（来源见本节末）逐项核验本仓三个清单口径：`requirements.txt`（镜像与 CI 实际消费）、`uv.lock`（随仓库分发但不被 pip 路径消费）、本机 venv 实测版本。

| 依赖 | 公告与受影响区间 | 本仓声明 | 锁/已装 | 判定 |
|---|---|---|---|---|
| `starlette` | CVE-2026-48710（BadHost：`Host` 头未校验 → 认证/缓存投毒类），受影响 **<= 1.0.0** | `>=0.49.1` | 1.6.0 / 1.6.0 | 当前不受影响；**但声明下限把 0.49.1–1.0.0 这段受影响版本留在合法安装区间内** |
| `python-multipart` | CVE-2026-24486（CWE-22，构造文件名写任意路径）修复于 **0.0.22**；CVE-2026-53537（RFC 2231 参数 smuggling，CWE-20/436）修复于 **0.0.30** | `>=0.0.32` | 0.0.32 | **两条均不受影响**，下限选择正确 |
| `urllib3`（`requests` 的传递依赖，**未出现在任何清单**） | CVE-2026-44431：跨域重定向时敏感头被转发，受影响 **1.23 – < 2.7.0** | 无（仅由 `requests>=2.34.2` 间接约束） | 2.8.0 | 当前不受影响；但**无任何下限保护**，重装/解析回退即可能落入受影响段 |
| `requests` | 2025 年的 `.netrc` 凭据外泄问题修复于 **2.32.4** | `>=2.34.2` | 2.34.2 | 不受影响 |

- **说明与影响**：本仓运行时清单刻意为「只有下限、无上限」（唯一例外是 `protobuf>=6.31.1,<8`），且 `uv.lock` 不参与镜像/CI 安装（AGENTS 已记为既定口径）。对可用性代价可以接受，但**安全代价**是：`pip install -r requirements.txt` 在不同日期/不同索引镜像下得到的集合不受约束，声明区间内还残留已知受影响版本（starlette 0.49.1–1.0.0）；而 `urllib3` 这类高价值传递依赖根本不在受控面上。本项的严重度定级为**中等**而非「已受攻击」：当前三种安装形态实测/推演均落在修复版本之上，风险是**下一次解析**时的回退，而非现网可利用缺陷。
- **建议**：① 把 `starlette` 下限提到受影响段之上（`>=1.0.1`），并同步 `pyproject` 与 `requirements.txt` 两处；② 为 `urllib3` 增加显式下限（`>=2.7.0`）——它虽为传递依赖，但本仓所有出站 HTTP 都经它；③ 更根本的做法：在 CI 增加一步 `pip-audit`（本地 venv 实测 `pip_audit`/`safety` **均未安装**，故本项无法在现有门禁内自动发现），或在 `build-release.yml` 里以 `uv sync --frozen` 走一次 `uv.lock` 使发布环境可复现。
- **置信度**：高（版本区间与公告逐项核对）。

### D.7 补-06 ｜ `AGENTS.md` 与外迁文档的链接关系在本轮审查期间反复变动，两态各有缺陷 —— **已消解，不计入统计**

- **Severity**: ~~轻微~~ → **已消解（20:48 复核）**
- **消解取证**（`AGENTS.md` mtime 已推进至 `2026-09-20 20:41:26`，`docs/agent-reference/measured-evidence.md` 为 `20:36:51`）：
  ① 入链恢复为 **4 条**且四条 destination 均**不含裸空格**（`#虎牙选档ratio` / `#斗鱼本地重试链` / `#探针客户端复用作用域` / `#禁止关掉探针客户端keepalive`），与 `measured-evidence.md:8/12/16/20` 四个实际标题逐字匹配 → 按 GFM slug 规则（小写、空格转连字符、CJK 保留）四条锚点**均可解析**；作者选择的是「标题与锚点同去空格」而非「锚点写成 `%20`」，两处一致即可，故本报告的原始建议 ① 已被更彻底的做法覆盖。
  ② `grep -c "。；" AGENTS.md` → **0**（三处句号叠分号残留清除，改写为 `；其实测数据见 …`）。
  ③ 本条第一态的「孤儿文档 / 双事实源」随入链恢复而消失。
  两点缺陷均已在报告定稿前关闭，故**不计入统计**；下文保留 20:21→20:34 的两态时间线，因为它记录的是「同一轮并行编辑会来回切换归属」这一流程风险，对本仓后续外迁仍有参考价值。
- **位置**：`AGENTS.md`（「HTTP 客户端复用与热路径性能」「画质档位与选源映射」共 4 处链接）、`docs/agent-reference/measured-evidence.md`
- **实测时间线**（同一会话内两次抓取，均为只读 `grep`）：

  | 时刻 | `AGENTS.md` 对 `measured-evidence.md` 的入链 | 该态暴露的问题 |
  |---|---|---|
  | 20:21–20:24 | **0 条**（文件存在、无人引用） | 外迁文档成为孤儿；同一批实测数值同时存在于根文件内联文本与该文档 → 出现第二份事实源，与「外迁以避免并行事实源」的约定相反 |
  | 20:34（复核时） | **4 条**（链接恢复） | 上项消失；但见下述两点 |

- **说明与影响（链接恢复态）**：① 4 条锚点中 `](docs/agent-reference/measured-evidence.md#虎牙选档 ratio)` **目的地址含裸空格**——CommonMark/GFM 在此处截断 destination，渲染端解析到的是 `#虎牙选档` 而非目标标题的 slug（`#虎牙选档-ratio`），该条链接点不开；另 3 条为纯中文锚点，可正常解析。这与新「可达性约定」所称「链接可被 `agent-lint` 机检」直接冲突，且此类缺陷只在浏览器/编辑器渲染时暴露，纯文本 grep 看不出来。② 恢复链接时留下了机械拼接残留 `。；其实测数据见 …`（3 处，句号叠分号），属外迁/回迁改写的痕迹型文案缺陷。
- **建议**：① 锚点统一改为无空格形态（`#虎牙选档-ratio`，或写成 `%20`），并把「链接 destination 不得含空格、锚点须按 GFM slug 规则生成」纳入 `agent-lint` 校验；② 一次性清掉 `。；` 残留；③ **确定唯一归属**——要么根文件内联 + 删除 `measured-evidence.md`，要么根文件只留链接 + 数值仅存于该文档，不要在同一轮里来回切换，否则每次切换都会重新制造本条第一态的孤儿/双源问题。**置信度：高（两态均实测）**。

### D.8 补扫后统计与既有编号的影响

| 项 | 变化 |
|---|---|
| 新增条目 | **计入 3 项**：补-05（中等）、补-03（轻微）、补-04（轻微）。**补-01（中等）与 补-06（轻微）在 20:48 复核中确认已由作者就地修复，标为已消解、不计入**（取证见 D.2/D.7）。补-02 为 MID-62 的追补证据，不单计 |
| 合计 | 严重 10 / 中等 70 / 轻微 26 = **106 项**（正文 103 + 附录 D 3） |
| 正文第三至五节 | 编号与结论不变；补-03/04 为分组结论并入时漏登项的回补，非新发现问题 |
| 清白色新增记录 | `src/weverse_auth.py` 的公开应用密钥（有 env 覆盖 + 注释说明）、`src/utils.py` 钉定表——已并入第九章「已核实不构成问题」的取证范围 |
| 统计口径说明 | 本报告的计数口径为「定稿时刻工作区实测状态」，而非「审查过程中出现过的缺陷总数」。补-01/补-06 在审查窗口内确曾存在（black rc=1、锚点含裸空格），但定稿前已关闭，故只留痕不计数——与第九章「已核实不构成问题」的处理方式一致 |


*报告结束。正文登记 103 项、附录 D 补扫增 3 项，合计 **106 项**（严重 10 / 中等 70 / 轻微 26），全部附 `文件:行号` 与原文片段；标「实测」者已由真实函数或对照实验复现；补-01/补-06 因定稿前已由作者修复而标为已消解、不计入（D.8）；凭据类取值一律以脱敏形式记录。*
