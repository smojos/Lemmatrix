# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders. Additional terms: NOTICE.md
"""Texts and songs (idea 7, stage 3): the model, the file, TextGrid lines and clipping."""

from pathlib import Path

import numpy as np

from lemmatrix import audio, storage, textgrid as tgmod
from lemmatrix.defaults import new_database
from lemmatrix.model import TEXTS, ClipSource, Text, TierMapping, TierRule

SAMPLES = Path(__file__).resolve().parent / "data" / "sample"    # the prototype's sample (conftest.py)


def _db(tmp_path):
    db = new_database()
    db.path = str(tmp_path / "Lex.xml")
    db.metadata.language_code, db.metadata.variety_code = "LXX", "VXX"
    return db


def _grid(path, speaker=""):
    at = f"@{speaker}" if speaker else ""
    tgmod.write_example(path, {
        f"tx{at}": [(0.5, 1.5, "ʔəŋ kɒ"), (2.0, 3.0, "ɛ ŋəə")],
        f"ge{at}": [(0.5, 1.0, "hare"), (1.0, 1.5, "run.PST"), (2.0, 3.0, "where.3SG")],
        f"ft{at}": [(0.5, 1.5, "the hare ran"), (2.0, 3.0, "where is he?")],
        f"mb{at}": [(0.5, 1.5, "ʔəŋ k-ɔ")],
    }, 4.0)
    return path


def test_new_databases_have_text_settings():
    s = new_database().settings
    assert [c.letter for c in s.categories(TEXTS)] == ["T", "S"]
    assert [f.name for f in s.text_fields] == ["Title", "Genre", "Status", "Description", "Comment"]
    assert "folktale" in s.text_field("genre").all_values()
    assert s.text_field("status").all_values() == ["untranscribed", "transcribed", "translated",
                                                     "analyzed", "finished"]
    m = s.tier_mapping
    assert m.main == "tx" and m.rule("ft@SP1").key == "Translation:en" and m.rule("mb").field == ""


def test_lines_are_read_with_the_mapping(tmp_path):
    db = _db(tmp_path)
    lines = tgmod.read_lines(_grid(tmp_path / "a.TextGrid"), db.settings.tier_mapping, "SP1")
    assert [(l.start, l.end) for l in lines] == [(0.5, 1.5), (2.0, 3.0)]
    first = lines[0]
    assert first.values == {"Phonetic": "ʔəŋ kɒ", "Morphemes": "hare run.PST", "Translation:en": "the hare ran"}
    assert first.speaker == "SP1" and "mb" not in first.copied           # mb is ignored
    assert first.copied["tx"] == "ʔəŋ kɒ"
    assert [t.name for t in tgmod.tiers(tmp_path / "a.TextGrid")] == ["tx", "ge", "ft", "mb"]


def test_speaker_tiers(tmp_path):
    db = _db(tmp_path)
    p = tmp_path / "b.TextGrid"
    tgmod.write_example(p, {"tx@SP1": [(0.0, 1.0, "a")], "ft@SP1": [(0.0, 1.0, "A")],
                            "tx@SP2": [(0.5, 2.0, "b")], "ft@SP2": [(0.5, 2.0, "B")]}, 2.0)
    lines = tgmod.read_lines(p, db.settings.tier_mapping)
    assert [(l.speaker, l.values["Translation:en"]) for l in lines] == [("SP1", "A"), ("SP2", "B")]


def test_no_main_tier_is_explained(tmp_path):
    p = tmp_path / "c.TextGrid"
    tgmod.write_example(p, {"words": [(0, 1, "x")]}, 1.0)
    try:
        tgmod.read_lines(p, TierMapping("tx", []))
    except tgmod.TextGridError as exc:
        assert "tx" in str(exc) and "words" in str(exc)
    else:
        raise AssertionError


def test_texts_are_saved_and_read(tmp_path):
    db = _db(tmp_path)
    t = Text("T001", "Hyena and Hare", "2026-10-18", ["SP1", "SP2"], ["JS"], ["Sample variety village"],
             "LXX-VXX_T001_Hyena_and_Hare.wav", "LXX-VXX_T001_Hyena_and_Hare.TextGrid")
    t.set("Title", "Hyena and Hare")
    t.set("Genre", "folktale")
    t.tiers = TierMapping("words", [TierRule("words", "Phonemic")])
    db.texts.append(t)
    u = db.new_utterance("W001", "hare ran")
    u.source = ClipSource(t.id, 0.5, 1.5, {"tx": "ʔəŋ kɒ", "ft": "the hare ran"}, "2026-10-18T20:00:00")
    db.utterances.append(u)
    storage.save(db, backup=False)
    text = Path(db.path).read_text(encoding="utf-8")
    assert f'<database format="{storage.FORMAT_VERSION}">' in text and "<texts>" in text
    again = storage.load(db.path)
    v = again.texts[0]
    assert (v.ref, v.file_label, v.participants, v.locations, v.get("Genre")) == \
        ("T001", "Hyena and Hare", ["SP1", "SP2"], ["Sample variety village"], "folktale")
    assert v.tiers.main == "words" and v.id == t.id
    assert again.utterances[0].source == u.source
    assert again.clipped_from(v) == [again.utterances[0]]
    assert again.expected_text_name(v) == "LXX-VXX_T001_Hyena_and_Hare.wav"
    assert again.expected_text_name(v, ".TextGrid") == "LXX-VXX_T001_Hyena_and_Hare.TextGrid"
    assert again.suggest_utterance_reference("T") == "T002"


def test_format_5_is_upgraded_for_texts_and_lowercase_examples(tmp_path):
    db = _db(tmp_path)
    for _, g in db.settings.tags.leaf_groups():
        if g.name == "Examples":
            for t in g.tags:
                t.code = t.code.upper()
    storage.save(db, backup=False)
    p = Path(db.path)
    old = p.read_text(encoding="utf-8").replace(f'format="{storage.FORMAT_VERSION}"', 'format="5"')
    import re
    old = re.sub(r"\s*<text-fields>.*?</text-fields>", "", old, flags=re.S)
    old = re.sub(r"\s*<tier-mapping.*?</tier-mapping>", "", old, flags=re.S)
    old = re.sub(r'\s*<category letter="[TS]" for="texts">[^<]*</category>', "", old)
    p.write_text(old, encoding="utf-8")
    again = storage.load(p)
    assert [c.letter for c in again.settings.categories(TEXTS)] == ["T", "S"]
    assert again.settings.text_field("genre") is not None and again.settings.tier_mapping.main == "tx"
    codes = [t.code for _, g in again.settings.tags.leaf_groups() if g.name == "Examples" for t in g.tags]
    assert codes == ["x1", "x2"]
    assert any("texts" in n for n in again.load_notes)


def test_clip_and_segment(tmp_path):
    rate = 8000
    samples = (0.2 * np.sin(np.arange(rate * 3) / 5)).astype(np.float32)
    src = tmp_path / "long.wav"
    audio.write_wav(src, samples, rate, 24)
    audio.clip_wav(src, tmp_path / "clip.wav", 1.0, 1.5, artist="SP1", date="2026-10-18")
    a, r = audio.read_wav(tmp_path / "clip.wav")
    assert r == rate and len(a) == rate // 2
    assert audio.read_info(tmp_path / "clip.wav").get("IART") == "SP1"
    import wave
    with wave.open(str(tmp_path / "clip.wav")) as w:
        assert w.getsampwidth() == 3                        # the original's bit depth is kept
    seg, _ = audio.read_segment(src, 2.5, 9.0)               # clipped to the end of the file
    assert len(seg) == rate // 2
    assert abs(audio.duration(src) - 3.0) < 1e-6


# ---- the Texts tab ------------------------------------------------------------------------

import os
import time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["LEMMATRIX_SETTINGS"] = "Lemmatrix-tests"


def _recording(path, seconds=4.0, rate=8000):
    audio.write_wav(path, (0.2 * np.sin(np.arange(int(rate * seconds)) / 5)).astype(np.float32), rate, 16)
    return path


def _add_text(win, tmp_path, monkeypatch, title="Hyena and Hare", src=None):
    from lemmatrix.ui import texts as tx
    src = src or tmp_path / "field"
    src.mkdir(parents=True, exist_ok=True)
    wav = _recording(src / "story.wav")
    if not (src / "story.TextGrid").exists():
        _grid(src / "story.TextGrid")

    def fake_exec(dlg):
        dlg.new_wav = wav
        dlg.new_grid = None
        for ext in (".TextGrid",):
            if wav.with_suffix(ext).exists():
                dlg.new_grid = wav.with_suffix(ext)
        dlg._show_files()
        dlg.fields["Title"].setText(title)
        dlg.fields["Genre"].setCurrentText("folktale")
        return 1
    monkeypatch.setattr(tx.TextDialog, "exec", fake_exec)
    uw = win.open_utterances()
    uw.tabs.setCurrentIndex(0)
    uw.texts.add()
    return uw, win.doc.db.texts[-1]


def test_add_a_text_copies_its_files_and_shows_its_lines(win, tmp_path, monkeypatch):
    uw, t = _add_text(win, tmp_path, monkeypatch)
    folder = tmp_path / "Soundfiles" / "Texts"
    assert t.ref == "T001" and t.file_label == "Hyena and Hare" and t.get("Genre") == "folktale"
    assert (folder / "LXX-VXX_T001_Hyena_and_Hare.wav").exists()
    assert (folder / "LXX-VXX_T001_Hyena_and_Hare.TextGrid").exists()
    assert (tmp_path / "field" / "story.wav").exists()                    # the original stays
    assert len(uw.texts.lines.rows) == 2
    keys = [f.key for f in uw.texts.lines.fields]
    assert "Phonetic" in keys and "Translation:en" in keys
    win.doc.undo.undo()
    assert win.doc.db.texts == [] and not (folder / "LXX-VXX_T001_Hyena_and_Hare.wav").exists()
    win.doc.undo.redo()
    assert (folder / "LXX-VXX_T001_Hyena_and_Hare.wav").exists()


def test_a_text_already_in_soundfiles_texts_is_renamed_not_copied(win, tmp_path, monkeypatch):
    folder = tmp_path / "Soundfiles" / "Texts"
    uw, t = _add_text(win, tmp_path, monkeypatch, src=folder)
    assert sorted(f.name for f in folder.iterdir()) == ["LXX-VXX_T001_Hyena_and_Hare.TextGrid",
                                                       "LXX-VXX_T001_Hyena_and_Hare.wav"]
    assert len(uw.texts.lines.rows) == 2
    win.doc.undo.undo()                                    # the old names come back
    assert sorted(f.name for f in folder.iterdir()) == ["story.TextGrid", "story.wav"]
    win.doc.undo.redo()
    assert (folder / "LXX-VXX_T001_Hyena_and_Hare.wav").exists() and not (folder / "story.wav").exists()
    assert win.doc.revert_renames() == []                  # discarding the changes too
    assert sorted(f.name for f in folder.iterdir()) == ["story.TextGrid", "story.wav"]


def test_a_text_already_named_right_is_taken_as_it_is(win, tmp_path, monkeypatch):
    folder = tmp_path / "Soundfiles" / "Texts"
    folder.mkdir(parents=True, exist_ok=True)
    wav = _recording(folder / "LXX-VXX_T001_Hyena_and_Hare.wav")
    _grid(folder / "LXX-VXX_T001_Hyena_and_Hare.TextGrid")
    from lemmatrix.ui import texts as tx

    def fake_exec(dlg):
        dlg.new_wav, dlg.new_grid = wav, wav.with_suffix(".TextGrid")
        dlg._show_files()
        dlg.fields["Title"].setText("Hyena and Hare")
        return 1
    monkeypatch.setattr(tx.TextDialog, "exec", fake_exec)
    uw = win.open_utterances()
    uw.texts.add()
    t = win.doc.db.texts[-1]
    assert t.file == wav.name and t.textgrid == "LXX-VXX_T001_Hyena_and_Hare.TextGrid"
    assert len(list(folder.iterdir())) == 2
    win.doc.undo.undo()
    assert win.doc.db.texts == [] and wav.exists()          # nothing to move: the file stays


def test_import_a_wav_already_in_soundfiles_utterances(win, tmp_path, monkeypatch):
    folder = tmp_path / "Soundfiles" / "Utterances"
    folder.mkdir(parents=True, exist_ok=True)
    w = _recording(folder / "hare ran.wav")
    uw = win.open_utterances()
    u = uw.import_files([str(w)])[0]
    assert [f.name for f in folder.iterdir()] == [u.token.file] and u.token.file != "hare ran.wav"
    win.doc.undo.undo()
    assert [f.name for f in folder.iterdir()] == ["hare ran.wav"]


def test_clip_lines_as_utterances(win, tmp_path, monkeypatch):
    uw, t = _add_text(win, tmp_path, monkeypatch)
    p = uw.texts
    p.lines.selectAll()
    items = p.clip()
    db = win.doc.db
    assert [u.ref for u in items] == ["W001", "W002"]
    u = items[0]
    assert u.label == "the hare ran" and u.token.get("Phonetic") == "ʔəŋ kɒ"
    assert u.token.get("Translation", "en") == "the hare ran" and u.token.get("Morphemes") == "hare run.PST"
    assert u.source.text == t.id and (u.source.start, u.source.end) == (0.5, 1.5)
    assert u.source.copied["ft"] == "the hare ran" and u.source.modified
    clip = tmp_path / "Soundfiles" / "Utterances" / u.token.file
    a, rate = audio.read_wav(clip)
    assert abs(len(a) / rate - 1.2) < 0.01                 # the line, with 100 ms either side
    assert db.clipped_from(t) == items
    assert p.lines.clips.get(p.lines.rows[0].id) == ["W001"]
    win.doc.undo.undo()                                    # one step for both
    assert db.utterances == [] and not clip.exists()


def test_edit_text_title_in_file_names_renames_both_files(win, tmp_path, monkeypatch):
    from lemmatrix.ui import texts as tx
    uw, t = _add_text(win, tmp_path, monkeypatch)

    def fake_exec(dlg):
        dlg.label.setText("Hare story")
        return 1
    monkeypatch.setattr(tx.TextDialog, "exec", fake_exec)
    uw.texts.edit(t)
    folder = tmp_path / "Soundfiles" / "Texts"
    assert t.file == "LXX-VXX_T001_Hare_story.wav" and t.textgrid == "LXX-VXX_T001_Hare_story.TextGrid"
    assert (folder / t.file).exists() and (folder / t.textgrid).exists()
    win.doc.undo.undo()
    assert (folder / "LXX-VXX_T001_Hyena_and_Hare.TextGrid").exists()


def test_a_new_tier_is_learned_and_a_different_choice_is_the_texts_own(win, tmp_path, monkeypatch):
    from lemmatrix.ui import texts as tx
    db = win.doc.db
    src = tmp_path / "field"
    src.mkdir()
    wav = _recording(src / "song.wav")
    tgmod.write_example(src / "song.TextGrid", {"tx": [(0.2, 1.0, "la la")], "nt": [(0.2, 1.0, "a note")]}, 4.0)

    def fake_exec(dlg):
        dlg.new_wav, dlg.new_grid = wav, src / "song.TextGrid"
        dlg._show_files()
        dlg.fields["Title"].setText("Song")
        rows = {dlg.tiers.item(r, 0).text(): r for r in range(dlg.tiers.rowCount())}
        combo = dlg.tiers.cellWidget(rows["nt"], 2)
        combo.setCurrentIndex(combo.findText("Comment"))
        combo = dlg.tiers.cellWidget(rows["tx"], 2)
        combo.setCurrentIndex(combo.findText("Phonemic"))  # unlike the database's rule
        return 1
    monkeypatch.setattr(tx.TextDialog, "exec", fake_exec)
    uw = win.open_utterances()
    uw.texts.add()
    t = db.texts[-1]
    assert db.settings.tier_mapping.rule("nt").field == "Comment"          # learned
    assert db.settings.tier_mapping.rule("tx").field == "Phonetic"         # unchanged
    assert t.tiers is not None and t.tiers.rule("tx").field == "Phonemic"  # the text's own
    assert uw.texts.lines.rows[0].values == {"Phonemic": "la la", "Comment": "a note"}


def test_delete_a_text_holds_its_files(win, tmp_path, monkeypatch):
    uw, t = _add_text(win, tmp_path, monkeypatch)
    folder = tmp_path / "Soundfiles" / "Texts"
    uw.texts.table.select_row(t)
    uw.texts.delete()
    assert win.doc.db.texts == [] and not any(folder.iterdir())
    win.doc.undo.undo()
    assert win.doc.db.texts == [t] and (folder / t.file).exists() and (folder / t.textgrid).exists()


def test_play_a_line(win, tmp_path, monkeypatch):
    uw, t = _add_text(win, tmp_path, monkeypatch)
    played = []
    monkeypatch.setattr(win.player, "play_samples", lambda s, r, *a: played.append(len(s) / r))
    uw.texts.lines.select_row(uw.texts.lines.rows[1])
    uw.texts.play_line()
    uw.texts.play_line(context=True)
    assert abs(played[0] - 1.0) < 0.01 and abs(played[1] - 4.0) < 0.01   # 2 s either side, to the ends


def test_praat_gets_the_textgrid_too(win, tmp_path, monkeypatch):
    uw, t = _add_text(win, tmp_path, monkeypatch)
    from lemmatrix import praat
    assert "selectObject: sound, grid" in praat.script_for(Path("a.wav"), Path("a.TextGrid"))
    got = []
    monkeypatch.setattr(win, "open_in_praat",
                        lambda path, parent=None, textgrid=None, select=None: got.append((path, textgrid, select)))
    uw.texts.lines.clearSelection()
    uw.texts.open_in_praat()
    assert got[0][0].name == t.file and got[0][1].name == t.textgrid
    uw.texts.lines.select_row(uw.texts.lines.rows[1])          # at the selected line
    uw.texts.open_in_praat()
    assert got[1][2] == (2.0, 3.0)
    script = praat.script_for(Path("a.wav"), Path("a.TextGrid"), (2.0, 3.0))
    assert "editor: grid\n    Zoom: 1.0000, 4.0000\n    Select: 2.0000, 3.0000\nendeditor" in script
    assert "Zoom: 0.0000" in praat.script_for(Path("a.wav"), Path("a.TextGrid"), (0.5, 1.5))


def test_import_a_wav_with_a_textgrid_beside_it(win, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    src = tmp_path / "in"
    src.mkdir()
    one = _recording(src / "one.wav")
    tgmod.write_example(src / "one.TextGrid", {"tx": [(0.1, 0.9, "ʔəŋ kɒ")], "ft": [(0.1, 0.9, "the hare ran")]}, 4.0)
    two = _recording(src / "two.wav")
    _grid(src / "two.TextGrid")                           # two lines
    uw = win.open_utterances()
    monkeypatch.setattr(uw, "_ask_lines", lambda wav, lines: ("join", None))
    items = uw.import_files([str(one), str(two)])
    assert items[0].token.get("Phonetic") == "ʔəŋ kɒ" and items[0].token.get("Translation", "en") == "the hare ran"
    assert items[1].token.get("Phonetic") == "ʔəŋ kɒ ɛ ŋəə"                     # joined
    monkeypatch.setattr(uw, "_ask_lines", lambda wav, lines: ("one", 1))
    third = uw.import_files([str(two)])[0]
    assert third.token.get("Phonetic") == "ɛ ŋəə"
    monkeypatch.setattr(uw, "_ask_lines", lambda wav, lines: ("text", None))
    assert uw.import_files([str(two)]) == []
    t = win.doc.db.texts[-1]
    assert t.ref == "T001" and t.textgrid.endswith(".TextGrid")
    assert (tmp_path / "Soundfiles" / "Texts" / t.textgrid).exists()
    # several at once: each its own reference (all got T002, and the second failed: audit, 25 October)
    three = _recording(src / "three.wav")
    _grid(src / "three.TextGrid")
    warned = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: warned.append(a[2]))
    assert uw.import_files([str(two), str(three)]) == []
    assert [x.ref for x in win.doc.db.texts[-2:]] == ["T002", "T003"] and not warned


def test_clipped_utterance_shows_its_source(win, tmp_path, monkeypatch):
    from lemmatrix.ui.token_dialog import Slot
    from lemmatrix.ui.utterances import UtteranceDialog
    uw, t = _add_text(win, tmp_path, monkeypatch)
    uw.texts.lines.select_row(uw.texts.lines.rows[0])
    u = uw.texts.clip()[0]
    dlg = UtteranceDialog(win, [Slot(u, 0)], 0, uw)
    assert not dlg.clip_source_box.isHidden() and "T001" in dlg.source_label.text()
    played = []
    monkeypatch.setattr(win.player, "play_samples", lambda s, r, *a: played.append(len(s) / r))
    dlg._play_context()
    assert abs(played[0] - 3.5) < 0.01                    # 0.5–1.5 with 2 s either side, from 0
    dlg.edits["Comment"].setText("checked")
    dlg._ok()
    assert u.source is not None and u.token.get("Comment") == "checked"   # the link stays


def test_notebook_lists_the_days_texts(win, tmp_path, monkeypatch):
    """A text is listed on the day its lines are worked on, not the day it was added (21 October)."""
    uw, t = _add_text(win, tmp_path, monkeypatch)
    win.write_notebook()
    win.open_notebook(win.work_date())
    win.notebook_dialog.reload(win.work_date())
    assert win.notebook_dialog.texts.topLevelItemCount() == 0      # added only
    win.notebook_dialog.close()
    t.date = win.work_date()
    uw.texts.set_line_field(uw.texts.lines.rows[0], "Translation:en", "the hare fled")
    assert t.id in win.doc.notebook.session(win.work_date()).texts
    win.open_notebook(t.date)
    nb = win.notebook_dialog
    nb.reload(t.date)
    assert nb.texts.topLevelItemCount() == 1 and "T001" in nb.texts.topLevelItem(0).text(0)
    from lemmatrix.ui.notebook_dialog import TEXTS_TAB
    assert nb.tabs.tabText(TEXTS_TAB) == "Texts (1)"
    nb._open_text(nb.texts.topLevelItem(0))
    assert uw.texts.current() is t and uw.tabs.currentIndex() == 0
    nb.close()


def test_update_all_names_renames_texts_files(win, tmp_path, monkeypatch):
    uw, t = _add_text(win, tmp_path, monkeypatch)
    win.doc.db.settings.text_pattern = "{reference} {title}"
    win.update_all_names(ask=False)
    folder = tmp_path / "Soundfiles" / "Texts"
    assert t.file == "T001_Hyena_and_Hare.wav" and (folder / t.file).exists()
    assert (folder / "T001_Hyena_and_Hare.TextGrid").exists()


def test_tier_mapping_page_and_text_fields(win):
    from lemmatrix.ui.lists_dialog import TIERS, ListsDialog
    from lemmatrix.ui.fields_dialog import FieldsDialog
    db = win.doc.db
    dlg = ListsDialog(win, db, win.doc.notebook, TIERS)
    ed = dlg.tier_editor
    assert [r.tier for r in ed.mapping().rules] == ["tx", "ge", "ft", "mb"] and ed.mapping().main == "tx"
    assert any(f.name == "Genre" for f, _ in dlg.field_lists)               # the genre list is edited here
    ed.table.item(3, 0).setText("mb@SP1")
    assert "@" in ed.problem()
    f = FieldsDialog(win, db)
    assert [x.name for x in f.lists["text"]][:3] == ["Title", "Genre", "Status"]
    f.lists["token"][0].name = "Narrow"                                    # Phonetic renamed…
    f.apply()
    assert db.settings.tier_mapping.rule("tx").field == "Narrow"          # …and the tier follows


def test_text_file_dialogues_open_in_soundfiles_texts(win, monkeypatch):
    from PySide6.QtWidgets import QFileDialog
    from lemmatrix.ui import texts as tx
    seen = []
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda parent, title, start, *a, **k: (seen.append(start), ("", ""))[1])
    uw = win.open_utterances()
    dlg = tx.TextDialog(uw.texts)
    dlg._choose_wav()
    dlg._choose_grid()
    folder = storage.text_folder(win.doc.db)
    assert [Path(s) for s in seen] == [folder, folder] and folder.is_dir()
    dlg.close()


# ---- Pull (stage 4) -----------------------------------------------------------------------

def _resave(grid, tiers, end=4.0):
    import time as _t
    tgmod.write_example(grid, tiers, end)
    st = os.stat(grid)
    _resave.n = getattr(_resave, "n", 0) + 10
    os.utime(grid, (st.st_atime, _t.time() + _resave.n))   # a later time to the second


def test_pull_a_changed_line_from_the_window(win, tmp_path, monkeypatch):
    from lemmatrix.ui import pull_dialog
    uw, t = _add_text(win, tmp_path, monkeypatch)
    uw.texts.lines.selectAll()
    first, second = uw.texts.clip()
    first.token.set("Comment", "mine")
    grid = tmp_path / "Soundfiles" / "Texts" / t.textgrid
    clip = tmp_path / "Soundfiles" / "Utterances" / first.token.file
    size = clip.stat().st_size
    _resave(grid, {"tx": [(0.4, 1.5, "ʔəŋ kɒɒ"), (2.0, 3.0, "ɛ ŋəə")],
                   "ge": [(0.5, 1.0, "hare"), (1.0, 1.5, "run.PST"), (2.0, 3.0, "where.3SG")],
                   "ft": [(0.4, 1.5, "the hare ran"), (2.0, 3.0, "where is he?")],
                   "mb": [(0.5, 1.5, "ʔəŋ k-ɔ")]})
    uw.tabs.setCurrentIndex(1)
    uw.refresh()
    assert uw._flagged(first) and not uw._flagged(second)
    assert "changed" in uw._source_display(first) and uw.checks[first.id].moved
    shown = {}
    monkeypatch.setattr(pull_dialog.PullDialog, "exec",
                        lambda dlg: shown.setdefault("rows", [dlg.tree.topLevelItem(i).text(1)
                                                              for i in range(dlg.tree.topLevelItemCount())]) and 1)
    uw.table.select_row(first)
    uw.pull_selected()
    assert shown["rows"] == ["Phonetic", "Times"]
    assert first.token.get("Phonetic") == "ʔəŋ kɒɒ" and first.token.get("Comment") == "mine"
    assert first.source.start == 0.4 and not uw._flagged(first)
    assert clip.stat().st_size > size                     # cut again: 0.1 s longer
    win.doc.undo.undo()
    assert first.token.get("Phonetic") == "ʔəŋ kɒ" and first.source.start == 0.5
    uw.refresh()
    assert uw._flagged(first)


def test_check_dialog_and_unlink(win, tmp_path, monkeypatch):
    from lemmatrix.ui import pull_dialog
    uw, t = _add_text(win, tmp_path, monkeypatch)
    uw.texts.lines.selectAll()
    first, second = uw.texts.clip()
    grid = tmp_path / "Soundfiles" / "Texts" / t.textgrid
    _resave(grid, {"tx": [(2.0, 3.0, "ɛ ŋəə")], "ft": [(2.0, 3.0, "where is he!")]})
    dlg = pull_dialog.CheckDialog(win)
    labels = sorted(dlg.tree.topLevelItem(i).text(3) for i in range(dlg.tree.topLevelItemCount()))
    assert labels == ["changed", "line not found"]
    monkeypatch.setattr(pull_dialog.PullDialog, "exec", lambda d: 1)
    dlg.pull()                                            # nothing selected: all that can be
    assert second.token.get("Translation", "en") == "where is he!"
    assert [dlg.tree.topLevelItem(i).text(3) for i in range(dlg.tree.topLevelItemCount())] == ["line not found"]
    dlg.tree.topLevelItem(0).setSelected(True)
    dlg.unlink()
    assert first.source is None and dlg.tree.topLevelItemCount() == 0
    assert "match" in dlg.note.text()
    dlg.close()


def test_utterance_dialog_shows_the_flag_and_pulls(win, tmp_path, monkeypatch):
    from lemmatrix.ui import pull_dialog
    from lemmatrix.ui.token_dialog import Slot
    from lemmatrix.ui.utterances import UtteranceDialog
    uw, t = _add_text(win, tmp_path, monkeypatch)
    uw.texts.lines.select_row(uw.texts.lines.rows[0])
    (u,) = uw.texts.clip()
    grid = tmp_path / "Soundfiles" / "Texts" / t.textgrid
    _resave(grid, {"tx": [(0.5, 1.5, "ʔəŋ kɒ"), (2.0, 3.0, "ɛ ŋəə")],
                   "ft": [(0.5, 1.5, "the hare ran away"), (2.0, 3.0, "where is he?")]})
    dlg = UtteranceDialog(win, [Slot(u, 0)], 0, uw)
    assert not dlg.pull_btn.isHidden() and "Changed in the TextGrid" in dlg.source_label.text()
    monkeypatch.setattr(pull_dialog.PullDialog, "exec", lambda d: 1)
    dlg._pull()
    assert u.token.get("Translation", "en") == "the hare ran away" and dlg.pull_btn.isHidden()
    dlg.close()


# ---- Pull (stage 4) -------------------------------------------------------------------------

def _resave(path, tiers, end=4.0):
    """Change the TextGrid as Praat would (a later time, to the second)."""
    import time
    tgmod.write_example(path, tiers, end)
    st = os.stat(path)
    os.utime(path, (st.st_atime, time.time() + 60))


def _clipped(win, tmp_path, monkeypatch):
    uw, t = _add_text(win, tmp_path, monkeypatch)
    uw.texts.lines.select_row(uw.texts.lines.rows[0])
    u = uw.texts.clip()[0]
    return uw, t, u, tmp_path / "Soundfiles" / "Texts" / t.textgrid


def test_a_changed_line_is_flagged_and_pulled(win, tmp_path, monkeypatch):
    from lemmatrix.ui import pull_dialog
    uw, t, u, grid = _clipped(win, tmp_path, monkeypatch)
    uw.refresh()
    assert not uw._flagged(u) and uw._source_display(u).startswith("T001 ")
    _resave(grid, {"tx": [(0.5, 1.5, "ʔəŋ kɒɒ"), (2.0, 3.0, "ɛ ŋəə")],
                   "ft": [(0.5, 1.5, "the hare ran"), (2.0, 3.0, "where is he?")]})
    assert uw.recheck() and uw._flagged(u) and "changed" in uw._source_value(u)
    uw.refresh()
    uw.table.select_row(u)
    shown = {}

    def fake_exec(dlg):
        shown["rows"] = [[dlg.tree.topLevelItem(i).text(c) for c in range(4)] for i in range(dlg.tree.topLevelItemCount())]
        return 1
    monkeypatch.setattr(pull_dialog.PullDialog, "exec", fake_exec)
    uw.pull_selected()
    assert shown["rows"] == [["W001", "Phonetic", "ʔəŋ kɒ", "ʔəŋ kɒɒ"]]
    assert u.token.get("Phonetic") == "ʔəŋ kɒɒ" and not uw._flagged(u)
    win.doc.undo.undo()
    assert u.token.get("Phonetic") == "ʔəŋ kɒ" and u.source.copied["tx"] == "ʔəŋ kɒ"


def test_moved_times_cut_the_clip_again(win, tmp_path, monkeypatch):
    from lemmatrix.ui import pull_dialog
    uw, t, u, grid = _clipped(win, tmp_path, monkeypatch)
    clip = tmp_path / "Soundfiles" / "Utterances" / u.token.file
    before = audio.duration(clip)
    _resave(grid, {"tx": [(0.5, 2.5, "ʔəŋ kɒ")], "ft": [(0.5, 2.5, "the hare ran")]})
    monkeypatch.setattr(pull_dialog.PullDialog, "exec", lambda dlg: 1)
    from lemmatrix import pull
    c = pull.check(win.doc.db, u)
    assert c.status == pull.MOVED
    assert pull_dialog.pull_utterances(win, uw, [c])
    assert (u.source.start, u.source.end) == (0.5, 2.5)
    assert abs(audio.duration(clip) - (before + 1.0)) < 0.01          # a second longer
    assert not list(clip.parent.glob("*.lemmatrix-new.wav"))


def test_check_clipped_utterances_and_unlink(win, tmp_path, monkeypatch):
    from lemmatrix.ui import pull_dialog
    uw, t, u, grid = _clipped(win, tmp_path, monkeypatch)
    dlg = pull_dialog.CheckDialog(win)
    assert dlg.tree.topLevelItemCount() == 0 and "All 1 clipped" in dlg.note.text()
    _resave(grid, {"tx": [(2.0, 3.0, "ɛ ŋəə")], "ft": [(2.0, 3.0, "where is he?")]})   # the line is gone
    dlg.fill()
    assert dlg.tree.topLevelItemCount() == 1 and dlg.tree.topLevelItem(0).text(3) == "line not found"
    assert not dlg.pull_btn.isEnabled()
    dlg.tree.topLevelItem(0).setSelected(True)
    assert dlg.unlink_btn.isEnabled()
    dlg.unlink()
    assert u.source is None and dlg.tree.topLevelItemCount() == 0
    win.doc.undo.undo()
    assert u.source is not None
    dlg.close()


def test_the_utterance_dialogue_offers_pull(win, tmp_path, monkeypatch):
    from lemmatrix.ui import pull_dialog
    from lemmatrix.ui.token_dialog import Slot
    from lemmatrix.ui.utterances import UtteranceDialog
    uw, t, u, grid = _clipped(win, tmp_path, monkeypatch)
    dlg = UtteranceDialog(win, [Slot(u, 0)], 0, uw)
    assert dlg.pull_btn.isHidden()
    _resave(grid, {"tx": [(0.5, 1.5, "ʔəŋ"), (2.0, 3.0, "ɛ ŋəə")],
                   "ft": [(0.5, 1.5, "the hare ran"), (2.0, 3.0, "where is he?")]})
    dlg._show_source()
    assert not dlg.pull_btn.isHidden() and "Changed in the TextGrid" in dlg.source_label.text()
    monkeypatch.setattr(pull_dialog.PullDialog, "exec", lambda d: 1)
    dlg._pull()
    assert u.token.get("Phonetic") == "ʔəŋ" and dlg.pull_btn.isHidden()
    dlg.close()


# ---- Praat's names (18 October) -------------------------------------------------------------

def test_text_files_are_named_as_praat_names_them(tmp_path):
    from lemmatrix.filenames import praat_name
    assert praat_name("LXX-VXX_T001_Hyena and Hare (ʔəŋ), v.2") == "LXX-VXX_T001_Hyena_and_Hare__ʔəŋ___v_2"
    assert praat_name("a+b=c-d_é–ŋ") == "a+b=c-d_é–ŋ"
    db = _db(tmp_path)
    t = Text(ref="T001", file_label="Hyena and Hare")
    assert db.expected_text_name(t, ".TextGrid") == "LXX-VXX_T001_Hyena_and_Hare.TextGrid"


def test_praat_names_match_praat_itself(tmp_path):
    parselmouth = pytest.importorskip("parselmouth")          # Praat, embedded (only where installed)
    from lemmatrix.filenames import praat_name
    stem = "LXX-VXX_T001_Hyena and Hare (ʔəŋ), v.2 [x] it's & {y}; 50% ~ @#!^`"
    path = tmp_path / f"{stem}.TextGrid"
    tgmod.write_example(path, {"tx": [(0.5, 1.5, "a")]}, 4.0)
    script = 'Read from file: "' + str(path).replace('"', '""') + '"\nappendInfoLine: selected$()\n'
    out = parselmouth.praat.run(script, capture_output=True)[1].strip()
    assert out == "TextGrid " + praat_name(stem)


def test_old_text_names_are_renamed_on_opening_and_praats_copy_is_kept(win, tmp_path, monkeypatch):
    import time
    from lemmatrix.ui import main_window
    db = win.doc.db
    folder = tmp_path / "Soundfiles" / "Texts"
    folder.mkdir(parents=True, exist_ok=True)
    _recording(folder / "LXX-VXX_T001_Hyena and Hare.wav")
    _grid(folder / "LXX-VXX_T001_Hyena and Hare.TextGrid")
    t = Text(ref="T001", file_label="Hyena and Hare", file="LXX-VXX_T001_Hyena and Hare.wav",
             textgrid="LXX-VXX_T001_Hyena and Hare.TextGrid")
    t2 = Text(ref="T002", file_label="Two words", textgrid="LXX-VXX_T002_Two words.TextGrid")
    _grid(folder / "LXX-VXX_T002_Two words.TextGrid")
    praats = folder / "LXX-VXX_T002_Two_words.TextGrid"        # saved by Praat, later
    tgmod.write_example(praats, {"tx": [(0.5, 1.5, "edited")]}, 4.0)
    os.utime(praats, (time.time() + 60, time.time() + 60))
    db.texts += [t, t2]
    shown = []
    monkeypatch.setattr(main_window.QMessageBox, "information", lambda *a, **k: shown.append(a[2]))
    win._praat_text_names(db)
    assert t.file == "LXX-VXX_T001_Hyena_and_Hare.wav" and (folder / t.file).exists()
    assert t.textgrid == "LXX-VXX_T001_Hyena_and_Hare.TextGrid" and not (folder / "LXX-VXX_T001_Hyena and Hare.wav").exists()
    assert t2.textgrid == praats.name and tgmod.read_lines(praats, db.mapping_for(t2))[0].values["Phonetic"] == "edited"
    assert not (folder / "LXX-VXX_T002_Two words.TextGrid").exists()            # held for now
    assert "Praat had saved" in shown[0] and win.doc.dirty
    assert win.doc.revert_renames() == []                                        # not saved: all back
    assert (folder / "LXX-VXX_T001_Hyena and Hare.wav").exists() and (folder / "LXX-VXX_T002_Two words.TextGrid").exists()


def test_an_edit_saved_in_praat_is_seen(win, tmp_path, monkeypatch):
    """The whole round: clip a line, edit the TextGrid in Praat and save it under the name Praat
    suggests (its object's name), back in Lemmatrix the utterance is flagged and can be pulled."""
    parselmouth = pytest.importorskip("parselmouth")
    from lemmatrix.ui import pull_dialog
    uw, t, u, grid = _clipped(win, tmp_path, monkeypatch)
    time.sleep(1.1)                                       # Praat saves a second later at least
    script = (f'grid = Read from file: "{grid}"\n'
              'Set interval text: 1, 2, "ʔəŋ kɒ ɗæær"\n'
              f'Save as text file: "{grid.parent}/" + selected$("TextGrid") + ".TextGrid"\n')
    parselmouth.praat.run(script)
    assert sorted(f.name for f in grid.parent.iterdir()) == sorted([t.file, t.textgrid])   # no second TextGrid
    assert uw.recheck() and uw._flagged(u)
    monkeypatch.setattr(pull_dialog.PullDialog, "exec", lambda d: 1)
    uw.table.select_row(u)
    uw.pull_selected()
    assert u.token.get("Phonetic") == "ʔəŋ kɒ ɗæær"


# ---- Push (agreed 18 October) ----------------------------------------------------------------

def test_push_from_the_window(win, tmp_path, monkeypatch):
    from lemmatrix.ui import pull_dialog
    uw, t, u, grid = _clipped(win, tmp_path, monkeypatch)
    u.token.set("Phonetic", "ʔə̀ŋ kɒ̄")
    u.token.set("Morphemes", "hare.run")                     # the ge tier has two segments here
    uw.refresh()
    assert not uw._flagged(u) and uw._source_display(u).endswith("– edited here")
    seen = {}

    def fake_exec(dlg):
        seen["rows"] = [[dlg.items[i].text(c) for c in (0, 1, 3, 4, 2)] for i in range(len(dlg.items))]
        seen["merge shown"] = not dlg.merge_note.isHidden()
        dlg.items[[ch.tier for ch in dlg.plan].index("ge")].setCheckState(1, Qt.Unchecked)   # not ge
        seen["merge after unticking"] = not dlg.merge_note.isHidden()
        return 1
    from PySide6.QtCore import Qt
    monkeypatch.setattr(pull_dialog.PushDialog, "exec", fake_exec)
    uw.table.select_row(u)
    uw.push_selected()
    assert ["W001", "Phonetic → tx", "ʔəŋ kɒ", "ʔə̀ŋ kɒ̄", ""] in seen["rows"]
    assert ["", "Morphemes → ge", "hare run.PST", "hare.run", "merges 2 segments"] in seen["rows"]
    assert seen["merge shown"] and not seen["merge after unticking"]
    assert tgmod.read_lines(grid, win.doc.db.mapping_for(t))[0].values["Phonetic"] == "ʔə̀ŋ kɒ̄"
    assert uw.checks[u.id].edited == ["ge"]                   # Morphemes still waits
    assert any(f.suffix == ".TextGrid" for f in (tmp_path / "Backups").iterdir())


def test_the_utterance_dialogue_offers_push(win, tmp_path, monkeypatch):
    from lemmatrix.ui import pull_dialog
    from lemmatrix.ui.token_dialog import Slot
    from lemmatrix.ui.utterances import UtteranceDialog
    uw, t, u, grid = _clipped(win, tmp_path, monkeypatch)
    dlg = UtteranceDialog(win, [Slot(u, 0)], 0, uw)
    assert dlg.source_push_btn.isHidden()
    dlg.edits["Phonetic"].setText("ʔə̀ŋ kɒ̄")                  # typed, not yet saved
    monkeypatch.setattr(pull_dialog.PushDialog, "exec", lambda d: 1)
    dlg._push()                                               # saves it first, then pushes
    assert u.token.get("Phonetic") == "ʔə̀ŋ kɒ̄"
    assert tgmod.read_lines(grid, win.doc.db.mapping_for(t))[0].values["Phonetic"] == "ʔə̀ŋ kɒ̄"
    assert dlg.source_push_btn.isHidden()
    dlg.comment.setText("a question")                     # Push to question is its own button again
    assert dlg.push_btn.isEnabled() and dlg.push_btn is not dlg.source_push_btn
    dlg.close()


def test_the_window_opens_on_texts(win, tmp_path, monkeypatch):
    from lemmatrix.ui.utterances import TEXTS, UTTERANCES_TAB
    action = next(a for m in win.menuBar().actions() if m.menu()
                  for a in m.menu().actions() if a.text() == "&Texts and utterances")
    action.trigger()                                          # as View → Texts and utterances / Ctrl+U
    uw = win.utterances_window
    assert uw.isVisible() and uw.tabs.currentIndex() == TEXTS
    uw.tabs.setCurrentIndex(UTTERANCES_TAB)
    uw.hide()                                                 # hidden, not closed: the same window
    action.trigger()
    assert win.utterances_window is uw and uw.tabs.currentIndex() == TEXTS
    uw.close()
    action.trigger()
    assert win.utterances_window.tabs.currentIndex() == TEXTS   # closed: a new window, on Texts
    win.utterances_window.close()
    uw = win.open_utterances()
    assert uw.tabs.currentIndex() == TEXTS
    uw.tabs.setCurrentIndex(UTTERANCES_TAB)
    uw.close()
    assert win.open_utterances().tabs.currentIndex() == TEXTS


# ---- editing lines in Lemmatrix (19 October) -----------------------------------------------

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402

def test_edit_a_line_in_place_saves_into_the_textgrid(win, tmp_path, monkeypatch):
    uw, t = _add_text(win, tmp_path, monkeypatch)
    p = uw.texts
    grid = tmp_path / "Soundfiles" / "Texts" / t.textgrid
    p.set_edit_mode(True)
    assert p.lines.edit_mode and not p.edit_label.isHidden()
    ln = p.lines.rows[1]
    p.lines.start_edit(ln, "Translation:en")
    ed = p.lines._editor[0]
    ed.setText("where did he go?")
    QTest.keyClick(ed, Qt.Key_Tab)                           # kept, and on to the next field
    assert p.lines.rows[1].values["Translation:en"] == "where did he go?"
    assert p.lines._editor is not None and p.lines._editor[2] != "Translation:en"
    p.lines._close_editor(commit=False)
    assert tgmod.read_lines(grid, win.doc.db.mapping_for(t))[1].values["Translation:en"] == "where is he?"   # not yet
    assert win.doc.dirty and "not yet saved" in p.lines_title.text()
    win.doc.undo.undo()
    assert p.lines.rows[1].values["Translation:en"] == "where is he?"
    win.doc.undo.redo()
    assert win.save()
    assert tgmod.read_lines(grid, win.doc.db.mapping_for(t))[1].values["Translation:en"] == "where did he go?"
    assert any(f.suffix == ".TextGrid" for f in (tmp_path / "Backups").iterdir())


def test_a_word_tier_edit_that_merges_asks_first(win, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    uw, t = _add_text(win, tmp_path, monkeypatch)
    p = uw.texts
    asked = []
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: (asked.append(a[2]), QMessageBox.No)[1])
    p.set_line_field(p.lines.rows[0], "Morphemes", "hare run PST")       # 3 units, 2 segments
    assert "merge several segments in Praat" in asked[0]
    assert p.lines.rows[0].values["Morphemes"] == "hare run.PST"       # declined: nothing changed
    p.set_line_field(p.lines.rows[0], "Morphemes", "{} run.PFV")        # 2 units: segments kept
    assert len(asked) == 1 and p.lines.rows[0].values["Morphemes"] == "{} run.PFV"


def test_editing_a_line_updates_its_clipped_utterance(win, tmp_path, monkeypatch):
    uw, t, u, grid = _clipped(win, tmp_path, monkeypatch)
    p = uw.texts
    p.set_line_field(p.lines.rows[0], "Phonetic", "ʔə̀ŋ kɒ̄")
    assert u.token.get("Phonetic") == "ʔə̀ŋ kɒ̄"
    uw.refresh()
    assert not uw._flagged(u) and not uw.checks[u.id].edited       # the same analysis, no flag
    win.doc.undo.undo()
    assert u.token.get("Phonetic") == "ʔəŋ kɒ"
    win.doc.undo.redo()
    assert win.save()
    uw.refresh()
    assert not uw._flagged(u) and not uw.checks[u.id].edited       # and after saving too


def test_a_line_comment_goes_into_the_notebook(win, tmp_path, monkeypatch):
    uw, t = _add_text(win, tmp_path, monkeypatch)
    p = uw.texts
    assert p.comment_key() == "Comment"
    p.set_line_field(p.lines.rows[0], "Comment", "existential clause")
    s = win.doc.notebook.session(win.work_date())
    assert [(c.text, c.is_line, c.ref) for c in s.comments] == [("existential clause", True, "T001")]
    p.set_line_field(p.lines.rows[0], "Comment", "existential clause, discourse opener")   # same day: written over
    assert [c.text for c in s.comments] == ["existential clause, discourse opener"]
    win.doc.undo.undo()
    assert [c.text for c in s.comments] == ["existential clause"]
    from lemmatrix import notebook as nbmod
    assert not nbmod.refresh_comments(win.doc.db, s)                # kept by the usual refresh


def test_comments_already_in_a_textgrid_go_into_the_notebook_on_adding(win, tmp_path, monkeypatch):
    from lemmatrix.model import TierRule
    win.doc.db.settings.tier_mapping.rules.append(TierRule("note", "Comment"))
    src = tmp_path / "field"
    src.mkdir()
    tgmod.write_example(src / "story.TextGrid", {"tx": [(0.5, 1.5, "ʔəŋ kɒ"), (2.0, 3.0, "ɛ ŋəə")],
                                                 "note": [(0.5, 1.5, "laughs")]}, 4.0)
    uw, t = _add_text(win, tmp_path, monkeypatch, src=src)
    s = win.doc.notebook.session(t.date)
    assert [c.text for c in s.comments] == ["laughs"] and s.comments[0].about.startswith("T001")


def test_next_empty_and_search(win, tmp_path, monkeypatch):
    uw, t = _add_text(win, tmp_path, monkeypatch)
    p = uw.texts
    p.lines.select_row(p.lines.rows[0])
    p.next_field.setCurrentIndex(p.next_field.findData("Comment"))
    p.next_empty()
    assert p.lines.current_row() is p.lines.rows[1]
    p.line_search.setText("hare")
    assert len(p.lines.visible_rows()) == 1 and p.count.text().startswith("1 of 2")


def test_configure_view(win, tmp_path, monkeypatch):
    from lemmatrix.ui import lines_view
    uw, t = _add_text(win, tmp_path, monkeypatch)
    p = uw.texts

    def fake_exec(dlg):
        for i in range(dlg.tree.topLevelItemCount()):
            it = dlg.tree.topLevelItem(i)
            it.setCheckState(0, Qt.Checked if it.data(0, Qt.UserRole) in ("Morphemes", "Phonetic") else Qt.Unchecked)
            it.setCheckState(1, Qt.Unchecked)
        return 1
    monkeypatch.setattr(lines_view.ConfigureViewDialog, "exec", fake_exec)
    p.configure_view()
    assert [f.key for f in p.lines.fields] == ["Phonetic", "Morphemes"] and not any(f.aligned for f in p.lines.fields)
    win.prefs.set_list("lines/fields", [])
    win.prefs.set_list("lines/aligned", [])


def test_hidden_symbols():
    from lemmatrix.ui.lines_view import shown
    assert shown("a {big dog} {} ran") == "a big dog ran" and shown("plain") == "plain"


def test_keys_in_the_lines_view(win, tmp_path, monkeypatch):
    uw, t = _add_text(win, tmp_path, monkeypatch)
    v = uw.texts.lines
    played = []
    monkeypatch.setattr(uw.texts, "play_line", lambda *a, **k: played.append(1))
    v.playRequested.disconnect()
    v.playRequested.connect(uw.texts.play_line)
    v.select_row(v.rows[0])
    QTest.keyClick(v, Qt.Key_Down)
    assert v.current_row() is v.rows[1]
    QTest.keyClick(v, Qt.Key_Space)
    assert played == [1]
    uw.texts.set_edit_mode(True)
    steps = win.doc.undo.count()
    v.start_edit(v.rows[0], "Phonetic")
    ed = v._editor[0]
    QTest.keyClick(ed, Qt.Key_Space, Qt.ControlModifier)         # plays, never types a space
    assert played == [1, 1] and " " not in ed.text()[-1:]
    QTest.keyClick(ed, Qt.Key_Down)                               # the same field, one line down
    assert v._editor[1] == v.rows[1].id and v._editor[2] == "Phonetic"
    QTest.keyClick(v._editor[0], Qt.Key_Escape)
    assert v._editor is None and win.doc.undo.count() == steps       # nothing typed: nothing recorded


def test_a_segment_filled_in_praat_shows_up_with_no_utterances_in_the_database(win, tmp_path, monkeypatch):
    """Josh, 21 October: a segment empty when the text was added, filled in Praat later, never
    showed up: back from Praat, the lines were only read again if the database had utterances."""
    import time
    from PySide6.QtCore import QEvent
    from lemmatrix.ui.utterances import TextsUtterancesWindow
    src = tmp_path / "field"
    src.mkdir()

    def grid(path, filled):
        tgmod.write_example(path, {
            "tx": [(0.5, 1.5, "ʔəŋ kɒ"), (2.0, 3.0, "ɛ ŋəə" if filled else "")],
            "ft": [(0.5, 1.5, "the hare ran" if filled else ""), (2.0, 3.0, "where is he?" if filled else "")],
        }, 4.0)
    grid(src / "story.TextGrid", False)
    uw, t = _add_text(win, tmp_path, monkeypatch, src=src)
    assert not win.doc.db.utterances
    p = uw.texts
    assert len(p.lines.rows) == 1 and "Translation:en" not in p.lines.rows[0].values
    time.sleep(0.02)
    grid(p.grid_path(t), True)                       # saved in Praat
    monkeypatch.setattr(TextsUtterancesWindow, "isActiveWindow", lambda self: True)
    uw.changeEvent(QEvent(QEvent.ActivationChange))  # back from Praat
    assert len(p.lines.rows) == 2
    assert p.lines.rows[0].values["Translation:en"] == "the hare ran"
    assert p.lines.rows[1].values["Phonetic"] == "ɛ ŋəə"


def test_refresh_text_reads_the_textgrid_again_and_asks_about_unsaved_edits(win, tmp_path, monkeypatch):
    """Josh, 21 October: Refresh text reads the TextGrid again whatever its date, finding every
    line again; line edits not yet saved are saved first or dropped, after asking."""
    import os
    from PySide6.QtWidgets import QMessageBox
    src = tmp_path / "field"
    src.mkdir()

    def grid(path, second):
        tgmod.write_example(path, {"tx": [(0.5, 1.5, "ʔəŋ kɒ"), (2.0, 3.0, second)],
                                   "ft": [(0.5, 1.5, "the hare ran"), (2.0, 3.0, "")]}, 4.0)
    grid(src / "story.TextGrid", "")
    uw, t = _add_text(win, tmp_path, monkeypatch, src=src)
    p = uw.texts
    assert len(p.lines.rows) == 1
    path = p.grid_path(t)
    st = os.stat(path)
    grid(path, "ɛ ŋəə")                                  # saved in Praat, but the date looks unchanged
    os.utime(path, ns=(st.st_atime_ns, st.st_mtime_ns))
    p.lines_changed()
    assert len(p.lines.rows) == 1                        # the date check alone doesn't see it
    p.refresh_text()
    assert len(p.lines.rows) == 2 and p.lines.rows[1].values["Phonetic"] == "ɛ ŋəə"

    # an edit made here and not saved: Refresh asks first
    p.set_line_field(p.lines.rows[0], "Translation:en", "the hare ran away")
    asked = []

    def fake_exec(box):
        asked.append([b.text() for b in box.buttons()])
        box._hit = next(b for b in box.buttons() if b.text() == pick)
        return 0
    monkeypatch.setattr(QMessageBox, "exec", fake_exec)
    monkeypatch.setattr(QMessageBox, "clickedButton", lambda box: box._hit)
    pick = "Cancel"
    p.refresh_text()
    assert asked and "Save and refresh" in asked[-1] and "Refresh without saving" in asked[-1]
    assert p.lines.rows[0].values["Translation:en"] == "the hare ran away"     # Cancel: nothing changes
    pick = "Refresh without saving"
    p.refresh_text()
    assert p.lines.rows[0].values["Translation:en"] == "the hare ran"          # dropped, as in the file
    assert not win.doc.text_buffers[t.id].changed
    win.doc.undo.undo()                                  # undoing the dropped edit leaves the file's text
    assert p.lines.rows[0].values["Translation:en"] == "the hare ran"
    p.set_line_field(p.lines.rows[0], "Translation:en", "the hare fled")
    saved = []
    monkeypatch.setattr(win, "save", lambda: saved.append(1) or True)
    pick = "Save and refresh"
    p.refresh_text()
    assert saved == []                                   # the TextGrid only, not the database (audit, 25 October)
    assert tgmod.read_lines(path, win.doc.db.mapping_for(t))[0].values["Translation:en"] == "the hare fled"
    assert p.lines.rows[0].values["Translation:en"] == "the hare fled"
