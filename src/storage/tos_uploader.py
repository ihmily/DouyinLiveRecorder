# -*- coding: utf-8 -*-
"""
TOS (Volcano Engine Object Storage) upload client.
Based on existing scripts/test_tos.py pattern.

Author: DouyinLiveRecorder
Date: 2025-12-16
"""
import os
from datetime import datetime
import configparser
import tos
from tos.exceptions import TosClientError, TosServerError


class TOSUploader:
    """Wrapper for TOS SDK operations."""

    def __init__(
        self,
        config_path: str | None = None,
        access_key: str | None = None,
        secret_key: str | None = None,
        endpoint: str | None = None,
        region: str | None = None,
        bucket: str | None = None
    ):
        """
        Initialize TOS client.

        Priority: explicit params > config file

        Args:
            config_path: Path to tos_credentials.ini
            access_key: TOS access key
            secret_key: TOS secret key
            endpoint: TOS endpoint (e.g., tos-cn-beijing.ivolces.com)
            region: TOS region (e.g., cn-beijing)
            bucket: Default bucket name
        """
        # Import logger
        try:
            from ..logger import logger
            self.logger = logger
        except ImportError:
            import logging
            self.logger = logging.getLogger(__name__)

        # Load from config if not all params provided
        if config_path and not all([access_key, secret_key, endpoint, region, bucket]):
            cfg = self._load_config(config_path)
            access_key = access_key or cfg.get('access_key')
            secret_key = secret_key or cfg.get('secret_key')
            endpoint = endpoint or cfg.get('endpoint')
            region = region or cfg.get('region')
            bucket = bucket or cfg.get('bucket')

        if not all([access_key, secret_key, endpoint, region, bucket]):
            raise ValueError("Missing required TOS configuration")

        self.bucket = bucket
        self.endpoint = endpoint
        self.region = region

        # Clear proxy environment for internal network access
        for key in ['http_proxy', 'https_proxy', 'HTTP_PROXY', 'HTTPS_PROXY']:
            os.environ.pop(key, None)

        self.client = tos.TosClientV2(
            ak=access_key,
            sk=secret_key,
            endpoint=endpoint,
            region=region
        )
        self.logger.debug(f"TOS client initialized for bucket: {bucket}")

    @staticmethod
    def _load_config(config_path: str) -> dict:
        """Load TOS config from ini file."""
        if not os.path.exists(config_path):
            raise FileNotFoundError(f"TOS config not found: {config_path}")

        config = configparser.ConfigParser()
        config.read(config_path, encoding='utf-8-sig')

        return {
            'endpoint': config.get('tos', 'endpoint'),
            'region': config.get('tos', 'region'),
            'bucket': config.get('tos', 'bucket'),
            'access_key': config.get('tos', 'access_key'),
            'secret_key': config.get('tos', 'secret_key'),
        }

    def generate_oss_key(
        self,
        platform: str,
        anchor_name: str,
        filename: str,
        date: datetime | None = None
    ) -> str:
        """
        Generate OSS object key.

        Format: {platform}/{date}/{anchor_name}/{filename}
        Example: 抖音直播/2024-01-15/张三/张三_2024-01-15_10-30-00.ts
        """
        if date is None:
            date = datetime.now()
        date_str = date.strftime("%Y-%m-%d")
        return f"{platform}/{date_str}/{anchor_name}/{filename}"

    def upload_file(
        self,
        local_path: str,
        oss_key: str,
        bucket: str | None = None
    ) -> tuple[bool, str | None]:
        """
        Upload file to TOS.

        Args:
            local_path: Local file path
            oss_key: Object key in TOS
            bucket: Bucket name (uses default if not specified)

        Returns:
            (success: bool, oss_path or error_message)
        """
        bucket = bucket or self.bucket

        if not os.path.exists(local_path):
            return False, f"Local file not found: {local_path}"

        try:
            self.client.put_object_from_file(
                bucket=bucket,
                key=oss_key,
                file_path=local_path
            )
            oss_path = f"tos://{bucket}/{oss_key}"
            self.logger.debug(f"Upload success: {local_path} -> {oss_path}")
            return True, oss_path

        except TosClientError as e:
            error_msg = f"TOS client error: {e.message}"
            self.logger.error(error_msg)
            return False, error_msg

        except TosServerError as e:
            error_msg = f"TOS server error: {e.code} - {e.message}"
            self.logger.error(error_msg)
            return False, error_msg

        except Exception as e:
            error_msg = f"Upload failed: {str(e)}"
            self.logger.error(error_msg)
            return False, error_msg

    def upload_content(
        self,
        content: bytes | str,
        oss_key: str,
        bucket: str | None = None
    ) -> tuple[bool, str | None]:
        """
        Upload content (bytes or string) to TOS.

        Args:
            content: Content to upload
            oss_key: Object key in TOS
            bucket: Bucket name (uses default if not specified)

        Returns:
            (success: bool, oss_path or error_message)
        """
        bucket = bucket or self.bucket

        try:
            self.client.put_object(
                bucket=bucket,
                key=oss_key,
                content=content
            )
            oss_path = f"tos://{bucket}/{oss_key}"
            self.logger.debug(f"Upload content success: {oss_path}")
            return True, oss_path

        except TosClientError as e:
            error_msg = f"TOS client error: {e.message}"
            self.logger.error(error_msg)
            return False, error_msg

        except TosServerError as e:
            error_msg = f"TOS server error: {e.code} - {e.message}"
            self.logger.error(error_msg)
            return False, error_msg

        except Exception as e:
            error_msg = f"Upload failed: {str(e)}"
            self.logger.error(error_msg)
            return False, error_msg

    def check_bucket_access(self) -> bool:
        """Verify bucket is accessible."""
        try:
            self.client.head_bucket(self.bucket)
            return True
        except Exception as e:
            self.logger.error(f"Bucket access check failed: {e}")
            return False

    def delete_object(self, oss_key: str, bucket: str | None = None) -> bool:
        """Delete object from TOS."""
        bucket = bucket or self.bucket
        try:
            self.client.delete_object(bucket, oss_key)
            return True
        except Exception as e:
            self.logger.error(f"Delete failed: {e}")
            return False

    def get_file_size(self, local_path: str) -> int | None:
        """Get file size in bytes."""
        try:
            return os.path.getsize(local_path)
        except OSError:
            return None
