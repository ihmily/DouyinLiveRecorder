# -*- coding: utf-8 -*-
import os
import platform
import re
import shutil
import subprocess
from pathlib import Path

import distro
import requests

# loguru 的 logger 为模块级单例，src.logger 对其做过的配置在此同样生效；
# 直接从此处导入可避免基于 basedpyright 的 "未从 src.logger 导出" 告警。
from loguru import logger
from tqdm import tqdm

import i18n

# 应用根目录复用 src.logger 公开导出的 script_path（等价原私有 _app_root() 的返回值）
from . import utils
from .logger import script_path

# 解压实现与 ffmpeg_install 共用同一份（原先两处逐字重复，见 src/utils.unzip_file）
from .utils import is_valid_zip, unzip_file

# Node.js 环境自动安装模块 - 跨平台的 Node.js 自动检测和安装功能
#
# 职责：检测 `node` 命令是否可用（check_nodejs_installed），不可用则按平台自动安装
#   （Windows 从 npmmirror 拉 zip 解压；Linux 按发行版走 yum/apt；macOS 走 Homebrew）。
# 安装落点：execute_dir（冻结后指向 _internal/），解压后把 node 目录前置注入 PATH，
#   使同进程后续 `node` 调用直接命中。所有路径最后 `node -v` 校验 returncode==0 才认成功。
# 设计取舍：安装失败只返 False、不抛异常，交由调用方提示用户手动安装，避免中断主程序启动。
#
# 完整性模型：**权威哈希来自 nodejs.org 上游本体，npmmirror 只当加速镜像**。版本号取自
#   nodejs.cn 页面，但 zip 的期望哈希一律取 https://nodejs.org/dist/<version>/SHASUMS256.txt
#   里对应文件名的那条记录；取不到该文档才退回旁路基准 TOFU，并把降级显式写进 warning 日志。
#   必须换宿主取文档：让 npmmirror 自己出 SHASUMS 等于「镜像自证」——它能替换 zip 就能替换
#   自己的清单，校验归零；分离后镜像只影响速度、不影响信任判定。
#   取文档而非钉哈希常量：装的是页面当前推荐的版本（随上游发版轮转），钉常量会在下一版永久
#   失败（历史坑 MID-59 的形态）。本模块属 AGENTS.md「三类钉定/校验」的第②类（运行期安装）。


current_platform = platform.system()
execute_dir = script_path  # 冻结后指向 _internal/，与 __file__ 定位的资源收敛到同一处
current_env_path = os.environ.get("PATH", "")


# 分块计算文件 SHA256（二进制下载完整性校验用）。实现已下沉到 src.utils.sha256_of_file，此处为薄封装。
def _sha256_of_file(path: str | Path) -> str:
    return utils.sha256_of_file(path)


_NODE_HASH_SUFFIX = ".sha256"

# 权威哈希文档：nodejs.org 每个版本目录都发布 SHASUMS256.txt（每行 `<sha256>  <文件名>`）。
# 刻意**不**从 npmmirror 取这份文档：镜像能替换 zip 就能替换自己的清单，同源校验不构成校验。
_NODE_DIST_BASE = "https://nodejs.org/dist/"
_NODE_SHASUMS_NAME = "SHASUMS256.txt"
# 文档只有几 KB，与几百 MB 的 zip 共用 30s 超时会在上游故障时把启动拖慢；拿不到即降级。
_OFFICIAL_DOC_TIMEOUT_SECONDS = 15
# 摘要必须是**正好** 64 位小写十六进制：nodejs.cn 页面被 WAF/代理劫持时会回 200 + HTML，
# 宽松判定的后果不是「没校验」而是「把可用产物判成篡改」，比无校验更糟。
_SHA256_RE = re.compile(r"[0-9a-f]{64}")


# 版本号归一为 nodejs.org/dist 的目录形态（带 v 前缀）。当前页面的正则已把 `v` 锚进捕获组，
# 常态下本函数恒等；它防的是「页面改版 → 捕获到 22.11.0 这类裸形态」：那种形态拼 npmmirror
# 与权威文档 URL 都 404，两条一起坏且报错落在「取不到官方哈希」上，极易误判成上游故障。
# 在源头归一一次，两个下游共用同一个形态。
def _normalize_node_version(raw: str) -> str:
    value = raw.strip()
    if not value:
        return ""
    return value if value.startswith("v") else f"v{value}"


# 从 SHASUMS256.txt 正文里取目标文件的期望哈希；找不到 / 形态不符返回 ""。
# 匹配按「文件名字段逐字相等」，不做前缀/子串匹配：同一份清单里
# node-v22.11.0-win-x64.zip 与 node-v22.11.0-win-x64.7z 只差扩展名，子串匹配会拿错条目。
def _parse_shasums256(text: str, file_name: str) -> str:
    for line in text.splitlines():
        fields = line.strip().split()
        if len(fields) != 2 or fields[1] != file_name:
            continue
        candidate = fields[0].lower()
        return candidate if _SHA256_RE.fullmatch(candidate) else ""
    return ""


# 向 nodejs.org 取权威期望值。返回 ""=未取得（调用方据此显式降级到 TOFU）。
# 不抛异常：这份文档是「可选的更强防线」，它不可达时安装仍须能按原有 TOFU 路径完成。
def _fetch_official_sha256(version: str, file_name: str) -> str:
    doc_url = f"{_NODE_DIST_BASE}{version}/{_NODE_SHASUMS_NAME}"
    try:
        with requests.get(doc_url, timeout=_OFFICIAL_DOC_TIMEOUT_SECONDS) as response:
            response.raise_for_status()
            text = response.text
    except Exception as e:
        logger.warning(
            i18n.tr(
                "未取得 Node.js 官方 SHA256 文档: {masked_url} - {type_name}: {err}",
                masked_url=utils.mask_credentials(doc_url),
                type_name=type(e).__name__,
                err=e,
            )
        )
        return ""
    parsed = _parse_shasums256(text, file_name)
    if not parsed:
        logger.warning(
            i18n.tr(
                "Node.js 官方 SHA256 文档中没有 {file_name} 的条目（上游形态可能已变更）: {masked_url}",
                file_name=file_name,
                masked_url=utils.mask_credentials(doc_url),
            )
        )
    return parsed


def _record_zip_sha256(zip_path: Path, hash_file: Path, current_hash: str) -> None:
    # 把本次实算哈希写进旁路基准（TOFU 的「记录」侧）：权威校验通过时同样记录，
    # 这样将来某次取不到官方文档时手上仍有一份可比对的基准。
    try:
        hash_file.write_text(current_hash, encoding="ascii")
        logger.debug(i18n.tr("首次下载 Node.js SHA256 已记录：{current_hash}", current_hash=current_hash))
    except OSError as e:
        logger.warning(i18n.tr("写入 SHA256 缓存失败（不影响本次安装）: {e}", e=e))


def _check_or_record_zip_sha256(zip_path: Path, official_hash: str = "", source_url: str = "") -> bool:
    # 完整性判定入口：SHA256 校验/记录一体化，权威哈希优先，取不到才退回旁路基准
    # trust-on-first-use（原行为）——与 ffmpeg_install 同模式。
    hash_file = Path(str(zip_path) + _NODE_HASH_SUFFIX)
    current_hash = _sha256_of_file(zip_path)
    masked_url = utils.mask_credentials(source_url) if source_url else "unknown"
    if official_hash:
        # 权威分支：旁路基准只有「记不下」时的辅助价值，不得否决官方清单。
        if official_hash != current_hash:
            logger.error(
                i18n.tr(
                    "Node.js zip 与 nodejs.org 公布的 SHA256 不一致，拒绝安装（官方 {official} vs 实际 {actual}）："
                    "{masked_url}。可能是镜像被替换或下载期间上游发布了同名版本的新构建。",
                    official=official_hash,
                    actual=current_hash,
                    masked_url=masked_url,
                )
            )
            return False
        logger.debug(i18n.tr("Node.js zip 已通过 nodejs.org 公布的 SHA256 校验: {masked_url}", masked_url=masked_url))
        _record_zip_sha256(zip_path, hash_file, current_hash)
        return True
    # 降级分支（P-1 的显式降级点）：拿不到官方清单 → 只能沿用首次信任，必须在日志里说清强度回落了。
    logger.warning(
        i18n.tr(
            "未能取得 Node.js 官方公布的 SHA256，本次退回旁路基准/首次信任（TOFU）: {masked_url}",
            masked_url=masked_url,
        )
    )
    if hash_file.exists():
        try:
            expected = hash_file.read_text(encoding="ascii").strip().lower()
        except OSError as e:
            logger.warning(i18n.tr("读取 SHA256 缓存失败，跳过校验: {e}", e=e))
            return True
        if expected != current_hash:
            logger.error(
                i18n.tr(
                    "Node.js zip SHA256 与上次记录不一致（{expected} vs {actual}）。"
                    "可能 CDN 被篡改或版本变更。请删除 {hash_file} 后重试，或手动下载校验。",
                    expected=expected,
                    actual=current_hash,
                    hash_file=str(hash_file),
                )
            )
            return False
        logger.debug("Node.js SHA256 校验通过")
        return True
    _record_zip_sha256(zip_path, hash_file, current_hash)
    return True


def install_nodejs_windows() -> bool:
    # 在 Windows 系统上安装 Node.js，从 npmmirror 下载最新稳定版
    try:
        logger.warning("Node.js is not installed.")
        logger.debug("Installing the stable version of Node.js for Windows...")
        # 两处下载响应均以 with 管理（页面 + zip 流式下载），关闭连接不泄漏（与 ffmpeg_install 同写法）。
        with requests.get("https://nodejs.cn/download/", timeout=30) as response:
            if response.status_code != 200:
                logger.error("Failed to retrieve the Node.js version page")
                return False
            # 从 nodejs.cn 下载页正则抠出 npmmirror 镜像直链：页面 HTML 结构一旦变动，match 为空即安装失败。
            match = re.search("https://npmmirror.com/mirrors/node/(v.*?)/node-(v.*?)-x64.msi", response.text)
        if not match:
            logger.error("Failed to retrieve the download URL for the latest version of Node.js...")
            return False
        version = _normalize_node_version(match.group(1))
        # 原以 machine 是否含 "32" 判架构：Windows on ARM 的 machine 为 "ARM64"（不含 "32"）会被
        # 误判成 x64，下载 x64 构建在 ARM 上无法运行，且错误表现为「装完仍找不到 node」，极难归因。
        # 改为显式识别 arm64，其余按位宽回落。
        _machine = platform.machine().upper()
        if "ARM" in _machine or "AARCH" in _machine:
            system_bit = "arm64"
        elif "32" in _machine or "86" in _machine and "64" not in _machine:
            system_bit = "x86"
        else:
            system_bit = "x64"
        url = f"https://npmmirror.com/mirrors/node/{version}/node-{version}-win-{system_bit}.zip"

        full_file_name = url.rsplit("/", maxsplit=1)[-1]
        zip_file_path = Path(execute_dir) / full_file_name

        # P-1：先向 nodejs.org 取权威期望值，再决定要不要拉几百 MB 的 zip——
        # 清单不可达时只多花一次几百 KB 的探测，而清单可达但内容被换时省掉整次下载。
        # 注意文档宿主与下载宿主**刻意不同**（镜像只加速、不背书，见模块头）。
        official_hash = _fetch_official_sha256(version, full_file_name)

        # 原只判 exists()：中断下载留下的残缺 zip 会被当成「已下载」，随后
        # _check_or_record_zip_sha256 把**错误哈希固化为基线**，解压再抛 BadZipFile 被外层
        # except 吞掉；下次运行 zip 仍在且「哈希匹配」→ 永久失败且不自愈（只能手工删目录）。
        # 与 ffmpeg_install 的 _is_valid_zip 判据对齐：非有效 zip 即删除重下。
        if Path(zip_file_path).exists() and is_valid_zip(zip_file_path):
            logger.debug("Node.js installation file already exists, start install...")
        else:
            if Path(zip_file_path).exists():
                logger.warning("检测到残缺的 Node.js 压缩包缓存，删除后重新下载")
                try:
                    Path(zip_file_path).unlink()
                except OSError as e:
                    logger.warning(i18n.tr("删除残缺压缩包失败: {e}", e=e))
            with requests.get(url, stream=True, timeout=30) as response:
                response.raise_for_status()
                total_size = int(response.headers.get("Content-Length", 0))
                block_size = 1024

                with tqdm(
                    total=total_size, unit="B", unit_scale=True, ncols=100, desc=f"Downloading Node.js ({version})"
                ) as t:
                    with open(zip_file_path, "wb") as f:
                        for data in response.iter_content(block_size):
                            _ = t.update(len(data))
                            _ = f.write(data)

        # 校验/记录放在解压之前——解压出来的就是会被 PATH 命中并执行的二进制；
        # 哈希来源优先级（官方清单 > TOFU）见模块头「完整性模型」。
        if not _check_or_record_zip_sha256(zip_file_path, official_hash, source_url=url):
            try:
                zip_file_path.unlink()
            except OSError:
                pass
            return False

        # 解压到 execute_dir；zip 内顶层目录名为 node-vX.Y.Z-win-x64，提取后整体改名为 "node" 目录以便固定 PATH 引用。
        unzip_file(zip_file_path, execute_dir)
        extract_dir_path = str(zip_file_path).rsplit(".", maxsplit=1)[0]
        new_extract_dir_path = Path(execute_dir) / "node"
        # 仅当解压出的原目录存在、且目标 "node" 目录尚不存在时才重命名；已存在则走下方验证分支（避免覆盖/重复）。
        if Path(extract_dir_path).exists() and not Path(new_extract_dir_path).exists():
            os.rename(extract_dir_path, new_extract_dir_path)
            os.environ["PATH"] = os.path.join(execute_dir, "node") + os.pathsep + current_env_path
            result = subprocess.run(["node", "-v"], capture_output=True, timeout=15)
            if result.returncode == 0:
                logger.debug("Node.js installation was successful. Restart for changes to take effect")
                return True
            else:
                logger.debug("Node.js installation failed")
                return False
        elif Path(new_extract_dir_path).exists():
            # 已有安装目录，验证可用性
            result = subprocess.run(["node", "-v"], capture_output=True, timeout=15)
            if result.returncode == 0:
                return True
            logger.debug("Node.js directory exists but not working")
            return False
        return False

    except Exception as e:
        logger.error(i18n.tr("type: {type_name}, Node.js installation failed {e}", type_name=type(e).__name__, e=e))
        return False


def install_nodejs_centos() -> bool:
    # 在 CentOS/RHEL 系统上通过 yum 安装 Node.js
    try:
        logger.warning("Node.js is not installed.")
        logger.debug("Installing the latest version of Node.js for CentOS...")
        result = subprocess.run(["yum", "install", "-y", "epel-release"], capture_output=True, timeout=900)
        if result.returncode != 0:
            logger.error("Failed to install EPEL repository")
            return False

        result = subprocess.run(["yum", "install", "-y", "nodejs"], capture_output=True, timeout=900)
        if result.returncode == 0:
            logger.debug("Node.js installation was successful. Restart for changes to take effect.")
            return True
        else:
            logger.error("Node.js installation failed")
            return False

    except Exception as e:
        logger.error(i18n.tr("type: {type_name}, Node.js installation failed {e}", type_name=type(e).__name__, e=e))
        return False


def install_nodejs_ubuntu() -> bool:
    # Ubuntu/Debian：直接 apt 装 nodejs（未先 apt update，依赖已就新的包索引；装失败即返 False 提示手动）。
    try:
        logger.warning("Node.js is not installed.")
        logger.debug("Installing the latest version of Node.js for Ubuntu...")
        install_command = ["apt", "install", "-y", "nodejs"]
        result = subprocess.run(install_command, capture_output=True, timeout=900)
        if result.returncode == 0:
            logger.debug("Node.js installation was successful. Restart for changes to take effect.")
            return True
        else:
            logger.error("Node.js installation failed")
            return False
    except Exception as e:
        logger.error(i18n.tr("type: {type_name}, Node.js installation failed, {e}", type_name=type(e).__name__, e=e))
        return False


def install_nodejs_mac() -> bool:
    # 在 macOS 系统上通过 Homebrew 安装 Node.js
    logger.warning("Node.js is not installed.")
    logger.debug("Installing the latest version of Node.js for macOS...")
    try:
        result = subprocess.run(["brew", "install", "node"], capture_output=True, timeout=900)
        if result.returncode == 0:
            logger.debug("Node.js installation was successful. Restart for changes to take effect.")
            return True
        else:
            logger.error("Node.js installation failed")
            return False
    # [历史注] 此处原有 except subprocess.CalledProcessError 不可达：run 未传 check=True 永不抛该异常。
    except Exception as e:
        logger.error(i18n.tr("An unexpected error occurred: {e}", e=e))
        return False


def get_package_manager() -> str:
    # 检测 Linux 发行版类型，返回包管理器标识。distro.id() 为小写发行版标识；
    # 仅白名单内的 RHEL 系走 yum，其余（含 alpine/suse/arch 等无 apt 的）一律归 DBS(apt)——
    # 对无 apt 的发行版最终会因 apt 缺失而失败、提示手动安装，列表即「支持的包管理器白名单」。
    dist_id = distro.id()
    if dist_id in ["centos", "fedora", "rhel", "amzn", "oracle", "scientific", "opencloudos", "alinux"]:
        return "RHS"
    else:
        return "DBS"


def install_nodejs() -> bool:
    # 跨平台安装 Node.js 的主入口函数
    if current_platform == "Windows":
        return install_nodejs_windows()
    elif current_platform == "Linux":
        os_type = get_package_manager()
        if os_type == "RHS":
            return install_nodejs_centos()
        else:
            return install_nodejs_ubuntu()
    elif current_platform == "Darwin":
        return install_nodejs_mac()
    else:
        logger.debug(
            i18n.tr(
                "Node.js auto installation is not supported on this platform: {current_platform}. Please install Node.js manually.",
                current_platform=current_platform,
            )
        )
        return False


def check_nodejs_installed() -> bool:
    # 仅校验 `node` 命令存在即视为已安装，不检查 npm：Node 存在但 npm 缺失时，依赖 npm 的下游
    # 功能仍会失败，此处不感知（false positive）。
    # 异常集必须含 TimeoutExpired/OSError：`node -v` 卡死（杀毒软件拦截扫描、残缺安装）抛
    # TimeoutExpired、二进制损坏抛 OSError。本函数经 check_node() 在 import src 导入期被调用
    # （仅测试开关豁免），抛穿即 CLI/GUI/Web 三入口启动崩溃；口径对齐 check_ffmpeg_installed。
    try:
        result = subprocess.run(["node", "-v"], capture_output=True, timeout=15)
        version = result.stdout.strip()
        if result.returncode == 0 and version:
            return True
    # 命令不存在（FileNotFoundError）即视为未安装、静默返 False 触发自动安装。
    except FileNotFoundError:
        pass
    except subprocess.TimeoutExpired:
        logger.warning(
            i18n.tr(
                "node -v 执行超时（15 秒），按未安装处理: {node_path}",
                node_path=shutil.which("node") or "unknown",
            )
        )
    except OSError as e:
        logger.warning(
            i18n.tr(
                "OSError occurred: {e}. node may not be installed correctly or is not available in the system PATH.",
                e=e,
            )
        )
        logger.warning("Please delete the node directory and try to download and install again.")
    return False


def check_node() -> bool:
    # 检查并确保 Node.js 已安装，未安装则自动安装
    if not check_nodejs_installed():
        return install_nodejs()
    return True
