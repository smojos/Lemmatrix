# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders. Additional terms: NOTICE.md
"""Behaviour several views share, written once (the audit, section 8, step 4; 26 October).

WheelZoom: Ctrl + mouse wheel zooms, Ctrl+0 back to normal (the grids, the matrices and a text's
lines; Josh, 21 and 24 October). Each view keeps its own set_zoom (what grows differs); this is the
wheel, the key and the limits.

ClickUnselect: a plain click on the selected row or token unselects it (All data and the matrices;
IDEAS.md idea 14), after the double-click interval so the first click of a double-click (which
opens) never unselects. Each view says what is selected (_unselect_key) and how to unselect it.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QApplication


class WheelZoom:
    ZOOM_MIN, ZOOM_MAX, ZOOM_STEP = 0.6, 2.5, 1.1
    zoom = 1.0

    def set_zoom(self, zoom: float):
        raise NotImplementedError

    def clamp_zoom(self, zoom: float) -> float:
        return max(self.ZOOM_MIN, min(self.ZOOM_MAX, zoom))

    def wheelEvent(self, event):
        if event.modifiers() & Qt.ControlModifier:
            d = event.angleDelta().y() or event.angleDelta().x()
            if d:
                self.set_zoom(self.zoom * (self.ZOOM_STEP ** (d / 120)))
            event.accept()
            return
        super().wheelEvent(event)

    def zoom_key(self, event) -> bool:
        """Ctrl+0: the zoom back to normal. True if it was that key (the caller returns)."""
        if event.key() == Qt.Key_0 and event.modifiers() & Qt.ControlModifier:
            self.set_zoom(1.0)
            return True
        return False


class ClickUnselect:
    _unselect_on_release = False
    _pending_unselect = None

    def _unselect_key(self):
        """What is selected now (compared when the wait is over)."""
        return True

    def _unselect(self):
        raise NotImplementedError

    def _arm_unselect(self, on: bool):
        """In mousePressEvent: this click, if it stays a single click, unselects."""
        self._unselect_on_release = bool(on)

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        if self._unselect_on_release:
            self._unselect_on_release = False
            self._pending_unselect = self._unselect_key()
            QTimer.singleShot(QApplication.doubleClickInterval() + 10, self._unselect_if_still)

    def _cancel_unselect(self):
        """A double-click opens; it never unselects."""
        self._pending_unselect = None

    def _unselect_if_still(self):
        pending, self._pending_unselect = self._pending_unselect, None
        if pending is not None and pending == self._unselect_key():
            self._unselect()
