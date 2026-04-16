#!/usr/bin/env bash

# stop_sync.sh - Terminates the background auto_sync process

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PID_FILE="$REPO_DIR/auto_sync.pid"
LOG_FILE="$REPO_DIR/auto_sync.log"

if [[ -f "$PID_FILE" ]]; then
    PID=$(cat "$PID_FILE")
    if ps -p "$PID" > /dev/null; then
        echo "[$(date)] Stopping auto_sync process (PID: $PID)..." >> "$LOG_FILE"
        kill "$PID"
        echo "Auto-sync process stopped."
    else
        echo "Auto-sync process (PID: $PID) is not running."
    fi
    rm "$PID_FILE"
else
    echo "No auto_sync.pid found. Is the process running?"
fi
