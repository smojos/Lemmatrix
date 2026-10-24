# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders. Additional terms: NOTICE.md
"""Josh's tweaks of 24 October (IDEAS.md idea 14): a click on the selected token in a matrix
unselects it, as in All data (a double-click still opens it); Ctrl + mouse wheel zooms the grids."""

import os
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["LEMMATRIX_SETTINGS"] = "Lemmatrix-tests"

from PySide6.QtCore import QEvent, QPoint, QPointF, Qt  # noqa: E402
from PySide6.QtGui import QMouseEvent  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from lemmatrix import matrix as mx  # noqa: E402
from test_ui import app, win  # noqa: E402,F401


import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def _no_modifiers_left(app):
    """A synthetic Ctrl+0 leaves Qt thinking Ctrl is still held, which changes later tests' clicks
    (the token dialogue's Ctrl+click); a key press with no modifier clears it."""
    yield
    from PySide6.QtGui import QKeyEvent
    from PySide6.QtWidgets import QWidget
    w = QWidget()
    QApplication.sendEvent(w, QKeyEvent(QEvent.KeyPress, Qt.Key_unknown, Qt.NoModifier))
    w.deleteLater()
    _settle()


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


# ---- Ctrl + mouse wheel zoom in the grids (idea 14, Josh, 24 October) ------------------------

def _wheel(view, steps, mods=Qt.ControlModifier):
    from PySide6.QtCore import QPoint as P
    from PySide6.QtGui import QWheelEvent
    pos = QPointF(view.viewport().rect().center())
    ev = QWheelEvent(pos, view.viewport().mapToGlobal(pos), P(0, 0), P(0, 120 * steps),
                     Qt.NoButton, mods, Qt.NoScrollPhase, False)
    QApplication.sendEvent(view.viewport(), ev)


def test_ctrl_wheel_zooms_the_grids_and_ctrl_0_resets(win):
    from PySide6.QtGui import QKeyEvent
    win.resize(1400, 780)
    win.show()
    _settle()
    for t in (win.lemmas, win.all_table):
        pt = t.font().pointSizeF()
        ipa = t.model_.ipa.pointSizeF()
        row_h = t.verticalHeader().defaultSectionSize()
        w0 = t.horizontalHeader().sectionSize(0)
        _wheel(t, 3)
        _settle()
        assert t.zoom > 1.3
        assert t.font().pointSizeF() > pt and t.model_.ipa.pointSizeF() > ipa
        assert t.verticalHeader().defaultSectionSize() > row_h
        assert t.horizontalHeader().sectionSize(0) > w0
        QApplication.sendEvent(t, QKeyEvent(QEvent.KeyPress, Qt.Key_0, Qt.ControlModifier))
        _settle()
        assert t.zoom == 1.0 and abs(t.font().pointSizeF() - pt) < 0.01
        assert abs(t.model_.ipa.pointSizeF() - ipa) < 0.01
        assert t.verticalHeader().defaultSectionSize() == row_h
        assert abs(t.horizontalHeader().sectionSize(0) - w0) <= 2


def test_each_grid_has_its_own_zoom_and_a_plain_wheel_still_scrolls(win):
    win.resize(1400, 780)
    win.show()
    _settle()
    _wheel(win.lemmas, 2)
    assert win.lemmas.zoom > 1.1 and win.all_table.zoom == 1.0
    _wheel(win.all_table, -1, Qt.NoModifier)
    assert win.all_table.zoom == 1.0
    _wheel(win.lemmas, -20)
    assert win.lemmas.zoom == win.lemmas.ZOOM_MIN
    win.lemmas.set_zoom(1.0)

