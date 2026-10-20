# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders
"""Tests for the notebook: sessions, the record of comments, people and places, the file."""

import pytest

from lemmatrix import notebook as nb, storage
from lemmatrix.defaults import new_database
from lemmatrix.model import Location, Person


@pytest.fixture
def db(tmp_path):
    d = new_database()
    d.metadata.language_code, d.metadata.variety_code = "LXX", "VXX"
    d.metadata.researchers = [Person("JS", "Joshua A. G. Smolders")]
    d.metadata.participants = [Person("SP1", "Sample Speaker", "CONSENT", "Consent/SP1")]
    d.metadata.locations = [Location("Sudan", "SU", children=[Location("Sample variety village", "VXX-V", "A village")]),
                            Location("United Kingdom", children=[Location("Edinburgh")])]
    e = d.new_entry("D009", "ɗæær", "goat", "NOUN")
    e.tokens[0].set("Phonetic", "ɗæær")
    pl = d.new_token(e, ["Plural"])
    e.tokens.append(pl)
    d.entries.append(e)
    d.path = str(tmp_path / "LXX.xml")
    return d


def edit(db, e, change, date):
    before = e.copy()
    change(e)
    db.stamp_comments(before, e, date)


def test_people_places_ids_and_comment_dates_round_trip(db, tmp_path):
    e = db.entries[0]
    edit(db, e, lambda x: x.set("Comment", "check the tone"), "2026-10-16")
    edit(db, e, lambda x: x.tokens[1].set("Comment", "plural is odd"), "2026-10-17")
    db.metadata.author = "Joshua A. G. Smolders"
    storage.save(db, db.path, backup=False)
    text = (tmp_path / "LXX.xml").read_text(encoding="utf-8")
    assert '<Comment changed="2026-10-16">check the tone</Comment>' in text
    back = storage.load(db.path)
    md = back.metadata
    assert md.author == "Joshua A. G. Smolders"
    assert md.participant("SP1").consent == "Consent/SP1"
    assert md.participant("SP1").description == "CONSENT"
    assert md.location_path("VXX-V") == "Sudan › Sample variety village"
    assert md.location("Edinburgh").name == "Edinburgh"       # no code: the name is the key
    assert md.location("VXX-V").description == "A village"
    be = back.entries[0]
    assert be.id == e.id and [t.id for t in be.tokens] == [t.id for t in e.tokens]
    assert be.changed == {"Comment": "2026-10-16"}
    assert be.tokens[1].changed == {"Comment": "2026-10-17"}


def test_duplicate_ids_are_made_unique(tmp_path):
    p = tmp_path / "dup.xml"
    p.write_text('<database format="6"><metadata/><settings/>'
                 '<entry ref="A001" id="x"><token id="t"/><token id="t"/></entry></database>', encoding="utf-8")
    d = storage.load(p)
    assert len({t.id for t in d.entries[0].tokens}) == 2


def test_only_changed_comments_get_dated(db):
    e = db.entries[0]
    edit(db, e, lambda x: x.tokens[0].set("Phonetic", "ɗææ"), "2026-10-17")
    assert e.changed == {} and e.tokens[0].changed == {}
    # a token edited through a copy (as the token dialogue does) is still itself
    def via_copy(x):
        t = x.tokens[1].copy()
        t.set("Comment", "new")
        x.tokens[1] = t
    edit(db, e, via_copy, "2026-10-17")
    assert e.tokens[1].changed == {"Comment": "2026-10-17"}
    assert e.tokens[0].changed == {}


def test_record_of_comments_follows_the_rules(db):
    book = nb.Notebook()
    e = db.entries[0]
    edit(db, e, lambda x: x.set("Comment", "first"), "2026-10-15")
    s15 = nb.write_session(book, db, "2026-10-15", ["JS"], ["SP1"], ["VXX-V"])
    assert [c.text for c in s15.comments] == ["first"]
    assert s15.comments[0].about == "D009 goat"
    # changed again the same day: written over
    edit(db, e, lambda x: x.set("Comment", "first, better"), "2026-10-15")
    nb.refresh_comments(db, s15)
    assert [c.text for c in s15.comments] == ["first, better"]
    # changed on a later day: the old record keeps its text, the new day gets the new one
    edit(db, e, lambda x: x.set("Comment", "second"), "2026-10-16")
    nb.refresh_comments(db, s15)
    assert [c.text for c in s15.comments] == ["first, better"]
    s16 = nb.write_session(book, db, "2026-10-16", ["JS"], [], [])
    assert [c.text for c in s16.comments] == ["second"]
    # a token comment, then the token deleted the same day: it leaves that day's record
    edit(db, e, lambda x: x.tokens[1].set("Comment", "plural?"), "2026-10-16")
    nb.refresh_comments(db, s16)
    assert [c.text for c in s16.comments] == ["second", "plural?"]
    assert s16.comments[1].about == "D009 goat · PL"
    plural_note = s16.comments[1]
    edit(db, e, lambda x: x.tokens.pop(1), "2026-10-16")
    nb.refresh_comments(db, s16)
    assert [c.text for c in s16.comments] == ["second"]
    # a lemma deleted on a later day: the old records keep it, but the link is broken
    db.entries.remove(e)
    assert nb.find(db, s15.comments[0]) is None
    assert nb.missing_text(s15.comments[0]) == "Lemma no longer exists"
    assert nb.missing_text(plural_note) == "Token no longer exists"


def test_write_never_touches_notes_or_questions(db):
    book = nb.Notebook()
    s = nb.write_session(book, db, "2026-10-16", ["JS"], ["SP1"], [])
    s.notes = "=ACTIVITIES=\nrecorded goats"
    s.questions.append(nb.Question("Is the plural regular?", "2026-10-16"))
    nb.write_session(book, db, "2026-10-16", ["JS"], [], ["Edinburgh"])
    assert s.notes.startswith("=ACTIVITIES=") and len(s.questions) == 1
    assert s.participants == [] and s.locations == ["Edinburgh"]


def test_no_future_sessions(db):
    with pytest.raises(nb.NotebookError):
        nb.Notebook().add_session("2999-01-01")


def test_notebook_file_round_trip(db, tmp_path):
    book = nb.Notebook()
    e = db.entries[0]
    edit(db, e, lambda x: x.set("Comment", "ATR <harmony> & more"), "2026-10-16")
    s = nb.write_session(book, db, "2026-10-16", ["JS"], ["SP1"], ["VXX-V", "Edinburgh"])
    s.notes = "Line one\n  indented line\nɗæær [ATR]"
    s.questions = [nb.Question("open one", "2026-10-16"),
                   nb.Question("closed one", "2026-10-15", "2026-10-16", "2026-10-17")]
    book.add_session("2026-09-29").notes = "older"
    path = nb.path_for(db.path)
    assert path.name == "LXX.notebook"
    nb.save(book, path, "LXX.xml")
    back = nb.load(path)
    assert [x.date for x in back.sessions] == ["2026-09-29", "2026-10-16"]
    b = back.session("2026-10-16")
    assert b.notes == s.notes
    assert b.researchers == ["JS"] and b.participants == ["SP1"] and b.locations == ["VXX-V", "Edinburgh"]
    assert b.comments == s.comments
    assert b.questions == s.questions
    assert [q.status for _, q in back.all_questions()] == ["Open", "Resolved"]
    assert nb.matches(b, db, "speaker") and nb.matches(b, db, "sample variety") and nb.matches(b, db, "harmony")
    assert not nb.matches(b, db, "zebra")


def test_rename_codes_in_sessions(db):
    book = nb.Notebook()
    s = book.add_session("2026-10-16")
    s.researchers, s.participants, s.locations = ["JS"], ["SP1", "SP2"], ["VXX-V"]
    book.rename({"JS": "JAGS"}, {"SP2": "SP1"}, {"VXX-V": "VXX"})
    assert s.researchers == ["JAGS"] and s.participants == ["SP1"] and s.locations == ["VXX"]
    assert book.people() == (["JAGS"], ["SP1"])


def test_long_date():
    assert nb.long_date("2026-10-17") == "2026-OCT-17"
