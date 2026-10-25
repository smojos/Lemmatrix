# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders. Additional terms: NOTICE.md
"""The audit of 25 October 2026: the "fix first" bugs (claude/AUDIT.md, B1–B9)."""

from test_texts import _add_text, app, win  # noqa: F401  (fixtures)


# ---- B1: Record in the utterance dialogue -------------------------------------------------

def test_utterance_dialogue_records(win, tmp_path, monkeypatch):
    """The clipped-from-text Source box no longer takes the name of the Record from choice."""
    from PySide6.QtWidgets import QComboBox

    from lemmatrix import audio
    from lemmatrix.ui.token_dialog import Slot
    from lemmatrix.ui.utterances import UtteranceDialog

    class FakeRecorder:
        def __init__(self, source, rate):
            self.source = source

        def start(self):
            pass

    monkeypatch.setattr(audio, "Recorder", FakeRecorder)
    uw, t = _add_text(win, tmp_path, monkeypatch)
    uw.texts.lines.select_row(uw.texts.lines.rows[0])
    u = uw.texts.clip()[0]
    dlg = UtteranceDialog(win, [Slot(u, 0)], 0, uw)
    assert isinstance(dlg.source_box, QComboBox)
    assert not dlg.clip_source_box.isHidden()
    other = "computer" if win.prefs.record_source != "computer" else "microphone"
    old = win.prefs.record_source
    dlg.source_box.setCurrentIndex(dlg.source_box.findData(other))
    assert win.prefs.record_source == other
    from PySide6.QtWidgets import QMessageBox
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.Yes)
    dlg._record()                                  # crashed: 'QGroupBox' has no 'currentData'
    assert isinstance(dlg.recorder, FakeRecorder) and dlg.recorder.source == other
    dlg.timer.stop()
    dlg.recorder = None
    dlg.reject()
    win.prefs.record_source = old


# ---- B2: menu items never get Qt's checked flag as their first argument -------------------

def _action(win, text):
    from PySide6.QtGui import QAction
    hits = [a for a in win.findChildren(QAction) if a.text().replace("&", "") == text]
    assert hits, text
    return hits[0]


def test_update_all_names_asks_from_the_menu(win, monkeypatch):
    """Tools → Update all soundfile names asked nothing and renamed (its ask came in as False)."""
    from PySide6.QtWidgets import QMessageBox
    db = win.doc.db
    e = next(e for e in db.entries if any(t.file for t in e.tokens))
    t = next(t for t in e.tokens if t.file)
    t.file = "old_name.wav"                       # out of date
    asked, told = [], []
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: asked.append(a[2]) or QMessageBox.No)
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: told.append(a[2]))
    _action(win, "Update all soundfile names").trigger()
    assert asked and "Rename" in asked[0]
    assert t.file == "old_name.wav"               # No: nothing renamed


def test_act_passes_no_arguments(win):
    """The same flaw made View → Matrix → Take snapshot skip its animation (animate came in as False)."""
    seen = []

    def probe(animate=True):
        seen.append(animate)
    win._act(None, "probe", probe).trigger()
    assert seen == [True]


# ---- B3: moving a citation token keeps the target's other tokens ---------------------------

def test_moving_a_citation_token_keeps_a_tagged_token_listed_first(tmp_path):
    from lemmatrix import defaults, move
    from lemmatrix.model import Entry, Token
    db = defaults.new_database()
    src, target = Entry("D901"), Entry("D902")
    moved = Token()
    moved.values["Phonetic"] = "kaba"            # a citation token with data
    src.tokens = [moved]
    plural = Token(tags=["Plural"])
    plural.values["Phonetic"] = "kabaŋ"
    empty = Token()                              # the target's empty citation token, listed second
    target.tokens = [plural, empty]
    db.entries += [src, target]
    p = move.plan(db, [(src, 0)], target, tmp_path)
    assert p.moves[0].replaces == 1
    pairs, renames, grew = move.changes(db, p, tmp_path, add_examples=False)
    after = dict((id(e), a) for e, a in pairs)[id(target)]
    assert [t.get("Phonetic") for t in after.tokens] == ["kaba", "kabaŋ"]   # the empty one went
    assert not any(t.is_citation and not t.has_content() for t in after.tokens)


# ---- B4: Bulk edit → Deselect highlighted rows on the Lemmas tab --------------------------

def test_bulk_deselect_highlighted_lemmas(win):
    from PySide6.QtCore import QItemSelectionModel
    from lemmatrix import bulk
    from lemmatrix.ui import bulk_window as bw
    win.open_bulk_edit()
    w = win.bulk_window
    w.levels.setCurrentIndex(bw.LEVELS.index(bulk.LEMMAS))
    t = w.tables[bulk.LEMMAS]
    sm = t.selectionModel()
    for r in (0, 1):
        sm.select(t.model().index(r, 0), QItemSelectionModel.Select | QItemSelectionModel.Rows)
    rows = w._selected(bulk.LEMMAS)             # crashed: unhashable type: 'Entry'
    assert len(rows) == 2
    w.set_ticked(rows, False)
    assert not any(w.is_ticked(r) for r in rows)
    w.close()


# ---- B5: editing a text changes its files only once nothing can stop it --------------------

def _edit_text(uw, monkeypatch, label, new_wav=None):
    from lemmatrix.ui import texts as tx

    def fake_exec(dlg):
        dlg.new_wav = new_wav
        dlg.new_grid = None
        dlg.label.setText(label)
        return 1
    monkeypatch.setattr(tx.TextDialog, "exec", fake_exec)
    uw.texts.edit(uw.texts.current())


def test_edit_text_stopped_leaves_files_alone(win, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    from test_texts import _recording
    uw, t = _add_text(win, tmp_path, monkeypatch)
    folder = tmp_path / "Soundfiles" / "Texts"
    before = sorted(p.name for p in folder.iterdir())
    (folder / "LXX-VXX_T001_Hare.wav").write_bytes(b"in the way")   # the new recording's name is taken
    warned = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: warned.append(a[2]))
    _edit_text(uw, monkeypatch, "Hare", new_wav=_recording(tmp_path / "other.wav"))
    assert warned                                   # stopped
    assert sorted(p.name for p in folder.iterdir()) == sorted(before + ["LXX-VXX_T001_Hare.wav"])
    assert t.file_label == "Hyena and Hare"
    assert (folder / t.textgrid).exists()           # was renamed to …_Hare.TextGrid before


def test_edit_text_undo_takes_a_new_recording_out(win, tmp_path, monkeypatch):
    from test_texts import _recording
    uw, t = _add_text(win, tmp_path, monkeypatch)
    folder = tmp_path / "Soundfiles" / "Texts"
    old_file, old_grid = t.file, t.textgrid
    _edit_text(uw, monkeypatch, "Hare", new_wav=_recording(tmp_path / "other.wav"))
    assert t.file == "LXX-VXX_T001_Hare.wav" and (folder / t.file).exists()
    assert t.textgrid == "LXX-VXX_T001_Hare.TextGrid" and (folder / t.textgrid).exists()
    win.doc.undo.undo()
    t = win.doc.db.texts[-1]
    assert (t.file, t.textgrid) == (old_file, old_grid)
    assert (folder / old_grid).exists()
    assert not (folder / "LXX-VXX_T001_Hare.wav").exists()     # the copy went out with the undo
    assert not (folder / "LXX-VXX_T001_Hare.TextGrid").exists()
    win.doc.undo.redo()
    assert (folder / "LXX-VXX_T001_Hare.wav").exists()


# ---- B6: Clear empty days keeps a day that holds only snapshots ---------------------------

def test_a_day_with_a_snapshot_is_not_empty():
    from lemmatrix import defaults
    from lemmatrix import notebook as nbmod
    db = defaults.new_database()
    book = nbmod.Notebook()
    nbmod.take_snapshot(book, "2026-10-20", {"tab": 0}, "All data")
    assert nbmod.empty_days(book, db, "2026-10-24") == []


# ---- B7: Convert references never deletes a lemma that holds data -------------------------

def test_convert_keeps_lemmas_with_a_second_language_gloss_or_built_on():
    from lemmatrix import convert_refs as cr
    from lemmatrix import defaults
    db = defaults.new_database()
    arabic = db.new_entry("D901")
    arabic.set("Gloss", "kalb", "ar")             # only a gloss in another language
    root = db.new_entry("D902")
    child = db.new_entry("D903")
    child.from_lemmas = [root.id]                 # another lemma is built from D902
    plain = db.new_entry("D904")                  # really empty
    db.entries += [arabic, root, child, plain]
    p = cr.plan(db, [cr.Row("D901", "-"), cr.Row("D902", "-"), cr.Row("D904", "-")])
    assert [e.ref for e in p.deletions] == ["D904"]
    assert sum("D901" in x for x in p.problems) == 1 and sum("D902" in x for x in p.problems) == 1


# ---- B8: undoing a pitch-kind conversion brings the Pitch back after other edits ----------

def test_pitch_kind_undo_after_another_edit(win):
    from lemmatrix import pitchkind as pk
    doc = win.doc
    e = next(e for e in doc.db.entries if any(t.get("Pitch") for t in e.tokens))
    i = next(i for i, t in enumerate(e.tokens) if t.get("Pitch"))
    pitch = e.tokens[i].get("Pitch")
    doc.convert_pitch_kind(pk.UNSPECIFIED, {pk.TOKEN_PITCH, pk.TONE_CLASS})   # delete the data
    assert not e.tokens[i].get("Pitch")
    doc.edit_entry(e, lambda x: x.tokens[i].set("Translation", "changed", "en"), "Edit")
    doc.undo.undo()                               # the edit: fresh copies of e's tokens
    doc.undo.undo()                               # the conversion
    assert pk.kind(doc.db) == pk.TONAL
    assert e.tokens[i].get("Pitch") == pitch      # was written into tokens no longer in the database


# ---- B9: Full backup leaves out half-finished writes, keeps a recording mid-rename --------

def test_full_backup_skips_half_written_files(tmp_path):
    from lemmatrix import layout
    db = tmp_path / "Main" / "LXX-VXX.xml"
    tokens = db.parent / "Soundfiles" / "Tokens"
    tokens.mkdir(parents=True)
    db.write_text("<database/>", encoding="utf-8")
    names = ["LXX-VXX.xml.saving", "D001.wav.part", "T001.TextGrid.lemmatrix-writing",
             ".LXX-VXX.xml.lemmatrix-lock"]
    for n in names[:1] + names[3:]:
        (db.parent / n).write_text("x")
    for n in names[1:3]:
        (tokens / n).write_text("x")
    (tokens / "D002.wav.lemmatrix-renaming").write_text("the only copy")
    got = {p.name for p in layout.backup_files(db)}
    assert got == {"LXX-VXX.xml", "D002.wav.lemmatrix-renaming"}
