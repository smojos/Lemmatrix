# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders. Additional terms: NOTICE.md
"""Render the main windows and dialogues offscreen to PNG files (for checking layouts). A tool for
the developer (Claude checks layouts with it): nothing in Lemmatrix uses it. It works on the
sample database as it is now (an EACW database since 23 October: D009 goat, E132 duck, V148 see;
fixed 26 October, the audit's section 8, step 9).

    QT_QPA_PLATFORM=offscreen python tools/screenshots.py OUTPUT_FOLDER
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))
os.environ.setdefault("LEMMATRIX_SETTINGS", "Lemmatrix-screenshots")


def main(out: Path):
    from PySide6.QtWidgets import QApplication

    from lemmatrix import filters as fl
    from lemmatrix import matrix as mx
    from lemmatrix import storage
    from lemmatrix.ui.fields_dialog import FieldsDialog
    from lemmatrix.ui.filter_dialogs import ChooseDialog, ConfigureColumnsDialog, FilterForDialog
    from lemmatrix.ui.main_window import ALL_DATA, LEMMA_TAG, TAG_TAG, MainWindow
    from lemmatrix.ui.matrix_dialogs import ConfigureMatrixDialog, SpecDialog
    from lemmatrix.ui.token_dialog import Slot, TokenDialog

    out.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp())
    shutil.copy2(HERE / "samples" / "Sample.xml", work / "Sample.xml")
    shutil.copytree(HERE / "samples" / "Soundfiles", work / "Soundfiles")

    app = QApplication([])
    app.setStyle("Fusion")
    from PySide6.QtWidgets import QInputDialog, QMessageBox
    for name in ("information", "warning"):     # no message box may wait for a click here
        setattr(QMessageBox, name, staticmethod(lambda *a, **k: None))

    def exec_(box):                              # any other box takes its default button at once
        b = box.defaultButton() or (box.buttons()[0] if box.buttons() else None)
        box._shot_answer = b
        return int(box.standardButton(b)) if b is not None else 0
    QMessageBox.exec = exec_
    QMessageBox.clickedButton = lambda box: getattr(box, "_shot_answer", None)
    QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.No)
    QInputDialog.getItem = staticmethod(lambda p, t, l, items, *a, **k: (items[0], True))
    win = MainWindow()
    win.resize(1500, 900)
    win.show()

    def shot(widget, name):
        app.processEvents()
        widget.grab().save(str(out / name))
        print("saved", name)

    win.load_database(storage.load(work / "Sample.xml"))
    shot(win, "01-all-data.png")
    win.lemmas.select_row(win.doc.db.entry_by_ref("D009"))
    win.tabs.setCurrentIndex(LEMMA_TAG)
    shot(win, "02-lemma-tag-blank.png")
    cfg = win.config_for(LEMMA_TAG)
    cfg.x = [mx.Spec.citation(), mx.Spec(frozenset({"Singular"}), mx.LOOSE),
             mx.Spec(frozenset({"Plural"}), mx.EXACT)]
    win.refresh()
    shot(win, "03-lemma-tag-loose.png")
    win.switch_axes(LEMMA_TAG)
    shot(win, "04-lemma-tag-switched.png")
    win.switch_axes(LEMMA_TAG)
    win.lemmas.select_row(win.doc.db.entry_by_ref("V148"))
    win.tabs.setCurrentIndex(TAG_TAG)
    shot(win, "05-tag-tag-unconfigured.png")
    tcfg = win.config_for(TAG_TAG)
    tcfg.y = [mx.Spec(frozenset({"2SG.A"})), mx.Spec(frozenset({"3SG.A"}), mx.LOOSE)]
    tcfg.x = [mx.Spec(frozenset({"Future"})), mx.Spec(frozenset({"Imperative"})), mx.Spec(frozenset({"Indicative"}))]
    win.refresh()
    shot(win, "06-tag-tag.png")

    dlg = ConfigureMatrixDialog(win, win.doc.db, tcfg)
    dlg.show()
    shot(dlg, "07-configure-matrix.png")
    dlg.close()
    dlg = SpecDialog(win, win.doc.db, mx.Spec(frozenset({"Singular"}), mx.LOOSE))
    dlg.show()
    shot(dlg, "08-matrix-column.png")
    dlg.close()

    goat = win.doc.db.entry_by_ref("D009")
    idx = next(i for i, t in enumerate(goat.tokens) if "Frame 2" in t.tags)
    d = TokenDialog(win, [Slot(goat, idx)], 0)
    d.show()
    shot(d, "09-token-dialog.png")
    d.close()

    d = FieldsDialog(win, win.doc.db)
    d.show()
    d.widgets["lemma"].setCurrentRow(3)
    shot(d, "10-fields.png")
    d.close()

    d = FilterForDialog(win, "Phonetic", fl.TextFilter("deet"))
    d.show()
    shot(d, "11-filter-for.png")
    d.close()
    tags_col = next(c for c in win.all_table.model_.all_columns if c.key == "tags")
    d = ChooseDialog(win, "Tags", tags_col.tree(), {"Plural": 9, "Singular": 7},
                     fl.ChoiceFilter({"Plural"}), allow_exactly=True)
    d.show()
    shot(d, "12-choose.png")
    d.close()
    cols = win._lemma_columns()
    d = ConfigureColumnsDialog(win, [(c.key, c.title) for c in cols], win.lemmas.visible_keys())
    d.show()
    shot(d, "13-configure-columns.png")
    d.close()

    from lemmatrix import bulk
    from lemmatrix.ui import bulk_window as bw
    win.tabs.setCurrentIndex(ALL_DATA)
    win.open_bulk_edit()
    b = win.bulk_window
    b.resize(1360, 900)
    b.ops.setCurrentIndex(bw.REPLACE)
    b.r_field.setCurrentIndex(b.r_field.findData("f:Phonetic"))
    b.r_find.setText("ee")
    b.r_repl.setText("ææ")
    b.set_ticked([r for r in b.tables[bulk.TOKENS].visible_rows() if r.entry.ref == "D011"], False)
    b.preview()
    shot(b, "15-bulk-replace.png")
    b.set_ticked(b.tables[bulk.TOKENS].visible_rows(), True)
    b.ops.setCurrentIndex(bw.SHORTCUTS)
    b.s_which.setCurrentIndex(b.s_which.findData("pitch"))
    b.preview()
    shot(b, "16-bulk-pitch-error.png")
    b.levels.setCurrentIndex(0)
    b.ops.setCurrentIndex(bw.SET)
    shot(b, "17-bulk-lemmas.png")
    db = win.doc.db
    for ref in ("D011", "E132"):                 # empty some translations, for Predict to fill
        e = db.entry_by_ref(ref)
        win.doc.edit_entry(e, lambda en: [t.set("Translation", "", "en") for t in en.tokens[1:]],
                           "clear translations")
    b.levels.setCurrentIndex(1)
    b.ops.setCurrentIndex(bw.PREDICT)
    b.preview()
    shot(b, "23-bulk-predict.png")
    win.refresh()
    shot(win, "24-all-data-suggestions.png")
    goat = db.entry_by_ref("D009")              # a few typos, for the spelling views
    win.doc.edit_entry(goat, lambda en: (en.tokens[2].set("Translation", "of teh goat", "en"),
                                         en.tokens[4].set("Translation", "of the goatss", "en"),
                                         en.set("Gloss", "goatt", "en", True)), "typos")
    win.refresh()
    shot(win, "25-spelling-underlines.png")
    win.check_spelling()
    win.spelling_window.resize(900, 640)
    shot(win.spelling_window, "26-check-spelling.png")
    d = TokenDialog(win, [Slot(goat, 2)], 0)
    d.show()
    shot(d, "27-token-spelling.png")
    d.reject()
    win.spelling_window.close()
    win.doc.undo.undo()
    win.doc.undo.undo()
    win.doc.undo.undo()
    b.close()
    from lemmatrix.ui.dialogs import PreferencesDialog, TagStructureDialog
    goat = win.doc.db.entry_by_ref("D009")
    d = TokenDialog(win, [Slot(goat, 1)], 0)
    d.show()
    shot(d, "18-token-usual-tags.png")
    d.show_all_btn.setChecked(True)
    d.tags.buttons["Past"].setChecked(True)
    shot(d, "19-token-all-tags-unusual.png")
    d.reject()
    duck = win.doc.db.entry_by_ref("E132")
    d = TokenDialog(win, [Slot(duck, None, ("Singular", "Genitive"), explicit=True, defaults=True)], 0)
    d.show()
    d.translation.setFocus()
    shot(d, "22-token-suggestion.png")
    d.reject()
    d = TagStructureDialog(win, win.doc.db)
    d.show()
    shot(d, "20-tag-structure.png")
    d.close()
    d = PreferencesDialog(win, win.doc.db, win.prefs)
    d.show()
    shot(d, "21-settings-general.png")
    d.close()

    # utterances: the window and the dialogue (idea 7, stage 2)
    import numpy as np
    from lemmatrix import audio
    from lemmatrix.ui.utterances import UtteranceDialog
    clips = work / "clips"
    clips.mkdir()
    for n in ("hare ran", "where is he"):
        audio.write_wav(clips / f"{n}.wav", (0.1 * np.sin(np.arange(8000) / 9)).astype(np.float32), 8000, 16)
    uw = win.open_utterances()
    items = uw.import_files([str(p) for p in sorted(clips.glob("*.wav"))])
    for u, ph in zip(items, ("ʔəŋ kɒ ɗæær", "ɛ ŋəə")):
        win.doc.edit_entry(u, lambda x, ph=ph: x.token.set("Phonetic", ph))
    uw.resize(1300, 480)
    shot(uw, "28-utterances.png")
    d = UtteranceDialog(win, [Slot(u, 0) for u in items], 0, uw)
    d.show()
    shot(d, "29-utterance-dialog.png")
    d.reject()
    uw.close()

    big = HERE / "samples" / "Test-300.xml"
    if big.exists():                             # a copy: opening it writes its workspace
        (work / "big").mkdir()
        for f in big.parent.glob("Test-300.*"):
            shutil.copy2(f, work / "big" / f.name)
        win.load_database(storage.load(work / "big" / big.name))
        win.lemmas.select_row(win.doc.db.entries[0])
        win.tabs.setCurrentIndex(LEMMA_TAG)
        shot(win, "14-test-300-lemma-tag.png")
    win.doc.undo.setClean()
    win.doc._settings_dirty = False
    win.close()


if __name__ == "__main__":
    main(Path(sys.argv[1] if len(sys.argv) > 1 else "screenshots"))
