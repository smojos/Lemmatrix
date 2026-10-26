# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders. Additional terms: NOTICE.md
"""The text lines, 21 October: the Clip icon in the dark theme, Save TextGrid (Ctrl+S), the
lines' zoom (Ctrl + mouse wheel), Create token from a line (IDEAS.md idea 31), the pitch
scratchpad (idea 33) and the Comment box's font and editor."""

from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
from PySide6.QtGui import QColor, QMouseEvent, QWheelEvent

from lemmatrix import textgrid as tgmod

from test_texts import _add_text  # noqa: F401 (fixtures)


def _pixel(ic, size, fx, fy) -> QColor:
    img = ic.pixmap(size, size).toImage()
    return img.pixelColor(round(img.width() * fx), round(img.height() * fy))


def test_the_clip_icons_scissors_follow_the_text_colour(app):
    from lemmatrix.ui.icons import icon
    dark = _pixel(icon("clip", 40, "#198583;#e8e8e8"), 40, 0.44, 0.515)     # on a blade
    light = _pixel(icon("clip", 40, "#198583;#1b1b1b"), 40, 0.44, 0.515)
    assert dark.alpha() > 100 and dark.lightnessF() > 0.7                  # white on the dark theme
    assert light.alpha() > 100 and light.lightnessF() < 0.3                # black on the light one


def _edit(p, ln, key, value):
    p.set_line_field(ln, key, value)


def test_save_textgrid_writes_this_text_only_and_leaves_the_database_unsaved(win, tmp_path, monkeypatch):
    uw, t = _add_text(win, tmp_path, monkeypatch)
    p = uw.texts
    grid = tmp_path / "Soundfiles" / "Texts" / t.textgrid
    assert not p.save_btn.isEnabled()                         # nothing to save yet
    _edit(p, p.lines.rows[1], "Translation:en", "where did he go?")
    assert p.save_btn.isEnabled()
    p.save_key()                                             # Ctrl+S on the Texts tab
    assert tgmod.read_lines(grid, win.doc.db.mapping_for(t))[1].values["Translation:en"] == "where did he go?"
    assert not p.save_btn.isEnabled() and "not yet saved" not in p.lines_title.text()
    assert any(f.suffix == ".TextGrid" for f in (tmp_path / "Backups").iterdir())
    assert win.doc.dirty                                      # the database itself waits for Save
    win.doc.undo.undo()                                       # undo after: unsaved again
    assert p.save_btn.isEnabled() and p.lines.rows[1].values["Translation:en"] == "where is he?"
    assert win.save()
    assert tgmod.read_lines(grid, win.doc.db.mapping_for(t))[1].values["Translation:en"] == "where is he?"
    assert not p.save_btn.isEnabled()


def test_ctrl_s_on_the_utterances_tab_saves_the_database(win, tmp_path, monkeypatch):
    uw, t = _add_text(win, tmp_path, monkeypatch)
    p = uw.texts
    _edit(p, p.lines.rows[0], "Translation:en", "the hare fled")
    uw.show()
    uw.tabs.setCurrentIndex(1)
    assert win.doc.dirty
    p.save_key()
    assert not win.doc.dirty and not p.save_btn.isEnabled()   # the database, with the TextGrid


def _wheel(v, delta, mods):
    pos = QPointF(50, 30)
    ev = QWheelEvent(pos, v.viewport().mapToGlobal(pos), QPoint(), QPoint(0, delta), Qt.NoButton, mods,
                     Qt.NoScrollPhase, False)
    v.wheelEvent(ev)


def test_ctrl_wheel_zooms_the_lines_and_closing_the_window_resets_it(win, tmp_path, monkeypatch):
    uw, t = _add_text(win, tmp_path, monkeypatch)
    v = uw.texts.lines
    size, h = v.plain.pointSizeF(), v._cells[0].h
    _wheel(v, 120, Qt.ControlModifier)
    assert v.zoom > 1.0 and v.plain.pointSizeF() > size and v._cells[0].h > h
    _wheel(v, -240, Qt.ControlModifier)
    assert v.zoom < 1.0
    from PySide6.QtTest import QTest
    QTest.keyClick(v, Qt.Key_0, Qt.ControlModifier)
    assert v.zoom == 1.0
    _wheel(v, 360, Qt.ControlModifier)
    uw.close()
    uw2 = win.open_utterances()
    assert uw2 is not uw and uw2.texts.lines.zoom == 1.0


def test_the_comment_has_the_translations_size_and_wraps_from_the_top_left(win, tmp_path, monkeypatch):
    from lemmatrix.ui.lines_view import CommentEdit
    uw, t = _add_text(win, tmp_path, monkeypatch)
    p = uw.texts
    v = p.lines
    p.set_edit_mode(True)
    v.start_edit(v.rows[0], p.comment_key())
    ed = v._editor[0]
    assert isinstance(ed, CommentEdit) and ed.font().pointSizeF() == v.plain.pointSizeF()
    ed.setText("check the tone on the second word")
    from PySide6.QtTest import QTest
    QTest.keyClick(ed, Qt.Key_Return)                          # Enter keeps it (no new line)
    assert v._editor is None and v.rows[0].values[p.comment_key()] == "check the tone on the second word"


def _press(v, x, y, kind=QEvent.MouseButtonPress, buttons=Qt.LeftButton):
    pos = QPointF(x, y)
    ev = QMouseEvent(kind, pos, v.viewport().mapToGlobal(pos), Qt.LeftButton, buttons, Qt.NoModifier)
    {QEvent.MouseButtonPress: v.mousePressEvent, QEvent.MouseMove: v.mouseMoveEvent,
     QEvent.MouseButtonRelease: v.mouseReleaseEvent}[kind](ev)


def test_dragging_across_words_highlights_them(win, tmp_path, monkeypatch):
    uw, t = _add_text(win, tmp_path, monkeypatch)
    v = uw.texts.lines
    v.resize(900, 400)
    i = 0
    spec = next(s for s in v.fields if s.key == "Translation:en")
    spans = v._word_spans(i, spec)                            # ‘the hare ran’
    y = next(oy + h // 2 for s, oy, h in v._cells[i].rows if s.key == spec.key)
    _press(v, spans[1][0] + 2, y)
    _press(v, spans[2][1] - 2, y, QEvent.MouseMove)
    _press(v, spans[2][1] - 2, y, QEvent.MouseButtonRelease, Qt.NoButton)
    line, key, words = v.text_selection()
    assert line is v.rows[0] and key == "Translation:en" and words == "hare ran"   # no closing quote
    _press(v, spans[0][0] + 2, y)                             # a click elsewhere clears it
    _press(v, spans[0][0] + 2, y, QEvent.MouseButtonRelease, Qt.NoButton)
    assert v.text_selection() is None


def test_create_token_fills_in_only_the_highlighted_words(win, tmp_path, monkeypatch):
    from lemmatrix.ui import move_dialog, token_dialog
    uw, t = _add_text(win, tmp_path, monkeypatch)
    db = win.doc.db
    target = db.new_entry("D900", "kɔ", "hare")              # no tokens: no soundfile name to clash with
    target.tokens = []
    db.entries.append(target)
    seen = {}
    monkeypatch.setattr(move_dialog.CreateTokenDialog, "exec", lambda self: seen.update(
        first=self.entries[:1], heading=self.windowTitle()) or 1)
    monkeypatch.setattr(move_dialog.CreateTokenDialog, "chosen", lambda self: target)

    def fake_exec(dlg):
        seen["fields"] = {k: ed.text() for k, ed in dlg.edits.items()}
        seen["entry"] = dlg.slot.entry
        dlg._ok()
        return 1
    monkeypatch.setattr(token_dialog.TokenDialog, "exec", fake_exec)
    v = uw.texts.lines
    n = len(target.tokens)
    v.select_words(v.rows[0], "Translation:en", 1, 2)           # ‘the hare ran’ → hare ran
    line, key, words = v.text_selection()
    uw.texts.create_token(line, key, words)
    assert seen["entry"] is target and seen["fields"]["Translation"] == "hare ran"
    assert not seen["fields"]["Phonetic"] and not seen["fields"].get("Phonemic")
    assert len(target.tokens) == n + 1 and target.tokens[-1].get("Translation", "en") == "hare ran"
    v.select_words(v.rows[0], "Phonetic", 0, 0)                 # ʔəŋ from the Phonetic line
    line, key, words = v.text_selection()
    assert words == "ʔəŋ"
    monkeypatch.setattr(token_dialog.TokenDialog, "exec", lambda dlg: seen.update(
        fields={k: ed.text() for k, ed in dlg.edits.items()}) or 0)
    uw.texts.create_token(line, key, words)
    assert seen["fields"]["Phonetic"] == "ʔəŋ" and not seen["fields"]["Translation"]


def test_lemmas_matching_the_words_come_first(app):
    from lemmatrix.defaults import new_database
    from lemmatrix.ui.move_dialog import matching_first
    db = new_database()
    db.entries += [db.new_entry("D001", "kʊ", "cow"), db.new_entry("D002", "dɔ", "dog")]
    b = db.entries[-1]
    assert matching_first(db, "my dog")[0] is b


def test_the_pitch_scratchpad(win, tmp_path, monkeypatch):
    uw, t = _add_text(win, tmp_path, monkeypatch)
    p = uw.texts
    played = []
    monkeypatch.setattr(win, "play_pitch", lambda text: played.append(text))
    p.scratch.setText("55 3:3 21")
    assert p.scratch_canvas.text == "55 3:3 21"
    uw.play_pitch()                                          # Ctrl+Shift+Space on the Texts tab
    assert played == ["55 3:3 21"]
    from PySide6.QtTest import QTest
    QTest.keyClicks(p.scratch, " x4")                       # only pitch notation can be typed
    assert p.scratch.text() == "55 3:3 21 4"
    uw.close()
    assert win.open_utterances().texts.scratch.text() == ""    # cleared with the window


def test_the_lines_search_sits_with_its_field_and_next_empty(win, tmp_path, monkeypatch):
    uw, t = _add_text(win, tmp_path, monkeypatch)
    p = uw.texts
    assert p.line_search.maximumWidth() <= 320


def test_texts_worked_on_are_kept_in_the_notebook_file(tmp_path):
    from lemmatrix import notebook as nbmod
    from lemmatrix.defaults import new_database
    from lemmatrix.model import Text
    db = new_database()
    t = Text(ref="T001")
    nb = nbmod.Notebook()
    assert nbmod.note_text_worked_on(nb, db, "2026-10-20", t)
    assert not nbmod.note_text_worked_on(nb, db, "2026-10-20", t)      # once a day
    path = tmp_path / "Lex.notebook"
    nbmod.save(nb, path)
    assert nbmod.load(path).session("2026-10-20").texts == [t.id]


def _matrix_wheel(view, delta, mods):
    pos = QPointF(50, 30)
    view.wheelEvent(QWheelEvent(pos, view.viewport().mapToGlobal(pos), QPoint(), QPoint(0, delta), Qt.NoButton,
                                mods, Qt.NoScrollPhase, False))


def test_ctrl_wheel_zooms_a_matrix_and_ctrl_0_resets_it(win):
    from PySide6.QtTest import QTest
    from lemmatrix.ui.main_window import LEMMA_TAG
    from lemmatrix import matrix as mx
    win.tabs.setCurrentIndex(LEMMA_TAG)
    cfg = win.config_for(LEMMA_TAG)
    cfg.x = [mx.Spec.citation(), mx.Spec(frozenset({"Plural"}), mx.EXACT)]
    win.refresh()
    view = win._view(LEMMA_TAG)
    assert view.model_.layout_.cols
    col_w = view.horizontalHeader().sectionSize(0)
    d = view.delegate
    size, unit = d.ipa.pointSize(), d.unit
    _matrix_wheel(view, 240, Qt.ControlModifier)
    assert view.zoom > 1.0 and d.ipa.pointSize() > size and d.unit > unit
    assert view.horizontalHeader().chip_font.pointSizeF() > view.font().pointSizeF()
    assert view.horizontalHeader().sectionSize(0) > col_w                # sized from the content again
    win.refresh()                                                      # the zoom stays with the view
    assert view.zoom > 1.0 and view.delegate.ipa.pointSize() > size
    _matrix_wheel(view, 120, Qt.NoModifier)                    # an ordinary wheel still scrolls
    assert view.zoom > 1.0
    QTest.keyClick(view, Qt.Key_0, Qt.ControlModifier)
    assert view.zoom == 1.0 and d.ipa.pointSize() == size


def test_a_bookmark_per_text(win, tmp_path, monkeypatch):
    """IDEAS.md idea 32: one bookmark per text, set in edit mode in the margin, kept in the
    workspace by start time, and the text opens at it."""
    from lemmatrix.ui.lines_view import MARGIN
    uw, t = _add_text(win, tmp_path, monkeypatch)
    p = uw.texts
    v = p.lines
    v.resize(900, 400)
    assert MARGIN == 40
    c = v._cells[1]
    pos = v._bookmark_rect(c, c.y).center()
    assert v._hit(pos.toPoint())[1] == "bookmark"
    _press(v, pos.x(), pos.y())                               # outside edit mode: nothing
    assert v.bookmark is None
    p.set_edit_mode(True)
    steps = win.doc.undo.count()
    _press(v, pos.x(), pos.y())                               # golden
    assert v.bookmark == v.rows[1].id and win.doc.ws.get_dict("bookmarks") == {t.id: v.rows[1].start}
    assert win.doc.undo.count() == steps                      # not an undo step
    c0 = v._cells[0]
    p0 = v._bookmark_rect(c0, c0.y).center()
    _press(v, p0.x(), p0.y())                                 # moved to the first line
    assert v.bookmark == v.rows[0].id and win.doc.ws.get_dict("bookmarks")[t.id] == v.rows[0].start
    _press(v, p0.x(), p0.y())                                 # again: gone
    assert v.bookmark is None and win.doc.ws.get_dict("bookmarks") == {}
    _press(v, pos.x(), pos.y())
    p.set_edit_mode(False)
    uw.close()
    uw = win.open_utterances()                                # opened again: at the bookmark
    v = uw.texts.lines
    assert v.bookmark == v.rows[1].id and v.current_row() is v.rows[1]
    v.select_row(v.rows[0])
    uw.show()
    uw.texts.go_to_bookmark()                                 # Ctrl+G
    assert v.current_row() is v.rows[1]


def test_the_bookmark_finds_the_nearest_line_when_a_boundary_moves(win, tmp_path, monkeypatch):
    uw, t = _add_text(win, tmp_path, monkeypatch)
    p = uw.texts
    win.doc.ws_set("bookmarks", {t.id: 2.05})                 # the second line started at 2.0
    p._bookmark_shown_for = None
    p._show_lines()
    assert p.lines.bookmark == p.lines.rows[1].id
