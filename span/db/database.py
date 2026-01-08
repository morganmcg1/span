"""SQLite database setup and operations."""

import json
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from span.db.models import (
    ContentType,
    ConversationMessage,
    CurriculumItem,
    ExtractedFact,
    LearnerProfile,
    LessonSession,
    LessonType,
    SkillDimensions,
    User,
    UserProgress,
)


SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    phone_number TEXT NOT NULL,
    telegram_id INTEGER NOT NULL,
    timezone TEXT DEFAULT 'Europe/Dublin',
    preferred_call_times TEXT DEFAULT '["09:50"]',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS curriculum_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    content_type TEXT NOT NULL,
    spanish TEXT NOT NULL,
    english TEXT NOT NULL,
    example_sentence TEXT,
    mexican_notes TEXT,
    topic TEXT NOT NULL,
    difficulty INTEGER DEFAULT 1,
    prerequisite_items TEXT DEFAULT '[]',
    skill_requirements TEXT DEFAULT '{}',
    skill_contributions TEXT DEFAULT '{}',
    cefr_level TEXT DEFAULT 'A1',
    prompt_types TEXT DEFAULT '[]',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS user_progress (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER REFERENCES users(id),
    item_id INTEGER REFERENCES curriculum_items(id),
    easiness_factor REAL DEFAULT 2.5,
    interval_days INTEGER DEFAULT 0,
    repetitions INTEGER DEFAULT 0,
    next_review TIMESTAMP,
    last_reviewed TIMESTAMP,
    UNIQUE(user_id, item_id)
);

CREATE TABLE IF NOT EXISTS lesson_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER REFERENCES users(id),
    lesson_type TEXT NOT NULL,
    topic TEXT,
    items_covered TEXT,
    performance_score REAL,
    duration_seconds INTEGER,
    transcript TEXT,
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS conversation_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER REFERENCES users(id),
    session_id INTEGER REFERENCES lesson_sessions(id),
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    channel TEXT NOT NULL,
    audio_path TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_progress_next_review ON user_progress(next_review);
CREATE INDEX IF NOT EXISTS idx_progress_user ON user_progress(user_id);
CREATE INDEX IF NOT EXISTS idx_messages_session ON conversation_messages(session_id);
CREATE INDEX IF NOT EXISTS idx_messages_user ON conversation_messages(user_id);
CREATE INDEX IF NOT EXISTS idx_items_topic ON curriculum_items(topic);

CREATE TABLE IF NOT EXISTS learner_profiles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER UNIQUE REFERENCES users(id),
    name TEXT,
    native_language TEXT DEFAULT 'English',
    location TEXT,
    level TEXT DEFAULT 'beginner',
    strong_topics TEXT DEFAULT '[]',
    weak_topics TEXT DEFAULT '[]',
    interests TEXT DEFAULT '[]',
    goals TEXT DEFAULT '[]',
    conversation_style TEXT DEFAULT 'casual',
    notes TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS extracted_facts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER REFERENCES users(id),
    fact_type TEXT NOT NULL,
    fact_value TEXT NOT NULL,
    source_channel TEXT,
    confidence REAL DEFAULT 1.0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_facts_user ON extracted_facts(user_id);
CREATE INDEX IF NOT EXISTS idx_facts_type ON extracted_facts(fact_type);

CREATE TABLE IF NOT EXISTS skill_dimensions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER UNIQUE REFERENCES users(id),
    vocabulary_recognition INTEGER DEFAULT 1,
    vocabulary_production INTEGER DEFAULT 1,
    pronunciation INTEGER DEFAULT 1,
    grammar_receptive INTEGER DEFAULT 1,
    grammar_productive INTEGER DEFAULT 1,
    conversational_flow INTEGER DEFAULT 1,
    cultural_pragmatics INTEGER DEFAULT 1,
    narration INTEGER DEFAULT 1,
    conditionals INTEGER DEFAULT 1,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_skills_user ON skill_dimensions(user_id);
"""


class Database:
    """SQLite database wrapper with thread-local connection pooling."""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._local = threading.local()
        if db_path != ":memory:":
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    def _get_connection(self) -> sqlite3.Connection:
        """Get or create a thread-local database connection."""
        if not hasattr(self._local, "conn") or self._local.conn is None:
            self._local.conn = sqlite3.connect(self.db_path)
            self._local.conn.row_factory = sqlite3.Row
        return self._local.conn

    @contextmanager
    def connection(self):
        """Get a database connection (reuses thread-local connection)."""
        conn = self._get_connection()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    def close(self) -> None:
        """Close the thread-local connection if open."""
        if hasattr(self._local, "conn") and self._local.conn is not None:
            self._local.conn.close()
            self._local.conn = None

    def init_schema(self) -> None:
        """Initialize the database schema and run migrations."""
        with self.connection() as conn:
            conn.executescript(SCHEMA)
            # Run migrations for existing databases
            self._migrate(conn)

    def _migrate(self, conn: sqlite3.Connection) -> None:
        """Run schema migrations for existing databases."""
        # Check if audio_path column exists in conversation_messages
        cursor = conn.execute("PRAGMA table_info(conversation_messages)")
        columns = {row[1] for row in cursor.fetchall()}
        if "audio_path" not in columns:
            conn.execute("ALTER TABLE conversation_messages ADD COLUMN audio_path TEXT")

        # Migrate curriculum_items for adaptive selection fields
        cursor = conn.execute("PRAGMA table_info(curriculum_items)")
        columns = {row[1] for row in cursor.fetchall()}
        if "prerequisite_items" not in columns:
            conn.execute("ALTER TABLE curriculum_items ADD COLUMN prerequisite_items TEXT DEFAULT '[]'")
        if "skill_requirements" not in columns:
            conn.execute("ALTER TABLE curriculum_items ADD COLUMN skill_requirements TEXT DEFAULT '{}'")
        if "skill_contributions" not in columns:
            conn.execute("ALTER TABLE curriculum_items ADD COLUMN skill_contributions TEXT DEFAULT '{}'")
        if "cefr_level" not in columns:
            conn.execute("ALTER TABLE curriculum_items ADD COLUMN cefr_level TEXT DEFAULT 'A1'")
        if "prompt_types" not in columns:
            conn.execute("ALTER TABLE curriculum_items ADD COLUMN prompt_types TEXT DEFAULT '[]'")

    # User operations
    def create_user(self, user: User) -> int:
        """Create a new user and return their ID."""
        with self.connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO users (phone_number, telegram_id, timezone, preferred_call_times)
                VALUES (?, ?, ?, ?)
                """,
                (user.phone_number, user.telegram_id, user.timezone, user.preferred_call_times),
            )
            return cursor.lastrowid

    def get_user(self, user_id: int) -> User | None:
        """Get a user by ID."""
        with self.connection() as conn:
            row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
            if row:
                return User(
                    id=row["id"],
                    phone_number=row["phone_number"],
                    telegram_id=row["telegram_id"],
                    timezone=row["timezone"],
                    preferred_call_times=row["preferred_call_times"],
                    created_at=datetime.fromisoformat(row["created_at"]) if row["created_at"] else None,
                )
            return None

    def get_user_by_telegram(self, telegram_id: int) -> User | None:
        """Get a user by Telegram ID."""
        with self.connection() as conn:
            row = conn.execute("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,)).fetchone()
            if row:
                return User(
                    id=row["id"],
                    phone_number=row["phone_number"],
                    telegram_id=row["telegram_id"],
                    timezone=row["timezone"],
                    preferred_call_times=row["preferred_call_times"],
                    created_at=datetime.fromisoformat(row["created_at"]) if row["created_at"] else None,
                )
            return None

    def get_first_user(self) -> User | None:
        """Get the first user in the database, if any."""
        with self.connection() as conn:
            row = conn.execute("SELECT * FROM users ORDER BY id LIMIT 1").fetchone()
            if row:
                return User(
                    id=row["id"],
                    phone_number=row["phone_number"],
                    telegram_id=row["telegram_id"],
                    timezone=row["timezone"],
                    preferred_call_times=row["preferred_call_times"],
                    created_at=datetime.fromisoformat(row["created_at"]) if row["created_at"] else None,
                )
            return None

    # Curriculum operations
    def add_curriculum_item(self, item: CurriculumItem) -> int:
        """Add a curriculum item and return its ID."""
        with self.connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO curriculum_items
                (content_type, spanish, english, example_sentence, mexican_notes, topic, difficulty,
                 prerequisite_items, skill_requirements, skill_contributions, cefr_level, prompt_types)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item.content_type.value,
                    item.spanish,
                    item.english,
                    item.example_sentence,
                    item.mexican_notes,
                    item.topic,
                    item.difficulty,
                    json.dumps(item.prerequisite_items),
                    json.dumps(item.skill_requirements),
                    json.dumps(item.skill_contributions),
                    item.cefr_level,
                    json.dumps(item.prompt_types),
                ),
            )
            return cursor.lastrowid

    def get_curriculum_item(self, item_id: int) -> CurriculumItem | None:
        """Get a curriculum item by ID."""
        with self.connection() as conn:
            row = conn.execute("SELECT * FROM curriculum_items WHERE id = ?", (item_id,)).fetchone()
            if row:
                return self._row_to_curriculum_item(row)
            return None

    def get_all_curriculum_items(self) -> list[CurriculumItem]:
        """Get all curriculum items."""
        with self.connection() as conn:
            rows = conn.execute("SELECT * FROM curriculum_items ORDER BY difficulty, topic").fetchall()
            return [self._row_to_curriculum_item(row) for row in rows]

    def get_curriculum_items_by_topic(self, topic: str) -> list[CurriculumItem]:
        """Get curriculum items by topic."""
        with self.connection() as conn:
            rows = conn.execute(
                "SELECT * FROM curriculum_items WHERE topic = ? ORDER BY difficulty",
                (topic,),
            ).fetchall()
            return [self._row_to_curriculum_item(row) for row in rows]

    def get_curriculum_item_by_spanish(self, spanish: str) -> CurriculumItem | None:
        """Get a curriculum item by its Spanish text (case-insensitive)."""
        with self.connection() as conn:
            row = conn.execute(
                "SELECT * FROM curriculum_items WHERE LOWER(spanish) = LOWER(?)",
                (spanish,),
            ).fetchone()
            if row:
                return self._row_to_curriculum_item(row)
            return None

    def get_user_vocabulary(self, user_id: int, limit: int = 20) -> list[CurriculumItem]:
        """Get vocabulary items the user is currently learning."""
        with self.connection() as conn:
            rows = conn.execute(
                """
                SELECT c.* FROM curriculum_items c
                JOIN user_progress p ON c.id = p.item_id
                WHERE p.user_id = ?
                ORDER BY p.last_reviewed IS NULL, p.last_reviewed DESC, c.difficulty
                LIMIT ?
                """,
                (user_id, limit),
            ).fetchall()
            return [self._row_to_curriculum_item(row) for row in rows]

    def _row_to_curriculum_item(self, row: sqlite3.Row) -> CurriculumItem:
        """Convert a database row to a CurriculumItem."""
        # Handle optional new fields for backward compatibility
        row_keys = row.keys()
        return CurriculumItem(
            id=row["id"],
            content_type=ContentType(row["content_type"]),
            spanish=row["spanish"],
            english=row["english"],
            example_sentence=row["example_sentence"],
            mexican_notes=row["mexican_notes"],
            topic=row["topic"],
            difficulty=row["difficulty"],
            prerequisite_items=(
                json.loads(row["prerequisite_items"])
                if "prerequisite_items" in row_keys and row["prerequisite_items"]
                else []
            ),
            skill_requirements=(
                json.loads(row["skill_requirements"])
                if "skill_requirements" in row_keys and row["skill_requirements"]
                else {}
            ),
            skill_contributions=(
                json.loads(row["skill_contributions"])
                if "skill_contributions" in row_keys and row["skill_contributions"]
                else {}
            ),
            cefr_level=(
                row["cefr_level"]
                if "cefr_level" in row_keys and row["cefr_level"]
                else "A1"
            ),
            prompt_types=(
                json.loads(row["prompt_types"])
                if "prompt_types" in row_keys and row["prompt_types"]
                else []
            ),
            created_at=datetime.fromisoformat(row["created_at"]) if row["created_at"] else None,
        )

    # Progress operations
    def get_or_create_progress(self, user_id: int, item_id: int) -> UserProgress:
        """Get or create progress for a user/item pair."""
        with self.connection() as conn:
            row = conn.execute(
                "SELECT * FROM user_progress WHERE user_id = ? AND item_id = ?",
                (user_id, item_id),
            ).fetchone()
            if row:
                return self._row_to_progress(row)
            # Create new progress
            cursor = conn.execute(
                """
                INSERT INTO user_progress (user_id, item_id, next_review)
                VALUES (?, ?, ?)
                """,
                (user_id, item_id, datetime.now().isoformat()),
            )
            return UserProgress(
                id=cursor.lastrowid,
                user_id=user_id,
                item_id=item_id,
                next_review=datetime.now(),
            )

    def update_progress(self, progress: UserProgress) -> None:
        """Update user progress."""
        with self.connection() as conn:
            conn.execute(
                """
                UPDATE user_progress
                SET easiness_factor = ?, interval_days = ?, repetitions = ?,
                    next_review = ?, last_reviewed = ?
                WHERE id = ?
                """,
                (
                    progress.easiness_factor,
                    progress.interval_days,
                    progress.repetitions,
                    progress.next_review.isoformat() if progress.next_review else None,
                    progress.last_reviewed.isoformat() if progress.last_reviewed else None,
                    progress.id,
                ),
            )

    def get_items_due_for_review(self, user_id: int, limit: int = 20) -> list[CurriculumItem]:
        """Get curriculum items due for review."""
        with self.connection() as conn:
            rows = conn.execute(
                """
                SELECT ci.* FROM curriculum_items ci
                JOIN user_progress up ON ci.id = up.item_id
                WHERE up.user_id = ? AND up.next_review <= ?
                ORDER BY up.next_review
                LIMIT ?
                """,
                (user_id, datetime.now().isoformat(), limit),
            ).fetchall()
            return [self._row_to_curriculum_item(row) for row in rows]

    def get_new_items_for_user(self, user_id: int, limit: int = 5) -> list[CurriculumItem]:
        """Get items the user hasn't learned yet."""
        with self.connection() as conn:
            rows = conn.execute(
                """
                SELECT ci.* FROM curriculum_items ci
                WHERE ci.id NOT IN (
                    SELECT item_id FROM user_progress WHERE user_id = ?
                )
                ORDER BY ci.difficulty, ci.id
                LIMIT ?
                """,
                (user_id, limit),
            ).fetchall()
            return [self._row_to_curriculum_item(row) for row in rows]

    def _row_to_progress(self, row: sqlite3.Row) -> UserProgress:
        """Convert a database row to UserProgress."""
        return UserProgress(
            id=row["id"],
            user_id=row["user_id"],
            item_id=row["item_id"],
            easiness_factor=row["easiness_factor"],
            interval_days=row["interval_days"],
            repetitions=row["repetitions"],
            next_review=datetime.fromisoformat(row["next_review"]) if row["next_review"] else None,
            last_reviewed=datetime.fromisoformat(row["last_reviewed"]) if row["last_reviewed"] else None,
        )

    # Session operations
    def create_session(self, session: LessonSession) -> int:
        """Create a lesson session and return its ID."""
        with self.connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO lesson_sessions
                (user_id, lesson_type, topic, items_covered, performance_score, duration_seconds, transcript, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session.user_id,
                    session.lesson_type.value,
                    session.topic,
                    session.items_covered,
                    session.performance_score,
                    session.duration_seconds,
                    session.transcript,
                    session.notes,
                ),
            )
            return cursor.lastrowid

    def get_recent_sessions(self, user_id: int, limit: int = 10) -> list[LessonSession]:
        """Get recent lesson sessions for a user."""
        with self.connection() as conn:
            rows = conn.execute(
                """
                SELECT * FROM lesson_sessions
                WHERE user_id = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (user_id, limit),
            ).fetchall()
            return [
                LessonSession(
                    id=row["id"],
                    user_id=row["user_id"],
                    lesson_type=LessonType(row["lesson_type"]),
                    topic=row["topic"],
                    items_covered=row["items_covered"],
                    performance_score=row["performance_score"],
                    duration_seconds=row["duration_seconds"],
                    transcript=row["transcript"],
                    notes=row["notes"],
                    created_at=datetime.fromisoformat(row["created_at"]) if row["created_at"] else None,
                )
                for row in rows
            ]

    # Conversation message operations
    def save_message(
        self,
        user_id: int,
        role: str,
        content: str,
        channel: str,
        session_id: int | None = None,
        audio_path: str | None = None,
    ) -> int:
        """Save a conversation message."""
        with self.connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO conversation_messages (user_id, session_id, role, content, channel, audio_path)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (user_id, session_id, role, content, channel, audio_path),
            )
            return cursor.lastrowid

    def get_conversation_history(
        self,
        user_id: int,
        limit: int = 20,
        channel: str | None = None,
    ) -> list[ConversationMessage]:
        """Get recent conversation history for a user across all channels."""
        with self.connection() as conn:
            if channel:
                rows = conn.execute(
                    """
                    SELECT * FROM conversation_messages
                    WHERE user_id = ? AND channel = ?
                    ORDER BY created_at DESC
                    LIMIT ?
                    """,
                    (user_id, channel, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT * FROM conversation_messages
                    WHERE user_id = ?
                    ORDER BY created_at DESC
                    LIMIT ?
                    """,
                    (user_id, limit),
                ).fetchall()
            # Return in chronological order (oldest first)
            return [self._row_to_message(row) for row in reversed(rows)]

    def _row_to_message(self, row: sqlite3.Row) -> ConversationMessage:
        """Convert a database row to a ConversationMessage."""
        return ConversationMessage(
            id=row["id"],
            user_id=row["user_id"],
            session_id=row["session_id"],
            role=row["role"],
            content=row["content"],
            channel=row["channel"],
            audio_path=row["audio_path"] if "audio_path" in row.keys() else None,
            created_at=datetime.fromisoformat(row["created_at"]) if row["created_at"] else None,
        )

    # Learner profile operations
    def get_or_create_learner_profile(self, user_id: int) -> LearnerProfile:
        """Get or create a learner profile for a user."""
        with self.connection() as conn:
            row = conn.execute(
                "SELECT * FROM learner_profiles WHERE user_id = ?",
                (user_id,),
            ).fetchone()
            if row:
                return self._row_to_profile(row)
            # Create new profile
            conn.execute(
                "INSERT INTO learner_profiles (user_id) VALUES (?)",
                (user_id,),
            )
            return LearnerProfile(user_id=user_id)

    def update_learner_profile(self, profile: LearnerProfile) -> None:
        """Update a learner profile."""
        with self.connection() as conn:
            conn.execute(
                """
                UPDATE learner_profiles SET
                    name = ?,
                    native_language = ?,
                    location = ?,
                    level = ?,
                    strong_topics = ?,
                    weak_topics = ?,
                    interests = ?,
                    goals = ?,
                    conversation_style = ?,
                    notes = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE user_id = ?
                """,
                (
                    profile.name,
                    profile.native_language,
                    profile.location,
                    profile.level,
                    json.dumps(profile.strong_topics),
                    json.dumps(profile.weak_topics),
                    json.dumps(profile.interests),
                    json.dumps(profile.goals),
                    profile.conversation_style,
                    profile.notes,
                    profile.user_id,
                ),
            )

    def _row_to_profile(self, row: sqlite3.Row) -> LearnerProfile:
        """Convert a database row to a LearnerProfile."""
        return LearnerProfile(
            id=row["id"],
            user_id=row["user_id"],
            name=row["name"],
            native_language=row["native_language"],
            location=row["location"],
            level=row["level"],
            strong_topics=json.loads(row["strong_topics"]) if row["strong_topics"] else [],
            weak_topics=json.loads(row["weak_topics"]) if row["weak_topics"] else [],
            interests=json.loads(row["interests"]) if row["interests"] else [],
            goals=json.loads(row["goals"]) if row["goals"] else [],
            conversation_style=row["conversation_style"],
            notes=row["notes"],
            updated_at=datetime.fromisoformat(row["updated_at"]) if row["updated_at"] else None,
            created_at=datetime.fromisoformat(row["created_at"]) if row["created_at"] else None,
        )

    # Extracted facts operations
    def save_extracted_fact(
        self,
        user_id: int,
        fact_type: str,
        fact_value: str,
        source_channel: str | None = None,
        confidence: float = 1.0,
    ) -> int:
        """Save an extracted fact."""
        with self.connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO extracted_facts (user_id, fact_type, fact_value, source_channel, confidence)
                VALUES (?, ?, ?, ?, ?)
                """,
                (user_id, fact_type, fact_value, source_channel, confidence),
            )
            return cursor.lastrowid

    def get_extracted_facts(
        self,
        user_id: int,
        fact_type: str | None = None,
        limit: int = 50,
    ) -> list[ExtractedFact]:
        """Get extracted facts for a user."""
        with self.connection() as conn:
            if fact_type:
                rows = conn.execute(
                    """
                    SELECT * FROM extracted_facts
                    WHERE user_id = ? AND fact_type = ?
                    ORDER BY created_at DESC
                    LIMIT ?
                    """,
                    (user_id, fact_type, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT * FROM extracted_facts
                    WHERE user_id = ?
                    ORDER BY created_at DESC
                    LIMIT ?
                    """,
                    (user_id, limit),
                ).fetchall()
            return [self._row_to_fact(row) for row in rows]

    def _row_to_fact(self, row: sqlite3.Row) -> ExtractedFact:
        """Convert a database row to an ExtractedFact."""
        return ExtractedFact(
            id=row["id"],
            user_id=row["user_id"],
            fact_type=row["fact_type"],
            fact_value=row["fact_value"],
            source_channel=row["source_channel"],
            confidence=row["confidence"],
            created_at=datetime.fromisoformat(row["created_at"]) if row["created_at"] else None,
        )

    # Skill dimensions operations
    def get_or_create_skill_dimensions(self, user_id: int) -> SkillDimensions:
        """Get or create skill dimensions for a user."""
        with self.connection() as conn:
            row = conn.execute(
                "SELECT * FROM skill_dimensions WHERE user_id = ?",
                (user_id,),
            ).fetchone()
            if row:
                return self._row_to_skill_dimensions(row)
            # Create new skill dimensions
            conn.execute(
                "INSERT INTO skill_dimensions (user_id) VALUES (?)",
                (user_id,),
            )
            return SkillDimensions(user_id=user_id)

    def update_skill_dimensions(self, skills: SkillDimensions) -> None:
        """Update skill dimensions for a user."""
        with self.connection() as conn:
            conn.execute(
                """
                UPDATE skill_dimensions SET
                    vocabulary_recognition = ?,
                    vocabulary_production = ?,
                    pronunciation = ?,
                    grammar_receptive = ?,
                    grammar_productive = ?,
                    conversational_flow = ?,
                    cultural_pragmatics = ?,
                    narration = ?,
                    conditionals = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE user_id = ?
                """,
                (
                    skills.vocabulary_recognition,
                    skills.vocabulary_production,
                    skills.pronunciation,
                    skills.grammar_receptive,
                    skills.grammar_productive,
                    skills.conversational_flow,
                    skills.cultural_pragmatics,
                    skills.narration,
                    skills.conditionals,
                    skills.user_id,
                ),
            )

    def _row_to_skill_dimensions(self, row: sqlite3.Row) -> SkillDimensions:
        """Convert a database row to SkillDimensions."""
        return SkillDimensions(
            id=row["id"],
            user_id=row["user_id"],
            vocabulary_recognition=row["vocabulary_recognition"],
            vocabulary_production=row["vocabulary_production"],
            pronunciation=row["pronunciation"],
            grammar_receptive=row["grammar_receptive"],
            grammar_productive=row["grammar_productive"],
            conversational_flow=row["conversational_flow"],
            cultural_pragmatics=row["cultural_pragmatics"],
            narration=row["narration"],
            conditionals=row["conditionals"],
            updated_at=datetime.fromisoformat(row["updated_at"]) if row["updated_at"] else None,
            created_at=datetime.fromisoformat(row["created_at"]) if row["created_at"] else None,
        )
