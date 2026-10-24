.PHONY: docker-build docker-test docker-cli docker-seed docker-smoke

IMAGE ?= rentrakshak:local

docker-build:
	docker compose build

docker-test:
	docker compose run --rm test

docker-cli:
	docker compose run --rm cli

docker-seed:
	docker compose run --rm seed

docker-smoke: docker-build docker-test docker-cli
	@echo "Docker smoke OK"
