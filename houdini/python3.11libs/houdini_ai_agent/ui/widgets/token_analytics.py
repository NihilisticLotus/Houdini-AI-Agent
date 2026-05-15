"""Token usage analytics panel with per-turn breakdown and cost estimation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from houdini_ai_agent.qt import QtCore, QtGui, QtWidgets
from houdini_ai_agent.ui.style import scaled


@dataclass
class TokenUsage:
    """Token usage record for a single API call."""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    model: str = ""
    cost_usd: float = 0.0
    timestamp: str = ""
    turn: int = 0


class TokenAnalyticsPanel(QtWidgets.QWidget):
    """Panel showing token usage analytics, cost estimation, and context window visualization."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._usage_history: List[TokenUsage] = []
        self._context_window = 128_000
        self._current_usage_tokens = 0
        self._build_ui()

    def _build_ui(self) -> None:
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(scaled(8), scaled(8), scaled(8), scaled(8))
        root.setSpacing(scaled(8))

        # Header
        header_row = QtWidgets.QHBoxLayout()
        header_row.setContentsMargins(0, 0, 0, 0)
        title = QtWidgets.QLabel("Token Analytics")
        title.setObjectName("PanelTitle")
        header_row.addWidget(title, 1)
        root.addLayout(header_row)

        # Context window bar
        self._context_bar = ContextWindowBar()
        root.addWidget(self._context_bar)

        # Summary stats
        self._stats_frame = QtWidgets.QFrame()
        self._stats_frame.setObjectName("TokenStatsFrame")
        stats_layout = QtWidgets.QHBoxLayout(self._stats_frame)
        stats_layout.setContentsMargins(scaled(6), scaled(6), scaled(6), scaled(6))
        stats_layout.setSpacing(scaled(12))

        self._total_label = self._stat_label("Total", "0")
        self._prompt_label = self._stat_label("Prompt", "0")
        self._completion_label = self._stat_label("Completion", "0")
        self._cost_label = self._stat_label("Cost", "$0.00")

        stats_layout.addWidget(self._total_label)
        stats_layout.addWidget(self._prompt_label)
        stats_layout.addWidget(self._completion_label)
        stats_layout.addWidget(self._cost_label)
        root.addWidget(self._stats_frame)

        # Turn-by-turn table
        self._table = QtWidgets.QTableWidget(0, 5)
        self._table.setObjectName("TokenTable")
        self._table.setHorizontalHeaderLabels(["Turn", "Prompt", "Completion", "Total", "Cost"])
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.horizontalHeader().setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(1, QtWidgets.QHeaderView.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(2, QtWidgets.QHeaderView.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(3, QtWidgets.QHeaderView.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(4, QtWidgets.QHeaderView.ResizeToContents)
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self._table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self._table.setMaximumHeight(scaled(200))
        root.addWidget(self._table, 1)

        # Clear button
        btn_row = QtWidgets.QHBoxLayout()
        btn_row.addStretch(1)
        clear_btn = QtWidgets.QPushButton("Clear History")
        clear_btn.setObjectName("GhostButton")
        clear_btn.setFixedWidth(scaled(90))
        clear_btn.clicked.connect(self.clear_history)
        btn_row.addWidget(clear_btn)
        root.addLayout(btn_row)

    @staticmethod
    def _stat_label(title: str, value: str) -> QtWidgets.QWidget:
        w = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(w)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(scaled(2))
        t = QtWidgets.QLabel(title)
        t.setObjectName("HintText")
        v = QtWidgets.QLabel(value)
        v.setObjectName("TokenStatValue")
        layout.addWidget(t)
        layout.addWidget(v)
        w._value_label = v
        return w

    def set_context_window(self, total: int) -> None:
        self._context_window = max(1, total)
        self._update_bar()

    def set_current_usage(self, tokens: int) -> None:
        self._current_usage_tokens = tokens
        self._update_bar()

    def add_usage(self, usage: TokenUsage) -> None:
        self._usage_history.append(usage)
        self._add_table_row(usage)
        self._update_summary()
        self._update_bar()

    def clear_history(self) -> None:
        self._usage_history.clear()
        self._table.setRowCount(0)
        self._update_summary()

    def _add_table_row(self, usage: TokenUsage) -> None:
        row = self._table.rowCount()
        self._table.insertRow(row)
        self._table.setItem(row, 0, QtWidgets.QTableWidgetItem(str(usage.turn)))
        self._table.setItem(row, 1, QtWidgets.QTableWidgetItem(f"{usage.prompt_tokens:,}"))
        self._table.setItem(row, 2, QtWidgets.QTableWidgetItem(f"{usage.completion_tokens:,}"))
        self._table.setItem(row, 3, QtWidgets.QTableWidgetItem(f"{usage.total_tokens:,}"))
        cost_item = QtWidgets.QTableWidgetItem(f"${usage.cost_usd:.4f}")
        self._table.setItem(row, 4, cost_item)
        self._table.scrollToBottom()

    def _update_summary(self) -> None:
        total_prompt = sum(u.prompt_tokens for u in self._usage_history)
        total_completion = sum(u.completion_tokens for u in self._usage_history)
        total_all = sum(u.total_tokens for u in self._usage_history)
        total_cost = sum(u.cost_usd for u in self._usage_history)

        self._total_label._value_label.setText(f"{total_all:,}")
        self._prompt_label._value_label.setText(f"{total_prompt:,}")
        self._completion_label._value_label.setText(f"{total_completion:,}")
        self._cost_label._value_label.setText(f"${total_cost:.4f}")

    def _update_bar(self) -> None:
        self._context_bar.set_usage(self._current_usage_tokens, self._context_window)

    @classmethod
    def estimate_cost(cls, prompt_tokens: int, completion_tokens: int, model: str) -> float:
        """Estimate cost in USD based on model pricing (rough estimates)."""
        m = model.lower()
        # Pricing per 1M tokens (approximate)
        if "gpt-4o" in m or "gpt-4-turbo" in m:
            p_rate, c_rate = 2.50, 10.00
        elif "gpt-4" in m:
            p_rate, c_rate = 30.00, 60.00
        elif "gpt-3.5" in m:
            p_rate, c_rate = 0.50, 1.50
        elif "claude-3.5" in m or "claude-3-5" in m:
            p_rate, c_rate = 3.00, 15.00
        elif "claude-3" in m:
            p_rate, c_rate = 0.25, 1.25
        elif "deepseek" in m:
            p_rate, c_rate = 0.14, 0.28
        elif "glm" in m:
            p_rate, c_rate = 0.10, 0.10
        else:
            p_rate, c_rate = 1.00, 3.00
        return (prompt_tokens / 1_000_000) * p_rate + (completion_tokens / 1_000_000) * c_rate


class ContextWindowBar(QtWidgets.QWidget):
    """Horizontal bar showing current context window usage."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._used = 0
        self._total = 128_000
        self.setFixedHeight(scaled(32))
        self.setMinimumWidth(scaled(200))

    def set_usage(self, used: int, total: int) -> None:
        self._used = max(0, used)
        self._total = max(1, total)
        self.update()

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)

        w = self.width()
        h = self.height()
        bar_h = scaled(12)
        y = (h - bar_h) // 2
        margin = scaled(4)

        # Background
        painter.setPen(QtCore.Qt.NoPen)
        painter.setBrush(QtGui.QColor("#2a2d33"))
        painter.drawRoundedRect(margin, y, w - 2 * margin, bar_h, 4, 4)

        # Fill
        ratio = min(1.0, self._used / self._total) if self._total > 0 else 0
        fill_w = max(0, int((w - 2 * margin) * ratio))
        if ratio < 0.5:
            fill_color = QtGui.QColor("#4caf50")
        elif ratio < 0.8:
            fill_color = QtGui.QColor("#ff9800")
        else:
            fill_color = QtGui.QColor("#f44336")

        if fill_w > 0:
            painter.setBrush(fill_color)
            painter.drawRoundedRect(margin, y, fill_w, bar_h, 4, 4)

        # Text
        painter.setPen(QtGui.QColor("#d8dee8"))
        font = painter.font()
        font.setPixelSize(scaled(10))
        painter.setFont(font)
        pct = int(ratio * 100)
        text = f"{self._used:,} / {self._total:,}  ({pct}%)"
        painter.drawText(self.rect(), QtCore.Qt.AlignCenter, text)
        painter.end()
