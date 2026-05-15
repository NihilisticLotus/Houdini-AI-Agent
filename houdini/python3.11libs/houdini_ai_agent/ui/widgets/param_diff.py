"""Parameter diff preview widget with red/green comparison and undo support."""

from __future__ import annotations

from html import escape
from typing import Dict, List, Optional, Tuple

from houdini_ai_agent.qt import QtCore, QtGui, QtWidgets
from houdini_ai_agent.ui.style import scaled


class ParamDiffView(QtWidgets.QFrame):
    """Shows before/after parameter values with red/green diff and one-click undo."""

    undo_requested = QtCore.Signal(str, str, object)

    def __init__(
        self,
        diffs: List[Dict[str, object]],
        parent=None,
    ):
        super().__init__(parent)
        self.setObjectName("ParamDiffView")
        self._diffs = diffs
        self._build_ui(diffs)

    def _build_ui(self, diffs: List[Dict[str, object]]) -> None:
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(scaled(10), scaled(8), scaled(10), scaled(8))
        layout.setSpacing(scaled(6))

        header = QtWidgets.QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(scaled(6))

        title = QtWidgets.QLabel("Parameter Changes")
        title.setObjectName("PanelTitle")
        header.addWidget(title, 1)

        undo_all = QtWidgets.QPushButton("Undo All")
        undo_all.setObjectName("GhostButton")
        undo_all.setFixedWidth(scaled(72))
        undo_all.clicked.connect(self._undo_all)
        header.addWidget(undo_all)

        layout.addLayout(header)

        if not diffs:
            empty = QtWidgets.QLabel("No parameter changes.")
            empty.setObjectName("HintText")
            layout.addWidget(empty)
            return

        for i, diff in enumerate(diffs[:20]):
            layout.addWidget(self._build_diff_row(diff, i))

    def _build_diff_row(self, diff: Dict[str, object], index: int) -> QtWidgets.QWidget:
        row = QtWidgets.QFrame()
        row.setObjectName("ParamDiffRow")
        rlayout = QtWidgets.QHBoxLayout(row)
        rlayout.setContentsMargins(scaled(6), scaled(4), scaled(6), scaled(4))
        rlayout.setSpacing(scaled(8))

        node = escape(str(diff.get("node_path", "")))
        parm = escape(str(diff.get("parm", "")))
        old_val = str(diff.get("old_value", ""))
        new_val = str(diff.get("new_value", ""))

        node_label = QtWidgets.QLabel(node)
        node_label.setObjectName("ParamDiffNode")
        node_label.setFixedWidth(scaled(180))
        node_label.setWordWrap(True)
        node_label.setToolTip(str(diff.get("node_path", "")))

        parm_label = QtWidgets.QLabel(parm)
        parm_label.setObjectName("ParamDiffParm")
        parm_label.setFixedWidth(scaled(100))

        old_label = QtWidgets.QLabel(escape(old_val))
        old_label.setObjectName("ParamDiffOld")
        old_label.setStyleSheet("color: #e06c75; text-decoration: line-through;")
        old_label.setWordWrap(True)

        arrow = QtWidgets.QLabel("→")
        arrow.setObjectName("ParamDiffArrow")

        new_label = QtWidgets.QLabel(escape(new_val))
        new_label.setObjectName("ParamDiffNew")
        new_label.setStyleSheet("color: #98c379;")
        new_label.setWordWrap(True)

        undo_btn = QtWidgets.QToolButton()
        undo_btn.setText("↩")
        undo_btn.setObjectName("GhostButton")
        undo_btn.setFixedWidth(scaled(24))
        undo_btn.setToolTip("Undo this change")
        undo_btn.clicked.connect(lambda checked=False, d=diff: self._undo_single(d))

        rlayout.addWidget(node_label)
        rlayout.addWidget(parm_label)
        rlayout.addWidget(old_label, 1)
        rlayout.addWidget(arrow)
        rlayout.addWidget(new_label, 1)
        rlayout.addWidget(undo_btn)

        return row

    def _undo_single(self, diff: Dict[str, object]) -> None:
        node_path = str(diff.get("node_path", ""))
        parm = str(diff.get("parm", ""))
        old_value = diff.get("old_value", "")
        self.undo_requested.emit(node_path, parm, old_value)

    def _undo_all(self) -> None:
        for diff in self._diffs:
            self._undo_single(diff)
