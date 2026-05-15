"""Growth tracker — monitors agent performance trends and personality formation.

Records task metrics over time and computes growth curves, skill confidence
levels, and personality descriptions that can be injected into system prompts.
"""

from __future__ import annotations

import json
import math
import sqlite3
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from houdini_ai_agent.core.config import APP_CONFIG_DIR


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class TaskMetric:
    """Metric data for a single completed task."""
    timestamp: float = 0.0
    success: bool = True
    tool_count: int = 0
    error_count: int = 0
    retry_count: int = 0
    duration: float = 0.0
    reward_score: float = 0.0
    tags: List[str] = field(default_factory=list)

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = time.time()


# ---------------------------------------------------------------------------
# GrowthTracker
# ---------------------------------------------------------------------------

_GROWTH_DB = APP_CONFIG_DIR / "memory" / "growth.db"


class GrowthTracker:
    """Tracks agent performance trends and personality over time."""

    def __init__(self, db_path: Optional[Path] = None) -> None:
        self._db_path = Path(db_path) if db_path else _GROWTH_DB
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._skill_confidence: Dict[str, float] = {}
        self._personality_cache: Optional[str] = None
        self._personality_cache_time: float = 0.0
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        conn = self._get_conn()
        try:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS task_metrics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp REAL,
                    success INTEGER,
                    tool_count INTEGER,
                    error_count INTEGER,
                    retry_count INTEGER,
                    duration REAL,
                    reward_score REAL,
                    tags TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_metrics_ts ON task_metrics(timestamp);

                CREATE TABLE IF NOT EXISTS skill_confidence (
                    skill TEXT PRIMARY KEY,
                    confidence REAL,
                    usage_count INTEGER DEFAULT 0,
                    last_updated REAL
                );
            """)
            conn.commit()
        finally:
            conn.close()

    # -- Task recording ----------------------------------------------------

    def record_task(self, metric: TaskMetric) -> None:
        """Record a task metric."""
        with self._lock:
            conn = self._get_conn()
            try:
                conn.execute(
                    "INSERT INTO task_metrics "
                    "(timestamp, success, tool_count, error_count, retry_count, "
                    "duration, reward_score, tags) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        metric.timestamp, int(metric.success), metric.tool_count,
                        metric.error_count, metric.retry_count, metric.duration,
                        metric.reward_score,
                        json.dumps(metric.tags, ensure_ascii=False),
                    ),
                )
                conn.commit()
            finally:
                conn.close()

        # Update skill confidence for tags
        for tag in metric.tags:
            self._update_skill(tag, metric.success)

        # Invalidate personality cache
        self._personality_cache = None

    def _update_skill(self, skill: str, success: bool) -> None:
        """Update confidence for a skill tag using exponential moving average."""
        with self._lock:
            conn = self._get_conn()
            try:
                row = conn.execute(
                    "SELECT confidence, usage_count FROM skill_confidence WHERE skill = ?",
                    (skill,),
                ).fetchone()
                if row:
                    old_conf = row["confidence"]
                    count = row["usage_count"] + 1
                    new_conf = old_conf * 0.85 + (1.0 if success else 0.0) * 0.15
                    conn.execute(
                        "UPDATE skill_confidence SET confidence=?, usage_count=?, last_updated=? "
                        "WHERE skill=?",
                        (new_conf, count, time.time(), skill),
                    )
                else:
                    conn.execute(
                        "INSERT INTO skill_confidence (skill, confidence, usage_count, last_updated) "
                        "VALUES (?, ?, 1, ?)",
                        (skill, 1.0 if success else 0.0, time.time()),
                    )
                conn.commit()
            finally:
                conn.close()

    def update_skill_confidence_batch(self, updates: Dict[str, float]) -> None:
        """Batch update skill confidence from reflection results."""
        for skill, confidence in updates.items():
            with self._lock:
                conn = self._get_conn()
                try:
                    conn.execute(
                        "INSERT OR REPLACE INTO skill_confidence (skill, confidence, usage_count, last_updated) "
                        "VALUES (?, ?, COALESCE((SELECT usage_count FROM skill_confidence WHERE skill=?), 0), ?)",
                        (skill, confidence, skill, time.time()),
                    )
                    conn.commit()
                finally:
                    conn.close()

    # -- Metrics query -----------------------------------------------------

    def get_growth_metrics(self, days: int = 30) -> Dict[str, Any]:
        """Get growth metrics for the last N days."""
        cutoff = time.time() - days * 86400.0
        conn = self._get_conn()
        try:
            rows = conn.execute(
                "SELECT * FROM task_metrics WHERE timestamp >= ? ORDER BY timestamp",
                (cutoff,),
            ).fetchall()
        finally:
            conn.close()

        if not rows:
            return {"success_rate": 0.0, "total_tasks": 0, "avg_tools": 0.0, "avg_reward": 0.0}

        total = len(rows)
        successes = sum(1 for r in rows if r["success"])
        avg_tools = sum(r["tool_count"] for r in rows) / total
        avg_reward = sum(r["reward_score"] for r in rows) / total
        avg_errors = sum(r["error_count"] for r in rows) / total

        # Trend: compare first half vs second half
        mid = total // 2
        first_half_success = sum(1 for r in rows[:mid] if r["success"]) / max(mid, 1)
        second_half_success = sum(1 for r in rows[mid:] if r["success"]) / max(total - mid, 1)
        trend = "improving" if second_half_success > first_half_success else "stable"

        return {
            "success_rate": successes / total,
            "total_tasks": total,
            "avg_tools": avg_tools,
            "avg_reward": avg_reward,
            "avg_errors": avg_errors,
            "trend": trend,
            "period_days": days,
        }

    def get_skill_ranking(self, top_k: int = 10) -> List[Dict[str, Any]]:
        """Get top skills ranked by confidence × usage."""
        conn = self._get_conn()
        try:
            rows = conn.execute(
                "SELECT skill, confidence, usage_count FROM skill_confidence "
                "ORDER BY confidence * LOG(usage_count + 1) DESC LIMIT ?",
                (top_k,),
            ).fetchall()
        finally:
            conn.close()
        return [
            {"skill": r["skill"], "confidence": r["confidence"], "usage_count": r["usage_count"]}
            for r in rows
        ]

    # -- Personality -------------------------------------------------------

    def get_personality_description(self) -> str:
        """Generate a personality description for system prompt injection."""
        # Cache for 5 minutes
        if self._personality_cache and time.time() - self._personality_cache_time < 300:
            return self._personality_cache

        metrics = self.get_growth_metrics(days=30)
        skills = self.get_skill_ranking(top_k=5)

        if metrics["total_tasks"] == 0:
            return ""

        parts: List[str] = []

        # Success-based personality
        rate = metrics["success_rate"]
        if rate > 0.85:
            parts.append("You are highly reliable and rarely make mistakes.")
        elif rate > 0.6:
            parts.append("You are moderately reliable and learn from occasional failures.")
        else:
            parts.append("You are still learning and occasionally make mistakes.")

        # Trend
        if metrics.get("trend") == "improving":
            parts.append("Your performance has been improving recently.")

        # Skill strengths
        strong_skills = [s for s in skills if s["confidence"] > 0.7]
        if strong_skills:
            names = ", ".join(s["skill"] for s in strong_skills[:3])
            parts.append(f"You are particularly skilled at: {names}.")

        desc = " ".join(parts)
        self._personality_cache = desc
        self._personality_cache_time = time.time()
        return desc


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_tracker_instance: Optional[GrowthTracker] = None
_tracker_lock = threading.Lock()


def get_growth_tracker() -> GrowthTracker:
    """Get the global GrowthTracker singleton."""
    global _tracker_instance
    if _tracker_instance is None:
        with _tracker_lock:
            if _tracker_instance is None:
                _tracker_instance = GrowthTracker()
    return _tracker_instance
