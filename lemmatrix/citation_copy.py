# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders. Additional terms: NOTICE.md
"""Tools → Copy citation forms to empty lemmas… (IDEAS.md idea 67, Josh, 24 October; built 26
October): every lemma whose Lemma field is empty can take its citation token's form (Phonemic,
else Phonetic, or the order chosen), as written: diacritics, length and tone marks untouched.
A lemma with a filled Lemma is never touched; one whose citation token has no form is skipped and
counted. No Qt here."""

from __future__ import annotations

from dataclasses import dataclass

from .model import Database, Entry, token_form

ORDERS = {                     # the dialogue's choice → the token fields tried, in order
    "phonemic-phonetic": ("phonemic", "phonetic"),
    "phonetic-phonemic": ("phonetic", "phonemic"),
    "phonemic": ("phonemic",),
    "phonetic": ("phonetic",),
}
LABELS = {
    "phonemic-phonetic": "Phonemic, else Phonetic",
    "phonetic-phonemic": "Phonetic, else Phonemic",
    "phonemic": "Phonemic only",
    "phonetic": "Phonetic only",
}


@dataclass
class Plan:
    copies: list[tuple[Entry, str]]      # (lemma, the form it would get)
    no_form: list[Entry]                 # empty Lemma, but the citation token has no such form
    filled: int                          # lemmas whose Lemma is already filled (left alone)


def plan(db: Database, order: str = "phonemic-phonetic") -> Plan:
    from .wordlists import citation_token
    f = db.settings.entry_field("lemma")
    copies, no_form, filled = [], [], 0
    if f is None:
        return Plan(copies, no_form, filled)
    for e in db.entries:
        if e.get(f.name).strip():
            filled += 1
            continue
        form = token_form(db, citation_token(db, e), ORDERS.get(order, ORDERS["phonemic-phonetic"])).strip()
        (copies.append((e, form)) if form else no_form.append(e))
    return Plan(copies, no_form, filled)


def changed_copies(db: Database, chosen: list[tuple[Entry, str]]) -> list[tuple[Entry, Entry]]:
    """(lemma, a copy with its Lemma filled) for Document.apply_changes: one undo step."""
    f = db.settings.entry_field("lemma")
    out = []
    for e, form in chosen:
        after = e.copy()
        after.set(f.name, form)
        out.append((e, after))
    return out
