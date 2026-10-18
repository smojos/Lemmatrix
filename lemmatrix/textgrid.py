"""A text's lines, read from its Praat TextGrid (idea 7, stage 3). No Qt here.

The lines stay in the TextGrid: Lemmatrix reads them when it needs them and never writes the
file. A tier mapping says which tiers fill which fields; the main tier's intervals are the
lines, and the other tiers are matched to them by overlapping times. A tier named "tx@SP1"
belongs to the speaker SP1: its line is matched only with SP1's other tiers. TextGrids are read
with praatio (MIT licence), which handles Praat's long and short formats and their encodings.
"""

from __future__ import annotations

import datetime as _dt
import os
from dataclasses import dataclass, field
from pathlib import Path

from .model import TierMapping, nfc, tier_base


class TextGridError(Exception):
    pass


@dataclass
class TierInfo:
    name: str
    kind: str          # "intervals" or "points"
    count: int         # intervals (or points) with text


@dataclass
class Line:
    start: float
    end: float
    speaker: str = ""
    values: dict[str, str] = field(default_factory=dict)   # field key (Phonetic, Translation:en) -> text
    copied: dict[str, str] = field(default_factory=dict)   # tier name -> its text in this line
    index: int = 0

    @property
    def id(self):                       # for the grid
        return (round(self.start, 4), round(self.end, 4), self.speaker)

    def overlaps(self, start: float, end: float) -> bool:
        return min(self.end, end) - max(self.start, start) > 1e-6


def _open(path):
    try:
        from praatio import textgrid
    except ImportError as exc:                          # pragma: no cover
        raise TextGridError("Reading TextGrids needs the praatio package (installed with the next "
                            "start of Lemmatrix).") from exc
    try:
        return textgrid.openTextgrid(str(path), includeEmptyIntervals=False, reportingMode="silence",
                                     duplicateNamesMode="rename")
    except Exception as exc:                            # praatio raises several kinds
        raise TextGridError(f"Couldn't read {Path(path).name}: {exc}") from exc


def modified(path) -> str:
    """When the TextGrid was last changed (ISO, to the second): stored with clipped utterances."""
    try:
        return _dt.datetime.fromtimestamp(os.path.getmtime(path)).isoformat(timespec="seconds")
    except OSError:
        return ""


_cache: dict = {}


def _grid(path):
    """The parsed TextGrid, read again only when the file has changed."""
    p = Path(path)
    try:
        stamp = p.stat().st_mtime_ns
    except OSError as exc:
        raise TextGridError(f"{p.name} isn't there.") from exc
    key = str(p.resolve())
    hit = _cache.get(key)
    if hit and hit[0] == stamp:
        return hit[1]
    tg = _open(p)
    _cache[key] = (stamp, tg)
    return tg


def tiers(path) -> list[TierInfo]:
    tg = _grid(path)
    out = []
    for name in tg.tierNames:
        tier = tg.getTier(name)
        kind = "intervals" if type(tier).__name__ == "IntervalTier" else "points"
        out.append(TierInfo(nfc(name), kind, sum(1 for e in tier.entries if (e[-1] or "").strip())))
    return out


def read_lines(path, mapping: TierMapping, default_speaker: str = "") -> list[Line]:
    """The text's lines: one per interval (with text) of the main tier, in time order, with the
    other mapped tiers' text that overlaps it. Raises TextGridError."""
    tg = _grid(path)
    names = [nfc(n) for n in tg.tierNames]
    interval = {n: tg.getTier(raw) for n, raw in zip(names, tg.tierNames)
                if type(tg.getTier(raw)).__name__ == "IntervalTier"}
    mains = [n for n in interval if mapping.is_main(n)]
    if not mains:
        raise TextGridError(f"No tier called “{mapping.main}” (the main tier) in {Path(path).name}. "
                            f"Its tiers are: {', '.join(names) or 'none'}.")
    lines: list[Line] = []
    for main in mains:
        _, speaker = tier_base(main)
        main_rule = mapping.rule(main)
        others = []
        for n, tier in interval.items():
            if n == main or mapping.is_main(n):
                continue
            rule = mapping.rule(n)
            if rule is None or not rule.field:
                continue
            if tier_base(n)[1] not in ("", speaker) and speaker:
                continue                                # another speaker's tier
            if not speaker and tier_base(n)[1]:
                continue
            others.append((n, rule, tier))
        for start, end, label in interval[main].entries:
            text = nfc((label or "").strip())
            if not text:
                continue
            ln = Line(float(start), float(end), speaker or default_speaker)
            ln.copied[main] = text
            if main_rule is not None and main_rule.field:
                ln.values[main_rule.key] = text
            for n, rule, tier in others:
                parts = [nfc((lab or "").strip()) for s, e, lab in tier.entries
                         if (lab or "").strip() and ln.overlaps(float(s), float(e))]
                if parts:
                    joined = " ".join(parts)
                    ln.copied[n] = joined
                    key = rule.key
                    ln.values[key] = (ln.values[key] + " " + joined) if ln.values.get(key) else joined
            lines.append(ln)
    lines.sort(key=lambda x: (x.start, x.speaker))
    for i, ln in enumerate(lines):
        ln.index = i
    return lines


def write_example(path, tiers_: dict[str, list[tuple[float, float, str]]], end: float):
    """Write a TextGrid (for tests and the sample data)."""
    from praatio import textgrid
    tg = textgrid.Textgrid()
    for name, entries in tiers_.items():
        tg.addTier(textgrid.IntervalTier(name, entries, 0, end))
    tg.save(str(path), format="long_textgrid", includeBlankSpaces=True)
