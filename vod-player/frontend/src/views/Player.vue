<template>
  <el-container class="player-container">
    <el-header class="player-header">
      <el-button @click="goBack" :icon="ArrowLeft">返回</el-button>
      <h2 v-if="session">{{ session.anchor_name }} - {{ session.live_title || formatDate(session.started_at) }}</h2>
    </el-header>
    <el-main class="player-main">
      <div class="player-layout">
        <div class="video-section">
          <VideoPlayer
            v-if="currentPlayUrl"
            ref="videoPlayer"
            :src="currentPlayUrl.url"
            :title="currentPlayUrl.title"
            :duration="currentPlayUrl.duration"
            @error="handlePlayerError"
            @refresh-requested="refreshCurrentUrl"
            @ended="handleVideoEnded"
          />
          <div v-else-if="loading" class="loading-state">
            <el-icon class="is-loading" :size="48"><Loading /></el-icon>
            <span>加载中...</span>
          </div>
          <div v-else-if="error" class="error-state">
            <el-result icon="error" :title="error">
              <template #extra>
                <el-button type="primary" @click="loadSession">重试</el-button>
              </template>
            </el-result>
          </div>
          <div v-else class="empty-state">
            <el-empty description="选择右侧分段开始播放" />
          </div>
        </div>
        <div class="segment-section">
          <div class="segment-header">
            <h3>分段列表</h3>
            <span v-if="session" class="segment-count">共 {{ session.segments.length }} 个分段</span>
          </div>
          <el-scrollbar class="segment-list">
            <div
              v-for="segment in session?.segments"
              :key="segment.id"
              :class="['segment-item', { active: currentSegmentId === segment.id }]"
              @click="playSegment(segment)"
            >
              <div class="segment-info">
                <span class="segment-index">分段 {{ segment.index + 1 }}</span>
                <span class="segment-duration">{{ formatDuration(segment.duration) }}</span>
              </div>
              <div class="segment-status">
                <el-tag
                  v-if="segment.mp4_status === 'completed'"
                  type="success"
                  size="small"
                >就绪</el-tag>
                <el-tag
                  v-else-if="segment.mp4_status === 'processing'"
                  type="warning"
                  size="small"
                >转换中</el-tag>
                <el-tag
                  v-else-if="segment.mp4_status === 'failed'"
                  type="danger"
                  size="small"
                >失败</el-tag>
                <el-tag
                  v-else
                  type="info"
                  size="small"
                >等待中</el-tag>
              </div>
            </div>
          </el-scrollbar>
        </div>
      </div>
    </el-main>
  </el-container>
</template>

<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { useRouter } from 'vue-router'
import { ArrowLeft, Loading } from '@element-plus/icons-vue'
import VideoPlayer from '@/components/VideoPlayer.vue'
import { getSession, getPlayUrl } from '@/api'
import type { SessionDetail, SegmentInfo, PlaybackUrl } from '@/api'

const props = defineProps<{
  sessionId: string
}>()

const router = useRouter()

const session = ref<SessionDetail | null>(null)
const currentSegmentId = ref<number | null>(null)
const currentPlayUrl = ref<PlaybackUrl | null>(null)
const loading = ref(true)
const error = ref<string | null>(null)
const videoPlayer = ref<InstanceType<typeof VideoPlayer> | null>(null)

const currentSegment = computed(() => {
  if (!session.value || !currentSegmentId.value) return null
  return session.value.segments.find(s => s.id === currentSegmentId.value)
})

function goBack() {
  router.push({ name: 'Home' })
}

function formatDate(dateStr: string): string {
  return new Date(dateStr).toLocaleString('zh-CN')
}

function formatDuration(seconds: number | null): string {
  if (!seconds) return '--:--'
  const minutes = Math.floor(seconds / 60)
  const secs = Math.floor(seconds % 60)
  return `${minutes.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`
}

async function loadSession() {
  loading.value = true
  error.value = null

  try {
    const sessionIdNum = parseInt(props.sessionId, 10)
    if (isNaN(sessionIdNum)) {
      throw new Error('Invalid session ID')
    }

    session.value = await getSession(sessionIdNum)

    // T047: Handle empty sessions with zero segments
    if (!session.value.segments || session.value.segments.length === 0) {
      error.value = '此录像会话没有可用的分段'
      return
    }

    // Auto-play first completed segment
    const firstReady = session.value.segments.find(s => s.mp4_status === 'completed')
    if (firstReady) {
      await playSegment(firstReady)
    } else {
      // No completed segments - show message
      error.value = '没有已完成转换的分段可供播放'
    }
  } catch (e: any) {
    error.value = e.response?.data?.detail || e.message || '加载失败'
  } finally {
    loading.value = false
  }
}

async function playSegment(segment: SegmentInfo) {
  if (segment.mp4_status !== 'completed') {
    return
  }

  currentSegmentId.value = segment.id
  loading.value = true
  error.value = null

  try {
    currentPlayUrl.value = await getPlayUrl(segment.id)
  } catch (e: any) {
    error.value = e.response?.data?.detail || e.message || '获取播放URL失败'
    currentPlayUrl.value = null
  } finally {
    loading.value = false
  }
}

async function refreshCurrentUrl() {
  if (currentSegment.value) {
    await playSegment(currentSegment.value)
  }
}

function handlePlayerError(errorMsg: string) {
  console.error('Player error:', errorMsg)
}

function handleVideoEnded() {
  // Auto-play next segment
  if (!session.value || !currentSegmentId.value) return

  const currentIndex = session.value.segments.findIndex(s => s.id === currentSegmentId.value)
  if (currentIndex < 0) return

  // Find next completed segment
  for (let i = currentIndex + 1; i < session.value.segments.length; i++) {
    if (session.value.segments[i].mp4_status === 'completed') {
      playSegment(session.value.segments[i])
      break
    }
  }
}

onMounted(() => {
  loadSession()
})
</script>

<style scoped>
.player-container {
  height: 100vh;
  background-color: #1a1a1a;
}

.player-header {
  display: flex;
  align-items: center;
  gap: 16px;
  background-color: #2d2d2d;
  border-bottom: 1px solid #404040;
  padding: 0 16px;
}

.player-header h2 {
  margin: 0;
  font-size: 16px;
  color: #fff;
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.player-main {
  padding: 0;
  overflow: hidden;
}

.player-layout {
  display: flex;
  height: 100%;
}

.video-section {
  flex: 1;
  display: flex;
  justify-content: center;
  align-items: center;
  background-color: #000;
  min-width: 0;
}

.segment-section {
  width: 280px;
  background-color: #2d2d2d;
  border-left: 1px solid #404040;
  display: flex;
  flex-direction: column;
}

.segment-header {
  padding: 16px;
  border-bottom: 1px solid #404040;
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.segment-header h3 {
  margin: 0;
  font-size: 14px;
  color: #fff;
}

.segment-count {
  font-size: 12px;
  color: #909399;
}

.segment-list {
  flex: 1;
}

.segment-item {
  padding: 12px 16px;
  border-bottom: 1px solid #404040;
  cursor: pointer;
  transition: background-color 0.2s;
}

.segment-item:hover {
  background-color: #3a3a3a;
}

.segment-item.active {
  background-color: #409eff33;
  border-left: 3px solid #409eff;
}

.segment-info {
  display: flex;
  justify-content: space-between;
  margin-bottom: 8px;
}

.segment-index {
  color: #fff;
  font-size: 14px;
}

.segment-duration {
  color: #909399;
  font-size: 12px;
}

.segment-status {
  display: flex;
  justify-content: flex-end;
}

.loading-state,
.error-state,
.empty-state {
  color: #fff;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
}
</style>
