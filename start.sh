#!/usr/bin/env bash
#
# Start script for Storj Multi-Node Summary Dashboard
#

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PID_FILE="$SCRIPT_DIR/dashboard.pid"
LOG_FILE="$SCRIPT_DIR/dashboard.log"

cd "$SCRIPT_DIR"

if [ -f "$PID_FILE" ]; then
    PID=$(cat "$PID_FILE")
    if ps -p "$PID" > /dev/null 2>&1; then
        echo "[INFO] Storj Dashboard is already running (PID: $PID)."
        echo "       URL: http://localhost:8888"
        exit 0
    else
        rm -f "$PID_FILE"
    fi
fi

# Check if port 8888 is already bound by another process
if command -v lsof > /dev/null 2>&1; then
    OCCUPIED=$(lsof -ti:8888)
    if [ -n "$OCCUPIED" ]; then
        echo "[ERROR] Port 8888 is already in use by PID $OCCUPIED."
        exit 1
    fi
fi

if [ "$1" == "--foreground" ] || [ "$1" == "-f" ]; then
    echo "[INFO] Starting Storj Multi-Node Dashboard in foreground..."
    exec python3 "$SCRIPT_DIR/server.py"
fi

echo "[INFO] Starting Storj Multi-Node Dashboard in background..."
nohup python3 -u "$SCRIPT_DIR/server.py" >> "$LOG_FILE" 2>&1 &
PID=$!
echo "$PID" > "$PID_FILE"
disown "$PID" 2>/dev/null || true

# Wait briefly to confirm start
sleep 1
if ps -p "$PID" > /dev/null 2>&1; then
    echo "[SUCCESS] Storj Dashboard started successfully (PID: $PID)."
    echo "          Local Access: http://localhost:8888"
    LAN_IP=$(hostname -I 2>/dev/null | awk '{print $1}')
    if [ -n "$LAN_IP" ]; then
        echo "          LAN Access:   http://$LAN_IP:8888"
    fi
    echo "          Logs:         $LOG_FILE"
    echo "          Stop command: ./stop.sh"
else
    echo "[ERROR] Dashboard failed to start. Showing last log entries:"
    tail -n 20 "$LOG_FILE"
    rm -f "$PID_FILE"
    exit 1
fi
