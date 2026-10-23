# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders. Additional terms: NOTICE.md
"""Pull and Push (idea 7, stage 4): a clipped utterance and its line in the TextGrid. No Qt here.

A clipped utterance keeps what it copied from each tier of its line, the line's times and when
the TextGrid was last changed (model.ClipSource). Checking reads the TextGrid again (only when it
has been saved since), finds the line again and compares it with what was copied, never with
the utterance as it is now, so edits made in Lemmatrix don't count as changes in Praat.

A tier no longer in the TextGrid at all (renamed, say) isn't a change; an emptied interval is.

Finding the line again: the line with the same times, or else the one that overlaps it most,
among the lines of the same tiers (the same speaker). Pulling replaces only the fields filled
from the tiers that changed, and remembers the line as it is now.

Push goes the other way (agreed with Josh, 18 October): a field edited in Lemmatrix (it differs
from what was copied) is written into its tier at the line. Where the line spans several
segments of that tier (a word-level tier), they are merged into one, with a warning. Lemmatrix
copies the TextGrid into Backups first, since undo can't reach it; Praat keeps its own copy of an
open TextGrid, so the dialogue says to close it there first.
"""

from __future__ import annotations

import datetime as _dt
import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from . import storage, textgrid as tgmod
from .model import SPEAKER_FIELD, ClipSource, Database, Text, Utterance, tier_base

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
    edited: list[str] = field(default_factory=list)   # tiers whose field was edited in Lemmatrix

    @property
    def pushable(self) -> bool:
        """Something to write into the TextGrid: a field edited here, or (when the line changed
        in Praat) a field that differs from it, for the user to choose the direction."""
        return self.status in (OK, CHANGED, MOVED) and bool(self.edited or self.changes)

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


def check(db: Database, u: Utterance, buffers: dict | None = None) -> Check | None:
    """The state of a clipped utterance's line (None for an utterance not clipped from a text).
    buffers: text id -> lines.Buffer, so unsaved line edits made in Lemmatrix are seen."""
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
    buf = (buffers or {}).get(t.id)
    if buf is not None and not buf.changed:
        buf = None                              # nothing unsaved: the file says the same
    try:
        infos = tgmod.tiers_of(buf.tg) if buf is not None else tgmod.tiers(path)
        tier_names = [ti.name for ti in infos if ti.kind == "intervals"]
    except (tgmod.TextGridError, OSError) as exc:
        return Check(u, NO_TEXTGRID, t, message=str(exc))
    edited = edited_tiers(db, u, t, tier_names)
    if buf is None and src.modified and tgmod.modified(path) == src.modified:
        return Check(u, OK, t, edited=edited)   # not saved since it was clipped
    try:
        lines = buf.lines(db, t) if buf is not None else _lines(db, t, path)
    except (tgmod.TextGridError, OSError) as exc:
        return Check(u, NO_TEXTGRID, t, message=str(exc))
    ln = find_line(lines, src)
    if ln is None:
        return Check(u, NOT_FOUND, t, message=f"The line isn't in {t.ref}'s TextGrid any more.")
    mapping = db.mapping_for(t)
    present = set(tier_names)
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
    return Check(u, status, t, ln, changes, moved, edited=edited)


def _same(a: str, b: str) -> bool:
    return " ".join((a or "").split()) == " ".join((b or "").split())


def target_tiers(db: Database, t: Text, src: ClipSource, tier_names) -> list[tuple[str, str]]:
    """(tier, field key) for each field the line's tiers fill: the TextGrid's interval tiers
    of the line's speaker that the mapping gives a field (the first such tier for each field)."""
    mapping = db.mapping_for(t)
    speakers = {tier_base(x)[1] for x in src.copied} or {""}
    out, keys = [], set()
    for name in tier_names:
        rule = mapping.rule(name)
        if rule is None or not rule.field or rule.field == SPEAKER_FIELD or tier_base(name)[1] not in speakers \
                or rule.key in keys:
            continue
        keys.add(rule.key)
        out.append((name, rule.key))
    return out


def edited_tiers(db: Database, u: Utterance, t: Text, tier_names) -> list[str]:
    """The tiers whose field has been edited in Lemmatrix since it was copied (or pulled)."""
    src = u.source
    return [tier for tier, key in target_tiers(db, t, src, tier_names)
            if not _same(field_value(db, u, key), src.copied.get(tier, ""))]


def describe_edits(c: Check) -> str:
    return f"Edited in Lemmatrix ({', '.join(c.edited)}): Push to source… writes it into the TextGrid."


def check_all(db: Database, buffers: dict | None = None) -> dict[str, Check]:
    """utterance id -> its check, for every clipped utterance."""
    out = {}
    for u in db.utterances:
        c = check(db, u, buffers)
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


# ---- Push --------------------------------------------------------------------------------

@dataclass
class PushChange:
    utterance: Utterance
    tier: str
    key: str
    old: str                   # the tier's text in the line now
    new: str                   # the utterance's field
    segments: int              # how many segments of the tier the line spans (merged if > 1)
    edited: bool = True        # edited here; False: changed only in Praat (offered, not ticked)

    @property
    def merges(self) -> bool:
        return self.segments > 1


def _read_full(path):
    from praatio import textgrid
    try:
        return textgrid.openTextgrid(str(path), includeEmptyIntervals=True, reportingMode="silence",
                                     duplicateNamesMode="rename")
    except Exception as exc:
        raise tgmod.TextGridError(f"Couldn't read {Path(path).name}: {exc}") from exc


def _span(c: Check) -> tuple[float, float]:
    """The line's times as it is now (the stored ones if the TextGrid wasn't read)."""
    if c.line is not None:
        return c.line.start, c.line.end
    return c.utterance.source.start, c.utterance.source.end


def _exact_span(db: Database, c: Check) -> tuple[float, float]:
    """The line's exact times, from the TextGrid: the stored ones are rounded (to 0.1 ms), and
    a rounded start can reach a sliver into the segment before the line (Josh, 19 October: a
    push merged the empty segments either side into the line)."""
    if c.line is not None:
        return c.line.start, c.line.end
    path = storage.text_folder(db) / c.text.textgrid
    ln = find_line(_lines(db, c.text, path), c.utterance.source)
    return (ln.start, ln.end) if ln is not None else _span(c)


def _overlapping(entries, start: float, end: float) -> list[int]:
    """The segments that are part of the line: more than a sliver (SAME_TIME) inside it."""
    return [i for i, e in enumerate(entries) if min(e[1], end) - max(e[0], start) > SAME_TIME]


def _replacement(entries, hits, start: float, end: float, label: str):
    """The segments that replace entries[hits]: one segment with the label, never reaching past
    the line where the segment at its edge is empty (that one is split at the line's edge)."""
    from praatio.utilities.constants import Interval
    first, last = entries[hits[0]], entries[hits[-1]]
    out = []
    a, b = first[0], last[1]
    if a < start - SAME_TIME and not (first[2] or "").strip():
        out.append(Interval(a, start, ""))
        a = start
    tail = []
    if b > end + SAME_TIME and not (last[2] or "").strip():
        tail.append(Interval(end, b, ""))
        b = end
    return out + [Interval(a, b, label)] + tail


def push_plan(db: Database, c: Check) -> list[PushChange]:
    """What pushing this utterance would write: each edited tier, its text now and the
    utterance's, and how many segments of the tier the line spans."""
    if not c.pushable:
        return []
    path = storage.text_folder(db) / c.text.textgrid
    tg = _read_full(path)
    names = {tgmod.nfc(n): n for n in tg.tierNames}
    start, end = _exact_span(db, c)
    differing = set(c.edited) | {ch.tier for ch in c.changes}
    out = []
    for tier, key in target_tiers(db, c.text, c.utterance.source, list(names)):
        if tier not in differing:
            continue
        entries = tg.getTier(names[tier]).entries
        hits = _overlapping(entries, start, end)
        now = " ".join(tgmod.nfc((entries[i][2] or "").strip()) for i in hits if (entries[i][2] or "").strip())
        new = field_value(db, c.utterance, key)
        if not _same(now, new):
            words = [i for i in hits if (entries[i][2] or "").strip()] if len(hits) > 1 else hits
            out.append(PushChange(c.utterance, tier, key, now, new, len(hits) if len(words) > 1 else 1,
                                  tier in c.edited))
    return out


def backup_textgrid(db: Database, path: Path) -> Path:
    """A dated copy of the TextGrid in Backups, before Lemmatrix writes to it."""
    from . import layout
    folder = layout.backups_folder(db.path)
    folder.mkdir(parents=True, exist_ok=True)
    stamp = _dt.datetime.now().strftime("%Y-%m-%d_%H%M%S")
    target, n = folder / f"{path.stem}_{stamp}{path.suffix}", 2
    while target.exists():
        target, n = folder / f"{path.stem}_{stamp}_{n}{path.suffix}", n + 1
    shutil.copy2(path, target)
    return target


def push(db: Database, text: Text, jobs: list[tuple[Check, list[PushChange]]]) -> dict[str, Utterance]:
    """Write the chosen changes for one text into its TextGrid (one write, after a backup).
    Returns utterance id -> a copy of the utterance with its link updated. Raises
    TextGridError or OSError (nothing is written then)."""
    path = storage.text_folder(db) / text.textgrid
    spans = {id(c): _exact_span(db, c) for c, _ in jobs}     # before anything is written
    tg = _read_full(path)
    names = {tgmod.nfc(n): n for n in tg.tierNames}
    for c, changes in jobs:
        start, end = spans[id(c)]
        for ch in changes:
            raw = names.get(ch.tier)
            if raw is None:
                raise tgmod.TextGridError(f"There is no tier “{ch.tier}” in {path.name} any more.")
            tier = tg.getTier(raw)
            entries = list(tier.entries)
            hits = _overlapping(entries, start, end)
            if not hits:
                raise tgmod.TextGridError(f"{ch.tier} has no segment at {start:.2f}–{end:.2f} s.")
            first, last = hits[0], hits[-1]
            entries[first:last + 1] = _replacement(entries, hits, start, end, ch.new)
            tg.replaceTier(raw, tier.new(entries=entries))
    backup_textgrid(db, path)
    tmp = path.with_name(path.name + ".lemmatrix-writing")
    tg.save(str(tmp), format="long_textgrid", includeBlankSpaces=True)
    os.replace(tmp, path)
    stamp = tgmod.modified(path)
    out = {}
    for c, changes in jobs:
        u = c.utterance.copy()
        src = u.source
        for ch in changes:
            src.copied[ch.tier] = ch.new
        if c.status == OK:                      # nothing else changed in Praat: up to date now
            src.modified = stamp
        out[u.id] = u
    return out
