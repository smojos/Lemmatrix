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
                              "Something unexpected happened. If Lemmatrix still responds, save "
                              "(Ctrl+S): the previous version stays in the Backups folder, in case "
                              "the save isn't right. Then "
                              f"send Claude the details below (also kept in {log.name}).")
            box.setDetailedText(text)
            box.exec()
        except Exception:
            pass

    sys.excepthook = hook


def main() -> int:
    from PySide6.QtWidgets import QApplication, QMessageBox

    from .ui.main_window import SAMPLE, MainWindow

    if sys.platform.startswith("win"):
        # Lets Windows show Lemmatrix's own icon on the taskbar instead of Python's.
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Lemmatrix.Lemmatrix")
        except (AttributeError, OSError):
            pass
    app = QApplication(sys.argv)
    _install_error_handler()
    from . import lock as lockmod
    app._running_lock = lockmod.single_instance()       # held until the program ends
    if app._running_lock is None:
        QMessageBox.warning(None, "Lemmatrix", lockmod.ANOTHER_RUNNING)
    app.setApplicationName("Lemmatrix")
    app.setOrganizationName("Lemmatrix")
    app.setStyle("Fusion")
    from .ui.icons import app_icon
    app.setWindowIcon(app_icon())

    win = MainWindow()
    path = sys.argv[1] if len(sys.argv) > 1 else win.prefs.last_file
    win.show()
    if path and Path(path).exists():
        win.open_file(path)                 # warns if it's open on another computer
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
