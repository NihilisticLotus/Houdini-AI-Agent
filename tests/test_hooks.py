"""Tests for the plugin hook system."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
import shutil
import unittest
from unittest.mock import MagicMock, patch


class TestHookManagerCore(unittest.TestCase):
    """Test HookManager singleton, registration, and dispatch."""

    def setUp(self):
        # Reset singleton for each test
        from houdini_ai_agent.core.hooks.hook_manager import HookManager
        HookManager._instance = None
        HookManager._init_done = False

    def test_singleton(self):
        from houdini_ai_agent.core.hooks import get_hook_manager
        m1 = get_hook_manager()
        m2 = get_hook_manager()
        self.assertIs(m1, m2)

    def test_fire_notify(self):
        from houdini_ai_agent.core.hooks import get_hook_manager
        manager = get_hook_manager()
        received = []
        manager.register("on_message_sent", lambda text, **kw: received.append(text))
        manager.fire("on_message_sent", text="hello")
        self.assertEqual(received, ["hello"])

    def test_fire_filter(self):
        from houdini_ai_agent.core.hooks import get_hook_manager
        manager = get_hook_manager()
        manager.register("on_message_sent", lambda v, **kw: v.upper())
        result = manager.fire_filter("on_message_sent", "hello")
        self.assertEqual(result, "HELLO")

    def test_fire_filter_none_keeps_value(self):
        from houdini_ai_agent.core.hooks import get_hook_manager
        manager = get_hook_manager()
        manager.register("on_message_sent", lambda v, **kw: None)
        result = manager.fire_filter("on_message_sent", "hello")
        self.assertEqual(result, "hello")

    def test_priority_ordering(self):
        from houdini_ai_agent.core.hooks import get_hook_manager
        manager = get_hook_manager()
        order = []
        manager.register("on_tool_after", lambda **kw: order.append("low"), priority=10)
        manager.register("on_tool_after", lambda **kw: order.append("high"), priority=0)
        manager.fire("on_tool_after")
        self.assertEqual(order, ["high", "low"])

    def test_unregister(self):
        from houdini_ai_agent.core.hooks import get_hook_manager
        manager = get_hook_manager()
        received = []
        cb = lambda **kw: received.append(1)
        manager.register("on_error", cb)
        manager.fire("on_error")
        self.assertEqual(received, [1])
        manager.unregister("on_error", cb)
        manager.fire("on_error")
        self.assertEqual(received, [1])

    def test_exception_does_not_propagate(self):
        from houdini_ai_agent.core.hooks import get_hook_manager
        manager = get_hook_manager()
        manager.register("on_error", lambda **kw: 1 / 0)
        # Should not raise
        manager.fire("on_error")

    def test_fire_filter_exception_does_not_propagate(self):
        from houdini_ai_agent.core.hooks import get_hook_manager
        manager = get_hook_manager()
        manager.register("on_message_sent", lambda v, **kw: 1 / 0)
        result = manager.fire_filter("on_message_sent", "hello")
        self.assertEqual(result, "hello")


class TestExternalTools(unittest.TestCase):
    """Test external tool registration and execution."""

    def setUp(self):
        from houdini_ai_agent.core.hooks.hook_manager import HookManager
        HookManager._instance = None
        HookManager._init_done = False

    def test_register_and_execute_tool(self):
        from houdini_ai_agent.core.hooks import get_hook_manager
        manager = get_hook_manager()
        schema = {"type": "object", "properties": {"name": {"type": "string"}}}
        manager.register_tool("test_tool", "A test tool", schema,
                              lambda args: {"success": True, "result": f"hi {args.get('name')}"})
        self.assertTrue(manager.has_external_tool("test_tool"))
        result = manager.execute_external_tool("test_tool", {"name": "world"})
        self.assertTrue(result["success"])
        self.assertEqual(result["result"], "hi world")

    def test_execute_unknown_tool(self):
        from houdini_ai_agent.core.hooks import get_hook_manager
        manager = get_hook_manager()
        result = manager.execute_external_tool("nonexistent", {})
        self.assertFalse(result["success"])

    def test_tool_exception_handled(self):
        from houdini_ai_agent.core.hooks import get_hook_manager
        manager = get_hook_manager()
        manager.register_tool("bad_tool", "Bad", {}, lambda args: 1 / 0)
        result = manager.execute_external_tool("bad_tool", {})
        self.assertFalse(result["success"])
        self.assertIn("division by zero", result["error"])

    def test_unregister_tool(self):
        from houdini_ai_agent.core.hooks import get_hook_manager
        manager = get_hook_manager()
        manager.register_tool("temp_tool", "Temp", {}, lambda args: {"success": True})
        self.assertTrue(manager.has_external_tool("temp_tool"))
        manager.unregister_tool("temp_tool")
        self.assertFalse(manager.has_external_tool("temp_tool"))

    def test_get_external_tools_schemas(self):
        from houdini_ai_agent.core.hooks import get_hook_manager
        manager = get_hook_manager()
        schema = {"type": "object", "properties": {"x": {"type": "integer"}}}
        manager.register_tool("schema_tool", "Desc", schema, lambda args: {})
        tools = manager.get_external_tools()
        self.assertTrue(any(t["function"]["name"] == "schema_tool" for t in tools))


class TestPluginContext(unittest.TestCase):
    """Test PluginContext API proxy."""

    def setUp(self):
        from houdini_ai_agent.core.hooks.hook_manager import HookManager
        HookManager._instance = None
        HookManager._init_done = False

    def test_on_registers_hook(self):
        from houdini_ai_agent.core.hooks import get_hook_manager
        from houdini_ai_agent.core.hooks.plugin_context import PluginContext
        manager = get_hook_manager()
        ctx = PluginContext("test", manager, {}, Path("/tmp/test.json"))
        received = []
        ctx.on("on_message_sent", lambda **kw: received.append(kw.get("text")))
        manager.fire("on_message_sent", text="hello")
        self.assertEqual(received, ["hello"])

    def test_register_tool_via_context(self):
        from houdini_ai_agent.core.hooks import get_hook_manager
        from houdini_ai_agent.core.hooks.plugin_context import PluginContext
        manager = get_hook_manager()
        ctx = PluginContext("test", manager, {}, Path("/tmp/test.json"))
        ctx.register_tool("ctx_tool", "Test", {}, lambda args: {"success": True, "result": "ok"})
        self.assertTrue(manager.has_external_tool("ctx_tool"))

    def test_cleanup_removes_hooks(self):
        from houdini_ai_agent.core.hooks import get_hook_manager
        from houdini_ai_agent.core.hooks.plugin_context import PluginContext
        manager = get_hook_manager()
        ctx = PluginContext("test", manager, {}, Path("/tmp/test.json"))
        received = []
        ctx.on("on_error", lambda **kw: received.append(1))
        manager.fire("on_error")
        self.assertEqual(received, [1])
        ctx._cleanup()
        manager.fire("on_error")
        self.assertEqual(received, [1])

    def test_cleanup_removes_tools(self):
        from houdini_ai_agent.core.hooks import get_hook_manager
        from houdini_ai_agent.core.hooks.plugin_context import PluginContext
        manager = get_hook_manager()
        ctx = PluginContext("test", manager, {}, Path("/tmp/test.json"))
        ctx.register_tool("cleanup_tool", "Test", {}, lambda args: {})
        self.assertTrue(manager.has_external_tool("cleanup_tool"))
        ctx._cleanup()
        self.assertFalse(manager.has_external_tool("cleanup_tool"))


class TestDecorators(unittest.TestCase):
    """Test @hook, @tool, @ui_button decorators."""

    def setUp(self):
        from houdini_ai_agent.core.hooks.hook_manager import (
            HookManager, _pending_hooks, _pending_tools, _pending_buttons,
        )
        HookManager._instance = None
        HookManager._init_done = False
        _pending_hooks.clear()
        _pending_tools.clear()
        _pending_buttons.clear()

    def test_hook_decorator_collects(self):
        from houdini_ai_agent.core.hooks.hook_manager import hook, _pending_hooks
        @hook("on_tool_after")
        def my_cb(**kw):
            pass
        self.assertEqual(len(_pending_hooks), 1)
        self.assertEqual(_pending_hooks[0][0], "on_tool_after")
        self.assertIs(_pending_hooks[0][1], my_cb)

    def test_tool_decorator_collects(self):
        from houdini_ai_agent.core.hooks.hook_manager import tool, _pending_tools
        @tool(name="test_dec_tool", description="desc")
        def handler(args):
            return {}
        self.assertEqual(len(_pending_tools), 1)
        self.assertEqual(_pending_tools[0]["name"], "test_dec_tool")

    def test_ui_button_decorator_collects(self):
        from houdini_ai_agent.core.hooks.hook_manager import ui_button, _pending_buttons
        @ui_button(icon="📊", tooltip="Stats")
        def on_click():
            pass
        self.assertEqual(len(_pending_buttons), 1)
        self.assertEqual(_pending_buttons[0]["icon"], "📊")


class TestPluginLoaderLogic(unittest.TestCase):
    """Test plugin loading logic (without actual file I/O)."""

    def setUp(self):
        from houdini_ai_agent.core.hooks.hook_manager import HookManager
        HookManager._instance = None
        HookManager._init_done = False

    def test_list_plugins_empty(self):
        from houdini_ai_agent.core.hooks.plugin_loader import list_plugins, _loaded_plugins
        _loaded_plugins.clear()
        plugins = list_plugins()
        self.assertIsInstance(plugins, list)

    def test_get_plugins_dir(self):
        from houdini_ai_agent.core.hooks.plugin_loader import get_plugins_dir
        plugins_dir = get_plugins_dir()
        self.assertIsInstance(plugins_dir, Path)
        self.assertTrue(str(plugins_dir).endswith("plugins"))


class TestActionRunnerPluginDispatch(unittest.TestCase):
    """Test that ActionRunner dispatches plugin tools correctly."""

    def test_plugin_tool_dispatch(self):
        from houdini_ai_agent.core.action_runner import ActionRunner
        from houdini_ai_agent.core.hooks import get_hook_manager

        manager = get_hook_manager()
        manager.register_tool(
            "test_plugin_action",
            "A test plugin tool",
            {"type": "object", "properties": {"name": {"type": "string"}}},
            lambda args: {"success": True, "result": f"Hello {args.get('name', 'world')}"},
        )

        runner = ActionRunner(
            adapter=MagicMock(),
            thinking_level=lambda: "medium",
        )
        result = runner.execute({"action": "test_plugin_action", "name": "test"})
        self.assertTrue(result.get("success"))
        self.assertIn("Hello test", result.get("message", ""))

    def test_unknown_action_not_plugin(self):
        from houdini_ai_agent.core.action_runner import ActionRunner
        from houdini_ai_agent.core.hooks import get_hook_manager

        runner = ActionRunner(
            adapter=MagicMock(),
            thinking_level=lambda: "medium",
        )
        result = runner.execute({"action": "totally_unknown_action"})
        self.assertFalse(result.get("success"))

    def tearDown(self):
        from houdini_ai_agent.core.hooks.hook_manager import HookManager
        HookManager._instance = None
        HookManager._init_done = False


class TestAllEvents(unittest.TestCase):
    """Verify all 7 events are defined."""

    def test_all_events_count(self):
        from houdini_ai_agent.core.hooks.hook_manager import ALL_EVENTS
        self.assertEqual(len(ALL_EVENTS), 7)

    def test_all_events_names(self):
        from houdini_ai_agent.core.hooks.hook_manager import ALL_EVENTS
        expected = {
            "on_message_sent", "on_message_received", "on_tool_before",
            "on_tool_after", "on_plan_created", "on_plan_step_updated", "on_error",
        }
        self.assertEqual(set(ALL_EVENTS), expected)


class TestPluginLoadFromFile(unittest.TestCase):
    """Test loading a plugin from a temporary file."""

    def setUp(self):
        from houdini_ai_agent.core.hooks.hook_manager import HookManager
        HookManager._instance = None
        HookManager._init_done = False
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_load_valid_plugin(self):
        from houdini_ai_agent.core.hooks.hook_manager import (
            HookManager, _pending_hooks, _pending_tools, _pending_buttons,
        )
        _pending_hooks.clear()
        _pending_tools.clear()
        _pending_buttons.clear()

        from houdini_ai_agent.core.hooks.plugin_loader import _load_single_plugin

        # Create a temporary plugin file
        plugin_code = '''
PLUGIN_INFO = {
    "name": "Test Plugin",
    "version": "0.1.0",
    "description": "A test plugin",
}

def register(ctx):
    ctx.log("Test plugin loaded!")
'''
        plugin_file = Path(self.tmpdir) / "test_plugin.py"
        plugin_file.write_text(plugin_code, encoding="utf-8")

        manager = HookManager()
        _load_single_plugin(plugin_file, manager, set(), {})

        # The plugin should be loaded (no tools registered, just a log message)
        from houdini_ai_agent.core.hooks.plugin_loader import _loaded_plugins
        self.assertIn("Test Plugin", _loaded_plugins)
        self.assertTrue(_loaded_plugins["Test Plugin"]["enabled"])


class TestFireHookInSession(unittest.TestCase):
    """Test that _fire_hook method exists and is callable."""

    def test_fire_hook_method(self):
        # Just verify the method pattern exists in session.py
        from houdini_ai_agent.core.session import AgentSession
        # We can't fully instantiate AgentSession without Houdini, but we can
        # verify the method is defined
        self.assertTrue(hasattr(AgentSession, "_fire_hook"))
        import inspect
        sig = inspect.signature(AgentSession._fire_hook)
        self.assertIn("event", sig.parameters)


if __name__ == "__main__":
    unittest.main()
