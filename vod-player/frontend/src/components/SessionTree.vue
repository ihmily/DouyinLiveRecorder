<template>
  <div class="session-tree">
    <el-tree
      :data="treeData"
      :props="defaultProps"
      :load="loadNode"
      lazy
      node-key="id"
      @node-click="handleNodeClick"
      highlight-current
    >
      <template #default="{ node, data }">
        <span class="tree-node">
          <el-icon v-if="data.type === 'platform'"><Monitor /></el-icon>
          <el-icon v-else-if="data.type === 'anchor'"><User /></el-icon>
          <el-icon v-else-if="data.type === 'session'"><VideoPlay /></el-icon>
          <span class="tree-node-label">{{ node.label }}</span>
          <span v-if="data.count" class="tree-node-count">({{ data.count }})</span>
        </span>
      </template>
    </el-tree>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { Monitor, User, VideoPlay } from '@element-plus/icons-vue'
import { getPlatforms, getAnchors, getSessions } from '@/api'
import type { Platform, Anchor, SessionSummary } from '@/api'

interface TreeNode {
  id: string
  label: string
  type: 'platform' | 'anchor' | 'session'
  count?: number
  isLeaf?: boolean
  data?: Platform | Anchor | SessionSummary
}

const emit = defineEmits<{
  (e: 'session-selected', session: SessionSummary): void
}>()

const treeData = ref<TreeNode[]>([])

const defaultProps = {
  children: 'children',
  label: 'label',
  isLeaf: 'isLeaf',
}

function formatDuration(seconds: number | null): string {
  if (!seconds) return ''
  const hours = Math.floor(seconds / 3600)
  const minutes = Math.floor((seconds % 3600) / 60)
  if (hours > 0) {
    return `${hours}h${minutes}m`
  }
  return `${minutes}m`
}

function formatDate(dateStr: string): string {
  const date = new Date(dateStr)
  return date.toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

async function loadNode(node: any, resolve: (data: TreeNode[]) => void) {
  // Root level: load platforms
  if (node.level === 0) {
    try {
      const platforms = await getPlatforms()
      const nodes: TreeNode[] = platforms.map((p) => ({
        id: `platform-${p.name}`,
        label: p.name,
        type: 'platform',
        count: p.session_count,
        isLeaf: false,
        data: p,
      }))
      resolve(nodes)
    } catch (error) {
      console.error('Failed to load platforms:', error)
      resolve([])
    }
    return
  }

  const data = node.data as TreeNode

  // Platform level: load anchors
  if (data.type === 'platform') {
    try {
      const anchors = await getAnchors(data.label)
      const nodes: TreeNode[] = anchors.map((a) => ({
        id: `anchor-${data.label}-${a.name}`,
        label: a.name,
        type: 'anchor',
        count: a.session_count,
        isLeaf: false,
        data: a,
      }))
      resolve(nodes)
    } catch (error) {
      console.error('Failed to load anchors:', error)
      resolve([])
    }
    return
  }

  // Anchor level: load sessions
  if (data.type === 'anchor') {
    try {
      // Extract platform from parent
      const platformName = node.parent?.data?.label || ''
      const response = await getSessions(data.label, { platform: platformName, limit: 50 })
      const nodes: TreeNode[] = response.items.map((s) => ({
        id: `session-${s.id}`,
        label: `${formatDate(s.started_at)} ${formatDuration(s.duration)}`,
        type: 'session',
        count: s.segment_count,
        isLeaf: true,
        data: s,
      }))
      resolve(nodes)
    } catch (error) {
      console.error('Failed to load sessions:', error)
      resolve([])
    }
    return
  }

  resolve([])
}

function handleNodeClick(data: TreeNode) {
  if (data.type === 'session' && data.data) {
    emit('session-selected', data.data as SessionSummary)
  }
}
</script>

<style scoped>
.session-tree {
  height: 100%;
  overflow-y: auto;
  padding: 10px;
}

.tree-node {
  display: flex;
  align-items: center;
  gap: 6px;
}

.tree-node-label {
  flex: 1;
}

.tree-node-count {
  color: #909399;
  font-size: 12px;
}

:deep(.el-tree-node__content) {
  height: 36px;
}
</style>
