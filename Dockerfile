# =============================================================================
# DouyinLiveRecorder 容器镜像（多阶段构建）
# 基础镜像：python:3.14-slim-bookworm（Debian 12，最小 Python 运行时）
# 平台与版本清单的事实源是 pyproject.toml，此处不再复述
# =============================================================================

# -----------------------------------------------------------------------------
# 阶段1：构建阶段 —— 只把 Python 依赖装进 /opt/venv
# Node.js 不在此阶段装：它只被 PyExecJS / exejs 在**运行时**跑各平台 JS 签名脚本，
# 构建期引入只会拖慢层缓存；弹幕采集链的 websockets / protobuf / brotli 随
# requirements.txt 一并装入 /opt/venv，运行时直接可用。
# -----------------------------------------------------------------------------
FROM python:3.14-slim-bookworm AS builder

# 无缓冲输出便于容器日志、禁止写字节码减小体积、关闭 pip 缓存与版本检查
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# build-essential 用于编译无二进制轮子的依赖（如部分加密 / 解析库）
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# 虚拟环境落在中立路径 /opt/venv，对所有用户可读，供运行时阶段整目录复用
RUN python -m venv /opt/venv

WORKDIR /build

# 只先拷依赖声明文件：仅依赖变更才重装，源码变更不打断层缓存
COPY requirements.txt pyproject.toml ./

# requirements.txt 含 HTTP / 日志 / 加密 / GUI / Web / 弹幕全部运行时依赖。
# INSTALL_GUI=false（默认）时**不装** PySide6：镜像按设计只跑 main.py 与 web.py，本机实测两者
# 屏蔽 PySide6 后导入链完整（gui.py 把窗口层延迟到 main() 内导入，可导入、但起窗才需要它）；
# 而 PySide6 解压后本机实测 647.56MB，阶段2 的 slim-bookworm 又缺 Qt 运行库
# （libEGL/libGL/glib/fontconfig/xkbcommon…），默认装入只会撑大一倍却仍起不动窗口。
# 需要容器内 GUI 时显式 --build-arg INSTALL_GUI=true，由阶段2 同条件补装 Qt 运行库
# （两侧判据必须一起改）；过滤只发生在镜像侧，requirements.txt 与 pyproject
# [project.dependencies] 的集合相等锁不受影响。
ARG INSTALL_GUI=false
RUN /opt/venv/bin/pip install --upgrade pip \
    && if [ "$INSTALL_GUI" = "true" ]; then \
           /opt/venv/bin/pip install --no-cache-dir -r requirements.txt; \
       else \
           grep -viE '^[[:space:]]*pyside6' requirements.txt > /tmp/requirements.nogui.txt \
           && echo "[build] INSTALL_GUI=false：已从镜像依赖清单剔除 $(grep -icE '^[[:space:]]*pyside6' requirements.txt) 条 GUI 依赖" \
           && /opt/venv/bin/pip install --no-cache-dir -r /tmp/requirements.nogui.txt; \
       fi

# -----------------------------------------------------------------------------
# 阶段2：运行阶段 - 最小化运行镜像
# -----------------------------------------------------------------------------
FROM python:3.14-slim-bookworm

# 默认时区，可被 --build-arg TZ / .env 覆盖
ARG TZ=Asia/Shanghai
# 版本号唯一事实源是 pyproject.toml 的 [project].version，构建时经 --build-arg APP_VERSION 注入；
# docker-compose.yaml 从 .env 读同名变量，不设则 LABEL version 为空（镜像内版本仍由
# main.py / src/web_api.py 经 importlib.metadata 在运行时读取）。本地 / CI 取值：
#   docker build --build-arg APP_VERSION="$(python -c "import tomllib;print(tomllib.load(open('pyproject.toml','rb'))['project']['version'])")"
# MIN-14（2026-09-21）：ARG 必须声明在**使用它的 LABEL 之前**——Dockerfile 按行做变量替换，
# 顺序颠倒会让 version 标签固化为空串、--build-arg 完全不生效；scripts/check_version.py 现已
# 断言「声明行号 < 使用行号」（原先只正则匹配字面 version="${APP_VERSION}"，检不出顺序错误）。
ARG APP_VERSION

# 维护者与项目 URL 与 pyproject.toml [project.urls]/authors 同源（y123ao6）；上游原作者 ihmily
# 的署名保留在 README「上游项目」行与 main.py 版权头
LABEL maintainer="y123ao6 <zmzx0690@agent.qq.com>" \
      version="${APP_VERSION}" \
      description="支持抖音、TikTok、YouTube等60+平台直播录制工具" \
      url="https://github.com/y123ao6/DouyinLiveRecorder"

# 运行时行为：无缓冲、不写字节码、UTF-8 输出、时区、彩色终端、venv 入 PATH
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONIOENCODING=utf-8 \
    TZ=${TZ} \
    TERM=xterm-256color \
    PATH="/opt/venv/bin:$PATH"

# 运行时依赖：ffmpeg（录制与转码）、tzdata（配合 TZ）、curl（取 NodeSource 脚本）、
#   procps（提供 pgrep，供下方 HEALTHCHECK 判活）、ca-certificates（HTTPS 抓取根证书）、
#   nodejs 24 LTS（PyExecJS / exejs 跑各平台 JS 签名脚本；2026-08 实测兼容 Node 24.19.0，
#   全部签名脚本 + migu.js 重写版通过，与 src/node_install.py 拉取的最新稳定版同代）。
# apt-get upgrade -y：牺牲一点可重现性换及时安全补丁。
# NodeSource 脚本「先下载 → 校验 SHA256 → 一致才执行」：原写法 `curl -fsSL <url> | bash -`
#   无哈希校验，源站或 CDN 被替换即以 root 权限在构建期执行任意代码（构建期无运行时隔离，
#   危害等同生产 RCE）；此处钉哈希，与 src/ffmpeg_install.py 的 trust-on-first-use 互补。
# 升级 NodeSource 主版本必须同步改下面两个变量，否则构建失败（fail-closed）；
#   当前哈希对应 2026-09-12 抓取的 setup_24.x（3907 字节）。
ARG NODESOURCE_SETUP_URL=https://deb.nodesource.com/setup_24.x
ARG NODESOURCE_SETUP_SHA256=6e3d580f5bd7ccf2aa1e8df8d35c60d78e873c3ff8beb282c9bebd914904ad72
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    tzdata \
    curl \
    procps \
    ca-certificates \
    && curl -fsSL "${NODESOURCE_SETUP_URL}" -o /tmp/nodesource_setup.sh \
    && echo "${NODESOURCE_SETUP_SHA256}  /tmp/nodesource_setup.sh" | sha256sum -c - \
    && bash /tmp/nodesource_setup.sh \
    && rm -f /tmp/nodesource_setup.sh \
    && apt-get install -y nodejs \
    && apt-get upgrade -y \
    && ln -fs /usr/share/zoneinfo/${TZ} /etc/localtime \
    && dpkg-reconfigure -f noninteractive tzdata \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# 运行阶段的 Qt 系统库：只在 INSTALL_GUI=true 时装。slim-bookworm 默认没有 libEGL/libGL/glib/
# fontconfig/xkbcommon/xcb 等 QtWidgets 链接依赖，缺任一项 `import PySide6.QtWidgets` 即失败——
# 「装 PySide6」与「装 Qt 库」是同一个开关的两半，必须同条件、同批改（ARG 不跨阶段，本阶段须
# 重新声明）。默认 false 时本 RUN 只落一个空层，不影响镜像体积。
ARG INSTALL_GUI=false
RUN if [ "$INSTALL_GUI" = "true" ]; then \
        apt-get update \
        && apt-get install -y --no-install-recommends \
            libegl1 \
            libgl1 \
            libglib2.0-0 \
            libfontconfig1 \
            libxkbcommon0 \
            libxkbcommon-x11-0 \
            libdbus-1-3 \
            libxcb-xinerama0 \
            libxcb-cursor0 \
        && apt-get clean \
        && rm -rf /var/lib/apt/lists/*; \
    fi

# 创建非 root 用户（降低容器被攻破后的影响面；uid/gid=1000 便于卷挂载权限对齐）
RUN groupadd --gid 1000 recorder \
    && useradd --uid 1000 --gid recorder --shell /bin/bash --create-home recorder

WORKDIR /app

COPY --from=builder /opt/venv /opt/venv

# 应用代码以 recorder 属主入镜像，实际内容由 .dockerignore 裁剪（那份文件是唯一清单事实源）：
# 留下 main.py / web.py / gui.py + src/（javascript/ 签名脚本、platforms/ 平台实现、proto/ 弹幕协议）
#   + web/ 静态资源 + i18n/**/*.mo（gettext 运行时必需，构建期不重编译）；排除测试与工具
#   （tests/ scripts/ typings/ uv.lock 等）、文档、运行期产物（logs/ downloads/ backup_config/，
#   改由卷挂载提供）、平台二进制与 config/*.ini（含凭据）。
COPY --chown=recorder:recorder . ./

# 预建运行期目录（日志 / 录制产物 / 配置备份），使卷挂载前目录已存在且归属 recorder
RUN mkdir -p logs downloads backup_config \
    && chown -R recorder:recorder /app

USER recorder

# 健康检查：经 pgrep 匹配进程命令行，同时兼容 main.py（命令行）与 web.py（面板）两种模式；
# compose 的 web 服务继承此判定，gui 服务必须单独覆盖（本判定对 gui.py 永远失败）
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD pgrep -f 'python (main|web).py' || exit 1

# Web 管理面板模式端口。注意：web.py 默认监听 127.0.0.1，容器内需在 config/config.ini 的
# [Web] 节将 web_host 设为 0.0.0.0，宿主机端口映射才能访问到面板。
EXPOSE 8000

# 默认命令行录制模式；Web 面板模式改 command 为 python web.py
# （docker-compose.yaml 已提供 web / gui 两个 profile 服务）
ENTRYPOINT ["python", "main.py"]
