# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders. Additional terms: NOTICE.md
"""Josh's small list of 20 October: Ctrl+R, Ctrl+E, window sizes, Push to question on a line,
glosses and translations quoted the same everywhere."""

import os


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["LEMMATRIX_SETTINGS"] = "Lemmatrix-tests"

from test_texts import _add_text  # noqa: E402,F401  (the same window and text)


def test_meanings_are_in_single_quotes_and_never_doubled():
    from lemmatrix.ui.widgets import meaning
    assert meaning("goat") == "‘goat’"
    assert meaning('"the hare ran"') == "‘the hare ran’"
    assert meaning("“where is he?”") == "‘where is he?’"
    assert meaning("") == ""


def test_ctrl_r_opens_the_token_and_starts_recording(win, monkeypatch):
    from PySide6.QtGui import QKeySequence
    from lemmatrix.ui import token_dialog
    started = []
    monkeypatch.setattr(token_dialog.TokenDialog, "_record", lambda self: started.append(self.token))
    monkeypatch.setattr(token_dialog.TokenDialog, "exec", lambda self: None)
    assert QKeySequence("Ctrl+R") in [a.shortcut() for a in win.actions()]
    t = win.all_table
    row = t.model_.rows[0]
    t.select_row(row)
    win.record_selected()
    from PySide6.QtWidgets import QApplication
    QApplication.processEvents()
    assert len(started) == 1


def test_ctrl_e_toggles_edit_mode_in_the_lines(win, tmp_path, monkeypatch):
    uw, t = _add_text(win, tmp_path, monkeypatch)
    p = uw.texts
    uw.show()
    assert not p.lines.edit_mode
    p.toggle_edit_mode()
    assert p.lines.edit_mode and p.edit_btn.isChecked()
    p.toggle_edit_mode()
    assert not p.lines.edit_mode


def test_push_a_line_comment_to_question(win, tmp_path, monkeypatch):
    uw, t = _add_text(win, tmp_path, monkeypatch)
    p = uw.texts
    line = p.lines.rows[0]
    p.set_line_field(line, "Comment", "is this a relative clause?")
    p.push_to_question(p.lines.rows[0])
    s = win.doc.notebook.session(win.work_date())
    q = s.questions[-1]
    assert q.text == "is this a relative clause?" and q.is_open
    assert q.link.is_line and q.link.entry_id == t.id and q.ref == t.ref
    assert abs(q.link.line_start - line.start) < 1e-3
    assert not p.lines.rows[0].values.get("Comment")          # the Comment is emptied, as in the token dialogue
    assert not [c for c in s.comments if c.is_line]


def test_texts_and_utterances_window_remembers_its_splitters(win, tmp_path, monkeypatch):
    from lemmatrix.ui.utterances import TextsUtterancesWindow
    uw = win.open_utterances()
    sp = uw.split
    sp.setSizes([500, 260])
    uw._winstate.save()
    want = sp.sizes()
    uw.close()
    win.utterances_window = None
    uw2 = TextsUtterancesWindow(win)
    assert uw2.split.sizes() == want or uw2.split.saveState() == sp.saveState()
    uw2.close()


def test_bulk_edit_remembers_its_size(win):
    win.open_bulk_edit()
    bw = win.bulk_window
    bw.resize(1100, 560)               # the test screen is 800 × 800: Qt keeps a window that fits
    bw._winstate.save()
    bw.close()
    win.open_bulk_edit()
    assert win.bulk_window.size().height() == 560
    win.bulk_window.close()


def test_shift_wheel_scrolls_sideways(app):
    from PySide6.QtCore import QPoint, QPointF, Qt
    from PySide6.QtGui import QWheelEvent
    from PySide6.QtWidgets import QApplication, QTableWidget
    from lemmatrix.ui import shiftwheel
    f = shiftwheel.install(QApplication.instance())
    try:
        t = QTableWidget(5, 40)
        t.resize(300, 200)
        t.show()
        QApplication.processEvents()
        h, v = t.horizontalScrollBar(), t.verticalScrollBar()
        assert h.maximum() > 0 and h.value() == 0
        ev = QWheelEvent(QPointF(50, 50), QPointF(t.viewport().mapToGlobal(QPoint(50, 50))), QPoint(),
                         QPoint(0, -120), Qt.NoButton, Qt.ShiftModifier, Qt.NoScrollPhase, False)
        QApplication.sendEvent(t.viewport(), ev)
        assert h.value() > 0 and v.value() == 0
    finally:
        QApplication.instance().removeEventFilter(f)


def test_tags_down_the_side_wrap_to_the_header_width(win):
    from PySide6.QtCore import Qt
    from lemmatrix import matrix as mx
    from lemmatrix.ui.main_window import LEMMA_TAG
    win.tabs.setCurrentIndex(LEMMA_TAG)
    many = frozenset({"Plural", "Genitive", "before H", "after L", "postverbal", "utterance-final"})
    win.config_for(LEMMA_TAG).x = [mx.Spec.citation(), mx.Spec(frozenset({"Plural"}), mx.EXACT),
                                   mx.Spec(many, mx.EXACT)]
    win.refresh()
    win.switch_axes(LEMMA_TAG)                     # tags down the side
    vh = win.lt_view.verticalHeader()
    assert vh.sectionSizeFromContents(2).width() <= vh.WRAP_WIDTH
    assert vh.sectionSizeFromContents(2).height() > vh.sectionSizeFromContents(1).height() \
        or vh.sectionSize(2) >= vh.sectionSizeFromContents(2).height()
    assert len(vh._chip_lines(vh.model().headerData(2, Qt.Vertical, Qt.UserRole), vh.WRAP_WIDTH - 24)) > 1
    win.lt_view.grab()


def test_tags_across_the_top_wrap_onto_two_lines(win):
    from lemmatrix import matrix as mx
    from lemmatrix.ui.main_window import LEMMA_TAG
    win.tabs.setCurrentIndex(LEMMA_TAG)
    many = frozenset({"Plural", "Genitive", "before H", "after L", "postverbal", "utterance-final"})
    win.config_for(LEMMA_TAG).x = [mx.Spec(frozenset({"Plural"}), mx.EXACT), mx.Spec(many, mx.EXACT)]
    win.refresh()
    v = win.lt_view
    hh = v.horizontalHeader()
    from lemmatrix.ui.widgets import chips_width
    labels = hh._chips(1)
    assert hh.sectionSize(1) < chips_width(labels, hh.chip_font) + 24     # not stretched to one line
    assert len(hh._chip_lines(labels, hh.sectionSize(1) - 24)) == 2
    assert hh.height() >= 2 * 20                                          # two lines tall
    assert v.switch.height() >= hh.height() - 2                           # the switch button grows too
    v.grab()
