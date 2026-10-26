# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders. Additional terms: NOTICE.md
"""Debug, 26 October (Josh): Ctrl+Alt+Space (Open in Praat) did nothing in the token dialogue,
and nothing anywhere with the cursor in a field."""

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QApplication


def _press(widget, mods):
    for t in (QEvent.ShortcutOverride, QEvent.KeyPress):
        QApplication.sendEvent(widget, QKeyEvent(t, Qt.Key_Space, mods, " "))


def _filter(app, alt=True, shift=False):
    from lemmatrix.ui import ctrlspace
    f = ctrlspace.CtrlSpaceFilter(app, held_fn=lambda: (True, shift, alt))
    app.installEventFilter(f)
    return f


def test_token_dialogue_opens_in_praat_from_a_field(win, app, monkeypatch):
    from lemmatrix.ui.token_dialog import Slot, TokenDialog
    opened = []
    monkeypatch.setattr(win, "open_in_praat", lambda path, parent=None, **k: opened.append(parent))
    dlg = TokenDialog(win, [Slot(win.doc.db.entries[0], 0)], 0)
    dlg.show()
    f = _filter(app)
    try:
        dlg.praat_btn.setEnabled(True)
        field = next(iter(dlg.edits.values()))
        before = field.text()
        _press(field, Qt.ControlModifier | Qt.AltModifier)
        assert opened == [dlg] and field.text() == before          # opened, no space typed
        dlg.praat_btn.setEnabled(False)                            # no recording: nothing happens
        dlg._praat_key()
        assert opened == [dlg]
        assert "Ctrl+Alt+Space" in dlg.praat_btn.toolTip()
    finally:
        app.removeEventFilter(f)
        dlg.reject()


def test_main_window_search_bar_opens_in_praat(win, app, monkeypatch):
    from lemmatrix.ui import ctrlspace
    act = next(a for a in win.findChildren(type(win.play_action)) if ctrlspace.PRAAT in a.shortcuts())
    hit = []
    act.triggered.disconnect()
    act.triggered.connect(lambda *a: hit.append(1))
    win.show()
    f = _filter(app)
    try:
        _press(win.all_search, Qt.ControlModifier | Qt.AltModifier)
        assert hit == [1] and win.all_search.text() == ""
    finally:
        app.removeEventFilter(f)


def test_ctrl_alt_space_is_left_alone_where_nothing_opens_praat(app):
    """Ctrl+Alt is AltGr on Windows: without a Praat key in the window, the field keeps it."""
    from PySide6.QtWidgets import QDialog, QLineEdit, QVBoxLayout
    d = QDialog()
    ed = QLineEdit()
    QVBoxLayout(d).addWidget(ed)
    d.show()
    f = _filter(app)
    try:
        from lemmatrix.ui import ctrlspace
        assert ctrlspace.find_shortcut(ed, False, praat=True) is None
        ev = QKeyEvent(QEvent.ShortcutOverride, Qt.Key_Space, Qt.ControlModifier | Qt.AltModifier, " ")
        assert not f.eventFilter(ed, ev)
    finally:
        app.removeEventFilter(f)
        d.close()
