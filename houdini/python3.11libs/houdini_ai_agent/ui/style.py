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
        "TITLE_FONT": scaled(18, scale),
        "PANEL_FONT": scaled(13, scale),
        "CONTROL_HEIGHT": scaled(26, scale),
        "LINE_EDIT_HEIGHT": scaled(26, scale),
        "SIDEBAR_TOGGLE": scaled(24, scale),
        "TOOLBUTTON_PAD_V": scaled(4, scale),
        "TOOLBUTTON_PAD_H": scaled(8, scale),
        "INPUT_PAD_V": scaled(6, scale),
        "INPUT_PAD_H": scaled(8, scale),
        "BUTTON_PAD_H": scaled(11, scale),
        "COMBO_PAD_H": scaled(8, scale),
        "COMBO_DROPDOWN_WIDTH": scaled(22, scale),
        "LIST_PAD_V": scaled(8, scale),
        "LIST_PAD_H": scaled(10, scale),
        "SCROLLBAR_SIZE": scaled(12, scale),
        "SCROLLBAR_MIN": scaled(26, scale),
        "MENU_PAD": scaled(6, scale),
        "MENU_ITEM_PAD_V": scaled(6, scale),
        "MENU_ITEM_PAD_H": scaled(18, scale),
        "GROUP_MARGIN_TOP": scaled(9, scale),
        "GROUP_PADDING_TOP": scaled(10, scale),
        "SPLITTER_WIDTH": scaled(5, scale),
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
    font-size: @TITLE_FONT@px;
    font-weight: 700;
    color: #f4efe7;
}

QLabel#PanelTitle {
    font-size: @PANEL_FONT@px;
    font-weight: 700;
    color: #f1ece3;
}

QLabel#HintText {
    color: #b7ab99;
}

QLabel#StatusPill {
    color: #f3eadf;
    padding: @STATUS_PAD_V@px @STATUS_PAD_H@px;
    border: 1px solid rgba(151, 128, 94, 0.55);
    border-radius: 7px;
    background: rgba(58, 52, 46, 0.95);
}

QLabel#WelcomeText {
    color: #d9d0c4;
    padding: @WELCOME_PAD@px;
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

QTextBrowser#MessageBody {
    color: #f2ede6;
    border: none;
    background: transparent;
}

QTextBrowser#MessageBody a {
    color: #8ec5ff;
    text-decoration: none;
}

QTextBrowser#MessageBody a:hover {
    color: #b9ddff;
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
    padding: @LIST_PAD_V@px @LIST_PAD_H@px;
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
    padding: @INPUT_PAD_V@px @INPUT_PAD_H@px;
}

QLineEdit {
    min-height: @LINE_EDIT_HEIGHT@px;
    padding: 0 @INPUT_PAD_H@px;
}

QPushButton {
    min-height: @CONTROL_HEIGHT@px;
    padding: 0 @BUTTON_PAD_H@px;
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
    min-width: @SIDEBAR_TOGGLE@px;
    max-width: @SIDEBAR_TOGGLE@px;
    min-height: @SIDEBAR_TOGGLE@px;
    max-height: @SIDEBAR_TOGGLE@px;
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
    padding: @TOOLBUTTON_PAD_V@px @TOOLBUTTON_PAD_H@px;
    background: rgba(58, 53, 48, 0.75);
    color: #e4dbcf;
}

QToolButton:hover {
    background: rgba(73, 66, 58, 0.9);
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
    background: rgba(37, 35, 33, 0.55);
    border-radius: 6px;
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
    background: rgba(116, 102, 81, 0.8);
    border-radius: 6px;
    min-height: @SCROLLBAR_MIN@px;
    min-width: @SCROLLBAR_MIN@px;
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
    padding: @MENU_PAD@px;
}

QMenu::item {
    padding: @MENU_ITEM_PAD_V@px @MENU_ITEM_PAD_H@px;
    border-radius: 6px;
}

QMenu::item:selected {
    background: rgba(91, 108, 131, 0.88);
}

QGroupBox {
    margin-top: @GROUP_MARGIN_TOP@px;
    padding-top: @GROUP_PADDING_TOP@px;
    border: 1px solid rgba(112, 98, 80, 0.45);
    border-radius: 9px;
}

QSplitter::handle {
    background: rgba(64, 60, 56, 0.55);
}

QSplitter::handle:horizontal {
    width: @SPLITTER_WIDTH@px;
}

QTableWidget {
    border: 1px solid rgba(122, 110, 90, 0.46);
    border-radius: 8px;
    background: rgba(29, 28, 26, 0.98);
    gridline-color: rgba(83, 77, 69, 0.8);
}

QHeaderView::section {
    border: none;
    padding: @HEADER_PAD@px;
    background: rgba(60, 54, 48, 0.98);
    color: #eee7dc;
}
"""


STYLE = build_style()
