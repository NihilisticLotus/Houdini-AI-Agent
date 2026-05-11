"""Main Houdini AI Agent panel."""

from __future__ import annotations

from houdini_ai_agent.adapters.houdini import create_best_adapter
from houdini_ai_agent.core.config import CODEX_MODELS, looks_like_direct_key
from houdini_ai_agent.core.session import AgentSession, THINKING_LEVELS
from houdini_ai_agent.ui.chat_view import ChatView
from houdini_ai_agent.ui.context_panel import ContextPanel, ExecutionTrace
from houdini_ai_agent.ui.settings_dialog import SettingsDialog
from houdini_ai_agent.ui.style import STYLE
from houdini_ai_agent.qt import QtCore, QtWidgets


class AgentMainPanel(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("HoudiniAIAgentPanel")
        self.setWindowTitle("Houdini AI Agent")
        self.setStyleSheet(STYLE)
        self.setAutoFillBackground(True)
        self.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
        self._syncing_conversations = False
        self._conversation_filter = ""
        self._left_sidebar_visible = True
        self._right_sidebar_visible = True
        self._left_sidebar_width = 210
        self._right_sidebar_width = 310
        self._focus_mode = False
        self._trace_visible_before_focus = True

        self.session = AgentSession(create_best_adapter(), self)
        self._build_ui()
        self._wire()
        self._populate_provider_combo()
        self._refresh_conversation_list()
        self.chat.load_conversation(self.session.current_conversation)
        self._set_storage_status(self.session.storage_status)
        self.session.refresh_context()

    def _build_ui(self) -> None:
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        root.addWidget(self._build_header())
        root.addWidget(self._build_action_bar())

        self.main_splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        self.left_sidebar = self._build_session_sidebar()
        self.center_workspace = self._build_center_workspace()
        self.context_panel = ContextPanel()
        self.context_panel.setMinimumWidth(290)

        self.main_splitter.addWidget(self.left_sidebar)
        self.main_splitter.addWidget(self.center_workspace)
        self.main_splitter.addWidget(self.context_panel)
        self.main_splitter.setSizes([210, 780, 310])
        self.main_splitter.setStretchFactor(0, 0)
        self.main_splitter.setStretchFactor(1, 1)
        self.main_splitter.setStretchFactor(2, 0)
        self.main_splitter.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)

        focus_row = QtWidgets.QHBoxLayout()
        focus_row.setContentsMargins(0, 0, 0, 0)
        focus_row.setSpacing(6)
        self.left_toggle_btn = QtWidgets.QPushButton("◀")
        self.left_toggle_btn.setObjectName("SidebarToggle")
        self.left_toggle_btn.setFixedWidth(24)
        self.left_toggle_btn.clicked.connect(self._toggle_left_sidebar)
        self.right_toggle_btn = QtWidgets.QPushButton("▶")
        self.right_toggle_btn.setObjectName("SidebarToggle")
        self.right_toggle_btn.setFixedWidth(24)
        self.right_toggle_btn.clicked.connect(self._toggle_right_sidebar)
        focus_row.addWidget(self.left_toggle_btn)
        focus_row.addWidget(self.main_splitter, 1)
        focus_row.addWidget(self.right_toggle_btn)
        focus_widget = QtWidgets.QWidget()
        focus_widget.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
        focus_widget.setLayout(focus_row)
        root.addWidget(focus_widget, 1)

    def _build_header(self) -> QtWidgets.QWidget:
        header_widget = QtWidgets.QFrame()
        header_widget.setObjectName("HeaderBar")
        header = QtWidgets.QHBoxLayout(header_widget)
        header.setContentsMargins(12, 10, 12, 10)
        header.setSpacing(10)

        title_col = QtWidgets.QVBoxLayout()
        title_col.setContentsMargins(0, 0, 0, 0)
        title_col.setSpacing(2)

        title = QtWidgets.QLabel("Houdini AI Agent")
        title.setObjectName("AppTitle")
        subtitle = QtWidgets.QLabel("会话式工程助手，支持图片、自动保存和工程上下文读取")
        subtitle.setObjectName("HintText")
        self.adapter_label = QtWidgets.QLabel("")
        self.adapter_label.setObjectName("HintText")

        title_col.addWidget(title)
        title_col.addWidget(subtitle)

        status_col = QtWidgets.QVBoxLayout()
        status_col.setContentsMargins(0, 0, 0, 0)
        status_col.setSpacing(3)
        status_col.addWidget(self.adapter_label)

        settings_btn = QtWidgets.QPushButton("设置")
        settings_btn.setFixedWidth(72)
        settings_btn.clicked.connect(self._open_settings)
        self.focus_mode_btn = QtWidgets.QPushButton("专注模式")
        self.focus_mode_btn.setFixedWidth(84)
        self.focus_mode_btn.clicked.connect(self._toggle_focus_mode)

        header.addLayout(title_col)
        header.addStretch(1)
        header.addLayout(status_col)
        header.addWidget(self.focus_mode_btn)
        header.addWidget(settings_btn)
        header_widget.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        header_widget.setMaximumHeight(74)
        return header_widget

    def _build_action_bar(self) -> QtWidgets.QWidget:
        bar = QtWidgets.QFrame()
        bar.setObjectName("ActionBar")
        actions = QtWidgets.QHBoxLayout(bar)
        actions.setContentsMargins(6, 0, 6, 0)
        actions.setSpacing(8)
        self._add_action_button(actions, "分析工程", "analyze_scene")
        self._add_action_button(actions, "查看选中节点", "inspect_selection")
        self._add_action_button(actions, "创建节点", "create_nodes")
        self._add_action_button(actions, "修复错误", "fix_error")
        self._add_action_button(actions, "捕获视口", "capture_viewport")
        actions.addStretch(1)
        bar.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        bar.setMaximumHeight(42)
        return bar

    def _build_session_sidebar(self) -> QtWidgets.QWidget:
        sidebar = QtWidgets.QFrame()
        sidebar.setObjectName("SessionSidebar")
        sidebar.setMinimumWidth(210)
        sidebar.setMaximumWidth(280)
        sidebar.setSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Expanding)
        layout = QtWidgets.QVBoxLayout(sidebar)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        row = QtWidgets.QHBoxLayout()
        title = QtWidgets.QLabel("会话")
        title.setObjectName("PanelTitle")
        new_btn = QtWidgets.QPushButton("新建")
        new_btn.setFixedWidth(50)
        new_btn.clicked.connect(lambda: self.session.create_conversation("新会话"))
        import_btn = QtWidgets.QPushButton("导入")
        import_btn.setFixedWidth(50)
        import_btn.clicked.connect(self._import_conversations)
        export_btn = QtWidgets.QPushButton("导出")
        export_btn.setFixedWidth(50)
        export_btn.clicked.connect(lambda: self._export_conversation(self.session.current_conversation_id))
        row.addWidget(title)
        row.addStretch(1)
        row.addWidget(new_btn)
        row.addWidget(import_btn)
        row.addWidget(export_btn)

        self.conversation_search = QtWidgets.QLineEdit()
        self.conversation_search.setPlaceholderText("搜索会话")
        self.conversation_search.textChanged.connect(self._filter_conversations)

        self.conversation_list = QtWidgets.QListWidget()
        self.conversation_list.setObjectName("ConversationList")
        self.conversation_list.currentItemChanged.connect(self._conversation_item_changed)
        self.conversation_list.itemDoubleClicked.connect(self._rename_conversation_item)
        self.conversation_list.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.conversation_list.customContextMenuRequested.connect(self._show_conversation_menu)

        self.storage_status_label = QtWidgets.QLabel("")
        self.storage_status_label.setObjectName("HintText")
        self.storage_status_label.setWordWrap(True)

        layout.addLayout(row)
        layout.addWidget(self.conversation_search)
        layout.addWidget(self.conversation_list, 1)
        layout.addWidget(self.storage_status_label)
        return sidebar

    def _build_center_workspace(self) -> QtWidgets.QWidget:
        center = QtWidgets.QFrame()
        center.setObjectName("CenterWorkspace")
        center.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
        layout = QtWidgets.QVBoxLayout(center)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        self.chat = ChatView()
        self.chat.setObjectName("ChatSurface")
        self.chat.set_image_path_preprocessor(self.session.materialize_current_image_paths)
        layout.addWidget(self.chat, 1)

        layout.addWidget(self._build_composer_controls())

        self.trace = ExecutionTrace()
        self.trace.setMinimumHeight(150)
        self.trace.setMaximumHeight(190)
        self.trace.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        layout.addWidget(self.trace)
        return center

    def _build_composer_controls(self) -> QtWidgets.QWidget:
        bar = QtWidgets.QFrame()
        bar.setObjectName("ComposerBar")
        layout = QtWidgets.QHBoxLayout(bar)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(10)

        left = QtWidgets.QHBoxLayout()
        left.setContentsMargins(0, 0, 0, 0)
        left.setSpacing(8)
        left.addWidget(QtWidgets.QLabel("模型"))
        self.provider_combo = QtWidgets.QComboBox()
        self.provider_combo.setMinimumWidth(150)
        left.addWidget(self.provider_combo)
        self.model_combo = QtWidgets.QComboBox()
        self.model_combo.setEditable(True)
        self.model_combo.setMinimumWidth(170)
        left.addWidget(self.model_combo)
        self.provider_status = QtWidgets.QLabel("")
        self.provider_status.setMinimumWidth(84)
        self.provider_status.setObjectName("StatusPill")
        left.addWidget(self.provider_status)

        left.addSpacing(10)
        left.addWidget(QtWidgets.QLabel("思考"))
        self.thinking_combo = QtWidgets.QComboBox()
        self.thinking_combo.addItems(list(THINKING_LEVELS.keys()))
        self.thinking_combo.setCurrentText("中")
        self.thinking_combo.setMinimumWidth(74)
        left.addWidget(self.thinking_combo)

        self.thinking_hint = QtWidgets.QLabel(THINKING_LEVELS["中"]["description"])
        self.thinking_hint.setObjectName("HintText")
        left.addWidget(self.thinking_hint, 1)

        self.clear_messages_btn = QtWidgets.QPushButton("清空消息")
        self.clear_messages_btn.setFixedWidth(78)
        self.clear_messages_btn.clicked.connect(self._clear_current_conversation_messages)

        layout.addLayout(left, 1)
        layout.addWidget(self.clear_messages_btn)
        bar.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        bar.setMaximumHeight(48)
        return bar

    def _wire(self) -> None:
        self.chat.send_requested.connect(self.session.send_message)
        self.chat.stop_requested.connect(self.session.stop)
        self.chat.delete_message_requested.connect(self._delete_single_message)
        self.context_panel.refresh_requested.connect(self.session.refresh_context)

        self.session.message_added.connect(self.chat.add_message)
        self.session.event_added.connect(self.trace.add_event)
        self.session.context_changed.connect(self.context_panel.set_context)
        self.session.providers_changed.connect(self._providers_changed)
        self.session.busy_changed.connect(self.chat.set_busy)
        self.session.busy_changed.connect(self._set_actions_busy)
        self.session.conversations_changed.connect(self._refresh_conversation_list)
        self.session.conversation_changed.connect(self._load_conversation)
        self.session.storage_status_changed.connect(self._set_storage_status)

        self.provider_combo.currentIndexChanged.connect(self._provider_changed)
        self.model_combo.currentTextChanged.connect(self._model_changed)
        self.thinking_combo.currentTextChanged.connect(self._thinking_changed)

    def _add_action_button(self, layout, label: str, action: str) -> None:
        button = QtWidgets.QPushButton(label)
        button.setProperty("agent_action", action)
        button.clicked.connect(lambda checked=False, name=action: self.session.run_action(name))
        layout.addWidget(button)

    def _refresh_conversation_list(self) -> None:
        if not hasattr(self, "conversation_list"):
            return
        self._syncing_conversations = True
        self.conversation_list.clear()
        current_row = 0
        visible_row = 0
        for conversation in self.session.conversations:
            if self._conversation_filter and self._conversation_filter not in conversation.title.lower():
                continue
            suffix = f" · {len(conversation.messages)}条" if conversation.messages else ""
            item = QtWidgets.QListWidgetItem(f"{conversation.title}{suffix}")
            item.setData(QtCore.Qt.UserRole, conversation.id)
            item.setToolTip(f"Created at {conversation.created_at}")
            self.conversation_list.addItem(item)
            if conversation.id == self.session.current_conversation_id:
                current_row = visible_row
            visible_row += 1
        if self.conversation_list.count():
            self.conversation_list.setCurrentRow(current_row)
        self._syncing_conversations = False

    def _filter_conversations(self, text: str) -> None:
        self._conversation_filter = text.strip().lower()
        self._refresh_conversation_list()

    def _conversation_item_changed(self, current, previous) -> None:
        if self._syncing_conversations or current is None:
            return
        conversation_id = current.data(QtCore.Qt.UserRole)
        if conversation_id:
            self.session.switch_conversation(conversation_id)

    def _show_conversation_menu(self, pos) -> None:
        item = self.conversation_list.itemAt(pos)
        if item is None:
            return
        conversation_id = item.data(QtCore.Qt.UserRole)
        menu = QtWidgets.QMenu(self)
        rename_action = menu.addAction("重命名")
        export_action = menu.addAction("导出")
        clear_action = menu.addAction("清空消息")
        delete_action = menu.addAction("删除会话")
        action = menu.exec_(self.conversation_list.mapToGlobal(pos))
        if action == rename_action:
            self._rename_conversation_item(item)
        elif action == export_action:
            self._export_conversation(conversation_id)
        elif action == clear_action:
            self._clear_conversation_messages(conversation_id)
        elif action == delete_action:
            self._delete_conversation(conversation_id)

    def _rename_conversation_item(self, item) -> None:
        conversation_id = item.data(QtCore.Qt.UserRole)
        if not conversation_id:
            return
        current_title = self._conversation_title_by_id(conversation_id)
        new_title, ok = QtWidgets.QInputDialog.getText(self, "重命名会话", "会话名称", text=current_title)
        if ok:
            self.session.rename_conversation(conversation_id, new_title)

    def _import_conversations(self) -> None:
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            "导入会话记录",
            "",
            "Agent Session (*.json);;All Files (*)",
        )
        if not path:
            return
        count = self.session.import_conversations_from_file(path)
        QtWidgets.QMessageBox.information(self, "导入会话记录", f"已导入 {count} 个会话。")

    def _export_conversation(self, conversation_id: str) -> None:
        title = self._conversation_title_by_id(conversation_id) or "houdini_agent_session"
        safe_title = "".join(ch if ch.isalnum() or ch in (" ", "-", "_") else "_" for ch in title).strip() or "houdini_agent_session"
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self,
            "导出会话记录",
            f"{safe_title}.json",
            "Agent Session (*.json);;All Files (*)",
        )
        if not path:
            return
        exported = self.session.export_conversation_to_file(conversation_id, path)
        if exported:
            QtWidgets.QMessageBox.information(self, "导出会话记录", f"已导出：{exported}")

    def _delete_conversation(self, conversation_id: str) -> None:
        title = self._conversation_title_by_id(conversation_id)
        if not title:
            return
        answer = QtWidgets.QMessageBox.question(
            self,
            "删除会话",
            f"确定删除会话「{title}」吗？\n对应的自动保存文件和 Agent/images 下的会话图片也会被清理。",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            QtWidgets.QMessageBox.No,
        )
        if answer != QtWidgets.QMessageBox.Yes:
            return
        if not self.session.delete_conversation(conversation_id):
            QtWidgets.QMessageBox.information(self, "删除会话", "至少需要保留一个会话。")

    def _clear_current_conversation_messages(self) -> None:
        self._clear_conversation_messages(self.session.current_conversation_id)

    def _clear_conversation_messages(self, conversation_id: str) -> None:
        title = self._conversation_title_by_id(conversation_id)
        if not title:
            return
        answer = QtWidgets.QMessageBox.question(
            self,
            "清空全部消息",
            f"确定清空会话「{title}」里的全部消息和执行轨迹吗？\n会话本身会保留。",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            QtWidgets.QMessageBox.No,
        )
        if answer != QtWidgets.QMessageBox.Yes:
            return
        self.session.clear_conversation_history(conversation_id)

    def _delete_single_message(self, message_index: int) -> None:
        title = self._conversation_title_by_id(self.session.current_conversation_id)
        answer = QtWidgets.QMessageBox.question(
            self,
            "删除消息",
            f"确定删除会话「{title}」中的这条消息吗？",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            QtWidgets.QMessageBox.No,
        )
        if answer != QtWidgets.QMessageBox.Yes:
            return
        self.session.delete_message(self.session.current_conversation_id, message_index)

    def _set_storage_status(self, text: str) -> None:
        if hasattr(self, "storage_status_label"):
            self.storage_status_label.setText(text)

    def _toggle_left_sidebar(self) -> None:
        sizes = self.main_splitter.sizes()
        if self._left_sidebar_visible:
            self._left_sidebar_width = max(160, sizes[0])
            self.left_sidebar.hide()
            self.main_splitter.setSizes([0, sizes[1] + sizes[0], sizes[2]])
            self.left_toggle_btn.setText("▶")
            self._left_sidebar_visible = False
        else:
            self.left_sidebar.show()
            total = sum(self.main_splitter.sizes()) or 1200
            right = self.main_splitter.sizes()[2]
            center = max(420, total - self._left_sidebar_width - right)
            self.main_splitter.setSizes([self._left_sidebar_width, center, right])
            self.left_toggle_btn.setText("◀")
            self._left_sidebar_visible = True

    def _toggle_right_sidebar(self) -> None:
        sizes = self.main_splitter.sizes()
        if self._right_sidebar_visible:
            self._right_sidebar_width = max(240, sizes[2])
            self.context_panel.hide()
            self.main_splitter.setSizes([sizes[0], sizes[1] + sizes[2], 0])
            self.right_toggle_btn.setText("◀")
            self._right_sidebar_visible = False
        else:
            self.context_panel.show()
            total = sum(self.main_splitter.sizes()) or 1200
            left = self.main_splitter.sizes()[0]
            center = max(420, total - left - self._right_sidebar_width)
            self.main_splitter.setSizes([left, center, self._right_sidebar_width])
            self.right_toggle_btn.setText("▶")
            self._right_sidebar_visible = True

    def _toggle_focus_mode(self) -> None:
        self._focus_mode = not self._focus_mode
        if self._focus_mode:
            self._trace_visible_before_focus = self.trace.isVisible()
            if self._left_sidebar_visible:
                self._toggle_left_sidebar()
            if self._right_sidebar_visible:
                self._toggle_right_sidebar()
            self.trace.hide()
            self.focus_mode_btn.setText("退出专注")
        else:
            if not self._left_sidebar_visible:
                self._toggle_left_sidebar()
            if not self._right_sidebar_visible:
                self._toggle_right_sidebar()
            if self._trace_visible_before_focus:
                self.trace.show()
            self.focus_mode_btn.setText("专注模式")

    def _conversation_title_by_id(self, conversation_id: str) -> str:
        for conversation in self.session.conversations:
            if conversation.id == conversation_id:
                return conversation.title
        return ""

    def _load_conversation(self, conversation) -> None:
        if hasattr(self, "chat"):
            self.chat.load_conversation(conversation)
        if hasattr(self, "trace"):
            self.trace.clear()
            for event in conversation.events:
                self.trace.add_event(event)
        self._refresh_conversation_list()

    def _populate_provider_combo(self) -> None:
        self.provider_combo.blockSignals(True)
        self.provider_combo.clear()
        for provider in self.session.providers:
            self.provider_combo.addItem(provider.name, provider)
        self.provider_combo.setCurrentIndex(self.session.current_provider_index)
        self.provider_combo.blockSignals(False)
        self._populate_model_combo()
        self._update_provider_status()
        self.adapter_label.setText(f"Adapter: {self.session.adapter.name}")

    def _providers_changed(self, providers) -> None:
        self._populate_provider_combo()

    def _provider_changed(self, index: int) -> None:
        self.session.set_provider_index(index)
        self._populate_model_combo()
        self._update_provider_status()

    def _populate_model_combo(self) -> None:
        if not hasattr(self, "model_combo"):
            return
        provider = self.session.current_provider
        self.model_combo.blockSignals(True)
        self.model_combo.clear()
        if provider.source == "codex":
            values = []
            for label, value, description in CODEX_MODELS:
                self.model_combo.addItem(label, value)
                self.model_combo.setItemData(self.model_combo.count() - 1, description, QtCore.Qt.ToolTipRole)
                values.append(value)
            if provider.model not in values and provider.model:
                self.model_combo.addItem(provider.model, provider.model)
            index = values.index(provider.model) if provider.model in values else self.model_combo.findData(provider.model)
            self.model_combo.setCurrentIndex(index if index >= 0 else 0)
        else:
            self.model_combo.addItem(provider.model or "", provider.model or "")
            self.model_combo.setCurrentText(provider.model or "")
        self.model_combo.blockSignals(False)

    def _model_changed(self, text: str) -> None:
        if not text:
            return
        data = self.model_combo.currentData()
        model = str(data or text).strip()
        if model:
            self.session.set_current_model(model)
        self._update_provider_status()

    def _thinking_changed(self, level: str) -> None:
        self.session.set_thinking_level(level)
        self.thinking_hint.setText(THINKING_LEVELS[level]["description"])

    def _update_provider_status(self) -> None:
        provider = self.session.current_provider
        self.provider_status.setText(provider.status_text)
        if provider.source == "codex" and not provider.has_key:
            self.provider_status.setToolTip("未检测到 Codex 本地登录状态。请先在这台机器上登录 Codex。")
        elif provider.source == "codex":
            self.provider_status.setToolTip("使用本机已登录的 Codex CLI，不需要单独填写 OpenAI API key。")
        elif provider.source != "mock" and not provider.has_key:
            self.provider_status.setToolTip(
                f"请在启动 Houdini 前设置环境变量 {provider.api_key_env}，"
                "或者先切回 Mock Preview。"
            )
        elif provider.source != "mock" and looks_like_direct_key(provider.api_key_env):
            self.provider_status.setToolTip("Using the direct API key saved in provider settings.")
        else:
            self.provider_status.setToolTip("")

    def _open_settings(self) -> None:
        dialog = SettingsDialog(self.session.providers, self)
        dialog.providers_saved.connect(self.session.set_providers)
        dialog.exec_()

    def _set_actions_busy(self, busy: bool) -> None:
        for button in self.findChildren(QtWidgets.QPushButton):
            if button.property("agent_action"):
                button.setEnabled(not busy)
        if hasattr(self, "clear_messages_btn"):
            self.clear_messages_btn.setEnabled(not busy)


def create_panel():
    return AgentMainPanel()
