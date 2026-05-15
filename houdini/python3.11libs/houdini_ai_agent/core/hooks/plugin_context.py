"""PluginContext — API proxy passed to each plugin's register(ctx) function.

Each plugin receives a PluginContext instance that provides controlled access
to hook registration, tool registration, settings persistence, and UI insertion.
"""

from __future__ import annotations

import json
import traceback
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from houdini_ai_agent.core.config import APP_CONFIG_DIR
from houdini_ai_agent.core.hooks.hook_manager import HookManager


class PluginContext:
    """API entry point for each plugin.

    Provides methods to register hooks, tools, and UI buttons, as well as
    read/write per-plugin settings that persist to ``~/.houdini_ai_agent/plugins.json``.
    """

    def __init__(
        self,
        plugin_name: str,
        manager: HookManager,
        settings: Dict[str, Any],
        config_path: Path,
    ) -> None:
        self._plugin_name = plugin_name
        self._manager = manager
        self._settings = settings
        self._config_path = config_path
        # Track registered hooks for cleanup
        self._registered_hooks: List[Tuple[str, Callable]] = []
        # Track registered tool names for cleanup
        self._registered_tools: List[str] = []

    @property
    def plugin_name(self) -> str:
        """The name of this plugin (from PLUGIN_INFO)."""
        return self._plugin_name

    # -- Hook registration --------------------------------------------------

    def on(self, event: str, callback: Callable, priority: int = 0) -> None:
        """Register an event hook. Tracked for automatic cleanup."""
        self._manager.register(event, callback, priority)
        self._registered_hooks.append((event, callback))

    # -- Tool registration --------------------------------------------------

    def register_tool(
        self,
        name: str,
        description: str,
        schema: Dict[str, Any],
        handler: Callable,
        modes: Optional[Tuple[str, ...]] = None,
    ) -> None:
        """Register an external tool the AI model can call.

        Args:
            name:        Unique tool name (will be prefixed with plugin context).
            description: What the tool does.
            schema:      JSON Schema for parameters.
            handler:     Callable that receives a dict of args and returns a result dict.
            modes:       Tuple of work modes where this tool is available.
        """
        self._manager.register_tool(name, description, schema, handler,
                                     plugin_name=self._plugin_name, modes=modes)
        self._registered_tools.append(name)

    # -- UI registration ----------------------------------------------------

    def register_button(self, icon: str, tooltip: str, callback: Callable) -> None:
        """Register a toolbar button for this plugin."""
        self._manager.register_button(self._plugin_name, icon, tooltip, callback)

    def insert_chat_card(self, widget) -> None:
        """Insert a custom QWidget into the chat area (thread-safe)."""
        bridge = self._manager.get_ui_bridge()
        if bridge:
            bridge.insert_chat_card(widget)

    # -- Settings -----------------------------------------------------------

    def get_setting(self, key: str, default: Any = None) -> Any:
        """Read a plugin setting (persisted in plugins.json)."""
        return self._settings.get(key, default)

    def set_setting(self, key: str, value: Any) -> None:
        """Write a plugin setting and persist to disk."""
        self._settings[key] = value
        self._persist_settings()

    def _persist_settings(self) -> None:
        """Save current settings to the plugins config file."""
        try:
            config = _load_plugins_config()
            settings_map = config.setdefault("settings", {})
            settings_map[self._plugin_name] = dict(self._settings)
            _save_plugins_config(config)
        except Exception:
            self.log(f"Failed to persist settings: {traceback.format_exc()}")

    # -- Logging ------------------------------------------------------------

    def log(self, msg: str) -> None:
        """Print a prefixed log message."""
        print(f"[Plugin:{self._plugin_name}] {msg}")

    # -- Cleanup ------------------------------------------------------------

    def _cleanup(self) -> None:
        """Unregister all hooks, tools, and buttons for this plugin."""
        for event, callback in self._registered_hooks:
            self._manager.unregister(event, callback)
        self._registered_hooks.clear()

        for tool_name in self._registered_tools:
            self._manager.unregister_tool(tool_name)
        self._registered_tools.clear()

        self._manager.unregister_all_for_plugin(self._plugin_name)


# ---------------------------------------------------------------------------
# Config helpers (shared with plugin_loader)
# ---------------------------------------------------------------------------

_plugins_config_path = APP_CONFIG_DIR / "plugins.json"


def _load_plugins_config() -> Dict[str, Any]:
    """Load the plugins configuration file."""
    if _plugins_config_path.exists():
        try:
            with open(_plugins_config_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def _save_plugins_config(config: Dict[str, Any]) -> None:
    """Save the plugins configuration file."""
    _plugins_config_path.parent.mkdir(parents=True, exist_ok=True)
    with open(_plugins_config_path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)
