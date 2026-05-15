"""Panel stylesheet."""

from __future__ import annotations

import os

from houdini_ai_agent.qt import QtWidgets


def resolve_ui_scale(scale: float | None = None) -> float:
    """Return a UI scale that follows the current screen DPI when possible."""
    if scale is not None:
        return _clamp_scale(scale)

    override = os.environ.get("HOUDINI_AI_AGENT_UI_SCALE", "").strip()
    if override:
        try:
            return _clamp_scale(float(override))
        except ValueError:
            pass

    detected = 1.0
    app = QtWidgets.QApplication.instance()
    if app is not None:
        screen = app.primaryScreen()
        if screen is not None:
            try:
                detected = max(detected, float(screen.logicalDotsPerInch()) / 96.0)
            except Exception:
                pass
            try:
                detected = max(detected, float(screen.devicePixelRatio()))
            except Exception:
                pass
        try:
            point_size = float(app.font().pointSizeF())
            if point_size > 0:
                detected = max(detected, point_size / 9.0)
        except Exception:
            pass
    detected = max(detected, _detect_windows_ui_scale())
    return _clamp_scale(detected)


def scaled(value: int | float, scale: float | None = None) -> int:
    return max(1, int(round(float(value) * resolve_ui_scale(scale))))


def _clamp_scale(scale: float) -> float:
    return max(1.0, min(float(scale), 2.25))


def _detect_windows_ui_scale() -> float:
    if os.name != "nt":
        return 1.0
    try:
        import ctypes

        dpi = ctypes.windll.shcore.GetDpiForSystem()
        if dpi:
            return float(dpi) / 96.0
    except Exception:
        pass
    try:
        import ctypes

        scale_percent = ctypes.windll.shcore.GetScaleFactorForDevice(0)
        if scale_percent:
            return float(scale_percent) / 100.0
    except Exception:
        pass
    try:
        import ctypes

        hdc = ctypes.windll.user32.GetDC(0)
        if not hdc:
            return 1.0
        try:
            dpi_x = ctypes.windll.gdi32.GetDeviceCaps(hdc, 88)
            if dpi_x:
                return float(dpi_x) / 96.0
        finally:
            ctypes.windll.user32.ReleaseDC(0, hdc)
    except Exception:
        pass
    return 1.0


def build_style(scale: float | None = None) -> str:
    scale = resolve_ui_scale(scale)
    values = {
        "BASE_FONT": scaled(12, scale),
        "SMALL_FONT": scaled(10, scale),
        "TITLE_FONT": scaled(13, scale),
        "PANEL_FONT": scaled(12, scale),
        "CONTROL_HEIGHT": scaled(24, scale),
        "LINE_EDIT_HEIGHT": scaled(24, scale),
        "SIDEBAR_TOGGLE": scaled(8, scale),
        "TOOLBUTTON_PAD_V": scaled(4, scale),
        "TOOLBUTTON_PAD_H": scaled(8, scale),
        "INPUT_PAD_V": scaled(6, scale),
        "INPUT_PAD_H": scaled(8, scale),
        "BUTTON_PAD_H": scaled(9, scale),
        "COMBO_PAD_H": scaled(8, scale),
        "COMBO_DROPDOWN_WIDTH": scaled(22, scale),
        "LIST_PAD_V": scaled(6, scale),
        "LIST_PAD_H": scaled(8, scale),
        "SCROLLBAR_SIZE": scaled(10, scale),
        "SCROLLBAR_MIN": scaled(22, scale),
        "MENU_PAD": scaled(6, scale),
        "MENU_ITEM_PAD_V": scaled(6, scale),
        "MENU_ITEM_PAD_H": scaled(18, scale),
        "GROUP_MARGIN_TOP": scaled(9, scale),
        "GROUP_PADDING_TOP": scaled(10, scale),
        "SPLITTER_WIDTH": scaled(4, scale),
        "HEADER_PAD": scaled(6, scale),
        "STATUS_PAD_V": scaled(3, scale),
        "STATUS_PAD_H": scaled(8, scale),
        "WELCOME_PAD": scaled(18, scale),
    }
    style = _STYLE_TEMPLATE
    for key, value in values.items():
        style = style.replace(f"@{key}@", str(value))
    return style


_STYLE_TEMPLATE = """
QWidget {
    font-size: @BASE_FONT@px;
    color: #eceff3;
    background: transparent;
}

QWidget#HoudiniAIAgentPanel {
    background: #1f2022;
}

QFrame#HeaderBar {
    border: none;
    border-bottom: 1px solid #2b2d31;
    border-radius: 0;
    background: #191a1c;
}

QFrame#ActionBar {
    border: none;
    border-bottom: 1px solid #2b2d31;
    border-radius: 0;
    background: #202123;
}

QFrame#CenterWorkspace,
QWidget#ContextPanel,
QFrame#ComposerBar,
QWidget#ExecutionTrace {
    border: none;
    border-radius: 0;
    background: #1f2022;
}

QFrame#CenterWorkspace {
    background: #1f2022;
}

QWidget#ContextPanel {
    border-left: 1px solid #2b2d31;
    background: #202123;
}

QFrame#ComposerBar {
    border-top: 1px solid #303238;
    background: #202123;
}

QFrame#ConversationTabsBar {
    border: none;
    border-bottom: 1px solid #2b2d31;
    border-radius: 0;
    background: #1f2022;
}

QTabBar#ConversationTabBar {
    qproperty-drawBase: 0;
    background: transparent;
}

QTabBar#ConversationTabBar::tab {
    min-width: 58px;
    max-width: 118px;
    min-height: 15px;
    max-height: 15px;
    padding: 0 6px;
    margin-right: 2px;
    border: 1px solid #343741;
    border-bottom-color: #2b2d31;
    border-top-left-radius: 4px;
    border-top-right-radius: 4px;
    background: #202123;
    color: #aeb4bf;
    font-size: @SMALL_FONT@px;
}

QTabBar#ConversationTabBar::tab:selected {
    background: #273552;
    color: #f3f6fb;
    border-color: #2d7fe7;
    border-bottom-color: #273552;
}

QTabBar#ConversationTabBar::tab:hover:!selected {
    background: #25272b;
    color: #e1e5ec;
}

QPushButton#TabAddButton {
    font-weight: 700;
    border-radius: 4px;
    padding: 0;
    font-size: @SMALL_FONT@px;
}

QLabel#AppTitle {
    font-size: @TITLE_FONT@px;
    font-weight: 700;
    color: #f3f5f7;
}

QLabel#PanelTitle {
    font-size: @PANEL_FONT@px;
    font-weight: 700;
    color: #e7eaf0;
}

QLabel#HintText {
    color: #8c929d;
}

QLabel#StatusPill {
    color: #d8e5ff;
    padding: @STATUS_PAD_V@px @STATUS_PAD_H@px;
    border: 1px solid rgba(68, 113, 190, 0.55);
    border-radius: 5px;
    background: rgba(40, 65, 112, 0.55);
}

QLabel#ContextUsageChip {
    color: #cfe1ff;
    padding: @STATUS_PAD_V@px @STATUS_PAD_H@px;
    border: 1px solid rgba(68, 113, 190, 0.45);
    border-radius: 5px;
    background: rgba(29, 54, 96, 0.42);
}

QLabel#WelcomeText {
    color: #cfd5df;
    padding: @WELCOME_PAD@px;
    border: none;
    border-left: 2px solid #4a90e2;
    border-radius: 0;
    background: transparent;
}

QFrame#MessageBubble {
    border: none;
    border-left: 2px solid #3a3d44;
    border-radius: 0;
    background: transparent;
}

QFrame#MessageBubble[role="user"] {
    border: 1px solid rgba(76, 112, 178, 0.35);
    border-radius: 6px;
    background: rgba(37, 45, 59, 0.72);
}

QFrame#MessageBubble[role="thought"] {
    border: none;
    border-left: 2px solid #6b5f3f;
    background: transparent;
}

QFrame#ThoughtBubble {
    border: none;
    border-left: 2px solid #3f6b5f;
    border-radius: 0;
    background: transparent;
}

QToolButton#ThoughtToggle {
    color: #cfd5df;
    font-weight: 600;
    padding: 1px 4px;
    background: transparent;
}

QToolButton#ThoughtToggle:hover {
    background: transparent;
    color: #f0f5f2;
}

QLabel#ThoughtPreview {
    color: #aeb6c2;
    padding-left: 18px;
}

QLabel#ThoughtBody {
    color: #bfc7d2;
    padding-left: 18px;
}

QFrame#MessageBubble[role="plan"] {
    border: 1px solid rgba(54, 151, 121, 0.35);
    border-radius: 6px;
    background: rgba(28, 45, 41, 0.48);
}

QFrame#PlanCard {
    border: none;
    background: transparent;
}

QFrame#PlanTodoBox {
    border: 1px solid #444961;
    border-radius: 5px;
    background: rgba(22, 24, 34, 0.72);
}

QLabel#MessageHeader {
    color: #9ca3af;
    font-weight: 600;
}

QLabel#MessageBody {
    color: #edf1f5;
}

QTextBrowser#MessageBody {
    color: #f2ede6;
    border: none;
    background: transparent;
}

QTextBrowser#MessageBody a {
    color: #7db7ff;
    text-decoration: none;
}

QTextBrowser#MessageBody a:hover {
    color: #acd2ff;
}

QFrame#AttachmentBar {
    border: none;
    border-top: 1px solid #2c2f36;
    border-radius: 0;
    background: transparent;
}

QFrame#TodoBar {
    border: none;
    border-bottom: 1px solid #2c2f36;
    border-radius: 0;
    background: rgba(25, 27, 31, 0.72);
}

QLabel#TodoChip {
    color: #d8e5ff;
    padding: @STATUS_PAD_V@px @STATUS_PAD_H@px;
    border: 1px solid rgba(68, 113, 190, 0.42);
    border-radius: 5px;
    background: rgba(36, 48, 69, 0.72);
}

QFrame#PromptDock {
    border: 1px solid #1493ff;
    border-radius: 7px;
    background: #1a1b1d;
}

QTextEdit#PromptInput {
    border: none;
    border-radius: 0;
    background: transparent;
    color: #e8edf3;
}

QTextEdit#PromptInput:focus {
    border: none;
}

QWidget#ChatSurface {
    background: transparent;
}

QFrame#ImageThumb,
QLabel#ImagePreview {
    border: 1px solid #343741;
    border-radius: 5px;
    background: #17181a;
}

QListWidget#ConversationList {
    border: none;
    background: transparent;
}

QListWidget#ConversationList::item {
    padding: @LIST_PAD_V@px @LIST_PAD_H@px;
    border-radius: 5px;
    margin-bottom: 2px;
    color: #cfd5df;
}

QListWidget#ConversationList::item:hover {
    background: #2a2d33;
}

QListWidget#ConversationList::item:selected {
    background: #273b5d;
    color: #f4f7fb;
}

QTextEdit,
QLineEdit,
QComboBox,
QListWidget,
QTreeWidget,
QPlainTextEdit {
    border: 1px solid #343741;
    border-radius: 5px;
    background: #18191b;
    selection-background-color: #245ea8;
}

QTextEdit,
QPlainTextEdit {
    padding: @INPUT_PAD_V@px @INPUT_PAD_H@px;
}

QLineEdit {
    min-height: @LINE_EDIT_HEIGHT@px;
    padding: 0 @INPUT_PAD_H@px;
}

QPushButton {
    min-height: @CONTROL_HEIGHT@px;
    padding: 0 @BUTTON_PAD_H@px;
    border: 1px solid #343741;
    border-radius: 5px;
    background: #25272b;
    color: #dce2ea;
}

QPushButton:hover {
    border-color: #4b5565;
    background: #2b2e34;
}

QPushButton:pressed {
    background: #1d1f23;
}

QPushButton:disabled {
    color: #737985;
    border-color: #2b2e34;
    background: #202226;
}

QPushButton#PrimaryButton {
    border-color: #4b5565;
    background: #2a2d33;
    color: #f3f8ff;
    font-weight: 600;
}

QPushButton#PrimaryButton:hover {
    border-color: #1493ff;
    background: #303641;
}

QPushButton#GhostButton {
    border: none;
    border-radius: 5px;
    background: transparent;
    color: #b9c0cc;
}

QPushButton#GhostButton:hover {
    background: #2a2d33;
    color: #eef2f7;
}

QPushButton#SidebarToggle {
    min-width: @SIDEBAR_TOGGLE@px;
    max-width: @SIDEBAR_TOGGLE@px;
    min-height: 54px;
    max-height: 54px;
    padding: 0;
    border: 1px solid rgba(91, 100, 114, 0.36);
    border-radius: 4px;
    background: rgba(36, 38, 42, 0.86);
    color: #8b94a3;
    font-size: @SMALL_FONT@px;
}

QPushButton#SidebarToggle:hover {
    border-color: rgba(45, 127, 231, 0.58);
    background: rgba(45, 52, 66, 0.95);
    color: #d8e5ff;
}

QToolButton {
    border: none;
    border-radius: 5px;
    padding: @TOOLBUTTON_PAD_V@px @TOOLBUTTON_PAD_H@px;
    background: transparent;
    color: #b9c0cc;
}

QToolButton:hover {
    background: #2a2d33;
    color: #eef2f7;
}

QComboBox {
    min-height: @CONTROL_HEIGHT@px;
    padding: 0 @COMBO_PAD_H@px;
}

QComboBox::drop-down {
    width: @COMBO_DROPDOWN_WIDTH@px;
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
    background: transparent;
    border-radius: 5px;
    margin: 2px;
}

QScrollBar:vertical {
    width: @SCROLLBAR_SIZE@px;
}

QScrollBar:horizontal {
    height: @SCROLLBAR_SIZE@px;
}

QScrollBar::handle:vertical,
QScrollBar::handle:horizontal {
    background: #454952;
    border-radius: 5px;
    min-height: @SCROLLBAR_MIN@px;
    min-width: @SCROLLBAR_MIN@px;
}

QScrollBar::handle:hover {
    background: #5a606b;
}

QScrollBar::add-line,
QScrollBar::sub-line,
QScrollBar::add-page,
QScrollBar::sub-page {
    border: none;
    background: transparent;
}

QMenu {
    border: 1px solid #343741;
    background: #202123;
    padding: @MENU_PAD@px;
}

QMenu::item {
    padding: @MENU_ITEM_PAD_V@px @MENU_ITEM_PAD_H@px;
    border-radius: 6px;
}

QMenu::item:selected {
    background: #273b5d;
}

QGroupBox {
    margin-top: @GROUP_MARGIN_TOP@px;
    padding-top: @GROUP_PADDING_TOP@px;
    border: none;
    border-top: 1px solid #343741;
    border-radius: 0;
    color: #9ca3af;
}

QLabel#ContextValue {
    color: #d8dee8;
}

QWidget#ExecutionTrace QListWidget {
    border: none;
    border-top: 1px solid #343741;
    background: #1f2022;
}

QSplitter::handle {
    background: #24262a;
}

QSplitter::handle:horizontal {
    width: @SPLITTER_WIDTH@px;
}

QSplitter::handle:horizontal:hover {
    background: #2b2e35;
}

QTableWidget {
    border: 1px solid #343741;
    border-radius: 5px;
    background: #1f2022;
    gridline-color: #343741;
}

QHeaderView::section {
    border: none;
    padding: @HEADER_PAD@px;
    background: #25272b;
    color: #e8edf3;
}

QFrame#ToolResultCard {
    border: 1px solid #343741;
    border-radius: 6px;
    background: rgba(30, 32, 38, 0.85);
}

QLabel#ToolStatusIcon {
    font-size: 14px;
    font-weight: 700;
}

QLabel#ToolResultTitle {
    font-weight: 600;
    color: #e8edf3;
}

QLabel#ToolResultMessage {
    color: #cfd5df;
}

QLabel#ToolResultEvent {
    color: #aeb4bf;
}

QLabel#ToolResultWarning {
    color: #ff9800;
}

QLabel#ToolResultError {
    color: #f44336;
}

QLabel#ToolResultPaths {
    color: #8c929d;
    font-size: @SMALL_FONT@px;
}

QFrame#ParamDiffView {
    border: 1px solid #343741;
    border-radius: 6px;
    background: rgba(28, 30, 36, 0.90);
}

QFrame#ParamDiffRow {
    border: none;
    border-bottom: 1px solid #2b2d31;
    border-radius: 0;
    background: transparent;
}

QLabel#ParamDiffNode {
    color: #61afef;
    font-size: @SMALL_FONT@px;
}

QLabel#ParamDiffParm {
    color: #e5c07b;
    font-weight: 600;
    font-size: @SMALL_FONT@px;
}

QLabel#ParamDiffArrow {
    color: #5c6370;
    font-weight: 700;
}

QFrame#TokenStatsFrame {
    border: 1px solid #343741;
    border-radius: 5px;
    background: rgba(25, 27, 31, 0.72);
}

QLabel#TokenStatValue {
    color: #e8edf3;
    font-weight: 700;
    font-size: @TITLE_FONT@px;
}

QTableWidget#TokenTable {
    border: 1px solid #343741;
    border-radius: 5px;
    background: #1f2022;
    gridline-color: #2b2d31;
    font-size: @SMALL_FONT@px;
}

QListWidget#NodeCompleter {
    border: 1px solid #4b5565;
    border-radius: 6px;
    background: #25272b;
    padding: @LIST_PAD_V@px 0;
    outline: none;
}

QListWidget#NodeCompleter::item {
    padding: @LIST_PAD_V@px @LIST_PAD_H@px;
    color: #dce2ea;
}

QListWidget#NodeCompleter::item:hover,
QListWidget#NodeCompleter::item:selected {
    background: #273b5d;
    color: #f4f7fb;
    border-radius: 3px;
}

QFrame#CodePreviewWidget {
    border: 1px solid #343741;
    border-radius: 6px;
    background: #1a1b1d;
}

QTextBrowser#CodeDisplay {
    border: none;
    border-radius: 0;
    background: transparent;
    color: #abb2bf;
    padding: @INPUT_PAD_V@px @INPUT_PAD_H@px;
    selection-background-color: #3e4451;
}
"""


STYLE = build_style()
