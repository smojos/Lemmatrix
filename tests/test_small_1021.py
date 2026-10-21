# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders
"""Josh's tweaks of 21 October: the splash screen's corners and how long it stays."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["LEMMATRIX_SETTINGS"] = "Lemmatrix-tests"

from test_ui import app  # noqa: E402,F401


def test_splash_has_rounded_corners(app):
    from lemmatrix.ui import splash
    img = splash.pixmap().toImage()
    assert img.pixelColor(0, 0).alpha() == 0                     # the corner is cut off
    assert img.pixelColor(img.width() // 2, img.height() // 2).alpha() == 255


def test_splash_stays_for_its_minimum_time(app):
    import time
    from PySide6.QtWidgets import QApplication, QWidget
    from lemmatrix.ui import splash
    s = splash.show(app)
    w = QWidget()
    w.show()
    splash.finish(app, s, w, 1.0)
    QApplication.processEvents()
    assert s.isVisible()                                         # still up: the time isn't over
    end = time.monotonic() + 4
    while s.isVisible() and time.monotonic() < end:
        QApplication.processEvents()
        time.sleep(0.02)
    assert not s.isVisible()
    s2 = splash.show(app)
    splash.finish(app, s2, w, 0.0)                               # as short as possible
    QApplication.processEvents()
    assert not s2.isVisible()


def test_splash_seconds_setting():
    from lemmatrix.ui.prefs import Prefs
    p = Prefs()
    p.splash_seconds = 9
    assert p.splash_seconds == 5.0
    p.splash_seconds = 1.5
    assert p.splash_seconds == 1.5
    p.q.remove("display/splash_seconds")
    assert p.splash_seconds == 2.5


def test_filter_for_wording_keys_and_size(app):
    from PySide6.QtWidgets import QWidget
    from lemmatrix import filters as fl
    from lemmatrix.ui.filter_dialogs import FilterForDialog
    parent = QWidget()
    d = FilterForDialog(parent, "Gloss (en)")
    texts = {m: rb.text() for m, rb in d.radios.items()}
    assert texts == {fl.ANYWHERE: "&Anywhere", fl.START: "&Beginning", fl.WHOLE: "&Discrete",
                     fl.END: "&End", fl.REGEX: "Rege&X"}
    assert d.case.text() == "Mat&Ch cAsE" and d.diacritics.text() == "Match &Fûnkỹ stṵff"
    assert d.width() == d.sizeHint().width()


def test_lightbulb_switches_the_theme(app, tmp_path, monkeypatch):
    from lemmatrix.ui import theme
    from lemmatrix.ui.main_window import MainWindow
    w = MainWindow()
    before = theme.dark()
    w.theme_btn.click()
    assert theme.dark() != before and w.prefs.theme == ("dark" if not before else "light")
    w.theme_btn.click()
    assert theme.dark() == before
    w.close()


def test_current_session_codes_and_width(app):
    from PySide6.QtWidgets import QApplication
    from lemmatrix.model import Location, Person
    from lemmatrix.ui import chiprow as chips
    from lemmatrix.ui.main_window import MainWindow
    w = MainWindow()
    w.resize(1900, 980)
    w.show()
    QApplication.processEvents()
    md = w.doc.db.metadata
    md.participants += [Person(f"SP{i}") for i in range(1, 13)]
    md.locations += [Location("Ethiopia", "ET")]
    rows = w.sess_rows
    rows[chips.LOCATIONS].set_keys(["ET"])
    narrow = w.sess_panel.width()
    assert rows[chips.LOCATIONS].flow.itemAt(0).widget().text() == "ET"       # the code, not Ethiopia
    rows[chips.PARTICIPANTS].set_keys(["SP1", "SP2", "SP3", "SP4"])
    for _ in range(3):
        QApplication.processEvents()
    wider = w.sess_panel.width()
    assert wider > narrow                                                    # grows with its chips
    rows[chips.PARTICIPANTS].set_keys([f"SP{i}" for i in range(1, 13)])
    for _ in range(3):
        QApplication.processEvents()
    assert w.sess_panel.width() <= int(w.right_split.width() * w.SESSION_MAX) + 1   # a third at most
    assert rows[chips.PARTICIPANTS].height() > rows[chips.RESEARCHERS].height()   # then wraps
    w.close()
