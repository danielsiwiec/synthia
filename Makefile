.PHONY: start dev test lint format

start:
	uv run uvicorn main:app --host 0.0.0.0 --port 8003

dev:
	uv run uvicorn main:app --host 0.0.0.0 --port 8003 --reload

test:
	uv run pytest -n auto --testmon

lint: format
	uv run ruff check . --fix --unsafe-fixes

format:
	uv run ruff format .
