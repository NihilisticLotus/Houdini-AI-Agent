"""Panel stylesheet."""


STYLE = """
QWidget {
    font-size: 12px;
    color: #e7e4dd;
}
QWidget#HoudiniAIAgentPanel {
    background: rgba(58, 56, 53, 255);
}
QFrame#CenterWorkspace {
    border: 1px solid rgba(88, 90, 92, 110);
    border-radius: 8px;
    background: rgba(46, 45, 42, 155);
}
QFrame#HeaderBar {
    border: 1px solid rgba(104, 94, 74, 110);
    border-radius: 8px;
    background: rgba(49, 45, 40, 165);
}
QFrame#ActionBar {
    background: transparent;
}
QFrame#ComposerBar {
    border: 1px solid rgba(104, 94, 74, 100);
    border-radius: 8px;
    background: rgba(58, 52, 45, 150);
}
QFrame#SessionSidebar {
    border: 1px solid rgba(104, 94, 74, 110);
    border-radius: 8px;
    background: rgba(41, 39, 35, 145);
}
QLabel#AppTitle {
    font-size: 16px;
    font-weight: 700;
}
QFrame#MessageBubble {
    border: 1px solid rgba(120, 112, 94, 70);
    border-radius: 8px;
    background: rgba(61, 58, 54, 145);
}
QFrame#MessageBubble[role="user"] {
    background: rgba(72, 89, 108, 155);
}
QFrame#MessageBubble[role="thought"] {
    background: rgba(49, 50, 48, 120);
    border: 1px solid rgba(126, 116, 94, 95);
}
QLabel#MessageHeader {
    color: #c9d8ea;
    font-weight: 600;
}
QLabel#MessageBody {
    color: #f0ede7;
}
QLabel#WelcomeText {
    color: #d5d0c6;
    padding: 16px;
    border: 1px dashed rgba(150, 136, 112, 90);
    border-radius: 8px;
    background: rgba(56, 52, 47, 110);
}
QLabel#HintText {
    color: #b0a89b;
}
QLabel#StatusPill {
    color: #ece5d8;
    padding: 2px 6px;
    border: 1px solid rgba(128, 116, 94, 80);
    border-radius: 5px;
    background: rgba(46, 42, 37, 170);
}
QLabel#PanelTitle {
    font-weight: 700;
    font-size: 13px;
}
QLabel#ContextValue {
    color: #ece6db;
}
QFrame#ImageThumb {
    border: 1px solid rgba(128, 118, 98, 75);
    border-radius: 5px;
    background: rgba(36, 34, 32, 155);
}
QFrame#AttachmentBar {
    border: 1px solid rgba(128, 118, 98, 90);
    border-radius: 6px;
    background: rgba(54, 51, 48, 160);
}
QLabel#ImagePreview {
    border: 1px solid rgba(128, 118, 98, 90);
    border-radius: 6px;
    background: rgba(28, 27, 24, 180);
}
QListWidget#ConversationList {
    border: none;
    background: transparent;
}
QListWidget#ConversationList::item {
    padding: 8px;
    border-radius: 6px;
    margin-bottom: 2px;
}
QListWidget#ConversationList::item:selected {
    background: rgba(90, 104, 122, 170);
}
QTextEdit {
    border: 1px solid rgba(120, 112, 94, 80);
    border-radius: 8px;
    background: rgba(22, 22, 21, 210);
    selection-background-color: rgba(104, 133, 168, 160);
}
QLineEdit {
    min-height: 24px;
    border: 1px solid rgba(120, 112, 94, 80);
    border-radius: 6px;
    background: rgba(28, 28, 27, 190);
    padding: 0 8px;
}
QPushButton {
    min-height: 24px;
    padding: 0 10px;
    border: 1px solid rgba(128, 116, 94, 90);
    border-radius: 6px;
    background: rgba(70, 64, 57, 185);
}
QPushButton:hover {
    background: rgba(88, 80, 70, 195);
}
QPushButton:pressed {
    background: rgba(58, 54, 48, 205);
}
QPushButton#SidebarToggle {
    min-width: 22px;
    max-width: 22px;
    padding: 0;
    border-radius: 8px;
    background: rgba(60, 56, 50, 165);
}
QPushButton#SidebarToggle:hover {
    background: rgba(84, 78, 69, 185);
}
QComboBox {
    min-height: 24px;
    border: 1px solid rgba(120, 112, 94, 80);
    border-radius: 6px;
    background: rgba(34, 33, 31, 185);
    padding: 0 8px;
}
QGroupBox {
    margin-top: 8px;
    padding-top: 8px;
    border: 1px solid rgba(104, 94, 74, 100);
    border-radius: 8px;
}
QListWidget {
    border: 1px solid rgba(104, 94, 74, 100);
    border-radius: 8px;
    background: rgba(32, 31, 29, 170);
}
"""
