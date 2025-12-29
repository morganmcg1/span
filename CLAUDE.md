# Project: span - a Mexican Spanish language learning helper

This app helps people learn conversational Mexican Spanish through daily voice calls and Telegram messages. It uses spaced repetition for vocabulary and provides pronunciation feedback via AI voice conversations.

## Core Features
- **Voice calls** via Daily/PipeCat Cloud with OpenAI gpt-realtime for pronunciation feedback
- **Telegram bot** for text-based vocabulary practice and voice note conversations
- **Adaptive curriculum** using SM-2 spaced repetition algorithm
- **Focus**: Mexican Spanish - conversational skills, texting slang, pronunciation

## Tech Stack
- **Voice**: Daily (telephony) + OpenAI gpt-realtime (native speech understanding)
- **Text**: Anthropic Claude for Telegram text conversations
- **Voice Notes**: OpenAI gpt-realtime via WebSocket for Telegram voice notes
- **Database**: SQLite for user progress and curriculum
- **Framework**: PipeCat for voice pipeline orchestration

## API Services
| Service | Purpose |
|---------|---------|
| Daily | Voice calls via Pipecat Cloud |
| OpenAI | gpt-realtime for voice calls + Telegram voice notes |
| Anthropic | Claude for Telegram text chat |
| Telegram | Bot API for text + voice note lessons |

---

## Coding guidelines and philosophy
- Generate code that is simple and readable, avoid unnecessary abstractions and complexity. This is a research codebase so we want to be maintainable and readable.
- Avoid overly defensive coding, no need for a lot of `try, except` patterns, I want the code to fail if something is wrong so that I can fix it.
- Do not add demo-only flags or placeholder CLI options that gate real functionality (e.g., `--run` just to toggle execution); scripts should run their main logic directly.

## Dependency management
This project uses uv as dependency manager for python. Run scripts using `uv run script.py` instead of calling python directly. This is also true for tools like `uv run pytest`

## Argument parsing
Use `simple_parsing` as an argument parser for the scripts. Like this

```python
import simple_parsing as sp

@dataclass
class Args:
    """ Help string for this group of command-line arguments """
    arg1: str       # Help string for a required str argument
    arg2: int = 1   # Help string for arg2

args = sp.parse(Args)
```

## Typing
We are using modern python (3.12+) so no need to import annotations, you can also use `dict` and `list` and `a | b` or `a | None` instead of Optional, Union, Dict, List, etc...

## Printing and logging
Use rich.Console to print stuff on scripts, use Panel and console.rule to make stuff organized

## Debugging
When running scripts, use the `debug` flags if available, and ask to run the full pipeline (this enables faster iteration)

## Running Analysis
Ensure to always use performant code for running analysis, always use pandas best practices for speed and efficiency.

## Working with Weights & Biases - project and entity to use
When logging to `wandb` or `weave` from Weights & Biases, always log to the `milieu` entity and the `radio_analysis` project, unless specifically asked to log elsewhere

## Working with Jupyter notebooks
### Reading / visualizing pandas dataframes
When working with jupyter notebooks, remove truncation so we can print full outputs
```python
import pandas as pd
pd.set_option('display.max_columns', None)   # no column truncation
pd.set_option('display.width', None)         # keep each row on one line
pd.set_option('display.max_colwidth', None)  # don't truncate long string cells
```

### Autoreload
Prefer adding autoreload at the top cell of the notebook so that we don't have to restart the notebook when we make changes to our library
```python
%load_ext autoreload
%autoreload 2
```

## Running commands
Avoid asking the user to run commands unless its strictly necesary for the user to run it. Its fine to educate them and tell them the commands that are being run and why, but if you've been asked to achieve a task and there isn't a strong reason why you can't just run the command yourself, just run the command.

## AI system design
- Use OpenAI gpt-realtime for voice calls (handles STT + LLM + TTS natively via PipeCat/Daily)
- Use OpenAI gpt-realtime for Telegram voice notes (via WebSocket, single-turn audio exchange)
- Use Claude for text-based Telegram interactions
- Pronunciation feedback is handled natively by gpt-realtime (not a separate service)

---

## Voice Server

### Running the voice server
```bash
uv run python -m span.voice
```
Server runs on port 7860 by default.

### Voice testing endpoints
| Endpoint | Purpose |
|----------|---------|
| `/web` | Browser-based voice session - returns room URL to open in browser |
| `/dialout` | Phone dial-out (requires international calling for non-US numbers) |
| `/health` | Health check |

### Browser-based testing (recommended)
```bash
curl http://localhost:7860/web
# Returns: {"room_url": "https://...daily.co/XYZ", ...}
# Open the room_url in your browser, allow mic access, talk to bot
```

---

## Pipecat / OpenAI Realtime Configuration

### Model
Use `gpt-realtime-2025-08-28` (not `gpt-4o-realtime-preview`)

### Turn detection
Must use `type="server_vad"` (not `"semantic_vad"`):
```python
TurnDetection(type="server_vad")
```

### Session properties
```python
session_properties = SessionProperties(
    input_audio_transcription=InputAudioTranscription(model="whisper-1"),
    turn_detection=TurnDetection(type="server_vad"),
    instructions=system_prompt,
)
```

---

## Daily.co Setup

### API Key location
The Daily API key for Pipecat Cloud is in: **Pipecat Cloud > Settings > Telephony > Daily API Key**
(Not in the main API Keys section)

### International dial-out
Daily free tier only supports US/Canada dial-out. International numbers require contacting Daily sales.
Use browser-based testing (`/web` endpoint) as a free alternative.

---

## Memory System

The app uses a continuous async memory system to maintain context across sessions and channels (voice + Telegram).

### Architecture
See [docs/memory-research.md](docs/memory-research.md) for detailed research and design.

| Memory Tier | Description | Storage |
|-------------|-------------|---------|
| **Core Memory** | Learner profile (name, level, interests, goals) | `learner_profiles` table |
| **Working Memory** | Last 20 messages | `conversation_messages` table |
| **Archival Memory** | Extracted facts, milestones | `extracted_facts` table |

### How It Works
1. **Shared History**: Voice calls, Telegram text, and voice notes share the same conversation history
2. **Audio Context**: Voice note audio files are stored and re-injected as audio for pronunciation continuity
3. **Continuous Extraction**: Every 5 messages, Claude Sonnet extracts facts async (non-blocking)
4. **Profile Updates**: Extracted facts update the learner profile automatically
5. **Context Building**: Each session loads profile + last 15-20 messages (audio + text blended)

### Key Files
| File | Purpose |
|------|---------|
| `span/memory/extractor.py` | Async fact extraction service |
| `span/db/models.py` | `LearnerProfile`, `ExtractedFact`, `ConversationMessage` models |
| `span/db/database.py` | Profile, fact, and message persistence |
| `span/telegram/voice_handler.py` | OpenAI Realtime WebSocket client for voice notes |

---

## Telegram Bot

### Running the Telegram bot
```bash
uv run python -m span.telegram
```

### Required environment variables
```
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_USER_ID=your_numeric_user_id  # Get from @userinfobot
OPENAI_API_KEY=your_openai_key  # Required for voice notes
```

### Commands
| Command | Purpose |
|---------|---------|
| `/start` | Initialize bot |
| `/vocab` | Browse your vocabulary |
| `/review` | Get items due for review |
| `/new` | Learn new vocabulary |
| `/practice` | Start a practice conversation |
| `/stats` | See your progress |

### Voice Notes
Send a voice note to the bot and it will respond with a voice note from Lupita (the tutor).

**How it works:**
1. User sends voice note (OGG/Opus) via Telegram
2. Audio converted to PCM 24kHz, sent to OpenAI Realtime API via WebSocket
3. Recent chat history (text + previous voice notes as audio) injected for context
4. Response audio converted back to OGG, sent as voice note reply
5. Transcripts saved to shared conversation history

**Audio storage:**
- User voice notes stored in `data/voice_notes/` for pronunciation context
- Previous voice notes are re-injected as audio (not just text) so Lupita can reference how you pronounced things

---

## Adaptive Curriculum Framework

The curriculum system implements research-backed learning science principles to maximize language acquisition through conversation.

### Core Learning Philosophy

#### 1. "Whole Game" Teaching (Jeremy Howard/David Perkins)
Start with real communication, not isolated drills. The learner plays the "whole game" of having a conversation from day one, then iteratively deepens their skills:

- **Top-down learning**: Have a real conversation first, then learn the parts
- **Anti-elementitis**: Don't drill grammar tables before speaking—speak first
- **Iterative deepening**: Return to concepts with more detail over time
- **Immediate application**: Every new word/phrase is used in conversation right away

This is why span uses voice calls and natural chat rather than flashcards alone.

#### 2. Krashen's i+1 (Comprehensible Input)
Content should be *just beyond* current ability—not too easy (boring), not too hard (frustrating):

- **Zone of Proximal Development (ZPD)**: Select items learner is *ready* for
- **Compelling input**: Content must be interesting, not just comprehensible
- **Low affective filter**: Reduce anxiety through friendly conversation

#### 3. Swain's Output Hypothesis (Pushed Output)
Production (speaking/writing) is where acquisition happens, not just listening:

- **Noticing function**: Speaking reveals gaps in knowledge
- **Hypothesis testing**: Learner tries alternatives when stuck
- **Dialogue IS learning**: Conversation is the learning event itself

This is why span emphasizes voice calls and text production, not passive listening.

#### 4. Bjork's Desirable Difficulties
Strategically introduce challenges that improve long-term retention:

- **Interleaving**: Mix topics rather than blocking (e.g., greetings → food → greetings → transport)
- **Spacing**: Time between reviews (SM-2 algorithm handles this)
- **Retrieval practice**: Testing as a learning event, not just assessment
- **Variation**: Change conditions to strengthen encoding

#### 5. Andy Matuschak's Prompt Design
Well-designed prompts make remembering deliberate:

- **Focused**: One concept per prompt
- **Precise**: Unambiguous what's being asked
- **Consistent**: Same prompt = same expected response
- **Tractable**: Answerable from memory
- **Effortful**: Requires genuine recall, not recognition

Prompt progression moves from recognition → production → application as mastery develops.

### Skill Dimension Model

The curriculum tracks 9 skill dimensions, each with categorical levels 1-5:

```python
class SkillLevel(IntEnum):
    NONE = 1        # No exposure - cannot recognize or produce
    EXPOSURE = 2    # Has seen/heard - may recognize with hints
    RECOGNITION = 3 # Can understand when heard/read - cannot produce reliably
    PRODUCTION = 4  # Can produce with effort - may need time or make errors
    FLUENT = 5      # Automatic - produces quickly and accurately
```

**Why categorical (1-5) instead of continuous (0.0-1.0)?**
LLMs are better at assessing discrete categories with clear descriptions than choosing precise floats. Each level has explicit criteria the LLM can evaluate against.

| Dimension | What It Measures |
|-----------|------------------|
| `vocabulary_recognition` | Understand Spanish when heard/read |
| `vocabulary_production` | Express ideas in Spanish |
| `pronunciation` | Phoneme accuracy and prosody |
| `grammar_receptive` | Understand grammatical structures |
| `grammar_productive` | Use grammatical structures correctly |
| `conversational_flow` | Fillers, repairs, turn-taking |
| `cultural_pragmatics` | Register, politeness, when to use what |
| `narration` | Tell stories, sequence events in past tense |
| `conditionals` | Express hypotheticals ("si yo fuera...") |

**Priority Skills**: `narration` and `conditionals` enable the learner's goal of storytelling and expressing hypothetical situations.

### Curriculum Item Structure

Each curriculum item has metadata for adaptive selection:

```python
CurriculumItem(
    spanish="¿Qué onda?",
    english="What's up?",
    cefr_level="A1",

    # Prerequisites: minimum skill levels needed
    skill_requirements={},  # Entry-level, no prerequisites

    # What mastering this develops
    skill_contributions={
        "vocabulary_production": 3,   # Develops to RECOGNITION level
        "cultural_pragmatics": 3,     # Learn informal register
    },

    # Available prompt types
    prompt_types=["recognition", "production", "application"],
)
```

### Adaptive Selection Algorithm

The selector implements i+1 by computing "readiness" for each item:

```
Readiness Categories:
- NOT_READY: Too far ahead (gap > 2 levels) - skip for now
- STRETCH: Challenging but possible (gap = 2) - good for pushing
- READY: Perfect ZPD (gap = 1) - ideal selection
- MASTERED: Already knows this (gap ≤ 0) - for review only
```

Selection priority:
1. Items due for SM-2 review (spaced repetition)
2. New items in ZPD (READY or STRETCH)
3. Interleaved topics (mix greetings, food, transport—don't block)
4. Weighted toward weak areas (60% weak, 30% varied, 10% strong)

### Prompt Type Progression

Each item cycles through prompt types based on mastery (Matuschak-inspired):

| Repetitions | Prompt Type | Example |
|-------------|-------------|---------|
| 0 (new) | Recognition | "What does '¿Qué onda?' mean?" |
| 1-2 | Cued Production | "How would you say 'what's up'? (hint: onda)" |
| 3-5 | Free Production | "Greet me casually in Mexican Spanish" |
| 6+ | Application | [Novel scenario requiring the phrase] |

### Mastery Criteria

Skills advance based on consecutive correct responses:

| Transition | Requirement |
|------------|-------------|
| NONE → EXPOSURE | 1 correct encounter |
| EXPOSURE → RECOGNITION | 2 correct in context |
| RECOGNITION → PRODUCTION | 2 correct productions |
| PRODUCTION → FLUENT | 3 correct, each < 3 seconds |

### Key Implementation Files

| File | Purpose |
|------|---------|
| `span/db/models.py` | SkillLevel, SkillDimensions, CurriculumItem models |
| `span/curriculum/selector.py` | ZPD-based item selection, readiness computation |
| `span/curriculum/scheduler.py` | Daily plan generation with interleaving |
| `span/curriculum/prompts.py` | Prompt type selection and generation |
| `span/curriculum/content.py` | Seed curriculum items with metadata |
| `span/curriculum/taxonomy.py` | Skill level descriptions for LLM assessment |
| `span/voice/tools.py` | Skill tracking during voice practice |
| `span/memory/extractor.py` | Extract skill indicators from conversation |

### Adding New Curriculum Content

When adding new items, follow these principles:

1. **Identify the skill gap**: What can learners NOT do that they need to?
2. **Determine prerequisites**: What skill levels are required to attempt this?
3. **Write for ZPD**: Item should be achievable with effort (i+1)
4. **Include Mexican context**: Every item should have `mexican_notes`
5. **Design for production**: How will they USE this in conversation?
6. **Create prompt variants**: Recognition, production, and application scenarios

**Content Layers by CEFR Level:**

| Layer | CEFR | Focus |
|-------|------|-------|
| Foundation | A1 | Survival phrases, greetings, numbers 1-10, basic courtesy |
| Expansion | A1-A2 | Mexican expressions, texting, fillers, questions |
| Consolidation | A2 | Food, transport, money, basic past tense |
| Independence | A2-B1 | Opinions, preferences, imperfect vs preterite |
| Storytelling | B1 | **Narration and conditionals** (user priority) |
| Fluency | B1+ | Abstract topics, idioms, complex grammar |

### Storytelling & Conditionals (B1 Priority)

These skills enable the user's goal of telling stories and expressing hypotheticals:

**Narration skill progression:**
| Level | Description | Example |
|-------|-------------|---------|
| 1 | Cannot sequence events | Only uses present tense |
| 2 | Basic past tense attempts | "Yo ir al mercado ayer" (errors) |
| 3 | Understands stories told to them | Follows but can't retell |
| 4 | Can narrate with effort | Uses preterite, some time markers |
| 5 | Fluent storytelling | Natural preterite/imperfect, time markers |

Key narration vocabulary:
- Time markers: "primero", "luego", "después", "de repente", "mientras"
- Story starters: "Un día...", "Hace tiempo...", "¿Sabes qué pasó?"
- Emotional color: "¡No lo vas a creer!", "Fue increíble"

**Conditionals skill progression:**
| Level | Description | Example |
|-------|-------------|---------|
| 1 | No hypothetical constructions | Only states facts |
| 2 | Recognizes conditional intent | Understands but can't produce |
| 3 | Real conditionals only | "Si tengo tiempo, voy" |
| 4 | Hypothetical present with effort | "Si yo fuera rico, compraría..." |
| 5 | Natural hypotheticals | Smooth subjunctive + conditional |

Key conditional patterns:
- Real: "Si tengo tiempo, voy a ir" (present + future)
- Hypothetical present: "Si tuviera dinero, viajaría" (imperfect subjunctive + conditional)
- Wishes: "Ojalá pudiera...", "Me gustaría..."

### Research Sources

- [Andy Matuschak: How to write good prompts](https://andymatuschak.org/prompts/)
- [David Perkins: Making Learning Whole](https://www.gse.harvard.edu/ideas/usable-knowledge/09/01/whole-game)
- [Jeremy Howard/fast.ai: Top-down teaching](https://www.fast.ai/posts/2016-10-08-teaching-philosophy/)
- [Krashen's Input Hypothesis](https://en.wikipedia.org/wiki/Input_hypothesis)
- [Swain's Output Hypothesis](https://en.wikipedia.org/wiki/Comprehensible_output)
- [Bjork's Desirable Difficulties](https://bjorklab.psych.ucla.edu/)

---

## Testing

### Running Tests

```bash
# Run all tests
uv run pytest tests/ -v

# Run specific test file
uv run pytest tests/test_database.py -v

# Run tests matching a pattern
uv run pytest tests/ -v -k "skill"
```

### Test Coverage

| Test File | What It Tests |
|-----------|---------------|
| `tests/test_database.py` | Database CRUD, migrations, skill dimensions |
| `tests/test_scheduler.py` | Daily plan generation, topic selection, exercises |
| `tests/test_sm2.py` | Spaced repetition algorithm |
| `tests/test_selector.py` | ZPD readiness computation, item selection |
| `tests/test_taxonomy.py` | Skill levels, assessment prompts |

### Integration Test Script

The curriculum flow can be tested end-to-end without voice calls:

```bash
# Basic test
uv run python scripts/test_curriculum_flow.py

# Verbose output showing ZPD selection
uv run python scripts/test_curriculum_flow.py --verbose

# Include memory extraction test (requires ANTHROPIC_API_KEY)
uv run python scripts/test_curriculum_flow.py --test-extraction
```

This script tests:
1. Initial skill dimensions (all start at level 1)
2. SM-2 scheduling (intervals increase with quality)
3. Skill advancement (dimensions can be updated)
4. ZPD item selection (items selected based on readiness)
5. Skill-based selection (different skills = different items)
6. Memory extraction (optional, extracts facts from conversation)

### Testing Voice Bot Locally

```bash
# 1. Start the voice server
uv run python -m span.voice

# 2. Get a browser session URL
curl http://localhost:7860/web
# Returns: {"room_url": "https://...daily.co/XYZ", ...}

# 3. Open room_url in browser, allow mic, talk to Lupita
```

### Verifying Skill Tracking Works

After a voice session, check the database:

```bash
# View skill dimensions for user 1
uv run python -c "
from span.db.database import Database
from span.db.models import SkillLevel

db = Database('data/span.db')
skills = db.get_or_create_skill_dimensions(1)

for name in ['vocabulary_production', 'pronunciation', 'narration', 'conditionals']:
    level = getattr(skills, name)
    print(f'{name}: {level} ({SkillLevel(level).name})')
"
```

### Database State Inspection

```bash
# Check curriculum items count
sqlite3 data/span.db "SELECT COUNT(*) FROM curriculum_items"

# View recent sessions
sqlite3 data/span.db "SELECT * FROM lesson_sessions ORDER BY created_at DESC LIMIT 5"

# Check user progress
sqlite3 data/span.db "SELECT ci.spanish, up.repetitions, up.interval_days, up.next_review
FROM user_progress up
JOIN curriculum_items ci ON up.item_id = ci.id
WHERE up.user_id = 1
ORDER BY up.next_review LIMIT 10"
```

---

## Deployment (Hetzner)

### Server Access

The production server IP is stored in `.env` as `SPAN_SERVER_IP`.

```bash
# SSH into the server
ssh root@$(grep SPAN_SERVER_IP .env | cut -d'=' -f2)

# Or manually
ssh root@135.181.102.44
```

Server name: `span-server-ubuntu-4gb-hel1-3`

### Server Setup

Create a Hetzner Cloud server with:
- Ubuntu 22.04 or 24.04
- Add your SSH public key (`~/.ssh/id_rsa.pub` or `~/.ssh/id_ed25519.pub`)
- Skip cloud-init (configure manually)

### Firewall Rules (Inbound)

Configure in Hetzner Cloud Console > Firewalls:

| Source | Protocol | Port | Purpose |
|--------|----------|------|---------|
| Any IPv4/IPv6 | ICMP | - | Ping |
| Any IPv4/IPv6 | TCP | 80 | HTTP |
| Any IPv4/IPv6 | TCP | 443 | HTTPS |
| Any IPv4/IPv6 | TCP | 22 | SSH (harden below) |

**Outbound:** Leave as "all allowed" - the app needs to reach OpenAI, Anthropic, Telegram, and Daily APIs.

### SSH Hardening (Required)

After first SSH login, run these commands:

```bash
# 1. Disable password auth (key-only)
sudo sed -i 's/#PasswordAuthentication yes/PasswordAuthentication no/' /etc/ssh/sshd_config
sudo sed -i 's/PasswordAuthentication yes/PasswordAuthentication no/' /etc/ssh/sshd_config

# 2. Disable root login
sudo sed -i 's/PermitRootLogin yes/PermitRootLogin no/' /etc/ssh/sshd_config

# 3. Restart SSH (Ubuntu uses 'ssh' not 'sshd')
sudo systemctl restart ssh

# 4. Install fail2ban (auto-bans IPs after failed attempts)
sudo apt update && sudo apt install -y fail2ban
sudo systemctl enable fail2ban
```

**Important:** Ensure you can SSH with your key before running step 3. Don't lock yourself out.

### Why Not Restrict SSH by IP?

If you access from multiple locations (home, travel, mobile via Telegram browser, VPN), IP whitelisting is impractical. Key-only auth + fail2ban provides equivalent security without the hassle.

### Deploying Updates

```bash
# One command to deploy everything
./deploy.sh
```

This script:
1. Pushes local changes to GitHub
2. Pulls on server + installs new deps (`uv sync`)
3. Kills existing bot, starts new one with `nohup` + `disown`
4. Verifies bot is running
5. Shows recent logs and helpful commands

**Note for AI assistants:** Backgrounding processes over SSH is tricky. The deploy script uses:
1. A helper script on the server (`/root/span/start-bot.sh`) that handles nohup/backgrounding
2. `ssh -f` to fork SSH to background immediately

If you need to manually restart:
```bash
ssh -f root@135.181.102.44 "/root/span/start-bot.sh"
```

GitHub PAT is embedded in the git remote URL on the server (already configured).

### Checking Logs

```bash
# View Telegram bot logs
ssh root@135.181.102.44 "tail -50 /root/span/telegram.log"

# Follow logs live
ssh root@135.181.102.44 "tail -f /root/span/telegram.log"
```

### Starting/Stopping Services

```bash
# Stop Telegram bot
ssh root@135.181.102.44 "pkill -f 'span.telegram'"

# Start Telegram bot
ssh root@135.181.102.44 "cd /root/span && nohup /root/.local/bin/uv run python -m span.telegram > telegram.log 2>&1 &"

# Check if running
ssh root@135.181.102.44 "pgrep -f 'span.telegram' && echo 'Running' || echo 'Not running'"
```
