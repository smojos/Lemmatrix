# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders. Additional terms: NOTICE.md
"""The audit of 25 October 2026, B13 and B14 (claude/AUDIT.md): the ɛλicit review's keys and
closing it when applying fails. On the ɛλicit test database, as tests/test_elicit.py."""

from lemmatrix import elicit as el
from test_elicit import _items, _response, db, win  # noqa: F401  (fixtures and helpers)


def _review(win, tmp_path):
    from lemmatrix.ui import elicit_dialogs as ed
    db = win.doc.db
    items = _items(db)
    req = el.new_request(db, items, "SP1", "RS1", "fr")
    el.write_request(db, req, items)
    st = el.receive(db, _response(el.stored_requests(db.path)[0], tmp_path / "r.zip"))
    dlg = ed.ReviewDialog(win, st)
    dlg.autoplay.setChecked(False)
    return dlg


def test_review_keys_work_with_the_table_focused(win, tmp_path, monkeypatch):
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    dlg = _review(win, tmp_path)
    played = []
    monkeypatch.setattr(dlg, "play_new", lambda *a: played.append(1))
    dlg.show()
    dlg.table.setFocus()
    dlg.table.setCurrentCell(0, 1)
    n0 = dlg.st.request.cards[0].n
    QTest.keyClick(dlg.table, Qt.Key_A)
    assert dlg.decisions.get(n0) == el.APPROVED     # never reached the dialogue before
    dlg.table.setCurrentCell(1, 1)
    n1 = dlg.st.request.cards[1].n
    QTest.keyClick(dlg.table, Qt.Key_R)
    assert dlg.decisions.get(n1) == el.REJECTED
    QTest.keyClick(dlg.table, Qt.Key_Space)
    assert played
    dlg.decisions.clear()
    dlg.reject()


def test_review_can_close_when_applying_fails(win, tmp_path, monkeypatch):
    from lemmatrix.ui import widgets
    dlg = _review(win, tmp_path)
    monkeypatch.setattr(dlg, "apply", lambda: False)
    answers = [False, True]                         # Keep reviewing, then Close the review
    monkeypatch.setattr(widgets, "ask", lambda *a, **k: answers.pop(0))
    dlg.show()
    dlg.reject()
    assert dlg.isVisible()                          # kept open
    dlg.reject()
    assert not dlg.isVisible()                      # closed: before, it could never close


def test_a_refreshed_sign_in_is_stored_on_the_main_thread(win, monkeypatch):
    """B23: the background Drive check wrote the refreshed token into the settings from its own
    thread; it now hands it over and the main thread stores it."""
    import threading
    import time

    from PySide6.QtWidgets import QApplication

    from lemmatrix import cloud_keys, gdrive
    from test_elicit import FakeDrive
    db = win.doc.db
    drive = FakeDrive()
    items = _items(db)[:1]
    req = el.new_request(db, items, "SP1", "RS1", "fr")
    el.publish_drive(db, req, items, drive, "KEY")
    where = []

    class Prefs:                                  # records which thread stores the token
        def __init__(self, real):
            self.__dict__["_real"] = real

        def __getattr__(self, name):
            return getattr(self._real, name)

        def __setattr__(self, name, value):
            if name == "google_token":
                where.append(threading.current_thread() is threading.main_thread())
            setattr(self._real, name, value)

    def fake_drive(token, on_token=None):
        on_token({"refresh_token": "R", "access_token": "NEW"})   # refreshed during the check
        return drive
    monkeypatch.setattr(cloud_keys, "google_ready", lambda: True)
    monkeypatch.setattr(gdrive, "Drive", fake_drive)
    win.prefs.google_token = {"refresh_token": "R"}
    win.prefs = Prefs(win.prefs)
    win.check_elicit_drive()
    for _ in range(150):
        QApplication.processEvents()
        if not win._elicit_checking:
            break
        time.sleep(0.02)
    assert where == [True]                        # stored, and on the main thread
    assert win.prefs.google_token.get("access_token") == "NEW"
    win.prefs = win.prefs._real
