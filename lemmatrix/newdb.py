# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders. Additional terms: NOTICE.md
"""Making a new database from the choices of File → New database (IDEAS.md idea 9; Josh, 23
October): the wordlist, the language and variety, the pitch kind, the database's name, the gloss
languages, you as researcher, a setup copied from another database and the soundfile names.
The window is ui/new_database.py; this part has no Qt, so it can be tested on its own."""
from __future__ import annotations

import copy
from dataclasses import dataclass, field

from . import defaults, pitchkind
from .model import SEQUENCE, Database, Person, nfc

# Soundfile name presets (the pattern box in Settings → Sound takes any pattern)
PATTERNS = [
    ("Lemmatrix's default", "{language}-{variety}_{reference}_{gloss}_{tags}"),
    ("With the speaker", "{language}-{variety}-{speaker}_{reference}_{gloss}_{tags}"),
    ("Without the variety", "{language}_{reference}_{gloss}_{tags}"),
    ("Reference first", "{reference}_{gloss}_{tags}"),
]


@dataclass
class Choices:
    base: str = ""                         # the wordlist (EACW, CAWL, SWADESH) or "" for blank
    items: str = "base"                    # the EACW: base (default items) or expanded (hidden too)
    region: str = "africa"                 # the EACW: global, africa, or one region (N W E S C)
    language_name: str = ""
    language_code: str = ""
    variety_name: str = ""
    variety_code: str = ""
    kind: str = pitchkind.DEFAULT          # tonal (Josh: the default), intonational, unspecified
    name: str = ""                         # the database's own name
    gloss_languages: list[str] = field(default_factory=lambda: ["en"])
    you: dict = field(default_factory=dict)   # name, code, email: the first researcher and the owner
    copy_from: Database | None = None      # its fields, lists and tags (no data, people, settings)
    pattern: str = PATTERNS[0][1]


def copy_setup(db: Database, src: Database):
    """The other database's fields, lists and tags: lemma, token and text fields (closed fields
    with their lists), the tag structure, the reference categories and the tier mapping. Nothing
    else: no data, people, places, settings or matrices."""
    s, o = db.settings, src.settings
    s.entry_fields = copy.deepcopy(o.entry_fields)
    s.token_fields = copy.deepcopy(o.token_fields)
    if o.text_fields:
        s.text_fields = copy.deepcopy(o.text_fields)
    s.tags = copy.deepcopy(o.tags)
    if o.ref_scheme != SEQUENCE and o.ref_categories:
        s.ref_categories = copy.deepcopy(o.ref_categories)
    s.tier_mapping = copy.deepcopy(o.tier_mapping)


def make(ch: Choices) -> Database:
    """A new database, not yet saved, from the window's choices."""
    db = defaults.new_database()
    if ch.copy_from is not None:
        copy_setup(db, ch.copy_from)
        defaults.ensure_core_fields(db.settings)
    md, s = db.metadata, db.settings
    md.language_name, md.language_code = nfc(ch.language_name.strip()), nfc(ch.language_code.strip())
    md.variety_name, md.variety_code = nfc(ch.variety_name.strip()), nfc(ch.variety_code.strip())
    md.name = nfc(ch.name.strip())
    langs = [x.strip() for x in ch.gloss_languages if x.strip()] or ["en"]
    s.gloss_languages = list(dict.fromkeys(langs))
    s.primary_gloss = s.gloss_languages[0]
    if ch.pattern.strip():
        s.filename_pattern = ch.pattern.strip()
    you = {k: (ch.you or {}).get(k, "").strip() for k in ("name", "code", "email")}
    if you["name"] or you["code"]:            # you in RS1's place, and the owner
        me = Person.researcher(you["code"] or "RS1", you["name"])
        me.email = you["email"]
        if md.researchers:
            md.researchers[0] = me
        else:
            md.researchers.append(me)
        md.author = you["name"] or you["code"]
    if ch.base:
        defaults.fill_from_wordlist(db, ch.base, ch.items, ch.region)
    pitchkind.convert(db, ch.kind)            # its fields follow the kind (a new database has no data)
    return db


def example_name(pattern: str, ch: Choices | None = None) -> str:
    """The soundfile name a pattern gives a plural token of an example lemma (the live example)."""
    db = defaults.new_database()
    md = db.metadata
    md.language_code = (ch.language_code if ch else "") or "LXX"
    md.variety_code = (ch.variety_code if ch else "") or "VXX"
    db.settings.filename_pattern = pattern
    e = db.new_entry("D001", gloss="goat", speaker="SP1")
    db.entries.append(e)
    t = copy.deepcopy(e.tokens[0])
    t.tags = ["Plural"] if db.settings.tags.tag("Plural") is not None else []
    t.speaker = "SP1"
    return db.expected_filename(e, t)
