# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders. Additional terms: NOTICE.md
"""Batch tokens from the lemma list (IDEAS.md idea 64, 24 October 2026)."""

import pytest

from lemmatrix import batch, defaults, predict
from lemmatrix.model import Token

pytestmark = pytest.mark.real_defaults


def small_db():
    db = defaults.new_database()
    for ref, gloss, wc in (("D001", "goat", "NOUN"), ("D002", "dog", "NOUN"), ("V001", "to eat", "VERB")):
        db.entries.append(db.new_entry(ref, gloss=gloss, word_class=wc))
    return db


def test_combinations_multiply_by_group():
    db = small_db()
    combos = batch.combinations(db, ["Frame 2", "Plural", "Singular", "Frame 1"])
    assert combos == [["Singular", "Frame 1"], ["Singular", "Frame 2"],
                      ["Plural", "Frame 1"], ["Plural", "Frame 2"]]
    assert batch.group_names(db, ["Frame 2", "Plural", "Singular", "Frame 1"]) == \
        [["Singular", "Plural"], ["Frame 1", "Frame 2"]]
    assert batch.combinations(db, []) == []


def test_plan_makes_one_token_per_lemma_and_combination_blank_speaker_and_date():
    db = small_db()
    nouns = db.entries[:2]
    combos = batch.combinations(db, ["Singular", "Plural", "Frame 1", "Frame 2"])
    p = batch.plan(db, nouns, combos, translate=False)
    assert len(p.made) == 8 and not p.skipped
    for e, t in p.made:
        assert t.speaker == "" and t.collected == "" and not t.file
        assert "Nominative" in t.tags                      # the lemma's own defaults
    names = {db.expected_filename(e, t) for e, t in p.made}
    assert len(names) == 8
    assert any(n.endswith("D001_goat_F1.wav") for n in names)   # Singular has no code
    for e, c in batch.pairs(p):
        assert len(c.tokens) == 5 and c.tokens[0].is_citation   # the citation token stays first


def test_existing_combinations_are_skipped_without_examples():
    db = small_db()
    goat = db.entries[0]
    goat.add_token(db.new_token(goat, ["Plural", "Frame 1"], defaults=True))
    goat.add_token(Token(tags=["Frame 2"]))                 # same name as Singular + Frame 2
    combos = batch.combinations(db, ["Singular", "Plural", "Frame 1", "Frame 2"])
    p = batch.plan(db, [goat], combos, translate=False)
    assert sorted(tuple(c) for _, c in p.skipped) == [("Plural", "Frame 1"), ("Singular", "Frame 2")]
    assert len(p.made) == 2
    assert not any("Example" in " ".join(t.tags) for _, t in p.made)


def test_two_combinations_that_would_share_a_name_make_one_token():
    db = small_db()
    goat = db.entries[0]
    p = batch.plan(db, [goat], [["Singular", "Frame 1"], ["Frame 1"]], translate=False)
    assert len(p.made) == 1 and len(p.skipped) == 1


def test_unusual_tags_are_counted_by_lemma():
    db = small_db()
    p = batch.plan(db, db.entries, batch.combinations(db, ["Plural"]), translate=False)
    eat = db.entries[2]
    assert p.unusual == {eat.id}


def test_predicted_translations_fill_where_there_is_one():
    db = small_db()
    goat, dog, eat = db.entries
    fname = predict.translation_field(db)
    pl = db.new_token(goat, ["Plural"], defaults=True)
    pl.set(fname, "goats", "en")
    goat.add_token(pl)
    blank = db.new_entry("D003")                         # no gloss: nothing to predict from
    db.entries.append(blank)
    p = batch.plan(db, [dog, blank], batch.combinations(db, ["Plural"]), translate=True)
    by_ref = {e.ref: t for e, t in p.made}
    assert by_ref["D002"].get(fname, "en") == "dogs"
    assert by_ref["D003"].get(fname, "en") == ""
    assert p.predicted == 1 and p.untranslated == 1
    p2 = batch.plan(db, [dog], batch.combinations(db, ["Plural"]), translate=False)
    assert p2.made[0][1].get(fname, "en") == ""


def test_utterances_are_left_out():
    db = small_db()
    from lemmatrix.model import Utterance
    u = Utterance(ref="U001")
    p = batch.plan(db, [u], [["Plural"]], translate=False)
    assert not p.made


def test_label():
    db = small_db()
    p = batch.plan(db, db.entries[:2], batch.combinations(db, ["Plural", "Frame 1", "Frame 2"]), translate=False)
    assert batch.label(p) == "Add 4 tokens to 2 lemmas"


def test_citation_audit():
    db = small_db()
    goat, dog, _ = db.entries
    goat.tokens = [db.new_token(goat, ["Plural"], defaults=True)]
    dog.tokens = []
    assert batch.missing_citation(db) == [goat, dog]
    pairs = batch.citation_pairs(db)
    for e, c in pairs:
        assert c.tokens[0].is_citation and c.tokens[0].speaker == "" and c.tokens[0].collected == ""
    assert len(pairs[0][1].tokens) == 2


def test_matrices_rows_first_group_columns_the_rest():
    from lemmatrix import matrix as mx
    db = small_db()
    picked = ["Singular", "Plural", "Frame 1", "Frame 2"]
    lt, tt = batch.matrices(db, picked)
    assert lt.kind == mx.LEMMA_TAG and [set(s.tags) for s in lt.x] == \
        [{"Singular", "Frame 1"}, {"Singular", "Frame 2"}, {"Plural", "Frame 1"}, {"Plural", "Frame 2"}]
    assert all(s.match == mx.EXACT for s in lt.x)
    assert [set(s.tags) for s in tt.y] == [{"Singular"}, {"Plural"}]
    assert [set(s.tags) for s in tt.x] == [{"Frame 1"}, {"Frame 2"}]
    assert batch.matrices(db, ["Plural", "Singular"])[1] is None
    assert batch.same_saved(db, lt) is None
    saved = lt.copy()
    saved.name = "Number>Frames"
    db.settings.matrices.append(saved)
    assert batch.same_saved(db, lt) is saved


def test_new_tokens_fit_their_matrix_cells():
    from lemmatrix import matrix as mx
    db = small_db()
    picked = ["Singular", "Plural", "Frame 1", "Frame 2"]
    p = batch.plan(db, db.entries[:2], batch.combinations(db, picked), translate=False)
    for e, c in batch.pairs(p):
        e.tokens[:] = c.tokens
    lt, tt = batch.matrices(db, picked)
    layout = mx.lemma_tag_layout(db, db.entries[:2], lt)
    assert all(len(layout.tokens(r, c)) == 1 for r in range(2) for c in range(4))
    layout = mx.tag_tag_layout(db, db.entries[0], tt)
    assert all(len(layout.tokens(r, c)) == 1 for r in range(2) for c in range(2))
