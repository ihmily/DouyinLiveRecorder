# Research: Video Segment Aggregation

**Feature**: 004-video-segment-aggregation
**Date**: 2026-01-06

## Research Questions Addressed

1. Seamless multi-segment video playback with Video.js
2. Pre-fetching strategies for minimizing transition time
3. Unified timeline/progress bar implementation
4. Browser localStorage patterns for playback position
5. Vue Router handling of Chinese characters in URLs

---

## 1. Seamless Playback Strategy

### Decision: Canvas Overlay + Source Switching

**Rationale**: Given our existing Video.js 8.10 setup and MP4 format, the canvas overlay technique provides the best balance of implementation simplicity and user experience.

**Implementation Approach**:
1. Detect when current segment is ~5 seconds from ending
2. Pre-fetch presigned URL for next segment
3. On segment end event:
   - Capture last frame to canvas overlay
   - Switch video source to next segment
   - Hide canvas when "playing" event fires

**Alternatives Considered**:

| Approach | Pros | Cons | Why Rejected |
|----------|------|------|--------------|
| MSE (Media Source Extensions) | True gapless playback | Requires fragmented MP4; iOS incompatible | Would require re-encoding all existing MP4s |
| HLS Playlist | Native Video.js support | Requires .m3u8 generation | Additional backend complexity; files already in MP4 |
| videojs-playlist plugin | Simple API | Visible gaps between videos | Poor UX for long sessions |

**Key Code Pattern**:
```javascript
// Capture frame before source change
const captureFrame = (videoElement, canvas) => {
  const ctx = canvas.getContext('2d');
  ctx.drawImage(videoElement, 0, 0, canvas.width, canvas.height);
  canvas.style.display = 'block';
};

// Hide canvas when new video starts playing
player.on('playing', () => {
  canvas.style.display = 'none';
});
```

---

## 2. Pre-fetching Strategy

### Decision: Fetch API with Low Priority + 5-Second Threshold

**Rationale**: Simple to implement, works with our presigned URL system, and provides sufficient buffer time for segment transitions.

**Implementation Approach**:
1. When `currentTime > (duration - 5)`, trigger pre-fetch
2. Use `fetch(nextUrl, { priority: 'low' })` to avoid blocking main content
3. Store pre-fetched URL in component state for immediate use
4. Pre-fetch only one segment ahead (not entire playlist)

**Alternatives Considered**:

| Approach | Pros | Cons | Why Rejected |
|----------|------|------|--------------|
| Service Worker | Most sophisticated caching | Overkill for single-user; complex | Our segments are large (10min); cache would bloat |
| `<link rel="preload">` | Browser-native | Limited support; needs DOM manipulation | Video.js already manages sources |
| videojs-cdn-prefetch | Purpose-built plugin | Designed for HLS segments | Our files are complete MP4s, not HLS segments |

**Key Consideration**: Presigned URLs expire (default 1 hour), so we pre-fetch URL metadata, not the video data itself.

---

## 3. Unified Timeline Implementation

### Decision: Custom Progress Bar with Cumulative Offsets

**Rationale**: Video.js ProgressControl tracks single-video duration. We need a custom component that:
- Calculates total duration across all converted segments
- Maps unified seek position to segment + local offset
- Updates in real-time as playback progresses

**Implementation Approach**:

```typescript
interface SegmentTimeline {
  segments: Array<{
    id: number;
    duration: number;
    startOffset: number; // cumulative offset
  }>;
  totalDuration: number;
}

// Build timeline from segment list
function buildTimeline(segments: SegmentInfo[]): SegmentTimeline {
  let offset = 0;
  const mapped = segments
    .filter(s => s.mp4_status === 'completed' && s.duration)
    .map(s => {
      const entry = { id: s.id, duration: s.duration!, startOffset: offset };
      offset += s.duration!;
      return entry;
    });
  return { segments: mapped, totalDuration: offset };
}

// Find segment for a given unified position
function findSegmentForPosition(timeline: SegmentTimeline, position: number) {
  for (const seg of timeline.segments) {
    if (position < seg.startOffset + seg.duration) {
      return {
        segment: seg,
        localPosition: position - seg.startOffset
      };
    }
  }
  return null;
}
```

**Visual Design**:
- Single progress bar representing total duration
- Optional: segment markers (thin vertical lines) at boundaries
- Time display shows unified position (e.g., "47:32 / 1:23:45")

---

## 4. Playback Position Persistence

### Decision: localStorage with Session-Keyed Storage

**Rationale**: localStorage persists across browser sessions, is widely supported, and has sufficient capacity for our use case.

**Key Implementation Details**:

**Storage Key Format**: `vod_position_{anchor_name}_{session_timestamp}`
- Unique per session
- Human-readable for debugging
- Example: `vod_position_Seven(国服老虎)_2026-01-06_14-01-37`

**Data Structure**:
```typescript
interface PlaybackState {
  position: number;        // Cumulative position in seconds
  segmentId: number;       // Current segment ID
  timestamp: number;       // When this was saved (for expiry)
}
```

**Save Frequency**: Every 5 seconds during playback (throttled to avoid excessive writes)

**Edge Cases**:
- Private browsing: Wrap in try-catch, fallback to in-memory only
- Position > available duration: Reset to 0 (handles deleted segments)
- Video completed: Remove stored position

**Expiry Policy**: 30 days (configurable)

---

## 5. URL Routing with Chinese Characters

### Decision: Human-Readable Path with URL Encoding

**Rationale**: Vue Router 4 automatically handles encoding/decoding. Chinese characters in URLs will be percent-encoded in the address bar but displayed correctly in the UI.

**Route Definition**:
```typescript
{
  path: '/:anchorName/:sessionTimestamp',
  name: 'Player',
  component: Player,
  props: true
}
```

**URL Examples**:
- Displayed in browser: `http://localhost:5173/Seven(国服老虎)/2026-01-06_14-01-37`
- Encoded form: `http://localhost:5173/Seven(%E5%9B%BD%E6%9C%8D%E8%80%81%E8%99%8E)/2026-01-06_14-01-37`
- Both work; Vue Router handles conversion

**Backend Lookup**:
```python
@router.get("/{anchor_name}/{session_timestamp}")
async def get_session_by_path(anchor_name: str, session_timestamp: str):
    # anchor_name is automatically URL-decoded by FastAPI
    session = await db.query(RecordingSession).filter(
        RecordingSession.anchor_name == anchor_name,
        RecordingSession.started_at.like(f"{session_timestamp}%")
    ).first()
```

**Special Characters Handling**:
- Parentheses `()`: Allowed in URLs, no encoding needed
- Slashes in names: Would break routing; use the database session ID as fallback

**Alternatives Considered**:

| Approach | Pros | Cons | Why Rejected |
|----------|------|------|--------------|
| Numeric IDs only | No encoding issues | Not human-readable | User explicitly requested readable URLs |
| Pinyin conversion | ASCII-only URLs | Loses meaning; complex | Unnecessary with modern browsers |
| Base64 encoding | Consistent format | Completely unreadable | Defeats purpose of human-readable URLs |

---

## Summary of Technical Decisions

| Component | Decision | Key Rationale |
|-----------|----------|---------------|
| Seamless playback | Canvas overlay + source switch | Simple; works with existing MP4s |
| Pre-fetching | Fetch API, 5-sec threshold | Matches presigned URL workflow |
| Unified timeline | Custom cumulative offset tracker | Video.js doesn't support multi-video natively |
| Position storage | localStorage, session-keyed | Persistent; widely supported |
| URL routing | Accept URL encoding, decode in UI | Vue Router handles automatically |

---

## Dependencies

No new packages required. All functionality can be implemented with:
- Video.js 8.10.0 (existing)
- Vue 3.4.0 (existing)
- Vue Router 4.2.0 (existing)
- Native localStorage API
- Native Fetch API
- HTML5 Canvas API
