"""Tests for the user rules system (rules_manager)."""

import json
import os
import shutil
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "houdini", "python3.11libs"))

from houdini_ai_agent.core.rules_manager import (
    _new_rule,
    _scan_file_rules,
    add_rule,
    delete_rule,
    ensure_rules_dir,
    get_all_rules,
    get_rules_dir,
    get_rules_for_prompt,
    get_ui_rules,
    reload_rules,
    save_all_ui_rules,
    set_rule_enabled,
    update_rule,
)


class TestNewRule(unittest.TestCase):
    """Tests for _new_rule factory."""

    def test_creates_dict(self):
        rule = _new_rule(title="Test", content="Body")
        self.assertEqual(rule["title"], "Test")
        self.assertEqual(rule["content"], "Body")
        self.assertTrue(rule["enabled"])
        self.assertEqual(len(rule["id"]), 12)
        self.assertGreater(rule["created_at"], 0)

    def test_default_empty(self):
        rule = _new_rule()
        self.assertEqual(rule["title"], "")
        self.assertEqual(rule["content"], "")


class TestFileRules(unittest.TestCase):
    """Tests for file rule scanning."""

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self._orig_dir = Path(__file__).resolve().parent.parent / "rules"

    def tearDown(self):
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_scan_empty_dir(self):
        with patch("houdini_ai_agent.core.rules_manager._RULES_DIR", Path(self._tmpdir)):
            rules = _scan_file_rules()
            self.assertEqual(rules, [])

    def test_scan_md_files(self):
        rules_dir = Path(self._tmpdir)
        (rules_dir / "my_style.md").write_text("# My Style\nUse VEX", encoding="utf-8")
        with patch("houdini_ai_agent.core.rules_manager._RULES_DIR", rules_dir):
            rules = _scan_file_rules()
            self.assertEqual(len(rules), 1)
            self.assertEqual(rules[0]["title"], "my_style")
            self.assertEqual(rules[0]["source"], "file")
            self.assertIn("VEX", rules[0]["content"])
            self.assertTrue(rules[0]["enabled"])

    def test_scan_excludes_underscore(self):
        rules_dir = Path(self._tmpdir)
        (rules_dir / "_example.md").write_text("example", encoding="utf-8")
        (rules_dir / "active.md").write_text("active", encoding="utf-8")
        with patch("houdini_ai_agent.core.rules_manager._RULES_DIR", rules_dir):
            rules = _scan_file_rules()
            self.assertEqual(len(rules), 1)
            self.assertEqual(rules[0]["title"], "active")

    def test_scan_txt_files(self):
        rules_dir = Path(self._tmpdir)
        (rules_dir / "notes.txt").write_text("Some notes", encoding="utf-8")
        with patch("houdini_ai_agent.core.rules_manager._RULES_DIR", rules_dir):
            rules = _scan_file_rules()
            self.assertEqual(len(rules), 1)
            self.assertEqual(rules[0]["title"], "notes")

    def test_scan_ignores_non_text(self):
        rules_dir = Path(self._tmpdir)
        (rules_dir / "data.json").write_text("{}", encoding="utf-8")
        with patch("houdini_ai_agent.core.rules_manager._RULES_DIR", rules_dir):
            rules = _scan_file_rules()
            self.assertEqual(rules, [])

    def test_file_rule_id_format(self):
        rules_dir = Path(self._tmpdir)
        (rules_dir / "style.md").write_text("content", encoding="utf-8")
        with patch("houdini_ai_agent.core.rules_manager._RULES_DIR", rules_dir):
            rules = _scan_file_rules()
            self.assertTrue(rules[0]["id"].startswith("file:"))


class TestUIRulesCRUD(unittest.TestCase):
    """Tests for UI rule CRUD operations."""

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self._rules_path = Path(self._tmpdir) / "user_rules.json"
        self._rules_path.write_text("[]", encoding="utf-8")
        reload_rules()
        self._patcher = patch(
            "houdini_ai_agent.core.rules_manager._USER_RULES_PATH",
            self._rules_path,
        )
        self._patcher.start()
        # Clear cache after patching
        import houdini_ai_agent.core.rules_manager as rm
        rm._ui_rules_cache = None

    def tearDown(self):
        self._patcher.stop()
        reload_rules()
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_add_rule(self):
        rule = add_rule(title="Test Rule", content="Do something")
        self.assertEqual(rule["title"], "Test Rule")
        self.assertEqual(rule["source"], "ui")
        # Verify persisted
        data = json.loads(self._rules_path.read_text(encoding="utf-8"))
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["title"], "Test Rule")

    def test_get_ui_rules(self):
        add_rule(title="R1", content="C1")
        add_rule(title="R2", content="C2")
        rules = get_ui_rules()
        self.assertEqual(len(rules), 2)

    def test_update_rule(self):
        rule = add_rule(title="Original", content="Original content")
        updated = update_rule(rule["id"], title="Updated", content="New content")
        self.assertEqual(updated["title"], "Updated")
        self.assertEqual(updated["content"], "New content")

    def test_update_nonexistent(self):
        result = update_rule("nonexistent_id", title="X")
        self.assertIsNone(result)

    def test_delete_rule(self):
        rule = add_rule(title="ToDelete", content="bye")
        self.assertTrue(delete_rule(rule["id"]))
        rules = get_ui_rules()
        self.assertEqual(len(rules), 0)

    def test_delete_nonexistent(self):
        self.assertFalse(delete_rule("nonexistent_id"))

    def test_set_rule_enabled(self):
        rule = add_rule(title="Toggle", content="test")
        self.assertTrue(set_rule_enabled(rule["id"], False))
        rules = get_ui_rules()
        self.assertFalse(rules[0]["enabled"])

    def test_save_all_ui_rules(self):
        rules = [
            {"id": "abc", "title": "T", "content": "C", "enabled": True, "created_at": 0},
        ]
        save_all_ui_rules(rules)
        data = json.loads(self._rules_path.read_text(encoding="utf-8"))
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["id"], "abc")

    def test_reload_clears_cache(self):
        add_rule(title="Cached", content="test")
        reload_rules()
        # After reload, cache is cleared; next call reads from disk
        rules = get_ui_rules()
        self.assertEqual(len(rules), 1)


class TestGetAllRules(unittest.TestCase):
    """Tests for get_all_rules combining UI + file rules."""

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self._rules_path = Path(self._tmpdir) / "user_rules.json"
        self._rules_path.write_text("[]", encoding="utf-8")
        self._file_rules_dir = Path(self._tmpdir) / "rules"
        self._file_rules_dir.mkdir()
        (self._file_rules_dir / "file_rule.md").write_text("File content", encoding="utf-8")
        reload_rules()

        self._patches = [
            patch("houdini_ai_agent.core.rules_manager._USER_RULES_PATH", self._rules_path),
            patch("houdini_ai_agent.core.rules_manager._RULES_DIR", self._file_rules_dir),
        ]
        for p in self._patches:
            p.start()
        import houdini_ai_agent.core.rules_manager as rm
        rm._ui_rules_cache = None

    def tearDown(self):
        for p in self._patches:
            p.stop()
        reload_rules()
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_combines_ui_and_file(self):
        add_rule(title="UI Rule", content="UI content")
        all_rules = get_all_rules()
        self.assertEqual(len(all_rules), 2)
        sources = [r["source"] for r in all_rules]
        self.assertIn("ui", sources)
        self.assertIn("file", sources)

    def test_force_reload(self):
        add_rule(title="R1", content="C1")
        rules1 = get_all_rules()
        # Add another directly to file
        data = json.loads(self._rules_path.read_text(encoding="utf-8"))
        data.append({"id": "manual", "title": "Manual", "content": "M", "enabled": True})
        self._rules_path.write_text(json.dumps(data), encoding="utf-8")
        # Without force_reload, cache is stale
        rules2 = get_all_rules()
        self.assertEqual(len(rules2), len(rules1))
        # With force_reload
        rules3 = get_all_rules(force_reload=True)
        self.assertEqual(len(rules3), len(rules1) + 1)


class TestGetRulesForPrompt(unittest.TestCase):
    """Tests for get_rules_for_prompt formatting."""

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self._rules_path = Path(self._tmpdir) / "user_rules.json"
        self._rules_path.write_text("[]", encoding="utf-8")
        self._file_rules_dir = Path(self._tmpdir) / "rules"
        self._file_rules_dir.mkdir()
        reload_rules()

        self._patches = [
            patch("houdini_ai_agent.core.rules_manager._USER_RULES_PATH", self._rules_path),
            patch("houdini_ai_agent.core.rules_manager._RULES_DIR", self._file_rules_dir),
        ]
        for p in self._patches:
            p.start()
        import houdini_ai_agent.core.rules_manager as rm
        rm._ui_rules_cache = None

    def tearDown(self):
        for p in self._patches:
            p.stop()
        reload_rules()
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_empty_returns_empty(self):
        result = get_rules_for_prompt()
        self.assertEqual(result, "")

    def test_format_with_title(self):
        add_rule(title="VEX Style", content="Always use inline VEX")
        result = get_rules_for_prompt()
        self.assertIn("<user_rules>", result)
        self.assertIn("</user_rules>", result)
        self.assertIn("## VEX Style", result)
        self.assertIn("Always use inline VEX", result)

    def test_format_without_title(self):
        add_rule(title="", content="Untitled rule body")
        result = get_rules_for_prompt()
        self.assertIn("Untitled rule body", result)
        # No ## heading for empty title
        self.assertNotIn("## \n", result)

    def test_disabled_excluded(self):
        rule = add_rule(title="Disabled Rule", content="Should not appear")
        set_rule_enabled(rule["id"], False)
        result = get_rules_for_prompt()
        self.assertEqual(result, "")

    def test_file_rules_included(self):
        (self._file_rules_dir / "test_rule.md").write_text("File rule content", encoding="utf-8")
        reload_rules()
        import houdini_ai_agent.core.rules_manager as rm
        rm._ui_rules_cache = None
        result = get_rules_for_prompt()
        self.assertIn("File rule content", result)

    def test_empty_content_skipped(self):
        add_rule(title="Empty", content="")
        result = get_rules_for_prompt()
        self.assertEqual(result, "")

    def test_multiple_rules(self):
        add_rule(title="Rule A", content="Content A")
        add_rule(title="Rule B", content="Content B")
        result = get_rules_for_prompt()
        self.assertIn("Content A", result)
        self.assertIn("Content B", result)
        self.assertIn("## Rule A", result)
        self.assertIn("## Rule B", result)


class TestRulesDir(unittest.TestCase):
    """Tests for get_rules_dir and ensure_rules_dir."""

    def test_get_rules_dir_returns_path(self):
        d = get_rules_dir()
        self.assertIsInstance(d, Path)

    def test_ensure_rules_dir(self):
        tmpdir = tempfile.mkdtemp()
        target = Path(tmpdir) / "sub" / "rules"
        try:
            with patch("houdini_ai_agent.core.rules_manager._RULES_DIR", target):
                result = ensure_rules_dir()
                self.assertTrue(target.exists())
                self.assertEqual(result, target)
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
