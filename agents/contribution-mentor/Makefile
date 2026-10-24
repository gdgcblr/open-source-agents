-include .env

export LLM_PROVIDER
export LLM_BASE_URL
export LLM_MODEL
export LLM_API_KEY
export GITHUB_TOKEN
export GITHUB_REPO
export EXPERIENCE
export ISSUE
export IMPLEMENT
export PROJECT_DIR
export QUESTION
export OLLAMA_IMAGE
export OLLAMA_SERVER_HOST

ifeq ($(IMPLEMENT),true)
READ_ONLY := false
CONTAINER_USER := 0:0
else
READ_ONLY := true
CONTAINER_USER := 65532:65532
endif
export READ_ONLY
export CONTAINER_USER

.PHONY: run ensure-env _run test down

run: ensure-env
	$(MAKE) --no-print-directory _run

ensure-env:
	@if not exist .env copy .env.example .env

_run:
	@docker info >NUL 2>&1 || (echo Docker is not running. Start Docker Desktop and try again. & exit /b 1)
ifeq ($(LLM_PROVIDER),ollama)
	docker compose --profile ollama up -d ollama
	docker compose --profile ollama run --rm model-init
else ifneq ($(LLM_PROVIDER),openai-compatible)
ifneq ($(LLM_PROVIDER),)
	$(error LLM_PROVIDER must be ollama or openai-compatible)
endif
endif
	docker compose run --build --rm mentor

test:
	go test ./...

down:
	docker compose --profile ollama down
