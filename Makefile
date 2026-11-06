SHELL := /bin/sh

COMPOSE ?= docker compose

.PHONY: build up seed refresh run check ps logs stop down

build:
	$(COMPOSE) build

up:
	$(COMPOSE) up -d --build

seed:
	$(COMPOSE) run --rm seed

refresh:
	$(COMPOSE) run --rm refresh

run: up
	$(COMPOSE) run --rm seed
	$(COMPOSE) run --rm refresh

check: build
	$(COMPOSE) config --quiet
	$(COMPOSE) run --rm --no-deps --entrypoint ruff refresh check src dags

ps:
	$(COMPOSE) ps

logs:
	$(COMPOSE) logs --tail=200 airflow

stop:
	$(COMPOSE) stop

down:
	$(COMPOSE) down
