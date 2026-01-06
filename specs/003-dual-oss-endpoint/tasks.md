# Tasks: VOD/OSS双端点配置

**Input**: Design documents from `/specs/003-dual-oss-endpoint/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

**Tests**: No tests requested in specification - manual verification only per quickstart.md

**Organization**: Tasks organized by user story for independent implementation and testing.

## Format: `[ID] [P?] [Story?] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2, US3)
- Include exact file paths in descriptions

## Path Conventions

This feature modifies the VOD player backend:
- **Backend**: `vod-player/backend/app/`
- **Config**: `config/tos_credentials.ini` (user-managed)

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: No setup required - feature modifies existing infrastructure

This is a minimal change feature (~30 lines). No new project structure or dependencies needed.

- [ ] T001 Verify existing file structure in vod-player/backend/app/config.py
- [ ] T002 Verify existing file structure in vod-player/backend/app/services/tos_sign.py

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: No foundational work required - feature builds on existing infrastructure

This feature extends existing Settings class and TOS client - no blocking prerequisites.

**Checkpoint**: Ready for user story implementation

---

## Phase 3: User Story 1 - 内网上传视频文件 (Priority: P1) 🎯 MVP

**Goal**: 确保录制管道通过内网端点上传文件到OSS（代码已正确，仅需配置值修正说明）

**Independent Test**: 执行 `uv run main.py` 录制直播，验证上传通过内网端点

### Implementation for User Story 1

> **NOTE**: 代码逻辑已正确实现（使用 `endpoint` 配置项上传）。此用户故事主要是验证和文档说明。

- [ ] T003 [US1] Verify upload code uses endpoint config in src/storage/tos_uploader.py:69-74
- [ ] T004 [US1] Verify proxy clearing logic in src/storage/tos_uploader.py:65-67
- [ ] T005 [US1] Document correct endpoint configuration values (内网 = *.ivolces.com) in quickstart.md

**Checkpoint**: 上传功能验证完成，配置说明已更新

---

## Phase 4: User Story 2 - 生成公网可访问的播放URL (Priority: P1)

**Goal**: VOD服务使用公网端点生成限时签名URL

**Independent Test**: 调用 `/api/segments/{segment_id}/play`，验证返回的URL包含公网域名 (*.volces.com)

### Implementation for User Story 2

- [ ] T006 [P] [US2] Add tos_s3_endpoint field to Settings class in vod-player/backend/app/config.py
- [ ] T007 [P] [US2] Update load_tos_credentials() to read s3_endpoint in vod-player/backend/app/config.py
- [ ] T008 [US2] Update get_settings() with s3_endpoint population and fallback logic in vod-player/backend/app/config.py
- [ ] T009 [US2] Modify get_tos_client() to use tos_s3_endpoint in vod-player/backend/app/services/tos_sign.py
- [ ] T010 [US2] Add warning log when s3_endpoint fallback is used in vod-player/backend/app/services/tos_sign.py

**Checkpoint**: VOD服务可生成公网URL，可独立测试

---

## Phase 5: User Story 3 - 配置管理 (Priority: P2)

**Goal**: 支持管理员分别配置内网/公网端点，向后兼容单端点配置

**Independent Test**: 修改配置文件端点设置，重启服务验证使用正确端点

### Implementation for User Story 3

- [ ] T011 [US3] Add endpoint configuration validation and logging on startup in vod-player/backend/app/config.py
- [ ] T012 [US3] Document configuration options and backward compatibility in specs/003-dual-oss-endpoint/quickstart.md

**Checkpoint**: 配置管理完成，文档更新

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Final validation and documentation

- [ ] T013 Run quickstart.md manual verification (upload via 内网, URL via 公网)
- [ ] T014 Verify backward compatibility with s3_endpoint not configured
- [ ] T015 Update plan.md to mark tasks.md as generated

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: File verification only - immediate start
- **Phase 2 (Foundational)**: N/A for this feature
- **Phase 3 (US1)**: Verification and documentation - no code changes
- **Phase 4 (US2)**: Core implementation - can start after Phase 1
- **Phase 5 (US3)**: Depends on Phase 4 completion (uses the new config field)
- **Phase 6 (Polish)**: Depends on Phase 4 and 5

### User Story Dependencies

- **User Story 1 (P1)**: Independent - code already correct, verification only
- **User Story 2 (P1)**: Independent - core feature implementation
- **User Story 3 (P2)**: Depends on US2 config field being available

### Within Each User Story

- T006 and T007 can run in parallel (different parts of same file, but no conflicts)
- T008 depends on T006, T007 (uses the new field and loaded value)
- T009 depends on T008 (needs settings populated)
- T010 can run with T009 (same file, related logic)

### Parallel Opportunities

Within Phase 4 (US2):
```bash
# Launch together (different logical sections of config.py):
Task: T006 "Add tos_s3_endpoint field to Settings class"
Task: T007 "Update load_tos_credentials() to read s3_endpoint"
```

---

## Parallel Example: User Story 2 Implementation

```bash
# Step 1: Launch config model changes in parallel
Task: "T006 Add tos_s3_endpoint field to Settings class in vod-player/backend/app/config.py"
Task: "T007 Update load_tos_credentials() to read s3_endpoint in vod-player/backend/app/config.py"

# Step 2: After T006/T007, update settings population
Task: "T008 Update get_settings() with s3_endpoint population and fallback logic"

# Step 3: After T008, update signing service
Task: "T009 Modify get_tos_client() to use tos_s3_endpoint in vod-player/backend/app/services/tos_sign.py"
Task: "T010 Add warning log when s3_endpoint fallback is used in vod-player/backend/app/services/tos_sign.py"
```

---

## Implementation Strategy

### MVP First (User Stories 1 & 2)

1. Skip Phase 1-2 (no setup needed)
2. Complete Phase 3 (US1): Verify existing upload logic
3. Complete Phase 4 (US2): Implement public endpoint URL generation
4. **STOP and VALIDATE**: Test both upload and URL generation
5. Deploy if ready

### Recommended Execution Order

1. T001-T002: Quick verification (5 min)
2. T003-T005: US1 verification (10 min)
3. T006-T010: US2 implementation (20 min) - **CORE CHANGES**
4. T011-T012: US3 config management (10 min)
5. T013-T015: Final validation (15 min)

**Total Estimated Scope**: ~25-30 lines of code changes across 2 files

---

## Notes

- [P] tasks = different files or non-conflicting sections
- [Story] label maps task to specific user story for traceability
- US1 and US2 are both P1 priority but US1 is verification only
- Main implementation work is in US2 (T006-T010)
- This is a minimal change feature - 2 files, ~30 lines
- Configuration VALUE changes are user responsibility (documented in quickstart.md)
