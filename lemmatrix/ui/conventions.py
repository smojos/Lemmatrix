# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders
"""Display conventions in the cell views (IDEAS.md idea 26, 21 October 2026).

How the matrix cells, a text's lines and the utterance cell show their fields: Phonetic in
[square brackets], Phonemic in /slashes/, glosses in capitals (the Morphemes line) in small
caps, translations in ‘single’ or “double” quotes or none. They are set in Settings → Display
(this computer: they are how things look, not data), and the /[β]/ button under every cell view
turns them all on or off at once. Display only: the stored text, the search, Bulk edit and the
exports never see them.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from PySide6.QtGui import QFont, QFontMetrics

SINGLE, DOUBLE, NO_QUOTES = "single", "double", "none"
QUOTES = {SINGLE: ("‘", "’"), DOUBLE: ("“", "”"), NO_QUOTES: ("", "")}
DECORATIONS = "[]/‘’“”"                       # what a convention may add at the ends of a field


@dataclass
class Conventions:
    on: bool = True               # the /[β]/ button: all of them on or off
    brackets: bool = True         # Phonetic in [square brackets]
    slashes: bool = True          # Phonemic in /slashes/
    small_caps: bool = True       # glosses in capitals (the Morphemes line) in small caps
    quotes: str = SINGLE          # translations in ‘single’ or “double” quotes, or none


CURRENT = Conventions()           # set from this computer's settings by the main window


def load(prefs) -> Conventions:
    g = prefs.get_bool
    q = prefs.get_value("conventions/quotes")
    c = Conventions(on=g("conventions/on", True), brackets=g("conventions/brackets", True),
                    slashes=g("conventions/slashes", True), small_caps=g("conventions/small_caps", True),
                    quotes=q if q in QUOTES else SINGLE)
    CURRENT.__dict__.update(c.__dict__)
    return CURRENT


def save(prefs, c: Conventions):
    for k in ("on", "brackets", "slashes", "small_caps"):
        prefs.set_value(f"conventions/{k}", bool(getattr(c, k)))
    prefs.set_value("conventions/quotes", c.quotes)
    CURRENT.__dict__.update(c.__dict__)


def ends(role: str, c: Conventions | None = None) -> tuple[str, str]:
    """What goes before and after a field with this role (phonetic, phonemic, translation…)."""
    c = c or CURRENT
    if not c.on:
        return "", ""
    if role == "phonetic" and c.brackets:
        return "[", "]"
    if role == "phonemic" and c.slashes:
        return "/", "/"
    if role == "translation":
        return QUOTES.get(c.quotes, QUOTES[SINGLE])
    return "", ""


def wrap(role: str, text: str, c: Conventions | None = None) -> str:
    """A whole field's text with its convention (nothing added to an empty one, or to a translation
    already in quotes)."""
    if not text:
        return text
    a, b = ends(role, c)
    if role == "translation" and text[:1] in "‘“'\"" and text[-1:] in "’”'\"":
        return text
    return f"{a}{text}{b}"


def wrap_units(role: str, units: list[str], c: Conventions | None = None) -> list[str]:
    """Lined-up units with the convention on the first and the last (so they still line up)."""
    a, b = ends(role, c)
    if not units or not (a or b):
        return list(units)
    out = list(units)
    first = next((i for i, u in enumerate(out) if u), None)
    last = next((i for i in range(len(out) - 1, -1, -1) if out[i]), None)
    if first is None:
        return out
    out[first] = a + out[first]
    out[last] = out[last] + b
    return out


def small_caps_on(role: str, c: Conventions | None = None) -> bool:
    c = c or CURRENT
    return c.on and c.small_caps and role == "morphemes"


_WORD = re.compile(r"[A-Za-z0-9]+")


def runs(text: str) -> list[tuple[str, bool]]:
    """The text in pieces, (piece, in small caps?): each run of letters and digits written in
    capitals (PL, 1SG, GEN; at least one letter, no lowercase) is a small-caps piece."""
    out, at = [], 0
    for m in _WORD.finditer(text):
        w = m.group()
        if any(ch.isalpha() for ch in w) and not any(ch.islower() for ch in w):
            if m.start() > at:
                out.append((text[at:m.start()], False))
            out.append((w, True))
            at = m.end()
    if at < len(text):
        out.append((text[at:], False))
    return out or [("", False)]


def caps_font(font: QFont) -> QFont:
    f = QFont(font)
    f.setCapitalization(QFont.SmallCaps)
    return f


def width(text: str, font: QFont, small_caps: bool) -> int:
    """How wide the text is drawn (with its capitals in small caps when small_caps)."""
    if not small_caps:
        return QFontMetrics(font).horizontalAdvance(text)
    fm, fc = QFontMetrics(font), QFontMetrics(caps_font(font))
    return sum((fc.horizontalAdvance(p.lower()) if caps else fm.horizontalAdvance(p)) for p, caps in runs(text))


def draw(painter, rect, flags, text: str, font: QFont, small_caps: bool):
    """Draw the text left-aligned in rect (its capitals in small caps when small_caps)."""
    from PySide6.QtCore import QRect
    if not small_caps or not any(caps for _, caps in runs(text)):
        painter.setFont(font)
        painter.drawText(rect, flags, text)
        return
    x = rect.x()
    fm, fc = QFontMetrics(font), QFontMetrics(caps_font(font))
    cf = caps_font(font)
    for piece, caps in runs(text):
        painter.setFont(cf if caps else font)
        shown = piece.lower() if caps else piece
        w = (fc if caps else fm).horizontalAdvance(shown)
        painter.drawText(QRect(x, rect.y(), w + 2, rect.height()), flags, shown)
        x += w
    painter.setFont(font)
