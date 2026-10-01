.PHONY: help install test api ui up down

.DEFAULT_GOAL := help

# Calendar dev tasks. Run from backend/, or from the repo root via the root Makefile.
# API http://127.0.0.1:8000   UI http://127.0.0.1:5173

help: ## Show this help message
	@echo install  Install backend and frontend dependencies
	@echo test     Run backend tests
	@echo api      Start the API on :8000
	@echo ui       Start the frontend on :5173
	@echo up       Start the API and the frontend
	@echo down     Stop the API and the frontend

install: ## Install backend and frontend dependencies
	uv sync
	npm install --prefix ../frontend

test: ## Run backend tests
	uv run pytest

api: ## Start the API on :8000
	uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

ui: ## Start the frontend on :5173
	npm run dev --prefix ../frontend

ifeq ($(OS),Windows_NT)
up: ## Start the API (:8000) and the frontend (:5173)
	powershell -NoProfile -ExecutionPolicy Bypass -File scripts/dev.ps1 up

down: ## Stop the API and the frontend
	powershell -NoProfile -ExecutionPolicy Bypass -File scripts/dev.ps1 down
else
up: ## Start the API (:8000) and the frontend (:5173)
	@echo "API  http://127.0.0.1:8000"
	@echo "UI   http://127.0.0.1:5173"
	@trap 'kill 0' EXIT INT TERM; \
		uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000 & \
		npm run dev --prefix ../frontend & \
		wait

down: ## Stop the API and the frontend
	-pkill -f "uvicorn app.main:app"
	-pkill -f "vite"
endif
