# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders. Additional terms: NOTICE.md
"""Small features, 21 October night (Josh's triage): a lone pitch digit as an extra-short trace,
Sentence-ify, Clear fields in Bulk edit's Replace, the recording source in the token dialogue,
the pitch-looking text warning, saved matrices in a hierarchy, the To Do button and shortcut,
and several items in a quick search."""

import os
import shutil
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["LEMMATRIX_SETTINGS"] = "Lemmatrix-tests"

from test_texts import app, win  # noqa: E402,F401

from lemmatrix import bulk, matrix as mx, pitch, storage  # noqa: E402

SAMPLES = Path(__file__).resolve().parent / "data" / "sample"


# ---- a lone pitch digit (IDEAS.md idea 14) -----------------------------------

def test_a_lone_digit_is_an_extra_short_level():
    syl = pitch.parse("5")[0]
    assert syl.points == [5, 5] and syl.steps == [pitch.EXTRA_SHORT]
    assert syl.length < pitch.parse("55")[0].length
    assert pitch.normalise("5  3, 13") == "5 3, 13"          # no longer doubled
    assert pitch.normalise("55 3:3") == "55 3:3"              # existing data unchanged
    from lemmatrix import pitchsound
    tracks = [t for t in pitchsound.contour("5 55") if not isinstance(t, int)]
    assert 0 < len(tracks[0]) < len(tracks[1])                # played as a briefer tone


def test_a_lone_digit_draws_narrower():
    from lemmatrix.ui.widgets import pitch_width
    assert 0 < pitch_width("5") < pitch_width("55")


# ---- Sentence-ify (idea 18) ----------------------------------------------------

def test_sentenceify():
    assert bulk.sentenceify("the dog ran") == "The dog ran."
    assert bulk.sentenceify("‘go home’", "!") == "‘Go home’!"
    assert bulk.sentenceify("Did he go?") == "Did he go?"      # already punctuated
    assert bulk.sentenceify("he said “go!”") == "He said “go!”"
    assert bulk.sentenceify("wait…") == "Wait…"
    assert bulk.sentenceify("") == ""
    assert bulk.sentence_mark(["Interrogative"]) == "?"
    assert bulk.sentence_mark(["Imperative", "2SG"]) == "!"
    assert bulk.sentence_mark(["Indicative"]) == "." and bulk.sentence_mark([]) == "."


def test_sentenceify_in_bulk_edit(tmp_path):
    shutil.copy2(SAMPLES / "Sample.xml", tmp_path / "Sample.xml")
    shutil.copytree(SAMPLES / "Soundfiles", tmp_path / "Soundfiles")
    db = storage.load(tmp_path / "Sample.xml")
    key = next(t.key for t in bulk.targets(db, bulk.TOKENS) if t.role == "translation")
    tgt = bulk.target(db, bulk.TOKENS, key)
    e, i = db.entries[0], 0
    e.tokens[i].tags = ["Imperative"]
    bulk._put(tgt, e, e.tokens[i], "go home")
    p = bulk.plan(db, bulk.TOKENS, [(e, i)], bulk.RunShortcut(key, "sentence", "on"))
    assert p.ok and p.changes and p.changes[0].new == "Go home!"
    phon = next(t.key for t in bulk.targets(db, bulk.TOKENS) if t.role == "phonetic")
    try:
        bulk.plan(db, bulk.TOKENS, [(e, i)], bulk.RunShortcut(phon, "sentence", "on"))
        assert False, "Sentence-ify is for translations only"
    except bulk.BulkError:
        pass


# ---- quick search for several items (idea 29) --------------------------------

def test_search_terms_and_marks():
    from lemmatrix.ui import searchmark as sm
    assert sm.terms("dog, cat ,hare") == ["dog", "cat", "hare"]
    assert sm.terms("go\\, walk") == ["go, walk"]
    assert sm.terms(",") == [","]
    assert sm.found("a black cat", "dog, cat") and not sm.found("a goat", "dog, cat")
    assert sm.found("go, walk", "go\\, walk") and not sm.found("go walk", "go\\, walk")
    assert sm.spans("the dog and cat", "dog, cat") == [(4, 7), (12, 15)]
    assert sm.spans("the dog", "dog") == [(4, 7)]


def test_lemma_list_search_with_commas(win):
    db = win.doc.db
    a, b = db.entries[0], db.entries[1]
    ga, gb = db.gloss(a), db.gloss(b)
    win.lemma_search.setText(f"{ga}, {gb}")
    shown = {e.ref for e in win.lemmas.visible_rows()}
    assert {a.ref, b.ref} <= shown
    win.lemma_search.setText("")


# ---- saved matrices in a hierarchy (idea 37) ---------------------------------

def test_matrix_tree():
    assert mx.tidy_matrix_name(" Imperative > Basic ") == "Imperative>Basic"
    assert mx.shown_matrix_name("Imperative>Basic") == "Imperative › Basic"
    rows = mx.matrix_tree(["Basic Tense", "Imperative>Basic", "Imperative", "Imperative>Negative>Past"])
    assert rows == [("Basic Tense", 0, "Basic Tense"), ("Imperative", 0, "Imperative"),
                    ("Basic", 1, "Imperative>Basic"), ("Negative", 1, None),
                    ("Past", 2, "Imperative>Negative>Past")]


def test_saved_matrix_drop_down_groups(win):
    from lemmatrix.ui.main_window import LEMMA_TAG
    cfg = win.config_for(LEMMA_TAG)
    mats = win.doc.db.settings.matrices
    base = mx.MatrixConfig(kind=cfg.kind)
    for name in ("Imp>Basic", "Imp>Neg>Past"):
        m = base.copy()
        m.name = name
        mats.append(m)
    win._fill_saved(LEMMA_TAG)
    cb = win.lt_bar["saved"]
    heading = next(i for i in range(cb.count()) if cb.itemText(i) == "Imp")
    assert cb.itemData(heading) is None and not cb.model().item(heading).isEnabled()
    past = cb.findData("Imp>Neg>Past")
    assert past > heading and cb.itemText(past).strip() == "Past"
    win._saved_chosen(LEMMA_TAG, past)
    assert win.config_for(LEMMA_TAG).name == "Imp>Neg>Past"
    win._saved_chosen(LEMMA_TAG, heading)                      # a heading opens nothing
    assert win.config_for(LEMMA_TAG).name == "Imp>Neg>Past"
    mats[:] = [m for m in mats if not m.name.startswith("Imp>")]


# ---- To Do button and shortcut (idea 38) -------------------------------------

def test_todo_button_and_shortcut(win):
    assert not win.todo_btn.icon().isNull()
    from PySide6.QtGui import QAction
    acts = [a for a in win.findChildren(QAction) if a.text().replace("&", "") == "To Do"]
    assert acts and acts[0].shortcut().toString() == "Ctrl+Shift+T"


# ---- the token dialogue: source, pitch warning; Bulk edit's Clear ------------

def test_recording_source_follows_settings(win):
    from lemmatrix.ui.token_dialog import Slot, TokenDialog
    e = win.doc.db.entries[0]
    old = win.prefs.record_source
    dlg = TokenDialog(win, [Slot(e, 0)], 0)
    assert dlg.source_box.currentData() == old
    other = "computer" if old != "computer" else "microphone"
    dlg.source_box.setCurrentIndex(dlg.source_box.findData(other))
    assert win.prefs.record_source == other
    dlg.reject()
    win.prefs.record_source = old


def test_pitch_like_text(win, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    from lemmatrix.ui.token_dialog import Slot, TokenDialog
    assert TokenDialog.PITCH_LIKE.match("55 3:3, 21") and not TokenDialog.PITCH_LIKE.match("da55")
    assert not TokenDialog.PITCH_LIKE.match(":: ,")
    e = win.doc.db.entries[0]
    dlg = TokenDialog(win, [Slot(e, 0)], 0)
    s = win.doc.db.settings
    phon = next(ed for n, ed in dlg.edits.items() if s.token_field(n).role == "phonetic")
    ptch = next(ed for n, ed in dlg.edits.items() if s.token_field(n).role == "pitch")
    phon.setText("55 21")

    def press(label):
        def exec_(box):
            box._clicked = next(b for b in box.buttons() if label in b.text())
            return 0
        return exec_
    monkeypatch.setattr(QMessageBox, "exec", press("Move it to Pitch"))
    monkeypatch.setattr(QMessageBox, "clickedButton", lambda box: box._clicked)
    assert dlg.check_pitch_like()
    assert ptch.text() == "55 21" and phon.text() == ""
    phon.setText("3:3")
    monkeypatch.setattr(QMessageBox, "exec", press("Cancel"))
    assert not dlg.check_pitch_like() and phon.text() == "3:3"
    phon.setText("dabuuba")
    assert dlg.check_pitch_like()
    dlg.reject()


def test_bulk_replace_clear_fields(win):
    from lemmatrix.ui.bulk_window import BulkEditWindow
    w = BulkEditWindow(win)
    w.r_find.setText("y")
    w.r_repl.setText("j")
    w.r_clear.click()
    assert w.r_find.text() == "" and w.r_repl.text() == ""
    w.close()


# ---- Settings in the File menu (Josh, 22 October) ----------------------------

def test_settings_is_in_the_file_menu(win):
    menus = {m.title().replace("&", ""): m for m in (a.menu() for a in win.menuBar().actions()) if m}
    texts = [a.text().replace("&", "") if not a.isSeparator() else "—" for a in menus["File"].actions()]
    assert texts[-3:] == ["Settings…", "—", "Exit"] and texts[-4] == "—"
    act = win.settings_action
    assert act.shortcut().toString() == "Ctrl+," and not act.icon().isNull()
    assert "Settings…" not in [a.text().replace("&", "") for a in menus["Edit"].actions()]


# ---- the menus reviewed (Josh's TWEAK, 22 October) ----------------------------

def _menus(win):
    return {a.text().replace("&", ""): a.menu() for a in win.menuBar().actions() if a.menu()}


def _texts(menu):
    return ["—" if a.isSeparator() else a.text().replace("&", "") for a in menu.actions()]


def test_menus_after_the_review(win):
    from lemmatrix.ui.main_window import ALL_DATA, LEMMA_TAG
    m = _menus(win)
    assert list(m)[-3:] == ["Analyze", "Compose", "Help"]
    assert "version 2" in _texts(m["Analyze"])[0] and "version 3" in _texts(m["Compose"])[0]
    assert "Open folder" in _texts(m["File"]) and not any("sample" in t for t in _texts(m["File"]))
    assert "Write to notebook" in _texts(m["Edit"])
    assert "ɛλicit" in _texts(m["Tools"]) and "Open the sound folder" not in _texts(m["Tools"])
    view = _texts(m["View"])
    assert view[-1] != "—" and "Matrix" in view and "Swap rows and columns" not in view
    help_ = _texts(m["Help"])
    assert "Keyboard shortcuts…" in help_ and "Sample databases" in help_
    q = next(a for a in m["View"].actions() if a.text().replace("&", "") == "Questions")
    assert q.shortcut().toString() == "Ctrl+Shift+Q"
    win.tabs.setCurrentIndex(ALL_DATA)
    assert not win.matrix_edit_action.isEnabled()
    win.tabs.setCurrentIndex(LEMMA_TAG)
    assert win.matrix_edit_action.isEnabled() and win.matrix_edit_action.shortcut().toString() == "Ctrl+E"


def test_open_folder_menu(win, monkeypatch):
    opened = []
    monkeypatch.setattr(win, "open_folder", lambda f: opened.append(f))
    win._fill_folder_menu()
    acts = [a for a in win.folder_menu.actions() if not a.isSeparator()]
    labels = [a.text() for a in acts]
    assert labels[0] == "Main folder" and "Soundfiles › Tokens" in labels and "Exports" in labels
    acts[0].trigger()
    from pathlib import Path
    assert opened and opened[0] == Path(win.doc.db.path).parent


def test_keyboard_shortcuts_list(win):
    rows = dict(win.shortcut_rows())
    flat = [d for r in rows.values() for _, d in r]
    assert any("Settings" in d for d in flat) and any("Edit mode" in d for d in flat)
    assert "A text's lines" in rows


def test_josh_questions_and_todo_icons_1022(app):
    """Josh's ? (23 October: a grey ring round a teal ?, replacing 22 October's) and To Do
    (three ✓ beside grey lines, 22 October)."""
    from lemmatrix.ui import icons
    q = icons.QUESTIONS_FILE.read_text(encoding="utf-8")
    assert "<text" not in q and q.count("<path") == 2      # the ring and the ?, as outlines
    t = icons.TODO_FILE.read_text(encoding="utf-8")
    assert "<text" not in t and t.count("<path") == 3     # the ticks are outlines, no font needed
    for name in ("questions", "todo"):
        assert not icons.icon(name, 48, "#123456").pixmap(48, 48).isNull()
