"""Scene context and execution trace widgets."""

from __future__ import annotations

from houdini_ai_agent.qt import QtCore, QtWidgets
from houdini_ai_agent.ui.style import scaled


class ContextPanel(QtWidgets.QWidget):
    refresh_requested = QtCore.Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(QtCore.Qt.WA_StyledBackground, True)
        self.setAutoFillBackground(True)
        self._labels = {}
        self._build_ui()

    def set_context(self, context: dict) -> None:
        self._set("hip_file", str(context.get("hip_file", "Unknown")))
        self._set("network", str(context.get("network", "Unknown")))
        selected = context.get("selected_nodes", [])
        self._set("selected_nodes", "\n".join(selected) if selected else "None")
        self._set("viewport", str(context.get("viewport", "Unknown")))
        self._set("summary", str(context.get("summary", "")))

        errors = context.get("errors", [])
        if errors:
            lines = [f"[{item.get('severity', 'info')}] {item.get('node')}: {item.get('message')}" for item in errors]
            self._set("errors", "\n".join(lines))
        else:
            self._set("errors", "No errors or warnings in current context.")

    def _build_ui(self) -> None:
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(scaled(8), scaled(8), scaled(8), scaled(8))
        root.setSpacing(scaled(8))

        title_row = QtWidgets.QHBoxLayout()
        title = QtWidgets.QLabel("工程上下文")
        title.setObjectName("PanelTitle")
        refresh = QtWidgets.QPushButton("刷新")
        refresh.setFixedWidth(scaled(58))
        refresh.clicked.connect(self.refresh_requested.emit)
        title_row.addWidget(title)
        title_row.addStretch(1)
        title_row.addWidget(refresh)
        root.addLayout(title_row)

        self._add_section(root, "HIP", "hip_file")
        self._add_section(root, "当前网络", "network")
        self._add_section(root, "选中节点", "selected_nodes")
        self._add_section(root, "视口", "viewport")
        self._add_section(root, "错误摘要", "errors")
        self._add_section(root, "摘要", "summary")
        root.addStretch(1)

    def _add_section(self, root, title: str, key: str) -> None:
        group = QtWidgets.QGroupBox(title)
        layout = QtWidgets.QVBoxLayout(group)
        layout.setContentsMargins(scaled(8), scaled(8), scaled(8), scaled(8))
        layout.setSpacing(scaled(4))
        value = QtWidgets.QLabel("")
        value.setWordWrap(True)
        value.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
        value.setObjectName("ContextValue")
        self._labels[key] = value
        layout.addWidget(value)
        root.addWidget(group)

    def _set(self, key: str, value: str) -> None:
        self._labels[key].setText(value)


class ExecutionTrace(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(QtCore.Qt.WA_StyledBackground, True)
        self.setAutoFillBackground(True)
        self._build_ui()

    def add_event(self, event) -> None:
        item = QtWidgets.QListWidgetItem(f"{event.timestamp}  {event.title}\n{event.detail}")
        item.setData(QtCore.Qt.UserRole, event.status)
        if event.status == "success":
            item.setForeground(QtCore.Qt.darkGreen)
        elif event.status == "warning":
            item.setForeground(QtCore.Qt.darkYellow)
        elif event.status == "running":
            item.setForeground(QtCore.Qt.darkCyan)
        self.list.addItem(item)
        self.list.scrollToBottom()

    def clear(self) -> None:
        self.list.clear()

    def _build_ui(self) -> None:
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(scaled(6))
        title = QtWidgets.QLabel("执行轨迹")
        title.setObjectName("PanelTitle")
        self.list = QtWidgets.QListWidget()
        self.list.setAlternatingRowColors(True)
        root.addWidget(title)
        root.addWidget(self.list, 1)
