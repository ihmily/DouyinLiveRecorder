# -*- coding: utf-8 -*-
"""
Test TOS delete API by uploading and deleting a test file.

This script validates that:
1. TOS credentials are valid
2. Upload operations work
3. Delete operations work (required for OSS cleanup feature)

Usage: python scripts/test_tos_delete.py
"""
import os
import sys
from datetime import datetime

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.storage.tos_uploader import TOSUploader

# Import logger
try:
    from src.logger import logger
except ImportError:
    import logging
    logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)s | %(message)s')
    logger = logging.getLogger(__name__)


def test_upload_and_delete() -> bool:
    """
    Test file upload followed by deletion.

    Returns:
        True if both upload and delete succeed, False otherwise
    """
    config_path = 'config/tos_credentials.ini'

    # Check config exists
    if not os.path.exists(config_path):
        logger.error(f"TOS config not found: {config_path}")
        return False

    try:
        # Initialize uploader
        uploader = TOSUploader(config_path=config_path)
        logger.info(f"TOS client initialized for bucket: {uploader.bucket}")
    except Exception as e:
        logger.error(f"Failed to initialize TOS client: {e}")
        return False

    # Generate unique test key
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    test_key = f"_test_delete/{timestamp}_test.txt"
    test_content = f"Test file created at {timestamp}\nThis file should be deleted immediately after creation."

    # Step 1: Upload test file
    logger.info(f"Step 1: Uploading test file to {test_key}")

    upload_success, upload_result = uploader.upload_content(
        content=test_content.encode('utf-8'),
        oss_key=test_key
    )

    if not upload_success:
        logger.error(f"Upload failed: {upload_result}")
        return False

    logger.info(f"Upload successful: {upload_result}")

    # Step 2: Delete test file
    logger.info(f"Step 2: Deleting test file {test_key}")

    delete_success = uploader.delete_object(test_key)

    if not delete_success:
        logger.error("Delete failed!")
        return False

    logger.info("Delete successful")

    logger.info("OSS delete API test passed!")
    return True


def main():
    """Main entry point."""
    print("=" * 60)
    print("TOS Delete API Test")
    print("=" * 60)
    print()

    success = test_upload_and_delete()

    print()
    print("=" * 60)
    if success:
        print("Result: PASS")
        print("OSS delete API is working correctly.")
        print("You can safely enable the OSS cleanup feature.")
    else:
        print("Result: FAIL")
        print("Please check:")
        print("  1. TOS credentials in config/tos_credentials.ini")
        print("  2. Bucket permissions allow DELETE operations")
        print("  3. Network connectivity to TOS endpoint")
    print("=" * 60)

    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
