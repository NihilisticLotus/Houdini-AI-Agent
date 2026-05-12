from __future__ import annotations

import json
import unittest
from dataclasses import dataclass, field

from houdini_ai_agent.core.plan_store import PlanStore


@dataclass
class Message:
    role: str
    content: str


@dataclass
class Conversation:
    plans: dict = field(default_factory=dict)


class PlanStoreTests(unittest.TestCase):
    def test_normalize_plan_preserves_step_dependencies_and_language(self):
        store = PlanStore()

        plan = store.normalize_plan(
            {
                "title": "Build terrain",
                "goal": "Create a terrain network",
                "steps": [
                    {"id": "a", "title": "Create grid"},
                    {"id": "b", "description": "Add noise", "depends_on": ["a"]},
                ],
            },
            "source",
            "English",
        )

        self.assertEqual("Build terrain", plan["title"])
        self.assertEqual("English", plan["language"])
        self.assertEqual(["a"], plan["steps"][1]["depends_on"])
        self.assertEqual("Add noise", plan["steps"][1]["title"])

    def test_plan_from_text_builds_linear_dependencies(self):
        store = PlanStore()

        plan = store.plan_from_text("计划：\n1. Inspect scene\n2. Create box\n3. Verify result", "English")

        self.assertEqual("待确认执行计划", plan["title"])
        self.assertEqual(["1"], plan["steps"][1]["depends_on"])
        self.assertEqual(["2"], plan["steps"][2]["depends_on"])

    def test_plans_from_dict_pauses_interrupted_execution(self):
        store = PlanStore()

        plans = store.plans_from_dict(
            {
                "plan-a": {
                    "status": "executing",
                    "steps": [{"status": "in_progress"}, {"status": "pending"}],
                }
            }
        )

        plan = plans["plan-a"]
        self.assertEqual("paused", plan["status"])
        self.assertEqual("pending", plan["steps"][0]["status"])

    def test_update_plan_message_rewrites_matching_plan_message(self):
        store = PlanStore()
        plan = {"id": "p1", "status": "draft", "steps": []}
        messages = [
            Message("assistant", "hello"),
            Message("plan", json.dumps({"id": "p1", "status": "old"})),
        ]

        self.assertTrue(store.update_plan_message(messages, plan))

        self.assertEqual("draft", json.loads(messages[1].content)["status"])

    def test_store_and_rebuild_pending(self):
        store = PlanStore()
        conversation = Conversation()
        pending = {}
        plan = {"status": "draft", "steps": []}

        plan_id = store.store(conversation, pending, plan)
        rebuilt = store.rebuild_pending([conversation])

        self.assertIn(plan_id, pending)
        self.assertIn(plan_id, rebuilt)


if __name__ == "__main__":
    unittest.main()

