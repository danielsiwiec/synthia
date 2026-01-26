.PHONY: start smoke dev test test-voice lint check format toml-sort install-chrome-cdp uninstall-chrome-cdp

start:
	uv run uvicorn synthia.main:app --host 0.0.0.0 --port 8003

dev:
	uv run uvicorn synthia.main:app --host 0.0.0.0 --port 8003 --reload

test:
	uv run pytest tests/ -n auto --testmon -m "not voice"

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

up:
	docker compose up --build -d --remove-orphans

down:
	docker compose down

restart:
	docker compose restart

get-credentials:
	ks -k login show "Claude Code-credentials" > ./claude_home/.credentials.json

install-chrome-cdp:
	cp com.dansiwiec.chrome-cdp.plist ~/Library/LaunchAgents/
	launchctl load ~/Library/LaunchAgents/com.dansiwiec.chrome-cdp.plist
	@echo "✓ Chrome CDP service installed and started"
	@echo "Chrome will start automatically on login"

uninstall-chrome-cdp:
	-launchctl unload ~/Library/LaunchAgents/com.dansiwiec.chrome-cdp.plist
	rm -f ~/Library/LaunchAgents/com.dansiwiec.chrome-cdp.plist
	@echo "✓ Chrome CDP service uninstalled"