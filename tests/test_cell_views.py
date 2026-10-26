# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders. Additional terms: NOTICE.md
"""The cell views, 21 October evening: the utterance cell (IDEAS.md idea 22), lined-up fields in
the matrix cells (idea 2), the display conventions (idea 26), New lemma… in Create token
(idea 31) and lines where only other tiers have text."""

from PySide6.QtCore import Qt

from lemmatrix import matrix as mx

from test_texts import _add_text  # noqa: F401
from test_utterances import _wav  # noqa: F401 (fixtures)


def _utterance(win, tmp_path):
    uw = win.open_utterances()
    uw.import_files([str(_wav(tmp_path / "tune.wav"))])
    u = win.doc.db.utterances[0]

    def ch(x):
        x.token.set("Phonetic", "ŋɔːɲ kʷʊːn")
        x.token.set("Phonemic", "ŋɔ́ɔɲ kʊ̀ʊn")
        x.token.set("Morphemes", "lion house.PL")
        x.token.set("Translation", "the lions' houses", "en", True)
    win.doc.edit_entry(u, ch)
    uw.tabs.setCurrentIndex(1)
    uw.table.select_row(u)
    return uw, u


# ---- the utterance cell ------------------------------------------------------------------

def test_the_utterance_cell_shows_and_edits_the_selected_utterance(win, tmp_path):
    uw, u = _utterance(win, tmp_path)
    cell = uw.cell
    assert len(cell.rows) == 1 and cell.rows[0].utterance is u
    assert cell.rows[0].values["Translation:en"] == "the lions' houses"
    assert uw._cell_head(u).startswith(u.ref) and uw.cell_title.text().startswith(u.ref)
    assert cell.comment_below and not cell.side_w           # the Comment under the fields (21 October)
    uw.set_cell_edit_mode(True)
    cell.start_edit(cell.rows[0], "Translation:en")
    ed = cell._editor[0]
    ed.setText("the houses of the lions")
    cell._close_editor(commit=True)
    assert u.token.get("Translation", "en") == "the houses of the lions"
    win.doc.undo.undo()
    assert u.token.get("Translation", "en") == "the lions' houses"


def test_the_utterance_cell_is_never_wider_than_half_the_options_area(win, tmp_path):
    uw, u = _utterance(win, tmp_path)
    sp = uw.cell_split
    sp.resize(1000, 200)
    sp.setSizes([200, 800])
    sp._clamp()
    a, b = sp.sizes()
    assert b <= (a + b) // 2 + 1


def test_create_token_from_the_utterance_cell(win, tmp_path, monkeypatch):
    from lemmatrix.ui import move_dialog, token_dialog
    uw, u = _utterance(win, tmp_path)
    db = win.doc.db
    target = db.new_entry("D901", "kʊʊn", "house")
    target.tokens = []
    db.entries.append(target)
    monkeypatch.setattr(move_dialog.CreateTokenDialog, "exec", lambda self: 1)
    monkeypatch.setattr(move_dialog.CreateTokenDialog, "chosen", lambda self: target)
    seen = {}
    monkeypatch.setattr(token_dialog.TokenDialog, "exec", lambda dlg: seen.update(
        fields={k: e.text() for k, e in dlg.edits.items()}) or 0)
    cell = uw.cell
    assert any(s.key == "Phonetic" for s in cell.fields)
    cell.select_words(cell.rows[0], "Phonetic", 1, 1)
    line, key, words = cell.text_selection()
    uw.texts.create_token(line, key, words, view=cell)
    assert seen["fields"]["Phonetic"] == "kʷʊːn"


# ---- lined-up fields in the matrix cells -------------------------------------------------

def test_matrix_cells_line_up_the_aligned_fields(win):
    from lemmatrix.ui.main_window import LEMMA_TAG
    db = win.doc.db
    e = db.entry_by_ref("D001")
    t = e.tokens[0]
    t.set("Phonemic", "dɪɪr {bəə ka}")
    t.set("Morphemes", "goat {of.the house}")
    win.tabs.setCurrentIndex(LEMMA_TAG)
    cfg = win.config_for(LEMMA_TAG)
    cfg.x = [mx.Spec.citation()]
    cfg.cell = ["Phonetic", "Phonemic", "Morphemes"]
    win.refresh()
    d = win._view(LEMMA_TAG).delegate
    assert d._units(t, "Phonemic")[1].strip("/") == "bəə ka"          # braces group, symbols hidden
    cols = d._cols(t)
    assert len(cols) == 2 and cols[1] >= d._w("Morphemes", "of.the house")
    win.set_aligned(set())                                            # nothing lines up
    assert not d._aligned("Phonemic") and d._cols(t) == []


def test_configure_cell_sets_the_shared_line_up(win, monkeypatch):
    from lemmatrix.ui import main_window
    from lemmatrix.ui.main_window import LEMMA_TAG

    def fake_exec(dlg):
        for i in range(dlg.list.topLevelItemCount()):
            it = dlg.list.topLevelItem(i)
            if it.data(0, Qt.UserRole) == "Translation":
                it.setCheckState(1, Qt.Checked)
            if it.data(0, Qt.UserRole) == "Morphemes":
                it.setCheckState(1, Qt.Unchecked)
        return 1
    monkeypatch.setattr(main_window.ConfigureCellDialog, "exec", fake_exec)
    win.configure_cell(LEMMA_TAG)
    al = win.aligned_set()
    assert "Translation:en" in al and "Morphemes" not in al and "Phonemic" in al
    assert win.doc.ws.get_list("lines/aligned") == sorted(al)


# ---- the display conventions -------------------------------------------------------------

def test_conventions_wrap_and_small_caps(app):
    from lemmatrix.ui import conventions as cv
    c = cv.Conventions()
    assert cv.wrap("phonetic", "dɪɪr", c) == "[dɪɪr]" and cv.wrap("phonemic", "dɪɪr", c) == "/dɪɪr/"
    assert cv.wrap("translation", "goat", c) == "‘goat’" and cv.wrap("translation", "‘goat’", c) == "‘goat’"
    assert cv.wrap("translation", "goat", cv.Conventions(quotes=cv.DOUBLE)) == "“goat”"
    assert cv.wrap("translation", "goat", cv.Conventions(quotes=cv.NO_QUOTES)) == "goat"
    assert cv.wrap("phonetic", "dɪɪr", cv.Conventions(on=False)) == "dɪɪr"
    assert cv.wrap_units("phonemic", ["dɪɪr", "", "ka"], c) == ["/dɪɪr", "", "ka/"]
    assert cv.runs("house-PL.1SG of xH") == [("house-", False), ("PL", True), (".", False), ("1SG", True),
                                             (" of xH", False)]
    from lemmatrix.ui.widgets import ipa_font
    f = ipa_font(14)
    assert cv.width("goat-PL", f, True) < cv.width("goat-PL", f, False)    # small caps are narrower


def test_the_switch_turns_them_all_off_and_on(win):
    from lemmatrix.ui import conventions as cv
    from lemmatrix.ui.main_window import LEMMA_TAG
    win.tabs.setCurrentIndex(LEMMA_TAG)
    d = win._view(LEMMA_TAG).delegate
    t = win.doc.db.entry_by_ref("D001").tokens[0]
    buttons = [b for b in win._conv_buttons]
    assert buttons and all(b.isChecked() == cv.CURRENT.on for b in buttons)
    win.set_conventions_on(True)
    assert d._text(t, "Phonetic").startswith("[")
    win.set_conventions_on(False)
    assert not d._text(t, "Phonetic").startswith("[") and not any(b.isChecked() for b in win._conv_buttons)
    assert win.prefs.get_bool("conventions/on", True) is False
    win.set_conventions_on(True)


# ---- Create token: New lemma… -------------------------------------------------------------

def test_new_lemma_from_create_token_puts_the_words_in_its_citation_token(win, tmp_path, monkeypatch):
    from lemmatrix.ui import dialogs, move_dialog, token_dialog
    uw, t = _add_text(win, tmp_path, monkeypatch)
    db = win.doc.db
    n = len(db.entries)

    def entry_exec(dlg):
        gloss = next(e for (name, lang), e in dlg.fields.items() if name == "Gloss" and lang == "en")
        assert gloss.text() == "hare"                          # the words to start with
        dlg.ref.setText("D950")
        return 1
    monkeypatch.setattr(dialogs.EntryDialog, "exec", entry_exec)
    monkeypatch.setattr(move_dialog.CreateTokenDialog, "exec", lambda self: (self._make(), 1)[1])
    seen = {}
    monkeypatch.setattr(token_dialog.TokenDialog, "exec", lambda dlg: seen.update(
        index=dlg.slot.index, tr=dlg.edits["Translation"].text()) or 0)
    v = uw.texts.lines
    v.select_words(v.rows[0], "Translation:en", 1, 1)
    line, key, words = v.text_selection()
    uw.texts.create_token(line, key, words)
    assert len(db.entries) == n + 1
    e = db.entries[-1]
    assert e.tokens[0].get("Translation", "en") == "hare" and seen == {"index": 0, "tr": "hare"}


# ---- lines where only other tiers have text ----------------------------------------------

def test_a_stretch_without_main_tier_text_shows_as_a_flagged_line(win, tmp_path, monkeypatch):
    from lemmatrix import textgrid as tgmod
    src = tmp_path / "field"
    src.mkdir()
    tgmod.write_example(src / "story.TextGrid", {
        "tx": [(0.5, 1.5, "ʔəŋ kɒ")],
        "ft": [(0.5, 1.5, "the hare ran"), (2.0, 3.0, "where is he?")]}, 4.0)
    uw, t = _add_text(win, tmp_path, monkeypatch, src=src)
    rows = uw.texts.lines.rows
    assert len(rows) == 2 and rows[1].missing_main and rows[1].values["Translation:en"] == "where is he?"


# ---- 21 October, later: edit mode in the matrices, the cell's Comment below ----------------

def test_ctrl_e_edits_a_matrix_cell_in_place(win):
    from PySide6.QtGui import QKeySequence
    from PySide6.QtTest import QTest
    from lemmatrix.ui.main_window import LEMMA_TAG
    acts = {a.shortcut().toString(): a.text() for a in win.findChildren(type(win.menuBar().actions()[0]))
            if not a.shortcut().isEmpty()}
    assert acts.get(QKeySequence("Ctrl+Shift+B").toString()) == "&Bulk edit…"     # moved from Ctrl+E
    win.tabs.setCurrentIndex(LEMMA_TAG)
    cfg = win.config_for(LEMMA_TAG)
    cfg.x = [mx.Spec.citation()]
    cfg.cell = ["Phonetic", "Translation"]
    win.refresh()
    view = win._view(LEMMA_TAG)
    win.toggle_matrix_edit()
    assert view.edit_mode and not win.lt_bar["edit_mode"].isHidden()
    lay = view.model_.layout_
    r = next(i for i, row in enumerate(lay.rows) if lay.tokens(i, 0))
    e, t = lay.tokens(r, 0)[0]
    view.start_edit(r, 0, 0, "Translation")
    ed = view._editor[0]
    assert ed.text() == t.get("Translation", "en")
    ed.setText("a new translation")
    QTest.keyClick(ed, Qt.Key_Return)
    assert e.tokens[0].get("Translation", "en") == "a new translation"
    win.doc.undo.undo()
    assert e.tokens[0].get("Translation", "en") != "a new translation"
    win.toggle_matrix_edit()
    assert not view.edit_mode


def test_the_utterance_cells_comment_is_under_the_fields(win, tmp_path):
    uw, u = _utterance(win, tmp_path)
    uw.resize(1200, 800)
    uw.show()
    cell = uw.cell
    c = cell._cells[0]
    box = cell._comment_box(c, c.y)
    assert box.top() >= c.fields_h - 1 and box.width() > cell.viewport().width() * 0.7
    assert cell.needed_height() >= c.fields_h + cell.comment_min()
    assert uw.cell_config_btn.toolTip().startswith("Configure view")


def test_new_databases_line_up_phonemic_and_morphemes(win):
    from lemmatrix.defaults import new_database
    win.load_database(new_database())
    assert win.aligned_set() == {"Phonemic", "Morphemes"}


def test_the_matrix_pencil_is_edit_mode(win):
    from lemmatrix.ui.main_window import LEMMA_TAG
    win.tabs.setCurrentIndex(LEMMA_TAG)
    btn = win.lt_bar["edit_btn"]
    assert btn.isCheckable() and "Ctrl+E" in btn.toolTip()
    btn.click()
    assert win._view(LEMMA_TAG).edit_mode and btn.isChecked() and win.tt_bar["edit_btn"].isChecked()
    btn.click()
    assert not win._view(LEMMA_TAG).edit_mode and not btn.isChecked()
