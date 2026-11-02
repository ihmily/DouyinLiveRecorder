#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import contextlib
import hashlib
import os
import platform
import re
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

# loguru 的 logger 为模块级单例，src.logger 对其做过的配置在此同样生效；
# 直接从此处导入可避免基于 basedpyright 的 "未从 src.logger 导出" 告警。
from loguru import logger
from tqdm import tqdm

import i18n

# 解压实现与 node_install 共用同一份（原先两处逐字重复，见 src/utils.unzip_file）
from src import utils

# 布尔环境开关的唯一解析入口（与全仓布尔配置同一识别集合，勿在别处再造第三套布尔判定）
from src.config_bool import parse_config_bool

# Linux 原生 ffmpeg 直下（类别② 的 Linux 分支）。master_allowed 由本模块传入而非该模块自读环境变量：
# ffmpeg_install → ffmpeg_linux_download 已有一条 import 边，反向 import _master_source_allowed() 即成环。
# 位置不能下移：isort 按模块名字典序排（ffmpeg_linux_download < ffmpeg_master_download）。
from src.ffmpeg_linux_download import install_ffmpeg_linux_native

# Windows ARM64 原生构建 / gyan.dev 不可达时的兜底下载器：BtbN master 滚动构建（上游不公布 latest
# 别名的 SHA256，只有 TOFU）。**默认不调用**——须 FFMPEG_MASTER_ALLOWED 显式取真才走该路径，判据见
# _master_source_allowed()。该模块不 import 本模块，故此处单向引入无循环依赖风险。
from src.ffmpeg_master_download import download_ffmpeg_master

# 应用根目录复用 src.logger 公开导出的 script_path（等价原私有 _app_root() 的返回值）
from src.logger import script_path

# 官方哈希小文档的「按字节限长读取」判据（M-12）：单点住在 node_install（S-12② 已抽成唯一函数），
# ffmpeg 两条文档链直接复用，避免第三份拷贝再漂移。node_install 不 import 本模块，单向引入无环。
from src.node_install import _read_small_document_capped
from src.utils import unzip_file

# FFmpeg 自动安装模块 - 跨平台 FFmpeg 自动检测与安装
#
# 职责：检测系统是否已安装 ffmpeg（check_ffmpeg_installed），未安装则按平台自动拉取并安装——
#   Windows 默认只有官方源 gyan.dev 一条自动路径（第二条源默认关闭，见「Windows 下载源现状」段），
#   macOS 走 Homebrew，Linux 走 yum/apt，再兜底官方月末构建直下。
# 安装落点：execute_dir（冻结后指向 _internal/，与运行时资源同目录），装好后把 ffmpeg 目录
#   前置注入 os.environ["PATH"]，使同进程后续 subprocess 调用 `ffmpeg` 能直接命中。
# 校验约定：所有安装路径最后都跑一次 `ffmpeg -version`，returncode==0 才认成功，否则报错并返回 False。
# 设计取舍：安装失败只返回 False、不抛异常（由调用方决定提示用户手动安装），避免中断主程序启动。
#
# 完整性模型：**权威校验优先、TOFU 只作显式降级的兜底**。
#   ① 下载前向 gyan.dev 取官方公布的 <zip URL>.sha256 文档，与本地实算哈希比对——不符即拒绝安装；
#   ② 只有「取不到官方文档」（网络失败 / 非 200 / 文档形态变更）时才退回旁路基准 TOFU，
#      并 logger.warning 将降级显式写进日志。
#   为什么取文档而不是把哈希常量钉进源码：下载的是**滚动**地址，钉常量会在上游发新版后永久失败
#   （即历史坑 MID-59「自动安装永久死路」的成因）；取文档则每次都对应当前构建。
#   为什么 TOFU 不足以作为唯一防线：首次安装那一次没有任何可比对的期望值，而那正是供应链投毒最
#   有价值的窗口（发布后第一批用户必然命中）。本模块属 AGENTS.md「三类钉定/校验」的第②类（运行期
#   自动安装，单机面），与 build_exe.py 的发布期钉定（分发面）、utils._JS_SHA256_EXPECTED 的签名
#   脚本层互不覆盖。
#
# Windows 下载源现状（2026-09-23 起）：gyan.dev 是**默认且唯一**的自动路径；失败且未开启
#   FFMPEG_MASTER_ALLOWED 时只给出手动安装提示（见 install_ffmpeg_windows）。第二条源 BtbN master
#   滚动构建（src/ffmpeg_master_download.py）因上游不为 latest 别名公布 .sha256、只能落 TOFU，不满足
#   第②类的准入判据，故显式门控且默认关闭；开启与跳过两条分支都各落一条 warning，不静默。
#   [历史注] 蓝奏云个人网盘兜底已整体删除（直链需爬分享页内联签名、无独立可信来源可比对）；
#   master 源曾默认开启，按 SEV-2218 收为默认关闭。
#
# PATH 优先级策略（W6，2026-09-22 起）：包内 ffmpeg 目录是否前置由 should_prepend_bundled_ffmpeg_dir()
#   单点裁决（判据、后果与日志口径见该函数注释）。本模块自身的「安装成功后前置注入 PATH」**不在**该
#   判据范围内：它只发生在「系统里本来就没有可用 ffmpeg」的自动安装分支。
#   现有**三处**注入点：Windows 官方源（本模块）、Windows master 兜底
#   （src/ffmpeg_master_download.py）、Linux 直下
#   （src/ffmpeg_linux_download.install_ffmpeg_linux_native）。三处都是「先注入再校验，校验失败也保留
#   注入」——该取舍与合并前一致，本次刻意不改。让位判据本身不变：只在 darwin+arm64 生效，Linux 上
#   should_prepend_bundled_ffmpeg_dir() 恒 True，故下一次启动会命中上一次直下的那份、不会每轮重下。
#   [历史注] 上句原写「仅 Windows 分支可达」，Linux arm64 支持落地后已被证伪（Linux 直下同样就地前置 PATH）。


current_platform = platform.system()
execute_dir = script_path  # 冻结后指向 _internal/，与 __file__ 定位的资源收敛到同一处
# [历史注 M-47] 原有导入时快照 `current_env_path = os.environ.get("PATH")` 已连常量撤掉：快照会丢掉
# main.py 侧 W6 注入，防重复嵌套须对**实时** PATH 去重（收敛于内联块的 prepend_to_path_env）。
# 安装目标子目录：解压后可执行文件平铺位于 execute_dir/ffmpeg/ffmpeg.exe。
# [历史注] 原注释称 execute_dir/ffmpeg/bin/，与 copytree 平铺解压的实际布局不符。
# **消费方是 main.py**（模块级 `from src.ffmpeg_install import ... ffmpeg_path ...`）：本模块自己的
# PATH 注入已改读「本次调用的 dest_dir 算出的目标目录」，不得再拿这个常量当注入对象（M-47 的成因）。
ffmpeg_path = os.path.join(execute_dir, "ffmpeg")

# 下载链的重试与退避（M-49）：取值与形态都对齐 src/ffmpeg_master_download.py 与
# src/ffmpeg_linux_download.py 已有的两处实现——连接/读取超时分离，只对连接级与写盘级异常重试，
# 4xx/5xx 不重试（重试不会把 404 变成 200），退避按 2**attempt 递增。
_CONNECT_TIMEOUT = 15
_READ_TIMEOUT = 30
_MAX_RETRIES = 3
_RETRY_BACKOFF = 2.0

# 临时包的**前缀**（不是完整文件名）：保留可识别前缀给既有断言与日志定位，随机后缀由
# 内联块 unique_path 追加，写入一律走 open_exclusive（M-44）。
_TEMP_ZIP_PREFIX = "ffmpeg_official_temp"
_TEMP_ZIP_SUFFIX = ".zip"
# 解包暂存目录的前缀（同级落在 dest_dir 内，见 M-48）与安装落位暂存目录的前缀（见 M-45）。
_UNPACK_PREFIX = "ffmpeg_unpack_"
_STAGED_PREFIX = "ffmpeg_staged_"
# 单次下载的字节上限（M-49 的第三件事：重试之外还必须有量）。gyan.dev essentials 当前约 90MB，
# 取 512MiB 是给上游构建增长留出的余量，同时把「无上限的流」这一族故障关掉：CDN 故障或被改指的
# URL 可以持续吐字节，没有量就没有任何一处能停下 iter_content 的循环。
_MAX_DOWNLOAD_BYTES = 512 * 1024 * 1024


# 下面两个薄封装：实现已下沉到 src.utils，保留本模块别名供既有调用点与测试继续引用（原状是两处
# 逐字重复、node_install 那份还只判 exists——打补丁必漏一处，故收敛到唯一实现）。
# _sha256_of_file 分块读取：整读几百 MB 二进制会瞬时占用大量内存，分块保持内存恒定。
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
#      替换。取舍与后果见下方 swap_directories 定义处注释（旧 `rmtree → copytree` 窗口是「几百 MB 拷
#      贝的全程」，现仅毫秒级）。
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


def _sha256_of_file(path: str | Path) -> str:
    return utils.sha256_of_file(path)


def _is_valid_zip(path: str | Path) -> bool:
    return utils.is_valid_zip(path)


# 子进程控制台窗口抑制：`ffmpeg -version` 这类探测在 Windows 的无控制台形态（pythonw.exe 跑 gui.py、
#   冻结 console=False 的 exe）下每次都会闪出一个黑色控制台窗口。判据与实现一律复用
#   src/video_postprocess.get_startup_info（STARTUPINFO + STARTF_USESHOWWINDOW，录制链的 ffmpeg 调用
#   早已用它），**不得**在本模块再写一份 STARTUPINFO 构造（同一件事只允许一个定义点；孪生的第二份在
#   src/ffmpeg_master_download.py）。
# 判据抽成模块级常量 `_HIDE_CHILD_CONSOLE` 而不是就地写 `if sys.platform != "win32"`，是为了让 Linux CI
#   也能**真走进** win32 分支（与 src/ffmpeg_proc.py 的 `_QUIT_VIA_STDIN` 同一手法）；常量值本身仍是
#   sys.platform 字面量比较，mypy 各平台目标下都只会把它当普通 bool。本函数不引用任何 Windows 专属
#   符号（STARTUPINFO 藏在 get_startup_info 内部，其返回型已是跨平台的 object | None），故**不需要**
#   `# type: ignore`（加了反而在另一侧触发 basedpyright reportUnnecessaryTypeIgnoreComment）。
# 回归锁（tests/test_ffmpeg_install.py::TestChildConsoleStartupInfo）：
#   ::test_gate_off_passes_none_and_never_imports_video_postprocess（门控假 ⇒ 传 None 且不触达那条链）、
#   ::test_delegation_is_skipped_when_the_import_would_be_circular（下面那段前置条件的锁）、
#   ::test_twin_helpers_agree_on_both_gate_states（与 master 孪生副本的行为等价性）、
#   ::test_check_ffmpeg_installed_forwards_startup_info / ::test_official_verify_run_forwards_startup_info
#   （本模块两处调用点的透传）。缺键即 KeyError，故「删掉 startupinfo 实参」这一变异必然转红。
_HIDE_CHILD_CONSOLE = sys.platform == "win32"


def _win_startup_info() -> object | None:
    # 非 Windows 恒返回 None（subprocess 收到 startupinfo=None 等价于不传，行为逐字不变）。
    if not _HIDE_CHILD_CONSOLE:
        return None
    # 委托前置条件：① src.video_postprocess 已在 sys.modules（其模块体已跑完，或被测试用假模块占位），
    # 或 ② main 已在 sys.modules（正常入口顺序——main.py 在模块级就 import 了它）。两者都不成立时
    # **必须**直接返 None：那时这句 from-import 会**首次**执行 video_postprocess，而它顶层 `import main`
    # → main → src.notify 的模块级 `from src.video_postprocess import get_startup_info` 命中尚未跑完的
    # video_postprocess → ImportError（2026-10-18 由 TestChildConsoleStartupInfo 实测抓出，形态
    # "cannot import name 'get_startup_info' from partially initialized module"）。除报错外，那次失败
    # 的导入还会**半程执行 main 的模块体**（含 SetConsoleOutputCP(65001)），污染整个宿主进程。
    # 本模块对「可选加固不得打断主流程」早有口径：拿不到就退回改动前的行为（闪一个控制台窗口）。
    if "src.video_postprocess" not in sys.modules and "main" not in sys.modules:
        return None
    from src.video_postprocess import get_startup_info

    return get_startup_info(os.name)


# 校验已下载 zip 的 SHA256（trust-on-first-use 模型）：
# - 首次下载完成后把哈希写到旁路文件
# - 再次下载/校验时若旁路文件存在则比对，不一致则拒绝安装
#
# 旁路文件**按构建标识命名**而不是按滚动 URL 的固定 zip 名：gyan.dev 的
#   ffmpeg-release-essentials.zip 是滚动地址、上游每次出新构建内容（SHA）必变，固定命名
#   _ffmpeg_official.zip.sha256 一旦记录某构建，下次自动安装拿到新构建就**永远不等** → 官方源拒绝 →
#   用户只剩一行 logger.error 和「请手动安装 ffmpeg」（MID-59「自动安装永久死路」）。按构建标识（响应
#   头 Last-Modified / ETag / Content-Length 的摘要）命名后，「版本轮转」表现为「为新构建记录新基准」、
#   「同一构建内容变了」仍是硬失败——篡改检测强度不降。
#   [历史注] 旧失败链的蓝奏云兜底已删除（见模块头「Windows 下载源现状」），链尾现为「官方源拒绝 → 直接只剩手动安装」。
#
# 防护强度边界（勿据此高估）：
#   1) 不能消除 CDN 投毒（首次下载始终是 trust-on-first-use），只阻断「已缓存 zip 被静默替换」这条
#      重安装路径；官方哈希文档优先后，TOFU 只在取不到文档时生效，已收窄；
#   2) 旁路文件与 zip 同在 execute_dir（冻结后为 _internal/），能写该目录者可同时替换产物与基准文件，
#      故其强度**等同目录权限**，不是独立的信任根；
#   3) 官方哈希文档与产物**同主机、同一 HTTPS 通道**，只是一次**同源一致性校验**（防传输截断、防
#      CDN/代理缓存污染、防把挑战页当产物），**不构成来源认证**——宿主或 CDN 被整体替换时文档与产物
#      会被一并换掉，校验归零。gyan.dev 不提供 detached 签名，故 Windows 运行期目前只能到这一档；
#      真要加来源认证得换一个「文档与产物异源」的取法（对比 src/node_install.py 刻意换宿主取
#      SHASUMS256.txt 的做法，以及 build_exe.py 的发布期钉定，见 AGENTS.md「三类钉定/校验」②）。
_FFMPEG_HASH_FILE = "_ffmpeg_official.zip.sha256"  # 旧版（不随构建轮转）命名，仅作只读兼容
_HASH_SUFFIX = ".zip.sha256"

# 官方哈希文档的后缀（gyan.dev 对每个构建产物都公布 `<产物名>.sha256`，内容就是裸 64 位十六进制）。
# 与上面的 _HASH_SUFFIX（本地旁路基准文件名的后缀，含 .zip）刻意不同名，勿混用。
_OFFICIAL_DOC_SUFFIX = ".sha256"
# 哈希文档只有 64 字节，用与 300MB 压缩包相同的 30s 超时会在上游故障时把启动拖慢一倍；
# 取不到即降级为 TOFU，不值得为它多等。
_OFFICIAL_DOC_TIMEOUT_SECONDS = 15
# 官方哈希小文档的读取上限（M-12）：下载**主链路**有 512MiB 上限，文档链此前无任何上限——
# TLS 被拦截/恶意代理前提下，64 字节端点回 GB 级 200 响应可在启动期耗尽内存。与 node 侧
# _NODE_VERSION_PAGE_MAX_BYTES 同值（2MiB，比真实文档宽一个数量级以上，宁可放宽不误杀）。
_OFFICIAL_DOC_MAX_BYTES = 2 * 1024 * 1024
# 官方文档的合法形态：整篇剥掉空白后必须**正好**是 64 位小写十六进制。
# 判据必须严格：gyan.dev 在前置代理/WAF 介入时会回 200 + 一段 HTML 挑战页，
# 「长度看着像」的宽松判定会把挑战页当成期望哈希，从而把可用源判成篡改。
_SHA256_RE = re.compile(r"[0-9a-f]{64}")


# 把官方哈希文档正文解析为小写十六进制摘要；形态不符（HTML 错误页、截断、含文件名前缀等）返回 ""。
def _parse_official_sha256(text: str) -> str:
    candidate = text.strip().lower()
    return candidate if _SHA256_RE.fullmatch(candidate) else ""


# 向上游取官方公布的 SHA256。返回 ""=未取得（调用方据此显式降级到 TOFU）。失败绝不抛异常：本函数
# 的定位是「能拿到就更强、拿不到就退回原有防线」，若让网络故障把整条安装链路打成异常，等于用一个
# 可选加固换掉本来能成功的自动安装。
# 2026-09-22 实测形态：文档端点回 303 → /ffmpeg/builds/packages/ffmpeg-<ver>-essentials_build.zip.sha256，
# 最终正文是**裸 64 位小写十六进制**（无换行、无文件名）。因此这里**必须保持 requests 的默认
# allow_redirects=True**：改成 False（或换成 HEAD）会永远只看到 303 + 空正文 → 恒降级为 TOFU，且日志
# 里只是一句「未取得文档」，极易误判成上游故障。
def _fetch_official_sha256(doc_url: str) -> str:
    try:
        with requests.get(doc_url, timeout=_OFFICIAL_DOC_TIMEOUT_SECONDS) as response:
            response.raise_for_status()
            # M-12：官方哈希小文档按字节限长读取（判据复用 node_install._read_small_document_capped）。
            # 超限返回 None → 置空串，落进下方「内容不合法」既有降级口径走 TOFU，不新增 fatal 形态。
            text = _read_small_document_capped(response, _OFFICIAL_DOC_MAX_BYTES)
            if text is None:
                text = ""
    except Exception as e:
        logger.warning(
            i18n.tr(
                "未取得 ffmpeg 官方 SHA256 文档: {masked_url} - {type_name}: {err}",
                masked_url=utils.mask_credentials(doc_url),
                type_name=type(e).__name__,
                err=e,
            )
        )
        return ""
    parsed = _parse_official_sha256(text)
    if not parsed:
        logger.warning(
            i18n.tr(
                "ffmpeg 官方 SHA256 文档内容不是合法的 64 位十六进制摘要（上游形态可能已变更）: {masked_url}",
                masked_url=utils.mask_credentials(doc_url),
            )
        )
    return parsed


# 由下载响应头推导「构建标识」：无任何可用头时返回 ""（退化为旧命名，保持有校验而非静默放行）。
def _build_identity(headers: Mapping[str, str] | None) -> str:
    if not headers:
        return ""
    try:
        bits = [
            str(headers.get("Last-Modified") or "").strip().strip('"'),
            str(headers.get("ETag") or "").strip().strip('"'),
            str(headers.get("Content-Length") or "").strip(),
        ]
    except Exception:  # 非 Mapping 形态（测试桩）不影响主流程
        return ""
    raw = "|".join(b for b in bits if b)
    if not raw:
        return ""
    # 取摘要前 12 位：头里含冒号 / 空格 / 逗号，直接拼进文件名在 Windows 上非法
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]


# 旁路文件基名：有构建标识 → _ffmpeg_official.<id>.zip.sha256；无标识 → 旧名。
def _hash_file_name(build_id: str) -> str:
    return f"_ffmpeg_official.{build_id}{_HASH_SUFFIX}" if build_id else _FFMPEG_HASH_FILE


# 把本次实算哈希写进旁路基准（TOFU 的「记录」侧）。
# 权威校验通过时同样记录：官方文档不可达的那次运行（离线 / 上游故障）需要它才有可比对基准。
def _record_zip_sha256(zip_path: Path, hash_file: Path, current_hash: str) -> None:
    # 本构建标识首次记录。若目录里已存在其它基准文件，说明上游发布了新构建（旧基准随之失效），
    # 显式告警并列出被取代的基准，便于用户复核两次哈希是否来自可信渠道。
    stale = sorted(p.name for p in zip_path.parent.glob(f"_ffmpeg_official*{_HASH_SUFFIX}") if p.name != hash_file.name)
    try:
        hash_file.write_text(current_hash, encoding="ascii")
        if stale:
            logger.warning(
                i18n.tr(
                    "ffmpeg 官方源已发布新构建，已为新构建记录 SHA256 基准：{hash_file}（{actual}）。"
                    "旧基准 {stale} 不再参与校验，确认无误后可删除。",
                    hash_file=str(hash_file),
                    actual=current_hash,
                    stale=", ".join(stale),
                )
            )
        else:
            logger.debug(i18n.tr("首次下载 SHA256 已记录：{current_hash}", current_hash=current_hash))
    except OSError as e:
        logger.warning(i18n.tr("写入 SHA256 缓存失败（不影响本次安装）: {e}", e=e))


# 完整性判定入口：**官方公布的哈希优先**，取不到才退回旁路基准 TOFU（原行为）。
# 返回 True = 校验通过或（首次/新构建）记录成功；返回 False 一律意味着「同一构建标识下内容与
# 期望值不符」——真篡改形态，调用方必须删包且不执行。
def _check_or_record_zip_sha256(
    zip_path: Path, build_id: str = "", official_hash: str = "", source_url: str = ""
) -> bool:
    hash_file = zip_path.parent / _hash_file_name(build_id)
    current_hash = _sha256_of_file(zip_path)
    masked_url = utils.mask_credentials(source_url) if source_url else "unknown"
    if official_hash:
        # 权威分支：官方文档就是当前构建的期望值，旁路基准至多是第二道记录，不得反过来否决它
        # （否则 MID-59 的「版本轮转即永久拒装」在官方文档可达时仍会复现）。
        if official_hash != current_hash:
            logger.error(
                i18n.tr(
                    "ffmpeg 官方源 zip 与官方公布的 SHA256 不一致，拒绝安装（官方 {official} vs 实际 {actual}）："
                    "{masked_url}。可能是 CDN/中间人替换，或下载期间上游又发了新构建（稍后重试即可）。",
                    official=official_hash,
                    actual=current_hash,
                    masked_url=masked_url,
                )
            )
            return False
        logger.debug(i18n.tr("ffmpeg zip 已通过官方公布 SHA256 校验: {masked_url}", masked_url=masked_url))
        _record_zip_sha256(zip_path, hash_file, current_hash)
        return True
    # 降级分支（P-1 的显式降级点）：官方文档拿不到 → 只能沿用首次信任，必须让日志说清强度回落了。
    logger.warning(
        i18n.tr(
            "未能取得 ffmpeg 官方公布的 SHA256，本次退回旁路基准/首次信任（TOFU）: {masked_url}",
            masked_url=masked_url,
        )
    )
    if hash_file.exists():
        try:
            expected = hash_file.read_text(encoding="ascii").strip().lower()
        # 必须并捕 UnicodeDecodeError：基准是磁盘上可被外部改写的输入，用户手工编辑或同步盘把它转成
        # UTF-8 后，read_text(encoding="ascii") 抛的是 UnicodeDecodeError（ValueError 子类，**不是**
        # OSError），只捕 OSError 接不住。本模块的代价是「检查失效」：异常穿出后被
        # download_ffmpeg_official 的 catch-all `except Exception` 归成一句泛化的「安装失败」，于是
        # ① 下面那条 fail-closed 分支（删包 + 点名「请人工核对或删除 {hash_file} 后重试」）整个被跳过，
        # 用户失去自救入口；② 几百 MB 的 ffmpeg_official_temp.zip 不会被删。三处姊妹实现
        # （ffmpeg_master_download / ffmpeg_linux_download）同批并捕，不再分叉。需要 as 绑定取
        # type(e)/e，故按 AGENTS 的 except 约定回退加括号形态。回归锁：
        # tests/test_ffmpeg_install.py::TestOfficialBaselineDecodeGuard::test_non_ascii_baseline_refuses_and_unlinks。
        except (OSError, UnicodeDecodeError) as e:
            # 基准**存在**却读不出来 = 本机那份可信基准处于不可信状态，必须拒装（fail-closed）。旧实现
            # warning 后 return True 放行——唯一一道完整性检查在磁盘异常时静默失效（官方文档不可达时
            # TOFU 就是最后一道）。触发需「官方文档不可达 ∧ 基准损坏 ∧ CDN 投毒」三重叠加，属防御纵深收紧
            # 非行为回归；返回 False 走调用方既有「删包且不执行」路径，用户删掉该基准后重试即恢复 TOFU 记账。
            # [历史注] master 侧同形分支曾称两侧「刻意不同」（那边 TOFU 是唯一一道）——该理由对本模块的
            # 降级分支同样成立，故 L-44（2026-10-02）两侧统一收紧。
            try:
                zip_path.unlink()
            except OSError:
                pass
            logger.error(
                i18n.tr(
                    "ffmpeg 的 SHA256 基准文件存在但读取失败，拒绝安装未校验的二进制"
                    "（请人工核对或删除 {hash_file} 后重试）: {type_name}: {e}",
                    hash_file=str(hash_file),
                    type_name=type(e).__name__,
                    e=e,
                )
            )
            return False
        if expected != current_hash:
            logger.error(
                i18n.tr(
                    "ffmpeg 官方源 zip SHA256 与上次记录不一致（{expected} vs {actual}）。"
                    "可能 CDN 被篡改或版本变更。请删除 {hash_file} 后重试，或手动下载校验。",
                    expected=expected,
                    actual=current_hash,
                    hash_file=str(hash_file),
                )
            )
            return False
        logger.debug("ffmpeg SHA256 校验通过")
        return True
    _record_zip_sha256(zip_path, hash_file, current_hash)
    return True


# 删除本次下载的临时压缩包。幂等：不存在即什么都不做。删不掉**静默吞掉** OSError 而不留日志：本函数
#   唯一场景是「系统 PATH 里没有 ffmpeg」时的自动安装，删不掉临时包属清理失败而非安装失败——升级成
#   异常会穿出「安装失败只返回 False、不抛」的契约（见模块头「设计取舍」），升级成 warning 则会在磁盘
#   只读/文件被占用的机器上每轮启动刷一条与结果无关的噪音。真正的风险是**残留**：gyan.dev essentials
#   约 90MB、BtbN master 约 190MB，下载中断或解压抛错后不删，程序目录就长期躺着一个「看着像已下载
#   完成」的半截包。
def _discard_official_zip(zip_path: Path) -> None:
    if not zip_path.exists():
        return
    try:
        zip_path.unlink()
    except OSError:
        pass


# 单次流式下载的重试外壳（M-49）：把「重试 + 指数退避 + 字节上限」收敛成一处，形态对齐
#   src/ffmpeg_master_download._stream_download 与 src/ffmpeg_linux_download._download。
#   三条链此前只有这一条是单次尝试、无任何量上限，而它恰是 Windows 上**默认且唯一**的自动路径
#   ——一次连接重置就整条安装失败，用户只剩一句「请手动安装」。
# 判序三条，任一条回退都会重开已修故障：
#   ① `except requests.HTTPError` 必须写在 `except (requests.RequestException, OSError)` **之前**
#     （HTTPError 是 RequestException 的子类，顺序写反就永远进不了「不重试」这一支；同 Linux 侧注释）；
#   ② 独占创建发生在 `raise_for_status()` **之后**——4xx/5xx 那一支根本不产生文件，这与
#     tests/test_ffmpeg_linux_download.py::TestDownloadRetryPolicy::test_http_error_is_not_retried
#     对同名分支的判据保持一致；
#   ③ 半截文件必须在下一轮尝试之前删掉：留着它，下一轮的 O_EXCL 创建必然失败（且它本身就是
#     「看着像下载完成」的假证据）。close 与 unlink 的先后由 `with open_exclusive(...)` 保证——
#     Windows 上未关闭的句柄会让 unlink 直接失败。
# 返回值口径：**二元组** (构建标识, 本次是否真的创建了临时包)。构建标识合法值含空串，None 一律意味着
#   「本次没拿到可信产物」；第二个成员是 M-44 的收尾依据——调用点的 finally **只能删自己创建的文件**，
#   否则「路径已被别人占着」这一轮会把对方的文件当成我们的半截包删掉（正是 M-44 登记的互删形态）。
# 本函数**不抛**（抛出会把「装不上」升级成穿出 download_ffmpeg_official 的异常，违背模块头
#   「安装失败只返回 False、不抛」的契约）。
def _stream_official_zip(url: str, zip_path: Path) -> tuple[str | None, bool]:
    last_err: Exception | None = None
    # 循环前的这次预置只为「_MAX_RETRIES 被改成 0 时返回语句仍有绑定」兜底；真正的语义是
    # **每轮 attempt 都重新判定**——上一轮删掉的是自己创建的，下一轮创建失败不能算我们的文件。
    created = False
    for attempt in range(1, _MAX_RETRIES + 1):
        completed = False
        created = False
        try:
            with requests.get(
                url, stream=True, timeout=(_CONNECT_TIMEOUT, _READ_TIMEOUT), allow_redirects=True
            ) as response:
                response.raise_for_status()
                with open_exclusive(zip_path) as sink:
                    created = True
                    # Content-Length 可能缺失（分块传输）为 0，tqdm 进度条退化为未知总量，仅影响显示不影响下载。
                    total_size = int(response.headers.get("Content-Length", 0))
                    # MID-59：在读取响应头仍可用的作用域内固化「构建标识」，供旁路文件命名。
                    build_id = _build_identity(response.headers)
                    written = 0
                    with tqdm(
                        total=total_size, unit="B", unit_scale=True, ncols=100, desc="Downloading ffmpeg (official)"
                    ) as t:
                        for data in response.iter_content(chunk_size=1024):
                            written += len(data)
                            if written > _MAX_DOWNLOAD_BYTES:
                                logger.error(
                                    "Official ffmpeg download exceeded the accepted size limit; aborting without install"
                                )
                                return None, created
                            _ = t.update(len(data))
                            _ = sink.write(data)
                    completed = True
                    return build_id, created
        except requests.HTTPError as e:
            logger.error("Official ffmpeg download returned an HTTP error: " + type(e).__name__)
            return None, created
        except (requests.RequestException, OSError) as e:
            last_err = e
            logger.warning("Official ffmpeg download failed on attempt " + str(attempt) + "/" + str(_MAX_RETRIES))
            if attempt < _MAX_RETRIES:
                time.sleep(_RETRY_BACKOFF**attempt)
        finally:
            if created and not completed:
                _discard_official_zip(zip_path)
    logger.error("Official ffmpeg download still failed after " + str(_MAX_RETRIES) + " attempts")
    logger.debug("Official ffmpeg download last error: " + type(last_err).__name__)
    return None, created


# 把解包出来的 bin 目录**完整落成同级暂存目录、再两次改名换进目标位**（M-45）。
# 旧形态 `rmtree(target) + copytree(bin, target)` 的破坏排序与后果见 swap_directories 函数注释。
# 这里保留原有的那道前置校验：调用点必须先确认解包产物里有 bin/ffmpeg.exe（见
#   download_ffmpeg_official 里的 `bin_dir is None` 分支），删旧动作永远发生在校验之后。
# 返回 False 表示「本次没能落位、旧安装原地未动」，由调用方归成安装失败。
def _install_bin_dir(bin_dir: str, ffmpeg_target: str) -> bool:
    parent = os.path.dirname(ffmpeg_target) or "."
    staged = Path(tempfile.mkdtemp(dir=parent, prefix=_STAGED_PREFIX))
    try:
        shutil.copytree(bin_dir, str(staged), dirs_exist_ok=True)
        # 落位前再验一次「暂存副本里确实有可执行文件」：copytree 中途失败不会抛的话，
        # 换进去的就是一个空壳，M-45 要防的形态会以另一种形式回来。
        if not (staged / "ffmpeg.exe").is_file():
            logger.error("Staged ffmpeg directory is incomplete; previous install left untouched")
            return False
        swap_directories(staged, ffmpeg_target)
    except OSError as e:
        logger.warning("Could not put the newly installed ffmpeg in place: " + type(e).__name__)
        return False
    finally:
        shutil.rmtree(str(staged), ignore_errors=True)
    return True


def download_ffmpeg_official(url: str, dest_dir: str) -> bool:
    # L-13：临时包路径必须先于 try 求值，函数末尾的 finally 才能在**所有**出口（含两个 except 分支）
    # 引用到它；写在 try 第一行则异常出口可能没有这个名字（UnboundLocalError 风险）。
    # [M-44 2026-10-21] 「先于 try 求值」这条形状约束保留，但名字不再固定：原先的
    #   `Path(dest_dir) / "ffmpeg_official_temp.zip"` 是可预测名，两个并发安装会互相覆盖并在各自
    #   finally 里 unlink 掉对方的包，能写本目录的本地主体还能预置同名符号链接把几百 MB 引到任意路径。
    #   现由 unique_path 生成「可识别前缀 + 随机后缀」，写入一律走 open_exclusive（O_CREAT|O_EXCL|
    #   O_NOFOLLOW）：已存在即失败，绝不跟随、绝不覆盖。
    # 目录锁（M-44 的另一半）：随机名只保证「互不覆盖」，不保证「互不并发」——两条链同时跑仍会
    #   同时向同一个 execute_dir/ffmpeg 落位。锁竞争按**失败**处置（返回 False），与模块头的
    #   「安装失败只返回 False、不抛」契约同一口径。
    zip_file_path = unique_path(dest_dir, _TEMP_ZIP_PREFIX, _TEMP_ZIP_SUFFIX)
    # 本次是否真的创建了那个临时包（M-44）：收尾清理**只能删自己创建的文件**。不判这一条，
    # 「路径已被另一个实例或本地攻击者占着」的那一轮会把对方的文件当成我们的半截包 unlink 掉——
    # 而那恰好是 M-44 登记的另一半故障（两实例在各自 finally 里互删对方的包）。
    created_temp_zip = False
    with install_lock(dest_dir) as lock_held:
        if not lock_held:
            logger.warning("Another ffmpeg installer holds this directory; skipping the official download")
            return False
        try:
            # P-1：下载**前**先取官方公布的期望哈希。放在前面而不是后面，是为了在上游文档已不可达 / 已被
            # 替换时少拉一次几百 MB；比对对象仍是同一 URL 的当前构建（上游版本轮转的窗口在两种顺序下都存在，
            # 区别只是「白下载一次」与「白等一次」）。
            official_hash = _fetch_official_sha256(url + _OFFICIAL_DOC_SUFFIX)

            # 下载文件（带进度条、重试与字节上限）
            build_id, created_temp_zip = _stream_official_zip(url, zip_file_path)
            if build_id is None:
                return False

            # 加固：先判「拿到的到底是不是压缩包」，再进哈希校验/记账。成因不是假想：CDN / 前置代理 / 被改指
            # 的 URL 都会以 **200 + text/html** 回一段挑战页（实测形态：某镜像站的人机验证 PoW 页，正文 10KB、
            # 且不带 Content-Length / ETag / Last-Modified）。三个头全缺 → _build_identity 返回 "" → 旁路基准落到
            # **旧文件名**；若不在此拦住，_check_or_record_zip_sha256 会在 TOFU 分支把这段 HTML 的哈希当成
            # 「可信基准」写下去，而真正的失败要等到 unzip_file 才暴露，基准已被污染。判序必须是「形态 →
            # 哈希 → 解压」：三者校验的都是同一个产物文件。
            if not _is_valid_zip(zip_file_path):
                logger.error(
                    i18n.tr(
                        "ffmpeg 下载产物不是有效的 zip 压缩包，拒绝校验与安装"
                        "（内容可能是人机验证页 / 错误页，而非构建产物）: {masked_url}",
                        masked_url=utils.mask_credentials(url),
                    )
                )
                try:
                    zip_file_path.unlink()
                except OSError:
                    pass
                return False

            if not _check_or_record_zip_sha256(zip_file_path, build_id, official_hash, source_url=url):
                try:
                    zip_file_path.unlink()
                except OSError:
                    pass
                return False

            # 解压并提取 bin 目录。统一走 unzip_file：它带解压炸弹防护（单文件 4GB / 累计 8GB / 压缩比 100x
            # 上限）与 Zip Slip 校验，损坏或被投毒的 zip 不得绕过这层。
            # M-48：解包目录必须落在**目标目录同级**而不是 %TEMP%。gpl/essentials 包解后可达几百 MB，
            #   而容器里的 /tmp 常是小 tmpfs，默认临时目录一满就整条链 ENOSPC 死在解压这一步；
            #   Linux 侧早就刻意落在应用目录内（src/ffmpeg_linux_download._install_binaries 的
            #   `TemporaryDirectory(dir=...)`），Windows 两处留在默认临时目录属同一功能点的两套口径。
            #   空间预检排在解包**之前**：预检的意义就是「不要先写坏一半再失败」。
            if not has_room_for_unpack(dest_dir, zip_file_path.stat().st_size):
                logger.warning("Insufficient free space beside the install target; ffmpeg unpacking aborted")
                return False
            with tempfile.TemporaryDirectory(dir=dest_dir, prefix=_UNPACK_PREFIX) as tmp_dir:
                unzip_file(zip_file_path, tmp_dir, delete=False)

                # 查找 bin 目录（含 ffmpeg.exe）
                bin_dir = None
                for root, _dirs, files in os.walk(tmp_dir):
                    if os.path.basename(root) == "bin":
                        if "ffmpeg.exe" in files:
                            bin_dir = root
                            break

                if bin_dir is None:
                    logger.error("ffmpeg.exe not found in official package")
                    return False

                # 复制到目标位置（M-45：同级暂存 + 改名替换，失败时旧安装原地保留）
                ffmpeg_target = os.path.join(dest_dir, "ffmpeg")
                if not _install_bin_dir(bin_dir, ffmpeg_target):
                    return False

            # 清理临时文件
            if zip_file_path.exists():
                zip_file_path.unlink()

            # 把 ffmpeg 目录前置注入 PATH，本进程及子进程后续 `ffmpeg` 调用都命中新装文件（覆盖系统其它同名项）。
            # 先注入再校验，校验失败也保留注入——无副作用（该目录即安装产物）。
            # L-15：本行刚装完就真跑一次 ffmpeg.exe，Windows 无控制台形态下不传 startupinfo 会闪窗。
            # M-47：注入对象改为**本次调用的目标目录**（此前是模块级 ffmpeg_path 常量 + 导入时 PATH 快照，
            #   dest_dir != execute_dir 时注入的是一个没被写过的目录，紧随其后的复核必然失败）；
            #   去重交给 prepend_to_path_env（同一前缀反复叠加的老问题由它一次关掉）。
            prepend_to_path_env(ffmpeg_target)
            result = subprocess.run(
                ["ffmpeg", "-version"], capture_output=True, timeout=30, startupinfo=_win_startup_info()
            )
            if result.returncode == 0:
                logger.debug("ffmpeg (official) installation was successful")
                return True
            else:
                logger.error("ffmpeg official installation verification failed")
                return False

        except requests.RequestException as e:
            logger.warning(i18n.tr("Official ffmpeg download failed (network error): {e}", e=e))
            return False
        except Exception as e:
            logger.error(
                i18n.tr("Official ffmpeg installation failed: {type_name} - {e}", type_name=type(e).__name__, e=e)
            )
            return False
        finally:
            # L-13：出口统一清理。此前只有三条「判定失败」出口各自内联 unlink（非压缩包 / 哈希不符 /
            # 成功后清临时文件），而**异常**出口一条都没删：下载中断、unzip_file 抛解压炸弹/损坏、
            # bin 目录找不到 ffmpeg.exe（在 with 块内直接 return）、copytree/复核抛错——实测共四条出口漏删
            # （gyan.dev 包约 90MB、master 约 190MB）。finally 覆盖全部路径且与三条既有内联 unlink 幂等共存。
            # 回归锁：tests/test_ffmpeg_install.py::TestOfficialDownload
            # ::test_interrupted_download_unlinks_temp_zip / ::test_unzip_failure_unlinks_temp_zip
            # ::test_missing_bin_dir_unlinks_temp_zip。
            # [2026-10-21 M-44] 这条统一清理现在带「所有权」前提：只删本轮真正创建过的文件。
            # 随机名让「占位者猜中本轮名字」几乎不可能，但一旦 unique_path 被换回固定名或名字被复用，
            # 无差别的 unlink 就立刻变成「删掉别人的下载包」，所以前提必须留在代码里而不是靠命名兜住。
            if created_temp_zip:
                _discard_official_zip(zip_file_path)


def install_ffmpeg_official_windows() -> bool:
    # Windows: 从官方源 gyan.dev 安装 FFmpeg
    official_url = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
    return download_ffmpeg_official(official_url, execute_dir)


# 第二条 Windows 运行期 ffmpeg 源（BtbN master 滚动构建）的显式开关，默认关闭（SEV-2218）。
# 为什么必须默认关：AGENTS.md「三类钉定/校验」② 的红线是「Windows 运行期新增第二条自动路径前必须
# 先满足『官方公布哈希』判据」；master-latest 是**滚动别名**，BtbN 与 fyhub 镜像都不为它公布可核对的
# .sha256（后者该文档实测 404），只能落 TOFU——恰恰不满足判据。与被删除的蓝奏云兜底同一处置口径：
# 要使用，就得用户显式承担未校验安装的后果。
_FFMPEG_MASTER_ENV = "FFMPEG_MASTER_ALLOWED"


def _master_source_allowed() -> bool:
    # 取值口径一律走 src/config_bool.parse_config_bool（是/否、true/false、1/0、yes/no、on/off、t/f，
    # 大小写与首尾空白均不敏感），**不得**再写 `== "1"` / `in ("true","1")` 这类第三套布尔判定。
    # 未设置该变量时 parse_config_bool(None, False) 返回默认值 False。
    return parse_config_bool(os.environ.get(_FFMPEG_MASTER_ENV), False)


def install_ffmpeg_windows() -> bool:
    # Windows 安装入口：按「架构 × FFMPEG_MASTER_ALLOWED 开关」分流（门禁理由见 _FFMPEG_MASTER_ENV）。
    # x86_64 只走 gyan.dev 官方源（带官方 SHA256 校验），失败时**仅当**开关取真才回落 BtbN master（仅
    # TOFU）；ARM64 因 gyan.dev 只发 x86_64（可经 x64 模拟），原生 arm64 只能来自 master，故未开启时用
    # 官方 x86_64 模拟、开启后先试原生 arm64 再退官方 x86_64 保底。失败不抛异常，由调用方决定后续提示。
    logger.warning("ffmpeg is not installed.")
    is_arm64 = platform.machine().lower() in ("arm64", "aarch64")
    master_allowed = _master_source_allowed()
    if master_allowed:
        logger.warning(
            i18n.tr(
                "{env} 已开启：允许使用 BtbN master 构建作为 ffmpeg 兜底源。该源上游不公布 latest 别名的 "
                "SHA256，本次完整性仅为首次信任（TOFU，等同未校验安装），请在可信网络环境下核对产物。",
                env=_FFMPEG_MASTER_ENV,
            )
        )
    else:
        logger.warning(
            i18n.tr(
                "{env} 未开启：跳过 BtbN master 兜底源（因其无官方公布的 SHA256，默认不作为自动安装路径）。"
                "Windows 仍只使用 gyan.dev 一条官方自动路径{arm_note}",
                env=_FFMPEG_MASTER_ENV,
                arm_note="；ARM64 宿主上该官方构建经 x64 模拟运行" if is_arm64 else "",
            )
        )

    if is_arm64:
        if master_allowed:
            logger.debug(
                "Windows on ARM detected; gyan.dev ships x86_64 only — trying native arm64 master build (TOFU) ..."
            )
            if download_ffmpeg_master(execute_dir, arch="winarm64"):
                return True
            # 原生失败退回官方 x86_64（经模拟运行），至少可用
            logger.warning(
                "Native arm64 ffmpeg unavailable, falling back to official x86_64 build (emulated under x64) ..."
            )
        if install_ffmpeg_official_windows():
            return True
    else:
        logger.debug("Trying to install ffmpeg from official source (gyan.dev)...")
        if install_ffmpeg_official_windows():
            return True
        # x86_64 官方源失败的兜底：BtbN master 构建（来自 ffmpeg-windows-builds 官方发布通道；
        # latest 别名不公布 .sha256，故仅 TOFU，完整性弱于官方 SHA256），受上面的 master_allowed
        # 门禁、未开启时走不到这一行。它是「gyan.dev 慢/被阻」时的可用性兜底。
        if master_allowed:
            logger.warning("Official gyan.dev source failed; trying BtbN master build fallback (TOFU, unverified) ...")
            if download_ffmpeg_master(execute_dir, arch="win64"):
                return True

    # 全部失败：给出手动安装提示。官方源被「哈希基准」拒时用户只剩一句无指向性的提示，故把可执行的自救
    # 步骤（删过期基准）与旁路文件的真实防护强度（与产物同目录 → 等同目录权限）一并说明；master 路径的
    # TOFU 基准（_ffmpeg_master*）同理。
    logger.error("All download methods failed. Please manually install ffmpeg by yourself.")
    logger.warning(
        i18n.tr(
            "若因 SHA256 基准校验被拒，请删除 {files} 后重试（该旁路文件与安装包同目录，"
            "其校验强度等同于目录权限；官方源用 _ffmpeg_official*，master 源用 _ffmpeg_master*）。",
            files=os.path.join(execute_dir, "_ffmpeg_official*") + " / " + os.path.join(execute_dir, "_ffmpeg_master*"),
        )
    )
    return False


def install_ffmpeg_mac() -> bool:
    # macOS: 使用 Homebrew 安装 FFmpeg
    logger.warning("ffmpeg is not installed.")
    logger.debug("Installing the stable version of ffmpeg for macOS...")
    try:
        result = subprocess.run(["brew", "install", "ffmpeg"], capture_output=True, timeout=600)
        if result.returncode == 0:
            logger.debug("ffmpeg installation was successful. Restart for changes to take effect.")
            return True
        else:
            logger.error("ffmpeg installation failed")
    # L-43（2026-10-02）：原在此处的 except subprocess.CalledProcessError 不可达——
    # subprocess.run 未传 check=True 永不抛该异常，删除；通用兜底分支保留。
    except Exception as e:
        logger.error(i18n.tr("An unexpected error occurred: {e}", e=e))
    return False


def install_ffmpeg_linux() -> bool:
    # Linux: 自动选择 yum/apt 安装 FFmpeg
    is_RHS = True

    # 尝试 yum (RHEL/CentOS)
    try:
        logger.warning("ffmpeg is not installed.")
        logger.debug("Trying to install the stable version of ffmpeg")
        # 移除 `yum -y update`：它是**全量系统升级**（一并升内核 / glibc / systemd，副作用远超「装一个
        # ffmpeg」、甚至要求重启），且 `yum install` 自身会刷新仓库元数据、无需前置 update；旧实现
        # update 失败即 return False，还会把「yum 源暂不可用」误判成 RHEL 系不可用、连 apt 回退都不给。
        # [历史注] is_RHS 原本只在 FileNotFoundError 分支置 False，「yum 在位但装不上」曾直接落到「请手动安装」。
        result = subprocess.run(["yum", "install", "-y", "ffmpeg"], capture_output=True, timeout=300)
        if result.returncode == 0:
            logger.debug("ffmpeg installation was successful using yum. Restart for changes to take effect.")
            return True
        logger.error(result.stderr.decode("utf-8", errors="replace").strip())
        # MIN-24④：is_RHS 的语义是「还要不要试 apt」。yum 存在但装不上（仓库里没有 ffmpeg）
        # 时不能就此放弃——继续走 apt 分支；apt 也不存在时由它的 FileNotFoundError 分支
        # 给出「请手动安装」，不会静默成功。
        is_RHS = False
    except FileNotFoundError:
        logger.debug("yum command not found, trying to install using apt...")
        is_RHS = False
    except Exception as e:
        logger.error(i18n.tr("An error occurred while trying to install ffmpeg using yum: {e}", e=e))
        # L-14：本分支必须置 is_RHS=False。原先只打日志、不改标志，于是「yum 在位但 run() 抛非
        # FileNotFoundError 异常」（TimeoutExpired——yum 挂在仓库同步上；PermissionError——非 root 却试图写
        # yum 缓存；以及 result.stderr 形态异常带来的 AttributeError 等）会跳过 apt 分支、直接落到函数
        # 末尾的直下兜底，与该处自述的顺序判据正相反。is_RHS 的语义就是「还要不要试 apt」，异常轮同样属
        # 「没装上」。代价可控：RHEL 系上 apt 本就不存在，只会多一条「apt command not found」的既有 error
        # 日志。
        # [行为变更] tests/test_ffmpeg_install.py::TestLinuxExtraBranches::test_yum_probe_crash_keeps_rhs_semantics
        # 曾把「apt 不被触达」当既有语义钉住（锁的是本条要修的缺陷本身），已随 L-14 改判为「yum 抛错后必须
        # 仍试 apt」。副作用：改完后走到 `if not is_RHS:` 时该标志恒为 False（yum 成功那一支已 return），守卫
        # 成为形式上的恒真判断——刻意保留而不删，它仍是「两条包管理器路径」这一结构的落点。
        # 回归锁：tests/test_ffmpeg_install.py::TestLinuxExtraBranches::test_yum_probe_crash_still_tries_apt。
        is_RHS = False

    # 尝试 apt (Debian/Ubuntu)
    if not is_RHS:
        try:
            logger.debug("Trying to install the stable version of ffmpeg for Linux using apt...")
            result = subprocess.run(["apt", "update"], capture_output=True, timeout=300)
            if result.returncode != 0:
                logger.error("Failed to update package lists using apt")
                # R-11：本分支原先在此 `return False` 早退，绕过了函数末尾的直下兜底。而无 root 的
                # Debian/Ubuntu arm64（含本仓镜像的 USER recorder）上 `apt update` 失败正是常态——它要写
                # /var/lib/apt/lists，而这一人群恰是新模块头声明的目标用户。现只去掉早退：保留「update
                # 失败就别白跑 apt install」的取舍（收进 else 分支），但让它与「apt install 失败」「apt 不存在」
                # 一样落到统一出口——先试官方直下，仍失败才给手动提示。
            else:
                result = subprocess.run(["apt", "install", "-y", "ffmpeg"], capture_output=True, timeout=300)
                if result.returncode == 0:
                    logger.debug("ffmpeg installation was successful using apt. Restart for changes to take effect.")
                    return True
                else:
                    logger.error(result.stderr.decode("utf-8", errors="replace").strip())
        except FileNotFoundError:
            logger.error("apt command not found, unable to install ffmpeg. Please manually install ffmpeg by yourself")
        except Exception as e:
            logger.error(i18n.tr("An error occurred while trying to install ffmpeg using apt: {e}", e=e))
    # 顺序判据：直下兜底**只能在** yum、apt 两条包管理器路径都试过且都没装上之后进行，不得颠倒——
    # apt/yum 天然给原生 arm64 构建且带发行版自己的签名链，完整性强度高于「运行期取官方公布的
    # SHA256」；直下只兜「拿不到包管理器」（轻量发行版/容器）或仓库里没有 ffmpeg 的情形。
    # 成功即 return True，与上面两条包管理器路径的返回形态一致；失败则继续落到下方手动安装提示。
    # master_allowed 由本模块的开关函数传入（同一份 FFMPEG_MASTER_ALLOWED 语义），新模块自身不读环境变量。
    # [历史注] 「apt 在位但 update 失败」同样属于「两条路径都试过且都没装上」，该分支已不再早退。
    if install_ffmpeg_linux_native(execute_dir, master_allowed=_master_source_allowed()):
        return True
    logger.error("Manual installation of ffmpeg is required. Please manually install ffmpeg by yourself.")
    return False


def install_ffmpeg() -> bool:
    # 根据当前平台选择对应的 FFmpeg 安装方法
    # 按 current_platform 分发到对应平台的安装器；未知平台仅记录不支持并返 False（不抛异常）。
    if current_platform == "Windows":
        return install_ffmpeg_windows()
    elif current_platform == "Linux":
        return install_ffmpeg_linux()
    elif current_platform == "Darwin":
        return install_ffmpeg_mac()
    else:
        logger.debug(
            i18n.tr(
                "ffmpeg auto installation is not supported on this platform: {current_platform}. Please install ffmpeg manually.",
                current_platform=current_platform,
            )
        )
    return False


# 包内 ffmpeg 目录是否应当前置到 PATH ——**主程序侧**判据的唯一事实源（W6，2026-09-22）。
# 孪生副本：`scripts/douyin_live_recorder_standalone.py` 里同名同语义函数（该文件按设计不 import
# src/，可独立单文件分发）。**改判据必须两处同改**，行为等价性由
# tests/test_ffmpeg_path_preference.py 的 TestTwinEquivalence 锁住。
# 返回 True = 维持既有行为（把包内目录前置）；False = 不前置，让系统 PATH 上已有的那份生效。
#
# 为什么要让位：full 包内置的 macOS ffmpeg 是 evermeet 的 **x86_64** 静态构建（上游不发布 arm64
#   构建，arm64 端点实测 404），在 Apple Silicon 上只能经 Rosetta 2 转译执行。而 main.py 原先
#   **无条件**前置，于是「已用 Homebrew 装了原生 arm64 ffmpeg」的用户会被包内那份遮蔽，白付转译
#   开销——重编码路径最明显（libx264 / libmp3lame），转译对纯 copy 拉流影响小、对软件编码影响大。
#
# 为什么判据保守（任一不成立即维持现状）：PATH 优先级是全局副作用，误判一次会让全部录制子进程改用
#   用户机器上的另一份 ffmpeg（版本/编译选项都可能不同）。故只在「darwin + arm64 + 包内目录存在 +
#   注入前的 PATH 上另有 ffmpeg + 那份不是包内自身」五条同时成立时才让位；Windows / Linux / Intel Mac
#   的行为逐字不变（Windows 的自动安装分支本身就靠前置生效，见模块头「PATH 优先级策略」段）。
def should_prepend_bundled_ffmpeg_dir(bundled_dir: str, current_path: str) -> bool:
    # 判据 1（平台门控必须用 sys.platform 字面量）：非 darwin 一律恒前置。
    # mypy 在 --platform linux / win32 下都会把该分支当常量处理，但不影响可达性判定
    # （本仓未开 warn_unreachable），故这里不写 `# type: ignore`。
    if sys.platform != "darwin":
        return True

    # 判据 2（架构）：只有 arm64 宿主才存在「包内是转译构建」这回事。
    # 已知边界：Python 解释器自身跑在 Rosetta 下时 platform.machine() 报 "x86_64"，
    # 判据不成立 → 维持现状前置。这是刻意选择的**漏判方向**（宁可继续用包内那份，
    # 也不要在架构信息不可信时改用系统那份）。
    if platform.machine().lower() != "arm64":
        return True

    # 判据 3：包内目录不存在时谈不上「遮蔽」，行为保持不变（照旧前置；后续 ffmpeg 查找
    # 自然落到系统 PATH，与改动前完全一致）。
    if not os.path.isdir(bundled_dir):
        return True

    # 判据 4：注入**前**的 PATH 上确实有一个可执行的 ffmpeg。必须用 current_path 而不是
    # 默认的 os.environ["PATH"]——调用点（main.py）正是在前置之前取好的快照，
    # 否则本函数会探测到「刚被自己前置进来的那一份」，判据恒成立、让位永不发生。
    system_ffmpeg = shutil.which("ffmpeg", path=current_path) if current_path else None

    # 判据 5：探到的这份不能就是包内那一份。用户把包内目录永久写进了自己的 PATH 时，
    # 「让位」只是不再前置、命中的仍是同一份 x86_64 构建——日志却会承诺原生 arm64，
    # 即自我遮蔽下的假绿。realpath 归一后再比目录前缀，覆盖符号链接（/usr/local/bin 常见）
    # 与嵌套落点两种形态。
    if system_ffmpeg:
        candidate_real = os.path.realpath(system_ffmpeg)
        bundle_real = os.path.realpath(bundled_dir)
        if candidate_real == bundle_real or candidate_real.startswith(bundle_real + os.sep):
            logger.debug(
                i18n.tr(
                    "FFmpeg PATH 优先级：Apple Silicon 上系统 PATH 探测到的 {system_ffmpeg} "
                    "就是包内目录自身，仍前置包内目录 {bundled_dir}（没有原生 arm64 构建可让位）",
                    system_ffmpeg=utils.mask_credentials(system_ffmpeg),
                    bundled_dir=utils.mask_credentials(bundle_real),
                )
            )
            return True
    else:
        logger.debug(
            i18n.tr(
                "FFmpeg PATH 优先级：Apple Silicon 上系统 PATH 未探测到 ffmpeg，"
                "仍前置包内目录 {bundled_dir}（包内为 x86_64 构建，需经 Rosetta 运行）",
                bundled_dir=utils.mask_credentials(os.path.realpath(bundled_dir)),
            )
        )
        return True

    # 五条判据全部成立：让位。只打印两个候选路径，不打印整条 PATH
    # （那会把用户全部个人目录写进会轮转留存的日志，超出排查所需）。
    logger.debug(
        i18n.tr(
            "FFmpeg PATH 优先级：让位于系统原生 ffmpeg {system_ffmpeg}，不再前置包内目录 "
            "{bundled_dir}（包内为 x86_64 构建，Apple Silicon 需经 Rosetta 转译）",
            system_ffmpeg=utils.mask_credentials(system_ffmpeg),
            bundled_dir=utils.mask_credentials(os.path.realpath(bundled_dir)),
        )
    )
    return False


def check_ffmpeg_installed() -> bool:
    # 检查 FFmpeg 是否已安装并可用
    try:
        # timeout 必带：ffmpeg 可执行档存在但卡住时（PATH 命中损坏/被占用的 ffmpeg、网络文件系统上的
        # 可执行档、杀毒软件拦截扫描等）subprocess.run 会无限阻塞，把整个启动流程挂死；版本探测是
        # 毫秒级操作，15 秒已远超正常耗时。startupinfo 抑制 Windows 无控制台形态下每次探测闪出的
        # 子进程窗口（判据见 _win_startup_info；本行是被启动流程调用最频繁的一处探测）。
        result = subprocess.run(
            ["ffmpeg", "-version"], capture_output=True, text=True, timeout=15, startupinfo=_win_startup_info()
        )
        version = result.stdout.strip()
        if result.returncode == 0 and version:
            return True
    # FileNotFoundError：系统 PATH 中无 ffmpeg 可执行文件，静默返回 False 触发自动安装；OSError 通常是
    # script_path/ffmpeg 残留了损坏目录但 PATH 找到的是它，提示删除重装以避免反复失败。
    except FileNotFoundError:
        pass
    except subprocess.TimeoutExpired:
        logger.warning(
            i18n.tr(
                "ffmpeg -version 执行超时（15 秒），按未安装处理: {ffmpeg_path}",
                ffmpeg_path=shutil.which("ffmpeg") or "unknown",
            )
        )
    except OSError as e:
        logger.warning(
            i18n.tr(
                "OSError occurred: {e}. ffmpeg may not be installed correctly or is not available in the system PATH.",
                e=e,
            )
        )
        logger.warning("Please delete the ffmpeg and try to download and install again.")
    except Exception as e:
        logger.error(i18n.tr("An unexpected error occurred: {e}", e=e))
    return False


def check_ffmpeg() -> bool:
    # 主入口：检查 FFmpeg，未安装则自动安装
    if not check_ffmpeg_installed():
        return install_ffmpeg()
    return True
