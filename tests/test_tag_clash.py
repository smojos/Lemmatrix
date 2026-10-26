# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders. Additional terms: NOTICE.md
"""Josh's case: Singular (SG) made the Number group's default. A new default that would give two tokens of a lemma one soundfile name (Josh, 26 October):
on OK, Add Example tags, Choose for each (merge where nothing is lost), or Cancel."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from lemmatrix import tagclash  # noqa: E402
from lemmatrix.model import Token  # noqa: E402


def _singular_default(ts):
    s = ts.copy() if hasattr(ts, "copy") else ts
    for t, _ in s.tags():
        if t.name == "Singular":
            t.default, t.code = True, ""
    s.__dict__.pop("_cache", None)
    return s


def _structure(db):
    import copy
    return _singular_default(copy.deepcopy(db.settings.tags))


def test_finding_the_clashes(win):
    db = win.doc.db
    assert tagclash.find(db, copy_of(db.settings.tags)) == []           # no change: nothing
    clashes = tagclash.find(db, _structure(db))
    assert clashes
    c = next(c for c in clashes if not c.keep.tags)
    assert "Singular" in c.other.tags and c.name.lower().endswith(".wav")
    assert db.settings.tags.tag("Singular").code                           # nothing changed by looking


def copy_of(ts):
    import copy
    return copy.deepcopy(ts)


def test_merge_only_where_nothing_is_lost():
    a, b = Token(), Token(tags=["Singular"])
    a.set("Phonetic", "dʌːm")
    b.set("Phonemic", "dʌ́ʌm")
    assert tagclash.merge_problem(a, b) == ""
    b.set("Phonetic", "dʌm")
    assert "Phonetic" in tagclash.merge_problem(a, b)
    b.set("Phonetic", "")
    a.file, b.file = "a.wav", "b.wav"
    assert tagclash.merge_problem(a, b) == ""                           # two recordings: choose one


def test_example_tags_or_merge_through_edit_lists(win, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    from lemmatrix.ui import lists_dialog, tagclash_dialog
    db = win.doc.db
    e = next(e for e in db.entries if any(not t.tags for t in e.tokens)
             and any("Singular" in t.tags for t in e.tokens))
    before = len(e.tokens)
    clashes = tagclash.find(db, _structure(db))
    mine = [i for i, c in enumerate(clashes) if c.entry is e]
    # Choose for each: merge where it can, Example tags elsewhere
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.No)   # → Choose for each…

    def pick(self):
        return {i: (tagclash.MERGE if i in mine and not clashes[i].merge_problem else tagclash.EXAMPLE)
                for i in range(len(self.boxes))}
    monkeypatch.setattr(tagclash_dialog.ChooseEach, "exec", lambda self: 1)
    monkeypatch.setattr(tagclash_dialog.ChooseEach, "choices", pick)
    dlg = lists_dialog.ListsDialog(win, db, win.doc.notebook, lists_dialog.TAGS)
    for it in dlg.tags._tag_items():
        if it.text(0) == "Singular":
            from lemmatrix.ui.dialogs import DEFAULT
            from PySide6.QtCore import Qt
            it.setCheckState(DEFAULT, Qt.Checked)
    assert dlg.tags.validate() and dlg.tags.clash_plan is not None
    win._apply_tags(dlg.tags)
    assert db.duplicate_filenames() == {}                                # no two tokens share a name
    merged = sum(1 for i in mine if not clashes[i].merge_problem)
    assert len(e.tokens) == before - merged
    assert any(t.tags and t.tags[-1].startswith("Example") for en in db.entries for t in en.tokens)


def test_cancel_changes_nothing(win, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    from lemmatrix.ui import lists_dialog
    from lemmatrix.ui.dialogs import DEFAULT
    from PySide6.QtCore import Qt
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.Cancel)
    dlg = lists_dialog.ListsDialog(win, win.doc.db, win.doc.notebook, lists_dialog.TAGS)
    for it in dlg.tags._tag_items():
        if it.text(0) == "Singular":
            it.setCheckState(DEFAULT, Qt.Checked)
    assert not dlg.tags.validate()


def test_merging_two_recordings_keeps_the_one_chosen(win, tmp_path):
    from lemmatrix import storage
    db = win.doc.db
    clashes = [c for c in tagclash.find(db, _structure(db)) if c.two_recordings and not c.merge_problem]
    if not clashes:
        import pytest
        pytest.skip("no clash with two recordings in the test data")
    c = clashes[0]
    folder = storage.folder_for(db, c.entry)
    for t in (c.keep, c.other):
        (folder / t.file).write_bytes(b"RIFF")
    theirs = c.other.file
    db.settings.tags = _structure(db)
    tagclash.apply(db, [c], {0: tagclash.MERGE_THEIRS})
    assert c.keep.file == theirs and c.other not in c.entry.tokens
    assert any(storage.held_folder(db).iterdir())                        # the other recording held
