# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders. Additional terms: NOTICE.md
"""How a link reads (Josh, 25 October): {reference} {phonemic, else phonetic} {translation, else
the lemma's gloss} · {tags}; a question in Cogitate is "Q: …". One token form everywhere a form
stands for a token (model.token_form; the audit, section 8, step 2)."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from lemmatrix import defaults, notebook as nbmod  # noqa: E402
from lemmatrix.model import Entry, Token, Utterance, meaning, token_form  # noqa: E402


def _db():
    db = defaults.new_database()
    return db


def _entry(db, phonetic="dʌːm", phonemic="dʌ́ʌm", translation="", gloss="goat", tags=()):
    e = Entry(ref="D009")
    e.set("Gloss", gloss, "en")
    t = Token(tags=list(tags))
    t.set("Phonetic", phonetic)
    t.set("Phonemic", phonemic)
    if translation:
        t.set("Translation", translation, "en")
    e.tokens.append(t)
    db.entries.append(e)
    return e, t


def test_phonemic_first_then_phonetic():
    db = _db()
    e, t = _entry(db)
    assert token_form(db, t) == "dʌ́ʌm"                       # the analysed form first (Josh)
    t.set("Phonemic", "")
    assert token_form(db, t) == "dʌːm"                        # blank: the phonetic
    assert token_form(db, t, order=("phonetic", "phonemic")) == "dʌːm"


def test_a_token_reads_reference_form_meaning_tags():
    db = _db()
    pl = next(tag.name for tag, _ in db.settings.tags.tags() if not tag.default)
    e, t = _entry(db, translation="your (sg) goat", tags=[pl])
    text = nbmod.describe(db, e, t)
    assert text.startswith("D009 dʌ́ʌm ‘your (sg) goat’ · ")
    t.set("Translation", "", "en")                            # no translation: the lemma's gloss
    assert nbmod.describe(db, e, t).startswith("D009 dʌ́ʌm ‘goat’ · ")


def test_a_citation_token_and_a_lemma():
    db = _db()
    e, t = _entry(db)
    assert nbmod.describe(db, e, t) == "D009 dʌ́ʌm ‘goat’ · citation"
    assert nbmod.describe(db, e) == "D009 dʌ́ʌm ‘goat’"         # the citation token's form


def test_an_utterance_reads_reference_form_translation():
    db = _db()
    t = Token()
    t.set("Phonemic", "tʌ́dɔ̄tʌ̄ŋ")
    t.set("Translation", "We will eat lion meat today.", "en")
    u = Utterance(ref="U003", file_gloss="we will eat", tokens=[t])
    db.utterances.append(u)
    assert nbmod.describe(db, u) == "U003 tʌ́dɔ̄tʌ̄ŋ ‘We will eat lion meat today.’"


def test_meaning_has_one_copy():
    from lemmatrix.ui import widgets
    assert widgets.meaning is meaning
    assert meaning("‘goat’") == "‘goat’" and meaning("") == ""


def test_cogitate_names_a_question_q(win):
    from lemmatrix import hypotheses as hy
    nb = win.doc.notebook
    db = win.doc.db
    q = nbmod.push_question(nb, db, win.work_date(), "Is the H tone lexical?", None, None)
    link = hy.question_link(nb.session(win.work_date()), q)
    assert hy.label(db, nb, link) == "Q: Is the H tone lexical?"


def test_the_questions_list_shows_the_link_as_it_reads_now(win):
    db = win.doc.db
    nb = win.doc.notebook
    e = db.entries[0]
    t = e.tokens[0]
    q = nbmod.push_question(nb, db, win.work_date(), "Why?", e, t)
    q.about = "written in the old way"
    assert nbmod.about_now(db, q) == nbmod.describe(db, e, t)
    e.tokens.remove(t)                                        # gone: what was written then
    assert nbmod.about_now(db, q) == "written in the old way"
