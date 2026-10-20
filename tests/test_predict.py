# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders
"""Predictive translation: templates from English translations, filled in with another gloss."""

from pathlib import Path

import pytest

from lemmatrix import predict, storage
from lemmatrix.model import Token

SAMPLES = Path(__file__).resolve().parent / "data" / "sample"    # the prototype's sample (conftest.py)
needs_inflection = pytest.mark.skipif(not predict.available(), reason="lemminflect isn't installed")


@pytest.fixture
def db():
    return storage.load(SAMPLES / "Sample.xml")


def add_lemma(db, ref, gloss, word_class, tokens):
    """tokens: (tags, English translation) pairs."""
    e = db.new_entry(ref, lemma=ref.lower(), gloss=gloss, word_class=word_class)
    e.tokens = [Token(tags=list(tags)) for tags, _ in tokens]
    for t, (_, text) in zip(e.tokens, tokens):
        if text:
            t.set("Translation", text, "en")
    db.entries.append(e)
    return e


# ---- templates -------------------------------------------------------------

def test_gloss_variants():
    assert predict.gloss_variants("goat") == [["goat"]]
    assert predict.gloss_variants("to run away") == [["to", "run", "away"], ["run", "away"]]
    assert predict.gloss_variants("father (address); dad") == [["father"]]
    assert predict.gloss_variants("(note only)") == []


def test_extract_unchanged_gloss():
    t = predict.extract("your father", "father")
    assert (t.prefix, t.suffix, t.tag) == ("your ", "", "")
    assert t.render("mother") == "your mother"
    assert t.render("older brother") == "your older brother"


def test_extract_keeps_the_words_around_it():
    t = predict.extract("of the goat (genitive)", "goat")
    assert t.render("lion") == "of the lion (genitive)"
    assert predict.extract("Father!", "father").render("mother") == "Mother!"


def test_whole_words_only():
    assert predict.extract("headache", "head") is None
    assert predict.extract("house of goats", "lion") is None


@needs_inflection
def test_inflected_glosses():
    t = predict.extract("goats", "goat", ["NOUN"])
    assert t.tag == "NNS"
    assert t.render("man") == "men"
    assert t.render("child") == "children"
    assert t.render("older brother") == "older brothers"
    t = predict.extract("he ate it", "to eat", ["VERB"])
    assert (t.prefix, t.suffix, t.tag, t.to) == ("he ", " it", "VBD", False)
    assert t.render("to run") == "he ran it"
    assert t.render("to run away") == "he ran away it"
    assert predict.extract("I have eaten", "eat", ["VERB"]).render("go") == "I have gone"
    assert predict.extract("he walks", "walk", ["VERB"]).tag == "VBZ"


def test_a_leading_to_is_kept_when_the_translation_has_it():
    t = predict.extract("to eat", "to eat", ["VERB"])
    assert t.render("to sleep") == "to sleep"


# ---- the predictor ---------------------------------------------------------

def test_suggests_from_tokens_with_the_same_tags(db):
    add_lemma(db, "C001", "father", "NOUN", [((), "father"), (("Singular", "Genitive"), "of my father")])
    mother = add_lemma(db, "C002", "mother", "NOUN", [((), "mother"), (("Singular", "Genitive"), "")])
    p = predict.Predictor()
    s = p.suggest(db, mother, ["Singular", "Genitive"])
    # the Sample's goat and lion say "of the goat", "of the lion"; father says "of my father"
    assert s.text == "of the mother"
    assert s.count == 3 and "goat" in s.sources
    assert "these tags" in s.describe()
    assert p.suggest(db, mother, ["Singular", "Genitive"], current="mum's") is None


def test_group_defaults_dont_count(db):
    goat = db.entry_by_ref("D001")
    # Sample tokens have isolation (a default); a token without it still matches, and the other way round
    assert predict.Predictor().suggest(db, goat, ["Singular", "Genitive"]).text == "of the goat"
    assert predict.Predictor().suggest(db, goat, ["Singular", "Genitive", "isolation"]).text == "of the goat"


def test_no_suggestion_without_a_template_or_a_gloss(db):
    goat = db.entry_by_ref("D001")
    p = predict.Predictor()
    assert p.suggest(db, goat, ["Ergative"]) is None
    bare = add_lemma(db, "D099", "", "NOUN", [((), "")])
    assert p.suggest(db, bare, ["Singular", "Genitive"]) is None


def test_the_word_class_comes_first(db):
    add_lemma(db, "V010", "to walk", "VERB", [((), "to walk")])
    add_lemma(db, "V011", "to run", "VERB", [((), "to run")])
    sing = add_lemma(db, "V012", "to sing", "VERB", [((), "")])
    cow = add_lemma(db, "D050", "cow", "NOUN", [((), "")])
    p = predict.Predictor()
    assert p.suggest(db, sing, []).text == "to sing"
    assert p.suggest(db, cow, []).text == "cow"      # nouns' citations: just the gloss


def test_follows_edits(db):
    mother = add_lemma(db, "C002", "mother", "NOUN", [(("Plural", "Accusative"), "")])
    father = add_lemma(db, "C001", "father", "NOUN", [(("Plural", "Accusative"), "my father")])
    p = predict.Predictor()
    assert p.suggest(db, mother, ["Plural", "Accusative"]).text == "my mother"
    father.tokens[0].set("Translation", "your father", "en")        # corrected
    assert p.suggest(db, mother, ["Plural", "Accusative"]).text == "your mother"
    db.entries.remove(father)
    assert p.suggest(db, mother, ["Plural", "Accusative"]) is None


def test_the_most_common_template_wins(db):
    for i, (g, text) in enumerate([("father", "your father"), ("uncle", "your uncle"),
                                   ("aunt", "thy aunt")]):
        add_lemma(db, f"C00{i}", g, "NOUN", [(("Plural", "Oblique"), text)])
    sister = add_lemma(db, "C009", "sister", "NOUN", [(("Plural", "Oblique"), "")])
    s = predict.Predictor().suggest(db, sister, ["Plural", "Oblique"])
    assert s.text == "your sister" and s.count == 2


@needs_inflection
def test_irregular_plural_from_regular_ones(db):
    sheep = db.entry_by_ref("D003")
    # learned from goats, lions, ducks: the plural of sheep is sheep, not "sheeps"
    s = predict.Predictor().suggest(db, sheep, ["Plural"])
    assert s.text == "sheep" and s.template.tag == "NNS"
