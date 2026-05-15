"""Plan management with three-phase state machine, DAG dependency, and JSON persistence.

Supports:
- Plan lifecycle: draft -> confirmed -> executing -> completed / rejected
- DAG dependency via declarative ``depends_on`` on each step
- Architecture blueprint (nodes/connections/groups) for target node network
- Auto-continuation support (resume count, progress context injection)
- JSON file persistence to ``~/.houdini_ai_agent/plans/``
- Tool schema definitions for create_plan, update_plan_step, ask_question
"""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Optional, Tuple

from houdini_ai_agent.core.config import APP_CONFIG_DIR


# ---------------------------------------------------------------------------
# Type aliases
# ---------------------------------------------------------------------------

PlanDict = Dict[str, Any]
StepDict = Dict[str, Any]
ArchDict = Dict[str, Any]


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Plan status values
PLAN_DRAFT = "draft"
PLAN_CONFIRMED = "confirmed"
PLAN_EXECUTING = "executing"
PLAN_COMPLETED = "completed"
PLAN_REJECTED = "rejected"

# Step status values
STEP_PENDING = "pending"
STEP_RUNNING = "running"
STEP_DONE = "done"
STEP_ERROR = "error"

# Phase labels (for the UI state machine)
PHASE_IDLE = "idle"
PHASE_PLANNING = "planning"
PHASE_AWAITING_CONFIRMATION = "awaiting_confirmation"
PHASE_EXECUTING = "executing"
PHASE_COMPLETED = "completed"

MAX_PLAN_RESUMES = 5
MAX_STEPS = 20
MAX_STEP_TITLE = 80
MAX_RESULT_SUMMARY = 500


# ---------------------------------------------------------------------------
# Persistence paths
# ---------------------------------------------------------------------------

_PLANS_DIR = APP_CONFIG_DIR / "plans"


def _ensure_plans_dir() -> Path:
    _PLANS_DIR.mkdir(parents=True, exist_ok=True)
    return _PLANS_DIR


def _plan_path(session_id: str) -> Path:
    return _ensure_plans_dir() / f"plan_{session_id}.json"


def _archive_path(session_id: str) -> Path:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return _ensure_plans_dir() / f"plan_{session_id}_archived_{ts}.json"


# ---------------------------------------------------------------------------
# Tool schema definitions (for tool_registry registration)
# ---------------------------------------------------------------------------

PLAN_TOOL_CREATE_SCHEMA: Mapping[str, Any] = {
    "type": "object",
    "properties": {
        "title": {
            "type": "string",
            "description": "Plan title (concise summary of the goal)",
        },
        "overview": {
            "type": "string",
            "description": "Brief overview of the plan approach and expected outcome",
        },
        "complexity": {
            "type": "string",
            "enum": ["low", "medium", "high"],
            "description": "Estimated complexity of the plan",
        },
        "steps": {
            "type": "array",
            "description": "Ordered list of execution steps",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "Unique step ID (e.g. 'step-1')"},
                    "title": {"type": "string", "description": "Short step title"},
                    "description": {"type": "string", "description": "Detailed description with node paths, parameter values"},
                    "sub_steps": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Atomic sub-operations for this step",
                    },
                    "tools": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Houdini tools used in this step",
                    },
                    "depends_on": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Step IDs this depends on (DAG edges)",
                    },
                    "expected_result": {
                        "type": "string",
                        "description": "Verifiable expected outcome",
                    },
                    "risk": {
                        "type": "string",
                        "enum": ["low", "medium", "high"],
                        "description": "Risk level",
                    },
                    "fallback": {
                        "type": "string",
                        "description": "Fallback strategy if step fails",
                    },
                },
                "required": ["id", "title", "description", "tools", "expected_result"],
            },
        },
        "phases": {
            "type": "array",
            "description": "Logical phase groupings (required for 3+ steps)",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "step_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                },
                "required": ["name", "step_ids"],
            },
        },
        "architecture": {
            "type": "object",
            "description": "Target node network architecture blueprint",
            "properties": {
                "nodes": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "string", "description": "Node identifier (e.g. 'grid1')"},
                            "label": {"type": "string", "description": "Display label"},
                            "type": {"type": "string", "description": "Node type category"},
                            "group": {"type": "string", "description": "Logical group name"},
                            "is_new": {"type": "boolean", "description": "Whether this is a new node"},
                            "params": {"type": "string", "description": "Key parameters summary"},
                        },
                        "required": ["id"],
                    },
                },
                "connections": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "from": {"type": "string"},
                            "to": {"type": "string"},
                            "label": {"type": "string"},
                        },
                        "required": ["from", "to"],
                    },
                },
                "groups": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "node_ids": {"type": "array", "items": {"type": "string"}},
                            "color": {"type": "string"},
                        },
                        "required": ["name", "node_ids"],
                    },
                },
            },
            "required": ["nodes", "connections"],
        },
    },
    "required": ["title", "overview", "steps"],
}

PLAN_TOOL_UPDATE_STEP_SCHEMA: Mapping[str, Any] = {
    "type": "object",
    "properties": {
        "step_id": {
            "type": "string",
            "description": "Step ID to update (e.g. 'step-1')",
        },
        "status": {
            "type": "string",
            "enum": ["running", "done", "error"],
            "description": "New step status",
        },
        "result_summary": {
            "type": "string",
            "description": "Summary of the step result or error",
        },
    },
    "required": ["step_id", "status"],
}

PLAN_TOOL_ASK_QUESTION_SCHEMA: Mapping[str, Any] = {
    "type": "object",
    "properties": {
        "questions": {
            "type": "array",
            "description": "Questions for the user (max 2)",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "Question ID"},
                    "prompt": {"type": "string", "description": "Question text"},
                    "options": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "id": {"type": "string"},
                                "label": {"type": "string"},
                            },
                            "required": ["id", "label"],
                        },
                        "description": "Predefined answer options",
                    },
                    "allow_multiple": {
                        "type": "boolean",
                        "description": "Allow selecting multiple options",
                    },
                    "allow_free_text": {
                        "type": "boolean",
                        "description": "Allow free-text input",
                    },
                },
                "required": ["id", "prompt"],
            },
        },
    },
    "required": ["questions"],
}


# ---------------------------------------------------------------------------
# Plan normalization helpers (kept from original PlanStore)
# ---------------------------------------------------------------------------

def normalize_step(raw: Any, index: int) -> StepDict:
    """Normalize a single step from AI output or user input."""
    if not isinstance(raw, dict):
        raw = {"title": str(raw)}

    step_id = str(raw.get("id") or f"step-{index}")
    title = str(raw.get("title") or raw.get("name") or f"Step {index}")[:MAX_STEP_TITLE]
    description = str(raw.get("description") or raw.get("detail") or "")
    tools = raw.get("tools", [])
    if isinstance(tools, str):
        tools = [t.strip() for t in tools.split(",") if t.strip()]

    depends_on = raw.get("depends_on", [])
    if not isinstance(depends_on, list):
        depends_on = []

    return {
        "id": step_id,
        "title": title,
        "description": description,
        "sub_steps": raw.get("sub_steps", []),
        "tools": tools,
        "depends_on": depends_on,
        "expected_result": str(raw.get("expected_result") or ""),
        "risk": str(raw.get("risk") or "low"),
        "estimated_operations": int(raw.get("estimated_operations") or 0),
        "fallback": str(raw.get("fallback") or ""),
        "notes": str(raw.get("notes") or ""),
        "status": STEP_PENDING,
        "result_summary": None,
    }


def extract_steps_from_text(text: str) -> List[StepDict]:
    """Extract step list from free-form text (fallback when no structured steps)."""
    cleaned = re.sub(r"^\s*计划\s*[:：]\s*", "", text.strip(), flags=re.IGNORECASE)
    parts = re.split(r"(?:^|\n)\s*(?:\d+[\.、)]|[-*])\s+", cleaned)
    candidates = [p.strip(" \n;；。") for p in parts if p.strip(" \n;；。")]
    if len(candidates) <= 1:
        candidates = [item.strip() for item in re.split(r"[；;]\s*", cleaned) if item.strip()]

    steps: List[StepDict] = []
    for i, item in enumerate(candidates[:12], 1):
        title, detail = _split_title_detail(item)
        steps.append({
            "id": f"step-{i}",
            "title": title,
            "description": detail,
            "sub_steps": [],
            "tools": [],
            "depends_on": [f"step-{i - 1}"] if i > 1 else [],
            "expected_result": "",
            "risk": "low",
            "estimated_operations": 0,
            "fallback": "",
            "notes": "",
            "status": STEP_PENDING,
            "result_summary": None,
        })
    return steps


def _split_title_detail(text: str) -> Tuple[str, str]:
    text = " ".join(text.split())
    if len(text) <= 42:
        return text, ""
    for sep in ("：", ":", "，", ","):
        if sep in text[:54]:
            title, detail = text.split(sep, 1)
            return title.strip(), detail.strip()
    return text[:42].rstrip() + "...", text


# ---------------------------------------------------------------------------
# PlanManager — core plan lifecycle manager
# ---------------------------------------------------------------------------

class PlanManager:
    """Manages plan CRUD, state transitions, persistence, and context generation."""

    def __init__(self) -> None:
        self._resume_counts: Dict[str, int] = {}  # session_id -> resume count

    # -- Create --

    def create_plan(self, session_id: str, kwargs: Mapping[str, Any]) -> PlanDict:
        """Create a new plan from AI-provided kwargs. Archives any existing plan."""
        # Archive old plan if exists
        old_path = _plan_path(session_id)
        if old_path.exists():
            try:
                archive = _archive_path(session_id)
                old_path.rename(archive)
            except OSError:
                try:
                    old_path.unlink(missing_ok=True)
                except OSError:
                    pass

        steps_raw = kwargs.get("steps", [])
        if not isinstance(steps_raw, list):
            steps_raw = []

        steps = []
        for i, raw_step in enumerate(steps_raw[:MAX_STEPS], 1):
            steps.append(normalize_step(raw_step, i))

        # If no structured steps, try to extract from text
        if not steps:
            fallback_text = str(kwargs.get("overview") or kwargs.get("title") or "")
            steps = extract_steps_from_text(fallback_text)

        phases = kwargs.get("phases", [])
        if not isinstance(phases, list):
            phases = []

        architecture = kwargs.get("architecture", {})
        if not isinstance(architecture, dict):
            architecture = {}

        plan: PlanDict = {
            "plan_id": uuid.uuid4().hex[:8],
            "session_id": session_id,
            "title": str(kwargs.get("title") or "Untitled Plan")[:120],
            "overview": str(kwargs.get("overview") or ""),
            "complexity": str(kwargs.get("complexity") or "medium"),
            "estimated_total_operations": sum(
                s.get("estimated_operations", 0) for s in steps
            ),
            "phases": phases,
            "created_at": datetime.now().isoformat(),
            "status": PLAN_DRAFT,
            "steps": steps,
            "architecture": architecture,
        }

        self._save(plan)
        self._resume_counts[session_id] = 0
        return plan

    # -- Read --

    def load_plan(self, session_id: str) -> Optional[PlanDict]:
        """Load the active plan for a session."""
        path = _plan_path(session_id)
        if not path.exists():
            return None
        try:
            text = path.read_text(encoding="utf-8")
            return json.loads(text)
        except (json.JSONDecodeError, OSError):
            return None

    # -- Update step --

    def update_step(
        self,
        session_id: str,
        step_id: str,
        status: str,
        result_summary: str = "",
    ) -> Optional[PlanDict]:
        """Update a single step's status. Auto-transitions plan status."""
        plan = self.load_plan(session_id)
        if plan is None:
            return None

        # Find and update the step
        target_step = None
        for step in plan.get("steps", []):
            if step.get("id") == step_id:
                step["status"] = status
                if result_summary:
                    step["result_summary"] = result_summary[:MAX_RESULT_SUMMARY]
                target_step = step
                break

        if target_step is None:
            return plan  # Step not found, return unchanged

        # Auto-transition plan status
        steps = plan.get("steps", [])
        all_statuses = [s.get("status") for s in steps]

        if plan["status"] == PLAN_CONFIRMED and STEP_RUNNING in all_statuses:
            plan["status"] = PLAN_EXECUTING

        if plan["status"] in (PLAN_EXECUTING, PLAN_CONFIRMED):
            if all(s in (STEP_DONE, STEP_ERROR) for s in all_statuses):
                plan["status"] = PLAN_COMPLETED

        self._save(plan)
        return plan

    # -- State transitions --

    def confirm_plan(self, session_id: str) -> Optional[PlanDict]:
        """Transition plan from draft to confirmed."""
        plan = self.load_plan(session_id)
        if plan is None:
            return None
        if plan["status"] != PLAN_DRAFT:
            return plan
        plan["status"] = PLAN_CONFIRMED
        self._save(plan)
        return plan

    def reject_plan(self, session_id: str) -> bool:
        """Reject and delete the plan."""
        plan = self.load_plan(session_id)
        if plan is None:
            return False
        plan["status"] = PLAN_REJECTED
        self._save(plan)
        return True

    def delete_plan(self, session_id: str) -> bool:
        """Delete the plan file."""
        path = _plan_path(session_id)
        try:
            path.unlink(missing_ok=True)
            return True
        except OSError:
            return False

    # -- Progress / context for AI injection --

    def get_plan_for_context(self, session_id: str) -> str:
        """Generate a compact context string for AI system prompt injection.

        Returns empty string if no active plan or plan is in draft/rejected.
        """
        plan = self.load_plan(session_id)
        if plan is None:
            return ""
        status = plan.get("status", "")
        if status in (PLAN_DRAFT, PLAN_REJECTED):
            return ""

        steps = plan.get("steps", [])
        if not steps:
            return ""

        total = len(steps)
        done_count = sum(1 for s in steps if s.get("status") == STEP_DONE)
        error_count = sum(1 for s in steps if s.get("status") == STEP_ERROR)

        lines = [
            f"[Active Plan: {plan.get('title', 'Untitled')}]",
            f"Progress: {done_count}/{total} done, {error_count} errors",
        ]

        # Current / running step
        for s in steps:
            if s.get("status") == STEP_RUNNING:
                tools_str = ", ".join(s.get("tools", [])[:3])
                lines.append(
                    f"Current: {s['id']} \"{s['title']}\" "
                    f"(tools: {tools_str}) | Expected: {s.get('expected_result', '')}"
                )
                if s.get("fallback"):
                    lines.append(f"  Fallback: {s['fallback']}")

        # Next pending step (first pending whose depends_on are all done)
        pending_names: List[str] = []
        for s in steps:
            if s.get("status") in (STEP_PENDING, STEP_RUNNING):
                pending_names.append(s.get("title", s["id"]))

        if pending_names:
            lines.append(f"Remaining: " + ", ".join(f"\"{n}\"" for n in pending_names[:5]))

        return "\n".join(lines)

    # -- Auto-continuation --

    def check_plan_incomplete(self, session_id: str) -> Optional[str]:
        """Check if the plan has incomplete steps. Returns a resume message or None.

        Used as the on_plan_incomplete callback for the agent loop.
        Returns None if plan is complete or max resumes reached.
        """
        count = self._resume_counts.get(session_id, 0)
        if count >= MAX_PLAN_RESUMES:
            return None

        plan = self.load_plan(session_id)
        if plan is None:
            return None

        steps = plan.get("steps", [])
        if not steps:
            return None

        total = len(steps)
        done_count = sum(1 for s in steps if s.get("status") == STEP_DONE)
        error_count = sum(1 for s in steps if s.get("status") == STEP_ERROR)

        # All done
        if done_count + error_count >= total:
            return None

        # Collect pending/running steps
        pending = [
            s for s in steps
            if s.get("status") in (STEP_PENDING, STEP_RUNNING)
        ]
        if not pending:
            return None

        self._resume_counts[session_id] = count + 1

        names = ", ".join(
            f"\"{s.get('title', s['id'])}\""
            for s in pending[:5]
        )
        return (
            f"[Plan Incomplete] Plan has {done_count}/{total} steps completed. "
            f"Incomplete steps: {names}. "
            f"Continue executing the next unfinished step immediately. "
            f"Do not stop or summarize — call tools to continue."
        )

    def get_resume_count(self, session_id: str) -> int:
        return self._resume_counts.get(session_id, 0)

    def reset_resume_count(self, session_id: str) -> None:
        self._resume_counts[session_id] = 0

    # -- Step ordering helpers --

    def get_executable_steps(self, session_id: str) -> List[StepDict]:
        """Get steps whose dependencies are all done, in execution order."""
        plan = self.load_plan(session_id)
        if plan is None:
            return []

        steps = plan.get("steps", [])
        done_ids = {s["id"] for s in steps if s.get("status") == STEP_DONE}

        result = []
        for step in steps:
            if step.get("status") not in (STEP_PENDING,):
                continue
            deps = step.get("depends_on", [])
            if all(d in done_ids for d in deps):
                result.append(step)
        return result

    # -- Persistence --

    def _save(self, plan: PlanDict) -> None:
        session_id = plan.get("session_id", "")
        if not session_id:
            return
        path = _plan_path(session_id)
        try:
            path.write_text(
                json.dumps(plan, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except OSError as exc:
            import logging
            logging.getLogger(__name__).warning("Failed to save plan: %s", exc)

    # -- Stats --

    def plan_stats(self, session_id: str) -> Dict[str, int]:
        """Return step status counts."""
        plan = self.load_plan(session_id)
        if plan is None:
            return {}
        steps = plan.get("steps", [])
        return {
            "total": len(steps),
            "pending": sum(1 for s in steps if s.get("status") == STEP_PENDING),
            "running": sum(1 for s in steps if s.get("status") == STEP_RUNNING),
            "done": sum(1 for s in steps if s.get("status") == STEP_DONE),
            "error": sum(1 for s in steps if s.get("status") == STEP_ERROR),
        }


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_manager_instance: Optional[PlanManager] = None


def get_plan_manager() -> PlanManager:
    """Get or create the singleton PlanManager."""
    global _manager_instance
    if _manager_instance is None:
        _manager_instance = PlanManager()
    return _manager_instance


# ---------------------------------------------------------------------------
# Backward-compatible PlanStore (keeps existing API working)
# ---------------------------------------------------------------------------

class PlanStore:
    """Keep plan shaping and state transitions out of the Qt session object.

    This class provides backward compatibility with the original PlanStore API
    while delegating to PlanManager for persistence and state management.
    """

    def rebuild_pending(self, conversations: Iterable[object]) -> Dict[str, PlanDict]:
        pending: Dict[str, PlanDict] = {}
        for conversation in conversations:
            plans = getattr(conversation, "plans", {})
            if not isinstance(plans, dict):
                continue
            for plan in plans.values():
                if not isinstance(plan, dict):
                    continue
                plan_id = str(plan.get("id") or plan.get("plan_id") or "")
                status = str(plan.get("status") or "draft")
                if plan_id and status not in {PLAN_COMPLETED, PLAN_CANCELLED if hasattr(self, '_CANCELLED') else "cancelled", PLAN_REJECTED}:
                    pending[plan_id] = plan
        return pending

    def store(self, conversation: object, pending: MutableMapping[str, PlanDict], plan: PlanDict) -> str:
        plan_id = str(plan.get("id") or plan.get("plan_id") or uuid.uuid4().hex)
        plan["id"] = plan_id
        if "plan_id" not in plan:
            plan["plan_id"] = plan_id
        plans = getattr(conversation, "plans")
        plans[plan_id] = plan
        pending[plan_id] = plan
        return plan_id

    def update_plan_message(self, messages: Iterable[object], plan: PlanDict) -> bool:
        plan_id = str(plan.get("id") or plan.get("plan_id") or "")
        if not plan_id:
            return False
        for message in messages:
            if getattr(message, "role", "") != "plan":
                continue
            try:
                data = json.loads(getattr(message, "content", ""))
            except Exception:
                continue
            if isinstance(data, dict) and str(data.get("id") or data.get("plan_id") or "") == plan_id:
                message.content = json.dumps(plan, ensure_ascii=False)
                return True
        return False

    def set_step_status(self, plan: PlanDict, index: int, status: str, message: str = "") -> None:
        steps = plan.get("steps", []) if isinstance(plan.get("steps"), list) else []
        if 0 <= index < len(steps) and isinstance(steps[index], dict):
            steps[index]["status"] = status
            if message:
                steps[index]["result_summary"] = message[:MAX_RESULT_SUMMARY]

    def normalize_plan(self, data: PlanDict, source_text: str, language: str) -> PlanDict:
        steps_raw = data.get("steps", [])
        normalized_steps = []
        if isinstance(steps_raw, list):
            for index, step in enumerate(steps_raw, 1):
                normalized_steps.append(normalize_step(step, index))
        if not normalized_steps:
            normalized_steps = extract_steps_from_text(
                str(data.get("response") or source_text)
            )
        title = str(data.get("title") or data.get("name") or "待确认执行计划")
        goal = str(data.get("goal") or data.get("summary") or data.get("response") or "").strip()
        risks = data.get("risks", [])
        if isinstance(risks, str):
            risks = [risks]
        elif not isinstance(risks, list):
            risks = []
        return {
            "id": uuid.uuid4().hex,
            "status": PLAN_DRAFT,
            "title": title,
            "goal": goal,
            "language": language,
            "steps": normalized_steps,
            "risks": risks,
            "source_response": source_text,
        }

    def plan_from_text(self, text: str, language: str) -> PlanDict:
        steps = extract_steps_from_text(text)
        stripped = re.sub(r"^\s*计划\s*[:：]\s*", "", text.strip(), flags=re.IGNORECASE)
        return {
            "id": uuid.uuid4().hex,
            "status": PLAN_DRAFT,
            "title": "待确认执行计划",
            "goal": stripped.splitlines()[0][:120] if stripped.strip() else "",
            "language": language,
            "steps": steps,
            "risks": [],
            "source_response": text,
        }

    def extract_steps_from_text(self, text: str) -> List[PlanDict]:
        return extract_steps_from_text(text)

    def strip_plan_prefix(self, text: str) -> str:
        return re.sub(r"^\s*计划\s*[:：]\s*", "", text.strip(), flags=re.IGNORECASE)

    def split_step_title_detail(self, text: str) -> tuple[str, str]:
        return _split_title_detail(text)

    def plans_from_dict(self, raw: object) -> Dict[str, PlanDict]:
        if not isinstance(raw, dict):
            return {}
        plans: Dict[str, PlanDict] = {}
        for key, value in raw.items():
            if not isinstance(value, dict):
                continue
            plan = dict(value)
            plan_id = str(plan.get("id") or plan.get("plan_id") or key or uuid.uuid4().hex)
            plan["id"] = plan_id
            if "plan_id" not in plan:
                plan["plan_id"] = plan_id
            if plan.get("status") == PLAN_EXECUTING:
                plan["status"] = "paused"
                for step in plan.get("steps", []):
                    if isinstance(step, dict) and step.get("status") == STEP_RUNNING:
                        step["status"] = STEP_PENDING
            plans[plan_id] = plan
        return plans
