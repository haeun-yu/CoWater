#!/usr/bin/env bash
set -euo pipefail

PLIST_NAME="com.cowater.ollama.plist"
LABEL="com.cowater.ollama"
SOURCE_DIR="$(cd "$(dirname "$0")" && pwd)"
SOURCE_PLIST="$SOURCE_DIR/launchd/$PLIST_NAME"
TARGET_DIR="$HOME/Library/LaunchAgents"
TARGET_PLIST="$TARGET_DIR/$PLIST_NAME"

if ! command -v ollama >/dev/null 2>&1; then
  printf 'ollama binary not found on PATH. Install Ollama first.\n' >&2
  exit 1
fi

mkdir -p "$TARGET_DIR"
cp "$SOURCE_PLIST" "$TARGET_PLIST"

OLLAMA_BIN="$(command -v ollama)"
/usr/bin/sed -i '' "s#/usr/local/bin/ollama#$OLLAMA_BIN#g" "$TARGET_PLIST"
/usr/bin/sed -i '' "s#/Users/teamgrit#$HOME#g" "$TARGET_PLIST"

launchctl unload "$TARGET_PLIST" >/dev/null 2>&1 || true
launchctl load "$TARGET_PLIST"
launchctl kickstart -k "gui/$(id -u)/$LABEL"

printf 'Installed and started launchd agent: %s\n' "$LABEL"
printf 'Logs: /tmp/cowater-host-ollama.log\n'
