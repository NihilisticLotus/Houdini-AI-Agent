""""@-mention node path autocomplete popup for ChatInput."""

from __future__ import annotations

from typing import Callable, List, Optional

from houdini_ai_agent.qt import QtCore, QtGui, QtWidgets
from houdini_ai_agent.ui.style import scaled


class NodeCompleter(QtWidgets.QListWidget):
    """Popup list that shows matching node paths for @-mention completion."""

    path_selected = QtCore.Signal(str)

    MAX_VISIBLE_ITEMS = 8

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("NodeCompleter")
        self.setWindowFlags(QtCore.Qt.Popup | QtCore.Qt.FramelessWindowHint)
        self.setAttribute(QtCore.Qt.WA_ShowWithoutActivating)
        self.setFocusPolicy(QtCore.Qt.NoFocus)
        self.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)
        self.itemClicked.connect(self._on_item_clicked)
        self._trigger_char = "@"
        self._min_chars = 1
        self._all_paths: List[str] = []
        self._current_prefix = ""
        self._target_edit: Optional[QtWidgets.QTextEdit] = None

    def set_node_paths(self, paths: List[str]) -> None:
        """Set the full list of available node paths."""
        self._all_paths = sorted(set(paths))

    def attach_to(self, text_edit: QtWidgets.QTextEdit) -> None:
        """Attach this completer to a QTextEdit widget."""
        self._target_edit = text_edit

    def try_complete(self, text: str, cursor_pos: int, global_pos: QtCore.QPoint) -> bool:
        """Check if cursor is after a @trigger and show completions.

        Returns True if the completer was shown.
        """
        prefix = self._extract_prefix(text, cursor_pos)
        if prefix is None:
            self.hide()
            return False

        self._current_prefix = prefix
        matches = self._find_matches(prefix)
        if not matches:
            self.hide()
            return False

        self._populate(matches)
        self.move(global_pos)
        self.show()
        return True

    def handle_key(self, event: QtGui.QKeyEvent) -> bool:
        """Handle keyboard navigation. Returns True if the event was consumed."""
        if not self.isVisible():
            return False

        key = event.key()
        if key == QtCore.Qt.Key_Escape:
            self.hide()
            return True
        if key in (QtCore.Qt.Key_Return, QtCore.Qt.Key_Enter, QtCore.Qt.Key_Tab):
            current = self.currentItem()
            if current:
                self._apply_completion(current.text())
            self.hide()
            return True
        if key == QtCore.Qt.Key_Up:
            row = max(0, self.currentRow() - 1)
            self.setCurrentRow(row)
            return True
        if key == QtCore.Qt.Key_Down:
            row = min(self.count() - 1, self.currentRow() + 1)
            self.setCurrentRow(row)
            return True
        return False

    def _extract_prefix(self, text: str, cursor_pos: int) -> Optional[str]:
        """Extract the completion prefix after @ if cursor is in a mention."""
        before = text[:cursor_pos]
        at_idx = before.rfind(self._trigger_char)
        if at_idx < 0:
            return None
        # Don't trigger if there's a space between @ and cursor
        segment = before[at_idx + 1:]
        if " " in segment or "\n" in segment:
            return None
        if len(segment) < self._min_chars:
            return None
        return segment

    def _find_matches(self, prefix: str) -> List[str]:
        """Find node paths matching the prefix (case-insensitive substring)."""
        prefix_lower = prefix.lower()
        matches = []
        for path in self._all_paths:
            path_lower = path.lower()
            # Match if prefix is a substring of the path
            if prefix_lower in path_lower:
                matches.append(path)
            if len(matches) >= 30:
                break
        return matches

    def _populate(self, matches: List[str]) -> None:
        """Fill the list with matches."""
        self.clear()
        for path in matches[:self.MAX_VISIBLE_ITEMS]:
            self.addItem(path)
        if self.count() > 0:
            self.setCurrentRow(0)

        item_h = scaled(22)
        visible_count = min(self.count(), self.MAX_VISIBLE_ITEMS)
        self.setFixedHeight(visible_count * item_h + scaled(4))
        self.setFixedWidth(scaled(320))

    def _on_item_clicked(self, item: QtWidgets.QListWidgetItem) -> None:
        self._apply_completion(item.text())
        self.hide()

    def _apply_completion(self, path: str) -> None:
        """Insert the selected path into the text edit, replacing the @prefix."""
        if self._target_edit is None:
            return
        cursor = self._target_edit.textCursor()
        text = self._target_edit.toPlainText()
        pos = cursor.position()

        # Find the @ before cursor
        before = text[:pos]
        at_idx = before.rfind(self._trigger_char)
        if at_idx < 0:
            return

        # Replace from @ to cursor with the full path
        cursor.setPosition(at_idx)
        cursor.setPosition(pos, QtGui.QTextCursor.KeepAnchor)
        cursor.insertText(path + " ")
        self._target_edit.setTextCursor(cursor)
        self.path_selected.emit(path)
