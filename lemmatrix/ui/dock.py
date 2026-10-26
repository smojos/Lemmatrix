# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders. Additional terms: NOTICE.md
"""The dock for minimised windows (IDEAS.md idea 78, Josh, 26 October).

When one of Lemmatrix's windows of its own is minimised (Texts and utterances, Cogitate, the
notebook, Questions, To Do, Snapshots, the XML viewer, Bulk edit, Check spelling, the Whiteboard),
a little copy of its icon appears in a strip at the bottom of the main window's working panels,
70% opaque (30% transparent; full on hover), and an outline of the window flies into its place as
the visual cue. A click (or right-click → Restore) brings the window back where it was.

**The taskbar must live** (Josh): minimising stays a real minimise, so the window keeps its place
in the Windows taskbar and Alt+Tab finds it; the dock is in addition. Restoring it any way (the
taskbar, Alt+Tab, its shortcut, the dock) takes its icon out again; closing it does too.

Nothing changes in the windows themselves: the dock watches their state (an event filter).
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, QRect, QSize, Qt
from PySide6.QtWidgets import (QFrame, QGraphicsOpacityEffect, QHBoxLayout, QLabel, QMenu, QToolButton,
                               QWidget)

from . import theme

DOCK_H = 30            # the strip's height
ICON = 22              # the docked icons' size
OPACITY = 0.7          # 30% transparent (Josh); full on hover


def letters_icon(text: str, size: int = ICON):
    """A window with no icon of its own (Check spelling): its letters, underlined in red like a
    misspelling, in the theme's text colour."""
    from PySide6.QtCore import QPointF, QRectF
    from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPen, QPixmap
    pm = QPixmap(size * 2, size * 2)
    pm.setDevicePixelRatio(2.0)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    f = QFont()
    f.setPixelSize(round(size * 0.55))
    f.setBold(True)
    p.setFont(f)
    p.setPen(theme.colour("window_text"))
    p.drawText(QRectF(0, 0, size, size * 0.8), Qt.AlignCenter, text)
    p.setPen(QPen(QColor("#d93030"), max(1.2, size * 0.07)))
    y = size * 0.82
    for i in range(6):                          # a wavy underline
        p.drawLine(QPointF(size * (0.12 + i * 0.13), y + (0 if i % 2 else 2)),
                   QPointF(size * (0.25 + i * 0.13), y + (2 if i % 2 else 0)))
    p.end()
    return QIcon(pm)


class _DockButton(QToolButton):
    def __init__(self, dock: "MinimiseDock", window: QWidget, icon):
        super().__init__(dock)
        self.dock, self.window_ = dock, window
        self.setIcon(icon)
        self.setIconSize(QSize(ICON, ICON))
        self.setAutoRaise(True)
        self.setToolTip(f"{window.windowTitle()} (minimised): click to bring it back")
        self.fade = QGraphicsOpacityEffect(self)
        self.fade.setOpacity(OPACITY)
        self.setGraphicsEffect(self.fade)
        self.clicked.connect(lambda *_: dock.restore(window))
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._menu)

    def enterEvent(self, event):
        self.fade.setOpacity(1.0)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.fade.setOpacity(OPACITY)
        super().leaveEvent(event)

    def _menu(self, pos):
        m = QMenu(self)
        m.addAction("Restore").triggered.connect(lambda *_: self.dock.restore(self.window_))
        m.addAction("Close").triggered.connect(lambda *_: self.window_.close())
        m.exec(self.mapToGlobal(pos))


class MinimiseDock(QWidget):
    """The strip. watch(window, icon_fn) once for each window of its own; the rest follows."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(DOCK_H)
        self.lay = QHBoxLayout(self)
        self.lay.setContentsMargins(6, 2, 6, 2)
        self.lay.setSpacing(4)
        self.hint = QLabel("")                   # nothing docked: the strip stays, empty
        self.lay.addWidget(self.hint)
        self.lay.addStretch(1)
        self.buttons: dict[int, _DockButton] = {}
        self.icon_fns: dict[int, object] = {}
        self._filter = _StateFilter(self)
        self._flights = []
        self.setToolTip("Minimised windows dock here (they stay in the taskbar too)")

    # ---- watching ------------------------------------------------------------
    def watch(self, window: QWidget, icon_fn):
        """Dock this window when it is minimised; icon_fn() gives its icon then."""
        key = id(window)
        if key in self.icon_fns:
            return
        self.icon_fns[key] = icon_fn
        window.installEventFilter(self._filter)
        window.destroyed.connect(lambda *_, k=key: self._forget(k))

    def _forget(self, key):
        self.icon_fns.pop(key, None)
        b = self.buttons.pop(key, None)
        if b is not None:
            try:
                b.deleteLater()
            except RuntimeError:                  # the main window (and the dock) went first
                pass

    def docked(self) -> list[QWidget]:
        return [b.window_ for b in self.buttons.values()]

    # ---- docking and restoring -------------------------------------------------
    def add(self, window: QWidget, came_from: QRect | None = None):
        key = id(window)
        if key in self.buttons:
            return
        fn = self.icon_fns.get(key)
        icon = fn() if callable(fn) else window.windowIcon()
        b = _DockButton(self, window, icon)
        self.lay.insertWidget(self.lay.count() - 1, b)   # in the order minimised, before the stretch
        self.buttons[key] = b
        if came_from is not None and came_from.isValid() and self.isVisible():
            self._fly(came_from, b)

    def remove(self, window: QWidget):
        b = self.buttons.pop(id(window), None)
        if b is not None:
            b.hide()
            b.deleteLater()

    def restore(self, window: QWidget):
        window.showNormal()
        window.raise_()
        window.activateWindow()
        self.remove(window)

    # ---- the visual cue ----------------------------------------------------------
    def _fly(self, start: QRect, button: QWidget):
        """An outline of the window shrinking into its place in the dock (as a snapshot flies into the
        Snapshots button), on top of everything, in screen coordinates."""
        from PySide6.QtCore import QEasingCurve, QParallelAnimationGroup, QPropertyAnimation, QTimer
        end = QRect(button.mapToGlobal(button.rect().topLeft()), button.size())
        if end.width() <= 0:                      # not laid out yet: the strip's left end
            end = QRect(self.mapToGlobal(self.rect().topLeft()), QSize(ICON, ICON))
        box = QFrame(None, Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
                     | Qt.WindowTransparentForInput | Qt.WindowDoesNotAcceptFocus)
        box.setAttribute(Qt.WA_TranslucentBackground)
        box.setAttribute(Qt.WA_ShowWithoutActivating)
        inner = QFrame(box)
        c = theme.colour("pitch")
        inner.setStyleSheet(f"background: rgba({c.red()}, {c.green()}, {c.blue()}, 40); "
                            f"border: 3px solid {c.name()}; border-radius: 6px;")
        box.setGeometry(start)
        inner.setGeometry(box.rect())
        box.show()
        grow = QPropertyAnimation(box, b"geometry", box)
        grow.setDuration(450)
        grow.setStartValue(start)
        grow.setEndValue(end)
        grow.setEasingCurve(QEasingCurve.InCubic)
        grow.valueChanged.connect(lambda *_: inner.setGeometry(box.rect()))
        dim = QPropertyAnimation(box, b"windowOpacity", box)
        dim.setDuration(450)
        dim.setStartValue(1.0)
        dim.setEndValue(0.35)
        group = QParallelAnimationGroup(box)
        group.addAnimation(grow)
        group.addAnimation(dim)
        self._flights.append(box)

        def done():
            if box in self._flights:
                self._flights.remove(box)
            box.close()
            box.deleteLater()
        group.finished.connect(done)
        QTimer.singleShot(2000, lambda: box in self._flights and done())   # never left on screen
        group.start()


class _StateFilter(QObject):
    """Watches the windows: minimised → docked; shown normally again, or closed → undocked."""

    def __init__(self, dock: MinimiseDock):
        super().__init__(dock)
        self.dock = dock
        self.last: dict[int, QRect] = {}          # each window's place before it was minimised

    def eventFilter(self, obj, event):
        t = event.type()
        if t in (QEvent.Move, QEvent.Resize) and isinstance(obj, QWidget) and not obj.isMinimized():
            self.last[id(obj)] = obj.frameGeometry()
        elif t == QEvent.WindowStateChange and isinstance(obj, QWidget):
            if obj.isMinimized():
                self.dock.add(obj, self.last.get(id(obj)) or obj.frameGeometry())
            else:
                self.dock.remove(obj)
        elif isinstance(obj, QWidget) and (t == QEvent.Close or (t == QEvent.Hide and not event.spontaneous())):
            self.dock.remove(obj)             # closed (a minimise hides it too, but spontaneously)
        return False
