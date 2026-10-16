"""Render the main windows offscreen to PNG files (for checking the layout).

    QT_QPA_PLATFORM=offscreen python tools/screenshots.py OUTPUT_FOLDER
"""

from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))


def main(out: Path):
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication

    from lemmatrix import storage
    from lemmatrix.ui.main_window import MainWindow
    from lemmatrix.ui.matrix_view import ALL_DATA, ENTRY_TAG, TAG_TAG
    from lemmatrix.ui.token_dialog import Slot, TokenDialog
    from lemmatrix.ui.dialogs import TagStructureDialog, EntryDialog, DisplaySetupDialog

    out.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp())
    shutil.copy2(HERE / "samples" / "Sample.xml", work / "Sample.xml")
    shutil.copytree(HERE / "samples" / "Soundfiles", work / "Soundfiles")

    app = QApplication([])
    app.setStyle("Fusion")
    win = MainWindow()
    win.load_database(storage.load(work / "Sample.xml"))
    win.resize(1500, 880)
    win.show()
    app.processEvents()

    def shot(widget, name):
        app.processEvents()
        widget.grab().save(str(out / name))
        print("saved", name)

    win.tabs.setCurrentIndex(ENTRY_TAG)
    shot(win, "1-entry-tag.png")
    win.matching.setCurrentIndex(1)
    shot(win, "2-entry-tag-includes.png")
    win.matching.setCurrentIndex(0)
    win.switch_axes()
    shot(win, "3-entry-tag-switched.png")
    win.switch_axes()
    verb = win.doc.db.entry_by_ref("V001")
    win.lemmas.select_entry(verb)
    win.tabs.setCurrentIndex(TAG_TAG)
    shot(win, "4-tag-tag.png")
    win.tabs.setCurrentIndex(ALL_DATA)
    shot(win, "5-all-data.png")

    goat = win.doc.db.entry_by_ref("D001")
    idx = next(i for i, t in enumerate(goat.tokens) if "f2" in t.tags)
    dlg = TokenDialog(win, [Slot(goat, idx)], 0)
    dlg.show()
    shot(dlg, "6-token-dialog.png")
    dlg.close()

    v = win.doc.db.entry_by_ref("V001")
    dlg = TokenDialog(win, [Slot(v, None, ("3SG.A", "1SG.O", "Past"), explicit=True, defaults=True)], 0)
    dlg.show()
    shot(dlg, "7-token-dialog-new-verb.png")
    dlg.close()

    d = TagStructureDialog(win, win.doc.db)
    d.show()
    shot(d, "8-tag-structure.png")
    d.close()
    d = EntryDialog(win, win.doc.db)
    d.show()
    d.category.setCurrentIndex(d.category.findData("D"))
    shot(d, "9-add-entry.png")
    d.close()
    win.doc._settings_dirty = False
    win.doc.undo.setClean()
    win.close()


if __name__ == "__main__":
    main(Path(sys.argv[1] if len(sys.argv) > 1 else "screenshots"))
