# -*- coding: utf-8 -*-
# 启动期陈旧字节码缓存清理（源码直跑形态的外围功能）。
#
# 要闭合的故障类：以「解压覆盖」方式升级源码包时，复制工具通常保留源文件 mtime；若模块字节数
# 恰好也没变，CPython 基于 (mtime, size) 的失效判定会认为缓存新鲜，静默沿用旧 .pyc——表现是
# 「改了代码却还在跑旧逻辑」，且任何门禁/日志都不指向缓存。本模块用源码内容哈希做基线，正是为了
# 在这种情形下仍能判定「源码变过」。
#
# 三条形态约束（失效路径不同，缺一不可）：
# - 触发一次即止：基线落 logs/.pyc_stamp，源码与版本都没变时零删除，健康轮次不付重编译成本，
#   也避免 CLI/GUI 子进程/Web 三个入口互相删掉对方刚生成的缓存。
# - 正向白名单：只回收 Python 真正会写缓存的位置（程序目录顶层 + src/ 下直接含 .py 的目录），
#   不用「递归排除若干目录名」的反向写法——漏登记一个新目录就会删到用户数据或运行期产物。
# - 全程不抛：本模块在启动早期运行，任何异常都不得让录制主流程起不来。

import hashlib
import os
import sys
from dataclasses import dataclass
from pathlib import Path

import i18n
from src.logger import logger

# 缓存目录名（CPython 固定写死，逐字相等才认定为目标）
PYCACHE_DIR_NAME = "__pycache__"

# 只回收这两种字节码扩展名；缓存目录里的其它内容一律留着（宁可删不净并告警，也不越界删不认识的文件）
BYTECODE_SUFFIXES = (".pyc", ".pyo")

# 基线文件相对程序目录的位置。选 logs/ 而非程序目录根：该目录已在 build_exe 的
# RUNTIME_ARTIFACT_DIR_NAMES、.gitignore、.dockerignore 三处排除，新增运行期文件不必再改
# 第四处；Docker 下它是宿主机挂载卷，镜像重建后仍在，正好让「源码换了但镜像标签没变」也被判出。
STAMP_DIR_NAME = "logs"
STAMP_FILE_NAME = ".pyc_stamp"

# 哨兵内容格式：`<版本号>|<源码树内容哈希>`，一条两字段，故意不用 JSON（读失败即视为无基线，无需解析异常分类）
_STAMP_SEPARATOR = "|"

# 冻结发行包形态判定：模块级常量供用例强制置真，使该分支在任意主机上真实执行。
# PyInstaller 的字节码在 PYZ/exe 内，_internal/ 下没有 __pycache__，而 _app_root() 冻结后
# 指向 _internal——遍历它毫无收益且方向错误。
_IS_FROZEN = bool(getattr(sys, "frozen", False))


@dataclass(frozen=True)
class PurgeResult:
    # 清理结论，供用例断言与日志取材（triggered = 本轮是否判定为「源码/版本已变」）
    triggered: bool
    removed_dirs: int
    freed_bytes: int
    errors: int


def _stamp_path(app_root: Path) -> Path:
    # 基线文件路径：程序目录下的 logs/.pyc_stamp
    return app_root / STAMP_DIR_NAME / STAMP_FILE_NAME


def _scan_dirs(app_root: Path) -> list[Path]:
    # 枚举扫描根 = 程序目录顶层（仅当它直接含 .py）+ src/ 子树里每个直接含 .py 的目录。
    # 顶层刻意不递归：程序目录下的 downloads/ logs/ tests/ scripts/ node/ 都可能藏 .py（用户脚本、
    # 临时验证脚本、正式维护脚本），它们的缓存与本次运行的导入无关，一律不属于清理范围。
    dirs: list[Path] = []
    if any(app_root.glob("*.py")):
        dirs.append(app_root)
    src_root = app_root / "src"
    if src_root.is_dir():
        # os.walk 默认 followlinks=False：src 下若出现指向别处的链接目录，不跟随即不进入，
        # 这条默认值正是白名单不被绕过的关键，改动它等于打开越界删除的口子。
        for root, subdirs, files in os.walk(src_root):
            if any(name.endswith(".py") for name in files):
                dirs.append(Path(root))
            subdirs[:] = [name for name in subdirs if name != PYCACHE_DIR_NAME]
    return dirs


def _tree_fingerprint(app_root: Path, scan_dirs: list[Path]) -> str:
    # 源码树内容哈希：按「相对路径 + 文件字节」顺序喂进同一个 sha256。
    # 用内容而非 (size, mtime)：见模块头；全树哈希仅毫秒级，远低于一轮重编译的成本。
    hasher = hashlib.sha256()
    for directory in scan_dirs:
        for source in sorted(directory.glob("*.py")):
            hasher.update(f"{source.relative_to(app_root).as_posix()}\n".encode("utf-8"))
            hasher.update(source.read_bytes())
    return hasher.hexdigest()


def _read_stamp(app_root: Path) -> tuple[str, str] | None:
    # 读基线；文件缺失、读不动、格式不合一律回 None——调用方把 None 当作「无法证明缓存新鲜」，
    # 保守动作是清一次（只付一轮重编译），而不是静默放弃整个功能。
    try:
        text = _stamp_path(app_root).read_text(encoding="utf-8")
    except OSError, UnicodeDecodeError:
        # 必须带 UnicodeDecodeError：read_text(encoding="utf-8") 在基线被写坏或被同步工具
        # 转成非 UTF-8 时抛的是 UnicodeDecodeError（ValueError 子类，不属 OSError），不捕获
        # 会穿透本函数，违反模块头的「全程不抛」硬约束。
        return None
    version, separator, digest = text.strip().partition(_STAMP_SEPARATOR)
    if not separator or not version or not digest:
        return None
    return version, digest


def _write_stamp(app_root: Path, version: str, digest: str) -> bool:
    # 原子写基线：同目录临时文件 + os.replace（后者只看父目录写权限，目标已存在也安全覆盖）。
    # 不复用 src.config_io._atomic_write_text：那条路径持 main.file_update_lock（录制引擎锁体系），
    # 而本模块会被 GUI 进程与录制子进程各自加载，两类锁不得混用。
    target = _stamp_path(app_root)
    temp = target.with_name(f"{target.name}.{os.getpid()}.tmp")
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        temp.write_text(f"{version}{_STAMP_SEPARATOR}{digest}", encoding="utf-8")
        os.replace(temp, target)
    except OSError as e:
        logger.warning(
            i18n.tr(
                "字节码缓存基线写入失败(下轮仍会清理): {type_name}: {err}",
                type_name=type(e).__name__,
                err=e,
            )
        )
        # 半写的临时文件不留给下一轮（失败本身已告警，这里静默尽力）
        try:
            temp.unlink()
        except OSError:
            pass
        return False
    return True


def _purge_cache_dir(cache: Path) -> tuple[int, int, int]:
    # 处理一个 __pycache__ 目录，返回 (是否整体删除 0/1, 释放字节, 失败次数)。
    # 逐文件删而非 shutil.rmtree：扩展名白名单在此生效；删不净时能精确报出是哪一个，
    # 而不是让 ignore_errors 把「没删掉」抹成零信息。
    freed_bytes = 0
    errors = 0
    for entry in sorted(cache.glob("*")):
        if entry.suffix not in BYTECODE_SUFFIXES:
            continue
        try:
            # 先取尺寸再删：删完就再也问不到了（日志里的「释放多少」必须是实测量，不得估算）
            if entry.is_file():
                freed_bytes += entry.stat().st_size
            entry.unlink()
        except OSError as e:
            # 目录形态在 Windows 抛 PermissionError、POSIX 抛 IsADirectoryError，同属 OSError → 两侧同分支
            errors += 1
            logger.warning(
                i18n.tr(
                    "字节码缓存文件删除失败(跳过): {name} - {type_name}: {err}",
                    name=entry.name,
                    type_name=type(e).__name__,
                    err=e,
                )
            )
    removed = 0
    try:
        # 仍有非字节码残留时 rmdir 自然抛非空错误，落到下面的告警分支——不会误删不认识的内容
        cache.rmdir()
        removed = 1
    except OSError as e:
        errors += 1
        logger.warning(
            i18n.tr(
                "字节码缓存目录未删净(跳过): {name} - {type_name}: {err}",
                name=cache.name,
                type_name=type(e).__name__,
                err=e,
            )
        )
    return removed, freed_bytes, errors


def _purge(root: Path, version: str) -> PurgeResult:
    scan_dirs = _scan_dirs(root)
    digest = _tree_fingerprint(root, scan_dirs)
    baseline = _read_stamp(root)
    # 「源码/版本没变」必须是被证明的，不是被假定的：基线缺失或格式不合都算变过
    if baseline == (version, digest):
        return PurgeResult(triggered=False, removed_dirs=0, freed_bytes=0, errors=0)

    removed_dirs = 0
    freed_bytes = 0
    errors = 0
    for directory in scan_dirs:
        cache = directory / PYCACHE_DIR_NAME
        if not cache.is_dir():
            continue
        one_removed, one_freed, one_errors = _purge_cache_dir(cache)
        removed_dirs += one_removed
        freed_bytes += one_freed
        errors += one_errors

    # 无论删得净不净都写新基线：否则一个删不掉的缓存会让每次启动重跑整轮清理（风暴式重复告警）
    stamp_written = _write_stamp(root, version, digest)
    if not stamp_written:
        errors += 1

    if removed_dirs:
        # 只在真删了东西时说话：健康轮次与「无缓存可删」的首轮都不该产生 INFO 噪声
        logger.info(
            i18n.tr(
                "源码或版本已变化，已清理 {count} 个字节码缓存目录（释放 {freed_kb} KB）",
                count=removed_dirs,
                freed_kb=freed_bytes // 1024,
            )
        )
    return PurgeResult(triggered=True, removed_dirs=removed_dirs, freed_bytes=freed_bytes, errors=errors)


def purge_stale_bytecode_caches(app_root: str | Path, version: str, enabled: bool = True) -> PurgeResult:
    # 启动期唯一入口：由 main() 在读完配置后调用。开关关闭与冻结发行包都在此早退，保证
    # 「零 I/O」（不遍历、不哈希、不读写基线）；关闭态不得只变成「遍历后什么都不删」。
    if not enabled or _IS_FROZEN:
        return PurgeResult(triggered=False, removed_dirs=0, freed_bytes=0, errors=0)
    try:
        return _purge(Path(app_root), version)
    except (OSError, UnicodeDecodeError) as e:
        # 兜住遍历/哈希本身（含覆盖进行中的读文件竞态）与基线编码损坏：外围功能不得把一次
        # I/O 故障升级成启动失败。
        logger.warning(
            i18n.tr(
                "字节码缓存清理未完成(忽略): {type_name}: {err}",
                type_name=type(e).__name__,
                err=e,
            )
        )
        return PurgeResult(triggered=False, removed_dirs=0, freed_bytes=0, errors=1)
