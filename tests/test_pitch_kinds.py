# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders. Additional terms: NOTICE.md
"""Pitch kinds (IDEAS.md idea 9; DESIGN.md 3.5): tonal, intonational, unspecified, kept as typology
in the metadata (format 10); converting never loses data unasked; the New database window."""

import os
import shutil

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["LEMMATRIX_SETTINGS"] = "Lemmatrix-tests"

import pytest  # noqa: E402

from lemmatrix import newdb, pitchkind as pk, pitchview, storage  # noqa: E402
from test_ui import SAMPLES, app, win  # noqa: E402,F401


@pytest.fixture(autouse=True)
def _tonal_again():
    yield
    pitchview.load(None)
    pitchview.set_kind(pk.TONAL)


def _sample(tmp_path):
    shutil.copy2(SAMPLES / "Sample.xml", tmp_path / "Sample.xml")
    return storage.load(tmp_path / "Sample.xml")


# ---- the data (no Qt) ---------------------------------------------------------------------------

def test_an_older_database_opens_as_tonal_and_saves_format_10(tmp_path):
    from pathlib import Path
    shutil.copy2(Path(__file__).resolve().parent.parent / "samples" / "Sample.xml", tmp_path / "Sample.xml")
    assert '<database format="9">' in (tmp_path / "Sample.xml").read_text(encoding="utf-8")
    db = storage.load(tmp_path / "Sample.xml")    # format 9, like Josh's Burun database
    assert pk.kind(db) == pk.TONAL and db.upgraded
    storage.save(db, db.path, backup=False)
    text = (tmp_path / "Sample.xml").read_text(encoding="utf-8")
    assert '<database format="10">' in text
    head = text[:text.index("<researcher")]       # near the top, right after the language
    assert '<typology>' in head and '<feature id="tone" value="tonal" />' in head
    assert head.index("<variety") < head.index("<typology>")


def test_a_new_database_is_tonal(tmp_path):
    db = newdb.make(newdb.Choices())
    assert pk.kind(db) == pk.TONAL
    assert pk.pitch_field(db) is not None and pk.tone_class_field(db) is not None


def test_unspecified_has_no_pitch_and_stays_so(tmp_path):
    db = newdb.make(newdb.Choices(kind=pk.UNSPECIFIED))
    assert pk.pitch_field(db) is None and pk.tone_class_field(db) is None
    p = tmp_path / "U.xml"
    db.path = str(p)
    storage.save(db, p, backup=False)
    text = p.read_text(encoding="utf-8")
    assert 'value="unspecified"' in text and 'role="pitch"' not in text and "<pitch " not in text
    again = storage.load(p)                       # the core field isn't brought back
    assert pk.kind(again) == pk.UNSPECIFIED and pk.pitch_field(again) is None


def test_intonational_keeps_the_pitch_field_without_tone_class():
    db = newdb.make(newdb.Choices(kind=pk.INTONATIONAL))
    assert pk.pitch_field(db) is not None and pk.tone_class_field(db) is None
    assert pk.PARTS[pk.INTONATIONAL] == {"utterances"}


def test_converting_keeps_data_hidden_unless_ticked(tmp_path):
    db = _sample(tmp_path)
    held = {h.key: h.count for h in pk.holdings(db, pk.UNSPECIFIED)}
    assert held[pk.TOKEN_PITCH] > 0 and held[pk.TONE_CLASS] > 0
    before = sum(1 for e in db.entries for t in e.tokens if t.get("Pitch"))
    pk.convert(db, pk.UNSPECIFIED)                # Keep it hidden: the data and its fields stay
    assert pk.kind(db) == pk.UNSPECIFIED and pk.pitch_field(db) is not None
    assert sum(1 for e in db.entries for t in e.tokens if t.get("Pitch")) == before
    assert pk.holdings(db, pk.TONAL) == [] and pk.added(db, pk.TONAL) == []
    done = pk.convert(db, pk.UNSPECIFIED, {pk.TOKEN_PITCH, pk.TONE_CLASS})
    assert "Pitch field removed" in done and "Tone Class field removed" in done
    assert pk.pitch_field(db) is None and not any(t.get("Pitch") for e in db.entries for t in e.tokens)
    assert pk.added(db, pk.TONAL) == ["Pitch", "Tone Class"]
    pk.convert(db, pk.TONAL)
    tc = pk.tone_class_field(db)
    assert [i.name for i in tc.items] == ["H", "L", "LH", "HL"]
    names = [f.name for f in db.settings.token_fields]
    assert names.index("Pitch") == names.index("Morphemes") + 1


def test_tonal_to_intonational_offers_lemma_tokens_and_tone_class_only(tmp_path):
    db = _sample(tmp_path)
    keys = {h.key for h in pk.holdings(db, pk.INTONATIONAL)}
    assert pk.UTTERANCE_PITCH not in keys and pk.TOKEN_PITCH in keys


def test_the_archives_keep_the_kind(tmp_path):
    from lemmatrix import anonymise
    db = _sample(tmp_path)
    db.metadata.typology["tone"] = pk.INTONATIONAL
    for kind in (anonymise.ANONYMOUS, anonymise.ETHICAL):
        out = tmp_path / kind
        anonymise.export(db, None, out, anonymise.Options.for_kind(kind))
        xml = next(out.glob("*.xml"))
        assert pk.kind(storage.load(xml)) == pk.INTONATIONAL


def test_copy_setup_takes_fields_lists_and_tags_only(tmp_path):
    src = _sample(tmp_path)
    src.settings.entry_fields[-1].label = "My comment"
    db = newdb.make(newdb.Choices(copy_from=src, language_code="QQQ"))
    assert db.settings.entry_fields[-1].label == "My comment"
    assert not db.entries and db.metadata.language_code == "QQQ"
    assert [p.code for p in db.metadata.participants] == ["SP1", "SP2"]      # not the source's people


def test_you_and_the_placeholders():
    db = newdb.make(newdb.Choices(you={"name": "Joshua A. G. Smolders", "code": "JS", "email": "j@x.org"}))
    md = db.metadata
    assert [p.code for p in md.researchers] == ["JS", "RS2"] and md.author == "Joshua A. G. Smolders"
    assert md.researchers[0].email == "j@x.org" and md.researchers[0].identifiable
    assert md.location_path("L1T") == "L1 › L1 Region › L1 Town"
    blank = newdb.make(newdb.Choices())
    assert [p.code for p in blank.metadata.researchers] == ["RS1", "RS2"]


def test_soundfile_name_presets():
    assert [newdb.example_name(p) for _, p in newdb.PATTERNS] == [
        "LXX-VXX_D001_goat_PL.wav", "LXX-VXX-SP1_D001_goat_PL.wav", "LXX_D001_goat_PL.wav", "D001_goat_PL.wav"]
    db = newdb.make(newdb.Choices(pattern=newdb.PATTERNS[2][1]))
    assert db.settings.filename_pattern == "{language}_{reference}_{gloss}_{tags}"


# ---- the window -------------------------------------------------------------------------------

def test_converting_from_edit_metadata_is_one_undo_step(win, monkeypatch):
    from lemmatrix.ui import pitchkind_dialog as pkd
    db = win.doc.db
    pitches = sum(1 for e in db.entries for t in e.tokens if t.get("Pitch"))

    def answer(self, *a):                          # Keep it hidden
        self.answer = pkd.KEEP
    monkeypatch.setattr(pkd.ConvertDialog, "exec", answer)
    assert win.convert_pitch_kind(pk.INTONATIONAL)
    assert pk.kind(db) == pk.INTONATIONAL and win.doc.dirty
    assert not pitchview.has(pitchview.TOKENS) and pitchview.has(pitchview.UTTERANCES)
    assert "drawing" not in [c.key for c in win.all_table.model_.columns]
    assert win.comparison.alpha.isHidden() and win.comparison.hidden_note.text() == "no pitch"
    win.doc.undo.undo()
    assert pk.kind(db) == pk.TONAL and pitchview.has(pitchview.TOKENS)
    assert "drawing" in [c.key for c in win.all_table.model_.columns]

    def delete(self, *a):                          # Delete the ticked data, without a backup
        for b in self.ticks.values():
            b.setChecked(True)
        self.answer = pkd.DELETE
    monkeypatch.setattr(pkd.ConvertDialog, "exec", delete)
    from lemmatrix.ui import main_window
    monkeypatch.setattr(pkd, "ask_backup", lambda parent: pkd.NO_BACKUP)
    assert win.convert_pitch_kind(pk.UNSPECIFIED)
    assert pk.pitch_field(db) is None and pk.tone_class_field(db) is None
    win.doc.undo.undo()                            # Ctrl+Z brings the data back
    assert pk.kind(db) == pk.TONAL and pk.pitch_field(db) is not None
    assert sum(1 for e in db.entries for t in e.tokens if t.get("Pitch")) == pitches
    assert main_window is not None


def test_settings_for_an_unspecified_database(win):
    from lemmatrix.ui.dialogs import PreferencesDialog
    win.doc.db.metadata.typology["tone"] = pk.UNSPECIFIED
    dlg = PreferencesDialog(win, win.doc.db, win.prefs)
    assert not dlg.pitch_on.isEnabled() and not dlg.low.isEnabled()
    assert "Unspecified" in dlg.kind_note.text()
    win.doc.db.metadata.typology["tone"] = pk.TONAL


def test_the_new_day_reset_keeps_the_researcher(win, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    from lemmatrix.ui import chiprow as chips
    rows = win.sess_rows
    rows[chips.RESEARCHERS].set_keys(["RS1", "RS2"])
    rows[chips.PARTICIPANTS].set_keys(["SP1"])
    win.prefs.you = {"name": "", "code": "RS2", "email": ""}
    win._session_last_day = "2020-01-01"
    monkeypatch.setattr(QMessageBox, "exec", lambda box: None)
    monkeypatch.setattr(QMessageBox, "clickedButton", lambda box: None)     # Reset
    try:
        win._remind_new_day()
        assert rows[chips.RESEARCHERS].keys == ["RS2"] and rows[chips.PARTICIPANTS].keys == []
    finally:
        win.prefs.you = {}


def test_the_new_database_window(win):
    from lemmatrix.ui.new_database import NewDatabaseDialog
    win.prefs.you = {"name": "Joshua", "code": "JS", "email": ""}
    try:
        dlg = NewDatabaseDialog(win, win.prefs)
        assert dlg.you_code.text() == "JS"                            # remembered on this computer
        assert dlg.pitch_kind.currentData() == pk.TONAL                # the default
        dlg._language_chosen("Burun · bdi")
        assert dlg.lang_name.text() == "Burun" and dlg.lang_code.text() == "BDI"
        dlg.pitch_kind.setCurrentIndex(dlg.pitch_kind.findData(pk.INTONATIONAL))
        dlg.pattern_choice.setCurrentIndex(dlg.pattern_choice.findData("custom"))
        assert dlg.pattern.isVisibleTo(dlg)
        dlg.pattern.setText("{reference}_{gloss}")
        assert dlg.example.text() == "D001_goat.wav"
        for b in dlg.lists.group.buttons():
            if b.property("list") == "":
                b.setChecked(True)                                   # Blank, for speed
        db = newdb.make(dlg.choices())
        assert pk.kind(db) == pk.INTONATIONAL and db.metadata.language_code == "BDI"
        assert db.settings.filename_pattern == "{reference}_{gloss}" and not db.entries
    finally:
        win.prefs.you = {}
