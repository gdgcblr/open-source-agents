# Developer workflow for the Healthcare IVR.
# Run `make` (or `make help`) to list every target. Works on macOS and Linux; on Windows, run it
# inside WSL 2 (see README.md > Prerequisites).

.DEFAULT_GOAL := help
SHELL := /bin/bash

BACKEND_DIR  := backend
FRONTEND_DIR := frontend
BACKEND_PORT ?= 8000
COMPOSE      := docker compose

# A virtualenv activated in your shell for another project would confuse uv; always use backend/.venv.
unexport VIRTUAL_ENV

##@ Getting started

.PHONY: help
help: ## Show this help
	@awk 'BEGIN { FS = ":.*## "; printf "\nUsage: make \033[36m<target>\033[0m\n" } \
		/^[a-zA-Z0-9_.-]+:.*## / { printf "  \033[36m%-17s\033[0m %s\n", $$1, $$2 } \
		/^##@/ { printf "\n\033[1m%s\033[0m\n", substr($$0, 5) }' $(MAKEFILE_LIST)
	@echo ""

.PHONY: setup
setup: check-tools .env install ## First-time setup: check tools, create .env, install dependencies
	@echo ""
	@echo "Setup complete. Add your keys to .env, then run 'make dev'."

.PHONY: check-tools
check-tools: ## Verify that uv, Node.js (22.22+ or 24.15+) and npm are installed
	@missing=0; \
	for tool in uv node npm; do \
		command -v $$tool >/dev/null 2>&1 || { echo "Missing required tool: $$tool"; missing=1; }; \
	done; \
	if [ $$missing -ne 0 ]; then echo "Install it as described in README.md > Prerequisites."; exit 1; fi
	@node -e 'const [major, minor] = process.versions.node.split(".").map(Number); \
		process.exit((major === 22 && minor >= 22) || (major === 24 && minor >= 15) || major >= 25 ? 0 : 1)' \
		|| { echo "Node.js $$(node -v) is too old for the dashboard: install Node.js 24 LTS."; exit 1; }
	@echo "Found uv $$(uv --version | cut -d' ' -f2), Node.js $$(node -v), npm $$(npm -v)."
	@for tool in docker ngrok; do \
		command -v $$tool >/dev/null 2>&1 || echo "Optional: $$tool not found (only needed for 'make docker-up' / 'make tunnel')."; \
	done

.env:
	cp .env.example .env
	@echo "Created .env from .env.example. Set DEEPGRAM_API_KEY and DASHBOARD_PASSWORD before starting."

.PHONY: env
env: .env ## Create .env from .env.example (never overwrites an existing .env)

.PHONY: check-env
check-env: .env ## Check that .env has your own Deepgram key and dashboard password
	@if grep -q '^DASHBOARD_PASSWORD=change-me-to-a-long-random-password' .env; then \
		echo "Set DASHBOARD_PASSWORD in .env to a password of your own, then run this again."; exit 1; \
	fi
	@if grep -q '^DEEPGRAM_API_KEY=your_deepgram_api_key_here' .env; then \
		echo "Warning: DEEPGRAM_API_KEY in .env is still the placeholder. The dashboard will start,"; \
		echo "but calls and transcription need a real key from https://console.deepgram.com."; \
	fi

.PHONY: install
install: install-backend install-frontend ## Install backend and frontend dependencies

.PHONY: install-backend
install-backend: ## Install Python dependencies into backend/.venv
	cd $(BACKEND_DIR) && uv sync

.PHONY: install-frontend
install-frontend: ## Install Node dependencies exactly as locked
	cd $(FRONTEND_DIR) && npm ci --no-fund --no-audit

##@ Development

.PHONY: dev
dev: check-env ## Run the API (:8000) and dashboard (:5173) together with hot reload
	@$(MAKE) --no-print-directory -j2 dev-backend dev-frontend

.PHONY: dev-backend
dev-backend: check-env ## Run only the API, reloading on code changes
	cd $(BACKEND_DIR) && uv run uvicorn app.main:create_app --factory --reload --port $(BACKEND_PORT)

.PHONY: dev-frontend
dev-frontend: ## Run only the dashboard dev server
	cd $(FRONTEND_DIR) && BACKEND_URL=http://localhost:$(BACKEND_PORT) npm run dev

.PHONY: tunnel
tunnel: ## Give the API a public HTTPS URL with ngrok so Twilio can reach it
	ngrok http $(BACKEND_PORT)

##@ Quality

.PHONY: test
test: test-backend test-frontend ## Run all tests

.PHONY: test-backend
test-backend: ## Run backend tests (pytest)
	cd $(BACKEND_DIR) && uv run pytest

.PHONY: test-frontend
test-frontend: ## Run frontend tests (Vitest)
	cd $(FRONTEND_DIR) && npm test

.PHONY: lint
lint: ## Lint, check formatting and type-check both apps
	cd $(BACKEND_DIR) && uv run ruff check . && uv run ruff format --check .
	cd $(FRONTEND_DIR) && npm run lint && npm run typecheck

.PHONY: format
format: ## Auto-format and auto-fix backend code
	cd $(BACKEND_DIR) && uv run ruff format . && uv run ruff check --fix .

.PHONY: check
check: lint test ## Run everything CI should run before a pull request

##@ Docker

.PHONY: docker-build
docker-build: .env ## Build the backend and frontend images
	$(COMPOSE) build

.PHONY: docker-up
docker-up: check-env ## Build and start the stack in the background
	$(COMPOSE) up --build -d
	@echo "Dashboard: http://localhost:8080    API: http://localhost:8000"

.PHONY: docker-down
docker-down: ## Stop the stack (keeps calls and recordings)
	$(COMPOSE) down

.PHONY: docker-logs
docker-logs: ## Follow logs from all services
	$(COMPOSE) logs -f

.PHONY: docker-clean
docker-clean: ## Stop the stack and delete its volume (removes all calls and recordings)
	$(COMPOSE) down -v

##@ Housekeeping

.PHONY: reset-db
reset-db: ## Delete local calls, appointments and recordings (backend/data); needed after schema changes
	@read -r -p "Delete backend/data (all local calls, appointments and recordings)? [y/N] " answer; \
	if [ "$$answer" = "y" ] || [ "$$answer" = "Y" ]; then \
		rm -rf $(BACKEND_DIR)/data && echo "Deleted. The next start creates a fresh database."; \
	else \
		echo "Nothing deleted."; \
	fi

.PHONY: clean
clean: ## Remove dependencies, build output and caches (keeps .env and call data)
	rm -rf $(BACKEND_DIR)/.venv $(BACKEND_DIR)/.pytest_cache $(BACKEND_DIR)/.ruff_cache
	rm -rf $(FRONTEND_DIR)/node_modules $(FRONTEND_DIR)/dist
	find $(BACKEND_DIR) -name __pycache__ -type d -prune -exec rm -rf {} +
