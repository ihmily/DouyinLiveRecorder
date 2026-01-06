# -*- coding: utf-8 -*-
"""
Upload stage for TOS (Volcano Engine Object Storage).

Handles uploading converted MP4 files (or fallback TS files) to TOS.

Author: DouyinLiveRecorder
Date: 2026-01-06
"""
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

from ..pipeline import BaseStage, StageInput, StageResult, StageStatus


class UploadStage(BaseStage):
    """
    Stage for uploading files to TOS.

    Supports:
    - Uploading converted MP4 files
    - Fallback to TS upload if conversion failed
    - Updating segment records with OSS paths
    - Cleaning up local files after successful upload
    """

    @property
    def name(self) -> str:
        return "upload"

    def __init__(self, config_path: Optional[str] = None, delete_after_upload: bool = True):
        super().__init__()
        self._config_path = config_path
        self._uploader = None
        self.delete_after_upload = delete_after_upload

    def _get_uploader(self):
        """Lazy-load TOS uploader."""
        if self._uploader is None:
            from ..tos_uploader import TOSUploader

            config_path = self._config_path
            if not config_path:
                # Default config path
                project_root = os.path.dirname(
                    os.path.dirname(
                        os.path.dirname(
                            os.path.dirname(os.path.abspath(__file__))
                        )
                    )
                )
                config_path = os.path.join(project_root, "config", "tos_credentials.ini")

            self._uploader = TOSUploader(config_path=config_path)

        return self._uploader

    async def process(self, input_data: StageInput) -> StageResult:
        """
        Upload file to TOS.

        If conversion succeeded (mp4_path in extra), uploads MP4.
        If conversion failed (fallback_to_ts in extra), uploads original TS.

        Args:
            input_data: Stage input with file paths and metadata

        Returns:
            StageResult with oss_path and mp4_oss_path on success
        """
        try:
            uploader = self._get_uploader()
        except Exception as e:
            self.logger.error(f"Failed to initialize TOS uploader: {e}")
            return StageResult(
                status=StageStatus.FAILED,
                error=f"TOS uploader initialization failed: {e}"
            )

        # Determine what to upload
        mp4_path = input_data.extra.get("mp4_path")
        fallback_to_ts = input_data.extra.get("fallback_to_ts", False)
        duration = input_data.extra.get("duration")

        results = {}

        # T039: Upload MP4 if conversion succeeded
        if mp4_path and not fallback_to_ts:
            mp4_file = Path(mp4_path)
            if mp4_file.exists():
                # Generate OSS key for MP4
                mp4_oss_key = uploader.generate_oss_key(
                    platform=input_data.platform,
                    anchor_name=input_data.anchor_name,
                    filename=mp4_file.name,
                    date=datetime.now()
                )

                success, result = uploader.upload_file(
                    local_path=str(mp4_file),
                    oss_key=mp4_oss_key
                )

                if success:
                    results["mp4_oss_path"] = mp4_oss_key
                    results["mp4_uploaded"] = True
                    self.logger.info(f"MP4 uploaded: {mp4_oss_key}")
                else:
                    self.logger.error(f"MP4 upload failed: {result}")
                    # Fallback to TS
                    fallback_to_ts = True
            else:
                self.logger.warning(f"MP4 file not found: {mp4_path}")
                fallback_to_ts = True

        # Upload TS as fallback or if no conversion
        if fallback_to_ts or not mp4_path:
            ts_file = Path(input_data.local_file_path)
            if ts_file.exists():
                ts_oss_key = uploader.generate_oss_key(
                    platform=input_data.platform,
                    anchor_name=input_data.anchor_name,
                    filename=ts_file.name,
                    date=datetime.now()
                )

                success, result = uploader.upload_file(
                    local_path=str(ts_file),
                    oss_key=ts_oss_key
                )

                if success:
                    results["oss_path"] = ts_oss_key
                    results["ts_uploaded"] = True
                    self.logger.info(f"TS uploaded (fallback): {ts_oss_key}")
                else:
                    return StageResult(
                        status=StageStatus.FAILED,
                        error=f"TS upload failed: {result}"
                    )
            else:
                return StageResult(
                    status=StageStatus.FAILED,
                    error=f"Source file not found: {ts_file}"
                )

        # Include duration from conversion stage
        if duration:
            results["duration"] = duration

        # Determine final status
        if results.get("mp4_uploaded"):
            results["mp4_status"] = "completed"
        elif results.get("ts_uploaded"):
            results["mp4_status"] = "failed"  # Conversion failed, fell back to TS

        # Clean up local files after successful upload
        if self.delete_after_upload:
            files_deleted = []

            # Delete MP4 file if it was uploaded
            if results.get("mp4_uploaded") and mp4_path:
                mp4_file = Path(mp4_path)
                if mp4_file.exists():
                    try:
                        os.remove(mp4_file)
                        files_deleted.append(str(mp4_file))
                        self.logger.info(f"MP4 file deleted after upload: {mp4_file}")
                    except OSError as e:
                        self.logger.warning(f"Failed to delete MP4 file: {mp4_file} - {e}")

            # Delete original TS file after successful upload (MP4 or TS fallback)
            original_ts = Path(input_data.local_file_path)
            if original_ts.exists() and (results.get("mp4_uploaded") or results.get("ts_uploaded")):
                try:
                    os.remove(original_ts)
                    files_deleted.append(str(original_ts))
                    self.logger.info(f"Original TS file deleted after upload: {original_ts}")
                except OSError as e:
                    self.logger.warning(f"Failed to delete original TS file: {original_ts} - {e}")

            results["files_deleted"] = files_deleted
            results["local_file_deleted"] = len(files_deleted) > 0

        return StageResult(
            status=StageStatus.COMPLETED,
            output=results
        )
