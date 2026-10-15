#!/usr/bin/env bash
#
# Status script for Storj Multi-Node Summary Dashboard
#

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PID_FILE="$SCRIPT_DIR/dashboard.pid"

RUNNING=false

if [ -f "$PID_FILE" ]; then
    PID=$(cat "$PID_FILE")
    if ps -p "$PID" > /dev/null 2>&1; then
        RUNNING=true
        echo "[STATUS] Storj Dashboard is RUNNING (PID: $PID)"
    fi
fi

if [ "$RUNNING" = false ]; then
    PID=$(pgrep -f "python3.*server.py" | head -n 1)
    if [ -n "$PID" ]; then
        RUNNING=true
        echo "[STATUS] Storj Dashboard is RUNNING without PID file (PID: $PID)"
    else
        echo "[STATUS] Storj Dashboard is STOPPED"
        exit 1
    fi
fi

# Query health
HEALTH=$(curl -s --max-time 2 http://localhost:8888/health 2>/dev/null)
if [ -n "$HEALTH" ]; then
    echo "[HEALTH] Local API is responsive: $HEALTH"
else
    echo "[WARN] Process is alive but HTTP endpoint on port 8888 did not respond."
fi
