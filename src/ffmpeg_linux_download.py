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

import os
import platform
import re
import shutil
import stat
import subprocess
import tarfile
import tempfile
import time
from pathlib import Path
from typing import Any

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
    last_err: Exception | None = None
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            with requests.get(archive_url, stream=True, timeout=(_CONNECT_TIMEOUT, _READ_TIMEOUT)) as response:
                response.raise_for_status()
                with open(archive, "wb") as sink:
                    for chunk in response.iter_content(chunk_size=1024 * 64):
                        if chunk:
                            sink.write(chunk)
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
            last_err = e
            if archive.exists():
                try:
                    archive.unlink()
                except OSError:
                    pass
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
    resolved = arch or _linux_arch()
    url = _asset_url(resolved)
    dest = Path(dest_dir)
    ffmpeg_dir = dest / "ffmpeg"
    archive = dest / "ffmpeg_linux_native_temp.tar.xz"
    logger.debug(
        i18n.tr(
            "Linux 包管理器未提供 ffmpeg，改试官方月末构建直下: {arch} - {masked_url}",
            arch=resolved,
            masked_url=_mask(url),
        )
    )
    try:
        official = _fetch_asset_digest(url)
        if not _download(url, archive):
            return False
        if not _verify_archive(archive, official, dest, url, master_allowed):
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
        if archive.exists():
            try:
                archive.unlink()
            except OSError:
                pass

    os.environ["PATH"] = str(ffmpeg_dir) + os.pathsep + (os.environ.get("PATH") or "")
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
