"""Editing a text's lines in Lemmatrix (agreed with Josh, 19 October). No Qt here.

The TextGrid is the only store of a text's lines: Lemmatrix is a layer over it that can't move
a boundary. A text being edited is read once into a Buffer (empty segments included); edits
change the Buffer, with undo, and the Buffer is written back when the database is saved (a copy
of the TextGrid goes to Backups first). If Praat saved the file meanwhile, saving asks first.

Setting a field on a line writes into the tier the mapping gives that field (the line's
speaker's). A word-level tier (several segments in the line) keeps its segments when the
field has one unit per segment (units as in interlinear.py: spaces, {braces}, {} for an empty
one); otherwise the segments are merged into one, which the interface warns about first. A
field with no tier yet gets one. Empty segments reaching past the line are split at its edge,
never merged in, so no boundary ever moves outside the line.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from . import textgrid as tgmod
from .interlinear import bare, split_units
from .model import SPEAKER_FIELD, Database, Text, TierRule, nfc, tier_base

SAME = tgmod.SAME_TIME


class LineEditError(Exception):
    pass


def _stamp(path) -> int | None:
    try:
        return os.stat(path).st_mtime_ns
    except OSError:
        return None


@dataclass
class TierEdit:
    tier: str                    # the tier's name in the TextGrid
    old: list | None             # its segments before (None: the tier is new)
    new: list                    # its segments after
    merged: int = 0              # how many segments were merged into one (0: none)
    created: bool = False


class Buffer:
    """A text's TextGrid, read into memory to be edited."""

    def __init__(self, path):
        self.path = Path(path)
        self.tg = tgmod.read_grid(self.path)
        self.stamp = _stamp(self.path)
        self.changed = False                  # edits not yet written
        self.generation = 0                   # goes up when the file is read again

    def reload(self):
        self.tg = tgmod.read_grid(self.path)
        self.stamp = _stamp(self.path)
        self.changed = False
        self.generation += 1

    def disk_changed(self) -> bool:
        """Saved by something else (Praat) since it was read or written here."""
        return _stamp(self.path) != self.stamp

    def lines(self, db: Database, text: Text) -> list:
        speaker = text.participants[0] if len(text.participants) == 1 else ""
        return tgmod.lines_from(self.tg, db.mapping_for(text), speaker)

    def raw_names(self) -> dict[str, str]:
        return {nfc(n): n for n in self.tg.tierNames}

    def apply(self, edits: list[TierEdit], undo: bool = False):
        from praatio import textgrid
        for e in (reversed(edits) if undo else edits):
            entries = e.old if undo else e.new
            if entries is None:               # undoing a new tier: it goes again
                if e.tier in self.tg.tierNames:
                    self.tg.removeTier(e.tier)
                continue
            if e.tier in self.tg.tierNames:
                self.tg.replaceTier(e.tier, self.tg.getTier(e.tier).new(entries=list(entries)))
            else:
                self.tg.addTier(textgrid.IntervalTier(e.tier, list(entries), self.tg.minTimestamp,
                                                      self.tg.maxTimestamp))
        self.changed = True

    def write(self, db: Database):
        """Back up the file on disk, then write the edits into it."""
        from .pull import backup_textgrid
        if self.path.exists():
            backup_textgrid(db, self.path)
        tmp = self.path.with_name(self.path.name + ".lemmatrix-writing")
        self.tg.save(str(tmp), format="long_textgrid", includeBlankSpaces=True)
        os.replace(tmp, self.path)
        self.stamp = _stamp(self.path)
        self.changed = False


# ---- planning an edit ------------------------------------------------------------------------

def _interval(a, b, label):
    from praatio.utilities.constants import Interval
    return Interval(a, b, label)


def _core(entries, idx: list[int], start: float, end: float) -> list[int]:
    """The line's own segments: without empty ones at either end that reach past the line."""
    core = list(idx)
    while core and not (entries[core[0]][2] or "").strip() and entries[core[0]][0] < start - SAME:
        core.pop(0)
    while core and not (entries[core[-1]][2] or "").strip() and entries[core[-1]][1] > end + SAME:
        core.pop()
    return core


def _merge(entries, first: int, last: int, start: float, end: float, label: str) -> list:
    """entries[first..last] become one segment with the label; an empty segment at either end
    that reaches past the line is split at the line's edge instead of being swallowed."""
    a, b = entries[first][0], entries[last][1]
    out = []
    if a < start - SAME and not (entries[first][2] or "").strip():
        out.append(_interval(a, start, ""))
        a = start
    tail = []
    if b > end + SAME and not (entries[last][2] or "").strip():
        tail.append(_interval(end, b, ""))
        b = end
    return entries[:first] + out + [_interval(a, b, label)] + tail + entries[last + 1:]


def target_tier(buf: Buffer, db: Database, text: Text, line, key: str) -> str | None:
    """The TextGrid tier (its name there) that a field fills for this line, or None."""
    mapping = db.mapping_for(text)
    speakers = {tier_base(t)[1] for t in line.copied} or {""}
    for raw in buf.tg.tierNames:
        name = nfc(raw)
        if type(buf.tg.getTier(raw)).__name__ != "IntervalTier":
            continue
        rule = mapping.rule(name)
        if rule is None or not rule.field or rule.field == SPEAKER_FIELD or rule.key != key:
            continue
        if tier_base(name)[1] in speakers:
            return raw
    return None


def plan_edit(buf: Buffer, db: Database, text: Text, line, key: str, value: str) -> list[TierEdit]:
    """What setting this field of the line to value would change. Raises LineEditError."""
    value = nfc((value or "").strip())
    mapping = db.mapping_for(text)
    main_rule = mapping.rule(next(iter(line.copied), "")) if line.copied else None
    if main_rule is not None and main_rule.key == key and not value:
        raise LineEditError("The main tier's text can't be empty: it is what makes the line. "
                            "Put a placeholder in it instead.")
    raw = target_tier(buf, db, text, line, key)
    start, end = line.start, line.end
    if raw is None:                            # no tier for this field yet: a new one
        if not value:
            return []
        field, _, lang = key.partition(":")
        base = next((r.tier for r in mapping.rules if r.key == key), field)
        speaker = next((tier_base(t)[1] for t in line.copied if tier_base(t)[1]), "")
        name = f"{base}@{speaker}" if speaker else base
        if name in buf.tg.tierNames:
            raise LineEditError(f"There is already a tier called “{name}” that isn't mapped to this field.")
        if mapping.rule(name) is None:
            mapping.rules.append(TierRule(base, field, lang))
        return [TierEdit(name, None, [_interval(start, end, value)], created=True)]
    entries = list(buf.tg.getTier(raw).entries)
    idx = tgmod.segments_in(entries, start, end)
    if not idx:                                # a gap in the tier: a segment for the line
        if not value:
            return []
        new = sorted(entries + [_interval(start, end, value)], key=lambda e: e[0])
        return [TierEdit(raw, entries, new)]
    core = _core(entries, idx, start, end)
    units = split_units(value)
    new, merged = list(entries), 0
    if len(core) > 1 and not value:            # emptied: every segment empty, none merged
        for i in core:
            new[i] = _interval(entries[i][0], entries[i][1], "")
    elif len(core) > 1 and len(units) == len(core):
        for i, u in zip(core, units):          # one unit per segment: the boundaries stay
            new[i] = _interval(entries[i][0], entries[i][1], bare(u))
    elif len(core) == 1 and core == idx:
        i = core[0]
        new[i] = _interval(entries[i][0], entries[i][1], value)
    elif len(core) > 1:                        # units ≠ segments: the line's segments become one
        merged = len(core)
        new = _merge(entries, core[0], core[-1], start, end, value)
    elif len(core) == 1:                       # its one segment, with empties past the line beside it
        i = core[0]
        new[i] = _interval(entries[i][0], entries[i][1], value)
    else:                                      # only empty segments reaching past the line
        if not value:
            return []
        new = _merge(entries, idx[0], idx[-1], start, end, value)
    if new == entries:
        return []
    return [TierEdit(raw, entries, new, merged)]


def would_merge(edits: list[TierEdit]) -> list[tuple[str, int]]:
    """(tier, segments) for each tier an edit merges: the interface asks first."""
    return [(e.tier, e.merged) for e in edits if e.merged > 1]


def follow_clips(db: Database, text: Text, before: list, after: list, line, key: str,
                 edits: list[TierEdit]) -> list[tuple]:
    """The utterances clipped from this line, updated with the edit (Josh: one analysis, not
    several): (utterance, its copy with the line's new value and link). Unlinked ones don't follow."""
    from .pull import find_line
    new = next((ln for ln in after if ln.id == line.id), None)
    if new is None:
        return []
    out = []
    field, _, lang = key.partition(":")
    fd = db.settings.token_field(field)
    for u in db.clipped_from(text):
        old = find_line(before, u.source)
        if old is None or old.id != line.id:
            continue
        a = u.copy()
        if fd is not None:
            a.token.set(field, new.values.get(key, ""), (lang or db.settings.primary_gloss) if fd.multilingual
                        else None, fd.multilingual)
        for e in edits:
            name = nfc(e.tier)
            if new.copied.get(name):
                a.source.copied[name] = new.copied[name]
            else:
                a.source.copied.pop(name, None)
        out.append((u, a))
    return out
