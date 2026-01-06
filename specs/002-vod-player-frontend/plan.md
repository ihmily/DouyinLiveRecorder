# Implementation Plan: VOD Pipeline Bug Fix

**Branch**: `002-vod-player-frontend` | **Date**: 2026-01-06 | **Spec**: [spec.md](spec.md)
**Input**: Runtime error during segment processing

## Summary

Fix pipeline integration error where `RecordingManager.on_segment_created()` references non-existent method `process_segment_with_pipeline_sync`. The actual method is named `process_segment_sync` and requires an additional `platform` parameter.

## Technical Context

**Language/Version**: Python 3.10+
**Primary Dependencies**: asyncio, threading (stdlib)
**Storage**: SQLite via SQLAlchemy
**Testing**: Manual testing via live recording
**Target Platform**: Linux server
**Project Type**: Single project (existing codebase)
**Performance Goals**: N/A (bug fix)
**Constraints**: Minimal change, no breaking changes
**Scale/Scope**: Single file fix

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Recording Reliability | ✅ PASS | Fix enables pipeline processing to work correctly |
| II. Platform Abstraction | ✅ PASS | No platform-specific changes |
| III. Configuration Simplicity | ✅ PASS | No config changes |
| IV. Async-First Architecture | ✅ PASS | Uses existing async pattern correctly |
| V. Observable Operations | ✅ PASS | Error logging already in place |

## Project Structure

### Documentation (this feature)

```text
specs/002-vod-player-frontend/
├── plan.md              # This file
├── research.md          # Root cause analysis (section 9)
├── data-model.md        # N/A for bug fix
├── quickstart.md        # N/A for bug fix
├── contracts/           # N/A for bug fix
└── tasks.md             # Existing task list
```

### Source Code (affected files)

```text
src/storage/
└── manager.py           # Line 294-295: Fix method name and add parameter
```

## Bug Fix Details

### Error
```
'RecordingManager' object has no attribute 'process_segment_with_pipeline_sync'
```

### Root Cause
1. **Wrong method name**: `process_segment_with_pipeline_sync` (called) vs `process_segment_sync` (defined)
2. **Missing parameter**: `platform` not passed to thread args

### Fix Location
`src/storage/manager.py` lines 293-298

### Fix Diff
```diff
 thread = threading.Thread(
-    target=self.process_segment_with_pipeline_sync,
-    args=(segment_id, segment_path, save_type.lower(), session_id, anchor_name),
+    target=self.process_segment_sync,
+    args=(segment_id, segment_path, save_type.lower(), session_id, anchor_name, platform),
     daemon=True
 )
```

## Complexity Tracking

N/A - Simple bug fix with no complexity trade-offs.
