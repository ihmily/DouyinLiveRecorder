#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import hashlib
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from collections.abc import Mapping
from pathlib import Path

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
# 位置取「ffmpeg_master_download 之前」而非其后：isort 按模块名字典序排（ffmpeg_linux_download <
# ffmpeg_master_download），插在下方会直接让 `isort --check-only` 红。
from src.ffmpeg_linux_download import install_ffmpeg_linux_native

# Windows ARM64 原生构建 / gyan.dev 不可达时的兜底下载器：BtbN master 滚动构建
# （上游不公布 latest 别名的 SHA256，只有 TOFU）。**默认不调用**——须 FFMPEG_MASTER_ALLOWED
# 显式取真才走该路径，判据与理由见 _master_source_allowed() 与 install_ffmpeg_windows()。
# 本模块不 import ffmpeg_install，故此处单向引入无循环依赖风险。
from src.ffmpeg_master_download import download_ffmpeg_master

# 应用根目录复用 src.logger 公开导出的 script_path（等价原私有 _app_root() 的返回值）
from src.logger import script_path
from src.utils import unzip_file

# FFmpeg 自动安装模块 - 跨平台 FFmpeg 自动检测与安装
#
# 职责：检测系统是否已安装 ffmpeg（check_ffmpeg_installed），未安装则按平台自动拉取并安装——
#   Windows 默认只有官方源 gyan.dev 一条自动路径（第二条源默认关闭，见「Windows 下载源现状」段），
#   macOS 走 Homebrew，Linux 走 yum/apt。
# 安装落点：execute_dir（冻结后指向 _internal/，与运行时资源同目录），装好后把 ffmpeg 目录
#   前置注入 os.environ["PATH"]，使同进程后续 subprocess 调用 `ffmpeg` 能直接命中。
# 校验约定：所有安装路径最后都跑一次 `ffmpeg -version`，returncode==0 才认成功，否则报错并返回 False。
# 设计取舍：安装失败只返回 False、不抛异常（由调用方决定提示用户手动安装），避免中断主程序启动。
#
# 完整性模型（P-1，2026-09-22 起）：**权威校验优先、TOFU 只作显式降级的兜底**。
#   ① 下载前向 gyan.dev 取官方公布的 <zip URL>.sha256 文档，与本地实算哈希比对——不符即拒绝安装；
#   ② 只有「取不到官方文档」（网络失败 / 非 200 / 文档形态变更）时才退回旁路基准 TOFU，
#      并 logger.warning 将降级显式写进日志。
#   为什么取文档而不是把哈希常量钉进源码：下载的是**滚动**地址，钉常量会在上游发新版后
#   永久失败（即历史坑 MID-59「自动安装永久死路」的成因）；取文档则每次都对应当前构建。
#   为什么 TOFU 不足以作为唯一防线：首次安装那一次没有任何可比对的期望值，
#   而那正是供应链投毒最有价值的窗口（发布后第一批用户必然命中）。
#   本模块属 AGENTS.md「三类钉定/校验」中的第②类（运行期自动安装，单机面），
#   与 build_exe.py 的发布期钉定（分发面）、utils._JS_SHA256_EXPECTED 的签名脚本层互不覆盖。
#
# Windows 下载源现状（2026-09-23 起）：gyan.dev 是**默认且唯一**的自动路径；失败且未开启
#   FFMPEG_MASTER_ALLOWED 时只给出手动安装提示（见 install_ffmpeg_windows）。
#   第二条源 BtbN master 滚动构建（src/ffmpeg_master_download.py）因上游不为 latest 别名公布
#   .sha256、只能落 TOFU，不满足第②类的准入判据，故显式门控且默认关闭；开启与跳过两条分支
#   都各落一条 warning，不静默。
#   [历史注] 2026-09-22 蓝奏云个人网盘兜底整体删除（直链需爬分享页内联签名、且无独立可信来源
#   可比对）；同日 master 源曾默认开启，2026-09-23 按 SEV-2218 收为默认关闭。
#
# PATH 优先级策略（W6，2026-09-22 起）：包内 ffmpeg 目录是否前置由
#   should_prepend_bundled_ffmpeg_dir() 单点裁决（判据、后果与日志口径见该函数注释）。
#   本模块自身的「安装成功后前置注入 PATH」（Windows 官方源一处）**不在**该判据范围内：
#   它只发生在「系统里本来就没有可用 ffmpeg」的自动安装分支，且仅 Windows 分支可达，
#   让位判据在 macOS/Linux 安装路径（brew / yum / apt）上根本不执行。
#   [历史注 2026-10-03] 上句「仅 Windows 分支可达」在 Windows-only 自动下载时代为真、原文照留，本批
#   Linux arm64 支持落地后已被证伪：Linux 直下分支（src/ffmpeg_linux_download.install_ffmpeg_linux_native
#   把 ffmpeg/ffprobe 落进 execute_dir/ffmpeg/ 之后）同样就地前置 `os.environ["PATH"]`，注入点也在
#   「安装后验证」之前，故验证失败（`ffmpeg -version` 抛异常或返非零）时留下的正是「跑不起来的落件 +
#   不回滚的 PATH」——与下面两条 Windows 注入点（本模块 install_ffmpeg_windows、
#   src/ffmpeg_master_download.py）「先注入再校验，校验失败也保留注入」的既有取舍一字不差，
#   本批刻意不改该取舍（与 AGENTS.md「包内 ffmpeg 的 PATH 前置在 Apple Silicon 上必须「让位」（W6）」
#   条目里「Windows/Linux/Intel Mac 行为逐字不变」的口径同源——本批改的只是注入点数量，不是让位判据）。
#   因此「安装成功后前置注入 PATH」现有**三处**（Windows 官方源 / Windows master 兜底 / Linux 直下），
#   不再只有一处；让位判据本身不变——仍只在 darwin+arm64 生效，Linux 上
#   should_prepend_bundled_ffmpeg_dir() 恒 True，所以下一次启动会命中上一次直下的那份、不会每轮重下。


current_platform = platform.system()
execute_dir = script_path  # 冻结后指向 _internal/，与 __file__ 定位的资源收敛到同一处
# 安装时把新 ffmpeg 目录前缀拼回系统原 PATH；运行期 PATH 可能已被修改，先快照原始值避免重复嵌套。
current_env_path = os.environ.get("PATH")
# 安装目标子目录：解压后 ffmpeg 可执行文件平铺位于 execute_dir/ffmpeg/ffmpeg.exe（L-42，
# 2026-10-02 注释更正：原注释称 execute_dir/ffmpeg/bin/，与 copytree 平铺解压的实际布局不符，
# PATH 注入用的正是本目录、与实际一致）。
ffmpeg_path = os.path.join(execute_dir, "ffmpeg")


# 下面两个薄封装：实现已于 2026-09-18（CR-11）下沉到 src.utils，保留本模块别名供既有调用点与测试
# 继续引用（与 spider._is_safe_http_url 同一处置）。原状是两处逐字重复、node_install 那份还只判
# exists——打补丁必漏一处，故收敛到唯一实现。
# _sha256_of_file 分块读取：整读几百 MB 二进制会瞬时占用大量内存，分块保持内存恒定（H-1）。
def _sha256_of_file(path: str | Path) -> str:
    return utils.sha256_of_file(path)


def _is_valid_zip(path: str | Path) -> bool:
    return utils.is_valid_zip(path)


# 子进程控制台窗口抑制（L-15，2026-10-18）：`ffmpeg -version` 这类探测在 Windows 的无控制台形态
#   （pythonw.exe 跑 gui.py、冻结 console=False 的 exe）下每次都会闪出一个黑色控制台窗口——
#   子进程默认继承"创建控制台"的行为，而本模块的探测发生在启动期，用户看到的就是"一闪而过的窗口"。
#   判据与实现一律复用 src/video_postprocess.get_startup_info（STARTUPINFO + STARTF_USESHOWWINDOW，
#   录制链的 ffmpeg 调用早已用它），**不得**在本模块再写一份 STARTUPINFO 构造（F-01 同族：
#   同一件事只允许一个定义点；孪生的第二份在 src/ffmpeg_master_download.py，见该处注释）。
# 平台门控形态：判据抽成模块级常量 `_HIDE_CHILD_CONSOLE` 而不是就地写 `if sys.platform != "win32"`，
#   是为了让 Linux CI 也能**真走进** win32 分支（AGENTS「平台专属分支的测试不得靠 skipif 让 CI 跳过」，
#   与 src/ffmpeg_proc.py 的 `_QUIT_VIA_STDIN` 同一手法）；常量值本身仍是 sys.platform 字面量比较，
#   mypy 各平台目标下都只会把它当普通 bool——本函数不引用任何 Windows 专属符号（STARTUPINFO 藏在
#   get_startup_info 内部，其返回型已是跨平台的 object | None），故**不需要** `# type: ignore`
#   （加了反而在另一侧触发 basedpyright reportUnnecessaryTypeIgnoreComment）。
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
    # 委托前置条件：① src.video_postprocess 已在 sys.modules（它的模块体已跑完，或被测试用假模块占位），
    # 或 ② main 已在 sys.modules（正常入口顺序——main.py 在模块级就 `from src.video_postprocess import (...)`）。
    # 两者都不成立时**必须**直接返 None：那时这句 from-import 会**首次**执行 video_postprocess，而它顶层
    # `import main` → main → src.notify 的模块级 `from src.video_postprocess import get_startup_info`
    # 命中尚未跑完的 video_postprocess → ImportError（2026-10-18 由本文件 TestChildConsoleStartupInfo
    # 实测抓出，形态 "cannot import name 'get_startup_info' from partially initialized module"，
    # 7 条既有 download/探测用例当场变红）。除了报错，那次失败的导入还会**半程执行 main 的模块体**
    # （含 SetConsoleOutputCP(65001)），污染整个宿主进程。本模块对「可选加固不得打断主流程」早有口径
    # （见 _fetch_official_sha256：一次网络故障不得把安装打成异常），同一条判据落在这里：
    # 拿不到就退回改动前的行为（闪一个控制台窗口），绝不让探测/安装失败。
    if "src.video_postprocess" not in sys.modules and "main" not in sys.modules:
        return None
    from src.video_postprocess import get_startup_info

    return get_startup_info(os.name)


# 校验已下载 zip 的 SHA256（trust-on-first-use 模型）：
# - 首次下载完成后把哈希写到旁路文件
# - 再次下载/校验时若旁路文件存在则比对，不一致则拒绝安装
#
# MID-59（避免「自动安装永久死路」）：旁路文件**按构建标识命名**而不是按滚动 URL 的固定 zip 名——
#   gyan.dev 的 ffmpeg-release-essentials.zip 是滚动地址、上游每次出新构建内容（SHA）必变，旧命名
#   _ffmpeg_official.zip.sha256 一旦记录某构建，下次自动安装拿到新构建就**永远不等** → 官方源拒绝 →
#   用户只剩一行 logger.error 和「请手动安装 ffmpeg」。按构建标识（响应头 Last-Modified / ETag /
#   Content-Length 的摘要）命名后，「版本轮转」表现为「为新构建记录新基准」、「同一构建内容变了」仍
#   是硬失败——篡改检测强度不降。（默认下 gyan.dev 是唯一自动路径，此「死路」论断成立；用户自开 master
#   开关时不成立，而那时他已看过写明 TOFU 强度的 warning。）
#   [历史注] 旧版本此处把失败链写成「官方源拒绝 → 转蓝奏云 → 蓝奏云亦拒绝」，该兜底源于 2026-09-22 删除，
#   链尾现为「官方源拒绝 → 直接只剩手动安装」。
#
# 防护强度边界（勿据此高估）：
#   1) 本机制不能消除 CDN 投毒（首次下载始终是 trust-on-first-use），只阻断「已缓存 zip 被静默
#      替换」这条重安装路径；P-1 之后优先走官方哈希文档，TOFU 只在取不到文档时才生效，已收窄；
#   2) 旁路文件与 zip 同在 execute_dir（冻结后为 _internal/），能写该目录者可同时替换产物与基准
#      文件，故其强度**等同目录权限**，不是独立的信任根；
#   3) 官方哈希文档（_fetch_official_sha256）与产物**同主机、同一 HTTPS 通道**，期望值与实际文件
#      同源，故它只是一次**同源一致性校验**（防传输截断、防 CDN/代理缓存污染、防把挑战页当产物），
#      **不构成来源认证**——宿主或 CDN 被整体替换时，文档与产物会被一并换掉，校验归零。
#      gyan.dev 不提供 detached 签名，故 Windows 运行期目前只能到这一档；真要加来源认证得换一个
#      「文档与产物异源」的取法（对比 src/node_install.py 刻意换宿主取 SHASUMS256.txt 的做法，
#      以及 build_exe.py 的发布期钉定，见 AGENTS.md「三类钉定/校验」②）。
_FFMPEG_HASH_FILE = "_ffmpeg_official.zip.sha256"  # 旧版（不随构建轮转）命名，仅作只读兼容
_HASH_SUFFIX = ".zip.sha256"

# 官方哈希文档的后缀（gyan.dev 对每个构建产物都公布 `<产物名>.sha256`，内容就是裸 64 位十六进制）。
# 与上面的 _HASH_SUFFIX（本地旁路基准文件名的后缀，含 .zip）刻意不同名，勿混用。
_OFFICIAL_DOC_SUFFIX = ".sha256"
# 哈希文档只有 64 字节，用与 300MB 压缩包相同的 30s 超时会在上游故障时把启动拖慢一倍；
# 取不到即降级为 TOFU，不值得为它多等。
_OFFICIAL_DOC_TIMEOUT_SECONDS = 15
# 官方文档的合法形态：整篇剥掉空白后必须**正好**是 64 位小写十六进制。
# 判据必须严格：gyan.dev 在前置代理/WAF 介入时会回 200 + 一段 HTML 挑战页，
# 「长度看着像」的宽松判定会把挑战页当成期望哈希，从而把可用源判成篡改。
_SHA256_RE = re.compile(r"[0-9a-f]{64}")


# 把官方哈希文档正文解析为小写十六进制摘要；形态不符（HTML 错误页、截断、含文件名前缀等）返回 ""。
def _parse_official_sha256(text: str) -> str:
    candidate = text.strip().lower()
    return candidate if _SHA256_RE.fullmatch(candidate) else ""


# 向上游取官方公布的 SHA256。返回 ""=未取得（调用方据此显式降级到 TOFU）。
# 失败绝不抛异常：本函数的定位是「能拿到就更强、拿不到就退回原有防线」，
# 若让网络故障把整条安装链路打成异常，等于用一个可选加固换掉本来能成功的自动安装。
#
# 2026-09-22 实测形态：文档端点回 303 → /ffmpeg/builds/packages/ffmpeg-<ver>-essentials_build.zip.sha256，
# 最终正文是**裸 64 位小写十六进制**（无换行、无文件名），与滚动别名两个端点互相印证。
# 因此这里**必须保持 requests 的默认 allow_redirects=True**：把它改成 False（或换成 HEAD）
# 会永远只看到 303 + 空正文 → 恒降级为 TOFU，且日志里只是一句「未取得文档」，极易误判成上游故障。
def _fetch_official_sha256(doc_url: str) -> str:
    try:
        with requests.get(doc_url, timeout=_OFFICIAL_DOC_TIMEOUT_SECONDS) as response:
            response.raise_for_status()
            text = response.text
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


# 把本次实算哈希写进旁路基准（TOFU 的「记录」侧，原先内联在 _check_or_record_zip_sha256 里）。
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
        # [为什么必须并捕 UnicodeDecodeError（L-12，2026-10-18）] 与 M-06
        # （src/ffmpeg_master_download.py::_tofu_verify_or_record）同一形态：基准是磁盘上可被
        # 外部改写的输入，用户手工编辑或同步盘把它转成 UTF-8 后，read_text(encoding="ascii")
        # 抛的是 UnicodeDecodeError（ValueError 子类，**不是** OSError），只捕 OSError 接不住。
        # 本模块的代价与 master 侧不同但同样是「检查失效」：异常穿出后被 download_ffmpeg_official
        # 的 catch-all `except Exception` 归成一句泛化的「安装失败」，于是 ① 下面那条 fail-closed
        # 分支（删包 + 点名「请人工核对或删除 {hash_file} 后重试」）整个被跳过，用户失去自救入口；
        # ② 几百 MB 的 ffmpeg_official_temp.zip 不会被删（该分支的 unlink 同样被跳过）。
        # 姊妹模块 ffmpeg_linux_download.py::_verify_archive 的同一修法（含「为什么保留 .lower()」
        # 的强度说明）见其 except 元组处的注释；master 侧见 M-06。三处一律并捕，不再分叉。
        # 需要 as 绑定取 type(e)/e，故按 AGENTS 的 except 约定回退加括号形态。
        # 回归锁：tests/test_ffmpeg_install.py::TestOfficialBaselineDecodeGuard
        # ::test_non_ascii_baseline_refuses_and_unlinks。
        except (OSError, UnicodeDecodeError) as e:
            # L-44（2026-10-02，对齐 ffmpeg_master_download 的 SEV-2222 口径）：基准**存在**
            # 却读不出来 = 本机那份可信基准处于不可信状态，必须拒装（fail-closed）。旧实现
            # warning 后 return True 放行——唯一一道完整性检查在磁盘异常时静默失效（官方
            # 文档不可达时 TOFU 就是最后一道，与 master 侧没有区别）。触发需「官方文档
            # 不可达 ∧ 基准损坏 ∧ CDN 投毒」三重叠加，属防御纵深收紧，非行为回归。
            # 返回 False 走调用方既有「删包且不执行」路径；用户删掉该基准后重试即恢复 TOFU 记账。
            # [历史注] master 侧同形分支注释曾称两侧「刻意不同」（那边 TOFU 是唯一一道）——
            # 该理由对本模块的降级分支同样成立，故统一收紧。
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


# 删除本次下载的临时压缩包（L-13，2026-10-18）。幂等：不存在即什么都不做。
# 为什么删不掉要**静默吞掉** OSError、不留日志：本函数的唯一场景是「系统 PATH 里没有 ffmpeg」时的
#   自动安装，删不掉临时包属清理失败而不是安装失败——升级成异常会穿出「安装失败只返回 False、不抛」
#   的既有契约（见模块头「设计取舍」），升级成 warning 则会在磁盘只读/文件被占用的机器上每轮启动
#   刷一条与结果无关的噪音，还要为它新增一条四目录 msgid。形态与同目录内的 `_discard_master_zip`
#   （src/ffmpeg_master_download.py）以及本函数内三条既有内联 unlink 逐字一致（那边同样是
#   `except OSError: pass`），三类实现不并列第二套口径。
# 真正的风险是**残留**：gyan.dev 的 essentials 包约 90MB、BtbN master 约 190MB，下载中断或解压抛错
#   后若不删，程序目录就长期躺着一个「看着像已下载完成」的半截包——与本仓「残缺/非压缩包不得留在
#   目录里被后续运行当成已下载」的既有口径冲突（见 download_ffmpeg_official 里的形态守卫段注释）。
def _discard_official_zip(zip_path: Path) -> None:
    if not zip_path.exists():
        return
    try:
        zip_path.unlink()
    except OSError:
        pass


def download_ffmpeg_official(url: str, dest_dir: str) -> bool:
    # 从官方源下载并安装 FFmpeg (Windows)
    # L-13（2026-10-18）：临时包路径必须先于 try 求值，函数末尾的 finally 才能在**所有**出口
    # （含两个 except 分支）引用到它；原先它写在 try 的第一行，finally 里直接读会撞 UnboundLocalError
    # 风险（dest_dir 拼接本身不会抛，但把它放在 try 内就等于「异常出口可能没有这个名字」）。
    zip_file_path = Path(dest_dir) / "ffmpeg_official_temp.zip"
    try:
        # P-1：下载**前**先取官方公布的期望哈希。放在前面而不是后面，是为了在上游文档已不可达 /
        # 已被替换时少拉一次几百 MB；比对对象仍是同一 URL 的当前构建（上游版本轮转的窗口
        # 在两种顺序下都存在，区别只是「白下载一次」与「白等一次」）。
        official_hash = _fetch_official_sha256(url + _OFFICIAL_DOC_SUFFIX)

        # 下载文件（带进度条）
        with requests.get(url, stream=True, timeout=30) as response:
            response.raise_for_status()
            # Content-Length 可能缺失（分块传输）为 0，tqdm 进度条退化为未知总量，仅影响显示不影响下载。
            total_size = int(response.headers.get("Content-Length", 0))
            # MID-59：在读取响应头仍可用的作用域内固化「构建标识」，供旁路文件命名。
            build_id = _build_identity(response.headers)

            with tqdm(
                total=total_size, unit="B", unit_scale=True, ncols=100, desc="Downloading ffmpeg (official)"
            ) as t:
                with open(zip_file_path, "wb") as f:
                    for data in response.iter_content(chunk_size=1024):
                        _ = t.update(len(data))
                        _ = f.write(data)

        # 加固（2026-09-22）：先判「拿到的到底是不是压缩包」，再进哈希校验/记账。
        # 成因不是假想：CDN / 前置代理 / 被改指的 URL 都会以 **200 + text/html** 回一段挑战页
        # （实测形态：某镜像站的人机验证 PoW 页，正文 10KB、且不带 Content-Length / ETag /
        # Last-Modified）。三个头全缺 → _build_identity 返回 "" → 旁路基准落到**旧文件名**
        # _ffmpeg_official.zip.sha256；若不在此拦住，_check_or_record_zip_sha256 会在 TOFU 分支
        # 把这段 HTML 的哈希当成「可信基准」写下去，而真正的失败要等到 unzip_file 才暴露，
        # 日志只剩一句「不是 zip」——基准已被污染，下次拿到真包反倒可能被判成篡改。
        # 判序必须是「形态 → 哈希 → 解压」：三者校验的都是同一个产物文件。
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

        # 解压并提取 bin 目录
        # CR-11 修复：官方源原走 zf.extractall，绕过了 unzip_file 的解压炸弹防护
        # （单文件 4GB / 累计 8GB / 压缩比 100x 上限）与 Zip Slip 校验，与同期的蓝奏云路径
        # （现已删除）防护强度不一致。损坏或被投毒的 zip 可撑爆磁盘。统一走唯一实现。
        with tempfile.TemporaryDirectory() as tmp_dir:
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

            # 复制到目标位置
            ffmpeg_target = os.path.join(dest_dir, "ffmpeg")
            if os.path.exists(ffmpeg_target):
                shutil.rmtree(ffmpeg_target)

            _ = shutil.copytree(bin_dir, ffmpeg_target)

        # 清理临时文件
        if zip_file_path.exists():
            zip_file_path.unlink()

        # 更新 PATH 并验证安装
        # 把 ffmpeg 目录前置注入 PATH，本进程及子进程后续 `ffmpeg` 调用都命中新装文件（覆盖系统其它同名项）。
        # 先注入再校验，校验失败也保留注入——无副作用（该目录即安装产物）。
        # L-15：本行刚装完就真跑一次 ffmpeg.exe，Windows 无控制台形态下不传 startupinfo 会闪窗。
        os.environ["PATH"] = ffmpeg_path + os.pathsep + (current_env_path or "")
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
        logger.error(i18n.tr("Official ffmpeg installation failed: {type_name} - {e}", type_name=type(e).__name__, e=e))
        return False
    finally:
        # L-13（2026-10-18）：出口统一清理。此前只有三条「判定失败」出口各自内联 unlink
        # （非压缩包 / 哈希不符 / 成功后清临时文件），而**异常**出口一条都没删：
        # ① 下载中断（requests 读取期抛错，或写盘 OSError）→ except 分支返 False、半截包留下；
        # ② unzip_file 抛解压炸弹/损坏 → 同上；另有 ③ bin 目录里找不到 ffmpeg.exe 的 return False
        #   （在 with TemporaryDirectory 块内直接返回，跳过后面的清理）与 ④ copytree/复核抛错。
        #   报告点名的是 ①②两条，实测共四条出口漏删（gyan.dev 包约 90MB、master 约 190MB）。
        # finally 覆盖全部路径且与三条既有内联 unlink 幂等共存（那三条刻意保留：它们各自绑着
        # 「为什么这一支必须立刻删」的说明，见上方形态守卫段），存在即删、不存在即 no-op。
        # 回归锁：tests/test_ffmpeg_install.py::TestOfficialDownload
        # ::test_interrupted_download_unlinks_temp_zip / ::test_unzip_failure_unlinks_temp_zip
        # ::test_missing_bin_dir_unlinks_temp_zip。
        _discard_official_zip(zip_file_path)


def install_ffmpeg_official_windows() -> bool:
    # Windows: 从官方源 gyan.dev 安装 FFmpeg
    official_url = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
    return download_ffmpeg_official(official_url, execute_dir)


# 第二条 Windows 运行期 ffmpeg 源（BtbN master 滚动构建）的显式开关，默认关闭（SEV-2218）。
# 为什么必须默认关：AGENTS.md「三类钉定/校验」② 的红线是「Windows 运行期只有 gyan.dev 一条
# 自动路径，新增任何第二条前必须先满足『官方公布哈希』判据」。master-latest 是**滚动别名**，
# BtbN 与 fyhub 镜像都不为它公布可核对的 .sha256（后者该文档实测 404），故该源只能落在
# TOFU（首次信任）强度上——恰恰不满足该判据，因此不得成为默认路径。
# 与被删除的蓝奏云兜底同一处置口径：要使用，就得用户显式承担未校验安装的后果。
_FFMPEG_MASTER_ENV = "FFMPEG_MASTER_ALLOWED"


def _master_source_allowed() -> bool:
    # 取值口径一律走 src/config_bool.parse_config_bool（是/否、true/false、1/0、yes/no、
    # on/off、t/f，大小写与首尾空白均不敏感），**不得**再写 `== "1"` / `in ("true","1")`
    # 这类第三套布尔判定——「同一份配置在不同模块语义不同」的老坑（见 AGENTS.md 第 9 条）。
    # 未设置该变量时 parse_config_bool(None, False) 返回默认值 False。
    return parse_config_bool(os.environ.get(_FFMPEG_MASTER_ENV), False)


def install_ffmpeg_windows() -> bool:
    # Windows FFmpeg 安装入口：按「架构 × FFMPEG_MASTER_ALLOWED 开关」分流（master 门禁理由见
    # _FFMPEG_MASTER_ENV 上方注释）。x86_64 只走 gyan.dev 官方源（带官方 SHA256 校验），失败时**仅当**
    # FFMPEG_MASTER_ALLOWED 取真才回落 BtbN master（无官方 .sha256、仅 TOFU）；ARM64 因 gyan.dev 只发
    # x86_64（可经 x64 模拟跑、非原生）、原生 arm64 只能来自 master，故未开启时用官方 x86_64 模拟、开启后
    # 先试原生 arm64 master 再退官方 x86_64 保底。两条分支在「开启」与「因未开启而跳过」时各落一条 warning、
    # 绝不静默；失败不抛异常，由调用方决定后续提示（与既有契约一致）。
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

    # 全部失败：给出手动安装提示。
    # MID-59：官方源被「哈希基准」拒时用户只剩「手动安装」这一句无指向性的提示。
    # 把可执行的自救步骤（删过期基准）与旁路文件的真实防护强度（与产物同目录 →
    # 等同目录权限）一并说明；master 路径的 TOFU 基准（_ffmpeg_master*）同理。
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
        # 2026-09-12 修复（CODE_REVIEW_FIX_1 F-17）：移除 `yum -y update`——它是**全量系统升级**（一并升
        # 内核 / glibc / systemd，副作用远超「装一个 ffmpeg」、甚至要求重启），且 `yum install` 自身会刷新
        # 仓库元数据、无需前置 update；旧实现 update 失败即 return False，还会把「yum 源暂不可用」误判成
        # RHEL 系不可用、连 apt 回退都不给。
        # [2026-09-20 MIN-24④ 修订] 本块旧末句「移除 update 后 install 失败会自然落到下方 apt 分支」与实现不符：
        # is_RHS 原本只在 FileNotFoundError 分支置 False，「yum 在位但装不上」（RHEL 未启用 EPEL 的常态）遂
        # 直接落到「请手动安装」——真正的回退置位在下方 returncode!=0 分支（其语义见该处注释）。
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
        # L-14（2026-10-18）：本分支原先只打日志、不改 is_RHS，于是「yum 在位但 run() 抛非
        # FileNotFoundError 异常」（TimeoutExpired——yum 挂在仓库同步上；PermissionError——非 root
        # 却试图写 yum 缓存；以及 result.stderr 形态异常带来的 AttributeError 等）会跳过 apt 分支、
        # 直接落到函数末尾的直下兜底，与该处自述的顺序判据「直下兜底**只能在** yum、apt 两条包
        # 管理器路径都试过且都没装上之后进行」正相反（MIN-24④ 只把回退补在 returncode!=0 那一支，
        # 异常这一支是同族漏网）。is_RHS 的语义就是「还要不要试 apt」，异常轮同样属「没装上」，
        # 故一并置 False。代价可控：RHEL 系上 apt 本就不存在，只会多一条「apt command not found」
        # 的既有 error 日志，随后照旧落直下兜底/手动提示，不会静默成功。
        # [行为变更] 本分支此前被 tests/test_ffmpeg_install.py::TestLinuxExtraBranches
        # ::test_yum_probe_crash_keeps_rhs_semantics 当作「既有语义」钉住（断言 apt 不被触达）；
        # 该断言锁的是本条要修的缺陷本身，已随 L-14 改判为「yum 抛错后必须仍试 apt」。
        # 副作用说明：改完后走到 `if not is_RHS:` 时该标志恒为 False（yum 成功那一支已 return），
        # 守卫成为形式上的恒真判断——刻意保留而不删，它仍是「两条包管理器路径」这一结构的落点，
        # 将来若在 yum 块再增出口，该守卫会继续生效。
        # 回归锁：tests/test_ffmpeg_install.py::TestLinuxExtraBranches
        # ::test_yum_probe_crash_still_tries_apt。
        is_RHS = False

    # 尝试 apt (Debian/Ubuntu)
    if not is_RHS:
        try:
            logger.debug("Trying to install the stable version of ffmpeg for Linux using apt...")
            result = subprocess.run(["apt", "update"], capture_output=True, timeout=300)
            if result.returncode != 0:
                logger.error("Failed to update package lists using apt")
                # R-11（2026-10-02）：本分支原先在此 `return False` 早退，绕过了函数末尾的直下兜底。
                # 而无 root 的 Debian/Ubuntu arm64（含本仓镜像的 USER recorder）上 `apt update` 失败正是
                # 常态——它要写 /var/lib/apt/lists，而这一人群恰是规格 §一 与新模块头注释声明的目标用户。
                # 现只去掉早退：保留「update 失败就别白跑 apt install」的既有取舍（收进下方 else 分支），
                # 但让它与「apt install 失败」「apt 不存在」一样落到统一出口——先试官方直下，仍失败才给手动提示。
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
    # 顺序判据（2026-10-02 Linux arm64 支持）：直下兜底**只能在** yum、apt 两条包管理器路径都试过
    # 且都没装上之后进行，不得颠倒——apt/yum 天然给原生 arm64 构建且带发行版自己的签名链，
    # 完整性强度高于「运行期取官方公布的 SHA256」；直下只兜「拿不到包管理器」（轻量发行版/容器）
    # 或包管理器仓库里没有 ffmpeg 的情形。
    # 成功即 return True，与上面两条包管理器路径的返回形态一致；失败则继续落到下方手动安装提示。
    # master_allowed 由本模块的开关函数传入（同一份 FFMPEG_MASTER_ALLOWED 语义），新模块自身不读环境变量。
    # [2026-10-02 R-11 补充] 「apt 在位但 update 失败」同样属于「两条包管理器路径都试过且都没装上」，
    # 该分支不再早退、一并落到本统一出口；判据仍是「两条路径都试过之后」，顺序未颠倒。
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


# 包内 ffmpeg 目录是否应当前置到 PATH —— **主程序侧**判据的唯一事实源（W6，2026-09-22）。
# 孪生副本：`scripts/douyin_live_recorder_standalone.py` 里同名同语义函数（该文件按设计不 import
# src/，可独立单文件分发）。**改判据必须两处同改**（同 src/scheduler.py 的副本先例），
# 行为等价性由 tests/test_ffmpeg_path_preference.py 的 TestTwinEquivalence 锁住。
# 返回 True  = 维持既有行为（把包内目录前置）；False = 不前置，让系统 PATH 上已有的那份生效。
#
# 为什么要让位：full 包内置的 macOS ffmpeg 是 evermeet 的 **x86_64** 静态构建
#   （ffmpeg.org 官方 macOS 条目只列「Static builds for macOS 64-bit」，上游不发布 arm64 构建，
#   arm64 端点实测 404），在 Apple Silicon 上只能经 Rosetta 2 转译执行。而 main.py 原先
#   **无条件**把包内目录前置，于是「已用 Homebrew 装了原生 arm64 ffmpeg」的用户会被包内那份
#   遮蔽，白付转译开销——重编码路径最明显（src/video_postprocess.py 的 libx264、
#   main.py 的 libmp3lame），因为转译对纯 copy 拉流影响小、对软件编码影响大。
#
# 为什么判据保守（任一不成立即维持现状）：PATH 优先级是全局副作用，误判一次会让全部录制
#   子进程改用用户机器上的另一份 ffmpeg（版本/编译选项都可能不同）。故只在「darwin + arm64 +
#   包内目录存在 + 注入前的 PATH 上另有 ffmpeg + 那份不是包内自身」五条同时成立时才让位；
#   Windows / Linux / Intel Mac 的行为逐字不变——改它们的 PATH 优先级会破坏既有语义
#   （Windows 的自动安装分支本身就靠前置生效，见模块头「PATH 优先级策略」段）。
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
        # 2026-09-12 审查（低危）：原无 timeout——ffmpeg 可执行档存在但卡住时
        # （PATH 命中损坏/被占用的 ffmpeg、网络文件系统上的可执行档、杀毒软件
        # 拦截扫描等）subprocess.run 会无限阻塞，把整个启动流程挂死。
        # 版本探测是毫秒级操作，给 15 秒已远超正常耗时。
        # L-15：startupinfo 用来抑制 Windows 无控制台形态下每次探测闪出的子进程窗口（判据见
        # _win_startup_info；本行是本模块被启动流程调用最频繁的一处探测）。
        result = subprocess.run(
            ["ffmpeg", "-version"], capture_output=True, text=True, timeout=15, startupinfo=_win_startup_info()
        )
        version = result.stdout.strip()
        if result.returncode == 0 and version:
            return True
    # FileNotFoundError：系统 PATH 中无 ffmpeg 可执行文件，静默返回 False 触发自动安装；
    # OSError 通常是 script_path/ffmpeg 残留了损坏目录但 PATH 找到的是它，提示删除重装以避免反复失败。
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
