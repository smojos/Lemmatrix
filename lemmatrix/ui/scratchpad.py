# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders
"""The pitch scratchpad (IDEAS.md idea 33): a pitch drawing with a box under it. A trace typed
there (the usual notation, e.g. 55 3:3 21) is drawn as it is typed and played with the button or
Enter. Nothing is saved anywhere. Used under a text's lines and in the main window's bottom row."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLineEdit, QVBoxLayout, QWidget

from .widgets import PitchCanvas, ipa_font


class PitchScratchpad(QWidget):
    def __init__(self, main, low: int, high: int, tip: str, parent=None):
        super().__init__(parent)
        from .main_window import tool
        from .token_dialog import PitchValidator
        self.main = main
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 2, 0, 0)
        lay.setSpacing(2)
        self.canvas = PitchCanvas(low=low, high=high, font=ipa_font(main.prefs.ipa_size + 3))
        self.canvas.setToolTip("Pitch scratchpad: the trace typed below, drawn")
        lay.addWidget(self.canvas)
        row = QHBoxLayout()
        row.setSpacing(4)
        self.edit = QLineEdit()
        self.edit.setPlaceholderText("pitch scratchpad, e.g. 55 3:3 21")
        self.edit.setToolTip(tip)
        self.edit.setValidator(PitchValidator(self.edit))
        self.edit.setFont(ipa_font(main.prefs.ipa_size))
        self.edit.textChanged.connect(self.canvas.set_pitch)
        self.edit.returnPressed.connect(self.play)
        play = tool("Play pitch scratchpad", "play-pitch", self.play, "Play the pitch scratchpad")
        play.setToolButtonStyle(Qt.ToolButtonIconOnly)
        row.addWidget(self.edit, 1)
        row.addWidget(play)
        lay.addLayout(row)

    def set_range(self, low: int, high: int):
        self.canvas.set_range(low, high)

    def play(self):
        """The trace, in the voice and volume of Settings → Pitch."""
        self.main.play_pitch(self.edit.text())


class ComparisonPads(QWidget):
    """The comparison area (Josh, 22 October): two scratchpads, α on top and β under it, for asking
    a speaker "is it A or B?". Each has its letter on its left, large, bold, in the theme colour."""

    def __init__(self, main, low: int, high: int, tip: str, parent=None):
        super().__init__(parent)
        from PySide6.QtWidgets import QGridLayout, QLabel
        grid = QGridLayout(self)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(4)
        self.pads, self.letters = [], []
        for r, letter in enumerate(("α", "β")):
            lbl = QLabel(letter)
            f = lbl.font()
            f.setBold(True)
            f.setPointSizeF(f.pointSizeF() * 2.2)
            lbl.setFont(f)
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setToolTip(f"Comparison: pitch trace {letter}")
            pad = PitchScratchpad(main, low, high, tip)
            grid.addWidget(lbl, r, 0)
            grid.addWidget(pad, r, 1)
            self.letters.append(lbl)
            self.pads.append(pad)
        self.alpha, self.beta = self.pads
        self.restyle()

    def set_range(self, low: int, high: int):
        for p in self.pads:
            p.set_range(low, high)

    def restyle(self):
        from . import theme
        for lbl in self.letters:
            lbl.setStyleSheet(f"color: {theme.colour('pitch').name()};")   # the accent, lighter on dark
