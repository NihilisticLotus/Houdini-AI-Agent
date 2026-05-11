"""Provider settings dialog."""

from __future__ import annotations

from typing import List

from houdini_ai_agent.core.config import (
    ProviderConfig,
    discover_external_configs,
    save_providers,
)
from houdini_ai_agent.core.session import THINKING_LEVELS
from houdini_ai_agent.qt import QtCore, QtWidgets


class SettingsDialog(QtWidgets.QDialog):
    providers_saved = QtCore.Signal(list)

    COLUMNS = ["Name", "Base URL", "API Key / Env", "Model", "Reasoning", "Vision", "Vision Fallback", "Default Thinking"]

    def __init__(self, providers: List[ProviderConfig], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Houdini AI Agent 设置")
        self.resize(860, 560)
        self.providers = [p for p in providers]
        self._build_ui()
        self._populate()

    def _build_ui(self) -> None:
        root = QtWidgets.QVBoxLayout(self)
        root.setSpacing(10)

        intro = QtWidgets.QLabel(
            "配置 OpenAI-compatible provider。API Key 只保存环境变量名，不保存密钥本身。"
        )
        intro.setText("Configure OpenAI-compatible providers. API Key accepts an env name or direct key. Mark one provider as a vision fallback for text-only models.")
        intro.setWordWrap(True)
        root.addWidget(intro)

        self.table = QtWidgets.QTableWidget(0, len(self.COLUMNS))
        self.table.setHorizontalHeaderLabels(self.COLUMNS)
        header = self.table.horizontalHeader()
        header.setStretchLastSection(True)
        header.setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QtWidgets.QHeaderView.Stretch)
        header.setSectionResizeMode(2, QtWidgets.QHeaderView.Stretch)
        header.setSectionResizeMode(3, QtWidgets.QHeaderView.ResizeToContents)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        root.addWidget(self.table, 1)

        button_row = QtWidgets.QHBoxLayout()
        add_btn = QtWidgets.QPushButton("添加 Provider")
        add_openai_btn = QtWidgets.QPushButton("添加 OpenAI 示例")
        remove_btn = QtWidgets.QPushButton("删除选中")
        add_btn.clicked.connect(self._add_blank_provider)
        add_openai_btn.clicked.connect(self._add_openai_provider)
        remove_btn.clicked.connect(self._remove_selected)
        button_row.addWidget(add_btn)
        button_row.addWidget(add_openai_btn)
        button_row.addWidget(remove_btn)
        button_row.addStretch(1)
        root.addLayout(button_row)

        external_group = QtWidgets.QGroupBox("Codex / Claude 配置发现")
        external_layout = QtWidgets.QVBoxLayout(external_group)
        self.external_list = QtWidgets.QListWidget()
        external_layout.addWidget(self.external_list)
        root.addWidget(external_group)

        dialog_buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Save | QtWidgets.QDialogButtonBox.Cancel)
        dialog_buttons.accepted.connect(self._save)
        dialog_buttons.rejected.connect(self.reject)
        root.addWidget(dialog_buttons)

    def _populate(self) -> None:
        for provider in self.providers:
            self._append_provider_row(provider)
        self._populate_external_configs()

    def _append_provider_row(self, provider: ProviderConfig) -> None:
        row = self.table.rowCount()
        self.table.insertRow(row)
        self._set_item(row, 0, provider.name)
        self._set_item(row, 1, provider.base_url)
        self._set_item(row, 2, provider.api_key_env)
        self._set_item(row, 3, provider.model)

        reasoning = QtWidgets.QCheckBox()
        reasoning.setChecked(provider.supports_reasoning)
        self.table.setCellWidget(row, 4, reasoning)

        vision = QtWidgets.QCheckBox()
        vision.setChecked(provider.supports_vision)
        vision.setToolTip("Enable this for providers that can directly read attached images.")
        self.table.setCellWidget(row, 5, vision)

        fallback = QtWidgets.QCheckBox()
        fallback.setChecked(provider.use_as_vision_fallback)
        fallback.setToolTip("When the selected main model is text-only, the first checked fallback provider will summarize images for it.")
        self.table.setCellWidget(row, 6, fallback)

        thinking = QtWidgets.QComboBox()
        thinking.addItems(list(THINKING_LEVELS.keys()))
        index = thinking.findText(provider.default_thinking_level)
        thinking.setCurrentIndex(index if index >= 0 else 1)
        self.table.setCellWidget(row, 7, thinking)

        self.table.setRowHeight(row, 28)

    def _set_item(self, row: int, column: int, text: str) -> None:
        item = QtWidgets.QTableWidgetItem(text)
        self.table.setItem(row, column, item)

    def _populate_external_configs(self) -> None:
        self.external_list.clear()
        for hint in discover_external_configs():
            state = "found" if hint.found else "missing"
            model = f" model={hint.model}" if hint.model else ""
            provider = f" provider={hint.provider}" if hint.provider else ""
            self.external_list.addItem(f"{hint.source}: {state} | {hint.path}{model}{provider} | {hint.note}")

    def _add_blank_provider(self) -> None:
        self._append_provider_row(ProviderConfig(name="New Provider", source="custom"))

    def _add_openai_provider(self) -> None:
        self._append_provider_row(
            ProviderConfig(
                name="OpenAI",
                base_url="https://api.openai.com/v1",
                api_key_env="OPENAI_API_KEY",
                model="gpt-5.2",
                supports_reasoning=True,
                supports_vision=True,
                use_as_vision_fallback=False,
                default_thinking_level="中",
                source="custom",
            )
        )

    def _remove_selected(self) -> None:
        rows = sorted({index.row() for index in self.table.selectedIndexes()}, reverse=True)
        for row in rows:
            name_item = self.table.item(row, 0)
            if name_item and name_item.text() == "Mock Preview":
                continue
            self.table.removeRow(row)

    def _save(self) -> None:
        providers: List[ProviderConfig] = []
        for row in range(self.table.rowCount()):
            name = self._text(row, 0)
            if not name:
                continue
            reasoning = self.table.cellWidget(row, 4)
            vision = self.table.cellWidget(row, 5)
            fallback = self.table.cellWidget(row, 6)
            thinking = self.table.cellWidget(row, 7)
            source = "mock" if name == "Mock Preview" else "custom"
            providers.append(
                ProviderConfig(
                    name=name,
                    base_url=self._text(row, 1),
                    api_key_env=self._text(row, 2),
                    model=self._text(row, 3),
                    supports_reasoning=bool(reasoning.isChecked()) if reasoning else True,
                    supports_vision=bool(vision.isChecked()) if vision else True,
                    use_as_vision_fallback=bool(fallback.isChecked()) if fallback else False,
                    default_thinking_level=thinking.currentText() if thinking else "中",
                    source=source,
                )
            )
        save_providers(providers)
        self.providers_saved.emit(providers)
        self.accept()

    def _text(self, row: int, column: int) -> str:
        item = self.table.item(row, column)
        return item.text().strip() if item else ""
