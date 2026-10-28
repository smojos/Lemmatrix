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


def built_from(db) -> set:
    """The ids of the lemmas other lemmas are built from (their From), for has_data's used_in."""
    return {i for o in db.entries for i in o.from_lemmas}


def has_data(db, e, used_in: set | None = None) -> bool:
    """Whether a lemma holds anything of the researcher's: a token with something in it, a field
    the list doesn't fill, a gloss in another language, From, or another lemma built from it.
    The one test for "empty" (Check wordlist integrity and Convert references from a table both
    use it); used_in: built_from(db), worked out once when many lemmas are asked about."""
    if any(t.has_content() for t in e.tokens):
        return True
    s = db.settings
    own = {f.name for role in ("gloss", "word-class", wl.CLARIFICATION, wl.TAXON)
           if (f := s.entry_field(role)) is not None}
    fresh = db.new_entry(e.ref).values               # what every new lemma has (Stem type: simple)
    if any(v.strip() and fresh.get(k) != v for k, v in e.values.items() if k not in own):
        return True
    gname = f.name if (f := s.entry_field("gloss")) is not None else ""
    n = wl.canon(wl.EACW, e.ref) if wl.is_eacw(db) else None

    def shipped(name, lang, v):                    # a gloss the EACW brought (idea 63) isn't the researcher's
        return n is not None and name == gname and v.strip() == wl.item_gloss_in(n, lang)
    for name, langs in e.multi.items():
        if any(v.strip() and (name not in own or lang not in (s.primary_gloss, "en")) and not shipped(name, lang, v)
               for lang, v in langs.items()):
            return True
    if e.from_lemmas or e.from_languages:
        return True
    return e.id in (built_from(db) if used_in is None else used_in)


def _numbers_text(base: str, e, new: dict) -> str:
    out = []
    for lid in wl.LIST_IDS:
        if lid == base:
            continue
        old, now = e.lists.get(lid) or [], new.get(lid) or []
        if old != now:
            out.append(f"{wl.SHORT[lid]} {', '.join(old) or '—'} → {', '.join(now) or '—'}")
    return "; ".join(out)


# ---- an edition that renumbered items (2026-10-27) ------------------------
@dataclass
class Renumbering:
    """What an edition's renumbering does to a database, worked out before anything changes: the
    lemmas with their changed copies (the new reference, and the new list gloss where the lemma's
    is still the old list's), the empty lemmas of deleted items (removed), and `shadow`, a stand-in
    database whose lemmas are as they will be, which the other checks run on (so they compare the
    new references with the new list, never the old numbers with it)."""
    pairs: list = field(default_factory=list)       # (lemma, its changed copy)
    removed: list = field(default_factory=list)     # the empty lemmas of deleted items
    moved_own: list = field(default_factory=list)   # (old reference, the own reference it got): deleted
                                                    # items with data, and references clashing with new ones
    shadow: object = None
    real_of: dict = field(default_factory=dict)     # id(shadow lemma) → the real lemma

    @property
    def count(self) -> int:
        return len(self.pairs) + len(self.removed)


def _next_own(letter: str, taken: set, digits: int = 3) -> str:
    """The next own reference in a section after everything the list and the database use."""
    highest = 0
    for r in taken:
        if r.startswith(letter) and r[len(letter):].isdigit():
            highest = max(highest, int(r[len(letter):]))
    return f"{letter}{highest + 1:0{digits}d}"


def _file_gloss(text: str) -> str:
    from .model import FORBIDDEN_CHARS, nfc
    return "".join(ch for ch in nfc(text) if ch not in FORBIDDEN_CHARS).strip()


def renumbering(db) -> Renumbering | None:
    """The renumbering of the editions after the database's version, or None if none renumbers.

    - A lemma whose reference the conversion names takes its new reference.
    - A researcher's own reference under a renumbered item follows its item (P096e under P096 →
      P095e); under an item that became a sub-item or was deleted it can't, so it is kept under the
      next own reference of its section.
    - A redesignated item's lemma (D040 anteater, now aardwolf) with data keeps its meaning and its
      gloss under the next own reference of its section; an empty one becomes the new item.
    - A deleted item's lemma is removed when empty, and otherwise kept under the next own reference
      of its section (Josh, 27 October: *own ref at section end*); so is an own reference that a
      renumbered item now takes.
    - A gloss becomes the new list's only where it is still the old list's (a gloss of one's own is
      left), and the gloss in soundfile names follows only where it was the old gloss's."""
    from copy import copy as shallow
    from .model import nfc
    if not wl.is_eacw(db):
        return None
    conv = wl.conversion_since(version(db))
    if not conv:
        return None
    was_gloss = wl.old_glosses_since(version(db))
    s = db.settings
    eacw = wl.get(wl.EACW).by_number
    gf = s.entry_field("gloss")
    lang = "en" if "en" in s.gloss_languages else s.primary_gloss
    used = built_from(db)
    OWN = "+"                                   # "+D": the next own reference of section D
    r = Renumbering()
    target: dict[int, str] = {}
    redesigned = wl.redesignated_since(version(db))
    folded = {o.casefold(): o for o in conv}
    for e in db.entries:
        ref = e.ref.strip()
        if ref not in conv and ref.casefold() in folded:
            ref = folded[ref.casefold()]           # p096 typed by hand is P096 (the review)
        if ref in redesigned and ref not in conv:
            conv = {**conv, ref: ref}              # it stays where it is, unless it has data
        if ref in conv:
            to = conv[ref]
        else:
            m = wl._STEM.match(ref)
            stem = m.group(1) if m else ""
            if not (m and m.group(2) and stem in conv):
                continue                        # not touched by the renumbering
            plain = conv[stem]
            to = plain + m.group(2) if wl._STEM.fullmatch(plain) and len(plain) == len(stem) else OWN + ref[:1]
        if to in redesigned and has_data(db, e, used):
            to = OWN + ref[:1]                  # its word is for the old item, not the new one
        if to == "-":
            if has_data(db, e, used):
                to = OWN + ref[:1]
            else:
                r.removed.append(e)
                continue
        target[id(e)] = to
    gone = {id(e) for e in r.removed}
    list_targets = {v for v in target.values() if not v.startswith(OWN)}
    for e in db.entries:                        # an own reference a renumbered item now takes
        if id(e) not in gone and id(e) not in target and e.ref in list_targets:
            target[id(e)] = OWN + e.ref[:1]
    taken = set(eacw) | {target.get(id(e), e.ref) for e in db.entries if id(e) not in gone}
    for e in db.entries:
        t = target.get(id(e), "")
        if t.startswith(OWN):
            own = _next_own(t[1:], taken, s.ref_digits or 3)
            taken.add(own)
            target[id(e)] = own
            r.moved_own.append((e.ref, own))
    for e in db.entries:
        if id(e) in gone:
            continue
        ref = target.get(id(e), e.ref)
        after = None
        if ref != e.ref:
            after = e.copy()
            after.ref = nfc(ref)
        item, was = eacw.get(ref), was_gloss.get(e.ref)
        if gf is not None and item is not None and was and was != item.gloss:
            now = e.get(gf.name, lang) if gf.multilingual else e.get(gf.name)
            if now and " ".join(now.casefold().split()) == " ".join(was.casefold().split()):
                after = after or e.copy()
                after.set(gf.name, item.gloss, lang if gf.multilingual else None, gf.multilingual)
                if e.file_gloss == _file_gloss(was):
                    after.file_gloss = _file_gloss(item.gloss)
        if item is not None and e.ref.strip() in redesigned and ref == e.ref:   # empty, now the new item
            after = after or e.copy()
            for role, value in (("word-class", item.word_class), (wl.TAXON, item.taxon)):
                f = s.entry_field(role)
                if role == "word-class":
                    value = s.word_class_named(value)
                if f is not None and value:
                    after.set(f.name, value)
        if after is not None:
            r.pairs.append((e, after))
    finals = [target.get(id(e), e.ref) for e in db.entries if id(e) not in gone]
    if len(finals) != len(set(finals)):            # never two lemmas with one reference (a safety net)
        seen = set()
        for e in db.entries:
            if id(e) in gone:
                continue
            ref = target.get(id(e), e.ref)
            if ref in seen:
                own = _next_own(ref[:1], taken, s.ref_digits or 3)
                taken.add(own)
                r.moved_own.append((e.ref, own))
                after = next((a for x, a in r.pairs if x is e), None)
                if after is None:
                    after = e.copy()
                    r.pairs.append((e, after))
                after.ref = own
                ref = own
            seen.add(ref)
    shadow = shallow(db)
    after_of = {id(e): a for e, a in r.pairs}
    # the renumbering keeps the list's order (the snails land under H055, where H056–H058 were); only
    # a lemma moved under an own reference goes to its new place (the end of its section)
    order = [after_of.get(id(e), e) for e in db.entries if id(e) not in gone]
    moved = {own for _, own in r.moved_own}
    for a in [x for x in order if x.ref in moved]:
        order.remove(a)
        at = wl.insert_position(order, a.ref)
        order.insert(len(order) if at is None else at, a)
    shadow.entries = order
    shadow.metadata = shallow(db.metadata)
    r.shadow = shadow
    r.real_of = {id(a): e for e, a in r.pairs}
    return r


_UNSET = object()


def check(db, rn=_UNSET) -> list[Finding]:
    """Everything that isn't as the shipped list has it, in KINDS order. A database still on old
    numbers (an edition renumbered items since) is checked as it will be once renumbered: pass the
    `renumbering(db)` the fixes will be planned with, so the findings name its stand-in lemmas."""
    base = wl.base_of(db)
    if not base:
        return []
    if rn is _UNSET:
        rn = renumbering(db)
    if rn is not None:
        db = rn.shadow
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


def plan(db, findings, new_entry, rn: "Renumbering | None" = None) -> tuple[list, list, list]:
    """What fixing the selected findings does: (the lemmas' new order, (lemma, its changed copy)
    pairs, the new lemmas), for Document.restructure as one undo step. new_entry(item) makes the
    lemma for a missing item (with the session's speaker and date). The database isn't changed.
    rn: the renumbering the findings were checked after (they name its stand-in lemmas); it is always
    part of the plan, whatever is selected, and the result names the real lemmas."""
    if rn is not None:
        order, pairs, made = _plan(rn.shadow, findings, new_entry)
        real = lambda e: rn.real_of.get(id(e), e)
        first = {id(e): a for e, a in rn.pairs}                       # real lemma → renumbered copy
        fixed = {id(real(e)): a for e, a in pairs}                    # real lemma → the fixes' copy
        out_pairs = [(e, fixed.get(id(e), a)) for e, a in rn.pairs]
        out_pairs += [(real(e), a) for e, a in pairs if id(real(e)) not in first]
        return [real(e) for e in order], out_pairs, made
    return _plan(db, findings, new_entry)


def _plan(db, findings, new_entry) -> tuple[list, list, list]:
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


def update_file(db, new_entry=None) -> tuple[int, list[str]]:
    """The editions notice's Update without the program (the samples, and tests): every fix that
    starts selected, the edition's renumbering with its recordings and pictures renamed, and the
    shipped edition recorded. Changes `db` in place (not saved). Returns (fixes, problems): when a
    file can't be renamed nothing changes."""
    from pathlib import Path
    from . import convert_refs as cr
    from . import storage
    rn = renumbering(db)
    findings = check(db, rn)
    if new_entry is None:
        def new_entry(item):
            e = db.new_entry(item.number, gloss=item.gloss,
                             word_class=db.settings.word_class_named(item.word_class))
            wl.fill_item(db, e, item)
            return e
    order, pairs, made = plan(db, findings, new_entry, rn)
    renames = []
    if rn is not None:
        renames, _ = cr.file_renames(db, pairs)
        pairs = cr.token_files(db, pairs)
    done = []
    for old, new in renames:
        old, new = Path(old), Path(new)
        problem = ""
        if not old.exists() or (new.exists() and not storage.same_file(old, new)):
            problem = f"{old.name} can't be renamed to {new.name}"
        else:
            try:
                old.rename(new)
            except OSError as exc:
                problem = f"{old.name}: {exc}"
        if problem:
            stuck = []
            for o, n in reversed(done):           # everything back as it was
                try:
                    n.rename(o)
                except OSError:
                    stuck.append(f"{n.name} couldn't be named {o.name} again")
            return 0, [problem, *stuck]
        done.append((old, new))
    after = {id(e): a for e, a in pairs}
    db.entries[:] = [after.get(id(e), e) for e in order]
    if wl.is_eacw(db):
        db.metadata.wordlist_version = wl.EACW_VERSION
    return sum(1 for f in findings if f.selected and f.fixable) + (rn.count if rn else 0), []
