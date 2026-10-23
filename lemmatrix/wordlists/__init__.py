# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders. Additional terms: NOTICE.md
"""The comparative wordlists (IDEAS.md idea 40, designed with Josh 22 October 2026): the
Extended African Comparative Wordlist (EACW, Josh's own), the SIL Comparative African Wordlist
(CAWL; Snider & Roberts 2006) and the Swadesh list (207 items).

The lists live here, in Lemmatrix, never in a database (Josh: "that must be stored in Lemmatrix
not in the XML database"). A database built on one of them has that list's numbers as its
references (its *base*); the other lists' numbers are stored on each lemma, readable in the XML
and shown nowhere else (`<entry ref="C001b" cawl="0345" swadesh="42">`). They are data: they
describe the lemmas, so they go into the archives too.

The data files beside this module (tab-separated, UTF-8, one header line):
- `eacw.tsv`: ref, gloss, word class (the list's own order);
- `cawl.tsv`: number, domain, word class, the EACW items it maps to, and its English and French
  glosses when SIL's permission allows them to be shipped (until then the columns are empty);
- `swadesh.tsv`: number, gloss, word class, the EACW items and CAWL numbers it maps to.
The data files are not under the AGPL: see `THIRD-PARTY.md` and `CITATIONS` below.

No Qt here.
"""

from __future__ import annotations

import csv
import re
import unicodedata
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

HERE = Path(__file__).parent

EACW, CAWL, SWADESH = "EACW", "CAWL", "SWADESH"
LIST_IDS = (EACW, CAWL, SWADESH)
ATTRS = {EACW: "eacw", CAWL: "cawl", SWADESH: "swadesh"}    # the entry attribute for each list

# Citations and DOIs, shown in New database's hovers, the exports and the documentation. The EACW's
# DOI is added once it has one (Josh, 22 October: "Once I get a DOI that can be added").
CITATIONS = {
    EACW: "Smolders, Joshua. 2026. Extended African Comparative Wordlist.",
    CAWL: "Snider, Keith & James Roberts. 2006. SIL Comparative African Wordlist (SILCAWL). "
          "SIL Electronic Working Papers 2006-005. Dallas: SIL International. "
          "(First published in Journal of West African Languages 31(2): 73–122.)",
    SWADESH: "Swadesh, Morris. 1952. Lexico-statistic dating of prehistoric ethnic contacts. "
             "Proceedings of the American Philosophical Society 96(4): 452–463; "
             "Swadesh, Morris. 1955. Towards greater accuracy in lexicostatistic dating. "
             "International Journal of American Linguistics 21(2): 121–137. "
             "(The 207-item list combining his 100- and 200-word lists.)",
}
DOIS = {EACW: "", CAWL: "", SWADESH: ""}
NAMES = {EACW: "Extended African Comparative Wordlist",
         CAWL: "SIL Comparative African Wordlist",
         SWADESH: "Swadesh list"}
SHORT = {EACW: "EACW", CAWL: "CAWL", SWADESH: "Swadesh"}
DIGITS = {CAWL: 4, SWADESH: 3}       # references in a database built on the list (0345, 042)


@dataclass
class Item:
    number: str                       # the list's own form: C001b, 0345, 42
    gloss: str = ""                   # English ("" for the CAWL until its glosses can be shipped)
    word_class: str = ""
    domain: str = ""                  # the CAWL's section number (1.1.1)
    french: str = ""
    eacw: list[str] = field(default_factory=list)     # the EACW items it maps to (CAWL, Swadesh)
    cawl: list[str] = field(default_factory=list)     # the CAWL numbers it maps to (Swadesh)


@dataclass
class WordList:
    id: str
    items: list[Item]
    by_number: dict[str, Item] = field(default_factory=dict)

    @property
    def name(self) -> str:
        return NAMES[self.id]

    @property
    def citation(self) -> str:
        return CITATIONS[self.id]

    @property
    def doi(self) -> str:
        return DOIS[self.id]

    @property
    def has_glosses(self) -> bool:
        return any(i.gloss for i in self.items)


def _read(name: str) -> list[dict]:
    with open(HERE / name, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f, delimiter="\t"))


def _split(text) -> list[str]:
    return (text or "").split()


@lru_cache(maxsize=None)
def get(list_id: str) -> WordList:
    if list_id == EACW:
        items = [Item(r["ref"], r["gloss"], r["word_class"]) for r in _read("eacw.tsv")]
    elif list_id == CAWL:
        items = [Item(r["number"], r.get("gloss") or "", r["word_class"], r["domain"],
                      r.get("french") or "", _split(r["eacw"])) for r in _read("cawl.tsv")]
    elif list_id == SWADESH:
        items = [Item(r["number"], r["gloss"], r["word_class"], eacw=_split(r["eacw"]),
                      cawl=_split(r["cawl"])) for r in _read("swadesh.tsv")]
    else:
        raise KeyError(list_id)
    wl = WordList(list_id, items)
    wl.by_number = {i.number: i for i in items}
    return wl


def list_id(name: str) -> str | None:
    """EACW, CAWL or SWADESH for a name as typed (any case), or None."""
    n = (name or "").strip().upper()
    return n if n in LIST_IDS else None


def canon(lid: str, text: str) -> str | None:
    """A number as the list writes it: `c001b` → C001b, `345` → 0345, `042` → 42. None if the list
    has no such item."""
    t = (text or "").strip()
    if not t:
        return None
    wl = get(lid)
    if lid == EACW:
        if t in wl.by_number:
            return t
        low = _eacw_lower().get(t.casefold())
        return low
    if not t.isdigit():
        return None
    n = int(t)
    key = f"{n:04d}" if lid == CAWL else str(n)
    return key if key in wl.by_number else None


@lru_cache(maxsize=1)
def _eacw_lower() -> dict[str, str]:
    return {i.number.casefold(): i.number for i in get(EACW).items}


def display(lid: str, number: str) -> str:
    """How a number is written in a reference of a database built on the list (0345, 042)."""
    if lid in DIGITS and number.isdigit():
        return f"{int(number):0{DIGITS[lid]}d}"
    return number


# ---- the mapping -------------------------------------------------------
@lru_cache(maxsize=None)
def _maps() -> dict[tuple[str, str], dict[str, list[str]]]:
    """(from, to) → {number: [numbers]} for every pair of lists, with the EACW as the pivot and the
    Swadesh list's own CAWL column."""
    m: dict[tuple[str, str], dict[str, list[str]]] = {}

    def add(a, b, x, y):
        d = m.setdefault((a, b), {})
        if y not in d.setdefault(x, []):
            d[x].append(y)

    for lid in (CAWL, SWADESH):
        for i in get(lid).items:
            for e in i.eacw:
                add(lid, EACW, i.number, e)
                add(EACW, lid, e, i.number)
    for i in get(SWADESH).items:
        for c in i.cawl:
            add(SWADESH, CAWL, i.number, c)
            add(CAWL, SWADESH, c, i.number)
    return m


def mapped(src: str, number: str, dst: str) -> list[str]:
    """The numbers in list `dst` that item `number` of list `src` maps to."""
    if src == dst:
        return [number]
    out = list(_maps().get((src, dst), {}).get(number, []))
    if not out and {src, dst} == {CAWL, SWADESH}:      # through the EACW, when there's no direct pair
        for e in mapped(src, number, EACW):
            for x in mapped(EACW, e, dst):
                if x not in out:
                    out.append(x)
    return out


def _order(lid: str, numbers) -> list[str]:
    pos = {i.number: k for k, i in enumerate(get(lid).items)}
    return sorted(set(numbers), key=lambda n: pos.get(n, 10 ** 9))


def other_numbers(base: str, number: str) -> dict[str, list[str]]:
    """The other lists' numbers for item `number` of the base list, as stored on a lemma."""
    out = {}
    for lid in LIST_IDS:
        if lid != base:
            nums = _order(lid, mapped(base, number, lid))
            if nums:
                out[lid] = nums
    return out


# ---- a database's lemmas -----------------------------------------------
def base_of(db) -> str:
    return list_id(getattr(db.metadata, "wordlist_base", "")) or ""


def numbers(db, entry, lid: str) -> list[str]:
    """Item numbers of list `lid` the lemma carries: its reference when `lid` is the database's base
    (and the list has it), and any stored on it."""
    out = []
    if base_of(db) == lid:
        n = canon(lid, entry.ref)
        if n:
            out.append(n)
    for n in entry.lists.get(lid, []):
        if n not in out:
            out.append(n)
    return out


def describe(db, entry) -> str:
    """'EACW C001b · CAWL 0345 · Swadesh 42' for the lemma's Reference tooltip ('' if none)."""
    parts = []
    for lid in LIST_IDS:
        nums = numbers(db, entry, lid)
        if nums:
            parts.append(f"{SHORT[lid]} {', '.join(nums)}")
    return " · ".join(parts)


_TERM = re.compile(r"^(eacw|cawl|swadesh)(?:\s+(\S+))?$", re.IGNORECASE)


def search_term(term: str) -> tuple[str, str | None] | None:
    """A quick search's item read as a wordlist search: `CAWL 345` → (CAWL, '0345'), `swadesh` →
    (SWADESH, None). A number the list doesn't have still counts as a wordlist search (it finds
    nothing), so `CAWL 9999` doesn't fall back to searching the text. None for anything else."""
    m = _TERM.match((term or "").strip())
    if not m:
        return None
    lid = m.group(1).upper()
    if m.group(2) is None:
        return lid, None
    return lid, canon(lid, m.group(2)) or "\0"


def search_match(db, entry, term: str) -> bool | None:
    """Whether a lemma matches a wordlist search item; None when the item isn't one."""
    st = search_term(term)
    if st is None:
        return None
    lid, num = st
    nums = numbers(db, entry, lid)
    return bool(nums) if num is None else num in nums


# ---- glosses -----------------------------------------------------------
def norm_gloss(text: str) -> str:
    """A gloss as compared for matching: capitals, brackets, a leading "to " or "be ", and
    punctuation at the ends ignored; spaces squeezed."""
    t = unicodedata.normalize("NFC", text or "").casefold()
    t = re.sub(r"\([^)]*\)", " ", t)
    t = re.sub(r"\s+", " ", t).strip(" .,;:!?'\"‘’“”")
    t = re.sub(r"^(to|be) ", "", t)
    return t.strip()


def gloss_keys(text: str) -> set[str]:
    """Every way a gloss can match: the whole, and each of its alternatives (`spine, backbone`)."""
    whole = norm_gloss(text)
    keys = {whole} if whole else set()
    for part in re.split(r"[,;/]", re.sub(r"\([^)]*\)", " ", text or "")):
        p = norm_gloss(part)
        if p:
            keys.add(p)
    return keys


def item_gloss(lid: str, item: Item) -> str:
    """The list's own gloss; for the CAWL without its glosses, the EACW's for its first match."""
    if item.gloss:
        return item.gloss
    for e in item.eacw:
        if (x := get(EACW).by_number.get(e)) is not None:
            return x.gloss
    return ""


def word_class_for(lid: str, item: Item) -> str:
    """A word class for a lemma made from the item (Josh, 22 October): the EACW item's it maps to,
    otherwise from the list's own markers ('(v)', '(be)', 'to …' → VERB; '(n)' → NOUN), else ''."""
    if item.word_class:
        return item.word_class
    for e in item.eacw:
        if (x := get(EACW).by_number.get(e)) is not None and x.word_class:
            return x.word_class
    return ""


# ---- export --------------------------------------------------------------
@dataclass
class Row:
    number: str
    gloss: str
    entries: list            # the lemmas carrying the number, in database order


def rows(db, lid: str) -> list[Row]:
    """Every item of the list, in its order, with the lemmas that carry it (none: a blank row)."""
    carried: dict[str, list] = {}
    for e in db.entries:
        for n in numbers(db, e, lid):
            carried.setdefault(n, []).append(e)
    wl = get(lid)
    return [Row(i.number, item_gloss(lid, i), carried.get(i.number, [])) for i in wl.items]


def gloss_matches(db, lid: str) -> list[tuple[str, object]]:
    """(number, lemma) for each list item no lemma carries, matched to lemmas with a filled Lemma
    whose English gloss matches the list's (Josh, 22 October: shown with ticks; the ticked ones are
    exported and their number stored). A lemma that already carries a number of this list isn't
    offered another."""
    if lid == CAWL and not get(CAWL).has_glosses:
        keys_of = lambda i: set().union(*(gloss_keys(get(EACW).by_number[e].gloss)
                                          for e in i.eacw if e in get(EACW).by_number)) if i.eacw else set()
    else:
        keys_of = lambda i: gloss_keys(i.gloss)
    taken, with_numbers = set(), set()
    for e in db.entries:
        nums = numbers(db, e, lid)
        taken.update(nums)
        if nums:
            with_numbers.add(e.id)
    by_key: dict[str, list] = {}
    for e in db.entries:
        if e.id in with_numbers or not db.lemma(e).strip():
            continue
        for k in gloss_keys(db.gloss(e)):
            by_key.setdefault(k, []).append(e)
    out, used = [], set()
    for i in get(lid).items:
        if i.number in taken:
            continue
        hits = []
        for k in keys_of(i):
            for e in by_key.get(k, []):
                if e.id not in used and e not in hits:
                    hits.append(e)
        for e in hits:
            used.add(e.id)
            out.append((i.number, e))
    return out


def table(db, lid: str, extra=()) -> tuple[list[str], list[list[str]]]:
    """The export's header and rows: number, lemma, gloss. `extra` adds (number, lemma) pairs (the
    ticked gloss matches) before they are stored. Several lemmas on one number are joined with ; ."""
    header = [SHORT[lid], "Lemma", "Gloss"]
    add: dict[str, list] = {}
    for n, e in extra:
        add.setdefault(n, []).append(e)
    out = []
    for r in rows(db, lid):
        es = r.entries + [e for e in add.get(r.number, []) if e not in r.entries]
        out.append([r.number, "; ".join(db.lemma(e) for e in es if db.lemma(e)), r.gloss])
    return header, out


def tsv(header, data) -> str:
    """Tab-separated, so it pastes as a table into Word or Excel."""
    clean = lambda s: str(s).replace("\t", " ").replace("\n", " ")
    return "\n".join("\t".join(clean(c) for c in row) for row in [header, *data]) + "\n"


# ---- linking an existing database --------------------------------------
def link_plan(db, base: str) -> list[tuple[object, dict[str, list[str]]]]:
    """For Tools → Link to wordlists…: (lemma, its new numbers of the other lists) for each lemma
    whose reference is an item of the base list and whose numbers would change."""
    out = []
    for e in db.entries:
        n = canon(base, e.ref)
        if not n:
            continue
        new = other_numbers(base, n)
        old = {k: v for k, v in e.lists.items() if k != base and v}
        if new != old:
            out.append((e, new))
    return out
