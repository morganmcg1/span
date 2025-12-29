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

# 3. Restart Telegram bot
echo "🤖 Restarting Telegram bot..."
ssh $SERVER "pkill -f 'span.telegram' || true"
ssh $SERVER "cd $REMOTE_DIR && nohup /root/.local/bin/uv run python -m span.telegram > telegram.log 2>&1 &"

# 4. Check it's running
sleep 2
ssh $SERVER "pgrep -f 'span.telegram' > /dev/null && echo '✅ Telegram bot running' || echo '❌ Telegram bot failed to start'"

echo ""
echo "📋 Recent logs:"
ssh $SERVER "tail -10 $REMOTE_DIR/telegram.log"

echo ""
echo "✅ Deploy complete!"
