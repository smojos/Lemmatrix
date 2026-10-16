"""Render the main windows and dialogues offscreen to PNG files (for checking layouts).

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
    win = MainWindow()
    win.resize(1500, 900)
    win.show()

    def shot(widget, name):
        app.processEvents()
        widget.grab().save(str(out / name))
        print("saved", name)

    win.load_database(storage.load(work / "Sample.xml"))
    shot(win, "01-all-data.png")
    win.lemmas.select_row(win.doc.db.entry_by_ref("D001"))
    win.tabs.setCurrentIndex(LEMMA_TAG)
    shot(win, "02-lemma-tag-automatic.png")
    cfg = win.config_for(LEMMA_TAG)
    cfg.x = [mx.Spec.citation(), mx.Spec(frozenset({"Singular"}), mx.LOOSE),
             mx.Spec(frozenset({"Plural"}), mx.EXACT)]
    win.refresh()
    shot(win, "03-lemma-tag-loose.png")
    win.switch_axes(LEMMA_TAG)
    shot(win, "04-lemma-tag-switched.png")
    win.switch_axes(LEMMA_TAG)
    win.lemmas.select_row(win.doc.db.entry_by_ref("V001"))
    win.tabs.setCurrentIndex(TAG_TAG)
    shot(win, "05-tag-tag-unconfigured.png")
    tcfg = win.config_for(TAG_TAG)
    tcfg.y = [mx.Spec(frozenset({"1SG.A"})), mx.Spec(frozenset({"3SG.A"}), mx.LOOSE)]
    tcfg.x = [mx.Spec(frozenset({"1SG.O"})), mx.Spec(frozenset({"3SG.O"})), mx.Spec(frozenset({"3SG.A"}))]
    win.refresh()
    shot(win, "06-tag-tag.png")

    dlg = ConfigureMatrixDialog(win, win.doc.db, tcfg)
    dlg.show()
    shot(dlg, "07-configure-matrix.png")
    dlg.close()
    dlg = SpecDialog(win, win.doc.db, "NOUN", mx.Spec(frozenset({"Singular"}), mx.LOOSE))
    dlg.show()
    shot(dlg, "08-matrix-column.png")
    dlg.close()

    goat = win.doc.db.entry_by_ref("D001")
    idx = next(i for i, t in enumerate(goat.tokens) if "f2" in t.tags)
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

    big = HERE / "samples" / "Test-300.xml"
    if big.exists():
        win.load_database(storage.load(big))
        win.lemmas.select_row(win.doc.db.entries[0])
        win.tabs.setCurrentIndex(LEMMA_TAG)
        shot(win, "14-test-300-lemma-tag.png")
    win.doc.undo.setClean()
    win.doc._settings_dirty = False
    win.close()


if __name__ == "__main__":
    main(Path(sys.argv[1] if len(sys.argv) > 1 else "screenshots"))
