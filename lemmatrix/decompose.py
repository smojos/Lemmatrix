# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders. Additional terms: NOTICE.md
"""Decomposed transcriptions (IDEAS.md ideas 18 and 21; Josh, 27 October; DESIGN.md 3.1).

A database can promise that its **Phonetic and Phonemic** fields (every field whose role is
phonetic or phonemic: lemmas, tokens, utterances, texts) hold **no precomposed characters**:
é is stored as e + U+0301, so a tone mark is always a mark of its own, on every vowel (under
NFC *é* is one character but *ɛ́* two), and an analysis engine, a regex or another program reads
tone suprasegmentally. The promise is `Settings.decomposed`, written in the database as
`<characters transcriptions="NFD" …>` so a computer or a researcher can read it (Josh).

While it is on, **everything written** into those fields is decomposed: typing (`ui/bestfriend.py`),
every edit through the Document (dialogues, grids, Bulk edit, ɛλicit, imports), opening and saving.
Everything else stays NFC (`model.nfc`), and so do soundfile names (`filenames.praat_name`).
NFC and NFD are canonically equivalent: converting either way loses nothing.

No Qt here.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass

ROLES = ("phonetic", "phonemic")


def nfd(text: str) -> str:
    return unicodedata.normalize("NFD", text) if text else ""


def precomposed(text: str) -> bool:
    """Whether the text has a character that decomposes (é, ã, ǹ…)."""
    return bool(text) and unicodedata.normalize("NFD", text) != text


def precomposed_chars(text: str) -> list[str]:
    """The precomposed characters in the text, each once, in order."""
    out = []
    for ch in text or "":
        if unicodedata.normalize("NFD", ch) != ch and ch not in out:
            out.append(ch)
    return out


def field_names(settings) -> tuple[set[str], set[str], set[str]]:
    """The names of the phonetic and phonemic fields: (lemma fields, token fields, text fields)."""
    pick = lambda fields: {f.name for f in fields if f.role in ROLES}  # noqa: E731
    return pick(settings.entry_fields), pick(settings.token_fields), pick(settings.text_fields)


def _fix_values(values: dict, multi: dict | None, names: set[str], form: str) -> int:
    n = 0
    for name in names:
        v = values.get(name)
        if v and unicodedata.normalize(form, v) != v:
            values[name] = unicodedata.normalize(form, v)
            n += 1
        if multi and name in multi:
            for lang, v in list(multi[name].items()):
                if v and unicodedata.normalize(form, v) != v:
                    multi[name][lang] = unicodedata.normalize(form, v)
                    n += 1
    return n


def fix_entry(entry, names, form: str = "NFD") -> int:
    """Put a lemma's or utterance's phonetic and phonemic fields in `form` (NFD: decomposed, NFC:
    composed) in place (`names` from field_names). Returns how many values changed. Written
    straight into the values: the setters normalise to NFC."""
    entry_names, token_names, _ = names
    n = _fix_values(entry.values, entry.multi, entry_names, form)
    for t in entry.tokens:
        n += _fix_values(t.values, t.multi, token_names, form)
    return n


def fix_text(text, names, form: str = "NFD") -> int:
    return _fix_values(text.values, None, names[2], form)


def form_of(settings) -> str:
    return "NFD" if settings.decomposed else "NFC"


def fix_database(db, form: str | None = None) -> int:
    """Every phonetic and phonemic value in the database in `form` (the database's own by
    default), in place. Returns how many values changed."""
    form = form or form_of(db.settings)
    names = field_names(db.settings)
    n = sum(fix_entry(e, names, form) for e in db.entries)
    n += sum(fix_entry(u, names, form) for u in db.utterances)
    n += sum(fix_text(t, names, form) for t in db.texts)
    return n


def pairs(db, form: str, items=None) -> list:
    """(lemma or utterance, its copy in `form`) for those whose transcriptions would change: for
    Document.apply_changes, one undo step. items: only these (default: every lemma and utterance)."""
    names = field_names(db.settings)
    out = []
    for e in (items if items is not None else [*db.entries, *db.utterances]):
        c = e.copy()
        if fix_entry(c, names, form):
            out.append((e, c))
    return out


# ---- the audit (Tools → Audits → Find precomposed characters…) ----------------------------

@dataclass
class Finding:
    kind: str          # "lemma", "token", "utterance", "text"
    item: object       # the Entry, Utterance or Text
    where: str         # e.g. "D009 ‘goat’ · PL", shown in the list
    field: str
    lang: str          # a multilingual field's language, else ""
    before: str

    @property
    def chars(self) -> str:
        return " ".join(precomposed_chars(self.before))


def find(db, describe_token=None) -> list[Finding]:
    """Every phonetic or phonemic value with precomposed characters, in the database's order.
    describe_token(entry, token) -> str names a token (else the reference and its tags)."""
    entry_names, token_names, text_names = field_names(db.settings)
    out: list[Finding] = []

    def values(owner, names):
        for name in sorted(names):
            v = owner.values.get(name)
            if v and precomposed(v):
                yield name, "", v
            for lang, mv in sorted(getattr(owner, "multi", {}).get(name, {}).items()):
                if mv and precomposed(mv):
                    yield name, lang, mv

    for kind, items in (("lemma", db.entries), ("utterance", db.utterances)):
        for e in items:
            if kind == "lemma":
                for name, lang, v in values(e, entry_names):
                    out.append(Finding("lemma", e, e.ref, name, lang, v))
            for t in e.tokens:
                for name, lang, v in values(t, token_names):
                    if kind == "utterance":
                        where = e.ref
                    elif describe_token:
                        where = describe_token(e, t)
                    else:
                        where = e.ref + (" · " + ".".join(t.tags) if t.tags else "")
                    out.append(Finding("token" if kind == "lemma" else "utterance", e, where, name, lang, v))
    for t in db.texts:
        for name, lang, v in values(t, text_names):
            out.append(Finding("text", t, t.ref, name, lang, v))
    return out
