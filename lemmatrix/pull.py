"""Pull (idea 7, stage 4): has a clipped utterance's line changed in its TextGrid? No Qt here.

A clipped utterance keeps what it copied from each tier of its line, the line's times and when
the TextGrid was last changed (model.ClipSource). Checking reads the TextGrid again (only when it
has been saved since), finds the line again and compares it with what was copied, never with
the utterance as it is now, so edits made in Lemmatrix don't count as changes in Praat.

A tier no longer in the TextGrid at all (renamed, say) isn't a change; an emptied interval is.

Finding the line again: the line with the same times, or else the one that overlaps it most,
among the lines of the same tiers (the same speaker). Pulling replaces only the fields filled
from the tiers that changed, and remembers the line as it is now.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from . import storage, textgrid as tgmod
from .model import ClipSource, Database, Text, Utterance

OK = "ok"
CHANGED = "changed"            # the text of a tier is different
MOVED = "moved"                # the same text, but the line's start or end moved
NOT_FOUND = "not found"        # no line there any more
NO_TEXTGRID = "no textgrid"    # the text's TextGrid isn't in Soundfiles/Texts (or can't be read)
NO_TEXT = "no text"            # the text was deleted: not a problem, so not flagged

SAME_TIME = 0.0005             # seconds: times closer than this are the same


@dataclass
class Change:
    key: str                   # the field it fills: "Phonetic", "Translation:en"
    tier: str
    old: str                   # as copied
    new: str                   # in the TextGrid now


@dataclass
class Check:
    utterance: Utterance
    status: str
    text: Text | None = None
    line: tgmod.Line | None = None          # the line as it is now
    changes: list[Change] = field(default_factory=list)
    moved: bool = False
    message: str = ""

    @property
    def flagged(self) -> bool:
        return self.status not in (OK, NO_TEXT)

    @property
    def pullable(self) -> bool:
        return self.status in (CHANGED, MOVED) and self.line is not None


_lines_cache: dict = {}


def _lines(db: Database, text: Text, path) -> list:
    """The text's lines, read again only when the TextGrid or its mapping changed."""
    mapping = db.mapping_for(text)
    speaker = text.participants[0] if len(text.participants) == 1 else ""
    key = (os.path.normcase(str(path)), os.stat(path).st_mtime_ns, repr(mapping), speaker)
    hit = _lines_cache.get(key[0])
    if hit and hit[0] == key:
        return hit[1]
    lines = tgmod.read_lines(path, mapping, speaker)
    _lines_cache[key[0]] = (key, lines)
    return lines


def find_line(lines, src: ClipSource):
    """The line the utterance was clipped from, as it is now (None if it isn't there)."""
    tiers = set(src.copied)
    same_tiers = [ln for ln in lines if tiers & set(ln.copied)] or list(lines)
    for ln in same_tiers:
        if abs(ln.start - src.start) < SAME_TIME and abs(ln.end - src.end) < SAME_TIME:
            return ln
    best, overlap = None, 0.0
    for ln in same_tiers:
        o = min(ln.end, src.end) - max(ln.start, src.start)
        if o > overlap + 1e-9:
            best, overlap = ln, o
    return best


def check(db: Database, u: Utterance) -> Check | None:
    """The state of a clipped utterance's line (None for an utterance not clipped from a text)."""
    src = u.source
    if src is None:
        return None
    t = db.text_by_id(src.text)
    if t is None:
        return Check(u, NO_TEXT, message="The text it was clipped from has been deleted.")
    if not t.textgrid:
        return Check(u, NO_TEXTGRID, t, message=f"{t.ref} has no TextGrid.")
    path = storage.text_folder(db) / t.textgrid
    if not path.exists():
        return Check(u, NO_TEXTGRID, t, message=f"{t.textgrid} isn't in Soundfiles\\Texts.")
    if src.modified and tgmod.modified(path) == src.modified:
        return Check(u, OK, t)                  # not saved since it was clipped
    try:
        lines = _lines(db, t, path)
    except (tgmod.TextGridError, OSError) as exc:
        return Check(u, NO_TEXTGRID, t, message=str(exc))
    ln = find_line(lines, src)
    if ln is None:
        return Check(u, NOT_FOUND, t, message=f"The line isn't in {t.ref}'s TextGrid any more.")
    mapping = db.mapping_for(t)
    present = {ti.name for ti in tgmod.tiers(path)}
    changes = []
    for tier in [*src.copied, *(x for x in ln.copied if x not in src.copied)]:
        if tier not in present:
            continue                            # a tier gone altogether (renamed?) changes nothing
        old, new = src.copied.get(tier, ""), ln.copied.get(tier, "")
        if old != new:
            rule = mapping.rule(tier)
            changes.append(Change(rule.key if rule is not None and rule.field else "", tier, old, new))
    moved = abs(ln.start - src.start) >= SAME_TIME or abs(ln.end - src.end) >= SAME_TIME
    status = CHANGED if changes else MOVED if moved else OK
    return Check(u, status, t, ln, changes, moved)


def check_all(db: Database) -> dict[str, Check]:
    """utterance id -> its check, for every clipped utterance."""
    out = {}
    for u in db.utterances:
        c = check(db, u)
        if c is not None:
            out[u.id] = c
    return out


def describe(c: Check) -> str:
    """One line for a tooltip or a list."""
    if c.status == OK:
        return "The same as its line in the TextGrid."
    if c.status == CHANGED:
        tiers = ", ".join(ch.tier for ch in c.changes)
        return f"Changed in the TextGrid ({tiers})" + (", and the line's times moved." if c.moved else ".")
    if c.status == MOVED:
        return "The line's start or end moved in the TextGrid (the text is the same)."
    return c.message


def field_value(db: Database, u: Utterance, key: str) -> str:
    name, _, lang = key.partition(":")
    f = db.settings.token_field(name)
    if f is None:
        return ""
    return u.token.get(name, (lang or db.settings.primary_gloss) if f.multilingual else None)


def pulled(db: Database, c: Check) -> Utterance:
    """A copy of the utterance with its line as it is now: the fields filled from the tiers that
    changed, and the line remembered (times, what was copied, the TextGrid's time)."""
    u = c.utterance.copy()
    s = db.settings
    ln = c.line
    for key in dict.fromkeys(ch.key for ch in c.changes if ch.key):
        name, _, lang = key.partition(":")
        f = s.token_field(name)
        if f is not None:
            u.token.set(name, ln.values.get(key, ""), (lang or s.primary_gloss) if f.multilingual else None,
                        f.multilingual)
    path = storage.text_folder(db) / c.text.textgrid
    u.source = ClipSource(c.text.id, ln.start, ln.end, dict(ln.copied), tgmod.modified(path))
    return u


def unlinked(c: Check) -> Utterance:
    """A copy of the utterance with no source (it keeps its fields and recording)."""
    u = c.utterance.copy()
    u.source = None
    return u
