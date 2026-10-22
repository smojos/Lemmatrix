# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders
"""View → Questions and View → To Do stay open beside the main window (Josh, 22 October): not modal,
minimisable, one of each, and they follow changes made in the notebook meanwhile."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["LEMMATRIX_SETTINGS"] = "Lemmatrix-tests"

from PySide6.QtCore import Qt  # noqa: E402

from test_texts import _add_text, app, win  # noqa: E402,F401


def test_questions_and_to_do_are_not_modal(win):
    from lemmatrix import notebook as nb
    s = win.doc.notebook.add_session("2026-10-02")
    s.todos = [nb.Question("open one", "2026-10-02", kind=nb.TODO)]
    for open_ in (win.open_todos, win.open_questions):
        dlg = open_()                                   # returns at once: no exec()
        assert dlg.isVisible() and not dlg.isModal()
        assert dlg.windowFlags() & Qt.WindowMinimizeButtonHint
        assert open_() is dlg                           # the same window brought forward
    todo = win.items_dialogs["todo"]
    assert todo.tree.topLevelItemCount() == 1
    s.todos.append(nb.Question("another", "2026-10-02", kind=nb.TODO))   # e.g. pushed from a token
    win.open_todos()
    assert todo.tree.topLevelItemCount() == 2
    todo.close()
    for d in win.items_dialogs.values():
        d.close()
