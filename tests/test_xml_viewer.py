# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders
"""The XML viewer (IDEAS.md idea 23, 21 October): read-only, opening at the selected token or lemma."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["LEMMATRIX_SETTINGS"] = "Lemmatrix-tests"

from PySide6.QtWidgets import QApplication  # noqa: E402

from lemmatrix import storage, xmlview  # noqa: E402
from test_ui import app, win  # noqa: E402,F401


def test_line_of_finds_entries_and_tokens():
    text = '<a>\n<entry ref="A001" id="e1">\n  <token tags="PL" id="t9">\n</entry>\n'
    assert xmlview.line_of(text, "entry", "e1") == 1
    assert xmlview.line_of(text, "token", "t9") == 2
    assert xmlview.line_of(text, "token", "e1") is None
    assert xmlview.line_of(text, "entry", "") is None


def test_search_ignores_diacritics_and_capitals():
    f = xmlview.FoldedText("<Phonetic>dɪ́ɪtʰ</Phonetic> DÁ")
    hits = f.find_all("da")
    assert [f.text[s:e] for s, e in hits] == ["DÁ"]
    assert f.find_all("phonetic") and len(f.find_all("phonetic")) == 2
    assert f.find_all("") == []


def test_button_sits_between_elicit_and_questions(win):
    order = [win.head_icons.itemAt(i).widget() for i in range(win.head_icons.count())]
    assert [order.index(b) for b in (win.elicit_btn, win.xml_btn, win.cogitate_btn, win.questions_btn,
                                     win.todo_btn, win.texts_btn)] \
        == [0, 1, 2, 3, 4, 5]                # ɛλicit, XML viewer, Cogitate, Questions, To Do, Texts and utterances
    assert not win.xml_btn.icon().isNull()


def test_opens_read_only_at_the_beginning_with_nothing_selected(win, monkeypatch):
    monkeypatch.setattr(win, "xml_target", lambda: None)
    w = win.open_xml_viewer()
    assert w.text.isReadOnly()
    assert w.text.toPlainText() == storage.to_string(win.doc.db)
    assert w.text.textCursor().blockNumber() == 0
    assert w.text.verticalScrollBar().value() == 0


def _line(w):
    return w.text.document().findBlockByNumber(w.text.textCursor().blockNumber()).text()


def test_opens_at_the_selected_lemma_then_the_selected_token(win):
    db = win.doc.db
    e = next(e for e in db.entries[5:] if len(e.tokens) > 1)
    win.go_to(e)
    win.all_table.clearSelection()
    win.all_table.setCurrentIndex(win.all_table.model().index(-1, -1))
    assert win.xml_target() == ("entry", e.id)
    w = win.open_xml_viewer()
    assert _line(w).lstrip().startswith("<entry") and f'id="{e.id}"' in _line(w)
    assert w.target_line == w.text.textCursor().blockNumber()
    win.go_to(e, 1)                                  # a token in All data wins over the lemma
    assert win.xml_target() == ("token", e.tokens[1].id)
    w = win.open_xml_viewer()
    assert _line(w).lstrip().startswith("<token") and f'id="{e.tokens[1].id}"' in _line(w)


def test_unsaved_changes_show_on_coming_back(win):
    w = win.open_xml_viewer()
    before = w.shown_text
    e = win.doc.db.entries[0]
    win.doc.edit_entry(e, lambda en: en.set("Comment", "zqxv marker", None, False), "Edit Comment")
    assert w.refresh() is True
    assert "zqxv marker" in w.text.toPlainText() and w.shown_text != before
    assert "unsaved" in w.where.text()
    w.search.setText("ZQXV")
    w.run_search()
    assert len(w.matches) == 1 and w.count.text() == "1 / 1"
    s, e2 = w.matches[0]
    assert w.shown_text[s:e2] == "zqxv"
    w.close()
    QApplication.processEvents()
