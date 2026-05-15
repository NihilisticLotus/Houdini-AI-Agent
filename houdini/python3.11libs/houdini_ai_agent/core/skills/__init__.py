# -*- coding: utf-8 -*-
"""Skill loader and registry for Houdini AI Agent.

Provides a plugin-style skill system where each ``.py`` file in this
directory (and an optional user directory) defines ``SKILL_INFO`` and
``run(adapter, **kwargs)``. Skills are lazily loaded on first access,
automatically converted to OpenAI Function Calling schema, and registered
to the ToolRegistry as ``skill:xxx`` tools.

Design principles (adapted from Houdini-Agent reference project):
- Convention over configuration: SKILL_INFO + run()
- Lazy loading with importlib
- Adapter-aware: run() receives adapter, not raw hou
- Dual registration: internal _registry + ToolRegistry for FC
- User custom skill directory via config INI
"""

from __future__ import annotations

import importlib.util
import logging
import os
import types
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Internal registry
# ---------------------------------------------------------------------------

_registry: Dict[str, types.ModuleType] = {}
_loaded: bool = False
_adapter: Any = None  # cached adapter for execution

# ---------------------------------------------------------------------------
# Schema conversion
# ---------------------------------------------------------------------------

_TYPE_MAP = {
    "string": "string",
    "str": "string",
    "float": "number",
    "double": "number",
    "int": "integer",
    "integer": "integer",
    "bool": "boolean",
    "boolean": "boolean",
    "list": "array",
    "array": "array",
}


def _skill_info_to_openai_schema(info: Dict[str, Any]) -> Dict[str, Any]:
    """Convert a SKILL_INFO dict to OpenAI Function Calling parameter schema."""
    properties: Dict[str, Any] = {}
    required: List[str] = []

    for pname, pdef in info.get("parameters", {}).items():
        ptype = _TYPE_MAP.get(str(pdef.get("type", "string")).lower(), "string")
        prop: Dict[str, Any] = {
            "type": ptype,
            "description": pdef.get("description", f"{pname} parameter"),
        }
        if "enum" in pdef:
            prop["enum"] = pdef["enum"]
        if "default" in pdef:
            prop["default"] = pdef["default"]
        properties[pname] = prop
        if pdef.get("required", False):
            required.append(pname)

    return {
        "type": "object",
        "properties": properties,
        "required": required,
    }


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------

def _load_skills_from_dir(directory: Path) -> None:
    """Scan a directory for skill .py files and load them."""
    if not directory.is_dir():
        return
    for py_file in sorted(directory.glob("*.py")):
        if py_file.name.startswith("_"):
            continue
        try:
            module_name = f"houdini_ai_agent.core.skills.{py_file.stem}"
            spec = importlib.util.spec_from_file_location(module_name, str(py_file))
            if spec is None or spec.loader is None:
                continue
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            if not hasattr(module, "SKILL_INFO") or not hasattr(module, "run"):
                logger.debug("Skipping %s: missing SKILL_INFO or run()", py_file.name)
                continue
            if not callable(getattr(module, "run")):
                logger.debug("Skipping %s: run() is not callable", py_file.name)
                continue

            skill_name = module.SKILL_INFO.get("name", py_file.stem)
            _registry[skill_name] = module
            logger.debug("Loaded skill: %s from %s", skill_name, py_file.name)
        except Exception as exc:
            logger.warning("Failed to load skill %s: %s", py_file.name, exc)


def _get_user_skill_dir() -> Optional[Path]:
    """Read user skill directory from config INI if available."""
    try:
        import configparser
        from houdini_ai_agent.core.config import APP_CONFIG_DIR
        ini_path = APP_CONFIG_DIR / "houdini_ai.ini"
        if not ini_path.exists():
            return None
        config = configparser.ConfigParser()
        config.read(str(ini_path))
        user_dir = config.get("skills", "user_skill_dir", fallback="")
        if user_dir and Path(user_dir).is_dir():
            return Path(user_dir)
    except Exception:
        pass
    return None


def _load_all() -> None:
    """Load all skills from built-in directory and optional user directory."""
    global _loaded
    if _loaded:
        return

    # Built-in skills directory
    builtin_dir = Path(__file__).parent
    _load_skills_from_dir(builtin_dir)

    # User custom skills directory
    user_dir = _get_user_skill_dir()
    if user_dir is not None:
        _load_skills_from_dir(user_dir)

    _loaded = True
    logger.info("Loaded %d skill(s)", len(_registry))


# ---------------------------------------------------------------------------
# ToolRegistry integration
# ---------------------------------------------------------------------------

def _register_skills_to_registry() -> None:
    """Register all loaded skills to the ToolRegistry."""
    from houdini_ai_agent.core.tool_registry import (
        TAG_GEOMETRY,
        TAG_READONLY,
        TAG_SKILL,
        THREAD_HOUDINI_MAIN,
        TOOL_MODES_SKILL,
        ToolMeta,
        get_default_tool_registry,
    )

    registry = get_default_tool_registry()

    for skill_name, module in _registry.items():
        info = module.SKILL_INFO
        tool_name = f"skill:{skill_name}"
        json_schema = _skill_info_to_openai_schema(info)
        description = f"[Skill] {info.get('description', '')}"

        # Build a handler closure that captures skill_name properly
        def _make_handler(sn: str) -> Callable:
            def handler(**kwargs):
                return run_skill(sn, kwargs)
            return handler

        tool = ToolMeta(
            name=tool_name,
            label=info.get("label", skill_name),
            description=description,
            schema={"action": tool_name},
            json_schema=json_schema,
            adapter_method="",  # skills use their own run()
            tags=(TAG_READONLY, TAG_GEOMETRY, TAG_SKILL),
            modes=TOOL_MODES_SKILL,
            thread_safety=THREAD_HOUDINI_MAIN,
            source="skill",
        )
        # Store handler reference on the tool for action_runner to use
        tool._skill_handler = _make_handler(skill_name)
        tool._skill_name = skill_name
        registry.register(tool)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def list_skills() -> List[Dict[str, Any]]:
    """Return metadata for all loaded skills."""
    _load_all()
    result = []
    for name, module in _registry.items():
        info = dict(module.SKILL_INFO)
        info["name"] = name
        result.append(info)
    return result


def run_skill(skill_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """Execute a skill by name with the given parameters."""
    _load_all()
    module = _registry.get(skill_name)
    if module is None:
        return {"error": f"Skill not found: {skill_name}"}
    try:
        result = module.run(adapter=_adapter, **params)
        if not isinstance(result, dict):
            return {"result": result}
        return result
    except Exception as exc:
        logger.error("Skill %s execution failed: %s", skill_name, exc)
        return {"error": f"Skill execution failed: {exc}"}


def set_adapter(adapter: Any) -> None:
    """Set the adapter instance for skill execution."""
    global _adapter
    _adapter = adapter


def reload_skills() -> None:
    """Clear and reload all skills (useful for development)."""
    global _loaded, _registry
    _loaded = False
    _registry = {}
    _load_all()
    _register_skills_to_registry()


def initialize(adapter: Any = None) -> None:
    """Initialize the skill system: set adapter, load all, register to ToolRegistry."""
    if adapter is not None:
        set_adapter(adapter)
    _load_all()
    _register_skills_to_registry()


def get_skill_info(skill_name: str) -> Optional[Dict[str, Any]]:
    """Get SKILL_INFO for a specific skill."""
    _load_all()
    module = _registry.get(skill_name)
    if module is None:
        return None
    return module.SKILL_INFO
