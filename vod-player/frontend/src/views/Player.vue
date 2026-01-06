<template>
  <el-container class="player-container">
    <el-header class="player-header">
      <el-button @click="goBack" :icon="ArrowLeft">返回</el-button>
      <h2 v-if="aggregatedSession">{{ aggregatedSession.anchor_name }} - {{ aggregatedSession.live_title || formatDate(aggregatedSession.started_at) }}</h2>
    </el-header>
    <el-main class="player-main">
      <div class="player-layout">
        <div class="video-section">
          <AggregatedPlayer
            v-if="sessionIdNum"
            ref="aggregatedPlayer"
            :session-id="sessionIdNum"
            @session-loaded="handleSessionLoaded"
            @error="handlePlayerError"
            @playback-ended="handlePlaybackEnded"
          />
          <div v-else-if="loading" class="loading-state">
            <el-icon class="is-loading" :size="48"><Loading /></el-icon>
            <span>加载中...</span>
          </div>
          <div v-else-if="error" class="error-state">
            <el-result icon="error" :title="error">
              <template #extra>
                <el-button type="primary" @click="goBack">返回首页</el-button>
              </template>
            </el-result>
          </div>
        </div>
        <div class="segment-section">
          <div class="segment-header">
            <h3>分段列表</h3>
            <span v-if="aggregatedSession" class="segment-count">
              {{ aggregatedSession.converted_segment_count }} / {{ aggregatedSession.total_segment_count }} 可播放
            </span>
          </div>
          <el-scrollbar class="segment-list">
            <div
              v-for="segment in aggregatedSession?.segments"
              :key="segment.segment_id"
              :class="['segment-item', 'completed']"
              @click="jumpToSegment(segment)"
            >
              <div class="segment-info">
                <span class="segment-index">分段 {{ segment.segment_index + 1 }}</span>
                <span class="segment-duration">{{ formatDurationDisplay(segment.duration) }}</span>
              </div>
              <div class="segment-time">
                <span class="segment-offset">{{ formatDurationDisplay(segment.start_offset) }}</span>
              </div>
            </div>
          </el-scrollbar>
        </div>
      </div>
    </el-main>
  </el-container>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { ArrowLeft, Loading } from '@element-plus/icons-vue'
import AggregatedPlayer from '@/components/AggregatedPlayer.vue'
import { getSessionByPath } from '@/api'
import type { AggregatedSession, AggregatedSegment } from '@/api'
import { formatDuration } from '@/services/timeline'

// T036: Support both legacy and new URL formats
const props = defineProps<{
  sessionId?: string           // Legacy format: /player/:sessionId
  anchorName?: string          // New format: /:anchorName/:sessionTimestamp
  sessionTimestamp?: string    // New format: /:anchorName/:sessionTimestamp
}>()

const router = useRouter()
const route = useRoute()

const aggregatedSession = ref<AggregatedSession | null>(null)
const aggregatedPlayer = ref<InstanceType<typeof AggregatedPlayer> | null>(null)
const resolvedSessionId = ref<number | null>(null)
const loading = ref(false)
const error = ref<string | null>(null)

// T036: Compute session ID from either route format
const sessionIdNum = computed(() => resolvedSessionId.value)

// T036: Resolve session ID from URL params
async function resolveSessionId() {
  // Legacy format: /player/:sessionId
  if (props.sessionId) {
    const num = parseInt(props.sessionId, 10)
    if (!isNaN(num)) {
      resolvedSessionId.value = num
      return
    }
  }

  // New format: /:anchorName/:sessionTimestamp
  if (props.anchorName && props.sessionTimestamp) {
    loading.value = true
    error.value = null
    try {
      // T037: Use getSessionByPath to lookup session
      const session = await getSessionByPath(props.anchorName, props.sessionTimestamp)
      resolvedSessionId.value = session.session_id
    } catch (e: any) {
      error.value = e.response?.data?.detail || e.message || '找不到指定的录像'
      resolvedSessionId.value = null
    } finally {
      loading.value = false
    }
    return
  }

  // No valid params
  error.value = '无效的URL参数'
  resolvedSessionId.value = null
}

// Watch for route changes
watch(
  () => [props.sessionId, props.anchorName, props.sessionTimestamp],
  () => resolveSessionId(),
  { immediate: false }
)

onMounted(() => {
  resolveSessionId()
})

function goBack() {
  router.push({ name: 'Home' })
}

function formatDate(dateStr: string): string {
  return new Date(dateStr).toLocaleString('zh-CN')
}

function formatDurationDisplay(seconds: number | null): string {
  return formatDuration(seconds)
}

function handleSessionLoaded(session: AggregatedSession) {
  aggregatedSession.value = session
}

function handlePlayerError(errorMsg: string) {
  console.error('Player error:', errorMsg)
}

function handlePlaybackEnded() {
  console.log('Playback ended')
}

function jumpToSegment(segment: AggregatedSegment) {
  if (aggregatedPlayer.value) {
    aggregatedPlayer.value.seekToPosition(segment.start_offset)
  }
}
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

.segment-item.completed {
  border-left: 3px solid #67c23a;
}

.segment-info {
  display: flex;
  justify-content: space-between;
  margin-bottom: 4px;
}

.segment-index {
  color: #fff;
  font-size: 14px;
}

.segment-duration {
  color: #67c23a;
  font-size: 12px;
}

.segment-time {
  display: flex;
  justify-content: flex-end;
}

.segment-offset {
  font-size: 12px;
  color: #909399;
  font-family: monospace;
}

.loading-state,
.error-state {
  flex: 1;
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
  color: #fff;
  gap: 12px;
}
</style>
