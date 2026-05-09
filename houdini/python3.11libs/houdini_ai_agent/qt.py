"""Qt compatibility helpers for Houdini builds."""

try:
    from PySide6 import QtCore, QtGui, QtWidgets

    PYSIDE_VERSION = 6
except ImportError:
    from PySide2 import QtCore, QtGui, QtWidgets

    PYSIDE_VERSION = 2


def alignment_flag(name):
    """Return a Qt alignment flag that works across PySide2 and PySide6."""
    if PYSIDE_VERSION >= 6:
        return getattr(QtCore.Qt.AlignmentFlag, name)
    return getattr(QtCore.Qt, name)


def word_wrap_flag():
    if PYSIDE_VERSION >= 6:
        return QtGui.QTextOption.WrapMode.WordWrap
    return QtGui.QTextOption.WordWrap
