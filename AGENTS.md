# AGENTS.md — DouyinLiveRecorder 核心约定

> 本文件供编码代理（Copilot / Cursor / Qoder 等）快速消费，汇总项目关键约定。

## 项目概览

- **名称**: DouyinLiveRecorder
- **版本**: 4.0.8.1（单源：`pyproject.toml` 中的 `version` 字段，`main.py` 运行时自动从该文件读取；`Dockerfile` / `README.md` / `CODE_WIKI.md` / `i18n/zh_CN/LC_MESSAGES/zh_CN.po` 需同步更新）
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
├── i18n/                # gettext 翻译文件
│   └── zh_CN/LC_MESSAGES/
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
- 覆盖率源码: `src/`
- 覆盖率排除: `tests/`, `__pycache__/`, `node/`, `ffmpeg/`
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

# Docker 构建
docker build -t douyin-recorder .
docker compose up -d             # 使用 docker-compose.yaml
```

## 格式化命令

```bash
black .
isort .
mypy src/
```

## 关键约定

1. **版本号同步**: 修改版本时只需更新 `pyproject.toml`（单一事实源），然后同步 `Dockerfile`, `README.md`, `CODE_WIKI.md`, `i18n/zh_CN/LC_MESSAGES/zh_CN.po`；`main.py` 运行时自动读取 `pyproject.toml`，无需手动修改
2. **行宽**: 120 字符（black + isort 统一）
3. **导入排序**: isort 使用 `black` profile，`known_first_party = ["src", "i18n"]`
4. **运行时资源**: `config/`, `ffmpeg/`, `node/` 与 exe 保持同级，不进入 `_internal/`
5. **JS 签名脚本**: 位于 `src/javascript/`，通过 `__file__` 定位，打包时收入 `_internal/`
6. **编码**: 源文件统一 UTF-8，中文注释
7. **排除目录**: `node/`, `ffmpeg/`, `downloads/`, `__pycache__/` 在所有工具中均排除
