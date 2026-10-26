# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders. Additional terms: NOTICE.md
"""The empty-data toggles (IDEAS.md idea 74, Josh, 26 October): Hide empty lemmas (λ) and Hide
empty tokens (τ, was the checkbox Show only lemmas with token data) as icon toggles in the options
bars, a red line across while on; Clear all filters turns them off."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def test_hide_empty_tokens_is_a_toggle_in_each_tabs_options_bar(win):
    a, lt, tt = win.hide_tokens_btns
    assert all(b.isCheckable() and b.text() == "Hide empty tokens" for b in (a, lt, tt))
    assert win.only_data is a
    lt.setChecked(True)                                    # one setting: the others follow
    assert a.isChecked() and tt.isChecked() and win.doc.ws.get_bool("only_with_data")
    a.setChecked(False)
    assert not lt.isChecked() and not tt.isChecked()


def test_the_icons_have_an_on_look(win):
    from PySide6.QtGui import QIcon
    ic = win.hide_empty.icon()
    off = ic.pixmap(20, 20, QIcon.Normal, QIcon.Off).toImage()
    on = ic.pixmap(20, 20, QIcon.Normal, QIcon.On).toImage()
    assert off != on                                       # the red line while on


def test_clear_all_filters_turns_them_off(win):
    win.hide_empty.setChecked(True)
    win._clear_lemma_filters()
    assert not win.hide_empty.isChecked()
    win.only_data.setChecked(True)
    win._clear_all_filters()
    assert not win.only_data.isChecked() and not win.hide_tokens_btns[1].isChecked()


def test_a_link_still_says_what_it_turned_off(win):
    from lemmatrix.model import Token
    e = win.doc.db.new_entry(win.doc.db.next_ref("D") if hasattr(win.doc.db, "next_ref") else "D998", gloss="empty")
    e.tokens = [Token()]
    win.doc.db.entries.append(e)
    win.lemmas.set_rows(win.doc.db.entries)
    win.hide_empty.setChecked(True)
    win.lemma_search.setText("zzzz-no-such")
    assert win.go_to(e) is not False
    assert not win.hide_empty.isChecked()
    assert "Hide empty lemmas" in win.statusBar().currentMessage()
