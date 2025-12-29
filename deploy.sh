#!/bin/bash
set -e

SERVER="root@135.181.102.44"
REMOTE_DIR="/root/span"

echo "🚀 Deploying span to production..."

# 1. Push local changes
echo "📤 Pushing to GitHub..."
git push

# 2. Pull on server and install any new deps
echo "📥 Pulling on server..."
ssh $SERVER "cd $REMOTE_DIR && git pull && /root/.local/bin/uv sync"

# 3. Restart Telegram bot using ssh -f (fork to background)
echo "🤖 Restarting Telegram bot..."
ssh -f $SERVER "$REMOTE_DIR/start-bot.sh"

# 4. Check it's running (give it time to start)
echo "⏳ Waiting for bot to start..."
sleep 4

STATUS=$(ssh $SERVER "pgrep -f 'span.telegram' > /dev/null && echo 'running' || echo 'stopped'")
if [ "$STATUS" = "running" ]; then
    echo "✅ Telegram bot running"
else
    echo "❌ Telegram bot failed to start"
    echo "Check logs: ssh $SERVER \"tail -50 $REMOTE_DIR/telegram.log\""
    exit 1
fi

echo ""
echo "📋 Recent logs:"
ssh $SERVER "tail -10 $REMOTE_DIR/telegram.log"

echo ""
echo "✅ Deploy complete!"
echo ""
echo "Commands:"
echo "  Logs:    ssh $SERVER \"tail -f $REMOTE_DIR/telegram.log\""
echo "  Stop:    ssh $SERVER \"killall python3\""
echo "  Status:  ssh $SERVER \"pgrep -f span.telegram && echo running || echo stopped\""
