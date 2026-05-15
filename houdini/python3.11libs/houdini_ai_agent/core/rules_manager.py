"""User rules manager — load, save, and inject custom rules into system prompts.

Supports two rule sources:
  1. UI rules  — created via settings dialog, stored in config/user_rules.json
  2. File rules — user-placed .md/.txt files in rules/ directory

File rules are always enabled and read-only in the UI. UI rules can be
toggled on/off.

Adapted from the reference project's rules_manager following first principles,
using our project's conventions (APP_CONFIG_DIR, etc.).
"""

from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from houdini_ai_agent.core.config import APP_CONFIG_DIR


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_RULES_DIR = Path(__file__).resolve().parent.parent.parent.parent.parent / "rules"
_USER_RULES_PATH = APP_CONFIG_DIR / "user_rules.json"


# ---------------------------------------------------------------------------
# Data model helpers
# ---------------------------------------------------------------------------

def _new_rule(title: str = "", content: str = "") -> Dict[str, Any]:
    """Create a new UI rule dict."""
    return {
        "id": uuid.uuid4().hex[:12],
        "title": title,
        "content": content,
        "enabled": True,
        "created_at": time.time(),
    }


# ---------------------------------------------------------------------------
# File rules
# ---------------------------------------------------------------------------

def get_rules_dir() -> Path:
    """Return the rules/ directory path."""
    return _RULES_DIR


def ensure_rules_dir() -> Path:
    """Ensure the rules/ directory exists and return it."""
    _RULES_DIR.mkdir(parents=True, exist_ok=True)
    return _RULES_DIR


def _scan_file_rules() -> List[Dict[str, Any]]:
    """Scan rules/ directory for .md and .txt files.

    Files starting with ``_`` are excluded (treated as templates/examples).
    """
    rules: List[Dict[str, Any]] = []
    if not _RULES_DIR.exists():
        return rules

    for path in sorted(_RULES_DIR.iterdir()):
        if path.name.startswith("_"):
            continue
        if path.suffix.lower() not in (".md", ".txt"):
            continue
        if not path.is_file():
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except Exception:
            continue
        rules.append({
            "id": f"file:{path.name}",
            "title": path.stem,
            "content": content,
            "enabled": True,
            "source": "file",
            "file_path": str(path),
        })
    return rules


# ---------------------------------------------------------------------------
# UI rules
# ---------------------------------------------------------------------------

_ui_rules_cache: Optional[List[Dict[str, Any]]] = None


def _load_ui_rules() -> List[Dict[str, Any]]:
    """Load UI rules from user_rules.json."""
    global _ui_rules_cache
    if _ui_rules_cache is not None:
        return _ui_rules_cache

    if not _USER_RULES_PATH.exists():
        _ui_rules_cache = []
        return _ui_rules_cache

    try:
        data = json.loads(_USER_RULES_PATH.read_text(encoding="utf-8"))
        if isinstance(data, list):
            _ui_rules_cache = data
        else:
            _ui_rules_cache = []
    except Exception:
        _ui_rules_cache = []
    return _ui_rules_cache


def _save_ui_rules(rules: List[Dict[str, Any]]) -> None:
    """Persist UI rules to user_rules.json."""
    global _ui_rules_cache
    _USER_RULES_PATH.parent.mkdir(parents=True, exist_ok=True)
    # Strip runtime-only keys
    clean = []
    for r in rules:
        entry = {k: v for k, v in r.items() if k not in ("source", "file_path")}
        clean.append(entry)
    _USER_RULES_PATH.write_text(
        json.dumps(clean, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    _ui_rules_cache = list(rules)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_all_rules(force_reload: bool = False) -> List[Dict[str, Any]]:
    """Get all rules (UI + file)."""
    global _ui_rules_cache
    if force_reload:
        _ui_rules_cache = None
    ui = _load_ui_rules()
    for r in ui:
        r.setdefault("source", "ui")
    file_rules = _scan_file_rules()
    return ui + file_rules


def get_ui_rules() -> List[Dict[str, Any]]:
    """Get only UI rules."""
    rules = _load_ui_rules()
    for r in rules:
        r.setdefault("source", "ui")
    return rules


def add_rule(title: str = "", content: str = "") -> Dict[str, Any]:
    """Add a new UI rule and persist."""
    rule = _new_rule(title=title, content=content)
    rules = _load_ui_rules()
    rules.append(rule)
    _save_ui_rules(rules)
    rule["source"] = "ui"
    return rule


def update_rule(rule_id: str, **kwargs: Any) -> Optional[Dict[str, Any]]:
    """Update an existing UI rule by ID. Returns the updated rule or None."""
    rules = _load_ui_rules()
    for r in rules:
        if r.get("id") == rule_id:
            for key in ("title", "content", "enabled"):
                if key in kwargs:
                    r[key] = kwargs[key]
            _save_ui_rules(rules)
            r.setdefault("source", "ui")
            return r
    return None


def delete_rule(rule_id: str) -> bool:
    """Delete a UI rule by ID. Returns True if deleted."""
    rules = _load_ui_rules()
    new_rules = [r for r in rules if r.get("id") != rule_id]
    if len(new_rules) == len(rules):
        return False
    _save_ui_rules(new_rules)
    return True


def set_rule_enabled(rule_id: str, enabled: bool) -> bool:
    """Toggle a UI rule's enabled state."""
    result = update_rule(rule_id, enabled=enabled)
    return result is not None


def save_all_ui_rules(rules: List[Dict[str, Any]]) -> None:
    """Batch-replace all UI rules."""
    _save_ui_rules(rules)


def reload_rules() -> None:
    """Clear cache and force reload on next access."""
    global _ui_rules_cache
    _ui_rules_cache = None


# ---------------------------------------------------------------------------
# Prompt injection
# ---------------------------------------------------------------------------

def get_rules_for_prompt() -> str:
    """Format all enabled rules as a text block for system prompt injection.

    Returns an empty string if no rules are enabled.
    """
    all_rules = get_all_rules()
    enabled = [r for r in all_rules if r.get("enabled", True)]
    if not enabled:
        return ""

    parts: List[str] = []
    for r in enabled:
        title = r.get("title", "").strip()
        content = r.get("content", "").strip()
        if not content:
            continue
        if title:
            parts.append(f"## {title}\n{content}")
        else:
            parts.append(content)

    if not parts:
        return ""

    body = "\n\n".join(parts)
    return (
        "<user_rules>\n"
        "The following are custom rules defined by the user. "
        "You MUST follow them in every response.\n\n"
        f"{body}\n"
        "</user_rules>"
    )
