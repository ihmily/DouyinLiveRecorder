<template>
  <div class="aggregated-player-container">
    <!-- Video wrapper with canvas overlay for seamless transitions -->
    <div class="video-wrapper">
      <video
        ref="videoElement"
        class="video-js vjs-big-play-centered"
      ></video>
      <canvas ref="transitionCanvas" class="transition-canvas"></canvas>
    </div>

    <!-- Loading overlay -->
    <div v-if="loading" class="loading-overlay">
      <el-icon class="is-loading" :size="48"><Loading /></el-icon>
      <span>{{ loadingMessage }}</span>
    </div>

    <!-- Error overlay -->
    <div v-if="error" class="error-overlay">
      <el-result icon="error" :title="error">
        <template #extra>
          <el-button type="primary" @click="retryPlayback">重试</el-button>
        </template>
      </el-result>
    </div>

    <!-- Unified progress bar -->
    <div class="unified-controls" v-if="timeline && !error">
      <div class="progress-container" @click="handleProgressClick" ref="progressBar">
        <div class="progress-background">
          <!-- Segment markers -->
          <div
            v-for="segment in timeline.segments"
            :key="segment.segmentId"
            class="segment-marker"
            :style="{ left: `${(segment.startOffset / timeline.totalDuration) * 100}%` }"
          ></div>
          <!-- Progress fill -->
          <div class="progress-fill" :style="{ width: `${progressPercent}%` }"></div>
          <!-- Playhead -->
          <div class="playhead" :style="{ left: `${progressPercent}%` }"></div>
        </div>
      </div>
      <div class="time-display">
        <span class="current-time">{{ formatDuration(unifiedPosition) }}</span>
        <span class="time-separator">/</span>
        <span class="total-duration">{{ formatDuration(timeline.totalDuration) }}</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount, watch } from 'vue'
import { Loading } from '@element-plus/icons-vue'
import videojs from 'video.js'
import type Player from 'video.js/dist/types/player'
import 'video.js/dist/video-js.css'
import { getAggregatedSession, getPlayUrl, batchGetPlayUrls } from '@/api'
import type { AggregatedSession, PlaybackUrl } from '@/api'
import {
  buildTimeline,
  findSegmentForPosition,
  getNextSegment,
  getUnifiedPosition,
  formatDuration,
} from '@/services/timeline'
import type { SegmentTimeline, TimelineSegment } from '@/services/timeline'
import {
  loadPosition,
  clearPosition,
  createThrottledSaver,
  cleanupExpiredPositions,
} from '@/stores/playback'

const props = defineProps<{
  sessionId: number
}>()

const emit = defineEmits<{
  (e: 'error', error: string): void
  (e: 'session-loaded', session: AggregatedSession): void
  (e: 'playback-ended'): void
}>()

// DOM refs
const videoElement = ref<HTMLVideoElement | null>(null)
const transitionCanvas = ref<HTMLCanvasElement | null>(null)
const progressBar = ref<HTMLDivElement | null>(null)

// State
const player = ref<Player | null>(null)
const aggregatedSession = ref<AggregatedSession | null>(null)
const timeline = ref<SegmentTimeline | null>(null)
const currentSegment = ref<TimelineSegment | null>(null)
const currentPlayUrl = ref<PlaybackUrl | null>(null)
const loading = ref(true)
const loadingMessage = ref('加载中...')
const error = ref<string | null>(null)

// Prefetch state
const prefetchedUrls = ref<Map<number, PlaybackUrl>>(new Map())
const isPrefetching = ref(false)

// Playback position persistence
let throttledSaver: ((position: number, segmentId: number) => void) | null = null
let hasSeekedToSavedPosition = false

// Playback position tracking
const localPosition = ref(0) // Position within current segment
const unifiedPosition = computed(() => {
  if (!currentSegment.value) return 0
  return getUnifiedPosition(timeline.value!, currentSegment.value.segmentId, localPosition.value)
})

const progressPercent = computed(() => {
  if (!timeline.value || timeline.value.totalDuration === 0) return 0
  return (unifiedPosition.value / timeline.value.totalDuration) * 100
})

// Initialize Video.js player
function initPlayer() {
  if (!videoElement.value) return

  player.value = videojs(videoElement.value, {
    controls: true,
    autoplay: false,
    preload: 'metadata',
    fluid: false,
    fill: true,
    responsive: true,
    playbackRates: [0.5, 1, 1.5, 2],
    html5: {
      nativeVideoTracks: true,
      nativeAudioTracks: true,
      nativeTextTracks: true,
    },
    controlBar: {
      children: [
        'playToggle',
        'volumePanel',
        'playbackRateMenuButton',
        'fullscreenToggle',
      ],
    },
  })

  // Event listeners
  player.value.on('loadedmetadata', handleLoadedMetadata)
  player.value.on('timeupdate', handleTimeUpdate)
  player.value.on('ended', handleSegmentEnded)
  player.value.on('error', handlePlayerError)
  player.value.on('waiting', () => {
    loading.value = true
    loadingMessage.value = '缓冲中...'
  })
  player.value.on('playing', handlePlaying)
}

function handleLoadedMetadata() {
  loading.value = false
  error.value = null
}

function handleTimeUpdate() {
  if (!player.value || !currentSegment.value) return

  localPosition.value = player.value.currentTime() || 0

  // T015: Pre-fetch next segment URL when 5 seconds from end
  const duration = player.value.duration() || 0
  const timeRemaining = duration - localPosition.value

  if (timeRemaining <= 5 && timeRemaining > 0 && !isPrefetching.value) {
    prefetchNextSegment()
  }

  // T030: Save position (throttled)
  if (throttledSaver && currentSegment.value) {
    throttledSaver(unifiedPosition.value, currentSegment.value.segmentId)
  }
}

// T016: Handle segment end - auto advance to next
async function handleSegmentEnded() {
  if (!timeline.value || !currentSegment.value) {
    // T032: Clear position when playback completes
    if (aggregatedSession.value) {
      clearPosition(aggregatedSession.value.anchor_name, aggregatedSession.value.session_timestamp)
    }
    emit('playback-ended')
    return
  }

  const nextSeg = getNextSegment(timeline.value, currentSegment.value.segmentId)

  if (!nextSeg) {
    // No more segments - playback complete
    // T032: Clear position when playback completes
    if (aggregatedSession.value) {
      clearPosition(aggregatedSession.value.anchor_name, aggregatedSession.value.session_timestamp)
    }
    emit('playback-ended')
    return
  }

  // Show canvas overlay with last frame for seamless transition
  captureFrameToCanvas()

  // Switch to next segment
  await playSegment(nextSeg.segmentId, 0, true)
}

function handlePlaying() {
  loading.value = false
  // Hide canvas overlay when new segment starts playing
  if (transitionCanvas.value) {
    transitionCanvas.value.style.display = 'none'
  }
}

function handlePlayerError() {
  const err = player.value?.error()
  loading.value = false
  if (err) {
    if (err.code === 4) {
      error.value = 'URL已过期或无法访问，请刷新'
    } else if (err.code === 2) {
      error.value = '网络错误，请检查连接后重试'
    } else {
      error.value = `播放错误: ${err.message || '未知错误'}`
    }
    emit('error', error.value)
  }
}

// Canvas overlay for seamless transitions
function captureFrameToCanvas() {
  if (!transitionCanvas.value || !videoElement.value) return

  const video = videoElement.value
  const canvas = transitionCanvas.value
  const ctx = canvas.getContext('2d')
  if (!ctx) return

  // Match canvas size to video
  canvas.width = video.videoWidth || video.clientWidth
  canvas.height = video.videoHeight || video.clientHeight

  // Draw current frame
  ctx.drawImage(video, 0, 0, canvas.width, canvas.height)
  canvas.style.display = 'block'
}

// T015: Pre-fetch next segment URL
async function prefetchNextSegment() {
  if (!timeline.value || !currentSegment.value || isPrefetching.value) return

  const nextSeg = getNextSegment(timeline.value, currentSegment.value.segmentId)
  if (!nextSeg || prefetchedUrls.value.has(nextSeg.segmentId)) return

  isPrefetching.value = true

  try {
    // Use batch API for efficiency (could pre-fetch multiple segments)
    const result = await batchGetPlayUrls([nextSeg.segmentId])
    const url = result.urls[String(nextSeg.segmentId)]
    if (url) {
      prefetchedUrls.value.set(nextSeg.segmentId, url)
    }
  } catch (e) {
    console.warn('Failed to prefetch next segment:', e)
  } finally {
    isPrefetching.value = false
  }
}

// Play a specific segment
async function playSegment(segmentId: number, startTime = 0, autoplay = false) {
  if (!timeline.value) return

  loading.value = true
  loadingMessage.value = '加载分段...'
  error.value = null

  // Find segment in timeline
  const segment = timeline.value.segments.find(s => s.segmentId === segmentId)
  if (!segment) {
    error.value = '分段不存在'
    loading.value = false
    return
  }

  currentSegment.value = segment

  try {
    // Check if URL is prefetched
    let playUrl = prefetchedUrls.value.get(segmentId)

    if (!playUrl) {
      playUrl = await getPlayUrl(segmentId)
    }

    currentPlayUrl.value = playUrl

    if (player.value) {
      player.value.src({
        src: playUrl.url,
        type: 'video/mp4',
      })

      // Set start time after metadata loads
      player.value.one('loadedmetadata', () => {
        if (startTime > 0 && player.value) {
          player.value.currentTime(startTime)
        }
        if (autoplay && player.value) {
          player.value.play()
        }
      })
    }
  } catch (e: any) {
    error.value = e.response?.data?.detail || e.message || '获取播放URL失败'
    loading.value = false
  }
}

// T017: Handle progress bar click for seeking (unified timeline)
function handleProgressClick(event: MouseEvent) {
  if (!progressBar.value || !timeline.value) return

  const rect = progressBar.value.getBoundingClientRect()
  const clickX = event.clientX - rect.left
  const percent = clickX / rect.width
  const targetPosition = percent * timeline.value.totalDuration

  seekToPosition(targetPosition)
}

// Seek to a unified position
async function seekToPosition(position: number) {
  if (!timeline.value) return

  const result = findSegmentForPosition(timeline.value, position)
  if (!result) return

  const { segment, localPosition: seekLocalPosition } = result

  // If same segment, just seek within it
  if (currentSegment.value?.segmentId === segment.segmentId) {
    if (player.value) {
      player.value.currentTime(seekLocalPosition)
    }
  } else {
    // Different segment - load it and seek
    await playSegment(segment.segmentId, seekLocalPosition, true)
  }
}

// Load session and initialize
async function loadSession() {
  loading.value = true
  loadingMessage.value = '加载会话...'
  error.value = null
  hasSeekedToSavedPosition = false

  try {
    aggregatedSession.value = await getAggregatedSession(props.sessionId)

    if (aggregatedSession.value.segments.length === 0) {
      error.value = '没有已完成转换的分段可供播放'
      loading.value = false
      return
    }

    // Build timeline from aggregated session
    timeline.value = buildTimeline(aggregatedSession.value)

    // T029/T033: Create throttled position saver
    throttledSaver = createThrottledSaver(
      aggregatedSession.value.anchor_name,
      aggregatedSession.value.session_timestamp
    )

    emit('session-loaded', aggregatedSession.value)

    // T031/T033: Load saved position if available
    const savedState = loadPosition(
      aggregatedSession.value.anchor_name,
      aggregatedSession.value.session_timestamp,
      timeline.value.totalDuration // T034: Validates position doesn't exceed duration
    )

    if (savedState && savedState.position > 0) {
      // Resume from saved position
      hasSeekedToSavedPosition = true
      await seekToPosition(savedState.position)
    } else {
      // Auto-play first segment
      const firstSegment = timeline.value.segments[0]
      if (firstSegment) {
        await playSegment(firstSegment.segmentId, 0, false)
      }
    }

    // Cleanup expired positions occasionally
    cleanupExpiredPositions()
  } catch (e: any) {
    error.value = e.response?.data?.detail || e.message || '加载失败'
    loading.value = false
  }
}

function retryPlayback() {
  loadSession()
}

// Watch for sessionId changes
watch(() => props.sessionId, () => {
  prefetchedUrls.value.clear()
  loadSession()
})

onMounted(() => {
  initPlayer()
  loadSession()
})

onBeforeUnmount(() => {
  if (player.value) {
    player.value.dispose()
    player.value = null
  }
})

// Expose methods for parent component
defineExpose({
  play: () => player.value?.play(),
  pause: () => player.value?.pause(),
  seekToPosition,
  getCurrentPosition: () => unifiedPosition.value,
  getTimeline: () => timeline.value,
})
</script>

<style scoped>
.aggregated-player-container {
  position: relative;
  width: 100%;
  height: 100%;
  background-color: #000;
  display: flex;
  flex-direction: column;
}

.video-wrapper {
  flex: 1;
  position: relative;
  min-height: 0;
}

.transition-canvas {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  object-fit: contain;
  display: none;
  z-index: 5;
  pointer-events: none;
}

.loading-overlay,
.error-overlay {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
  background-color: rgba(0, 0, 0, 0.8);
  color: #fff;
  z-index: 10;
}

.loading-overlay {
  gap: 12px;
}

/* Unified progress bar */
.unified-controls {
  height: 48px;
  background-color: #2d2d2d;
  display: flex;
  align-items: center;
  padding: 0 16px;
  gap: 16px;
}

.progress-container {
  flex: 1;
  height: 24px;
  display: flex;
  align-items: center;
  cursor: pointer;
}

.progress-background {
  position: relative;
  width: 100%;
  height: 6px;
  background-color: #404040;
  border-radius: 3px;
}

.segment-marker {
  position: absolute;
  top: -2px;
  width: 2px;
  height: 10px;
  background-color: #666;
  transform: translateX(-1px);
  pointer-events: none;
}

.segment-marker:first-child {
  display: none;
}

.progress-fill {
  position: absolute;
  top: 0;
  left: 0;
  height: 100%;
  background-color: #409eff;
  border-radius: 3px 0 0 3px;
  transition: width 0.1s linear;
}

.playhead {
  position: absolute;
  top: 50%;
  width: 12px;
  height: 12px;
  background-color: #409eff;
  border-radius: 50%;
  transform: translate(-50%, -50%);
  transition: left 0.1s linear;
}

.progress-container:hover .playhead {
  transform: translate(-50%, -50%) scale(1.2);
}

.time-display {
  font-size: 14px;
  color: #fff;
  font-family: monospace;
  white-space: nowrap;
}

.time-separator {
  margin: 0 4px;
  color: #909399;
}

.total-duration {
  color: #909399;
}

:deep(.video-js) {
  width: 100%;
  height: 100%;
}

:deep(.video-js video) {
  object-fit: contain;
}

:deep(.vjs-big-play-button) {
  font-size: 3em;
}

/* Hide Video.js default progress bar since we use custom unified one */
:deep(.vjs-progress-control) {
  display: none !important;
}

:deep(.vjs-current-time),
:deep(.vjs-time-divider),
:deep(.vjs-duration) {
  display: none !important;
}
</style>
