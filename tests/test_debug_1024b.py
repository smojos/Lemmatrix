# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders. Additional terms: NOTICE.md
"""Debug, 24 October evening (Josh): a long lemma no longer stretches the Lemma/Tag matrix's
headers; the phonetics scratchpad follows a switch from the dark theme to the light."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["LEMMATRIX_SETTINGS"] = "Lemmatrix-tests"

from PySide6.QtGui import QPalette  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from test_ui import app, win  # noqa: E402,F401


def test_a_long_lemma_is_capped_down_the_side_and_across_the_top(win):
    from lemmatrix import matrix as mx
    from lemmatrix.ui.main_window import LEMMA_TAG
    from lemmatrix.ui.matrix_view import ChipHeader
    db = win.doc.db
    e = db.entry_by_ref("D001")
    e.set(db.settings.entry_field("lemma").name, "a" * 200)
    win.tabs.setCurrentIndex(LEMMA_TAG)
    cfg = win.config_for(LEMMA_TAG)
    cfg.x = [mx.Spec.citation(), mx.Spec(frozenset({"Plural"}), mx.LOOSE)]
    win.refresh()
    vh = win.lt_view.verticalHeader()
    row = next(i for i, it in enumerate(win.layouts[LEMMA_TAG].rows) if it.entry is e)
    assert vh.sectionSizeFromContents(row).width() <= ChipHeader.WRAP_WIDTH
    assert vh.textElideMode().name == "ElideRight"
    win.switched[LEMMA_TAG] = True                 # lemmas across the top
    win.refresh()
    hh = win.lt_view.horizontalHeader()
    col = next(i for i, it in enumerate(win.layouts[LEMMA_TAG].cols) if it.entry is e)
    assert hh.sectionSizeFromContents(col).width() <= ChipHeader.LEMMA_WIDTH   # the data decides the width
    win.switched[LEMMA_TAG] = False
    win.refresh()


def test_the_scratchpad_follows_dark_to_light(win):
    from lemmatrix.ui import theme
    win.show()
    win.prefs.theme = "dark"
    theme.from_prefs(win.prefs)
    win._restyle()
    QApplication.processEvents()
    dark = win.comparison.alpha.edit.palette().color(QPalette.Base).name()
    win.toggle_theme()                             # to light
    QApplication.processEvents()
    for pad in win.comparison.pads + win.comparison.seg_pads:
        base = pad.edit.palette().color(QPalette.Base).name()
        assert base == theme.interface_palette().color(QPalette.Base).name() and base != dark


def test_ctrl_alt_space_opens_the_line_in_praat(win, monkeypatch):
    from PySide6.QtGui import QKeySequence, QShortcut
    w = win.open_utterances()
    keys = {s.key().toString(): s for s in w.findChildren(QShortcut)}
    assert "Ctrl+Alt+Space" in keys
    got = []
    monkeypatch.setattr(w.texts, "open_in_praat", lambda: got.append("line"))
    from lemmatrix.ui.utterances import TEXTS
    w.tabs.setCurrentIndex(TEXTS)
    keys["Ctrl+Alt+Space"].activated.emit()
    assert got == ["line"]
    w.close()
