# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders
"""Spelling: English translations and glosses checked against two word lists and the database's own."""

from pathlib import Path

import pytest

from lemmatrix import spelling, storage

SAMPLES = Path(__file__).resolve().parent / "data" / "sample"    # the prototype's sample (conftest.py)
pytestmark = pytest.mark.skipif(not spelling.available(), reason="no spelling dictionaries installed")


@pytest.fixture
def db():
    return storage.load(SAMPLES / "Sample.xml")


def words(checker, text):
    return [w for _, _, w in checker.misspelled(text)]


def test_english_both_spellings_and_little_words():
    c = spelling.Checker()
    assert words(c, "of the goats and the colour, he doesn't eat it") == []
    assert words(c, "I recognise the goat's horn; the goats' house; mother-in-law") == []
    assert words(c, "recieve teh goatt") == ["recieve", "teh", "goatt"]


def test_conventions_and_transcriptions_are_not_checked():
    c = spelling.Checker()
    assert words(c, "goat (pl, xyzzy) 1SG PL f2 xH ɗæær [qqq]") == []
    assert words(c, "Recieve") == ["Recieve"]


def test_suggestions_keep_a_capital():
    c = spelling.Checker()
    assert c.suggestions("recieve")[0] == "receive"
    assert c.suggestions("Goatt")[0] == "Goat"


def test_the_word_list():
    c = spelling.Checker(["Pade", "tilapia"])
    assert words(c, "in Pade, the tilapia; Tilapia") == []
    c.set_words([])
    assert words(c, "in Pade") == ["Pade"]


def test_word_list_is_saved_in_the_workspace(db, tmp_path):
    from lemmatrix import workspace
    db.settings.spelling_words = ["tilapia", "Pade"]
    storage.save(db, tmp_path / "x.xml", backup=False)
    assert "<spelling" not in (tmp_path / "x.xml").read_text(encoding="utf-8")   # format 7: not in the database
    workspace.save(workspace.Workspace(), db)
    text = (tmp_path / "x.workspace").read_text(encoding="utf-8")
    assert "<spelling>" in text and "<word>Pade</word>" in text
    again = storage.load(tmp_path / "x.xml")
    workspace.load(tmp_path / "x.workspace", again)
    assert sorted(again.settings.spelling_words) == ["Pade", "tilapia"]


def test_no_word_list_writes_nothing(db, tmp_path):
    storage.save(db, tmp_path / "x.xml", backup=False)
    assert "<spelling" not in (tmp_path / "x.xml").read_text(encoding="utf-8")


def test_scan_and_replace(db):
    goat = db.entry_by_ref("D001")
    goat.tokens[2].set("Translation", "of the goatt", "en")
    goat.tokens[3].set("Translation", "Goatt's", "en")
    goat.set("Gloss", "goatt", "en", True)
    found = spelling.scan(db)
    u = next(x for x in found if x.word.lower() == "goatt")
    assert u.count == 3 and u.where() == "Gloss, Translation"
    pairs = spelling.replacements(db, u, "goat")
    assert len(pairs) == 1
    after = pairs[0][1]
    assert after.get("Gloss", "en") == "goat"
    assert after.tokens[2].get("Translation", "en") == "of the goat"
    assert after.tokens[3].get("Translation", "en") == "Goat's"
    assert goat.tokens[2].get("Translation", "en") == "of the goatt"       # nothing changed yet


def test_replace_whole_words_only():
    assert spelling.replace_word("teh tehran teh", "teh", "the") == "the tehran the"


def test_soundfile_is_a_word():
    c = spelling.Checker([])
    assert c.known("soundfile") and c.known("Soundfiles") and c.known("soundfile's")
