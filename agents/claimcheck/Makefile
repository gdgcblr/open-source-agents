UV ?= uv
IMAGE = python@sha256:a0f57064cbdcd6285fa45f51237ab0b35ea8ebaed06a1f5973e89e19dfb86704

.PHONY: help setup doctor doctor-model test lint format typecheck check docker-prepare demo demo-lite demo-agent audit specs spec-status build

help: ## Show available commands
	@awk 'BEGIN {FS = ":.*## "} /^[a-zA-Z_-]+:.*## / {printf "%-18s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

setup: ## Install locked Python dependencies (does not overwrite .env)
	$(UV) sync --locked --python 3.12
	@test -f .env || cp .env.example .env

doctor: ## Check local tools, Docker daemon and sandbox image
	$(UV) run --locked claimcheck doctor

doctor-model: ## Also check configured Ollama model (requires remote consent if applicable)
	$(UV) run --locked claimcheck doctor --model

test: ## Run deterministic tests, including mocked native ADK/Ollama
	$(UV) run --locked pytest --cov=claimcheck --cov-report=term-missing

lint: ## Check Python style
	$(UV) run --locked ruff check src tests fixtures
	$(UV) run --locked ruff format --check src tests fixtures

format: ## Format Python sources
	$(UV) run --locked ruff format src tests fixtures

typecheck: ## Strict-check application types
	$(UV) run --locked mypy src

check: lint typecheck test specs ## Run all deterministic quality gates

docker-prepare: ## Explicitly download the pinned sandbox runtime
	docker pull $(IMAGE)

demo: ## Full offline demo: README execution, live API and stale-image drift (needs Docker)
	$(UV) run --locked claimcheck demo --docker --output reports/demo

demo-lite: ## No-Docker/no-model live API + links demo; other checks honestly unverified
	$(UV) run --locked claimcheck demo --output reports/demo-lite

demo-agent: ## Full synthetic demo orchestrated by ADK and native Ollama (needs Docker)
	$(UV) run --locked claimcheck demo --docker --agent --output reports/demo-agent

audit: ## Audit PROJECT=/path BASE_URL=http://localhost:8000 IMAGE_REF=repo:tag (safe default)
	@test -n "$(PROJECT)" || (echo 'Set PROJECT=/path/to/project' >&2; exit 2)
	$(UV) run --locked claimcheck audit "$(PROJECT)" $(if $(BASE_URL),--base-url "$(BASE_URL)") $(if $(IMAGE_REF),--image "$(IMAGE_REF)")

specs: ## Validate OpenSpec main specifications and change artifacts
	OPENSPEC_TELEMETRY=0 openspec validate --all --strict --no-interactive

spec-status: ## Show initial implementation change completeness
	OPENSPEC_TELEMETRY=0 openspec status --change add-claimcheck

build: ## Build a wheel and sdist, including the synthetic fixture
	$(UV) build
