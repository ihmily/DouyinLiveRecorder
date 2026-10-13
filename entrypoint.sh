#!/bin/sh
# 容器入口：初始化配置 + 环境自检，最后把控制权交给 CMD
set -eu

# 宿主机挂载的 config 目录首次通常是空的，此时用镜像内的默认配置初始化。
# 「无效」的判定不能只看文件大小：实测有用户在群晖上新建的 config.ini 只含一个
# 换行符（1 字节，-s 判定为非空），configparser 读到没有 [section] 头直接崩。
# 因此只要不存在 / 0 字节 / 没有任何 [节] 头，都强制用默认配置覆盖——
# 无效内容没有保留价值；注意 cp -rn 不会覆盖已存在文件，所以这里必须显式 -f。
if [ ! -s /app/config/config.ini ] || ! grep -q '^\[' /app/config/config.ini 2>/dev/null; then
    if [ -d /app/defaults_config ]; then
        mkdir -p /app/config
        cp -f /app/defaults_config/config.ini /app/config/config.ini
        cp -rn /app/defaults_config/. /app/config/ 2>/dev/null || true
        echo "[entrypoint] 检测到 config.ini 缺失或内容无效，已用默认配置覆盖"
    fi
fi

# 直播间地址必须预先填好：容器没有交互终端，程序卡在读取地址时不会提示你去哪填
if [ ! -s /app/config/URL_config.ini ]; then
    echo ""
    echo "[entrypoint] 提示：config/URL_config.ini 目前是空的。"
    echo "[entrypoint] 请在宿主机上往这个文件里写入直播间地址（每行一个），容器会自动开始录制。"
    echo "[entrypoint] 需要弹幕的话，确认 config/config.ini 中：是否录制弹幕(是/否) = 是"
    echo ""
fi

echo "[entrypoint] ffmpeg: $(ffmpeg -version 2>/dev/null | head -n 1 || echo '缺失')"
echo "[entrypoint] node:   $(node --version 2>/dev/null || echo '缺失（弹幕签名需要）')"

exec "$@"
