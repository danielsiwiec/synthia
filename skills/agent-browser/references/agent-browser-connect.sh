#!/bin/bash

CDP_HOST="${AGENT_BROWSER_CDP_HOST:-host.docker.internal}"
CDP_PORT="${AGENT_BROWSER_CDP_PORT:-9222}"

WS_URL=$(curl -s -H "Host: localhost" "http://${CDP_HOST}:${CDP_PORT}/json/version" | grep -o '"webSocketDebuggerUrl"[[:space:]]*:[[:space:]]*"[^"]*"' | sed 's/.*"\(ws:\/\/[^"]*\)".*/\1/')

if [ -z "$WS_URL" ]; then
    echo "Error: Could not get WebSocket URL from Chrome CDP at ${CDP_HOST}:${CDP_PORT}" >&2
    exit 1
fi

WS_URL=$(echo "$WS_URL" | sed "s|ws://localhost|ws://${CDP_HOST}:${CDP_PORT}|")

agent-browser connect "$WS_URL"
