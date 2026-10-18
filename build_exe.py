#!/usr/bin/env python3
# -*- encoding: utf-8 -*-
#
# DouyinLiveRecorder 可执行文件打包脚本（本地 / GitHub Actions 通用）
#
# 一次构建产出三个入口（CLI / GUI / Web），共享同一发布目录的依赖与资源；
#     三个 exe 与 main.py / gui.py / web.py 的对应关系见下方「打包策略」树。
#
# 用法：
#     python build_exe.py             # 打包并生成 zip 产物
#     python build_exe.py --smoke     # 打包后额外运行冒烟测试（CI 推荐）
#     python build_exe.py --no-zip    # 只打包不压缩
#     python build_exe.py --no-runtime # 跳过 ffmpeg/node 打包（交由用户运行时自动下载，减小分发体积）
#     python build_exe.py --dual      # 同时生成 lite（无运行时）与 full（下载并打包 ffmpeg+node）两个 zip
#     python build_exe.py --require-pinned # 运行时二进制缺 SHA256 钉定即终止构建（CI 默认开启，SEV-10 fail-closed）
#     python build_exe.py --pin-source verify # 拉取官方清单与内置钉定表比对（默认 off：不联网、行为不变）
#
# 打包策略（onedir + contents_directory='_internal'）—— 最终产物结构：
#     dist/DouyinLiveRecorder/
#     ├── DouyinLiveRecorder(.exe)        CLI 录制核心（main.py，控制台）
#     ├── DouyinLiveRecorder-GUI(.exe)    图形界面（gui.py，无控制台窗口）
#     ├── DouyinLiveRecorder-Web(.exe)    Web 管理面板（web.py，控制台）
#     ├── config/ · ffmpeg/ · node/       运行时资源，一律与 exe 同级（不进 _internal/）
#     └── _internal/                      依赖包 + src/ 及打包资源（i18n/ web/ src/javascript）
#     划分依据：经 __file__ 定位的资源（i18n/ web/ src/javascript）随 contents_directory 收进
#     _internal/；经 sys.argv[0]/sys.executable 定位的（config/ ffmpeg/ node/）由本脚本在
#     COLLECT 之后复制到 exe 同级（见 copy_external_binaries / _prepare_url_config），
#     二者经 src/logger._app_root() 收敛到同一目录。
#     多入口共享依赖必须用 .spec 文件（命令行不支持多 Analysis），故本脚本动态生成
#     spec 后调用 PyInstaller。
#
# 产物：
#     dist/DouyinLiveRecorder/                          发布目录（3 个 exe + 运行时目录 + _internal/ 依赖）
#     dist/DouyinLiveRecorder-v{ver}-{os}-{arch}{suffix}.zip  压缩包（普通构建 suffix 为空，--dual 为 -lite/-full）
#
import argparse
import hashlib
import http.client
import json
import os
import platform
import re
import shutil
import signal
import subprocess
import sys
import tarfile
import time
import urllib.request
import zipfile
from pathlib import Path
from typing import Any, cast

PROJECT_ROOT = Path(__file__).resolve().parent
APP_NAME = "DouyinLiveRecorder"
DIST_DIR = PROJECT_ROOT / "dist"
RELEASE_DIR = DIST_DIR / APP_NAME
SPEC_PATH = PROJECT_ROOT / "DouyinLiveRecorder.spec"
# 与下方 spec 模板中的 contents_directory 保持一致：冻结后所有资源落在 _internal/
CONTENTS_DIR = "_internal"
IS_WIN = sys.platform == "win32"
EXE_SUFFIX = ".exe" if IS_WIN else ""

# 体积优化：运行期不可达模块的排除清单（每项体积为 2026-09-24 本机 Windows lite 构建实测值，
# 基线发布目录 82.77MB）。进表判据只有一条：**能指出它在产物里、且运行期不可达**——
# 靠「看着像没用」排除会在某个平台/某条分支上变成 ModuleNotFoundError（冻结产物里该错误只在
# 运行时炸，测试覆盖不到）。新增项必须：① 用 scripts/report_bundle_size.py 复测体积；
# ② 本地 `python build_exe.py --smoke --no-runtime` 三入口冒烟通过后才可提交。
BLOAT_EXCLUDES: tuple[str, ...] = (
    # pydantic v1 兼容层自带的 mypy 插件：pydantic/v1/mypy.py 顶层就是
    # `from mypy.errorcodes import ErrorCode`，于是整个 mypy 包（0.71MB / 69 个文件，含 69 个
    # .pyd）被拖进产物——这是基线里唯一一处「开发工具链泄漏」。pydantic/v1/__init__.py 自身
    # 不 import mypy，故只排除该插件模块即可，pydantic.v1 其余部分不受影响。
    "pydantic.v1.mypy",
    # Pillow 插件：本仓对 PIL 的全部用法就是 Image.new + ImageDraw 画托盘图标
    # （gui.py / src/web_tray.py），编解码与字体后端均不可达。容错依据（不是推测）：
    # PIL/ImageFont.py 里 `from . import _imagingft as core` 包在 try/except ImportError →
    # DeferredError，PIL/Image.py 的 init() 对每个插件同样是 try/except ImportError，
    # 故缺失插件只在**真的调用**时才报错，不会在导入期炸。
    "PIL._avif",  # 7.52MB：Pillow 12 自带 libavif，是产物内最大的单个非解释器文件
    "PIL._imagingft",  # 2.07MB：FreeType；全仓无 ImageFont / truetype 调用点
    "PIL._webp",  # 0.40MB
    "PIL._imagingcms",  # 0.26MB
    "PIL._imagingmath",  # 0.02MB
    # uvicorn 的可选实现依赖：web.py 用 uvicorn.Server(uvicorn.Config(...))，http/loop/ws 三项
    # 均为默认 "auto"，而三处 auto 实现内部就是「try 可选实现 except ImportError 回退」
    # （httptools→h11、uvloop→asyncio、wsproto→websockets）。故排除只影响「显式指定该实现」
    # 的用法，本仓没有；watchfiles 仅 --reload 路径使用，冻结产物从不 reload。
    "httptools",  # 0.17MB
    "watchfiles",  # 0.61MB
    "uvloop",  # 仅 POSIX 安装；Windows 无此包，写明以免将来换平台构建时漏排
    "zuvloop",
    "wsproto",
    # 开发 / 测试工具链：都不在 requirements.txt 里、运行期不会被导入，但一旦有人误加一个顶层
    # import 就会被静默带进对外分发的 zip（mypy 正是这样进来的）。显式排除把「误收集」从
    # 「事后在 report_bundle_size 里发现」变成「不可能发生」，与下面的测试同口径。
    "pytest",
    "_pytest",
    "mypy",
    "mypyc",
    "mypy_extensions",
    "basedpyright",
    "black",
    "blackd",
    "blib2to3",
    "isort",
    "coverage",
    "pip",
    "pygments",
    "nodejs_wheel",  # 114MB：本仓 venv 里有而 requirements.txt 没有，误收集即炸体积
    "py",
    "iniconfig",
    "pluggy",
)

# Qt 死重清理（2026-10-17 GUI 迁移 PySide6 后实测）：PyInstaller 的 hook-PySide6.py 按「插件类型
# 整目录」收集 Qt 插件（hook 只按类型过滤、不逐个判断），插件的链接依赖再被递归带进包，于是
# 几个用不到的 Qt 模块被间接拖入产物。判据与 BLOAT_EXCLUDES 同源（**能指出它在产物里 + 运行期
# 不可达**），但 excludes 只对模块生效、管不到 hook 收集的 DLL，故只能在 COLLECT 之后按文件名删。
# 实测判据：对 _internal/PySide6/ 下全部 dll/pyd 做链接依赖扫描，下列文件**零反向引用**（除彼此
# 与那两个插件本体之外）；正向扫描确认删掉后不出现任何无法解析的导入。
QT_BLOAT_FILES: tuple[str, ...] = (
    # Mesa 软件 OpenGL（19.68MB，产物内最大单文件）：hook 的 collect_extra_binaries 无条件收它
    # （_collect_all_or_none(['opengl32sw.dll'])），不看应用是否真用 OpenGL。本仓 GUI 是纯
    # QtWidgets，走 Qt6Gui 的 raster 后端，不创建任何 GL 上下文。
    "opengl32sw.dll",
    # Qt VirtualKeyboard 是 Qml/Quick 三个 DLL 进包的唯一入口链：
    # 插件 qtvirtualkeyboardplugin.dll（platforminputcontexts 整目录收集）→ Qt6VirtualKeyboard
    # → Qt6Quick → Qt6Qml / Qt6QmlModels / Qt6QmlMeta / Qt6QmlWorkerScript / Qt6OpenGL。
    # 本仓无虚拟键盘用法，整条链一并剪掉（合计约 15.1MB）。
    "Qt6VirtualKeyboard.dll",
    "Qt6Quick.dll",
    "Qt6Qml.dll",
    "Qt6QmlModels.dll",
    "Qt6QmlMeta.dll",
    "Qt6QmlWorkerScript.dll",
    # 只被 Qt6Quick 链接（QtWidgets 不链它），1.90MB。
    "Qt6OpenGL.dll",
    # 只被 imageformats/qpdf.dll 链接，本仓不渲染 PDF，4.41MB。
    "Qt6Pdf.dll",
    # 两个插件本体：删了它们才不会在运行时 dlopen 上面那批 DLL（插件是运行时按目录尝试加载的，
    # 只删 DLL 不删插件，Qt 仍会去加载插件并因缺依赖报错）。
    "plugins/imageformats/qpdf.dll",
    "plugins/platforminputcontexts/qtvirtualkeyboardplugin.dll",
)


# i18n 资源清单（替代整目录拷贝）：运行时只消费 .mo / .json / .yaml（见 i18n.py 的加载优先级），
# *.po 是翻译源文件、冻结产物里属死重量（0.12MB）。这里按文件逐个列出而非写 ('i18n','i18n')，
# 因为目录形态会把 .po 一起带进分发包；新增语言只要把文件放进 i18n/ 就会被本函数自动纳入，
# 不需要改 spec 模板（避免「加语言忘了改打包清单」这类漂移）。
def i18n_datas_entries() -> list[tuple[str, str]]:
    root = PROJECT_ROOT / "i18n"
    if not root.is_dir():
        return []
    entries: list[tuple[str, str]] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix == ".po":
            continue
        subdir = path.parent.relative_to(root).as_posix()
        dest = "i18n" if subdir == "." else f"i18n/{subdir}"
        entries.append((path.relative_to(PROJECT_ROOT).as_posix(), dest))
    return entries


# 动态生成的 PyInstaller spec 模板：
# - 三个 Analysis / EXE，共用一个 COLLECT（依赖去重，体积约为独立打包的 1/3）
# - 数据文件只挂在 CLI 的 Analysis 上即可（COLLECT 合并时统一落盘）
SPEC_TEMPLATE = """\
# -*- mode: python ; coding: utf-8 -*-
# 本文件由 build_exe.py 自动生成，请勿手工编辑（修改请改 build_exe.py）
from PyInstaller.utils.hooks import collect_submodules

# 体积优化排除项（清单与每项实测体积见 build_exe.py 的 BLOAT_EXCLUDES）
excludes_bloat = {bloat_excludes}

datas = [
    ('src/javascript', 'src/javascript'),   # JS 签名脚本（src/__init__.py 经 __file__ 定位 → _internal/src/javascript）
    *{i18n_datas},   # 翻译目录（剔除 *.po 源文件；由 build_exe.i18n_datas_entries() 生成）
    ('web', 'web'),                         # Web 面板静态资源（src/web_api.py 经 __file__ 定位 → _internal/web）
]
# 注意：config/ 不在此处（不进 _internal），由 copy_external_binaries 复制到 exe 同级目录，
# 以便程序在运行时直接读写配置。ffmpeg/ node/ 同理。
# [2026-10-03 阶段5] collect_data_files('customtkinter') 已随该依赖摘除而移除（无资源可收）；
# excludes 里的 'customtkinter' 条目按 fastapi 同款防御口径保留（防 venv 残留回渗打包）。
#
# [2026-10-17] GUI 入口改走 PySide6（src/gui_qt/），收集由 PyInstaller 自带的 hook-PySide6.py
# 完成（Qt6 平台插件 / ANGLE / ICU 等），本 spec **不加任何 collect 调用**：hook 已按「实际
# 导入的 Qt 模块」逐个收，而 collect_all('PySide6') 会把整个 647MB 的轮子（含 194MB 的
# Qt6WebEngineCore）拖进产物。同理，'PySide6' 只加在 CLI/Web 两个 Analysis 的 excludes 上
# ——GUI 必须收它，加了反而会让 GUI exe 起不来。

hidden_common = [
    'i18n',                          # main.py 内部延迟导入
    'src.async_http',              # main.py 经 __import__ 动态导入
    'h2',                            # httpx[http2] 懒加载依赖
    'exejs',                         # PyExecJS 继任者，try/except 条件导入需显式收集
]
# uvicorn 的协议/事件循环模块均为运行时按字符串导入，必须全量收集
hidden_web = hidden_common + collect_submodules('uvicorn')

# 注意：PyInstaller 6.x 已移除 cipher / zipped_data / zipfiles，spec 语法为 v6 风格
# excludes 一律以 excludes_bloat 打头：三个入口共用同一个 _internal（COLLECT 合并去重），
# 只在某一个 Analysis 上排除没有意义——只要 GUI 收了它，CLI 的产物里照样带着。
a_cli = Analysis(['main.py'], pathex=[], datas=datas, hiddenimports=hidden_common,
                 excludes=excludes_bloat + ['tkinter', 'customtkinter', 'pystray', 'PIL',
                           'fastapi', 'uvicorn', 'starlette', 'brotlicffi', 'PySide6'],
                 noarchive=False)
a_gui = Analysis(['gui.py'], pathex=[], datas=[], hiddenimports=hidden_common,
                 excludes=excludes_bloat + ['fastapi', 'uvicorn', 'starlette', 'brotlicffi'], noarchive=False)
a_web = Analysis(['web.py'], pathex=[], datas=[], hiddenimports=hidden_web,
                 excludes=excludes_bloat + ['tkinter', 'customtkinter', 'pystray', 'brotlicffi',
                           'PySide6'], noarchive=False)

pyz_cli = PYZ(a_cli.pure)
pyz_gui = PYZ(a_gui.pure)
pyz_web = PYZ(a_web.pure)

exe_cli = EXE(pyz_cli, a_cli.scripts, [], exclude_binaries=True,
              name='{app}', console=True, contents_directory='_internal')
exe_gui = EXE(pyz_gui, a_gui.scripts, [], exclude_binaries=True,
              name='{app}-GUI', console=False, contents_directory='_internal')
exe_web = EXE(pyz_web, a_web.scripts, [], exclude_binaries=True,
              name='{app}-Web', console=True, contents_directory='_internal')

coll = COLLECT(
    exe_cli, a_cli.binaries, a_cli.datas,
    exe_gui, a_gui.binaries, a_gui.datas,
    exe_web, a_web.binaries, a_web.datas,
    strip=False, upx=False, name='{app}',
)
"""


# 解析 pyproject.toml 中的 version 字段（版本唯一事实源），返回版本字符串；解析失败回退 "0.0.0"
def read_version() -> str:
    text = (PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    m = re.search(r'^version\s*=\s*["\'](.+?)["\']', text, re.M)
    return m.group(1) if m else "0.0.0"


# 打包前预编译所有入口脚本与 src/ 源码，提前以文件名+行号暴露语法错误
def preflight_syntax_check() -> None:
    # 曾出现 gui.py 首行编码注释被破坏（丢失行首 '#'）导致三平台 CI 全部在 PyInstaller
    # Analysis 阶段报 IndentationError，且报错混在长日志里不易定位；提前编译可在几秒内
    # 以明确的文件名+行号失败，避免浪费 CI 时间。
    import py_compile

    targets = [PROJECT_ROOT / name for name in ("main.py", "gui.py", "web.py", "i18n.py", "msg_push.py")]
    targets += sorted((PROJECT_ROOT / "src").rglob("*.py"))
    for path in targets:
        if not path.is_file():
            continue
        try:
            _ = py_compile.compile(str(path), doraise=True)
        except py_compile.PyCompileError as exc:
            print(f"[build] 预检失败：{path.relative_to(PROJECT_ROOT)} 存在语法错误：\n{exc.msg}")
            sys.exit(1)
        # 额外守护：首行以空白开头即文件头被破坏（py_compile 已能捕获丢 '#' 的情形，
        # 这里再堵 BOM 以外的不可见前缀，防编辑器/网页端粘贴引入脏字节）。
        head = path.read_bytes()[:16]
        if head[:1] in (b" ", b"\t"):
            print(f"[build] 预检失败：{path.relative_to(PROJECT_ROOT)} 首行以空白开头（文件头可能被破坏）")
            sys.exit(1)
    print(f"[build] 预检通过：{len(targets)} 个源码文件语法正常")


# 生成 spec 模板并调用 PyInstaller 完成 CLI/GUI/Web 三入口 onedir 打包
def run_pyinstaller() -> None:
    preflight_syntax_check()
    _ = SPEC_PATH.write_text(
        SPEC_TEMPLATE.format(app=APP_NAME, bloat_excludes=list(BLOAT_EXCLUDES), i18n_datas=i18n_datas_entries()),
        encoding="utf-8",
    )
    print(f"[build] 已生成 spec：{SPEC_PATH}")
    cmd = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", str(SPEC_PATH)]
    print(f"[build] PyInstaller 命令：\n  {' '.join(cmd)}")
    _ = subprocess.run(cmd, check=True, cwd=PROJECT_ROOT)
    prune_qt_bloat()


# COLLECT 之后按文件名剪除 Qt 死重（清单与每项判据见 QT_BLOAT_FILES）
def prune_qt_bloat() -> None:
    # 放在 run_pyinstaller 末尾而不是 main 里：--dual 只跑一次 PyInstaller 就出两个 zip，
    # 挂在这里才能保证两条路径都剪到；且剪除对象是 COLLECT 的产物，紧邻生成点最不容易漏。
    qt_dir = RELEASE_DIR / CONTENTS_DIR / "PySide6"
    if not qt_dir.is_dir():
        print("[build] 产物内无 PySide6 目录，跳过 Qt 死重剪除")
        return
    freed = 0
    removed = 0
    for rel in QT_BLOAT_FILES:
        target = qt_dir / rel
        if not target.is_file():
            # 清单里的名字随 Qt/PyInstaller 版本可能变化：跳过而不是报错——
            # 少剪一项只是体积没降，多报错一次会让整轮构建在别人机器上红掉。
            continue
        freed += target.stat().st_size
        target.unlink()
        removed += 1
    if removed:
        print(f"[build] 已剪除 Qt 死重 {freed / 1048576:.2f}MB（{removed}/{len(QT_BLOAT_FILES)} 项命中）")


# 将仓库内 ffmpeg/node/config 复制到发布根目录（exe 同级），运行时可直接读写
def copy_external_binaries(include_runtime: bool = True) -> None:
    # 三者是运行时资源，必须与最终 exe 同级（而非收进 _internal/），程序才能直接读写配置、
    # 调用 FFmpeg / Node.js。仓库内缺失时不报错：运行时会下载对应平台的 ffmpeg / node；
    # include_runtime=False（--no-runtime）时跳过 ffmpeg/node，交用户首跑自动下载。
    if include_runtime:
        for name in ("ffmpeg", "node"):
            src = PROJECT_ROOT / name
            if not src.is_dir():
                continue
            has_exe = any(p.suffix == ".exe" for p in src.iterdir())
            if has_exe and not IS_WIN:
                print(f"[build] 跳过 {name}/（Windows 二进制，与当前平台不符）")
                continue
            dst = RELEASE_DIR / name
            _ = shutil.copytree(src, dst, dirs_exist_ok=True)
            print(f"[build] 已复制 {name}/ -> {dst}")
    else:
        print("[build] --no-runtime：跳过 ffmpeg/ 与 node/（用户首次运行时自动下载）")

    # SEV-2213（2026-09-23）：**绝不能整目录原样复制**。仓库根的 config/config.ini 与
    # config/URL_config.ini 含真实凭据（平台 Cookie / 代理账密 / Web 口令 / 内嵌 query token
    # 的房间地址），而 make_zip 会把发布目录整棵树压成对外分发的 zip —— 继 .gitignore 与
    # .dockerignore 之后的**第三条外发通道**，此前完全没有排除。改法：按「模板化」逐个写入
    # （结构保留、凭据置空）+ make_zip 前另有一道 assert_no_credentials_in_release 兜底；
    # 二者同源判据但不互相替代：这里是「不产生」，那里是「产生了就拦住」。
    _prepare_config_dir()


# 发布目录内**绝不允许**存在的凭据文件（SEV-2213）。与 .dockerignore 的 `config/config.ini` /
# `config/URL_config.ini` 两条排除项同源——同一批文件、同一份敏感判定，只是作用在「外发 zip」通道上。
CREDENTIAL_FILE_NAMES: tuple[str, ...] = ("config.ini", "URL_config.ini")


def _sanitized_config_text(text: str, *, fallback_header: str = "") -> str:
    # 把 config.ini 文本按「敏感键置空」重写为可分发模板，保留注释与节结构（产物仍是用户
    # 可直接编辑的模板，而非空文件）。
    # 敏感判定复用 src/web_config（is_sensitive_item + _looks_like_secret_value），不另写一份
    #   正则：那会造出第二份「什么算敏感」的事实源，两侧迟早漂移。
    # 用 configparser + 已知节名而非逐行正则：ini 的 section/key 认法（`=` 与 `:` 均可、
    #   键名大小写不敏感）与运行时读取完全一致，不会出现「面板认为敏感、打包器不认为」的缝。
    import configparser

    from src import web_config

    parser = configparser.ConfigParser(interpolation=None)
    # 保留键名原样大小写，避免写回时把键名改成小写形态。
    # 类型注记：ConfigParser 里 optionxform 是方法，实例赋值 str 会触发 mypy
    #   [method-assign]/[assignment]；这是 configparser 的既知惯用法（CPython 文档亦如此
    #   演示），故就地标注忽略，而不是绕开该赋值。
    parser.optionxform = str  # type: ignore[method-assign,assignment]
    try:
        parser.read_string(text)
    except configparser.Error:
        # 解析不了（损坏/异构 ini）：**不得**退回「原样复制」——那正是本次要堵的形态。
        # 返回只含表头的空模板，宁可让用户重新填，也不外发可能含凭据的原文。
        return fallback_header or "# config.ini 解析失败，已置为空白模板（原文件未分发）\n"

    lines: list[str] = []
    for section in parser.sections():
        lines.append(f"[{section}]")
        for key, value in parser.items(section):
            # 空值（未启用）本就不含凭据，原样保留；非空且命中敏感判定的一律置空。
            # web_config.is_sensitive_item 覆盖节白名单（Cookie / 账号密码 / Authorization）+ 键名
            #   模式（令牌/密码/授权码/token/secret/passwd/password/api_key/推送接口链接/推送地址/
            #   代理地址）；_looks_like_secret_value 兜住「键名正常但值里嵌 token」（与面板脱敏同口径）。
            if value.strip() and (
                web_config.is_sensitive_item(section, key) or web_config._looks_like_secret_value(value)
            ):
                lines.append(f"{key} = ")
            else:
                lines.append(f"{key} = {value}")
        lines.append("")
    return "\n".join(lines).rstrip("\n") + "\n"


def _sanitized_url_config_text() -> str:
    # URL_config.ini 一律重写为**单行注释样例**：该文件通篇是房间地址，而地址的 query 里可能
    # 内嵌平台 token（本仓在 _looks_like_secret_value 里已承认这一形态）。样例串与
    # _prepare_url_config() 写入口径逐字同源，避免两处各自演化。
    return "#https://live.douyin.com/000000000000\n"


def _prepare_config_dir() -> None:
    # 把发布目录的 config/ 写成**脱敏模板**（SEV-2213 的「不产生」一侧）。
    # 只写这两个已知文件；源目录里的其它文件（用户自建、无凭据）才走复制。
    cfg_dst = RELEASE_DIR / "config"
    cfg_dst.mkdir(parents=True, exist_ok=True)
    cfg_src = PROJECT_ROOT / "config"

    known = set(CREDENTIAL_FILE_NAMES)
    # 1) 凭据文件：从仓库源读取后脱敏重写（源不存在时落空白模板，绝不跳过）
    ini_src = cfg_src / "config.ini"
    template = (
        _sanitized_config_text(ini_src.read_text(encoding="utf-8-sig", errors="replace"))
        if ini_src.is_file()
        else "[录制设置]\n"
    )
    _ = (cfg_dst / "config.ini").write_text(template, encoding="utf-8")
    _ = (cfg_dst / "URL_config.ini").write_text(_sanitized_url_config_text(), encoding="utf-8")
    print(f"[build] 已生成脱敏配置模板 config/config.ini + config/URL_config.ini -> {cfg_dst}")

    # 2) 其余非凭据文件照常复制（保留「模板之外的附属文件也能带过去」行为）
    if cfg_src.is_dir():
        for item in sorted(cfg_src.iterdir()):
            if item.name in known or not item.is_file():
                continue
            _ = shutil.copy2(item, cfg_dst / item.name)
            print(f"[build] 已复制 config/{item.name} -> {cfg_dst / item.name}")


def assert_no_credentials_in_release() -> None:
    # SEV-2213 的「产生了就拦住」一侧：make_zip **之前**校验发布目录里那两份文件确实不含任何
    # 敏感键的真实值，命中即非零退出——与 .dockerignore 同源口径。
    # 为什么在 make_zip 前：zip 一旦生成就可能已被 copy/上传，事后再删已无意义。
    # 为什么不只看「文件存在」：文件**必须**存在（用户要能在 exe 同级编辑），真正要拦的是
    #   「里面还有凭据」，故判据是逐键比对源值，不是存在性。
    from src import web_config

    assert RELEASE_DIR.is_dir(), f"{RELEASE_DIR} 不存在，无从校验"
    cfg_dst = RELEASE_DIR / "config"

    problems: list[str] = []

    # ① URL_config.ini：必须是注释样例（既有的 _prepare_url_config 口径），不得含有效房间行
    url_cfg = cfg_dst / "URL_config.ini"
    if url_cfg.is_file():
        for n, line in enumerate(url_cfg.read_text(encoding="utf-8-sig", errors="replace").splitlines(), 1):
            stripped = line.strip()
            if stripped and not stripped.startswith("#"):
                problems.append(f"config/URL_config.ini:{n} 含未注释的有效行（可能内嵌房间/token）：{stripped[:80]!r}")

    # ② config.ini：逐键比对**仓库源文件的真实值**——命中即说明脱敏漏了该键。用「源值出现在
    #    发布文件里」作判据而不是「键名敏感」：前者是实际泄漏的事实、后者只是推断，且这样
    #    也覆盖「键名不在敏感表里但值确实是凭据」的漏网情形。
    src_ini = PROJECT_ROOT / "config" / "config.ini"
    dst_ini = cfg_dst / "config.ini"
    if src_ini.is_file() and dst_ini.is_file():
        dst_text = dst_ini.read_text(encoding="utf-8-sig", errors="replace")
        src_parser = _read_ini_pairs(src_ini)
        for section, key, value in src_parser:
            v = value.strip()
            # 只拦「有实质内容且确实敏感」的值；空值/纯布尔运维参数不算凭据。
            if len(v) < 4:
                continue
            if not (web_config.is_sensitive_item(section, key) or web_config._looks_like_secret_value(v)):
                continue
            if v in dst_text:
                problems.append(f"config/config.ini 的 [{section}] {key} 真实值未被脱敏（长度 {len(v)}）")

    if problems:
        print("[build][FATAL] 发布目录内检出凭据（SEV-2213：外发 zip 不得包含配置凭据）：", file=sys.stderr)
        for p in problems:
            print(f"  - {p}", file=sys.stderr)
        raise SystemExit(1)
    print("[build] 发布目录凭据校验通过：config/ 内无敏感键真实值")


def _read_ini_pairs(path: Path) -> list[tuple[str, str, str]]:
    # 读 ini 为 (节, 键, 值) 三元组列表；解析失败返回空（由 assert_no_credentials_in_release 的
    # 「成品侧」检查兜底，此函数自身不参与放行判定）。
    import configparser

    parser = configparser.ConfigParser(interpolation=None)
    parser.optionxform = str  # type: ignore[method-assign,assignment]  # 同上：保留键名原样大小写
    try:
        parser.read(path, encoding="utf-8-sig")
    except configparser.Error:
        return []
    return [(section, key, value) for section in parser.sections() for key, value in parser.items(section)]


# ==================== 运行时二进制下载（--dual full 版本） ====================

# 运行时二进制的「槽位」标识：与下载点一一对应，刻意**不**用下载文件名做键——ffmpeg 的临时文件名
# 是通用的 _ffmpeg_temp.zip / _ffmpeg_temp.tar.xz（三平台共用的两支不同构建），node 的文件名又随
# 「最新 LTS」每次构建都可能变化，按文件名钉定既无法分平台表达、也无法表达「这一份还没核实」。
RUNTIME_SLOTS: tuple[str, ...] = ("ffmpeg", "node")

# [2026-09-26] 某些平台还有一个「与 ffmpeg 分家发布」的可执行件（macOS 的 ffprobe），它同样需要一个
# 下载槽位。这类槽位按运行时键登记在 _EXTRA_EXECUTABLE_URLS，**不并进本元组**：并进来会让
# windows/linux 三键凭空多出没有公布值的钉定义务。查「这个键该有几个槽」一律用 runtime_slots_for()。

# 发布矩阵覆盖的运行时键（<os>-<arch>），与 .github/workflows/build-release.yml 的四平台矩阵同源；
# scripts/check_runtime_pins.py 校验钉定表对它的覆盖完整性。
RELEASE_RUNTIME_KEYS: tuple[str, ...] = ("windows-x64", "linux-x64", "linux-arm64", "macos-x64", "macos-arm64")

# 尚未核实官方哈希的占位标记。判定「是否已钉定」只看形状（64 位十六进制），
# 故任何非 hex 值（含本标记）都等价于「未钉定」，无需在别处复制本常量。
UNVERIFIED_PIN = "UNVERIFIED-OFFICIAL-SHA256-FILL-ME"

# 官方签名档的表值标记：该槽**没有**上游公布的 SHA256 可比对，完整性判据换成「上游公布的分离
# GPG 签名 + 带外钉死的完整 40 位主钥指纹」。为什么这一档比哈希钉定更强而不是更弱：哈希钉定的
# 期望值与产物走同一条通道（gyan.dev 的 .sha256 文档就是它自己服务器发的），通道被劫持时两者一起
# 被换；而签名档的判据是「这份产物由那把钥匙签出」，公钥按指纹从 keys.openpgp.org 这一**独立**
# 通道导入，伪造者没有私钥就签不出环内钥匙认过的签名。
# 该档自带两处硬条件，缺一即视为未管住（见 _is_signature_satisfied）：① 槽位必须在
# _RUNTIME_GPG_SIGNATURES 里确有登记；② 指纹必须是 40 位十六进制。光填标记拿不到放行。
OFFICIAL_SIGNATURE_PIN = "PINNED-OFFICIAL-GPG-SIGNATURE"

# 已钉定的运行时二进制 SHA256，按运行时键分列：{ "<os>-<arch>": { "<槽位>": "<sha256>" } }。
# 发布路径为 **fail-closed**（SEV-10）：CI（GITHUB_ACTIONS）默认 --require-pinned，缺钉定/形状非法
# 即在**下载之前** SystemExit（不浪费 300MB 带宽，也不落盘未校验产物）。
# 维护方式（每次升级运行时版本都要走一遍）：
#   1) 从官方渠道取该构建公布的 SHA256：nodejs.org 的 SHASUMS256.txt、gyan.dev 的 <name>.zip.sha256、
#      BtbN 资产则取 api.github.com 的 releases/tags/<钉定标签> → assets[].digest（形如 "sha256:<64hex>"）；
#      [2026-09-27] 不要用 releases/latest：那是滚动别名，digest 每次上游重传都变，取完当天就可能失配。
#      三条取数命令与读数时刻记在 docs/agent-reference/measured-evidence.md 对应小节。
#   2) 把 64 位十六进制小写值替换下表中的 UNVERIFIED_PIN（**不得凭本地下载结果填写**——
#      那只会把「构建机已中毒」的情形固化成基线）；上游确实只给签名不给哈希时，改填
#      OFFICIAL_SIGNATURE_PIN 并把「签名 URL + 完整 40 位主钥指纹」同批登记进 _RUNTIME_GPG_SIGNATURES
#      （只改表不登记 = 未满足，--strict 照旧拦，见 _is_signature_satisfied）。
#      [历史注] 本清单曾列 johnvansickle 的 ffmpeg-release-<arch>-static.tar.xz.sha56：该端点实测 404
#      （它只发 *.md5），Linux 两槽已于 2026-09-26 换源到 BtbN，见 _FFMPEG_DOWNLOAD_URLS。
#   3) 也可不改本表、由 CI 用环境变量 DLR_RUNTIME_SHA256（JSON）注入同一批值，把「发布密钥」
#      与代码仓分离；两种来源都接受槽位名或下载文件名做键。
# 表内仍是占位值时，`python scripts/check_runtime_pins.py --strict` 与 CI 发布链一律失败，直到
# 维护者填入官方值——这是刻意设计，不得为了「让 CI 变绿」而回填自算哈希或放宽判定。
#
# [2026-09-22 回填进度] 只回填「取值可追溯到上游官方公布页」的槽位，判定形状未变：
#   · node × 5 段已全部钉定：来源 https://nodejs.org/dist/v24.21.0/SHASUMS256.txt，并在同版本
#     GPG 签名文档 SHASUMS256.txt.asc 的明文本体里逐条复核一致（仅做取值一致性复核，**未验签**）。
#     v24.21.0 = 当日 dist/index.json 里第一条 lts 项（codename Krypton），即 _download_nodejs
#     会选中的那一版；上游一发新 LTS 本段即失配并由 --strict 拦下发布——这正是 SEV-10 写明的
#     人工闸口，不得改成「自动取本次实际哈希」。
#   · windows-x64/ffmpeg 已钉定：来源 gyan.dev 官方 .sha256 文档，两个端点取值互相印证（滚动别名
#     ffmpeg-release-essentials.zip.sha256 与重定向目标 packages/ffmpeg-9.0.2-essentials_build.zip
#     .sha256），对应版本 ffmpeg 9.0.2。滚动别名意味着**每次上游发新版本都会失配**，需重新核对后回填。
#   · macos-x64 / macos-arm64 的 ffmpeg 取值 = OFFICIAL_SIGNATURE_PIN（官方签名档，判据见该常量注释）：
#     evermeet 页面只写「任意文件追加 /sig 取 GPG 签名」、无 sha256 文档（2026-09-26 实测 /sig → 200
#     application/pgp-signature、594 B 二进制 OpenPGP 包，重定向真实落点 e.deolaha.ca:4242/pub/ffmpeg/
#     ffmpeg-9.0.2.zip.sig）；_RUNTIME_GPG_SIGNATURES 已登记该槽的签名 URL 与完整主钥指纹，指纹同日经
#     keys.openpgp.org 这一**独立**通道回显印证（UID "static FFmpeg binaries (signing key)"）。
#     两槽是同一份 x86_64 产物（原 arm64 下载点 getrelease-arm64/zip 上游从不存在、恒 404，2026-09-22
#     已把两架构统一为 x86_64 构建，见 _FFMPEG_DOWNLOAD_URLS 注释）。
#   · linux-x64 / linux-arm64 的 ffmpeg 已换用**公布 SHA256 的上游**（BtbN FFmpeg-Builds 的 n9.0 系列
#     资产，2026-09-26）：下表取值取自 api.github.com 该 release asset 的 digest 字段——属平台公布的哈希
#     文档，不是本地下载自算，故仍是常规 64 位十六进制钉定，不需要新开完整性档。
#     [2026-09-27 更正] 取数端点由 `releases/latest` 改为 `releases/tags/<标签>`，且标签必须是**月末**
#     autobuild（现钉 autobuild-2026-08-31-13-27）：`latest` 是滚动别名，上游每次重建即换 digest——
#     实测 2026-09-26 当天取的 87de0900… 在同日 13:22 上游重发后即失配，发布链当次即红；日更
#     autobuild 标签又只保留约两周（实测仅剩 09-13~09-26 共 15 条），钉它会变成两周后必然 404。
#     月末标签实测可回溯到 autobuild-2024-10-31，是本仓能拿到的唯一「URL 与 digest 都不可变」的组合。
#   [历史注] 2026-09-22 至 2026-09-26 这四槽长期保持占位，原因是当时所选上游确实不公布 SHA256：
#     johnvansickle（Linux）只提供 *.md5（实测 200，内容为 md5 摘要）。按「不得凭本地下载结果填写」的
#     硬约束宁可让发布链红在这些槽位上。Linux 侧最终处置选了「换用公布 SHA256 的上游」，而不是为
#     md5-only 上游另设一档显式降级——代价是产物体积：BtbN linux64-gpl 150,998,508 B
#     vs johnvansickle amd64-static 41,888,096 B（实测 2026-09-26，见 _FFMPEG_DOWNLOAD_URLS 注释）。
# [历史注] 2026-09-18 CR-11 只有校验框架、表为空且未钉定仅告警后继续（fail-open），
#   2026-09-20 SEV-10 确认约 300MB 无校验二进制直接进分发包，改为上方 fail-closed 语义。
# [2026-09-27 恢复] 下表 8 个槽位曾被整体改写成 OFFICIAL_SIGNATURE_PIN（该档只适用于「上游确实不公布
# 哈希且已在 _RUNTIME_GPG_SIGNATURES 登记」的 macOS ffmpeg/ffprobe 四槽），于是 tests/test_build_exe.py
# 的签名档不变量锁转红、check_runtime_pins.py --strict rc=1、发布链在 prepare 即断。取值一律按
# 上方维护方式的**官方通道**重新核对（非本地下载自算）：nodejs.org SHASUMS256.txt、
# gyan.dev .sha256、api.github.com releases/tags/<月末标签> → assets[].digest，读数时刻见
# docs/agent-reference/measured-evidence.md。
# [2026-10-18 重钉 v24.22.0] 上游 node 于 2026-10-14 发布 v24.22.0（Krypton），dist/index.json 首条
#   lts 即换成它，于是发布链四个平台（win-x64 / linux-x64 / linux-arm64 / macos-arm64）同时以
#   「SHA256 不匹配」终止：期望 158f7685…/6e1db87e…/724282c3…/bed7eea5…（= v24.21.0 的取值）、
#   实际 f9683a19…/28ea0a43…/b7e7991d…/6a9724d9…。这正是上方「上游一发新 LTS 本段即失配」的
#   预期行为，不是完整性告警——按维护方式走官方通道重取：nodejs.org/dist/v24.22.0/SHASUMS256.txt
#   （34 行）与同版本 SHASUMS256.txt.asc 的明文本体逐条复核完全一致（仍是**未验签**，与 2026-09-22
#   同一口径；该槽在 _PIN_SOURCE_TABLE 里的 fingerprint 仍为空，故在线层不 adopt 它）。核对结果与
#   CI 报出的 4 条实测值逐位相同，可作为「值本身没错、只是版本漂移」的独立佐证。macos-x64 本次
#   矩阵未报错，但同属一套取值来源，一并不留旧版本（否则下次 mac 构建才红）。
#   上段 2026-09-22 的 v24.21.0 读数为当时实测记录，保留不动。
_PINNED_RUNTIME_SHA256: dict[str, dict[str, str]] = {
    # node 各段取值均来自 https://nodejs.org/dist/v24.22.0/SHASUMS256.txt（来源与复核方式见上方注释）
    "windows-x64": {
        # gyan.dev ffmpeg-release-essentials.zip.sha256（= ffmpeg 9.0.2 essentials_build，2026-09-22）
        "ffmpeg": "60f467265b1e312373dbcd92200c2618a74850f98d3d078e94296bb3fa2047ba",
        # node-v24.22.0-win-x64.zip（_download_nodejs 在 Windows 下取 .zip）
        "node": "f9683a19877e12a9b167305c8db71040d812876359de21f0d2e97c3f321f80c3",
    },
    "linux-x64": {
        # BtbN autobuild-2026-08-31-13-27 的 ffmpeg-n9.0.1-11-ge47273f4d9-linux64-gpl-9.0.tar.xz
        # （api.github.com releases/tags/<标签> → assets[].digest，2026-09-27）
        "ffmpeg": "182c1b509720e939bb47bfb47dc29cc0c298640401128e3dce8627d10707eb5a",
        # node-v24.22.0-linux-x64.tar.gz（非 .tar.xz：_download_nodejs 统一取 tar.gz）
        "node": "28ea0a438de9a13bd7891fd758eee6c7819ee8af5442dfd8d45bd65e56d4228c",
    },
    "linux-arm64": {
        # 同一标签的 linuxarm64 资产；与上一条同一次取数（2026-09-27）
        "ffmpeg": "e2dd447c8a47849c5812d87e54a47b20ae0f3603d38989440f4a5fe1af8755b1",
        "node": "b7e7991d5407815adfa74a2a9cd4db683552c8ce32ff4a295c22e972849c3f5d",
    },
    "macos-x64": {
        # evermeet getrelease/zip：官方只给 GPG 签名（追加 /sig），无 SHA256 → 走官方签名档
        "ffmpeg": OFFICIAL_SIGNATURE_PIN,
        "ffprobe": OFFICIAL_SIGNATURE_PIN,
        # node-v24.22.0-darwin-x64.tar.gz
        "node": "495e3f273c645f3c4677d438304cdfc701729ea5dec5728f5c8e76a2dece4b91",
    },
    "macos-arm64": {
        # 与 macos-x64 同一份 evermeet 构建（上游不发布 arm64，见 _FFMPEG_DOWNLOAD_URLS 注释）：
        # 同一来源 → 同一档；两槽的取值必须保持相等（tests/test_build_exe.py 锁此项）
        "ffmpeg": OFFICIAL_SIGNATURE_PIN,
        "ffprobe": OFFICIAL_SIGNATURE_PIN,
        # node-v24.22.0-darwin-arm64.tar.gz
        "node": "6a9724d9b50a5f22b4816cded441b5a8d9ddae546191a5e5b7efa5a5e2ee26d5",
    },
}

_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
# 钉定指纹的形状关：与哈希同理，只看形状、不看语义。39 位/带空格/非十六进制一律算「没钉指纹」，
# 于是签名档不可能靠填个像样的字符串凑过判定（_is_pinned 的同类设计）。
_FINGERPRINT_PATTERN = re.compile(r"^[0-9a-f]{40}$")

# 命令行对「必须钉定」的显式覆盖：None = 沿用默认判定（CI 环境变量自动开启）。
# 由 main() 在解析参数后写入，_download_file 通过 require_pinned_hashes() 读取。
_REQUIRE_PINNED_OVERRIDE: bool | None = None

# 平台 → node dist 目录命名 / 本机架构归一（_download_nodejs 与运行时键共用同一份映射，
# 避免两处各自演化出「同一台机器两种键名」的漂移）
_NODE_PLATFORM_MAP = {"win32": "win", "darwin": "darwin", "linux": "linux"}
_NODE_ARCH_MAP = {"x86_64": "x64", "amd64": "x64", "arm64": "arm64", "aarch64": "arm64"}


# 当前机器对应的运行时键，如 "windows-x64"
def runtime_slot_key() -> str:
    os_tag = {"win32": "windows", "darwin": "macos"}.get(sys.platform, "linux")
    arch = _NODE_ARCH_MAP.get(platform.machine().lower(), "x64")
    return f"{os_tag}-{arch}"


# 解析 DLR_RUNTIME_SHA256（JSON）。接受三种形态并统一收敛为「槽位/文件名 → 哈希」：
#   ① {"ffmpeg": "...", "node": "..."}                          —— 扁平（只作用于当前运行时键）
#   ② {"windows-x64": {"ffmpeg": "..."}, "any": {...}}          —— 按运行时键分列（CI 主用法）
#   ③ {"node-v24.1.0-win-x64.zip": "..."}                       —— 按下载文件名（历史兼容）
def _env_pins() -> dict[str, str]:
    raw = os.environ.get("DLR_RUNTIME_SHA256", "").strip()
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        print("[build][warn] DLR_RUNTIME_SHA256 不是合法 JSON，已忽略")
        return {}
    if not isinstance(data, dict):
        print("[build][warn] DLR_RUNTIME_SHA256 应为 JSON 对象，已忽略")
        return {}
    current = runtime_slot_key()
    merged: dict[str, str] = {}
    for key, value in data.items():
        if isinstance(value, dict):
            # 分列形态：只取「本运行时键」与「any/*」两段，其它平台的钉定不参与判定
            if str(key) == current or str(key).lower() in ("any", "*"):
                merged.update({str(k): str(v) for k, v in value.items()})
        elif value is not None:
            merged[str(key)] = str(value)
    return {str(k): str(v).strip().lower() for k, v in merged.items()}


def _pinned_slots() -> dict[str, str]:
    # 合并内置钉定表（当前运行时键那一段）与环境变量覆盖（环境变量优先，便于 CI 注入）。
    # 在线来源层排在两者之后、且只在被显式开启时才动作（默认 off，见该节头注释）。
    merged = {str(k): str(v).strip().lower() for k, v in _PINNED_RUNTIME_SHA256.get(runtime_slot_key(), {}).items()}
    merged.update(_env_pins())
    _apply_online_pin_source(merged)
    return merged


def _is_pinned(value: str) -> bool:
    # 「已钉定」的唯一判据是形状：64 位小写十六进制。占位标记、空串、截断值一律算未钉定，
    # 因此新增占位写法不需要改判定逻辑（也不可能靠「填个非空字符串」蒙过门禁）。
    return bool(_SHA256_PATTERN.fullmatch(value))


# ==================== 第 4 类完整性口径：源码可复现构建（W1，2026-09-22 批准） ====================

# 为什么需要第四类而不是「把 CI 自算哈希塞进 _PINNED_RUNTIME_SHA256」：CI 自源码构建的产物
# **没有上游公布值**，而「把构建机算出的哈希当基线」正是 SEV-10 明令禁止的形态。本类把闸口从
# 「产物哈希」换成「输入可钉定 + 过程可追溯」，三件证据齐备才算满足：source_sha256（上游官方
# **源码 tarball** 的 SHA256，可人工核对）、recipe_sha256（构建配方即 configure 参数串的 SHA256，
# 配方变即基线失效、逼后来的人重核）、provenance_ref（产出该二进制的 workflow/attestation 引用，
# 空 = 无过程证据）。两条硬防绕过要求：① 标记本身**绝不构成放行**，证据缺任一条即算未满足；
# ② 声明为第 4 类的槽位**不得再走下载路径**（它的产物是构建出来的，走下载等于「换个标记拿免检」）。
SOURCE_BUILD_PROVENANCE = "SOURCE-BUILD-PROVENANCE"
SOURCE_BUILD_EVIDENCE_FIELDS: tuple[str, ...] = ("source_sha256", "recipe_sha256", "provenance_ref")

# {运行时键: {槽位: {证据字段: 值}}}。当前**为空**是刻意状态：本轮只落口径，路线 A 的构建步骤
# （W2~W4）尚未获批实施，没有真实证据可登记。空表 = 第 4 类一个都不满足 = --strict 照旧拦。
_SOURCE_BUILD_EVIDENCE: dict[str, dict[str, dict[str, str]]] = {}


def _source_build_evidence(key: str, slot: str) -> dict[str, str]:
    entry = _SOURCE_BUILD_EVIDENCE.get(key, {}).get(slot, {})
    return {field: str(entry.get(field, "")).strip() for field in SOURCE_BUILD_EVIDENCE_FIELDS}


def _is_source_build_marker(value: str) -> bool:
    # 比较一律大小写无关：_pinned_slots() 会把内置表与环境变量的取值统一 .strip().lower()，
    # 若按常量原样逐字比，注入进来的标记就永远认不出——等于第 4 类的拒下载判定形同虚设
    # （这条正是 tests/test_build_exe.py::test_env_injected_marker_also_refuses_download 抓出来的）。
    return value.strip().lower() == SOURCE_BUILD_PROVENANCE.lower()


def _is_source_build_satisfied(value: str, key: str, slot: str) -> bool:
    # 证据值同样要过形状关：「填个占位字符串凑数」与 CR-11 的「空表 + warn 后继续」是同一族失效。
    if not _is_source_build_marker(value):
        return False
    evidence = _source_build_evidence(key, slot)
    if not evidence["provenance_ref"]:
        return False
    return bool(
        _SHA256_PATTERN.fullmatch(evidence["source_sha256"].lower())
        and _SHA256_PATTERN.fullmatch(evidence["recipe_sha256"].lower())
    )


def _is_signature_marker(value: str) -> bool:
    # 与 _is_source_build_marker 同理：比较一律大小写无关，否则 CI 经 DLR_RUNTIME_SHA256 注入的
    # 标记永远认不出（_pinned_slots() 会把取值统一 .strip().lower()）。
    return value.strip().lower() == OFFICIAL_SIGNATURE_PIN.lower()


def _is_signature_satisfied(value: str, key: str, slot: str) -> bool:
    # 标记本身**绝不构成放行**（与第 4 类同一条防线）：必须同时满足「该槽在 _RUNTIME_GPG_SIGNATURES
    # 里确有登记」且「登记的指纹过 40 位十六进制形状关」，否则「换个更容易填的标记」就成了绕闸通道。
    if not _is_signature_marker(value):
        return False
    entry = _RUNTIME_GPG_SIGNATURES.get(key, {}).get(slot)
    if entry is None:
        return False
    return bool(_FINGERPRINT_PATTERN.fullmatch(str(entry[1]).strip().lower()))


def _slot_is_gated(value: str, key: str, slot: str) -> bool:
    # 「这个槽位今天算不算被管住了」的**唯一**口径 = 已钉定的官方哈希 ∨ 证据齐备的第 4 类。
    # scripts/check_runtime_pins.py 必须调本函数而不是自己判 _is_pinned，否则会出现两份判定、
    # 第 4 类在某一侧被漏认（AGENTS.md 禁止并行事实源的同一条）。
    # [2026-09-26] 第三个析取项「官方签名档」（_is_signature_satisfied）并入，仍只有本函数一个口径。
    return (
        _is_pinned(value) or _is_source_build_satisfied(value, key, slot) or _is_signature_satisfied(value, key, slot)
    )


def _declares_source_build(value: str) -> bool:
    # 只看标记、不看证据：用于下载路径的处置——声明走第 4 类的槽位根本不该下载。
    return _is_source_build_marker(value)


# 发布路径是否要求「必须有钉定」。CI 默认开启（GITHUB_ACTIONS=true），本地默认关闭但会告警；
# 命令行 --require-pinned / --allow-unpinned 可显式覆盖两者。
def require_pinned_hashes() -> bool:
    if _REQUIRE_PINNED_OVERRIDE is not None:
        return _REQUIRE_PINNED_OVERRIDE
    return os.environ.get("GITHUB_ACTIONS", "").strip().lower() == "true"


# 未钉定时的处置：发布路径终止构建，本地路径打印实际哈希供人工核对官方值后再钉定。
def _unpinned_action(
    slot: str, dest: Path, desc: str, declared_source_build: bool = False, declared_signature: bool = False
) -> None:
    # declared_source_build 由调用方传入**已合并环境变量后的实际取值**（而不是只查内置表），
    # 否则「CI 用 DLR_RUNTIME_SHA256 注入第 4 类标记」这条通道会绕过下面的拒下载判定。
    key = runtime_slot_key()
    if declared_source_build:
        # 声明为第 4 类却走到下载：说明产物应由构建步骤产出而非从上游拉取。放行就等于「换个标记拿免检」，
        # 因此**两侧都终止**（不受 require_pinned_hashes 影响），并把证据要求原样打出来。
        raise SystemExit(
            f"[build][FATAL] {desc}（槽位 {key}/{slot}）声明为第 4 类 {SOURCE_BUILD_PROVENANCE}，"
            f"不该走下载路径。该类的满足条件 = {SOURCE_BUILD_EVIDENCE_FIELDS} 三件证据齐备且过形状关"
            f"（见 _SOURCE_BUILD_EVIDENCE）。已终止构建，未开始下载。"
        )
    if declared_signature:
        # 声明了官方签名档却没被认下，只可能是「该槽未在 _RUNTIME_GPG_SIGNATURES 登记」或「登记的指纹
        # 形状不符」两种原因。报错必须点名这两种，否则维护者会去核对一个本就不存在的「缺失的哈希」。
        msg = (
            f"{desc}（槽位 {key}/{slot}）声明为官方签名档 {OFFICIAL_SIGNATURE_PIN!r} 但未满足："
            f"需该槽在 _RUNTIME_GPG_SIGNATURES 有登记，且登记的指纹为 40 位十六进制"
        )
        if require_pinned_hashes():
            raise SystemExit(f"[build][FATAL] {msg}。已终止构建，未开始下载。")
        print(f"[build][warn] {msg}——本地构建继续，但**该产物不得用于发布**")
        return
    msg = f"{desc}（槽位 {key}/{slot}）未钉定 SHA256"
    if require_pinned_hashes():
        raise SystemExit(
            f"[build][FATAL] {msg}。发布路径为 fail-closed（--require-pinned / CI 默认开启）："
            f"请先从官方渠道核对并填入 build_exe.py 的 _PINNED_RUNTIME_SHA256"
            f"（当前为占位值 {UNVERIFIED_PIN!r} 视为未钉定），"
            f"或由 CI 注入 DLR_RUNTIME_SHA256；"
            f"上游确实不公布哈希时改走第 4 类（{SOURCE_BUILD_PROVENANCE} + 三件证据，见 W1）。已终止构建，未开始下载。"
        )
    print(f"[build][warn] {msg}——本地构建继续，但**该产物不得用于发布**")


# ==================== 官方 GPG 签名核验（P-2，2026-09-22 批准引入 gnupg） ====================

# {运行时键: {槽位: (签名 URL, 完整公钥指纹)}}。SHA256 钉定只回答「下到的是先头核过的那一份吗」，
# 它**自身不带来源认证**——期望值与实际产物是从同一个 HTTPS 通道取回的，域名/CDN 被劫持时
# 两者会被一起换掉；签名核验补的正是「这份产物确实由那把钥匙签出」，且公钥按**完整 40 位指纹**
# 导入而不是 key id（key id 只有 16 位十六进制，可碰撞、可仿冒）。
# 只登记**上游确实公布 detached 签名**的槽位，没公布的留空即跳过：evermeet（macOS 两架构）页面
# 明示「任意文件追加 /sig 取其 GPG 签名」；gyan.dev / johnvansickle 实测不公布签名文件，
# **不得**为了「看起来全都验了」伪造配置。
# [2026-09-26] macOS 两槽的 _PINNED_RUNTIME_SHA256 取值改为本表的官方签名档，于是「登记了签名」从
# 锦上添花升格为**判据本体**：该表若缺某槽条目，_is_signature_satisfied 直接判未管住（--strict 红），
# 而不是像过去那样只是「顺带没验」。指纹已于 2026-09-26 经 keys.openpgp.org 独立通道回显印证。
# 指纹的信任来源要知情：它取自上游自己的页面/文档，属「同一通道带回来的钥匙」，强度等同
# TOFU-of-key；要再上一格需从第二渠道（密钥服务器上的签名网络 / 与维护者当面核对指纹）确认。
_RUNTIME_GPG_SIGNATURES: dict[str, dict[str, tuple[str, str]]] = {
    "macos-x64": {
        "ffmpeg": (
            "https://evermeet.ca/ffmpeg/getrelease/zip/sig",
            "20F6EA3E0CFD6B4C53447A73476C4B611A660874",
        ),
        # ffprobe 归档与 ffmpeg 归档同页同钥：实测两份 .sig 的签发者都是主钥
        # 20F6EA3E0CFD6B4C53447A73476C4B611A660874 名下的子钥 4E7BEC998E920EE1
        # （RSA-4096 / SHA-512，2026-09-18 签），_verify_gpg_artifact 按「主钥+子钥指纹集合」判归属，
        # 故沿用同一个已钉主钥指纹，不需要另立第 4 把钥匙。
        "ffprobe": (
            "https://evermeet.ca/ffmpeg/getrelease/ffprobe/zip/sig",
            "20F6EA3E0CFD6B4C53447A73476C4B611A660874",
        ),
    },
    "macos-arm64": {
        # 与 macos-x64 同一份产物、同一把钥匙（见 _FFMPEG_DOWNLOAD_URLS 注释）
        "ffmpeg": (
            "https://evermeet.ca/ffmpeg/getrelease/zip/sig",
            "20F6EA3E0CFD6B4C53447A73476C4B611A660874",
        ),
        "ffprobe": (
            "https://evermeet.ca/ffmpeg/getrelease/ffprobe/zip/sig",
            "20F6EA3E0CFD6B4C53447A73476C4B611A660874",
        ),
    },
}


def _run_gpg(args: list[str], timeout: int = 180) -> subprocess.CompletedProcess[bytes] | None:
    # 返回 None 表示「gpg 这个工具不可用」（未安装 / 超时 / 无法启动），调用方据此区分
    # 「工具缺失」与「验签失败」——后者无论本地还是发布路径都必须终止构建，前者只在发布路径终止。
    # 输出**一律按字节**返回且不开 text=True：--status-fd 的机器行是判定依据，而中文 Windows 上
    # locale 解码会让 subprocess 的 reader 线程抛 UnicodeDecodeError、把 stdout 变成 None
    # （AGENTS.md「探测子进程输出一律按字节比较」同源坑）。
    try:
        return subprocess.run(
            ["gpg", *args],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=timeout,
            check=False,
        )
    except OSError, subprocess.SubprocessError:
        return None


def _verify_official_signature(dest: Path, slot: str, desc: str) -> None:
    # 未登记签名的槽位（gyan.dev 与 BtbN 均不公布 detached 签名文件）直接返回——**跳过是显式状态**，
    # 不是「静默通过」：--strict 仍会因该槽位未钉定而拦下发布。
    # [2026-09-26] 官方签名档槽位（macOS 两槽）以本函数**作为唯一完整性判据**，故这里的「跳过」
    # 对那一档不可能发生：_is_signature_satisfied 已把「该槽确有登记」列为满足条件之一。
    entry = _RUNTIME_GPG_SIGNATURES.get(runtime_slot_key(), {}).get(slot)
    if entry is None:
        return
    sig_url, fingerprint = entry
    print(f"[build] 核验 {desc} 的官方 GPG 签名（指纹 {fingerprint[-16:]}）")
    # 签名文件只活在临时目录里：落到 target_dir 会被 make_zip 一起打进对外分发包。
    import tempfile

    with tempfile.TemporaryDirectory(prefix="dlr-gpg-") as tmp:
        _verify_gpg_artifact(dest, Path(tmp) / "artifact.sig", sig_url, fingerprint, desc)


def _verify_gpg_artifact(
    dest: Path, sig_path: Path, sig_url: str, fingerprint: str, desc: str, *, strict: bool = True
) -> bool:
    # 判据一律来自 --status-fd 的机器行，而不是 gpg 的退出码：退出码 0 只说明「签名能被钥匙环里
    # 某把钥匙验通」，不核对签名者身份时，任意一把可导入的钥匙签过的产物都能蒙过去。
    # strict=True（默认）= 产物侧的唯一口径。
    # strict=False = 仅供**在线清单**复核用：那时「验不过」的处置是「不采用这份清单」，而不是终止
    # 构建——内置钉定表仍在，真正的 fail-closed 闸口在产物下载那一步（见 _unpinned_action）。
    # 返回 True 只在「GOODSIG + VALIDSIG 且签名钥匙属于钉定指纹那把钥匙」时成立，调用方不得用
    # 「没抛异常」代替本返回值（下面每一条早返回都是验签未成立）。
    def _skip_or_fail(msg: str, ci_hint: str) -> bool:
        # 「取不到签名文件」/「gpg 不可用」属工具或网络缺失：发布路径终止，本地路径留痕后跳过，
        # 两侧都不许出现「什么都没发生」的形态。
        if not strict:
            print(f"[build][warn] {desc} 在线清单验签无法进行，本次不参与判定——{msg}")
            return False
        if require_pinned_hashes():
            raise SystemExit(f"[build][FATAL] {desc} 签名核验失败——{msg}{ci_hint}")
        print(f"[build][warn] {desc} 签名核验跳过——{msg}；本地构建继续，产物不得发布")
        return False

    def _hard_fail(msg: str) -> bool:
        # 判据类失败（指纹不在环内 / BADSIG / 无 VALIDSIG）：**本地与发布路径都终止**，
        # 因为这类失败说的是「这份产物不可信」，而不是「这次没法验」。
        if not strict:
            print(f"[build][warn] {desc} 在线清单验签未通过，本次不参与判定——{msg}")
            return False
        raise SystemExit(f"[build][FATAL] {desc} {msg}")

    try:
        with urllib.request.urlopen(sig_url, timeout=60) as resp:
            sig_path.write_bytes(resp.read())
    except OSError as e:
        return _skip_or_fail(
            f"取不到 {sig_url} 的签名文件：{type(e).__name__}: {e}", "（发布路径 fail-closed，已终止构建）"
        )

    if _run_gpg(["--batch", "--quiet", "--keyserver", "hkps://keys.openpgp.org", "--recv-keys", fingerprint]) is None:
        return _skip_or_fail("gnupg 不可用（未安装或无法启动 gpg）", "；CI runner 需先装 gnupg")

    # 钉定的指纹必须是**导入成功的那把钥匙**的主钥指纹：用 --with-colons 的 fpr 记录核对，
    # 顺带拿到主钥 + 全部子钥的指纹集合（下面判签名者用）。
    listed = _run_gpg(["--batch", "--quiet", "--list-keys", "--with-colons", fingerprint])
    key_fprs: set[bytes] = set()
    if listed is not None:
        key_fprs = {
            line.split(b":")[9].strip().lower()
            for line in (listed.stdout or b"").splitlines()
            if line.startswith(b"fpr:") and len(line.split(b":")) > 9
        }
    if listed is None or fingerprint.lower().encode("ascii") not in key_fprs:
        return _hard_fail(f"无法在钥匙环中确认指纹 {fingerprint}，签名核验终止（不降级放行）")

    checked = _run_gpg(["--batch", "--quiet", "--status-fd", "1", "--verify", str(sig_path), str(dest)])
    if checked is None:
        return _hard_fail("gpg --verify 无法执行，签名核验终止")
    status = checked.stdout or b""
    # 判据三条同时成立：GOODSIG + VALIDSIG（签名可被环内钥匙验通）、无 ERRSIG/BADSIG、
    # 且**实际签名的那把钥匙属于钉定指纹那把钥匙的主钥/子钥集合**。
    # 最后一条为什么要用集合而不是逐字比钉定值：GnuPG 的 VALIDSIG 首字段报的是**签名子钥**
    # 指纹，若上游用子钥签名而这里硬比主钥指纹，就会把合法产物判成失败（假红比漏检更难排查）。
    lines = status.splitlines()
    good = any(line.startswith(b"[GNUPG:] GOODSIG ") for line in lines)
    bad = any(line.startswith(b"[GNUPG:] ERRSIG") or line.startswith(b"[GNUPG:] BADSIG") for line in lines)
    signer = {
        line.split()[2].lower() for line in lines if line.startswith(b"[GNUPG:] VALIDSIG ") and len(line.split()) >= 3
    }
    if not good or bad or not signer or not signer <= key_fprs:
        # status 仅用于把状态行原文打进报错供人看，不参与判定
        return _hard_fail(
            f"签名核验未通过（需 GOODSIG+VALIDSIG，且签名钥匙属于钉定指纹 {fingerprint}）:\n" + status.decode("latin-1")
        )
    print(f"[build] {desc} GPG 签名核验通过（{fingerprint}）")
    return True


# ==================== 运行时钉定的在线来源（2026-10-17 引入，默认关闭） ====================
#
# 为什么要有这一层：_PINNED_RUNTIME_SHA256 是「维护者在某时刻从官方渠道抄下来的带外基线」，强度来自
# 通道独立，代价是上游一发新版本就失配、且只能靠构建失败才被发现。本层补的是「不必等构建失败就知道
# 上游换了版本」，但**不取代**那张表——两者的分工由下方信任档界定，内置表始终是唯一事实源。
#
# 三态开关（--pin-source / DLR_RUNTIME_PIN_SOURCE），默认 off：
#   off    完全只用内置表，一次网络请求都不发（引入本层前后的构建行为逐字相同）。
#   verify 拉取官方清单后**只与内置表比对**：一致 = 印证内置表仍有效；不一致 = 上游已发新值，
#          发布路径终止并打印「请把新值回填内置表」，本地路径告警且继续用内置表。
#          **永不把拉到的值写进期望值**——这一步存在的意义就是不自动放行。
#   adopt  在线值升格为本次构建的判据。仅对 trust=signed 且**清单验签通过**的槽位生效
#          （见 _pin_source_is_adoptable）；其余档位一律拒绝采用并回退内置表。
PIN_SOURCE_OFF = "off"
PIN_SOURCE_VERIFY = "verify"
PIN_SOURCE_ADOPT = "adopt"
_PIN_SOURCE_MODES: tuple[str, ...] = (PIN_SOURCE_OFF, PIN_SOURCE_VERIFY, PIN_SOURCE_ADOPT)

# 信任档：决定「拉到的这个哈希能不能当判据」。这条是整层的命门，判错了整层就退化成安全剧场。
#   signed —— 该清单**另有独立认证**：配套发布的分离 GPG 签名 + 已在本条目 fingerprint 里钉住的
#             完整 40 位主钥指纹。只有这一档允许 adopt，因为判据是「这份清单由那把钥匙签出」，
#             与「清单自己说什么」无关——通道被劫持时，没有私钥的人签不出能过验签的清单。
#   advisory —— 清单与产物**同源同服务器**（gyan.dev 的 .sha256 文档就是它自己发的；
#             api.github.com 的 digest 与产物同在 github.com）。这种值再新也不具备独立性：
#             中间人换掉 zip 的同时就把 .sha256 一起换了，于是「拉清单 → 当期望值 → 比对产物」
#             三步恒等通过。故这一档只用于 verify 比对与提示，**绝不作 expected**。
PIN_TRUST_SIGNED = "signed"
PIN_TRUST_ADVISORY = "advisory"

# 清单的解析形态（各上游公布的文档格式不同，但形状关只有 _SHA256_PATTERN 一个）：
#   raw      响应体就是哈希本身，形如 "<64hex>" 或 "<64hex>  <文件名>"（gyan.dev 的 .sha256）。
#   shasums  多行 "<64hex>  <文件名>"，按文件名取对应那一行（nodejs.org 的 SHASUMS256.txt）。
#   github   GitHub Release JSON，按 assets[].name 精确匹配后取该资产的 digest（"sha256:<64hex>"）。
_PIN_KIND_RAW = "raw"
_PIN_KIND_SHASUMS = "shasums"
_PIN_KIND_GITHUB = "github"

# {运行时键: {槽位: {字段: 值}}}。**未登记的槽位一律跳过、不拉取**（evermeet 根本不公布哈希，
# macOS 两槽因此维持「官方签名档」这一档，不会被本层打扰）。
# url / sig_url 里的 {version} 由 _download_nodejs 解析出的**本次实际版本**代入：node 的下载点是
# 从 nodejs.org/dist/index.json 选出的最新 LTS，版本每次构建都可能不同，把某个版本硬写进 URL 会
# 拉到别的版本的清单、恒失配——且失配原因会被误读成「内置表填错了」。
# asset 只在 shasums / github 两档需要（分别是清单里的文件名与 GitHub 资产名）。
# fingerprint 只在 signed 档需要：留空 = 未登记 = 该槽**不可 adopt**（见 _pin_source_is_adoptable），
# 这是有意设计——没钉住钥匙指纹的「signed」等于没验。
_PIN_SOURCE_TABLE: dict[str, dict[str, dict[str, str]]] = {
    # "*" = 对所有运行时键生效，与 _env_pins() 接受 "any"/"*" 同一口径：node 的清单 URL 与平台
    # 无关（同一份 SHASUMS256.txt 里按文件名分列），写五遍只会埋下「改了四个忘了第五个」的漂移。
    "*": {
        "node": {
            "url": "https://nodejs.org/dist/{version}/SHASUMS256.txt",
            "sig_url": "https://nodejs.org/dist/{version}/SHASUMS256.txt.asc",
            "trust": PIN_TRUST_SIGNED,
            "kind": _PIN_KIND_SHASUMS,
            # 待维护者补：Node.js 发布钥匙的**完整 40 位主钥指纹**。留空 = 该槽不可 adopt，
            # 在线值在 adopt 模式下会被明确拒绝并回退内置表（fail-closed，不降级）。
            "fingerprint": "",
            # asset 留空时按 _download_nodejs 解析出的**本次下载文件名**匹配（见 _pin_asset_name），
            # 因为文件名里含版本与平台，硬写会随版本漂移。
            "asset": "{filename}",
        },
    },
    "windows-x64": {
        "ffmpeg": {
            "url": "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip.sha256",
            "trust": PIN_TRUST_ADVISORY,
            "kind": _PIN_KIND_RAW,
        },
    },
    "linux-x64": {
        "ffmpeg": {
            "url": "https://api.github.com/repos/BtbN/FFmpeg-Builds/releases/tags/autobuild-2026-08-31-13-27",
            "trust": PIN_TRUST_ADVISORY,
            "kind": _PIN_KIND_GITHUB,
            "asset": "ffmpeg-n9.0.1-11-ge47273f4d9-linux64-gpl-9.0.tar.xz",
        },
    },
    "linux-arm64": {
        "ffmpeg": {
            "url": "https://api.github.com/repos/BtbN/FFmpeg-Builds/releases/tags/autobuild-2026-08-31-13-27",
            "trust": PIN_TRUST_ADVISORY,
            "kind": _PIN_KIND_GITHUB,
            "asset": "ffmpeg-n9.0.1-11-ge47273f4d9-linuxarm64-gpl-9.0.tar.xz",
        },
    },
}

# --pin-source 的显式覆盖（None = 沿用环境变量/默认），与 _REQUIRE_PINNED_OVERRIDE 同一手法。
_PIN_SOURCE_OVERRIDE: str | None = None

# 进程内缓存：(运行时键, 槽位) → (取数时刻, 已过形状关的在线值)。
# 为什么需要：_pinned_slots() 每次下载都要跑一遍，同一槽位在一轮构建里会被问多次，对同一个清单
# 文件反复请求既慢又容易被上游限流。**只缓存成功值**：一次超时不该把整轮构建的在线核对钉死在
# 「拉不到」上——失败路径保持可重试，代价只是多一次请求（清单只有几 KB）。
_PIN_ONLINE_CACHE: dict[tuple[str, str], tuple[float, str]] = {}

# _download_nodejs 解析出的本次版本与下载文件名：node 清单 URL 的 {version} 与 shasums 的
# 文件名匹配都靠它。置空 = 还没解析，此时含占位符的清单一律跳过（不拼残缺 URL）。
_NODE_RESOLVED_VERSION = ""
_NODE_RESOLVED_FILENAME = ""


def pin_source_mode() -> str:
    # 优先级：命令行 > 环境变量 > off。未识别的环境值明确告警后按 off，**绝不猜成别的档**
    # （"verfiy" 这类拼写错误若被当成 verify，等于在维护者不知情时打开了联网路径）。
    if _PIN_SOURCE_OVERRIDE is not None:
        return _PIN_SOURCE_OVERRIDE
    raw = os.environ.get("DLR_RUNTIME_PIN_SOURCE", "").strip().lower()
    if not raw:
        return PIN_SOURCE_OFF
    if raw not in _PIN_SOURCE_MODES:
        print(f"[build][warn] DLR_RUNTIME_PIN_SOURCE={raw!r} 不是 {_PIN_SOURCE_MODES} 之一，按 {PIN_SOURCE_OFF} 处理")
        return PIN_SOURCE_OFF
    return raw


def _pin_env_float(name: str, default: float) -> float:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError:
        print(f"[build][warn] {name}={raw!r} 不是数字，按默认 {default} 处理")
        return default
    return value if value >= 0 else default


def _pin_cache_ttl() -> float:
    # 默认 24h：一轮构建远短于此，故进程内缓存实际只在「同一进程多次问同一槽位」时生效。
    # 设 0 = 每次都重取（排查「上游刚发新版」时有用）；设很大 = 全程只拉一次。
    return _pin_env_float("DLR_PIN_CACHE_TTL", 86400.0)


def _pin_fetch_timeout() -> float:
    # 清单都是几 KB 的文档，超时给得比产物下载（180s）短得多：在线核对不该拖慢构建。
    return _pin_env_float("DLR_PIN_FETCH_TIMEOUT", 30.0)


def _pin_resolved_node() -> tuple[str, str]:
    # 本次构建解析出的 (node 版本, 下载文件名)；未解析时两个都是空串。
    return _NODE_RESOLVED_VERSION, _NODE_RESOLVED_FILENAME


def _format_pin_url(template: str, slot: str) -> str:
    # 代入 {version} / {filename}；模板里没有占位符就原样返回。返回空串 = 无法代入。
    if "{" not in template:
        return template
    version, filename = _pin_resolved_node()
    if "{version}" in template and not version:
        # 明确跳过而不是拼出 https://nodejs.org/dist//SHASUMS256.txt 这种残缺 URL：
        # 它恒 404，而报错会指向「上游挂了」，把真正的原因（版本还没解析）藏起来。
        print(f"[build][warn] 槽位 {slot} 的在线清单需要 {{version}}，但本次构建尚未解析 node 版本，跳过在线拉取")
        return ""
    if "{filename}" in template and not filename:
        print(f"[build][warn] 槽位 {slot} 的在线清单需要 {{filename}}，但本次构建尚未解析 node 文件名，跳过在线拉取")
        return ""
    return template.replace("{version}", version).replace("{filename}", filename)


def _parse_online_sha256(payload: str, kind: str, asset: str) -> str:
    # 从上游清单里抠哈希。**唯一出口**：要么 64 位小写十六进制，要么空串。
    # 空响应体 / HTML 错误页 / 截断值 / 非 sha256 的算法前缀一律落空串——形状关永远只有
    # _SHA256_PATTERN 一处，与「已钉定」的判定同口径（本项目对钉定值的定义就只有这一个形状）。
    token = ""
    if kind == _PIN_KIND_RAW:
        parts = payload.split()
        token = parts[0] if parts else ""
    elif kind == _PIN_KIND_SHASUMS:
        for line in payload.splitlines():
            parts = line.split()
            if len(parts) >= 2 and parts[1].strip() == asset:
                token = parts[0]
                break
    elif kind == _PIN_KIND_GITHUB:
        try:
            data: Any = json.loads(payload)
        except json.JSONDecodeError:
            return ""
        assets = data.get("assets") if isinstance(data, dict) else None
        if isinstance(assets, list):
            for item in assets:
                if isinstance(item, dict) and str(item.get("name", "")) == asset:
                    token = str(item.get("digest", ""))
                    break
    else:
        # 未知 kind = 配置写错。**不猜格式**：猜错就会把 HTML 页面里的某段文本当成哈希。
        return ""
    token = token.strip().lower()
    if token.startswith("sha256:"):  # GitHub 资产 digest 的前缀形态
        token = token[len("sha256:") :]
    return token if _SHA256_PATTERN.fullmatch(token) else ""


def _pin_source_is_adoptable(entry: dict[str, str]) -> bool:
    # adopt 的准入门：trust 必须是 signed **且**指纹已钉（40 位十六进制），缺一即不可采用。
    # 尤其 fingerprint 留空时：没钉住钥匙就说「走签名档」，等于把验签这一步省掉，adopt 会
    # 退化成「同源清单说什么就是什么」——正是 PIN_TRUST_ADVISORY 注释里点名的失效形态。
    if entry.get("trust", "") != PIN_TRUST_SIGNED:
        return False
    return bool(_FINGERPRINT_PATTERN.fullmatch(entry.get("fingerprint", "").strip().lower()))


def _fetch_online_pin(entry: dict[str, str], slot: str) -> str:
    # 拉一份官方清单并返回其中的哈希；任何一步不成就返回空串（调用方据此回退内置表）。
    if not entry:
        return ""
    url = _format_pin_url(entry.get("url", ""), slot)
    asset_tpl = entry.get("asset", "")
    asset = _format_pin_url(asset_tpl, slot)
    if not url or (asset_tpl and not asset):
        return ""
    try:
        with urllib.request.urlopen(url, timeout=_pin_fetch_timeout()) as resp:
            raw = resp.read()
    # 加括号是 PEP 758 的硬性要求（无括号形式不能带 `as` 绑定），与「统一无括号」的风格约定不冲突：
    # 本仓约定里「需要 as 绑定时必须回退加括号」正是这一处。
    except (OSError, ValueError) as e:
        # 超时 / DNS / TLS / 4xx-5xx 都归到「本次拉不到」：URLError 与 HTTPError 都是 OSError
        # 子类，故这一条足以覆盖全部网络侧失败，不需要再列 http.client 的异常类型。
        print(f"[build][warn] 槽位 {slot} 在线清单拉取失败（{type(e).__name__}: {e}），本次不参与判定")
        return ""
    value = _parse_online_sha256(raw.decode("utf-8", errors="replace"), entry.get("kind", ""), asset)
    if not value:
        print(f"[build][warn] 槽位 {slot} 在线清单未解析出 64 位十六进制值（来源 {url}），本次不参与判定")
        return ""
    if entry.get("trust", "") == PIN_TRUST_SIGNED:
        # signed 档：值可用与否取决于**清单本身的验签结果**，而不是它长得像不像哈希。
        if not _pin_source_is_adoptable(entry):
            print(
                f"[build][warn] 槽位 {slot} 声明为 {PIN_TRUST_SIGNED} 档但未登记 40 位主钥指纹，"
                f"不采用在线值（没钉住钥匙的「签名档」等于没验）"
            )
            return ""
        import tempfile

        with tempfile.TemporaryDirectory(prefix="dlr-pinman-") as tmp:
            document = Path(tmp) / "manifest"
            document.write_bytes(raw)
            # 判据与产物侧**同一份**（_verify_gpg_artifact），本层不自造第二套验签口径；
            # strict=False 的语义见该函数：这里是「不采用」，不是「终止构建」。
            ok = _verify_gpg_artifact(
                document,
                Path(tmp) / "manifest.sig",
                _format_pin_url(entry.get("sig_url", ""), slot),
                entry.get("fingerprint", "").strip().lower(),
                f"在线清单 {slot}",
                strict=False,
            )
        if not ok:
            return ""
    return value


def _online_pin_entry(slot: str) -> dict[str, str]:
    # 键的优先级与 _env_pins() 同口径：先查本运行时键那一段，再查通配段 "*"。
    per_key = _PIN_SOURCE_TABLE.get(runtime_slot_key(), {})
    if slot in per_key:
        return per_key[slot]
    return _PIN_SOURCE_TABLE.get("*", {}).get(slot, {})


def _online_pin(slot: str) -> str:
    # 带缓存的在线值；取不到返回空串。进程内缓存的意义见 _PIN_ONLINE_CACHE 注释。
    key = runtime_slot_key()
    cached = _PIN_ONLINE_CACHE.get((key, slot))
    if cached is not None and (time.monotonic() - cached[0]) < _pin_cache_ttl():
        return cached[1]
    value = _fetch_online_pin(_online_pin_entry(slot), slot)
    if value:
        _PIN_ONLINE_CACHE[(key, slot)] = (time.monotonic(), value)
    return value


def _apply_online_pin_source(merged: dict[str, str]) -> None:
    # 在线来源层的落点（默认 off，语义见本节头注释）。**只增不改**：在线值要么被采纳、要么只用于
    # 比对与提示；内置表与 DLR_RUNTIME_SHA256 已经给出的值永不被在线值静默覆盖——否则上游一次
    # 重传就能改写判据，钉定也就不再是一条独立的证据。
    mode = pin_source_mode()
    if mode == PIN_SOURCE_OFF:
        return
    key = runtime_slot_key()
    for slot in runtime_slots_for(key):
        entry = _online_pin_entry(slot)
        if not entry:
            continue  # 该槽没有可拉的官方清单（evermeet 不公布哈希），维持它原有的满足方式
        online = _online_pin(slot)
        if not online:
            continue  # 拉取失败 / 形状非法已在 _fetch_online_pin 里说明，此处不重复打印
        pinned = merged.get(slot, "")
        if not pinned:
            # 内置表这一槽本来就空：在线值只作提示。放行与否仍由 _download_file 的既有闸口决定
            # （那个闸口按 require_pinned_hashes() 决定终止还是告警），本层不抢它的判定。
            print(f"[build][warn] 槽位 {key}/{slot} 内置表未钉定，在线清单值 {online} 仅供人工核对，不参与判定")
            continue
        if online == pinned:
            print(f"[build] 槽位 {key}/{slot} 在线清单与内置钉定一致（{online[:12]}…）")
            continue
        # 走到这里 = 上游清单与内置表不一致，即上游已发新版本（或内置值需要重新核对）。
        if mode == PIN_SOURCE_VERIFY:
            # verify 档**绝不写入**：把它写进期望值就等于跳过「人工回填内置表」这道闸口，
            # 而那道闸口同时也是「发布前重新确认版本代次 / 体积 / 冒烟」的触发点。
            shown = pinned if pinned else UNVERIFIED_PIN
            msg = (
                f"槽位 {key}/{slot} 的上游清单与内置钉定表不一致：内置 {shown}、在线 {online}。"
                f"请核对后回填 build_exe.py 的 _PINNED_RUNTIME_SHA256"
            )
            if require_pinned_hashes():
                raise SystemExit(f"[build][FATAL] {msg}。发布路径为 fail-closed，已终止构建，未开始下载。")
            print(f"[build][warn] {msg}——本地构建继续用内置值，但**该产物不得用于发布**")
            continue
        if not _pin_source_is_adoptable(entry):
            # advisory 档：清单与产物同源同服务器，把它当判据等于把钉定降级成 TOFU。
            print(
                f"[build][warn] 槽位 {key}/{slot} 的在线清单属 {PIN_TRUST_ADVISORY} 档"
                f"（清单与产物同源同服务器，无独立认证），adopt 已跳过、沿用内置值；"
                f"在线值 {online} 仅供人工核对"
            )
            continue
        print(f"[build] 槽位 {key}/{slot} 采用在线清单值（{online[:12]}…）：清单已过钉定指纹验签")
        merged[slot] = online


# 下载文件到 dest 并打印进度（自动跟随重定向）；完成后按钉定值校验完整性，
# 发布路径（CI / --require-pinned）缺钉定即在下载前终止。
#
# slot 为**必填关键字参数**（2026-09-21 收紧，SEV-10 的残留形态）：三个平台的 ffmpeg 临时文件名都是
# _ffmpeg_temp.zip / _ffmpeg_temp.tar.xz，靠 dest.name 兜底查表既分不出平台、也永远命中不了按槽位
# 分列的钉定表。原默认值 slot="" 让 macOS/Linux 两个分支漏传参数而**静默降级**——即便维护者已把
# 官方哈希填进表，那两路依旧查不到 expected：本地路径退化成无校验下载，发布路径则永久红在一处
# 误导人的报错上。去掉默认值后，同类遗漏变成 TypeError + mypy 报错。
def _download_file(url: str, dest: Path, desc: str, *, slot: str) -> None:
    # 先解析钉定值再决定是否下载：fail-closed 的意义包含「不要在未校验的 300MB 上浪费带宽」
    pins = _pinned_slots()
    expected = pins.get(slot, "") if slot else ""
    if not expected:
        expected = pins.get(dest.name, "")
    # 满足口径取 _slot_is_gated 的两个析取项（哈希档 / 官方签名档），**不得**只认 _is_pinned：
    # 只认哈希会让声明为签名档的槽位（macOS 两槽）在下载前即终止，于是「上游确实只给签名」这一档
    # 永远不会被真实构建路径执行到（SEV-2221 的形态：验签代码写在下载后、闸口卡在下载前）。
    signature_mode = _is_signature_satisfied(expected, runtime_slot_key(), slot)
    if not (_is_pinned(expected) or signature_mode):
        _unpinned_action(
            slot or dest.name, dest, desc, _declares_source_build(expected), _is_signature_marker(expected)
        )

    # 下载文件到 dest（带进度输出）；重定向由 urllib 自动跟随。
    print(f"[build] 下载 {desc}：{url}")
    with urllib.request.urlopen(url, timeout=180) as resp:
        total = int(resp.headers.get("Content-Length", 0))
        downloaded = 0
        with open(dest, "wb") as f:
            while True:
                chunk = resp.read(65536)
                if not chunk:
                    break
                f.write(chunk)
                downloaded += len(chunk)
                if total:
                    pct = downloaded * 100 // total
                    print(f"\r[build] {desc}: {downloaded // 1024}KB / {total // 1024}KB ({pct}%)", end="", flush=True)
        print()

    # CR-11：完整性校验。钉定值不匹配即终止构建，避免污染产物被分发。
    h = hashlib.sha256()
    with open(dest, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    actual = h.hexdigest()
    if _is_pinned(expected):
        if expected != actual:
            raise SystemExit(f"[build][FATAL] {dest.name} SHA256 不匹配（期望 {expected}，实际 {actual}），已终止构建")
        print(f"[build] {dest.name} SHA256 校验通过（{slot or dest.name}）")
        # 签名核验只在**哈希已过**之后做：对一份连内容都没核过的产物验签没有意义。
        _verify_official_signature(dest, slot, desc)
    elif signature_mode:
        # 本档没有可比对的公布哈希：**验签本身**就是完整性判据，不能再挂在「哈希已过」的分支里。
        # _verify_gpg_artifact 对 BADSIG/ERRSIG/指纹不在环内一律 SystemExit，发布路径下
        # 「gpg 不可用」与「取不到签名文件」同样 SystemExit，因此控制流能走到下一行
        # 就等于这份产物已由钉定指纹那把钥匙（或其子钥）签出并被 GnuPG 判为 GOOD。
        _verify_official_signature(dest, slot, desc)
        # evermeet 的 getrelease/zip 是滚动别名：签名钉住「谁签的」，钉不住「哪个版本」。
        # 把实测哈希留在构建日志里作事后审计线索（发布产物版本异常时唯一的可比对记录）。
        print(f"[build] {desc} 官方签名核验通过（{slot}），实测 SHA256={actual}")
    else:
        # 仅本地路径可达（发布路径已在下载前终止）：打出实际哈希，供人工核对官方值后钉定
        print(f"[build][warn] {desc} 未钉定 SHA256，请核对官方值后填入 _PINNED_RUNTIME_SHA256：{actual}")


# 下载并解压匹配当前平台的 Node.js LTS 到 target_dir/node/，返回是否成功
def _download_nodejs(target_dir: Path) -> bool:
    # 用官方 dist 源（https://nodejs.org/dist/）自动选取「最新 LTS」× 当前平台/架构的包并解压到
    # target_dir/node/；LTS 随上游漂移正是钉定表的人工闸口（见 _PINNED_RUNTIME_SHA256 注释）。
    try:
        with urllib.request.urlopen("https://nodejs.org/dist/index.json", timeout=30) as resp:
            versions = json.loads(resp.read())
        lts = [v for v in versions if v.get("lts")]
        if not lts:
            print("[build] 未找到 Node.js LTS 版本，跳过 node 下载")
            return False
        version = lts[0]["version"]  # 如 "v22.5.1"

        # 平台/架构映射与运行时钉定键共用模块级常量（见 _NODE_PLATFORM_MAP 上方注释）
        node_plat = _NODE_PLATFORM_MAP.get(sys.platform)
        node_arch = _NODE_ARCH_MAP.get(platform.machine().lower(), "x64")
        if not node_plat:
            print(f"[build] 不支持的平台：{sys.platform}，跳过 node 下载")
            return False

        ext = "zip" if IS_WIN else "tar.gz"
        filename = f"node-{version}-{node_plat}-{node_arch}.{ext}"
        # 供在线钉定来源层代入清单 URL 的 {version} / {filename}：必须在 _download_file 之前写入，
        # 否则那一层只能跳过（它会明确告警说「版本尚未解析」，而不是拼一条恒 404 的残缺 URL）。
        global _NODE_RESOLVED_VERSION, _NODE_RESOLVED_FILENAME
        _NODE_RESOLVED_VERSION = version
        _NODE_RESOLVED_FILENAME = filename
        url = f"https://nodejs.org/dist/{version}/{filename}"
        archive = target_dir / filename
        _download_file(url, archive, f"Node.js {version}", slot="node")

        extract_tmp = target_dir / "_node_extract"
        if extract_tmp.exists():
            shutil.rmtree(extract_tmp)
        extract_tmp.mkdir()
        if IS_WIN:
            with zipfile.ZipFile(archive) as zf:
                zf.extractall(extract_tmp)
        else:
            with tarfile.open(archive, "r:gz") as tf:
                # MI-26：显式传 filter="data"，不依赖 Python 3.12+ 的默认值，
                # 防止将来在更低版本解释器上构建时回归出路径穿越
                tf.extractall(extract_tmp, filter="data")

        extracted = extract_tmp / f"node-{version}-{node_plat}-{node_arch}"
        node_dir = target_dir / "node"
        if node_dir.exists():
            shutil.rmtree(node_dir)
        shutil.move(str(extracted), str(node_dir))

        archive.unlink(missing_ok=True)
        shutil.rmtree(extract_tmp, ignore_errors=True)
        print(f"[build] Node.js {version} 已安装到 {node_dir}")
        return True
    except Exception as e:
        print(f"[build] Node.js 下载失败：{type(e).__name__}: {e}")
        return False


# full zip 的 ffmpeg 来源表：**按运行时键（<os>-<arch>）一条**，与 _PINNED_RUNTIME_SHA256 的分列
# 口径同构（同一份键，才能既查「有没有钉定」又查「钉的是哪一份」）。
# 三个来源的可信度依据（2026-09-22 逐条实测，结论亦写进同日更新日志）：
#   windows → gyan.dev：ffmpeg.org 官方 Windows 条目推荐的构建站，**公布 .sha256 文档**，滚动别名
#             与版本化包两个端点取值互证，故 windows-x64/ffmpeg 已钉定。
#   macos   → evermeet：ffmpeg.org 官方 macOS 条目「Static builds for macOS 64-bit」，自包含构建，
#             **只有 x86_64**——实测 getrelease-arm64/zip 恒 404、页面亦无 arm64 产物，故 Apple
#             Silicon 复用同一份 x86_64 构建、经 Rosetta 2 执行。旧实现按 arm64 拼出一条从不存在的
#             URL，下载失败被 except 吞成一行 warning，于是 Apple Silicon 的 full zip **静默不含
#             ffmpeg**——本次修的就是这个。不公布 SHA256，只给 `/sig` GPG 签名。
#             刻意不用 Homebrew bottle 作 arm64 来源：其 ffmpeg bottle 的 11 个 runtime_deps（dav1d/
#             lame/libvmaf/libvpx/openssl@3/opus/sdl2-compat/svt-av1/x264/x265/xz）的 dylib 位于
#             Homebrew 前缀下的**其他 formulae**、不在 bottle tarball 内，直接打进分发包只会得到
#             `dyld: Library not loaded` 的坏产物。
#   linux   → BtbN FFmpeg-Builds 的 **n9.0 系列**资产（2026-09-26 换源）：选该上游是因为它有一份
#             **可人工核对的公布哈希**——api.github.com 的 release asset 带 `digest: sha256:<64hex>`，
#             取值即按此填入 _PINNED_RUNTIME_SHA256（属平台公布的哈希文档，不是本地下载自算）。
#             版本对齐：gyan/evermeet 当前均为 ffmpeg 9.0.x，故取 `-gpl-9.0` 系列而不是 master 滚动
#             构建，避免三大平台各拉一条不同代次的 ffmpeg。
#             [2026-09-27] URL 里的 release 标签必须钉**月末 autobuild**，绝不用 `latest` 或日更标签：
#             `latest` 是滚动别名（同名资产被反复重传，digest 天天变，钉定当天就可能失配）；日更
#             autobuild 标签实测只保留约两周，钉它等于预埋一次 404。月末标签（如
#             autobuild-2026-08-31-13-27）实测保留到 2024-10-31，URL 与 digest 双双不可变——这才是
#             「钉定」能成立的形态。代价：内置 ffmpeg 会比 `latest` 落后（现为 n9.0.1-11-ge47273f4d9，
#             上游 latest 已到 n9.0.2），升级要人工换标签 + 换钉定值，属刻意的人工闸口。
#             代价（实测 2026-09-27，月末标签资产）：linux64 126,600,656 B / linuxarm64 108,761,296 B，
#             体积门禁需按 report_bundle_size.py 实跑复核，不估算。
#             [历史注] 2026-09-22 起此槽用 johnvansickle 自包含 static 构建（amd64 41,888,096 B），
#             换走的唯一原因是它只提供 *.md5、无 SHA256，导致 --strict 长期拦下发布。
#   两条运行期源（src/ffmpeg_install.py / src/ffmpeg_master_download.py，类别 ②）与本表**互不覆盖**：
#   那里仍按「gyan.dev 为默认唯一自动路径、BtbN master 由 FFMPEG_MASTER_ALLOWED 默认关闭」执行，
#   本表的换源不改动那一侧，也不构成对「BtbN master 无 .sha256 文档」结论的反驳（本表靠的是 GitHub
#   平台 digest + 人工核后写入常量，运行期自动安装拿不到那份带外核对）。
_FFMPEG_DOWNLOAD_URLS: dict[str, str] = {
    "windows-x64": "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip",
    "macos-x64": "https://evermeet.ca/ffmpeg/getrelease/zip",
    "macos-arm64": "https://evermeet.ca/ffmpeg/getrelease/zip",
    "linux-x64": (
        "https://github.com/BtbN/FFmpeg-Builds/releases/download/"
        "autobuild-2026-08-31-13-27/ffmpeg-n9.0.1-11-ge47273f4d9-linux64-gpl-9.0.tar.xz"
    ),
    "linux-arm64": (
        "https://github.com/BtbN/FFmpeg-Builds/releases/download/"
        "autobuild-2026-08-31-13-27/ffmpeg-n9.0.1-11-ge47273f4d9-linuxarm64-gpl-9.0.tar.xz"
    ),
}


def _ffmpeg_source_url() -> str:
    # 未登记的架构组合回落到同族 x64 构建（Windows ARM64 走 x64 仿真；macOS 本就只有 x86_64），
    # 但**绝不静默回落**：连同族项都没有时抛 KeyError，由调用方按「组件下载失败」报告——
    # 「拼出一条不存在的 URL 再被 except 吞掉」正是本次 arm64 缺陷的成因形态。
    key = runtime_slot_key()
    if key in _FFMPEG_DOWNLOAD_URLS:
        return _FFMPEG_DOWNLOAD_URLS[key]
    os_tag = key.partition("-")[0]
    fallback = _FFMPEG_DOWNLOAD_URLS.get(f"{os_tag}-x64")
    if fallback is None:
        raise KeyError(f"ffmpeg 来源表既无 {key!r} 也无 {os_tag}-x64 回落项")
    print(f"[build][warn] 运行时键 {key} 未登记 ffmpeg 来源，回落使用同族 x64 构建")
    return fallback


# 「与 ffmpeg 分家发布」的第二可执行件：{运行时键: {槽位: 归档 URL}}。
# 目前只有 macOS 一支：evermeet 的 getrelease/zip 里**只有 ffmpeg**，ffprobe 要在同页面另下一份
# （getrelease/ffprobe/zip，2026-09-26 实测真实落点 e.deolaha.ca:4242/pub/ffprobe/ffprobe-9.0.2.zip、
# 26,104,193 B，且 .sig 存在、与 ffmpeg 同为已钉主钥的子钥 4E7BEC998E920EE1 签出）。
# gyan.dev 与 BtbN 的归档里 ffmpeg+ffprobe 同包，其完整性已由该平台的 ffmpeg 槽一并覆盖，
# 故本表**不含**windows/linux 键——给同包成员另立一个没有独立公布值的钉定槽，等于凭空造一个假闸口。
# 本表的键集合就是「哪些运行时键多一个下载槽位」的唯一事实源：runtime_slots_for() 与
# scripts/check_runtime_pins.py 的槽位覆盖面都由它推导，不得在第二处再列一遍槽位名。
_EXTRA_EXECUTABLE_URLS: dict[str, dict[str, str]] = {
    "macos-x64": {"ffprobe": "https://evermeet.ca/ffmpeg/getrelease/ffprobe/zip"},
    "macos-arm64": {"ffprobe": "https://evermeet.ca/ffmpeg/getrelease/ffprobe/zip"},
}


def runtime_slots_for(key: str) -> tuple[str, ...]:
    # 该运行时键**实际存在**的下载槽位 = 通用槽位 + 该平台独有的独立归档槽位。
    # 用它而不是全局 RUNTIME_SLOTS 来圈定钉定表的义务范围：ffprobe 只在 macOS 需要单独钉定，
    # 按全局槽位查会让 windows/linux 三键因「缺 ffprobe 钉定项」被判结构缺陷（rc=2）。
    return (*RUNTIME_SLOTS, *tuple(_EXTRA_EXECUTABLE_URLS.get(key, {})))


def _extra_executable_urls() -> dict[str, str]:
    # 当前机器需要另行下载的槽位及其归档 URL；空字典 = 本平台所有可执行件都随主归档同包。
    # 回落规则与 _ffmpeg_source_url 一致（未登记架构回落同族 x64），否则会出现
    # 「ffmpeg 拿到了回落项、ffprobe 查不到键」的半拉子形态。
    key = runtime_slot_key()
    entry = _EXTRA_EXECUTABLE_URLS.get(key) or _EXTRA_EXECUTABLE_URLS.get(f"{key.partition('-')[0]}-x64")
    return dict(entry or {})


# 解包 Linux 的 ffmpeg 归档，把 ffmpeg/ffprobe 取到 ffmpeg_dir（与平台分支解耦，便于在任一
# 开发机上直接驱动真 tarfile + 真目录查找，不必靠 skipif 让 CI 静默丢掉这条锁）。
def _extract_linux_ffmpeg_binaries(archive: Path, ffmpeg_dir: Path) -> None:
    import tempfile

    # 布局一律**递归按名查**（_find_runtime_binary），不硬编码顶层目录形态：johnvansickle 是
    # `ffmpeg-<ver>-<arch>-static/ffmpeg` 平铺，BtbN 是 `<资产名去后缀>/bin/ffmpeg`（2026-09-27 实测
    # 顶层 `ffmpeg-n9.0.1-11-ge47273f4d9-linux64-gpl-9.0/`）。写死任一种，另一种产物会「解包成功但一件没拷」，
    # 而本函数的调用方对此并无感知——唯一兜底只剩出包前的 verify_runtime_binaries。
    missing: list[str] = []
    with tempfile.TemporaryDirectory(dir=ffmpeg_dir.parent) as tmp:
        with tarfile.open(archive, "r:xz") as tf:
            # MI-26：显式传 filter 而非依赖解释器默认值，防止在更低版本解释器上回归出路径穿越
            tf.extractall(tmp, filter="data")
        root = Path(tmp)
        for binary in ("ffmpeg", "ffprobe"):
            found = _find_runtime_binary(root, (binary,))
            if found is None:
                missing.append(binary)
                continue
            # 赋给 _ 只为消除 basedpyright reportUnusedCallResult，非功能所需
            _ = shutil.copy2(found, ffmpeg_dir / binary)
    if missing:
        # 抛 SystemExit 而不是 return False：BaseException 不被调用方的 `except Exception` 吞掉。
        # 「归档里没有可执行件」必须终止构建，不能降级成一行 warning（那正是 arm64 404 长期隐身的路径）。
        raise SystemExit(f"[build][FATAL] Linux ffmpeg 归档内找不到 {'、'.join(missing)}，已终止构建")


# 从 zip 归档里按成员名取可执行件到 dest_dir（Windows 的 gyan zip 与 macOS 的 evermeet zip 共用）。
# 之所以做成一个函数而不是两条分支各写一遍：darwin 分支此前是 `zf.extractall()`，既没有下面这条
# CR-11 路径校验、也没有缺件判定，于是同一份「解包」语义在两处漂移成了两种强度（AGENTS.md 对
# `-segment_format` 事故的结论同源：复制粘贴的分支会各自演化）。
# 三条硬要求：
#   ① CR-11：手工写成员绕过 zipfile.extractall 的路径净化（它会剥离 `..` 与盘符），而 `name` 取自
#      压缩包自述、可含 `../../`——配合无哈希校验可写到任意已存在目录。逐成员做 realpath 前缀校验
#      （与 src/utils.unzip_file 同判据），并限制为期望的可执行文件名。
#   ② 缺件必须 SystemExit 而不是静默出空目录（与 _extract_linux_ffmpeg_binaries 同一条判据）：
#      上游一改内部层级，「解包成功但一件没拷」就又落回「一行 warning + 出包成功」。
#   ③ set_exec_bit：Python 的 ZipFile.extract 系列**不还原**归档外部属性里的 unix mode，只按
#      「成员是否只读」决定要不要去掉写位，落盘即 0o666 & ~umask（macOS 上 0o644）。evermeet 的
#      ffmpeg 在归档里本来是 0o755，解出来却没有可执行位，产物自检直接 PermissionError
#      [Errno 13]（2026-09-26 macOS 实测）。Windows 无此概念，传 False。
def _install_executables_from_zip(
    archive: Path,
    dest_dir: Path,
    allowed_names: tuple[str, ...],
    *,
    require_bin_dir: bool,
    set_exec_bit: bool,
    required: tuple[str, ...],
) -> None:
    dest_root = os.path.realpath(dest_dir)
    written: set[str] = set()
    with zipfile.ZipFile(archive) as zf:
        for member in zf.namelist():
            if member.endswith("/"):
                continue
            if require_bin_dir:
                # gyan.dev zip 内结构：ffmpeg-release-essentials/bin/{ffmpeg,ffprobe}.exe
                if "/bin/" not in member:
                    continue
                name = member.split("/bin/")[-1]
            else:
                # evermeet zip 是平铺布局（成员名即文件名），取 basename 后与白名单比
                name = member.rsplit("/", 1)[-1]
            if not name or name not in allowed_names:
                continue
            target_path = os.path.realpath(dest_dir / name)
            if not target_path.startswith(dest_root + os.sep):
                raise SystemExit(f"[build][FATAL] 压缩包成员路径越界，已终止构建：{member}")
            with zf.open(member) as src, open(target_path, "wb") as dst:
                shutil.copyfileobj(src, dst)
            if set_exec_bit:
                os.chmod(target_path, 0o755)
            written.add(name)
    # 判「有没有取到」按**词干**而不是全名：Windows 侧白名单同时收 ffmpeg 与 ffmpeg.exe，
    # 只比全名会把已经取到的件误判成缺件。
    missing = [stem for stem in required if not any(w == stem or w.split(".")[0] == stem for w in written)]
    if missing:
        raise SystemExit(
            f"[build][FATAL] {archive.name} 内没取到 {'、'.join(missing)}（白名单 {list(allowed_names)}，"
            f"实际命中 {sorted(written)}），已终止构建"
        )


# 按平台下载并解压 ffmpeg/ffprobe 到 target_dir/ffmpeg/，返回是否成功
def _download_ffmpeg(target_dir: Path) -> bool:
    # URL 一律取自 _FFMPEG_DOWNLOAD_URLS（按运行时键查表；来源与可信度依据写在该表上方注释，
    # 勿在此重复），本函数只按平台决定**解压与取用方式**。
    ffmpeg_dir = target_dir / "ffmpeg"
    if ffmpeg_dir.exists():
        shutil.rmtree(ffmpeg_dir)
    ffmpeg_dir.mkdir(parents=True)
    url = _ffmpeg_source_url()

    try:
        if IS_WIN:
            archive = target_dir / "_ffmpeg_temp.zip"
            _download_file(url, archive, "ffmpeg (gyan.dev release-essentials)", slot="ffmpeg")
            _install_executables_from_zip(
                archive,
                ffmpeg_dir,
                ("ffmpeg.exe", "ffprobe.exe", "ffmpeg", "ffprobe"),
                require_bin_dir=True,
                set_exec_bit=False,
                required=("ffmpeg", "ffprobe"),
            )

        elif sys.platform == "darwin":
            # 两架构共用 evermeet x86_64 构建（上游无 arm64 产物，依据见 _FFMPEG_DOWNLOAD_URLS 注释），
            # Apple Silicon 经 Rosetta 2 执行。**不得**再按 machine 拼 arm64 专用 URL——恒 404 且会被
            # 下面的 except 吞成一行 warning，让 full zip 静默缺 ffmpeg。
            archive = target_dir / "_ffmpeg_temp.zip"
            _download_file(url, archive, "ffmpeg (evermeet.ca release)", slot="ffmpeg")
            # 归档成员名是 ffmpeg（evermeet 平铺、无扩展名），执行位要显式补回来
            _install_executables_from_zip(
                archive,
                ffmpeg_dir,
                ("ffmpeg",),
                require_bin_dir=False,
                set_exec_bit=True,
                required=("ffmpeg",),
            )
            # ffprobe 在 evermeet 上是**另一支归档**（依据见 _EXTRA_EXECUTABLE_URLS 注释）：
            # 上面那支里只有 ffmpeg，漏掉这一步会让 macOS 的 full 包长期缺 ffprobe——而 ffmpeg 本身
            # 是好的，缺件要到出包前自检才暴露。列表为空即该平台无需另下。
            for slot, extra_url in sorted(_extra_executable_urls().items()):
                extra_archive = target_dir / f"_{slot}_temp.zip"
                _download_file(extra_url, extra_archive, f"{slot} (evermeet.ca release)", slot=slot)
                _install_executables_from_zip(
                    extra_archive,
                    ffmpeg_dir,
                    (slot,),
                    require_bin_dir=False,
                    set_exec_bit=True,
                    required=(slot,),
                )
                extra_archive.unlink(missing_ok=True)

        else:  # Linux
            archive = target_dir / "_ffmpeg_temp.tar.xz"
            _download_file(url, archive, "ffmpeg (BtbN FFmpeg-Builds n9.0)", slot="ffmpeg")
            _extract_linux_ffmpeg_binaries(archive, ffmpeg_dir)

        archive.unlink(missing_ok=True)
        print(f"[build] ffmpeg 已安装到 {ffmpeg_dir}")
        return True
    except Exception as e:
        print(f"[build] ffmpeg 下载失败：{type(e).__name__}: {e}")
        return False


def _find_runtime_binary(root: Path, names: tuple[str, ...]) -> Path | None:
    # 按名字**递归**找：各上游压缩包内部层级并不统一（Windows 平铺、node 的 tar.gz 带 bin/），
    # 只查根目录会把「布局不同」误判成「组件缺失」。0 字节不算命中——下载被截断时文件是在的。
    if not root.is_dir():
        return None
    for name in names:
        for hit in sorted(root.rglob(name)):
            if hit.is_file() and hit.stat().st_size > 0:
                return hit
    return None


# 每个组件的「版本探针」取值（唯一事实源，_probe_runnable 按此查表）：三者的 CLI 解析器互不通用。
# 实测读数：`node --version` 返回码 0、`node -version` 是「bad option: -version」+ 返回码 1；
# `ffmpeg --version` 返回码 8、`ffmpeg -version` 返回码 0；`ffprobe -version` 返回码 0
# （取自 2026-09-26 三平台 build-release 日志——那两轮自检只点名 node，ffmpeg/ffprobe 均已通过）。
# 取值与运行期自动安装侧保持一致（src/node_install.py 用 `node -v`、src/ffmpeg_install.py 用
# `ffmpeg -version`），免得同一组件在两条路径上被问两个问题。
VERSION_PROBE_ARGS: dict[str, str] = {"ffmpeg": "-version", "ffprobe": "-version", "node": "--version"}


def _probe_runnable(binary: Path, component: str) -> str | None:
    # 跑一次版本探针：文件存在不等于能用。这一 probe 恰好覆盖三种「在包里但跑不动」的形态——
    # 以及解包丢了可执行位（PermissionError）。
    # 探针取值一律查 VERSION_PROBE_ARGS，不在本函数内写死：三平台共用 `-version` 曾让 full 包
    # **一支都出不来**（node 判它非法选项），而反向统一成 `--version` 同样错（ffmpeg 返回码 8）。
    # 输出按字节读、显式解码失败也不参与判定（AGENTS.md「探测子进程输出一律按字节比较」）。
    probe_arg = VERSION_PROBE_ARGS[component]
    try:
        proc = subprocess.run(
            [str(binary), probe_arg],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            timeout=60,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as e:
        # 需要 e 时必须加括号：PEP 758 的无括号写法不支持 as 绑定（AGENTS.md 已记此坑）
        return f"无法执行：{type(e).__name__}: {e}"
    if proc.returncode != 0:
        first = (proc.stderr or b"").splitlines()[:1]
        detail = first[0].decode("latin-1", errors="replace") if first else f"退出码 {proc.returncode}"
        return f"执行 `{probe_arg}` 失败：{detail}"
    return None


def verify_runtime_binaries(target_dir: Path) -> list[str]:
    # full 包出包前的产物自检；返回问题清单（空 = 就绪）。为什么必须查**产物**而不是下载函数的
    # 返回值：download_runtime_binaries 刻意「单组件失败不中断」（两个组件各自 except 后只 return
    # False），于是「缺 ffmpeg 的 full 包」能被静默做出来——macOS arm64 下载点 404 时就是那个形态。
    problems: list[str] = []
    ffmpeg_dir = target_dir / "ffmpeg"
    node_dir = target_dir / "node"

    ffmpeg_bin = _find_runtime_binary(ffmpeg_dir, ("ffmpeg.exe", "ffmpeg"))
    if ffmpeg_bin is None:
        problems.append(f"{ffmpeg_dir} 内找不到非空的 ffmpeg 可执行文件")
    else:
        why = _probe_runnable(ffmpeg_bin, "ffmpeg")
        if why:
            problems.append(f"ffmpeg ({ffmpeg_bin}) {why}")

    ffprobe_bin = _find_runtime_binary(ffmpeg_dir, ("ffprobe.exe", "ffprobe"))
    if ffprobe_bin is None:
        problems.append(f"{ffmpeg_dir} 内找不到非空的 ffprobe 可执行文件")
    else:
        why_probe = _probe_runnable(ffprobe_bin, "ffprobe")
        if why_probe:
            problems.append(f"ffprobe ({ffprobe_bin}) {why_probe}")

    node_bin = _find_runtime_binary(node_dir, ("node.exe", "node"))
    if node_bin is None:
        problems.append(f"{node_dir} 内找不到非空的 node 可执行文件")
    else:
        why_node = _probe_runnable(node_bin, "node")
        if why_node:
            problems.append(f"node ({node_bin}) {why_node}")
    return problems


def download_runtime_binaries(target_dir: Path) -> None:
    # 下载 ffmpeg + node 到 target_dir（用于 --dual 的 full 版本）；单个组件失败不中断，仅打印
    # 警告。SEV-10 例外：完整性判定抛的是 SystemExit（BaseException），不被下面两处
    # `except Exception` 吞掉——「缺钉定 / 哈希不匹配」属于「不得进包」，不是「组件下载失败」。
    # 但下载之后还有一道产物自检：「不中断」只在「有人查产物齐不齐」时才安全，否则它等于把
    # 缺件静默送进分发链。
    print("[build] 开始下载运行时二进制（ffmpeg + Node.js）...")
    _ = _download_ffmpeg(target_dir)
    _ = _download_nodejs(target_dir)
    problems = verify_runtime_binaries(target_dir)
    for problem in problems:
        print(f"[build][error] full 包产物自检：{problem}")
    if problems:
        if require_pinned_hashes():
            raise SystemExit(
                "[build][FATAL] full 包缺少可用运行时组件，已终止（发布路径不允许缺件）：\n  " + "\n  ".join(problems)
            )
        print("[build][warn] 上述缺件的 full 产物**不得用于发布**（本地路径仅告警继续）")
    else:
        print("[build] full 包产物自检通过：ffmpeg / ffprobe / node 均可执行")


# 发布目录内**绝不允许**进包的开发/运行期产物（MID-2254）。与 .gitignore / .dockerignore
# 对同名目录的排除同源，只是作用在「对外分发 zip」这条通道上。
RUNTIME_ARTIFACT_DIR_NAMES: tuple[str, ...] = ("logs", "backup_config", "downloads")


def _clean_runtime_artifacts_from_release() -> list[str]:
    # 压缩前删除发布目录里的运行期产物，返回被删条目的相对路径（供日志打印）。
    # 为什么必须删：冒烟以 cwd=RELEASE_DIR 连跑 CLI 25s / Web 90s / GUI 8s，src/logger.py 会在包根落下
    # streamget.log / PlayURL.log / web_console.log（内容含 runner 绝对路径、用户名与告警堆栈），「缺键
    # 补写」还会改写包内 config.ini；这些随包分发即信息外泄。主修法是「先压缩、后冒烟」（见 main()），
    # 本函数是第二道：清掉上一次构建或本地手工跑过残留在 dist/ 里的同类产物（PyInstaller 的 --clean
    # 只清它自己的缓存）。rmtree 用 ignore_errors=True：Windows 下偶发句柄占用（索引/杀软扫描）不应
    # 让打包整体失败，leftovers 由 _assert_zip_has_no_runtime_artifacts 在实物上兜住。
    removed: list[str] = []
    for name in RUNTIME_ARTIFACT_DIR_NAMES:
        victim = RELEASE_DIR / name
        if victim.is_dir():
            shutil.rmtree(victim, ignore_errors=True)
            removed.append(f"{name}/")
    # __pycache__ 可能出现在任意层级（源码复制、包内脚本被跑过），按目录名自顶向下剔除
    for root, dirs, _files in os.walk(RELEASE_DIR):
        if "__pycache__" in dirs:
            victim = Path(root) / "__pycache__"
            shutil.rmtree(victim, ignore_errors=True)
            dirs.remove("__pycache__")
            removed.append(f"{victim.relative_to(RELEASE_DIR)}/")
    return removed


def _zip_member_is_runtime_artifact(name: str) -> bool:
    # 判定 zip 成员名（`unzip -l` 看到的那一列）是否为不得分发的运行期产物。
    # shutil.make_archive(root_dir=DIST_DIR, base_dir=APP_NAME) 决定了每个成员都以 `DouyinLiveRecorder/`
    # 打头，故先剥掉该前缀再按相对路径判定；zip 规范的分隔符恒为 '/'（不用 os.sep，否则 Windows 上
    # 判不出、Linux CI 上又恰好能过——「本地绿 CI 绿但判据不同」）。
    parts = [p for p in name.replace("\\", "/").split("/") if p and p != "."]
    if parts and parts[0] == APP_NAME:
        parts = parts[1:]
    if not parts:
        return False
    return parts[0] in RUNTIME_ARTIFACT_DIR_NAMES or "__pycache__" in parts


def _assert_zip_has_no_runtime_artifacts(zip_path: Path) -> None:
    # 发布产物清单断言（MID-2254）：zip 内不得出现 logs/ backup_config/ downloads/ 或任意 __pycache__。
    # 为什么清理之后还要在实物上再查一次：清理是 best-effort（ignore_errors），而真正分发出去的是
    # zip——以实物为准才自证。本条等价于把「人工 unzip -l 看一眼」固化成机器断言，删掉它即重新
    # 引入「日志随 full 包外发」这条失效路径（SEV-2213 只判凭据真实值，对不含凭据却泄露环境信息
    # 的日志完全无感，两者互不替代）。
    with zipfile.ZipFile(zip_path) as zf:
        bad = sorted({name for name in zf.namelist() if _zip_member_is_runtime_artifact(name)})
    if bad:
        raise SystemExit(
            "[build][FATAL] 发布 zip 含运行期产物，已终止（这些内容会随包外发给用户）：\n  " + "\n  ".join(bad[:20])
        )


# 把发布目录压成 zip；成员名一律 `<APP_NAME>/<相对路径>`（与旧实现 shutil.make_archive(
# root_dir=DIST_DIR, base_dir=APP_NAME) 逐字同构 —— _assert_zip_has_no_runtime_artifacts 的
# 判据就是按这个前缀剥的，改了前缀等于让那条断言永远绿）。
# 为什么不再用 shutil.make_archive：它内部固定用 zipfile 的默认压缩级别，无法指定
# compresslevel；实测同一发布目录 level=9 比默认再小 1.36%（lite 54.84MB → 54.09MB）。
def _zip_release_dir(zip_path: Path) -> None:
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for path in sorted(RELEASE_DIR.rglob("*")):
            if path.is_file():
                zf.write(path, f"{APP_NAME}/{path.relative_to(RELEASE_DIR).as_posix()}")


# 将发布目录压缩为带平台/架构标识的 zip（suffix 用于 --dual 区分 lite / full），返回路径
def make_zip(version: str, suffix: str = "") -> Path:
    # 压缩是**对外分发的最后一道口**，故两道检查都放在这里而不是调用方，使「--no-zip 跳过压缩」与
    # 「压缩即校验」两条路径都不可能出「绕开校验的 zip」：SEV-2213 的凭据校验（敏感键真实值即
    # SystemExit(1)）管「不得外发真实值」，MID-2254 的清理 + 实物断言管「不得外发环境信息」；
    # 判据不同、互不替代。
    removed = _clean_runtime_artifacts_from_release()
    if removed:
        print(f"[build] 压缩前已剔除发布目录内的运行期产物：{', '.join(removed)}")
    assert_no_credentials_in_release()
    os_tag = {"win32": "windows", "darwin": "macos"}.get(sys.platform, "linux")
    arch = platform.machine().lower()
    # `.zip` 必须与其余段拼进同一个 f-string，**不得**改用 Path.with_suffix(".zip")：版本号本身带点
    # （如 4.3.0），with_suffix 把最后一个点之后的全部内容当旧扩展名整段丢弃，实测
    # （Windows 的架构段实测是 amd64）DouyinLiveRecorder-v4.3.0-windows-amd64-lite
    # → DouyinLiveRecorder-v4.3.zip，于是 lite 与 full
    # 落到同一个路径、full 静默覆盖 lite，dist/ 只剩一个 zip（平台/架构标识也一起没了）。
    # 2026-09-27 CI 实红即此形态：build-release.yml 的 lite/full 校验与 dist/*-lite.zip 上传通配双双落空。
    zip_path = DIST_DIR / f"{APP_NAME}-v{version}-{os_tag}-{arch}{suffix}.zip"
    # version / suffix 一旦含路径分隔符，f-string 拼出的就不再是**单个文件名**而是子路径，
    # 成品会落到 DIST_DIR 之外（Windows 下 pathlib 把 `\` 当分隔符，实测 `make_zip("4.3.0\p1")`
    # 的目标是 dist/DouyinLiveRecorder-v4.3.0/p1-<os>-<arch>.zip）。读版本失败时会回退 "0.0.0"，
    # 静默写到别处比报错更难查，故按「父目录必须还是 dist/」这一结构性不变量拦住（同时覆盖 suffix）。
    if zip_path.parent != DIST_DIR:
        raise SystemExit(f"[build][FATAL] zip 产物名含路径分隔符，会写到 {DIST_DIR} 之外：{zip_path}")
    _zip_release_dir(zip_path)
    _assert_zip_has_no_runtime_artifacts(zip_path)
    print(f"[build] 压缩包已生成：{zip_path}（{zip_path.stat().st_size / 1024 / 1024:.1f} MB）")
    return zip_path


# 压缩前剔除 dist/ 里上一次构建残留的 zip，并把被删名字打进日志（与 _clean_runtime_artifacts_from_release
# 同口径：删了什么都要写出来，不留静默删除）
def _clean_stale_release_zips() -> list[str]:
    # 只按 `{APP_NAME}-v*.zip` 命中，不通配 dist/ 下的一切：用户自己放在 dist/ 里的其它压缩包不归本次
    # 构建管辖。为什么必须删（2026-09-27 复核发布链时列为未闭合项）：build-release.yml 的
    # 「Upload build artifact (inspection only)」用 `path: dist/*.zip`，凡是复用工作区的 runner
    # （自建 / 手动 `--dual` 反复跑）都会把上一轮的 zip 连同本轮一起扫进附件——其中就包括
    # with_suffix 截断缺陷时期那种名字里既无平台也无变体的 `DouyinLiveRecorder-v4.3.zip`。
    # 必须在**第一个** zip 之前调用：放进 make_zip 内会让第二次删掉第一次的产物。
    removed: list[str] = []
    for victim in sorted(DIST_DIR.glob(f"{APP_NAME}-v*.zip")):
        victim.unlink()
        removed.append(victim.name)
    return removed


def _drop_stale_release_zips() -> None:
    stale = _clean_stale_release_zips()
    if stale:
        print(f"[build] 压缩前已剔除 dist/ 内的陈旧 zip：{', '.join(stale)}")


def _assert_dual_zips_are_two_files(lite_zip: Path, full_zip: Path) -> None:
    # make_zip 只自证**单次调用**的名字结构；「两次调用算出同一个路径」这种病（2026-09-27 的
    # with_suffix 截断即此形态）只有事后比对两个返回值才看得见——第二次以 zipfile `"w"` 打开同名文件
    # 是原地截断，不报错、退出码 0。判据与 CI 的 `Verify dist contains both lite & full zips` 同源，
    # 区别只是那条在 runner 上、这条在出包的那台机器上，本地跑 `--dual` 不必等 CI 就能看到红。
    if lite_zip == full_zip:
        raise SystemExit(f"[build][FATAL] --dual 的 lite 与 full 落到同一个文件，后者已覆盖前者：{lite_zip}")
    missing = [zip_path.name for zip_path in (lite_zip, full_zip) if not zip_path.is_file()]
    if missing:
        raise SystemExit(f"[build][FATAL] --dual 已声称出包，但下列产物不存在：{', '.join(missing)}")


# ==================== 冒烟测试 ====================

FATAL_MARKERS = ("Traceback (most recent call last)", "ModuleNotFoundError", "ImportError")


# 准备 URL 配置文件：若为空则写入一条注释示例 URL，避免 CLI 阻塞在 input()。
# 配置在 exe 同级目录（而非 _internal），故写到 RELEASE_DIR/config；样例串与
# _sanitized_url_config_text() 逐字同源，两处不得各自演化。
def _prepare_url_config() -> None:
    url_cfg = RELEASE_DIR / "config" / "URL_config.ini"
    url_cfg.parent.mkdir(parents=True, exist_ok=True)
    if not url_cfg.exists() or not url_cfg.read_text(encoding="utf-8-sig", errors="ignore").strip():
        _ = url_cfg.write_text("#https://live.douyin.com/000000000000\n", encoding="utf-8")


# 以独立进程组/会话启动子进程，便于冒烟结束一次性杀掉整棵进程树（含应用 spawn 的 ffmpeg
# 子进程），避免子进程孤儿化被 runner 清理时刷屏
def _launch(exe: Path, extra_env: "dict[str, str] | None" = None) -> subprocess.Popen[str]:
    # Unix 用 start_new_session=True（子进程成为新会话首领，PGID == 其 PID），Windows 用
    # creationflags=CREATE_NEW_PROCESS_GROUP（新进程组，配合 taskkill /T 递归终止）；两个参数均
    # 显式传递（非本平台的分支取默认 0/False），既满足类型检查又保持跨平台语义。
    # extra_env 合并到 os.environ 后注入子进程（不覆盖其余变量）；冒烟测试用它向 Web 面板传
    #   DOUYIN_WEB_ALLOW_INSECURE=1 以绕过「非回环地址需认证」护栏。
    start_new_session = not IS_WIN
    creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) if IS_WIN else 0
    launch_env = os.environ.copy()
    if extra_env:
        launch_env.update(extra_env)
    return subprocess.Popen(
        [str(exe)],
        cwd=RELEASE_DIR,
        env=launch_env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        start_new_session=start_new_session,
        creationflags=creationflags,
    )


# 杀掉整个进程树（应用本体及其 ffmpeg 子进程），跨平台处理 Windows/Unix。
def _kill_tree(proc: subprocess.Popen[str]) -> None:  # pylint: disable=not-callable,no-member
    # 仅杀父进程会留下孤儿化的 ffmpeg，最终被 runner 的 orphan-process 清理收尸，
    # 产生大量 "Terminate orphan process" 噪声；此处连根拔起避免之。
    pid = proc.pid
    if IS_WIN:
        # taskkill /T 递归终止进程树，/F 强制；进程已退出时忽略错误
        _ = subprocess.run(
            ["taskkill", "/T", "/F", "/PID", str(pid)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return
    # Unix：kill 整个进程组（子进程已是新会话首领，PGID == PID）。
    # getpgid/killpg 为 POSIX-only，用 getattr 兼容类型检查与跨平台运行。
    getpgid = getattr(os, "getpgid", None)
    if getpgid is None:
        return
    try:
        pgid = getpgid(pid)  # type: ignore[misc]  # pylint: disable=not-callable
    except ProcessLookupError:
        return
    killpg = getattr(os, "killpg", None)
    if killpg is None:
        return
    try:
        killpg(pgid, getattr(signal, "SIGKILL", 9))  # type: ignore[misc]  # pylint: disable=not-callable
    except ProcessLookupError:
        pass


# 收尾：终止进程并检查输出中是否有崩溃堆栈（可按 ignore_patterns 豁免良性输出）
def _finish(
    proc: subprocess.Popen[str],
    name: str,
    expect_alive: bool,
    ignore_patterns: "tuple[str, ...]" = (),
) -> None:
    # ignore_patterns：headless CI 等环境下某些库会打印无害堆栈（如 pystray 在无系统托盘时记录
    # "Failed to dock icon" 并附带 Traceback）而应用实际仍正常运行，这类已知良性输出应从致命判定
    # 中排除；真正的崩溃（进程退出或真实堆栈）仍会被捕获。
    still_running = proc.poll() is None
    if still_running:
        _kill_tree(proc)
    try:
        out = proc.communicate(timeout=10)[0] or ""
    except subprocess.TimeoutExpired:
        out = ""
    tail = "\n".join(out.splitlines()[-20:])
    print(f"[smoke:{name}] 进程输出（末尾 20 行）：\n{tail}")
    benign = any(p in out for p in ignore_patterns)
    # 仅当进程已自行退出时，才把 FATAL_MARKERS 视为真实崩溃信号：进程仍存活（still_running）时输出
    # 里的 Traceback 多为应用捕获并记录的异常（asyncio 对未处理任务异常的默认处理会打印完整
    # Traceback 但 loop 继续运行；API 偶发网络错误重试时也会记录堆栈）。真正的崩溃（导入失败 /
    # 未捕获异常）会致进程退出，此时下方 returncode 校验与本判定共同覆盖该情形。
    if not still_running and any(m in out for m in FATAL_MARKERS) and not benign:
        raise RuntimeError(f"[smoke:{name}] 检测到导入错误 / 崩溃堆栈，冒烟测试失败")
    if expect_alive and not still_running and proc.returncode not in (0, None):
        raise RuntimeError(f"[smoke:{name}] 进程异常退出，退出码 {proc.returncode}")
    print(f"[smoke:{name}] 通过 ✅")


# 冒烟：运行 CLI 数秒确认进入监控循环且无崩溃堆栈
def smoke_cli(timeout: int = 25) -> None:
    exe = RELEASE_DIR / f"{APP_NAME}{EXE_SUFFIX}"
    print(f"[smoke:cli] 启动 {exe}（最长 {timeout}s）...")
    proc = _launch(exe)
    start = time.time()
    while time.time() - start < timeout and proc.poll() is None:
        time.sleep(0.5)
    _finish(proc, "cli", expect_alive=True)


# 冒烟：启动 Web 后 HTTP 探活首页（IPv4+localhost），能返回即视为面板可用
def smoke_web(timeout: int = 90, port: int = 8000) -> None:
    # 探测地址同时覆盖 IPv4(127.0.0.1) 与主机名(localhost)：config 默认 web_host=0.0.0.0 时两者均可
    # 达；若 web_host 改为 localhost，macOS 会优先解析为 IPv6(::1)，仅探 IPv4 会误判失败。
    # timeout 取较大值：macOS arm64 冷启动加载 fastapi/uvicorn/httpx 较重，40s 易超时（与平台性能
    # 相关，非应用缺陷）。
    # 关键：用 ProxyHandler({}) 构造「无代理」opener——macOS 上 urllib 默认读系统代理配置
    # （SystemConfiguration），CI runner 的 localhost 请求可能被路由到不存在的代理而挂起超时，
    # 即便服务已正常监听；禁用代理后探测直连本机端口。
    # 安全护栏（web.py C1）：未启用 Web 认证时拒绝监听非回环地址（config 默认 web_host=0.0.0.0）。
    # 冒烟只做本地 HTTP 探活、从不真正暴露到局域网，故注入 DOUYIN_WEB_ALLOW_INSECURE=1 放行——这正是
    # 该环境变量的设计用途（本地 CI/沙箱内临时暴露），不影响生产部署的默认安全行为；同时保留了
    # 「真实绑定 0.0.0.0」的验证路径，比把 web_host 改成 127.0.0.1 更能暴露回归。
    exe = RELEASE_DIR / f"{APP_NAME}-Web{EXE_SUFFIX}"
    hosts = ("127.0.0.1", "localhost")
    print(f"[smoke:web] 启动 {exe}，探活 http://127.0.0.1:{port}/（最长 {timeout}s）...")
    proc = _launch(exe, extra_env={"DOUYIN_WEB_ALLOW_INSECURE": "1"})
    ok = False
    start = time.time()
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        while time.time() - start < timeout and proc.poll() is None:
            for host in hosts:
                try:
                    with cast(http.client.HTTPResponse, opener.open(f"http://{host}:{port}/", timeout=3)) as resp:
                        if resp.status == 200:
                            ok = True
                            break
                except Exception:
                    continue
            if ok:
                break
            time.sleep(1)
    finally:
        _finish(proc, "web", expect_alive=True)
    if not ok:
        raise RuntimeError(f"[smoke:web] {timeout}s 内 HTTP 探活失败（端口 {port} 被占用或启动过慢也会导致此错误）")
    print("[smoke:web] HTTP 探活成功 ✅")


# 冒烟：启动 GUI 数秒确认窗口存活，无显示环境自动跳过
def smoke_gui(timeout: int = 8) -> None:
    if sys.platform not in ("win32", "darwin") and not os.environ.get("DISPLAY"):
        print("[smoke:gui] 无显示环境（DISPLAY 未设置），跳过 GUI 冒烟测试")
        return
    exe = RELEASE_DIR / f"{APP_NAME}-GUI{EXE_SUFFIX}"
    print(f"[smoke:gui] 启动 {exe}（运行 {timeout}s 后终止）...")
    proc = _launch(exe)
    start = time.time()
    while time.time() - start < timeout and proc.poll() is None:
        time.sleep(0.5)
    # GUI 为 windowed 模式，stdout 通常为空；崩溃时进程会提前非零退出。
    # 豁免 pystray 在 headless（无系统托盘）环境的良性 "Failed to dock icon" 堆栈（机理见 _finish）。
    _finish(proc, "gui", expect_alive=True, ignore_patterns=("Failed to dock icon",))


# 依次运行 CLI/Web/GUI 冒烟测试，全部通过才算成功
def smoke_test() -> None:
    _prepare_url_config()
    smoke_cli()
    smoke_web()
    smoke_gui()
    print("[smoke] 全部冒烟测试通过 ✅")


# 将 stdout/stderr 配置为 UTF-8，避免 Windows CI 下中文日志抛 UnicodeEncodeError
def _ensure_utf8_streams() -> None:
    # Windows CI 的 stdout/stderr 默认 cp1252，输出中文日志会抛 UnicodeEncodeError；重配置为 UTF-8，
    # 并让后续派生的 Python 子进程也用 UTF-8。
    # errors 必须显式给 "replace"：TextIOWrapper.reconfigure 在只传 encoding="utf-8" 时会把错误处理器
    # **重置为 "strict"**（CPython 规定，见 io.TextIOWrapper.reconfigure）。本函数在 pytest 进程内被
    # 调用时（tests/test_build_exe.py 三条用例经 main() 调用），sys.stdout/stderr 正是 pytest fd 捕获的
    # EncodedFile（原 errors="replace"），裸调等于把框架资产就地改成 strict，此后任何非 UTF-8 字节
    # 落进捕获文件都会在会话收尾读回时抛 UnicodeDecodeError，表现为「pytest 整轮无结论 + 无关用例
    # 报 FAILED/ERROR」（2026-09-23 故障根因，见 DIAGNOSIS_2026-09-23_pytest-teardown-crash.md）。
    # 与 scripts/run_gates.py 的同款实现同一口径，改一侧须同步另一侧（那里已是 replace）。
    os.environ["PYTHONUTF8"] = "1"
    for s in (sys.stdout, sys.stderr):
        reconfigure = getattr(s, "reconfigure", None)
        if callable(reconfigure):
            try:
                _ = reconfigure(encoding="utf-8", errors="replace")
            except ValueError, OSError:
                pass


# 解析命令行参数并驱动打包/可选冒烟/可选压缩的全流程
def main() -> None:
    global _PIN_SOURCE_OVERRIDE, _REQUIRE_PINNED_OVERRIDE
    _ensure_utf8_streams()
    parser = argparse.ArgumentParser(description=f"{APP_NAME} 打包脚本")
    _ = parser.add_argument("--smoke", action="store_true", help="打包后运行冒烟测试")
    _ = parser.add_argument("--no-zip", action="store_true", help="跳过 zip 压缩")
    _ = parser.add_argument("--no-runtime", action="store_true", help="跳过 ffmpeg/node 打包（用户运行时自动下载）")
    _ = parser.add_argument(
        "--dual", action="store_true", help="同时生成 lite（无运行时）与 full（下载并打包 ffmpeg+node）两个 zip"
    )
    # SEV-10：发布路径 fail-closed。CI 未显式传参时也自动开启（GITHUB_ACTIONS=true）；
    # 这两个参数存在的意义是让「本地也要严格」与「临时放宽排障」两种意图都写在命令行里。
    _ = parser.add_argument(
        "--require-pinned",
        action="store_true",
        default=False,
        help="运行时二进制缺钉定时终止构建（CI 默认已开启，本参数用于本地显式严格化）",
    )
    _ = parser.add_argument(
        "--allow-unpinned",
        action="store_true",
        default=False,
        help="仅本地排障：即使在 CI 环境下也对未钉定的运行时二进制只告警不终止（不得用于发布）",
    )
    # 在线来源层默认关闭：开启后才会联网拉官方清单（语义见「运行时钉定的在线来源」节头注释）。
    _ = parser.add_argument(
        "--pin-source",
        choices=list(_PIN_SOURCE_MODES),
        default=None,
        help=(
            "运行时钉定的在线来源策略：off（默认，只用内置表、不联网）/ "
            "verify（拉取官方清单后只与内置表比对，不一致即告警或终止）/ "
            "adopt（仅『清单有独立认证』的槽位可采用在线值作判据）"
        ),
    )
    args = parser.parse_args()
    smoke = cast(bool, args.smoke)
    no_zip = cast(bool, args.no_zip)
    no_runtime = cast(bool, args.no_runtime)
    dual = cast(bool, args.dual)
    if args.require_pinned and args.allow_unpinned:
        raise SystemExit("[build][FATAL] --require-pinned 与 --allow-unpinned 互斥")
    # --dual 与 --no-zip 互斥（2026-09-27）：--dual 分支从不读 no_zip，旧形态是「显式写了 --no-zip
    # 却被静默无视，照样压出 lite + full 两个大 zip」。矛盾参数组合必须 fail-fast，而不是让其中
    # 一个不起作用——与 zip 名截断同族，都属「发布运行的实际行为与命令写出来的不一致」。
    if dual and no_zip:
        raise SystemExit("[build][FATAL] --dual 与 --no-zip 互斥（--dual 只产出 lite + full 两个 zip）")
    if args.require_pinned:
        _REQUIRE_PINNED_OVERRIDE = True
    elif args.allow_unpinned:
        _REQUIRE_PINNED_OVERRIDE = False
    if args.pin_source:
        _PIN_SOURCE_OVERRIDE = str(args.pin_source)

    version = read_version()
    print(f"[build] 项目版本：v{version}，平台：{sys.platform}/{platform.machine()}")
    strict = "是（缺钉定即终止构建）" if require_pinned_hashes() else "否（仅本地构建，产物不得发布）"
    print(f"[build] 运行时二进制钉定：槽位 {runtime_slot_key()}，要求钉定={strict}，" f"在线来源={pin_source_mode()}")

    if dual:
        # --dual：PyInstaller 只跑一次，先产 lite 再产 full，避免重复打包。
        run_pyinstaller()
        # 顺序（MID-2254）：lite zip → 下载运行时 → full zip → 冒烟。冒烟必须排在**两个** zip 之后：
        # 它以 cwd=RELEASE_DIR 连跑 CLI/Web/GUI 共约 120s，期间 src/logger.py 往包根写日志、应用还会
        # 「缺键补写」改写包内 config.ini；旧顺序（lite → 冒烟 → full）让对外分发的 full 包带上
        # runner 绝对路径/用户名/告警堆栈，属信息外泄；make_zip 内的清理+实物断言只是第二道，顺序才是第一道。
        # 「先出包再冒烟」不削弱冒烟的意义：跑仍是 dist/<APP_NAME>/ 里那三个 exe 本体（与 zip 内容
        # 逐文件同源），只是不再把运行期写入的产物压进包里。
        # 1) lite 版本：仅 config，不含运行时
        _drop_stale_release_zips()
        copy_external_binaries(include_runtime=False)
        _prepare_url_config()  # 确保配置就绪（冒烟测试也需要）
        lite_zip = make_zip(version, suffix="-lite")
        # full 版本：下载并打包 ffmpeg + node
        download_runtime_binaries(RELEASE_DIR)
        full_zip = make_zip(version, suffix="-full")
        _assert_dual_zips_are_two_files(lite_zip, full_zip)
        if smoke:
            smoke_test()
        print(f"[build] 完成。发布目录：{RELEASE_DIR}（已生成 lite + full 两个 zip：{lite_zip.name}、{full_zip.name}）")
        return

    run_pyinstaller()
    copy_external_binaries(include_runtime=not no_runtime)

    # 同上（MID-2254）：先压缩、后冒烟，zip 内容永不含冒烟产物
    zip_path: Path | None = None
    if not no_zip:
        _drop_stale_release_zips()
        zip_path = make_zip(version)

    if smoke:
        smoke_test()

    print(f"[build] 完成。发布目录：{RELEASE_DIR}" + (f"（产物：{zip_path.name}）" if zip_path else ""))


if __name__ == "__main__":
    main()
