.PHONY: start smoke dev test lint check format

start:
	uv run uvicorn daimos.main:app --host 0.0.0.0 --port 8003

dev:
	uv run uvicorn daimos.main:app --host 0.0.0.0 --port 8003 --reload

test:
	uv run pytest tests/ -n auto --testmon

smoke:
	uv run pytest tests/ -m smoke

lint:
	uv run ruff check . --fix --unsafe-fixes

check: format type lint

format:
	uv run ruff format .

type:
	uv run ty check .
