# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders
"""The recording level meter and the level check after recording (Josh, 22 October).

Lemmatrix never changes a recording's level: no gain, no normalising, no limiting. It only shows
the level while recording and says afterwards if a recording clipped or is very quiet, so it can
be recorded again (closer, further away, or with the microphone's level set in the computer's own
sound settings, which happens before the sound is captured).
"""

from __future__ import annotations

import math
import time

import numpy as np
from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget

from . import theme

FLOOR_DB = -60.0          # the meter's left end
AMBER_DB = -12.0          # from here amber: loud enough, getting close
RED_DB = -3.0             # from here red: about to clip
QUIET_DB = -30.0          # a recording whose peak stays below this is called very quiet
CLIP = 0.999              # a sample this close to full scale counts as clipped
HOLD = 1.5                # seconds the peak mark stays


def to_db(level: float) -> float:
    return 20 * math.log10(level) if level > 0 else FLOOR_DB


def check(samples) -> tuple[str, float]:
    """("clipped" | "quiet" | "", the peak in dBFS) for a finished recording."""
    a = np.abs(np.asarray(samples, dtype=np.float64))
    if a.size == 0:
        return "", FLOOR_DB
    peak = float(a.max())
    if int((a >= CLIP).sum()) >= 3:              # a few samples at full scale: clipped
        return "clipped", to_db(peak)
    db = to_db(peak)
    return ("quiet" if db < QUIET_DB else ""), db


def message(verdict: str, db: float) -> str:
    if verdict == "clipped":
        return ("Clipped: too loud for the microphone. Record again a little further away, or with the "
                "microphone's level lower in the computer's sound settings.")
    if verdict == "quiet":
        return (f"Very quiet (peak {db:.0f} dB). Record again closer to the microphone, or with its level "
                "higher in the computer's sound settings.")
    return ""


class LevelMeter(QWidget):
    """A level meter in decibels (−60 to 0 dBFS): green, amber from −12, red from −3, with the
    recent peak held as a line, and a red end that stays lit once anything clipped."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.level = 0.0
        self.peak_db = FLOOR_DB
        self.peak_at = 0.0
        self.clipped = False
        self.setMinimumHeight(16)
        self.setToolTip("Recording level: green is fine, amber is loud, red is about to clip. "
                        "Lemmatrix never changes a recording's level.")

    def sizeHint(self):
        return QSize(220, 16)

    def reset(self):
        self.level, self.peak_db, self.peak_at, self.clipped = 0.0, FLOOR_DB, 0.0, False
        self.update()

    def set_level(self, level: float):
        self.level = max(0.0, min(1.0, level))
        db = to_db(self.level)
        now = time.monotonic()
        if db >= self.peak_db or now - self.peak_at > HOLD:
            self.peak_db, self.peak_at = db, now
        if self.level >= CLIP:
            self.clipped = True
        self.update()

    @staticmethod
    def _x(db: float, w: float) -> float:
        return max(0.0, min(1.0, (db - FLOOR_DB) / -FLOOR_DB)) * w

    def paintEvent(self, event):
        p = QPainter(self)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        w = r.width() - 8                          # the last 8 px: the clip light
        p.fillRect(r, theme.colour("chip_blank"))
        green, amber, red = QColor("#2e9e44"), QColor("#e0a020"), QColor("#d93030")
        x = self._x(to_db(self.level), w)
        for lo, hi, c in ((FLOOR_DB, AMBER_DB, green), (AMBER_DB, RED_DB, amber), (RED_DB, 0.0, red)):
            a, b = self._x(lo, w), min(self._x(hi, w), x)
            if b > a:
                p.fillRect(QRectF(r.left() + a, r.top() + 1, b - a, r.height() - 2), c)
        p.setPen(QPen(QColor(theme.muted()), 1))
        for db in (AMBER_DB, RED_DB):              # faint marks where the zones start
            xx = r.left() + self._x(db, w)
            p.drawLine(int(xx), int(r.top()), int(xx), int(r.bottom()))
        if self.peak_db > FLOOR_DB:
            xx = r.left() + self._x(self.peak_db, w)
            p.setPen(QPen(QColor(theme.colour("text")), 2))
            p.drawLine(int(xx), int(r.top()), int(xx), int(r.bottom()))
        p.fillRect(QRectF(r.right() - 6, r.top() + 1, 6, r.height() - 2), red if self.clipped else QColor("#bbbbbb"))
        p.setPen(QPen(QColor(theme.muted()), 1))
        p.setBrush(Qt.NoBrush)
        p.drawRect(r)
        p.end()
