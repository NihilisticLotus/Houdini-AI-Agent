"""Streaming code preview widget with syntax-aware highlighting for VEX/Python."""

from __future__ import annotations

import re
from typing import Optional

from houdini_ai_agent.qt import QtCore, QtGui, QtWidgets
from houdini_ai_agent.ui.style import scaled


class CodePreviewWidget(QtWidgets.QFrame):
    """Widget that displays code with syntax highlighting and streaming support."""

    copy_requested = QtCore.Signal()

    # Simple syntax highlighting rules
    _RULES = [
        # Python keywords
        (r"\b(def|class|import|from|return|if|elif|else|for|while|try|except|finally|with|as|pass|break|continue|yield|lambda|and|or|not|in|is|True|False|None|raise|global|nonlocal|assert|del)\b", "#c678dd"),
        # VEX keywords
        (r"\b(function|return|if|else|for|while|do|foreach|break|continue|int|float|vector|vector4|string|matrix|matrix3|void|struct|typedef|enum|union|export|using|include|pragma)\b", "#c678dd"),
        # Numbers
        (r"\b(\d+\.?\d*(?:[eE][+-]?\d+)?)\b", "#d19a66"),
        # Strings (double and single quoted)
        (r'(?:"[^"]*"|\'[^\']*\')', "#98c379"),
        # Comments (Python # and VEX //)
        (r"(#[^\n]*|//[^\n]*)", "#5c6370"),
        # VEX block comments
        (r"/\*[\s\S]*?\*/", "#5c6370"),
        # Decorators / pragmas
        (r"^[\t ]*(@\w+|#pragma\b)", "#e5c07b"),
        # Function calls
        (r"\b(\w+)\s*\(", "#61afef"),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("CodePreviewWidget")
        self._code = ""
        self._language = ""
        self._is_streaming = False
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(scaled(8), scaled(6), scaled(8), scaled(6))
        layout.setSpacing(scaled(4))

        # Header
        header = QtWidgets.QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(scaled(8))

        self._lang_label = QtWidgets.QLabel("")
        self._lang_label.setObjectName("HintText")

        self._status_label = QtWidgets.QLabel("")
        self._status_label.setObjectName("HintText")

        self._line_count = QtWidgets.QLabel("")
        self._line_count.setObjectName("HintText")

        header.addWidget(self._lang_label)
        header.addWidget(self._status_label)
        header.addStretch(1)
        header.addWidget(self._line_count)

        copy_btn = QtWidgets.QToolButton()
        copy_btn.setText("Copy")
        copy_btn.setObjectName("GhostButton")
        copy_btn.clicked.connect(self.copy_requested.emit)
        header.addWidget(copy_btn)
        layout.addLayout(header)

        # Code display
        self._code_display = QtWidgets.QTextBrowser()
        self._code_display.setObjectName("CodeDisplay")
        self._code_display.setOpenExternalLinks(False)
        self._code_display.setLineWrapMode(QtWidgets.QTextEdit.NoWrap)
        layout.addWidget(self._code_display, 1)

    def set_language(self, lang: str) -> None:
        """Set the language for syntax highlighting (python/vex)."""
        self._language = lang
        self._lang_label.setText(lang.upper() if lang else "")

    def set_code(self, code: str) -> None:
        """Set the code content and re-render."""
        self._code = code
        self._is_streaming = False
        self._status_label.setText("")
        self._render()

    def append_streaming(self, chunk: str) -> None:
        """Append a streaming chunk and re-render."""
        self._is_streaming = True
        self._code += chunk
        self._status_label.setText("Streaming...")
        self._render()

    def finish_streaming(self) -> None:
        """Mark streaming as complete."""
        self._is_streaming = False
        self._status_label.setText("Complete")
        self._render()

    def clear(self) -> None:
        """Clear the code preview."""
        self._code = ""
        self._is_streaming = False
        self._language = ""
        self._code_display.setHtml("")
        self._lang_label.setText("")
        self._status_label.setText("")
        self._line_count.setText("")

    def _render(self) -> None:
        """Render code with syntax highlighting."""
        if not self._code:
            self._code_display.setHtml("")
            self._line_count.setText("")
            return

        lines = self._code.splitlines()
        self._line_count.setText(f"{len(lines)} lines")

        # Build highlighted HTML
        html_parts = []
        for i, line in enumerate(lines, 1):
            escaped = self._highlight_line(line)
            line_num = f'<span style="color:#4b5263; user-select:none;">{i:>4} │ </span>'
            html_parts.append(f"{line_num}{escaped}")

        # Add cursor indicator when streaming
        cursor = ""
        if self._is_streaming:
            cursor = '<span style="background:#abb2bf; color:#282c34;">▎</span>'

        html = (
            "<pre style='margin:0; padding:0; font-family:Consolas, \"Courier New\", monospace; "
            f"font-size:{scaled(12)}px; line-height:1.45; color:#abb2bf; background:transparent;'>"
            + "<br/>".join(html_parts)
            + cursor
            + "</pre>"
        )
        self._code_display.setHtml(html)

    def _highlight_line(self, line: str) -> str:
        """Apply syntax highlighting to a single line, returning HTML."""
        from html import escape
        result = escape(line)

        # Apply rules in order (simple approach: replace matches)
        for pattern, color in self._RULES:
            # We need to avoid replacing inside already-HTML-escaped content
            # Simple approach: work on the escaped text and use non-overlapping replacement
            try:
                result = re.sub(
                    pattern,
                    lambda m: f'<span style="color:{color};">{m.group(0)}</span>',
                    result,
                )
            except re.error:
                pass
        return result

    def get_code(self) -> str:
        """Return the raw code text."""
        return self._code
