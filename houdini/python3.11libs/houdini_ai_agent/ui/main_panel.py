"""Main Houdini AI Agent panel."""

from __future__ import annotations

from houdini_ai_agent.adapters.houdini import create_best_adapter
from houdini_ai_agent.core.config import CODEX_MODELS, looks_like_direct_key
from houdini_ai_agent.core.session import AgentSession, THINKING_LEVELS
from houdini_ai_agent.core.tool_registry import WORK_MODE_ORDER, WORK_MODES
from houdini_ai_agent.ui.chat_view import ChatView
from houdini_ai_agent.ui.context_panel import ContextPanel, ExecutionTrace
from houdini_ai_agent.ui.settings_dialog import SettingsDialog
from houdini_ai_agent.ui.style import build_style, scaled
from houdini_ai_agent.qt import QtCore, QtWidgets


class AgentMainPanel(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("HoudiniAIAgentPanel")
        self.setWindowTitle("Houdini AI Agent")
        self.setStyleSheet(build_style())
        self.setAutoFillBackground(True)
        self.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
        self._syncing_conversations = False
        self._right_sidebar_visible = True
        self._right_sidebar_width = scaled(292)
        self._focus_mode = False
        self._trace_visible_before_focus = True
        self._action_buttons = {}

        self.session = AgentSession(create_best_adapter(), self)
        self._build_ui()
        self._apply_ui_language()
        self._wire()
        self._populate_provider_combo()
        self._refresh_conversation_list()
        self.chat.load_conversation(self.session.current_conversation)
        self._update_context_usage()
        self._set_storage_status(self.session.storage_status)
        self.session.refresh_context()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._position_right_toggle()

    def _build_ui(self) -> None:
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(scaled(1))

        root.addWidget(self._build_header())
        root.addWidget(self._build_action_bar())

        self.main_splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        self.center_workspace = self._build_center_workspace()
        self.context_panel = ContextPanel()
        self.context_panel.setObjectName("ContextPanel")
        self.context_panel.setMinimumWidth(scaled(280))

        self.main_splitter.addWidget(self.center_workspace)
        self.main_splitter.addWidget(self.context_panel)
        self.main_splitter.setSizes([scaled(1016), scaled(292)])
        self.main_splitter.setStretchFactor(0, 1)
        self.main_splitter.setStretchFactor(1, 0)
        self.main_splitter.setChildrenCollapsible(False)
        self.main_splitter.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)

        focus_widget = QtWidgets.QWidget()
        self.focus_widget = focus_widget
        focus_widget.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
        focus_layout = QtWidgets.QHBoxLayout(focus_widget)
        focus_layout.setContentsMargins(0, 0, 0, 0)
        focus_layout.setSpacing(0)
        focus_layout.addWidget(self.main_splitter, 1)

        self.right_toggle_btn = QtWidgets.QPushButton(">", focus_widget)
        self.right_toggle_btn.setObjectName("SidebarToggle")
        self.right_toggle_btn.setFixedSize(scaled(8), scaled(54))
        self.right_toggle_btn.clicked.connect(self._toggle_right_sidebar)
        self.right_toggle_btn.raise_()

        self.main_splitter.splitterMoved.connect(lambda *_args: self._position_right_toggle())
        root.addWidget(focus_widget, 1)
        QtCore.QTimer.singleShot(0, self._position_right_toggle)

    def _build_header(self) -> QtWidgets.QWidget:
        header_widget = QtWidgets.QFrame()
        header_widget.setObjectName("HeaderBar")
        header = QtWidgets.QHBoxLayout(header_widget)
        header.setContentsMargins(scaled(8), scaled(4), scaled(8), scaled(4))
        header.setSpacing(scaled(8))

        title_col = QtWidgets.QVBoxLayout()
        title_col.setContentsMargins(0, 0, 0, 0)
        title_col.setSpacing(scaled(2))

        title = QtWidgets.QLabel("Houdini AI Agent")
        title.setObjectName("AppTitle")
        subtitle = QtWidgets.QLabel("会话式工程助手，支持图片、自动保存和工程上下文读取")
        subtitle.setObjectName("HintText")
        subtitle.hide()
        self.adapter_label = QtWidgets.QLabel("")
        self.adapter_label.setObjectName("HintText")

        title_col.addWidget(title)
        title_col.addWidget(subtitle)

        status_col = QtWidgets.QVBoxLayout()
        status_col.setContentsMargins(0, 0, 0, 0)
        status_col.setSpacing(scaled(3))
        status_col.addWidget(self.adapter_label)

        settings_btn = QtWidgets.QPushButton("设置")
        settings_btn.setFixedWidth(scaled(68))
        settings_btn.clicked.connect(self._open_settings)
        self.focus_mode_btn = QtWidgets.QPushButton("专注模式")
        self.focus_mode_btn.setFixedWidth(scaled(80))
        self.focus_mode_btn.clicked.connect(self._toggle_focus_mode)

        header.addLayout(title_col)
        header.addStretch(1)
        header.addLayout(status_col)
        self.language_btn = QtWidgets.QPushButton("")
        self.language_btn.setFixedWidth(scaled(70))
        self.language_btn.clicked.connect(self._toggle_ui_language)
        header.addWidget(self.language_btn)
        header.addWidget(self.focus_mode_btn)
        header.addWidget(settings_btn)
        header_widget.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        header_widget.setMaximumHeight(scaled(42))
        return header_widget

    def _build_action_bar(self) -> QtWidgets.QWidget:
        bar = QtWidgets.QFrame()
        bar.setObjectName("ActionBar")
        actions = QtWidgets.QHBoxLayout(bar)
        actions.setContentsMargins(scaled(8), 0, scaled(8), 0)
        actions.setSpacing(scaled(6))
        self._add_action_button(actions, "分析工程", "analyze_scene")
        self._add_action_button(actions, "查看选中节点", "inspect_selection")
        self._add_action_button(actions, "创建节点", "create_nodes")
        self._add_action_button(actions, "修复错误", "fix_error")
        self._add_action_button(actions, "捕获视口", "capture_viewport")
        actions.addStretch(1)
        bar.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        bar.setMaximumHeight(scaled(32))
        return bar

    def _build_center_workspace(self) -> QtWidgets.QWidget:
        center = QtWidgets.QFrame()
        center.setObjectName("CenterWorkspace")
        center.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
        layout = QtWidgets.QVBoxLayout(center)
        layout.setContentsMargins(scaled(4), scaled(4), scaled(4), scaled(4))
        layout.setSpacing(scaled(6))

        self.chat = ChatView()
        self.chat.setObjectName("ChatSurface")
        self.chat.set_image_path_preprocessor(self.session.materialize_current_image_paths)

        layout.addWidget(self._build_conversation_tab_bar())
        layout.addWidget(self.chat, 1)
        layout.addWidget(self._build_composer_controls())

        self.trace = ExecutionTrace()
        self.trace.setObjectName("ExecutionTrace")
        self.trace.setMinimumHeight(scaled(88))
        self.trace.setMaximumHeight(scaled(118))
        self.trace.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        layout.addWidget(self.trace)
        return center

    def _build_conversation_tab_bar(self) -> QtWidgets.QWidget:
        bar = QtWidgets.QFrame()
        bar.setObjectName("ConversationTabsBar")
        layout = QtWidgets.QHBoxLayout(bar)
        layout.setContentsMargins(scaled(2), 0, scaled(2), 0)
        layout.setSpacing(scaled(4))

        self.conversation_tabs = QtWidgets.QTabBar()
        self.conversation_tabs.setObjectName("ConversationTabBar")
        self.conversation_tabs.setExpanding(False)
        self.conversation_tabs.setUsesScrollButtons(True)
        self.conversation_tabs.setElideMode(QtCore.Qt.ElideRight)
        self.conversation_tabs.setDrawBase(False)
        self.conversation_tabs.setFixedHeight(scaled(18))
        self.conversation_tabs.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.conversation_tabs.currentChanged.connect(self._conversation_tab_changed)
        self.conversation_tabs.tabBarDoubleClicked.connect(self._rename_conversation_tab)
        self.conversation_tabs.customContextMenuRequested.connect(self._show_conversation_tab_menu)

        new_tab_btn = QtWidgets.QPushButton("+")
        new_tab_btn.setObjectName("TabAddButton")
        new_tab_btn.setFixedSize(scaled(18), scaled(16))
        new_tab_btn.setToolTip("新建会话")
        new_tab_btn.clicked.connect(lambda: self.session.create_conversation("新会话"))

        layout.addWidget(self.conversation_tabs, 0)
        layout.addStretch(1)
        layout.addWidget(new_tab_btn)
        bar.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        bar.setFixedHeight(scaled(20))
        return bar

    def _build_composer_controls(self) -> QtWidgets.QWidget:
        bar = QtWidgets.QFrame()
        bar.setObjectName("ComposerBar")
        layout = QtWidgets.QHBoxLayout(bar)
        layout.setContentsMargins(scaled(8), scaled(6), scaled(8), scaled(6))
        layout.setSpacing(scaled(8))

        left = QtWidgets.QHBoxLayout()
        left.setContentsMargins(0, 0, 0, 0)
        left.setSpacing(scaled(8))

        self.context_usage_label = QtWidgets.QLabel("上下文 0%")
        self.context_usage_label.setObjectName("ContextUsageChip")
        self.context_usage_label.setMinimumWidth(scaled(82))
        left.addWidget(self.context_usage_label)

        left.addWidget(QtWidgets.QLabel("模型"))
        self.provider_combo = QtWidgets.QComboBox()
        self.provider_combo.setMinimumWidth(scaled(140))
        left.addWidget(self.provider_combo)
        self.model_combo = QtWidgets.QComboBox()
        self.model_combo.setEditable(False)
        self.model_combo.setInsertPolicy(QtWidgets.QComboBox.NoInsert)
        self.model_combo.setMinimumWidth(scaled(160))
        left.addWidget(self.model_combo)
        self.provider_status = QtWidgets.QLabel("")
        self.provider_status.setMinimumWidth(scaled(78))
        self.provider_status.setObjectName("StatusPill")
        left.addWidget(self.provider_status)

        left.addSpacing(scaled(10))
        self.mode_label = QtWidgets.QLabel("模式")
        left.addWidget(self.mode_label)
        self.mode_combo = QtWidgets.QComboBox()
        for mode in WORK_MODE_ORDER:
            meta = WORK_MODES[mode]
            self.mode_combo.addItem(meta.label, mode)
            self.mode_combo.setItemData(self.mode_combo.count() - 1, meta.description, QtCore.Qt.ToolTipRole)
        mode_index = self.mode_combo.findData(self.session.work_mode)
        self.mode_combo.setCurrentIndex(mode_index if mode_index >= 0 else 0)
        self.mode_combo.setMinimumWidth(scaled(82))
        left.addWidget(self.mode_combo)

        left.addSpacing(scaled(10))
        left.addWidget(QtWidgets.QLabel("思考"))
        self.thinking_combo = QtWidgets.QComboBox()
        self.thinking_combo.addItems(list(THINKING_LEVELS.keys()))
        self.thinking_combo.setCurrentText(self.session.current_thinking_level)
        self.thinking_combo.setMinimumWidth(scaled(70))
        left.addWidget(self.thinking_combo)

        self.thinking_hint = QtWidgets.QLabel(THINKING_LEVELS[self.session.current_thinking_level]["description"])
        self.thinking_hint.setObjectName("HintText")
        left.addWidget(self.thinking_hint, 1)

        self.clear_messages_btn = QtWidgets.QPushButton("清空消息")
        self.clear_messages_btn.setFixedWidth(scaled(74))
        self.clear_messages_btn.clicked.connect(self._clear_current_conversation_messages)

        layout.addLayout(left, 1)
        layout.addWidget(self.clear_messages_btn)
        bar.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        bar.setMaximumHeight(scaled(36))
        return bar

    def _wire(self) -> None:
        self.chat.send_requested.connect(self.session.send_message)
        self.chat.stop_requested.connect(self.session.stop)
        self.chat.delete_message_requested.connect(self._delete_single_message)
        self.chat.node_link_clicked.connect(self._focus_node_from_chat)
        self.chat.plan_confirm_requested.connect(self.session.confirm_plan)
        self.chat.plan_cancel_requested.connect(self.session.cancel_plan)
        self.chat.pending_images_changed.connect(self._update_context_usage)
        self.context_panel.refresh_requested.connect(self.session.refresh_context)

        self.session.message_added.connect(self.chat.add_message)
        self.session.message_added.connect(self._update_context_usage)
        self.session.event_added.connect(self.trace.add_event)
        self.session.context_changed.connect(self.context_panel.set_context)
        self.session.context_changed.connect(self._update_context_usage)
        self.session.providers_changed.connect(self._providers_changed)
        self.session.busy_changed.connect(self.chat.set_busy)
        self.session.busy_changed.connect(self._set_actions_busy)
        self.session.conversations_changed.connect(self._refresh_conversation_list)
        self.session.conversation_changed.connect(self._load_conversation)
        self.session.storage_status_changed.connect(self._set_storage_status)
        self.session.work_mode_changed.connect(self._session_work_mode_changed)
        self.session.todo_changed.connect(self.chat.set_todos)

        self.provider_combo.currentIndexChanged.connect(self._provider_changed)
        self.model_combo.currentTextChanged.connect(self._model_changed)
        self.mode_combo.currentIndexChanged.connect(self._work_mode_changed)
        self.thinking_combo.currentTextChanged.connect(self._thinking_changed)

    def _add_action_button(self, layout, label: str, action: str) -> None:
        button = QtWidgets.QPushButton(label)
        button.setObjectName("GhostButton")
        button.setProperty("agent_action", action)
        button.clicked.connect(lambda checked=False, name=action: self.session.run_action(name))
        self._action_buttons[action] = button
        layout.addWidget(button)

    def _refresh_conversation_list(self) -> None:
        self._syncing_conversations = True
        self._refresh_conversation_tabs()
        self._syncing_conversations = False

    def _refresh_conversation_tabs(self) -> None:
        if not hasattr(self, "conversation_tabs"):
            return
        self.conversation_tabs.blockSignals(True)
        try:
            while self.conversation_tabs.count():
                self.conversation_tabs.removeTab(0)
            current_index = 0
            for index, conversation in enumerate(self.session.conversations):
                message_count = len(conversation.messages)
                label = conversation.title
                if len(label) > 22:
                    label = label[:21] + "..."
                tab_index = self.conversation_tabs.addTab(label)
                self.conversation_tabs.setTabData(tab_index, conversation.id)
                suffix = f"\n{message_count} 条消息" if message_count else ""
                self.conversation_tabs.setTabToolTip(tab_index, f"{conversation.title}{suffix}")
                if conversation.id == self.session.current_conversation_id:
                    current_index = index
            if self.conversation_tabs.count():
                self.conversation_tabs.setCurrentIndex(current_index)
        finally:
            self.conversation_tabs.blockSignals(False)

    def _conversation_tab_changed(self, index: int) -> None:
        if self._syncing_conversations or index < 0:
            return
        conversation_id = self.conversation_tabs.tabData(index)
        if conversation_id:
            self.session.switch_conversation(conversation_id)

    def _rename_conversation_tab(self, index: int) -> None:
        if index < 0:
            return
        conversation_id = self.conversation_tabs.tabData(index)
        if conversation_id:
            self._rename_conversation(conversation_id)

    def _show_conversation_tab_menu(self, pos) -> None:
        index = self.conversation_tabs.tabAt(pos)
        conversation_id = self.conversation_tabs.tabData(index) if index >= 0 else ""
        menu = QtWidgets.QMenu(self)
        new_action = menu.addAction("新建会话")
        import_action = menu.addAction("导入会话")
        rename_action = menu.addAction("重命名")
        export_action = menu.addAction("导出")
        clear_action = menu.addAction("清空消息")
        delete_action = menu.addAction("删除会话")
        if not conversation_id:
            rename_action.setEnabled(False)
            export_action.setEnabled(False)
            clear_action.setEnabled(False)
            delete_action.setEnabled(False)
        action = menu.exec_(self.conversation_tabs.mapToGlobal(pos))
        if action == new_action:
            self.session.create_conversation("新会话")
        elif action == import_action:
            self._import_conversations()
        elif action == rename_action:
            self._rename_conversation(conversation_id)
        elif action == export_action:
            self._export_conversation(conversation_id)
        elif action == clear_action:
            self._clear_conversation_messages(conversation_id)
        elif action == delete_action:
            self._delete_conversation(conversation_id)

    def _rename_conversation(self, conversation_id: str) -> None:
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
        self.setToolTip(text)

    def _toggle_right_sidebar(self) -> None:
        sizes = self.main_splitter.sizes()
        if self._right_sidebar_visible:
            self._right_sidebar_width = max(scaled(240), sizes[1])
            self.context_panel.hide()
            self.main_splitter.setSizes([sizes[0] + sizes[1], 0])
            self.right_toggle_btn.setText("<")
            self._right_sidebar_visible = False
        else:
            self.context_panel.show()
            total = sum(self.main_splitter.sizes()) or scaled(1200)
            center = max(scaled(420), total - self._right_sidebar_width)
            self.main_splitter.setSizes([center, self._right_sidebar_width])
            self.right_toggle_btn.setText(">")
            self._right_sidebar_visible = True
        self._refresh_splitter_after_toggle()

    def _refresh_splitter_after_toggle(self) -> None:
        for widget in (self.center_workspace, self.context_panel, self.main_splitter):
            widget.updateGeometry()
            widget.update()
        self._position_right_toggle()
        QtCore.QTimer.singleShot(0, self._repaint_splitter_widgets)

    def _repaint_splitter_widgets(self) -> None:
        for widget in (self.center_workspace, self.context_panel, self.main_splitter):
            widget.repaint()
        self._position_right_toggle()

    def _position_right_toggle(self) -> None:
        if not hasattr(self, "right_toggle_btn") or not hasattr(self, "main_splitter"):
            return
        parent = self.right_toggle_btn.parentWidget()
        if parent is None:
            return
        button_width = self.right_toggle_btn.width()
        button_height = self.right_toggle_btn.height()
        sizes = self.main_splitter.sizes()
        center_width = sizes[0] if sizes else self.main_splitter.width()
        splitter_x = self.main_splitter.x()
        splitter_y = self.main_splitter.y()
        if self._right_sidebar_visible:
            boundary_x = splitter_x + min(center_width, self.main_splitter.width())
            x = boundary_x - button_width // 2
        else:
            x = splitter_x + self.main_splitter.width() - button_width
        x = max(splitter_x, min(parent.width() - button_width, x))
        y = splitter_y + max(0, (self.main_splitter.height() - button_height) // 2)
        self.right_toggle_btn.setGeometry(x, y, button_width, button_height)
        self.right_toggle_btn.raise_()

    def _toggle_focus_mode(self) -> None:
        self._focus_mode = not self._focus_mode
        if self._focus_mode:
            self._trace_visible_before_focus = self.trace.isVisible()
            if self._right_sidebar_visible:
                self._toggle_right_sidebar()
            self.trace.hide()
            self.focus_mode_btn.setText("退出专注")
        else:
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
        self._update_context_usage()

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
        self._update_context_usage()

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
        self._update_context_usage()

    def _thinking_changed(self, level: str) -> None:
        self.session.set_thinking_level(level)
        self.thinking_hint.setText(THINKING_LEVELS[level]["description"])

    def _work_mode_changed(self, _index: int = -1) -> None:
        if not hasattr(self, "mode_combo"):
            return
        mode = str(self.mode_combo.currentData() or "agent")
        self.session.set_work_mode(mode)
        self._update_mode_controls()

    def _session_work_mode_changed(self, mode: str) -> None:
        if hasattr(self, "mode_combo"):
            self.mode_combo.blockSignals(True)
            index = self.mode_combo.findData(mode)
            if index >= 0:
                self.mode_combo.setCurrentIndex(index)
            self.mode_combo.blockSignals(False)
        self._update_mode_controls()

    def _toggle_ui_language(self) -> None:
        next_language = "en" if self.session.ui_language == "zh" else "zh"
        self.session.set_ui_language(next_language)
        self._apply_ui_language()

    def _apply_ui_language(self) -> None:
        language = getattr(self.session, "ui_language", "zh")
        is_english = language == "en"
        if hasattr(self, "language_btn"):
            self.language_btn.setText("中文" if is_english else "English")
            self.language_btn.setToolTip("Switch to Chinese" if is_english else "切换到英文")
        if hasattr(self, "mode_label"):
            self.mode_label.setText("Mode" if is_english else "模式")
        if hasattr(self, "_action_buttons"):
            labels = {
                "analyze_scene": ("Analyze Scene", "分析工程"),
                "inspect_selection": ("Inspect Selection", "查看选中节点"),
                "create_nodes": ("Create Node", "创建节点"),
                "fix_error": ("Fix Error", "修复错误"),
                "capture_viewport": ("Capture Viewport", "捕获视口"),
            }
            for action, button in self._action_buttons.items():
                english, chinese = labels.get(action, (action, action))
                button.setText(english if is_english else chinese)
        self._update_mode_controls()
        self._update_context_usage()

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

    def _update_context_usage(self, *_args) -> None:
        if not hasattr(self, "context_usage_label"):
            return
        conversation = self.session.current_conversation
        text_chars = 0
        image_count = 0
        for message in conversation.messages:
            text_chars += len(str(getattr(message, "role", "")))
            text_chars += len(str(getattr(message, "content", "")))
            image_count += len(getattr(message, "image_paths", []) or [])
        if hasattr(self, "chat"):
            image_count += len(getattr(self.chat, "pending_images", []) or [])
        text_chars += len(str(getattr(self.session, "context", {}) or {}))

        estimated_tokens = max(0, int(round(text_chars / 3.5)) + image_count * 850)
        context_window = self._estimated_context_window(self.session.current_provider.model)
        percent = 0 if estimated_tokens <= 0 else min(100, int(round((estimated_tokens / context_window) * 100)))
        if estimated_tokens > 0 and percent == 0:
            percent = 1
        is_english = getattr(self.session, "ui_language", "zh") == "en"
        prefix = "Context" if is_english else "上下文"
        self.context_usage_label.setText(f"{prefix} {percent}%")
        if is_english:
            tooltip = (
                f"Local estimate: about {estimated_tokens:,} tokens / {context_window:,} context window. "
                "Provider-reported usage is not wired yet; TODO already tracks token/context management."
            )
        else:
            tooltip = (
                f"本地估算：约 {estimated_tokens:,} tokens / {context_window:,} 上下文窗口。"
                " 当前版本还没有接入 provider 返回的真实 usage；TODO 中已有 token / context 管理计划。"
            )
        self.context_usage_label.setToolTip(tooltip)

    def _estimated_context_window(self, model: str) -> int:
        normalized = (model or "").strip().lower()
        explicit_windows = (
            ("1000k", 1_000_000),
            ("1m", 1_000_000),
            ("200k", 200_000),
            ("128k", 128_000),
            ("64k", 64_000),
            ("32k", 32_000),
            ("16k", 16_000),
            ("8k", 8_000),
        )
        for marker, size in explicit_windows:
            if marker in normalized:
                return size
        if "gemini" in normalized:
            return 1_000_000
        if "claude" in normalized or "opus" in normalized or "sonnet" in normalized:
            return 200_000
        return 128_000

    def _open_settings(self) -> None:
        dialog = SettingsDialog(self.session.providers, self.session.vision_backend, self)
        dialog.settings_saved.connect(self.session.set_runtime_settings)
        dialog.exec_()

    def _focus_node_from_chat(self, node_path: str) -> None:
        navigator = getattr(self.session.adapter, "navigate_to_node", None)
        if navigator is None:
            return
        result = navigator(node_path)
        if result.get("ok"):
            self.session._add_event("Focus node", result.get("message", node_path), "success")
            self.session.refresh_context()
        else:
            QtWidgets.QMessageBox.warning(self, "Node Focus", result.get("message", node_path))

    def _update_mode_controls(self) -> None:
        if hasattr(self, "mode_combo"):
            self.mode_combo.setToolTip(self.session.tool_registry.mode_description(self.session.work_mode))
        busy = getattr(self.session, "busy", False)
        for action, button in getattr(self, "_action_buttons", {}).items():
            allowed = self.session.toolbar_action_allowed(action)
            button.setEnabled((not busy) and allowed)
            button.setToolTip(self.session.toolbar_action_tooltip(action))

    def _set_actions_busy(self, busy: bool) -> None:
        for action, button in getattr(self, "_action_buttons", {}).items():
            button.setEnabled((not busy) and self.session.toolbar_action_allowed(action))
            button.setToolTip(self.session.toolbar_action_tooltip(action))
        if hasattr(self, "clear_messages_btn"):
            self.clear_messages_btn.setEnabled(not busy)


def create_panel():
    return AgentMainPanel()
