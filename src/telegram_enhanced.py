# -*- encoding: utf-8 -*-
"""
[DLR][TG] Enhanced Telegram Notifications
Author: Claude Code
Date: 2025-11-05
Function: Enhanced Telegram push with templates, status colors, and premium room detection
"""

from typing import Optional, Dict
from datetime import datetime
from enum import Enum

try:
    from .dlr_logger import dlr_logger, Platform, log_tg_template_applied, log_tg_status_color
except ImportError:
    from dlr_logger import dlr_logger, Platform, log_tg_template_applied, log_tg_status_color


class LiveStatus(Enum):
    """# [DLR][TG] Live stream status"""
    ONLINE = "online"      # 🟢 Green
    OFFLINE = "offline"    # 🔴 Red
    PREMIUM = "premium"    # 🟣 Purple (fans-only/paid)
    ERROR = "error"        # ⚠️  Warning


class RecordStatus(Enum):
    """# [DLR][TG] Recording status"""
    RECORDING = "recording"    # 🔴 Recording
    STOPPED = "stopped"        # ⏹️  Stopped
    PAUSED = "paused"          # ⏸️  Paused
    WAITING = "waiting"        # ⏳ Waiting


class TelegramEnhanced:
    """
    # [DLR][TG] Enhanced Telegram Notifier

    Features:
    - Status color indicators (🟢🔴🟣)
    - Template-based messages (TEMPLATE_V2)
    - Premium/fans-only room detection
    - M3U8 URL updates
    - Rich formatting with Markdown
    """

    def __init__(self, template_version: str = "full_v2"):
        """
        Initialize Enhanced Telegram Notifier

        Args:
            template_version: Template version (default: "full_v2")
        """
        self.template_version = template_version
        self.status_colors = self._init_status_colors()
        log_tg_template_applied()
        dlr_logger.info_tg(f"Initialized with template={template_version}")

    def _init_status_colors(self) -> Dict[str, str]:
        """
        # [DLR][TG] STATUS_COLOR_MAP
        Initialize status color mapping
        """
        colors = {
            LiveStatus.ONLINE.value: "🟢",      # Green
            LiveStatus.OFFLINE.value: "🔴",     # Red
            LiveStatus.PREMIUM.value: "🟣",     # Purple
            LiveStatus.ERROR.value: "⚠️",       # Warning
            RecordStatus.RECORDING.value: "🔴", # Red dot
            RecordStatus.STOPPED.value: "⏹️",   # Stop
            RecordStatus.PAUSED.value: "⏸️",    # Pause
            RecordStatus.WAITING.value: "⏳",   # Hourglass
        }

        for status, color in colors.items():
            log_tg_status_color(status, color)

        return colors

    def get_status_icon(self, status: str) -> str:
        """# [DLR][TG] Get status icon/color"""
        return self.status_colors.get(status, "⚫")

    def format_message_v2(self, **kwargs) -> str:
        """
        # [DLR][TG] TEMPLATE_V2
        Format message using TEMPLATE_V2 (full format)

        Template placeholders:
        - {platform}: Platform name (e.g., "PandaLive", "SOOP")
        - {anchor}: Anchor/streamer name
        - {room}: Room ID or name
        - {type}: Room type (normal/premium/fans-only)
        - {live_status}: Live status (online/offline/premium)
        - {rec_status}: Recording status (recording/stopped/waiting)
        - {title}: Stream title
        - {url}: Room URL
        - {m3u8}: M3U8 playlist URL
        - {bitrate}: Stream bitrate
        - {resolution}: Stream resolution
        - {ts}: Timestamp

        Returns:
            Formatted message string with Markdown
        """
        # Extract parameters with defaults
        platform = kwargs.get('platform', 'Unknown')
        anchor = kwargs.get('anchor', 'Unknown')
        room = kwargs.get('room', '')
        room_type = kwargs.get('type', 'normal')
        live_status = kwargs.get('live_status', LiveStatus.OFFLINE.value)
        rec_status = kwargs.get('rec_status', RecordStatus.STOPPED.value)
        title = kwargs.get('title', '')
        url = kwargs.get('url', '')
        m3u8 = kwargs.get('m3u8', '')
        bitrate = kwargs.get('bitrate', 'N/A')
        resolution = kwargs.get('resolution', 'N/A')
        timestamp = kwargs.get('ts', datetime.now().strftime('%Y-%m-%d %H:%M:%S'))

        # [DLR][TG] Get status icons
        live_icon = self.get_status_icon(live_status)
        rec_icon = self.get_status_icon(rec_status)

        # [DLR][TG] Build message using TEMPLATE_V2
        lines = [
            f"📺 *{platform} Live Notification*",
            f"━━━━━━━━━━━━━━━━━━",
        ]

        # Anchor info
        lines.append(f"👤 *Anchor:* `{anchor}`")

        # Room info
        if room:
            lines.append(f"🏠 *Room:* `{room}`")

        # Room type (highlight premium/fans-only)
        if room_type in ['premium', 'fans', 'paid']:
            type_icon = self.get_status_icon(LiveStatus.PREMIUM.value)
            lines.append(f"{type_icon} *Type:* `{room_type.upper()}`")

        # Live status
        lines.append(f"{live_icon} *Status:* `{live_status.upper()}`")

        # Recording status
        lines.append(f"{rec_icon} *Recording:* `{rec_status.upper()}`")

        # Title
        if title:
            lines.append(f"📝 *Title:* {title}")

        # Stream quality
        if bitrate != 'N/A' or resolution != 'N/A':
            quality_parts = []
            if resolution != 'N/A':
                quality_parts.append(resolution)
            if bitrate != 'N/A':
                if isinstance(bitrate, (int, float)):
                    quality_parts.append(f"{bitrate}kbps")
                else:
                    quality_parts.append(str(bitrate))
            lines.append(f"🎬 *Quality:* `{' @ '.join(quality_parts)}`")

        # URLs
        if url:
            lines.append(f"🔗 *URL:* {url}")

        if m3u8:
            # Truncate long m3u8 URLs
            if len(m3u8) > 100:
                m3u8_display = m3u8[:97] + "..."
            else:
                m3u8_display = m3u8
            lines.append(f"📡 *M3U8:* `{m3u8_display}`")

        # Timestamp
        lines.append(f"⏰ *Time:* `{timestamp}`")

        lines.append(f"━━━━━━━━━━━━━━━━━━")

        message = '\n'.join(lines)

        dlr_logger.debug_tg(f"Formatted message: {len(message)} chars, template=full_v2")

        return message

    def format_message_simple(self, **kwargs) -> str:
        """
        # [DLR][TG] Simple message format
        Shorter format for frequent updates
        """
        platform = kwargs.get('platform', 'Unknown')
        anchor = kwargs.get('anchor', 'Unknown')
        live_status = kwargs.get('live_status', LiveStatus.OFFLINE.value)
        rec_status = kwargs.get('rec_status', RecordStatus.STOPPED.value)

        live_icon = self.get_status_icon(live_status)
        rec_icon = self.get_status_icon(rec_status)

        message = (
            f"{live_icon} *{platform}* - {anchor}\n"
            f"{rec_icon} {rec_status.upper()}"
        )

        return message

    def format_m3u8_update(self, **kwargs) -> str:
        """
        # [DLR][TG][M3U8] M3U8 URL update notification
        Specifically for m3u8 refresh events
        """
        platform = kwargs.get('platform', 'Unknown')
        anchor = kwargs.get('anchor', 'Unknown')
        old_m3u8 = kwargs.get('old_m3u8', '')
        new_m3u8 = kwargs.get('new_m3u8', '')
        bitrate_change = kwargs.get('bitrate_change', None)
        timestamp = kwargs.get('ts', datetime.now().strftime('%H:%M:%S'))

        lines = [
            f"🔄 *M3U8 Updated* - {platform}",
            f"👤 {anchor}",
        ]

        if bitrate_change:
            old_br, new_br = bitrate_change
            if new_br > old_br:
                lines.append(f"📈 Quality improved: {old_br}kbps → {new_br}kbps")
            elif new_br < old_br:
                lines.append(f"📉 Quality changed: {old_br}kbps → {new_br}kbps")

        if new_m3u8:
            m3u8_display = new_m3u8[:80] + "..." if len(new_m3u8) > 80 else new_m3u8
            lines.append(f"📡 `{m3u8_display}`")

        lines.append(f"⏰ {timestamp}")

        return '\n'.join(lines)

    def format_premium_room_detected(self, **kwargs) -> str:
        """
        # [DLR][TG][PREMIUM] Premium/fans-only room detection
        Special notification for premium rooms
        """
        platform = kwargs.get('platform', 'Unknown')
        anchor = kwargs.get('anchor', 'Unknown')
        room_type = kwargs.get('type', 'premium')
        url = kwargs.get('url', '')
        message_text = kwargs.get('message', '')

        premium_icon = self.get_status_icon(LiveStatus.PREMIUM.value)

        lines = [
            f"{premium_icon} *{room_type.upper()} ROOM DETECTED*",
            f"━━━━━━━━━━━━━━━━━━",
            f"📺 *Platform:* {platform}",
            f"👤 *Anchor:* `{anchor}`",
        ]

        if message_text:
            lines.append(f"💬 *Message:* {message_text}")

        if url:
            lines.append(f"🔗 {url}")

        lines.append(f"━━━━━━━━━━━━━━━━━━")
        lines.append("⚠️ This room requires authentication or payment")

        return '\n'.join(lines)

    def format_error_notification(self, **kwargs) -> str:
        """
        # [DLR][TG][ERR] Error notification
        """
        platform = kwargs.get('platform', 'Unknown')
        anchor = kwargs.get('anchor', 'Unknown')
        error_type = kwargs.get('error_type', 'Unknown')
        error_msg = kwargs.get('error_msg', '')
        line = kwargs.get('line', None)
        cause = kwargs.get('cause', None)

        error_icon = self.get_status_icon(LiveStatus.ERROR.value)

        lines = [
            f"{error_icon} *ERROR* - {platform}",
            f"👤 {anchor}",
            f"❌ *Type:* `{error_type}`",
        ]

        if error_msg:
            lines.append(f"💬 {error_msg}")

        if line:
            lines.append(f"📍 Line: `{line}`")

        if cause:
            lines.append(f"🔍 Cause: `{cause}`")

        return '\n'.join(lines)


# [DLR][TG] Global Telegram Enhanced instance
telegram_enhanced = TelegramEnhanced()


if __name__ == "__main__":
    print("=== [DLR][TG] Testing Telegram Enhanced ===\n")

    # Test full message format
    print("=== TEMPLATE_V2 (Full Format) ===")
    msg1 = telegram_enhanced.format_message_v2(
        platform="PandaLive",
        anchor="TestAnchor-123",
        room="live123",
        type="normal",
        live_status=LiveStatus.ONLINE.value,
        rec_status=RecordStatus.RECORDING.value,
        title="测试直播间标题",
        url="https://www.pandalive.co.kr/live/play/test123",
        m3u8="https://cdn.pandalive.co.kr/live/test123/playlist.m3u8",
        bitrate=6000,
        resolution="1080p"
    )
    print(msg1)
    print()

    # Test premium room detection
    print("\n=== Premium Room Detected ===")
    msg2 = telegram_enhanced.format_premium_room_detected(
        platform="SOOP",
        anchor="PremiumAnchor-456",
        type="fans-only",
        url="https://play.sooplive.co.kr/test456",
        message="This room is only accessible to fans"
    )
    print(msg2)
    print()

    # Test m3u8 update
    print("\n=== M3U8 Update ===")
    msg3 = telegram_enhanced.format_m3u8_update(
        platform="PandaLive",
        anchor="TestAnchor-123",
        old_m3u8="https://old.url/playlist.m3u8",
        new_m3u8="https://new.url/playlist.m3u8",
        bitrate_change=(4500, 6000)
    )
    print(msg3)
    print()

    # Test error notification
    print("\n=== Error Notification ===")
    msg4 = telegram_enhanced.format_error_notification(
        platform="PandaLive",
        anchor="ErrorAnchor-789",
        error_type="needCoinPurchase",
        error_msg="유저 정보가 없습니다 (No user info)",
        line=1281,
        cause="bjInfo not in response"
    )
    print(msg4)

    print("\n\n=== [DLR][TG] Test completed ===")
