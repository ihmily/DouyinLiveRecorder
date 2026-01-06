# -*- coding: utf-8 -*-
"""
Configuration module for VOD Player backend.

Reads settings from existing config.ini and tos_credentials.ini files.
"""
import os
import configparser
from functools import lru_cache
from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    """Application settings with environment variable support."""

    # Database
    database_url: str = ""

    # TOS (Volcano Engine Object Storage)
    tos_access_key: str = ""
    tos_secret_key: str = ""
    tos_endpoint: str = ""
    tos_region: str = ""
    tos_bucket: str = ""

    # VOD settings
    vod_enabled: bool = True
    url_expiration_seconds: int = 3600
    server_port: int = 8000

    # Paths
    config_path: str = ""
    tos_credentials_path: str = ""

    class Config:
        env_prefix = ""
        case_sensitive = False


def get_project_root() -> str:
    """Get the project root directory."""
    # vod-player/backend/app/config.py -> project root is 3 levels up
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


def load_config_ini(config_path: Optional[str] = None) -> configparser.ConfigParser:
    """Load the main config.ini file."""
    if config_path is None:
        config_path = os.path.join(get_project_root(), "config", "config.ini")

    config = configparser.ConfigParser()
    if os.path.exists(config_path):
        # Use utf-8-sig to handle BOM (Byte Order Mark) in config files
        config.read(config_path, encoding="utf-8-sig")
    return config


def load_tos_credentials(credentials_path: Optional[str] = None) -> dict:
    """Load TOS credentials from tos_credentials.ini."""
    if credentials_path is None:
        credentials_path = os.path.join(get_project_root(), "config", "tos_credentials.ini")

    credentials = {}
    if os.path.exists(credentials_path):
        config = configparser.ConfigParser()
        config.read(credentials_path, encoding="utf-8")

        if "TOS" in config:
            credentials["access_key"] = config.get("TOS", "access_key", fallback="")
            credentials["secret_key"] = config.get("TOS", "secret_key", fallback="")
            credentials["endpoint"] = config.get("TOS", "endpoint", fallback="")
            credentials["region"] = config.get("TOS", "region", fallback="")
            credentials["bucket"] = config.get("TOS", "bucket", fallback="")

    return credentials


@lru_cache()
def get_settings() -> Settings:
    """Get cached application settings."""
    project_root = get_project_root()
    config_path = os.path.join(project_root, "config", "config.ini")
    tos_credentials_path = os.path.join(project_root, "config", "tos_credentials.ini")

    # Load config.ini
    config = load_config_ini(config_path)

    # Load TOS credentials
    tos_creds = load_tos_credentials(tos_credentials_path)

    # Parse VOD settings
    vod_enabled = True
    url_expiration = 3600
    server_port = 8000

    if "VOD设置" in config:
        vod_section = config["VOD设置"]
        vod_enabled = vod_section.get("启用VOD(是/否)", "是") == "是"
        url_expiration = int(vod_section.get("签名有效期", "3600"))
        server_port = int(vod_section.get("服务端口", "8000"))

    # Database URL
    database_url = os.environ.get("DATABASE_URL", "")
    if not database_url:
        if "OSS设置" in config:
            database_url = config.get("OSS设置", "数据库URL", fallback="")
        if not database_url:
            # Default to SQLite
            data_dir = os.path.join(project_root, "data")
            os.makedirs(data_dir, exist_ok=True)
            database_url = f"sqlite:///{os.path.join(data_dir, 'recordings.db')}"

    return Settings(
        database_url=database_url,
        tos_access_key=tos_creds.get("access_key", ""),
        tos_secret_key=tos_creds.get("secret_key", ""),
        tos_endpoint=tos_creds.get("endpoint", ""),
        tos_region=tos_creds.get("region", ""),
        tos_bucket=tos_creds.get("bucket", ""),
        vod_enabled=vod_enabled,
        url_expiration_seconds=url_expiration,
        server_port=server_port,
        config_path=config_path,
        tos_credentials_path=tos_credentials_path,
    )
