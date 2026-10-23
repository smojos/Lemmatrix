# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders. Additional terms: NOTICE.md
"""To Do (Josh, 21 October): a list parallel to Questions, Push to To Do (the orange flag), View →
To Do, the notebook's To Do tab, and Convert to To Do / Convert to question."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["LEMMATRIX_SETTINGS"] = "Lemmatrix-tests"

from test_texts import _add_text, app, win  # noqa: E402,F401


def test_todos_are_saved_beside_the_questions(tmp_path):
    from lemmatrix import notebook as nb
    book = nb.Notebook()
    s = book.add_session("2026-10-16")
    s.questions.append(nb.Question("Is the plural regular?", "2026-10-16"))
    s.todos.append(nb.Question("Rerecord D002 with SP2", "2026-10-16", "", "2026-10-17",
                               entry_id="e1", token_id="t1", ref="D002", about="D002 goat", kind=nb.TODO))
    nb.save(book, tmp_path / "x.notebook")
    text = (tmp_path / "x.notebook").read_text(encoding="utf-8")
    assert "<todo " in text and "<question " in text
    b = nb.load(tmp_path / "x.notebook").session("2026-10-16")
    assert [q.text for q in b.questions] == ["Is the plural regular?"] and b.questions[0].kind == nb.QUESTION
    t = b.todos[0]
    assert t.is_todo and t.resolved == "2026-10-17" and t.link is not None and t.about == "D002 goat"
    assert nb.matches(b, None, "rerecord")                       # the search finds to dos too


def test_convert_keeps_dates_link_and_status():
    from lemmatrix import notebook as nb
    s = nb.Session("2026-10-16")
    q = nb.Question("check the tone", "2026-10-10", "2026-10-12", "", entry_id="e1", ref="D001")
    s.questions = [nb.Question("other", "2026-10-16"), q]
    assert nb.convert(s, q) is q
    assert q.is_todo and s.todos == [q] and [x.text for x in s.questions] == ["other"]
    assert (q.created, q.edited, q.resolved, q.entry_id) == ("2026-10-10", "2026-10-12", "", "e1")
    nb.convert(s, q)                                             # and back
    assert not q.is_todo and s.questions[-1] is q and not s.todos


def test_push_to_todo_from_the_token_dialogue(win):
    from lemmatrix import notebook as nb
    from lemmatrix.ui.token_dialog import Slot, TokenDialog
    e = win.doc.db.entry_by_ref("D002")
    dlg = TokenDialog(win, [Slot(e, 0)], 0)
    assert not dlg.todo_btn.isEnabled() and not dlg.todo_btn.icon().isNull()
    dlg.comment.setText("Rerecord with SP2")
    assert dlg.todo_btn.isEnabled()
    dlg.push_to_todo()
    assert dlg.comment.text() == ""
    s = win.doc.notebook.session(win.work_date())
    t = s.todos[-1]
    assert t.text == "Rerecord with SP2" and t.is_open and t.is_todo
    assert "Rerecord with SP2" not in [q.text for q in s.questions]
    assert nb.find(win.doc.db, t.link) == (e, 0)
    dlg.reject()


def test_push_a_line_comment_to_todo(win, tmp_path, monkeypatch):
    uw, t = _add_text(win, tmp_path, monkeypatch)
    p = uw.texts
    line = p.lines.rows[0]
    p.set_line_field(line, "Comment", "gloss the second clause")
    seen = []
    p.lines.todoRequested.connect(lambda ln: seen.append(ln))
    p.push_to_todo(p.lines.rows[0])
    s = win.doc.notebook.session(win.work_date())
    todo = s.todos[-1]
    assert todo.text == "gloss the second clause" and todo.link.is_line and todo.link.entry_id == t.id
    assert not p.lines.rows[0].values.get("Comment")


def test_the_flag_sits_left_of_the_question_mark(win, tmp_path, monkeypatch):
    from PySide6.QtCore import QRectF
    uw, t = _add_text(win, tmp_path, monkeypatch)
    v = uw.texts.lines
    box = QRectF(0, 0, 200, 60)
    q, f = v._push_rect(box), v._push_rect(box, True)
    assert f.right() < q.left()
    assert v._push_hit(box, q.center().toPoint()) == "push"
    assert v._push_hit(box, f.center().toPoint()) == "push-todo"


def test_notebook_to_do_tab_and_convert(win):
    from lemmatrix import notebook as nb
    from lemmatrix.model import today
    from lemmatrix.ui.notebook_dialog import QUESTIONS_TAB, TODO_TAB
    win.open_notebook()
    d = win.notebook_dialog
    d.add_note(today())
    s = d.session
    s.questions, s.todos = [nb.Question("Why?", today())], [nb.Question("Do it", today(), kind=nb.TODO)]
    d._fill_questions()
    assert d.tabs.tabText(QUESTIONS_TAB) == "Questions (1 open)" and d.tabs.tabText(TODO_TAB) == "To Do (1 open)"
    assert d.todos.headerItem().text(0) == "To Do"
    # Convert to To Do (the button on the Questions tab)
    d.questions.setCurrentItem(d.questions.topLevelItem(0))
    d.q_panel.convert()
    assert [x.text for x in s.todos] == ["Do it", "Why?"] and not s.questions and win.doc.dirty
    assert d.tabs.tabText(QUESTIONS_TAB) == "Questions" and d.tabs.tabText(TODO_TAB) == "To Do (2 open)"
    # Convert to question (the To Do tab), resolve, delete
    d.todos.setCurrentItem(d.todos.topLevelItem(0))
    d.t_panel.convert()
    assert [x.text for x in s.questions] == ["Do it"] and s.questions[0].kind == nb.QUESTION
    d.todos.setCurrentItem(d.todos.topLevelItem(0))
    d.t_panel.toggle()
    assert s.todos[0].resolved == today()


def test_to_do_window_and_its_convert(win):
    from lemmatrix import notebook as nb
    from lemmatrix.ui.notebook_dialog import QuestionsDialog, TodoDialog
    s = win.doc.notebook.add_session("2026-10-02")
    s.todos = [nb.Question("open one", "2026-10-02", kind=nb.TODO),
               nb.Question("done", "2026-10-02", "", "2026-10-03", kind=nb.TODO)]
    dlg = TodoDialog(win)
    assert dlg.windowTitle() == "To Do" and dlg.tree.topLevelItemCount() == 1
    dlg.show_which.setCurrentIndex(dlg.show_which.findData("all"))
    assert dlg.tree.topLevelItemCount() == 2
    dlg.tree.setCurrentItem(dlg.tree.topLevelItem(0))
    assert dlg.convert_btn.isEnabled()
    dlg.convert()                                               # Convert to question
    assert s.questions[-1].text == "open one" and len(s.todos) == 1
    q = QuestionsDialog(win)
    q.tree.setCurrentItem(next(q.tree.topLevelItem(i) for i in range(q.tree.topLevelItemCount())
                               if q.tree.topLevelItem(i).text(1) == "open one"))
    q.convert()                                                 # Convert to To Do
    assert s.todos[-1].text == "open one" and s.todos[-1].created == "2026-10-02"


def test_view_menu_has_to_do(win):
    acts = [a.text() for m in win.menuBar().actions() if m.menu() for a in m.menu().actions()]
    assert "To &Do" in acts and "&Questions" in acts
