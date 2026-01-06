# Quickstart: OSS Storage Cleanup

**Feature**: 005-oss-cleanup
**Date**: 2026-01-06

## Overview

This feature adds automatic OSS storage cleanup that triggers after each upload. When storage exceeds a configurable threshold, the oldest completed recording sessions are deleted to free space.

## Configuration

### Enable Cleanup

Add these settings to `config/config.ini` under the `[OSS设置]` section:

```ini
[OSS设置]
# ... existing settings ...
启用OSS存储清理(是/否) = 是
OSS存储清理阈值(GB) = 50
```

| Setting | Description | Default |
|---------|-------------|---------|
| `启用OSS存储清理(是/否)` | Enable/disable automatic cleanup | 否 (disabled) |
| `OSS存储清理阈值(GB)` | Threshold in GB before cleanup triggers | 0 |

**Note**: Cleanup is disabled by default. Set threshold to 0 to disable cleanup even if enabled flag is "是".

## Behavior

### Trigger Point

Cleanup check is triggered **after each successful segment upload**.

### Cleanup Logic

1. Acquire cleanup lock (blocks if another cleanup is running)
2. Query database for total OSS storage usage
3. If below threshold → exit (no cleanup)
4. While over threshold:
   - Select oldest completed session (by `started_at`)
   - Delete all its segment files from OSS (both TS and MP4)
   - Mark segments as `oss_deleted = True` in database
5. Release lock

### Protected Content

The following are **never deleted** by automatic cleanup:
- **Active sessions**: Recording in progress (`ended_at` is NULL)
- **Failed uploads**: Segments that haven't successfully uploaded to OSS
- **Already deleted**: Segments with `oss_deleted = True`

## Database Migration

A migration is required to add the `oss_deleted` column:

```bash
python migrations/002_add_oss_deleted.py
```

Or manually:

```sql
ALTER TABLE recording_segments ADD COLUMN oss_deleted BOOLEAN DEFAULT FALSE;
```

## Verification

### Check Storage Stats

Use the `RecordingManager` to check current storage:

```python
from src.storage import RecordingManager

manager = RecordingManager.from_config('config/config.ini', 'config/tos_credentials.ini')
if manager.cleanup:
    stats = manager.cleanup.get_storage_stats()
    print(f"Current storage: {stats.total_bytes / 1024**3:.2f} GB")
    print(f"Threshold: {stats.threshold_bytes / 1024**3:.2f} GB")
    print(f"Over threshold: {stats.over_threshold}")
```

### Check Logs

Cleanup operations are logged with `loguru`:

```
INFO  | OSS cleanup triggered: current=55.2GB, threshold=50.0GB
INFO  | Deleting session 42 (主播名, started 2026-01-01 10:00:00)
INFO  | Deleted segment 123: 抖音直播/2026-01-01/主播名/主播名_xxx.ts
INFO  | OSS cleanup complete: 3 sessions, 8.5GB freed in 12.3s
```

## Testing

### Test OSS Delete API

Before enabling cleanup, verify that the OSS delete API works correctly:

```bash
python scripts/test_tos_delete.py
```

This test script:
1. Uploads a small test file to `_test_delete/` folder
2. Immediately deletes the test file
3. Reports success or failure

**Expected Output**:
```
INFO  | Step 1: Uploading test file to _test_delete/20260106_120000_test.txt
INFO  | Upload successful
INFO  | Step 2: Deleting test file _test_delete/20260106_120000_test.txt
INFO  | Delete successful
INFO  | ✓ OSS delete API test passed!
```

If this test fails, check:
- TOS credentials in `config/tos_credentials.ini`
- Bucket permissions allow DELETE operations
- Network connectivity to TOS endpoint

### Manual Cleanup Test

1. Set a low threshold (e.g., 100MB)
2. Upload several recordings
3. Verify oldest sessions are deleted when threshold exceeded
4. Check logs for cleanup activity

### Verify Concurrent Safety

1. Run multiple upload threads simultaneously
2. Observe logs - cleanup should only run once at a time
3. Other upload threads should block and wait

## Troubleshooting

### Cleanup Not Triggering

1. Check `启用OSS存储清理(是/否)` is set to `是`
2. Check `OSS存储清理阈值(GB)` is greater than 0
3. Verify storage actually exceeds threshold
4. Check logs for errors

### Files Not Being Deleted from OSS

1. Check TOS credentials are valid
2. Check network connectivity to OSS
3. Review error logs for specific failures

### Database Shows Wrong Storage

Storage is calculated from database `file_size` field. If this doesn't match actual OSS usage:
1. Ensure uploads are completing successfully
2. Check `file_size` is being set correctly on segment creation
3. Future: implement periodic reconciliation feature
