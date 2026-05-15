"""Reusable UI widgets for the Houdini AI Agent panel.

Widget imports are lazy to avoid requiring Qt at import time.
This allows core tests to run without PySide2/PySide6 installed.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from houdini_ai_agent.ui.widgets.tool_result_card import ToolResultCard
    from houdini_ai_agent.ui.widgets.param_diff import ParamDiffView
    from houdini_ai_agent.ui.widgets.token_analytics import TokenAnalyticsPanel
    from houdini_ai_agent.ui.widgets.node_completer import NodeCompleter
    from houdini_ai_agent.ui.widgets.code_preview import CodePreviewWidget


def __getattr__(name: str):
    """Lazy import widgets on first access."""
    _lazy = {
        "ToolResultCard": ".tool_result_card",
        "ParamDiffView": ".param_diff",
        "TokenAnalyticsPanel": ".token_analytics",
        "NodeCompleter": ".node_completer",
        "CodePreviewWidget": ".code_preview",
    }
    if name in _lazy:
        import importlib
        module = importlib.import_module(_lazy[name], __package__)
        return getattr(module, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "ToolResultCard",
    "ParamDiffView",
    "TokenAnalyticsPanel",
    "NodeCompleter",
    "CodePreviewWidget",
]
