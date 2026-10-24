# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders. Additional terms: NOTICE.md
"""Batch tokens from the lemma list in the window (IDEAS.md idea 64, 24 October 2026): the lemma
list's selection and pin, the batch box, the closing box's ticks, planned tokens in the token
dialogue, and Tools → Audits → Give every lemma its citation token…"""

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QAbstractItemView, QMessageBox

from lemmatrix import batch, matrix as mx
from lemmatrix.model import Token

from test_ui import app, win  # noqa: F401 (fixtures)


def _nouns(win):
    db = win.doc.db
    return [db.entry_by_ref(r) for r in ("D001", "D002", "D003")]


def _click(table, row, modifiers):
    idx = None
    for r in range(table.proxy.rowCount()):
        i = table.proxy.index(r, 0)
        if table.row_at(i) is row:
            idx = i
    rect = table.visualRect(idx)
    QTest.mouseClick(table.viewport(), Qt.LeftButton, modifiers, rect.center())


def test_the_lemma_list_selects_like_windows_and_alt_click_pins(win):
    t = win.lemmas
    assert t.selectionMode() == QAbstractItemView.ExtendedSelection
    goat, lion, sheep = _nouns(win)
    t.resize(600, 400)
    t.show()
    _click(t, goat, Qt.NoModifier)
    _click(t, sheep, Qt.ControlModifier)
    assert {id(r) for r in t.selected_rows()} == {id(goat), id(sheep)}
    assert t.proxy.pinned is None                            # Ctrl+click no longer pins
    _click(t, goat, Qt.NoModifier)
    _click(t, sheep, Qt.ShiftModifier)                       # the range: D001, D002, E001, D003
    assert len(t.selected_rows()) == 4
    _click(t, lion, Qt.AltModifier)
    assert t.proxy.pinned == lion.id and t.visible_rows() == [lion]
    _click(t, lion, Qt.AltModifier)                          # again: everything back
    assert t.proxy.pinned is None and len(t.visible_rows()) == len(win.doc.db.entries)
    t.hide()


def test_several_lemmas_pinned_and_kept_in_the_workspace(win):
    t = win.lemmas
    goat, lion, sheep = _nouns(win)
    t.pin_rows([goat, sheep])
    assert {id(r) for r in t.visible_rows()} == {id(goat), id(sheep)}
    state = t.filter_state()
    assert sorted(state["pinned"]) == sorted([goat.id, sheep.id])
    t.pin_rows([])
    assert t.proxy.pinned is None
    t.set_filter_state(state)
    assert len(t.visible_rows()) == 2 and t.active_filters() == 1
    win.refresh()
    assert "2 lemmas pinned" in win.lemma_count.toolTip()
    t.clear_filters()
    assert len(t.visible_rows()) == len(win.doc.db.entries)


def test_lambda_tau_with_one_lemma_still_opens_the_token_dialogue(win, monkeypatch):
    opened = []
    monkeypatch.setattr(win, "_open_dialog", lambda slots, *a, **k: opened.append(slots))
    monkeypatch.setattr(win, "batch_tokens", lambda: opened.append("batch"))
    goat, lion, _ = _nouns(win)
    win.lemmas.select_rows([goat])
    win.add_token_to_lemma()
    assert opened and opened[0][0].entry is goat
    win.lemmas.select_rows([goat, lion])
    win.add_token_to_lemma()
    assert opened[-1] == "batch"


def _pick(dlg, monkeypatch, names):
    from lemmatrix.ui import tagpanel
    monkeypatch.setattr(tagpanel.QApplication, "keyboardModifiers", staticmethod(lambda: Qt.ControlModifier))
    for n in names:
        dlg.tags.buttons[n].setChecked(True)
    dlg._update()


def test_the_batch_box_makes_one_undo_step(win, monkeypatch):
    from lemmatrix.ui.batch_tokens import BatchDialog
    db = win.doc.db
    nouns = _nouns(win)
    before = {e.ref: len(e.tokens) for e in nouns}
    dlg = BatchDialog(win, nouns, win.lemmas.visible_rows())
    assert dlg.for_sel.isChecked() and dlg.lemmas() == nouns
    assert "Plural" in dlg.tags.buttons and "f1" in dlg.tags.buttons
    assert "1SG.A" not in dlg.tags.buttons                   # verbs' groups only under Show all tags
    _pick(dlg, monkeypatch, ["Singular", "Plural", "f1", "f2"])
    p = dlg.plan_
    assert len(dlg.combos()) == 4
    assert len(p.made) + len(p.skipped) == 12
    assert "→ 4 combinations × 3 lemmas" in dlg.count.text()
    made = len(p.made)
    dlg._create()
    p = dlg.plan_                                            # the plan as it was applied
    after = {e.ref: len(e.tokens) for e in nouns}
    assert sum(after.values()) - sum(before.values()) == made
    for e, t in p.made:
        tok = next(x for x in e.tokens if x.id == t.id)
        assert tok.speaker == "" and tok.collected == ""
    assert win.doc.undo.undoText() == batch.label(p)
    win.doc.undo.undo()
    assert {e.ref: len(e.tokens) for e in nouns} == before
    win.doc.undo.redo()
    assert {e.ref: len(e.tokens) for e in nouns} == after
    assert db.duplicate_filenames() == {} or all(
        not any(t.id in {x.id for _, x in p.made} for _, t in v) for v in db.duplicate_filenames().values())


def test_all_shown_and_nothing_picked(win, monkeypatch):
    from lemmatrix.ui.batch_tokens import BatchDialog
    shown = win.lemmas.visible_rows()
    dlg = BatchDialog(win, shown[:1], shown)
    assert dlg.for_shown.isChecked()                         # one selected: all shown to begin with
    assert not dlg.create_btn.isEnabled() and "Pick the tags" in dlg.count.text()
    _pick(dlg, monkeypatch, ["f1"])
    assert dlg.lemmas() == shown and dlg.create_btn.isEnabled()


def test_the_closing_box_ticks(win, monkeypatch):
    from lemmatrix.ui.batch_tokens import BatchDialog, ClosingDialog, follow_up
    from lemmatrix.ui.main_window import ALL_DATA
    db = win.doc.db
    nouns = _nouns(win)
    picked = ["Singular", "Plural", "f1", "f2"]
    dlg = BatchDialog(win, nouns, nouns)
    _pick(dlg, monkeypatch, picked)
    dlg._create()
    p = dlg.plan_
    close = ClosingDialog(win, p, True)
    assert all(c.isChecked() for c in (close.elicit, close.filter, close.lemma_tag, close.tag_tag))
    done = follow_up(win, p, picked)
    assert {t.id for _, t in p.made} <= set(win.elicit_basket)
    assert {id(r) for r in win.lemmas.visible_rows()} == {id(e) for e in p.lemmas}
    assert "tags" in win.all_table.proxy.filters and win.tabs.currentIndex() == ALL_DATA
    assert len(win.configs[mx.LEMMA_TAG].x) == 4 and len(win.configs[mx.TAG_TAG].y) == 2
    assert any("Save matrix" in d for d in done)
    saved = win.configs[mx.LEMMA_TAG].copy()                 # a saved one with the same lines is used
    saved.name = "Number>Frames"
    db.settings.matrices.append(saved)
    done = follow_up(win, p, picked, elicit=False, filter_all=False, tag_tag=False)
    assert win.configs[mx.LEMMA_TAG].name == "Number>Frames"
    assert any("Number › Frames" in d for d in done)


def test_one_group_offers_no_tag_tag(win, monkeypatch):
    from lemmatrix.ui.batch_tokens import ClosingDialog
    p = batch.plan(win.doc.db, _nouns(win), [["f1"]], translate=False)
    close = ClosingDialog(win, p, batch.matrices(win.doc.db, ["f1"])[1] is not None)
    assert not close.tag_tag.isEnabled() and not close.tag_tag.isChecked()


def test_a_planned_token_takes_the_session_s_speaker_and_date_when_collected(win):
    from lemmatrix.ui.token_dialog import Slot, TokenDialog
    goat = win.doc.db.entry_by_ref("D001")
    goat.add_token(Token(tags=["f2"]))
    i = len(goat.tokens) - 1
    win.set_speaker("SP1")
    dlg = TokenDialog(win, [Slot(goat, i)], 0)
    assert dlg.speaker.currentText() == "SP1" and dlg.date.text() == win.session_date()
    dlg._collect()
    assert dlg.token.speaker == "" and dlg.token.collected == ""   # opening writes nothing
    dlg._ok()
    assert goat.tokens[i].speaker == "" and goat.tokens[i].collected == ""
    dlg = TokenDialog(win, [Slot(goat, i)], 0)
    dlg.edits["Phonetic"].setText("dʌːm")                      # something collected
    dlg._ok()
    assert goat.tokens[i].speaker == "SP1" and goat.tokens[i].collected == win.session_date()


def test_the_citation_token_audit(win, monkeypatch):
    db = win.doc.db
    goat = db.entry_by_ref("D001")
    goat.tokens = [t for t in goat.tokens if not t.is_citation]
    lion = db.entry_by_ref("D002")
    lion.tokens = []
    asked = []
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: asked.append(a[2]) or QMessageBox.Yes)
    win.give_citation_tokens()
    assert "2 lemmas have no citation token" in asked[0]
    assert goat.tokens[0].is_citation and lion.tokens[0].is_citation and len(lion.tokens) == 1
    win.doc.undo.undo()
    assert not lion.tokens and not any(t.is_citation for t in goat.tokens)


def test_deleting_several_lemmas_is_one_undo_step(win):
    db = win.doc.db
    goat, lion, _ = _nouns(win)
    n = len(db.entries)
    win.lemmas.select_rows([goat, lion])
    win.delete_entry()
    assert len(db.entries) == n - 2 and goat not in db.entries
    win.doc.undo.undo()
    assert len(db.entries) == n
