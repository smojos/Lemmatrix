"""Start Lemmatrix:  python -m lemmatrix [database.xml]"""

from __future__ import annotations

import sys
from pathlib import Path


def _install_error_handler():
    """Show unexpected errors in a message box and keep a log next to the program."""
    import traceback

    log = Path(__file__).resolve().parent.parent / "lemmatrix-errors.log"

    def hook(kind, value, tb):
        text = "".join(traceback.format_exception(kind, value, tb))
        sys.__stderr__.write(text)
        try:
            with open(log, "a", encoding="utf-8") as fh:
                import datetime
                fh.write(f"--- {datetime.datetime.now():%Y-%m-%d %H:%M:%S}\n{text}\n")
        except OSError:
            pass
        try:
            from PySide6.QtWidgets import QMessageBox
            box = QMessageBox(QMessageBox.Critical, "Lemmatrix: something went wrong",
                              "Something unexpected happened. If Lemmatrix still responds, use "
                              "File → Save as to keep your recent changes under a new name. Then "
                              f"send Claude the details below (also kept in {log.name}).")
            box.setDetailedText(text)
            box.exec()
        except Exception:
            pass

    sys.excepthook = hook


def main() -> int:
    from PySide6.QtWidgets import QApplication, QMessageBox

    from . import storage
    from .ui.main_window import SAMPLE, MainWindow

    app = QApplication(sys.argv)
    _install_error_handler()
    app.setApplicationName("Lemmatrix")
    app.setOrganizationName("Lemmatrix")
    app.setStyle("Fusion")

    win = MainWindow()
    path = sys.argv[1] if len(sys.argv) > 1 else win.prefs.last_file
    if path and Path(path).exists():
        try:
            db = storage.load(path)
            win.prefs.last_file = path
            win.load_database(db)
        except (storage.FormatError, OSError) as exc:
            QMessageBox.warning(win, "Lemmatrix", f"Couldn't open {Path(path).name}:\n{exc}")
    win.show()
    if not win.doc.db.path:
        box = QMessageBox(win)
        box.setWindowTitle("Welcome to Lemmatrix")
        box.setText("Open a database to start, or try a copy of the sample database.")
        sample = box.addButton("Open a copy of the sample", QMessageBox.AcceptRole)
        opened = box.addButton("Open a database…", QMessageBox.ActionRole)
        new = box.addButton("New database…", QMessageBox.ActionRole)
        box.addButton("Close", QMessageBox.RejectRole)
        if not SAMPLE.exists():
            sample.setEnabled(False)
        box.exec()
        if box.clickedButton() is sample:
            win.open_sample()
        elif box.clickedButton() is opened:
            win.open_file()
        elif box.clickedButton() is new:
            win.new_file()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
