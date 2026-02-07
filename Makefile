.PHONY: start smoke dev test test-voice lint check format toml-sort

start:
	uv run uvicorn synthia.main:app --host 0.0.0.0 --port 8003

dev:
	uv run uvicorn synthia.main:app --host 0.0.0.0 --port 8003 --reload

test:
	uv run pytest tests/ -n auto --testmon -m "not voice and not performance"

smoke:
	uv run pytest tests/ -m smoke

test-voice:
	uv run pytest tests/ -m voice

lint:
	uv run ruff check . --fix --unsafe-fixes

check: format type lint toml-sort

format:
	uv run ruff format .

type:
	uv run ty check .

toml-sort:
	uv run toml-sort --in-place pyproject.toml

run:
	docker compose up --build --remove-orphans

up:
	docker compose up --build -d --remove-orphans

down:
	docker compose down

restart:
	docker compose restart
