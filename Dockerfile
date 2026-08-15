# =============================================================================
# DouyinLiveRecorder Dockerfile
# 支持抖音、TikTok、YouTube等60+平台直播录制工具
# =============================================================================

# -----------------------------------------------------------------------------
# 阶段1：构建阶段 - 仅安装 Python 依赖到虚拟环境
# （Node.js 只在运行时需要，由阶段2安装，构建阶段无需引入）
# -----------------------------------------------------------------------------
FROM python:3.13-slim-bookworm AS builder

# 设置环境变量
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# 安装构建依赖（build-essential 用于编译无二进制轮子的依赖）
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# 创建 Python 虚拟环境（中立路径，对所有用户可读）
RUN python -m venv /opt/venv

# 设置工作目录
WORKDIR /build

# 先复制依赖声明文件，利用 Docker 层缓存
COPY requirements.txt pyproject.toml ./

# 安装 Python 依赖到虚拟环境
RUN /opt/venv/bin/pip install --upgrade pip \
    && /opt/venv/bin/pip install --no-cache-dir -r requirements.txt

# -----------------------------------------------------------------------------
# 阶段2：运行阶段 - 最小化运行镜像
# -----------------------------------------------------------------------------
FROM python:3.13-slim-bookworm

# 标签
LABEL maintainer="Hmily <ihmily@github>" \
      version="${APP_VERSION}" \
      description="支持抖音、TikTok、YouTube等60+平台直播录制工具" \
      url="https://github.com/ihmily/DouyinLiveRecorder"

# 构建参数
ARG TZ=Asia/Shanghai
# 版本号从 pyproject.toml 动态注入：构建时通过 --build-arg APP_VERSION=<版本> 传入
ARG APP_VERSION

# 环境变量
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONIOENCODING=utf-8 \
    TZ=${TZ} \
    TERM=xterm-256color \
    PATH="/opt/venv/bin:$PATH"

# 安装运行时依赖（含 Node.js 22 LTS — PyExecJS 运行签名脚本必需）
# 同时升级所有已安装软件包到最新安全版本
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    tzdata \
    curl \
    procps \
    ca-certificates \
    && curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y nodejs \
    && apt-get upgrade -y \
    && ln -fs /usr/share/zoneinfo/${TZ} /etc/localtime \
    && dpkg-reconfigure -f noninteractive tzdata \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# 创建非 root 用户
RUN groupadd --gid 1000 recorder \
    && useradd --uid 1000 --gid recorder --shell /bin/bash --create-home recorder

# 设置工作目录
WORKDIR /app

# 复制 Python 虚拟环境（包含所有依赖）
COPY --from=builder /opt/venv /opt/venv

# 复制应用代码，设置正确的所有权
COPY --chown=recorder:recorder . ./

# 运行时创建必要目录
RUN mkdir -p logs downloads backup_config \
    && chown -R recorder:recorder /app

# 切换到非 root 用户
USER recorder

# 健康检查：同时兼容 main.py（命令行模式）与 web.py（Web 管理面板模式）
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
