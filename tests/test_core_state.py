from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from houdini_ai_agent.adapters.mock_houdini import MockHoudiniAdapter
from houdini_ai_agent.core.session import AgentSession
from houdini_ai_agent.core.tool_registry import (
    WORK_MODE_AGENT,
    WORK_MODE_ASK,
    WORK_MODE_PLAN,
    get_default_tool_registry,
)


class StorageAdapter(MockHoudiniAdapter):
    def __init__(self, storage_dir: Path):
        self.storage_dir = storage_dir

    def get_session_storage_dir(self):
        return self.storage_dir


class CoreStateTests(unittest.TestCase):
    def test_tool_registry_keeps_scene_mutation_out_of_ask_and_plan(self):
        registry = get_default_tool_registry()

        self.assertFalse(registry.is_tool_allowed(WORK_MODE_ASK, "create_node"))
        self.assertFalse(registry.is_tool_allowed(WORK_MODE_PLAN, "create_node"))
        self.assertTrue(registry.is_tool_allowed(WORK_MODE_AGENT, "create_node"))
        self.assertTrue(registry.is_tool_allowed(WORK_MODE_AGENT, "set_parm"))
        self.assertFalse(registry.is_tool_allowed(WORK_MODE_PLAN, "set_parm"))
        self.assertTrue(registry.is_tool_allowed(WORK_MODE_PLAN, "add_todo"))
        self.assertTrue(registry.is_tool_allowed(WORK_MODE_ASK, "update_todo"))

    def test_plan_state_is_saved_and_rebuilt(self):
        with tempfile.TemporaryDirectory() as tmp:
            session = AgentSession(StorageAdapter(Path(tmp)))
            payload = {
                "plan": {
                    "title": "Build preview",
                    "goal": "Create a safe node preview",
                    "steps": [{"title": "Inspect scene"}, {"title": "Create node"}],
                }
            }

            self.assertTrue(session._handle_plan_response(f"```json\n{json.dumps(payload)}\n```"))
            plan_id = next(iter(session.current_conversation.plans))
            session.save_autosaved_conversations()

            restored = AgentSession(StorageAdapter(Path(tmp)))

            self.assertIn(plan_id, restored.current_conversation.plans)
            self.assertIn(plan_id, restored._pending_plans)
            self.assertEqual(restored.current_conversation.plans[plan_id]["status"], "draft")

    def test_todo_state_is_saved_and_reloaded(self):
        with tempfile.TemporaryDirectory() as tmp:
            session = AgentSession(StorageAdapter(Path(tmp)))
            session._execute_model_action({"action": "add_todo", "title": "Inspect selection"})
            session._execute_model_action({"action": "update_todo", "title": "Inspect selection", "status": "in_progress"})
            session.save_autosaved_conversations()

            restored = AgentSession(StorageAdapter(Path(tmp)))

            self.assertEqual(len(restored.current_conversation.todos), 1)
            self.assertEqual(restored.current_conversation.todos[0]["title"], "Inspect selection")
            self.assertEqual(restored.current_conversation.todos[0]["status"], "in_progress")

    def test_plan_parser_recovers_json_embedded_in_response_text(self):
        session = AgentSession(MockHoudiniAdapter())
        payload = {
            "response": "```json\n"
            + json.dumps(
                {
                    "plan": {
                        "title": "破碎测试计划",
                        "goal": "创建盒子破碎测试",
                        "steps": [{"title": "创建基础几何"}, {"title": "设置 RBD"}],
                    }
                },
                ensure_ascii=False,
            )
            + "\n```"
        }

        self.assertTrue(session._handle_plan_response(json.dumps(payload, ensure_ascii=False)))
        plan = next(iter(session.current_conversation.plans.values()))

        self.assertEqual(plan["title"], "破碎测试计划")
        self.assertEqual(plan["goal"], "创建盒子破碎测试")
        self.assertEqual(plan["steps"][0]["title"], "创建基础几何")

    def test_plan_execution_blocks_when_model_returns_no_actions(self):
        session = AgentSession(MockHoudiniAdapter())
        plan = {
            "id": "plan1",
            "status": "executing",
            "title": "测试计划",
            "goal": "创建节点",
            "steps": [{"title": "创建 box"}],
        }
        session.current_conversation.plans[plan["id"]] = plan
        session._active_plan_execution = {"plan": plan, "step_index": 1, "completed": []}
        session._active_task_id = "task1"

        session._model_call_finished("task1", "I will create a box later.", "done", "ok", "success")

        self.assertIsNone(session._active_plan_execution)
        self.assertEqual(plan["status"], "blocked")
        self.assertEqual(plan["steps"][0]["status"], "blocked")


if __name__ == "__main__":
    unittest.main()
