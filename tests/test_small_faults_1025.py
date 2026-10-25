# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders. Additional terms: NOTICE.md
"""The audit's smaller faults, left out of the report (25 October 2026): windows freed when
closed and not redrawn while hidden, a hidden window following a theme change, the Wordlist
export's form, TextGrid stamps, a request card with a field this version doesn't know, and
Ctrl+Space in a window with nothing to play."""

import datetime as dt
import json
import os

import shiboken6
from PySide6.QtCore import QCoreApplication, QEvent, Qt
from PySide6.QtGui import QKeyEvent, QKeySequence, QShortcut
from PySide6.QtWidgets import QDialog, QLineEdit, QVBoxLayout

from lemmatrix import elicit as el, textgrid as tgmod, wordlists as wl
from lemmatrix.model import Token


def _flush_deletes():
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    QCoreApplication.processEvents()


# ---------------------------------------------------------------- windows

def test_closed_windows_are_freed(win):
    win.open_bulk_edit()
    bw = win.bulk_window
    win.check_spelling()
    sw = win.spelling_window
    win.open_utterances()
    uw = win.utterances_window
    for w in (bw, sw, uw):
        w.close()
    _flush_deletes()
    assert not any(shiboken6.isValid(w) for w in (bw, sw, uw))       # kept hidden before
    assert win.bulk_window is win.spelling_window is win.utterances_window is None
    win.open_bulk_edit()                                              # and they open again
    assert win.bulk_window.isVisible()
    win.bulk_window.close()


def test_the_hidden_notebook_isnt_redrawn(win):
    day = win.doc.notebook.add_session("2026-10-20")
    day.notes = "A day's notes."
    win.open_notebook("2026-10-20")
    d = win.notebook_dialog
    shown = d.notes.toPlainText()
    d.hide()
    d.session.notes = shown + "\nH1 made: a new hypothesis"
    d._hypotheses_changed()
    assert d.notes.toPlainText() == shown                            # hidden: left until it is opened
    win.open_notebook("2026-10-20")
    assert "H1 made" in d.notes.toPlainText()                        # opened: as it is now
    d.close()


def test_a_hidden_window_follows_a_theme_change_when_shown(win, monkeypatch):
    w = win.open_xml_viewer()
    w.hide()
    calls = []
    monkeypatch.setattr(w, "_restyle", lambda: calls.append(1))
    win.toggle_theme()
    assert calls == []                                                # hidden: nothing yet
    w.show()
    assert calls == [1]                                               # shown: restyled once
    w.hide()
    w.show()
    assert calls == [1]
    win.toggle_theme()                                                # back to the theme it had
    w.close()


# ---------------------------------------------------------------- the Wordlist export's form

def test_the_export_never_takes_a_plural_as_the_form(win):
    db = win.doc.db
    ph = db.settings.token_field("phonetic").name
    tags = db.settings.tags
    default = next(t.name for t, _ in tags.tags() if t.default)
    plural = next(t.name for t, _ in tags.tags() if not t.default and t.code)
    e = db.entries[0]
    lemma = db.settings.entry_field("lemma")
    if lemma is not None:
        e.set(lemma.name, "")
    pl = Token(tags=[plural])
    pl.set(ph, "plural-form")
    e.tokens = [pl]
    assert wl.export_form(db, e) == ""                              # was "plural-form"
    sg = Token(tags=[default])
    sg.set(ph, "default-form")
    e.tokens = [pl, sg]
    assert wl.export_form(db, e) == "default-form"                  # only default tags: the citation
    bare = Token()
    bare.set(ph, "citation-form")
    e.tokens = [pl, sg, bare]
    assert wl.export_form(db, e) == "citation-form"                 # no tags at all comes first


# ---------------------------------------------------------------- TextGrid stamps

def test_textgrid_stamps_tell_saves_within_a_second_apart(tmp_path):
    p = tmp_path / "t.TextGrid"
    p.write_text("x")
    base = int(dt.datetime(2026, 10, 25, 1, 30, 0).timestamp()) * 10**9
    os.utime(p, ns=(base + 100_000_000, base + 100_000_000))
    a = tgmod.modified(p)
    os.utime(p, ns=(base + 700_000_000, base + 700_000_000))         # saved again in the same second
    b = tgmod.modified(p)
    assert a != b
    assert a.endswith("+00:00")                                      # UTC: no jump when the clocks change


# ---------------------------------------------------------------- ɛλicit

def test_a_card_field_this_version_doesnt_know_keeps_the_request(tmp_path):
    d = {"format": el.FORMAT, "id": "abc", "created": "2026-10-25T07:00:00", "expires": "2026-11-01",
         "speaker": {"code": "SP1", "name": "SP1"}, "researcher": {"code": "RS1", "name": "RS1"},
         "database": {}, "languages": ["en"], "language_names": {}, "prompts": {}, "accent": "#198583",
         "cards": [{"n": 1, "kind": "new", "file": "01.wav", "added_in_a_later_version": True}],
         "something_new": 1}
    req = el.Request.from_dict(d)
    assert [c.n for c in req.cards] == [1] and req.cards[0].file == "01.wav"
    folder = tmp_path / "r"
    folder.mkdir()
    (folder / "request.json").write_text(json.dumps(d), encoding="utf-8")
    assert el.load_stored(folder) is not None                        # was dropped (None)


# ---------------------------------------------------------------- Ctrl+Space

def _ctrl_space(field):
    return QKeyEvent(QEvent.ShortcutOverride, Qt.Key_Space, Qt.ControlModifier, " ")


def test_ctrl_space_is_left_alone_where_nothing_plays(app):
    from lemmatrix.ui.ctrlspace import CtrlSpaceFilter
    f = CtrlSpaceFilter(held_fn=lambda: (True, False, False))
    dlg = QDialog()
    field = QLineEdit(dlg)
    QVBoxLayout(dlg).addWidget(field)
    dlg.show()
    assert f.eventFilter(field, _ctrl_space(field)) is False        # nothing to play: not swallowed
    played = []
    sc = QShortcut(QKeySequence("Ctrl+Space"), dlg)
    sc.activated.connect(lambda: played.append(1))
    assert f.eventFilter(field, _ctrl_space(field)) is True          # a window that plays: taken
    press = QKeyEvent(QEvent.KeyPress, Qt.Key_Space, Qt.ControlModifier, " ")
    f.eventFilter(field, press)
    assert played == [1]
    dlg.close()
