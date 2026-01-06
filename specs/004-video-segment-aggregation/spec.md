# Feature Specification: Video Segment Aggregation

**Feature Branch**: `004-video-segment-aggregation`
**Created**: 2026-01-06
**Status**: Draft
**Input**: User description: "现在每个录制Session会分为多个小段（目前是10mins 取决于配置文件），但是UI可视化的时候，是一个个的文件，我在想，是否可以把他们聚合为一整个video？我认知里应该是可以做到这个的"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Play Session as Continuous Video (Priority: P1)

As a user viewing a recorded live stream session, I want to watch all segments as a single continuous video without manually clicking through each segment, so that I can have a seamless viewing experience similar to watching the original live stream.

**Why this priority**: This is the core user need - the current experience requires manually clicking each 10-minute segment, which disrupts the viewing experience and makes it tedious to watch long recordings.

**Independent Test**: Can be fully tested by playing a multi-segment session and verifying continuous playback across segment boundaries without user intervention.

**Acceptance Scenarios**:

1. **Given** a recording session with 5 segments (50 minutes total), **When** I click play on the session, **Then** the video plays from segment 0 through segment 4 continuously without stopping or requiring manual intervention.

2. **Given** I am watching segment 2 of a 5-segment session, **When** segment 2 finishes, **Then** segment 3 begins playing automatically within 2 seconds.

3. **Given** I am watching an aggregated session, **When** I look at the progress bar, **Then** I see the total duration of all segments combined (not just the current segment).

---

### User Story 2 - Seek Across Segments (Priority: P2)

As a user watching an aggregated session, I want to seek/scrub to any point in the entire recording using a single timeline, so that I can quickly navigate to specific moments without knowing which segment contains them.

**Why this priority**: Seeking is essential for usability, but continuous playback (P1) provides more fundamental value. Users can work around limited seeking by watching continuously, but cannot work around manual segment switching.

**Independent Test**: Can be tested by seeking to various timestamps across different segments and verifying correct playback position.

**Acceptance Scenarios**:

1. **Given** a 50-minute session (5 segments × 10 minutes), **When** I seek to the 25-minute mark, **Then** playback starts at the beginning of segment 3 (index 2).

2. **Given** I seek to 37 minutes in a 50-minute session, **When** the seek completes, **Then** playback starts at 7 minutes into segment 4 (index 3).

3. **Given** I am at minute 5 of a session, **When** I seek backward to minute 45, **Then** playback moves to segment 5 (index 4) at the 5-minute mark within that segment.

---

### User Story 3 - Session Duration Display (Priority: P3)

As a user browsing recordings, I want to see the total duration of each session (sum of all segments), so that I can understand how long each recording is before deciding to watch it.

**Why this priority**: This is informational and improves browsing experience, but does not block core playback functionality.

**Independent Test**: Can be tested by comparing displayed duration against the sum of individual segment durations.

**Acceptance Scenarios**:

1. **Given** I am viewing the session list for an anchor, **When** I look at a session with 6 segments, **Then** I see the total combined duration (e.g., "58:32") rather than individual segment durations.

2. **Given** a session where some segments have different durations (first and last segments may be shorter), **When** the total duration is displayed, **Then** it accurately reflects the sum of actual segment durations.

---

### User Story 4 - Segment-Level Navigation (Optional) (Priority: P4)

As a user watching a long session, I want to optionally see segment boundaries and jump directly to specific segments, so that I can quickly navigate to approximate positions in very long recordings.

**Why this priority**: This is a convenience feature that enhances P2 but is not required for basic functionality. The unified timeline (P2) provides sufficient navigation for most use cases.

**Independent Test**: Can be tested by clicking on segment markers and verifying playback jumps to correct positions.

**Acceptance Scenarios**:

1. **Given** I am watching an aggregated session, **When** I view the player interface, **Then** I can optionally see markers or a list indicating segment boundaries.

2. **Given** I click on "Segment 4" in the segment list, **When** the player responds, **Then** playback jumps to the start of segment 4.

---

### Edge Cases

- What happens when a segment in the middle of a session is missing or corrupted?
  - The player should skip the corrupted segment and continue to the next available segment, displaying a brief notification to the user.

- What happens when a segment is still being converted (mp4_status = processing)?
  - Playback should proceed up to the last completed segment. If the user reaches an unconverted segment, show a "Processing..." indicator and auto-resume when ready.

- What happens when seeking to a position in a segment that hasn't been uploaded yet?
  - Display a loading indicator and wait for the segment to become available, or show an error if the segment is not expected to be available.

- What happens with sessions that have only 1 segment?
  - Single-segment sessions should play normally without any aggregation logic affecting them.

- What happens if segment durations in the database are inaccurate or missing?
  - Fall back to estimating positions based on segment count and average segment duration, or fetch duration on-demand during playback.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST provide continuous playback across all segments in a recording session without user intervention between segments.

- **FR-002**: System MUST display a unified progress bar/timeline representing the total duration of all segments combined.

- **FR-003**: System MUST support seeking to any timestamp within the aggregated session, automatically determining and loading the correct segment.

- **FR-004**: System MUST display the total session duration (sum of all segment durations) in the session list and player interface.

- **FR-005**: System MUST automatically advance to the next segment when the current segment finishes playing.

- **FR-006**: System MUST handle missing or corrupted segments gracefully by skipping to the next available segment and notifying the user.

- **FR-007**: System MUST handle in-progress segments (still being converted) by showing appropriate status and resuming playback when ready.

- **FR-008**: System SHOULD provide optional segment-level navigation to allow users to jump directly to specific segments.

- **FR-009**: System MUST maintain accurate time display showing current position within the entire session (not just current segment).

- **FR-010**: System MUST preserve the ability to view and play individual segments separately for users who prefer segment-by-segment navigation.

### Key Entities

- **Recording Session**: A complete live stream recording that may contain multiple segments. Key attributes: total_duration (aggregated), segment_count, playback_position.

- **Recording Segment**: An individual video file within a session. Key attributes: segment_index, duration, start_offset (cumulative offset within session), playback_status.

- **Aggregated Timeline**: A virtual timeline representing the entire session. Maps absolute timestamps to specific segment + offset combinations.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Users can watch a multi-segment recording session from start to finish without any manual intervention to switch segments.

- **SC-002**: Segment transitions occur within 2 seconds, maintaining viewing continuity.

- **SC-003**: Seeking to any point in a session loads the correct segment and position within 3 seconds.

- **SC-004**: Total session duration displayed is accurate to within 1 second of the sum of individual segment durations.

- **SC-005**: 95% of segment transitions are seamless (no visible loading indicator or playback interruption).

- **SC-006**: Users can navigate a 2-hour recording (12+ segments) as easily as a single-segment recording.

## Assumptions

- All segments within a session use the same video format and encoding parameters (as they come from the same FFmpeg segmentation process).
- Segment durations are stored accurately in the database after MP4 conversion.
- The existing presigned URL generation can handle rapid sequential requests for different segments.
- Network conditions are sufficient for buffering the next segment before the current one ends (pre-fetching is feasible).
- The existing video player component supports playlist-like functionality or can be extended to support it.
