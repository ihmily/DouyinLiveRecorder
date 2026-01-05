<template>
  <div class="video-player-container">
    <div ref="videoContainer" class="video-wrapper">
      <video
        ref="videoElement"
        class="video-js vjs-big-play-centered vjs-fluid"
      ></video>
    </div>
    <div v-if="error" class="error-overlay">
      <el-result icon="error" :title="error">
        <template #extra>
          <el-button type="primary" @click="handleRefresh">刷新URL</el-button>
        </template>
      </el-result>
    </div>
    <div v-if="loading" class="loading-overlay">
      <el-icon class="is-loading" :size="48"><Loading /></el-icon>
      <span>加载中...</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount, watch } from 'vue'
import { Loading } from '@element-plus/icons-vue'
import videojs from 'video.js'
import type Player from 'video.js/dist/types/player'
import 'video.js/dist/video-js.css'

const props = defineProps<{
  src: string
  title?: string
  duration?: number | null
}>()

const emit = defineEmits<{
  (e: 'error', error: string): void
  (e: 'refresh-requested'): void
  (e: 'ended'): void
}>()

const videoElement = ref<HTMLVideoElement | null>(null)
const videoContainer = ref<HTMLDivElement | null>(null)
const player = ref<Player | null>(null)
const error = ref<string | null>(null)
const loading = ref(true)

function initPlayer() {
  if (!videoElement.value) return

  player.value = videojs(videoElement.value, {
    controls: true,
    autoplay: false,
    preload: 'metadata',
    fluid: true,
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
        'currentTimeDisplay',
        'timeDivider',
        'durationDisplay',
        'progressControl',
        'playbackRateMenuButton',
        'fullscreenToggle',
      ],
    },
  })

  // Event listeners
  player.value.on('loadedmetadata', () => {
    loading.value = false
    error.value = null
  })

  player.value.on('error', () => {
    const err = player.value?.error()
    loading.value = false
    if (err) {
      // T044: Handle TOS unavailability and URL expiration
      if (err.code === 4) {
        // Media error - could be 403 (expired), 404 (not found), or network error
        error.value = 'URL已过期或无法访问，请刷新'
      } else if (err.code === 2) {
        // Network error - TOS might be unavailable
        error.value = '网络错误，请检查连接后重试'
      } else {
        error.value = `播放错误: ${err.message || '未知错误'}`
      }
      emit('error', error.value)
    }
  })

  // T045: Buffering indicator
  player.value.on('waiting', () => {
    loading.value = true
  })

  player.value.on('playing', () => {
    loading.value = false
  })

  // T046: Handle seek beyond duration - Video.js handles this natively by clamping

  player.value.on('ended', () => {
    emit('ended')
  })

  // Set initial source
  if (props.src) {
    loadSource(props.src)
  }
}

function loadSource(src: string) {
  if (!player.value) return

  loading.value = true
  error.value = null

  player.value.src({
    src,
    type: 'video/mp4',
  })
}

function handleRefresh() {
  emit('refresh-requested')
}

// T025: Seek functionality is built into Video.js progress bar
// The player handles seek via HTTP Range requests on Fast Start MP4

// Watch for source changes
watch(() => props.src, (newSrc) => {
  if (newSrc && player.value) {
    loadSource(newSrc)
  }
})

onMounted(() => {
  initPlayer()
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
  seek: (time: number) => {
    if (player.value) {
      player.value.currentTime(time)
    }
  },
})
</script>

<style scoped>
.video-player-container {
  position: relative;
  width: 100%;
  background-color: #000;
}

.video-wrapper {
  width: 100%;
}

.error-overlay,
.loading-overlay {
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

:deep(.video-js) {
  width: 100%;
}

:deep(.vjs-big-play-button) {
  font-size: 3em;
}
</style>
