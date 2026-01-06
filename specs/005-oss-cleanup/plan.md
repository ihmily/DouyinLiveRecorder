# Implementation Plan: OSS Storage Cleanup

**Branch**: `005-oss-cleanup` | **Date**: 2026-01-06 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/005-oss-cleanup/spec.md`

## Summary

Implement automatic OSS storage cleanup that triggers after each successful upload, checks total storage against a configurable threshold, and deletes oldest completed sessions (FIFO) until storage falls below threshold. The cleanup must be thread-safe with mutex protection ensuring only one cleanup executes at a time while other requests block and wait.

## Technical Context

**Language/Version**: Python >= 3.10
**Primary Dependencies**: SQLAlchemy 2.0+, tos (Volcano Engine TOS SDK), loguru, threading
**Storage**: SQLite (default, data/recordings.db), also supports PostgreSQL/MySQL via SQLAlchemy
**Testing**: Manual testing via scripts (no formal test framework)
**Target Platform**: Linux server, Windows, macOS (cross-platform)
**Project Type**: Single project (CLI application)
**Performance Goals**: Cleanup adds <5 seconds overhead to individual upload operations
**Constraints**: Thread-safe, blocking cleanup, protect active sessions
**Scale/Scope**: Continuous 24/7 recording with up to 10 concurrent uploads

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Compliance | Notes |
|-----------|------------|-------|
| **I. Recording Reliability** | ✅ PASS | Active sessions protected from cleanup (FR-008). Cleanup failures logged but don't corrupt recordings. |
| **II. Platform Abstraction** | ✅ PASS | Cleanup operates at storage layer, independent of platform-specific spider code. |
| **III. Configuration Simplicity** | ✅ PASS | New settings added to existing `[OSS设置]` section in config.ini. Simple threshold value. |
| **IV. Async-First Architecture** | ✅ PASS | Cleanup uses existing threading patterns from upload_queue.py. Blocking cleanup per spec but non-blocking to main recording loop. |
| **V. Observable Operations** | ✅ PASS | Cleanup activities logged via loguru (FR-014). Sessions deleted, space freed, errors all logged. |

**Gate Status**: PASS - All constitution principles satisfied.

## Project Structure

### Documentation (this feature)

```text
specs/005-oss-cleanup/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output (internal contracts only - no external API)
└── tasks.md             # Phase 2 output (/speckit.tasks command)
```

### Source Code (repository root)

```text
src/
├── storage/
│   ├── models.py           # Existing - may need oss_deleted field
│   ├── repository.py       # Existing - add cleanup queries
│   ├── tos_uploader.py     # Existing - delete_object() already exists
│   ├── upload_queue.py     # Modify - add cleanup hook after upload
│   ├── manager.py          # Modify - add cleanup orchestration
│   └── cleanup.py          # NEW - cleanup logic with mutex
scripts/
└── test_tos_delete.py      # NEW - test script for OSS delete API
config/
└── config.ini              # Add cleanup threshold to [OSS设置]
```

**Structure Decision**: Single project - extend existing `src/storage/` module with new `cleanup.py` file for cleanup logic. Integrates with existing upload_queue.py callback mechanism.

## Complexity Tracking

No constitution violations requiring justification.
