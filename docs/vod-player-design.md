# VOD 播放器系统设计方案

本文档描述一个与现有录制工具解耦的 VOD（Video on Demand）播放系统，采用 **控制流与数据流分离** 架构，通过预签名 URL 实现浏览器直连 TOS，达到"低延迟、高性能 Seek、安全访问、服务器零带宽负载"的目标。

---

## 1. 需求分析

### 1.1 核心需求

1. **与录制工具解耦** - 仅通过数据库交互，独立部署
2. **Web UI 浏览** - 按「平台 → 主播 → 直播场次 → 分段」层级浏览
3. **高性能播放** - 支持精确 Seek，毫秒级跳转响应
4. **服务器零带宽** - 视频流量直连 TOS/CDN，不经过应用服务器
5. **安全访问** - 私有 Bucket + 时效性预签名 URL

### 1.2 现有数据结构

```
RecordingSession (直播场次)
├── platform         # 平台
├── anchor_name      # 主播名称
├── started_at       # 开始时间
├── ended_at         # 结束时间
└── segments[]       # 分段列表
    └── RecordingSegment
        ├── segment_index    # 分段序号
        ├── file_name        # 文件名
        ├── file_size        # 文件大小
        ├── oss_path         # OSS 路径 (TS)
        ├── oss_bucket       # OSS bucket
        ├── upload_status    # 上传状态
        ├── mp4_oss_path     # MP4 路径 (新增)
        ├── mp4_status       # MP4 转换状态 (新增)
        └── duration         # 时长秒数 (新增)
```

---

## 2. 系统架构

### 2.1 整体架构

采用 **控制流与数据流分离** 设计：

- **控制流（服务器）**：目录索引、用户鉴权、生成预签名 URL
- **数据流（TOS/CDN）**：媒体数据存储和流式分发，浏览器直连

```
┌─────────────────────────────────────────────────────────────────┐
│                         浏览器 (Web UI)                          │
│  ┌─────────────────┐  ┌─────────────────────────────────────┐  │
│  │   Vue 3         │  │         Video.js 播放器              │  │
│  │   树形导航       │  │         原生 MP4 + Range 请求        │  │
│  └────────┬────────┘  └───────────────┬─────────────────────┘  │
└───────────┼───────────────────────────┼─────────────────────────┘
            │ REST API                  │ Range Request (直连)
            │ (目录/签名URL)             │
            ▼                           ▼
┌───────────────────────┐       ┌───────────────────────────────┐
│   FastAPI 后端服务     │       │        火山云 TOS / CDN        │
│  ┌─────────────────┐  │       │                               │
│  │  /api/* 目录API  │  │       │   ┌─────────────────────┐    │
│  │  /api/play 签名  │  │       │   │  Fast Start MP4     │    │
│  └────────┬────────┘  │       │   │  (moov 在文件头部)   │    │
│           │           │       │   └─────────────────────┘    │
│           ▼           │       │                               │
│  ┌─────────────────┐  │       └───────────────────────────────┘
│  │ SQLAlchemy ORM  │  │
│  └────────┬────────┘  │
└───────────┼───────────┘
            │
            ▼
     ┌───────────┐
     │  SQLite/  │
     │ PostgreSQL│
     └───────────┘
```

### 2.2 数据流说明

```
1. 用户浏览器 ──请求目录/签名URL──▶ 应用服务器
2. 应用服务器 ──鉴权 & 查询DB──▶ 数据库
3. 应用服务器 ──调用SDK生成预签名URL──▶ 返回给浏览器
4. 用户浏览器 ──Range Request (Seek)──▶ TOS/CDN (直连)
5. TOS/CDN ──返回视频分片数据──▶ 用户浏览器
```

### 2.3 组件说明

| 组件 | 技术选型 | 说明 |
|------|----------|------|
| **前端 UI** | Vue 3 + Element Plus | 树形导航、分段列表 |
| **播放器** | Video.js | 原生 MP4 播放，无需 HLS 插件 |
| **后端 API** | FastAPI (Python) | 异步高性能，与录制工具同语言 |
| **对象存储** | 火山云 TOS | Private Bucket + 预签名 URL |
| **数据库** | 复用现有 SQLAlchemy 模型 | 只读访问 |

---

## 3. 数据处理方案

### 3.1 TS → MP4 转封装

录制源文件是 `.ts` 格式，为实现 Web 端"秒开"和"精确 Seek"，需转封装为 **Fast Start MP4**（`moov` 原子位于文件头部）。

**处理策略**：
- **Remuxing（转封装）**，非转码，无损且快速
- 每个 Segment 单独转换为 MP4
- 转换完成后上传至 TOS

**FFmpeg 命令**：
```bash
ffmpeg -i input.ts -c copy -movflags faststart output.mp4
```

### 3.2 处理流程

```
┌─────────────────────────────────────────────────────────────┐
│              录制分段完成 & TS 上传成功                       │
└─────────────────────────────┬───────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│  1. 下载 TS 文件到本地临时目录                                │
│     (或直接从本地录制路径读取)                                │
└─────────────────────────────┬───────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│  2. 转封装为 Fast Start MP4                                  │
│     ffmpeg -i segment.ts -c copy -movflags faststart seg.mp4 │
└─────────────────────────────┬───────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│  3. 获取时长信息                                             │
│     ffprobe -v quiet -print_format json -show_format seg.mp4 │
└─────────────────────────────┬───────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│  4. 上传 MP4 到 TOS，更新数据库                              │
│     - mp4_oss_path = "recordings/xxx/segment_0.mp4"         │
│     - mp4_status = "completed"                              │
│     - duration = 1800.5 (秒)                                │
└─────────────────────────────────────────────────────────────┘
```

### 3.3 转封装服务代码

```python
# backend/services/transcode.py

import subprocess
import json
from pathlib import Path
from typing import Tuple

def remux_ts_to_mp4(ts_path: str, mp4_path: str) -> bool:
    """
    将 TS 文件转封装为 Fast Start MP4
    返回是否成功
    """
    cmd = [
        'ffmpeg', '-y',
        '-i', ts_path,
        '-c', 'copy',
        '-movflags', 'faststart',
        mp4_path
    ]
    result = subprocess.run(cmd, capture_output=True)
    return result.returncode == 0


def get_duration(file_path: str) -> float:
    """使用 ffprobe 获取视频时长（秒）"""
    cmd = [
        'ffprobe', '-v', 'quiet',
        '-print_format', 'json',
        '-show_format',
        file_path
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        return 0.0
    data = json.loads(result.stdout)
    return float(data.get('format', {}).get('duration', 0))


async def process_segment(segment_id: int, db: Session):
    """
    处理单个分段：下载 TS → 转 MP4 → 上传 → 更新 DB
    """
    segment = db.query(RecordingSegment).get(segment_id)
    if not segment or segment.mp4_status == "completed":
        return

    # 更新状态为处理中
    segment.mp4_status = "processing"
    db.commit()

    try:
        # 1. 下载 TS (如果不在本地)
        ts_local = f"/tmp/{segment.id}.ts"
        await download_from_tos(segment.oss_bucket, segment.oss_path, ts_local)

        # 2. 转封装
        mp4_local = f"/tmp/{segment.id}.mp4"
        if not remux_ts_to_mp4(ts_local, mp4_local):
            raise Exception("FFmpeg remux failed")

        # 3. 获取时长
        duration = get_duration(mp4_local)

        # 4. 上传 MP4
        mp4_oss_path = segment.oss_path.replace('.ts', '.mp4')
        await upload_to_tos(segment.oss_bucket, mp4_oss_path, mp4_local)

        # 5. 更新数据库
        segment.mp4_oss_path = mp4_oss_path
        segment.mp4_status = "completed"
        segment.duration = duration
        db.commit()

    except Exception as e:
        segment.mp4_status = "failed"
        db.commit()
        raise

    finally:
        # 清理临时文件
        Path(ts_local).unlink(missing_ok=True)
        Path(mp4_local).unlink(missing_ok=True)
```

---

## 4. 存储与安全设计

### 4.1 TOS Bucket 权限

- **权限设置**：**Private（私有）**，禁止匿名访问
- **访问方式**：仅通过后端生成的 **预签名 URL** 访问

### 4.2 预签名 URL 机制

后端使用 AK/SK 计算签名，生成时效性链接：

```python
# backend/services/tos_sign.py

import tos

def generate_presigned_url(
    bucket: str,
    object_key: str,
    expires: int = 3600  # 默认1小时
) -> str:
    """
    生成 TOS 预签名 URL
    """
    client = tos.TosClientV2(
        ak=config.TOS_ACCESS_KEY,
        sk=config.TOS_SECRET_KEY,
        endpoint=config.TOS_ENDPOINT,
        region=config.TOS_REGION
    )

    return client.pre_signed_url(
        tos.HttpMethodType.Http_Method_Get,
        bucket,
        object_key,
        expires=expires,
        # 确保浏览器直接播放而非下载
        params={'response-content-disposition': 'inline'}
    )
```

### 4.3 URL 有效期策略

| 场景 | 有效期建议 |
|------|-----------|
| 短分段 (< 30分钟) | 1 小时 |
| 长分段 (30-120分钟) | 视频时长 × 1.5 |
| 超长分段 (> 2小时) | 4 小时 |

---

## 5. 后端 API 设计

### 5.1 目录结构

```
vod-player/
├── backend/
│   ├── main.py                  # FastAPI 入口
│   ├── config.py                # 配置管理
│   ├── routers/
│   │   └── api.py               # REST API 路由
│   ├── services/
│   │   ├── tos_sign.py          # TOS 签名服务
│   │   └── transcode.py         # 转封装服务
│   ├── models/
│   │   └── recording.py         # 数据库模型
│   └── schemas/
│       └── response.py          # API 响应模型
├── frontend/
│   ├── src/
│   │   ├── views/
│   │   │   ├── Home.vue         # 首页/导航
│   │   │   └── Player.vue       # 播放页
│   │   ├── components/
│   │   │   ├── SessionTree.vue  # 树形导航
│   │   │   └── VideoPlayer.vue  # 播放器封装
│   │   └── api/
│   │       └── index.ts         # API 调用
│   └── package.json
├── docker-compose.yml
└── README.md
```

### 5.2 API 接口设计

```yaml
# 平台列表
GET /api/platforms
Response: ["抖音直播", "快手直播", "Bilibili直播", ...]

# 主播列表（按平台）
GET /api/platforms/{platform}/anchors
Response: [
  { "name": "主播A", "session_count": 10, "last_live": "2025-12-16" },
  ...
]

# 直播场次列表（按主播）
GET /api/anchors/{anchor_name}/sessions
Query: ?platform=抖音直播&page=1&limit=20
Response: {
  "total": 50,
  "items": [
    {
      "id": 123,
      "started_at": "2025-12-16T14:00:00",
      "ended_at": "2025-12-16T16:30:00",
      "duration": 9000,
      "segment_count": 5,
      "total_size": 5368709120
    },
    ...
  ]
}

# 场次详情（含分段信息）
GET /api/sessions/{session_id}
Response: {
  "id": 123,
  "platform": "抖音直播",
  "anchor_name": "主播A",
  "started_at": "2025-12-16T14:00:00",
  "total_duration": 9000,
  "segments": [
    {
      "id": 456,
      "index": 0,
      "duration": 1800,
      "size": 1073741824,
      "mp4_status": "completed"
    },
    ...
  ]
}

# 获取分段播放 URL（核心 API）
GET /api/segments/{segment_id}/play
Response: {
  "url": "https://bucket.tos-cn-beijing.volces.com/xxx.mp4?X-Tos-...",
  "expires_at": "2025-12-17T15:30:00Z",
  "duration": 1800,
  "title": "主播A - 2025-12-16 14:00 - 分段1"
}
```

### 5.3 API 实现

```python
# backend/routers/api.py

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from services.tos_sign import generate_presigned_url
from datetime import datetime, timedelta

router = APIRouter(prefix="/api")

@router.get("/platforms")
async def list_platforms(db: Session = Depends(get_db)):
    """获取所有平台列表"""
    result = db.query(RecordingSession.platform).distinct().all()
    return [r[0] for r in result]


@router.get("/platforms/{platform}/anchors")
async def list_anchors(platform: str, db: Session = Depends(get_db)):
    """获取指定平台的主播列表"""
    from sqlalchemy import func

    result = db.query(
        RecordingSession.anchor_name,
        func.count(RecordingSession.id).label('session_count'),
        func.max(RecordingSession.started_at).label('last_live')
    ).filter(
        RecordingSession.platform == platform
    ).group_by(
        RecordingSession.anchor_name
    ).all()

    return [
        {
            "name": r.anchor_name,
            "session_count": r.session_count,
            "last_live": r.last_live.isoformat() if r.last_live else None
        }
        for r in result
    ]


@router.get("/segments/{segment_id}/play")
async def get_play_url(segment_id: int, db: Session = Depends(get_db)):
    """获取分段的预签名播放 URL"""
    segment = db.query(RecordingSegment).get(segment_id)
    if not segment:
        raise HTTPException(404, "Segment not found")

    if segment.mp4_status != "completed":
        raise HTTPException(400, f"MP4 not ready, status: {segment.mp4_status}")

    # 计算 URL 有效期
    duration = segment.duration or 3600
    expires = max(3600, int(duration * 1.5))

    url = generate_presigned_url(
        bucket=segment.oss_bucket,
        object_key=segment.mp4_oss_path,
        expires=expires
    )

    session = segment.session
    return {
        "url": url,
        "expires_at": (datetime.utcnow() + timedelta(seconds=expires)).isoformat() + "Z",
        "duration": segment.duration,
        "title": f"{session.anchor_name} - {session.started_at.strftime('%Y-%m-%d %H:%M')} - 分段{segment.segment_index + 1}"
    }
```

---

## 6. 前端设计

### 6.1 技术栈

| 组件 | 选择 | 说明 |
|------|------|------|
| 框架 | Vue 3 + TypeScript | 响应式、类型安全 |
| UI 库 | Element Plus | 树形控件、表格、布局 |
| 播放器 | Video.js | 原生 MP4 支持 |
| 构建 | Vite | 快速开发体验 |

### 6.2 页面布局

```
┌────────────────────────────────────────────────────────────┐
│  LOGO   直播录像回放                          [设置] [帮助] │
├──────────────┬─────────────────────────────────────────────┤
│              │                                             │
│  平台        │   ┌─────────────────────────────────────┐   │
│  ├─ 抖音直播 │   │                                     │   │
│  │  ├─ 主播A │   │          Video.js Player            │   │
│  │  │  ├─ 12/16 14:00 │                                │   │
│  │  │  └─ 12/15 20:00 │                                │   │
│  │  └─ 主播B │   │                                     │   │
│  ├─ 快手直播 │   └─────────────────────────────────────┘   │
│  └─ Bilibili │                                             │
│              │   00:45:30 / 01:30:00   advancement ▶ [🔊] [⛶] │
│              │                                             │
│              │   分段列表：                                │
│              │   ┌──────┐ ┌──────┐ ┌──────┐              │
│              │   │Seg 1 │ │Seg 2 │ │Seg 3 │ ...          │
│              │   │30min │ │30min │ │30min │              │
│              │   └──────┘ └──────┘ └──────┘              │
│              │                                             │
└──────────────┴─────────────────────────────────────────────┘
```

### 6.3 播放器组件

```vue
<!-- frontend/src/components/VideoPlayer.vue -->
<template>
  <div class="video-container">
    <video
      ref="videoRef"
      class="video-js vjs-default-skin vjs-big-play-centered"
    />

    <!-- 分段选择器 -->
    <div class="segment-list">
      <div
        v-for="seg in segments"
        :key="seg.id"
        class="segment-item"
        :class="{ active: currentSegmentId === seg.id, disabled: seg.mp4_status !== 'completed' }"
        @click="playSegment(seg)"
      >
        <span class="segment-index">分段 {{ seg.index + 1 }}</span>
        <span class="segment-duration">{{ formatDuration(seg.duration) }}</span>
        <span v-if="seg.mp4_status !== 'completed'" class="segment-status">
          {{ seg.mp4_status === 'processing' ? '转换中...' : '未就绪' }}
        </span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import videojs from 'video.js'
import 'video.js/dist/video-js.css'
import { getPlayUrl } from '@/api'

interface Segment {
  id: number
  index: number
  duration: number
  mp4_status: string
}

const props = defineProps<{
  segments: Segment[]
}>()

const videoRef = ref<HTMLVideoElement>()
const currentSegmentId = ref<number | null>(null)
let player: ReturnType<typeof videojs> | null = null

onMounted(() => {
  player = videojs(videoRef.value!, {
    controls: true,
    autoplay: false,
    preload: 'metadata',  // 关键：仅加载元数据，不预下载全片
    fluid: true,
    playbackRates: [0.5, 1, 1.25, 1.5, 2],
    html5: {
      nativeVideoTracks: true,
      nativeAudioTracks: true,
      nativeTextTracks: true
    }
  })

  // 自动播放第一个可用分段
  const firstReady = props.segments.find(s => s.mp4_status === 'completed')
  if (firstReady) {
    playSegment(firstReady)
  }
})

onUnmounted(() => {
  player?.dispose()
})

async function playSegment(segment: Segment) {
  if (segment.mp4_status !== 'completed' || !player) return

  currentSegmentId.value = segment.id

  try {
    const { url } = await getPlayUrl(segment.id)
    player.src({
      type: 'video/mp4',
      src: url
    })
    player.play()
  } catch (error) {
    console.error('Failed to load segment:', error)
  }
}

function formatDuration(seconds: number): string {
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  const s = Math.floor(seconds % 60)
  if (h > 0) {
    return `${h}:${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`
  }
  return `${m}:${s.toString().padStart(2, '0')}`
}
</script>

<style scoped>
.segment-list {
  display: flex;
  gap: 8px;
  margin-top: 16px;
  flex-wrap: wrap;
}

.segment-item {
  padding: 8px 16px;
  border: 1px solid #ddd;
  border-radius: 4px;
  cursor: pointer;
  display: flex;
  flex-direction: column;
  align-items: center;
  min-width: 80px;
}

.segment-item:hover:not(.disabled) {
  border-color: #409eff;
  background-color: #f0f7ff;
}

.segment-item.active {
  border-color: #409eff;
  background-color: #409eff;
  color: white;
}

.segment-item.disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.segment-duration {
  font-size: 12px;
  color: #666;
}

.segment-item.active .segment-duration {
  color: rgba(255, 255, 255, 0.8);
}

.segment-status {
  font-size: 11px;
  color: #999;
}
</style>
```

### 6.4 Seek 工作流程

1. **初始加载**：Video.js 设置 `preload: 'metadata'`，浏览器发送 `Range: bytes=0-` 仅读取 MP4 头部
2. **解析索引**：浏览器读取 `moov` 原子，获取整片时长和关键帧字节分布
3. **用户拖拽**：用户拖动进度条到任意位置
4. **按需请求**：浏览器计算目标字节偏移，发起 `Range: bytes=XXXXXX-` 请求
5. **即时播放**：TOS 仅返回该偏移量后的数据，实现毫秒级 Seek

---

## 7. 数据库变更

### 7.1 RecordingSegment 表新增字段

```python
# 在现有 RecordingSegment 模型中添加

class RecordingSegment(Base):
    __tablename__ = 'recording_segments'

    # ... 现有字段 ...

    # 新增字段
    mp4_oss_path = Column(String(500), nullable=True, comment='MP4 文件 OSS 路径')
    mp4_status = Column(
        String(20),
        default='pending',
        comment='MP4 转换状态: pending/processing/completed/failed'
    )
    duration = Column(Float, nullable=True, comment='视频时长（秒）')
```

### 7.2 数据库迁移

```python
# alembic/versions/xxx_add_mp4_fields.py

def upgrade():
    op.add_column('recording_segments',
        sa.Column('mp4_oss_path', sa.String(500), nullable=True))
    op.add_column('recording_segments',
        sa.Column('mp4_status', sa.String(20), server_default='pending'))
    op.add_column('recording_segments',
        sa.Column('duration', sa.Float(), nullable=True))


def downgrade():
    op.drop_column('recording_segments', 'mp4_oss_path')
    op.drop_column('recording_segments', 'mp4_status')
    op.drop_column('recording_segments', 'duration')
```

---

## 8. 部署方案

### 8.1 Docker Compose

```yaml
# docker-compose.yml
version: '3.8'

services:
  backend:
    build: ./backend
    ports:
      - "8000:8000"
    volumes:
      - ./data:/data              # 数据库
      - ./config:/config:ro       # 配置文件
    environment:
      - DATABASE_URL=sqlite:///data/recordings.db
      - TOS_ACCESS_KEY=${TOS_ACCESS_KEY}
      - TOS_SECRET_KEY=${TOS_SECRET_KEY}
      - TOS_ENDPOINT=tos-cn-beijing.volces.com
      - TOS_REGION=cn-beijing

  frontend:
    build: ./frontend
    ports:
      - "80:80"
    depends_on:
      - backend

  # 转封装 Worker (可选，独立部署)
  transcode-worker:
    build: ./backend
    command: python -m services.transcode_worker
    volumes:
      - ./data:/data
      - /tmp/transcode:/tmp        # 临时转换目录
    environment:
      - DATABASE_URL=sqlite:///data/recordings.db
      - TOS_ACCESS_KEY=${TOS_ACCESS_KEY}
      - TOS_SECRET_KEY=${TOS_SECRET_KEY}
```

### 8.2 Nginx 配置（可选 CDN 前置）

```nginx
server {
    listen 80;
    server_name vod.example.com;

    # 静态前端
    location / {
        root /usr/share/nginx/html;
        try_files $uri $uri/ /index.html;
    }

    # API 代理
    location /api/ {
        proxy_pass http://backend:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

---

## 9. 性能与成本优化

### 9.1 CDN 加速（推荐）

当并发用户 > 10 时，建议在 TOS 前挂载火山云 CDN：

- 绑定自定义域名（如 `media.example.com`）
- 开启 URL 鉴权（Type A/B/C），与后端签名逻辑一致
- 缓存策略：视频文件缓存 7 天

### 9.2 浏览器缓存

- 预签名 URL 参数保持稳定（同一资源生成相同签名）
- 利用 `ETag` 和 `Last-Modified` 减少重复请求

### 9.3 转封装优化

- 使用 SSD 作为临时转换目录
- 可部署多个 transcode-worker 并行处理
- 优先处理最新录制的分段

---

## 10. 开发计划

### Phase 1: 后端核心

- [ ] 项目初始化，FastAPI 脚手架
- [ ] 数据库模型适配（新增字段）
- [ ] REST API 实现（目录浏览 + 预签名 URL）
- [ ] TOS 签名服务

### Phase 2: 转封装服务

- [ ] TS → MP4 转封装逻辑
- [ ] 转封装 Worker（监听新分段）
- [ ] 存量数据批量转换脚本

### Phase 3: 前端 UI

- [ ] Vue 项目初始化
- [ ] 树形导航组件
- [ ] Video.js 播放器集成
- [ ] 分段选择器

### Phase 4: 集成部署

- [ ] Docker 镜像构建
- [ ] 端到端测试
- [ ] 文档完善

---

## 11. 开源组件清单

| 组件 | 用途 | License |
|------|------|---------|
| [Video.js](https://github.com/videojs/video.js) | 播放器 | Apache-2.0 |
| [FastAPI](https://github.com/tiangolo/fastapi) | 后端框架 | MIT |
| [SQLAlchemy](https://github.com/sqlalchemy/sqlalchemy) | ORM | MIT |
| [Vue 3](https://github.com/vuejs/core) | 前端框架 | MIT |
| [Element Plus](https://github.com/element-plus/element-plus) | UI 组件库 | MIT |
| [tos-sdk](https://github.com/volcengine/ve-tos-python-sdk) | TOS 访问 | Apache-2.0 |
| [FFmpeg](https://ffmpeg.org/) | 转封装 | LGPL/GPL |

---

## 12. 方案优势总结

1. **极致 Seek 体验** - 基于 Fast Start MP4 和 HTTP Range，实现毫秒级跳转
2. **服务器零带宽压力** - 视频流量直连 TOS/CDN，应用服务器仅处理元数据
3. **开发成本低** - 无需复杂的 HLS 分片逻辑，API 设计简洁
4. **高安全性** - 私有 Bucket + 时效性预签名 URL
5. **完全适配现有系统** - 复用现有数据库，仅需新增少量字段
