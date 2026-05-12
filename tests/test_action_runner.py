from __future__ import annotations

import unittest

from houdini_ai_agent.adapters.mock_houdini import MockHoudiniAdapter
from houdini_ai_agent.core.action_runner import ActionRunner, ToolResult


class MissingCreateAdapter(MockHoudiniAdapter):
    create_node = None


class ActionRunnerTests(unittest.TestCase):
    def test_normalizes_adapter_result_shape(self):
        runner = ActionRunner(MockHoudiniAdapter(), thinking_level=lambda: "中")

        result = runner.execute(
            {
                "action": "set_parm",
                "target_node": "/obj/geo1/box1",
                "parm": "tx",
                "value": 2,
            }
        )

        self.assertEqual("Set parameter", result["title"])
        self.assertEqual(True, result["success"])
        self.assertEqual([], result["errors"])
        self.assertIn("/obj/geo1/box1.tx", result["message"])

    def test_reports_missing_adapter_method_as_failed_result(self):
        runner = ActionRunner(MissingCreateAdapter(), thinking_level=lambda: "中")

        result = runner.execute({"action": "create_node", "node_type": "box"})

        self.assertEqual(False, result["success"])
        self.assertTrue(runner.has_error(result))
        self.assertIn("cannot create nodes", result["message"])

    def test_validates_required_fields_before_adapter_dispatch(self):
        class RecordingAdapter(MockHoudiniAdapter):
            def __init__(self):
                self.calls = 0

            def create_node(self, node_type, node_name="", parent_path=""):
                self.calls += 1
                return super().create_node(node_type, node_name, parent_path)

        adapter = RecordingAdapter()
        runner = ActionRunner(adapter, thinking_level=lambda: "中")

        result = runner.execute({"action": "create_node"})

        self.assertEqual(False, result["success"])
        self.assertTrue(runner.has_error(result))
        self.assertIn("node_type", result["message"])
        self.assertEqual(0, adapter.calls)

    def test_set_parm_validation_allows_falsey_values(self):
        runner = ActionRunner(MockHoudiniAdapter(), thinking_level=lambda: "中")

        result = runner.execute(
            {
                "action": "set_parm",
                "target_node": "/obj/geo1/box1",
                "parm": "display",
                "value": False,
            }
        )

        self.assertEqual(True, result["success"])

    def test_set_parm_validation_requires_value_key(self):
        runner = ActionRunner(MockHoudiniAdapter(), thinking_level=lambda: "中")

        result = runner.execute(
            {
                "action": "set_parm",
                "target_node": "/obj/geo1/box1",
                "parm": "tx",
            }
        )

        self.assertEqual(False, result["success"])
        self.assertIn("value", result["message"])

    def test_error_detection_uses_status_and_message(self):
        self.assertTrue(ToolResult.from_mapping({"title": "x", "success": False}).has_error())
        self.assertTrue(
            ToolResult.from_mapping(
                {
                    "title": "x",
                    "events": [{"title": "Cook", "detail": "bad", "status": "error"}],
                }
            ).has_error()
        )
        self.assertTrue(ToolResult.from_mapping({"title": "x", "message": "Create failed"}).has_error())

    def test_todo_handlers_are_dispatched(self):
        added = []

        def add_todo(title, detail="", status="pending"):
            added.append((title, detail, status))
            return {"title": "Update todo", "message": title, "events": [], "success": True}

        runner = ActionRunner(MockHoudiniAdapter(), thinking_level=lambda: "中", add_todo=add_todo)
        result = runner.execute({"action": "add_todo", "title": "Inspect", "status": "in_progress"})

        self.assertEqual([("Inspect", "", "in_progress")], added)
        self.assertEqual(True, result["success"])


if __name__ == "__main__":
    unittest.main()
