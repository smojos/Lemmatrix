# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders. Additional terms: NOTICE.md
"""⚡ Power search (IDEAS.md idea 86, Josh, 27 October): one search for every search bar; plain by
default (what's typed is found as typed), and with Power search on, `--` leaves out, `++` is AND,
`;;` is OR; Settings → Advanced → Fire."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["LEMMATRIX_SETTINGS"] = "Lemmatrix-tests"

import pytest  # noqa: E402
from PySide6.QtWidgets import QApplication, QLineEdit  # noqa: E402

from lemmatrix import search  # noqa: E402
from lemmatrix import wordlists as wl  # noqa: E402


@pytest.fixture
def power():
    search.set_power(True)
    yield
    search.set_power(False)


def _settle():
    for _ in range(5):
        QApplication.processEvents()


# ---- the parser ----------------------------------------------------------------------------

def test_plain_is_found_as_typed():
    for text in ("ba-túul", "go, walk", "goat ++ PL", "a ;; b", "--kid", "1SG/see"):
        q = search.parse(text, False)
        assert q.groups == ((search.fl.search_form(text.strip()),),) and not q.excluded
    assert not search.parse("   ", False)
    assert search.parse("Go, Walk", False).found("to go, walk away")


def test_power_operators():
    q = search.parse("goat ;; sheep --kid", True)
    assert q.groups == (("goat",), ("sheep",)) and q.excluded == ("kid",)
    assert q.matches(["goat"]) and q.matches(["sheep"]) and not q.matches(["goat", "kid"])
    assert not q.matches(["cow"])
    q = search.parse("--kid", True)                      # everything but kid
    assert q.matches(["goat"]) and not q.matches(["kid"])
    q = search.parse("goat ++ PL ;; sheep", True)       # ++ binds tighter
    assert q.matches(["goat", "pl"]) and q.matches(["sheep"]) and not q.matches(["goat"])
    assert search.parse("goat++PL", True).groups == (("goat", "pl"),)   # no spaces needed


def test_single_characters_are_always_text():
    for text in ("ba-túul", "1SG-see", "go, walk", "kp+a", "1SG/see", "a;b"):
        q = search.parse(text, True)
        assert len(q.groups) == 1 and len(q.groups[0]) == 1 and not q.excluded
    assert search.parse("ba-túul", True).found("ba-tuul")


def test_escapes():
    assert search.parse("x \\-- y", True).groups == (("x -- y",),)
    assert search.parse("a \\++ b", True).groups == (("a ++ b",),)
    assert search.parse("a \\;; b", True).groups == (("a ;; b",),)


def test_and_is_across_columns_never_inside_one_split():
    q = search.parse("goat ++ PL", True)
    assert q.matches(["a goat", "Plural".casefold()])
    q = search.parse("go walk", True)
    assert not q.matches(["go", "walk"])                 # one item never spans two columns


def test_diacritics_and_capitals_ignored():
    assert search.matches("TUUL", ["ba-túul"])
    assert search.matches("goat", ["GOAT"])


def test_marks_leave_out_the_left_out():
    q = search.parse("goat ++ PL ;; sheep --kid", True)
    assert q.marked == ["goat", "pl", "sheep"] and "kid" not in q.marked
    from lemmatrix.ui import searchmark
    search.set_power(True)
    try:
        assert searchmark.spans("goat kid", "goat --kid") == [(0, 4)]
    finally:
        search.set_power(False)


# ---- the lemma searches' own items ---------------------------------------------------------

def test_wordlist_items_lose_their_own_minus():
    assert wl.search_term("CAWL 345") == (wl.CAWL, "0345")
    assert wl.search_term("swadesh") == (wl.SWADESH, None)
    assert wl.search_term("-Swadesh") is None             # the single minus is gone
    assert wl.search_term("Joshua") == (wl.EACW, "V139")


def test_extras_only_with_power_on():
    extra = lambda t: True if t == "swadesh" else None     # noqa: E731
    assert search.parse("SWADESH", True).matches(["goat"], extra)
    assert not search.parse("SWADESH", False).matches(["goat"], extra)
    assert not search.parse("--SWADESH", True).matches(["goat"], extra)


def test_lemma_list_power_and_plain(win):
    db = win.doc.db
    wl.link_as_eacw(db)
    win.lemmas.set_rows(db.entries)
    t = win.lemmas
    with_sw = [e for e in db.entries if e.lists.get(wl.SWADESH)]
    assert with_sw
    win.lemma_search.setText("SWADESH")                   # plain: searched as text
    t.proxy.set_search("SWADESH")
    _settle()
    assert len(t.visible_rows()) < len(with_sw)
    search.set_power(True)
    try:
        _settle()
        t.proxy.set_search("SWADESH")
        assert len(t.visible_rows()) == len(with_sw)
        t.proxy.set_search("--SWADESH")
        assert len(t.visible_rows()) == len(db.entries) - len(with_sw)
        assert win.lemma_search.placeholderText() == search.PLACEHOLDER
    finally:
        search.set_power(False)
    assert win.lemma_search.placeholderText() != search.PLACEHOLDER
    t.proxy.set_search("")


def test_all_data_and_across_columns(win, power):
    t = win.all_table
    rows = t.model_.rows
    tok = next(r for r in rows if r.token.tags)
    tag = sorted(tok.token.tags)[0]
    gloss = win.doc.db.gloss(tok.entry)
    t.proxy.set_search(f"{gloss} ++ {tag}")
    shown = t.visible_rows()
    assert any(r.token is tok.token for r in shown)
    t.proxy.set_search(f"{gloss} --{tag}")
    assert all(tag not in r.token.tags for r in t.visible_rows())
    t.proxy.set_search("")


def test_switching_searches_again(win):
    t = win.lemmas
    t.proxy.set_search("zz ;; " + win.doc.db.gloss(win.doc.db.entries[0]))
    assert t.visible_rows() == []                          # plain: the ;; is text
    search.set_power(True)
    try:
        assert t.visible_rows()                            # read again with the operators
    finally:
        search.set_power(False)
    t.proxy.set_search("")


def test_placeholder_follows_the_switch(app):
    e = QLineEdit()
    e.setPlaceholderText("Search the notebook")
    from lemmatrix.ui.searchmark import power_placeholder
    power_placeholder(e)
    search.set_power(True)
    try:
        assert e.placeholderText() == "⚡ Power search"
    finally:
        search.set_power(False)
    assert e.placeholderText() == "Search the notebook"


# ---- the other searches --------------------------------------------------------------------

def test_notebook_and_hypotheses(power):
    from lemmatrix import hypotheses as hy
    h = hy.Hypothesis(id="h1", number=1, summary="Tone spreads rightward", formulation="Only in verbs")
    assert hy.matches(h, "tone ++ verbs") and not hy.matches(h, "tone --verbs")
    assert hy.matches(h, "nouns ;; spreads")


# ---- Settings → Advanced -------------------------------------------------------------------

def test_settings_advanced(win):
    from PySide6.QtWidgets import QGroupBox, QTabWidget
    from lemmatrix.ui.dialogs import PreferencesDialog
    win.prefs.set_value(search.POWER_KEY, False)
    dlg = PreferencesDialog(win, win.doc.db, win.prefs)
    tabs = dlg.findChild(QTabWidget)
    names = [tabs.tabText(i) for i in range(tabs.count())]
    assert names[-1] == "Advanced"
    titles = [b.title() for b in dlg.findChildren(QGroupBox)]
    assert "Fire (this computer)" in titles and "Women" in titles and "Dangerous things" in titles
    assert not dlg.power_search.isChecked()
    dlg.power_search.setChecked(True)
    dlg.apply()
    try:
        assert search.power() and win.prefs.get_bool(search.POWER_KEY)
    finally:
        win.prefs.set_value(search.POWER_KEY, False)
        search.set_power(False)
    dlg.reject()


def test_never_in_the_menus(win):
    texts = []

    def walk(menu):
        for a in menu.actions():
            texts.append(a.text())
            if a.menu():
                walk(a.menu())
    for a in win.menuBar().actions():
        if a.menu():
            walk(a.menu())
    assert not any("power" in t.casefold() or "advanced" in t.casefold() for t in texts)
