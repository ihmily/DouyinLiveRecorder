# Feature Specification: VOD/OSS双端点配置

**Feature Branch**: `003-dual-oss-endpoint`
**Created**: 2026-01-06
**Status**: Draft
**Input**: User description: "现在的vod and oss上传会读取统一的配置，vod里面需要提供公网的oss地址，且需要从SDK把公网oss的地址转换成一个限时可读的url，但是uv run main.py 中 数据转换的PPL 上传OSS必须走内网"

## Clarifications

### Session 2026-01-06

- Q: 公网端点应该使用现有的 `s3_endpoint` 配置项还是新增一个 `public_endpoint` 配置项？ → A: 复用现有 `s3_endpoint` 作为公网端点（零配置变更）
- Q: 当 `s3_endpoint` 未配置时，VOD服务是否应该回退使用 `endpoint`（内网），还是拒绝启动？ → A: 回退使用 `endpoint`，记录警告日志（渐进式迁移友好）

## Problem Statement

当前系统存在OSS端点配置的冲突需求：

1. **VOD播放服务**需要使用**公网OSS地址**来生成限时可读URL，以便用户通过浏览器访问视频内容
2. **录制转换管道（PPL）**需要使用**内网OSS地址**上传文件，以节省带宽成本并提高上传速度

目前系统读取统一的配置，无法同时满足这两种场景的需求。

## User Scenarios & Testing *(mandatory)*

### User Story 1 - 内网上传视频文件 (Priority: P1)

作为录制系统的运维人员，我希望视频文件通过内网端点上传到OSS，以便节省公网带宽成本并获得更快的上传速度。

**Why this priority**: 上传功能是核心功能，内网上传直接影响运营成本和系统性能。

**Independent Test**: 可以通过执行 `uv run main.py` 录制一段直播视频，验证文件是否通过内网端点成功上传到OSS。

**Acceptance Scenarios**:

1. **Given** 系统配置了内网OSS端点，**When** 录制完成并触发上传，**Then** 文件通过内网端点上传到指定bucket，且不使用代理
2. **Given** 系统在内网环境运行，**When** 上传大文件(>100MB)，**Then** 上传速度应达到内网预期速度（显著快于公网）
3. **Given** 内网端点配置错误或不可达，**When** 尝试上传，**Then** 系统记录明确的错误信息，标识是内网端点连接问题

---

### User Story 2 - 生成公网可访问的播放URL (Priority: P1)

作为视频观看者，我希望通过浏览器访问VOD服务时能获取可播放的视频URL，以便在任何网络环境下观看录制内容。

**Why this priority**: 播放功能是面向用户的核心功能，没有可访问的URL用户无法观看视频。

**Independent Test**: 可以通过调用 VOD API `/api/segments/{segment_id}/play` 验证返回的URL是否为公网可访问的限时签名URL。

**Acceptance Scenarios**:

1. **Given** 视频已上传到OSS，**When** 用户请求播放URL，**Then** 返回使用公网端点的限时签名URL
2. **Given** 返回的播放URL，**When** 用户在公网环境访问该URL，**Then** 能够正常加载并播放视频
3. **Given** 签名URL已生成，**When** 超过配置的有效期（默认3600秒），**Then** URL失效，访问返回权限错误

---

### User Story 3 - 配置管理 (Priority: P2)

作为系统管理员，我希望能够分别配置内网和公网OSS端点，以便根据部署环境灵活调整配置。

**Why this priority**: 配置灵活性支持多种部署场景，但依赖于核心上传和播放功能。

**Independent Test**: 可以通过修改配置文件中的端点设置，重启相关服务，验证系统使用了正确的端点。

**Acceptance Scenarios**:

1. **Given** 配置文件包含内网和公网两个端点，**When** 系统启动，**Then** 上传模块读取内网端点，VOD服务读取公网端点
2. **Given** 只配置了一个端点（向后兼容），**When** 系统启动，**Then** 两个服务都使用该端点，并记录警告日志提示配置不完整
3. **Given** 配置文件格式错误或缺失必要字段，**When** 系统启动，**Then** 提供清晰的错误提示说明缺失的配置项

---

### Edge Cases

- 配置中内网/公网端点设置为相同值时，系统应正常工作
- 公网端点不可达但内网端点可用时，上传应成功，但生成的播放URL可能无法访问
- 系统在纯公网环境部署（无内网）时，两个端点可配置为相同的公网地址
- 切换端点配置后，已生成的播放URL保持其原有行为（已签名的URL不受配置变更影响）

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: 系统MUST支持在配置文件中分别配置内网端点和公网端点
- **FR-002**: 录制转换管道MUST使用内网端点进行OSS文件上传
- **FR-003**: VOD服务MUST使用公网端点生成限时签名URL
- **FR-004**: 系统MUST在生成签名URL时，使用公网端点替换存储时使用的内网端点
- **FR-005**: 系统MUST支持向后兼容，当 `s3_endpoint` 未配置时，VOD服务回退使用 `endpoint` 并记录警告日志
- **FR-006**: 系统MUST在启动时验证端点配置，并对配置问题提供明确的日志提示
- **FR-007**: 系统MUST确保上传时清除代理环境变量，以保证内网直连
- **FR-008**: VOD服务生成的签名URL MUST包含正确的公网域名

### Key Entities

- **OSS端点配置**: 包含内网端点 `endpoint`（用于上传）和公网端点 `s3_endpoint`（用于URL生成）两个配置项，复用现有配置结构
- **签名URL**: 包含公网端点域名、bucket、object key、签名参数、过期时间的完整URL
- **配置加载器**: 负责从配置文件读取双端点配置并提供给不同服务组件

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100%的文件上传操作通过配置的内网端点完成
- **SC-002**: 100%的播放URL使用配置的公网端点生成
- **SC-003**: 用户能够在公网环境成功播放通过内网上传的视频
- **SC-004**: 现有单端点配置的系统能够不修改配置正常运行（向后兼容）
- **SC-005**: 配置错误时，系统在启动阶段提供明确的错误提示，定位问题时间不超过1分钟

## Assumptions

1. 运行录制服务的机器具有内网访问OSS的网络能力
2. VOD服务的用户通过公网访问系统
3. 使用的OSS服务（火山引擎TOS）支持内网和公网两种访问方式
4. 内网和公网端点访问的是同一个bucket中的相同文件
5. 签名算法与端点无关，只需替换URL中的域名部分

## Out of Scope

- 自动检测网络环境并选择端点
- 端点健康检查和自动故障转移
- 多Region或多Bucket的端点配置
- CDN加速配置
