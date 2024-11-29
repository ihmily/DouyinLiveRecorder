# -*- coding: utf-8 -*-

"""
Author: Hmily
GitHub:https://github.com/ihmily
Copyright (c) 2024 by Hmily, All Rights Reserved.
"""

import os
import subprocess
import sys
import platform
import zipfile
from pathlib import Path
import requests
import re
import distro
from tqdm import tqdm
from .logger import logger

current_platform = platform.system()
execute_dir = os.path.split(os.path.realpath(sys.argv[0]))[0]
current_env_path = os.environ.get('PATH')


def unzip_file(zip_path: str | Path, extract_to: str | Path, delete: bool = True) -> None:
    if not os.path.exists(extract_to):
        os.makedirs(extract_to)

    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
        zip_ref.extractall(extract_to)

    if delete and os.path.exists(zip_path):
        os.remove(zip_path)


def install_nodejs_windows():
    try:
        logger.warning("Node.js is not installed.")
        logger.debug("Installing the stable version of Node.js for Windows...")
        response = requests.get('https://nodejs.cn/download/')
        if response.status_code == 200:
            match = re.search('https://npmmirror.com/mirrors/node/(v.*?)/node-(v.*?)-x64.msi',
                              response.text)
            if match:
                version = match.group(1)
                system_bit = 'x64' if '32' not in platform.machine() else 'x86'
                url = f'https://npmmirror.com/mirrors/node/{version}/node-{version}-win-{system_bit}.zip'
            else:
                logger.error("Failed to retrieve the download URL for the latest version of Node.js...")
                return

            full_file_name = url.rsplit('/', maxsplit=1)[-1]
            zip_file_path = Path(execute_dir) / full_file_name

            if Path(zip_file_path).exists():
                logger.debug("Node.js installation file already exists, start install...")
            else:
                response = requests.get(url, stream=True)
                total_size = int(response.headers.get('Content-Length', 0))
                block_size = 1024

                with tqdm(total=total_size, unit="B", unit_scale=True,
                          ncols=100, desc=f'Downloading Node.js ({version})') as t:
                    with open(zip_file_path, 'wb') as f:
                        for data in response.iter_content(block_size):
                            t.update(len(data))
                            f.write(data)

            unzip_file(zip_file_path, execute_dir)
            extract_dir_path = str(zip_file_path).rsplit('.', maxsplit=1)[0]
            f_path, f_name = os.path.splitext(zip_file_path)
            new_extract_dir_path = Path(f_path).parent / 'node'
            if Path(extract_dir_path).exists() and not Path(new_extract_dir_path).exists():
                os.rename(extract_dir_path, new_extract_dir_path)
                os.environ['PATH'] = execute_dir + '/node' + os.pathsep + current_env_path
                result = subprocess.run(["node", "-v"], capture_output=True)
                if result.returncode == 0:
                    logger.debug('Node.js installation was successful. Restart for changes to take effect')
                else:
                    logger.debug('Node.js installation failed')
                return True
        else:
            logger.error("Failed to retrieve the Node.js version page")

    except Exception as e:
        logger.error(f"type: {type(e).__name__}, Node.js installation failed {e}")


def install_nodejs_centos():
    try:
        logger.warning("Node.js is not installed.")
        logger.debug("Installing the latest version of Node.js for CentOS...")
        result = subprocess.run('curl -fsSL https://mirrors.tuna.tsinghua.edu.cn/nodesource/rpm/setup_lts.x | '
                                'bash -', shell=True, capture_output=True)
        if result.returncode != 0:
            logger.error("Failed to run NodeSource installation script")
            return

        result = subprocess.run(['yum', 'install', '-y', 'epel-release'], capture_output=True)
        if result.returncode != 0:
            logger.error("Failed to install EPEL repository")
            return

        result = subprocess.run(['yum', 'install', '-y', 'nodejs'], capture_output=True)
        if result.returncode == 0:
            logger.debug('Node.js installation was successful. Restart for changes to take effect.')
            return True
        else:
            logger.error("Node.js installation failed")

    except Exception as e:
        logger.error(f"type: {type(e).__name__}, Node.js installation failed {e}")


def install_nodejs_ubuntu():
    try:
        logger.warning("Node.js is not installed.")
        logger.debug("Installing the latest version of Node.js for Ubuntu...")
        install_script = 'curl -fsSL https://deb.nodesource.com/setup_lts.x | bash -'
        result = subprocess.run(install_script, shell=True, capture_output=True)
        if result.returncode != 0:
            logger.error("Failed to run NodeSource installation script")
            return

        install_command = ['apt', 'install', '-y', 'nodejs']
        result = subprocess.run(install_command, capture_output=True)
        if result.returncode == 0:
            logger.debug('Node.js installation was successful. Restart for changes to take effect.')
            return True
        else:
            logger.error("Node.js installation failed")
    except Exception as e:
        logger.error(f"type: {type(e).__name__}, Node.js installation failed, {e}")


def install_nodejs_mac():
    logger.warning("Node.js is not installed.")
    logger.debug("Installing the latest version of Node.js for macOS...")
    try:
        result = subprocess.run(["brew", "install", "node"], capture_output=True)
        if result.returncode == 0:
            logger.debug('Node.js installation was successful. Restart for changes to take effect.')
            return True
        else:
            logger.error("Node.js installation failed")
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to install Node.js using Homebrew. {e}")
        logger.error("Please install Node.js manually or check your Homebrew installation.")
    except Exception as e:
        logger.error(f"An unexpected error occurred: {e}")


def get_package_manager():
    dist_id = distro.id()
    if dist_id in ["centos", "fedora", "rhel", "amzn", "oracle", "scientific", "opencloudos", "alinux"]:
        return "RHS"
    else:
        return "DBS"


def install_nodejs() -> bool:
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
        logger.debug(f"Node.js auto installation is not supported on this platform: {current_platform}. "
                     f"Please install Node.js manually.")
        return False


def ensure_nodejs_installed(func):
    def wrapper(*args, **kwargs):
        try:
            result = subprocess.run(['node', '-v'], capture_output=True)
            version = result.stdout.strip()
            if result.returncode == 0 and version:
                return func(*args, **kwargs)
        except FileNotFoundError:
            pass
        return False

    def wrapped_func(*args, **kwargs):
        if sys.version_info >= (3, 7):
            res = wrapper(*args, **kwargs)
        else:
            res = wrapper(*args, **kwargs)
        if not res:
            install_nodejs()
            res = wrapper(*args, **kwargs)

        if not res:
            raise RuntimeError("Node.js is not installed.")

        return func(*args, **kwargs)

    return wrapped_func


def check_nodejs_installed() -> bool:
    try:
        result = subprocess.run(['node', '-v'], capture_output=True)
        version = result.stdout.strip()
        if result.returncode == 0 and version:
            return True
    except FileNotFoundError:
        pass
    return False


def check_node() -> bool:
    if not check_nodejs_installed():
        return install_nodejs()
