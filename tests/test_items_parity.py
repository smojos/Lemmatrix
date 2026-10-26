# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders. Additional terms: NOTICE.md
"""View → Questions and View → To Do have the notebook tabs' actions and the tabs the windows'
(Josh, 26 October: the tab is the window filtered to its day); one set of actions (ItemActions)."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from lemmatrix import notebook as nb  # noqa: E402


def _texts(menu_items):
    return [t for t, *_ in menu_items]


def test_one_set_of_actions_in_both(win):
    from lemmatrix.ui.notebook_dialog import ItemActions, ItemsDialog, ItemsPanel
    for name in ("add", "edit", "delete", "toggle", "toggle_pin", "convert", "to_hypothesis",
                 "link_to_hypothesis", "go_to_token", "_menu"):
        assert name in ItemActions.__dict__
        assert name not in ItemsPanel.__dict__ and name not in ItemsDialog.__dict__, name


def test_the_same_menu_in_the_window_and_the_tab(win):
    from lemmatrix.ui.notebook_dialog import QuestionsDialog
    s = win.doc.notebook.add_session(win.work_date())
    s.questions = [nb.Question("Why?", s.date)]
    dlg = QuestionsDialog(win)
    dlg.tree.setCurrentItem(dlg.tree.topLevelItem(0))
    win.open_notebook(s.date)
    panel = win.notebook_dialog.q_panel
    panel.fill(s.questions[0])
    view_menu = _texts(dlg._menu_items(dlg.current()))
    tab_menu = _texts(panel._menu_items(panel.current()))
    assert [t for t in view_menu if t != "Open in notebook"] == tab_menu
    assert "Delete question" in view_menu and "Link to hypothesis…" in view_menu
    dlg.reject()


def test_delete_from_view_and_the_notebook_follows(win, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    from lemmatrix.ui.notebook_dialog import TodoDialog
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.Yes)
    s = win.doc.notebook.add_session(win.work_date())
    s.todos = [nb.Question("Do it", s.date, kind=nb.TODO), nb.Question("And this", s.date, kind=nb.TODO)]
    win.open_notebook(s.date)
    nbw = win.notebook_dialog
    assert nbw.t_panel.tree.topLevelItemCount() == 2
    dlg = TodoDialog(win)
    dlg.tree.setCurrentItem(dlg.tree.topLevelItem(0))
    assert dlg.delete_btn.isEnabled() and dlg.link_btn is not None
    dlg.delete()
    assert [q.text for q in s.todos] == ["And this"] and win.doc.dirty
    assert nbw.t_panel.tree.topLevelItemCount() == 1              # the open notebook follows
    dlg.reject()


def test_tab_add_goes_on_its_day_and_view_windows_follow(win, monkeypatch):
    from lemmatrix.ui import notebook_dialog as nd
    s = win.doc.notebook.add_session("2026-10-02")
    view = win.open_todos()
    monkeypatch.setattr(nd, "ask_text", lambda *a, **k: "Check D002")
    win.open_notebook("2026-10-02")
    panel = win.notebook_dialog.t_panel
    panel.add()
    assert [q.text for q in s.todos] == ["Check D002"]            # on the tab's day
    assert any(view.tree.topLevelItem(i).text(1) == "Check D002" for i in range(view.tree.topLevelItemCount()))
    view.reject()
