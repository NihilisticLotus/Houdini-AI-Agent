"""HookManager — singleton core for event registration, dispatch, and external tools.

Design adapted from the reference project (KazamaSuichiku/Houdini-Agent v1.5.5),
following our project's conventions:
  - APP_CONFIG_DIR for config storage
  - ToolMeta/ToolRegistry for tool registration
  - ToolResult for structured results
  - thread-safe operations with threading.Lock
"""

from __future__ import annotations

import json
import threading
import traceback
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from houdini_ai_agent.core.config import APP_CONFIG_DIR

# ---------------------------------------------------------------------------
# Hook event definitions
# ---------------------------------------------------------------------------

EVENT_ON_MESSAGE_SENT = "on_message_sent"
EVENT_ON_MESSAGE_RECEIVED = "on_message_received"
EVENT_ON_TOOL_BEFORE = "on_tool_before"
EVENT_ON_TOOL_AFTER = "on_tool_after"
EVENT_ON_PLAN_CREATED = "on_plan_created"
EVENT_ON_PLAN_STEP_UPDATED = "on_plan_step_updated"
EVENT_ON_ERROR = "on_error"

ALL_EVENTS: Tuple[str, ...] = (
    EVENT_ON_MESSAGE_SENT,
    EVENT_ON_MESSAGE_RECEIVED,
    EVENT_ON_TOOL_BEFORE,
    EVENT_ON_TOOL_AFTER,
    EVENT_ON_PLAN_CREATED,
    EVENT_ON_PLAN_STEP_UPDATED,
    EVENT_ON_ERROR,
)

# ---------------------------------------------------------------------------
# Pending decorator collectors (cleared per-plugin during loading)
# ---------------------------------------------------------------------------

_pending_hooks: List[Tuple[str, Callable, int]] = []
_pending_tools: List[Dict[str, Any]] = []
_pending_buttons: List[Dict[str, Any]] = []

_config_lock = threading.Lock()
_plugins_config_path = APP_CONFIG_DIR / "plugins.json"


# ---------------------------------------------------------------------------
# HookManager
# ---------------------------------------------------------------------------

class HookManager:
    """Singleton managing hook registration, event dispatch, external tools, and UI buttons.

    Two dispatch modes:
      - ``fire(event, **kwargs)``        — notify all callbacks; exceptions are caught.
      - ``fire_filter(event, value, **kw)`` — pipeline: each callback may transform *value*.
    """

    _instance: Optional[HookManager] = None
    _init_done: bool = False

    def __new__(cls) -> HookManager:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        if self._init_done:
            return
        self._init_done = True
        # event_name -> [(priority, callback), ...] sorted by priority ascending
        self._hooks: Dict[str, List[Tuple[int, Callable]]] = {e: [] for e in ALL_EVENTS}
        # External tools: tool_name -> {"schema": dict, "handler": callable, "plugin": str}
        self._external_tools: Dict[str, Dict[str, Any]] = {}
        # UI buttons: [(plugin_name, icon, tooltip, callback), ...]
        self._ui_buttons: List[Tuple[str, str, str, Callable]] = []
        # UI bridge reference (set by the panel at init time)
        self._ui_bridge: Optional[PluginUIBridge] = None
        self._lock = threading.Lock()

    # -- Hook registration --------------------------------------------------

    def register(self, event: str, callback: Callable, priority: int = 0) -> None:
        """Register *callback* for *event* with given *priority* (lower runs first)."""
        with self._lock:
            hooks = self._hooks.setdefault(event, [])
            hooks.append((priority, callback))
            hooks.sort(key=lambda pair: pair[0])

    def unregister(self, event: str, callback: Callable) -> None:
        """Remove a specific callback from an event."""
        with self._lock:
            hooks = self._hooks.get(event, [])
            self._hooks[event] = [(p, cb) for p, cb in hooks if cb is not callback]

    def unregister_all_for_plugin(self, plugin_name: str) -> None:
        """Remove all hooks/tools/buttons registered by a plugin.

        This is called during plugin cleanup (disable/reload).
        """
        # Hook cleanup is tracked by PluginContext._registered_hooks
        # We only clean tools and buttons here by plugin_name
        with self._lock:
            to_remove = [
                name for name, info in self._external_tools.items()
                if info.get("plugin") == plugin_name
            ]
            for name in to_remove:
                del self._external_tools[name]
            self._ui_buttons = [
                btn for btn in self._ui_buttons if btn[0] != plugin_name
            ]

    # -- Event dispatch -----------------------------------------------------

    def fire(self, event: str, **kwargs: Any) -> None:
        """Notify all registered callbacks for *event*. Exceptions are caught."""
        with self._lock:
            hooks = list(self._hooks.get(event, []))
        for _priority, callback in hooks:
            try:
                callback(**kwargs)
            except Exception:
                print(f"[Hook] {event} callback error:")
                traceback.print_exc()

    def fire_filter(self, event: str, value: Any, **kwargs: Any) -> Any:
        """Pipeline dispatch: each callback receives *value* and may return a modified value."""
        with self._lock:
            hooks = list(self._hooks.get(event, []))
        for _priority, callback in hooks:
            try:
                try:
                    result = callback(value, **kwargs)
                except TypeError:
                    result = callback(value)
                if result is not None:
                    value = result
            except Exception:
                print(f"[Hook] {event} filter error:")
                traceback.print_exc()
        return value

    # -- External tool management -------------------------------------------

    def register_tool(
        self,
        name: str,
        description: str,
        schema: Dict[str, Any],
        handler: Callable,
        plugin_name: str = "",
        modes: Optional[Tuple[str, ...]] = None,
    ) -> None:
        """Register an external tool that the AI model can call via Function Calling."""
        with self._lock:
            self._external_tools[name] = {
                "schema": schema,
                "description": description,
                "handler": handler,
                "plugin": plugin_name,
                "modes": modes or ("ask", "agent", "plan_executing"),
            }
            # Sync into the global ToolRegistry while still holding the lock
            self._sync_tool_to_registry(name)

    def unregister_tool(self, name: str) -> None:
        with self._lock:
            self._external_tools.pop(name, None)
        self._remove_tool_from_registry(name)

    def get_external_tools(self) -> List[Dict[str, Any]]:
        """Return a list of OpenAI Function Calling tool schemas for all external tools."""
        with self._lock:
            return [
                {
                    "type": "function",
                    "function": {
                        "name": name,
                        "description": info.get("description", ""),
                        "parameters": info.get("schema", {}),
                    },
                }
                for name, info in self._external_tools.items()
            ]

    def has_external_tool(self, name: str) -> bool:
        with self._lock:
            return name in self._external_tools

    def execute_external_tool(self, name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        """Execute an external tool by name. Returns a dict with success/result."""
        with self._lock:
            info = self._external_tools.get(name)
        if info is None:
            return {"success": False, "error": f"Unknown external tool: {name}"}
        handler = info.get("handler")
        if not callable(handler):
            return {"success": False, "error": f"No handler for tool: {name}"}
        try:
            result = handler(args)
            if not isinstance(result, dict):
                result = {"success": True, "result": str(result)}
            return result
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    # -- UI button management -----------------------------------------------

    def register_button(
        self, plugin_name: str, icon: str, tooltip: str, callback: Callable,
    ) -> None:
        with self._lock:
            self._ui_buttons.append((plugin_name, icon, tooltip, callback))

    def get_buttons(self) -> List[Tuple[str, str, str, Callable]]:
        with self._lock:
            return list(self._ui_buttons)

    # -- UI bridge ----------------------------------------------------------

    def set_ui_bridge(self, bridge: PluginUIBridge) -> None:
        self._ui_bridge = bridge

    def get_ui_bridge(self) -> Optional[PluginUIBridge]:
        return self._ui_bridge

    # -- Internal helpers ---------------------------------------------------

    @staticmethod
    def _sync_tool_to_registry(name: str) -> None:
        """Register an external tool into the global ToolRegistry.

        **Must be called while self._lock is held.**
        """
        try:
            from houdini_ai_agent.core.tool_registry import (
                ToolMeta,
                get_default_tool_registry,
            )
            manager = get_hook_manager()
            # No lock needed — caller holds it
            info = manager._external_tools.get(name)
            if not info:
                return
            modes = info.get("modes", ("ask", "agent", "plan_executing"))
            tool = ToolMeta(
                name=name,
                label=f"[Plugin] {name}",
                description=info.get("description", ""),
                schema=info.get("schema", {}),
                tags=("plugin",),
                modes=frozenset(modes),
                source="plugin",
                adapter_method=f"_plugin_{name}",
            )
            registry = get_default_tool_registry()
            registry.register(tool)
        except Exception:
            pass

    @staticmethod
    def _remove_tool_from_registry(name: str) -> None:
        """Remove an external tool from the global ToolRegistry."""
        try:
            from houdini_ai_agent.core.tool_registry import get_default_tool_registry
            get_default_tool_registry().unregister(name)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# PluginUIBridge — thread-safe bridge between plugins and Qt UI
# ---------------------------------------------------------------------------

class PluginUIBridge:
    """Bridges plugin widgets into the Qt chat panel.

    Set up by the main panel during initialization. Plugins call
    ``insert_chat_card(widget)`` to inject custom QWidgets into the chat area.
    """

    def __init__(self) -> None:
        self._chat_layout = None
        self._button_container = None
        self._insert_card_signal = None
        self._panel_ref = None

    def mount(self, chat_layout, button_container, insert_card_signal, panel_ref) -> None:
        """Called by the panel to supply UI references."""
        self._chat_layout = chat_layout
        self._button_container = button_container
        self._insert_card_signal = insert_card_signal
        self._panel_ref = panel_ref

    def insert_chat_card(self, widget) -> None:
        """Insert a custom QWidget into the chat area (thread-safe via signal)."""
        if self._insert_card_signal is not None:
            self._insert_card_signal.emit(widget)

    def mount_buttons(self) -> None:
        """Remount all plugin buttons into the button container."""
        if self._button_container is None:
            return
        try:
            from houdini_ai_agent.qt import QtWidgets
        except ImportError:
            return
        # Clear existing plugin buttons
        while self._button_container.count():
            item = self._button_container.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        # Add current buttons
        manager = get_hook_manager()
        for plugin_name, icon, tooltip, callback in manager.get_buttons():
            btn = QtWidgets.QPushButton(icon)
            btn.setToolTip(tooltip)
            btn.setObjectName("PluginButton")
            btn.clicked.connect(callback)
            self._button_container.addWidget(btn)


# ---------------------------------------------------------------------------
# Convenience accessor
# ---------------------------------------------------------------------------

def get_hook_manager() -> HookManager:
    """Return the global HookManager singleton."""
    return HookManager()


# ---------------------------------------------------------------------------
# Decorator API
# ---------------------------------------------------------------------------

def hook(event: str, priority: int = 0) -> Callable:
    """Decorator to register a function as an event hook.

    Usage::

        @hook("on_tool_after")
        def my_callback(tool_name, args, result):
            print(f"Tool {tool_name} executed")
    """
    def decorator(func: Callable) -> Callable:
        _pending_hooks.append((event, func, priority))
        return func
    return decorator


def tool(
    name: str,
    description: str = "",
    parameters: Optional[Dict[str, Any]] = None,
    modes: Optional[Tuple[str, ...]] = None,
) -> Callable:
    """Decorator to register a function as an external tool callable by the AI.

    Usage::

        @tool(name="my_tool", description="Does something", parameters={"type": "object", ...})
        def handle_my_tool(args):
            return {"success": True, "result": "done"}
    """
    def decorator(func: Callable) -> Callable:
        _pending_tools.append({
            "name": name,
            "description": description,
            "parameters": parameters or {"type": "object", "properties": {}},
            "handler": func,
            "modes": modes,
        })
        return func
    return decorator


def ui_button(icon: str, tooltip: str = "") -> Callable:
    """Decorator to register a toolbar button.

    Usage::

        @ui_button(icon="📊", tooltip="Stats")
        def on_stats_click():
            print("Stats clicked")
    """
    def decorator(func: Callable) -> Callable:
        _pending_buttons.append({
            "icon": icon,
            "tooltip": tooltip,
            "callback": func,
        })
        return func
    return decorator
