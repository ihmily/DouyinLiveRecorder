#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# FFmpeg master 滚动构建的 Windows 下载器（x86_64 / ARM64）
#
# 背景：用户给出的两个链接
#   https://fyhub.cn/FFmpeg/latest/ffmpeg-master-latest-win64-gpl.zip
#   https://fyhub.cn/FFmpeg/latest/ffmpeg-master-latest-winarm64-gpl.zip
# 是「枫源镜像」(fyhub.cn) 对 BtbN 的 GitHub「FFmpeg-Builds」仓库 master 分支
# 滚动构建（latest 别名）的国内镜像。命名拆解：
#   - win64       = Windows x86_64（Intel/AMD 64 位，绝大多数 PC）
#   - winarm64    = Windows ARM64（Surface / 骁龙 X 等 Windows on ARM 设备）
#   - gpl         = 含 GPL 编解码器的构建（x264/x265/libvpx 等）；另有 lgpl 变体不含
#   - master-latest = 取自 ffmpeg git master 的每日滚动构建（比 gyan.dev 的「release」
#     构建更新但更不稳定；且是滚动别名，上游每次出新构建内容即变，故不能把哈希常量钉死）
#
# 关键约束（实测，2026-09-22）：
#   fyhub.cn 对这两个直链返回「下载验证」HTML 页（200 + text/html，引用 vdf-worker.js 的
#   PoW 人机验证），普通脚本拿不到文件；其 .sha256 文档也返回 404。
#   真正可直接下载的同源上游是 BtbN GitHub release 直链（字节一致、无门控），
#   但同样不发布 latest 别名的 .sha256。
# 因此本模块的「正确下载方式」是（细则与 ID 见各函数注释）：
#   ① 按宿主架构选 win64 / winarm64；
#   ② 候选 [BtbN-GitHub, fyhub]，**顺序即优先级**：权威上游必排在镜像之前（镜像哪天直出文件也不得
#      取代上游），fyhub 用 Range 探针识别「挑战页」并跳过、落到无门控的 BtbN 上游（见 _probe / _candidate_urls）；
#   ③ 下载后强制「是不是真的 zip」形态校验，拒把验证页/错误页当产物（对齐 ffmpeg_install._is_valid_zip 前置）；
#   ④ 滚动构建无权威哈希文档，完整性只能 TOFU（首次信任），与 ffmpeg_install 降级分支同强度、不冒充「已校验」；
#      基准存在却读不出即**拒装**（SEV-2222，见 _tofu_verify_or_record）——这是本模块唯一一道完整性检查，不容静默失效；
#   ⑤ TOFU 基准按构建标识分文件，写新删旧只留 1 份（见 _prune_stale_master_baselines）。
#
# **默认关闭**（SEV-2218，2026-09-23 定稿）：本模块不是默认路径。ffmpeg_install 只在环境变量
#   FFMPEG_MASTER_ALLOWED 显式取真时才调用 download_ffmpeg_master()，默认跳过并各落一条
#   warning（开启 = 声明本次用的是未校验 TOFU 源；跳过 = 声明因未开启而未做兜底）。
#   理由：AGENTS.md「三类钉定/校验」② 的红线是「新增任何第二条 Windows 运行期下载源前必须先
#   满足『官方公布哈希』判据」，而本模块按上面 ④ 只有 TOFU 强度、不满足该判据，故只能以
#   「显式开启 + 默认关」的形态存在（与被删除的蓝奏云兜底同一处置口径）。
#
# 与 ffmpeg_install.py 的关系：不改动其既有完整性模型（gyan.dev 官方源 + 官方 SHA256 优先），
#   仅作为「Windows ARM64 无官方源」或「gyan.dev 不可达」时**需显式开启**的补充路径。

import hashlib
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import time
from collections.abc import Mapping
from pathlib import Path

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
# 探测挑战页只需 1 字节，给短超时：探针只判可达性、不取内容，5 秒已远超正常往返
# （实测毫秒级）。[历史注] 原值 20 与本注释相互矛盾——fyhub 被探成挑战页/超时是**常态**，
# 两候选串行即「无 ffmpeg 的机器首次启动」要多等 40 秒，故 2026-09-23 降到 5（MIN-2267）。
_PROBE_TIMEOUT = 5
# 连接级失败（DNS/连接重置/读取中断）的重试次数与退避。
_MAX_RETRIES = 3
_RETRY_BACKOFF = 2.0  # 每次退避翻倍：2s, 4s, 8s


class FfmpegDownloadError(Exception):
    # 下载链路统一异常基类；顶层安装入口只捕获它并转成 False + 日志，不向上抛。
    pass


class IntegrityError(FfmpegDownloadError):
    # 产物不是合法 zip，或 TOFU 哈希与已缓存基准不符（含基准存在但读不出）——拒绝写盘/安装。
    pass


class NetworkError(FfmpegDownloadError):
    # 重试耗尽后仍连不上 / 读取中断 / HTTP 错误。
    pass


# 宿主 Windows 架构 → fyhub/BtbN 的构建名后缀。
# 判据用 platform.machine() 字面量：arm64/aarch64 才走 winarm64，其余（AMD64/x86_64/
# 空串/未知）一律默认 x86_64——宁可装能跑的 x86_64（ARM 上经 x64 模拟），
# 也不要在架构信息不可信时误装 arm64 原生包导致无法启动。
def _windows_arch() -> str:
    machine = platform.machine().lower()
    if machine in ("arm64", "aarch64"):
        return "winarm64"
    return "win64"


# 同一构建名在两源下的候选直链，**列表顺序即优先级**：权威上游（BtbN GitHub）在前，
# 镜像（fyhub）在后——镜像既能替换产物也就能替换它自己的任何元数据，权威性严格弱于上游，
# 其价值只在「上游不可达」时体现，故只作兜底项（fyhub 被探成挑战页时会被自动跳过，
# 不会误导用户以为「源可用」）。
#   [历史注] 2026-09-23 SEV-2218 子项之前，用户点名的个人镜像排在前面。
def _candidate_urls(arch: str) -> list[str]:
    base = f"ffmpeg-master-latest-{arch}-gpl.zip"
    return [
        f"https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/{base}",
        f"https://fyhub.cn/FFmpeg/latest/{base}",
    ]


# 响应是否为「人机验证页 / 错误页」而非文件：Content-Type 是 html，或正文前若干字节
# 是 <!doctype / <html 形态即判为挑战页。后者比只看 Content-Type 更稳——
# 某些 CDN 对挑战页会误标 application/octet-stream，但首字节一定是 HTML 标签。
def _looks_like_html(response: requests.Response) -> bool:
    ctype = (response.headers.get("Content-Type") or "").lower()
    if "text/html" in ctype:
        return True
    try:
        first = next(response.iter_content(512), b"")
    except Exception:
        # 读不到首字节即内容不可信，判 True（是 HTML/坏页）。
        # [历史注] 2026-09-23 MIN-2267 之前此处返回 False（=「不是 HTML，放行」），把**读失败**
        # 当成「拿到的是文件」：流一断就误报探针 ok，随后 _stream_download 才发现问题，
        # 而这一次误判会让本可换源的候选被当成唯一可用源。
        return True
    text = first.lstrip()[:64].lower()
    return text.startswith(b"<!doctype") or text.startswith(b"<html")


# Range 探针：取首字节并据状态码/Content-Type 判定该候选源是否真的给文件。
# 返回 ("ok" | "challenge" | "http-error", response-or-None)——换源靠这个**字符串状态**驱动。
# 用 bytes=0-0 而非 HEAD：HEAD 在 fyhub 上返回 405（Method Not Allowed），
# 与 ffmpeg_install 处理 douyinliving CDN 的 405 同源——Range GET 才是可靠的探测手段。
#   [历史注] 2026-09-23 MIN-2267 删除了原有的 ChallengePageError 异常类：探测路径改向为上述
#   字符串状态后它全仓零引用、属死码，而留着会让读者以为存在「抛挑战页异常换源」这条链路。
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


# 由响应头推导构建标识（与 ffmpeg_install._build_identity 同口径）：无可用头时返回 ""，
# 退化为按 URL 基础名命名，避免 Windows 非法文件名。只用于 TOFU 缓存文件命名，
# 不是信任根（这些滚动构建本就没有权威哈希文档）。
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


# 流式下载（带重试与进度）：仅在连接级/读取级异常时重试，HTTP 4xx/5xx 直接失败。
# 复用 ffmpeg_install 的内存恒定分块写法；tmp 落盘后再做形态/哈希校验，避免把
# 半截文件当产物。
def _stream_download(url: str, zip_path: Path) -> tuple[str, int, Mapping[str, str]]:
    last_err: Exception | None = None
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            with requests.get(
                url, stream=True, timeout=(_CONNECT_TIMEOUT, _READ_TIMEOUT), allow_redirects=True
            ) as response:
                response.raise_for_status()
                total = int(response.headers.get("Content-Length", 0))
                build_id = _build_identity(response.headers)
                with tqdm(total=total, unit="B", unit_scale=True, ncols=100, desc="Downloading ffmpeg (master)") as t:
                    with open(zip_path, "wb") as f:
                        for chunk in response.iter_content(chunk_size=1024 * 64):
                            if not chunk:
                                continue
                            f.write(chunk)
                            _ = t.update(len(chunk))
                return build_id, total, response.headers
        except requests.HTTPError as e:
            # 4xx/5xx 不是重试能解决的（fyhub 验证页若漏判、或源真的 404）→ 直接抛。
            raise NetworkError(i18n.tr("ffmpeg master 下载 HTTP 错误: {e}", e=e)) from e
        except (requests.RequestException, ConnectionError) as e:
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
            if zip_path.exists():
                try:
                    zip_path.unlink()
                except OSError:
                    pass
            if attempt < _MAX_RETRIES:
                time.sleep(_RETRY_BACKOFF**attempt)
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


# 写新基准时修剪同前缀的旧基准（只保留本次这一份）：master-latest 是滚动别名，上游每发一次
# 新构建就多一个 .sha256，不修剪既让程序目录无界增长、又留下一堆不再参与校验的陈旧基准。
# 这里与 ffmpeg_install._record_zip_sha256 的做法刻意不同：那边的陈旧基准会被列进告警供用户
# 人工比对，故不删；本模块是**默认关闭**的 TOFU 路径，陈旧基准没有可比对价值（两侧哈希都无
# 权威来源），故直接修剪。
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


# 子进程控制台窗口抑制（L-15，2026-10-18）：与 src/ffmpeg_install._win_startup_info 同一语义的
# 孪生副本。本模块**不得**改为 import 那边那个函数——ffmpeg_install 在模块级
# `from src.ffmpeg_master_download import download_ffmpeg_master`，反向引用即构成循环导入
# （与本模块不 import ffmpeg_install、以及 ffmpeg_linux_download 的 master_allowed 由调用方
# 传参是同一族规避手法，见 ffmpeg_install 模块头「Linux 原生 ffmpeg 直下」那段注释）。
# 两份实现必须逐字同语义：改判据要同时改两处，等价性由
# tests/test_ffmpeg_install.py::TestChildConsoleStartupInfo::test_twin_helpers_agree_on_both_gate_states
# 在两个门控取值下逐一对齐（与 tests/test_ffmpeg_path_preference.py::TestTwinEquivalence 同一口径）。
# 平台门控取 `sys.platform == "win32"` 字面量并抽成模块级常量（Linux CI 可 monkeypatch 强制
# 走进 win32 分支，见 ffmpeg_install 侧同处的完整理由）；函数体不引用任何 Windows 专属符号，
# 故不需要 `# type: ignore`。
_HIDE_CHILD_CONSOLE = sys.platform == "win32"


def _win_startup_info() -> object | None:
    # 非 Windows 恒 None：subprocess 收到 startupinfo=None 等价于不传该实参，行为逐字不变。
    if not _HIDE_CHILD_CONSOLE:
        return None
    # 委托前置条件与孪生处逐字相同，理由完整写在 src/ffmpeg_install.py::_win_startup_info 头上
    # （直接首次 import video_postprocess 会撞 video_postprocess → main → src.notify →
    # video_postprocess 的循环导入并半程执行 main 的模块体；拿不到就退回改动前的闪窗行为）。
    # 本模块更极端：ffmpeg_install 在模块级 `from src.ffmpeg_master_download import
    # download_ffmpeg_master`，所以连「模块级 import video_postprocess」都不可能是选项——
    # 那条环在导入本模块的那一刻就会闭合。
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
            # SEV-2222：基准**存在**却读不出来 = 本机那份可信基准处于不可信状态，
            # 必须拒装。旧实现只 warning 后 return，调用方把 None 当成校验通过，于是
            # 「唯一一道完整性检查在磁盘异常时静默失效」（与本仓 MID-63/MID-68/MIN-19
            # 「不得用捕获异常后跳过让它变绿」同一族禁令）。只有「基准确实不存在」才走首次记账。
            # [历史注] 本段注释曾称与 ffmpeg_install._check_or_record_zip_sha256 的同形分支
            # 「刻意不同」（理由：那边前面还有官方哈希一道）——L-44（2026-10-02）复核认为
            # 该理由对降级分支不成立（官方文档不可达时那边 TOFU 同样是最后一道），两侧已
            # 统一收紧为拒装，不再存在口径分叉。
            # [为什么必须并捕 UnicodeDecodeError（M-06，2026-10-18）] 基准是**磁盘上可被外部
            # 改写的输入**：用户手工编辑、同步盘/压缩工具把它转成 UTF-8，都会让
            # read_text(encoding="ascii") 抛 UnicodeDecodeError（ValueError 子类，**不是** OSError），
            # 只捕 OSError 接不住。本模块接不住的代价比 Linux 姊妹侧更硬：顶层入口承诺「失败一律
            # 返回 False 不抛」，而调用方 download_ffmpeg_master 只并捕 (IntegrityError, OSError)，
            # 于是该异常会穿出 download_ffmpeg_master → install_ffmpeg_windows → check_ffmpeg
            # 直达启动流程（install_ffmpeg_windows 全程无 try），把「装不上」升级成「起不来」。
            # 归一成 IntegrityError 后走的就是本分支既有的「删包 + 拒装」路径，失败方向不变，
            # 只是让它按 SEV-2222 的口径**带着「请人工核对或删除 {hash_file} 后重试」指引**失败。
            # 姊妹形态的同口径修法见 src/ffmpeg_linux_download.py::_verify_archive 与
            # src/ffmpeg_install.py::_check_or_record_zip_sha256（L-12，与本条一并修、注释互相点名）。
            # 需要 as 绑定取 type(e)/e，故按 AGENTS 的 except 约定回退加括号形态。
            # 回归锁：tests/test_ffmpeg_install.py::TestMasterBaselineDecodeGuard
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


# 顶层下载+安装入口：返回 True 表示成功把 bin 落到 dest_dir/ffmpeg。
# 失败一律返回 False（不抛），与 ffmpeg_install.install_ffmpeg_windows 的契约一致，
# 由调用方决定提示用户手动安装。
# [MIN-2266⑤] 该承诺此前只兑现了一半：_stream_download 仅捕 requests 系异常，
# open(zip_path, "wb") 的 OSError（磁盘满 / 无权限 / 路径失效）会一路穿出
# except FfmpegDownloadError，传到 install_ffmpeg_windows() → 启动期 check_ffmpeg()。
# 故下面的下载段与完整性段都额外并捕 OSError，归一成 False（并清掉半截产物）。
def download_ffmpeg_master(dest_dir: str, arch: str | None = None) -> bool:
    arch = arch or _windows_arch()
    zip_path = Path(dest_dir) / f"ffmpeg_master_{arch}_temp.zip"
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

    try:
        build_id, _total, _headers = _stream_download(chosen_url, zip_path)
    except (FfmpegDownloadError, OSError) as e:
        # OSError 分支见上方 MIN-2266⑤：写盘失败（磁盘满 / 无权限 / 路径失效）属「拿不到产物」，
        # 与网络失败同级，一律归一成 False，不得穿出「失败不抛」的契约。半截文件必须删掉。
        _discard_master_zip(zip_path)
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
    try:
        with tempfile.TemporaryDirectory() as tmp_dir:
            unzip_file(zip_path, tmp_dir, delete=False)
            bin_dir = None
            for root, _dirs, files in os.walk(tmp_dir):
                if os.path.basename(root) == "bin" and "ffmpeg.exe" in files:
                    bin_dir = root
                    break
            if bin_dir is None:
                logger.error("ffmpeg.exe not found in master package")
                return False
            target = Path(dest_dir) / "ffmpeg"
            if target.exists():
                shutil.rmtree(target)
            shutil.copytree(bin_dir, target)
    except Exception as e:
        logger.error(i18n.tr("ffmpeg master 解压失败: {type_name}: {e}", type_name=type(e).__name__, e=e))
        return False
    finally:
        _discard_master_zip(zip_path)

    # 与 download_ffmpeg_official 一致：安装成功后把 bin 目录前置注入 PATH，再用 `ffmpeg -version`
    # 真跑一次验证（returncode==0 才认成功）。该前置只发生在「系统本无可用 ffmpeg」的自动安装分支，
    # 不会与 W6 的 PATH 优先级判据冲突（W6 在 main.py 侧、注入前取快照，本处注入在其之后）。
    os.environ["PATH"] = str(target) + os.pathsep + (os.environ.get("PATH") or "")
    try:
        # L-15：本行真跑刚下载的 ffmpeg.exe，Windows 无控制台形态（pythonw / 冻结 console=False）
        # 下不传 startupinfo 会闪出一个控制台窗口；判据见 _win_startup_info。
        rc = subprocess.run(["ffmpeg", "-version"], capture_output=True, timeout=30, startupinfo=_win_startup_info())
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
