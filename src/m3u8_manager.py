# -*- encoding: utf-8 -*-
"""
[DLR][M3U8] M3U8 Manager with Refresh and Fallback
Author: Claude Code
Date: 2025-11-05
Function: Manages m3u8 URLs with periodic refresh and historical fallback
"""

import asyncio
import time
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Tuple
from collections import deque
from dataclasses import dataclass
from pathlib import Path
import json

try:
    from .dlr_logger import dlr_logger, Platform, log_m3u8_fetch_start, log_premium_fallback
except ImportError:
    # For standalone testing
    from dlr_logger import dlr_logger, Platform, log_m3u8_fetch_start, log_premium_fallback


@dataclass
class M3U8Record:
    """# [DLR][M3U8] Record of an m3u8 URL fetch"""
    url: str
    master_url: str
    timestamp: datetime
    bitrate: Optional[int] = None
    resolution: Optional[str] = None
    is_premium: bool = False  # 是否为付费/粉丝房
    variant_list: Optional[List[str]] = None


class M3U8Manager:
    """
    # [DLR][M3U8] M3U8 Manager with Periodic Refresh and Historical Fallback

    Features:
    - Periodic refresh every N seconds (default: 300s = 5min)
    - Maintains historical m3u8 URLs for fallback (last 10 minutes)
    - Handles premium/fans-only room errors with fallback
    - Logs all operations with [DLR][M3U8] tags
    """

    def __init__(self, refresh_interval: int = 300, history_window_minutes: int = 10):
        """
        Initialize M3U8 Manager

        Args:
            refresh_interval: Seconds between m3u8 refreshes (default: 300 = 5min)
            history_window_minutes: Minutes to keep m3u8 history (default: 10)
        """
        self.refresh_interval = refresh_interval
        self.history_window = timedelta(minutes=history_window_minutes)

        # [DLR][M3U8] History storage: {room_url: deque of M3U8Record}
        self.history: Dict[str, deque] = {}

        # [DLR][M3U8] Current m3u8 URLs: {room_url: current_m3u8_url}
        self.current_m3u8: Dict[str, str] = {}

        # [DLR][M3U8] Last refresh time: {room_url: timestamp}
        self.last_refresh: Dict[str, float] = {}

        # [DLR][M3U8] Log directory for m3u8 history
        self.log_dir = Path("logs")
        self.log_dir.mkdir(exist_ok=True)

        dlr_logger.info_m3u8(f"Initialized with refresh_interval={refresh_interval}s, history_window={history_window_minutes}min")

    def add_record(self, room_url: str, m3u8_url: str, master_url: str = None,
                   bitrate: int = None, resolution: str = None,
                   is_premium: bool = False, variant_list: List[str] = None,
                   platform: Platform = None):
        """
        # [DLR][M3U8] Add a new m3u8 record to history

        Args:
            room_url: Live room URL
            m3u8_url: M3U8 playlist URL
            master_url: Master playlist URL (if different)
            bitrate: Stream bitrate in kbps
            resolution: Stream resolution (e.g., "1080p")
            is_premium: Whether this is a premium/fans-only room
            variant_list: List of available variant URLs
            platform: Platform identifier
        """
        if room_url not in self.history:
            self.history[room_url] = deque(maxlen=100)  # Keep last 100 records

        record = M3U8Record(
            url=m3u8_url,
            master_url=master_url or m3u8_url,
            timestamp=datetime.now(),
            bitrate=bitrate,
            resolution=resolution,
            is_premium=is_premium,
            variant_list=variant_list
        )

        self.history[room_url].append(record)
        self.current_m3u8[room_url] = m3u8_url
        self.last_refresh[room_url] = time.time()

        dlr_logger.debug_m3u8(
            f"Added record: {room_url} -> {m3u8_url[:80]}... (bitrate={bitrate}, resolution={resolution})",
            platform
        )

        # [DLR][M3U8] Save to log file
        self._save_to_log(room_url, record, platform)

    def get_current_m3u8(self, room_url: str) -> Optional[str]:
        """# [DLR][M3U8] Get current m3u8 URL for a room"""
        return self.current_m3u8.get(room_url)

    def needs_refresh(self, room_url: str) -> bool:
        """
        # [DLR][M3U8] Check if m3u8 needs refresh

        Returns True if:
        - Never refreshed before
        - Last refresh was more than refresh_interval seconds ago
        """
        if room_url not in self.last_refresh:
            return True

        elapsed = time.time() - self.last_refresh[room_url]
        needs_refresh = elapsed >= self.refresh_interval

        if needs_refresh:
            dlr_logger.debug_m3u8(f"REFRESH_NEEDED: {room_url} (elapsed={elapsed:.0f}s)")

        return needs_refresh

    def get_fallback_m3u8(self, room_url: str, platform: Platform = None) -> Optional[M3U8Record]:
        """
        # [DLR][PREMIUM] FALLBACK_TO_PREV_M3U8
        Get previous valid m3u8 from history (within last 10 minutes)

        Used when encountering premium/fans-only errors like:
        - needCoinPurchase
        - needUnlimitItem
        - needAdult (adult verification)

        Args:
            room_url: Live room URL
            platform: Platform identifier

        Returns:
            Previous M3U8Record if found, None otherwise
        """
        if room_url not in self.history or len(self.history[room_url]) < 2:
            dlr_logger.warn_m3u8(f"FALLBACK_FAILED: No history available for {room_url}", platform)
            return None

        cutoff_time = datetime.now() - self.history_window
        history = list(self.history[room_url])

        # [DLR][PREMIUM] Search backwards for valid m3u8 (skip current one)
        for i in range(len(history) - 2, -1, -1):
            record = history[i]
            if record.timestamp >= cutoff_time:
                log_premium_fallback(room_url, platform)
                dlr_logger.info_m3u8(
                    f"FALLBACK_SUCCESS: Found m3u8 from {record.timestamp.strftime('%H:%M:%S')} "
                    f"(age={(datetime.now() - record.timestamp).total_seconds():.0f}s)",
                    platform
                )
                return record

        dlr_logger.warn_m3u8(
            f"FALLBACK_FAILED: No recent m3u8 found within {self.history_window.total_seconds()/60:.0f} minutes",
            platform
        )
        return None

    def get_recent_master_url(self, room_url: str, minutes: int = 10,
                              platform: Platform = None) -> Optional[str]:
        """
        # [DLR][PREMIUM] RECENT_MASTER
        Get most recent master m3u8 URL from history

        Args:
            room_url: Live room URL
            minutes: Look back N minutes (default: 10)
            platform: Platform identifier

        Returns:
            Master m3u8 URL if found, None otherwise
        """
        if room_url not in self.history:
            return None

        cutoff_time = datetime.now() - timedelta(minutes=minutes)
        history = list(self.history[room_url])

        for record in reversed(history):
            if record.timestamp >= cutoff_time and record.master_url:
                dlr_logger.debug_m3u8(
                    f"RECENT_MASTER: Found master URL from {record.timestamp.strftime('%H:%M:%S')}",
                    platform
                )
                return record.master_url

        return None

    def get_all_variants(self, room_url: str) -> List[str]:
        """
        # [DLR][QOS] Get all available variant URLs for a room
        Used for quality selection and adaptive streaming
        """
        if room_url not in self.history or not self.history[room_url]:
            return []

        latest_record = list(self.history[room_url])[-1]
        return latest_record.variant_list or []

    def clear_old_history(self, room_url: str = None):
        """
        # [DLR][M3U8] Clear old history beyond the window

        Args:
            room_url: Clear specific room (None = clear all rooms)
        """
        cutoff_time = datetime.now() - self.history_window

        if room_url:
            rooms_to_clear = [room_url]
        else:
            rooms_to_clear = list(self.history.keys())

        total_cleared = 0
        for room in rooms_to_clear:
            if room not in self.history:
                continue

            original_len = len(self.history[room])
            # Keep only recent records
            self.history[room] = deque(
                (r for r in self.history[room] if r.timestamp >= cutoff_time),
                maxlen=100
            )
            cleared = original_len - len(self.history[room])
            total_cleared += cleared

        if total_cleared > 0:
            dlr_logger.debug_m3u8(f"Cleared {total_cleared} old m3u8 records")

    def _save_to_log(self, room_url: str, record: M3U8Record, platform: Platform = None):
        """
        # [DLR][M3U8] Save m3u8 record to daily log file
        Format: logs/BJ-live-m3u8-YYYYMMDD.log
        """
        try:
            platform_name = platform.value if platform else "UNKNOWN"
            log_file = self.log_dir / f"BJ-live-m3u8-{datetime.now().strftime('%Y%m%d')}.log"

            log_entry = {
                "timestamp": record.timestamp.isoformat(),
                "room_url": room_url,
                "m3u8_url": record.url,
                "master_url": record.master_url,
                "bitrate": record.bitrate,
                "resolution": record.resolution,
                "is_premium": record.is_premium,
                "platform": platform_name
            }

            with open(log_file, 'a', encoding='utf-8') as f:
                f.write(json.dumps(log_entry, ensure_ascii=False) + '\n')

        except Exception as e:
            dlr_logger.error_m3u8(f"Failed to save log: {e}", platform)

    def load_recent_history_from_log(self, room_url: str, platform: Platform = None) -> int:
        """
        # [DLR][M3U8] Load recent m3u8 history from log files
        Useful for resuming after restart

        Returns:
            Number of records loaded
        """
        try:
            today = datetime.now()
            loaded_count = 0

            # Check today's and yesterday's logs
            for days_ago in [0, 1]:
                date = today - timedelta(days=days_ago)
                log_file = self.log_dir / f"BJ-live-m3u8-{date.strftime('%Y%m%d')}.log"

                if not log_file.exists():
                    continue

                with open(log_file, 'r', encoding='utf-8') as f:
                    for line in f:
                        try:
                            entry = json.loads(line.strip())
                            if entry['room_url'] != room_url:
                                continue

                            timestamp = datetime.fromisoformat(entry['timestamp'])
                            if datetime.now() - timestamp > self.history_window:
                                continue  # Too old

                            record = M3U8Record(
                                url=entry['m3u8_url'],
                                master_url=entry['master_url'],
                                timestamp=timestamp,
                                bitrate=entry.get('bitrate'),
                                resolution=entry.get('resolution'),
                                is_premium=entry.get('is_premium', False),
                                variant_list=entry.get('variant_list')
                            )

                            if room_url not in self.history:
                                self.history[room_url] = deque(maxlen=100)

                            self.history[room_url].append(record)
                            loaded_count += 1

                        except (json.JSONDecodeError, KeyError) as e:
                            continue  # Skip malformed entries

            if loaded_count > 0:
                dlr_logger.info_m3u8(f"Loaded {loaded_count} historical records for {room_url}", platform)

            return loaded_count

        except Exception as e:
            dlr_logger.error_m3u8(f"Failed to load history: {e}", platform)
            return 0

    def get_statistics(self, room_url: str) -> Dict:
        """
        # [DLR][M3U8] Get statistics for a room

        Returns:
            Dictionary with:
            - total_records: Total number of records
            - oldest_record: Timestamp of oldest record
            - newest_record: Timestamp of newest record
            - avg_bitrate: Average bitrate (if available)
            - refresh_count: Number of refreshes
        """
        if room_url not in self.history or not self.history[room_url]:
            return {
                "total_records": 0,
                "oldest_record": None,
                "newest_record": None,
                "avg_bitrate": None,
                "refresh_count": 0
            }

        history = list(self.history[room_url])
        bitrates = [r.bitrate for r in history if r.bitrate is not None]

        return {
            "total_records": len(history),
            "oldest_record": history[0].timestamp.isoformat(),
            "newest_record": history[-1].timestamp.isoformat(),
            "avg_bitrate": sum(bitrates) / len(bitrates) if bitrates else None,
            "refresh_count": len(history)
        }


# [DLR][M3U8] Global M3U8 manager instance
m3u8_manager = M3U8Manager()


if __name__ == "__main__":
    print("=== [DLR][M3U8] Testing M3U8 Manager ===\n")

    # Test adding records
    test_room = "https://www.pandalive.co.kr/live/play/test123"
    m3u8_manager.add_record(
        room_url=test_room,
        m3u8_url="https://cdn.pandalive.co.kr/live/test123/playlist.m3u8",
        master_url="https://cdn.pandalive.co.kr/live/test123/master.m3u8",
        bitrate=6000,
        resolution="1080p",
        platform=Platform.PANDA
    )

    print(f"\n✓ Current m3u8: {m3u8_manager.get_current_m3u8(test_room)[:80]}...")

    # Simulate time passing
    import time
    time.sleep(2)

    # Add another record (simulating refresh)
    m3u8_manager.add_record(
        room_url=test_room,
        m3u8_url="https://cdn.pandalive.co.kr/live/test123/playlist_new.m3u8",
        bitrate=5500,
        resolution="1080p",
        platform=Platform.PANDA
    )

    # Test fallback
    print("\n=== Testing fallback ===")
    fallback = m3u8_manager.get_fallback_m3u8(test_room, Platform.PANDA)
    if fallback:
        print(f"✓ Fallback m3u8: {fallback.url[:80]}...")
        print(f"  Timestamp: {fallback.timestamp.strftime('%H:%M:%S')}")
        print(f"  Bitrate: {fallback.bitrate} kbps")

    # Test statistics
    print("\n=== Statistics ===")
    stats = m3u8_manager.get_statistics(test_room)
    print(f"Total records: {stats['total_records']}")
    print(f"Average bitrate: {stats['avg_bitrate']:.0f} kbps" if stats['avg_bitrate'] else "N/A")

    print("\n=== [DLR][M3U8] Test completed ===")
