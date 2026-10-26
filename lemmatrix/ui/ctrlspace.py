# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders. Additional terms: NOTICE.md
"""Ctrl+Space plays (Ctrl+Shift+Space: the pitch; Ctrl+Alt+Space opens in Praat) from inside any text
field, whatever the keyboard.

Josh, 19 October: with an IPA keyboard (Keyman's SIL IPA) Ctrl+Space typed a space in the
fields and search bars instead of playing. Keyman lets go of Ctrl for a moment while it sends
the character it makes, so the space reaches Lemmatrix without Ctrl, and the shortcut never
fires. The keyboard itself is left alone (it's needed to type IPA into the searches).

One filter on the whole application catches a space typed into a text field while Ctrl is
held. Whether Ctrl is held is asked of the operating system as it is now (on Windows,
GetAsyncKeyState), not taken from the key event, which Keyman has already changed. The space
is dropped and the window's own Ctrl+Space (or Ctrl+Shift+Space) shortcut is run instead, so
each window plays what it always played.
"""

from __future__ import annotations

import sys
import time

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtGui import QAction, QGuiApplication, QKeySequence, QShortcut
from PySide6.QtWidgets import QAbstractSpinBox, QComboBox, QLineEdit, QPlainTextEdit, QTextEdit, QWidget

TEXT_WIDGETS = (QLineEdit, QTextEdit, QPlainTextEdit, QAbstractSpinBox, QComboBox)
PLAY = QKeySequence("Ctrl+Space")
PLAY_PITCH = QKeySequence("Ctrl+Shift+Space")
PRAAT = QKeySequence("Ctrl+Alt+Space")      # Open in Praat (26 October: a field ate it too)

_VK_SHIFT, _VK_CONTROL, _VK_MENU = 0x10, 0x11, 0x12


def _held_windows() -> tuple[bool, bool, bool] | None:
    try:
        import ctypes
        get = ctypes.windll.user32.GetAsyncKeyState
        return tuple(bool(get(vk) & 0x8000) for vk in (_VK_CONTROL, _VK_SHIFT, _VK_MENU))
    except Exception:
        return None


def held() -> tuple[bool, bool, bool]:
    """(Ctrl, Shift, Alt) as they are held now."""
    if sys.platform == "win32":
        state = _held_windows()
        if state is not None:
            return state
    m = QGuiApplication.queryKeyboardModifiers()
    return bool(m & Qt.ControlModifier), bool(m & Qt.ShiftModifier), bool(m & (Qt.AltModifier | Qt.MetaModifier))


def _live(owner, win) -> bool:
    """A shortcut's or action's owner belongs to this window and is showing. (A closed dialogue
    is kept, hidden, as a child of the main window: its Ctrl+Space played the token it last
    showed, whatever was selected. Josh, 19 October.)"""
    return isinstance(owner, QWidget) and owner.window() is win and owner.isVisible()


def find_shortcut(widget: QWidget, pitch: bool, praat: bool = False):
    """The Ctrl+Space (pitch: Ctrl+Shift+Space; praat: Ctrl+Alt+Space) shortcut or action of
    `widget`'s window, or None."""
    win = widget.window()
    seq = PRAAT if praat else PLAY_PITCH if pitch else PLAY
    for sc in win.findChildren(QShortcut):
        if sc.key() == seq and sc.isEnabled() and _live(sc.parent(), win):
            return sc
    for act in dict.fromkeys([*win.actions(), *win.findChildren(QAction)]):
        if seq in act.shortcuts() and act.isEnabled() and _live(act.parent(), win):
            return act
    return None


def run_shortcut(widget: QWidget, pitch: bool, praat: bool = False) -> bool:
    """Run the Ctrl+Space (pitch: Ctrl+Shift+Space; praat: Ctrl+Alt+Space) shortcut of `widget`'s window."""
    found = find_shortcut(widget, pitch, praat)
    if found is None:
        return False
    if isinstance(found, QShortcut):
        found.activated.emit()
    else:
        found.trigger()
    return True


class CtrlSpaceFilter(QObject):
    """Installed on the application (install())."""

    def __init__(self, parent=None, held_fn=None):
        super().__init__(parent)
        self.held = held_fn or held
        self._last = 0.0

    def _modifiers(self, event) -> tuple[bool, bool, bool]:
        ctrl, shift, alt = self.held()
        m = event.modifiers() if hasattr(event, "modifiers") else Qt.NoModifier
        return (ctrl or bool(m & Qt.ControlModifier), shift or bool(m & Qt.ShiftModifier),
                alt or bool(m & (Qt.AltModifier | Qt.MetaModifier)))

    def eventFilter(self, obj, event):
        t = event.type()
        if t not in (QEvent.ShortcutOverride, QEvent.KeyPress, QEvent.InputMethod):
            return False
        if not isinstance(obj, TEXT_WIDGETS):
            return False
        if t == QEvent.InputMethod:
            if event.commitString() != " " or event.preeditString():
                return False
        elif not (event.key() == Qt.Key_Space or event.text() == " "):
            return False
        ctrl, shift, alt = self._modifiers(event)
        if not ctrl:
            return False
        praat = alt and not shift                 # Ctrl+Alt+Space: Open in Praat (26 October). Ctrl+Alt is
        if alt and not praat:                     # also AltGr on Windows, so it is only taken where the
            return False                          # window has the Praat key; elsewhere left to the field
        if find_shortcut(obj, shift, praat) is None:   # nothing to play in this window: the key is left
            return False                          # to the field (it used to be swallowed; 25 October)
        if t == QEvent.ShortcutOverride:          # handled on the key press, so only once
            event.accept()
            return True
        if t == QEvent.KeyPress and event.isAutoRepeat():
            return True
        now = time.monotonic()
        if now - self._last > 0.12:               # the same press reaching us twice
            self._last = now
            run_shortcut(obj, shift, praat)
        event.accept()
        return True


def install(app) -> CtrlSpaceFilter:
    f = CtrlSpaceFilter(app)
    app.installEventFilter(f)
    return f
