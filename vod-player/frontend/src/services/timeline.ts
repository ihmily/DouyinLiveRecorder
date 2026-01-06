/**
 * Timeline service for unified multi-segment playback.
 * Part of feature: 004-video-segment-aggregation
 */

// Types matching backend AggregatedSession schema
export interface AggregatedSegment {
  segment_id: number
  segment_index: number
  duration: number
  start_offset: number
  end_offset: number
}

export interface AggregatedSession {
  session_id: number
  anchor_name: string
  platform: string
  live_title: string | null
  session_timestamp: string
  started_at: string
  ended_at: string | null
  total_duration: number
  converted_segment_count: number
  total_segment_count: number
  segments: AggregatedSegment[]
}

// Frontend timeline interface
export interface SegmentTimeline {
  sessionId: number
  anchorName: string
  sessionTimestamp: string
  totalDuration: number
  segments: TimelineSegment[]
}

export interface TimelineSegment {
  segmentId: number
  segmentIndex: number
  duration: number
  startOffset: number
  endOffset: number
}

/**
 * Build a frontend timeline from backend AggregatedSession response.
 */
export function buildTimeline(session: AggregatedSession): SegmentTimeline {
  return {
    sessionId: session.session_id,
    anchorName: session.anchor_name,
    sessionTimestamp: session.session_timestamp,
    totalDuration: session.total_duration,
    segments: session.segments.map(seg => ({
      segmentId: seg.segment_id,
      segmentIndex: seg.segment_index,
      duration: seg.duration,
      startOffset: seg.start_offset,
      endOffset: seg.end_offset,
    })),
  }
}

/**
 * Find which segment contains a given position in the unified timeline.
 * Returns the segment and the local position within that segment.
 */
export function findSegmentForPosition(
  timeline: SegmentTimeline,
  position: number
): { segment: TimelineSegment; localPosition: number } | null {
  if (position < 0 || position > timeline.totalDuration) {
    return null
  }

  for (const segment of timeline.segments) {
    if (position >= segment.startOffset && position < segment.endOffset) {
      const localPosition = position - segment.startOffset
      return { segment, localPosition }
    }
  }

  // If we're exactly at the end, return the last segment at its end
  if (timeline.segments.length > 0 && position === timeline.totalDuration) {
    const lastSegment = timeline.segments[timeline.segments.length - 1]
    return { segment: lastSegment, localPosition: lastSegment.duration }
  }

  return null
}

/**
 * Get the next segment after the given segment ID.
 * Returns null if there's no next segment.
 */
export function getNextSegment(
  timeline: SegmentTimeline,
  currentSegmentId: number
): TimelineSegment | null {
  const currentIndex = timeline.segments.findIndex(s => s.segmentId === currentSegmentId)
  if (currentIndex < 0 || currentIndex >= timeline.segments.length - 1) {
    return null
  }
  return timeline.segments[currentIndex + 1]
}

/**
 * Get the previous segment before the given segment ID.
 * Returns null if there's no previous segment.
 */
export function getPreviousSegment(
  timeline: SegmentTimeline,
  currentSegmentId: number
): TimelineSegment | null {
  const currentIndex = timeline.segments.findIndex(s => s.segmentId === currentSegmentId)
  if (currentIndex <= 0) {
    return null
  }
  return timeline.segments[currentIndex - 1]
}

/**
 * Calculate the unified position from segment + local position.
 */
export function getUnifiedPosition(
  timeline: SegmentTimeline,
  segmentId: number,
  localPosition: number
): number {
  const segment = timeline.segments.find(s => s.segmentId === segmentId)
  if (!segment) {
    return 0
  }
  return segment.startOffset + Math.min(localPosition, segment.duration)
}

/**
 * Format duration as HH:MM:SS or MM:SS depending on length.
 */
export function formatDuration(seconds: number | null | undefined): string {
  if (seconds == null || seconds < 0) return '--:--'

  const totalSeconds = Math.floor(seconds)
  const hours = Math.floor(totalSeconds / 3600)
  const minutes = Math.floor((totalSeconds % 3600) / 60)
  const secs = totalSeconds % 60

  if (hours > 0) {
    return `${hours}:${minutes.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`
  }
  return `${minutes.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`
}

/**
 * Format duration as human-readable string (e.g., "1小时23分钟")
 */
export function formatDurationHuman(seconds: number | null | undefined): string {
  if (seconds == null || seconds < 0) return '--'

  const totalSeconds = Math.floor(seconds)
  const hours = Math.floor(totalSeconds / 3600)
  const minutes = Math.floor((totalSeconds % 3600) / 60)

  if (hours > 0) {
    return minutes > 0 ? `${hours}小时${minutes}分钟` : `${hours}小时`
  }
  return `${minutes}分钟`
}
