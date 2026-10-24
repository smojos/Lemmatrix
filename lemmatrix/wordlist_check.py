# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders. Additional terms: NOTICE.md
"""Tools → Audits → Check wordlist integrity… (IDEAS.md idea 66, Josh, 24 October 2026): one
report that brings a database up to date with the list it is built on, in place of Link to
wordlists, Convert references from a table and Insert EACW items one after the other.

Every finding has a checkbox; Fix the selected is one undo step (Josh: "One report, select and
fix"). What it looks for:
- **numbers**: the CAWL and Swadesh numbers (or the EACW's, in a CAWL or Swadesh database) out of
  date with the shipped mapping;
- **hidden** (EACW): lemmas whose item isn't in the database's Items and Region. An empty one can be
  removed; one with data is never removed, only named (preserve and protect the data);
- **missing** (EACW): default items of the database's Items and Region it doesn't have;
- **order** (EACW): lemmas out of the list's order;
- **glosses** (EACW): glosses that don't match their item's.

What starts selected is what an update of the list changed: the numbers always; the items hidden
or made default by the editions since the database's version (`wordlists.EDITIONS`). The rest is
listed for the researcher to choose: a hidden item inserted on purpose, a default item left out on
purpose, a gloss of one's own. On opening, a database on an older edition is told and offered the
update with one click (Josh: "given the option to bring their version of the list up to date with
the click of a button"): the selected fixes, and the version recorded.

No Qt here.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from . import wordlists as wl

NUMBERS, HIDDEN, MISSING, ORDER, GLOSS = "numbers", "hidden", "missing", "order", "gloss"
KINDS = (NUMBERS, HIDDEN, MISSING, ORDER, GLOSS)
KIND_NAMES = {NUMBERS: "Numbers", HIDDEN: "Hidden items", MISSING: "Missing items", ORDER: "Order",
              GLOSS: "Glosses"}


@dataclass
class Finding:
    kind: str
    ref: str
    gloss: str
    text: str                         # what was found
    fix: str = ""                     # what fixing does ("": listed only)
    selected: bool = False            # starts selected
    entry: object = field(default=None, repr=False)
    item: object = field(default=None, repr=False)
    numbers: dict | None = field(default=None, repr=False)

    @property
    def fixable(self) -> bool:
        return bool(self.fix)


def version(db) -> str:
    """The EACW edition the database is up to date with ("" read as the first)."""
    return db.metadata.wordlist_version or wl.EDITIONS[0].version


def out_of_date(db) -> bool:
    """An EACW database on an older edition than the shipped one."""
    return wl.is_eacw(db) and bool(wl.editions_since(version(db)))


def _since(db) -> tuple[set, set]:
    """(made default, hidden) by the editions after the database's version."""
    made, hidden = set(), set()
    for ed in wl.editions_since(version(db)):
        made |= ed.made_default
        hidden |= ed.hidden
        made -= ed.hidden
        hidden -= ed.made_default
    return made, hidden


def _items_region(db) -> tuple[str, str]:
    md = db.metadata
    return md.wordlist_items or wl.BASE, md.wordlist_region or wl.AFRICA


def has_data(db, e) -> bool:
    """Whether a lemma holds anything of the researcher's: a token with something in it, a field
    the list doesn't fill, a gloss in another language, From, or another lemma built from it."""
    if any(t.has_content() for t in e.tokens):
        return True
    s = db.settings
    own = {f.name for role in ("gloss", "word-class", wl.CLARIFICATION, wl.TAXON)
           if (f := s.entry_field(role)) is not None}
    fresh = db.new_entry(e.ref).values               # what every new lemma has (Stem type: simple)
    if any(v.strip() and fresh.get(k) != v for k, v in e.values.items() if k not in own):
        return True
    for name, langs in e.multi.items():
        if any(v.strip() and (name not in own or lang not in (s.primary_gloss, "en")) for lang, v in langs.items()):
            return True
    if e.from_lemmas or e.from_languages:
        return True
    return any(e.id in other.from_lemmas for other in db.entries if other is not e)


def _numbers_text(base: str, e, new: dict) -> str:
    out = []
    for lid in wl.LIST_IDS:
        if lid == base:
            continue
        old, now = e.lists.get(lid) or [], new.get(lid) or []
        if old != now:
            out.append(f"{wl.SHORT[lid]} {', '.join(old) or '—'} → {', '.join(now) or '—'}")
    return "; ".join(out)


def check(db) -> list[Finding]:
    """Everything that isn't as the shipped list has it, in KINDS order."""
    base = wl.base_of(db)
    if not base:
        return []
    out = []
    for e, new in wl.link_plan(db, base):
        out.append(Finding(NUMBERS, e.ref, db.gloss(e), _numbers_text(base, e, new), "Renew the numbers",
                           True, e, numbers=new))
    if base != wl.EACW:
        return out
    items, region = _items_region(db)
    made, hidden = _since(db)
    eacw = wl.get(wl.EACW)
    for e in db.entries:
        n = wl.canon(wl.EACW, e.ref)
        item = eacw.by_number.get(n) if n else None
        if item is None or wl.in_version(item, items, region):
            continue
        why = "now hidden in the list" if n in hidden else f"not in {wl.version_name(items, region)}"
        if not has_data(db, e):
            out.append(Finding(HIDDEN, e.ref, db.gloss(e), f"Empty; {why}", "Remove the empty lemma",
                               n in hidden, e, item))
        elif n in hidden:
            out.append(Finding(HIDDEN, e.ref, db.gloss(e), f"Has data, so it is kept; {why}", "", False, e, item))
    have = {wl.canon(wl.EACW, e.ref) for e in db.entries}
    for item in wl.version_items(items, region):
        if item.number not in have:
            new = item.number in made
            out.append(Finding(MISSING, item.number, item.gloss,
                               "Now a default item" if new else "A default item the database doesn't have",
                               "Insert it", new, item=item))
    _, moving = wl.out_of_place(db.entries)
    for e in moving:
        out.append(Finding(ORDER, e.ref, db.gloss(e), "Out of the list's order", "Move it into place", False, e))
    _, wrong = wl.gloss_mismatches(db, wl.EACW)
    for e, item in wrong:
        out.append(Finding(GLOSS, e.ref, db.gloss(e, "en") or db.gloss(e),
                           f"The list's gloss is “{item.gloss}”", "Give it the list's gloss", False, e, item))
    return out


def plan(db, findings, new_entry) -> tuple[list, list, list]:
    """What fixing the selected findings does: (the lemmas' new order, (lemma, its changed copy)
    pairs, the new lemmas), for Document.restructure as one undo step. new_entry(item) makes the
    lemma for a missing item (with the session's speaker and date). The database isn't changed."""
    chosen = [f for f in findings if f.selected and f.fixable]
    removed = {id(f.entry) for f in chosen if f.kind == HIDDEN}
    order = [e for e in db.entries if id(e) not in removed]
    copies: dict[int, tuple] = {}

    def changed(e):
        return copies.setdefault(id(e), (e, e.copy()))[1]

    s = db.settings
    gloss_field = s.entry_field("gloss")
    lang = "en" if "en" in s.gloss_languages else s.primary_gloss
    for f in chosen:
        if id(f.entry) in removed and f.kind != HIDDEN:
            continue
        if f.kind == NUMBERS:
            after = changed(f.entry)
            after.lists = {k: v for k, v in after.lists.items() if k == wl.base_of(db)}
            after.lists.update(f.numbers)
        elif f.kind == GLOSS and gloss_field is not None:
            changed(f.entry).set(gloss_field.name, f.item.gloss, lang if gloss_field.multilingual else None,
                                 gloss_field.multilingual)
        elif f.kind == ORDER:
            order.remove(f.entry)
            at = wl.insert_position(order, f.entry.ref)
            order.insert(len(order) if at is None else at, f.entry)
    made = []
    for f in chosen:
        if f.kind == MISSING:
            e = new_entry(f.item)
            at = wl.insert_position(order, f.item.number)
            order.insert(len(order) if at is None else at, e)
            made.append(e)
    return order, list(copies.values()), made


def summary(findings) -> str:
    """"Numbers 3 · Hidden items 186 · Missing items 5" for the selected ones."""
    counts = {}
    for f in findings:
        if f.selected and f.fixable:
            counts[f.kind] = counts.get(f.kind, 0) + 1
    return " · ".join(f"{KIND_NAMES[k]} {counts[k]:,}" for k in KINDS if counts.get(k))
