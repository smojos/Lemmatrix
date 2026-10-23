# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders. Additional terms: NOTICE.md
"""Pitch notation.

    Digits are pitch points; spaces separate syllables; a comma is a pause.
    Between two adjacent points is one short step, and each colon between
    them adds a step:

        11     short level          1:1    long level        1::1   extra long
        14     quick rise           1:4    long steady rise
        4:42   long high level, then a quick fall
        42:1   quick fall, then a long fall

    5      extra short: a lone digit is a level half a short step long
           (Josh, 21 October; until then it was doubled to 55)
    Stored as typed; drawing happens in the UI.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

PAUSE = ","
EXTRA_SHORT = 0.5               # a lone digit's length, in short steps
LENGTH_MARK = "\u02d0"          # ː, typed out of habit: means the same as a colon


@dataclass
class Syllable:
    points: list[int]          # pitch levels
    steps: list[float]         # length of each step between points: 0.5 extra short, 1 short, 2 long, ...
    bad_colons: bool = False   # colons at the start or end, which mean nothing

    @property
    def length(self) -> int:
        return sum(self.steps)


_TOKEN = re.compile(r",|[^\s,]+")


def _syllable(text: str) -> Syllable | None:
    points, steps = [], []
    colons = 0
    bad = False
    for ch in text:
        if ch.isdigit():
            if points:
                steps.append(1 + colons)
            elif colons:
                bad = True
            points.append(int(ch))
            colons = 0
        elif ch == ":":
            colons += 1
    if colons:
        bad = True
    if not points:
        return None
    if len(points) == 1:                 # a lone digit is an extra-short level
        points = points * 2
        steps = [EXTRA_SHORT]
    return Syllable(points, steps, bad)


def parse(text: str) -> list:
    """A list of Syllable objects and PAUSE markers. Other characters are ignored."""
    items: list = []
    for tok in _TOKEN.findall((text or "").replace(LENGTH_MARK, ":")):
        if tok == ",":
            items.append(PAUSE)
            continue
        syl = _syllable(tok)
        if syl:
            items.append(syl)
    return items


def normalise(text: str) -> str:
    """Tidy spacing; everything else as typed (a lone digit stays one digit).
    The IPA length mark (ː) counts as a colon."""
    if not text:
        return ""
    text = text.replace(LENGTH_MARK, ":")
    out = []
    for tok in _TOKEN.findall(text):
        if tok == ",":
            if out:
                out[-1] += ","
            continue
        out.append(tok)
    return " ".join(out)


def invalid_chars(text: str) -> str:
    return "".join(sorted({c for c in text or ""
                           if not (c.isdigit() or c.isspace() or c in ",:")}))


def syllable_count(text: str) -> int:
    return sum(1 for i in parse(text) if i != PAUSE)


def out_of_range(text: str, low: int, high: int) -> list[int]:
    return sorted({d for s in parse(text) if s != PAUSE for d in s.points if d < low or d > high})


def problems(text: str, low: int, high: int) -> list[str]:
    notes = []
    bad = out_of_range(text, low, high)
    if bad:
        notes.append(f"Outside the display range {low}-{high}: {' '.join(map(str, bad))}.")
    if any(s != PAUSE and s.bad_colons for s in parse(text)):
        notes.append("A colon at the start or end of a syllable means nothing; "
                     "colons go between two digits (e.g. 4:42).")
    junk = invalid_chars(text)
    if junk:
        notes.append(f"Ignored: {junk}")
    return notes
