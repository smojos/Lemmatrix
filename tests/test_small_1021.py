# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders. Additional terms: NOTICE.md
"""Josh's tweaks of 21 October: the splash screen's corners and how long it stays."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["LEMMATRIX_SETTINGS"] = "Lemmatrix-tests"

from test_ui import app, win  # noqa: E402,F401


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


def test_questions_button_opens_questions(app, monkeypatch):
    from lemmatrix.ui.main_window import MainWindow
    w = MainWindow()
    opened = []
    monkeypatch.setattr(w, "open_questions", lambda: opened.append(1))
    assert not w.questions_btn.icon().isNull()
    w.questions_btn.click()
    assert opened
    w.close()


def test_new_day_asks_to_keep_or_reset_the_session(app, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    from lemmatrix.model import Person
    from lemmatrix.ui import chiprow as chips
    from lemmatrix.ui.main_window import MainWindow
    w = MainWindow()
    w.doc.db.path = "x.xml"                       # as if opened from a file
    w.doc.db.metadata.researchers.append(Person("RS1"))
    w.sess_rows[chips.RESEARCHERS].set_keys(["RS1"])
    asked = []

    def answer(which):
        def exec_(box):
            asked.append(box.text())
            box.clickedButton = lambda: next(b for b in box.buttons() if b.text() == which)
        return exec_
    monkeypatch.setattr(QMessageBox, "exec", answer("Keep"))
    w._session_last_day = "2026-10-20"
    monkeypatch.setattr("lemmatrix.ui.main_window.today", lambda: "2026-10-21")
    w._remind_new_day()
    assert asked and w.sess_rows[chips.RESEARCHERS].keys == ["RS1"]
    monkeypatch.setattr(QMessageBox, "exec", answer("Reset"))
    w._remind_new_day()
    assert w.sess_rows[chips.RESEARCHERS].keys == []
    asked.clear()
    w._session_last_day = "2026-10-21"            # the same day: nothing asked
    w.sess_rows[chips.RESEARCHERS].set_keys(["RS1"])
    w._remind_new_day()
    assert not asked
    w.doc.db.path = ""
    w.close()


def test_splash_says_entering(app):
    from lemmatrix.ui import splash
    s = splash.show(app)
    assert isinstance(s, splash.Splash) and splash.LOADING == "Entering Lemmatrix..."
    s.grab()
    s.close()


def test_dragging_a_matrix_column_reorders_its_lines(win):
    from lemmatrix import matrix as mx
    from lemmatrix.ui.main_window import LEMMA_TAG
    win.tabs.setCurrentIndex(LEMMA_TAG)
    cols = [mx.Spec.citation(), mx.Spec(frozenset({"Plural"}), mx.EXACT),
            mx.Spec(frozenset({"Singular"}), mx.EXACT)]
    win.config_for(LEMMA_TAG).x = list(cols)
    win.refresh()
    hh = win.lt_view.horizontalHeader()
    assert hh.sectionsMovable()
    hh.moveSection(0, 2)                          # as a drag does
    assert win.config_for(LEMMA_TAG).x == [cols[1], cols[2], cols[0]]
    assert [hh.logicalIndex(i) for i in range(hh.count())] == [0, 1, 2]   # the header is the order
    win.switch_axes(LEMMA_TAG)                    # lemmas along the top: not movable
    assert not win.lt_view.horizontalHeader().sectionsMovable()
