# Quickstart: Video Segment Aggregation

**Feature**: 004-video-segment-aggregation
**Date**: 2026-01-06

## Prerequisites

- Existing VOD player setup working (`vod-player/backend` and `vod-player/frontend`)
- At least one recording session with multiple converted segments (mp4_status = COMPLETED)
- Python 3.10+, Node.js 18+, pnpm/npm

## Development Setup

### 1. Start Backend

```bash
cd vod-player/backend
uv run uvicorn app.main:app --reload --port 8000
```

### 2. Start Frontend

```bash
cd vod-player/frontend
pnpm dev
```

### 3. Access Player

Navigate to a session using the new URL format:
```
http://localhost:5173/{anchor_name}/{session_timestamp}
```

Example:
```
http://localhost:5173/Seven(国服老虎)/2026-01-06_14-01-37
```

## Testing the Feature

### Test 1: Continuous Playback

1. Open a session with 3+ converted segments
2. Start playback from segment 0
3. Let it play through segment boundaries
4. **Expected**: Video continues without manual intervention

### Test 2: Cross-Segment Seeking

1. Open a session with 3+ converted segments
2. Note the total duration in progress bar
3. Seek to a position beyond the first segment
4. **Expected**: Correct segment loads at correct position

### Test 3: Playback Position Persistence

1. Open a session and play to ~50% position
2. Close the browser tab
3. Reopen the same URL
4. **Expected**: Playback resumes from saved position

### Test 4: Human-Readable URLs

1. Open home page
2. Navigate to a session
3. Check browser URL
4. **Expected**: URL contains anchor name and timestamp, not numeric ID

## Key Files Changed

### Backend

| File | Change |
|------|--------|
| `app/routers/api.py` | Add `/sessions/by-path/` and `/sessions/{id}/aggregated` endpoints |
| `app/schemas.py` | Add `AggregatedSession`, `AggregatedSegment` schemas |
| `app/services/aggregation.py` | NEW: Timeline computation logic |

### Frontend

| File | Change |
|------|--------|
| `src/router/index.ts` | New route pattern `/:anchorName/:sessionTimestamp` |
| `src/views/Player.vue` | Support aggregated playback |
| `src/components/AggregatedPlayer.vue` | NEW: Unified timeline player |
| `src/stores/playback.ts` | NEW: localStorage persistence |
| `src/services/timeline.ts` | NEW: Seek position calculations |

## API Endpoints

### New Endpoints

```
GET /api/sessions/by-path/{anchor_name}/{session_timestamp}
  → Returns AggregatedSession

GET /api/sessions/{session_id}/aggregated
  → Returns AggregatedSession

POST /api/segments/batch-urls
  → Returns BatchPlaybackUrls (for pre-fetching)
```

### Example Response

```json
{
  "session_id": 13,
  "anchor_name": "Seven(国服老虎)",
  "platform": "抖音直播",
  "session_timestamp": "2026-01-06_14-01-37",
  "total_duration": 3600.5,
  "converted_segment_count": 6,
  "total_segment_count": 7,
  "segments": [
    {
      "segment_id": 101,
      "segment_index": 0,
      "duration": 600.0,
      "start_offset": 0.0,
      "end_offset": 600.0
    },
    {
      "segment_id": 102,
      "segment_index": 1,
      "duration": 600.0,
      "start_offset": 600.0,
      "end_offset": 1200.0
    }
  ]
}
```

## Debugging Tips

### Check Timeline Calculation

In browser console:
```javascript
// Get current timeline state
console.log(window.__VOD_TIMELINE__)
```

### Check Stored Playback Position

```javascript
// List all saved positions
Object.keys(localStorage).filter(k => k.startsWith('vod_position_'))

// Get specific position
localStorage.getItem('vod_position_Seven(国服老虎)_2026-01-06_14-01-37')
```

### Check Backend Aggregation

```bash
curl "http://localhost:8000/api/sessions/13/aggregated" | jq
```

## Performance Targets

| Metric | Target | How to Verify |
|--------|--------|---------------|
| Segment transition | < 2 seconds | Watch segment boundary in player |
| Seek operation | < 3 seconds | Seek to different segment |
| Position restore | < 2 seconds | Reload page with saved position |

## Troubleshooting

### "Session not found" on human-readable URL

- Check anchor name spelling (case-sensitive)
- Check timestamp format: `YYYY-MM-DD_HH-MM-SS`
- Verify session exists in database

### Gap between segments

- Check network tab for pre-fetch timing
- Ensure next segment URL is fetched before current ends
- Check canvas overlay is hiding video element during transition

### Position not persisting

- Check localStorage is available (not in private mode)
- Check console for localStorage errors
- Verify session key format matches
