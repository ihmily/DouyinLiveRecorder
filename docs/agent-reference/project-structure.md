# 项目结构目录树（自 AGENTS.md 外迁的纯参考段）

> 本文件是 [`AGENTS.md`](../../AGENTS.md)「项目结构」章节的**完整版目录树**，2026-09-20 自根文件外迁：
> 该段是「在哪里找东西」的参考清单，不含任何需要每次会话都遵守的约定，故移出根指令的全量加载路径，
> 由根文件保留一句职责说明 + 本文件链接（根文件仍是长期约定的唯一事实源，本文件只是其附属明细）。
>
> **维护约定**：新增/删除/移动顶层目录或根目录文件时，改本文件；根文件只在「职责边界」变化时改。
> 本文件中的注释与被外迁的原文一字不差（仅缩进层级与本标题结构不同）。

## 目录树

```
项目根目录/
├── main.py              # CLI 录制入口（douyin-recorder）
├── gui.py               # GUI 入口（douyin-recorder-gui）
├── web.py               # Web 管理面板入口（douyin-recorder-web）
├── i18n.py              # 国际化模块
├── msg_push.py          # 消息推送模块
├── build_exe.py         # PyInstaller 打包脚本
├── pyproject.toml       # 项目元数据 + 工具配置
├── requirements.txt     # 运行时依赖（与 pyproject.toml 同步）
├── uv.lock              # uv 锁文件（随仓库分发；镜像/CI 用 pip 走 requirements.txt，不消费它）
├── .coveragerc-concurrency # 并发测试专用覆盖率配置（CI 经 COVERAGE_RCFILE 引用，fail_under = 0）
├── Dockerfile           # Docker 镜像构建（python:3.14-slim 多阶段 + Node 24 LTS）
├── docker-compose.yaml  # compose 编排（recorder / web / gui 三模式服务）
├── .gitignore           # 版本库忽略规则（敏感配置 / 运行期产物 / 本地工具目录）
├── .dockerignore        # 镜像构建上下文裁剪（与 .gitignore、pyproject 各工具排除列表同源维护）
├── .gitattributes       # 行尾与二进制属性钉定（*.py/*.md 等文本 LF 归一 + 二进制标注；2026-10-29 引入）
├── .pre-commit-config.yaml # 提交期门禁 hook（black/isort/mypy + 仓库级 5 脚本；mypy 平台双跑由 run_gates.py 承担）
├── pyrightconfig.json   # pyright / Pylance IDE 口径配置（include/exclude 与 pyproject [tool.mypy] 同源）
│
├── src/                 # 核心源码包
│   ├── __init__.py      # 包出口（含 get_danmaku_collector 工厂）
│   ├── base.py          # 公共基类/常量
│   ├── room.py          # 直播间管理（HEADERS / DESKTOP_UA）
│   ├── spider.py        # 平台爬虫/流地址解析
│   ├── stream.py        # 流录制逻辑
│   ├── stream_select.py # 选源与流地址可达性校验（探针/节流/退避）
│   ├── scheduler.py     # 并发调度中枢（自适应容量 + 按平台熔断）
│   ├── startup_cleanup.py # 启动期陈旧字节码缓存回收（白名单根 + 内容哈希哨兵）
│   ├── notify.py        # 错误/成功计数与消息推送接线
│   ├── collector.py     # 弹幕采集器 + DanmakuMonitorHub
│   ├── danmaku_monitor.py # 弹幕监控数据面（Web/GUI 消费）
│   ├── srt_writer.py    # 弹幕 SRT 分片写入
│   ├── ws_client.py     # 弹幕 WebSocket 客户端（proxy=None）
│   ├── async_http.py    # 异步 HTTP 客户端
│   ├── sync_http.py     # 同步 HTTP 请求
│   ├── http_config.py   # HTTP 配置（SSL 验证策略）
│   ├── cookie_cache.py  # Cookie 缓存
│   ├── config_io.py     # 配置读写
│   ├── config_read.py   # 配置读取容错层（tolerant_config_parser：重复键等异常输入告警降级而非崩口）
│   ├── config_bool.py   # 布尔配置解析（是/否 与 true/false/1/0/yes/no 等价，零依赖模块）
│   ├── recorder_status.py # 录制状态
│   ├── ffmpeg_proc.py   # FFmpeg 进程封装
│   ├── video_postprocess.py # 录制后处理
│   ├── logger.py        # 日志（loguru）
│   ├── utils.py         # 工具函数
│   ├── proxy.py         # 代理支持
│   ├── ttwid.py         # 抖音 ttwid 获取
│   ├── web_api.py       # Starlette Web API
│   ├── web_models.py    # Web 请求体校验层（dataclass + parse）
│   ├── web_config.py    # Web 配置
│   ├── web_tray.py      # Web 托盘
│   ├── ui_theme.py      # GUI 主题偏好层（主题 id 白名单 + 系统明暗探测 + config.ini 持久化）
│   ├── ui_scale.py    # GUI 缩放档位层（可选档位 + 自动档 + 持久化）
│   ├── ui_i18n.py     # GUI 静态标签 i18n 接线（T() 标记 + retranslate_all 整窗回填）
│   ├── ui_fonts.py    # GUI 自选字体（偏好读写 + config/fonts/ 副本 + 文件名清洗）
│   ├── ui_icons.py    # 应用图标安装与解析（WEB_ICON_KEY/WEB_SECTION、图标偏好持久化、体积前置闸）
│   ├── gui_qt/        # GUI 窗口层（PySide6/Qt6：app·theme·widgets·main_window·tray·settings_dialog·recorder + pages 五页）
│   ├── log_archive.py   # 运行日志归档（停止录制流程收尾：四日志按时间戳改名）
│   ├── ffmpeg_install.py # FFmpeg 自动安装
│   ├── ffmpeg_master_download.py # FFmpeg master 构建下载器（Windows 专属，TOFU 默认关闭）
│   ├── ffmpeg_linux_download.py  # Linux 运行期 ffmpeg 直下（月末不可变标签 + 双趟拷贝）
│   ├── node_install.py  # Node.js 自动安装
│   ├── platforms/       # 平台专属实现（douyin/douyu/huya/bilibili/twitch + _xbogus/_tars）
│   ├── proto/           # protobuf（__init__.py + douyin.proto + douyin_pb2.py + douyin_pb2.pyi 存根）
│   └── javascript/      # JS 签名脚本（各平台）
│
├── config/              # 运行时配置（exe 同级）
│   ├── config.ini       # 主配置
│   └── URL_config.ini   # 直播间 URL 配置
│
├── tests/               # 测试（pytest 用例 + 前端用例）
│   ├── conftest.py      # 全局 fixture（禁日志归档 env、代理清理等）
│   ├── test_*.py        # 后端 / 集成用例（与 src 模块一一对应）
│   └── frontend/        # 前端用例（.mjs，Node 内置 node:test，零 npm 依赖）
│
├── web/                 # Web 面板前端静态资源
│   ├── index.html
│   ├── app.js
│   ├── style.css
│   └── motion.js
│
├── i18n/                # 翻译目录（多语言多格式）
│   ├── zh_CN/LC_MESSAGES/  # 简体中文（gettext .po 源 + 编译 .mo）
│   ├── en_US.json          # 英语（美国）目录（JSON 格式）
│   ├── en_GB.json          # 英语（英国）目录（JSON 格式）
│   └── zh_TW.yaml          # 繁体中文目录（YAML 格式）
│
├── docs/                # 项目文档（agent-reference：AGENTS 外迁参考段；changelog：双语历史归档；worklog：审查/诊断/提案报告；gui-redesign：Qt 重设计原型）
├── assets/              # 静态资产（app.ico 应用图标）
│
├── ffmpeg/              # FFmpeg 运行时（自动下载；已忽略二进制）
├── node/                # Node.js 运行时（自动下载；已忽略）
├── logs/                # 运行日志（streamget.log / PlayURL.log / danmaku_monitor.jsonl / web_console.log）
├── downloads/           # 录制产物（视频 .ts/.mp4/.flv 与弹幕 .srt）
├── backup_config/       # 配置自动备份（*.ini_<时间戳>）
├── typings/             # 第三方库类型存根（2026-10-20 起只剩 execjs/ 一个目录）
│   └── execjs/          # PyExecJS 类型存根（多个 .pyi）
│
├── .agents/             # 项目级 Skill 资产（**已入库**：.gitignore 以 .agents/* + !.agents/skills/ 反选，其余内容物仍忽略）
│   └── skills/          # 7 个 Skill 目录：dlr-dev-playbook / dlr-domain-constraints（选源→录制→发布） / comment-refactor-at-scale（注释重构） / code-review-lifecycle（只读审查→整改） / runtime-security-response（Node/PHP 应急） / python-engineering / general-dev-toolkit（后两者非本仓约定）
│       └── .gitattributes # *.sh text eol=lf（仓库 core.autocrlf=true 会把 shebang 翻成 bash\r，限定在本子树生效）
│
├── scripts/             # 维护脚本与独立工具（CI 门禁、i18n 工具、单文件整合版；运行时链路不引用）
│   ├── check_coverage.py       # 逐模块覆盖率门禁（阈值见 MODULE_THRESHOLDS）
│   ├── check_version.py        # 版本「动态化、未写死」状态校验
│   ├── check_workflow_constants.py # ci.yml 与 build-release.yml 版本常量跨文件一致性门禁
│   ├── sync_metadata.py        # uv.lock / egg-info 与 pyproject 元数据再生成 + --check 一致性校验
│   ├── report_bundle_size.py   # 发布产物体积报告（打包体积门禁的度量侧：总量/按包聚合/最大单文件）
│   ├── sync_version.py         # 从 pyproject.toml 同步版本号到遗留文件
│   ├── compile_po.py           # 纯 Python po→mo 编译（CI --check 字节级门禁）
│   ├── extract_i18n_strings.py # i18n 待翻译串提取（AST 扫描，与四语目录比对）
│   ├── check_annotations.py   # 注释规范检查 + 逻辑等价性校验（三模式，见下方「注释约定」章节）
│   ├── run_gates.py            # 本地一次性门禁入口：运行时解析 AGENTS.md「格式化命令」章节逐字执行（只跑 --check）
│   ├── check_runtime_pins.py  # 运行时二进制 SHA256 钉定表检查：默认只查结构（rc=2 表缺陷），
│   │                          #   --strict 供 build-release.yml 拦发布，--emit-env 输出 DLR_RUNTIME_SHA256
│   ├── smoke_test.py           # Web/接口冒烟测试工具（JSON 配置驱动，纯标准库）
│   ├── check_skill_agents_consistency.py # AGENTS.md「项目级 Skill」表与 .agents/skills/ 目录同源校验（已入门禁清单）
│   ├── agent_hook_guard.py     # 项目级 Hook 执行体：stdin 收 Qoder 事件 JSON，拦「风险控制（前置）」红线 + 报「对门禁三面隐形」的回归（注册在 .qoder/settings.json）
│   ├── smoke_web.json          # 冒烟测试接口配置
│   ├── _ci_web_smoke.sh        # CI 侧 Web 冒烟包装（原样透传 smoke_test.py 退出码，区分 rc=1/2）
│   ├── spike_arm64_static_ffmpeg.sh # W2 spike：Apple Silicon 自源码构建静态 ffmpeg（仅产出验收证据，不接入 build-release.yml）
│   └── douyin_live_recorder_standalone.py # 单文件整合版录制脚本（抖音/虎牙/B站/斗鱼，零第三方依赖）
│
└── .github/
    ├── actions/retry/   # 复合动作：网络安装重试包装（ci.yml / build-release.yml 共用）
    ├── ISSUE_TEMPLATE/  # 议题模板（中英双语：bug / feature / question）
    ├── PULL_REQUEST_TEMPLATE.md
    └── workflows/       # CI/CD：ci.yml（门禁 + deps-audit）/ build-release.yml（四平台构建发布，含 linux aarch64）
                       #   / trivy.yml（镜像漏洞扫描，本地构建不推送）/ issue-translator.yml（已降级为仅手动）

# 根目录文档与分发脚本（不进镜像，见 .dockerignore）
├── README.md / README_EN.md        # 用户说明（中英）
├── CODE_WIKI.md / CODE_WIKI_EN.md  # 架构文档（中英）
├── AGENTS.md                       # 编码代理约定（本文件）
├── CODE_REVIEW_FIX_1.md            # 代码审查遗留项清单（2026-09-14 收官：25 项全部结项）
├── LICENSE                         # MIT
├── index.html                      # 独立 M3U8 播放器页面（Web 面板用 web/ 目录）
└── StopRecording.vbs               # Windows 停止录制脚本（UTF-16 LE 带 BOM，见「已知坑」）
```

## 与根文件的分工

- 根文件「项目结构」章节只保留**职责边界一句话 + 本文件链接**；任何「约定 / 门禁 / 坑」都不写在这里。
- 逐模块覆盖率**阈值数值**不在本文件也不在根文件维护：唯一事实源是
  [`scripts/check_coverage.py`](../../scripts/check_coverage.py) 的 `MODULE_THRESHOLDS`（根文件只指向该脚本）。
- `.gitignore` / `.dockerignore` / pyproject 各工具排除列表的同源约定，见根文件「CI / workflow 约定」章节，
  本文件不重复规定。
