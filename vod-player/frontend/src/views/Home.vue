<template>
  <el-container class="home-container">
    <el-aside width="300px" class="sidebar">
      <div class="sidebar-header">
        <h2>录像库</h2>
      </div>
      <SessionTree @session-selected="handleSessionSelected" />
    </el-aside>
    <el-main class="main-content">
      <div v-if="!selectedSession" class="welcome">
        <el-empty description="选择左侧列表中的录像开始播放">
          <template #image>
            <el-icon :size="80" color="#409eff"><VideoPlay /></el-icon>
          </template>
        </el-empty>
      </div>
      <div v-else class="session-preview">
        <el-card>
          <template #header>
            <div class="card-header">
              <span>录像详情</span>
              <el-button type="primary" @click="goToPlayer">
                <el-icon><VideoPlay /></el-icon>
                播放
              </el-button>
            </div>
          </template>
          <el-descriptions :column="2" border>
            <el-descriptions-item label="开始时间">
              {{ formatDateTime(selectedSession.started_at) }}
            </el-descriptions-item>
            <el-descriptions-item label="结束时间">
              {{ selectedSession.ended_at ? formatDateTime(selectedSession.ended_at) : '进行中' }}
            </el-descriptions-item>
            <el-descriptions-item label="分段数">
              {{ selectedSession.segment_count }}
            </el-descriptions-item>
            <el-descriptions-item label="总时长">
              {{ formatDuration(selectedSession.duration) }}
            </el-descriptions-item>
            <el-descriptions-item label="文件大小">
              {{ formatSize(selectedSession.total_size) }}
            </el-descriptions-item>
          </el-descriptions>
        </el-card>
      </div>
    </el-main>
  </el-container>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { VideoPlay } from '@element-plus/icons-vue'
import SessionTree from '@/components/SessionTree.vue'
import type { SessionSummary } from '@/api'

// T038: Extended session type with anchor name from SessionTree
interface SessionWithAnchor extends SessionSummary {
  anchorName: string
}

const router = useRouter()
const selectedSession = ref<SessionWithAnchor | null>(null)

function handleSessionSelected(session: SessionWithAnchor) {
  selectedSession.value = session
}

// T038: Helper to format timestamp for URL
// Uses the raw date string parsing to avoid timezone conversion issues
function formatSessionTimestamp(dateStr: string): string {
  // Parse ISO format: "2026-01-06T14:01:37" or "2026-01-06 14:01:37"
  // Extract components directly from string to avoid timezone conversion
  const match = dateStr.match(/(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2}):(\d{2})/)
  if (match) {
    const [, year, month, day, hour, minute, second] = match
    return `${year}-${month}-${day}_${hour}-${minute}-${second}`
  }
  // Fallback to Date parsing if format doesn't match
  const date = new Date(dateStr)
  const pad = (n: number) => n.toString().padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}_${pad(date.getHours())}-${pad(date.getMinutes())}-${pad(date.getSeconds())}`
}

function goToPlayer() {
  if (selectedSession.value) {
    // T038: Use human-readable URL format
    const sessionTimestamp = formatSessionTimestamp(selectedSession.value.started_at)
    router.push({
      name: 'Player',
      params: {
        anchorName: selectedSession.value.anchorName,
        sessionTimestamp,
      }
    })
  }
}

function formatDateTime(dateStr: string): string {
  return new Date(dateStr).toLocaleString('zh-CN')
}

function formatDuration(seconds: number | null): string {
  if (!seconds) return '-'
  const hours = Math.floor(seconds / 3600)
  const minutes = Math.floor((seconds % 3600) / 60)
  const secs = Math.floor(seconds % 60)
  if (hours > 0) {
    return `${hours}小时${minutes}分${secs}秒`
  }
  return `${minutes}分${secs}秒`
}

function formatSize(bytes: number | null): string {
  if (!bytes) return '-'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  let size = bytes
  let unitIndex = 0
  while (size >= 1024 && unitIndex < units.length - 1) {
    size /= 1024
    unitIndex++
  }
  return `${size.toFixed(2)} ${units[unitIndex]}`
}
</script>

<style scoped>
.home-container {
  height: 100vh;
}

.sidebar {
  background-color: #f5f7fa;
  border-right: 1px solid #e4e7ed;
  display: flex;
  flex-direction: column;
}

.sidebar-header {
  padding: 16px;
  border-bottom: 1px solid #e4e7ed;
}

.sidebar-header h2 {
  margin: 0;
  font-size: 18px;
  color: #303133;
}

.main-content {
  background-color: #fff;
  padding: 20px;
}

.welcome {
  display: flex;
  justify-content: center;
  align-items: center;
  height: 100%;
}

.session-preview {
  max-width: 800px;
  margin: 0 auto;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
</style>
