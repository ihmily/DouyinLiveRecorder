# -*- mode: python ; coding: utf-8 -*-
# 本文件由 build_exe.py 自动生成，请勿手工编辑（修改请改 build_exe.py）
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

datas = [
    ('src/javascript', 'src/javascript'),   # JS 签名脚本（src/__init__.py 经 __file__ 定位 → _internal/src/javascript）
    ('i18n', 'i18n'),                       # gettext 翻译文件（i18n.py 经 __file__ 定位 → _internal/i18n）
    ('web', 'web'),                         # Web 面板静态资源（src/web_api.py 经 __file__ 定位 → _internal/web）
]
# 注意：config/ 不在此处（不进 _internal），由 copy_external_binaries 复制到 exe 同级目录，
# 以便程序在运行时直接读写配置。ffmpeg/ node/ 同理。
# customtkinter 的主题 JSON 等资源文件
datas += collect_data_files('customtkinter')

hidden_common = [
    'i18n',                          # main.py 内部延迟导入
    'src.http_clients.async_http',   # main.py 经 __import__ 动态导入
    'h2',                            # httpx[http2] 懒加载依赖
]
# uvicorn 的协议/事件循环模块均为运行时按字符串导入，必须全量收集
hidden_web = hidden_common + collect_submodules('uvicorn')

# 注意：PyInstaller 6.x 已移除 cipher / zipped_data / zipfiles，spec 语法为 v6 风格
a_cli = Analysis(['main.py'], pathex=[], datas=datas, hiddenimports=hidden_common,
                 excludes=['tkinter', 'customtkinter', 'pystray', 'PIL',
                           'fastapi', 'uvicorn', 'starlette'],
                 noarchive=False)
a_gui = Analysis(['gui.py'], pathex=[], datas=[], hiddenimports=hidden_common,
                 excludes=['fastapi', 'uvicorn', 'starlette'], noarchive=False)
a_web = Analysis(['web.py'], pathex=[], datas=[], hiddenimports=hidden_web,
                 excludes=['tkinter', 'customtkinter', 'pystray'], noarchive=False)

pyz_cli = PYZ(a_cli.pure)
pyz_gui = PYZ(a_gui.pure)
pyz_web = PYZ(a_web.pure)

exe_cli = EXE(pyz_cli, a_cli.scripts, [], exclude_binaries=True,
              name='DouyinLiveRecorder', console=True, contents_directory='_internal')
exe_gui = EXE(pyz_gui, a_gui.scripts, [], exclude_binaries=True,
              name='DouyinLiveRecorder-GUI', console=False, contents_directory='_internal')
exe_web = EXE(pyz_web, a_web.scripts, [], exclude_binaries=True,
              name='DouyinLiveRecorder-Web', console=True, contents_directory='_internal')

coll = COLLECT(
    exe_cli, a_cli.binaries, a_cli.datas,
    exe_gui, a_gui.binaries, a_gui.datas,
    exe_web, a_web.binaries, a_web.datas,
    strip=False, upx=False, name='DouyinLiveRecorder',
)
