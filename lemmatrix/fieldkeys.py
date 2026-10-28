# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders. Additional terms: NOTICE.md
"""What a field answers to in a template (IDEAS.md ideas 71–73, Josh, 26 October 2026).

A template (soundfile names, the Wordlist export) names a field in braces: `{Tone Class}`. A field
answers to its element name, its label and its abbreviation, in any case and with or without
spaces, so `{Tone Class}` **reserves** Tone Class, tone class, ToneClass, toneclass… and its
abbreviation (tnc). No two fields may answer to the same thing (Josh: a field named so that it
would call another field is warned about), nor to a template's own words ({language}, {tags}…).
The lemma and token fields of one name (Comment) are one name on purpose and are not a clash.

Labels may not hold the template's own characters, `{ } >`, nor those Windows forbids in file
names (idea 72), so any field can always be written in a template.
"""

from __future__ import annotations

from .model import FORBIDDEN_CHARS

TEMPLATE_CHARS = "{}>"
LABEL_FORBIDDEN = TEMPLATE_CHARS + FORBIDDEN_CHARS

# The token fields' abbreviations (Josh, 26 October); other fields have none until given one
DEFAULT_ABBR = {"phonetic": "pht", "phonemic": "phm", "morphemes": "mph", "constituents": "cns", "translation": "trs",
                "pitch": "pch", "comment": "com"}

# A template's own words, which no field may answer to unless it is the field they already mean
# (the lemma's Gloss, a text's Title)
TEMPLATE_WORDS = ("language", "variety", "speaker", "reference", "gloss", "label", "tags", "date",
                  "title")


def fold(text: str) -> str:
    """How a template's name is compared: any case, spaces left out."""
    return "".join((text or "").split()).casefold()


def keys(f) -> set[str]:
    """Everything a field answers to (folded)."""
    out = {fold(f.name), fold(f.title)}
    if getattr(f, "abbr", ""):
        out.add(fold(f.abbr))
    return {k for k in out if k}


def label_problem(text: str) -> str:
    """The characters a label or abbreviation can't have; "" if none."""
    bad = [c for c in LABEL_FORBIDDEN if c in (text or "")]
    return " ".join(dict.fromkeys(bad))


def all_fields(lists: dict) -> list[tuple[str, object]]:
    """(list name, field) for every field of every list: {"lemma": [...], "token": [...], …}."""
    return [(kind, f) for kind, fields in lists.items() for f in fields]


def clash(lists: dict, kind: str, f, before: set[str] | None = None) -> str:
    """Why a field's name, label or abbreviation can't be used, or "". Only what is new for the
    field is checked (`before`: what it answered to when the dialogue opened), so a database that
    already has a doubtful name still opens and saves."""
    new = keys(f) - set(before or ())
    for key in sorted(new):
        for other_kind, o in all_fields(lists):
            if o is f:
                continue
            if other_kind != kind and o.name == f.name:
                continue                          # the lemma's and the token's Comment: one name
            if key in keys(o):
                what = "abbreviation" if fold(getattr(f, "abbr", "")) == key else "name"
                return (f"The {what} “{_shown(f, key)}” would call the {other_kind} field "
                        f"{o.title} in a template ({{{o.title}}} answers to it, in any case, with or "
                        "without spaces). Choose another.")
        if key in TEMPLATE_WORDS and key != fold(getattr(f, "role", "")):
            return (f"“{_shown(f, key)}” is a word templates already use ({{{key}}}). Choose another.")
    return ""


def _shown(f, key: str) -> str:
    for text in (getattr(f, "abbr", ""), f.title, f.name):
        if fold(text) == key:
            return text
    return key


def give_defaults(fields) -> bool:
    """The token fields' default abbreviations, where a field has none (a new database, an older
    file). True if any was given."""
    changed = False
    for f in fields:
        a = DEFAULT_ABBR.get(f.role)
        if a and not getattr(f, "abbr", ""):
            f.abbr = a
            changed = True
    return changed


def find(fields, name: str):
    """The field a template name means: its element name exactly, else anything it answers to."""
    name = (name or "").strip()
    for f in fields:
        if f.name == name:
            return f
    k = fold(name)
    for f in fields:
        if k in keys(f):
            return f
    return None
