# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders. Additional terms: NOTICE.md
"""The dock for minimised windows (IDEAS.md idea 78, Josh, 26 October): a minimised window of its
own gets a little icon in a strip at the bottom of the working panels; a click brings it back; it
stays a real minimise (the taskbar and Alt+Tab keep it)."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402


def _minimise(w):
    w.setWindowState(w.windowState() | Qt.WindowMinimized)
    QApplication.processEvents()


def test_a_minimised_window_docks_and_comes_back(win):
    w = win.open_cogitate()
    QApplication.processEvents()
    _minimise(w)
    assert w in win.dock.docked()
    b = win.dock.buttons[id(w)]
    assert abs(b.fade.opacity() - 0.7) < 1e-6 and "Cogitate" in b.toolTip()
    assert not b.icon().isNull()
    b.click()
    QApplication.processEvents()
    assert w not in win.dock.docked() and not w.isMinimized()


def test_restoring_any_other_way_or_closing_undocks(win):
    w = win.open_xml_viewer()
    _minimise(w)
    assert w in win.dock.docked()
    w.showNormal()                                           # the taskbar, Alt+Tab, its shortcut
    QApplication.processEvents()
    assert w not in win.dock.docked()
    _minimise(w)
    w.close()
    QApplication.processEvents()
    assert w not in win.dock.docked()


def test_the_view_windows_and_the_notebook_dock_too(win):
    q = win.open_todos()
    win.open_notebook()
    nb = win.notebook_dialog
    for w in (q, nb):
        _minimise(w)
    assert {id(q), id(nb)} <= set(win.dock.buttons)
    assert [x for x in win.dock.docked()] == [q, nb]          # in the order minimised
    for w in (q, nb):
        w.close()
    QApplication.processEvents()
    assert not win.dock.docked()


def test_the_strip_is_under_the_working_panels(win):
    assert win.dock.height() == 30 and win.dock.isVisibleTo(win)


def test_it_comes_back_as_it_was_maximised_or_at_its_own_size(win):
    """Debug, 26 October (Josh): the dock brought a maximised window back small."""
    from PySide6.QtCore import QRect
    w = win.open_cogitate()
    w.showMaximized()
    QApplication.processEvents()
    _minimise(w)
    win.dock.buttons[id(w)].click()
    QApplication.processEvents()
    assert w.isMaximized() and not w.isMinimized()
    w.showNormal()
    w.setGeometry(QRect(140, 120, 777, 600))
    QApplication.processEvents()
    was = w.geometry()
    _minimise(w)
    win.dock.restore(w)
    QApplication.processEvents()
    assert not w.isMaximized() and w.geometry() == was
