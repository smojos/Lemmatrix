# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders. Additional terms: NOTICE.md
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
    _install_crash_log(log)


def _install_crash_log(log: Path):
    """A crash inside Qt itself closes Lemmatrix silently, with no message box (Josh, 23 October:
    it closed while opening the sample database). faulthandler writes where Python was at that
    moment into lemmatrix-crash.log beside the error log, so it can be traced. The file is started
    afresh on each run, so it only ever holds the last run: empty after a run that ended normally."""
    import faulthandler
    try:
        fh = open(log.with_name("lemmatrix-crash.log"), "w", encoding="utf-8")
        faulthandler.enable(file=fh, all_threads=True)
        _install_crash_log.file = fh          # kept open for faulthandler while Lemmatrix runs
    except OSError:
        pass


def main() -> int:
    from PySide6.QtWidgets import QApplication, QMessageBox

    from .ui.main_window import MainWindow

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
    from .ui import ctrlspace
    app._ctrl_space = ctrlspace.install(app)            # Ctrl+Space plays from any field, any keyboard
    from .ui import shiftwheel
    app._shift_wheel = shiftwheel.install(app)          # Shift + wheel scrolls sideways
    from .ui import rightshift
    app._right_shift = rightshift.install(app)          # Right Shift+A / B play α / β
    from .ui import symbols
    app._symbols = symbols.install(app)                 # Σymbols in every text field's right-click menu
    from .ui import keyboards
    app._keyboards = keyboards.install(app)             # a field's own keyboard (idea 43; off until set up)

    from .ui import splash as splashmod
    splash = splashmod.show(app)                        # until the database is open (a dialogue closes it)
    win = MainWindow()
    path = start_path(sys.argv[1:], win.prefs)
    win.show()
    if splash is not None:
        splash.raise_()
    if path and Path(path).exists():
        win.open_file(path)                 # warns if it's open on another computer
    splashmod.finish(app, splash, win, win.prefs.splash_seconds)
    if not win.doc.db.path:
        dlg = welcome_box(win)
        dlg.exec()
        win.prefs.show_welcome = dlg.every_start.isChecked()   # after the first start: "never" unless selected
        if dlg.choice == "sample":
            win.open_sample()
        elif dlg.choice == "open":
            win.open_file()
        elif dlg.choice == "new":
            win.new_file()
        elif dlg.choice == "recent":
            win.open_file(dlg.path)
    return app.exec()


def start_path(args: list[str], prefs) -> str:
    """The database to open at start-up: one given on the command line; otherwise the most recent,
    unless the welcome window comes first, on the very first start and, when selected, on every
    start (Josh, 23 October)."""
    if args:
        return args[0]
    return "" if prefs.welcome_mode in ("", "always") else prefs.last_file

def welcome_box(win):
    """The welcome window (ui/welcome.py): Josh's question first, with Yes (a copy of the sample)
    as the default (IDEAS.md idea 52, 23 October); the three databases opened most recently on
    this computer under it (idea 51)."""
    from .ui.main_window import SAMPLE
    from .ui.welcome import WelcomeDialog
    recent = [r for r in win.prefs.recent if Path(r["path"]).exists()][:3]
    return WelcomeDialog(win, recent, SAMPLE.exists(), win.prefs.show_welcome)

if __name__ == "__main__":
    sys.exit(main())
