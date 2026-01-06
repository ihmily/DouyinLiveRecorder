# Research: VOD Player Frontend

**Feature**: 002-vod-player-frontend
**Date**: 2026-01-06

## 1. Pipeline Architecture (CSP/DAG Pattern)

### Decision: Python `asyncio` with Task Graph

**Rationale**: Python's native `asyncio` provides sufficient CSP-like patterns through queues and tasks. For this use case, a simple DAG with dependency tracking is more appropriate than full CSP channels.

**Implementation Approach**:
```python
# Pipeline stage interface
class Stage(Protocol):
    async def process(self, input: StageInput) -> StageOutput: ...

# DAG executor
class Pipeline:
    def __init__(self):
        self.stages: dict[str, Stage] = {}
        self.dependencies: dict[str, list[str]] = {}

    def add_stage(self, name: str, stage: Stage, depends_on: list[str] = []):
        self.stages[name] = stage
        self.dependencies[name] = depends_on

    async def execute(self, initial_input: dict) -> dict:
        # Topological sort and execute stages respecting dependencies
        ...
```

**Alternatives Considered**:
- **Prefect/Dagster**: Too heavy for this use case (single-machine execution)
- **Celery**: Adds Redis/RabbitMQ dependency unnecessarily
- **Raw threading**: Less composable than async/await pattern

## 2. TS to MP4 Conversion (Fast Start)

### Decision: FFmpeg with `-movflags faststart`

**Rationale**: FFmpeg is already a dependency for recording. The `faststart` flag relocates the moov atom to file beginning, enabling HTTP Range requests for instant seek.

**Command**:
```bash
ffmpeg -i input.ts -c copy -movflags faststart output.mp4
```

**Key Considerations**:
- `-c copy`: Remux only, no transcoding (fast, lossless)
- `-movflags faststart`: Critical for web seek support
- Error handling: If conversion fails, upload original TS as fallback

**Performance**:
- 30-minute TS file converts in ~10 seconds (disk I/O bound)
- Temporary space needed: ~2x file size during conversion

## 3. TOS Presigned URL Generation

### Decision: TOS SDK `pre_signed_url()` method

**Rationale**: Using the existing TOS SDK maintains consistency with current upload code.

**Implementation**:
```python
from tos import TosClientV2, HttpMethodType

def generate_presigned_url(bucket: str, key: str, expires: int = 3600) -> str:
    client = TosClientV2(ak=..., sk=..., endpoint=..., region=...)
    return client.pre_signed_url(
        HttpMethodType.Http_Method_Get,
        bucket,
        key,
        expires=expires,
        params={'response-content-disposition': 'inline'}
    )
```

**Security Considerations**:
- URL expiration: Default 1 hour, configurable per video duration
- No IP restriction (would break mobile/changing networks)
- `inline` disposition prevents download dialog

## 4. Frontend Video Player

### Decision: Video.js with native MP4

**Rationale**: Video.js is mature, well-documented, and supports native MP4 playback without HLS complexity. Fast Start MP4 enables browser-native Range requests for seek.

**Alternatives Considered**:
- **hls.js + HLS**: Requires server-side segmentation, adds complexity
- **dash.js + DASH**: Same issues as HLS
- **Native `<video>` tag**: Video.js adds controls, quality switching, better UX

**Key Configuration**:
```javascript
videojs(element, {
  controls: true,
  preload: 'metadata',  // Only load moov atom initially
  html5: { nativeVideoTracks: true }
})
```

## 5. Frontend Framework

### Decision: Vue 3 + Vite + Element Plus

**Rationale**: Matches the existing design document recommendation. Vue 3's composition API works well with TypeScript. Element Plus provides tree component for navigation.

**Key Dependencies**:
```json
{
  "vue": "^3.4",
  "video.js": "^8.0",
  "element-plus": "^2.5",
  "axios": "^1.6"
}
```

## 6. API Framework

### Decision: FastAPI (Python)

**Rationale**:
- Same language as existing codebase (Python)
- Native async support
- Automatic OpenAPI documentation
- Pydantic for request/response validation

**Alternatives Considered**:
- **Flask**: Lacks native async, less modern
- **Django**: Too heavy for API-only service
- **Go/Rust**: Different language, harder to share DB models

## 7. Database Schema Changes

### Decision: Add fields to existing RecordingSegment model

**New Fields**:
```python
class RecordingSegment(Base):
    # Existing fields...

    # New VOD fields
    mp4_oss_path: str | None  # Path to converted MP4 in TOS
    mp4_status: str  # pending | processing | completed | failed
    duration: float | None  # Video duration in seconds
```

**Migration Strategy**: Alembic migration with nullable new fields, backfill via conversion worker.

## 8. Segment Watcher Integration

### Decision: Hook conversion into existing SegmentWatcher callback

**Current Flow**:
```
SegmentWatcher detects file → on_segment_created() → RecordingManager → UploadWorker
```

**New Flow**:
```
SegmentWatcher detects file → on_segment_created() → Pipeline.execute([ConvertStage, UploadStage])
```

**Key Change**: Replace direct UploadWorker enqueue with pipeline execution.

## Summary of Decisions

| Topic | Decision | Key Reason |
|-------|----------|------------|
| Pipeline | asyncio DAG | Native Python, simple |
| Conversion | FFmpeg faststart | Already a dependency |
| Presigned URL | TOS SDK | Consistency |
| Video Player | Video.js | Mature, native MP4 |
| Frontend | Vue 3 + Element Plus | Design doc alignment |
| Backend | FastAPI | Python, async, OpenAPI |
| DB Changes | Add 3 fields | Minimal migration |

---

## 9. Bug Fix Analysis: Pipeline Integration Error (2026-01-06)

### Issue Report
```
2026-01-06 01:56:59.408 | ERROR - [序号8 王者荣耀易辞(混的暃)] 处理分段失败:
'RecordingManager' object has no attribute 'process_segment_with_pipeline_sync'
```

### Root Cause

The code at `src/storage/manager.py:294` references a method that doesn't exist:

```python
# Line 294 - CALL (INCORRECT)
thread = threading.Thread(
    target=self.process_segment_with_pipeline_sync,  # ❌ Method doesn't exist
    args=(segment_id, segment_path, save_type.lower(), session_id, anchor_name),
    ...
)
```

The actual method is defined at line 541 with a different name:

```python
# Line 541 - DEFINITION (CORRECT)
def process_segment_sync(  # ✅ Actual method name
    self,
    segment_id: int,
    local_path: str,
    file_format: str,
    session_id: int,
    anchor_name: str,
    platform: str
) -> bool:
```

### Additional Issue: Missing Parameter

The call passes 5 positional arguments, but the method expects 6:

| Position | Passed | Expected |
|----------|--------|----------|
| 1 | `segment_id` | `segment_id` |
| 2 | `segment_path` | `local_path` |
| 3 | `save_type.lower()` | `file_format` |
| 4 | `session_id` | `session_id` |
| 5 | `anchor_name` | `anchor_name` |
| 6 | ❌ **MISSING** | `platform` |

The `platform` parameter is available in the caller's scope but not passed.

### Decision: Fix the call site

**Fix Strategy**: Update the call at line 293-298 to use the correct method name AND pass all required parameters.

**Rationale**:
1. The method name `process_segment_sync` is more concise and follows existing naming patterns
2. Adding the missing `platform` parameter ensures the pipeline has all required context for OSS path construction
3. Minimal change - single file edit at one location

### Resolution

Edit `src/storage/manager.py` lines 293-298:

**Before**:
```python
thread = threading.Thread(
    target=self.process_segment_with_pipeline_sync,
    args=(segment_id, segment_path, save_type.lower(), session_id, anchor_name),
    daemon=True
)
```

**After**:
```python
thread = threading.Thread(
    target=self.process_segment_sync,
    args=(segment_id, segment_path, save_type.lower(), session_id, anchor_name, platform),
    daemon=True
)
```
