.PHONY: start smoke dev test lint check format

start:
	uv run uvicorn synthia.main:app --host 0.0.0.0 --port 8003

dev:
	uv run uvicorn synthia.main:app --host 0.0.0.0 --port 8003 --reload

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

install:
	mkdir -p ~/Library/LaunchAgents
	cp com.dansiwiec.synthia.plist ~/Library/LaunchAgents
	launchctl bootstrap gui/$$(id -u) ~/Library/LaunchAgents/com.dansiwiec.synthia.plist || true

uninstall:
	launchctl bootout gui/$$(id -u)/com.dansiwiec.synthia || true
	rm ~/Library/LaunchAgents/com.dansiwiec.synthia.plist || true

restart:
	cp com.dansiwiec.synthia.plist ~/Library/LaunchAgents
	launchctl kickstart -k gui/$$(id -u)/com.dansiwiec.synthia