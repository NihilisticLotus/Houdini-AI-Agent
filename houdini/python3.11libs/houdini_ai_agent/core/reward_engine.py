"""Reward engine — dopamine-inspired reward calculation for memory importance.

Evaluates task outcomes and assigns reward scores that determine memory
importance, retention, and retrieval priority.
"""

from __future__ import annotations

import math
import threading
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from houdini_ai_agent.core.memory_store import EpisodicRecord, get_memory_store


# ---------------------------------------------------------------------------
# Reward calculation
# ---------------------------------------------------------------------------

# Weight factors for reward composition
_WEIGHT_SUCCESS = 0.35
_WEIGHT_ERROR_RATE = 0.20
_WEIGHT_RETRY_RATE = 0.15
_WEIGHT_COMPLEXITY = 0.15
_WEIGHT_NOVELTY = 0.15

# Importance bounds
_IMPORTANCE_MIN = 0.01
_IMPORTANCE_MAX = 5.0

# Decay rate per day (exponential)
_DAILY_DECAY_RATE = 0.05

# Reinforcement boost for activated memories
_ACTIVATION_BOOST = 0.1


@dataclass
class RewardResult:
    """Result of a reward calculation."""
    reward_score: float = 0.0
    importance: float = 1.0
    tags: List[str] = field(default_factory=list)
    reinforcement_applied: bool = False


class RewardEngine:
    """Calculates reward scores for task completions and updates memory importance."""

    def __init__(self) -> None:
        self._tag_success_history: Dict[str, List[bool]] = {}
        self._lock = threading.Lock()

    def calculate_reward(
        self,
        success: bool,
        error_count: int = 0,
        retry_count: int = 0,
        action_count: int = 1,
        tags: Optional[List[str]] = None,
    ) -> RewardResult:
        """Calculate a reward score for a completed task.

        Args:
            success:       Whether the task succeeded.
            error_count:   Number of errors encountered.
            retry_count:   Number of retries.
            action_count:  Number of tool actions executed.
            tags:          Category tags for the task.

        Returns:
            RewardResult with reward_score (0~1) and importance (0.01~5.0).
        """
        tags = tags or []

        # Success component (0 or 1)
        success_score = 1.0 if success else 0.0

        # Error rate component (lower is better)
        error_rate = min(error_count / max(action_count, 1), 1.0)
        error_score = 1.0 - error_rate

        # Retry rate component (lower is better)
        retry_rate = min(retry_count / max(action_count, 1), 1.0)
        retry_score = 1.0 - retry_rate

        # Complexity component (more actions = more complex = higher importance)
        complexity_score = min(math.log(action_count + 1) / math.log(10), 1.0)

        # Novelty component (tag-based novelty estimation)
        novelty_score = self._calculate_novelty(tags, success)

        # Weighted combination
        reward = (
            _WEIGHT_SUCCESS * success_score +
            _WEIGHT_ERROR_RATE * error_score +
            _WEIGHT_RETRY_RATE * retry_score +
            _WEIGHT_COMPLEXITY * complexity_score +
            _WEIGHT_NOVELTY * novelty_score
        )
        reward = max(0.0, min(1.0, reward))

        # Importance = base importance modulated by reward
        importance = 1.0 + reward * 3.0  # Range: 1.0 ~ 4.0
        if not success and error_count > 0:
            importance *= 1.5  # Failures are often more educational

        importance = max(_IMPORTANCE_MIN, min(_IMPORTANCE_MAX, importance))

        return RewardResult(
            reward_score=reward,
            importance=importance,
            tags=tags,
        )

    def process_task_completion(
        self,
        episodic_record: EpisodicRecord,
        tool_call_count: int = 0,
    ) -> RewardResult:
        """Process a completed task: calculate reward and update importance.

        This is the main entry point called by the reflection module.
        """
        result = self.calculate_reward(
            success=episodic_record.success,
            error_count=episodic_record.error_count,
            retry_count=episodic_record.retry_count,
            action_count=tool_call_count or len(episodic_record.actions),
            tags=episodic_record.tags,
        )

        # Update the episodic record
        episodic_record.reward_score = result.reward_score
        episodic_record.importance = result.importance

        # Apply daily decay to old memories
        self._apply_decay()

        return result

    def update_importance(self, record_id: str, delta: float) -> None:
        """Boost or reduce importance of an episodic memory."""
        store = get_memory_store()
        # Find and update the record
        conn = store._get_conn()
        try:
            row = conn.execute(
                "SELECT importance FROM episodic_memory WHERE id = ?",
                (record_id,),
            ).fetchone()
            if row:
                new_importance = max(_IMPORTANCE_MIN, min(_IMPORTANCE_MAX, row["importance"] + delta))
                conn.execute(
                    "UPDATE episodic_memory SET importance = ? WHERE id = ?",
                    (new_importance, record_id),
                )
                conn.commit()
        finally:
            conn.close()

    def _calculate_novelty(self, tags: List[str], success: bool) -> float:
        """Estimate novelty based on tag history."""
        if not tags:
            return 0.5  # Unknown

        with self._lock:
            novel_count = 0
            for tag in tags:
                history = self._tag_success_history.get(tag, [])
                if len(history) < 3:
                    novel_count += 1
                else:
                    # Low success rate = high novelty value
                    recent_rate = sum(history[-5:]) / min(len(history), 5)
                    if success and recent_rate < 0.5:
                        novel_count += 1

            # Record for future
            for tag in tags:
                if tag not in self._tag_success_history:
                    self._tag_success_history[tag] = []
                self._tag_success_history[tag].append(success)
                # Keep last 20 entries
                if len(self._tag_success_history[tag]) > 20:
                    self._tag_success_history[tag] = self._tag_success_history[tag][-20:]

        return min(novel_count / max(len(tags), 1), 1.0)

    def _apply_decay(self) -> None:
        """Apply time-based decay to episodic memory importance."""
        store = get_memory_store()
        conn = store._get_conn()
        try:
            now = time.time()
            one_day = 86400.0
            # Decay: importance *= exp(-DAILY_DECAY_RATE * days_since_creation)
            conn.execute(
                "UPDATE episodic_memory SET importance = MAX(?, importance * EXP(-? * ((? - timestamp) / ?))) "
                "WHERE importance > ?",
                (_IMPORTANCE_MIN, _DAILY_DECAY_RATE, now, one_day, _IMPORTANCE_MIN),
            )
            conn.commit()
        except Exception:
            # EXP() may not be available in older SQLite — log once
            import traceback
            print(f"[RewardEngine] _apply_decay failed (SQLite may lack EXP): {traceback.format_exc()}")
        finally:
            conn.close()


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_engine_instance: Optional[RewardEngine] = None
_engine_lock = threading.Lock()


def get_reward_engine() -> RewardEngine:
    """Get the global RewardEngine singleton."""
    global _engine_instance
    if _engine_instance is None:
        with _engine_lock:
            if _engine_instance is None:
                _engine_instance = RewardEngine()
    return _engine_instance
