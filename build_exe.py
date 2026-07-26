#!/usr/bin/env python3
# -*- encoding: utf-8 -*-
#
# DouyinLiveRecorder 可执行文件打包脚本（本地 / GitHub Actions 通用）
#
# 一次构建产出三个入口（共享同一发布目录的依赖与资源）：
#     DouyinLiveRecorder(.exe)        CLI 录制核心（main.py，控制台）
#     DouyinLiveRecorder-GUI(.exe)    图形界面（gui.py，无控制台窗口）
#     DouyinLiveRecorder-Web(.exe)    Web 管理面板（web.py，控制台）
#
# 用法：
#     python build_exe.py             # 打包并生成 zip 产物
#     python build_exe.py --smoke     # 打包后额外运行冒烟测试（CI 推荐）
#     python build_exe.py --no-zip    # 只打包不压缩
#
# 打包策略（onedir + contents_directory='_internal'）：
#     目录组织规范（最终产物结构）：
#         dist/DouyinLiveRecorder/
#         ├── DouyinLiveRecorder(.exe)        CLI 录制核心（main.py，控制台）
#         ├── DouyinLiveRecorder-GUI(.exe)    图形界面（gui.py，无控制台窗口）
#         ├── DouyinLiveRecorder-Web(.exe)    Web 管理面板（web.py，控制台）
#         ├── config/                         配置目录（exe 同级，运行时直接读写）
#         ├── ffmpeg/                         FFmpeg 运行时（exe 同级）
#         ├── node/                           Node.js 运行时（exe 同级）
#         └── _internal/                      依赖包 + src/ 及打包资源（i18n/ web/ src/javascript）
#     即：node/ffmpeg/config 三个目录与最终 exe 保持同级；src/ 与全部 Python 依赖包
#     统一收入 _internal/ 管理。
#     采用 contents_directory='_internal' 后，PyInstaller 把所有依赖与经 __file__ 定位的
#     资源（i18n/ web/ src/javascript）收进 exe 同级的 _internal/；而经 sys.argv[0]/
#     sys.executable 定位的运行时资源（config/ ffmpeg/ node）由本脚本在 COLLECT 之后
#     复制到 exe 同级目录（见 copy_external_binaries / _prepare_url_config），
#     二者通过 src/logger._app_root() 收敛到 exe 同级目录。
#     多入口共享依赖必须使用 .spec 文件（命令行不支持多 Analysis），
#     故本脚本动态生成 spec 后调用 PyInstaller。
#
# 产物：
#     dist/DouyinLiveRecorder/                          发布目录（3 个 exe + 运行时目录 + _internal/ 依赖）
#     dist/DouyinLiveRecorder-{ver}-{os}-{arch}.zip     压缩包
#
import argparse
import os
import platform
import re
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from typing import cast

import http.client

PROJECT_ROOT = Path(__file__).resolve().parent
APP_NAME = "DouyinLiveRecorder"
DIST_DIR = PROJECT_ROOT / "dist"
RELEASE_DIR = DIST_DIR / APP_NAME
SPEC_PATH = PROJECT_ROOT / "DouyinLiveRecorder.spec"
# 与下方 spec 模板中的 contents_directory 保持一致：冻结后所有资源落在 _internal/
CONTENTS_DIR = "_internal"
IS_WIN = sys.platform == "win32"
EXE_SUFFIX = ".exe" if IS_WIN else ""

# 动态生成的 PyInstaller spec 模板：
# - 三个 Analysis / EXE，共用一个 COLLECT（依赖去重，体积约为独立打包的 1/3）
# - 数据文件只挂在 CLI 的 Analysis 上即可（COLLECT 合并时统一落盘）
SPEC_TEMPLATE = """\
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


def read_version() -> str:
    # 从 main.py 中解析版本号，解析失败时回退到 0.0.0
    text = (PROJECT_ROOT / "main.py").read_text(encoding="utf-8")
    m = re.search(r'^version:\s*str\s*=\s*["\'](v?[\w.\-]+)["\']', text, re.M)
    return m.group(1).lstrip("v") if m else "0.0.0"


def run_pyinstaller() -> None:
    # 生成 spec 并调用 PyInstaller 完成三入口 onedir 打包
    _ = SPEC_PATH.write_text(SPEC_TEMPLATE.format(app=APP_NAME), encoding="utf-8")
    print(f"[build] 已生成 spec：{SPEC_PATH}")
    cmd = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", str(SPEC_PATH)]
    print(f"[build] PyInstaller 命令：\n  {' '.join(cmd)}")
    _ = subprocess.run(cmd, check=True, cwd=PROJECT_ROOT)


def copy_external_binaries() -> None:
    # 将仓库内已有的 ffmpeg / node / config 目录复制到发布根目录（exe 同级）。
    #
    #     这三者是运行时资源，必须与最终生成的 exe 保持同级（而非收进 _internal/），
    #     以便程序在运行时直接读写配置、调用 FFmpeg / Node.js。
    #     缺失时不报错：程序运行时会自动下载对应平台的 ffmpeg / node。
    #
    for name in ("ffmpeg", "node"):
        src = PROJECT_ROOT / name
        if not src.is_dir():
            continue
        has_exe = any(p.suffix == ".exe" for p in src.iterdir())
        if has_exe and not IS_WIN:
            print(f"[build] 跳过 {name}/（Windows 二进制，与当前平台不符）")
            continue
        dst = RELEASE_DIR / name  # exe 同级目录
        _ = shutil.copytree(src, dst, dirs_exist_ok=True)
        print(f"[build] 已复制 {name}/ -> {dst}")

    # config 配置目录：保持在 exe 同级，供程序运行时读取
    cfg_src = PROJECT_ROOT / "config"
    if cfg_src.is_dir():
        cfg_dst = RELEASE_DIR / "config"
        _ = shutil.copytree(cfg_src, cfg_dst, dirs_exist_ok=True)
        print(f"[build] 已复制 config/ -> {cfg_dst}")


def make_zip(version: str) -> Path:
    # 把发布目录压缩为带平台与架构标识的 zip
    os_tag = {"win32": "windows", "darwin": "macos"}.get(sys.platform, "linux")
    arch = platform.machine().lower()
    zip_base = DIST_DIR / f"{APP_NAME}-v{version}-{os_tag}-{arch}"
    zip_path = Path(shutil.make_archive(str(zip_base), "zip", DIST_DIR, APP_NAME))
    print(f"[build] 压缩包已生成：{zip_path}（{zip_path.stat().st_size / 1024 / 1024:.1f} MB）")
    return zip_path


# ==================== 冒烟测试 ====================

FATAL_MARKERS = ("Traceback (most recent call last)", "ModuleNotFoundError", "ImportError")


def _prepare_url_config() -> None:
    # 写入一条注释 URL，避免 URL 配置为空时 CLI 阻塞在 input()
    #
    #     配置保持在 exe 同级目录（而非 _internal），故写到 RELEASE_DIR/config。
    #
    url_cfg = RELEASE_DIR / "config" / "URL_config.ini"
    url_cfg.parent.mkdir(parents=True, exist_ok=True)
    if not url_cfg.exists() or not url_cfg.read_text(encoding="utf-8-sig", errors="ignore").strip():
        _ = url_cfg.write_text("#https://live.douyin.com/000000000000\n", encoding="utf-8")


def _launch(exe: Path) -> subprocess.Popen[str]:
    return subprocess.Popen(
        [str(exe)], cwd=RELEASE_DIR,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, encoding="utf-8", errors="replace",
    )


def _finish(
    proc: subprocess.Popen[str],
    name: str,
    expect_alive: bool,
    ignore_patterns: "tuple[str, ...]" = (),
) -> None:
    # 收尾：终止进程、检查输出中是否有崩溃堆栈。
    # ignore_patterns：在 headless CI 等环境下，某些库会打印无害的堆栈（如 pystray 在
    # 无系统托盘时记录 "Failed to dock icon" 并附带 Traceback），应用实际仍正常运行。
    # 这类已知良性输出应从致命判定中排除；真正的崩溃（进程退出或真实堆栈）仍会被捕获。
    still_running = proc.poll() is None
    if still_running:
        proc.kill()
    try:
        out = proc.communicate(timeout=10)[0] or ""
    except subprocess.TimeoutExpired:
        out = ""
    tail = "\n".join(out.splitlines()[-20:])
    print(f"[smoke:{name}] 进程输出（末尾 20 行）：\n{tail}")
    benign = any(p in out for p in ignore_patterns)
    if any(m in out for m in FATAL_MARKERS) and not benign:
        raise RuntimeError(f"[smoke:{name}] 检测到导入错误 / 崩溃堆栈，冒烟测试失败")
    if expect_alive and not still_running and proc.returncode not in (0, None):
        raise RuntimeError(f"[smoke:{name}] 进程异常退出，退出码 {proc.returncode}")
    print(f"[smoke:{name}] 通过 ✅")


def smoke_cli(timeout: int = 25) -> None:
    # CLI：运行数秒确认进入监控循环且无崩溃
    exe = RELEASE_DIR / f"{APP_NAME}{EXE_SUFFIX}"
    print(f"[smoke:cli] 启动 {exe}（最长 {timeout}s）...")
    proc = _launch(exe)
    start = time.time()
    while time.time() - start < timeout and proc.poll() is None:
        time.sleep(0.5)
    _finish(proc, "cli", expect_alive=True)


def smoke_web(timeout: int = 90, port: int = 8000) -> None:
    # Web：启动后 HTTP 探活首页，能返回即视为面板可用。
    # 探测地址同时覆盖 IPv4(127.0.0.1) 与主机名(localhost)：
    #   - config 默认 web_host=0.0.0.0 时两者均可达；
    #   - 若 web_host 改为 localhost，macOS 会优先解析为 IPv6(::1)，
    #     仅探 IPv4 会误判失败，故两地址都试。
    # timeout 取较大值：macOS arm64 冷启动加载 fastapi/uvicorn/httpx 较重，
    # 40s 易超时（与平台性能相关，非应用缺陷）。
    # 关键：用 ProxyHandler({}) 构造「无代理」opener。macOS 上 urllib 默认会读取
    # 系统代理配置（SystemConfiguration），CI runner 的 localhost 请求可能被路由到
    # 不存在的代理而挂起超时——即便服务已正常监听。禁用代理后探测直连本机端口。
    exe = RELEASE_DIR / f"{APP_NAME}-Web{EXE_SUFFIX}"
    hosts = ("127.0.0.1", "localhost")
    print(f"[smoke:web] 启动 {exe}，探活 http://127.0.0.1:{port}/（最长 {timeout}s）...")
    proc = _launch(exe)
    ok = False
    start = time.time()
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        while time.time() - start < timeout and proc.poll() is None:
            for host in hosts:
                try:
                    with cast(http.client.HTTPResponse,
                              opener.open(f"http://{host}:{port}/", timeout=3)) as resp:
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
        raise RuntimeError(
            f"[smoke:web] {timeout}s 内 HTTP 探活失败（端口 {port} 被占用或启动过慢也会导致此错误）"
        )
    print("[smoke:web] HTTP 探活成功 ✅")


def smoke_gui(timeout: int = 8) -> None:
    # GUI：启动数秒确认窗口进程存活且无崩溃；无显示环境自动跳过
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
    # 忽略 pystray 在 headless（无系统托盘）环境打印的良性 "Failed to dock icon" 堆栈：
    # 此时 GUI 窗口仍正常运行，不应判为失败。
    _finish(proc, "gui", expect_alive=True, ignore_patterns=("Failed to dock icon",))


def smoke_test() -> None:
    _prepare_url_config()
    smoke_cli()
    smoke_web()
    smoke_gui()
    print("[smoke] 全部冒烟测试通过 ✅")


def _ensure_utf8_streams() -> None:
    # Windows CI 的 stdout/stderr 默认编码为 cp1252，无法输出中文日志会抛
    # UnicodeEncodeError。重新配置为 UTF-8，并让后续派生的 Python 子进程也用 UTF-8。
    os.environ["PYTHONUTF8"] = "1"
    for s in (sys.stdout, sys.stderr):
        reconfigure = getattr(s, "reconfigure", None)
        if callable(reconfigure):
            try:
                _ = reconfigure(encoding="utf-8")
            except (ValueError, OSError):
                pass


def main() -> None:
    _ensure_utf8_streams()
    parser = argparse.ArgumentParser(description=f"{APP_NAME} 打包脚本")
    _ = parser.add_argument("--smoke", action="store_true", help="打包后运行冒烟测试")
    _ = parser.add_argument("--no-zip", action="store_true", help="跳过 zip 压缩")
    args = parser.parse_args()
    smoke = cast(bool, args.smoke)
    no_zip = cast(bool, args.no_zip)

    version = read_version()
    print(f"[build] 项目版本：v{version}，平台：{sys.platform}/{platform.machine()}")

    run_pyinstaller()
    copy_external_binaries()

    if smoke:
        smoke_test()

    if not no_zip:
        _ = make_zip(version)

    print(f"[build] 完成。发布目录：{RELEASE_DIR}")


if __name__ == "__main__":
    main()
