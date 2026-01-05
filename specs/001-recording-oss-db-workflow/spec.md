# Feature Specification: Recording & OSS Upload & Database Workflow

**Feature Branch**: `001-recording-oss-db-workflow`
**Created**: 2026-01-05
**Status**: Draft
**Input**: User description: "Document the video recording, OSS upload, and database workflow based on current implementation"

## Overview

This specification documents the existing end-to-end workflow for live stream recording, cloud storage upload (TOS/OSS), and database persistence. The workflow is implemented across `main.py`, `src/storage/` module, and configuration files.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Basic Recording with Automatic Upload (Priority: P1)

As a user, I want to record live streams and have the recordings automatically uploaded to cloud storage (TOS) while metadata is persisted to a database, so I can access recordings from anywhere without manual file management.

**Why this priority**: This is the core value proposition - automated recording and cloud backup without user intervention.

**Independent Test**: Start a recording with OSS enabled. Verify segment files appear in TOS bucket and database records are created.

**Acceptance Scenarios**:

1. **Given** a configured TOS bucket and enabled OSS upload, **When** a live stream recording completes, **Then** the recording file is uploaded to TOS and a `RecordingSegment` record is created with `upload_status=completed`.

2. **Given** split recording enabled (segments every N seconds), **When** FFmpeg creates a new segment file, **Then** the segment is detected within 2 seconds, written to database, and queued for upload immediately (real-time processing).

3. **Given** a recording session starts, **When** `main.py` calls `recording_manager.start_recording()`, **Then** a `RecordingSession` record is created with anchor_name, platform, live_room_url, and started_at timestamp.

---

### User Story 2 - Graceful Shutdown with Data Preservation (Priority: P2)

As a user, I want the system to gracefully handle shutdown signals (Ctrl+C, SIGTERM) so that in-progress recordings are properly finalized and pending uploads are completed.

**Why this priority**: Data integrity during interruption is critical for long-running recording sessions.

**Independent Test**: Start a recording, press Ctrl+C, verify FFmpeg receives SIGINT, segment watcher stops, pending uploads are flushed, and no data is lost.

**Acceptance Scenarios**:

1. **Given** active recordings and pending uploads, **When** SIGINT/SIGTERM is received, **Then** `graceful_shutdown()` sets `exit_recording=True`, sends SIGINT to FFmpeg processes, waits for them to exit, and calls `recording_manager.stop()` to flush upload queue.

2. **Given** a SegmentWatcher is running, **When** shutdown is triggered, **Then** the watcher performs a final scan to process any remaining segments before stopping.

---

### User Story 3 - Upload Retry on Failure (Priority: P3)

As a user, I want failed uploads to be automatically retried so transient network issues don't result in data loss.

**Why this priority**: Network reliability varies; automatic retry improves upload success rate.

**Independent Test**: Simulate upload failure, verify retry is scheduled, verify status transitions: PENDING -> UPLOADING -> FAILED -> PENDING (retry) -> COMPLETED.

**Acceptance Scenarios**:

1. **Given** an upload fails, **When** retry count < max_retries (default 3), **Then** the segment is re-queued with priority=1 (lower than new uploads) and `upload_retry_count` is incremented.

2. **Given** an upload fails after max_retries, **When** the retry loop runs, **Then** the segment status is set to `FAILED` with error message, and `on_upload_failed` callback is triggered.

---

### User Story 4 - Local File Cleanup After Upload (Priority: P3)

As a user, I want uploaded files to be automatically deleted from local storage to save disk space.

**Why this priority**: Disk management is important for long-running recording operations.

**Independent Test**: Enable `delete_after_upload`, complete an upload, verify local file is deleted and `local_file_deleted=True` in database.

**Acceptance Scenarios**:

1. **Given** `delete_after_upload=True` in config, **When** upload succeeds, **Then** the local file is removed and `RecordingSegment.local_file_deleted` is set to `True`.

---

### Edge Cases

- What happens when local file is deleted before upload? System sets segment status to `SKIPPED` with error "Local file not found"
- What happens when TOS bucket is inaccessible at startup? Upload is disabled, warning logged, recording continues without upload
- What happens when database is unavailable? Uses default SQLite at `data/recordings.db`
- What happens when FFmpeg crashes? Return code logged, session ended, partial segments still processed
- What happens when segment file is empty (0 bytes)? SegmentWatcher skips the file

## Workflow Architecture

### Phase 1: Initialization (`main.py` startup)

1. Load `config/config.ini` for OSS settings (`[OSS设置]` section)
2. Load `config/tos_credentials.ini` for TOS credentials
3. Initialize `RecordingManager.from_config()`:
   - Create `DatabaseManager` (SQLite default or configured URL)
   - Create `TOSUploader` if enabled
   - Verify bucket access with `check_bucket_access()`
4. Call `recording_manager.start()` to start `UploadWorker` thread
5. Register signal handlers for `SIGINT` and `SIGTERM`

### Phase 2: Recording Session Lifecycle

```
start_record() -> check_subprocess() -> FFmpeg recording
       |
recording_manager.start_recording()  <- Creates RecordingSession
       |
SegmentWatcher.start()  <- Monitors for new segments
       |
on_segment_detected() callback
       |
recording_manager.on_segment_created()  <- Creates RecordingSegment + queues upload
       |
[FFmpeg exits]
       |
segment_watcher.stop() -> final scan
       |
recording_manager.end_recording()  <- Updates session.ended_at
```

### Phase 3: Upload Pipeline

```
UploadTask enqueued -> UploadWorker._worker_loop()
       |
Update status: PENDING -> UPLOADING
       |
tos_uploader.upload_file() -> TOS API
       |
[Success] -> Status: COMPLETED, oss_path saved, local file deleted
[Failure] -> Status: FAILED, error_message saved, retry scheduled
```

### Phase 4: Graceful Shutdown

```
SIGINT/SIGTERM received
       |
graceful_shutdown() handler
       |
exit_recording = True  <- Prevents new recordings
       |
For each active_recording:
  - segment_watcher.stop()
  - process.send_signal(SIGINT)
  - recording_manager.end_recording()
       |
Wait for FFmpeg processes to exit (10s timeout)
       |
recording_manager.stop()  <- Flushes upload queue
       |
sys.exit(0)
```

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST create a `RecordingSession` record when recording starts with anchor_name, platform, live_room_url, and started_at
- **FR-002**: System MUST detect new segment files within `poll_interval` seconds (default 2s) using SegmentWatcher
- **FR-003**: System MUST create a `RecordingSegment` record for each segment with local_file_path, file_name, file_format, file_size, segment_index
- **FR-004**: System MUST queue segments for upload to TOS with OSS key format: `{platform}/{date}/{anchor_name}/{filename}`
- **FR-005**: System MUST retry failed uploads up to `max_retries` times (default 3)
- **FR-006**: System MUST handle graceful shutdown by stopping watchers, signaling FFmpeg, and flushing upload queue
- **FR-007**: System MUST support split recording where FFmpeg outputs segments using `_%03d.{ext}` naming pattern
- **FR-008**: System MUST track upload status transitions: PENDING -> UPLOADING -> COMPLETED/FAILED/SKIPPED
- **FR-009**: System MUST delete local files after successful upload when `delete_after_upload` is enabled
- **FR-010**: System MUST log all segment lifecycle events with timestamps (detection, database write, upload start/complete)

### Key Entities

- **RecordingSession**: Represents one live broadcast recording. Contains anchor_name, platform, live_room_url, live_title, started_at, ended_at, record_quality, is_split, segment_count. Relationship: has many RecordingSegments.

- **RecordingSegment**: Represents a single recorded file (or segment in split mode). Contains session_id, segment_index, local_file_path, file_name, file_format, file_size, oss_path, oss_bucket, upload_status, upload_retry_count, upload_error_message, local_file_deleted.

- **UploadStatus**: Enumeration with values: PENDING, UPLOADING, COMPLETED, FAILED, SKIPPED.

- **UploadTask**: Priority queue item containing segment_id, local_path, platform, anchor_name, filename. Priority 0 for new uploads, 1 for retries.

## Configuration

### config/config.ini - [OSS设置] Section

| Setting | Description | Default |
|---------|-------------|---------|
| 启用OSS上传(是/否) | Enable/disable TOS upload | 否 |
| 上传后删除本地文件(是/否) | Delete local file after upload | 是 |
| 上传失败重试次数 | Max retry attempts | 3 |
| 数据库URL | SQLAlchemy database URL | sqlite:///data/recordings.db |

### config/tos_credentials.ini - [tos] Section

| Setting | Description |
|---------|-------------|
| endpoint | TOS API endpoint (e.g., tos-cn-beijing.ivolces.com) |
| region | TOS region (e.g., cn-beijing) |
| bucket | Bucket name |
| access_key | TOS access key |
| secret_key | TOS secret key |

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Segment detection latency is under 3 seconds from file creation to database record
- **SC-002**: Upload success rate exceeds 95% after retries
- **SC-003**: Graceful shutdown completes within 30 seconds for up to 10 concurrent recordings
- **SC-004**: Database query for session history returns results in under 100ms for 10,000 sessions
- **SC-005**: Zero data loss during normal shutdown (all segments in database, pending uploads flushed)
- **SC-006**: System supports concurrent recording of 50+ live rooms without upload queue backlog

## Assumptions

- TOS (Volcano Engine Object Storage) is the cloud storage provider
- FFmpeg outputs segments with `_%03d.{ext}` naming pattern for split recordings
- SQLite is acceptable for default single-instance deployments
- Network connectivity to TOS is generally stable (retries handle transient failures)
- Local disk has sufficient space for recording buffer before upload completes
