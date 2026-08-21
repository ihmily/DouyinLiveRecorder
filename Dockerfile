# =============================================================================
# DouyinLiveRecorder Dockerfile
# 支持抖音、TikTok、YouTube等60+平台直播录制工具
# 基础镜像：python:3.13-slim-bookworm（Debian 12，最小 Python 运行时）
# =============================================================================

# -----------------------------------------------------------------------------
# 阶段1：构建阶段 - 仅安装 Python 依赖到虚拟环境
# 说明：Node.js 只在运行时需要（PyExecJS / exejs 运行签名脚本），由阶段2安装，
#       构建阶段无需引入，从而保持 builder 镜像精简、利用层缓存。
# 弹幕（src/danmaku）运行时依赖 websockets / protobuf / brotli 也在此阶段随
# requirements.txt 一并装入 /opt/venv，运行时直接可用。
# -----------------------------------------------------------------------------
FROM python:3.13-slim-bookworm AS builder

# 设置环境变量（无缓冲输出便于容器日志、禁止写字节码减小体积、关闭 pip 缓存与版本检查）
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# 安装构建依赖（build-essential 用于编译无二进制轮子的依赖，如部分加密 / 解析库）
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# 创建 Python 虚拟环境（中立路径，对所有用户可读，运行时阶段直接复用）
RUN python -m venv /opt/venv

# 设置工作目录
WORKDIR /build

# 先复制依赖声明文件，利用 Docker 层缓存（仅依赖变更时才重装，源码变更不触发）
COPY requirements.txt pyproject.toml ./

# 安装 Python 依赖到虚拟环境（含 HTTP / 日志 / 加密 / GUI / Web / 弹幕等全部运行时依赖）
RUN /opt/venv/bin/pip install --upgrade pip \
    && /opt/venv/bin/pip install --no-cache-dir -r requirements.txt

# -----------------------------------------------------------------------------
# 阶段2：运行阶段 - 最小化运行镜像
# -----------------------------------------------------------------------------
FROM python:3.13-slim-bookworm

# 标签（version 由构建参数 APP_VERSION 注入，来自 pyproject.toml 的 version）
LABEL maintainer="Hmily <ihmily@github>" \
      version="${APP_VERSION}" \
      description="支持抖音、TikTok、YouTube等60+平台直播录制工具" \
      url="https://github.com/ihmily/DouyinLiveRecorder"

# 构建参数
ARG TZ=Asia/Shanghai
# 版本号从 pyproject.toml 动态注入：构建时通过 --build-arg APP_VERSION=<版本> 传入
ARG APP_VERSION

# 环境变量（运行时行为：无缓冲、不写字节码、UTF-8 输出、时区、彩色终端、venv 入 PATH）
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONIOENCODING=utf-8 \
    TZ=${TZ} \
    TERM=xterm-256color \
    PATH="/opt/venv/bin:$PATH"

# 安装运行时依赖：
#   ffmpeg      - 视频录制与转码（核心外部依赖）
#   tzdata      - 时区数据（配合 TZ 参数）
#   curl        - 下载 Node.js 安装脚本
#   procps      - 提供 pgrep，供下方 HEALTHCHECK 判定进程存活
#   ca-certificates - HTTPS 抓取所需根证书
#   nodejs(24 LTS) - PyExecJS / exejs 运行各平台 JS 签名脚本（2026-08 已实测
#                    兼容 Node 24.19.0：全部签名脚本 + migu.js 重写版通过；
#                    与 node_install.py 拉取的最新稳定版保持同代）
# 随后 apt-get upgrade -y 升级已安装包到最新安全补丁（权衡：牺牲一点可重现性换取及时安全修复）
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    tzdata \
    curl \
    procps \
    ca-certificates \
    && curl -fsSL https://deb.nodesource.com/setup_24.x | bash - \
    && apt-get install -y nodejs \
    && apt-get upgrade -y \
    && ln -fs /usr/share/zoneinfo/${TZ} /etc/localtime \
    && dpkg-reconfigure -f noninteractive tzdata \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# 创建非 root 用户（降低容器被攻破后的影响面；uid/gid=1000 便于卷挂载权限对齐）
RUN groupadd --gid 1000 recorder \
    && useradd --uid 1000 --gid recorder --shell /bin/bash --create-home recorder

# 设置工作目录
WORKDIR /app

# 复制 Python 虚拟环境（包含所有运行时依赖，来自 builder 阶段）
COPY --from=builder /opt/venv /opt/venv

# 复制应用代码，设置正确的所有权（运行时以 recorder 用户运行）
COPY --chown=recorder:recorder . ./

# 运行时创建必要目录（日志 / 录制产物 / 配置备份），并统一归属 recorder
RUN mkdir -p logs downloads backup_config \
    && chown -R recorder:recorder /app

# 切换到非 root 用户（遵循最小权限原则）
USER recorder

# 健康检查：同时兼容 main.py（命令行模式）与 web.py（Web 管理面板模式）
# 通过 pgrep 匹配进程命令行；recorder / gui 模式继承此判定，gui 在 compose 中单独覆盖
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD pgrep -f 'python (main|web).py' || exit 1

# 暴露端口（Web 管理面板模式使用）
# 注意：web.py 默认监听 127.0.0.1，容器内需在 config/config.ini 的 [Web] 节
# 将 web_host 设为 0.0.0.0，宿主机端口映射才能访问到面板。
EXPOSE 8000

# 默认运行命令：命令行录制模式
# 如需 Web 管理面板模式，启动时改 command 为: python web.py
# （docker-compose.yaml 已提供 web / gui 两个 profile 服务）
ENTRYPOINT ["python", "main.py"]
