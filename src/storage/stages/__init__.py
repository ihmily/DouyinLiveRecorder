# -*- coding: utf-8 -*-
"""
Pipeline stages for recording post-processing.

Stages:
- ConvertStage: TS → Fast Start MP4 conversion
- UploadStage: Upload to TOS (Volcano Engine Object Storage)
"""
from .convert import ConvertStage
from .upload import UploadStage

__all__ = ["ConvertStage", "UploadStage"]
