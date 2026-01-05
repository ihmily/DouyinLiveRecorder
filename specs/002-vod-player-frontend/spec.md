# Feature Specification: VOD Player Frontend with Seekable Playback

**Feature Branch**: `002-vod-player-frontend`
**Created**: 2026-01-05
**Status**: Draft
**Input**: User description: "VOD player with seekable playback, OSS to public URL conversion, and frontend for video-on-demand"

## Overview

This feature implements a complete VOD (Video on Demand) playback system that enables users to browse and watch recorded live streams. The system converts private OSS storage paths to time-limited public URLs, allowing direct browser playback with full seek support. The architecture separates control flow (metadata, authentication, URL signing) from data flow (video streaming directly from cloud storage).

## Clarifications

### Session 2026-01-05

- Q: When should TS-to-MP4 conversion be triggered? → A: Conversion happens locally BEFORE OSS upload. Workflow: Recording complete → MP4 conversion → OSS upload (MP4 only). Use CSP or DAG pattern for elegant pipeline orchestration, avoiding hard-coded logic.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Browse and Play Recordings (Priority: P1)

As a user, I want to browse recorded live streams by platform and anchor, then play any recording with the ability to seek to any position instantly, so I can quickly find and watch specific moments from past broadcasts.

**Why this priority**: This is the core user journey - browsing content and playing videos with seek capability is the fundamental value proposition.

**Independent Test**: Navigate through platform/anchor tree, select a recording session, click play, drag the progress bar to a random position - video should jump to that position within 1 second.

**Acceptance Scenarios**:

1. **Given** recordings exist in the database, **When** a user opens the VOD player, **Then** they see a tree navigation showing platforms, anchors, and recording sessions.

2. **Given** a user selects a recording session with multiple segments, **When** they click on a segment, **Then** the video player loads and begins playback within 3 seconds.

3. **Given** a video is playing, **When** the user drags the progress bar to any position, **Then** playback resumes from that position within 1 second (no full file download required).

---

### User Story 2 - Secure Time-Limited Access (Priority: P2)

As a system administrator, I want video URLs to be time-limited and secure, so that private recordings cannot be accessed by unauthorized users or through leaked/bookmarked URLs.

**Why this priority**: Security is essential for protecting private content - URLs must expire and be non-shareable.

**Independent Test**: Request a play URL, wait for expiration time, attempt to access - should return access denied.

**Acceptance Scenarios**:

1. **Given** a user requests to play a video, **When** the system generates a playback URL, **Then** the URL contains a cryptographic signature and expiration timestamp.

2. **Given** a playback URL was generated 2 hours ago (past default expiration), **When** someone attempts to access it, **Then** access is denied with an appropriate error message.

3. **Given** a user copies a playback URL to share, **When** another user/device attempts to access it, **Then** access works only if within the validity period (URL is not user-specific by default).

---

### User Story 3 - Multi-Segment Session Playback (Priority: P2)

As a user watching a long recording split into multiple segments, I want to easily navigate between segments and see which segment I'm currently watching, so I can follow the complete broadcast chronologically.

**Why this priority**: Long recordings are split into segments for reliability; users need seamless navigation between them.

**Independent Test**: Open a session with 5 segments, play segment 3, finish it, verify automatic or manual transition to segment 4.

**Acceptance Scenarios**:

1. **Given** a recording session has multiple segments, **When** the user views the session details, **Then** all segments are displayed with their duration and status (ready/processing/failed).

2. **Given** the user is watching segment 2, **When** they click on segment 4, **Then** playback switches to segment 4 immediately.

3. **Given** segment 3 is still being processed (MP4 conversion), **When** the user tries to play it, **Then** a clear message indicates the segment is not yet ready.

---

### User Story 4 - Format Conversion for Seek Support (Priority: P3)

As a system operator, I want recorded TS files to be automatically converted to seek-friendly MP4 format before upload, so users can enjoy instant seek without waiting for full file downloads.

**Why this priority**: Technical enabler for P1 - without MP4 conversion, seek would require downloading entire file first.

**Independent Test**: Complete a recording, verify MP4 conversion runs locally, then MP4 is uploaded to storage with moov atom at file start.

**Acceptance Scenarios**:

1. **Given** a recording segment completes locally, **When** the processing pipeline runs, **Then** MP4 conversion happens BEFORE OSS upload (local conversion, not cloud-side).

2. **Given** conversion completes successfully, **When** the upload step runs, **Then** only the MP4 file is uploaded to OSS (TS file may be retained locally or discarded based on config).

3. **Given** conversion fails, **When** the pipeline handles the error, **Then** the original TS file is uploaded as fallback, and segment is marked with conversion_failed status.

---

### Edge Cases

- What happens when a user seeks beyond the video duration? Player should clamp to the end of the video.
- What happens when the signed URL expires during playback? Player should show an error and offer a "Refresh" button to get a new URL.
- What happens when MP4 conversion is in progress? Segment shows "Processing" status and is not playable until complete.
- What happens when a recording has zero segments? Session is listed but marked as "Empty" with no play option.
- What happens when TOS/OSS is temporarily unavailable? Player shows connection error with retry option.
- What happens when user has slow connection? Progressive download with buffering indicator; seek works but may require buffering.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST display recordings in a hierarchical navigation: Platform → Anchor → Session → Segments
- **FR-002**: System MUST generate time-limited signed URLs for video playback (default 1 hour validity)
- **FR-003**: System MUST support seeking to any position in a video without downloading the entire file
- **FR-004**: System MUST convert TS recordings to Fast Start MP4 format (moov atom at file beginning) locally BEFORE uploading to OSS
- **FR-005**: System MUST track conversion status for each segment: pending, processing, completed, failed
- **FR-011**: System MUST implement the recording pipeline using composable stages (CSP/DAG pattern): Recording → Conversion → Upload, avoiding hard-coded sequential logic
- **FR-006**: System MUST display segment duration after conversion
- **FR-007**: System MUST allow users to switch between segments within a session
- **FR-008**: System MUST show recording metadata: anchor name, platform, start time, total duration
- **FR-009**: System MUST handle URL expiration gracefully with user-friendly error and refresh option
- **FR-010**: System MUST NOT route video data through the application server (direct browser-to-storage)

### Key Entities

- **Platform**: A streaming platform name (e.g., "抖音直播", "快手直播"). Used for top-level grouping.

- **Anchor**: A streamer/broadcaster identified by name. Has multiple recording sessions across platforms.

- **RecordingSession**: A single live broadcast event. Contains metadata (start/end time, platform, anchor) and has multiple segments.

- **RecordingSegment**: A single video file within a session. Contains:
  - Original TS file path in storage
  - MP4 file path (after conversion)
  - Conversion status
  - Duration (seconds)
  - File size

- **PlaybackURL**: A temporary signed URL for video access. Contains:
  - Signed URL with expiration
  - Expiration timestamp
  - Segment metadata for player display

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Users can seek to any position in a video and playback resumes within 1 second
- **SC-002**: Video playback begins within 3 seconds of clicking play
- **SC-003**: 95% of TS-to-MP4 conversions complete successfully
- **SC-004**: Signed URLs expire correctly after the configured validity period
- **SC-005**: Video streaming does not consume application server bandwidth (0 bytes proxied)
- **SC-006**: Navigation tree loads within 2 seconds for libraries with 1000+ sessions
- **SC-007**: System supports 50 concurrent video playback sessions without degradation
- **SC-008**: Users can browse 10,000+ recordings with pagination loading under 1 second per page

## Assumptions

- TOS (Volcano Engine Object Storage) is used as the storage backend with presigned URL support
- FFmpeg is available locally for TS-to-MP4 conversion (conversion runs on recording machine before upload)
- Recordings are already being stored with the existing RecordingSession/RecordingSegment data model
- The storage bucket is configured as private (no public access)
- Users access the system via modern web browsers (Chrome, Firefox, Safari, Edge - last 2 versions)
- Initial release does not require user authentication (single-user/internal deployment)
- Local disk has sufficient space to hold both TS and MP4 temporarily during conversion
- Pipeline stages (Recording → Conversion → Upload) can be composed declaratively using CSP or DAG patterns

## Out of Scope

- User authentication and multi-user access control (future enhancement)
- Live streaming / real-time playback of ongoing recordings
- Video editing or clipping features
- Automatic thumbnail generation
- Search functionality across recordings
- Mobile native applications (web-only for initial release)
- CDN integration (direct TOS access for initial release)
