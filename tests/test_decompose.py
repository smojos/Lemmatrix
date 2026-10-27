# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders. Additional terms: NOTICE.md
"""Decomposed transcriptions (IDEAS.md ideas 18 and 21, Josh, 27 October; format 14): a database
can promise that Phonetic and Phonemic hold no precomposed characters, says so in its file, keeps
the promise for everything written, and has an audit, Tools → Audits → Find precomposed characters…"""

import unicodedata

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QDialog, QLineEdit

from lemmatrix import decompose as dmod, storage

E_ACUTE = "é"                      # é, one character
E_DECOMP = "é"                    # é, e + U+0301


def _token_with(db, phonetic, other=E_ACUTE):
    e = next(e for e in db.entries if e.tokens)
    t = e.tokens[0]
    t.set("Phonetic", phonetic)
    t.set("Morphemes", other)
    return e, t


def test_the_helpers():
    assert dmod.precomposed(E_ACUTE) and not dmod.precomposed(E_DECOMP)
    assert not dmod.precomposed("ɛ́") and not dmod.precomposed("")      # no precomposed ɛ́ in Unicode
    assert dmod.nfd("bá" + "ã") == "báã"
    assert dmod.precomposed_chars("éaéã") == ["é", "ã"]


def test_saved_nfd_and_says_so(win, tmp_path):
    db = win.doc.db
    db.settings.decomposed = True
    e, t = _token_with(db, "b" + E_ACUTE + "t")
    assert t.get("Phonetic") == "bét" and unicodedata.is_normalized("NFC", t.get("Phonetic"))   # the setter: NFC
    text = storage.to_string(db)
    assert '<characters transcriptions="NFD"' in text and "no precomposed characters" in text
    assert "Phonetic" in text.split("<characters", 1)[1].split(">", 1)[0]
    assert "b" + E_DECOMP + "t" in text                                   # the promise kept on saving
    assert t.get("Phonetic") == "b" + E_DECOMP + "t"
    assert t.get("Morphemes") == E_ACUTE                                  # other fields: NFC
    assert unicodedata.is_normalized("NFC", db.expected_filename(e, t))   # names always composed
    p = tmp_path / "x.xml"
    storage.save(db, p, backup=False)
    back = storage.load(p)
    assert back.settings.decomposed
    t2 = next(x for x in back.entries if x.id == e.id).tokens[0]
    assert t2.get("Phonetic") == "b" + E_DECOMP + "t"                     # read back decomposed


def test_off_is_nfc_and_says_so(win):
    db = win.doc.db
    assert not db.settings.decomposed                                     # an older database: off
    e, t = _token_with(db, "b" + E_ACUTE)
    t.values["Phonetic"] = "b" + E_DECOMP                                 # however it got there
    text = storage.to_string(db)
    assert '<characters transcriptions="NFC"' in text
    assert "b" + E_DECOMP not in text and t.get("Phonetic") == "b" + E_ACUTE


def test_a_hand_edited_file_is_decomposed_on_opening(win, tmp_path):
    db = win.doc.db
    db.settings.decomposed = True
    e, t = _token_with(db, "ba")
    p = tmp_path / "x.xml"
    storage.save(db, p, backup=False)
    raw = p.read_text(encoding="utf-8").replace(">ba<", ">b" + E_ACUTE + "<", 1)
    p.write_text(raw, encoding="utf-8")
    back = storage.load(p)
    assert next(x for x in back.entries if x.id == e.id).tokens[0].get("Phonetic") == "b" + E_DECOMP


def test_an_older_file_reads_as_nfc(win, tmp_path):
    p = tmp_path / "x.xml"
    storage.save(win.doc.db, p, backup=False)
    raw = p.read_text(encoding="utf-8")
    raw = raw.replace(f'format="{storage.FORMAT_VERSION}"', 'format="13"')
    raw = "".join(line for line in raw.splitlines(True) if "<characters" not in line)
    p.write_text(raw, encoding="utf-8")
    back = storage.load(p)
    assert not back.settings.decomposed and back.upgraded


def test_edits_through_the_document_are_decomposed(win):
    db = win.doc.db
    db.settings.decomposed = True
    e = next(e for e in db.entries if e.tokens)
    win.doc.edit_entry(e, lambda x: x.tokens[0].set("Phonemic", "t" + E_ACUTE), "Edit")
    assert e.tokens[0].get("Phonemic") == "t" + E_DECOMP
    copy = e.copy()
    copy.tokens[0].set("Phonetic", E_ACUTE)
    win.doc.apply_changes("Bulk", [(e, copy)])                            # Bulk edit's way in
    assert e.tokens[0].get("Phonetic") == E_DECOMP
    assert e.tokens[0].get("Translation") != E_DECOMP                     # never other fields


def test_settings_switch_converts_as_one_undo_step(win):
    db = win.doc.db
    e, t = _token_with(db, "k" + E_ACUTE)
    db.settings.decomposed = True
    n = win.convert_transcriptions()
    ph = lambda: e.tokens[0].get("Phonetic")  # noqa: E731
    assert n >= 1 and ph() == "k" + E_DECOMP
    assert win.doc.undo.undoText() == "Decompose transcriptions"
    win.doc.undo.undo()
    assert ph() == "k" + E_ACUTE
    win.doc.undo.redo()
    db.settings.decomposed = False                                        # and back: composed
    win.convert_transcriptions()
    assert ph() == "k" + E_ACUTE


def test_the_audit(win, monkeypatch):
    from lemmatrix.ui import precomposed_dialog as pd
    db = win.doc.db
    e, t = _token_with(db, "s" + E_ACUTE)
    found = dmod.find(db, pd.describe_token(db))
    f = next(f for f in found if f.item is e and f.field == "Phonetic")
    assert f.chars == E_ACUTE and e.ref in f.where
    assert not any(f.field == "Morphemes" for f in found)
    monkeypatch.setattr(pd.PrecomposedDialog, "exec", lambda self: QDialog.Accepted)
    pd.run(win)
    assert db.settings.decomposed                                         # it turns the switch on
    assert e.tokens[0].get("Phonetic") == "s" + E_DECOMP and not dmod.find(db)
    shown = []
    monkeypatch.setattr(pd.PrecomposedDialog, "exec", lambda self: shown.append(1) or QDialog.Rejected)
    pd.run(win)                                                           # nothing left: a message only
    assert shown == []


def test_typing_decomposes_only_in_a_decomposing_database(win):
    from lemmatrix.ui import fastpaste, keyboards
    from lemmatrix.ui.bestfriend import BestFriendFilter
    fastpaste.set_context(lambda: win.doc.db)
    f = BestFriendFilter()

    def typed(field, on):
        win.doc.db.settings.decomposed = on
        e = QLineEdit()
        keyboards.tag(e, field)
        for ch in "b" + E_ACUTE:
            if not f.eventFilter(e, QKeyEvent(QEvent.KeyPress, 0, Qt.NoModifier, ch)):
                e.insert(ch)
        return e.text()
    assert typed("Phonetic", True) == "b" + E_DECOMP
    assert typed("Phonemic", True) == "b" + E_DECOMP
    assert typed("Phonetic", False) == "b" + E_ACUTE
    assert typed("Translation", True) == "b" + E_ACUTE


def test_the_dialogue_warns_and_decomposes(win):
    from lemmatrix.ui.token_dialog import Slot, TokenDialog
    db = win.doc.db
    db.settings.decomposed = True
    e = next(e for e in db.entries if e.tokens)
    dlg = TokenDialog(win, [Slot(e, 0)], 0)
    dlg.show()
    try:
        ed = dlg.edits["Phonetic"]
        ed.setText("b" + E_ACUTE + "t")                                   # e.g. pasted
        assert dlg.precomposed_note.isVisible() and "⚠️" in dlg.precomposed_note.text()
        assert dlg.decompose_btn.isVisible()
        dlg.decompose_fields()
        assert ed.text() == "b" + E_DECOMP + "t" and not dlg.precomposed_note.isVisible()
        ed.undo()
        assert ed.text() == "b" + E_ACUTE + "t"
        db.settings.decomposed = False
        dlg._check_precomposed()
        assert not dlg.precomposed_note.isVisible()                       # a precomposed database: no warning
    finally:
        dlg.reject()


def test_new_databases_decompose():
    from lemmatrix import newdb
    assert newdb.make(newdb.Choices()).settings.decomposed
