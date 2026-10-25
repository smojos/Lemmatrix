# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders. Additional terms: NOTICE.md
"""Saving a token with the configuration of one its lemma already has (Josh, 24 October):
switch to that token, add an Example tag, or overwrite it (DESIGN.md section 5.6)."""

import hashlib
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["LEMMATRIX_SETTINGS"] = "Lemmatrix-tests"

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402

from test_ui import app, win  # noqa: E402,F401


def _new(win, entry, tags):
    from lemmatrix.ui.token_dialog import Slot, TokenDialog
    dlg = TokenDialog(win, [Slot(entry, None, tuple(tags), explicit=True, defaults=False)], 0)
    dlg.show()
    return dlg


def _answers(monkeypatch, dlg, *choices):
    seen = []
    queue = list(choices)

    def ask(o, chip):
        seen.append((o, chip))
        return queue.pop(0)
    monkeypatch.setattr(dlg, "_ask_duplicate", ask)
    return seen


def _md5(path):
    return hashlib.md5(path.read_bytes()).hexdigest()


def test_switch_fills_only_empty_fields_and_shows_that_token(win, monkeypatch):
    lion = win.doc.db.entry_by_ref("D002")
    pl = lion.tokens[3]                                    # Plural, isolation: rʉʉɲ, 'lions'
    count = len(lion.tokens)
    dlg = _new(win, lion, pl.tags)
    dlg.edits["Phonetic"].setText("xxx")                   # pl has a Phonetic: kept
    dlg.edits["Comment"].setText("checked with SP2")       # pl has no Comment: carried over
    seen = _answers(monkeypatch, dlg, "switch")
    dlg._ok()
    assert seen and seen[0][0] is pl and seen[0][1] == "x1"
    assert dlg.result() == 0 and dlg.isVisible()           # still open, now on that token
    assert len(lion.tokens) == count
    now = lion.tokens[3]
    assert now.get("Phonetic") == "rʉʉɲ" and now.get("Comment") == "checked with SP2"
    assert dlg.original is now and dlg.edits["Comment"].text() == "checked with SP2"
    win.doc.undo.undo()
    assert not lion.tokens[3].get("Comment")
    dlg.reject()


def test_overwrite_replaces_typed_fields_but_blanks_never_erase(win, monkeypatch):
    lion = win.doc.db.entry_by_ref("D002")
    pl = lion.tokens[3]
    count = len(lion.tokens)
    dlg = _new(win, lion, pl.tags)
    dlg.edits["Phonetic"].setText("rʉʉɲɲ")
    _answers(monkeypatch, dlg, "overwrite")
    told = []
    monkeypatch.setattr(dlg, "_confirm_overwrite", lambda what: told.append(what) or True)
    dlg._ok()
    assert told == ["Phonetic"]
    assert dlg.result() == 1 and len(lion.tokens) == count
    now = lion.tokens[3]
    assert now.get("Phonetic") == "rʉʉɲɲ" and now.get("Phonemic") == "rʉʉɲ"    # empty here: kept
    assert now.get("Translation", "en") == "lions" and now.file == pl.file


def test_cancel_further_on_goes_back_to_the_box_and_cancel_there_to_the_dialogue(win, monkeypatch):
    lion = win.doc.db.entry_by_ref("D002")
    pl = lion.tokens[3]
    count, before = len(lion.tokens), pl.copy()
    dlg = _new(win, lion, pl.tags)
    dlg.edits["Phonetic"].setText("rʉʉɲɲ")
    seen = _answers(monkeypatch, dlg, "overwrite", "cancel")
    monkeypatch.setattr(dlg, "_confirm_overwrite", lambda what: False)
    dlg._ok()
    assert len(seen) == 2 and dlg.result() == 0 and dlg.original is None
    assert len(lion.tokens) == count and lion.tokens[3] == before


def test_add_is_the_example_tag_as_before(win, monkeypatch):
    lion = win.doc.db.entry_by_ref("D002")
    pl = lion.tokens[3]
    count = len(lion.tokens)
    dlg = _new(win, lion, pl.tags)
    dlg.edits["Phonetic"].setText("rʉʉɲ")
    _answers(monkeypatch, dlg, "add")
    dlg._ok()
    assert len(lion.tokens) == count + 1 and "Example 1" in lion.tokens[-1].tags


def test_two_soundfiles_ask_which_to_keep_and_undo_brings_both_back(win, monkeypatch):
    from lemmatrix import storage
    from lemmatrix.ui.token_dialog import Slot, TokenDialog
    db = win.doc.db
    lion = db.entry_by_ref("D002")
    pl, plgen = lion.tokens[3], lion.tokens[4]
    folder = storage.sound_folder(db)
    a, b = folder / pl.file, folder / plgen.file
    ha, hb = _md5(a), _md5(b)
    assert ha != hb
    count = len(lion.tokens)
    dlg = TokenDialog(win, [Slot(lion, 4)], 0)             # the PL-GEN token, retagged to plain PL
    dlg.show()
    QTest.mouseClick(dlg.tags.buttons["Genitive"], Qt.LeftButton)          # clicking it clears it
    assert "Genitive" not in dlg.tag_combinations()[0]
    _answers(monkeypatch, dlg, "switch")
    asked = []
    monkeypatch.setattr(dlg, "_ask_soundfile", lambda mine, theirs: asked.append((mine, theirs)) or "mine")
    dlg._ok()
    assert asked == [(b, a)]
    assert len(lion.tokens) == count - 1                   # the token being edited went into PL
    merged = lion.tokens[3]
    assert merged.file == pl.file and _md5(a) == hb and not b.exists()
    assert merged.get("Phonetic") == "rʉʉɲ"                # switch: PL's own fields stay
    win.doc.undo.undo()
    assert len(lion.tokens) == count and _md5(a) == ha and _md5(b) == hb
    dlg.reject()


def test_the_box_lists_core_fields_with_phonemic_bold(win):
    from lemmatrix.ui.duplicate_token import DuplicateBox, OverwriteBox
    lion = win.doc.db.entry_by_ref("D002")
    dlg = _new(win, lion, lion.tokens[3].tags)
    found = dlg._core_found(lion.tokens[3])
    assert ("Phonemic", True) in found and ("Phonetic", False) in found
    assert not any(t == "Comment" for t, _ in found)
    box = DuplicateBox(dlg, found, "x1")
    assert box.add_btn.text() == "Add" and not box.add_btn.icon().isNull()
    assert "Overwrite" in box.overwrite_btn.text()
    ow = OverwriteBox(dlg, "Phonetic and the soundfile")
    assert not ow.go.isEnabled()
    ow.check.setChecked(True)
    assert ow.go.isEnabled() and "Phonetic and the soundfile will be overwritten" in ow.check.text()
    dlg.reject()


def test_recording_asks_the_same_box(win, monkeypatch):
    import numpy as np
    from lemmatrix import storage
    lion = win.doc.db.entry_by_ref("D002")
    pl = lion.tokens[3]
    count = len(lion.tokens)
    monkeypatch.setattr("lemmatrix.audio.Recorder", lambda *a, **k: type("R", (), {"start": lambda s: None})())
    dlg = _new(win, lion, pl.tags)
    seen = _answers(monkeypatch, dlg, "cancel")
    dlg._record()
    assert seen and dlg.recorder is None and len(lion.tokens) == count       # Cancel: nothing recorded
    # Add: the Example tag, then it records under a name of its own
    _answers(monkeypatch, dlg, "add")
    dlg._record()
    assert dlg.recorder is not None and "Example 1" in dlg.token.tags
    dlg.recorder = None
    # Switch: the dialogue shows the existing token and records onto it (its recording asked about)
    dlg2 = _new(win, lion, pl.tags)
    _answers(monkeypatch, dlg2, "switch")
    replace = []
    from PySide6.QtWidgets import QMessageBox
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: replace.append(a[2]) or QMessageBox.Yes)
    dlg2._record()
    assert dlg2.original is lion.tokens[3] and replace and "Replace this token's recording" in replace[0]
    assert dlg2.recorder is not None
    dlg2.recorder = None
    dlg.reject(); dlg2.reject()


def test_cancel_adds_no_example_tag(win, monkeypatch):
    """The audit, 25 October (S3): the new Example tag was added before the question, so Cancel
    left it in the tag structure and the database unsaved; now only Add adds it."""
    from lemmatrix.defaults import EXAMPLES, INSTANCES
    ts = win.doc.db.settings.tags
    top = next(g for g in ts.groups if g.name.lower() == INSTANCES.lower())
    top.groups = [g for g in top.groups if g.name.lower() != EXAMPLES.lower()]   # an older structure
    win.doc._settings_dirty = False
    lion = win.doc.db.entry_by_ref("D002")
    pl = lion.tokens[3]
    dlg = _new(win, lion, pl.tags)
    dlg.edits["Comment"].setText("again")
    seen = _answers(monkeypatch, dlg, "cancel")
    dlg._ok()
    assert seen and seen[0][1] == "x1"            # offered as x1 all the same
    assert not ts.find("Example 1") and not win.doc._settings_dirty
    seen = _answers(monkeypatch, dlg, "add")
    dlg._ok()
    assert ts.find("Example 1") and "Example 1" in lion.tokens[-1].tags
    dlg.reject()
