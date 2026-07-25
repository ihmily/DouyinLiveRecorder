# tests/conftest.py
from pathlib import Path

import pytest


@pytest.fixture
def tmp_url_config(tmp_path: Path) -> Path:
    """临时 URL_config.ini，含示例直播间与注释行。"""
    p = tmp_path / "URL_config.ini"
    p.write_text(
        "https://live.douyin.com/123\n"
        "超清,https://live.bilibili.com/456\n"
        "# https://www.huya.com/789\n"
        "高清,https://www.douyu.com/012,主播: 测试主播\n"
        "超清，https://www.huya.com/001，主播：全角测试\n",
        encoding="utf-8",
    )
    return p


@pytest.fixture
def tmp_config_ini(tmp_path: Path) -> Path:
    """临时 config.ini，含录制设置与 [Web] 节。"""
    p = tmp_path / "config.ini"
    p.write_text(
        "[录制设置]\n"
        "循环时间(秒) = 300\n"
        "原画|超清|高清|标清|流畅 = 原画\n"
        "[推送配置]\n"
        "直播状态推送渠道 = \n"
        "[Cookie]\n"
        "抖音cookie = abc123\n"
        "[账号密码]\n"
        "sooplive账号 = \n"
        "[Authorization]\n"
        "popkontv_token = \n"
        "[Web]\n"
        "web_host = 0.0.0.0\n"
        "web_port = 8000\n"
        "web_auth_enable = false\n"
        "web_password = \n"
        "web_token_expiry = 86400\n"
        "web_show_console = true\n",
        encoding="utf-8",
    )
    return p
