# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders. Additional terms: NOTICE.md
"""Tools → Convert references from a table… (Josh, 23 October 2026): a database's references changed
all at once from a conversion map, e.g. a database made from an earlier numbering of a wordlist
moving to its new one. References can't be changed one by one in Lemmatrix (they are part of the
soundfile names, and the comparative wordlists' numbers hang on them), so this is the one way.

The table is a CSV or tab-separated file with a header naming its columns:
- `old`: the reference now;
- `new`: the reference it becomes, or `-` to delete the lemma (only when it has no data);
- `gloss` (optional): its new primary gloss (the gloss in file names follows);
- `old gloss` (optional): the gloss is changed only when the lemma's gloss is still this one, so a
  gloss the researcher changed is left alone.
A table is the researcher's own: nothing of it is kept in Lemmatrix (Josh: no database's conversion
"trapped in the code"; the tool stays, for future conversions).

Everything happens at once, by lemma, never one rename after another: references in the table may
swap places. Recordings whose names were up to date are renamed to their new names (through
temporary names), and so are pictures in Images; one undo step. No Qt here.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path

from .model import FORBIDDEN_CHARS, Database, Entry, forbidden_in, nfc

DELETE = {"-", "(deleted)", "(removed)", "delete"}
HEADERS = {"old": "old", "old ref": "old", "old reference": "old",
           "new": "new", "new ref": "new", "new reference": "new",
           "gloss": "gloss", "new gloss": "gloss",
           "old gloss": "old_gloss", "gloss now": "old_gloss"}


@dataclass
class Row:
    old: str
    new: str
    gloss: str = ""
    old_gloss: str = ""


class TableError(Exception):
    pass


def read_table(path) -> list[Row]:
    """The conversion map's rows. Tab-separated or CSV (by the header line); a header is needed."""
    text = Path(path).read_text(encoding="utf-8-sig")
    lines = text.splitlines()
    if not lines:
        raise TableError("The table is empty.")
    delim = "\t" if "\t" in lines[0] else ("," if "," in lines[0] else ";")
    rows = list(csv.reader(lines, delimiter=delim))
    head = [HEADERS.get(h.strip().casefold(), "") for h in rows[0]]
    if "old" not in head or "new" not in head:
        raise TableError("The table needs a header line with the columns old and new "
                         "(and gloss and old gloss if glosses change).")
    out = []
    for r in rows[1:]:
        if not any(c.strip() for c in r):
            continue
        get = lambda k: nfc(r[head.index(k)].strip()) if k in head and head.index(k) < len(r) else ""
        if get("old"):
            out.append(Row(get("old"), get("new"), get("gloss"), get("old_gloss")))
    return out


def has_data(db: Database, e: Entry) -> bool:
    """Whether a lemma holds anything a researcher put there: a token with content, a lemma form or
    any lemma field but its gloss, word class, stem type and the wordlist's Clarification and
    Taxon; From links."""
    if any(t.has_content() for t in e.tokens) or e.from_lemmas or e.from_languages:
        return True
    s = db.settings
    skip = {f.name for f in s.entry_fields if f.role in ("gloss", "word-class", "stem-type", "clarification", "taxon")}
    return any(v for k, v in e.values.items() if k not in skip)


def _norm(text: str) -> str:
    return " ".join((text or "").casefold().split())


@dataclass
class Plan:
    refs: list = field(default_factory=list)        # (entry, new reference)
    glosses: list = field(default_factory=list)     # (entry, new gloss)
    deletions: list = field(default_factory=list)   # entries deleted (empty ones)
    unknown: list = field(default_factory=list)     # old references the database doesn't have
    left: list = field(default_factory=list)        # (entry, why): rows that change nothing
    problems: list = field(default_factory=list)    # what stops the conversion

    @property
    def changes(self) -> int:
        return len(self.refs) + len(self.glosses) + len(self.deletions)


def plan(db: Database, rows: list[Row]) -> Plan:
    p = Plan()
    by_ref = {e.ref: e for e in db.entries}
    seen = set()
    gf = db.settings.entry_field("gloss")
    for r in rows:
        if r.old in seen:
            p.problems.append(f"{r.old} is in the table twice")
            continue
        seen.add(r.old)
        e = by_ref.get(r.old)
        if e is None:
            p.unknown.append(r.old)
            continue
        if r.new in DELETE or not r.new:
            if has_data(db, e):
                p.problems.append(f"{r.old} {db.gloss(e)} has data, so it can't be deleted: give it a new reference")
            else:
                p.deletions.append(e)
            continue
        if forbidden_in(r.new):
            p.problems.append(f"{r.new}: a reference can't contain {' '.join(FORBIDDEN_CHARS)}")
            continue
        if r.new != e.ref:
            p.refs.append((e, r.new))
        if r.gloss and gf is not None:
            now = db.gloss(e)
            if r.old_gloss and _norm(now) != _norm(r.old_gloss):
                p.left.append((e, f"gloss left as “{now}” (the table expects “{r.old_gloss}”)"))
            elif now != r.gloss:
                p.glosses.append((e, r.gloss))
    gone = {id(e) for e in p.deletions}
    final: dict[str, Entry] = {}
    new_of = {id(e): n for e, n in p.refs}
    for e in db.entries:
        if id(e) in gone:
            continue
        ref = new_of.get(id(e), e.ref)
        if ref in final:
            p.problems.append(f"two lemmas would be {ref}: {final[ref].ref} and {e.ref}")
        final[ref] = e
    for x in [*db.utterances, *db.texts]:
        if x.ref in final and new_of.get(id(final[x.ref])):
            p.problems.append(f"{x.ref} is already an utterance's or text's reference")
    return p


def converted(db: Database, p: Plan) -> list[tuple[Entry, Entry]]:
    """(entry, its changed copy) for every lemma whose reference or gloss changes."""
    gf = db.settings.entry_field("gloss")
    out: dict[int, tuple[Entry, Entry]] = {}
    for e, ref in p.refs:
        out.setdefault(id(e), (e, e.copy()))[1].ref = nfc(ref)
    for e, gloss in p.glosses:
        after = out.setdefault(id(e), (e, e.copy()))[1]
        after.set(gf.name, gloss, db.settings.primary_gloss, gf.multilingual)
        after.file_gloss = "".join(ch for ch in nfc(gloss) if ch not in FORBIDDEN_CHARS).strip()
    return list(out.values())


def file_renames(db: Database, pairs) -> tuple[list[tuple[Path, Path]], list[str]]:
    """The recordings and pictures to rename for the changed lemmas: (old, new) through temporary
    names, so names can swap. A recording is renamed only when its name was up to date; one already
    out of date is left (Update all soundfile names deals with it) and listed."""
    from . import filenames, layout, storage
    moves, notes = [], []
    if not db.path:
        return [], []
    for e, after in pairs:
        folder = storage.folder_for(db, e)
        for t in e.tokens:
            if t.file:
                now, then = db.expected_filename(e, t), db.expected_filename(after, t)
                if t.file != now:
                    notes.append(f"{t.file}: already out of date, left as it is")
                elif then != now and (folder / t.file).exists():
                    moves.append((folder / t.file, folder / then))
            img = filenames.find_image(db, e, t)
            if img is not None:
                stem = filenames.image_stem(db, after, t)
                if stem != img.stem:
                    moves.append((img, img.with_name(stem + img.suffix)))
    renames = [(src, src.with_name(src.name + ".lemmatrix-renaming")) for src, _ in moves]
    renames += [(src.with_name(src.name + ".lemmatrix-renaming"), dst) for src, dst in moves]
    return renames, notes


def token_files(db: Database, pairs) -> list[tuple[Entry, Entry]]:
    """The changed copies with their tokens' stored file names following the renames."""
    out = []
    for e, after in pairs:
        for t, ta in zip(e.tokens, after.tokens):
            if t.file and t.file == db.expected_filename(e, t):
                ta.file = db.expected_filename(after, ta)
        out.append((e, after))
    return out
