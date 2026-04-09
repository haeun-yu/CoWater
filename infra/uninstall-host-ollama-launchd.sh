#!/usr/bin/env bash
set -euo pipefail

PLIST_NAME="com.cowater.ollama.plist"
LABEL="com.cowater.ollama"
TARGET_PLIST="$HOME/Library/LaunchAgents/$PLIST_NAME"

if [[ -f "$TARGET_PLIST" ]]; then
  launchctl unload "$TARGET_PLIST" >/dev/null 2>&1 || true
  rm -f "$TARGET_PLIST"
fi

pkill -f '^ollama serve$' >/dev/null 2>&1 || true

printf 'Removed launchd agent: %s\n' "$LABEL"
