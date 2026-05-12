"""Qt compatibility helpers for Houdini builds."""

try:
    from PySide6 import QtCore, QtGui, QtWidgets

    PYSIDE_VERSION = 6
except ImportError:
    try:
        from PySide2 import QtCore, QtGui, QtWidgets

        PYSIDE_VERSION = 2
    except ImportError:
        PYSIDE_VERSION = 0

        class _FallbackSignal:
            def __init__(self, *args, **kwargs):
                self._slots = []

            def connect(self, slot):
                self._slots.append(slot)

            def emit(self, *args, **kwargs):
                for slot in list(self._slots):
                    slot(*args, **kwargs)

        class _FallbackQObject:
            def __init__(self, *args, **kwargs):
                pass

        class _FallbackQLocale:
            @staticmethod
            def system():
                return _FallbackQLocale()

            def name(self):
                return "en_US"

        class _FallbackQt:
            Key_Return = 16777220
            Key_Enter = 16777221
            AltModifier = 0x08000000
            TextSelectableByMouse = 1
            LinksAccessibleByMouse = 2
            RichText = 1
            ToolButtonTextBesideIcon = 0
            RightArrow = 1
            DownArrow = 2

        class _FallbackQtCore:
            QObject = _FallbackQObject
            Signal = _FallbackSignal
            QLocale = _FallbackQLocale
            Qt = _FallbackQt

            class QTimer:
                @staticmethod
                def singleShot(_msec, callback):
                    callback()

        class _UnavailableQtModule:
            def __getattr__(self, name):
                raise RuntimeError(
                    "PySide2/PySide6 is required for Houdini AI Agent UI widgets. "
                    "Core session tests can run without Qt, but the panel must run inside Houdini or a PySide environment."
                )

        QtCore = _FallbackQtCore()
        QtGui = _UnavailableQtModule()
        QtWidgets = _UnavailableQtModule()


def alignment_flag(name):
    """Return a Qt alignment flag that works across PySide2 and PySide6."""
    if PYSIDE_VERSION == 0:
        return getattr(QtCore.Qt, name)
    if PYSIDE_VERSION >= 6:
        return getattr(QtCore.Qt.AlignmentFlag, name)
    return getattr(QtCore.Qt, name)


def word_wrap_flag():
    if PYSIDE_VERSION == 0:
        return 0
    if PYSIDE_VERSION >= 6:
        return QtGui.QTextOption.WrapMode.WordWrap
    return QtGui.QTextOption.WordWrap
