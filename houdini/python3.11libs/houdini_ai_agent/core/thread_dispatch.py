"""Thread-safe dispatch for Houdini tool operations.

Houdini's `hou` module is NOT thread-safe — all HOM operations must run on
the Qt main thread (especially critical on macOS where Cocoa enforces this).

This module provides:

1. **ThreadDispatcher**: Routes tool execution to the correct thread
   - HOM tools → Qt main thread via BlockingQueuedConnection
   - Background-safe tools → direct execution in worker thread
   - No-Qt fallback → direct execution (for tests / CLI usage)

2. **Timeout protection**: Prevents deadlocks from slow cook operations
3. **Main-thread busy guard**: Stops signal pile-up after timeout

Design principles (first principles):
- Minimal API surface: one class, one public method
- Graceful degradation: works without Qt (tests, CLI)
- Zero overhead when already on main thread
- Composable with AgentLoop + ActionRunner
"""

from __future__ import annotations

import queue
import threading
import traceback
from typing import Any, Callable, Dict, Optional

from houdini_ai_agent.core.tool_registry import (
    THREAD_BACKGROUND,
    THREAD_EXTERNAL,
    THREAD_HOUDINI_MAIN,
    ToolRegistry,
)

# ---------------------------------------------------------------------------
# Qt import (optional)
# ---------------------------------------------------------------------------

try:
    from PySide6 import QtCore
    _PYSIDE_VERSION = 6
except ImportError:
    try:
        from PySide2 import QtCore
        _PYSIDE_VERSION = 2
    except ImportError:
        _PYSIDE_VERSION = 0

# Fallback when no Qt is available
if _PYSIDE_VERSION == 0:
    QtCore = None  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Default timeout for main-thread tool execution (seconds)
DEFAULT_TOOL_TIMEOUT = 120.0

# Shorter timeout for batch read-only operations
BATCH_READ_TIMEOUT = 60.0


# ---------------------------------------------------------------------------
# ThreadDispatcher
# ---------------------------------------------------------------------------

class ThreadDispatcher:
    """Routes tool calls to the appropriate thread based on thread_safety.

    Usage with AgentLoop::

        dispatcher = ThreadDispatcher(registry, executor)
        loop = AgentLoop(
            tool_registry=registry,
            tool_executor=dispatcher.dispatch,
        )
    """

    def __init__(
        self,
        registry: ToolRegistry,
        tool_executor: Callable[[str, Dict[str, Any]], Dict[str, Any]],
        timeout: float = DEFAULT_TOOL_TIMEOUT,
    ):
        """
        Args:
            registry: ToolRegistry for looking up thread_safety metadata.
            tool_executor: The actual executor (e.g., ActionRunner.run).
            timeout: Max seconds to wait for main-thread execution.
        """
        self._registry = registry
        self._executor = tool_executor
        self._timeout = timeout

        # Thread-safe result passing
        self._result_queue: queue.Queue = queue.Queue()
        self._lock = threading.Lock()

        # Main-thread busy guard (prevents deadlock after timeout)
        self._main_thread_busy = False

        # Qt signal bridge (created lazily when first needed)
        self._bridge: Optional[_MainBridge] = None

    @property
    def is_main_thread_busy(self) -> bool:
        """Whether the main thread is blocked by a previous timeout."""
        return self._main_thread_busy

    def reset_busy_flag(self) -> None:
        """Clear the main-thread busy flag (call on agent done/error/stop)."""
        self._main_thread_busy = False

    def dispatch(
        self,
        tool_name: str,
        tool_args: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Route a tool call to the appropriate thread.

        This is the primary entry point used as `tool_executor` for AgentLoop.

        Args:
            tool_name: Name of the tool to execute.
            tool_args: Arguments dict for the tool.

        Returns:
            Result dict with at least 'success' and 'message'/'error'.
        """
        meta = self._registry.get(tool_name)

        # If tool doesn't need main thread, execute directly
        if meta is None or not meta.needs_main_thread:
            return self._execute_direct(tool_name, tool_args)

        # If we're already on the main thread, execute directly
        if self._is_main_thread():
            return self._execute_direct(tool_name, tool_args)

        # Main-thread busy guard: prevent signal pile-up after timeout
        if self._main_thread_busy:
            return {
                "success": False,
                "error": (
                    "主线程正忙（可能正在进行耗时计算），请等待完成后重试。"
                    "建议：按停止按钮中断当前操作。"
                ),
            }

        # Dispatch to main thread via Qt signal
        return self._execute_on_main_thread(tool_name, tool_args)

    # ------------------------------------------------------------------
    # Internal: direct execution (background or main thread)
    # ------------------------------------------------------------------

    def _execute_direct(
        self,
        tool_name: str,
        tool_args: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Execute tool directly in the current thread."""
        try:
            return self._executor(tool_name, tool_args)
        except Exception as exc:
            return {
                "success": False,
                "error": f"Tool execution error: {exc}\n{traceback.format_exc()[:300]}",
            }

    # ------------------------------------------------------------------
    # Internal: main-thread dispatch via Qt
    # ------------------------------------------------------------------

    def _execute_on_main_thread(
        self,
        tool_name: str,
        tool_args: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Dispatch tool execution to the Qt main thread.

        Uses BlockingQueuedConnection to:
        1. Block the worker thread until the main thread finishes
        2. Ensure hou operations run on the main thread
        3. Pass results back via thread-safe queue
        """
        bridge = self._ensure_bridge()
        if bridge is None:
            # No Qt available — execute directly (test/CLI mode)
            return self._execute_direct(tool_name, tool_args)

        with self._lock:
            # Drain stale results from previous calls
            while not self._result_queue.empty():
                try:
                    self._result_queue.get_nowait()
                except queue.Empty:
                    break

            # Emit signal → main thread slot (blocks until slot returns)
            bridge.request_execution(tool_name, tool_args)

            # Wait for result with timeout
            try:
                result = self._result_queue.get(timeout=self._timeout)
                self._main_thread_busy = False
                return result
            except queue.Empty:
                self._main_thread_busy = True
                return {
                    "success": False,
                    "error": (
                        f"操作超时（{int(self._timeout)}秒）："
                        f"Houdini 主线程可能正在进行耗时计算（如 cook/渲染）。"
                        f"操作 {tool_name} 仍在后台执行中。"
                    ),
                }

    def _on_main_thread_execute(
        self,
        tool_name: str,
        tool_args: Dict[str, Any],
    ) -> None:
        """Slot: executes on main thread, puts result in queue."""
        try:
            result = self._executor(tool_name, tool_args)
        except Exception as exc:
            result = {
                "success": False,
                "error": f"Tool execution error: {exc}\n{traceback.format_exc()[:300]}",
            }
        self._result_queue.put(result)

    def _ensure_bridge(self) -> Optional[_MainBridge]:
        """Lazily create the Qt signal bridge."""
        if self._bridge is not None:
            return self._bridge

        if QtCore is None:
            return None

        # Check if QApplication exists (we're inside Houdini)
        app = None
        try:
            app = QtCore.QCoreApplication.instance()
        except Exception:
            pass

        if app is None:
            return None

        self._bridge = _MainBridge(self._on_main_thread_execute)
        return self._bridge

    @staticmethod
    def _is_main_thread() -> bool:
        """Check if we're currently on the main/application thread."""
        if QtCore is None:
            return threading.current_thread() is threading.main_thread()

        try:
            app = QtCore.QCoreApplication.instance()
            if app is not None:
                return app.thread() == QtCore.QThread.currentThread()
        except Exception:
            pass

        # No QApplication → fall back to threading check
        return threading.current_thread() is threading.main_thread()


# ---------------------------------------------------------------------------
# Qt Signal Bridge
# ---------------------------------------------------------------------------

if _PYSIDE_VERSION > 0 and QtCore is not None:
    class _MainBridge(QtCore.QObject):
        """Qt signal bridge for dispatching tool execution to main thread.

        Uses BlockingQueuedConnection so the emitting (worker) thread blocks
        until the slot finishes on the main thread.
        """
        _executeRequest = QtCore.Signal(str, dict)

        def __init__(self, slot: Callable[[str, Dict[str, Any]], None], parent=None):
            super().__init__(parent)
            self._executeRequest.connect(
                slot,
                QtCore.Qt.BlockingQueuedConnection,
            )

        def request_execution(self, tool_name: str, tool_args: Dict[str, Any]) -> None:
            """Emit signal to request execution on main thread.

            This blocks the calling thread until the slot returns.
            """
            self._executeRequest.emit(tool_name, tool_args)
else:
    class _MainBridge:  # type: ignore[no-redef]
        """No-op fallback when Qt is not available."""

        def __init__(self, slot=None, parent=None):
            pass

        def request_execution(self, tool_name: str, tool_args: Dict[str, Any]) -> None:
            pass
