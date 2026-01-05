# -*- coding: utf-8 -*-
"""
TS to MP4 conversion stage using FFmpeg with Fast Start.

The Fast Start option (-movflags faststart) places the moov atom at the
beginning of the file, enabling instant seek via HTTP Range requests.

Author: DouyinLiveRecorder
Date: 2026-01-06
"""
import asyncio
import json
import os
import subprocess
from pathlib import Path
from typing import Optional

from ..pipeline import BaseStage, StageInput, StageResult, StageStatus
from ..models import Mp4Status


class ConvertStage(BaseStage):
    """
    Stage for converting TS files to Fast Start MP4.

    Uses FFmpeg with -movflags faststart for web-optimized playback.
    Also extracts video duration using FFprobe.
    """

    @property
    def name(self) -> str:
        return "convert"

    def __init__(self, ffmpeg_path: str = "ffmpeg", ffprobe_path: str = "ffprobe"):
        super().__init__()
        self.ffmpeg_path = ffmpeg_path
        self.ffprobe_path = ffprobe_path

    async def process(self, input_data: StageInput) -> StageResult:
        """
        Convert TS file to Fast Start MP4.

        Args:
            input_data: Stage input with segment file info

        Returns:
            StageResult with mp4_path and duration on success
        """
        local_path = Path(input_data.local_file_path)

        # Skip if not a TS file
        if input_data.file_format.lower() != "ts":
            self.logger.info(f"Skipping conversion for non-TS file: {input_data.file_format}")
            return StageResult(
                status=StageStatus.SKIPPED,
                output={"skip_reason": "Not a TS file"}
            )

        # Check if source file exists
        if not local_path.exists():
            return StageResult(
                status=StageStatus.FAILED,
                error=f"Source file not found: {local_path}"
            )

        # Prepare output path
        mp4_path = local_path.with_suffix(".mp4")

        try:
            # Update status to processing (will be done by manager)
            self.logger.info(f"Converting {local_path} to {mp4_path}")

            # Run FFmpeg conversion
            success = await self._run_ffmpeg(local_path, mp4_path)

            if not success:
                # T042: Fallback - return failure status
                # The upload stage should handle this by uploading TS instead
                return StageResult(
                    status=StageStatus.FAILED,
                    error="FFmpeg conversion failed",
                    output={"fallback_to_ts": True}
                )

            # T037: Extract duration using FFprobe
            duration = await self._get_duration(mp4_path)

            return StageResult(
                status=StageStatus.COMPLETED,
                output={
                    "mp4_path": str(mp4_path),
                    "duration": duration,
                    "original_path": str(local_path),
                }
            )

        except Exception as e:
            self.logger.error(f"Conversion error: {e}")
            return StageResult(
                status=StageStatus.FAILED,
                error=str(e),
                output={"fallback_to_ts": True}
            )

    async def _run_ffmpeg(self, input_path: Path, output_path: Path) -> bool:
        """
        Run FFmpeg to convert TS to MP4 with faststart.

        Args:
            input_path: Source TS file
            output_path: Destination MP4 file

        Returns:
            True if conversion succeeded
        """
        cmd = [
            self.ffmpeg_path,
            "-y",  # Overwrite output
            "-i", str(input_path),
            "-c", "copy",  # Remux only, no transcoding
            "-movflags", "faststart",  # Move moov atom to beginning
            str(output_path)
        ]

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            stdout, stderr = await process.communicate()

            if process.returncode != 0:
                self.logger.error(f"FFmpeg error: {stderr.decode()}")
                return False

            # Verify output file exists and has size
            if not output_path.exists() or output_path.stat().st_size == 0:
                self.logger.error("Output file missing or empty")
                return False

            return True

        except FileNotFoundError:
            self.logger.error(f"FFmpeg not found at: {self.ffmpeg_path}")
            return False

    async def _get_duration(self, file_path: Path) -> Optional[float]:
        """
        Extract video duration using FFprobe.

        Args:
            file_path: Video file path

        Returns:
            Duration in seconds, or None if extraction fails
        """
        cmd = [
            self.ffprobe_path,
            "-v", "quiet",
            "-print_format", "json",
            "-show_format",
            str(file_path)
        ]

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            stdout, stderr = await process.communicate()

            if process.returncode != 0:
                self.logger.warning(f"FFprobe error: {stderr.decode()}")
                return None

            data = json.loads(stdout.decode())
            duration_str = data.get("format", {}).get("duration")

            if duration_str:
                return float(duration_str)

            return None

        except (FileNotFoundError, json.JSONDecodeError, ValueError) as e:
            self.logger.warning(f"Duration extraction failed: {e}")
            return None
