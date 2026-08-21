# AGENTS.md — DouyinLiveRecorder 核心约定

> 本文件供编码代理（Copilot / Cursor / Qoder 等）快速消费，汇总项目关键约定。

## 项目概览

- **名称**: DouyinLiveRecorder
- **版本**: 4.0.8.3（唯一事实源：`pyproject.toml` 的 `version` 字段。`main.py` 与 `src/web_api.py` 运行时经 `importlib.metadata` 动态读取；`Dockerfile` 经 `APP_VERSION` 构建参数动态注入；`i18n/zh_CN/LC_MESSAGES/zh_CN.po` 不再携带版本号。`README.md` / `CODE_WIKI.md` 为文档，不再纳入版本同步/校验。）
- **描述**: 支持抖音、TikTok、YouTube、快手等 60+ 平台的直播录制工具
- **许可证**: MIT

## Python 版本

- **最低要求**: Python >= 3.10
- **目标版本**: py310, py311, py312, py313
- **mypy 检查版本**: 3.10

## 代码风格

### Black

```toml
line-length = 120
target-version = ['py310', 'py311', 'py312', 'py313']
include = '\.pyi?$'
```

排除目录: `.git`, `.venv`, `build`, `dist`, `__pycache__`, `.pyc`, `node`, `ffmpeg`, `downloads`, `logs`

### isort

```toml
profile = "black"
line_length = 120
known_first_party = ["src", "i18n"]
```

排除目录: `.git`, `node`, `ffmpeg`, `downloads`, `__pycache__`, `*.pyc`

### mypy

```toml
python_version = "3.10"
warn_return_any = true
warn_unused_configs = true
disallow_untyped_defs = true
ignore_missing_imports = true
```

## 项目结构

```
项目根目录/
├── main.py              # CLI 录制入口（douyin-recorder）
├── gui.py               # GUI 入口（douyin-recorder-gui）
├── gui_legacy.py         # 旧版 GUI 入口
├── web.py               # Web 管理面板入口（douyin-recorder-web）
├── i18n.py              # 国际化模块
├── msg_push.py          # 消息推送模块
├── build_exe.py         # PyInstaller 打包脚本
├── pyproject.toml       # 项目元数据 + 工具配置
├── requirements.txt     # 运行时依赖（与 pyproject.toml 同步）
│
├── src/                 # 核心源码包
│   ├── __init__.py
│   ├── room.py          # 直播间管理
│   ├── spider.py        # 平台爬虫/流地址解析
│   ├── stream.py        # 流录制逻辑
│   ├── async_http.py    # 异步 HTTP 客户端
│   ├── sync_http.py     # 同步 HTTP 请求
│   ├── http_config.py   # HTTP 配置
│   ├── logger.py        # 日志（loguru）
│   ├── utils.py         # 工具函数
│   ├── proxy.py         # 代理支持
│   ├── ttwid.py         # 抖音 ttwid 获取
│   ├── ab_sign.py       # AB 签名
│   ├── web_api.py       # FastAPI Web API
│   ├── web_config.py    # Web 配置
│   ├── web_tray.py      # Web 托盘
│   ├── weverse_auth.py  # Weverse 认证
│   ├── ffmpeg_install.py # FFmpeg 自动安装
│   ├── node_install.py  # Node.js 自动安装
│   └── javascript/      # JS 签名脚本（各平台）
│
├── config/              # 运行时配置（exe 同级）
│   ├── config.ini       # 主配置
│   └── URL_config.ini   # 直播间 URL 配置
│
├── web/                 # Web 面板前端静态资源
│   ├── index.html
│   ├── app.js
│   └── style.css
│
├── i18n/                # 翻译目录（多语言多格式）
│   ├── zh_CN/LC_MESSAGES/  # 简体中文（gettext .po 源 + 编译 .mo）
│   ├── en_US.json          # 英语（美国）目录（JSON 格式）
│   ├── en_GB.json          # 英语（英国）目录（JSON 格式）
│   └── zh_TW.yaml          # 繁体中文目录（YAML 格式）
│
├── ffmpeg/              # FFmpeg 运行时（自动下载）
├── node/                # Node.js 运行时（自动下载）
├── typings/             # 第三方库类型存根
│   ├── customtkinter/   # customtkinter 类型存根（__init__.pyi）
│   ├── execjs/          # PyExecJS 类型存根（多个 .pyi）
│   └── pystray/         # pystray 类型存根（__init__.pyi）
└── .github/workflows/   # CI/CD（GitHub Actions 构建发布）
```

## 入口点

| 命令 | 模块 | 说明 |
|------|------|------|
| `douyin-recorder` | `main:main` | CLI 录制核心 |
| `douyin-recorder-gui` | `gui:main` | 图形界面 |
| `douyin-recorder-web` | `web:main` | Web 管理面板 |

## 依赖管理

- **运行时依赖**: `pyproject.toml` `[project.dependencies]` 与 `requirements.txt` 保持同步
- **开发依赖**: `pip install .[dev]`（pytest, black, isort, mypy）
- **构建依赖**: `pip install .[build]`（PyInstaller >= 6.10.0）
- **GUI 依赖**: `pip install .[gui]`（customtkinter, pystray, Pillow）
- **i18n 依赖**: PyYAML（zh_TW.yaml 目录加载；缺失时仅损失 YAML 格式，JSON/gettext 不受影响）

## 测试

```toml
testpaths = ["tests"]
python_files = ["test_*.py"]
python_classes = ["Test*"]
python_functions = ["test_*"]
asyncio_mode = "auto"
```

- 测试目录: `tests/`
- 运行测试: `pytest`
- **tests/ 质量门禁（2026-08 起全绿，须保持）**: `pytest`（0 警告）、`black --check tests/`、`isort --check-only tests/`、`mypy tests/`、`basedpyright tests/`（0 error/0 warning）
- 覆盖率源码: `src/`
- 覆盖率排除: `tests/`, `__pycache__/`, `node/`, `ffmpeg/`
- 逐模块覆盖率门禁: `python scripts/check_coverage.py`（CI 自动执行，阈值定义见脚本 `MODULE_THRESHOLDS`）
- 并发测试专用覆盖率配置: `.coveragerc-concurrency`（随仓库分发，CI 经 `COVERAGE_RCFILE` 引用，`fail_under = 0`）
- 创建/更新测试: 使用 [test-creator Skill](.qoder/skills/test-creator/SKILL.md) 标准化流程（源码分析 → Mock 配置 → 验证执行）

## 构建命令

```bash
# 安装依赖
pip install -r requirements.txt

# 打包可执行文件
python build_exe.py              # 标准打包
python build_exe.py --smoke      # 打包 + 冒烟测试
python build_exe.py --no-zip     # 只打包不压缩
python build_exe.py --no-runtime # 跳过 ffmpeg/node（减小体积）
python build_exe.py --dual       # 同时生成 lite + full 两个 zip

# Docker 构建（版本号经 --build-arg 从 pyproject.toml 动态注入）
docker build --build-arg APP_VERSION="$(python -c "import tomllib;print(tomllib.load(open('pyproject.toml','rb'))['project']['version'])")" -t douyin-recorder .
docker compose up -d             # 使用 docker-compose.yaml（APP_VERSION 可由 .env 提供）
```

## 格式化命令

```bash
black .
isort .
mypy src/
```

## 关键约定

1. **版本号同步**: 版本唯一事实源是 `pyproject.toml`，各消费方均动态读取、不再写死。`main.py` 与 `src/web_api.py` 运行时经 `importlib.metadata` 读取（无需修改源码）；`Dockerfile` 通过 `APP_VERSION` 构建参数动态注入；`i18n/zh_CN/LC_MESSAGES/zh_CN.po` 不再写版本号。`README.md` / `CODE_WIKI.md` 为文档，不纳入版本同步/校验。`scripts/check_version.py` 校验上述“动态化”状态
2. **行宽**: 120 字符（black + isort 统一）
3. **导入排序**: isort 使用 `black` profile，`known_first_party = ["src", "i18n"]`
4. **运行时资源**: `config/`, `ffmpeg/`, `node/` 与 exe 保持同级，不进入 `_internal/`
5. **JS 签名脚本**: 位于 `src/javascript/`，通过 `__file__` 定位，打包时收入 `_internal/`
6. **编码**: 源文件统一 UTF-8，中文注释
7. **排除目录**: `node/`, `ffmpeg/`, `downloads/`, `__pycache__/` 在所有工具中均排除

## 已知坑（避免回归）

- **弹幕 WS 连接必须显式 `proxy=None`**：`src/ws_client.py` 的 `connect()` 必须传入 `proxy=None`，使弹幕 WebSocket 直连服务器、不跟随系统代理（macOS `urllib.request.getproxies()` / `ALL_PROXY` 等环境变量）。一旦改为跟随系统代理，B站/斗鱼等平台会报 `connecting through a SOCKS proxy requires python-socks` 并连接即断。该修复对所有复用 `WsClient` 的平台弹幕连接统一生效，改动此处须保留 `proxy=None`。
- **录制链不得嵌套于 `if headers:` 内**：`main.py` 录制主链（约数百行）曾被整体包裹在 `if headers:` 条件中，导致无自定义请求头时抖音/斗鱼等平台静默不录制（状态显示"正在直播中"却无文件、无报错）。编辑录制流程时，录制链必须位于条件判断**之外**，仅把"是否附加自定义头"作为局部行为；绝不可用该条件包裹整个录制流程。
- **流地址校验 GET 复核的容错语义不得简化**：斗鱼 hw/虎牙 al 等 CDN 对毫秒级连击探针（HEAD→GET）会**偶发** 403（实测同 URL 片刻后重试即 200，ffmpeg 单次 GET 正常）。`src/stream_select.py` 的 `_confirm_get_ok` 必须满足两点：401/403 先原样重试一次再定罪；候选已是末位（`select_source_url` 中无 record_url 备选、或 record_url 本身）时稳定拒绝也仅告警放行、交由 ffmpeg 实际拉流定夺（探针与 ffmpeg 客户端指纹不同）。删掉重试或末位放行会重新引入"探针误杀可用源"（校验假红导致整轮放弃录制）。同语义扩展至两处：m3u8 的 Range-GET 探针 401/403 同样先隔 `_GET_RECHECK_INTERVAL` 重试一次再定罪（斗鱼 hw CDN HEAD=405 后连击 Range-GET 偶发 403，重试即 206——救回 HLS 候选，免疫游客态 FLV 约 70 秒被掐断）；HLS 为唯一候选（无 FLV/record_url 备选）或 FLV 为 h265 不可用时，HLS 即末位、校验须传 `last_resort=True`。
- **斗鱼必须附带 FLV→m3u8 同 token HLS 候选**：斗鱼 H5 接口只返回 FLV，游客态 FLV 长连接约 70 秒被 CDN 掐断（反复分段、I/O error）；而 wsAuth token 对 FLV/HLS 通用，`get_douyu_stream_url` 把路径 `.flv` 改 `.m3u8` 即同 token 的 HLS 播放列表（实测 hw CDN 200 + mpegurl），HLS 逐段拉取免疫单连接超时。该候选由 `select_source_url` 校验 gating、不可达自动回退 FLV，须保留。
- **`real_url` 为空必须跳过录制链**：`select_source_url` 返回 None 时若不拦截，会让 None 流入录制执行链（ffmpeg 参数/scheme 转换处崩溃，或复用上一轮残留命令；斗鱼 hw CDN 全候选探针 405/403 时实测）。必须在选源后 `if not real_url: 告警+等待+continue`。该守卫之后 `now`/`title_in_name` 为无条件赋值（原恒真冗余的 `if real_url:` 包装已移除——嵌套条件包裹录制链属反模式，且曾致 basedpyright 判定 possibly unbound）。
- **末位候选的 content-type 拒绝也须放行**：`_validate_stream_url` 的 text/html 启发式分支与尾部非 200 分支，对 `last_resort=True` 候选必须仅告警放行——斗鱼 hw CDN 对探针 HEAD 回 405+text/html（禁 HEAD 方法），ffmpeg 实际 GET 拉流正常；此前放行逻辑只存在于 `_confirm_get_ok`（401/403 GET 复核），content-type 路径漏放行导致斗鱼整轮放弃录制。
- **B站弹幕 buvid 必须真实、AUTH_REPLY 必须显式校验**：spi 官方端点是 `/x/frontend/finger/spi`（少写结尾 `i` 会 200+空 body，永远 JSONDecodeError）；spi 被风控时的兜底随机 UUID 未在 B站注册，弹幕服务器 AUTH 软拒绝（连接保持、不推弹幕、不断连，表现为"连接就绪"但 0 弹幕）。buvid 获取链按真实注册标识优先排序：进程缓存 → 登录 cookie `buvid3=` → spi → **`www.bilibili.com` 首页 Set-Cookie**（经 cookie_cache，与 spi 不同域名、风控独立）→ 随机 UUID 兜底（标记 is_fallback）。`_decode_packet` 必须校验 operation=8 回应的 code：非 0 时经 `_reject_auth()` 告警+断开+调 `spider.invalidate_bili_buvid_cache()` 失效缓存（被拒 UUID 不可复用，下一轮重新获取，否则死循环）；另有 `_auth_watchdog` 兜底「服务器不回 AUTH_REPLY 的静默拒绝」——进房包发出 8 秒无 code=0 回应按被拒处理，host 切换后旧看门狗作废。
- **虎牙探针退避仅限 `_PROBE_BACKOFF_PLATFORMS` 名单**：虎牙 aldirect CDN 对同一路径短时间连续连接做限流，每轮「HLS 3 连探针 + FLV 2~3 连探针 + ffmpeg 拉流」烧光连接预算——实测形态为校验 `GET 复核重试通过(200)` 后 ffmpeg 立即 403（返回码 3436169992），或拉流数百 KB 被 `Stream ends prematurely` 掐断，录制陷入秒级失败循环、弹幕采集器随录制反复起停（"连接就绪"却 0 条消息）。`src/stream_select.py` 的探针退避（`_mark_probe_reject`/`_probe_in_backoff`，键为 scheme://host/路径 去 query，窗口 60 秒）在观测到 401/403（含重试恢复的偶发）后跳过后续探针：非末位候选直接回退下一候选，末位候选零探针直接放行 ffmpeg 独享连接预算。**绝不可把斗鱼等平台加入名单**：斗鱼 hw 的偶发 403 由既有「重试一次再定罪」救回（重试即 206 保住 HLS-first），负缓存跳过会导致斗鱼回退 FLV（游客态约 70 秒被掐）回归。
- **弹幕监控房间须随录制线程退出而移除**：`DanmakuMonitorHub._rooms` 此前永不删除条目，URL 从 URL_config.ini 移除/注释后房间线程退出，但 Web/GUI 监控页会一直残留"已失效直播间"及其旧弹幕数据。`main.py` 的 `start_record` 在 outer try 的 `finally` 中调 `get_hub().room_stopped(record_name)`（录制态/轮询态/解析失败态的 return 全覆盖），枢纽写 `conn/stopped` 事件、GUI `_danmaku_dispatch` 收到 `state=="stopped"` 后 pop 房间行；同房间重新录制时由 collector `room_started` 重新注册。删掉该清理会重新引入旧房间残留。
- **「已被注释」检查必须在解析之前**：`main.py` 房间线程内层循环顶部（`exit_recording` 检查后）须先查 `record_url in url_comments` 再进入平台解析——原检查点位于解析成功之后，平台接口持续失败（如风控返回空）时永远走不到，线程滞留占用监控位，URL_config.ini 的移除/注释变更迟迟不生效。
- **UA 双端一字不差约定与全库统一基准**：录制拉流链的 UA 存在两组"必须一字不差"的配对——`main.py` ffmpeg 命令默认移动 UA ≡ `stream_select.MOBILE_UA`（校验探针与 ffmpeg 客户端指纹一致，否则校验假红/假绿）；`room.HEADERS` 的 UA 参与 X-Bogus 签名（签名以请求头同一 UA 计算、自洽，改字符串安全但四处须同步：`stream_select.MOBILE_UA`、`main.py` ffmpeg 默认 UA、`room.HEADERS`、B站 H5 接口 UA）。全库统一基准（2026-08）：桌面 Chrome/141（对齐 `room.DESKTOP_UA`）、Edg/141、Firefox/148（rv:148.0）、移动端 `Android 14; Pixel 8` Chrome/141——新增 UA 或升级版本时必须对齐该基准，禁止回落 Chrome≤138/Firefox≤127/SamsungBrowser 等过旧指纹（过旧 UA 是风控按指纹识别的特征之一）。
- **探针节流/抖动语义不得移除**：`src/stream_select.py` 的同 host 探针节流（`_throttle_probe`，`_PROBE_MIN_HOST_INTERVAL=0.35s`+抖动，按 host 全局限速）与重试抖动（`_recheck_delay`，`0.8s+uniform(0,0.7s)`）用于消除两类机器人节奏指纹：多房间并发下同 CDN 的毫秒级连击探针、固定 0.8s 恒定重试间隔。把重试间隔改回固定值或移除节流会重新引入"按节奏识别→误触发 403"的风控误伤（实测虎牙/斗鱼 CDN 均有此行为）。测试侧依赖 autouse fixture 把 `_throttle_probe` 置 no-op（部分用例 patch 整个 time 模块，真实节流的时间差比较会炸）；节流专项测试经 from-import 的真实函数引用绕过 no-op。
- **「禁用SSL证书验证的平台」仅在需要证书校验时生效（FFmpeg 9.0 语义）**：FFmpeg 9.0 起 TLS 证书验证默认开启。`http_config.get_effective_ssl_verify` 的平台覆盖仅在全局 `ssl_verify=True`（http 录制模式，即需要证书校验时）参与读取；https 录制模式全局已禁用、平台覆盖无意义。`main.py` 启动时经 `_sync_ssl_disable_platforms` 把证书异常平台（虎牙直播/B站直播，`SSL_DISABLE_REQUIRED_PLATFORMS`）自动追加至配置键并写回——只追加、绝不移除用户手填项。`update_config_line` 的键匹配为大小写不敏感（与 configparser optionxform 语义对齐），改回精确匹配会导致代码常量（大写 SSL/SMTP）与配置文件行（小写）无法互找。
- **i18n 多格式目录与语言热切换**：`i18n.py` 按语言依次探测 gettext `.mo` → `<lang>.json` → `<lang>.yaml`（zh_CN 用 .mo、en_US/en_GB 用 .json、zh_TW 用 .yaml）；四种目录键集合必须一致（test_i18n.py 强制）。`set_language()` 热替换 `_tr` 供 Web（PUT /api/language）/GUI（侧边栏语言菜单）/main 主循环（每轮重同步）即时切换；`language(zh_cn/en)` 配置键名保留兼容，值经 `normalize_language` 归一（别名表键统一为「小写+连字符」形态）。修改 zh_CN.po 后必须 `python scripts/compile_po.py` 重编译 .mo（测试强制字节级同步）。
- **migu.js 输出契约为完整签名 URL**：2026-08 重写后的 `src/javascript/migu.js` 适配 migu 播放器 v_20260731+ 的 wasm 接口（导入函数 a..l 共 12 个、导出名整体重排：memory=m/malloc=p/CI1=t…CI14=F），并改为输出带 `ddCalcu`/`sv` 参数的**完整地址**（sv 由官网因子接口获取，失败回退播放器内置默认因子）；`spider.get_migu_stream_url` 直接使用该 URL，不再拼接固定 `sv=10010`（已过期）。
- **Node 24 / FFmpeg 9.0 兼容基线（2026-08）**：Node 运行时以 24.19.0 实测为准（全部 JS 签名脚本 + migu.js 通过），Dockerfile 随之安装 Node 24 LTS；FFmpeg 以 9.0 为基线——9.0 移除的 CLI 参数（`-vsync`/`-top`/`-qphist`/`-filter_complex_script`/`-adrift_threshold`）禁止引入，录制命令中的冗余 `-v verbose` 已删除（被 `-loglevel error` 覆盖）。
