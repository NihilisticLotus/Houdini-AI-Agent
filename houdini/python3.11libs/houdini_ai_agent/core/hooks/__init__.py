"""Plugin hook system for extending the Houdini AI Agent.

Exports:
    HookManager      — singleton that manages hook registration and dispatch
    PluginContext     — API proxy passed to each plugin's register() function
    PluginUIBridge   — bridges plugin widgets into the Qt UI layer
    get_hook_manager — convenience accessor for the HookManager singleton
    load_all_plugins — scan and load all plugins from the plugins/ directory
    hook / tool / ui_button — decorator API for declarative registration
"""

from houdini_ai_agent.core.hooks.hook_manager import (
    ALL_EVENTS,
    HookManager,
    PluginUIBridge,
    get_hook_manager,
    hook,
    tool,
    ui_button,
)
from houdini_ai_agent.core.hooks.plugin_context import PluginContext
from houdini_ai_agent.core.hooks.plugin_loader import (
    disable_plugin,
    enable_plugin,
    get_plugins_dir,
    list_plugins,
    load_all_plugins,
    reload_all_plugins,
    reload_plugin,
)

__all__ = [
    "ALL_EVENTS",
    "HookManager",
    "PluginUIBridge",
    "PluginContext",
    "get_hook_manager",
    "hook",
    "tool",
    "ui_button",
    "load_all_plugins",
    "reload_plugin",
    "reload_all_plugins",
    "enable_plugin",
    "disable_plugin",
    "list_plugins",
    "get_plugins_dir",
]
