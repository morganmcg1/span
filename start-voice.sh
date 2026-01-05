#!/bin/bash
# Start the voice server.
# Usage: ./start-voice.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SPAN_DIR="${SPAN_DIR:-$SCRIPT_DIR}"
LOG="$SPAN_DIR/voice.log"

# Kill any existing voice server
pkill -f 'span.voice' 2>/dev/null || true
sleep 1

# Find uv binary
if [ -x "/root/.local/bin/uv" ]; then
    UV_BIN="/root/.local/bin/uv"
elif command -v uv &> /dev/null; then
    UV_BIN="uv"
else
    echo "[$(date)] ERROR: uv not found" >> "$LOG"
    exit 1
fi

cd "$SPAN_DIR"
echo "[$(date)] Starting voice server..." >> "$LOG"
nohup $UV_BIN run python -m span.voice >> "$LOG" 2>&1 &
echo "[$(date)] Voice server started with PID $!" >> "$LOG"
