"""Tests for the upgraded plan_store module."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from houdini_ai_agent.core.plan_store import (
    MAX_PLAN_RESUMES,
    PHASE_AWAITING_CONFIRMATION,
    PHASE_COMPLETED,
    PHASE_EXECUTING,
    PHASE_IDLE,
    PHASE_PLANNING,
    PLAN_COMPLETED,
    PLAN_CONFIRMED,
    PLAN_DRAFT,
    PLAN_EXECUTING,
    PLAN_REJECTED,
    PLAN_TOOL_ASK_QUESTION_SCHEMA,
    PLAN_TOOL_CREATE_SCHEMA,
    PLAN_TOOL_UPDATE_STEP_SCHEMA,
    STEP_DONE,
    STEP_ERROR,
    STEP_PENDING,
    STEP_RUNNING,
    PlanManager,
    PlanStore,
    extract_steps_from_text,
    get_plan_manager,
    normalize_step,
)


class TestNormalizeStep(unittest.TestCase):
    def test_full_dict(self):
        raw = {
            "id": "step-1",
            "title": "Create box",
            "description": "Create a box SOP",
            "tools": ["create_node"],
            "depends_on": [],
            "expected_result": "Box node exists",
            "risk": "low",
        }
        step = normalize_step(raw, 1)
        self.assertEqual(step["id"], "step-1")
        self.assertEqual(step["title"], "Create box")
        self.assertEqual(step["status"], STEP_PENDING)
        self.assertEqual(step["tools"], ["create_node"])

    def test_minimal_dict(self):
        raw = {"title": "Do something"}
        step = normalize_step(raw, 3)
        self.assertEqual(step["id"], "step-3")
        self.assertEqual(step["title"], "Do something")
        self.assertEqual(step["status"], STEP_PENDING)

    def test_non_dict_input(self):
        step = normalize_step("Just a string", 1)
        self.assertEqual(step["id"], "step-1")
        self.assertEqual(step["title"], "Just a string")

    def test_tools_string_parsed(self):
        raw = {"title": "T", "tools": "create_node, set_parm"}
        step = normalize_step(raw, 1)
        self.assertEqual(step["tools"], ["create_node", "set_parm"])

    def test_depends_on_non_list_normalized(self):
        raw = {"title": "T", "depends_on": "step-1"}
        step = normalize_step(raw, 1)
        self.assertEqual(step["depends_on"], [])


class TestExtractStepsFromText(unittest.TestCase):
    def test_numbered_list(self):
        text = "1. Create box\n2. Set height\n3. Connect nodes"
        steps = extract_steps_from_text(text)
        self.assertEqual(len(steps), 3)
        self.assertEqual(steps[0]["title"], "Create box")
        self.assertTrue(steps[1]["depends_on"])

    def test_chinese_semicolons(self):
        text = "创建节点；设置参数；连接节点"
        steps = extract_steps_from_text(text)
        self.assertEqual(len(steps), 3)

    def test_empty_text(self):
        steps = extract_steps_from_text("")
        self.assertEqual(steps, [])

    def test_plan_prefix_stripped(self):
        text = "计划：1. 第一步\n2. 第二步"
        steps = extract_steps_from_text(text)
        self.assertTrue(len(steps) >= 1)


class TestPlanManagerCreate(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self._patcher = patch("houdini_ai_agent.core.plan_store._ensure_plans_dir",
                              return_value=Path(self.tmp_dir))
        self._patcher.start()
        self._plan_path_patcher = patch("houdini_ai_agent.core.plan_store._plan_path",
                                        lambda sid: Path(self.tmp_dir) / f"plan_{sid}.json")
        self._plan_path_patcher.start()
        self._archive_patcher = patch("houdini_ai_agent.core.plan_store._archive_path",
                                      lambda sid: Path(self.tmp_dir) / f"plan_{sid}_archived.json")
        self._archive_patcher.start()
        self.manager = PlanManager()

    def tearDown(self):
        self._patcher.stop()
        self._plan_path_patcher.stop()
        self._archive_patcher.stop()
        import shutil
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_create_basic_plan(self):
        plan = self.manager.create_plan("sess1", {
            "title": "Test Plan",
            "overview": "A test",
            "steps": [
                {"id": "step-1", "title": "Step 1", "description": "Do stuff",
                 "tools": ["create_node"], "expected_result": "Node created"},
                {"id": "step-2", "title": "Step 2", "description": "More stuff",
                 "tools": ["set_parm"], "expected_result": "Param set",
                 "depends_on": ["step-1"]},
            ],
        })
        self.assertEqual(plan["status"], PLAN_DRAFT)
        self.assertEqual(plan["title"], "Test Plan")
        self.assertEqual(len(plan["steps"]), 2)
        self.assertEqual(plan["steps"][0]["id"], "step-1")
        self.assertEqual(plan["steps"][1]["depends_on"], ["step-1"])

    def test_create_archives_old_plan(self):
        self.manager.create_plan("sess1", {"title": "Old", "overview": "", "steps": [
            {"id": "s1", "title": "T", "description": "D", "tools": [], "expected_result": ""}
        ]})
        self.manager.create_plan("sess1", {"title": "New", "overview": "", "steps": [
            {"id": "s1", "title": "T", "description": "D", "tools": [], "expected_result": ""}
        ]})
        plan = self.manager.load_plan("sess1")
        self.assertEqual(plan["title"], "New")
        # Archived file should exist
        archived = Path(self.tmp_dir) / "plan_sess1_archived.json"
        self.assertTrue(archived.exists())

    def test_create_with_architecture(self):
        plan = self.manager.create_plan("sess1", {
            "title": "Arch Plan",
            "overview": "Has architecture",
            "steps": [
                {"id": "s1", "title": "T", "description": "D", "tools": [], "expected_result": ""}
            ],
            "architecture": {
                "nodes": [{"id": "grid1", "label": "Grid"}],
                "connections": [{"from": "grid1", "to": "null1"}],
            },
        })
        self.assertIn("nodes", plan["architecture"])
        self.assertIn("connections", plan["architecture"])

    def test_persistence(self):
        self.manager.create_plan("sess1", {"title": "Persist", "overview": "", "steps": [
            {"id": "s1", "title": "T", "description": "D", "tools": [], "expected_result": ""}
        ]})
        # Load from fresh manager
        manager2 = PlanManager()
        plan = manager2.load_plan("sess1")
        self.assertIsNotNone(plan)
        self.assertEqual(plan["title"], "Persist")


class TestPlanManagerStateTransitions(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self._patcher = patch("houdini_ai_agent.core.plan_store._ensure_plans_dir",
                              return_value=Path(self.tmp_dir))
        self._patcher.start()
        self._plan_path_patcher = patch("houdini_ai_agent.core.plan_store._plan_path",
                                        lambda sid: Path(self.tmp_dir) / f"plan_{sid}.json")
        self._plan_path_patcher.start()
        self._archive_patcher = patch("houdini_ai_agent.core.plan_store._archive_path",
                                      lambda sid: Path(self.tmp_dir) / f"plan_{sid}_archived.json")
        self._archive_patcher.start()
        self.manager = PlanManager()

    def tearDown(self):
        self._patcher.stop()
        self._plan_path_patcher.stop()
        self._archive_patcher.stop()
        import shutil
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def _create_plan(self, n_steps=2):
        steps = [
            {"id": f"step-{i}", "title": f"Step {i}", "description": f"Desc {i}",
             "tools": [], "expected_result": f"Result {i}"}
            for i in range(1, n_steps + 1)
        ]
        return self.manager.create_plan("test", {
            "title": "Test", "overview": "", "steps": steps
        })

    def test_confirm_transitions(self):
        self._create_plan()
        plan = self.manager.confirm_plan("test")
        self.assertEqual(plan["status"], PLAN_CONFIRMED)

    def test_reject_marks_rejected(self):
        self._create_plan()
        self.manager.reject_plan("test")
        plan = self.manager.load_plan("test")
        self.assertEqual(plan["status"], PLAN_REJECTED)

    def test_update_step_to_running_auto_transitions_to_executing(self):
        self._create_plan()
        self.manager.confirm_plan("test")
        plan = self.manager.update_step("test", "step-1", STEP_RUNNING)
        self.assertEqual(plan["status"], PLAN_EXECUTING)

    def test_update_all_done_transitions_to_completed(self):
        self._create_plan(2)
        self.manager.confirm_plan("test")
        self.manager.update_step("test", "step-1", STEP_RUNNING)
        self.manager.update_step("test", "step-1", STEP_DONE)
        self.manager.update_step("test", "step-2", STEP_RUNNING)
        plan = self.manager.update_step("test", "step-2", STEP_DONE)
        self.assertEqual(plan["status"], PLAN_COMPLETED)

    def test_update_with_errors_completes(self):
        self._create_plan(2)
        self.manager.confirm_plan("test")
        self.manager.update_step("test", "step-1", STEP_DONE)
        plan = self.manager.update_step("test", "step-2", STEP_ERROR, "Failed")
        self.assertEqual(plan["status"], PLAN_COMPLETED)
        self.assertEqual(plan["steps"][1]["result_summary"], "Failed")

    def test_update_nonexistent_step_noop(self):
        self._create_plan()
        plan = self.manager.update_step("test", "step-99", STEP_DONE)
        self.assertIsNotNone(plan)

    def test_update_no_plan_returns_none(self):
        plan = self.manager.update_step("nonexistent", "step-1", STEP_DONE)
        self.assertIsNone(plan)


class TestPlanManagerContext(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self._patcher = patch("houdini_ai_agent.core.plan_store._ensure_plans_dir",
                              return_value=Path(self.tmp_dir))
        self._patcher.start()
        self._plan_path_patcher = patch("houdini_ai_agent.core.plan_store._plan_path",
                                        lambda sid: Path(self.tmp_dir) / f"plan_{sid}.json")
        self._plan_path_patcher.start()
        self._archive_patcher = patch("houdini_ai_agent.core.plan_store._archive_path",
                                      lambda sid: Path(self.tmp_dir) / f"plan_{sid}_archived.json")
        self._archive_patcher.start()
        self.manager = PlanManager()

    def tearDown(self):
        self._patcher.stop()
        self._plan_path_patcher.stop()
        self._archive_patcher.stop()
        import shutil
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_draft_returns_empty(self):
        self.manager.create_plan("test", {"title": "T", "overview": "", "steps": [
            {"id": "s1", "title": "T", "description": "D", "tools": [], "expected_result": ""}
        ]})
        ctx = self.manager.get_plan_for_context("test")
        self.assertEqual(ctx, "")

    def test_confirmed_returns_context(self):
        self.manager.create_plan("test", {"title": "My Plan", "overview": "", "steps": [
            {"id": "s1", "title": "Do X", "description": "D", "tools": ["create_node"],
             "expected_result": "Node exists"},
        ]})
        self.manager.confirm_plan("test")
        ctx = self.manager.get_plan_for_context("test")
        self.assertIn("Active Plan: My Plan", ctx)
        self.assertIn("0/1 done", ctx)

    def test_executing_shows_running_step(self):
        self.manager.create_plan("test", {"title": "T", "overview": "", "steps": [
            {"id": "s1", "title": "Step 1", "description": "D", "tools": ["create_node"],
             "expected_result": "R", "fallback": "Try again"},
        ]})
        self.manager.confirm_plan("test")
        self.manager.update_step("test", "s1", STEP_RUNNING)
        ctx = self.manager.get_plan_for_context("test")
        self.assertIn("Current: s1", ctx)
        self.assertIn("Fallback: Try again", ctx)

    def test_no_plan_returns_empty(self):
        ctx = self.manager.get_plan_for_context("nonexistent")
        self.assertEqual(ctx, "")


class TestPlanManagerAutoContinuation(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self._patcher = patch("houdini_ai_agent.core.plan_store._ensure_plans_dir",
                              return_value=Path(self.tmp_dir))
        self._patcher.start()
        self._plan_path_patcher = patch("houdini_ai_agent.core.plan_store._plan_path",
                                        lambda sid: Path(self.tmp_dir) / f"plan_{sid}.json")
        self._plan_path_patcher.start()
        self._archive_patcher = patch("houdini_ai_agent.core.plan_store._archive_path",
                                      lambda sid: Path(self.tmp_dir) / f"plan_{sid}_archived.json")
        self._archive_patcher.start()
        self.manager = PlanManager()

    def tearDown(self):
        self._patcher.stop()
        self._plan_path_patcher.stop()
        self._archive_patcher.stop()
        import shutil
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def _create_executing_plan(self, n_steps=3):
        steps = [
            {"id": f"s{i}", "title": f"Step {i}", "description": "D",
             "tools": [], "expected_result": "R"}
            for i in range(1, n_steps + 1)
        ]
        self.manager.create_plan("test", {"title": "T", "overview": "", "steps": steps})
        self.manager.confirm_plan("test")

    def test_incomplete_returns_message(self):
        self._create_executing_plan(3)
        # Complete only step 1
        self.manager.update_step("test", "s1", STEP_DONE)
        msg = self.manager.check_plan_incomplete("test")
        self.assertIsNotNone(msg)
        self.assertIn("Plan Incomplete", msg)
        self.assertIn("1/3", msg)

    def test_complete_returns_none(self):
        self._create_executing_plan(2)
        self.manager.update_step("test", "s1", STEP_DONE)
        self.manager.update_step("test", "s2", STEP_DONE)
        msg = self.manager.check_plan_incomplete("test")
        self.assertIsNone(msg)

    def test_max_resumes_returns_none(self):
        self._create_executing_plan(2)
        self.manager.update_step("test", "s1", STEP_DONE)
        for _ in range(MAX_PLAN_RESUMES):
            msg = self.manager.check_plan_incomplete("test")
        # After max resumes, should return None
        msg = self.manager.check_plan_incomplete("test")
        self.assertIsNone(msg)

    def test_no_plan_returns_none(self):
        msg = self.manager.check_plan_incomplete("nonexistent")
        self.assertIsNone(msg)

    def test_resume_count_tracking(self):
        self._create_executing_plan(2)
        self.assertEqual(self.manager.get_resume_count("test"), 0)
        self.manager.check_plan_incomplete("test")
        self.assertEqual(self.manager.get_resume_count("test"), 1)
        self.manager.reset_resume_count("test")
        self.assertEqual(self.manager.get_resume_count("test"), 0)


class TestPlanManagerExecutableSteps(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self._patcher = patch("houdini_ai_agent.core.plan_store._ensure_plans_dir",
                              return_value=Path(self.tmp_dir))
        self._patcher.start()
        self._plan_path_patcher = patch("houdini_ai_agent.core.plan_store._plan_path",
                                        lambda sid: Path(self.tmp_dir) / f"plan_{sid}.json")
        self._plan_path_patcher.start()
        self._archive_patcher = patch("houdini_ai_agent.core.plan_store._archive_path",
                                      lambda sid: Path(self.tmp_dir) / f"plan_{sid}_archived.json")
        self._archive_patcher.start()
        self.manager = PlanManager()

    def tearDown(self):
        self._patcher.stop()
        self._plan_path_patcher.stop()
        self._archive_patcher.stop()
        import shutil
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_dag_respects_depends_on(self):
        self.manager.create_plan("test", {
            "title": "T", "overview": "", "steps": [
                {"id": "s1", "title": "S1", "description": "D", "tools": [], "expected_result": "R"},
                {"id": "s2", "title": "S2", "description": "D", "tools": [], "expected_result": "R",
                 "depends_on": ["s1"]},
                {"id": "s3", "title": "S3", "description": "D", "tools": [], "expected_result": "R"},
            ]
        })
        self.manager.confirm_plan("test")
        # Initially s1 and s3 are executable (no deps), s2 depends on s1
        executable = self.manager.get_executable_steps("test")
        ids = [s["id"] for s in executable]
        self.assertIn("s1", ids)
        self.assertIn("s3", ids)
        self.assertNotIn("s2", ids)

        # After s1 done, s2 becomes executable
        self.manager.update_step("test", "s1", STEP_DONE)
        executable = self.manager.get_executable_steps("test")
        ids = [s["id"] for s in executable]
        self.assertIn("s2", ids)
        self.assertIn("s3", ids)


class TestPlanManagerStats(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self._patcher = patch("houdini_ai_agent.core.plan_store._ensure_plans_dir",
                              return_value=Path(self.tmp_dir))
        self._patcher.start()
        self._plan_path_patcher = patch("houdini_ai_agent.core.plan_store._plan_path",
                                        lambda sid: Path(self.tmp_dir) / f"plan_{sid}.json")
        self._plan_path_patcher.start()
        self._archive_patcher = patch("houdini_ai_agent.core.plan_store._archive_path",
                                      lambda sid: Path(self.tmp_dir) / f"plan_{sid}_archived.json")
        self._archive_patcher.start()
        self.manager = PlanManager()

    def tearDown(self):
        self._patcher.stop()
        self._plan_path_patcher.stop()
        self._archive_patcher.stop()
        import shutil
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_stats(self):
        self.manager.create_plan("test", {
            "title": "T", "overview": "", "steps": [
                {"id": "s1", "title": "S1", "description": "D", "tools": [], "expected_result": "R"},
                {"id": "s2", "title": "S2", "description": "D", "tools": [], "expected_result": "R"},
            ]
        })
        self.manager.confirm_plan("test")
        self.manager.update_step("test", "s1", STEP_DONE)
        stats = self.manager.plan_stats("test")
        self.assertEqual(stats["total"], 2)
        self.assertEqual(stats["done"], 1)
        self.assertEqual(stats["pending"], 1)

    def test_no_plan_stats(self):
        stats = self.manager.plan_stats("nonexistent")
        self.assertEqual(stats, {})


class TestPlanManagerDelete(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self._patcher = patch("houdini_ai_agent.core.plan_store._ensure_plans_dir",
                              return_value=Path(self.tmp_dir))
        self._patcher.start()
        self._plan_path_patcher = patch("houdini_ai_agent.core.plan_store._plan_path",
                                        lambda sid: Path(self.tmp_dir) / f"plan_{sid}.json")
        self._plan_path_patcher.start()
        self._archive_patcher = patch("houdini_ai_agent.core.plan_store._archive_path",
                                      lambda sid: Path(self.tmp_dir) / f"plan_{sid}_archived.json")
        self._archive_patcher.start()
        self.manager = PlanManager()

    def tearDown(self):
        self._patcher.stop()
        self._plan_path_patcher.stop()
        self._archive_patcher.stop()
        import shutil
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_delete_plan(self):
        self.manager.create_plan("test", {"title": "T", "overview": "", "steps": [
            {"id": "s1", "title": "T", "description": "D", "tools": [], "expected_result": ""}
        ]})
        self.assertTrue(self.manager.delete_plan("test"))
        self.assertIsNone(self.manager.load_plan("test"))

    def test_delete_nonexistent(self):
        self.assertTrue(self.manager.delete_plan("nonexistent"))


class TestToolSchemas(unittest.TestCase):
    def test_create_plan_schema_has_required_fields(self):
        props = PLAN_TOOL_CREATE_SCHEMA["properties"]
        self.assertIn("title", props)
        self.assertIn("overview", props)
        self.assertIn("steps", props)
        self.assertIn("architecture", props)
        required = PLAN_TOOL_CREATE_SCHEMA["required"]
        self.assertIn("title", required)
        self.assertIn("steps", required)

    def test_update_step_schema_has_required_fields(self):
        props = PLAN_TOOL_UPDATE_STEP_SCHEMA["properties"]
        self.assertIn("step_id", props)
        self.assertIn("status", props)
        self.assertIn("result_summary", props)

    def test_ask_question_schema_structure(self):
        props = PLAN_TOOL_ASK_QUESTION_SCHEMA["properties"]
        self.assertIn("questions", props)
        q_items = props["questions"]["items"]["properties"]
        self.assertIn("id", q_items)
        self.assertIn("prompt", q_items)
        self.assertIn("options", q_items)


class TestPlanStoreBackwardCompat(unittest.TestCase):
    def setUp(self):
        self.store = PlanStore()

    def test_plans_from_dict(self):
        raw = {
            "p1": {
                "id": "p1",
                "status": "draft",
                "steps": [{"id": "s1", "title": "T", "status": "pending"}],
            }
        }
        plans = self.store.plans_from_dict(raw)
        self.assertIn("p1", plans)

    def test_plans_from_dict_executing_becomes_paused(self):
        raw = {
            "p1": {
                "id": "p1",
                "status": PLAN_EXECUTING,
                "steps": [{"id": "s1", "title": "T", "status": STEP_RUNNING}],
            }
        }
        plans = self.store.plans_from_dict(raw)
        self.assertEqual(plans["p1"]["status"], "paused")
        self.assertEqual(plans["p1"]["steps"][0]["status"], STEP_PENDING)

    def test_plan_from_text(self):
        plan = self.store.plan_from_text("1. Step one\n2. Step two", "zh")
        self.assertEqual(plan["status"], PLAN_DRAFT)
        self.assertTrue(len(plan["steps"]) >= 1)

    def test_set_step_status(self):
        plan = {
            "steps": [{"id": "s1", "title": "T", "status": STEP_PENDING}]
        }
        self.store.set_step_status(plan, 0, STEP_DONE, "Done!")
        self.assertEqual(plan["steps"][0]["status"], STEP_DONE)
        self.assertEqual(plan["steps"][0]["result_summary"], "Done!")

    def test_normalize_plan(self):
        data = {
            "title": "Test Plan",
            "steps": [{"id": "s1", "title": "Step 1", "description": "D"}],
        }
        plan = self.store.normalize_plan(data, "source text", "en")
        self.assertEqual(plan["title"], "Test Plan")
        self.assertEqual(len(plan["steps"]), 1)


class TestGetPlanManager(unittest.TestCase):
    def test_singleton(self):
        from houdini_ai_agent.core.plan_store import _manager_instance
        # Reset singleton
        import houdini_ai_agent.core.plan_store as ps
        ps._manager_instance = None
        m1 = get_plan_manager()
        m2 = get_plan_manager()
        self.assertIs(m1, m2)
        ps._manager_instance = None  # Clean up


if __name__ == "__main__":
    unittest.main()
