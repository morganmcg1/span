#!/bin/bash
set -euo pipefail

SERVER="root@135.181.102.44"
REMOTE_DIR="/home/span/span"
SPAN_USER="span"

# Detect if we're already on the server
if [[ "$(hostname)" == "span-server-ubuntu-4gb-hel1-3" ]]; then
    ON_SERVER=true
    run_cmd() { eval "$1"; }
    run_bg() { eval "$1"; }
    run_as_span() { su - $SPAN_USER -c "$1"; }
else
    ON_SERVER=false
    run_cmd() { ssh $SERVER "$1"; }
    run_as_span() { ssh $SERVER "su - $SPAN_USER -c '$1'"; }
fi

run_or_die() {
    local cmd="$1"
    if ! run_cmd "$cmd"; then
        echo "❌ Command failed: $cmd"
        exit 1
    fi
}

echo "🚀 Deploying span to production..."

# 1. Push local changes (only if not on server)
if [ "$ON_SERVER" = false ]; then
    echo "📤 Pushing to GitHub..."
    if ! git push; then
        echo "❌ git push failed. Aborting deploy."
        exit 1
    fi
fi

# 2. Pull and install any new deps
echo "📥 Pulling latest..."
run_or_die "su - $SPAN_USER -c 'cd $REMOTE_DIR && git pull && /home/span/.local/bin/uv sync'"

# 3. Restart Telegram bot (runs as span user, not root, for Claude Code permissions)
echo "🤖 Restarting Telegram bot..."
# Kill any existing bot/wrapper processes (avoid matching this shell)
run_cmd "pkill -f '[s]pan.telegram' || true; pkill -f '[s]tart-bot-wrapper' || true"
sleep 1
# Start bot as span user using helper script (wrapper backgrounds itself)
run_as_span "$REMOTE_DIR/start-bot.sh"

# 4. Restart Voice server (still runs as root for now)
echo "🎤 Restarting Voice server..."
run_or_die "$REMOTE_DIR/start-voice.sh"

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
run_as_span "tail -5 $REMOTE_DIR/telegram.log || true"
echo ""
echo "--- Voice server ---"
run_cmd "tail -5 $REMOTE_DIR/voice.log || true"

echo ""
echo "✅ Deploy complete!"
echo ""
echo "Commands:"
echo "  Bot logs:    ssh $SERVER \"su - span -c 'tail -f $REMOTE_DIR/telegram.log'\""
echo "  Voice logs:  ssh $SERVER \"tail -f $REMOTE_DIR/voice.log\""
echo "  Stop all:    ssh $SERVER \"pkill -f 'span.telegram'; pkill -f 'span.voice'\""
echo "  Status:      ssh $SERVER \"pgrep -a -f 'span.(telegram|voice)'\""
