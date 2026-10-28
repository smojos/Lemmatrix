# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders. Additional terms: NOTICE.md
"""Drawing the Constituents tier (IDEAS.md idea 91) over the lined-up words of a cell: each phrase
a bracket spanning its words, its label on it (left, centred or right: Settings → Display), nested ones inside (lower); floating
labels just above their word. The notation itself (_, brackets) shows only while editing.

    ┌────NP────┐       ┌──NP───┐
    │      MOD │   V  │       │
    kʊ̀ʊn   rɪ̀ɪŋ    tʌ́  ŋɔ́ɔɲ  ɲàmá

Used by a text's lines and the utterance cell (lines_view.py) and the matrix cells
(matrix_view.py), with the columns they line the words up in."""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QFontMetrics, QPainter, QPen

from .. import constituents as cons
from . import conventions

TICK = 4          # the bracket's ends, pointing down at the words


def level_h(font) -> int:
    return QFontMetrics(font).height() + 2


def height(text: str, font) -> int:
    """How tall the drawing is: a level per depth of brackets, and one for floating labels."""
    p = cons.parse(text)
    floating = any(s.label for s in p.slots)
    levels = p.depth + (1 if floating else 0)
    return max(1, levels) * level_h(font) + 2


def drawable(text: str, n_cols: int) -> bool:
    """Whether the line can be drawn as brackets over n_cols lined-up words: closed brackets and
    no more words than there are columns."""
    p = cons.parse(text)
    return bool(text.strip()) and not p.errors and 0 < len(p.slots) <= n_cols


def _place(a: float, b: float, w: float, align: str) -> float:
    """Where a label w wide starts between a and b: left, centred (the default) or right
    (Settings → Display → Constituent labels; Josh, 28 October)."""
    if align == "left":
        return a
    if align == "right":
        return b - w
    return (a + b - w) / 2


def paint(p: QPainter, x0: float, y0: float, cols: list, text: str, font, colour, gap: float = 0):
    """Draw the line's brackets and labels from (x0, y0) down, over columns of the given widths
    (each column a word, its width including the gap after it)."""
    parse = cons.parse(text)
    if parse.errors:
        return
    bottom = y0 + height(text, font) - 2         # the brackets' ends reach down to the words,
    if any(sl.label for sl in parse.slots):      # or to the floating labels
        bottom = y0 + parse.depth * level_h(font)
    xs, x = [], x0
    for w in cols:
        xs.append(x)
        x += w
    lh = level_h(font)
    caps = conventions.small_caps_on(cons.ROLE)
    align = conventions.CURRENT.label_align
    fm = QFontMetrics(font)
    p.save()
    p.setPen(QPen(colour, 1.2))
    p.setFont(font)
    for ph in sorted(parse.phrases, key=lambda ph: ph.depth):
        if ph.end >= len(xs):
            continue
        left = xs[ph.start] - 2 + ph.depth * 5
        right = xs[ph.end] + cols[ph.end] - gap - 2 - ph.depth * 5
        y = y0 + ph.depth * lh + lh / 2
        label = ph.label
        lw = conventions.width(label, font, caps) if label else 0
        end = max(y + TICK, bottom)
        lx = _place(left + 4, right - 4, lw, align)  # left, centred or right on the bracket (Josh, 28 October)
        clear = (not label) or (lx >= left + 3.5 and lx + lw <= right - 3.5)   # the label fits
        top = y if clear else y + fm.height() / 2    # a label wider than its words: the ends start under it
        p.drawLine(QPointF(left, top), QPointF(left, end))        # the ends, down to the words
        p.drawLine(QPointF(right, top), QPointF(right, end))
        if label:
            conventions.draw(p, QRectF(lx, y - fm.height() / 2, lw + 4, fm.height()).toRect(),
                             Qt.AlignLeft | Qt.AlignVCenter, label, font, caps)
            if clear:                                # the line either side of the label
                if lx - 4 > left + 1:
                    p.drawLine(QPointF(left, y), QPointF(lx - 4, y))
                else:
                    p.drawLine(QPointF(left, y), QPointF(left + 2, y))
                if lx + lw + 4 < right - 1:
                    p.drawLine(QPointF(lx + lw + 4, y), QPointF(right, y))
                else:
                    p.drawLine(QPointF(right - 2, y), QPointF(right, y))
        else:
            p.drawLine(QPointF(left, y), QPointF(right, y))
    fy = y0 + parse.depth * lh
    for s in parse.slots:                            # floating labels over their word
        if s.label and s.index < len(xs):
            lw = conventions.width(s.label, font, caps)
            word_w = max(cols[s.index] - gap, lw)
            lx = _place(xs[s.index], xs[s.index] + word_w, lw, align)
            conventions.draw(p, QRectF(lx, fy, lw + 4, lh).toRect(),
                             Qt.AlignLeft | Qt.AlignVCenter, s.label, font, caps)
    p.restore()
