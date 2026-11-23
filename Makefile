PY := .venv/bin/python

.PHONY: setup check train ablation up down

COMPOSE := docker compose --env-file .env -f docker/docker-compose.yml

# create the virtual environment and install dependencies
setup:
	python3.11 -m venv .venv
	$(PY) -m pip install --upgrade pip
	$(PY) -m pip install -r requirements.txt -r requirements-dev.txt

# lint and run tests
check:
	$(PY) -m ruff check .
	$(PY) -m pytest -q

# train the classifier and write metrics
train:
	$(PY) -m src.train

# run the additive feature ablation
ablation:
	$(PY) -m src.ablation

# build and start the streaming stack
up:
	@test -f .env || cp .env.example .env
	$(COMPOSE) up -d --build

# stop the streaming stack and remove its volumes
down:
	@test -f .env || cp .env.example .env
	$(COMPOSE) down -v
