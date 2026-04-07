#!/bin/bash
# Installa Jarvis Client come LaunchAgent su macOS (avvio automatico al login)

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLIST_PATH="$HOME/Library/LaunchAgents/com.jarvis.client.plist"
PYTHON=$(which python3)

echo "=== Jarvis Client - Installazione macOS ==="

# Controlla Python
if ! command -v python3 &>/dev/null; then
    echo "ERRORE: Python 3 non trovato. Installa con: brew install python"
    exit 1
fi

# Installa dipendenze
echo "Installo dipendenze Python..."
pip3 install -r "$SCRIPT_DIR/requirements.txt"

# Crea LaunchAgent plist
cat > "$PLIST_PATH" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.jarvis.client</string>
    <key>ProgramArguments</key>
    <array>
        <string>$PYTHON</string>
        <string>$SCRIPT_DIR/jarvis_client.py</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>$HOME/.jarvis_client.log</string>
    <key>StandardErrorPath</key>
    <string>$HOME/.jarvis_client.log</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>JARVIS_SERVER</key>
        <string>ws://192.168.1.131/ws/voice</string>
        <key>JARVIS_USER</key>
        <string>mac_client</string>
    </dict>
</dict>
</plist>
EOF

# Carica il LaunchAgent
launchctl load "$PLIST_PATH"

echo ""
echo "✅ Jarvis Client installato!"
echo "   - Si avvia automaticamente al login"
echo "   - Log: $HOME/.jarvis_client.log"
echo "   - Per fermarlo: launchctl unload $PLIST_PATH"
echo "   - Per i log: tail -f ~/.jarvis_client.log"
