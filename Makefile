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
	sudo cp com.dansiwiec.synthia.plist /Library/LaunchDaemons
	sudo launchctl bootstrap system /Library/LaunchDaemons/com.dansiwiec.synthia.plist || true

uninstall:
	sudo launchctl bootout system/com.dansiwiec.synthia || true
	sudo rm /Library/LaunchDaemons/com.dansiwiec.synthia.plist

restart:
	sudo cp com.dansiwiec.synthia.plist /Library/LaunchDaemons
	sudo launchctl kickstart -k system/com.dansiwiec.synthia