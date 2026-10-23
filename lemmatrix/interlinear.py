# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders. Additional terms: NOTICE.md
"""Interlinear alignment (Josh, 19 October), following the LaTeX glossing packages (gb4e,
expex): in an aligned field, spaces separate the units that line up, braces group several
words into one unit ({big dog}), and {} is an empty unit (an unglossed word). No Qt here."""

from __future__ import annotations

BLANK = "{}"


def split_units(text: str) -> list[str]:
    """The units of an aligned field, braces kept: "a {big dog} {} ran" → ["a", "{big dog}", "{}", "ran"]."""
    out, cur, depth = [], "", 0
    for ch in (text or "").strip():
        if ch == "{":
            depth += 1
        elif ch == "}" and depth:
            depth -= 1
        if ch.isspace() and depth == 0:
            if cur:
                out.append(cur)
                cur = ""
            continue
        cur += ch
    if cur:
        out.append(cur)
    return out


def bare(unit: str) -> str:
    """What a unit says: "{big dog}" → "big dog", "{}" → ""."""
    u = unit.strip()
    if len(u) >= 2 and u[0] == "{" and u[-1] == "}":
        return u[1:-1].strip()
    return u


def as_unit(label: str) -> str:
    """A segment's text as one unit: empty → {}, several words → {several words}."""
    label = (label or "").strip()
    if not label:
        return BLANK
    return "{" + label + "}" if any(c.isspace() for c in label) else label
