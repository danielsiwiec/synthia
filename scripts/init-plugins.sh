#!/bin/bash
set -e

export PATH="$HOME/.local/bin:$PATH"

PLUGIN_INSTALLED_MARKER="/home/synthia/.claude/plugins/.episodic-memory-installed"

if [ ! -f "$PLUGIN_INSTALLED_MARKER" ]; then
    echo "Installing episodic-memory plugin..."
    claude plugin marketplace add obra/episodic-memory
    claude plugin install episodic-memory@episodic-memory-dev
    touch "$PLUGIN_INSTALLED_MARKER"
    echo "Plugin installed successfully"
else
    echo "Plugin already installed, skipping..."
fi

exec "$@"
