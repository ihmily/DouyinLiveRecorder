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
import requests
import re
import distro
from tqdm import tqdm
from .logger import logger

current_platform = platform.system()


def install_nodejs_windows():
    try:
        logger.warning("Node.js is not installed.")
        logger.debug("Installing the stable version of Node.js for Windows...")
        response = requests.get('https://nodejs.cn/download/')
        if response.status_code == 200:
            match = re.search('href="(https://npmmirror.com/mirrors/node/v.*?/node-v.*?.msi)"> <svg class="d',
                              response.text)
            if match:
                url = match.group(1)
                version = url.rsplit('/', maxsplit=2)[1]
            else:
                logger.error("Failed to retrieve the download URL for the latest version of Node.js...")
                return

            temp_dir = os.path.split(os.path.realpath(sys.argv[0]))[0]
            file_path = os.path.join(temp_dir, url.rsplit('/', maxsplit=1)[-1])
            if os.path.exists(file_path):
                logger.debug("Node.js installation file already exists, start install...")
            else:
                response = requests.get(url, stream=True)
                total_size = int(response.headers.get('Content-Length', 0))
                block_size = 1024

                with tqdm(total=total_size, unit="B", unit_scale=True,
                          ncols=100, desc=f'Downloading Node.js ({version})') as t:
                    with open(file_path, 'wb') as f:
                        for data in response.iter_content(block_size):
                            t.update(len(data))
                            f.write(data)

            powershell_command = f"Start-Process 'msiexec' -ArgumentList '/i {file_path} /quiet' -Wait -NoNewWindow"
            result = subprocess.run(["powershell", "-Command", powershell_command], capture_output=True, text=True)
            if result.returncode == 0:
                logger.debug('Node.js installation was successful. Restart for changes to take effect.')
                return True
            else:
                logger.error("Node.js installation failed")
        else:
            logger.error("Failed to retrieve the stable Node.js version page")

    except Exception as e:
        logger.error(f"type: {type(e).__name__}, Node.js installation failed")


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


def install_nodejs():
    if current_platform == "Windows":
        return install_nodejs_windows()
    elif current_platform == "Linux":
        dist = distro.id()
        if dist.lower() == "centos":
            return install_nodejs_centos()
        elif dist.lower() == "ubuntu":
            return install_nodejs_ubuntu()
    elif current_platform == "Darwin":
        return install_nodejs_mac()
    else:
        logger.debug(f"Node.js auto installation is not supported on this platform: {current_platform}. "
                     f"Please install Node.js manually.")


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


def check_nodejs_installed():
    try:
        result = subprocess.run(['node', '-v'], capture_output=True)
        version = result.stdout.strip()
        if result.returncode == 0 and version:
            return True
    except FileNotFoundError:
        pass
    return False


def check_node():
    res = check_nodejs_installed()
    if not res:
        return install_nodejs()
