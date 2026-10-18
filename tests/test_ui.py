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
    assert new.tags == ["Plural", "before H", "isolation"]
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
    i = next(i for i, t in enumerate(goat.tokens) if t.tags == ["Singular", "isolation"])
    old = goat.tokens[i].file
    folder = storage.sound_folder(db)
    assert (folder / old).exists()
    dlg = TokenDialog(win, [Slot(goat, i)], 0)
    dlg.tags.buttons["Ergative"].setChecked(True)
    dlg._ok()
    t = goat.tokens[i]
    assert t.file == "LXX-VXX_D001_goat_SG-ERG.wav"
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


def test_matrix_tabs_render(win):
    from lemmatrix import matrix as mx
    from lemmatrix.ui.main_window import ALL_DATA, LEMMA_TAG, TAG_TAG
    assert win.tabs.currentIndex() == ALL_DATA                   # All data is the default
    assert win.all_table.model_.rowCount() > 0
    win.lemmas.select_row(win.doc.db.entry_by_ref("D001"))
    win.tabs.setCurrentIndex(LEMMA_TAG)
    lay = win.layouts[LEMMA_TAG]
    assert not lay.cols and "Blank matrix" in win.count_label(win.tabs.currentIndex()).text()      # blank until configured
    cfg = win.config_for(LEMMA_TAG)
    cfg.x = [mx.Spec.citation(), mx.Spec(frozenset({"Plural"}), mx.LOOSE)]
    win.refresh()
    lay = win.layouts[LEMMA_TAG]
    assert len(lay.rows) == len(win.doc.db.entries)                      # every word class
    assert "lemmas shown" in win.count_label(win.tabs.currentIndex()).text()
    win.tabs.setCurrentIndex(TAG_TAG)
    assert win.layouts[TAG_TAG].message == "Please configure a matrix."
    cfg = win.config_for(TAG_TAG)
    cfg.y = [mx.Spec(frozenset({"Singular"})), mx.Spec(frozenset({"Plural"}))]
    cfg.x = [mx.Spec(frozenset()), mx.Spec(frozenset({"Genitive"}))]
    win.refresh()
    lay = win.layouts[TAG_TAG]
    assert len(lay.rows) == 2 and lay.tokens(1, 1)               # PL + GEN exists for goat
    assert all(s.entry is not None for s in win._slots(TAG_TAG))


def test_tag_filter_in_all_data(win):
    from lemmatrix import filters as fl
    t = win.all_table
    total = t.proxy.rowCount()
    t.proxy.set_filter("tags", fl.ChoiceFilter({"Plural"}))
    some = t.proxy.rowCount()
    t.proxy.set_filter("tags", fl.ChoiceFilter({"Plural"}, fl.NONE))
    rest = t.proxy.rowCount()
    assert 0 < some < total and some + rest == total
    t.proxy.set_filter("tags", fl.ChoiceFilter({"Plural", "Genitive"}, fl.EXACTLY))
    assert t.proxy.rowCount() == 3                               # goat, lion and duck PL + GEN
    t.clear_filters()
    assert t.proxy.rowCount() == total


def test_delete_token_recycles_recording(win, monkeypatch):
    from PySide6.QtCore import QFile
    trashed = []
    monkeypatch.setattr(QFile, "moveToTrash", lambda path: trashed.append(path) or True)
    goat = win.doc.db.entry_by_ref("D001")
    i = next(i for i, t in enumerate(goat.tokens) if t.file)
    n = len(goat.tokens)
    win.all_table.select_row(next(r for r in win.all_table.model_.rows if r.entry is goat and r.index == i))
    win.delete_token()
    assert len(goat.tokens) == n - 1 and len(trashed) == 1
    win.doc.undo.undo()
    assert len(goat.tokens) == n
    win.prefs.delete_recordings_with_tokens = False
    win.refresh()
    win.all_table.select_row(next(r for r in win.all_table.model_.rows if r.entry is goat and r.index == i))
    win.delete_token()
    assert len(trashed) == 1                                     # kept this time
    win.prefs.delete_recordings_with_tokens = True


def test_save_and_reload(win):
    win.save()
    back = storage.load(win.doc.db.path)
    assert storage.to_string(back) == storage.to_string(win.doc.db)


def test_fields_dialog_renames_and_adds(win):
    from lemmatrix.ui.fields_dialog import FieldsDialog
    db = win.doc.db
    dlg = FieldsDialog(win, db)
    lemma = dlg.lists["lemma"]
    tone = next(f for f in lemma if f.name == "ToneClass")
    tone.name = "Tone"
    dlg.accept()
    assert dlg.result() == 1                                     # accepted
    assert dlg.apply()                                           # a rename happened
    goat = db.entry_by_ref("D001")
    assert goat.get("Tone") == "L/H" and not goat.get("ToneClass")
    dlg._preview()
    assert "<Tone>" in dlg.preview.toPlainText()
    win._setup_columns()
    assert any(c.key == "Tone" for c in win.lemmas.model_.all_columns)


def test_configure_matrix_dialog_round_trip(win):
    from lemmatrix import matrix as mx
    from lemmatrix.ui.matrix_dialogs import ConfigureMatrixDialog
    cfg = mx.MatrixConfig(kind=mx.TAG_TAG, y=[mx.Spec(frozenset({"1SG.A"}))],
                          x=[mx.Spec.citation()])
    dlg = ConfigureMatrixDialog(win, win.doc.db, cfg)
    out = dlg.result_config()
    assert out.y == cfg.y and out.x == cfg.x


def test_save_matrix(win, monkeypatch):
    from lemmatrix import matrix as mx
    from lemmatrix.ui import main_window
    from lemmatrix.ui.main_window import LEMMA_TAG
    monkeypatch.setattr(main_window, "ask_matrix_name", lambda *a, **k: "Noun overview")
    win.lemmas.select_row(win.doc.db.entry_by_ref("D001"))
    win.tabs.setCurrentIndex(LEMMA_TAG)
    win.save_matrix(LEMMA_TAG)                                   # a blank matrix isn't saved
    assert win.doc.db.settings.matrices == []
    win.config_for(LEMMA_TAG).x = [mx.Spec(frozenset({"Plural"}), mx.LOOSE)]
    win.save_matrix(LEMMA_TAG)
    saved = win.doc.db.settings.matrices
    assert [m.name for m in saved] == ["Noun overview"] and saved[0].x
    win.tabs.setCurrentIndex(main_window.TAG_TAG)               # Tag/Tag lists only its own kind
    assert win.tt_bar["saved"].findText("Noun overview") < 0
    win.tabs.setCurrentIndex(LEMMA_TAG)
    assert win.lt_bar["saved"].findText("Noun overview") > 0


def _button(widget, text):
    from PySide6.QtWidgets import QToolButton
    return next(b for b in widget.findChildren(QToolButton) if b.text() == text)


def test_option_buttons_actually_work(win, monkeypatch):
    """Clicking passes a 'checked' flag; it must not replace the button's own arguments."""
    from PySide6.QtWidgets import QDialog
    from lemmatrix.ui.main_window import LEMMA_TAG, TAG_TAG
    opened = []
    monkeypatch.setattr(QDialog, "exec", lambda self: opened.append(type(self).__name__) or 0)
    win.lemmas.select_row(win.doc.db.entry_by_ref("V001"))
    for tab, bar in ((LEMMA_TAG, win.lt_bar), (TAG_TAG, win.tt_bar)):
        win.tabs.setCurrentIndex(tab)
        _button(bar["widget"], "Configure cell").click()
        _button(bar["widget"], "Configure matrix").click()
    assert opened == ["ConfigureCellDialog", "ConfigureMatrixDialog"] * 2


def test_fields_dialog_add_buttons(win, monkeypatch):
    from PySide6.QtWidgets import QInputDialog, QToolButton
    from lemmatrix.ui.fields_dialog import FieldsDialog
    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("Syllables", True))
    dlg = FieldsDialog(win, win.doc.db)
    adds = [b for b in dlg.findChildren(QToolButton) if b.toolTip() == "Add a token field"]
    adds[0].click()
    assert dlg.lists["token"][-1].name == "Syllables"


def test_citation_and_sound_file_filters(win):
    from lemmatrix import filters as fl
    t = win.all_table
    t.proxy.set_filter("tags", fl.ChoiceFilter({fl.CITATION_ITEM}))
    cit = t.proxy.rowCount()
    assert cit == len(win.doc.db.entries)                        # one citation token per lemma
    t.proxy.set_filter("tags", fl.ChoiceFilter({fl.CITATION_ITEM}, fl.NONE))
    assert t.proxy.rowCount() == t.model_.rowCount() - cit
    t.clear_filters()
    t.proxy.set_filter("file", fl.Blanks())
    blanks = t.proxy.rowCount()
    t.proxy.set_filter("file", fl.NonBlanks())
    recorded = t.proxy.rowCount()
    assert recorded == len(win.sound_files) and blanks + recorded == t.model_.rowCount()


def test_lemma_fields_edit_in_place(win):
    goat = win.doc.db.entry_by_ref("D001")
    win._lemma_edited(goat, "ToneClass", "H/H")
    assert goat.get("ToneClass") == "H/H"
    assert "H/H" in win.doc.db.settings.entry_field("ToneClass").all_values()
    win._lemma_edited(goat, "Gloss:en", "he/she")              # refused: / isn't allowed
    assert win.doc.db.gloss(goat) == "goat"


def test_closing_with_unsaved_changes_and_discarding(app, tmp_path, monkeypatch):
    import sys
    from PySide6.QtWidgets import QMessageBox
    from lemmatrix.ui import main_window
    shutil.copy2(SAMPLES / "Sample.xml", tmp_path / "Sample.xml")
    w = main_window.MainWindow()
    w.load_database(storage.load(tmp_path / "Sample.xml"))
    goat = w.doc.db.entry_by_ref("D001")
    w.doc.edit_entry(goat, lambda e: e.set("Comment", "changed"), "Edit")
    assert w.doc.dirty
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.Discard)
    errors = []
    monkeypatch.setattr(sys, "excepthook", lambda *a: errors.append(a))
    assert w.close()
    w.deleteLater()
    app.processEvents()
    from PySide6.QtCore import QCoreApplication, QEvent
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    assert errors == []


def test_new_matrix_lines_default_to_loose_and_duplicate(win, monkeypatch):
    from lemmatrix import matrix as mx
    from lemmatrix.ui import matrix_dialogs as md
    dlg = md.SpecDialog(win, win.doc.db)
    assert dlg.radios[mx.LOOSE].isChecked()
    lst = md.SpecList(win.doc.db, [mx.Spec(frozenset({"Plural", "before H"}), mx.EXACT)], "X",
                      present=lambda: [mx.Spec.citation()])
    lst.list.setCurrentRow(0)
    monkeypatch.setattr(md.SpecDialog, "exec", lambda self: True)
    lst._duplicate()
    assert lst.specs() == [mx.Spec(frozenset({"Plural", "before H"}), mx.EXACT)] * 2
    lst.list.clear()
    assert lst.specs() == []
    lst.set_specs(lst.present())
    assert lst.specs() == [mx.Spec.citation()]


def test_clear_and_rename_matrix(win, monkeypatch):
    from lemmatrix import matrix as mx
    from lemmatrix.ui import main_window as mw
    win.lemmas.select_row(win.doc.db.entry_by_ref("D001"))
    win.tabs.setCurrentIndex(mw.LEMMA_TAG)
    win.clear_matrix(mw.LEMMA_TAG)
    assert win.layouts[mw.LEMMA_TAG].cols == [] and win.layouts[mw.LEMMA_TAG].rows == []
    assert win.lt_bar["saved"].itemText(0) == "(blank)"
    cfg = win.config_for(mw.LEMMA_TAG)
    cfg.x = [mx.Spec(frozenset({"Plural"}), mx.LOOSE)]
    cfg.blank = False
    monkeypatch.setattr(mw, "ask_matrix_name", lambda *a, **k: "Plurals")
    win.save_matrix(mw.LEMMA_TAG)
    monkeypatch.setattr(mw, "ask_matrix_name", lambda *a, **k: "All plurals")
    win.rename_matrix(mw.LEMMA_TAG)
    names = [m.name for m in win.doc.db.settings.matrices]
    assert "All plurals" in names and "Plurals" not in names
    assert win.config_for(mw.LEMMA_TAG).name == "All plurals"


def test_renamed_tags_follow_into_matrices(win, monkeypatch):
    from lemmatrix import matrix as mx
    from lemmatrix.ui import main_window as mw
    db = win.doc.db
    db.settings.matrices.append(mx.MatrixConfig("Pl", mx.LEMMA_TAG,
                                                x=[mx.Spec(frozenset({"Plural"}), mx.LOOSE)]))
    win.configs[mx.TAG_TAG] = mx.MatrixConfig(kind=mx.TAG_TAG,
                                              y=[mx.Spec(frozenset({"Plural"}), mx.LOOSE)],
                                                        x=[mx.Spec(frozenset({"before H"}), mx.LOOSE)])

    class Fake:
        def __init__(self, *a):
            pass

        def exec(self):
            return True

        def renames(self):
            return {"Plural": "Many"}

        def structure(self):
            ts = db.settings.tags
            for _, g in ts.leaf_groups():
                for t in g.tags:
                    if t.name == "Plural":
                        t.name = "Many"
            return ts
    _tag_editor(monkeypatch, lambda dlg: Fake())
    win.edit_tags()
    assert db.settings.matrices[-1].x == [mx.Spec(frozenset({"Many"}), mx.LOOSE)]
    assert win.configs[mx.TAG_TAG].y == [mx.Spec(frozenset({"Many"}), mx.LOOSE)]
    assert any("Many" in t.tags for e in db.entries for t in e.tokens)


def test_duplicate_tags_are_red_and_block_ok(win, monkeypatch):
    from PySide6.QtCore import Qt
    from lemmatrix.ui.dialogs import KIND_TAG, TagStructureDialog
    dlg = TagStructureDialog(win, win.doc.db)
    noun = dlg.tree.topLevelItem(0)
    tags = [it for it in dlg._tag_items(noun) if it.data(0, Qt.UserRole) == KIND_TAG]
    assert tags[0].data(0, Qt.ForegroundRole) is None
    tags[1].setText(0, tags[0].text(0))            # e.g. two "Singular"s
    assert tags[0].data(0, Qt.ForegroundRole) is not None
    assert tags[1].data(0, Qt.ForegroundRole) is not None
    assert dlg.problem_note.text()
    accepted = []
    monkeypatch.setattr(type(dlg).__mro__[1], "accept", lambda self: accepted.append(1))
    dlg.accept()
    assert not accepted


def test_spacebar_plays_in_matrix_and_all_data(win, monkeypatch):
    from PySide6.QtCore import QEvent, Qt
    from PySide6.QtGui import QKeyEvent
    from lemmatrix.ui import main_window as mw
    played = []
    monkeypatch.setattr(mw.MainWindow, "play_selected", lambda self: played.append(1))
    # the signals were connected to the bound originals, so watch the signals instead
    win.lt_view.playRequested.connect(lambda: played.append("lt"))
    win.all_table.playRequested.connect(lambda: played.append("all"))
    space = QKeyEvent(QEvent.KeyPress, Qt.Key_Space, Qt.NoModifier, " ")
    win.lt_view.keyPressEvent(space)
    win.all_table.keyPressEvent(space)
    assert "lt" in played and "all" in played


def test_settings_tabs_theme_and_pitch(win):
    from PySide6.QtGui import QPalette
    from PySide6.QtWidgets import QTabWidget
    from lemmatrix.ui import theme
    from lemmatrix.ui.dialogs import PreferencesDialog
    dlg = PreferencesDialog(win, win.doc.db, win.prefs)
    tabs = dlg.findChild(QTabWidget)
    assert [tabs.tabText(i) for i in range(tabs.count())] == ["General", "Sound", "Display", "Pitch"]
    dlg.theme.setCurrentIndex(dlg.theme.findData("dark"))
    dlg.accent.set_colour(theme.QColor("#2e9e44"))
    dlg.apply()
    try:
        theme.from_prefs(win.prefs)
        win._restyle()
        assert QApplication.instance().palette().color(QPalette.Window).lightness() < 80
        # the data views are dark too, with light text
        assert win.all_table.palette().color(QPalette.Base).lightness() < 60
        assert win.lt_view.palette().color(QPalette.Text).lightness() > 200
        # pitch traces follow the accent, brightened enough to show on dark grey
        p = theme.colour("pitch")
        assert p.green() > p.red() and p.lightness() > theme.accent().lightness()
    finally:
        win.prefs.theme, win.prefs.accent = "light", theme.DEFAULT_ACCENT
        theme.from_prefs(win.prefs)
    assert theme.colour("pitch").name() == theme.DEFAULT_ACCENT
    menus = [a.text() for a in win.menuBar().actions()]
    assert "&Settings" not in menus
    edit = next(a.menu() for a in win.menuBar().actions() if a.text() == "&Edit")
    assert any("Settings" in a.text() for a in edit.actions())


def test_last_view_is_restored(app, tmp_path, monkeypatch):
    from lemmatrix import matrix as mx
    from lemmatrix.ui import main_window as mw
    shutil.copy2(SAMPLES / "Sample.xml", tmp_path / "Sample.xml")
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.Discard)
    w = mw.MainWindow()
    w.load_database(storage.load(tmp_path / "Sample.xml"))
    w.lemmas.select_row(w.doc.db.entry_by_ref("V001"))
    w.tabs.setCurrentIndex(mw.TAG_TAG)
    cfg = w.config_for(mw.TAG_TAG)
    cfg.y = [mx.Spec(frozenset({"Past"}), mx.LOOSE)]
    cfg.x = [mx.Spec(frozenset({"Negative"}), mx.LOOSE)]
    w.switch_axes(mw.TAG_TAG)
    w.close()
    w2 = mw.MainWindow()
    w2.load_database(storage.load(tmp_path / "Sample.xml"))
    try:
        assert w2.tabs.currentIndex() == mw.TAG_TAG
        assert w2.lemmas.current_row().ref == "V001"
        got = w2.config_for(mw.TAG_TAG)
        assert got.y == cfg.y and got.x == cfg.x
        assert w2.switched[mw.TAG_TAG]
    finally:
        w2.close()


def test_token_dialogue_praat_and_pitch_buttons(win, monkeypatch):
    from lemmatrix.ui.token_dialog import Slot, TokenDialog
    e = win.doc.db.entry_by_ref("D001")
    recorded = next(i for i, t in enumerate(e.tokens) if t.file)
    dlg = TokenDialog(win, [Slot(e, recorded)], 0)
    assert dlg.praat_btn.isEnabled()
    assert "Soundfiles" in dlg.location.text()
    opened, played = [], []
    monkeypatch.setattr(win, "open_in_praat", lambda path, parent=None: opened.append(path))
    monkeypatch.setattr(win, "play_pitch", lambda text: played.append(text))
    dlg._open_in_praat()
    dlg._play_pitch()
    assert opened and opened[0].name == e.tokens[recorded].file
    assert played == [dlg.canvas.text]
    new = TokenDialog(win, [Slot(e, None, ("Plural",), explicit=True)], 0)
    assert not new.praat_btn.isEnabled()
    assert new.location.text().startswith("Will be saved as ")


def test_token_menus_and_clear_matrix_button(win):
    from PySide6.QtWidgets import QToolButton
    from lemmatrix.ui import main_window as mw
    win.lemmas.select_row(win.doc.db.entry_by_ref("D001"))
    win.tabs.setCurrentIndex(mw.ALL_DATA)
    win.all_table.selectRow(1)
    names = [i[0].split("\t")[0] for i in win._token_items()]
    assert names == ["Play", "Play pitch", "Open in Praat"]
    first_row = win.lt_bar["widget"].layout().itemAt(0).layout()
    texts = [first_row.itemAt(i).widget().text() for i in range(first_row.count())
             if isinstance(first_row.itemAt(i).widget(), QToolButton)]
    assert texts[-2:] == ["Configure matrix", "Clear matrix"]


def test_sound_folder_setting_shows_full_path_and_stores_relative(win, tmp_path):
    from lemmatrix.ui.dialogs import PreferencesDialog
    dlg = PreferencesDialog(win, win.doc.db, win.prefs)
    assert dlg.folder.text().endswith("Soundfiles") and len(dlg.folder.text()) > len("Soundfiles")
    assert dlg._stored_folder() == "Soundfiles"            # unchanged stays as it was
    dlg.folder.edit.setText(str(Path(win.doc.db.path).parent / "Recordings" / "2026"))
    assert dlg._stored_folder() == "Recordings/2026"
    dlg.folder.edit.setText(str(tmp_path.parent / "elsewhere"))
    assert dlg._stored_folder() == str(tmp_path.parent / "elsewhere")


def test_export_csv(win, tmp_path, monkeypatch):
    import csv
    from PySide6.QtWidgets import QFileDialog
    from lemmatrix import matrix as mx
    from lemmatrix.ui import main_window as mw
    db = win.doc.db
    out = tmp_path / "out.csv"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (str(out), ""))
    # entire database: one row per token, plus lemmas without tokens
    win.export_csv(filtered=False)
    rows = list(csv.reader(open(out, encoding="utf-8-sig")))
    assert rows[0][0] == "Reference" and "Tags" in rows[0] and "Sound file" in rows[0]
    assert len(rows) - 1 == sum(max(1, len(e.tokens)) for e in db.entries)
    assert open(out, "rb").read(3) == b"\xef\xbb\xbf"           # BOM, so Excel reads IPA
    # filtered: All data, after a quick search
    win.tabs.setCurrentIndex(mw.ALL_DATA)
    win.all_table.proxy.set_search("goat")
    win.export_csv(filtered=True)
    rows = list(csv.reader(open(out, encoding="utf-8-sig")))
    assert len(rows) - 1 == win.all_table.proxy.rowCount() and all("D001" in r[0] for r in rows[1:])
    # filtered: the Lemma/Tag grid as shown
    win.all_table.proxy.set_search("")
    win.lemmas.select_row(db.entry_by_ref("D001"))
    win.tabs.setCurrentIndex(mw.LEMMA_TAG)
    cfg = win.config_for(mw.LEMMA_TAG)
    cfg.x = [mx.Spec.citation(), mx.Spec(frozenset({"Plural"}), mx.EXACT)]
    win.refresh()
    win.export_csv(filtered=True)
    rows = list(csv.reader(open(out, encoding="utf-8-sig")))
    assert rows[0][1:] == ["Citation", "PL"]
    assert rows[1][0].startswith("D001") and "goat" in rows[1][1]


def test_app_icon_has_every_size(app):
    from lemmatrix.ui.icons import app_icon
    ic = app_icon()
    assert not ic.isNull()
    sizes = {(s.width(), s.height()) for s in ic.availableSizes()}
    assert {(16, 16), (32, 32), (256, 256)} <= sizes


def _tag_editor(monkeypatch, change):
    """Edit → Lists answers OK at once, with change(dialogue) applied to its tag editor
    (or the tag editor replaced by what change returns)."""
    from lemmatrix.ui import lists_dialog as ld
    real_init = ld.ListsDialog.__init__

    def init(self, *a, **k):
        real_init(self, *a, **k)
        replacement = change(self.tags)
        if replacement is not None:
            self.tags = replacement
    monkeypatch.setattr(ld.ListsDialog, "__init__", init)
    monkeypatch.setattr(ld.ListsDialog, "exec", lambda self: True)


def _set_singular_code(win, monkeypatch, code):
    def change(tags):
        for i in range(tags.tree.topLevelItemCount()):
            for it in tags._tag_items(tags.tree.topLevelItem(i)):
                if it.text(0) == "Singular":
                    it.setText(1, code)
    _tag_editor(monkeypatch, change)
    win.edit_tags()


def _missing(win):
    folder = storage.sound_folder(win.doc.db)
    return [t.file for e in win.doc.db.entries for t in e.tokens if t.file and not (folder / t.file).exists()]


def test_changed_tag_code_then_undo_keeps_recordings_linked(win, monkeypatch):
    db = win.doc.db
    assert db.settings.auto_update_names
    folder = storage.sound_folder(db)
    _set_singular_code(win, monkeypatch, "VG")
    assert (folder / "LXX-VXX_D001_goat_VG.wav").exists() and not _missing(win)
    while win.doc.undo.canUndo():
        win.doc.undo.undo()
    assert not _missing(win)                                  # files renamed back with the tokens
    assert (folder / "LXX-VXX_D001_goat_SG.wav").exists()
    while win.doc.undo.canRedo():
        win.doc.undo.redo()
    assert not _missing(win) and (folder / "LXX-VXX_D001_goat_VG.wav").exists()


def test_discarding_changes_puts_recording_names_back(win, monkeypatch):
    db = win.doc.db
    folder = storage.sound_folder(db)
    _set_singular_code(win, monkeypatch, "VG")
    assert (folder / "LXX-VXX_D001_goat_VG.wav").exists()
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.Discard)
    assert win._confirm_discard()
    saved = storage.load(db.path)                              # what's on disk now
    missing = [t.file for e in saved.entries for t in e.tokens if t.file and not (folder / t.file).exists()]
    assert not missing and (folder / "LXX-VXX_D001_goat_SG.wav").exists()


def test_find_missing_recordings_relinks_renamed_files(win, monkeypatch):
    db = win.doc.db
    folder = storage.sound_folder(db)
    (folder / "LXX-VXX_D001_goat_SG.wav").rename(folder / "LXX-VXX_D001_goat_VG.wav")   # renamed outside
    assert "LXX-VXX_D001_goat_SG.wav" in _missing(win)
    found, lost = win.missing_recordings()
    assert [(e.ref, n) for e, i, n, had in found] == [("D001", "LXX-VXX_D001_goat_VG.wav")] and not lost
    win.find_missing_recordings()
    assert not _missing(win)


def test_ctrl_space_plays_in_all_data_and_matrices(win, monkeypatch):
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from lemmatrix.ui import main_window as mw
    played = []
    monkeypatch.setattr(mw.MainWindow, "play_selected", lambda self: played.append("sound"))
    monkeypatch.setattr(mw.MainWindow, "play_selected_pitch", lambda self: played.append("pitch"))
    win.play_action.triggered.disconnect()
    win.play_pitch_action.triggered.disconnect()
    win.play_action.triggered.connect(lambda *_: win.play_selected())
    win.play_pitch_action.triggered.connect(lambda *_: win.play_selected_pitch())
    win.show()
    for tab, view in ((mw.ALL_DATA, win.all_table), (mw.LEMMA_TAG, win.lt_view)):
        win.tabs.setCurrentIndex(tab)
        view.setFocus()
        QApplication.processEvents()
        played.clear()
        QTest.keyClick(view, Qt.Key_Space, Qt.ControlModifier)
        QTest.keyClick(view, Qt.Key_Space, Qt.ControlModifier | Qt.ShiftModifier)
        assert played == ["sound", "pitch"], (tab, played)
    assert win.play_action.shortcut().toString() == "Ctrl+Space"


def test_find_recordings_added_by_hand_for_tokens_without_one(win):
    from lemmatrix import audio
    db = win.doc.db
    folder = storage.sound_folder(db)
    e = db.entry_by_ref("D001")
    fileless = [i for i, t in enumerate(e.tokens) if not t.file]
    assert fileless
    i = fileless[0]
    t = e.tokens[i]
    # Josh's case: a frame recording cut from a longer one, saved in the old Dekereke style
    old_style = "LXX-VXX_D001_goat-F2.wav"
    exact = db.expected_filename(e, t)
    audio.write_wav(folder / exact, [0.0] * 100, 8000)
    found, _ = win.missing_recordings()
    assert (e.ref, i, exact) in [(x.ref, k, n) for x, k, n, had in found]
    (folder / exact).rename(folder / old_style)                # a near name is found too
    found, _ = win.missing_recordings()
    assert [n for x, k, n, had in found if x is e] == [old_style]
    win.find_missing_recordings()
    assert any(tok.file == old_style or tok.file == exact for tok in e.tokens)


def test_online_only_recordings_are_marked_and_explained(win, monkeypatch):
    from lemmatrix import audio, matrix as mx
    from lemmatrix.ui import main_window as mw
    db = win.doc.db
    folder = storage.sound_folder(db)
    cloudy = "LXX-VXX_D001_goat_SG.wav"
    real_scan = storage.scan_sound_folder
    monkeypatch.setattr(storage, "scan_sound_folder", lambda f: (real_scan(f)[0], {cloudy}))
    win.lemmas.select_row(db.entry_by_ref("D001"))
    win.tabs.setCurrentIndex(mw.LEMMA_TAG)
    win.config_for(mw.LEMMA_TAG).x = mx.auto_specs(db, db.entries)
    win.refresh()
    assert win.lt_view.cloud_files == {cloudy}
    lay = win.layouts[mw.LEMMA_TAG]
    tips = [win.lt_view.model_.data(win.lt_view.model_.index(r, c), mw.Qt.ToolTipRole) or ""
            for r in range(len(lay.rows)) for c in range(len(lay.cols))]
    assert any("online only" in t for t in tips)
    win.lt_view.grab()                                        # paints the cloud mark without errors
    # a read that fails on an online-only file says why, in plain words
    monkeypatch.setattr(storage, "is_cloud_only", lambda p: True)
    monkeypatch.setattr(audio, "read_wav", lambda p: (_ for _ in ()).throw(OSError(22, "cloud provider")))
    import pytest
    with pytest.raises(audio.AudioError, match="online only"):
        audio.load_for_playing(folder / cloudy)


def test_open_elsewhere_warning(app, tmp_path, monkeypatch):
    import json
    from lemmatrix import lock
    from lemmatrix.ui import main_window as mw
    shutil.copy2(SAMPLES / "Sample.xml", tmp_path / "Sample.xml")
    path = str(tmp_path / "Sample.xml")
    lock.lock_path(path).write_text(json.dumps({"computer": "LAPTOP", "user": "josh", "pid": 1,
                                                "opened": "2026-10-17 09:14:00"}))
    choice = {"text": "Don't open"}
    shown = []
    monkeypatch.setattr(QMessageBox, "exec", lambda self: shown.append(self.text()) or 0)
    monkeypatch.setattr(QMessageBox, "clickedButton",
                        lambda self: next(b for b in self.buttons() if b.text() == choice["text"]))
    w = mw.MainWindow()
    try:
        w.open_file(path)
        assert shown and "LAPTOP" in shown[0] and w.doc.db.path != path
        choice["text"] = "Open anyway"
        w.open_file(path)
        assert w.doc.db.path == path
        assert lock.read(path).mine()                  # the marker is now this window's
    finally:
        w.doc.undo.setClean()
        w.doc._settings_dirty = False
        monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.Discard)
        w.close()
    assert not lock.lock_path(path).exists()           # removed on close


def test_only_lemmas_with_data_and_backup_folder(win, tmp_path):
    from lemmatrix.ui import main_window as mw
    db = win.doc.db
    win.lemmas.select_row(db.entry_by_ref("D001"))
    win.tabs.setCurrentIndex(mw.LEMMA_TAG)
    from lemmatrix import matrix as mx
    win.config_for(mw.LEMMA_TAG).x = mx.auto_specs(db, db.entries)
    win.only_data.setChecked(False)
    db.entries.append(db.new_entry("D099", gloss="unrecorded"))
    db.entries[-1].tokens.clear()
    db.entries[-1].set("WordClass", "NOUN")
    win.lemmas.set_rows(db.entries)
    win.refresh()
    all_rows = len(win.layouts[mw.LEMMA_TAG].rows)
    win.only_data.setChecked(True)
    rows = win.layouts[mw.LEMMA_TAG].rows
    assert len(rows) == all_rows - 1 and all(r.entry.ref != "D099" for r in rows)
    assert "hidden" in win.count_label(win.tabs.currentIndex()).text()
    # the same tick works in All data and Tag/Tag
    db.entries[-1].tokens.append(db.new_token(db.entries[-1]))      # an empty token: no data
    win.tabs.setCurrentIndex(mw.ALL_DATA)
    win.refresh()
    assert all(r.entry.ref != "D099" for r in win.all_table.model_.rows)
    win.lemmas.select_row(db.entry_by_ref("D099"))
    win.tabs.setCurrentIndex(mw.TAG_TAG)
    win.refresh()
    assert "no token data" in win.count_label(win.tabs.currentIndex()).text()
    win.only_data.setChecked(False)
    win.tabs.setCurrentIndex(mw.ALL_DATA)
    assert any(r.entry.ref == "D099" for r in win.all_table.model_.rows)
    # backups go to the chosen folder
    win.prefs.backup_folder = str(tmp_path / "MyBackups")
    try:
        win.save()
        win.save()
        assert list((tmp_path / "MyBackups").glob("Sample_*.xml"))
    finally:
        win.prefs.backup_folder = ""


def test_pitch_length_mark_and_compact_drawing(win):
    from lemmatrix import pitch
    from lemmatrix.ui.token_dialog import PitchValidator, Slot, TokenDialog
    assert pitch.normalise("4ː42 1ː1") == "4:42 1:1"
    v = PitchValidator()
    state, text, _ = v.validate("4ː42", 2)
    assert state == PitchValidator.Acceptable and text == "4:42"
    assert v.validate("4a", 1)[0] == PitchValidator.Invalid
    e = win.doc.db.entry_by_ref("D001")
    dlg = TokenDialog(win, [Slot(e, 0)], 0)
    assert dlg.canvas.height() < 60                     # 1-5: a compact drawing
    dlg.canvas.set_range(0, 9)
    assert dlg.canvas.height() > 60                     # a wider range draws taller


def test_pitch_volume_scales_the_sound():
    import numpy as np
    from lemmatrix import pitchsound as ps
    loud = ps.synthesise("22 44", voice="buzz", volume=1.0, seed=1)
    quiet = ps.synthesise("22 44", voice="buzz", volume=0.25, seed=1)
    assert np.isclose(np.abs(quiet).max() * 4, np.abs(loud).max(), rtol=0.01)


def test_ctrl_click_makes_a_line_for_each_combination(win):
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from lemmatrix import matrix as mx
    from lemmatrix.ui import matrix_dialogs as md
    old = mx.Spec(frozenset({"3SG.A", "Past"}), mx.LOOSE)
    dlg = md.SpecDialog(win, win.doc.db, old)              # opening with a spec works
    dlg.show()
    b = dlg.tags.buttons
    QTest.mouseClick(b["3PL.A"], Qt.LeftButton, Qt.ControlModifier)     # 3SG.A and 3PL.A
    QTest.mouseClick(b["Present"], Qt.LeftButton, Qt.ControlModifier)   # Past and Present
    QTest.mouseClick(b["Negative"], Qt.LeftButton)                       # one Polarity
    specs = dlg.specs()
    assert len(specs) == 4 and "4 lines" in dlg.count.text()
    assert {frozenset(s.tags) for s in specs} == {
        frozenset({p, t, "Negative"}) for p in ("3SG.A", "3PL.A") for t in ("Past", "Present")}
    QTest.mouseClick(b["1SG.A"], Qt.LeftButton)              # a plain click still replaces
    assert not b["3SG.A"].isChecked() and not b["3PL.A"].isChecked()
    assert len(dlg.specs()) == 2
    # editing a line in the list puts the extra combinations just below it
    lst = md.SpecList(win.doc.db, [old, mx.Spec.citation()], "X")
    lst.list.setCurrentRow(0)
    class Fake:
        def __init__(self, *a, **k): pass
        def exec(self): return True
        def specs(self): return specs
    import pytest
    mp = pytest.MonkeyPatch()
    mp.setattr(md, "SpecDialog", Fake)
    try:
        lst._edit(lst.list.item(0))
    finally:
        mp.undo()
    assert lst.specs() == specs + [mx.Spec.citation()]
    dlg.close()


# ---- notebook ---------------------------------------------------------------

def _today():
    from lemmatrix.model import today
    return today()


def test_saving_records_todays_comments_in_the_notebook(win, tmp_path):
    from lemmatrix import notebook as nb
    from lemmatrix.model import Person
    db = win.doc.db
    db.metadata.researchers = [Person("JS", "Josh")]
    win.sess_rows["researchers"].set_keys(["JS"])
    win.sess_rows["participants"].set_keys(["SP1"])
    win._session_people_changed()
    e = db.entry_by_ref("D002")
    win.doc.edit_entry(e, lambda x: x.set("Comment", "check the vowel"), "comment")
    assert e.changed == {"Comment": _today()}
    win.save()
    book = nb.load(tmp_path / "Sample.notebook")
    s = book.session(_today())
    assert s.researchers == ["JS"] and s.participants == ["SP1"]
    assert [c.text for c in s.comments] == ["check the vowel"]
    # undoing the comment and saving again takes it out of today's record
    win.doc.undo.undo()
    win.save()
    assert nb.load(tmp_path / "Sample.notebook").session(_today()).comments == []


def test_write_to_notebook_keeps_notes_and_saves_the_notebook(win, tmp_path):
    from lemmatrix import notebook as nb
    win.sess_rows["participants"].set_keys(["ABC"])
    win._session_people_changed()
    win.write_notebook()
    path = tmp_path / "Sample.notebook"
    assert path.exists()
    win.doc.notebook.session(_today()).notes = "my notes"
    win.sess_rows["participants"].set_keys(["SP1", "ABC"])
    win.write_notebook()
    s = nb.load(path).session(_today())
    assert s.notes == "my notes" and s.participants == ["SP1", "ABC"]


def test_first_participant_is_the_speaker_until_another_is_chosen(win):
    from lemmatrix.ui.token_dialog import Slot, TokenDialog
    win.prefs.speaker = ""
    win.sess_rows["participants"].set_keys(["ABC", "SP1"])
    win._session_people_changed()
    assert win.session_speaker() == "ABC"
    e = win.doc.db.entry_by_ref("D002")
    dlg = TokenDialog(win, [Slot(e, 0)], 0)
    items = [dlg.speaker.itemText(i) for i in range(dlg.speaker.count())]
    assert items[:3] == ["", "ABC", "SP1"]
    dlg.speaker.setCurrentText("SP1")
    dlg.speaker.activated.emit(dlg.speaker.currentIndex())
    assert win.session_speaker() == "SP1"
    dlg.reject()
    win.sess_rows["participants"].set_keys(["ABC"])        # SP1 leaves the session
    win._session_people_changed()
    assert win.session_speaker() == "ABC"


def test_notebook_window_edits_and_links(win, tmp_path):
    from lemmatrix import notebook as nb
    from lemmatrix.ui.notebook_dialog import NotebookDialog
    db = win.doc.db
    e = db.entry_by_ref("D002")
    win.doc.edit_entry(e, lambda x: x.tokens[0].set("Comment", "token note"), "comment")
    win.open_notebook()
    d = win.notebook_dialog
    assert isinstance(d, NotebookDialog) and d.session is None    # no notes yet
    d.add_note(_today())
    assert d.session.date == _today()
    assert [c.text for c in d.session.comments] == ["token note"]
    assert d.comments.topLevelItemCount() == 1
    d.notes.setPlainText("ɗæær [ATR]")
    assert d.session.notes == "ɗæær [ATR]" and win.doc.dirty
    d.session.questions.append(nb.Question("Why?", _today()))
    d._fill_questions()
    d.questions.setCurrentItem(d.questions.topLevelItem(0))
    d.toggle_resolved()
    assert d.session.questions[0].resolved == _today()
    # the link goes to the token
    d._follow(d.comments.topLevelItem(0))
    assert win.all_table.current_row() == type(win.all_table.current_row())(e, 0)
    win.save()
    assert nb.load(tmp_path / "Sample.notebook").session(_today()).notes == "ɗæær [ATR]"
    # search, and a past day pulls its speakers
    d.search.setText("ATR")
    d._search_changed()
    assert d.days.count() == 1
    d.search.setText("zzz")
    d._search_changed()
    assert d.days.count() == 0
    d.search.clear()
    d._search_changed()
    d.add_note("2026-10-09")
    assert d.session.participants == ["SP1"]                  # who spoke the tokens of that day
    assert d.recordings.topLevelItemCount() > 0
    d.delete_note()
    assert win.doc.notebook.session("2026-10-09") is None


def test_deleted_lemma_link_says_so(win):
    from lemmatrix import notebook as nb
    db = win.doc.db
    e = db.entry_by_ref("D002")
    s = win.doc.notebook.add_session("2026-10-01")
    s.comments.append(nb.NoteComment("old", e.id, "", e.ref, "D002 x"))
    win.doc.delete_entry(e)
    win.open_notebook("2026-10-01")
    it = win.notebook_dialog.comments.topLevelItem(0)
    assert "no longer exists" in it.text(1)


def test_lists_rename_a_participant_everywhere(win, monkeypatch):
    from lemmatrix.ui import lists_dialog as ld
    db = win.doc.db
    s = win.doc.notebook.add_session("2026-10-01")
    s.participants = ["SP1"]
    n = sum(1 for e in db.entries for t in e.tokens if t.speaker == "SP1")
    assert n

    def run(self):
        t = self.participants.table
        t.item(0, 0).setText("KD")
        return True
    monkeypatch.setattr(ld.ListsDialog, "exec", run)
    win.edit_lists("participants")
    assert db.participant_codes()[0] == "KD"
    assert sum(1 for e in db.entries for t in e.tokens if t.speaker == "KD") == n
    assert s.participants == ["KD"]


def test_lists_dialog_reads_and_writes_people_and_places(win):
    from lemmatrix.model import Location, Person
    from lemmatrix.ui.lists_dialog import ListsDialog
    db = win.doc.db
    db.metadata.locations = [Location("Sudan", "SU", children=[Location("Sample variety village", "VXX-V", "village")])]
    dlg = ListsDialog(win, db, win.doc.notebook, "locations")
    dlg.researchers._add_row(Person("JS", "Josh"))
    tree = dlg.locations.tree
    tree.setCurrentItem(tree.topLevelItem(0))
    dlg.locations._add_inside()
    tree.currentItem().setText(0, "Blue Nile")
    tree.currentItem().setText(1, "BND")
    dlg.apply()
    assert db.metadata.researcher("JS").name == "Josh"
    assert db.metadata.location_path("BND") == "Sudan › Blue Nile"
    assert db.metadata.location("VXX-V").description == "village"
    dlg.participants._add_row(Person("SP1"))                  # twice
    assert "twice" in dlg.participants.problem()


def test_questions_window(win):
    from lemmatrix import notebook as nb
    from lemmatrix.ui.notebook_dialog import QuestionsDialog
    s = win.doc.notebook.add_session("2026-10-01")
    s.questions = [nb.Question("open one", "2026-10-01"), nb.Question("done", "2026-10-01", "", "2026-10-02")]
    dlg = QuestionsDialog(win)
    assert dlg.tree.topLevelItemCount() == 1                   # open ones first
    dlg.show_which.setCurrentIndex(dlg.show_which.findData("all"))
    assert dlg.tree.topLevelItemCount() == 2
    dlg.tree.setCurrentItem(dlg.tree.topLevelItem(0))
    dlg.toggle()
    assert not s.questions[0].is_open and win.doc.dirty


def test_ctrl_click_shows_only_that_lemma(win):
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtTest import QTest
    t = win.lemmas
    total = t.proxy.rowCount()
    goat = win.doc.db.entry_by_ref("D002")
    t.select_row(goat)
    rect = t.visualRect(t.currentIndex())
    QTest.mouseClick(t.viewport(), Qt.LeftButton, Qt.ControlModifier, rect.center())
    assert t.visible_rows() == [goat]
    assert t.current_row() is goat
    win.refresh()
    assert "only D002" in win.lemma_count.text()
    rect = t.visualRect(t.currentIndex())
    QTest.mouseClick(t.viewport(), Qt.LeftButton, Qt.ControlModifier, rect.center())
    assert t.proxy.rowCount() == total and t.current_row() is goat
    t.toggle_pin(goat)
    win._clear_lemma_filters()                   # Clear all filters undoes it too
    assert t.proxy.rowCount() == total


def test_save_button_saves(win):
    win.doc.db.entry_by_ref("D002").values["Comment"] = "x"
    called = []
    win.save = lambda: called.append(1) or True
    win.save_btn.click()
    assert called


def test_tab_goes_round_the_token_fields_only(win):
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from lemmatrix.ui.token_dialog import Slot, TokenDialog
    from PySide6.QtWidgets import QApplication
    dlg = TokenDialog(win, [Slot(win.doc.db.entry_by_ref("E001"), 0)], 0)
    dlg.show()
    edits = list(dlg.edits.values())
    edits[0].setFocus()
    dlg.activateWindow()
    QApplication.processEvents()
    for nxt in edits[1:] + edits[:1]:
        QTest.keyClick(dlg.focusWidget(), Qt.Key_Tab)
        assert dlg.focusWidget() is nxt
    QTest.keyClick(dlg.focusWidget(), Qt.Key_Backtab)
    assert dlg.focusWidget() is edits[-1]
    dlg.reject()


# ---- bulk edit ----------------------------------------------------------------

def _bulk(win):
    win.open_bulk_edit()
    return win.bulk_window


def test_bulk_replace_preview_apply_and_undo(win):
    from lemmatrix import bulk
    from lemmatrix.ui import bulk_window as bw
    w = _bulk(win)
    assert w.level == bulk.TOKENS
    w.ops.setCurrentIndex(bw.REPLACE)
    w.r_field.setCurrentIndex(w.r_field.findData("f:Phonetic"))
    w.r_find.setText("ee")
    w.r_repl.setText("ææ")
    w.preview()
    assert w.plan is not None and w.plan.ok and w.apply_btn.isEnabled()
    goat = win.doc.db.entry_by_ref("D001")
    before = [t.get("Phonetic") for t in goat.tokens]
    assert "ee" in before[0]                               # nothing changed by the preview
    model = w.tables[bulk.TOKENS].model_
    assert any(c.new == "dæær" for c in model.preview.values())
    w.apply()
    assert goat.tokens[0].get("Phonetic") == "dæær"
    win.doc.undo.undo()                                     # one step undoes everything
    assert [t.get("Phonetic") for t in goat.tokens] == before


def test_bulk_unticked_rows_are_left_alone(win):
    from lemmatrix import bulk
    from lemmatrix.ui import bulk_window as bw
    w = _bulk(win)
    goat = win.doc.db.entry_by_ref("D001")
    rows = [r for r in w.tables[bulk.TOKENS].visible_rows() if r.entry is goat]
    w.set_ticked(rows, False)
    w.ops.setCurrentIndex(bw.REPLACE)
    w.r_field.setCurrentIndex(w.r_field.findData("f:Phonetic"))
    w.r_find.setText("ee")
    w.r_repl.setText("ææ")
    w.preview()
    w.apply()
    assert goat.tokens[0].get("Phonetic") == "dɪɪr"
    assert win.doc.db.entry_by_ref("D003").tokens[0].get("Phonetic") == "kæær"


def test_bulk_pitch_error_blocks_apply(win):
    from lemmatrix.ui import bulk_window as bw
    w = _bulk(win)
    w.ops.setCurrentIndex(bw.SHORTCUTS)
    w.s_which.setCurrentIndex(w.s_which.findData("pitch"))
    w.s_dir.setCurrentIndex(w.s_dir.findData("up"))
    w.preview()
    assert w.plan is not None and not w.plan.ok
    assert not w.apply_btn.isEnabled()
    assert "highest pitch" in w.summary.text()


def test_bulk_tag_change_renames_and_undo_renames_back(win):
    from lemmatrix import bulk
    from lemmatrix.ui import bulk_window as bw
    db = win.doc.db
    folder = storage.sound_folder(db)
    w = _bulk(win)
    chʊʊ = db.entry_by_ref("E001")
    rows = [r for r in w.tables[bulk.TOKENS].visible_rows()]
    w.set_ticked(rows, False)
    target = next(r for r in rows if r.entry is chʊʊ and r.token.tags == ["Singular", "isolation"])
    w.set_ticked([target], True)
    w.ops.setCurrentIndex(bw.SET)
    w.v_field.setCurrentIndex(w.v_field.findData("tags"))
    w.v_tag_action.setCurrentIndex(w.v_tag_action.findData(bulk.ADD_TAG))
    w.v_tag.setCurrentIndex(w.v_tag.findData("Genitive"))
    w.preview()
    assert w.plan.ok and len(w.plan.renames) == 1
    w.apply()
    t = target.token
    assert t.tags == ["Singular", "Genitive", "isolation"]
    assert t.file == "LXX-VXX_E001_duck_SG-GEN.wav" and (folder / t.file).exists()
    win.doc.undo.undo()
    t = target.token                                       # undo restores a fresh copy
    assert t.tags == ["Singular", "isolation"]
    assert (folder / "LXX-VXX_E001_duck_SG.wav").exists()
    assert not (folder / "LXX-VXX_E001_duck_SG-GEN.wav").exists()


def test_word_class_is_an_ordinary_field_now(win):
    db = win.doc.db
    nɨn = db.entry_by_ref("V002")
    before = [list(t.tags) for t in nɨn.tokens]
    wcf = db.settings.entry_field("word-class")
    win._lemma_edited(nɨn, wcf.name, "NOMINAL")             # a new class goes into the list
    assert db.word_class(nɨn) == "NOMINAL" and "NOMINAL" in wcf.all_values()
    assert [t.tags for t in nɨn.tokens] == before            # the tags stay
    assert db.unusual_tags(nɨn, nɨn.tokens[1].tags)          # and are now marked as unusual
    win.doc.undo.undo()
    assert db.word_class(nɨn) == "VERB"


def test_token_dialog_shows_usual_groups_first(win):
    from lemmatrix.ui.token_dialog import Slot, TokenDialog
    db = win.doc.db
    goat = db.entry_by_ref("D001")
    dlg = TokenDialog(win, [Slot(goat, 1)], 0)
    assert "Plural" in dlg.tags.buttons and "Past" not in dlg.tags.buttons
    assert dlg.show_all_btn.isVisibleTo(dlg) and "more group" in dlg.show_all_btn.text()
    dlg.show_all_btn.setChecked(True)
    assert "Past" in dlg.tags.buttons and dlg.tags.buttons["Past"].unusual
    dlg.tags.buttons["Past"].setChecked(True)
    assert not dlg.unusual_note.isHidden() and "isn't usual for NOUN" in dlg.unusual_note.text()
    dlg._ok()
    assert "Past" in goat.tokens[1].tags                     # allowed, only marked
    dlg = TokenDialog(win, [Slot(goat, 1)], 0)                # a group with a picked tag always shows
    assert "Past" in dlg.tags.buttons
    dlg._stop_unusual_warning()                               # "Don't show this again"
    assert not win.prefs.warn_unusual_tags
    win.set_unusual_warning(True)


def test_upgrading_an_old_database_is_reported(win, tmp_path, monkeypatch):
    shown = []
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: shown.append(a[2]))
    old = Path(__file__).resolve().parent / "data" / "Sample-format1.xml"
    shutil.copy2(old, tmp_path / "Old.xml")
    win.load_database(storage.load(tmp_path / "Old.xml"))
    assert shown and "upgraded" in shown[0]
    assert win.doc.dirty                                     # so saving writes the new format


def test_bulk_window_screenshot_layout(win):
    w = _bulk(win)
    w.resize(1360, 900)
    w.show()
    QApplication.processEvents()
    assert w.tables["tokens"].model_.rowCount() > 0
    w.close()
    assert win.bulk_window is None


def test_option_panels_hide_and_show(win):
    win.show()
    win.left_split.setSizes([600, 170])
    win.right_split.setSizes([600, 150])
    win.toggle_panels()
    assert win.panels_hidden()
    assert win.left_split.sizes()[1] == 0 and win.right_split.sizes()[1] == 0
    win.toggle_panels()
    assert not win.panels_hidden()
    assert win.left_split.sizes()[1] > 0 and win.right_split.sizes()[1] > 0


def test_renaming_a_word_class_follows_into_lemmas_and_hints(win):
    from lemmatrix.ui.lists_dialog import ListsDialog
    db = win.doc.db
    dlg = ListsDialog(win, db, win.doc.notebook)
    tree = dlg.class_list.tree
    verb = next(tree.topLevelItem(i) for i in range(tree.topLevelItemCount())
                if tree.topLevelItem(i).text(0) == "VERB")
    verb.setText(0, "Verbal")
    assert next(g for g in dlg.tags.structure().groups if g.name == "VERB").usual == ["Verbal"]
    assert dlg.value_renames() == {"WordClass": {"VERB": "Verbal"}}
    dlg.apply()
    win._apply_tags(dlg.tags, dlg.value_renames())
    assert db.word_class(db.entry_by_ref("V001")) == "Verbal"
    assert "Verbal" in db.settings.word_classes()
    assert db.unusual_tags(db.entry_by_ref("V001"), ["Past"]) == []     # still usual


def test_session_people_carry_over_to_the_next_day(win, tmp_path):
    """A new day starts with the last people and places: remembered, or the latest notebook day."""
    from lemmatrix.ui import chiprow as chips
    path = win.doc.db.path
    win.prefs.set_session_for(path, {})                      # nothing remembered
    s = win.doc.notebook.add_session("2026-01-05")         # yesterday, say: a day with notes
    s.researchers, s.participants = ["JS"], ["SP1"]
    win._fill_session()                                    # opening on a day without notes
    assert win.sess_rows[chips.RESEARCHERS].keys == ["JS"]
    assert win.sess_rows[chips.PARTICIPANTS].keys == ["SP1"]
    assert win.prefs.session_for(path)[chips.PARTICIPANTS] == ["SP1"]   # and now remembered
    win.sess_rows[chips.PARTICIPANTS]._add("ABC")         # picked in the panel
    win._fill_session()
    assert win.sess_rows[chips.PARTICIPANTS].keys == ["SP1", "ABC"]


def test_token_dialogue_remembers_its_size(win):
    from lemmatrix.ui.token_dialog import Slot, TokenDialog
    e = win.doc.db.entry_by_ref("E001")
    dlg = TokenDialog(win, [Slot(e, 0)], 0)
    dlg.show()
    dlg.resize(760, 700)         # (the offscreen test screen is small)
    dlg.reject()
    again = TokenDialog(win, [Slot(e, 0)], 0)
    assert (again.width(), again.height()) == (760, 700)
    again.reject()


def test_double_clicking_a_lemma_in_lemma_tag_selects_it(win):
    from lemmatrix import matrix as mx
    from lemmatrix.ui.main_window import LEMMA_TAG
    win.tabs.setCurrentIndex(LEMMA_TAG)
    win.config_for(LEMMA_TAG).x = [mx.Spec.citation()]
    win.refresh()
    lay = win.layouts[LEMMA_TAG]
    target = lay.rows[2].entry
    win.lemmas.select_row(lay.rows[0].entry)
    win.lt_view.verticalHeader().sectionDoubleClicked.emit(2)
    assert win.lemmas.current_row() is target
    win.switch_axes(LEMMA_TAG)                     # lemmas along the top: the same
    win.lemmas.select_row(lay.rows[0].entry)
    win.lt_view.horizontalHeader().sectionDoubleClicked.emit(2)
    assert win.lemmas.current_row() is target


def test_predicted_translation_in_the_token_dialogue(win):
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from lemmatrix.ui.token_dialog import Slot, TokenDialog
    duck = win.doc.db.entry_by_ref("E001")          # has no Singular + Genitive token yet
    dlg = TokenDialog(win, [Slot(duck, None, ("Singular", "Genitive"), explicit=True, defaults=True)], 0)
    ed = dlg.translation
    assert ed.text() == "" and ed.placeholderText() == "of the duck"   # from goat, lion, sheep
    assert ed.font().italic() and "→" in ed.toolTip()
    QTest.keyClick(ed, Qt.Key_Right)                # → accepts it
    assert ed.text() == "of the duck" and not ed.font().italic()
    QTest.keyClick(ed, Qt.Key_Right)                # and is an ordinary key again
    assert ed.text() == "of the duck"
    ed.clear()
    assert ed.placeholderText() == "of the duck"
    QTest.keyClicks(ed, "duck's")                   # typing replaces the suggestion
    assert ed.text() == "duck's" and ed.placeholderText() == ""
    ed.clear()
    dlg.tags.buttons["Genitive"].click()            # other tags: another suggestion
    assert ed.placeholderText() == "duck"
    dlg.tags.buttons["Genitive"].click()
    dlg.accept_suggestion()
    dlg._ok()
    new = duck.tokens[-1]
    assert new.get("Translation", "en") == "of the duck"
    win.doc.undo.undo()
    assert duck.tokens[-1] is not new


def test_bulk_edit_fills_predicted_translations(win):
    from lemmatrix import bulk
    from lemmatrix.ui import bulk_window as bw
    lion = win.doc.db.entry_by_ref("D002")
    i = next(i for i, t in enumerate(lion.tokens) if set(t.tags) >= {"Plural", "Genitive"})
    win.doc.edit_entry(lion, lambda en: en.tokens[i].set("Translation", "", "en"), "clear")
    win.open_bulk_edit()
    b = win.bulk_window
    b.ops.setCurrentIndex(bw.PREDICT)
    assert b.p_field.text() == "Translation"
    b.preview()
    assert b.plan.ok and b.apply_btn.isEnabled()
    assert "1 of" in b.summary.text() and "left as they are" in b.summary.text()
    b.apply()
    assert lion.tokens[i].get("Translation", "en") == "of the lions"
    win.doc.undo.undo()
    assert lion.tokens[i].get("Translation", "en") == ""
    b.levels.setCurrentIndex(0)
    b.preview()
    assert b.plan is None and "Tokens tab" in b.summary.text()
    b.close()


def test_predicted_translation_in_all_data(win):
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QWidget
    lion = win.doc.db.entry_by_ref("D002")
    i = next(i for i, t in enumerate(lion.tokens) if set(t.tags) >= {"Plural", "Genitive"})
    win.doc.edit_entry(lion, lambda en: en.tokens[i].set("Translation", "", "en"), "clear")
    win.refresh()
    table = win.all_table
    row = next(r for r in table.visible_rows() if r.entry is lion and r.index == i)
    assert win.suggestion_for(row).text == "of the lions"
    col = table.visible_keys().index("f:Translation")
    table.select_row(row)
    idx = table.currentIndex().siblingAtColumn(col)
    assert idx.data(Qt.DisplayRole) == ""                       # still empty: only shown
    assert "→" in idx.data(Qt.ToolTipRole)
    delegate = table.itemDelegateForColumn(col)
    holder = QWidget()
    ed = delegate.createEditor(holder, None, idx)
    delegate.setEditorData(ed, idx)
    assert ed.placeholderText() == "of the lions" and ed.font().italic()
    ed.installEventFilter(delegate)
    QTest.keyClick(ed, Qt.Key_Right)
    assert ed.text() == "of the lions" and not ed.font().italic()
    delegate.setModelData(ed, table.model(), idx)
    assert lion.tokens[i].get("Translation", "en") == "of the lions"
    win.doc.undo.undo()
    assert lion.tokens[i].get("Translation", "en") == ""
    win.accept_suggestion(row)                                  # the right-click menu's item
    assert lion.tokens[i].get("Translation", "en") == "of the lions"
    assert win.suggestion_for(row) is None                      # has a translation now
