# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders
"""Remember a window's size and place, and its splitters, as they are adjusted (Josh, 20 October).

Saved a moment after each move, resize or splitter drag (and when the window hides), so the
sizes survive however the window goes: closed, or taken down with the main window.
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, QTimer
from PySide6.QtWidgets import QSplitter


class _Keeper(QObject):
    def __init__(self, window, prefs, key: str):
        super().__init__(window)
        self.window, self.prefs, self.key = window, prefs, key
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(400)
        self.timer.timeout.connect(self.save)
        self.restoring = False

    def splitters(self) -> list[QSplitter]:
        return self.window.findChildren(QSplitter)

    def restore(self):
        self.restoring = True
        g = self.prefs.get_bytes(self.key)
        if g:
            self.window.restoreGeometry(g)
        for i, sp in enumerate(self.splitters()):
            st = self.prefs.get_bytes(f"{self.key}/split{i}")
            if st:
                sp.restoreState(st)
        self.restoring = False

    def save(self):
        try:
            self.prefs.set_value(self.key, self.window.saveGeometry())
            for i, sp in enumerate(self.splitters()):
                self.prefs.set_value(f"{self.key}/split{i}", sp.saveState())
        except RuntimeError:                    # the window has gone already
            pass

    def eventFilter(self, obj, event):
        if obj is self.window and not self.restoring:
            t = event.type()
            if t in (QEvent.Resize, QEvent.Move) and self.window.isVisible():
                self.timer.start()
            elif t in (QEvent.Hide, QEvent.Close):
                self.timer.stop()
                self.save()
        return False


def keep(window, prefs, key: str):
    """Restore the window's geometry and splitter sizes under `key`, then keep them saved."""
    k = _Keeper(window, prefs, key)
    k.restore()
    window.installEventFilter(k)
    for sp in k.splitters():
        sp.splitterMoved.connect(lambda *_: None if k.restoring else k.timer.start())
    window._winstate = k
    return k
