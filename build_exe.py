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
#     python build_exe.py --no-runtime # 跳过 ffmpeg/node 打包（交由用户运行时自动下载，减小分发体积）
#     python build_exe.py --dual      # 同时生成 lite（无运行时）与 full（下载并打包 ffmpeg+node）两个 zip
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
import json
import os
import platform
import re
import signal
import shutil
import subprocess
import sys
import tarfile
import time
import urllib.request
import zipfile
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
    'exejs',                         # PyExecJS 继任者，try/except 条件导入需显式收集
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


def copy_external_binaries(include_runtime: bool = True) -> None:
    # 将仓库内已有的 ffmpeg / node / config 目录复制到发布根目录（exe 同级）。
    #
    #     这三者是运行时资源，必须与最终生成的 exe 保持同级（而非收进 _internal/），
    #     以便程序在运行时直接读写配置、调用 FFmpeg / Node.js。
    #     缺失时不报错：程序运行时会自动下载对应平台的 ffmpeg / node。
    #     当 include_runtime=False（--no-runtime）时跳过 ffmpeg/node，
    #     交由用户首次运行时自动下载，可减小分发体积。
    #
    if include_runtime:
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
    else:
        print("[build] --no-runtime：跳过 ffmpeg/ 与 node/（用户首次运行时自动下载）")

    # config 配置目录：保持在 exe 同级，供程序运行时读取
    cfg_src = PROJECT_ROOT / "config"
    if cfg_src.is_dir():
        cfg_dst = RELEASE_DIR / "config"
        _ = shutil.copytree(cfg_src, cfg_dst, dirs_exist_ok=True)
        print(f"[build] 已复制 config/ -> {cfg_dst}")


# ==================== 运行时二进制下载（--dual full 版本） ====================

def _download_file(url: str, dest: Path, desc: str) -> None:
    # 下载文件到 dest（带简单进度输出）。urllib 默认跟随重定向。
    print(f"[build] 下载 {desc}：{url}")
    with urllib.request.urlopen(url, timeout=180) as resp:
        total = int(resp.headers.get('Content-Length', 0))
        downloaded = 0
        with open(dest, 'wb') as f:
            while True:
                chunk = resp.read(65536)
                if not chunk:
                    break
                f.write(chunk)
                downloaded += len(chunk)
                if total:
                    pct = downloaded * 100 // total
                    print(f"\r[build] {desc}: {downloaded // 1024}KB / {total // 1024}KB ({pct}%)",
                          end='', flush=True)
        print()


def _download_nodejs(target_dir: Path) -> bool:
    # 下载并解压 Node.js 预构建二进制到 target_dir/node/。
    # 使用官方 dist 源（https://nodejs.org/dist/），自动选取最新 LTS 与当前平台/架构匹配的包。
    try:
        with urllib.request.urlopen("https://nodejs.org/dist/index.json", timeout=30) as resp:
            versions = json.loads(resp.read())
        lts = [v for v in versions if v.get("lts")]
        if not lts:
            print("[build] 未找到 Node.js LTS 版本，跳过 node 下载")
            return False
        version = lts[0]["version"]  # 如 "v22.5.1"

        plat_map = {"win32": "win", "darwin": "darwin", "linux": "linux"}
        arch_map = {"x86_64": "x64", "amd64": "x64", "arm64": "arm64", "aarch64": "arm64"}
        node_plat = plat_map.get(sys.platform)
        node_arch = arch_map.get(platform.machine().lower(), "x64")
        if not node_plat:
            print(f"[build] 不支持的平台：{sys.platform}，跳过 node 下载")
            return False

        ext = "zip" if IS_WIN else "tar.gz"
        filename = f"node-{version}-{node_plat}-{node_arch}.{ext}"
        url = f"https://nodejs.org/dist/{version}/{filename}"
        archive = target_dir / filename
        _download_file(url, archive, f"Node.js {version}")

        extract_tmp = target_dir / "_node_extract"
        if extract_tmp.exists():
            shutil.rmtree(extract_tmp)
        extract_tmp.mkdir()
        if IS_WIN:
            with zipfile.ZipFile(archive) as zf:
                zf.extractall(extract_tmp)
        else:
            with tarfile.open(archive, "r:gz") as tf:
                tf.extractall(extract_tmp)

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


def _download_ffmpeg(target_dir: Path) -> bool:
    # 下载并解压 ffmpeg 二进制到 target_dir/ffmpeg/。
    #   Windows: gyan.dev release-essentials（提取 bin/）
    #   macOS:   evermeet.ca（arm64 / x64 分别提供）
    #   Linux:   johnvansickle.com 静态构建（含 ffmpeg + ffprobe）
    import tempfile

    ffmpeg_dir = target_dir / "ffmpeg"
    if ffmpeg_dir.exists():
        shutil.rmtree(ffmpeg_dir)
    ffmpeg_dir.mkdir(parents=True)
    machine = platform.machine().lower()

    try:
        if IS_WIN:
            url = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
            archive = target_dir / "_ffmpeg_temp.zip"
            _download_file(url, archive, "ffmpeg")
            # gyan.dev zip 内结构：ffmpeg-release-essentials/bin/{ffmpeg,ffprobe}.exe
            with zipfile.ZipFile(archive) as zf:
                for member in zf.namelist():
                    if '/bin/' in member and not member.endswith('/'):
                        name = member.split('/bin/')[-1]
                        if name:
                            with zf.open(member) as src, open(ffmpeg_dir / name, 'wb') as dst:
                                shutil.copyfileobj(src, dst)

        elif sys.platform == "darwin":
            url = ("https://evermeet.ca/ffmpeg/getrelease-arm64/zip" if machine == "arm64"
                   else "https://evermeet.ca/ffmpeg/getrelease/zip")
            archive = target_dir / "_ffmpeg_temp.zip"
            _download_file(url, archive, "ffmpeg")
            with zipfile.ZipFile(archive) as zf:
                zf.extractall(ffmpeg_dir)

        else:  # Linux
            url = ("https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-arm64-static.tar.xz"
                   if machine in ("arm64", "aarch64")
                   else "https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz")
            archive = target_dir / "_ffmpeg_temp.tar.xz"
            _download_file(url, archive, "ffmpeg")
            with tempfile.TemporaryDirectory(dir=target_dir) as tmp:
                with tarfile.open(archive, "r:xz") as tf:
                    tf.extractall(tmp)
                for item in Path(tmp).iterdir():
                    if item.is_dir() and item.name.startswith("ffmpeg-"):
                        for binary in ("ffmpeg", "ffprobe"):
                            src = item / binary
                            if src.exists():
                                shutil.copy2(str(src), str(ffmpeg_dir / binary))
                        break

        archive.unlink(missing_ok=True)
        print(f"[build] ffmpeg 已安装到 {ffmpeg_dir}")
        return True
    except Exception as e:
        print(f"[build] ffmpeg 下载失败：{type(e).__name__}: {e}")
        return False


def download_runtime_binaries(target_dir: Path) -> None:
    # 下载 ffmpeg + node 到 target_dir（用于 --dual 的 full 版本）。
    # 单个组件失败不中断，仅打印警告（full zip 仍可生成，只是缺该组件）。
    print("[build] 开始下载运行时二进制（ffmpeg + Node.js）...")
    _ = _download_ffmpeg(target_dir)
    _ = _download_nodejs(target_dir)


def make_zip(version: str, suffix: str = "") -> Path:
    # 把发布目录压缩为带平台与架构标识的 zip。
    # suffix 用于 --dual 模式区分 lite / full（如 "-lite"、"-full"）。
    os_tag = {"win32": "windows", "darwin": "macos"}.get(sys.platform, "linux")
    arch = platform.machine().lower()
    zip_base = DIST_DIR / f"{APP_NAME}-v{version}-{os_tag}-{arch}{suffix}"
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
    # 让子进程自成进程组/会话：冒烟结束时能一次性杀掉整棵进程树
    # （含应用 spawn 的 ffmpeg 子进程），避免子进程孤儿化被 runner 清理时刷屏。
    #   - Unix:    start_new_session=True → 子进程成为新会话首领，PGID == 其 PID
    #   - Windows: creationflags=CREATE_NEW_PROCESS_GROUP → 新进程组，配合 taskkill /T 递归终止
    # 两个参数均显式传递（非本平台的分支取默认 0/False），既满足类型检查又保持跨平台语义。
    start_new_session = not IS_WIN
    creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) if IS_WIN else 0
    return subprocess.Popen(
        [str(exe)], cwd=RELEASE_DIR,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, encoding="utf-8", errors="replace",
        start_new_session=start_new_session,
        creationflags=creationflags,
    )


def _kill_tree(proc: subprocess.Popen[str]) -> None:
    # 杀掉整个进程树（应用本体 + 其 spawn 的 ffmpeg 等子进程）。
    # 仅杀父进程会留下孤儿化的 ffmpeg，最终被 runner 的 orphan-process 清理收尸，
    # 产生大量 "Terminate orphan process" 噪声；此处连根拔起避免之。
    pid = proc.pid
    if IS_WIN:
        # taskkill /T 递归终止进程树，/F 强制；进程已退出时忽略错误
        _ = subprocess.run(
            ["taskkill", "/T", "/F", "/PID", str(pid)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        return
    # Unix：kill 整个进程组（子进程已是新会话首领，PGID == PID）。
    # getpgid/killpg 为 POSIX-only，用 getattr 兼容类型检查与跨平台运行。
    getpgid = getattr(os, "getpgid", None)
    if getpgid is None:
        return
    try:
        pgid = getpgid(pid)
    except ProcessLookupError:
        return
    killpg = getattr(os, "killpg", None)
    if killpg is None:
        return
    try:
        killpg(pgid, getattr(signal, "SIGKILL", 9))
    except ProcessLookupError:
        pass


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
        _kill_tree(proc)
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
    _ = parser.add_argument("--no-runtime", action="store_true",
                            help="跳过 ffmpeg/node 打包（用户运行时自动下载）")
    _ = parser.add_argument("--dual", action="store_true",
                            help="同时生成 lite（无运行时）与 full（下载并打包 ffmpeg+node）两个 zip")
    args = parser.parse_args()
    smoke = cast(bool, args.smoke)
    no_zip = cast(bool, args.no_zip)
    no_runtime = cast(bool, args.no_runtime)
    dual = cast(bool, args.dual)

    version = read_version()
    print(f"[build] 项目版本：v{version}，平台：{sys.platform}/{platform.machine()}")

    if dual:
        # --dual：PyInstaller 只跑一次，先产 lite 再产 full，避免重复打包
        run_pyinstaller()
        # 1) lite 版本：仅 config，不含运行时
        copy_external_binaries(include_runtime=False)
        _prepare_url_config()  # 确保配置就绪（冒烟测试也需要）
        _ = make_zip(version, suffix="-lite")
        if smoke:
            smoke_test()
        # 2) full 版本：下载并打包 ffmpeg + node
        download_runtime_binaries(RELEASE_DIR)
        _ = make_zip(version, suffix="-full")
        print(f"[build] 完成。发布目录：{RELEASE_DIR}（已生成 lite + full 两个 zip）")
        return

    run_pyinstaller()
    copy_external_binaries(include_runtime=not no_runtime)

    if smoke:
        smoke_test()

    if not no_zip:
        _ = make_zip(version)

    print(f"[build] 完成。发布目录：{RELEASE_DIR}")


if __name__ == "__main__":
    main()
