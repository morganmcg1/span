# Memory & Context Management Research

Research on long-term memory systems for conversational AI, with focus on applying learnings to a language tutor that maintains context over months of interactions.

---

## Part 1: Long-Term Memory Architectures

### 1.1 Letta/MemGPT - "LLM as Operating System"

**Source**: [Letta GitHub](https://github.com/letta-ai/letta), [MemGPT Docs](https://docs.letta.com/concepts/memgpt/)

**Core Concept**: Treat LLM context like an OS manages RAM vs disk.

| Memory Tier | Description | Persistence |
|-------------|-------------|-------------|
| **Core Memory** | Always in prompt - persona, user info | In-context |
| **Working Memory** | Recent conversation turns | In-context |
| **Archival Memory** | Vector DB, retrieved on demand | Out-of-context |

**Self-Editing Memory**: The LLM updates its own memory using tool calls:
- `core_memory_append(section, content)` - Add to persona/human blocks
- `core_memory_replace(section, old, new)` - Update existing info
- `archival_memory_insert(content)` - Store for later retrieval
- `archival_memory_search(query)` - Retrieve relevant context

**Memory Blocks Example**:
```python
memory_blocks = [
    {"label": "persona", "value": "I am Lupita, a Mexican Spanish tutor..."},
    {"label": "human", "value": "Morgan is intermediate, likes slang, from Ireland..."}
]
```

**Key Insight**: Agent autonomously decides what to remember vs forget.

---

### 1.2 Mem0 - Extract-Update Pipeline

**Source**: [Mem0 Research](https://mem0.ai/research)

**Two-Phase Approach**:

1. **Extract Phase**: LLM identifies salient facts from conversation
   - Input: latest exchange + rolling summary + recent messages
   - Output: candidate memory facts

2. **Update Phase**: Compare against vector DB, then:
   - **ADD** - New fact not in memory
   - **UPDATE** - Fact exists but needs modification
   - **DELETE** - Fact contradicted by new info
   - **NOOP** - No change needed

**Store Facts, Not Messages**:
```
Raw: "User: My name is Morgan and I'm from Ireland"

Extracted Facts:
- {type: "name", value: "Morgan"}
- {type: "location", value: "Ireland"}
```

**Graph Variant (Mem0g)**: Stores entities + relationships as directed graph for multi-hop reasoning.

**Performance**: 26% improvement over OpenAI memory, 91% latency reduction vs full history.

---

### 1.3 LoCoMo Benchmark Findings

**Source**: [LoCoMo Paper](https://arxiv.org/abs/2402.17753)

Tested LLMs on 300-turn conversations over 35 sessions.

**Key Findings**:
- RAG helps but still lags human performance significantly
- Long-context models struggle with temporal/causal reasoning
- Structured memory (facts/events) outperforms raw retrieval
- LLMs often fail at "when" questions (temporal reasoning)

---

### 1.4 Language Tutor Specific Approaches

**Sources**: [Duolingo Research](https://research.duolingo.com/papers/settles.acl16.pdf), [Lingvist](https://lingvist.com/blog/spaced-repetition-in-learning/)

| Feature | Description |
|---------|-------------|
| **Per-word forgetting curves** | Each vocab item has individual decay rate |
| **Learner model** | Tracks strengths/weaknesses across skills |
| **Adaptive scheduling** | Review words at predicted forgetting point |
| **Contextual practice** | AI weaves practiced words into conversation |

---

## Part 2: Context Compaction in Coding Agents

Research on how coding agents handle context window limits - highly relevant for deciding what to extract and save.

### 2.1 Claude Code

**Source**: [Claude Code Compaction](https://stevekinney.com/courses/ai-development/claude-code-compaction)

**Trigger**: Manual `/compact` or automatic at ~95% capacity

**What Gets Preserved**:
- What was accomplished
- Current work in progress
- Files involved
- Next steps
- Key user requests or constraints

**Custom Instructions**: Users can guide summarization:
```
/compact only keep the names of the websites we reviewed
/compact preserve the coding patterns we established
```

**Warning**: Quality degrades with multiple compactions (cumulative information loss). Auto-compaction mid-task can cause agent to "go off the rails."

**Best Practice**: Compact at natural breakpoints (feature complete, bug fixed), not mid-task.

---

### 2.2 Gemini CLI

**Source**: [Gemini CLI Tips](https://addyo.substack.com/p/gemini-cli-tips-and-tricks)

**Key Distinction**:
| Command | Purpose | Persistence |
|---------|---------|-------------|
| `/compress` | Condense current session | Ephemeral |
| `/memory add` | Store in GEMINI.md | Permanent |

**Memory Survives Compression**: Facts in `/memory` persist through compression and across sessions.

**Compression Preserves**:
- Key facts and important discussion points
- Essential details from the conversation
- Critical context needed for future exchanges

**Compression Drops**:
- Granular minute-by-minute dialogue
- Verbose explanations already covered
- Redundant exchanges

---

### 2.3 OpenHands

**Source**: [OpenHands Condenser Docs](https://docs.openhands.dev/sdk/arch/condenser)

**Rolling Window Pattern**:
```
[KEEP: First N events (system prompts)]
[SUMMARIZE: Middle events → condensed summary]
[KEEP: Last M events (recent context)]
```

**Configuration**:
- `max_size`: Event threshold (default: 120)
- `keep_first`: Initial events to preserve (default: 4)
- `target_size`: Post-condensation size

**Condenser Types**:
1. **NoOpCondenser** - Pass-through, no compression
2. **LLMSummarizingCondenser** - LLM generates summary
3. **PipelineCondenser** - Chain multiple strategies

**Key Finding**: Simple observation masking (hiding old tool outputs) is as effective as LLM summarization for many tasks - cheaper and faster.

---

### 2.4 OpenAI Codex CLI

**Source**: [Context Compaction Research Gist](https://gist.github.com/badlogic/cd2ef65b0697c4dbe2d13fbecb0a0a5f)

**Mechanism**:
1. Apply dedicated summarization prompt
2. Rebuild history: initial context + recent messages (up to 20k tokens) + summary
3. Include note: "another language model produced this summary"

**Token Thresholds**: 180k-244k depending on model, with 95% safety margin.

---

### 2.5 Amp (Sourcegraph)

**Philosophy**: "Keep conversations short & focused" - no automatic compaction.

**Tools Instead of Compaction**:
- **Handoff** - Extract relevant info for new thread
- **Fork** - Duplicate conversation at a point
- **Thread references** - Selective extraction
- **Edit/restore** - Manual context management

---

## Part 3: Key Insights for Language Tutors

### 3.1 What Coding Agents Preserve (Applicable to Tutors)

| Coding Context | Language Tutor Equivalent |
|----------------|---------------------------|
| Files involved | Vocabulary practiced |
| Work in progress | Current lesson topic |
| Next steps | Next review items |
| User constraints | Learning preferences |
| Accomplished tasks | Mastered vocabulary |

### 3.2 Compaction Strategy Comparison

| Strategy | Pros | Cons | Best For |
|----------|------|------|----------|
| **LLM Summarization** | Semantic understanding | Expensive, slow, info loss | Important context |
| **Rolling Window** | Simple, fast | Loses old context | Recent focus |
| **Fact Extraction** | Structured, queryable | Misses nuance | Long-term memory |
| **Hybrid** | Best of both | Complex | Production systems |

### 3.3 When to Compress vs Extract

**Compress** (lossy, for context window):
- Detailed conversation flow
- Verbose explanations
- Trial-and-error attempts

**Extract to Long-term Memory** (preserved forever):
- User facts (name, location, goals)
- Vocabulary mastery levels
- Learning preferences
- Session summaries

---

## Part 4: Proposed Architecture for Span

### 4.1 Memory Tiers

```
┌─────────────────────────────────────────────────────────────┐
│                    CORE MEMORY (always in context)           │
├─────────────────────────────────────────────────────────────┤
│ persona_block: "Lupita - Mexican Spanish tutor, friendly..." │
│ learner_block: "Morgan: intermediate, good at slang,         │
│                struggles with subjunctive, from Ireland,     │
│                prefers casual conversation style"            │
└─────────────────────────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────┐
│                  WORKING MEMORY (recent context)             │
├─────────────────────────────────────────────────────────────┤
│ Last 5-10 messages (rolling window, oldest dropped)          │
└─────────────────────────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────┐
│               ARCHIVAL MEMORY (retrievable on demand)        │
├─────────────────────────────────────────────────────────────┤
│ • Session summaries: "Dec 28: Practiced greetings, good     │
│   pronunciation, struggled with 'qué onda' initially"        │
│ • Vocabulary progress: SM-2 data per word (already exists)   │
│ • Extracted facts: interests, goals, struggles               │
│ • Conversation highlights: memorable exchanges               │
└─────────────────────────────────────────────────────────────┘
```

### 4.2 Memory Operations

**Continuous Extraction** (async, every few turns):
```python
# Spin off async task to extract facts without blocking conversation
async def extract_facts_async(user_id: int, recent_messages: list):
    """Run in background - don't wait for completion."""
    facts = await claude.extract_facts(recent_messages)
    if facts:
        db.save_extracted_facts(user_id, facts)
        # Update learner profile with new insights
        await update_learner_profile(user_id, facts)

# Triggered every N messages or on significant events
asyncio.create_task(extract_facts_async(user_id, messages[-5:]))
```

**Why Continuous vs End-of-Session**:
- User may not reach "end" of session (disconnect, close app)
- Avoids losing everything if session crashes
- Smaller extraction batches = faster, cheaper
- Can detect milestones in real-time ("User just mastered 'qué onda'!")

**End of Session** (optional, for full summary):
```python
# Generate session summary if session formally ends
summary = claude.summarize_session(conversation, vocab_practiced)
db.save_session_summary(user_id, summary)
```

**Start of Session** (automatic):
```python
# 1. Load core memory blocks
persona = db.get_persona_block()
learner = db.get_learner_block(user_id)

# 2. Load recent raw messages (working memory)
recent = db.get_conversation_history(user_id, limit=10)

# 3. Optionally retrieve relevant archival memory
relevant_summaries = db.search_summaries(user_id, current_topic)

# 4. Build context
context = build_context(persona, learner, recent, relevant_summaries)
```

**During Session** (tools available):
```python
# Agent can query archival memory
@tool
def recall_vocabulary_history(word: str) -> dict:
    """Get practice history for a specific word."""
    return db.get_word_progress(user_id, word)

@tool
def recall_past_sessions(topic: str) -> list:
    """Find past sessions about a topic."""
    return db.search_sessions(user_id, topic)
```

### 4.3 Learner Profile Schema

```python
@dataclass
class LearnerProfile:
    # Basic info
    name: str
    native_language: str
    location: str

    # Learning status
    level: str  # beginner, intermediate, advanced
    started_at: datetime
    total_sessions: int

    # Strengths and weaknesses
    strong_topics: list[str]  # ["greetings", "slang"]
    weak_topics: list[str]    # ["subjunctive", "formal speech"]

    # Preferences
    conversation_style: str   # casual, structured, immersive
    interests: list[str]      # ["music", "travel", "food"]
    goals: list[str]          # ["conversational fluency", "travel prep"]

    # Learning patterns
    best_time_of_day: str
    average_session_length: int
    preferred_channel: str    # voice, telegram, both
```

### 4.4 Session Summary Schema

```python
@dataclass
class SessionSummary:
    session_id: int
    user_id: int
    channel: str              # voice, telegram
    timestamp: datetime
    duration_minutes: int

    # Content
    topic: str
    vocabulary_practiced: list[str]
    vocabulary_introduced: list[str]

    # Performance
    overall_quality: str      # excellent, good, needs_work
    pronunciation_notes: str | None
    grammar_notes: str | None

    # Key moments
    highlights: list[str]     # Memorable exchanges or breakthroughs
    struggles: list[str]      # Areas of difficulty

    # Generated summary (1-2 sentences)
    summary_text: str
```

### 4.5 Compaction Strategy for Span

**Trigger**: Continuous async extraction (every 5 turns) + optional end-of-session summary

**Process**:
1. **Continuous Extraction** → Async tasks extract facts every few messages
2. **Profile Updates** → Learner profile updated incrementally
3. **Keep Recent** → Last 20 raw messages for working memory
4. **Optional Summary** → Full session summary if session ends cleanly

**What Survives Forever**:
- Learner profile (continuously updated via async extraction)
- Session summaries (when session ends cleanly)
- Vocabulary progress (SM-2 data)
- Extracted facts (interests, goals, milestones)

**What Gets Dropped**:
- Raw conversation messages older than 20 turns
- Verbose explanations (facts extracted, raw dropped)
- Correction attempts (just keep outcome in profile)

---

## Part 5: Implementation Roadmap

### Phase 1: Learner Profile (Simple) ✅ COMPLETE
- [x] Add `learner_profiles` table
- [x] Load profile into context at session start
- [x] Profile auto-created on first interaction

### Phase 2: Continuous Fact Extraction ✅ COMPLETE
- [x] Add `extracted_facts` table
- [x] Async extraction every 5 messages (non-blocking)
- [x] Automatic profile updates from extracted facts
- [x] Works on both Voice and Telegram channels

### Phase 3: Shared Memory ✅ COMPLETE
- [x] Voice and Telegram share `conversation_messages` table
- [x] Last 20 messages loaded as working memory
- [x] Profile context included in both channels' system prompts

### Phase 4: Archival Retrieval (Future)
- [ ] Vector embeddings for summaries
- [ ] Semantic search for relevant past sessions
- [ ] Tools for agent to query history
- [ ] End-of-session summaries (optional enhancement)

---

## References

### Memory Systems
- [Letta/MemGPT GitHub](https://github.com/letta-ai/letta)
- [Mem0 Research](https://mem0.ai/research)
- [LoCoMo Benchmark](https://arxiv.org/abs/2402.17753)
- [A-Mem: Agentic Memory](https://arxiv.org/pdf/2502.12110)

### Coding Agent Compaction
- [Context Compaction Research Gist](https://gist.github.com/badlogic/cd2ef65b0697c4dbe2d13fbecb0a0a5f)
- [OpenHands Condenser Docs](https://docs.openhands.dev/sdk/arch/condenser)
- [Claude Code Compaction](https://stevekinney.com/courses/ai-development/claude-code-compaction)
- [Gemini CLI Context Engineering](https://aipositive.substack.com/p/a-look-at-context-engineering-in)

### Language Learning
- [Duolingo Spaced Repetition Model](https://research.duolingo.com/papers/settles.acl16.pdf)
- [Lingvist Memory Model](https://lingvist.com/blog/spaced-repetition-in-learning/)
