.PHONY: start smoke dev test lint check format toml-sort vapid-keys frontend-install frontend-build frontend-dev

start: frontend-build
	uv run uvicorn synthia.main:app --host 0.0.0.0 --port 8003

dev:
	uv run uvicorn synthia.main:app --host 0.0.0.0 --port 8003 --reload

frontend-install:
	cd frontend && npm ci

frontend-build:
	cd frontend && npm run build

frontend-dev:
	cd frontend && npm run dev

test:
	uv run pytest tests/ --ignore=tests/test_ui.py -n auto --testmon -m "not performance and not eval"
	uv run pytest tests/test_ui.py -p no:testmon -m "not performance and not eval"

smoke:
	uv run pytest tests/ -m smoke

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

vapid-keys:
	@uv run python -c "from py_vapid import Vapid; from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat; import base64; v = Vapid(); v.generate_keys(); raw = v.private_key.private_numbers().private_value.to_bytes(32, 'big'); print('VAPID_PRIVATE_KEY=' + base64.urlsafe_b64encode(raw).rstrip(b'=').decode()); print('VAPID_PUBLIC_KEY=' + base64.urlsafe_b64encode(v.public_key.public_bytes(Encoding.X962, PublicFormat.UncompressedPoint)).rstrip(b'=').decode())"
