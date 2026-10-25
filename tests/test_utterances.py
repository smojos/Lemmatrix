# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders. Additional terms: NOTICE.md
"""Utterances (idea 7, stage 2): the data model, the file, file names and the notebook."""

from pathlib import Path

from lemmatrix import layout, notebook as nbmod, storage
from lemmatrix.defaults import new_database
from lemmatrix.model import UTTERANCES, Group, Tag, is_utterance

DATA = Path(__file__).resolve().parent / "data"
SAMPLES = Path(__file__).resolve().parent / "data" / "sample"    # the prototype's sample (conftest.py)


def _db(tmp_path):
    db = new_database()
    db.path = str(tmp_path / "Lex.xml")
    db.metadata.language_code, db.metadata.variety_code = "LXX", "VXX"
    e = db.new_entry("D009", "ɗæær", "goat", "NOUN")
    db.entries.append(e)
    return db, e


def test_new_databases_have_utterance_categories():
    s = new_database().settings
    assert [c.letter for c in s.categories(UTTERANCES)] == ["U", "W", "X", "Y", "Z"]
    assert s.category("U012").name == "Unorganised"
    assert all(c.letter not in "UWXYZ" for c in s.categories())          # lemma categories


def test_utterance_references_go_past_999(tmp_path):
    db, _ = _db(tmp_path)
    assert db.suggest_utterance_reference("W") == "W001"
    db.utterances.append(db.new_utterance("W999"))
    assert db.suggest_utterance_reference("W") == "W1000"
    db.utterances.append(db.new_utterance("W1000"))
    assert db.suggest_utterance_reference("W") == "W1001"
    assert db.suggest_utterance_reference("U") == "U001"


def test_utterance_file_names_have_no_tags(tmp_path):
    db, _ = _db(tmp_path)
    u = db.new_utterance("W001", "hare ran", speaker="SP1")
    u.token.tags = ["before H"]
    assert db.expected_filename(u, u.token) == "LXX-VXX_W001_hare_ran.wav"
    assert storage.folder_for(db, u) == tmp_path / "Soundfiles" / "Utterances"
    assert not db.new_utterance("U001").token.tags          # no defaults: no word class


def test_utterances_are_saved_and_read(tmp_path):
    db, goat = _db(tmp_path)
    u = db.new_utterance("W001", "hare ran", speaker="SP1", date="2026-10-18")
    u.token.set("Phonetic", "ʔəŋ kɒ")
    u.token.set("Morphemes", "hare run.PST")
    u.token.set("Translation", "the hare ran", "en")
    u.token.tags = ["before H"]
    u.lemmas = [goat.id]
    db.utterances.append(u)
    db.settings.tags.groups.append(Group("Clause type", [Tag("Relative clause", "REL")],
                                         utterances_only=True))
    storage.save(db, backup=False)
    text = Path(db.path).read_text(encoding="utf-8")
    assert f'<database format="{storage.FORMAT_VERSION}">' in text and "<utterances>" in text
    assert 'file-label="hare ran"' in text and f'lemmas="{goat.id}"' in text
    assert 'for="utterances"' in text and 'utterances-only="yes"' in text
    again = storage.load(db.path)
    v = again.utterances[0]
    assert is_utterance(v) and v.ref == "W001" and v.label == "hare ran"
    assert v.token.get("Morphemes") == "hare run.PST" and v.token.tags == ["before H"]
    assert again.linked_lemmas(v)[0].ref == "D009"
    assert v.id == u.id and v.token.id == u.token.id
    ts = again.settings.tags
    assert ts.utterance_only_tags() == {"Relative clause"}
    assert all(g.name != "Clause type" for _, g in ts.usual_groups(["NOUN"]))     # not for lemmas
    assert not again.load_notes


def test_notebook_counts_utterance_comments_and_recordings(tmp_path):
    db, _ = _db(tmp_path)
    u = db.new_utterance("U001", "greeting", speaker="SP1", date="2026-10-18")
    u.token.file = "LXX-VXX_U001_greeting.wav"
    u.token.set("Comment", "said twice")
    db.utterances.append(u)
    db.stamp_comments(None, u, "2026-10-18")
    comments = nbmod.dated_comments(db, "2026-10-18")
    assert [c.about for c in comments] == ["U001 greeting (utterance)"]
    assert nbmod.find(db, comments[0]) == (u, 0)
    assert nbmod.recordings(db, "2026-10-18") == [(u, 0)]
    assert nbmod.speakers(db, "2026-10-18") == ["SP1"]


def test_new_layout_has_an_utterances_folder(tmp_path):
    layout.create_layout(tmp_path / "Lex.xml")
    assert (tmp_path / "Soundfiles" / "Utterances").is_dir()


# ---- the window and the dialogue ---------------------------------------------------------

import os


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["LEMMATRIX_SETTINGS"] = "Lemmatrix-tests"


def _wav(path: Path):
    from lemmatrix import audio
    import numpy as np
    audio.write_wav(path, np.zeros(800, dtype=np.float32), 8000, 16)
    return path


def test_import_wavs_as_utterances_and_undo(win, tmp_path):
    src = tmp_path / "outside"
    src.mkdir()
    a, b = _wav(src / "hare_ran.wav"), _wav(src / "greeting.wav")
    uw = win.open_utterances()
    items = uw.import_files([str(a), str(b), str(src / "notes.txt")])
    db = win.doc.db
    assert [u.ref for u in items] == ["W001", "W002"]
    assert [u.label for u in items] == ["hare ran", "greeting"]
    folder = tmp_path / "Soundfiles" / "Utterances"
    assert (folder / "LXX-VXX_W001_hare_ran.wav").exists() and a.exists()      # copied, original kept
    assert items[0].token.file == "LXX-VXX_W001_hare_ran.wav"
    assert uw.table.model_.rowCount() == 2
    win.doc.undo.undo()                                     # one step for the whole import
    assert db.utterances == [] and not (folder / "LXX-VXX_W001_hare_ran.wav").exists()
    win.doc.undo.redo()
    assert len(db.utterances) == 2 and (folder / "LXX-VXX_W001_hare_ran.wav").exists()
    win.save()
    again = storage.load(db.path)
    assert [u.ref for u in again.utterances] == ["W001", "W002"]


def test_drop_wavs_on_the_grid(win, tmp_path):
    from PySide6.QtCore import QMimeData, QPointF, QUrl, Qt
    from PySide6.QtGui import QDropEvent
    uw = win.open_utterances()
    wav = _wav(tmp_path / "clip.wav")
    md = QMimeData()
    md.setUrls([QUrl.fromLocalFile(str(wav))])
    ev = QDropEvent(QPointF(10, 10), Qt.CopyAction, md, Qt.LeftButton, Qt.NoModifier)
    uw.table.dropEvent(ev)
    assert [u.label for u in win.doc.db.utterances] == ["clip"]


def test_utterance_dialogue_label_lemmas_and_tags(win, tmp_path):
    from lemmatrix.model import Group, Tag
    from lemmatrix.ui.utterances import UtteranceDialog
    from lemmatrix.ui.token_dialog import Slot
    db = win.doc.db
    db.settings.tags.groups.insert(0, Group("Clause type", [Tag("Relative clause", "REL")],
                                            utterances_only=True))
    uw = win.open_utterances()
    uw.import_files([str(_wav(tmp_path / "x.wav"))])
    u = db.utterances[0]
    dlg = UtteranceDialog(win, [Slot(u, 0)], 0, uw)
    assert "W001" in dlg.header.text() and dlg.label_edit.text() == "x"
    assert "Relative clause" in dlg.tags.buttons            # utterance-only groups are offered
    assert not dlg.tags.buttons["Relative clause"].unusual
    dlg.label_edit.setText("hare ran")
    dlg.edits["Phonetic"].setText("ʔəŋ kɒ")
    dlg.tags.buttons["Relative clause"].setChecked(True)
    goat = db.entry_by_ref("D001")
    choice = next(t for t in dlg._choices if t.startswith("D001"))
    dlg._lemma_chosen(choice)
    dlg._ok()
    assert u.label == "hare ran" and u.token.get("Phonetic") == "ʔəŋ kɒ"
    assert u.token.tags == ["Relative clause"] and u.lemmas == [goat.id]
    assert u.token.file == "LXX-VXX_W001_hare_ran.wav"          # renamed with the label
    folder = tmp_path / "Soundfiles" / "Utterances"
    assert (folder / u.token.file).exists() and not (folder / "LXX-VXX_W001_x.wav").exists()
    win.doc.undo.undo()
    assert u.label == "x" and (folder / "LXX-VXX_W001_x.wav").exists()


def test_lemma_tokens_are_not_offered_utterance_only_tags(win):
    from lemmatrix.model import Group, Tag
    from lemmatrix.ui.token_dialog import Slot, TokenDialog
    db = win.doc.db
    db.settings.tags.groups.insert(0, Group("Clause type", [Tag("Relative clause", "REL")],
                                            utterances_only=True))
    goat = db.entry_by_ref("D001")
    dlg = TokenDialog(win, [Slot(goat, 0)], 0)
    assert "Relative clause" not in dlg.tags.buttons
    dlg.show_all_btn.setChecked(True)                       # not even under Show all tags
    assert "Relative clause" not in dlg.tags.buttons
    assert db.unusual_tags(goat, ["Relative clause"]) == ["Relative clause"]


def test_add_a_new_utterance_only_when_saved(win):
    from lemmatrix.ui.utterances import UtteranceDialog
    from lemmatrix.ui.token_dialog import Slot
    db = win.doc.db
    uw = win.open_utterances()
    u = db.new_utterance("W001")
    dlg = UtteranceDialog(win, [Slot(u, None, explicit=True)], 0, uw)
    dlg.reject()
    assert db.utterances == []
    dlg = UtteranceDialog(win, [Slot(u, None, explicit=True)], 0, uw)
    dlg.edits["Phonetic"].setText("ʔəŋ")
    dlg._ok()
    assert db.utterances == [u] and u.token.get("Phonetic") == "ʔəŋ"


def test_move_to_another_category_renames(win, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QInputDialog
    db = win.doc.db
    uw = win.open_utterances()
    uw.import_files([str(_wav(tmp_path / "hello.wav"))])
    u = db.utterances[0]
    monkeypatch.setattr(QInputDialog, "getItem", lambda parent, title, label, items, *a, **k:
                        (next(i for i in items if i.startswith("U")), True))
    uw.move_category(u)
    assert u.ref == "U001" and u.token.file == "LXX-VXX_U001_hello.wav"
    assert (tmp_path / "Soundfiles" / "Utterances" / u.token.file).exists()


def test_delete_an_utterance_holds_its_recording(win, tmp_path):
    db = win.doc.db
    uw = win.open_utterances()
    uw.import_files([str(_wav(tmp_path / "bye.wav"))])
    u = db.utterances[0]
    path = tmp_path / "Soundfiles" / "Utterances" / u.token.file
    uw.table.select_row(u)
    uw.delete()
    assert db.utterances == [] and not path.exists()
    win.doc.undo.undo()
    assert db.utterances == [u] and path.exists()


def test_reference_categories_page(win):
    from lemmatrix.ui.lists_dialog import ListsDialog, REFS
    dlg = ListsDialog(win, win.doc.db, win.doc.notebook, REFS)
    ed = dlg.categories
    cats = ed.categories()
    w = next(i for i, c in enumerate(cats) if c.letter == "W")
    ed.table.item(w, 1).setText("Clause types")
    assert ed.problem() == ""
    dlg.apply()
    assert win.doc.db.settings.category("W001").name == "Clause types"
    d_row = next(i for i, c in enumerate(cats) if c.letter == "D")
    from PySide6.QtCore import Qt
    assert not (ed.table.item(d_row, 0).flags() & Qt.ItemIsEditable)   # D is used: its letter stays
    ed.table.item(w, 0).setText("D")
    assert "Two categories" in ed.problem()


def test_notebook_link_opens_the_utterance(win, tmp_path):
    uw = win.open_utterances()
    uw.import_files([str(_wav(tmp_path / "hi.wav"))])
    u = win.doc.db.utterances[0]
    uw.table.clearSelection()
    assert win.go_to(u)
    assert uw.table.current_row() is u


def test_update_all_names_renames_utterances_too(win, tmp_path):
    db = win.doc.db
    uw = win.open_utterances()
    uw.import_files([str(_wav(tmp_path / "rain.wav"))])
    u = db.utterances[0]
    db.settings.utterance_pattern = "{reference}_{label}"
    win.update_all_names(ask=False)
    assert u.token.file == "W001_rain.wav"
    assert (tmp_path / "Soundfiles" / "Utterances" / "W001_rain.wav").exists()


def test_anonymous_backup_takes_utterance_recordings(win, tmp_path):
    from lemmatrix import anonymise
    uw = win.open_utterances()
    uw.import_files([str(_wav(tmp_path / "song.wav"))])
    win.save()
    db = win.doc.db
    song = db.utterances[0].token
    rep = anonymise.export(db, win.doc.notebook, tmp_path / "none", anonymise.Options(recordings=True))
    assert not (tmp_path / "none" / "Soundfiles" / "Utterances").exists()   # nobody agreed to audio sharing
    assert rep.withheld_recordings >= 1
    for p in db.metadata.participants:               # the Ethical archive: only agreed audio sharing
        p.audio_sharing = True
    song.speaker = db.metadata.participants[0].code
    rep = anonymise.export(db, win.doc.notebook, tmp_path / "anon", anonymise.Options(recordings=True))
    assert (tmp_path / "anon" / "Soundfiles" / "Utterances" / "LXX-VXX_W001_song.wav").exists()
    assert rep.recordings > 1


def test_ctrl_shift_space_plays_an_utterances_pitch(win, tmp_path, monkeypatch):
    from PySide6.QtGui import QKeySequence, QShortcut
    uw = win.open_utterances()
    uw.import_files([str(_wav(tmp_path / "tune.wav"))])
    u = win.doc.db.utterances[0]
    win.doc.edit_entry(u, lambda x: x.token.set("Pitch", "11 4:42"))
    uw.tabs.setCurrentIndex(1)                     # on the Texts tab it plays the lines' scratchpad
    uw.table.select_row(u)
    played = []
    monkeypatch.setattr(win, "play_pitch", lambda text: played.append(text))
    keys = {sc.key().toString(): sc for sc in uw.findChildren(QShortcut)}
    keys[QKeySequence("Ctrl+Shift+Space").toString()].activated.emit()
    assert played == ["11 4:42"]


def test_ctrl_space_in_any_utterance_field_plays(win, tmp_path, monkeypatch):
    from PySide6.QtCore import QEvent, Qt
    from PySide6.QtGui import QKeyEvent
    from PySide6.QtWidgets import QApplication
    from lemmatrix.ui.token_dialog import Slot
    from lemmatrix.ui.utterances import UtteranceDialog
    uw = win.open_utterances()
    uw.import_files([str(_wav(tmp_path / "beat.wav"))])
    dlg = UtteranceDialog(win, [Slot(win.doc.db.utterances[0], 0)], 0, uw)
    played = []
    monkeypatch.setattr(dlg, "_play", lambda: played.append("sound"))
    monkeypatch.setattr(dlg, "_play_pitch", lambda: played.append("pitch"))
    fields = [dlg.label_edit, dlg.lemma_find, dlg.date, *dlg.edits.values()]
    for ed in fields:
        before = ed.text()
        QApplication.sendEvent(ed, QKeyEvent(QEvent.KeyPress, Qt.Key_Space, Qt.ControlModifier, " "))
        assert ed.text() == before, ed
    QApplication.sendEvent(dlg.label_edit, QKeyEvent(QEvent.KeyPress, Qt.Key_Space,
                                                     Qt.ControlModifier | Qt.ShiftModifier, " "))
    assert played == ["sound"] * len(fields) + ["pitch"]
    dlg.reject()


def test_recording_dates_are_filled_in_for_utterances(win, tmp_path):
    from lemmatrix import audio, recdates
    import numpy as np
    uw = win.open_utterances()
    clip = tmp_path / "dated.wav"
    audio.write_wav(clip, np.zeros(800, dtype=np.float32), 8000, 16, date="2026-09-30")
    win.sess_nodate.setChecked(True)                 # imported with no date
    u = uw.import_files([str(clip)])[0]
    assert u.token.collected == ""
    changes, _ = recdates.plan(win.doc.db)
    assert any(c.entry is u and c.new == "2026-09-30" for c in changes)
    recdates.apply(win.doc, changes)
    assert u.token.collected == "2026-09-30"


def test_tag_editor_counts_utterance_tokens(win, tmp_path):
    from lemmatrix.ui.dialogs import TagStructureDialog
    db = win.doc.db
    u = db.new_utterance("U001", "x")
    u.token.tags = ["before H"]
    db.utterances.append(u)
    dlg = TagStructureDialog(win, db)
    before = sum(1 for e in db.entries for t in e.tokens if "before H" in t.tags)
    assert dlg._used({"before H"}) == before + 1


def test_move_question_says_when_the_recording_keeps_its_name(win, tmp_path, monkeypatch):
    """The audit, 25 October (S9): with automatic renaming off, the question promised a rename."""
    from PySide6.QtWidgets import QInputDialog, QMessageBox
    db = win.doc.db
    uw = win.open_utterances()
    uw.import_files([str(_wav(tmp_path / "hello.wav"))])
    u = db.utterances[0]
    db.settings.auto_update_names = False
    asked = []
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: asked.append(a[2]) or QMessageBox.No)
    monkeypatch.setattr(QInputDialog, "getItem", lambda parent, title, label, items, *a, **k:
                        (next(i for i in items if i.startswith("U")), True))
    uw.move_category(u)
    assert "keeps its name" in asked[-1] and "renamed to match" not in asked[-1]
