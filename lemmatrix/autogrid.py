# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders. Additional terms: NOTICE.md
"""A text's TextGrid from its speech (Josh, 28 October; DESIGN.md 3.11): Lemmatrix finds the
stretches of speech itself (Praat's rule: within 25 dB of the loudest part, pauses of 0.3 s or
more, on ✂ auto-snip's level measurements with hum left out), pads each by a buffer
(0.25 s), merges those the padding makes overlap, and writes a TextGrid whose tiers are cut at the
same boundaries: by default cns pht phm mph trs com (the fields' abbreviations), with *translate me*
in each segment of the Translation tier. The Translation tier is the main tier (Josh: "then future
versions of Lemmatrix with analysis capabilities won't be reading placeholder data"), so every
stretch is a line and no transcription tier holds a placeholder. No Praat needed, no Qt here.

Also archiving (Josh, 28 October): `archive_path` gives the next free name.archiveN.TextGrid
beside the TextGrid (Praat still opens it by double-click; Lemmatrix never reads it as a text's)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

BUFFER = 0.25                  # s of room either side of each stretch of speech (Josh's script)
PLACEHOLDER = "translate me"
FIELD_ROLES = ("constituents", "phonetic", "phonemic", "morphemes", "translation", "comment")
FALLBACK_NAMES = {"constituents": "cns", "phonetic": "pht", "phonemic": "phm", "morphemes": "mph",
                  "translation": "trs", "comment": "com"}
ARCHIVE = re.compile(r"\.archive(\d+)\.textgrid$", re.IGNORECASE)


@dataclass
class Tier:
    name: str                  # the tier's name in the TextGrid (the field's abbreviation)
    field: str                 # the token field it fills
    lang: str = ""             # a multilingual field's language (Translation: the analysis language)


def tiers_for(db) -> list[Tier]:
    """The tiers a new TextGrid gets: the fields' own abbreviations, in Josh's order; a field the
    database doesn't have (or a renamed abbreviation) follows the database."""
    s = db.settings
    out = []
    for role in FIELD_ROLES:
        f = s.token_field(role)
        if f is None:
            continue
        name = (getattr(f, "abbr", "") or FALLBACK_NAMES[role]).strip() or FALLBACK_NAMES[role]
        out.append(Tier(name, f.name, s.primary_gloss if f.multilingual else ""))
    return out


def main_tier(tiers: list[Tier], db) -> str:
    """The Translation tier (Josh, 28 October), else the first."""
    f = db.settings.token_field("translation")
    for t in tiers:
        if f is not None and t.field == f.name:
            return t.name
    return tiers[0].name if tiers else ""


THRESHOLD = -25.0               # dB below the loudest part: quieter is silence (Praat's default)
MIN_SILENCE = 0.3              # s: a shorter pause doesn't end a line (a breath, a closure)
MIN_SPEECH = 0.1               # s: a shorter sound isn't speech (a click, a knock)


def speech_spans(samples, rate: int, buffer: float = BUFFER, threshold: float = THRESHOLD,
                 min_silence: float = MIN_SILENCE, min_speech: float = MIN_SPEECH) -> list[tuple[float, float]]:
    """The stretches of speech in seconds, each padded by the buffer and merged where they overlap.
    Praat's own rule for To TextGrid (silences), on auto-snip's levels (snip._levels: hum left
    out): sound within `threshold` dB of the loudest part, pauses shorter than `min_silence`
    bridged, sounds shorter than `min_speech` dropped. (Auto-snip's own detector keeps quiet
    edges for trimming and so joins sentences across breaths: 5 stretches for the sample's 10.)"""
    from . import snip
    x = snip._mono(samples)
    if not rate or len(x) < rate * snip.FRAME:
        return []
    hop, overall, _hiss = snip._levels(x, rate)
    if len(overall) == 0:
        return []
    step = hop / float(rate)
    dur = len(x) / float(rate)
    loud = overall > overall.max() + threshold
    runs: list[list[int]] = []
    for a, b in snip._runs(loud):
        if runs and (a - runs[-1][1]) * step < min_silence:
            runs[-1][1] = b
        else:
            runs.append([a, b])
    spans: list[list[float]] = []
    for a, b in runs:
        if (b - a) * step < min_speech:
            continue
        s, e = max(0.0, a * step - buffer), min(dur, b * step + buffer)
        if spans and s <= spans[-1][1]:
            spans[-1][1] = max(spans[-1][1], e)
        else:
            spans.append([s, e])
    return [(round(s, 4), round(e, 4)) for s, e in spans if e > s]


def write(path, spans, duration: float, tiers: list[Tier], placeholder_tier: str,
          placeholder: str = PLACEHOLDER):
    """A TextGrid with every tier cut at the spans; the placeholder in the placeholder tier's."""
    from praatio import textgrid
    tg = textgrid.Textgrid()
    for t in tiers:
        entries = [(s, e, placeholder if t.name == placeholder_tier else "") for s, e in spans]
        tg.addTier(textgrid.IntervalTier(t.name, entries, 0, duration))
    tg.save(str(path), format="long_textgrid", includeBlankSpaces=True)


def from_recording(wav, out, db, buffer: float = BUFFER) -> int:
    """Write `out` from the speech in `wav`; the number of segments. Raises OSError, AudioError."""
    from . import audio
    samples, rate = audio.read_wav(wav)
    duration = len(samples) / float(rate)
    spans = speech_spans(samples, rate, buffer)
    tiers = tiers_for(db)
    write(out, spans, duration, tiers, main_tier(tiers, db))
    return len(spans)


def blank_like(src, out):
    """A TextGrid with the same tiers and length as `src`, and no segments."""
    from praatio import textgrid
    from .textgrid import _grid
    old = _grid(src)
    tg = textgrid.Textgrid()
    for name in old.tierNames:
        tier = old.getTier(name)
        if type(tier).__name__ == "IntervalTier":
            tg.addTier(textgrid.IntervalTier(name, [], old.minTimestamp, old.maxTimestamp))
        else:
            tg.addTier(textgrid.PointTier(name, [], old.minTimestamp, old.maxTimestamp))
    tg.save(str(out), format="long_textgrid", includeBlankSpaces=True)


def archive_path(grid: Path) -> Path:
    """The next free name.archiveN.TextGrid beside the TextGrid (N from 1)."""
    grid = Path(grid)
    stem = grid.name[: -len(grid.suffix)] if grid.suffix else grid.name
    used = {int(m.group(1)) for p in grid.parent.glob(f"{glob_escape(stem)}.archive*.*")
            if (m := ARCHIVE.search(p.name))}
    n = 1
    while n in used:
        n += 1
    return grid.with_name(f"{stem}.archive{n}{grid.suffix or '.TextGrid'}")


def is_archive(path) -> bool:
    return bool(ARCHIVE.search(Path(path).name))


def glob_escape(s: str) -> str:
    return re.sub(r"([*?\[])", r"[\1]", s)
