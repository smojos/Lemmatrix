# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders. Additional terms: NOTICE.md
"""Cogitate (IDEAS.md idea 35, Josh, 21 October): hypotheses at the end of the notebook, linked to
tokens, utterances, text lines, snapshots, questions, comments and other hypotheses as Evidence,
Counterevidence or Relevant; log lines in the day's notes; snapshots from the camera."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["LEMMATRIX_SETTINGS"] = "Lemmatrix-tests"

from lemmatrix import hypotheses as hy, notebook as nb  # noqa: E402

from test_texts import _add_text  # noqa: E402,F401

DAY = "2026-10-16"


def _book():
    book = nb.Notebook()
    return book, hy.Journal(book)


# ---------------------------------------------------------------- the model and the file
def test_numbers_are_never_reused():
    book, j = _book()
    h1 = hy.make(book, j, DAY, "Tone spreads rightward")
    h2 = hy.make(book, j, DAY, "Plural is suffixal")
    assert (h1.label, h2.label) == ("H1", "H2") and h1.confidence == "initial"
    hy.delete(book, j, DAY, h2)
    h3 = hy.make(book, j, DAY, "Third")
    assert h3.label == "H3"


def test_the_file_round_trip(tmp_path):
    book, j = _book()
    s = book.add_session(DAY)
    q = nb.Question("Is the plural regular?", DAY)
    s.questions.append(q)
    h = hy.make(book, j, DAY, "Tone spreads rightward", "A H tone spreads one syllable to the right.",
                "developing")
    hy.add_link(book, j, DAY, h, hy.Link(hy.TOKEN, hy.EVIDENCE, "clear case", entry="e1", token="t1",
                                         about="D001 goat · PL"))
    hy.add_link(book, j, DAY, h, hy.Link(hy.LINE, hy.COUNTER, entry="x1", start=1.25,
                                          about="T001 Hare · 0:01.25", text="ŋɔːɲ kʷʊːn"))
    hy.add_link(book, j, DAY, h, hy.question_link(s, q))
    hy.add_link(book, j, DAY, h, hy.snapshot_link({"tab": 1, "lemma": "D001"}, "Lemma/Tag · D001"))
    h2 = hy.make(book, j, DAY, "Second", links=[hy.hypothesis_link(h, hy.EVIDENCE)])
    book.confidence = hy.default_confidence()[:2]
    nb.save(book, tmp_path / "x.notebook")
    text = (tmp_path / "x.notebook").read_text(encoding="utf-8")
    assert 'format="4"' in text and "<hypotheses" in text and "<summary>Tone spreads rightward</summary>" in text
    assert text.index("<hypotheses") > text.index("<session")      # at the end of the notebook
    b = nb.load(tmp_path / "x.notebook")
    assert [x.label for x in b.hypotheses] == ["H1", "H2"] and b.next_number == 3
    g = b.hypotheses[0]
    assert (g.summary, g.formulation, g.confidence) == (h.summary, h.formulation, "developing")
    kinds = [(ln.kind, ln.mark) for ln in g.links]
    assert kinds == [(hy.TOKEN, hy.EVIDENCE), (hy.LINE, hy.COUNTER), (hy.QUESTION, hy.RELEVANT),
                     (hy.SNAPSHOT, hy.RELEVANT)]
    assert g.links[0].note == "clear case" and g.links[1].start == 1.25 and g.links[1].text == "ŋɔːɲ kʷʊːn"
    assert g.links[3].view == {"tab": 1, "lemma": "D001"}
    assert b.session(DAY).questions[0].id == q.id and q.id            # the question got an id
    assert hy.find(None, b, g.links[2])[1].text == "Is the plural regular?"
    assert [x.name for x in b.confidence] == ["initial", "developing"]
    assert set(b.session(DAY).hypotheses) == {h.id, h2.id}
    assert hy.cited_by(b, g)[0][0].label == "H2"


def test_an_older_notebook_has_no_hypotheses(tmp_path):
    (tmp_path / "old.notebook").write_text('<?xml version="1.0"?><notebook format="2"><session date="2026-10-01">'
                                           '<notes>hi</notes></session></notebook>', encoding="utf-8")
    b = nb.load(tmp_path / "old.notebook")
    assert b.hypotheses == [] and b.next_number == 1 and hy.confidence_list(b) == hy.DEFAULT_CONFIDENCE
    nb.save(b, tmp_path / "old.notebook")
    assert "<hypotheses" not in (tmp_path / "old.notebook").read_text(encoding="utf-8")


def test_log_lines_go_into_the_days_notes():
    book, j = _book()
    book.add_session(DAY).notes = "Worked with SP1."
    h = hy.make(book, j, DAY, "Tone spreads")
    hy.edit(book, j, DAY, h, summary="Tone spreads rightward")          # made that day: the made line follows
    hy.edit(book, j, DAY, h, formulation="One syllable")
    hy.edit(book, j, DAY, h, confidence="developing")
    hy.add_link(book, j, DAY, h, hy.Link(hy.TOKEN, hy.EVIDENCE, about="D001 goat · PL", entry="e", token="t"))
    notes = book.session(DAY).notes.split("\n")
    assert notes[:3] == ["Worked with SP1.", "", "=====COGITATE HISTORY====="]   # Josh, 22 October
    assert notes[3] == "H1 made: Tone spreads rightward"
    assert notes[4] == "H1 Tone spreads rightward: confidence initial → developing"
    assert notes[5] == "H1 Tone spreads rightward: evidence linked, D001 goat · PL"
    later = "2026-10-17"
    h.made = DAY
    hy.edit(book, j, later, h, summary="Tone spreads right")
    hy.edit(book, j, later, h, summary="H tone spreads right")
    assert book.session(later).notes == "\n\n=====COGITATE HISTORY=====\nH1 edited: H tone spreads right"   # once a day
    assert h.id in book.session(later).hypotheses


def test_the_journal_takes_its_lines_out_again():
    book, j = _book()
    book.add_session(DAY).notes = "Mine."
    h = hy.make(book, j, DAY, "X")
    book.session(DAY).notes += "\n\nwritten by hand afterwards"
    j.undo_lines()
    assert book.session(DAY).notes == "Mine.\n\nwritten by hand afterwards"   # the emptied section goes
    j.redo_lines()
    assert book.session(DAY).notes == "Mine.\n\nwritten by hand afterwards\n\n=====COGITATE HISTORY=====\nH1 made: X"
    j2 = hy.Journal(book)
    hy.make(book, j2, "2026-10-18", "Y")
    j2.undo_lines()
    assert book.session("2026-10-18") is not None                # it lists the hypothesis still
    book.session("2026-10-18").hypotheses.clear()
    j2.lines.clear()
    j2.undo_lines()
    assert book.session("2026-10-18") is None                    # made for it, empty again: gone


def test_linking_the_same_item_again_changes_its_mark():
    book, j = _book()
    h = hy.make(book, j, DAY, "X")
    a = hy.add_link(book, j, DAY, h, hy.Link(hy.TOKEN, hy.EVIDENCE, entry="e", token="t"))
    b = hy.add_link(book, j, DAY, h, hy.Link(hy.TOKEN, hy.COUNTER, entry="e", token="t"))
    assert a is b and len(h.links) == 1 and a.mark == hy.COUNTER
    assert h.count(hy.COUNTER) == 1 and h.count(hy.EVIDENCE) == 0


# ---------------------------------------------------------------- with the database
def test_links_find_their_items_and_say_when_they_are_gone(win):
    db = win.doc.db
    e = db.entry_by_ref("D002")
    t = e.tokens[0]
    book = win.doc.notebook
    ln = hy.token_link(db, e, t, hy.EVIDENCE)
    assert hy.find(db, book, ln) == (e, 0) and hy.label(db, book, ln).startswith("D002")
    gone = hy.Link(hy.TOKEN, entry=e.id, token="nope", about="D002 x · PL")
    assert hy.is_gone(db, book, gone) and hy.gone_text(gone) == "Token no longer exists"
    assert hy.label(db, book, gone) == "D002 x · PL"


def test_changes_are_undo_steps(win):
    doc = win.doc
    date = win.work_date()
    h = doc.change_hypotheses("Make hypothesis", lambda j: hy.make(doc.notebook, j, date, "Undo me"))
    assert [x.summary for x in doc.notebook.hypotheses][-1] == "Undo me"
    assert doc.notebook.session(date).notes.endswith(f"{h.label} made: Undo me")
    doc.undo.undo()
    assert "Undo me" not in [x.summary for x in doc.notebook.hypotheses]
    s = doc.notebook.session(date)
    assert s is None or f"{h.label} made" not in s.notes
    doc.undo.redo()
    assert [x.summary for x in doc.notebook.hypotheses][-1] == "Undo me"
    assert doc.notebook.session(date).notes.endswith(f"{h.label} made: Undo me")


# ---------------------------------------------------------------- the picker, the window, the links
def _pick(monkeypatch, choose=None, mark=hy.EVIDENCE, note=""):
    """Make the link picker answer by itself: a hypothesis (by id), or Make a new hypothesis…"""
    from lemmatrix.ui import cogitate as cg

    def fake_exec(dlg):
        for b in dlg.marks.buttons():
            b.setChecked(b.property("mark") == mark)
        dlg.note.setText(note)
        if choose == "make":
            dlg._make()
            return 1
        for i in range(dlg.tree.topLevelItemCount()):
            it = dlg.tree.topLevelItem(i)
            if it.data(0, 0x0100) == choose:
                dlg.tree.setCurrentItem(it)
        dlg.accept()
        return 1
    monkeypatch.setattr(cg.LinkPicker, "exec", fake_exec)


def test_link_a_token_from_all_data(win, monkeypatch):
    from lemmatrix.ui import main_window as mw
    doc = win.doc
    e = doc.db.entry_by_ref("D002")
    win.lemmas.select_row(e)
    win.tabs.setCurrentIndex(mw.ALL_DATA)
    win.go_to(e, 0)
    _pick(monkeypatch, "make", hy.EVIDENCE, "clear plural")
    h = win.link_token_to_hypothesis()
    assert h is not None and h.links[0].kind == hy.TOKEN and h.links[0].mark == hy.EVIDENCE
    assert h.links[0].note == "clear plural" and hy.find(doc.db, doc.notebook, h.links[0]) == (e, 0)
    w = win.cogitate_window
    assert w.isVisible() and w.pages.currentIndex() == 1 and w.current_id == h.id
    assert w.links.model_.rows[0].link is h.links[0] and "1 evidence" in w.counts.text()
    doc.undo.undo()                                           # made with its link: one undo step
    assert hy.by_id(doc.notebook, h.id) is None
    doc.undo.redo()
    assert hy.by_id(doc.notebook, h.id).links


def test_the_window_lists_and_steps_through_hypotheses(win, monkeypatch):
    doc = win.doc
    w = win.open_cogitate()
    a = w.make()
    w.summary.setText("First")
    w._commit()
    b = w.make()
    w.summary.setText("Second")
    w.confidence.setCurrentText("proven")
    w._commit()
    assert [r.h.summary for r in w.table.model_.rows] == ["First", "Second"]
    assert hy.by_id(doc.notebook, b.id).confidence == "proven"
    w.show_hypothesis(a.id)
    assert not w.back_btn.isEnabled() and w.next_btn.isEnabled()
    w.next()
    assert w.current_id == b.id and w.summary.text() == "Second"
    # hypothesis → hypothesis, and Cited by
    import lemmatrix.ui.cogitate as cg
    monkeypatch.setattr(cg._PickHypothesis, "exec", lambda dlg: 1)
    w.link_hypothesis()
    w.show_hypothesis(a.id)
    assert w.cited.topLevelItemCount() == 1 and w.cited.topLevelItem(0).text(0) == b.label
    # unlink, marks and notes
    w.show_hypothesis(b.id)
    row = w.links.model_.rows[0]
    w.links.select_row(row)
    w.set_mark(row, hy.COUNTER)
    assert hy.by_id(doc.notebook, b.id).links[0].mark == hy.COUNTER
    w.unlink()
    assert not hy.by_id(doc.notebook, b.id).links
    notes = doc.notebook.session(win.work_date()).notes
    assert f"{b.label} Second: unlinked" in notes and f"{b.label} Second: now counterevidence" in notes
    w.table.select_row(cg._HypRow(hy.by_id(doc.notebook, a.id)))
    w.pages.setCurrentIndex(0)
    w.delete()
    assert hy.by_id(doc.notebook, a.id) is None
    w.show_hypothesis(b.id)
    assert w.links.model_.rows == []


def test_the_token_dialogue_says_which_hypotheses_it_is_in(win, monkeypatch):
    from lemmatrix.ui.token_dialog import Slot, TokenDialog
    e = win.doc.db.entry_by_ref("D002")
    _pick(monkeypatch, "make", hy.COUNTER)
    dlg = TokenDialog(win, [Slot(e, 0)], 0)
    assert dlg.hyp_line.text() == ""                          # in none yet: only the button
    b = dlg.hyp_btn                                           # the 48 px Cogitate button (22 October)
    assert b.iconSize().width() == 48 and not b.icon().isNull() and b.text() == ""
    b.click()                                                 # Link to hypothesis…
    h = hy.by_id(win.doc.notebook, win.doc.notebook.hypotheses[-1].id)
    assert f">{h.label}</a> (counterevidence)" in dlg.hyp_line.text()
    dlg.reject()


def test_the_utterance_dialogue_has_the_cogitate_button_too(win, tmp_path, monkeypatch):
    from lemmatrix.ui.token_dialog import Slot
    from lemmatrix.ui.utterances import UtteranceDialog
    uw, t = _add_text(win, tmp_path, monkeypatch)
    uw.texts.lines.select_row(uw.texts.lines.rows[0])
    u = uw.texts.clip()[0]
    _pick(monkeypatch, "make", hy.EVIDENCE)
    dlg = UtteranceDialog(win, [Slot(u, 0)], 0, uw)
    assert dlg.hyp_btn.iconSize().width() == 48 and dlg.hyp_line.text() == ""
    dlg.hyp_btn.click()
    assert "(evidence)" in dlg.hyp_line.text()
    dlg.reject()


def test_snapshots_restore_the_view(win, monkeypatch):
    from lemmatrix.ui import main_window as mw
    e = win.doc.db.entry_by_ref("D002")
    win.tabs.setCurrentIndex(mw.LEMMA_TAG)
    win.lemma_search.setText("goat")
    win.lemmas.select_row(e)
    win.switched[mw.LEMMA_TAG] = True
    _pick(monkeypatch, "make", hy.RELEVANT)
    h = win.link_snapshot()
    ln = h.links[0]
    assert ln.kind == hy.SNAPSHOT and ln.view["tab"] == mw.LEMMA_TAG and ln.about.startswith("Lemma/Tag")
    assert ln.view["search"]["lemma"] == "goat" and ln.view["lemma_id"] == e.id
    win.tabs.setCurrentIndex(mw.ALL_DATA)
    win.lemma_search.setText("")
    win.switched[mw.LEMMA_TAG] = False
    from lemmatrix.ui.cogitate import open_link
    assert open_link(win, ln)
    assert win.tabs.currentIndex() == mw.LEMMA_TAG and win.lemma_search.text() == "goat"
    assert win.switched[mw.LEMMA_TAG] and win.lemmas.current_row() is e
    view = dict(ln.view, lemma="Z999", lemma_id="gone")
    assert "the lemma Z999" in win.restore_snapshot(view)


def test_link_a_text_line_and_open_it(win, tmp_path, monkeypatch):
    uw, t = _add_text(win, tmp_path, monkeypatch)
    line = uw.texts.lines.rows[1]
    _pick(monkeypatch, "make", hy.EVIDENCE)
    h = uw.texts.link_line(line)
    ln = h.links[0]
    assert ln.kind == hy.LINE and ln.entry == t.id and abs(ln.start - line.start) < 0.001 and ln.text
    uw.texts.lines.select_row(uw.texts.lines.rows[0])
    ln.start += 0.003                                         # a boundary moved a little in Praat
    from lemmatrix.ui.cogitate import open_link
    assert open_link(win, ln)
    assert uw.texts.lines.current_row().id == line.id


def test_questions_and_comments_can_be_linked(win, monkeypatch):
    doc = win.doc
    date = win.work_date()
    e = doc.db.entry_by_ref("D002")
    q = nb.push_question(doc.notebook, doc.db, date, "Is it regular?", e, e.tokens[0])
    s = doc.notebook.session(date)
    _pick(monkeypatch, "make")
    win.open_notebook(date)
    panel = win.notebook_dialog.q_panel
    panel.fill(q)
    panel.link_to_hypothesis()
    h = doc.notebook.hypotheses[-1]
    assert h.links[0].kind == hy.QUESTION and h.links[0].target == q.id and q.id
    assert hy.label(doc.db, doc.notebook, h.links[0]) == "Q: Is it regular?"                  # Q: (Josh, 25 October)
    nb.convert(s, q)                                          # converted since: still found
    assert hy.label(doc.db, doc.notebook, h.links[0]) == "To Do: Is it regular?"
    c = nb.NoteComment("tone?", e.id, e.tokens[0].id, e.ref, "D002 · citation")
    _pick(monkeypatch, h.id, hy.COUNTER)
    win.notebook_dialog._link_comment(c)
    assert h.links[-1].kind == hy.COMMENT and h.links[-1].text == "tone?"
    assert hy.find(doc.db, doc.notebook, h.links[-1]) == (e, 0)
    win.notebook_dialog.reload(date)
    tabs = win.notebook_dialog.tabs
    from lemmatrix.ui.notebook_dialog import HYPOTHESES_TAB
    assert tabs.tabText(HYPOTHESES_TAB) == "Hypotheses (1)"
    assert f"{h.label} made" in win.notebook_dialog.notes.toPlainText()


def test_confidence_list_in_edit_lists(win, monkeypatch):
    from lemmatrix.ui.lists_dialog import CONFIDENCE, ListsDialog
    doc = win.doc
    h = doc.change_hypotheses("Make", lambda j: hy.make(doc.notebook, j, win.work_date(), "X",
                                                        confidence="developing"))
    dlg = ListsDialog(win, doc.db, doc.notebook, CONFIDENCE)
    tree = dlg.confidence.tree
    it = tree.topLevelItem(1)
    assert it.text(0) == "developing"
    it.setText(0, "growing")
    dlg.apply()
    assert hy.confidence_list(doc.notebook)[1] == "growing" and h.confidence == "growing"


def test_the_anonymous_backup_covers_hypotheses(win):
    from lemmatrix import anonymise
    doc = win.doc
    p = doc.db.metadata.participants[0]
    p.name = "Kuku Dabi"
    hy.make(doc.notebook, hy.Journal(doc.notebook), DAY, "Kuku Dabi says tone spreads", "Kuku says so")
    report = anonymise.Report()
    _, book = anonymise.anonymise(doc.db, doc.notebook, anonymise.Options(notebook=True), report)
    assert "Kuku" not in book.hypotheses[-1].summary and p.code in book.hypotheses[-1].summary


def test_links_note_before_mark_and_the_item_note_border_drags(win):
    """Josh, 22 October: Note sits before Mark, and the border between Item and Note can be dragged."""
    from PySide6.QtWidgets import QHeaderView
    from lemmatrix.ui.cogitate import CogitateWindow
    w = CogitateWindow(win)
    keys = w.links.visible_keys()
    assert keys.index("item") + 1 == keys.index("note") and keys.index("note") + 1 == keys.index("mark")
    h = w.links.horizontalHeader()
    assert h.sectionResizeMode(keys.index("item")) == QHeaderView.Interactive
    assert h.sectionResizeMode(keys.index("note")) == QHeaderView.Stretch


# ---------------------------------------------------------------- the history sections (Josh, 22 October)
def test_history_sections_in_the_notes():
    add = nb.history_add
    notes, _ = add("", nb.COGITATE_HISTORY, "H1 made: X")
    assert notes == "\n\n=====COGITATE HISTORY=====\nH1 made: X"      # two blank lines on a blank page
    notes, _ = add(notes, nb.ELICIT_HISTORY, "JS sent ɛλicit request to SP1")   # ɛλicit's first
    assert notes.split("\n") == ["", "", "=====ELICIT HISTORY=====", "JS sent ɛλicit request to SP1", "",
                                 "=====COGITATE HISTORY=====", "H1 made: X"]
    notes, _ = add(notes, nb.ELICIT_HISTORY, "Received ɛλicit request from SP1")
    notes, _ = add(notes, nb.COGITATE_HISTORY, "H2 made: Y")
    assert notes.split("\n")[2:] == ["=====ELICIT HISTORY=====", "JS sent ɛλicit request to SP1",
                                     "Received ɛλicit request from SP1", "", "=====COGITATE HISTORY=====",
                                     "H1 made: X", "H2 made: Y"]
    typed = "Worked with SP1." + notes                                  # typed on the top line: still a gap
    assert typed.split("\n")[:3] == ["Worked with SP1.", "", "=====ELICIT HISTORY====="]
    notes, _ = add("Worked with SP1.\n\n", nb.ELICIT_HISTORY, "a")
    assert notes == "Worked with SP1.\n\n=====ELICIT HISTORY=====\na"    # one blank line after typed notes
    assert nb.history_remove(notes, nb.ELICIT_HISTORY, "a") == "Worked with SP1."


def test_history_can_be_switched_off(win, monkeypatch):
    from lemmatrix.ui import elicit_dialogs as ed
    doc = win.doc
    date = win.work_date()
    doc.ws_set(nb.HISTORY_SETTINGS[nb.COGITATE_HISTORY], False)
    doc.ws_set(nb.HISTORY_SETTINGS[nb.ELICIT_HISTORY], False)
    h = doc.change_hypotheses("Make", lambda j: hy.make(doc.notebook, j, date, "Quiet"))
    ed.note_in_notebook(win, "JS sent ɛλicit request to SP1")
    s = doc.notebook.session(date)
    assert h.id in s.hypotheses and "HISTORY" not in s.notes       # still listed, nothing written
    doc.ws_set(nb.HISTORY_SETTINGS[nb.COGITATE_HISTORY], True)
    doc.change_hypotheses("Edit", lambda j: hy.edit(doc.notebook, j, date, h, confidence="proven"))
    assert "=====COGITATE HISTORY=====" in s.notes and "ELICIT" not in s.notes
    win.open_notebook(date)
    ticks = win.notebook_dialog.history_ticks
    assert ticks[nb.COGITATE_HISTORY].isChecked() and not ticks[nb.ELICIT_HISTORY].isChecked()
    ticks[nb.ELICIT_HISTORY].setChecked(True)                       # the notebook window's tick
    assert doc.ws.get_bool(nb.HISTORY_SETTINGS[nb.ELICIT_HISTORY], False)
    from lemmatrix.ui.dialogs import PreferencesDialog
    dlg = PreferencesDialog(win, doc.db, win.prefs)
    assert dlg.history[nb.ELICIT_HISTORY].isChecked()
    dlg.history[nb.COGITATE_HISTORY].setChecked(False)
    dlg.apply()
    assert not doc.ws.get_bool(nb.HISTORY_SETTINGS[nb.COGITATE_HISTORY], True)
    assert "=====COGITATE HISTORY=====" in s.notes                 # what was written stays


def test_opening_another_hypothesis_from_the_list_never_copies_the_shown_one(win, monkeypatch):
    """Josh, 22 October: with A shown, selecting B in the List and double-clicking it (or Edit,
    or the Hypothesis tab) copied A's summary and formulation over B's."""
    from lemmatrix.ui.cogitate import HYPOTHESIS_TAB, LIST_TAB, _HypRow
    doc = win.doc
    w = win.open_cogitate()
    a = w.make()
    w.summary.setText("Tone spreads rightward")
    w.formulation.setPlainText("H spreads one syllable to the right.")
    w._commit()
    b = w.make()
    w.summary.setText("Plural is -a")
    w.formulation.setPlainText("Plurals add a low -a.")
    w._commit()
    w.show_hypothesis(a.id)                          # A shown in the Hypothesis tab
    for how in ("double-click", "tab"):
        w.tabs.setCurrentIndex(LIST_TAB)
        w.table.select_row(_HypRow(hy.by_id(doc.notebook, b.id)))   # select B in the List
        assert w.current_id == b.id
        if how == "double-click":
            w.table.rowActivated.emit(w.table.current_row())
        else:
            w.tabs.setCurrentIndex(HYPOTHESIS_TAB)
        hb, ha = hy.by_id(doc.notebook, b.id), hy.by_id(doc.notebook, a.id)
        assert (hb.summary, hb.formulation) == ("Plural is -a", "Plurals add a low -a."), how
        assert (ha.summary, ha.formulation) == ("Tone spreads rightward", "H spreads one syllable to the right.")
        assert w.summary.text() == "Plural is -a" and w.shown_id == b.id
        w.show_hypothesis(a.id)
    # an edit typed in the shown one still goes into it when another is opened from the List
    w.summary.setText("Tone spreads leftward")
    w.tabs.setCurrentIndex(LIST_TAB)
    w.table.select_row(_HypRow(hy.by_id(doc.notebook, b.id)))
    w.table.rowActivated.emit(w.table.current_row())
    assert hy.by_id(doc.notebook, a.id).summary == "Tone spreads leftward"
    assert hy.by_id(doc.notebook, b.id).summary == "Plural is -a"
