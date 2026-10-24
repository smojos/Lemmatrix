# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders. Additional terms: NOTICE.md
"""Josh's tweak of 24 October (IDEAS.md idea 14): a click on the selected token in a matrix
unselects it, as in All data; a double-click still opens it."""

import os
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["LEMMATRIX_SETTINGS"] = "Lemmatrix-tests"

from PySide6.QtCore import QEvent, QPoint, QPointF, Qt  # noqa: E402
from PySide6.QtGui import QMouseEvent  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from lemmatrix import matrix as mx  # noqa: E402
from test_ui import app, win  # noqa: E402,F401


def _settle():
    for _ in range(10):
        QApplication.processEvents()


def _send(view, kind, pos, mods=Qt.NoModifier):
    p = QPointF(pos)
    buttons = Qt.NoButton if kind == QEvent.MouseButtonRelease else Qt.LeftButton
    ev = QMouseEvent(kind, p, view.viewport().mapToGlobal(pos), Qt.LeftButton, buttons, mods)
    QApplication.sendEvent(view.viewport(), ev)


def _click(view, pos, mods=Qt.NoModifier):
    _send(view, QEvent.MouseButtonPress, pos, mods)
    _send(view, QEvent.MouseButtonRelease, pos, mods)


def _token_pos(view):
    """The middle of the first cell's first token."""
    lay = view.model_.layout_
    for (r, c), hits in lay.cells.items():
        if hits:
            rect = view.visualRect(view.model_.index(r, c))
            pos = QPoint(rect.left() + 12, rect.center().y())
            if view._hit(pos) == (r, c, 0):
                return pos, (r, c, 0)
    raise AssertionError("no token in the matrix")


def _matrix(win):
    from lemmatrix.ui.main_window import LEMMA_TAG
    win.resize(1400, 780)
    win.show()
    win.tabs.setCurrentIndex(LEMMA_TAG)
    cfg = win.config_for(LEMMA_TAG)
    cfg.x = [mx.Spec.citation()]
    win.refresh()
    _settle()
    return win._view(LEMMA_TAG)


def test_a_click_on_the_selected_token_in_a_matrix_unselects_it(win):
    view = _matrix(win)
    pos, hit = _token_pos(view)
    _click(view, pos)
    _settle()
    assert view.selected == hit and win.selected_token() is not None
    _click(view, pos)                                  # a click on the selected token...
    time.sleep(QApplication.doubleClickInterval() / 1000 + 0.1)
    _settle()
    assert view.selected is None                       # ...unselects it
    assert win.selected_token() is None
    _click(view, pos)
    _settle()
    assert view.selected == hit                        # a click selects it again


def test_a_double_click_on_the_selected_token_keeps_it_selected(win, monkeypatch):
    view = _matrix(win)
    opened = []
    monkeypatch.setattr(win, "_open_dialog", lambda *a, **k: opened.append(a))
    pos, hit = _token_pos(view)
    _click(view, pos)
    _settle()
    _send(view, QEvent.MouseButtonPress, pos)
    _send(view, QEvent.MouseButtonRelease, pos)
    _send(view, QEvent.MouseButtonDblClick, pos)
    _send(view, QEvent.MouseButtonRelease, pos)
    time.sleep(QApplication.doubleClickInterval() / 1000 + 0.1)
    _settle()
    assert opened and view.selected == hit             # opened, and still selected


def test_no_unselecting_in_edit_mode_or_with_a_modifier(win):
    view = _matrix(win)
    pos, hit = _token_pos(view)
    _click(view, pos)
    _settle()
    _click(view, pos, Qt.ShiftModifier)
    time.sleep(QApplication.doubleClickInterval() / 1000 + 0.1)
    _settle()
    assert view.selected == hit
    view.set_edit_mode(True)
    _click(view, pos)
    time.sleep(QApplication.doubleClickInterval() / 1000 + 0.1)
    _settle()
    assert view.selected == hit
    view.set_edit_mode(False)
