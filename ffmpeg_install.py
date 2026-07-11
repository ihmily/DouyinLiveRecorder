#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# FFmpeg 自动安装模块 - 跨平台 FFmpeg 自动检测与安装

import os
import re
import shutil
import subprocess
import sys
import platform
import tempfile
import zipfile
from pathlib import Path
import requests
from tqdm import tqdm
from src.logger import logger

# 全局路径和环境变量
current_platform = platform.system()
execute_dir = os.path.split(os.path.realpath(sys.argv[0]))[0]
current_env_path = os.environ.get('PATH')
ffmpeg_path = os.path.join(execute_dir, 'ffmpeg')


def unzip_file(zip_path: str | Path, extract_to: str | Path, delete: bool = True) -> None:
    # 解压 ZIP 文件
    if not os.path.exists(extract_to):
        os.makedirs(extract_to)

    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
        zip_ref.extractall(extract_to)

    if delete and os.path.exists(zip_path):
        os.remove(zip_path)


def download_ffmpeg_official(url: str, dest_dir: str) -> bool:
    # 从官方源下载并安装 FFmpeg (Windows)
    try:
        zip_file_path = Path(dest_dir) / 'ffmpeg_official_temp.zip'

        # 下载文件（带进度条）
        response = requests.get(url, stream=True, timeout=30)
        response.raise_for_status()
        total_size = int(response.headers.get('Content-Length', 0))

        with tqdm(total=total_size, unit="B", unit_scale=True,
                  ncols=100, desc='Downloading ffmpeg (official)') as t:
            with open(zip_file_path, 'wb') as f:
                for data in response.iter_content(chunk_size=1024):
                    t.update(len(data))
                    f.write(data)

        # 解压并提取 bin 目录
        with tempfile.TemporaryDirectory() as tmp_dir:
            with zipfile.ZipFile(zip_file_path, 'r') as zf:
                zf.extractall(tmp_dir)

            # 查找 bin 目录（含 ffmpeg.exe）
            bin_dir = None
            for root, _dirs, files in os.walk(tmp_dir):
                if os.path.basename(root) == 'bin':
                    if 'ffmpeg.exe' in files:
                        bin_dir = root
                        break

            if bin_dir is None:
                logger.error("ffmpeg.exe not found in official package")
                return False

            # 复制到目标位置
            ffmpeg_target = os.path.join(dest_dir, 'ffmpeg')
            if os.path.exists(ffmpeg_target):
                shutil.rmtree(ffmpeg_target)

            shutil.copytree(bin_dir, ffmpeg_target)

        # 清理临时文件
        if zip_file_path.exists():
            zip_file_path.unlink()

        # 更新 PATH 并验证安装
        os.environ['PATH'] = ffmpeg_path + os.pathsep + (current_env_path or "")
        result = subprocess.run(["ffmpeg", "-version"], capture_output=True)
        if result.returncode == 0:
            logger.debug('ffmpeg (official) installation was successful')
            return True
        else:
            logger.error('ffmpeg official installation verification failed')
            return False

    except requests.RequestException as e:
        logger.warning(f"Official ffmpeg download failed (network error): {e}")
        return False
    except Exception as e:
        logger.error(f"Official ffmpeg installation failed: {type(e).__name__} - {e}")
        return False


def install_ffmpeg_official_windows() -> bool:
    # Windows: 从官方源 gyan.dev 安装 FFmpeg
    official_url = 'https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip'
    return download_ffmpeg_official(official_url, execute_dir)


def get_lanzou_download_link(url: str, password: str | None = None) -> str | None:
    # 从蓝奏云获取 FFmpeg 真实下载链接
    try:
        headers = {
            'accept-language': 'zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6',
            'Origin': 'https://wweb.lanzouv.com',
            'Referer': 'https://wweb.lanzouv.com/iXncv0dly6mh',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) '
                          'Chrome/121.0.0.0 Safari/537.36 Edg/121.0.0.0',
        }
        # 获取页面 sign 签名
        response = requests.get(url, headers=headers)
        sign_match = re.search("var skdklds = '(.*?)';", response.text)
        if not sign_match:
            logger.error("Failed to extract sign from lanzou page")
            return None
        sign = sign_match.group(1)

        # 请求下载地址
        data = {
            'action': 'downprocess',
            'sign': sign,
            'p': password,
            'kd': '1',
        }
        response = requests.post('https://wweb.lanzouv.com/ajaxm.php', headers=headers, data=data)
        json_data = response.json()
        download_url = json_data['dom'] + "/file/" + json_data['url']

        # 获取最终重定向地址
        response = requests.get(download_url, headers=headers)
        return response.url
    except Exception as e:
        logger.error(f"Failed to obtain ffmpeg download address. {e}")


def _install_ffmpeg_lanzou() -> bool:
    # Windows: 从蓝奏云备用源安装 FFmpeg
    try:
        logger.debug("Installing the latest version of ffmpeg from lanzou for Windows...")
        ffmpeg_url = get_lanzou_download_link('https://wweb.lanzouv.com/iHAc22ly3r3g', 'eots')
        if not ffmpeg_url:
            logger.error("Failed to obtain ffmpeg download address from lanzou")
            return False

        full_file_name = 'ffmpeg_latest_build_20250124.zip'
        version = 'v20250124'
        zip_file_path = Path(execute_dir) / full_file_name

        # 如果已下载则直接安装
        if Path(zip_file_path).exists():
            logger.debug("ffmpeg installation file already exists, start install...")
        else:
            # 下载文件
            response = requests.get(ffmpeg_url, stream=True)
            total_size = int(response.headers.get('Content-Length', 0))
            block_size = 1024

            with tqdm(total=total_size, unit="B", unit_scale=True,
                      ncols=100, desc=f'Downloading ffmpeg ({version})') as t:
                with open(zip_file_path, 'wb') as f:
                    for data in response.iter_content(block_size):
                        t.update(len(data))
                        f.write(data)

        # 解压并验证
        unzip_file(zip_file_path, execute_dir)
        os.environ['PATH'] = ffmpeg_path + os.pathsep + (current_env_path or "")
        result = subprocess.run(["ffmpeg", "-version"], capture_output=True)
        if result.returncode == 0:
            logger.debug('ffmpeg (lanzou) installation was successful')
            return True
        else:
            logger.error('ffmpeg lanzou installation verification failed')
            return False
    except Exception as e:
        logger.error(f"ffmpeg lanzou installation failed: {type(e).__name__} - {e}")
        return False


def install_ffmpeg_windows() -> bool:
    # Windows FFmpeg 安装（官方源优先，蓝奏云备用）
    logger.warning("ffmpeg is not installed.")

    logger.debug("Trying to install ffmpeg from official source (gyan.dev)...")
    if install_ffmpeg_official_windows():
        return True

    logger.warning("Official source unavailable, falling back to lanzou download...")
    if _install_ffmpeg_lanzou():
        return True

    logger.error("All download methods failed. Please manually install ffmpeg by yourself.")
    return False


def install_ffmpeg_mac():
    # macOS: 使用 Homebrew 安装 FFmpeg
    logger.warning("ffmpeg is not installed.")
    logger.debug("Installing the stable version of ffmpeg for macOS...")
    try:
        result = subprocess.run(["brew", "install", "ffmpeg"], capture_output=True)
        if result.returncode == 0:
            logger.debug('ffmpeg installation was successful. Restart for changes to take effect.')
            return True
        else:
            logger.error("ffmpeg installation failed")
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to install ffmpeg using Homebrew. {e}")
        logger.error("Please install ffmpeg manually or check your Homebrew installation.")
    except Exception as e:
        logger.error(f"An unexpected error occurred: {e}")
    return False


def install_ffmpeg_linux():
    # Linux: 自动选择 yum/apt 安装 FFmpeg
    is_RHS = True

    # 尝试 yum (RHEL/CentOS)
    try:
        logger.warning("ffmpeg is not installed.")
        logger.debug("Trying to install the stable version of ffmpeg")
        result = subprocess.run(['yum', '-y', 'update'], capture_output=True)
        if result.returncode != 0:
            logger.error("Failed to update package lists using yum.")
            return False

        result = subprocess.run(['yum', 'install', '-y', 'ffmpeg'], capture_output=True)
        if result.returncode == 0:
            logger.debug("ffmpeg installation was successful using yum. Restart for changes to take effect.")
            return True
        logger.error(result.stderr.decode('utf-8').strip())
    except FileNotFoundError:
        logger.debug("yum command not found, trying to install using apt...")
        is_RHS = False
    except Exception as e:
        logger.error(f"An error occurred while trying to install ffmpeg using yum: {e}")

    # 尝试 apt (Debian/Ubuntu)
    if not is_RHS:
        try:
            logger.debug("Trying to install the stable version of ffmpeg for Linux using apt...")
            result = subprocess.run(['apt', 'update'], capture_output=True)
            if result.returncode != 0:
                logger.error("Failed to update package lists using apt")
                return False

            result = subprocess.run(['apt', 'install', '-y', 'ffmpeg'], capture_output=True)
            if result.returncode == 0:
                logger.debug("ffmpeg installation was successful using apt. Restart for changes to take effect.")
                return True
            else:
                logger.error(result.stderr.decode('utf-8').strip())
        except FileNotFoundError:
            logger.error("apt command not found, unable to install ffmpeg. Please manually install ffmpeg by yourself")
        except Exception as e:
            logger.error(f"An error occurred while trying to install ffmpeg using apt: {e}")
    logger.error("Manual installation of ffmpeg is required. Please manually install ffmpeg by yourself.")
    return False


def install_ffmpeg() -> bool:
    # 根据当前平台选择对应的 FFmpeg 安装方法
    if current_platform == "Windows":
        return install_ffmpeg_windows()
    elif current_platform == "Linux":
        return install_ffmpeg_linux()
    elif current_platform == "Darwin":
        return install_ffmpeg_mac()
    else:
        logger.debug(f"ffmpeg auto installation is not supported on this platform: {current_platform}. "
                     f"Please install ffmpeg manually.")
    return False


def check_ffmpeg_installed() -> bool:
    # 检查 FFmpeg 是否已安装并可用
    try:
        result = subprocess.run(['ffmpeg', '-version'], capture_output=True)
        version = result.stdout.strip()
        if result.returncode == 0 and version:
            return True
    except FileNotFoundError:
        pass
    except OSError as e:
        logger.warning(f"OSError occurred: {e}. ffmpeg may not be installed correctly or is not available in the system PATH.")
        logger.warning("Please delete the ffmpeg and try to download and install again.")
    except Exception as e:
        logger.error(f"An unexpected error occurred: {e}")
    return False


def check_ffmpeg() -> bool:
    # 主入口：检查 FFmpeg，未安装则自动安装
    if not check_ffmpeg_installed():
        return install_ffmpeg()
    return True
