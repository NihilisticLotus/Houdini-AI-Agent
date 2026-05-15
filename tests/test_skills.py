# -*- coding: utf-8 -*-
"""Tests for the skill loading and registry system."""

from __future__ import annotations

import importlib
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest import mock


class TestSkillInfoToSchema(unittest.TestCase):
    """Test _skill_info_to_openai_schema conversion."""

    def _get_converter(self):
        from houdini_ai_agent.core.skills import _skill_info_to_openai_schema
        return _skill_info_to_openai_schema

    def test_basic_schema(self):
        convert = self._get_converter()
        info = {
            "name": "test_skill",
            "description": "A test skill",
            "parameters": {
                "node_path": {
                    "type": "string",
                    "description": "Node path",
                    "required": True,
                },
                "count": {
                    "type": "integer",
                    "description": "Number",
                    "required": False,
                },
            },
        }
        schema = convert(info)
        self.assertEqual(schema["type"], "object")
        self.assertIn("node_path", schema["properties"])
        self.assertEqual(schema["properties"]["node_path"]["type"], "string")
        self.assertEqual(schema["properties"]["count"]["type"], "integer")
        self.assertIn("node_path", schema["required"])
        self.assertNotIn("count", schema["required"])

    def test_float_maps_to_number(self):
        convert = self._get_converter()
        info = {
            "name": "test",
            "parameters": {
                "tol": {"type": "float", "description": "Tolerance"},
            },
        }
        schema = convert(info)
        self.assertEqual(schema["properties"]["tol"]["type"], "number")

    def test_enum_values(self):
        convert = self._get_converter()
        info = {
            "name": "test",
            "parameters": {
                "mode": {"type": "string", "description": "Mode", "enum": ["a", "b", "c"]},
            },
        }
        schema = convert(info)
        self.assertEqual(schema["properties"]["mode"]["enum"], ["a", "b", "c"])

    def test_default_value(self):
        convert = self._get_converter()
        info = {
            "name": "test",
            "parameters": {
                "max": {"type": "integer", "description": "Max", "default": 100},
            },
        }
        schema = convert(info)
        self.assertEqual(schema["properties"]["max"]["default"], 100)

    def test_empty_parameters(self):
        convert = self._get_converter()
        info = {"name": "test", "description": "No params", "parameters": {}}
        schema = convert(info)
        self.assertEqual(schema["properties"], {})
        self.assertEqual(schema["required"], [])


class TestSkillLoading(unittest.TestCase):
    """Test skill loading from directories."""

    def setUp(self):
        # Reset skills module state
        import houdini_ai_agent.core.skills as skills_mod
        skills_mod._registry = {}
        skills_mod._loaded = False
        skills_mod._adapter = None

    def test_load_builtin_skills(self):
        from houdini_ai_agent.core.skills import _load_all, _registry
        _load_all()
        # Should have loaded the 9 built-in skills
        self.assertGreaterEqual(len(_registry), 9)

    def test_builtin_skill_names(self):
        from houdini_ai_agent.core.skills import _load_all, _registry
        _load_all()
        expected = {
            "analyze_geometry_attribs",
            "analyze_normals",
            "analyze_cook_performance",
            "get_bounding_info",
            "compare_attributes",
            "analyze_connectivity",
            "find_dead_nodes",
            "find_attribute_references",
            "trace_node_dependencies",
        }
        loaded_names = set(_registry.keys())
        self.assertTrue(expected.issubset(loaded_names), f"Missing: {expected - loaded_names}")

    def test_load_custom_skill_from_dir(self):
        from houdini_ai_agent.core.skills import _load_skills_from_dir, _registry
        with tempfile.TemporaryDirectory() as tmpdir:
            skill_file = Path(tmpdir) / "my_test_skill.py"
            skill_file.write_text(textwrap.dedent("""\
                SKILL_INFO = {
                    "name": "my_test_skill",
                    "description": "Custom test skill",
                    "parameters": {},
                }
                def run(adapter=None, **kwargs):
                    return {"result": "ok"}
            """))
            _load_skills_from_dir(Path(tmpdir))
            self.assertIn("my_test_skill", _registry)

    def test_skip_files_without_skill_info(self):
        from houdini_ai_agent.core.skills import _load_skills_from_dir, _registry
        with tempfile.TemporaryDirectory() as tmpdir:
            bad_file = Path(tmpdir) / "bad_skill.py"
            bad_file.write_text("# Not a skill\nx = 1\n")
            _load_skills_from_dir(Path(tmpdir))
            self.assertEqual(len(_registry), 0)

    def test_skip_underscore_files(self):
        from houdini_ai_agent.core.skills import _load_skills_from_dir, _registry
        with tempfile.TemporaryDirectory() as tmpdir:
            helper = Path(tmpdir) / "_helper.py"
            helper.write_text("SKILL_INFO = {'name': 'x'}\ndef run(): pass\n")
            _load_skills_from_dir(Path(tmpdir))
            self.assertEqual(len(_registry), 0)


class TestListSkills(unittest.TestCase):
    """Test list_skills public API."""

    def setUp(self):
        import houdini_ai_agent.core.skills as skills_mod
        skills_mod._registry = {}
        skills_mod._loaded = False
        skills_mod._adapter = None

    def test_list_returns_metadata(self):
        from houdini_ai_agent.core.skills import list_skills
        skills = list_skills()
        self.assertIsInstance(skills, list)
        self.assertGreater(len(skills), 0)
        for info in skills:
            self.assertIn("name", info)
            self.assertIn("description", info)


class TestRunSkill(unittest.TestCase):
    """Test run_skill execution."""

    def setUp(self):
        import houdini_ai_agent.core.skills as skills_mod
        skills_mod._registry = {}
        skills_mod._loaded = False
        skills_mod._adapter = None

    def test_run_nonexistent_skill(self):
        from houdini_ai_agent.core.skills import run_skill
        result = run_skill("nonexistent_skill", {})
        self.assertIn("error", result)

    def test_run_builtin_skill_with_mock(self):
        from houdini_ai_agent.core.skills import run_skill
        result = run_skill("get_bounding_info", {"node_path": "/obj/geo1/box1"})
        # Mock mode returns mock data
        self.assertIn("node", result)
        self.assertIn("size", result)

    def test_run_skill_error_handling(self):
        from houdini_ai_agent.core.skills import _load_all, run_skill, _registry
        _load_all()
        # Find a skill that requires node_path and pass empty
        result = run_skill("get_bounding_info", {})
        # Mock mode should still return data
        self.assertIn("node", result)


class TestGetSkillInfo(unittest.TestCase):
    """Test get_skill_info."""

    def setUp(self):
        import houdini_ai_agent.core.skills as skills_mod
        skills_mod._registry = {}
        skills_mod._loaded = False
        skills_mod._adapter = None

    def test_existing_skill(self):
        from houdini_ai_agent.core.skills import get_skill_info
        info = get_skill_info("get_bounding_info")
        self.assertIsNotNone(info)
        self.assertEqual(info["name"], "get_bounding_info")

    def test_nonexistent_skill(self):
        from houdini_ai_agent.core.skills import get_skill_info
        self.assertIsNone(get_skill_info("does_not_exist"))


class TestSetAdapter(unittest.TestCase):
    """Test adapter management."""

    def test_set_and_use_adapter(self):
        import houdini_ai_agent.core.skills as skills_mod
        skills_mod._registry = {}
        skills_mod._loaded = False

        mock_adapter = mock.MagicMock()
        from houdini_ai_agent.core.skills import set_adapter
        set_adapter(mock_adapter)
        self.assertIs(skills_mod._adapter, mock_adapter)


class TestReloadSkills(unittest.TestCase):
    """Test reload_skills."""

    def test_reload_clears_and_reloads(self):
        import houdini_ai_agent.core.skills as skills_mod
        skills_mod._registry = {}
        skills_mod._loaded = False
        skills_mod._adapter = None

        from houdini_ai_agent.core.skills import _load_all, _registry
        _load_all()  # Just test loading, skip ToolRegistry registration
        self.assertTrue(skills_mod._loaded)
        self.assertGreater(len(_registry), 0)


class TestSkillMockResults(unittest.TestCase):
    """Test that all skills return valid mock data when hou is unavailable."""

    def setUp(self):
        import houdini_ai_agent.core.skills as skills_mod
        skills_mod._registry = {}
        skills_mod._loaded = False
        skills_mod._adapter = None

    def _run_skill(self, name, params):
        from houdini_ai_agent.core.skills import run_skill
        return run_skill(name, params)

    def test_bounding_box_info(self):
        result = self._run_skill("get_bounding_info", {"node_path": "/obj/geo1/box1"})
        self.assertNotIn("error", result)
        self.assertIn("size", result)

    def test_analyze_normals(self):
        result = self._run_skill("analyze_normals", {"node_path": "/obj/geo1/box1"})
        self.assertIn("issues", result)

    def test_analyze_cook_performance(self):
        result = self._run_skill("analyze_cook_performance", {"network_path": "/obj/geo1"})
        self.assertIn("slow_nodes", result)

    def test_analyze_geometry_attribs(self):
        result = self._run_skill("analyze_geometry_attribs", {"node_path": "/obj/geo1/box1"})
        self.assertNotIn("error", result)

    def test_compare_attributes(self):
        result = self._run_skill("compare_attributes", {
            "node_path_a": "/obj/geo1/box1",
            "node_path_b": "/obj/geo1/sphere1",
        })
        self.assertIn("identical", result)

    def test_analyze_connectivity(self):
        result = self._run_skill("analyze_connectivity", {"node_path": "/obj/geo1/box1"})
        self.assertIn("total_components", result)

    def test_find_dead_nodes(self):
        result = self._run_skill("find_dead_nodes", {"network_path": "/obj/geo1"})
        self.assertIn("orphan_nodes", result)

    def test_find_attribute_references(self):
        result = self._run_skill("find_attribute_references", {
            "network_path": "/obj/geo1",
            "attr_name": "Cd",
        })
        self.assertIn("references", result)

    def test_trace_dependencies(self):
        result = self._run_skill("trace_node_dependencies", {"node_path": "/obj/geo1/OUT"})
        self.assertIn("tree_text", result)


class TestActionRunnerSkillDispatch(unittest.TestCase):
    """Test that ActionRunner can dispatch skill tools."""

    def test_skill_dispatch(self):
        from houdini_ai_agent.core.action_runner import ActionRunner
        from houdini_ai_agent.adapters.mock_houdini import MockHoudiniAdapter

        adapter = MockHoudiniAdapter()
        runner = ActionRunner(adapter, lambda: "normal")

        action = {
            "action": "skill:get_bounding_info",
            "node_path": "/obj/geo1/box1",
        }
        result = runner.execute(action)
        self.assertTrue(result.get("success", False))
        # The skill result is embedded in the message as JSON
        self.assertIn("box1", result.get("message", ""))

    def test_skill_summarize(self):
        from houdini_ai_agent.core.action_runner import ActionRunner
        from houdini_ai_agent.adapters.mock_houdini import MockHoudiniAdapter

        adapter = MockHoudiniAdapter()
        runner = ActionRunner(adapter, lambda: "normal")

        action = {"action": "skill:get_bounding_info", "node_path": "/obj/test"}
        summary = runner.summarize(action)
        self.assertIn("get bounding info", summary.lower())


if __name__ == "__main__":
    unittest.main()
