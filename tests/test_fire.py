# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders. Additional terms: NOTICE.md
"""Settings → Advanced's 🔥 hot mic (IDEAS.md idea 68) and 📋 fast paste (idea 79), Josh, 27 October:
hot mic records over a soundfile without asking and the Record button wears the flame; fast paste
copies Phonetic into Phonemic (and back) with Shift+Down / Shift+Up, the arrow pointing to the other
field on the screen."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication, QLineEdit  # noqa: E402

from lemmatrix import advanced  # noqa: E402


def _settle():
    for _ in range(5):
        QApplication.processEvents()


# ---- 🔥 hot mic ---------------------------------------------------------------------------

def test_off_asks_on_does_not(win, monkeypatch):
    from lemmatrix.ui import recording_panel as rp
    from lemmatrix.ui import widgets
    asked = []
    monkeypatch.setattr(widgets, "ask", lambda *a, **k: asked.append(a[2]) or False)
    assert not rp.ask_record_over(win, "Replace this token's recording?", "Record over it") and asked
    advanced.set_on(advanced.HOT_MIC_KEY, True)
    asked.clear()
    assert rp.ask_record_over(win, "Replace this token's recording?", "Record over it") and not asked


def test_the_token_dialogue_records_over_its_own_without_asking(win, monkeypatch):
    from lemmatrix.ui import widgets
    from lemmatrix.ui.token_dialog import Slot, TokenDialog
    db = win.doc.db
    e = next(x for x in db.entries if any(t.file for t in x.tokens))
    k = next(i for i, t in enumerate(e.tokens) if t.file)
    dlg = TokenDialog(win, [Slot(e, k)], 0)
    if not dlg._path(dlg.token.file).exists():
        dlg.reject()
        return
    asked, started = [], []
    monkeypatch.setattr(widgets, "ask", lambda *a, **k: asked.append(a[2]) or False)
    monkeypatch.setattr(dlg.rec_panel, "start", lambda: started.append(1) or True)
    dlg._record()
    assert asked and not started                          # off: asked (and declined here)
    advanced.set_on(advanced.HOT_MIC_KEY, True)
    asked.clear()
    dlg._record()
    assert not asked and started                          # on: straight to recording
    dlg.reject()


def test_the_record_button_wears_the_flame(win):
    from lemmatrix.ui.token_dialog import Slot, TokenDialog
    from lemmatrix.ui import recording_panel as rp
    dlg = TokenDialog(win, [Slot(win.doc.db.entries[0], 0)], 0)
    assert rp.record_icon() == "record" and "hot mic" not in dlg.rec_panel.record_btn.toolTip()
    advanced.set_on(advanced.HOT_MIC_KEY, True)
    assert rp.record_icon() == "record-hot" and "hot mic is on" in dlg.rec_panel.record_btn.toolTip()
    advanced.set_on(advanced.HOT_MIC_KEY, False)
    assert "hot mic" not in dlg.rec_panel.record_btn.toolTip()
    dlg.reject()


def test_the_segment_dialogue_follows_hot_mic(win, monkeypatch, tmp_path):
    from lemmatrix.ui import recording_panel as rp
    src = open(rp.__file__, encoding="utf-8").read()
    seg = open(rp.__file__.replace("recording_panel", "segment_record"), encoding="utf-8").read()
    assert "ask_record_over" in seg and "def ask_record_over" in src


# ---- 📋 fast paste ------------------------------------------------------------------------

def _boxes(dlg):
    from lemmatrix.ui import keyboards
    out = {}
    for w in dlg.findChildren(QLineEdit):
        k = keyboards.field_key(w)
        if k in ("Phonetic", "Phonemic"):
            out[k] = w
    return out


def test_the_token_dialogue_pastes_down_and_up(win):
    from lemmatrix.ui import fastpaste
    from lemmatrix.ui.token_dialog import Slot, TokenDialog
    fastpaste.set_context(lambda: win.doc.db)
    dlg = TokenDialog(win, [Slot(win.doc.db.entries[0], 0)], 0)
    dlg.show()
    _settle()
    b = _boxes(dlg)
    pht, phm = b["Phonetic"], b["Phonemic"]
    pht.setText("dʌ́ʌm")
    phm.setText("old")
    assert not fastpaste.paste(pht, up=True)              # Phonemic isn't above Phonetic
    assert fastpaste.paste(pht, up=False) and phm.text() == "dʌ́ʌm"
    phm.undo()
    assert phm.text() == "old"                            # one step of the box's own undo
    phm.setText("dʌʌm")
    assert fastpaste.paste(phm, up=True) and pht.text() == "dʌʌm"
    dlg.reject()


def test_the_arrow_follows_the_screen(win):
    """Phonemic above Phonetic (a reordered layout): Shift+Down from Phonemic goes to Phonetic."""
    from lemmatrix.ui import fastpaste
    from lemmatrix.ui.token_dialog import Slot, TokenDialog
    fastpaste.set_context(lambda: win.doc.db)
    dlg = TokenDialog(win, [Slot(win.doc.db.entries[0], 0)], 0)
    dlg.show()
    _settle()
    b = _boxes(dlg)
    pht, phm = b["Phonetic"], b["Phonemic"]
    below_is_phm = phm.mapToGlobal(phm.rect().center()).y() > pht.mapToGlobal(pht.rect().center()).y()
    upper, lower = (pht, phm) if below_is_phm else (phm, pht)
    upper.setText("abc")
    assert fastpaste.paste(upper, up=False) and lower.text() == "abc"
    assert not fastpaste.paste(upper, up=True)
    dlg.reject()


def test_other_fields_are_untouched(win):
    from lemmatrix.ui import fastpaste, keyboards
    fastpaste.set_context(lambda: win.doc.db)
    e = QLineEdit()
    keyboards.tag(e, "Translation")
    assert not fastpaste.paste(e, up=False)


def test_the_filter_only_when_on(win, app):
    from PySide6.QtGui import QKeyEvent
    from PySide6.QtCore import QEvent
    from lemmatrix.ui import fastpaste
    f = fastpaste.FastPasteFilter()
    e = QLineEdit()
    ev = QKeyEvent(QEvent.KeyPress, Qt.Key_Down, Qt.ShiftModifier)
    assert not f.eventFilter(e, ev)                       # off: Shift+Down selects as usual


def test_the_matrix_cell_pastes_into_the_line_below(win):
    from lemmatrix import matrix as mx
    from lemmatrix.ui import fastpaste
    from lemmatrix.ui.main_window import LEMMA_TAG
    fastpaste.set_context(lambda: win.doc.db)
    win.tabs.setCurrentIndex(LEMMA_TAG)
    cfg = win.config_for(LEMMA_TAG)
    cfg.x = [mx.Spec.citation()]
    cfg.cell = ["Phonetic", "Phonemic", "Translation"]
    win.refresh()
    view = win._view(LEMMA_TAG)
    win.toggle_matrix_edit()
    lay = view.model_.layout_
    r = next(i for i, row in enumerate(lay.rows) if lay.tokens(i, 0))
    e, t = lay.tokens(r, 0)[0]
    view.start_edit(r, 0, 0, "Phonetic")
    ed = view._editor[0]
    ed.setText("ŋa-pasted")
    assert not fastpaste.paste(ed, up=True)               # nothing above Phonetic that is Phonemic
    assert fastpaste.paste(ed, up=False)
    assert t.get("Phonemic") == "ŋa-pasted" and view._editor[3] == "Phonemic"
    assert t.get("Phonetic") == "ŋa-pasted"               # its own edit kept too
    view._close_editor(commit=False)
    win.toggle_matrix_edit()


def test_all_data_pastes_into_the_other_column(win):
    from lemmatrix.ui import fastpaste
    fastpaste.set_context(lambda: win.doc.db)
    t = win.all_table
    cols = [c.key for c in t.model_.columns]
    assert "f:Phonetic" in cols and "f:Phonemic" in cols
    c = cols.index("f:Phonetic")
    idx = t.proxy.index(0, c)
    row = t.row_at(idx)
    t.setCurrentIndex(idx)
    t.edit(idx)
    _settle()
    ed = t.indexWidget(idx) or QApplication.focusWidget()
    ed = ed if isinstance(ed, QLineEdit) else next(w for w in t.viewport().findChildren(QLineEdit) if w.isVisible())
    ed.setText("ba-tuul")
    assert t.fast_paste(ed, False, "phonemic", win.doc.db)
    _settle()
    assert row.token.get("Phonemic") == "ba-tuul" and row.token.get("Phonetic") == "ba-tuul"


def test_settings_advanced_has_both(win):
    from PySide6.QtWidgets import QLabel
    from lemmatrix.ui.dialogs import PreferencesDialog
    dlg = PreferencesDialog(win, win.doc.db, win.prefs)
    assert dlg.hot_mic_box.text() == "🔥 hot mic" and dlg.fast_paste_box.text() == "📋 fast paste"
    assert not dlg.hot_mic_box.isChecked() and not dlg.fast_paste_box.isChecked()
    assert any(lb.toolTip() == "Not recommended with an orange or red theme" for lb in dlg.findChildren(QLabel))
    dlg.hot_mic_box.setChecked(True)
    dlg.fast_paste_box.setChecked(True)
    dlg.apply()
    assert advanced.hot_mic() and advanced.fast_paste()
    assert win.prefs.get_bool(advanced.HOT_MIC_KEY) and win.prefs.get_bool(advanced.FAST_PASTE_KEY)
    for key in (advanced.HOT_MIC_KEY, advanced.FAST_PASTE_KEY):
        win.prefs.set_value(key, False)
    dlg.reject()


def test_the_utterance_cell_pastes_into_the_field_below(win, tmp_path):
    from lemmatrix.ui import fastpaste
    from test_cell_views import _utterance
    fastpaste.set_context(lambda: win.doc.db)
    uw, u = _utterance(win, tmp_path)
    win.doc.ws_set("lines/fields", ["Phonetic", "Phonemic", "Translation:en"])   # Configure view
    uw.show_cell(u)
    cell = uw.cell
    keys = [s.key for s in cell.fields]
    assert "Phonetic" in keys and "Phonemic" in keys
    uw.set_cell_edit_mode(True)
    top, bottom = sorted(("Phonetic", "Phonemic"), key=keys.index)
    cell.start_edit(cell.rows[0], top)
    ed = cell._editor[0]
    ed.setText("ŋɔ-pasted")
    assert not fastpaste.paste(ed, up=True)
    assert fastpaste.paste(ed, up=False)
    assert u.token.get(bottom) == "ŋɔ-pasted" and cell._editor[2] == bottom
    cell._close_editor(commit=False)
