SHELL := /bin/sh
APP_PORT ?= 8501
OLLAMA_API_BASE ?= http://localhost:11434
OLLAMA_MODEL_TAG ?= gemma3:latest
MODEL_NAME ?= ollama_chat/$(OLLAMA_MODEL_TAG)
RESOLVED_APP_PORT := $(shell python3 scripts/find_free_port.py $(APP_PORT))
LOCAL_UID := $(shell id -u)
LOCAL_GID := $(shell id -g)
COMPOSE_ENV = APP_PORT=$(RESOLVED_APP_PORT) OLLAMA_API_BASE=http://host.docker.internal:11434 MODEL_NAME=$(MODEL_NAME) LOCAL_UID=$(LOCAL_UID) LOCAL_GID=$(LOCAL_GID)

.PHONY: up down stop logs status config check-ollama

up: check-ollama
	mkdir -p artifacts
	$(COMPOSE_ENV) docker compose up --build -d --wait app
	@printf '\nGemma Code Studio is available at http://localhost:%s\n' '$(RESOLVED_APP_PORT)'

check-ollama:
	@OLLAMA_API_BASE='$(OLLAMA_API_BASE)' OLLAMA_MODEL_TAG='$(OLLAMA_MODEL_TAG)' python3 scripts/check_ollama.py

down:
	$(COMPOSE_ENV) docker compose down

stop:
	$(COMPOSE_ENV) docker compose stop

logs:
	$(COMPOSE_ENV) docker compose logs -f app

status:
	$(COMPOSE_ENV) docker compose ps

config:
	$(COMPOSE_ENV) docker compose config