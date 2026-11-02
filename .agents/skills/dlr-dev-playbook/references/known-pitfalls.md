# 已知坑（避免回归）

> **唯一事实源仍是 `AGENTS.md`**。本文件从 `AGENTS.md`「已知坑」章节外迁，供按需查阅。
> 约束语句（must / must-not）以 `AGENTS.md` 为准；本文件展开事故背景、平台细节与验证命令。

---

## 录制链与房间线程主循环

- **录制链不得嵌套于 `if headers:` 内**: 录制主链必须位于条件判断**之外**，仅把「是否附加自定义头」作局部行为；用该条件包裹整条流程会导致无自定义头时静默不录制。
- **`real_url` 为空必须跳过录制链**: `select_source_url` 返回 None 时 `if not real_url: 告警+等待+continue`，否则 None 流入录制执行链崩溃或复用残留命令。守卫之后 `now`/`title_in_name` 为无条件赋值（移除恒真 `if real_url:` 包装）。
- **弹幕监控房间须随录制线程退出而移除**: `main.start_record` 在 outer try 的 `finally` 调 `get_hub().room_stopped(record_name)`（各 return 全覆盖），GUI `_danmaku_dispatch` 收到 `state=="stopped"` 后 pop 房间行；删掉该清理会残留失效直播间。
- **「已被注释」检查必须在解析之前**: 房间线程内层循环顶部（`exit_recording` 检查后）先查 `record_url in url_comments` 再进平台解析——原检查点在解析成功后，平台持续失败（风控空响应）时永远走不到，线程滞留占用监控位。
- **录制并发槽必须在 `Popen` 之前 acquire**（main.py::check_subprocess）: `recording_semaphore` 语义是限制同时进行 ffmpeg 数，先起进程再 acquire 则上限根本不约束 ffmpeg 进程数（资源耗尽）。结构：「`acquire` → `try:`（`Popen`+注册+弹幕启动+主循环）→ `finally: release`」，**启动段也必须落 `try` 内**，抛错同样归还槽位否则泄漏累积饿死所有后续录制。
- **录后自定义脚本（`src/notify.py`）的命令原文进日志前必须脱敏，超时回收必须处理孙进程**: 用户脚本常内嵌 rclone token / curl 的 Authorization / 数据库口令，而 `logs/` 轮转保留多份＝凭据长期落盘，故四条失败分支的 command 与异常文本一律过 `utils.mask_credentials`。超时 `kill()` 只杀直接子进程，孙进程握着管道写端会让**第二次无超时的 `communicate()` 永久挂住**录后钩子线程——第二次读必须带超时；进程树回收 POSIX 走 `start_new_session` + `killpg`、Windows 走 `taskkill /T /F`（一律 argv 列表，禁 `shell=True`），任一步失败退化到原来的 `kill` 且不改写结果。回归锁 `tests/test_notify_script_guard.py`。

## 流地址探针与可达性校验

> 完整流程与操作步骤见 `.agents/skills/dlr-domain-constraints/SKILL.md`。以下为本节硬约束摘要。

- **GET 复核容错不得简化**: 401/403 先原样重试一次再定罪；末位候选仅告警放行交 ffmpeg 定夺。
- **虎牙探针退避仅限 `_PROBE_BACKOFF_PLATFORMS`**: 绝不可把斗鱼等加入名单。
- **虎牙 FLV-first（`_FLV_FIRST_PLATFORMS`），斗鱼绝不加入**: 斗鱼游客态 FLV ~70s 被掐必须 HLS 优先。
- **探针退避窗口 ≥ 一个主循环周期**: 不可改回固定 60s 常量。
- **UA 双端一字不差**: 改字符串须同步四处（`MOBILE_UA`/ffmpeg UA/`room.HEADERS`/B站 H5 UA）。
- **探针节流/抖动不得移除**: 改为固定值或移除会重引风控误伤。
- **探测方法基线**: HEAD 非 2xx → Range GET bytes=0-0（200/206 判可达），不要只覆盖 400/401/403/405。
- **「HLS 采集排除平台」与「FLV-first 调序」两种语义不可互实现**: 回归锁 `tests/test_stream_select.py`。
- **重定向逐跳复检只有两个合法接线点，新增第三处自建客户端即视为漏防**: 异步侧 `async_http._build_client`（response 事件钩子）、同步侧 `stream_select._probe_client` 工厂（2026-09-30 补齐：此前同步探针**连初始 URL 的内网判定都没有**，只有 `_is_recordable_url` 的协议形态白名单，它挡 `file://`/`concat:` 却不挡 `http://127.0.0.1:6379`）。两处判定一律复用 `async_http` 的同一份 helper，禁止在 stream_select 另写 urlparse/内网名单。钩子触发时机在该跳响应头已收到之后，闭合的是「不再跟随 + 响应不外流」，**不是**「不建连」；DNS 重绑定窗口本层不闭合，且**不得**给判定结果加缓存（缓存会把一次解析供给所有跳，主动拉长窗口）。复用形态不得回退：作用域仍是单次选源、不按 `(proxy, verify)` 做模块级全局缓存、不关 keepalive、`utils.handle_proxy_addr` 的归一仍只在构造客户端之前那一处。回归锁 `tests/test_regression_2026_09_29_wp_b_netguard.py` + `tests/test_sync_probe_internal_guard.py`（含 AST 结构锁：构造点唯一 + `event_hooks` 实参必须来自同步钩子工厂）。
- **「响应决定 URL」的落地页一律双闸，且拼出的下游主机须再过一次白名单**: 小红书 SEV-2214 与 Shopee（S-1）同型——① 域族白名单用 `urlparse().hostname` 做「精确等于或 `.` 后缀」判定并拒 userinfo；② `web_config._host_internal_reason` 判内网/回环/云元数据/CGNAT/缩写 IP。任一条不过即**丢弃跳转、保留用户自填的原始 url、并剥离 Cookie**。准入白名单只约束短链宿主，绝不等于约束落地页；由 `host_suffix` 拼出的 `api_host` 是第二处暴露面，发出带凭据请求前必须复验。
- **`sync_http` 的 opener 必须显式按协议白名单构造**: 不得用默认 `build_opener`（自带 FileHandler/FTPHandler/DataHandler，`file://` 即读本地文件），`HTTPSHandler` 是**必填实参**（放默认列表再补会出两支、降级语义被默认那支吃掉）。abroad 分支走进程全局 `urlopen`，只能做事后落地复核——该分支**不得**改 `install_opener`（会波及全进程）。
- **小红书链接形态与判据唯一入口**（2026-10-04）: 四类形态（`/livestream/<数字房间ID>`、`/livestream/<动态段>/<数字房间ID>`、`xhslink.com/o/<短码>`、`/user/profile/<id>`）一律经 `src/spider.py::parse_xhs_live_url`，**不得**在别处重写路径切分或 `re.search` 抠参数。硬约束：① host 精确等于 `www.xiaohongshu.com` / `xhslink.com`（后缀伪装、尾部点、userinfo 伪装、路径里出现域名词全拒），与 `_XHS_ALLOWED_HOST_SUFFIXES`（管落地页能否带凭据，须容纳 CDN 子域）分工不同，**不得**互相替代；② 房间 ID 判 ASCII 数字（`[0-9]+`，**不得**用 `\d+`，会放行全角数字），动态段/短码/主页 ID 只收 `[A-Za-z0-9_-]+`（点段与 `%2e%2e` 不进规范 URL）；③ 动态段原样保留，**不得**折叠成标准路径（删掉后页面未必可访问）；④ query 白名单只留 `host_id` / `xsec_token` / `xsec_source`——`xsec_token` 是页面鉴权参数，**不得**当噪声剥掉（旧 `&host_id=` 正则两个洞：只认 `&` 前缀的首参数形态、连鉴权参数一起剥）；⑤ `XhsUrlError` 带稳定 `code`，消息**不得**回显原始 URL / query / path。回归锁 `tests/test_xhs_live_links.py`（含短链安全边界与 `start_record` 录制启动集成）。
- **小红书未开播轮必须能建起监控作业**: 主播名读 `liveStream.roomData.hostInfo.nickName`（该字段在 `liveStatus="end"` 时依然存在，实测 2026-10-04），**不得**只从 `roomInfo.deeplink` 抠 `host_nickname`（那是开播态字段）——否则标准链接在等待开播的每一轮都拿不到 `anchor_name`，`start_record` 判「网址内容获取成功」并持续重试。仍取不到时用 `小红书_<room_id>` 兜底，**不得**对空 `user_id` 请求 `/user/profile/None`。`port_info["error"]` 必须在 `_resolve_xhslink_com` 转成告警 + `ctx.unrecognized`，不得与「主播没开播」混同空转；短链规范地址经 `new_record_url` 通道回写配置，**不得**在 URL 配置准入阶段解跳转（一次网络抖动就会改写用户配置）。

## 弹幕采集与 SRT 写入

- **弹幕 WS 连接必须显式 `proxy=None`**（src/ws_client.py::connect）: 使 WebSocket 直连不跟随系统代理，否则 B站/斗鱼等报 `connecting through a SOCKS proxy requires python-socks` 连接即断。改动须保留 `proxy=None`。
- **B站弹幕 buvid 必须真实、AUTH_REPLY 必须显式校验**: spi 端点是 `/x/frontend/finger/spi`（少写结尾 `i` 会 200+空 body 永远 JSONDecodeError）；buvid 获取链按真实注册标识优先排序（进程缓存→cookie `buvid3=`→spi→`www.bilibili.com` 首页 Set-Cookie→随机 UUID 兜底标记 is_fallback）。`_decode_packet` 须校验 operation=8 回应的 code：非 0 经 `_reject_auth()` 告警+断开+`spider.invalidate_bili_buvid_cache()`；`_auth_watchdog` 兜底「服务器 8s 不回 AUTH_REPLY 的静默拒绝」。
- **`collector.stop()` 与采集线程握手顺序不可单独调整**（src/collector.py）: `stop()` 必须先 `set(self._stop_event)` 再读 `self._loop`；`_run()` 必须先发布 `self._loop` 再检查 `self._stop_event`（两相反顺序保证信号必被一方接收）。缺一半会丢信号致 `join(timeout=8)` 超时、线程与 SRT 句柄双泄漏。另：`_shutdown` 中 `await danmaku.stop()` 必须 `asyncio.wait_for` 限时（`_SHUTDOWN_TIMEOUT_SECONDS`），否则 SDK 半开连接挂住 `loop.stop()` 永不执行。
- **弹幕文本写入 SRT 前必须转义**（src/srt_writer.py::_sanitize_srt_text）: `user_name`/`message` 为外部可控输入，含 `\n` 截断 SRT 块、含 `-->` 被解析成新时间轴行可伪造字幕。替换（非删除）为可见字符。回归锁：注入 `normal\n2\n00:00:99,000 --> 00:00:99,999\nFAKE\n` 后产物必须仍只有 1 个块 1 条时间轴。片内 `end` 须 `max(start, min(end, _seg_seconds))` 钳制。
- **弹幕链路接线点与分段命名约定**: `start_record` 各平台解析分支只填 `ctx.record_danmaku_args`（现 60 处赋值，2026-10-17 复测口径 `grep -c 'record_danmaku_args = ' main.py`）→ 唯一调用点 `main.py` 内 `comment_end = check_subprocess(...)`（按锚点引用，行号随文件增删漂移）的 `check_subprocess(..., platform=platform, danmaku_args=record_danmaku_args)` → `src/__init__.py::get_danmaku_collector(platform, args, base_filename, segment_seconds)`（实现在 `src/collector.py`）。硬约束：① `danmaku_collector.stop()` 必须在 `while process.poll() is None` 循环之外（`DanmakuCollector.stop()` 有 `_stop_called` 防重入幂等）；② 分段文件名——视频 `_%03d`（FLV 已从 `_%02d` 对齐；音频仍 `_%02d`）、SRT `{seg:03d}` 与之对应，`check_subprocess` 需同时剥离两种占位符；③ 抖音弹幕空 cookie 时在 `DouyinDanmaku.start()` 协程内 `await get_ttwid()` 动态获取（不再硬编码 ttwid）。配置项 `弹幕分片时长(秒)` 走 `_safe_float(..., 1800.0)`。
- **抖音弹幕 `signature` 保持不编码，禁止顺手加 `quote()`**（F-13）: XBogus 字符表含 `+`/`/`，但上游确认直接拼接不 encodeComponent、服务端不按 form-urlencoded 把 `+` 解成空格。改编码会让本端成为唯一异类指纹。回归锁：`tests/test_douyin_signature_encoding.py`。
- **B站弹幕 host 轮换的关闭回调必须走 `BilibiliDanmaku._report_close` 闸门**: 仍有候选 host 未尝试时属轮换中间态（转 `_on_reconnect` 留 debug），候选排空或已进入 `_stopped` 终态才向 hub 上报且**恰好一次**；`start()` 进入每个 host 前登记剩余候选数、循环结束必须归零，否则会话期之后的真实断连会被吞（回归锁 `tests/test_bili_host_rotation.py`）。不得为此新增 i18n msgid——`tests/test_i18n_migration.py::test_runtime_templates_covered_by_catalog` 是硬门禁，新增裸 `logger.debug` 文案会当场红。

## 平台接口、签名与流地址解析

- **斗鱼必须附带 FLV→m3u8 同 token HLS 候选**: 斗鱼 H5 只返 FLV，游客态 FLV 长连接 ~70s 被掐；wsAuth token 对 FLV/HLS 通用，把路径 `.flv` 改 `.m3u8` 即同 token HLS（hw CDN 200+mpegurl）。该候选由 `select_source_url` 校验 gating、不可达自动回退 FLV，须保留。
- **migu.js 输出契约为完整签名 URL**；`src/javascript/` 的**文件增删必须与 `utils._JS_SHA256_EXPECTED` 同批提交**（2026-09-26 CI 实测坑）：`tests/test_utils.py::TestJsPinTable::test_every_executable_js_is_pinned` 断言「目录里每个 `.js` == 钉定表键集」双向相等，删除脚本却没推送 `.js` 本体（或反之）会让 CI 红，而本地已删的工作区全绿——本地与远端内容不一致时**只信远端**。`src/javascript/migu.js` 适配 migu 播放器 v_20260731+ wasm 接口（12 个导入函数、导出名重排），输出带 `ddCalcu`/`sv` 参数的完整地址（`sv` 失败回退内置默认因子）；`spider.get_migu_stream_url` 直接使用，不再拼接过期 `sv=10010`。
- **抖音接口风控信号是「HTTP 200 + 空响应体」不是 4xx**: 解析失败先看 `len(response.text)`，为 0 基本是 UA/Cookie 被拒。三条配套：① UA 敏感——`src/room.py` 模块级 `HEADERS` 是 2020 三星安卓 UA，`iesdouyin.com/web/api/v2/user/info/` 用它必被静默拒，此类接口一律用 `room.DESKTOP_UA`；② `iesdouyin.com/share/user/<sec_uid>` 已是 JS 反爬壳页，取 `unique_id` 请走 `https://www.iesdouyin.com/web/api/v2/user/info/?sec_uid=<sec_uid>`；③ `webcast.amemv.com/webcast/room/reflow/info/` 用占位 `room_id=2`+`sec_user_id` 解析主页行不通（status_code=10011）。
- **`live.douyin.com` 的 `web_rid` 同时接受数字房间号与抖音号**: `webcast/room/web/enter/` 两者皆可，`live.douyin.com/<抖音号>` 不重定向。**不要写「抖音号需先重定向解析成数字」的逻辑**（已被实测证伪并删除）。`main.py` 以 `port_info["anchor_name"]` 为空作「网址内容获取失败」判据。
- **`hevc_flv_url` 必须带 `codec=h265` 标记**（src/spider.py::extract_douyin_hevc_flv_url）: 正则抠出的 HEVC 地址必须补 `&codec=h265`（已带则原样返回）。下游 `_is_h265()`/`main.py` 的 h265 兜底**只认 URL 上的 codec 查询参数**。注意 `utils.get_query_params` 返回 **list**（`spider.get_params` 返回 str，不可混用）。
- **斗鱼房间号提取只认数字，且新域名必须两处同时登记**（2026-10-03 接入 `m.douyu.com` 时定稿）: 提取走 `spider.extract_douyu_rid_param()`（锚定 `[?&]rid=`，值非数字时**不作数**、回落路径首段）与 `spider.extract_douyu_room_id()`（`urlsplit` 取路径**首个非空段**，天然剥掉尾斜杠 / query / fragment，scheme 无关；无 scheme 时按准入侧同一规则补 `https://`，否则首段取到的是主机名）。取代的两处整串正则各有洞：`rid=(.*?)(?=&|$)` 会被 `?xyzrid=123` 误命中，`douyu.com/(.*?)(?=\?|$)` 会把尾斜杠与后续路径段带进房间号（`/8751648/` → `8751648/`）→ `betard` 拿不到 room、用户只看到「房间不存在」这类误导。字母号仍走移动端 `vike_pageContext` 还原，**还原产物非数字必须在还原出口报错**（`betard` / `getH5PlayV1` 只吃数字 rid）。新增斗鱼域名须**同时**登记 `main.py` 的 `PLATFORM_HOST` 与分发表匹配片段：缺前者链接在读取 URL 配置阶段就被判「未知链接」并注释掉，缺后者落入 `_resolve_unrecognized` 无限空转（SEV-2203 同型）。另：往分发表**插入**表项会挪动其后所有下标，`tests/test_platform_dispatch.py::test_resolver_table_priority_head` 的顺序锁必须同步改。

## 画质档位与选源映射

> 完整流程与操作步骤见 `.agents/skills/dlr-domain-constraints/SKILL.md`「画质档位映射」章。以下为本节硬约束摘要。

- **蓝光子档位折叠到 BD 索引，不得塞进 `QUALITY_MAPPING`**: 中文映射新增须同步四处（`get_quality_code`/`web_config.QUALITY_KEYWORDS`/`main.py` 白名单/`web/index.html`）。
- **虎牙选档不可抛异常或返回空流地址**: 不可用时就近降级或回原画，保持 `is_live=True` 契约。
- **斗鱼本地重试链最多回退 2 档**: 全部失败保持 `is_live=True`，不得替代 HLS 候选与全局退避。
- **选档一律「保留原始请求索引 + FLV/HLS 双列表各自钳制」**: 不得把一侧钳过的下标写回共享变量再供另一侧复用——TikTok 曾因此对 HLS-only 房间恒取首档，且 `actual_quality` 回采 OD 后降级告警永不触发（「选流畅实拉原画」无提示）。参照 `src/stream.py` 抖音分支的 `flv_idx`/`m3u8_idx` 与修复后的 `flv_quality_index`/`m3u8_quality_index`（回归锁 `tests/test_tiktok_hls_quality_index.py`）。回退/探针失败重算分支同样不得复用被钳值。
- **抖音原画 hevc 替换必须把被替换的 h264 FLV 存入 `flv_url_list`**: 原画请求且接口下发 `hevc_flv_url` 时，选源层在保存格式不支持 HEVC 直拷时会把 `codec=h265` 候选在探针前剔除（TS/MKV/MP4 已放行，见下条），不保留 h264 原画备选则「HLS 采集关闭 / m3u8 缺席」+ FLV/音频格式的原画 hevc 房过滤后零可用候选、每轮「本轮无可用源」永不录制（2026-10-01 两间房实测）。与 hevc 地址逐字相同或自带 `codec=h265` 标记的条目不得收进备选（同样会被剔，徒增告警）。回归锁 `tests/test_stream.py::TestGetDouyinStreamUrl` + `tests/test_stream_select.py::test_select_source_url_h265_flv_falls_back_to_h264_from_list`。
- **h265 候选按保存格式放行（`_h265_copy_format_supported`）**: TS/MKV/MP4 三种容器可直拷 HEVC（main.py 选中 h265 地址时强制转 TS 是同一事实），此时 h265 候选进常规序列按序参与探针；FLV（HEVC-in-FLV 属 Enhanced-FLV 扩展、仓库口径不支持）、MP3/M4A 纯音频、域外/缺失取值仍一律剔除（保守默认）。判定读 main 的热更新全局 `video_save_type`（与 `_hls_selection_config` 同模式），改允许集须同步核实 `_EXTENSION_BY_SAVE_TYPE`/`SEGMENT_FORMAT_BY_SUFFIX` 的容器能力；main.py 的 h265→TS 强制块带同一口径守卫（已是 TS/MKV/MP4 不接管、不打「use TS format instead」）。回归锁 `tests/test_stream_select.py` 的 h265×保存格式双矩阵与 `test_h265_copy_format_supported_matrix`。
- **HLS 配置静默丢弃导致无源必须点名**: m3u8 候选被「是否启用HLS采集(是/否)/HLS采集排除平台(逗号分隔)」整组静默剔除且本轮最终无可用源时，选源结论前必须补一条带候选条数与恢复开关指引的告警——这是唯一「零日志」的选源成因（有 FLV/record_url 兜底时早退告警不触发）；选中源的轮次不得打（健康轮零噪音）。回归锁 `tests/test_stream_select.py::test_select_source_url_warns_dropped_hls_when_no_source` + `test_no_dropped_hls_warning_when_source_found`。

## HTTP 客户端复用与连接管理

- **httpx 请求级 headers 是「合并」不是「替换」**: 把 UA/Referer/Cookie 挂 client 级时，只传 `{"Range": "bytes=0-0"}` 的请求仍带全部 client 级头——不要据此判「丢了请求头」。但客户端一旦在多个候选间复用（select_source_url 整轮共用一支），业务头绝不能再挂 client 级（候选间互相污染），必须逐请求显式传入。
- **探针客户端复用作用域 = 单次选源，禁止升级为全局缓存**: `_validate_stream_url` 新增可选 `client` 参数（不传时自建自管）；刻意不做按 `(proxy, verify)` 模块级全局缓存（虎牙 CDN 按连接预算限流，常驻 keepalive 会与 ffmpeg 拉流争抢）。
- **禁止为「保险」关掉探针客户端 keepalive**: 会把复用收益全部退掉；排查虎牙 403 应临时改回「每候选一支 Client」。
- **`requests.Session` 必须线程级复用，禁止每次新建**（src/sync_http.py）: `_session()` 经 `threading.local()` 缓存（Session 非线程安全不可跨线程共享）。改回每次新建会让每次出站多一轮 TCP+TLS 握手（退化幅度本机读数见 `docs/agent-reference/measured-evidence.md`「`sync_http` 线程级 Session 复用的收益读数」）。`tests/test_sync_http.py` 的代理替身 patch 目标须是 `src.sync_http._session` 不是 `src.sync_http.requests`。**注意**：该模块当前无生产 importer（sync_req 调用点现只剩 tests/），保留是因为 requests 仍在运行时清单且 8× 复用结论成立——任何「已经吃到这个收益」的表述不得再写。
- **`sync_req` 的 SSL 降级路径必须保持惰性+单次覆盖**（F-12）: CERT_NONE 上下文与 opener 由 `_get_insecure_context()`/`_get_insecure_opener()` 按需构造，禁止改回模块级常驻。「无调用者」只是当下状态，不作为放宽惰性要求的理由。
- **出站响应体读取一律带上限，异步侧的上限只有 `_build_client` 那一处接线点**（2026-10-18 定稿，CODE_REVIEW M-03/M-04/L-11）：三条读取链各有自己的上限形态——① 异步主路径 `async_http._bounded_response_read`（挂在 `_build_client` 的**唯一** response 钩子内）；② 同步侧 `sync_http._read_capped`（含 400 错误体分支）；③ 探针 `stream_select._bounded_probe_get`（可达性判定只需少量确认）。硬约束四条：**不得**为异步侧新建第二支 response 钩子或第二支客户端；8 MB / 32 MB 两个取值与同步侧**同值但各存一份**；超限时走**既有失败出口**；新增任何出站读取点必须落进同一上限体系。回归锁：`tests/test_async_http.py::TestBoundedResponseRead`/`TestAsyncReqCapEndToEnd`、`tests/test_sync_http.py::test_http_error_400_oversized_body_hits_read_cap`、`tests/test_stream_select.py` 的探针限量组。**读取点本身另有台账锁**：`tests/test_outbound_read_caps.py` 按 `(文件, 函数)` 双向相等枚举。

## 并发、事件循环与锁

- **`asyncio.get_event_loop()` 3.14 起不再隐式创建事件循环**: 当前线程无循环时抛 RuntimeError。`src/async_http.py::close_all_clients_sync` 已改为捕获 RuntimeError 走引用清理兜底；协程内获取循环一律 `get_running_loop()`。
- **跨事件循环禁止创建/调度旧 AsyncClient 的 aclose 协程**（src/async_http.py::_get_client）: 淘汰他循环创建的旧客户端时一律**不创建** `aclose()` 协程，释放引用交 GC 兜底。回归锁：`tests/test_async_http_lock.py::test_cross_loop_running_old_loop_skips_close`/`test_cross_loop_stopped_old_loop_skips_close`。
- **熔断计数必须增量、不得 `sum(deque)`；`import time` 提顶层**（src/scheduler.py）。
- **「调用方持锁」改「内部自持锁」必须同步清调用点外层锁**: 约定：函数要么只内部加锁、要么只由调用方加锁，二选一并在注释写明；改造其一必须 `grep` 全部调用点。
- **可重入性判定一律以源码定义行为为准**: 不要把文档清单当推断依据。改动前必须 `grep` 定义行确认。历史分类快照见 `docs/agent-reference/lock-classification.md`。
- **Qt 的 GUI 线程必须是主线程；禁止给 Tk 进程塞第二个工具包**（2026-10-20 定论）: `QApplication` 只能在主线程构造。
- **`QDialog` 是顶层窗口，父窗隐藏不影响它显示**。

## ffmpeg 命令构造与容器格式

> 完整流程、事故背景与验证命令见 `.agents/skills/dlr-domain-constraints/SKILL.md`。

- **`-reconnect*` 必须在 `-i` 之前且紧跟取值**: 写在 `-i` 之后被静默忽略。HLS 输入必须移除 `-reconnect_at_eof`。回归锁：`tests/test_ffmpeg_reconnect_args.py`。
- **`-thread_queue_size` 只能位于 `-i` 之后**: 放错侧致录制 100% 失败。
- **`-segment_format` 一律经 `SEGMENT_FORMAT_BY_SUFFIX` 查表**: 禁止任何分支直接写字面量。回归锁：`tests/test_record_container.py`。
- **命令构造统一到四个单一定义点（F-01）**: ① `_build_ffmpeg_input_args` ② `_build_record_output_path` ③ `_run_ffmpeg_record`+`_convert_after_record` ④ `_PLATFORM_RESOLVERS`+`_PlatformResolveContext`。禁止各平台分支手写 `command=[...]`。回归锁：`tests/test_platform_dispatch.py`+`tests/test_start_record_command_golden.py`。

## 日志、控制台与 GUI / 后台模式

- **Web 后台模式必须重建 loguru 控制台 sink**（web.py::_enter_background_mode）。
- **GUI 父进程绝不持有录制日志文件句柄（`DLR_GUI_PARENT` 标记）**。
- **异常日志必须带异常类型与上下文，禁止裸 `logger.xxx(e)`**。
- **无控制台环境 `sys.stderr is None`，`logger.add` 前必须判空**（src/logger.py）。
- **多房间交织日志靠 `extra[room]` 列切出**（src/logger.py::ROOM_FIELD）。
- **GUI 控件层一律走 `src/ui_kit` 工厂且颜色不进工厂**。
- **Web 托盘走 QSystemTrayIcon，主线程必须交给 Qt 事件循环**。

> 各条详细事故背景与回归锁清单见原 `AGENTS.md` 2026-10 版本。

## i18n 文案、目录与占位符

- **i18n 多格式目录与语言热切换**: `.mo`→`.json`→`.yaml` 优先级。
- **形参日志必须走 `i18n.tr(模板, **kw)`，禁止 f-string**。
- **测试必须冻结翻译为恒等映射**。
- **`tr()` 的两层 except 必须含 `AttributeError, TypeError`**。
- **GUI 静态标签走 `T()` 登记表，语言切换必须整窗回填**。

> 各条详细占位符规则、门禁判据与 Qt 模式差异见原 `AGENTS.md` 2026-10 版本。

## 配置键名、布尔口径与 SSL 验证

- **「禁用SSL证书验证的平台」仅在需要证书校验时生效**。
- **缺键补写必须幂等**。
- **读取侧容错层**（`src/config_read.py`）。
- **config.ini 键名禁止含 `=`/`:` 等 configparser 分隔符**。
- **布尔配置统一到 `src/config_bool.py`**。

> 各条详细接线点与回归锁清单见原 `AGENTS.md` 2026-10 版本。

## 凭据与敏感配置脱敏

- **出站链路的异常文本进日志前必须过 `utils.mask_credentials`，存量以棘轮只降不升**。
- **敏感配置判定必须「节白名单 + 键名正则」双重**。

## 类型检查、注释与静态门禁

- **PEP 758 `except A, B:` 在 3.14 合法**。
- **protoc 生成模块需手写 `.pyi` 存根**。
- **平台专属符号必须 `sys.platform` 字面量门控**。
- **`[tool.mypy].exclude` 的运行时二进制目录条目必须写目录段锚定形态**。

> 各条详细门禁与回归锁清单见原 `AGENTS.md` 2026-10 版本。

## 热路径性能

- **主循环去重容器必须为 `set`**。
- **高频正则提模块级常量、按 key 缓存**。

## 构建产物、依赖与运行时基线

- **Node 24 / FFmpeg 9.0 兼容基线**。
- **发布链运行时二进制必须 fail-closed 钉定（SEV-10）**。
- **`make_zip` 的产物名一律整体 f-string 拼接**。
- **打包图标的 `EXE(icon=)` 与 `datas` 是两条独立通道**。

> 各条详细钉定流程与回归锁清单见原 `AGENTS.md` 2026-10 版本及 `.agents/skills/dlr-domain-constraints/SKILL.md`。

## 装饰器与平台兜底契约

- **装饰器与 `def` 之间的注释会让装饰器绑到下一个 `def`**。
- **平台解析函数返回契约必须匹配兜底装饰器**。
- **spider.py 平台解析一律走 `_loads_dict`+`_dig/_dig_str/_list`**。

## Web / GUI 面板与接口层

- **Web 后端已从 FastAPI 迁移到 Starlette 直接驱动**。
- **GUI 窗口层已迁到 PySide6（Qt6）**。
- **托盘 / 面板图标必须走 `src/ui_icons.py` 单点解析**。

> 各条详细接线约束与回归锁清单见原 `AGENTS.md` 2026-10 版本。

## 测试质量与审查协作流程

- **测试不得自实现被测逻辑（假绿）**。
- **探测子进程输出一律按字节比较**。
- **平台专属分支的测试不得靠 `skipif` 让 CI 跳过**。
- **修复后必须运行受影响测试并保留 relevant-check 证据**。

> 各条详细判据与回归锁清单见原 `AGENTS.md` 2026-10 版本。
