# SPDX-License-Identifier: LicenseRef-Lemmatrix-Artwork
# Copyright © 2026 Joshua A. G. Smolders. All rights reserved: see ARTWORK.md.
"""Icons drawn by the program (no image files), so they look the same everywhere. Josh's artwork,
not under the AGPL: modified versions of Lemmatrix must replace this module (ARTWORK.md)."""

from __future__ import annotations

import math
import re
from functools import lru_cache
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap, QPolygonF

# Josh's χμλ for the XML viewer (21 October), his Inkscape file as it is; its teal becomes the theme colour
XML_VIEWER_FILE = Path(__file__).resolve().parent.parent / "resources" / "xml_viewer.svg"
QUESTIONS_FILE = Path(__file__).resolve().parent.parent / "resources" / "questions.svg"   # Josh's, 21 October
COGITATE_FILE = Path(__file__).resolve().parent.parent / "resources" / "cogitate.svg"     # Josh's hypotheses.svg
TODO_FILE = Path(__file__).resolve().parent.parent / "resources" / "to_do.svg"            # Josh's, 22 October

GREEN = QColor("#2e9e44")
RED = QColor("#d93030")
PURPLE = QColor("#7b3fbf")
BLUE = QColor("#3a78d4")
ORANGE = QColor("#e8822a")                       # To Do's flag (Josh, 21 October)
WHITE = QColor("white")
BLACK = QColor("#1b1b1b")


WIDE = {"gear-cells": 1.6, "gear-columns": 1.6, "gear-matrix": 1.6, "move-token": 1.6, "lemma-token": 1.6, "text-token": 1.3}   # icons wider than tall: width as a multiple of height
PRAAT_BEIGE = QColor("#909068")


# Josh's Texts and utterances icon (Inkscape, 20 October), its letters (Charis SIL Bold) as outlines
# so it looks the same without the font. {dark} is the theme colour, {light} a lighter shade of it.
TEXTS_UTTERANCES_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 33.750435 33.750435">
<g transform="translate(0.20704102,2.6205319)">
<path fill="{dark}" d="m 5.3862345,3.6220011 c -1.8836,0 -3.3997924,1.5167092 -3.3997924,3.4003093 v 6.4032266 c 0,1.8836 1.5161924,3.399793 3.3997924,3.399793 h 1.9166789 l 3.0375406,8.06204 0.116789,-8.06204 h 9.492444 c 1.8836,0 3.399792,-1.516193 3.399792,-3.399793 V 7.0223104 c 0,-1.8836001 -1.516192,-3.4003093 -3.399792,-3.4003093 z"/>
<path fill="{light}" d="M 17.691091 9.165312 C 15.807491 9.165312 14.290782 10.682021 14.290782 12.565621 L 14.290782 18.968848 C 14.290782 19.034523 14.296962 19.098418 14.300601 19.163151 L 14.290782 19.160051 L 10.340636 24.88735 L 17.304552 22.36864 L 17.29525 22.343836 C 17.425224 22.358795 17.55698 22.36864 17.691091 22.36864 L 27.949897 22.36864 C 29.833497 22.36864 31.349689 20.852448 31.349689 18.968848 L 31.349689 12.565621 C 31.349689 10.682021 29.833497 9.165312 27.949897 9.165312 L 17.691091 9.165312 z"/>
</g>
<path fill="#ffffff" d="M12.839 11.339H12.121L11.942 10.24Q11.928 10.124 11.802 10.124H10.698V15.386Q10.698 15.483 10.763 15.538Q10.828 15.593 10.915 15.603L11.498 15.656V16.158H8.484V15.656L9.058 15.603Q9.15 15.593 9.217 15.538Q9.285 15.483 9.285 15.386V10.124H8.18Q8.045 10.124 8.031 10.24L7.852 11.339H7.143V9.531H12.839Z"/>
<path fill="#ffffff" d="M26.392 15.496 25.866 15.544Q25.789 15.554 25.719 15.612Q25.649 15.67 25.649 15.766V19.113Q25.649 20.57 24.988 21.175Q24.327 21.781 22.943 21.781Q21.67 21.781 21.048 21.098Q20.425 20.416 20.425 19.113V15.766Q20.425 15.67 20.355 15.612Q20.286 15.554 20.199 15.544L19.663 15.496V14.994H22.586V15.496L22.056 15.544Q21.974 15.554 21.906 15.612Q21.839 15.67 21.839 15.766V19.191Q21.839 20.117 22.229 20.539Q22.62 20.961 23.435 20.961Q24.212 20.961 24.554 20.476Q24.896 19.991 24.896 19.191V15.766Q24.896 15.67 24.834 15.612Q24.771 15.554 24.679 15.544L24.12 15.496V14.994H26.392Z"/>
</svg>"""


def _pixmap(size: int, width: int | None = None) -> tuple[QPixmap, QPainter]:
    pm = QPixmap((width or size) * 2, size * 2)  # drawn at 2x for sharp edges
    pm.setDevicePixelRatio(2.0)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    return pm, p


def _circle(p, s, color):
    p.setPen(Qt.NoPen)
    p.setBrush(color)
    p.drawEllipse(QRectF(1, 1, s - 2, s - 2))


def _rounded(p, s, color):
    p.setPen(Qt.NoPen)
    p.setBrush(color)
    p.drawRoundedRect(QRectF(1, 1, s - 2, s - 2), s * 0.22, s * 0.22)


def _plus(p, s, width):
    p.setPen(QPen(WHITE, width, Qt.SolidLine, Qt.RoundCap))
    m = s * 0.28
    p.drawLine(QPointF(s / 2, m), QPointF(s / 2, s - m))
    p.drawLine(QPointF(m, s / 2), QPointF(s - m, s / 2))


def _cross(p, s, width, color=WHITE, margin=0.3):
    p.setPen(QPen(color, width, Qt.SolidLine, Qt.RoundCap))
    m = s * margin
    p.drawLine(QPointF(m, m), QPointF(s - m, s - m))
    p.drawLine(QPointF(s - m, m), QPointF(m, s - m))


def _notepad(p, s, colour, x=0.0, y=0.0, scale=1.0):
    """A spiral notepad in a colour, with white lines of writing."""
    def P(a, b):
        return QPointF(s * (x + a * scale), s * (y + b * scale))
    p.setPen(Qt.NoPen)
    p.setBrush(colour)
    p.drawRoundedRect(QRectF(P(0.16, 0.14), P(0.84, 0.94)), s * 0.08 * scale, s * 0.08 * scale)
    p.setPen(QPen(WHITE, max(1.0, s * 0.055 * scale), Qt.SolidLine, Qt.RoundCap))
    for a in (0.30, 0.44, 0.58, 0.72):                  # the spiral's rings
        p.drawLine(P(a, 0.06), P(a, 0.22))
    p.setPen(QPen(WHITE, max(1.0, s * 0.05 * scale), Qt.SolidLine, Qt.RoundCap))
    for b, end in ((0.40, 0.72), (0.54, 0.72), (0.68, 0.72), (0.82, 0.56)):
        p.drawLine(P(0.28, b), P(end, b))


def _block_arrow(s, cy, direction):
    """A solid arrow across the icon at height cy (a fraction), pointing right (1) or left (-1)."""
    shaft, head_h, head_l = 0.115, 0.225, 0.32     # half-heights and the head's length, as fractions
    tip, tail = (0.97, 0.04) if direction > 0 else (0.03, 0.96)
    neck = tip - direction * head_l
    pts = [(tail, cy - shaft), (neck, cy - shaft), (neck, cy - head_h), (tip, cy),
           (neck, cy + head_h), (neck, cy + shaft), (tail, cy + shaft)]
    return QPolygonF([QPointF(s * x, s * y) for x, y in pts])


def funnel(box: QRectF) -> QPolygonF:
    """The filter funnel, filling a box: the reset-filters icon's, and the column headers' (one shape)."""
    x, y, w, h = box.x(), box.y(), box.width(), box.height()
    return QPolygonF([QPointF(x, y), QPointF(x + w, y),
                      QPointF(x + w * 0.625, y + h * 0.512), QPointF(x + w * 0.625, y + h),
                      QPointF(x + w * 0.375, y + h), QPointF(x + w * 0.375, y + h * 0.512)])


def _draw(name: str, s: int, p: QPainter, colour: QColor | None = None, colour2: QColor | None = None):
    w = max(1.6, s * 0.11)
    if name == "notebook":                       # a notepad in the theme colour
        _notepad(p, s, colour or BLUE)
    elif name == "clip":                         # Josh's: scissors cutting a speech bubble (Clip as utterance)
        bubble = QPainterPath()
        bubble.addRoundedRect(QRectF(s * 0.44, s * 0.04, s * 0.54, s * 0.44), s * 0.09, s * 0.09)
        tail = QPainterPath()
        tail.addPolygon(QPolygonF([QPointF(s * 0.56, s * 0.44), QPointF(s * 0.72, s * 0.44), QPointF(s * 0.50, s * 0.70)]))
        tail.closeSubpath()
        fill = QColor(colour or GREEN)
        fill.setAlpha(225)
        p.setPen(Qt.NoPen)
        p.setBrush(fill)
        p.drawPath(bubble.united(tail))
        ink_colour = colour2 or BLACK                # the scissors: the theme's text colour (white on dark)
        ink = QPen(ink_colour, max(1.4, s * 0.085), Qt.SolidLine, Qt.RoundCap)
        p.setPen(ink)
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(QPointF(s * 0.17, s * 0.36), s * 0.11, s * 0.11)          # the handles
        p.drawEllipse(QPointF(s * 0.17, s * 0.80), s * 0.11, s * 0.11)
        p.drawLine(QPointF(s * 0.27, s * 0.42), QPointF(s * 0.95, s * 0.80))    # the blades
        p.drawLine(QPointF(s * 0.27, s * 0.74), QPointF(s * 0.90, s * 0.46))
        p.setPen(Qt.NoPen)
        p.setBrush(BLACK if ink_colour.lightnessF() > 0.5 else WHITE)
        p.drawEllipse(QPointF(s * 0.505, s * 0.585), s * 0.03, s * 0.03)      # the pivot
    elif name == "texts-utterances":             # Josh's design (20 October): a T bubble and a lighter U bubble
        from PySide6.QtCore import QByteArray
        from PySide6.QtSvg import QSvgRenderer
        dark = colour or GREEN
        light = QColor.fromHslF(dark.hslHueF(), dark.hslSaturationF() * 0.676,     # #198583 → #5cc3c0
                                dark.lightnessF() + (1 - dark.lightnessF()) * 0.367)
        svg = TEXTS_UTTERANCES_SVG.format(dark=dark.name(), light=light.name())
        QSvgRenderer(QByteArray(svg.encode("utf-8"))).render(p, QRectF(0, 0, s, s))
    elif name == "pin":                          # a pushpin (pinned questions and To Dos), in a colour
        c = colour or BLUE
        p.save()
        p.translate(s * 0.5, s * 0.5)
        p.rotate(35)
        p.translate(-s * 0.5, -s * 0.5)
        p.setPen(Qt.NoPen)
        p.setBrush(c)
        p.drawRoundedRect(QRectF(s * 0.30, s * 0.06, s * 0.40, s * 0.12), s * 0.04, s * 0.04)   # the head
        p.drawPolygon(QPolygonF([QPointF(s * 0.36, s * 0.18), QPointF(s * 0.64, s * 0.18),
                                 QPointF(s * 0.70, s * 0.46), QPointF(s * 0.30, s * 0.46)]))  # the body
        p.drawRoundedRect(QRectF(s * 0.20, s * 0.44, s * 0.60, s * 0.10), s * 0.04, s * 0.04)   # the collar
        p.setPen(QPen(c, max(1.2, s * 0.06), Qt.SolidLine, Qt.RoundCap))
        p.drawLine(QPointF(s * 0.5, s * 0.54), QPointF(s * 0.5, s * 0.95))                     # the needle
        p.restore()
    elif name == "lightbulb":                    # light or dark theme: the bulb in the colour given
        c = colour or BLACK
        p.setPen(Qt.NoPen)
        p.setBrush(c)
        bulb = QPainterPath()
        bulb.addEllipse(QPointF(s * 0.5, s * 0.38), s * 0.27, s * 0.27)
        neck = QPainterPath()
        neck.addPolygon(QPolygonF([QPointF(s * 0.33, s * 0.52), QPointF(s * 0.67, s * 0.52),
                                   QPointF(s * 0.62, s * 0.72), QPointF(s * 0.38, s * 0.72)]))
        p.drawPath(bulb.united(neck))
        p.drawRoundedRect(QRectF(s * 0.37, s * 0.76, s * 0.26, s * 0.07), s * 0.03, s * 0.03)   # the screw
        p.drawRoundedRect(QRectF(s * 0.40, s * 0.86, s * 0.20, s * 0.07), s * 0.03, s * 0.03)
        p.setPen(QPen(c, max(1.0, s * 0.06), Qt.SolidLine, Qt.RoundCap))
        for ang in (-150, -115, -65, -30):                                                       # its rays
            r1, r2 = s * 0.36, s * 0.46
            a = math.radians(ang)
            p.drawLine(QPointF(s * 0.5 + r1 * math.cos(a), s * 0.38 + r1 * math.sin(a)),
                       QPointF(s * 0.5 + r2 * math.cos(a), s * 0.38 + r2 * math.sin(a)))
    elif name == "write-notebook":               # a pencil, and an arrow pointing at the notebook
        p.setPen(QPen(BLACK, max(1.0, s * 0.05)))
        p.setBrush(WHITE)
        body = QPolygonF([QPointF(s * 0.14, s * 0.46), QPointF(s * 0.46, s * 0.14),
                          QPointF(s * 0.60, s * 0.28), QPointF(s * 0.28, s * 0.60)])
        p.drawPolygon(body)
        p.setBrush(BLACK)
        p.drawPolygon(QPolygonF([QPointF(s * 0.14, s * 0.46), QPointF(s * 0.28, s * 0.60),
                                 QPointF(s * 0.06, s * 0.68)]))
        p.drawLine(QPointF(s * 0.38, s * 0.22), QPointF(s * 0.52, s * 0.36))
        shaft_y, tip = s * 0.80, s * 0.96
        arrow = QPolygonF([QPointF(s * 0.20, shaft_y - s * 0.05), QPointF(s * 0.70, shaft_y - s * 0.05),
                           QPointF(s * 0.70, shaft_y - s * 0.15), QPointF(tip, shaft_y),
                           QPointF(s * 0.70, shaft_y + s * 0.15), QPointF(s * 0.70, shaft_y + s * 0.05),
                           QPointF(s * 0.20, shaft_y + s * 0.05)])
        p.setPen(QPen(WHITE, max(1.0, s * 0.05), Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.setBrush(BLACK)
        p.drawPolygon(arrow)
    elif name == "calendar":                     # a page of a calendar
        p.setPen(QPen(BLACK, max(1.0, s * 0.06)))
        p.setBrush(WHITE)
        p.drawRoundedRect(QRectF(s * 0.12, s * 0.18, s * 0.76, s * 0.70), s * 0.08, s * 0.08)
        p.setPen(Qt.NoPen)
        p.setBrush(colour or RED)
        p.drawRect(QRectF(s * 0.15, s * 0.21, s * 0.70, s * 0.17))
        p.setBrush(BLACK)
        for r in range(3):
            for c in range(4):
                p.drawRect(QRectF(s * (0.22 + c * 0.15), s * (0.46 + r * 0.13), s * 0.08, s * 0.07))
        p.setPen(QPen(BLACK, max(1.2, s * 0.07), Qt.SolidLine, Qt.RoundCap))
        p.drawLine(QPointF(s * 0.32, s * 0.10), QPointF(s * 0.32, s * 0.26))
        p.drawLine(QPointF(s * 0.68, s * 0.10), QPointF(s * 0.68, s * 0.26))
    elif name == "resolve":                      # a purple square with a white tick
        _rounded(p, s, PURPLE)
        p.setPen(QPen(WHITE, max(1.6, s * 0.10), Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.setBrush(Qt.NoBrush)
        p.drawPolyline(QPolygonF([QPointF(s * 0.26, s * 0.52), QPointF(s * 0.43, s * 0.69),
                                  QPointF(s * 0.75, s * 0.32)]))
    elif name == "add":
        _circle(p, s, GREEN)
        _plus(p, s, w)
    elif name == "delete":
        _circle(p, s, RED)
        _cross(p, s, w, margin=0.32)
    elif name == "edit":                         # black-on-white pencil
        p.setPen(QPen(BLACK, max(1.0, s * 0.06)))
        p.setBrush(WHITE)
        body = QPolygonF([QPointF(s * 0.22, s * 0.62), QPointF(s * 0.62, s * 0.22),
                          QPointF(s * 0.78, s * 0.38), QPointF(s * 0.38, s * 0.78)])
        p.drawPolygon(body)
        tip = QPolygonF([QPointF(s * 0.22, s * 0.62), QPointF(s * 0.38, s * 0.78),
                         QPointF(s * 0.14, s * 0.86)])
        p.setBrush(BLACK)
        p.drawPolygon(tip)
        p.drawLine(QPointF(s * 0.54, s * 0.30), QPointF(s * 0.70, s * 0.46))
    elif name in ("gear-cells", "gear-columns"):  # the gear, then cells (stacked lines) or columns, in a colour
        _draw("gear", s, p)
        p.setPen(Qt.NoPen)
        p.setBrush(colour or GREEN)
        x0, x1 = s * 1.03, s * 1.57
        lw = max(1.0, s * 0.06)
        if name == "gear-cells":
            boxes = [QRectF(x0, s * 0.12, x1 - x0, s * 0.35), QRectF(x0, s * 0.53, x1 - x0, s * 0.35)]
            for b in boxes:
                p.setBrush(colour or GREEN)
                p.drawRect(b)
                p.setBrush(WHITE)
                for k, dashed in ((0.25, False), (0.5, True), (0.75, False)):
                    y = b.top() + b.height() * k - lw / 2
                    if dashed:
                        n = 4
                        seg = (b.width() * 0.8) / (2 * n - 1)
                        for j in range(n):
                            p.drawRect(QRectF(b.left() + b.width() * 0.1 + 2 * j * seg, y, seg, lw))
                    else:
                        p.drawRect(QRectF(b.left() + b.width() * 0.1, y, b.width() * 0.8, lw))
        else:
            gap = s * 0.08
            w = (x1 - x0 - gap) / 2
            for bx in (x0, x0 + w + gap):
                b = QRectF(bx, s * 0.08, w, s * 0.84)
                p.setBrush(colour or GREEN)
                p.drawRect(b)
                p.setBrush(WHITE)
                n = 6
                for j in range(n):
                    y = b.top() + b.height() * (j + 0.6) / (n + 0.2) - lw / 2
                    p.drawRect(QRectF(b.left() + w * 0.2, y, w * 0.6, lw))
    elif name == "gear-matrix":                  # the gear, then a χ (the icon's letter), drawn as strokes
        _draw("gear", s, p)
        p.setPen(QPen(colour or GREEN, max(1.4, s * 0.10), Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.setBrush(Qt.NoBrush)
        curve = QPainterPath()                   # top left, with a hook, down to the bottom right, with a tail
        curve.moveTo(s * 1.04, s * 0.24)
        curve.cubicTo(s * 1.12, s * 0.08, s * 1.21, s * 0.16, s * 1.27, s * 0.48)
        curve.cubicTo(s * 1.33, s * 0.80, s * 1.40, s * 0.94, s * 1.52, s * 0.84)
        p.drawPath(curve)
        p.drawLine(QPointF(s * 1.50, s * 0.14), QPointF(s * 1.06, s * 0.90))
    elif name in ("lemma-token", "move-token"):  # λ→τ: a token made for a lemma (21 October);
        c = colour or GREEN                       # λ←τ: a token moved to another lemma (Josh: symmetry)
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(c, max(1.6, s * 0.10), Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        w, top, bottom = s * 0.42, s * 0.18, s * 0.84
        x0 = s * 0.06                             # λ, as in move-token
        hook = QPainterPath()
        hook.moveTo(x0, top)
        hook.lineTo(x0 + w * 0.22, top)
        hook.lineTo(x0 + w, bottom)
        p.drawPath(hook)
        p.drawLine(QPointF(x0 + w * 0.56, s * 0.50), QPointF(x0 + w * 0.02, bottom))
        y, a0, a1 = s * 0.56, s * 0.58, s * 1.02  # the arrow
        p.drawLine(QPointF(a0, y), QPointF(a1, y))
        tip, back = (a1, -1) if name == "lemma-token" else (a0, 1)     # → or ←
        p.drawLine(QPointF(tip + back * s * 0.14, y - s * 0.13), QPointF(tip, y))
        p.drawLine(QPointF(tip + back * s * 0.14, y + s * 0.13), QPointF(tip, y))
        t0, t1 = s * 1.14, s * 1.56               # τ: a bar with a stem that curls right at its foot
        p.drawLine(QPointF(t0, s * 0.36), QPointF(t1, s * 0.36))
        stem = QPainterPath()
        sx = (t0 + t1) / 2 - s * 0.02
        stem.moveTo(sx, s * 0.36)
        stem.lineTo(sx, s * 0.72)
        stem.quadTo(sx, s * 0.84, sx + s * 0.13, s * 0.80)
        p.drawPath(stem)
    elif name == "text-token":                   # ➜τ: a token made from a text's line (Josh, 21 October)
        c = colour or GREEN
        p.setPen(Qt.NoPen)
        p.setBrush(c)
        y = s * 0.52                              # ➜: a heavy arrow, its tail narrower than its head
        p.drawPolygon(QPolygonF([QPointF(s * 0.04, y - s * 0.07), QPointF(s * 0.40, y - s * 0.11),
                                 QPointF(s * 0.36, y - s * 0.28), QPointF(s * 0.74, y),
                                 QPointF(s * 0.36, y + s * 0.28), QPointF(s * 0.40, y + s * 0.11),
                                 QPointF(s * 0.04, y + s * 0.07)]))
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(c, max(1.6, s * 0.10), Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        t0, t1 = s * 0.84, s * 1.26               # τ, as in λ→τ
        p.drawLine(QPointF(t0, s * 0.36), QPointF(t1, s * 0.36))
        stem = QPainterPath()
        sx = (t0 + t1) / 2 - s * 0.02
        stem.moveTo(sx, s * 0.36)
        stem.lineTo(sx, s * 0.72)
        stem.quadTo(sx, s * 0.84, sx + s * 0.13, s * 0.80)
        p.drawPath(stem)
    elif name == "find-missing":                 # a magnifying glass over a music note, in a colour
        c = colour or GREEN
        cx, cy, r = s * 0.42, s * 0.42, s * 0.30
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(c, max(1.6, s * 0.09)))
        p.drawEllipse(QPointF(cx, cy), r, r)
        p.setPen(QPen(c, max(2.4, s * 0.14), Qt.SolidLine, Qt.RoundCap))
        d = r * 0.7071 + s * 0.05
        p.drawLine(QPointF(cx + d, cy + d), QPointF(s * 0.88, s * 0.88))
        p.setPen(Qt.NoPen)                       # the note: a head, a stem and a flag
        p.setBrush(c)
        p.save()
        p.translate(cx - s * 0.05, cy + s * 0.12)
        p.rotate(-20)
        p.drawEllipse(QPointF(0, 0), s * 0.095, s * 0.07)
        p.restore()
        sx = cx - s * 0.05 + s * 0.075
        p.drawRect(QRectF(sx, cy - s * 0.20, max(1.0, s * 0.05), s * 0.31))
        flag = QPainterPath()
        flag.moveTo(sx, cy - s * 0.20)
        flag.cubicTo(sx + s * 0.05, cy - s * 0.12, sx + s * 0.16, cy - s * 0.10, sx + s * 0.12, cy + s * 0.01)
        flag.cubicTo(sx + s * 0.12, cy - s * 0.06, sx + s * 0.05, cy - s * 0.07, sx, cy - s * 0.10)
        flag.closeSubpath()
        p.drawPath(flag)
    elif name == "gear":                         # black-on-white gear
        c = QPointF(s / 2, s / 2)
        outer, inner, teeth = s * 0.46, s * 0.34, 8
        path = QPainterPath()
        for i in range(teeth * 2):
            a0 = math.pi * i / teeth
            r = outer if i % 2 == 0 else inner
            for da in (-0.18, 0.18):
                pt = QPointF(c.x() + r * math.cos(a0 + da), c.y() + r * math.sin(a0 + da))
                if path.elementCount() == 0:
                    path.moveTo(pt)
                else:
                    path.lineTo(pt)
        path.closeSubpath()
        hole = QPainterPath()
        hole.addEllipse(c, s * 0.14, s * 0.14)
        p.setPen(QPen(BLACK, max(1.0, s * 0.06)))
        p.setBrush(WHITE)
        p.drawPath(path.subtracted(hole))
    elif name == "record":                       # purple rounded square, white microphone
        _rounded(p, s, PURPLE)
        p.setPen(Qt.NoPen)
        p.setBrush(WHITE)
        p.drawRoundedRect(QRectF(s * 0.40, s * 0.18, s * 0.20, s * 0.38), s * 0.10, s * 0.10)
        p.setPen(QPen(WHITE, max(1.4, s * 0.06)))
        p.setBrush(Qt.NoBrush)
        p.drawArc(QRectF(s * 0.30, s * 0.30, s * 0.40, s * 0.36), 200 * 16, 140 * 16)
        p.drawLine(QPointF(s / 2, s * 0.66), QPointF(s / 2, s * 0.80))
        p.drawLine(QPointF(s * 0.38, s * 0.80), QPointF(s * 0.62, s * 0.80))
    elif name == "stop":                         # purple rounded square, white square
        _rounded(p, s, PURPLE)
        p.setPen(Qt.NoPen)
        p.setBrush(WHITE)
        p.drawRect(QRectF(s * 0.32, s * 0.32, s * 0.36, s * 0.36))
    elif name == "play":                         # green rounded square, white triangle
        _rounded(p, s, GREEN)
        p.setPen(Qt.NoPen)
        p.setBrush(WHITE)
        p.drawPolygon(QPolygonF([QPointF(s * 0.36, s * 0.26), QPointF(s * 0.36, s * 0.74),
                                 QPointF(s * 0.76, s * 0.5)]))
    elif name == "delete-recording":             # red rounded square, white X
        _rounded(p, s, RED)
        _cross(p, s, w)
    elif name == "update":                       # blue rounded square, white update arrows
        _rounded(p, s, BLUE)
        pen = QPen(WHITE, max(1.6, s * 0.08), Qt.SolidLine, Qt.RoundCap)
        p.setPen(pen)
        r = QRectF(s * 0.26, s * 0.26, s * 0.48, s * 0.48)
        p.drawArc(r, 30 * 16, 150 * 16)
        p.drawArc(r, 210 * 16, 150 * 16)
        p.setPen(Qt.NoPen)
        p.setBrush(WHITE)
        a = s * 0.11
        for cx, cy, d in ((s * 0.71, s * 0.38, -1), (s * 0.29, s * 0.62, 1)):
            p.drawPolygon(QPolygonF([QPointF(cx - a, cy), QPointF(cx + a, cy),
                                     QPointF(cx, cy + d * a * 1.2)]))
    elif name in ("up", "down"):                 # white arrow, black outline (reads on light and dark)
        if name == "up":
            pts = [QPointF(s / 2, s * 0.12), QPointF(s * 0.86, s * 0.52), QPointF(s * 0.62, s * 0.52),
                   QPointF(s * 0.62, s * 0.86), QPointF(s * 0.38, s * 0.86), QPointF(s * 0.38, s * 0.52),
                   QPointF(s * 0.14, s * 0.52)]
        else:
            pts = [QPointF(s / 2, s * 0.88), QPointF(s * 0.86, s * 0.48), QPointF(s * 0.62, s * 0.48),
                   QPointF(s * 0.62, s * 0.14), QPointF(s * 0.38, s * 0.14), QPointF(s * 0.38, s * 0.48),
                   QPointF(s * 0.14, s * 0.48)]
        p.setPen(QPen(BLACK, max(1.0, s * 0.06), Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.setBrush(WHITE)
        p.drawPolygon(QPolygonF(pts))
    elif name in ("switch", "switch-plain"):     # two solid arrows, ⇄, in a colour (switch: a white edge)
        p.setPen(QPen(WHITE, max(1.0, s * 0.05), Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
                 if name == "switch" else Qt.NoPen)
        p.setBrush(colour or BLACK)
        for cy, d in ((0.27, 1), (0.73, -1)):    # top points right, bottom points left
            p.drawPolygon(_block_arrow(s, cy, d))
    elif name == "reset-filters":                # a funnel (colour) inside two turning arrows (colour2)
        c = colour2 or colour or BLACK
        cx, cy, r = s / 2, s / 2, s * 0.40
        p.setPen(QPen(c, max(2.4, s * 0.11), Qt.SolidLine, Qt.FlatCap))
        p.setBrush(Qt.NoBrush)
        box = QRectF(cx - r, cy - r, 2 * r, 2 * r)
        for start in (118, 298):                 # the left arc, and the right one opposite it
            p.drawArc(box, start * 16, 104 * 16)
        p.setPen(Qt.NoPen)
        p.setBrush(c)
        for end in (222, 42):                    # arrowheads where the arcs end, pointing along them
            a = math.radians(end)
            ex, ey = cx + r * math.cos(a), cy - r * math.sin(a)
            tx, ty = -math.sin(a), -math.cos(a)  # direction of travel (anticlockwise on screen)
            nx, ny = math.cos(a), -math.sin(a)   # outward
            L, W = s * 0.22, s * 0.15
            p.drawPolygon(QPolygonF([QPointF(ex + tx * L, ey + ty * L),
                                     QPointF(ex + nx * W, ey + ny * W),
                                     QPointF(ex - nx * W, ey - ny * W)]))
        p.setBrush(colour or BLACK)
        p.drawPolygon(funnel(QRectF(s * 0.26, s * 0.31, s * 0.48, s * 0.41)))
    elif name == "refresh-text":                 # two turning arrows round three lines of text, in a colour
        c = colour or BLACK                       # (Refresh text: the TextGrid read again; 21 October)
        cx, cy, r = s / 2, s / 2, s * 0.40
        p.setPen(QPen(c, max(2.0, s * 0.10), Qt.SolidLine, Qt.FlatCap))
        p.setBrush(Qt.NoBrush)
        box = QRectF(cx - r, cy - r, 2 * r, 2 * r)
        for start in (118, 298):
            p.drawArc(box, start * 16, 104 * 16)
        p.setPen(Qt.NoPen)
        p.setBrush(c)
        for end in (222, 42):
            a = math.radians(end)
            ex, ey = cx + r * math.cos(a), cy - r * math.sin(a)
            tx, ty = -math.sin(a), -math.cos(a)
            nx, ny = math.cos(a), -math.sin(a)
            L, W = s * 0.22, s * 0.15
            p.drawPolygon(QPolygonF([QPointF(ex + tx * L, ey + ty * L),
                                     QPointF(ex + nx * W, ey + ny * W),
                                     QPointF(ex - nx * W, ey - ny * W)]))
        p.setPen(QPen(c, max(1.4, s * 0.07), Qt.SolidLine, Qt.RoundCap))
        for y, w in ((0.38, 0.36), (0.50, 0.36), (0.62, 0.24)):
            p.drawLine(QPointF(s * 0.32, s * y), QPointF(s * (0.32 + w), s * y))
    elif name in ("chevron-down", "chevron-up"):   # a bold chevron in a colour
        p.setPen(QPen(colour or BLACK, max(1.8, s * 0.14), Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.setBrush(Qt.NoBrush)
        y0, y1 = (0.36, 0.64) if name == "chevron-down" else (0.64, 0.36)
        p.drawPolyline(QPolygonF([QPointF(s * 0.22, s * y0), QPointF(s * 0.5, s * y1),
                                  QPointF(s * 0.78, s * y0)]))
    elif name == "save-solid":                   # a floppy disk in one colour, shutter and label cut out
        body = QPainterPath()
        x0, y0, x1, y1, cut = s * 0.12, s * 0.12, s * 0.88, s * 0.88, s * 0.17
        body.moveTo(x0, y0)
        body.lineTo(x1 - cut, y0)
        body.lineTo(x1, y0 + cut)
        body.lineTo(x1, y1)
        body.lineTo(x0, y1)
        body.closeSubpath()
        holes = QPainterPath()
        holes.addRect(QRectF(s * 0.30, s * 0.12, s * 0.36, s * 0.24))            # the shutter's slot
        holes.addRoundedRect(QRectF(s * 0.25, s * 0.50, s * 0.50, s * 0.28), s * 0.04, s * 0.04)  # label
        p.setPen(Qt.NoPen)
        p.setBrush(colour or BLUE)
        p.drawPath(body.subtracted(holes))
        p.drawRect(QRectF(s * 0.52, s * 0.15, s * 0.09, s * 0.17))           # the shutter's metal
    elif name == "praat":                        # Praat beige rounded square, white waveform (Josh's mockup)
        _rounded(p, s, PRAAT_BEIGE)
        p.setPen(QPen(WHITE, max(1.5, s * 0.08), Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        amps = [0.05, 0.18, 0.32, 0.12, 0.26, 0.08, 0.22, 0.30, 0.10, 0.16, 0.04]
        pts = []
        for i, a in enumerate(amps):
            x = s * (0.18 + 0.64 * i / (len(amps) - 1))
            pts.append(QPointF(x, s * (0.5 - a if i % 2 else 0.5 + a)))
        p.drawPolyline(QPolygonF(pts))
    elif name == "play-pitch":                   # green rounded square, white triangle and a little tune
        _rounded(p, s, GREEN)
        p.setPen(Qt.NoPen)
        p.setBrush(WHITE)
        p.drawPolygon(QPolygonF([QPointF(s * 0.18, s * 0.28), QPointF(s * 0.18, s * 0.72),
                                 QPointF(s * 0.48, s * 0.5)]))
        p.setPen(QPen(WHITE, max(1.3, s * 0.08), Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.setBrush(Qt.NoBrush)
        p.drawPolyline(QPolygonF([QPointF(s * 0.56, s * 0.64), QPointF(s * 0.68, s * 0.36),
                                  QPointF(s * 0.84, s * 0.56)]))
    elif name == "push-question":                # green rounded square, white question mark
        _rounded(p, s, GREEN)
        f = p.font()
        f.setBold(True)
        f.setPixelSize(max(8, round(s * 0.78)))
        p.setFont(f)
        p.setPen(WHITE)
        p.drawText(QRectF(0, 0, s, s * 1.02), Qt.AlignCenter, "?")
    elif name == "push-todo":                    # a little orange flag (To Do), beside the green ?
        p.setPen(QPen(ORANGE.darker(135), max(1.4, s * 0.09), Qt.SolidLine, Qt.RoundCap))
        p.drawLine(QPointF(s * 0.24, s * 0.12), QPointF(s * 0.24, s * 0.90))     # the pole
        p.setPen(Qt.NoPen)
        p.setBrush(ORANGE)
        flag = QPainterPath()                    # the cloth, a gentle wave at its free edge
        flag.moveTo(s * 0.27, s * 0.14)
        flag.cubicTo(s * 0.45, s * 0.07, s * 0.62, s * 0.22, s * 0.84, s * 0.13)
        flag.lineTo(s * 0.84, s * 0.52)
        flag.cubicTo(s * 0.62, s * 0.61, s * 0.45, s * 0.46, s * 0.27, s * 0.53)
        flag.closeSubpath()
        p.drawPath(flag)
    elif name == "thumbs-down":                  # a thumbs-down in one colour (the rerecord flag)
        c = colour or BLACK
        p.setPen(Qt.NoPen)
        p.setBrush(c)
        p.drawRoundedRect(QRectF(s * 0.70, s * 0.10, s * 0.20, s * 0.50), s * 0.04, s * 0.04)   # cuff
        hand = QPainterPath()
        hand.moveTo(s * 0.64, s * 0.10)          # top of the hand, by the cuff
        hand.lineTo(s * 0.26, s * 0.10)
        hand.quadTo(s * 0.12, s * 0.10, s * 0.11, s * 0.24)       # the fingers' rounded ends, down the left
        hand.lineTo(s * 0.08, s * 0.46)
        hand.quadTo(s * 0.07, s * 0.58, s * 0.20, s * 0.58)
        hand.lineTo(s * 0.38, s * 0.58)          # the thumb, pointing down
        hand.lineTo(s * 0.34, s * 0.80)
        hand.quadTo(s * 0.33, s * 0.92, s * 0.43, s * 0.92)
        hand.quadTo(s * 0.48, s * 0.92, s * 0.51, s * 0.84)
        hand.lineTo(s * 0.64, s * 0.60)
        hand.closeSubpath()
        p.drawPath(hand)
    elif name == "camera":                       # a snapshot (Cogitate): a camera in a colour, the lens cut out
        c = QColor(colour or BLACK)
        p.setPen(Qt.NoPen)
        p.setBrush(c)
        body = QPainterPath()
        body.addRoundedRect(QRectF(s * 0.08, s * 0.30, s * 0.84, s * 0.54), s * 0.09, s * 0.09)
        hump = QPainterPath()
        hump.addRoundedRect(QRectF(s * 0.33, s * 0.18, s * 0.34, s * 0.18), s * 0.05, s * 0.05)
        lens = QPainterPath()
        lens.addEllipse(QPointF(s * 0.5, s * 0.57), s * 0.19, s * 0.19)
        inner = QPainterPath()
        inner.addEllipse(QPointF(s * 0.5, s * 0.57), s * 0.11, s * 0.11)
        p.drawPath(body.united(hump).subtracted(lens).united(inner))
        p.drawEllipse(QRectF(s * 0.74, s * 0.37, s * 0.08, s * 0.08).adjusted(0, 0, 0, 0))
    elif name == "tick":                         # "I found a tick!": a tick (the bug) in the theme colour
        c = QColor(colour or GREEN)
        cx = s * 0.5
        p.setPen(QPen(c, max(1.1, s * 0.065), Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.setBrush(Qt.NoBrush)
        for i, (y, out, down) in enumerate(((0.38, 0.40, -0.10), (0.48, 0.44, 0.0),
                                            (0.58, 0.43, 0.10), (0.67, 0.38, 0.20))):
            for side in (-1, 1):                 # four legs a side, bent at the knee
                knee = QPointF(cx + side * s * (out - 0.12), s * (y - 0.04 + down * 0.3))
                foot = QPointF(cx + side * s * out, s * (y + down))
                p.drawPolyline(QPolygonF([QPointF(cx + side * s * 0.12, s * y), knee, foot]))
        p.setPen(Qt.NoPen)
        p.setBrush(c)
        p.drawEllipse(QRectF(cx - s * 0.20, s * 0.32, s * 0.40, s * 0.52))        # the body
        p.drawEllipse(QRectF(cx - s * 0.09, s * 0.17, s * 0.18, s * 0.19))        # the head
        p.setPen(QPen(c, max(1.0, s * 0.05), Qt.SolidLine, Qt.RoundCap))
        p.drawLine(QPointF(cx - s * 0.04, s * 0.19), QPointF(cx - s * 0.07, s * 0.09))   # mouthparts
        p.drawLine(QPointF(cx + s * 0.04, s * 0.19), QPointF(cx + s * 0.07, s * 0.09))
        light = QColor(WHITE)
        light.setAlpha(110)
        p.setPen(Qt.NoPen)
        p.setBrush(light)
        p.drawEllipse(QRectF(cx - s * 0.12, s * 0.37, s * 0.24, s * 0.20))        # the shield on its back
    elif name == "duplicate":                    # two white pages, black outlines
        p.setPen(QPen(BLACK, max(1.0, s * 0.06)))
        p.setBrush(WHITE)
        p.drawRoundedRect(QRectF(s * 0.14, s * 0.12, s * 0.48, s * 0.56), s * 0.06, s * 0.06)
        p.drawRoundedRect(QRectF(s * 0.38, s * 0.32, s * 0.48, s * 0.56), s * 0.06, s * 0.06)
        p.setPen(QPen(GREEN, max(1.4, s * 0.09), Qt.SolidLine, Qt.RoundCap))
        p.drawLine(QPointF(s * 0.62, s * 0.46), QPointF(s * 0.62, s * 0.74))
        p.drawLine(QPointF(s * 0.48, s * 0.60), QPointF(s * 0.76, s * 0.60))


RESOURCES = __import__("pathlib").Path(__file__).resolve().parent.parent / "resources"


def app_icon() -> QIcon:
    """The Lemmatrix icon, in every size drawn for it (falls back to the SVG)."""
    ic = QIcon()
    folder = RESOURCES / "icons"
    for png in sorted(folder.glob("lemmatrix-*.png")) if folder.exists() else []:
        ic.addFile(str(png))
    if ic.isNull() and (RESOURCES / "lemmatrix.svg").exists():
        ic = QIcon(str(RESOURCES / "lemmatrix.svg"))
    return ic


def ink_icon(name: str, size: int = 22) -> QIcon:
    """An icon drawn in the theme's text colour: dark on the light theme, light on the dark one."""
    from . import theme
    spec = theme.colour("window_text").name()
    if name == "reset-filters":                  # its arrows in the theme colour (lighter on dark)
        spec += ";" + theme.colour("pitch").name()
    return icon(name, size, spec)


THEMED = {"reset-filters", "gear-cells", "gear-columns", "gear-matrix", "find-missing", "move-token",
          "lemma-token", "text-token", "tick", "refresh-text", "camera", "xml-viewer"}   # follow the theme: redrawn on a change


def themed_icon(name: str, size: int = 22) -> QIcon:
    """An icon in the theme's colours where it has them (THEMED), otherwise the plain icon."""
    from . import theme
    if name == "reset-filters":
        return ink_icon(name, size)
    if name in THEMED:
        return icon(name, size, theme.colour("pitch").name())    # the accent, lighter on dark
    return icon(name, size)


def elicit_logo(height: int) -> QPixmap:
    """The ɛλicit logo in the request dialogue: Josh's web icon (Ellicit_webicon.svg) as he drew
    it, its teal in the theme colour (lighter on dark), square."""
    from PySide6.QtCore import QByteArray
    from PySide6.QtSvg import QSvgRenderer
    from .. import elicit_art
    from . import theme
    pm, p = _pixmap(height)
    QSvgRenderer(QByteArray(elicit_art.logo(theme.colour("pitch").name()).encode("utf-8"))).render(
        p, QRectF(0, 0, height, height))
    p.end()
    return pm


def elicit_icon(size: int, waiting: bool = False) -> QIcon:
    """The ɛλicit button: Josh's drawing, its teal in the theme colour (lighter on dark); while
    recordings wait for review, his grey rain cloud with the rain in the theme colour."""
    from . import theme
    return icon("elicit-waiting" if waiting else "elicit", size, theme.colour("pitch").name())


def icon_size(name: str, size: int):
    """The QSize to show an icon at: wide icons keep their proportions."""
    from PySide6.QtCore import QSize
    return QSize(round(size * WIDE.get(name, 1.0)), size)


@lru_cache(maxsize=None)
def icon(name: str, size: int = 22, colour: str | None = None) -> QIcon:
    """A drawn icon; some (the notebook's) take a colour, e.g. the theme's ("a;b" gives a second)."""
    pm, p = _pixmap(size, round(size * WIDE[name]) if name in WIDE else None)
    if name in ("elicit", "elicit-waiting"):     # Josh's drawings; colour: the theme colour for his teal
        from PySide6.QtCore import QByteArray
        from PySide6.QtSvg import QSvgRenderer
        from .. import elicit_art
        svg = elicit_art.svg("main" if name == "elicit" else "waiting", colour or elicit_art.TEAL)
        QSvgRenderer(QByteArray(svg.encode("utf-8"))).render(p, QRectF(0, 0, size, size))
        p.end()
        return QIcon(pm)
    if name in ("xml-viewer", "questions", "cogitate", "todo"):   # Josh's χμλ, ?, Cogitate and To Do; colour: for his teal
        from PySide6.QtCore import QByteArray
        from PySide6.QtSvg import QSvgRenderer
        from .. import elicit_art
        svg = {"xml-viewer": XML_VIEWER_FILE, "questions": QUESTIONS_FILE,
               "cogitate": COGITATE_FILE, "todo": TODO_FILE}[name].read_text(encoding="utf-8")
        if colour:
            svg = re.sub(re.escape(elicit_art.TEAL), colour, svg, flags=re.IGNORECASE)
        QSvgRenderer(QByteArray(svg.encode("utf-8"))).render(p, QRectF(0, 0, size, size))
        p.end()
        return QIcon(pm)
    cs = [QColor(c) for c in colour.split(";")] if colour else []
    _draw(name, size, p, cs[0] if cs else None, cs[1] if len(cs) > 1 else None)
    p.end()
    return QIcon(pm)
