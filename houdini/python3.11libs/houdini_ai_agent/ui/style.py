"""Panel stylesheet."""


STYLE = """
QWidget {
    font-size: 12px;
    color: #ece7df;
    background: transparent;
}

QWidget#HoudiniAIAgentPanel {
    background: #34312d;
}

QFrame#HeaderBar {
    border: 1px solid rgba(128, 112, 84, 0.55);
    border-radius: 10px;
    background: qlineargradient(
        x1: 0, y1: 0, x2: 1, y2: 1,
        stop: 0 rgba(70, 60, 50, 0.92),
        stop: 1 rgba(50, 45, 40, 0.95)
    );
}

QFrame#ActionBar {
    background: transparent;
}

QFrame#CenterWorkspace,
QFrame#SessionSidebar,
QWidget#ContextPanel,
QFrame#ComposerBar,
QWidget#ExecutionTrace {
    border: 1px solid rgba(120, 105, 82, 0.42);
    border-radius: 10px;
    background: rgba(45, 42, 39, 0.92);
}

QFrame#CenterWorkspace {
    background: rgba(43, 40, 37, 0.96);
}

QLabel#AppTitle {
    font-size: 18px;
    font-weight: 700;
    color: #f4efe7;
}

QLabel#PanelTitle {
    font-size: 13px;
    font-weight: 700;
    color: #f1ece3;
}

QLabel#HintText {
    color: #b7ab99;
}

QLabel#StatusPill {
    color: #f3eadf;
    padding: 3px 8px;
    border: 1px solid rgba(151, 128, 94, 0.55);
    border-radius: 7px;
    background: rgba(58, 52, 46, 0.95);
}

QLabel#WelcomeText {
    color: #d9d0c4;
    padding: 18px;
    border: 1px dashed rgba(154, 136, 110, 0.55);
    border-radius: 10px;
    background: rgba(61, 55, 49, 0.5);
}

QFrame#MessageBubble {
    border: 1px solid rgba(123, 110, 92, 0.3);
    border-radius: 10px;
    background: rgba(63, 59, 55, 0.92);
}

QFrame#MessageBubble[role="user"] {
    border: 1px solid rgba(118, 132, 157, 0.5);
    background: rgba(82, 98, 120, 0.88);
}

QFrame#MessageBubble[role="thought"] {
    border: 1px solid rgba(150, 128, 93, 0.45);
    background: rgba(52, 50, 46, 0.95);
}

QLabel#MessageHeader {
    color: #d7e4f5;
    font-weight: 600;
}

QLabel#MessageBody {
    color: #f2ede6;
}

QFrame#AttachmentBar {
    border: 1px solid rgba(130, 116, 94, 0.45);
    border-radius: 8px;
    background: rgba(60, 56, 51, 0.75);
}

QFrame#ImageThumb,
QLabel#ImagePreview {
    border: 1px solid rgba(138, 122, 98, 0.45);
    border-radius: 7px;
    background: rgba(28, 27, 25, 0.98);
}

QListWidget#ConversationList {
    border: none;
    background: transparent;
}

QListWidget#ConversationList::item {
    padding: 8px 10px;
    border-radius: 7px;
    margin-bottom: 3px;
    color: #ded6ca;
}

QListWidget#ConversationList::item:hover {
    background: rgba(94, 86, 75, 0.42);
}

QListWidget#ConversationList::item:selected {
    background: rgba(92, 109, 132, 0.82);
    color: #f8f5ef;
}

QTextEdit,
QLineEdit,
QComboBox,
QListWidget,
QTreeWidget,
QPlainTextEdit {
    border: 1px solid rgba(122, 110, 90, 0.5);
    border-radius: 8px;
    background: rgba(25, 24, 23, 0.98);
    selection-background-color: rgba(102, 130, 162, 0.9);
}

QTextEdit,
QPlainTextEdit {
    padding: 6px 8px;
}

QLineEdit {
    min-height: 26px;
    padding: 0 8px;
}

QPushButton {
    min-height: 26px;
    padding: 0 11px;
    border: 1px solid rgba(137, 119, 88, 0.56);
    border-radius: 7px;
    background: qlineargradient(
        x1: 0, y1: 0, x2: 0, y2: 1,
        stop: 0 rgba(87, 75, 61, 0.92),
        stop: 1 rgba(71, 63, 54, 0.96)
    );
    color: #efe7db;
}

QPushButton:hover {
    background: qlineargradient(
        x1: 0, y1: 0, x2: 0, y2: 1,
        stop: 0 rgba(101, 87, 70, 0.96),
        stop: 1 rgba(80, 71, 60, 0.98)
    );
}

QPushButton:pressed {
    background: rgba(63, 56, 49, 0.98);
}

QPushButton:disabled {
    color: #92887b;
    border-color: rgba(94, 86, 75, 0.4);
    background: rgba(55, 51, 47, 0.75);
}

QPushButton#SidebarToggle {
    min-width: 24px;
    max-width: 24px;
    min-height: 24px;
    max-height: 24px;
    padding: 0;
    border-radius: 12px;
    background: rgba(72, 66, 58, 0.95);
}

QPushButton#SidebarToggle:hover {
    background: rgba(95, 86, 75, 0.98);
}

QToolButton {
    border: 1px solid rgba(124, 109, 86, 0.38);
    border-radius: 7px;
    padding: 4px 8px;
    background: rgba(58, 53, 48, 0.75);
    color: #e4dbcf;
}

QToolButton:hover {
    background: rgba(73, 66, 58, 0.9);
}

QComboBox {
    min-height: 26px;
    padding: 0 8px;
}

QComboBox::drop-down {
    width: 22px;
    border: none;
    background: transparent;
}

QScrollArea {
    border: none;
    background: transparent;
}

QScrollBar:vertical,
QScrollBar:horizontal {
    border: none;
    background: rgba(37, 35, 33, 0.55);
    border-radius: 6px;
    margin: 2px;
}

QScrollBar:vertical {
    width: 12px;
}

QScrollBar:horizontal {
    height: 12px;
}

QScrollBar::handle:vertical,
QScrollBar::handle:horizontal {
    background: rgba(116, 102, 81, 0.8);
    border-radius: 6px;
    min-height: 26px;
    min-width: 26px;
}

QScrollBar::handle:hover {
    background: rgba(140, 122, 95, 0.9);
}

QScrollBar::add-line,
QScrollBar::sub-line,
QScrollBar::add-page,
QScrollBar::sub-page {
    border: none;
    background: transparent;
}

QMenu {
    border: 1px solid rgba(124, 109, 86, 0.46);
    background: rgba(45, 41, 37, 0.98);
    padding: 6px;
}

QMenu::item {
    padding: 6px 18px;
    border-radius: 6px;
}

QMenu::item:selected {
    background: rgba(91, 108, 131, 0.88);
}

QGroupBox {
    margin-top: 9px;
    padding-top: 10px;
    border: 1px solid rgba(112, 98, 80, 0.45);
    border-radius: 9px;
}

QSplitter::handle {
    background: rgba(64, 60, 56, 0.55);
}

QSplitter::handle:horizontal {
    width: 5px;
}

QTableWidget {
    border: 1px solid rgba(122, 110, 90, 0.46);
    border-radius: 8px;
    background: rgba(29, 28, 26, 0.98);
    gridline-color: rgba(83, 77, 69, 0.8);
}

QHeaderView::section {
    border: none;
    padding: 6px;
    background: rgba(60, 54, 48, 0.98);
    color: #eee7dc;
}
"""
