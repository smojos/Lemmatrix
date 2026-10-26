# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders. Additional terms: NOTICE.md
"""The comparative wordlists (IDEAS.md idea 40, designed with Josh 22 October 2026): the
Extended African Comparative Wordlist (EACW, Josh's own), the SIL Comparative African Wordlist
(CAWL; Snider & Roberts 2006) and the Swadesh list (207 items).

The lists live here, in Lemmatrix, never in a database (Josh: "that must be stored in Lemmatrix
not in the XML database"). A database built on one of them has that list's numbers as its
references (its *base*); the other lists' numbers are stored on each lemma, readable in the XML
and shown nowhere else (`<entry ref="C001f" cawl="0345" swadesh="42">`). They are data: they
describe the lemmas, so they go into the archives too.

The data files beside this module (tab-separated, UTF-8, one header line):
- `eacw.tsv`: ref, gloss, word class, default (yes: the published list; no: a hidden item, a
  recommended variant a researcher can add), sub (blank: everyone; A: all of Africa; N W E S C: only
  those regions), clarification (the gloss's plain meaning) and taxon (with its family), in the
  list's own order (the final list of 23 October 2026: 2,556 items);
- `cawl.tsv`: number, domain, word class, the EACW items it maps to, and its English and French
  glosses when SIL's permission allows them to be shipped (until then the columns are empty);
- `swadesh.tsv`: number, gloss, word class, the EACW items and CAWL numbers it maps to.
The data files are not under the AGPL: see `THIRD-PARTY.md` and `CITATIONS` below.

No Qt here.
"""

from __future__ import annotations

import bisect
import csv
import re
import unicodedata
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

HERE = Path(__file__).parent

EACW, CAWL, SWADESH = "EACW", "CAWL", "SWADESH"
LIST_IDS = (EACW, CAWL, SWADESH)

# Citations and DOIs, shown in New database's hovers, the exports and the documentation. The EACW's
# DOI is added once it has one (Josh, 22 October: "Once I get a DOI that can be added").
CITATIONS = {
    EACW: "Smolders, Joshua. 2026. The Extended African Comparative Wordlist: A lexical organization system for field linguists.",
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
    number: str                       # the list's own form: C001f, 0345, 42
    gloss: str = ""                   # English ("" for the CAWL until its glosses can be shipped)
    word_class: str = ""
    domain: str = ""                  # the CAWL's section number (1.1.1)
    french: str = ""
    eacw: list[str] = field(default_factory=list)     # the EACW items it maps to (CAWL, Swadesh)
    cawl: list[str] = field(default_factory=list)     # the CAWL numbers it maps to (Swadesh)
    default: bool = True              # EACW: in the published list (False: a hidden item)
    sub: list[str] = field(default_factory=list)      # EACW: the regions it is for ([] everyone, A, N W E S C)
    clarification: str = ""           # EACW: the gloss's plain meaning
    taxon: str = ""                   # EACW: animals and plants, with the family (Capra hircus (Bovidae))


# ---- the EACW's versions (Josh, 23 October 2026) --------------------------
# New database → EACW: the base list (its default items) or the expanded list (the hidden items
# too), and global (only the items for everyone), Africa (every region) or one region.
BASE, EXPANDED = "base", "expanded"
GLOBAL, AFRICA = "global", "africa"
REGIONS = {"N": "North", "W": "West", "E": "East", "S": "South", "C": "Central"}   # Josh's order: N W E S C
REGION_NAMES = {GLOBAL: "Global", AFRICA: "Africa", **REGIONS}
ITEM_NAMES = {BASE: "Base", EXPANDED: "Expanded"}


# ---- the EACW's editions (Josh, 24 October 2026: "I want to be able to update EACW periodically") ---
# Each edition of the shipped list, oldest first: its date (the version a database records on its
# <wordlist>, format 12), what changed, and the items it made default or hid. A database with no
# version is on the first edition (every EACW database was made from it or after it). A new edition
# goes at the end, with the eacw.tsv that has it; on opening, a database on an older one is told and
# offered the update (Tools → Audits → Check wordlist integrity…, lemmatrix/wordlist_check.py).
@dataclass(frozen=True)
class Edition:
    version: str
    note: str
    made_default: frozenset = frozenset()
    hidden: frozenset = frozenset()


EDITIONS = (
    Edition("2026-10-23", "The final list (2,281 published items)"),
    Edition("2026-10-24", "B044f the default, B044 hidden; C009 hidden; C012–C024 hidden, all their f and m "
            "the default (2,274 published)",
            made_default=frozenset({"B044f", "C015f", "C015m", "C019f", "C019m"}),
            hidden=frozenset({"B044", "C009", *(f"C0{n}" for n in range(12, 25))})),
)
EACW_VERSION = EDITIONS[-1].version


def editions_since(version: str) -> list[Edition]:
    """The editions after a database's version ("" or unknown: the first edition's)."""
    known = [e.version for e in EDITIONS]
    at = known.index(version) if version in known else 0
    return list(EDITIONS[at + 1:])


def in_version(item: Item, items: str = EXPANDED, region: str = AFRICA) -> bool:
    """Whether an EACW item is in a version of the list: base (default items only) or expanded;
    global (blank sub code), Africa (all) or a region (blank, A, or that region's letter)."""
    if items == BASE and not item.default:
        return False
    if region == GLOBAL:
        return not item.sub
    if region in REGIONS:
        return not item.sub or "A" in item.sub or region in item.sub
    return True


def version_items(items: str = EXPANDED, region: str = AFRICA) -> list[Item]:
    return [i for i in get(EACW).items if in_version(i, items, region)]


def version_name(items: str, region: str) -> str:
    return f"{ITEM_NAMES.get(items, items)}, {REGION_NAMES.get(region, region)}"


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
        items = [Item(r["ref"], r["gloss"], r["word_class"], default=(r.get("default") or "yes") != "no",
                      sub=_split(r.get("sub")), clarification=r.get("clarification") or "",
                      taxon=r.get("taxon") or "") for r in _read("eacw.tsv")]
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
    """A number as the list writes it: `c001F` → C001f, `345` → 0345, `042` → 42. None if the list
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


# Two patterns on purpose (the audit, 26 October): _FAMILY is a list item's family (a section's
# letter, three digits, at most one letter: B033f), _STEM any reference's family for sorting, the
# researcher's own too (D1000, B001bc; see _places).
_FAMILY = re.compile(r"([A-QV]\d{3})([a-z]?)")   # Q too: Q001b first, Q002b second (the audit, 25 October)


def family(number: str) -> list[Item]:
    """The EACW items that share an item's number (B033, B033f, B033m; J073, J073b…), in list order."""
    m = _FAMILY.fullmatch(number or "")
    if not m:
        return []
    stem = m.group(1)
    return [i for i in get(EACW).items if i.number[:4] == stem and _FAMILY.fullmatch(i.number)]


def _gender_family(number: str) -> list[str]:
    """An item, its female and male (Xf, Xm) and their generic (X), when the family has f or m."""
    m = _FAMILY.fullmatch(number or "")
    if not m or m.group(2) not in ("", "f", "m"):
        return []
    stem = m.group(1)
    have = get(EACW).by_number
    members = [n for n in (stem, stem + "f", stem + "m") if n in have]
    return members if any(n != stem for n in members) else []


def other_numbers(base: str, number: str) -> dict[str, list[str]]:
    """The other lists' numbers for item `number` of the base list, as stored on a lemma.

    A hidden EACW item with no number of a list takes the numbers of its gendered family's
    published members (Josh, 23 October: B033f female warrior, if added, goes with B033m male
    warrior's CAWL 0406), or of its other members if those have none. A published item keeps
    only its own. The human terms (B and C) don't inherit: they carry their family links in the
    data itself since 24 October (an un-gendered CAWL or Swadesh item on the generic and its female
    and male, a gendered pair on the generic too, unless the family is discrete like B004 child,
    girl, boy), so CAWL young man stays off B015f female youth."""
    out = {}
    eacw = get(EACW).by_number
    for lid in LIST_IDS:
        if lid != base:
            nums = _order(lid, mapped(base, number, lid))
            if (not nums and base == EACW and number in eacw and not eacw[number].default
                    and number[:1] not in "BC"):            # the human terms: their links are in the data
                fam = [n for n in _gender_family(number) if n != number]
                got = []
                for group in ([n for n in fam if eacw[n].default], fam):
                    for n in group:
                        got += [x for x in mapped(EACW, n, lid) if x not in got]
                    if got:
                        break
                nums = _order(lid, got)
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
    """'EACW C001f · CAWL 0345 · Swadesh 42' for the lemma's Reference tooltip ('' if none)."""
    parts = []
    for lid in LIST_IDS:
        nums = numbers(db, entry, lid)
        if nums:
            parts.append(f"{SHORT[lid]} {', '.join(nums)}")
    return " · ".join(parts)


_TERM = re.compile(r"^(-)?\s*(eacw|cawl|swadesh)(?:\s+(\S+))?$", re.IGNORECASE)
_SMOLDER = ("josh", "joshua")                 # Josh, 23 October: his name finds V139 *to smolder*


def search_term(term: str) -> tuple[str, str | None, bool] | None:
    """A quick search's item read as a wordlist search: `CAWL 345` → (CAWL, '0345', False),
    `swadesh` → (SWADESH, None, False); a leading minus is everything but (`-CAWL` → the lemmas
    with no CAWL number; Josh, 23 October). A number the list doesn't have still counts as a
    wordlist search (it finds nothing), so `CAWL 9999` doesn't fall back to searching the text.
    `Josh` or `Joshua` → (EACW, 'V139', False). None for anything else."""
    t = (term or "").strip()
    if t.casefold() in _SMOLDER:
        return EACW, "V139", False
    m = _TERM.match(t)
    if not m:
        return None
    lid, minus = m.group(2).upper(), bool(m.group(1))
    if m.group(3) is None:
        return lid, None, minus
    return lid, canon(lid, m.group(3)) or "\0", minus


def search_match(db, entry, term: str) -> bool | None:
    """Whether a lemma matches a wordlist search item; None when the item isn't one. A taxon
    matches too, shown as a column or not (Josh, 23 October: a genus finds every item of that
    genus; a family every item of that family), and then the columns aren't searched."""
    st = search_term(term)
    if st is None:
        f = db.settings.entry_field(TAXON)
        if f is not None and len(term.strip()) >= 3:
            hay = unicodedata.normalize("NFD", entry.get(f.name)).casefold()
            hay = "".join(ch for ch in hay if not unicodedata.combining(ch))
            if term.strip().casefold() in hay:
                return True
        return None
    lid, num, minus = st
    nums = numbers(db, entry, lid)
    hit = bool(nums) if num is None else num in nums
    return hit != minus


# ---- an EACW database: its fields, and the hidden items within reach ------
# (Josh, 23 October 2026: "hidden items stay within reach": a peek in the Reference's hover, a
# clashing reference warns, a matching gloss offers the reference; f and m are reserved)
CLARIFICATION, TAXON = "clarification", "taxon"      # the roles of the two lemma fields
LETTERS = "abcdeghijklnopqrstuvwxyz"                 # sub-letters in order: f and m are reserved


def is_eacw(db) -> bool:
    return base_of(db) == EACW


def ensure_fields(db) -> list[str]:
    """An EACW database's Clarification and Taxon lemma fields (Josh, 23 October: lemma fields,
    editable, so a species a researcher adds has its own taxon), after the others. Returns the
    titles of the fields added."""
    from ..model import FieldDef
    s, added = db.settings, []
    for role, name in ((CLARIFICATION, "Clarification"), (TAXON, "Taxon")):
        if s.entry_field(role) is None:
            s.entry_fields.append(FieldDef(name, role=role))
            added.append(name)
    return added


def ensure_word_classes(db) -> list[str]:
    """The EACW's word classes the database's Word Class list lacks (DEM, CONJ…), added at its
    end. Returns those added."""
    f = db.settings.entry_field("word-class")
    if f is None:
        return []
    have, added = set(f.all_values()), []
    for i in get(EACW).items:
        if i.word_class and i.word_class not in have:
            f.add_value(i.word_class)
            have.add(i.word_class)
            added.append(i.word_class)
    return added


def fill_item(db, entry, item: Item, overwrite: bool = False):
    """A lemma made from (or made into) an EACW item: its gloss, word class, Clarification and
    Taxon where empty (all of them with overwrite), and the other lists' numbers."""
    s = db.settings
    for role, value, lang in (("gloss", item.gloss, s.primary_gloss), ("word-class", item.word_class, None),
                              (CLARIFICATION, item.clarification, None), (TAXON, item.taxon, None)):
        f = s.entry_field(role)
        if f is None or not value:
            continue
        if role == "word-class" and value not in s.word_classes():
            continue
        current = entry.get(f.name, lang) if f.multilingual else entry.get(f.name)
        if overwrite or not current:
            entry.set(f.name, value, lang if f.multilingual else None, f.multilingual)
    if not entry.file_gloss and item.gloss:
        entry.file_gloss = "".join(ch for ch in item.gloss if ch not in _forbidden())
    if is_eacw(db):
        entry.lists = {k: v for k, v in entry.lists.items() if k == EACW}
        entry.lists.update(other_numbers(EACW, item.number))


def _forbidden() -> str:
    from ..model import FORBIDDEN_CHARS
    return FORBIDDEN_CHARS


def missing(db) -> list[Item]:
    """The EACW items an EACW database doesn't have (by reference), in list order."""
    if not is_eacw(db):
        return []
    have = {canon(EACW, e.ref) for e in db.entries}
    return [i for i in get(EACW).items if i.number not in have]


def missing_family(db, entry) -> list[Item]:
    """The items of a lemma's family (the same number) the database doesn't have: the peek."""
    if not is_eacw(db):
        return []
    have = {canon(EACW, e.ref) for e in db.entries}
    return [i for i in family(canon(EACW, entry.ref) or "") if i.number not in have]


def unused_item(db, ref: str) -> Item | None:
    """The EACW item a reference is, when the database doesn't have it yet (a clash with a hidden
    item, for the lemma dialogue's warning)."""
    if not is_eacw(db):
        return None
    n = canon(EACW, ref)
    if not n or any(canon(EACW, e.ref) == n for e in db.entries):
        return None
    return get(EACW).by_number[n]


def gloss_items(db, gloss: str) -> list[Item]:
    """EACW items the database doesn't have whose gloss is this one (whole, or one of the
    item's alternatives): a new lemma with that gloss is offered the item's reference."""
    key = norm_gloss(gloss)
    if not key or not is_eacw(db):
        return []
    return [i for i in missing(db) if key in gloss_keys(i.gloss)]


def reserved(ref: str) -> tuple[str, str] | None:
    """(the item's number, f or m) when a reference ends in f or m after a number (C123f), which
    mean female and male only (Josh, 23 October); None otherwise."""
    m = re.fullmatch(r"([A-Z]+\d+)([fm])", ref or "")
    return (m.group(1), m.group(2)) if m else None


def next_letter(db, stem: str) -> str:
    """The next free sub-letter of an item, skipping f and m: C123b, C123c… C123g."""
    taken = {e.ref for e in db.items()} | ({i.number for i in get(EACW).items} if is_eacw(db) else set())
    for ch in LETTERS[1:]:
        if stem + ch not in taken:
            return stem + ch
    return stem + "z"


def peek(db, entry) -> str:
    """The Reference's hover in an EACW database: the numbers, the Clarification and Taxon, and the
    items of the same number not in the database (hidden or not inserted)."""
    lines = []
    if (d := describe(db, entry)):
        lines.append(d)
    s = db.settings
    for role, label in ((CLARIFICATION, "Clarification"), (TAXON, "Taxon")):
        f = s.entry_field(role)
        if f is not None and entry.get(f.name):
            lines.append(f"{label}: {entry.get(f.name)}")
    near = missing_family(db, entry)
    if near:
        lines.append("Not in this database (Insert EACW items… adds them):")
        lines += [f"   {i.number}  {i.gloss}" + ("" if i.default else "  (hidden)") for i in near]
    return "\n".join(lines)


_STEM = re.compile(r"^([A-Z]\d{3,4})([a-z]*)$")   # any reference, for sorting (see _FAMILY)


@lru_cache(maxsize=1)
def _places():
    """The EACW's items by position, by family (A030 → [(position, ""), (…, "a"), …]) and the last
    position of each section letter. Worked out once (the list doesn't change while Lemmatrix runs):
    it was worked out again for every lemma compared (the audit, 25 October)."""
    items = get(EACW).items
    pos = {i.number: k for k, i in enumerate(items)}
    families: dict[str, list[tuple[int, str]]] = {}
    section_end: dict[str, int] = {}
    for k, i in enumerate(items):
        m = _STEM.match(i.number)
        if m:
            families.setdefault(m.group(1), []).append((k, m.group(2)))
        section_end[i.number[:1]] = k
    return pos, families, section_end


def place(ref: str, places=None) -> tuple | None:
    """Where a reference sorts in the EACW's order (Josh, 23 October): an item at its place; a
    reference of the researcher's own under an item's number (B001b, A002c) inside that family in
    alphabetical order of its letters, as the list orders its families (B001, B001b, B001f, B001m);
    any other reference with a section's letter (an ethnic group's C + ISO code, RC3) at the end of
    that section, alphabetically. None if it has no place (no section letter)."""
    return _place(ref) if places is None or places is _places() else _place_in(ref, places)


@lru_cache(maxsize=1 << 16)
def _place(ref: str) -> tuple | None:
    return _place_in(ref, _places())


def _place_in(ref: str, places) -> tuple | None:
    pos, families, section_end = places
    item = canon(EACW, ref)
    if item is not None:
        return (pos[item], 0, "")
    t = (ref or "").strip()
    m = _STEM.match(t)
    if m and m.group(1) in families:
        fam, mine = families[m.group(1)], m.group(2)
        before = [k for k, letters in fam if letters < mine]
        return (max(before), 1, mine) if before else (fam[0][0] - 0.5, 1, mine)
    if t[:1] in section_end:
        return (section_end[t[:1]], 2, t)
    return None


def insert_position(entries, ref: str) -> int | None:
    """Where a new lemma goes among the lemmas of an EACW database: after the last lemma that sorts
    before it in the list's order (at the start if none). None if its reference has no place."""
    places = _places()
    me = place(ref, places)
    if me is None:
        return None
    at = 0
    for k, e in enumerate(entries):
        p = place(e.ref, places)
        if p is not None and p <= me:
            at = k + 1
    return at


def eacw_order(entries) -> list:
    """Lemmas in the EACW's order (`place`); a lemma whose reference has no place stays after the
    one it follows now."""
    places = _places()
    keyed, last = [], (-1.0, -1, "")
    for k, e in enumerate(entries):
        p = place(e.ref, places)
        if p is not None:
            last = p
            keyed.append((p, 0, k, e))
        else:
            keyed.append((last, 1, k, e))
    return [e for *_, e in sorted(keyed, key=lambda x: x[:3])]


def out_of_place(entries) -> tuple[list, list]:
    """Tools → Check reference order (Josh, 23 October): the lemmas in the EACW's order, and the
    fewest lemmas that have to move to get there (the rest, the longest run already in order, stay
    put)."""
    entries = list(entries)
    order = eacw_order(entries)
    rank = {id(e): k for k, e in enumerate(order)}
    seq = [rank[id(e)] for e in entries]
    # the longest increasing run of ranks (patience sorting), kept; everything else moves
    tails, tails_at, back = [], [], [-1] * len(seq)
    for k, r in enumerate(seq):
        j = bisect.bisect_left(tails, r)
        back[k] = tails_at[j - 1] if j else -1
        if j == len(tails):
            tails.append(r)
            tails_at.append(k)
        else:
            tails[j], tails_at[j] = r, k
    keep, k = set(), (tails_at[-1] if tails_at else -1)
    while k >= 0:
        keep.add(id(entries[k]))
        k = back[k]
    return order, [e for e in order if id(e) not in keep]


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


def glosses_agree(a: str, b: str) -> bool:
    """Whether two glosses could name the same thing: a shared gloss or alternative, or one inside
    the other as whole words (*bread*, *traditional bread*)."""
    ka, kb = gloss_keys(a), gloss_keys(b)
    if ka & kb:
        return True
    words = lambda k: [f" {x} " for x in k]
    na, nb = f" {norm_gloss(a)} ", f" {norm_gloss(b)} "
    return any(x in nb for x in words(ka)) or any(x in na for x in words(kb))


def link_as_eacw(db, items: str = BASE, region: str = AFRICA):
    """Make a database built in code an EACW database, as Tools → Link to wordlists… would (the
    samples): the base and version, the Clarification and Taxon fields and the word classes, the
    other lists' numbers and the fields' values, and the lemmas in the list's order. No undo."""
    md = db.metadata
    md.wordlist_base, md.wordlist_items, md.wordlist_region = EACW, items, region
    md.wordlist_version = EACW_VERSION
    ensure_fields(db)
    ensure_word_classes(db)
    for e, numbers in link_plan(db, EACW):
        e.lists = {k: v for k, v in e.lists.items() if k == EACW}
        e.lists.update(numbers)
    for e, vals in field_plan(db):
        for name, value in vals.items():
            e.set(name, value)
    db.entries[:] = eacw_order(db.entries)


def sample_reference(db, gloss: str, letter: str, taken: set, verb: bool | None = None) -> str:
    """A sample lemma's reference: the EACW item its gloss names (in its section first, then any),
    else the database's next own reference in that section. Adds it to `taken`."""
    ref = (eacw_for_gloss(gloss, letter, taken, verb) or eacw_for_gloss(gloss, "", taken, verb)
           or db.suggest_reference(letter))
    taken.add(ref)
    return ref


def eacw_for_gloss(gloss: str, letter: str = "", taken=(), verb: bool | None = None) -> str | None:
    """The EACW item a gloss names, for building a database from glosses (the samples): an item
    whose gloss or one of its alternatives is the same (a leading "to " or "be " ignored), in the
    section `letter` when given; published items first, then the whole gloss before an
    alternative, then list order; `verb` True or False keeps to verbs or to everything else. None
    if there is none (or all are `taken`)."""
    want = norm_gloss(gloss)
    if not want:
        return None
    best = None
    for k, i in enumerate(get(EACW).items):
        if i.number in taken or (letter and not i.number.startswith(letter)):
            continue
        if verb is not None and (i.word_class == "VERB") != verb:
            continue
        whole = norm_gloss(i.gloss) == want
        if not whole and want not in gloss_keys(i.gloss):
            continue
        key = (not i.default, not whole, k)
        if best is None or key < best[0]:
            best = (key, i.number)
    return best[1] if best else None


def gloss_mismatches(db, base: str) -> tuple[int, list[tuple[object, Item]]]:
    """For Link to wordlists… (Josh, 23 October: a database whose references weren't the list's
    numbers got the wrong items' numbers): how many lemmas with a reference in the list and a gloss
    can be compared, and those whose gloss doesn't agree with their item's."""
    wl = get(base)
    compared, out = 0, []
    for e in db.entries:
        n = canon(base, e.ref)
        gloss = db.gloss(e, "en") or db.gloss(e)
        if not n or not gloss:
            continue
        item = wl.by_number[n]
        theirs = item_gloss(base, item)
        if not theirs:
            continue
        compared += 1
        if not glosses_agree(gloss, theirs):
            out.append((e, item))
    return compared, out


def preferred_eacw(item: Item) -> list[str]:
    """An item's EACW matches, the closest first: a gendered item linked to its sex and the generic
    (CAWL 0345 mother → C001f and C001, Josh, 24 October) puts the gendered one first; otherwise
    the list's order (CAWL 0813 rich man → B047 rich person, B047f, B047m)."""
    groups: dict[str, list[str]] = {}
    for r in item.eacw:
        m = _FAMILY.fullmatch(r)
        groups.setdefault(m.group(1) if m else r, []).append(r)
    out = []
    for stem, refs in groups.items():
        sexed = [r for r in refs if r in (stem + "f", stem + "m")]
        if stem in refs and len(sexed) == 1:          # the generic and one sex: a gendered item
            refs = sexed + [r for r in refs if r not in sexed]
        out += refs
    return out


def item_gloss(lid: str, item: Item) -> str:
    """The list's own gloss; for the CAWL without its glosses, the EACW's for its closest match."""
    if item.gloss:
        return item.gloss
    for e in preferred_eacw(item):
        if (x := get(EACW).by_number.get(e)) is not None:
            return x.gloss
    return ""


def word_class_for(lid: str, item: Item) -> str:
    """A word class for a lemma made from the item (Josh, 22 October): the EACW item's it maps to,
    otherwise from the list's own markers ('(v)', '(be)', 'to …' → VERB; '(n)' → NOUN), else ''."""
    if item.word_class:
        return item.word_class
    for e in preferred_eacw(item):
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
        keys_of = lambda i: set().union(*(gloss_keys(get(EACW).by_number[e].gloss)       # the closest only
                                          for e in preferred_eacw(i)[:1] if e in get(EACW).by_number)) if i.eacw else set()
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


# The form column of File → Export → Wordlist…, written as a template (IDEAS.md idea 71, Josh,
# 26 October): the Soundfiles notation, `>` for else, fields by name, label or abbreviation.
DEFAULT_TEMPLATE = "{Phonemic>Phonetic} {Word Class}"
TEMPLATE_PRESETS = [("Phonemic, else Phonetic, and the word class", DEFAULT_TEMPLATE),
                    ("Lemma, else Phonemic, else Phonetic", "{Lemma>Phonemic>Phonetic}"),
                    ("Lemma, else Phonetic, else Phonemic", "{Lemma>Phonetic>Phonemic}"),
                    ("Phonetic", "{Phonetic}"),
                    ("Phonemic", "{Phonemic}")]
TEMPLATE_KEY = "wordlist/template"        # the database's workspace


def citation_token(db, entry):
    """The token that stands for a lemma: the one with no tags, else one with only its groups'
    default tags (SG where SG is the default); never just the first token, which may be a plural
    or a possessed form (25 October: the export could take one)."""
    tags = db.settings.tags

    def plain(tok) -> bool:
        return all(tags.tag(n) is not None and tags.tag(n).default for n in tok.tags)
    return next((x for x in entry.tokens if x.is_citation), None) or next((x for x in entry.tokens if plain(x)), None)


def template_values(db, entry) -> dict:
    """What a wordlist template can name: the lemma's fields, its citation token's fields (the
    lemma's win where both have one of a name, as Comment), and its reference."""
    s = db.settings
    values = {"reference": entry.ref}
    for f in s.entry_fields:
        values.setdefault(f.name, entry.get(f.name))
    t = citation_token(db, entry)
    if t is not None:
        for f in s.token_fields:
            values.setdefault(f.name, t.get(f.name))
    return values


def export_form(db, entry, template: str = DEFAULT_TEMPLATE) -> str:
    """A lemma's row in a wordlist export, from the template: by default its citation token's
    Phonemic, else its Phonetic, then its word class (Josh, 26 October; until then the Lemma
    field, then the citation token's Phonetic, then its Phonemic, a preset now). The template's
    first placeholder is the form: when it is empty the lemma gives nothing, so a word not yet
    collected leaves its row blank, never just its word class."""
    from ..filenames import lookup, render, split_pattern
    s = db.settings
    template = template or DEFAULT_TEMPLATE
    value_of = lookup(template_values(db, entry), list(s.entry_fields) + list(s.token_fields))
    first = next((name for _, name in split_pattern(template)[1] if name), "")
    if first and not any(value_of(a.strip()) for a in first.split(">") if a.strip()):
        return ""                                 # no form: not collected yet, the row stays blank
    return " ".join(render(template, value_of).split())


def template_unknown(db, template: str) -> list[str]:
    """The names in a template that call nothing (no field answers to them), for the dialogue."""
    from .. import fieldkeys
    from ..filenames import split_pattern
    s = db.settings
    fields = list(s.entry_fields) + list(s.token_fields)
    out = []
    for _, name in split_pattern(template or "")[1]:
        for alt in (name.split(">") if name else []):
            alt = alt.strip()
            if alt and alt.casefold() != "reference" and fieldkeys.find(fields, alt) is None:
                out.append(alt)
    return out


def table(db, lid: str, extra=(), template: str = DEFAULT_TEMPLATE) -> tuple[list[str], list[list[str]]]:
    """The export's header and rows: number, lemma, gloss. `extra` adds (number, lemma) pairs (the
    ticked gloss matches) before they are stored. Several lemmas on one number are joined with ; ."""
    header = [SHORT[lid], "Lemma", "Gloss"]
    add: dict[str, list] = {}
    for n, e in extra:
        add.setdefault(n, []).append(e)
    out = []
    for r in rows(db, lid):
        es = r.entries + [e for e in add.get(r.number, []) if e not in r.entries]
        out.append([r.number, "; ".join(f for f in (export_form(db, e, template) for e in es) if f), r.gloss])
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


def field_plan(db) -> list[tuple[object, dict[str, str]]]:
    """For Link to wordlists… on the EACW: (lemma, {field name: value}) for each lemma whose empty
    Clarification or Taxon the list can fill (a value the researcher typed is never replaced)."""
    s, out = db.settings, []
    fields = [(f, role) for role in (CLARIFICATION, TAXON) if (f := s.entry_field(role)) is not None]
    for e in db.entries:
        n = canon(EACW, e.ref)
        item = get(EACW).by_number.get(n) if n else None
        if item is None:
            continue
        vals = {f.name: getattr(item, role) for f, role in fields if getattr(item, role) and not e.get(f.name)}
        if vals:
            out.append((e, vals))
    return out
