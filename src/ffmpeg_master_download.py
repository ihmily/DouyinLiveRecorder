#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# FFmpeg master 滚动构建的 Windows 下载器（x86_64 / ARM64）
#
# 背景：目标源是「枫源镜像」(fyhub.cn) 对 BtbN 的 GitHub「FFmpeg-Builds」仓库 master 分支
# 滚动构建（latest 别名）的国内镜像：
#   https://fyhub.cn/FFmpeg/latest/ffmpeg-master-latest-win64-gpl.zip
#   https://fyhub.cn/FFmpeg/latest/ffmpeg-master-latest-winarm64-gpl.zip
# 命名拆解：
#   - win64       = Windows x86_64（Intel/AMD 64 位，绝大多数 PC）
#   - winarm64    = Windows ARM64（Surface / 骁龙 X 等 Windows on ARM 设备）
#   - gpl         = 含 GPL 编解码器的构建（x264/x265/libvpx 等）；另有 lgpl 变体不含
#   - master-latest = 取自 ffmpeg git master 的每日滚动构建（比 gyan.dev 的 release 构建更新但
#     更不稳定；且是滚动别名，上游每次出新构建内容即变，故不能把哈希常量钉死）
#
# 关键约束（实测，2026-09-22）：fyhub.cn 对这两个直链返回「下载验证」HTML 页（200 + text/html，
#   引用 vdf-worker.js 的 PoW 人机验证），普通脚本拿不到文件，其 .sha256 文档也返回 404。真正可
#   直接下载的同源上游是 BtbN GitHub release 直链（字节一致、无门控），但同样不发布 latest 别名的
#   .sha256。故本模块的正确下载方式（细则与 ID 见各函数注释）：
#   ① 按宿主架构选 win64 / winarm64；
#   ② 候选 [BtbN-GitHub, fyhub]，**顺序即优先级**：权威上游必排在镜像之前（镜像哪天直出文件也不得
#      取代上游），fyhub 用 Range 探针识别「挑战页」并跳过、落到无门控的 BtbN 上游；
#   ③ 下载后强制「是不是真的 zip」形态校验，拒把验证页/错误页当产物；
#   ④ 滚动构建无权威哈希文档，完整性只能 TOFU（首次信任），与 ffmpeg_install 降级分支同强度、不冒充
#      「已校验」；基准存在却读不出即**拒装**（SEV-2222）——这是本模块唯一一道完整性检查，不容静默失效；
#   ⑤ TOFU 基准按构建标识分文件，写新删旧只留 1 份。
#
# **默认关闭**（SEV-2218，2026-09-23 定稿）：ffmpeg_install 只在环境变量 FFMPEG_MASTER_ALLOWED 显式
#   取真时才调用 download_ffmpeg_master()，默认跳过并各落一条 warning（开启 = 声明本次用的是未校验
#   TOFU 源；跳过 = 声明因未开启而未做兜底）。理由：AGENTS.md「三类钉定/校验」② 的红线是「新增任何
#   第二条 Windows 运行期下载源前必须先满足『官方公布哈希』判据」，而本模块按 ④ 只有 TOFU 强度。
#
# 与 ffmpeg_install.py 的关系：不改动其既有完整性模型（gyan.dev 官方源 + 官方 SHA256 优先），
#   仅作为「Windows ARM64 无官方源」或「gyan.dev 不可达」时**需显式开启**的补充路径。

import contextlib
import hashlib
import os
import platform
import secrets
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import BinaryIO, cast

import requests
from loguru import logger
from tqdm import tqdm

import i18n
from src import utils

# 与 ffmpeg_install 一致的依赖：zip 形态校验、哈希、解压炸弹防护走同一份实现。
from src.utils import is_valid_zip, sha256_of_file, unzip_file

# 下载连接超时（建立连接）/ 读取超时（两个 chunk 之间）分离，避免慢速 CDN 永久挂起。
_CONNECT_TIMEOUT = 15
_READ_TIMEOUT = 30
# 探测挑战页只需 1 字节，给短超时：探针只判可达性、不取内容，5 秒已远超正常往返（实测毫秒级）。
# [历史注] 原值 20 与本注释相互矛盾——fyhub 被探成挑战页/超时是**常态**，两候选串行即「无 ffmpeg
# 的机器首次启动」要多等 40 秒，故 2026-09-23 降到 5（MIN-2267）。
_PROBE_TIMEOUT = 5
# 连接级失败（DNS/连接重置/读取中断）的重试次数与退避。
_MAX_RETRIES = 3
_RETRY_BACKOFF = 2.0  # 每次退避翻倍：2s, 4s, 8s

# 临时 zip 的**前缀**（随机后缀由内联块 unique_path 追加，M-44）：保留
# ffmpeg_master_<arch>_temp 这段可识别前缀，既有断言与日志仍靠它定位本次下载的产物。
_TEMP_ZIP_PREFIX = "ffmpeg_master_{arch}_temp"
_TEMP_ZIP_SUFFIX = ".zip"
# 解包暂存目录前缀（M-48：与目标目录同级）与落位暂存目录前缀（M-45：同级暂存后改名替换）。
_UNPACK_PREFIX = "ffmpeg_unpack_"
_STAGED_PREFIX = "ffmpeg_staged_"
# 单次下载的字节上限（M-49：本模块此前有重试、无量）。BtbN win64-gpl 当前约 190MB，取 512MiB
# 给上游构建增长留余量，同时关掉「CDN 持续吐字节、iter_content 永不结束」这一族无上限故障。
# 与 ffmpeg_install._MAX_DOWNLOAD_BYTES、ffmpeg_linux_download._MAX_ARCHIVE_BYTES 同值但各存一份：
# 三条链的产物形态不同，互 import 会在两个安装器之间新增一条耦合边（同 AGENTS「响应体上限
# 8MB/32MB 各存一份」的口径）。
_MAX_DOWNLOAD_BYTES = 512 * 1024 * 1024


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


class FfmpegDownloadError(Exception):
    # 下载链路统一异常基类；顶层安装入口只捕获它并转成 False + 日志，不向上抛。
    pass


class IntegrityError(FfmpegDownloadError):
    # 产物不是合法 zip，或 TOFU 哈希与已缓存基准不符（含基准存在但读不出）——拒绝写盘/安装。
    pass


class NetworkError(FfmpegDownloadError):
    # 重试耗尽后仍连不上 / 读取中断 / HTTP 错误。
    pass


# 宿主 Windows 架构 → fyhub/BtbN 的构建名后缀。判据用 platform.machine() 字面量：arm64/aarch64
# 才走 winarm64，其余（AMD64/x86_64/空串/未知）一律默认 x86_64——宁可装能跑的 x86_64（ARM 上经
# x64 模拟），也不要在架构信息不可信时误装 arm64 原生包导致无法启动。
def _windows_arch() -> str:
    machine = platform.machine().lower()
    if machine in ("arm64", "aarch64"):
        return "winarm64"
    return "win64"


# 同一构建名在两源下的候选直链，**列表顺序即优先级**：权威上游（BtbN GitHub）在前，镜像（fyhub）
# 在后——镜像既能替换产物也就能替换它自己的任何元数据，权威性严格弱于上游，其价值只在「上游不可达」
# 时体现，故只作兜底项（fyhub 被探成挑战页时会被自动跳过，不会误导用户以为「源可用」）。
#   [历史注] 2026-09-23 SEV-2218 子项之前，用户点名的个人镜像排在前面。
def _candidate_urls(arch: str) -> list[str]:
    base = f"ffmpeg-master-latest-{arch}-gpl.zip"
    return [
        f"https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/{base}",
        f"https://fyhub.cn/FFmpeg/latest/{base}",
    ]


# 响应是否为「人机验证页 / 错误页」而非文件：Content-Type 是 html，或正文前若干字节是
# <!doctype / <html 形态即判为挑战页。后者比只看 Content-Type 更稳——某些 CDN 对挑战页会误标
# application/octet-stream，但首字节一定是 HTML 标签。
def _looks_like_html(response: requests.Response) -> bool:
    ctype = (response.headers.get("Content-Type") or "").lower()
    if "text/html" in ctype:
        return True
    try:
        first = next(response.iter_content(512), b"")
    except Exception:
        # 读不到首字节即内容不可信，判 True（是 HTML/坏页）。
        # [历史注] 2026-09-23 MIN-2267 之前此处返回 False（=「不是 HTML，放行」），把**读失败**当成
        # 「拿到的是文件」：流一断就误报探针 ok，随后 _stream_download 才发现问题，而这一次误判会让
        # 本可换源的候选被当成唯一可用源。
        return True
    text = first.lstrip()[:64].lower()
    return text.startswith(b"<!doctype") or text.startswith(b"<html")


# Range 探针：取首字节并据状态码/Content-Type 判定该候选源是否真的给文件。返回
# ("ok" | "challenge" | "http-error", response-or-None)——换源靠这个**字符串状态**驱动。用
# bytes=0-0 而非 HEAD：HEAD 在 fyhub 上返回 405，与 ffmpeg_install 处理 douyinliving CDN 的 405
# 同源——Range GET 才是可靠的探测手段。
#   [历史注] 2026-09-23 MIN-2267 删除了原有的 ChallengePageError：改为字符串状态后它全仓零引用，
#   留着会让读者以为存在「抛挑战页异常换源」这条链路。
def _probe(url: str) -> tuple[str, requests.Response | None]:
    try:
        response = requests.get(
            url,
            headers={"Range": "bytes=0-0"},
            timeout=_PROBE_TIMEOUT,
            stream=True,
            allow_redirects=True,
        )
    except requests.RequestException as e:
        logger.debug(
            i18n.tr(
                "ffmpeg master 候选源探测连接失败（将换下一源）: {masked} - {type_name}: {e}",
                masked=utils.mask_credentials(url),
                type_name=type(e).__name__,
                e=e,
            )
        )
        return "http-error", None
    status = response.status_code
    if status not in (200, 206):
        logger.debug(
            i18n.tr(
                "ffmpeg master 候选源探测返回非 2xx: {status} {masked}",
                status=status,
                masked=utils.mask_credentials(url),
            )
        )
        response.close()
        return "http-error", None
    if _looks_like_html(response):
        response.close()
        return "challenge", None
    return "ok", response


# 由响应头推导构建标识（与 ffmpeg_install._build_identity 同口径）：无可用头时返回 ""，退化为
# 按 URL 基础名命名，避免 Windows 非法文件名。只用于 TOFU 缓存文件命名，不是信任根。
def _build_identity(headers: Mapping[str, str] | None) -> str:
    if not headers:
        return ""
    try:
        bits = [
            str(headers.get("Last-Modified") or "").strip().strip('"'),
            str(headers.get("ETag") or "").strip().strip('"'),
            str(headers.get("Content-Length") or "").strip(),
        ]
    except Exception:
        return ""
    raw = "|".join(b for b in bits if b)
    if not raw:
        return ""
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]


# 流式下载（带重试与进度）：仅在连接级/读取级异常时重试，HTTP 4xx/5xx 直接失败。内存恒定的分块
# 写法；tmp 落盘后再做形态/哈希校验，避免把半截文件当产物。
# 2026-10-21 评审 M-44 / M-49 的两处收紧，三条判序缺一不可：
#   ① 写入走内联块 open_exclusive（O_CREAT|O_EXCL|O_NOFOLLOW），且创建点排在
#     `raise_for_status()` **之后**——4xx/5xx 那一支根本不产生文件（与
#     tests/test_ffmpeg_linux_download.py::TestDownloadRetryPolicy::test_http_error_is_not_retried
#     对同名分支的判据同源），而「已存在」一律按失败处理，绝不覆盖、绝不跟随预置的符号链接；
#   ② 只有**本次真正创建了**该文件才允许 unlink：路径可能被另一个实例或本地攻击者占着，
#     无差别删除等于把 M-44 的另一半（互删对方的包）留在原地；
#   ③ 累计字节超上限即判 IntegrityError 并放弃：上限是「量」的防线，重试治不了「一直有字节」的流。
def _stream_download(url: str, zip_path: Path) -> tuple[str, int, Mapping[str, str]]:
    last_err: Exception | None = None
    for attempt in range(1, _MAX_RETRIES + 1):
        created = False
        completed = False
        try:
            with requests.get(
                url, stream=True, timeout=(_CONNECT_TIMEOUT, _READ_TIMEOUT), allow_redirects=True
            ) as response:
                response.raise_for_status()
                total = int(response.headers.get("Content-Length", 0))
                build_id = _build_identity(response.headers)
                with open_exclusive(zip_path) as sink:
                    created = True
                    with tqdm(
                        total=total, unit="B", unit_scale=True, ncols=100, desc="Downloading ffmpeg (master)"
                    ) as t:
                        written = 0
                        for chunk in response.iter_content(chunk_size=1024 * 64):
                            if not chunk:
                                continue
                            written += len(chunk)
                            if written > _MAX_DOWNLOAD_BYTES:
                                raise IntegrityError("ffmpeg master download exceeded the accepted size limit")
                            sink.write(chunk)
                            _ = t.update(len(chunk))
                    completed = True
                return build_id, total, response.headers
        except requests.HTTPError as e:
            # 4xx/5xx 不是重试能解决的（fyhub 验证页若漏判、或源真的 404）→ 直接抛。
            raise NetworkError(i18n.tr("ffmpeg master 下载 HTTP 错误: {e}", e=e)) from e
        except IntegrityError:
            # 上限判定属「拿到的东西不可信」，不是「网络抖了一下」：不得进入重试循环，直接交给
            # 顶层入口按完整性失败处置（删包 + 拒装）。排在宽捕获之前，是为了日后有人把下面那支
            # 扩成 `except Exception` 时，上限判定也不会被顺带吞进重试循环。
            raise
        except (requests.RequestException, ConnectionError, OSError) as e:
            # OSError 一并在此并捕（2026-10-21 M-44）：独占创建本身就会抛 FileExistsError /
            # PermissionError（路径被占、目录只读），而「换一个名字重写」不是可接受的处置——
            # 归一成重试耗尽后的 NetworkError，由入口转 False，才是与「绝不覆盖」一致的出口。
            last_err = e
            logger.warning(
                i18n.tr(
                    "ffmpeg master 下载连接异常（第 {attempt}/{max} 次重试）: {type_name}: {e}",
                    attempt=attempt,
                    max=_MAX_RETRIES,
                    type_name=type(e).__name__,
                    e=e,
                )
            )
            if created:
                _discard_master_zip(zip_path)
            if attempt < _MAX_RETRIES:
                time.sleep(_RETRY_BACKOFF**attempt)
        finally:
            # 异常穿出（含 IntegrityError 与 HTTPError 那两条 return/raise 路径）时，半截文件同样
            # 不能留给下一轮或下一次启动：`with open_exclusive(...)` 只负责关句柄，不负责删除。
            if created and not completed:
                _discard_master_zip(zip_path)
    raise NetworkError(
        i18n.tr(
            "ffmpeg master 下载重试 {max} 次后仍失败: {type_name}: {e}",
            max=_MAX_RETRIES,
            type_name=type(last_err).__name__,
            e=last_err,
        )
    )


# TOFU 哈希缓存（这些滚动构建无权威 .sha256 文档，只能首次信任 + 同构建重装比对）。
# 命名前缀 _ffmpeg_master 与 ffmpeg_install 的 _ffmpeg_official* 区分，互不污染基准。
_HASH_PREFIX = "_ffmpeg_master"
_HASH_SUFFIX = ".zip.sha256"


def _master_hash_file(dest_dir: Path, build_id: str, arch: str) -> Path:
    name = f"{_HASH_PREFIX}.{arch}.{build_id}{_HASH_SUFFIX}" if build_id else f"{_HASH_PREFIX}.{arch}{_HASH_SUFFIX}"
    return dest_dir / name


# 写新基准时修剪同前缀的旧基准（只保留本次这一份）：master-latest 是滚动别名，上游每发一次新构建就
# 多一个 .sha256，不修剪既让程序目录无界增长、又留下一堆不再参与校验的陈旧基准。与
# ffmpeg_install._record_zip_sha256 刻意不同：那边把陈旧基准列进告警供用户人工比对故不删；本模块是
# **默认关闭**的 TOFU 路径，两边哈希都无权威来源，陈旧基准没有可比对价值，故直接修剪。
def _prune_stale_master_baselines(dest_dir: Path, keep: Path) -> list[str]:
    removed: list[str] = []
    for stale in sorted(dest_dir.glob(f"{_HASH_PREFIX}*{_HASH_SUFFIX}")):
        if stale.name == keep.name:
            continue
        try:
            stale.unlink()
            removed.append(stale.name)
        except OSError as e:
            # 删不掉不影响本次安装（校验只看 keep 这一份），只告警，不得因此拒装。
            logger.warning(
                i18n.tr(
                    "修剪 ffmpeg master 陈旧 SHA256 基准失败（不影响本次安装）: {file} - {type_name}: {e}",
                    file=stale.name,
                    type_name=type(e).__name__,
                    e=e,
                )
            )
    return removed


def _discard_master_zip(zip_path: Path) -> None:
    if zip_path.exists():
        try:
            zip_path.unlink()
        except OSError:
            pass


# 子进程控制台窗口抑制：与 src/ffmpeg_install._win_startup_info 同一语义的孪生副本。本模块**不得**
# 改为 import 那边那个函数——ffmpeg_install 在模块级
# `from src.ffmpeg_master_download import download_ffmpeg_master`，反向引用即构成循环导入。
# 两份实现必须逐字同语义：改判据要同时改两处，等价性由
# tests/test_ffmpeg_install.py::TestChildConsoleStartupInfo::test_twin_helpers_agree_on_both_gate_states
# 在两个门控取值下逐一对齐。平台门控取 `sys.platform == "win32"` 字面量并抽成模块级常量
# （Linux CI 可 monkeypatch 强制走进 win32 分支）；函数体不引用任何 Windows 专属符号，故不需要
# `# type: ignore`。
_HIDE_CHILD_CONSOLE = sys.platform == "win32"


def _win_startup_info() -> object | None:
    # 非 Windows 恒 None：subprocess 收到 startupinfo=None 等价于不传该实参，行为逐字不变。
    if not _HIDE_CHILD_CONSOLE:
        return None
    # 委托前置条件与孪生处逐字相同，完整理由见 src/ffmpeg_install.py::_win_startup_info
    # （首次 import video_postprocess 会撞 video_postprocess → main → src.notify →
    # video_postprocess 的循环导入并半程执行 main 的模块体；拿不到就退回改动前的闪窗行为）。
    # 本模块更极端：连「模块级 import video_postprocess」都不可能是选项——那条环在导入本模块的
    # 那一刻就会闭合。
    if "src.video_postprocess" not in sys.modules and "main" not in sys.modules:
        return None
    from src.video_postprocess import get_startup_info

    return get_startup_info(os.name)


def _tofu_verify_or_record(zip_path: Path, hash_file: Path, source_url: str) -> None:
    current = sha256_of_file(zip_path)
    masked = utils.mask_credentials(source_url)
    if hash_file.exists():
        try:
            expected = hash_file.read_text(encoding="ascii").strip().lower()
        except (OSError, UnicodeDecodeError) as e:
            # SEV-2222：基准**存在**却读不出来 = 本机那份可信基准处于不可信状态，必须拒装。旧实现
            # 只 warning 后 return，调用方把 None 当成校验通过，于是「唯一一道完整性检查在磁盘异常时
            # 静默失效」（与 MID-63/MID-68/MIN-19「不得用捕获异常后跳过让它变绿」同一族禁令）；
            # 只有「基准确实不存在」才走首次记账。
            # 必须并捕 UnicodeDecodeError（M-06）：基准是**磁盘上可被外部改写的输入**，用户手工编辑、
            # 同步盘/压缩工具把它转成 UTF-8 都会让 read_text(encoding="ascii") 抛 UnicodeDecodeError
            # （ValueError 子类，**不是** OSError）。本模块接不住的代价比 Linux 姊妹侧更硬：顶层入口
            # 承诺「失败一律返回 False 不抛」，而调用方 download_ffmpeg_master 只并捕
            # (IntegrityError, OSError)，该异常会穿出 → install_ffmpeg_windows（全程无 try）→
            # check_ffmpeg 直达启动流程，把「装不上」升级成「起不来」。归一成 IntegrityError 后走的
            # 就是本分支既有的「删包 + 拒装」路径，并带上「请人工核对或删除 {hash_file} 后重试」指引。
            # [历史注] 本段曾称与 ffmpeg_install._check_or_record_zip_sha256 同形分支「刻意不同」
            # （那边前面还有官方哈希一道）——L-44（2026-10-02）复核认为该理由对降级分支不成立
            # （官方文档不可达时 TOFU 同样是最后一道），两侧已统一收紧为拒装，不再有口径分叉。
            # 两处姊妹修法（ffmpeg_linux_download._verify_archive / ffmpeg_install 同名函数）与本条
            # 同批修。需要 as 绑定取 type(e)/e，故按 AGENTS 的 except 约定回退加括号形态。回归锁：
            # tests/test_ffmpeg_install.py::TestMasterBaselineDecodeGuard
            # ::test_non_ascii_baseline_becomes_integrity_error_and_discards_zip（单元层）与
            # ::test_entrypoint_normalises_non_ascii_baseline_to_false（入口层，钉「返 False 而非抛」）。
            _discard_master_zip(zip_path)
            raise IntegrityError(
                i18n.tr(
                    "ffmpeg master 的 SHA256 基准文件存在但读取失败，拒绝安装未校验的二进制"
                    "（读取异常不代表基准不存在，请人工核对或删除 {hash_file} 后重试）: "
                    "{type_name}: {e} - {masked}",
                    hash_file=str(hash_file),
                    type_name=type(e).__name__,
                    e=e,
                    masked=masked,
                )
            ) from e
        if expected != current:
            _discard_master_zip(zip_path)
            raise IntegrityError(
                i18n.tr(
                    "ffmpeg master zip SHA256 与已缓存基准不一致（{expected} vs {actual}），"
                    "可能 CDN 被替换或上游发了新构建。删除 {hash_file} 后重试，或手动下载校验: {masked}",
                    expected=expected,
                    actual=current,
                    hash_file=str(hash_file),
                    masked=masked,
                )
            )
        logger.debug(i18n.tr("ffmpeg master zip 已通过 TOFU 基准校验: {masked}", masked=masked))
        return
    try:
        hash_file.write_text(current, encoding="ascii")
        # 首次记账必须与 ffmpeg_install 的同类降级口径一致（warning，而非 debug）：
        # 这一条是「本次安装没有任何可比对的期望值」的唯一书面证据。
        removed = _prune_stale_master_baselines(hash_file.parent, hash_file)
        logger.warning(
            i18n.tr(
                "ffmpeg master 源无权威哈希文档，本次为首次记录 SHA256（TOFU，无可比对的期望值，"
                "等同于未校验安装）: {hash_file} = {current}{stale}",
                hash_file=str(hash_file),
                current=current,
                stale=("（已修剪陈旧基准 " + ", ".join(removed) + "）") if removed else "",
            )
        )
    except OSError as e:
        logger.warning(i18n.tr("写入 ffmpeg master SHA256 缓存失败（不影响本次安装）: {e}", e=e))


# 把解包出来的 bin 目录**完整落成同级暂存目录、再两次改名换进目标位**（M-45）。
# 与 src/ffmpeg_install._install_bin_dir 同一语义（那条链的成因与取舍写在其注释里，不在此重述）：
# 本模块此前是 `if target.exists(): rmtree(target)` + `copytree(bin, target)`，删旧动作排在
# 「这一次能不能装成」之前，拷贝被磁盘满 / 杀软占用打断后就留下一个空壳 ffmpeg 目录——而 master 源
# 是唯一一条**默认关闭**的兜底路径，用户开它正是因为主路径已经装不上，再来一次破坏等于直接没救。
# 前置校验照旧：调用点必须先确认解包产物里有 bin/ffmpeg.exe，删旧永远发生在校验之后。
def _install_master_binaries(bin_dir: str, target: Path) -> bool:
    parent = str(target.parent) or "."
    staged = Path(tempfile.mkdtemp(dir=parent, prefix=_STAGED_PREFIX))
    try:
        shutil.copytree(bin_dir, str(staged), dirs_exist_ok=True)
        # 落位前再验一次「暂存副本里确实有可执行文件」：copytree 中途失败若不抛，换进去的就是空壳。
        if not (staged / "ffmpeg.exe").is_file():
            logger.error("Staged ffmpeg directory is incomplete; previous install left untouched")
            return False
        swap_directories(staged, target)
    except OSError as e:
        logger.warning("Could not put the newly installed ffmpeg in place: " + type(e).__name__)
        return False
    finally:
        shutil.rmtree(str(staged), ignore_errors=True)
    return True


# 顶层下载+安装入口：返回 True 表示成功把 bin 落到 dest_dir/ffmpeg。失败一律返回 False（不抛），
# 与 ffmpeg_install.install_ffmpeg_windows 的契约一致，由调用方决定提示用户手动安装。
# [历史注] 该承诺曾只兑现一半：_stream_download 仅捕 requests 系异常，open(zip_path, "wb") 的
# OSError（磁盘满 / 无权限 / 路径失效）会一路穿出 except FfmpegDownloadError，经
# install_ffmpeg_windows() 直达启动期 check_ffmpeg()；故下载段与完整性段都额外并捕 OSError。
def download_ffmpeg_master(dest_dir: str, arch: str | None = None) -> bool:
    arch = arch or _windows_arch()
    # M-44：`ffmpeg_master_<arch>_temp.zip` 是固定可预测名——两实例并发时互相覆盖并在各自 finally 里
    # unlink 对方的包，能写本目录的本地主体还能预置同名符号链接把几百 MB 引到任意路径。现由
    # unique_path 生成「可识别前缀 + 随机后缀」，实际写入由 open_exclusive 独占创建，存在即失败。
    zip_path = unique_path(dest_dir, _TEMP_ZIP_PREFIX.format(arch=arch), _TEMP_ZIP_SUFFIX)
    urls = _candidate_urls(arch)
    logger.debug(i18n.tr("ffmpeg master 下载：检测到架构 {arch}，候选源 {n} 个", arch=arch, n=len(urls)))

    chosen_url = None
    probe_response = None
    for url in urls:
        status, resp = _probe(url)
        if status == "ok":
            chosen_url = url
            probe_response = resp
            break
        if status == "challenge":
            logger.warning(
                i18n.tr(
                    "ffmpeg master 候选源返回人机验证页，跳过（不可脚本化下载）: {masked}",
                    masked=utils.mask_credentials(url),
                )
            )
        # http-error：直接试下一源

    if not chosen_url:
        logger.error(
            i18n.tr(
                "ffmpeg master 全部候选源不可用（均返回验证页或连接失败），请手动从 "
                "https://github.com/BtbN/FFmpeg-Builds/releases/tag/latest 下载 ffmpeg-master-latest-{arch}-gpl.zip",
                arch=arch,
            )
        )
        return False

    # 探针响应可复用作下载的首字节；为简单与一致，这里关闭探针连接、走完整下载。
    if probe_response is not None:
        try:
            probe_response.close()
        except Exception:
            pass

    # 目录锁（M-44 的另一半）：随机名只保证「互不覆盖」，不保证「互不并发落位」。探针段不写
    # dest_dir，因此锁只包住真正落盘的后半段；竞争按**失败**处置（False），与上面的契约同口径。
    with install_lock(dest_dir) as lock_held:
        if not lock_held:
            logger.warning("Another ffmpeg installer holds this directory; skipping the master download")
            return False

        try:
            build_id, _total, _headers = _stream_download(chosen_url, zip_path)
        except (FfmpegDownloadError, OSError) as e:
            # OSError 分支见上方 MIN-2266⑤：写盘失败（磁盘满 / 无权限 / 路径失效）属「拿不到产物」，
            # 与网络失败同级，一律归一成 False，不得穿出「失败不抛」的契约。
            # [2026-10-21 M-44] 这里**不再**调 _discard_master_zip：本分支的含义是「下载段自己结束了」，
            # 而 _stream_download 内部的 finally 已经删掉**它自己创建过**的半截包；在这一层再删一次，
            # 删到的就可能是「独占创建失败时占着那个路径的别人的文件」（正是 M-44 登记的互删形态）。
            # 后面的每一条失败出口都删在 `_stream_download 已成功返回` 之后，那时产物必然归本轮所有。
            logger.error(i18n.tr("ffmpeg master 下载失败: {type_name}: {e}", type_name=type(e).__name__, e=e))
            return False

        # 形态校验先于哈希：拒绝把验证页/错误页当产物（即便探针漏判了 HTML）。
        if not is_valid_zip(zip_path):
            logger.error(
                i18n.tr(
                    "ffmpeg master 下载产物不是有效 zip（可能是验证页/错误页），拒绝安装: {masked}",
                    masked=utils.mask_credentials(chosen_url),
                )
            )
            _discard_master_zip(zip_path)
            return False

        hash_file = _master_hash_file(Path(dest_dir), build_id, arch)
        try:
            _tofu_verify_or_record(zip_path, hash_file, chosen_url)
        except (IntegrityError, OSError) as e:
            # IntegrityError 分支已在内部删包；OSError 来自 sha256_of_file（产物被外部删除 /
            # 句柄失效）。两者都属「无法确认完整性」，一律拒装且不执行刚下载的二进制。
            _discard_master_zip(zip_path)
            logger.error(i18n.tr("ffmpeg master 完整性校验失败: {type_name}: {e}", type_name=type(e).__name__, e=e))
            return False

        # 解压（统一走 unzip_file 的解压炸弹防护 + Zip Slip 校验），提取含 ffmpeg.exe 的 bin 目录。
        # M-48：解包目录必须落在目标目录同级而不是 %TEMP%——master 的 gpl 包解后可达数百 MB，
        #   而容器里的 /tmp 常是小 tmpfs，默认临时目录一满就整条链 ENOSPC 死在解压这一步；
        #   Linux 侧（ffmpeg_linux_download._install_binaries）早就刻意落在应用目录内，此处对齐同一条
        #   口径，并把空间预检排在解包之前。
        target = Path(dest_dir) / "ffmpeg"
        try:
            if not has_room_for_unpack(dest_dir, zip_path.stat().st_size):
                logger.warning("Insufficient free space beside the install target; ffmpeg unpacking aborted")
                return False
            with tempfile.TemporaryDirectory(dir=dest_dir, prefix=_UNPACK_PREFIX) as tmp_dir:
                unzip_file(zip_path, tmp_dir, delete=False)
                bin_dir = None
                for root, _dirs, files in os.walk(tmp_dir):
                    if os.path.basename(root) == "bin" and "ffmpeg.exe" in files:
                        bin_dir = root
                        break
                if bin_dir is None:
                    logger.error("ffmpeg.exe not found in master package")
                    return False
                # M-45：同级暂存 + 改名替换；失败时上一次可用安装原地保留，不再留下空壳目录。
                if not _install_master_binaries(bin_dir, target):
                    return False
        except Exception as e:
            logger.error(i18n.tr("ffmpeg master 解压失败: {type_name}: {e}", type_name=type(e).__name__, e=e))
            return False
        finally:
            _discard_master_zip(zip_path)

        # 与 download_ffmpeg_official 一致：安装成功后把 bin 目录前置注入 PATH，再用 `ffmpeg -version`
        # 真跑一次验证（returncode==0 才认成功）。该前置只发生在「系统本无可用 ffmpeg」的自动安装分支，
        # 不会与 W6 的 PATH 优先级判据冲突（W6 在 main.py 侧、注入前取快照，本处注入在其之后）。
        # M-47：注入走内联块 prepend_to_path_env——此前这里是「运行时目标目录 + 实时 PATH
        #   直接拼接、无去重」，同一路径会被反复叠在 PATH 前面；去重与「本次目标目录」两条口径统一在
        #   那一个函数里，与 ffmpeg_install / ffmpeg_linux_download 两侧同形。
        prepend_to_path_env(target)
        try:
            # L-15：本行真跑刚下载的 ffmpeg.exe，Windows 无控制台形态（pythonw / 冻结 console=False）
            # 下不传 startupinfo 会闪出一个控制台窗口；判据见 _win_startup_info。
            rc = subprocess.run(
                ["ffmpeg", "-version"], capture_output=True, timeout=30, startupinfo=_win_startup_info()
            )
        except Exception as e:
            logger.error(i18n.tr("ffmpeg master 安装后验证失败: {type_name}: {e}", type_name=type(e).__name__, e=e))
            return False
        if rc.returncode == 0:
            logger.debug(
                i18n.tr(
                    "ffmpeg master ({arch}) 已从 {masked} 安装并验证: {dest}",
                    arch=arch,
                    masked=utils.mask_credentials(chosen_url),
                    dest=dest_dir,
                )
            )
            return True
        logger.error("ffmpeg master installation verification failed")
        return False


if __name__ == "__main__":
    # 仅做「选源 + 探针」自测（不下载完整 ~190MB 包），方便快速确认本机架构与可达源。
    # 注意：本自测块会真的发起出站探测，因此只在人工通道下运行，不会被 pytest 收集执行。
    a = _windows_arch()
    # 形参打印一律走 i18n.tr（MID-68 不变量①：f-string 在查目录之前完成插值，
    # 目录里带占位符的 msgid 永远匹配不上，翻译会静默退化为原文）。
    print(i18n.tr("detected arch: {a}", a=a))
    for u in _candidate_urls(a):
        status, _ = _probe(u)
        print(f"  [{status}] {u}")
