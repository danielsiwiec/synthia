#!/usr/bin/env bash
set -euo pipefail

LABEL="com.synthia.chrome-cdp"
PLIST_PATH="$HOME/Library/LaunchAgents/$LABEL.plist"

generate_plist() {
    cat <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>$LABEL</string>

    <key>ProgramArguments</key>
    <array>
        <string>/Applications/Google Chrome.app/Contents/MacOS/Google Chrome</string>
        <string>--remote-debugging-port=9222</string>
        <string>--remote-debugging-address=0.0.0.0</string>
        <string>--remote-allow-origins=*</string>
        <string>--user-data-dir=$HOME/Library/Application Support/Google/Chrome-CDP</string>
        <string>--password-store=basic</string>
    </array>

    <key>RunAtLoad</key>
    <true/>

    <key>KeepAlive</key>
    <true/>

    <key>StandardOutPath</key>
    <string>$HOME/Library/Logs/chrome-cdp.log</string>

    <key>StandardErrorPath</key>
    <string>$HOME/Library/Logs/chrome-cdp.error.log</string>
</dict>
</plist>
EOF
}

install() {
    generate_plist > "$PLIST_PATH"
    launchctl load "$PLIST_PATH"
    echo "✓ Chrome CDP service installed and started"
    echo "Chrome will start automatically on login"
}

uninstall() {
    launchctl unload "$PLIST_PATH" 2>/dev/null || true
    rm -f "$PLIST_PATH"
    echo "✓ Chrome CDP service uninstalled"
}

case "${1:-}" in
    install)   install ;;
    uninstall) uninstall ;;
    *)         echo "Usage: $0 {install|uninstall}" >&2; exit 1 ;;
esac
