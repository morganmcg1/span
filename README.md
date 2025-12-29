# span

A Mexican Spanish language learning helper that uses voice calls and Telegram for conversational practice.

## Features

- **Voice calls** via Daily/PipeCat with OpenAI gpt-realtime for pronunciation feedback
- **Telegram bot** for text and voice note conversations
- **Adaptive curriculum** using SM-2 spaced repetition
- **Continuous memory** across sessions and channels

## Quick Start

```bash
# Install dependencies
uv sync

# Run tests
uv run pytest tests/ -v

# Start Telegram bot
uv run python -m span.telegram

# Start voice server
uv run python -m span.voice
```

## Environment Variables

```bash
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_USER_ID=your_numeric_user_id
OPENAI_API_KEY=your_openai_key
ANTHROPIC_API_KEY=your_anthropic_key
DAILY_API_KEY=your_daily_key
SPAN_SERVER_IP=135.181.102.44  # Production server
```

## Production Server

```bash
# SSH into the server
ssh root@$(grep SPAN_SERVER_IP .env | cut -d'=' -f2)
```

See [CLAUDE.md](CLAUDE.md) for full deployment and SSH hardening instructions.

## Documentation

See [CLAUDE.md](CLAUDE.md) for detailed architecture, curriculum design, and deployment instructions.
