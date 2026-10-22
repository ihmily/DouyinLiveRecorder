#!/usr/bin/env bash
# W2 spike：在 macOS runner / 本地 Apple Silicon 上自源码构建**自包含 arm64 静态 ffmpeg**，
# 并产出可判定「路线 A 是否可行」的验收证据。脚本只到 spike 为止——**不接入 build-release.yml**
# （那属 W3，需单独批准）。
#
# 背景（PROPOSAL_2026-09-22_binary-trust-policy.md 第五节）：ffmpeg.org 官方 macOS 条目只有
# evermeet 的 x86_64 静态构建，上游不发 arm64 → full 包里的 macOS ffmpeg 在 Apple Silicon 上走
# Rosetta 转译；Homebrew bottle 又不能当分发源（11 个 runtime_deps 的 dylib 在别的 formulae 里）。
# W1 已落的第 4 类「源码可复现构建」要求**输入可钉定 + 过程可追溯**，本脚本就是来实测三件证据
# 取不取得到（官方源码 tarball 校验值 / configure 配方哈希 / 产出凭据）。
#
# 只做三件事：① 验证能否拿到官方公布的 tarball 摘要——拿不到即失败并把事实打出来（W3 的阻塞点，
# 不能糊过去）；② 用一组**固定且可复现**的 configure 参数产出 arm64 静态单文件；③ 用 lipo/otool
# 判定「自包含」与「架构」，而不是 `--enable-static` 写了就当成立（最常见的假自包含是 brew 的
# dylib 被静默链进来，必须实测 otool）。
#
# 无 macOS 时：`bash scripts/spike_arm64_static_ffmpeg.sh --print-only` 打印将要执行的全部命令与
# 常量、不执行任何外部程序，评审据此复核。
#
# 用法（macOS）：
#   bash scripts/spike_arm64_static_ffmpeg.sh                 # 全流程（约 20~45 min，装依赖需 brew）
#   FFMPEG_VERSION=8.1.2 bash scripts/spike_arm64_static_ffmpeg.sh
#   SKIP_DEPS=1 bash scripts/spike_arm64_static_ffmpeg.sh     # 依赖已装好时跳过 brew install
#   bash scripts/spike_arm64_static_ffmpeg.sh --print-only    # 只打印计划
#
# 退出码：0 全部验收通过；1 任一验收不通过（结论同样有效，spike 就是来给结论的）；
#         2 前置条件不满足（非 macOS / 拿不到官方 tarball 摘要 / 工具缺失），属「没跑成」不是「跑过了」。

set -euo pipefail

# 下面用了 [[ ... =~ ]]（正则匹配摘要长度），这是 bash 扩展：若被 `sh script.sh` 拉起会
# 报一句难懂的语法错，这里显式挡住并给出正确调用方式。
if [ -z "${BASH_VERSION:-}" ]; then
    printf '请用 bash 运行：bash %s [--print-only]\n' "$0" >&2
    exit 2
fi

# ------------------------------ 可调参数 ------------------------------
# 版本留空 → 从官方 releases 目录列表自动挑最新**正式release**（排除 git/snapshot 命名）。
FFMPEG_VERSION="${FFMPEG_VERSION:-}"
RELEASE_INDEX="${RELEASE_INDEX:-https://ffmpeg.org/releases/}"
# M-96（2026-10-21）：索引、摘要、tarball 三者此前全部由 RELEASE_INDEX 推导——同一站点被替换时
# 三样一起换，「摘要比对」退化成自己验自己。现拆成三个可独立覆盖的变量，使摘要可指向独立镜像
# 或人工登记值；默认值仍相同（ffmpeg.org 没有第二个官方摘要端点），故脚本在两者同源时**显式
# 打一条告警**，禁止把同源比对当成来源认证的证据。
FFMPEG_INDEX_URL="${FFMPEG_INDEX_URL:-$RELEASE_INDEX}"
FFMPEG_TARBALL_BASE="${FFMPEG_TARBALL_BASE:-$RELEASE_INDEX}"
FFMPEG_DIGEST_BASE="${FFMPEG_DIGEST_BASE:-$FFMPEG_TARBALL_BASE}"
# 依赖只装「项目真用到的编码器」：libx264（src/video_postprocess.py 的转码路径）与
# libmp3lame（main.py 的 mp3 音频路径）。刻意不引 x265/libvpx/openssl@3——每多一个第三方库，
# 静态链失败或漏进 dylib 的概率就多一分；TLS 走 macOS 自带的 SecureTransport，不需要 openssl。
BREW_DEPS=(nasm pkg-config x264 lame)
JOBS="${JOBS:-$(sysctl -n hw.ncpu 2>/dev/null || echo 3)}"
# 产物默认落在**仓库外**（AGENTS.md「一次性脚本优先写在仓库之外」同源）：spike 会留下
# tarball / 源码树 / 编出来的二进制，共约 1GB，绝不该进工作区或版本控制。
OUT_DIR="${OUT_DIR:-${TMPDIR:-/tmp}/spike-arm64-ffmpeg}"
SKIP_DEPS="${SKIP_DEPS:-0}"
PRINT_ONLY=0

for arg in "$@"; do
    case "$arg" in
        --print-only) PRINT_ONLY=1 ;;
        --help | -h)
            sed -n '1,40p' "$0" | sed 's/^# \{0,1\}//'
            exit 0
            ;;
        *)
            echo "[spike][FATAL] 未知参数：$arg（可用：--print-only / --help）" >&2
            exit 2
            ;;
    esac
done

log() { printf '[spike] %s\n' "$*"; }
fail_pre() { printf '[spike][PRECONDITION-FAIL] %s\n' "$*" >&2; exit 2; }
fail_check() { printf '[spike][CHECK-FAIL] %s\n' "$*" >&2; exit 1; }

# --print-only 时把命令原样打出来（**不执行**）：这是非 macOS 评审的唯一可行路径，
# 也是本 spike 唯一能在 Windows 上真跑起来的分支，所以它必须真的存在而不是注释里的「你应该这么跑」。
run() {
    if [ "$PRINT_ONLY" -eq 1 ]; then
        printf '    + %s\n' "$*"
        return 0
    fi
    log "\$ $*"
    "$@"
}

# ------------------------------ 前置检查 ------------------------------
if [ "$PRINT_ONLY" -eq 0 ]; then
    [ "$(uname -s)" = "Darwin" ] || fail_pre "本 spike 只能在 macOS 上执行（lipo/otool/SecureTransport 皆为系统工具）；查看计划请加 --print-only"
    command -v brew >/dev/null 2>&1 || fail_pre "未找到 Homebrew：spike 用它装 nasm/pkg-config/x264/lame。装好后重跑，或 SKIP_DEPS=1 自行准备"
    command -v make >/dev/null 2>&1 || fail_pre "未找到 make（通常需要 xcode-select --install 的 Command Line Tools）"
fi

# --print-only 不留任何痕迹：不建目录、不写文件（评审机上跑完应当什么都不会多出来）。
if [ "$PRINT_ONLY" -eq 0 ]; then
    mkdir -p "$OUT_DIR"
fi
TARBALL_NAME=""
SOURCE_SHA256=""
SHA_SOURCE_KIND=""
REPORT_JSON="$OUT_DIR/report.json"
# 配方哈希：把 configure 的全部参数当「构建配方」钉住（W1 第 4 类的 recipe_sha256 语义）。
# 任何一次参数调整都会让哈希变，从而强制后来的人重核 —— 这正是「参数写在 CI 里但没人复核」的老毛病。
CONFIGURE_ARGS=(
    --prefix="$OUT_DIR/prefix"
    --enable-static
    --disable-shared
    --pkg-config-flags=--static
    --disable-autodetect
    --enable-gpl
    --enable-libx264
    --enable-libmp3lame
    --enable-securetransport
    --enable-videotoolbox
    --disable-doc
    --disable-debug
    --optflags=-O3
)
RECIPE_SHA=""
if [ "$PRINT_ONLY" -eq 0 ]; then
    RECIPE_SHA="$(printf '%s\n' "${CONFIGURE_ARGS[@]}" | shasum -a 256 | cut -d' ' -f1)"
fi

# ------------------------------ 1. 挑版本 + 官方摘要 ------------------------------
pick_version() {
    local index_html="$1"
    # 只要 ffmpeg-<主>.<次>[.<修>].tar.xz，排除 ffmpeg-release / ffmpeg-git 之类滚动名。
    # 不用 `sort -V`：macOS 自带 FreeBSD sort，旧版不认 -V；改成显式数值键排序（主.次.修，缺修补 0），
    # 以便脚本在 Linux 评审机上同样可跑。
    grep -oE 'ffmpeg-[0-9]+\.[0-9]+(\.[0-9]+)?\.tar\.xz' <<<"$index_html" \
        | sed -E 's/ffmpeg-([0-9]+)\.([0-9]+)(\.([0-9]+))?\.tar\.xz/\1 \2 \4/' \
        | awk '{ printf "%d %d %d\n", $1, $2, ($3 == "" ? 0 : $3) }' \
        | sort -k1,1n -k2,2n -k3,3n \
        | tail -1 \
        | awk '{ if ($3 == 0) printf "%s.%s\n", $1, $2; else printf "%s.%s.%s\n", $1, $2, $3 }'
}

# 从「一行摘要」里取出摘要本身：官方文件常见形态是 "<hex>  ffmpeg-x.y.tar.xz"，也有纯 hex 一行。
# 必须先按字段切、再校验长度——直接对整行做 anchored 正则会永不匹配，而用 tr -d '[:space:]'
# 拼成一坨会让 SHA512(128) 的尾巴被当成 SHA256(64) 用。
first_field_hex() {
    local text="$1"
    awk 'NF { print $1; exit }' <<<"$text" | tr 'A-Z' 'a-z'
}

fetch_official_sha256() {
    local ver="$1" url base_url suffix raw digest
    # M-96：摘要端点走 FFMPEG_DIGEST_BASE（可与 tarball 源不同），不再硬绑 RELEASE_INDEX。
    base_url="${FFMPEG_DIGEST_BASE%/}/ffmpeg-${ver}.tar.xz"
    # 候选端点按「能直接喂给第 4 类 source_sha256 字段」的强度排序：先 .sha256，再 .sha512
    # （SHA512 只算**事实登记**，不拿来当 SHA256 用，见下面的 fail_pre）。
    # 刻意不静默降级成「自己算一个」：第 4 类的口径就是不得把构建机自算值当基线，拿不到官方
    # 摘要时正确行为是**失败并把端点打出来**，交人工核对。
    for suffix in .sha256 .sha512; do
        url="${base_url}${suffix}"
        log "尝试官方摘要端点：$url"
        if [ "$PRINT_ONLY" -eq 1 ]; then
            printf '    + curl -fsSL %s\n' "$url"
            SHA_SOURCE_KIND="PRINT-ONLY"
            SOURCE_SHA256="<待官方端点取回>"
            return 0
        fi
        raw="$(curl -fsSL --max-time 60 "$url" 2>/dev/null || true)"
        [ -n "$raw" ] || continue
        digest="$(first_field_hex "$raw")"
        case "$suffix:$digest" in
            .sha256:*)
                if [[ "$digest" =~ ^[0-9a-f]{64}$ ]]; then
                    SOURCE_SHA256="$digest"
                    SHA_SOURCE_KIND="$suffix"
                    return 0
                fi
                log "端点 $url 返回的内容不是 64 位十六进制（形态可能已变）：${digest:0:32}…"
                ;;
            .sha512:*)
                if [[ "$digest" =~ ^[0-9a-f]{128}$ ]]; then
                    SHA_SOURCE_KIND="$suffix"
                    fail_pre "官方只提供 ${TARBALL_NAME}.sha512（128 位）——**不得截取前/后 64 位当 SHA256**。请在 W3 前决定：把 _SOURCE_BUILD_EVIDENCE 的 source 字段扩成 SHA512，或另找官方 SHA256 来源"
                fi
                ;;
        esac
    done
    return 1
}

if [ "$PRINT_ONLY" -eq 1 ]; then
    log "PRINT-ONLY 计划（不会执行任何外部程序）"
    printf '    目标平台 = darwin/arm64，JOBS=%s，OUT_DIR=%s\n' "$JOBS" "$OUT_DIR"
    printf '    1) curl -fsSL %s | 挑最新正式 release（当前 FFMPEG_VERSION=%s）\n' "$FFMPEG_INDEX_URL" "${FFMPEG_VERSION:-<自动>}"
    printf '    2) 取官方摘要：%s/ffmpeg-<ver>.tar.xz{.sha256,.sha512}（拿不到即 rc=2 退出，不自算基线）\n' "${FFMPEG_DIGEST_BASE%/}"
    printf '    3) 下载 tarball 并 shasum -a 256 与之逐字比对\n'
    printf '    4) brew install %s（SKIP_DEPS=1 可跳过）\n' "${BREW_DEPS[*]}"
    printf '    5) ./configure %s\n' "${CONFIGURE_ARGS[*]}"
    printf '    6) make -j%s && make install\n' "$JOBS"
    printf '    7) 验收：lipo -archs=arm64；otool -L 只剩 /usr 与 /System 库；-encoders 有 libx264/libmp3lame；跑一次 1s 真实转码\n'
    printf '    8) 写 %s（三件证据 + 计时 + 验收原文）\n' "$REPORT_JSON"
    printf '    + configure 配方 = %s\n' "${CONFIGURE_ARGS[*]}"
    exit 0
fi

log "读取 releases 目录：$FFMPEG_INDEX_URL"
# M-96：同源摘要只证明「下载没被截断/串版本」，不证明来源可信（站点被换则索引/摘要/产物一起换）。
if [ "${FFMPEG_DIGEST_BASE%/}" = "${FFMPEG_TARBALL_BASE%/}" ]; then
    log "WARN: 摘要与 tarball 同源（$FFMPEG_TARBALL_BASE）——该比对仅作形态校验，发布前须用独立来源复核"
fi
INDEX_HTML="$(curl -fsSL --max-time 60 "$FFMPEG_INDEX_URL")"
if [ -z "$FFMPEG_VERSION" ]; then
    FFMPEG_VERSION="$(pick_version "$INDEX_HTML")"
    [ -n "$FFMPEG_VERSION" ] || fail_pre "无法从 $FFMPEG_INDEX_URL 解析出正式 release 版本号（目录形态可能已变，请人工确认后用 FFMPEG_VERSION=x.y.z 重跑）"
fi
TARBALL_NAME="ffmpeg-${FFMPEG_VERSION}.tar.xz"
log "目标版本 = ffmpeg $FFMPEG_VERSION"

if ! fetch_official_sha256 "$FFMPEG_VERSION"; then
    printf '%s\n' "$INDEX_HTML" | grep -oE "${TARBALL_NAME}[.a-z0-9]*" | sort -u | sed 's/^/    官方目录里的同名条目: /' >&2 || true
    fail_pre "ffmpeg.org 上取不到 ${TARBALL_NAME} 的官方 SHA256 —— 这就是 W3 的阻塞点：第 4 类需要「输入可钉定」。请把上面列出的端点交人工核对，不要改用自算值继续"
fi
log "官方摘要端点 $SHA_SOURCE_KIND → $SOURCE_SHA256"

# ------------------------------ 2. 下载 + 校验 + 解压 ------------------------------
cd "$OUT_DIR"
# M-96：tarball 走 FFMPEG_TARBALL_BASE（与摘要端点解耦，见文件头同源告警）。
run curl -fsSL --max-time 600 -o "$TARBALL_NAME" "${FFMPEG_TARBALL_BASE%/}/${TARBALL_NAME}"
ACTUAL_SHA="$(shasum -a 256 "$TARBALL_NAME" | cut -d' ' -f1)"
if [ "$ACTUAL_SHA" != "$SOURCE_SHA256" ]; then
    fail_check "tarball SHA256 与官方公布值不符：期望 $SOURCE_SHA256 实得 $ACTUAL_SHA（下载链路被替换或版本轮转，spike 停在这里）"
fi
log "tarball 校验通过（$ACTUAL_SHA）"
# M-96：解压前先看成员表——拒绝绝对路径与 `..` 穿越，并要求恰好一个顶层目录。
# 旧形态裸 `tar -xf`，归档里的绝对路径/穿越成员会写到 OUT_DIR 之外。
TAR_LIST="$(tar -tf "$TARBALL_NAME")"
if printf '%s\n' "$TAR_LIST" | grep -qE '(^/|(^|/)\.\.(/|$))'; then
    fail_check "tarball 含绝对路径或 .. 成员，拒绝解压"
fi
TAR_TOP_DIRS="$(printf '%s\n' "$TAR_LIST" | awk -F/ 'NF > 1 { print $1 }' | sort -u)"
if [ -z "$TAR_TOP_DIRS" ] || [ "$(printf '%s\n' "$TAR_TOP_DIRS" | wc -l | tr -d ' ')" != "1" ]; then
    fail_check "tarball 顶层目录不唯一（实得：${TAR_TOP_DIRS:-<无>}），拒绝解压"
fi
run tar --no-same-owner -xf "$TARBALL_NAME"

# ------------------------------ 3. 依赖 + 构建 ------------------------------
if [ "$SKIP_DEPS" != "1" ]; then
    run brew install "${BREW_DEPS[@]}"
else
    log "SKIP_DEPS=1：跳过 brew install，假设 nasm/pkg-config/x264/lame 已就绪"
fi

# 显式把 brew 前缀喂给 pkg-config（Apple Silicon 是 /opt/homebrew、Intel 是 /usr/local，不写死）。
# --pkg-config-flags=--static 才是「链 .a 而不是 .dylib」的关键，但它只影响 pkg-config 输出的 flag，
# 仍可能有库经 --disable-autodetect 之外的路径被拽进来——故下面必验 otool。三个 .pc 位置都要给：
# x264 与 lame 各自 opt 目录下一份、brew 的聚合 lib/pkgconfig 又一份；少给一处就会出现
# 「--enable-libx264 被 configure 静默忽略」这种假自包含前兆。
BREW_PREFIX="$(brew --prefix)"
export PKG_CONFIG_PATH="${BREW_PREFIX}/opt/x264/lib/pkgconfig:${BREW_PREFIX}/opt/lame/lib/pkgconfig:${BREW_PREFIX}/lib/pkgconfig:${PKG_CONFIG_PATH:-}"

SRC_DIR="$OUT_DIR/ffmpeg-${FFMPEG_VERSION}"
START_TS="$(date +%s)"
run "${SRC_DIR}/configure" "${CONFIGURE_ARGS[@]}"
run make "-j${JOBS}"
run make install
BUILD_SECONDS=$(( $(date +%s) - START_TS ))
log "构建耗时 ${BUILD_SECONDS}s"

FFMPEG_BIN="$OUT_DIR/prefix/bin/ffmpeg"
[ -x "$FFMPEG_BIN" ] || fail_check "构建产物里没有可执行的 $FFMPEG_BIN"

# ------------------------------ 4. 验收（自包含判据） ------------------------------
ARCHS="$(lipo -archs "$FFMPEG_BIN")"
log "lipo -archs = $ARCHS"
# ① 架构必须是 arm64（出现 x86_64 说明被宿主 toolchain 带偏，spike 的直接目的就没达到）。
case " $ARCHS " in
    *" arm64 "*) ;;
    *) fail_check "产物架构为 [$ARCHS]，不含 arm64" ;;
esac

OTOOM_LINES="$("$FFMPEG_BIN" -hide_banner -version >/dev/null 2>&1 && otool -L "$FFMPEG_BIN" | tail -n +2)"
printf '%s\n' "$OTOOM_LINES" | sed 's/^/    otool: /'
# ② otool 里只能出现系统路径（/usr/lib、/System/Library）。任何 /opt/homebrew、@rpath、@loader_path
#    都意味着 dylib 没被静态化 —— 那种产物发给用户就是 `dyld: Library not loaded`（当初否决 bottle 的同一理由）。
if grep -qE '(/opt/homebrew|/usr/local|@rpath|@loader_path)' <<<"$OTOOM_LINES"; then
    fail_check "otool -L 出现非系统库（dylib 闭包未静态化）：该产物不可分发，W3 需要显式加 --enable-* 的静态库路径或改用 -static-libgcc 类参数"
fi
log "自包含检查通过：全部依赖均为系统库"

# ③ 功能面：项目实际用到的两个编码器必须在（libx264 转码、libmp3lame 音频），
#    以及 HLS/RTMP 输入与 https（SecureTransport）—— 少一个就是「能跑但不能录」。
ENCODERS="$("$FFMPEG_BIN" -hide_banner -encoders 2>/dev/null || true)"
for want in libx264 libmp3lame; do
    grep -q " $want" <<<"$ENCODERS" || fail_check "缺少编码器 $want（项目录制链路依赖它）"
done
"$FFMPEG_BIN" -hide_banner -protocols 2>/dev/null | grep -q '^ *https' || fail_check "无 https 支持（SecureTransport 未生效）"
# hls 要按**整字段**匹配：`grep hls` 会同时命中 theora/hevc 之类含 "hls" 子串的条目，判不出真实缺失。
"$FFMPEG_BIN" -hide_banner -demuxers 2>/dev/null | grep -qE '(^|[[:space:]])hls([[:space:]]|$)' ||
    fail_check "无 hls demuxer（直播拉流主路径会失效）"

# ④ 真跑一次：1s testsrc → libx264 mp4，再 copy 成 ts。比 -version 更能证明「用户拿到能编码」。
"$FFMPEG_BIN" -hide_banner -loglevel error -y -f lavfi -i testsrc=size=320x240:rate=25 -t 1 \
    -c:v libx264 -preset ultrafast "$OUT_DIR/smoke.mp4"
"$FFMPEG_BIN" -hide_banner -loglevel error -y -i "$OUT_DIR/smoke.mp4" -c copy "$OUT_DIR/smoke.ts"
[ -s "$OUT_DIR/smoke.ts" ] || fail_check "转码冒烟产物为空文件"
log "转码冒烟通过：smoke.mp4 / smoke.ts"

# ------------------------------ 5. 产出 W1 第 4 类证据三件套 ------------------------------
PROVENANCE_REF="spike:$(hostname):$(date -u +%Y-%m-%dT%H:%M:%SZ)"
cat >"$REPORT_JSON" <<EOF
{
  "kind": "W2-spike",
  "ffmpeg_version": "${FFMPEG_VERSION}",
  "source_sha256": "${SOURCE_SHA256}",
  "source_sha256_endpoint": "${SHA_SOURCE_KIND}",
  "recipe_args": "$(printf '%s ' "${CONFIGURE_ARGS[@]}")",
  "recipe_sha256": "${RECIPE_SHA}",
  "provenance_ref": "${PROVENANCE_REF}",
  "build_seconds": ${BUILD_SECONDS},
  "lipo_archs": "${ARCHS}",
  "otool_system_only": true,
  "encoders_ok": ["libx264", "libmp3lame"],
  "binary": "${FFMPEG_BIN}"
}
EOF

log "全部验收通过。报告：$REPORT_JSON"
log "下一步（W3）需先把上面 source_sha256/recipe_sha256 交人工核对，再决定是否接入发布链 —— 未批准前不改 build-release.yml。"
