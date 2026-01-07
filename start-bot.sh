#!/bin/bash
# Helper script to start the Telegram bot via the restart-aware wrapper.
# This allows Claude Code to trigger restarts via the sentinel file mechanism.
#
# Usage: ./start-bot.sh
#
# The wrapper runs in a loop and restarts the bot when:
# 1. The bot exits (crash or os._exit)
# 2. data/restart_sentinel file appears (from Claude Code push & restart)

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Start wrapper with nohup in background (the wrapper itself loops forever)
cd "$SCRIPT_DIR"
nohup ./start-bot-wrapper.sh >> telegram.log 2>&1 &
echo "Bot wrapper started with PID $!"
