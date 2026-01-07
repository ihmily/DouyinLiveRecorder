#!/bin/bash
# DouyinLiveRecorder - Docker Entrypoint Script
# This script runs before the main application starts

set -e

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${GREEN}[Entrypoint] Starting DouyinLiveRecorder...${NC}"

# =============================================================================
# Step 1: Create required directories
# =============================================================================
echo -e "${GREEN}[Entrypoint] Creating required directories...${NC}"

mkdir -p /app/data
mkdir -p /app/downloads
mkdir -p /app/logs
mkdir -p /app/config

# =============================================================================
# Step 2: Copy default configuration files if missing
# =============================================================================
echo -e "${GREEN}[Entrypoint] Checking configuration files...${NC}"

# Copy config.ini if not exists
if [ ! -f /app/config/config.ini ]; then
    if [ -f /app/backup_config/config.ini ]; then
        cp /app/backup_config/config.ini /app/config/config.ini
        echo -e "${YELLOW}[Entrypoint] Created config.ini from backup${NC}"
    else
        echo -e "${RED}[Entrypoint] Warning: No config.ini found${NC}"
    fi
fi

# Copy URL_config.ini if not exists
if [ ! -f /app/config/URL_config.ini ]; then
    if [ -f /app/backup_config/URL_config.ini ]; then
        cp /app/backup_config/URL_config.ini /app/config/URL_config.ini
        echo -e "${YELLOW}[Entrypoint] Created URL_config.ini from backup${NC}"
    else
        # Create empty URL config
        touch /app/config/URL_config.ini
        echo -e "${YELLOW}[Entrypoint] Created empty URL_config.ini${NC}"
    fi
fi

# Copy tos_credentials.ini if not exists
if [ ! -f /app/config/tos_credentials.ini ]; then
    if [ -f /app/config/tos_credentials.ini.example ]; then
        cp /app/config/tos_credentials.ini.example /app/config/tos_credentials.ini
        echo -e "${YELLOW}[Entrypoint] Created tos_credentials.ini from example${NC}"
    fi
fi

# =============================================================================
# Step 3: Validate TOS connectivity (with timeout)
# =============================================================================
echo -e "${GREEN}[Entrypoint] Validating TOS connectivity...${NC}"

# Run TOS validation with 10-second timeout
# Continue even if validation fails (graceful degradation)
timeout 10 uv run python -c "
try:
    from src.tos_validator import validate_and_log
    validate_and_log()
except ImportError:
    print('[Entrypoint] TOS validator not available - skipping validation')
except Exception as e:
    print(f'[Entrypoint] TOS validation error: {e}')
" 2>/dev/null || echo -e "${YELLOW}[Entrypoint] TOS validation skipped or failed - continuing...${NC}"

# =============================================================================
# Step 4: Start the main application
# =============================================================================
echo -e "${GREEN}[Entrypoint] Starting main application...${NC}"

# Execute the main command (passed as arguments)
exec "$@"
