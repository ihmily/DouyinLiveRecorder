# VOD Player Makefile
# Provides one-command development and production workflows
# Uses uv for Python environment management

.PHONY: help install install-backend install-frontend dev dev-backend dev-frontend \
        build clean migrate docker-up docker-down docker-build check health

# Default target
help:
	@echo "VOD Player - Development Commands"
	@echo ""
	@echo "Setup:"
	@echo "  make install          Install all dependencies (backend + frontend)"
	@echo "  make install-backend  Install backend dependencies only (via uv)"
	@echo "  make install-frontend Install frontend dependencies only (via npm)"
	@echo "  make migrate          Run database migrations"
	@echo ""
	@echo "Development:"
	@echo "  make dev              Start both backend and frontend"
	@echo "  make dev-backend      Start backend development server"
	@echo "  make dev-frontend     Start frontend development server"
	@echo ""
	@echo "Production:"
	@echo "  make build            Build frontend for production"
	@echo "  make docker-build     Build Docker images"
	@echo "  make docker-up        Start with Docker Compose"
	@echo "  make docker-down      Stop Docker Compose services"
	@echo ""
	@echo "Utilities:"
	@echo "  make check            Check prerequisites (uv, Node, FFmpeg)"
	@echo "  make health           Check if services are running"
	@echo "  make clean            Clean build artifacts"

# =============================================================================
# Prerequisites Check
# =============================================================================

check:
	@echo "Checking prerequisites..."
	@echo ""
	@echo -n "uv: " && uv --version || echo "NOT FOUND - install with: curl -LsSf https://astral.sh/uv/install.sh | sh"
	@echo -n "Python: " && python3 --version || echo "NOT FOUND"
	@echo -n "Node.js: " && node --version || echo "NOT FOUND"
	@echo -n "npm: " && npm --version || echo "NOT FOUND"
	@echo -n "FFmpeg: " && ffmpeg -version 2>/dev/null | head -1 || echo "NOT FOUND"
	@echo -n "FFprobe: " && ffprobe -version 2>/dev/null | head -1 || echo "NOT FOUND"
	@echo ""
	@echo "Config files:"
	@test -f ../config/config.ini && echo "  config/config.ini: OK" || echo "  config/config.ini: MISSING"
	@test -f ../config/tos_credentials.ini && echo "  config/tos_credentials.ini: OK" || echo "  config/tos_credentials.ini: MISSING (optional)"

# =============================================================================
# Installation
# =============================================================================

install: install-backend install-frontend
	@echo ""
	@echo "All dependencies installed!"
	@echo "Run 'make dev' to start development servers."

install-backend:
	@echo "Installing backend dependencies with uv..."
	cd backend && uv sync

install-frontend:
	@echo "Installing frontend dependencies with npm..."
	cd frontend && npm install

# =============================================================================
# Database Migration
# =============================================================================

migrate:
	@echo "Running database migration..."
	cd .. && uv run python migrations/001_add_vod_fields.py

# =============================================================================
# Development
# =============================================================================

# Start both servers (uses background processes)
# For better experience, use 'make dev-backend' and 'make dev-frontend' in separate terminals
dev:
	@echo "Starting VOD Player development servers..."
	@echo ""
	@echo "Backend:  http://localhost:8000"
	@echo "Frontend: http://localhost:5173"
	@echo "API Docs: http://localhost:8000/docs"
	@echo ""
	@echo "Press Ctrl+C to stop all servers"
	@echo ""
	@trap 'kill 0' EXIT; \
		(cd backend && uv run uvicorn app.main:app --host 0.0.0.0 --reload --port 8000) & \
		(cd frontend && npm run dev) & \
		wait

dev-backend:
	@echo "Starting backend development server..."
	@echo "API:  http://localhost:8000"
	@echo "Docs: http://localhost:8000/docs"
	cd backend && uv run uvicorn app.main:app --host 0.0.0.0 --reload --port 8000

dev-frontend:
	@echo "Starting frontend development server..."
	@echo "URL: http://localhost:5173"
	cd frontend && npm run dev

# =============================================================================
# Production Build
# =============================================================================

build:
	@echo "Building frontend for production..."
	cd frontend && npm run build
	@echo ""
	@echo "Build complete! Output in frontend/dist/"

# =============================================================================
# Docker
# =============================================================================

docker-build:
	@echo "Building Docker images..."
	docker-compose build

docker-up:
	@echo "Starting Docker Compose services..."
	docker-compose up -d
	@echo ""
	@echo "Services started:"
	@echo "  Backend:  http://localhost:8000"
	@echo "  Frontend: http://localhost:5173"

docker-down:
	@echo "Stopping Docker Compose services..."
	docker-compose down

docker-logs:
	docker-compose logs -f

# =============================================================================
# Health Check
# =============================================================================

health:
	@echo "Checking service health..."
	@echo ""
	@echo -n "Backend (http://localhost:8000/health): "
	@curl -s http://localhost:8000/health 2>/dev/null || echo "NOT RUNNING"
	@echo ""
	@echo -n "Frontend (http://localhost:5173): "
	@curl -s -o /dev/null -w "%{http_code}" http://localhost:5173 2>/dev/null || echo "NOT RUNNING"
	@echo ""

# =============================================================================
# Cleanup
# =============================================================================

clean:
	@echo "Cleaning build artifacts..."
	rm -rf frontend/dist
	rm -rf frontend/node_modules/.cache
	rm -rf backend/__pycache__
	rm -rf backend/**/__pycache__
	rm -rf backend/.venv
	@echo "Clean complete!"
