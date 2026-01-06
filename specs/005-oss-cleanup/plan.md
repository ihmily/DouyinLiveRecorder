# Implementation Plan: OSS Storage Cleanup

**Branch**: `005-oss-cleanup` | **Date**: 2026-01-06 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/005-oss-cleanup/spec.md`

**Note**: This template is filled in by the `/speckit.plan` command. See `.specify/templates/commands/plan.md` for the execution workflow.

## Summary

Implement automatic OSS storage cleanup that triggers after each upload to delete oldest completed sessions (FIFO) when storage exceeds a configurable threshold. The cleanup is session-based (deletes all segments together), thread-safe via mutex, and integrates with the existing graceful shutdown handler to wait for in-progress cleanup operations before exiting.

## Technical Context

**Language/Version**: Python >= 3.10 (existing project requirement)
**Primary Dependencies**: SQLAlchemy 2.0+, `tos` (Volcano Engine TOS SDK), loguru, threading
**Storage**: SQLite (default, data/recordings.db), also supports PostgreSQL/MySQL via SQLAlchemy
**Testing**: Manual testing via `demo.py` pattern, integration tests with mock TOS
**Target Platform**: Linux server (primary), Windows, macOS
**Project Type**: Single Python application with async architecture
**Performance Goals**: Cleanup adds <5 seconds overhead to uploads; concurrent uploads (up to 10) handled safely
**Constraints**: Mutex ensures only one cleanup runs at a time; graceful shutdown waits for cleanup completion
**Scale/Scope**: 24/7 continuous recording, hundreds of sessions, GB-scale cleanup operations

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

### Pre-Design Gate Evaluation

| Principle | Status | Evidence |
|-----------|--------|----------|
| **I. Recording Reliability** | ✅ PASS | Cleanup protects active sessions (FR-008); graceful shutdown waits for cleanup completion; FFmpeg processes unaffected by cleanup thread |
| **II. Platform Abstraction** | ✅ PASS | No changes to spider/stream modules; cleanup operates at storage layer only |
| **III. Configuration Simplicity** | ✅ PASS | Config in `config/config.ini` [OSS设置] section; threshold in GB (user-friendly unit); disable via threshold=0 |
| **IV. Async-First Architecture** | ✅ PASS | Cleanup uses `threading.Lock()` for mutex; integrates with existing thread model; non-blocking to main recording loop |
| **V. Observable Operations** | ✅ PASS | All cleanup operations logged via loguru; session deletions audited with timestamp, size freed, and error details |

### Specific Compliance Notes

- **FR-008 (Protect Active Sessions)**: Sessions with `ended_at IS NULL` are excluded from cleanup candidates
- **Graceful Shutdown Enhancement**: Signal handler will wait for in-progress cleanup to complete before exit
- **Thread Safety**: Single cleanup lock ensures concurrent upload triggers don't cause race conditions

## Project Structure

### Documentation (this feature)

```text
specs/005-oss-cleanup/
├── plan.md              # This file (/speckit.plan command output)
├── research.md          # Phase 0 output (/speckit.plan command)
├── data-model.md        # Phase 1 output (/speckit.plan command)
├── quickstart.md        # Phase 1 output (/speckit.plan command)
├── contracts/           # Phase 1 output (internal APIs, no REST endpoints)
└── tasks.md             # Phase 2 output (/speckit.tasks command)
```

### Source Code (repository root)

```text
src/storage/                    # Storage management module (existing)
├── __init__.py                 # Module exports
├── cleanup.py                  # StorageCleanup class (NEW - core cleanup logic)
├── database.py                 # DatabaseManager (existing)
├── manager.py                  # RecordingManager (MODIFY - add cleanup integration)
├── models.py                   # SQLAlchemy models (existing)
├── repository.py               # RecordingRepository (MODIFY - add cleanup queries)
├── tos_uploader.py             # TOSUploader (MODIFY - add delete_object method)
├── upload_queue.py             # UploadWorker (MODIFY - trigger cleanup callback)
└── pipeline.py                 # VOD pipeline (existing)

main.py                         # Entry point (MODIFY - graceful shutdown enhancement)

config/
└── config.ini                  # Config file (MODIFY - add cleanup settings)
```

**Structure Decision**: Single Python project. Cleanup functionality is a new module (`cleanup.py`) within the existing `src/storage/` package. No new directories needed. Integration via callback pattern keeps modules loosely coupled.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

No violations. All constitution principles are satisfied without exceptions.
