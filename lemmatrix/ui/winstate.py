# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders
"""Remember a window's size and place, and its splitters, as they are adjusted (Josh, 20 October).

Saved a moment after each move, resize or splitter drag (and when the window hides), so the
sizes survive however the window goes: closed, or taken down with the main window.
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, QRect, QTimer
from PySide6.QtWidgets import QSplitter


def fit_to_screen(window, width: int, height: int):
    """Size a window to width x height, but never bigger than the screen it opens on (with room
    for the title bar and the taskbar), so its bottom row of buttons is always in reach."""
    scr = window.screen() if window.screen() else None
    if scr is None and window.parentWidget() is not None:
        scr = window.parentWidget().screen()
    if scr is not None:
        a = scr.availableGeometry()
        width = min(width, int(a.width() * 0.95))
        height = min(height, int(a.height() * 0.9))
    window.resize(width, height)


def _clamp(window):
    """Bring a window that is bigger than its screen, or partly off it, back inside it."""
    try:
        scr = window.screen()
    except RuntimeError:                         # gone already
        return
    if scr is None or window.isMaximized() or window.isFullScreen():
        return
    a = scr.availableGeometry()
    fr = window.frameGeometry()
    extra_w, extra_h = fr.width() - window.width(), fr.height() - window.height()
    w = min(window.width(), a.width() - extra_w)
    h = min(window.height(), a.height() - extra_h)
    if (w, h) != (window.width(), window.height()):
        window.resize(max(w, window.minimumWidth()), max(h, window.minimumHeight()))
    fr = window.frameGeometry()
    x = min(max(fr.left(), a.left()), a.right() - fr.width() + 1)
    y = min(max(fr.top(), a.top()), a.bottom() - fr.height() + 1)
    if (x, y) != (fr.left(), fr.top()):
        window.move(max(x, a.left()), max(y, a.top()))


class _Keeper(QObject):
    def __init__(self, window, prefs, key: str):
        super().__init__(window)
        self.window, self.prefs, self.key = window, prefs, key
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(400)
        self.timer.timeout.connect(self.save)
        self.restoring = False
        self.shown = False

    def splitters(self) -> list[QSplitter]:
        return self.window.findChildren(QSplitter)

    def restore(self):
        self.restoring = True
        g = self.prefs.get_bytes(self.key)
        if g:
            self.window.restoreGeometry(g)
        for sp, k in self._keyed():
            st = self.prefs.get_bytes(k)
            if st:
                way = sp.orientation()           # a state saved for another splitter never turns this one
                sp.restoreState(st)
                sp.setOrientation(way)
        self.restoring = False

    def _keyed(self):
        """(splitter, its key): named ones by name, so adding one doesn't shift the others, which
        are counted by place (as before)."""
        out, i = [], 0
        for sp in self.splitters():
            if sp.objectName():
                out.append((sp, f"{self.key}/split-{sp.objectName()}"))
            else:
                out.append((sp, f"{self.key}/split{i}"))
                i += 1
        return out

    def save(self):
        try:
            self.prefs.set_value(self.key, self.window.saveGeometry())
            for sp, k in self._keyed():
                self.prefs.set_value(k, sp.saveState())
        except RuntimeError:                    # the window has gone already
            pass

    def eventFilter(self, obj, event):
        if obj is self.window and not self.restoring:
            t = event.type()
            if t == QEvent.Show and not self.shown:
                self.shown = True                # the first show: the frame's size is known now
                QTimer.singleShot(0, lambda: _clamp(self.window))
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
