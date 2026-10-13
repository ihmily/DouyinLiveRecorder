# -*- coding: utf-8 -*-
"""把 PyInstaller 产物组装成「双击即用」的绿色版目录。

PyInstaller 每次构建都会清空 dist/<name>，所以随包的运行时、配置和使用说明
必须在构建之后重新铺一遍——这个脚本就是干这件事的，可反复执行。

用法（在仓库根目录）：
    .buildvenv\\Scripts\\python.exe assemble_portable.py
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TARGET = ROOT / 'dist' / 'DouyinLiveRecorder'

# 随包携带的运行时：静态 ffmpeg（免安装、无 DLL 依赖）+ 便携 node（弹幕签名用）
FFMPEG_SRC = Path(r'H:\ffmpeg-7.1-essentials_build\bin')
NODE_SRC = Path(r'C:\Users\Admin\.workbuddy\binaries\node\versions\22.22.2-6\node.exe')

URL_CONFIG = """# 把要录制的直播间网址一行一个贴在这里，保存后双击 DouyinLiveRecorder.exe 即可开始录制。
#
# 写法要求：
#   1. 一行一个完整网址，前后不要有空格、不要写中文说明
#   2. 不想录某一行，就在行首加 # 注释掉（程序检测到后会自动收尾并生成字幕）
#   3. 网址示例：https://live.douyin.com/123456789012
#
# 下面两行是示例，改成你自己的网址后把行首的 # 去掉即可：
# https://live.douyin.com/123456789012
# https://live.douyin.com/987654321098
"""

README = """抖音直播录制（带弹幕）绿色版  使用说明
==================================================

【怎么用，三步】

1. 用记事本打开 config\\URL_config.ini
   把要录的直播间网址一行一个贴进去，保存。

2. 双击本目录下的 DouyinLiveRecorder.exe
   黑色窗口会显示正在录制的直播间状态。
   这个黑窗口要一直开着，关掉它录制就停了。

3. 录好的东西在 downloads 文件夹里，按主播分了子文件夹。


【录完有什么】

    主播名_日期_时间_000.mp4        原始分段录像
    主播名_日期_时间_000_弹幕.mp4   烧好弹幕的版本（要看弹幕就播这个）
    主播名_日期_时间.danmaku.jsonl  弹幕原始数据（一条不少）
    主播名_日期_时间.danmaku.srt    外挂字幕（播放器可直接挂）
    主播名_日期_时间.danmaku.ass    烧录用字幕

  注意：字幕和"弹幕版视频"是这一场录制结束的那一刻才生成的，
  直播进行中只有 .jsonl 在变大，这是正常的。

  结束一场录制请用"把 URL_config.ini 里那行网址加 # 注释掉"的方式，
  或者直接等主播下播；不要直接关黑窗口，字幕可能来不及生成。


【弹幕怎么调 —— config\\config.ini】

  用记事本打开 config\\config.ini，找到"弹幕设置"那一段，
  每一项上面都有中文注释说明。改完保存，重启本程序生效。

  最常用的几个：
    弹幕显示方式(滚动/固定)    滚动=从右往左飘屏；固定=停在顶部一条条换
    弹幕最多同时显示行数        默认4，直播很热闹可以调到 6~8
    弹幕单条显示时长(秒)        滚动模式下=飘完一屏的秒数，默认8；想慢就调大
    弹幕字号(像素)              默认40，竖屏或4K录制可按需调到 30~60
    弹幕礼物最低钻石数          填1000就只显示嘉年华这种大礼物
    弹幕字幕包含的消息类型      想让进场、点赞也飘出来就补上 member,like,social
    录制完成后自动将弹幕烧录到视频  关掉就只出字幕文件、不烧进画面

  完整数据永远在 .danmaku.jsonl 里，画面上放不下的弹幕一条都不少。


【目录里都是什么】

    DouyinLiveRecorder.exe   主程序
    _internal\\               程序运行库，不要动
    ffmpeg\\                  录制和烧字幕用的工具，不要动
    runtime\\                 弹幕签名用的 Node 运行时，不要动
    config\\                  配置文件（就改这里）
    downloads\\               录好的视频都在这里
    logs\\                    运行日志，出问题看这里
    backup_config\\           配置备份


【常见问题】

  问：双击后黑窗口一闪就没了？
  答：config\\URL_config.ini 里没填网址（或全被 # 注释掉了），
      程序会提示后等待，填好网址再启动。

  问：录不到弹幕 / 没有 .danmaku 文件？
  答：看 config.ini 里"是否录制弹幕"是不是"是"；
      再看 logs 里的日志有没有"签名失败"字样。

  问：提示缺少 xxx？
  答：本绿色版自带 ffmpeg 和 Node，不需要额外安装任何东西，
      也不需要 Python 环境。

  问：杀毒软件报警？
  答：打包的程序常被误报，加入白名单即可。
"""


def write_gbk(path: Path, text: str) -> None:
    """记事本友好：Windows 下用 GBK 存，双击打开不乱码。"""
    path.write_bytes(text.replace('\n', '\r\n').encode('gbk'))


def main() -> None:
    if not (TARGET / 'DouyinLiveRecorder.exe').exists():
        raise SystemExit(f'未找到打包产物：{TARGET / "DouyinLiveRecorder.exe"}，请先执行 PyInstaller 构建')

    for sub in ('config', 'downloads', 'logs', 'backup_config', 'ffmpeg', 'runtime'):
        (TARGET / sub).mkdir(parents=True, exist_ok=True)

    for name in ('ffmpeg.exe', 'ffprobe.exe'):
        src = FFMPEG_SRC / name
        if src.exists():
            shutil.copy2(src, TARGET / 'ffmpeg' / name)
            print(f'  + ffmpeg/{name}')
        else:
            print(f'  ! 缺少 {src}，请手动放入')

    if NODE_SRC.exists():
        shutil.copy2(NODE_SRC, TARGET / 'runtime' / 'node.exe')
        print('  + runtime/node.exe')
    else:
        print(f'  ! 缺少 {NODE_SRC}，弹幕签名会失效')

    # 配置：仓库里那份带中文注释的默认配置（UTF-8 with BOM，程序按 utf-8-sig 读取）
    shutil.copy2(ROOT / 'config' / 'config.ini', TARGET / 'config' / 'config.ini')
    print('  + config/config.ini')

    write_gbk(TARGET / 'config' / 'URL_config.ini', URL_CONFIG)
    write_gbk(TARGET / '使用说明.txt', README)
    print('  + config/URL_config.ini')
    print('  + 使用说明.txt')

    total = sum(f.stat().st_size for f in TARGET.rglob('*') if f.is_file())
    print(f'\n绿色版就绪：{TARGET}')
    print(f'总大小：{total / 1024 / 1024:.0f} MB')


if __name__ == '__main__':
    main()
