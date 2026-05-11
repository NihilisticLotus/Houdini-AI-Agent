"""Chat widgets for the Houdini AI Agent panel."""

from __future__ import annotations

from html import escape
from pathlib import Path
from typing import List
import re
import tempfile
import uuid

from houdini_ai_agent.qt import QtCore, QtGui, QtWidgets, alignment_flag


class MessageBubble(QtWidgets.QFrame):
    delete_requested = QtCore.Signal(int)
    node_link_clicked = QtCore.Signal(str)

    def __init__(self, role: str, content: str, timestamp: str, image_paths=None, message_index: int = -1, parent=None):
        super().__init__(parent)
        self.setObjectName("MessageBubble")
        self.setProperty("role", role)
        self.message_index = message_index

        role_label = "You" if role == "user" else ("Plan" if role == "thought" else "Agent")
        header = QtWidgets.QLabel(f"{role_label}  {timestamp}")
        header.setObjectName("MessageHeader")

        body = QtWidgets.QTextBrowser()
        body.setOpenLinks(False)
        body.setOpenExternalLinks(False)
        body.setFrameShape(QtWidgets.QFrame.NoFrame)
        body.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        body.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        body.setSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Minimum)
        body.setHtml(self._format_message_html(content))
        body.setObjectName("MessageBody")
        body.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse | QtCore.Qt.LinksAccessibleByMouse)
        body.setMaximumHeight(16777215)
        body.document().documentLayout().documentSizeChanged.connect(lambda size: body.setMinimumHeight(int(size.height()) + 6))
        body.anchorClicked.connect(self._anchor_clicked)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 10)
        layout.setSpacing(8)
        layout.addWidget(header)
        if image_paths:
            layout.addWidget(ImageStrip(image_paths, max_thumb_size=132))
        if role == "thought":
            toggle = QtWidgets.QToolButton()
            toggle.setText("模型计划 / 工具调用")
            toggle.setCheckable(True)
            toggle.setChecked(False)
            toggle.setToolButtonStyle(QtCore.Qt.ToolButtonTextBesideIcon)
            toggle.setArrowType(QtCore.Qt.RightArrow)
            body.hide()

            def _toggle_plan(checked):
                toggle.setArrowType(QtCore.Qt.DownArrow if checked else QtCore.Qt.RightArrow)
                body.setVisible(checked)

            toggle.toggled.connect(_toggle_plan)
            layout.addWidget(toggle)
            layout.addWidget(body)
        else:
            layout.addWidget(body)

    def contextMenuEvent(self, event):
        menu = QtWidgets.QMenu(self)
        delete_action = menu.addAction("删除此消息")
        action = menu.exec_(event.globalPos())
        if action == delete_action and self.message_index >= 0:
            self.delete_requested.emit(self.message_index)

    def _anchor_clicked(self, url: QtCore.QUrl) -> None:
        if url.scheme() == "node":
            self.node_link_clicked.emit(url.path())

    def _format_message_html(self, content: str) -> str:
        lines = []
        for raw_line in content.splitlines() or [""]:
            escaped_line = escape(raw_line)
            linked = re.sub(
                r"(/(?:obj|mat|stage|img|out|shop|tasks|lopnet|ch|vex|top|topnet|cop2|geo)[^\s`<]*)",
                r'<a href="node:\1">\1</a>',
                escaped_line,
            )
            lines.append(linked)
        return "<br/>".join(lines)


class ImageStrip(QtWidgets.QWidget):
    def __init__(self, image_paths: List[str], max_thumb_size: int = 96, compact: bool = False, parent=None):
        super().__init__(parent)
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6 if compact else 8)
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
            self.setMaximumHeight(max_thumb_size + 8)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
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
            name.setMaximumWidth(max_thumb_size + 20)
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
        self.resize(900, 700)
        self._build_ui()

    def _build_ui(self) -> None:
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)

        pixmap = QtGui.QPixmap(self.path)
        self.image_label = QtWidgets.QLabel()
        self.image_label.setAlignment(alignment_flag("AlignCenter"))
        self.image_label.setMinimumSize(360, 240)
        self.image_label.setObjectName("ImagePreview")
        self._pixmap = pixmap
        self._update_pixmap()

        info = QtWidgets.QLabel(self.path)
        info.setObjectName("HintText")
        info.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)

        close_btn = QtWidgets.QPushButton("关闭")
        close_btn.setFixedWidth(80)
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
        if event.key() in (QtCore.Qt.Key_Return, QtCore.Qt.Key_Enter) and event.modifiers() == QtCore.Qt.ControlModifier:
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
            accepted = []
            for url in mime.urls():
                path = url.toLocalFile()
                if path and Path(path).suffix.lower() in {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".webp"}:
                    accepted.append(path)
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
        bubble = MessageBubble(
            message.role,
            message.content,
            message.timestamp,
            message.image_paths,
            message_index=self._message_count,
        )
        bubble.delete_requested.connect(self.delete_message_requested.emit)
        bubble.node_link_clicked.connect(self.node_link_clicked.emit)
        row = QtWidgets.QWidget()
        row_layout = QtWidgets.QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        if message.role == "user":
            row_layout.addStretch(1)
            row_layout.addWidget(bubble, 5)
        else:
            row_layout.addWidget(bubble, 5)
            row_layout.addStretch(1)
        self.messages_layout.addWidget(row)
        self.messages_layout.addStretch(1)
        self._message_count += 1
        QtCore.QTimer.singleShot(0, self._scroll_to_bottom)

    def load_conversation(self, conversation) -> None:
        self.clear_messages()
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
        root.setSpacing(8)

        self.scroll = QtWidgets.QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QtWidgets.QFrame.NoFrame)

        self.messages_widget = QtWidgets.QWidget()
        self.messages_layout = QtWidgets.QVBoxLayout(self.messages_widget)
        self.messages_layout.setContentsMargins(12, 12, 12, 12)
        self.messages_layout.setSpacing(10)
        self.scroll.setWidget(self.messages_widget)

        self.attachment_bar = QtWidgets.QFrame()
        self.attachment_bar.setObjectName("AttachmentBar")
        self.attachment_layout = QtWidgets.QHBoxLayout(self.attachment_bar)
        self.attachment_layout.setContentsMargins(6, 2, 6, 2)
        self.attachment_layout.setSpacing(6)
        self.attachment_bar.setMaximumHeight(46)
        self.attachment_bar.hide()

        input_row = QtWidgets.QWidget()
        input_layout = QtWidgets.QHBoxLayout(input_row)
        input_layout.setContentsMargins(0, 0, 0, 0)
        input_layout.setSpacing(8)

        self.input = ChatInput()
        self.input.setPlaceholderText("输入请求，Ctrl+Enter 发送。也可以先添加图片让 Agent 识别。")
        self.input.setFixedHeight(82)
        self.input.submit_requested.connect(self._emit_send)
        self.input.image_pasted.connect(self._add_pending_image)

        self.attach_button = QtWidgets.QPushButton("图片")
        self.attach_button.setFixedWidth(76)
        self.attach_button.clicked.connect(self._attach_images)

        self.send_button = QtWidgets.QPushButton("发送")
        self.send_button.setFixedWidth(76)
        self.send_button.clicked.connect(self._emit_send)

        self.stop_button = QtWidgets.QPushButton("停止")
        self.stop_button.setFixedWidth(76)
        self.stop_button.setEnabled(False)
        self.stop_button.clicked.connect(self.stop_requested.emit)

        buttons = QtWidgets.QVBoxLayout()
        buttons.setContentsMargins(0, 0, 0, 0)
        buttons.setSpacing(6)
        buttons.addWidget(self.attach_button)
        buttons.addWidget(self.send_button)
        buttons.addWidget(self.stop_button)

        input_layout.addWidget(self.input, 1)
        input_layout.addLayout(buttons)

        hint = QtWidgets.QLabel("Ctrl+Enter 发送")
        hint.setAlignment(alignment_flag("AlignRight"))
        hint.setObjectName("HintText")

        root.addWidget(self.scroll, 1)
        root.addWidget(self.attachment_bar)
        root.addWidget(input_row)
        root.addWidget(hint)

    def _attach_images(self) -> None:
        paths, _ = QtWidgets.QFileDialog.getOpenFileNames(
            self,
            "选择图片",
            "",
            "Images (*.png *.jpg *.jpeg *.bmp *.tif *.tiff *.webp);;All Files (*)",
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
            return

        label = QtWidgets.QLabel(f"待发送图片 {len(self.pending_images)}")
        label.setObjectName("HintText")
        self.attachment_layout.addWidget(label)
        self.attachment_layout.addWidget(ImageStrip(self.pending_images, max_thumb_size=32, compact=True), 1)
        clear_btn = QtWidgets.QPushButton("清空")
        clear_btn.setFixedWidth(52)
        clear_btn.clicked.connect(self._clear_attachments)
        self.attachment_layout.addWidget(clear_btn)
        self.attachment_bar.show()

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
        item = self.messages_layout.itemAt(self.messages_layout.count() - 1)
        if item and item.spacerItem():
            self.messages_layout.takeAt(self.messages_layout.count() - 1)

    def _scroll_to_bottom(self) -> None:
        bar = self.scroll.verticalScrollBar()
        bar.setValue(bar.maximum())
