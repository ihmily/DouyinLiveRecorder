# DouyinLiveRecorder - Docker Compose Makefile
# Unified entry point for all Docker operations

.PHONY: help up down restart logs logs-tail ps build clean config-init check-tos up-dev up-prod build-frontend

# Default target
.DEFAULT_GOAL := help

# Colors for output
BLUE := \033[34m
GREEN := \033[32m
YELLOW := \033[33m
RED := \033[31m
NC := \033[0m # No Color

help: ## Show this help message
	@echo "$(BLUE)DouyinLiveRecorder - Docker Compose Commands$(NC)"
	@echo ""
	@echo "$(GREEN)Usage:$(NC) make [target]"
	@echo ""
	@echo "$(YELLOW)Targets:$(NC)"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  $(GREEN)%-15s$(NC) %s\n", $$1, $$2}'

# =============================================================================
# Core Operations
# =============================================================================

up: ## Start all services (development mode)
	docker compose up -d

down: ## Stop all services
	docker compose down

restart: ## Restart all services
	docker compose restart

build: ## Build all Docker images
	docker compose build

clean: ## Stop services and remove volumes
	docker compose down -v --remove-orphans

# =============================================================================
# Monitoring
# =============================================================================

logs: ## View all service logs
	docker compose logs

logs-tail: ## Follow logs in real-time
	docker compose logs -f

ps: ## Show running services status
	docker compose ps

# =============================================================================
# Configuration
# =============================================================================

config-init: ## Initialize default configuration files
	@echo "$(BLUE)Initializing configuration files...$(NC)"
	@mkdir -p config data downloads logs/recorder logs/backend logs/frontend
	@if [ ! -f config/config.ini ] && [ -f backup_config/config.ini ]; then \
		cp backup_config/config.ini config/config.ini; \
		echo "$(GREEN)Created config/config.ini from backup$(NC)"; \
	fi
	@if [ ! -f config/URL_config.ini ] && [ -f backup_config/URL_config.ini ]; then \
		cp backup_config/URL_config.ini config/URL_config.ini; \
		echo "$(GREEN)Created config/URL_config.ini from backup$(NC)"; \
	fi
	@if [ ! -f config/tos_credentials.ini ] && [ -f config/tos_credentials.ini.example ]; then \
		cp config/tos_credentials.ini.example config/tos_credentials.ini; \
		echo "$(GREEN)Created config/tos_credentials.ini from example$(NC)"; \
	fi
	@echo "$(GREEN)Configuration initialized. Edit files in ./config/ as needed.$(NC)"

check-tos: ## Validate TOS/OSS connectivity
	@echo "$(BLUE)Validating TOS connectivity...$(NC)"
	@docker compose exec recorder python -c "from src.tos_validator import validate_and_log; validate_and_log()" 2>/dev/null || \
		python -c "from src.tos_validator import validate_and_log; validate_and_log()" 2>/dev/null || \
		echo "$(YELLOW)TOS validation requires running containers or local Python environment$(NC)"

# =============================================================================
# Development vs Production
# =============================================================================

up-dev: ## Start in development mode (hot-reload frontend)
	docker compose --profile dev up -d

up-prod: ## Start in production mode (nginx + static frontend)
	@echo "$(BLUE)Building frontend for production...$(NC)"
	$(MAKE) build-frontend
	docker compose --profile production up -d

build-frontend: ## Build frontend static files for production
	@echo "$(BLUE)Building frontend...$(NC)"
	cd vod-player/frontend && npm install && npm run build
	@echo "$(GREEN)Frontend built to vod-player/frontend/dist/$(NC)"

# =============================================================================
# Shortcuts
# =============================================================================

recorder-logs: ## View recorder service logs only
	docker compose logs -f recorder

backend-logs: ## View backend service logs only
	docker compose logs -f backend

frontend-logs: ## View frontend service logs only
	docker compose logs -f frontend

shell-recorder: ## Open shell in recorder container
	docker compose exec recorder bash

shell-backend: ## Open shell in backend container
	docker compose exec backend bash
