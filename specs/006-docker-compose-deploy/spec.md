# Feature Specification: Docker Compose One-Click Deployment

**Feature Branch**: `006-docker-compose-deploy`
**Created**: 2026-01-07
**Status**: Draft
**Input**: User description: "让系统可以一键启动:录制 后端业务 前端，都基于docker，且数据库文件-config-oss key这类外部信息以及运行时的日志，保存在host中的文件夹中，且用docker映射到volume。用最佳实践一键启动系统的同时，让外部可以access和管理这些文件。"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - One-Click System Launch (Priority: P1)

As a system administrator, I want to launch the complete live recording system (recorder, backend API, frontend player) with a single command so that I can quickly deploy and start recording live streams without manual setup of individual components.

**Why this priority**: Core functionality - without this, the unified Docker deployment has no value. This is the fundamental use case that enables all other functionality.

**Independent Test**: Can be fully tested by running a single docker compose command and verifying all three services (recorder, backend, frontend) start successfully and are accessible.

**Acceptance Scenarios**:

1. **Given** Docker and Docker Compose are installed on the host machine, **When** the user runs `docker compose up -d`, **Then** all three services (recorder, backend API, frontend) start and become accessible within 2 minutes
2. **Given** the system is running, **When** the user accesses the frontend URL, **Then** the VOD player interface loads and can communicate with the backend API
3. **Given** the system is running with configured live room URLs, **When** a monitored stream goes live, **Then** the recorder service detects and begins recording

---

### User Story 2 - External Configuration Management (Priority: P1)

As a system administrator, I want all configuration files (config.ini, tos_credentials.ini, URL_config.ini) to be stored on the host filesystem and mounted into containers so that I can easily edit configurations without rebuilding images or entering containers.

**Why this priority**: Essential for practical usage - users must be able to configure which streams to record and set up credentials without Docker expertise.

**Independent Test**: Can be fully tested by modifying a config file on the host and verifying the change takes effect in the running containers (with or without restart depending on the service).

**Acceptance Scenarios**:

1. **Given** the system is running, **When** the user modifies `URL_config.ini` on the host, **Then** the recorder picks up the new stream URLs on its next monitoring cycle (within the configured loop time)
2. **Given** the user sets up new OSS credentials in `tos_credentials.ini` on the host, **When** the system restarts, **Then** the recorder uses the new credentials for uploads
3. **Given** an empty config directory exists, **When** the user runs docker compose up for the first time, **Then** default configuration files are created in the host config directory

---

### User Story 3 - Persistent Data Storage (Priority: P1)

As a system administrator, I want the database file and recorded videos to persist on the host filesystem so that data is not lost when containers are stopped, removed, or upgraded.

**Why this priority**: Critical for data integrity - losing recordings or metadata would make the system unusable for its core purpose.

**Independent Test**: Can be fully tested by running the system, creating some recordings, stopping and removing containers, then starting again and verifying all data is intact.

**Acceptance Scenarios**:

1. **Given** recordings have been made and stored in the database, **When** the user stops and removes all containers, then runs docker compose up again, **Then** all previous recording metadata is accessible in the VOD player
2. **Given** video files have been recorded locally, **When** the user browses the downloads folder on the host, **Then** all recorded video files are visible and playable
3. **Given** the database has grown over time, **When** the user backs up the data folder on the host, **Then** the backup contains the complete SQLite database

---

### User Story 4 - Log Accessibility (Priority: P2)

As a system administrator, I want runtime logs from all services to be stored on the host filesystem so that I can monitor system health, debug issues, and maintain historical records without accessing container internals.

**Why this priority**: Important for operations but not blocking core functionality - the system works without external log access, but troubleshooting becomes difficult.

**Independent Test**: Can be fully tested by running the system, triggering some operations, and verifying logs appear in the expected host directories.

**Acceptance Scenarios**:

1. **Given** the recorder is running and monitoring streams, **When** the user views the logs directory on the host, **Then** recorder logs are visible and contain recent activity
2. **Given** the backend API is handling requests, **When** the user views the logs directory on the host, **Then** API access logs are visible and contain request information
3. **Given** an error occurs in any service, **When** the user checks the appropriate log file on the host, **Then** the error details are logged with timestamps

---

### User Story 5 - Container Orchestration (Priority: P2)

As a system administrator, I want proper service dependencies and health checks so that services start in the correct order and the system recovers gracefully from failures.

**Why this priority**: Enhances reliability - without this, services might fail due to missing dependencies, requiring manual intervention.

**Independent Test**: Can be fully tested by starting the system and verifying services start in dependency order, then killing a service and verifying it restarts.

**Acceptance Scenarios**:

1. **Given** the docker compose file defines service dependencies, **When** docker compose up runs, **Then** the database/recorder starts before the backend, and the backend starts before the frontend can connect
2. **Given** a service crashes unexpectedly, **When** Docker detects the failure, **Then** the service is automatically restarted
3. **Given** the backend service is unhealthy, **When** the frontend attempts to connect, **Then** the frontend displays an appropriate connection error message

---

### User Story 6 - Production vs Development Modes (Priority: P3)

As a developer or administrator, I want the option to run in development mode (with hot-reload and debugging) or production mode (optimized and behind nginx) so that I can choose the appropriate configuration for my use case.

**Why this priority**: Nice-to-have for development workflow - production mode is essential for deployment, development mode improves developer experience.

**Independent Test**: Can be fully tested by running with different profile flags and verifying the appropriate services start with expected configurations.

**Acceptance Scenarios**:

1. **Given** the user wants production deployment, **When** running with the production profile, **Then** frontend is served through nginx and backend runs without debug mode
2. **Given** the user wants to develop locally, **When** running with the development profile, **Then** frontend has hot-reload enabled and backend has auto-restart on code changes

---

### Edge Cases

- What happens when the host config directory is empty on first startup? (System should create default configuration files)
- How does the system handle permission issues on mounted volumes? (Clear error messages should guide the user)
- What happens when disk space runs out on the host? (Recording should pause gracefully with logged warnings)
- How does the system behave when one service fails but others are healthy? (Dependent services should handle the failure gracefully)
- What happens when the user upgrades to a new version with schema changes? (Database migrations should run automatically)

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST provide a single docker-compose.yml file at the project root that defines all three services (recorder, backend, frontend)
- **FR-002**: System MUST mount the host's `./config` directory to provide configuration files to all services that need them
- **FR-003**: System MUST mount the host's `./data` directory for the SQLite database, shared between recorder and backend
- **FR-004**: System MUST mount the host's `./downloads` directory for recorded video files
- **FR-005**: System MUST mount the host's `./logs` directory for runtime logs from all services
- **FR-006**: System MUST include default configuration file templates that are created if the config directory is empty
- **FR-007**: System MUST define proper service dependencies so recorder starts before backend, and backend starts before frontend
- **FR-008**: System MUST configure automatic restart policies for all services
- **FR-009**: System MUST expose the frontend on a configurable port (default: 80 for production, 5173 for development)
- **FR-010**: System MUST expose the backend API on a configurable port (default: 8000)
- **FR-011**: System MUST support both development and production deployment profiles
- **FR-012**: System MUST include health checks for backend service to ensure API availability
- **FR-013**: System MUST pass environment variables for database path, config paths, and credential paths to services

### Key Entities

- **Service: Recorder**: The live stream recording service that monitors URLs and records streams to local/OSS storage
- **Service: Backend API**: FastAPI service providing VOD metadata and signed stream URLs
- **Service: Frontend**: TypeScript/Vite web application for VOD playback
- **Volume: config**: Host directory containing config.ini, URL_config.ini, and tos_credentials.ini
- **Volume: data**: Host directory containing recordings.db SQLite database
- **Volume: downloads**: Host directory for recorded video files organized by streamer/date
- **Volume: logs**: Host directory for runtime logs from all services

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Users can start the complete system with a single `docker compose up` command
- **SC-002**: All configuration files are accessible and editable from the host filesystem without entering containers
- **SC-003**: Data persists across container restarts, removals, and image upgrades
- **SC-004**: Logs are accessible from the host filesystem within 5 seconds of being generated
- **SC-005**: System recovers from service crashes within 30 seconds via automatic restart
- **SC-006**: New users can have the system running with default configuration in under 5 minutes (excluding Docker installation)
- **SC-007**: Configuration changes take effect without rebuilding Docker images

## Assumptions

- Docker and Docker Compose are already installed on the host machine
- The host has sufficient disk space for recordings and database growth
- The host operating system supports standard Docker volume mounts (Linux, macOS, or Windows with WSL2)
- Users have basic command-line knowledge for running docker compose commands
- Network ports 80, 5173, and 8000 are available or users can configure alternatives
- The existing Dockerfiles for each service are functional and only require orchestration
