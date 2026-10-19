"""19 October fixes: Edit in the lines' menu, Ctrl+Space with IPA keyboards, search marks."""

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["LEMMATRIX_SETTINGS"] = "Lemmatrix-tests"

from test_texts import _add_text, app, win  # noqa: F401  (fixtures)


def test_search_spans_ignore_diacritics_and_capitals():
    from lemmatrix.ui import searchmark as sm
    q = sm.fold_query("Deet")
    assert sm.spans("ɗɪɪtʰ deet", q) == [(6, 10)]
    assert sm.spans("dɪɪtʰ", q) == [(0, 5)]                     # the ʰ goes with the match
    assert sm.spans("bə́ə bə", sm.fold_query("bə")) == [(0, 2), (4, 6)]
    assert sm.spans("bə\u0301a", sm.fold_query("bə")) == [(0, 3)]          # a combining mark too
    assert sm.spans("abc", "") == [] and sm.spans("", "a") == []


def test_line_menu_has_edit_field_and_edit_text(win, tmp_path, monkeypatch):
    from PySide6.QtCore import QPoint
    from PySide6.QtWidgets import QMenu
    from lemmatrix.ui import texts as tx
    uw, t = _add_text(win, tmp_path, monkeypatch)
    p = uw.texts
    seen = {}

    class Menu(QMenu):
        def exec(self, *a):
            seen.update({x.text(): x for x in self.actions() if x.text()})
    monkeypatch.setattr(tx, "QMenu", Menu)
    ln = p.lines.rows[1]
    p.lines.menu_key = "Translation:en"
    p._line_menu(ln, QPoint(0, 0))
    title = p.lines.title("Translation:en")
    assert f"Edit {title}" in seen and "Edit text…" in seen
    seen[f"Edit {title}"].trigger()
    assert p.lines._editor is not None and p.lines._editor[2] == "Translation:en"
    p.lines._close_editor(commit=False)
    p.lines.menu_key = ""
    seen.clear()
    p._line_menu(ln, QPoint(0, 0))
    assert not seen["Edit field"].isEnabled()


def _type_space(widget, mods):
    from PySide6.QtCore import QEvent, Qt
    from PySide6.QtGui import QKeyEvent
    from PySide6.QtWidgets import QApplication
    for t in (QEvent.ShortcutOverride, QEvent.KeyPress):
        QApplication.sendEvent(widget, QKeyEvent(t, Qt.Key_Space, mods, " "))


def test_ctrl_space_plays_even_when_the_keyboard_drops_ctrl(win, app, monkeypatch):
    from PySide6.QtCore import Qt
    from lemmatrix.ui import ctrlspace
    ctrl = {"on": True, "shift": False}
    f = ctrlspace.CtrlSpaceFilter(app, held_fn=lambda: (ctrl["on"], ctrl["shift"], False))
    app.installEventFilter(f)
    played = []
    monkeypatch.setattr(win, "play_selected", lambda *a: played.append("token"))
    monkeypatch.setattr(win, "play_selected_pitch", lambda *a: played.append("pitch"))
    win.play_action.triggered.disconnect()
    win.play_action.triggered.connect(lambda *a: win.play_selected())
    pitch = next(a for a in win.findChildren(type(win.play_action))
                 if ctrlspace.PLAY_PITCH in a.shortcuts())
    pitch.triggered.disconnect()
    pitch.triggered.connect(lambda *a: win.play_selected_pitch())
    try:
        search = win.all_search
        search.setText("ab")
        _type_space(search, Qt.NoModifier)            # what Keyman sends: a space, Ctrl let go
        assert search.text() == "ab" and played == ["token"]
        f._last = 0
        ctrl["shift"] = True
        _type_space(search, Qt.NoModifier)
        assert search.text() == "ab" and played == ["token", "pitch"]
        ctrl.update(on=False, shift=False)            # a plain space still types
        search.setCursorPosition(2)
        _type_space(search, Qt.NoModifier)
        assert search.text() == "ab " and len(played) == 2
    finally:
        app.removeEventFilter(f)


def test_marks_drawn_in_a_grid_cell(win, app):
    """The grids paint the search's marks (a smoke test: the delegate runs with a search)."""
    from PySide6.QtGui import QImage, QPainter
    from lemmatrix.ui.searchmark import SearchDelegate
    t = win.lemmas
    assert isinstance(t.itemDelegate(), SearchDelegate)
    t.proxy.set_search(t.proxy.index(0, 1).data() or "a")
    idx = t.proxy.index(0, 1)
    img = QImage(300, 30, QImage.Format_ARGB32)
    img.fill(0xFFFFFFFF)
    p = QPainter(img)
    from PySide6.QtWidgets import QStyleOptionViewItem
    opt = QStyleOptionViewItem()
    opt.rect = img.rect()
    opt.widget = t
    t.itemDelegate(idx).paint(p, opt, idx)
    p.end()
    yellowish = sum(1 for x in range(0, 300, 3) for y in range(0, 30, 3)
                    if (c := img.pixelColor(x, y)).blue() < 150 and c.red() > 200 and c.green() > 180)
    assert yellowish > 5
