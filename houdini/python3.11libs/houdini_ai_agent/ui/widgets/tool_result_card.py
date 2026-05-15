"""Structured card widget for displaying tool execution results."""

from __future__ import annotations

import json
from html import escape
from typing import Dict, List, Optional

from houdini_ai_agent.qt import QtCore, QtGui, QtWidgets
from houdini_ai_agent.ui.style import scaled


class ToolResultCard(QtWidgets.QFrame):
    """A collapsible card showing a tool execution result with status indicator."""

    undo_requested = QtCore.Signal(str, dict)
    link_clicked = QtCore.Signal(str)

    def __init__(
        self,
        title: str,
        message: str = "",
        success: bool = True,
        events: Optional[List[Dict[str, str]]] = None,
        changed_paths: Optional[List[str]] = None,
        warnings: Optional[List[str]] = None,
        errors: Optional[List[str]] = None,
        tool_name: str = "",
        raw_action: Optional[dict] = None,
        parent=None,
    ):
        super().__init__(parent)
        self.setObjectName("ToolResultCard")
        self._expanded = True
        self._title = title
        self._tool_name = tool_name
        self._raw_action = raw_action or {}
        self._build_ui(title, message, success, events or [], changed_paths or [],
                       warnings or [], errors or [])

    def _build_ui(
        self,
        title: str,
        message: str,
        success: bool,
        events: List[Dict[str, str]],
        changed_paths: List[str],
        warnings: List[str],
        errors: List[str],
    ) -> None:
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(scaled(10), scaled(8), scaled(10), scaled(8))
        layout.setSpacing(scaled(6))

        # Header row: status icon + title + toggle
        header = QtWidgets.QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(scaled(6))

        self._status_icon = QtWidgets.QLabel(self._status_symbol(success))
        self._status_icon.setObjectName("ToolStatusIcon")
        self._status_icon.setFixedWidth(scaled(18))

        title_label = QtWidgets.QLabel(escape(title))
        title_label.setObjectName("ToolResultTitle")

        self._toggle_btn = QtWidgets.QToolButton()
        self._toggle_btn.setObjectName("ThoughtToggle")
        self._toggle_btn.setCheckable(True)
        self._toggle_btn.setChecked(True)
        self._toggle_btn.setArrowType(QtCore.Qt.DownArrow)
        self._toggle_btn.setFixedWidth(scaled(16))
        self._toggle_btn.toggled.connect(self._toggle_body)

        header.addWidget(self._status_icon)
        header.addWidget(title_label, 1)
        header.addWidget(self._toggle_btn)
        layout.addLayout(header)

        # Body container
        self._body = QtWidgets.QWidget()
        body_layout = QtWidgets.QVBoxLayout(self._body)
        body_layout.setContentsMargins(scaled(18), 0, 0, 0)
        body_layout.setSpacing(scaled(4))

        # Message body
        if message:
            msg_label = QtWidgets.QLabel()
            msg_label.setWordWrap(True)
            msg_label.setTextFormat(QtCore.Qt.PlainText)
            msg_label.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
            msg_label.setObjectName("ToolResultMessage")
            display = message
            if len(display) > 2000:
                display = display[:1800] + "\n... (truncated)"
            msg_label.setText(display)
            body_layout.addWidget(msg_label)

        # Events
        for event in events[:10]:
            ev_title = escape(str(event.get("title", "")))
            ev_detail = escape(str(event.get("detail", "")))
            ev_status = str(event.get("status", "info")).lower()
            color = {"success": "#4caf50", "warning": "#ff9800", "error": "#f44336"}.get(ev_status, "#8c929d")
            ev_html = f"<span style='color:{color}; font-weight:600;'>{ev_title}</span>"
            if ev_detail:
                ev_html += f": {ev_detail}"
            ev_label = QtWidgets.QLabel(ev_html)
            ev_label.setWordWrap(True)
            ev_label.setTextFormat(QtCore.Qt.RichText)
            ev_label.setObjectName("ToolResultEvent")
            body_layout.addWidget(ev_label)

        # Warnings
        if warnings:
            for w in warnings[:5]:
                w_label = QtWidgets.QLabel(f"⚠ {escape(w)}")
                w_label.setObjectName("ToolResultWarning")
                w_label.setWordWrap(True)
                body_layout.addWidget(w_label)

        # Errors
        if errors:
            for e in errors[:5]:
                e_label = QtWidgets.QLabel(f"✕ {escape(e)}")
                e_label.setObjectName("ToolResultError")
                e_label.setWordWrap(True)
                body_layout.addWidget(e_label)

        # Changed paths
        if changed_paths:
            path_text = "Changed: " + ", ".join(escape(p) for p in changed_paths[:8])
            if len(changed_paths) > 8:
                path_text += f" (+{len(changed_paths) - 8})"
            path_label = QtWidgets.QLabel(path_text)
            path_label.setObjectName("ToolResultPaths")
            path_label.setWordWrap(True)
            body_layout.addWidget(path_label)

        # Undo button for mutating tools
        mutating_tools = {
            "create_node", "set_parm", "delete_node", "connect_nodes",
            "copy_node", "batch_set_parameters", "set_display_flag",
            "layout_nodes", "apply_code",
        }
        if self._tool_name in mutating_tools and self._raw_action:
            undo_row = QtWidgets.QHBoxLayout()
            undo_row.addStretch(1)
            self._undo_btn = QtWidgets.QPushButton("Undo")
            self._undo_btn.setObjectName("GhostButton")
            self._undo_btn.setFixedWidth(scaled(60))
            self._undo_btn.clicked.connect(self._emit_undo)
            undo_row.addWidget(self._undo_btn)
            body_layout.addLayout(undo_row)

        layout.addWidget(self._body)

    @staticmethod
    def _status_symbol(success: bool) -> str:
        return "✓" if success else "✕"

    def _toggle_body(self, checked: bool) -> None:
        self._toggle_btn.setArrowType(QtCore.Qt.DownArrow if checked else QtCore.Qt.RightArrow)
        self._body.setVisible(checked)

    def _emit_undo(self) -> None:
        self.undo_requested.emit(self._tool_name, dict(self._raw_action))

    @classmethod
    def from_result(cls, result: dict, parent=None) -> "ToolResultCard":
        """Create a ToolResultCard from an ActionRunner result dict."""
        return cls(
            title=str(result.get("title", "Tool Result")),
            message=str(result.get("message", "")),
            success=bool(result.get("success", True)),
            events=result.get("events", []),
            changed_paths=result.get("changed_paths", []),
            warnings=result.get("warnings", []),
            errors=result.get("errors", []),
            tool_name=str(result.get("tool_name", "")),
            raw_action=result.get("raw_action"),
            parent=parent,
        )
