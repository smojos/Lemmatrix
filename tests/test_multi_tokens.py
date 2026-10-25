# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders. Additional terms: NOTICE.md
"""Several tokens at once from the token dialogue (IDEAS.md idea 25, DESIGN.md section 5.6)."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["LEMMATRIX_SETTINGS"] = "Lemmatrix-tests"

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402



def _dialog(win, entry, index=None, tags=("Singular",)):
    from lemmatrix.ui.token_dialog import Slot, TokenDialog
    slot = Slot(entry, index) if index is not None else Slot(entry, None, tags, explicit=True, defaults=True)
    dlg = TokenDialog(win, [slot], 0)
    dlg.show()
    return dlg


def test_ctrl_click_makes_one_token_per_combination(win, monkeypatch):
    goat = win.doc.db.entry_by_ref("D001")
    before = len(goat.tokens)
    dlg = _dialog(win, goat)
    b = dlg.tags.buttons
    QTest.mouseClick(b["Plural"], Qt.LeftButton, Qt.ControlModifier)       # Singular and Plural
    QTest.mouseClick(b["Ergative"], Qt.LeftButton)
    QTest.mouseClick(b["Accusative"], Qt.LeftButton, Qt.ControlModifier)   # Ergative and Accusative
    assert len(dlg.tag_combinations()) == 4 and "4 tokens" in dlg.combo_note.text()
    assert dlg.token.tags == dlg.tag_combinations()[0]                     # the file name is the first's
    dlg.edits["Phonetic"].setText("dʌ́ʌm")
    seen = {}

    def confirm(make, skipped):
        seen["make"], seen["skipped"] = make, skipped
        return True                                                        # copy the fields
    monkeypatch.setattr(dlg, "_confirm_extras", confirm)
    dlg._ok()
    assert len(goat.tokens) == before + 4
    new = goat.tokens[before:]
    assert {frozenset(t.tags) - {"isolation"} for t in new} == {
        frozenset({n, c}) for n in ("Singular", "Plural") for c in ("Ergative", "Accusative")}
    assert all(t.get("Phonetic") == "dʌ́ʌm" for t in new)
    assert len({t.id for t in new}) == 4 and not any(t.file for t in new[1:])
    win.doc.undo.undo()                                                    # one undo step for the lot
    assert len(goat.tokens) == before


def test_existing_combinations_are_skipped_and_fields_can_stay_empty(win, monkeypatch):
    goat = win.doc.db.entry_by_ref("D001")
    before = len(goat.tokens)
    dlg = _dialog(win, goat)
    b = dlg.tags.buttons
    QTest.mouseClick(b["Ergative"], Qt.LeftButton)
    QTest.mouseClick(b["Genitive"], Qt.LeftButton, Qt.ControlModifier)    # SG+GEN is already there
    dlg.edits["Phonetic"].setText("x")
    seen = {}

    def confirm(make, skipped):
        seen["make"], seen["skipped"] = make, skipped
        return False                                                       # don't copy
    monkeypatch.setattr(dlg, "_confirm_extras", confirm)
    dlg._ok()
    assert [set(t) for t in seen["skipped"]] == [{"Singular", "Genitive", "isolation"}]
    assert seen["make"] == []
    assert len(goat.tokens) == before + 1                                  # SG+ERG only


def test_cancel_saves_nothing(win, monkeypatch):
    goat = win.doc.db.entry_by_ref("D001")
    before = len(goat.tokens)
    dlg = _dialog(win, goat)
    QTest.mouseClick(dlg.tags.buttons["Plural"], Qt.LeftButton, Qt.ControlModifier)
    QTest.mouseClick(dlg.tags.buttons["Oblique"], Qt.LeftButton)
    monkeypatch.setattr(dlg, "_confirm_extras", lambda make, skipped: None)
    dlg._ok()
    assert len(goat.tokens) == before and dlg.isVisible()


def test_editing_a_token_keeps_its_own_tags_and_adds_the_rest(win, monkeypatch):
    goat = win.doc.db.entry_by_ref("D001")
    i = next(i for i, t in enumerate(goat.tokens) if t.tags == ["Plural", "before H", "isolation", "f2"])
    own = goat.tokens[i].copy()
    before = len(goat.tokens)
    dlg = _dialog(win, goat, index=i)
    QTest.mouseClick(dlg.tags.buttons["Singular"], Qt.LeftButton, Qt.ControlModifier)
    QTest.mouseClick(dlg.tags.buttons["f3"], Qt.LeftButton, Qt.ControlModifier)
    assert dlg.tag_combinations()[0] == own.tags                        # its own combination first
    monkeypatch.setattr(dlg, "_confirm_extras", lambda make, skipped: False)
    dlg._ok()
    t = goat.tokens[i]
    assert t.id == own.id and t.tags == own.tags and t.file == own.file
    assert len(goat.tokens) == before + 3
    assert all(not x.get("Phonetic") and not x.file for x in goat.tokens[before:])


def test_plain_click_still_replaces_and_back_next_save_extras_only_on_leaving(win, monkeypatch):
    goat = win.doc.db.entry_by_ref("D001")
    dlg = _dialog(win, goat)
    b = dlg.tags.buttons
    QTest.mouseClick(b["Plural"], Qt.LeftButton)                           # replaces Singular
    assert not b["Singular"].isChecked() and len(dlg.tag_combinations()) == 1
    assert not dlg.combo_note.isVisible()
    called = []
    QTest.mouseClick(b["Singular"], Qt.LeftButton, Qt.ControlModifier)
    QTest.mouseClick(b["Oblique"], Qt.LeftButton)
    monkeypatch.setattr(dlg, "_confirm_extras", lambda m, s: called.append(m) or False)
    dlg._commit(keep_empty=True)                                           # a save on the way
    assert not called                                                      # (recording, Push to question)


def test_the_confirmation_lists_the_tokens(win, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    goat = win.doc.db.entry_by_ref("D001")
    dlg = _dialog(win, goat)
    dlg.edits["Phonetic"].setText("x")
    dlg._collect()
    texts = {}

    def fake_exec(box):
        texts["text"] = box.text()
        texts["check"] = box.checkBox().text() if box.checkBox() else None
        return 0
    monkeypatch.setattr(QMessageBox, "exec", fake_exec)
    monkeypatch.setattr(QMessageBox, "clickedButton", lambda box: box.defaultButton())
    assert dlg._confirm_extras([["Plural", "Oblique", "isolation"]], [["Singular", "Genitive"]]) in (True, False)
    assert "This makes 2 tokens" in texts["text"] and "skipped" in texts["text"]
    assert "Copy" in texts["check"]


def test_utterances_pick_one_tag_per_group(win):
    from lemmatrix.ui.utterances import UtteranceDialog
    assert UtteranceDialog.MULTI_TOKENS is False
