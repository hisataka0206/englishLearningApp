#!/bin/bash
# English Learning App - one-time setup on the Mac.
# - Installs a LaunchAgent so the server auto-starts at login and
#   restarts automatically if it crashes. After this, no manual operation.
set -e

APP_DIR="$(cd "$(dirname "$0")" && pwd)"
LABEL="com.englishlearningapp.server"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
PYTHON="$(command -v python3)"

mkdir -p "$APP_DIR/logs" "$HOME/Library/LaunchAgents"

cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
 "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key>
  <array>
    <string>$PYTHON</string>
    <string>$APP_DIR/server.py</string>
  </array>
  <key>WorkingDirectory</key><string>$APP_DIR</string>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>$APP_DIR/logs/server.log</string>
  <key>StandardErrorPath</key><string>$APP_DIR/logs/server.err.log</string>
</dict>
</plist>
EOF

launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"
sleep 1

echo "--------------------------------------------"
echo "LaunchAgent installed: $LABEL"
echo "Server status:"
curl -s "http://localhost:8765/api/health" | head -c 300 || echo "(not responding yet - check logs/)"
echo ""
echo "--------------------------------------------"
echo "Remaining one-time steps (see README.md):"
echo " 1. Mac: keep Tailscale 'Start on login' ON"
echo " 2. Mac: System Settings > prevent sleep"
echo " 3. iPhone: Tailscale app > VPN On Demand ON"
echo " 4. iPhone: open http://<mac-name>:8765 and 'Add to Home Screen'"
