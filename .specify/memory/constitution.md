<!--
  SYNC IMPACT REPORT
  ==================
  Version change: N/A (initial) → 1.0.0

  Modified principles: None (initial creation)

  Added sections:
    - Core Principles (5 principles)
    - Platform Integration Standards
    - Development Workflow
    - Governance

  Removed sections: None (initial creation)

  Templates requiring updates:
    - .specify/templates/plan-template.md: ✅ No changes needed (Constitution Check section is generic)
    - .specify/templates/spec-template.md: ✅ No changes needed (user stories compatible)
    - .specify/templates/tasks-template.md: ✅ No changes needed (phase structure compatible)
    - .specify/templates/commands/*.md: ✅ No command files exist

  Deferred TODOs: None
-->

# DouyinLiveRecorder Constitution

## Core Principles

### I. Recording Reliability

All recording operations MUST be fault-tolerant and data-preserving:

- FFmpeg subprocesses MUST be monitored with graceful shutdown handling
- Recording interruptions MUST NOT corrupt previously recorded segments
- The `ts` format is the RECOMMENDED output format for resilience against interruption
- Stream reconnection MUST be automatic when transient network failures occur
- All recording state changes MUST be logged with structured timestamps

**Rationale**: Users run this tool for extended periods to capture live content. Data loss
from crashes or interruptions is the primary failure mode to prevent.

### II. Platform Abstraction

Each supported platform MUST follow a consistent integration pattern:

- Stream fetching logic resides in `src/spider.py` as async functions named `get_{platform}_stream_data()`
- Stream URL extraction resides in `src/stream.py` with corresponding processor functions
- URL pattern matching for platform detection resides in `main.py`
- New platforms MUST NOT require changes to core recording logic
- Platform-specific cookies/auth MUST be configurable via `config/config.ini`

**Rationale**: Supporting 40+ platforms requires strict separation between platform-specific
parsing and universal recording infrastructure.

### III. Configuration Simplicity

User configuration MUST remain accessible to non-technical users:

- `config/URL_config.ini` is the single source for monitored live rooms (one URL per line)
- `config/config.ini` is the single source for all runtime settings
- Defaults MUST work without modification for basic use cases
- Quality overrides use inline syntax: `quality,URL` (e.g., `超清,https://...`)
- Commenting a URL with `#` MUST immediately stop monitoring that room

**Rationale**: The primary user base expects simple text file configuration without
needing to understand Python or complex configuration formats.

### IV. Async-First Architecture

All network operations MUST use asynchronous patterns:

- Platform spider functions MUST be async (use `asyncio.run()` for synchronous entry points)
- HTTP clients MUST use the `src/http_clients/` abstractions (httpx-based)
- Blocking I/O in the main recording loop MUST be avoided
- Thread management for concurrent recordings MUST use proper synchronization

**Rationale**: Monitoring dozens of live rooms simultaneously requires non-blocking I/O
to maintain responsiveness and reduce resource consumption.

### V. Observable Operations

All significant operations MUST produce observable output:

- Use `loguru` for all logging (configured in `src/logger.py`)
- Live status changes MUST trigger configurable notifications (msg_push.py)
- Recording start/stop events MUST be logged with room URL, anchor name, and timestamp
- Errors MUST include sufficient context for debugging (platform, URL, error type)
- The `trace_error_decorator` MUST wrap functions that can fail silently

**Rationale**: Long-running recording sessions require clear visibility into what the
tool is doing, especially when running headless or in containers.

## Platform Integration Standards

When adding support for a new streaming platform:

1. **Spider Function**: Add `async def get_{platform}_stream_data()` in `src/spider.py`
   - MUST return consistent data structure with live status and stream URLs
   - MUST handle platform-specific authentication if required

2. **Stream Processor**: Add URL extraction in `src/stream.py` if stream data requires transformation

3. **URL Detection**: Add pattern matching in `main.py` to route URLs to correct spider

4. **Configuration**: Add cookie/auth fields to `config/config.ini` if platform requires credentials

5. **Testing**: Add entry to `demo.py` for manual verification

6. **Documentation**: Update README.md platform support list

## Development Workflow

### Code Quality Gates

- All spider functions MUST be manually testable via `demo.py` before merge
- FFmpeg command construction MUST be validated against known-working parameters
- Configuration parsing MUST fail fast with clear error messages for invalid input

### Dependency Management

- Python >= 3.10 is REQUIRED
- FFmpeg MUST be available in PATH (bundled on Windows, system-installed elsewhere)
- Node.js is REQUIRED for JavaScript-based signature algorithms
- Use `uv` for dependency management (preferred) or `pip` with `requirements.txt`

### Container Support

- Docker builds MUST include all runtime dependencies (FFmpeg, Node.js)
- Volume mounts for `config/` and `downloads/` MUST be documented
- Container interruption warnings MUST be prominent (use `ts` format)

## Governance

This constitution defines non-negotiable development standards for DouyinLiveRecorder.
All contributions MUST comply with these principles.

### Amendment Procedure

1. Propose changes via GitHub issue with rationale
2. Changes require maintainer approval
3. Version increment follows semantic versioning:
   - MAJOR: Principle removal or incompatible redefinition
   - MINOR: New principle or significant expansion
   - PATCH: Clarification or wording improvement

### Compliance Review

- Pull requests SHOULD reference applicable principles when touching core systems
- Platform additions MUST follow Platform Integration Standards checklist
- Recording reliability changes MUST include test evidence of data preservation

**Version**: 1.0.0 | **Ratified**: 2026-01-05 | **Last Amended**: 2026-01-05
