# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders
"""Josh's tweaks of 22 October: the pitch scratchpad in the main window."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["LEMMATRIX_SETTINGS"] = "Lemmatrix-tests"

from test_ui import app, win  # noqa: E402,F401


def test_pitch_scratchpad_in_the_main_window(win, monkeypatch):
    played = []
    monkeypatch.setattr(win, "play_pitch", lambda text: played.append(text))
    sp = win.comparison.alpha
    assert win.scratchpad is sp and [l.text() for l in win.comparison.letters] == ["α", "β"]
    win.comparison.beta.edit.setText("33")
    win.comparison.beta.edit.returnPressed.emit()
    assert played == ["33"]
    played.clear()
    sp.edit.setText("55 3:3 21")
    assert sp.canvas.text == "55 3:3 21"
    sp.edit.returnPressed.emit()
    assert played == ["55 3:3 21"]
    order = [win.bottom_row.itemAt(i).widget() for i in range(win.bottom_row.count())]
    assert order.index(win.comparison.parentWidget()) + 1 == order.index(win.sess_panel)   # left of Current Session


def test_symbols_in_a_text_fields_menu(app):
    from PySide6.QtWidgets import QApplication, QLineEdit, QPlainTextEdit
    from lemmatrix.ui import symbols
    f = symbols.install(QApplication.instance())
    try:
        symbols.set_current(symbols.DEFAULT)
        for ed in (QLineEdit(), QPlainTextEdit()):
            menu = ed.createStandardContextMenu()
            menu.show()
            QApplication.processEvents()
            first = menu.actions()[0]
            assert first.text() == "Σymbols"
            menu.close()
            g = symbols.open_grid(ed)
            assert (g.table.columnCount(), g.table.rowCount()) == (4, 3)     # 11 symbols: 4 across, 3 down
            assert g.table.item(0, 2).text() == "∅"
            g.table.cellDoubleClicked.emit(0, 2)
            assert (ed.text() if isinstance(ed, QLineEdit) else ed.toPlainText()) == "∅"
            assert not g.isVisible()
        ro = QLineEdit()
        ro.setReadOnly(True)
        menu = ro.createStandardContextMenu()
        menu.show()
        QApplication.processEvents()
        assert all(a.text() != "Σymbols" for a in menu.actions())     # not in read-only fields
        menu.close()
    finally:
        QApplication.instance().removeEventFilter(f)


def test_symbols_list_in_edit_lists(win, monkeypatch):
    from lemmatrix.ui import symbols
    from lemmatrix.ui.lists_dialog import ListsDialog
    assert win._symbols() == symbols.DEFAULT
    dlg = ListsDialog(win, win.doc.db, win.doc.notebook, symbols=["ʔ", "ŋ"])
    assert dlg.symbol_list() == ["ʔ", "ŋ"]
    dlg._reset_symbols()
    assert dlg.symbol_list() == symbols.DEFAULT


def test_texts_comparison_and_logo(win):
    uw = win.open_utterances()
    t = uw.texts
    assert t.scratch is t.comparison.alpha.edit and t.comparison.beta.edit is not None
    assert not uw.logo.pixmap().isNull()                      # the logo, under both tabs
    assert uw.options.parentWidget() is uw.logo.parentWidget().parentWidget()
    uw.close()


def test_therefore_in_the_default_symbols():
    from lemmatrix.ui import symbols
    assert symbols.DEFAULT[-1] == "∴"


def test_convert_question_to_hypothesis(win):
    from lemmatrix import hypotheses as hy
    from lemmatrix import notebook as nb
    from lemmatrix.ui.notebook_dialog import QuestionsDialog, TodoDialog
    s = win.doc.notebook.add_session("2026-10-02")
    s.questions = [nb.Question("Does tone spread rightward?", "2026-10-02")]
    dlg = QuestionsDialog(win)
    dlg.tree.setCurrentItem(dlg.tree.topLevelItem(0))
    assert dlg.hypothesis_btn is not None and dlg.hypothesis_btn.isEnabled()
    dlg.to_hypothesis()
    q = s.questions[0]
    h = win.doc.notebook.hypotheses[-1]
    assert h.summary == "Does tone spread rightward?" and h.confidence == hy.confidence_list(win.doc.notebook)[0]
    assert [(ln.kind, ln.mark, ln.target) for ln in h.links] == [(hy.QUESTION, hy.RELEVANT, q.id)]
    assert q.resolved and len(s.questions) == 1                  # stays, resolved
    w = win.cogitate_window
    assert w is not None and w.isVisible() and w.summary.text() == h.summary
    win.doc.undo.undo()                                           # the hypothesis is one undo step
    assert h.id not in [x.id for x in win.doc.notebook.hypotheses]
    assert TodoDialog(win).hypothesis_btn is None                 # questions only
    w.close()


def test_pinned_questions_and_todos(win, tmp_path):
    from lemmatrix import notebook as nb
    from lemmatrix.ui.notebook_dialog import QuestionsDialog
    book = win.doc.notebook
    old = book.add_session("2026-10-01")
    new = book.add_session("2026-10-05")
    old.questions = [nb.Question("old one", "2026-10-01")]
    new.questions = [nb.Question("new one", "2026-10-05")]
    assert [q.text for _, q in book.all_items(nb.QUESTION)] == ["new one", "old one"]
    dlg = QuestionsDialog(win)
    dlg.tree.setCurrentItem(dlg.tree.topLevelItem(1))           # old one
    dlg.toggle_pin()
    assert old.questions[0].pinned
    assert dlg.tree.topLevelItem(0).text(1) == "old one"          # pinned on top
    assert not dlg.tree.topLevelItem(0).icon(1).isNull()
    path = tmp_path / "x.notebook"                                # saved and read back
    nb.save(book, path)
    assert 'pinned="yes"' in path.read_text(encoding="utf-8")
    back = nb.load(path)
    assert [q.text for _, q in back.all_items(nb.QUESTION)][0] == "old one"
    dlg.tree.setCurrentItem(dlg.tree.topLevelItem(0))
    dlg.toggle()                                                  # resolving unpins
    assert old.questions[0].resolved and not old.questions[0].pinned


def test_level_check_never_changes_the_recording():
    import numpy as np
    from lemmatrix.ui import levelmeter as lm
    loud = np.concatenate([np.zeros(100), np.ones(10), np.zeros(100)])
    quiet = np.full(1000, 0.01)
    fine = np.sin(np.linspace(0, 100, 4000)) * 0.5
    assert lm.check(loud)[0] == "clipped"
    assert lm.check(quiet)[0] == "quiet" and lm.check(quiet)[1] < lm.QUIET_DB
    assert lm.check(fine)[0] == ""
    before = fine.copy()
    lm.check(fine)
    assert np.array_equal(fine, before)
    assert "Clipped" in lm.message("clipped", 0) and "quiet" in lm.message("quiet", -40)


def test_level_meter_widget(app):
    from lemmatrix.ui.levelmeter import LevelMeter
    m = LevelMeter()
    m.set_level(0.5)
    assert not m.clipped and -7 < m.peak_db < -5
    m.set_level(1.0)
    assert m.clipped
    m.grab()
    m.reset()
    assert not m.clipped
