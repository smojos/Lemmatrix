# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders. Additional terms: NOTICE.md
"""Right Shift+A plays the comparison area's α, Right Shift+B its β (Josh, 24 October), in the
window that is active (the main window, or Texts and utterances on its Texts tab).

Qt's shortcuts can't tell the right Shift from the left, so one filter on the whole application
watches the Shift keys themselves (by their scan code or key name) and, on Windows, asks the
system whether the right Shift is held now (GetAsyncKeyState, VK_RSHIFT). Left Shift+A types an A
as ever; Right Shift+A plays instead, wherever the cursor is, while the window shows a comparison
area."""

from __future__ import annotations

import sys

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtWidgets import QApplication

_VK_RSHIFT = 0xA1
# the right Shift's scan code (Windows 0x36, X11 62) or key code (Windows VK_RSHIFT, X11 Shift_R)
_RIGHT_SCANS = {0x36, 62}
_RIGHT_KEYS = {_VK_RSHIFT, 0xFFE2}
_MAC_RIGHT_SHIFT = 0x4                    # NX_DEVICERSHIFTKEYMASK in the native modifiers


def _right_shift_windows() -> bool | None:
    try:
        import ctypes
        return bool(ctypes.windll.user32.GetAsyncKeyState(_VK_RSHIFT) & 0x8000)
    except Exception:
        return None


def comparison_in(win):
    """The visible comparison area of a window, if it has one."""
    from .scratchpad import ComparisonPads
    if win is None:
        return None
    for c in win.findChildren(ComparisonPads):
        if c.isVisible():
            return c
    return None


class RightShiftFilter(QObject):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.right = False                # the right Shift is down (from its own key events)

    def right_held(self, event) -> bool:
        if sys.platform == "win32":
            state = _right_shift_windows()
            if state is not None:
                return state
        if sys.platform == "darwin":
            return bool(event.nativeModifiers() & _MAC_RIGHT_SHIFT)
        return self.right

    def eventFilter(self, obj, event):
        t = event.type()
        if t in (QEvent.KeyPress, QEvent.KeyRelease) and event.key() == Qt.Key_Shift:
            if event.nativeScanCode() in _RIGHT_SCANS or event.nativeVirtualKey() in _RIGHT_KEYS:
                self.right = t == QEvent.KeyPress
            return False
        if t == QEvent.KeyPress and event.key() in (Qt.Key_A, Qt.Key_B) \
                and event.modifiers() & Qt.ShiftModifier \
                and not event.modifiers() & (Qt.ControlModifier | Qt.AltModifier | Qt.MetaModifier) \
                and self.right_held(event):
            area = comparison_in(QApplication.activeWindow())
            if area is not None:
                if not event.isAutoRepeat():
                    area.play_key("A" if event.key() == Qt.Key_A else "B")
                return True               # not typed: it plays
        return False


def install(app) -> RightShiftFilter:
    f = RightShiftFilter(app)
    app.installEventFilter(f)
    return f
