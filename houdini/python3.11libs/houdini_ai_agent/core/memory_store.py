"""Three-layer memory store backed by SQLite.

Layers:
  1. Episodic — concrete task events (what happened)
  2. Semantic  — abstracted rules/knowledge (what was learned)
  3. Procedural — reusable strategies (how to do things)

Adapted from the reference project's brain-inspired memory system,
using our project's conventions (APP_CONFIG_DIR, embed_text, etc.).
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from houdini_ai_agent.core.config import APP_CONFIG_DIR
from houdini_ai_agent.core.embedding import (
    LocalEmbedder,
    bytes_to_vector,
    cosine_similarity,
    embed_text,
    get_embedder,
    vector_to_bytes,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MEMORY_CATEGORIES = (
    "node_creation", "parameter_setting", "error_fixing",
    "scene_analysis", "workflow", "vex_hscript", "performance",
    "user_preference",
)

ABSTRACTION_LEVELS = {
    0: "core_identity",      # Core personality/identity rules
    1: "critical_rules",     # Always-follow rules
    2: "experience",         # Regular learned experience
    3: "workflow_pattern",   # Reusable workflow patterns
    4: "observation",        # Uncertain observations
    5: "raw_fact",           # Unprocessed facts
}


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class EpisodicRecord:
    """A concrete task event."""
    id: str = ""
    timestamp: float = 0.0
    session_id: str = ""
    task_description: str = ""
    actions: List[Dict[str, Any]] = field(default_factory=list)
    result_summary: str = ""
    success: bool = True
    error_count: int = 0
    retry_count: int = 0
    reward_score: float = 0.0
    importance: float = 1.0
    tags: List[str] = field(default_factory=list)
    _embedding: List[float] = field(default_factory=list)

    def __post_init__(self):
        if not self.id:
            self.id = uuid.uuid4().hex[:12]
        if not self.timestamp:
            self.timestamp = time.time()


@dataclass
class SemanticRecord:
    """An abstracted rule or piece of knowledge."""
    id: str = ""
    created_at: float = 0.0
    updated_at: float = 0.0
    rule: str = ""
    source_episodes: List[str] = field(default_factory=list)
    confidence: float = 0.5
    activation_count: int = 0
    category: str = "experience"
    abstraction_level: int = 2
    _embedding: List[float] = field(default_factory=list)

    def __post_init__(self):
        if not self.id:
            self.id = uuid.uuid4().hex[:12]
        now = time.time()
        if not self.created_at:
            self.created_at = now
        if not self.updated_at:
            self.updated_at = now


@dataclass
class ProceduralRecord:
    """A reusable strategy."""
    id: str = ""
    strategy_name: str = ""
    description: str = ""
    priority: float = 0.5
    success_rate: float = 0.0
    usage_count: int = 0
    last_used: float = 0.0
    conditions: List[str] = field(default_factory=list)
    _embedding: List[float] = field(default_factory=list)

    def __post_init__(self):
        if not self.id:
            self.id = uuid.uuid4().hex[:12]


# ---------------------------------------------------------------------------
# MemoryStore
# ---------------------------------------------------------------------------

_DB_DIR = APP_CONFIG_DIR / "memory"
_DB_PATH = _DB_DIR / "agent_memory.db"


class MemoryStore:
    """Three-layer memory store backed by SQLite with vector search."""

    def __init__(self, db_path: Optional[Path] = None) -> None:
        self._db_path = Path(db_path) if db_path else _DB_PATH
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._embedder = get_embedder()
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        conn = self._get_conn()
        try:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS episodic_memory (
                    id TEXT PRIMARY KEY,
                    timestamp REAL,
                    session_id TEXT,
                    task_description TEXT,
                    actions TEXT,
                    result_summary TEXT,
                    success INTEGER,
                    error_count INTEGER,
                    retry_count INTEGER,
                    reward_score REAL,
                    importance REAL,
                    tags TEXT,
                    embedding BLOB
                );
                CREATE INDEX IF NOT EXISTS idx_episodic_session ON episodic_memory(session_id);
                CREATE INDEX IF NOT EXISTS idx_episodic_ts ON episodic_memory(timestamp);
                CREATE INDEX IF NOT EXISTS idx_episodic_importance ON episodic_memory(importance);

                CREATE TABLE IF NOT EXISTS semantic_memory (
                    id TEXT PRIMARY KEY,
                    created_at REAL,
                    updated_at REAL,
                    rule TEXT,
                    source_episodes TEXT,
                    confidence REAL,
                    activation_count INTEGER DEFAULT 0,
                    embedding BLOB,
                    category TEXT,
                    abstraction_level INTEGER DEFAULT 2
                );
                CREATE INDEX IF NOT EXISTS idx_semantic_cat ON semantic_memory(category);
                CREATE INDEX IF NOT EXISTS idx_semantic_conf ON semantic_memory(confidence);
                CREATE INDEX IF NOT EXISTS idx_semantic_level ON semantic_memory(abstraction_level);

                CREATE TABLE IF NOT EXISTS procedural_memory (
                    id TEXT PRIMARY KEY,
                    strategy_name TEXT,
                    description TEXT,
                    priority REAL,
                    success_rate REAL,
                    usage_count INTEGER DEFAULT 0,
                    last_used REAL,
                    embedding BLOB,
                    conditions TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_procedural_priority ON procedural_memory(priority);
            """)
            conn.commit()
        finally:
            conn.close()

    # -- Episodic Memory ---------------------------------------------------

    def add_episodic(self, record: EpisodicRecord) -> str:
        """Store an episodic memory record."""
        embedding = self._embedder.embed(record.task_description)
        record._embedding = embedding
        with self._lock:
            conn = self._get_conn()
            try:
                conn.execute(
                    "INSERT OR REPLACE INTO episodic_memory "
                    "(id, timestamp, session_id, task_description, actions, result_summary, "
                    "success, error_count, retry_count, reward_score, importance, tags, embedding) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        record.id, record.timestamp, record.session_id,
                        record.task_description,
                        json.dumps(record.actions, ensure_ascii=False),
                        record.result_summary,
                        int(record.success), record.error_count, record.retry_count,
                        record.reward_score, record.importance,
                        json.dumps(record.tags, ensure_ascii=False),
                        vector_to_bytes(embedding) if embedding else b"",
                    ),
                )
                conn.commit()
            finally:
                conn.close()
        return record.id

    def search_episodic(
        self, query: str, top_k: int = 5, session_id: Optional[str] = None,
    ) -> List[Tuple[EpisodicRecord, float]]:
        """Search episodic memory by query similarity."""
        query_vec = self._embedder.embed(query)
        conn = self._get_conn()
        try:
            sql = "SELECT * FROM episodic_memory"
            params: list = []
            if session_id:
                sql += " WHERE session_id = ?"
                params.append(session_id)
            sql += " ORDER BY importance DESC LIMIT 200"
            rows = conn.execute(sql, params).fetchall()
        finally:
            conn.close()

        results: List[Tuple[EpisodicRecord, float]] = []
        for row in rows:
            vec = bytes_to_vector(row["embedding"]) if row["embedding"] else []
            score = cosine_similarity(query_vec, vec) if vec else 0.0
            if score > 0.1:
                rec = EpisodicRecord(
                    id=row["id"], timestamp=row["timestamp"],
                    session_id=row["session_id"],
                    task_description=row["task_description"],
                    actions=json.loads(row["actions"] or "[]"),
                    result_summary=row["result_summary"],
                    success=bool(row["success"]),
                    error_count=row["error_count"],
                    retry_count=row["retry_count"],
                    reward_score=row["reward_score"],
                    importance=row["importance"],
                    tags=json.loads(row["tags"] or "[]"),
                    _embedding=vec,
                )
                results.append((rec, score))

        results.sort(key=lambda x: x[1], reverse=True)
        return results[:top_k]

    # -- Semantic Memory ---------------------------------------------------

    def add_semantic(self, record: SemanticRecord) -> str:
        """Store a semantic memory record."""
        embedding = self._embedder.embed(record.rule)
        record._embedding = embedding
        with self._lock:
            conn = self._get_conn()
            try:
                conn.execute(
                    "INSERT OR REPLACE INTO semantic_memory "
                    "(id, created_at, updated_at, rule, source_episodes, confidence, "
                    "activation_count, embedding, category, abstraction_level) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        record.id, record.created_at, record.updated_at,
                        record.rule,
                        json.dumps(record.source_episodes, ensure_ascii=False),
                        record.confidence, record.activation_count,
                        vector_to_bytes(embedding) if embedding else b"",
                        record.category, record.abstraction_level,
                    ),
                )
                conn.commit()
            finally:
                conn.close()
        return record.id

    def update_semantic(self, record_id: str, **kwargs: Any) -> None:
        """Update fields of a semantic memory record."""
        allowed = {"rule", "confidence", "activation_count", "category",
                    "abstraction_level", "updated_at"}
        updates = {k: v for k, v in kwargs.items() if k in allowed}
        if not updates:
            return
        updates["updated_at"] = time.time()
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        with self._lock:
            conn = self._get_conn()
            try:
                conn.execute(
                    f"UPDATE semantic_memory SET {set_clause} WHERE id = ?",
                    list(updates.values()) + [record_id],
                )
                conn.commit()
            finally:
                conn.close()

    def search_semantic(
        self, query: str, top_k: int = 5, category: Optional[str] = None,
        min_confidence: float = 0.1, abstraction_level: Optional[int] = None,
    ) -> List[Tuple[SemanticRecord, float]]:
        """Search semantic memory by query similarity."""
        query_vec = self._embedder.embed(query)
        conn = self._get_conn()
        try:
            sql = "SELECT * FROM semantic_memory WHERE confidence >= ?"
            params: list = [min_confidence]
            if category:
                sql += " AND category = ?"
                params.append(category)
            if abstraction_level is not None:
                sql += " AND abstraction_level = ?"
                params.append(abstraction_level)
            sql += " ORDER BY confidence DESC LIMIT 200"
            rows = conn.execute(sql, params).fetchall()
        finally:
            conn.close()

        results: List[Tuple[SemanticRecord, float]] = []
        for row in rows:
            vec = bytes_to_vector(row["embedding"]) if row["embedding"] else []
            score = cosine_similarity(query_vec, vec) if vec else 0.0
            if score > 0.15:
                rec = SemanticRecord(
                    id=row["id"], created_at=row["created_at"],
                    updated_at=row["updated_at"], rule=row["rule"],
                    source_episodes=json.loads(row["source_episodes"] or "[]"),
                    confidence=row["confidence"],
                    activation_count=row["activation_count"],
                    category=row["category"],
                    abstraction_level=row["abstraction_level"],
                    _embedding=vec,
                )
                results.append((rec, score))

        results.sort(key=lambda x: x[1], reverse=True)
        return results[:top_k]

    def get_core_memories(self, max_count: int = 5) -> List[SemanticRecord]:
        """Get level=0 core identity memories, sorted by confidence."""
        conn = self._get_conn()
        try:
            rows = conn.execute(
                "SELECT * FROM semantic_memory WHERE abstraction_level = 0 "
                "ORDER BY confidence DESC LIMIT ?",
                (max_count,),
            ).fetchall()
        finally:
            conn.close()
        return [
            SemanticRecord(
                id=r["id"], created_at=r["created_at"], updated_at=r["updated_at"],
                rule=r["rule"], source_episodes=json.loads(r["source_episodes"] or "[]"),
                confidence=r["confidence"], activation_count=r["activation_count"],
                category=r["category"], abstraction_level=r["abstraction_level"],
            )
            for r in rows
        ]

    def search_all_levels(
        self, query: str, category: Optional[str] = None,
        top_k: int = 5, min_confidence: float = 0.1,
    ) -> List[Tuple[SemanticRecord, float]]:
        """Cross-level search for the search_memory tool."""
        return self.search_semantic(query, top_k, category, min_confidence)

    def count_semantic(self) -> int:
        conn = self._get_conn()
        try:
            row = conn.execute("SELECT COUNT(*) as cnt FROM semantic_memory").fetchone()
            return row["cnt"] if row else 0
        finally:
            conn.close()

    # -- Procedural Memory -------------------------------------------------

    def add_procedural(self, record: ProceduralRecord) -> str:
        """Store a procedural memory record."""
        embedding = self._embedder.embed(f"{record.strategy_name} {record.description}")
        record._embedding = embedding
        with self._lock:
            conn = self._get_conn()
            try:
                conn.execute(
                    "INSERT OR REPLACE INTO procedural_memory "
                    "(id, strategy_name, description, priority, success_rate, "
                    "usage_count, last_used, embedding, conditions) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        record.id, record.strategy_name, record.description,
                        record.priority, record.success_rate, record.usage_count,
                        record.last_used or time.time(),
                        vector_to_bytes(embedding) if embedding else b"",
                        json.dumps(record.conditions, ensure_ascii=False),
                    ),
                )
                conn.commit()
            finally:
                conn.close()
        return record.id

    def update_procedural_usage(self, strategy_name: str, success: bool) -> None:
        """Update usage count and success rate for a strategy."""
        with self._lock:
            conn = self._get_conn()
            try:
                row = conn.execute(
                    "SELECT usage_count, success_rate FROM procedural_memory WHERE strategy_name = ?",
                    (strategy_name,),
                ).fetchone()
                if row:
                    count = row["usage_count"] + 1
                    # Exponential moving average for success rate
                    old_rate = row["success_rate"]
                    new_rate = old_rate * 0.8 + (1.0 if success else 0.0) * 0.2
                    conn.execute(
                        "UPDATE procedural_memory SET usage_count=?, success_rate=?, last_used=? "
                        "WHERE strategy_name=?",
                        (count, new_rate, time.time(), strategy_name),
                    )
                    conn.commit()
            finally:
                conn.close()

    def search_procedural(
        self, query: str, top_k: int = 3,
    ) -> List[Tuple[ProceduralRecord, float]]:
        """Search procedural memory by query similarity."""
        query_vec = self._embedder.embed(query)
        conn = self._get_conn()
        try:
            rows = conn.execute(
                "SELECT * FROM procedural_memory ORDER BY priority DESC LIMIT 100"
            ).fetchall()
        finally:
            conn.close()

        results: List[Tuple[ProceduralRecord, float]] = []
        for row in rows:
            vec = bytes_to_vector(row["embedding"]) if row["embedding"] else []
            score = cosine_similarity(query_vec, vec) if vec else 0.0
            if score > 0.15:
                rec = ProceduralRecord(
                    id=row["id"], strategy_name=row["strategy_name"],
                    description=row["description"], priority=row["priority"],
                    success_rate=row["success_rate"], usage_count=row["usage_count"],
                    last_used=row["last_used"],
                    conditions=json.loads(row["conditions"] or "[]"),
                    _embedding=vec,
                )
                results.append((rec, score))

        results.sort(key=lambda x: x[1], reverse=True)
        return results[:top_k]

    # -- Stats -------------------------------------------------------------

    def get_stats(self) -> Dict[str, Any]:
        """Return counts and summary statistics."""
        conn = self._get_conn()
        try:
            epi = conn.execute("SELECT COUNT(*) as c FROM episodic_memory").fetchone()["c"]
            sem = conn.execute("SELECT COUNT(*) as c FROM semantic_memory").fetchone()["c"]
            pro = conn.execute("SELECT COUNT(*) as c FROM procedural_memory").fetchone()["c"]
        finally:
            conn.close()
        return {
            "episodic_count": epi,
            "semantic_count": sem,
            "procedural_count": pro,
            "total": epi + sem + pro,
        }


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_store_instance: Optional[MemoryStore] = None
_store_lock = threading.Lock()


def get_memory_store() -> MemoryStore:
    """Get the global MemoryStore singleton."""
    global _store_instance
    if _store_instance is None:
        with _store_lock:
            if _store_instance is None:
                _store_instance = MemoryStore()
    return _store_instance
