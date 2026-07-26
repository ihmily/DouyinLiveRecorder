# -*- coding: utf-8 -*-
# Node.js 环境自动安装模块 - 跨平台的 Node.js 自动检测和安装功能

import os
import subprocess
import platform
import zipfile
from pathlib import Path
import requests
import re
import distro
from tqdm import tqdm
# loguru 的 logger 为模块级单例，src.logger 对其做过的配置在此同样生效；
# 直接从此处导入可避免基于 basedpyright 的 "未从 src.logger 导出" 告警。
from loguru import logger
# 应用根目录复用 src.logger 公开导出的 script_path（等价原私有 _app_root() 的返回值）
from .logger import script_path

current_platform = platform.system()
execute_dir = script_path  # 冻结后指向 _internal/，与 __file__ 定位的资源收敛到同一处
current_env_path = os.environ.get('PATH', '')


def unzip_file(zip_path: str | Path, extract_to: str | Path, delete: bool = True) -> None:
    # 解压 ZIP 文件到指定目录
    if not os.path.exists(extract_to):
        os.makedirs(extract_to)

    extract_root = os.path.realpath(extract_to)
    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
        # 防止 Zip Slip 目录穿越攻击：校验每个成员解压后的真实路径
        for member in zip_ref.namelist():
            member_path = os.path.realpath(os.path.join(extract_root, member))
            if not member_path.startswith(extract_root + os.sep) and member_path != extract_root:
                raise ValueError(f"Unsafe path in zip file: {member}")
        zip_ref.extractall(extract_to)

    if delete and os.path.exists(zip_path):
        os.remove(zip_path)


def install_nodejs_windows() -> bool:
    # 在 Windows 系统上安装 Node.js，从 npmmirror 下载最新稳定版
    try:
        logger.warning("Node.js is not installed.")
        logger.debug("Installing the stable version of Node.js for Windows...")
        response = requests.get('https://nodejs.cn/download/', timeout=30)
        if response.status_code == 200:
            match = re.search('https://npmmirror.com/mirrors/node/(v.*?)/node-(v.*?)-x64.msi',
                              response.text)
            if match:
                version = match.group(1)
                system_bit = 'x64' if '32' not in platform.machine() else 'x86'
                url = f'https://npmmirror.com/mirrors/node/{version}/node-{version}-win-{system_bit}.zip'
            else:
                logger.error("Failed to retrieve the download URL for the latest version of Node.js...")
                return False

            full_file_name = url.rsplit('/', maxsplit=1)[-1]
            zip_file_path = Path(execute_dir) / full_file_name

            if Path(zip_file_path).exists():
                logger.debug("Node.js installation file already exists, start install...")
            else:
                response = requests.get(url, stream=True, timeout=30)
                response.raise_for_status()
                total_size = int(response.headers.get('Content-Length', 0))
                block_size = 1024

                with tqdm(total=total_size, unit="B", unit_scale=True,
                          ncols=100, desc=f'Downloading Node.js ({version})') as t:
                    with open(zip_file_path, 'wb') as f:
                        for data in response.iter_content(block_size):
                            _ = t.update(len(data))
                            _ = f.write(data)

            unzip_file(zip_file_path, execute_dir)
            extract_dir_path = str(zip_file_path).rsplit('.', maxsplit=1)[0]
            new_extract_dir_path = Path(execute_dir) / 'node'
            if Path(extract_dir_path).exists() and not Path(new_extract_dir_path).exists():
                os.rename(extract_dir_path, new_extract_dir_path)
                os.environ['PATH'] = os.path.join(execute_dir, 'node') + os.pathsep + current_env_path
                result = subprocess.run(["node", "-v"], capture_output=True)
                if result.returncode == 0:
                    logger.debug('Node.js installation was successful. Restart for changes to take effect')
                    return True
                else:
                    logger.debug('Node.js installation failed')
                    return False
            elif Path(new_extract_dir_path).exists():
                # 已有安装目录，验证可用性
                result = subprocess.run(["node", "-v"], capture_output=True)
                if result.returncode == 0:
                    return True
                logger.debug('Node.js directory exists but not working')
                return False
            return False
        else:
            logger.error("Failed to retrieve the Node.js version page")
            return False

    except Exception as e:
        logger.error(f"type: {type(e).__name__}, Node.js installation failed {e}")
        return False


def install_nodejs_centos() -> bool:
    # 在 CentOS/RHEL 系统上通过 yum 安装 Node.js
    try:
        logger.warning("Node.js is not installed.")
        logger.debug("Installing the latest version of Node.js for CentOS...")
        result = subprocess.run(['yum', 'install', '-y', 'epel-release'], capture_output=True)
        if result.returncode != 0:
            logger.error("Failed to install EPEL repository")
            return False

        result = subprocess.run(['yum', 'install', '-y', 'nodejs'], capture_output=True)
        if result.returncode == 0:
            logger.debug('Node.js installation was successful. Restart for changes to take effect.')
            return True
        else:
            logger.error("Node.js installation failed")
            return False

    except Exception as e:
        logger.error(f"type: {type(e).__name__}, Node.js installation failed {e}")
        return False


def install_nodejs_ubuntu() -> bool:
    # 在 Ubuntu/Debian 系统上通过 apt 安装 Node.js
    try:
        logger.warning("Node.js is not installed.")
        logger.debug("Installing the latest version of Node.js for Ubuntu...")
        install_command = ['apt', 'install', '-y', 'nodejs']
        result = subprocess.run(install_command, capture_output=True)
        if result.returncode == 0:
            logger.debug('Node.js installation was successful. Restart for changes to take effect.')
            return True
        else:
            logger.error("Node.js installation failed")
            return False
    except Exception as e:
        logger.error(f"type: {type(e).__name__}, Node.js installation failed, {e}")
        return False


def install_nodejs_mac() -> bool:
    # 在 macOS 系统上通过 Homebrew 安装 Node.js
    logger.warning("Node.js is not installed.")
    logger.debug("Installing the latest version of Node.js for macOS...")
    try:
        result = subprocess.run(["brew", "install", "node"], capture_output=True)
        if result.returncode == 0:
            logger.debug('Node.js installation was successful. Restart for changes to take effect.')
            return True
        else:
            logger.error("Node.js installation failed")
            return False
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to install Node.js using Homebrew. {e}")
        logger.error("Please install Node.js manually or check your Homebrew installation.")
        return False
    except Exception as e:
        logger.error(f"An unexpected error occurred: {e}")
        return False


def get_package_manager() -> str:
    # 检测 Linux 发行版类型，返回包管理器标识
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
            f"Node.js auto installation is not supported on this platform: {current_platform}. Please install Node.js manually.")
        return False


def check_nodejs_installed() -> bool:
    # 检查系统是否已安装 Node.js
    try:
        result = subprocess.run(['node', '-v'], capture_output=True)
        version = result.stdout.strip()
        if result.returncode == 0 and version:
            return True
    except FileNotFoundError:
        pass
    return False


def check_node() -> bool:
    # 检查并确保 Node.js 已安装，未安装则自动安装
    if not check_nodejs_installed():
        return install_nodejs()
    return True
