# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders
"""Josh's debug list of 20 October: no jolt on saving, pitch drawings cut off with an ellipsis in
narrow columns, Bulk edit opening inside the screen and keeping its size."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["LEMMATRIX_SETTINGS"] = "Lemmatrix-tests"

from PySide6.QtCore import QEvent, QObject, QRectF  # noqa: E402
from PySide6.QtGui import QColor, QImage, QPainter  # noqa: E402
from PySide6.QtWidgets import QApplication, QSplitter  # noqa: E402

from test_ui import app, win  # noqa: E402,F401


def _settle():
    for _ in range(10):
        QApplication.processEvents()


def test_saving_doesnt_move_the_panes(win):
    win.resize(1400, 780)
    win.show()
    _settle()
    before = [s.sizes() for s in win.findChildren(QSplitter)]
    for _ in range(2):
        win.doc.settings_changed()
        assert win.save()
        _settle()
    assert [s.sizes() for s in win.findChildren(QSplitter)] == before


def test_saving_doesnt_rebuild_the_session_chips(win):
    class Spy(QObject):
        n = 0

        def eventFilter(self, o, e):
            if e.type() == QEvent.ChildRemoved:
                Spy.n += 1
            return False
    spy = Spy()
    rows = list(win.sess_rows.values())
    for r in rows:
        r.installEventFilter(spy)
    win.doc.settings_changed()
    win.save()
    assert Spy.n == 0


def _ink_right_of(text: str, width: int, elide: bool) -> tuple[bool, bool]:
    from lemmatrix.ui.widgets import draw_pitch
    img = QImage(300, 30, QImage.Format_ARGB32)
    img.fill(QColor("white"))
    p = QPainter(img)
    draw_pitch(p, QRectF(0, 2, width, 26), text, 1, 5, color=QColor("black"), unit=8, elide=elide)
    p.end()
    past = any(img.pixelColor(x, y).value() < 128 for x in range(width + 2, 300) for y in range(30))
    inside = any(img.pixelColor(x, y).value() < 128 for x in range(0, width) for y in range(30))
    return past, inside


def test_pitch_drawing_is_cut_off_in_a_narrow_column(app):
    long = "13 31 55 11 13 31 55 11 13 31"
    assert _ink_right_of(long, 60, elide=False)[0]          # the old way: it spilled over
    past, inside = _ink_right_of(long, 60, elide=True)
    assert not past and inside


def test_bulk_edit_opens_inside_a_small_screen(win):
    win.bulk_window = None
    win.prefs.q.remove("window/bulk")
    win.open_bulk_edit()
    bw = win.bulk_window
    _settle()
    a = bw.screen().availableGeometry()
    assert bw.frameGeometry().bottom() <= a.bottom() and bw.height() <= a.height()
    bw.close()


def test_bulk_edit_keeps_its_size_in_a_new_window(win):
    win.open_bulk_edit()
    bw = win.bulk_window
    _settle()
    bw.resize(1100, 520)
    _settle()
    bw.close()
    win.bulk_window = None
    win.open_bulk_edit()
    _settle()
    assert win.bulk_window.height() == 520
    win.bulk_window.close()


def test_a_saved_size_bigger_than_the_screen_is_brought_inside(win):
    from lemmatrix.ui.bulk_window import BulkEditWindow
    win.open_bulk_edit()
    bw = win.bulk_window
    _settle()
    bw.resize(1100, 2000)                       # as an old default could have left it
    bw._winstate.save()
    bw.close()
    win.bulk_window = BulkEditWindow(win)
    win.bulk_window.show()
    _settle()
    a = win.bulk_window.screen().availableGeometry()
    assert win.bulk_window.frameGeometry().bottom() <= a.bottom()
    win.bulk_window.close()


def test_questions_buttons_say_what_the_message_says(app, monkeypatch):
    """Josh, 20 October: Reset to defaults talked of OK and Cancel over Yes and No buttons."""
    from PySide6.QtWidgets import QMessageBox

    from lemmatrix.ui import widgets
    seen = []

    def exec_(box):
        seen.append((box.text(), [b.text() for b in box.buttons()]))
        return 0
    monkeypatch.setattr(QMessageBox, "exec", exec_)
    assert not widgets.real_ask(None, "Reset to defaults", "Replace the genre with the defaults?",
                                "Reset to defaults")
    text, buttons = seen[0]
    assert sorted(buttons) == ["Cancel", "Reset to defaults"]


def test_no_message_names_a_button_it_doesnt_have():
    """The Yes/No questions never tell the user to click OK, Cancel, Save…"""
    import re
    from pathlib import Path
    src = Path(__file__).resolve().parent.parent / "lemmatrix"
    for f in src.rglob("*.py"):
        code = f.read_text(encoding="utf-8")
        for m in re.finditer(r"QMessageBox\.question\(", code):
            i, depth = m.end(), 1
            while depth:
                depth += {"(": 1, ")": -1}.get(code[i], 0)
                i += 1
            call = code[m.start():i]
            buttons = set(re.findall(r"QMessageBox\.(\w+)", call)) - {"question"} or {"Yes", "No"}
            named = set(re.findall(r"\b(?:click|press|choose) (OK|Yes|No|Cancel|Save|Discard|Ignore)\b",
                                   call))
            assert named <= buttons, f"{f.name}: {call[:120]}"
            assert "Ignore" not in buttons, f"{f.name}: an Ignore button never matches a question"


def test_deleting_a_lemmas_last_token_in_all_data_doesnt_crash(win, monkeypatch):
    """Josh, 21 October: deleting a token just added (the last of its lemma) in All data threw
    IndexError while painting, before the rows were rebuilt."""
    from PySide6.QtWidgets import QMessageBox

    from lemmatrix.model import Token
    errors = []
    monkeypatch.setattr("sys.excepthook", lambda *a: errors.append(a))
    win.resize(1400, 780)
    win.show()
    win.tabs.setCurrentIndex(0)
    _settle()
    e = win.doc.db.entries[0]
    win.doc.edit_entry(e, lambda en: en.tokens.append(Token(tags=["Example 1"])), "add")
    _settle()
    t = win.all_table
    row = next(r for r in t.model_.rows if r.entry is e and r.index == len(e.tokens) - 1)
    t.select_row(row)
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.Yes)
    n = len(e.tokens)
    win._refresh_timer.stop = lambda: None
    win.schedule_refresh = lambda delay=0: None     # as if the refresh hadn't come yet
    win.delete_token()
    assert len(e.tokens) == n - 1
    t.viewport().repaint()
    for r in t.model_.rows:                          # every row still points at a token
        assert r.index < len(r.entry.tokens)
    _settle()
    assert not errors
