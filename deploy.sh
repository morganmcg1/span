#!/bin/bash
set -e

SERVER="root@135.181.102.44"
REMOTE_DIR="/root/span"

# Detect if we're already on the server
if [[ "$(hostname)" == "span-server-ubuntu-4gb-hel1-3" ]]; then
    ON_SERVER=true
    run_cmd() { eval "$1"; }
    run_bg() { eval "$1"; }
else
    ON_SERVER=false
    run_cmd() { ssh $SERVER "$1"; }
    run_bg() { ssh -f $SERVER "$1"; }
fi

echo "🚀 Deploying span to production..."

# 1. Push local changes (only if not on server)
if [ "$ON_SERVER" = false ]; then
    echo "📤 Pushing to GitHub..."
    git push
fi

# 2. Pull and install any new deps
echo "📥 Pulling latest..."
run_cmd "cd $REMOTE_DIR && git pull && /root/.local/bin/uv sync"

# 3. Restart Telegram bot
echo "🤖 Restarting Telegram bot..."
run_bg "$REMOTE_DIR/start-bot.sh"

# 4. Restart Voice server
echo "🎤 Restarting Voice server..."
run_bg "$REMOTE_DIR/start-voice.sh"

# 5. Check services are running
echo "⏳ Waiting for services to start..."
sleep 4

echo ""
echo "📊 Service Status:"

BOT_STATUS=$(run_cmd "pgrep -f 'span.telegram' > /dev/null && echo '✅ running' || echo '❌ stopped'")
echo "  Telegram bot: $BOT_STATUS"

VOICE_STATUS=$(run_cmd "pgrep -f 'span.voice' > /dev/null && echo '✅ running' || echo '❌ stopped'")
echo "  Voice server: $VOICE_STATUS"

# 6. Quick health check on voice server
HEALTH=$(run_cmd "curl -s http://localhost:7860/health 2>/dev/null || echo 'failed'")
if [ "$HEALTH" = "failed" ]; then
    echo "  Voice health:  ❌ not responding"
else
    echo "  Voice health:  ✅ responding"
fi

echo ""
echo "📋 Recent logs:"
echo "--- Telegram bot ---"
run_cmd "tail -5 $REMOTE_DIR/telegram.log"
echo ""
echo "--- Voice server ---"
run_cmd "tail -5 $REMOTE_DIR/voice.log"

echo ""
echo "✅ Deploy complete!"
echo ""
echo "Commands:"
echo "  Bot logs:    ssh $SERVER \"tail -f $REMOTE_DIR/telegram.log\""
echo "  Voice logs:  ssh $SERVER \"tail -f $REMOTE_DIR/voice.log\""
echo "  Stop all:    ssh $SERVER \"killall python3 uvicorn\""
echo "  Status:      ssh $SERVER \"pgrep -a -f 'span.(telegram|voice)'\""
