# Feature Specification: OSS Storage Cleanup

**Feature Branch**: `005-oss-cleanup`
**Created**: 2026-01-06
**Status**: Draft
**Input**: User description: "直播视频的录制是无止境的，因此我希望，在main.py启动后，每一次触发上传，都触发一次清理任务，清理任务应该从db中先检索一下目前OSS视频的总大小，超过阈值了就触发一次清理，以Session为单位，清理最早的，直到容量小于当前阈值，上传触发的清理任务是阻塞的，多个上传触发清理的话，清理任务应该并发安全，临界区只允许进入一个"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Automatic Storage Cleanup on Upload (Priority: P1)

As a live stream recorder operator, I want the system to automatically check and clean up old recordings from OSS when storage exceeds a threshold, so that I don't run out of cloud storage space or incur unexpected costs.

**Why this priority**: This is the core functionality requested. Without automatic cleanup, continuous recording will eventually exhaust storage quota, causing upload failures and service disruption.

**Independent Test**: Can be fully tested by configuring a low storage threshold (e.g., 100MB), uploading several recordings, and verifying that the oldest sessions are deleted when the threshold is exceeded.

**Acceptance Scenarios**:

1. **Given** OSS storage is below threshold (e.g., 8GB used, 10GB threshold), **When** a new segment upload completes, **Then** no cleanup occurs and all existing recordings remain intact.

2. **Given** OSS storage exceeds threshold (e.g., 11GB used, 10GB threshold), **When** a new segment upload completes, **Then** the system deletes the oldest complete session(s) until storage falls below threshold.

3. **Given** multiple uploads complete simultaneously, **When** cleanup is triggered by multiple threads, **Then** only one cleanup task executes at a time (concurrent safety).

4. **Given** cleanup is in progress, **When** another upload completes and triggers cleanup, **Then** the second cleanup request waits (blocks) until the first completes, then re-evaluates storage.

---

### User Story 2 - Session-Based Cleanup Granularity (Priority: P1)

As a live stream recorder operator, I want cleanup to delete entire recording sessions (all segments of a stream) rather than individual segments, so that I don't end up with incomplete recordings that are useless for playback.

**Why this priority**: Deleting partial sessions would leave orphaned segments that cannot be played back meaningfully, defeating the purpose of the recording system.

**Independent Test**: Can be tested by creating multiple sessions with multiple segments each, triggering cleanup, and verifying that all segments of deleted sessions are removed while other sessions remain complete.

**Acceptance Scenarios**:

1. **Given** a session with 5 segments exists and is selected for cleanup, **When** cleanup executes, **Then** all 5 segments are deleted from OSS and their database records are updated.

2. **Given** sessions A (oldest), B, and C exist, **When** cleanup needs to free 500MB and session A is 600MB, **Then** only session A is deleted (FIFO order by session start time).

3. **Given** sessions A (300MB, oldest) and B (400MB) exist, **When** cleanup needs to free 500MB, **Then** both sessions A and B are deleted to reach the target.

---

### User Story 3 - Cleanup Configuration (Priority: P2)

As a system administrator, I want to configure the storage threshold for cleanup, so that I can balance storage costs against recording retention based on my specific needs.

**Why this priority**: Configuration flexibility is important but secondary to core functionality. The system can work with sensible defaults initially.

**Independent Test**: Can be tested by modifying configuration values and verifying that cleanup behavior respects the new threshold settings.

**Acceptance Scenarios**:

1. **Given** threshold is set to 50GB in configuration, **When** storage reaches 51GB after upload, **Then** cleanup triggers and removes oldest sessions until below 50GB.

2. **Given** threshold is set to 0 (disabled), **When** uploads complete, **Then** no automatic cleanup occurs regardless of storage usage.

3. **Given** configuration file is missing threshold setting, **When** system starts, **Then** a sensible default threshold is used (or cleanup is disabled).

---

### User Story 4 - Cleanup Logging and Visibility (Priority: P3)

As a system operator, I want to see logs of cleanup activities, so that I can audit what was deleted and troubleshoot any issues.

**Why this priority**: Logging is important for operations but the system can function without detailed logging initially.

**Independent Test**: Can be tested by triggering cleanup and verifying that appropriate log entries are created.

**Acceptance Scenarios**:

1. **Given** cleanup executes successfully, **When** I check system logs, **Then** I see which sessions were deleted, how much space was freed, and current storage usage.

2. **Given** cleanup fails (e.g., OSS deletion error), **When** I check system logs, **Then** I see the error details and which session failed to delete.

---

### Edge Cases

- What happens when the only session in OSS is currently being recorded (active session)?
  - Active sessions (no `ended_at` timestamp) should be protected from cleanup
- What happens when OSS deletion fails for some segments in a session?
  - Cleanup should log the error and continue; partial failures should not block other cleanup operations
- What happens when database records exist but OSS files are already deleted (orphaned records)?
  - System should handle gracefully (treat as already deleted) and update database records accordingly
- What happens when storage calculation from database doesn't match actual OSS usage?
  - Database is source of truth for cleanup decisions; periodic reconciliation could be a future enhancement
- What happens when threshold is set lower than current single-session average size?
  - System should still function, potentially clearing all completed sessions except active ones

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST calculate total OSS storage usage from database records (sum of `file_size` for all uploaded segments)
- **FR-002**: System MUST trigger cleanup check after each successful segment upload completes
- **FR-003**: System MUST compare current storage usage against configured threshold before deciding to clean
- **FR-004**: System MUST delete sessions in FIFO order (oldest `started_at` first) when cleanup is needed
- **FR-005**: System MUST delete all segments belonging to a session when that session is selected for cleanup
- **FR-006**: System MUST delete both TS files (`oss_path`) and MP4 files (`mp4_oss_path`) when cleaning a segment
- **FR-007**: System MUST update database records after successful OSS deletion (mark as deleted or remove records)
- **FR-008**: System MUST protect active sessions (where `ended_at` is NULL) from cleanup
- **FR-009**: System MUST ensure only one cleanup task executes at a time (mutex/lock mechanism)
- **FR-010**: System MUST block upload-triggered cleanup requests until any in-progress cleanup completes
- **FR-011**: System MUST re-evaluate storage after acquiring cleanup lock (another cleanup may have freed space)
- **FR-012**: System MUST allow configuration of storage threshold via config file
- **FR-013**: System MUST allow disabling automatic cleanup via configuration (threshold = 0 or explicit disable flag)
- **FR-014**: System MUST log cleanup activities including sessions deleted, space freed, and any errors

### Key Entities

- **RecordingSession**: Represents a complete live stream recording. Key attributes: start time, end time, active status. Sessions are the unit of cleanup - entire sessions are deleted together.
- **RecordingSegment**: Individual video file within a session. Key attributes: file size, OSS path, MP4 path, upload status. Segments inherit their session's cleanup fate.
- **CleanupThreshold**: Configuration value representing maximum allowed OSS storage in bytes/GB before cleanup triggers.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: System maintains OSS storage below configured threshold (within one session's size tolerance) during continuous 24/7 recording operations
- **SC-002**: Cleanup operations complete without leaving partial sessions (0% orphaned segments after cleanup)
- **SC-003**: Concurrent upload operations (up to 10 simultaneous uploads) do not cause duplicate cleanup executions or race conditions
- **SC-004**: Cleanup adds less than 5 seconds overhead to individual upload operations under normal conditions
- **SC-005**: System logs provide complete audit trail of all cleanup operations (100% of deletions logged)
- **SC-006**: Active recording sessions are never deleted by automatic cleanup (0% data loss of in-progress recordings)

## Assumptions

- Database `file_size` field accurately reflects the OSS file size for storage calculations
- OSS deletion operations are idempotent (deleting already-deleted files doesn't cause errors)
- Session `started_at` timestamp is reliably set when recording begins
- Upload completion callbacks are reliable triggers for cleanup checks
- Configuration file is read at startup; changes require restart to take effect
