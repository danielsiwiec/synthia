dev:
	uv run uvicorn synthia.main:app --host 0.0.0.0 --port 8001 --reload

start:
	uv run uvicorn synthia.main:app --host 0.0.0.0 --port 8001

test:
	uv run pytest tests/ --testmon

lint:
	uv run ruff check . --fix --unsafe-fixes

check: format type lint

format:
	uv run ruff format .

type:
	uv run ty check .