# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders. Additional terms: NOTICE.md
"""The pitch scratchpad (IDEAS.md idea 33): a pitch drawing with a box under it. A trace typed
there (the usual notation, e.g. 55 3:3 21) is drawn as it is typed and played with Enter, a click on
its letter (α, β) or Right Shift+A / Right Shift+B (Josh, 24 October). Nothing is saved anywhere.
Used under a text's lines and in the main window's bottom row.

What a pad holds is a value with a kind (`content()`: {"kind": "pitch", "value": "55 3:3 21"}), and
playing goes by the kind (`PLAYERS`), so segmental comparison (Compare V and Compare C, IDEAS.md
idea 46) can be added later as another kind, with little tabs in the pad to switch."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLineEdit, QVBoxLayout, QWidget

from .widgets import PitchCanvas, ipa_font


def _play_pitch(main, value: str):
    """A pitch trace, in the voice and volume of Settings → Pitch."""
    main.play_pitch(value)


# How each kind of content is played: kind -> function(main, value). Segments come later (idea 46).
PLAYERS = {"pitch": _play_pitch}


class PitchScratchpad(QWidget):
    KIND = "pitch"

    def __init__(self, main, low: int, high: int, tip: str, parent=None):
        super().__init__(parent)
        from .token_dialog import PitchValidator
        self.main = main
        self.kind = self.KIND
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
        row.addWidget(self.edit, 1)                # no play button: the pad's letter plays it
        lay.addLayout(row)

    def set_range(self, low: int, high: int):
        self.canvas.set_range(low, high)

    def content(self) -> dict:
        """What the pad holds: its kind and its value."""
        return {"kind": self.kind, "value": self.edit.text()}

    def play(self):
        """Play what the pad holds, by its kind."""
        c = self.content()
        player = PLAYERS.get(c["kind"])
        if player is not None and c["value"].strip():
            player(self.main, c["value"])


class ComparisonPads(QWidget):
    """The comparison area (Josh, 22 October): two scratchpads, α on top and β under it, for asking
    a speaker "is it A or B?". Each has its letter on its left, large, bold, in the theme colour."""

    def __init__(self, main, low: int, high: int, tip: str, parent=None):
        super().__init__(parent)
        from PySide6.QtWidgets import QGridLayout, QLabel, QToolButton
        grid = QGridLayout(self)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(4)
        self.pads, self.letters = [], []
        for r, (letter, key) in enumerate((("α", "A"), ("β", "B"))):
            # the letter is the play button (Josh, 24 October), its key in the hover
            lbl = QToolButton()
            lbl.setText(letter)
            lbl.setAutoRaise(True)
            lbl.setCursor(Qt.PointingHandCursor)
            f = lbl.font()
            f.setBold(True)
            f.setPointSizeF(f.pointSizeF() * 2.2)
            lbl.setFont(f)
            lbl.setToolTip(f"Play {letter} (Right Shift+{key})")
            pad = PitchScratchpad(main, low, high, tip)
            lbl.clicked.connect(lambda _=False, p=pad: self.play(p))
            grid.addWidget(lbl, r, 0)
            grid.addWidget(pad, r, 1)
            self.letters.append(lbl)
            self.pads.append(pad)
        self.alpha, self.beta = self.pads
        # the pitch system hidden (idea 9): the pads go, α and β stay at the area's left edge
        # (Compare V and Compare C will join them there, idea 46); until then a faint line says why,
        # in italics and intentionally lowercase (Josh, 23 October); right-click it to unhide
        self.main = main
        self.hidden_note = QLabel("pitch hidden")
        f = self.hidden_note.font()
        f.setItalic(True)
        self.hidden_note.setFont(f)
        self.hidden_note.setToolTip("The pitch system is hidden. Right-click to unhide it "
                                    "(or View → Show pitch system, or File → Settings → Pitch)")
        self.hidden_note.setContextMenuPolicy(Qt.CustomContextMenu)
        self.hidden_note.customContextMenuRequested.connect(self._note_menu)
        grid.addWidget(self.hidden_note, 0, 1, 2, 1, Qt.AlignLeft | Qt.AlignVCenter)
        grid.setColumnStretch(1, 1)
        self.restyle()
        self.show_pitch()

    def play(self, pad):
        """A letter clicked (or Right Shift+A / B): play its pad, if it is shown."""
        if pad.isVisible():
            pad.play()

    def play_key(self, key: str):
        """Right Shift+A plays α, Right Shift+B β."""
        i = {"A": 0, "B": 1}.get(key.upper())
        if i is not None:
            self.play(self.pads[i])

    def set_range(self, low: int, high: int):
        for p in self.pads:
            p.set_range(low, high)

    def show_pitch(self, on: bool | None = None):
        """Show the pitch scratchpads, or hide them (the pitch system hidden); None: as the open
        database's Show the pitch system says."""
        from .. import pitchview
        if on is None:
            on = pitchview.shown(pitchview.SCRATCHPADS)
        for p in self.pads:
            p.setVisible(on)
        # the pitch kind has no scratchpads (intonational, unspecified): "no pitch", nothing to unhide
        kind_has = pitchview.has(pitchview.SCRATCHPADS)
        self.hidden_note.setText("pitch hidden" if kind_has else "no pitch")
        self.hidden_note.setToolTip(
            "The pitch system is hidden. Right-click to unhide it (or View → Show pitch system, or "
            "File → Settings → Pitch)" if kind_has else
            "This database's pitch kind has no pitch scratchpads (Edit → Metadata → Pitch kind)")
        self.hidden_note.setContextMenuPolicy(Qt.CustomContextMenu if kind_has else Qt.NoContextMenu)
        # no reminder where the kind has no pitch at all (Josh, 23 October: an annoying reminder to
        # non-tonal researchers that they don't have what they need): α and β alone
        self.hidden_note.setVisible(not on and kind_has)

    def note_menu(self):
        """The right-click menu of the pitch hidden line: Unhide pitch."""
        from PySide6.QtWidgets import QMenu
        m = QMenu(self)
        a = m.addAction("Unhide pitch")
        a.triggered.connect(lambda *_: self.main.set_pitch_shown(True))
        return m

    def _note_menu(self, pos):
        self.note_menu().exec(self.hidden_note.mapToGlobal(pos))

    def restyle(self):
        from . import theme
        self.hidden_note.setStyleSheet(f"color: {theme.colour('disabled').name()};")
        for lbl in self.letters:
            lbl.setStyleSheet(                                      # the accent, lighter on dark
                f"QToolButton {{ color: {theme.colour('pitch').name()}; border: none; padding: 0 4px; }}"
                f"QToolButton:hover {{ background: {theme.wash(0.8).name()}; border-radius: 6px; }}")
