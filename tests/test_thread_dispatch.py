"""Tests for thread_dispatch module."""

from __future__ import annotations

import threading
import time
import unittest
from unittest.mock import MagicMock, patch

from houdini_ai_agent.core.thread_dispatch import (
    DEFAULT_TOOL_TIMEOUT,
    ThreadDispatcher,
    _MainBridge,
)
from houdini_ai_agent.core.tool_registry import (
    THREAD_BACKGROUND,
    THREAD_HOUDINI_MAIN,
    ToolMeta,
    ToolRegistry,
)


def _make_registry() -> ToolRegistry:
    """Create a registry with test tools."""
    reg = ToolRegistry()
    reg.register(ToolMeta(
        name="bg_tool",
        label="BG Tool",
        description="Background-safe tool",
        schema={"type": "object", "properties": {}},
        adapter_method="bg_op",
        thread_safety=THREAD_BACKGROUND,
        tags=("readonly",),
    ))
    reg.register(ToolMeta(
        name="hou_tool",
        label="HOU Tool",
        description="Houdini main-thread tool",
        schema={"type": "object", "properties": {}},
        adapter_method="hou_op",
        thread_safety=THREAD_HOUDINI_MAIN,
        tags=("network",),
    ))
    reg.register(ToolMeta(
        name="unknown_tool",
        label="Unknown Tool",
        description="Another Houdini tool",
        schema={"type": "object", "properties": {}},
        adapter_method="unknown_op",
        thread_safety=THREAD_HOUDINI_MAIN,
        tags=("network",),
    ))
    return reg


class DirectExecutionTests(unittest.TestCase):
    """Tests for direct (non-dispatched) execution."""

    def test_bg_tool_executes_directly(self):
        registry = _make_registry()
        executor = MagicMock(return_value={"success": True, "message": "done"})
        dispatcher = ThreadDispatcher(registry, executor)

        result = dispatcher.dispatch("bg_tool", {"arg": "val"})
        self.assertTrue(result["success"])
        executor.assert_called_once_with("bg_tool", {"arg": "val"})

    def test_executor_exception_returns_error(self):
        registry = _make_registry()
        executor = MagicMock(side_effect=RuntimeError("boom"))
        dispatcher = ThreadDispatcher(registry, executor)

        result = dispatcher.dispatch("bg_tool", {})
        self.assertFalse(result["success"])
        self.assertIn("boom", result["error"])

    def test_unknown_tool_still_dispatches(self):
        """Tools not in registry default to direct execution."""
        registry = _make_registry()
        executor = MagicMock(return_value={"success": True})
        dispatcher = ThreadDispatcher(registry, executor)

        result = dispatcher.dispatch("completely_unknown", {"x": 1})
        self.assertTrue(result["success"])
        executor.assert_called_once_with("completely_unknown", {"x": 1})


class MainThreadDetectionTests(unittest.TestCase):
    """Tests for _is_main_thread detection."""

    def test_main_thread_detected(self):
        self.assertTrue(ThreadDispatcher._is_main_thread())

    def test_bg_thread_detected(self):
        result = [True]

        def check():
            result[0] = ThreadDispatcher._is_main_thread()

        t = threading.Thread(target=check)
        t.start()
        t.join()
        # Without QApplication, falls back to threading.main_thread()
        # In test env, the bg thread should NOT be main
        self.assertFalse(result[0])


class MainThreadBusyGuardTests(unittest.TestCase):
    """Tests for the main-thread busy guard."""

    def test_busy_flag_blocks_hou_tool(self):
        registry = _make_registry()
        executor = MagicMock(return_value={"success": True})
        dispatcher = ThreadDispatcher(registry, executor)

        # Simulate main thread busy
        dispatcher._main_thread_busy = True

        # bg_tool should still work
        result = dispatcher.dispatch("bg_tool", {})
        self.assertTrue(result["success"])

        # hou_tool should be blocked (force is_main_thread to False)
        with patch.object(ThreadDispatcher, '_is_main_thread', return_value=False):
            result = dispatcher.dispatch("hou_tool", {})
            self.assertFalse(result["success"])
            self.assertIn("主线程正忙", result["error"])

    def test_reset_clears_busy_flag(self):
        registry = _make_registry()
        executor = MagicMock(return_value={"success": True})
        dispatcher = ThreadDispatcher(registry, executor)

        dispatcher._main_thread_busy = True
        dispatcher.reset_busy_flag()
        self.assertFalse(dispatcher.is_main_thread_busy)


class NoQtFallbackTests(unittest.TestCase):
    """Tests for behavior when Qt is not available."""

    def test_hou_tool_falls_back_to_direct_when_no_qt(self):
        registry = _make_registry()
        executor = MagicMock(return_value={"success": True, "message": "direct"})
        dispatcher = ThreadDispatcher(registry, executor)

        # Force no bridge (simulating no Qt)
        dispatcher._bridge = None

        with patch.object(ThreadDispatcher, '_is_main_thread', return_value=False):
            with patch.object(dispatcher, '_ensure_bridge', return_value=None):
                result = dispatcher.dispatch("hou_tool", {})
                self.assertTrue(result["success"])
                executor.assert_called_once_with("hou_tool", {})


class MainThreadDispatchTests(unittest.TestCase):
    """Tests for actual main-thread dispatch via mock bridge."""

    def test_dispatch_uses_bridge(self):
        registry = _make_registry()
        executor = MagicMock(return_value={"success": True, "message": "main_result"})
        dispatcher = ThreadDispatcher(registry, executor)

        # Create a mock bridge that simulates the signal/slot flow
        mock_bridge = MagicMock()

        def fake_request(tool_name, tool_args):
            # Simulate: the slot runs on main thread and puts result in queue
            result = executor(tool_name, tool_args)
            dispatcher._result_queue.put(result)

        mock_bridge.request_execution = fake_request
        dispatcher._bridge = mock_bridge

        with patch.object(ThreadDispatcher, '_is_main_thread', return_value=False):
            result = dispatcher.dispatch("hou_tool", {"path": "/obj"})
            self.assertTrue(result["success"])
            self.assertEqual(result["message"], "main_result")

    def test_dispatch_timeout_marks_busy(self):
        registry = _make_registry()
        executor = MagicMock(return_value={"success": True})
        dispatcher = ThreadDispatcher(registry, executor, timeout=0.1)

        # Create a mock bridge that does NOT put result (simulating timeout)
        mock_bridge = MagicMock()
        mock_bridge.request_execution = MagicMock()  # no-op: doesn't put result
        dispatcher._bridge = mock_bridge

        with patch.object(ThreadDispatcher, '_is_main_thread', return_value=False):
            result = dispatcher.dispatch("hou_tool", {})
            self.assertFalse(result["success"])
            self.assertIn("超时", result["error"])
            self.assertTrue(dispatcher.is_main_thread_busy)

    def test_successful_dispatch_clears_busy(self):
        registry = _make_registry()
        executor = MagicMock(return_value={"success": True})
        dispatcher = ThreadDispatcher(registry, executor)
        # Don't set busy flag — verify it stays clear after successful dispatch

        mock_bridge = MagicMock()

        def fake_request(tool_name, tool_args):
            dispatcher._result_queue.put({"success": True})

        mock_bridge.request_execution = fake_request
        dispatcher._bridge = mock_bridge

        with patch.object(ThreadDispatcher, '_is_main_thread', return_value=False):
            result = dispatcher.dispatch("hou_tool", {})
            self.assertTrue(result["success"])
            self.assertFalse(dispatcher.is_main_thread_busy)


class QueueDrainTests(unittest.TestCase):
    """Tests that stale results are drained before dispatch."""

    def test_stale_results_drained(self):
        registry = _make_registry()
        call_count = [0]
        executor = MagicMock()

        def _executor_impl(name, args):
            call_count[0] += 1
            return {"success": True, "message": f"call_{call_count[0]}"}

        executor.side_effect = _executor_impl
        dispatcher = ThreadDispatcher(registry, executor)

        # Put a stale result in the queue (simulating leftover from previous call)
        dispatcher._result_queue.put({"success": True, "message": "stale"})

        mock_bridge = MagicMock()

        def fake_request(tool_name, tool_args):
            result = executor(tool_name, tool_args)
            dispatcher._result_queue.put(result)

        mock_bridge.request_execution = fake_request
        dispatcher._bridge = mock_bridge

        with patch.object(ThreadDispatcher, '_is_main_thread', return_value=False):
            result = dispatcher.dispatch("hou_tool", {})
            # Should get the fresh result (call_1), not the stale one
            self.assertEqual(result["message"], "call_1")


class IntegrationTests(unittest.TestCase):
    """Integration: ThreadDispatcher with real ActionRunner-like executor."""

    def test_mixed_tools_dispatch_correctly(self):
        """Simulate an agent loop calling both bg and hou tools."""
        call_log = []

        def executor(name, args):
            call_log.append(("exec", name, threading.current_thread().name))
            return {"success": True, "message": f"{name} done"}

        registry = _make_registry()
        dispatcher = ThreadDispatcher(registry, executor)

        # bg_tool → direct (on current thread)
        r1 = dispatcher.dispatch("bg_tool", {})
        self.assertTrue(r1["success"])

        # hou_tool on main thread → direct (we're on main thread)
        r2 = dispatcher.dispatch("hou_tool", {"path": "/obj"})
        self.assertTrue(r2["success"])

        # Both should have been executed
        self.assertEqual(len(call_log), 2)

    def test_executor_error_in_main_thread_dispatch(self):
        """Errors from main-thread execution are caught and returned."""
        registry = _make_registry()
        executor = MagicMock(side_effect=ValueError("bad param"))
        dispatcher = ThreadDispatcher(registry, executor)

        mock_bridge = MagicMock()

        def fake_request(tool_name, tool_args):
            try:
                result = executor(tool_name, tool_args)
            except Exception as exc:
                result = {"success": False, "error": str(exc)}
            dispatcher._result_queue.put(result)

        mock_bridge.request_execution = fake_request
        dispatcher._bridge = mock_bridge

        with patch.object(ThreadDispatcher, '_is_main_thread', return_value=False):
            result = dispatcher.dispatch("hou_tool", {})
            self.assertFalse(result["success"])
            self.assertIn("bad param", result["error"])


if __name__ == "__main__":
    unittest.main()
