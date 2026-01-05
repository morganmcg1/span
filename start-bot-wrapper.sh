#!/bin/bash
# Wrapper script that monitors for restart requests from Claude Code integration.
# This script runs the Telegram bot in a loop and restarts it when a sentinel file appears.
#
# Usage: ./start-bot-wrapper.sh
#
# The bot can request a restart by touching data/restart_sentinel.
# This is used by the Claude Code integration to deploy changes on the fly.

set -e

# Determine script directory (works whether run locally or on server)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SPAN_DIR="${SPAN_DIR:-$SCRIPT_DIR}"

# Paths
SENTINEL="$SPAN_DIR/data/restart_sentinel"
LOG="$SPAN_DIR/telegram.log"

# Clean up any stale sentinel from previous runs
rm -f "$SENTINEL"

echo "[$(date)] Bot wrapper starting in $SPAN_DIR" >> "$LOG"

while true; do
    echo "[$(date)] Starting Telegram bot..." >> "$LOG"

    # Change to span directory
    cd "$SPAN_DIR"

    # Find uv binary (different locations on server vs local)
    if [ -x "/root/.local/bin/uv" ]; then
        UV_BIN="/root/.local/bin/uv"
    elif command -v uv &> /dev/null; then
        UV_BIN="uv"
    else
        echo "[$(date)] ERROR: uv not found" >> "$LOG"
        exit 1
    fi

    # Start the bot in background
    $UV_BIN run python -m span.telegram >> "$LOG" 2>&1 &
    BOT_PID=$!

    echo "[$(date)] Bot started with PID $BOT_PID" >> "$LOG"

    # Monitor both the process and the sentinel file
    while kill -0 $BOT_PID 2>/dev/null; do
        if [ -f "$SENTINEL" ]; then
            echo "[$(date)] Restart requested via sentinel" >> "$LOG"
            rm -f "$SENTINEL"

            # Gracefully stop the bot
            kill $BOT_PID 2>/dev/null || true

            # Wait for process to exit (max 10 seconds)
            for i in {1..10}; do
                if ! kill -0 $BOT_PID 2>/dev/null; then
                    break
                fi
                sleep 1
            done

            # Force kill if still running
            kill -9 $BOT_PID 2>/dev/null || true

            break
        fi
        sleep 1
    done

    # Reap the bot process and log exit code
    if wait $BOT_PID 2>/dev/null; then
        EXIT_CODE=0
    else
        EXIT_CODE=$?
    fi
    echo "[$(date)] Bot exited with code $EXIT_CODE" >> "$LOG"

    # Brief pause before restart
    echo "[$(date)] Restarting in 2 seconds..." >> "$LOG"
    sleep 2
done
