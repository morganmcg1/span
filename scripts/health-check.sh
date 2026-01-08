#!/bin/bash
# Health check script for span services
#
# Usage:
#   On the server directly:  ./scripts/health-check.sh
#   From local machine:      ./scripts/health-check.sh --remote
#
# No SSH key needed when running directly on the server.

set -e

# If --remote flag, SSH into server and run this script there
if [ "$1" = "--remote" ] || [ "$1" = "-r" ]; then
    SERVER_IP="${SPAN_SERVER_IP:-135.181.102.44}"
    exec ssh "root@$SERVER_IP" "/home/span/span/scripts/health-check.sh"
fi

# Paths (allow override via SPAN_DIR)
SPAN_DIR="${SPAN_DIR:-/home/span/span}"
TELEGRAM_LOG="$SPAN_DIR/telegram.log"
VOICE_LOG="$SPAN_DIR/voice.log"

echo "========================================="
echo "  Span Health Check - $(date)"
echo "========================================="
echo ""

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check Telegram bot
echo -n "Telegram bot: "
if pgrep -f 'span.telegram' > /dev/null; then
    echo -e "${GREEN}running${NC}"
else
    echo -e "${RED}NOT RUNNING${NC}"
fi

# Check Voice server
echo -n "Voice server: "
if pgrep -f 'span.voice' > /dev/null; then
    echo -e "${GREEN}running${NC}"
else
    echo -e "${RED}NOT RUNNING${NC}"
fi

# Check voice server health endpoint
echo -n "Voice health:  "
if curl -s --max-time 5 http://localhost:7860/health | grep -q "ok"; then
    echo -e "${GREEN}responding${NC}"
else
    echo -e "${YELLOW}not responding${NC}"
fi

echo ""
echo "--- Recent Telegram Logs ---"
if [ -f "$TELEGRAM_LOG" ]; then
    tail -10 "$TELEGRAM_LOG"
else
    echo "(no log file found)"
fi

echo ""
echo "--- Recent Voice Logs ---"
if [ -f "$VOICE_LOG" ]; then
    tail -10 "$VOICE_LOG"
else
    echo "(no log file found)"
fi

echo ""
echo "--- Check for Errors ---"
echo -n "Telegram errors: "
if [ -f "$TELEGRAM_LOG" ]; then
    error_count=$(grep -ci "error\|exception\|traceback" "$TELEGRAM_LOG" 2>/dev/null | tail -1 || echo "0")
    if [ "$error_count" -gt 0 ]; then
        echo -e "${YELLOW}$error_count found${NC}"
    else
        echo -e "${GREEN}none${NC}"
    fi
else
    echo "no log file"
fi

echo -n "Voice errors:    "
if [ -f "$VOICE_LOG" ]; then
    error_count=$(grep -ci "error\|exception\|traceback" "$VOICE_LOG" 2>/dev/null | tail -1 || echo "0")
    if [ "$error_count" -gt 0 ]; then
        echo -e "${YELLOW}$error_count found${NC}"
    else
        echo -e "${GREEN}none${NC}"
    fi
else
    echo "no log file"
fi

echo ""
echo "========================================="
