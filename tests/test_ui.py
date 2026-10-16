"""Offscreen checks of the main window and token dialogue (no audio needed)."""

import os
import shutil
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["LEMMATRIX_SETTINGS"] = "Lemmatrix-tests"

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from lemmatrix import storage  # noqa: E402

SAMPLES = Path(__file__).resolve().parent.parent / "samples"


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def win(app, tmp_path, monkeypatch):
    from lemmatrix.ui import main_window
    shutil.copy2(SAMPLES / "Sample.xml", tmp_path / "Sample.xml")
    shutil.copytree(SAMPLES / "Soundfiles", tmp_path / "Soundfiles")
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.Yes)
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: None)
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)
    w = main_window.MainWindow()
    w.load_database(storage.load(tmp_path / "Sample.xml"))
    w.prefs.confirm_delete = True
    yield w
    w.doc.undo.setClean()
    w.doc._settings_dirty = False
    w.close()


def test_fill_an_empty_cell_and_undo(win):
    from lemmatrix.ui.token_dialog import Slot, TokenDialog
    rʉʉr = win.doc.db.entry_by_ref("D002")
    before = len(rʉʉr.tokens)
    dlg = TokenDialog(win, [Slot(rʉʉr, None, ("Plural", "before H"), explicit=True, defaults=True)], 0)
    dlg.edits["Phonetic"].setText("rʉʉɲ kɒ")
    dlg._ok()
    assert len(rʉʉr.tokens) == before + 1
    new = rʉʉr.tokens[-1]
    assert new.tags == ["Plural", "before H", "in isolation"]
    assert new.get("Phonetic") == "rʉʉɲ kɒ"
    win.doc.undo.undo()
    assert len(rʉʉr.tokens) == before


def test_back_and_next_skip_untouched_empty_cells(win):
    from lemmatrix.ui.token_dialog import Slot, TokenDialog
    chʊʊ = win.doc.db.entry_by_ref("E001")
    before = len(chʊʊ.tokens)
    slots = [Slot(chʊʊ, 0), Slot(chʊʊ, None, ("Singular", "Genitive"), defaults=True), Slot(chʊʊ, 1)]
    dlg = TokenDialog(win, slots, 0)
    dlg._move(1)
    dlg._move(1)              # passes through the empty cell without typing anything
    assert len(chʊʊ.tokens) == before
    assert dlg.pos == 2


def test_changing_tags_renames_the_recording(win):
    from lemmatrix.ui.token_dialog import Slot, TokenDialog
    db = win.doc.db
    goat = db.entry_by_ref("D001")
    i = next(i for i, t in enumerate(goat.tokens) if t.tags == ["Singular", "in isolation"])
    old = goat.tokens[i].file
    folder = storage.sound_folder(db)
    assert (folder / old).exists()
    dlg = TokenDialog(win, [Slot(goat, i)], 0)
    dlg.tags.buttons["Ergative"].setChecked(True)
    dlg._ok()
    t = goat.tokens[i]
    assert t.file == "LXX-VXX-SP1_D001_goat_SG-ERG.wav"
    assert (folder / t.file).exists() and not (folder / old).exists()


def test_tag_buttons_are_exclusive_within_a_group(win):
    from lemmatrix.ui.token_dialog import Slot, TokenDialog
    goat = win.doc.db.entry_by_ref("D001")
    dlg = TokenDialog(win, [Slot(goat, 1)], 0)
    dlg.tags.buttons["Plural"].setChecked(True)
    assert not dlg.tags.buttons["Singular"].isChecked()
    dlg.tags.buttons["Plural"].setChecked(False)
    assert "Plural" not in dlg.tags.selected() and "Singular" not in dlg.tags.selected()
    dlg.reject()


def test_matrix_modes_render(win):
    from lemmatrix.ui.matrix_view import ALL_DATA, ENTRY_TAG, TAG_TAG
    for mode in (ALL_DATA, TAG_TAG, ENTRY_TAG):
        win.tabs.setCurrentIndex(mode)
    assert win.layout_ is not None and win.layout_.rows
    slots = win._slots()
    assert slots and all(s.entry is not None for s in slots)


def test_save_and_reload(win):
    win.save()
    back = storage.load(win.doc.db.path)
    assert storage.to_string(back) == storage.to_string(win.doc.db)
