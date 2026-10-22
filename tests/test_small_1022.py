# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders
"""Josh's tweaks of 22 October: the pitch scratchpad in the main window."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["LEMMATRIX_SETTINGS"] = "Lemmatrix-tests"

from test_ui import app, win  # noqa: E402,F401


def test_pitch_scratchpad_in_the_main_window(win, monkeypatch):
    played = []
    monkeypatch.setattr(win, "play_pitch", lambda text: played.append(text))
    sp = win.comparison.alpha
    assert win.scratchpad is sp and [l.text() for l in win.comparison.letters] == ["α", "β"]
    win.comparison.beta.edit.setText("33")
    win.comparison.beta.edit.returnPressed.emit()
    assert played == ["33"]
    played.clear()
    sp.edit.setText("55 3:3 21")
    assert sp.canvas.text == "55 3:3 21"
    sp.edit.returnPressed.emit()
    assert played == ["55 3:3 21"]
    order = [win.bottom_row.itemAt(i).widget() for i in range(win.bottom_row.count())]
    assert order.index(win.comparison.parentWidget()) + 1 == order.index(win.sess_panel)   # left of Current Session


def test_symbols_in_a_text_fields_menu(app):
    from PySide6.QtWidgets import QApplication, QLineEdit, QPlainTextEdit
    from lemmatrix.ui import symbols
    f = symbols.install(QApplication.instance())
    try:
        symbols.set_current(symbols.DEFAULT)
        for ed in (QLineEdit(), QPlainTextEdit()):
            menu = ed.createStandardContextMenu()
            menu.show()
            QApplication.processEvents()
            first = menu.actions()[0]
            assert first.text() == "Σymbols"
            menu.close()
            g = symbols.open_grid(ed)
            assert (g.table.columnCount(), g.table.rowCount()) == (4, 3)     # 11 symbols: 4 across, 3 down
            assert g.table.item(0, 2).text() == "∅"
            g.table.cellDoubleClicked.emit(0, 2)
            assert (ed.text() if isinstance(ed, QLineEdit) else ed.toPlainText()) == "∅"
            assert not g.isVisible()
        ro = QLineEdit()
        ro.setReadOnly(True)
        menu = ro.createStandardContextMenu()
        menu.show()
        QApplication.processEvents()
        assert all(a.text() != "Σymbols" for a in menu.actions())     # not in read-only fields
        menu.close()
    finally:
        QApplication.instance().removeEventFilter(f)


def test_symbols_list_in_edit_lists(win, monkeypatch):
    from lemmatrix.ui import symbols
    from lemmatrix.ui.lists_dialog import ListsDialog
    assert win._symbols() == symbols.DEFAULT
    dlg = ListsDialog(win, win.doc.db, win.doc.notebook, symbols=["ʔ", "ŋ"])
    assert dlg.symbol_list() == ["ʔ", "ŋ"]
    dlg._reset_symbols()
    assert dlg.symbol_list() == symbols.DEFAULT


def test_texts_comparison_and_logo(win):
    uw = win.open_utterances()
    t = uw.texts
    assert t.scratch is t.comparison.alpha.edit and t.comparison.beta.edit is not None
    assert not uw.logo.pixmap().isNull()                      # the logo, under both tabs
    assert uw.options.parentWidget() is uw.logo.parentWidget().parentWidget()
    uw.close()


def test_therefore_in_the_default_symbols():
    from lemmatrix.ui import symbols
    assert symbols.DEFAULT[-1] == "∴"
