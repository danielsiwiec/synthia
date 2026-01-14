.PHONY: start smoke dev test test-voice lint check format install-playwright-mcp start-playwright-mcp stop-playwright-mcp uninstall-playwright-mcp

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

check: format type lint

format:
	uv run ruff format .

type:
	uv run ty check .

up:
	docker compose up --build -d --remove-orphans

down:
	docker compose down

restart:
	docker compose restart

install-playwright-mcp:
	mkdir -p ~/Library/LaunchAgents/
	cp com.dansiwiec.playwright-mcp.plist ~/Library/LaunchAgents/
	-launchctl bootout gui/$$(id -u)/com.dansiwiec.playwright-mcp 2>/dev/null || true
	-launchctl unload ~/Library/LaunchAgents/com.dansiwiec.playwright-mcp.plist 2>/dev/null || true
	launchctl bootstrap gui/$$(id -u) ~/Library/LaunchAgents/com.dansiwiec.playwright-mcp.plist

uninstall-playwright-mcp:
	-launchctl bootout gui/$$(id -u)/com.dansiwiec.playwright-mcp 2>/dev/null || true
	rm -f ~/Library/LaunchAgents/com.dansiwiec.playwright-mcp.plist

get-credentials:
	ks -k login show "Claude Code-credentials" > ./claude_home/.credentials.json