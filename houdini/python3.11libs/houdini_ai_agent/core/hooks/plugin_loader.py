"""PluginLoader — discovers, loads, and manages plugin lifecycle.

Plugins are Python files placed in the ``plugins/`` directory next to the
package.  Each plugin must define::

    PLUGIN_INFO = {
        "name": "My Plugin",
        "version": "1.0.0",
        "description": "What it does",
        "settings": [
            {"key": "option_name", "type": "bool", "label": "...", "default": True},
        ],
    }

    def register(ctx):
        ctx.log("Loaded!")
"""

from __future__ import annotations

import importlib.util
import json
import traceback
from pathlib import Path
from typing import Any, Dict, List, Optional

from houdini_ai_agent.core.config import APP_CONFIG_DIR
from houdini_ai_agent.core.hooks.hook_manager import (
    HookManager,
    get_hook_manager,
    _pending_hooks,
    _pending_tools,
    _pending_buttons,
)
from houdini_ai_agent.core.hooks.plugin_context import PluginContext

# ---------------------------------------------------------------------------
# Paths and state
# ---------------------------------------------------------------------------

_PACKAGE_DIR = Path(__file__).resolve().parent.parent  # houdini_ai_agent/
_PLUGINS_DIR = _PACKAGE_DIR.parent.parent / "plugins"
_CONFIG_PATH = APP_CONFIG_DIR / "plugins.json"

# Loaded plugin records: plugin_name -> {"module", "info", "ctx", "enabled", "file"}
_loaded_plugins: Dict[str, Dict[str, Any]] = {}
_loaded_once = False


# ---------------------------------------------------------------------------
# Config helpers
# ---------------------------------------------------------------------------

def _load_config() -> Dict[str, Any]:
    if _CONFIG_PATH.exists():
        try:
            with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def _save_config(config: Dict[str, Any]) -> None:
    _CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(_CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------

def load_all_plugins() -> None:
    """Scan the plugins/ directory and load all enabled plugins."""
    global _loaded_once
    if _loaded_once:
        return
    _loaded_once = True

    plugins_dir = get_plugins_dir()
    if not plugins_dir.exists():
        plugins_dir.mkdir(parents=True, exist_ok=True)

    config = _load_config()
    disabled = set(config.get("disabled", []))

    plugin_files = sorted(
        f for f in plugins_dir.glob("*.py")
        if not f.name.startswith("_")
    )

    manager = get_hook_manager()
    for filepath in plugin_files:
        try:
            _load_single_plugin(filepath, manager, disabled, config)
        except Exception:
            print(f"[PluginLoader] Error loading {filepath.name}:")
            traceback.print_exc()

    # Apply disabled_tools list to registry
    disabled_tools = config.get("disabled_tools", [])
    if disabled_tools:
        try:
            from houdini_ai_agent.core.tool_registry import get_default_tool_registry
            registry = get_default_tool_registry()
            for tool_name in disabled_tools:
                registry.set_enabled(tool_name, False)
        except Exception:
            pass


def _load_single_plugin(
    filepath: Path,
    manager: HookManager,
    disabled: set,
    config: Dict[str, Any],
) -> None:
    """Load a single plugin file."""
    # Clear global decorator collectors (prevent cross-plugin contamination)
    _pending_hooks.clear()
    _pending_tools.clear()
    _pending_buttons.clear()

    module_name = f"_plugin_{filepath.stem}"
    spec = importlib.util.spec_from_file_location(module_name, str(filepath))
    if spec is None or spec.loader is None:
        return
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    # Validate required attributes
    plugin_info = getattr(module, "PLUGIN_INFO", None)
    if not isinstance(plugin_info, dict):
        return
    register_fn = getattr(module, "register", None)
    if not callable(register_fn):
        return

    plugin_name = str(plugin_info.get("name") or filepath.stem)
    is_disabled = plugin_name in disabled

    # Load saved settings with defaults from schema
    saved_settings = config.get("settings", {}).get(plugin_name, {})
    settings = dict(saved_settings)
    for setting_def in plugin_info.get("settings", []):
        key = setting_def.get("key", "")
        if key and key not in settings:
            settings[key] = setting_def.get("default")

    ctx = PluginContext(
        plugin_name=plugin_name,
        manager=manager,
        settings=settings,
        config_path=_CONFIG_PATH,
    )

    _loaded_plugins[plugin_name] = {
        "module": module,
        "info": plugin_info,
        "ctx": ctx,
        "enabled": not is_disabled,
        "file": filepath,
    }

    if not is_disabled:
        try:
            register_fn(ctx)
            _apply_decorators(ctx, manager)
        except Exception:
            print(f"[PluginLoader] Error in register() for {plugin_name}:")
            traceback.print_exc()


def _apply_decorators(ctx: PluginContext, manager: HookManager) -> None:
    """Apply pending decorator-registered hooks, tools, and buttons."""
    for event, callback, priority in _pending_hooks:
        ctx.on(event, callback, priority)

    for tool_info in _pending_tools:
        ctx.register_tool(
            name=tool_info["name"],
            description=tool_info.get("description", ""),
            schema=tool_info.get("parameters", {"type": "object", "properties": {}}),
            handler=tool_info["handler"],
            modes=tool_info.get("modes"),
        )

    for button_info in _pending_buttons:
        ctx.register_button(
            icon=button_info.get("icon", "🔌"),
            tooltip=button_info.get("tooltip", ""),
            callback=button_info["callback"],
        )

    _pending_hooks.clear()
    _pending_tools.clear()
    _pending_buttons.clear()


# ---------------------------------------------------------------------------
# Lifecycle management
# ---------------------------------------------------------------------------

def reload_plugin(name: str) -> bool:
    """Reload a single plugin by name. Returns True on success."""
    plugin_data = _loaded_plugins.get(name)
    if not plugin_data:
        return False

    # Cleanup old registrations
    ctx = plugin_data["ctx"]
    ctx._cleanup()

    manager = get_hook_manager()
    config = _load_config()
    disabled = set(config.get("disabled", []))

    try:
        _load_single_plugin(plugin_data["file"], manager, disabled, config)
        print(f"[PluginLoader] Reloaded plugin: {name}")
        return True
    except Exception:
        print(f"[PluginLoader] Error reloading {name}:")
        traceback.print_exc()
        return False


def enable_plugin(name: str) -> bool:
    """Enable a disabled plugin. Returns True on success."""
    plugin_data = _loaded_plugins.get(name)
    if not plugin_data:
        return False
    config = _load_config()
    disabled = list(config.get("disabled", []))
    if name in disabled:
        disabled.remove(name)
        config["disabled"] = disabled
        _save_config(config)
    plugin_data["enabled"] = True
    return reload_plugin(name)


def disable_plugin(name: str) -> bool:
    """Disable an enabled plugin. Returns True on success."""
    plugin_data = _loaded_plugins.get(name)
    if not plugin_data:
        return False
    # Cleanup
    plugin_data["ctx"]._cleanup()
    plugin_data["enabled"] = False
    # Persist
    config = _load_config()
    disabled = list(config.get("disabled", []))
    if name not in disabled:
        disabled.append(name)
        config["disabled"] = disabled
        _save_config(config)
    # Remount buttons
    bridge = get_hook_manager().get_ui_bridge()
    if bridge:
        bridge.mount_buttons()
    print(f"[PluginLoader] Disabled plugin: {name}")
    return True


def reload_all_plugins() -> None:
    """Cleanup and reload all plugins."""
    global _loaded_once
    # Cleanup all
    for plugin_data in _loaded_plugins.values():
        plugin_data["ctx"]._cleanup()
    _loaded_plugins.clear()
    _loaded_once = False
    load_all_plugins()
    bridge = get_hook_manager().get_ui_bridge()
    if bridge:
        bridge.mount_buttons()


def list_plugins() -> List[Dict[str, Any]]:
    """Return metadata for all discovered plugins."""
    if not _loaded_once:
        load_all_plugins()
    result = []
    for name, data in _loaded_plugins.items():
        info = data.get("info", {})
        result.append({
            "name": name,
            "version": info.get("version", ""),
            "description": info.get("description", ""),
            "author": info.get("author", ""),
            "enabled": data.get("enabled", True),
            "file": str(data.get("file", "")),
        })
    return result


def get_plugins_dir() -> Path:
    """Return the plugins directory path, creating it if needed."""
    if not _PLUGINS_DIR.exists():
        _PLUGINS_DIR.mkdir(parents=True, exist_ok=True)
    return _PLUGINS_DIR


# ---------------------------------------------------------------------------
# Settings helpers
# ---------------------------------------------------------------------------

def get_plugin_setting(plugin_name: str, key: str, default: Any = None) -> Any:
    """Get a setting value for a plugin."""
    plugin_data = _loaded_plugins.get(plugin_name)
    if plugin_data and plugin_data.get("ctx"):
        return plugin_data["ctx"].get_setting(key, default)
    config = _load_config()
    return config.get("settings", {}).get(plugin_name, {}).get(key, default)


def set_plugin_setting(plugin_name: str, key: str, value: Any) -> None:
    """Set a setting value for a plugin and persist."""
    plugin_data = _loaded_plugins.get(plugin_name)
    if plugin_data and plugin_data.get("ctx"):
        plugin_data["ctx"].set_setting(key, value)
