#!/usr/bin/env bash
#
# Stop script for Storj Multi-Node Summary Dashboard
#

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PID_FILE="$SCRIPT_DIR/dashboard.pid"

if [ -f "$PID_FILE" ]; then
    PID=$(cat "$PID_FILE")
    if ps -p "$PID" > /dev/null 2>&1; then
        echo "[INFO] Stopping Storj Dashboard (PID: $PID)..."
        kill "$PID"
        sleep 1
        if ps -p "$PID" > /dev/null 2>&1; then
            echo "[INFO] Forcing termination..."
            kill -9 "$PID"
        fi
        echo "[SUCCESS] Dashboard stopped."
    else
        echo "[WARN] PID file exists but process $PID is not running."
    fi
    rm -f "$PID_FILE"
else
    # Check if anything is running server.py or listening on 8888
    PID=$(pgrep -f "python3.*server.py" | head -n 1)
    if [ -n "$PID" ]; then
        echo "[INFO] Stopping running server instance (PID: $PID)..."
        kill "$PID"
        echo "[SUCCESS] Dashboard stopped."
    else
        echo "[INFO] Storj Dashboard is not running."
    fi
fi
