#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Linux 原生 ffmpeg 直下安装器（AGENTS.md「三类钉定/校验」的类别②，Linux 分支）。
#
# 为什么需要它：install_ffmpeg_linux() 原先只有 yum/apt 两条路，两者都要求 root 且要求发行版仓库里
#   有 ffmpeg 包。aarch64 上的轻量发行版/容器/无 root 部署正好同时缺这两条，于是「未装 ffmpeg」
#   在 Linux 上只剩「请手动安装」一句死路。
#
# 为什么默认路径必须已校验：AGENTS.md ② 的红线是「TOFU 不得成为默认路径」。期望值来自
#   api.github.com 上该 release asset 的 digest 字段，下载 URL 里的标签是**月末 autobuild**
#   （与 build_exe._FFMPEG_DOWNLOAD_URLS 同一份，一致性由 tests/test_ffmpeg_linux_download.py 的
#   TestUrlParityWithBuildExe 锁住）——标签不可变，期望值不会随上游重发漂移。
#   [口径] 它与产物同属 GitHub 平台但**异服务**（API 域 ↔ 对象存储域），属「同源一致性校验而非
#   来源认证」，与 gyan.dev 的 .sha256 同级，**不得**写成「已认证来源」。
#
# 为什么降级档仍要开关：GitHub API 不可达 / 403 限流时拿不到 digest，唯一可选项是首次信任，与
#   Windows 的 master 源同强度，故复用同一个默认关闭的开关 FFMPEG_MASTER_ALLOWED，并由**调用方
#   传入** master_allowed（本模块反向 import ffmpeg_install 会构成循环依赖）。
#
# 为什么单独成模块：ffmpeg_master_download.py 的语义是「master 滚动别名 + 只有 TOFU 一档 + 只认
#   zip」，把「不可变标签 + 官方 digest + tar.xz」塞进去会让两个完整性档在同模块内互相打脸。

import contextlib
import os
import platform
import re
import secrets
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any, BinaryIO, cast

import requests
from loguru import logger

import i18n
from src import utils

# 与 ffmpeg_master_download 同量级但**各自持有**：跨模块引私有常量会把 Windows 语义模块的内部细节
# 变成第二个耦合点（该模块的超时取值是为「挑战页探针」调的，Linux 侧没有这个问题）。
_CONNECT_TIMEOUT = 15
_READ_TIMEOUT = 30
_MAX_RETRIES = 3
_RETRY_BACKOFF = 2.0

# 临时归档的**前缀**（M-44）：保留 ffmpeg_linux_native_temp 这段可识别前缀给既有断言与日志定位，
# 随机后缀由内联块 unique_path 追加；实际写入一律走 open_exclusive（O_CREAT|O_EXCL|O_NOFOLLOW）。
_TEMP_ARCHIVE_PREFIX = "ffmpeg_linux_native_temp"
_TEMP_ARCHIVE_SUFFIX = ".tar.xz"
# 单次下载的字节上限（M-49 的第三件事：本模块此前有重试、无量）。BtbN 的 linux*-gpl tar.xz 当前约
# 100MB，取 512MiB 给上游构建增长留余量；与另两条链同值但各存一份，理由见 _CONNECT_TIMEOUT 处注释。
_MAX_ARCHIVE_BYTES = 512 * 1024 * 1024

# 与 build_exe._is_pinned 同一条形状关：只看形状不看语义，占位/截断/大写形态一律算「取不到」。
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
# 只认 https 的 GitHub release 直链：形态不符即无法反解 repo/tag，一律按「取不到官方哈希」处理，
# 绝不带着猜想的 API URL 出站。
_ASSET_URL_PATTERN = re.compile(
    r"^https://github\.com/(?P<repo>[^/]+/[^/]+)/releases/download/(?P<tag>[^/]+)/(?P<asset>[^/]+)$"
)

_HASH_PREFIX = "_ffmpeg_linux"
_HASH_SUFFIX = ".tar.xz.sha256"

# 两条 URL 与 build_exe._FFMPEG_DOWNLOAD_URLS 的 linux 两项**逐字相同**（物理上两份：冻结 exe 里
# import 不到根目录 build 脚本）。改一处必须同步另一处，由 TestUrlParityWithBuildExe 机检。
_LINUX_FFMPEG_URLS: dict[str, str] = {
    "linux64": (
        "https://github.com/BtbN/FFmpeg-Builds/releases/download/"
        "autobuild-2026-08-31-13-27/ffmpeg-n9.0.1-11-ge47273f4d9-linux64-gpl-9.0.tar.xz"
    ),
    "linuxarm64": (
        "https://github.com/BtbN/FFmpeg-Builds/releases/download/"
        "autobuild-2026-08-31-13-27/ffmpeg-n9.0.1-11-ge47273f4d9-linuxarm64-gpl-9.0.tar.xz"
    ),
}


# =============================================================================
# 运行期安装器的落盘纪律原语（M-44 独占创建与目录锁 / M-45 暂存后改名替换 / M-47 PATH 去重前置 /
# M-48 解包前空间预检）——**内联孪生块**。
#
# 2026-10-21 用户要求把原先的 src/download_guard.py 内联回三个安装器，故本块在
#   ffmpeg_install.py / ffmpeg_master_download.py / ffmpeg_linux_download.py 中**逐字重复**。
# 三份必须同改：一致性由 tests/test_ffmpeg_install.py::TestInlineInstallGuardParity 机检
#   （提取 BEGIN/END 标记之间的字节并断言三份相等）。日志前缀刻意保留 "download_guard:" 原文，
#   以免改动已登记的 15 条 i18n msgid。
#
# 能力边界（勿据此高估，也别按「分布式锁」理解本块）：
#   1) install_lock 是**尽力而为**的互斥——靠本地文件系统上 O_CREAT|O_EXCL 的原子创建 + 按龄回收。
#      它要治的故障是「同机两个实例互相覆盖对方的下载包、并在各自 finally 里 unlink 掉对方的文件」；
#      NFS 之类的共享目录不保证创建原子性，本块不假装解决那一层。
#   2) 符号链接拒绝位 O_NOFOLLOW 在 Windows 上**不存在**（本仓 Python 3.14 win32 实测 os 无该属性）。
#      Windows 侧靠「名字不可预测」：随机后缀使攻击者无法在链接位置上等到本次要写的那个名字，
#      而 O_EXCL 保证「名字已被占用」（占用者是不是链接都一样）时绝不写入、绝不跟随。
#   3) swap_directories 的「原子」是**两次改名之间的短暂窗口**（先让位、再落位），不是文件系统级原子
#      替换。取舍在于：窗口期只有毫秒级的「PATH 上暂时少一个 ffmpeg」，而旧实现的
#      `rmtree → copytree` 窗口是「几百 MB 拷贝的全程」，且中途失败就是永久空壳（M-45 的成因）。
# >>> BEGIN INLINE INSTALL-GUARD BLOCK (keep byte-identical across the three installers)
# 平台专属符号一律用 `sys.platform` 字面量门控（AGENTS.md「平台专属符号必须 sys.platform 字面量门控」）：
# mypy 在 --platform win32 / --platform linux 下各只分析其中一支，另一支按常量真值判不可达。
# **不得**改用 `# type: ignore` 糊另一侧（那会在另一平台触发 basedpyright reportUnnecessaryTypeIgnoreComment），
# 也**不得**用三参 getattr 取这两个符号（Any 泄漏，见「已知坑」三参 getattr 条目）。
if sys.platform == "win32":
    # win32 无 O_NOFOLLOW；低层 fd 的二进制形态由显式 O_BINARY 表达（调用点还会再包一层 fdopen("wb")，
    # 两处任一成立都不会做换行翻译，双重写下不依赖任何一侧的实现细节）。
    _O_NOFOLLOW: int = 0
    _O_BINARY: int = os.O_BINARY
else:
    _O_NOFOLLOW = os.O_NOFOLLOW
    _O_BINARY = 0

# 独占创建位组合：O_EXCL 必须与 O_CREAT 同时给出才是「存在即失败」，单独 O_EXCL 在 POSIX 上是未定义组合。
_EXCLUSIVE_FLAGS = os.O_WRONLY | os.O_CREAT | os.O_EXCL | _O_NOFOLLOW | _O_BINARY

# 随机名后缀的熵源字节数（落成 8 个十六进制字符）。刻意不走 `tempfile.mkstemp`：它的公开签名**不接受**
#   flags 实参（本仓 Python 3.14 实测无该参数，带 flags 的是私有 `_mkstemp_inner`），拿不到 O_NOFOLLOW；
#   而且本仓要求「保留可识别前缀给既有断言与日志定位」，自己拼名反而口径清楚。
_TOKEN_BYTES = 4
# 回滚位命名冲突时的重试轮数：随机名撞上同名（含被人预置）时换名再来，超过即判「本目录无法安全腾出回滚位」。
_MAX_NAME_ATTEMPTS = 8

# 目录锁的回收年龄（秒）。取值口径：一次自动安装的最坏耗时（取 ~200MB 包 + 解包 + 同级暂存拷贝）再乘二。
#   持有者进程崩溃后留下的锁**必须**能被回收，否则这条兜底路径会永久失效；反过来把窗口压到分钟级，
#   会把「仍在正常下载的另一个实例」当成陈旧锁而并发起来，等于没锁。
_LOCK_STALE_SECONDS = 1800.0
_LOCK_FILE_NAME = ".ffmpeg_install_lock"

# 进程内已持有的锁路径（键为归一化后的绝对路径）。用途只有一个：同进程内的嵌套调用不得自锁——
#   install_ffmpeg_windows 会先后走官方源与 master 两条链，今天是顺序执行、不嵌套，但「一改就自锁」
#   这种潜在形态必须由本集合消掉，而不是留给未来某次改动去踩。
_HELD_LOCKS: set[str] = set()
# 保护 _HELD_LOCKS 自身的锁。**必须**是 RLock：install_lock 存在重入路径（上一条那一支就是），
#   普通 Lock 下同线程第二次进入会自锁（AGENTS.md「跨 await 持有的跨线程锁一律用 threading.RLock」）。
_HELD_LOCKS_GUARD = threading.RLock()

# 解包空间系数：压缩包 → 解包产物约 3~4 倍（gyan.dev essentials ~90MB → ~300MB），M-45 的同级暂存副本
#   还要**再落一份**解包产物，故取 8 倍，并留出交换窗口内新旧两份并存的余量。判据是「估算」不是「实测」，
#   所以宁大勿小：预检只负责在小 tmpfs / 快满的磁盘上**提前**失败，不承担精确记账。
UNPACK_SPACE_FACTOR = 8.0


# 生成**不可预测**的目标文件名：保留调用方给的可识别前缀（既有断言与日志靠它定位），追加随机后缀。
# 只命名、不创建——创建一律走 open_exclusive，中间不做任何「先看后写」的判定（那是 TOCTOU 的入口）。
def unique_path(dir_path: str | Path, prefix: str, suffix: str) -> Path:
    return Path(dir_path) / (prefix + str(os.getpid()) + "-" + secrets.token_hex(_TOKEN_BYTES) + suffix)


# 以「独占 + 不跟随符号链接」打开写入目标，返回已就位的二进制写句柄。
# 失败形态一律抛 OSError 且**不产生任何写入**：FileExistsError（名字已被占用；占用者可能是本地攻击者
#   预置的符号链接，也可能是另一个实例刚创建的包）、PermissionError、目录不存在。
# 调用方据此判失败即可，**不得**在外层补一句「那就换个名字重写」——那等于把「已存在」重新解释成
#   「可以覆盖」，正是 M-44 要关掉的那扇门。
def open_exclusive(path: str | Path) -> BinaryIO:
    fd = os.open(str(path), _EXCLUSIVE_FLAGS, 0o600)
    try:
        return cast(BinaryIO, os.fdopen(fd, "wb"))
    except OSError:
        # fdopen 失败时 fd 仍归我们，必须显式关闭：句柄泄漏会让 Windows 上的后续 unlink 一直失败。
        os.close(fd)
        raise


# 目录级跨进程互斥。上下文管理器 **yield True=拿到锁 / yield False=没拿到**（而不是抛异常）：
# 三条安装链的统一契约是「失败只返回 False、绝不抛出穿出启动流程」，锁竞争属失败而不是异常。
# 释放动作在 finally 里；进程被杀后留下的锁由 _take_over_stale_lock 按龄回收。
@contextlib.contextmanager
def install_lock(dir_path: str | Path, file_name: str = _LOCK_FILE_NAME) -> Iterator[bool]:
    lock_path = Path(dir_path) / file_name
    # 归一化键：同一目录的不同写法（尾斜杠、大小写、符号链接别名）必须落到同一个进程内键上，
    # 否则嵌套守卫形同虚设。realpath 不要求路径存在，对「目录还不存在」的调用同样安全。
    held_key = os.path.realpath(str(lock_path))
    with _HELD_LOCKS_GUARD:
        if held_key in _HELD_LOCKS:
            # 同进程重入：外层已经持有，本轮直接放行，退出时也**不得**替外层释放。
            yield True
            return
    if not _acquire_lock(lock_path):
        yield False
        return
    with _HELD_LOCKS_GUARD:
        _HELD_LOCKS.add(held_key)
    try:
        yield True
    finally:
        with _HELD_LOCKS_GUARD:
            _HELD_LOCKS.discard(held_key)
        _release_lock(lock_path)


def _acquire_lock(lock_path: Path) -> bool:
    # 锁文件本身也走独占创建：有人在锁路径上预置链接时只能「创建失败」，
    # 持有者信息不会被写进攻击者的文件。
    try:
        fd = os.open(str(lock_path), _EXCLUSIVE_FLAGS, 0o600)
    except FileExistsError:
        return _take_over_stale_lock(lock_path)
    except OSError as e:
        # 连锁都建不出来（只读目录 / 目录不存在）：按「拿不到锁」处理，让调用方放弃本次安装。
        logger.warning("download_guard: cannot create the install lock file in the target directory")
        logger.debug("download_guard: lock create failed: " + type(e).__name__)
        return False
    try:
        os.write(fd, ("pid=" + str(os.getpid())).encode("ascii"))
    except OSError as e:
        # 持有者信息写不进去不影响互斥本身（创建成功即已排他），只影响陈旧判定的一条辅助线索。
        logger.debug("download_guard: lock owner record failed: " + type(e).__name__)
    finally:
        os.close(fd)
    return True


def _take_over_stale_lock(lock_path: Path) -> bool:
    # 回收判据只留「年龄」这一个可机检形态：PID 存活探测在 Windows 上要引 CreateProcess/toolhelp 那一套
    # 平台专属符号，为一个尽力而为的互斥引入平台分叉不值得，而且跨机场景下 PID 复用会误判。
    if os.path.islink(str(lock_path)):
        # 锁路径被人做成了链接：本函数**从不**跟随，也从不删「猜出来的」攻击者目标——直接判拿不到锁，
        # 让调用方放弃本次安装（放弃的成本远低于把几百 MB 写进任意路径）。
        logger.warning("download_guard: the install lock path is a symbolic link, refusing to take the lock")
        return False
    age = _lock_age_seconds(lock_path)
    if age is None or age < _LOCK_STALE_SECONDS:
        logger.warning("download_guard: another ffmpeg installer already holds the directory lock")
        return False
    try:
        lock_path.unlink()
    except OSError as e:
        logger.debug("download_guard: stale lock unlink failed: " + type(e).__name__)
        return False
    # unlink 成功后再竞争一次：另一进程可能同时做了同样的事，O_EXCL 保证只有一方胜出。
    return _acquire_lock(lock_path)


# 锁文件相对当前时刻的年龄（秒）；取不到 mtime 返回 None，由调用方按「拿不到锁」处理。
# fail-closed 方向是刻意的：一个「无法判龄」的锁不能被当成陈旧锁回收，否则并发保护可以被
# 「碰一下 mtime 再制造 stat 失败」无限次绕开。
def _lock_age_seconds(path: Path) -> float | None:
    try:
        modified = path.stat().st_mtime
    except OSError:
        return None
    return max(0.0, time.time() - modified)


def _release_lock(lock_path: Path) -> None:
    try:
        lock_path.unlink()
    except FileNotFoundError:
        # 已被别的进程按「陈旧」回收（并可能重建）——本进程的临界区早已结束，无事可做。
        return
    except OSError as e:
        # 删不掉锁只让后续安装多等一个回收窗口，不得把已经成功的安装改判成失败。
        logger.warning("download_guard: failed to remove the install lock file; it will expire by age")
        logger.debug("download_guard: lock unlink failed: " + type(e).__name__)


# 把「本次运行真正落成的目录」前置进 PATH，并对已存在的同一前缀去重（M-47）。
# 两条口径各自对应一个真实故障：
#   ① 必须用**本次**的目标目录，不能用模块级常量——dest_dir != execute_dir 时（测试宿主、便携包换位）
#      注入的是一个没被写过的目录，紧随其后的 `ffmpeg -version` 复核必然失败，安装「成功」被判成失败；
#   ② 必须以**实时** os.environ["PATH"] 为基础并去重，不能用导入时的快照——快照会把 main.py 侧 W6 已经
#      做过的注入整体丢掉；而「不做去重的实时拼接」是另一侧的故障：同一前缀被反复叠在 PATH 前面，
#      每跑一次自动安装 PATH 就再长一截（main.py 侧同样有「已在 PATH 里就不重复插入」的守卫，同源）。
def prepend_to_path_env(target_dir: str | Path) -> None:
    target = str(target_dir)
    wanted = os.path.normcase(os.path.normpath(target))
    parts = [part for part in (os.environ.get("PATH") or "").split(os.pathsep) if part]
    kept = [part for part in parts if os.path.normcase(os.path.normpath(part)) != wanted]
    os.environ["PATH"] = os.pathsep.join([target, *kept])


# 解包前的可用空间预检（M-48）。返回 False = 明确知道装不下，调用方必须**在解包之前**放弃本次安装；
# 探测本身失败时返回 True 并留一条 debug——预检是为「小 tmpfs / 快满磁盘上提前失败」而加的，
# 让它反过来把探测不到的正常机器一律挡在门外，等于用一个新增防线制造新的不可用。
def has_room_for_unpack(dir_path: str | Path, archive_bytes: int) -> bool:
    required = int(archive_bytes * UNPACK_SPACE_FACTOR)
    try:
        free = shutil.disk_usage(str(dir_path)).free
    except OSError as e:
        logger.debug("download_guard: free space probe failed, precheck skipped: " + type(e).__name__)
        return True
    if free >= required:
        return True
    logger.warning("download_guard: not enough free space beside the install target to unpack the archive")
    logger.debug("download_guard: required=" + str(required) + " free=" + str(free))
    return False


# 把**已完整落成**的暂存目录换成目标目录，中途失败则把旧目录放回原位（M-45）。
# 与旧实现 `rmtree(target) → copytree(bin, target)` 的差别正是这道防线的落点：
#   旧顺序把「删掉上一次可用安装」排在「这一次能不能装成」之前，拷贝被磁盘满 / 杀软占用打断后
#   execute_dir/ffmpeg 只剩空壳，程序彻底失去录制能力，且下次启动会重复同一条破坏路径。
#   新顺序里的破坏性动作只有两次改名：让位失败（目录被占用）→ 旧安装原地未动；落位失败 → 立刻回填。
# 失败一律抛 OSError 由调用方归一成 False；本函数**不吞**异常，吞掉就等于把「没装上」写成「装好了」。
def swap_directories(staged_dir: str | Path, target_dir: str | Path) -> None:
    staged = Path(staged_dir)
    target = Path(target_dir)
    if not target.exists():
        os.rename(str(staged), str(target))
        return
    backup = _reserve_backup_name(target)
    # 让位这一步是整条链里唯一可能「因为 ffmpeg.exe 正被别的进程使用」而失败的动作。
    # 失败即抛：此刻旧安装仍在原位、暂存目录仍在同级，调用方按失败处理不会留下空壳。
    os.rename(str(target), str(backup))
    try:
        os.rename(str(staged), str(target))
    except OSError:
        try:
            os.rename(str(backup), str(target))
            logger.warning("download_guard: swap rolled back, the previous ffmpeg directory is still in place")
        except OSError as rollback_error:
            # 回滚也失败 = 旧安装躺在 <target>.previous-* 里、目标位是空的。必须点名到日志：
            # 那是用户唯一的自救线索（手工改名即可恢复），静默等于把可恢复的故障说成「请重装」。
            logger.error("download_guard: ROLLBACK FAILED, the previous install is kept under a .previous- name")
            logger.debug("download_guard: rollback error: " + type(rollback_error).__name__)
        raise
    # 成功路径上把旧目录删掉。删不掉**只告警**：新安装此刻已就位，为了清理陈迹把成功改判成失败，
    # 会让下一次启动重跑整条下载链，代价远大于多留一个目录。
    try:
        shutil.rmtree(str(backup))
    except OSError as e:
        logger.warning("download_guard: replaced the ffmpeg directory but could not delete the previous copy")
        logger.debug("download_guard: backup removal failed: " + type(e).__name__)


# 给旧目录挑一个「同级、以目标目录名为前缀、且不冲突」的暂存名。刻意保留 <target>.previous- 前缀：
# 它既是崩溃后人工识别的线索，也不会被 glob("ffmpeg*") 之类的既有断言误当成安装结果。
def _reserve_backup_name(target: Path) -> Path:
    parent = target.parent
    for _attempt in range(_MAX_NAME_ATTEMPTS):
        candidate = parent / (target.name + ".previous-" + secrets.token_hex(_TOKEN_BYTES))
        if not candidate.exists():
            return candidate
    raise FileExistsError("download_guard: could not reserve a rollback slot beside the install target")


# <<< END INLINE INSTALL-GUARD BLOCK


def _linux_arch() -> str:
    # 保守判据与 ffmpeg_master_download._windows_arch() 同构：只认 arm64/aarch64 为 ARM，
    # 其余（x86_64/AMD64/空串/未知）一律 linux64——架构信息不可信时宁可装能跑的那份。
    return "linuxarm64" if platform.machine().lower() in ("arm64", "aarch64") else "linux64"


def _asset_url(arch: str) -> str:
    # 未知 arch 必须抛 KeyError 而不是回落：回落等于「静默拿错架构的产物」，
    # 而调用方给的 arch 只可能来自 _linux_arch() 或测试，出现陌生值只可能是改错。
    return _LINUX_FFMPEG_URLS[arch]


def _api_release_url(asset_url: str) -> str:
    match = _ASSET_URL_PATTERN.match(asset_url)
    if match is None:
        return ""
    return f"https://api.github.com/repos/{match.group('repo')}/releases/tags/{match.group('tag')}"


def _asset_name(asset_url: str) -> str:
    match = _ASSET_URL_PATTERN.match(asset_url)
    return match.group("asset") if match else ""


def _mask(url: str) -> str:
    return utils.mask_credentials(url)


def _digest_from_assets(assets: list[Any], want_name: str) -> str:
    # 从 release 的 assets 列表里取本资产的 digest；形状非法（截断/大写/未剥净前缀）与「没有该项」
    # 同级回 ""。want_name 必须是实参，不得在函数里回头调 _asset_name(_asset_url(_linux_arch()))：
    # 那会让这个纯判定函数依赖宿主架构，而同文件的分流用例正靠 monkeypatch machine 跑——结果随机器漂。
    # 绝不 .lower()：形状关与 build_exe._is_pinned 逐字同判据（64 位**小写**十六进制），先 lower 再比对
    # 等于放行「大写形态」——GitHub 的 asset.digest 恒为小写 `sha256:<64hex>`，出现大写只可能是响应被
    # 改写过或解析错位，正是这道关要拦的对象。
    for asset in assets:
        if not isinstance(asset, dict) or str(asset.get("name") or "") != want_name:
            continue
        digest = str(asset.get("digest") or "").strip()
        if digest.startswith("sha256:"):
            digest = digest.partition(":")[2]
        return digest if _SHA256_PATTERN.fullmatch(digest) else ""
    return ""


def _payload_assets(payload: Any) -> list[Any]:
    # 载荷形态由远端决定，本模块一行都不可以相信：GitHub API 正常回 dict，但前置网关/错误页/被改写的
    # 应答常见地回数组、null 或字符串，直接 payload.get("assets") 即抛 AttributeError。归一成 [] 而不是
    # 抛，是「取不到官方哈希」这条降级语义的地基——判定必须是**返回值**（空列表 = 取不到），不得改写成
    # 「靠调用点的 try 兜住异常」：那样异常形态会被入口的 catch-all 归成「直下安装异常」，用户既看不到
    # FFMPEG_MASTER_ALLOWED 指引、也拿不到本该发生的降级安装。
    # 回归锁：tests/test_ffmpeg_linux_download.py::TestDigestPayloadShape::test_non_dict_payload_yields_no_assets。
    if isinstance(payload, dict):
        assets = payload.get("assets")
        if isinstance(assets, list):
            return assets
    # {"assets": null} 与「键缺失」同级：dict.get 的默认值只在键缺失时生效，故下游 `or []` 不能替代
    # 这里判类型。形态判定已由 isinstance 做完，再挂 cast 等于向 mypy 声明「一定是 dict」的假前提。
    return []


def _fetch_asset_digest(asset_url: str) -> str:
    # 恒不抛：任何异常/非 200/形态非法一律回 ""，由调用方按「取不到官方哈希」分支处理。
    api_url = _api_release_url(asset_url)
    if not api_url:
        return ""
    try:
        response = requests.get(
            api_url,
            headers={"Accept": "application/vnd.github+json"},
            timeout=(_CONNECT_TIMEOUT, _READ_TIMEOUT),
        )
        if response.status_code != 200:
            # 403（限流）与 404 都在此归一成「取不到」——本模块的降级路径就是为此而设计，把它当错误
            # 中断安装只会让用户在 GitHub API 限流时完全装不上 ffmpeg。非 200 一律不采信载荷：201/500
            # 的响应体里同样可能带 assets 数组，闸门摘掉就等于拿错误页的 digest 当官方期望值。
            # 回归锁：tests/test_ffmpeg_linux_download.py::TestApiStatusGate::test_non_200_status_never_trusts_payload。
            logger.debug(
                i18n.tr(
                    "未取得 ffmpeg 官方 SHA256（API 返回 {status}）: {masked_url}",
                    status=response.status_code,
                    masked_url=_mask(api_url),
                )
            )
            return ""
        # 取 assets 这步必须留在 try 内，且形态归一交给 _payload_assets：原实现把 payload.get("assets")
        # 放在 try **之外**，于是「API 以 200 回数组载荷」这条真实可发生的畸形形态会抛 AttributeError
        # 穿出本函数，被入口 catch-all 归成「直下安装异常」，而「任何异常一律回 ""（= 走降级）」被偷换成 fatal。
        return _digest_from_assets(_payload_assets(response.json()), _asset_name(asset_url))
    except Exception as e:
        logger.debug(
            i18n.tr(
                "未取得 ffmpeg 官方 SHA256（请求异常）: {masked_url} - {type_name}: {err}",
                masked_url=_mask(api_url),
                type_name=type(e).__name__,
                err=e,
            )
        )
        return ""


def _baseline_path(dest_dir: Path, asset: str) -> Path:
    # 资产名进文件名：换标签即换基准，不会出现「新标签的产物被旧标签的基准判成篡改」。
    stem = asset.rsplit("/", 1)[-1].replace(".tar.xz", "")
    return dest_dir / f"{_HASH_PREFIX}.{stem}{_HASH_SUFFIX}"


def _prune_stale_baselines(dest_dir: Path, keep: Path) -> list[str]:
    removed: list[str] = []
    for stale in sorted(dest_dir.glob(f"{_HASH_PREFIX}*{_HASH_SUFFIX}")):
        if stale.name == keep.name:
            continue
        try:
            stale.unlink()
            removed.append(stale.name)
        except OSError as e:
            logger.warning(
                i18n.tr(
                    "修剪 Linux ffmpeg 陈旧 SHA256 基准失败（不影响本次安装）: {file} - {type_name}: {err}",
                    file=stale.name,
                    type_name=type(e).__name__,
                    err=e,
                )
            )
    return removed


def _verify_archive(archive: Path, official: str, dest_dir: Path, source_url: str, master_allowed: bool) -> bool:
    # 判序（形态 → 哈希 → 解压）与 ffmpeg_install.download_ffmpeg_official 同口径：三者校验的都是
    # 同一个产物文件，颠倒会让挑战页/错误页的哈希被当成基准写下去。这条形态关是「基准不被污染」的
    # 唯一前置：200 + HTML 错误页照样能算出哈希，若先算哈希再判形态，TOFU 档就会把错误页的哈希记成
    # 可信基准。回归锁：tests/test_ffmpeg_linux_download.py
    # ::TestArchiveShapeGate::test_non_tar_archive_refuses_before_hashing。
    if not tarfile.is_tarfile(str(archive)):
        logger.error(
            i18n.tr(
                "Linux ffmpeg 下载产物不是有效的 tar.xz 压缩包，拒绝校验与安装: {masked_url}",
                masked_url=_mask(source_url),
            )
        )
        return False
    current = utils.sha256_of_file(archive)
    if official:
        if current != official:
            logger.error(
                i18n.tr(
                    "Linux ffmpeg 的 SHA256 与官方公布值不符（{expected} vs {actual}），"
                    "产物可能已被替换，已删除: {masked_url}",
                    expected=official,
                    actual=current,
                    masked_url=_mask(source_url),
                )
            )
            return False
        logger.debug(i18n.tr("Linux ffmpeg 已通过官方公布 SHA256 校验: {masked_url}", masked_url=_mask(source_url)))
        return True
    hash_file = _baseline_path(dest_dir, source_url)
    if not master_allowed:
        # 默认路径必须已校验：拿不到官方哈希就拒装，且**不留下**任何基准（留了就等于偷偷启用 TOFU）。
        logger.error(
            i18n.tr(
                "未取得 ffmpeg 官方公布的 SHA256，本次不安装未校验的二进制"
                "（如接受首次信任降级，请显式设 {env}=1）: {masked_url}",
                env="FFMPEG_MASTER_ALLOWED",
                masked_url=_mask(source_url),
            )
        )
        return False
    # 「基准已存在 → 比对不符即拒」是上游换构建 / CDN 被替换时的**唯一**一道防线（第二次及以后的
    # 运行才走到这里），整段不可省。回归锁：tests/test_ffmpeg_linux_download.py::TestTofuBaselineCompare
    # ::test_second_run_with_different_bytes_refuses（首跑记账、换字节重跑必须拒且基准不被改写）。
    if hash_file.exists():
        try:
            # [这里保留 .lower()、与 _digest_from_assets 的严格形状关刻意不同强度] 基准是本模块自己
            # write_text(current) 写下的**自产物**（恒为小写十六进制），lower 只为容忍用户手工改过
            # 大小写后仍能对上；_digest_from_assets 管的是**外来的** API 应答，大写在那里只可能是
            # 响应被改写/解析错位，必须拒绝。两侧强度差不是口径分叉。
            expected = hash_file.read_text(encoding="ascii").strip().lower()
        # 必须并捕 UnicodeDecodeError：基准文件是**磁盘上可被外部改写的输入**（用户手工编辑、同步盘/
        # 压缩工具把它转成 UTF-8、或上一版实现写入非 ASCII 字节），read_text(encoding="ascii") 抛的是
        # UnicodeDecodeError（ValueError 子类，**不是** OSError），只捕 OSError 接不住。接不住的代价不是
        # 「装不上」而是「说不清为什么装不上」：异常穿出 _verify_archive、被入口 catch-all 归成一句泛化的
        # 「直下安装异常」，而本分支唯一那条带「请人工核对或删除 {file} 后重试」指引的 error 日志永不打印。
        # 拒装方向不变，只是让它按 SEV-2222 的口径**带着指引**失败。需要 as 绑定取 type(e)/err，故按
        # AGENTS 的 except 约定回退加括号形态。回归锁：tests/test_ffmpeg_linux_download.py
        # ::TestTofuBaselineCompare::test_non_ascii_baseline_refuses_without_raising。
        except (OSError, UnicodeDecodeError) as e:
            # SEV-2222 同口径：基准存在却读不出 = 本机唯一一道检查处于不可信状态，必须拒装。
            logger.error(
                i18n.tr(
                    "Linux ffmpeg 的 SHA256 基准存在但读取失败，拒绝安装（请人工核对或删除 {file} 后重试）: "
                    "{type_name}: {err}",
                    file=str(hash_file),
                    type_name=type(e).__name__,
                    err=e,
                )
            )
            return False
        if expected != current:
            logger.error(
                i18n.tr(
                    "Linux ffmpeg 的 TOFU 基准与本次产物不符（{expected} vs {actual}），已拒绝: {file}",
                    expected=expected,
                    actual=current,
                    file=str(hash_file),
                )
            )
            return False
        return True
    try:
        hash_file.write_text(current, encoding="ascii")
        removed = _prune_stale_baselines(dest_dir, hash_file)
        # 首次记账必须 warning（与 Windows master 侧同一档）：这是「本次没有可比对期望值」的唯一书面证据。
        logger.warning(
            i18n.tr(
                "未取得官方 SHA256，本次为 Linux ffmpeg 首次记录基准（TOFU，等同未校验安装）: "
                "{file} = {actual}{stale}",
                file=str(hash_file),
                actual=current,
                stale=("（已修剪陈旧基准 " + ", ".join(removed) + "）") if removed else "",
            )
        )
    except OSError as e:
        logger.warning(
            i18n.tr(
                "写入 Linux ffmpeg SHA256 基准失败（不影响本次安装）: {type_name}: {err}",
                type_name=type(e).__name__,
                err=e,
            )
        )
    return True


def _download(archive_url: str, archive: Path) -> bool:
    # 只有连接级/读取级异常才重试；4xx/5xx 直接失败（重试不会把 404 变成 200，只会白等退避）。
    # 下面两个 except 的**顺序**也是判据（HTTPError 是 RequestException 的子类，写在它后面就永远
    # 进不了「不重试」这一支）。回归锁：tests/test_ffmpeg_linux_download.py::TestDownloadRetryPolicy
    # ::test_connection_error_retries_to_max_then_fails / ::test_http_error_is_not_retried
    # ::test_write_oserror_does_not_escape_download（三条都直调 _download，异常一律不得穿出）。
    # 2026-10-21 评审 M-44 / M-49 的三处收紧，判序逐条对上上面的既有约束：
    #   ① 写入走内联块 open_exclusive（O_CREAT|O_EXCL|O_NOFOLLOW），创建点仍排在
    #     `raise_for_status()` **之后**——4xx/5xx 那一支根本不产生文件，那条既有断言逐字不变；
    #   ② 「删半截归档」只对本次真正创建过文件的尝试生效：路径可能被另一个实例或本地攻击者占着，
    #     无差别 unlink 等于把 M-44 要关掉的那扇门留在原地；
    #   ③ 累计字节超上限即判失败并放弃（重试治不了「一直有字节」的流，上限才治得了）。
    last_err: Exception | None = None
    for attempt in range(1, _MAX_RETRIES + 1):
        created = False
        completed = False
        try:
            with requests.get(archive_url, stream=True, timeout=(_CONNECT_TIMEOUT, _READ_TIMEOUT)) as response:
                response.raise_for_status()
                with open_exclusive(archive) as sink:
                    created = True
                    written = 0
                    for chunk in response.iter_content(chunk_size=1024 * 64):
                        if chunk:
                            written += len(chunk)
                            if written > _MAX_ARCHIVE_BYTES:
                                logger.error("Linux ffmpeg download exceeded the accepted size limit")
                                return False
                            sink.write(chunk)
                    completed = True
            return True
        except requests.HTTPError as e:
            logger.error(
                i18n.tr(
                    "Linux ffmpeg 下载返回 HTTP 错误: {type_name}: {err} - {masked_url}",
                    type_name=type(e).__name__,
                    err=e,
                    masked_url=_mask(archive_url),
                )
            )
            return False
        except (requests.RequestException, OSError) as e:
            # OSError 一并在此并捕（M-44）：独占创建本身就会抛 FileExistsError / PermissionError
            # （路径被占、目录只读），而「换一个名字重写」不是可接受的处置——归一成重试耗尽后的
            # False，才是与「绝不覆盖」一致的出口。
            last_err = e
            logger.warning(
                i18n.tr(
                    "Linux ffmpeg 下载异常（第 {attempt}/{max} 次）: {type_name}: {err}",
                    attempt=attempt,
                    max=_MAX_RETRIES,
                    type_name=type(e).__name__,
                    err=e,
                )
            )
            if attempt < _MAX_RETRIES:
                time.sleep(_RETRY_BACKOFF**attempt)
        finally:
            # 异常穿出与提前 return 两条路径都要收尾：`with open_exclusive(...)` 只关句柄、不删文件，
            # 而半截归档留在原地就是「看着像已下载完成」的假证据（既有断言同样依赖它被删净）。
            if created and not completed:
                try:
                    archive.unlink()
                except OSError:
                    pass
    logger.error(
        i18n.tr(
            "Linux ffmpeg 下载重试 {max} 次后仍失败: {type_name}: {err} - {masked_url}",
            max=_MAX_RETRIES,
            type_name=type(last_err).__name__ if last_err is not None else "RequestException",
            err=last_err,
            masked_url=_mask(archive_url),
        )
    )
    return False


def _install_binaries(archive: Path, ffmpeg_dir: Path) -> list[str]:
    # 递归按名取件（与 build_exe._extract_linux_ffmpeg_binaries 同一判据）：BtbN 顶层目录名带构建号，
    # 写死 <顶层>/bin/ 会让「解包成功但一件没拷」重新变成一行 warning。分「先全量定位 / 后统一落位」
    # 两趟：入口把 missing 非空判成整次安装作废，若边找边拷，则 ffmpeg 已落进 dest/ffmpeg/ 而 ffprobe
    # 缺席——半截目录会留到下一次运行，且该空壳本身也是「装过了」的假证据（mkdir 同样挪到定位成功之后）。
    # 回归锁：tests/test_ffmpeg_linux_download.py::TestBinaryLayoutDiscovery
    # ::test_missing_companion_leaves_no_half_install。
    missing: list[str] = []
    located: dict[str, Path] = {}
    with tempfile.TemporaryDirectory(dir=ffmpeg_dir.parent) as tmp:
        with tarfile.open(archive, "r:xz") as tf:
            # MI-26 同源：显式传 filter，不依赖解释器默认值（防低版本回归出路径穿越）。
            tf.extractall(tmp, filter="data")
        root = Path(tmp)
        for binary in ("ffmpeg", "ffprobe"):
            found = next((p for p in root.rglob(binary) if p.is_file()), None)
            if found is None:
                missing.append(binary)
                continue
            located[binary] = found
        if missing:
            return missing
        # 落位必须仍在 with 块内：临时目录一出作用域就被删，先拷进 dest 才有意义。
        ffmpeg_dir.mkdir(parents=True, exist_ok=True)
        for binary in ("ffmpeg", "ffprobe"):
            target = ffmpeg_dir / binary
            shutil.copy2(located[binary], target)
            # Python 的 tar 解包按成员 mode 落位，但归档外属性在部分构建里是 0o644；
            # 执行位必须显式补回，否则安装「成功」了却一跑就 PermissionError。
            # 注：该位是否可观测取决于宿主文件系统（Windows 的 chmod 只表达只读位），
            # 断言在测试侧按此收敛到 POSIX，见 tests/test_ffmpeg_linux_download.py 的 exec 位用例。
            target.chmod(target.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return missing


def install_ffmpeg_linux_native(dest_dir: str, arch: str | None = None, *, master_allowed: bool = False) -> bool:
    # 契约与 install_ffmpeg_windows 一致：失败一律 False，绝不抛出穿出 install_ffmpeg_linux()。
    # master_allowed 由**调用方传入**（ffmpeg_install 那侧的 _master_source_allowed()）：本模块反向
    # import 那个判据函数即构成循环依赖，故**不得**在此自行读 FFMPEG_MASTER_ALLOWED。
    resolved = arch or _linux_arch()
    url = _asset_url(resolved)
    dest = Path(dest_dir)
    ffmpeg_dir = dest / "ffmpeg"
    # M-44：`ffmpeg_linux_native_temp.tar.xz` 是固定可预测名——两实例并发时互相覆盖并在各自的收尾段里
    # unlink 对方的包，能写本目录的本地主体还能预置同名符号链接把几百 MB 引到任意路径。现取
    # 「可识别前缀 + 随机后缀」，创建由 _download 内部的 open_exclusive 完成（存在即失败，不跟随不覆盖）。
    archive = unique_path(dest, _TEMP_ARCHIVE_PREFIX, _TEMP_ARCHIVE_SUFFIX)
    logger.debug(
        i18n.tr(
            "Linux 包管理器未提供 ffmpeg，改试官方月末构建直下: {arch} - {masked_url}",
            arch=resolved,
            masked_url=_mask(url),
        )
    )
    # 目录锁（M-44 的另一半）：随机名只保证「互不覆盖」，不保证「互不并发落位」；两个安装器同时向
    # dest/ffmpeg 写还是会互相踩。竞争按**失败**处置（False），与本函数开头的契约同口径。
    with install_lock(dest_dir) as lock_held:
        if not lock_held:
            logger.warning("Another ffmpeg installer holds this directory; skipping the native download")
            return False
        # 本轮是否真的拿到了**由自己创建**的归档（M-44 的收尾前提，见下面 finally 的说明）。
        archive_ours = False
        try:
            official = _fetch_asset_digest(url)
            if not _download(url, archive):
                return False
            archive_ours = True
            if not _verify_archive(archive, official, dest, url, master_allowed):
                return False
            # M-48：解包前先看同级还剩多少空间。_install_binaries 刻意把临时目录落在**应用目录内**
            #   （不是 %TEMP%），这个选择把 ENOSPC 的风险从 tmpfs 挪到了目标卷，因此预检必须配套补上，
            #   否则「解包解到一半抛异常」会以新的形态回来。判据与两条 Windows 链同一个函数。
            if not has_room_for_unpack(dest_dir, archive.stat().st_size):
                logger.warning("Insufficient free space beside the install target; ffmpeg unpacking aborted")
                return False
            missing = _install_binaries(archive, ffmpeg_dir)
            if missing:
                logger.error(
                    i18n.tr(
                        "Linux ffmpeg 归档里找不到 {missing}，本次安装终止: {masked_url}",
                        missing="、".join(missing),
                        masked_url=_mask(url),
                    )
                )
                return False
        except Exception as e:
            logger.error(
                i18n.tr(
                    "Linux ffmpeg 直下安装异常（已归一为失败，不向上抛）: {type_name}: {err}",
                    type_name=type(e).__name__,
                    err=e,
                )
            )
            return False
        finally:
            # M-44 的收尾前提：**只删本轮自己创建过的归档**。_download 返 False 时归档要么从没建成
            # （连接级失败，_download 内部已按 created 收好尾），要么被别的主体占着——后者无差别
            # unlink 正是登记的那条「两实例互删对方的包」。archive_ours 只在 _download 返 True 后置真，
            # 于是这条清理恰好覆盖「我们拿到了产物、之后任何一步失败」的全部出口。
            if archive_ours and archive.exists():
                try:
                    archive.unlink()
                except OSError:
                    pass

        # M-47：注入走内联块 prepend_to_path_env。此前是「运行时目标目录 + 实时 PATH 直接
        #   拼接、无去重」，同一路径会被反复叠在 PATH 前面；「本次真正落成的目录 + 去重后的原 PATH」
        #   这一条口径现在三处（本模块、ffmpeg_install、ffmpeg_master_download）由同一个函数承担。
        prepend_to_path_env(ffmpeg_dir)
        try:
            probe = subprocess.run(["ffmpeg", "-version"], capture_output=True, timeout=30)
        except Exception as e:
            logger.error(
                i18n.tr(
                    "Linux ffmpeg 安装后验证失败: {type_name}: {err} - {dest}",
                    type_name=type(e).__name__,
                    err=e,
                    dest=str(ffmpeg_dir),
                )
            )
            return False
        if probe.returncode != 0:
            logger.error(
                i18n.tr(
                    "Linux ffmpeg 安装后 -version 返回非零（rc={rc}），判为安装失败: {dest}",
                    rc=probe.returncode,
                    dest=str(ffmpeg_dir),
                )
            )
            return False
        logger.debug(i18n.tr("Linux ffmpeg ({arch}) 已安装并验证: {dest}", arch=resolved, dest=str(ffmpeg_dir)))
        return True
