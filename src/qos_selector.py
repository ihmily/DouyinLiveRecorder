# -*- encoding: utf-8 -*-
"""
[DLR][QOS] Quality of Service Selector
Author: Claude Code
Date: 2025-11-05
Function: Intelligent bitrate/fps selection, avoid selecting 720p over 1080p mistakes
"""

import re
from typing import List, Optional, Dict, Tuple
from dataclasses import dataclass

try:
    from .dlr_logger import dlr_logger, Platform, log_qos_select_highest, log_qos_variant_switch
except ImportError:
    from dlr_logger import dlr_logger, Platform, log_qos_select_highest, log_qos_variant_switch


@dataclass
class StreamVariant:
    """# [DLR][QOS] Stream variant information"""
    url: str
    bitrate: Optional[int] = None  # kbps
    resolution: Optional[str] = None  # e.g., "1080p", "720p"
    width: Optional[int] = None
    height: Optional[int] = None
    fps: Optional[int] = None
    codec: Optional[str] = None
    score: float = 0.0  # Quality score for ranking


class QoSSelector:
    """
    # [DLR][QOS] Quality of Service Selector

    Features:
    - SELECT_HIGHEST_BITRATE: Select highest quality stream
    - Resolution-aware ranking (1080p > 720p, even if 720p has higher bitrate)
    - FPS consideration (60fps > 30fps for same resolution)
    - Adaptive variant switching with hysteresis
    - Avoid 720p-over-1080p selection mistakes

    Priority order:
    1. Resolution (higher is better)
    2. FPS (higher is better for same resolution)
    3. Bitrate (higher is better for same resolution+fps)
    """

    def __init__(self, prefer_highest: bool = True, min_switch_improve_kbps: int = 500):
        """
        Initialize QoS Selector

        Args:
            prefer_highest: Always prefer highest quality (default: True)
            min_switch_improve_kbps: Minimum bitrate improvement to trigger switch (default: 500kbps)
        """
        self.prefer_highest = prefer_highest
        self.min_switch_improve_kbps = min_switch_improve_kbps

        # [DLR][QOS] Resolution rankings
        self.resolution_scores = {
            "4K": 4000,
            "2160p": 4000,
            "1440p": 1440,
            "QHD": 1440,
            "1080p": 1080,
            "FHD": 1080,
            "900p": 900,
            "720p": 720,
            "HD": 720,
            "540p": 540,
            "480p": 480,
            "SD": 480,
            "360p": 360,
            "240p": 240,
            "144p": 144,
        }

        dlr_logger.info_qos(f"Initialized: prefer_highest={prefer_highest}, min_switch={min_switch_improve_kbps}kbps")

    def parse_variant(self, url: str, m3u8_content: Optional[str] = None) -> StreamVariant:
        """
        # [DLR][QOS] Parse stream variant information

        Extract information from:
        - URL patterns (e.g., "playlist_1080p60.m3u8")
        - M3U8 EXT-X-STREAM-INF tags

        Args:
            url: Variant URL
            m3u8_content: Optional m3u8 content containing metadata

        Returns:
            StreamVariant object
        """
        variant = StreamVariant(url=url)

        # [DLR][QOS] Parse URL for quality indicators
        url_lower = url.lower()

        # Extract resolution from URL
        res_patterns = [
            r'(\d{3,4})p',  # e.g., "1080p", "720p"
            r'_(\d{3,4})_',  # e.g., "_1080_"
            r'(\d{3,4})x(\d{3,4})',  # e.g., "1920x1080"
        ]

        for pattern in res_patterns:
            match = re.search(pattern, url_lower)
            if match:
                if len(match.groups()) == 2:  # width x height
                    variant.width = int(match.group(1))
                    variant.height = int(match.group(2))
                    variant.resolution = f"{variant.height}p"
                else:
                    height = int(match.group(1))
                    variant.height = height
                    variant.resolution = f"{height}p"
                break

        # Extract FPS from URL
        fps_match = re.search(r'(\d+)fps', url_lower)
        if fps_match:
            variant.fps = int(fps_match.group(1))
        else:
            # Check for common FPS indicators
            if '60' in url_lower or 'hfr' in url_lower:
                variant.fps = 60
            elif '30' in url_lower:
                variant.fps = 30

        # Extract bitrate from URL
        bitrate_patterns = [
            r'(\d+)kbps',
            r'(\d+)k',
            r'_(\d{3,5})_',  # Common in CDN URLs
        ]

        for pattern in bitrate_patterns:
            match = re.search(pattern, url_lower)
            if match:
                variant.bitrate = int(match.group(1))
                break

        # [DLR][QOS] Parse m3u8 metadata if provided
        if m3u8_content:
            # Extract from EXT-X-STREAM-INF tag
            stream_inf_pattern = r'#EXT-X-STREAM-INF:.*BANDWIDTH=(\d+)'
            bandwidth_match = re.search(stream_inf_pattern, m3u8_content)
            if bandwidth_match:
                bandwidth_bps = int(bandwidth_match.group(1))
                variant.bitrate = bandwidth_bps // 1000  # Convert to kbps

            # Extract resolution from RESOLUTION tag
            res_pattern = r'RESOLUTION=(\d+)x(\d+)'
            res_match = re.search(res_pattern, m3u8_content)
            if res_match:
                variant.width = int(res_match.group(1))
                variant.height = int(res_match.group(2))
                variant.resolution = f"{variant.height}p"

            # Extract FPS from FRAME-RATE tag
            fps_pattern = r'FRAME-RATE=([\d.]+)'
            fps_match = re.search(fps_pattern, m3u8_content)
            if fps_match:
                variant.fps = int(float(fps_match.group(1)))

            # Extract codec
            codec_pattern = r'CODECS="([^"]+)"'
            codec_match = re.search(codec_pattern, m3u8_content)
            if codec_match:
                variant.codec = codec_match.group(1)

        # [DLR][QOS] Calculate quality score
        variant.score = self._calculate_score(variant)

        dlr_logger.debug_qos(
            f"Parsed variant: {variant.resolution or 'N/A'} @ {variant.fps or '?'}fps, "
            f"{variant.bitrate or '?'}kbps, score={variant.score:.2f}"
        )

        return variant

    def _calculate_score(self, variant: StreamVariant) -> float:
        """
        # [DLR][QOS] Calculate quality score for ranking

        Scoring formula:
        - Resolution: Primary factor (weight=1000)
        - FPS: Secondary factor (weight=10)
        - Bitrate: Tertiary factor (weight=0.01)

        Example scores:
        - 1080p60 @ 6000kbps = 1080 * 1000 + 60 * 10 + 6000 * 0.01 = 1,080,660
        - 720p60 @ 8000kbps  = 720 * 1000 + 60 * 10 + 8000 * 0.01 = 720,680
        - 1080p30 @ 4000kbps = 1080 * 1000 + 30 * 10 + 4000 * 0.01 = 1,080,340

        This ensures 1080p30 > 720p60 (correct behavior)
        """
        score = 0.0

        # [DLR][QOS] Resolution score (primary factor)
        if variant.resolution:
            res_score = self.resolution_scores.get(variant.resolution, 0)
            if res_score == 0 and variant.height:
                res_score = variant.height
            score += res_score * 1000
        elif variant.height:
            score += variant.height * 1000

        # [DLR][QOS] FPS score (secondary factor)
        if variant.fps:
            score += variant.fps * 10

        # [DLR][QOS] Bitrate score (tertiary factor)
        if variant.bitrate:
            score += variant.bitrate * 0.01

        return score

    def select_best_variant(self, variants: List[StreamVariant],
                           platform: Platform = None) -> Optional[StreamVariant]:
        """
        # [DLR][QOS] SELECT_HIGHEST_BITRATE
        Select the best quality variant from a list

        Args:
            variants: List of available variants
            platform: Platform identifier

        Returns:
            Best variant or None if list is empty
        """
        if not variants:
            dlr_logger.warn_qos("No variants available for selection", platform)
            return None

        if len(variants) == 1:
            dlr_logger.debug_qos("Only one variant available", platform)
            return variants[0]

        # [DLR][QOS] Sort by score (descending)
        sorted_variants = sorted(variants, key=lambda v: v.score, reverse=True)

        best = sorted_variants[0]

        log_qos_select_highest()
        dlr_logger.info_qos(
            f"Selected: {best.resolution or 'N/A'} @ {best.fps or '?'}fps, "
            f"{best.bitrate or '?'}kbps (score={best.score:.2f})",
            platform
        )

        # [DLR][QOS] Log rejected alternatives
        if len(sorted_variants) > 1:
            for i, var in enumerate(sorted_variants[1:3], 1):  # Show top 3
                dlr_logger.debug_qos(
                    f"  Alternative #{i}: {var.resolution or 'N/A'} @ {var.fps or '?'}fps, "
                    f"{var.bitrate or '?'}kbps (score={var.score:.2f})",
                    platform
                )

        return best

    def should_switch_variant(self, current: StreamVariant, new: StreamVariant,
                             platform: Platform = None) -> bool:
        """
        # [DLR][QOS] SWITCH_VARIANT_IF_BETTER
        Determine if should switch to new variant

        Switching logic with hysteresis:
        - Always switch if resolution improves
        - For same resolution, switch if:
          - FPS improves significantly (30->60)
          - Bitrate improves by at least min_switch_improve_kbps

        Args:
            current: Current variant
            new: New variant to consider
            platform: Platform identifier

        Returns:
            True if should switch, False otherwise
        """
        if not current or not new:
            return False

        # [DLR][QOS] Check resolution improvement
        current_height = current.height or 0
        new_height = new.height or 0

        if new_height > current_height:
            log_qos_variant_switch(
                current.bitrate or 0,
                new.bitrate or 0
            )
            dlr_logger.info_qos(
                f"Switch recommended: Resolution improved {current_height}p -> {new_height}p",
                platform
            )
            return True

        if new_height < current_height:
            dlr_logger.debug_qos(
                f"No switch: Resolution downgrade {current_height}p -> {new_height}p",
                platform
            )
            return False

        # [DLR][QOS] Same resolution - check FPS
        current_fps = current.fps or 30
        new_fps = new.fps or 30

        if new_fps > current_fps and (new_fps - current_fps) >= 15:
            log_qos_variant_switch(current.bitrate or 0, new.bitrate or 0)
            dlr_logger.info_qos(
                f"Switch recommended: FPS improved {current_fps} -> {new_fps}fps",
                platform
            )
            return True

        # [DLR][QOS] Same resolution and FPS - check bitrate
        current_bitrate = current.bitrate or 0
        new_bitrate = new.bitrate or 0

        bitrate_diff = new_bitrate - current_bitrate

        if bitrate_diff >= self.min_switch_improve_kbps:
            log_qos_variant_switch(current_bitrate, new_bitrate)
            dlr_logger.info_qos(
                f"Switch recommended: Bitrate improved +{bitrate_diff}kbps",
                platform
            )
            return True

        dlr_logger.debug_qos(
            f"No switch: Insufficient improvement (bitrate diff={bitrate_diff}kbps)",
            platform
        )
        return False

    def parse_m3u8_variants(self, m3u8_content: str) -> List[StreamVariant]:
        """
        # [DLR][QOS] Parse all variants from master m3u8 content

        Args:
            m3u8_content: Master m3u8 playlist content

        Returns:
            List of parsed StreamVariant objects
        """
        variants = []

        # Split into stream info blocks
        lines = m3u8_content.split('\n')
        current_info = None

        for line in lines:
            line = line.strip()

            if line.startswith('#EXT-X-STREAM-INF:'):
                current_info = line
            elif line and not line.startswith('#') and current_info:
                # This is a variant URL
                variant = self.parse_variant(line, current_info)
                variants.append(variant)
                current_info = None

        dlr_logger.debug_qos(f"Parsed {len(variants)} variants from m3u8")

        return variants


# [DLR][QOS] Global QoS selector instance
qos_selector = QoSSelector()


if __name__ == "__main__":
    print("=== [DLR][QOS] Testing QoS Selector ===\n")

    # Test variant parsing
    print("=== Testing Variant Parsing ===")
    test_urls = [
        "https://cdn.example.com/live/playlist_1080p60_6000k.m3u8",
        "https://cdn.example.com/live/playlist_720p60_8000k.m3u8",
        "https://cdn.example.com/live/playlist_1080p30_4000k.m3u8",
        "https://cdn.example.com/live/playlist_480p30_2000k.m3u8",
    ]

    variants = []
    for url in test_urls:
        variant = qos_selector.parse_variant(url)
        variants.append(variant)
        print(f"URL: {url.split('/')[-1]}")
        print(f"  Resolution: {variant.resolution}, FPS: {variant.fps}, Bitrate: {variant.bitrate}kbps")
        print(f"  Score: {variant.score:.2f}\n")

    # Test best variant selection
    print("\n=== Testing Best Variant Selection ===")
    best = qos_selector.select_best_variant(variants, Platform.PANDA)
    if best:
        print(f"✓ Best variant: {best.resolution} @ {best.fps}fps, {best.bitrate}kbps")
        print(f"  URL: {best.url}")

    # Test variant switching
    print("\n\n=== Testing Variant Switching ===")
    current = variants[2]  # 1080p30
    new = variants[1]      # 720p60

    print(f"Current: {current.resolution} @ {current.fps}fps, {current.bitrate}kbps")
    print(f"New: {new.resolution} @ {new.fps}fps, {new.bitrate}kbps")

    should_switch = qos_selector.should_switch_variant(current, new, Platform.PANDA)
    print(f"Should switch: {should_switch} (Expected: False - 1080p is better than 720p)\n")

    # Test with resolution upgrade
    new_better = variants[0]  # 1080p60
    print(f"Current: {current.resolution} @ {current.fps}fps, {current.bitrate}kbps")
    print(f"New: {new_better.resolution} @ {new_better.fps}fps, {new_better.bitrate}kbps")

    should_switch = qos_selector.should_switch_variant(current, new_better, Platform.PANDA)
    print(f"Should switch: {should_switch} (Expected: True - FPS improved)")

    print("\n=== [DLR][QOS] Test completed ===")
