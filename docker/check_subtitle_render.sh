#!/bin/sh
# 镜像自检：确认「中文 ASS 字幕能真的画到画面上」。
#
# 这个场景很容易翻车——容器里没中文字体时，ffmpeg 的 ass 滤镜不会报错，
# 但一个汉字都渲染不出来，最后拿到的视频看起来就是"没有字幕"。
# 做法是拿一段纯黑视频烧中文字幕，再统计画面里的非黑像素。

set -e

FONT_NAMES="WenQuanYi Micro Hei|Microsoft YaHei"
OUT_DIR=/tmp/subtitle_check
W=640
H=360

mkdir -p "$OUT_DIR"
cd "$OUT_DIR"

ffmpeg -y -v error -f lavfi -i "color=c=black:s=${W}x${H}:r=25:d=2" \
    -pix_fmt yuv420p black.mp4

check() {
    font="$1"
    cat > test.ass <<EOF
[Script Info]
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080
WrapStyle: 2

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, OutlineColour, BackColour, Bold, Italic, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Danmaku,${font},70,&H00FFFFFF,&H00000000,&H80000000,0,0,1,2,0,8,40,40,36,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 0,0:00:00.00,0:00:02.00,Danmaku,,0,0,0,,中文字幕渲染检测ABC123
EOF

    ffmpeg -y -v error -i black.mp4 -vf "ass=test.ass" \
        -c:v libx264 -preset ultrafast -pix_fmt yuv420p out.mp4

    ffmpeg -v error -i out.mp4 -pix_fmt gray -f rawvideo - | python3 -c "
import sys
data = sys.stdin.buffer.read()
w, h = ${W}, ${H}
frame = w * h
n = len(data) // frame
if n == 0:
    print('FAIL: 没有解出任何帧')
    sys.exit(1)
mid = data[frame * (n // 2):frame * (n // 2 + 1)]
lit = sum(1 for b in mid if b > 60)
print('${font}' + f' -> 帧数={n}, 非黑像素={lit}')
if lit < 200:
    print('FAIL: 中文字幕没有渲染出来（缺字体或字体映射没生效）')
    sys.exit(1)
print('OK: 中文字幕渲染正常')
"
}

IFS='|'
for font in $FONT_NAMES; do
    check "$font"
done

# emoji 单独看一眼：libass 对彩色位图 emoji 的支持因版本而异，画不出来不算致命
# （只是弹幕里的表情变成方块），所以这里只报告不失败。
cat > emoji.ass <<EOF
[Script Info]
ScriptType: v4.00+
PlayResX: 640
PlayResY: 360
WrapStyle: 2

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, OutlineColour, BackColour, Bold, Italic, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Danmaku,Noto Color Emoji,70,&H00FFFFFF,&H00000000,&H80000000,0,0,1,2,0,8,40,40,36,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 0,0:00:00.00,0:00:02.00,Danmaku,,0,0,0,,emoji检测
EOF

ffmpeg -y -v error -i black.mp4 -vf "ass=emoji.ass" \
    -c:v libx264 -preset ultrafast -pix_fmt yuv420p emoji.mp4

ffmpeg -v error -i emoji.mp4 -pix_fmt gray -f rawvideo - | python3 -c "
import sys
data = sys.stdin.buffer.read()
w, h = 640, 360
frame = w * h
n = len(data) // frame
if n == 0:
    print('WARN: emoji 检查没有解出帧')
    sys.exit(0)
mid = data[frame * (n // 2):frame * (n // 2 + 1)]
lit = sum(1 for b in mid if b > 60)
print(f'Noto Color Emoji -> 帧数={n}, 非黑像素={lit}')
print('OK: emoji 渲染正常' if lit > 200 else 'WARN: emoji 可能显示为方块（不影响中文弹幕）')
"
