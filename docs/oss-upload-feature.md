# 录制文件管理与 OSS 上传功能

本文档记录录制文件管理与 TOS 上传功能的设计、实现和使用说明。

## 1. 规划

### 1.1 需求概述

1. 使用 SQLAlchemy ORM 保存录制业务信息（支持多数据库后端）
2. 每次录制完成后写入数据库记录
3. 分段录制的文件作为一组记录（父子关系：Session -> Segments）
4. 后台线程异步上传到 TOS（火山引擎对象存储，使用官方 SDK）
5. 上传完成后更新数据库、删除本地文件
6. 失败自动重试 3 次

### 1.2 模块结构

```
src/storage/                    # 新模块
├── __init__.py                # 模块导出
├── models.py                  # SQLAlchemy ORM 模型
├── database.py                # 数据库引擎和会话管理
├── repository.py              # 数据访问层 (CRUD)
├── tos_uploader.py            # TOS 上传客户端封装
├── upload_queue.py            # 后台上传队列和工作线程
└── manager.py                 # 高层 API（与 main.py 集成）

data/
└── recordings.db              # SQLite 数据库（自动创建）

config/
├── config.ini                 # 添加 [OSS设置] 配置节
└── tos_credentials.ini        # TOS 凭证（不提交到 git）
```

### 1.3 数据库模型

#### RecordingSession（录制会话 - 一次直播）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | Integer | 主键 |
| anchor_name | String(255) | 主播名称 |
| platform | String(100) | 平台（抖音直播等） |
| live_room_url | Text | 直播间地址 |
| live_title | String(500) | 直播标题 |
| started_at | DateTime | 开始时间 |
| ended_at | DateTime | 结束时间 |
| record_quality | String(20) | 录制质量 |
| is_split | Boolean | 是否分段 |
| segment_count | Integer | 分段数量 |
| created_at | DateTime | 记录创建时间 |
| updated_at | DateTime | 记录更新时间 |

#### RecordingSegment（录制分段 - 单个文件）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | Integer | 主键 |
| session_id | Integer | 外键 -> RecordingSession |
| segment_index | Integer | 分段序号 (0, 1, 2...) |
| local_file_path | Text | 本地文件路径 |
| file_name | String(500) | 文件名 |
| file_format | String(20) | 格式 (ts/mp4/mkv/flv) |
| file_size | BigInteger | 文件大小 (bytes) |
| oss_path | Text | OSS 路径 (上传后填充) |
| oss_bucket | String(255) | OSS bucket |
| upload_status | Enum | pending/uploading/completed/failed/skipped |
| upload_retry_count | Integer | 重试次数 |
| upload_error_message | Text | 错误信息 |
| local_file_deleted | Boolean | 本地文件已删除 |
| recorded_at | DateTime | 录制时间 |

### 1.4 OSS 路径格式

```
tos://{bucket}/{platform}/{date}/{anchor_name}/{filename}

示例：
tos://ql-live/抖音直播/2025-12-16/Seven(国服老虎)/Seven(国服老虎)_2025-12-16_14-50-21_000.ts
```

---

## 2. 实施细节

### 2.1 核心类设计

#### DatabaseManager（数据库管理器）
- 单例模式，全局唯一实例
- 支持 SQLite（默认）、PostgreSQL、MySQL（通过 URL 配置）
- 提供 session 上下文管理器，自动处理事务

```python
# 使用示例
db_manager = DatabaseManager.get_instance(database_url)
with db_manager.get_session() as session:
    # 数据库操作
    pass
```

#### RecordingRepository（数据访问层）
- `create_session()` - 创建录制会话
- `add_segment()` - 添加录制分段
- `get_pending_uploads()` - 获取待上传列表
- `update_upload_status()` - 更新上传状态
- `end_session()` - 结束录制会话
- `get_upload_stats()` - 获取上传统计

#### TOSUploader（TOS 上传器）
- 封装官方 tos SDK
- `upload_file()` - 上传文件到 TOS
- `generate_oss_key()` - 生成 OSS 路径
- `check_bucket_access()` - 检查 bucket 访问权限
- 自动禁用代理（内网访问需要直连）

#### UploadWorker（上传工作线程）
- 后台 daemon 线程，不阻塞主程序退出
- 优先级队列处理任务
- 自动重试失败任务（最多 3 次）
- 上传成功后可选删除本地文件

#### RecordingManager（高层管理器）
- 主要集成接口，提供简洁 API
- `from_config()` - 从配置文件创建实例
- `start()` - 启动后台上传服务
- `stop()` - 停止后台服务
- `start_recording()` - 开始录制时调用
- `on_recording_complete()` - 录制完成时调用
- `end_recording()` - 结束录制时调用

### 2.2 配置项

在 `config/config.ini` 中添加：

```ini
[OSS设置]
# OSS 上传功能开关
启用OSS上传(是/否) = 否
# 上传成功后是否删除本地文件
上传后删除本地文件(是/否) = 是
# 上传失败重试次数
上传失败重试次数 = 3
# 数据库连接 URL（留空则使用 SQLite）
# 示例: postgresql://user:pass@localhost/dbname
#      mysql+pymysql://user:pass@localhost/dbname
数据库URL =
```

TOS 凭证配置 `config/tos_credentials.ini`：

```ini
[credentials]
access_key_id = YOUR_ACCESS_KEY
secret_access_key = YOUR_SECRET_KEY
endpoint = tos-cn-beijing.ivolces.com
region = cn-beijing
bucket = your-bucket-name
```

### 2.3 main.py 集成

#### 初始化（在配置加载后）

```python
from src.storage import RecordingManager

# 全局变量
recording_manager: RecordingManager | None = None

# 初始化
recording_manager = RecordingManager.from_config(
    config_file='config/config.ini',
    tos_config_file='config/tos_credentials.ini'
)
recording_manager.start()
```

#### check_subprocess() 修改

添加参数：`platform`, `anchor_name`, `live_room_url`

录制成功后调用：

```python
if recording_manager:
    recording_manager.on_recording_complete(
        record_name=record_name,
        save_file_path=save_file_path,
        save_type=save_type,
        platform=platform,
        anchor_name=anchor_name,
        live_room_url=live_room_url
    )
```

### 2.4 依赖

```toml
# pyproject.toml
dependencies = [
    "sqlalchemy>=2.0.0",
    "tos>=2.7.2",
    # ... 其他依赖
]
```

### 2.5 工作流程

```
录制开始
    ↓
FFmpeg 录制直播流
    ↓
录制完成（check_subprocess 检测到）
    ↓
调用 recording_manager.on_recording_complete()
    ↓
写入数据库（RecordingSession + RecordingSegment）
    ↓
如果启用 OSS 上传
    ↓
加入上传队列（UploadWorker）
    ↓
后台线程上传到 TOS
    ↓
上传成功 → 更新数据库状态 → 删除本地文件（可选）
上传失败 → 重试（最多 3 次）→ 标记为 failed
```

---

## 3. 现状

### 3.1 已完成

| 阶段 | 任务 | 状态 |
|------|------|------|
| Phase 1 | 创建 src/storage/ 目录和 models.py | ✅ 完成 |
| Phase 1 | 实现 database.py 数据库管理 | ✅ 完成 |
| Phase 1 | 添加 sqlalchemy 依赖 | ✅ 完成 |
| Phase 2 | 实现 repository.py 数据访问层 | ✅ 完成 |
| Phase 2 | 实现 __init__.py 模块导出 | ✅ 完成 |
| Phase 3 | 实现 tos_uploader.py TOS 客户端封装 | ✅ 完成 |
| Phase 3 | 实现 upload_queue.py 后台上传队列 | ✅ 完成 |
| Phase 4 | 实现 manager.py 高层管理 API | ✅ 完成 |
| Phase 4 | 修改 config.ini 添加 OSS 配置 | ✅ 完成 |
| Phase 4 | 修改 main.py 集成录制管理器 | ✅ 完成 |
| Phase 5 | 测试数据库操作 | ✅ 完成 |
| Phase 5 | 测试模拟录制流程 | ✅ 完成 |

### 3.2 测试结果

```
=== Simulating Recording Flow ===
Manager started (upload disabled for test)
Session created: id=1
Segment 0 added: /tmp/test_recording_0.ts
Segment 1 added: /tmp/test_recording_1.ts
Session ended
Upload stats: {'total': 2, 'pending': 2, 'uploading': 0, 'completed': 0, 'failed': 0}
Session: anchor=TestAnchor, platform=抖音直播, segments=2
  Segment 0: test_recording_0.ts, status=pending
  Segment 1: test_recording_1.ts, status=pending
Manager stopped

=== Test Completed Successfully ===
```

### 3.3 新增/修改的文件

| 文件 | 操作 | 说明 |
|------|------|------|
| `src/storage/__init__.py` | 新建 | 模块导出 |
| `src/storage/models.py` | 新建 | SQLAlchemy ORM 模型 |
| `src/storage/database.py` | 新建 | 数据库管理器 |
| `src/storage/repository.py` | 新建 | 数据访问层 |
| `src/storage/tos_uploader.py` | 新建 | TOS 上传客户端 |
| `src/storage/upload_queue.py` | 新建 | 后台上传队列 |
| `src/storage/manager.py` | 新建 | 高层管理 API |
| `config/config.ini` | 修改 | 添加 [OSS设置] 节 |
| `main.py` | 修改 | 集成 RecordingManager |
| `pyproject.toml` | 修改 | 添加 sqlalchemy 依赖 |
| `.gitignore` | 修改 | 添加 data/ 和 tos_credentials.ini |
| `config/tos_credentials.ini.example` | 新建 | TOS 凭证模板 |

### 3.4 使用说明

#### 启用 OSS 上传

1. 复制凭证模板：
   ```bash
   cp config/tos_credentials.ini.example config/tos_credentials.ini
   ```

2. 编辑 `config/tos_credentials.ini`，填入真实的 TOS 凭证

3. 编辑 `config/config.ini`，设置：
   ```ini
   [OSS设置]
   启用OSS上传(是/否) = 是
   ```

4. 运行程序：
   ```bash
   uv run main.py
   ```

#### 仅使用数据库记录（不上传）

默认配置即可，数据库会自动记录每次录制信息到 `data/recordings.db`。

#### 使用其他数据库

在 `config/config.ini` 中设置数据库 URL：

```ini
[OSS设置]
数据库URL = postgresql://user:pass@localhost/recordings
# 或
数据库URL = mysql+pymysql://user:pass@localhost/recordings
```

### 3.5 待后续优化

- [ ] 添加 Web UI 查看录制历史和上传状态
- [ ] 支持断点续传（大文件）
- [ ] 添加上传速度限制
- [ ] 支持其他云存储（阿里云 OSS、腾讯云 COS 等）

---

## 附录：TOS 测试脚本

测试 TOS 连接的脚本位于 `scripts/` 目录：

- `scripts/test_tos.py` - 使用官方 TOS SDK 测试
- `scripts/test_tos_boto3.py` - 使用 boto3 测试（备用）

运行测试：

```bash
uv run scripts/test_tos.py
```
