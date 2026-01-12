# -*- coding: utf-8 -*-
"""
TOS (Volcano Engine Object Storage) connectivity validator.
Validates TOS credentials and performs read/write tests on startup.

Author: DouyinLiveRecorder
Date: 2026-01-08
"""
import os
import configparser
from enum import Enum
from dataclasses import dataclass
from typing import Optional


class ValidationResult(Enum):
    """TOS validation result codes."""
    SUCCESS = "success"
    MISSING_CONFIG = "missing_config"
    MISSING_CREDENTIALS = "missing_credentials"
    EMPTY_ACCESS_KEY = "empty_access_key"
    EMPTY_SECRET_KEY = "empty_secret_key"
    MISSING_ENDPOINT = "missing_endpoint"
    MISSING_BUCKET = "missing_bucket"
    AUTH_FAILED = "auth_failed"
    BUCKET_NOT_FOUND = "bucket_not_found"
    NETWORK_ERROR = "network_error"
    READ_WRITE_FAILED = "read_write_failed"
    UNKNOWN_ERROR = "unknown_error"


@dataclass
class TOSConfig:
    """TOS configuration data."""
    access_key: str
    secret_key: str
    endpoint: str
    region: str
    bucket: str


def get_tos_credentials_path() -> str:
    """Get the path to tos_credentials.ini file."""
    # Check environment variable first
    env_path = os.environ.get('TOS_CREDENTIALS_PATH')
    if env_path and os.path.exists(env_path):
        return env_path

    # Check config directory
    config_paths = [
        '/app/config/tos_credentials.ini',  # Docker container path
        'config/tos_credentials.ini',        # Local path
        './config/tos_credentials.ini',      # Relative path
    ]

    for path in config_paths:
        if os.path.exists(path):
            return path

    return 'config/tos_credentials.ini'  # Default path


def load_tos_config(config_path: str) -> Optional[TOSConfig]:
    """
    Load TOS configuration from ini file.

    Args:
        config_path: Path to tos_credentials.ini

    Returns:
        TOSConfig if successful, None if file doesn't exist or is invalid
    """
    if not os.path.exists(config_path):
        return None

    config = configparser.ConfigParser()
    try:
        config.read(config_path, encoding='utf-8-sig')
    except Exception:
        return None

    # Try both uppercase and lowercase section names for compatibility
    section = None
    for s in ['TOS', 'tos', 'credentials', 'Credentials']:
        if config.has_section(s):
            section = s
            break

    if section is None:
        return None

    try:
        return TOSConfig(
            access_key=config.get(section, 'access_key', fallback=''),
            secret_key=config.get(section, 'secret_key', fallback=''),
            endpoint=config.get(section, 'endpoint', fallback=''),
            region=config.get(section, 'region', fallback=''),
            bucket=config.get(section, 'bucket', fallback=''),
        )
    except Exception:
        return None


def validate_tos_connectivity(config_path: Optional[str] = None) -> tuple[ValidationResult, str]:
    """
    Validate TOS credentials and connectivity.

    Performs:
    1. Check if credentials file exists
    2. Parse and validate required fields (access_key, secret_key, endpoint, bucket)
    3. Test bucket access (HeadBucket)
    4. Test read/write permissions (PutObject/GetObject/DeleteObject)

    Args:
        config_path: Path to tos_credentials.ini (optional, uses default if not provided)

    Returns:
        Tuple of (ValidationResult, message_string)
    """
    if config_path is None:
        config_path = get_tos_credentials_path()

    # Step 1: Check if config file exists
    if not os.path.exists(config_path):
        return (
            ValidationResult.MISSING_CONFIG,
            f"TOS: credentials not configured in {config_path} - OSS upload disabled"
        )

    # Step 2: Load and validate config
    tos_config = load_tos_config(config_path)

    if tos_config is None:
        return (
            ValidationResult.MISSING_CONFIG,
            f"TOS: invalid config format in {config_path} - OSS upload disabled"
        )

    # Check required fields
    if not tos_config.access_key:
        return (
            ValidationResult.EMPTY_ACCESS_KEY,
            f"TOS: access_key is empty in {config_path} - OSS upload disabled"
        )

    if not tos_config.secret_key:
        return (
            ValidationResult.EMPTY_SECRET_KEY,
            f"TOS: secret_key is empty in {config_path} - OSS upload disabled"
        )

    if not tos_config.endpoint:
        return (
            ValidationResult.MISSING_ENDPOINT,
            f"TOS: endpoint is missing in {config_path} - OSS upload disabled"
        )

    if not tos_config.bucket:
        return (
            ValidationResult.MISSING_BUCKET,
            f"TOS: bucket is missing in {config_path} - OSS upload disabled"
        )

    # Step 3: Try to connect to TOS
    try:
        import tos
        from tos.exceptions import TosClientError, TosServerError
    except ImportError:
        return (
            ValidationResult.UNKNOWN_ERROR,
            "TOS: tos SDK not installed - OSS upload disabled"
        )

    # Clear proxy environment for internal network access
    for key in ['http_proxy', 'https_proxy', 'HTTP_PROXY', 'HTTPS_PROXY', 'all_proxy', 'ALL_PROXY']:
        os.environ.pop(key, None)

    try:
        client = tos.TosClientV2(
            ak=tos_config.access_key,
            sk=tos_config.secret_key,
            endpoint=tos_config.endpoint,
            region=tos_config.region or 'cn-beijing'
        )
    except Exception as e:
        return (
            ValidationResult.UNKNOWN_ERROR,
            f"TOS: failed to create client - {str(e)}"
        )

    # Step 4: Test bucket access (HeadBucket)
    try:
        client.head_bucket(tos_config.bucket)
    except TosServerError as e:
        if e.status_code == 403:
            return (
                ValidationResult.AUTH_FAILED,
                f"TOS: authentication failed for endpoint {tos_config.endpoint} - check access_key/secret_key"
            )
        elif e.status_code == 404:
            return (
                ValidationResult.BUCKET_NOT_FOUND,
                f"TOS: bucket '{tos_config.bucket}' not found in region {tos_config.region}"
            )
        else:
            return (
                ValidationResult.UNKNOWN_ERROR,
                f"TOS: server error {e.status_code} - {e.message}"
            )
    except TosClientError as e:
        return (
            ValidationResult.NETWORK_ERROR,
            f"TOS: cannot reach endpoint {tos_config.endpoint} - {e.message}"
        )
    except Exception as e:
        error_str = str(e).lower()
        if 'timeout' in error_str or 'connection' in error_str or 'network' in error_str:
            return (
                ValidationResult.NETWORK_ERROR,
                f"TOS: cannot reach endpoint {tos_config.endpoint} - will retry periodically"
            )
        return (
            ValidationResult.UNKNOWN_ERROR,
            f"TOS: unexpected error - {str(e)}"
        )

    # Step 5: Test read/write permissions
    test_key = ".tos-connectivity-test"
    test_content = b"DouyinLiveRecorder TOS connectivity test"

    try:
        # Write test
        client.put_object(
            bucket=tos_config.bucket,
            key=test_key,
            content=test_content
        )

        # Read test
        response = client.get_object(
            bucket=tos_config.bucket,
            key=test_key
        )
        read_content = response.read()

        # Verify content
        if read_content != test_content:
            return (
                ValidationResult.READ_WRITE_FAILED,
                "TOS: read/write verification failed - content mismatch"
            )

        # Cleanup test file
        client.delete_object(
            bucket=tos_config.bucket,
            key=test_key
        )

    except TosServerError as e:
        if e.status_code == 403:
            return (
                ValidationResult.AUTH_FAILED,
                f"TOS: write permission denied for bucket '{tos_config.bucket}'"
            )
        return (
            ValidationResult.READ_WRITE_FAILED,
            f"TOS: read/write test failed - {e.message}"
        )
    except Exception as e:
        return (
            ValidationResult.READ_WRITE_FAILED,
            f"TOS: read/write test failed - {str(e)}"
        )

    # All tests passed
    return (
        ValidationResult.SUCCESS,
        f"TOS: connectivity verified - OSS upload enabled (bucket: {tos_config.bucket})"
    )


def validate_and_log(config_path: Optional[str] = None) -> ValidationResult:
    """
    Validate TOS connectivity and log the result.

    This is the main entry point called from docker-entrypoint.sh.

    Args:
        config_path: Path to tos_credentials.ini (optional)

    Returns:
        ValidationResult enum value
    """
    # Import logger - use loguru if available, fallback to print
    try:
        from .logger import logger
        log_info = logger.info
        log_warning = logger.warning
        log_error = logger.error
    except ImportError:
        try:
            from loguru import logger
            log_info = logger.info
            log_warning = logger.warning
            log_error = logger.error
        except ImportError:
            def log_info(msg): print(f"[INFO] {msg}")
            def log_warning(msg): print(f"[WARNING] {msg}")
            def log_error(msg): print(f"[ERROR] {msg}")

    result, message = validate_tos_connectivity(config_path)

    if result == ValidationResult.SUCCESS:
        log_info(message)
    elif result in [ValidationResult.MISSING_CONFIG, ValidationResult.MISSING_CREDENTIALS,
                    ValidationResult.EMPTY_ACCESS_KEY, ValidationResult.EMPTY_SECRET_KEY]:
        log_warning(message)
    elif result == ValidationResult.NETWORK_ERROR:
        log_warning(message)
    else:
        log_error(message)

    # Set environment variable for main.py to check
    os.environ['TOS_VALIDATION_RESULT'] = result.value

    return result


# Allow running as standalone script
if __name__ == "__main__":
    result = validate_and_log()
    print(f"\nValidation result: {result.value}")
