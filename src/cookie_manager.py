# -*- encoding: utf-8 -*-
"""
[DLR][COOKIE] Cookie Management and Sanitization
Author: Claude Code
Date: 2025-11-05
Function: Cookie cleaning, validation, and platform-specific processing
"""

import re
from typing import Optional, Dict
from urllib.parse import unquote

try:
    from .dlr_logger import dlr_logger, Platform, log_cookie_soop_sanitize
except ImportError:
    from dlr_logger import dlr_logger, Platform, log_cookie_soop_sanitize


class CookieManager:
    """
    # [DLR][COOKIE] Cookie Manager for all platforms

    Features:
    - SOOP cookie sanitization (remove invalid characters)
    - Cookie validation
    - Cookie parsing and formatting
    - Platform-specific cookie processing
    """

    def __init__(self):
        """Initialize Cookie Manager"""
        dlr_logger.info_cookie("Cookie Manager initialized")

        # [DLR][COOKIE][SOOP] Invalid characters in SOOP cookies
        self.soop_invalid_chars = [
            '\n', '\r', '\t', '\x00', '\x01', '\x02', '\x03', '\x04',
            '\x05', '\x06', '\x07', '\x08', '\x0b', '\x0c', '\x0e',
            '\x0f', '\x10', '\x11', '\x12', '\x13', '\x14', '\x15',
            '\x16', '\x17', '\x18', '\x19', '\x1a', '\x1b', '\x1c',
            '\x1d', '\x1e', '\x1f'
        ]

    def sanitize_soop_cookie(self, cookie: Optional[str]) -> Optional[str]:
        """
        # [DLR][COOKIE][SOOP] SOOP_SANITIZE_APPLIED
        Clean invalid characters from SOOP cookie

        SOOP cookies may contain:
        - Newlines (\n, \r)
        - Control characters
        - Invalid UTF-8 sequences

        Args:
            cookie: Raw cookie string

        Returns:
            Cleaned cookie string or None if empty
        """
        if not cookie or not cookie.strip():
            return None

        original_length = len(cookie)
        cleaned = cookie

        # [DLR][COOKIE] Remove invalid characters
        for char in self.soop_invalid_chars:
            cleaned = cleaned.replace(char, '')

        # [DLR][COOKIE] Remove extra whitespace
        cleaned = ' '.join(cleaned.split())

        # [DLR][COOKIE] Remove duplicate semicolons
        cleaned = re.sub(r';+', ';', cleaned)

        # [DLR][COOKIE] Ensure proper formatting
        if cleaned and not cleaned.endswith(';'):
            # Don't add semicolon if it's not there originally
            pass

        if len(cleaned) != original_length:
            log_cookie_soop_sanitize()
            dlr_logger.debug_cookie(
                f"Sanitized SOOP cookie: {original_length} -> {len(cleaned)} chars",
                Platform.SOOP
            )

        return cleaned if cleaned else None

    def validate_cookie(self, cookie: Optional[str], platform: Platform = None) -> bool:
        """
        # [DLR][COOKIE] Validate cookie format

        Basic validation:
        - Not empty
        - Contains '=' character
        - Contains at least one cookie key-value pair

        Args:
            cookie: Cookie string to validate
            platform: Platform identifier

        Returns:
            True if valid, False otherwise
        """
        if not cookie or not cookie.strip():
            dlr_logger.warn_cookie("Cookie is empty", platform)
            return False

        # Check for basic cookie format
        if '=' not in cookie:
            dlr_logger.warn_cookie("Cookie missing '=' separator", platform)
            return False

        # Check for at least one valid cookie pair
        pairs = cookie.split(';')
        valid_pairs = 0
        for pair in pairs:
            pair = pair.strip()
            if pair and '=' in pair:
                key, value = pair.split('=', 1)
                if key.strip() and value.strip():
                    valid_pairs += 1

        if valid_pairs == 0:
            dlr_logger.warn_cookie("No valid cookie pairs found", platform)
            return False

        dlr_logger.debug_cookie(f"Cookie validated: {valid_pairs} pairs", platform)
        return True

    def parse_cookie(self, cookie: str) -> Dict[str, str]:
        """
        # [DLR][COOKIE] Parse cookie string into dictionary

        Args:
            cookie: Cookie string (format: "key1=value1; key2=value2")

        Returns:
            Dictionary of cookie key-value pairs
        """
        cookie_dict = {}

        if not cookie:
            return cookie_dict

        pairs = cookie.split(';')
        for pair in pairs:
            pair = pair.strip()
            if '=' in pair:
                key, value = pair.split('=', 1)
                key = key.strip()
                value = value.strip()
                if key and value:
                    cookie_dict[key] = value

        return cookie_dict

    def format_cookie(self, cookie_dict: Dict[str, str]) -> str:
        """
        # [DLR][COOKIE] Format dictionary into cookie string

        Args:
            cookie_dict: Dictionary of cookie key-value pairs

        Returns:
            Cookie string (format: "key1=value1; key2=value2")
        """
        return '; '.join([f"{k}={v}" for k, v in cookie_dict.items()])

    def extract_auth_token(self, cookie: Optional[str], token_name: str = "AuthTicket",
                          platform: Platform = None) -> Optional[str]:
        """
        # [DLR][COOKIE] Extract authentication token from cookie

        Args:
            cookie: Cookie string
            token_name: Name of the token to extract (default: "AuthTicket")
            platform: Platform identifier

        Returns:
            Token value or None if not found
        """
        if not cookie:
            return None

        cookie_dict = self.parse_cookie(cookie)
        token = cookie_dict.get(token_name)

        if token:
            dlr_logger.debug_cookie(f"Extracted {token_name} token", platform)
        else:
            dlr_logger.warn_cookie(f"{token_name} not found in cookie", platform)

        return token

    def has_auth_token(self, cookie: Optional[str], platform: Platform = None) -> bool:
        """
        # [DLR][COOKIE] Check if cookie contains authentication token

        Common auth token names:
        - AuthTicket (SOOP)
        - PdboxTicket (PandaLive)
        - sessionid (Generic)

        Args:
            cookie: Cookie string
            platform: Platform identifier

        Returns:
            True if auth token found, False otherwise
        """
        if not cookie:
            return False

        auth_tokens = ['AuthTicket', 'PdboxTicket', 'sessionid', 'token', 'access_token']

        cookie_lower = cookie.lower()
        for token_name in auth_tokens:
            if token_name.lower() in cookie_lower:
                dlr_logger.debug_cookie(f"Found auth token: {token_name}", platform)
                return True

        return False

    def merge_cookies(self, old_cookie: Optional[str], new_cookie: Optional[str],
                     platform: Platform = None) -> str:
        """
        # [DLR][COOKIE] Merge two cookie strings
        New cookie values override old ones

        Args:
            old_cookie: Existing cookie string
            new_cookie: New cookie string
            platform: Platform identifier

        Returns:
            Merged cookie string
        """
        old_dict = self.parse_cookie(old_cookie or "")
        new_dict = self.parse_cookie(new_cookie or "")

        # Merge: new values override old
        merged_dict = {**old_dict, **new_dict}

        merged_cookie = self.format_cookie(merged_dict)

        if old_cookie and new_cookie:
            dlr_logger.debug_cookie(
                f"Merged cookies: {len(old_dict)} + {len(new_dict)} = {len(merged_dict)} pairs",
                platform
            )

        return merged_cookie

    def decode_url_encoded_cookie(self, cookie: str) -> str:
        """
        # [DLR][COOKIE] Decode URL-encoded cookie values

        Args:
            cookie: Cookie string with URL-encoded values

        Returns:
            Decoded cookie string
        """
        if not cookie:
            return cookie

        cookie_dict = self.parse_cookie(cookie)
        decoded_dict = {}

        for key, value in cookie_dict.items():
            try:
                decoded_value = unquote(value)
                decoded_dict[key] = decoded_value
            except Exception:
                decoded_dict[key] = value  # Keep original if decode fails

        return self.format_cookie(decoded_dict)

    def get_cookie_info(self, cookie: Optional[str], platform: Platform = None) -> Dict:
        """
        # [DLR][COOKIE] Get detailed cookie information

        Returns:
            Dictionary with:
            - valid: Whether cookie is valid
            - pairs_count: Number of cookie pairs
            - has_auth: Whether auth token present
            - length: Total character count
        """
        if not cookie:
            return {
                "valid": False,
                "pairs_count": 0,
                "has_auth": False,
                "length": 0
            }

        cookie_dict = self.parse_cookie(cookie)

        info = {
            "valid": self.validate_cookie(cookie, platform),
            "pairs_count": len(cookie_dict),
            "has_auth": self.has_auth_token(cookie, platform),
            "length": len(cookie),
            "keys": list(cookie_dict.keys())
        }

        return info


# [DLR][COOKIE] Global cookie manager instance
cookie_manager = CookieManager()


if __name__ == "__main__":
    print("=== [DLR][COOKIE] Testing Cookie Manager ===\n")

    # Test SOOP cookie sanitization
    print("=== Testing SOOP Cookie Sanitization ===")
    dirty_cookie = "AuthTicket=abc123\n\rSID=xyz789\t\x00\x01test=value"
    print(f"Before: {repr(dirty_cookie)}")
    clean_cookie = cookie_manager.sanitize_soop_cookie(dirty_cookie)
    print(f"After: {repr(clean_cookie)}")
    print(f"Valid: {cookie_manager.validate_cookie(clean_cookie, Platform.SOOP)}\n")

    # Test cookie parsing
    print("=== Testing Cookie Parsing ===")
    test_cookie = "token1=value1; token2=value2; AuthTicket=secret123"
    cookie_dict = cookie_manager.parse_cookie(test_cookie)
    print(f"Parsed: {cookie_dict}")
    print(f"Formatted back: {cookie_manager.format_cookie(cookie_dict)}\n")

    # Test auth token extraction
    print("=== Testing Auth Token Extraction ===")
    auth_token = cookie_manager.extract_auth_token(test_cookie, "AuthTicket", Platform.SOOP)
    print(f"AuthTicket: {auth_token}")
    print(f"Has auth: {cookie_manager.has_auth_token(test_cookie, Platform.SOOP)}\n")

    # Test cookie merging
    print("=== Testing Cookie Merging ===")
    old_cookie = "token1=old_value; token2=keep_this"
    new_cookie = "token1=new_value; token3=added"
    merged = cookie_manager.merge_cookies(old_cookie, new_cookie, Platform.PANDA)
    print(f"Old: {old_cookie}")
    print(f"New: {new_cookie}")
    print(f"Merged: {merged}\n")

    # Test cookie info
    print("=== Testing Cookie Info ===")
    info = cookie_manager.get_cookie_info(test_cookie, Platform.SOOP)
    print(f"Cookie info:")
    for key, value in info.items():
        print(f"  {key}: {value}")

    print("\n=== [DLR][COOKIE] Test completed ===")
