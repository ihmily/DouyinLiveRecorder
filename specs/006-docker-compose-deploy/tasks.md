# Tasks: Docker Compose One-Click Deployment

**Input**: Design documents from `/specs/006-docker-compose-deploy/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, quickstart.md

**Tests**: Manual verification via docker compose commands (no automated tests)

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Path Conventions

This feature uses:
- Root level: `docker-compose.yml`, `Makefile`, `.env.example`
- Scripts: `scripts/docker-entrypoint.sh`
- Source: `src/tos_validator.py`
- Config: `config/` (existing)
- VOD Player: `vod-player/` (existing structure)

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Create Makefile as unified entry point and prepare project structure

- [x] T001 Create Makefile at project root with docker compose commands in Makefile
- [x] T002 [P] Create .env.example with default port configurations in .env.example
- [x] T003 [P] Create scripts directory structure in scripts/

**Checkpoint**: Makefile commands ready for testing after docker-compose.yml is created

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Create the core docker-compose.yml that all stories depend on

**⚠️ CRITICAL**: User stories cannot be fully tested until this phase is complete

- [x] T004 Create unified docker-compose.yml with recorder service definition in docker-compose.yml
- [x] T005 Add backend service definition to docker-compose.yml in docker-compose.yml
- [x] T006 Add frontend-dev service definition to docker-compose.yml in docker-compose.yml
- [x] T007 [P] Create docker-entrypoint.sh script for recorder service in scripts/docker-entrypoint.sh
- [x] T008 Update recorder Dockerfile to use entrypoint script in Dockerfile

**Checkpoint**: Basic docker compose up should start all three services (without health checks or volume optimization)

---

## Phase 3: User Story 1 - One-Click System Launch (Priority: P1) 🎯 MVP

**Goal**: Users can start the complete system with `docker compose up` or `make up`

**Independent Test**: Run `make up` and verify all three services start within 2 minutes

### Implementation for User Story 1

- [x] T009 [US1] Add service network configuration to connect all services in docker-compose.yml
- [x] T010 [US1] Configure backend to connect to recorder's data volume in docker-compose.yml
- [x] T011 [US1] Configure frontend to connect to backend API URL via environment in docker-compose.yml
- [x] T012 [US1] Add `make up`, `make down`, `make restart` targets to Makefile in Makefile
- [x] T013 [US1] Add `make logs` and `make ps` targets for monitoring in Makefile
- [ ] T014 [US1] Verify all three services start and communicate via `make up`

**Checkpoint**: `make up` starts recorder, backend, and frontend; frontend can display VOD player

---

## Phase 4: User Story 2 - External Configuration Management (Priority: P1)

**Goal**: Config files on host are mounted and editable without entering containers

**Independent Test**: Modify config/URL_config.ini on host, verify recorder uses new URLs after restart

### Implementation for User Story 2

- [x] T015 [US2] Configure ./config volume mount for recorder service in docker-compose.yml
- [x] T016 [US2] Configure ./config volume mount for backend service in docker-compose.yml
- [x] T017 [US2] Add default config file copy logic to docker-entrypoint.sh in scripts/docker-entrypoint.sh
- [x] T018 [US2] Add environment variables for config paths in docker-compose.yml
- [x] T019 [US2] Add `make config-init` target to create default configs in Makefile
- [ ] T020 [US2] Verify config changes on host are reflected in containers

**Checkpoint**: Editing config/config.ini on host affects running recorder after restart

---

## Phase 5: User Story 3 - Persistent Data Storage (Priority: P1)

**Goal**: Database and recordings persist across container restarts

**Independent Test**: Create recording, run `make down && make up`, verify recording still exists in VOD player

### Implementation for User Story 3

- [x] T021 [US3] Configure ./data volume mount for recorder service in docker-compose.yml
- [x] T022 [US3] Configure ./data volume mount for backend service in docker-compose.yml
- [x] T023 [US3] Configure ./downloads volume mount for recorder service in docker-compose.yml
- [x] T024 [US3] Add data directory creation to docker-entrypoint.sh in scripts/docker-entrypoint.sh
- [ ] T025 [US3] Verify database persists after `make down && make up`

**Checkpoint**: recordings.db and downloaded videos persist across container lifecycle

---

## Phase 6: User Story 7 - Runtime Prerequisite Validation (Priority: P1)

**Goal**: TOS credentials validated on startup with clear log messages

**Independent Test**: Start with invalid TOS credentials, verify error logged; start with valid credentials, verify "TOS connectivity verified" logged

### Implementation for User Story 7

- [x] T026 [US7] Create TOS validator module in src/tos_validator.py
- [x] T027 [US7] Implement credential file parsing in tos_validator.py in src/tos_validator.py
- [x] T028 [US7] Implement HeadBucket check for bucket access in src/tos_validator.py
- [x] T029 [US7] Implement PutObject/GetObject/DeleteObject connectivity test in src/tos_validator.py
- [x] T030 [US7] Implement ValidationResult enum and logging in src/tos_validator.py
- [x] T031 [US7] Add TOS validation call to docker-entrypoint.sh with 10s timeout in scripts/docker-entrypoint.sh
- [x] T032 [US7] Add `make check-tos` target for manual validation testing in Makefile
- [ ] T033 [US7] Verify validation logs correctly for all scenarios (missing, invalid, network error, success)

**Checkpoint**: TOS validation runs on startup; OSS gracefully disabled if validation fails

---

## Phase 7: User Story 4 - Log Accessibility (Priority: P2)

**Goal**: Service logs accessible on host filesystem

**Independent Test**: Run `make up`, check logs/recorder/ directory contains log files

### Implementation for User Story 4

- [x] T034 [US4] Configure ./logs volume mount for recorder service in docker-compose.yml
- [x] T035 [US4] Configure ./logs volume mount for backend service in docker-compose.yml
- [x] T036 [US4] Configure ./logs volume mount for frontend service in docker-compose.yml
- [x] T037 [US4] Add log directory creation to docker-entrypoint.sh in scripts/docker-entrypoint.sh
- [x] T038 [US4] Configure loguru to write to mounted logs directory for recorder
- [x] T039 [US4] Add `make logs-tail` target for live log viewing in Makefile
- [ ] T040 [US4] Verify logs appear in ./logs/ subdirectories on host

**Checkpoint**: Logs from all services accessible in ./logs/{recorder,backend,frontend}/

---

## Phase 8: User Story 5 - Container Orchestration (Priority: P2)

**Goal**: Services start in correct order with health checks and auto-restart

**Independent Test**: Kill recorder container, verify it restarts automatically within 30 seconds

### Implementation for User Story 5

- [x] T041 [US5] Add healthcheck for recorder service (database file exists) in docker-compose.yml
- [x] T042 [US5] Add healthcheck for backend service (curl /health endpoint) in docker-compose.yml
- [x] T043 [US5] Configure depends_on with service_healthy condition for backend in docker-compose.yml
- [x] T044 [US5] Configure depends_on with service_healthy condition for frontend in docker-compose.yml
- [x] T045 [US5] Add restart: unless-stopped policy to all services in docker-compose.yml
- [x] T046 [US5] Add /health endpoint to backend if not exists in vod-player/backend/app/main.py
- [ ] T047 [US5] Verify service startup order: recorder → backend → frontend
- [ ] T048 [US5] Verify auto-restart by killing a service with `docker kill`

**Checkpoint**: Services start in dependency order; crashed services restart automatically

---

## Phase 9: User Story 6 - Production vs Development Modes (Priority: P3)

**Goal**: Support both development (hot-reload) and production (nginx) deployment

**Independent Test**: Run `make up-prod`, verify nginx serves frontend on port 80

### Implementation for User Story 6

- [x] T049 [US6] Add nginx service with production profile in docker-compose.yml
- [x] T050 [US6] Configure nginx to serve frontend static files and proxy to backend in docker-compose.yml
- [x] T051 [US6] Add profiles configuration to frontend-dev (dev profile) in docker-compose.yml
- [x] T052 [US6] Update vod-player/nginx.conf for production reverse proxy in vod-player/nginx.conf
- [x] T053 [US6] Add `make up-dev` and `make up-prod` targets in Makefile
- [x] T054 [US6] Add `make build-frontend` target for production frontend build in Makefile
- [ ] T055 [US6] Verify development mode starts frontend with hot-reload on port 5173
- [ ] T056 [US6] Verify production mode starts nginx on port 80 serving static frontend

**Checkpoint**: `make up-dev` for development, `make up-prod` for production deployment

---

## Phase 10: Polish & Cross-Cutting Concerns

**Purpose**: Documentation and final integration

- [x] T057 [P] Update README.md with Docker deployment instructions in README.md
- [x] T058 [P] Add inline comments to docker-compose.yml explaining configuration in docker-compose.yml
- [x] T059 [P] Add inline comments to Makefile explaining each target in Makefile
- [ ] T060 Run quickstart.md validation - verify all documented commands work
- [ ] T061 Test full workflow: `make config-init && make up && make check-tos && make logs-tail`

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: No dependencies - can start immediately
- **Phase 2 (Foundational)**: Depends on Phase 1 - BLOCKS all user stories
- **Phases 3-6 (P1 Stories)**: Depend on Phase 2 completion
  - US1 (One-Click Launch) - foundation for all others
  - US2 (Config Management) - can parallel with US3
  - US3 (Data Persistence) - can parallel with US2
  - US7 (TOS Validation) - depends on US2 for config mounts
- **Phases 7-8 (P2 Stories)**: Depend on Phase 2; can parallel with P1 stories if needed
  - US4 (Logs) - can parallel with US5
  - US5 (Orchestration) - can parallel with US4
- **Phase 9 (P3 Story)**: Depends on Phase 2; can parallel with P1/P2 stories
  - US6 (Prod/Dev Modes) - independent of other stories
- **Phase 10 (Polish)**: Depends on all desired user stories being complete

### User Story Dependencies

```
Phase 1 (Setup)
    │
    ▼
Phase 2 (Foundational: docker-compose.yml base)
    │
    ├──────────────────────────────────────────┐
    │                                          │
    ▼                                          ▼
US1 (One-Click Launch)                    US6 (Prod/Dev Modes)
    │                                          │
    ├────────────┬────────────┐                │
    ▼            ▼            ▼                │
US2 (Config) US3 (Data)  US4 (Logs)           │
    │            │            │                │
    └────────────┴────────────┘                │
              │                                │
              ▼                                │
        US7 (TOS Validation)                   │
              │                                │
              ▼                                │
        US5 (Orchestration)                    │
              │                                │
              └────────────────────────────────┘
                            │
                            ▼
                    Phase 10 (Polish)
```

### Within Each User Story

- Configuration changes in docker-compose.yml before Makefile targets
- Entrypoint script updates before Dockerfile changes
- Implementation before verification tasks

### Parallel Opportunities

**Within Phase 1**:
- T002 (.env.example) and T003 (scripts dir) can run in parallel

**Within Phase 2**:
- T005, T006, T007 can potentially run in parallel after T004

**Across User Stories (after Phase 2)**:
- US2 (Config) and US3 (Data) can run in parallel
- US4 (Logs) and US5 (Orchestration) can run in parallel
- US6 (Prod/Dev) can run in parallel with all other stories

**Within Phase 10**:
- T057, T058, T059 can run in parallel

---

## Parallel Example: Phase 2 and Early User Stories

```bash
# After T004 (base docker-compose.yml), launch in parallel:
Task: "Add backend service definition to docker-compose.yml" (T005)
Task: "Add frontend-dev service definition to docker-compose.yml" (T006)
Task: "Create docker-entrypoint.sh script for recorder service" (T007)

# After Phase 2, launch US2 and US3 in parallel:
Task: "Configure ./config volume mount for recorder service" (T015)
Task: "Configure ./data volume mount for recorder service" (T021)
```

---

## Implementation Strategy

### MVP First (User Stories 1-3 + 7)

1. Complete Phase 1: Setup (Makefile)
2. Complete Phase 2: Foundational (docker-compose.yml base)
3. Complete Phase 3: US1 - One-Click Launch
4. Complete Phase 4: US2 - Config Management
5. Complete Phase 5: US3 - Data Persistence
6. Complete Phase 6: US7 - TOS Validation
7. **STOP and VALIDATE**: Run `make up`, verify system works end-to-end
8. Deploy/demo if ready

### Incremental Delivery

1. Setup + Foundational → Basic structure ready
2. Add US1 → `docker compose up` works → Demo
3. Add US2 + US3 → Config and data persist → Demo
4. Add US7 → TOS validation on startup → Demo
5. Add US4 + US5 → Logs accessible, health checks work → Demo
6. Add US6 → Production mode available → Final Demo

### Makefile Targets Summary

| Target | Description |
|--------|-------------|
| `make up` | Start all services (development mode) |
| `make down` | Stop all services |
| `make restart` | Restart all services |
| `make logs` | View service logs |
| `make logs-tail` | Follow logs in real-time |
| `make ps` | Show running services |
| `make config-init` | Initialize default config files |
| `make check-tos` | Validate TOS connectivity |
| `make up-dev` | Start in development mode |
| `make up-prod` | Start in production mode |
| `make build-frontend` | Build frontend for production |

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- Each user story should be independently completable and testable
- Commit after each task or logical group
- Stop at any checkpoint to validate story independently
- Avoid: vague tasks, same file conflicts, cross-story dependencies that break independence
- User requested Makefile as unified entry point - ensure all docker commands go through Makefile
