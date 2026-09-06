#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# FFmpeg 自动安装模块 - 跨平台 FFmpeg 自动检测与安装
#
# 职责：检测系统是否已安装 ffmpeg（check_ffmpeg_installed），未安装则按平台自动拉取并安装
#   （Windows 官方源 gyan.dev 优先、蓝奏云备用；macOS 走 Homebrew；Linux 走 yum/apt）。
# 安装落点：execute_dir（冻结后指向 _internal/，与运行时资源同目录），装好后把 ffmpeg 目录
#   前置注入 os.environ["PATH"]，使同进程后续 subprocess 调用 `ffmpeg` 能直接命中。
# 校验约定：所有安装路径最后都跑一次 `ffmpeg -version`，returncode==0 才认成功，否则回退下一源/报错。
# 设计取舍：安装失败只返回 False、不抛异常（由调用方决定提示用户手动安装），避免中断主程序启动。

import os
import platform
import re
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path
from typing import cast

import requests

# loguru 的 logger 为模块级单例，src.logger 对其做过的配置在此同样生效；
# 直接从此处导入可避免基于 basedpyright 的 "未从 src.logger 导出" 告警。
from loguru import logger
from tqdm import tqdm

# 应用根目录复用 src.logger 公开导出的 script_path（等价原私有 _app_root() 的返回值）
from src.logger import script_path

# 解压实现与 node_install 共用同一份（原先两处逐字重复，见 src/utils.unzip_file）
from src.utils import unzip_file

# 全局路径和环境变量
current_platform = platform.system()
execute_dir = script_path  # 冻结后指向 _internal/，与 __file__ 定位的资源收敛到同一处
# 安装时把新 ffmpeg 目录前缀拼回系统原 PATH；运行期 PATH 可能已被修改，先快照原始值避免重复嵌套。
current_env_path = os.environ.get("PATH")
# 安装目标子目录：ffmpeg 可执行文件最终位于 execute_dir/ffmpeg/bin/ffmpeg.exe（官方源）或平铺（蓝奏云）。
ffmpeg_path = os.path.join(execute_dir, "ffmpeg")


def download_ffmpeg_official(url: str, dest_dir: str) -> bool:
    # 从官方源下载并安装 FFmpeg (Windows)
    try:
        zip_file_path = Path(dest_dir) / "ffmpeg_official_temp.zip"

        # 下载文件（带进度条）
        with requests.get(url, stream=True, timeout=30) as response:
            response.raise_for_status()
            # Content-Length 可能缺失（分块传输）为 0，tqdm 进度条退化为未知总量，仅影响显示不影响下载。
            total_size = int(response.headers.get("Content-Length", 0))

            with tqdm(
                total=total_size, unit="B", unit_scale=True, ncols=100, desc="Downloading ffmpeg (official)"
            ) as t:
                with open(zip_file_path, "wb") as f:
                    for data in response.iter_content(chunk_size=1024):
                        _ = t.update(len(data))
                        _ = f.write(data)

        # 解压并提取 bin 目录
        with tempfile.TemporaryDirectory() as tmp_dir:
            with zipfile.ZipFile(zip_file_path, "r") as zf:
                zf.extractall(tmp_dir)

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
        os.environ["PATH"] = ffmpeg_path + os.pathsep + (current_env_path or "")
        result = subprocess.run(["ffmpeg", "-version"], capture_output=True, timeout=30)
        if result.returncode == 0:
            logger.debug("ffmpeg (official) installation was successful")
            return True
        else:
            logger.error("ffmpeg official installation verification failed")
            return False

    except requests.RequestException as e:
        logger.warning(f"Official ffmpeg download failed (network error): {e}")
        return False
    except Exception as e:
        logger.error(f"Official ffmpeg installation failed: {type(e).__name__} - {e}")
        return False


def install_ffmpeg_official_windows() -> bool:
    # Windows: 从官方源 gyan.dev 安装 FFmpeg
    official_url = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
    return download_ffmpeg_official(official_url, execute_dir)


def get_lanzou_download_link(url: str, password: str | None = None) -> str | None:
    # 从蓝奏云获取 FFmpeg 真实下载链接
    try:
        headers = {
            "accept-language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
            "Origin": "https://wwasx.lanzout.com",
            "Referer": "https://wwasx.lanzout.com/b00hryv9ch",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36 Edg/141.0.0.0",
        }
        # 蓝奏云下载直链由页面内联动态签名 sign 保护：先 GET 页面提取 sign，再 POST ajaxm.php 换取，
        # 不能直接构造 URL（会得到 403/已过期）。headers 里的 Referer/Origin 为接口硬校验项。
        with requests.get(url, headers=headers, timeout=30) as response:
            sign_match = re.search("var skdklds = '(.*?)';", response.text)
        if not sign_match:
            logger.error("Failed to extract sign from lanzou page")
            return None
        sign = sign_match.group(1)

        # 请求下载地址
        data = {
            "action": "downprocess",
            "sign": sign,
            "p": password,
            "kd": "1",
        }
        with requests.post("https://wwasx.lanzout.com/ajaxm.php", headers=headers, data=data, timeout=30) as response:
            json_data = cast(dict[str, str], response.json())
        download_url = json_data.get("dom", "") + "/file/" + json_data.get("url", "")
        if not download_url or download_url == "/file/":
            logger.error("Failed to build download URL from lanzou response")
            return None

        # 获取最终重定向地址
        with requests.get(download_url, headers=headers, timeout=30) as response:
            return response.url
    except Exception as e:
        logger.error(f"Failed to obtain ffmpeg download address. {e}")
    return None


def _install_ffmpeg_lanzou() -> bool:
    # Windows: 从蓝奏云备用源安装 FFmpeg
    try:
        logger.debug("Installing the latest version of ffmpeg from lanzou for Windows...")
        ffmpeg_url = get_lanzou_download_link("https://wwasx.lanzout.com/b00hryv9ch", "eh7o")
        if not ffmpeg_url:
            logger.error("Failed to obtain ffmpeg download address from lanzou")
            return False

        # 蓝奏云直链不暴露版本号，文件名/版本号写死为快照常量，仅用于展示与本地去重文件名；
        # 实际下载始终取 latest 构建，升级不会因版本号写死而失效。
        full_file_name = "ffmpeg_latest_build_20250124.zip"
        version = "v20250124"
        zip_file_path = Path(execute_dir) / full_file_name

        # 如果已下载则直接安装
        if Path(zip_file_path).exists():
            logger.debug("ffmpeg installation file already exists, start install...")
        else:
            # 下载文件
            with requests.get(ffmpeg_url, stream=True, timeout=60) as response:
                response.raise_for_status()
                total_size = int(response.headers.get("Content-Length", 0))
                block_size = 1024

                with tqdm(
                    total=total_size, unit="B", unit_scale=True, ncols=100, desc=f"Downloading ffmpeg ({version})"
                ) as t:
                    with open(zip_file_path, "wb") as f:
                        for data in response.iter_content(block_size):
                            _ = t.update(len(data))
                            _ = f.write(data)

        # 解压并验证
        unzip_file(zip_file_path, execute_dir)
        # 解压到 execute_dir（与官方源落点一致），随后同样注入 PATH 并 `ffmpeg -version` 校验。
        # 把 ffmpeg 目录前置注入 PATH，使后续 `ffmpeg` 调用命中新装文件。
        os.environ["PATH"] = ffmpeg_path + os.pathsep + (current_env_path or "")
        result = subprocess.run(["ffmpeg", "-version"], capture_output=True, timeout=30)
        if result.returncode == 0:
            logger.debug("ffmpeg (lanzou) installation was successful")
            return True
        else:
            logger.error("ffmpeg lanzou installation verification failed")
            return False
    except Exception as e:
        logger.error(f"ffmpeg lanzou installation failed: {type(e).__name__} - {e}")
        return False


def install_ffmpeg_windows() -> bool:
    # Windows FFmpeg 安装（官方源优先，蓝奏云备用）
    # Windows 安装顺序：官方源 gyan.dev 优先，失败（网络/被墙）再回退蓝奏云备用源；两者皆败提示手动安装。
    # 单源失败不抛异常，让另一源有机会补救，最大化自动安装成功率。
    logger.warning("ffmpeg is not installed.")

    logger.debug("Trying to install ffmpeg from official source (gyan.dev)...")
    if install_ffmpeg_official_windows():
        return True

    logger.warning("Official source unavailable, falling back to lanzou download...")
    if _install_ffmpeg_lanzou():
        return True

    logger.error("All download methods failed. Please manually install ffmpeg by yourself.")
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
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to install ffmpeg using Homebrew. {e}")
        logger.error("Please install ffmpeg manually or check your Homebrew installation.")
    except Exception as e:
        logger.error(f"An unexpected error occurred: {e}")
    return False


def install_ffmpeg_linux() -> bool:
    # Linux: 自动选择 yum/apt 安装 FFmpeg
    is_RHS = True

    # 尝试 yum (RHEL/CentOS)
    try:
        logger.warning("ffmpeg is not installed.")
        logger.debug("Trying to install the stable version of ffmpeg")
        # 注意：yum update 失败（returncode!=0）直接 return False，不再回退 apt——
        # 仅当 yum 命令根本不存在（FileNotFoundError）才切到 apt。混用包管理器的环境会被误判为 RHS 源损坏。
        result = subprocess.run(["yum", "-y", "update"], capture_output=True, timeout=300)
        if result.returncode != 0:
            logger.error("Failed to update package lists using yum.")
            return False

        result = subprocess.run(["yum", "install", "-y", "ffmpeg"], capture_output=True, timeout=300)
        if result.returncode == 0:
            logger.debug("ffmpeg installation was successful using yum. Restart for changes to take effect.")
            return True
        logger.error(result.stderr.decode("utf-8", errors="replace").strip())
    except FileNotFoundError:
        logger.debug("yum command not found, trying to install using apt...")
        is_RHS = False
    except Exception as e:
        logger.error(f"An error occurred while trying to install ffmpeg using yum: {e}")

    # 尝试 apt (Debian/Ubuntu)
    if not is_RHS:
        try:
            logger.debug("Trying to install the stable version of ffmpeg for Linux using apt...")
            result = subprocess.run(["apt", "update"], capture_output=True, timeout=300)
            if result.returncode != 0:
                logger.error("Failed to update package lists using apt")
                return False

            result = subprocess.run(["apt", "install", "-y", "ffmpeg"], capture_output=True, timeout=300)
            if result.returncode == 0:
                logger.debug("ffmpeg installation was successful using apt. Restart for changes to take effect.")
                return True
            else:
                logger.error(result.stderr.decode("utf-8", errors="replace").strip())
        except FileNotFoundError:
            logger.error("apt command not found, unable to install ffmpeg. Please manually install ffmpeg by yourself")
        except Exception as e:
            logger.error(f"An error occurred while trying to install ffmpeg using apt: {e}")
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
            f"ffmpeg auto installation is not supported on this platform: {current_platform}. Please install ffmpeg manually."
        )
    return False


def check_ffmpeg_installed() -> bool:
    # 检查 FFmpeg 是否已安装并可用
    try:
        result = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True)
        version = result.stdout.strip()
        if result.returncode == 0 and version:
            return True
    # FileNotFoundError：系统 PATH 中无 ffmpeg 可执行文件，静默返回 False 触发自动安装；
    # OSError 通常是 script_path/ffmpeg 残留了损坏目录但 PATH 找到的是它，提示删除重装以避免反复失败。
    except FileNotFoundError:
        pass
    except OSError as e:
        logger.warning(
            f"OSError occurred: {e}. ffmpeg may not be installed correctly or is not available in the system PATH."
        )
        logger.warning("Please delete the ffmpeg and try to download and install again.")
    except Exception as e:
        logger.error(f"An unexpected error occurred: {e}")
    return False


def check_ffmpeg() -> bool:
    # 主入口：检查 FFmpeg，未安装则自动安装
    if not check_ffmpeg_installed():
        return install_ffmpeg()
    return True
