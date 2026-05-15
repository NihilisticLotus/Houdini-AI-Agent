"""Reflection module — processes task completions and generates long-term memories.

Provides both rule-based (fast) and LLM-based (deep) reflection:
  - Rule reflection: extracts tags, categorizes, and stores episodic records.
  - Deep reflection: every N tasks, uses LLM to generate semantic/procedural memories.
  - Light sleep: periodically summarizes recent conversations.
  - Deep sleep: on context compression, extracts all knowledge.

Adapted from the reference project's reflection system.
"""

from __future__ import annotations

import re
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

from houdini_ai_agent.core.memory_store import (
    EpisodicRecord,
    ProceduralRecord,
    SemanticRecord,
    MEMORY_CATEGORIES,
    get_memory_store,
)
from houdini_ai_agent.core.reward_engine import RewardResult, get_reward_engine
from houdini_ai_agent.core.growth_tracker import TaskMetric, get_growth_tracker


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Deep reflection interval (every N tasks)
DEEP_REFLECT_INTERVAL = 5

# Light sleep interval (every N user messages)
LIGHT_SLEEP_INTERVAL = 5

# Tag extraction patterns
_TAG_PATTERNS = {
    "node_creation": r"create_node|add_node|节点创建",
    "parameter_setting": r"set_parm|set_parameter|参数设置",
    "error_fixing": r"fix_error|apply_code|修复|错误",
    "scene_analysis": r"inspect|analyze|分析|检查",
    "workflow": r"connect|layout|batch|工作流",
    "vex_hscript": r"vex|wrangle|hscript|snippet",
    "performance": r"optim|cache|cook|性能|优化",
    "user_preference": r"喜欢|偏好|prefer|usually",
}


# ---------------------------------------------------------------------------
# Rule-based reflection
# ---------------------------------------------------------------------------

def extract_tags(task_description: str, actions: List[Dict[str, Any]]) -> List[str]:
    """Extract category tags from task description and actions."""
    text = task_description.lower()
    for action in actions:
        name = str(action.get("action", "") or "").lower()
        text += " " + name

    tags = []
    for category, pattern in _TAG_PATTERNS.items():
        if re.search(pattern, text):
            tags.append(category)

    return tags or ["general"]


def categorize_task(task_description: str) -> str:
    """Categorize a task into one of the memory categories."""
    text = task_description.lower()
    for category, pattern in _TAG_PATTERNS.items():
        if re.search(pattern, text):
            return category
    return "general"


# ---------------------------------------------------------------------------
# ReflectionModule
# ---------------------------------------------------------------------------

class ReflectionModule:
    """Processes task completions through rule-based and optional LLM reflection."""

    def __init__(self) -> None:
        self._task_count = 0
        self._lock = threading.Lock()

    def reflect_on_task(
        self,
        session_id: str,
        task_description: str,
        actions: List[Dict[str, Any]],
        result_summary: str,
        success: bool,
        error_count: int = 0,
        retry_count: int = 0,
    ) -> Dict[str, Any]:
        """Process a completed task and generate memories.

        This is the main entry point called after each tool execution cycle.

        Returns:
            Dict with keys: tags, reward_score, importance, record_id, deep_reflected
        """
        # 1. Extract tags via rules
        tags = extract_tags(task_description, actions)

        # 2. Create episodic record
        episodic = EpisodicRecord(
            session_id=session_id,
            task_description=task_description,
            actions=actions,
            result_summary=result_summary[:500],
            success=success,
            error_count=error_count,
            retry_count=retry_count,
            tags=tags,
        )

        # 3. Calculate reward
        reward_engine = get_reward_engine()
        reward_result = reward_engine.process_task_completion(
            episodic, tool_call_count=len(actions),
        )

        # 4. Store episodic memory
        store = get_memory_store()
        record_id = store.add_episodic(episodic)

        # 5. Record growth metric
        growth = get_growth_tracker()
        metric = TaskMetric(
            success=success,
            tool_count=len(actions),
            error_count=error_count,
            retry_count=retry_count,
            reward_score=reward_result.reward_score,
            tags=tags,
        )
        growth.record_task(metric)

        # 6. Increment task count and check for deep reflection
        deep_reflected = False
        with self._lock:
            self._task_count += 1
            if self._task_count % DEEP_REFLECT_INTERVAL == 0:
                deep_reflected = True

        return {
            "tags": tags,
            "reward_score": reward_result.reward_score,
            "importance": reward_result.importance,
            "record_id": record_id,
            "deep_reflected": deep_reflected,
        }

    def generate_semantic_from_episodic(
        self,
        task_description: str,
        result_summary: str,
        success: bool,
        tags: List[str],
        source_id: str = "",
    ) -> Optional[str]:
        """Generate a semantic memory from an episodic record using rule-based extraction.

        Returns the ID of the created semantic record, or None.
        """
        # Rule-based: create a simple rule from the experience
        if success:
            rule = f"Successfully: {task_description[:80]}"
        else:
            rule = f"Avoid: {result_summary[:80]}"

        category = tags[0] if tags else "general"

        record = SemanticRecord(
            rule=rule[:120],
            source_episodes=[source_id] if source_id else [],
            confidence=0.6 if success else 0.4,
            category=category,
            abstraction_level=2,
        )

        store = get_memory_store()
        return store.add_semantic(record)

    def light_sleep(
        self,
        session_id: str,
        recent_messages: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Light sleep: summarize recent conversation messages into memories.

        Called every LIGHT_SLEEP_INTERVAL user messages.
        Does NOT call LLM (would require model access). Instead, extracts
        key information from messages using rule-based analysis.

        Args:
            session_id:      Current session ID.
            recent_messages: List of message dicts with 'role' and 'content'.

        Returns:
            Dict with summary statistics.
        """
        if not recent_messages:
            return {"episodic_count": 0, "semantic_count": 0}

        store = get_memory_store()
        episodic_count = 0
        semantic_count = 0

        # Extract user-assistant pairs as episodic records
        for msg in recent_messages:
            if msg.get("role") == "user":
                content = str(msg.get("content", ""))[:200]
                if content.strip():
                    record = EpisodicRecord(
                        session_id=session_id,
                        task_description=f"[Light sleep] {content}",
                        result_summary="Summarized from conversation",
                        tags=["conversation_summary"],
                    )
                    store.add_episodic(record)
                    episodic_count += 1

        return {
            "episodic_count": episodic_count,
            "semantic_count": semantic_count,
        }

    def deep_sleep(
        self,
        session_id: str,
        all_messages: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Deep sleep: extract all knowledge from conversation history.

        Called on context compression. Does NOT call LLM.
        Extracts tool calls, user requests, and outcomes as memories.

        Args:
            session_id:   Current session ID.
            all_messages: Full message history.

        Returns:
            Dict with summary statistics.
        """
        store = get_memory_store()
        episodic_count = 0
        semantic_count = 0

        # Extract tool call patterns as procedural memories
        tool_patterns: Dict[str, int] = {}
        for msg in all_messages:
            content = str(msg.get("content", ""))
            # Look for JSON action patterns
            for match in re.finditer(r'"action"\s*:\s*"(\w+)"', content):
                action = match.group(1)
                tool_patterns[action] = tool_patterns.get(action, 0) + 1

        # Store frequently used patterns as procedural memories
        for action, count in tool_patterns.items():
            if count >= 2:
                record = ProceduralRecord(
                    strategy_name=f"frequent_{action}",
                    description=f"Tool '{action}' used {count} times in session",
                    priority=min(count / 10.0, 1.0),
                    conditions=[action],
                )
                store.add_procedural(record)
                semantic_count += 1

        return {
            "episodic_count": episodic_count,
            "semantic_count": semantic_count,
            "tool_patterns": tool_patterns,
        }


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_reflection_instance: Optional[ReflectionModule] = None
_reflection_lock = threading.Lock()


def get_reflection_module() -> ReflectionModule:
    """Get the global ReflectionModule singleton."""
    global _reflection_instance
    if _reflection_instance is None:
        with _reflection_lock:
            if _reflection_instance is None:
                _reflection_instance = ReflectionModule()
    return _reflection_instance
