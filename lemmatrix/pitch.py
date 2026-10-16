"""Pitch notation: digits 0-9, spaces between syllables, commas for pauses.

    "13 3 31, 5"  ->  rise, level, fall, pause, level
    "22"          ->  one long level syllable

Stored as typed; drawing happens in the UI.
"""

from __future__ import annotations

PAUSE = ","

# Dekereke's one-character-per-syllable contour letters (used when converting).
DEKEREKE_LETTERS = dict(item.split("=")[::-1] for item in (
    "12=A 13=I 14=P 21=a 23=B 24=J 25=Q 31=i 32=b 34=C 35=K 36=R 41=p 42=j "
    "43=c 45=D 46=L 52=q 53=k 54=d 56=E 63=r 64=l 65=e").split())


def parse(text: str) -> list:
    """Return a list of syllables (lists of ints) and PAUSE markers.

    Characters other than digits, spaces and commas are ignored.
    """
    items: list = []
    current: list[int] = []

    def flush():
        nonlocal current
        if current:
            items.append(current)
            current = []

    for ch in text or "":
        if ch.isdigit():
            current.append(int(ch))
        elif ch == ",":
            flush()
            items.append(PAUSE)
        elif ch.isspace():
            flush()
    flush()
    return items


def invalid_chars(text: str) -> str:
    return "".join(sorted({c for c in text or "" if not (c.isdigit() or c.isspace() or c == ",")}))


def syllable_count(text: str) -> int:
    return sum(1 for i in parse(text) if i != PAUSE)


def out_of_range(text: str, low: int, high: int) -> list[int]:
    return sorted({d for s in parse(text) if s != PAUSE for d in s if d < low or d > high})


def from_dekereke(text: str) -> str:
    """Convert Dekereke's pitch letters (one character per syllable) to digits."""
    out = []
    for ch in text or "":
        if ch in DEKEREKE_LETTERS:
            out.append(DEKEREKE_LETTERS[ch])
        elif ch.isdigit():
            out.append(ch)
        elif ch == ",":
            out.append(",")
    return " ".join(out).replace(" ,", ",")
