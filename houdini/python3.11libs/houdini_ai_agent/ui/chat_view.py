"""Chat widgets for the Houdini AI Agent panel."""

from __future__ import annotations

import json
from html import escape
from pathlib import Path
from typing import List
import re
import tempfile
import uuid

from houdini_ai_agent.qt import QtCore, QtGui, QtWidgets, alignment_flag
from houdini_ai_agent.ui.style import scaled


NODE_PATH_PATTERN = re.compile(r"(/(?:obj|mat|stage|img|out|shop|tasks|lopnet|ch|vex|top|topnet|cop2|geo)[^\s`<]*)")


class ThoughtBubble(QtWidgets.QFrame):
    delete_requested = QtCore.Signal(int)
    node_link_clicked = QtCore.Signal(str)

    def __init__(self, content: str, timestamp: str, message_index: int = -1, parent=None):
        super().__init__(parent)
        self.setObjectName("ThoughtBubble")
        self.message_index = message_index

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(scaled(12), scaled(8), scaled(12), scaled(8))
        layout.setSpacing(scaled(7))

        header = QtWidgets.QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(scaled(7))

        self.toggle = QtWidgets.QToolButton()
        self.toggle.setObjectName("ThoughtToggle")
        self.toggle.setCheckable(True)
        self.toggle.setChecked(False)
        self.toggle.setArrowType(QtCore.Qt.RightArrow)
        self.toggle.setText(f"已思考  {timestamp}")
        self.toggle.setToolButtonStyle(QtCore.Qt.ToolButtonTextBesideIcon)
        header.addWidget(self.toggle)
        header.addStretch(1)
        layout.addLayout(header)

        preview_text = self._preview_text(content)
        if preview_text:
            preview = QtWidgets.QLabel(preview_text)
            preview.setObjectName("ThoughtPreview")
            preview.setWordWrap(True)
            layout.addWidget(preview)

        self.body = QtWidgets.QLabel()
        self.body.setWordWrap(True)
        self.body.setTextFormat(QtCore.Qt.RichText)
        self.body.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse | QtCore.Qt.LinksAccessibleByMouse)
        self.body.setOpenExternalLinks(False)
        self.body.setObjectName("ThoughtBody")
        self.body.setText(self._format_thought_html(content))
        self.body.linkActivated.connect(self._link_activated)
        self.body.hide()
        layout.addWidget(self.body)

        def _toggle(checked: bool) -> None:
            self.toggle.setArrowType(QtCore.Qt.DownArrow if checked else QtCore.Qt.RightArrow)
            self.body.setVisible(checked)

        self.toggle.toggled.connect(_toggle)

    def contextMenuEvent(self, event):
        menu = QtWidgets.QMenu(self)
        delete_action = menu.addAction("删除此消息")
        action = menu.exec_(event.globalPos())
        if action == delete_action and self.message_index >= 0:
            self.delete_requested.emit(self.message_index)

    def _preview_text(self, content: str) -> str:
        lines = [line.strip(" -•\t") for line in content.splitlines() if line.strip()]
        cleaned = [line for line in lines if not line.startswith(("可用工具：", "本轮允许的工具："))]
        return " · ".join(cleaned[:2])[:180]

    def _format_thought_html(self, content: str) -> str:
        rows = []
        for raw_line in content.splitlines() or [""]:
            line = raw_line.strip()
            if not line:
                continue
            line = re.sub(r"^(模式判断|场景依据|输入依据|本轮允许的工具|下一步)[：:]", "", line).strip()
            label_match = re.match(r"^(模式|已读取当前网络|已检查选择与错误|输入|可用工具|下一步)[：:](.*)$", line)
            if label_match:
                escaped = f"<b>{escape(label_match.group(1))}：</b>{escape(label_match.group(2).strip())}"
            else:
                escaped = escape(line)
            linked = NODE_PATH_PATTERN.sub(r'<a href="node:\1">\1</a>', escaped)
            rows.append(f"<li>{linked}</li>")
        if not rows:
            rows.append("<li>已完成本轮判断。</li>")
        return "<ul class='thought-list'>" + "".join(rows[:8]) + "</ul>"

    def _link_activated(self, href: str) -> None:
        if href.startswith("node:"):
            self.node_link_clicked.emit(href[5:])


class MessageBubble(QtWidgets.QFrame):
    delete_requested = QtCore.Signal(int)
    node_link_clicked = QtCore.Signal(str)
    plan_confirm_requested = QtCore.Signal(str)
    plan_cancel_requested = QtCore.Signal(str)

    def __init__(self, role: str, content: str, timestamp: str, image_paths=None, message_index: int = -1, parent=None):
        super().__init__(parent)
        self.setObjectName("MessageBubble")
        self.setProperty("role", role)
        self.message_index = message_index

        role_label = "You" if role == "user" else ("已思考" if role == "thought" else ("Plan" if role == "plan" else "Agent"))
        header = QtWidgets.QLabel(f"{role_label}  {timestamp}")
        header.setObjectName("MessageHeader")

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(scaled(11), scaled(7), scaled(11), scaled(9))
        layout.setSpacing(scaled(7))
        layout.addWidget(header)
        if image_paths:
            layout.addWidget(ImageStrip(image_paths, max_thumb_size=116))
        if role == "plan":
            layout.addWidget(self._build_plan_widget(content))
        elif role == "thought":
            body = self._build_body_label(content)
            toggle = QtWidgets.QToolButton()
            toggle.setText("已思考")
            toggle.setCheckable(True)
            toggle.setChecked(False)
            toggle.setToolButtonStyle(QtCore.Qt.ToolButtonTextBesideIcon)
            toggle.setArrowType(QtCore.Qt.RightArrow)
            body.hide()

            def _toggle_thought(checked: bool) -> None:
                toggle.setArrowType(QtCore.Qt.DownArrow if checked else QtCore.Qt.RightArrow)
                body.setVisible(checked)

            toggle.toggled.connect(_toggle_thought)
            layout.addWidget(toggle)
            layout.addWidget(body)
        else:
            body = self._build_body_label(content)
            layout.addWidget(body)

    def contextMenuEvent(self, event):
        menu = QtWidgets.QMenu(self)
        delete_action = menu.addAction("删除此消息")
        action = menu.exec_(event.globalPos())
        if action == delete_action and self.message_index >= 0:
            self.delete_requested.emit(self.message_index)

    def _build_body_label(self, content: str) -> QtWidgets.QLabel:
        body = QtWidgets.QLabel()
        body.setWordWrap(True)
        body.setTextFormat(QtCore.Qt.RichText)
        body.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse | QtCore.Qt.LinksAccessibleByMouse)
        body.setOpenExternalLinks(False)
        body.setObjectName("MessageBody")
        body.setText(self._format_message_html(content))
        body.linkActivated.connect(self._link_activated)
        return body

    def _build_plan_widget(self, content: str) -> QtWidgets.QWidget:
        plan = self._parse_plan_content(content)
        widget = QtWidgets.QFrame()
        widget.setObjectName("PlanCard")
        layout = QtWidgets.QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(scaled(8))

        title = QtWidgets.QLabel(plan.get("title") or "执行计划")
        title.setObjectName("PanelTitle")
        title.setWordWrap(True)
        layout.addWidget(title)

        goal = str(plan.get("goal") or plan.get("summary") or "").strip()
        if goal:
            goal_label = self._build_body_label(f"计划目标：{goal}")
            layout.addWidget(goal_label)

        steps = plan.get("steps", [])
        if isinstance(steps, list) and steps:
            layout.addWidget(self._build_plan_steps_widget(steps))
        else:
            fallback = self._build_body_label(str(plan.get("response") or "暂无结构化步骤。"))
            layout.addWidget(fallback)

        risks = plan.get("risks", [])
        if isinstance(risks, list) and risks:
            risk_text = "风险：" + "；".join(str(item) for item in risks if str(item).strip())
            layout.addWidget(self._build_body_label(risk_text))

        status = str(plan.get("status") or "draft")
        status_label = QtWidgets.QLabel(self._plan_status_text(status))
        status_label.setObjectName("HintText")
        layout.addWidget(status_label)

        row = QtWidgets.QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(scaled(8))
        row.addStretch(1)
        confirm_btn = QtWidgets.QPushButton("切换 Agent 执行")
        confirm_btn.setFixedWidth(scaled(126))
        cancel_btn = QtWidgets.QPushButton("取消计划")
        cancel_btn.setFixedWidth(scaled(86))
        enabled = status in {"draft", "paused", "blocked"}
        confirm_btn.setEnabled(enabled)
        cancel_btn.setEnabled(enabled)

        plan_id = str(plan.get("id") or "")

        def _confirm() -> None:
            confirm_btn.setEnabled(False)
            cancel_btn.setEnabled(False)
            status_label.setText("已确认，正在切换到 Agent 模式执行。")
            if plan_id:
                self.plan_confirm_requested.emit(plan_id)

        def _cancel() -> None:
            confirm_btn.setEnabled(False)
            cancel_btn.setEnabled(False)
            status_label.setText("已取消。")
            if plan_id:
                self.plan_cancel_requested.emit(plan_id)

        confirm_btn.clicked.connect(_confirm)
        cancel_btn.clicked.connect(_cancel)
        row.addWidget(cancel_btn)
        row.addWidget(confirm_btn)
        layout.addLayout(row)
        return widget

    def _build_plan_steps_widget(self, steps: List[object]) -> QtWidgets.QWidget:
        box = QtWidgets.QFrame()
        box.setObjectName("PlanTodoBox")
        layout = QtWidgets.QVBoxLayout(box)
        layout.setContentsMargins(scaled(10), scaled(8), scaled(10), scaled(8))
        layout.setSpacing(scaled(5))
        done = 0
        for step in steps:
            if isinstance(step, dict) and str(step.get("status") or "") == "completed":
                done += 1
        header = QtWidgets.QLabel(f"To-dos {done}/{len(steps)} 已完成")
        header.setObjectName("PanelTitle")
        layout.addWidget(header)
        for index, step in enumerate(steps, 1):
            layout.addWidget(self._build_plan_step(index, step))
        return box

    def _build_plan_step(self, index: int, step: object) -> QtWidgets.QWidget:
        if not isinstance(step, dict):
            step = {"title": str(step)}
        title = str(step.get("title") or step.get("name") or f"Step {index}").strip()
        detail = str(step.get("detail") or step.get("description") or "").strip()
        tool = str(step.get("tool_hint") or step.get("tool") or "").strip()
        depends_on = step.get("depends_on", [])
        if isinstance(depends_on, list) and depends_on:
            dep_text = "依赖：" + ", ".join(str(item) for item in depends_on)
        else:
            dep_text = ""
        status = str(step.get("status") or "pending").strip()
        marker = "○"
        if status == "completed":
            marker = "✓"
        elif status in {"in_progress", "executing"}:
            marker = "●"
        elif status in {"blocked", "error"}:
            marker = "!"
        lines = [f"{marker} {title}"]
        if detail:
            lines.append(f"  {detail}")
        if status and status != "pending":
            lines.append(f"  状态：{status}")
        result = str(step.get("result") or "").strip()
        if result:
            lines.append(f"  结果：{result}")
        if tool:
            lines.append(f"  工具/动作：{tool}")
        if dep_text:
            lines.append(f"  {dep_text}")
        return self._build_body_label("\n".join(lines))

    def _parse_plan_content(self, content: str) -> dict:
        try:
            data = json.loads(content)
        except Exception:
            return {"title": "执行计划", "response": content, "steps": []}
        return data if isinstance(data, dict) else {"title": "执行计划", "steps": []}

    def _plan_status_text(self, status: str) -> str:
        labels = {
            "draft": "等待确认。确认后会切换到 Agent 模式执行。",
            "confirmed": "已确认，等待执行。",
            "executing": "正在执行。",
            "completed": "已完成。",
            "cancelled": "已取消。",
        }
        labels["paused"] = "Paused; confirm again to resume."
        labels["blocked"] = "Blocked; revise or confirm again after adjustment."
        return labels.get(status, status)

    def _link_activated(self, href: str) -> None:
        if href.startswith("node:"):
            self.node_link_clicked.emit(href[5:])

    def _format_message_html(self, content: str) -> str:
        lines = []
        for raw_line in content.splitlines() or [""]:
            escaped_line = escape(raw_line)
            linked = NODE_PATH_PATTERN.sub(r'<a href="node:\1">\1</a>', escaped_line)
            lines.append(linked)
        return "<div style='line-height:1.45; white-space:normal;'>" + "<br/>".join(lines) + "</div>"


class ImageStrip(QtWidgets.QWidget):
    def __init__(self, image_paths: List[str], max_thumb_size: int = 96, compact: bool = False, parent=None):
        super().__init__(parent)
        max_thumb_size = scaled(max_thumb_size)
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(scaled(6 if compact else 8))
        for path in image_paths:
            layout.addWidget(ImageThumb(path, max_thumb_size, compact=compact))
        layout.addStretch(1)


class ImageThumb(QtWidgets.QFrame):
    def __init__(self, path: str, max_thumb_size: int, compact: bool = False, parent=None):
        super().__init__(parent)
        self.setObjectName("ImageThumb")
        self.path = path
        self.max_thumb_size = max_thumb_size
        self.compact = compact
        self.setToolTip(path)
        if compact:
            self.setMaximumHeight(max_thumb_size + scaled(8))
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(scaled(2), scaled(2), scaled(2), scaled(2))
        layout.setSpacing(0)

        label = QtWidgets.QLabel()
        label.setAlignment(alignment_flag("AlignCenter"))
        pixmap = QtGui.QPixmap(path)
        if not pixmap.isNull():
            label.setPixmap(
                pixmap.scaled(
                    max_thumb_size,
                    max_thumb_size,
                    QtCore.Qt.KeepAspectRatio,
                    QtCore.Qt.SmoothTransformation,
                )
            )
        else:
            label.setText("Image")
            label.setFixedSize(max_thumb_size, max_thumb_size)
        layout.addWidget(label)

        if not compact:
            name = QtWidgets.QLabel(Path(path).name)
            name.setObjectName("HintText")
            name.setAlignment(alignment_flag("AlignCenter"))
            name.setMaximumWidth(max_thumb_size + scaled(20))
            name.setWordWrap(True)
            layout.addWidget(name)

    def mouseDoubleClickEvent(self, event):
        viewer = ImagePreviewDialog(self.path, self)
        viewer.exec_()
        super().mouseDoubleClickEvent(event)


class ImagePreviewDialog(QtWidgets.QDialog):
    def __init__(self, path: str, parent=None):
        super().__init__(parent)
        self.path = path
        self.setWindowTitle(Path(path).name)
        self.resize(scaled(900), scaled(700))
        self._build_ui()

    def _build_ui(self) -> None:
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(scaled(10), scaled(10), scaled(10), scaled(10))
        root.setSpacing(scaled(6))

        pixmap = QtGui.QPixmap(self.path)
        self.image_label = QtWidgets.QLabel()
        self.image_label.setAlignment(alignment_flag("AlignCenter"))
        self.image_label.setMinimumSize(scaled(360), scaled(240))
        self.image_label.setObjectName("ImagePreview")
        self._pixmap = pixmap
        self._update_pixmap()

        info = QtWidgets.QLabel(self.path)
        info.setObjectName("HintText")
        info.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)

        close_btn = QtWidgets.QPushButton("关闭")
        close_btn.setFixedWidth(scaled(80))
        close_btn.clicked.connect(self.accept)

        bottom = QtWidgets.QHBoxLayout()
        bottom.addWidget(info, 1)
        bottom.addWidget(close_btn)

        root.addWidget(self.image_label, 1)
        root.addLayout(bottom)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_pixmap()

    def _update_pixmap(self) -> None:
        if self._pixmap.isNull():
            self.image_label.setText("无法读取图片")
            return
        available = self.image_label.size()
        if available.width() <= 1 or available.height() <= 1:
            return
        self.image_label.setPixmap(
            self._pixmap.scaled(
                available,
                QtCore.Qt.KeepAspectRatio,
                QtCore.Qt.SmoothTransformation,
            )
        )


class ChatInput(QtWidgets.QTextEdit):
    submit_requested = QtCore.Signal()
    image_pasted = QtCore.Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)

    def keyPressEvent(self, event):
        if event.key() in (QtCore.Qt.Key_Return, QtCore.Qt.Key_Enter):
            modifiers = event.modifiers()
            alt_pressed = bool(modifiers & QtCore.Qt.AltModifier)
            ctrl_pressed = bool(modifiers & QtCore.Qt.ControlModifier)
            shift_pressed = bool(modifiers & QtCore.Qt.ShiftModifier)
            meta_pressed = bool(modifiers & QtCore.Qt.MetaModifier)
            if alt_pressed:
                self.insertPlainText("\n")
                return
            if not (ctrl_pressed or shift_pressed or meta_pressed):
                self.submit_requested.emit()
                return
        if event.matches(QtGui.QKeySequence.Paste) and self._paste_image_from_clipboard():
            return
        super().keyPressEvent(event)

    def insertFromMimeData(self, source):
        if self._paste_image_from_clipboard():
            return
        super().insertFromMimeData(source)

    def dragEnterEvent(self, event):
        if self._accept_image_urls(event.mimeData()):
            event.acceptProposedAction()
            return
        super().dragEnterEvent(event)

    def dropEvent(self, event):
        accepted = self._extract_image_urls(event.mimeData())
        if accepted:
            for path in accepted:
                self.image_pasted.emit(path)
            event.acceptProposedAction()
            return
        super().dropEvent(event)

    def _paste_image_from_clipboard(self) -> bool:
        clipboard = QtWidgets.QApplication.clipboard()
        mime = clipboard.mimeData()
        image = None
        if mime and mime.hasImage():
            image = clipboard.image()
        elif mime and mime.hasUrls():
            accepted = self._extract_image_urls(mime)
            if accepted:
                for path in accepted:
                    self.image_pasted.emit(path)
                return True

        if image is None or image.isNull():
            return False

        temp_dir = Path(tempfile.gettempdir()) / "houdini_ai_agent_clipboard"
        temp_dir.mkdir(parents=True, exist_ok=True)
        path = temp_dir / f"clipboard_{uuid.uuid4().hex}.png"
        image.save(str(path), "PNG")
        self.image_pasted.emit(str(path))
        return True

    def _accept_image_urls(self, mime) -> bool:
        return bool(self._extract_image_urls(mime))

    def _extract_image_urls(self, mime) -> List[str]:
        if mime is None or not mime.hasUrls():
            return []
        accepted = []
        for url in mime.urls():
            path = url.toLocalFile()
            if path and Path(path).suffix.lower() in {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".webp", ".gif"}:
                accepted.append(path)
        return accepted


class ChatView(QtWidgets.QWidget):
    send_requested = QtCore.Signal(str, list)
    stop_requested = QtCore.Signal()
    delete_message_requested = QtCore.Signal(int)
    node_link_clicked = QtCore.Signal(str)
    plan_confirm_requested = QtCore.Signal(str)
    plan_cancel_requested = QtCore.Signal(str)
    pending_images_changed = QtCore.Signal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.pending_images: List[str] = []
        self._showing_welcome = False
        self._image_path_preprocessor = None
        self._message_count = 0
        self._build_ui()

    def set_image_path_preprocessor(self, preprocessor) -> None:
        self._image_path_preprocessor = preprocessor

    def add_message(self, message) -> None:
        if self._showing_welcome:
            self.clear_messages()
        self._remove_bottom_stretch()
        if message.role == "thought":
            bubble = ThoughtBubble(message.content, message.timestamp, message_index=self._message_count)
            bubble.delete_requested.connect(self.delete_message_requested.emit)
            bubble.node_link_clicked.connect(self.node_link_clicked.emit)
        else:
            bubble = MessageBubble(
                message.role,
                message.content,
                message.timestamp,
                message.image_paths,
                message_index=self._message_count,
            )
            bubble.delete_requested.connect(self.delete_message_requested.emit)
            bubble.node_link_clicked.connect(self.node_link_clicked.emit)
            bubble.plan_confirm_requested.connect(self.plan_confirm_requested.emit)
            bubble.plan_cancel_requested.connect(self.plan_cancel_requested.emit)
        row = QtWidgets.QWidget()
        row_layout = QtWidgets.QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        if message.role == "user":
            row_layout.addStretch(1)
            row_layout.addWidget(bubble, 3)
        elif message.role == "thought":
            row_layout.addSpacing(scaled(24))
            row_layout.addWidget(bubble, 5)
            row_layout.addStretch(2)
        else:
            row_layout.addWidget(bubble, 1)
        self.messages_layout.addWidget(row)
        self.messages_layout.addStretch(1)
        self._message_count += 1
        QtCore.QTimer.singleShot(0, self._scroll_to_bottom)

    def load_conversation(self, conversation) -> None:
        self.clear_messages()
        self.set_todos(getattr(conversation, "todos", []) or [])
        if not conversation.messages:
            self.show_welcome()
            return
        for message in conversation.messages:
            self.add_message(message)

    def clear_messages(self) -> None:
        while self.messages_layout.count():
            item = self.messages_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        self._showing_welcome = False
        self._message_count = 0

    def set_todos(self, todos) -> None:
        if not hasattr(self, "todo_bar"):
            return
        while self.todo_layout.count():
            item = self.todo_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        visible_todos = [todo for todo in (todos or []) if isinstance(todo, dict) and str(todo.get("status") or "") != "done"]
        if not visible_todos:
            self.todo_bar.hide()
            return
        title = QtWidgets.QLabel("Todos")
        title.setObjectName("HintText")
        self.todo_layout.addWidget(title)
        status_labels = {
            "pending": "Pending",
            "in_progress": "Running",
            "error": "Blocked",
            "done": "Done",
        }
        for todo in visible_todos[:6]:
            status = str(todo.get("status") or "pending")
            text = f"{status_labels.get(status, status)}: {todo.get('title') or 'Task'}"
            label = QtWidgets.QLabel(text)
            label.setObjectName("TodoChip")
            label.setToolTip(str(todo.get("detail") or ""))
            self.todo_layout.addWidget(label)
        if len(visible_todos) > 6:
            more = QtWidgets.QLabel(f"+{len(visible_todos) - 6}")
            more.setObjectName("HintText")
            self.todo_layout.addWidget(more)
        self.todo_layout.addStretch(1)
        self.todo_bar.show()

    def set_busy(self, busy: bool) -> None:
        self.send_button.setEnabled(not busy)
        self.stop_button.setEnabled(busy)
        self.attach_button.setEnabled(not busy)

    def show_welcome(self) -> None:
        self._remove_bottom_stretch()
        label = QtWidgets.QLabel(
            "欢迎使用 Houdini AI Agent。\n"
            "你可以创建多个会话、发送图片、切换思考档位，并在右侧查看工程上下文。"
        )
        label.setWordWrap(True)
        label.setObjectName("WelcomeText")
        self.messages_layout.addWidget(label)
        self.messages_layout.addStretch(1)
        self._showing_welcome = True

    def _build_ui(self) -> None:
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(scaled(6))

        self.scroll = QtWidgets.QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QtWidgets.QFrame.NoFrame)

        self.todo_bar = QtWidgets.QFrame()
        self.todo_bar.setObjectName("TodoBar")
        self.todo_layout = QtWidgets.QHBoxLayout(self.todo_bar)
        self.todo_layout.setContentsMargins(scaled(10), scaled(5), scaled(10), scaled(5))
        self.todo_layout.setSpacing(scaled(6))
        self.todo_bar.hide()

        self.messages_widget = QtWidgets.QWidget()
        self.messages_layout = QtWidgets.QVBoxLayout(self.messages_widget)
        self.messages_layout.setContentsMargins(scaled(10), scaled(10), scaled(10), scaled(10))
        self.messages_layout.setSpacing(scaled(8))
        self.scroll.setWidget(self.messages_widget)

        self.attachment_bar = QtWidgets.QFrame()
        self.attachment_bar.setObjectName("AttachmentBar")
        self.attachment_layout = QtWidgets.QHBoxLayout(self.attachment_bar)
        self.attachment_layout.setContentsMargins(scaled(6), scaled(2), scaled(6), scaled(2))
        self.attachment_layout.setSpacing(scaled(6))
        self.attachment_bar.setMaximumHeight(scaled(40))
        self.attachment_bar.hide()

        input_row = QtWidgets.QFrame()
        input_row.setObjectName("PromptDock")
        input_layout = QtWidgets.QHBoxLayout(input_row)
        input_layout.setContentsMargins(scaled(10), scaled(8), scaled(8), scaled(8))
        input_layout.setSpacing(scaled(8))

        self.input = ChatInput()
        self.input.setObjectName("PromptInput")
        self.input.setPlaceholderText("输入请求，Enter 发送，Alt+Enter 换行。也可以先添加图片让 Agent 识别。")
        self.input.setFixedHeight(scaled(86))
        self.input.submit_requested.connect(self._emit_send)
        self.input.image_pasted.connect(self._add_pending_image)

        self.attach_button = QtWidgets.QPushButton("图片")
        self.attach_button.setFixedWidth(scaled(58))
        self.attach_button.clicked.connect(self._attach_images)

        self.send_button = QtWidgets.QPushButton("发送")
        self.send_button.setObjectName("PrimaryButton")
        self.send_button.setFixedWidth(scaled(58))
        self.send_button.clicked.connect(self._emit_send)

        self.stop_button = QtWidgets.QPushButton("停止")
        self.stop_button.setFixedWidth(scaled(58))
        self.stop_button.setEnabled(False)
        self.stop_button.clicked.connect(self.stop_requested.emit)

        buttons = QtWidgets.QVBoxLayout()
        buttons.setContentsMargins(0, 0, 0, 0)
        buttons.setSpacing(scaled(4))
        buttons.addWidget(self.attach_button)
        buttons.addWidget(self.send_button)
        buttons.addWidget(self.stop_button)

        input_layout.addWidget(self.input, 1)
        input_layout.addLayout(buttons)

        root.addWidget(self.todo_bar)
        root.addWidget(self.scroll, 1)
        root.addWidget(self.attachment_bar)
        root.addWidget(input_row)

    def _attach_images(self) -> None:
        paths, _ = QtWidgets.QFileDialog.getOpenFileNames(
            self,
            "选择图片",
            "",
            "Images (*.png *.jpg *.jpeg *.bmp *.tif *.tiff *.webp *.gif);;All Files (*)",
        )
        if not paths:
            return
        for path in paths:
            self._add_pending_image(path)
        self._refresh_attachments()

    def _add_pending_image(self, path: str) -> None:
        if self._image_path_preprocessor:
            processed = self._image_path_preprocessor([path])
            if processed:
                path = processed[0]
        if path and path not in self.pending_images:
            self.pending_images.append(path)
        self._refresh_attachments()

    def _refresh_attachments(self) -> None:
        while self.attachment_layout.count():
            item = self.attachment_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        if not self.pending_images:
            self.attachment_bar.hide()
            self.pending_images_changed.emit([])
            return

        label = QtWidgets.QLabel(f"待发送图片 {len(self.pending_images)}")
        label.setObjectName("HintText")
        self.attachment_layout.addWidget(label)
        self.attachment_layout.addWidget(ImageStrip(self.pending_images, max_thumb_size=32, compact=True), 1)
        clear_btn = QtWidgets.QPushButton("清空")
        clear_btn.setFixedWidth(scaled(52))
        clear_btn.clicked.connect(self._clear_attachments)
        self.attachment_layout.addWidget(clear_btn)
        self.attachment_bar.show()
        self.pending_images_changed.emit(list(self.pending_images))

    def _clear_attachments(self) -> None:
        self.pending_images = []
        self._refresh_attachments()

    def _emit_send(self) -> None:
        text = self.input.toPlainText().strip()
        image_paths = list(self.pending_images)
        if not text and not image_paths:
            return
        self.input.clear()
        self._clear_attachments()
        self.send_requested.emit(text, image_paths)

    def _remove_bottom_stretch(self) -> None:
        if self.messages_layout.count() == 0:
            return
        last = self.messages_layout.itemAt(self.messages_layout.count() - 1)
        if last and last.spacerItem():
            self.messages_layout.takeAt(self.messages_layout.count() - 1)

    def _scroll_to_bottom(self) -> None:
        bar = self.scroll.verticalScrollBar()
        bar.setValue(bar.maximum())
