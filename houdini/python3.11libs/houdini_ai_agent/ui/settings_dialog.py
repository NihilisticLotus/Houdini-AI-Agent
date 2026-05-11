"""Provider and vision backend settings dialog."""

from __future__ import annotations

from typing import List

from houdini_ai_agent.core.config import (
    ProviderConfig,
    VisionBackendConfig,
    discover_external_configs,
    provider_model_allows_vision,
    save_runtime_settings,
)
from houdini_ai_agent.core.session import THINKING_LEVELS
from houdini_ai_agent.qt import QtCore, QtWidgets


class SettingsDialog(QtWidgets.QDialog):
    settings_saved = QtCore.Signal(list, object)

    COLUMNS = ["名称", "Base URL", "API Key / 环境变量", "模型", "推理", "视觉", "自动兜底", "默认思考"]

    def __init__(self, providers: List[ProviderConfig], vision_backend: VisionBackendConfig, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Houdini AI Agent 设置")
        self.resize(900, 620)
        self.providers = [p for p in providers]
        self.vision_backend = vision_backend
        self._build_ui()
        self._populate()

    def _build_ui(self) -> None:
        root = QtWidgets.QVBoxLayout(self)
        root.setSpacing(10)

        intro = QtWidgets.QLabel(
            "配置聊天模型和独立的视觉后端。主模型可以是纯文本模型，图片理解可以交给另一个多模态 provider。"
        )
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

        vision_group = QtWidgets.QGroupBox("视觉后端")
        vision_layout = QtWidgets.QFormLayout(vision_group)
        self.vision_mode_combo = QtWidgets.QComboBox()
        self.vision_mode_combo.addItem("自动（不使用 Codex）", "auto")
        self.vision_mode_combo.addItem("禁用", "disabled")
        self.vision_mode_combo.addItem("指定 Provider", "provider")
        self.vision_mode_combo.addItem("Codex Local（显式启用）", "codex")
        self.vision_mode_combo.addItem("MCP（预留）", "mcp")
        self.vision_mode_combo.addItem("Skill（预留）", "skill")
        self.vision_mode_combo.currentIndexChanged.connect(self._update_vision_backend_ui)

        self.vision_target_combo = QtWidgets.QComboBox()
        self.vision_target_combo.setEditable(True)

        self.vision_hint = QtWidgets.QLabel("")
        self.vision_hint.setWordWrap(True)

        vision_layout.addRow("模式", self.vision_mode_combo)
        vision_layout.addRow("目标", self.vision_target_combo)
        vision_layout.addRow("说明", self.vision_hint)
        root.addWidget(vision_group)

        external_group = QtWidgets.QGroupBox("外部配置发现")
        external_layout = QtWidgets.QVBoxLayout(external_group)
        self.external_list = QtWidgets.QListWidget()
        external_layout.addWidget(self.external_list)
        root.addWidget(external_group)

        dialog_buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Save | QtWidgets.QDialogButtonBox.Cancel)
        save_button = dialog_buttons.button(QtWidgets.QDialogButtonBox.Save)
        cancel_button = dialog_buttons.button(QtWidgets.QDialogButtonBox.Cancel)
        if save_button is not None:
            save_button.setText("保存")
        if cancel_button is not None:
            cancel_button.setText("取消")
        dialog_buttons.accepted.connect(self._save)
        dialog_buttons.rejected.connect(self.reject)
        root.addWidget(dialog_buttons)

    def _populate(self) -> None:
        for provider in self.providers:
            self._append_provider_row(provider)
        self._populate_vision_backend_targets()
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
        vision.setChecked(provider_model_allows_vision(provider))
        vision.setToolTip("勾选后表示该 provider 可以直接读取图片。")
        self.table.setCellWidget(row, 5, vision)

        fallback = QtWidgets.QCheckBox()
        fallback.setChecked(provider.use_as_vision_fallback)
        fallback.setToolTip("仅在自动模式下作为优先提示；Codex Local 不会被自动模式隐式选中。")
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
            state = "已找到" if hint.found else "未找到"
            model = f" model={hint.model}" if hint.model else ""
            provider = f" provider={hint.provider}" if hint.provider else ""
            self.external_list.addItem(f"{hint.source}: {state} | {hint.path}{model}{provider} | {hint.note}")

    def _populate_vision_backend_targets(self) -> None:
        provider_names = [
            provider.name
            for provider in self.providers
            if provider.source != "mock" and provider.source != "codex" and provider_model_allows_vision(provider)
        ]
        self.vision_target_combo.blockSignals(True)
        self.vision_target_combo.clear()
        self.vision_target_combo.addItem("")
        for name in provider_names:
            self.vision_target_combo.addItem(name)

        mode = self.vision_backend.normalized_mode()
        mode_index = self.vision_mode_combo.findData(mode)
        self.vision_mode_combo.setCurrentIndex(mode_index if mode_index >= 0 else 0)
        if self.vision_backend.target:
            target_index = self.vision_target_combo.findText(self.vision_backend.target)
            if target_index < 0:
                self.vision_target_combo.addItem(self.vision_backend.target)
                target_index = self.vision_target_combo.findText(self.vision_backend.target)
            self.vision_target_combo.setCurrentIndex(target_index)
        self.vision_target_combo.blockSignals(False)
        self._update_vision_backend_ui()

    def _update_vision_backend_ui(self) -> None:
        mode = str(self.vision_mode_combo.currentData() or "auto")
        self.vision_target_combo.setEnabled(mode not in {"auto", "disabled", "codex"})
        self.vision_target_combo.setEditable(mode in {"provider", "mcp", "skill"})
        if mode == "auto":
            text = "自动模式只会选择非 Codex 的视觉 provider；如需使用 Codex 读图，请显式选择 Codex Local。"
        elif mode == "disabled":
            text = "插件仍可正常聊天，但纯文本模型不会获得图片理解结果。"
        elif mode == "provider":
            text = "指定一个多模态 provider 专门读图，主聊天模型可以继续使用 glm-5.1 等文本模型。"
        elif mode == "codex":
            text = "显式使用本机 Codex 作为读图 companion。只有这个模式会调用 Codex 读图。"
        elif mode == "mcp":
            text = "预留给后续 MCP 视觉后端。当前版本不会执行 MCP 读图。"
        else:
            text = "预留给后续本地 Skill 视觉后端。当前版本不会执行 Skill 读图。"
        self.vision_hint.setText(text)

    def _add_blank_provider(self) -> None:
        self._append_provider_row(ProviderConfig(name="New Provider", source="custom"))
        self._populate_vision_backend_targets()

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
        self._populate_vision_backend_targets()

    def _remove_selected(self) -> None:
        rows = sorted({index.row() for index in self.table.selectedIndexes()}, reverse=True)
        for row in rows:
            name_item = self.table.item(row, 0)
            if name_item and name_item.text() == "Mock Preview":
                continue
            self.table.removeRow(row)
        self._populate_vision_backend_targets()

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
            base_url = self._text(row, 1)
            if name == "Mock Preview":
                source = "mock"
            elif name == "Codex Local" or base_url == "codex://local-cli":
                source = "codex"
            else:
                source = "custom"
            providers.append(
                ProviderConfig(
                    name=name,
                    base_url=base_url,
                    api_key_env=self._text(row, 2),
                    model=self._text(row, 3),
                    supports_reasoning=bool(reasoning.isChecked()) if reasoning else True,
                    supports_vision=bool(vision.isChecked()) if vision else False,
                    use_as_vision_fallback=bool(fallback.isChecked()) if fallback else False,
                    default_thinking_level=thinking.currentText() if thinking else "中",
                    source=source,
                )
            )

        vision_backend = VisionBackendConfig(
            mode=str(self.vision_mode_combo.currentData() or "auto"),
            target=self.vision_target_combo.currentText().strip(),
        )
        save_runtime_settings(providers, vision_backend)
        self.settings_saved.emit(providers, vision_backend)
        self.accept()

    def _text(self, row: int, column: int) -> str:
        item = self.table.item(row, column)
        return item.text().strip() if item else ""
