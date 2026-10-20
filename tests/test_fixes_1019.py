# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders
"""19 October fixes: Edit in the lines' menu, Ctrl+Space with IPA keyboards, search marks."""

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["LEMMATRIX_SETTINGS"] = "Lemmatrix-tests"

from test_texts import _add_text, app, win  # noqa: F401  (fixtures)


def test_search_spans_ignore_diacritics_and_capitals():
    from lemmatrix.ui import searchmark as sm
    q = sm.fold_query("Dɪɪt")
    assert sm.spans("ɗɪɪtʰ dɪɪt", q) == [(6, 10)]
    assert sm.spans("dɪɪtʰ", q) == [(0, 5)]                     # the ʰ goes with the match
    assert sm.spans("bə́ə bə", sm.fold_query("bə")) == [(0, 3), (5, 7)]
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
    win.show()
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


# ---- 19 October, second list ------------------------------------------------------------

def test_a_closed_token_dialogue_doesnt_take_ctrl_space(win, app, monkeypatch):
    """A hidden dialogue under the main window kept its Ctrl+Space: it played its last token."""
    from PySide6.QtGui import QKeySequence, QShortcut
    from PySide6.QtWidgets import QDialog
    from lemmatrix.ui import ctrlspace
    old = QDialog(win)
    stale = []
    QShortcut(QKeySequence("Ctrl+Space"), old, lambda: stale.append(1))
    played = []
    win.play_action.triggered.disconnect()
    win.play_action.triggered.connect(lambda *a: played.append(1))
    win.show()
    assert ctrlspace.run_shortcut(win.all_search, pitch=False)
    assert played == [1] and stale == []


def test_selected_rows_keep_a_cells_own_colour(win):
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QColor, QPalette
    from PySide6.QtWidgets import QStyleOptionViewItem
    t = win.all_table
    keys = t.visible_keys()
    col = keys.index("file")
    for r in range(t.proxy.rowCount()):
        idx = t.proxy.index(r, col)
        fg = idx.data(Qt.ForegroundRole)
        if fg is not None:
            break
    opt = QStyleOptionViewItem()
    t.itemDelegate(idx).initStyleOption(opt, idx)
    assert QColor(opt.palette.color(QPalette.HighlightedText)) == QColor(fg)


def test_bulk_filter_after_preview_doesnt_touch_the_model_mid_filter(win, app):
    from PySide6.QtWidgets import QApplication
    from lemmatrix import bulk, filters as fl
    from lemmatrix.ui import bulk_window as bw
    goat = win.doc.db.entry_by_ref("D001")
    goat.tokens[0].set("Translation", "goat (sg.)", "en")
    win.open_bulk_edit()
    w = win.bulk_window
    w.ops.setCurrentIndex(bw.REPLACE)
    w.r_field.setCurrentIndex(w.r_field.findData("f:Translation"))
    w.r_find.setText("(sg.)")
    w.r_repl.setText("(sg)")
    w.preview()
    t = w.tables[bulk.TOKENS]
    assert t.model_.preview
    during = []
    t.model_.dataChanged.connect(lambda *a: during.append(t.proxy._filtering))
    t.proxy._filtering = True
    t.proxy.set_filter("f:Translation", fl.TextFilter("(sg.)"))
    t.proxy._filtering = False
    QApplication.processEvents()                      # the preview is cleared after, not during
    assert during and not any(during) and not t.model_.preview and t.proxy.rowCount() == 1
    w.close()


def test_unticked_cell_lines_sit_in_their_usual_place():
    from lemmatrix.ui.matrix_dialogs import cell_order
    natural = ["drawing", "Phonetic", "Phonemic", "Morphemes", "Pitch", "Translation", "Comment"]
    assert cell_order(["drawing", "Phonetic", "Phonemic", "Translation"], natural) == natural
    mine = cell_order(["Translation", "Phonetic"], natural)          # a chosen order is kept
    assert mine.index("Translation") < mine.index("Phonetic") and sorted(mine) == sorted(natural)


def test_open_texts_window_follows_a_theme_change(win, tmp_path, monkeypatch):
    from PySide6.QtGui import QPalette
    from lemmatrix.ui import theme
    uw, t = _add_text(win, tmp_path, monkeypatch)
    uw.show()
    try:
        theme.configure("dark", "#7b2fa8")
        theme.apply()
        win._restyle()
        assert uw.texts.lines.palette().color(QPalette.Base) == theme.colour("base")
        assert uw.table.palette().color(QPalette.Base) == theme.colour("base")
        assert "#" in uw.title.styleSheet() and theme.colour("pitch").name() in uw.title.styleSheet()
    finally:
        theme.configure("light", theme.DEFAULT_ACCENT)
        theme.apply()
        win._restyle()


def test_praat_copy_of_a_token_recording_is_adopted_on_opening(win, tmp_path):
    """A recording named with a space, and Praat's newer copy saved under its own name beside it:
    on opening, the newer one is used and the old one set aside (as for texts)."""
    import time
    from lemmatrix import storage
    db = win.doc.db
    e = db.entry_by_ref("D001")
    e.file_gloss = "billy goat"
    t = e.tokens[0]
    folder = storage.sound_folder(db)
    old, new = "LXX-VXX_D001_billy goat.wav", "LXX-VXX_D001_billy_goat.wav"
    (folder / t.file).rename(folder / old)
    t.file = old
    (folder / new).write_bytes((folder / old).read_bytes() + b"edited")
    later = time.time() + 5
    os.utime(folder / new, (later, later))
    win._praat_text_names(db)
    assert t.file == new and (folder / new).exists() and not (folder / old).exists()
    # an older name with no copy beside it is simply renamed
    t2 = e.tokens[1]
    (folder / t2.file).rename(folder / t2.file.replace("goat", "billy goat"))
    t2.file = t2.file.replace("goat", "billy goat")
    win._praat_text_names(db)
    assert " " not in t2.file and (folder / t2.file).exists()
