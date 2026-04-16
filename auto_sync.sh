#!/usr/bin/env bash

# auto_sync.sh - Background Git sync script
# Logs to auto_sync.log

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_FILE="$REPO_DIR/auto_sync.log"
PID_FILE="$REPO_DIR/auto_sync.pid"

echo $$ > "$PID_FILE"

echo "[$(date)] Auto-sync started. PID: $$" >> "$LOG_FILE"

while true; do
    cd "$REPO_DIR"
    
    # Check for changes (tracked or untracked)
    if [[ -n $(git status --porcelain) ]]; then
        echo "[$(date)] Changes detected. Starting sync..." >> "$LOG_FILE"
        
        git add . >> "$LOG_FILE" 2>&1
        git commit -m "Auto-sync at $(date)" >> "$LOG_FILE" 2>&1
        
        if git push origin main >> "$LOG_FILE" 2>&1; then
            echo "[$(date)] Successfully pushed changes." >> "$LOG_FILE"
        else
            echo "[$(date)] ERROR: Push failed. Check your network or credentials." >> "$LOG_FILE"
        fi
    else
        echo "[$(date)] No changes detected. Skipping sync." >> "$LOG_FILE"
    fi
    
    # Sleep for 1 hour (3600 seconds)
    sleep 3600
done
