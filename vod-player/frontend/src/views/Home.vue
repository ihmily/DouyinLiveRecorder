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

const router = useRouter()
const selectedSession = ref<SessionSummary | null>(null)

function handleSessionSelected(session: SessionSummary) {
  selectedSession.value = session
}

function goToPlayer() {
  if (selectedSession.value) {
    router.push({ name: 'Player', params: { sessionId: selectedSession.value.id } })
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
