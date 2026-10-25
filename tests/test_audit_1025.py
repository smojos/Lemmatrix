# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders. Additional terms: NOTICE.md
"""The audit of 25 October 2026: the "fix first" bugs (claude/AUDIT.md, B1–B9)."""

from test_texts import _add_text  # noqa: F401  (fixtures)


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


# ---- B10: a field renamed in Edit → Fields keeps its place in the workspace ---------------

def test_renamed_field_keeps_its_columns_cells_and_lines(win, monkeypatch):
    from lemmatrix.ui import fields_dialog
    doc = win.doc
    doc.ws_set("columns/alldata", ["ref", "f:Phonemic", "f:Translation", "f:Translation:ar"])
    doc.ws_set("columns/lemma", ["ref", "ToneClass", "Gloss"])
    doc.ws_set("lines/aligned", ["Phonemic", "Morphemes"])
    cfg = next(iter(win.configs.values()), None) or win.config_for(1)
    cfg.cell = ["drawing", "Phonemic", "Translation:ar"]

    def fake_exec(dlg):
        for f in dlg.lists["token"]:
            if f.name == "Phonemic":
                f.name = "Phonemes"
        for f in dlg.lists["lemma"]:
            if f.name == "ToneClass":
                f.name = "Tone"
        return 1
    monkeypatch.setattr(fields_dialog.FieldsDialog, "exec", fake_exec)
    win.edit_fields()
    ws = doc.ws
    assert ws.get("columns/alldata") == ["ref", "f:Phonemes", "f:Translation", "f:Translation:ar"]
    assert ws.get("columns/lemma") == ["ref", "Tone", "Gloss"]
    assert ws.get("lines/aligned") == ["Phonemes", "Morphemes"]
    assert cfg.cell == ["drawing", "Phonemes", "Translation:ar"]
    assert any(c.key == "f:Phonemes" for c in win.all_table.model_.columns)


def test_renamed_key_leaves_other_keys():
    from lemmatrix.workspace import renamed_key
    m = {"Translation": "Free translation"}
    assert renamed_key("f:Translation:ar", m) == "f:Free translation:ar"
    assert renamed_key("Translation", m) == "Free translation"
    assert renamed_key("TranslationNote", m) == "TranslationNote"
    assert renamed_key("ref", m) == "ref"


# ---- B11: a deleted field that isn't a core field stays deleted ---------------------------

def test_deleted_tone_and_inflection_class_stay_deleted(tmp_path):
    from lemmatrix import defaults, storage
    db = defaults.new_database()
    s = db.settings
    s.entry_fields = [f for f in s.entry_fields if f.name not in ("ToneClass", "InflectionClass")]
    s.text_fields = [f for f in s.text_fields if f.name != "Description"]
    assert defaults.ensure_core_fields(s) == []
    p = tmp_path / "LXX-VXX.xml"
    storage.save(db, p, backup=False)
    back = storage.load(p)
    names = [f.name for f in back.settings.entry_fields]
    assert "ToneClass" not in names and "InflectionClass" not in names
    assert "Description" not in [f.name for f in back.settings.text_fields]


def test_a_missing_core_field_still_comes_back():
    from lemmatrix import defaults
    s = defaults.new_database().settings
    s.token_fields = [f for f in s.token_fields if f.role != "morphemes"]
    assert "Morphemes" in defaults.ensure_core_fields(s)


# ---- B12: the next reference goes on past D999 --------------------------------------------

def test_next_reference_past_999():
    from lemmatrix import defaults
    db = defaults.new_database()
    db.entries += [db.new_entry(r) for r in ("D998", "D999", "D1000")]
    assert db.suggest_reference("D") == "D1001"
    db.entries.pop()
    assert db.suggest_reference("D") == "D1000"


# ---- B15: Bulk edit starts on the lemmas the lemma list shows -----------------------------

def test_bulk_edit_copies_wordlist_search_and_hide_empty(win):
    from lemmatrix import bulk
    for e in win.doc.db.entries[:6]:              # (the prototype sample has no wordlist numbers)
        e.lists["SWADESH"] = ["42"]
    win.doc.db.entries[0].tokens = []             # one of them empty: Hide empty lemmas leaves it out
    win.lemmas.set_rows(win.doc.db.entries)
    win.lemma_search.setText("SWADESH")
    win._search_timers["lemma"].timeout.emit()
    win.hide_empty.setChecked(True)
    shown = win.lemmas.proxy.rowCount()
    assert 0 < shown < len(win.doc.db.entries)
    win.open_bulk_edit()
    w = win.bulk_window
    assert w.tables[bulk.LEMMAS].proxy.rowCount() == shown   # the search was plain text before
    w.close()
    win.hide_empty.setChecked(False)
    win.lemma_search.clear()


# ---- B17: the EACW's Q families are found -------------------------------------------------

def test_q_families():
    from lemmatrix import wordlists as wl
    assert [i.number for i in wl.family("Q002")] == ["Q002", "Q002b"]     # second
    assert [i.number for i in wl.family("Q001")] == ["Q001", "Q001b", "Q001c"]
    assert wl.family("Q1736") == []                 # the number itself, no family


# ---- B18: a day's date changed outside undo; undoing a snapshot step keeps its snapshots --

def test_snapshot_undo_after_the_days_date_changed(win):
    from lemmatrix import notebook as nbmod
    doc = win.doc
    nb = doc.notebook
    doc.change_snapshots("Take snapshot", lambda: nbmod.take_snapshot(nb, "2026-10-20", {"tab": 0}, "first"))
    s = nb.session("2026-10-20")
    doc.change_snapshots("Take snapshot", lambda: nbmod.take_snapshot(nb, "2026-10-20", {"tab": 1}, "second"))
    s.date = "2026-10-19"                        # Change date… in the notebook (not an undo step)
    nb.sort()
    doc.undo.undo()                               # the second snapshot
    assert [x.about for x in s.snapshots] == ["first"]   # wiped altogether before
    doc.undo.redo()
    assert [x.about for x in s.snapshots] == ["first", "second"]


# ---- B19: a link to a lemma Hide empty lemmas hides still shows it ------------------------

def test_go_to_an_empty_lemma_with_hide_empty_on(win):
    e = win.doc.db.entries[3]
    e.tokens = []                                 # empty
    win.lemmas.set_rows(win.doc.db.entries)
    win.hide_empty.setChecked(True)
    assert not any(r is e for r in win.lemmas.visible_rows())
    assert win.go_to(e)
    assert win.lemmas.current_row() is e          # selected nothing before
    assert not win.hide_empty.isChecked()


# ---- B20: an edit keeps a multi-selection, and an unselected row unselected ---------------

def test_an_edit_keeps_the_selection(win):
    from PySide6.QtWidgets import QApplication
    from lemmatrix.ui.main_window import ALL_DATA
    db = win.doc.db
    picked = db.entries[2:5]
    win.lemmas.select_rows(picked)
    assert [r.ref for r in win.lemmas.selected_rows()] == [e.ref for e in picked]
    win.doc.edit_entry(picked[1], lambda x: x.set("Gloss", "edited", "en"), "Edit")
    QApplication.processEvents()
    assert [r.ref for r in win.lemmas.selected_rows()] == [e.ref for e in picked]   # collapsed to one before
    # All data: a token clicked to unselect it stays unselected after an edit
    win.tabs.setCurrentIndex(ALL_DATA)
    win.refresh()
    t = win.all_table
    t.select_row(t.visible_rows()[0])
    t.selectionModel().clearSelection()           # as a click on the selected token does
    assert t.selected_row() is None and t.current_row() is not None
    win.doc.edit_entry(db.entries[0], lambda x: x.set("Gloss", "again", "en"), "Edit")
    win.refresh()
    assert t.selected_row() is None               # selected again before


# ---- B21: replacing the sample asks about unsaved changes before copying over it ----------

def test_fresh_sample_asks_before_copying(win, tmp_path, monkeypatch):
    from pathlib import Path
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path / "home"))
    dst = tmp_path / "home" / "Documents" / "Lemmatrix Sample" / "Sample.xml"
    seen = []

    def confirm():                                # the unsaved-changes question: what's on disk then
        seen.append(dst.read_text(encoding="utf-8")[:20] if dst.exists() else "")
        return True
    monkeypatch.setattr(win, "_confirm_discard", confirm)
    win.open_sample()                             # the first copy, opened
    assert dst.exists() and win.doc.db.path == str(dst)
    seen.clear()
    dst.write_text("as it was on disk", encoding="utf-8")
    win.open_sample()                             # QMessageBox.question says Yes: replace
    assert seen[0] == "as it was on disk"         # asked before the copy (it was asked after)
    assert dst.read_text(encoding="utf-8").startswith("<?xml")


# ---- B22: a workspace with bytes that aren't text is unreadable, not a crash ---------------

def test_undecodable_workspace_is_unreadable(tmp_path):
    import pytest
    from lemmatrix import defaults
    from lemmatrix import workspace as wsmod
    p = tmp_path / "LXX-VXX.workspace"
    p.write_bytes(b"<workspace>\xff\xfe\x00broken</workspace>")
    with pytest.raises(wsmod.WorkspaceError):    # was a UnicodeDecodeError past the handler
        wsmod.load(p, defaults.new_database())


# ---- small bugs (claude/AUDIT.md, section 1, Small) ---------------------------------------

def test_push_to_question_from_a_new_token_keeps_the_comment_out_of_it(win):
    """S2: the comment was saved into the new token, so Cancel left it there as well as in the notebook."""
    from lemmatrix.ui.token_dialog import Slot, TokenDialog
    e = win.doc.db.entry_by_ref("D002")
    n = len(e.tokens)
    dlg = TokenDialog(win, [Slot(e, None, ("Plural", "Accusative"), explicit=True)], 0)   # not there yet
    dlg.comment.setText("Ask about the plural")
    dlg.push_to_question()
    dlg.reject()
    assert len(e.tokens) == n + 1                 # the new token exists, for the link
    new = next(t for t in e.tokens if "Accusative" in t.tags)
    assert not any("Ask about the plural" in v for v in new.values.values())
    q = win.doc.notebook.session(win.work_date()).questions[-1]
    assert q.text == "Ask about the plural" and q.token_id == new.id


def test_delete_several_tokens_sharing_a_recording(win):
    """S5: two selected tokens with one recording: it was held twice and the delete rolled back."""
    from lemmatrix import storage
    from lemmatrix.ui.main_window import TokenRow
    db = win.doc.db
    e = next(e for e in db.entries if sum(1 for t in e.tokens if t.file) >= 1 and len(e.tokens) >= 2)
    i = next(i for i, t in enumerate(e.tokens) if t.file)
    j = next(j for j in range(len(e.tokens)) if j != i)
    e.tokens[j].file = e.tokens[i].file           # two tokens, one recording (an old Keep as it is)
    path = storage.sound_folder(db) / e.tokens[i].file
    assert path.exists()
    win.prefs.delete_recordings_with_tokens = True
    n = len(e.tokens)
    assert win.delete_tokens([TokenRow(e, i), TokenRow(e, j)])
    assert len(e.tokens) == n - 2 and not path.exists()
    win.doc.undo.undo()
    assert len(e.tokens) == n and path.exists()


def test_ok_with_nothing_changed_leaves_the_database_saved(win, monkeypatch):
    """S7: OK in Settings, Edit → Metadata or Edit → Fields always marked the database unsaved."""
    from PySide6.QtWidgets import QDialog
    monkeypatch.setattr(QDialog, "exec", lambda self: 1)          # OK, nothing touched
    win.doc.undo.setClean()
    win.doc._settings_dirty = False
    win.doc.notebook.dirty = False
    for open_it in (win.edit_settings, win.edit_metadata, win.edit_fields):
        open_it()
        assert not win.doc.dirty, open_it.__name__

    def rename(dlg):                              # a real change still counts
        next(f for f in dlg.lists["lemma"] if f.name == "ToneClass").name = "Tone"
        return 1
    from lemmatrix.ui import fields_dialog
    monkeypatch.setattr(fields_dialog.FieldsDialog, "exec", rename)
    win.edit_fields()
    assert win.doc.dirty


def test_receive_closes_a_zip_it_turns_down(tmp_path, monkeypatch):
    """S10: a zip that isn't a response, or answers another database's request, stayed open
    (locked on Windows)."""
    import json
    import zipfile

    import pytest
    from lemmatrix import defaults
    from lemmatrix import elicit as el
    opened = []

    class Tracked(zipfile.ZipFile):
        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            opened.append(self)
    db = defaults.new_database()
    db.path = str(tmp_path / "LXX-VXX.xml")
    other = tmp_path / "other.zip"
    with zipfile.ZipFile(other, "w") as zf:
        zf.writestr("response.json", json.dumps({"format": el.RESPONSE_FORMAT, "request": "nope", "cards": []}))
    wrong = tmp_path / "wrong.zip"
    with zipfile.ZipFile(wrong, "w") as zf:
        zf.writestr("response.json", json.dumps({"format": "something else"}))
    monkeypatch.setattr(el.zipfile, "ZipFile", Tracked)
    for path in (other, wrong):
        with pytest.raises(el.ElicitError):
            el.receive(db, path)
    assert len(opened) == 2 and all(z.fp is None for z in opened)   # closed


def test_ipa_size_applies_at_start_and_everywhere(win):
    """S11: the IPA size reached the lemma list and All data only after Settings, and nothing else."""
    from lemmatrix.ui import widgets
    from lemmatrix.ui.main_window import MainWindow
    old = win.prefs.ipa_size
    try:
        win.prefs.ipa_size = 17
        fresh = MainWindow()                      # a new start
        assert fresh.lemmas.model_.ipa.pointSize() == 17 and fresh.all_table.model_.ipa.pointSize() == 17
        assert fresh.lt_view.delegate.ipa.pointSize() == 17
        uw = fresh.open_utterances()
        assert uw.table.model_.ipa.pointSize() == 17
        fresh.all_table.set_zoom(1.5)
        fresh.prefs.ipa_size = 12                 # Settings → Display, then OK
        fresh.apply_ipa_size()
        assert uw.table.model_.ipa.pointSize() == 12
        assert round(fresh.all_table.model_.ipa.pointSizeF()) == 18           # 12 at its zoom
        fresh.doc.undo.setClean()
        fresh.doc._settings_dirty = False
        fresh.close()
    finally:
        win.prefs.ipa_size = old
        widgets.set_ipa_size(old)


# ---- the utterance dialogue fits the screen (Josh, 25 October: its recording area was out of reach) --

def test_utterance_dialogue_scrolls_rather_than_outgrowing_the_screen(win, tmp_path, monkeypatch):
    from lemmatrix.ui import widgets
    from lemmatrix.ui.token_dialog import Slot
    from lemmatrix.ui.utterances import UtteranceDialog
    monkeypatch.setattr(widgets, "IPA_SIZE", 22)              # large IPA, as on Josh's screen
    uw, t = _add_text(win, tmp_path, monkeypatch)
    uw.texts.lines.select_row(uw.texts.lines.rows[0])
    u = uw.texts.clip()[0]
    dlg = UtteranceDialog(win, [Slot(u, 0)], 0, uw)
    assert dlg.minimumSizeHint().height() < 400                # the body scrolls; it set the minimum before
    body = dlg.body_scroll.widget()
    for w in (dlg.meter, dlg.clip_source_box, dlg.lemma_find, dlg.header):
        assert body.isAncestorOf(w)                            # the recording area, Source, Lemmas
    dlg.resize(900, 3000)
    dlg.show()
    a = dlg.screen().availableGeometry()
    assert dlg.frameGeometry().height() <= a.height()          # never taller than the screen
    assert not body.isAncestorOf(dlg.next_btn)                 # Back, Next, OK, Cancel always in view
    dlg.reject()
