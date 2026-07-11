# =============================================================================
# DouyinLiveRecorder Dockerfile
# 支持抖音、TikTok、YouTube等60+平台直播录制工具
# =============================================================================

# -----------------------------------------------------------------------------
# 阶段1：构建阶段 - 安装 Python 依赖和 Node.js
# -----------------------------------------------------------------------------
FROM python:3.14-slim AS builder

# 设置环境变量
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# 安装构建依赖和 Node.js (用于 JS 签名脚本)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    gnupg \
    build-essential \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
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
FROM python:3.14-slim

# 标签
LABEL maintainer="Hmily <ihmily@github>" \
      version="4.0.7" \
      description="支持抖音、TikTok、YouTube等60+平台直播录制工具" \
      url="https://github.com/ihmily/DouyinLiveRecorder"

# 构建参数
ARG TZ=Asia/Shanghai

# 环境变量
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONIOENCODING=utf-8 \
    TZ=${TZ} \
    TERM=xterm-256color \
    PATH="/opt/venv/bin:$PATH"

# 安装运行时依赖（含 Node.js — PyExecJS 运行签名脚本必需）
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    tzdata \
    curl \
    procps \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
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

# 健康检查：检测 main.py 主进程是否存活
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD pgrep -f 'python main.py' || exit 1

# 暴露端口（用于可能的 Web UI）
EXPOSE 8000

# 默认运行命令
ENTRYPOINT ["python", "main.py"]
