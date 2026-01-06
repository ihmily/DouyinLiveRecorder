# -*- coding: utf-8 -*-
"""
TOS (Volcano Engine Object Storage) presigned URL generation service.

Generates time-limited signed URLs for video playback.
"""
import os
import sys

# Add project root to path (vod-player/backend/app/services/tos_sign.py -> 5 levels up)
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
sys.path.insert(0, project_root)

from app.config import get_settings

# TOS SDK import with fallback
try:
    from tos import TosClientV2, HttpMethodType
    TOS_AVAILABLE = True
except ImportError:
    TOS_AVAILABLE = False
    TosClientV2 = None
    HttpMethodType = None


def get_tos_client():
    """
    Get TOS client instance for presigned URL generation.

    Uses tos_s3_endpoint (public endpoint) for URL generation.
    This ensures generated URLs are accessible from public networks.
    """
    if not TOS_AVAILABLE:
        raise RuntimeError("TOS SDK not available. Install with: pip install tos")

    settings = get_settings()

    # Use s3_endpoint for URL generation (public endpoint)
    endpoint = settings.tos_s3_endpoint or settings.tos_endpoint
    if not all([settings.tos_access_key, settings.tos_secret_key, endpoint]):
        raise RuntimeError("TOS credentials not configured. Check config/tos_credentials.ini")

    return TosClientV2(
        ak=settings.tos_access_key,
        sk=settings.tos_secret_key,
        endpoint=endpoint,
        region=settings.tos_region,
    )


def generate_presigned_url(
    bucket: str,
    key: str,
    expires: int = 3600,
    content_disposition: str = "inline"
) -> str:
    """
    Generate a presigned URL for object access.

    Args:
        bucket: TOS bucket name
        key: Object key (path) in the bucket
        expires: URL validity in seconds (default 1 hour)
        content_disposition: Content-Disposition header value (inline for browser playback)

    Returns:
        Presigned URL string

    Raises:
        RuntimeError: If TOS SDK is not available or credentials are missing
    """
    settings = get_settings()

    # Use configured bucket if not specified
    if not bucket:
        bucket = settings.tos_bucket

    if not bucket:
        raise ValueError("Bucket name is required")

    if not key:
        raise ValueError("Object key is required")

    client = get_tos_client()

    # Generate presigned URL with query parameters
    query = {}
    if content_disposition:
        query["response-content-disposition"] = content_disposition

    url = client.pre_signed_url(
        HttpMethodType.Http_Method_Get,
        bucket,
        key,
        expires=expires,
        query=query if query else None
    ).signed_url

    return url


def check_tos_connection() -> bool:
    """
    Check if TOS connection is working.

    Returns:
        True if connection is successful, False otherwise
    """
    if not TOS_AVAILABLE:
        return False

    try:
        settings = get_settings()
        endpoint = settings.tos_s3_endpoint or settings.tos_endpoint
        if not all([settings.tos_access_key, settings.tos_secret_key, endpoint]):
            return False

        client = get_tos_client()
        # Try to list buckets as a connection test
        client.list_buckets()
        return True
    except Exception:
        return False
