"""Pure helpers for plan normalization and in-memory plan state."""

from __future__ import annotations

import json
import re
import uuid
from typing import Dict, Iterable, List, MutableMapping


PlanDict = Dict[str, object]


class PlanStore:
    """Keep plan shaping and state transitions out of the Qt session object."""

    def rebuild_pending(self, conversations: Iterable[object]) -> Dict[str, PlanDict]:
        pending: Dict[str, PlanDict] = {}
        for conversation in conversations:
            plans = getattr(conversation, "plans", {})
            if not isinstance(plans, dict):
                continue
            for plan in plans.values():
                if not isinstance(plan, dict):
                    continue
                plan_id = str(plan.get("id") or "")
                status = str(plan.get("status") or "draft")
                if plan_id and status not in {"completed", "cancelled"}:
                    pending[plan_id] = plan
        return pending

    def store(self, conversation: object, pending: MutableMapping[str, PlanDict], plan: PlanDict) -> str:
        plan_id = str(plan.get("id") or uuid.uuid4().hex)
        plan["id"] = plan_id
        plans = getattr(conversation, "plans")
        plans[plan_id] = plan
        pending[plan_id] = plan
        return plan_id

    def update_plan_message(self, messages: Iterable[object], plan: PlanDict) -> bool:
        plan_id = str(plan.get("id") or "")
        if not plan_id:
            return False
        for message in messages:
            if getattr(message, "role", "") != "plan":
                continue
            try:
                data = json.loads(getattr(message, "content", ""))
            except Exception:
                continue
            if isinstance(data, dict) and str(data.get("id") or "") == plan_id:
                message.content = json.dumps(plan, ensure_ascii=False)
                return True
        return False

    def set_step_status(self, plan: PlanDict, index: int, status: str, message: str = "") -> None:
        steps = plan.get("steps", []) if isinstance(plan.get("steps"), list) else []
        if 0 <= index < len(steps) and isinstance(steps[index], dict):
            steps[index]["status"] = status
            if message:
                steps[index]["result"] = message[:500]

    def normalize_plan(self, data: PlanDict, source_text: str, language: str) -> PlanDict:
        steps = data.get("steps", [])
        normalized_steps = []
        if isinstance(steps, list):
            for index, step in enumerate(steps, 1):
                if isinstance(step, dict):
                    normalized_steps.append(
                        {
                            "id": str(step.get("id") or index),
                            "title": str(step.get("title") or step.get("name") or step.get("description") or f"Step {index}"),
                            "detail": str(step.get("detail") or step.get("description") or ""),
                            "tool_hint": str(step.get("tool_hint") or step.get("tool") or ""),
                            "depends_on": step.get("depends_on", []) if isinstance(step.get("depends_on", []), list) else [],
                        }
                    )
                else:
                    normalized_steps.append({"id": str(index), "title": str(step), "detail": "", "tool_hint": "", "depends_on": []})
        if not normalized_steps:
            normalized_steps = self.extract_steps_from_text(str(data.get("response") or source_text))
        title = str(data.get("title") or data.get("name") or "待确认执行计划")
        goal = str(data.get("goal") or data.get("summary") or data.get("response") or "").strip()
        risks = data.get("risks", [])
        if isinstance(risks, str):
            risks = [risks]
        elif not isinstance(risks, list):
            risks = []
        return {
            "id": uuid.uuid4().hex,
            "status": "draft",
            "title": title,
            "goal": goal,
            "language": language,
            "steps": normalized_steps,
            "risks": risks,
            "source_response": source_text,
        }

    def plan_from_text(self, text: str, language: str) -> PlanDict:
        steps = self.extract_steps_from_text(text)
        stripped = self.strip_plan_prefix(text)
        return {
            "id": uuid.uuid4().hex,
            "status": "draft",
            "title": "待确认执行计划",
            "goal": stripped.splitlines()[0][:120] if stripped.strip() else "",
            "language": language,
            "steps": steps,
            "risks": [],
            "source_response": text,
        }

    def extract_steps_from_text(self, text: str) -> List[PlanDict]:
        normalized = self.strip_plan_prefix(text)
        parts = re.split(r"(?:^|\n)\s*(?:\d+[\.、)]|[-*])\s+", normalized)
        candidates = [part.strip(" \n;；。") for part in parts if part.strip(" \n;；。")]
        if len(candidates) <= 1:
            candidates = [item.strip() for item in re.split(r"[；;]\s*", normalized) if item.strip()]
        steps = []
        for index, item in enumerate(candidates[:12], 1):
            title, detail = self.split_step_title_detail(item)
            steps.append({"id": str(index), "title": title, "detail": detail, "tool_hint": "", "depends_on": [str(index - 1)] if index > 1 else []})
        return steps

    def strip_plan_prefix(self, text: str) -> str:
        return re.sub(r"^\s*计划\s*[:：]\s*", "", text.strip(), flags=re.IGNORECASE)

    def split_step_title_detail(self, text: str) -> tuple[str, str]:
        text = " ".join(text.split())
        if len(text) <= 42:
            return text, ""
        for sep in ("：", ":", "，", ","):
            if sep in text[:54]:
                title, detail = text.split(sep, 1)
                return title.strip(), detail.strip()
        return text[:42].rstrip() + "...", text

    def plans_from_dict(self, raw: object) -> Dict[str, PlanDict]:
        if not isinstance(raw, dict):
            return {}
        plans: Dict[str, PlanDict] = {}
        for key, value in raw.items():
            if not isinstance(value, dict):
                continue
            plan = dict(value)
            plan_id = str(plan.get("id") or key or uuid.uuid4().hex)
            plan["id"] = plan_id
            if plan.get("status") == "executing":
                plan["status"] = "paused"
                for step in plan.get("steps", []):
                    if isinstance(step, dict) and step.get("status") == "in_progress":
                        step["status"] = "pending"
            plans[plan_id] = plan
        return plans
