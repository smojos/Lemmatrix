# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders. Additional terms: NOTICE.md
"""Shift + mouse wheel scrolls sideways, everywhere that scrolls (Josh, 20 October).

Qt on its own uses Shift + wheel for page-sized steps (and Alt + wheel for sideways), so one
filter on the whole program turns Shift + wheel over any scroll area (the grids, the matrices,
a text's lines, the notebook…) into a sideways scroll of its horizontal bar.
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtWidgets import QAbstractScrollArea


def _area(obj) -> QAbstractScrollArea | None:
    """The scroll area that received the wheel (on itself or its viewport), if any. A wheel on a
    widget inside the viewport reaches the viewport too, when the widget doesn't use it."""
    if isinstance(obj, QAbstractScrollArea):
        return obj
    p = obj.parentWidget() if hasattr(obj, "parentWidget") else None
    if isinstance(p, QAbstractScrollArea) and p.viewport() is obj:
        return p
    return None


def scroll_sideways(area: QAbstractScrollArea, delta: int) -> bool:
    """Scroll the area's horizontal bar for a wheel turn of `delta` (120 per notch). False if it can't."""
    bar = area.horizontalScrollBar()
    if bar is None or bar.maximum() <= bar.minimum() or not delta:
        return False
    step = max(1, bar.singleStep()) * 3
    bar.setValue(bar.value() - round(delta / 120 * step))
    return True


class ShiftWheelFilter(QObject):
    def eventFilter(self, obj, event):
        if event.type() == QEvent.Wheel and event.modifiers() & Qt.ShiftModifier \
                and not event.modifiers() & (Qt.ControlModifier | Qt.AltModifier):
            area = _area(obj)
            if area is not None:
                d = event.angleDelta()
                delta = d.y() or d.x()        # some systems already turn Shift + wheel into x
                if scroll_sideways(area, delta):
                    return True
        return False


def install(app) -> ShiftWheelFilter:
    f = ShiftWheelFilter(app)
    app.installEventFilter(f)
    return f
